# 数据卡：公开运行物料 `genebench_public_runtime_v1`

> v1.0.16 的**第三个** Release 附件。前两个是数据面（公开 provider、公开 gold 子集），
> 这一个装的是「跑得起来、算得出分」所必需、而**仓库与前两个附件都没有**的两堆。
> 建卡由来与完整判据见 `ops/reports/public_runtime_material.md`（卡 B2，2026-09-13）。

## 1. 身份

| 字段 | 值 |
| --- | --- |
| 包名 | `genebench_public_runtime_v1.tar.gz` |
| 字节数 | **42,046,516** |
| sha256 | `49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f` |
| 包内文件 | 533 件 / 84,755,038 B（另加包内三件 `runtime_SHA256SUMS` / `runtime_MANIFEST.json` / `runtime_README.md`） |
| 构建 HEAD | `efe17e81695fe57c71ef0906dc508bc7fc336ee5` |
| `built_at` | `2026-09-13T00:00:00+00:00`（可复现口径：同一棵树 + 同一个 `--built-at` → tar.gz 逐字节相同） |
| 打包器 | `ops/release/pack_public_runtime.py` |
| 落点 | `$GB/release/public_v1/` |
| `download_url` | `https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16/genebench_public_runtime_v1.tar.gz`（2026-09-13 传上 Release `v1.0.16` 后回填） |
| 四条轴 | 1.0.16 / p1.0.0 / r1.0.23 / `geneprotocol_v1@<逐 run 反算>` |

## 2. 装了什么

| 包内前缀 | 件数 | 字节 | 是什么 | 答案面 |
| --- | ---: | ---: | --- | :---: |
| `reference/tasks/public/v1.0-smoke-public/` | 506 | 73,467,699 | 公开题集的**物化实例**：34 道题的题面 / `arms/` / `work/` 夹具 / `solution/` / `gold/` / `scorer.yaml` / `taskspec.json`，外加 `_ledger.jsonl` | **是**（有意，见 §5） |
| `snapshots/public_v1/` | 27 | 11,287,339 | `calibration.json`（41,410 B）+ `calibration.sha256` + `epsilon/`（23 件 / 11,245,846 B） | 否（τ/ε 是**阈值**不是解） |

**没装**：`gold_factors*/`、`crosscheck/`、`tables/`、`qlib_provider/`、`tradability/`、
`universe/`、`instruments_rebuild/`、`state/`。前两个已在 gold 子集附件里，
后几个已在 provider 附件里；`instruments_rebuild/` 与 `state/` 是构建中间态，不随包发。

## 3. 数源与口径

* **题集实例**：`ops/mk_instances.py` 按 `genetask/templates` + `genetask/params` 物化；
  夹具字节由 `reference/make_fixtures.py` / `reference/make_s7_signal.py` 生成，
  数源是公开通道的 provider 与 gold（baostock 派生），冻结线 `2026-07-31`。
* **`calibration.json`**：`reference/calibration.py` 建，链路
  公开 provider → gold → 互检 → τ → ε → IC-ε → `calibration.json`
  （`ops/run_public_chain.py`）。τ = `0.9839810664562939`，`card` = `2.2`，
  `freeze_date` = `2026-07-31`，`ready_for_scoring` = **false**，
  `outstanding` = `["epsilon: 标定源失效，等换源后回填（E-1 / D-05）"]`。
* **`epsilon/`**：`build_info.json` 记 `"channel": "public"` /
  `"produced_by": "ops/run_public_chain.py"` / `reference_version` `r1.0.19`。

**公开 ≠ 私有，逐字段核过**：公开 τ `0.9839810664562939` ≠ 私有 τ `0.9840059556217291`；
公开 `calibration.json` 全文扫绝对路径只出现 `snapshots/public_v1/…` 五处，
**没有一处指向 `snapshots/v1/`**。打包器的 `FORBIDDEN_SUBSTRINGS` 里有
`snapshots/v1/` 与 `tasks/private/`，命中即拒绝打包。

## 4. `tables/manifest.json`：**显式 public/snapshot 下不需要它**

外部验收报过「`snapshots/public_v1/tables/manifest.json` 不存在，但日历仍读得出」。
查清了，**不该发**，也不是漏发：

`gateway/backends.py` 里这个文件只出现在一处 —— `default_backend()` 的最后一行
`return "snapshot" if SNAPSHOT_MANIFEST.exists() else "live"`，而 `SNAPSHOT_MANIFEST`
**恒指私有** `snapshots/v1/tables/`，是私有通道「有没有快照物料」的自动切换开关。
公开通道在它上面一行就无条件 `return "snapshot"`，根本走不到。

干净 clone 实测（没有该文件）：`public 通道 default_backend() = snapshot`。
**下一个人不用再撞这一次。**

## 5. 这个包里有答案面 —— 有意的

题集实例带每道题的 `solution/`（参考解 + gold artifact）、`gold/`、`scorer.yaml`。
不带就算不出分：`scorer/score_run.py:328` 把 `task_dir/work` 当 gold 目录，
`:291-292` 读 `task.yaml` 与 `taskspec.json`。

这与 v1.0.16 公开树「带全部答案面」是同一条裁定（N-627 走 B）。**红线 2 在本版是
容器边界口径**：答案面永不挂进 agent 容器。打包器据此
① `assert_dest_is_not_on_the_exec_plane()` 硬挡落点，② **不提供任何推送开关**，
③ 硬挡 `tasks/private/` / `snapshots/v1/` / `memory_probe_answers/` / `runs_in/` /
凭据形态文件（`.env*` / `secrets.env` / `*.pem` / `*.key` / `id_ed25519*` / `id_rsa*`）。

代价（题面与参考解在公网、有进训练语料的风险）是设计性限制，
记在 `ops/reports/known_limits_v1.md`「G2（2026-09-12）」，v1.1 以留出集处理。

## 6. 落位

```sh
tar -xzf genebench_public_runtime_v1.tar.gz
(cd genebench_public_runtime_v1 && sha256sum -c runtime_SHA256SUMS)     # 533/533 OK
tar -xzf genebench_public_runtime_v1.tar.gz --strip-components=1 -C "$GENEBENCH_ROOT"
```

落位后 `ops/freeze_v10.py --check-all` 三条轴全绿，公开根 =
`3e5ab441a991c4115a6c0fb988715f583e22ee303f582f1302fd3197fb183538`。
**不要**用 `--write-public` 把它改绿 —— 那是重冻，会让已发通行证作废。

## 7. 它复现不了什么

* **τ/ε/IC 阈值算在「换面之前」的 gold 上**，与现包的 gold 子集不同源；
  贴近阈值的样本可能翻转通过/不通过。重算排 v1.0.17（见
  `ops/reports/known_limits_v1.md` 与 `ops/reports/public/instruments_switch.md` §7）。
* `calibration.json` 里记着**发布方的绝对路径**（`provider.dir` 等五处）。
  评分**不读**它们；只有 `ops/test_public_chain.py:296` 有一条断言读，
  外部环境下那条会红 —— 登记不修。
* `calibration.json` 自己写着 `ready_for_scoring=false` / `outstanding`
  「epsilon: 标定源失效，等换源后回填」—— 这是既有登记（N-265 / N-266），不是本包引入的。
* 本包**不含** csi1000 行情，也不足以重新推导整个因子池的选取（与 gold 子集同限）。

## 8. 相关

* 完整报告与判据实测：`ops/reports/public_runtime_material.md`
* 打包器：`ops/release/pack_public_runtime.py`；附件登记：`ops/release/attachments.json`
* 定向测试：`ops/test_b2.py`
* 公开通道总卡：`ops/data_cards/public_channel.md`（**待补一条指向本卡的链接**，见 `ops/tickets_inbox/B2.md`）
