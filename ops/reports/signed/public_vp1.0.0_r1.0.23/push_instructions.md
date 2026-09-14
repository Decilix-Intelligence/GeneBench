# 把两棵树推上去（**这一步由仓库所有者执行**）

**施工方没有推，也没有给本仓库配 remote。** `git remote -v` 现在是空的，那是有意的：
`/data/shared/genebench/repo` 是一棵内网工作树，给它配一个外网 remote 等于让任何一次
手滑的 `git push` 把答案面推出去。所以这份文件给的是**命令与核对清单**，不是一次已完成的操作。

| | 地址 |
| --- | --- |
| 基准本体 | `https://github.com/Decilix-Intelligence/GeneBench.git` |
| 协议工件 | `https://github.com/Decilix-Intelligence/GeneQuant.git` |

两棵备好的树在 **`$GB/release/trees/`**（`genebench/` 与 `genequant/`），
各自已经是一个**独立的 git 仓库**（`git init` + 一次提交），可以直接 `git push`。

---

## 0. 推之前要再确认的三件事

### ① 两个远端**已经有内容了**，你的推送不是空仓库上的第一推

2026-09-11 现查（`git ls-remote`，从 f01）：

| 仓库 | `refs/heads/main` |
| --- | --- |
| GeneBench | `55ead48588dd1ddfff7d62e9ce6bf94401424124` |
| GeneQuant | `6eadb004104aa4564e60db70dff40445c836b817` |

这两个 commit **与本地这两棵树没有共同祖先**（本地树是新 `git init` 的）。
于是普通 `git push` 会被拒（`non-fast-forward` / `unrelated histories`）。**三条路，选一条**：

* **A（推荐，远端那一次只是初始化用的空壳）**：`git push --force origin main:main`。
  **先看一眼远端那一次提交里有什么**（`git ls-remote` 只给 sha，看内容要
  `git clone --depth 1 <url> /tmp/peek && ls -la /tmp/peek`）—— 如果里面只有一个
  GitHub 生成的 README/LICENSE，force 掉没有损失；**如果里面有别人的东西，别 force。**
* **B（想留住远端那一次）**：`git fetch origin && git rebase --onto origin/main --root`
  或 `git merge --allow-unrelated-histories origin/main`，解冲突后再推。
* **C**：推到一个新分支 `git push origin main:release-v1`，在网页上开 PR，人看过再合。

### ② 这两棵树里**没有**答案面 —— 但请自己再扫一遍

推的是数据集/基准，一次泄漏不可撤销（GitHub 上删掉的 commit 在一段时间内仍可访问）。
本卡对两棵树各跑过一次 `runner/f02/answer_plane_guard` 的扫描，**各 0 命中**，
输出留在 `$GB/release/trees/scan_genebench.txt` 与 `scan_genequant.txt`。
推之前**自己再跑一遍**（不到一分钟）：

```sh
GB=/data/shared/genebench; PY=$GB/env/bin/python
cd $GB/repo && PYTHONDONTWRITEBYTECODE=1 $PY - <<'PY'
import sys; sys.path.insert(0, "/data/shared/genebench/repo")
from runner.f02 import answer_plane_guard as G
for t in ("genebench", "genequant"):
    root = f"/data/shared/genebench/release/trees/{t}"
    hits = G.scan(root)
    print(t, len(hits), "命中", hits[:5])
PY
```

**剔除的是这些**（`release/trees/genebench/EXCLUDED.txt` 逐件列出）：
`reference/`、`scorer/`、`tasks/`、`genetask/templates/`、`genetask/params/`、`paper/` 六棵，
外加按文件名剔的六种（`solve.py` / `scorer.yaml` / `canary.json` / `slots.json` /
`equivalence.md` / `_ledger.jsonl`）。剔除口径与 `ops/push_bundle_to_f02.sh` 的守门同源。

> **剔除之后 `snapshots/` 与 `gold_factors` 也不在树里** —— 那是数据，走公开数据包
> （形态 A / B，见 README §2.1），不走 git。

### ③ 许可与署名：`DATA_LICENSE` 还是 `pending_license_text`

代码按 Apache-2.0 发（`LICENSE` 已是全文），这一条没有悬念。
**数据不是。** `DATA_LICENSE` 的状态仍是 `pending_license_text`，
`RELEASE_MANIFEST.json` 的 `releasable` 因此仍然是 `false`。

推源码**不等于**发数据包：树里没有任何行情数据。但 README 里对数据获取的描述会被人照着做，
所以推之前确认你接受「代码公开 / 数据包暂不公开」这个状态。

还有两处**故意留着**的占位符，它们不挡推送，但会被人照抄：

* `LICENSE` 附录的 `Copyright <待用户填>` 版权行；
* `CITATION.cff`（本体与 `genequant/` 各一份）的 `authors`。

填法在 `LICENSE` §A。**没有代填任何一个** —— 编一个版权人比留一个占位符坏得多。

### ④ **这棵树按今天的剔除口径，跑不了结算与出集** —— 推之前必须先裁这一条

剔除答案面（`reference/` `scorer/` `genetask/templates` `genetask/params` `tasks/`）是
**零命中判据自己要求的**：`runner/f02/answer_plane_guard` 见到名为 `reference` 的目录就整棵删，
见到 `solve.py` / `scorer.yaml` 就删。所以「零命中」与「树里有参考解」不可能同时成立。

后果是具体的，不是理论上的 —— 树里**还有 65 个模块 import 那两棵**：

| 断掉的链路 | 入口 | 缺什么 |
| --- | --- | --- |
| **结算** | `ops/score_runs.py` | `from scorer import score_run, report` |
| **出表** | `ops/mk_tables.py` | 同上 |
| **出集 / 建题** | `genetask/packager.py`、`genetask/render.py`、`genetask/schema.py` | `reference/`、`genetask/templates/` 的 329 个题面文件 |
| **oracle / 控制组 / 适配赛道** | `ops/run_oracles.py`、`ops/run_controls.py`、`ops/pack_adaptation.py` | `reference/` |

**能用的仍然有**：网关（`gateway/`）、注入器与两臂运行器（`runner/`）、13 条 harness 与接入契约
（`harnesses/` `integrations/`）、协议工件（`genequant/`）、全部文档与数据卡、
114 个测试文件里不依赖答案面的那些。也就是说，这棵树今天是
**「把 agent 跑起来、拿到 artifact」的那一半**，不是「判它得几分」的那一半。

**这是一个需要你裁的取舍，施工方没有替你选**：

* **A（保持现状）**：公开仓库不含答案面 —— 与多数基准的做法一致（防污染：题面与参考解一旦进了
  训练语料，这个基准就废了）。代价是外部用户跑完之后**自己算不出分**，要么把 artifact 交回来判，
  要么等一个单独的评分服务/私有仓库。选这条**必须**在 README 首页写明，今天的 README 没写。
* **B（公开仓库也带答案面）**：外部用户闭环，但题面与参考解就在公网上了，
  而 `τ`/`ε` 的标定、`canary`、`memory_probe_answers` 的判别力会随之失效。
  选这条要**重打**这棵树（本卡这棵是剔过的），并且红线 2 的口径要由你改写。
* **C（拆两个仓库）**：`GeneBench` 公开这一半，`GeneBench-private`（或私有分支）放答案面，
  发布清单里写清两边的对应关系。工作量最大，但它是唯一同时满足「外部可用」与「防污染」的形态。

**在裁之前，推 A 是安全的**（推出去的东西不会变多），只是 README 会对不上。

---

## 1. 推送命令（逐条可粘贴）

```sh
GB=/data/shared/genebench

# ---- 基准本体 ----
cd $GB/release/trees/genebench
git log --oneline -1                 # 看清你要推的是哪一次
git remote add origin https://github.com/Decilix-Intelligence/GeneBench.git
git push -u origin main              # 被拒的话按 §0① 选 A / B / C

# ---- 协议工件 ----
cd $GB/release/trees/genequant
git log --oneline -1
git remote add origin https://github.com/Decilix-Intelligence/GeneQuant.git
git push -u origin main
```

`git push` 会要**凭据**（HTTPS 下是 GitHub 的 personal access token，作用域 `repo`）。
**施工方没有、也不该有这个凭据**；不要把它写进这棵树里的任何文件，
也不要写进 `~/.git-credentials` 以外的地方。

从 f01 推得通（2026-09-11 实测）：`https://github.com/` 回 **200**（6.8 s，走代理），
`git ls-remote` 两个仓库都能列出 refs。对照组 `…/ThisRepoDoesNotExist-zzz9` 回 **404** ——
所以那两个 200 是「仓库真的在」，不是「代理对什么都回 200」。

## 2. 推完之后要做的三件事

1. **回来重打一次公开数据包。** `_staging_unpublished/` 里那份 README 是旧文本
   （成包时地址还是占位符）。命令见 `ops/release/pack_public_provider.py`。
2. **`git clone` 一遍验收自己的包。** 按 README §2.1 从零走一遍 ——
   `ops/reports/rehearsal_v2.md` 是上一次从零演练的记录，照它的七步核。
3. **协议那棵的 pin 要对得上。** `genequant/MANIFEST.json` 的 sha256 被本体的
   `RELEASE_MANIFEST.json::genequant.manifest_sha256` 钉着，
   `ops/test_genequant_subtree.py` 两个方向都查。两棵树推的**必须是同一时刻的那一版** ——
   先推协议后改本体（或反过来）会让这条 pin 指向一个远端没有的版本。

## 3. 不要做的事

* **不要给 `$GB/repo` 配 remote。** 要推就在 `release/trees/` 那两棵里推。
* **不要 `git push --mirror` / `--tags --force`**（本地那两棵没有需要保留的标签）。
* **不要把 `$GB/repo` 的 `.git` 一并打包上传** —— 它的历史里有答案面。
  `release/trees/` 里那两棵是**新 init 的**，历史只有一次提交，这是有意的。
