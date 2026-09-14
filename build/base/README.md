# `build/base/` —— GeneBench 统一基座 `gb-base:bookworm-r1`

这一份就是构出统一基座的那一份。**2026-09-13 之前它不在仓库里** —— 它住在发布方
执行面的一个绝对路径下，于是外部用户 clone 下来跑 `harnesses/build.sh`，
拿到的是一句「先去 `/data/genebench_runner/build/base/Dockerfile` 构基座」，
而那是他没有的机器上的一条他没有的路径。2026-09-13 的 Mac 外部验收就阻塞在这里
（缺件①）。搬进仓库之后，**一台只有 Docker 的干净机器光凭这棵树就能把基座构出来**，
`harnesses/build.sh` 在基座缺失时也会自己来构。

## 1. 为什么要有"统一基座"

N-62 的裁定（2026-09-05）：三条配置的全部意义是「同一模型、三种 harness，**固定模型效应**」。
三个 harness 各用各的官方基座时（`python:3.12-slim` / `node:22-slim` / RD-Agent 自带），
pandas 只有 RD 那个有、且版本与题面钉的不一致 —— 主表上「harness 差异」那一列里
就混进了运行时差异。而 S2/S3/S7 的产出恰恰是 parquet/csv **数值**，
pandas 与 pyarrow 的版本会影响它们。

所以所有 harness 的 `Dockerfile` 第一条有效指令都必须是 `FROM gb-base:bookworm-r1`，
`harnesses/build.sh` 在构建前显式核这一条。

## 2. 里面钉了什么

| 层 | 值 | 怎么钉的 |
|---|---|---|
| 基础镜像 | `python:3.12-slim-bookworm@sha256:782412e8…` | 钉的是 **OCI image index**（manifest list）的 digest，不是某一架构的镜像 digest —— 所以同一行 `FROM` 在 x86_64 与 Apple Silicon 上都解析得出 |
| Python | 3.12.14（基础镜像自带） | 随基础镜像 |
| Node | 22.23.2 | 官方 tarball + **按架构分的两个 sha256**（见下） |
| npm | 10.9.8（随 Node tarball） | 随 Node |
| 数值栈 | pandas 2.3.3 / pyarrow 25.0.1 | `requirements.txt`（直接依赖）+ `constraints.txt`（连传递依赖一起钉死） |

**Node 的 tarball 与 sha256 是按架构分的**：`node-v22.23.2-linux-x64.tar.xz` 与
`node-v22.23.2-linux-arm64.tar.xz` 是两个不同的包、两个不同的哈希。
2026-09-13 之前这里只钉了 x64 的那一个 —— 在 Apple Silicon 上的表现是
「下到 arm64 的包、拿 x64 的哈希去核」，`sha256sum -c` 当场失败，
看起来像下载损坏，而真正的原因是这份 Dockerfile 只认一个架构。
现在两个值都钉着，架构由镜像里的 `dpkg --print-architecture` 选。

`constraints.txt` 里的传递依赖取自既有 `gb-base:bookworm-r1` 的 `pip freeze --all`。
有它，换一台机器换一天构建装到的是同一批版本；没有它，pandas 的 numpy 会随构建日期漂。

## 3. 怎么构

```sh
# 在仓库根目录
docker build -t gb-base:bookworm-r1 build/base
```

多数时候你**不用手敲这条**：`harnesses/build.sh` 发现本机没有基座时会自己来构。

```sh
sh harnesses/build.sh codex          # 缺基座 → 先构基座，再构 harness
sh harnesses/build.sh codex --dry-run    # 只看要发生什么，什么都不构
sh harnesses/build.sh codex --no-base-build   # 缺基座就报错，不要自动构
```

树里没有 `build/`（例如只同步了执行树）的机器，用 `GB_BASE_CONTEXT` 指过去：

```sh
GB_BASE_CONTEXT=/path/to/build/base sh harnesses/build.sh codex
```

## 4. 构建期要出哪些网

构建期联网、运行时断网（卡 4.1 L-8）。这一步要能访问：

| 域名 | 干什么 |
|---|---|
| `registry-1.docker.io` / `auth.docker.io` | 拉 `FROM` 的 `python:3.12-slim-bookworm` |
| `deb.debian.org` | `apt-get` 装 curl / ca-certificates / xz-utils（装完就 purge 掉） |
| `nodejs.org` | Node tarball |
| `pypi.org` / `files.pythonhosted.org` | pandas / pyarrow 及其传递依赖的轮子 |

四个里缺哪一个都构不出来。**如果你的网络到不了 `docker.io`**：在能出网的机器上构好，
然后 `docker save gb-base:bookworm-r1 | gzip > gb-base.tar.gz` 搬过去 `docker load`。

## 5. 要多久、多大

实测（2026-09-13，x86_64 Ubuntu，Docker 29.1.3，12 核 30 GB，`docker build --no-cache`）：

| | 值 |
|---|---|
| 构建耗时 | **282 秒**（约 4 分 42 秒），冷缓存、不含 `FROM` 那一层的首次 pull |
| 镜像内容大小 | **约 203 MB**（`docker image inspect` 的 `.Size` = 202,649,476 字节） |
| 磁盘占用 | **约 889 MB**（`docker images` 的 DISK USAGE，解压后、含共享层） |
| 构建期峰值下载 | 约 250 MB（apt ≈ 10 MB + Node 约 46 MB(x64) / 30 MB(arm64) + 轮子约 80 MB） |

有缓存时同一条命令**几秒钟**就打印"构建完成"，digest 与旧镜像相同 —— 想量真实成本
必须加 `--no-cache`（N-616）。

叠在基座上的 harness 镜像另算：codex ≈ 1.6 GB、claude-code ≈ 1.4 GB、
openhands ≈ 2.6 GB、rd ≈ 2.8 GB（磁盘占用）。

## 6. 多架构

`FROM` 钉的是 multi-arch 的 index digest，Node 两个架构的哈希都钉着，
pandas/pyarrow/numpy 的 cp312 aarch64 manylinux 轮子经核实都在 —— 也就是说
**这份 Dockerfile 在 amd64 与 arm64 上都成立**。

amd64 是**实测**（见上表）。arm64 这一侧哪些是实测、哪些是查实，以及
Apple Silicon 用户照做的确切命令，逐条写在
[`ops/reports/base_image_portability.md`](../../ops/reports/base_image_portability.md)。

## 7. 改这里的代价

改 `requirements.txt` / `constraints.txt` / Node 版本 = 改所有 harness 的运行时数值栈，
而 S2/S3/S7 的产出是数值。**重构基座之后所有 harness 镜像都要跟着重构**，
新 digest 要同步到所有引用它的 `ops/export_bundle.py --digest` —— 漏掉的表现是
「通行证核对绿而跑的是另一个镜像」。

`build/` 与 `harnesses/build.sh` **不在任何一条冻结根内**
（`ops/freeze_v10.py` 的 `CODE_FILES` / `CODE_DIRS` / `TEMPLATE_FILES` /
`REFERENCE_*` 逐条查过，2026-09-13），所以改它们不需要推版本号。
但上一段那句「所有 harness 镜像都要跟着重构」照样成立。
