# v1.0.16 发布收尾报告（2026-09-12）

> 六节，短。逐条票据见 `ops/tickets.md`「发布收尾卡（2026-09-12）」（N-703…N-726）；
> 已知限制终态见 [`known_limits_v1.md`](known_limits_v1.md) 末节；接手指南见 `ops/HANDOFF.md` §19.5。
> **一句话**：v1.0.16 的东西全部就位且可校验；**两个附件已于 2026-09-13 挂上 GitHub Release `v1.0.16`
> 并三重回核** —— 卡 R1 上传、卡 R2 / R3 重打树后各复核一次，回执见
> [`push_result.md`](push_result.md) §7 / §8.1 与 [`release_upload_report.md`](release_upload_report.md)。
>
> **本文正文写的是 2026-09-12 那一轮收尾当时的状态。** 凡涉及 Release 与附件的，现状以本节、
> §一 状态表里标了 2026-09-13 的两行、以及 `push_result.md` §7 起各节为准；§三 的 BLOCKED
> 与 §六 第 1 条按原样留证并各自标了日期（2026-09-13 均已解除）。

## 一、状态表 + 全量数字 + 真 API 用量

| 项 | 值 | 出处 |
| --- | --- | --- |
| 任务集轴 | **1.0.16** `d9ebd5412ac4cc7e…` | `RELEASE_MANIFEST.axes` |
| 公开轴 | **p1.0.0** `3e5ab441a991c411…` | 同上 |
| 参考轴 | **r1.0.23** `dddabe440163b36e…` | 同上 |
| 公开 provider 根 | **`f7dda2899071b07a…`**（本轮换面，旧 `561348660a3175b1…`） | `runner/inject.py:532` |
| 发布清单 | 五条 blocker **全 `satisfied`**、`missing=[]`、**`releasable=true`**、`--check` 退 0 | `RELEASE_MANIFEST.json` |
| 签字包 | 私有 33 件 / 公开 27 件，**一个字节没改**（只读归档） | `ops/reports/signed/` |
| GeneBench 远端（**2026-09-12 那一轮的终值**） | `refs/heads/main` = **`bd0513a47d1ad273d4cc21fdbdfb5604b2487645`**；tag `v1.0.16` 解引用同值（tag 对象 `c9596315993b1811…`）。此后公开树又重打并 force-push 过数轮，**当前终值不写在本文**（进树的文档不记自己所在那棵树的 sha，理由见 `push_result.md` §5）—— 以 `git ls-remote` 实测与 `push_result.md` §8.2 / §8.3 为准 | `git ls-remote` |
| GeneQuant 远端 | **`6ce7664e84e467c39d11bb4ec88209bdae6a7c92`**（本轮无改动，只核不推） | 同上 |
| **Release 附件清单（2026-09-13 现状）** | **已建 Release `v1.0.16`（id `387775425`）；两件附件均 `state=uploaded`**，2026-09-13 上传并三重回核，匿名（不带 token）可下。*留证：2026-09-12 本报告写作当时 `GET /repos/Decilix-Intelligence/GeneBench/releases` 还回 **200 `[]`** —— 当时一个 Release 都没有。* | 2026-09-12 为本卡实测；2026-09-13 见 [`push_result.md`](push_result.md) §7 / §8.1、[`release_upload_report.md`](release_upload_report.md) |
| 两个附件（**已上传**） | provider **782,100,276 B** `33083ff242c64a8f…` / gold 子集 **157,448,605 B** `edc5ea7cf70ffec3…`；两条实际下载地址与完整 sha256 见紧接本表的那张表 | `$GB/release/public_v1/`、`RELEASE_MANIFEST.release_attachments`（两条 `download_url` 均已回填） |

**两件附件的实际下载地址（2026-09-13 起匿名可下）** —— 地址、字节数、`sha256` 与
`RELEASE_MANIFEST.release_attachments` 同源；外部用户自核的两段命令在 `README.md` §2.1a：

| 附件 | 下载地址 | 字节 | `sha256` |
| --- | --- | ---: | --- |
| provider 包 | `https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16/genebench_public_provider_v1.tar.gz` | 782,100,276 | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` |
| gold 子集包 | `https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16/genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` |

<!-- P2-2026-09-13 -->
**第三件附件（2026-09-13 登记，同日下午上传）** —— 与
`RELEASE_MANIFEST.release_attachments` 同源，`ops/release/attachments.json` 是单一来源：

| 附件 | 下载地址 | 字节 | `sha256` |
| --- | --- | ---: | --- |
| `genebench_public_runtime_v1.tar.gz` | `https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16/genebench_public_runtime_v1.tar.gz` | 42,046,516 | `49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f` |

它装的是**公开题集实例**（`reference/tasks/public/v1.0-smoke-public/`，506 件）与
**公开通道标定物料**（`calibration.json` + `epsilon/`，27 件）—— 2026-09-13 Mac 外部验收
报出的缺件 ②③，落位之后 `ops/freeze_v10.py --check-all` 三条轴实测全绿。
**状态：已上传**（2026-09-13，卡 Q）—— 传上**已在的** Release `v1.0.16`，不新建 Release、已在的两件附件一个字节没碰。`state=uploaded`、asset id `561398049`，远端 `digest` 与本地 `sha256` 逐字相同；匿名（不带 token）带 `Range` 的 GET 回 **206**、`content-range` 总长 `42046516` 对得上。`ops/release/attachments.json`、本表、`RELEASE_MANIFEST.release_attachments`（**`n=3 / uploaded=3`**）三处同源。逐步记录见 [`push_result.md`](push_result.md) §8.5。

Release 页：`https://github.com/Decilix-Intelligence/GeneBench/releases/tag/v1.0.16`（id `387775425`）。三重回核（上传后整件下回来重算 sha256、
重打树后两次带 `Range` 的匿名 GET 回 206 且远端 `digest` 与本地逐字相同）见
`push_result.md` §7.2 / §8.1 / §8.2。

**全量 pytest**（`flock $GB/locks/pytest.lock` + `systemd-run --user --scope -p MemoryHigh=5G -p MemoryMax=6G`，
与上一轮同一条命令 `pytest ops/ -q`）：**终值 4511 passed / 9 failed / 33 skipped / 1 xfailed / 0 errors，1305.21 s**
（本卡提交**之后**复跑的那一次，`$GB/scratch/E/pytest_full.log`）。
提交**之前**那一次是 4495 passed / 10 failed / 32 skipped / 1 xfailed / **2 errors**，1326.67 s；
上一轮（最终卡）终值 4443 passed / 6 failed。**9 红逐条归属 —— 没有一条是本卡改动引起的**：

| 条数 | 是什么 | 归属 |
| ---: | --- | --- |
| 4 | `test_lake_baseline.py`（4 条） | 宿主上**别人的 ETL**：湖被写锁 / 停更表清单变了。任务书点名可不算 |
| 1 | `test_env.py::test_gold_only_lives_under_reference_or_snapshots` | 卡 B 的跑前备份 `$GB/scratch/B/backup/**/gold`（24 条）。**不是答案面泄漏**，登记不修（N-726） |
| 1 | `test_env.py::test_no_api_key_material_in_run_dirs` | 别人的 `$GB/scratch/Y1/rh2_*`，是**测试文件自身的夹具字面量**，不是真凭据。已登记 |
| 1 | `test_underdetermination_guard.py` | 要的第三处出处 `ambiguity_impact_2.2b.md` 是**别人未提交的改动**（契约 C：不动别人的半成品） |
| 1 | `test_wrt.py::test_rebudget只动没跑过的行` | `job_id` 缺 `@<机器标识>` 后缀，卡 G1 已登记（N-619 / N-669），本轮之前单跑也红 |
| 1 | `test_e.py::test_报告的全量数字与日志同源_不是手写的` | **本报告自己的同源门**：复跑时本节还写着上一轮的数，它当场红 —— 这正是它该做的。数字改成本次终值后单跑**绿**（`$GB/scratch/E/tests_after.log`） |

两处变化值得记一句：① 上一次红的 `test_gateway.py`（1 failed + 2 errors，栈底是
`duckdb.connect(read_only=True)` 重试用尽）**本次全绿** —— 外部 ETL 的湖写锁是**间歇**的，
这条印证了任务书「持湖写锁那几类不算本卡」的口径；② `test_V2.py::test_十个收件箱都改名merged了_原名一个不留`
上一次红、**本次绿** —— 那是本卡开工时就红的一条（本轮卡号 A/B/C 与收尾卡 v2 撞车，N-725），收口即闭。

**这次全量之后本卡又提交了两次**（`4debc10` 把本节的数字改成上面这一次、`06cd5b0` 把
HANDOFF §19.5.3 那条扫描命令改成走 `d_scan.sh`），**都是文档与清单重出、没有再跑全量**；
受这两次影响的六个测试文件单跑 **128 passed**
（`ops/test_e.py` / `test_release_manifest.py` / `test_V2.py` / `test_final.py` / `test_h.py` / `test_p.py`）。
`ops/mk_release_manifest.py --check` 在每一次提交前后各退 0，`releasable` 始终为 `true`。
`ops/freeze_v10.py --check-all` 实测三条轴**全部与冻结清单一致** —— 本卡零 freeze bump。

**真 API 用量**（`$PY ops/api_usage.py`，机器统计）：**5,036 次真调用 / 133 个 run / 194,204,110 tokens**
（口径：f02 各 run `log/llm_log.jsonl` 里 `decision == "allow"` 计一次，被拒的不计）。
**本轮五张卡（A/B/C/D/E）零模型 API 调用** —— 卡 B 的 `run_oracles --agent oracle` 跑的是参考 `solve.py`，
打的是数据网关（snapshot 后端），不打模型 API。

## 二、本轮完成项与证据路径

### 2.1 六条裁定逐条判

| 裁定 | 判 | 证据路径 |
| --- | --- | --- |
| ① instruments 走重建（公开包 `instruments/` 与 `universe/` 全换 baostock 重建结果、不含 tushare 派生行、`csi1000` 不入包、gold 子集按新成分核一次不一致的重算、`DATA_LICENSE` §5 改写） | **达成** | `ops/reports/public/instruments_switch.md`（换面记录 + §5 逐件比对与完全归因）、`$SNAPSHOTS/public_v1/qlib_provider/instruments/`、`universe/universe_pit.parquet`、`gold_factors_r2/gold_subset_public.json`（41 件逐件 sha）、`DATA_LICENSE:32,165`、`ops/test_a_publish.py`（12 条，含「归因没有余项」那道门） |
| ② 打包（建 `release/public_v1/`、写打包脚本、逐件 sha256 进 `RELEASE_MANIFEST`） | **达成** | `$GB/release/public_v1/`（10 件约 940 MB）、`ops/release/pack_{public_provider,gold_subset}.py`、`ops/release/attachments.json`、`RELEASE_MANIFEST.release_attachments`（已进 `FATAL_KEYS`）、`ops/test_pack_release.py`（21 条）、`$GB/scratch/C/{verify_pkg.json,userwalk.log}` |
| ③ 上传 GitHub Release v1.0.16（两个附件）+ README 真实下载地址与校验命令 | **2026-09-12 本轮：未达成（部分）** —— README 那半**达成**，上传那半 **BLOCKED**。**2026-09-13 卡 R1：已达成** —— Release `v1.0.16`（id `387775425`）已建，两件附件 `state=uploaded` | 2026-09-12 达成的那半：`README.md` §2.1a（真实地址 + 两段校验命令）、`ops/test_d.py` 的双向门；当轮未达成那半的回执：`ops/reports/push_result.md` §2（403 + `contents=write`）、本报告 §三，当轮实测 `GET /releases` → 200 `[]`。2026-09-13 补齐的回执：`push_result.md` §7 / §8.1、`release_upload_report.md` |
| ④ 冒烟集 S8 四题 gold 重出（经网关真跑，不设时间盒） | **达成** | `ops/reports/s8_gold_reissue.md`（8 次零 finding、新旧只差 `produced_at`、`session.json` 逐字节相同）、`$GB/scratch/B/{private,public}/probe_run_oracle.json`、`$GB/scratch/B/backup/reports/`（共享矩阵 6/6 `diff -q` 相同） |
| ⑤ 公开树同步一次到 GitHub（单次提交、同一作者、无 AI 署名）+ `ls-remote` 核对 | **达成** | `ops/reports/push_result.md` §6–§6.7、`ops/reports/release_scan_claude_mentions.md`（全树署名形态 1 条 = 判据表自身）、`git ls-remote` 实测（见 §一状态表）、树内 `ops/test_p.py` 28 passed |
| ⑥ 六节短报告；其余一切问题维持登记不修 | **达成** | 本文件；`ops/reports/known_limits_v1.md` 末节（终态 63 条，本轮 +16）、`ops/tickets.md` 本轮一节（N-703…N-726）、`ops/HANDOFF.md` §19.5 |

### 2.2 做成的事与证据

| 做成的事 | 证据 |
| --- | --- |
| 公开包宇宙定义面换成 baostock 重建结果；gold 子集按新成分**全量重算**（41 件 sha 全变，完全归因：13.5% 的值变 **100%** 落在「成分区段变了」的票上） | `ops/reports/public/instruments_switch.md`、`$SNAPSHOTS/public_v1/gold_factors_r2/`、`$GB/scratch/A/gold_{compare,attrib}.json` |
| 新根的九处跟改 + 两条通道各一次 `check_provider_pin` 与 `--dry` 注入（**反向门仍有牙**：塞清单外文件当场红） | `runner/inject.py:532`、`$GB/scratch/A/gates2.log`、`dry2.log` |
| S8 四题 gold 两条通道各经网关真跑重出一次，**8 次零 finding**；40 列共享矩阵与两份跑批汇总 6/6 `diff -q` 相同 | `ops/reports/s8_gold_reissue.md`、`$GB/scratch/B/{private,public}/` |
| 两个可发布附件打定 + 新写 `pack_gold_subset.py` + 逐件 sha256 进 `release_attachments`；确定性（同 `--built-at` 打两次 8 件逐字节相同）；外部用户口径实走 `sha256sum -c` **0 FAILED** | `$GB/release/public_v1/`、`ops/test_pack_release.py`、`$GB/scratch/C/{verify_pkg.json,userwalk.log}` |
| 上传前六项扫描**全零**（宇宙定义面逐行核、`csi1000` 0 命中、凭据七正则 + 七类文件名 0 命中、探针钥匙 0 命中…）+ `answer_plane_guard --mode container` 正例绿 / 两个反例红 | `ops/reports/release_scan_publish.md`、`$GB/scratch/D/scan_publish.json` |
| README §2.1a 给真实下载地址 + 两段可复制校验命令（**2026-09-12 当时**还如实写明附件会 404；附件 2026-09-13 挂上之后，那段提示已按 `ops/test_d.py` 的双向门同步删去） | `README.md` §2.1a、`ops/test_d.py` 的双向门 |
| 公开树同步到 GitHub：单次提交、同一作者、**无 AI 署名**，`ls-remote` 核对 | `ops/reports/push_result.md` §6.7 |
| 票据合并（N-703…N-726）、HANDOFF §19.5、本报告、已知限制终态 | 本卡 |

## 三、BLOCKED

> **本节是 2026-09-12 当轮的留证，2026-09-13 已解除，原文照录不改一字。**
> 用户按 §六 第 1 条补了 token 权限，卡 R1 当天把 Release 与两个附件都传上去了
> （`push_result.md` §7、`release_upload_report.md`）。解除回执在本节末尾。
> **2026-09-13 又新开了一条、当天即闭合**，写在本节**最末**：第三件附件先登记、后上传。
> 它不是 2026-09-12 那条的复发 —— 是附件清单从两件变成三件之后的新状态。

**当轮只有一条**，且不挡「(b) 自己从公开源建数据面」这条路：

**Release v1.0.16 建不成、两个附件传不上 —— GitHub token 缺 `Contents: Read and write`（N-718）。**
实测 `POST /repos/Decilix-Intelligence/GeneBench/releases` 回 `403 Resource not accessible by personal access token`，
响应头点名 `x-accepted-github-permissions: contents=write`；同一把 token 的读全通（`GET /releases` → 200 `[]`），
无 `x-oauth-scopes` → **fine-grained PAT，仓库权限只给了读**；账号本身是 repo admin，
**账号权限与 token 权限是两回事**。机器上没有第二把凭据。SSH 那条路是通的（所以裁定 ⑤ 做得成），
**两者不互相替代**。补法与照抄的六步在 `ops/HANDOFF.md` §19.5.4 与 `ops/reports/push_result.md` §2.2–§2.3。

**解除回执（2026-09-13，卡 R1，N-727）**：用户给 token 加上 `Contents: Read and write` 之后，
`POST /releases` 与两次 asset 上传全部回 **201**，两件附件 `state=uploaded`，
整件下回来重算 `sha256` 与本地逐字相同。**自本轮起本节归零 —— 发布侧不再有 BLOCKED。**
仍开着的两条（baostock 许可正文、`CITATION.cff`）在 §六 第 3 条，都在用户那一侧、都不挡使用。

<!-- P2-2026-09-13；Q-2026-09-13 闭合 -->
**开过一条、当天闭合（2026-09-13，N-779）：第三件附件 `genebench_public_runtime_v1.tar.gz`
先登记、后上传。** 登记那一刻它的 `download_url` 还是空串，
`RELEASE_MANIFEST.release_attachments` 因此从 `n=2 / uploaded=2` 变成 `n=3 / uploaded=2`。
**那不是回归，是状态真的变了**：`ops/test_e.py::test_附件还没上传时_报告必须把它记成blocked`
是一条**双向门**，清单里一出现空的 `download_url`，它就翻到「报告必须把这件事说出来」那一面。
**当时挡什么**：只落位了前两个附件的机器上，公开任务集轴核不绿（差异全在 `channel_fixtures/`），题也跑不起来。

**解除回执（2026-09-13 下午，卡 Q）**：该件已传上**已在的** Release `v1.0.16`
（不新建 Release，已在的两件附件一个字节没碰），`state=uploaded`、asset id `561398049`，
远端 `digest` 与本地 `sha256` 逐字相同，匿名带 `Range` 的 GET 回 **206**、`content-range` 总长 `42046516`。
`download_url` 已回填，`RELEASE_MANIFEST.release_attachments` 现为 **`n=3 / uploaded=3`**，
清单里再没有空的 `download_url` —— 那条双向门随之翻回另一面。**自本轮起本节重新归零。**

## 四、CONFLICT

**一条，两处原文，按保守方向做并标记。**

* **spec_a** —— 施工契约 C 段：「提交信息中文、说清做了什么，结尾加一行 `Co-Authored-By: …`」。
* **spec_b** —— 任务书【推送与凭据】：「提交作者与提交者均为 深情代码大师 `<2994718175@qq.com>`……
  **不加 Co-Authored-By**，提交信息里一个 AI 厂商名都不许有」。
* **本轮一致的裁断**（卡 C / 卡 D / 本卡同口径）：**内网仓库 `$GB/repo` 的提交按 spec_a**；
  **推到 GitHub 的公开树那次提交按 spec_b**（实测公开树 `%an/%cn` 均为深情代码大师、body 为空、
  全树署名形态 1 条且是判据表自身）。判据：spec_b 整段讲的是 token、SSH key 与**推到 GitHub 的那次提交**，
  射程是 `$GB/release/trees/*` 两棵公开树；`git archive` 不带提交信息，内网 trailer 进不了公开树。
  **若编排方认定射程是全部提交**，本轮 A/B/C/D/E 的十余次提交需要改写重提 —— 契约禁止自行 `amend`。

## 五、红线接触

| 红线 | 本轮接触点 | 结论 |
| --- | --- | --- |
| B1 无 sudo / 不动既有服务 | 卡 B 按 HANDOFF 的方式 `systemctl --user restart genebench-gateway.service` 一次；**没有改任何单元文件** | 未违反 |
| B2 答案面不上执行面 | 最贴近的两处：gold 子集被打成**公开下载附件**、公开树**有意带全部答案面**（用户裁定 N-627 走 B，v1.0.16 起红线 2 改写为**容器边界**）。判据而非承诺：`pack_gold_subset.assert_dest_is_not_on_the_exec_plane()` 硬挡五个前缀、打包脚本无推送开关、包内顶层段名用 `gold_factors`、`answer_plane_guard --mode container` 正例绿两反例红 | 未越界 |
| B3 凭据 | `GITHUB_TOKEN` **只经 HTTPS 头**（`set -a; . github.env; set +a` 注入进程环境），无 `echo`/`cat`/`set -x`，错误文本过 `scrub()` 脱敏；f02 的 `secrets.env` 一次没碰；脚本与测试里无 key 形态字面量 | 未违反 |
| B4 冻结根 | 一个文件都没改。S8 重出会漂的题面已用 `b_restore.sh` 逐件还原成跑前字节 → **本轮零 freeze bump** | 未违反 |
| B5 网关绑定 / 端口 / 网段 / 出向 | 公开实例绑 `192.168.1.48:18081`（脚本自带），未出现 `0.0.0.0`；其余未碰 | 未违反 |
| B6 跑批串行 | 卡 B 两轮跑批都在网关锁内，inner 一律 `--no-batch-lock`，**没有给 `run_oracles` 外套 `gateway_lock`** | 未违反 |
| B7 f02 上跑 runner | 验门命令带 `umask 022` 与 `PYTHONDONTWRITEBYTECODE=1`；卡 C/D/E 全程没连过 f02 | 未违反 |
| 红线 5（`$GB` 全树 `go-rwx`） | 各卡远端命令一律 `umask 077` + 事后 `chmod -R go-rwx`，收尾 `find -perm /0077` 复核为空 | 合规 |
| 内存纪律 | 重活（gold 重算 / 逐件比对 / 打包 / 扫描 / 全量 pytest）全部持锁 + `systemd-run` 封顶；**f01 本轮未 OOM** | 合规 |
| 对外不可撤动作 | 唯一一类：对 GitHub 远端 `push --force` 四次（main 两次、tag 两次），force 掉的都是**我们自己上一轮推的同一棵树**，用户已明文授权 | 如实记 |

## 六、需要用户提供的 / 下一步

1. ~~**给 token 加 `Contents: Read and write`**~~ —— **2026-09-13 用户已补，本条已闭（N-727）。**
   （当轮原文：fine-grained PAT，射程含 `Decilix-Intelligence/GeneBench`；不需要 workflows、不需要 org admin，
   写回 f01 `~/.config/genebench/github.env` 并保持 `0600`；当时这是裁定 ③ 唯一缺的东西。）
   补齐之后 HANDOFF §19.5.4 那六步机械动作由卡 R1 一次跑通，回执见
   `ops/reports/push_result.md` §7 与 `release_upload_report.md`。
2. **确认提交署名口径**（§四）：内网仓库的提交要不要也去掉 `Co-Authored-By`。要统一去掉需要 `amend`/`rebase`，
   契约禁止执行代理自行做。
3. 两条历史遗留的 BLOCKED 仍在：**baostock 许可正文**（`ops/terms/baostock/permission/` 保持不存在，
   不许塞占位文件让锁变绿）、**`CITATION.cff` 的 `authors` / `date-released`**。
4. 三条**可选的清理**，当轮都不挡验收、都属不可逆或动别人现场，交仓库所有者拍板；
   **2026-09-13 用户裁定后前两条已闭**：
   ~~删 `$GB/release/_staging_unpublished/public_v1/` 那份 09-06 旧包（N-714）~~ → **已删**，
   删前现算 `sha256` 核过身份，存根 `$GB/scratch/R2/deleted_staging_pkg.txt`；
   ~~把卡 B 的跑前备份移出 `$GB` 让 `test_env` 那条绿（N-726）~~ → **已移出**到
   `/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/`，一个字节没删，实跑 `-k gold` **3 passed**；
   `csi1000` 的 8.9 GB 公开 gold 是否长期保留 —— **仍开着**（N-733：保留在 f01、不入公开包）。
