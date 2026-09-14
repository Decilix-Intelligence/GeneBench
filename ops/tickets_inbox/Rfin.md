# 收件箱：卡 Rfin（终核卡，2026-09-13）

**本卡只读**：除本文件外没有改动任何文件，没有推树、没有碰 Release。
下面每一条都有实跑留证，命令与输出在 `$GB/scratch/Rfin/`（`tests.log` / `place.log` / `e2e.log` / `scan_stale.txt`）
与克隆树 `/home/ljn/genebench_scratch/Rfin/ghclone`（按裁定③落在 `$GB` 之外）。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| N-808 | **`ops/selfcheck_public.py:335-336` 把「第三件附件还没上传到 Release」写成了硬编码字符串** | **待修（一行）** | 第 5 项走到「登记在案」分支时，逐字打出「它已经打成附件 `genebench_public_runtime_v1.tar.gz` 登记在 `ops/release/attachments.json` 里，但那一件的 `download_url` 还是空串 —— **还没上传到 Release**。等它挂上去……」。该件 2026-09-13 下午已传上（asset id `561398049`，本卡匿名 Range GET 实测 **206**），`attachments.json` 三条 `download_url` 一条不空。同一次运行里第 4 项**已经**打出三条 `curl`，第 5 项紧接着说第三件没上传 —— **一个外部用户在同一屏上读到互相矛盾的两句，而且被劝去等一个已经到位的东西**。第 4 项那段提示是从 `attachments.json` 现算的（`published` / `pending` 两个列表），第 5 项这段却是写死的。改法：把这段提示改成按 `pending` 是否为空分支，或直接删掉「还是空串 / 还没上传到 Release / 等它挂上去」这三句，只留「缺的是整棵公开题集树，它在附件 `genebench_public_runtime_v1.tar.gz` 里，按 README §2.1a 落位之后这一条就绿」。**这是本卡唯一一条会误导外部用户的现在时假话**，也是 `ops/w_scan_stale.py` 结构性扫不到的（它只扫 `.md`）。 |
| N-809 | **`ops/test_b2.py:84` 读的是私有标定，在任何外部 clone 上都是恒红** | **待修** | `test_calibration_gate_passes_and_reports_the_public_tau` 最后一句 `priv = json.loads((cfg.SNAPSHOTS_V1 / "calibration.json").read_text(...))` 读 `$GENEBENCH_ROOT/snapshots/v1/calibration.json`（**私有通道**那份）。本卡实测：`snapshots/v1/calibration.json` 在**三件附件里一件都没有**（`SHA256SUMS` 与 `runtime_SHA256SUMS` 各 0 命中，公开那份落在 `snapshots/public_v1/`）。于是外部用户把三件附件**正确落位之后**跑这条仍然 `FileNotFoundError`。**与 N-770 同形**：一条判据悄悄取决于「跑它的是不是发布方那台机器」，在内网永远看不见。前半截（公开 τ 与 `calibration.sha256` 对得上）在外部跑得通，只有「公开 τ ≠ 私有 τ」这一句跑不了。改法：把最后两行包进 `pytest.skip`（`if not (cfg.SNAPSHOTS_V1 / "calibration.json").exists(): pytest.skip("私有标定不随包发，只有发布方那台有")`），或把私有 τ 的值钉成常量。反面门 `test_calibration_gate_bites_on_sha_mismatch` 用 `tmp_path`，不受影响。 |
| N-810 | README 与手册把外部自检说成查「**两个**附件」，实为三件 | **待修（措辞）** | `README.md:227`（外部步骤代码块的行内注释）、`README.md:238`（紧跟其后的引用块逐项列举）、`docs/OPERATOR_MANUAL.md:64`、`ops/selfcheck_public.py:495`（`--downloads` 的 help）四处都写「两个附件」，而 `ops/selfcheck_public.py` 自己打出来的是「**发布附件落位与 sha256（清单登记 3 件）**」。不挡使用（第 4 项从 `attachments.json` 现算），但这是外部用户读到的**第一个**附件件数。 |
| N-811 | `README.md:703` §5 仍写「Release 的**两个**附件 —— 已经挂上去了」 | **待修（措辞）** | 整段讲的是前两件的上传留证（指向 `push_result.md` §7），但句子的主语是「Release 的两个附件」，读起来就是「这个 Release 有两件」。`README.md:269` 同形（「两个附件挂在 GitHub Release `v1.0.16` 上」），而 §2.1a 的表列的是三件。 |
| N-812 | `README.md:174/176` 的磁盘预算表只算了两个附件 | **登记不修（不挡）** | 「两个附件本身 0.91 GB」「解开之后（两个包一起）1.15 GB」；第三件是 42,046,516 B 下载 / 84,755,038 B 解开，合计被低估约 0.13 GB。与同一份 README §2.1a 的「三个附件……加起来 936.1 MiB，解开约 1.15 GiB」对不上。总额 ≈10.8 GB、建议「按 15 GB 准备」的结论不受影响。 |
| N-813 | 照 README §2.4 出完表再跑 `pytest ops/`，`ops/test_V2.py` 必红 | **登记不修（README 不叫外部用户跑 pytest）** | `_main_table_dirs()`（`ops/test_V2.py:67`）扫 `ops/reports/*` 下**任何**含 `table_main.csv` 的目录，然后 `test_每个出了主表的批都有两张全量指标表` 要求同目录还有 `table_main.md` / `.tex` / `metrics_agent.{csv,md}` / `metrics_stage.{csv,md}` 六件。而 README §2.4 给的那条命令（`mk_tables.py --table main --format csv --out ops/reports/<你的目录>`）只产出 `table_main.csv` + `table_main.axes.json`。本卡实跑复现：`AssertionError: rfin_e2e_table 缺 table_main.md`。**这条门的射程本意是发布方自己重出的那 20 个批**，却把用户自己的输出目录也圈了进去。 |
| N-814 | **N-795 仍然红**（卡 Q 已报，本卡实测复现，仍没人清） | **待清（一条命令）** | `ssh finance01-ts` 上 `ops/guard_modes.py` 退 1：「读不到模式 `/data/shared/genebench/scratch/C2/extroot2/repo`」—— 卡 P2 按裁定③把目标整棵移走、断链软链留在原地。**只影响发布方内网**：本卡在克隆树 + 外部 `GENEBENCH_ROOT` 上跑 `ops/selfcheck_public.py` 第 6 项（网关起得来）是**绿的**（4 秒起来、`/healthz` 200），所以**不挡外部用户**，与卡 Q 交接里「挡终核卡第 6 项」的预判**不一致，以本卡实测为准**。挡的是发布方这台的网关起停（单元的 `ExecStartPre` 就是这道门）。照抄：`ssh finance01-ts "rm -f /data/shared/genebench/scratch/C2/extroot2/repo && /data/shared/genebench/env/bin/python /data/shared/genebench/repo/ops/guard_modes.py"`，看到「敏感根权限合规」才算好。顺带判 `$GB/scratch/C2/extroot2/reference`（指向答案面的软链）要不要一起清。 |
| N-815 | `ops/test_V2.py::test_签字包逐件sha256对得上_且都是0400` 在任何 clone 上恒红 | **登记不修（卡 Q 已判过）** | `git clone` 不保留 `0400`，落地 `0600`（本卡实测 `known_limits_v1.md 不是 0400：assert 384 == 256`）。 |

## 本卡实跑到底的两条（留证，不是票据）

* **N-770 终验通过**。在克隆树上、**不加任何软链**（`find $GB -type l -lname '/data/shared*'` = 0 条）、
  外部 `GENEBENCH_ROOT` 下，把 `m6_public` 里 **s1/s2/s3 三题双臂 6 个真 run** 拷进
  `$GENEBENCH_ROOT/runs_in/rfin_e2e/`，走完 **结算 → 入库 → 出表**：
  `score_runs` `runs: 6；问题: 0`（标定 / 题集根 / 网关日志三处都打印成外部根下的路径，τ=`0.9839810664562939` 是公开那份）；
  `results_db ingest` `{"added": 6, ..., "protocol_version": "geneprotocol_v1@d6fbcaa08302"}`
  —— **正是卡 D2 报「协议轴反算不出」的那一步**；
  `mk_tables --table main --format csv` 出 **24 列**（5 身份 + 19 指标），表头逐字与 README §2.4 的口径相同。
* **裁定② 终验通过**。一棵**有 `origin`** 的干净 clone + 外部 `GENEBENCH_ROOT` 上
  `ops/mk_release_manifest.py --check` **退 0**；`ops/test_P1.py` 19 passed / 1 skipped，
  其中 `test_清单在有remote与没有remote的同一棵树上逐字节相同` 与它的反面门
  `test_这条机器无关性比对自己有判别力` 都绿。
