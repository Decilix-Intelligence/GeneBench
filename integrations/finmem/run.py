# -*- coding: utf-8 -*-
"""FinMem 的 GeneBench 接入入口（P2）。

一次运行做五件事，顺序不可换：

1. 读 `/task/INSTRUCTION.md` 的固定槽（`as_of` / `window` / `universe` /
   「本次任务的口径（逐项）」）。**取不到就退出，不猜默认值**。
2. 装三处接线（都在 `glue/`，内核一个字没改）：模型端 `parse_response`、
   记忆端向量后端、数据端 `env_data.pkl`。
3. 按 FinMem 自己的两段式协议跑：**train 段**（用已实现的次日收益做后见之明，
   建记忆）→ **test 段**（不给未来，逐日出 buy / hold / sell）。
   两段**首尾相接、不重叠**：test 段的每一天只用到严格更早的日子。
4. 把 test 段的逐日决策变成 S5 的一格信号：buy +1 / hold 0 / sell -1。
5. `genebench_client.emit` 交产物到 `/task/artifact.json`。

## 为什么必须是两段（这是本接入最重要的一条设计）

FinMem 的 **train 模式不产出交易决策** —— `_construct_train_actions` 直接拿
`cur_record`（次日价 − 当日价）的符号当动作，LLM 在那一段只负责写反思。
`investment_decision` 只在 **test 模式**里产生（`agent.py::__process_test_action`）。
所以「跑一遍 train 就交信号」是不可能的；而「整段都用 train」会把**次日收益**
喂进产出信号的那一步 —— 那是窗口内的前视，网关看不见它（数据全在 as_of 之内），
但它会让分数不是这个系统的能力。

官方的做法是 `sim`（train）落 checkpoint → `sim -rm test -tap <ckpt>` 载入。
本入口不落盘、直接把同一个 agent 对象接着用 —— 与官方的 save→load 等价
（`save_checkpoint` / `load_checkpoint` 存的就是 brain + portfolio +
reflection_result_series_dict + counter，都在对象里），只是少一次 pickle 往返。

## 为什么只交几十格

FinMem 的产出粒度是**一个标的、一天、一条 buy/hold/sell**，而且它是**顺序**的
（第 n 天的记忆来自前 n−1 天）。S5 题面要的是窗口内每个交易日 × universe 全体
的一张面板。每一天要一次模型调用（`num_reasks=1`，最多两次），而每 run 的闸是
100 次（`runner/registry.py::RUN_BUDGET`）。

**我们不替它补格子。** 凑不满是**事实**，由评分器判；接入层把剩下的格子填成
0 / 前值 / 随机数，得到的分数就是「我们替它补了多少」的函数 ——
而且**没有任何信号会红，分数只是更高一点**。跑得完几格就交几格。

**一个标的 × 连续若干天** 而不是 **若干标的 × 一天**：FinMem 的核心是分层记忆，
记忆只有在同一个标的的时间序列上才积累得起来。横着切会把它变成一个没有记忆的
零样本分类器 —— 那测的不是 FinMem。
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import traceback

TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))
#: 上游源码在镜像里的落点（Dockerfile 里 tar 解到这里）。
FINMEM_SRC = os.environ.get("GENEBENCH_FINMEM_SRC", "/opt/finmem/src")
#: 上游把日志写在**相对 CWD** 的 `data/04_model_output_log/` 下（agent.py / memorydb.py
#: 里三处 `logging.FileHandler(os.path.join("data", "04_model_output_log", …))`）。
#: 所以必须先 chdir 到一个可写目录 —— **不能是 /task**（容器里的 /task 就是 run dir
#: 的 work/ 本身，往它下面落东西会破 P8 文件集封闭）。
WORKDIR = pathlib.Path(os.environ.get("GENEBENCH_FINMEM_WORKDIR", "/tmp/finmem"))

#: 三档决策 → 有序分数。题面（S5）要 value_semantics=score、direction=higher_is_long。
#: `hold` 记 0.0：那是 FinMem 自己给出的一档决策（含它 guardrails 解析失败时的
#: 兜底 `investment_decision="hold"`），与「没有观点」含义不同。
DECISION_SCORE: dict[str, float] = {"buy": 1.0, "hold": 0.0, "sell": -1.0}

MAX_SYMBOLS = int(os.environ.get("GENEBENCH_FINMEM_MAX_SYMBOLS", "1"))
TRAIN_DAYS = int(os.environ.get("GENEBENCH_FINMEM_TRAIN_DAYS", "12"))
TEST_DAYS = int(os.environ.get("GENEBENCH_FINMEM_TEST_DAYS", "10"))
#: 连着这么多天一次决策都没拿到就停。预算耗尽（429 budget_exceeded）的现场表现
#: 就是「每一天都拿不到决策」，而上游把任何异常都吞成 `{}`（reflection.py 末尾），
#: 所以不设这道闸的话，它会安安静静地把剩下的天数全跑成空。
MAX_CONSECUTIVE_FAILURES = int(os.environ.get("GENEBENCH_FINMEM_MAX_FAILS", "3"))

SYSTEM_MESSAGE = "You are a helpful assistant."

#: 角色设定。上游示例配置里的那一段是**人工写的 TSLA 先验**（"You are an expert of
#: TSLA … Tesla's continued growth …"）。标的换成 A 股之后逐字照抄等于把一段与标的
#: 无关的先验塞进检索查询（`query_short(query_text=character_string)` 用的就是它）。
#: 这里写的是一段只陈述**题面与本环境事实**的中性 persona：标的是什么、有什么数据、
#: 没有什么数据。**没有任何方向性判断。**
CHARACTER = (
    "You are a disciplined daily trader for the China A-share ticker {symbol}. "
    "In this environment the only market information available to you is the daily "
    "adjusted price series of {symbol}. There are no news articles, no analyst "
    "commentary, no 10-K/10-Q filings and no sentiment feeds -- that absence is a "
    "fact of this environment, not an oversight, so do not assume unseen news exists. "
    "Base your judgement on the price history and on your own accumulated memory."
)


def build_config(symbol: str, model: str) -> dict:
    """FinMem 的 config 字典。

    除了下面点名的四处，**数值逐字照抄上游 `config/tsla_gpt_config.toml`**
    （四个记忆层的衰减、清理阈值、跳层阈值、top_k、look_back_window_size、
    embedding 的 chunk_size）—— 调它们就是在调这个系统本身。

    改的四处：`trading_symbol`（题面的标的）、`character_string`（见 CHARACTER）、
    `[chat].end_point` / `[chat].model`（只能经边车，见 glue/chat_seam.py）。
    """
    from glue import chat_seam

    return {
        "general": {
            "agent_name": "agent_1",
            "trading_symbol": symbol,
            "character_string": CHARACTER.format(symbol=symbol),
            "top_k": 3,
            "look_back_window_size": 7,
        },
        "chat": chat_seam.build_chat_config(model, SYSTEM_MESSAGE),
        "agent": {"agent_1": {"embedding": {"detail": {
            "embedding_model": "text-embedding-ada-002",
            "chunk_size": 5000,
            "verbose": False,
        }}}},
        "short": {
            "importance_score_initialization": "sample",
            "decay_params": {"recency_factor": 3.0, "importance_factor": 0.92},
            "clean_up_threshold_dict": {"recency_threshold": 0.05, "importance_threshold": 5},
            "jump_threshold_upper": 60,
        },
        "mid": {
            "jump_threshold_lower": 60,
            "jump_threshold_upper": 80,
            "importance_score_initialization": "sample",
            "decay_params": {"recency_factor": 90.0, "importance_factor": 0.967},
            "clean_up_threshold_dict": {"recency_threshold": 0.05, "importance_threshold": 5},
        },
        "long": {
            "jump_threshold_lower": 80,
            "importance_score_initialization": "sample",
            "decay_params": {"recency_factor": 365.0, "importance_factor": 0.988},
            "clean_up_threshold_dict": {"recency_threshold": 0.05, "importance_threshold": 5},
        },
        "reflection": {
            "importance_score_initialization": "sample",
            "decay_params": {"recency_factor": 365.0, "importance_factor": 0.988},
            "clean_up_threshold_dict": {"recency_threshold": 0.05, "importance_threshold": 5},
        },
    }


def install_seams():
    """三处接线，**装完各自断言在位**。返回 `puppy` 的几个入口。"""
    if FINMEM_SRC not in sys.path:
        sys.path.insert(0, FINMEM_SRC)
    from glue import chat_seam, embedding_seam

    import puppy.chat as chat_mod
    import puppy.agent as agent_mod
    import puppy.memorydb as memorydb_mod

    chat_seam.install(agent_mod, chat_mod)
    chat_seam.assert_seam_installed(agent_mod, chat_mod)
    embedding_seam.install(memorydb_mod)
    embedding_seam.assert_seam_installed(memorydb_mod)

    from puppy import MarketEnvironment, LLMAgent, RunMode
    return MarketEnvironment, LLMAgent, RunMode


def prepare_workdir() -> None:
    for sub in ("01_raw", "02_intermediate", "03_model_input", "04_model_output_log",
                "05_train_model_output", "06_train_checkpoint"):
        (WORKDIR / "data" / sub).mkdir(parents=True, exist_ok=True)
    os.chdir(WORKDIR)


def run_symbol(symbol: str, data, MarketEnvironment, LLMAgent, RunMode,
               model: str) -> tuple[list[dict], dict]:
    """一个标的：train 段建记忆，test 段逐日出决策。"""
    days = sorted(data)
    need = TRAIN_DAYS + TEST_DAYS + 1
    if len(days) < 3:
        raise SystemExit(f"{symbol} 在窗口内可用的交易日只有 {len(days)} 天，跑不成两段。")
    sel = days[-need:] if len(days) >= need else days
    # test 段要 TEST_DAYS 个决策 → 需要 TEST_DAYS+1 个日期（最后一天只提供次日价）。
    n_test = min(TEST_DAYS, len(sel) - 2)
    split = len(sel) - n_test - 1
    train_dates, test_dates = sel[: split + 1], sel[split:]
    print(f"[glue] {symbol}: train {train_dates[0]}..{train_dates[-1]}"
          f"（{len(train_dates) - 1} 天建记忆） → test {test_dates[0]}..{test_dates[-1]}"
          f"（{len(test_dates) - 1} 天出决策）", flush=True)

    agent = LLMAgent.from_config(build_config(symbol, model))
    stats = {"symbol": symbol, "train_steps": 0, "test_steps": 0,
             "decisions": {}, "failures": []}

    def _loop(start_date, end_date, mode, on_decision=None) -> None:
        env = MarketEnvironment(env_data_pkl=data, start_date=start_date,
                                end_date=end_date, symbol=symbol)
        fails = 0
        while True:
            market_info = env.step()
            if market_info[-1]:
                break
            cur_date = market_info[0]
            agent.counter += 1
            try:
                agent.step(market_info=market_info, run_mode=mode)
            except Exception as exc:                              # noqa: BLE001
                # 一天跑挂了**不补一行** —— 补出来的那一行在评分侧与「它这么想」不可区分。
                stats["failures"].append(f"{cur_date}: {type(exc).__name__}: {exc}"[:300])
                print(f"[glue] {symbol} {cur_date} 跑挂了：{type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
                traceback.print_exc()
                if on_decision is not None:
                    on_decision(cur_date, None)
                fails += 1
                if fails >= MAX_CONSECUTIVE_FAILURES:
                    print(f"[glue] {symbol}: 连着 {fails} 天没拿到决策，停 —— "
                          f"预算耗尽（429 budget_exceeded）的样子就是这样。",
                          file=sys.stderr, flush=True)
                    return
                continue
            fails = 0
            if mode is RunMode.Train:
                stats["train_steps"] += 1
            else:
                stats["test_steps"] += 1
                result = agent.reflection_result_series_dict.get(cur_date)
                decision = None
                if isinstance(result, dict):
                    decision = result.get("investment_decision")
                if on_decision is not None:
                    on_decision(cur_date, decision)

    _loop(train_dates[0], train_dates[-1], RunMode.Train)

    rows: list[dict] = []

    def _record(cur_date, decision) -> None:
        key = str(decision).strip().lower() if decision is not None else None
        # **拿不到决策 → None（无观点），不是 0.0**：题面写着无观点的格子不得补 0，
        # 而 FinMem 的 `hold` 是一档真决策，与「这一天根本没跑出决策」含义相反。
        value = DECISION_SCORE.get(key) if key is not None else None
        stats["decisions"][key or "<none>"] = stats["decisions"].get(key or "<none>", 0) + 1
        rows.append({"date": cur_date, "symbol": symbol, "value": value})
        print(f"[glue] {symbol} @ {cur_date} → {decision!r} → {value!r}", flush=True)

    _loop(test_dates[0], test_dates[-1], RunMode.Test, on_decision=_record)
    return rows, stats


def main() -> int:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import genebench_client as gb
    from genebench_client import emit
    from glue import embedding_seam, env_data, instruction

    text = (TASK / "INSTRUCTION.md").read_text(encoding="utf-8")
    as_of = instruction.slot(text, "as_of", pattern=r"(?:\d{4}-\d{2}-\d{2}|\d{8})")
    universe = instruction.slot(text, "universe")
    start, end = instruction.window(text)
    gb.set_as_of(as_of)              # GENEBENCH_AS_OF 不由 runner 注入；启动时一次
    cli = gb.client()

    decls = instruction.declarations(text, emit.declaration_fields("S5"))
    print(f"[glue] as_of={as_of} universe={universe} window={start}..{end}", flush=True)
    print(f"[glue] declarations={json.dumps(decls, ensure_ascii=False)}", flush=True)

    codes = list(cli.members(universe, as_of))[:MAX_SYMBOLS]
    if not codes:
        raise SystemExit(f"网关 /universe 在 {as_of} 没有 {universe} 成分 —— 不编标的。")

    model = os.environ.get("GENEBENCH_MODEL", "deepseek-chat")
    MarketEnvironment, LLMAgent, RunMode = install_seams()
    print("[glue] 向量后端探针：" + json.dumps(
        embedding_seam.probe("text-embedding-ada-002"), ensure_ascii=False), flush=True)
    prepare_workdir()

    rows: list[dict] = []
    report: list[dict] = []
    for code in codes:
        missing = env_data.note_missing_sources(cli, code, start, end)
        print(f"[glue] {code} NO_DATA 留痕：" + json.dumps(missing, ensure_ascii=False),
              flush=True)
        data = env_data.build(code, start, end)
        print(f"[glue] {code} env_data：{len(data)} 个交易日有价；"
              f"news / filing_k / filing_q 三槽全空", flush=True)
        got, stats = run_symbol(code, data, MarketEnvironment, LLMAgent, RunMode, model)
        rows.extend(got)
        report.append(stats | {"missing_sources": missing, "n_days_priced": len(data)})

    art = emit.emit_s5(signals=rows, as_of=as_of, declarations=decls)
    out = art.write(TASK / "artifact.json")
    print(f"[glue] wrote {out}  cells={len(rows)}", flush=True)
    print("[glue] 接入报告：" + json.dumps(report, ensure_ascii=False, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
