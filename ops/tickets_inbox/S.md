# 收件箱：卡 S（收口一轮，2026-09-13）

**本卡可改路径**：`ops/selfcheck_public.py`、`ops/test_b2.py`、`ops/test_V2.py`、
`ops/test_docs_consistency.py`、`README.md`、`docs/OPERATOR_MANUAL.md`、
`ops/reports/known_limits_v1.md`、`ops/reports/push_result.md`、`ops/tickets.md`、
`ops/tickets_inbox/S.md`、`RELEASE_MANIFEST.json`。**没有碰其它路径**，
工作树里别人未提交的改动（`ops/reports/ambiguity_impact_2.2b.md`、`ops/reports/validator_parity.*`、
`ops/specs/operator_semantics_conflicts.md`、`paper/`）**一个字节没动、没提交**。

证据在 `$GB/scratch/S/`：`selfcheck_before.txt` / `selfcheck_after.txt`（第 1 步两次实跑）、
`tests_targeted.log`（定向测试）、`manifest.log`（重出清单）、`scan_mentions.txt` / `scan_stale.txt`（打树后两遍扫描）。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| N-808 | `ops/selfcheck_public.py:335-336` 第 5 项写死「那一件还没上传到 Release」 | **已修** | 改成 `_missing_public_material_hint()`，与第 4 项**同源**（都读 `ops/release/attachments.json`；按 `role == "public_runtime_material"` 认那一件，**不按文件名写死**），按 `download_url` 空不空分支。这个文件里不再写死任何一句「上传了没有」。两棵树各实跑一次留证：落位前仍「登记在案」但下文打出真地址与 `curl`；落位后第 5 项**绿**。 |
| N-809 | `ops/test_b2.py:84` 读私有标定 `snapshots/v1/calibration.json`，外部落位正确之后仍恒红 | **已修** | 读不到就 `pytest.skip`，读得到（发布方那台）照旧判。**私有 τ 不往公开树里钉**（它不随包发）。前两条断言在 skip 之前已经跑过，不会退化成恒绿；反面门用 `tmp_path`，不受影响。 |
| N-810 | README / 手册 / `--downloads` help 把外部自检说成查「两个附件」 | **已修** | 能不写件数的改成「发布附件」并指向 `ops/release/attachments.json`（件数的单一来源）；必须说数的地方改成三件。 |
| N-811 | `README.md` §2.1 / §5 写「Release 的两个附件」 | **已修** | §2.1 改「三个附件挂在 Release `v1.0.16` 上」；§5 改「Release 的附件 —— 三件都已经挂上去了」。§2.1a 那句「两个附件已经挂上去了」**没动**：下一行自我更正成三件，在上下文里成立。 |
| N-812 | `README.md:174/176` 磁盘预算表只算两个附件 | **已修**（Rfin 原判「登记不修」，本卡顺手做掉） | 下载行补第三件 `42,046,516 B`（三件合计 `981,595,397 B` = 936.1 MiB），解包行补 `84,755,038 B`。**合计 ≈ 10.8 GB、「按 15 GB 准备」不变。** |
| N-813 | `ops/test_V2.py:67` `_main_table_dirs()` 把用户按 README §2.4 出的目录也圈进来 | **已修** | 射程收窄成「仓库自己交付的那批」（`git ls-files` 认得的目录），六件仍逐件查；拿不到 git 退回全扫。同节 `>= 20` 是收窄的下限守卫。**没有放宽这道门想验的东西。** |
| N-814 | `$GB/scratch/C2/extroot2` 的断链软链让 `ops/guard_modes.py` 退 1 | **已闭** | 断链 `repo` 由编排方删除；本卡把余下 `{reference, env, logs, results, snapshots}` **整棵移**到 `/home/ljn/genebench_scratch/C2-extroot2/`（移，不是删），空目录删除。复核：`guard_modes` 退 0「敏感根权限合规（2 个根）」、`ops/test_env.py` **63 passed / 1 skipped**、`$GB/scratch/C2` 下一条软链不剩。 |
| N-815 | `ops/test_V2.py:227` 签字包 `0400` 断言在任何 clone 上恒红 | **已修** | `git clone` 不保留 `0400`（落地 `0600`）。断言改成「模式不含 group/other 位」（`S_IMODE & 0o077 == 0`）：`0400`/`0600` 过，`0440`/`0604` 照样红。逐件 sha256 那一半没动。 |
| N-816 | 「文档说没说假话」的扫描射程漏掉**会打印给用户看的 `.py`** | **口径（本卡登记，未做成工具）** | `$GB/scratch/W/w_scan_stale.py` **只扫 `.md`**，而 N-808 那句假话在 `.py` 里 —— 那类扫描**结构性地看不到它**。下次扫这一类，要把自检脚本（`ops/selfcheck_public.py`）、各 CLI 的 `--help` 与提示文案一起纳入射程。本卡只登记口径，没有改扫描器（不在可改路径内，且本轮纪律「不新增扫描类自查」）。 |
| N-817 | 用户裁定：预算档写进 README 与手册两处 | **已做** | 默认 **100 次调用 / 6,000,000 tokens**、S4 **150 / 9M**、S7 **300 / 18M**（`runner/registry.py::budget_for`，现读不照抄）；撞闸记 `budget_exhausted` 是与 `ok`/`violation`/`timeout` 并列的**收口状态、不是失败**，主表那一格渲染成 `—`（与 `0` / `unobservable` / `n/a` 四者不同）；并写明卡 D2 那六个 run 的分布是 100 次闸下的真实分布、**不调档**。新门 `ops/test_docs_consistency.py::budget_tiers_and_exhausted_status`（两处各 5 require + 1 forbid，双向有牙）。 |
