# 上传前最后一次扫描（卡 D 步骤 1 / 裁定 ③）

**日期** 2026-09-12 · **执行** 卡 D · **扫描器** `$GB/scratch/D/d_scan.py`（只读，流式读 tar，不落盘解包）
**机读输出** `$GB/scratch/D/scan_publish.json` · **结论：六项全部零命中，两个附件可以上传。**

这一份**不是**卡 C 那次核包的复述。卡 C 核的是「包打对了没有」（清单自洽、确定性、
与源逐字节相同）；这一份核的是「传到公网上会不会泄露」，判据另写一遍，
交集只有 `csi1000` 与逐行核成分表两条 —— **两次独立算出同一个 sha256**
本身就是一条证据（见 §0）。

## 0. 被扫的就是待传的那两个文件

| 附件 | 盘上字节数 | 本次现算 sha256 | 与 `ops/release/attachments.json` |
| --- | --- | --- | --- |
| `genebench_public_provider_v1.tar.gz` | 782,100,276 | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` | **一致** |
| `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` | **一致** |

tar 里的条目数比 `attachments.json` 的 `files_inside` 各多 3 件，**这不是对不上**：
`files_inside` 记的是被打进去的**内容件**，tar 里另有三件包自带的随附文档。逐字节对得上：

| 包 | tar 条目 | `files_inside` | 差 | 多出来的三件 | 字节差 |
| --- | --- | --- | --- | --- | --- |
| provider | 28,659 | 28,656 | 3 | `SHA256SUMS` / `MANIFEST.json` / `README.md` | 6,383,834 = 3,058,833 + 3,321,178 + 3,823 |
| gold 子集 | 47 | 44 | 3 | `gold_subset_SHA256SUMS` / `gold_subset_MANIFEST.json` / `gold_subset_README.md` | 14,969 = 5,015 + 8,215 + 1,739 |

## 1. 宇宙定义面：**逐行**核，不含任何 tushare 派生的成分行

判据不是「看起来像 baostock」，是**与卡 W2 的 baostock 重建产物逐行比对**
（`$GB/snapshots/public_v1/instruments_rebuild/{csi300,csi500}.txt`）：

| | 包内行数 | 重建产物行数 | 逐行不同的行 | 逐字节相同 |
| --- | --- | --- | --- | --- |
| `provider/instruments/csi300.txt` | 1,026 | 1,026 | **0** | **是**（`2c3ee2b7…`） |
| `provider/instruments/csi500.txt` | 2,269 | 2,269 | **0** | **是**（`8538c995…`） |

`provider/instruments/all.txt` 1,917 行：**落在 csi300 ∪ csi500 之外的 0 行**；
并集减 all 恰为 `SZ000022` / `SZ300114` 两只（这两只没有 features bin，卡 A §3 已给出理由）。

`universe/` 一层四件，逐件核过：

* `universe_pit.parquet` —— 3,295 行，`universe` 列的**取值只有 `csi300` / `csi500` 两个**
  （现场读 parquet 取 distinct，不是读 build_info 的自述）；列是
  `code / universe / in_date_compact / out_date_compact / ambiguous / canonical`。
* `build_info.json` —— `source` 记 baostock 三个接口，`note` 明写「不含任何 tushare / universe_pit 派生行」。
* `v1_union.txt` —— 3,575 行，**每行只有一个代码、没有任何成分区段列**
  （现场核：不存在任何一行分出第二个字段）。它是**取数名单**（决定 `features/` 有哪些票的 bin），
  不是宇宙定义面 —— 这个区分写在包内 `MANIFEST.json` 的 `universe_definition_note` 与
  `ops/reports/public/release_forms.md` §7.4 / §7.9。
* `MANIFEST.sha256`。

**`csi1000` 在两个包的全部路径与全部内容里命中 0 次。**

## 2. 凭据：零命中

* **文件名形态**：`.env*` / `*.env` / `secrets*` / `*.pem` / `*.key` / `id_rsa*` / `id_ed25519*` —— 两个包各 **0 件**。
* **内容正则**（七条，按形态写成正则，本仓库任何脚本与测试里都不写 key 形态的字面量）：
  `sk-`+长串、`gh[pousr]_`+长串、`github_pat_`+长串、`AKIA`+16、`xox[baprs]-`+长串、
  PEM 私钥头、`(DEEPSEEK|OPENAI|ANTHROPIC|TUSHARE|GITHUB)_(API_)?(KEY|TOKEN)` 后跟 16+ 位实值
  —— **逐条零命中**（占位串另有白名单，本次一条都没用上，因为根本没命中）。
  扫的是**全部字节**，不按后缀豁免：provider 包 997,749,931 B、gold 子集 159,409,406 B 全部过了一遍正则。

## 3. 记忆探针钥匙与答案面：零命中

* 路径段 `memory_probe_answers/` —— **0**。
* gold 串形状 `GBC-G-[0-9a-f]{16}`（与 `runner/f02/answer_plane_guard.py::GOLD_TOKEN_RE` 同一个模式）
  —— 两个包全字节扫，**0 命中**。
* 答案面文件名（`canary.json` / `scorer.yaml` / `solve.py` / `equivalence.md` / `slots.json` / `_ledger.jsonl`）
  —— 两个包各 **0 件**。

> **gold 子集包里装的就是 gold，这不矛盾。** 红线 2 管的是「答案面不进 f02、不进容器、不进 bundle」；
> 裁定 ② 明文要把 gold 子集打成公开下载附件。上面这三条查的是**另外三件事**：
> 探针钥匙（不在）、gold 串（不在 —— 因子面板是数值，不带题面串）、题面与参考解文件（不在）。

## 4. scratch 与 run 目录：零命中

路径段 `scratch/` / `runs/` / `runs_in/` / `run_dirs/` / `.git/` —— 两个包各 **0 件**。
tar 里也没有任何非普通文件条目（无软链、无设备、无目录条目）。

## 5. `answer_plane_guard --mode container` 对公开树跑一次

对 `$GB/release/trees/genebench/`（2026-09-12T16:51:45Z，`$GB/scratch/D/scan_genebench_container.txt`）：

| | 结果 |
| --- | --- |
| 正例：只把本 run 的 `work/` 挂到 `/task` | 挂载面 2 条，命中 **0** → **绿** |
| 反例①：把公开树的 `reference/` 挂进 `/task/ref` | 命中 **1**（`answer_plane_dir`）→ **红，符合预期** |
| 反例②：顶层 named volume 的 `driver_opts` 偷挂带 gold 串的目录 | 命中 **1**（`gold_token`）→ **红，符合预期** |

**正例绿、两个反例红 —— 这道门有牙。** 容器模式一个字节都没删。

树口径（第二道）对这棵树命中 **95 条**，**这不是红**：v1.0.16 起公开树**有意带全部答案面**
（用户裁定 N-627 走 B，不带的话外部用户算不出分）。树口径对一棵有意公开答案面的仓库没有判别力，
它保留下来是为私有通道的执行面。原委见 `$GB/release/trees/scan_genebench_tree.txt` 顶部那段。

## 6. 判定

```
PASS = true ；blocking = {}（六项逐项零命中）
```

任一项非零本卡即停下记 BLOCKED 不上传。**六项全零，附件本身没有挡上传的理由** ——
真正挡住上传的是凭据权限，见 `ops/reports/push_result.md` §2。
