# 公开运行物料：补了什么、落在哪、外部用户怎么落位（卡 B2，2026-09-13）

> 由来：用户在一台**干净 Mac** 上做外部验收（`VALIDATION_REPORT.md`，2026-09-13），
> 四项通过、端到端阻塞。三个真缺件里的 ②③ 归本卡：**公开题集夹具**与**标定物料**。
> 本卡只把缺的文件补进发布，**不重冻、不改三条轴的值、不推树、不碰已发的两个附件**。

## 0. 一句话结论

第三个 Release 附件 **`genebench_public_runtime_v1.tar.gz`**（42,046,516 B，
sha256 `49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f`）已打好，
落在 `$GB/release/public_v1/`，登记进 `ops/release/attachments.json`。
包里 533 个文件、84,755,038 字节（题集 506 件 / 73,467,699 B；标定 27 件 / 11,287,339 B），
另有包内三件 `runtime_SHA256SUMS` / `runtime_MANIFEST.json` / `runtime_README.md`。
干净 clone + 落位之后 `ops/freeze_v10.py --check-all` **三条根全绿**，
公开根回到 `3e5ab441a991c4115a6c0fb988715f583e22ee303f582f1302fd3197fb183538`，
**全程没有用过任何 `--write*`**。本轮**不上传**。

## 1. 缺件 ② 公开题集夹具 —— 实物是什么

计算器读的是 `$GENEBENCH_ROOT/reference/tasks/public/v1.0-smoke-public/`。
`ops/freeze_v10.build_channel_fixtures()` 只收**题面 `inputs[]` 声明过**的那些文件，
所以「18 道题 30 个输入文件」指的是 S4–S7 这 18 道带 `inputs[]` 的题
（s1/s2/s3/s8 的 `task.yaml` 是 `inputs: []`，因此不进公开根 —— 这也是为什么
把整棵题集树打进包里**不会**让公开根变）。

| | 实测 |
| --- | ---: |
| 带 `inputs[]` 的题 | **18**（s4×4、s5×4、s6×5、s7×5） |
| 夹具文件 | **30** |
| 夹具总字节 | **19,250,210** |
| 这 18 道题的 `task.yaml`（读 `inputs[]` 要它） | 18 件 / 43,710 B |
| 整棵公开题集树（34 道题 + `_ledger.jsonl`） | **506 件 / 73,467,699 B** |

逐件路径 / 字节 / sha256 落在包内 `runtime_MANIFEST.json` 的 `sha256` 段，
以及 `$GB/release/public_v1/runtime_SHA256SUMS`（533 行，`sha256sum -c` 可直接吃）。
现算与已冻 `channel_fixtures` **30/30 逐件相同**（`ops/release/pack_public_runtime.py`
的 `assert_fixtures_match_frozen()` 是打包时的硬门，不等就拒绝打包）。

## 2. 它为什么没进发布 —— 真正的那一处

**不是 `.gitignore`，不是 `EXCLUDED.txt`，也不是 `scratch/G2/mk_tree_g2.sh` 的剔除清单。**
三条都查过：

* `scratch/G2/mk_tree_g2.sh` 的剔除只有四类（私有通道数据 / 凭据 / 记忆探针钥匙 /
  `scratch` 与 run 目录）。`reference/tasks/` **一条都没命中**。
* `.gitignore` 里确有 `*.parquet` 的兜底，但它挡不到从来没进过仓库的路径。
* 内网仓库里**根本没有 `reference/tasks/` 这个目录**：
  `git ls-files reference/tasks` 返回空，`ls repo/reference/tasks` 是 `No such file`。

真正的那一处是**公开树的建法**：`mk_tree_g2.sh` 第 15 行

```sh
git archive HEAD | tar -x -C "$T"
```

公开题集是 `ops/mk_instances.py` **物化**出来的产物，按红线 6「大产物只落
`$GENEBENCH_ROOT`、不进 git」落在 `$GB/reference/tasks/public/…`，**在仓库之外**，
于是 `git archive HEAD` 的射程里没有它。同一条红线也解释了标定物料为什么不在树里。

**这不是漏配，是两条规矩在发布口径上撞了**：红线 6 说「大产物不进 git」，
而公开根的判据又要求外部能拿到这些字节。修法只能是**把它作为发布附件发**，
不是把它塞进 git（塞进去等于在公网仓库里挂 73 MB 二进制，且与红线 6 正面冲突）。

> **给重打树的那张卡**：`scratch/G2/mk_tree_g2.sh` 生成的 `EXCLUDED.txt` 现在
> 只说"树里本来就没有数据文件"，**没有说"题集与标定在第三个附件里"**。
> 重打树时要在 `EXCLUDED.txt` 里补这一句，否则下一个外部用户还是只能自己猜。

## 3. 落点判断：为什么是附件不是仓库

任务书给的门槛是「小（比如 < 20 MB）就进仓库」。实测两个数：

* 只算 30 个夹具文件：**19,250,210 B**（18.4 MiB）—— 卡在门槛线上；
* 外部用户真正需要的整棵题集树：**73,467,699 B**（70.1 MiB）—— 明显超门槛。

选**整棵树 + 附件**，理由三条（按份量排）：

1. **只发 30 个夹具，冻结根会绿，但题集还是跑不起来。**
   `ops/run_joblist.py`（出集）与 `ops/score_runs.py`（结算）都以
   `reference/tasks/public/v1.0-smoke-public/` 为**题集根**，`scorer/score_run.py:291-292`
   读每道题的 `task.yaml` 与 `taskspec.json`、`:328` 把 `task_dir/work` 当 gold 目录。
   只补夹具 = 公开根对上了、README 第 6 步照样起不来 —— 正是本轮要终结的那种
   「跑起来 ok，其实缺件」。下一个外部验收会在同一类问题上再撞一次，只是晚一步。
2. **19 MB 的 parquet 进 git 与仓库自己的纪律正面冲突**（`.gitignore` 明写
   「按扩展名兜底：任何层级的数据文件都不入库」），要 `git add -f` 才进得去，
   而且会永久留在公网仓库的历史里。
3. 门槛是按**该落位的那一堆**量的，那一堆是 70.1 MiB。

## 4. 缺件 ③ 标定物料 —— 在哪、是哪一份、有没有混私有

| 物件 | 实物路径 | 公开通道用哪一份 |
| --- | --- | --- |
| `calibration.json` | `$GB/snapshots/public_v1/calibration.json`（41,410 B） | **就是这一份**；`genebench_config.calibration_path()` 按通道取，public → `snapshots/public_v1/` |
| `calibration.sha256` | 同目录（83 B） | 随包发，落位后可自校 |
| `epsilon/` | `$GB/snapshots/public_v1/epsilon/`（23 件 / 11,245,846 B） | 同上，`cfg.epsilon_dir()` 按通道取 |

私有那一份在 `$GB/snapshots/v1/`，**本包一件都没带**（打包器的
`FORBIDDEN_SUBSTRINGS` 里有 `snapshots/v1/`，命中即拒绝打包）。

**逐字段核过，没有混入私有标定**：

* τ：公开 `0.9839810664562939` ≠ 私有 `0.9840059556217291` —— 两份是各自算的，
  不是把私有那份复制过来改了个名。
* 全文正则扫绝对路径，只出现 `snapshots/public_v1/…` 五处（`provider.dir`、
  `gold_factors`、`qlib_provider`、`crosscheck/rank_ic_cells_csi300.parquet`、
  `epsilon/ic_epsilon_dual.json`），**没有一处指向 `snapshots/v1/`**。
* `epsilon/build_info.json` 自己写着 `"channel": "public"`、
  `"produced_by": "ops/run_public_chain.py"`。
* oracle 产物**没有**被顺手带出去：包里只有 `calibration.json` / `calibration.sha256` /
  `epsilon/`；`gold_factors*/`、`crosscheck/`、`instruments_rebuild/`、`state/` 都没进。

**τ/ε 是阈值不是解**，所以它们不属于答案面 —— 这一点与题集实例不同，题集实例里
**确实带答案面**（见 §6）。

### 评分链路真的能加载（干净 clone 实测）

```
calibration_path = <CR>/snapshots/public_v1/calibration.json | exists = True
tau = 0.9839810664562939
epsilon.by_frequency 频率 = ['daily', 'monthly', 'weekly']
epsilon.ic_family 有没有 = True
epsilon_dir = <CR>/snapshots/public_v1/epsilon | exists = True
```

`scorer/l3.py` 读的是 `calibration.json.epsilon.by_frequency` 与
`.epsilon.ic_family`（`:833` / `:810`）—— **ε 的数值在 `calibration.json` 里**，
`epsilon/` 目录是它的**产地与证据**（三份实现 + 逐频率产物 + `MANIFEST.sha256` +
`build_info.json`）。两个都随包发：不发 `calibration.json` 算不出分，
不发 `epsilon/` 外部无从复核这条带是怎么来的。

## 5. `tables/manifest.json`：**显式 public/snapshot 下不需要它**

Mac 报告提到这个文件不存在但日历仍读得出。查清了，**不该发**：

`gateway/backends.py` 里它只出现在一处 ——

```python
def default_backend() -> str:
    ...
    if public:
        return "snapshot"
    return "snapshot" if SNAPSHOT_MANIFEST.exists() else "live"     # :115
```

它是**私有通道**「有没有快照物料」的自动切换开关（`SNAPSHOT_MANIFEST` 恒指
私有 `snapshots/v1/tables/`）。公开通道在它上面一行就**无条件返回 `snapshot`**，
根本走不到那一行；`GENEBENCH_GATEWAY_BACKEND=snapshot` 显式指定时更是直接返回。

干净 clone 实测（没有 `tables/manifest.json`）：

```
tables_dir = <CR>/snapshots/public_v1/tables
tables/manifest.json 存在？ False
public 通道 default_backend() = snapshot
```

**结论**：公开通道不需要 `tables/manifest.json`，两个已发附件不缺它。
这条写进数据卡（`ops/data_cards/public_runtime_v1.md` §4），免得下一个人再撞。

## 6. 这个包里有答案面 —— 是有意的

题集实例里带每道题的 `solution/`（参考解 + gold artifact）、`gold/`、`scorer.yaml`、
`tests_test_outputs.py`。**不带就算不出分**（`scorer/score_run.py:328` 把
`task_dir/work` 当 gold 目录）。这与 v1.0.16 公开树「带全部答案面」是同一条裁定
（N-627 走 B，见公开树 `EXCLUDED.txt`）：红线 2 在本版的口径是**容器边界** ——
答案面永不挂进 agent 容器。

打包器因此保留 `assert_dest_is_not_on_the_exec_plane()`（落点判据，不是口头承诺），
**不提供任何推送开关**，并且硬挡 `tasks/private/`、`snapshots/v1/`、
`memory_probe_answers/`、`runs_in/` 与凭据形态文件。

代价（题面与参考解在公网、有进训练语料的风险）是设计性限制，
已记在 `ops/reports/known_limits_v1.md`「G2（2026-09-12）」。

## 7. 外部用户要执行的确切命令

```sh
# ① 下载（第三个附件，上传后回填 download_url）
curl -fL -O <download_url>/genebench_public_runtime_v1.tar.gz

# ② 整包解开 + 逐件校验（533 行全 OK）
tar -xzf genebench_public_runtime_v1.tar.gz
(cd genebench_public_runtime_v1 && sha256sum -c runtime_SHA256SUMS)

# ③ 落位（一条命令；--strip-components=1 把包内顶层目录剥掉）
tar -xzf genebench_public_runtime_v1.tar.gz --strip-components=1 -C "$GENEBENCH_ROOT"

# ④ 该绿的两件事
cd "$GENEBENCH_ROOT/repo"
python3 ops/freeze_v10.py --check-all     # 三条轴全绿；公开根 = 3e5ab441…

# 评分链路自检。**不要**拿 `ops/score_runs.py --help` 当判据 —— argparse 在读任何
# 文件之前就退了，它证明不了标定在不在（包内 README 第一版写错过，已改）。
GENEBENCH_CHANNEL=public python3 -c \
  "import genebench_config as c; from scorer import l3; print(l3.load_calibration(c.calibration_path())['tau']['value'])"
```

落位之后两棵子树在：

```
$GENEBENCH_ROOT/reference/tasks/public/v1.0-smoke-public/   # 34 道题 + _ledger.jsonl
$GENEBENCH_ROOT/snapshots/public_v1/{calibration.json,calibration.sha256,epsilon/}
```

**不要**用 `--write-public` 把冻结检查"改绿" —— 那是重冻，会让已发的通行证全部作废。
对不上就先逐件比 `runtime_SHA256SUMS`：少一件、多一件、或者换行/权限被改过，
都会让 `channel_fixtures` 那一段变。

## 8. 判据实测（干净 clone，全程无 `--write*`）

在 f01 上建全新空目录 `$GB/scratch/B2/cleanroom`，`git clone` 内网仓库（HEAD
`efe17e81695fe57c71ef0906dc508bc7fc336ee5`，工作树 0 条改动，
`reference/tasks/public` **不存在**），然后：

| 步 | 结果 |
| --- | --- |
| ② 落位**前** `freeze_v10.py --check-all` | 退出码 **1**，公开根 `c5639e55…`，18 道题全列为差异 —— **逐字复现了 Mac 报告** |
| ③ `sha256sum -c runtime_SHA256SUMS` | 退出码 **0**，**533/533 OK** |
| ④ 落位 | 题集 34 个题目录（`find -maxdepth 1 -type d` 报 35 是带上了根自己）；标定 `calibration.json` / `calibration.sha256` / `epsilon/` |
| ⑤ 落位**后** `freeze_v10.py --check-all` | 退出码 **0**，**三条轴全部与冻结清单一致**；公开根 = `3e5ab441a991c4115a6c0fb988715f583e22ee303f582f1302fd3197fb183538` |
| ⑥ 评分链路 | `load_calibration()` 成功，τ / `by_frequency` / `ic_family` / `epsilon_dir` 全部就位 |

脚本与原始输出：`$GB/scratch/B2/cleanroom.sh`、`$GB/scratch/B2/cleanroom/dl/sums_check.log`。

## 9. 还挡着端到端的一件事（**不在本卡的可改路径里**）

⑥ 里顺手发现一个**真阻塞**，它不是缺件，是写死的路径：

```
ops/run_controls.py:53
PUBLIC_ANSWER_ROOT = Path("/data/shared/genebench/reference/tasks/public/v1.0-smoke-public")
```

`ops/score_runs.py:49` 正是 `from ops.run_controls import PUBLIC_ANSWER_ROOT as PUBLIC_REF_TASKS`。
而 `ops/run_joblist.py:79` 用的是 `cfg.GENEBENCH_ROOT / "reference" / ...`。
干净 clone 实测（`GENEBENCH_ROOT` 指向 cleanroom）：

```
run_joblist.answer_root(public) = <CR>/reference/tasks/public/v1.0-smoke-public
run_controls.PUBLIC_ANSWER_ROOT = /data/shared/genebench/reference/tasks/public/v1.0-smoke-public
两者相等？ False
```

**后果**：外部用户即使把本包正确落位，`ops/score_runs.py` 仍然去发布方的绝对路径找题集，
那个路径在他们机器上不存在 → 每个 run 都记 `没有题目录`，整批结算不出分。
在 f01 上这两条路径**碰巧都存在**，所以内部怎么跑都发现不了
（`ops/test_c65.py:49` 那条 `RJ.answer_root("public") == RCTL.PUBLIC_ANSWER_ROOT`
也只在发布方机器上成立）。

`ops/run_controls.py` 不在本卡的可改路径里，**没有动它**。已登记
`ops/tickets_inbox/B2.md`，并写进 `notes_for_orchestrator`。同一类写死还有
`run_controls.py:48/49/54`、`ops/validator_parity.py:40-41`、
`ops/run_probe_mutations.py:46/382` —— 前四条在端到端主链上。

## 10. 本卡没做的事

* **没有重冻**：一次 `--write` / `--write-public` / `--write-reference` 都没跑过。
  本卡是把缺的文件**补回去**让现算根回到冻结值，不是重冻。
* 没有改三条轴的值（1.0.16 / r1.0.23 / p1.0.0 一个字没动）。
* 没有重打公开树、没有 push、没有碰 Release、没有碰已发的两个附件。
* 第三个附件**只打包落到 `$GB/release/public_v1/` 并登记**，`download_url` 留空 —— 本轮不上传。
* 没有重算 τ/ε（排 v1.0.17）。
