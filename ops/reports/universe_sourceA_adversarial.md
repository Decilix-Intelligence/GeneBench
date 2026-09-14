# 卡 1.1 源A 对抗审查：`index_weight` 月末快照 diff → 成分区间

- **审查对象**：`repo/snapshots/universe_index_weight.py` / `repo/ops/universe_source_A.json` /
  `$GENEBENCH_ROOT/snapshots/v1/universe/index_weight_intervals.parquet`（sha256 `e1ff463d…d47a5`，6729 行）
- **审查立场**：证伪。默认它有问题，逐条去撞。不复核"算得对不对"，只找"约定错在哪、下游会被它坑在哪"。
- **审查方式**：不读它的自测，全部从湖里重新拉数独立重建，再与产物对账。
- **裁决**：**FAIL**。核心区间表（`in_date` / `out_date` / `segment_idx` / 截断标记）经四轮独立验证**无缺陷**；
  但产物 14 列里有 **2 列布尔标记在其为 True 的全部 20 行上都是错的**，摘要 JSON 里有一条**错误的 `FAIL` 判定**，
  文档里有一条**被自家数据证伪的不变量**，还有一条**会让卡 1.2 产生 245 条假警报的预判**。这些都在已交付物里，不是假设。

## 环境与复现前提

```bash
ssh -o ConnectTimeout=60 -o ServerAliveInterval=15 -o BatchMode=yes ljn@finance01.tail642a54.ts.net
cd /data/shared/genebench/repo && ulimit -n 8192
PY=/data/shared/genebench/env/bin/python     # 隔离环境解释器
```

本报告全部探针脚本在 `ops/reports/adv_sourceA/adv_a{1..7}.py`，均为只读（`lake.catalog()` → `read_only=True`），
不写湖、不写产物。原始输出留在 `$GENEBENCH_ROOT/adv_a/out{1..5}.json`。

```bash
$PY ops/reports/adv_sourceA/adv_a1.py   # 类型 / 无损还原 / LOCF / 每期成分数
$PY ops/reports/adv_sourceA/adv_a2.py   # 独立重建逐行对账 / 截断 / 多段 / 停牌
$PY ops/reports/adv_sourceA/adv_a3.py   # 退市取证 / 缺口成因 / 第三方源 / qlib
$PY ops/reports/adv_sourceA/adv_a4.py   # 界外行为 / 裸 gold 对账 / weight 反事实 / 复现性
$PY ops/reports/adv_sourceA/adv_a5.py   # DATE-VARCHAR 陷阱实证 / 停牌掉出去向 / 出场滞后
$PY ops/reports/adv_sourceA/adv_a6.py   # 出场负滞后成因
$PY ops/reports/adv_sourceA/adv_a7.py   # D1 补证：entry 标记的必要条件 / suspend_d 覆盖率
```

---

# 一、问题清单（按会不会传染到下游排序）

## D1 【高】`entry_gap_suspect` / `exit_gap_suspect` 两列的精度是 **0 / 20**，全部是假阳性

产物里这两列一共标了 20 行 True（18 entry + 2 exit），**全部**挂在 csi300 的 20091231 这一期上。
模块的解释是"该期成分数缺额 298，紧邻它的段边界可能是数据漏行造成的假调仓"。**这个前提是错的。**

**取证 1 —— 缺的那两只是真退市，不是漏行。**

```bash
$PY - <<'EOF'
import sys; sys.path.insert(0,'/data/shared/genebench/repo')
from snapshots import lake
with lake.catalog() as c:
    print(lake.query("SELECT ts_code,name,list_status,delist_date FROM stock_basic "
                     "WHERE ts_code IN ('600001.SH','600357.SH')", conn=c))
    print(lake.query("SELECT ts_code,max(trade_date) last_bar FROM daily "
                     "WHERE ts_code IN ('600001.SH','600357.SH') GROUP BY 1", conn=c))
EOF
```

实测输出：

```
     ts_code        name list_status delist_date
0  600001.SH  邯郸钢铁(退)           D    20091229
1  600357.SH  承德钒钛(退)           D    20091229
     ts_code  last_bar
0  600001.SH  20091215
1  600357.SH  20091215
```

两只都在 **20091229 退市**（同日）、最后一根 K 线同为 20091215 —— 同一次吸收合并的两个标的。
20091231 那期名单里没有它们，是因为它们已经不存在了，不是因为行丢了。

**取证 2 —— 权重和证明没有行丢失。**

```bash
$PY ops/reports/adv_sourceA/adv_a1.py | python3 -c "import json,sys; d=json.load(sys.stdin); \
print(d['per_period']['csi300']['off_size']); print(d['per_period']['csi300']['weight_sum_min5'][:2], \
d['per_period']['csi300']['weight_sum_max5'][-2:])"
```

实测：`off_size = [{'date':'20091231','n':298,'nominal':300,'sum_weight':99.993}]`；
csi300 全部 211 期的权重和落在 **[99.90, 100.11]**。20091231 的 99.993 稳稳在带内。
若真漏了 2 行，权重和应当少掉 0.1~0.6（这两只当时的权重量级）。**没有少。**

**取证 3 —— 18 个 entry 标记，没有一个满足"漏行"假设的必要条件。**

18 行全部是 `in_date=20100129, prev_snapshot=20091231`，也就是 2010 年 1 月那次正常调入的整份名单被无差别染红。
"它其实在 20091231 的名单里、只是行丢了"这个假设的必要条件是**它在 20091130 那期在成分内**。

```bash
$PY ops/reports/adv_sourceA/adv_a7.py | python3 -c "import json,sys;d=json.load(sys.stdin)['entry_flag_codes_history'];\
print('n_codes',len(d));print('20091130 在成分内的',sum(1 for v in d.values() if v['in_20091130']))"
```

实测：`n_codes 18` / **`20091130 在成分内的 = 0`**。18 只里 17 只在 20091231 之前**从未**进过 csi300，
剩下 1 只（600062.SH）上次在册停在 20090630。其中 `601668.SH` 中国建筑（`list_date=20090729`）与
`601618.SH` 中国中冶（`list_date=20090921`）更是 2009 年才上市的新股 —— 从 stock_basic 直接可查。

讽刺的是，模块自己的 `_missing_row_suspects()` 做的正是这个判据（"前一期在、后一期也在、偏偏这期不在"），
返回的是**空**；`off_size_detail[...].came_back_next_period` 也是**空**。
证据全在摘要里，只是标记的定义与它要检验的假设**完全脱钩**了。

**影响**：卡 1.2 做 A↔B 对账时若按 `entry_gap_suspect` 剔除"可疑段"，会一次丢掉 18 段真实区间，
含中国建筑、中国中冶从 2010 一直到冻结线的**全部持有期**（这两段 `out_date` 都是 NULL，即至今仍在成分内）。

**修法**：
1. 判缺额期成因时增加两个判别量：`sum(weight)` 是否仍≈100，缺席票的 `stock_basic.delist_date`
   是否落在 `(prev_snapshot, trade_date]` 内。两者都满足 → 归类为 `index_vacancy`（指数真空缺），**不打 suspect**。
2. `entry_gap_suspect` 的定义收窄成"该 code 在 `prev_snapshot` 的**上一期**在成分内"
   （只标真正"前在–中缺–后在"的形状）。当前定义把缺额期之后整份调入名单都染红，
   在本数据上把 2 个可能的目标扩大成了 18 个。
3. 在把这两列改对之前，产物的这两列不应当被任何下游当过滤条件用；建议先在 `COLUMN_DOC` 里写明
   "当前实现为整期染色，精度未验证"。

## D2 【高】摘要 JSON 把一次公司行为判成 `verdict: "FAIL"`

```bash
python3 -c "import json;d=json.load(open('/data/shared/genebench/repo/ops/universe_source_A.json'));\
print({k:v['verdict'] for k,v in d['integrity']['nominal_size_check'].items()})"
```

实测：`{'csi300': 'FAIL', 'csi500': 'PASS', 'csi1000': 'PASS'}`

这是整份摘要里唯一的 FAIL。任何读摘要的人或自动门禁都会认为源A 的 csi300 有数据缺陷。
按 D1 的取证，实际原因是指数在合并退市后短暂空缺 2 席，属正常。

**修法**：verdict 改三态 —— `PASS` / `VACANCY_EXPLAINED`（缺额已由退市解释）/ `FAIL`（无法解释）；
并把 `sum_weight`、缺席票的 `delist_date` 一并写进 `off_size_periods` 的每一条，让人不用回头查湖就能判。

## D3 【高】产物在冻结线之外**静默**返回满额宇宙

`out_date IS NULL` 表示"区间开口"（这个约定本身是对的，见第二节 V2）。代价是任何按
`in_date <= D AND (out_date IS NULL OR D <= out_date)` 过滤的下游，把 D 取到冻结线之外时不会报错。

```bash
$PY - <<'EOF'
import sys; sys.path.insert(0,'/data/shared/genebench/repo')
import pandas as pd, genebench_config as cfg
pq = pd.read_parquet(cfg.UNIVERSE_INTERVALS_PARQUET); s = pq[pq.universe=='csi300']
for d in ('20090105','20090122','20260731','20270101','29991231'):
    print(d, int(((s.in_date<=d) & (s.out_date.isna() | (s.out_date>=d))).sum()))
EOF
```

实测输出：

```
20090105 0
20090122 0
20260731 300
20270101 300
29991231 300
```

红线 7 说 v1 一切查询/快照上界不得超过 2026-07-31。模块的**查询**守住了（`WHERE trade_date <= ?`），
但**产物**没带这个上界：查 2027 年、查公元 2999 年，都安静地给你 2026-07-31 那份名单。
反方向同样安静：查首期之前（20090105）返回**空集**，也不报错。

另外 parquet 的 key-value metadata 里只有 `pandas` 一项，没有任何 `valid_from` / `valid_to`：

```bash
$PY -c "import sys;sys.path.insert(0,'/data/shared/genebench/repo');import genebench_config as cfg,pyarrow.parquet as p;\
print(list((p.ParquetFile(cfg.UNIVERSE_INTERVALS_PARQUET).schema_arrow.metadata or {}).keys()))"
# 实测: [b'pandas']
```

**修法**：往 parquet 的 schema metadata 写 `valid_from` / `valid_to=20260731` / `freeze_line` / `source_view`；
并在 repo 里提供唯一的读取入口 `universe_at(universe, D)`，D 超出 `[valid_from, valid_to]` 时抛错，
而不是返回空集或满额。摘要 JSON 里的 `date_coverage` 只在 JSON 里，parquet 单独流转时带不走。

## D4 【中】文档自称的不变量被自家数据证伪

模块 docstring 1.1 节：「…也让每个交易日的宇宙规模恒等于名义值 300/500/1000，而不是在月中缩水。」

```bash
$PY ops/reports/adv_sourceA/adv_a1.py | python3 -c "import json,sys;d=json.load(sys.stdin);\
print({u:v['size_histogram'] for u,v in d['locf_equivalence'].items()})"
```

实测（在**每一个**交易日上展开区间后数宇宙规模）：

```
csi300  {298: 20, 300: 4235}     # 20091231 ~ 20100128 这 20 个交易日是 298
csi500  {500: 4255}
csi1000 {1000: 2857}
```

绝对句式 + 紧跟"而不是在月中缩水"，读者会当成不变量去依赖（例如下游写 `assert len(univ)==300`）。

**修法**：改成「除 20091231→20100128 这 20 个交易日为 298（合并退市留下的 2 席空缺）之外恒等于名义值」，
并把这句话落成 `ops/test_universe_source_a.py` 里一条真正跑得起来的断言（允许一个白名单区间），
而不是只写在注释里。

## D5 【中】给卡 1.2 的预判 `out_date_A >= end_B` 按字面执行会产生 **245 条假"真矛盾"**

docstring 第三节写道：「出场侧 `out_date_A >= end_B`」，且「方向反了的不是精度问题，是真矛盾，必须逐条查」。

```bash
$PY ops/reports/adv_sourceA/adv_a6.py
```

实测（`out_date_A − end_B`，自然日；只算非右截断段）：

```
csi300  {-2: 35,  0: 505,  2: 2,  25: 43, 27: 39, 28: 23, 29: 36, 30: 40}
csi500  {-2: 101, 0: 1411, 21: 1, 25: 101, 28: 51, 29: 51, 30: 50}
csi1000 {-2: 109, 0: 2240}
n_negative_where_qlib_end_is_a_trading_day = 0 / 0 / 0
```

**全部 245 条负值都恰好是 −2，且 qlib 的 `end` 无一是交易日**（全部落在周末）。
这正是模块自己第三节写明的「qlib 用自然日，我们用前一个**交易日**」的必然产物，不是矛盾。
但预判里把它定义成必须逐条查的"真矛盾"，卡 1.2 会被这 245 条淹掉。

**修法**：预判改写成 `out_date_A >= prev_trading_day(end_B + 1 天)`（即先把 B 的自然日端点取整到交易日网格），
或退一步给 ±2 自然日容差；并在 `qlib_alignment.expected_direction_for_card_1_2` 里直接把这 245 条的
成因和数量写进去，省下游一次踩坑。

## D6 【中】「真正的下界要靠源B 补」对 csi1000 不成立，conventions 块没写例外

```bash
$PY ops/reports/adv_sourceA/adv_a3.py | python3 -c "import json,sys;d=json.load(sys.stdin);\
print({u:v['left_censor_magnitude'] for u,v in d['qlib_month_internal'].items()})"
```

实测：

| 宇宙 | 首期成员 | qlib 能回溯到更早的 | 可回溯天数 p50 / max |
|---|---|---|---|
| csi300 | 300 | **300**（100%） | 1386 / 1386 |
| csi500 | 500 | 466（93.2%） | 723 / 723 |
| csi1000 | 1000 | **0**（0%） | — / — |

`conventions.left_censored` 那句「真正的下界靠源B 回溯」对 csi1000 是空头支票 —— 源B 首日与源A 首期
同为 20141031（正文第三节提到了同日，但 conventions 块没写，而下游读的是 conventions）。

顺带：csi300 的 p50 == max == 1386 天，说明这 300 只**全部撞到了 qlib 自己的左边界 2005-04-08**
—— 1386 天只是**下界**，真实在册时长被低估得更多。摘要里应当把这一点写明，否则下游会把 1386 当成实数。

## D7 【低】YYYYMMDD 字符串约定只靠 catalog view 的隐式规范化，没有断言

题目问「有没有字符串与日期混比导致的**静默**错误」。答案：**本模块内没有静默错误**，但地雷是真的埋着。

```bash
$PY ops/reports/adv_sourceA/adv_a5.py | python3 -c "import json,sys;print(json.dumps(json.load(sys.stdin)['type_trap'],ensure_ascii=False,indent=1))"
```

实测：**同一份 gold 数据，两条访问路径给出两种类型**

| 访问路径 | `trade_date` 类型 | 取值形态 |
|---|---|---|
| `catalog` 的 `index_weight` view（模块用的） | `VARCHAR` | `20090123` |
| `read_parquet(gold/index_weight/*/*.parquet)` | `DATE` | `2009-01-23` |

而且 `hive_partition_only = false` —— gold parquet **文件内部**的 `trade_date` 列本身就是 DATE，
不只是分区目录名。于是：

```
WHERE trade_date <= '20260731'   打在裸 gold 上 → ConversionException: invalid date field format: "20260731"
CAST('20260731' AS DATE)                        → ConversionException（同上）
WHERE trade_date <= '2026-07-31' 打在裸 gold 上 → 310798 行（正确）
```

**好消息**：混比会**大声报错**，不会静默。即使有人绕过异常，`previous_trading_day_map()` 也会因为
"快照日 `2009-01-23` 不在 trade_cal 里"而抛 `LakeError`。这是模块设计得对的地方。

**坏消息**：`AGENT_CONTEXT.md` 恰恰把 `read_parquet('<gold>/<ds>/…')` 推荐为 "Too many open files" 的绕法。
下一个照着绕的人拿到的是 DATE，而模块通篇按 8 位字符串做字典键和大小比较，没有一条断言守住这个前提。

**修法**：在 `load_snapshots()` 开头加两行廉价断言 —— `SELECT typeof(trade_date) FROM index_weight LIMIT 1`
必须是 `VARCHAR`，且 `min(trade_date)` 长度必须是 8。失败就抛 `LakeError` 说明"视图口径变了，
本模块的 YYYYMMDD 字符串约定失效"。

## D8 【低】冻结线过滤当前是无操作，且没有负控

```bash
$PY -c "import sys;sys.path.insert(0,'/data/shared/genebench/repo');from snapshots import lake;\
print(lake.query('SELECT count(*) n FROM index_weight WHERE trade_date > ?',[lake.FREEZE_DATE_COMPACT]))"
# 实测: n = 0
```

湖里的 `index_weight` 本身已经冻在 20260731，所以 `WHERE trade_date <= ?` 这条红线 7 的防线
**从未真正生效过一次**。将来湖前进时若这行被误删或写错，没有任何测试会变红。

**修法**：加一条负控 —— 构造一张含 20260801 行的内存表喂给 `build_intervals()` 的上游过滤逻辑，
断言那一期不出现在 `dates_by_universe` 里。

## D9 【低】`_dist()` 的四分位在零变动期占多数时是误导数

摘要里 csi300 的 `adds` 分布是 `p25 = median = p75 = 0`（210 个转移里 168 个零变动），
读起来像"这个指数不换手"，实际 `mean = 3.448`、`max = 30`（= 10% 的调仓上限）。
不是计算错误，是可读性问题。**修法**：补 `p95` 或"仅非零期"的条件分布。

---

# 二、验过、确实找不到问题的项目（附验法与实测数）

以下每一项都是**独立重建后对账**的结果，不是采信摘要。

## V1 无损还原（题目第 1 项）—— PASS

把产物区间展开回逐期成员集合，与原始 `index_weight` 月末快照**逐期逐票**对比。

```bash
$PY ops/reports/adv_sourceA/adv_a1.py | python3 -c "import json,sys;d=json.load(sys.stdin);\
print(json.dumps(d['roundtrip_snapshot_dates'],ensure_ascii=False))"
```

实测：

| 宇宙 | 期数 | 对不上的期数 | 少的票 | 多的票 |
|---|---|---|---|---|
| csi300 | 211 | **0** | **0** | **0** |
| csi500 | 211 | **0** | **0** | **0** |
| csi1000 | 142 | **0** | **0** | **0** |

再加严一档：不只在快照日，而是在**每一个交易日**上比 LOCF（"不晚于 D 的最后一期快照的名单"）：

```
csi300  4255 个交易日, 有差异的 0 天
csi500  4255 个交易日, 有差异的 0 天
csi1000 2857 个交易日, 有差异的 0 天
```

**结论**：`in_date` / `out_date` 的闭区间约定自洽，`out_date = prev_trading_day(T_{j+1})` **没有 off-by-one**。
区间表与快照序列信息等价，可无损互推。这一项撞不动。

## V2 左右截断（题目第 2 项）—— PASS

题目怀疑「第一期出现的票是否被错误地标成 `in_date=首期` 而不是左截断」。实测：**两者都做了**
—— `in_date` 填首期**且** `left_censored=True`，不是二选一。

```bash
$PY ops/reports/adv_sourceA/adv_a2.py | python3 -c "import json,sys;print(json.dumps(json.load(sys.stdin)['censoring'],ensure_ascii=False,indent=1))"
```

实测（三宇宙全部）：

| 一致性检查 | csi300 | csi500 | csi1000 |
|---|---|---|---|
| `left_censored` ⟺ `in_date == 首期` 的违例 | 0 | 0 | 0 |
| `left_censored` 段的 `segment_idx != 0` 的违例 | 0 | 0 | 0 |
| `right_censored` ⟺ `out_date IS NULL` 的违例 | 0 | 0 | 0 |
| `right_censored` ⟺ `last_seen == 20260731` 的违例 | 0 | 0 | 0 |
| 左截断计数 / 首期成员数 | 300 / 300 | 500 / 500 | 1000 / 1000 |
| 右截断计数 / 末期成员数 | 300 / 300 | 500 / 500 | 1000 / 1000 |

`out_date` 为 NULL 的行数 = 1800 = 300+500+1000，与 `prev_snapshot` / `next_snapshot` 的 NULL 数一致。
末期仍在成分里的票 `out_date` 确实是 NULL，**没有**被写成 20260731。这一项也撞不动。

## V3 多段进出（题目第 3 项）—— PASS

不信摘要，从原始 `index_weight` 独立做游程编码（期序号连续 = 一段），逐 code 与产物比段数。

```bash
$PY ops/reports/adv_sourceA/adv_a2.py | python3 -c "import json,sys;d=json.load(sys.stdin);\
print({u:{k:v[k] for k in ('n_codes','n_codes_multi','max_runs','segment_count_mismatches')} for u,v in d['multi_segment'].items()})"
```

实测：

| 宇宙 | 去重 code | 多段 code | 最多段数 | **段数不符的 code** |
|---|---|---|---|---|
| csi300 | 825 | 166 | 5 | **0** |
| csi500 | 1706 | 466 | 5 | **0** |
| csi1000 | 2839 | 547 | 4 | **0** |

自己从数据里挖出来的真实多次进出实例（原始在册期次 → 产物分段），逐段核对无误：

- **601991.SH 大唐发电（csi300，5 段）**
  `[20090123, 20110128] [20120131, 20130130] [20130731, 20141230] [20150630, 20161229] [20171229, 20190627]`
  原始名单里它在 2011 全年、2013 上半年、2015 上半年、2017 前 11 个月确实缺席，段没有被合并。
- **600027.SH 华电国际（csi300，4 段）** 末段 `in_date=20240628, out_date=NULL`，右截断正确。
- **002032.SZ 苏泊尔（csi500，5 段）** 跨 2009/2014/2017/2023/2025 五次进出，末段右截断。
- **000048.SZ（csi1000，3 段）** 首段只有 2 期（20141031、20141128）且 `left_censored=True`。

再验段与段之间的结构约束（全 6729 行）：

```
overlap（前段 out_date >= 后段 in_date）        : 0
non_monotonic                                   : 0
adjacent_no_real_gap（相邻两段之间没有真缺口）  : 0
outdate_le_indate                               : 0
```

**结论**：多段没有被合并成一段，段边界也没有粘连。

## V4 每期成分数（题目第 4 项）—— 唯一偏差是**数据源的真实空缺**，不是代码问题

- csi500 全部 211 期恰好 500，csi1000 全部 142 期恰好 1000。
- csi300 210/211 期恰好 300，唯一例外 20091231 = 298。
- 举证见 D1：两只缺席票 `delist_date=20091229`、最后 K 线 20091215、该期权重和 99.993（正常带 [99.90, 100.11]）。
  **是指数真空缺，不是漏行，也不是代码丢数。**
- 顺带验了三条可能的代码侧成因，全部排除：
  - 快照日不是交易日？→ 三宇宙 `snapshot_not_trading_day` 全为空。
  - 快照日不是当月最后一个交易日？→ 三宇宙 `snapshot_not_month_last_trading_day` 全为空。
  - 整月缺失导致假断段？→ `n_distinct_months == n_periods`（211/211/142），月序列连续无洞。
- 视图有没有丢数/重数？绕开 catalog 直接读裸 gold 对账：

```bash
$PY ops/reports/adv_sourceA/adv_a4.py | python3 -c "import json,sys;d=json.load(sys.stdin);\
print(d['gold_raw_vs_view'], 'dupes=', d['gold_dupes'])"
# 实测: 裸 gold 310798 行 / view 310798 行 / match=True; (index_code,trade_date) 内重复 con_code = 0
```

`310798 = 211×300 − 2 + 211×500 + 142×1000`，逐项对得上。

## V5 weight 未被误用（题目第 5 项）—— PASS

- 源码层：`load_snapshots()` 的 SQL 是 `SELECT index_code, con_code, trade_date`，**weight 根本没被选出来**，
  全文件也没有任何 weight 阈值分支（`grep -n weight snapshots/universe_index_weight.py` 只命中注释与文档字符串）。
- 行为层：我的独立重建同样忽略 weight，与产物**逐行逐列一致**（见 V7），说明 weight 确实没有进入判定路径。
- 反事实量化（说明"风险面存在但没被踩"）：

```bash
$PY ops/reports/adv_sourceA/adv_a4.py | python3 -c "import json,sys;print(json.load(sys.stdin)['weight_counterfactual'])"
```

```
min(weight) = 0.007
weight < 0.01 : 43 行
weight < 0.02 : 1258 行
weight < 0.05 : 24954 行（占全表 8.03%）
NULL = 0, 零值 = 0, 负值 = 0
```

也就是说，只要有人手滑加一条 `weight >= 0.05`，就会静默抹掉 8% 的成员日。当前没有。

## V6 停牌 / 退市（题目第 6 项）—— PASS，且量化了

问题是"成分股当期停牌，`index_weight` 里还有没有它？会不会被误判为退出"。分两个角度撞。

**角度一：停牌当期还在不在名单里 / 下一期会不会掉。**
（湖里停牌是 `daily` 缺行，不是显式标记，所以判据是"成分股在快照日没有 daily 行"，再用 `suspend_d` 交叉确认：
实测 1309 个样本的 `suspend_type` 分布是 `{'S': 1309}` —— **100% 有停牌记录，零个例外**，判据成立。）

```bash
$PY ops/reports/adv_sourceA/adv_a2.py | python3 -c "import json,sys;d=json.load(sys.stdin)['suspended_members_csi300'];\
print({k:v for k,v in d.items() if k not in ('dropped_detail','examples')})"
```

实测（csi300，211 期）：

```
成分股当期无 daily 行的样本数 : 1309   （suspend_d 里 1309/1309 标 S）
其中下一期仍在名单里          : 1275   （97.4%）
其中下一期消失                : 34     （2.6%）
```

**`index_weight` 保留停牌成分股**，停牌本身不会把票踢出名单。

**角度二：那 34 个消失的，是不是"停牌→假退出→复牌再回来"？**

```bash
$PY ops/reports/adv_sourceA/adv_a5.py | python3 -c "import json,sys;d=json.load(sys.stdin)['suspended_then_dropped_fate'];\
print({k:v for k,v in d.items() if k!='detail'})"
```

```
n = 34
1 期内回归 : 0
6 期内回归 : 1
再也没回来 : 25   （其中 12 只 list_status='D' 已退市：*ST上航、莱钢股份、美的电器、退吉恩、
                    宏源证券、东方明珠、武钢股份、乐视退、*ST信威、*ST中天、海通证券、中国重工）
```

**没有任何一例是"停 1 个月、掉一期、再回来"**。回归的那几只间隔 6~71 期（如中国东航 18 期、
首钢股份 71 期），是正常的调出再调入。

**角度三：从区间侧反查 —— 有没有哪个成员缺口其实是长停牌？**

```bash
$PY ops/reports/adv_sourceA/adv_a4.py | python3 -c "import json,sys;d=json.load(sys.stdin)['gap_trading_coverage'];\
print({k:v for k,v in d.items() if k!='worst'})"
```

三宇宙一共 1359 个成员缺口，统计"缺口内该票有行情的交易日占比"：

```
min = 0.389,  p05 = 0.803,  p50 = 0.999
占比 = 0 的缺口数 : 0        ← 没有任何一个缺口是"全程停牌"
占比 < 0.5 的缺口 : 5        （最低 002075.SZ 沙钢股份 0.389，缺口横跨 54 期；名称取自 stock_basic）
```

**结论**：三个角度都指向同一件事 —— 在本数据上，"停牌被误判为退出"**不成立**。
（这条不能推广到别的数据源；换源必须重跑角度三。）

## V7 复现性与产物卫生 —— PASS

```bash
$PY ops/reports/adv_sourceA/adv_a4.py | python3 -c "import json,sys;print(json.load(sys.stdin)['reproducibility'])"
```

- 重跑 `build()`：6729 行，与磁盘 parquet **逐值一致**（`values_identical = True`）。
- 磁盘 sha256 `e1ff463d3b08e5fd9c62f845f5c3dc99158f21fbf4169f9a634ebd9e170d47a5`，与摘要 JSON 里记录的一致。
- 另做了一次完全脱离本模块的重建（`adv_a2.py` 用自己的游程编码 + 自己的前一交易日表）：
  6729 行、11 个语义列**逐列字符串比对无差异**（`column_diffs = {}`；`DataFrame.equals` 因 dtype 标注差异返回 False，
  值层面完全相同）。
- 权限：`snapshots/v1/universe` = `700`，`index_weight_intervals.parquet` = `600`，
  `ops/universe_source_A.json` = `600`，`snapshots/universe_index_weight.py` = `600`。红线 5 未被击穿。
- 绝对路径字面量扫描：`grep -nE "'/|\"/|/data/|/home/|/tmp/" snapshots/universe_index_weight.py` → **0 命中**，
  41 处 `cfg.` 引用。唯一配置入口这条守住了。

## V8 第三方交叉源尝试（负结果，记录以免下一个人重复找）

湖里的 `dc_index_member` 看起来像"指数成分区间"的第三方源，实测**不可用**：

```
1348 行；ts_code 只有 BK0145.DC(1336) 与 BK0685.DC(12) —— 东财板块，不是中证指数
trade_date 只有 20260728 / 20260729 / 20260806 三天
```

跟 csi300/500/1000 无关。**源A 的唯一可交叉对象仍然只有 qlib instruments（源B）。**

---

# 三、题目第 8 项：月内调整被抹平的量级

方法：qlib instruments 先把"贴片式"相邻段合并（`end + 1 自然日 == start`）成极大段，
再与源A 的月末快照日网格对照。合并后段数 **csi300 1225 / csi500 2466 / csi1000 3349**，
与模块数据卡里写的数字**完全一致**（数据卡这部分口径准确，一并核过：
distinct start 数 54/45/34、落在快照日的 29/35/34、连交易日都不是的 14/4/0，全部对得上）。

## 3.1 完全被抹平的成员（月中进、同月又出）：**0 段**

```bash
$PY ops/reports/adv_sourceA/adv_a3.py | python3 -c "import json,sys;d=json.load(sys.stdin)['qlib_month_internal'];\
print({u:(v['n_segments_overlapping_A_window'],v['n_segments_invisible_to_A']) for u,v in d.items()})"
# 实测: csi300 (1023, 0)  csi500 (2266, 0)  csi1000 (3349, 0)
```

落在源A 时间窗内的 qlib 极大段，**没有一段是整段夹在两期快照之间的**。
也就是说源A 抹掉的不是成员的**存在性**，而是成员的**日期**。docstring 里"月中调进、同月内又调出的票，
源A 里根本不存在"这句在本数据上是**理论风险，实测发生 0 次**——值得在数据卡里写上这个实测数，
它把一条"未知大小的坑"降级成了"已量化为零的坑"。

## 3.2 日期被推迟的量级

```bash
$PY ops/reports/adv_sourceA/adv_a4.py | python3 -c "import json,sys;print(json.dumps(json.load(sys.stdin)['qlib_intra_month_lag'],ensure_ascii=False,indent=1))"
$PY ops/reports/adv_sourceA/adv_a6.py
```

**入场侧**（qlib start 落在源A 窗口内的段）：

| 宇宙 | 窗内起点数 | 不在月末快照日 | 占比 | 推迟天数 min/p50/max |
|---|---|---|---|---|
| csi300 | 723 | **183** | 25.3% | 25 / 28 / 30 |
| csi500 | 1766 | **254** | 14.4% | 21 / 28 / 30 |
| csi1000 | 3346 | **0** | 0.0% | — |

**出场侧**（`out_date_A − end_B`，自然日；直方图见 D5）：

| 宇宙 | 段数 | 差 ≤ 2 天 | 差 21–30 天 | 均值 |
|---|---|---|---|---|
| csi300 | 723 | 542（75.0%） | **181（25.0%）** | 6.8 天 |
| csi500 | 1766 | 1512（85.6%） | **254（14.4%）** | 3.8 天 |
| csi1000 | 2349 | 2349（100%） | **0** | −0.1 天 |

## 3.3 量级结论（可直接抄进数据卡）

- **csi1000：月末快照粒度几乎零成本。** 入场侧 0 段被推迟，出场侧 0 段被推迟，
  剩下的差异全是 ±2 天的自然日/交易日取整伪影。原因是中证 1000 的调仓切点本来就落在月末最后一个交易日。
- **csi300：约 1/4 的成员区间两端各带 3–4 周的系统性滞后。** 换算成事件频率：
  183 次 ÷ 17.5 年 ≈ **10.5 次/年**的调仓事件被推迟到下一个月末。
- **csi500：约 1/7。** 254 次 ÷ 17.5 年 ≈ **14.5 次/年**。
- **左截断是比月内滞后大两个数量级的误差源**：csi300 首期 300 只**全部**被低估了 **≥1386 天**
  （≥3.8 年，且这是撞到 qlib 左边界后的下界，真实更长）；csi500 466/500 被低估 ≤723 天；
  csi1000 0/1000。任何跨 2009 年初的回测，左截断的影响远大于月内抹平。

---

# 四、给卡 1.2 的三条移交事项

1. **不要按 `entry_gap_suspect` / `exit_gap_suspect` 过滤**（D1）。这两列当前在 True 的 20 行上全错。
   在改对之前把它们当"待人工复核的候选"，不要当"已确认的脏数据"。
2. **`out_date_A >= end_B` 要先把 B 的自然日端点取整到交易日网格**（D5），否则会先收到 245 条 −2 天的假警报。
   `in_date_A >= start_B` 这一侧没有这个问题（实测入场滞后最小 21 天、无负值）。
3. **对齐 csi1000 时可以把出场侧当成 1:1**（3.3）：2349 段里 2240 段差 0 天、109 段差 −2 天（周末伪影），
   没有一段是真滞后。差异一旦超出这个形状，就是真问题，值得逐条查。
