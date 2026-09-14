"""往 ops/progress.md 末尾**追加**卡 1.1-reconcile 的一行。

用追加而不是整文件覆盖:同一时间可能有别的卡在写这份日志,
覆盖会把别人刚写的行抹掉。也做幂等 —— 已经有这一行就不再追加。
"""
import pathlib
import sys

TARGET = pathlib.Path(__file__).resolve().parents[1] / "progress.md"
MARK = "| 1.1-reconcile |"
text = TARGET.read_text(encoding="utf-8")
if MARK in text:
    print("already appended, no-op")
    sys.exit(0)

ROW = (
    "| 1.1-reconcile | 2026-08-31 06:52 | "
    "**源A(index_weight 月末 diff) vs 源B(qlib instruments)对账**:写 `snapshots/universe_reconcile.py`,"
    "产出 `ops/reports/universe_reconciliation.md`(人读,会被原样贴出去)与 `ops/universe_reconciliation.json`(机器可读);"
    "给 `genebench_config` 加 `REPORTS` 常量;配套 `ops/test_universe_reconcile.py`(27 项)与 "
    "`ops/negctl_universe_reconcile.py`(约定敏感度负控) | "
    "`cd /data/shared/genebench/repo && /data/shared/genebench/env/bin/python -m snapshots.universe_reconcile && "
    "/data/shared/genebench/env/bin/python -m pytest ops/test_universe_reconcile.py -q && "
    "/data/shared/genebench/env/bin/python ops/negctl_universe_reconcile.py` | "
    "`27 passed in 2.90s`(exit=0);成员日 Jaccard **0.972570**(剔除源B csi1000 基期缺口后 **0.994849**);"
    "区间段完全一致 **67.00%** / 容忍内 **87.44%**(剔基期缺口 78.35% / **98.88%**);归因配平 True、未归类 0 | "
    "PASS | "
    "**① 先解决约定再算数字。** 两源不可直接比:源A 是字符串 `YYYYMMDD`、`out_date=prev_trading_day(下一期快照)`、"
    "NULL=右删失;源B 是 `date32`、闭日历区间、`out_date=下一期生效日−1 **日历**天`、且是**贴片式**(每 epoch 一行、首尾相接)。"
    "归一化 = 投影到 `trade_cal` 交易日网格 + 合并网格上相邻的段。**负控实测这三步都有判别力**:"
    "读成半开区间多出 **55,657** 个假分歧成员日;按自然日比多出 **83,251** 个;不合并贴片行则源B 段数虚增 **11.7 倍**"
    "(成员日不变 —— 所以两个层次的指标各防各的错,都得算)。"
    "**② 重叠窗口**:csi300/csi500 `2009-01-23…2026-07-31`、csi1000 `2014-10-31…2026-07-31`;"
    "两源都已被冻结线截断,右端一律是 2026-07-31,左端由源A 决定。源B 窗口前的 csi300 4,200 行 / csi500 2,000 行单独统计,不算分歧。"
    "**③ 分歧归因不重不漏**(各类成员日之和 172,182 == 总对称差 172,182,未归类 0):"
    "指数基期缺口 81.64%(源B 的 csi1000 在 2015-05-29 前只有 3 个成员,即 B-01)、"
    "月末快照粒度边界差 9.96%(源A 约定的分辨率上限,**不是错误**)、"
    "代码映射 5.31%、源B 换仓格点粗 2.15%、退市响应差 0.47%、纯整段有无之差 0.46%。"
    "**④ 自动配对重现了源B 文档 §2.2 的 4 组代码变更**(`000022.SZ↔001872.SZ`、`000043.SZ↔001914.SZ`、"
    "`300114.SZ↔302132.SZ`、`601313.SH↔601360.SH`)—— 判据必须用**日集合 Jaccard**,"
    "用 `|X∩Y|/min(|X|,|Y|)` 会把三个不相干的码全配到同一只票上(实测踩过,测试里钉死了这 4 组)。"
    "**⑤ 方向不是单边的**:源B 的 epoch 在本窗口内每年只有 2~4 个,比源A 的月末网格**更粗** —— "
    "所以「月内调整被源A 抹平」这一类实测 **0 例**,反而是源A 先看到 IPO 快速纳入(`601288.SH` 农业银行早 103 个交易日)"
    "与退市临时替换。退市判词**必须按方向算**:源B 通常晚剔除(`600005.SH` 武钢股份退市后仍在 csi300 挂 83 个交易日),"
    "但 `600357.SH` 是源A 反而多留 2 天,套模板会给出反向的错误结论。"
    "**⑥ 抽样可复现**:种子 `20260731`,用 `sha256(seed|universe|code)` 排序取前 300,"
    "**不用 random/numpy.random**(实现随版本可变,重跑抽到别的票会让签字失效);抽中的 900 只 code 已落盘进 JSON。"
    "**⑦ 20 条签字清单按类型分层挑**(每个非空类型保底 1 条、单类 ≤ 4、类内取最大/中位/最小),覆盖 20 家**不同**公司;"
    "随机挑会把 20 条全砸在基期缺口那一类上。"
    "**⑧ 这不是互证**:源B 上游 chenditc/investment_data 用 Tushare `index_weight` 生成区间,与湖同宗(源B 风险 B-07),"
    "对得上只说明口径一致,**对不上的地方才有信息量**。"
    "**⑨ 遗留(不是本卡的)**:全套合跑 `388 passed / 2 failed`,两条红全部来自**另一张卡**的 "
    "`ops/reports/adv_sourceA/adv_a4.py:67` 与 `adv_a5.py:21` —— 它们写了 `duckdb.connect(\":memory:\")`,"
    "被 `test_env.py::test_every_duckdb_connect_in_repo_is_read_only` 与 "
    "`test_lake_baseline.py::test_lake_is_the_only_module_that_connects_to_the_lake` 同时抓住。"
    "本卡最初也踩了同一条(直接 `duckdb.connect`),已改成全程走 `snapshots.lake`(`lake.catalog()` / `lake.query()`),"
    "两条扫描里都已无本卡的行。**那两个文件归其作者处理:要么改走 lake,要么把 `:memory:` 的理由写进 CONNECT_ALLOWLIST。**"
    "**⑩ 未做**:git commit —— 本轮无提交指令,新文件仍是 untracked,由上层统一提交。 |\n"
)
with TARGET.open("a", encoding="utf-8") as fh:
    fh.write(ROW)
print("appended to", TARGET)
