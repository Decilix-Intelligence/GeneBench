# 卡 V（外部用户视角复核，2026-09-13）

> 本卡**只读复核**卡 F 那一轮的发布，不重做它的活。七件逐件自己动手跑过，
> 命令与实测输出在 `$GB/scratch/V/`（`clone.log` / `anon.log` / `grep.log` / `pytest.log`）。
> **本卡没有改任何代码、没有推树、没有碰 Release、零模型 API 调用。**

## 一、复核通过的（与卡 F 所报逐字相符，无需再动）

| 件 | 实测 | 判 |
|---|---|---|
| 两个远端 `ls-remote` | GeneBench `refs/heads/main` = `HEAD` = `refs/tags/v1.0.16^{}` = `5e4e179e1603236117f8b27f3530a5dc4cec6612`；annotated tag 对象 `2f49fa626faaf54157789dd6da68e455b32e6dd1`；GeneQuant `6ce7664e84e467c39d11bb4ec88209bdae6a7c92` | **符**，tag 解引用 == main |
| 全新空目录 SSH `clone --depth 1` | 一次成功，`HEAD` = `5e4e179e…`，2,189 件 / 33 M，作者=提交者 深情代码大师，body 空 | **符** |
| 克隆树里跑 `ops/test_e.py ops/test_d.py` | **31 passed / 1 skipped**（skip 是 `test_本卡写的文件里没有署名形态[D.md]`，按绝对路径找已改名的文件，内网同样 skip） | **符** |
| 匿名（不带 token）Release 对象 | `id 387775425`、`tag_name v1.0.16`、`target_commitish 5e4e179e…`（**有 ref，不悬空**）、`draft=false`、`prerelease=false`、两件 asset `state=uploaded` | **符** |
| 匿名附件 `Range 0-0` | 两件都 **206**，`content-length: 1`，`content-range` 总长 `157448605` / `782100276`；GitHub 的 `digest` 字段 = `sha256:edc5ea7c…` / `sha256:33083ff2…` | **符** |
| 三处登记比对 | 上面的字节数与 sha256 与 `ops/release/attachments.json`、`RELEASE_MANIFEST.release_attachments`（`n=2` / `uploaded=2`）**逐字相同** | **符** |
| 不同源说明 | 克隆树 `README.md:259` 与 `DATA_LICENSE:201/222/223`（另 §表第 34 行）都写了「阈值与当前 gold 名单不同源、本轮不重算、重算排 v1.0.17」 | **符** |
| csi1000 不入包 | 用**包内校验清单**（不解包）：`SHA256SUMS` 28,658 行 **0 命中**、`gold_subset_SHA256SUMS` 46 行 **0 命中**；出现的宇宙只有 csi300 / csi500。包内 `MANIFEST.json` 那 2 处命中是**显式声明「csi1000 不入本包」**的说明文字 | **符** |
| 署名形态 | 克隆树工作树 462 条 `claude`/`anthropic` 命中**逐条都是技术事实**（被测 harness 目录名、`anthropic_messages` 线型、白名单与定价表里的域名、报告里对判据本身的描述）；`.git` 整棵**除 `.git/index` 里的文件路径外 0 命中**，唯一的提交对象无 trailer、body 空。**判成 AI 署名的：0 条** | **符** |

## 二、新登记（本卡发现，卡 F 漏掉；**登记不修**，按纪律不开新票、不改别的文件）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| N-? | **`ops/HANDOFF.md` §19.6.1 的「终值」表指着上一轮的 sha，而它自己给了核对命令** | **block · 待有该路径的卡** | 内网 = 公开树逐字节相同。`ops/HANDOFF.md:1976` 写 `refs/heads/main` = `f466f1c91481acfc0c5cf87235d5e82b601d8190`、`:1977` 写 tag 对象 `bae1438986fc…`、`:1981` 写「公开树现状：2,187 件」。**同一行的「怎么核」列就是 `git ls-remote`** —— 照着敲实际回 `5e4e179e…` / `2f49fa62…`，件数实测 **2,189**。三处全对不上。**后果**：接手的人或外部用户照着自核会判成「拿到的不是发布的那一棵」。根因：卡 F 重打树换了 sha，而这份文件不在卡 F 的路径内。**改法（一处即可）**：把该表抬头改成「**2026-09-13 R1–R3 轮终值；卡 F 之后又推过一轮，当前终值以 `git ls-remote` 现查为准**」，三行值原样留证。 出处：卡 V。 |
| N-? | **`ops/reports/release_upload_report.md` §4.1 仍在说「有一条真红、文档在对外说假话」** | **block · 待有该路径的卡** | `:84` 写「**`ops/reports/publish_report.md` 里还写着「一个 Release 都没有，附件清单为空」**」、`:85` 写那条双向门「当场红」、`:86` 写「外部用户 clone 公开树跑 `pytest ops/` 会看到这一条红」，小节抬头还是「⚠ 唯一一条**挡外部用户**的」。**三句现在全是假的** —— 本卡在克隆树里实跑 `ops/test_e.py ops/test_d.py` 是 **31 passed / 1 skipped**，那个子串在 `publish_report.md` 里 0 命中。这正是卡 F 被派去消灭的那一类「对外说假话」，只是换了个文件。**改法（一处即可）**：§4.1 抬头与正文加一句「**2026-09-13 卡 F 已闭合（N-739），本节原样留证**」。 出处：卡 V。 |
| N-? | **`ops/HANDOFF.md` §19.6.4「还欠什么（按挡不挡排）」第一行仍把已闭合的事列成「挡」** | **block · 待有该路径的卡** | `ops/HANDOFF.md:2023` 那一行仍写「⚠ `publish_report.md` 里「附件清单为空」那一格 | **挡** … 一行即绿，改法见 N-739。改完**要重打树重推**。| 施工侧，派一张有该路径的卡」。N-739 已由卡 F 闭合（`ops/tickets.md` 自己写着「已闭合」）。这是全仓库最被人当真的一张「还欠什么」表，不改会让下一张卡重做一遍已经做完的事。**改法**：该行状态改成「**已闭合（2026-09-13 卡 F，N-739）**」或整行移出该表。 出处：卡 V。 |
| N-? | **公开树里 `push_result.md` §8.1 / §8.2 的标题说「公开树里没有这一小节」，而它们就在公开树里** | **major · 内网已有修正文，只差一次重推** | 克隆树 `ops/reports/push_result.md:454` / `:536` 两条标题都带「**公开树里没有这一小节**」。读者在公开树里读到一节说自己不在公开树里 —— 自相矛盾。**内网仓库已经不缺这句更正**：卡 F 的 §8.3（内网 `:615`）写了「那两句说的是它们各自那一轮的树…原样保留作留证，别照它去判树是不是漏同步了」。但 §8.3 是推完才提交的，**不在已推的树里**。所以这一条**不需要写新文字，下一次重打树自然带上**。同源的还有 §5 对 `§6`/`§6.7` 的同一条更正 —— 这个坑一轮踩一次，已经第三次。 出处：卡 V。 |
| N-? | **`RELEASE_MANIFEST.json` 的 `package.parts` 里那条形态 A 三处过时，且与同树 README 互相打架** | **major · 登记不修** | 那一条是 `{"part": "已打好的公开数据包（形态 A，今天 publishable=false）", "bytes": 788422669, "ship": "许可到位后发"}`。① `publishable` 实际是 **true**（包内 `MANIFEST.license.publishable=true`，`blockers.data_license_text.satisfied=true`）；② 「许可到位后发」—— 它 2026-09-13 **已经发了**，同一棵树的 `README.md` §2.1a 明写「两个附件已经挂上去了…匿名就能下」；③ `788,422,669` 不是已发的任何一件（已发的 provider 是 `782,100,276`），它是卡 R2 按 N-714 **删掉的**那份 `_staging_unpublished` 旧包。`RELEASE_MANIFEST.json` 是机器可读的权威件，三条里任何一条都够让人对「这个包到底能不能用」判反。**改法**：改 `parts` 的源（`ops/mk_release_manifest.py` 那一条的字面量）后重出清单 —— 属别的卡的路径。 出处：卡 V。 |
| N-? | **`RELEASE_MANIFEST.json` 的 `blockers[data_license_text].blocks` 正文三句全已不成立** | **major · 登记不修** | 原文：「形态 A（冻结包下载）：包只落 `$GB/release/_staging_unpublished/`，`MANIFEST.license.publishable=false`，外部用户拿不到包」。实测：那个目录卡 R2 已删；包内 `publishable=true`；两件附件本卡**匿名 206 拿得到**。该条 `satisfied=true`，所以不闸任何东西，**但正文在骗读许可的人**。与上一条同源、同一处改。 出处：卡 V。 |
| N-? | **`ops/reports/release_upload_report.md` §三 抬头写「现状」，给的却是上一轮的值** | **major · 登记不修** | `:70` / `:71` / `:131`：main `f466f1c9…`、tag 对象 `bae14389…`、「2,187 件」，小节抬头是「## 三、两个远端 sha 与 tag **现状**」。实际 `5e4e179e…` / `2f49fa62…` / 2,189 件。比 N-?（HANDOFF §19.6.1）轻，因为这一处没有叫读者去 `ls-remote` 比对。**改法**：抬头「现状」改成「2026-09-13 R1–R3 轮终值」。另 `:20` 第 6 步那一格同病。 出处：卡 V。 |
| N-? | **`ops/HANDOFF.md` §19.5.1 说 README 里有「还没挂上去 / 地址现在会 404」，README 里已经没有了** | **minor · 登记不修** | `ops/HANDOFF.md:1922`：「README §2.1a … 同时如实写着「这两个附件今天还没挂上去，上面的地址现在会 404」（**远端实测确为 404**）」。实测：README 全树 0 命中那段话，两条地址匿名 GET **206** 不是 404。§19.6 的前言说了「§19.5.4 那六步已经做完」，所以 §19.5 可算上一轮的存档 —— 但这一句本身是现在时、且没有日期抬头。**改法**：句首加「2026-09-12 那一轮：」。 出处：卡 V。 |
| N-? | **已发布的 provider 包内 `MANIFEST.json` 带 `license.published: false`，而它已经发布了** | **minor · 知情保留，不要修** | 这个字段烤在 tar.gz 里，改它就要重打包，重打包就换 sha256，两件附件已公布的校验值当场作废（卡 C 撞过一次：`21ec3202…` → `33083ff2…`）。**修的代价远大于害处**，登记即可。同理 `published: false` 在包内 README 也可能有。 出处：卡 V。 |

## 三、一处规格冲突（本卡按保守方向处理，标 CONFLICT）

* **spec_a** —— 本卡任务书：「**唯一允许的写**是 `ops/reports/known_limits_v1.md` 与 `ops/tickets_inbox/V.md`（都只许追加）」。
* **spec_b** —— `ops/HANDOFF.md` §19.3.5（N-685）：「**改了任何手写发布件（README / 手册 / HANDOFF / known_limits / fairness_protocol / push_instructions）之后必须重跑 `$PY ops/mk_release_manifest.py`**」；
  且 `ops/test_release_manifest.py:62` 的 docstring 写着「逐件重算 sha256。**清单的全部价值就在这一条上**」，
  `:82` 对**手写件**的 sha 漂移直接判红。实测 `RELEASE_MANIFEST.files["ops/reports/known_limits_v1.md"]`
  记的 `22a77a68…` / `85344 B` 与盘上**此刻逐字节相同**。
* **处理** —— 往 `known_limits_v1.md` 里追加哪怕一个字节，都会把一条**当前是绿的**门打红，
  而唯一的收拾办法是重出 `RELEASE_MANIFEST.json` —— **那不在本卡允许写的路径里**。
  「恒红恒绿不绕过」+「不要改别的文件」两条合起来，保守方向只能是**不动 `known_limits_v1.md`**。
  于是上面第二节那九条**全部登记在本文件里**。`ops/tickets_inbox/` 不在 `RELEASE_MANIFEST.files` 里（实测为空集），写它没有这个副作用。
  **给编排方**：要把这九条并进 `known_limits_v1.md`，请派一张**同时**含
  `ops/reports/known_limits_v1.md` 与 `RELEASE_MANIFEST.json` 两条路径的卡，并记得它的逐类计数表
  （`test_e.py::test_已知限制的终态计数表自洽` 钉着「上一次盘点」与「终值」两列逐类相加各自等于合计）。

## 四、给后续卡的两句话

1. **上面三条 block 全是同一个根因**：卡 F 只拿到六个路径，而「指着 `publish_report.md` 旧内容说话」的文件
   （`HANDOFF.md` §19.6.4、`release_upload_report.md` §4.1）和「记着推送前 sha」的表
   （`HANDOFF.md` §19.6.1、`release_upload_report.md` §三）都不在那六个里。
   **下一张修这个的卡，路径至少要含 `ops/HANDOFF.md` + `ops/reports/release_upload_report.md`**，
   而且四处要一起改，否则还是顾此失彼。
2. **「报告记不下自己那棵树的 sha」这个递归，三轮踩了三次**（§5 的 `§6`/`§6.7`、§8.3 的 `§8.1`/`§8.2`、
   本卡的 §19.6.1 与 §三）。**根治办法不是每轮补一条口径更正，是从此不在树内文件里写终值 sha**，
   只写 `push_result.md` §5 那条自核不变量 —— 本卡实测它是对的且当前成立：
   `git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16`，三者都是 `5e4e179e…`。
