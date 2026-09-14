"""GeneBench 单一配置常量模块.

这是全仓库**唯一**允许出现绝对路径字面量的地方。
任何其它模块都必须 `import genebench_config as cfg` 并使用这里的常量,
禁止把 `/data/shared/genebench`、`/home/ljn/projects/data/...` 之类
硬编码散落到代码里。

T-01 搬家契约
-------------
当前落点 `/data/shared/genebench` 是**临时**的:`/data` 是 root:root 0755,
ljn 无法 `mkdir /data/genebench`,规范落点需要一条人工特权命令
(见 `ops/tickets.md` T-01)。搬家时的改动面 = 本文件的 `_DEFAULT_ROOT`
一行 + 一次 `mv`,不需要改任何其它文件。
也可以完全不改代码,直接用环境变量覆盖::

    GENEBENCH_ROOT=/data/genebench python -m gateway.app

安全红线(代码级)
----------------
红线 4:网关必须绑定 `192.168.1.48`,禁止监听 `0.0.0.0`。
finance01 在 tailscale 上,tailscale 流量绕过 ufw,`0.0.0.0` 等于把执行面
网关对整个 tailnet 敞开。`assert_no_wildcard_bind()` 是这条红线的代码级防线,
任何启动监听的地方都必须先调它。

红线 5:`reference/` 与 `scorer/` 产物不对执行面暴露。本机 umask 是 **002**,
裸 `mkdir` / `os.makedirs` 会静默产出 0775 的组/世界可读目录。
**后续所有卡建目录一律用 `create_dir()`,不要裸 mkdir**;进程入口处调一次
`harden_umask()`。`ops/test_env.py` 会递归审计 `$GENEBENCH_ROOT` 下每个目录。
"""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "GENEBENCH_ROOT",
    "REPO",
    "ENV",
    "LOGS",
    "SNAPSHOTS",
    "RESULTS",
    "WHEELS",
    "OPS",
    "REPORTS",
    "PIP_CONF",
    "DATA_CARDS",
    "SNAPSHOT_VERSION",
    "SNAPSHOTS_V1",
    "UNIVERSE_DIR",
    "UNIVERSE_INTERVALS_PARQUET",
    "UNIVERSE_SOURCE_A_JSON",
    "UNIVERSE_PIT_PARQUET",
    "UNIVERSE_PIT_JSON",
    "UNIVERSE_PIT_CARD",
    "UNIVERSES",
    "MARKET_UNIVERSE",
    "UNIVERSES_PIT",
    "UNIVERSE_INDEX_CODE",
    "INDEX_CODE_UNIVERSE",
    "UNIVERSE_NOMINAL_SIZE",
    "UNIVERSE_SOURCES",
    "BOUNDARY_TOL_TD",
    "TRADABILITY_DIR",
    "TRADABILITY_ACCEPTANCE_DIR",
    "TRADABILITY_ACCEPTANCE_DATE",
    "TRADABILITY_JSON",
    "TRADABILITY_CARD",
    "TRADABILITY_SAMPLE_REPORT",
    "TRADABILITY_STATUSES",
    "TRADABILITY_SUSPEND_BASES",
    "TRADABILITY_DOMAIN_SOURCES",
    "TRADABILITY_SAMPLE_N",
    "TRADABILITY_SAMPLE_DETAIL_N",
    "TRADABILITY_SAMPLE_SEED",
    "LIMIT_PRICE_TOL",
    "NO_PRICE_LIMIT_UP_MIN",
    "NO_PRICE_LIMIT_DOWN_MAX",
    "NO_PRICE_LIMIT_BAND_MAX",
    "NO_PRICE_LIMIT_LEGS",
    "PYTHON",
    "LAKE",
    "CATALOG",
    "GOLD",
    "QLIB_RELEASE",
    "PYTHON_BASE",
    "FREEZE_DATE",
    "GATEWAY_HOST",
    "GATEWAY_PORT",
    "GATEWAY_BASE_URL",
    "WILDCARD_BIND_HOSTS",
    "REQUIRED_DIR_MODE",
    "FORBIDDEN_MODE_BITS",
    "REQUIRED_UMASK",
    "assert_no_wildcard_bind",
    "harden_umask",
    "create_dir",
    # 卡 1.1-a:数据通道(加法,既有名字一个没动)
    "CHANNELS",
    "CHANNEL_ENV",
    "DEFAULT_CHANNEL",
    "PUBLIC_VERSION",
    "SNAPSHOTS_PUBLIC",
    "PUBLIC_TABLES_DIR",
    "PUBLIC_TRADABILITY_DIR",
    "PUBLIC_PROVIDER_DIR",
    "PUBLIC_BUILD_DIR",
    "PUBLIC_STATE_DIR",
    "GATEWAY_PORT_ENV",
    "GATEWAY_PUBLIC_PORT",
    "GATEWAY_ACCESS_LOG_NAME",
    "assert_channel",
    "channel",
    "snapshot_tables_dir",
    "tradability_dir",
    "provider_dir",
    "gateway_access_log",
    "gateway_port",
    # 卡 1.1-b:重建链的落点(加法,既有名字一个没动)
    "snapshot_root",
    "gold_dir",
    "crosscheck_dir",
    "crosscheck_report",
    "epsilon_dir",
    "calibration_path",
    "universe_dir",
    "universe_pit_parquet",
]

# --------------------------------------------------------------------------
# 根路径 —— 搬家唯一改动点
# --------------------------------------------------------------------------

#: 临时落点。规范落点 `/data/genebench` 需要 T-01 特权窗口后才能启用。
_DEFAULT_ROOT = "/data/shared/genebench"

#: 所有 GeneBench 产物的根。可由环境变量 ``GENEBENCH_ROOT`` 覆盖。
#: 目录 mode 必须是 0700 —— `/data/shared` 是 1777 的公共目录,
#: 只有 0700 才能保护 `reference/` 与 `scorer/` 产物不被旁人读到(红线 5)。
GENEBENCH_ROOT: Path = Path(
    os.environ.get("GENEBENCH_ROOT") or _DEFAULT_ROOT
).expanduser()

# --------------------------------------------------------------------------
# 派生路径
# --------------------------------------------------------------------------

#: 代码仓(git 仓库根)
REPO: Path = GENEBENCH_ROOT / "repo"
#: conda clone 出来的隔离运行环境(禁止 pip 进 PYTHON_BASE)
ENV: Path = GENEBENCH_ROOT / "env"
#: 施工/运行日志(conda clone 日志、后续卡的构建日志等)。
#: 必须走这个常量,不要在别处拼 `$GENEBENCH_ROOT/logs` —— T-01 搬家时
#: 只有派生自 `GENEBENCH_ROOT` 的路径会被那"唯一一行"带走。
LOGS: Path = GENEBENCH_ROOT / "logs"
#: 冻结数据快照(parquet / duckdb),大体量,禁落 /home(红线 6)
SNAPSHOTS: Path = GENEBENCH_ROOT / "snapshots"
#: 跑分结果
RESULTS: Path = GENEBENCH_ROOT / "results"
#: 离线 wheel 缓存
WHEELS: Path = GENEBENCH_ROOT / "wheels"
#: 运维:tickets.md / progress.md / 特权事项
OPS: Path = REPO / "ops"

#: 人读报告目录(卡 1.1 的对账报告等)。小文本、进 git、会被原样贴给人看,
#: 所以和 `ops/` 一样留在 REPO 里,不落 `SNAPSHOTS`。
REPORTS: Path = OPS / "reports"

#: **数据卡**目录。一张冻结快照表配一张数据卡:来源、口径、已知局限、
#: "不该拿它做什么"。和 `REPORTS` 一样是进 git 的小文本 —— 数据卡与产物
#: 分家(产物在 `SNAPSHOTS` 下)是刻意的:parquet 单独流转时带不走说明书,
#: 所以产物的 parquet metadata 里另有一份机器可读的口径指纹(见
#: `snapshots/universe_build.py::_PARQUET_METADATA`)。
DATA_CARDS: Path = OPS / "data_cards"

#: **本项目唯一该用的解释器**(card 0.1 由 `conda create --clone qlib_env` 建出)。
#: 任何 subprocess 起 python、任何文档里的跑法,都用这个常量,不要写死路径,
#: 也不要退回 `PYTHON_BASE` —— 那是只读的用户环境,往里装东西违反红线 2。
#: 万一 clone 环境不可用,改这一行指向可用解释器即可,调用方不用动。
PYTHON: Path = ENV / "bin" / "python"

#: pip 镜像配置。用法::
#:     PIP_CONFIG_FILE=$GENEBENCH_ROOT/pip.conf pip install ...
#: 刻意**不**写 `~/.config/pip/pip.conf` —— 那是用户既有配置,红线 2 不许碰。
PIP_CONF: Path = GENEBENCH_ROOT / "pip.conf"

# --------------------------------------------------------------------------
# 冻结快照产物(大体量,只落 `$GENEBENCH_ROOT`,红线 6 —— **不进 repo**)
# --------------------------------------------------------------------------

#: 快照版本号。一次冻结 = 一个版本目录,历史版本不覆盖。
SNAPSHOT_VERSION: str = "v1"

#: 本版本的快照根。`repo/` 只放代码,parquet/duckdb 一律落这里。
SNAPSHOTS_V1: Path = SNAPSHOTS / SNAPSHOT_VERSION

#: PIT 宇宙产物目录(卡 1.1 / 1.2 / 1.3)。
UNIVERSE_DIR: Path = SNAPSHOTS_V1 / "universe"

#: 卡 1.1 **源A** 产物:index_weight 月末快照相邻期 diff 推出的成分区间表。
UNIVERSE_INTERVALS_PARQUET: Path = UNIVERSE_DIR / "index_weight_intervals.parquet"

#: 卡 1.1 源A 的统计摘要 + 数据卡(约定、局限、与源B 的对齐分析)。
#: 这是**小文本**、要进 git、要被人读,所以刻意落 `ops/` 而不是 `SNAPSHOTS`。
UNIVERSE_SOURCE_A_JSON: Path = OPS / "universe_source_A.json"

#: 卡 1.1 **收口**产物:三源合并后的最终 PIT 宇宙表。**下游只该读这一张**,
#: 源A / 源B 的中间产物是给对账用的,不是给回测用的。
UNIVERSE_PIT_PARQUET: Path = UNIVERSE_DIR / "universe_pit.parquet"

#: `universe_pit` 的机器可读摘要(统计 + 口径 + 完整性自查)。
UNIVERSE_PIT_JSON: Path = OPS / "universe_pit.json"

#: `universe_pit` 的**数据卡**(人读)。由 `snapshots/universe_build.py` 生成 ——
#: 手写会和产物漂移,数据卡里的每个数字都必须是这次产出现算的。
UNIVERSE_PIT_CARD: Path = DATA_CARDS / "universe_pit.md"

# --------------------------------------------------------------------------
# 宇宙定义(v1 基准的三个股票池)
# --------------------------------------------------------------------------

#: v1 的三个宇宙。顺序即产物里的排序顺序,不要改。
UNIVERSES: tuple[str, ...] = ("csi300", "csi500", "csi1000")

#: 宇宙名 → 湖内 `index_weight.index_code`。
#: 湖里**只有**这三个指数(卡 0.2 实测),所以这张表就是全集。
UNIVERSE_INDEX_CODE: dict[str, str] = {
    "csi300": "000300.SH",
    "csi500": "000905.SH",
    "csi1000": "000852.SH",
}

#: 反向映射,读湖出来的 `index_code` 直接翻成宇宙名。
INDEX_CODE_UNIVERSE: dict[str, str] = {
    _code: _uni for _uni, _code in UNIVERSE_INDEX_CODE.items()
}

#: 各宇宙的**名义**成分数。"每期恰好这么多"是数据质量判据,
#: 不是可以随便放宽的软约束 —— 对不上就要点名是哪几期、差多少。
UNIVERSE_NOMINAL_SIZE: dict[str, int] = {
    "csi300": 300,
    "csi500": 500,
    "csi1000": 1000,
}

#: **市场全集**宇宙名。它不是指数,没有名义规模,成员数随上市/退市自然变化;
#: 唯一来源是 `stock_basic` 的 `list_date` / `delist_date`(第三源兜底),
#: 所以它在 `universe_pit` 里的 `source` 恒为 `basic_fallback`、
#: `agreement_flag` 恒为空(无第二源可对)。
MARKET_UNIVERSE: str = "all"

#: `universe_pit` 里出现的全部宇宙。**顺序即产物排序顺序**,不要改。
#: 刻意与 `UNIVERSES` 分开:`UNIVERSES` 是"有指数成分源的三个基准宇宙",
#: 一切"两源对账"的逻辑只对它们成立;`all` 是单源宇宙,混进去会让
#: `agreement_flag` 的语义整个垮掉。
UNIVERSES_PIT: tuple[str, ...] = UNIVERSES + (MARKET_UNIVERSE,)

#: `universe_pit.source` 的取值全集(枚举,不许出现别的值)。
#:
#: * ``index_weight``     —— 只有源A(湖 index_weight 月末快照 diff)这么说
#: * ``qlib_instruments`` —— 只有源B(qlib instruments)这么说
#: * ``both``             —— 两源都这么说
#: * ``basic_fallback``   —— 第三源(stock_basic 上市窗口)兜底,`all` 宇宙专用
UNIVERSE_SOURCES: tuple[str, ...] = (
    "index_weight",
    "qlib_instruments",
    "both",
    "basic_fallback",
)

#: 两源边界差的容忍上限,单位 **交易日**。
#:
#: 不是拍脑袋:源B 的 `in_date` 是成分调整**生效日**,源A 最早也要等到生效日
#: 之后的第一期**月末快照**才看得见这次调整。一个自然月约 20~23 个交易日,
#: 取上界 23。超过这个数的偏差就不再能用"月末粒度"解释,必须单独归类。
#: 卡 1.1-reconcile 用的就是这个常量(那里叫 `BOUNDARY_TOL_TD`),
#: 收口时提到 cfg 里来 —— 两处各写一份必然漂移。
BOUNDARY_TOL_TD: int = 23

# --------------------------------------------------------------------------
# 卡 1.2:可交易性视图 `tradability`
# --------------------------------------------------------------------------

#: `tradability` 产物目录,**按年分区**:`year=YYYY/part-0.parquet`。
#: 上界 = `FREEZE_DATE`(红线 7)。体量约 1500 万行,只落 `SNAPSHOTS`,不进 git。
TRADABILITY_DIR: Path = SNAPSHOTS_V1 / "tradability"

#: **验收专用**切片目录,与冻结产物**物理分家**。
#: 里面的日期在冻结线**之外**,只为复现实施稿点名的两个实测样例而存在。
#: 目录名里带 `acceptance` 是刻意的:任何人 glob `tradability/` 都不会误捞到它,
#: 而误把它拼进训练/回测窗口就等于越过红线 7。
TRADABILITY_ACCEPTANCE_DIR: Path = SNAPSHOTS_V1 / "tradability_acceptance"

#: 验收切片的日期(冻结线之外)。实施稿点名的两个样例都在这一天:
#: `000711.SZ` = suspend 且 daily 无行;`600491.SH` = trade(当日复牌 R)。
TRADABILITY_ACCEPTANCE_DATE: str = "2026-08-28"

#: `tradability` 的机器可读摘要(口径 + 分布 + 完整性自查)。进 git。
TRADABILITY_JSON: Path = OPS / "tradability.json"

#: `tradability` 的**数据卡**(人读)。由 `snapshots/tradability.py` 生成。
TRADABILITY_CARD: Path = DATA_CARDS / "tradability.md"

#: 验收 (b):10 条抽样的**完整判定链路取证**表,供人照着链路自行复核。
TRADABILITY_SAMPLE_REPORT: Path = REPORTS / "tradability_sample_10.md"

#: `tradability.status` 的取值全集。**产物里不许出现这张表之外的值。**
#:
#: 优先级(从上到下,先命中先定):
#:
#: 1. ``no_data``    —— daily 无行,且 suspend_d 没有任何"这天停牌"的证据。
#: 2. ``suspend``    —— daily 无行,且 suspend_d 说停牌(直接 S,或从前一个 S 顺延)。
#: 3. ``limit_up``   —— daily 有行且 **收盘价 == 涨停价**(收盘封板,买不进)。
#: 4. ``limit_down`` —— daily 有行且 **收盘价 == 跌停价**(收盘封板,卖不出)。
#: 5. ``trade``      —— daily 有行且收盘没封板。
#:
#: ⚠️ `limit_up` / `limit_down` 是**收盘口径**。盘中触板是另一件事,
#: 走 `limit_touched_up` / `limit_touched_down` 两个布尔列,不进 `status`。
TRADABILITY_STATUSES: tuple[str, ...] = (
    "trade",
    "suspend",
    "limit_up",
    "limit_down",
    "no_data",
)

#: `tradability.suspend_basis` 的取值全集 —— "凭什么说它停牌"。
#:
#: * ``suspend_d_S``     —— 当天 `suspend_d` 有 `suspend_type='S'` 的行(直接证据)。
#: * ``carried_after_S`` —— 当天没有 S 行,但前面某个交易日有 S、此后一直没有
#:   行情行也没有 R;停牌状态**顺延**到今天(推断证据)。
#: * ``none``            —— 没有任何停牌证据。`status` 只可能是 `no_data` 或有行情的三档。
TRADABILITY_SUSPEND_BASES: tuple[str, ...] = (
    "suspend_d_S",
    "carried_after_S",
    "none",
)

#: `tradability.domain_*` 四个布尔列对应的四条**行域**证据通道。
#: 行域 = 四者的**并集**(见 `snapshots/tradability.py` 的"行域"一节)。
TRADABILITY_DOMAIN_SOURCES: tuple[str, ...] = (
    "listing_window",
    "daily",
    "stk_limit",
    "suspend_d",
)

#: 验收 (b):随机抽样的总条数。
TRADABILITY_SAMPLE_N: int = 50

#: 验收 (b):其中做"完整判定链路取证"的条数(写进 `TRADABILITY_SAMPLE_REPORT`)。
TRADABILITY_SAMPLE_DETAIL_N: int = 10

#: 抽样随机种子。**抽样必须可复现** —— 换个种子就换一批样本,
#: 那样"人工复核过了"这句话就失去意义。
TRADABILITY_SAMPLE_SEED: int = 20260731

#: 触板比价的浮点容差。价格与涨跌停价都是两位小数,
#: 但 float64 表示 2 位小数本身就不精确,裸 ``==`` 是在赌位模式对齐。
#:
#: 实测(2015-06 / 2021-06 / 2026-07 三个月,共 26.9 万行):
#: ``==``、``<1e-6``、``<5e-3``、``round(2) ==`` 四种判据给出**逐行相同**的结果,
#: 一条都不差。所以这个容差在**当前湖数据上**不改变任何结论 ——
#: 它是防线不是修正,防的是将来换数据源/换精度时的静默漂移。
LIMIT_PRICE_TOL: float = 1e-6

#: `stk_limit` 里"**无涨跌幅限制**"哨兵的 **up 侧**判据下界。
#:
#: ⚠️ **这个值不是 100000.0。** 卡 1.2 第一版写的是 `100000.0`,少了一分钱,
#: 于是漏掉整整一族编码 —— 见下面 `NO_PRICE_LIMIT_LEGS` 的实测表。
#: 取 `9.9e4` 而不是 `1e5`,是为了把 `99999.999` / `99999.99` 一并罩住;
#: 实测冻结线内**非哨兵**行的 `up_limit` 最大值是 **3,240.0**(`688808.SH @ 2026-06-26`),
#: 离 99,000 还有 **30 倍**余量,不存在把真实价格误吞进来的风险。
NO_PRICE_LIMIT_UP_MIN: float = 9.9e4

#: 哨兵的 **down 侧**判据上界。
#:
#: A 股最小报价单位是 0.01 元,一只票要让 `down_limit` 真的等于 0.01,
#: 前收得在 0.011 元附近。实测冻结线内**非哨兵**行的 `down_limit` 最小值是 **0.07**,
#: 所以 `down_limit <= 0.01` 本身就已经是"这不是真实价格带"的充分证据。
NO_PRICE_LIMIT_DOWN_MAX: float = 0.01

#: 哨兵的 **band 侧**判据下界 —— 隐含涨跌幅带宽 ``(up - down) / (up + down)``。
#:
#: 前两条腿都咬死在**具体数值**上,只能罩住"已经见过"的编码。这一条不同:
#: 它是**尺度无关**的,不认识任何具体哨兵值,只问"这一对价格隐含的涨跌幅带
#: 像不像一个真实的涨跌停区间"。真实的 ±5% / ±10% / ±20% / ±30% / ±44% 档
#: 分别给出 band ≈ 0.05 / 0.10 / 0.20 / 0.30 / 0.44;而哨兵一律给出 **1.0**
#: (`down` 相对 `up` 小到可以忽略)。实测冻结线内 14,892,432 行:
#:
#: - 非哨兵行 band ∈ **[0.0097, 0.4408]**,最大值是 `601975.SH @ 2019-01-08`
#:   (6.21 / 2.41,新股首日 ±44% 档);
#: - 哨兵行 band **恒等于 1.0**(28 行 `0.0/0.0` 的 band 是 0/0 = NaN,单独由
#:   ``up + down <= 0`` 罩住)。
#:
#: 0.44 与 1.0 之间是一条**空的**鸿沟,阈值取 0.5 / 0.6 / 0.7 / 0.9 选出的行数
#: 完全一样(都是 7,107)。取 0.5 是因为它紧贴真实上界之上、离 1.0 又有一半余量。
#: **这条腿是"未来出现新哨兵编码"的兜底**:哪怕湖里明天冒出个
#: ``up=88888.88 / down=0.02`` 这种谁也没见过的编码,band ≈ 0.9999995 照样罩得住。
NO_PRICE_LIMIT_BAND_MAX: float = 0.5

#: `stk_limit` 里"**无涨跌幅限制**"的哨兵判据 —— **三条腿取并集(OR)**::
#:
#:     no_price_limit = (up_limit >= NO_PRICE_LIMIT_UP_MIN or up_limit <= 0)
#:                      or (down_limit <= NO_PRICE_LIMIT_DOWN_MAX)
#:                      or (band >= NO_PRICE_LIMIT_BAND_MAX or up_limit + down_limit <= 0)
#:
#: **实测(≤ `FREEZE_DATE` 的 14,892,432 行 `stk_limit`,up/down 两列均无 NULL)**,
#: `down_limit <= 0.01` 的行共 **7,107** 行,`(up_limit, down_limit)` 只有六种取值:
#:
#: ==================  ==============  ======  ======
#: up_limit            down_limit      行数    band
#: ==================  ==============  ======  ======
#: 100000.0            0.01             2,754     1.0
#: 1000000.0           0.01             2,332     1.0
#: 999999.999          0.01               975     1.0
#: 99999.999           0.01               751     1.0
#: 99999.99            0.0                267     1.0
#: 0.0                 0.0                 28     NaN
#: ==================  ==============  ======  ======
#:
#: (不加冻结线是 7,163 行 —— 多出来的 56 行全在 2026-08,只是被红线 7 挡在窗口外。)
#:
#: 旧判据 `up_limit >= 100000.0` 只抓到前三种(**6,061** 行),**漏掉后三种 1,046 行**,
#: 而且漏的那族在增长(2021:22 / 2022:83 / 2023:320 / 2024:190 / 2025:241 / 2026:162,
#: 另有 28 行 `0.0/0.0` 散在 2009-2015)。后果是那 1,046 行被断言"有涨跌停价、可判、
#: 且没触板",并把 `99999.999` 当**真实涨停价**发出去 —— 例:`688425.SH @ 2021-06-22`
#: (科创板上市首日,low 5.19 / high 12.15 / close 8.22,日内振幅 >130%,本就没有涨跌停),
#: 下游算 `up_limit/close` 会拿到 **12,165 倍**。
#:
#: **为什么三条腿是 OR 不是 AND。** 实测三条腿在当前湖上选出**完全相同**的 7,107 行
#: (`down_limit <= 0.01` 而 `up_limit` 正常的行 **0 行**;反向也是 **0 行**)。
#: 既然各自都已充分,OR 就是 fail-safe 的方向 —— 宁可多标一行"没法判",
#: 也不要把荒谬价格当真实涨停价发出去。
#: `ops/test_tradability.py::test_sentinel_legs_agree_on_the_lake` 断言三条腿逐行同集:
#: **湖里一旦出现只满足其中一部分腿的行,那条测试会变红** ——
#: 这就是"遇到没见过的编码时报警而不是静默判 False"的落点。
#:
#: 命名上刻意**不**保留旧的 `NO_PRICE_LIMIT_MIN` 别名:留着它,任何漏改的引用都会
#: 拿到一个语义已经变了的常量而不报错;删掉它,漏改的地方直接 `AttributeError`。
NO_PRICE_LIMIT_LEGS: tuple[str, str, str] = (
    f"up_limit >= {NO_PRICE_LIMIT_UP_MIN:g} or up_limit <= 0",
    f"down_limit <= {NO_PRICE_LIMIT_DOWN_MAX:g}",
    f"(up_limit - down_limit) / (up_limit + down_limit) >= {NO_PRICE_LIMIT_BAND_MAX:g}"
    f" or up_limit + down_limit <= 0",
)

# --------------------------------------------------------------------------
# 数据湖(只读)
# --------------------------------------------------------------------------

#: 数据湖根。**只读**,不许写入任何字节(红线 2)。
LAKE: Path = Path("/home/ljn/projects/data/market_lake")
#: duckdb catalog,150 个只读 view。必须 ``duckdb.connect(str(CATALOG), read_only=True)``。
CATALOG: Path = LAKE / "catalog" / "market.duckdb"
#: gold 层 parquet。全表扫会 "Too many open files",先 ``ulimit -n 8192``
#: 或直接 ``read_parquet('<GOLD>/<ds>/<partition>/*.parquet')`` 读定向分区。
GOLD: Path = LAKE / "gold"
#: qlib 数据发布目录(instruments 代码是 `SH600000` 前缀式,需转成湖里的 `600000.SH`)
QLIB_RELEASE: Path = Path("/home/ljn/projects/data/qlib/releases/2026-08-26")
#: 基础 python 解释器。**只读使用**,禁止 pip install 进去(红线 2)。
PYTHON_BASE: Path = Path("/home/ljn/tools/miniconda3/envs/qlib_env/bin/python")

#: 数据冻结线(红线 7)。v1 的一切查询、快照、任务上界不得超过它。
FREEZE_DATE: str = "2026-07-31"

# --------------------------------------------------------------------------
# 目录权限(红线 5)
# --------------------------------------------------------------------------

#: `$GENEBENCH_ROOT` 下**每一个**目录必须的权限。
#: `/data/shared` 是 1777 的公共目录,答案产物(`reference/`、`scorer/`)
#: 的唯一一道门就是权限位 —— 不是路径隔离(路径隔离要等 T-01)。
REQUIRED_DIR_MODE: int = 0o700

#: 目录权限里**一位都不许亮**的比特:组 + 其它的 rwx。
#: 审计用 `mode & FORBIDDEN_MODE_BITS == 0` 而不是 `mode == 0o700`,
#: 这样 0o500 之类更严的模式也算合规。答案目录另有 `== 0o700` 的硬断言。
FORBIDDEN_MODE_BITS: int = 0o077

#: 本项目进程该用的 umask。**本机默认 umask 是 002**(实测:`conda create`
#: 和 pytest 建出来的目录都是 0775),裸 `mkdir` 会静默产出组/世界可读目录。
REQUIRED_UMASK: int = 0o077


def harden_umask() -> int:
    """把当前进程的 umask 收紧到 `REQUIRED_UMASK`,返回旧值。

    在每个入口(网关启动、runner、scorer、pytest 的 conftest)调**一次**。
    只影响本进程及其子进程,不写任何配置文件 —— 红线 2 不许碰用户既有配置。

    Returns:
        调用前的 umask,便于需要时还原。
    """
    return os.umask(REQUIRED_UMASK)


def create_dir(
    path: "str | os.PathLike[str]",
    *,
    mode: int = REQUIRED_DIR_MODE,
    exist_ok: bool = True,
) -> Path:
    """建目录,并保证**每一个新建层级**都是 `mode`(默认 0700)。

    后续所有卡建目录一律走这里,不要裸 `mkdir` / `os.makedirs`。

    为什么不能只写 `os.makedirs(p, mode=0o700)`:

    1. **Python 3.7 起 `mode` 只作用于最后一级**,中间层拿的是
       ``0o777 & ~umask`` —— 本机 umask 是 002,中间层会落成 **0775**。
    2. `mkdir(2)` 的 mode 本身还要再被 umask 削一道。

    所以这里先收集"本次会新建哪些层级",建完再对每一级显式 `os.chmod`。
    对已存在的目录也会 chmod(幂等收敛),这样历史上被裸 mkdir 建歪的目录
    一旦被再次 `create_dir` 就会自动收紧。

    Args:
        path: 目标目录。
        mode: 目录权限,默认 `REQUIRED_DIR_MODE`。
        exist_ok: 目标已存在时是否放行。

    Returns:
        目标目录的 `Path`。

    Raises:
        ValueError: `mode` 亮了 `FORBIDDEN_MODE_BITS` 里的位(红线 5)。
        NotADirectoryError: 目标已存在但不是目录。
        FileExistsError: 目标已存在且 ``exist_ok=False``。
    """
    if mode & FORBIDDEN_MODE_BITS:
        raise ValueError(
            f"红线 5 违规:目录 mode={oct(mode)} 对组/其它开放;"
            f" 允许的位掩码是 ~{oct(FORBIDDEN_MODE_BITS)}"
        )
    target = Path(path)
    if target.exists() and not target.is_dir():
        raise NotADirectoryError(f"{target} 已存在但不是目录")

    # 自底向上收集"现在还不存在、因而本次会被新建"的层级。
    missing: list[Path] = []
    probe = target
    while not probe.exists():
        missing.append(probe)
        if probe.parent == probe:  # 到了文件系统根
            break
        probe = probe.parent

    os.makedirs(target, mode=mode, exist_ok=exist_ok)

    # 最后一级 + 每个新建的中间层,逐个显式 chmod(绕开 umask 与 3.7+ 的语义)。
    for created in [target, *missing]:
        os.chmod(created, mode)
    return target


# --------------------------------------------------------------------------
# 网关(执行面数据唯一入口)
# --------------------------------------------------------------------------

#: 网关绑定地址。**硬编码内网 IP,禁止 0.0.0.0**(红线 4)。
GATEWAY_HOST: str = "192.168.1.48"
#: 网关端口(实测空闲)。
GATEWAY_PORT: int = 18080
#: 客户端拼 URL 用这个,别自己拼。
GATEWAY_BASE_URL: str = f"http://{GATEWAY_HOST}:{GATEWAY_PORT}"

#: 被禁止的通配绑定地址。空串 = 某些库里的 "所有接口"。
WILDCARD_BIND_HOSTS: frozenset[str] = frozenset(
    {"0.0.0.0", "", "::", "*", "[::]", "::0", "0", "0.0.0.0.0.0"}
)


def assert_no_wildcard_bind(host: str) -> str:
    """红线 4 的代码级防线:拒绝任何通配 / 全接口绑定。

    在**每一处**启动监听之前调用它(uvicorn、http.server、socket.bind 等)。

    Args:
        host: 打算绑定的地址。

    Returns:
        原样返回 ``host``(去掉首尾空白),方便直接内联::

            uvicorn.run(app, host=cfg.assert_no_wildcard_bind(cfg.GATEWAY_HOST), ...)

    Raises:
        ValueError: ``host`` 是通配地址,或不是字符串。
    """
    if not isinstance(host, str):
        raise ValueError(
            f"红线 4:bind host 必须是字符串,拿到 {type(host).__name__}={host!r}"
        )
    normalized = host.strip().strip("[]").lower()
    if normalized in WILDCARD_BIND_HOSTS or host.strip() in WILDCARD_BIND_HOSTS:
        raise ValueError(
            f"红线 4 违规:拒绝绑定通配地址 {host!r}。"
            f"finance01 在 tailscale 上,tailscale 流量绕过 ufw,"
            f"监听 0.0.0.0 等于把执行面网关对整个 tailnet 敞开。"
            f"请绑定 GATEWAY_HOST={GATEWAY_HOST!r}。"
        )
    return host.strip()


# --------------------------------------------------------------------------
# 数据通道(卡 1.1-a:公开通道的数据面)
# --------------------------------------------------------------------------
#
# 两条通道**并列、不覆盖**:
#
# * ``private`` —— 审计湖 + ChinaScope 建出来的 `snapshots/v1/`(既有,默认)。
# * ``public``  —— 可再分发的公开源(baostock)建出来的 `snapshots/public_v1/`。
#
# **默认恒为 private,且行为与加这一节之前逐字节一致** —— 环境变量不设时,
# 下面每个函数返回的都是本文件上半部分那些既有常量本身。
# 这一节只**加**名字,一个既有常量都没改。

#: 通道全集。**白名单**:不认识的名字当场抛,不静默退回默认
#: (静默退回的表现是「以为在跑公开通道,其实读的是私有表」)。
CHANNELS: tuple[str, ...] = ("private", "public")

#: 选通道的环境变量名。配置驱动,不改代码。
CHANNEL_ENV: str = "GENEBENCH_CHANNEL"

#: 不设环境变量时的通道。
DEFAULT_CHANNEL: str = "private"

#: 公开通道的快照版本目录名。与私有的 `v1` **同级不同名**,不覆盖。
PUBLIC_VERSION: str = "public_v1"

#: 公开通道的快照根。布局与 `SNAPSHOTS_V1` 同名同形。
SNAPSHOTS_PUBLIC: Path = SNAPSHOTS / PUBLIC_VERSION

#: 公开通道的网关后端表(与 `SNAPSHOTS_V1 / "tables"` 对应)。
PUBLIC_TABLES_DIR: Path = SNAPSHOTS_PUBLIC / "tables"

#: 公开通道的 `tradability` 年分区(与 `TRADABILITY_DIR` 对应)。
PUBLIC_TRADABILITY_DIR: Path = SNAPSHOTS_PUBLIC / "tradability"

#: 公开通道的冻结 qlib provider(与 `SNAPSHOTS_V1 / "qlib_provider"` 对应)。
PUBLIC_PROVIDER_DIR: Path = SNAPSHOTS_PUBLIC / "qlib_provider"

#: 公开通道的**中间产物**(归一化后的原始行情等)。不是交付面,不进公开包。
PUBLIC_BUILD_DIR: Path = SNAPSHOTS_PUBLIC / "build"

#: 公开通道构建的**断点标记**目录(`ops/build_public_channel.py` 的 `.done`)。
PUBLIC_STATE_DIR: Path = SNAPSHOTS_PUBLIC / "state"

#: 网关端口的环境变量名。生产网关(systemd,private,18080)不读它 —— 那边不设。
GATEWAY_PORT_ENV: str = "GENEBENCH_GATEWAY_PORT"

#: 公开通道实例的默认端口。**刻意与 `GATEWAY_PORT` 不同**:
#: 「忘了设端口」的失败形态必须是「起在 18081」,不能是「抢生产网关的 18080」。
GATEWAY_PUBLIC_PORT: int = 18081

#: 每条通道自己的 access_log 文件名。两条通道**各写各的** ——
#: 混在一份里,卡 5.1 的越权率就分不清是哪条通道产生的。
GATEWAY_ACCESS_LOG_NAME: dict[str, str] = {
    "private": "gateway_access.jsonl",
    "public": "gateway_access_public.jsonl",
}


def assert_channel(name: "str | None" = None) -> str:
    """通道名白名单。不认识就抛。

    Args:
        name: 通道名;`None` 表示取环境变量(见 `channel()`)。

    Returns:
        规范化后的通道名。

    Raises:
        ValueError: 不在 `CHANNELS` 里。
    """
    value = (name if name is not None else os.environ.get(CHANNEL_ENV, "")).strip().lower()
    if not value:
        return DEFAULT_CHANNEL
    if value not in CHANNELS:
        raise ValueError(
            f"{CHANNEL_ENV}={value!r} 不认识;只接受 {CHANNELS}。"
            f"不静默退回 {DEFAULT_CHANNEL!r} —— 静默退回的表现是"
            f"「以为在跑公开通道,其实读的是私有表」。"
        )
    return value


def channel() -> str:
    """当前生效的通道。配置驱动,默认 `private`。"""
    return assert_channel(None)


def snapshot_tables_dir(ch: "str | None" = None) -> Path:
    """该通道的网关后端表目录。private 返回的就是既有的那个路径。"""
    return PUBLIC_TABLES_DIR if assert_channel(ch) == "public" else SNAPSHOTS_V1 / "tables"


def tradability_dir(ch: "str | None" = None) -> Path:
    """该通道的 `tradability` 产物根。"""
    return PUBLIC_TRADABILITY_DIR if assert_channel(ch) == "public" else TRADABILITY_DIR


def provider_dir(ch: "str | None" = None) -> Path:
    """该通道的冻结 qlib provider 根。"""
    return PUBLIC_PROVIDER_DIR if assert_channel(ch) == "public" else SNAPSHOTS_V1 / "qlib_provider"


def gateway_access_log(ch: "str | None" = None) -> Path:
    """该通道的 access_log 落点。"""
    return LOGS / GATEWAY_ACCESS_LOG_NAME[assert_channel(ch)]


def gateway_port(ch: "str | None" = None) -> int:
    """该通道的网关端口。

    优先级:环境变量 `GENEBENCH_GATEWAY_PORT` > 通道默认值
    (private `GATEWAY_PORT`=18080 / public `GATEWAY_PUBLIC_PORT`=18081)。

    Raises:
        ValueError: 环境变量不是 1..65535 的整数。
    """
    raw = os.environ.get(GATEWAY_PORT_ENV, "").strip()
    if raw:
        try:
            port = int(raw)
        except ValueError as exc:
            raise ValueError(f"{GATEWAY_PORT_ENV}={raw!r} 不是整数") from exc
        if not 1 <= port <= 65535:
            raise ValueError(f"{GATEWAY_PORT_ENV}={port} 不在 1..65535")
        return port
    return GATEWAY_PUBLIC_PORT if assert_channel(ch) == "public" else GATEWAY_PORT


# --------------------------------------------------------------------------
# 重建链的落点(卡 1.1-b)
# --------------------------------------------------------------------------
#
# gold → 互检 → τ → ε → calibration.json 这条链原来把落点写死在 `SNAPSHOTS_V1` 上。
# 公开通道要用**同一条链**长出第二份产物,做法与卡 1.1-a 的 provider 一样:
# 把「快照根」抽成一个函数,**不复制一份新链** —— 复制的表现是两条通道的
# τ/ε 口径慢慢漂开,而两边都照常算得出数。
#
# **private 分支返回的就是既有常量本身**:不设 `GENEBENCH_CHANNEL` 时,
# 下面每个函数的返回值与本节引入之前逐字相同
# (`ops/test_public_chain.py::test_private_paths_are_the_existing_constants` 钉住)。


def snapshot_root(ch: "str | None" = None) -> Path:
    """该通道的快照根。private = `SNAPSHOTS_V1`,public = `SNAPSHOTS_PUBLIC`。"""
    return SNAPSHOTS_PUBLIC if assert_channel(ch) == "public" else SNAPSHOTS_V1


def gold_dir(ch: "str | None" = None) -> Path:
    """该通道的 gold 因子根(卡 2.1b 的 `write_gold` 落点)。"""
    return snapshot_root(ch) / "gold_factors"


def crosscheck_dir(ch: "str | None" = None) -> Path:
    """该通道的 2.1b 互检格(`rank_ic_cells_<universe>.parquet`)。"""
    return snapshot_root(ch) / "crosscheck"


def crosscheck_report(ch: "str | None" = None) -> Path:
    """该通道的 2.1b 互检报告。

    private **仍是仓库里那份** `ops/acceptance/card_2.1b_crosscheck.json`
    (它是签字面,进 git);public 落到公开快照根下 —— 公开通道的产物是大产物,
    按红线 6 不进 git。
    """
    if assert_channel(ch) == "public":
        return crosscheck_dir(ch) / "card_2.1b_crosscheck.json"
    return OPS / "acceptance" / "card_2.1b_crosscheck.json"


def epsilon_dir(ch: "str | None" = None) -> Path:
    """该通道的 ε 标定目录(面板 / 三份实现 / `epsilon_dual_<freq>.json`)。"""
    return snapshot_root(ch) / "epsilon"


def calibration_path(ch: "str | None" = None) -> Path:
    """该通道的 `calibration.json` —— 评分参数的单一事实来源。"""
    return snapshot_root(ch) / "calibration.json"


def universe_dir(ch: "str | None" = None) -> Path:
    """该通道的宇宙定义面。

    **公开通道的宇宙轴沿用 v1**(卡 2.5 §1 第 4 项裁定 / N-68):
    「谁在指数里」是定义不是行情,公开通道复用同一份 `universe_pit.parquet`,
    与卡 1.1-a 的 `PUBLIC_PATHS.universe_pit` 同一条裁定。
    这里给出的是**公开快照根下的那份副本**(内容逐字节相同,附 sha256),
    好让公开包自足 —— 外部用户手里没有 `snapshots/v1/`。
    """
    return snapshot_root(ch) / "universe"


def universe_pit_parquet(ch: "str | None" = None) -> Path:
    """该通道的 PIT 成分表。"""
    return universe_dir(ch) / "universe_pit.parquet"


if __name__ == "__main__":  # pragma: no cover - 手工自检用
    for _name in __all__:
        _value = globals()[_name]
        if callable(_value):
            continue
        print(f"{_name:20s} = {_value!r}")
