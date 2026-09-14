# 全树 Claude / Anthropic 字样扫描（卡 P / 用户裁定 ⑫）

**执行** 卡 P，2026-09-12 · 扫描器 `$GB/scratch/P/scan_mentions.py`（只读）
机读输出 `$GB/scratch/P/mentions_genebench.json`、`mentions_genequant.json`

## 口径（编排方已向用户明示，本卡照此执行）

裁定 ⑫ 的字面要求是「不得出现 Claude 或 Anthropic 字样」。**字面做不到**，
因为本 benchmark 本身就把 **Claude Code 当作五个 harness 之一**
（`harnesses/claude-code/`），`llm_trace` 要按 **Anthropic Messages** 的 wire 形状抽 usage，
白名单文档记着 `api.anthropic.com` 从两台机 403。删掉会让文档变成**假话**。

于是分两类：

| | 判据 | 处置 |
| --- | --- | --- |
| **署名形态** | `Co-Authored-By:` / `Generated with` / `🤖` / 代理签名 / `noreply@<anthropic 域>` / 任何声称「本文由某 AI 助手撰写」的行 | **一律删** |
| **技术事实** | harness 名、wire 形状、白名单域名、模型 id、供应商名出现在技术语境 | **保留**，逐条给出处与「删了会变成什么假话」 |

**提交信息里一个字都没有** —— 两棵树各一次提交，`%s` 与 `%b` 实测如下（`%b` 为空 = 没有 trailer）：

```
genebench  800004f  S:GeneBench v1.0.16 release   B:[]
genequant  1269121  S:GeneQuant v1.0 release      B:[]
作者与提交者均为 深情代码大师 <2994718175@qq.com>
```

---

## 一、已删（署名）

### 文件内容层面：**0 条**

两棵树 2,189 个文件逐行扫过，八条署名正则**一条都没命中**。
这不是巧合：两棵树都是新 `git init` 的单次提交，仓库内部历史里的
`Co-Authored-By:` trailer **不随 `git archive` 进入树**。

### git 元数据层面：**1 条，本卡已删**

| 位置 | 原值 | 现值 |
| --- | --- | --- |
| `release/trees/genequant` 的提交作者与提交者 | `GeneQuant release <noreply@<anthropic 域>>` | `深情代码大师 <2994718175@qq.com>` |
| 同一次提交的 message | `GeneQuant 协议 v1：首次对外树` | `GeneQuant v1.0 release` |

**这一条是扫描扫出来的，不是照着裁定挨个改出来的** —— 卡 Z 打这棵树时用的是
一个 anthropic 域的占位邮箱，落在 commit 的 author/committer 里。
文件内容扫描看不见它（扫描器跳过 `.git`），是单独核对提交元数据时抓到的。

修法：`$GB/scratch/P/mk_tree_genequant_p.sh` 重打（`rm -rf` + 重建 + `git init` + 单次提交），
**旧的 `915d664` 从未推送过**，所以没有对外痕迹。
GeneBench 树（卡 G2 打的 `c864020`）的身份本来就对，本卡重打后为 `800004f`
（重打的原因是要带上卡 H 的两次提交，不是身份问题）。

### 重扫会剩一条 —— 那是本报告自己

拿 `scan_mentions.py` 重扫公开树，署名那一栏会是 **1 条**，位置固定是本文件
上面那张口径表里「**署名形态**」那一行 —— 因为那一行要把判据**列出来**
（`Co-Authored-By:` … 某域占位邮箱 …），于是它被自己的正则命中。

**这是扫描器的自指，不是署名。** 判别方法：命中若只有这一条、且 `file` 是
`ops/reports/release_scan_claude_mentions.md`，就是它；多出任何一条都要查。
不把这条消掉，是因为消掉它就得把判据从报告里删掉 ——
那样下一个人就不知道「署名形态」到底按什么判的。

---

## 二、保留（技术事实）

`genebench` 树 **387 条 / 30 个文件**；`genequant` 树 **0 条**。
按类归并如下，每类给出处与「删了会变成什么假话」。

### 1. harness 目录与 ID：`claude-code`（161 条）+ `Claude Code`（22 条）

**出处**：`harnesses/claude-code/{README.md,Dockerfile,config.yaml,launch.json}`、
`ops/test_harness_claude_code.py`、`ops/reports/h_claude-code/**`（records.json 与 scores/）、
`runner/registry.py`、`ops/tickets_inbox/3.2-claude-code.md.merged`

**删了会变成什么假话**：Claude Code 是本 benchmark **五个 harness 之一**，
有自己的镜像、接入契约、真跑记录与逐题得分。删掉这个名字，
主表上那一臂就没有名字了 —— 读者会看到一列数字而不知道它测的是什么，
`ops/reports/h_claude-code/` 里 11 份 score.json 也就成了无主的孤儿。
**这是被测对象的名字，不是我们的署名。**

> 附带一条事实，别读错：`harnesses/claude-code/README.md:10` 明写
> 「**模型待换** —— 现在跑的模型是 `deepseek-chat`，不是 Claude」。
> 这一臂测的是**这个 CLI 工具**，接的上游是 DeepSeek 的 Anthropic 兼容端点。

### 2. 出向白名单与可达性实测：`api.anthropic.com`（35 条）

**出处**：`runner/c41/egress_proxy.py`（`MODEL_API_ALLOW` 及其注释）、
`harnesses/README.md:245`、`ops/recon/readiness_r1.md:156`、`ops/tickets.md`

**删了会变成什么假话**：白名单是**红线 5** 的一部分（出向只放模型 API 域名），
它的历史是「先前挂着 anthropic / openai 两条，后来实测从两台机都 403（地区封锁，N-32），
于是摘掉，现表只剩 `api.deepseek.com` 一条」。
删掉域名，这段注释就变成「摘掉了两条不知道是什么的东西」，
下一个人无从判断白名单为什么是现在这个样子，也无从复核「那两条到底可不可达」。

### 3. wire 形状：`Anthropic Messages`（7 条）

**出处**：`runner/c42/llm_trace.py:44,97`（`"anthropic_messages"` 是**代码里的常量值**）、
`ops/test_llm_usage_shapes.py:80,92`、`ops/reports/harness_llm_log.md:46-47`

**删了会变成什么假话**：`llm_trace` 归一 usage 时要先判 wire 形状，
`anthropic_messages` 是它的**枚举值之一**；`harness_llm_log.md` 记着
「Anthropic 那一行的『跨两个事件』是唯一一处不能照搬的 —— 旧实现对 SSE
从后往前找第一个带 usage 的事件，用在它上面会取到 `message_delta`」。
删掉名字，这条**踩过的坑**就没有主语；改名字则代码跑不起来（那是个字面常量）。

### 4. 供应商名出现在技术语境（86 条）与 `Claude` 出现在技术语境（76 条）

**出处（抽样）**：
`runner/pricing.yaml:90-91`（`- model: claude` / `provider: anthropic` —— **留位行，价全 null**）、
`ops/test_pricing.py:63-64`（钉着「有 row 没 price」与「这家没接 ≠ 这家不要钱」可分）、
`runner/registry.py:20`（*「为什么是 DeepSeek 而不是 Claude / GPT」* 的实测记录）、
`ops/test_env.py:766`（红线 3 扫描器的 **`sk-ant-` 形态正则**）、
`ops/GeneBench工程实施稿_v1.md:113`、`ops/test_memory_probe.py:196`、
`harnesses/gemini-cli/README.md:14,82`、`harnesses/opencode/README.md`

**删了会变成什么假话**：
`pricing.yaml` 的留位行删掉，`test_pricing.py` 当场红，而且「未接入」与「免费」
在主表上就分不开了；`ops/test_env.py:766` 的 `sk-ant-` 正则删掉，
**红线 3 的凭据扫描就少一种密钥形态认不出来**；
`registry.py:20` 与 `harnesses/gemini-cli/README.md` 记的是选型理由
（够得着的上游只有 DeepSeek，它只服务 OpenAI 兼容与 Anthropic 兼容两套协议），
删掉之后「为什么全都跑 deepseek-chat」这个问题就没有答案。

### 5. 模型 id（`claude-opus` / `claude-sonnet` / `claude-haiku`）

**出处**：`ops/test_harness_claude_code.py:10`
（*「模型名要写五处：只设 `ANTHROPIC_MODEL` 时后台小模型仍点名 haiku」*）等

**删了会变成什么假话**：那是一条**踩过的坑**的记录 —— 只设一个环境变量不够，
后台小模型会绕过它去点名另一个 id。删掉 id，这条坑就复现不出来。

---

## 三、边界判定两条：**本卡没有自行删除，交用户/编排方定**

这两条既不是干净的「技术事实」，也不是典型的「署名」。
契约 C 规定共享文件只许在 flock 内**追加或插入**，删除不在授权内；
且本卡路径不含这两个文件。**如实登记，不静默处理。**

| # | 位置 | 原文要点 | 为什么是边界 | 倾向 |
| --- | --- | --- | --- | --- |
| 1 | `ops/HANDOFF.md:1457` | 一条票据：*「提交署名不统一：任务书要求的 trailer 是 `Claude Fable 5.1`，而部分卡的运行时配置给的是 `Claude Opus 5`，两条 trailer 在仓库历史里并存」* | 它**不是**一条署名，是一条**关于内部署名不统一的票据**。但它确实向读者说明「本仓库内部历史带 AI 助手的 Co-Authored-By trailer」，而那些 trailer **不在公开树里**（新历史）—— 于是这条票据在公开树里指向一个不存在的东西 | **倾向删**（它对外既无用又暴露内部署名）。要删请在 flock 内定点改 `ops/HANDOFF.md` 并重跑 `$PY ops/mk_release_manifest.py` |
| 2 | `ops/specs/card_3.2_smoke40.md:127,132` | 两处写死本地 Mac 的 scratchpad 绝对路径 `/private/tmp/claude-501/…/scratchpad/…` | 不是 Claude/Anthropic 的**署名**，但路径里带 `claude-501`，且是**施工方本地机器的路径**，对外读者永远够不着 | **倾向改**为相对描述（陈路径，不是事实）。两处都在讲「本地已用真打包器全流程验过」，改写不影响那句话为真 |

---

## 复现

```sh
GB=/data/shared/genebench; PY=$GB/env/bin/python
cd $GB && PYTHONDONTWRITEBYTECODE=1 $PY scratch/P/scan_mentions.py release/trees/genebench
cd $GB && PYTHONDONTWRITEBYTECODE=1 $PY scratch/P/scan_mentions.py release/trees/genequant
cd $GB && PYTHONDONTWRITEBYTECODE=1 $PY scratch/P/sum_mentions.py       # 署名/技术两栏汇总
cd $GB && PYTHONDONTWRITEBYTECODE=1 $PY scratch/P/sample_mentions.py    # 泛化命中逐条抽样
# 提交元数据（扫描器跳过 .git，这一条要单独核）
for t in genebench genequant; do git -C $GB/release/trees/$t log --format='%an <%ae>|%cn <%ce>|%s|[%b]' -1; done
```

---

## 四、卡 D 重打公开树之前的复扫（2026-09-12）

口径不变（**署名形态一律删、技术事实保留**），本节只记「重打树之前又扫了一遍，结论没变」。

### 扫描器与被扫对象

```sh
cd $GB && PYTHONDONTWRITEBYTECODE=1 $PY scratch/P/scan_mentions.py repo   # 机读 $GB/scratch/D/mentions_repo.json
```

被扫的是**内网仓库工作树**（公开树是从它 `git archive` 出来的），
含卡 A/B/C/D 这一轮的全部新增与改动。

| | 值 |
| --- | --- |
| 文件 | 2,234（跳过二进制与 >8 MiB 后实扫 2,231） |
| **署名形态命中** | **1 条，且是自噬命中，见下** |
| 技术事实命中 | 439 条（harness 名 `claude-code`、`Anthropic Messages` wire 形状、白名单域名 `api.anthropic.com`、模型 id —— 逐类出处见 §二） |

### 唯一那条署名命中是**本文件自己**

```
ops/reports/release_scan_claude_mentions.md:17   （§一 那张「口径」表的「署名形态」一行）
```

命中的是**本文件第 17 行那张判据表**——它写的是「什么算署名形态」，不是一条署名
（那一格把四种署名写法逐个列了出来，于是被自己的判据扫到）。
这与 `runner/f02/answer_plane_guard.py::redact` 那个自噬循环是同一类问题
（一份文件因为**记录了判据**而被自己的判据判成违禁品）。**不删** ——
删了这份报告就说不清自己是按什么扫的。除它之外，全树署名形态 **0 条**。

### 卡 D 这一轮新增/改动的文件单独再核一遍

`README.md`、`ops/reports/release_scan_publish.md`、`ops/reports/push_result.md`、
`ops/tickets_inbox/D.md` 四件由 `ops/test_d.py::test_本卡写的文件里没有署名形态` 逐件盯着
（五条正则分别认：协作署名 trailer 的前缀、「由某助手生成」的行首、机器人表情、供应商域名下的占位邮箱、「由某助手撰写」的英文说法 —— 正则原文见 `ops/test_d.py` 顶部的 `_SIG`，这里**有意不原样抄**，抄一遍等于往公开树里又写一条署名形态），
**当前全绿**。这条测试留在仓库里，以后谁往这四件里写署名形态都会当场红。

### 提交元数据

公开树每重打一次就是一次新的 `git init` + 单次提交，作者与提交者均为
`深情代码大师 <2994718175@qq.com>`，`%s` = `GeneBench v1.0.16 release`，`%b` 为空。
本轮重打之后的实测值记在 [`push_result.md`](push_result.md) §6。

---

## 复扫（卡 R2，2026-09-13）：重打树之后再扫一遍

卡 R1 上传附件、卡 R2 落地三条清理与「不同源」说明之后，公开树按同一个脚本
（`$GB/scratch/G2/mk_tree_g2.sh`）重打了一次。**口径一字不变**（署名形态一律删、
技术事实保留），扫描器仍是 `$GB/scratch/P/scan_mentions.py`，只读。

命令与机读输出：

```sh
$PY $GB/scratch/P/scan_mentions.py $GB/release/trees/genebench > $GB/scratch/R2/mentions_genebench.json
```

### 结果

| | 卡 P（2026-09-12） | **卡 R2（2026-09-13）** |
| --- | ---: | ---: |
| 扫描文件数 | 2,189 | **2,187** |
| **署名形态命中** | 1 | **1** |
| 技术事实命中 | 442 | **444** |

> 卡 R2 这一列量的是**加入本节之前**那一次重打（同一批文件、同一个脚本）。
> 加入本节之后树又重打了一次，文件数不变、署名形态仍是 1 条（仍是本文件自指），
> 技术事实会再多几条 —— 终值记在内网仓库那一份 `push_result.md` §8.1。

**署名形态那 1 条就是上面「重扫会剩一条 —— 那是本报告自己」说的那一条**，
逐字相同：`ops/reports/release_scan_claude_mentions.md` 第 17 行那张口径表里
「署名形态」那一行 —— 它把判据**列出来**，于是被自己的正则命中。
判别方法照旧：命中若只有这一条、且 `file` 是本文件，就是自指；**多出任何一条都要查**。

技术事实 442 → 444（+2）：卡 R1/R2 新写的文字里没有引入任何新的供应商名，
增量全部落在**本文件自己新增的这一节**与 `ops/reports/push_result.md` 的新小节里
（引用本文件标题与判据时带上了那两个词）。

### git 元数据层面：**0 条**

```
author  深情代码大师 <2994718175@qq.com>
commit  深情代码大师 <2994718175@qq.com>
subject GeneBench v1.0.16 release
body    （空 —— 无署名 trailer、无「Generated with」行、无机器人表情前缀）
```

> **这里有意不写 commit sha** —— 本文件在树里，写进去 sha 就变（`push_result.md` §5 的递归）。
> 自核办法：在你 clone 下来的树里敲 `git log -1 --format='%an <%ae>|%cn <%ce>|%s|%b'`，
> 应当与上面四行逐字相同，且 sha 等于 `git ls-remote origin refs/heads/main`。
> 字面值记在内网仓库那一份 `push_result.md` §8.1 里。

`.git/` 整棵另外 `grep -ril` 过一遍两个关键词：**0 件命中**
（树是新 `git init` 的单次提交，内网仓库历史里的署名 trailer 不随 `git archive` 进树）。
