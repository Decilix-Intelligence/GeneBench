# 推送结果（卡 D / 裁定 ③⑤）

**日期** 2026-09-12 · **执行** 卡 D
**一句话**：⑤ **公开树按本轮改动重打并 force-push 了**；③ Release 当时**建不了 —— 凭据缺权限，不是我绕过去的**，
附件打定、验过、可上传。**2026-09-13 用户把 token 权限加上之后，卡 R1 把两个附件传上去并逐件核过，见 §7。**

| 步骤 | 裁定 | 状态 |
| --- | --- | --- |
| 上传前最后一次扫描（六项 + 容器口径） | ③ | **做完，六项全零** → [`release_scan_publish.md`](release_scan_publish.md) |
| 建 Release v1.0.16 并传两个附件 | ③ | **做完**（2026-09-13 卡 R1，权限到位后重跑同一条命令）→ §7 |
| README 快速开始给真实下载地址 + 校验命令 | ③ | **做完**（新 §2.1a；地址是终值，附件挂上去即生效） |
| `RELEASE_MANIFEST` 回填 `browser_download_url` | ③ | **做完**（卡 R1 回填并重出清单）→ §7；当时留空的道理见 §2.4 |
| 公开树重打、单次提交、身份与 message | ⑤ | **做完**，见 §3 |
| `git push --force` 到 GeneBench 远端 | ⑤ | **做完**，见 §3 与 §6 |
| GeneQuant | ⑤ | 本轮**无改动 → 只核不推**，见 §4 |
| 推后核对（`ls-remote` / 附件清单） | ⑤ | 见 §4 与 §6 |

上一版（卡 P，2026-09-12 上午）记的是「两棵树已备好但没推」；**那一版已经不是现状** ——
卡 P 之后的收尾卡把两棵树推上去了（GeneBench `45e33deb…` / GeneQuant `6ce7664e…`），
本卡在此基础上把 A/B/C 三张卡的改动同步上去。本文件整篇按现状重写。

---

## 1. 两个附件（**已打定、已验过，就等挂上去**）

| 附件 | 字节数 | sha256 |
| --- | --- | --- |
| `genebench_public_provider_v1.tar.gz` | 782,100,276（745.9 MiB） | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` |
| `genebench_public_gold_subset_v1.tar.gz` | 157,448,605（150.2 MiB） | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` |

落点 `$GB/release/public_v1/`（不是 `_staging_unpublished/` —— 许可已 `granted`）。
打包见 `ops/reports/public/release_forms.md` §7，上传前扫描见
[`release_scan_publish.md`](release_scan_publish.md)。**不要重打** ——
包内 `MANIFEST.json` 记 `code_head`，在本卡之后再提交一次再打包，这两个 sha256 就变，
README 与 Release 正文里写的校验和会当场失效。真要重打，顺序是
`flock heavy.lock` 打两个包 → `$PY ops/mk_release_manifest.py` → 再上传 → 再回填地址。

---

## 2. ③ 为什么没建成 Release：**token 缺 `contents: write`**

> **这一节是 2026-09-12 的诊断留证，已经闭合** —— 权限加上之后同一条命令回 201，做完的记录在 [§7](#7-上传结果卡-r12026-09-13两个附件已经挂上去了)。

### 2.1 实测证据（凭据全程只经 HTTPS 头，没有 echo、没有 cat、没有进任何脚本或日志）

```
POST https://api.github.com/repos/Decilix-Intelligence/GeneBench/releases
HTTP/2 403
{"message":"Resource not accessible by personal access token",
 "documentation_url":"https://docs.github.com/rest/releases/releases#create-a-release",
 "status":"403"}
x-accepted-github-permissions: contents=write; contents=write,workflows=write
```

同一把 token 的**读**是通的，所以不是「token 坏了」也不是「网络不通」：

| 探针 | 结果 |
| --- | --- |
| `GET /user` | `200`，`login = JensenLuan` |
| `GET /repos/Decilix-Intelligence/GeneBench` | `200`，`permissions: {admin: true, maintain: true, push: true}`（**账号是管理员**） |
| `GET /repos/.../releases` | `200`，`[]`（一个 Release 都还没有） |
| `GET /repos/.../tags` | `200`，`[]`（一个 tag 都还没有） |
| `POST /repos/.../releases` | **`403`**，见上 |

**账号有权限、token 没有。** 响应头里没有 `x-oauth-scopes` → 这是一把
**fine-grained PAT**；fine-grained PAT 的仓库权限与账号权限是两回事，
建 Release 要的是仓库权限 **Contents: Read and write**，这把只有读。
`~/.config/genebench/` 下只有 `github.env` 这一个文件，机器上没有 `gh` CLI、
没有 `~/.git-credentials`、没有 `credential.helper` —— **没有第二把可用的凭据**。

> **SSH 与 token 是两条独立的路。** `git push` 走 SSH key（已授权，§3 的 force-push 就是这么推上去的），
> 建 Release 与传附件**只能**走 HTTPS API。所以 ⑤ 做得成、③ 做不成，两件事不互相替代。

### 2.2 用户要做的一件事

给这把 token（或另发一把）加上 **`Contents: Read and write`**，射程含
`Decilix-Intelligence/GeneBench`，写回 `~/.config/genebench/github.env` 的 `GITHUB_TOKEN=`（保持 `0600`）。
`Metadata: Read` 是 fine-grained PAT 的强制依赖，一般已经有了。
**不需要**任何别的权限（不需要 `workflows`、不需要 org admin）。

### 2.3 权限到位之后照抄这一条（幂等，可重跑）

```sh
ssh finance01-ts 'bash /data/shared/genebench/scratch/D/d_release.sh; tail -40 /data/shared/genebench/scratch/D/release.log'
```

它做四件事：① 建 tag `v1.0.16` 的 Release（正文已备好在 `$GB/scratch/D/release_body.md`，
`target_commitish` 取 `$GB/scratch/D/target_commitish.txt`）；② 传两个附件；
③ 取回真实的 `browser_download_url` 与每件的大小，写 `$GB/scratch/D/release_result.json`；
④ **幂等**：Release 已存在就复用并只更新正文，同名附件字节数一致就跳过、不一致就先删再传。
脚本从进程环境读 `GITHUB_TOKEN`（由 `d_release.sh` 用 `set -a; . github.env` 注入），
**不打印、不写盘、不进 argv**，出错文本写出去之前统一过一遍脱敏。

跑完再补三件（都是一条命令）：

```sh
# ① 回填下载地址（attachments.json 里两条的 download_url，取 release_result.json 的 browser_download_url）
# ② 重出清单：release_attachments 在 FATAL_KEYS 里，回填之后不重出，test_release_manifest 会红
ssh finance01-ts 'cd /data/shared/genebench/repo && /data/shared/genebench/env/bin/python ops/mk_release_manifest.py && /data/shared/genebench/env/bin/python ops/mk_release_manifest.py --check; echo rc=$?'
# ③ 删掉 README §2.1a 里那段「这两个附件今天还没挂上去」的引用块，然后重打公开树再推一次（§3 的四条）
```

**`target_commitish` 与 tag 落在哪个提交上**：本卡把它填成**本次 force-push 之前**的远端 HEAD
（`45e33deb…`），因为建 Release 这一步本该在推之前做完。既然它没做成、而树已经推新了，
补做的时候**应当改成推后的 HEAD**（见 §6），否则 tag `v1.0.16` 会指向一个已经被 force 掉的提交。
改法：把 `$GB/scratch/D/target_commitish.txt` 换成 §6 记的那个 sha 再跑 §2.3。
附件的 `browser_download_url` 只由 tag 名决定（`…/releases/download/v1.0.16/<文件名>`），
**不随 tag 指向哪个提交而变** —— 所以 README §2.1a 里写死的那两条地址在任何一种选择下都成立。

### 2.4 为什么 `RELEASE_MANIFEST` 的 `download_url` **有意留空**

`ops/release/attachments.json` 自己写着「`download_url` 由上传那一步回填；**空串 = 还没上传**」，
`ops/mk_release_manifest.py::release_attachments_section` 据此把 `uploaded` 记成 0。
**现在确实还没上传，空串就是实话。** 填一个「它挂上去之后会长这样」的地址进清单，
等于让一份号称权威的判据文件替一件还没发生的事作证 —— 这正是卡 P §5 拒绝做的那件事，本卡照旧不做。

README §2.1a 写地址是另一回事：那一节**同时**写着「今天还没挂上去」，
读者拿到的是「地址 + 状态」两样，不会被误导。

---

## 3. ⑤ 公开树同步（**做完了**）

### 3.1 做法：**重打成一次提交**，不是在旧提交上追加

`bash $GB/scratch/G2/mk_tree_g2.sh` —— `rm -rf` 整棵、`git archive HEAD` 重铺、
剔四类（私有通道数据 / 凭据 / 记忆探针钥匙 / scratch 与 run 目录）、
`git init -b main` + **一次** `git commit`。所以树的历史**永远只有一个提交**，
不带内网仓库的任何内部历史。这与「`commit --amend`」不同，也与「在 `45e33deb` 上再加一条」不同——
选它的理由：① 既定做法（v1.0.15 起每一轮都这么重打），② 一次提交是裁定 ⑫ 的口径，
③ 重打是幂等的，任何人拿同一个仓库 HEAD 都能复现出同样的内容。

脚本 `git init` 之后 remote 是空的（它有意不加），所以重打之后要**重新 `git remote add origin`** 再推。

### 3.2 这一轮带进树里的东西

| 来源 | 内容 |
| --- | --- |
| 卡 A（`0b07713` / `66c4749`） | `DATA_LICENSE` §5 改写（成分表由 baostock 接口重建，在授权射程内）、`runner/inject.py` 的公开钉子换新根、`ops/data_cards/qlib_provider.md`、`ops/HANDOFF.md`、换面报告与归因 |
| 卡 B（`e73dc02`） | `ops/reports/s8_gold_reissue.md`（S8 四题两通道 gold 重出，8 次零 finding） |
| 卡 C（`4dfa5be` / `58d9da9`） | `ops/release/pack_gold_subset.py`、`ops/release/attachments.json`、`RELEASE_MANIFEST` 的 `release_attachments` 段、`ops/reports/public/release_forms.md` §7 |
| 卡 D（本卡） | `README.md` §2.1a（真实下载地址 + 校验命令）与 §5 末尾的 Release 状态段、`release_scan_publish.md`、本文件、`ops/tickets_inbox/D.md`、`ops/test_d.py` |

### 3.3 身份、message、扫描

* 作者与提交者均为 **深情代码大师 `<2994718175@qq.com>`**（`mk_tree_g2.sh` 里用
  `GIT_AUTHOR_*` / `GIT_COMMITTER_*` 显式给，**没有改任何全局 config**）。
* message = `GeneBench v1.0.16 release`，**body 为空**（无 AI 署名 trailer、无 `Generated with` 行、无机器人表情前缀）。
  —— 「AI 署名 trailer」指的就是裁定 ⑫ 点名要删的那一行；**这里刻意不把它的字面量写出来**，
  理由见本文件 §8.10「本轮的一条红是判据过宽」。
* 提交前后各扫一遍署名字样，结果记在
  [`release_scan_claude_mentions.md`](release_scan_claude_mentions.md)（口径不变：**署名形态一律删、技术事实保留**）。

### 3.4 推

```sh
git -C $GB/release/trees/genebench remote add origin git@github.com:Decilix-Intelligence/GeneBench.git
git -C $GB/release/trees/genebench push --force origin HEAD:main
```

`--force` 是用户已授权的（远端 `45e33deb…` 是我们自己上一轮推的同一棵树，
force 掉它没有第三方内容损失）。

---

## 4. GeneQuant：**本轮无改动，只核不推**（2026-09-12 那一轮；此后每一轮都是只核不推）

本卡没有碰 `$GB/repo/genequant/` 的任何文件，A/B/C 三张卡也没有（三份输出里都没有这个路径）。
所以 GeneQuant 远端应当还停在收尾卡推上去的 `6ce7664e…`，`ls-remote` 的核对结果见 §6。
`RELEASE_MANIFEST.json` 的 `genequant` 段钉的是 `genequant/MANIFEST.json` 的 sha256（不是 commit sha），
文件没动 → 这一段不需要改（口径出处见本文件的卡 P 版 §4 末尾，已并入 `ops/tickets_inbox/P.md`）。

---

## 5. 本文件为什么记不下自己所在这棵树的 sha

公开树的内容里**包含本文件**，而树的提交 sha 是对内容算的 —— 把 sha 写进来，sha 就变。
这个递归绕不过去。所以口径是：

* **树里的这一份**记到「推送怎么做」为止（§1–§4），并声明一句：
  **本文件所在这棵树的 `git log -1` 就是远端 `refs/heads/main`**，读者在自己 clone 下来的树里一敲就能核。
* **内网仓库 `$GB/repo` 的这一份**在推完之后补 §6（实测的 `ls-remote` 两行 + 附件清单），
  比树里的这一份多一节。两份的差别只有 §6，**这是有意的，不是漏同步**。

> **口径更正（2026-09-13，卡 R2 —— 上面那两段说的是 2026-09-12 那一轮）**
>
> 公开树是 `git archive HEAD` 打的：**上一轮写完 §6 之后它就进了内网仓库的 HEAD**，
> 所以卡 R2 这一轮重打的树里 **§6 与 §7 都在**，`§6`/`§6.7` 标题上那句
> 「只有内网仓库的这一份有这一节」对**这一轮的树**已经不成立 —— 那两句是
> 2026-09-12 那一刻的事实，原样保留作留证，**别照它去判树是不是漏同步了**。
>
> 递归本身没有消失，只是缩小到了**一个数**：本次推送产生的那个 commit sha
> 写不进被推送的内容里。所以口径改成 ——
> **推前能写的都写进树**（§1–§7 与 §8.0 的计划）；**只有推后实测的那几行**
> （§8.1 的 `ls-remote` 终值、附件清单、扫描终值）落在内网仓库这一份里，公开树没有。
> 读者的自核办法不变：`git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16`，
> 三者相同 = 你拿到的就是发布的那一棵。

---

## 6. 推后补记（**2026-09-12 那一轮**；标题里那句「只有内网仓库的这一份有这一节」说的也是那一轮，见 §5 的口径更正）

2026-09-12T17:1x Z 实测。公开树里的同名文件到 §5 为止 —— 那不是漏同步，是 §5 说的那个递归。

### 6.1 `git ls-remote` 两个远端

```
git ls-remote git@github.com:Decilix-Intelligence/GeneBench.git
    212f4d63ae1701a6656d8d7c3f0340d97c2daa85   HEAD
    212f4d63ae1701a6656d8d7c3f0340d97c2daa85   refs/heads/main
    5665f24710faabe534b6980871eb759879f4a83c   refs/tags/v1.0.16
    212f4d63ae1701a6656d8d7c3f0340d97c2daa85   refs/tags/v1.0.16^{}

git ls-remote git@github.com:Decilix-Intelligence/GeneQuant.git
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   HEAD
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   refs/heads/main
```

| | 推前 | 推后 | 与本地树 |
| --- | --- | --- | --- |
| GeneBench `refs/heads/main` | `45e33deb…` | **`212f4d63…`**（forced update） | **相同**（`git -C $GB/release/trees/genebench rev-parse HEAD`） |
| GeneQuant `refs/heads/main` | `6ce7664e…` | `6ce7664e…`（**没推，无改动**） | **相同** |

force 掉的 `45e33deb…` 是我们自己上一轮推的同一棵树，没有第三方内容损失。

### 6.2 推上去的那一棵：**单次提交、身份对、body 空**

```
212f4d63ae1701a6656d8d7c3f0340d97c2daa85
 author  : 深情代码大师 <2994718175@qq.com>
 commit  : 深情代码大师 <2994718175@qq.com>
 subject : GeneBench v1.0.16 release
 body    : []
 tracked files : 2,183     commits : 1     树 27 M（含 .git 40 M）
```

内容核对（从远端按 `ref=main` 取回 `README.md` 再核，不是核本地）：
新 §2.1a 的两行 sha256 与两条下载地址**都在远端那一份里**，
「这两个附件今天还没挂上去」那段状态提示也在（第 231 行）。

**全树署名形态复扫：3 条 → 1 条**（本卡上一次提交自己引入的两条已在 `422fe67` 定点改掉；
剩下那 1 条是 `release_scan_claude_mentions.md` 第 17 行那张判据表本身，按既定口径保留）。
技术事实命中 441 条，口径不变（harness 名、wire 形状、白名单域名、模型 id —— 删了文档变假话）。

### 6.3 tag：**本卡建了 `v1.0.16`，指向推后的 HEAD**

`§2.3` 原本把 `target_commitish` 留给补做那一步去定，**现在不用定了** ——
tag 已经建好并推上去（annotated，tagger 同为 `深情代码大师 <2994718175@qq.com>`，
message `GeneBench v1.0.16`，body 空），指向 `212f4d63…`。
补做 Release 时 `tag_name: v1.0.16` 会直接用这个已存在的 tag，`target_commitish` 被忽略，
所以**不需要**再改 `$GB/scratch/D/target_commitish.txt`（它也已经同步成 `212f4d63…` 了）。

### 6.4 Release 附件清单：**空的，如实记**

> **这是 2026-09-12 那一刻的快照，已经不是现状** —— 2026-09-13 两个附件传上去了，同样的三条命令现在回 1 个 Release / 2 个附件 / HTTP 200，见 §7。下面原样保留作留证。

```
GET /repos/Decilix-Intelligence/GeneBench/releases  →  []           （0 个 Release）
GET /repos/Decilix-Intelligence/GeneBench/tags      →  [v1.0.16 → 212f4d63…]
curl -L https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16/genebench_public_provider_v1.tar.gz
    → HTTP 404
```

**404 与 README §2.1a 写的是同一件事**，文档没有在对外说假话：
那一节明写「这两个附件今天还没挂上去，上面的地址现在会 404」。
附件名字、大小、sha256 三样的本地值在 §1，补传之后按 §2.3 逐件与 API 回的
`size` / `browser_download_url` 比一遍即可 —— 那一步留给带 `Contents: write` 的 token。

### 6.5 这一轮总共动了远端两次

| # | 动作 | 结果 |
| --- | --- | --- |
| 1 | `git push --force origin HEAD:main` | `+ 45e33de...212f4d6 HEAD -> main (forced update)`，rc=0 |
| 2 | `git push --force origin refs/tags/v1.0.16` | `* [new tag] v1.0.16 -> v1.0.16`，rc=0 |

**没有**第三次。Release 与附件一次都没动过（动不了，见 §2）。

### 6.6 第二次推送：把 `ops/test_p.py` 的断言修正也带上去

§6.5 写「这一轮总共动了远端两次」的时候，`ops/test_p.py` 还有三条钉死在卡 P 那个时点的断言
（「树里没有配远端」「推送未执行」「附件的两个拦路原因」）—— 前提已经被卡 A/C/D 改没了，
外部用户 clone 下来跑测试会看到四条红。**手上有修就不该把已知的红发出去**，
所以把 `7f8b77e`（三条改成不变量，每条留反向判别）也带进树里，**重打重推一次**。

于是远端一共被动过四次：

| # | 动作 | 结果 |
| --- | --- | --- |
| 1 | `push --force origin HEAD:main` | `+ 45e33de...212f4d6 (forced update)` |
| 2 | `push --force origin refs/tags/v1.0.16` | `* [new tag] v1.0.16` |
| 3 | `push --force origin HEAD:main`（重打后） | 见 §6.7 |
| 4 | `push --force origin refs/tags/v1.0.16`（tag 跟到新 HEAD） | 见 §6.7 |

**读者在自己 clone 下来的树里就能核**：`git log -1` 的 sha 应当等于
`git ls-remote origin refs/heads/main`，也等于 `git rev-list -n1 v1.0.16`。
三者相同 = 你拿到的就是发布的那一棵。内网仓库 `$GB/repo` 的这一份另有 §6.7 记着字面值
（公开树里没有 §6.7，理由见 §5：把 sha 写进内容里，内容的 sha 就变）。

### 6.7 终值（**2026-09-12 那一轮的终值** —— 已被 §8 取代）

> **读之前先看这一句（2026-09-13 补）**：下面这张表里的「终值」是 **2026-09-12 那一轮**的终值。
> 2026-09-13 卡 R1 上传附件、卡 R2 落地三条清理之后，公开树又重打重推了 ——
> **现在的终值在 §8.2**，`bd0513a4…` 已经不是 `refs/heads/main`。本节原样保留作留证。
> 标题原本还写着「公开树里没有这一小节」，那也是当时的事实（见 §5 末尾的口径更正）。

2026-09-12T17:2x Z，第 3、4 次推送之后实测：

```
git ls-remote git@github.com:Decilix-Intelligence/GeneBench.git
    bd0513a47d1ad273d4cc21fdbdfb5604b2487645   HEAD
    bd0513a47d1ad273d4cc21fdbdfb5604b2487645   refs/heads/main
    c9596315993b18114d52498b6d562f374be34591   refs/tags/v1.0.16
    bd0513a47d1ad273d4cc21fdbdfb5604b2487645   refs/tags/v1.0.16^{}

git ls-remote git@github.com:Decilix-Intelligence/GeneQuant.git
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   HEAD
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   refs/heads/main
```

| | 值 |
| --- | --- |
| GeneBench `refs/heads/main`（终） | **`bd0513a47d1ad273d4cc21fdbdfb5604b2487645`** |
| 本地树 `git rev-parse HEAD` | 相同 |
| tag `v1.0.16` 解引用后 | 相同（annotated 对象 `c9596315…`，tagger `深情代码大师 <2994718175@qq.com>`，body 空） |
| 文件 / 提交数 | 2,183 件 / **1 次提交** |
| 作者 = 提交者 | `深情代码大师 <2994718175@qq.com>` |
| message / body | `GeneBench v1.0.16 release` / **空** |
| 全树署名形态 | **1 条**（`release_scan_claude_mentions.md:17` 那张判据表自身，按既定口径保留）；技术事实 442 条 |
| 树里跑 `ops/test_p.py` | **28 passed**（外部用户口径：只用树里的东西） |
| GeneQuant | `6ce7664e…`，**没推**，与本地树相同 |
| Release 附件 | 当时 **0 个 Release** —— 见 §2；**2026-09-13 已补做**（1 个 Release / 2 个附件 / 逐件核过），见 §7 |

推送历史（`45e33deb` 是收尾卡那一轮的，不是本卡的起点之外的任何东西）：
`45e33deb` → `212f4d63`（第 1 次）→ `bd0513a4`（第 3 次，终）。
中间那一次已被 force 掉，**没有对外宣传过**，两次之间相隔约 15 分钟。

---

## 7. 上传结果（卡 R1，2026-09-13）：**两个附件已经挂上去了**

§2 记的「token 缺 `contents: write`」在用户把 token 加上 `Contents: Read and write` 之后闭合。
本节是**做完之后的实测记录**：建 Release → 两次上传 → 从真实下载地址取回重算 sha256 → 回填清单。

### 7.1 Release 本体

| | 值 |
| --- | --- |
| `html_url` | <https://github.com/Decilix-Intelligence/GeneBench/releases/tag/v1.0.16> |
| `tag_name` | `v1.0.16`（**复用远端已有的那一个**，没有建第二个 tag） |
| `target_commitish` | `bd0513a47d1ad273d4cc21fdbdfb5604b2487645` |
| release id | `387775425` |
| draft / prerelease | `False` / `False` |
| `published_at` | `2026-09-13T02:58:37Z` |

`POST /releases` 回 **201**（第一次试是 **403 `Resource not accessible by personal access token`**，
见 §2.1 —— 权限加上之后同一条命令直接过，脚本没有改过判据）。

### 7.2 两个附件：上传 → 取回 → 逐件比对

| 附件 | 字节数（本地 = Release = 下载回来） | 本地 sha256 | 下载回来重算的 sha256 | 判定 |
| --- | --- | --- | --- | --- |
| `genebench_public_provider_v1.tar.gz` | 782,100,276 | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` | **一致** |
| `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` | **一致** |

上传本身：`POST /releases/{id}/assets` 两次都回 **201**、`state=uploaded`。
**第一次试传 782 MB 那件在传输中 `BrokenPipeError`（rc=1，release 已建好、附件卡在 `state=starter`）**；
重试版脚本 `scratch/R1/r1_release.py` 每件最多试 4 次、每次先拉 assets 列表把半截的那件 `DELETE` 掉再传，
第 2 次一次过（782,100,276 B / 82 s / 9.5 MB/s；157,448,605 B / 23 s / 6.9 MB/s）。

GitHub 自己在 asset 上回了 `digest` 字段，两件都是：

* `genebench_public_provider_v1.tar.gz` → `sha256:33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9`（与本地 sha256 相同）
* `genebench_public_gold_subset_v1.tar.gz` → `sha256:edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06`（与本地 sha256 相同）

**但 `digest` 是上游自报，不算数** —— 所以另走了一遍真下载：从 API 回来的 `browser_download_url`
（不是手拼的地址）把两件都下回本地重算 sha256，就是上表第 4 列。**匿名可下，不需要 token**
（`curl` 对 `.../releases/download/v1.0.16/...` 回 206/200）。

### 7.3 外部用户路径：README §2.1a 那段命令原样跑一遍

把 §2.1a 的代码块从 README 里**抠出来**（不是照着重打一遍）在空目录里执行：

```
curl -L -O $B/genebench_public_provider_v1.tar.gz
curl -L -O $B/genebench_public_gold_subset_v1.tar.gz
sha256sum -c SHA256SUMS.release        # 2/2 OK
tar xzf … && sha256sum -c SHA256SUMS / gold_subset_SHA256SUMS   # 包内逐件
```

包体两行 **2/2 OK**；包内逐件校验也全 OK（逐行输出在 `scratch/R1/userwalk.log`）。

### 7.4 回填与清单

* `ops/release/attachments.json` 两条的 `download_url` 回填成 API 回来的 `browser_download_url`
  （脚本 `scratch/R1/r1_backfill.py`，只从 `release_result.json` 读，不手拼、不覆盖已有值）。
* `$PY ops/mk_release_manifest.py` 重出，`--check` 退 **0**；
  `release_attachments.uploaded` 由 **0 → 2**，`releasable` 仍 **true**，未闭合 blocker 仍 **0** 条。
* README 两处状态提示改口：§2.1a 那段「还没挂上去、地址会 404」的引用块、
  §5 里同义的那一段。`ops/test_d.py` 的双向门（地址已回填 ↔ README 还写着没挂上去）改完仍绿。
* 定向测试 `ops/test_d.py ops/test_release_manifest.py ops/test_pack_release.py`：**58 passed, 1 skipped**。

### 7.5 本节**没有**做的事

* **没有重打公开树、没有 push** —— 留给同批的下一张卡一次做完，避免推两次（`§6.5` 的教训）。
* **没有建第二个 tag**，`v1.0.16` 用的是远端已有的那一个（解引用 `bd0513a4…`）。
* **没有重打两个包** —— 顺序是「先上传、后写地址，中间不重打」，重打会换 sha 把校验值作废。

---

## 8. 第二轮重打与推送（卡 R2，2026-09-13）

### 8.0 为什么又推一次，推的是什么

卡 R1 把两个附件挂上去之后改了 4 个进公开树的文件（`README.md`、`RELEASE_MANIFEST.json`、
`ops/release/attachments.json`、本文件），**而那时的公开树还是 2026-09-12 打的那一棵** ——
外部用户 clone 下来读到的 README 仍写着「这两个附件今天还没挂上去，上面的地址现在会 404」。
**手上有修就不该把已知的假话发出去**，所以重打重推。

卡 R2 这一轮另外带进树里的（用户 2026-09-13 裁定）：

| 裁定 | 落在树里的东西 |
| --- | --- |
| 清理 ① 删 staging 旧包（N-714） | `ops/reports/known_limits_v1.md` 那条改成**已闭**，留原文存档 |
| 清理 ② 卡 B 跑前备份移出 `$GB`（N-726） | 同上；`ops/test_env.py::test_gold_only_lives_under_reference_or_snapshots` **转绿** |
| 清理 ③ `csi1000` 保留在 f01、不入包 | `README.md` §2.1a、`ops/data_cards/gold_subset_v1.md` 新一节、`known_limits_v1.md` |
| **阈值与 gold 名单不同源**（点名要写两处） | **`README.md` §2.1a** 与 **`DATA_LICENSE` §6**（新增整节），`known_limits_v1.md` 与数据卡同步指向这两处 |

做法与上一轮同源：`bash $GB/scratch/G2/mk_tree_g2.sh` —— `rm -rf` 整棵、`git archive HEAD` 重铺、
剔四类、`git init -b main` + **一次** `git commit`。树的历史**永远只有一个提交**。
身份、message、body 的口径一字不变（`深情代码大师 <2994718175@qq.com>`，
`GeneBench v1.0.16 release`，body 空，无 AI 署名 trailer）。

### 8.0a tag `v1.0.16` 怎么办：**跟着移到新 commit**

远端 tag `v1.0.16`（annotated 对象 `c9596315…`）当时指向 `bd0513a4…`。
本轮内容变了，三条路各自的后果：

| 选项 | 后果 | 取舍 |
| --- | --- | --- |
| **留在旧 commit** | §6.6 写在文档里的自核不变量当场断：`git rev-list -n1 v1.0.16` ≠ `ls-remote refs/heads/main`。外部用户 `git checkout v1.0.16` 拿到的是**还写着「附件没挂上去、地址会 404」的那一棵** —— 而附件早就挂上去了 | **否** |
| 新建 `v1.0.16.1` | 多一个版本号，而**三条版本轴（任务集 v1.0.16 / 参考轴 r1.0.23 / 公开轴 p1.0.0）一条都没动** —— 题面、参考实现、公开通道口径本轮零改动，改的全是文档与登记。凭文档改动造一个新的发布版本号，会让「版本号 = 口径」这条约定失效 | **否** |
| **移到新 commit** | Release 的 `tag_name` 仍是 `v1.0.16`，两个附件挂在 release id 上、**不受 tag 移动影响**（附件地址 `/releases/download/v1.0.16/<name>` 走的是 tag 名不是 commit）。自核不变量继续成立 | **是** |

**选移。** 理由一句话：**v1.0.16 这个号指的是「这一版发布」，本轮改的是同一版发布的文档与登记，
不是新的一版口径。** 让号指向那一版**最准确**的一棵树，比让它指向一棵已知在说假话的树好。
移法：本地用同一个 tagger 身份重建 annotated tag（message `GeneBench v1.0.16`、body 空）
→ `push --force origin refs/tags/v1.0.16`。推完**必须回头核 Release**：
`GET /releases/tags/v1.0.16` 要仍然回同一个 release id（`387775425`）、附件仍然 2 件、
`browser_download_url` 仍然 200 —— 不核这一步就有把 Release 指到不存在的 commit 上的风险。

### 8.0b GeneQuant：**只核不推**

本卡一个字节都没碰 `$GB/repo/genequant/`，也没重打 `$GB/release/trees/genequant/`。
`ls-remote` 的核对结果在 §8.1。

### 8.1 推后实测终值（**公开树里没有这一小节**，理由见 §5 的口径更正）

2026-09-13T05:2x–05:3x Z 实测。

#### 终值不写在本小节里（§5 的递归）

本轮**重打并 force 推了两次**（第一次推完之后又修掉一条本卡自己引入的红、把全量红名单
归因入表，于是重打重推）。而这份文件**在树里** —— 把「推后的 HEAD sha」写进它，
它自己的内容就变了，sha 当场作废。所以：

* **本小节（进公开树）只记不随重打而变的事实**：Release id、两件附件的字节数与 digest、
  匿名可下、全树署名形态扫描的结论。
* **`ls-remote` 的终值、annotated tag 的对象 sha、推送次数** 记在 **§8.2** ——
  那一节是**推完之后**才提交进内网仓库的，**公开树里没有它**。
* **读者的自核办法不变**（不需要任何人告诉你 sha 是多少）：

```sh
git clone git@github.com:Decilix-Intelligence/GeneBench.git && cd GeneBench
git log -1 --format='%H %an <%ae> %s'      # 作者=提交者=深情代码大师，subject=GeneBench v1.0.16 release，body 空
git ls-remote origin refs/heads/main
git rev-list -n1 v1.0.16
```

三者相同 = 你拿到的就是发布的那一棵。这棵树**永远只有一个提交**、**2,187 个文件**。

#### GeneQuant：推前 = 推后，**没推**

`git ls-remote git@github.com:Decilix-Intelligence/GeneQuant.git` 两次（推前、推后）
都回 `6ce7664e84e467c39d11bb4ec88209bdae6a7c92`（`HEAD` 与 `refs/heads/main` 同值），
与 `$GB/release/trees/genequant` 的 `rev-parse HEAD` **相同**。本卡一个字节都没碰
`$GB/repo/genequant/`，也没重打那棵树。

#### 远端内容核对：**不是核本地，是从远端按 `ref=main` 取回再核**

（`$GB/scratch/R2/remote_content.json`）7 个文件逐件取回、逐件 sha256 与本地树**全等**，
本轮该在里面的话**全在**：

| 远端那一份 | 核到的 |
| --- | --- |
| `README.md` | 「贴着阈值的边界样本可能判反」「保留着但不随包发」「两个附件已经挂上去了」「指向 `DATA_LICENSE` §6」四句全在；**「还没挂上去」与「404」两个旧说法都已不在** |
| `DATA_LICENSE` | 新 §6 整节在、一页速览那一行在、「重算排 v1.0.17」在 |
| `ops/data_cards/gold_subset_v1.md` | csi1000「保留在发布方机器上，不随包发」在 |
| `ops/reports/known_limits_v1.md` | N-714 / N-726 两条的「已闭」标记都在 |
| `ops/reports/push_result.md` | §8 与 §8.0a 在（§8.2 **不在**，那是有意的） |
| `ops/tickets_inbox/R2.md` / `release_scan_claude_mentions.md` | 都在 |

#### Release 与 tag 的关联：**核过了，没指向不存在的 commit**

tag 从 `bd0513a4…`（上一轮那个 commit）移到**本轮的新 commit**之后，Release 本体（id **`387775425`**）**没有被重建**，
两件附件**一件没动**。逐项实测（`$GB/scratch/R2/verify.json`、`patch_release.log`）：

| 核的东西 | 结果 |
| --- | --- |
| `GET /releases/tags/v1.0.16` | **200**，id `387775425`，`draft=false`、`prerelease=false`，`html_url` 不变 |
| `GET /git/ref/tags/v1.0.16` → `GET /git/tags/<sha>` | annotated tag 对象 → **指向 `refs/heads/main` 的同一个 commit**（字面值见 §8.2） |
| Release 存的 `target_commitish` | 原为**上一轮那个 commit**（force-push + tag 移动之后**没有任何 ref 指着它**）。每次重推都 `PATCH` 成当轮的新 commit，回 **200**。GitHub 文档口径：tag 已存在时这个字段**不生效**（不会重新打 tag），所以这一步只改记录、不动 tag，改完立刻回核 tag 与附件**都没变** |
| 两件附件 | `state=uploaded`，字节数与 `digest` 逐件与本地/登记表**三处相同**（见下表） |

| 附件 | 远端 size | 远端 digest | 本地 sha256 | 一致？ |
| --- | ---: | --- | --- | --- |
| `genebench_public_provider_v1.tar.gz` | 782,100,276 | `sha256:33083ff242c64a8f…` | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` | **字节数 ✓ / digest ✓ / 登记表 URL ✓** |
| `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `sha256:edc5ea7cf70ffec3…` | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` | **字节数 ✓ / digest ✓ / 登记表 URL ✓** |

**匿名可下**（外部用户口径，不带 token）：两条 `browser_download_url` 各发一次带
`Range: bytes=0-0` 的 GET，都回 **206**，`Content-Range` 里的总长度分别是
`…/782100276` 与 `…/157448605` —— 与上表逐字相同。
**这一轮没有把 782 MB 整个再下一遍**：卡 R1 已经整件下回来重算过 sha256 并逐字比对
（§7.2），而本轮**一个字节都没重打包**，包体不可能变；远端 `digest` 字段又是 GitHub
自己算的 sha256，与本地逐字相同，等价于又核了一遍。f01→GitHub 下行只有 ~300 KB/s，
整件重下要 75 分钟，不值当。

#### 全树署名形态：**1 条**，仍是那一条自指

重打后的树 2,187 个文件：**署名形态命中 1 条**，位置固定是
`ops/reports/release_scan_claude_mentions.md` 第 17 行那张口径表里列判据的那一行
（扫描器被自己的正则命中，判别法写在该文件「重扫会剩一条」一节）。
技术事实 **447 条**（本卡新增的几节自己引用了判据里那两个词），口径不变（harness 名、wire 形状、白名单域名、模型 id —— 删了文档变假话）。
git 元数据层面 **0 条**：作者 = 提交者 = `深情代码大师 <2994718175@qq.com>`，body 空，
`.git/` 整棵 `grep -ril` 两个关键词 **0 件命中**。
机读输出 `$GB/scratch/R2/mentions_genebench{,2,3}.json`（三次重打各扫一次，署名形态恒为 1 条）。


### 8.2 本轮终值（**公开树里没有这一小节** —— 它是推完之后才提交的）

2026-09-13T06:1x–06:3x Z 实测。

#### `git ls-remote` 两个远端

```
git ls-remote git@github.com:Decilix-Intelligence/GeneBench.git      （本轮推前）
    bd0513a47d1ad273d4cc21fdbdfb5604b2487645   HEAD
    bd0513a47d1ad273d4cc21fdbdfb5604b2487645   refs/heads/main
    c9596315993b18114d52498b6d562f374be34591   refs/tags/v1.0.16
    bd0513a47d1ad273d4cc21fdbdfb5604b2487645   refs/tags/v1.0.16^{}

git ls-remote git@github.com:Decilix-Intelligence/GeneBench.git      （本轮终值）
    f466f1c91481acfc0c5cf87235d5e82b601d8190   HEAD
    f466f1c91481acfc0c5cf87235d5e82b601d8190   refs/heads/main
    bae1438986fc2313d45cec4ffad1c05227a2de3c   refs/tags/v1.0.16
    f466f1c91481acfc0c5cf87235d5e82b601d8190   refs/tags/v1.0.16^{}

git ls-remote git@github.com:Decilix-Intelligence/GeneQuant.git      （推前 = 终值，没推）
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   HEAD
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   refs/heads/main
```

| | 本轮推前 | **本轮终值** | 与本地树 |
| --- | --- | --- | --- |
| GeneBench `refs/heads/main` | `bd0513a4…` | **`f466f1c91481acfc0c5cf87235d5e82b601d8190`** | **相同** |
| GeneBench `v1.0.16` 解引用 | `bd0513a4…` | **`f466f1c9…`** | **相同** |
| GeneBench `v1.0.16` annotated 对象 | `c9596315…` | **`bae1438986fc2313d45cec4ffad1c05227a2de3c`** | tagger `深情代码大师 <2994718175@qq.com>`，message `GeneBench v1.0.16`，body 空 |
| Release id / `target_commitish` | `387775425` / `bd0513a4…` | `387775425`（**没重建**）/ **`f466f1c9…`** | — |
| GeneQuant `refs/heads/main` | `6ce7664e…` | `6ce7664e…`（**没推**） | **相同** |

#### 本轮一共动了远端**九次**（三轮，每轮三次）

| 轮 | 为什么又推一次 | HEAD | tag 对象 |
| --- | --- | --- | --- |
| 1 | 卡 R1 的四个文件 + 卡 R2 的三条清理与「不同源」两处说明 | `60505d91…` | `8d13b38…` |
| 2 | 全量 pytest 查出本卡自己引入的一条红（README 里 csi1000 的路径写成了仓库路径），修掉 + 把九条红的归因入表 | `9a8f29ea…` | `09f6d3c…` |
| 3 | §8.1 里写死的 HEAD sha 被第 2 轮作废 —— 把会随重打失效的 sha 全抽到本节，§6.7 标注已被取代 | **`f466f1c9…`** | **`bae1438…`** |

每一轮三次 = `push --force HEAD:main` + `push --force refs/tags/v1.0.16` +
`PATCH /releases/387775425`（只改 `target_commitish` 一格）。
**前两轮的 HEAD 都被 force 掉了，一次都没有对外宣传过**（三轮相隔共约 70 分钟）。

**当轮为什么要 `PATCH`**（**这条纪律 2026-09-13 已整条作废，见本段末尾**）：
`target_commitish` 是 Release 创建时存下的字段，tag 已存在时它**不生效**
（GitHub 文档口径，不会重新打 tag），但 force-push + tag 移动之后
它会指向一个**没有任何 ref 的 commit**。每次 `PATCH` 回 200，改完立刻回核
「tag 仍指新 commit / release id 不变 / 两件附件仍 `uploaded` 且 digest 不变」，三样都没变。

<!-- P2-2026-09-13 -->
> **2026-09-13 用户裁定 ①（N-748）：`target_commitish` 一律写分支名 `main`。**
> 于是它永不悬空，**「每次 force-push 之后记得 `PATCH` 一次」这条手工纪律整条删除**（N-736 作废）。
> 依据：`PATCH {"target_commitish": "main"}` 实测回 **200**，且 tag 已存在时该字段不生效 ——
> 对 tag / 附件 / 下载地址**一概无影响**。上面这段是当轮做法的留证，**不是今天的做法**。

#### 附件：一个字节都没重打过

| 附件 | 远端 size | 远端 digest（GitHub 自己算的 sha256） | 本地 sha256 | 登记表 URL |
| --- | ---: | --- | --- | --- |
| `genebench_public_provider_v1.tar.gz` | 782,100,276 | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` | **逐字相同** | **相同** |
| `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` | **逐字相同** | **相同** |

匿名（不带 token）带 `Range: bytes=0-0` 的 GET 两条都回 **206**，
`Content-Range` 的总长度 `…/782100276` 与 `…/157448605`。
**没有把 782 MB 整个再下一遍**：卡 R1 §7.2 已整件下回来重算过 sha256 并逐字比对，
而本轮**一个字节都没重打包**；远端 `digest` 与本地逐字相同，等价于又核了一遍。
（f01→GitHub 下行 ~300 KB/s，整件重下 75 分钟。）

#### 读者的自核办法

> **注释里那个 sha 是卡 R2 那一轮（2026-09-13）的实测输出，留证用，**不是**你现在会看到的值** ——
> 卡 F 与卡 W 之后又各重打并推过一轮。按口径 `ops/HANDOFF.md` §19.6.6「树内不记终值」，
> **自核不要跟任何写死的值比**，只比这三条命令**彼此之间**是否同值：
> `git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16`。
> **三者同值 = 你拿到的就是发布的那一棵**，与它具体等于多少无关。

```sh
git clone git@github.com:Decilix-Intelligence/GeneBench.git && cd GeneBench
git log -1 --format='%H'        # f466f1c91481acfc0c5cf87235d5e82b601d8190
git rev-list -n1 v1.0.16        # 同上
```

机读证据：`$GB/scratch/R2/{push,push2,push3}.log`、`verify3.json`、
`patch_release3.log`、`remote_content.json`、`mentions_genebench4.json`。

---

### 8.3 第三轮重打与推送（卡 F，2026-09-13）：本轮终值

> **这一小节与 §8.1 / §8.2 一样，是推完之后才提交进内网仓库的，所以它不在本轮推上去的那棵树里。**
>
> **口径更正（接 §5 的那一条）**：`§8.1` / `§8.2` 标题上那句「公开树里没有这一小节」
> 说的都是**它们各自那一轮**的树。公开树是 `git archive HEAD` 打的，上一轮写完就进了内网 HEAD，
> 所以**本轮（卡 F）重打的树里 §8.1 与 §8.2 都在** —— 那两句对这一轮的树已不成立，
> 原样保留作留证，**别照它去判树是不是漏同步了**。每一轮真正不在树里的，
> 只有**那一轮自己**的推后实测小节。这一条与 §5 对 `§6`/`§6.7` 的更正是同一回事。

#### 为什么又推一次

上一轮（卡 R3）之后留下**一条真红 + 一处对外说假话**：`ops/reports/publish_report.md` 里还写着
「一个 Release 都没有，附件清单为空」，而两个附件 2026-09-13 已经挂上、
`RELEASE_MANIFEST.release_attachments` 两条 `download_url` 都已回填 ——
`ops/test_e.py::test_附件还没上传时_报告必须把它记成blocked` 那条**双向门**的 `else` 分支当场红。
R1 / R2 / R3 三张卡都不含该路径，按并发施工规则没碰（N-739）。本轮补上，顺手把 N-731
（`s8_gold_reissue.md` 三处证据路径指向旧备份地址）一并闭合。

**本轮一个字节都没重打包、没重传任何 asset**，只重打树 + force-push + `PATCH` Release 的
`target_commitish`。内网提交 `6590790`（六个文件：`publish_report.md`、`s8_gold_reissue.md`、
`known_limits_v1.md`、`tickets.md`、`tickets_inbox/F.md`、`RELEASE_MANIFEST.json`）。

#### `git ls-remote` 两个远端（推后实测）

```
git ls-remote git@github.com:Decilix-Intelligence/GeneBench.git
    5e4e179e1603236117f8b27f3530a5dc4cec6612   HEAD
    5e4e179e1603236117f8b27f3530a5dc4cec6612   refs/heads/main
    2f49fa626faaf54157789dd6da68e455b32e6dd1   refs/tags/v1.0.16        ← annotated tag 对象
    5e4e179e1603236117f8b27f3530a5dc4cec6612   refs/tags/v1.0.16^{}     ← 解引用，与 main 同值

git ls-remote git@github.com:Decilix-Intelligence/GeneQuant.git
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   HEAD
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   refs/heads/main          ← 本轮只核不推，没动
```

上一轮终值 `f466f1c9…` 被 force 掉（force 掉的是**我们自己上一轮推的同一棵树**，用户已明文授权）。
tag `v1.0.16` 沿用卡 R2 的既定取舍：**跟着移到新 commit**，三条版本轴（`1.0.16` / `r1.0.23` / `p1.0.0`）
一条都没动，不新建号。

#### Release：只 `PATCH` 了 `target_commitish`，附件一个字节没动

| 项 | 推前 | 推后 |
| --- | --- | --- |
| release id | `387775425` | `387775425`（**没变**） |
| `target_commitish` | `f466f1c9…` | `5e4e179e…`（`PATCH` 回 **200**） |
| `genebench_public_provider_v1.tar.gz` | 782,100,276 / `uploaded` | **同上，没变** |
| `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 / `uploaded` | **同上，没变** |

远端 `digest`（GitHub 自己算的）与本地 `sha256` 逐字相同：
`33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9`（provider）、
`edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06`（gold 子集）。

**当轮为什么要 `PATCH`**：见 §8.2 末尾与 `HANDOFF.md` §19.6.5 ——
不 `PATCH` 的话 Release 会指向一个没有任何 ref 的悬空 commit。改完立刻回核
「tag 仍指新 commit / release id 不变 / 两件附件仍 `uploaded` 且 `digest` 不变」，三样都没变。
<!-- P2-2026-09-13 -->
**这条纪律 2026-09-13 已整条作废**（用户裁定 ①，N-748 采纳、N-736 删除）：
`target_commitish` 改写**分支名 `main`** 之后永不悬空，不再有「推完要记得 `PATCH`」这件事。
本段是当轮做法的留证，不是今天的做法。

#### 匿名回核两件附件（**没有把 782 MB 再下一遍**）

不带任何凭据、带 `Range: bytes=0-0` 的 GET，两件都回 **206**：

```
content-range: bytes 0-0/782100276     genebench_public_provider_v1.tar.gz
content-range: bytes 0-0/157448605     genebench_public_gold_subset_v1.tar.gz
```

总长度与登记表一致。整件的 `sha256` 在卡 R1 §7.2 已经下回来重算并逐字比对过，
而本轮**一个字节都没重打包**，加上远端 `digest` 与本地逐字相同，等价于又核了一遍。

#### 树的内容回核（从远端按 `ref=main` 取回，逐件比对）

七个文件全部 **HTTP 200 且与本地树逐字节相同**：`publish_report.md`、`s8_gold_reissue.md`、
`known_limits_v1.md`、`tickets.md`、`tickets_inbox/F.md`、`test_e.py`、`RELEASE_MANIFEST.json`。
逐条判据（`want` / `got` 全对）：

* `附件清单为空` —— **0 命中**（本轮那条门的判据）；
* 「已建 Release `v1.0.16`（id `387775425`）」、两条完整 `sha256`、`782,100,276` / `157,448,605` —— **都在**；
* 「未达成」「`contents=write`」「`403`」「`bd0513a4…`」—— **仍在**。
  这三样是另外两条门要的：`test_六条裁定逐条有判` 要求裁定 ③ 那一格仍含「未达成」、
  `## 三、BLOCKED` 一节仍含 `403` 与 `contents=write`；`test_handoff_与报告记的远端sha是同一个`
  要求报告里仍有 2026-09-12 那个 `bd0513a4…`。**这三条门合起来的意思是：
  `publish_report.md` 是 2026-09-12 那一轮的存档，不是活文档** —— 所以本轮的改法是
  「现状写进 §一 并加显式日期，旧结论原样留证 + 标日期」，而不是把旧结论删掉。
* `5e4e179e…`（本轮 commit）—— **报告里 0 命中**，进树的文档不写自己那棵树的 sha（N-737）。

机读证据：`$GB/scratch/F/remote_content.json`。

#### 署名形态复扫

公开树 2,189 个文件，**署名形态 1 条** —— `ops/reports/release_scan_claude_mentions.md:17`
那条**自指** —— 那一行是判据表**自己**，它把各种署名形态（共同作者行、`Generated with …` 行、机器人表情、厂商 `noreply@` 邮箱）逐条列成了判据，于是被自己的扫描器扫到。既定口径保留。
技术语境的提及 451 条（harness 名 `claude-code` 之类），不是署名。
`.git` 整棵 grep 两个关键词 **0 命中**。机读证据：`$GB/scratch/F/mentions_f.json`。

#### 外部用户视角：空目录里 clone 一次，跑一次 pytest

> **下面注释里的 sha 与件数是卡 F 那一轮（2026-09-13）的实测输出，留证用，**不是**你现在会看到的值** ——
> 卡 W 之后又重打并推过一轮，`git log -1` 与 `git ls-files | wc -l` 都会不一样。
> 按口径 `ops/HANDOFF.md` §19.6.6，**自核只比三条命令彼此同值**，不跟写死的值比：
> `git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16`。
> （那一行 `pytest ... # 31 passed, 1 skipped` 不属于会变的终值，卡 V 独立复核时复现过同样的数。）

```
git clone git@github.com:Decilix-Intelligence/GeneBench.git    # 91 秒
git log -1 --format='%H'    # 5e4e179e1603236117f8b27f3530a5dc4cec6612
git rev-list -n1 v1.0.16    # 同上
git ls-files | wc -l        # 2189
git log -1 --format='%an <%ae>'   # 深情代码大师 <2994718175@qq.com>，body 为空
pytest ops/test_e.py ops/test_d.py -q   # 31 passed, 1 skipped
```

**那 1 条 skip 不是本轮引入的**：`ops/test_d.py:146` 按绝对路径找
`/data/shared/genebench/repo/ops/tickets_inbox/D.md`，那个名字在发布收尾卡已并表改名，
找不到就 `skip`（不是 fail）。在内网仓库里跑同样是 31 passed / 1 skipped，两边一致。

**登记一条（推后实测到的，不修）**：从 f01 **匿名 HTTPS** clone 这个仓库**不稳** ——
`fetch-pack: unexpected disconnect while reading sideband packet`，连试都断；
同一时刻 **SSH clone 91 秒一次成功**。匿名带 `Range` 的附件 GET 也断过三次
（`rc=56` / `rc=28` 各若干）再成功。这与 N-729 记的是同一件事：
**f01 → GitHub 的下行既慢又抖，凡是打 GitHub 的验收步骤都要自带重试**，
否则会假失败。**这是 f01 这条链路的事，不是仓库的事** —— 外部用户不受影响。

#### 本轮动远端的次数

`push --force` 两次（`main` 一次、`refs/tags/v1.0.16` 一次）+ `PATCH` Release 一次。
force 掉的都是我们自己上一轮推的同一棵树。**没有新建 Release、没有重传任何 asset、
没有碰 GeneQuant。**

#### 推完之后公开树落后内网 HEAD 两个文件（**预期内**）

本节（§8.3）是推完才提交的，随它一起进内网仓库的还有 `RELEASE_MANIFEST.json` ——
重出清单时只有 `generated_at` 一行变了（`push_result.md` 不在清单登记的 53 件发布件里），
`--check` 仍退 0、`releasable=true`、未闭合 blocker 0。
所以推完之后公开树落后内网 HEAD 的就是这两个文件：
`ops/reports/push_result.md` 与 `RELEASE_MANIFEST.json`。**这是预期的**，
和上一轮 §8.2 的情形一样，下一轮重打树时会一起带上。

### 8.4 第四轮重打与推送（卡 W，2026-09-13）：本轮终值

> **这一小节和 §8.1 / §8.2 / §8.3 一样，是推完之后才提交进内网仓库的，所以它不在本轮推上去的那棵树里。**
>
> 本轮把这件事**从惯例升格成口径**：`ops/HANDOFF.md` **§19.6.6「树内不记终值」**（N-743）。
> 要点一句话：**进公开树的文件里不写 `refs/heads/main` sha、tag 对象 sha、公开树件数这三类会变的值**；
> 要人自核只写**自核不变量**；推后终值**只记在这里**。
> 于是「每重打一次树，树内写死的终值就变成假话」这个递归**不再需要每轮追一条更正** ——
> 它已经被挪出树外了。这个坑到本轮为止**三轮踩了三次**（§5 对 `§6`/`§6.7`、§8.3 对 `§8.1`/`§8.2`、
> 卡 V 实测到的 `HANDOFF.md` §19.6.1 与 `release_upload_report.md` §三）。

#### 为什么又推一次

卡 V（外部用户视角独立复核，只读、零模型 API）在卡 F 推上去的那棵树里实测出
**3 条 block + 4 条 major**，根因是同一个：**卡 F 把红修好了，但「指着旧状态说话」的文件
和「记着推送前 sha」的表不在卡 F 的六个路径里。** 于是外部用户拿到的树里仍写着
「有一条真红、文档在对外说假话、你跑 `pytest` 会看到」，而实跑是 **31 passed / 1 skipped 全绿**；
`HANDOFF.md` §19.6.1 还在同一行给了 `git ls-remote` 当核对命令 —— 照着敲**三处全对不上**。

本轮把这七条一次修完，并**断掉复发根因**。
**一个字节都没重打包、没重传或删除任何 asset、没新建 Release、没推 GeneQuant、三条轴一条没动。**
内网提交：`fe1ae4e`（8 件）、`efe17e8`（`push_result.md` 两个小节标题补时点）。

#### `git ls-remote` 两个远端（推后实测）

```
git ls-remote git@github.com:Decilix-Intelligence/GeneBench.git
    06678a44bb7a980d175b4393984ffb51f78a1803   HEAD
    06678a44bb7a980d175b4393984ffb51f78a1803   refs/heads/main
    0c662a379f96bdcdd25f960f90291c51c8928d2b   refs/tags/v1.0.16        ← annotated tag 对象
    06678a44bb7a980d175b4393984ffb51f78a1803   refs/tags/v1.0.16^{}     ← 解引用，与 main 同值

git ls-remote git@github.com:Decilix-Intelligence/GeneQuant.git
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   HEAD
    6ce7664e84e467c39d11bb4ec88209bdae6a7c92   refs/heads/main          ← 本轮只核不推，没动
```

上一轮终值 `5e4e179e…` 被 force 掉（force 掉的是**我们自己上一轮推的同一棵树**，用户已明文授权）。
tag `v1.0.16` 沿用既定取舍：**跟着移到新 commit**，三条版本轴（`1.0.16` / `r1.0.23` / `p1.0.0`）
一条都没动，不新建号。公开树 **2,191 件**、单次提交、作者=提交者 **深情代码大师
`<2994718175@qq.com>`**、提交 body 空、署名形态复扫 **1 条**（`release_scan_claude_mentions.md`
自指，既定口径保留）。

#### Release：只 `PATCH` 了 `target_commitish`，附件一个字节没动

| 项 | 推前 | 推后 |
| --- | --- | --- |
| release id | `387775425` | `387775425`（**没变**） |
| `target_commitish` | `5e4e179e…` | `06678a44…`（`PATCH` 回 **200**） |
| `genebench_public_provider_v1.tar.gz` | 782,100,276 / `uploaded` / `sha256:33083ff2…` | **同上，没变** |
| `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 / `uploaded` / `sha256:edc5ea7c…` | **同上，没变** |

**踩到一个新坑（N-749）**：`PATCH` 头两次回 **500（响应体为空，带 `X-GitHub-Request-Id`）**，
第三次同样的请求回 **200**。`scratch/R2/r2_patch_release.py` 的 `api()` **只对网络异常重试，
对 HTTP 5xx 直接返回** —— 于是一次瞬时 500 看上去像硬失败。判别办法与补法见 N-749。
（同一轮里还撞到 `SSL: UNEXPECTED_EOF_WHILE_READING` 两次、匿名 `ls-remote` 连不上两次，
都是 N-729 记的那条链路问题，重试即过。）

#### 外部用户视角：空目录 clone 一次，自核一次，跑一次 pytest

```
git clone git@github.com:Decilix-Intelligence/GeneBench.git     # 83 秒
git log -1 --format='%H'                == git ls-remote origin refs/heads/main
                                        == git rev-list -n1 v1.0.16      ← 三者同值 [绿]
git ls-files | wc -l                    # 2191
git log -1 --format='%an <%ae>'         # 深情代码大师 <2994718175@qq.com>，body 为空
pytest ops/test_e.py ops/test_d.py -q   # 31 passed, 1 skipped
```

**注意这个代码块和上一轮那个的区别**：这里**没有把 sha 写成期望值**，只写「三者同值」——
这就是 §19.6.6 要的写法，它下一轮不会变成假话。
（`2191` 与 `83 秒` 是本轮实测，留证；件数会随下一轮改动而变，别拿它当判据。）

**完全匿名（不带 token、不带 SSH key）复核**：`ls-remote` 三条 ref 与上表逐字相同；
`GET /releases/tags/v1.0.16` 回 id `387775425`、`draft=false`、`prerelease=false`、
两件 `state=uploaded` 且 `digest` 与上表逐字相同；两件附件 `Range: 0-0` 各回 **206 / 1 字节**。
机读证据 `$GB/scratch/W/{anon.log,userwalk.log}`。

#### 推之前在打好的树上扫了一遍「会过期的话」

脚本 `$GB/scratch/W/w_scan_stale.py`（三类：写死 sha / 现在时的过时口径 /「还欠什么」表里的「挡」行），
逐条判据与结论写在 `ops/tickets_inbox/W.md`。判出 **2 条真错**（`push_result.md` §8.1 与 §8.3
两个「叫读者照着敲」的代码块里写死了当轮期望值），**改完才打树**。
改完之后 (a) 类由 43 条降到 **10 条，且全部落在「外部用户最可能读的」之外** ——
剩下的是 `integrations/*/README.md` 里**有意钉死**的第三方上游 commit、npm `shasum`、
以及因子定义 JSON 里的 id，**都不是终值**。

#### 推完之后公开树落后内网 HEAD 两个文件（**预期内**）

本节（§8.4）与 `ops/tickets.md` 的 N-748 / N-749 是推完才提交的。
所以推完之后公开树落后内网 HEAD 的就是这两个文件：`ops/reports/push_result.md` 与 `ops/tickets.md`
（`RELEASE_MANIFEST.json` 本轮**不用**跟着重出 —— 这两份都不在清单登记的 53 件发布件里）。
**这是预期的**，和前三轮一样，下一轮重打树时会一起带上。

### 8.5 第五轮重打与推送（卡 Q，2026-09-13）：本轮终值

> **本小节整节被标题标了时点**（N-743 / 卡 W 的扫描口径）：下面的 sha、tag 对象、件数都是
> **2026-09-13 卡 Q 推完那一刻**的实测值，不是永远的现状。要现值请自己 `git ls-remote`。
> 与前四轮一样，本节与 `ops/tickets.md` 的 §Q 是**推完之后才提交的**，所以**不在这一轮推上去的树里**。

#### 为什么又推一次

2026-09-13 的 macOS 外部验收（用户在干净 Mac 上做，报告在本机之外）报了八项里五项没过。
随后 A2 / B2 / C2 / D2 四张卡把东西落进内网仓库，P1 / P2 / P3 三张卡把剩下的真阻塞修完，
**一律没推**。本轮把这些一次推上去，并把**第三件附件**传上已发布的 Release。

本轮新进树的（前四轮都没有）：`build/` 五件（统一基座的构建上下文 —— 外部用户自己构基座就靠它，
正是 macOS 验收卡点 ①）、`ops/selfcheck_public.py`（外部六项自检）、`ops/test_docs_consistency.py`、
卡 P1 的 `ops/test_P1.py`、卡 B2 的公开运行物料登记与数据卡。**逐件核过它们真的在树里** ——
`mk_tree_g2.sh` 走的是 `git archive HEAD`，没被 git 收进去的文件不会进树（那正是缺件 ② 的根因）。

#### 第三件附件：传上**已在的** Release，不新建、不碰已在的两件

| | 值 |
| --- | --- |
| 包 | `genebench_public_runtime_v1.tar.gz` |
| 字节 / `sha256` | **42,046,516** / `49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f`（**脚本现场从盘上算**，没有照抄文档里的旧值） |
| Release | id **387775425**、tag `v1.0.16`（**没有新建**） |
| asset id / state | `561398049` / `uploaded`，一次传成（42 MB / 6 s / 7.5 MB/s） |
| 远端 `digest` | `sha256:49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f` —— 与本地逐字相同 |
| 地址 | `https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16/genebench_public_runtime_v1.tar.gz` |

**已在的两件一个字节没碰**：上传前后各读一次 assets 列表，provider（id `560453545`）与
gold 子集（id `560455532`）的 `id` / `size` / `state` / `digest` / `created_at` / `updated_at`
**六个字段逐字相同**。上传脚本 `$GB/scratch/Q/q_upload_third.py` 的 `ASSETS` 只有第三件，
它的 `DELETE`（半截重传用）只会对这一个名字发。

#### `git ls-remote` 两个远端（推后实测）

```
# GeneBench —— 2026-09-13 卡 Q 推完那一刻
0004a265cc4e67072c8d829b4f0eb514f84353ff	HEAD
0004a265cc4e67072c8d829b4f0eb514f84353ff	refs/heads/main
f0374b99721ba6f7c0831e26fbf5e7b1296eaf60	refs/tags/v1.0.16
0004a265cc4e67072c8d829b4f0eb514f84353ff	refs/tags/v1.0.16^{}

# GeneQuant —— 本轮只核不推，与上一轮逐字相同
6ce7664e84e467c39d11bb4ec88209bdae6a7c92	HEAD
6ce7664e84e467c39d11bb4ec88209bdae6a7c92	refs/heads/main
```

推前是 `06678a44bb7a980d175b4393984ffb51f78a1803`（tag 对象 `0c662a379f96bdcdd25f960f90291c51c8928d2b`）。
树 **2,217 件 / 1 个提交**，作者与提交者均 `深情代码大师 <2994718175@qq.com>`，提交信息 `GeneBench v1.0.16 release`。

#### Release：`target_commitish` 按裁定 ① 改成**分支名** `main`

`PATCH /repos/Decilix-Intelligence/GeneBench/releases/387775425 {"target_commitish": "main"}` → **HTTP 200**，
读回来确认就是 `"main"`（推前是 `06678a44…` 那个 sha）。PATCH 前后各读一次 release + assets 逐字比对：
`id` / `tag_name` / `name` / `draft` / `prerelease` / `created_at` / `published_at` / `html_url`
与**三件附件**的 `id` / `size` / `state` / `digest` / `browser_download_url` **一个字段都没变**
（机读证据 `$GB/scratch/Q/q_patch_result.json`，`problems` 为空数组）。

**N-736 那条「每次 force-push 之后手工 PATCH」的纪律，本轮起整条作废**（裁定 ①）——
tag 已存在时这个字段对 tag / 附件 / 下载地址一概无影响，写成分支名之后也不会再随重打树失效。
§8.2 / §8.3 里那两格已由卡 P2 标成留证。

#### 三件附件匿名回核（**没有把 782 MB 再下一遍**）

不带 token、带 `Range: bytes=0-1023` 各 GET 一次，**三件全部 HTTP 206**：

```
genebench_public_provider_v1.tar.gz     206  content-range: bytes 0-1023/782100276
genebench_public_gold_subset_v1.tar.gz  206  content-range: bytes 0-1023/157448605
genebench_public_runtime_v1.tar.gz      206  content-range: bytes 0-1023/42046516
```

三个总长与 `ops/release/attachments.json` 的 `bytes` 逐字相同。GitHub 的 asset `digest` 就是 `sha256`，
已在上表逐字比对过，所以不需要整件下回来。

#### 树的内容回核（从远端按 `ref=main` 取回，逐件比对）

`$GB/scratch/Q/q_remote_content.py`：13 份关键文件从 GitHub Contents API 按 `ref=main` 取回，
**逐字节等于本地打好的树**，并且每一份既查「新写法在不在」也查「旧说法还在不在」：

| 文件 | 字节 | 逐字节 | 判据 |
| --- | ---: | :---: | --- |
| `README.md` | 55,983 | ✓ | 有「三个附件挂在 GitHub Release」「第三件也挂上了」与第三件的 `sha256`；**没有**「本轮它还没有上传到 Release」「非零 ≠ 发布件损坏」 |
| `docs/OPERATOR_MANUAL.md` | 100,723 | ✓ | 有「2026-09-13 下午它也传上了同一个 Release」；**没有**「但它本轮还没有上传到 Release」「当前只到 `_staging_unpublished/`」 |
| `ops/release/attachments.json` | 3,797 | ✓ | 三条 `download_url` 都回填；**没有**空串 |
| `RELEASE_MANIFEST.json` | 22,887 | ✓ | `release_attachments` `n=3 / uploaded=3` |
| `ops/reports/publish_report.md` | 21,401 | ✓ | 有「状态：已上传」与解除回执；**没有**子串「附件清单为空」（`ops/test_e.py` 那条双向门的另一面） |
| `ops/data_cards/public_runtime_v1.md` | 6,706 | ✓ | `download_url` 那一格已回填 |
| `ops/test_docs_consistency.py` | 9,568 | ✓ | fact 已是 `manifest_check_is_machine_independent` |
| `ops/test_b2.py` | 11,053 | ✓ | 门已翻成 `…_and_uploaded` |
| `build/base/Dockerfile` / `build/README.md` | 5,063 / 912 | ✓ | **本轮第一次进树**（macOS 验收卡点 ①） |
| `ops/selfcheck_public.py` | 25,159 | ✓ | 本轮第一次进树 |
| `ops/test_P1.py` | 19,583 | ✓ | 本轮第一次进树 |
| `ops/tickets_inbox/Q-push.md.merged` | 6,596 | ✓ | N-797 ~ N-804 都在 |

机读证据 `$GB/scratch/Q/q_remote_content.json`，`bad` 为空数组。

#### 推之前在打好的树上扫了一遍

* `scratch/P/scan_mentions.py`：扫 2,217 个文件，**署名形态 1 条** —— 仍是
  `ops/reports/release_scan_claude_mentions.md` 自己**描述这条规则**的那一行（历轮同判）；技术事实 458 条按五类保留。
* `scratch/W/w_scan_stale.py`：扫 542 份散文件。(a) 40 位 sha 无时点 **11 条** ——
  第三方上游 tarball 名 / npm `shasum` / 因子表达式 / 票据引文，**都不是终值**；
  (b) 现在时的过时口径 **255 条**，逐条判：落在 `README.md`（1 条，在删除线里）、
  `docs/OPERATOR_MANUAL.md`（7 条）、`DATA_LICENSE`（2 条）、`publish_report.md`（5 条，带「2026-09-12 当时」抬头）
  的都不是说假话，其余集中在 `ops/tickets.md` / `known_limits_v1.md` 的历史行 ——
  按扫描脚本自己的口径（「票据与已知限制表里**描述**这些子串是正常的」）属正常。
  **判出真错 1 条**：手册目录树图里「`release/` 发布包（当前只到 `_staging_unpublished/`）」，
  那个目录卡 R2 按 N-714 已整棵删除 —— **改完才重打树、才推**（N-806）。

#### 推完之后公开树落后内网 HEAD 两个文件（**预期内**）

本节（§8.5）与 `ops/tickets.md` 的 §Q 补记是推完才提交的，所以推完之后公开树落后内网 HEAD 的就是
`ops/reports/push_result.md` 与 `ops/tickets.md` 这两份（都**不在**清单登记的 58 件发布件里，
所以 `RELEASE_MANIFEST.json` 本轮**不用**再重出一次，`--check` 仍退 0）。和前四轮一样，下一轮重打树时会一起带上。

### 8.6 第六轮重打与推送（卡 S，2026-09-13）：本轮终值

> **本节是推完之后才提交的**（N-743「树内不记终值」）—— 它不在刚推的那棵树里，
> 下一轮重打树时会一起带上。自核仍然只用**自核不变量**：
> `git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16` 三者同值。

**推的是什么**：卡 S 的收口一轮 —— 终核卡 Rfin 抓到的六条修掉（N-808 / N-809 / N-810 /
N-811 / N-812 / N-813 / N-815）、一条闭掉（N-814 裁定③ 扫尾）、按用户裁定把预算档写进
README 与手册两处（N-817）、`known_limits_v1.md` 补 D-06 家族第五例并重新点数（135 → 142）。
内网提交 `b74491fba537781e5127f3a58f92d06e31bb7132`（10 个文件，+396 / −30）。

| 项 | 推前 | **推后（本轮终值）** |
| --- | --- | --- |
| `refs/heads/main` | `0004a265cc4e67072c8d829b4f0eb514f84353ff` | **`2b1de09c6e1f0954476e07cd3e5019200ba49eaf`** |
| `refs/tags/v1.0.16`（tag 对象） | `f0374b99721ba6f7c0831e26fbf5e7b1296eaf60` | **`c9935fd8526e9eb00b77589a86a60ceda59f62fc`** |
| `refs/tags/v1.0.16^{}`（解引用） | `0004a265…` | **`2b1de09c…`**（与 main 同值） |
| 公开树件数 | 2,217 | **2,219**（新增 `ops/tickets_inbox/S.md`） |
| GeneQuant `refs/heads/main` | `6ce7664e84e467c39d11bb4ec88209bdae6a7c92` | **`6ce7664e…`（一个字节没推）** |

**Release 回核（匿名 GET，没带 token）**：`id = 387775425`、`tag_name = v1.0.16`、
**`target_commitish = "main"`（字符串，仍是裁定① 落下的那个值）**、`draft/prerelease = False/False`。
所以本轮 force-push 之后**没有也不需要 PATCH** —— 这正是裁定① 的红利。
三件附件五个字段一个没变：

| asset id | 名字 | size | state | digest |
| ---: | --- | ---: | --- | --- |
| 560453545 | `genebench_public_provider_v1.tar.gz` | 782,100,276 | `uploaded` | `sha256:33083ff242c64a8f…` |
| 560455532 | `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `uploaded` | `sha256:edc5ea7cf70ffec3…` |
| 561398049 | `genebench_public_runtime_v1.tar.gz` | 42,046,516 | `uploaded` | `sha256:49e9b250d398a1ce…` |

原始输出 `$GB/scratch/S/release_recheck.txt`、`$GB/scratch/S/push.log`。
**本轮没有传任何附件、没有重打任何包、没有改任何一件 asset。**

#### 推之前在打好的树上扫了两遍，逐条人工判

* `scratch/P/scan_mentions.py`：扫 **2,219** 个文件，**署名形态 1 条** —— 仍是
  `ops/reports/release_scan_claude_mentions.md` 自己**描述这条规则**的那一行（历轮同判，不是署名）；
  其余是技术事实（harness 名 `claude-code`、`pricing.yaml` 里的供应商与域名等）按五类保留。
* `scratch/W/w_scan_stale.py`：扫 **544** 份散文件。(a) 40 位 sha 无时点 **11 条** ——
  第三方上游 tarball 名 / npm `shasum` / 因子表达式 / 票据引文，**都不是终值**；
  (b) 现在时的过时口径 **262 条**、(c)「还欠什么 / 挡不挡」行 **34 条**，
  逐条按「**这句话是不是在对外说假话**」判（不按子串计数）：
  绝大多数落在 `ops/tickets.md` / `known_limits_v1.md` 的历史行与**门的判别力描述**
  （「……当场红」说的是这道门有牙，不是现在有一条红），以及签字包里的只读归档副本。
  **本轮判出真错 0 条** —— 上一轮那条（手册目录树图的 `_staging_unpublished/`，N-806）
  卡 Q 已经改掉，本轮复扫不再出现。
  本轮新增的那几行（`known_limits_v1.md` 的 S 节）都带 **【已修】** 标记且落在
  「### 本轮逐条（六条修、一条闭）」这条标题链下，按扫描脚本自己的口径属**留证**。
* **本轮新记一条扫描口径（N-816）**：`w_scan_stale.py` **只扫 `.md`**，
  而本轮唯一一条对外说假话的句子（N-808）在 `.py` 里 —— 那类扫描**结构性地看不到它**。
  下次扫「文档说没说假话」要把**会打印给用户看的 `.py`**
  （`ops/selfcheck_public.py` 这样的自检、各 CLI 的 `--help` 与提示文案）一并纳入射程。

#### 推完之后公开树落后内网 HEAD 一个文件（**预期内**）

本节（§8.6）是推完才提交的，所以公开树落后内网 HEAD 的就是 `ops/reports/push_result.md` 这一份
（**不在**清单登记的 58 件发布件里，所以 `RELEASE_MANIFEST.json` 本轮**不用**再重出，`--check` 仍退 0）。
下一轮重打树时会一起带上。

### 8.7 第七轮重打与推送（卡 U，2026-09-13）：本轮终值

> **本节是推完之后才提交的**（N-743「树内不记终值」）—— 它不在刚推的那棵树里，
> 下一轮重打树时会一起带上。自核仍然只用**自核不变量**：
> `git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16` 三者同值。

**推的是什么**：卡 U —— 终核卡 Tfin 站在**外部用户那一侧**在全新 clone 上实测出的六条，
本卡全修（N-818 block / N-819 major / N-820 / N-821 / N-822 / N-823），另登记一条（N-824）。
其中 **N-818 是挡在「用户在干净 Mac 上重跑验收」前面的最后一件**：照 README §2.1 建 venv，
网关就永远起不来，而文档给的修法（`ops/guard_modes.py --harden`）是空转 ——
`check()` 跟随符号链接取 mode、`harden()` 却跳过符号链接，**两个函数口径相反**，
于是 `bin/python* -> /usr/bin/python3.12`（0755、root 所有）这三条链
**结构上不可能被 harden 修好**。内网提交 `a6e35f5`（12 个文件，2 新增）。

| 项 | 推前 | **推后（本轮终值）** |
| --- | --- | --- |
| `refs/heads/main` | `2b1de09c6e1f0954476e07cd3e5019200ba49eaf` | **`e24c6143ffe9ae25a39684170fd6c79706ad21c1`** |
| `refs/tags/v1.0.16`（tag 对象） | `c9935fd8526e9eb00b77589a86a60ceda59f62fc` | **`270edc202f5002af3bd4122c0a0498f22b9acf21`** |
| `refs/tags/v1.0.16^{}`（解引用） | `2b1de09c…` | **`e24c6143…`**（与 main 同值） |
| 公开树件数 | 2,219 | **2,222**（新增 `ops/tickets_inbox/Tfin.md`、`ops/test_U.py`、`ops/tickets_inbox/U.md`） |
| GeneQuant `refs/heads/main` | `6ce7664e84e467c39d11bb4ec88209bdae6a7c92` | **`6ce7664e…`（一个字节没推）** |

**Release 回核（匿名 GET，没带 token）**：`id = 387775425`、`tag_name = v1.0.16`、
**`target_commitish = "main"`（字符串，仍是裁定① 落下的那个值）**、`draft/prerelease = False/False`。
所以本轮 force-push 之后**没有也不需要 PATCH**。三件附件五个字段一个没变
（`download_count` 是计数器，不是我们钉的字段）：

| asset id | 名字 | size | state | digest |
| ---: | --- | ---: | --- | --- |
| 560453545 | `genebench_public_provider_v1.tar.gz` | 782,100,276 | `uploaded` | `sha256:33083ff242c64a8f…` |
| 560455532 | `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `uploaded` | `sha256:edc5ea7cf70ffec3…` |
| 561398049 | `genebench_public_runtime_v1.tar.gz` | 42,046,516 | `uploaded` | `sha256:49e9b250d398a1ce…` |

`created_at` 从 `2026-09-13T17:02:31Z` 变成 `18:28:11Z` —— 那是 tag 移到新 commit 之后
GitHub 自己重盖的时间戳，`tag_name` / `id` / `published_at` 都没动，不是我们改的。
原始输出 `$GB/scratch/U/release_anon.txt`、`$GB/scratch/U/push.log`。
**本轮没有传任何附件、没有重打任何包、没有改任何一件 asset、没有新建 Release。**

#### N-818 的实测（这一条是本轮唯一的 block，证据要能被复现）

在 `$GB` **之外**按 README §2.1 逐字建一棵真 venv（`/usr/bin/python3.12 -m venv <root>/env`），
`GENEBENCH_ROOT` 指过去，**同一棵树上新旧两版各跑一遍**（`$GB/scratch/U/venv_fix.txt`）：

| | 旧版（`git HEAD`，N-818 未修） | **新版（本卡）** |
| --- | --- | --- |
| `guard_modes` 只查 | 3 条红（`env/bin/python` / `python3` / `python3.12`，`0o755`） | **退 0，「敏感根权限合规（2 个根）」** |
| `guard_modes --harden` | 「收紧 0 个条目」**退 1** | 收紧真实的那几件后**退 0** |
| 再查一次 | **仍是同样 3 条红**（死循环） | 退 0 |
| 三条软链还在不在盘上 | 在 | **在**（守门不替人删东西） |

另外三样：② 同一棵树起网关 —— `ops/selfcheck_public.py` 第 6 项 **[绿]**，
`http://192.168.1.48:48715/healthz = 200`（2 秒起来，`channel=public`、`backend=snapshot`）；
③ 造一个真的 `0644` 文件 + `0775` 目录 → `check` 退 1 并逐条列出 → `--harden` 收紧 2 条 → 退 0
（**判别力一个字没降**）；④ 造一条答案面断链 → 提示语不再说「修：`--harden`」，
而是「答案面根下的符号链接 1 条：**`--harden` 修不好**（它不替人删东西）—— 自己把这些链接删掉，
或换成实体文件」。门 `ops/test_U.py` 13 条，含**拿旧版 guard_modes 跑一遍**的反面判别
（`$GB/scratch/U/test_U_has_teeth.txt`：旧版两条断言当场红、新版通过）。

**`--copies` 判了不加**：`python3.12 -m venv --copies` 能绕开（实测 `--harden` 收紧 3 条、check 退 0），
但那是**绕**不是修 —— 代码修好之后那个开关没有活的理由，写进文档只会变成一句
没人知道为什么存在的咒语（还多占 ~24 MB）。README / 手册的建 venv 那一行一个字没改。

#### 推之前在打好的树上扫了两遍，逐条人工判

* `scratch/P/scan_mentions.py`：扫 **2,222** 个文件，**署名形态 1 条** —— 仍是
  `ops/reports/release_scan_claude_mentions.md` 自己**描述这条规则**的那一行（历轮同判，不是署名）；
  其余 461 条是技术事实（harness 名 `claude-code`、`pricing.yaml` 里的供应商与域名等）。
  **本轮改过的 12 个文件里新增的行，一条署名形态都没有。**
* `scratch/W/w_scan_stale.py`：扫 **546** 份散文件。(a) 40 位 sha 无时点 **11 条**、
  (b) 现在时的过时口径 **269 条**、(c)「还欠什么 / 挡不挡」行 **35 条**。
  按行号切出**本轮真正新增的那些行**（`known_limits_v1.md` > 1449、`ops/tickets.md` > 5803）
  逐条判：命中只有 **3 条**（`known_limits_v1.md:1535/1537`、`ops/tickets.md:5819`），
  三条都是 **N-820 那一行在「」里引用被删掉的旧句子**、或者明写「该目录已按 N-714 整棵删除」——
  按本轮口径（**判这句话是不是在对外说假话，不按子串计数**）属**留证**，不是假话。
  (a) 段 11 条一条都不在本卡改过的文件里 —— 本卡按 N-743 **没有往树里写任何终值**
  （main sha / tag 对象 / 件数三类一个都没写）。**本轮判出真错 0 条。**

#### 推完之后公开树落后内网 HEAD 一个文件（**预期内**）

本节（§8.7）是推完才提交的，所以公开树落后内网 HEAD 的就是 `ops/reports/push_result.md` 这一份
（**不在**清单登记的 58 件发布件里，所以 `RELEASE_MANIFEST.json` 本轮**不用**再重出，`--check` 仍退 0）。
下一轮重打树时会一起带上。
### 8.8 第八轮重打与推送（卡 W2，2026-09-13）：本轮终值

> **本节是推完之后才提交的**（N-743「树内不记终值」）—— 它不在刚推的那棵树里，
> 下一轮重打树时会一起带上。自核仍然只用**自核不变量**：
> `git -C $GB/release/trees/genebench log -1` == `git ls-remote origin refs/heads/main`
> == `refs/tags/v1.0.16^{}` 三者同值。

**推的是什么**：卡 W2 —— 终核卡 Vfin **完全照 README 逐字走了一遍外部用户的路**
（`0 block`、`tests_ok=true`）之后量出的两条 major，本卡全修：
**N-825**（README §2.1 与 §1.5 互相依赖，哪一边先敲都会失败 —— 而 §2.1 是用户复制粘贴的
第一个块）、**N-826**（`ops/test_d.py` 写死发布方内网路径 + 模块级 IO：外部整场中断、
内部对被测的那棵树毫无判别力）。另修两条 minor（**N-827** 文档补一句、**N-793** 闭合）、
新登记一条（**N-828**）。内网提交 `22de5db`（8 个文件）+ `d38efa5`（收口补一刀）。

| 项 | 推前 | **推后（本轮终值）** |
| --- | --- | --- |
| `refs/heads/main` | `e24c6143ffe9ae25a39684170fd6c79706ad21c1` | **`bd8b158dd292f26f2779cd7778dbe366ef884e66`** |
| `refs/tags/v1.0.16`（tag 对象） | `270edc202f5002af3bd4122c0a0498f22b9acf21` | **`8fcc82461e2195778e4149e0f74104d265f931ac`** |
| `refs/tags/v1.0.16^{}`（解引用） | `e24c6143…` | **`bd8b158d…`**（与 main 同值） |
| 公开树件数 | 2,222 | **2,224**（新增 `ops/tickets_inbox/Vfin.md`、`ops/tickets_inbox/W2.md`；`Tfin.md → Tfin.md.merged` 是改名，不增不减） |
| GeneQuant `refs/heads/main` | `6ce7664e84e467c39d11bb4ec88209bdae6a7c92` | **`6ce7664e…`（一个字节没推）** |

**Release 回核（匿名 GET，没带 token；原始输出 `$GB/scratch/W2/release_anon.txt`）**：
`HTTP 200`、`id = 387775425`、`tag_name = 'v1.0.16'`、
**`target_commitish = 'main'`（字符串，仍是裁定① 落下的那个值）**、
`draft / prerelease = False / False`。所以本轮 force-push 之后**没有也不需要 PATCH**。
三件附件五个字段一个没变：

| asset id | 名字 | size | state | digest |
| ---: | --- | ---: | --- | --- |
| 560453545 | `genebench_public_provider_v1.tar.gz` | 782,100,276 | `uploaded` | `sha256:33083ff242c64a8f…` |
| 560455532 | `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `uploaded` | `sha256:edc5ea7cf70ffec3…` |
| 561398049 | `genebench_public_runtime_v1.tar.gz` | 42,046,516 | `uploaded` | `sha256:49e9b250d398a1ce…` |

`created_at` 从 `2026-09-13T18:28:11Z` 变成 `19:46:03Z` —— 与上一轮同样，那是 tag 移到新 commit
之后 GitHub 自己重盖的时间戳；`tag_name` / `id` / `published_at`（`02:58:37Z`）都没动，不是我们改的。
**本轮没有传任何附件、没有重打任何包、没有改任何一件 asset、没有新建 Release。**

#### 推之前在打好的树上扫了两遍，逐条人工判

* `scratch/P/scan_mentions.py`：扫 **2,224** 个文件，**署名形态 1 条** —— 仍是
  `ops/reports/release_scan_claude_mentions.md` 自己**描述这条规则**的那一行（与上一轮推上去的
  那份**逐字节相同**，本卡一个字没动），历轮同判、不是署名。其余是技术事实
  （harness 名 `claude-code`、`pricing.yaml` 里的供应商与 `api.anthropic.com` 等）。
  **本轮改过的文件里新增的行，一条署名形态都没有。**
* `scratch/W/w_scan_stale.py`：扫 **547** 份散文件。(a) 40 位 sha 无时点 **11 条**、
  (b) 现在时的过时口径 **273 条**、(c)「还欠什么 / 挡不挡」行 **36 条**。
  按行号切出**本轮真正新增的那些行**（`ops/tickets.md` > 5825、`known_limits_v1.md` > 1573、
  新文件 `ops/tickets_inbox/W2.md`、README 本轮改的 §1.5 / §2.1 两块）逐条判：
  命中只有 **2 条**（`known_limits_v1.md:1671`、`ops/tickets_inbox/W2.md:13`），
  两条都是 **N-793 那一条**在明写「该目录**按 N-714 整棵删除**」——
  按本轮口径（**判这句话是不是在对外说假话，不按子串计数**；标题链带日期即算标住时点）
  属**留证**，不是假话。README 本轮新增的那几行**一条都没命中**。
  (a) 段 11 条一条都不在本卡改过的文件里 —— 本卡按 N-743 **没有往树里写任何终值**
  （main sha / tag 对象 / 件数三类一个都没写）。**本轮判出真错 0 条。**
  另：(c) 段里 `ops/tickets_inbox/V.md:25-27` 那三条「HANDOFF §19.6.4 仍把已闭合的事列成挡」
  **已经不成立** —— `ops/HANDOFF.md:2046` 起那张表卡 W 已逐行核过并把前两行划掉留证
  （本卡只核不改，那不是本卡的路径）。

#### 本轮两条 major 的实测（证据要能被复现）

**N-825**（`$GB/scratch/W2/n825_paste.txt`）：在一棵**全新 clone** 上，把改后的 §2.1 代码块
**整块复制、逐字粘贴**跑了一遍。**唯一替换**：第 4 行的 `/opt/homebrew/bin/python3.12` →
`python3.12`，依据是**该行自己的注释**「Linux 换 python3.12」（f01 是 Linux、没有 `/opt/homebrew`）；
`$GB` 照 README 原样取 `$HOME/genebench`（那台上原本不存在）。结果：**全程一条
`No such file or directory` / `Permission denied` 都没有**；`ops/selfcheck_public.py` 跑到底并
逐项给出可读的六项判定（绿 1 / 红 3 / 跳过 2），`ops/guard_modes.py --harden` 退 **0**。
顺带印证了 README §1.5 早就写着的「Linux 上 `python3 -m venv` 常常缺 `ensurepip`」：
f01 的 Ubuntu `python3.12` 正是如此（没有 root 的做法在手册 §1.2）——
而这**恰好**说明修法是对的：即使 `pip` 没装上，`$GB/env/bin/python` 已经在，
两条 `$PY …` 都**跑起来了**并给出可读的红，而不是「找不到解释器」。

**N-826**（`$GB/scratch/W2/n826_clone4.txt`，六段）：

| 段 | 做什么 | 结果 |
| --- | --- | --- |
| (a) | 克隆树上原样跑 `ops/test_d.py` | **15 passed / 3 skipped**，不再 collection 崩；skip 的理由里打的是**克隆树自己的**路径 |
| (b) | 把**克隆树自己的** README 里 provider 包 sha256 改坏一个字符 | **2 failed** —— 判别力在，读的确实是那棵树 |
| (c) | 还原 | 回到 **15 passed / 3 skipped** |
| (d) | 把克隆树的 `README.md` 挪走 | **整模块 skip**（`1 skipped`），**不是** collection 崩 |
| (e) | 旧版（那两行换成不存在的路径） | `Interrupted: 1 error during collection` —— 外部用户看到的样子 |
| (f) | **旧版原封不动**、克隆树 README 已被改坏 | **17 passed** 全绿 —— 「绿是假的」的实证 |

发布方那一侧：f01 内网仓库上 `ops/test_d.py` 仍是 **17 passed / 1 skipped**，
唯一那条 skip 还是原来那条（`ops/tickets_inbox/D.md` 不在），**没有一条断言退化成 skip**。
另按 AST 扫了全部 `ops/test_*.py` 的模块级语句（`$GB/scratch/W2/scan_hardcoded.txt`）：
与 N-826 同形的（模块级写死发布方路径 **且** 模块级 IO）**现在是 0 个**；
另有 12 个只有写死路径、没有模块级 IO，**不会整场中断**，逐条分类登记为 **N-828**（不修）。

#### 定向测试

`ops/test_e.py ops/test_d.py ops/test_release_manifest.py ops/test_pack_release.py
ops/test_docs_consistency.py ops/test_V2.py ops/test_b2.py ops/test_d2.py ops/test_A2.py
ops/test_P1.py ops/test_U.py ops/test_w1.py ops/test_env.py ops/test_env_guard.py`
→ **301 passed / 3 skipped**（12 分 55 秒，`flock pytest.lock` + `MemoryMax=6G`）。
补提交之后又跑了一遍与文档相关的五个文件 → **89 passed / 1 skipped**。
`$PY ops/mk_release_manifest.py --check` 退 **0**、`releasable = true`、未闭合 blocker **0**、
发布件 **58** 件、`release_attachments` **n=3 / uploaded=3**。

#### 推完之后公开树落后内网 HEAD 一个文件（**预期内**）

与历轮同样：`ops/reports/push_result.md`（就是本节）是推完才提交的，下一轮重打树时带上。

### 8.9 第九轮重打与推送（卡 Y，2026-09-13）：本轮终值

> **本节是推完之后才提交的**（N-743「树内不记终值」）—— 它不在刚推的那棵树里，
> 下一轮重打树时会一起带上。自核仍然只用**自核不变量**：
> `git -C $GB/release/trees/genebench log -1` == `git ls-remote origin refs/heads/main`
> == `refs/tags/v1.0.16^{}` 三者同值。

**推的是什么**：卡 Y —— 终核卡 **Xfin** 完全照 README 逐字走了一台干净外部机器的路
（`git clone --depth 1` + 三件附件 + 外部 3.12）之后量出的 **1 block + 2 major + 4 minor**，
按用户裁定**三条都修**并**加一道 3.12 冒烟门**。
**N-829**（block：`ops/joblist.py` 把子命令 `rebudget` 注册了两次 —— 3.10 不查重照跑、
**3.11 起查重**，于是 3.12 上 `--help`/`gen`/`stat`/`list`/`reset` 全部起不来，
README §2.4 的第一条命令当场死）、**N-830**（README §2.4 两条 `run_joblist` 没带
`--channel public`，默认 `private` = 静默跑一份外部永远拿不到的私有题集）、
**N-831**（`run_joblist`/`score_runs` 的 `F02` 写死、无 env 兜底，两处文档的常量表也都漏了它们）、
**N-832 / N-833 / N-834**（三条 minor：§2.1 先收紧再自检、两份文档门的路径判据收窄射程、
`ops/reports/d2_e2e/` 那份证据随树发）、**N-837**（手册那条锁落点判据的机器依赖）、
**N-836**（新增 `ops/test_Y.py`）、**N-370 更新**（复现，不重新发号）、**N-835 / N-838**（登记）。
内网提交 `773b50f`（15 个文件）+ `d696972`（4 个）+ `5d38a68`（7 个）。

| 项 | 推前 | **推后（本轮终值）** |
| --- | --- | --- |
| `refs/heads/main` | `bd8b158dd292f26f2779cd7778dbe366ef884e66` | **`eb9c8508afbf05d3b607cb16accce6dda28ecd2f`** |
| `refs/tags/v1.0.16`（tag 对象） | `8fcc82461e2195778e4149e0f74104d265f931ac` | **`d116937982c3477c9204d8281560ee92843c257a`** |
| `refs/tags/v1.0.16^{}`（解引用） | `bd8b158d…` | **`eb9c8508…`**（与 main 同值） |
| 公开树件数 | 2,224 | **2,230** |
| GeneQuant `refs/heads/main` | `6ce7664e84e467c39d11bb4ec88209bdae6a7c92` | **`6ce7664e…`（一个字节没推）** |

**件数 +6 的逐件账**（`git diff --name-status --diff-filter=AD d38efa5 HEAD`，删除 **0** 件）：
`ops/tickets_inbox/Xfin.md`（卡 Xfin 的收件箱，提交 `22e8007`，**不是本卡的**）、
`ops/test_Y.py`、`ops/tickets_inbox/Y.md`、
`ops/reports/d2_e2e/{README.md, run_states.csv, table_main_excerpt.csv}`。

**Release 回核（匿名 GET，没带 token；原始输出 `$GB/scratch/Y/release_anon.txt`）**：
`HTTP 200`、`id = 387775425`、`tag_name = 'v1.0.16'`、
**`target_commitish = 'main'`（字符串，仍是裁定① 落下的那个值）**、
`draft / prerelease = False / False`。所以本轮 force-push 之后**没有也不需要 PATCH**。
三件附件五个字段一个没变：

| asset id | 名字 | size | state | digest |
| ---: | --- | ---: | --- | --- |
| 560453545 | `genebench_public_provider_v1.tar.gz` | 782,100,276 | `uploaded` | `sha256:33083ff242c64a8f…` |
| 560455532 | `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `uploaded` | `sha256:edc5ea7cf70ffec3…` |
| 561398049 | `genebench_public_runtime_v1.tar.gz` | 42,046,516 | `uploaded` | `sha256:49e9b250d398a1ce…` |

`created_at` 从 `2026-09-13T19:46:03Z` 变成 `2026-09-14T05:50:05Z` —— 与前几轮同样，
那是 tag 移到新 commit 之后 GitHub 自己重盖的时间戳；`tag_name` / `id` /
`published_at`（`2026-09-13T02:58:37Z`）都没动，不是我们改的。
**本轮没有传任何附件、没有重打任何包、没有改任何一件 asset、没有新建 Release。**

**匿名回核这一步本轮抖了两次。** f01 → `api.github.com` 的 TLS 握手连着两次
`ssl.SSLEOFError: [SSL: UNEXPECTED_EOF_WHILE_READING]`，**同一时刻 `curl` 打同一个 URL 回 200** ——
所以是链路抖动，不是拒绝、也不是限流（限流会回 403 + `X-RateLimit-Remaining: 0`）。
第 3 次成功。下一轮照抄 `$GB/scratch/Y/y_anon.sh`（就是 `scratch/W2/anon.py` 外面套了一层
最多 8 次、间隔 8 秒的重试），别把一次 SSLEOFError 读成「Release 没了」。

#### 推之前在打好的树上扫了两遍，逐条人工判

**① `scratch/P/scan_mentions.py`**（2,230 个文件全扫）：
* **署名形态 1 条** —— `ops/reports/release_scan_claude_mentions.md:17`，那是**这份扫描报告
  自己的规则表**（署名 trailer / `Generated with` 行 / 机器人表情，三类「一律删」）。它是**被扫描器
  命中的规则原文**，不是一条真的署名，**自指**，前几轮同值。
* **事实性提及 465 条** —— 逐类：harness 目录/ID `claude-code` **177**（本 benchmark 五个
  harness 之一，是我们自己的目录名）、供应商名（技术语境）**110**、`Claude`（技术语境）**107**、
  出向白名单/实测域名 `api.anthropic.com` **38**（红线 5 要求白名单**写出来**，删掉才是错）、
  harness 名 `Claude Code` **24**、wire 形状 `Anthropic Messages API` **8**、模型 id **1**。
  **一条真错都没有。** 落在**本卡新增的四件文件**（`ops/test_Y.py`、`ops/tickets_inbox/Y.md`、
  `ops/reports/d2_e2e/` 三件）上的 **0 条**。
* **② `scratch/W/w_scan_stale.py`**（550 份散文件）：**(a) 11 / (b) 280 / (c) 37**。
  与卡 Xfin 在克隆树上量到的 **(a) 11 / (b) 273 / (c) 36** 相比：
  **(a) 一条没动**（全是上游仓库的 commit sha 与 npm shasum —— 那是**钉住的版本**，不是过期口径）；
  **(b) +7**：**5 条是本卡自己的正文里出现了「当场红」三个字**（在讲某条判据的**判别力**，
  例如「注入一个重复注册 → 当场红」「手册把 `locks/` 写成别的，当场红」）——
  扫描器按关键词命中，**不是过期口径**；另 2 条是卡 Xfin 收件箱与 `push_result.md` 里
  **各自那一轮的实测记录**（「(b) 273 条 / (c) 36 条」），都是**带卡号与日期的历史记账**，
  不是对外说的现在时。
  **(c) +1**：`ops/reports/push_result.md:1163` —— 卡 W2 §8.8 记自己那一轮扫描条数的那一行，同上。
  **一条真错都没有**，所以没有回头改树。

#### 本轮的一条「红是对的」

第一次提交之后复跑定向测试，`ops/test_V2.py::test_每个出了主表的批都有两张全量指标表`
当场红。查下来**那条红是对的**：`_main_table_dirs()` 按 `ops/reports/<x>/table_main.csv`
这个**文件名**认「批 `<x>` 出了主表」，认出来就要求同目录还带六件全量指标表；
而按 N-834 放进去的 `ops/reports/d2_e2e/` 是一份**摘录证据**，不是批的产物目录。
**修法是把名字说清楚**（`table_main.csv` → `table_main_excerpt.csv`），
不是往证据目录里塞六件它本来就没有的表 —— 后者会让那道门从此认一个假批。
三处引用同步改，并在 `d2_e2e/README.md`、`known_limits_v1.md`、票据三处写明**为什么不能叫那个名字**。

### 8.10 第十轮重打与推送（卡 D9，2026-09-14）：本轮终值

> 本轮的由来是**单机形态**那一轮：卡 A9（裁定 ①② 代码侧）、卡 B9（裁定 ③ 那道门）、
> 卡 C9（裁定 ④⑤ 文档侧）、卡 D9（本卡：收口 + 重打树 + 推）。
> 三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`）**一个值没改**，没重算 τ / ε，
> 没重打任何包、没传任何附件、没新建 Release、**推完没有 PATCH**。

#### 本轮终值（内网记，按 N-743 不进树）

| 什么 | 推之前 | **推之后** |
| --- | --- | --- |
| `refs/heads/main` | `eb9c8508afbf05d3b607cb16accce6dda28ecd2f` | **`453eddf2e50eb0ff1f8a400429518456cc56b683`** |
| `refs/tags/v1.0.16`（tag 对象） | `d116937982c3477c9204d8281560ee92843c257a` | **`8df27b2a842c6fcc44676943943c9503bd5a0292`** |
| `refs/tags/v1.0.16^{}`（指向的 commit） | `eb9c8508…` | **`453eddf2…`**（= main，没有悬空） |
| 公开树件数 | 2,230 | **2,239**（+9，**一件都没离开树**） |
| 内网 HEAD | `6afeebe`（卡 B9 补证） | **`65134c4`**（卡 D9 收口） |
| GeneQuant | `6ce7664e84e467c39d11bb4ec88209bdae6a7c92` | **同值，只核不推** |

树的提交口径一字不变：作者与提交者均为 `深情代码大师 <2994718175@qq.com>`，
message `GeneBench v1.0.16 release`，**body 为空**，提交数**永远只有 1**。

#### 本轮新进树的 9 件（**逐件核过它们真在树里、非空、被 git 跟踪**）

| 文件 | 字节 | 谁加的 |
| --- | ---: | --- |
| `runner/placement.py` | 18,709 | 卡 A9（单机形态的本地落位：exec 树 + bundle） |
| `runner/placement_dual.py` | 2,232 | 卡 A9（双机默认值，**单机分支不 import 它**） |
| `ops/test_A9.py` | 39,229 | 卡 A9（含「单机路径上 `/data` 字面量零次」那道门） |
| `ops/test_single_machine.py` | 40,477 | 卡 B9（裁定 ③ 那道门，外部干净 clone 上也跑得起来） |
| `ops/tickets_inbox/Zfin.md` | 19,432 | 卡 Zfin（交付终核，上一轮推完之后才提交） |
| `ops/tickets_inbox/A9-single.md.merged` | 4,397 | 卡 D9 归档 |
| `ops/tickets_inbox/B9-single.md.merged` | 11,727 | 卡 D9 归档 |
| `ops/tickets_inbox/C9-single.md.merged` | 5,822 | 卡 D9 归档 |
| `ops/tickets_inbox/D9.md` | 6,045 | 卡 D9 |

**内容变了的 10 件**：`README.md`、`docs/OPERATOR_MANUAL.md`（卡 C9）、
`ops/gateway_lock.py`、`ops/run_joblist.py`、`runner/c41/runner_core.py`（卡 A9）、
`ops/HANDOFF.md`、`ops/reports/known_limits_v1.md`、`ops/tickets.md`、
`ops/reports/push_result.md`、`RELEASE_MANIFEST.json`（卡 C9 + 卡 D9）。

#### 推之前在打好的树上扫了两遍，逐条人工判

**① `scratch/P/scan_mentions.py`**（2,239 个文件全扫）：

* **署名形态 1 条** —— `ops/reports/release_scan_claude_mentions.md:17`，那是**这份扫描报告
  自己的规则表**。它是**被扫描器命中的规则原文**，不是一条真的署名，**自指**，前几轮同值。
* **事实性提及 470 条**（上一轮 465）—— 逐类：harness 目录/ID `claude-code` **178**、
  供应商名（技术语境）**110**、`Claude`（技术语境）**109**、出向白名单/实测域名 **39**
  （红线 5 要求白名单**写出来**，删掉才是错）、harness 名 **25**、wire 形状 **8**、模型 id **1**。
  **一条真错都没有。** 落在**本轮新进树那 9 件**上的：署名 **0**、事实 **0**。

**② `scratch/W/w_scan_stale.py`**（只扫 `.md`）：**(a) 11 / (b) 285 / (c) 37**。
与上一轮（卡 Y）的 **(a) 11 / (b) 280 / (c) 37** 相比：

* **(a) 一条没动** —— 全是上游仓库的 commit sha 与 npm shasum，那是**钉住的版本**，不是过期口径。
* **(b) +5**，其中**本轮新写的正文只贡献 2 条**（`ops/tickets.md:5967` 与
  `ops/tickets_inbox/D9.md:19`，命中的都是「当场红」三个字 —— 在讲 `ops/test_wrapup.py`
  那条判据的**判别力**，与上一轮那 5 条同类，不是过期口径）。其余落在上一轮推完之后
  才进树的 `ops/tickets_inbox/Zfin.md` 与卡 C9 改的两份文档上，**逐条看过，没有一条在对外说假话**：
  命中的要么是表头、要么是签字包里的只读归档副本、要么是正文自己就写着
  「留这一句是给读过旧版的人看见它去哪了」的那种显式回溯。
* **(c) 一条没动** —— 仍是 37 条，全部是表头、归档副本，或 `它挡什么` 这种无关语义。

**逐条判的口径**：按「这句话是不是在对外说假话」判，**不按子串计数判**；
按 markdown 的**标题包含语义取整条标题链**判有没有标时点。

#### 推之后匿名回核（**没有 PATCH**，带重试，第 1 次就成功）

`GET /repos/Decilix-Intelligence/GeneBench/releases/387775425` **HTTP 200，不带 token**：

* `id = 387775425`、`tag_name = 'v1.0.16'`、**`target_commitish = 'main'`（字符串，没有悬空）**、
  `draft = False`、`prerelease = False`、`published_at = '2026-09-13T02:58:37Z'`（**没动**）。
* `assets = 3 件`，`state` 全部 `uploaded`，**钉的那五个字段一个都没变**：

| asset id | 名字 | size | state | digest |
| ---: | --- | ---: | --- | --- |
| 560455532 | `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `uploaded` | `sha256:edc5ea7c…9ef06` |
| 560453545 | `genebench_public_provider_v1.tar.gz` | 782,100,276 | `uploaded` | `sha256:33083ff2…c18e9` |
| 561398049 | `genebench_public_runtime_v1.tar.gz` | 42,046,516 | `uploaded` | `sha256:49e9b250…0963f` |

`created_at` 从 `2026-09-14T05:50:05Z` 变成 `2026-09-14T11:57:39Z` —— **与前四轮同样**，
那是 tag 移到新 commit 之后 GitHub 自己重盖的时间戳；
`tag_name` / `id` / `published_at` 都没动，**不是我们改的**，**本轮没有发过任何 PATCH**。

#### 树的内容回核（**匿名 HTTPS clone 回来逐项比**）

不是只看 `ls-remote` 的那一行 sha：本轮真把公开树**匿名 clone 回来**
（落 `$GB` 之外，`/home/ljn/genebench_scratch/D9_verify/`）比对。

* `HEAD = 453eddf2…`、**件数 2,239**；
* `git ls-files` 与本地打好的那棵树 **逐行相同**（`diff` 无输出）；
* 抽 6 件逐件 `sha256` 比对（`runner/placement.py`、`ops/test_single_machine.py`、
  `ops/HANDOFF.md`、`README.md`、`RELEASE_MANIFEST.json`、`ops/tickets_inbox/D9.md`）—— **全部 SAME**。

#### 定向测试（推之前）

| 组 | 结果 |
| --- | --- |
| 卡 A9 / B9 的新门 + `joblist` / `push_guard` / `c41` / `y2` / `d2` / `inject` | 276 passed / 6 skipped / 3 xfailed |
| 文档四件套 + `test_d` | 453 passed / 5 skipped（`test_d` 那条**转绿**，见下） |
| 发布件 / 打包 / 收尾 | 209 passed / **1 failed**（= N-866，未改动 HEAD 上已红） |
| `ops/test_Y.py` 喂真 3.12 | **32 passed**（无 skip） |
| 红线 3 / 红线 5（走 `$GB` 全树，3 分 41 秒） | 3 passed |
| `ops/mk_release_manifest.py --check` | **rc=0**，`releasable=true`，发布件 58 / 缺件 0 / 未闭合 blocker 0 |
| `ops/freeze_v10.py --check-all` | **rc=0**，三条轴与冻结清单一致 |

#### 本轮的一条红是判据过宽（`ops/test_d.py` 那条署名形态门）

`ops/test_d.py::test_本卡写的文件里没有署名形态[push_result.md]` **此前在内网树上恒红**，
命中的是**这份文件**里的三处。**那三处本来就不是署名** —— 它们是在陈述
「那次提交的 body 里没有署名 trailer」这个**技术事实**，以及引用扫描器自己的规则表。
红的原因是那道门的 `_SIG` 用的是**裸子串**，而同一个项目里
`scratch/P/scan_mentions.py` 用的是**带主语**的模式（署名行后面必须真的跟着一个助手名字）——
**后者才是对的口径**，它对这三处一条都不命中。

`ops/test_d.py` 不在卡 D9 的可改路径，能动的只有**措辞**：三处都改成**不嵌那两个字面量**的写法，
**技术事实一个字没丢**（裁定 ⑫ 的原话就是「署名形态一律删，**技术事实保留**」）。
实测由 `1 failed / 16 passed / 1 skipped` 转 **17 passed / 1 skipped**。
**所以这份文件里从此不再把那两个字面量写出来** —— 写回去会让那道门重新红。
门仍然过宽这件事记成 **N-865**，归下一张能改 `ops/test_d.py` 的卡。

#### 推完之后公开树落后内网 HEAD 一个文件（**预期内**）

本节（`ops/reports/push_result.md` §8.10）按 **N-743** 是**推完才写、推完才提交**的，
所以它不在刚推上去的那棵树里 —— 与前六轮完全一样。
下一次重打树时它会跟着进去，而那时**这一节的标题已经标了时点**（「第十轮…（卡 D9，2026-09-14）」），
`w_scan_stale.py` 的 (a) 类按**整条标题链**判，不会把它算成未标时点的终值。

#### 本轮**没有**做的事（写出来，免得下一张卡去找）

* **没有 PATCH Release** —— `target_commitish` 本来就是字符串 `main`，force-push 之后不会悬空。
* **没有碰 GeneQuant** —— 推前推后两次 `ls-remote` 都是 `6ce7664e…`，本地那棵树也没配过 push。
* **没有重算 τ / ε**，没有动三条版本轴，没有重打包、没有传附件、没有新建 Release。
* **没有修 README / 手册** —— 它们不在卡 D9 的可改路径。于是 **N-848 仍开着**：
  `runner/placement.py` 随树发了，而 README §2.4 ③④ 仍然教人跑两个 `push_*_to_f02.sh`。
  本卡把单机形态的照抄命令补进了**随树发的** `ops/HANDOFF.md` §19.10，
  但外部单机用户照 README 敲，撞的还是 N-840 那条 `rc=127`。**这是下一轮最该先修的两条之一**
  （另一条是 N-857 —— 它一旦随下一次 `ops/push_exec_to_f02.sh` 推上执行面，**双机生产也会断**）。


### 8.11 第十一轮重打与推送（卡 I10，2026-09-14）：本轮终值

本轮四张卡：**Efin**（交付终核，只读）、**F10**（五条代码缺陷一次修完 `b7b5cad`）、
**H10**（文档那批全改 `1fcfeb2` / `16300d4` / `fe3975f`）、**G10**（两道新门 `5bc9533`）、
**I10**（本卡：并表、重跑门、PATCH Release 正文、重出清单、重打树、两遍扫描、推、回核）。
本卡的两次提交：`f94de2e`（收口）与 `ce046c6`（两遍扫描逐条判时量到的一条真错）。

#### 本轮终值（内网记，按 N-743 不进树）

**本轮推了两次。** 第一次在 `ce046c6` 之后，第二次在 `c3ef087` 之后 —— 因为
第一次的顺序错了：**先重出 `RELEASE_MANIFEST.json`、后改的 `ops/HANDOFF.md` 标题**，
于是推上去那棵树里清单记的 `HANDOFF.md` 内容哈希与同一棵树里的 `HANDOFF.md` 对不上
（`--check` 仍退 0，但会报「内容已变、判据未变」）。外部用户在干净 clone 上第一件事
就可能是跑那条 `--check`，不该让他看见一棵自己跟自己对不上的树。
**下表是第一次推的终值**；本轮**最终**终值写在本节末尾的「补推一次」一段 ——
那一段按 **N-743** 是推完才写的，**因此不在这棵树里**（与前几轮同例）。

| 项 | 值 |
| --- | --- |
| 公开树 `refs/heads/main` | `1950ac5dfbf8c64b755d36580a6cdba83c19b55c` |
| annotated tag 对象 `v1.0.16` | `5a66b21466d33c2c44610d5bc6d78dfee56cee84` |
| `refs/tags/v1.0.16^{}` | `1950ac5dfbf8c64b755d36580a6cdba83c19b55c`（**== main，不悬空**） |
| 树里的文件数 / 提交数 | 2,247 件 / 1 个提交（孤儿树，每轮重打） |
| 推前 main | `453eddf2e50eb0ff1f8a400429518456cc56b683`（= 上一轮 v1.0.16） |
| GeneQuant | `6ce7664e84e467c39d11bb4ec88209bdae6a7c92`，**推前推后同值、没碰** |
| Release id | `387775425`，`tag_name=v1.0.16`，`target_commitish` 是字符串 `"main"`，`draft=false` / `prerelease=false` |
| Release 正文 | **本轮换过**（裁定 ③）：3,652 B → **4,934 B**，sha256 `3fed6a9e5f1a9f107a6847b113c8bc272296377e4f4797c684801a1e20f0ea8a` |
| 三件附件 | 三件 `state=uploaded`，`size` 与 `digest` **五个字段一个都没变**（逐件匿名核过） |

**`target_commitish` 本轮没有 PATCH** —— 它本来就是字符串 `main`，force-push 之后不会悬空
（任务书明写「不需要也不许再手工 PATCH」）。**本轮唯一 PATCH 的是 `body`。**

#### Release 正文 PATCH（用户裁定 ③）

正文取自 `ops/release/release_body_v1.0.16.md`（随树发）。改前先自检：
工具署名字样 **0 命中**、N-743 的三类终值（main sha / tag 对象 / 件数）**0 命中**；
三条 sha256 与三个字节数**逐字来自 `ops/release/attachments.json`**，卡 H10 与本卡都没有自己算过一个数。
PATCH 之后**匿名**回读**逐字节相同**，并逐项核过 `id` / `tag_name` / `target_commitish` /
`draft` / `prerelease` 与三件 asset 的五个字段**一个都没变**。
正文给了**两种**校验命令（Linux `sha256sum -c`、macOS `shasum -a 256 -c`）外加一个两边通用的
`sumc()` 函数 —— **本卡在 f02 上照抄跑了一遍，它真的把一件坏下载抓住了**（见下）。

#### 本轮新进树的 6 件（**逐件核过它们真在树里**）

`ops/tickets_inbox/I10.md`、`ops/tickets_inbox/Efin-fresh.md.merged`、
以及三个改名件 `F10-fresh.md.merged` / `G10-fresh.md.merged` / `H10-fresh.md.merged`
（旧名 `Efin.md` / `F10.md` / `G10.md` / `H10.md` 在树里**一个不留**，已核）、
`ops/release/release_body_v1.0.16.md`（卡 H10 提交、本轮第一次随树发）。
另有四份改动件：`ops/tickets.md`、`ops/reports/known_limits_v1.md`、`ops/HANDOFF.md`、`RELEASE_MANIFEST.json`。

#### 推之前在打好的树上扫了两遍，逐条人工判

* `scan_mentions.py`：2,247 个文件，**署名形态 1 条 / 技术事实 473 条**。
  那 1 条是 `ops/reports/release_scan_claude_mentions.md:17` —— **扫描器自己的规则表**，
  既定口径保留（`ops/HANDOFF.md` 上一轮已记同一条）。**本卡新写的段落 0 命中**（逐行核过）。
* `w_scan_stale.py`：(a) **11** / (b) **289** / (c) **38**。
  (a) 11 条与上一轮**逐条同值**，全是**钉住的第三方标识**（上游 commit、npm shasum、因子表达式），
  不是会随重打树失效的终值。落在**本卡新写段落**里的只有 **2 条**，都是扫描器按
  「当场红」这个关键词命中的**真陈述**（一条是 N-866 那张票据行、一条是本卡收件箱里
  描述两条反证测试的句子），判为**不是假话**。
* **量到一条真错，回头改完才重打的树**：`ops/HANDOFF.md` §19.10.4 的**标题本身**
  写着「这条路今天还走不到表 —— 四条拦路的，一条都还没修」，而那四条本轮已经全修完。
  上一次只在标题**下面**加了过期抬头 —— 按「markdown 的标题包含语义、取整条标题链判时点」
  这条判法，**标题自己仍然在对外说假话**。按 N-743 的口径处理（**不改值、只加显式时点**）：
  标题加前缀「【截至 2026-09-13 的状态，已过期 —— 改看 §19.11】」，正文一个字没动。
  改完**重新打树**再推（`ce046c6`）。**两个扫描器都没有把这一条报出来** —— 它是人工判出来的。

#### 单机门（用户裁定 ③ 那道门）这一轮**走到了第七步**

落点 `/home/ljn/gb_single2`（f02，`$GB` 之外，**不复用卡 B9 的那棵**），
三件附件**重新从 Release 匿名下载**，基座与 harness **现构新 tag**，
既有 `gb-base:bookworm-r1` / `gb-cx-u:r1` 的 image id 跑前跑后逐字相同。
七步逐步结果与照抄命令写在**随树发的** `ops/HANDOFF.md` §19.11，这里只记两件：

* **第二步抓住了一次真实的坏下载**：`genebench_public_gold_subset_v1.tar.gz` 第一次下成 **92 字节**
  （GitHub 侧错误响应），`curl` 却退 0 —— Release 正文与 README §2.1a 那句
  「三行都要 OK 再解包」当场把它报出来。已登记 **N-887**（建议给那三条 `curl` 加 `--fail --retry 3`）。
* **第七步出了表**：`table_main.csv` **24 列**（5 身份列 + 19 指标列），表头与 README §2.4 逐字相同。
  **但读数全 0**，两条原因都在机器上、都要 root：**N-858**（容器打不到宿主网关，实测仍不通）
  与本卡当场量到的 **N-890**（f02 上自定义 docker 网络一律出不了网 —— 宿主直连与默认 bridge 都是
  `401`，三个自定义网段全部 30 秒超时）。因此两臂各 30 次模型调用**全部是 `deny`**，
  `llm_log` 里 `decision=="allow"` **0 条** —— **本轮没有真正打到过模型 API 一次**。

#### 定向测试（推之前）与两条红

`ops/test_e` / `test_d` / `test_d2` / `test_6rt` / `test_readme` / `test_docs_consistency` /
`test_operator_manual` / `test_A9` / `test_single_machine` 合 **572 passed / 6 skipped**；
加上 `test_wrapup` / `test_Y` / `test_exec_tree_fresh` / `test_F10` 那一批是
**640 passed / 2 failed / 26 skipped**。两条红**都不在卡 I10 的可改路径内**：

* `ops/test_wrapup.py::test_八个收件箱都改名merged了_原名一个不留` —— **N-866**，
  卡 D9 已判**刻意不修**（`W2.md` 改名会让三份随树发的文档按路径引到不存在的文件）。**不是本轮引入的。**
* `ops/test_Y.py::test_the_readme_shortest_path_runs_on_the_public_channel` —— **N-882**，
  **是本轮引入的**（卡 H10 把 README §2.4 拆成三个代码块，而 `_readme_block` 只取第一个）。
  卡 F10、卡 G10、本卡**三次报出**，至今没有一张卡有权改 `ops/test_Y.py`。
  **判据本身在今天的 README 上是成立的** —— 本卡实测三个块里共 5 条 `run_joblist`，
  **每一条都带 `--channel public`**；红的只是取块那一步。**必须派一张能改它的卡**，修法照抄
  `ops/test_readme.py::fenced_blocks()`，**不许放宽判据**。

#### 本轮**没有**做的事（写出来，免得下一张卡去找）

* **没有重打包、没有传附件、没有新建 Release、没有改 tag 名**；三件附件一个字节没动。
* **没有 PATCH `target_commitish`**（已是字符串 `main`）。
* **没有碰 GeneQuant**（推前推后 `ls-remote` 同值）。
* **没有重算 τ / ε**，三条版本轴 `v1.0.16` / `r1.0.23` / `p1.0.0` 一个值没改。
* **没有改 README / 手册 / 任何测试文件** —— 都不在卡 I10 的可改路径。
* **没有动别人的未提交改动**（`ops/reports/ambiguity_impact_2.2b.md`、`validator_parity.*`、
  `ops/specs/operator_semantics_conflicts.md`、`paper/`）—— 只 `git add` 了本卡的显式路径。
