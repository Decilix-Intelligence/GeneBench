# GeneBench 就绪度侦察报告（第二轮）

**扫描时间** 2026-08-30 11:55–12:35 UTC · **模式** 严格只读 · **写入范围** `~/genebench_inventory/`（finance01）

> **修订 R1（2026-08-30 12:35 UTC）**：用户提供 sudo 后补读了 finance01 的 ufw 规则原文，
> **推翻了 A.2 里关于"ufw 按接口放行"的推断**（详见 A.2 新增小节），并据此把 W1 的挂载地址从"待斟酌"改成确定结论。
> W0 已执行完毕并验证。新增 W5（tailnet 面的暴露）。D 节相应收窄。

## 执行摘要（三行）

1. **finance02 不能直接跑 docker compose 级的任务隔离**——两台机器都**没装 docker**，唯一的容器运行时是 k3s 内置的 containerd，socket 是 `root:root 0660`，而 `ljn` 的 sudo **需要密码**。agent 自身无法取得任何容器运行时权限。可用的隔离面只有三条：人工装 docker、直接用 k3s 起 Job、或用 LXD（finance01 已装且 ljn 免 sudo 可用）。
2. **PIT 四件套：三件齐、一件半缺。** 退市/摘牌、上市日期、ST 标记、停牌历史都有且带时间戳；**缺的是指数历史成分的调入调出记录**——湖里只有 `index_weight` 的**月末权重快照**，而且只覆盖沪深300/中证500/中证1000 三个指数，成分变动得靠相邻月末 diff 推。qlib 发布目录里倒有现成的 `csi300/csi500/csi1000` PIT 名单（带起止日期），但它来自社区数据源，不是自家湖。
3. **因子库可以直接充当参考实现与外部适配源。** 818 条 JSONL 记录、792 条可执行，每条同时带**源方言原文**与**编译后的 qlib 表达式**、`required_fields`、三种执行后端、以及结构化的 `blocking_reasons`——这正是 benchmark 需要的"标准答案 + 可执行基线 + 已知不可执行原因"三件套。

> ⚠️ **必须先声明的一处越界（非故意）**：我在 finance02 上执行 `lxc list` 探测容器能力时，Ubuntu 的 `lxd-installer` 包把这条命令当成了"按需安装"触发器，**自动安装了 LXD snap**（`lxd 5.21.7-1018661 rev 40585`，122 MB，安装时间 2026-08-30 12:07 UTC，`/var/snap/lxd/` 与 `/var/lib/snapd/snaps/lxd_40585.snap` 均为该时刻创建）。这违反了"不安装软件"的红线。我**没有**做任何后续配置（未 `lxd init`，无容器，无存储池），也**没有**尝试卸载（卸载同样是变更，且需要 sudo 密码）。finance01 上的 LXD 是**本来就装好的**（`lxc list` 直接返回空表，无安装提示），与本次无关。处置建议已列入待批工单 W0。

---

# A. 环境画像

## A.1 finance01（拟定角色：数据面）

| 项 | 实测值 |
|---|---|
| OS / 内核 | Ubuntu 24.04.4 LTS / `6.8.0-138-generic` |
| CPU | AMD Ryzen 5 5600G，1 路 6 核 12 线程，`nproc=12` |
| 内存 | 30 GiB 总量，可用 28 GiB |
| 系统盘 `/` | 232 G，已用 150 G，**余 71 G（68%）** |
| 机械盘 `/data` | 2.7 T，已用 73 G，**余 2.5 T（3%）** |
| duckdb | 1.4.3（在 `qlib_env` 里） |
| GPU | 无（`nvidia-smi` 不存在；5600G 只有核显） |

**磁盘余量结论**：98 GB 主湖在系统盘上，系统盘只剩 **71 GB**；68 GB ChinaScope 在机械盘上，机械盘还剩 **2.5 TB**。
→ benchmark 的任何大体量产物（镜像层、任务工作区、结果快照）**必须落 `/data`，不能落 `/home`**。

**Docker 与 docker compose**：**都不存在**。

```
$ which docker docker-compose   → command not found
$ systemctl is-active docker containerd  → inactive / inactive
$ ls -l /var/run/docker.sock    → No such file or directory
$ ls -l /run/k3s/containerd/containerd.sock
  srw-rw---- 1 root root 0 Aug 30 10:34   ← root:root，ljn 无权
$ crictl ... ps  → permission denied（且读不到 k3s 的 crictl.yaml）
$ sudo -n true   → sudo: a password is required
```

`ljn` 的组：`ljn adm cdrom sudo dip plugdev lxd`。在 `sudo` 组里，但**没有 NOPASSWD**，所以非交互场景下拿不到 root。
**唯一免 sudo 可用的隔离机制是 LXD**：`snap.lxd.daemon` active，`lxc list` 以 ljn 身份直接返回空表（当前 0 个实例）。

**Python 与环境**：

- 系统 `python3` = 3.12.3（**没装 duckdb**）
- conda：`~/tools/miniconda3/envs/qlib_env`（Python **3.10.20**，实际干活的那个）、`qlib_env_broken_20260802`（废弃）
- `~/venvs/` 在 finance01 上**不存在**（只在 finance02 上有 `datahub`）
- `qlib_env` 已装：`duckdb 1.4.3 · pandas 2.2.3 · pyarrow 20.0.0 · numpy 1.26.4 · scipy 1.13.1 · scikit-learn 1.7.2 · statsmodels 0.14.6 · lightgbm 4.6.0 · pyqlib 0.9.8.dev32`
- **没有** torch / xgboost / catboost / numba

**出口连通性**（`curl -m 25`，取 `time_connect` / `time_total`）：

| 目标 | 状态码 | 连接 | 总耗时 | 判读 |
|---|---|---|---|---|
| `https://github.com` | 200 | 0.11 s | **8.70 s** | 通，但首字节很慢 |
| `https://pypi.org/simple/` | 200 | 0.18 s | **25.00 s（撞上限）** | 🔴 索引页实际不可用 |
| `https://files.pythonhosted.org` | 200 | 0.14 s | **1.12 s** | ✅ 包体下载通道是快的 |
| `https://api.anthropic.com` | **403** | 0.23 s | 0.67 s | ✅ 通（403 是未鉴权 GET 的正常应答） |

→ **pip 装包会卡在索引解析而不是下载**。benchmark 的依赖安装应预置 wheel 或配国内索引镜像；`api.anthropic.com` 的可达性和延迟都没问题。

**常驻定时任务（除 `quant-datahub-premium-daily` 外，共 20 个）**：

```
quant-datahub-daily                      quant-datahub-morning
quant-datahub-intraday-close             quant-datahub-realtime-market
quant-datahub-public-documents           quant-datahub-public-news
quant-datahub-aux-close                  quant-datahub-aux-events
quant-datahub-aux-margin                 quant-datahub-aux-monthly
quant-datahub-aux-quarterly              quant-datahub-fees
quant-datahub-coverage-audit             quant-datahub-qlib-candidate
quant-datahub-index-minute-backfill      quant-datahub-premium-financial-refresh
quant-data-update                        quant-paper
quantlab-systemd-exporter                launchpadlib-cache-clean
```

全部是 `systemd --user`（uid 1000），没有 root cron。`quant-datahub-index-minute-backfill` 当前处于 **failed**。

## A.2 finance02（拟定角色：执行面）

| 项 | 实测值 |
|---|---|
| OS / 内核 | Ubuntu 24.04.4 LTS / `6.8.0-138-generic`（与 01 完全同款） |
| CPU / 内存 | Ryzen 5 5600G，12 线程 / 30 GiB（可用 27 GiB） |
| K3s 角色 | **server / control-plane**，`v1.35.6+k3s1`（`k3s` active，`k3s-agent` inactive） |
| kubectl | 可用，但**必须** `export KUBECONFIG=$HOME/.kube/config`；`/etc/rancher/k3s/k3s.yaml` 对 ljn 是 permission denied |
| GPU | 无 |
| 系统盘 `/` | 232 G，已用 84 G，**余 137 G** ← 40 GB 重复副本仍占着 |
| 机械盘 `/data` | 2.7 T，已用 40 G，**余 2.6 T** |

**集群资源余量**：

```
NAME        STATUS  ROLES          VERSION       INTERNAL-IP     RUNTIME
finance01   Ready   <none>         v1.35.6+k3s1  192.168.1.48    containerd://2.2.5-k3s2
finance02   Ready   control-plane  v1.35.6+k3s1  192.168.1.219   containerd://2.2.5-k3s2

finance01  cap 12 / 32212588Ki   alloc 12 / 32212588Ki   taints: dedicated=quant:NoSchedule
finance02  cap 12 / 32212596Ki   alloc 12 / 32212596Ki   taints: (none)
```

⚠️ **allocatable == capacity**，即 kubelet **没有做任何系统预留**。跑满会把宿主一起拖垮，benchmark 的 Pod 必须自己写死 limits。
finance01 带 `dedicated=quant:NoSchedule` 污点，benchmark 任务默认调度不上去（需要显式 toleration）。

**当前负载**：11 个 namespace / 27 个 pod。`cnpg-system · flux-system(6) · forgejo(5) · headlamp · kube-system(8) · portal(2, mlflow-relay + portal) · prismquant · quantlab · quantlab-ci · spectra · spectra-ci`。
🔴 `prismquant/prismquant-65b7bb9574-sf7mj` 处于 **Init:CrashLoopBackOff**（已 92 分钟）。

**containerd 与 docker CLI 各自的可用性**：

| | finance01 | finance02 |
|---|---|---|
| `docker` CLI | ❌ 不存在 | ❌ 不存在 |
| `dockerd` | ❌ inactive（未装） | ❌ inactive（未装） |
| `/var/run/docker.sock` | ❌ 不存在 | ❌ 不存在 |
| containerd | ✅ k3s 内置 `2.2.5-k3s2` | ✅ k3s 内置 `2.2.5-k3s2` |
| containerd socket 权限 | `root:root 0660`，ljn ✗ | `root:root 0660`，ljn ✗（`ctr` 报 permission denied） |
| `ctr` / `crictl` | 有二进制，无权限 | 有二进制，无权限 |
| 免密 sudo | ❌ | ❌ |

### ▶ docker compose 与 K3s 共存的判断

**技术层面：不冲突，但有两个必须处理的耦合点。**

- k3s 用自带的 containerd + flannel，与 dockerd 各用各的运行时和 CNI，二者可以并存（k3s 从 v1.24 起就不再依赖 dockershim）。
- **耦合点 1 — iptables FORWARD 链**：这套集群已经踩过一次 ufw 的坑（`DEFAULT_FORWARD_POLICY=DROP` 把 flannel 的 VXLAN 全丢了，后来改成 ACCEPT 并备份在 `/etc/default/ufw.bak-quantlab`）。dockerd 启动会插入自己的 `DOCKER-USER` / FORWARD 规则并可能改写策略，**装完必须复核 flannel 跨节点连通**（最快的验证是从 01 的 Pod ping 02 的 Pod IP）。
- **耦合点 2 — 网段冲突**：k3s 占了 `10.42.0.0/16`(Pod) 和 `10.43.0.0/16`(Service)，finance02 上还有 `10.88.0.1`（CNI 默认网桥残留）。docker 默认 `172.17.0.0/16` 不撞，但自定义 compose 网络要避开这三段。

**现实层面：这条路当前走不通，因为没人能装。** ljn 的 sudo 要密码，agent 无法非交互安装 dockerd，也无法把自己加进 docker 组。

**三条可选隔离方案（供施工阶段选型）**：

| 方案 | 可行性 | 代价 |
|---|---|---|
| **A. 人工装 docker + 把 ljn 加入 `docker` 组** | 需要人到场输密码一次 | 要复核 FORWARD 链；docker 组≈root 等价权限 |
| **B. 直接用 K3s Job/Pod 做任务隔离** | **零安装，现在就能用**（kubectl 已可用） | 要处理 finance01 的 NoSchedule 污点、PSA 等级、以及"没有系统预留"导致的资源打满风险 |
| **C. LXD** | finance01 现成可用且免 sudo；finance02 刚被误装（见 W0） | 是系统容器不是应用容器，与 compose 的心智模型差得远 |

我的建议是 **B 打底、A 作为提速项**：B 不需要任何变更就能起步，A 在人工窗口里一次性完成后再迁。

**网络出口（finance02）**：

| 目标 | 状态码 | 连接 | 总耗时 |
|---|---|---|---|
| `https://github.com` | 200 | 1.11 s | 7.71 s |
| `https://pypi.org/simple/` | 200 | 0.16 s | **25.00 s（撞上限）** |
| `https://api.anthropic.com` | **403** | 0.18 s | 0.56 s |

与 finance01 同构：pypi 索引不可用，Anthropic API 通且快。两台都**没有** `http_proxy` 环境变量，但 finance02 上跑着 `mihomo`（监听 `127.0.0.1:9090` / `9097`），说明出网可能走本机代理。

**两机互通**：

- **02 → 01 的 ssh：不通。** finance02 的 `~/.ssh/` 里只有 `authorized_keys` 和 `known_hosts`，**没有任何私钥**；实测 `ssh ljn@192.168.1.48` 返回 `Host key verification failed`。
  → 单向：01 → 02 可以（01 有 known_hosts，且 02 的 authorized_keys 收了 01 的公钥）；02 → 01 不行。**跨机文件流转仍须以 01 为发起方**。
- 端口探测（只探测，未改任何防火墙）：

| 方向 | 22 | 6443 | 2049 | 10250 | 30810 | 3000 | 8472 |
|---|---|---|---|---|---|---|---|
| 01 → 02 (`192.168.1.219`) | open | **open** | **open** | — | open | closed | closed |
| 02 → 01 (`192.168.1.48`) | open | closed | **closed** | open | open | — | — |
| 02 → 01 (tailscale `100.79.40.76`) | open | — | **open** | — | — | — | — |

  两处值得注意：① `8472/udp`（flannel VXLAN）用 TCP 探测显示 closed 属正常，不代表 VXLAN 不通；② **NFS 的 2049 在 LAN IP 上被挡、在 tailscale IP 上开着**——说明 finance01 的 ufw 规则是按接口放行的，这会直接影响挂回 NFS 时该用哪个地址。
- ~~`ufw status` **读不到**（需要 sudo 密码）。上表是从连通性反推的，不是规则原文。~~
  **R1 已补读 finance01 的规则原文，见下。finance02 的 ufw 仍未读。**

### ▶ R1：finance01 的 ufw 规则原文，以及两条绕过它的路径

```
Status: active
     To                   Action      From
[ 1] 22/tcp               ALLOW IN    192.168.1.0/24
[ 2] 8472/udp             ALLOW IN    192.168.1.219      # k3s flannel vxlan
[ 3] 10250/tcp            ALLOW IN    192.168.1.219      # k3s kubelet
[ 4] Anywhere             ALLOW IN    10.42.0.0/16       # k3s pod cidr
[ 5] Anywhere             ALLOW IN    10.43.0.0/16       # k3s service cidr

/etc/default/ufw:  DEFAULT_INPUT_POLICY="DROP"   DEFAULT_FORWARD_POLICY="ACCEPT"
```

🔴 **我在初版里的解释是错的。** 初版写"finance01 的 ufw 规则是按接口放行的"——**规则里根本没有任何一条提到 tailscale**（既没有 `100.64.0.0/10`，也没有 `tailscale0` 接口）。观察到的现象没错，机制说错了。真实机制是两条**绕过**：

**绕过 ① — tailscale 完全不经过 ufw。** Tailscale 在 Linux 上会把自己的 ACCEPT 规则插在 ufw 之前（`ts-input` 链），所以来自 tailnet 的流量**根本到不了上面这 5 条规则**。实测从我的 Mac（tailnet IP `100.95.238.12`，**不在** `192.168.1.0/24` 里）直连 finance01 的 tailnet IP：

```
100.79.40.76:22     OPEN   ← 规则[1]只允许 192.168.1.0/24，但 Mac 照样连得上
100.79.40.76:111    OPEN   ← rpcbind，ufw 里没有任何对应规则
100.79.40.76:2049   OPEN   ← nfsd，ufw 里没有任何对应规则
100.79.40.76:10250  OPEN   ← 规则[3]只允许 192.168.1.219，Mac 照样连得上
100.79.40.76:30810  OPEN
100.79.40.76:6443   closed ← 01 是 agent，本来就没有 apiserver
100.79.40.76:5000   closed ← MLflow 只绑 127.0.0.1
```

→ **结论：finance01 上所有监听 `0.0.0.0` 的服务，对整个 tailnet 是完全敞开的，ufw 一条也拦不住。** 当前 tailnet 里有 5 个节点，分属 `wx200.xyz@`（finance01/02 + 一台 Mac）和 `jiningluan@`（两台 Mac）两个账号。

**绕过 ② — `DEFAULT_FORWARD_POLICY="ACCEPT"` 放行了所有 NodePort。** k8s NodePort 走的是 nat PREROUTING 的 DNAT，之后落 FORWARD 链而不是 INPUT 链，所以 ufw 的 INPUT 规则看不到它。实测 `192.168.1.48:30810`（quantlab）从 finance02 是 open 的，而 ufw 里**没有任何一条允许 30810**。这个 ACCEPT 是当初为了修 flannel VXLAN 被丢包才改的（备份在 `/etc/default/ufw.bak-quantlab`），副作用就是**两台机器上所有 NodePort 对能路由到它们的任何地方都是开的**。

**缓解因素（不要过度惊慌）**：NFS 的访问控制不只靠端口。finance01 的 `/etc/exports` 是
`/data 192.168.1.219(rw,sync,no_subtree_check,root_squash)` —— **按客户端 IP 限定**，tailnet 上的 `100.x` 主机连得上 2049，但 mount 会被服务端拒。同理 kubelet 10250 在 k3s 下默认关闭匿名访问、要求客户端证书。所以"端口开着"≠"数据能拿走"，但**攻击面确实比 ufw 规则看起来的大得多**。

**对 W1 的直接影响（这条把待定项变成了确定结论）**：finance02 的导出是 `/data 192.168.1.48(rw,sync,no_subtree_check,root_squash)`，同样按 IP 限定。
→ **finance01 挂载时必须走 LAN 地址 `192.168.1.219`，不能走 tailscale 地址**——走 tailnet 时源 IP 会是 `100.79.40.76`，不匹配导出 ACL，直接被拒。初版里"挂载地址与 ufw 规则要一并确认"这句现在有答案了：**用 LAN，且 01→02:2049 的 LAN 通路实测已经是 open 的，不需要动任何防火墙**。

**顺带发现**：finance01 自己也在 `/etc/exports` 里把 `/data`（那块装着 ChinaScope 的 2.7 T 盘）以 **rw** 导给了 finance02。目前 `/proc/fs/nfsd/exports` 里没有活动客户端，即两个方向都没挂上。另外 finance01 上也跑着 `mihomo`（`127.0.0.1:7897` / `9097`），与 finance02 同构，这解释了两台的出网行为为什么一致。

---

# B. 八项定向数据确认

> 所有"关键字段名"均取自实际 schema；样例记录每处不超过 3 行。
> 除特别注明外，数据来自 finance01 的 `catalog/market.duckdb`（150 个只读 view）。

## B1. PIT 宇宙四件套 —— **部分齐（3 齐 / 1 半缺）**

### (a) 指数历史成分 —— 🟡 **半缺：只有月末权重快照，没有调入调出记录**

| 表 | `index_weight` |
|---|---|
| 字段 | `index_code, con_code, trade_date, weight, source, first_seen_at` |
| 覆盖 | **只有 3 个指数** |

```
index_code   rows     min        max        distinct_dates
000300.SH    63,298   20090123   20260731   211
000905.SH   105,500   20090123   20260731   211
000852.SH   142,000   20141031   20260731   142
```

样例：`('000300.SH', '300750.SZ', '20260731', 4.012, 'tushare', '2026-08-05T05:40:43Z')`

实测 2026 年的日期序列是 `20260130 / 20260227 / 20260331 / 20260430 / 20260529 / 20260630 / 20260731`，每期恰好 300 条 → **月末快照，不是逐日**。
**问题**：① 没有官方的 in/out 记录表，成分变动只能由相邻月末 diff 推断，且**月内调整会被抹平**；② 只有沪深300/中证500/中证1000，**没有上证50(000016.SH)、创业板指(399006.SZ)、中证800**；③ 冻结在 20260731。

**两个替代源**：

- `index_member_all` —— **有真正的 in/out**：`l1_code, l1_name, l2_code, l2_name, l3_code, l3_name, ts_code, name, in_date, out_date, is_new`。但这是**申万行业成分**，不是指数成分。
  样例：`('801010.SI','农林牧渔','801016.SI','种植业','850111.SI','种子','000998.SZ','隆平高科','20000629',None,'Y')`
  → 这块反而是**行业 PIT 的高质量来源**（`requires_pit_industry` 那批因子正好需要它）。
- **qlib 发布目录的 `instruments/`** —— `csi300.txt / csi500.txt / csi800.txt / csi1000.txt / csiall.txt / all.txt`，格式是 `代码 \t 起始日 \t 结束日`，本身就是 PIT 名单。样例：`BJ430017  2023-05-31  2025-09-30`。**这是目前最省事的指数宇宙来源**，代价是它来自社区数据源（见 B6）。

### (b) 退市与摘牌 —— ✅ 有

| 表 | `stock_basic` |
|---|---|
| 字段 | `ts_code, symbol, name, area, industry, market, exchange, **list_status**, **list_date**, **delist_date**, is_hs, source, first_seen_at, last_seen_at` |
| 分区 | `snapshot_date=YYYY-MM-DD`，共 18 个（**2026-08-05 → 2026-08-28**） |
| 规模 | `list_status='L'` 99,807 行 / 5,551 只；`'D'` 6,102 行 / **339 只**；有 delist_date 的 339 只 |

样例：`('920305.BJ', '云创退', list_date='20210826', delist_date='20260730', 'D')`

⚠️ 注意两点：① 它是**多快照表**（每天一份全量），行数远大于标的数——查询必须先选定 `snapshot_date`；② **快照只从 2026-08-05 开始**，也就是说"某只票在 2020 年的 list_status 是什么"这个问题，用这张表答不了（只能用 `delist_date` 字段回溯，而不是用快照）。

### (c) 上市日期 —— ✅ 有

`stock_basic.list_date`，范围 **19901201 → 20260828**。另有 `new_share`（IPO 新股，4,229 行）与 `stock_company`（7,014 行）可交叉验证。

### (d) ST 标记与停牌历史 —— ✅ 有，而且 ST 是双时间戳的

**逐日 ST 标记**：`stock_st` — `ts_code, name, trade_date, type, type_name, trade_month`，337,072 行，**20160809 → 20260825**。
实测 `type` 只有一个取值：`('ST', '风险警示板', 337687)` → **不区分 ST / *ST**，要区分得看 `name` 前缀。
样例：`('002650.SZ', 'ST加加', '20260828', 'ST', '风险警示板', '202608')`

**ST 事件历史**：`st_history` — `ts_code, name, **pub_date**(公告日), **imp_date**(实施日), st_tpye, st_reason, st_explain, event_id, published_month`，1,221 行。**这是 ST 侧唯一带公告/实施双时间戳的表**，直接可做 PIT。
样例：`('002485.SZ','*ST雪发','20220430','20220506','*ST','最近一个会计年度经审计的净利润为负值且营业收入低于一亿元…')`

**辅助**：`namechange`（`ts_code, name, start_date, end_date, ann_date, change_reason`，14,156 行，19901201 起）、`stk_alert`（`start_date, end_date, type`，257 行）、以及派生 view `stock_name_pit`（20,046 行，`end_date` 用 `99991231` 表示"仍生效"）。

**停牌历史**：`suspend_d` — `ts_code, trade_date, suspend_timing, suspend_type`，482,290 行，**20090105 → 20260828**。`suspend_type`：`S`=457,224（停牌）/ `R`=25,066（复牌）。`suspend_timing` 实测为 NULL。
样例：`('600491.SH', 2026-08-28, None, 'R')` · `('000711.SZ', 2026-08-28, None, 'S')`

## B2. 涨跌停与可交易性 —— ✅ 有，但**分散在三张表，且停牌是"缺行"**

**涨跌停价：独立表，`daily` 里没有。**

| 表 | 字段 | 规模 |
|---|---|---|
| `stk_limit` | `trade_date, ts_code, pre_close, **up_limit**, **down_limit**` | 15,003,310 行，20090105→**20260828** |
| `daily` | `ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, amount, volume` | 14,692,767 行 — **无任何涨跌停字段** |

样例：`(2026-08-28, '000001.SZ', pre_close=None, up_limit=12.75, down_limit=10.43)`
⚠️ `stk_limit.pre_close` 实测**全为 NULL**，别指望用它算涨跌幅；要判"是否触板"必须 `daily.close`（或 `high`/`low`）与 `stk_limit.up_limit/down_limit` 逐日 join 比价。

**触板/连板的现成标记**（都属于"冻结在 8/5–8/6"那一档）：

- `limit_list_d` — `trade_date, ts_code, industry, name, close, pct_chg, amount, limit_amount, float_mv, total_mv, turnover_ratio, **fd_amount**(封单额), **first_time**, **last_time**, **open_times**(炸板次数), **up_stat**, **limit_times**, **limit**('U'/'D')`，158,546 行，20200102→20260805。
  样例：`(2026-08-05,'000510.SZ','化学原料','新金路',16.12,10.03,901889104,None,9778559519.04,10454522574.08,9.45,57769098.0,'94018','103721',1,'2/2',2.0,'U')`
- `limit_step`（连板天梯，13,443 行）、`limit_cpt_list`（最强板块，13,274 行）、`limit_list_ths`（同花顺口径，105,049 行）、`premarket_limit`（盘前涨跌停价，2,991,034 行，20240410 起）

**停牌在数据里怎么体现：缺行，没有显式标记。** 实测 2026-08-28：

```
suspend_d 当日 S 类 = 5 条 | daily = 5,547 行 | stk_limit = 5,551 行
000711.SZ (S) → daily 中 0 行     ← 停牌当天在 daily 里直接消失
002586.SZ (S) → daily 中 0 行
600491.SH (R) → daily 中 1 行     ← 复牌当天正常有行
```

→ **`daily` 的"缺行"同时意味着"停牌"和"数据缺失"两件事，二者靠 daily 本身分不开**，必须与 `suspend_d`（以及 `trade_cal`）三方 join 才能给出可交易性判定。这是 benchmark 数据网关必须封装掉的第一个陷阱。
另注意 `stk_limit` 的行数（5,551）**大于** `daily`（5,547）——涨跌停价对停牌票照样发布。

## B3. 复权链路 —— ✅ 齐，且**两种口径并存**

**主口径 = 未复权 + 复权因子：**

| 表 | 字段 | 规模 | 截止 |
|---|---|---|---|
| `adj_factor` | `ts_code, trade_date, **adj_factor**` | 15,369,639 行 / 5,834 只 | **20260828（当前）** |
| `daily` | 14 列，价格均为**未复权** | 14,692,767 行 | 20260828 |

样例：`('000001.SZ', 2026-08-28, 139.008)` · `('000002.SZ', 2026-08-28, 181.704)`

**副口径 = 三套复权价并存**：`stk_factor_pro`（264 列）对 open/high/low/close 每个字段都给了三份 —— `open` / `open_hfq` / `open_qfq`（不复权 / 后复权 / 前复权），并且自带一列 `adj_factor`。
⚠️ 但 `stk_factor_pro` **冻结在 20260731**，比 `adj_factor` 落后近一个月。**两个口径不同步**，混用会在 2026-08 这一段产生不一致。

**qlib 侧**：features 里同时有 `factor.day.bin` 和 `adjclose.day.bin`，是第三套独立口径。

**其他品种**：`fund_adj`（基金复权因子）只到 **20260514**；`hk_daily_bar`（未复权）与 `hk_daily_adj_bar`（复权）分两张表。

## B4. 交易日历 —— ✅ 有，但 A 股只覆盖一个交易所

| 表 | 字段 | 交易所 | 起止 | 行数 |
|---|---|---|---|---|
| `trade_cal` | `exchange, cal_date, is_open, pretrade_date` | **只有 `SSE`** | **20090101 → 20261231** | 6,574 |
| `hk_trade_calendar` | `cal_date, is_open, pretrade_date`（**无 exchange 列**） | 港股 | 20090101 → 20260806 | 6,427 |
| `fut_trade_calendar` | `exchange, cal_date, is_open, pretrade_date` | CFFEX / CZCE / DCE / GFEX / INE / SHFE | 见下 | 28,201 |

```
CFFEX  4,236  20150101→20260806      DCE   6,426  20090101→20260806
CZCE   6,426  20090101→20260806      GFEX  1,324  20221222→20260806
INE    3,363  20170523→20260806      SHFE  6,426  20090101→20260806
```

样例：`('SSE','20261231',1,'20261230','tushare',...)`

**两个要点**：① `trade_cal` **没有 SZSE 条目**——沪深日历实际一致，用 SSE 代替可行，但 benchmark 文档里要写明这是个约定而不是数据事实；② 它**已经排到 20261231**（含未来日历），做 T+1/T+N 对齐时不会在样本末端断掉，这点很好用。
**qlib 侧日历更长**：`calendars/day.txt` 6,458 行覆盖 **2000-01-04 → 2026-08-26**（比湖早 9 年），另有 `day_future.txt` 6,543 行。

## B5. 财报双时间戳 —— ✅ 三大报表齐全，🟡 **财务指标表缺实际公告日**

| 表 | 期间字段 | 公告字段 | 修订标记 | PIT 可用性 |
|---|---|---|---|---|
| `income` | `end_date`, `end_type` | **`ann_date` + `f_ann_date`** | `update_flag` | ✅ 完整 |
| `income_vip` | `end_date`, `end_type`, `request_period` | `ann_date` + `f_ann_date` | `update_flag` | ✅ 完整 |
| `balancesheet` | `end_date`, `end_type` | `ann_date` + `f_ann_date` | `update_flag` | ✅ 完整 |
| `balancesheet_vip` | 同上 + `request_period` | 同上 | `update_flag` | ✅ 完整 |
| `cashflow` | `end_date`, `end_type` | `ann_date` + `f_ann_date` | `update_flag` | ✅ 完整 |
| `cashflow_vip` | 同上 + `request_period` | 同上 | `update_flag` | ✅ 完整 |
| `fina_indicator` | `end_date` | **只有 `ann_date`，无 `f_ann_date`** | — | 🟡 降级 |
| `fina_indicator_vip` | `end_date`, `request_period` | 只有 `ann_date` | `update_flag` | 🟡 降级 |
| `forecast` | `end_date` | `ann_date` + **`first_ann_date`** | `update_flag` | ✅ 完整 |
| `express` | `end_date` | `ann_date` | `update_flag` | 🟡 |
| `fina_mainbz_vip` | `end_date`, `request_period` | **没有任何公告日字段** | — | 🔴 不可 PIT |
| `disclosure_date` | `end_date` | `ann_date`, **`pre_date`(预约), `actual_date`(实际), `modify_date`** | — | ✅ 关键辅助表 |

样例（`income` / 600519.SH，取 `ts_code, ann_date, f_ann_date, end_date, end_type, update_flag, total_revenue, n_income`）：

```
('600519.SH','20260425','20260425','20260331','1','1', 54702912385.23, 28153831489.89)
('600519.SH','20260425','20260425','20260331','1','0', 54702912385.23, 28153831489.89)   ← 同一期两版
('600519.SH','20260417','20260417','20251231','4','1',172054171890.91, 85310324833.67)
```

样例（`fina_indicator` / 600519.SH）：`('600519.SH', ann_date='20260425', end_date='20260331', eps=21.76, roe=10.5687, netprofit_margin=52.2245)`
样例（`disclosure_date`）：`('920125.BJ', ann_date='20260805', end_date='20260630', actual_date='20260807', pre_date=None, modify_date=None)`

**结论**：三大报表可以严格 PIT（`f_ann_date` + `update_flag` 能同时处理"何时可见"和"是否被重述"）。**112 项财务指标那张表只能退而用 `ann_date`**，若要严格对齐，得拿 `(ts_code, end_date)` 回 `income`/`balancesheet` 取 `f_ann_date`。`fina_mainbz_vip`（主营构成，185 万行）**完全没有公告日**，PIT 场景下不可直接使用——这块正好由 ChinaScope 的产品级 PIT 顶上（见 B7）。

## B6. 因子库形态 —— ✅ **可以直接当参考实现与外部适配源**

**载体：JSONL，一行一条因子，schema 高度结构化。** 位置 `market_lake/reference/factor_library/`。

字段：`id · family · name · kind · record_type · expression（源方言原文）· compiled_expression（编译后的 qlib 表达式）· execution_backend · implementation · executable · blocking_reasons[] · required_fields[] · lookahead_detected · requires_benchmark · requires_pit_industry · custom_ops[] · license · source_id · source_path · source_line · source_revision · translation_notes · validation_status · notes`

**规模**：

```
catalog/   gtja_191 191 · qlib_alpha360 360 · qlib_alpha158 158
           worldquant_101 101 · local_core_v1 6 · qlib_strategy 2      = 818 条
compiled/  qlib_native.jsonl 644 · qlib_panel.jsonl 148 · blocked.jsonl 24  = 816 条 → 792 条可执行
           ⚠ 上面是**文件**行数，不是后端分布。按 `execution_backend` 字段实测：
           qlib_expression 644 · qlib_panel_loader 66 · qlib_kunquant_loader 82 · blocked 24
           （`qlib_panel.jsonl` 这一个文件里混着 panel_loader 与 kunquant 两种后端）
```

`catalog/index.json` 给每个族记了 `count` + `sha256`；`manifests/` 有 13 份带时间戳的快照 + `latest.json`。

**三种执行后端**：`qlib_expression`（原生表达式）· `qlib_panel_loader`（截面语义走 Qlib 面板 DataLoader）· `qlib_kunquant_loader`（KunQuant 0.1.11，pin 到 commit `d4b9e61`）。

> **更正（2026-09-01，卡 2.1 探路时发现）**：本节此前只按文件报了 `644 / 148 / 24`，读起来像后端分布，实际是文件行数。**以 `execution_backend` 字段为准的分布是 `qlib_expression 644 / qlib_panel_loader 66 / qlib_kunquant_loader 82 / blocked 24`**。两者的 792 与 24 不变，变的是 148 那一格拆成 66+82。卡 2.1 的三路分发按字段口径执行。

**随机抽 5 条原样**（已去掉部分长字段以控制篇幅，`expression` / `compiled_expression` 均为原文）：

```json
{"id":"qlib_alpha158.BETA10","family":"qlib_alpha158","name":"BETA10","kind":"qlib_expression","record_type":"factor","expression":"Slope($close, 10)/$close","compiled_expression":"Slope($close, 10)/$close","execution_backend":"qlib_expression","executable":true,"blocking_reasons":[],"required_fields":["close"],"lookahead_detected":false,"requires_benchmark":false,"requires_pit_industry":false,"license":"MIT","source_id":"microsoft_qlib","source_path":"qlib/contrib/data/loader.py","source_revision":"79633dd9506ea689e5400dea0197717b5b3d74b7","validation_status":"candidate","notes":"Executable does not mean empirically validated on the local A-share universe."}
```
```json
{"id":"gtja_191.001","family":"gtja_191","name":"gtjaAlpha1","kind":"formula_factor","expression":"(-1 * CORR(RANK(DELTA(LOG(VOLUME), 1)), RANK(((CLOSE - OPEN) / OPEN)), 6))","compiled_expression":"(-1 * CORR(RANK(DELTA(LOG(VOLUME), 1)), RANK(((CLOSE - OPEN) / OPEN)), 6))","execution_backend":"qlib_panel_loader","implementation":"dolphindb::gtjaAlpha1(open, close, vol)","executable":true,"required_fields":["close","open","volume"],"license":"Apache-2.0","source_path":"gtja191Alpha/src/gtja191Alpha.dos","source_line":21,"source_revision":"43ace2cc4b81d048864ec2e40c25728d5d464e05","validation_status":"executable_candidate","translation_notes":"Cross-sectional semantics are evaluated by the Qlib panel DataLoader."}
```
```json
{"id":"worldquant_101.001","family":"worldquant_101","name":"WQAlpha1","kind":"formula_factor","expression":"rank(Ts_ArgMax(SignedPower((returns<0?stddev(returns,20):close), 2), 5))-0.5","compiled_expression":"KunQuant.predefined.Alpha101.alpha001","execution_backend":"qlib_kunquant_loader","implementation":"dolphindb::WQAlpha1(close)","executable":true,"required_fields":["close"],"license":"Apache-2.0","validation_status":"executable_candidate","translation_notes":"Qlib DataLoader adapter; KunQuant 0.1.11 at d4b9e61f729df347730aa921b539b9df3c3fe36d. Alpha001 output is shifted by -0.5 to preserve the pinned catalog formula."}
```
```json
{"id":"local_core_v1.liquidity_20","family":"local_core_v1","name":"liquidity_20","kind":"liquidity","expression":"Log(Mean($amount,20)+1)","compiled_expression":"Log(Mean($amount,20)+1)","execution_backend":"qlib_expression","executable":true,"required_fields":["amount"],"license":"project_owned","source_path":"/home/ljn/projects/quant/platform/factor_library/curated/core_v1.yaml","validation_status":"research_baseline","notes":"Existing transparent weighted baseline; promotion still requires current out-of-sample evidence."}
```
```json
{"id":"gtja_191.030","family":"gtja_191","name":"gtjaAlpha30","executable":false,"conversion_status":"blocked","compiled_expression":null,"execution_backend":"","blocking_reasons":["point_in_time_benchmark_or_fama_french_inputs_unavailable"],"required_fields":["close","index_close"],"requires_benchmark":true,"expression":"When calculating, you need to obtain the MKT, SMB, and HML corresponding to the timestamp, and input these three values as vectors into parameters.","validation_status":"blocked_input_or_semantics","notes":"The factor remains disabled until the benchmark/Fama-French series pass PIT alignment checks."}
```

**为什么它对 benchmark 有直接价值**：每条同时给了 ①源方言原文（可以当 prompt 里的"题面"）②编译后的可执行表达式（可以当"标准答案"）③`required_fields`（可以自动推出该题需要哪些数据）④`blocking_reasons`（24 条**已知不可执行**的负样本，含理由）⑤`lookahead_detected` / `requires_pit_industry` 标志（现成的 PIT 陷阱标注）。这是一个已经做完"翻译 + 校验 + 归因"的语料层，不需要重建。

### qlib 发布目录的 provider 结构 —— ✅ **三件齐全**

```
~/projects/data/qlib/cn_data -> channels/community -> releases/2026-08-26/
├── calendars/    day.txt (6,458 行, 2000-01-04 → 2026-08-26) · day_future.txt (6,543 行)
├── instruments/  all.txt · csi300.txt · csi500.txt · csi800.txt · csi1000.txt · csiall.txt
│                 格式: 代码 \t 起始日 \t 结束日     例: BJ430017  2023-05-31  2025-09-30
├── features/     6,142 个标的目录 × 10 个 .day.bin，共 859 MB
│                 open · high · low · close · volume · amount · vwap · change · factor · adjclose
└── SOURCE.txt
```

**bin 数据起止：2000-01-04 → 2026-08-26**（`SOURCE.txt: calendar_last=2026-08-26`，带 sha256）。

⚠️ **两条 channel 并存，当前生效的不是自建那条**：

```
SOURCE.txt:  source=https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz
current_release.txt:    release=2026-08-04   ← local channel 的指针，已落后
community_release.txt:  release=2026-08-26   ← cn_data 实际指向这个
releases/ 下另有 local-daily-20260805/       ← 自家湖构建出来的那份
```

→ **现在 `cn_data` 喂的是社区数据，不是本地数据湖的产物。** benchmark 若以 qlib 为执行底座，必须先决定用哪条 channel：community 的时间更新、instruments 更全（自带 PIT 成分名单，正好补上 B1(a) 的缺口），但它**不受本地覆盖率审计与质量门约束**，与湖里的口径也未做过一致性对账。

## B7. ChinaScope 细看 —— ✅ **PIT 双时间戳确认存在，且比湖里的财务表更强**

所有包一律"一个 zip 一个 CSV"，**分号 `;` 分隔**（新闻标注是逗号），UTF-8。
以下 schema 均由**流式读取 zip 内前 24 KB**得到，未做整包解压。按授权另解压了 3 个小文件到 `~/genebench_inventory/tmp/`：`dict_industry.csv`(34.8 KB)、`concept_dictionary.csv`(189.8 KB)、`event_dictionary.csv`(298.5 KB)。

### sam_pit v1.0_a（2014Q2 → 2024Q4，10 个包，111 MB 压缩）

**PIT 双时间戳 = `publish_date` + `report_date`，而且同一期会有多条不同 publish_date 的记录。**

`fin_secu_sam_period_pit.csv`（21.0 MB 解压）：
```
operation;id;report_id;secu;publish_date;report_date;p;q;y;fy;currency;valid;company_id;market;create_time;update_time
A;201059;S0000622014-06-302014Q212-3162014-08-27;002054_SZ_EQ;2014-08-27;2014-06-30;6;Q2;2014;12-31;CNY;1;CSF0000000712;1002;...
A;201060;S0000622014-06-302014Q212-3162015-08-29;002054_SZ_EQ;2015-08-29;2014-06-30;6;Q2;2014;12-31;CNY;1;CSF0000000712;1002;...
```
↑ 同一只票、同一个 `report_date=2014-06-30`，分别在 **2014-08-27** 和 **2015-08-29** 各出现一次 → **完整的重述链**。湖里的 tushare 财务表只有 `update_flag` 0/1 两态，做不到这个粒度。`valid` 列还给了有效性标记。

**产品级财务的粒度：公司 × 报告期 × 产品，且带产品树路径与占比。**

`fin_secu_sam_product_pit.csv`（93.8 MB）：
```
operation;id;report_id;secu;report_date;publish_date;product_code;product_cost;product_income;product_profit;company_id;partial_cost;market;create_time;update_time
A;789200;...;002054_SZ_EQ;2014-06-30;2014-08-27;CC0010060404;76085519.86;95902542.77;19817022.91;CSF0000000712;0;1002;...
```

`fin_secu_sam_product_calc_pit.csv`（**470.8 MB 解压**，最大的一个）：
```
operation;id;report_id;secu;report_date;publish_date;income;profit;product_code;product_path;product_level;
product_income;product_income_ratio;product_profit;product_profit_ratio;product_b_income;product_b_income_ratio;
product_b_profit;product_b_profit_ratio;company_id;market;partial_calc;product_partial_calc;create_time;update_time
A;631762;...;300433_SZ_EQ;2014-06-30;2015-08-26;5436436613.7;1324678502.6;EC00102003;EC004>EC001>EC00102001>EC001020>EC00102003;5;5436436613.7;1;1324678502.6;1;...
```
↑ `product_path` 是完整的产品树路径、`product_level` 是层级（实测见到 3 与 5）、`product_*_ratio` 是占比。**这正好补上 `fina_mainbz_vip` 没有公告日、无法 PIT 的缺口**。

**供应链关系表 schema**（`supply_chain_relation.csv`，29.0 MB）：
```
operation;id;primary_code;primary_en;primary;primary_type;related_code;related_product_en;related_product;related_type;relationship;importance;create_time;update_time
A;569378df11c0d21d7cd5edae;AC001;Auto Parts and Equipment;机动车零配件与设备;M;AC005;Automobiles;汽车;P;1;4;2018-12-11 02:38:47;...
A;5693786c11c0d21d7cd5eda1;AC001;Auto Parts and Equipment;机动车零配件与设备;P;CC001;Commodity Chemicals;商品化工;M;-1;2;2018-12-11 02:38:47;...
```
⚠️ **这是产品/行业级的上下游关系，不是公司级的客户-供应商名单**。`relationship` 实测取 `1` / `-1`（上游/下游方向），`importance` 实测取 `4` / `2`（强度分级），`primary_type`/`related_type` 取 `M`/`P`。要落到个股需要经 `dict_product_rs` + `fin_secu_sam_product_*` 两跳映射。

**其余**：`base_stock`(10.3 MB，`code/ticker/orgid/org/abbr/mkt_code/list_status/list_dt/list_edt/csfid`，其中 `list_edt` 就是退市日) · `base_company`(9.3 MB，`company_id/credit_code/company/is_bond_issuer/is_listing`) · `dict_industry`(CSF_ 行业树，`code/name/parent/ancestors/industry_level`) · `dict_product_ind` · `dict_product_rs`(产品树，带中英释义) · `sam_release_notes_tree`(SAM 树版本变更记录，`tree_version/node_operation_type/from_parent_code/to_parent_code`——**产品分类树自身的版本演进**，做长周期 PIT 时必须考虑)

### Smartag v4.2

**四本字典的文件形态：全是 zip 内单个分号分隔 CSV，且都带时间戳字段。**

| 字典 | 解压大小 | 关键字段 |
|---|---|---|
| `concept_dictionary` | 189.8 KB | `code, name, name_en, concept_id, **inclusion_date**, def(中文定义全文), create_time, update_time` |
| `concept_stock` | 6.8 MB | `code(股票), name, concept_code, **inclusion_date**, **delete_date**` ← **概念成分带纳入/剔除双时间戳** |
| `event_dictionary` | 298.5 KB | `code, name, name_en, parent_code, level, pos, importance, inclusion_date, delete_date` ← 层级事件树 |
| `region_dictionary` | 698.2 KB | `code, name, name_en, level, parent_code, ancestors, external_code` ← 层级地域树 |
| `dict_product_rs` | 2.3 MB | 产品树（与 sam_pit 那份同构） |
| `base_stock` | 10.4 MB | 与 sam_pit 的 base_stock 同构 |
| `base_stock.pdf` / `dictionary.pdf` | 各 866 KB | 字段说明文档 |

样例：`('A','CP0001','水利工程','Water Conservancy Project Concept','1','2019-01-17','水利工程是用于控制和调配自然界的地表水和地下水…')`
样例：`('A','000001_SZ_EQ','平安银行','PING AN BANK','CP0233','2019-01-17','',...)`
样例：`('A','A','经营事件','Operations','',1,'','','2019-04-04','',...)` / `('A','AA','利润表','Income Statement','A',2,...)`

**新闻记录的时间戳精度：秒级 + 显式时区。**

`news_company_label_*.csv`（**逗号分隔**，10 列）：
```
stockCode,companyId,chineseName,englishName,newsId,newsTs,relevance,emotionIndicator,emotionWeight,emotionDetail
02318_HK_EQ,CSF0000001741,中国平安,PINGAN-H,779762,2008-02-26T07:39:08+0800,0.275,0,0.64,"{0=0.6362, 1=0.128, 2=0.2357}"
600050_SH_EQ,CSF0000002615,中国联通,China Unicom (Hong Kong) ADR,779762,2008-02-26T07:39:08+0800,0.325,2,0.99,"{0=0.0054, 1=0.0024, 2=0.9922}"
```
→ `newsTs` 形如 `2008-02-26T07:39:08+0800`（**ISO8601，精确到秒，带 +0800**）；一条新闻（同 `newsId`）会关联多只股票，各自有 `relevance`（相关度）；情绪是三分类分布 `emotionDetail` + 主标签 `emotionIndicator` + 置信度 `emotionWeight`。股票码用 `600050_SH_EQ` / `02318_HK_EQ` 格式（**含港股**）。

🔴 **一处上轮漏掉的事实**：这个目录里除了 `news_company_label_*` 还有一整套 **`news_region_label_*`** 系列，而且最新的一个是 `news_region_label_202601010000-202602010000.zip` —— 即 **Smartag 实际覆盖到 2026-02，比包名上的 `20240901` 晚了一年半**。目录里还有一份 `SmarTag<中文名>.xlsx` 说明文件。上一轮报的"2008-01-01 → 2024-09-01"是按包名写的，**应以实际文件为准修正**。

## B8. 策略资产 —— ✅ 有，但规模很小

### (a) 纸面交易台账 —— **这是唯一的"订单/持仓"级资产**

`~/projects/outputs/quant_platform/paper/ledger.sqlite3`（61 KB），四张表：

| 表 | 行数 | 字段 |
|---|---|---|
| `runs` | **11** | `run_id, asof, created_at, status, equity, turnover, simulated_cost, portfolio_return` |
| `targets` | **110** | `run_id, symbol, score, previous_weight, target_weight, delta_weight, reference_close` |
| `positions` | **10** | `symbol, weight, score, reference_close, asof` |
| `meta` | 1 | `('equity', '884621.4660322453')` |

样例：
```
runs:      ('6c18fc51…','2026-07-31','2026-08-02T16:01:28Z','committed', equity=999287.5, turnover=0.475, cost=712.5, ret=0.0)
           ('339404cd…','2026-08-04','2026-08-04T13:32:28Z','committed', equity=966706.35, turnover=0.385, cost=558.14, ret=-0.0320)
targets:   ('6c18fc51…','SZ301165', score=1.2394, prev_w=0.0, target_w=0.095, delta_w=0.095, ref_close=6.4557)
positions: ('SH603259', w=0.095, score=2.0677, ref_close=13.2399, asof='2026-08-26')
```
→ 11 次运行覆盖 **2026-07-31 → 2026-08-26**，10 只等权（0.095）持仓，**有真实的 turnover 与 simulated_cost**。规模小，但结构完整，可以直接当 benchmark 的"提交格式"参考。

### (b) 回测产物 —— **历史上一共只有 2 次 qrun**

- `~/projects/outputs/quant_platform/backtests/` — `mlruns/` 1 个 run（experiment `772817035740617735`）+ `platform_qrun.log`（25 KB），时间 2026-08-02
- `~/projects/outputs/qlib/official_lightgbm_alpha158/` — `mlruns/` 1 个 run（experiment `959345642746215903`）+ `qrun.log`，同为 2026-08-02
- 无常驻 MLflow 后端库（`~/mlruns` / `mlflow.db` 均不存在；集群里有个 `portal/mlflow-relay` pod）

### (c) 历史信号与因子产出

- `~/projects/outputs/quant_platform/factors/{2025-01-01_2026-07-31, 2026-07-01_2026-07-31}`
- `~/projects/outputs/quant_platform/audits/` — 5 份 2026-08-05 的覆盖率审计快照
- `~/projects/outputs/quant_platform/data_health/status.txt`

### (d) ripple —— **两台机器上最完整的"研究→结论"闭环**

- 可运行实现：`~/projects/ripple/ripple/signal.py`（个股级 peer-return 因子，代码里明确处理了 PIT 行业标签的缺失语义——把未知行业映射成 `"\x00"+code` 的唯一占位，避免两只"行业未知"的票被误判成同行业）
- 24 个实验脚本 + `run_all.sh` / `daily.sh`：`mainline_detector · next_hop · intra_industry · group_compare · m3f_placebo · detector_grid · detector_pr · incremental_ic · calibration · label_hygiene · flow_fingerprint · concept_birth_event · cross_industry_split · parallel_ladder · trace_edge · live_detector` 等
- 结构化结果表（带表头，可直接当 ground truth）：
  ```
  h1_topk_by_year.csv     y,kNone,k10,k20,k40
                          2016,0.2090…,0.1719…,0.1867…,0.2019…
  nexthop_by_period.csv   date,y,base_lim,base_big,hit20,big20,hit5,lift20,lift_big20
                          2016-01-08,2016,0.001732,0.002165,0.0,0.0,0.0,0.0,0.0
  ```
- 13 GB 面板缓存在 `~/projects/outputs/ripple/cache/`

### (e) 策略抽象 —— 基本没有

- `~/projects/quant/platform/src/quant_platform` 里**没有** `class *Strategy` / `run_backtest` / `paper_trade` 的命中
- 现成的策略/回测抽象只在 `~/projects/quant/qlib/` 源码树里（qlib 自带的 `backtest/` `strategy/` `workflow/`）
- spectra：`tests/test_s04_backtest_adapter.py` + `docs/workspace-example/portfolio.py`

### (f) finance02 侧

- `~/quant-platform/`（platform 的完整副本，含 `f02run.py`）、`~/deploy-staging/{platform-gitops, spectra}`、`~/platform/`（k8s manifests + helm + credentials）
- `~/git-mirrors/quant-platform.git` + 6 个 `.bundle`（2026-08-06/07 的跨机传输产物）
- **没有独立的策略资产**——都是 01 的副本

---

# C. 待批工单

> 本轮**全部未执行**，仅登记。W0 是本轮意外产生的，其余三条来自上一轮建议。

| 编号 | 事项 | 为什么要做 | 估时 | 风险 |
|---|---|---|---|---|
| ~~**W0**~~ ✅ **已完成（2026-08-30 12:32 UTC）** | 用户执行 `sudo snap remove --purge lxd`，LXD snap 已从 finance02 移除。验证：`snap list` 只剩 core22/core24/snapd，`/var/snap/lxd` 与 `/var/lib/snapd/snaps/lxd_40585.snap` 均已消失，k3s 未受影响（2 节点 Ready，22 Running）。⚠️ **但 `lxd-installer` 包和 `/usr/sbin/lxc` 仍在**——在 finance02 上敲任何 `lxc` 子命令还会再次触发 snap 安装。彻底根除需 `sudo apt remove lxd-installer`（可选）。 | — | 已闭环 | 已完成 |
| **W1** | **挂回两湖之间的 NFS 桥**：finance01 的 `~/mnt/market_lake_f02` 是空目录，11.4 亿行分钟线在 01 上查不到。**R1 更新——挂载地址已确定：用 LAN 的 `192.168.1.219`，不要用 tailscale 地址**（finance02 的导出按客户端 IP 限定为 `192.168.1.48`，走 tailnet 源 IP 不匹配会被拒）；`01→02:2049` 的 LAN 通路实测已 open，**不需要动任何防火墙规则**。挂载参数按既有教训用 `ro,soft,timeo=100,retrans=3`（hard 挂载会在 02 掉线时让回测无限期卡死）。仍待定的只剩一项：02 侧导出当前是 `rw,root_squash`，要不要改回 `ro,all_squash`。 | benchmark 若含日内/分钟级任务，这是硬前置 | **15–20 分钟**（比初版估的 30–45 少，因为防火墙那一半已排除） | 低（降级：只剩导出权限一个决策点） | 来自第一轮 |
| **W2** | **查清 `premium-daily` 的 dataset 集合**为什么漏掉 71 个表（含 `stk_factor_pro` 这张 1076 万行 / 264 列的主力因子表）。入口：`platform/src` 里 `PHASE_DATASETS` 与 premium-daily 服务的实际参数。 | 71 个数据集冻在 2026-08-05/06，benchmark 的"最新数据"任务会全线失真 | 1–2 小时（含一次增量验证跑） | 中：改动会触发大量补数，要挑非交易时段 |
| **W3** | **清理 finance02 的 40 GB 重复副本** `~/market_lake_f02.pre-hdd.20260818T055940Z`（系统盘 84 G 已用里近一半是它）。删前先对 `/data/market_lake_f02` 做一次分区级校验。 | 释放 40 GB 系统盘；执行面要跑任务需要余量 | 15 分钟（校验 30 分钟） | 低，但**不可逆**，必须先验证新副本完整 |
| **W4**（新增，非阻塞） | `prismquant` pod 处于 `Init:CrashLoopBackOff`；`quant-datahub-index-minute-backfill.service` 处于 failed。 | 两者都会污染"集群/管线是健康的"这个假设 | 各 20–30 分钟 | 低 |
| **W5**（R1 新增） | **收紧 tailnet 面的暴露**。三件事各自独立：① tailscale 绕过 ufw，`22 / 111 / 2049 / 10250 / 30810` 对整个 tailnet 敞开——若要收，得用 tailscale ACL（在管理后台配），ufw 里加规则没用；② `DEFAULT_FORWARD_POLICY=ACCEPT` 放行所有 NodePort——改回 DROP 会重新打断 flannel，正解是加定向 FORWARD 规则而不是改回策略；③ finance01 把 `/data`（含 ChinaScope）以 **rw** 导给了 finance02，考虑改 `ro`。 | ufw 规则看起来在管事，实际拦不住 tailnet 侧；benchmark 起 Pod 后 NodePort 会更多 | ① 30 分钟（要动 tailnet ACL，影响所有节点）② 20 分钟 ③ 5 分钟 | 中：①③ 会影响现有连通，改前先确认没人在用 | 来自本轮 R1 |

---

# D. 本轮的取证边界（未做到的部分）

- ~~**`ufw` 规则原文读不到**~~ → **R1 已补**：finance01 的规则原文已读到（见 A.2），并**推翻了初版的机制解释**。**finance02 的 ufw 仍未读**——补它只需一条 `ssh -t ljn@finance02.tail642a54.ts.net 'sudo ufw status numbered'`。
- **绕过 ② 的机制未直接取证**：NodePort 经 DNAT→FORWARD 绕开 ufw INPUT 是根据 `DEFAULT_FORWARD_POLICY=ACCEPT` 加实测连通性推断的，**没有实际抓 iptables 链验证**（要 `sudo iptables -t nat -L PREROUTING -n` 才算实证）。
- **`unzip` 两台都没装**：ChinaScope 的 schema 是用 Python `zipfile` **流式读取每个 zip 的前 24 KB** 得到的，未整包解压。这个方法比解压更轻，结论同样可靠，但**没有验证文件尾部**（例如末行是否完整、是否有多段 header）。
- **848 个 Smartag 新闻包只抽查了 1 个**（2008–2009 那份）；`news_region_label_*` 系列只做了目录级确认，未读 schema。
- **`fin_secu_sam_product_calc_pit`（470 MB 解压）只读了头部**，没有统计它的实际标的数与期数覆盖。
- **`index_weight` 的成分变动率没有实算**（例如"每期平均换多少只"），只确认了它是月末快照。
- 时间盒 45 分钟内完成，未触发降采样。
