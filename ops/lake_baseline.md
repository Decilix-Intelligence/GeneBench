# 湖只读基线(卡 0.2)

- 生成时间(UTC):`2026-09-01T02:53:14Z`
- 冻结线:**20260731**(`freeze_line_ok = max_date >= 冻结线`)
- **数值口径**:duckdb 只读现场重算(rows/columns/min_date/max_date) + os.scandir(gold 分区)
- 旁证:`/home/ljn/projects/data/market_lake/manifests/coverage-audit-latest.json`(as_of=20260831,status=complete) —— 旁证 only —— 见 audit_* 字段与 H7
- catalog:`/home/ljn/projects/data/market_lake/catalog/market.duckdb`(150 个视图)

- **卡 0.2 判据**:**PASS** —— 22 张表,视图齐全=True,过冻结线=True(其中 3 张无日期列,冻结线不适用)
- **新鲜度(另一维)**:**STALLED_TABLES_PRESENT** —— 8 张停更,1 张判不了。湖侧基准 `20260901`。

> ⚠️ **两列不是一回事**。这 8 张表**已停更但仍然过冻结线**,所以在只看判据 ② 的基线里是一片绿(H6)。对 v1 的 ≤2026-07-31 窗口它们**不构成数据缺口**,因此不影响本卡 verdict;但卡 1.3 的网关**不得**拿 freeze_line_ok 当新鲜度判据,要读本字段。

## 逐表

| 数据集 | 视图 | 行数 | 列 | 日期列 | 覆盖 | gold 分区 | 分区语义 | 最新分区 | 过冻结线 | 仍在更新 | 哪张卡要用 |
| --- | --- | ---: | ---: | --- | --- | ---: | --- | --- | --- | --- | --- |
| `daily` | ✅ | 14,698,312 | 14 | trade_date | 20090105→20260831 | 4,290 | data_time | `trade_date=2026-08-31` | ✅ | ✅ 活(滞后 1 天) | 1.2, 1.3, 1.4, 2.1, 3.2, 5.2 |
| `adj_factor` | ✅ | 15,380,771 | 6 | trade_date | 20090105→20260901 | 4,291 | data_time | `trade_date=2026-09-01` | ✅ | ✅ 活(滞后 0 天) | 1.3, 1.4, 2.1, 5.1, 5.2 |
| `daily_basic` | ✅ | 14,607,515 | 22 | trade_date | 20090105→20260831 | 4,290 | data_time | `trade_date=2026-08-31` | ✅ | ✅ 活(滞后 1 天) | 1.3, 1.4, 2.1, 5.2 |
| `stk_limit` | ✅ | 15,008,861 | 8 | trade_date | 20090105→20260831 | 4,290 | data_time | `trade_date=2026-08-31` | ✅ | ✅ 活(滞后 1 天) | 1.2, 1.3, 1.4, 3.2, 5.2 |
| `suspend_d` | ✅ | 482,298 | 7 | trade_date | 20090105→20260831 | 4,290 | data_time | `trade_date=2026-08-31` | ✅ | ✅ 活(滞后 1 天) | 1.2, 1.3, 1.4, 3.2, 5.1 |
| `trade_cal` | ✅ | 6,574 | 6 | cal_date | 20090101→20261231 | 1 | capture_time | `snapshot_date=2026-08-05` | ✅ | ⛔ **停更 27 天** | 1.2, 1.3, 1.4, 2.2, 3.2, 5.1 |
| `index_weight` | ✅ | 310,798 | 6 | trade_date | 20090123→20260731 | 211 | data_time | `trade_date=2026-07-31` | ✅ | ✅ 活(滞后 32 天) | 1.1, 1.3, 1.4, 3.2 |
| `stock_basic` | ✅ | 117,691 | 14 | — | — | 20 | capture_time | `snapshot_date=2026-09-01` | —(无日期列) | ✅ 活(滞后 0 天) | 1.1, 1.3, 1.4, 5.1 |
| `namechange` | ✅ | 14,156 | 9 | ann_date | 19901201→20260806 | 5,875 | entity_code | `ts_code=920992.BJ` | ✅ | ⛔ **停更 26 天** | 1.1, 1.3, 5.1 |
| `stock_st` | ✅ | 337,687 | 9 | trade_date | 20160809→20260828 | 121 | data_time | `trade_month=202608` | ✅ | ✅ 活(滞后 4 天) | 1.1, 1.2, 1.3, 3.2 |
| `st_history` | ✅ | 1,227 | 12 | pub_date | 20220429→20260828 | 53 | data_time | `published_month=202608` | ✅ | ✅ 活(滞后 4 天) | 1.1 |
| `index_member_all` | ✅ | 7,893 | 13 | — | — | 338 | entity_code | `l3_code=859951.SI` | —(无日期列) | ❔ 判不了 | 1.1, 2.1, 3.2 |
| `income` | ✅ | 366,326 | 89 | ann_date | 20080102→20260804 | 5,854 | entity_code | `ts_code=920992.BJ` | ✅ | ⛔ **停更 28 天** | 1.3, 1.4, 2.1, 3.2, 5.1 |
| `income_vip` | ✅ | 401,367 | 89 | ann_date | 20090408→20260829 | 70 | data_time | `end_date=2026-06-30` | ✅ | ✅ 活(滞后 3 天) | 1.3, 1.4, 2.1 |
| `balancesheet` | ✅ | 412,547 | 156 | ann_date | 20080102→20260804 | 5,854 | entity_code | `ts_code=920992.BJ` | ✅ | ⛔ **停更 28 天** | 1.3, 1.4, 2.1, 3.2, 5.1 |
| `balancesheet_vip` | ✅ | 348,387 | 157 | ann_date | 20090409→20260828 | 70 | data_time | `end_date=2026-06-30` | ✅ | ✅ 活(滞后 4 天) | 1.3, 1.4, 2.1 |
| `cashflow` | ✅ | 376,183 | 101 | ann_date | 20080102→20260804 | 5,852 | entity_code | `ts_code=920992.BJ` | ✅ | ⛔ **停更 28 天** | 1.3, 1.4, 2.1, 3.2, 5.1 |
| `cashflow_vip` | ✅ | 413,399 | 102 | ann_date | 20090408→20260828 | 70 | data_time | `end_date=2026-06-30` | ✅ | ✅ 活(滞后 4 天) | 1.3, 1.4, 2.1 |
| `index_daily` | ✅ | 46,739 | 14 | trade_date | 20090105→20260831 | 4,290 | data_time | `trade_date=2026-08-31` | ✅ | ✅ 活(滞后 1 天) | 2.2, 3.2, 5.2 |
| `index_basic` | ✅ | 8 | 16 | — | — | 2 | capture_time | `snapshot_date=2026-08-06` | —(无日期列) | ⛔ **停更 26 天** | 1.1, 1.3 |
| `dividend` | ✅ | 177,858 | 19 | ann_date | 19910317→20260801 | 5,824 | entity_code | `ts_code=920992.BJ` | ✅ | ⛔ **停更 31 天** | 5.1, 2.1 |
| `limit_list_d` | ✅ | 158,546 | 21 | trade_date | 20200102→20260805 | 1,597 | data_time | `trade_date=2026-08-05` | ✅ | ⛔ **停更 27 天** | 1.2 |

> **`过冻结线` 与 `仍在更新` 是两件独立的事,刻意分成两列。**前者回答'v1 的 ≤ 冻结线窗口取不取得到数'(卡 0.2 的判据),后者回答'这张表今天还在长吗'(卡 1.3 网关要的)。实测有表**前者绿、后者红** —— 把它们合并成同一种绿正是这次补救要堵的洞。

> 分区语义三类,混起来就会得出错误结论:`data_time` = 分区值是数据日期(最新分区 = 新鲜度,可截冻结线);`capture_time` = 分区值是**我们哪天抄的表**(这几张的快照全在冻结线之后,但数据本身覆盖到 2009 年);`entity_code` = 分区值是 ts_code/l3_code,与时间无关。

## ⛔ 停更表(过了冻结线,但已经不长了)

湖侧基准 `20260901`(全部 update_cadence=trading_day 的表里最新的那个新鲜度日期。拿湖自己当基准(而不是墙上时钟),判的是表之间的相对滞后。)

| 数据集 | 节奏 | 新鲜度 | 新鲜度来源 | 滞后 | 容忍 | 为什么看着是绿的 | 哪张卡要用 |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| `trade_cal` | trading_day | 20260805 | latest_capture_partition(snapshot_date) | **27 天** | 12 天 | max_date=20261231 >= 冻结线 20260731,只看判据 ② 会判成绿 | 1.2, 1.3, 1.4, 2.2, 3.2, 5.1 |
| `namechange` | event | 20260806 | live max(ann_date) | **26 天** | 14 天 | max_date=20260806 >= 冻结线 20260731,只看判据 ② 会判成绿 | 1.1, 1.3, 5.1 |
| `income` | event | 20260804 | live max(ann_date) | **28 天** | 14 天 | max_date=20260804 >= 冻结线 20260731,只看判据 ② 会判成绿 | 1.3, 1.4, 2.1, 3.2, 5.1 |
| `balancesheet` | event | 20260804 | live max(ann_date) | **28 天** | 14 天 | max_date=20260804 >= 冻结线 20260731,只看判据 ② 会判成绿 | 1.3, 1.4, 2.1, 3.2, 5.1 |
| `cashflow` | event | 20260804 | live max(ann_date) | **28 天** | 14 天 | max_date=20260804 >= 冻结线 20260731,只看判据 ② 会判成绿 | 1.3, 1.4, 2.1, 3.2, 5.1 |
| `index_basic` | trading_day | 20260806 | latest_capture_partition(snapshot_date) | **26 天** | 12 天 | 无日期列,判据 ② 不适用 | 1.1, 1.3 |
| `dividend` | event | 20260801 | live max(ann_date) | **31 天** | 14 天 | max_date=20260801 >= 冻结线 20260731,只看判据 ② 会判成绿 | 5.1, 2.1 |
| `limit_list_d` | trading_day | 20260805 | live max(trade_date) | **27 天** | 12 天 | max_date=20260805 >= 冻结线 20260731,只看判据 ② 会判成绿 | 1.2 |

❔ **新鲜度判不了**的表:`index_member_all` —— 区间表没有单一时间轴。基线里 `stalled=null`,**不许**因为判不了就当它是活的。

## 已知陷阱(本卡实测,卡 1.3/1.4 别再踩一遍)

### H1 —— 关掉 union_by_name 是**静默丢列**,不是报错

- **实测证据**:read_gold('daily', 'trade_date=2026-08-0*') 在 union_by_name=False 下安静地返回 13 列(丢了 last_seen_at),=True 返回 14 列。duckdb 按第一个文件的 schema 绑定,后面文件多出来的列直接不要。
- **影响**:卡 1.3/1.4 跨分区取数若关掉 union,会在无任何报错的情况下少一列。
- **已做的规避**:lake.read_gold() 默认 union_by_name=True;只读单分区时才可关。

### H2 —— schema 漂移是**逐分区**的,不是按时间整齐切分

- **实测证据**:income 的 ts_code=000001.SZ 有 89 列,而 300325.SZ/301381.SZ/920992.BJ 都是 88 列;balancesheet 156/155、cashflow 101/100 同理。daily 则是按时间切:trade_date=2026-08-06 起从 13 列变 14 列。
- **影响**:拿单个分区探 schema 会得出'没漂移'的错误结论。
- **已做的规避**:本基线对每张表抽样首/中/末/冻结窗口末共 4 个分区,报并集与漂移列。

### H3 —— 还有**列类型**漂移,会在跨分区读时抛异常

- **实测证据**:read_gold('income', 'ts_code=00000*', union_by_name=False) 抛 ConversionException: failed to cast column "oper_cost"。
- **影响**:三大报表跨票取数是 v1 基本面因子的主路径,踩上就整批失败。
- **已做的规避**:同 H1:走 union_by_name=True。

### H4 —— snapshot_date 分区是**抓取时间**,不是数据时间

- **实测证据**:trade_cal / stock_basic / index_basic 的快照最早 2026-08-05,全部晚于冻结线 2026-07-31;但 trade_cal 的 cal_date 覆盖 20090101→20261231。
- **影响**:按分区截冻结线会得出'这些表在 v1 窗口内没有数据'的错误结论。
- **已做的规避**:lake.partition_semantics() 把它标成 capture_time;PIT 语义走表内字段(list_date/delist_date/cal_date)回溯,不选快照。

### H5 —— 默认 fd 上限 1024,查全表必炸

- **实测证据**:finance01 默认 RLIMIT_NOFILE soft=1024 / hard=1048576;catalog 视图是 read_parquet('<gold>/<ds>/**/*.parquet'),daily 有 4289 个分区文件。
- **影响**:SELECT * FROM daily 直接 'Too many open files'。
- **已做的规避**:lake.raise_open_file_limit() 抬 soft 到 8192(无需特权);大表走 read_gold 定向分区。

### H6 —— **过了冻结线 ≠ 这张表还活着**

- **实测证据**:limit_list_d 的 gold 分区硬停在 trade_date=2026-08-05,而 daily 在其后还有 17 个交易日分区;income/balancesheet/cashflow 的 max(ann_date) 停在 20260804,孪生的 _vip 表已到 20260828/29;namechange 停在 20260806、dividend 停在 20260801;trade_cal 只有 1 个 snapshot_date=2026-08-05 分区、index_basic 只有 2 个(最新 2026-08-06),从此再没抄过。这 6 张表的 max_date 全都 >= 20260731,于是在只看冻结线的基线里**一片绿**。
- **影响**:卡 1.3 的网关若照'过冻结线'判新鲜度,会把停更表当成实时表对外供数;对 v1 的 ≤2026-07-31 窗口它们不构成数据缺口,但**语义是错的**。
- **已做的规避**:baseline 的 summary.stalled_tables 显式列出停更表;每张表带 update_cadence / lag_days / stalled 三个字段,md 里'过冻结线'与'仍在更新'分成**两列**渲染,不再合并成同一种绿。

### H7 —— coverage-audit 周末不跑,`as_of` 天然滞后 1-3 天

- **实测证据**:quant-datahub-coverage-audit.timer: OnCalendar=Mon..Fri *-*-* 23:20:00 Asia/Shanghai(=15:20 UTC)+ RandomizedDelaySec=5m(实测落在 15:22 UTC)。**周末不触发** —— 周六/周日/周一上午取到的 as_of 一律是上周五,滞后 1-3 天是**结构性的,不是偶发故障**。所以 audit_* 只当旁证,rows/columns/min_date/max_date 一律以现场重算为准。
- **影响**:本卡第一版基线直接抄了 as_of=20260828 的审计值,于是 5 张表对不上现场:stock_st 337072/20260825、income_vip 393932/20260822、balancesheet_vip 343135/20260822、cashflow_vip 407461/20260822、st_history 1221 行 —— 全部低于现场重算值。
- **已做的规避**:rows/columns/min_date/max_date 一律现场重算(lake.column_range),审计值降级成 audit_* 前缀的旁证并标注 audit_as_of。

## 逐表备注(踩坑)

### `daily` —— 日线量价(未复权)——v1 一切价格的底座

- **哪张卡要用**:1.2, 1.3, 1.4, 2.1, 3.2, 5.2
- **为什么非它不可**:卡 1.2 用它的**缺行**识别停牌;卡 1.3 的 /bars 端点直接答它;卡 1.4 快照它;卡 2.1 全部量价因子的输入;卡 5.2 回测取价。
- 冻结线判据:`现场 max(trade_date)=20260831 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260831 落后湖侧基准 20260901 共 1 天,trading_day 节奏的容忍度是 12 天`(来源:live max(trade_date))
- 为什么是这一列:日分区键与表内时间轴同名同义,唯一候选。
- 备注:停牌票在这里是**缺行**不是显式标记,必须 join suspend_d + trade_cal 才能区分'停牌'与'尚未上市/已退市';触板判定也只能用它的 close/high/low 去比 stk_limit。；⚠️ 分区间 schema 漂移:catalog 视图 14 列(全分区并集),抽样分区实际为 trade_date=2009-01-05=13列, trade_date=2017-11-01=13列, trade_date=2026-08-31=14列, trade_date=2026-07-31=13列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。

### `adj_factor` —— 复权因子 —— v1 **唯一**复权口径

- **哪张卡要用**:1.3, 1.4, 2.1, 5.1, 5.2
- **为什么非它不可**:卡 1.3 的 /adj 端点;卡 2.1 因子计算前的价格复权;卡 5.1 复权指纹探针拿它当基准答案;卡 5.2 回测净值。
- 冻结线判据:`现场 max(trade_date)=20260901 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260901 落后湖侧基准 20260901 共 0 天,trading_day 节奏的容忍度是 12 天`(来源:live max(trade_date))
- 为什么是这一列:同 daily。
- 审计对账(as_of=20260831):{"rows": {"audit": 15375204, "live": 15380771, "delta": 5567}, "max_date": {"audit": "20260831", "live": "20260901"}}
- 备注:实施稿定死:v1 数据面统一走 adj_factor,stk_factor_pro 的 bfq/hfq/qfq 三价口径**不进网关**(2026-08 起两套口径不同步)。；⚠️ 分区间 schema 漂移:catalog 视图 6 列(全分区并集),抽样分区实际为 trade_date=2009-01-05=5列, trade_date=2017-11-01=5列, trade_date=2026-09-01=6列, trade_date=2026-07-31=5列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。；审计(as_of=20260831)与现场重算有出入 ['max_date', 'rows'] ——**以现场为准**,审计值见 audit_* 字段(H7:审计周末不跑,天然滞后 1-3 天)。

### `daily_basic` —— 日频估值/换手/市值衍生量

- **哪张卡要用**:1.3, 1.4, 2.1, 5.2
- **为什么非它不可**:卡 1.3 的 /bars 扩展字段;卡 2.1 的 pe/pb/ps/turnover_rate/total_mv/circ_mv 类因子;卡 5.2 市值中性化与分组。
- 冻结线判据:`现场 max(trade_date)=20260831 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260831 落后湖侧基准 20260901 共 1 天,trading_day 节奏的容忍度是 12 天`(来源:live max(trade_date))
- 为什么是这一列:同 daily。
- 备注:与 daily 同为 trade_date 日分区,行数略少于 daily(部分票缺估值)。；⚠️ 分区间 schema 漂移:catalog 视图 22 列(全分区并集),抽样分区实际为 trade_date=2009-01-05=21列, trade_date=2017-11-01=21列, trade_date=2026-08-31=22列, trade_date=2026-07-31=21列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。

### `stk_limit` —— 涨跌停价

- **哪张卡要用**:1.2, 1.3, 1.4, 3.2, 5.2
- **为什么非它不可**:卡 1.2 的触板判定;卡 1.3 的 /limits 端点;卡 3.2 的 S6/S8 约束与撮合;卡 5.2 可交易性过滤。
- 冻结线判据:`现场 max(trade_date)=20260831 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260831 落后湖侧基准 20260901 共 1 天,trading_day 节奏的容忍度是 12 天`(来源:live max(trade_date))
- 为什么是这一列:同 daily。
- 备注:**pre_close 全为 NULL**(实测),触板只能用 daily.close/high/low 对 up_limit/down_limit 比价,不要指望这张表自带前收。；⚠️ 分区间 schema 漂移:catalog 视图 8 列(全分区并集),抽样分区实际为 trade_date=2009-01-05=7列, trade_date=2017-11-01=7列, trade_date=2026-08-31=8列, trade_date=2026-07-31=7列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。

### `suspend_d` —— 停复牌事件(S=停牌 / R=复牌)

- **哪张卡要用**:1.2, 1.3, 1.4, 3.2, 5.1
- **为什么非它不可**:卡 1.2 三方 join 的第二源;卡 1.3 的 /tradability;卡 3.2 的 S2 清洗陷阱题材料;卡 5.1 欠定语义探针。
- 冻结线判据:`现场 max(trade_date)=20260831 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260831 落后湖侧基准 20260901 共 1 天,trading_day 节奏的容忍度是 12 天`(来源:live max(trade_date))
- 为什么是这一列:同 daily(事件发生日 = 交易日)。
- 备注:suspend_type 是 S/R 事件流,不是逐日状态,要自己前向填充成区间。；⚠️ 分区间 schema 漂移:catalog 视图 7 列(全分区并集),抽样分区实际为 trade_date=2009-01-05=6列, trade_date=2017-11-01=6列, trade_date=2026-08-31=7列, trade_date=2026-07-31=6列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。

### `trade_cal` —— 交易日历

- **哪张卡要用**:1.2, 1.3, 1.4, 2.2, 3.2, 5.1
- **为什么非它不可**:卡 1.2 区分'非交易日'与'停牌';卡 1.3 的 /calendar;卡 2.2 回测对齐;卡 5.1 日历探针的判据。
- 冻结线判据:`现场 max(cal_date)=20261231 >= 20260731`
- 新鲜度判据:`停更:新鲜度 20260805 落后湖侧基准 20260901 共 27 天,trading_day 节奏的容忍度是 12 天`(来源:latest_capture_partition(snapshot_date))
- 为什么是这一列:cal_date 是日历本身的时间轴;pretrade_date 是派生的前一交易日,不独立。⚠️ 但 cal_date **不能当新鲜度**:它是预写到 20261231 的未来日历,这张表的新鲜度是 snapshot_date(capture_time 语义,见 H4)。
- 备注:⛔ 停更(体检判定):停更:新鲜度 20260805 落后湖侧基准 20260901 共 27 天,trading_day 节奏的容忍度是 12 天。注意它 freeze_line_ok=True —— **过了冻结线不等于这张表还活着**(H6)。；湖里**只有 SSE 一个交易所**(6574 行,20090101→20261231,**含未来日历**——越过冻结线的日期天然存在,网关必须自己截断);gold 只有 1 个 snapshot_date 分区,不是日分区。⛔ **停更**:那唯一一个快照是 snapshot_date=2026-08-05,**此后从未刷新**。它照样'过冻结线'(cal_date 一路到 20261231),但那是**快照里预写的未来日历**,不是这张表还活着的证据 —— 判它新鲜度只能看**快照日**,不能看 cal_date。；分区键是 snapshot_date(**抓取时间**,不是数据时间):快照 snapshot_date=2026-08-05 → snapshot_date=2026-08-05 **全部晚于冻结线 2026-07-31**,冻结窗口内根本没有快照可选。这不是数据缺口 —— 这类表的 PIT 语义在**字段**上(list_date/delist_date/cal_date),网关必须走字段回溯而不是选快照。

### `index_weight` —— 指数成分权重月末快照 —— PIT 宇宙的**主源**

- **哪张卡要用**:1.1, 1.3, 1.4, 3.2
- **为什么非它不可**:卡 1.1 用相邻月末 diff 推 csi300/500/1000 的成分区间(方案甲)。
- 冻结线判据:`现场 max(trade_date)=20260731 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260731 落后湖侧基准 20260901 共 32 天,month_end 节奏的容忍度是 45 天`(来源:live max(trade_date))
- 为什么是这一列:月末快照的生效日,唯一时间轴。
- 备注:只有 000300.SH / 000905.SH / 000852.SH 三个指数,**月末快照**(2026 年为 0130/0227/0331/0430/0529/0630/0731,每期恰好 300/500/1000 条),**天然冻在 20260731**;月内调整会被抹平,这条局限要写进数据卡。注意它**不是停更** —— 月末节奏下 20260731 就是当期最新,所以 update_cadence 登记为 month_end(容忍 45 天),别拿日频尺子量它。

### `stock_basic` —— 上市状态多快照表(list_date / delist_date / list_status)

- **哪张卡要用**:1.1, 1.3, 1.4, 5.1
- **为什么非它不可**:卡 1.1 的兜底源(退市/未上市回溯);卡 1.3 封装 snapshot 语义;卡 5.1 PIT 宇宙探针的对照。
- 冻结线判据:`n/a:无日期列(区间表/元数据表),冻结线不适用`
- 新鲜度判据:`仍在更新:新鲜度 20260901 落后湖侧基准 20260901 共 0 天,trading_day 节奏的容忍度是 12 天`(来源:latest_capture_partition(snapshot_date))
- 为什么是这一列:表内 list_date / delist_date 是**上市/退市事件日**,不是这张表的时间轴 —— 拿 max(list_date) 当新鲜度会把'最近有新股上市'误读成'快照是新的'。这张表的时间轴在**分区**上(snapshot_date),按 capture_time 处理。
- 审计对账(as_of=20260831):{"rows": {"audit": 111799, "live": 117691, "delta": 5892}}
- 备注:**多快照表**,分区 snapshot_date=YYYY-MM-DD,**只有 2026-08-05 起的十几个快照**(全部晚于冻结线)。2026-08-05 之前的状态**只能靠 list_date/delist_date 字段回溯,不能靠快照** —— 网关必须把这条规则写死,否则会漏未来信息。✅ 快照**每个交易日都在刷新**(与 trade_cal / index_basic 相反),是三张 capture_time 表里唯一还活着的。；⚠️ 分区间 schema 漂移:catalog 视图 14 列(全分区并集),抽样分区实际为 snapshot_date=2026-08-05=13列, snapshot_date=2026-08-19=14列, snapshot_date=2026-09-01=14列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。；分区键是 snapshot_date(**抓取时间**,不是数据时间):快照 snapshot_date=2026-08-05 → snapshot_date=2026-09-01 **全部晚于冻结线 2026-07-31**,冻结窗口内根本没有快照可选。这不是数据缺口 —— 这类表的 PIT 语义在**字段**上(list_date/delist_date/cal_date),网关必须走字段回溯而不是选快照。；审计(as_of=20260831)与现场重算有出入 ['rows'] ——**以现场为准**,审计值见 audit_* 字段(H7:审计周末不跑,天然滞后 1-3 天)。；多快照表:跨快照重复主键 105909 行(同一 code 在多个 snapshot 里各有一行,取数必须先选定快照)。

### `namechange` —— 曾用名变更(ST 改名的原始事件)

- **哪张卡要用**:1.1, 1.3, 5.1
- **为什么非它不可**:卡 1.1 用它还原任一时点的证券简称,判 ST/*ST 前缀;卡 5.1 PIT 探针交叉核对。
- 冻结线判据:`现场 max(ann_date)=20260806 >= 20260731`
- 新鲜度判据:`停更:新鲜度 20260806 落后湖侧基准 20260901 共 26 天,event 节奏的容忍度是 14 天`(来源:live max(ann_date))
- 为什么是这一列:改名公告日 = 这条记录**何时可见**,是 PIT 正确的那一列;start_date/end_date 是改名生效区间,end_date 还有 4 成为空,不能当时间轴。
- 备注:⛔ 停更(体检判定):停更:新鲜度 20260806 落后湖侧基准 20260901 共 26 天,event 节奏的容忍度是 14 天。注意它 freeze_line_ok=True —— **过了冻结线不等于这张表还活着**(H6)。；ts_code 分区(5875 个),**不是时间分区** —— 它的'最新分区'是字典序最大的代码,与新鲜度无关,判新鲜度看视图的 ann_date。catalog 里另有派生视图 stock_name_pit 已把它与 stock_basic 拼成区间,卡 1.1 可直接对账。⛔ **停更**:max(ann_date) 停在 2026-08-06,此后再无新行。；⚠️ 分区间 schema 漂移:catalog 视图 9 列(全分区并集),抽样分区实际为 ts_code=000001.SZ=8列, ts_code=301380.SZ=8列, ts_code=920992.BJ=8列;视图有而抽样分区都没有的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。；分区键是 ts_code(实体码),'最新分区' ts_code=920992.BJ 只是字典序最大的代码,**不能当新鲜度**;新鲜度看 ann_date。

### `stock_st` —— 日频 ST / *ST 标记

- **哪张卡要用**:1.1, 1.2, 1.3, 3.2
- **为什么非它不可**:卡 1.1 的 ST 过滤;卡 1.2 状态字段;卡 3.2 的 S6 约束集(通常剔除 ST)。
- 冻结线判据:`现场 max(trade_date)=20260828 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260828 落后湖侧基准 20260901 共 4 天,trading_day 节奏的容忍度是 12 天`(来源:live max(trade_date))
- 为什么是这一列:逐日 ST 标记的所属交易日,唯一时间轴(月分区只是存储粒度)。
- 备注:gold 是 trade_month=YYYYMM 月分区(不是日分区),起点 201608,早于此无覆盖。**月分区但日频内容** —— 分区粒度别当成更新粒度。；⚠️ 分区间 schema 漂移:catalog 视图 9 列(全分区并集),抽样分区实际为 trade_month=201608=8列, trade_month=202108=8列, trade_month=202608=9列, trade_month=202607=8列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。

### `st_history` —— ST 事件历史(戴帽/摘帽的公告级记录)

- **哪张卡要用**:1.1
- **为什么非它不可**:卡 1.1 与 stock_st / namechange 三方交叉核对 ST 区间,给分歧清单当第三票。
- 冻结线判据:`现场 max(pub_date)=20260828 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260828 落后湖侧基准 20260901 共 4 天,event 节奏的容忍度是 14 天`(来源:live max(pub_date))
- 为什么是这一列:两个候选:pub_date(公告发布日)与 imp_date(实施日)。取 **pub_date** —— 实测 max(imp_date)=20260831 晚于 max(pub_date)=20260828,即实施日会**晚于**公告日,拿它当可见时间轴会漏未来信息。PIT 一律取可见日。
- 审计对账(as_of=20260831):{"date_column": {"audit": null, "registry": "pub_date", "why": "两个候选:pub_date(公告发布日)与 imp_date(实施日)。取 **pub_date** —— 实测 max(imp_date)=20260831 晚于 max(pub_date)=20260828,即实施日会**晚于**公告日,拿它当可见时间轴会漏未来信息。PIT 一律取可见日。"}}
- 备注:published_month 月分区(起点 202204),量很小(千级),只当交叉核对源,不当主源。⚠️ `coverage-audit` 把它记成 **date_column=null**,但表内 pub_date / imp_date 两列**全表非空**(实测 1227/1227)。审计那个 null 与它 data_time 的分区语义直接矛盾(卡 0.2 补救 D5),此处以**表内实测**为准。；审计(as_of=20260831)与现场重算有出入 ['date_column'] ——**以现场为准**,审计值见 audit_* 字段(H7:审计周末不跑,天然滞后 1-3 天)。

### `index_member_all` —— 申万行业成分区间(l1/l2/l3 + in_date/out_date)

- **哪张卡要用**:1.1, 2.1, 3.2
- **为什么非它不可**:卡 1.1 给每只票打 PIT 行业标签;卡 2.1 行业中性化因子必须的分组;卡 3.2 的 S5/S6 行业约束题面。
- 冻结线判据:`n/a:无日期列(区间表/元数据表),冻结线不适用`
- 新鲜度判据:`判不了:cadence=irregular(容忍度=None)、新鲜度日期=None、湖侧基准=20260901`(来源:无日期列且非 capture_time 分区 —— 新鲜度判不了)
- 为什么是这一列:区间表:in_date/out_date 是成分**进出**行业的两端,不是记录的可见时间轴。拿 max(in_date) 当新鲜度会把'最近有票换行业'误读成'表在更新'。
- 备注:❔ 新鲜度判不了:判不了:cadence=irregular(容忍度=None)、新鲜度日期=None、湖侧基准=20260901。；l3_code=8xxxxx.SI 分区(338 个),**不是时间分区**;本身是区间表(in_date/out_date),没有单一日期列,新鲜度看不出来,要看字段。登记为 update_cadence=irregular:停没停更**判不了**,基线里 stalled=null,**不许**因为判不了就默认它是活的。；分区键是 l3_code(实体码),'最新分区' l3_code=859951.SI 只是字典序最大的代码,**不能当新鲜度**;新鲜度看 表内字段区间。

### `income` —— 利润表(全量)

- **哪张卡要用**:1.3, 1.4, 2.1, 3.2, 5.1
- **为什么非它不可**:卡 1.3 的 /fundamentals(严格 PIT);卡 2.1 的盈利类因子;卡 3.2 的 S3/S4 题面;卡 5.1 前视探针的正例来源。
- 冻结线判据:`现场 max(ann_date)=20260804 >= 20260731`
- 新鲜度判据:`停更:新鲜度 20260804 落后湖侧基准 20260901 共 28 天,event 节奏的容忍度是 14 天`(来源:live max(ann_date))
- 为什么是这一列:与 audit / 其余报表口径一致,便于跨表对账。⚠️ 取数做严格 PIT 时用 **f_ann_date**(实际公告日,实测最早到 20070112,早于 ann_date 的 20080102);此处 date_column 只用于体检新鲜度,不是取数口径。
- 备注:⛔ 停更(体检判定):停更:新鲜度 20260804 落后湖侧基准 20260901 共 28 天,event 节奏的容忍度是 14 天。注意它 freeze_line_ok=True —— **过了冻结线不等于这张表还活着**(H6)。；有 ann_date + f_ann_date + end_date + end_type + update_flag,**可严格 PIT**(用 f_ann_date 而不是 ann_date);ts_code 分区,非时间分区。⛔ **停更**:max(ann_date) 停在 2026-08-04,而孪生表 income_vip 已到 08-29,**两者差 20 天以上**。取并集补历史时别把 income 当最新口径。；⚠️ 分区间 schema 漂移:catalog 视图 89 列(全分区并集),抽样分区实际为 ts_code=000001.SZ=89列, ts_code=301381.SZ=88列, ts_code=920992.BJ=88列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。；分区键是 ts_code(实体码),'最新分区' ts_code=920992.BJ 只是字典序最大的代码,**不能当新鲜度**;新鲜度看 ann_date。

### `income_vip` —— 利润表(vip 接口口径,end_date 分区)

- **哪张卡要用**:1.3, 1.4, 2.1
- **为什么非它不可**:与 income 同源不同抓取口径,卡 1.3/1.4 需要二者取并集补全历史,卡 2.1 交叉校验。
- 冻结线判据:`现场 max(ann_date)=20260829 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260829 落后湖侧基准 20260901 共 3 天,event 节奏的容忍度是 14 天`(来源:live max(ann_date))
- 为什么是这一列:与 income 同口径,便于孪生表逐日对账。
- 备注:end_date=YYYY-MM-DD 季度分区(70 个),覆盖 2009Q1→2026Q2;与 income 行数不同,不要假设互相包含。✅ 仍在更新(与已停更的 income 相反),是三大报表里的活口径。；⚠️ 分区间 schema 漂移:catalog 视图 89 列(全分区并集),抽样分区实际为 end_date=2009-03-31=88列, end_date=2017-12-31=88列, end_date=2026-06-30=89列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。

### `balancesheet` —— 资产负债表(全量)

- **哪张卡要用**:1.3, 1.4, 2.1, 3.2, 5.1
- **为什么非它不可**:同 income:估值/杠杆/资产类因子与 PIT 探针的输入。
- 冻结线判据:`现场 max(ann_date)=20260804 >= 20260731`
- 新鲜度判据:`停更:新鲜度 20260804 落后湖侧基准 20260901 共 28 天,event 节奏的容忍度是 14 天`(来源:live max(ann_date))
- 为什么是这一列:同 income。
- 备注:⛔ 停更(体检判定):停更:新鲜度 20260804 落后湖侧基准 20260901 共 28 天,event 节奏的容忍度是 14 天。注意它 freeze_line_ok=True —— **过了冻结线不等于这张表还活着**(H6)。；156 列;ts_code 分区,非时间分区。⛔ **停更**:max(ann_date) 停在 2026-08-04,孪生表 balancesheet_vip 已到 08-28。；⚠️ 分区间 schema 漂移:catalog 视图 156 列(全分区并集),抽样分区实际为 ts_code=000001.SZ=156列, ts_code=301381.SZ=155列, ts_code=920992.BJ=155列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。；分区键是 ts_code(实体码),'最新分区' ts_code=920992.BJ 只是字典序最大的代码,**不能当新鲜度**;新鲜度看 ann_date。

### `balancesheet_vip` —— 资产负债表(vip 口径)

- **哪张卡要用**:1.3, 1.4, 2.1
- **为什么非它不可**:与 balancesheet 取并集补历史 + 交叉校验。
- 冻结线判据:`现场 max(ann_date)=20260828 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260828 落后湖侧基准 20260901 共 4 天,event 节奏的容忍度是 14 天`(来源:live max(ann_date))
- 为什么是这一列:同 income。
- 备注:157 列(比 balancesheet 多一列),end_date 季度分区。✅ 仍在更新。；⚠️ 分区间 schema 漂移:catalog 视图 157 列(全分区并集),抽样分区实际为 end_date=2009-03-31=156列, end_date=2017-12-31=10列, end_date=2026-06-30=157列;抽样间就不一致的列 ['acc_exp', 'acc_receivable', 'accounts_pay', 'accounts_receiv', 'accounts_receiv_bill', 'acct_payable', 'acting_trading_sec', 'acting_uw_sec', 'adv_receipts', 'agency_bus_liab', 'amor_exp', 'bond_payable', 'cap_rese', 'cash_reser_cb', 'cb_borr', 'cip', 'cip_total', 'client_depos', 'client_prov', 'comm_payable', 'comp_type', 'const_materials', 'contract_assets', 'contract_liab', 'cost_fin_assets', 'debt_invest', 'decr_in_disbur', 'defer_inc_non_cur_liab', 'defer_tax_assets', 'defer_tax_liab', 'deferred_inc', 'depos', 'depos_ib_deposits', 'depos_in_oth_bfi', 'depos_oth_bfi', 'depos_received', 'deriv_assets', 'deriv_liab', 'div_payable', 'div_receiv', 'end_type', 'estimated_liab', 'fa_avail_for_sale', 'fair_value_fin_assets', 'fix_assets', 'fix_assets_total', 'fixed_assets_disp', 'forex_differ', 'goodwill', 'hfs_assets', 'hfs_sales', 'htm_invest', 'indem_payable', 'indep_acct_assets', 'indept_acc_liab', 'int_payable', 'int_receiv', 'intan_assets', 'inventories', 'invest_as_receiv', 'invest_loss_unconf', 'invest_real_estate', 'last_seen_at', 'lending_funds', 'loan_oth_bank', 'loanto_oth_bank_fi', 'long_pay_total', 'lt_amor_exp', 'lt_borr', 'lt_eqt_invest', 'lt_payable', 'lt_payroll_payable', 'lt_rec', 'minority_int', 'money_cap', 'nca_within_1y', 'non_cur_liab_due_1y', 'notes_payable', 'notes_receiv', 'oil_and_gas_assets', 'ordin_risk_reser', 'oth_assets', 'oth_comp_income', 'oth_cur_assets', 'oth_cur_liab', 'oth_debt_invest', 'oth_eqt_tools', 'oth_eqt_tools_p_shr', 'oth_liab', 'oth_nca', 'oth_ncl', 'oth_pay_total', 'oth_payable', 'oth_rcv_total', 'oth_receiv', 'payable_to_reinsurer', 'payables', 'payroll_payable', 'ph_invest', 'ph_pledge_loans', 'pledge_borr', 'policy_div_payable', 'prec_metals', 'prem_receiv_adva', 'premium_receiv', 'prepayment', 'produc_bio_assets', 'pur_resale_fa', 'r_and_d', 'refund_cap_depos', 'refund_depos', 'reinsur_receiv', 'reinsur_res_receiv', 'reser_lins_liab', 'reser_lthins_liab', 'reser_outstd_claims', 'reser_une_prem', 'rr_reins_lins_liab', 'rr_reins_lthins_liab', 'rr_reins_outstd_cla', 'rr_reins_une_prem', 'rsrv_insur_cont', 'sett_rsrv', 'sold_for_repur_fa', 'special_rese', 'specific_payables', 'st_bonds_payable', 'st_borr', 'st_fin_payable', 'surplus_rese', 'taxes_payable', 'time_deposits', 'total_assets', 'total_cur_assets', 'total_cur_liab', 'total_hldr_eqy_exc_min_int', 'total_hldr_eqy_inc_min_int', 'total_liab', 'total_liab_hldr_eqy', 'total_nca', 'total_ncl', 'total_share', 'trad_asset', 'trading_fl', 'transac_seat_fee', 'treasury_share', 'undistr_porfit']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。

### `cashflow` —— 现金流量表(全量)

- **哪张卡要用**:1.3, 1.4, 2.1, 3.2, 5.1
- **为什么非它不可**:同 income:现金流类因子与 PIT 探针的输入。
- 冻结线判据:`现场 max(ann_date)=20260804 >= 20260731`
- 新鲜度判据:`停更:新鲜度 20260804 落后湖侧基准 20260901 共 28 天,event 节奏的容忍度是 14 天`(来源:live max(ann_date))
- 为什么是这一列:同 income。
- 备注:⛔ 停更(体检判定):停更:新鲜度 20260804 落后湖侧基准 20260901 共 28 天,event 节奏的容忍度是 14 天。注意它 freeze_line_ok=True —— **过了冻结线不等于这张表还活着**(H6)。；101 列;ts_code 分区,非时间分区。⛔ **停更**:max(ann_date) 停在 2026-08-04,孪生表 cashflow_vip 已到 08-28。；⚠️ 分区间 schema 漂移:catalog 视图 101 列(全分区并集),抽样分区实际为 ts_code=000001.SZ=101列, ts_code=301381.SZ=100列, ts_code=920992.BJ=100列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。；分区键是 ts_code(实体码),'最新分区' ts_code=920992.BJ 只是字典序最大的代码,**不能当新鲜度**;新鲜度看 ann_date。

### `cashflow_vip` —— 现金流量表(vip 口径)

- **哪张卡要用**:1.3, 1.4, 2.1
- **为什么非它不可**:与 cashflow 取并集补历史 + 交叉校验。
- 冻结线判据:`现场 max(ann_date)=20260828 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260828 落后湖侧基准 20260901 共 4 天,event 节奏的容忍度是 14 天`(来源:live max(ann_date))
- 为什么是这一列:同 income。
- 备注:102 列;end_date 季度分区。✅ 仍在更新。；⚠️ 分区间 schema 漂移:catalog 视图 102 列(全分区并集),抽样分区实际为 end_date=2009-03-31=101列, end_date=2017-12-31=10列, end_date=2026-06-30=102列;抽样间就不一致的列 ['amort_intang_assets', 'beg_bal_cash', 'beg_bal_cash_equ', 'c_cash_equ_beg_period', 'c_cash_equ_end_period', 'c_disp_withdrwl_invest', 'c_fr_oth_operate_a', 'c_fr_sale_sg', 'c_inf_fr_operate_a', 'c_paid_for_taxes', 'c_paid_goods_s', 'c_paid_invest', 'c_paid_to_for_empl', 'c_pay_acq_const_fiolta', 'c_pay_claims_orig_inco', 'c_pay_dist_dpcp_int_exp', 'c_prepay_amt_borr', 'c_recp_borrow', 'c_recp_cap_contrib', 'c_recp_return_invest', 'comp_type', 'conv_copbonds_due_within_1y', 'conv_debt_into_cap', 'credit_impa_loss', 'decr_def_inc_tax_assets', 'decr_deferred_exp', 'decr_inventories', 'decr_oper_payable', 'depr_fa_coga_dpba', 'eff_fx_flu_cash', 'end_bal_cash', 'end_bal_cash_equ', 'end_type', 'fa_fnc_leases', 'finan_exp', 'free_cashflow', 'ifc_cash_incr', 'im_n_incr_cash_equ', 'im_net_cashflow_oper_act', 'incl_cash_rec_saims', 'incl_dvd_profit_paid_sc_ms', 'incr_acc_exp', 'incr_def_inc_tax_liab', 'incr_oper_payable', 'invest_loss', 'last_seen_at', 'loss_disp_fiolta', 'loss_fv_chg', 'loss_scr_fa', 'lt_amort_deferred_exp', 'n_cap_incr_repur', 'n_cash_flows_fnc_act', 'n_cashflow_act', 'n_cashflow_inv_act', 'n_depos_incr_fi', 'n_disp_subs_oth_biz', 'n_inc_borr_oth_fi', 'n_incr_cash_cash_equ', 'n_incr_clt_loan_adv', 'n_incr_dep_cbob', 'n_incr_disp_faas', 'n_incr_disp_tfa', 'n_incr_insured_dep', 'n_incr_loans_cb', 'n_incr_loans_oth_bank', 'n_incr_pledge_loan', 'n_recp_disp_fiolta', 'n_recp_disp_sobu', 'n_reinsur_prem', 'net_cash_rece_sec', 'net_dism_capital_add', 'net_profit', 'oth_cash_pay_oper_act', 'oth_cash_recp_ral_fnc_act', 'oth_cashpay_ral_fnc_act', 'oth_loss_asset', 'oth_pay_ral_inv_act', 'oth_recp_ral_inv_act', 'others', 'pay_comm_insur_plcy', 'pay_handling_chrg', 'prem_fr_orig_contr', 'proc_issue_bonds', 'prov_depr_assets', 'recp_tax_rends', 'st_cash_out_act', 'stot_cash_in_fnc_act', 'stot_cashout_fnc_act', 'stot_inflows_inv_act', 'stot_out_inv_act', 'uncon_invest_loss', 'use_right_asset_dep']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。

### `index_daily` —— 指数日线(基准收益)

- **哪张卡要用**:2.2, 3.2, 5.2
- **为什么非它不可**:卡 2.2 的 ε 标定需要基准;卡 3.2 的 S7 回测题面声明基准;卡 5.2 结算超额收益/IR 必须的对照。
- 冻结线判据:`现场 max(trade_date)=20260831 >= 20260731`
- 新鲜度判据:`仍在更新:新鲜度 20260831 落后湖侧基准 20260901 共 1 天,trading_day 节奏的容忍度是 12 天`(来源:live max(trade_date))
- 为什么是这一列:同 daily。
- 备注:与 daily 同为 trade_date 日分区;只覆盖少数几个指数,取用前先确认基准代码在表里。；⚠️ 分区间 schema 漂移:catalog 视图 14 列(全分区并集),抽样分区实际为 trade_date=2009-01-05=13列, trade_date=2017-11-01=13列, trade_date=2026-08-31=14列, trade_date=2026-07-31=13列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。

### `index_basic` —— 指数元数据(名称/基日/基点)

- **哪张卡要用**:1.1, 1.3
- **为什么非它不可**:卡 1.1/1.3 把 index_weight 与 index_daily 的指数代码解释成人读得懂的名字,并校验基准。
- 冻结线判据:`n/a:无日期列(区间表/元数据表),冻结线不适用`
- 新鲜度判据:`停更:新鲜度 20260806 落后湖侧基准 20260901 共 26 天,trading_day 节奏的容忍度是 12 天`(来源:latest_capture_partition(snapshot_date))
- 为什么是这一列:base_date(指数基日,max 20100531)/ list_date(发布日)是**指数自身的属性**,与'这张表抄到哪天'无关;exp_date 8 行全空。新鲜度只能看 snapshot_date。
- 备注:⛔ 停更(体检判定):停更:新鲜度 20260806 落后湖侧基准 20260901 共 26 天,trading_day 节奏的容忍度是 12 天。注意它 freeze_line_ok=None —— **过了冻结线不等于这张表还活着**(H6)。；**只有 8 行**,snapshot_date 分区且只有 2 个快照;无日期列。当元数据用,不当行情用。⛔ **停更**:两个快照是 2026-08-05 / 2026-08-06,此后再没抄过。同为 capture_time 的 stock_basic 每个交易日都在刷新 —— 这张没有,是真停了。；⚠️ 分区间 schema 漂移:catalog 视图 16 列(全分区并集),抽样分区实际为 snapshot_date=2026-08-05=15列, snapshot_date=2026-08-06=16列;抽样间就不一致的列 ['last_seen_at']。按视图列清单写取数代码会要到取不到的列;跨分区读**必须** union_by_name=True(关掉是**静默丢列**,不是报错)。；分区键是 snapshot_date(**抓取时间**,不是数据时间):快照 snapshot_date=2026-08-05 → snapshot_date=2026-08-06 **全部晚于冻结线 2026-07-31**,冻结窗口内根本没有快照可选。这不是数据缺口 —— 这类表的 PIT 语义在**字段**上(list_date/delist_date/cal_date),网关必须走字段回溯而不是选快照。；多快照表:跨快照重复主键 1 行(同一 code 在多个 snapshot 里各有一行,取数必须先选定快照)。

### `dividend` —— 分红送转事件(拆分/送股的原始记录)

- **哪张卡要用**:5.1, 2.1
- **为什么非它不可**:卡 5.1 明确要求'用湖内**已知拆分事件**构造复权指纹样本' —— 样本就来自这张表;卡 2.1 校验 adj_factor 的跳变点。
- 冻结线判据:`现场 max(ann_date)=20260801 >= 20260731`
- 新鲜度判据:`停更:新鲜度 20260801 落后湖侧基准 20260901 共 31 天,event 节奏的容忍度是 14 天`(来源:live max(ann_date))
- 为什么是这一列:预案公告日 = 事件**何时可见**。record_date/ex_date/pay_date/imp_ann_date 都只有三成填充率(57k/177k),且 ex_date 是**除权日**属于未来信息,拿它当时间轴会前视。
- 备注:⛔ 停更(体检判定):停更:新鲜度 20260801 落后湖侧基准 20260901 共 31 天,event 节奏的容忍度是 14 天。注意它 freeze_line_ok=True —— **过了冻结线不等于这张表还活着**(H6)。；ts_code 分区,非时间分区;ann_date 最早到 1991,注意早期数据质量。⛔ **停更**:max(ann_date) 停在 2026-08-01,是 v1 清单里滞后最久的一张。⚠️ ann_date 还有约 6000 行为空(171879/177858 非空),卡 5.1 用它构造拆分事件样本时要先过滤。；分区键是 ts_code(实体码),'最新分区' ts_code=920992.BJ 只是字典序最大的代码,**不能当新鲜度**;新鲜度看 ann_date。

### `limit_list_d` —— 涨跌停/炸板榜(触板结果的第三方口径)

- **哪张卡要用**:1.2
- **为什么非它不可**:卡 1.2 验收要求人工核对触板判定 —— 这张表是湖内可用的独立对照口径,省掉一半人工。
- 冻结线判据:`现场 max(trade_date)=20260805 >= 20260731`
- 新鲜度判据:`停更:新鲜度 20260805 落后湖侧基准 20260901 共 27 天,trading_day 节奏的容忍度是 12 天`(来源:live max(trade_date))
- 为什么是这一列:同 daily。
- 备注:⛔ 停更(体检判定):停更:新鲜度 20260805 落后湖侧基准 20260901 共 27 天,trading_day 节奏的容忍度是 12 天。注意它 freeze_line_ok=True —— **过了冻结线不等于这张表还活着**(H6)。；**只覆盖 20200102 起**,冻结线内可用但历史不全;只当交叉核对源,触板主判据仍是 daily 比价 stk_limit。⛔ **停更**:gold 分区**硬停在 trade_date=2026-08-05**,而 daily 在其后还有 17 个交易日分区(→2026-08-28)。它照样'过冻结线'(20260805 > 20260731),所以在只看冻结线的基线里是一片绿 —— 卡 1.3 的网关**不能**拿它判新鲜度。对 v1 的 ≤2026-07-31 窗口不构成数据缺口。

## 明确不进 v1 的表

- **`stk_factor_pro`** —— 带 bfq/hfq/qfq 三价口径。实施稿卡 1.3 定死:v1 数据面统一走 adj_factor,三价口径不进网关 —— 2026-08 起两套口径不同步,放进来等于给被测 agent 两个互相矛盾的复权答案。 _(重议时机:v1.1 若要做口径一致性题材,再单独评估。)_
- **`fina_indicator`** —— **只有 ann_date,无 f_ann_date**,做不了严格 PIT;放进网关会直接漏未来信息。 _(重议时机:v1.1 定降级规则(如统一延后 N 日可见)后再进。)_
- **`fina_indicator_vip`** —— 同 fina_indicator,缺 f_ann_date。 _(重议时机:同上。)_
- **`minute_1m / index_minute_1m / cn_minute_bar`** —— v1 **全日频**(实施稿 D3)。分钟线还卡在 NFS 桥(W1),v1 不需要。 _(重议时机:Live 赛道。)_
- **`moneyflow / margin / hk_hold 等另类数据`** —— v1 主实验一充分集只覆盖量价+基本面+宇宙+日历,不扩面。 _(重议时机:v1.1 扩量(卡 3.3)时按题材需要逐张登记。)_

## catalog 里的派生视图(不是数据源,但好用)

- **`stock_name_pit`**(由 namechange UNION ALL stock_basic 拼出)—— 已经把证券简称拼成 (ts_code, name, start_date, end_date) 区间,end_date 缺失填 99991231。卡 1.1 判 ST 前缀可直接对账,不必自己拼。
- **`limit_list_ths_enriched`**(由 limit_list_ths + 衍生字段 拼出)—— 卡 1.2 触板核对的又一路第三方口径(同花顺),优先级低于 limit_list_d。
