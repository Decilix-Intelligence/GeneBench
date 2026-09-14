# 推前扫描（卡 P / 用户裁定 ⑬）

**生成时间** 2026-09-12T11:16Z · **执行** 卡 P · **性质** 只读扫描，不删不改任何文件

被扫的是**将要推上去的那两棵树**，不是仓库工作树：

| 树 | 路径 | 文件数 | 体积 | 提交 |
| --- | --- | --- | --- | --- |
| GeneBench | `$GB/release/trees/genebench/` | 2,164 | 27 M（含 `.git` 39 M）| `800004f` |
| GeneQuant | `$GB/release/trees/genequant/` | 25 | 640 K | `1269121` |

两棵都是 `git init` 出来的**新历史、单次提交**，源是 `$GB/repo` 的 `git archive HEAD`
（HEAD = `ed29e02`，卡 H 的第二次提交）。`git archive` 只取已提交内容，
所以工作树里别人未提交的四个文件（`ops/reports/validator_parity.*` 等）与 `paper/`
**不在树里** —— 这一点是顺带核到的，不是设计。

扫描器：`$GB/scratch/P/scan_final.py`（凭据 / 派生表 / 记忆探针 / scratch 与 run 目录四项）
与 `$GB/scratch/P/scan_mentions.py`（⑫，另出一份报告）。
容器口径那一项走 `runner/f02/answer_plane_guard.py --mode container`。

---

## 结论先写（**不是零命中**）

| 项 | 结果 | 挡不挡推送 |
| --- | --- | --- |
| ① 凭据 | 文件名 **0**；内容 **3 条，逐条核实全是判别力夹具与占位串** | 不挡 |
| ② ChinaScope / tushare 派生 | **树里没有任何派生数据表**；但 **Release 附件里有**（见 §2.3）| **挡 ⑭（附件），不挡 ⑫⑪（推树）** |
| ③ 记忆探针钥匙 | **0** | 不挡 |
| ④ scratch 与 run 目录 | **0** | 不挡 |
| ⑤ answer_plane_guard 容器口径 | 正例绿 / 两个反例红 —— **门有牙** | 不挡 |

**一句话**：两棵**树**扫干净了；**Release 附件（⑭）扫不过**，原因是许可，不是泄漏。
详见 §2.3 与 `push_result.md`。

---

## ① 凭据

### 文件名层面

判据：`*.env` / `.env*` / `secrets*` / `*.pem` / `*.key` / `id_ed25519*` / `id_rsa*` /
`*.p12` / `*.pfx` / `github.env` / `.netrc`

```
genebench  0 件
genequant  0 件
```

f01 上真正的凭据在 `~/.config/genebench/`（`secrets.env` / `github.env`，均 0600），
**在仓库之外**，`git archive` 取不到 —— 「查过了没有」与「没查」分得开。

### 内容层面

判据六条正则（OpenAI/DeepSeek 形态、Anthropic 形态、GitHub token 形态、AWS AK 形态、
私钥 PEM、`key|secret|password|token = "<16 位以上字面量>"` 赋值形态）。
**本报告不抄任何命中的字面量** —— 抄一遍就等于自己往仓库里写一个 key 形态的串，
会把 `ops/test_env.py` 的红线 3 门跑红（契约点过名）。

```
genequant  0 条
genebench  3 条 —— 逐条核实如下
```

| # | 位置 | 是什么 | 判定 |
| --- | --- | --- | --- |
| 1 | `ops/test_env.py:850` | `test_key_scanner_is_discriminating` 往 `tmp_path` 里写的**坏输入夹具** | **不是凭据**。这条测试的正题就是「扫描器抓不抓得住」，夹具是它的反向判别项；删了这个夹具，红线 3 那道门就变成恒绿 |
| 2 | `ops/test_env.py:857` | 同一个测试的第三个夹具（长 base64 形态的 `token` 赋值） | 同上 |
| 3 | `harnesses/opencode/README.md:57` | 文档在讲 opencode 的 `{env:…}` 模板语法，随后出现的是容器里的**占位 key**（`sk-genebench-placeholder`，边车 `_client_key()` 认的就是它） | **不是凭据**。真 key 由边车注入，容器里从来只有占位串 |

三条都写在**测试与文档**里，没有一条出现在配置、脚本或数据文件中。

---

## ② ChinaScope 与 tushare 派生表

判据分两层：**名字/内容特征**（`chinascope` / `csf_` 前缀 / `tushare` / `ts_code` /
`index_member_all` / `pro_bar` / `daily_basic`）与**数据文件后缀**
（`.parquet` / `.csv` / `.duckdb` / `.feather` / `.jsonl` 等）。

### 2.1 字样命中（**是引用，不是数据**）

```
genebench  958 条 / 51 个文件
genequant   15 条 /  3 个文件
```

逐类：`ts_code`（tushare 列名）298 条、`tushare` 字样 60 条、`index_member_all` 23 条、
接口/表名 10 条、`chinascope` 字样 9 条。命中最密的是
`ops/lake_baseline.json`(74) / `ops/test_qlib_provider.py`(30) / `ops/tickets.md`(22) /
`ops/lake_baseline.md`(19) / `ops/tradability.json`(18) / `ops/recon_public_vs_private.py`(18)。

**逐个看过之后的判定：这些是「对账报告、基线声明与测试」，不是数据的再分发。**
它们说的是「私有通道的这张表有多少行、列叫什么、覆盖到哪天」，
以及「公开通道与私有通道对不对得上」。举证：

* `ops/universe_reconciliation.json` —— 抬头写着 *「PIT 宇宙对账:源A(index_weight 月末 diff)
  vs 源B(qlib instruments)」*，正文是参数、日历格点与抽样口径，**没有成分名单本身**；
* `ops/lake_baseline.json` —— `generator` / `rows` / `columns` / `min_date` / `max_date`
  这一类**模式与计数**；
* `ops/tradability.json` —— 日历约定与交易日数。

### 2.2 数据文件

```
genebench  142 件，最大的一件 552,199 B（factor_library/compiled/qlib_native.jsonl）
genequant    0 件
```

142 件全部是**因子库编译产物**（`factor_library/compiled/*.jsonl`：因子表达式与编译状态）
与**报告表**（`ops/reports/**/table_*.csv`、`metrics_*.csv`、`oracle_matrix.csv`）。
**没有一件是行情面板**：树里最大的数据文件 540 KB，
而真正的行情在 `$GB/snapshots/`（`daily.parquet` 单件就 330 MB），**那不在 git 树里**。

> 这一点与 `EXCLUDED.txt` §① 的说法一致，本卡独立复核过：
> `snapshots/` 目录在树里装的是**代码**（`manifest.py` 一类），不是快照数据。

### 2.3 **挡住 ⑭ 的那一条：Release 附件里有 tushare 派生面**

⑭ 要把**公开 provider 包**传成 Release 附件。那个包里有一层不是 baostock 的产物：

`$GB/release/_staging_unpublished/public_v1/MANIFEST.json` 自己写着（原文）：

> `instruments/` 的宇宙定义来自私有 `universe_pit`（tushare `index_member_all` 派生），
> 不是 baostock 的产物 —— 它的再分发不在 baostock 许可的射程内，发布前须单独确认

仓库的 `DATA_LICENSE` **§5** 用一整节说同一件事（原文）：

> 它的再分发**不在 baostock 许可的射程内** —— §2 的授权**不覆盖这一块**，
> **正文到位之后也不会**覆盖 […] **发布前须单独确认**（卡 1.4 提出）。

实物核过，确实在：

```
snapshots/public_v1/qlib_provider/instruments/
    all.txt      110,825 B      SZ000001  2009-01-05  2026-07-31   ← 谁在哪个指数里、从哪天到哪天
    csi300.txt    46,717 B
    csi500.txt    93,775 B
    csi1000.txt  138,105 B
包内另有 universe/ 一层 = scratch/v1_union.txt（3,575 行）
```

**用户裁定 ⑨ 覆盖不到这一块**：⑨ 给的授权摘要是
「研究用途、允许再分发**派生日线数据**、署名 baostock」，
`instruments/` 是**指数成分历史**，不是日线，来源也不是 baostock（baostock 没有这份数据）。
`DATA_LICENSE` §5 已经预先写明「正文到位之后也不会覆盖」。

**因此 ⑭ 停在这里，记 BLOCKED，不自行放宽判据。** 出路是 `DATA_LICENSE` §5 给的两条，
都要用户来定，本卡不替用户选：

1. 取得上游（tushare 侧）对这份派生名单的再分发许可；
2. **不发 `instruments/`**，改发重建脚本、让用户自备宇宙定义 ——
   代价是形态 A 的包不再自足，公开通道的三个 v1 宇宙用户复现不出来。

---

## ③ 记忆探针钥匙

```
genebench  0（reference/memory_probe_answers/ 整棵不在树里）
genequant  0
```

`EXCLUDED.txt` §③ 记着它被整棵剔掉。真正的钥匙本来就在仓库之外
（`$GB/reference/memory_probe_answers/`），git 树里原本也只有一份 README；
整棵剔掉是照裁定的字面执行 —— **这个目录名本身就是「钥匙在哪」的路标**。
卡 G2 的 `ops/test_g2.py::test_the_public_tree_has_no_memory_probe_keys` 盯着这条。

## ④ scratch 与 run 目录

```
genebench  0（scratch / runs / runs_in / run_dirs 四个名字都扫过）
genequant  0
```

## ⑤ answer_plane_guard —— 按裁定 ④ 的**容器口径**跑一次

命令（`$GB/scratch/G2/evidence.py`，随 `mk_tree_g2.sh` 在 2026-09-12T11:16:08Z 跑的）：

```sh
$PY runner/f02/answer_plane_guard.py --mode container \
    --compose <run_dir>/compose.yml --run-dir <run_dir> --log <log.jsonl>
```

结果（全文见 `$GB/release/trees/scan_genebench_container.txt`）：

| 用例 | 命中 | 期望 |
| --- | --- | --- |
| 正例：只把本 run 的 `work/` 挂到 `/task` | 0 条 | 绿 ✓ |
| 反例①：把公开树的 `reference/` 挂进 `/task/ref` | 1 条 `answer_plane_dir` | 红 ✓ |
| 反例②：顶层 named volume 的 `driver_opts.device` 偷挂带 gold 串的目录 | 1 条 `gold_token` | 红 ✓ |

**正例绿、两个反例红 —— 这道门有牙，不是恒绿也不是恒红。**

### 树口径的 95 条命中**不是红**，别误读

`$GB/release/trees/scan_genebench_tree.txt` 里树口径命中 **95 条**。
按裁定 ④，这棵树**有意带全部答案面**（`reference/`、`scorer/`、`genetask/templates`、
`genetask/params`、47 份 `solve.py`、标定代码）。树口径对它已经没有判别力 ——
上一版那个「0 命中」在新口径下恰恰意味着「这棵树对外没用」（不带答案面就有
65 个模块 import 断链，结算算不出分）。
有判别力的问题是「拿这棵树跑评测时答案面有没有被挂进 `/task`」，那是 ⑤ 那一栏。

---

## 复现

```sh
GB=/data/shared/genebench; PY=$GB/env/bin/python
cd $GB && PYTHONDONTWRITEBYTECODE=1 $PY scratch/P/scan_final.py release/trees/genebench genebench
cd $GB && PYTHONDONTWRITEBYTECODE=1 $PY scratch/P/scan_final.py release/trees/genequant genequant
cd $GB && PYTHONDONTWRITEBYTECODE=1 $PY scratch/P/sum_scan.py        # 汇总
bash $GB/scratch/G2/mk_tree_g2.sh                                    # 末尾自带容器口径证据
```

机读输出：`$GB/scratch/P/scan_genebench.json`、`scan_genequant.json`。
