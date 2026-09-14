# 指标与口径规格（约束性文件）

本目录存放**对 M2/M3 有约束力**的口径文件。凡本目录与实施稿冲突处，以本目录为准。

| 文件 | 作用 | 生效范围 |
| --- | --- | --- |
| `GeneBench指标对接决定_v1.md` | 量化研究员清单 × GeneBench 逐项采纳决定 | **凡与《指标规格 v1》冲突处以本文件为准**；规格 v1 的 §1/§3/§5 按本文件 §2/§3 增补 |
| `GeneBench指标规格_v1.md` | 指标与评分器规格 | Table A/B 定义式、探针规格、标定协议 |

> 归档于 2026-09-01，随 M1 签字后的补充指令一并落库。**不要改写这两份原文** ——
> 它们是决策记录；工程侧的落实记在 `ops/progress.md` 与各卡的验收里。

---

## 五项冻结项 → 卡的映射

对接决定 §6 列了五项"晚一步就要返工"的冻结项。逐项落到卡上：

| # | 冻结项 | 落在哪张卡 | 状态 |
| --- | --- | --- | --- |
| 1 | `SignalArtifact.value_semantics ∈ {rank, score}` 必填；**rank 语义下评分器禁止按数值距离加权**。缺失(`null`) 与主动空仓(显式 `flat`) 必须可区分，`fillna(0)` 判违例 | **卡 2.3** artifact schema | 待做 |
| 2 | scorer 输出 `validity` 与 `gate_failed`；**闸门语义非扣分** —— 五探针任一失败则该次运行效果分记 `invalid`、不产出数值、不进阶段均值与排名；correctness 类照常记录；报告单列 `invalid` 率 | **卡 2.3**（schema）+ **卡 5.2**（结算实现） | 待做 |
| 3 | 遥测 schema 预留 `search_count` 与 `trial_family`（M4 才填数，**字段名现在定死**） | **卡 2.3** schema 预留 + **卡 4.1** 填数 | 待做 |
| 4 | 标定配置写死并入 `calibration.json`：10 分位 / 平局平均法 / 等权 / 收盘后调仓 / 持有期 {1,5,20} 日 / Sharpe 年化 √252 且 gross-net 分开 / Sortino MAR=0 / turnover 明确 one-way 与 two-way **双记** / IC 汇总补 positive ratio 与 coverage 且不确定性一律用 **block-bootstrap** 而非仅 Newey-West | **卡 2.2** | 待做 |
| 5 | 卡 3.2 题目蓝图按 **COR / ROB / ECO / OPS 四族**覆盖，每阶段四族都要有题；v1.0 冒烟在 **S3 / S4 / S5 各留 1 道自由发挥题**（不指定具体因子/策略，由系统自行设计，承载效果指标） | **卡 3.2** | 待做 |

### 为什么第 2 项改变了计分语义

原先五探针是 Table A/B 里的**扣分列**。改成闸门之后，探针失败的那次运行其阶段效果分记 `invalid` 而**不是低分**。

理由（对接决定 §1.1 原文）：扣分制有一个致命漏洞 —— **带前视的因子 IC 会显著更高，扣掉几分之后总分仍可能高于诚实实现，等于奖励作弊**。闸门制堵死这条路。

对 scorer 的直接要求：`validity: {valid|invalid}` + `gate_failed: [探针 ID]`；`invalid` 时阶段效果分**不产出数值**（不是 0，是空）。correctness 类指标（Fid/Exec/Align）不受闸门影响 —— 它们回答"做对了没有"，与"结果可不可信"是两个问题。

### 第 4 项里最容易漏的两处

- **turnover 双记**：one-way 与 two-way 是两个数，不是一个数的两种叫法。只记一个，下游算成本时会差一倍。
- **不确定性用 block-bootstrap**：原规格只对 IC 的 t 值做 Newey–West，这是**窄口径**。新口径要求 IC / spread / alpha / Sharpe 一律给 block-bootstrap 区间（HAC 可并列但不能替代）。

---

## 未采纳 / 推迟（备查，避免日后重复讨论）

推迟到 v2：S8 幂等性以外的有状态项、容量与冲击曲线、跨市场迁移、B3-X 跨阶段科目（归 Chain 赛道）、S5 的 budget-matched tuned track（v1 只跑 canonical configuration，**报告里必须标注这一限制**）。

一处**保留意见**（对接决定 §5）：研究员主张不用加权总分。结算层完全采纳（主表逐指标分列、无总分）；呈现层的 profile 图需要每阶段一个标量，折中是按 §1.2 锚定归一定义、权重预注册并公示、图注标明"用于形状比较，逐指标记录以主表为准"，且**任何结论性断言只引用主表数字**。

---

## 第二批冻结（2026-09-01）：秩相关与 τ/ε 标定口径

全文见 [`GeneBench秩相关与标定口径_v1.md`](GeneBench秩相关与标定口径_v1.md)。六条，逐条落点：

| # | 冻结项 | 落点 | 状态 |
| --- | --- | --- | --- |
| F-1 | 逐交易日截面 Spearman（tie 平均法），再对时间取分布 | `reference/factor_crosscheck.py::_row_spearman` | 已做 |
| F-2 | τ = 全因子 × 全交易日 二维分布的 P10；**不先对时间平均** | 同上 `tau_candidates.pooled_factor_x_day_p10` | 已做 |
| F-3 | 三个数一起报（逐日 P10 / 因子级 P10 / 差） | 同上 `tau_candidates` | 已做 |
| F-4 | degenerate 判据：唯一值数 < 5% × 截面标的数，剔出 τ 样本；阈值来源记录 | 同上 `DEGENERATE_THRESHOLD_SOURCE` | 已做 |
| F-5 | 剔除率按因子/按日两个维度报；全窗 degenerate 的因子列名进 N-17 首批样本 | 同上 `degenerate_by_factor` / `degenerate_by_day` | 已做 |
| E-1 | ε 的随机性来源要写清；**五种子极差为 0 → 停下汇报**，不许设 0 也不许拍小数 | **卡 2.2** | 待做 |

**最容易漏的一处**：F-4 的 5% 与 **N-17 自己的上线阈值不是同一个数** ——
后者受 D-04 约束必须用 792 条实测覆盖率分布的 P5，不许拍。

---

## 两份会进论文的实证成稿

| 文件 | 论点 | 证据 |
| --- | --- | --- |
| [`operator_semantics_conflicts.md`](operator_semantics_conflicts.md) | **因子名与表达式不足以确定计算** | 同名算子 `ts_rank` 在两个成熟实现间值域不同（两边都没错）；`alpha038` 实现读错输入字段（一方就是错的）。两类在产物层面表现完全一样 |
| [`backtest_declaration_underdetermination.md`](backtest_declaration_underdetermination.md) | **回测声明不足以确定结果** | 三份互不知情的独立实现，同一份声明，毛收益互相差 6%+、双边换手差 6%+ |

**两份是同一论点的两端**，都以「跑通了、有数、看着正常」为共同的失败形态，
都只能靠**拿另一个独立实现去对**才照得出来。

---

## 新增任务卡规格

| 卡 | 文件 | 排期 | 阻塞什么 |
| --- | --- | --- | --- |
| **5.4 替换基线阶梯** | [`card_5.4_baseline_ladder.md`](card_5.4_baseline_ladder.md) | M5 之后、**M6 冒烟之前** | 不阻塞 M3/M4；**M6 出主表前必须完成**（profile 图 y 轴的定义靠它）|
| **4.1 容器隔离与出向策略** | [`card_4.1_container_isolation.md`](card_4.1_container_isolation.md) | M4，六条验收过五条 | 第 6 条等 **T-12**（一行 ufw）|
| **2.3 提交格式冻结** | [`card_2.3_artifact_schema.md`](card_2.3_artifact_schema.md) + `artifact_schema/v1.0/S1..S8.json` | M2 收尾，**M3 硬前置** | 三态声明字段 / `schema_version` 分派 / 两级结局；校验器 `reference/artifact_schema.py`，样例 40 非法 + 9 合法 |
| **3.1 GeneTask 打包器** | [`card_3.1_genetask_packager.md`](card_3.1_genetask_packager.md)（设计面板 [`card_3.1_design_panel.md`](card_3.1_design_panel.md)）| M3，3.2 的前置 | task.yaml 两面键集封闭；欠定字段渲染期屏蔽；判据先于题面落盘；金丝雀三串；六条待签字 |
| **S8 状态接口契约 v0** | [`s8_state_contract.md`](s8_state_contract.md) | S8 五题出题前签字（D-11）| `/sim/{state,order,cancel,advance,log}`、日频撮合规则、合法迁移、判据落点、三条未决 |
| **3.2 冒烟集 40 题** | [`card_3.2_smoke40.md`](card_3.2_smoke40.md) | M3；S3/S8 各五行 draft 等锁 | 覆盖矩阵、N1 40/40、oracle 验收方案；题面经指针词/评分词/概念句/情态对齐四轮机械修 |
| **红队流程（校验类卡标配）** | [`redteam_protocol.md`](redteam_protocol.md) | 卡 5.1 / 5.2 / 5.3 收口前各过一轮 | 六视角 × 两轮 × 两复核默认驳回；两个根因（自报切片键 / JSON 相等）单独成节 |
| **3.2 + 5.1 记忆探针（N-31）** | [`card_3.2_5.1_memory_probes.md`](card_3.2_5.1_memory_probes.md) | 题面随卡 3.2，判据与实现随卡 5.1 | **M6 出主表前必须完成** —— 主表要多三列 |

### 记忆探针为什么进 specs（而不是只当一张卡）

它改的是**主表的列**，不只是某一卡的产物：`memory_probe_hit_rate` /
`memory_probe_control_rate` / `memory_probe_horizon`。N-31 原本定性为
「必须声明的局限」，2026-09-01 **提级**为「必须测量的量」——
理由是污染程度与模型新旧**正相关**，它不会把结果打散，而会把结果**排好序**，
直接威胁主表的可比性。

**两处登记**：题面归卡 3.2（含「题面不得泄漏答案、不得让 agent 反推出冻结线后发生了什么」
两条硬约束），判据与探针实现归卡 5.1（含控制阶梯与 `inconclusive` 规则）。

---

## 第三批裁定（2026-09-01 晚）：出向策略与三件待批

| # | 裁定 | 落点 |
| --- | --- | --- |
| 1 | **出向默认拒绝 + 受控代理 + 主机名/SNI 白名单**，批准。理由是**防经互联网前视**，不是防外泄 | 设计笔记 **D-08**、卡 4.1 §3 |
| 2 | 代理日志登记为**卡 5.1 前视探针的第二结算源**（网关日志 = 数据面侧，代理日志 = 网络侧）| D-08、卡 4.1 §3.5 |
| 3 | 白名单**初值只放模型 API 域名**；依赖安装一律在**镜像构建期**解决，不进运行期白名单 | lint 规则 **L-8**、工单 **N-32** |
| 4 | **T-12** 按主机放行（`from 192.168.1.219`），不按网段、不无源限定 | 设计笔记 **D-09** |
| 5 | **N-30 / W1-b** 下个人工窗口执行，**先客户端后服务端** | D-06 第 7 个实例 |
| 6 | **N-31 提级**为 v1 必做的记忆探针 | 上表 |
| 7 | 记忆探针**判卷程序化不用 LLM**、容差按题类先冻结、对照题同构可验证 | `reference/memory_probe.py` + `ops/test_memory_probe.py`（44 项）|
| 8 | 探针答案集列为红线 5 的**第三类**不可泄漏物 | 实施稿红线段 + `reference/memory_probe_answers/README.md` |
| 9 | **卡 2.3 三条**：声明字段**三态**（`unresolved` 是显式枚举不是 null）；每个 artifact 带 `schema_version`、未知版本直接拒；非法样例按「会静默通过的形态」选 | `reference/artifact_schema.py` + `ops/test_artifact_schema.py` |
| 10 | 记忆探针**按模型跑一次、在臂指令之外**，按 model_id join；unparseable 的臂间不对称单独报 | `reference/memory_probe.py::summarize` |
| 11 | **D-11**：判据先于被判之物落盘（声明先于实现 B、判卷先于出题）| `design_notes.md` |
