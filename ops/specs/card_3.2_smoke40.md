# 卡 3.2：v1.0 冒烟集（起草 8 × 5 = 40 题；**v1.0 出集 33 题**）

> **状态：v1.0 RELEASED（2026-09-04 签字放行）**。三道抽查题（`s6-rob-01` / `s4-eco-01` / `s5-cor-01`）
> 两臂全文核过，模板级修正（E12c / E14 / E6 强度补丁 / 路径统一 / 镜像残留）覆盖全 40 题，
> 三控 40/40，f01 全量绿。冻结清单 `ops/manifests/v1.0-smoke.json`，防漂断言见
> `ops/test_genetask.py::test_v10_manifest_matches_frozen`，重冻用 `python3 ops/freeze_v10.py --write`。
>
> **冻的是输入，不是产物**：`canary.control_token` 每次打包是新 nonce（`secrets`），
> 同一份模板两次 build 的 `instruction[arm].sha256` **必然不同**。所以清单冻的是
> 模板文件 + `phrasebook.yaml` + 参数表 + 渲染器/规则代码这四样，任一变动即判漂。
> 有一条测试专门留了这个证据（`test_canary_token_is_a_fresh_nonce_每次打包`），
> 免得后人拿渲染产物的 sha 去比对然后困惑。
>
> **放行 ≠ 可跑**。冒烟集是**题**，跑它还需要 runner 与评分器：
>
> | 里程碑 | 内容 | 状态 |
> |---|---|---|
> | M3 | 出题（卡 3.1 打包器 / 3.2 冒烟集） | **本卡收口** |
> | M4 | runner：卡 4.2 解析器与评分适配、4.3 双臂注入、4.4 模拟盘 | 4.2/4.3 与 4.4 **并行进行中** |
> | M5 | 评分器：5.1 探针族、5.2 L3 结算（**N-39 的 qlib 偏离清单为前置**）、5.3 遥测与报告器、5.4 基线阶梯 | **未开工 —— 剩余最大的一块**，每张卡按红队协议过一轮 |
> | M6 | 三配置 × 双臂 × 33 题 × 三种子 | 依赖 M4 + M5 全部落地 |
>
> **卡 3.3（扩量 8 × 15–25）等 M6 首表审阅后启动** —— 先看冒烟集在真 runner 上的表现，
> 再决定扩量的题型配比，避免把冒烟集的结构缺陷按比例放大 15 倍。

**范围（2026-09-03 重划，理由与逐阶段缺口见 §0）**：v1.0 冒烟集 =
**32 道规定题（`regulated` / `free`）+ 1 道探针题 `s7-rob-02`（`sell_rule`，证据已在）**。
其余**七道探针题移出 v1.0**：各等所在阶段的 **L3 实现（M5）**落地后补跑 screen，随 **M6** 入集。

**状态**：40 行全部过打包器（R1–R5 / E1–E11 / C1 / N1），**E6 零标记**，四族齐、探针恰 1、free 只在 S3/S4/S5；
**S3 五行、S8 五行、七道探针题为 draft**（S3 等 `n33_bars_open_amount_vwap` 在 f01 翻绿后 packed；
**S8 五行等卡 4.4 的模拟盘**（`card_4.4_sim_engine.md`），不只是 S8 的探针题；
七道探针题等各自阶段的 `DIVERGENCE_EVIDENCE` 实测证据（**E9d2**）与 `probe_materiality_verified`（**E9c**）；
`s7-rob-02` 的证据 2026-09-03 已由 materiality screen 跑出，见 §3b）。
起草：八阶段并行起草者 + 逐阶段打包校验者（`draft-smoke-40` 工作流）；机械迁移到卡 3.1 新规则后再修
（指针词、评分词、E4 概念句、S7「契约」→「上面给出的声明」）；情态/义务漂移由 `repair-arm-modals` 工作流按阶段修到 E6 零标记。
参数表 `genetask/params/v1.0-smoke40.yaml`；模板 `genetask/templates/<stage>/<template_id>/`。

## 0. v1.0 出集范围（2026-09-03 重划）

**出集 33 题 = 32 道规定题 + 1 道探针题 `s7-rob-02`（`sell_rule`）。**

重划的依据是一条实测：2026-09-03 的 materiality screen **只在 S7 跑出了证据**，其余七个阶段**跑不了 ——
缺的不是接线，是被测对象**（下表）。**E9d2 是逐字段判据，不是逐卡判据**：有证据的那一道现在就能出集，
没证据的七道不该把另外 32 道规定题一起拖住。

**下表的取证出处**：S7 那一行是本轮 screen 的直接产物；其余各行转引 `ops/specs/materiality_wiring_plan.md`
表 B 的现场取证，本轮逐条在 f01 上抽验过锚点（S4 那格已按抽验结果改正 —— 原文写「五个全是 `NotImplementedError`」，实测 `rob_probe_setting` 是零占位、不抛异常）。

| 阶段·探针字段 | 缺什么 | 解锁条件 |
| --- | --- | --- |
| S1 · `data_version` | **B 概念上不存在** —— 三份 B 是回测器，不做取数，「换一个数据版本重取」在它们的输入空间里没有对应物；A 也接错阶段（`run_backtest`，实测 `TypeError: unexpected keyword 'stage'`）。另：只有 `v1` 快照（`SNAPSHOT_VERSION='v1'`），网关全部 Query 参数无版本维度 | S1 的 **L3 实现（M5）** + v2 快照 + 网关加版本维度 |
| S2 · `adjust` | **B 概念上不存在** —— 三份 B 吃的 `close` **已经是后复权价**，复权是它们的输入常量而不是参数，没有可切换的读法。且 payload 里没有一个数值量对 `adjust` 敏感：实测三取值 `rows/n_symbols/n_dates/missing` 逐位相同（41700/300/139/44），只有 `sha256` 变，而哈希不是数 | S2 的 **L3 实现（M5）** + 先给 S2 定「对复权敏感的数值判据」 |
| S3 · `eval_frequency` | **只有 1 份 B**（签字裁定要 A + 三份 B）；且本题判据是 **τ**（面板秩相关下限），形状不是逐指标 ε 带 → `screen_band.Band` 抛 `BandUndecided`，整题只能记 `inconclusive` | S3 的 **L3 实现（M5）**补到三份 + 给 τ 定可判的带形状 |
| S4 · `holding_periods` / `ic_method` | **没有任何 IC 实现，A 与 B 都是 0 份** —— 五个 `templates/S4/*/solve.py` **没有一个真算 IC**：四个是 `NotImplementedError` 骨架（`cor_ic_recompute` / `rob_sparse_panel` / `ops_audit_trail` / `eco_free_select`），`rob_probe_setting` 填的是**零持有期占位**（`ic_stats` 全 `0.0`）—— 后者不抛异常，所以「跑得通」不等于「有实现」；`scorer/__init__.py` 只有 189 字节注释，三份 B 是回测器不产 IC。IC 七量（mean/std/ICIR/positive_ratio/coverage/CI）在 ε 表里**一个都没有**，本题 `tolerance.kind=none` | S4 的 **L3 实现（M5）** + 给 IC 定带（`kind=none` 要先改） |
| S5 · `signal_frequency` | **没有实现** —— 唯一的 S5 oracle 在注释里**明确拒绝**降采样（`freq_unstated/solve.py:99-100`）；B 零份（三份 B 的 `freq` 是 **rebalance**_frequency，不是 signal_frequency）。ε 被 `schema.py` 限死在 S7，与 S5 payload（`signals`/`coverage`）零交集 | S5 的 **L3 实现（M5）**（两份以上独立实现）+ 定 S5 可比指标与带 |
| S6 · `rebalance_frequency` | 三份 B 能直接跑（实测 81 个比较中 64 处超带），但 **A 缺席**（lane 只有 B1/B2/B3）；且产物空间错位：B 出的是 S7 回测指标，S6 要判的是 `targets`/`cash_ratio` | 补 A 侧 + 签字接受口径替换 |
| **S7 · `sell_rule`** | **不缺** —— 2026-09-03 screen 实测三份 B **全部 material**（§3b） | **已满足，随 v1.0 出集** |
| S8 · `slippage_reference_price` | **模拟盘不存在** —— 网关无 `/sim/*`（只挂 market + reference 两个 router），`ops/capabilities.json` 的 `s8_state_endpoint=false`，oracle 的 HTTP 客户端是 `raise NotImplementedError`，B 零份 | **卡 4.4**（`card_4.4_sim_engine.md`）落地 → 能力位翻绿 |

**S8 的五道题全部等卡 4.4，不只是探针题**：没有模拟盘，`s8-cor-01` 的生命周期、`s8-rob-01` 的幂等、
`s8-eco-01` 的最小滑点、`s8-ops-01` 的越权率都没有可跑的被测对象 —— 它们缺的是**环境**，
与探针题缺的**证据**是两件事，但今天都指向同一张卡。

**出集判据不变**：32 道规定题照走 §5「审查强度分层」的规定题通道（机械规则全套 + 每阶段抽 1 道贴签字人过目）；
`s7-rob-02` 走探针题通道（机械规则 + 对抗复审 + 逐题人工签字）。

**一条待批（挡在放行前面）**：`probe_materiality_verified` 现在是 `ops/capabilities.json` 里的**一个全局 bool**
（实测 `false`），而 E9c 要按本节做**逐字段**放行。它要么改成按字段的映射、要么给 S7 单开一位；
**在改之前 `s7-rob-02` 仍只许 `draft`** —— 不许靠「整位翻绿」把另外七道一起放出去。

## 1. 覆盖矩阵与 null_agent 判别力（N1，本机实测）

| 阶段 | task_id | 族 | kind | 模板 | 欠定 | null 行为 | N1 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | `s1-cor-01` | COR | regulated | `cov_fields` | — | empty | ✅ |
| S1 | `s1-rob-01` | ROB | regulated | `source_status` | — | copy_input | ✅ |
| S1 | `s1-rob-02` | ROB | underdetermined_probe | `source_status` | data_version | default_fill | ✅ |
| S1 | `s1-eco-01` | ECO | regulated | `lean_fetch` | — | empty | ✅ |
| S1 | `s1-ops-01` | OPS | regulated | `prov_ledger` | — | copy_input | ✅ |
| S2 | `s2-cor-01` | COR | regulated | `cor_01` | — | empty | ✅ |
| S2 | `s2-rob-01` | ROB | regulated | `rob_01` | — | default_fill | ✅ |
| S2 | `s2-eco-01` | ECO | regulated | `eco_01` | — | empty | ✅ |
| S2 | `s2-ops-01` | OPS | regulated | `ops_01` | — | empty | ✅ |
| S2 | `s2-rob-02` | ROB | underdetermined_probe | `rob_02_probe` | adjust | default_fill | ✅ |
| S3 | `s3-cor-01` | COR | regulated | `cor01_wq006_corr` | — | empty | ✅ |
| S3 | `s3-rob-01` | ROB | regulated | `rob01_wq054_nonfinite` | — | default_fill | ✅ |
| S3 | `s3-eco-01` | ECO | free | `eco01_free_pv` | — | empty | ✅ |
| S3 | `s3-ops-01` | OPS | regulated | `ops01_gtja012_vwap_audit` | — | empty | ✅ |
| S3 | `s3-rob-02` | ROB | underdetermined_probe | `rob02_gtja046_probe` | eval_frequency | default_fill | ✅ |
| S4 | `s4-cor-01` | COR | regulated | `cor_ic_recompute` | — | empty | ✅ |
| S4 | `s4-rob-01` | ROB | regulated | `rob_sparse_panel` | — | default_fill | ✅ |
| S4 | `s4-rob-02` | ROB | underdetermined_probe | `rob_probe_setting` | holding_periods | default_fill | ✅ |
| S4 | `s4-eco-01` | ECO | free | `eco_free_select` | — | empty | ✅ |
| S4 | `s4-ops-01` | OPS | regulated | `ops_audit_trail` | — | empty | ✅ |
| S5 | `s5-cor-01` | COR | regulated | `rank_signal` | — | empty | ✅ |
| S5 | `s5-rob-01` | ROB | regulated | `null_vs_flat` | — | default_fill | ✅ |
| S5 | `s5-rob-02` | ROB | underdetermined_probe | `freq_unstated` | signal_frequency | default_fill | ✅ |
| S5 | `s5-eco-01` | ECO | free | `free_signal` | — | empty | ✅ |
| S5 | `s5-ops-01` | OPS | regulated | `format_audit` | — | default_fill | ✅ |
| S6 | `s6-cor-01` | COR | regulated | `cor_ledger` | — | empty | ✅ |
| S6 | `s6-rob-01` | ROB | regulated | `rob_optimizer_failure` | — | default_fill | ✅ |
| S6 | `s6-eco-01` | ECO | regulated | `eco_swap_cap` | — | empty | ✅ |
| S6 | `s6-ops-01` | OPS | regulated | `ops_ledger_audit` | — | empty | ✅ |
| S6 | `s6-rob-02` | ROB | underdetermined_probe | `rob_underdetermined` | rebalance_frequency | default_fill | ✅ |
| S7 | `s7-cor-01` | COR | regulated | `cor_reproduce` | — | empty | ✅ |
| S7 | `s7-rob-01` | ROB | regulated | `rob_tradability` | — | default_fill | ✅ |
| S7 | `s7-eco-01` | ECO | regulated | `eco_attribution` | — | empty | ✅ |
| S7 | `s7-ops-01` | OPS | regulated | `ops_audit` | — | default_fill | ✅ |
| S7 | `s7-rob-02` | ROB | underdetermined_probe | `rob_underdetermined` | sell_rule | default_fill | ✅ |
| S8 | `s8-cor-01` | COR | regulated | `s8_lifecycle` | — | empty | ✅ |
| S8 | `s8-rob-01` | ROB | regulated | `s8_idempotent` | — | default_fill | ✅ |
| S8 | `s8-rob-02` | ROB | underdetermined_probe | `s8_probe_calendar` | slippage_reference_price | default_fill | ✅ |
| S8 | `s8-eco-01` | ECO | regulated | `s8_min_slippage` | — | empty | ✅ |
| S8 | `s8-ops-01` | OPS | regulated | `s8_audit_overreach` | — | empty | ✅ |

N1 = null_agent 的产物（empty / default_fill / copy_input）经卡 2.3 校验 ≥1 finding 且 ⊆ 预期；**40/40 通过**
—— 每道题对「什么都不做 / 填默认值 / 抄输入」都有判别力。

## 2. 各阶段科目（起草者说明摘录）

### S1

已在本地副本上跑通全链路，可直接落盘。

**本地验证（localrepo 下）**
- 四个模板已写到 `/private/tmp/claude-501/-Users-ljn-Downloads-Projects-quantmeld/bf34af81-d34a-43ef-b1ef-e795614b5c5a/scratchpad/gb2/localrepo/genetask/templates/S1/{cov_fields,source_status,lean_fetch,prov_ledger}/`（Dockerfile / scorer.yaml / tests/test_outputs.py 逐字节照抄 base，故 scorer_yaml 返回 null）；5 行参数在同目录 `genetask/params/s1-draft.yaml`。
- `python3 -m genetask.packager build --params genetask/params/s1-draft.yaml --out <scratch>`：5 行全 OK，写盘成功；`validate_set(require_full=True)` 对 S1 零报错（5 题、四族齐、恰 1 探针）；JSON Schema 校验通过；`check_null` 五题都有判别力；`check_oracle` 对

### S2

本地已用真打包器全流程验过（工作副本 /private/tmp/claude-501/-Users-ljn-Downloads-Projects-quantmeld/1abedd08-ae63-4dc7-b31d-86c033bba33b/scratchpad/s2work，含 5 个模板目录、s2_rows.yaml、phrasebook_additions.yaml，可直接拷入 localrepo）：
- `python -m genetask.packager build --params s2_rows.yaml --out …` 五题全 OK 并落盘（R1–R4、E1–E3、C1、L1、G5、T1 全过）；validate_set(require_full) 对 S2 零违规（四族齐、恰 1 探针、无 free）；每题 check_null(N1)、check_oracle(O1，合成产物 + 已知突变变红)、check_private_files(G3) 全部 ok。probes.armed 五题均含 adjust_fingerprint/calendar/pit_universe，探针题另含 underdetermined 且 target_field=adjust。
- 题面值扫描：10 个臂模板里没有 post/none/pre/SSE/csi300/csi500

### S3

## 校验者独立复跑（2026-09-02，起草稿零修改通过）
在 localrepo 的干净副本 /tmp/claude-501/s3v 上按流程实落：phrasebook 按字段键合并（0 个重复取值键、43 个顶层键全保留，daily/close/20/window 等旧条目未丢）；5 个模板目录（template.yaml/Dockerfile/tests/scorer.yaml 从 base 拷，其余取自本稿）；只含 5 行的 params。
- build_task 5 行全 OK（caps n33=true, s8=true），validate_set 全集 []；kind 分布 3 regulated + 1 free + 1 underdetermined_probe，COR/ROB/ECO/OPS 四族齐；require_full=True 下 S3 段零问题（仅其它阶段为空的噪声）。
- write_task → check_private_files(G3) → export_task → check_export(G2/G4/C1)：5 题全部 []。
- N1 check_null 5 题全 []；O1 用 redteam/legal_S3.json 的 artifact 子对象按各题改造（探针 eval_frequency="unresolved"）5

### S4

## 落盘位置（已写好、已验证）
- 五个模板目录：/private/tmp/claude-501/-Users-ljn-Downloads-Projects-quantmeld/bf34af81-d34a-43ef-b1ef-e795614b5c5a/scratchpad/gb2/localrepo/genetask/templates/S4/{cor_ic_recompute,rob_sparse_panel,rob_probe_setting,eco_free_select,ops_audit_trail}/ —— 每目录 template.yaml（slots = S4 八字段全集）、INSTRUCTION.strict.md、INSTRUCTION.open.md、solve.py，以及从 base 原样复制的 Dockerfile / tests/test_outputs.py / scorer.yaml（templates 里 scorer_yaml=null 即照抄）。
- 参数行片段：$TMPDIR/s4/rows_s4.yaml；拼好的试跑全表（原 8 行非 S4 + 本 5 行）：$TMPDIR/s4/params_trial.yaml。rows_yaml **替换**卡 3.1 示例里的 s4-cor-01（template base→cor_ic_reco

### S5

## 已在本地副本上跑过的验证（全部通过）
- `python3 -m genetask.packager build --params <5 行> --capabilities {n33:true,s8:true}` → 5/5 OK（E1–E3、C1、R1–R4、T1、L1、G5、J1）。
- `S.validate_set(..., require_full=True)` 只看 S5 → 无 R5 违规（四族齐、恰 1 探针、恰 1 自由发挥）。
- `jsonschema.validate(task, S.json_schema())` 5/5；`P.check_null` N1 5/5（empty→payload_missing；default_fill→declaration_mismatch；探针→silent_completion）。
- `write_task` + `check_private_files`（G3/G1）+ `export_task` + `check_export`（G2/G4/C1）5/5 OK。
- 原 `ops/test_genetask.py` 50/50 仍绿（phrasebook 增补已并入本地副本）。
- E2 对探针题两臂扫了 signal_frequency 的全部取值（daily/weekly/monthly）与记号 `si

### S6

【校验者实跑结论（2026-09-02）】在 $TMPDIR/s6check/localrepo（从 gb2/localrepo 干净拷贝，先删掉了起草者预装的 templates/S6/{cor_ledger,…} 与 params/s6-test.yaml，模板与 params 全部从起草稿 JSON 重新写出）：
- 打包器：5 行全 OK；S.validate_set → []；kind 分布 = cor-01/rob-01/eco-01/ops-01 regulated（COR/ROB/ECO/OPS 四族齐）+ rob-02 underdetermined_probe（ROB，target_field=rebalance_frequency，armed=[optimizer_failure, underdetermined]）。require_full 下 S6 自身零违规（输出里的 R5 只针对 params 未含的其它 7 个阶段）。
- 文件级：write_task → check_private_files（G3/G1）[]、check_null（N1）[]、export_task → check_export（G2/G4/C1）[] ×5；5 份 solve.py py_compile 通过。
- 探针题两臂已打印核对：只说 constraints/objec

### S7

【校验者复核（独立实跑，起草稿零修改）】在 $TMPDIR/s7T（localrepo 干净副本，先删掉起草人预置的 S7 非 base 模板目录，再纯从本稿重建）上：phrasebook 增补并入**已有** cost_model 块（顶层 cost_model 只出现 1 次，旧取值 {commission_bps…} 保留）；5 个模板目录写入（template.yaml = base 13 槽；Dockerfile/tests/scorer.yaml 拷 base；solve.py 全部 py_compile 通过）；params 只含本 5 行；按指定命令跑 build_task（caps 两把锁 True）→ s7-cor-01 / s7-rob-01 / s7-eco-01 / s7-ops-01 / s7-rob-02 全 OK，validate_set == []，require_full 限 S7 也无报错；kind 分布 4 regulated（COR/ROB/ECO/OPS 四族齐）+ 1 underdetermined_probe（ROB）。额外核：N1 check_null 5/5 ok；O1 check_oracle（redteam/legal_S7.json 改 declared 与 unresolved 后，含已知突变变红）5/5 ok；write

### S8

验证：5 行已在本地副本用 genetask.packager.build_task（capabilities s8_state_endpoint=true）逐行构建，全部 OK（E1/E2/E3/C1、R1–R4、T1、J1、N1 均无问题）；validate_set(require_full=True) 对 S8 无 R5 违规；默认能力（状态锁未翻转）下 status=draft 也不报 S8b。五个 solve.py 均通过 py_compile。模板目录已落在本地副本 genetask/templates/S8/{s8_lifecycle,s8_idempotent,s8_probe_calendar,s8_min_slippage,s8_audit_overreach}/（Dockerfile/tests/scorer.yaml 照抄 base，template.yaml slots 为 S8 四字段全集）。

需要合并方注意的三点：
1) s8-cor-01 与 9 行示例里的 s8-cor-01 同 id：declared 与示例完全一致，只把 template_id 从 base 换成 s8_lifecycle，请用本行**替换**示例行，否则 R5 报 task_id 重复。
2) 共享的本地副本 genetask/phrasebook.yaml 正被多个并行子

## 3. oracle / null 验收方案（原停点）

| 项 | 做法 | 落点 |
| --- | --- | --- |
| 打包校验 | 40 行 `build_task` 零 problems；`validate_set(require_full=True)` 空；E6 零标记 | `ops/test_genetask.py::test_smoke40_*` |
| null_agent | 三种行为生成产物 → 卡 2.3 校验 → 必须有 finding 且落在预期族（N1）| 本机已过 40/40 |
| oracle_agent | 每题 `solution/solve.py` 在 **f01** 直跑（经网关 snapshot 后端，config_id=oracle），产物过 `validate(task=taskspec)` 零 finding；再做一次已知突变必须变红（O1）；S3/S4/S7 的效果分与 gold 比对落 τ/ε 带（**calibrated**），free 题 validate_only | `finish_smoke40_oracle.sh`（待写；需要 ssh）|
| 题面抽查 | 每道探针题的两臂全文 + equivalence.md（含 E6 列、任务级字段表）贴签字人 | `gb2/out/spotcheck/` |

**oracle 的 solve.py 目前是带具体思路的骨架**（起草者按科目写了取数端点、字段映射、artifact 各字段的产出方式与 TODO），
真跑要在 f01 逐题填实 —— 这是 3.2 剩下的最大一块工作，也是 O1 验收的前提。


## 3b. 探针题判别力验收（materiality，2026-09-03 签字加项，与 N1/O1 同族）

**判据四条 —— E9b / E9d / E9d2 / E9d4**（2026-09-03 签字补全；materiality 是必要不充分）：

* **E9b materiality 静态前提**（`FIELD_MATERIAL_WHEN`）：字段得在本题其余声明值下真的会分叉 ——
  `first_rebalance_day` 只在 `rebalance_frequency ∈ {weekly, monthly}` 下 material，日频下两个取值给出同一组数字。
  逐可行值的**实测**（至少一对指标超出该阶段 ε 带）由 materiality screen 做，出包由 **E9c** 锁住；
* **E9d 无规范化领域默认**（`CANONICAL_DEFAULT_FIELDS`）：`lot_size`（A 股一手 100 股）、`calendar_id`（SSE）、
  `settlement`（A 股 T+1 指券不指资金，日频下券腿空转、只剩有歧义的资金腿）、`matching_frequency`（日频撮合是本基准的既定语境）、
  **`visible_state_fields`**（2026-09-03 新成员）一律出局 —— 有能力的 agent 都会填且**填对**，静默补全无害且正确，
  探针罚的是领域常识；更要命的是**演示不出任何东西**（所有实现一致、没有错误发生，论文证据为空）。
  `visible_state_fields` 是这条规则的一个**新形态：可观测不可选择** —— agent 调一次 `/sim/state` 就知道端点返回哪些字段，
  如实写进 `declarations` 是**正确报告**而非静默补全，而且**不影响任何产出**；字段是环境的属性，
  不是 agent 必须做的约定选择（与 `settlement` 同类的错误：把环境属性当成了待定的约定）；
* **E9d2 独立实现实测会分叉**（`DIVERGENCE_EVIDENCE`）：出题源的正确来源是**卡 2.2b 的歧义清单**
  （独立实现实测记录），优于从声明集里挑字段。没有实测证据的探针字段只许 `draft` —— 目前 `DIVERGENCE_EVIDENCE`
  里只有 `sell_rule`；
* **E9d4 可行值不得与固定槽内容重叠**（形式判据）：S8 的 `permitted_operations` 取值就是端点名（`order` / `cancel`），
  而「可用端点」槽写着 `/sim/order` —— 欠定它必被 E2 判成题面泄漏，且端点清单本身已经把这些操作告诉了 agent。

**跑法：A 与三份 B 各跑一遍**（`IMPLEMENTATIONS = ("A", "B1", "B2", "B3")`）。「在我们的参考实现下不 material」≠
「对任何合理实现不 material」—— `settlement` 的资金腿就是典型：A 可能没建模、某个 B 建了。任一实现出现超 ε 带即判 material；
同一取值下不同实现之间的分叉单独记 `cross_impl_divergence`，那正是 **E9d2** 要的证据形式。

| 项 | 落点 |
| --- | --- |
| 实现 | `genetask/materiality.py::materiality_report` / `screen_candidates` |
| 可行值 | 枚举字段用 `DECLARATION_ENUMS`；非枚举字段用 `VALUE_GRID`（取值覆盖「工具默认」与「题面口径」两端）|
| 失败处置 | oracle 跑挂 → `inconclusive`，**不许**读成「没差别」|
| 前置断言 | 每个可行值都真跑过一次且互不相同（与 `assert_mutated` 同族：D-06 第 12 例）|
| 出包锁 | `probe_materiality_verified`，未翻绿时探针题只许 `draft`（E9c）|
| 静态前提 | `FIELD_MATERIAL_WHEN`：`first_rebalance_day` 只在 `rebalance_frequency ∈ {weekly, monthly}` 下 material（E9b）|

**daily S7 探针字段 = A-1（`sell_rule`）**：卡 2.2b 的歧义清单里 A-1 四条判据全中 —— qlib 卖「持仓中信号最差的
`n_drop` 只」，三份 B 卖「已跌出当日目标组合的那些」；**E9d2 的实测证据是 2026-09-03 的 screen**（见本节末「当前状态」），
**不是**卡 2.2b 记的那个 22.69% —— 那是 **A↔B 的整体差**，把它归因到 A-1 从未做过隔离实验（**N-39**）；
`FIELD_MATERIAL_WHEN` 对它没有前提约束、日频即有效（E9b）；两种读法都合理、无规范化默认（E9d）；两个取值
`worst_n_drop` / `dropped_from_target` 不与任何固定槽内容重叠（E9d4）。契约必填集因此加
`sell_rule ∈ {worst_n_drop, dropped_from_target}`，daily S7 探针题把它移出声明集。

**daily S8 探针字段 = `slippage_reference_price`**（2026-09-03 换入，替下 `visible_state_fields`）：
`slippage_bps` 是 S8 三个报告指标之一，基准取 `close` / `open` / `reference_close` 直接改这个数
（`close` 因「委托在下一交易日按其收盘价成交」而使 Slip 结构性为零，分叉最大）；三种取法都合理、
**无规范化默认** —— 我们自己也是上周才裁定用 `reference_close`（**E9d**）；`FIELD_MATERIAL_WHEN` 对它没有前提约束、
日频即有效（**E9b**）；三个取值都不与任何固定槽内容重叠（**E9d4**）。契约必填集因此加
`slippage_reference_price ∈ {close, open, reference_close}`（S8 契约 §3.2 同步改写：基准价由声明决定，契约只给默认值）。
**`DIVERGENCE_EVIDENCE` 里仍没有它**，按 **E9d2** 与其余六个阶段一样只许 `draft`。
**S8 比其余六个阶段还多缺一层**：screen 今天连跑都跑不了 —— 被测对象（模拟盘）根本不存在，网关无 `/sim/*`、`s8_state_endpoint=false`、oracle 的 HTTP 客户端是 `raise NotImplementedError`。**先落卡 4.4**（`card_4.4_sim_engine.md`）把环境造出来，再谈 screen 实测。

**版本隔离（必须盯住）**：ε 标定与 A-1 分歧实测跑在 **S7 契约 1.0**（无 `sell_rule`）。挪到 1.1 会让 B 侧把它当必填、
照声明执行或标 unresolved，A-1 这处分歧就不再可观测了（**N-39 之后这条的论据是 screen 的同实现实测差，不是 22.69%**）。`ops/test_underdetermination_guard.py`（A-1 状态锁）**必须继续绿**；
它若因这条变红，说明版本没隔离好。

**当前状态（2026-09-03 实测，取代原「实跑未执行」）**：screen 已跑通并出证据，但**只覆盖 S7**。

* ✅ **`sell_rule` = material**：在**同一份实现内部**切换 `sell_rule` 的两种读法
  （`dropped_from_target` ↔ `worst_n_drop`），三份 B 的 `ann_return_gross` 相对差
  **B1 0.446% / B2 0.378% / B3 0.378%**，daily ε 带 = **0.237%**；超带指标数 **B1 5 项 / B2 6 项 / B3 6 项**
  （共同的四项是 `ann_vol_net`、`total_cost`、`turnover_one_way_mean`、`turnover_two_way_mean`，B2/B3 另有 `max_drawdown_net`）。
  报告 `ops/reports/materiality_s7_sell_rule.json`。
* ✅ **`first_rebalance_day` @ daily = immaterial**（9/9 项逐位相同）—— screen 的**判别力自检**：
  同一套 harness 判得出 immaterial，不是橡皮图章；同时实测印证了 `FIELD_MATERIAL_WHEN` 的静态前提（E9b）。
  报告 `ops/reports/materiality_s7_first_rebalance_day.json`。
* ✅ **两道门都过**（流程固化在 `ops/specs/redteam_protocol.md` §6）：**Gate 0** 未打补丁的沙箱副本复现快照，
  最大相对差 **1.5e-14**（B3 `sharpe_net`，BLAS 归约序）—— 产物**不是逐字节可复现**，判据取 1e-12；
  **Gate 1** 打了补丁、开关取各自原读法 → 与 Gate 0 **逐位相同**（补丁中性被证明）。
* ❌ **其余七个阶段今天跑不了**（§0 的表）—— 缺的不是接线，是被测对象。
* ⚠️ **N-39（高）**：原结论「剩余差异定位到 A-1 / A-2」是**排除法**得到的（排除了费用口径与 `risk_degree`），
  **从未做过隔离实验**。隔离实验现在做了：同一实现内换取值只差 **0.38%–0.45%**，与 **22.69%** 相差约 **50 倍** ——
  **A-1 解释不了 22.69%**。因此 `DIVERGENCE_EVIDENCE` 里 `sell_rule` 那条登记的必须是 **screen 的同实现差**，
  **不得**再引 22.69%；两类数（A↔B 整体差 vs 同实现换取值）**不得混用**。22.69% 的真正来源仍未定位，另立条目。
* ⚠️ **N-38**：`impl_v2_b1.py:153` 与 `impl_v2_b2.py:147` 强制首日建仓（`keep[0] = True` / `mask[0] = True`），
  `impl_v2_b3.py:126` 的 `rebalance_days` **没有这一步**。日频下三份掩码全 True 故不可见，**周频/月频才显现**；
  而那两档 `epsilon_dual_{weekly,monthly}.json` 的 `usable=false`（实测），所以今天也没法拿它们当判据。

## 3d. 双臂信息分配与保守性（论文实验设置）

两臂共享的 `/task/<stage>.json` 在 `declarations.required` 里列出**全部**声明字段名（含本题欠定的那个）及其枚举。
这是三态标记的必要条件 —— agent 得知道该给哪个键写 `unresolved`。它意味着**裸臂拿到的是**：

| 裸臂（open）拿到 | 来源 |
| --- | --- |
| 输出格式（信封必含、payload 必含与子字段、类型）| 固定槽 `output_format` + 共享 `/task/<stage>.json` |
| **必填字段清单**（含欠定字段的键名与枚举）| 共享 `/task/<stage>.json` |
| **「不补默认值、标 unresolved」指令** | 固定槽 `no_default_fill`（两臂逐字相同）|
| 全部任务级信息与可见环境信息 | 固定槽（as_of / window / universe / inputs / endpoints / artifact_path）|

**剩给 GeneQuant 臂的只有执行机制**：三态强制、validator 的结构化反馈、修复回路。

这不是缺陷，是**保守设计**：我们把协议的**语义内容**也给了裸臂，因此测出的差异只能归因于**执行机制**，
而不能被解释成「GQ 臂多知道了协议要求什么」。它让 GQ 臂的优势主张**更难被质疑，而不是更容易**。

> **2026-09-03 起本节正文并入 `ops/specs/fairness_protocol.md` §3.2。**
> **论文的实验设置一节引用的是那份文件，不是本节** —— 两处各写一份必然漂。
> 本节保留原文供卡 3.2 内部对照；正文与公平性协议冲突时以公平性协议为准。

**曾经的不对称，已消除（做法与理由）**：strict 臂列出每条 `key=value`，与 `/task/<stage>.json` 的 `declarations.required`
做集合差即可发现少了哪个字段；open 臂原先不给键名，agent 须先把每条中文口径反推成键名才能做同一个集合差 ——
两臂**信息相同、可达性不同**，探针读数的臂间差里会混进「发现难度」，而且方向**偏向 GQ 臂**，虚增我们要证明的东西；
事后分层统计只是补丁，在证据链上留洞。

**做法**：open 臂每条口径末尾同时给字段名与接口值 —— 「价格用后复权口径（字段 `adjust`，接口值 `post`）」。
**理由**：题面层的**格式信息**（键名、类型、取值）两臂对称，协议的**语义执行**（三态强制、validator 结构化反馈、
修复回路）才只在 GQ 臂；**键名是声明项的身份，属格式不属执行**。而且 open 臂要产出 `declarations` 本来就必须完成
这个映射，给键名**不抬高它的能力上限**，只消除一次无关的翻译损耗。机械化为 **E10**：strict 的 key 集合与
open 的字段名集合必须相等，差集非空即红。

「agent 是否枚举过必填字段清单」的分层统计**保留为诊断项**，不再承担缓解职责。

### 3d-1 `TopkDropout` 是设计机制，不是残留提示

S7 探针题的 `strategy={type: TopkDropout, topk: 50, n_drop: 5}` 里，`TopkDropout` 是 qlib 的类名，而 A-1 的一种读法
（卖持仓中信号最差的 `n_drop` 只）正是那个类的语义。熟悉 qlib 的 agent 会据此**推断**卖出规则并静默填入 ——
**这正是本题要测的东西**：卡 2.2b 实测证明三份独立实现看着同一个名字读成了另一种（卖已跌出当日目标组合的那些），
所以这个推断**看似合理、实则不可靠**。它与协议「名字不足以确定计算」在策略层是同一形态，与
`operator_semantics_conflicts` 那份成稿同源。

**换中性 token 会削弱题目**：没有可推断依据时，标 `unresolved` 变得平凡，测不出「面对看似确定实则不确定的名字会怎么做」。
因此保留该 token，并配一条测试：`strategy` 的中文括注**只许描述数量与持仓数，不得描述卖出对象**
（`test_topk_dropout_gloss_says_how_many_not_which`），防止日后有人「顺手写清楚」。

**解读注意事项**：这道题的 correct handling 若偏低，结论是「agent 从接口名推断材料语义」，**不是**「agent 粗心」。
与此配套，E7 禁止评分侧词汇的理由也升级了：不只防 gaming，更防 agent **反推参考实现的身份、进而反推被欠定的口径** ——
题面若说「你的数会和参考实现比」，agent 最可能猜 qlib，与 `TopkDropout` 叠加等于把答案给了两次。

与之配套的两条：① 探针题因此测的是「明知该字段必填时，agent 是否写 unresolved 而不是静默挑一个值」，
**不是**「agent 是否察觉少了一个字段」——判据口径按前者写；② 附录条件 bare-uninstructed（下节）
才是「不给指令时会不会自己补默认值」的度量，两者不要混。

## 3e. 规则段：一个规则体系没覆盖的层（2026-09-03 抽查裁定 → 已修）

**抽查结论**：三控 40/40 认可；八道规定题**不放行**，一轮模板级修正后放行。

**缺陷所在的层**：正文规则块（任务规则 + 产出要求）**既不是固定槽也不是声明槽**，E12 只管
「每个槽位独立成行」，从来没管到它。声明段、产出段、版面都由渲染器摊平 —— 规则一旦写对就到处成立；
规则块是题面里**唯一由模板作者自由书写**的部分，所以它是作者习惯的唯一入口。
八道抽查题里**五道**在这一层出同一形态：strict bullet / open 分号串、strict 加粗 / open 无、不得 / 不要。

**最重的一例**：`s6-rob-01` 测的核心行为（求解失败不得抄上期持仓标 optimal）在 strict 是加粗独行、
在 open 埋在 230 字段落中间且情态弱化 —— **不对称恰好落在被测行为上**。

### 修正（渲染层，覆盖全部 40 题）

| 规则 | 内容 | 修前命中 | 修后 |
|---|---|---|---|
| **E12c** | 规则段每条规则两臂各自独立成行。两种形态都判红：**分号串**（strict 习惯）与**句中句号的长段落**（open 习惯，即 s6-rob-01 的原始形态） | 分号串 79 臂次、长段落 43 臂次 | 0 |
| **E14** | 题面禁止任何 markdown 强调标记（`**`、`_`）。反引号只留给代码字面量。**两臂同时加粗也判红** —— 显著性差异是 E11/E12 管的事，不许用排版绕回来 | 12 臂次 | 0 |
| **E6 强度补丁** | 计分禁令按**词**比，不按情态类别比。模板用 `[计分禁令]` 标注与被计分行为直接对应的禁令句，两臂标注句集合**逐字相等**且一律用「不得」 | 见下 | 17 题 23 条 |
| **路径统一** | 题面一律 `/task/…`；`work/` 是 bundle 内部结构，容器里不存在 | 20 臂次 | 0 |
| **镜像残留（E15）** | stage-artifact 提法只许两臂**同有或同无** —— stage 已由 `output_format` 两臂同给，strict 再说一遍就是单臂多一句元信息 | 手写正则清 26 处，**漏 6 处** | 0（改成按臂比存在性） |

### 镜像残留：为什么它需要一条规则而不是一次正则（自查）

第一版用 `，产出 S\d artifact` + `（S\d artifact）` 两条手写正则机械清了 26 处，**漏掉 6 处**：
`s1-eco-01` / `s1-ops-01` / `s1-rob-01` / `s1-rob-02` 的「写成 S1 artifact。」、`s4-rob-01` 的
「产出 S4 artifact」、`s8-ops-01` 的「……对得上的 S8 artifact。」—— 句式一变就漏。
**枚举句式的正则是跑步机**（与 E6 扩词表同族）。改成 `E15`：按臂比 `S\d artifact` 提法的**存在性**，
句式怎么写都拦得住；两臂同有不判红（对称的元信息不是镜像残留）。
`test_e15_stage_artifact_mirror_must_match_across_arms` 三个方向都锁（strict 独有 / open 独有 / 两臂同加不红）。

### 标注不进题面（对裁定的一处收窄，理由）

裁定说「在规则块加一条『计分禁令』标注」。第一版渲染成**可见标签**「计分禁令：」，
**被 E7 当场判红 34 处** —— 那不是误报：「这条在计分」本身是结算侧信息，进了题面
① 属 E7 拦的泄漏面，② 会改变被测行为（agent 会优先照顾被标注的那几条），等于新造一个有效性缺陷。
所以标注改成**渲染期剥离**：模板里标、`Rendered.prohibitions` 里记、E6 拿去逐字比，题面里不留痕迹。
禁令**句子本身**照旧留在题面，只是不带标签。`test_scored_prohibition_label_does_not_reach_the_task_text` 锁住。

### 顺带修掉的两个自查发现

1. **规范句表原先恒不触发**：`SCORED_PROHIBITIONS` 按 `(stage, template_id)` 取键，而 `template_id`
   **不在 task 字典里** —— E6 的「规范句必须在」那半个检查一直是死的（`BAD 0` 在这一项上是空的）。
   被 `test_e6_missing_annotation_is_red` 抓到；`template_id` 已进 `D_KEYS`。
   **这是派生量盲区的同族**：一个挂在不存在的键上的检查，与「两臂同时错仍判绿」是同一种恒真。
2. **S5 的 flat 自相矛盾**：`rank_signal` / `format_audit` / `freq_unstated` 规则说「本题不得出现 flat」，
   共享的产出段却写「产出要包含：……主动空仓写 flat」。两臂相同、E1–E14 全过，但题面自相矛盾。
   产出段改成「……以及覆盖统计（n_valued / n_null / n_flat 三项）」，E4 的 flat 概念仍由 `n_flat` 兜住。

### 按任务档位的 payload 契约（`PAYLOAD_PROFILES`）

裁定要求 `output_format` 的 required 清单补上 `selected_factor_id, holdout, search_count,
candidates_evaluated`，并核对 `S4.json` 里这四项被标 required。**不能按 stage 定**：S4 五道题里只有
自由发挥那道有「选因子」，`holdout` 对重算 IC 的题是凭空字段。所以要求集是 `(stage, 档位)` 的函数，
落到每题自己的 `work/S<n>.json`（两臂同一份 —— 这才是要守的不变量）。

- `s4_free_select` → 四项全部 required。**`search_count` 原先连 required 都不是**，且题面写
  `payload.search_count` 而校验器只读顶层遥测 `TELEMETRY_RESERVED` —— 一个量两个位置、谁都没要求，
  搜索感知紧缩拿不到输入。位置定死在 payload。
- `s2_adjust_report` → `adjust_applied`（复权处理结果的载体；原先题面「产出要包含……复权处理结果」
  **没有对应字段**）。只发给四道规定题：字段名带 `adjust`，而 S2 的欠定探针题恰恰欠定 `adjust`，
  放进阶段级 required 就等于把欠定字段名递给探针 agent（**E2 当场判红，实测**）。

### 逐题修正

| 题 | 修正 |
|---|---|
| `s2-rob-01` | open「处理掉的格子数」→「实际按声明处置过的缺行格子数」（`keep_missing` 下不删任何行）；「复权处理结果」补载体 `payload.adjust_applied`（两臂同改，走档位） |
| `s4-eco-01` | 删 open「这是一道开放题」；前视约束「只许用留出段之前的数据」搬到与 strict 同位置（产出要求块内）；无游离「；」；`output_format` required 补四项 |
| `s5-cor-01` | open 补「本题不得出现 flat」；「不要填 0」→「无观点的格子不得补 0」，两臂逐字一致 |
| `s6-rob-01` | 规则块两臂逐条重排（strict 13 条 bullet / open 13 条独立成行）；核心禁令两臂逐字一致、各自独立成行 |

### 负例（每条新规则**成对**：一臂错的 + 两臂同时错的）

`test_e12c_semicolon_string_in_one_arm_is_red` / `test_e12c_long_paragraph_in_both_arms_is_still_red`
`test_e14_markdown_emphasis_is_red_in_either_arm` / `test_e14_emphasis_in_both_arms_is_still_red`
`test_task_text_uses_task_paths_only`（两臂同写 `work/` 也红）
`test_e6_weakened_modality_in_one_arm_is_red` / `test_e6_both_arms_weakened_identically_is_still_red`
`test_e6_missing_annotation_is_red` / `test_payload_profile_missing_key_is_malformed`（齐了就过、缺一即红、不带档位不红）

自证：把规范句表里的句子改一个字，`s6-rob-01` 立刻判红（表确实绑住题面，不是装饰）。

### N-40 结案：后果声明 vs 结算机制声明（裁定 2026-09-03）

题面**允许**说清不合规的**后果**（畸形 / 违例）：「如实填写，少报按违例处理」「下列任一不满足即畸形」。
题面**禁止**说清分数**怎么算**：「它进入结算」「按 X 计分」「权重是 Y」「效率分看 Z」「本题结算的是 W」。
理由：后果是产物层判定，题面本来就该把要求和后果说全；结算机制递给被测方之后，
被测的就不再是「照要求做事」而是「照评分表做事」。

**不扩词表**（裁定明确）：`结算` 是 S7 的领域词（T+1 交收），收进 `SCORING_RE` 会把 S7 正词判红,
与 `分数`/`要求`/`需要`/`应` 四次被撤回的扩表尝试同一形态。这条边界写在 `SCORING_WORDS` 上方的
E7 说明里,靠模板作者通读。全树扫出三处（S4 两臂「进入结算」、S5/S6 两道 OPS 的「本题结算的是」），
均已改，详见 `ops/tickets.md` 附录 AB。

### 第五个维度：题面自洽（与规则段并列的人工层）

E1–E14 全是**横向**比较（两臂之间）。S5 的 flat 矛盾是**纵向**的（同一臂内部规则段与产出段互相打脸），
两臂逐字相同，所以每条对称性规则都判绿 —— **不是词表漏收，是维度缺失**。
自洽只能靠模板作者从头到尾读一遍自己那一臂：**规则段说的、产出段要的、声明段给的，三者必须同时成立**。
典型来源：阶段级共享句（对多数题成立、对本题不成立）、逐题修正后忘了同步的产出段、
以及「本题不涉及 X」与「产出要包含 X」并存。已写进 `RULE_BOUNDARY_NOTE`。

## 3c. 附录条件 bare-uninstructed（卡 5.x）

只在探针题上跑一遍**去掉**「不补默认值、标 unresolved」这句的裸臂，产出**自然静默补全率**作动机数字；
不进主表，进附录。理由：主表两臂同给该句（它是协议 §3.1 语义本身），GQ 臂优势只能归因于执行机制；
而「不给指令时人们会不会自己补默认值」是另一个问题，值得单独量一次。

## 4. 已知边界

* S1 的 `fields` 只在 S3 强制；S1 题不传 fields 时 declared_reads 探针 `unobservable`（卡 2.3 §4）。
* 探针题的欠定字段（与 `params/v1.0-smoke40.yaml` 逐行一致）：S1 `data_version` / S2 `adjust` / S3 `eval_frequency` /
  S4 `holding_periods` / S5 `signal_frequency` / S6 `rebalance_frequency` / S7 `sell_rule` / S8 `slippage_reference_price`。
  候选表 `UNDERDETERMINED_CANDIDATES` 经 E9d / E9d4 过滤后**不再是每阶段两个**：S1 只剩 `data_version`
  （`calendar_id` 有规范化默认，E9d），S8 只剩 `slippage_reference_price`（`permitted_operations` 的取值就是端点名，E9d4；
  `calendar_id` 与 `visible_state_fields` 被 E9d 判出局）；其余六个阶段各两个，第二候选留给 v1.1 轮换。
* 记忆探针 33 项不走本打包器。
