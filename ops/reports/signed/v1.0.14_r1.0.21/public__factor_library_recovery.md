# W2-1：`factor_library/compiled/` 三件冻结件 —— 找到了，收进仓库，与 gold 对账通过

* 做于 2026-09-10，f01，仓库 `/data/shared/genebench/repo`
* 结论：**没有丢**。三件一直在数据湖里，`gold` 就是在这三份上算的。
  本卡把它们**逐字节钉进仓库**，`RELEASE_MANIFEST.json` 的 blocker
  `frozen_artifacts_missing` 由此闭合（缺件 3 → **0**）。

---

## 1. 「缺件」是怎么来的 —— 不是丢了，是从来没进过仓库

`snapshots/public/manifest.py::PUBLIC_FROZEN_ARTIFACTS` 声明的六件里，
有三件写的是 `factor_library/compiled/{qlib_native,qlib_panel,blocked}.jsonl`。
`ops/mk_release_manifest.py::build()` 是这样解析的：

```python
for rel in items:
    p = repo / rel          # ← 仓库相对
```

而这三份的**真实住处是数据湖**，`reference/factor_exec.py` 自己写得清清楚楚：

```python
FACTOR_LIB: Path = cfg.LAKE / "reference" / "factor_library" / "compiled"
LIB_FILES: tuple[str, ...] = ("qlib_native.jsonl", "qlib_panel.jsonl", "blocked.jsonl")
```

`cfg.LAKE = /home/ljn/projects/data/market_lake`。所以

    $LAKE/reference/factor_library/compiled/   ← gold 从这里读，一直都在（mtime 2026-08-05）
    $REPO/factor_library/compiled/             ← 清单按这里找，这棵子树根本不存在

**两处指的是同一批文件，只是一处用湖路径、一处用仓库路径。**
`ops/reports/public/release_forms.md` §5 写的「整个 `factor_library/` 目录都不存在」
是对的 —— 但它说的是仓库，不是说这三份数据不存在。

### 找过哪些地方（都记下来，免得下一个人再找一遍）

| 找法 | 结果 |
| --- | --- |
| `git log --all --diff-filter=D --name-only -- '*compiled*'` | 空 —— **从未被提交过，也就谈不上被删** |
| `git log --all --oneline --name-only -- '*factor_library*'` | 空 |
| `find $GB -name 'qlib_native*' -o -name 'qlib_panel*' -o -name 'blocked.jsonl'` | 空（`$GB` 下确实没有） |
| `find $GB -maxdepth 5 -name 'factor_library*'` | 空（`scratch/`、`staging/` 里也没有） |
| `ls $LAKE/reference/factor_library/compiled/` | **三件齐全** |

所以**不需要用 2.1b 的编译器重生成** —— 重生成只会引入「重生成的和当初的是不是同一份」
这个新问题，而现在这三份就是当初那一份。

---

## 2. 收进仓库

`snapshots/public/recover_factor_library.py --write`：从湖**只读**拷进
`$REPO/factor_library/compiled/`，落点逐字等于清单声明的那三条相对路径
（于是 `mk_release_manifest.py` 与 `ops/release/pack_public_provider.py` 都不用改一行）。

| 文件 | 行数 | 字节 | sha256（湖与仓库**逐字节相同**） |
| --- | ---: | ---: | --- |
| `factor_library/compiled/qlib_native.jsonl` | 644 | 552,199 | `f0ea97c6bd5b1a8c41736b31a68756d1543d9e11c26ee3d1f8cf42727b2a4698` |
| `factor_library/compiled/qlib_panel.jsonl` | 148 | 165,036 | `cbf4ba183edfaabb30211decb57297c391b888ff1e6fc5fd77cc62720f882384` |
| `factor_library/compiled/blocked.jsonl` | 24 | 27,539 | `955f7a66c4e7a63d727fce9cb3b6fa6f22ca1b725d7db4e864bbbe76cb2bb5cc` |

六件的 sha256 一并登记进 `snapshots/public/manifest.py::PUBLIC_FROZEN_ARTIFACT_SHA256`。

**为什么放仓库而不是快照**：另外三件（`reference/factorlib_pinned/*.py`）本来就在仓库里，
而形态 B（用户自建）的第一步是「拿一份完整仓库」—— 定义面跟着仓库走，用户才可能自足。
这三份合计 745 KB，不触红线 6 的「大产物不进 git」。

---

## 3. 与 gold 对账：三项，逐条复现，**不是「文件在不在」**

对账要回答的不是「有没有文件」，而是「**这三份还是不是当初算出 gold 的那三份**」。
下面三项全部从**仓库副本**（不是湖）重新推导，与 2026-09-01 落盘的产物比。

### ① 后端分布（`reference/factor_exec.load_records()` 自带的硬核对）

    {'qlib_expression': 644, 'qlib_panel_loader': 66, 'qlib_kunquant_loader': 82, '<blocked>': 24}

与 `factor_exec.EXPECTED_BACKENDS` + `EXPECTED_BLOCKED` **逐个相等**。
644 + 66 + 82 = **792 条可执行**，+ 24 blocked = 816 条记录。
（注意 `qlib_panel.jsonl` 是 **148** 行 = 66 + 82：两个 loader 后端同住一个文件，
按 `execution_backend` 字段分，不是按文件分 —— `factor_exec` 的模块 docstring 里写着这件事。）
对不上 `load_records()` 会**直接抛**，不会静默降级。

### ② 算子冲突名单：13 条 τ 排除 / 23 条 gold 存疑

`reference/operator_flags.py` 的 `gold_suspect()` / `tau_excluded()` 完全由编译记录决定
（前者看 KunQuant 源码里有没有 `ts_rank`，后者看记录的 `expression` 里有没有 `Ts_Rank`）。
用**仓库副本**重跑，与 2026-09-01 写进
`$SNAPSHOTS/v1/gold_factors/operator_convention_suspect.json` 的两个数组**逐条相同**：

| 集合 | 重新推导 | 快照里 | 一致 |
| --- | ---: | ---: | :---: |
| `gold_suspect`（S3 出题必须避开） | 23 | 23 | ✅ 逐条 |
| `tau_excluded`（移出 τ 样本） | **13** | **13** | ✅ 逐条 |

这一项是三项里最有力的：那份 sidecar 是 gold 的**标注面**，它能被这三份编译记录
一字不差地重放出来，就说明 gold 与这三份同源。

### ③ 互检报告 §10 的「141 因子 / 379,950 格」

拿上面推导出的 13 条去筛互检逐格明细
`$SNAPSHOTS/v1/crosscheck/rank_ic_cells_csi300.parquet`（431,843 行，剔 degenerate 后 414,856）：

| | 重新算 | `ops/reports/factor_crosscheck_2.1b.md` §10 | 一致 |
| --- | ---: | ---: | :---: |
| 参与因子 | **141** | 141 | ✅ |
| 格数 | **379,950** | 379,950 | ✅ |

三项 `diffs == []`。**没有一处需要凑。**

---

## 4. 改了什么

| 路径 | 改动 |
| --- | --- |
| `factor_library/compiled/*.jsonl` | **新增**（从湖逐字节拷入，3 件） |
| `snapshots/public/recover_factor_library.py` | **新增**：拷贝 + 三项对账，`--write` 才写 |
| `snapshots/public/manifest.py` | **追加** `PUBLIC_FROZEN_ARTIFACT_SHA256`（6 条）与 `FACTOR_LIB_UPSTREAM` |
| `RELEASE_MANIFEST.json` | 重跑生成：发布件 47 件、**缺件 0**、`frozen_artifacts_missing` → `satisfied: true` |
| `ops/test_W2.py` | 新增：钉住上面三项与「六件都在且 sha 与登记一致」 |

`releasable` 仍是 **false**，剩下三条 blocker 全是**要用户拍板的**，不是技术项：
`data_license_text`（baostock 书面许可原文未入库）、`no_clone_url`（仓库没有公开地址）、
`code_license_undecided`（代码许可未定）。**没有伪造任何一条。**

---

## 5. 复现

```bash
export GENEBENCH_ROOT=/data/shared/genebench
cd $GENEBENCH_ROOT/repo && ulimit -n 8192
PY=$GENEBENCH_ROOT/env/bin/python

$PY snapshots/public/recover_factor_library.py            # 只对账（仓库副本已在）
$PY snapshots/public/recover_factor_library.py --write    # 重新从湖拷一次再对账
$PY ops/mk_release_manifest.py                            # 重出发布清单
$PY -m pytest ops/test_W2.py ops/test_release_manifest.py -q
```
