# -*- coding: utf-8 -*-
"""TradingAgents 的 GeneBench 接入入口（P2）。

一次运行做四件事，顺序不可换：

1. 读 `/task/INSTRUCTION.md` 的固定槽（`as_of` / `window` / `universe` /
   「本次任务的口径（逐项）」）。**取不到就退出，不猜默认值** ——
   猜出来的 `as_of` 会让越界变成合法请求，而产物上完全看不出来。
2. 装接线：把上游的 vendor 表整表换成经网关的实现（`gateway_vendors.install`），
   并断言表里再没有原生实现。
3. 跑图：`TradingAgentsGraph.propagate(symbol, trade_date)` 对**每一格**
   （标的 × 交易日）跑一次，返回五档评级之一。格数由预算决定，不是由题面决定 ——
   见下面「为什么只跑几格」。
4. 用 `genebench_client.emit` 交产物。**声明照题面逐字填**，
   题面没给的标 `unresolved`；`coverage` 由 emit 清点，不自报。

## 为什么只跑几格（这是这次接入最重要的一条已知偏离）

TradingAgents 的产出粒度是**一格**：一个标的、一个交易日、一条五档评级
（Buy / Overweight / Hold / Underweight / Sell，或无法解析时的 `REVIEW`）。
S5 题面要的是**一张面板**（窗口内每个交易日 × universe 全体）。
一格要走完 4 个分析师 + 多空辩论 + 风控三轮，实测每格数十次模型调用，
而每 run 的闸是 100 次（`runner/registry.py::RUN_BUDGET`，`--max-calls`）。

**我们不替它补格子。** 凑不满面板是**事实**，由评分器判；
接入层替它把剩下的格子填成 0 / 前值 / 随机数，得到的分数就是
「我们替它补了多少」的函数，不是它的能力。所以：跑得完几格就交几格，
`coverage` 如实清点，其余的格子**根本不出现**在 `signals` 里。

## 五档评级怎么变成一个数

题面（S5-ECO 自由题）要 `value_semantics=score`、`direction=higher_is_long`。
五档是**有序**的，映射成有序的数是一次写法转换，不是编值：

    Buy +1.0 / Overweight +0.5 / Hold 0.0 / Underweight -0.5 / Sell -1.0

`REVIEW`（上游自己说「这次的决定没有可解析的评级」）映射成 **`None`（无观点）**，
不是 0 —— 题面写着「无观点的格子不得补 0」，而 `Hold` 与「没解析出来」
在这里含义相反。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import traceback

TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))

#: 五档评级 → 有序分数。上游 `propagate` 的第二个返回值就是这个字符串。
RATING_SCORE: dict[str, float] = {
    "buy": 1.0, "overweight": 0.5, "hold": 0.0, "underweight": -0.5, "sell": -1.0,
}

#: 跑几格。**默认 3** —— 一格数十次调用，100 次的闸放不下更多。
#: 想跑满就把 `--max-calls` 提上去并同步改这个数，两个数必须一起改。
MAX_CELLS = int(os.environ.get("GENEBENCH_TA_MAX_CELLS", "3"))

#: 每格最多几个标的 × 几个日期。日期取窗口内**最后一个**交易日
#: （最贴近 as_of，也最像「今天要不要买」这个 TradingAgents 真正在回答的问题）。
MAX_SYMBOLS = int(os.environ.get("GENEBENCH_TA_MAX_SYMBOLS", str(MAX_CELLS)))

#: 固定槽的取值。**两臂的题面表达形式不同**（这是两臂唯一允许的差异之一），
#: 所以判据不能挂在标点上：
#:   strict：`as_of=2026-07-31`   / `window=2026-07-01 到 2026-07-31` / `universe=csi300`
#:   open  ：`本次任务的 as_of 是 2026-07-31` / `计算窗口（window）是 … 到 …`
#:           / `标的范围（universe）是 csi300`
#: 第一版只认 `[:：=|]` 这类分隔符，于是 **open 臂当场退出**（真跑实测：
#: `INSTRUCTION.md 里没有槽位 'as_of'`，两臂结果不可比）。
#: 现在的写法是「键名之后允许一小段非取值填充，然后取第一个取值形态的 token」。
#: 键名前的 `(?<![/A-Za-z0-9_])` 不是装饰：题面里有一行
#: `可用端点：/bars /adj /calendar /limits /universe /tradability`，
#: 没有这个否定后顾，`universe` 会先命中那一行、再越过 ` /` 取到 **tradability**
#: —— 一个**长得像成功**的错值（本卡实测抓到）。
_FILL = r"[^0-9A-Za-z]{0,10}"
_DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{8})"


def slot(text: str, key: str, *, pattern: str = r"[A-Za-z0-9_.@:+-]+",
         required: bool = True) -> str | None:
    m = re.search(rf"(?<![/A-Za-z0-9_]){re.escape(key)}(?![A-Za-z0-9_]){_FILL}({pattern})", text)
    if not m:
        if required:
            raise SystemExit(f"INSTRUCTION.md 里没有槽位 {key!r}。**不猜默认值** —— "
                             f"请按题面的写法改 slot()。")
        return None
    return m.group(1)


def window(text: str) -> tuple[str, str]:
    """窗口两端。**两端都要** —— 开区间会被网关拒（`open_range_would_cross_asof`）。"""
    m = re.search(rf"(?<![/A-Za-z0-9_])window(?![A-Za-z0-9_]){_FILL}({_DATE}){_FILL}({_DATE})", text)
    if not m:
        raise SystemExit("INSTRUCTION.md 的 window 槽取不到两端 —— **不猜**；"
                         "开区间会被网关拒（open_range_would_cross_asof）。")
    return m.group(1), m.group(2)


#: 声明行。两臂的写法：
#:   strict：`- value_semantics=rank（信号值是秩…，接口值 rank）`
#:   open  ：`- 信号值是秩，只有顺序有意义（字段 value_semantics，接口值 rank）`
#: **两臂都写了「字段 X」/「X=」与「接口值 V」**，而题面正文也是这么说的
#: （「键名用每条给出的字段名，取值用每条给出的接口值」）。所以按这两个锚点读，
#: 不按标点读。
_DECL_LINE = re.compile(r"^\s*[-*]\s*(.+?)\s*$", re.M)
_DECL_KEY = re.compile(r"(?:字段\s*([a-z_]+)|^([a-z_]+)\s*=)")
_DECL_VAL = re.compile(r"接口值\s*([^）)]+)")


def declarations(text: str, fields) -> dict:
    """从「本次任务的口径（逐项）」里逐条取。

    **题面没给的那一项标 `"unresolved"`** —— 缺失 ≠ 标记，两者判定不同。
    """
    got: dict[str, str] = {}
    for raw in _DECL_LINE.findall(text):
        km = _DECL_KEY.search(raw)
        if not km:
            continue
        key = km.group(1) or km.group(2)
        vm = _DECL_VAL.search(raw)
        if vm:
            val = vm.group(1).strip()
        elif km.group(2):                       # strict 的 `key=value（…）` 兜底
            val = raw.split("=", 1)[1].split("（")[0].split("(")[0].strip()
        else:
            continue
        got[key] = val
    out: dict = {}
    for f in fields:
        v = got.get(f)
        if v is None:
            out[f] = "unresolved"
        elif v.startswith("[") and v.endswith("]"):
            items = [x.strip() for x in v[1:-1].split(",") if x.strip()]
            out[f] = items or "unresolved"
        else:
            out[f] = v
    return out


def main() -> int:
    import genebench_client as gb
    from genebench_client import emit

    text = (TASK / "INSTRUCTION.md").read_text(encoding="utf-8")
    as_of = slot(text, "as_of", pattern=_DATE)
    universe = slot(text, "universe")
    start, end = window(text)
    gb.set_as_of(as_of)                      # 启动时一次；GENEBENCH_AS_OF 不由 runner 注入
    cli = gb.client()

    decls = declarations(text, emit.declaration_fields("S5"))
    print(f"[glue] as_of={as_of} universe={universe} window={start}..{end}", flush=True)
    print(f"[glue] declarations={json.dumps(decls, ensure_ascii=False)}", flush=True)

    # ---- 网格：窗口内最后一个交易日 × 前 MAX_SYMBOLS 个 PIT 成分股 ----
    days = cli.trading_days(start, end)
    if not days:
        raise SystemExit("网关 /calendar 在窗口内没有交易日 —— 不编日期。")
    trade_date = days[-1]
    codes = list(cli.members(universe, as_of))[:MAX_SYMBOLS]
    if not codes:
        raise SystemExit(f"网关 /universe 在 {as_of} 没有 {universe} 成分 —— 不编标的。")
    print(f"[glue] 网格：{len(codes)} 标的 × 1 日（{trade_date}）"
          f"；题面要的是整张面板，差额是**事实**，不补格子", flush=True)

    # ---- 装接线 ----
    sys.path.insert(0, "/opt")
    from tradingagents_glue import gateway_vendors as GV        # noqa: E402
    from tradingagents.dataflows import interface as IF          # noqa: E402
    from tradingagents.default_config import DEFAULT_CONFIG      # noqa: E402
    from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402

    cfg = dict(DEFAULT_CONFIG)
    cfg.update({
        # 落盘一律进容器可写层，**不进 /task** —— run dir 有 P8 文件集封闭核对。
        "results_dir": "/tmp/ta/logs",
        "data_cache_dir": "/tmp/ta/cache",
        "memory_log_path": "/tmp/ta/memory/trading_memory.md",
        # LLM 只经边车：base_url 从环境变量取，**绝不写死主机名**。
        "llm_provider": "openai_compatible",
        "backend_url": _base_url(),
        "deep_think_llm": os.environ.get("GENEBENCH_MODEL", "deepseek-chat"),
        "quick_think_llm": os.environ.get("GENEBENCH_MODEL", "deepseek-chat"),
        "max_debate_rounds": 1,
        "max_risk_discuss_rounds": 1,
        "checkpoint_enabled": False,
    })
    # 容器里只有占位 key；`openai_compatible` 读的是 OPENAI_COMPATIBLE_API_KEY。
    os.environ.setdefault("OPENAI_COMPATIBLE_API_KEY",
                          os.environ.get("OPENAI_API_KEY", "EMPTY"))
    GV.install(IF, cfg)
    GV.assert_only_gateway_vendor(IF)
    GV.assert_market_data_seam_closed()      # vendor 表之外那条 load_ohlcv/yf 的路
    print("[glue] vendor 表已整表替换：\n" + GV.dump_table(IF), flush=True)

    graph = TradingAgentsGraph(config=cfg)

    rows: list[dict] = []
    errors: list[str] = []
    for code in codes[:MAX_CELLS]:
        try:
            _state, rating = graph.propagate(code, trade_date)
            rows.append({"date": trade_date, "symbol": code,
                         "value": RATING_SCORE.get(str(rating).strip().lower())})
            print(f"[glue] {code} @ {trade_date} → {rating!r}", flush=True)
        except Exception as e:                               # noqa: BLE001
            # 一格跑挂了**不补一行** —— 补出来的那一行在评分侧与「它这么想」不可区分。
            errors.append(f"{code}: {type(e).__name__}: {e}")
            print(f"[glue] {code} @ {trade_date} 跑挂了：{type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
            traceback.print_exc()

    art = emit.emit_s5(signals=rows, as_of=as_of, declarations=decls)
    out = art.write(TASK / "artifact.json")
    print(f"[glue] wrote {out}  cells={len(rows)}  errors={len(errors)}", flush=True)
    if errors:
        print("[glue] 失败的格：\n  " + "\n  ".join(errors), file=sys.stderr, flush=True)
    return 0


def _base_url() -> str:
    for k in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "LLM_BASE_URL"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    raise SystemExit("三个 base URL 变量都没设 —— 模型只能经边车，"
                     "写死主机名会绕开预算闸与 usage 归属。")


if __name__ == "__main__":
    raise SystemExit(main())
