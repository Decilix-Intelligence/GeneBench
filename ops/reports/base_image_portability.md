# 统一基座的多架构可行性（卡 A2，2026-09-13）

**一句话**：`build/base/Dockerfile` 里钉的每一样东西，**amd64 与 arm64 两侧都拿得到**；
amd64 是在 f02 上**实测构出来的**，arm64 是把**每一个 pin 逐条查实**（其中 Node 的
arm64 tarball 与三个 aarch64 轮子是真下载下来核过哈希的），
但**没有在一台 arm64 机器上把镜像真构出来过** —— 本轮没有可用的 arm64 构建环境，
原因与证据在 §3。Apple Silicon 用户照做的命令在 §4。

本报告是卡 A2 的产物之一。它回答的问题是：Mac 外部验收里「统一基座没有交付」这一条
补齐之后，那份 Dockerfile 拿到 Apple Silicon 上还成不成立。

---

## 1. 基线：现有 `gb-base:bookworm-r1` 长什么样

搬进仓库的那一份要与它一致，所以先把它量下来（f02，2026-09-13）。

| 项 | 实测值 |
|---|---|
| 镜像 ID | `sha256:fd1e2fd0c7ae39ec2d15e293801a6744b286c4dfe76c45dcc8888c8b92da8e52` |
| 创建时间 | `2026-09-05T13:04:21.981435073Z` |
| 架构 / OS | `amd64` / `linux` |
| 内容大小 | `202,645,970` 字节（`docker image inspect .Size`） |
| 磁盘占用 | 889 MB（`docker images` 的 DISK USAGE） |
| `node -v` | `v22.23.2` |
| `npm -v` | `10.9.8` |
| `python -V` | `Python 3.12.14` |
| `pip freeze --all` | `numpy==2.5.2` `pandas==2.3.3` `pip==25.0.1` `pyarrow==25.0.1` `python-dateutil==2.9.0.post0` `pytz==2026.3.post1` `six==1.17.0` `tzdata==2026.3` |
| `uname -m`（容器内） | `x86_64` |
| Debian | 12.15（bookworm） |

原始 Dockerfile（f02 的 `build/base/Dockerfile`，2026-09-05）**没有任何 `COPY` 或 `ADD`** ——
也就是说它不依赖同目录下的任何别的文件，依赖清单是"内联在 `pip install` 那一行里"的
`pandas==2.3.3 pyarrow==25.0.1`，传递依赖一个都没钉。同目录里除它之外只有一份 `build.log`。
搬进仓库时把那一行拆成了 `requirements.txt`（直接依赖）+ `constraints.txt`（传递依赖，
取自上表的 `pip freeze`），**装到的版本因此与上表逐行相同**（§2 的实测）。

apt 层装的是 `curl ca-certificates xz-utils`，装完 `purge` + `autoremove` + 删 lists，
不留在最终镜像里（`ca-certificates` 是基础镜像本来就有的）。

---

## 2. amd64：**实测**，用仓库里的这份 Dockerfile 构了一次

```
docker build --no-cache -t gb-base:portcheck-20260913 build/base
```

| 项 | 实测值 |
|---|---|
| 结果 | 成功 |
| 耗时 | **282 秒**（冷缓存） |
| 新镜像 ID | `sha256:af693651ce03871dd2f8399b2170618c12fdf634ecafaae05cc4de0b9f1da8c4` |
| 架构 / OS | `amd64` / `linux` |
| 内容大小 | `202,649,476` 字节（比既有基座多 3,506 字节 —— 多出来的是 `COPY` 进去的两份清单那一层与 apt 时间戳） |
| 磁盘占用 | 889 MB |
| `node -v` / `npm -v` | `v22.23.2` / `10.9.8` |
| `python -V` | `Python 3.12.14` |
| `pip freeze --all` | **与既有基座逐行相同**（脚本里 `diff` 过，零差异） |

既有的 `gb-base:bookworm-r1`（`fd1e2fd0c7ae…`）与 `gb-cx-u:r1`（`961e3878b28f…`）
在整个过程中**没有被覆盖也没有被删除**，收尾时逐个核过 ID 不变。
`gb-base:portcheck-20260913` 作为证据保留在 f02 上。

---

## 3. arm64：逐个 pin 的可得性，以及为什么没能真构

### 3.1 逐条结论

| # | pin | arm64 拿不拿得到 | 证据等级 | 依据 |
|---|---|---|---|---|
| 1 | `FROM python:3.12-slim-bookworm@sha256:782412e8…` | **拿得到** | **实测**（直查 registry） | 这个 digest 是 **OCI image index**（`application/vnd.oci.image.index.v1+json`），不是单架构镜像 digest。index 里 10 条 manifest，含 `linux/amd64` → `sha256:9c47360a2a0355e2d…` 与 **`linux/arm64/v8` → `sha256:d04f49f5882f49a3b…`**（另有 arm/v7、386、ppc64le…），版本 `3.12.14-slim-bookworm`。**同一行 `FROM` 不需要为 arm64 换 digest**，docker 按构建平台自己挑 |
| 2 | Node 22.23.2 arm64 tarball | **拿得到** | **实测**（真下载 + 核哈希 + 验 ELF） | `https://nodejs.org/dist/v22.23.2/SHASUMS256.txt` HTTP 200；`node-v22.23.2-linux-arm64.tar.xz` 真下下来 30,246,708 字节，`sha256` 实算 = `fff4078c5def658577f92c88db7db3bc0072924bfb93fe52c1e744a54e94abb8` = Dockerfile 里钉的值；解出的 `bin/node` 是 `ELF 64-bit LSB executable, ARM aarch64`（`e_machine=0xb7`） |
| 3 | Node 22.23.2 x64 tarball | 拿得到 | **实测** | 同一份 SHASUMS，`d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307`，与改动前钉的值**逐字相同**（这次没有换 x64 的值，只是把它改名成 `NODE_SHA256_AMD64` 并补了 arm64 那一个） |
| 4 | `pandas==2.3.3` | **拿得到** | **实测**（真下载 + 核哈希） | `pandas-2.3.3-cp312-cp312-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl`，11,737,212 字节，实算 `sha256:ecaf1e12bdc03c86…1a1908` = PyPI 记的值 |
| 5 | `pyarrow==25.0.1` | **拿得到** | **实测**（真下载 + 核哈希） | `pyarrow-25.0.1-cp312-cp312-manylinux_2_28_aarch64.whl`，46,820,190 字节，实算 `sha256:4340f0ba6c1d2e13…d87e3` = PyPI 记的值 |
| 6 | `numpy==2.5.2`（pandas 的传递依赖，`constraints.txt` 钉着） | **拿得到** | **实测**（真下载 + 核哈希） | `numpy-2.5.2-cp312-cp312-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl`，15,612,696 字节，实算 `sha256:8ee9c4eeb8454b36…b676a9` = PyPI 记的值 |
| 7 | `python-dateutil` / `pytz` / `six` / `tzdata` | **与架构无关** | **查实**（PyPI JSON） | 四个在 PyPI 上**各只有一个** wheel，都是 `py2.py3-none-any.whl` 纯 Python：`python_dateutil-2.9.0.post0` / `pytz-2026.3.post1` / `six-1.17.0` / `tzdata-2026.3` |
| 8 | 架构选择逻辑 `dpkg --print-architecture` | **成立** | **查实** | Debian 的 `dpkg` 在 arm64 rootfs 上打印 `arm64`。**这一条没有在 arm64 机器上跑过** —— 它是本报告里唯一一条"逻辑上对但没实机验证"的关键路径 |
| 9 | 整镜像在 arm64 上构得出来 | **未验证** | — | 见 §3.2 |

三个二进制轮子是在 f02（x86_64）上真下下来核的哈希 —— **下载与校验跟运行平台无关**，
所以这一步不需要 arm64 机器就能做实。下载耗时 260 / 283 / 501 秒（f02 到
`files.pythonhosted.org` 的链路很慢），合计约 74 MB。

第 8 条之所以不用 BuildKit 的 `${TARGETARCH}`：f02 的 docker 走的是 legacy builder
（`docker buildx` 是 unknown command，CLI 插件只有 `docker-compose` 与 `docker-trust`），
那里 `TARGETARCH` 不一定有值，而空值会落到 Dockerfile 的「不支持的架构」分支 ——
**报出来的原因跟真正的原因无关**。`dpkg --print-architecture` 在两种 builder、
本机构建与 `--platform` 模拟构建下都给出正确答案。

### 3.2 为什么 arm64 没能在 f02 上真构（实测，时间盒内）

三条路一条都不通：

1. **没有 buildx**。`docker buildx version` / `docker buildx ls` → `docker: unknown command: docker buildx`。
   CLI 插件目录 `/usr/libexec/docker/cli-plugins/` 里只有 `docker-compose` 与 `docker-trust`。
2. **没有 qemu 模拟**。`/proc/sys/fs/binfmt_misc/` 下只有 `python3.12`、`register`、`status`
   三项，**没有任何 `qemu-aarch64` 处理器**；`/usr/bin/qemu-aarch64{,-static}` 都不存在。
   要注册它通常是 `docker run --privileged tonistiigi/binfmt --install all` ——
   **那个镜像在 docker.io 上，而 f02 到 docker.io 不通**（`registry-1.docker.io` 与
   `auth.docker.io` 实测 `http=000`；同一台机器上 `github.com` / `nodejs.org` /
   `pypi.org` / `deb.debian.org` 都是 200）。没有 sudo，也不能自己装 binfmt。
3. **legacy builder 的 `--platform` 是个陷阱**。实跑
   `docker build --platform linux/arm64 -t … build/base`，它**没有报"不支持"**，
   而是照常往下构：apt 装的是 `libcurl4:amd64`、抓的是 `binary-amd64_Packages`、
   `dpkg` 认出 amd64 于是取了 x64 的 Node 并核过了哈希 —— 一路"绿"到第 6 步 `COPY`
   才炸：

   ```
   Step 6/9 : COPY requirements.txt constraints.txt /tmp/gb-base/
   failed to get destination image "sha256:321a94db7a51…":
   image with reference sha256:321a94db7a51… was found but does not
   provide the specified platform (linux/arm64)
   ```

   也就是说 **legacy builder 把 `--platform` 当空气**，只在最后一刻发现平台对不上。
   这一条本身值得记进票据：谁在一台没有 buildx 的机器上敲 `--platform`，
   前五步的成功输出会让他以为在交叉构建。

**结论**：f02 上构不出 arm64，不是"没试"，是三条路都被堵死；按卡的口径
「没有就别硬来」停在这里，没有去硬装 binfmt。

---

## 4. Apple Silicon（arm64）用户照做什么

Mac 上的 Docker Desktop **自带 buildx 与 BuildKit**，而且 Apple Silicon 上
**本机架构就是 arm64** —— 所以最省事的做法是**什么平台参数都不加**：

```sh
# 在仓库根目录。Apple Silicon 上这就是一次原生 arm64 构建。
docker build -t gb-base:bookworm-r1 build/base
```

或者干脆别自己敲，让 `harnesses/build.sh` 发现缺基座时自己去构：

```sh
sh harnesses/build.sh codex
```

需要**显式**指定平台时（例如在 Intel Mac 上为 arm64 机器构、或想确认它真的在做 arm64）：

```sh
docker build --platform linux/arm64 -t gb-base:bookworm-r1 build/base
# 经 build.sh 走同一条：
GB_BASE_PLATFORM=linux/arm64 sh harnesses/build.sh codex
```

构完自己核一眼（这三行是"构对了没有"的全部判据）：

```sh
docker image inspect gb-base:bookworm-r1 --format '{{.Architecture}} {{.Os}} {{.Size}}'
docker run --rm --entrypoint sh gb-base:bookworm-r1 -c 'uname -m; node -v; npm -v; python -V'
docker run --rm --entrypoint sh gb-base:bookworm-r1 -c 'pip freeze --all'
```

期望看到：`arm64 linux …` / `aarch64` / `v22.23.2` / `10.9.8` / `Python 3.12.14`，
以及与 §1 表格里逐行相同的 `pip freeze`（`pip` 那一行除外，它随基础镜像走）。

**在 Intel/amd64 机器上用 `--platform linux/arm64` 之前**先确认你有 buildx
（`docker buildx version` 有输出）与 binfmt 模拟，否则会重演 §3.2 的第 3 条。

### 预计耗时与体积（arm64）

| | 估计 | 依据 |
|---|---|---|
| 原生 arm64（Apple Silicon）构建耗时 | **4–8 分钟**（冷缓存） | 以 amd64 实测 282 秒为基准，按 M 系列的单核更快、核数更少折算；下载量 arm64 略小（Node 30 MB vs 46 MB） |
| 模拟（qemu）交叉构建耗时 | **30–90 分钟** | qemu 用户态模拟通常慢 5–20 倍，且 `pip install` 装的是预编译轮子、不重新编译，所以不会到最坏情况 |
| 镜像内容大小 | **约 190–210 MB** | 与 amd64 的 203 MB 同量级；arm64 的 Node 与轮子略小 |
| 磁盘占用 | **约 850–900 MB** | 同上 |

这几个数是**估计不是实测**，标注如上。

---

## 5. 还剩什么不确定

1. **没有在 arm64 机器上把这个镜像真构出来过。** 所有 pin 都逐条查实（其中 4 条是
   真下载核哈希），但"四件东西都拿得到"与"`docker build` 一路跑绿"之间还隔着一次真跑。
   缺的是一台 arm64 构建环境：f02 是 x86_64 且没有 buildx/binfmt，f01 没有容器运行时，
   编排方这台 Mac 的沙箱连不上 Docker daemon（`unix:///Users/…/docker.sock` permission denied）。
   **补法**：让有 Apple Silicon 的人跑一次 §4 的第一条命令，把那三行核对的输出贴回来。
2. `dpkg --print-architecture` 在 arm64 rootfs 上返回 `arm64` —— 查实，未实机验证（§3.1 第 8 条）。
3. 本报告只覆盖**基座**。叠在它上面的 harness 镜像（`gb-cx-u` 等）各自 `npm install -g`
   或 `pip install` 自己的东西，那些包的 arm64 可得性**不在本卡范围内**，没有查。
