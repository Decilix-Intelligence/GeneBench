# 数据卡：公开数据通道（卡 2.5 / 卡 1.3）

源 **baostock** · 冻结线 `2026-07-31` · 落点 `snapshots/public_v1`
· 条款原文 `ops/terms/baostock/` · 涨跌停推导 `snapshots/public/limits.py`
· 逐值对账 `ops/reports/public/reconciliation.md`

> **本卡只写公开通道自己的数。** 卡 2.5 §8：抄来的数字描述的是另一份数据，
> 而读者会以为它描述的是手上这份 —— 所以这里一个私有通道的数都没有，
> 两条通道的**比对结果**统一放在 `reconciliation.md`，本卡只在 §9 摘要并引用。
>
> **每一个数后面都跟着一条 HTML 注释**（写法 `src` 冒号 `文件:键路径=值`），指向它在产物里的出处。
> `ops/test_recon_public.py` 逐条去那个文件取那个键、比值 —— 值对不上、键不存在、
> 或者「注释对而正文错」，三种都会把测试打红。手写的卡与产物之间只有这一条绑定。

> **统一入口**：[`ops/data_cards/README.md`](README.md) —— 八张卡的对照表（源 / 窗口 / 覆盖 / 已知陷阱 / 缺口 / 校验和），以及私有 / 公开两条通道各自由哪几张卡描述。

---

## 0. 一句话

公开通道是**同一套代码在 baostock 行情上跑出来的第二份产物**，与私有通道并列不覆盖。
行情面全部来自公开源；**宇宙定义面（谁在指数里）仍取私有 `universe_pit`** ——
那是定义不是行情，baostock 没有指数成分历史（N-68 裁定）。
两条通道在收益率级、τ、ε、gold 上的逐项比对见 §9。

## 1. 源、窗口、规模

| | |
| --- | --- |
| 源 | baostock：`query_history_k_data_plus(adjustflag=3)` / `query_adjust_factor` / `query_stock_basic` |
| 窗口 | `20090105` … `20260731` <!-- src: public_v1/tables/build_info.json:window.start=20090105 --> <!-- src: public_v1/tables/build_info.json:window.end=20260731 --> |
| 冻结线 | `2026-07-31`（与私有通道同一条，不动） |
| 票数 | **3,575** <!-- src: public_v1/tables/build_info.json:codes=3575 --> |
| 交易日 | 4,269 <!-- src: reconciliation.json:returns.calendar_days=4269 --> |
| `daily` 行 | 10,948,502 <!-- src: public_v1/tables/build_info.json:rows.daily_rows=10948502 --> |
| `stk_limit` 行（**本卡推导**，见 §7） | 11,327,557 <!-- src: public_v1/tables/build_info.json:rows.limit_rows=11327557 --> |
| `suspend_d` 行 | 379,055 <!-- src: public_v1/tables/build_info.json:rows.suspend_rows=379055 --> |
| provider bin 文件 | 28,607 <!-- src: public_v1/qlib_provider/build_info.json:files=28607 --> |
| provider digest | `f7dda2899071b07a933b6ecf73b9f3c6ea0f916df8384b2fdf498aa04d0a8752` <!-- src: public_v1/qlib_provider/build_info.json:files_sha256_digest=f7dda2899071b07a933b6ecf73b9f3c6ea0f916df8384b2fdf498aa04d0a8752 --> |
| gold 文件 | 2,379 <!-- src: public_v1/gold_factors/build_info.json:files=2379 -->（三宇宙 × 792 因子 + 3 个 manifest） |
| 参考版本 | `r1.0.19` <!-- src: public_v1/gold_factors/build_info.json:reference_version=r1.0.19 --> |

> **2026-09-12（卡 A）宇宙定义面换过一次。** 包里的 `instruments/` 与 `universe/`
> 从「私有 `universe_pit`（上游 tushare）派生」换成「**baostock 成分接口重建**」
> （`query_hs300_stocks` / `query_zz500_stocks`，见 `ops/reports/public/instruments_rebuild.md`
> 与 `ops/reports/public/instruments_switch.md`）。随之：**`csi1000` 出包**（baostock
> 没有中证 1000 的成分接口），`all` 改成 csi300 ∪ csi500 的码。**`features/` 一个字节没动**
> —— 下面这张表里的票数 / 行数 / 窗口说的是**行情面**，不受这次换面影响；
> 变的只有 `provider bin 文件` 与 `provider digest` 两行。

**票数 3,575 <!-- src: public_v1/tables/build_info.json:codes=3575 --> 不是全市场。**
公开通道的**行情面**建的是 v1 三宇宙（csi300 / csi500 / csi1000）的并集
—— 建全市场要多花约 11.5 小时打在一个免费 API 上，而 v1 的题一条都不碰并集之外的票
（N-68）。代价写在 §3。

## 2. 条款：再分发**没有**从平台条款里查出来

站点已改版为 SPA，五份平台条款经 `GET /articleMall/api/contract?contract_type=N`
取回并全部存档（含抓取时间、版本号、响应 sha256）。三条结论：

1. 五份**全部治理「Baostock 交易技术商城」这个知识付费平台** —— 账号、作者签约、
   分成、退款、平台内容著作权。**没有一条**提到通过行情 API 取得的数据能不能再分发。
2. 离得最近的是免责声明第 5 条：「网站内容（文字、图片、代码、设计等）…
   未经书面许可不得复制、传播或用于商业用途」。它**没有列举 API 数据**，
   但措辞是**默认禁止**。
3. PyPI 上 `baostock` 标的 `BSD License` 是**客户端库**的许可，**不是数据的条款**。
   拿它当依据，正是卡 2.5 §2 明写要避免的「我记得它允许」。

**再分发许可由用户单独取得**，不是从这五份里读出来的 —— 这一点要写清楚，
否则后来的人会以为「条款里查出来可以」，而条款里查不出来。
**状态 `pending_license_text`**：书面原文尚未入库，原文到位之前不发布任何包
（见仓库根 `DATA_LICENSE`、卡 1.4 的 `ops/reports/public/release_forms.md`）。

**另有一处许可缺口**：`instruments/`（宇宙定义面）派生自私有 `universe_pit`，
它的再分发**不在 baostock 那份许可的射程内**。已记进包的
`MANIFEST.json:data_source.universe_definition_note`，发布前要单独确认。

## 3. 覆盖面：**baostock 不服务北交所**

`920xxx.BJ` 一律返回 `10004011 股票代码未标识sh或sz`。

| | 只数 |
| --- | ---: |
| 公开 provider | 3,575 <!-- src: reconciliation.json:returns.coverage.codes_public=3575 --> |
| 只在私有通道有 | 2,242 <!-- src: reconciliation.json:returns.coverage.codes_only_private=2242 --> |
| **其中北交所** | **336** <!-- src: reconciliation.json:returns.coverage.codes_only_private_bse=336 --> |
| 只在公开通道有 | 0 <!-- src: reconciliation.json:returns.coverage.codes_only_public=0 --> |

**「只在私有」里绝大多数不是缺口，是没建**（§1：公开通道只建三宇宙并集）。
**真缺口是北交所那 336 只** —— 公开源根本取不到。

* **不阻塞 v1**：三个 universe 全是沪深，792 条 gold 因子不碰北交所。
* **但公开通道的 `all` ≠ 私有通道的 `all`。** 任何按 `all` 取宇宙的重算，
  两条通道的**分母不同**。这是卡 2.5 §1 七项依赖表之外的第八项差异，
  性质是「覆盖面」不是「字段」。

## 4. 停牌：公开源**有行**，私有湖**缺行**

| | 表示 |
| --- | --- |
| baostock | **有行**，`tradestatus=0`，`volume` / `amount` 为 0 |
| 我们的湖 | **缺行** |

建集时把这个差异吸收进 `suspend_d`（行数见 §1），
`tradability` 视图输出的三态不变（`trade` / `suspend` / `no_data`）。
吸收干净的判据是行集合：全量比下来**只在公开 0 行** <!-- src: reconciliation.json:rows.rows_only_public=0 -->、
**只在私有 5 行** <!-- src: reconciliation.json:rows.rows_only_private=5 -->
（共有 10,948,502 行 <!-- src: reconciliation.json:rows.rows_in_both=10948502 -->）。

**S2 全部 gold 必须在公开通道重算**（已在卡 1.1-b 做完）——
S2 正是「缺行 vs 有行」这个差异的落点（`missing_row_policy` 三档），
不重算等于把两个通道的差异藏进 gold。

## 5. 量额单位：`amount` 是**元**、`volume` 是**股**

不是 tushare 的千元 / 手，建 provider 时**不需要换算**。

**判据不是查文档**，是在公开源上跑落带检验：`vwap = amount / volume`
必须落在当日 `[low, high]` 里。全量
10,947,817 <!-- src: reconciliation.json:units.in_band=10947817 --> /
10,948,502 <!-- src: reconciliation.json:units.cells=10948502 --> 落带
（0.99993743 <!-- src: reconciliation.json:units.in_band_rate=0.99993743 -->），
中位 `vwap/close` = 0.9999954 <!-- src: reconciliation.json:units.median_vwap_over_close=0.9999954 -->。
把单位换成千元或手（×1000 / ÷1000），落带率会掉到 0 —— 这才是这条判据有判别力的原因。

## 6. 复权口径：**这是公开通道最深的一个坑**

两条通道的 provider 都以冻结线重定基（`factor = 1`），所以复权价位**本来就该可比**。
实测不是：

| 量 | 值 |
| --- | ---: |
| 复权收盘价逐格相对差 ≤ 1e-6 的占比 | **0.170748565** <!-- src: reconciliation.json:returns.price_level.agree_rate=0.170748565 --> |
| 该占比对应的格数 | 10,948,502 <!-- src: reconciliation.json:returns.price_level.cells=10948502 --> |
| 逐格相对差 P50 | 3.53732e-05 <!-- src: reconciliation.json:returns.price_level.quantiles.p50=3.53732e-05 --> |
| 逐格相对差 P99 | 0.000722856 <!-- src: reconciliation.json:returns.price_level.quantiles.p99=0.000722856 --> |

**这个 0.17 不是「算错了」，它是一句没有判别力的话。** 两条通道的归一化常数逐票不同，
而**常数不影响收益率**，也不影响任何以收益率为输入的下游数值。要分两类看：

| 类 | 只数 | 含义 |
| --- | ---: | --- |
| 「公开价 / 私有价」这个比值在该票内几乎不动（`max/min − 1` ≤ 0.001 <!-- src: reconciliation.json:returns.level_scale.constant_ratio_spread_threshold=0.001 -->）| **3,517** <!-- src: reconciliation.json:returns.level_scale.codes_constant_ratio=3517 --> | 差异**就是一个常数**。不影响收益率；**会**影响任何直接读价位的东西 |
| 比值真的在动 | **58** <!-- src: reconciliation.json:returns.level_scale.codes_drifting_ratio=58 --> | 两条通道对这只票的**复权处理真的不同**，差异会一路传到 gold |

比值离 1 最远的一只是 0.051912991 <!-- src: reconciliation.json:returns.level_scale.median_ratio.min=0.051912991 -->
（公开的复权价大约是私有的二十分之一）—— 而它的比值在该票内几乎不动，
所以它的**收益率一格都没差**。

**收益率级**（卡 2.1a 的口径，逐票逐日 close-to-close）：

| | 值 |
| --- | ---: |
| 收益率对 | 10,944,927 <!-- src: reconciliation.json:returns.full.return_pairs=10944927 --> |
| \|Δr\| ≤ 1e-6 的占比 | **0.995204902** <!-- src: reconciliation.json:returns.full.agree_rate=0.995204902 --> |
| \|Δr\| > 1e-3（**实质不同**）的对数 | **123** <!-- src: reconciliation.json:returns.full.pairs_over_material=123 --> |
| 这 123 对集中在几只票上 | **59** <!-- src: reconciliation.json:returns.full.codes_over_material=59 --> |

那 0.5% 的缺口按 `Δlog(1+r) = Δlog(原始收盘之比) + Δlog(factor 之比)` 分解，
**几乎全是复权因子的台阶差**：

| 类 | 对数 |
| --- | ---: |
| `adjustment_step`（复权因子在这两天走了不同的台阶）| **52,424** <!-- src: reconciliation.json:returns.attribution.adjustment_step=52424 --> |
| `raw_quote_step`（源报价的台阶差）| 12 <!-- src: reconciliation.json:returns.attribution.raw_quote_step=12 --> |
| `neither`（两项都在 1e-6 内，收益率却差更多）| 46 <!-- src: reconciliation.json:returns.attribution.neither=46 --> |
| 合计（\|Δr\| > 1e-6）| 52,482 <!-- src: reconciliation.json:returns.attribution.over=52482 --> |

**这条要写进使用说明**：拿公开通道跑出来的因子值/回测，**不要与私有通道的价位对读**；
可以对读的是收益率与由收益率导出的一切。以及：那 58 只票的 gold 与私有通道**实质不同**，
不是噪声。

## 7. 涨跌停：公开通道要**自己推**，已知误差 4 行

私有通道直接读 `stk_limit`，公开通道没有这张表 —— 必须从 `preclose` 推。
**这是公开通道唯一一处「我们自己算」的地方**，其余字段都是搬运。

| 板块 / 情形 | 幅度 | 取整 |
| --- | --- | --- |
| 主板（60xxxx / 00xxxx）| 10% | 四舍五入到分 |
| 创业板（300 / 301 / 302xxx）| 20%（`20200824` <!-- src: reconciliation.json:limits.rules.chinext_20pct_from=20200824 --> 起；之前 10%）| 四舍五入 |
| 科创板（688 / 689xxx）| 20%（`20190722` <!-- src: reconciliation.json:limits.rules.star_20pct_from=20190722 --> 起，开市即 20%）| 四舍五入 |
| 北交所（8xxxxx / 4xxxxx / 920xxx）| 30% | **「不超过幅度」的截断**（涨停向下、跌停向上）|
| ST / \*ST（**仅主板**）| 5%，最后一天 `20260703` <!-- src: reconciliation.json:limits.rules.st_5pct_last_day=20260703 --> | **2026-07-06 起取消**，回到板块正常幅度 |
| ST / \*ST（创业板 / 科创板）| **仍是 20%**，不收窄 | |
| S 股（未完成股改，名字以 `S` 开头且非 ST）| 5%，即 `0.05` <!-- src: reconciliation.json:limits.rules.s_share_pct=0.05 --> | 全市场仅 `600182.SH` |
| 新股 | **沪深 5 天** <!-- src: reconciliation.json:limits.rules.no_limit_trading_days.main=5 --> / **北交所 1 天** <!-- src: reconciliation.json:limits.rules.no_limit_trading_days.bse=1 --> 无限制 | |
| 退市整理期首日 | 无限制（判据取 `namechange.change_reason = '退市整理期'`）| |

**「无限制」在私有 `stk_limit` 里有三种编码**，三个交易所各一种 ——
对账时会用到，所以记在这里当**数据**，不当判据：
沪 `99999.999` <!-- src: reconciliation.json:limits.rules.oracle_no_limit_sentinel.SH[0]=99999.999 -->、
深 `999999.999` <!-- src: reconciliation.json:limits.rules.oracle_no_limit_sentinel.SZ[0]=999999.999 -->、
北 `99999.99` <!-- src: reconciliation.json:limits.rules.oracle_no_limit_sentinel.BJ[0]=99999.99 -->。
**推导侧不产出哨兵** —— `Limits.up is None` 就是「无限制」这个语义。

**验收（2026 年至冻结线，拿私有 `stk_limit` 逐行当 oracle）**：
比 466,773 行 <!-- src: reconciliation.json:limits.rows_compared=466773 -->，
一致率 0.999991431 <!-- src: reconciliation.json:limits.agree_rate=0.999991431 -->，
**分歧 4 行** <!-- src: reconciliation.json:limits.disagree=4 -->。

**这 4 行是已知误差，不是没查出来的错**：全部是**退市整理期首日**。
那一天无涨跌幅限制，而判据 `namechange.change_reason` 是**私有表**，
公开源推不出来 —— 公开通道于是按板块正常幅度推。
**不要用名字近似去补**：退市命名规则两个交易所相反（深 / 北是后缀「退」，
**沪是前缀「退市」**），按名字判会整个漏掉沪市，表现是分歧散落各处、看起来像随机噪声。

**S7 / S8 对这张表敏感。** 用公开通道跑这两阶段的题时，这 4 行是已知偏差面。

## 8. 缺失日

有价日数两边不等的票：5 只 <!-- src: reconciliation.json:returns.missing_days.codes_with_day_gap=5 -->，
合计公开比私有少 5 个 (票, 日) <!-- src: reconciliation.json:returns.missing_days.public_short_of_private=5 -->、
多 0 个 <!-- src: reconciliation.json:returns.missing_days.private_short_of_public=0 -->。
在千万量级的格上，这一项**不构成覆盖面问题**。

## 9. 与私有通道的差异摘要

**全部逐值比对在 `ops/reports/public/reconciliation.md`**（由
`ops/recon_public_vs_private.py` 渲染，数从产物读不手抄）。摘要：

| 面 | 结果 |
| --- | --- |
| `daily` 行级（全量） | `close` 到分一致率 0.999999087 <!-- src: reconciliation.json:rows.by_field.close.agree_rate=0.999999087 -->，不一致 10 行 <!-- src: reconciliation.json:rows.by_field.close.disagree=10 -->；`amount` 相对 1e-6 一致率 0.999958168 <!-- src: reconciliation.json:rows.by_field.amount.agree_rate=0.999958168 -->，不一致 458 行 <!-- src: reconciliation.json:rows.by_field.amount.disagree=458 --> |
| 收益率级 | 见 §6 |
| τ | 两条通道的差 2.488917e-05 <!-- src: reconciliation.json:calibration.tau.delta_abs=2.488917e-05 -->；参与因子数、参与格数、算子冲突名单**逐项相同** |
| ε 分档 | `daily` usable / `weekly`、`monthly` 不 usable，**分档结论相同**；但**带值本身两边并不接近**，见 `reconciliation.md` §2.2 |
| `ic_family` | 可用指标相同 |
| gold 抽样（三宇宙各 30 因子 × `20260105`..`20260630`）| 超阈（相对差 > 1e-3）占比：csi300 0.001564637 <!-- src: reconciliation.json:gold.by_universe.csi300.over_threshold_rate=0.001564637 -->、csi500 0.002200221 <!-- src: reconciliation.json:gold.by_universe.csi500.over_threshold_rate=0.002200221 -->、csi1000 0.003877111 <!-- src: reconciliation.json:gold.by_universe.csi1000.over_threshold_rate=0.003877111 --> |

**结构性结论（卡 2.5 §10）一条都没变**：算子冲突名单、声明欠定、materiality、
探针设计 —— 那些是关于**方法**的发现，不随数据源变。
**变的是数**，而数以公开通道为准进论文，私有通道作对照列。

## 10. 设计教训（引用**方法**，不引数字）

这三条来自私有通道的数据卡与既有裁定，**是关于方法的**，在公开通道同样成立
（各自的数在本卡与 `reconciliation.md` 里重新量过，没有抄）：

* **双实现互检是唯一能照出「参考实现算错了」的手段，而它的覆盖不完整**
  （`ops/data_cards/gold_factors.md` §3，N-22）。没有第二实现的那些因子，
  同类字段错位当前方法照不出来 —— 这条限度在公开通道上一字不变。
* **算子语义存疑与实现缺陷表现完全一样，处置不同**
  （同上 §4，N-24）。下游必须调 `reference.operator_flags` 的 API 而不是抄名单。
* **`inf` 保留不筛，`float64` 不用 `float32`**（同上 §5）。
  秩相关对饱和不是不变的：一批大数被压成同一个 `inf` 会并列，Fid% 虚高。

再加一条**本通道自己的**：

* **拿一份权威数据当验证器，比「规则写对了应该就对」强一个量级。**
  §7 的规则表原来错四处（北交所取整、ST 带的生效日、新股窗口按板块不同、
  退市整理期首日），四处**全部由私有 oracle 逐行核逼出来，对着文档一处都查不出**，
  而错的表现是 gold **照常算得出数**。

## 11. τ 标定于此实现对

τ = 0.983981 <!-- src: public_v1/calibration.json:tau.value=0.983981 -->，
ε\[daily\] usable = true <!-- src: public_v1/calibration.json:epsilon.by_frequency.daily.usable=true -->，
IC 族可用指标 4 项 <!-- src: public_v1/calibration.json:epsilon.ic_family.usable_metrics|len=4 -->：
`coverage` <!-- src: public_v1/calibration.json:epsilon.ic_family.usable_metrics[0]=coverage --> /
`icir` <!-- src: public_v1/calibration.json:epsilon.ic_family.usable_metrics[1]=icir --> /
`mean` <!-- src: public_v1/calibration.json:epsilon.ic_family.usable_metrics[2]=mean --> /
`std` <!-- src: public_v1/calibration.json:epsilon.ic_family.usable_metrics[3]=std -->。

**τ 标定于此实现对** —— 换实现 = 重算 gold + 重标 τ + 重新签字。
所以「因子库的定义面」必须随包发，逐件带 sha256（`PUBLIC_FROZEN_ARTIFACTS`，N-58⑥）：

| 冻结件 | 状态 | sha256 |
| --- | --- | --- |
| `reference/factorlib_pinned/formula.py` | 在 | `3eaf99b7dc829e824cc37cea4a414858ffc34dec9b317ab807df960bf9cb17a4` <!-- src: reconciliation.json:frozen.present["reference/factorlib_pinned/formula.py"].sha256=3eaf99b7dc829e824cc37cea4a414858ffc34dec9b317ab807df960bf9cb17a4 --> |
| `reference/factorlib_pinned/qlib_loader.py` | 在 | `bbad13f3b7152df1566b5719290baa6426f717e79227c7009a51c9208224cf96` <!-- src: reconciliation.json:frozen.present["reference/factorlib_pinned/qlib_loader.py"].sha256=bbad13f3b7152df1566b5719290baa6426f717e79227c7009a51c9208224cf96 --> |
| `reference/factorlib_pinned/qlib_ops.py` | 在 | `f3d16a7925c5778cf3760516ac62671958fdef675e26fb90983077aca8c7ced2` <!-- src: reconciliation.json:frozen.present["reference/factorlib_pinned/qlib_ops.py"].sha256=f3d16a7925c5778cf3760516ac62671958fdef675e26fb90983077aca8c7ced2 --> |
| `factor_library/compiled/qlib_native.jsonl` | 在 | `f0ea97c6bd5b1a8c41736b31a68756d1543d9e11c26ee3d1f8cf42727b2a4698` <!-- src: reconciliation.json:frozen.present["factor_library/compiled/qlib_native.jsonl"].sha256=f0ea97c6bd5b1a8c41736b31a68756d1543d9e11c26ee3d1f8cf42727b2a4698 --> |
| `factor_library/compiled/qlib_panel.jsonl` | 在 | `cbf4ba183edfaabb30211decb57297c391b888ff1e6fc5fd77cc62720f882384` <!-- src: reconciliation.json:frozen.present["factor_library/compiled/qlib_panel.jsonl"].sha256=cbf4ba183edfaabb30211decb57297c391b888ff1e6fc5fd77cc62720f882384 --> |
| `factor_library/compiled/blocked.jsonl` | 在 | `955f7a66c4e7a63d727fce9cb3b6fa6f22ca1b725d7db4e864bbbe76cb2bb5cc` <!-- src: reconciliation.json:frozen.present["factor_library/compiled/blocked.jsonl"].sha256=955f7a66c4e7a63d727fce9cb3b6fa6f22ca1b725d7db4e864bbbe76cb2bb5cc --> |

**声明的 6 个冻结件全部到位，不在仓库里的是 0 件** <!-- src: reconciliation.json:frozen.missing|len=0 -->。
`factor_library/compiled/` 那三件是 **2026-09-10（卡 W2，提交 `8428252`）从湖里收进仓库的** ——
在那之前整个 `factor_library/` 目录都不存在，这张卡、`README.md` §5 与
`docs/OPERATOR_MANUAL.md` §0.1 都如实写着它们不在、且挡发布。**那一条现在已闭合**
（`RELEASE_MANIFEST.json` 的 `frozen_artifacts_missing`：`satisfied=true`），
三处陈述由卡 W.rt 一并改到现状。
为什么它们非在不可：它们是 gold 的**定义面**（「τ 标定于此实现对」），
少了它们，拿到包的人**复现不了 τ** —— 而 τ 恰恰标定在「两个实现有多一致」上。
打包器不静默丢：不在仓库里的声明件会记进包的 `MANIFEST.json:missing_declared_artifacts`。

## 12. 复现

```bash
GB=/data/shared/genebench; cd $GB/repo && ulimit -n 8192
$GB/env/bin/python ops/build_public_channel.py        # 数据面：表 / tradability / provider
$GB/env/bin/python ops/run_public_chain.py            # 重建链：gold → 互检 → τ → ε → calibration
$GB/env/bin/python ops/recon_public_vs_private.py     # 两通道对账（本卡的数从这里来）
$GB/env/bin/python -m pytest ops/test_recon_public.py ops/test_public_limits.py -q
```

**重跑 gold 一定要给 `--spill-dir`**（`reference/factor_exec` 的面板暂存面）：
不给的话 792 个面板同时压内存，csi1000 常驻约 22 GiB。
`ops/run_public_chain.py` 的 gold 步默认带上，直接调 `factor_exec` 的调用方要自己给。
