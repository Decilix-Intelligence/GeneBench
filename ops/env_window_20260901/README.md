# 人工窗口取证 · 2026-09-01

**用途**：环境基线。日后换机或重装直接复用，不必再进一次人工窗口。

⚠ **落点说明**：签字人指定的路径是 `/data/genebench/ops/env_window_20260901/`，
但 `/data/genebench` **尚不存在**（T-01 的搬家还没做，`/data` 是 `root:root 755` 不可写）。
本目录落在当前的 `$GENEBENCH_ROOT/repo/ops/` 下，**T-01 搬家时随仓库一起过去**。

| 文件 | 内容 |
| --- | --- |
| `f01_exports_before.txt` | finance01 `/etc/exports` **改前**（备份自 `/etc/exports.bak-genebench`）|
| `f01_exports_after.txt` | 同上**改后** —— `/data 192.168.1.219(rw,…)` 已注释 |
| `f01_showmount_after.txt` | `showmount -e 127.0.0.1` 实测**空** = 零导出确认 |
| `f02_ufw.txt` | finance02 ufw 规则**原文** |
| `f02_iptables_forward.txt` | FORWARD 链策略（docker 装完并重启后仍为 `ACCEPT`）|
| `f02_iptables_tailscale.txt` | tailscale 相关规则 —— D-07 的证据 |
| `f02_docker.txt` | docker 29.1.3 / compose 2.40.3 / 镜像加速 / `ljn` 在 docker 组 / 服务状态 |
| `f02_exports.txt` | ⚠ finance02 **自己的**导出，**本窗口未处理**，见下 |
| `cluster_nodes.txt` | 两节点 Ready |
| `w3_verify.txt` | W3 分区级校验 + 40 GB 备份删除记录 |

## 两件本窗口**没有**闭环的事

**① finance02 仍以 `rw` 把 `/data` 导出给 finance01。**
本窗口封的是 **f01 → f02** 那条（执行面经 NFS 读 f01 的湖与 `$GENEBENCH_ROOT`），
方向对；但 f02 侧的 `/data 192.168.1.48(rw,…)` 还开着（工单 W1 早就建议改 ro）。
它不是网关旁路（方向相反），但仍是一条 rw 通道。

**② 更要紧：finance02 本地就有 40 GB 湖副本。**
`/data/market_lake_f02`（`drwxr-xr-x`，**world-readable**）。
执行面（docker）跑在 f02 上，所以**「容器内不得挂载任何 NFS」是必要但不充分的** ——
容器只要 bind-mount 了 `/data` 或其任何父路径，就能直读整个湖，根本不需要 NFS。
**M4 的隔离约束必须写成：容器不得 bind-mount 任何宿主机路径（只允许任务工作目录），
且数据只能经网关 `192.168.1.48:18080` 取。**
