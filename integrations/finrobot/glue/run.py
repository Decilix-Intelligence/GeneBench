# -*- coding: utf-8 -*-
"""FinRobot 的 GeneBench 接入入口（P2）。

一次运行做五件事，顺序不可换：

1. **先顶替 `yfinance`**（`compat.install()`），再 import FinRobot ——
   `finrobot/functional/quantitative.py` 在模块层 `import yfinance as yf`，
   顺序反了就顶替不到（`compat.install()` 对已 import 的模块无效）。
2. 读 `/task/INSTRUCTION.md` 的固定槽（`as_of` / `window` / 「本次任务的口径」）。
   **取不到就退出，不猜默认值** —— 猜出来的 `as_of` 会让越界变成合法请求，
   而产物上完全看不出来。
3. 装接线（`gateway_sources.install()`），并在跑图前把替换表核一遍。
4. 跑 FinRobot 自己的 `SingleAssistant("Market_Analyst")`：题面原文进对话，
   取数由**模型自己**决定调哪个工具、要哪些字段、什么窗口。
5. 用 `genebench_client.emit` 交 S1 产物：`payload.fetches` 由**网关 ledger 逐条清点**
   （不是自报），`fields_obtained` 由真回来的列清点，`declarations` 照题面逐字填。

## 为什么是 S1

FinRobot 的 `Market_Analyst` 是一个**带取数工具的分析 agent**：它的四件套
（company profile / news / basic financials / stock data）全是数据获取。
S1（「经数据网关取指定字段与窗口的日线，把每一次取数写成结构化记录」）
是它能力的正面照；S3/S4/S6/S7 那几档要的是因子/组合/回测，它没有对应部件。

## 产物是谁写的

**格式这一层是接线层写的，内容是 agent 取的。** FinRobot 没有"产物"这个概念，
所以 `emit` 由本文件调用；但 `fetches` 的每一行都来自网关 ledger ——
agent 没取的东西，产物里不会有；agent 取多了的东西，产物里也赖不掉。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import traceback

TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))

#: 一切落盘去可写层。**不进 `/task`** —— run dir 有 P8 文件集封闭核对，
#: autogen 的 `coding/`、`.cache/` 落在 `/task` 下就是"来路不明的文件"。
SCRATCH = pathlib.Path(os.environ.get("GENEBENCH_FR_SCRATCH", "/tmp/fr"))

#: 对话最多几轮（autogen 的 `max_consecutive_auto_reply`）。
#: 每轮一次模型调用，闸是 100 次/run（`runner/registry.py::RUN_BUDGET`）。
MAX_TURNS = int(os.environ.get("GENEBENCH_FR_MAX_TURNS", "12"))

# 固定槽的取法逐字借自 integrations/tradingagents/glue/run.py（同一批题面、
# 同样两臂表达形式不同的问题；那边真跑实测过 open 臂的坑，这里不重新踩一遍）。
_FILL = r"[^0-9A-Za-z]{0,10}"
_DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{8})"


def slot(text: str, key: str, *, pattern: str = r"[A-Za-z0-9_.@:+-]+",
         required: bool = True) -> str | None:
    """题面固定槽。键名前的否定后顾不是装饰：题面里有一行
    `可用端点：/bars /adj /calendar /limits /universe /tradability`，
    没有它 `universe` 会先命中那一行、再取到 **tradability** —— 一个长得像成功的错值。
    """
    m = re.search(rf"(?<![/A-Za-z0-9_]){re.escape(key)}(?![A-Za-z0-9_]){_FILL}({pattern})", text)
    if not m:
        if required:
            raise SystemExit(f"INSTRUCTION.md 里没有槽位 {key!r}。**不猜默认值**。")
        return None
    return m.group(1)


def window(text: str) -> tuple[str, str]:
    m = re.search(rf"(?<![/A-Za-z0-9_])window(?![A-Za-z0-9_]){_FILL}({_DATE}){_FILL}({_DATE})", text)
    if not m:
        raise SystemExit("INSTRUCTION.md 的 window 槽取不到两端 —— **不猜**。")
    return m.group(1), m.group(2)


_DECL_LINE = re.compile(r"^\s*[-*]\s*(.+?)\s*$", re.M)
_DECL_KEY = re.compile(r"(?:字段\s*([a-z_]+)|^([a-z_]+)\s*=)")
_DECL_VAL = re.compile(r"接口值\s*([^）)]+)")


def declarations(text: str, fields) -> dict:
    """从「本次任务的口径（逐项）」里逐条取；题面没给的标 `"unresolved"`。"""
    got: dict[str, str] = {}
    for raw in _DECL_LINE.findall(text):
        km = _DECL_KEY.search(raw)
        if not km:
            continue
        key = km.group(1) or km.group(2)
        vm = _DECL_VAL.search(raw)
        if vm:
            val = vm.group(1).strip()
        elif km.group(2):
            val = raw.split("=", 1)[1].split("（")[0].split("(")[0].strip()
        else:
            continue
        got[key] = val
    out: dict = {}
    for f in fields:
        v = got.get(f)
        out[f] = "unresolved" if v is None else v
    return out


def _base_url() -> str:
    for k in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "LLM_BASE_URL"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    raise SystemExit("三个 base URL 变量都没设 —— 模型只能经边车，"
                     "写死主机名会绕开预算闸与 usage 归属。")


def _ledger_to_fetches(ledger, emit) -> list[dict]:
    """网关 ledger → `payload.fetches`。**逐条清点，一条不漏也一条不编。**

    * `fetched_at` 取网关回包头 `x-genebench-ts`（ledger 里的 `ts`），
      **不是本地时钟** —— 用系统时钟填必判 `fetch_clock_mismatch`。
    * 404 是垫片的 NO_DATA 探针（打一个白名单之外的路径，让中间件留一行日志），
      它是一次**返回了零行**的取数尝试，所以记 `empty`；
      "为什么空"在 `params` 的 `api=` / `kind=` 里，不在 status 上。
    * 连不上网关的那条（`ts is None`）**不进产物**：没有网关时间戳的行填不出
      合法的 `fetched_at`，编一个就是伪造留痕。它进 stderr。
    """
    out: list[dict] = []
    dropped: list[str] = []
    for e in ledger:
        ts, code = e.get("ts"), e.get("status")
        if not ts:
            dropped.append(f"{e.get('path')} status={code} error={e.get('error')}")
            continue
        status = None
        if isinstance(code, int) and code >= 400 and code not in (403, 429):
            status = "empty"
        out.append(emit.fetch(e.get("path", ""), e.get("params") or {},
                              fetched_at=ts, rows=e.get("rows"),
                              status=status if status else code))
    if dropped:
        print("[glue] 这些请求没有网关时间戳，**不进产物**（不编 fetched_at）：\n  "
              + "\n  ".join(dropped), file=sys.stderr, flush=True)
    return out


def main() -> int:
    SCRATCH.mkdir(parents=True, exist_ok=True)

    # ---- ① 先顶替 yfinance，再 import 上游 ----
    import genebench_client as gb
    from genebench_client import compat, emit
    compat.install()

    # ---- ② 题面 ----
    text = (TASK / "INSTRUCTION.md").read_text(encoding="utf-8")
    as_of = slot(text, "as_of", pattern=_DATE)
    start, end = window(text)
    gb.set_as_of(as_of)                    # GENEBENCH_AS_OF 不由 runner 注入
    decls = declarations(text, emit.declaration_fields("S1"))
    print(f"[glue] as_of={as_of} window={start}..{end}", flush=True)
    print(f"[glue] declarations={json.dumps(decls, ensure_ascii=False)}", flush=True)

    # ---- ③ 接线 ----
    sys.path.insert(0, "/opt")
    from finrobot_glue import gateway_sources as GS               # noqa: E402
    GS.install()
    GS.assert_no_native_datasource()
    GS.assert_market_data_seam_closed()
    print("[glue] data_source 已整层替换：\n" + GS.dump_table(), flush=True)

    # `agent_library` 在模块层抓 toolkit 函数对象，所以 import 必须在 install() 之后。
    from finrobot.agents.agent_library import library              # noqa: E402
    from finrobot.agents.workflow import SingleAssistant           # noqa: E402

    # `agent_library` 在模块层抓函数对象。上面的 import 顺序保证它抓到的已经是
    # 换过的那份，但**顺序不能是唯一的保证** —— 谁在别处先 import 一次
    # `finrobot.agents.*`，这里就会静默拿到原生实现（镜像内自检抓到过一次）。
    rebound = GS.patch_library(library)
    if rebound:
        print(f"[glue] toolkit 表里重绑了 {len(rebound)} 项：{rebound}", flush=True)
    toolkits = list(library["Market_Analyst"]["toolkits"]) + list(GS.ADDED_TOOLS)
    native = [getattr(f, "__name__", str(f)) for f in toolkits
              if not getattr(f, GS.MARK, False)]
    if native:
        raise SystemExit(f"工具表里还有上游原件：{native} —— 那是一条未声明的数据源。")
    library["Market_Analyst"]["toolkits"] = toolkits
    print(f"[glue] Market_Analyst 的工具表（{len(toolkits)}）："
          + ", ".join(getattr(f, "__name__", str(f)) for f in toolkits), flush=True)

    # ---- ④ 跑 FinRobot 自己的工作流 ----
    llm_config = {
        "config_list": [{
            "model": os.environ.get("GENEBENCH_MODEL", "deepseek-chat"),
            "base_url": _base_url(),                 # 边车；**不写死主机名**
            "api_key": os.environ.get("OPENAI_API_KEY", "EMPTY"),  # 容器里只有占位 key
        }],
        "timeout": int(os.environ.get("GENEBENCH_FR_TIMEOUT", "300")),
        "temperature": 0,
        "cache_seed": None,       # 关掉 autogen 的磁盘缓存（否则往 cwd 写 .cache/）
    }
    os.chdir(SCRATCH)             # autogen 的 coding/ 与缓存都相对 cwd —— 别落进 /task
    assistant = SingleAssistant(
        "Market_Analyst", llm_config,
        max_consecutive_auto_reply=MAX_TURNS,
        code_execution_config={"work_dir": str(SCRATCH / "coding"), "use_docker": False},
    )

    message = text + "\n\n" + (
        "You are running inside a sandbox with no internet access. Every piece of data "
        "must come from the tools registered above, which read from the task's data "
        "gateway; there is no other data source. Tools that answer with `NO_DATA:` have "
        "no source in this environment — do not substitute a guess for them.\n"
        f"The window is {start} to {end} (both inclusive) and as_of is {as_of}.\n"
        "Fetch what the task asks for, then summarise in plain text which endpoint you "
        "called, with which parameters, and which fields you actually obtained. "
        "Reply TERMINATE when done."
    )
    try:
        assistant.chat(message)
    except Exception as exc:                                       # noqa: BLE001
        # 跑挂了**照样交产物** —— ledger 里已经发生的取数是事实，
        # 丢掉它等于把"它取过数"抹成"它什么都没做"。
        print(f"[glue] 对话中断：{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc()

    # ---- ⑤ 产物 ----
    fetches = _ledger_to_fetches(gb.client().ledger, emit)
    fields = GS.fields_obtained()
    art = emit.emit_s1(fetches=fetches, fields_obtained=fields,
                       as_of=as_of, declarations=decls)
    out = art.write(TASK / "artifact.json")
    print(f"[glue] wrote {out}  fetches={len(fetches)}  fields_obtained={fields}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
