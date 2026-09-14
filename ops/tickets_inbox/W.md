# 卡 W（2026-09-13）—— 断掉「树内写死终值」这个复发根因 + 修掉卡 V 的七条

> 本卡的由来：**卡 V**（外部用户视角独立复核，只读、零模型 API）在已推的公开树里实测出
> **3 条 block + 4 条 major + 2 条 minor**，逐条写在 `ops/tickets_inbox/V.md`（给了 where / what /
> suggested_fix）。卡 V 自己一个字都没改 —— 它标了 CONFLICT：要并进 `known_limits_v1.md`
> 就得重出 `RELEASE_MANIFEST.json`，而清单不在它的路径里。**卡 V 的判断是对的。**
> 本卡两条路径都有，由本卡做完。
>
> **本卡零模型 API 调用；一个字节都没重打包、没重传或删除任何 asset、没新建 Release、没推 GeneQuant。**

## 本卡登记（编号续 N-742，已并进 `ops/tickets.md`「卡 W（2026-09-13）」一节）

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-743** | **口径：树内不记终值** | **已立** | 「报告记不下自己那棵树的 sha」这个递归**三轮踩了三次**（`push_result.md` §5 对 `§6`/`§6.7`、同一份文件 §8.3 对 `§8.1`/`§8.2`、本轮卡 V 实测到的 `HANDOFF.md` §19.6.1 与 `release_upload_report.md` §三）。口径写进 `ops/HANDOFF.md` **§19.6.6**：① 进树的文件里不写 `refs/heads/main` sha、tag 对象 sha、公开树件数**这三类**；② 只写**自核不变量**（`git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16`，三者同值即是）；③ **已写下的值一律不改值**，只加显式日期抬头；④ 推后终值**只记进内网仓库** `push_result.md` §8.x，树内只写「终值在内网仓库、自核用那三条命令」——**这句话不含 sha，永远不过期**。自查脚本 `$GB/scratch/W/w_scan_stale.py`。 出处：卡 V 第四节两句话，本卡立。 |
| **N-744** | 卡 V 的 3 block + 2 major + 1 minor：四处文档「指着旧状态说话 / 记着推送前 sha」 | **已闭合** | 六处一次改完，全按「不改值、只加显式日期抬头」。详见 `ops/tickets.md` 本节。 出处：卡 V。 |
| **N-745** | `RELEASE_MANIFEST.json` 两处对外正文在骗读许可条款的人 | **已闭合（改源不改生成物）** | `package.parts` 形态 A 三处 + `blockers[data_license_text].blocks` 三句。改 `ops/mk_release_manifest.py` 的源；**`satisfied` 判定逻辑一个字没动**；存档件 `package_inventory.json` 一个字节没改。 出处：卡 V。 |
| **N-746** | 卡 V 的九条并进 `ops/reports/known_limits_v1.md` | **已闭合** | 新增 W 一节，逐类计数 **67 → 76**（两列各自逐类相加 = 各自合计）。 出处：卡 V。 |
| **N-747** | 已发布的 provider 包内 `MANIFEST.json` 带 `license.published: false` | **登记不修（知情保留）** | 按卡 V 的判断照办：改它要重打包 → 换 `sha256` → 已写进三处并被 GitHub `digest` 背书的校验值当场作废。等 v1.0.17 本来就要重打包时（N-734）顺手改。 出处：卡 V 判，本卡照办。 |

## 本卡**没有**登记为新条目的（说明一下，免得下一张卡以为漏了）

* 卡 V 的第 4 条 major（公开树里 `push_result.md` §8.1 / §8.2 标题说「公开树里没有这一小节」）——
  **不需要写新文字**：内网仓库里卡 F 的 §8.3 早就有那句更正，只是 §8.3 推完才提交、不在已推的树里。
  **本轮重打树自然带上。** 它作为「已修」计进 `known_limits_v1.md` 的 W 一节，不另开票。
* 卡 V 复核通过的九件（两个远端 `ls-remote`、全新 clone、克隆树里 31 passed / 1 skipped、
  匿名 Release 对象与 `Range` GET 206、三处登记比对、不同源说明、csi1000 不入包、署名形态 0 条）——
  **与卡 F 所报逐字相符**，无需登记。

## 给下一张卡的三句话

1. **先跑 `$GB/scratch/W/w_scan_stale.py`**，在**打好的树上**跑，不是在仓库上跑。
   有真错就回去改完再打树，别推上去再修。
2. **判的时候按「这句话是不是在对外说假话」判，不要按子串计数判。**
   票据与已知限制表里**描述**那些子串是正常的；门断言的只是它不在 `publish_report.md` 里。
   任务书里「全树 grep 某子串 = 0」这种判据**偏严**（卡 V 提醒过）。
3. **有的 sha 是门的断言常量**：`ops/test_e.py::test_handoff_与报告记的远端sha是同一个`
   钉着 `bd0513a4…` 同时在 `HANDOFF.md` 与 `publish_report.md` 里；
   `ops/test_e.py::test_六条裁定逐条有判` 要求 `publish_report.md` ③ 那一格仍含「未达成」、
   BLOCKED 一节仍含 `403` 与 `contents=write`。**这些只能标日期留证，不能改值、不能迁就着改判据。**

## 第 5 步：推之前在树上扫「这一类」—— 逐条判据与结论

脚本 `$GB/scratch/W/w_scan_stale.py`，输出 `$GB/scratch/W/scan_repo_pre.txt`（改前）
与 `$GB/scratch/W/scan_tree.txt`（**打好的树上**，推之前）。

**扫描范围的一条判据**：第一版扫全树所有文本件，(a) 类 883 条 —— 其中 800 多条来自
`factor_library/compiled/*.jsonl` 里的表达式 `sha1`，**那是真数据不是终值留证**，
信噪比被压垮。改成**只扫散文件**（`.md` + `DATA_LICENSE` + `CITATION.cff`）之后 (a) 类 43 条，可以逐条判。
**这条本身值得记**：扫「文档在不在说假话」就该只扫文档。

### (a) 40 位 sha，附近 ±5 行没有时点字样 —— 43 条，判成 2 条真错

| 判 | 条数 | 逐条 |
|---|---|---|
| **真错，本轮已改** | **2** | `ops/reports/push_result.md` §8.1「读者的自核办法」与 §8.3「外部用户视角」两个**叫读者照着敲**的代码块，注释里给了当轮的期望值（`git log -1` → `f466f1c9…` / `5e4e179e…`、`git ls-files \| wc -l` → `2189`）。**这正是卡 V 踩到的形状**：照着敲，三处全对不上。按 §19.6.6 的口径**值不改**，块前各加一句写明是哪一轮的输出、当前只比三条命令彼此同值。 |
| 带日期的留证（**不改**） | 28 | 同一份 `push_result.md` 的 §6.1 / §6.7 / §8.1 / §8.2 / §8.3 里的 `ls-remote` 实测转录 —— 每个小节的标题就写着是哪一轮（「2026-09-12 那一轮的终值 —— 已被 §8 取代」「第二轮重打与推送（卡 R2）」「第三轮…（卡 F）」）。这份文件的本职就是**流水账**，一轮一小节，是 §19.6.6 第四条指定的终值落点。 |
| **不是终值**（不改） | 10 | `integrations/{tradingagents,finmem,alphaagent}/README.md` 与 `ops/tickets.md:2254` 里的**上游仓库 commit 钉**（`codeload.github.com/.../tar.gz/<sha>`）—— 那是**有意钉死**的第三方版本，钉不住才是问题；`harnesses/claude-code/README.md:7` 的 npm `shasum`；`ops/recon/readiness_r1.md` 两行是因子定义 JSON 里的 id。 |
| 别人那一轮的报告（**登记不改**） | 2 | `ops/reports/final_report.md:31`「两个公开远端 GeneBench `55ead485…` / GeneQuant `6eadb004…` —— **均为初始提交，本轮未推**」。**判成不是真错**：该文件标题就是「最终卡报告（**2026-09-12 收口**）」，同一张表里还写着「HEAD（本报告提交之前）`cd711c6`」「票据到 N-702」「本轮未推」，通篇自明是那一轮的快照，**也没有叫读者去 `ls-remote` 比对**（这正是 §19.6.1 那一条够得上 block 的原因）。且**不在本卡路径内**。登记，留给后续卡顺手加个日期抬头即可。 |
| 卡 V 自己的收件箱（不改） | 1 | `ops/tickets_inbox/V.md:11`，文件抬头写着日期。 |

### (b) 现在时的过时口径 —— 241 条，判成 0 条真错

* **门的断言常量**：`ops/test_e.py::test_handoff_与报告记的远端sha是同一个` 钉 `bd0513a4…`
  同时在 `HANDOFF.md` 与 `publish_report.md`；`test_六条裁定逐条有判` 要求 `publish_report.md`
  ③ 那一格仍含「未达成」、BLOCKED 一节仍含 `403` 与 `contents=write`。**只能标日期，不能改值。**
* **带日期的留证**：`known_limits_v1.md` 里 `## D（2026-09-12）` / `## P（2026-09-12）` /
  `## R2（2026-09-13）` 等小节的原文，以及本卡新写的 W 一节里**引用**卡 V 原文的地方。
  特别核过 `known_limits_v1.md:810`（「外部用户 clone 下来跑 `pytest ops/` 会看到这一条红」）——
  **紧接着的两行卡 F 已经就地写了「2026-09-13 卡 F 已闭…全绿」**，不是假话。
* **本轮顺手改掉的一处**（不算真错，但值得改）：`ops/HANDOFF.md` §12.6 那张
  「挡发布的事（2026-09-08 是四条）」清单，第 1 条写「外部用户拿不到形态 A」——
  **这句到今天已经说反了**。该节抬头本来就写着日期、也写着「条数以 `RELEASE_MANIFEST.json`
  的 `blockers` 为准」（读者照着查会得到 `未闭合 0`，能自我纠正），所以判成 minor；
  仍加了一条带日期的更正，因为它与卡 V 判成 major 的那两条 `RELEASE_MANIFEST` 正文**是同一句话**。
* **判据提醒**（卡 V 提过，实测确实如此）：任务书里「全树 grep 某子串 = 0」这种判据**偏严**。
  门只断言 `附件清单为空` 不在 `publish_report.md` 里；票据与已知限制表**描述**这条门是正常的。
  **按「这句话是不是在对外说假话」判，不要按子串计数判。**

### (c)「还欠什么 / 挡不挡」表里状态为「挡」的行 —— 29 条，判成 0 条真错

* `ops/HANDOFF.md` §19.6.4 两行**本轮已改成「已闭合」并划掉留证**；后三行
  （baostock 许可正文 / `CITATION.cff` / v1.0.17）**逐行核过，仍然成立**。
* `ops/reports/release_upload_report.md` §4.1 **本轮已标闭合**；§4.2 两条仍成立；§4.3 已标闭合。
* 其余全是**表头**（`| 待裁定 | 挡什么 | …`）、签字包里的**只读归档副本**（不碰）、
  以及 `ops/specs/{adaptation_track,fairness_protocol}.md` 里「它挡什么」这种**无关语义**。
