# 卡 Vfin 收件箱（2026-09-13）——外部 clone 终核（只读卡）

本卡只读：除本文件外没有改动任何文件，没有推树、没有碰 Release、没有碰 f02。
全部实测在全新 `git clone --depth 1`（SSH）的外部落点上做：
`/home/ljn/genebench_scratch/Vfin/gb`（`$GB`）+ `$GB/repo`（clone）+ `$GB/env`（README §1.5 那条
`python3.12 -m venv` 的原样产物）。证据在 `/data/shared/genebench/scratch/Vfin/`。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| N-825 | **README「§2. 快速开始」的 §2.1 代码块里没有建 venv 这一步，而 §1.5 的建 venv 那一行又用了只在 §2.1 才定义的 `$GB`——两个块互相依赖，哪一边先敲都会失败** | **待修（major）** | 两种读法各实测一次（`scratch/Vfin/readme_order.txt`）：① 按文档顺序先敲 §1.5（README:188-191），此时 `$GB` 未定义，`$GB/env` 展开成 `/env` → `Error: [Errno 13] Permission denied: '/env'`；② 直接从 §2.1 逐字敲（README:222-228），走到第 6 行 `$PY ops/selfcheck_public.py`（README:225）→ `bash: …/env/bin/python: No such file or directory`，`ops/guard_modes.py --harden` 同样。§2.1 只在 `PY=` 那一行的**注释**里写了「venv **必须**建在 `$GB/env`（§1.5）」，没有给命令。**不是死路**（注释指了 §1.5，回去补一句就能往下走），但这是外部用户复制粘贴的**第一个块**，且上一轮的卡 U 与本轮任务书都把这条命令记成「README §2.1 那条」——说明它确实容易被读成 §2.1 自带。改法（任选其一，都只动 README）：(a) 把 `/opt/homebrew/bin/python3.12 -m venv $GB/env` 与那条 `pip install` 两行**插进 §2.1 的块**，放在 `mkdir -p $GB` 之后、`$PY …` 之前；(b) 在 §2.1 块的 `PY=` 行下面加一行显式的 `# ← 先照 §1.5 把 venv 建出来，否则下面两条 $PY 找不到解释器`。 |
| N-826 | **`ops/test_d.py` 把它要检查的文件全部写死在发布方内网路径 `/data/shared/genebench/repo` 下，而且是在模块级读的——在任何没有这个路径的机器上（= 所有外部用户）pytest 在 collection 期就崩，整场中断** | **待修（major，不挡本版验收）** | `ops/test_d.py:20` `REPO = Path("/data/shared/genebench/repo")`，`:21-25` 的 `README`/`ATTACH`/`MANIFEST`/`SCAN`/`PUSH` 全从它派生，`:34` `RD = README.read_text(...)` 是**模块级**调用。实测（`scratch/Vfin/macsim2.txt`：另起一棵全新 clone，只把那一行换成一个不存在的路径，其余一个字节没动）：`pytest ops/test_d.py` → `FileNotFoundError: … /README.md` + `Interrupted: 1 error during collection`；`pytest ops/` → 该文件与另外几处一起 `Interrupted: N errors during collection`，**整场中断，不是一条红**。连带后果：本卡在 f01 上跑十二个测试文件时，`ops/test_d.py` 那些断言读的其实是**内网仓库**的 README/清单/报告，**不是**我克隆下来的那棵树——也就是说它对「克隆树对不对」这件事**没有判别力**。改法：`REPO` 改成从测试文件自身位置推导（`Path(__file__).resolve().parents[1]`，和 `conftest.py:26` 的 `_REPO_ROOT` 同一套口径），`PKG_DIR` 改成从 `GENEBENCH_ROOT` 推导；模块级的 `read_text()` 挪进 fixture 或加存在性 skip 保护。 |
| N-827 | 文档给的六个包环境里 `pytest ops/` 有 5 处 collection error（缺 `jsonschema` / `httpx`），整场中断 | **登记不修** | 在**未改动**的克隆树上实测（`scratch/Vfin/collect.txt`）：`ops/test_artifact_schema.py` 与 `ops/test_genetask.py` → `ModuleNotFoundError: No module named 'jsonschema'`；`ops/test_gateway.py` / `ops/test_gateway_fields.py` / `ops/test_sim_endpoints.py` → `starlette.testclient` 要 `httpx`。两个包都不在 README §1.5 钉的六个包里。**不挡**：文档从不叫外部用户跑 `pytest ops/`，只点名跑单个文件（手册 §3.4 的 `test_harness_contract.py`、§4.2 的 `test_p2_contract.py` 等），那些单文件跑法不受影响。登记在这里是因为「跑一下全量测试」是外部用户很自然的动作，而他看到的是整场中断而不是几条红。 |

## 已登记、本卡只是复核到仍然存在的

* **N-793**（`RELEASE_MANIFEST.json` 的 `blockers[...].closes_when` 仍引用已被 N-714 整棵删除的
  `release/_staging_unpublished/`，本卡实测在 `RELEASE_MANIFEST.json:274`）——已在 `known_limits_v1.md`
  登记，本卡不重复取号。`ops/mk_release_manifest.py::PART_OVERRIDES` 用同一个路径**当字典键**是
  刻意的（源码 `:458-462` 写了理由：键用存档件的 `path`，对外正文由该表改写成「已发布」），
  那一处**不是**问题。
* 卡 U 留下的那条观察（`ops/guard_modes.roots()` 返回的 `$REPO` 在 `$GB` 之下，仓库树被走两遍、
  同一条违例报两行）——本卡在外部落点上同样看到（`$GB/repo` 在 `$GB` 之下）。仍然不挡任何事，
  仍然没开票，留给下一轮判。
