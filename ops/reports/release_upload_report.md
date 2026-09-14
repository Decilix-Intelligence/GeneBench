# Release 上传轮 短报告（2026-09-13）

> 三张卡：**R1 上传** / **R2 清理与同步** / **R3 收口**。本报告**短**，只记判与数。
>
> **读之前先看这一句（2026-09-13 卡 W 加）**：本报告记的是 **R1–R3 那一轮**的判与数。
> 之后 **卡 F** 与 **卡 W** 又各重打并推过一轮，所以**文中所有 sha、公开树件数、
> pytest 数字、已知限制条数与票据末号都是那一轮的留证，不是当前值** ——
> 按口径 `HANDOFF.md` §19.6.6「树内不记终值」，当前终值不写在树里。
> 要核「你拿到的是不是发布的那一棵」，用自核不变量：
> `git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16`，三者同值即是。
> 详细流水账在 `ops/reports/push_result.md` §7 / §8.x，手册收口在 `ops/HANDOFF.md` §19.6，
> 票据在 `ops/tickets.md`「Release 上传卡（2026-09-13）」一节（N-727…N-742）。

---

## 一、做了什么

### 1.1 `HANDOFF.md` §19.5.4 的六步，逐条判

| 步 | 该做什么 | 判 | 一句话 + 证据 |
|---|---|---|---|
| 1 | token 加 `Contents: Read and write` | **达成**（用户侧） | 写回 f01 `~/.config/genebench/github.env`（`0600`）。卡 D 那次 `POST /releases` 的 **403** 随之消失。 |
| 2 | 建 Release + 传两个附件 | **达成** | `POST /releases` **201**（id `387775425`，**复用**远端已有 tag `v1.0.16`，没建第二个）；两件 asset **201 / `state=uploaded`**。782 MB 那件第一次 `BrokenPipeError` 停在 `state=starter`，重试版脚本删旧重传，第 2 次一次过（82 s / 9.5 MB/s）。`$GB/scratch/R1/release.log` |
| 3 | 回填 `attachments.json` 的 `download_url` | **达成** | 两条都取自 API 回的 `browser_download_url`。`ops/release/attachments.json` |
| 4 | 重出 `RELEASE_MANIFEST.json` | **达成** | `uploaded 0→2`、`releasable` 仍 `true`、未闭合 blocker **0**、`$PY ops/mk_release_manifest.py --check` **退 0** |
| 5 | 删 README §2.1a 那段「还没挂上去」 | **达成（两处）** | §2.1a 与 §5 一起改口 —— `ops/test_d.py` 的双向门只认 §2.1a，但只改一处会留下「门是绿的、文档仍在对外说假话」。标 CONFLICT，见 §五。 |
| 6 | 重打公开树 → force-push main + tag | **达成（三轮）** | **2026-09-13 R1–R3 轮终值（留证，非当前值；卡 F、卡 W 之后又各推过一轮）**：`refs/heads/main` = **`f466f1c91481acfc0c5cf87235d5e82b601d8190`**；tag `v1.0.16` **移到新 commit**（对象 `bae1438986fc…`，解引用同值）。理由见 `push_result.md` §8.0a。 |

**上传前六项扫描**（`$GB/scratch/D/d_scan.sh`，自带 `heavy.lock` + 内存封顶）本轮**又跑了一次**：
`PASS=true`、`blocking={}`、两个 sha 与登记表一致、**rc=0**，才开始传。`$GB/scratch/D/scan.log`

### 1.2 三条清理，逐条判

| 清理 | 判 | 一句话 + 证据 |
|---|---|---|
| ① 删 `$GB/release/_staging_unpublished/public_v1/` 那份 2026-09-06 旧包（N-714） | **做了** | 删前现算 sha256 核身份（`c42c33ee…` / 782,040,927 B / `code_head e6424687…`，与 `final_report.md` 一致），存根 `$GB/scratch/R2/deleted_staging_pkg.txt`。删前 `grep` 过全仓库 + `$GB/scratch`：引用它的**全是叙述性文档**，没有任何测试/清单/脚本把它当落点。 |
| ② 卡 B 的跑前备份移出 `$GB`（N-726） | **做了，转绿** | 128 件整棵 `mv` 到 `/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/{private,public,reports}/`（`go-rwx`），原地留路标，**一个字节没删**。`ops/test_env.py -k gold` → **3 passed**（含判别力反例，门不是被放宽成恒绿）。 |
| ③ `csi1000`（8.3 GiB / 792 件）保留在 f01、不入包（N-733） | **确认 + 写明** | 两条独立证据：`pack_gold_subset.py` 源根写死 `gold_factors_r2/`（下面只有 `csi300`/`csi500`）；两个已发布附件的逐件校验和里 `csi1000` 命中 **0 行**。「保留但不发」写进 `README.md` §2.1a、`ops/data_cards/gold_subset_v1.md`、`known_limits_v1.md`。 |

### 1.3 不同源说明（用户点名必须显式写明）

**calibration / τ / ε 建在旧 gold 上，而 gold 子集已换成 baostock 名单 —— 阈值与当前 gold 名单不同源，
重算排 v1.0.17。本轮不重算。** 写在用户点名的**两处**：**`README.md` §2.1a** 与 **`DATA_LICENSE` §6**
（新增整节，另在一页速览加一行）。后果一句话：**分可复现，但判分用的那条线是跨名单的，
贴着阈值的边界样本可能判反。**（N-732 / N-734）

---

## 二、两个附件：实际下载地址、字节数、sha256

两件**匿名可下，不需要 token**。

| 附件 | 实际下载地址 | 字节数 | sha256（本地） | sha256（下载回核） |
|---|---|---:|---|---|
| 公开 provider 包 | `https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16/genebench_public_provider_v1.tar.gz` | **782,100,276** | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` | **同值** `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` |
| 公开 gold 子集包 | `https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16/genebench_public_gold_subset_v1.tar.gz` | **157,448,605** | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` | **同值** `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` |

**「下载回核」是怎么核的**（三重，互相独立）：

1. **卡 R1**：从 API 回的 `browser_download_url` 把两件**整个下回 f01** 重算 `sha256sum`，与本地逐字相同；
   随后又把 **README §2.1a 那段命令原样抠出来**在空目录里跑了一遍（匿名、不带 token）——
   包体 **2/2 OK**，解包后包内 **28,706 行**逐件校验**全 OK**。`$GB/scratch/R1/userwalk.log`
2. **卡 R2**：核 GitHub 自己算的 asset `digest` 字段，与本地 sha256、与 `attachments.json` 三处逐字相同。
3. **卡 R3**：匿名带 `Range: bytes=0-0` 的 `GET` 实测，两件都回 **206**，
   `content-range` 总长分别是 `782100276` / `157448605`。`$GB/scratch/R3/asset_liveness.log`

包内校验清单口径（免得下一个人对不上数）：`SHA256SUMS` 实测 **28,658 行**，
`MANIFEST.files` = **28,656** —— 差的 2 行是清单里多列了 `MANIFEST.json` 与 `README.md` 自身，
不影响 `sha256sum -c`。

---

## 三、两个远端 sha 与 tag：**2026-09-13 R1–R3 轮终值（留证，非当前值）**

> **这一节是那一轮的留证，不是现状。** 卡 F（2026-09-13）与卡 W（2026-09-13）之后
> 又各重打并推过一轮，下表的 sha 与件数都已经换过，**不要拿它去跟 `git ls-remote` 的结果比对** ——
> 对不上是预期的。当前终值按口径 **不写在树里**（`HANDOFF.md` §19.6.6），只记进内网仓库的
> `push_result.md` §8.x。自核请用：
> `git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16`，**三者同值即是**。

| 远端 | ref | 值（**那一轮**） | 备注 |
|---|---|---|---|
| GeneBench | `refs/heads/main` / `HEAD` | **`f466f1c91481acfc0c5cf87235d5e82b601d8190`** | 2,187 件、单次提交、作者=提交者 **深情代码大师 `<2994718175@qq.com>`**、body 空、**零 Claude / Anthropic 署名形态** |
| GeneBench | `refs/tags/v1.0.16` | 对象 `bae1438986fc2313d45cec4ffad1c05227a2de3c` | annotated；`^{}` 解引用 = `f466f1c9…`。**本轮移到了新 commit**，理由 `push_result.md` §8.0a |
| GeneBench | Release | id `387775425` | 两件附件 `state=uploaded`；`target_commitish` 每轮 force-push 后 `PATCH` 到当轮新 commit（回 200） |
| GeneQuant | `refs/heads/main` / `HEAD` | **`6ce7664e84e467c39d11bb4ec88209bdae6a7c92`** | 本轮**无改动，只核不推**；推前 = 推后 = 本地树 |

**三条版本轴本轮一条都没动**：任务集 `v1.0.16` / 参考轴 `r1.0.23` / 公开轴 `p1.0.0` ——
这也正是「不新建版本号、tag 跟着移」的理由。

---

## 四、BLOCKED / 还欠什么

### 4.1 ~~⚠ 唯一一条**挡外部用户**的~~ —— **2026-09-13 卡 F 已闭合（N-739），本节原样留证**

> **这一小节写的是 R1–R3 那一轮的状态，三句话到今天都已不成立。**
>
> **现状（2026-09-13，卡 F 做、卡 V 在全新 clone 上复核）**：
> `ops/reports/publish_report.md` 那一格已改成「已建 Release `v1.0.16`（id `387775425`）、
> 两件附件 `state=uploaded`」，**门认的子串 `附件清单为空` 全文 0 命中**；
> 在克隆下来的公开树里实跑 `ops/test_e.py ops/test_d.py` 是 **31 passed / 1 skipped**，**没有红**。
> 所以下面三句 ——「还写着」/「当场红」/「clone 公开树跑 pytest 会看到」—— **都不再是现状**，
> 按 §19.6.6 的口径**原样保留作留证**，不删。

**（以下为 R1–R3 那一轮的原文，留证）**

**`ops/reports/publish_report.md` 里还写着「一个 Release 都没有，附件清单为空」。**
`ops/test_e.py::test_附件还没上传时_报告必须把它记成blocked` 那条**双向门**当场红。
**后果**：外部用户 clone 公开树跑 `pytest ops/` 会看到这一条红，而且它属「文档对外说假话」。
改法逐字在票据 **N-739**（门认的是**子串** `附件清单为空`，那个子串必须消失，
不能用「原样留证 + 加一句已不是现状」的写法）。**改完要重打树重推**（命令见 `HANDOFF.md` §19.6.5）。
R1 / R2 / R3 三张卡都**按并发施工规则没碰**——**请派一张有该路径的卡**。

### 4.2 还欠**用户**的两件（都不挡使用）

| 欠什么 | 现状 |
|---|---|
| **baostock 许可正文** | `ops/terms/baostock/permission/` 按裁定**保持不存在**，**没有塞任何占位文件让锁变绿**。包内 `MANIFEST.license` = `state: granted` / `text_in_repo: true` / `published: false` —— 「口头已取得」与「有原文可查」是两回事，后来的人只能读到后者。 |
| **`CITATION.cff` 的 `authors` / `date-released`** | 待用户提供。 |

### 4.3 不挡、已登记、待别的卡

~~`ops/reports/s8_gold_reissue.md` 第 45 / 88 / 116 行三处证据路径指向旧备份地址（N-731）。~~

**2026-09-13 卡 F 已闭合**：三处已定点改成 `/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/`，改前 `ls` 实测三棵都在。
**本节至此为空 —— 没有「不挡、已登记、待别的卡」的条目了。**

---

## 五、红线接触（B1–B7，逐条；**一条都没违反**）

| 红线 | 接触在哪 | 怎么守住的 |
|---|---|---|
| **B1** 无 sudo / 不改系统服务 | 没接触 | 全程没有 `sudo`，没有改动任何系统服务或定时任务。 |
| **B2** 答案面不上执行面 | **接触** | ① gold 子集包**本就是要对外发的那一份**（用户 2026-09-12 明文裁定 ②），卡 R1 为「下回来核 sha」在 `$GB/scratch/R1/userwalk/` 下短暂落盘并解包，核完立刻 `rm -rf`（连 `tar.gz` 一起删），删前查过没有任何名为 `gold` 的路径段、没有 `oracle_artifact.json` / `slice.parquet` / `n_days_check.json`。② 反向做了一件**加固**：把卡 B 跑前备份里 24 条 `…/gold` offender 整棵移出 `$GB`，`test_gold_only_lives_under_reference_or_snapshots` 由红转绿。**全程没有任何东西进 f02、进容器、进 bundle。** |
| **B3** 凭据 | **接触** | `GITHUB_TOKEN` 只经 `set -a; . ~/.config/genebench/github.env; set +a` 注入进程环境，**只作为 HTTPS `Authorization` 头使用**；脚本里有 `scrub()` 把任何出错文本里的 token 换成 `<token:redacted>`。**没有 `echo` / `cat` / `set -x`，没有进 argv、脚本文件、日志、提交或任何对话回复。** SSH key 没改、没生成新 key、没动任何 ssh 配置。 |
| **B4** 冻结根 | 没接触 | `genetask/templates`、`genetask/params`、`ops/specs/artifact_schema`、`reference/` 模块与 `solve.py` **一个字节都没碰**。三条版本轴一条都没动，**没有 freeze bump**。 |
| **B5** 网关绑址 / 端口 / 网段 / 白名单 | 没接触 | 没碰网关、端口映射、compose 网络或出向白名单。`$GB` 下新建的一切全程 `umask 077` + `chmod -R go-rwx`，守门审计 0 件违例。 |
| **B6** 跑批与真跑串行 | **不适用** | 本轮**没有任何打网关的批任务、没有真跑模型 API**，因此没有需要拿 `gateway_lock` 的场合。 |
| **B7** f02 上跑 runner 的 umask | 不适用 | **本轮完全没碰 f02。** |

**内存纪律**：本轮唯一的重活是 `d_scan.sh`（脚本自带 `heavy.lock` + 封顶）；
全量 pytest 与每次定向测试都拿 `flock $GB/locks/pytest.lock` + `systemd-run --user --scope -p MemoryMax=6G`；
没有在 f01 留常驻轮询循环。

---

## 六、终值数字

| 项 | 终值 | 出处 |
|---|---|---|
| **全量 pytest**（`ops/`） | **4,515 passed / 9 failed / 33 skipped / 1 xfailed**，22 分 26 秒（**2026-09-13 R2 实测，留证**） | 卡 R2 实测，`$GB/scratch/R2/fulltest.log`。**卡 R3 未重跑全量**（本卡只改文档与登记）。9 条红逐条归因在 `known_limits_v1.md` 的 R2 一节 —— 8 条是环境 / 别人的 scratch / 别人的半成品；第 9 条**当时**是真红（§四 4.1），**已由 2026-09-13 卡 F 闭合（N-739）**。**外部用户看到的是绿的**：卡 V 在全新 clone 的公开树里实跑 `ops/test_e.py ops/test_d.py` 得 **31 passed / 1 skipped** |
| **真 API 用量** | **5,036 次真调用 / 133 个 run / 194,204,110 tokens** | `$PY ops/api_usage.py` 机器统计，卡 R3 本轮**重跑复核**，与上一轮**同值** —— R1 / R2 / R3 三张卡**一次真 API 都没打** |
| **已知限制** | R1–R3 收口时 **67 条**；**2026-09-13 卡 W 并入卡 V 的九条之后为 76 条** = 已修/已闭 26 · 设计性 11 · v1.1 5 · 登记不修 32 · **BLOCKED 2** | **权威出处是 `known_limits_v1.md` 的最末一节**（R3 一节记 63 → 67，W 一节记 67 → 76）。**这个数每收口一次就变，以那份文件为准，别在别处记死。** |
| **票据** | R1–R3 收口时到 **N-742**；卡 W 之后到 **N-747** | `ops/tickets.md`「Release 上传卡（2026-09-13）」与「卡 W（2026-09-13）」两节。**末号每收口一轮就变，以 `ops/tickets.md` 为准。** |
| **发布清单** | `releasable=true`、未闭合 blocker **0**、`uploaded=2`、`$PY ops/mk_release_manifest.py --check` **退 0** | `RELEASE_MANIFEST.json` |
| **公开树** | **那一轮**：2,187 件 / 单次提交 / 署名形态 **1 条**（自指，既定口径保留）/ 技术事实 447 条。**件数每重打一次就变，按 §19.6.6 的口径不在树里记死** | `ops/reports/release_scan_claude_mentions.md` |

**外部用户今天能走通的路**：既可以 (a) 从 Release 直接下两个附件（地址与校验命令见 §二，
卡 R1 原样演练过一遍），也可以 (b) 自己从公开源重建数据面（README §2.1a）。
**§19.5.2 里「③ 上传 GitHub Release = 未达成（BLOCKED）」那一格，到本轮为止已经闭合。**
