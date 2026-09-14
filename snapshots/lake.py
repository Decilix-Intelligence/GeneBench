"""snapshots.lake —— 数据湖 `market_lake` 的**只读**访问层。

全仓库访问数据湖的**唯一**入口。任何模块要碰湖,一律
``from snapshots import lake``,不要自己 ``duckdb.connect``。

为什么必须封装
--------------
1. **湖是别人的生产资产**(红线 2:不许写入任何字节)。连接必须以只读模式打开,
   这件事不能靠"每个调用点自觉",要靠一个被单测盯着的模块。
   `ops/test_lake_baseline.py` 会对本文件做**源码级**审计(AST + 字面量扫描):
   凡是本文件里出现写路径(文件写 API、写语义 SQL、非只读的连接调用),测试就红。
2. **湖是活的**。外部 ETL 周期性读写 catalog 并留下瞬时 `.wal`,只读打开会偶发
   失败 —— 所以 `open_catalog()` 自带重试(卡 0.1 已踩过同一个坑)。
3. **默认 `ulimit -n` 只有 1024**(实测 finance01:soft 1024 / hard 1048576)。
   `catalog/market.duckdb` 里的视图是 ``read_parquet('<gold>/<ds>/**/*.parquet')``,
   直接 ``SELECT * FROM daily`` 要开 4289 个分区文件 → "Too many open files"。
   本模块进程入口调 `raise_open_file_limit()`(无需 sudo,只抬 soft),
   并且提供 `read_gold()` 让调用方读**定向分区**而不是全表。

新鲜度怎么判(卡 0.2 的核心结论)
--------------------------------
判断一个数据集"数据到哪天了",**看 `gold_partitions(dataset)` 的最新时间分区**,
不要看 `crawler_state.sqlite3` 的 watermarks —— 那是**补数游标**不是新鲜度:
补数任务从新往旧走会把 watermark 一路拖回一年前,而 gold 分区一天都不会少。
`gold_partitions()` 走 `os.scandir`,4289 个分区 2.5ms,可以随便调。

但"最新分区 = 新鲜度"只对**数据时间**分区成立。分区值其实有三种语义
(`partition_semantics()`):`data_time`(`trade_date=` …)、`capture_time`
(`snapshot_date=`,是我们哪天抄的表)、`entity_code`(`ts_code=` / `l3_code=`)。
`stock_basic` / `trade_cal` / `index_basic` 是 `capture_time`:快照**全部**在
冻结线之后(2026-08-05 起),但 `trade_cal` 的数据覆盖 20090101→20261231 ——
拿它的分区去截冻结线会得出"冻结线内没数据"的错误结论。

分区间 schema 漂移(实测,会**静默**咬人)
------------------------------------------
catalog 视图用 ``union_by_name = true`` 把**全部**分区的列取并集,所以
"视图的列" ≠ "任意一个分区的列"。实测两种漂移,都出现在 v1 依赖表上:

1. **列数漂移**。`daily` 视图 14 列,但 `trade_date=2026-08-06` **之前**的每个
   分区只有 13 列(第 14 列 `last_seen_at` 是 8 月 6 日后 ETL 才加的)。
   v1 冻结窗口(≤ 2026-07-31)里 `daily` 只有 13 列。
   三大报表更碎:`income` 的 `ts_code=000001.SZ` 有 89 列而多数分区 88 列 ——
   **同一张表里逐分区不同**,不是按时间整齐切分的。
2. **列类型漂移**。`income` 关掉 union 读 ``ts_code=00000*`` 会抛
   ``ConversionException: failed to cast column "oper_cost"``。

关掉 ``union_by_name`` 的后果**不是报错而是静默丢列**:duckdb 按第一个文件的
schema 绑定,后面文件多出来的列直接不要了 —— 实测 `daily` 跨漂移点读
``trade_date=2026-08-0*``,``union_by_name=False`` 安静地返回 13 列(丢了
`last_seen_at`),``True`` 返回 14 列。运气差一点(类型对不上)才会抛异常。
所以 `read_gold()` **默认 ``union_by_name=True``**,与视图口径一致;
除非你确知只读一个分区,否则不要关。

用法
----
::

    from snapshots import lake

    lake.raise_open_file_limit()          # 进程入口调一次

    with lake.catalog() as con:           # 上下文管理器:连接必被关闭
        cols = lake.describe_view("daily", conn=con)
        n = lake.count_rows("stock_basic", conn=con)

    parts = lake.gold_partitions("daily")            # ['trade_date=2009-01-05', ...]
    lake.latest_gold_partition("daily")              # 'trade_date=2026-08-28'
    df = lake.read_gold("daily", "trade_date=2026-07-*")   # 只开 7 月那 23 个分区
"""

from __future__ import annotations

import os
import re
import resource
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import duckdb

try:  # 允许 `python snapshots/lake.py` 这种不带包上下文的跑法
    import genebench_config as cfg
except ModuleNotFoundError:  # pragma: no cover - 仅在裸脚本模式下走到
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import genebench_config as cfg

__all__ = [
    "DEFAULT_THREADS",
    "DEFAULT_RETRIES",
    "DEFAULT_RETRY_WAIT",
    "OPEN_FILE_TARGET",
    "FREEZE_DATE_COMPACT",
    "TIME_PARTITION_KEYS",
    "CAPTURE_PARTITION_KEYS",
    "PARTITION_SEMANTICS",
    "LakeError",
    "raise_open_file_limit",
    "open_catalog",
    "catalog",
    "query",
    "list_views",
    "view_exists",
    "describe_view",
    "count_rows",
    "column_range",
    "gold_dir",
    "gold_datasets",
    "gold_partitions",
    "gold_partition_key",
    "split_partition",
    "partition_values",
    "partition_semantics",
    "latest_gold_partition",
    "partitions_upto",
    "gold_latest_value",
    "gold_latest_capture",
    "read_gold",
]

# --------------------------------------------------------------------------
# 常量
# --------------------------------------------------------------------------

#: duckdb 线程数。湖是共享生产资产,不许把 12 核吃满 —— 连接一打开就 `SET`。
DEFAULT_THREADS: int = 2

#: 只读打开失败时的重试次数。湖是活的,外部 ETL 会留下瞬时 `.wal`。
DEFAULT_RETRIES: int = 5

#: 重试间隔基数(秒),实际等待按次数线性退避。
DEFAULT_RETRY_WAIT: float = 1.0

#: 期望的进程 fd 上限。finance01 默认 soft=1024,hard=1048576 —— 抬 soft 不需要特权。
OPEN_FILE_TARGET: int = 8192

#: 冻结线的紧凑写法(`20260731`)。湖里日期字段是 `YYYYMMDD`,
#: 而 gold 分区目录是 `YYYY-MM-DD`,两种形态都要用,统一在这里派生,不要各写各的。
FREEZE_DATE_COMPACT: str = "".join(cfg.FREEZE_DATE.split("-"))

#: **数据时间**分区键 —— 分区值 = 这批数据说的是哪一天。
#: 只有这类分区的"最新分区"才等于"数据到哪天了",也只有它能用来截冻结线。
TIME_PARTITION_KEYS: frozenset[str] = frozenset(
    {
        "trade_date",
        "cal_date",
        "end_date",
        "ann_date",
        "trade_month",
        "published_month",
        "month",
        "year",
    }
)

#: **抓取时间**分区键 —— 分区值 = 我们哪天把这张表抄下来的,与数据本身的时间无关。
#: 这是个真会咬人的区别:`stock_basic` / `trade_cal` / `index_basic` 全部
#: `snapshot_date` 分区且**最早的快照都在冻结线之后**(2026-08-05 起),
#: 但 `trade_cal` 的数据本身覆盖 20090101→20261231。把 snapshot_date 当数据时间去截
#: 冻结线,会得出"这些表在冻结线内没有数据"的错误结论 —— 它们的 PIT 语义要靠
#: 表内字段(`list_date`/`delist_date`/`cal_date`)回溯,不是靠选快照。
CAPTURE_PARTITION_KEYS: frozenset[str] = frozenset({"snapshot_date"})

#: `partition_semantics()` 的取值。
PARTITION_SEMANTICS: tuple[str, ...] = (
    "data_time",  # 分区值 = 数据日期,可截冻结线
    "capture_time",  # 分区值 = 抓取日期,**不能**当数据日期
    "entity_code",  # 分区值 = ts_code / l3_code 之类的实体码
    "none",  # 没有分区目录
)

#: 数据集名必须是纯标识符 —— 它会被拼进路径和 SQL 标识符,不能放任。
_DATASET_RE = re.compile(r"\A[a-z][a-z0-9_]*\Z")

#: 列名同上。
_IDENT_RE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")

#: 分区 glob 允许的字符集(含通配符)。`..` 另行单独拦截。
_PARTITION_GLOB_RE = re.compile(r"\A[A-Za-z0-9_=.*?/\-\[\]{},]+\Z")

#: `query()` 只放行这些语句头。用**白名单**而不是黑名单:
#: 白名单里天然不含任何写语义的动词,不需要在本文件里出现那些词。
#:
#: ⚠️ 这里**刻意没有** ``set``(卡 0.2 补救 D4 剔除)。理由:
#: ``SET`` 不写数据库、也不写文件系统,所以只读连接和"写路径"审计都拦不住它,
#: 但它能改**连接级会话状态** —— 实测 ``query("SET threads=12")`` 把线程数从
#: `DEFAULT_THREADS`(2)抬到 12,直接推翻本模块自述的"湖是共享生产资产,
#: 不许把 12 核吃满"。白名单的职责不只是"挡住写",是"挡住一切能改变
#: 本模块承诺的语义的语句"。
#: 剔掉它**没有副作用**:模块内部设线程走 `conn.execute`(见 `open_catalog`),
#: 根本不经过 `query()`;调用方要调线程,应该走 `open_catalog(threads=...)`
#: 这个**被签名约束、被单测盯着**的入口,而不是自己拼一条 SQL 绕过去。
_ALLOWED_STATEMENT_HEADS: frozenset[str] = frozenset(
    {
        "select",
        "with",
        "from",
        "describe",
        "summarize",
        "show",
        "explain",
        "values",
        "pivot",
        "unpivot",
    }
)


class LakeError(RuntimeError):
    """数据湖访问层的错误基类(参数非法 / 连不上 / 越界)。"""


# --------------------------------------------------------------------------
# 进程级:fd 上限
# --------------------------------------------------------------------------


def raise_open_file_limit(target: int = OPEN_FILE_TARGET) -> tuple[int, int]:
    """把本进程的 `RLIMIT_NOFILE` soft 上限抬到 `target`(不超过 hard)。

    等价于 shell 里的 ``ulimit -n 8192``,但不依赖调用方记得敲。
    只抬 soft、不动 hard,**不需要任何特权**(红线 1)。

    Args:
        target: 期望的 soft 上限。

    Returns:
        ``(旧 soft, 新 soft)``。已经够大时两者相等。
    """
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    want = min(target, hard)
    if soft >= want:
        return soft, soft
    resource.setrlimit(resource.RLIMIT_NOFILE, (want, hard))
    return soft, want


# --------------------------------------------------------------------------
# 连接
# --------------------------------------------------------------------------


def open_catalog(
    *,
    threads: int = DEFAULT_THREADS,
    retries: int = DEFAULT_RETRIES,
    retry_wait: float = DEFAULT_RETRY_WAIT,
) -> duckdb.DuckDBPyConnection:
    """打开 `cfg.CATALOG` 的**只读**连接,并把线程数收到 `threads`。

    调用方负责关闭。**推荐直接用 `catalog()` 上下文管理器**,
    它保证连接一定被关掉(异常路径也是)。

    连接以只读模式打开:duckdb 引擎会把一切写语义顶回去(卡 0.1 实测
    `CREATE`/`INSERT` 分别抛 InvalidInputException / CatalogException),
    这是"不写湖"这条红线的**引擎级**防线,源码级防线见本模块的单测。

    Args:
        threads: duckdb 线程数,默认 `DEFAULT_THREADS`。
        retries: 打开失败的重试次数。湖是活的,外部 ETL 的瞬时 `.wal`
            会让只读打开偶发失败 —— 重试即可,不是故障。
        retry_wait: 重试间隔基数(秒),第 i 次等 ``retry_wait * i``。

    Returns:
        已经 ``SET threads`` 的只读连接。

    Raises:
        LakeError: 参数非法,或重试用尽仍打不开。
    """
    if threads < 1:
        raise LakeError(f"threads 必须 >= 1,拿到 {threads}")
    if retries < 1:
        raise LakeError(f"retries 必须 >= 1,拿到 {retries}")

    path = str(cfg.CATALOG)
    last: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            conn = duckdb.connect(path, read_only=True)
        except Exception as exc:  # noqa: BLE001 - duckdb 抛的类型很杂
            last = exc
            if attempt < retries:
                time.sleep(retry_wait * attempt)
            continue
        conn.execute(f"SET threads={int(threads)}")
        return conn
    raise LakeError(
        f"打不开 catalog(只读,重试 {retries} 次):{path}\n"
        f"最后一次错误:{type(last).__name__}: {last}"
    ) from last


@contextmanager
def catalog(
    *,
    threads: int = DEFAULT_THREADS,
    retries: int = DEFAULT_RETRIES,
    retry_wait: float = DEFAULT_RETRY_WAIT,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """`open_catalog()` 的上下文管理器版 —— **连接必被关闭**。

    这是访问 catalog 的推荐姿势::

        with lake.catalog() as con:
            con.execute("SELECT 1").fetchall()

    Yields:
        只读连接。退出时无论正常还是异常都会 ``close()``。
    """
    conn = open_catalog(threads=threads, retries=retries, retry_wait=retry_wait)
    try:
        yield conn
    finally:
        conn.close()


#: 只读 parquet 的语句 —— 它们**不需要 catalog**。
#: `read_parquet('/abs/path')` 直接读文件，与湖里的 149 个 view 无关。
_PARQUET_ONLY = re.compile(r"read_parquet\s*\(", re.I)


def needs_catalog(sql: str) -> bool:
    """这条语句要不要 catalog。**纯函数** —— 本模块不为它开任何连接。

    **N-42 的根治**（裁定 2026-09-04）：benchmark 期 backend 钉死 snapshot，
    而 snapshot 读的是 parquet 文件 —— 却仍走 `catalog()` 开了一次
    `market.duckdb`，于是每个请求都与 19 个爬虫争一次只读锁。
    症状是全量套件里随机一两条测试红、单跑即过（本轮撞三次，各是不同的测试）。

    判据**保守**：只有确定不需要时才返回 False。判错方向的代价不对称 ——
    少开一次 = 查询失败并报错（响的）；多开一次 = 回到今天的争用（哑的）。
    第一版只查 `FROM`，**漏了 JOIN**（自测当场红）。

    **不在这里开内存连接**：`ops/test_lake_baseline.py` 要求本文件里每个
    `connect` 都带 `read_only=True` 字面量，而 `:memory:` 库开不了只读。
    那条基线是对的 —— 一个可写连接出现在这个文件里，
    下一个人复制它去连湖就没人拦得住。所以连接由**调用方**（`gateway/backends.py`）开。
    """
    body = sql.strip().rstrip(";")
    if not _PARQUET_ONLY.search(body):
        return True
    without = re.sub(r"read_parquet\s*\([^)]*\)", " __PQ__ ", body, flags=re.I)
    return bool(re.search(r'\b(FROM|JOIN)\s+(?!__PQ__)["\w]', without, re.I))


@contextmanager
def _parquet_conn() -> Iterator[duckdb.DuckDBPyConnection]:
    """跑纯 `read_parquet` 语句用的连接 —— **完全不碰 market.duckdb**（N-42）。

    **它是本文件里唯一一个不带 `read_only=True` 的 connect**，理由与
    `ops/test_lake_baseline.py` 自己在 `CONNECT_SCAN_EXEMPT_TREES` 注释里
    给对抗审计员写的那条**一模一样**：
    `duckdb.connect(":memory:")` + `read_parquet(...)`，**只读、不碰 catalog**。

    duckdb 拒绝以只读模式开内存库（`Cannot launch in-memory database in
    read-only mode!`），所以「每个 connect 都带 read_only=True」这条基线
    对 `:memory:` 无法满足 —— 那条基线守的是**对湖的连接**，
    而这个连接与湖无关：它没有底层文件，进程一退什么都不剩。

    基线因此加了一条**具名例外**（`MEMORY_CONN_EXEMPT`），不是放宽成通配：
    例外只认这一个函数名，别处再写 `:memory:` 照样红。
    """
    con = duckdb.connect(":memory:")
    try:
        yield con
    finally:
        con.close()


@contextmanager
def _conn_or_temp(
    conn: duckdb.DuckDBPyConnection | None,
    sql: str | None = None,
) -> Iterator[duckdb.DuckDBPyConnection]:
    """复用调用方给的连接;没给就临时开一个并在退出时关掉。

    `sql` 给了且它不需要 catalog（纯 `read_parquet`）→ 走**内存连接**，
    完全不碰 `market.duckdb`（N-42）。
    """
    if conn is not None:
        yield conn
    elif sql is not None and not needs_catalog(sql):
        with _parquet_conn() as pq:
            yield pq
    else:
        with catalog() as temp:
            yield temp


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------


def _check_dataset(dataset: str) -> str:
    """校验数据集名(它会被拼进文件路径和 SQL 标识符)。"""
    if not isinstance(dataset, str) or not _DATASET_RE.match(dataset):
        raise LakeError(f"数据集名非法:{dataset!r}(只允许 [a-z][a-z0-9_]*)")
    return dataset


def _check_ident(name: str) -> str:
    """校验列名 / 视图名。"""
    if not isinstance(name, str) or not _IDENT_RE.match(name):
        raise LakeError(f"标识符非法:{name!r}")
    return name


def _check_partition_glob(glob: str) -> str:
    """校验分区 glob:不许越出数据集目录,不许绝对路径。"""
    if not isinstance(glob, str) or not glob:
        raise LakeError(f"分区 glob 非法:{glob!r}")
    if not _PARTITION_GLOB_RE.match(glob):
        raise LakeError(f"分区 glob 含非法字符:{glob!r}")
    if ".." in glob or glob.startswith("/"):
        raise LakeError(f"分区 glob 不许越出数据集目录:{glob!r}")
    return glob


def _check_fragment(fragment: str, label: str) -> str:
    """校验拼进 SQL 的自由片段(where / order by):不许夹带第二条语句。"""
    if ";" in fragment:
        raise LakeError(f"{label} 里不许出现 ';':{fragment!r}")
    return fragment


# --------------------------------------------------------------------------
# catalog 视图
# --------------------------------------------------------------------------


def query(
    sql: str,
    params: Sequence[Any] | None = None,
    *,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> "Any":
    """执行一条**读语句**并返回 pandas DataFrame。

    语句头走白名单(`_ALLOWED_STATEMENT_HEADS`)。为什么还要这道白名单
    ——只读连接已经挡住了改库,但 duckdb 的 ``COPY ... TO 'file'`` 一类
    是往**文件系统**写,不受数据库只读模式约束;白名单从源头不让这类语句进来。

    Args:
        sql: 单条读语句。不许夹带 ``;`` 分隔的第二条语句。
        params: 预编译参数(``?`` 占位)。
        conn: 复用的连接;不给就临时开一个并在返回前关掉。

    Returns:
        pandas DataFrame。

    Raises:
        LakeError: 语句头不在白名单,或夹带了多条语句。
    """
    stripped = sql.strip()
    body = stripped.rstrip(";").strip()
    _check_fragment(body, "sql")
    head = re.split(r"[\s(]", body, maxsplit=1)[0].lower()
    if head not in _ALLOWED_STATEMENT_HEADS:
        raise LakeError(
            f"语句头 {head!r} 不在只读白名单里。lake 只服务读语句;"
            f"允许的语句头:{sorted(_ALLOWED_STATEMENT_HEADS)}"
        )
    with _conn_or_temp(conn, body) as con:
        return con.execute(body, list(params) if params else None).df()


def list_views(conn: duckdb.DuckDBPyConnection | None = None) -> list[str]:
    """列出 catalog 里全部视图名(升序)。"""
    with _conn_or_temp(conn) as con:
        rows = con.execute(
            "SELECT table_name FROM information_schema.tables ORDER BY 1"
        ).fetchall()
    return [r[0] for r in rows]


def view_exists(name: str, conn: duckdb.DuckDBPyConnection | None = None) -> bool:
    """catalog 里是否存在名为 `name` 的视图/表。"""
    _check_ident(name)
    with _conn_or_temp(conn) as con:
        row = con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
            [name],
        ).fetchone()
    return bool(row and row[0])


def describe_view(
    name: str, conn: duckdb.DuckDBPyConnection | None = None
) -> list[str]:
    """返回视图的列名清单(catalog 口径 = 全部分区的列**并集**)。

    ⚠️ 这不等于"任意一个分区的列":视图用 ``union_by_name``,
    实测 `daily` 视图 14 列而冻结窗口内每个分区只有 13 列。
    要拿"某个分区真实有哪些列",用 `read_gold(..., limit=0)` 看 DataFrame 的列。
    """
    ident = _check_ident(name)
    with _conn_or_temp(conn) as con:
        rows = con.execute(f'DESCRIBE "{ident}"').fetchall()
    return [r[0] for r in rows]


def count_rows(name: str, conn: duckdb.DuckDBPyConnection | None = None) -> int:
    """视图行数。

    ⚠️ 对 `daily` 这类 4289 分区的大表会把全部 parquet 打开
    —— 先 `raise_open_file_limit()`,否则 "Too many open files"。
    小表(分区数少)随便调。
    """
    ident = _check_ident(name)
    with _conn_or_temp(conn) as con:
        row = con.execute(f'SELECT count(*) FROM "{ident}"').fetchone()
    return int(row[0])


def column_range(
    dataset: str,
    column: str,
    *,
    bound: str | None = None,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> dict[str, Any]:
    """**现场**复算一列的 min / max / 截到 `bound` 的 max,外加表行数。

    这是"体检产物不许自证"的那把尺子(卡 0.2 补救 D1)。
    `ops/lake_baseline.json` 里的 `max_date` / `rows` 必须能被这个函数复算出来 ——
    产物写什么就信什么,等于让 JSON 给自己出成绩单。

    **一列一次全扫**,实测 18 张 v1 表合计约 12s(大表 `balancesheet` 单表 ~2s),
    可以放进验收测试;不要在循环里对同一张表反复调。

    返回的日期一律是 `CAST(... AS VARCHAR)` 后的字符串:湖里日期列实测都是
    `VARCHAR` 的 `YYYYMMDD`,统一成字符串后**字典序 == 时间序**,
    调用方不必关心底层类型。`bound` 也必须是同形态的字符串。

    Args:
        dataset: 视图名(catalog 里的表)。
        column: 日期列名。
        bound: 上界(含)。给了就额外返回 ``max_upto`` —— 冻结线(红线 7)以内
            的最大值。**这个量不随湖侧 ETL 前进而变**(历史是不动的),
            所以它才是能被逐字对账的那个数。
        conn: 复用的连接;不给就临时开一个。

    Returns:
        ``{"min": str|None, "max": str|None, "max_upto": str|None, "rows": int}``。
        空表时三个日期都是 `None`。
    """
    ds = _check_ident(dataset)
    col = _check_ident(column)
    cast = f'CAST("{col}" AS VARCHAR)'
    if bound is None:
        sql = f'SELECT min({cast}), max({cast}), NULL, count(*) FROM "{ds}"'
        params: list[Any] = []
    else:
        sql = (
            f"SELECT min({cast}), max({cast}), "
            f"max({cast}) FILTER (WHERE {cast} <= ?), "
            f'count(*) FROM "{ds}"'
        )
        params = [str(bound)]
    with _conn_or_temp(conn) as con:
        row = con.execute(sql, params or None).fetchone()
    return {
        "min": None if row[0] is None else str(row[0]),
        "max": None if row[1] is None else str(row[1]),
        "max_upto": None if row[2] is None else str(row[2]),
        "rows": int(row[3]),
    }


# --------------------------------------------------------------------------
# gold 分区(新鲜度的正确来源)
# --------------------------------------------------------------------------


def gold_dir(dataset: str) -> Path:
    """`$GOLD/<dataset>/` 的路径。"""
    return cfg.GOLD / _check_dataset(dataset)


def gold_datasets() -> list[str]:
    """`$GOLD` 下的全部数据集目录名(升序)。"""
    with os.scandir(cfg.GOLD) as it:
        return sorted(e.name for e in it if e.is_dir())


def gold_partitions(dataset: str) -> list[str]:
    """直接列 `$GOLD/<dataset>/` 的分区目录名,升序。

    **这是判断数据新鲜度的正确方式。**
    不要用 `crawler_state.sqlite3` 的 watermarks —— 那是**补数游标**不是新鲜度:
    补数从新往旧走会把 watermark 一路拖回一年前,而 gold 分区一天都不会少。

    走 `os.scandir`,不碰 duckdb,毫秒级(实测 `daily` 4289 个分区 2.5ms)。

    Args:
        dataset: 数据集名,如 ``"daily"``。

    Returns:
        形如 ``['trade_date=2009-01-05', ..., 'trade_date=2026-08-28']`` 的升序列表。
        数据集目录不存在时返回空列表(不抛)。
    """
    root = gold_dir(dataset)
    if not root.is_dir():
        return []
    with os.scandir(root) as it:
        return sorted(e.name for e in it if e.is_dir())


def split_partition(partition: str) -> tuple[str, str]:
    """把 ``'trade_date=2026-07-31'`` 拆成 ``('trade_date', '2026-07-31')``。

    没有 ``=`` 时返回 ``('', 原串)``。
    """
    key, sep, value = partition.partition("=")
    if not sep:
        return "", partition
    return key, value


def gold_partition_key(dataset: str) -> str | None:
    """数据集的分区键名(取第一个分区目录解析),没有分区则 `None`。"""
    parts = gold_partitions(dataset)
    if not parts:
        return None
    key, _ = split_partition(parts[0])
    return key or None


def partition_values(dataset: str) -> list[str]:
    """分区值(去掉 ``键=`` 前缀),升序。"""
    return [split_partition(p)[1] for p in gold_partitions(dataset)]


def partition_semantics(dataset: str) -> str:
    """这个数据集的分区值**是什么意思** —— 见 `PARTITION_SEMANTICS`。

    分三类,混起来就会得出错误结论:

    * ``"data_time"``:分区值 = 数据日期(`trade_date` / `end_date` / `trade_month` …)。
      最新分区 = 新鲜度,可以拿来截冻结线。
    * ``"capture_time"``:分区值 = **抓取日期**(`snapshot_date`)。
      `stock_basic` / `trade_cal` / `index_basic` 属此类,它们的快照全在
      冻结线之后,但数据本身覆盖到 2009 年 —— 别拿它截冻结线。
    * ``"entity_code"``:分区值 = 实体码(`ts_code` / `l3_code`)。
      "最新分区"只是字典序最大的代码(``ts_code=920992.BJ``),与时间无关。
    """
    key = gold_partition_key(dataset)
    if key is None:
        return "none"
    if key in TIME_PARTITION_KEYS:
        return "data_time"
    if key in CAPTURE_PARTITION_KEYS:
        return "capture_time"
    return "entity_code"


def latest_gold_partition(dataset: str) -> str | None:
    """最新(字典序最大)的分区目录名;没有分区则 `None`。

    ⚠️ 它等于"数据到哪天了"**只在** `partition_semantics(dataset) == "data_time"` 时成立。
    另外两类见 `partition_semantics()` 的说明。
    """
    parts = gold_partitions(dataset)
    return parts[-1] if parts else None


def gold_latest_value(dataset: str) -> str | None:
    """**数据时间**分区的"数据到哪天了";其它分区语义一律返回 `None`。

    返回值形如 ``'2026-08-28'``(日分区)或 ``'202608'``(月分区)。
    刻意对 `capture_time` / `entity_code` 返回 `None` 而不是硬给一个值 ——
    宁可答"不知道",也不要给一个会被当成新鲜度用的假答案。
    """
    if partition_semantics(dataset) != "data_time":
        return None
    parts = gold_partitions(dataset)
    return split_partition(parts[-1])[1] if parts else None


def gold_latest_capture(dataset: str) -> str | None:
    """**抓取时间**分区的最新快照日;非 `capture_time` 分区返回 `None`。"""
    if partition_semantics(dataset) != "capture_time":
        return None
    parts = gold_partitions(dataset)
    return split_partition(parts[-1])[1] if parts else None


def partitions_upto(dataset: str, bound: str | None = None) -> list[str]:
    """截到 `bound`(含)为止的分区列表 —— 冻结线(红线 7)的执行工具。

    比较在**分区值**上按字符串序做,所以 `YYYY-MM-DD` 与 `YYYYMM` 都成立。

    ⚠️ 只对 ``partition_semantics(dataset) == "data_time"`` 的数据集有意义。
    对 `capture_time` 分区(`stock_basic` / `trade_cal` / `index_basic`)它会返回
    **空列表** —— 那不是"冻结线内没数据",而是"这类表的 PIT 语义不在分区上,
    在字段上"(见 `CAPTURE_PARTITION_KEYS`)。

    Args:
        dataset: 数据集名。
        bound: 分区值上界,默认 `cfg.FREEZE_DATE`(``'2026-07-31'``)。
            月分区请自己传 ``'202607'`` 这类同形态的值。

    Returns:
        分区目录名的升序列表。
    """
    limit_value = cfg.FREEZE_DATE if bound is None else bound
    out: list[str] = []
    for part in gold_partitions(dataset):
        _, value = split_partition(part)
        if value <= limit_value:
            out.append(part)
    return out


# --------------------------------------------------------------------------
# 定向分区读取
# --------------------------------------------------------------------------


def read_gold(
    dataset: str,
    partition_glob: str,
    *,
    columns: Sequence[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    union_by_name: bool = True,
    hive_partitioning: bool = False,
    conn: duckdb.DuckDBPyConnection | None = None,
) -> "Any":
    """走 `read_parquet` 读**定向分区**,避开 "Too many open files"。

    catalog 里的视图是 ``read_parquet('<gold>/<ds>/**/*.parquet')`` —— 查 `daily`
    要开 4289 个分区文件,而 finance01 的默认 soft fd 上限只有 1024。
    本函数只展开你点名的那些分区,这是读大表的正确姿势。

    Args:
        dataset: 数据集名,如 ``"daily"``。
        partition_glob: 分区目录的 glob,相对 `$GOLD/<dataset>/`。
            例:``"trade_date=2026-07-*"``、``"trade_date=2026-07-31"``、
            ``"ts_code=6005*"``、``"*"``(等于全表,慎用)。
        columns: 只取这些列;`None` = 全部。
        where: 追加的过滤条件(不含 ``WHERE`` 关键字)。不许含 ``;``。
        order_by: 排序表达式(不含 ``ORDER BY``)。不许含 ``;``。
        limit: 行数上限。``0`` 合法,用来只探列名。
        union_by_name: 跨分区按列名取并集,默认 `True`,与 catalog 视图口径一致。
            **实测有分区间 schema 漂移,而且关掉它是静默丢列不是报错**:
            `daily` 从 `trade_date=2026-08-06` 起多了一列 `last_seen_at`,
            跨这个点读 ``trade_date=2026-08-0*`` 时 `False` 安静地返回 13 列、
            `True` 返回 14 列;三大报表还有列类型漂移(`income` 关掉会抛
            ``failed to cast column "oper_cost"``)。除非只读单个分区,别关。
        hive_partitioning: 是否把分区键注入成一列。默认 `False` —— 湖里的
            parquet 自己就带 `trade_date` 等列,再注入会与已有列同名。
        conn: 复用的连接;不给就临时开一个。

    Returns:
        pandas DataFrame。

    Raises:
        LakeError: 数据集名 / glob / 列名非法,或片段里夹带了 ``;``。
    """
    ds = _check_dataset(dataset)
    glob = _check_partition_glob(partition_glob)

    if columns is None:
        projection = "*"
    else:
        if not columns:
            raise LakeError("columns 给了空序列;要全部列请传 None")
        projection = ", ".join(f'"{_check_ident(c)}"' for c in columns)

    pattern = f"{cfg.GOLD / ds}/{glob}/*.parquet"
    scan = (
        "read_parquet(?, union_by_name => {ubn}, hive_partitioning => {hive})".format(
            ubn=str(bool(union_by_name)).lower(),
            hive=str(bool(hive_partitioning)).lower(),
        )
    )
    sql = f"SELECT {projection} FROM {scan}"
    if where:
        sql += f" WHERE {_check_fragment(where, 'where')}"
    if order_by:
        sql += f" ORDER BY {_check_fragment(order_by, 'order_by')}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    with _conn_or_temp(conn) as con:
        return con.execute(sql, [pattern]).df()


if __name__ == "__main__":  # pragma: no cover - 手工自检
    raise_open_file_limit()
    with catalog() as _con:
        _views = list_views(_con)
        print(f"catalog: {cfg.CATALOG}")
        print(f"views  : {len(_views)}")
        for _ds in ("daily", "trade_cal", "income", "stock_basic"):
            print(
                f"  {_ds:12s} parts={len(gold_partitions(_ds)):5d} "
                f"semantics={partition_semantics(_ds):12s} "
                f"latest={latest_gold_partition(_ds)} "
                f"fresh={gold_latest_value(_ds)}"
            )
