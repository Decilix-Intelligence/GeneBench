# finance01 环境基线（施工用速查）

> **角色**：数据面。GeneBench 的网关、快照仓、参考实现、评分器全部落在这台。
> **采集时间**：2026-08-30 11:55–12:35 UTC（readiness 第二轮 + R1 修订），端口与工具链部分补测于 2026-08-30 13:0x UTC（卡 0.0）。
> **采集方式**：严格只读探测，无 sudo（R1 的 ufw 原文除外，那次由用户临场提供 sudo）。
> **原始出处**：`ops/recon/readiness_r1.md` A.1 小节；`ops/recon/probes/`。
> **保鲜期**：环境类事实建议每次里程碑开工前复核一次；标 ⚠️ 的项变化会直接推翻施工假设。

---

## 1. 硬件与操作系统

| 项 | 值 |
|---|---|
| 主机名 / 地址 | `finance01`；LAN `192.168.1.48`、tailnet `100.79.40.76`（`finance01.tail642a54.ts.net`） |
| OS / 内核 | Ubuntu 24.04.4 LTS / `6.8.0-138-generic` |
| CPU | AMD Ryzen 5 5600G，1 路 6 核 12 线程（`nproc=12`） |
| 内存 | 30 GiB 总量 / 28 GiB 可用 |
| GPU | **无**（`nvidia-smi` 不存在；5600G 只有核显） |

⚠️ **无 GPU** —— 参考实现与评分器的一切模型训练必须是 CPU 可行的（LightGBM 已装，torch 未装）。

## 2. 磁盘（决定产物落点）

| 挂载点 | 容量 | 已用 | 可用 | 备注 |
|---|---|---|---|---|
| `/` （系统盘 SSD） | 232 G | 150 G | **71 G（68% used）** | 98 GB 主数据湖在这上面 |
| `/data` （机械盘） | 2.7 T | 73 G | **2.5 T（3% used）** | 68 GB ChinaScope 在这上面 |

**施工约束（红线 6）**：benchmark 的一切大体量产物（快照、结果库、wheel 缓存、任务工作区）**只落 `$GENEBENCH_ROOT`（在 `/data` 上），禁止落 `/home`**。系统盘只剩 71 G，写满会同时打死数据湖与 k3s。

⚠️ **落点是临时的**：当前 `GENEBENCH_ROOT=/data/shared/genebench`（mode 0700）。规范落点 `/data/genebench` 需要一条 sudo —— 见 **T-01**，且这是当前答案隔离的最大缺口（`/data/shared` 是 1777，且整块 `/data` 被 NFS 以 rw 导给 finance02）。

## 3. Python 与依赖

| 项 | 值 |
|---|---|
| 系统 `python3` | 3.12.3（**没装 duckdb**，不要用它干活） |
| 干活用的解释器 | `/home/ljn/tools/miniconda3/envs/qlib_env/bin/python`，Python **3.10.20** |
| conda | 23.11.0，装在 `~/tools/miniconda3` |
| 废弃环境 | `qlib_env_broken_20260802`（不要碰） |
| `~/venvs/` | finance01 上**不存在**（只有 finance02 有 `datahub`） |

**`qlib_env` 已装（实测版本，无需联网补装）**：

```
duckdb 1.4.3          pandas 2.2.3         pyarrow 20.0.0       numpy 1.26.4
scipy 1.13.1          scikit-learn 1.7.2   statsmodels 0.14.6   lightgbm 4.6.0
pyqlib 0.9.8.dev32    fastapi 0.141.1      uvicorn 0.52.1       pydantic 2.13.4
httpx 0.28.1          starlette 1.3.1      pytest 9.1.1         pyyaml 6.0.3
requests 2.34.2
```

**没有**：`torch` / `xgboost` / `catboost` / `numba`。

🚫 **`qlib_env` 只读使用，禁止 `pip install` 进去**（红线 2）。GeneBench 自己的环境是 `$GENEBENCH_ROOT/env`（克隆其包清单起步）。

## 4. 出口连通性

`curl -m 25`，取 `time_connect` / `time_total`：

| 目标 | 状态码 | 连接 | 总耗时 | 判读 |
|---|---|---|---|---|
| `https://github.com` | 200 | 0.11 s | 8.70 s | 通，首字节很慢 |
| `https://pypi.org/simple/` | 200 | 0.18 s | **25.00 s（撞上限）** | 🔴 索引页实际不可用 |
| `https://files.pythonhosted.org` | 200 | 0.14 s | 1.12 s | ✅ 包体下载通道很快 |
| `https://api.anthropic.com` | 403 | 0.23 s | 0.67 s | ✅ 通（403 是未鉴权 GET 的正常应答） |

→ **pip 卡在索引解析，不是卡在下载**。装依赖走两条路之一：预置 wheel 到 `$GENEBENCH_ROOT/wheels`，或用国内索引镜像（`$GENEBENCH_ROOT/pip.conf` 已就位）。
→ `api.anthropic.com` 的可达性与延迟都没问题，agent 臂可以直接出网调 API。

本机也跑着 `mihomo`（`127.0.0.1:7897` / `9097`），与 finance02 同构 —— 这解释了两台出网行为为什么一致。

## 5. 端口（网关选址依据）

`8080 / 8088 / 8100 / 8200 / 9100 / 18080` 在 `192.168.1.48` 上实测**均空闲**。
→ **网关用 `18080`，且必须绑 `192.168.1.48`，禁止监听 `0.0.0.0`**（红线 4：tailscale 绕过 ufw，绑 0.0.0.0 等于对全 tailnet 敞开；见 `ufw_finance01.txt`）。

已占用/需避让：`30810`（quantlab NodePort）、`2049`+`111`（nfsd/rpcbind）、`10250`（kubelet）、`5000`（MLflow，只绑 127.0.0.1）。`6443` closed（本机是 k3s **agent**，无 apiserver）。

## 6. 权限：没有 sudo，也没有 docker

```
$ sudo -n true                     → sudo: a password is required
$ which docker docker-compose      → command not found
$ systemctl is-active docker containerd → inactive / inactive
$ ls -l /var/run/docker.sock       → No such file or directory
$ ls -l /run/k3s/containerd/containerd.sock
  srw-rw---- 1 root root 0          ← root:root 0660，ljn 无权
$ crictl ... ps                    → permission denied
```

- `ljn` 的组：`ljn adm cdrom sudo dip plugdev lxd`。**在 sudo 组里但没有 NOPASSWD**，非交互场景拿不到 root。
- 唯一免 sudo 可用的隔离机制是 **LXD**（`snap.lxd.daemon` active，`lxc list` 以 ljn 身份返回空表，当前 0 实例）。注意：finance01 的 LXD 是**本来就装好的**，与侦察轮在 finance02 上误装的那次无关。
- k3s 角色：**agent**（非 control-plane）。节点带污点 `dedicated=quant:NoSchedule`，benchmark 的 Pod 默认调度不上来，需要显式 toleration。
- ⚠️ kubelet `allocatable == capacity`（12 核 / 32212588Ki），**没有任何系统预留** —— 起 Pod 必须自己写死 limits，否则跑满会把宿主一起拖垮。

## 7. 常驻定时任务（不得干扰，红线 2）

全部是 `systemd --user`（uid 1000），**没有 root cron**。除 `quant-datahub-premium-daily` 外共 20 个：

```
quant-datahub-daily                 quant-datahub-morning
quant-datahub-intraday-close        quant-datahub-realtime-market
quant-datahub-public-documents      quant-datahub-public-news
quant-datahub-aux-close             quant-datahub-aux-events
quant-datahub-aux-margin            quant-datahub-aux-monthly
quant-datahub-aux-quarterly         quant-datahub-fees
quant-datahub-coverage-audit        quant-datahub-qlib-candidate
quant-datahub-index-minute-backfill quant-datahub-premium-financial-refresh
quant-data-update                   quant-paper
quantlab-systemd-exporter           launchpadlib-cache-clean
```

🔴 `quant-datahub-index-minute-backfill` 当前 **failed** —— 见 **T-09**（非阻塞）。

## 8. 工具链

`git 2.43.0` · `conda 23.11.0` · `rsync`（`/usr/bin/rsync`）· `curl` · `ssh` 均可用。
**`unzip` 没装**（两台都没有）—— ChinaScope 的 schema 是用 Python `zipfile` 流式读前 24 KB 得到的。

## 9. 网络与防火墙

ufw 规则原文、两条绕过路径、以及对 NFS/NodePort 的影响见同目录 **`ufw_finance01.txt`**。
finance02 的对应文件尚缺 —— 见 **T-05**。

---

## 附：施工前 30 秒自检

```bash
ssh -o ConnectTimeout=60 -o ServerAliveInterval=15 ljn@finance01.tail642a54.ts.net '
  df -h / /data | tail -2
  /home/ljn/tools/miniconda3/envs/qlib_env/bin/python -c "import duckdb,pandas,pyarrow,qlib;print(duckdb.__version__,pandas.__version__)"
  ss -ltn | grep -E ":(18080|30810)\b" || echo "18080 still free"
  systemctl --user --failed --no-pager
'
```
