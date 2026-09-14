# -*- coding: utf-8 -*-
"""无头自检：不打网关、不调真模型、`--network none` 也能跑完。

    docker run --rm --network none --user 1000:1000 \
      -v $PWD/finmem/smoke_in_container.py:/tmp/smoke.py:ro \
      gb-finmem-u:r1 /opt/finmem/venv/bin/python /tmp/smoke.py     # → SMOKE-OK

它证明七件事：

1. 上游装上了（`puppy` 三个入口都在），而且是**在 3.10 那个 venv 里**；
2. 两处接线点**在替换之前各自都是红的**（非空证明 —— 一道永远绿的门证明不了任何事）；
3. 装上之后都转绿；
4. 离线向量后端是确定性的、维度对、空文本不产生全零向量；
5. **整条 FinMem 循环在零外网下跑得通**：faiss 记忆库 + guardrails 解析 +
   train 段建记忆 + test 段出 buy/hold/sell（模型换成回环上的一个桩，
   只为证明链路，不证明任何模型能力）；
6. 题面固定槽解析 + `emit.emit_s5` 走得通，产物落在 `/task/artifact.json`；
7. `puppy/` 全树没有第二条取数路径（没有任何行情/新闻源主机名）。

第 7 条是这个接入与 TradingAgents 最大的不同：FinMem 的**运行期不取数**，
它读一个离线造好的 pkl，所以「取数是否全部经过数据面」这件事在它身上
是由结构保证的，不是由我们穷举替换点保证的。
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("  OK   " if cond else "  FAIL ") + name + (f"  {detail}" if detail else ""),
          flush=True)
    if not cond:
        FAILS.append(name)


# ── 桩模型：回环上的一个 OpenAI 兼容 chat 端点 ──────────────────────────
_STUB_BODY = {
    "investment_decision": "buy",
    "summary_reason": "smoke stub: deterministic canned answer, no model was called.",
    "short_memory_index": [{"memory_index": -1}],
    "middle_memory_index": [{"memory_index": -1}],
    "long_memory_index": [{"memory_index": -1}],
    "reflection_memory_index": [{"memory_index": -1}],
}
CALLS: list[str] = []


class _Stub(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        CALLS.append(self.path)
        payload = json.dumps({"choices": [{"message": {
            "role": "assistant", "content": json.dumps(_STUB_BODY)}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
        body = payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # 静音
        return


def start_stub() -> str:
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/v1"


def main() -> int:
    src = os.environ.get("GENEBENCH_FINMEM_SRC", "/opt/finmem/src")
    root = "/opt/finmem"
    sys.path[:0] = [src, root]

    # 环境：桩模型 + 关掉 embeddings 探针（--network none 下它必然失败，
    # 而这里要测的是离线后端本身，不是探针）。
    os.environ["OPENAI_BASE_URL"] = start_stub()
    os.environ["OPENAI_API_KEY"] = "placeholder-not-a-credential"
    os.environ["GENEBENCH_FINMEM_EMB_PROBE"] = "0"
    os.environ["GENEBENCH_FINMEM_TRAIN_DAYS"] = "2"
    os.environ["GENEBENCH_FINMEM_TEST_DAYS"] = "2"
    task = pathlib.Path(os.environ.setdefault("GENEBENCH_TASK_DIR", "/tmp/smoke_task"))
    task.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("GENEBENCH_TASK_ID", "s5-smoke-00")
    os.environ.setdefault("GENEBENCH_CONFIG_ID", "cfg-finmem-deepseek")
    os.environ.setdefault("GENEBENCH_ARM", "open")
    os.environ.setdefault("GENEBENCH_RUN_ID", "smoke-local")

    print("[1] 上游与 venv", flush=True)
    check("venv 是 3.10", sys.version_info[:2] == (3, 10), str(sys.version_info[:3]))
    import puppy
    import puppy.agent as agent_mod
    import puppy.chat as chat_mod
    import puppy.memorydb as memorydb_mod
    check("puppy 三个入口都在",
          all(hasattr(puppy, n) for n in ("LLMAgent", "MarketEnvironment", "RunMode")))

    print("[2] 两处接线点在替换之前是红的（非空证明）", flush=True)
    from glue import chat_seam, embedding_seam, instruction

    red = []
    for name, fn in (("chat", lambda: chat_seam.assert_seam_installed(agent_mod, chat_mod)),
                     ("embedding", lambda: embedding_seam.assert_seam_installed(memorydb_mod))):
        try:
            fn()
            red.append(f"{name}:未报")
        except AssertionError:
            pass
    check("替换前两道门都报", not red, ";".join(red))
    # 上游的 parse_response 对 deepseek-chat 这样的模型名**当场抛** —— 这是
    # chat_seam 存在的全部理由，所以这里要看着它抛，而不是相信注释。
    class _Rsp:
        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "hi"}}]}

    raised = None
    try:
        chat_mod.ChatOpenAICompatible.parse_response(
            type("X", (), {"model": "deepseek-chat"})(), _Rsp)
    except NotImplementedError as exc:
        raised = str(exc)
    check("上游的 parse_response 不认 deepseek-chat", raised is not None, raised or "没抛")

    print("[3] 装接线", flush=True)
    chat_seam.install(agent_mod, chat_mod)
    chat_seam.assert_seam_installed(agent_mod, chat_mod)
    embedding_seam.install(memorydb_mod)
    embedding_seam.assert_seam_installed(memorydb_mod)
    check("两道门都转绿", True)

    print("[4] 离线向量后端", flush=True)
    emb = memorydb_mod.OpenAILongerThanContextEmb(embedding_model="text-embedding-ada-002",
                                                  chunk_size=5000, verbose=False)
    check("backend 是 offline_hash", emb.backend == "offline_hash", emb.info.get("reason", ""))
    check("维度 1536", emb.get_embedding_dimension() == 1536)
    a1, a2 = emb(["涨了三天"]), emb(["涨了三天"])
    check("确定性", bool((a1 == a2).all()))
    check("不同文本不同向量", not bool((emb(["涨了三天"]) == emb(["跌了三天"])).all()))
    zero = emb([""])
    check("空文本不是全零向量", float(abs(zero).sum()) > 0)
    check("dtype float32 且形状对", zero.dtype.name == "float32" and zero.shape == (1, 1536))

    print("[5] 整条循环（零外网，模型是回环上的桩）", flush=True)
    # **按文件路径加载**，不用 `import run`：上游自己也有一个 `run.py`
    # （`/opt/finmem/src/run.py`，它的 typer CLI），而 src 在 sys.path 里排在前面
    # —— `import run` 拿到的会是上游那一个。这不是容器入口的问题
    # （入口是 `python /opt/finmem/run.py`，按路径跑），只是自检里必须点名。
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location("gb_finmem_entry", f"{root}/run.py")
    entry = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(entry)
    check("按路径加载的入口不是上游那个 run.py", hasattr(entry, "run_symbol"))

    data = {}
    day = dt.date(2026, 7, 1)
    px = 10.0
    while len(data) < 6:
        if day.weekday() < 5:
            px += 0.1
            data[day] = {"price": {"600000.SH": round(px, 2)},
                         "filing_k": {}, "filing_q": {}, "news": {}}
        day += dt.timedelta(days=1)
    entry.prepare_workdir()
    rows, stats = entry.run_symbol("600000.SH", data, puppy.MarketEnvironment,
                                   puppy.LLMAgent, puppy.RunMode, "deepseek-chat")
    check("桩被调到了", len(CALLS) > 0, f"calls={len(CALLS)} paths={sorted(set(CALLS))}")
    check("train 段有步数", stats["train_steps"] > 0, json.dumps(stats["decisions"]))
    check("test 段出了决策行", len(rows) > 0 and all(set(r) == {"date", "symbol", "value"}
                                                     for r in rows), json.dumps(rows, default=str))
    check("决策落在 {1.0, 0.0, -1.0, None} 里",
          all(r["value"] in (1.0, 0.0, -1.0, None) for r in rows))

    print("[6] 题面解析 + emit", flush=True)
    (task / "INSTRUCTION.md").write_text(
        "本次任务的 as_of 是 2026-07-31。\n"
        "可用端点：/bars /adj /calendar /limits /universe /tradability\n"
        "计算窗口（window）是 2026-07-01 到 2026-07-31。\n"
        "标的范围（universe）是 csi300。\n"
        "本次任务的口径（逐项）：\n"
        "- 信号值是分数（字段 value_semantics，接口值 score）\n"
        "- 信号频率（字段 signal_frequency，接口值 daily）\n"
        "- 方向（字段 direction，接口值 higher_is_long）\n"
        "- 成分参照（字段 universe_ref，接口值 csi300@2026-07-31）\n"
        "- 缺失处理（字段 missing_policy，接口值 keep_null）\n"
        "- 输入因子（字段 input_factors，接口值 [gtja_191.001]）\n", encoding="utf-8")
    from genebench_client import emit

    text = (task / "INSTRUCTION.md").read_text(encoding="utf-8")
    check("as_of 槽", instruction.slot(text, "as_of", pattern=r"\d{4}-\d{2}-\d{2}") == "2026-07-31")
    check("universe 槽不被 /universe 那一行带偏", instruction.slot(text, "universe") == "csi300")
    check("window 两端", instruction.window(text) == ("2026-07-01", "2026-07-31"))
    decls = instruction.declarations(text, emit.declaration_fields("S5"))
    check("六个声明键都取到了且没有 unresolved",
          set(decls) == set(emit.declaration_fields("S5"))
          and "unresolved" not in json.dumps(decls, ensure_ascii=False),
          json.dumps(decls, ensure_ascii=False))
    art = emit.emit_s5(signals=rows, as_of="2026-07-31", declarations=decls)
    out = art.write(task / "artifact.json")
    body = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
    check("产物是 S5 且信封齐", body["stage"] == "S5" and body["schema_version"] == "1.0")
    check("coverage 由 emit 清点",
          body["payload"]["coverage"]["n_valued"] + body["payload"]["coverage"]["n_null"]
          + body["payload"]["coverage"]["n_flat"] == len(rows),
          json.dumps(body["payload"]["coverage"]))

    print("[7] puppy 全树没有第二条取数路径", flush=True)
    hosts = re.compile(r"(yahoo|yfinance|alpaca|polygon|finnhub|sec\.gov|tushare|akshare|"
                       r"eodhd|quandl|tiingo|marketwatch|reddit|stocktwits|fred\.stlouisfed)",
                       re.I)
    hits = []
    for p in sorted(pathlib.Path(src, "puppy").rglob("*.py")):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if hosts.search(line):
                hits.append(f"{p.name}:{i}")
    check("puppy/ 里没有行情/新闻源", not hits, ";".join(hits))

    print(("SMOKE-OK" if not FAILS else "SMOKE-FAIL " + ", ".join(FAILS)), flush=True)
    return 0 if not FAILS else 1


if __name__ == "__main__":
    raise SystemExit(main())
