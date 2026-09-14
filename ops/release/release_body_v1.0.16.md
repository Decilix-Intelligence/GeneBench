# GeneBench v1.0.16

面向大模型 agent 的量化研究基准。八个阶段、双臂（`strict` / `open`）对照，
冻结线 `2026-07-31`，发布表是 `--table main`（**19 个指标列 + 5 个身份列 = CSV 24 列**，
**刻意没有总分**：把多阶段合成一个数的列会被一条测试当场拦掉）。

仓库里带着**完整答案面**（oracle 源码、评分器、标定物料），clone 下来就能算分；
体积大的行情面与 gold 因子面板放不进仓库，作为**三件附件**挂在本页。

---

## 三件附件

| 附件 | 字节数 | sha256 |
| --- | ---: | --- |
| `genebench_public_provider_v1.tar.gz` | 782,100,276 | `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9` |
| `genebench_public_gold_subset_v1.tar.gz` | 157,448,605 | `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06` |
| `genebench_public_runtime_v1.tar.gz` | 42,046,516 | `49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f` |

* **provider** —— 公开通道的冻结 qlib 行情面（沪深，前复权 + 复权因子），
  以及宇宙定义面（由 baostock 成分接口重建）。
* **gold 子集** —— 出集题目与实例真正读到的那部分 gold 因子面板。
  **够跑题、够算分**，不够重新推导全量 gold 上的选取。
* **runtime** —— 公开题集实例树（`reference/tasks/public/v1.0-smoke-public/`）
  与公开通道的标定物料（`calibration.json`、`epsilon/`）。
  **缺了它，公开冻结根核不绿、题也跑不起来。**

**三件都匿名可下，不需要 token。**

---

## 下载

```sh
B=https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16
curl -L -O $B/genebench_public_provider_v1.tar.gz
curl -L -O $B/genebench_public_gold_subset_v1.tar.gz
curl -L -O $B/genebench_public_runtime_v1.tar.gz
```

## 校验（**三行都要 OK 再解包**）

先把校验和写成一个文件：

```sh
cat > SHA256SUMS.release <<'SUMS'
33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9  genebench_public_provider_v1.tar.gz
edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06  genebench_public_gold_subset_v1.tar.gz
49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f  genebench_public_runtime_v1.tar.gz
SUMS
```

**核包的命令两边不同名**，按你的系统选一条：

```sh
# Linux（GNU coreutils）
sha256sum -c SHA256SUMS.release
```

```sh
# macOS —— /usr/bin 里没有 sha256sum；一定在的是 perl 的 shasum
shasum -a 256 -c SHA256SUMS.release
```

两边通用的写法（脚本里用这个）：

```sh
sumc() { if command -v sha256sum >/dev/null 2>&1; then sha256sum -c "$@"; else shasum -a 256 -c "$@"; fi; }
sumc SHA256SUMS.release
```

**看输出，别只看退出码** —— 少一行 `OK` 就是没下全。

解开之后每个包里还有一份**逐文件**校验表，**三个包的文件名各不相同**
（写混了会「找不到文件」）：

```sh
tar xzf genebench_public_provider_v1.tar.gz
( cd genebench_public_provider_v1    && sumc SHA256SUMS )
tar xzf genebench_public_gold_subset_v1.tar.gz
( cd genebench_public_gold_subset_v1 && sumc gold_subset_SHA256SUMS )
tar xzf genebench_public_runtime_v1.tar.gz
( cd genebench_public_runtime_v1     && sumc runtime_SHA256SUMS )
```

---

## 解开之后放哪儿

**解包目录与运行时布局不是一一对应的** —— `provider/` 还要改名成 `qlib_provider/`。
逐条落位命令、以及落位对不对怎么自查（`ops/selfcheck_public.py`），
都在仓库 `README.md` 的 **§2.1a**。

跑起来还要两件事，两件都写在 `README.md` §2.3 / §2.4 与 `docs/OPERATOR_MANUAL.md`：

* **公开通道要显式开**：`export GENEBENCH_CHANNEL=public`，且每条跑批命令带 `--channel public`。
  不开的代价是**静默** —— 干跑照样把命令渲染出来，真跑才报「找不到任务目录」。
* **认清自己是单机还是双机**：`--topology single|dual`（不给按 `dual`）。
  单机形态整条路径**不含任何跨机步骤**，`--topology single` 一路带着走。

---

## 已知限制（挑三条最影响读数的）

* **`csi1000` 不在包里**（公开成分接口没有它）—— 公开通道复现不出任何以 csi1000 为宇宙的读数。
* **gold 只发子集**：够跑题、够算分，不够重新推导全量 gold 上那 30 条的选取。
* **阈值与当前 gold 名单不同源**：分可复现；但 `calibration.json` 里的 τ、ε 带与 IC 族阈值
  标定在**换面之前**那一版成分名单上，贴着阈值的边界样本可能判反。本版不重算。

逐条量化见仓库 `ops/reports/known_limits_v1.md`；数据许可见 `DATA_LICENSE`。

---

## 许可

代码与数据各有各的许可，见仓库根的 `LICENSE` 与 `DATA_LICENSE`。
附件有几件、各自的 sha256 与地址，**以仓库 `ops/release/attachments.json` 为准**。
