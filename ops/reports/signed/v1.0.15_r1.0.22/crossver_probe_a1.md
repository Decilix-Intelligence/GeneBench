# 跨版本数值核（A1 前置，N-62 统一基座）— 2026-09-05

脚本：`ops/acceptance/crossver_probe.py`。输入：`s4-cor-01/work/factor_panel.parquet`（agent 可见的 bundle 文件，
341 380 B；不是参考面产物）。两边各跑一次，JSON 逐键 diff。

| 侧 | python | pandas | numpy | pyarrow | 怎么跑 |
|---|---|---|---|---|---|
| f01 oracle 环境 | 3.10.20 | 2.2.3 | 1.26.4 | 20.0.0 | `env/bin/python` |
| 统一基座 `gb-base:bookworm-r1`（f02 容器） | 3.12.14 | 2.3.3 | 2.5.2 | 25.0.1 | `docker run --rm --network none -v xver:/x:ro` |

核的量（18 键）：面板形状/NaN 数、float64 与 float32 求和、float32 位串 sha、逐日截面 rank 自相关
（tie = average / min / first；n、mean、std(ddof=1)、2.5%/97.5% 分位）、移动块自举（`default_rng(0)`、
1000 次、块长 20；分位与前 5 个均值）、`pct_change`/`rolling(20)`/`groupby.std` 聚合、`describe()` sha、
parquet 往返 sha。

**结果：17/18 键逐位相同（repr 级）。** 唯一不同的是 `parquet_roundtrip_sha`（pyarrow 20 与 25 写出的
字节流不同——编码/元数据差异，**读回的值相同**，上面 17 键就是证据）。

判定：统一基座与 oracle 环境在本基准用到的算子上数值一致；A1 可以在统一基座镜像上跑，
N-62 的偏离从「数值未核」缩为「harness 镜像层未复现」（`gb-cx-u:r1` / `gb-oh-u:r1` 已在基座上重叠一层，
`gb-rd-u:r1` 构建中）。

原始输出：f01 `/data/shared/genebench/xver/f01_env.json`、f02 `/data/genebench_runner/xver/f02_base.json`
（已拷回 `xver/f02_base.json`）。第三条（f01 同机、`env_base_site` 钉版本）等 pip 装完补跑，用来把
「版本差」与「机器差」分开。
