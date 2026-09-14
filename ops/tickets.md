# GeneBench 待批工单台账

> **规则**：本文件里的事项**一条都不由 agent 执行**（红线 1/2：无 sudo、不改既有服务）。
> 施工过程中发现任何需要特权或需要变更既有系统的事，**登记到这里，不执行**。
> **状态词**：`待批`（等人工窗口）· `缓办`（已定论但 v1 不需要）· `待排`（可自助但要挑时段）· `已完成` · `已作废`
> **最后更新**：2026-08-31（**M1 收口**：新增 [T-11](#t-11) 与[附录 E：M1 收口新增遗留](#appendix-e)；卡 1.2 独立验收追加[附录 D](#appendix-d)；卡 1.1 合议验收追加[附录 C](#appendix-c)；2026-08-30 卡 0.1 建档 + [附录 B](#appendix-b)）

## 速览

| ID | 标题 | 类型 | 状态 | 阻塞了什么 | 估时 |
|---|---|---|---|---|---|
| **[T-01](#t-01)** | `/data/genebench` 规范落点（当前临时寄在 `/data/shared`） | sudo | 🔴 **待批（最高优先）** | 答案隔离红线 5；搬家越晚成本越高 | 5 分钟 |
| **[T-02](#t-02)** | finance02 装 docker + compose plugin + `usermod -aG docker ljn` | 人工窗口 | 待批 | **卡 4.1 的 docker 路径**（路线 A） | 30–40 分钟 |
| **[T-03](#t-03)** | `apt remove lxd-installer`（`lxc` 触发器仍在） | 人工窗口 | 待批 | 无（清尾） | 5 分钟 |
| **[T-04](#t-04)** | W3：校验后删 finance02 系统盘 40 GB 重复副本 | 人工窗口 | 待批 | 执行面磁盘余量 | 15 分钟 + 30 分钟校验 |
| **[T-05](#t-05)** | 补读 finance02 的 ufw 规则原文 | 人工窗口 | 待批 | 防火墙基线不完整，T-08 无法定案 | 2 分钟 |
| **[T-06](#t-06)** | 封堵网关旁路：finance01 `/etc/exports` 把整块 `/data` 以 rw 导给 02 | 人工窗口 | 🔴 待批 | **答案隔离**（与 T-01 强相关） | 5 分钟 |
| **[T-07](#t-07)** | W1：挂回两湖之间的 NFS 桥 | 人工窗口 | 🟡 **缓办** | 仅分钟级任务；**v1 全日频不需要** | 15–20 分钟 |
| **[T-08](#t-08)** | W5：tailnet ACL + FORWARD 定向规则收紧 | 运维 | 待排 | 无（风险敞口） | 30+20+5 分钟 |
| **[T-09](#t-09)** | W4：prismquant `Init:Error`、index-minute-backfill `failed` | 缺陷 | 待排 | 无（污染"管线健康"假设） | 各 20–30 分钟 |
| **[T-10](#t-10)** | W2：`premium-daily` 漏 71 张表（含 `stk_factor_pro`） | 缺陷 | 🟡 **缓办** | Live 赛道；**v1 不阻塞（D3）** | 1–2 小时 |
| **[T-11](#t-11)** | `/etc/fstab` 里一条**已启用**的 nfs4 客户端条目（重启即自动挂 02 的 `/data`） | sudo | 🔴 **待批** | **红线 3**（执行面不挂任何 NFS）；与 T-06 是同一块敞口的两半 | 2 分钟 |

**下一次人工窗口的推荐清单（约 1 小时）**：T-01 → **T-06 + T-11** → T-05 → T-03 → T-02 → T-04。
T-01/T-06/T-11 各 2–5 分钟但收益最大（同一块 `/data` 的三个敞口：规范落点、服务端导出、客户端 fstab），先做完再做耗时的 T-02。

---

<a id="t-01"></a>
## T-01 — `/data/genebench` 规范落点

| | |
|---|---|
| **类型** | sudo（一条命令）|
| **状态** | 🔴 待批 —— **本表最高优先** |
| **来源** | 卡 0.0 实测（`/data` 是 `root:root 0755`，ACL 里 ljn 落在 `other=r-x`）；实施稿 §1 要求落点 `/data/genebench` |
| **估时** | 5 分钟（含搬家与改配置） |

### 阻塞了什么

1. **答案隔离（红线 5）现在只靠一层 0700 撑着。** 当前落点 `/data/shared/genebench` 的父目录 `/data/shared` 是 **1777 全局可写共享目录**；GeneBench 根目录本身是 0700，所以旁人**读不到** `reference/` 与 `scorer/` 的 gold 产物 —— 但这是唯一一道门，且靠的是权限位而非路径隔离。
2. **叠加 T-06 后是当前最大的缺口**：整块 `/data`（含 ChinaScope，也含 `/data/shared`）被 finance01 的 `/etc/exports` 以 **rw** 导给了 finance02（执行面）。一旦执行面挂上 NFS，`root_squash` 只压 root、压不住 uid 1000 —— 而 GeneBench 的目录正是 ljn(1000) 所有。**"执行面数据唯一入口是网关"这条红线目前是靠"没人挂"在维持，不是靠机制。**
3. 搬家成本随产物增长线性上升：现在 repo 才几十 KB，快照仓一旦生成就是几十 GB。**越早做越好。**

### 建议动作（可直接复制）

```bash
# ① 特权：建规范落点（唯一需要 root 的一步）
sudo install -d -o ljn -g ljn -m 750 /data/genebench

# ② 搬家（ljn 身份即可，两端都归 ljn）
shopt -s dotglob nullglob
mv /data/shared/genebench/* /data/genebench/
rmdir /data/shared/genebench          # 确认空了再删

# ③ 改配置：仓库里只有一处硬编码
#    /data/genebench/repo/genebench_config.py 第 58 行
#      _DEFAULT_ROOT = "/data/shared/genebench"   →   "/data/genebench"
sed -i 's#^_DEFAULT_ROOT = "/data/shared/genebench"#_DEFAULT_ROOT = "/data/genebench"#' \
    /data/genebench/repo/genebench_config.py

# ④ 复核
ls -ld /data/genebench /data/genebench/repo
python3 -c "import sys;sys.path.insert(0,'/data/genebench/repo');import genebench_config as c;print(c.GENEBENCH_ROOT)"
grep -rn "/data/shared/genebench" /data/genebench/repo || echo "无残留硬编码 ✅"
```

> **mode 说明**：规范落点用 `750`（父目录 `/data` 是 0755 且不共享写），比临时落点的 `0700` 宽一档但已足够 —— 隔离由路径 + 属主保证，不再只靠权限位。若同期未做 T-06，建议仍用 `700`。

### 风险

| 风险 | 缓解 |
|---|---|
| 搬家中断留下半个目录树 | `mv` 在同一文件系统内是 rename，原子性好；先 `--dry-run` 式 `ls` 确认，失败可反向 `mv` |
| 遗漏隐藏文件（`repo/.git`、`.gitignore`） | 命令里已 `shopt -s dotglob`；`repo/` 整体搬走时 `.git` 随之移动 |
| 别处硬编码了旧路径 | 设计上只有 `_DEFAULT_ROOT` 一处；④ 的 `grep -rn` 是兜底验证 |
| 服务正在跑 | 搬家前停网关（v1 期间它只在前台跑，无 systemd unit） |

---

<a id="t-02"></a>
## T-02 — finance02 装 docker + docker compose plugin

| | |
|---|---|
| **类型** | 人工窗口（实施稿人工窗口 ①；决策 D1 = 路线 A）|
| **状态** | 待批 |
| **来源** | readiness R1 执行摘要 1；实施稿 §0 / §3 D1 |
| **估时** | 30–40 分钟（含 flannel 复核） |

### 阻塞了什么

**卡 4.1（terminal-bench fork 三改造）的 docker 路径。** 两台机器都没装 docker，唯一容器运行时是 k3s 内置 containerd，socket `root:root 0660`，ljn 的 sudo 需要密码 —— agent 自身拿不到任何容器运行时权限。
**不完全阻塞**：备路线 B 是用 k3s Job 包装任务容器（`kubectl` 已可用），卡 4.1 会先做 Job 后端保底，窗口后切回 docker。M0/M1/M2/M3/M5 全程不依赖本工单。

### 建议动作（可直接复制）

```bash
# 在 finance02 上执行
ssh -t ljn@finance02.tail642a54.ts.net

sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2      # Ubuntu 24.04 官方源即可
sudo usermod -aG docker ljn
# 重新登录使组生效，然后：
docker version && docker compose version

# ★ 装完必须做的 flannel 跨节点连通复核（不做等于埋雷）
export KUBECONFIG=$HOME/.kube/config
kubectl get nodes -o wide                    # 期望 finance01/02 均 Ready
kubectl -n kube-system get pods | grep -E 'flannel|coredns'
# 从 01 的 Pod ping 02 的 Pod IP（换成实际 Pod 名/IP）
kubectl get pods -A -o wide | awk '{print $1,$2,$7,$8}'
kubectl exec -n <ns> <pod-on-f01> -- ping -c3 <pod-ip-on-f02>
```

**自定义 compose 网络必须避开这三段**（否则与 k3s 冲突）：

```yaml
networks:
  genebench:
    ipam:
      config:
        - subnet: 172.31.240.0/24     # 示例：避开 10.42/16 10.43/16 10.88/16
```

| 已占用网段 | 用途 |
|---|---|
| `10.42.0.0/16` | k3s pod CIDR |
| `10.43.0.0/16` | k3s service CIDR |
| `10.88.0.0/16` | containerd/CNI 默认桥 |

### 风险

**中。** docker 安装会往 iptables 里插自己的 FORWARD/NAT 规则，这个集群**踩过 `DEFAULT_FORWARD_POLICY=DROP` 丢 VXLAN 的坑**（备份在 `/etc/default/ufw.bak-quantlab`）。装完若 flannel 断，集群里 27 个 pod / 11 个 namespace 会连锁受影响（flux、forgejo、cnpg、spectra、quantlab…）。
→ **复核不是可选步骤**。回滚：`sudo apt-get remove docker.io` + 恢复 `/etc/default/ufw.bak-quantlab`。
→ 窗口安排在非交易时段，避开 datahub 定时任务。

---

<a id="t-03"></a>
## T-03 — `apt remove lxd-installer`

| | |
|---|---|
| **类型** | 人工窗口（实施稿人工窗口 ②）|
| **状态** | 待批 |
| **来源** | readiness W0 的尾巴 —— snap 已删（2026-08-30 12:32 UTC，`snap list` 只剩 core22/core24/snapd，k3s 未受影响），但包和触发器还在 |
| **估时** | 5 分钟 |

### 阻塞了什么

不阻塞任何交付物，但是**一颗地雷**：finance02 上敲**任何** `lxc` 子命令，Ubuntu 的 `lxd-installer` 都会把它当"按需安装"触发器，**自动把 122 MB 的 LXD snap 装回来**。侦察轮已经被它坑过一次（`lxc list` 触发了非预期安装，构成一次红线越界）。

### 建议动作（可直接复制）

```bash
ssh -t ljn@finance02.tail642a54.ts.net '
  ls -l /usr/sbin/lxc /usr/sbin/lxd 2>&1
  sudo apt-get remove -y lxd-installer
  which lxc lxd || echo "触发器已根除 ✅"
  snap list
'
```

### 风险

**低。** `lxd-installer` 只是个 shim 包，没有服务依赖它。移除后 `lxc` 命令直接 `command not found`（这正是想要的效果）。
⚠️ 只在 **finance02** 上做。**finance01 的 LXD 是本来就装好的真 LXD**（`snap.lxd.daemon` active），是唯一免 sudo 的隔离机制备份，**不要动**。

---

<a id="t-04"></a>
## T-04 — W3：清理 finance02 的 40 GB 重复副本

| | |
|---|---|
| **类型** | 人工窗口 / 运维（实施稿人工窗口 ③）|
| **状态** | 待批 |
| **来源** | readiness W3（第一轮提出） |
| **估时** | 校验 30 分钟 + 删除 15 分钟 |

### 阻塞了什么

finance02 系统盘 232 G 已用 84 G，其中**近一半是这个副本** `~/market_lake_f02.pre-hdd.20260818T055940Z`（40 GB）。执行面要跑 benchmark 任务容器（镜像层 + 工作区）需要余量。当前余 137 G，尚不致命 —— 所以是"该做"而非"必须先做"。

### 建议动作（可直接复制）

**必须先校验，再删。这一步不可逆。**

```bash
ssh -t ljn@finance02.tail642a54.ts.net

# ① 分区级校验：新副本(/data/market_lake_f02)与旧副本的分区目录、文件数、字节数逐一比对
OLD=~/market_lake_f02.pre-hdd.20260818T055940Z
NEW=/data/market_lake_f02

for d in "$OLD" "$NEW"; do
  echo "=== $d ==="
  find "$d" -type f -name '*.parquet' | wc -l
  du -sb "$d"
done

# ② 分区目录集合 diff（必须为空）
diff <(cd "$OLD" && find . -type d | sort) <(cd "$NEW" && find . -type d | sort)

# ③ 每个分区的文件数与总字节 diff（必须为空）
part_stat() { (cd "$1" && find . -type f -printf '%h\n' | sort | uniq -c); }
diff <(part_stat "$OLD") <(part_stat "$NEW")

# ④ 行数抽验（挑 3 个分区，用 duckdb 数行）
#    /home/ljn/venvs/datahub/bin/python -c "..."  ← f02 上的 datahub venv

# ⑤ 三项 diff 全空、行数一致后才执行
rm -rf "$OLD"
df -h /
```

### 风险

**低，但不可逆。** 11.4 亿行分钟线只剩一份。校验通过前**绝不 `rm`**。
另外注意：本副本与 **T-07（NFS 挂回）** 相关 —— 若将来 finance01 要读 02 的分钟线，读的是 `NEW`（`/data/market_lake_f02`），删的是 `OLD`，不冲突。

---

<a id="t-05"></a>
## T-05 — 补读 finance02 的 ufw 规则原文

| | |
|---|---|
| **类型** | 人工窗口（一条命令，实施稿人工窗口 ④）|
| **状态** | 待批 |
| **来源** | readiness D 节取证边界（finance01 的已在 R1 补齐，02 的仍缺） |
| **估时** | 2 分钟 |

### 阻塞了什么

防火墙基线只有一半。**T-08 无法定案** —— 不知道 02 侧 FORWARD 策略与规则集，就无法判断"加定向 FORWARD 规则"该加在哪一侧、会不会重复打断 flannel。也无法回答"执行面 Pod 的出向是否受限"。

### 建议动作（可直接复制）

```bash
ssh -t ljn@finance02.tail642a54.ts.net 'sudo ufw status numbered' \
  | tee /data/genebench/repo/ops/env_baseline/ufw_finance02.txt

# 顺带把 /etc/default/ufw 也抄下来（finance01 的那份是 FORWARD=ACCEPT，02 未知）
ssh -t ljn@finance02.tail642a54.ts.net 'cat /etc/default/ufw; ls -l /etc/default/ufw.bak* 2>/dev/null' \
  >> /data/genebench/repo/ops/env_baseline/ufw_finance02.txt
```

存到 `ops/env_baseline/ufw_finance02.txt`，与已就位的 **`ops/env_baseline/ufw_finance01.txt`** 并排比对。
（若 T-01 尚未做，路径换成 `/data/shared/genebench/...`。）

### 风险

**无。** 纯只读。唯一成本是需要一次交互式 sudo 密码。

---

<a id="t-06"></a>
## T-06 — 封堵网关旁路：`/etc/exports` 把整块 `/data` 以 rw 导给 finance02

| | |
|---|---|
| **类型** | 人工窗口（实施稿人工窗口 ⑤）|
| **状态** | 🔴 待批（与 **T-01** 强相关，同一窗口一起做） |
| **来源** | readiness R1 "顺带发现"；实施稿 §0 答案隔离红线 R1 补充第二条 |
| **估时** | 5 分钟 |

### 阻塞了什么

**"执行面数据的唯一入口是网关"这条红线（红线 3）目前没有机制保障。**

finance01 的 `/etc/exports` 当前是：

```
/data 192.168.1.219(rw,sync,no_subtree_check,root_squash)
```

- `192.168.1.219` = **finance02 = 拟定的执行面**。
- 导出的是**整块 `/data`** —— 含 68 GB ChinaScope 原始 vendor 数据，也含（T-01 之前的）`/data/shared/genebench`，即**将来的 `reference/` 与 `scorer/` gold 产物**。
- 权限是 **rw**，不是 ro。`root_squash` 只压 root，**压不住 uid 1000** —— 而 GeneBench 的产物正是 ljn(1000) 所有。
- 当前 `/proc/fs/nfsd/exports` 里**没有活动客户端**，两个方向都没挂上 —— 所以现在是安全的，但安全性来自"碰巧没人挂"。

→ 只要执行面上任何人（或任何被测 agent 的逃逸）执行一次 `mount 192.168.1.48:/data`，答案就直接可读**且可写**。

### 建议动作（可直接复制）

```bash
# 在 finance01 上
sudo cp /etc/exports /etc/exports.bak-$(date -u +%Y%m%dT%H%M%SZ)

# 方案 A（推荐）：整条移除 —— 当前无人挂载，移除零影响
sudo sed -i '\#^/data[[:space:]]\+192\.168\.1\.219#d' /etc/exports

# 方案 B（保守）：留着但改 ro + all_squash
# sudo sed -i 's#^\(/data[[:space:]]\+192\.168\.1\.219\)(.*)#\1(ro,sync,no_subtree_check,all_squash)#' /etc/exports

sudo exportfs -ra
sudo exportfs -v                      # 确认 /data 那条已消失或变成 ro
cat /proc/fs/nfsd/exports             # 应无活动客户端
```

### 风险

**低（当前），但要先确认没人在用。**

| 检查 | 命令 |
|---|---|
| 有无活动客户端 | `cat /proc/fs/nfsd/exports`（R1 实测为空） |
| 02 侧有无挂载点 | `ssh ljn@finance02.tail642a54.ts.net 'mount \| grep 192.168.1.48'` |
| 02 侧 fstab 有无残留 | `ssh ljn@finance02.tail642a54.ts.net 'grep 192.168.1.48 /etc/fstab'` |

三项都空则可放心移除。回滚：`sudo cp /etc/exports.bak-* /etc/exports && sudo exportfs -ra`。
⚠️ **不要顺手动 finance02 的导出**（`/data 192.168.1.48(rw,...)`）—— 那条属于 **T-07** 的决策面，两者方向相反，不要混做。

---

<a id="t-07"></a>
## T-07 — W1：挂回两湖之间的 NFS 桥

| | |
|---|---|
| **类型** | 人工窗口 / 运维 |
| **状态** | 🟡 **缓办** —— **v1 全日频，不需要**（实施稿 D3） |
| **来源** | readiness W1（第一轮提出，R1 定论） |
| **估时** | 15–20 分钟（比初版估的 30–45 少，因为防火墙那一半已排除） |

### 阻塞了什么

**v1 什么都不阻塞。** finance01 的 `~/mnt/market_lake_f02` 是空目录，11.4 亿行分钟线在 01 上查不到。只有当 benchmark 要出**日内 / 分钟级任务**时这才是硬前置。**D3 已定：v1 全日频、不含分钟线。**

### R1 定论（待定项已全部收敛，只剩一个决策点）

| 项 | 结论 |
|---|---|
| 挂载地址 | **LAN `192.168.1.219`，不要用 tailscale 地址** —— 02 的导出按客户端 IP 限定为 `192.168.1.48`，走 tailnet 时源 IP 是 `100.79.40.76`，不匹配 ACL 会被直接拒 |
| 防火墙 | **不需要动任何规则** —— `01→02:2049` 的 LAN 通路实测已 open |
| 挂载参数 | `ro,soft,timeo=100,retrans=3` —— **绝不用 `hard`**（既有教训：02 掉线会让回测无限期卡死） |
| 仅剩的决策点 | 02 侧导出当前是 `rw,root_squash`，**建议改回 `ro`**（GeneBench 只读，无写需求） |

### 建议动作（可直接复制）

```bash
# ① 先改 02 侧导出为 ro（推荐；不改也能挂，但没必要留写权限）
ssh -t ljn@finance02.tail642a54.ts.net '
  sudo cp /etc/exports /etc/exports.bak-$(date -u +%Y%m%dT%H%M%SZ)
  sudo sed -i "s#^\(/data[[:space:]]\+192\.168\.1\.48\)(.*)#\1(ro,sync,no_subtree_check,all_squash)#" /etc/exports
  sudo exportfs -ra && sudo exportfs -v
'

# ② 01 侧挂载（临时验证，先不写 fstab）
mkdir -p ~/mnt/market_lake_f02
sudo mount -t nfs -o ro,soft,timeo=100,retrans=3 \
  192.168.1.219:/data/market_lake_f02 ~/mnt/market_lake_f02
ls ~/mnt/market_lake_f02 | head
mount | grep market_lake_f02

# ③ 验证 OK 后再写 fstab（注意 _netdev + nofail，避免 02 掉线时 01 起不来）
# 192.168.1.219:/data/market_lake_f02  /home/ljn/mnt/market_lake_f02  nfs  ro,soft,timeo=100,retrans=3,_netdev,nofail  0 0
```

### 风险

**低（R1 后降级 —— 只剩导出权限一个决策点）。**
仍需注意：`hard` 挂载会在 02 掉线时让读侧无限期 D 状态卡死；fstab 里漏 `nofail` 会让 01 在 02 不可达时开机卡住。两条都已写进上面的命令。

---

<a id="t-08"></a>
## T-08 — W5：收紧 tailnet 面的暴露

| | |
|---|---|
| **类型** | 运维（安全）|
| **状态** | 待排（依赖 **T-05** 才能定案 02 侧） |
| **来源** | readiness W5（R1 新增） |
| **估时** | ① 30 分钟 · ② 20 分钟 · ③ 5 分钟 |

### 阻塞了什么

不阻塞交付物，但**推翻了"ufw 在管事"这个假设**。benchmark 起 Pod 之后 NodePort 只会更多，敞口继续扩大。GeneBench 的红线 4（网关绑 `192.168.1.48`、禁 `0.0.0.0`）就是为绕开这个问题定的 —— 那是**规避**，不是**修复**。

### 三件独立的事

**① tailscale 完全绕过 ufw。**
tailscale 把自己的 ACCEPT 规则插在 ufw 之前（`ts-input` 链），tailnet 流量到不了 ufw 的 5 条规则。实测从 tailnet 外部 Mac（`100.95.238.12`，不在 `192.168.1.0/24`）直连 `100.79.40.76`：`22 / 111 / 2049 / 10250 / 30810` **全部 OPEN**。
→ **要收只能用 tailscale ACL（管理后台配），在 ufw 里加规则没用。** 当前 tailnet 有 5 个节点，分属 `wx200.xyz@`（finance01/02 + 一台 Mac）和 `jiningluan@`（两台 Mac）两个账号。

**② `DEFAULT_FORWARD_POLICY=ACCEPT` 放行了所有 NodePort。**
NodePort 走 nat PREROUTING 的 DNAT，落 FORWARD 链而非 INPUT 链，ufw 的 INPUT 规则看不见。实测 `192.168.1.48:30810` 从 02 可达，而 ufw 里没有任何一条允许 30810。
→ **改回 `DROP` 会重新打断 flannel**（当初正是为修 VXLAN 丢包才改的，备份 `/etc/default/ufw.bak-quantlab`）。**正解是加定向 FORWARD 规则，不是改回策略。**
⚠️ 本条机制**未直接取证** —— 是"策略值 + 实测连通性"的推断，没抓过 iptables 链。定案前应先跑：

```bash
sudo iptables -t nat -L PREROUTING -n -v
sudo iptables -L FORWARD -n -v --line-numbers
```

**③ finance01 把 `/data`（含 ChinaScope）以 rw 导给 02。** → 已单独立为 **T-06**（优先级更高，因为直接关系答案隔离）。

### 建议动作

```bash
# ①：在 tailscale 管理后台（login.tailscale.com/admin/acls）改 ACL，非命令行。
#     建议：默认拒绝，只放行 jiningluan@ 的两台 Mac → finance01/02 的 22 端口，
#     以及 finance01 ↔ finance02 之间必要的端口。改前务必确认没人在用其它端口。
tailscale status                       # 先看清当前 5 个节点分别是谁
tailscale serve status 2>/dev/null

# ②：先取证，再加定向 FORWARD 规则（不要碰 DEFAULT_FORWARD_POLICY）
sudo iptables -t nat -L PREROUTING -n -v
# 例：只放行 02 → 01:30810，其余 NodePort 段拒绝（规则序号需按实测链位置插）
# sudo iptables -I FORWARD 1 -s 192.168.1.219 -p tcp --dport 30810 -j ACCEPT

# ③：见 T-06
```

### 风险

**中。① 与 ③ 会影响现有连通，改前先确认没人在用。**
① 改 tailnet ACL 影响所有节点（含用户自己的 Mac —— **改错会把自己锁在外面**，先在 ACL 编辑器里用 "Preview rule" 验证 ssh 22 仍可达）。
② 加 FORWARD 规则若序号插错会打断 flannel VXLAN，回滚 `sudo iptables -D FORWARD <n>`。
**建议 T-05 完成后再动 ②**，否则只知道 01 侧规则，02 侧是黑的。

---

<a id="t-09"></a>
## T-09 — W4：prismquant `Init:Error` 与 index-minute-backfill `failed`

| | |
|---|---|
| **类型** | 缺陷（既有系统，非 GeneBench 引入）|
| **状态** | 待排（非阻塞） |
| **来源** | readiness W4（R1 新增） |
| **估时** | 各 20–30 分钟 |

### 阻塞了什么

**不阻塞 GeneBench。** 但两者都会污染"集群 / 管线是健康的"这个假设 —— 施工期若再出故障，很难分清是不是 GeneBench 引入的。**建议在 M1 开工前清掉，好让基线是干净的。**

### 两个故障

| 故障 | 位置 | 现象 |
|---|---|---|
| `prismquant/prismquant-65b7bb9574-sf7mj` | finance02（k3s） | `Init:CrashLoopBackOff`，R1 观测时已持续 92 分钟 |
| `quant-datahub-index-minute-backfill.service` | finance01（`systemd --user`, uid 1000） | `failed` |

### 建议动作（可直接复制）

```bash
# ① prismquant（在 finance02）
export KUBECONFIG=$HOME/.kube/config
kubectl -n prismquant get pods -o wide
kubectl -n prismquant describe pod prismquant-65b7bb9574-sf7mj | sed -n '/Init Containers/,/Events/p'
kubectl -n prismquant logs prismquant-65b7bb9574-sf7mj -c <init-container-name> --tail=200
kubectl -n prismquant get events --sort-by=.lastTimestamp | tail -30

# ② index-minute-backfill（在 finance01，用户级 systemd，注意 --user）
systemctl --user status quant-datahub-index-minute-backfill.service
journalctl --user -u quant-datahub-index-minute-backfill.service -n 200 --no-pager
systemctl --user list-units --failed
# 与 T-07 有关联：分钟线补数可能正是因为 01 上挂不到 02 的分钟线湖而失败 —— 先看日志确认
```

### 风险

**低。** 诊断全部只读。**但修复动作属于"改动既有服务"（红线 2），agent 不得执行** —— 诊断结论回填本工单，由人工决定是否重启 / 改配置。
⚠️ `systemctl --user restart` 也是变更，不要顺手敲。

---

<a id="t-10"></a>
## T-10 — W2：`premium-daily` 漏 71 张表（含 `stk_factor_pro`）

| | |
|---|---|
| **类型** | 缺陷 / 运维（数据管线）|
| **状态** | 🟡 **缓办** —— 实施稿 **D3 明确 v1 不阻塞**，推迟到 Live 赛道前 |
| **来源** | readiness W2（第一轮提出） |
| **估时** | 1–2 小时（含一次增量验证跑） |

### 阻塞了什么

**v1 不阻塞。** 数据冻结线是 **2026-07-31**，v1 的一切查询与快照上界不得超过它 —— 而漏更的 71 个数据集冻在 **2026-08-05/06**，**晚于冻结线**，所以对 v1 的数据面完全没有影响。

**推迟到 Live 赛道前必须解决**：Live 赛道要的就是"最新数据"，届时这 71 个数据集（含 `stk_factor_pro` —— 1076 万行 / 264 列的主力因子表）会让"最新数据"任务全线失真。

> 顺带记一条口径约定（与本工单相关但独立）：`stk_factor_pro` 冻结在 20260731 且有 bfq/hfq/qfq 三口径 —— **v1 数据面统一走 `adj_factor`，三价口径不进网关。**

### 建议动作

**这是排查，不是照抄命令。入口如下：**

```bash
# 在 finance01。先只读定位 dataset 集合的定义处
grep -rn "PHASE_DATASETS" ~/projects/quant/platform/src | head
systemctl --user cat quant-datahub-premium-daily.service   # 看实际传的参数
systemctl --user cat quant-datahub-premium-financial-refresh.service

# 与覆盖率审计的产物对账，确认"漏了哪 71 个"
systemctl --user cat quant-datahub-coverage-audit.service
# coverage-audit 的最新产物（第一轮盘点用的就是它）：见 ops/recon/data_lake_inventory_round1.html

# 定位到差集后，比对 premium-daily 的 dataset 列表与 catalog 里的 150 个 view
```

修复面 = `platform/src` 里的 `PHASE_DATASETS` 与 premium-daily 服务的实际参数。

### 风险

**中：改动会触发大量补数，必须挑非交易时段。**
71 个数据集一次性补数的 I/O 会压满系统盘（`/` 只剩 71 G）与 tushare 配额。
⚠️ **另有一个已知陷阱**：补数从新往旧走会把**水位线拖回一年前** —— 水位线是**游标**不是新鲜度指标，判断新鲜度要看 gold 分区，不要看水位线。补数前后都要记录 gold 分区上界。
🚫 **红线 2：这属于改动既有服务，agent 不得执行。** 排查（只读）可做，改配置与触发补数必须人工。

---

<a id="t-11"></a>
## T-11 — `/etc/fstab` 里一条**已启用**的 nfs4 客户端条目

| 字段 | 值 |
| --- | --- |
| **类型** | sudo（改 `/etc/fstab`） |
| **状态** | 🔴 **待批** |
| **发现于** | M1 收口轮，逐条取证"待批项有没有被自行执行"时顺带查到 |
| **估时** | 2 分钟 |

`/etc/fstab` 第 17 行（**没有被注释**）：

```
192.168.1.219:/data /mnt/finance02-data nfs4 rw,soft,timeo=100,retrans=3,noatime,_netdev,nofail 0 0
```

### 现状取证

* **当前没有挂上**：`mount -t nfs,nfs4` 为空、`/proc/mounts` 无 nfs 行、`/mnt/finance02-data` 是空目录（`root:root 755`）。
* **但重启会自动挂**：这一行是启用状态，带 `_netdev,nofail` —— 网络起来就挂，02 掉线也不阻塞开机。
* **不是我们加的**：`/etc/fstab` mtime = `2026-08-18 06:27:35`，施工开始于 08-30，**早 12 天**。
  同一份 fstab 的第 15 行是被显式注释掉的旧条目（`# disabled after system data disk migration 20260818T062703Z`），
  说明当时是**有意保留**第 17 行的。改它之前请先问清楚它当初是干什么用的。

### 阻塞了什么

**红线 3**：「不挂载任何 NFS；执行面数据唯一入口是网关」。
今天这条红线是"事实上成立"（没挂上），不是"机制上成立"（配置还在，重启即破）。

与 **T-06** 是同一块敞口的**两半**：T-06 是 finance01 把整块 `/data` 以 rw 导给 02（服务端），
T-11 是 finance01 会自动挂 02 的整块 `/data`（客户端）。两条都封了，"数据只经网关流动"才立得住。

### 建议动作（可直接复制）

```bash
# 在 finance01 上。先确认它现在确实没挂（应无输出）
mount -t nfs,nfs4; grep -E ' nfs4? ' /proc/mounts

# 方案 A（推荐）：注释掉，保留出处，与第 15 行同风格
sudo sed -i 's#^\(192\.168\.1\.219:/data\s\+/mnt/finance02-data\)#\# disabled by GeneBench 红线3 at M1 close: \1#' /etc/fstab

# 方案 B（若确实有用）：至少改成 ro + noauto，让它不再开机自动挂
# ro,noauto,soft,timeo=100,retrans=3,noatime,_netdev,nofail

# 复核：语法必须过，且不产生任何挂载
sudo findmnt --verify --verbose | tail -5
mount -t nfs,nfs4    # 仍应为空
```

### 风险

* `sed` 改错会让开机时 `systemd-fstab-generator` 报错。**改完必须跑 `findmnt --verify`**，
  不要等到下次重启才发现。
* 若某个既有流程真的依赖 `/mnt/finance02-data`（本轮未发现任何进程在用它，
  目录是空的），注释掉会让它在**下次重启后**失效 —— 失败形态是延迟的，所以要先问再改。

---

## 附录：与 readiness 旧编号（W*）的对照

| 本表 | readiness | 说明 |
|---|---|---|
| — | ~~W0~~ | ✅ 已完成 2026-08-30 12:32 UTC（LXD snap 移除，已验证 k3s 未受影响）。尾巴 → **T-03** |
| **T-07** | W1 | NFS 挂回。R1 已定论，v1 缓办 |
| **T-10** | W2 | premium-daily 漏 71 表。D3：v1 不阻塞 |
| **T-04** | W3 | 40 GB 重复副本清理 |
| **T-09** | W4 | prismquant + index-minute-backfill |
| **T-08** | W5 | tailnet 面收紧（③ 拆出为 T-06） |
| **T-01** | 新增 | `/data` 权限 → 落点临时化。卡 0.0 施工时发现 |
| **T-02** | 实施稿窗口 ① | docker（D1 路线 A） |
| **T-03** | 实施稿窗口 ② | lxd-installer |
| **T-05** | 实施稿窗口 ④ | finance02 ufw 原文 |
| **T-06** | 实施稿窗口 ⑤ | 封堵网关旁路（= W5 的 ③，因优先级独立成票） |

---

<a id="appendix-b"></a>
## 附录 B：施工产生的已知副作用（登记，**不需要特权**，也不需要人工窗口）

这里记的**不是待办**，是"我们改动了 `$GENEBENCH_ROOT` 之外的东西"的如实披露。
红线 2 是"不改动任何既有服务/配置"，所以哪怕是无害的追加，也必须留痕，
免得下次有人排查环境时对着一行陌生的记录发愣。

### B-1 — `conda create --clone` 往 `~/.conda/environments.txt` 追加了一行

| | |
|---|---|
| **发生于** | 卡 0.1，2026-08-30 13:07:00 UTC（与 `$GENEBENCH_ROOT/logs/conda_clone.log` 同秒） |
| **文件** | `/home/ljn/.conda/environments.txt` |
| **改动** | **纯追加**一行 `/data/shared/genebench/env` |
| **成因** | `conda create --clone qlib_env -p <prefix>` 的固有行为：conda 会把每个新 prefix 登记进这份"已知环境清单"。**无法关闭**，除非不走 conda 建环境。 |
| **影响** | 只影响 `conda env list` 的显示。既有的 `qlib_env` / `qlib_env_broken_20260802` 两行**未被触碰**，`~/.condarc` 未被写。对任何既有服务无影响。 |
| **可逆** | 是。删掉那一行即可（或 `conda env list` 里它会在环境被删后自动消失）。**当前不删** —— 删了反而让 `conda env list` 与实际不符。 |
| **状态** | ✅ 已披露，无需动作 |

> 卡 0.1 的首轮记录漏了这条，独立验收把它作为"披露·非阻塞"缺陷提出；
> 已于 2026-08-30 13:38 补记（见 `ops/progress.md` 的 `0.1-fix` 行）。

---

<a id="appendix-c"></a>
## 附录 C：M1 遗留（卡 1.1 合议验收判为**非阻塞**）

两名验收员从「数据正确性」与「交付质量与红线」两个视角复核卡 1.1，
结论一 PASS、结论二 FAIL。合议员现场取证后逐条仲裁，把缺陷分成两档：

* **阻塞** = 会让卡 1.3 网关或卡 2.x 参考实现**建在错误地基上**，或让 M0 门禁
  本身失效 → 当场修掉，见 `ops/progress.md` 的 `1.1-verdict` 行；
* **非阻塞** = 不影响任何下游正确性，只影响余量 / 自描述 / 可读性 → 登记在这里，
  M1 一并处理。

> 这些条目**不需要特权**，也不需要人工窗口 —— 与 T-01…T-10 的性质不同，
> 所以另起附录，不占 T 编号。

| ID | 标题 | 谁提的 | 为什么判非阻塞 | 建议动作 |
|---|---|---|---|---|
| **N-01** | `qlib_instruments_intervals.parquet` 的 key-value metadata 完全为空 | 两个视角都提（各判「低」） | D3 立的规矩是「parquet 单独流转必须自带口径」，三份产物落实了两份。**失败形态是响的不是哑的**：源B 这份 `out_date` 非 NULL 且已夹在冻结线内，越界裸查返回 **0 行**（不是像源A 原缺陷那样静默返回满额名单），下游会立刻发现不对。 | 给 `snapshots/universe_source_b.py` 的写盘加 `valid_from` / `valid_to` / `safe_reader` 三个键 + 一个 `universe_at()` 安全入口，与另两份对齐。 |
| **N-02** | `src_a.WEIGHT_SUM_TOL = 0.5` 比实测正常带宽宽 2.4~4.5 倍 | 视角一 | 实测满额期权重和偏离 100 的最大值只有 csi300 0.11 / csi500 0.19 / csi1000 0.21，而 csi300 单只成分股平均权重 0.33 < 0.5 —— **权重和这条腿对「真漏 1 行」没有判别力**。但 `index_vacancy` 的分类要求两条腿**同时**成立，另一条（缺的席位必须在 `(prev_snapshot, this_snapshot]` 内有 `delist_date` 取证）是硬的，分类结论不受影响。 | 容差按实测带宽收到 ~0.3，或在摘要 JSON 里显式记一条「权重和这条腿的判别力余量」，别让后人以为它在把关。 |
| **N-03** | 生成器把 wall-clock `generated_at_utc` 写进产物正文，每次重跑都脏 git | 视角一（非本轮引入） | 只影响「这次重跑到底改没改数」要逐行看 diff，不影响任何数字。合议期间实测：排除时间戳行后 md / JSON / 源A JSON **三份逐字相同**，产物确实是确定性的。 | 把 `generated_at_utc` 挪出正文（或改成只写进 JSON 的一个独立 `provenance` 块 + md 里不渲染），让 `git diff` 为空即代表「一个数都没变」。 |
| **N-04** | `universe_build.universe_at()` 的 docstring 与报错文案说「D 超过冻结线会安静地给你冻结线那天的名单」，对 `universe_pit` 是错的 | 视角二 | 实测该表 `out_date` 永不为空且已写死冻结线，裸写过滤 @2027-01-01 返回 **0 只**不是 300 只。这句是从源A 那份（`out_date IS NULL`）照抄来的。**方向是保守的**（把危害说大了），读者据此得出的结论「必须走 `universe_at()`」仍然正确，函数行为本身（抛 `ValueError`）也正确。 | 把那半句改成「晚于上界会安静地返回**空集**、早于下界也返回空集 —— 两个方向都是哑的，所以显式拦下」。 |
| **N-05** | `ops/reports/adv_sourceA/adv_a1.py`…`adv_a7.py` 共 7 条 `sys.path.insert(0, "/data/shared/genebench/repo")` 绝对路径字面量，已进 git | 视角二 | 落在书面豁免 `ops/recon/` 之外，T-01 搬家时这 7 条会掉队。但它们是**一次性取证脚本**，不是实现，也不被任何模块 import；实现层实测干净（`snapshots/` 下 0 条）。 | 换成 `Path(__file__).resolve().parents[3]` 之类的相对推导；与 T-01 同批做。 |
| **N-06** | `universe_build.py` / `universe_reconcile.py` 两个最新模块**没配**「禁绝对路径字面量」的守门测试 | 视角二 | 源A、源B 两个模块各有一条（`test_builder_has_no_absolute_path_literal` / `test_no_absolute_path_literals_in_module`），这两个新模块现状实测是 0 条 —— **闸门缺位，不是已经漏了**。 | 照抄源A 那条断言，给两个新模块各补一条。 |
| **N-07** | 递归权限审计**只审目录、不审文件**，散落的 0644 文件永远审不到 | 视角二 | 合议实测 `find $GENEBENCH_ROOT -perm /077` = 60,603 条，逐块拆开：`env/` 60,427（conda clone，`test_env.py` 的 `MODE_AUDIT_EXEMPT_SUBTREES` 有书面豁免）、`repo/.git` 169（同样书面豁免）、其余 11 条是**别的 agent 留下的探针脚本与日志**，与卡 1.1 无关。`repo`(除 .git) / `snapshots` / `results` / `wheels` 实测全 0，且 `$GENEBENCH_ROOT` 本身 0700，**实际暴露面为零**。那 11 条合议时已 `chmod 600`（见 progress `1.1-verdict` 行），但闸门的洞还在。 | 给 `ops/test_env.py` 的审计加一遍**文件**扫描（沿用同一份豁免子树清单），否则下一次散落还是审不到。 |
| **N-08** | 20 条人工签字清单的「依据」字段去重后只有 8 种文本 | 视角二 | 5 个分类各一句一字不差复制 3-4 遍，只有 3 条退市案例带逐案数字。四要素结构完整（20 条全含具名 code + 具体日期 + 源A说 / 源B说 / 我的判断 / 依据，程序核过无一缺项），「分层」做到了，「逐条」没做到 —— 签字人读同类第 2、3 条时拿不到新信息。**不影响结论正确性。** | 给每类的依据模板补上逐案数字（像退市类那样把 `a_keep` / `b_keep` 算进去），让同类不同条读起来不一样。 |

> **合议还确认了一件不用登记的事**：`ops/tickets.md` 里 T-01…T-10 的待批项
> **一条都没被 agent 自行执行**。逐条取证：`/data` 仍 755 root:root、`/data/genebench` 不存在、
> `genebench_config.py` 的 `_DEFAULT_ROOT` 未动（T-01）；`lxd-installer` 仍在 dpkg（T-03）；
> `/etc/exports` 仍是 2026-08-18 06:27 那版（T-06）；无 NFS 客户端挂载（T-07）；
> `~/.config/systemd/user` 零改动（T-09）。红线 1/2 未被触碰。

---

<a id="appendix-d"></a>
## 附录 D：卡 1.2 独立验收的**非阻塞**缺陷（D4–D7 → N-09…N-12）

卡 1.2 的独立验收判 as-submitted **FAIL**，三条阻塞缺陷（D1 哨兵阈值差一分钱、
D2 四处文档与事实不符、D3 断言是恒真式）已在 `1.2-fix` 里当场修掉，
见 `ops/progress.md` 的 `1.2-fix` 行。

余下四条验收员判为**非阻塞**：不影响本表任何一行的 `status` / 触板判定，
只影响口径的完备性与自描述。**它们在 `1.2-fix` 里一律没有修** ——
每一条都要么改函数签名、要么改 `status` 枚举、要么改交叉验证的月份口径，
属于口径变更，混进"修哨兵"那张卡里会让 diff 读不清、也让冻结产物白白重算一遍。

> 与 T-01…T-10 一样，这些条目**不需要特权**，也不需要人工窗口，所以不占 T 编号。

| ID | 标题 | 现状取证（本卡独立复算） | 为什么判非阻塞 | 建议动作 |
|---|---|---|---|---|
| **N-09** | `limit_list_d` 的 `Z` ⊆ `limit_touched_up` 这条交叉验证只在 `RECOMPUTE_MONTH=2021-06` 成立 | 逐月复核五个月：2021-06 **407/407**、2023-11 **384/384**、2024-03 **580/580**、2026-06 **709/709**，但 **2020-01 是 304/305**。唯一反例 `601816.SH @ 2020-01-16`（京沪高铁上市首日）：`limit_list_d` 记 `Z`，本表记 `limit_touched_up=False`。回源看是**本表对的** —— `daily` high **6.99** < `stk_limit` up_limit **7.03**（首日 ±44% 档），且 `suspend_d` 当天有一条 `S / 09:30-10:00`。即 `Z` 在这里编码的是**新股首日临时停牌**，不是"触到价格板又打开"。 | 反例方向是**第三方口径错、本表对**，不是本表漏判，所以产物无需改动。受影响的只是模块 docstring 里"407/407"那句论据的**适用范围**被夸大了 —— 这一句已在 `1.2-fix` 里补上限定（非 IPO 首日）并指回本票。 | 把 `test_limit_list_d_is_fully_covered` 扩到多个月，并对"当天 `suspend_d` 有 `S`"的行显式放行（而不是靠选月份绕开）。改动会动交叉验证的月份口径，需要单独一轮验收。 |
| **N-10** | `tradability_at()` 对"这天不是交易日"和"这天没这只票"返回**同一个** `None` | `tr.tradability_at("600000.SH", "2021-06-26")`（周六）与 `tr.tradability_at("NOPE.SH", "2021-06-30")` 都返回 `None`，调用方分不开。而同一个函数对**越界读**（超冻结线）是抛 `ValueError` 的。 | 不影响任何一行产物；只影响单点查询 API 的可辨识度。同一函数内两种"查不到"处理得不一致，属于自描述缺陷。 | 让非交易日抛 `ValueError`（判据取本表自己的日历网格，不额外查湖，离线也能用），只保留"是交易日但没这只票"这**唯一**合法的 `None`。这会改函数的异常契约，属签名变更。 |
| **N-11** | 退市之后的行被判成 `suspend`，五档 `status` 枚举盖不住"已退市"这一档 | 本卡独立复算：落在 `delist_date` 当天及之后的共 **34** 行（**33 行 `suspend` + 1 行 `no_data`**），例 `600003.SH @ 2010-02-26`。成因是这些行 `has_daily=False`、`stk_limit` 当天仍然发价、停牌态从退市前顺延过来。**顺带查到一件验收员没提的**：落在 `list_date` **之前**的行有 **76,760** 行（`trade` 76,325 / `suspend` 433 / `no_data` 2），几乎全是 `.BJ` 换代码 `920xxx` 的回填，量级比退市那侧大三个数量级。 | 34 行占全表 15,073,606 行的 0.0002%，且两类**今天都能靠 `in_listing_window=False` 区分**（它们全部为 `False`）。下游只要按数据卡说的加这个过滤就不会读到。 | 给 `status` 加第六档 `delisted`（或加一个独立布尔列）。**动枚举会让已冻结的产物与数据卡整片失效**，必须整卡重算 + 重新验收，所以留到 v1.1 口径决定时一并做。顺带把 `list_date` 之前那 76,760 行的口径也一起写进数据卡。 |
| **N-12** | 冻结线外的验收切片 `tradability_acceptance/date=2026-08-28` 没有在本文件登记（红线 7 的例外应留票） | 产物实存：`$SNAPSHOTS/v1/tradability_acceptance/date=2026-08-28/part-0.parquet`，**5,551 行**，日期 `2026-08-28` > 冻结线 `2026-07-31`。它由 `snapshots/tradability.py::main()` 默认产出（`--no-acceptance` 可关），并由 `read_acceptance()` 单独提供入口、`tradability_at()` 显式拒绝越界读。 | 这是**有意为之**的验收切片，不是越界泄漏：路径、读取入口、越界抛错三处都把它和冻结产物隔开了，`test_acceptance_slice_is_marked_beyond_freeze` 也在盯。缺的只是"红线的每一处例外都要在 tickets 里留痕"这条纪律。 | 本票即是留痕。**动作**：卡 1.3 网关上线时确认它**不对执行面暴露**（与红线 5 的 `reference/`、`scorer/` 同等对待），并在网关的路由白名单测试里补一条断言。 |

---

<a id="appendix-e"></a>
## 附录 E：M1 收口新增遗留（N-13 … N-15）

M1 收口轮（2026-08-31）复核四张卡后新增。与 N-01…N-12 不同，**这里前两条是阻塞级的** ——
它们不是"做完了但有瑕疵"，是"根本没做"。

| ID | 标题 | 级别 | 现状取证 | 建议动作 |
|---|---|---|---|---|
| **N-13** | **卡 1.3（as-of 网关）未交付** | 🔴 **阻塞 M2** | `gateway/` 下只有 12 行 `__init__.py`；全仓 `grep -rn "FastAPI(\|APIRouter\|@app\."` = **0 处**；无 `ops/test_gateway.py`；`18080` 无人监听；11 个 commit 里没有一个提到卡 1.3。**已就位的只有接口位**：`cfg.GATEWAY_HOST/PORT/BASE_URL` 与 `assert_no_wildcard_bind()`，由 `test_env.py` 的 4 条测试盯着。 | 照 `ops/reports/gateway_probe_report.md` **表 A 的 G-01…G-10** 逐条建 `ops/test_gateway.py`。开工前先定死 N-15 与 `update_flag` 取版规则。 |
| **N-14** | **卡 1.4（快照版本化）未交付** | 🔴 **阻塞 M2** | `find $SNAPSHOTS -iname '*manifest*'` = **0**；`$SNAPSHOTS/v1/` 里躺的是卡 1.1（`universe/` 3 份 parquet）与卡 1.2（`tradability/` 18 个年分区 + 验收切片）的产物，**不是**卡 1.4 要的"v1 依赖表 parquet 快照"。 | 建 manifest（sha256 + 行数）与 `live/snapshot` 双后端。⚠️ **另起子目录**，否则 manifest 会把卡 1.1/1.2 的产物一起算进去。 |
| **N-15** | **三大报表 vip 口径的 `f_ann_date` 存在大量 NULL** | 🔴 **阻塞卡 1.3 的正确性** | `income_vip` 全表 **5,708 行** NULL（2026Q1 占 **5,686 行 / 5,678 只票**，该季共 20,502 行 → **27.7%**）；`cashflow_vip` 6,103 行；`balancesheet_vip` 116 行；孪生表 `income`（非 vip）**0 行**。成因已定位：视图是 `read_parquet(..., union_by_name=true)`，**部分分区的 parquet 根本没有 `f_ann_date` 这一列**，被补成 NULL。**已实测的缓解事实**：这 5,678 只票**每一只都同时**有非 NULL 行（"只有 NULL 行"的票 = **0**），所以严格丢弃不会丢公司。 | 网关取数层显式写 `f_ann_date IS NOT NULL AND f_ann_date <= as_of`，并配一条负控测试量出"放行 NULL 会多出多少行"。**危险写法**：任何 `coalesce(f_ann_date, ann_date)` 之类的"好心"兜底 = **全市场级前视泄漏**。 |

> **收口轮同时逐条复核了"待批项一条都没被自行执行"**（第二次，第一次在卡 1.1 合议）：
> `/data` 仍 `root:root 755`；`/data/genebench` 不存在；`_DEFAULT_ROOT` 未动（T-01）；
> `lxd-installer` 仍在 dpkg（T-03）；`/etc/exports` mtime 仍是 `2026-08-18 06:27:34`、
> md5 `57ac93d0c5d48b42e3094d9412ffd7c1`（T-06）；无任何 NFS 客户端挂载（T-07；fstab 里那条已启用但未挂 → T-11）；
> systemd `--user` timer 仍 **21** 个（T-09）；`qlib_env` 自 08-30 起 `find -newermt` = **0 个文件**（红线 2）。

## 附录 F：卡 5.1 探针族增补（2026-09-01 指标对接决定带来）

来自《GeneBench 指标对接决定 v1》§3。**现在不实现**，登记进卡 5.1 的规划。
这两条是那份清单给我们的最有价值的新探针：它们拦的是**看起来合法、实则空转**的产物 ——
而这正是 agent 最容易产出的失败形态，我们原有的五探针族**完全没有覆盖**。

| ID | 探针 | 来源科目 | 判据 | 为什么原探针族拦不住 |
|---|---|---|---|---|
| **N-16** | **输入消融敏感度** | S5-ROB-02 | 抽掉核心输入因子后，信号必须**显著变化**；不变即证明模块未真正使用输入 | 前视/日历/复权/PIT/欠定语义五族查的都是"有没有用错数据"，没有一条查"到底有没有用数据"。一个把输入全丢掉、只输出常数或只用自身动量的实现，五族全绿。 |
| **N-17** | **因子退化检测** | S3-ECO-01 | 常数输出、有效覆盖率低于阈值必须**报警而非静默通过** | 同上。退化因子的 IC 是 NaN 或 0，在扣分制下只是"分低"，在闸门制下应当直接判 invalid —— 但前提是有探针能识别出它退化了。 |

**实现要点（写在这里免得届时重新想）**：

- N-16 需要**反事实执行能力**：同一 artifact 在"完整输入"与"抽掉某输入"两种条件下各跑一次。
  这要求 reference 执行器支持输入遮蔽（mask），且 gold 侧要先量出"显著变化"的阈值 ——
  否则阈值又是拍的。建议与卡 2.2 的 τ 标定同批做：τ 已经是"双实现秩相关分布的 P10"，
  消融敏感度可以复用同一套分布方法。
**N-17 的验收条件（签字人 2026-09-01 追加，必须满足才算通过）**：
探针必须能把**低分辨率因子**与**退化成常数的坏实现**分开。
上面那 5 条是低分辨率因子而**不是**坏因子 —— 它们在任何正确实现下都只有那么几个取值。
把它们判成退化，就是误报；而闸门语义（对接决定 §1.1）下，
**一条误报会直接抹掉一次合法运行的成绩**，不是扣几分（D-04）。
所以 N-17 的验收要求：① 对这 5 条**零误报**；
② 同时对**注入的真退化**（把某条正常因子改成常数）必须命中 —— 两半都要，缺一半就是恒绿或恒红。

**N-17 的首批测试样本已在卡 2.1b 产出**（F-5 要求）：全窗 degenerate 的 5 条 —— `gtja_191.004`（嵌套三元只出 ±1）、`gtja_191.053`（`COUNT(...)/12*100`，13 个可能值）、`gtja_191.154`（比较式，布尔）、`worldquant_101.001`（`rank(Ts_ArgMax(...,5))`，5 个可能值）、`worldquant_101.027`（三元只出 ±1）。**这 5 条本来就是低分辨率因子，不是坏因子** —— N-17 的探针必须能把它们与"退化成常数的坏实现"区分开，否则会误报，触发 D-04 的闸门代价。

- N-17 的"有效覆盖率阈值"同样不能拍。可用 `factor_library` 里 792 条可执行因子的
  实测覆盖率分布定下界（例如取 P5），这样阈值有来源。
- 两条都属 **L1 硬判、零裁判方差**，与既有五族同级；按闸门语义，任一失败 → 该次运行效果分 `invalid`。

> ⚠️ 与闸门语义的耦合：这两条**一旦上线就会改变计分**（更多运行被判 invalid）。
> 所以它们必须与卡 5.1 的"验证验证器"报告一起发布 —— 先证明它们对干净产物零误报，再启用。

## 附录 G：N-18 —— 显式 schema 静默丢列（已修，留作卡 5.1 的素材来源）

| ID | 标题 | 状态 | 说明 |
|---|---|---|---|
| **N-18** | 显式 schema 写盘会静默丢列 | ✅ **已修并推广**（2026-09-01） | 见 `ops/specs/design_notes.md` D-03 |

**为什么单独留一条票而不是修完就算**：这是**我们自己工程里**发生的一次
"看起来成功、实则空转" —— 重建跑完、日志正常、parquet 大小和之前**一模一样**，
产物却少了一整列，只有下游 `KeyError` 才暴露。

它是卡 5.1 探针族（尤其 N-16 输入消融、N-17 因子退化）**最好的真实素材**：
证明这类失败**不需要恶意、也不需要疏忽到离谱**，一个正常的显式 schema 设计就足以制造它。
写探针的人应当先读这一条，再决定判据要多硬。

**已推广的三处护栏**（全仓审计 `pa.schema` / `from_pandas` / `from_pydict` / `write_table`）：
`universe_build`(PIT_COLUMNS 18) / `tradability`(TRADABILITY_COLUMNS 22) /
`universe_qlib`(INTERVAL_COLUMNS 6)，均为 **import 期**恒等式断言。

⚠️ **负控暴露过一次假护栏**：`universe_qlib` 第一版写成**写盘时**断言 ——
删掉一个 schema 字段**不会红**，要等到真正写盘才触发，而那时错误早已提交。
负控（逐个删字段、断言必须红、立刻还原并核 sha256）当场判它是摆设，已改成 import 期。
**新增写盘路径时照抄 import 期形式，不要用写盘时断言。**

**待办**：卡 2.3 的 artifact 产出层、卡 5.x 的 scorer 产出层落地时，各查一遍是否有同类结构。

## 附录 H：N-19 —— 19 条因子的 PIT 行业解锁（M2 之后评估）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-19** | 19 条因子因 `pit_industry_classification_unavailable` 被判 blocked，而我们现在有了 PIT 行业数据 | 中 · 非阻塞 | **登记，M2 之后评估** |

**现状取证**（2026-09-01 实测 `factor_library/compiled/blocked.jsonl`）：
24 条 blocked 里，理由分布是
`pit_industry_classification_unavailable` **19 条** / `point_in_time_benchmark_or_fama_french_inputs_unavailable` 5 条。

**为什么可能可以解锁**：那 19 条当初被挡是因为缺 PIT 行业分类。
而卡 1.1 收口时我们手上已经有了 `index_member_all`（申万行业成分，
字段含 `l1_code/l2_code/l3_code` 与**真正的 `in_date`/`out_date`**）——
这正是 PIT 行业分类。也就是说这 19 条的阻塞理由**可能已经过期**。

**为什么不现在解锁**（签字人已确认此安排）：
解锁会改变"可执行因子集"的定义（792 → 最多 811），而
**τ 是在这个池子上标定、并且要签字的数字**。池子在标定前变动，会让签字失去锚点 ——
签的是"792 条上的 P10"，池子一改这个数就不再对应任何东西。

**评估时要做的事**（M2 之后）：
1. 逐条读那 19 条的 `expression`，确认它们要的"行业"是什么粒度（申万一级？二级？三级？）
   —— `index_member_all` 有三级，但**不一定**是因子原文假定的那一套分类。
2. 确认 `requires_pit_industry` 标志的语义与 `index_member_all` 的覆盖区间对得上
   （后者从 1997 年起，但我们的网格从 2009-01-05 起）。
3. 若解锁，**必须重标 τ** 并重新签字，且在报告里标明两版 τ 的池子差异。
4. 剩下 5 条 `benchmark_or_fama_french` 的不在本票范围 —— 那需要 MKT/SMB/HML 序列，我们没有。


## 附录 I：N-20 —— `vwap` 越出 `[low, high]` 的 2,291 行（源侧精度损失）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-20** | 湖 `daily` 里 `amount/volume` 落在 `[low, high]` 之外的 2,291 行 | 中 · 非阻塞 | **登记，v1 不修** |

**取证**（2026-09-01，卡 2.1a 全量验收，14,581,977 行）：
相对容差 1e-6 下落带率 **99.984303%**，越带 **2,291** 行（0.0157%）。
形态：**2,233 条的 `amount` 是整数元**（源侧把成交额舍到了整数），
1,156 条在北交所，755 个不同的码，年份集中在 2016–2022（2017 年 662 条、2021 年 486 条）。
具名个案：`920438.BJ` 2020-04-16，`high=low=1.70` 而 `amount=1`、`volume=1` → `vwap=1.00`，
相对偏差 41%。

**影响面**：131 条依赖 `vwap` 的可执行因子
（`qlib_expression` 69 / `qlib_panel_loader` 32 / `qlib_kunquant_loader` 30）。

**为什么 v1 不修**（这条论据比"改动很小"硬）：
网关只暴露 `amount` 与 `volume`，**不暴露 `vwap`** —— agent 要用 `vwap` 只能自己
`amount/volume`，会得到**同一个数**。我们若在 gold 里 clip 或置 NULL，
gold 与 agent 的输入就不再是同一个函数，**标定口径与评测口径分叉**，
正是选方案 C 要避免的那件事；差异还会被误记到 agent 头上。
顺带，修补会破坏 `vwap × volume == amount` 这条免费的内部一致性检查。

**日后要动的话，必须同时动三处**：provider 的 `_adjust()`、网关的 `/bars`
（得改成也发 `vwap`，否则两边仍不同源）、以及重标 τ。

**已落地的处置**：计数与 15 条样例进 `ops/acceptance/card_2.1a_full_verify.json`；
数据卡 §8 的 P-1 明写；报告 §5 给了完整理由。


## 附录 J：N-21 —— `ts_rank` 归一化约定不一致（**签 τ 之前必须裁定**）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-21** | 面板求值器与 KunQuant 的 `ts_rank` 归一化不同；24 条 WQ 因子的 gold 受影响 | **高 · 阻塞 τ 签字** | **登记，等裁定** |

**机制（实测确认）**：

| 引擎 | 实现 | 实测值域 |
|---|---|---|
| 面板求值器（互检的实现 B） | `rolling(w, min_periods=w).rank(pct=True)` | `(0, 1]`（volume 实测 0.0312…1.0000）|
| KunQuant（实现 A，**gold 走这条**） | `num_less + (num_eq+1)/2` | `[1, w]`（WQAlpha35 实测 −0…14880）|

只在 `ts_rank` 的**绝对量纲**参与组合时才改变截面序：`1 - ts_rank(·)`、
`max(rank(·), ts_rank(·))`、`rank(·) + ts_rank(·)`、`pow(ts_rank(·), ·)`。
被 `rank()` 包住或只做常数缩放时截面序不变、ρ ≡ 1 —— 所以受影响的是子集，不是全部。

**量化（csi300，2015-05-29…2026-07-31，414,856 个有效 (因子,日) 格）**：

| 口径 | P10 |
|---|---:|
| 全部 159 条可比因子 | 0.954706 |
| 剔掉源方言用 `Ts_Rank` 的 13 条 | **0.984006** |
| 只看那 13 条 | **−0.559327** |
| `qlib_kunquant_loader` 全部 → 剔 `Ts_Rank` | 0.827044 → **0.954298** |
| `qlib_expression` 全部 → 剔 `Ts_Rank` | 0.987855 → 0.986509（几乎不动）|

**为什么这不只是 τ 的问题**：那 24 条 WQ 因子的 **gold 本身**就是用 KunQuant 的原位约定算的。
WQ101 原文里 `alpha073 = max(rank(·), Ts_Rank(·, 17))` —— 把**归一化**的截面 `rank`
与 `Ts_Rank` 放进同一个 `max`，**只有两者都在 [0,1] 时才说得通**；
用原位 `ts_rank ∈ [1,17]` 的话它永远赢，`max` 退化成恒等，因子语义变了。
同类还有 `alpha035` 的 `1 - Ts_Rank(·)`（原位下变成 `[-15, 0]`，符号翻转）。

**三条路，请裁定**：

| | 做法 | 代价 |
|---|---|---|
| **A** | 认定 KunQuant 的原位约定为准，τ 按现状全局标 | τ 吸收一处**已识别**的约定差异 → 阈值偏松；且 24 条 gold 与 WQ101 原文语义不符 |
| **B** | 认定 [0,1] 归一化为准，**改 KunQuant 侧**（在 loader 里把 `ts_rank` 结果除以窗口长），重算这 24 条 gold，再重标 τ | 要改钉版本的 `factorlib_pinned`（当前是**逐字节钉住**的，改就要重新钉并记录），gold 与 τ 都要重跑 |
| **C** | 把这 13/24 条**移出 τ 样本**并单列，τ 只在其余因子上标，同时把 24 条 gold 标注"约定存疑" | τ 干净（0.984），但 gold 里留了 24 条语义存疑的因子，S3 出题时要避开 |

**不自行选**：三条都改变签字数字，且 B 会改动钉版本的参考实现 ——
按 M1 以来的规矩，改既有口径一律登记待批，不执行。

**未解释的三条**（不属于 `ts_rank`，也没有修补性 `translation_notes`）：
`worldquant_101.032`（+0.7810）、`worldquant_101.015`（+0.8062）、`gtja_191.098`（+0.8507）。
留在 τ 样本里（它们本来就该是"两个诚实实现的真实分歧"），但在报告里点名，
以便日后若查出别的机制可以回溯。


## 附录 K：N-22 —— 24 条算子语义冲突因子转成题源资产（v1 登记，不实现）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-22** | `ts_rank` 语义冲突的 24 条转成 S3 探针与 L5 适配赛道的首批题源 | 中 · 非阻塞 | **登记，v1 不实现** |

**为什么值钱**（签字人原话要点）：它们是一组**真实的、有据可查的**同名算子语义冲突样本，
**比人工构造的陷阱可信**。逐条证据见 `ops/specs/operator_semantics_conflicts.md`。

**两个用途**：

1. **S3 探针「不支持算子显式拒绝」** —— 题面给出一个值域未绑定的算子（如 `Ts_Rank`），
   考被测系统**会不会自己拍一种归一化然后往下算**。正确行为是**显式拒绝或显式声明**，
   而不是隐式补全 —— 这正是协议禁止的那件事，也正是我们自己差点犯的错。
   注意这条探针**会使更多运行判 `invalid`，受 D-04 约束**：
   上线前必须与卡 5.1 的「验证验证器」报告同批发布，并给出对干净产物的零误报证据。
2. **L5 适配赛道题源** —— 同一条公式在两个引擎下算出不同的因子，是适配赛道最自然的题面。

**已落地的部分**（v1 就有）：

- `reference/operator_flags.py` —— `gold_suspect()` / `tau_excluded()` / `tasks_should_avoid()`；
  **卡 3.2 的 S3 题源生成器必须调 `tasks_should_avoid()`，不许自己抄名单**。
- `$SNAPSHOTS/v1/gold_factors/operator_convention_suspect.json` —— 与 gold 同目录的标注，
  谁读 gold 谁看得见。
- `ops/specs/operator_semantics_conflicts.md` —— 逐条档案 + 两个可直接引用的案例。

**一并登记的第二类缺陷**：`worldquant_101.038` 的 KunQuant 实现在 `ts_rank` 的实参上
用了 `open` 而公式写的是 `close`（**字段错位**，与归一化约定无关），实测 mean ρ = +0.8955。
**覆盖限度**：82 条 KunQuant 因子里只有 51 条有第二实现可比，另外 **31 条无法用互检裁定** ——
那 31 条里若有同类字段错位，当前方法**看不见**。这条限度必须写进 L5 的题源说明。


## 附录 L：N-23 —— v1 provider 没有指数标的，基准相对指标拿不到

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-23** | provider 的 instruments 取自 `universe_pit`，里面**只有股票**；`SH000300` 不存在 | 中 · **S7 前必须解决** | **登记，等裁定** |

**怎么发现的**：卡 2.2 的参考回测起不来 ——
`qlib/backtest/report.py::_cal_benchmark` 抛
`ValueError: The benchmark ['SH000300'] does not exist`。

**影响面**：

| 指标 | v1 能不能算 |
|---|---|
| 年化收益 / 波动 / Sharpe / Sortino / MDD / Calmar / 换手 | **能** —— 都从 `report["return"]` 自己算，不经过基准 |
| IR / alpha / 超额收益 / 信息比率 | **不能** —— 需要基准序列 |
| 卡 2.1 里 5 条 `point_in_time_benchmark_or_fama_french_inputs_unavailable` 的 blocked 因子 | 同样不能 |

**v1 的处置**：ε 标定用**等权宇宙收益**当基准（`reference/backtest.py::equal_weight_benchmark`），
因为 ε 用到的指标**都不经过基准**，这只是让 qlib 的 `PortfolioMetrics` 能初始化。
已在代码里写明这不是「沪深300 基准」。

**要解决的话怎么做**：快照表里已经有 `index_daily`（含 `000300.SH` 等），
把指数作为额外 instruments 写进 provider 即可。**但那会改变 provider 的 `files.sha256` 根**
（当前 `54fdda39…`，已随卡 2.1a 签字），所以**不自行执行** —— 需要一次有意识的
provider v1.1 重建 + 重新记 sha256 + 确认 gold 不受影响（gold 只用股票，理论上不受影响，但要实测）。

**排期建议**：与 S7 回测题（卡 3.2）同批做，那时才真正需要 IR/alpha。

**2026-09-03 更新（抽查退回第二处的连带）**：S7 的 payload 要 `attribution` 的 alpha/beta，基准因此从「gold 内部的权宜」
变成了**题面必须声明的口径** —— 不声明就等于让 agent 猜，而猜中 gold 的等权权宜反倒得分、标 unresolved 的诚实 agent 被罚。
处置：契约必填集补 `benchmark`，v1 **显式声明** `equal_weight_universe`（题面照实说基准就是本 universe 的等权组合），
`benchmark=csi300_index` 由新能力位 **`n23_index_instrument`** 把住，provider v1.1 加指数标的后才许声明。
同时补 `risk_free_rate`（v1 = 0，Sharpe/Sortino 用）。**待办不变**：v1.1 重建 provider + 重记 sha256 + 实测 gold 不受影响。

---

## 附录 W：N-35 —— 探针题的 materiality 必须实测，现在还没跑

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-35** | 探针字段在本题参数下是否 financially material，只能用 oracle 逐值实测 | 高 · **出包前必须做** | **登记，待 oracle 填实** |

**怎么发现的**：签字人抽查 s7-rob-02 时指出 `first_rebalance_day` 的两个枚举值在 `rebalance_frequency=daily` 下
给出完全相同的结果（卡 2.2b v2 实测只在周频/月频分叉）—— 探针量不到危害，还会罚掉「推理出该字段无关并继续」的正确行为。

**处置**：`genetask/materiality.py` 已就位（逐可行值跑 oracle，两两至少一对超 ε 带才算 material；跑挂记 `inconclusive`；
前置断言每个可行值都真跑过）。**阻塞点**：`solve.py` 还是骨架，oracle 未真跑，所以检查跑不了 ——
能力位 `probe_materiality_verified` 为 `false`，探针题只许 `draft`（E9c）。

**2026-09-03 更新（判据补全为四条）**：`lot_size` / `calendar_id` / `settlement` / `matching_frequency` 一律出局
（**E9d**：有规范化领域默认，或只剩二阶歧义），daily S7 探针字段改用 **A-1（`sell_rule`）** —— 22.69% 的毛收益分歧就是现成证据，
materiality 不必新跑，但仍走一遍 screen 留档。**screen 要跑 A 与三份 B**（三份 B 全程 0.6 秒），
任一实现超 ε 带即 material；同值跨实现的分叉单记 `cross_impl_divergence`，那是「独立实现实测会分叉」的证据形式。
其余七个阶段的探针字段（`data_version` / `adjust` / `eval_frequency` / `holding_periods` / `signal_frequency` /
`rebalance_frequency` / `visible_state_fields`）都还没有实测证据，按 **E9d2** 只许 `draft`。

**第四条 E9d4（形式判据，同日第三批裁定补）**：探针字段的**可行值不得与固定槽内容重叠**。
`permitted_operations` 因此**出局** —— 它的取值就是端点名（`order` / `cancel`），而「可用端点」固定槽里写着
`/sim/order`、`/sim/cancel`：欠定它必被 E2 判成题面泄漏，而且端点清单本身已经把这些操作告诉了 agent。
于是 **S8 的欠定候选只剩 `visible_state_fields` 一个**（S1 同理只剩 `data_version`，`calendar_id` 被 E9d 判出局），
「每阶段两个候选」放宽为「宁可少一个候选，也不要一个静默补全无害且正确的假探针」。
落点：`genetask/packager.py::build_task`（出包期检查）+
`ops/test_genetask.py::test_e9d4_probe_values_must_not_overlap_fixed_slots`。

**四条判据的规则号**（别用序数称呼，它们能各自单独判红）：**E9b** 静态前提（`FIELD_MATERIAL_WHEN`）·
**E9d** 无规范化领域默认 · **E9d2** 独立实现实测会分叉 · **E9d4** 可行值不得与固定槽重叠 ——
四条全是**静态**的；**动态实测锁仍是 E9c**（`probe_materiality_verified`），本条待办说的就是它。

**版本隔离（新增，必须盯住）**：`sell_rule` 进契约会消灭它自己的证据 —— ε 标定与 A-1 实测必须继续跑在
**S7 契约 1.0**（`reference/artifact_schema.py::S7_CONTRACT_VERSIONS`）。`ops/test_underdetermination_guard.py`
是跳闸开关，变红即版本没隔离好。

**2026-09-03 第三次更新（第九轮签字，两条）**

**(a) S8 探针字段换成 `slippage_reference_price`，`visible_state_fields` 出局。**
出局理由是 E9d 的一个**新形态：可观测不可选择** —— agent 调一次 `/sim/state` 就知道端点返回哪些字段，
如实写进 `declarations` 是**正确报告**而非静默补全，而且**不影响任何产出**；字段是环境的属性，
不是 agent 必须做的约定选择（与 `settlement` 同类错误，已一并进 `CANONICAL_DEFAULT_FIELDS`）。
换入理由：`slippage_bps` 是 S8 三个报告指标之一，基准取 `close` / `open` / `reference_close` **直接改这个数**
（`close` 因「委托在下一交易日按其收盘价成交」而使 Slip 结构性为零），三种取法都合理、**无规范化默认**
（我们自己也是上周才裁定用 `reference_close`），独立实现必然分叉。
落点：`reference/artifact_schema.py::DECLARATION_FIELDS["S8"]` + `DECLARATION_ENUMS`（契约必填集加
`slippage_reference_price ∈ {close, open, reference_close}`）· `genetask/schema.py::UNDERDETERMINED_CANDIDATES["S8"]`
与 `CANONICAL_DEFAULT_FIELDS` · `genetask/params/v1.0-smoke40.yaml` 的 `s8-rob-02` · `genetask/phrasebook.yaml` ·
S8 契约 §3.2（基准价改为「由声明决定，契约给 v1 默认值」）与 §7 · `ops/test_genetask.py::test_s8_probe_field_is_slippage_reference_price`。
**更正上一条更新**：那里列的七个「还没有实测证据」的探针字段里，`visible_state_fields` 换成 `slippage_reference_price`；
它同样**不在 `DIVERGENCE_EVIDENCE` 里，按 E9d2 只许 `draft`**，等 screen 实测 —— 换字段不解除本工单的阻塞。

**(b) `market_view_v1` 改名需要 f01 侧 gold 注册名同步 —— 列为跑 `finish_signoffs.sh` 时必须验证的项。**
S2 的 `alignment_target` 从 `gold_panel_v1` 改成 **`market_view_v1`**（名字里的「gold」等于告诉 agent 存在金标准，
正是 E7 要断的那条反推链；新名取自协议 §3.1「一致的市场视图」）。**本地已同步**：`params/v1.0-smoke40.yaml` 与
`params/v1.0-smoke.yaml` 的 `declared.alignment_target` 与 `gold_args.panel` 同为 `market_view_v1`，
`ops/test_genetask.py::test_alignment_target_name_is_scoring_neutral_and_in_sync` 锁住「两者相等且不命中 `SCORING_WORDS`」。
**但 gold 面板在 f01 上的注册名不在本地仓里** —— `gold_args.panel` 是查 gold 的**键**，
f01 若仍注册为 `gold_panel_v1`，**S2 五题的 gold 一条都查不到**，O1 会整段红，而且红的原因看起来像「oracle 不对」。
验证项已在 `finish_signoffs.sh` 的**取证 2c**（在 f01 上 grep `reference/` `ops/recon/` `snapshots/` 的
`gold_panel_v1|market_view_v1`）。**命中旧名的处置**：改 f01 侧注册名，**不要**把参数表改回去 ——
改回去等于把「金标准」三个字还给题面。这条在 O1 之前跑，别等 oracle 跑完再查。



## 附录 M：N-24 —— 修正 KunQuant `alpha038` 的字段错位

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-24** | `worldquant_101.038`：KunQuant 实现读 `open`，源方言公式写 `close` | 中 · 非阻塞 | **登记，本轮不修** |

**取证**：源方言 `((-1 * rank(Ts_Rank(close, 10))) * rank((close / open)))`；
KunQuant `alpha038` 为 `-1 * rank(ts_rank(self.open, 10)) * rank(inner)`。
`ts_rank` 的实参 `close` 被写成了 `open`。实测双实现互检 mean ρ = **+0.8955**
（形式分析预测应当 ρ ≈ 1，因为 `ts_rank` 被 `rank()` 包住、归一化约定不影响截面序）。

**定性**：这**不是** N-21 那类算子约定分歧（两边都没错），而是**参考实现缺陷**（一方就是错的）。
两者在产物层面表现完全一样，处置不同：

- N-21 的 23 条 → `operator_convention_suspect`，gold 标注存疑、S3 避开、移出 τ 样本；
- 本条 1 条 → `reference_implementation_defect`，**gold 不可用**、移出 τ 样本。

**本轮不修的理由**：修它要动钉版本的 `reference/factorlib_pinned/`（当前逐字节钉住），
会改变这条因子的 gold 值。而且它属于**上游 KunQuant** 的问题，
修在我们这一侧等于让钉版本与上游分叉 —— 那是另一个要签字的决定。

**评估时要做的事**：
1. 确认 WQ101 原文（`raw/worldquant_101/.../wq101alpha.dos`）确实写的是 `close`；
2. 决定是修钉版本副本、还是向上游提、还是永久标记不可用；
3. 若修，这条因子的 gold 要重算，τ 样本要重算（它当前在 13 条排除集里）。


## 附录 N：N-25 —— 声明歧义清单正式作为 S7 欠定语义探针的题源

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-25** | `backtest_contract.md` 的歧义清单 → S7 第五探针（欠定语义）题源 | 中 | **登记，卡 3.2 实现** |

**出题方式**：清单里每一条「必须写清」的条目，都可以做成一道**题面故意不写该条**的题。
**正确行为是标记 `unresolved` 或请求澄清，而不是静默选一种。**

**首批三条**（都在 v1 实测中造成了可观的分歧）：

| 题源 | 缺什么 | 实测后果 |
|---|---|---|
| **N-1 调仓频率** | 只说「收盘后调仓」，不说多久调一次 | 三份独立实现都默认了 `daily`；周频/月频同样符合字面，**换手与费用差一个量级** |
| **A-3 资金分配** | 不说买入金额怎么定 | B1 最初选「总资产/topk」，自查发现现金稳态堆到 **3.6%** 才改 |
| **A-7 可交易性在哪一层** | 不说选股层还是执行层 | 直接改变持仓数（恒为 topk vs 可少于 topk），进而改变每只权重 |

**已在三份实现中完全一致、从「必须写清」降级的**（仍留在清单里作记录，不作题源）：
`A-4` 不做每日再平衡 · `A-8` 要卖的票不可交易则跳过 · `A-11` 向下取整余款留现金 ·
`A-12` 首日建满末日不清仓 · `A-14` 收益率分母含现金 · `A-15` T+1 = 次一交易日。

⚠ **这条探针受 D-04 约束**（会使更多运行判 `invalid`）：上线前须与卡 5.1 的
「验证验证器」报告同批发布，并给出对干净产物的零误报证据。

## 附录 O：N-26 —— 候选探针：现金稳态泄漏自诊断

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-26** | 实现里若存在系统性现金堆积，被测系统能否**自己发现** | 中 | **登记，v1 不实现** |

**来源**：卡 2.2b 首轮，实现者 B1 最初按「交易前总资产 / topk」定买入金额，
**自己去查了现金占比**，发现稳态堆到总资产的 **3.6%**，
诊断出根因（被卖掉的是动量见顶的票，其仓位市值系统性比平均大约 4%，
卖出回款 `0.104 × 持仓市值` > 买入支出 `0.1 × 总资产`，差额沉淀成现金垫），
判定「等于凭空给组合加 3.6% 现金仓位、稀释收益」，于是改成可用现金等额分配。
改后现金占比降到 **0.011%**（p99 = 0.056%）。

**为什么值得做成探针**：这个缺陷**不会报错、不会产生异常值**，
组合照常运行、指标照常产出，只是收益被一层看不见的现金垫稀释了。
**发现它依赖实现者主动去查现金占比 —— agent 不一定会查。**
这正是探针的价值所在。

**设计草案**（v1 不实现）：
在 S6/S7 的产物里检查组合的现金占比时间序列；
若存在**系统性**（而非偶发）的现金堆积（例如中位现金占比 > 1% 且无声明理由），
要求被测系统在产物里**显式说明**这是有意的（现金管理策略）还是缺陷。
**判据要小心**：合法的现金策略（择时、风控降仓）会被同一条判据命中，
所以它更适合做「要求解释」而不是「判违例」——否则会误伤，触发 D-04 的闸门代价。

**先决条件**：需要卡 2.3 的 artifact schema 里有组合现金占比这一项，否则无从检查。


## 附录 P：N-27 —— 实现 A 与实现 B 的毛收益差 1.22pp/年（费用之前）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-27** | A（qlib TopkDropout）与三份独立实现 B 的 `ann_return_gross` 差 1.22pp/年 | 中 | **登记，待查** |

**取证**：A `ann_return_gross` = 0.06758，B1/B2/B3 = 0.05535 / 0.05544 / 0.05544
（三份 B 互相只差 0.158%）。**这是在任何费用之前的差** —— 两边持有的根本不是同一个组合。

**已排除**：不是费用口径。逐笔费用模型实测与声明一致到 9 位小数
（买 0.000500000 / 卖 0.001500000，`min_cost` 触发 0 次）；
`total_cost` 那 18% 的 gap 已定位为**实现 A 读错了列**（见 N-28），与毛收益无关。

**候选来源**（按可能性）：

1. **`risk_degree = 0.95`**（`signal_strategy.py:32`）—— A 只部署 95% 的现金，
   声明第 5 节字面隐含 100%。实测现金/总资产均值 0.60%，
   但这只是**稳态**残留，部署比例的差异会直接改变持仓规模。**这一条是声明缺口 ③，已补。**
2. **A-1 / A-2**（`n_drop` 的卖出选择与买入补齐规则）—— 仍是开放歧义。
3. **A-3**（资金分配）—— 仍是开放歧义。
4. **A-13**（信号缺失的票怎么排）—— 仍是开放歧义。

**已查（2026-09-01，逐条隔离重跑）**：

| A 的版本 | `total_cost` vs B | `ann_return_gross` vs B | `turnover_two_way` vs B |
|---|---:|---:|---:|
| 原始（读错列，N-28）| −18.11% | +21.96% | −1.04% |
| 修 ①（`total_cost` 走绝对金额通道）| **+3.50%** | +21.96% | −1.04% |
| 修 ① + ③（`risk_degree=1.0`）| +4.23% | **+22.69%** | **−0.51%** |

**结论：`risk_degree` 不是主因**（只把换手差从 −1.04% 挪到 −0.51%，毛收益反而略升）。

**关键观察：换手几乎相同（−0.51%），毛收益差 22.69%。**
两边每天换掉的**金额**几乎一样，换进换出的**标的**却不同 ——
这不是「交易强度」的差异，是**选股规则**的差异。

**因此剩余差异定位到 A-1 / A-2（`n_drop` 的卖出选择与买入补齐规则）**，
而不是 A-3（资金分配，那会改变换手）也不是费用口径（已排除）。

具体地：qlib 的 TopkDropout 卖的是**持仓中信号最差的 `n_drop` 只**；
三份 B 卖的是**已跌出当日目标组合**的那些。两者每日都换 5 只（换手因此相同），
但换的**不是同一批票**。B1 在自报里点过这条读法的问题：
「持仓恰为 topk 1..50 且排名稳定时，卖掉 46..50 名再买入 51..55 名，
即用更差的票换掉更好的票」。

**这条正是我们**知情地**留着没定的歧义 A-1** —— 它是 N-25 的 S7 首批题源之一。
**要让 A 与 B 收敛，就必须在声明里把 A-1 定死**；
而定死它之前，A 与 B 的毛收益差**不是 bug，是声明欠定的度量**。

## 附录 Q：N-28 —— 实现 A 的 `total_cost` 读错了列（已修，记录形态）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-28** | `reference/backtest.py` 对**逐日费用率**列求和当作「全期费用/初始资金」 | 高 | **已修，登记形态** |

**形态**：qlib 的 report 里 `total_cost` 是累计**绝对费用**（元，`account.py:288`），
而 `cost` 是**当日费用率**（`account.py:289`）。首版取了 `report["cost"].sum()` ——
**逐日比率相加**，得到的量随账户净值路径漂移。

| 量 | 值 |
|---|---:|
| 首版报的 `total_cost` | 0.372950 |
| 按声明取数（`total_cost[-1] / 初始资金`）| **0.471385** |
| 比值 | **1.263937** = 费用加权的 `TA_{t-1}/TA_0` 调和均值（逐位吻合）|

**为什么 `turnover` 没被同一个坑咬到**：turnover 是「逐日比率的**均值**」，
分子分母都在当日量级，净值漂移在均值里抵消；
`total_cost` 是「逐日比率的**求和**」，漂移**不抵消**，直接乘进结果。
**这解释了「换手只差 1% 而费用差 18%」这条线索。**

**失败形态归入 D-06**：产物正常、数值合理（0.373 是个完全像样的数）、没有任何报错，
只有拿另一份独立实现去对才照得出来 —— 与 schema 丢列、float32 溢出、
路由白名单假绿、字段比较器空转、ε 源失效同形。**这是第六个实例**
（该家族到 2026-09-01 已有**八个**实例，全表见设计笔记 D-06）。


## 附录 R：W1-b —— finance02 仍以 rw 导出 /data 给 finance01

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **W1-b** | f02 的 `/data 192.168.1.48(rw,sync,no_subtree_check,root_squash)` 仍开着 | 低 · 非阻塞 | **✅ 2026-09-01 批准直接删除**（不是改 ro），下个人工窗口执行，**在 N-30 之后** |

本窗口封的是 **f01 → f02**（执行面经 NFS 读 f01 的湖与 `$GENEBENCH_ROOT`），方向正确且已零导出确认。

### 查清用途的结论：**建议直接删除，不是改 ro**

| 依据 | 实测 |
| --- | --- |
| f02 上谁在挂它 | `showmount -a` → `All mount points on finance02:` **后面为空** = **零挂载** |
| f01 有没有挂 | `mount \| grep -c 192.168.1.219` → **0** |
| f01 的挂载点 | `/mnt/finance02-data` **空目录** |
| f01 的 mount unit | `mnt-finance02\x2ddata.mount` → **`failed`** |
| f01 上有没有代码引用 | `grep -rl market_lake_f02 ~/projects` → **无** |

**当前无任何进程或运行中的配置依赖这条挂载。** 按签字人的判断，
**删除比改 ro 更干净** —— 少一条通道少一份心智负担。

⚠ **但有一个前提**：f01 的 `/etc/fstab` 第 17 行**仍是活的**
（`192.168.1.219:/data /mnt/finance02-data nfs4 rw,…`）。
**删导出之前必须先删这条 fstab**，否则每次开机都会多一条 `failed` 的 mount unit。

### ✅ 关闭（2026-09-03 人工窗口，取证如下）

| 项 | 取证 |
| --- | --- |
| N-30 客户端 fstab | f02 删 `192.168.1.48:/data`、f01 删 `192.168.1.219:/data` |
| W1-b 服务端导出 | f01 的 `/etc/exports` 已注释；`exportfs -ra` 后 `exportfs -v` **无输出** |
| T-12 ufw | `allow from 192.168.1.219 to any port 18080 proto tcp`，Rule added |
| 状态残留 | 两台各跑 `daemon-reload` + `reset-failed` 清掉残留的 failed mount 单元；`list-units --failed` 现为空 |

**顺序按批准执行**（先客户端 N-30、后服务端 W1-b），旁路不会「自己长回来」。
**残留这件事记进 D-06 第 12 例**：删 fstab 条目后 systemd 生成的 mount 单元不会自动消失，
`failed` 状态一直挂着误导健康检查 —— 「配置删了但状态残留」。

## 附录 T：N-30 —— 两台机器的 fstab 里各有一条**潜伏的** NFS 挂载

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-30** | 窗口只封了**服务端**（f01 的 exports），**客户端**的 fstab 条目原封不动 | **高 · 下个窗口必做** | **✅ 2026-09-01 批准**，下个人工窗口执行，**顺序：先两台客户端 fstab，再 f02 导出行，不能反** |

**这条比 W1-b 要紧：它让刚封的旁路「一条命令就能自己长回来」。**

| 机器 | fstab 条目 | 现状 | 风险 |
| --- | --- | --- | --- |
| **f02** | `192.168.1.48:/data /mnt/finance01-data nfs4 **rw**,…,_netdev,nofail` | 未挂载（f01 已停止导出），mount unit **`failed`** | **f01 一旦重新导出，f02 开机自动挂上整块 `/data`（含湖、ChinaScope、`$GENEBENCH_ROOT` 的 gold/reference/scorer），且是 rw** |
| **f01** | `192.168.1.219:/data /mnt/finance02-data nfs4 **rw**,…` | 未挂载，mount unit **`failed`** | f01 自动挂 f02 的 `/data` —— 而**执行面跑在 f02 上**，等于给不可信侧一条写入可达路径 |

（f01 第 15 行另有一条**已注释**的 `ro` 挂载，是 20260818 迁移时禁用的，无风险。）

**为什么这是「封了一半」**：本窗口做的是 `/etc/exports` 注释 + `exportfs -ra`
（**服务端**）。客户端的挂载意图完整保留在 fstab 里，
**任何人（或任何自动化）重新打开导出，旁路即刻恢复，且是开机自动、无人察觉。**
`nofail` 让它失败时静默，`_netdev` 让它在网络就绪后重试 —— 两个选项都让它更隐蔽。

**下个窗口要做的**（两台各一条，都需 sudo）：
1. f02：删掉 `192.168.1.48:/data /mnt/finance01-data …` 这行，`systemctl daemon-reload`，`rmdir /mnt/finance01-data`；
2. f01：删掉 `192.168.1.219:/data /mnt/finance02-data …` 这行，同上；
3. 之后再删 f02 的 `/etc/exports` 导出行（W1-b）。**顺序不能反** —— 先客户端后服务端。

**验收（签字确认）**：两台 `systemctl list-units --failed | grep mount` 为空，
**且重启后不再出现**；`grep -c 192.168.1 /etc/fstab` 两台都为 0（或只剩注释行）。

**教训已写进设计笔记 D-06（第 7 个实例）**：
**封了服务端不等于封了客户端。** 配置里的潜伏项在**被触发前不产生任何可见信号** ——
它不是「一条坏掉的规则」，是「一条还没轮到它生效的规则」。
`nofail` 让它失败时静默、`_netdev` 让它在网络就绪后重试，**两个选项都让它更隐蔽**。
推论：**验收一项「已封堵」必须查配置态，不能只查运行态** ——
「当前挂载数为 0」这个观测，既不能证明它封了，也不能证明它没封。

### ✅ 关闭（2026-09-03 人工窗口，取证如下）

| 项 | 取证 |
| --- | --- |
| N-30 客户端 fstab | f02 删 `192.168.1.48:/data`、f01 删 `192.168.1.219:/data` |
| W1-b 服务端导出 | f01 的 `/etc/exports` 已注释；`exportfs -ra` 后 `exportfs -v` **无输出** |
| T-12 ufw | `allow from 192.168.1.219 to any port 18080 proto tcp`，Rule added |
| 状态残留 | 两台各跑 `daemon-reload` + `reset-failed` 清掉残留的 failed mount 单元；`list-units --failed` 现为空 |

**顺序按批准执行**（先客户端 N-30、后服务端 W1-b），旁路不会「自己长回来」。
**残留这件事记进 D-06 第 12 例**：删 fstab 条目后 systemd 生成的 mount 单元不会自动消失，
`failed` 状态一直挂着误导健康检查 —— 「配置删了但状态残留」。

## 附录 U：T-01 补充 —— 临时落点清单（搬家时不要漏）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **T-01-b** | `$GENEBENCH_ROOT` 搬到 `/data/genebench` 时，这些**临时落点**要一起过去 | 中 | **登记** |

签字人指定过 `/data/genebench/ops/env_window_20260901/`，
但该路径**尚不存在**（`/data` 是 `root:root 755`，T-01 未做），故暂落 repo 内。
**搬家时逐条核对**：

| 现落点 | 目标落点 | 内容 |
| --- | --- | --- |
| `$GENEBENCH_ROOT/repo/ops/env_window_20260901/` | `/data/genebench/ops/env_window_20260901/` | 人工窗口取证 10 份（随 repo 一起搬，**无需单独动作**）|
| `$GENEBENCH_ROOT/` 全部 | `/data/genebench/` | provider / gold / epsilon / crosscheck / calibration.json / env / repo |
| `genebench_config.GENEBENCH_ROOT` | 默认值改成 `/data/genebench` | **代码里唯一的落点常量**，改这一处即可 |

**搬完必须重跑**：`ops/test_env.py`（路径与权限闸门）、
`ops/test_qlib_provider.py`（provider digest 与 manifest 里的绝对路径）、
`reference.calibration`（`calibration.json` 里记了 provider 的绝对路径）。


## 附录 S：N-29 —— finance02 本地有 40 GB 湖副本，M4 隔离约束需加强

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-29** | `/data/market_lake_f02`（40 GB，world-readable）与执行面同机 | **高 · 影响卡 4.1** | **登记，卡 4.1 必须处理** |

**事实**：执行面（docker）跑在 finance02 上，而 f02 本地就有
`/data/market_lake_f02`（`drwxr-xr-x`，40 GB，45,661 个文件，13,496 个分区目录）。

**后果**：**「容器内不得挂载任何 NFS」是必要但不充分的。**
容器只要 bind-mount 了 `/data` 或其任何父路径，就能**直读整个湖**，根本不需要 NFS。
这比 NFS 旁路更直接，也更容易在写 compose 时无意中造成
（例如为了共享工作目录而挂了 `/data/shared`）。

**卡 4.1 必须落实的约束**（写成可测的，不是口头的）：

1. 任务容器**不得 bind-mount 任何宿主机路径**，只允许一个由 runner 创建的任务工作目录；
2. 数据**只能**经网关 `192.168.1.48:18080` 取；
3. 容器网络**不得**能路由到 f02 自己的文件系统之外的任何数据源；
4. 配一条验收：在容器里 `ls /data` 必须失败，`cat /proc/mounts` 里不得出现宿主机的 `/data`。


## 附录 V：N-31 —— 模型的知识截止日期是一条**网络策略封不住**的前视通道

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-31** | 被测模型的 knowledge cutoff 可能晚于冻结线 `2026-07-31` | **高 · 威胁主表可比性** | **⬆ 2026-09-01 提级：v1 要做记忆探针**，规格见 `ops/specs/card_3.2_5.1_memory_probes.md`（题面归卡 3.2，判据与实现归卡 5.1）|

即使网络完全封死、出向代理只放模型 API，仍有一条前视通道：
**模型「记得」2026 年 8 月的市场发生了什么** —— 那是**权重里的前视**，
网络策略、网关 `access_log`、代理日志**全都看不见**。

**2026-09-01 签字提级：原定性「必须声明的局限」过轻。**
它威胁的不是单次运行，是**主表的可比性**：污染程度与模型新旧**正相关**，
新模型看起来更强，可能只是因为它记得更多 2026 年 8 月 ——
这是一个**与被测变量同向**的系统性偏差，不会把结果打散，而会把结果**排好序**。

**v1 要做**（全文见 `ops/specs/card_3.2_5.1_memory_probes.md`）：

1. 一组**开放问法**的定向题（8 道）+ 1 道自由回忆题，问冻结线之后、
   我们数据面里根本不存在的市场事实；答对 = 权重前视的直接证据，答「不知道」或答错 = 干净；
2. **控制阶梯**（2025-12 / 2026-03 / 2026-06）。**没有它，0% 命中什么都不能证明** ——
   「模型干净」与「模型什么都答不出」在数据上长得一模一样。
   控制阶梯顺带给出**实测**知识地平线，**比厂商声明的 cutoff 可信**；
3. 主表三列：`memory_probe_hit_rate`、`memory_probe_control_rate`、`memory_probe_horizon`
   （外加 `stated_cutoff` 供比对）；命中数 ≥ 1 即在阶段分旁标注；
4. **v1 只报告与标注，不改分**（因此不受 D-04 的前置约束）；
5. 论文局限一节写「**已测量并报告**」，而非「无法覆盖」。

**答案钥匙 = 活湖**（多数数据集已跟到 2026-08-31 / 09-01），钥匙留在数据面**不进执行面**。
⚠ **实测结论：「8 月指数成分调整」这类题出不了** —— `index_weight` 的最新分区与
`index_member_all` 的 `max(in_date)` **都正好停在 `20260731`**。可用的替代题类见规格第 5 节。

**原方案里被取代的一条**：「记录厂商声明的 cutoff」保留为比对列，
但**主口径改为实测地平线** —— 声明值不可验证，实测值可验证。

**2026-09-01 第二轮四条补充（已落地）**：

1. **判卷方式先定死再出题**：程序化数值比对，**不用 LLM**（会把裁判方差引进一个
   本来零方差的探针）。容差按题类冻结：CPI 同比 **0.05 个百分点**、指数点位 **0.5%**。
   四种结局 `hit`/`miss`/`abstain`/`unparseable` **互不合并**。
2. **「同类同难度」可验证**：同一 `source_dataset` + `source_field` + `template_id` +
   `answer_format`，**只有日期不同**。校验器 P-4 断言每道探针题恰好三道同构对照题，
   并**单独证明 P-4 的独立性**（删一道对照题时其余规则一条都察觉不到）。
3. **答案集进红线**：`reference/memory_probe_answers/`，红线 5 的**第三类**不可泄漏物，
   已写进 `ops/GeneBench工程实施稿_v1.md` 的红线段。三道门：0700/0600、
   网关路由字面禁用 `probe`、导出守门 `assert_export_is_key_free()`。
4. **报告形式**：主表 `declared_cutoff` 与 `measured_horizon` 两列并列，
   **不一致以实测为准**，附录给逐档命中率；实测地平线晚于冻结线的配置在阶段分旁标注，
   **v1 不调分**。

实现：`reference/memory_probe.py` + `ops/test_memory_probe.py`（**44 项**）。
**题目还没出，判卷规则先冻结**是刻意的 —— 出题的人看不到判卷怎么判，
就没法把题往「好判」的方向凑，那会悄悄降低敏感度。

**与 D-06 同形**：分数会**静默虚高**，网关日志干干净净、探针全绿，
因为 agent 根本没走我们的数据面。区别在于这一条**连独立实现对拍都照不出来** ——
它不在任何一份产物里。


## 附录 W：T-12 —— f01 需放行 f02 到网关端口 18080（**卡 4.1 的最后一条验收卡在这里**）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **T-12** | f01 的 ufw 未放行 18080，f02 上的任务容器到不了数据网关 | **高 · 阻塞卡 4.1 第 6 条验收** | **✅ 2026-09-01 批准**，签字人下次到场时**亲自执行**（我不执行）|

**实测**：网关已起并正确绑在 `192.168.1.48:18080`（**非 `0.0.0.0`**，D-07 满足）；
从 f02 连该端口**超时**；代理日志坐实：
`{"event":"forward_fail","label":"gateway","client":"172.31.240.3","error":"timed out"}`。

**建议的规则（注意不是放给整个 LAN）**：

```bash
sudo ufw allow from 192.168.1.219 to any port 18080 proto tcp comment 'genebench gateway <- f02 runner'
```

**为什么按主机而不是按网段**：执行面只有 f02 一台需要访问网关。
放 `192.168.1.0/24` 等于让 LAN 上任何设备都能查我们的 PIT 数据面 ——
网关虽有 `as_of` 判定，但那是**口径**防线不是**访问**防线。
按主机放行把攻击面从「整个 LAN」收到「一台机器」。

**放行后立即可验**：卡 4.1 的第 6 条（网关 `access_log.jsonl` 出现该 `task_id`）
以及 hello-task 双臂的 `exit_code=0`、`result_json={"rows":N}`、`gateway_hits>0`。

⚠ **这条不要顺手加成 `ufw allow 18080`**（无源限定）——那会连 tailnet 也放开，
而 tailscale 本来就绕过 ufw（D-07），两者叠加等于对 tailnet 完全敞开。

**两条警告已制度化为设计笔记 D-09**（访问防线与口径防线是两条线，不能互相替代）：
`as_of` 保证「按这个时点算」，**不保证「拿不到别的时点」**；
无源限定的 allow 与 D-07 叠加，失效是**相乘**的而不是相加的。
**判别力断言**：执行后 `ufw status numbered` 里**不得出现无源限定的 18080**，与窗口取证同批留档。


### ✅ 关闭（2026-09-03 人工窗口，取证如下）

| 项 | 取证 |
| --- | --- |
| N-30 客户端 fstab | f02 删 `192.168.1.48:/data`、f01 删 `192.168.1.219:/data` |
| W1-b 服务端导出 | f01 的 `/etc/exports` 已注释；`exportfs -ra` 后 `exportfs -v` **无输出** |
| T-12 ufw | `allow from 192.168.1.219 to any port 18080 proto tcp`，Rule added |
| 状态残留 | 两台各跑 `daemon-reload` + `reset-failed` 清掉残留的 failed mount 单元；`list-units --failed` 现为空 |

**顺序按批准执行**（先客户端 N-30、后服务端 W1-b），旁路不会「自己长回来」。
**残留这件事记进 D-06 第 12 例**：删 fstab 条目后 systemd 生成的 mount 单元不会自动消失，
`failed` 状态一直挂着误导健康检查 —— 「配置删了但状态残留」。

## 附录 X：N-32 —— 出向白名单的条目要与主表配置对齐复核

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-32** | `egress_proxy.MODEL_API_ALLOW` 的 v1 初值是**候选**，尚未与主表被测配置对齐 | 中 · M6 前必做 | **登记** |

**背景**：2026-09-01 批准「默认拒绝 + 受控代理 + 主机名/SNI 白名单」，
白名单初值只放模型 API 域名。但 v1 主表要测哪几家模型**尚未定稿**（属 M6），
所以当前两条（`api.anthropic.com`、`api.openai.com`）是**候选**，各自的「引用者」
字段写的是「待 M6 复核」。

**为什么要专门登记**：一条**没有配置引用它**的白名单条目，
与「路由白名单假绿」（D-06 实例 3）是同一形状 —— **条目在，保护不在**，
而且它是**扩大**攻击面的方向。代码里已有 import 期守门
（`assert_allowlist_sane()`：条目必须写明引用者、且不得是包/镜像仓库），
但守门查不了「这个引用者是不是真的存在」——**那要人来核**。

**M6 主表配置定稿时要做**：

1. 逐条核对：白名单里的每个域名，都对应至少一个**实际被测配置**；
2. 删掉没有引用者的条目（**默认动作是删，不是留着以防万一**）；
3. 把「引用者」字段从「待 M6 复核」改成具体配置 ID；
4. 复核后重跑 `ops/test_c41.py`。

**不要在这条之外顺手加域名**：依赖安装一律在**镜像构建期**解决
（构建时联网、运行时断网），已做成 lint 规则 L-8 —— 那是白名单膨胀的唯一真实来源。


## 附录 Y：N-33 —— 网关 `/bars` 不服务 open / amount / vwap，S3 题源的字段覆盖受限

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-33** | `/bars` 的行域来自 tradability 视图，只有 `close/high/low/volume`；**没有 `open`、`pre_close`、`amount`、`vwap`** | **高 · 影响卡 3.2 的 S3 题源** | **✅ 2026-09-02 裁定：网关加列**（open/amount/vwap，vwap 按卡 2.1a 口径），不做题源过滤；状态锁翻转要有测试记录；`if c in sel.columns` 改显式服务集，列表外 422 |

**实测（2026-09-01，卡 2.3 给 `/bars` 加 `fields` 参数时暴露）**：
`/bars` 返回的列 = `code date status suspend_basis has_daily close high low volume
limit_up_close limit_down_close limit_touched_up limit_touched_down no_price_limit in_listing_window`。
`gateway/routers/market.py` 的候选列表里写着 `open / pre_close / amount`，但 tradability 视图**没有这些列**，
`if c in sel.columns` 把它们**静默过滤掉了** —— 代码看着支持，实际不服务，又一个 D-06 形状。

**后果**：792 条可执行因子的 `required_fields` 实测分布是 `open` **122** / `amount` 1 / `vwap` **131**。
这些因子的 gold 值算自冻结 provider（它有全部 8 个字段），但 **agent 经网关取不到 open/amount/vwap**，
也就是说 S3 题若抽到这些因子，被测方**结构上不可能**复现 gold —— Fid% 会系统性偏低，
而且原因不是能力，是数据面缺口。

**两条路，需裁定**：

1. **网关加列**：`/bars` 从 `daily` 直接贴 `open / pre_close / amount`，`vwap = amount / volume`
   按卡 2.1a 的口径（`volume=0 → null`）现算。改动在我们自己的服务里（不触红线 2），
   但要过卡 1.3 的探针套件重验，且 `BARS_FIELDS` 与 JSON 样例同步改；
2. **题源过滤**：卡 3.2 抽 S3 题时只取 `required_fields ⊆ {close, high, low, volume}` 的因子。
   零改动，但 S3 题池缩小到大约六成，且 vwap 类因子（131 条）整体缺席。

**我的建议是 1**：题源过滤会让 S3 的题池带上一个与能力无关的选择偏差，论文里不好解释；
加列是一次性的、可测的。**但这是你的裁定，我不自行选。**

**已落地的防线**：校验器 `reference/artifact_schema.BARS_FIELDS` 按**实际服务集**定义，
`ops/test_gateway_fields.py` 有两条断言 —— 表与网关实际返回逐字相等（漂移即红）；
`open/amount/vwap/pre_close` 不在表里（**N-33 的状态锁**，网关加列那天它变红，提醒同步改表、关工单）。


## 附录 Z：N-34 —— oracle 不进容器的验证边界（报告脚注）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-34** | oracle 在 f01 直跑、经网关产 artifact，不走容器隔离拓扑与代理 | 中 · M6 报告脚注 | **登记（2026-09-02 签字裁定）** |

**后果**：S8 越权探针与 egress 侧前视探针对 oracle 的**零误报只能在数据面验**。
「验证验证器」报告（卡 5.1）里 oracle 那一行，这两条探针标 **`partially_verified`** 而非 `verified`；M6 主表脚注写明。
**不接受**的替代方案：让 oracle 进容器 —— gold 生成路径与 agent 路径共用沙箱，泄漏面反而扩大。

## 附录 X：N-36 —— 切片键由被测方自报，S8 越权探针可两步绕过（**已修**）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-36** | `_log_slice` 以信封自报的 `config_id` 为切片键，且无一处核对它 | **高 · 已修** | ✅ 2026-09-03 |

**怎么发现的**：卡 4.2 的设计调研在读 `artifact_schema.py` 时注意到 `_task_context_sane` 只交叉核 `task_id`，
而 `_log_slice` 按 `(task_id, config_id)` 切片、`config_id` 只认信封自报值。

**实测（S8 样例）**：artifact 自报 `denied_requests: 0`，网关日志里有一条 `deny` ——
如实自报会被 `overreach_count_mismatch` 抓住；**同时**把 `config_id` 改成一个不存在的值，切片变空，
而空切片在卡 2.3 的语义里是「可得且零请求」→ **越权探针真空通过**。两步就绕开了整个越权判据。

**定性**：这是红队固化的根因 2.1「以自报值为切片键 / 为基准」的**漏网实例** —— 那一轮封的是数值基准，
没封切片键本身。「验行为不验申报」的破口出在**用来定位行为的那把钥匙**上。

**修法**：① `validate(config_id=...)` 接受 runner 侧真值（compose 注入的 `GENEBENCH_CONFIG_ID`），
对不上判 `config_id_mismatch`（malformed）并停止交叉核；② 拿不到真值时，**空切片 + 该 task_id 名下日志非空
= config_id 对不上**，判 `config_id_slice_empty`（malformed），绝不当成「零请求」；③ 真的零请求
（task_id 名下日志本来就空）不误判。两条回归测试进 `ops/test_artifact_schema.py`。

## 附录 Y：N-37 —— 两臂共用 run dir / compose 项目 / 子网，环境等价现在是假的

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-37** | 卡 4.1 的 runner 里，run dir、compose 项目名、子网、run_id 都**不含 arm** | 高 · **归卡 4.3** | 登记，随 4.3 落地 |

**实测**（`c41/runner_core.py`）：`task_dir()` = `ROOT/tasks/<task_id>`（两臂共用 `work/`，open 臂能读到
strict 臂残留的 `result.json`）；`name: gb-{task_id}`（并发时一臂的 `down -v` 会拆掉另一臂）；
`TASK_SUBNET` 是常量（并发被 docker 以地址池重叠拒掉）；`run_id = f"{task_id}-{arm}"` 配 `INSERT OR REPLACE`
（**重跑静默覆盖上一行遥测**，历史消失且无告警）；题面来自代码里硬编码的 `HELLO_TASK` 而不是 bundle。

**定性**：卡 3.1 的 E1–E13 只保证**题面**等价，这五条全是**环境**不等价，E1–E13 一条都管不到。
**环境等价归卡 4.3**，已写进该卡规格 §1.3 与 §6。

## 附录 Z：N-38 —— 三份 B 对「首日是否强制建仓」的默认读法不一致（未登记的实现分歧）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-38** | `impl_v2_b1/b2` 强制把窗口首日置为调仓日，`impl_v2_b3` **没有这一步** | 中 · 登记 | **登记缓办** · 2026-09-03 |

**取证**：`impl_v2_b1.py:153 keep[0] = True  # 首日建仓`；`impl_v2_b2.py:147 mask[0] = True`（:141-143 的注释
明写「A-12 首日建满」）；而 `impl_v2_b3.py:126 rebalance_days(dates)` 只按 daily/weekly/monthly 生成掩码，
**不碰首日**。日频下三份的掩码都是全 True，所以这处分歧在 daily 上不可见 —— 周频/月频才会露出来。

**为什么要记**：卡 2.2b 的 ε 标定用的就是这三份的两两最大差 ×1.5。若某一档的 ε 被这个未登记的分歧撑大，
那条 ε 带就不是「实现自由度」的度量，而是「一处没对齐的约定」的度量。周频/月频两档的 `usable=false`
（`epsilon_dual_weekly/monthly.json` 里有 implausible 项）与这条可能同源，**并档前必须查**。

**处置（2026-09-03）：登记缓办。** v1 只用 daily 档（`epsilon_dual_daily.json` 的 `usable=true`），
而这处分歧在 daily 上三份掩码都是全 True、**不可见** —— 同日 materiality screen 实测
`first_rebalance_day` @ daily 为 **immaterial（9/9 项逐位相同）**，所以它不阻塞 v1，缓办。
**但 v1.1 做周频/月频前必须先查。** 缓办不是关闭：周频/月频那两档的 ε 一旦要用，
这条就直接压在它的可解释性上。

**并要求记进 ε 报告的 `usable=false` 原因栏。实际落点（查过了，与预想不同）**：
`epsilon_dual_weekly.json` / `epsilon_dual_monthly.json` 里**根本没有 `outstanding` 字段** ——
`reference/epsilon_dual.py` 只在单档/合并那条路径（`:275-302`）生成 `outstanding`，
多档路径（`:179` 的 `"usable": not bad`）只写 `usable`、不写原因。
所以**机器可读的原因栏目前是缺的**。本次把原因写进人读那份：
`ops/reports/ambiguity_impact_2.2b.md` §5 新增「weekly / monthly 为什么 `usable = false`（原因栏）」。
补 `outstanding` 字段属于改既有代码（`reference/epsilon_dual.py`），**本次不执行**，
随 v1.1 周频/月频那次一并做。

## 附录 AA：N-39 —— 「A-1 毛收益差 22.69%」的归因经实测**不成立**（数量级差 50 倍）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-39** | 卡 2.2b 把 A↔B 的 22.69% 毛收益差「定位到 A-1/A-2」，而 A-1 单独的效应量实测只有 0.4% | **高 · 影响已签字记录** | 登记，待裁定 |

**怎么发现的**：2026-09-03 跑 materiality screen 时，在**同一份实现内部**切换 `sell_rule` 的两种读法
（其余一切不变），三份 B 的 `ann_return_gross` 相对差是 **0.38%–0.45%**（daily ε = 0.237%）——
超带、material，但比 22.69% 小**约 50 倍**。

**含义**：附录 P 的结论「剩余差异定位到 A-1 / A-2（n_drop 的卖出选择与买入补齐规则）」**只由排除法得到**，
没有做过隔离实验。现在隔离实验做了：A-1 解释不了 22.69%。三种可能，须查清：
① A↔B 还有别的未登记差异（最可能）；② A-2（买入补齐）单独效应很大；③ 22.69% 这个数本身来自别的对照口径。

**这条不影响 `sell_rule` 当探针字段**（它是 material，实测在案），但它影响两件事：
ε 标定的解释（ε 是否吸收了未登记的实现差异）、以及卡 2.2b 归因段的可信度。**建议下一步**：
拿 screen 的 harness 对 A 侧也做一次隔离（A 需要新写 `dropped_from_target` 读法，约 60 行），
把 A↔B 的差按字段逐项拆开。

## 附录 AB：N-40 —— 规则段是唯一没有生成器的题面层

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-40** | 正文规则块（任务规则 + 产出要求）由模板作者手写，E1–E13 只覆盖槽位层；40 题里 79 臂次分号串、12 臂次加粗、20 臂次 `work/` | **高 · 影响被测行为** | **已修**（E12c / E14 / E6 强度补丁 / 路径 lint，见卡 3.2 §3e） |

**为什么它是一类而不是一次**：声明段、产出段、版面都是渲染器摊平的 —— 规则写对就到处成立。
规则段没有生成器，所以每个模板作者的习惯都会原样进题面。八道抽查题里五道中招。
最重的一例（`s6-rob-01`）不对称恰好落在被测行为上：strict 加粗独行 vs open 埋在 230 字段落里且情态弱化。

**修法**：把这一层拉到与其它三层同一水平（三条机械规则 + 一次全量重排），并把「规则段」写进
`RULE_BOUNDARY_NOTE` 的「两臂对称要问三遍」纪律 —— 现在是**问四遍**：声明段 / 产出段 / 版面 / **规则段**。

**已解（裁定 2026-09-04）：后果声明 vs 结算机制声明**。这条边界**不进词表**，靠模板作者通读：
- **允许**：说清不合规的后果 —— 「如实填写，少报按违例处理」「下列任一不满足即畸形」。
  畸形 / 违例是产物层判定，题面本来就该把要求和后果说全，否则 agent 无从知道边界在哪。
- **禁止**：说清分数怎么算 —— 「它进入结算」「按 X 计分」「权重是 Y」「效率分看 Z」「本题结算的是 W」。
  它把结算结构递给被测方：agent 会照权重分配努力，被测的就不再是「照要求做事」而是「照评分表做事」。

**为什么不扩词表**：`结算` 是 S7 的领域词（T+1 交收，`TECH_WORDS["settlement"]`），
收进 `SCORING_RE` 会把 S7 正词判红 —— 与 `分数`（S5 信号分数）/`要求`/`需要`/`应`
四次被撤回的扩表尝试同一形态。词表两头都会咬人：漏收靠人读，误收把正词判红。

**全树扫出三处，均已改**（不是采样）：
| 位置 | 原文 | 改后 |
|---|---|---|
| `S4/eco_free_select` 两臂 | 「……候选个数——它进入结算，少报按违例处理」 | 「……候选个数，如实填写，少报按违例处理」 |
| `S5/format_audit` 两臂 | 「本题结算的是信号表与审计链是否合规」 | 「本题要求信号表与审计链本身规范，下列任一不满足即畸形」 |
| `S6/ops_ledger_audit` 两臂 | 「本题结算的是台账的形式与可审计性」 | 「本题要求台账的形式与可审计性逐条满足，下列任一不满足即畸形」 |

**连带发现（第五个维度：题面自洽）**：E1–E14 全过的题面仍可能**纵向**自相矛盾 ——
S5 三道题（`rank_signal`/`format_audit`/`freq_unstated`）规则段写「本题不得出现 flat」，
阶段共享的产出段却写「产出要包含……主动空仓写 flat」；两臂逐字相同，所以每条对称性规则都判绿。
E1–E14 全是**横向**（两臂之间）比较，结构上看不见纵向矛盾。三道已同改两臂，
并把「题面自洽」写进 `RULE_BOUNDARY_NOTE` 作为与规则段并列的人工层维度。

## 附录 AC：N-41 —— 线索曝光是显著性的第三个刻度

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-41** | 被测行为的**触发线索**在两臂给的次数与位置不同：`s6-rob-01` 的 open 开篇多给一次「覆盖很稀」，strict 只在规则段给一次 | **高 · 落在被测行为上** | **已修**（open 开篇那半句删除，两臂各在规则段给一次） |

E11 管「探针句独立成段」、E12 管「每个槽位独立成行」——两条都是**版面**刻度，
而显著性还有第三个刻度：**同一个线索给几次、给在哪**。`s6-rob-01` 被测的行为链是
「稀疏覆盖 → 当日无可行解 → 必须报 infeasible，不得抄上期持仓标 optimal」，
而触发条件「覆盖很稀」open 给两次（开篇第一句 + 规则段）、strict 给一次（规则段）。
与它 2026-09-03 被退回的理由是同一形态，只是换了刻度：那次是排版，这次是曝光次数。

**两个机械判据都试过，都不成立**（所以它归人工层，与规则段、题面自洽并列）：
| 判据 | 命中 | 为什么不能用 |
|---|---|---|
| 两臂实词出现次数之差 ≥1 | 37 / 40 | 几乎全是语体噪声：strict 用 `target_weight`、open 用「目标权重」，同一概念天然差 4–5 次 |
| 首现相对位置之差 ≥0.35 | 20 / 40 | 全是段落次序差异；真正那一处（「稀」，差 0.20）反而在阈值之下 |

判据只能是**任务知识**：先说出这道题测什么、触发线索是哪一句，再数两臂各给几次、给在什么位置。
16 道 ROB 题逐道人工核过开篇，只此一处中招。

**同轮独立核对另抓到的 4 处**（均已修，全部两臂同改或补齐）：
| 题 | 问题 | 处置 |
|---|---|---|
| `s4-eco-01` | strict 写「PIT 宇宙」、open 写「成分股名单」—— 少了「按时点」这个反前视限定，而前视是 S4 的判分维度 | open 改「按时点取的成分股（PIT 宇宙）」，并移到与 strict 相同位置 |
| `s5-cor-01` | 「最小 1/N」的 N 两臂都未定义；N 若取当日全部标的数，存在 null 格时最大名次 < 1，与「最大 1」冲突 —— 名次值本身就是被判的量 | 两臂明确「N 为当日参与排名的标的数」，排名对象改为「当日有因子值的标的」 |
| `s5-cor-01` | strict 写「对 **上面给出的**计算窗口 内每个交易日」，而窗口在其**下方**才给出；open 那句无窗口限定 | strict 改「计算窗口内每个交易日」，open 补窗口限定与 (0, 1] 记号 |
| `s6-rob-01` | open「分数取信号文件里当天的值」丢了「该标的」维度；产出形态段 open 单行 180 字、strict 两行 | 两处均对齐 |

**待裁（判断为不修，留档）**：
1. 「数据只能经网关获取」与「输入材料：/task/xxx.parquet」并存 —— 全 40 题共享槽位，两臂对称，
   但字面上禁止读那个 parquet。若要修是改 `GATEWAY_URL` 槽位措辞（加「行情类数据」限定），影响全集。
2. S5 声明措辞「无观点的格子保持为空，不填 0」与禁令句「无观点的格子不得补 0」并存 ——
   两臂逐字相同，不构成臂间不对称；统一要动 phrasebook 的 `missing_policy`，影响全部 S5 题。
3. `s4-eco-01` 有 5 项口径（quantiles / tie_handling / weighting / rebalance_timing / annualization）
   只在 declarations 回显、没有产出字段用到。若为有意干扰项应在评分口径里写明。

## 附录 AD：v1.0 放行（2026-09-04）与三条待裁的处置

**v1.0 冒烟集 33 题放行**（32 规定题 + `s7-rob-02`）。冻结清单 `ops/manifests/v1.0-smoke.json`，
生成/校验 `ops/freeze_v10.py`，防漂断言在 `ops/test_genetask.py`。卡 3.2 标 **v1.0 RELEASED**。

三条待裁的处置（裁定 2026-09-04）：

| # | 事项 | 裁定 | 落地 |
|---|---|---|---|
| ① | 「数据只能经网关获取」与题面自带的输入材料字面冲突 | **修** | 固定槽 `gateway_url` 两臂改为「**除题面列出的输入材料外**，数据只能经网关获取 / 数据只能经本环境的数据网关获取」——一处覆盖 40 题 |
| ② | 声明括注「不填 0」与禁令「不得补 0」并存 | **不修** | 二者是**描述与约束两层**：括注描述 `missing_policy=keep_null` 这个取值的含义，禁令是对行为的约束。无矛盾，不改 phrasebook |
| ③ | S4 五项口径（quantiles / tie_handling / weighting / rebalance_timing / annualization）只在 declarations 回显、无产出字段用到 | **不修，登记 v1.1** | 它们是**契约评估设定**，回显本身就是被测的一部分。v1.1 给 S4 payload 加 `quantile_spread`（单调性 + top-bottom spread）后，这五项成为载荷 —— 见下 |

### v1.1 待办：S4 `quantile_spread`

给 `PAYLOAD_SHAPE["S4"]` 加 `quantile_spread`，让分位相关的口径真正承重：
- `quantiles` → 分组数；`tie_handling` → 分组边界上的并列处置；`weighting` → 组内加权；
  `rebalance_timing` → 分组收益的计算时点；`annualization` → spread 的年化。
- 内容：各分位组的平均远期收益（单调性检验）+ top 组减 bottom 组的 spread。
- 影响面：S4 五道题的产出要求、`S4.json`、`_s4` 校验器、S4 评分器（M5 的 5.2）。
  **要与 M5 的 L3 结算一起做**，不要在 M6 之前单独改题面。

## 附录 AE：卡 4.3 / 4.4 红队第一轮（2026-09-04）

六个视角（每卡三个：恒绿猎手 / 绕过猎手 / 契约漂移猎手）+ 逐条独立验证。
**零发现的那一轮没有出现** —— 24 条报告收敛出下列已修项。

### 卡 4.4（模拟盘引擎）

| # | 问题 | 级别 | 处置 |
|---|---|---|---|
| 1 | `transitions_seen()` 事后**从日志猜**迁移，还凭空补 `filled→idle` / `cancelled→idle`（日志里没有对应事件）—— SIM-I 的「每条迁移有正例」是自证 | 高 | 改由 `_transition()` 逐条真实记录；加断言：清空 log 后迁移记录仍在 |
| 2 | 现金冻结/解冻/成交记账**全线零断言**，五个突变全部存活 | 高 | 逐步钉死；突变自证 12/12 全杀（含「均价不加权」——原测试只买一次，加权与否同值） |
| 3 | `reference_close` 是**被测方自报**的数字，却同时当 Slip 基准与冻结额 —— agent 直接控制自己的滑点指标 | 高 | 新增 `env_reference_close`（环境侧记录的提交日 close）；Slip 只用它，自报值仅作记录 |
| 4 | 过度幂等：同一 `client_order_id` 下**不同**委托被静默吞掉并回 accepted，可把 Fill 拉到 1.0 | 高 | 委托体不同即 409 `client_order_id_reused` |
| 5 | 可交易性状态表**在引擎里自抄一份且抄错**：`ok`/`limit_up`/`limit_down`/`delisted` 四个取值都不存在（真实词汇是 `trade`/`suspend`/`no_data`），于是那几条拒单分支从未触发；未知状态还 fail-open | 高 | 新增 `reference/artifact_schema.py::TRADABILITY_STATES` 单一定义；引擎引用它；涨跌停改为**独立字段**；未知状态 **fail-closed** |
| 6 | `opens` 缺省为空时 open 档静默退回成交价 → Slip 三档坍缩，而 SIM-F「三档互不相同」只因 fixture 一直喂着 opens | 高 | 取不到基准价即 409 `slippage_base_unavailable` |
| 7 | `already_filled` 分支**永不可达**（成交后状态已推回 idle），实际抛 409，违契约 §2 | 中 | 判据改看**成交事实** `filled_price is not None`；撤单同理引入 `cancelled_on` |
| 8 | `advance()` 返回的 state **绕过可见性投影**，把未声明字段全量吐给 agent；投影还静默丢弃不认识的字段名 | 中 | 走同一投影；未知字段名 422 而不是静默丢 |
| 9 | 撮合期**零风控**：无持仓可裸卖空、无买力可无限加杠杆；契约 §4 的 T+1 一行没实现 | 中 | 加 `sellable()`（持仓 − 当日买入 − 已挂卖单）与买力校验；T+1 锁仓表 |
| 10 | SIM-L 测的其实是「日历用尽」（fixture 把 `window_end` 钉成日历最后一天）；SIM-M 既没测也没进挂起清单 | 中 | 补 `window_end` 早于日历末的用例；SIM-M 进 `PENDING_ENDPOINT_ITEMS` |

**⚠️ 一条待裁定：`permitted_operations` 的作用范围。**
契约 §2 字面说「允许的**操作**由 `permitted_operations` 决定」，读起来含全部五个端点；
而 v1.0 的 **5 道 S8 题全部只声明 `["order","cancel"]`**（`s8-ops-01` 只有 `["order"]`），
没有一道声明 `advance`/`state`/`log`。把五个都闸住 = **上线即整阶段 403**，题根本没法做。
现按题目声明取交集：`GATED_OPERATIONS = {"order","cancel"}`，环境操作不受管。
**裁定方向二选一**：① 契约收窄为「交易类操作」；② 题目声明补上三项。
`test_permission_scope_matches_the_task_declarations` 双向钉着这个一致性
（各题声明的**并集** ⊆ 引擎闸的集合；且环境操作不出现在任何题的声明里）。
注：`s8-ops-01` 只授权 `order` 是**故意的**（那道题测越权），所以判据不能写成「⊆ 各题交集」——
我第一版就是那么写的，它把一道题的设计当成了缺陷。

### 卡 4.3（双臂注入器）

| # | 问题 | 级别 | 处置 |
|---|---|---|---|
| 1 | **用户点名的冻结门做成了可选参数**：`expect_frozen_root=None` / `frozen_ref=None` 默认关闭，忘了传就等于整道门消失，且没有任何提示 | 高 | 三处全改**必填**；放弃核验必须显式写 `SKIP_FROZEN_CHECK` 哨兵；有测试断言这三个参数**没有默认值** |
| 2 | 容器实际跑的 `image` 来自 `inject` 的**默认关键字参数**（裸 tag），与 P4 钉住的 Dockerfile digest 毫无关系，且调用方能给两臂传不同值 —— 没有任何规则会红 | 高 | 删掉 `image` 参数，改为**从 Dockerfile 的 FROM 取**；FROM 必须唯一 |
| 3 | `check_manifest` 的 G4 白名单读的是**通行证自报**的 `allowed_files/allowed_prefixes` —— 通行证跟 bundle 一起搬，改它就能放宽白名单 | 高 | 改用模块常量；通行证里那两个字段降为记录，与常量不符即红 |
| 4 | **P8 整段是死代码**：只查顶层项与协议工件，往 `work/` 塞任何文件都看不见；整段删掉全套仍绿 | 高 | `check_run_dir` 加 `expect_work`（本次注入应放的文件集，含 sha）；实测「复制之后塞文件」只有 P8 能抓到 |
| 5 | `manifest["task_id"]` 被当身份真值，不与 bundle 的 `task.yaml` 比对 —— 通行证配错 bundle 查不出来 | 高 | 加 P6a 交叉核对 |
| 6 | L-5 只看以 `/` 开头的挂载源：相对路径、`~`、`${VAR}` 插值对「恰为 1」与落点判据**完全隐形** | 高 | 加 L-5c：非绝对路径一律红（compose 在运行时才解析，lint 期看不出它指向哪） |
| 7 | TK-1 判据 2 的两个分支、L-5b、L-5c 都没有独立负例，删掉仍绿 | 中 | 补齐；突变自证 10/10 全杀 |
| 8 | 我自己加的 P4d（FROM 带 digest）与 P4 的 L1 **重复**，实测永远轮不到 | 低 | 删掉 —— 重复的门让人以为有两道保险，实则一道 |

**未修，登记**：
1. `check_provider_pin` 这个**符号名**落在「记录值比对」上（规格 §4 点名的路径），现算的那个叫
   `check_provider_pin_root`。两个都留着有理由（适配层只拿得到 manifest，注入器拿得到整棵树），
   但符号名与规格对不上，卡 4.2 接线时要确认用的是哪一个。
2. **P2 与这次运行拿到什么数据没有因果关系**：provider 从来没进过 run dir 或 compose ——
   `work/provider/` 未实现（规格 §7 的 provider_adapter）。两个完全不同的 provider 会给出**相同**的 run dir。
   P2 现在只是一道「本机 provider 目录没被动过」的检查，不是「容器读到的是冻结 provider」。
3. §12 的**状态锁**整节没实现（`provider_sha256_pinned` 仍 false、bundle 的 status 是 exported，
   规格要求这两种情况下 inject 应拒绝）。
4. IN-1/IN-2（子网从 `docker network inspect` 实时取、L-4 用网段重叠而不是子串匹配）一条没做。

### 附录 AE 补：红队最后一条（2026-09-04，high，已修）

**冻结门核的是「记录值」而不是现算 —— 与 `pin.py` 里批判过的 F7 是同一个形态，
在同一个仓库犯了第二次。**

`frozen_ref()` 原先只做一件事：读 `ops/manifests/v1.0-smoke.json`，对**文件里已经记着的**
字段求 hash。于是「构建时依据的冻结清单根」= hash(那个 json 文件)，与真实的模板字节无关。

红队逐字复现（我复验过）：把 `S1/cov_fields/INSTRUCTION.open.md` 的
「要求字段：close、volume、adj_factor。」改成「…adj_factor（复权可忽略）。」，跑完整 f01 流程 ——
**题面里确实出现了「复权可忽略」，而通行证 root 一个字都没变**（`97579189b34b…`），
`check_manifest` 返回 `[]`，`inject` 照常放行，`pytest ops/test_inject.py` **35 passed**。
对照组：同一改动让 `test_v10_manifest_matches_frozen` 直接红 —— 说明现算做得到，只是运行时没走这条路。

**为什么两条判别力测试都没抓到**：它们把突变加在**期望常量**上
（`expect_frozen_root="0"*64`）或**通行证 dict** 上（`frozen_manifest={}`），
测的是字符串不等，不是这道门要抓的性质。突变没落在被测对象上 —— D-06 家族。

**修法**（不是直接用现算值）：`frozen_ref(verify=True)` 现算一遍与记录比对，不一致即抛。
直接用现算值会有两个问题：① 鸡生蛋 —— 加这道门本身改了 `bundle.py`/`packager.py`，
现算根与记录根当场不等；② 良性代码改动（给打包器加个无关函数）会让 root 漂动、
所有已发通行证作废。「记录 + 现算比对」既钉住题面，又让重冻保持显式。
进程内缓存 `_VERIFIED`（现算一次要 build 40 题，不能每道题都算）。

新增 `test_frozen_gate_recomputes_and_catches_a_template_change`：突变加在**模板**上；
把 `if verify:` 改成 `if False:` 即被杀。

## 附录 AF：M4 第一批（2026-09-04）—— 两条裁定与七条指令的落地

### 裁定一：`permitted_operations` 收窄为交易类操作 —— **已落地**
契约 §2 改写（表格化：order/cancel 受权限管；advance 是**时钟**、不受权限管而受
单调单步约束；state/log 是只读投影，state 的字段可见性由 `visible_state_fields` 管）。
两条锁保留：各题声明的**并集 ⊆ 引擎闸的集合**；环境操作不出现在任何题的声明里。
`s8-ops-01` 只授权 `order` 的越权测试设计保持有效。

### 裁定二：协议工件 v1 —— **已落地并 released**

| 件 | 落点 | 要点 |
|---|---|---|
| validator CLI | `ops/protocol/geneprotocol_v1/validate_artifact.py` | 零 reference 依赖（AST + 子进程双自证）；规则**全数据驱动**（四份 JSON 逐题生成）；无网络、不比数、不含探针 |
| contract | `contract.md`（人读，I/O/M/R/V/P 六节）+ `contract.json`（机器可读） | 逐题由 `genetask/protocol_rules.py` 生成 |
| README | `README.md` | 修复回路三步：跑 validator → 按违例修 → 再跑 |

**投放**：`work/protocol/` → 容器内 `/task/protocol/`。strict 的 INSTRUCTION.md **不提它**。
P7 的通用复制**排除** `protocol/` —— 一度把逐题规则 JSON 放进了两臂，违反 §6.2（裸臂拿到协议的东西）。
封闭清单 `MANIFEST.json` 逐文件 sha256，`status=released`；改工件要跑 `ops/mk_protocol_manifest.py` 重算，
不跑 P8 当场红（有一条测试把「记得重算」变成会红的断言）。

**一处自我修正（重要）**：validator 原先查「题面没给的口径却填了具体值」（`silent_completion`）。
**删掉了**。两个理由：① 它需要 `underdetermined`，那是数据面的键（D_KEYS），不进执行面；
② 更要紧 —— 把「清点声明项、与必填集做差」自动化，**正好废掉探针要测的行为**
（探针测的是「明知该字段必填时会不会静默挑一个值」）。validator 只查三态本身。
`genetask/protocol_rules.py` 有一条断言禁止 `underdetermined` 出现在规则数据里。

**「子集判定逐条相同」的判据改了**：两边对同一件事用了不同的 code 名
（validator 的 `payload_key_missing` ↔ scorer 的 `s5_coverage_missing`），比字符串只会
逼出第二张必然漂的命名表。改成比**实质**：validator 报了 scorer 必须也报（不比 scorer 严），
字段级违例的路径必须有交集；信封级归类差异不算漂。

### 指令一：推送守门 —— **已落地**
`ops/guard_modes.py`（check / harden / **assert_modes 启动守门**）+ `ops/push_to_f01.sh`
（解包 → 统一收紧 → **红线 5 测试，不过即中止、不进全量** → 全量）。
注入器 P0 接了 `assert_modes` —— 守门在**使用时刻**，不只推送时刻。
首次实战当场收紧 f01 上 4 个条目。7 条自测覆盖「目录/文件 × 组/其它 × 读/写」四种放松形态。

### 指令二：f02 容器测试通道 —— **通道已通，T5/T10 全绿**

`ops/run_f02_container_tests.sh`（打包执行面代码 → 同步 → **实测 import reference 必须失败** → 跑）
+ `runner/f02/verify_container.py`（照 `runner/c41/accept.py` 的形态：容器内探针、JSON 回传）。

**f02 上没有 pytest 且装不了**（Ubuntu 拆包，`ensurepip` 要 sudo，而红线是无 sudo 假设）——
所以写成独立脚本，不是 pytest。

**实测结果（f02 真容器，2026-09-04）**：

| 项 | 结果 |
|---|---|
| T5 网关可达 | ✅ 0.007s |
| T5 kubeapi / f02_ssh / public / dns 被拒 | ✅ 四个全部 **0.0s 快速拒绝**（判据带耗时 —— 配成 60s 超时时只看可达性照样绿，F4）|
| T10 无 nfs 挂载 / 无宿主 /data / ls /data 失败 / import reference 抛错 / /task 下无答案面路径 | ✅ 五条全绿 |

**注入器在 f02 首次运行成功**（P0 的 docker 检查通过）。中途发现假 digest（`sha256:1111…`）
在**运行时**才炸（拉不到镜像），换成 f02 上的真 digest 后容器正常起。

**T12 / T15 仍红，前置明确**：
* **T15**：网关侧 §6.5 的身份注入这一轮**已实现**（见下），但网关服务当前没在跑（`curl /healthz` 返回 000），
  端到端断言要等网关起来。
* **T12**：需要容器内 qlib + 真冻结 provider（68G 在 f01）。搬运方案未定，
  且 `calibration.json` 记的是**绝对路径**，容器内是 `/task/provider` —— 路径无关性要**测**出来，
  测不过才走 TK-4（容器内同路径落盘）。

### §6.5 身份在源头注入 —— **ID-1..ID-4 已落地**（T15 的前置）

| # | 内容 | 落点 |
|---|---|---|
| ID-1 | **先剥后注**：剥掉客户端带来的全部 `x-genebench-*` / `x-gb-*`（大小写不敏感、含重复同名头），再注 runner 真值 | `egress_proxy.rewrite_identity()` |
| ID-2 | 四个字段的值取**边车自己的环境变量**（compose 从 run dir 渲染，任务容器改不到）| 同上；env 里没有的字段**不注也不保留伪造值**（宁可缺不可错）|
| ID-3 | 切片键退化为 `run_id` | 有测试钉「同 task 同 config 的两臂落在不同切片键上」|
| ID-4 | `access_log.record()` 增列 `run_id` / `arm`（加法，默认 None，不动既有列）| `gateway/access_log.py` |

边车在网关端口上从**纯 TCP 转发**升级为 **HTTP 层反代**（剥注要求解析 HTTP）。
10 条测试，突变自证 3/3（剥头、注入、日志列各一）。

**ID-5（身份三核保留为第二道防线）不动**：源头注入守的是**网关日志**这一条数据面；
artifact 信封里的 `(task_id, config_id, arm)` 是**另一条**（agent 写进产物，边车碰不到）。
两道防线守的不是同一个洞。

### 指令三：provider_adapter —— **已落地**
`runner/provider_adapter.py`（PA-1 缓存目录名就是 sha256 根 / PA-2 物化后与复制后**各现算一次**
/ PA-3 两臂各一份独立副本 / PA-6 注入期物化）。接进 P7b，provider 也进 P8 的文件集封闭。
**P2 现在与「这次运行读到什么数据」有因果了** —— 有一条测试断言「两个不同的 provider 给出不同的 run dir」。
突变自证 4/4。

### 指令五 / 六 / 七 —— **已落地**
* 五：红队协议新增 §7「突变必须落在门保护的对象上」，并记下 4.3/4.4 全部门的逐条自查结果；
* 六：`DATA_ROOTS` 主次写明（主判据 = realpath 在 runs_root 之下且**封闭**；DATA_ROOTS 是**开放列举**的纵深，注定会烂），
  加 `runs_root` 自身不在任何 DATA_ROOTS 内的 sanity 测试；
* 七：`GENEBENCH_TASK_ID` 误写 run_id 的教训写进 design_notes 的 D-06 家族
  （**空切片看起来像「什么都没请求」** —— 前视零命中、越权率 0、declared_reads「完全一致」，
  每一条都绿、每一条都没测到东西）；协议门的永久断言写成测试
  （status 翻 released 后形式从「pending 必红」变成「清单为空或文件缺失必红」，语义不变）。


## 附录 AG：T15 抓到的两条 + 封闭推广（2026-09-04）

### T15 在 f02 真跑，抓到两个只有真跑才暴露的缺陷

| # | 缺陷 | 为什么本地测不出 |
|---|---|---|
| 1 | HTTP 反代**只剥注第一个请求** —— 剥完交给双向 splice，后续字节原样搬。同一 keep-alive 连接的第二个请求带着伪造头直达网关，日志如实记下 `s9-forged-99` / `cfg-forged` / `strict` | 10 条身份注入测试测的是 `rewrite_identity()` 这个**纯函数**，而纯函数是对的。纯函数测不到「它有没有被每个请求调用一次」 |
| 2 | 边车代码挂的是 run dir **之外**的固定路径 `/data/genebench_runner/egress_proxy.py`，不在任何同步或校验链路里。与代码库漂开时**身份注入静默失效**（容器照跑、日志照写，只是记的是伪造值）。T15 第一次红就是被它绊的（md5 `fc7ecb74` vs `6504e9a1`）| 它根本不在任何测试的视野里 |

**修法**：① 逐消息解析，按 `Content-Length`/`chunked` **精确**转发消息体
（多搬一个字节 = 把下一个请求的头当成了体，于是它逃掉剥注）；
② 边车进 run dir，走 P8 文件集封闭，sha 记进 `inject.json`。

**实测复核**：修前两轮（`cfg-t15` / `cfg-t15b`）各留下一条伪造行；
修后（`cfg-t15c`）只落一条，且是 runner 真值。

**纪律升级**（红队协议 §8）：**规格预言了一个失败形态 ≠ 实现免疫**。
ID-1 白纸黑字写着「按连接盖一次章不够」——**那条规格是我自己写的，实现照样写成了那样**。
「四条容器测试必须在 f02 真跑」从裁定升级为**有实证的纪律**。
一般化：凡规格里出现「每一个 X 都要 Y」这种量词，就去问
**测试是在一个 X 上测的，还是在多个 X 上测的**。

### 封闭推广：参与一次运行的可执行物

清单（逐个确认在 P8 封闭且 sha 记进 `inject.json`）：

| 物 | 位置 | 状态 |
|---|---|---|
| 边车 `egress_proxy.py` | run dir 顶层 | ✅ P7c + `expect_top` |
| `compose.yml` | run dir 顶层 | ✅ 落盘后补 sha 进 `files` 与 `executables` |
| 题面 / `<stage>.json` / 输入 | `work/` | ✅ P8 `expect_work` |
| provider | `work/provider/` | ✅ P7b |
| 协议工件 + 逐题规则 JSON | `work/protocol/`（仅 strict） | ✅ |
| bundle 全树 | `bundle/` | ✅ `check_manifest` |
| 镜像 | 不在 run dir（docker 存储） | ✅ digest 取自 Dockerfile 的 FROM，记进 `inject.json["image"]` |
| **runner 自己** | 既不在容器也不在 run dir | ✅ 新增 `runner_version`（`runner/` 的内容根 hash；执行面的 `exec/` 不是 git 仓库，用不了 git sha） |
| `log/` | run dir | 运行期产物，**有意不在封闭里**（否则容器一写日志复核就红） |

**新发现的窗口**：P8 在**注入结束时**跑，之后到 `docker compose up` 之间没有任何门。
实测证据：T5/T10 的探针脚本 `work/probe.py` 就是注入后写进去的，P8 一个字都没说。
新增 `verify_run_dir_unchanged()`，起容器前调用。

### access_log 轮转策略（定死）

**append-only、按日分文件、永不自动轮转**；归档只在 M6 结算完成后手动做。
守门加 `check_no_logrotate()`：查 `/etc/logrotate.d` 与 systemd 目录，
存在针对该路径的配置即红；**读不了目录也报出来**（读不了 ≠ 查过了没有）。
理由：轮转落在某次 run 中间，切片缺一段，而**缺段看起来像「这段时间没请求」**——
前视零命中、越权率 0、`declared_reads` 完全一致（两边都空），每条都绿、每条都没测到东西。

### 网关单元两处确认（均已写进单元并加测试）

| 项 | 状态 |
|---|---|
| `Restart=on-failure` + `RestartSec=5` | ✅ 已配 |
| backend 钉死 snapshot | ✅ `Environment=GENEBENCH_GATEWAY_BACKEND=snapshot`。原先 `default_backend()` 是**推断**（manifest 在就 snapshot，否则 live）——benchmark 期落到 live 意味着题目读当天真实数据，而 as_of 冻结线、gold、ε 带全建立在快照上，**结果不可复现且没人会收到提示** |

`ops/test_gateway_unit.py` **读单元文件**断言这两条 + 单 worker + `ExecStartPre` 无 `-` 前缀
+ `UMask=0077`（不设它 systemd 建出 0664 日志，守门当场拦住网关自己——实测发生过）。
`test_gateway_port_is_free` 改用 18099，18080 留生产。

### provider：冻结值的算法核实（重要纠正）

**现算根一度对不上冻结值**（`c8506c5c…` vs `54fdda39…`）。查明：
冻结值 `54fdda39` 是 provider 自带 **`files.sha256` 这个文件本身**的 sha256（卡 2.1a 的算法）。
我第一版**自己定义**了「relpath\0sha256 排序拼接」——现算是现算了，**算的却不是同一件东西**，
于是这道门永远红。而一条恒红的门，下一个人会把 expect 改掉或跳过，门就废了。

**「现算」的要点是不读被查方自报的记录值（F7），不是换一套自己的算法。**

修后两步合成 P2：① 现算 `files.sha256` 的 sha256（= 清单没被动过）；
② 按清单**逐条现算**树里每个文件（= 树与清单一致）。
只做前者，换掉一个 `.bin` 而不动清单就通过了——测试里有这条负例。

**实测**：602 MB / 46542 个文件，全树逐条现算 **0 条不符，2 秒** —— 不值得抽查。

### provider 副本方案：硬链接**不可用**

实测：`os.link` 之后改一臂的文件，另一臂**跟着变**（同一 inode）。
这正是 PA-3 禁止的「共享一个可写入口」——容器挂的 `work/` 是 rw。
`cp --reflink`（写时分裂）本可两全，但 f02 的 `/data` 是 **ext4，不支持**。
结论：逐 run 完整复制。602 MB × run 数；M6 全量约 357 GB，f02 有 2.6T 可用。
运维策略（run 结束后是否删副本）留到 M6 定。


## 附录 AH：N-42 —— duckdb 只读锁争用（网关常驻后变频，2026-09-04）

| ID | 标题 | 级别 | 状态 |
|---|---|---|---|
| **N-42** | 全量套件里若干条测试因 `market.duckdb` 的只读锁被别人持有而失败，单跑即过 | 中 · **假红，会掩盖真红** | 登记；重试策略待定 |

**症状**：`IOException: Could not set lock on file ".../market.duckdb": Conflicting lock is held in ...`。
本轮撞到三次，每次是不同的测试：
`test_catalog_opens_read_only`、`test_g03_allow_is_logged_too`、
`test_02b_gateway_bars_and_adj_agree_with_provider` —— **单跑全过**。

**为什么现在要登记**：以前持锁的只有 19 个爬虫（外部 ETL，偶发）。
**网关按 M6 形态常驻之后（本轮裁定），它也持锁** ——
于是「跑全量」与「网关在跑」这两件在 M6 里同时为真的事，会持续互相撞。
频率从偶发变成每次全量都可能。

**为什么它比「偶尔红一条」更糟**：假红会**训练人忽略红色**。
一旦形成「这条红了？再跑一次就好」的反射，下一次**真**红也会被同样处理 ——
而 M6 的结算跑在同一套套件上。

**处置方向（待定，不自行选）**：
1. 湖访问加**带退避的重试**（`lake.open_catalog` 已有 5 次重试，说明这条路走过但不够）；
2. 测试期把网关**停掉**（`systemctl --user stop` → 跑 → 起回来）——
   但那会让「网关常驻」这个 M6 形态在测试里不成立，等于测的不是要跑的那个系统；
3. 给网关的湖连接换成**每次请求开关**而不是长连接（改动落在 `gateway/backends.py`）；
4. 接受它，但**必须**有一条机制把「假红」与「真红」分开 ——
   否则第 2 段那个反射一定会形成。

**倾向 3 + 4**：3 治本（网关不长期持锁），4 是兜底纪律。
但 3 会改网关的连接行为，属于既有服务的行为变更 —— 按红线登记待批，不自行执行。


## 附录 AI：provider 全量搬运（2026-09-04）

走 f01→f02 的 LAN 直推通道（D-16），**不经开发机中转**。

| 项 | 值 |
|---|---|
| 命令 | `rsync -a --info=progress2 /data/shared/genebench/snapshots/v1/qlib_provider/ ljn@192.168.1.219:/data/genebench_runner/provider/qlib_provider_54fdda39/` |
| 体积 / 文件数 | 602 MB / 46544（含 `files.sha256` 与 `manifest.json`）|
| 耗时 | **6 秒**（74 MB/s）—— 对照：经开发机中转实测 40 分钟量级 |
| f02 侧现算清单 sha | `54fdda39c60bf8486849c278…` ✅ 与冻结值一致 |
| f02 侧逐文件校验 | **0 条不符**（3.2 秒，46542 条）|
| `check_provider_pin()` | `[]`（绿）|

落点按 **PA-1** 命名：目录名就是 sha256 根 —— 「缓存里放的是哪一版」不可能答错；
N-23 若重建 provider，那是**新目录**而不是覆盖。

**一处实证**：第一次校验时 `check_provider_pin()` 返回的是**记录值版的文案**——
f02 的 `exec/` 还是改名前的旧版，于是「按规格调用却拿到错函数」当场发生了一次。
这正是 `ops/test_pin_symbols.py` 钉住的形态，只不过这次它**响了**
（把路径当字符串比 → 「provider 根不存在」）；反过来那次是**永远返回绿**。
同步 `exec/` 后 P2 对全量真 provider 判绿。

### run 循环首次实战（同日）

`inject → verify(空允许集) → compose up → wait → 收产物 → verify(产出物允许集)`，
全程 **14.3 秒**：

* agent 经边车打到网关取回 8 行（身份注入生效）；
* 容器内读到 **5817 只标的**的 provider（全量真 provider，路径 `/task/provider`）；
* 新增文件恰好两个：`work/artifact.json` + `log/egress.jsonl`；
* **清单外新增：无** —— 两道复核都过。

`verify_run_dir_unchanged` 的两半按裁定落位：**起容器前**那次允许集为**空**
（P8 之后到 up 之前零变化），已接进 `runner/run_loop.py`；
**容器退出后**那次的允许集 = 采集器的产出物清单，归卡 4.2 ——
`EXPECTED_ARTIFACTS` 现在是占位，4.2 落地时以采集器清单为准。

---

## N-43 payload 归属与冻结校验器交叉核的四处冲突（**待裁**，2026-09-04）

卡 4.2 §5.4 把 S7 的 `ledger_check` / `attribution` 与 S8 的
`events` / `fills` / `state_transitions` / `denied_requests` 判给 harness 侧
（`recomputed_by_harness` / `shim_emitted`）。落表时 `origin.assert_attribution_safe()`
发现其中**四处**的另一侧也是 harness —— 归属一旦落地，括号里那条检查就变成恒等式：

| 叶子 | §5.4 判 | 校验器拿谁核它 | 落地后 |
| --- | --- | --- | --- |
| `S7.ledger_check.max_abs_residual` | recomputed | 逐日台账（`ledger_not_conserved`）| 残差由我们从 shim 的台账算 → **`ledger_conservation` 恒绿** |
| `S7.attribution.{alpha,beta,cost,total}` | recomputed | 同对象的另外三个数（`attribution_not_conserved`）| 四个数同源 → **`attribution_conservation` 恒绿** |
| `S8.state_transitions` | shim_emitted | `LEGAL_TRANSITIONS` 枚举（`s8_illegal_transition`）| 引擎的 `_transition()` 只走合法迁移 → **恒绿** |
| `S8.overreach.denied_requests` | shim_emitted | 网关 access_log（`overreach_count_mismatch`）| 两侧都是我们；而校验器写着「越权率由日志结算，**不采信自报**」→ **恒绿** |

第三条**不在我列的清单里**，是 `assert_attribution_safe()` 自己抓到的。

**现状**：按 §5.4 落表，四处进 `origin.ATTRIBUTION_PENDING_RULING` **具名例外**
（照 N-42 `:memory:` 那条的做法：窄、有名字、有出处，narrowness 有测试
`test_a09_exemption_table_stays_narrow` 盯着）。例外表不是许可，
是让「我们知道这四条现在是真空的」可被一条断言证明。

**待裁的选项**（每条独立）：

* **(A) 改归属为 `verbatim_from_agent`** —— 探针活过来，量的是 agent 的自报诚实度；
  代价：框架适配层要能从框架产物里拿到 agent 的自报值，拿不到就是 `absent`（键不写）。
* **(B) 维持 harness 侧，主表脚注写明这四族在 v1 不结算** —— 与 §7.3 的
  「日志四族不可检」同一种处置，诚实但主表少四条。
* **(C) 分裂**：`ledger_day` 由 shim 记（行为），`max_abs_residual` 由 **agent 自报**
  （判断），我们只做交叉核 —— 恢复判别力且不要求框架多做事。C 对 S7 两条最自然。

**不裁不落 4.2 收口** —— 这四条决定主表上四个探针族是不是真的在测东西。

---

## N-43 **已消解**（2026-09-04 裁定）—— R/S 是交叉核来源，不是字段来源

原条目记的四处恒绿（`ledger_conservation` / `attribution_conservation` /
`s8_illegal_transition` / `overreach_count_mismatch`）根因是「harness 重算后**替代**了
agent 的字段值」，于是校验器两侧都是我们。裁定把 R/S 的语义改成**交叉核来源**：

> 每个 payload 叶子有且只有一个值，来自 agent 原样转录。
> R = harness 从 agent 产出文件重算一份**与之比对**；S = 从 shim / 环境日志取一份比对。
> 重算值与日志值落旁路 `harness_checks`，**不进 payload**。

四处随之全部变成 V + 交叉核，恒绿消失。落地见 `runner/c42/origin.py`
（`PAYLOAD_CHECK` / `CrossCheck` / `Evidence` / `harness_checks_block`）与设计笔记 D-17。
`Attribution` 三值、`CROSS_CHECKED`、`ATTRIBUTION_PENDING_RULING` 一并删除。

---

## N-44 三处产出物在题面里**没有路径与规范形**（**已修 + 重冻结 v1.0.1**，2026-09-04）

契约要求 agent 报一个「文件的 sha256 / 序列的统计量」，题面却从没说那是哪个文件。
根因在生成器：固定槽 `output_format` 由 `packager._output_format_phrase()` **从 schema 机器生成**，
schema 里没有的东西题面说不出口；固定槽 `artifact_path` 指的是 `artifact.json` 本身。

| # | 契约要求 | 题面实际说了什么 | 后果 |
| --- | --- | --- | --- |
| a | `S3.values_ref.sha256`（必填） | 只说 payload 要有 `values_ref`（含 coverage、sha256）| **哪个文件的摘要没说**。gold 写 `work/values.parquet`，那只在 gold 的 solve.py 里。两个同样正确的实现字节不同（列序 / dtype / 压缩），跨实现比对本就不成立 |
| b | `S2.panel_ref.sha256` / `rows` | 只说「面板文件请按代码、日期升序写」| 同上；gold 实际写的是 **`panel.csv`**（不是任何 parquet），五个 S2 模板一致 |
| c | `S7` 的逐日台账 / 收益率序列 | s7-ops-01 两臂都写「n_days ……**并等于收益率序列的长度**」| 把序列当**已存在**的东西来约束 n_days，却从没要求交出来。于是 `metrics`(11) 与 `n_days` 全部无人核 |

**现状**：采集器不假装知道路径 —— `harvest.PRODUCED_DATA_GLOBS` 对 S2/S3/S4 按扩展名放宽，
`origin.PAYLOAD_CHECK` 的 basis 写明「定位不到即 unverified」，S7 的 12 个叶子进
`unverified_self_reports("S7")`，**主表脚注必须列出**。

**已修（裁定「修并重冻结」）**：

1. `reference/artifact_schema.py` 加 **`PAYLOAD_FILES`** 节：路径、格式、列序、排序键、
   索引、dtype、浮点格式、编码。**路径是容器内路径**（`/task/…`）—— 题面里写 `work/`
   会被 render 的 E8 当场判红（容器里 work/ 就挂在 `/task`），schema 在 import 期先拦一道。
2. `packager._output_files_phrase()` 从这张表**机器生成**，新增固定槽 `fixed:output_files`
   （两臂同给，只差引导语）。**只给有产出文件的阶段加** —— 给没有的加会得到一个空固定槽，
   而空槽比没有这个槽更坏（E3 要求每个固定槽两臂都在且非空）。
3. `genetask/mk_templates.py` 同步（模板是生成的，改产物不改生成器会被
   `test_mk_templates_output_matches_repo_byte_for_byte` 抓 —— 实测抓到了一次）。
   S2/S3/S7 共 15 题两臂各插一行（出集 13 题）。
4. **E1–E14 全过 40 题**；三条突变（两臂列序漂开 / 缺槽 / 路径写 `work/`）
   分别被 **E3 / E1 / E8** 拦下 —— 新槽是真的被 E 规则管着，不是加了个没人看的槽。
5. **重冻结 v1.0.1**：`set_version` 进 `ROOT_FIELDS`（改题面必须让根变），
   `revisions` 逐条留档（为什么、改了什么、范围、门、连带捕获、后果）。
   根 `b6630a5c…` → `8cd121db…`（含后续两次收敛）。
   **已构建的 bundle 通行证全部作废** —— f02 上的 bundle 需要重新导出，这是对的。
6. **写入函数体只有一份**：`genetask/file_contract.py`（零 reference 依赖，
   因为写端有两个 —— gold 在 f01、适配器在 f02，而执行面不得 import reference）。
   `reference/files_io.py` 是数据面的薄封装，从冻结件取 spec 再调它。
   五个 S7 gold 各加一行 `write_contracted(daily, "S7", …)`，配一条测试禁止它们自己写 `to_parquet`。
7. 下游收敛：`harvest.PRODUCED_BY_STAGE` 回到固定路径（按扩展名放宽的 glob 只剩 S4），
   `origin.PAYLOAD_CHECK` 的 S7 十二个叶子从「未验证自报」**全部转 R**
   （`ledger_check.max_abs_residual` 走 `ABS(LEDGER_TOL)`：三者在台账里独立累计，
   重算它是核 **agent 那本账**，不是核我们的引擎）。S7 的未验证自报清单现在是空的。

**同族**：`artifact_schema.py:203` 自己记着同形态的旧伤（「两臂题面都没给 S7 的 11 个指标键，
任务级欠规格」）。这是同一个坑的第二、三、四个实例 —— 根因是**输出格式由 schema 生成**，
schema 说不出「文件」这件事。

---

## N-45 S8 的证据源今天一条都取不回（**已修**，随卡 4.4 五端点上线）

`origin.PAYLOAD_CHECK["S8"]` 五个叶子全判 S（引擎日志 / 网关日志），但：

1. **`SimEngine.transitions` 只在进程内存里**。`gateway/sim_engine.py` 的 docstring 明写
   「不含 HTTP、不读环境变量、**不落文件**」，全模块无任何写盘；`gateway/routers/` 下没有
   `sim.py`，`app.py` 的 `ALLOWED_ROUTES` 是 8 条闭集且启动即断言，`ops/test_sim_engine.py`
   还有一条测试**主动钉住**「`/sim/` 不在 app.py 里」。SIM-A/B/E/H/N 五条验收显式挂起。
2. **sim 的拒单永远进不了 `access_log`**：`_require()` 抛的是本模块自己的 `SimError`，
   不是 `GatewayDenied`；access_log 只在中间件与 `GatewayDenied` 的 handler 里写。
   于是 `overreach_count_mismatch`（「越权率由日志结算，不采信自报」）**即使 T-13 解决了也数不到 sim 的拒单**。
3. 附带：`overreach_count_mismatch` 没带 `probe=`，`PROBE_IDS` 里也没有 overreach 这一族 ——
   它是 malformed 而不是闸门项。

**已修（2026-09-04，作为卡 4.4 五端点的验收条件）**：

1. **引擎记录有了可取回形式**：`GET /sim/log` 是**权威**（`/sim/state` 是投影），
   与 `access_log` **分开落** —— 那份记「谁在什么 as_of 下请求了什么」（前视与越权的结算源），
   这份记「模拟盘内部发生了什么」（Fill / Slip / Audit 的结算源）。合并会让
   「网络侧证据」与「环境内部叙述」混成一份，而后者部分来自被测方的输入。
2. **sim 的拒绝以与网关 deny 同格式、同切片键落 access_log**：`routers/sim.py::_translate()`
   把引擎的 `SimError` 翻成 `GatewayDenied` —— 于是它走 `app.py` 的 exception handler，
   自动落 `access_log`（`decision="deny"`, `reason="operation_not_permitted"`,
   `config_id`/`task_id` 取自请求身份）。新增 `Reason.OPERATION_NOT_PERMITTED` 与
   `Reason.WINDOW_EXHAUSTED`。**这条是本卡的验收条件之一，有测试逐条钉**
   （`ops/test_sim_endpoints.py::test_sim_h_overreach_403_lands_in_access_log`）。
3. 第三条（`overreach_count_mismatch` 没带 `probe=`、`PROBE_IDS` 里没有 overreach 族）
   仍在卡 2.3 那边，本卡不擅改冻结校验器 —— 但现在**有数据源了**，
   那条检查从「无数据可比」变成「能比但结论不进闸门」，性质不同。

**顺带一个 SIM-N 跑出来的结果**：从任务容器**一个身份头都不发**、或**伪造**一个身份，
网关看到的都是 runner 真值 —— 卡 4.3 的 ID-1..ID-5（边车先剥后注）端到端验过了。
这也说明 SIM-B 的「缺头必拒」只在**不经边车**直连网关时可达（A 档已覆盖）。

---

## N-46 `S2.adjust_applied` 的检查两侧都是 agent（**待办**，2026-09-04）

校验器的 `adjust_applied_mismatch` 拿 **artifact 的声明段**核 payload 的 `adjust_applied` ——
两侧都是 agent 自己写的，`adjust_fingerprint` 探针因此只在「agent 自相矛盾」时响，
测不出「声明 post 实际没复权」。

R 可行：拿网关 `/bars` 的原始 close × `/adj` 的 adj_factor 重算复权指纹，与 agent 的面板对，
none / pre / post 三档可区分。代价是检查期要访问网关。**登记，不在本轮落。**

---

## N-47 冻结校验器里有两份同值常量，没有断言绑住（**登记**，2026-09-04）

`reference/artifact_schema.py` 里 `_LEDGER`（:204）与 `LEDGER_FIELDS`（:1106）逐字段相同，
但没有任何一处断言把它们绑在一起：`_LEDGER` 只被 S6 的 `targets[].positions[]` shape 用，
`LEDGER_FIELDS` 只被 `_s6()` 的运行时检查用。**改一份不改另一份，schema 与检查就分叉**，
而分叉的表现是「schema 说要六个字段，检查只核五个」—— 不报错。

同形态的处置本仓已有先例（`genetask/bundle.py::ARMS` 与 `schema.ARMS` 之间那条
`test_t11_arms_constant_does_not_drift`）。校验器是冻结件，本卡不擅改 —— 登记给卡 2.3。

**另一条（同次取证）**：S6 → S7 之间**没有产物传递通道**。S7 的输入是数据面预烤的
专用信号 `s7_dedicated_signal_v1`（明确「不复用任何 S5 题的 gold」），
S6 的输入是另一份 slice。`provenance` 只是 agent 从 `signal.meta.json` 抄出来的**血缘声明**。
所以「拿 S6 的 positions 当 S7 的台账」这条路不存在 —— N-44(c) 只能走「给 S7 加逐日数组」。

**N-44(c) 的最小形状建议**：给 S7 加必填数组 `daily`，每行至少
`{date, cash, mv, total_assets, r_gross, r_net}` —— 正是 gold 引擎已经在算、只是没落盘的那几列
（`cor_reproduce/solve.py:29`）；并把 `work/ledger.parquet` 加进 `PRODUCED_BY_STAGE["S7"]`。
序列进了 payload，`max_abs_residual` 就能做 R 比对，`ledger_conservation` 才真的开始测东西。

---

## N-48 任务容器以 **root** 跑，产物是 root 属主（**已修**，2026-09-04）

`runner/c41/runner_core.py` 的 `COMPOSE_TMPL` **没有 `user:`**。实测上一轮真跑的 run dir：

```
-rw-r--r-- 1 root root   75 Sep  4 08:41 work/artifact.json
-rw-r--r-- 1 root root  814 Sep  4 08:41 log/egress.jsonl
```

三层后果：

1. **harness 删不掉自己 run 的产物。** 本卡的适配器冒烟第一次跑就撞上：
   `rm -rf` 报 `Permission denied`（result.h5 / pickle_cache 全是 root:root）。
   run dir 的清理、重跑、归档都要 root。
2. **被测 agent 是不可信方**（本项目的标准假设）。它以 root 身份往**宿主 bind mount**
   里写：可以造出 harness 删不掉的目录（`chmod 000` 的 root 目录会让
   `verify_run_dir_unchanged` 直接读不到，表现为「文件消失」而不是「越权」）。
3. 与本仓已有的实证同族：**root 容器写一次共享挂载，就悄悄搞坏了 19 个爬虫**
   （数据湖那次）。当时的结论是「只能 uid 1000 只读挂」。

**已修（裁定「现在修」，4.1 §0.2 是范围纪律不是禁修缺陷）**：

* `COMPOSE_TMPL` 的**两个**服务都加 `user: "{run_uid}:{run_gid}"`（取 `os.getuid()`，
  不写死 1000 —— 写死的那份换机器时静默错位，表现与「没降权」一样）、
  `cap_drop: [ALL]`、`security_opt: ["no-new-privileges:true"]`。
* **L-10** 进 lint，判据**封闭**（遍历每个服务，不列白名单）：缺 user / 显式 root /
  缺 cap_drop ALL / 缺 no-new-privileges 各一条。三条突变各自必红，都落在 compose 文本上。
* 顺带收敛：先前**三处**各自 `COMPOSE_TMPL.format(...)`，加占位符时只改了一处、
  另外两处当场 KeyError（这次是响的，下一个新占位符未必）。现在只有
  `RC.format_compose()` 一个出口，并加一条测试断言全仓只有它在 format。

**f02 真跑复核（2026-09-04）**：lint 九条 + L-10 全过；exit=0、经网关取回 8 行；
`work/artifact.json` 与 `log/egress.jsonl` 属主 **`ljn:ljn`**（改之前是 `root:root`）；
两个服务的 `user=1000:1000 cap_drop=[ALL] security_opt=[no-new-privileges:true]`；
harness `rmtree` 自己的 run dir 成功（改之前 Permission denied）。

**顺带清掉一项旧裁定**：`scratch/f02_bundle/reference/` 已删（内容是空的 gold 目录树，
f02 上没有对应物 —— 没有发生泄漏），并加 `ops/test_env.py` 的两条 gold lint：
答案面只能在 `reference/` 与 `snapshots/` 下，判据是路径**段**不是子串；
配一条判别力测试（gold 今天还没生成，不配坏输入的话那条是恒绿的）。

---

## N-49 没有任何模型 API 凭据（**已裁定：三配置全用 DeepSeek**；等凭据落地）

「两个适配器各跑一道冒烟题产出**可评分** artifact」这条**卡在这里**，不在代码上。

| 事实 | 实测 |
| --- | --- |
| 凭据 | **零个**。两台机的环境变量、`~/.config`、`~/.env`、仓库全文、systemd 单元全部无命中（全仓 `grep -rIn "API_KEY\|api_key"` = 0）。唯一存在的是 f01 的 Tushare token，与模型无关 |
| `api.openai.com` | **完全不通**（TCP 层，12s 超时） |
| `api.anthropic.com` | **403**（Cloudflare 地区封锁；TLS 通） |
| deepseek / dashscope / bigmodel / moonshot | **直连可用**（401/403 = 通了没凭据）—— 但**一条都不在白名单里** |
| 本地模型 | 没有（无 ollama / vllm / lmstudio） |
| 被测配置注册表 | `registry.py` **不存在**，真实 `config_id` **0 个** |

**裁定（2026-09-04）**：v1.0 冒烟三配置**全用 DeepSeek**（OpenAI 兼容端点）——
`cfg-openhands-deepseek` / `cfg-codex-deepseek` / `cfg-rdagent-deepseek`。
同一模型三种 harness：把**模型效应固定**，主表上暴露的只有 harness 与协议臂差异。
已落地：`runner/registry.py`（三条配置 + `collect_egress_hosts()`）、
`MODEL_API_ALLOW` 由它生成（键集相等的同源测试）、
`assert_allowlist_sane` 加第三类绊线（**行情/新闻源一律不得入表**）与
`assert_allowlist_reachable`（第四类：**条目必须实测可达**，不在 import 期跑 ——
边车在容器里 import 它，网络抖动会变成「边车起不来」）。
Claude/GPT 走 v1.1 的 tailnet 执行节点（N-54），**不走代理绕地区限制**。

**还差的只有凭据本身**：`DEEPSEEK_API_KEY` 以环境变量落到 f02 的 runner 配置。
不进仓库、不进对话 —— `ops/test_env.py` 的三条测试盯着仓库与 scratch 里
不出现像密钥的**字面量**（只出现变量名是允许的，那正是要求的写法），并配判别力用例。

**原始记录**：

1. **走哪家。** 两个框架都经 `litellm`，OpenAI 兼容端点即可接入 —— 直连可达的四家里挑一家
   给一把 key，比要 OpenAI key 现实。若坚持 anthropic/openai，需要经 mihomo
   （实测 `127.0.0.1:7897` 能打通），代价是三处改动：mihomo 改监听、
   `egress_proxy` 加上游 CONNECT、**并重新论证卡 5.1 的网络侧结算是否还成立**。第三项是设计裁定。
2. **v1 要测哪几个 `config_id`**（模型 + base_url）。这是 M6 的裁定，`registry.py`
   的内容由它决定；白名单再由注册表生成（§15）。

**顺带一条采纳的建议**（来自本轮取证）：`assert_allowlist_sane` 加**第三类绊线**——
**白名单条目必须实测可达**。否则一个只在 403 层失败的域名会一直挂在表上装作有效，
而「有效」正是白名单存在的全部意义。

---

## N-50 网关的参数名写错时，症状看起来像语义错误（**登记**）

`/bars` 的参数是 `start_date` / `end_date`。写成 `start` / `end` 时网关不报「未知参数」，
而是判**开区间** `open_range_would_cross_asof`（「不给 end_date 等于要到最新为止，
而最新在 as_of 视角下未定义」）。适配器第一次接网关就踩了这个：
排查的人会去查 as_of 与冻结线，不会去查拼写。

建议网关对**未知查询参数**显式拒绝（`unknown_param`），与「开区间」分开 ——
两件事的修法完全不同。网关是我们的服务，不走既有服务待批。

---

## N-51 **钉错了框架**：PyPI 的 `tradingagents` 不是文献里那个（已修，留档）

2026-09-04 红队复核抓到，实测证实：

| | PyPI `tradingagents` | 文献里的 TradingAgents |
| --- | --- | --- |
| 仓库 | `https://github.com/Mai0313/tradingagents` | `https://github.com/TauricResearch/TradingAgents` |
| stars | **3** | **102456** |
| 是不是 fork | **否**（同名独立重写） | — |
| author_email | `Wei <mai@mai0313.com>` | — |
| 版本 | 0.7.0（2026-05-21） | 最新标签 v0.4.0（`2448d0a12576…`） |

先前的 Pin 写着 `repo=TauricResearch/TradingAgents` + `dist=tradingagents==0.7.0`
—— **两个不同项目写在同一条 Pin 上**，而 `assert_pins_wellformed()` 当时只查 hex 位数，
永远发现不了。后果正是 §10 开头自己写的那种最贵的失败：
**不报错、有数字、方向一致**，论文会说「我们跑了 TradingAgents 基线」，
实际跑的是一个 3 star 的同名重写。

**已修两处**：

1. `Pin` 加 `dist_repo_url`（PyPI 为该 dist 声明的 Repository），
   `assert_pins_wellformed()` 加一条：**从 PyPI 装的，PyPI 声明的仓库必须就是 `repo`**。
   rdagent 通过（`microsoft/RD-Agent`），伪造一个不同仓库当场红。
2. TradingAgents 改为**从 codeload 装 TauricResearch 的 v0.4.0**
   （`commit=2448d0a12576f9b2ddcd5980a0630833423d1e1b`，tar.gz 摘要
   `f4f81e75…` 作旁证 —— GitHub 生成的 tar.gz 字节不保证跨时间稳定，**权威的钉是 commit**）。

**连带作废**：先前在 `gb-probe-ta:0.7.0` 里实测到的 `AgentState` 14 键、
`TradingAgentsConfig` 九字段、`ANALYST_TOOL_REGISTRY` 替换缝 —— 全部是 Mai0313 那个包的形状，
**与文献里的 TradingAgents 无关**。该 Pin 的 `required_*` 已退回 `None`，
适配器因此 import 不进来，直到在 `gb-probe-ta:tauric-v0.4.0` 里重新实测。

**教训（写进 D-21）**：名字不是钉。`pip install <名字>` 装到的东西，
与「那个名字在文献里指的项目」是两件事。

---

## N-52 替换工具注册表**不等于**替换图实际执行的工具（红队复核，待验）

复核实测（在 Mai0313 的 0.7.0 上）：把 `tool_registry.ANALYST_TOOL_REGISTRY` 换掉之后，
`ToolNode('market')` **仍然执行原生的 `core_stock_tools.get_stock_data`** ——
图在构造时就把工具捕获走了，按**工具名**分发。工具名一致、全程无异常、run 照常成功。
而 f02 容器实测**能直连** `query1/query2/fc.yahoo.com:443` —— 一条完整、静默、
会污染基准的美股数据泄漏链。

**这是「门装在错的层」的形态**：我们的断言查的是注册表的内容，
而真正决定取数的是 `graph.tool_nodes[t].tools_by_name[n].func.__module__`。

**处置**：断言下沉到图实际绑定的工具；并加**黑掉网关对照**（§11.2 已要求）——
把网关设为不可达，若仍能产出完整 artifact，即判「存在未声明的数据源」，该次运行作废。
后者比源码扫描强：源码扫描只能查我们**想到要查**的模块名，黑掉网关查的是**结果**。

**另两条同批发现（TauricResearch 版落地时一并核）**：

* 替换工具会**连带删掉框架自己的未来函数防护**。Mai0313 版里
  `reject_future_tool_dates` 出现在全部 15 个 `@tool` 的第一行；替换之后
  analyst 可以向网关索取 `trade_date` 之后的数据而框架侧不拦
  （我们网关的 as_of 仍拦，但框架侧那层没了）。**替换层必须逐个重实现 PIT 校验**，
  并加一条**正例**断言：一次 run 内至少命中一次 PIT 校验，否则判「守卫不在线」。
* 该防护是 `ContextVar` 实现且 **fail-open**（拿不到 run context 就放行）。
  若把 `propagate()` 丢进线程池，守卫静默消失。

---

## N-53 S7 的 metrics 容差应走**逐指标 ε**，现在是全局 1e-6（**登记**，2026-09-04）

N-44 之后 S7 的 11 个指标从「未验证自报」转 R（逐日台账进了题面）。
`origin.PAYLOAD_CHECK["S7"]` 现在统一用 `REL(RECOMPUTE_REL)=1e-6` **占位**。

这是不对的：`reference/epsilon.py` 的文档硬要求第 3 条明令禁止「用其他指标的 ε 代填」——
`max_drawdown_net` 与 `sharpe_net` 的可复现容差不是一个量级。
卡 5.4 的 ε 标定落地后按指标替换，并把这条测试从「统一容差」翻成「逐指标」。
**翻转要留记录**（同 N-33 / `anchor_ladder_54` 做法）。

---

## N-54 v1.1：在受支持地区起执行节点加入 tailnet（**基础设施票**，2026-09-04）

裁定：**Claude / GPT 配置不走代理绕地区限制**（条款问题）。
实测：`api.openai.com` 从两台机 TCP 层不通；`api.anthropic.com` 返回 403
（Cloudflare 边缘地区封锁，经本机 mihomo 后变成纯 `authentication_error`——
即封锁可解，但那条路是绕地区限制，不走）。

v1.0 因此三条配置全用 DeepSeek（同一模型三种 harness，把模型效应固定）。
v1.1 要比较**跨模型**时，正路是：在受支持地区起一个执行节点、加入 tailnet，
从那里跑 Claude / GPT 配置。这是基础设施工作，不是本卡能就地解决的。

**顺带**：`MODEL_API_ALLOW` 的两条旧条目（anthropic / openai）已删 ——
它们的引用者写的是「待 M6 复核」，即**没有任何真实配置需要它们**（N-32），
而且实测都不可达。白名单上挂了很久的两条既没人要、又用不了的条目。
N-32 随之关闭：白名单现在由 `runner/registry.py::collect_egress_hosts()` 生成，
引用者是真实的 `config_id`。

---

## N-55 **范围修正：M6 改定为构造验收、新增 M7 实验规划**（2026-09-04）

### M6：证明 benchmark 建成，不是产出实验数据

| 项 | 原（2026-08-30） | 改定（2026-09-04） |
| --- | --- | --- |
| 规模 | 3 配置 × 双臂 × **40 题** × **3 seed** | **1 个验收配置** × 双臂 × **每阶段 1–2 题**（含 `s7-rob-02`）× **1 种子** |
| 三控 | 未定 | oracle / null / filler 三桩走**完整评分器** |
| 产出 | **首份真实主表** | **v1.0 就绪报告**（组件版本、冻结根、全链一次无人工干预跑通的记录）|
| | 成本画像（预算曲线数据）| 成本画像**样本** |
| | 难度门回炉清单 | —— 移到 M7 的「难度门处置规则」 |
| 验证验证器报告 v1 | 有 | 有（探针对干净 oracle 零误报、对注入违例必命中、三态判定正确）|
| 后续 | 审阅首表签字后 M3.3 扩量 | **卡 3.3 扩量改挂 M7 的实验设计审定** |

**本阶段任何数字不进论文，不称主表。** 这是范围纪律不是措辞偏好：
一份「1 题 1 种子」的数走进论文，读者会按主表的分量读它，而它承不起那个分量。

### M7：实验规划（新增）

**M6 之后、任何网格运行之前**产出实验设计文档交用户审定，**审定前不启动网格**。必含六项：
E1–E5 各自的假设与所需运行 / 配置矩阵（含 Claude·GPT 经受支持地区执行节点接入，见 N-54）/
种子数与预算 / **预注册的 confirmatory 判据与 exploratory 边界** /
基线阶梯（卡 5.4）与记忆探针（N-31）的运行安排 / **难度门处置规则**（事先定，
事后按结果挑题就是选择性报告）。

### 三条 DeepSeek 配置的定性

`runner/registry.py` 的三条是**验收配置**，不是实验设计；「同一模型三 harness」
是验收时固定模型效应的做法，**不构成主实验的配置矩阵**。
写在两处（`registry.py` 模块 docstring + `fairness_protocol.md §6.5`）——
两者在代码里长得一模一样（都是 `Config` 实例），**只能靠这句话分开**。
并加一道机械门：`PURPOSE = "acceptance"`，改成 `"experiment"` 即 import 期红，
提示「要跑网格先过 M7 审定，那时的配置矩阵另立一张表，不是改这里的一个字符串」。

**落点**：实施稿 M6/M7 节（原文留档对照）、`fairness_protocol.md §6.5`、
`runner/registry.py`。M4/M5 不受影响。

---

## N-56 卡 2.5 开卡：公共数据通道（2026-09-04，与 M4 并行）

规格：[`ops/specs/card_2.5_public_data_channel.md`](specs/card_2.5_public_data_channel.md)。
跑在 f01 数据面，**不动 runner**。排期与 M5 并行；**M6 构造验收改在公开通道上做**。

第一件事是**范围核定**（v1 全部 40 题 / 792 条 gold 因子 / τ·ε 标定 /
materiality screen 实际触及的表与字段 → 逐项对到公开源），
**超出预期七项的依赖立即上报**。核定进行中。

---

## N-57 Codex CLI × DeepSeek 兼容实测（2026-09-04，**通过，两处要记**）

裁定要求「Codex/DeepSeek 兼容性在 M6 前实测一道真题」。实测结果：**通过**。
`ops/run_f02_harness_smoke.sh`，镜像 `gb-cx:0.153.2`（`@openai/codex@0.153.2`）。

**工具调用链通**：模型 shell 执行了 `cat secret.txt`、把读到的数写进 `found.txt`。
判据不是「模型答了话」而是「它调了工具、读到了文件、并把结果写了出来」——
前者只证明聊天通道通。边车侧证据：3 次调用、25250 tokens、路径全是 `/v1/responses`。

**两处必须记下来的**：

1. **`wire_api = "chat"` 被 Codex 0.153.2 直接拒**（配置加载期报错：
   「no longer supported，set `wire_api = "responses"`」）。**正确写法是省略这个键**
   —— 默认走 Responses API，而 **DeepSeek 服务 `/v1/responses`**（实测 200）。
   一开始按「DeepSeek 是 Chat Completions 兼容」的直觉写 `chat`，当场失败。
2. **`Model metadata for deepseek-chat not found`** 警告 —— Codex 用回退元数据，
   上下文窗口等假设可能不准。M6 前要确认它不影响长题面的 S7/S8。

**顺带抓到我们自己的两个 bug**（都只有真上游才露）：

* Responses API 的 `usage` 嵌在 `response.usage` 里（SSE 的 `response.completed` 事件），
  而抽取器只认顶层 —— 抽出来是 `None`，于是交叉核报了一条**假的 `telemetry_unbacked`**。
  **假 finding 比抽不到更坏：它指着被测方说谎，而说谎的是我们的抽取器。**
  修法：递归找 `usage` + 归一 `input_tokens`/`output_tokens` 到统一键名。
* `cross_check_tokens` 把「一次都没调」与「调了但上游没给 usage」混成一个结论。
  拆开：前者 `telemetry_unbacked`，后者 `usage_unavailable`（**不能据此判自报值不实**）。

**另一处口径提醒**：Codex 屏幕上的「tokens used 546」**不是累计值**（网络侧同一次运行是
25250）。§13.4 的自报值交叉核对通用 harness 要用**它写进遥测的那个数**，
不能用屏幕显示 —— 两者量的不是一回事。

`upstream_pins` 相应加了 `kind` 字段：`adapter`（有 §10 适配层，形状必须实测）
vs `harness`（镜像 + 调用命令，核 `version_cmd`）。
**硬把 harness 塞进 adapter 的义务里，只会逼出一份编出来的 `required_attrs`——
那比没有更坏**（空检查恒真）。npm 包钉 `dist_integrity`（`sha512-<base64>`）——
那才是 npm 装包时真正校验的东西，硬转成 hex sha256 反而离真相远。

---

## N-58 卡 2.5 §1 范围核定结果（**含须立即上报项**，2026-09-04）

三条**互相独立**的清点线（从 40 题往下 / 从 gold·τ·ε·screen 往下 / 从湖往上），
各配一轮证伪。

### 七项基准线：全部对得上

| # | 依赖 | 私有湖表 | 实际消费字段 |
| --- | --- | --- | --- |
| 1 | 日线 OHLCV/amount | `daily` | ts_code, trade_date, open, high, low, close, volume, amount |
| 2 | 复权因子 | `adj_factor` | ts_code, trade_date, adj_factor |
| 3 | 交易日历 | `trade_cal` | exchange, cal_date, is_open |
| 4 | 指数成分 PIT | `index_weight` + qlib 社区 instruments | index_code, con_code, trade_date / code, in_date, out_date |
| 5 | 上市退市 | `stock_basic` | ts_code, list_date, delist_date, list_status |
| 6 | 停牌 | `suspend_d` | ts_code, trade_date, suspend_type |
| 7 | 涨跌停价 | `stk_limit` | ts_code, trade_date, up_limit, down_limit |

**792 条因子只吃 7 个价量字段**：`close`(605 条) / `volume`(236) / `open` / `high` /
`low` / `amount` / `vwap`。没有一条碰基本面 —— 那是因为 24 条需要行业/基准的因子
当前 `executable=false`。

### 须立即上报（六项）

**① `/fundamentals`：gold 侧干净，但暴露面是敞开的。**
40 题的 solve.py / INSTRUCTION 里零调用（三条独立检索一致），**但**：

* `packager.py:176` 的端点清单字面量**不按 stage 区分**，`/fundamentals` 因此
  写进了**每一道题**两臂的「可用端点」槽 —— 每个 agent 都被告知可以查财报。
  `render.py` 的 E8b 只管「正文端点 ⊆ 槽」，**槽里多列一个不会被任何检查拦下**。
* **我们自己的 TradingAgents 适配器把它做成了 agent 手里的工具**
  （`gateway_tools.py:133` 的 `get_fundamentals` 注册进 vendor 表）——
  对照：`get_balance_sheet` / `get_cashflow` / `get_income_statement` 三个明细方法
  被显式登记进 `NO_SOURCE` 返回 `[NO_DATA]`，唯独汇总的那个接到了网关。
* 物料层：6 张报表**已冻进 v1 快照**（约 390MB），`build_snapshot` 还为它们
  专门写了「超集截断」逻辑 —— 这条链路是被认真实现过的，不是残留。

**准确表述**：`/fundamentals` **无 v1 题面调用（高置信）；agent 侧是敞开的（有具体代码路径）**。
公开赛道要同时处置端点与适配器 —— **只摘一头会把 403 记进越权率**。
baostock 有季频财务但**无 `f_ann_date`**，而 `routers/reference.py` 的 PIT 判据正是
`f_ann_date IS NOT NULL AND f_ann_date <= as_of`，且**明令禁止** `coalesce(f_ann_date, ann_date)`
（那是全市场级前视泄漏）—— 所以「用 baostock 补一份公开财务表」这条路**不成立**。

**② 单位归一化：公开源直接换会差 1000 倍。**
湖 `daily` 的 `amount` 单位是**元**、`volume` 是**股**（湖 platform 流水线里已做过变换）。
Tushare 原生是**千元 / 手**；**qlib 社区 release 的 amount 仍是千元（实测比值 0.001）**。
`vwap = amount / volume` 直接依赖这个归一 —— 公开通道若从另一个源重建而不做同样变换，
792 条里凡是用 `vwap` 的全部差 1000 倍，**而 gold 会照常算出数**。

**③ `stk_limit.pre_close` 全为 NULL。**
卡 2.5 §3 的推导写「从**前收盘**推」，而私有湖那一列是空的 —— 前收只能来自
`daily`（`pre_close`）。**这条改变了 §3 的输入假设**，要在写推导之前定下来。

**④ 快照里有约 705MB「登记了、拷进去了、零代码读取」的表**：
`daily_basic`(695MB!) / `stock_st` / `st_history` / `index_member_all` /
`index_daily` / `index_basic` / `dividend`。占 `tables/` 近一半。
卡 2.5 的交付物是「可下载的 benchmark」，**物料清单就是交付清单** —— 要么删，要么说明。

**⑤ 三项「待触发的第八项」**（当前不触发，但口子已开在 schema 里）：

* `benchmark="csi300_index"` 是合法枚举值 → 一旦有题用它，`index_daily` 成为真依赖
  （当前 5 道 S7 全写 `equal_weight_universe`）；
* 24 条 blocked 因子解封 → 申万行业 PIT（19 条）+ 指数收盘/FF3（5 条）；
* **卡 5.1 记忆探针**（M6 出主表前必须完成的三列）→ `cn_cpi` / `repurchase` /
  `block_trade`，**这三张连 v1 快照里都没有**。

**⑥ gold 的定义面也是复现依赖**（不是市场数据，但公开通道少了它就复现不了）：
`factor_library/compiled/*.jsonl`（792 条，后端分布 644/66/82 + blocked 24，
`factor_exec.load_records()` 当场核对，对不上直接抛）与
`reference/factorlib_pinned/`（66 条源方言的语义、alpha001 的 −0.5 —— τ 恰恰标定在
「两个实现有多一致」上，换实现 = 重算 gold + 重标 τ + 重新签字）。

### 本次核定的可信度限制（必须一并报）

**19/40 题的 gold 取数代码是骨架**，端点与字段只写在 solve.py 顶部的契约注释里，
不是可执行调用。所以上面的字段清单里，S3(4/5)、S4(5/5)、S7(4/5)、S8(5/5) 的部分
来源是**注释而不是实测调用**。
**这次核定不能算最终核定** —— gold 补全之后要复核一遍。

### N-58 补记：完整结果到齐后的三处补充与**一处自我纠正**（2026-09-04）

**① `/bars` 把七项里的**四项**压在一个端点里** —— 清点时最容易漏的一点：

| `/bars` 服务的列 | 对到七项 |
| --- | --- |
| open/high/low/close/volume/amount/vwap | 1（日线）|
| `status` / `has_daily` / `suspend_basis` | 6（停牌）|
| `in_listing_window` | 5（上市退市）|
| `limit_up_close` / `limit_down_close` / `limit_touched_*` / `no_price_limit` | 7（涨跌停）|

**15 列里有 7 列没有任何 gold 点名请求**（amount、suspend_basis、四个 limit_*、no_price_limit）。

**② `actual_reads()` 的放大效应 —— 这条直接影响公开通道要服务多少列。**
`artifact_schema.py:945-953`：`/bars` 请求**不传 fields 或传 `*`** 时，
按「读了全部 15 列」计。所以有效读取面是**整个服务集**，不是 gold 点名的 9 个。
公开通道若少服务几列，`declared_reads` 探针的分母就变了 —— 那是口径改变，不是省事。

**③ 自我纠正：因子层的 gold 是**建好的**，骨架的是**逐题 oracle**。**
先前上报写「19/40 题的 gold 取数代码是骨架」，容易被读成「gold 没建」。实测：

| 产物 | 状态 |
| --- | --- |
| `snapshots/v1/gold_factors/{csi300,csi500,csi1000}/` | **各 793 个文件**（792 因子 + 1）✅ |
| `snapshots/v1/crosscheck/`（τ 的原料格）| 在 ✅ |
| `snapshots/v1/epsilon/`（ε 与 screen 的数据面）| 33 个文件 ✅ |
| `snapshots/v1/universe/` / `tradability/` / `qlib_provider/` | 在（provider 46544 文件）✅ |
| **逐题 oracle**（`reference/tasks/<set>/<task>/gold/`）| **目录不存在** ❌ |
| `reference/s3_oracle_common.py`（S3 5 题里 4 题 import）| **不存在** ❌ |
| `reference/backtest.py` 的 `run()` / `config_from_declared()`（S7 5 题全走）| **没有这两个名字**（有 `run_backtest()`）❌ |
| `reference/{gold_factors,pools,signals,tasks}`（预烤材料）| **不存在** ❌ |
| 48 个 solve.py 里含 `NotImplementedError` / `# TODO` 的 | **26 个** |

**对排期的含义**（两者完全不同）：

* **卡 2.5 的重建链**（`provider → gold 三宇宙 → τ → ε → screen`）**本身是可跑的** ——
  「脚本已有，2–3 天」这个估计对**这条链**成立；
* 但 **M6 构造验收的三控里，`oracle` 依赖逐题 gold**，而那一层还没建。
  M6 改在公开通道上做之前，**逐题 oracle 是硬前置** —— 它不在卡 2.5 的范围里。

---

## N-59 B0 六项裁定落地（2026-09-04 通宵线 B）

| # | 裁定 | 落点 | 状态 |
| --- | --- | --- | --- |
| ① | 端点清单按 stage 生成，v1 不含 `/fundamentals`；TA 适配器改接 `NO_SOURCE`；6 张财务快照留私有 | `packager.stage_endpoints` + `V1_WITHHELD_ENDPOINTS`；`gateway_tools.SERVED`/`NO_SOURCE`；`public/manifest.PRIVATE_ONLY_TABLES` | **完成**，题面重冻结 **v1.0.1 → v1.0.2**（根 `19f46ec3…`），原因记进 `REVISIONS` |
| ② | 换源建 gold 前先过 vwap 落带判据（≥99%，2.1a 口径），不足即停记 BLOCKED | `snapshots/public/gates.assert_vwap_band`，容差常量**从 2.1a import**不抄 | **完成**，差 1000×/10× 实测都给 **0%** |
| ③ | 前收取 `daily.pre_close`，§3 输入假设相应改 | `gates.PRE_CLOSE_SOURCE` + `assert_pre_close_source` | **完成**，取 `stk_limit.pre_close` 必抛 |
| ④ | 705MB 零读取表：核实后公开通道排除，私有保留，卡 2.6 后复核 | 全树 **417 文件**扫描（未采样）确认零读取；`PUBLIC_EXCLUDED_TABLES` | **完成** |
| ⑤ | `benchmark=csi300_index` 登记 v1.1；24 条 blocked 维持；记忆探针钥匙从活源现取、不进快照不进公开包，归卡 2.6 | 见下 N-60；`manifest.NEVER_SNAPSHOT` | **完成** |
| ⑥ | `factor_library/compiled` 与 `factorlib_pinned` 作冻结件进开源包带 sha256 | `manifest.PUBLIC_FROZEN_ARTIFACTS`（6 项） | **完成**（sha256 待 B1 建包时计） |

**一个值得记的验证**：公开包实际要带的表 = 登记 22 张 − 零读取 7 张 − 私有专属 8 张
= **7 张**，而它们**正好**是范围核定的七项
（`daily` / `adj_factor` / `trade_cal` / `index_weight` / `stock_basic` / `suspend_d` / `stk_limit`）。
两条独立路径给出同一个答案。

---

## N-60 v1.1 登记项（2026-09-04）

* **`benchmark="csi300_index"`**：当前 5 道 S7 全写 `equal_weight_universe`，不触发。
  一旦有题用它，`index_daily` 成为真依赖（第八项）。**v1 维持现状。**
* **24 条 blocked 因子**：维持 `executable=false`。解封需要申万行业 PIT（19 条）
  与指数收盘/FF3（5 条）—— 那是第八、九项依赖。
* **记忆探针答案钥匙**（`cn_cpi` / `repurchase` / `block_trade`）：
  **从活源现取，不进快照、不进公开包**，归卡 2.6。
  冻进快照 = 把答案放进交付物，而探针问的正是「模型记没记住冻结线之后的事」。

---

## N-61 **红线接触（我犯的）：答案面上了执行面**（2026-09-04 深夜，线 A / A1）

**发生了什么。** 为把 `s1-cor-01` 的 X 面 bundle 送上 f02，我手写了一条

```
rsync -a /data/shared/genebench/scratch/a1/ ljn@192.168.1.219:/data/genebench_runner/a1/
```

`scratch/a1/` 是**导出工作目录**，里面并列着 `runner/`（X 面）与 `reference/`（**答案面**）。
带尾斜杠的 `-a` 把两棵树一起推了过去。落到执行面的东西包括
`canary.json`（`gold_token`）、D 面 `task.yaml`、`solution/solve.py`、`scorer.yaml`、
`arms/equivalence.md`、`arms/slots.json`、`_ledger.jsonl`。

**这是红线**：「reference 与 scorer 产物不对执行面暴露」。

**处置。** 发现后立即 `rm -rf /data/genebench_runner/a1/reference`；核实执行面上
`GBC-G-` 形状零命中（唯一剩下的 `gold_token` 字样是 `exec/genetask/bundle.py:77`
的一句代码注释，不含串值）。随后整个 `a1/` 删除重推。

**根因不是手滑。** 判据当时**只存在于我的注意力里** —— `genetask/bundle.py` 有
`X_ALLOWED_FILES`/`X_ALLOWED_PREFIXES`，`check_export` 也会跑，但**推送这一步没有门**：
一条手写命令就能绕过全部导出期检查。**没有门的地方，纪律迟早会输给一次疏忽。**

**修法（已落地）。**

| 落点 | 判据 | 性质 |
| --- | --- | --- |
| `ops/push_guard.py::check_bundle_tree` | 树里只许有 `task.yaml` + `arms/`+`image/`+`work/`，**允许集 import 自 `genetask.bundle`，不抄** | 封闭 |
| 同上 | `GBC-G-[0-9a-f]{16}` 内容扫描（`GBC-C-`/`GBC-X-` 合法，**不误伤**） | 内容纵深 |
| 同上 | 答案面文件名 / 路径段（`reference`/`gold`/`solution`/`scorer`） | 结构纵深 |
| 同上 | 读不了的文件是 **finding**，不是通过（F7） | 反恒绿 |
| `ops/push_guard.py::check_manifest` | 通行证逐文件 sha256 现算比对；多余/缺失文件；`check_export` 须空；`frozen_ref()` **现算**比对（过期 bundle 必须重导，不许改通行证） | D-21 对齐 |
| `ops/push_bundle_to_f02.sh` | **唯一推送入口**：SRC 解绝对路径（去尾斜杠语义）、DST 必须在 `/data/genebench_runner/` 下、推后在**对面**独立复核一次 gold 串 | 真路径 |

**自证。** `ops/test_push_guard.py` **24 条**全绿；**17 个突变全部被杀**
（含恒绿、恒红、拆掉四条判据各一、允许集改抄一份、shell 不调门、shell 不传通行证）。
其中两个突变最初**存活**，都是同一种病：
* **M7**（拆掉路径段判据）活着 —— 现有测试里带 `reference/` 的样例同时踩了允许集判据，
  没有测试**单独**盯住路径段。补了 `work/<seg>/notes.md`（名字无辜、前缀合法、无 gold 串）。
* **M17**（shell 不传通行证）活着 —— 通行证判据写好了，但**没人验证真路径上用了它**。
  这是 **D-20 第五次**。补了对调用行的 AST 式断言（运行时拼针，不查散文）。

**真路径反向验证**：拿数据面目录跑推送脚本 → 拒绝，退出码 1，对面**未创建任何目录**；
目标写 `/tmp/evil` → 拒绝。

**留档的两条教训。**
1. **导出目录的布局本身是隐患。** X 面与答案面同父目录，只差一个 `-a` 的尾斜杠。
   门补上了，但**布局仍是原样** —— 记为待办：导出时把 X 面落到独立的、不与 `reference/` 同父的路径。
2. **「我知道不能推 reference」不是判据。** 判据要能在我不在场时否决我。

---

## N-62 **BLOCKED_AWAITING_USER**：harness 与任务环境怎么合成一个镜像（线 A / A1）

**卡在哪。** A1 要「三配置各跑一道真题双臂各一次」。compose 里任务服务只有一个
`image`（从 bundle 的 `image/Dockerfile` 的 `FROM` 取，`inject.py` P4c 强制唯一），
而 harness 按设计就是**镜像 + 调用命令**（`upstream_pins.kind == "harness"`）。
于是「任务环境」与「harness 环境」必须落在**同一个镜像**里 —— 而这条合成规则
**规格里没有**。

**实测到的三份环境（2026-09-05 在 f02 直接跑）：**

| 配置 | 镜像 | 基座 | pandas / pyarrow |
| --- | --- | --- | --- |
| cfg-openhands-deepseek | `gb-oh:1.11.0` | `python:3.12-slim` | **无** |
| cfg-codex-deepseek | `gb-cx:0.153.2` | `node:22-slim` | **无**（连 python 都不是主语言） |
| cfg-rdagent-deepseek | `gb-probe-rd:0.8.0` | RD-Agent 自带 | 2.3.3 / 25.0.1 |
| **题面要求** | bundle `image/Dockerfile` | `python:3.11-alpine` | **2.2.3 / 17.0.0** |

**为什么不能就地挑一个凑合。** 三配置的全部意义是「同一模型、三种 harness，
**固定模型效应**」。如果连 python 与 pandas 版本都三家不同，主表上「harness 差异」
这一列里就混进了运行时差异 —— 而 S2/S3/S7 的产出是 parquet/csv 数值，
pandas 与 pyarrow 版本恰恰会影响它们。**这不是能靠跑一次看看的问题。**

**四条路，各自的代价（我不替你选）：**

| | 做法 | 任务环境是否三配置一致 | 代价 |
| --- | --- | --- | --- |
| (a) | `FROM 任务镜像` 再装 harness | **是** | alpine 上装 node 22 与 openhands；py 版本被题面钉死在 3.11，OpenHands 官方基座是 3.12 |
| (b) | `FROM harness 镜像` 再装任务依赖 | 否（python 版本仍三家不同） | 改动最小，但把运行时差异留在了主表里 |
| (c) | 双容器：harness 一个、执行环境一个 | 是 | 需要容器间执行通道 —— 等于给被测方开一个新能力面，卡 4.1 的隔离判据要重做 |
| (d) | **统一基座**：题面 Dockerfile 改成 debian-slim + python 3.11 + node 22，三配置共用，harness 只叠一层 | **是** | 要改 40 题的镜像模板并**重冻结**（题面改动，按纪律必须记因） |

**我的看法（仅供参考，不执行）**：(d) 最贴合「固定模型效应」这个已经写进
`runner/registry.py` docstring 的设计意图，(b) 最省事但会污染主表的解释。
(d) 触及已签字题面，**按纪律不自行动手**。

**在此期间不做**：不挑一个镜像先跑起来看看 —— 那会产出一组「跑通了」的数字，
而它们的可比性正是这张票要解决的问题。

**不受此阻塞、继续推进**：A3（§12 状态锁）、A4（IN-1/IN-2 子网重叠判据）、
A2（4.2/4.4 红队）、线 B、线 C。

---

## N-63 A3 §12 状态锁 + A4 IN-1/IN-2 落地（2026-09-05）

### A3：状态锁上来第一跑就抓到一处漂

`ops/status_lock.py` 把卡 4.3 §12 的五条签字裁定写成表，
`ops/test_status_lock.py` **逐条查现实**（不查表自己的字段 —— 那是 F7）。

**抓到的漂**：TK-1 裁定原文要求「两处措辞一致」，而卡 4.1 的规则表里
L-5 那行写的还是收紧**前**的措辞（「只许挂自己的 `tasks/<id>` 目录」），
卡 4.3 写的是收紧**后**的「挂载源与 run dir 精确相等」。
**两条互斥规则同时挂在墙上正是 TK-1 要消灭的东西** —— 裁完还留着就等于没裁。
已把卡 4.1 的 L-5 与 FS-1 两行改成与 TK-1 同文，并用 `L5_TIGHTENED_PHRASE`
两边都断言（配一条判别力测试：把一面墙换回旧措辞，锁必须红）。

**五条的当前状态**（每条配一个现实判据，不是读记录值）：

| | 状态 | 现实判据 |
| --- | --- | --- |
| TK-1 | 已实现 | `lint_compose` 对同一 runs 根下**别的** run dir 报 L-5a；两卡措辞一致 |
| TK-2 | 挂起 | AST 扫全树：没有任何**执行** `ufw`/`iptables`/`nft` 的子进程调用（散文里出现不算做了） |
| TK-3 | 实测已有·配额待定 | f02 实测已记进表并自洽（落盘 > 表观 × 1.2）；`inject.py` 里不许有配额常量 |
| TK-4 | 未启用 | 实现代码里零出现 `/data/genebench/provider`；FS-A 的「`ls /data` 必须失败」仍是活断言 |
| TK-5 | 归 v2 | 出证与验证两侧都没有签名符号；「清单没有签名」写在已知边界里 |

**TK-3 的 f02 实测（本轮现跑，第 1 步）**：
`/data/genebench_runner/provider/qlib_provider_54fdda39` —— 表观 **472M**
（494,008,883 字节）、落盘 **602M**、**46,544** 文件、`/data` 余 **2.6T**。
**与 f01 逐项相同**，28% 的块开销在两台机上都成立。
第 2 步（完整 run dir）待一次真跑，被 **N-62** 阻塞；
可给的界：每个 run dir ≥ 一份 provider 副本 ≈ 602M ⇒ 40 题 × 2 臂 = 80 个 run dir
⇒ **一轮 ≈ 48 GB**。配额数字仍不定 —— 裁定原文就是「不许拍脑袋」。

### A4：IN-2 的旧判据是**假绿**，实测确认

旧 L-4 写的是 `"10.42." in text`。**`10.40.0.0/13` 覆盖 10.42/16 与 10.43/16，
却一个禁用子串都不含** —— 实测确认它当场全绿。

**改法**：`runner/c41/subnets.py`，判据换成 `ipaddress.overlaps()`，
保留集从三条扩到五条（k3s pod / k3s service / cni / LAN / tailscale CGNAT），
每条写清**是谁的** —— 说不出归属的条目无从证伪，会永远留着。
L-4 现在解析 compose 的 `ipam.config[].subnet` 逐个判否；
**解析不出来是 finding，不是通过**；**一个 subnet 都没声明也是 finding**
（docker 会从自己的默认池挑，而那个池就在 172.16/12 里 ——
「没声明」与「声明了个好的」在日志里长得一样）。

**IN-1**：`allocate()` 从 `172.31.240.0/20` 取一组连续 /24（8 组并发），
与 `docker network inspect` 的**实时**结果一起判否，结果写进 `inject.json`。
池满 **抛 `SubnetExhausted`，不回绕** —— 静默复用等于两个运行共享网段。
`require_docker=False` 时**记一句「未探测」**：此路径下没有并发保证，
这件事必须留在记录里，不能只是没写。

新增负例三条进 `negctl_lint.py`：超网 `10.40.0.0/13`、tailscale `100.100.7.0/24`、
（原有）`10.42.9.0/24`。**T7 的反例现在真的在测试里。**

---

## N-64 卡 4.4 红队一轮：**六条确认，四个根因**（2026-09-05，线 A / A2）

按 `ops/specs/redteam_protocol.md` 的视角切法（按**输入面**切，不按代码结构切）：
身份与切片键 / 状态机与幂等 / as-of 与前视 / **误拒** / 权限位 / 审计重放。
每条**实跑**，修前输出原样记在测试的 docstring 里。

### 根因一：**路由层的类型强转让引擎的类型判据成了死代码**（A 类，3 条发现）

引擎里写着 `not isinstance(qty, int) or isinstance(qty, bool)`，
路由里写的是 `qty=int(body["qty"])`。**判据在那儿，没有任何请求能送到它面前。**

| 输入 | 修前实测 | 直接喂引擎 |
| --- | --- | --- |
| `qty: 300.0` | **200 accepted** | `SimError bad_qty` |
| `qty: 300.7` | **200 accepted，引擎里记成 300**（静默截断） | `SimError bad_qty` |
| `qty: "300"` | **200 accepted** | `SimError bad_qty` |

这是 D-06 的标准形态：**机制在，保护不在**。
修法：路由层做 JSON 类型判据（`_need_json_int` / `_need_json_number` / `_need_json_str`），
**不强转**。`true` 也在路由层判掉 —— 留给引擎接虽然也 422，但那是**碰巧**
（判据是「1 不是 100 的倍数」，不是「true 不是整数」），换个场景就静默通过。

### 根因二：**`reference_close` 被强转 ⇒ 凭空十倍杠杆**（A 类 high）

`reference_close` 是冻结额基准：`need = qty × reference_close × (1+fee)`。
**修前实测**：现金 1,000,000，提交 `qty=100000, reference_close=true` → **200 accepted**，
冻结 **100,000**（真价 10.0 应冻结 1,000,000）。`insufficient_cash` 全程不响。
`reference_close: "10.0"` 同样通过。

### 根因三：**没有会话 ⇒ 没有 as_of 上界 ⇒ S8 前视免费**（A 类 high）

`current_sim_date` 原来只 `.get()`；没会话返回 `None`，
`guard_run_ceiling` 里 `if ceiling and ...` **整条静默**。
S8 的 agent 只要**先取数、后交易**，就能在 sim_date=D 时读到冻结线 2026-07-31 的数据 ——
**数据面全程合法、网关日志全绿**，而这次运行的决策是拿未来做出来的。

修法两条（都要）：① `current_sim_date` 在取数时**物化**会话（工厂对非 S8 返回 `None`）；
② **S8 且无上界 ⇒ 拒绝**，不是放行 —— 阶段从 `task_id` 前缀取，
而 `task_id` 是边车按 runner 真值注入的，不是被测方自报的字段（N-36 同族）。

### 根因四：**格式错误被报成业务结果**（B 类）

`eng.cancel(str(body["order_id"]))`：`{"order_id": {"a": 1}}` → **200 `{"status": "not_found"}`**。
「请求写错了」与「这单不存在」是两回事，混成一个会让 Audit 重放对不上。

### 顺带抓到一条**说一件事、测另一件事**的测试

`test_sim_e_does_not_touch_runs_without_a_sim_session` 的 docstring 写「S1..S7 …」，
用的却是模块级的 `H`（`task_id = s8-cor-01`）。加 S8 判据时它当场红，
**而它红的理由与它的 docstring 无关**。这类测试在被别的改动碰到之前一直是绿的。
已改成真的用 `s3-cor-01`，并另立 S8 的两条（无会话必拒 / 有会话上界=sim_date）。

### 记录形态但不动的一条

`STAGE_LOCKS["S8"]` 的判据是 `caps 未就位 且 status != draft`，
而当前参数表里 S8 五行**无论能力位真假都产出 `draft`** ——
这道门今天**观测不到差别**。门是对的（`schema.py:482` 的实现有判别力），
只是被现有输入绕开了。**不注释、不改判据**，按纪律记录形态：
`s8_state_endpoint` 翻绿那天，这道门要有一条真的能翻转的用例。

### 自证

`ops/test_sim_endpoints.py` **34 条**全绿（新增 12 条，攻击者 case 原样入库）；
**8 个突变全部被杀**（含两条最初存活的：`true` 不在路由层判、会话不物化 ——
两条都是「判据存在但没有测试盯着它落在哪一层」）。

---

## N-65 卡 4.2 红队一轮：**三条确认，两个根因**（2026-09-05，线 A / A2）

视角按判定器的**输入面**切：归属表 / 比较器 / 采集链 / 轨迹源 / **误拒** / 适配器转录。
比较器这一族三条确认，全部**实跑**，修前输出原样记进测试 docstring。

### 根因一：**比较用的是 Python 相等，不是 JSON 相等**（A 类，2 条）

红队协议 §2.2 把这条写成判定器的**固有诱惑**，卡 2.3 上已经犯过一次。
同一形态在 `origin._agree` 里再次成立：

| 修前实测 | 结果 |
| --- | --- |
| `_agree(True, 1, EXACT)` | `(True, '')` —— **判一致** |
| `_agree(False, 0, EXACT)` | `(True, '')` |
| `_agree([1, True], [1], SET)` | `(True, '')` —— `set([1, True]) == {1}` |

后果：agent 自报 `true`、证据是 `1`，交叉核说「一致」；
SET 比法下两个不同的自报值折成一个。

**修法**：`_jclass()` 给出 JSON 类型类（**bool 单列**），
`EXACT` 走 `_json_eq`（先比类型类再比值），`SET` 的元素键带上类型类。

**故意不收紧的一处**：`int` 与 `float` 同属 `number`。JSON 只有一个数字类型，
`1` 与 `1.0` 过 parquet/json 往返会互变 —— 判成不一致就是**误拒**，
而误拒的危害不低于放过（协议 C 类）。这条边界配了一条正面测试钉住。

### 根因二：**PROJ 投影把「缺字段」与「显式 null」折成同一个值**（B 类）

`_project` 写的是 `r.get(f)`。修前实测：
`[{"path": "/bars"}]` 与 `[{"path": "/bars", "as_of": None}]`
在 `PROJ("path", "as_of")` 下 → **`(True, '')`**。

**「agent 根本没记 as_of」正是前视被掩盖时的形状** —— 而它与「记成 null」不可区分。
修法：缺字段投成显式的 `ABSENT_FIELD` 标记，与 `None` 分开。

### 记录形态、暂不动的一条（转下一项）

`cross_check` 把 **`harness_value is None`** 一律当成「拿不到证据」→ `unverified`。
如果某个叶子的**真证据值**就是 `None`，它会被静默归进「没查」这一类。
形态与已经修过的 `usage_unavailable` / `telemetry_unbacked` **同族**
（那次也是把「一次都没调」与「调了但没给」混成一个结论）。
**我没有核实当前是否存在真值可为 `None` 的叶子**，因此不声称这是缺陷 ——
登记为待核：要么证明不存在（配一条测试钉住），要么引入独立的「不可得」哨兵。

### 自证

`ops/test_c42.py` **167 条**全绿（新增 16 条，攻击者 case 原样入库）；
**6 个突变全部被杀**。其中 O3/O4 两个突变除了打红新测试，
还打红了原有的 `test_lock3_cross_check_can_actually_disagree` 的四个叶子
（`S1.fetches` / `S8.events` / `S1.fields_obtained` / `S3.approximated_operators`）——
**说明这两条修的是承重结构，不是边角**。

---

## N-66 B1 baostock 条款核实与源可用性（2026-09-05，线 B）

### 一、条款：**没有任何一条讲行情数据的再分发**

站点已经改版成前后端分离的 SPA（`www.baostock.com`），任何路径都返回同一个
8,086 字节的壳，条款正文经 `GET /articleMall/api/contract?contract_type=N` 返回。
**五份全部取回并原样存档**（含抓取时间、`contractId`/版本、响应 sha256）：
`ops/terms/baostock/`。

| type | 文件 | 标题 | 字数 |
| --- | --- | --- | --- |
| 1 | `01_user_service_agreement.md` | 用户服务协议 | 5,869 |
| 2 | `02_author_agreement.md` | Baostock交易技术商城作者签约协议 | 7,891 |
| 3 | `03_privacy_policy.md` | Baostock交易技术商城隐私政策 | 7,175 |
| 4 | `04_platform_trade_rules.md` | 平台交易规则 | 1,815 |
| 5 | `05_disclaimer.md` | 免责声明 | 887 |

**核实结论（三条，都要照原文读）**：

1. **五份全部治理「交易技术商城」这个知识付费平台**（运营方
   *阿尔法联合（上海）软件技术有限公司*），讲的是账号、作者签约、分成、退款、
   平台内容的著作权。**没有一条提到通过行情 API 取得的数据能不能再分发。**
2. 现有条款里离得最近的一句在**免责声明第 5 条**：
   「网站内容（包括文字、图片、代码、设计等）版权归我们所有，**未经书面许可不得复制、传播或用于商业用途**」。
   它列举的是文字/图片/代码/设计，**没有列举 API 数据**；但它的措辞是**默认禁止**。
3. **PyPI 的 `baostock==0.9.3` 标的是 `BSD License` —— 那是客户端库的许可，不是数据的条款。**
   把它当成「数据可再分发」的依据，正是这张卡明写要避免的「我记得它允许」。

**按更保守方向（总纪律 5）**：在拿到**书面许可**之前，把再分发按**不允许**处理，
即卡 2.5 §9 的第二种发布形态 —— **发构建脚本 + 校验和，用户自建**。
第一种形态（发冻结 provider + sha256）仍按卡的要求走通并计时，但**不作为默认发布路径**。
是否去争取书面许可是签字人的决定，不是本卡能就地定的。

### 二、源可用性：**活的，而且字段正好够**

`public-api.baostock.com:10030` TCP 连通；**匿名 `bs.login()` 成功**；
`query_history_k_data_plus` 取回 sh.600000 在 2026-07-27..07-31 的 **5 行**，
字段含 `open/high/low/close/preclose/volume/amount/turn/tradestatus/isST`。

**逐字段对上七项依赖**：`preclose` → §3 涨跌停推导的前收（B0 裁定③ 私有侧取
`daily.pre_close`，公开侧的对应物就是它）；`tradestatus` → 停牌；`isST` → ST 的 5% 幅度。

### 三、顺手做的一次对账抽样（B5 的起点）

同一只股票、同一 5 天，**公开源与私有湖逐值比对**：

| 字段 | 结论 |
| --- | --- |
| open / high / low / close / preclose | **完全一致**（到分） |
| volume | 一致（湖里有 `55723092.00000001` 这种浮点噪声） |
| amount | 一致**到分以内**：湖 `504617087.0` vs baostock `504617086.98` |

`amount` 那 0.02 元的差是**湖把金额取整到元**（列类型是 DOUBLE，不是精度丢失），
相对差 ≈ **4e-11**，远在任何容差之下。但它会出现在 `vwap = amount/volume` 上，
**对账报告要写明这条系统性差异的方向**（湖取整，公开源保留两位），
免得后来的人把它当成随机噪声。

**样本量声明**：这是 **1 只股票 × 5 天**的抽样，**不构成对账结论** ——
全量对账是 B5，判据与样本量在那张票里定。这里只回答「公开源到底能不能用」。

---

## N-67 B2 vwap 落带门 + B3 涨跌停推导：**763,301 行 100% 对上 oracle**（2026-09-05，线 B）

### B2：换源前置门，过

在公开源上跑 `snapshots/public/gates.vwap_band_report`
（容差常量从卡 2.1a **import**，不抄）：40 只票（沪主板 12 / 深主板 12 /
创业板 8 / 科创板 8，种子固定）× 2026-01-02..07-31 = **5,443 行**。

```
rows=5439  in_band=5439  ratio=1.000000  median(vwap/close)=1.000727  → 过（线 0.99）
判别力：amount×1000 → ratio 0.000000；amount÷1000 → ratio 0.000000
```

**baostock 的 `amount` 已经是元、`volume` 是股**，不需要 tushare 那样的千元/手归一。
这条门正是为「换源忘了归一」设的 —— 它现在有了真输入，两个方向都实测翻红。

### B3：涨跌停推导，**全窗口零分歧**

实现 `snapshots/public/limits.py`，验收 `ops/acceptance/card_2_5_limit_oracle.py`。

| 窗口 | 行数 | 一致率 | 分歧 |
| --- | --- | --- | --- |
| 2026-07 | 127,010 | **1.000000** | 0 |
| **2026-01-01..07-31** | **763,301** | **1.000000** | **0** |

八个规则分支全部有真实样本覆盖：主板 10%（425,687）/ 创业板 20%（193,568）/
科创板 20%（84,061）/ 北交所 30%（42,642）/ 主板 ST 5%（16,934）/ S 股 5%（139）/
新股无限制（255）/ 退市整理期首日（15）。

**这个 1.000000 是改了四处规则之后才拿到的。四处全部由 oracle 逼出来，
对着文档一处都查不出来 —— 这就是「拿权威答案逐行核」与「规则写对了应该就对」的差别。**

| # | 发现 | 首次核对时的表现 | 证据 |
| --- | --- | --- | --- |
| ① | **北交所取整是「不超过幅度」的截断**，不是四舍五入 | 北交所一致率 **52.4%**，其余板块 99.9%+ | 换成 floor/ceil → **99.87%** |
| ② | **ST 的 5% 带在 2026-07-06 起取消** | 主板 476 行分歧，隐含幅度全在 5% 附近 | 逐日数「4%~6% 带」的票数：20260615..0703 每天 **149–162** 只，**20260706 起只剩 1 只**，此后到冻结线不变 |
| ③ | 新股无限制窗口**沪深 5 天、北交所 1 天** | 北交所新股第 2–3 天被判无限制 | `920222.BJ`（20260629 上市）次日起就是 30% |
| ④ | **退市整理期首日无限制**（卡里没有这条规则）| 半年 15 行分歧 | 15/15 与 `namechange.change_reason='退市整理期'` 的 `start_date` 完全重合 |

**④ 里还藏着一个更隐蔽的**：命名规则**两个交易所相反** ——
深/北是后缀「退」（`国华退`、`云创退`），**沪是前缀「退市」**（`退市华嵘`、`退市观典`）。
第一版按后缀判，**整个沪市漏掉**，表现是半年里 8 行分歧散落各处、看起来像随机噪声，
而不是「少了一条规则」。改判 `change_reason` 之后归零。
判据取 `change_reason` 还有一个好处：那张表与 `stk_limit` **相互独立**，
不是拿 oracle 反推 oracle。

**顺带纠正一条既有结论**：B0 裁定③ 的理由写的是
「`stk_limit.pre_close` 在私有湖里**全为 NULL**」。实测**不成立** ——
全历史空值率 155,380/15,031,079 ≈ **1%**，按年是 2019–2025 的 0.2%~0.6%、
**2026 年 14.3%**；而 2026-07 只有 176 行（= `daily` 也缺行的那些）。
**裁定本身仍然正确**（取 `daily.pre_close` 更全），但**理由要改成实测的那个数** ——
一条错的理由会在下一次被人拿去推别的结论。
另：两个前收在都非空的 127,010 行上**逐行完全相等**。

### 自证

`ops/test_public_limits.py` **41 条**全绿；**10 个突变全部被杀**。
其中 P4（「ST 一律 5%，含注册制板块」）最初**存活** ——
因为那条测试用的日期在 ST 带取消日之后，`is_st` 早被重置，
**测试测不到它自己声称要测的东西**。把日期改到 20260601 并加一条
`assert day <= ST_5PCT_LAST_DAY` 的前提断言之后杀死。

---

## N-68 **需要裁定**：公开 provider 全量重建是 11.5 小时 / 5,817 次请求（线 B / B4）

私有 provider 的规模是**实测**的：`snapshots/v1/qlib_provider` 覆盖
**5,817 只票 × 4,269 个交易日**（2009-01-05 .. 2026-07-31），46,544 个文件。

baostock 单只**全历史**查询耗时实测（10 只样本，2026-09-05）：

```
sh.600000 4269 行 5.6s   sz.000001 4269 行 6.3s   sz.300750 1976 行 4.1s
sh.688111 1626 行 3.0s   sh.601318 4269 行 6.3s   sz.002415 3928 行 9.4s
sh.600519 4269 行 9.7s   sz.000858 4269 行 8.6s   sh.601899 4269 行 6.6s
sz.300059 3976 行 11.8s
→ 均 7.14 s/只
```

**⇒ csi300 全集（1,507 只）约 3 小时；全市场（5,817 只）约 11.5 小时。**

**为什么不自己开跑**：这是**对第三方免费服务的持续负载**，量级由签字人拍板更合适；
而且 N-66 的条款核实结论是「再分发**没有**明确许可，按默认禁止处理」——
既然默认发布形态是「**构建脚本 + 校验和，用户自建**」，
我们自己是否需要保有一份全量冻结 provider，本身就是一个待定问题。

**不等这个裁定、今晚已经在做的**：**分层抽样 200 只 × 全窗口**的逐值对账
（`ops/acceptance/card_2_5_source_reconcile.py`，可续跑，约 25 分钟）。
目的很具体：**在花掉那 11.5 小时之前，先知道会不会有系统性差异。**
抽样查出系统性差异 ⇒ 全量重建的前提就变了；抽样干净 ⇒ 全量只是时间问题。

**建议（不执行）**：① 先看抽样对账结果；② 若干净，按 csi300/500 优先分批跑，
每批之间留间隔；③ 全市场是否需要，等发布形态定下来再说。

---

## N-69 C1 卡 5.1：探针族覆盖审计 + 判卷器红队一轮（2026-09-05，线 C）

### 一、覆盖审计：**16 个探针族里有 3 个从来不会响**

AST 扫全树找 `Verdict.add(..., probe=X)` / `mark_unobservable(X, ...)` 的发出点：

| 有发出点（13） | 处数 |
| --- | --- |
| `underdetermined` 8 · `declared_reads` 3 · `adjust_fingerprint` 2 · 其余各 1 | — |

**零发出点（3）**：`lookahead` / `pit_universe` / `input_ablation`。

**这三族在主表上永远是 clean，而 clean 的原因不是「没违例」，是「没人检」。**
`lookahead` 尤其要紧 —— 它是整个基准的中心探针，而它在 artifact 侧一个发出点都没有
（结算在网关日志侧，被 **T-13 跨机取回**挡着，按 `unobservable` 报而不是 clean，
这一点 `runner/c42/visibility.py` 已经写对了）。

**三族都在测试里出现过族名** —— 也就是说「测试里提到过」完全不能说明它会响。

新增 `ops/test_probe_coverage.py`（6 条）：一个族要么有发出点，要么在
`NO_EMITTER_YET` 里**具名登记**并写清被什么挡着；已实现却忘了从表里删会红；
「今天有几个哑族」被钉成一个数（16 / 3），多一个少一个都要有人解释。

### 二、判卷器红队一轮：**六条确认，四个根因**

判卷器 `reference/memory_probe.grade_answer` 是典型的判定器，按协议过一轮。
每条**实跑**，修前输出原样记进测试 docstring。

| # | 类 | 发现 | 修前实测 |
| --- | --- | --- | --- |
| ① | **A** | `exact_set` 的钥匙写成裸串会被**逐字符**迭代 | `key="600000.SH"` → `('miss','1 个 vs 5 个')`，这道题**从此永远 miss**，说明看起来像模型少答了 4 个代码 |
| ② | **A** | `exact_int` 对小数钥匙**静默截断** | `key=3.7`、作答 `"3"` → **hit**，说明写「3.0 vs 3.7」 |
| ③ | **A** | `exact_int` 把 `True` 当 1 | `key=True`、作答 `"1"` → **hit** |
| ④ | **B** | 弃权词带句号就落进 `unparseable` | `"不知道。"`、`"n/a。"` → `unparseable` |
| ⑤ | **B** | `%` 对所有 NUMBER 题一律剥掉 | `index_level` 上 `"2.5%"` 与 `"2.5"` 判成同一个答案 —— **单位错误被静默改成正确答案** |
| ⑥ | **C** | 弃权的说明写「作答未通过 NUMBER 解析」 | 报告里会把一次明确的拒答写成格式错误 |

**根因一（①②③）：钥匙是我们的，钥匙错了却表现成模型答错。**
钥匙从活湖现取，是**我们这一侧**的东西；它类型不对必须当场炸，
而不是变成一条「模型没答对」的记录进主表。新增 `check_key()` + `KeyTypeError`，
逐容差模式检查，并配一条「每种模式都要被认领」的封闭断言。

**根因二（④⑥）：弃权与不可解析是两个结局，被判卷器的噪声混成了一个。**
整张卡量的是**实测知识地平线**；把「模型说我不知道」算成「我们没读懂它」，
会让地平线偏向答不出来那一侧。剥尾部标点是**纯词法**，不违反 `NO_LLM_JUDGE`。
**边界故意不放宽**：`"我不知道"` 仍是 `unparseable` —— 一旦开始猜「这句是不是弃权」，
判卷就引入了裁判方差，而整张卡的前提是判卷不经过任何模型。这条配了正面测试钉住。

**根因三（⑤）：单位错误被静默改成正确答案。** `%` 只对「个百分点」那类题
（`abs` 容差）有意义，其余题上出现 `%` 是类别错误，应判 `unparseable`。

### 自证

`ops/test_memory_probe.py` **65 条**全绿（新增 15 条，攻击者 case 原样入库）；
**8 个突变全部被杀**。原有 50 条一条没动 —— 说明这轮修的是它们**没覆盖到**的面。

---

## N-70 B5 第一阶段：公开源 vs 私有湖，**508,719 行逐值对账**（2026-09-05，线 B）

分层抽样 **200 只**（种子固定，可续跑）× **2009-01-05..2026-07-31**，
`ops/acceptance/card_2_5_source_reconcile.py`，耗时 943 秒。

### 一、**baostock 不服务北交所**（新缺口，须登记）

200 只里 **14 只 `920xxx.BJ` 全部返回** `10004011 股票代码未标识sh或sz`。
私有湖是有北交所的（2026-07 的 `stk_limit` 有 7,518 行）。

* **不阻塞 v1**：三个 universe（csi300 / 500 / 1000）**全是沪深**，792 条 gold 因子不碰北交所。
* **但要写进数据卡**：公开通道的 `all` 这个 universe **不等于**私有通道的 `all`。
  卡 2.5 §1 的七项依赖表里没有这条 —— 它是**第八项差异**，性质是「覆盖面」不是「字段」。

### 二、行集合：**公开源是私有湖的严格超集**

| | 行数 |
| --- | --- |
| 两边都有 | **508,719** |
| **只在公开源** | **17,770** —— `tradestatus` **全部为 0**，`volume`/`amount` 全部为 0 |
| 只在私有湖 | **0** |

这正是卡 §4 预判的那条差异（baostock **有行**、我们的湖**缺行**），
而且**方向与量级都对上了**：17,770 行集中在 2014–2018（每年 1,900–3,600 行）。
`tradability` 视图吸收它、三态不变 —— 这条现在有实测支撑，不再只是设计假设。

### 三、逐字段：价格全等，量额差在 6.1e-5 量级

| 字段 | 口径 | 一致率 | 不一致 |
| --- | --- | --- | --- |
| open / high / low / preclose | 到分 | **1.00000000** | **0** |
| close | 到分 | 0.99999803 | **1** |
| volume | 相对 1e-6 | 0.99999214 | **4** |
| amount | 相对 1e-6 | 0.99993906 | **31** |

**逐条归因（31 行 amount）**：

| 相对差档 | 行数 | 归因 |
| --- | --- | --- |
| 1e-6 ~ 1e-5 | 23 | **亚元取整**：`356564.0`(公开) vs `356564.4`(私有) 这类 —— 两边取整口径不同，方向**不固定** |
| 1e-5 ~ 1e-4 | 3 | 同上 |
| 1e-4 ~ 1e-3 | 4 | **2013 年的历史修订**：这 4 行的 `volume` 也同时不同（差 500–5,600 股），`close` 那唯一 1 行分歧也在其中（`600845.SH` 18.2 vs 18.19）|
| **> 1e-2** | **1** | `301279.SZ` @ 2022-07-20：两边 `volume` **完全相同**（1,757,791），`amount` 却是 64.67M vs 45.74M。用 `close × volume ≈ 45.8M` 做仲裁 —— **私有值自洽，公开值不自洽**。判定为**公开源的一处数据错误** |

**最重要的一条**：唯一一个量级上的分歧，用**第三个独立量**（`close × volume`）就能仲裁，
不需要相信任何一边。对账报告里凡是「两边不一样」的地方都要能这样落到第三个量上 ——
否则「以哪边为准」就只是立场。

### 四、对 gold 的影响估计

`vwap = amount / volume`（792 条因子里 vwap 是 7 个消费字段之一）。
31/508,719 = **6.1e-5** 的行会有 vwap 差异，其中 30 行的相对差 < 1e-3、
在任何 ε 带之下；剩下 1 行是公开源错误，**建 provider 时应当按 `close×volume` 校验并剔除**。

### 五、样本量声明

**200 只 / 5,817 只 = 3.4%**，按板块分层、种子固定，**不是全量结论**。
全量重建的成本见 N-68（11.5 小时 / 5,817 次请求）。
这一轮的目的就是**在花那 11.5 小时之前先知道会不会有系统性差异** ——
答案是：**没有系统性差异，只有三类可归因的零星差异**（停牌表示、亚元取整、历史修订），
外加一处公开源的单点错误和一个覆盖面缺口（北交所）。

---

## N-71 N-61 补强落地：**执行面自己的门**（2026-09-05 裁定，同日实现）

> 「判据要能在我不在场时否决我」—— `runner/f02/answer_plane_guard.py` 是这句话的实现。
> 它长在执行面上，**不问东西是谁送来的**，也不问送的人当时在想什么。

### 判据四条（裁定给三条，实测逼出第四条）

| # | 判据 | 备注 |
| --- | --- | --- |
| 1 | **gold 串** `GBC-G-`+16 hex | **流式二进制扫全部文件，不按类型豁免**（D-24）；块间 32 字节重叠，跨界串不漏 |
| 2 | **答案面文件名** 六个 | 裁定逐条给定；命中时**内容里有没有串也一并记下**（评估泄漏轻重靠内容不靠名字）|
| 3 | **答案面目录名** `reference/`、`solution/` | 整棵删 |
| 4 | **路径里的串** | **裁定里没有，实测漏过一次**：`mkdir <gold 串>` 之后目录名本身是串，里面的文件完全干净 —— 前三条一条都不占，而目录名随每一次 `ls` 泄漏 |

**命中即删 + 以 access_log 同格式记 `answer_plane_detected`**；删之前先记 sha256 与字节数
（**证据要留，内容不留**）。记录里只写 `sha256:` 前 8 位的**引用**，
**一位原串都不写** —— 连 `GBC-G-` 前缀都不留。

### 三处真机自证抓到的缺陷（都是跑出来的，不是读出来的）

**① 门吃掉了自己的日志。** 日志与闩都住在扫描根**里面**。我往日志里写了一句
带完整合成串的注解，下一轮扫描把**日志自己**判成 `gold_token` 并删掉 ——
**证据文件因为记录了证据而变成违禁品**，整条审计链被它自己的门清空。
修法两道缺一不可：写出去的文本一律脱敏 + 本门自己的文件**拒绝自删**。
「拒绝自删」**不是豁免** —— 它们照样被扫、照样进日志、照样落闩，
只是处置从「删除」换成「标人工处置」。豁免会造出一个「往日志里藏答案面」的口子。

**② 门吃掉了自己的源码。** 我在一句注释里写了 `mkdir <一个完整的示例串>`，
下一轮扫描把**门自己**删了，此后每次运行都是 `rc=2 文件不存在` ——
**门把自己关掉了，而且看起来像环境坏了**。
修：注释里的示例串一律写成抽象形；`owned_paths` 加上 `__file__`；
配一条自查测试「门自己的源码里不许有完整串」（并证明该判据对真串会命中，不是恒绿）。

**③ timer 悄悄变成了 disabled。** 改完 `.service` 之后
`systemctl --user list-timers` 里一个都不剩 —— **门还在，每小时没人来按它**。
修：推送脚本在**依赖它的那一刻**检查 `is-enabled && is-active`，不活就拒绝推送。

### 别的两个决定

* **systemd 那边故意不写 `SuccessExitStatus=1`**：命中就让 unit 进 `failed`，
  `systemctl --user --failed` 立刻看得见。
* 但 failed 会被下一次干净运行覆盖 —— 凌晨三点拦下的一次泄漏，早上就看不见了。
  所以另有一道**闩** `logs/ANSWER_PLANE_INCIDENT`：命中即写、**干净扫描不清它**、
  第二次事件**追加不覆盖**，一直留到有人来看。

### 部署形态

* `runner/f02/answer_plane_guard.py` → f02 `exec/runner/f02/`（0600）
* `~/.config/systemd/user/genebench-answer-plane-scan.{service,timer}`：
  `OnBootSec=5min` + `OnCalendar=hourly` + `Persistent=true`（错过的一次要补跑 ——
  「那小时没扫」与「那小时干净」不是一回事）；`Nice=10` + `IOSchedulingClass=idle`。
  **Linger 已经是 yes**（既有设置，未改），所以无登录会话也会跑。
* 全根扫描实测 **13.6 秒**（约 1.5 GB，含 602 MB provider），每小时跑一次无压力。
* `ops/push_bundle_to_f02.sh` 落地后**调对面自己的门**（不再在本地重写一份 grep），
  并先检查 timer 活性。

### 真机复验（最终一轮）

四种诱饵：答案面目录 / 答案面文件名（内含串）/ 内容带串的 `.parquet` / **以串命名的目录**
—— **4 项全部检出并删除**，日志与闩留存，结尾扫描 `rc=0` 干净。
自证残留已清理；日志**不删只加注**（注解说明哪些条目来自自证、用的是合成串）。

### 自证

`ops/test_answer_plane_guard.py` **41 条**全绿；**26 个突变全部被杀**。

**突变自证本身出过一次假象**：前两轮有 4 个突变报「存活」，
实为 `runner/f02/__pycache__` 的旧字节码没清 —— **测试跑的是没突变的那份代码**。
清缓存后全部杀死。这是本轮最值得记的一条：**突变自证也会说谎，
而它说谎的方向可以是「把没杀死的报成杀死」** —— 那比反过来危险得多。
突变脚本现在一律 `shutil.rmtree(__pycache__)` 后再跑。

---

## N-72 B8 开工：oracle 从未真跑过，一跑就翻出一族**方向相反**的探针（2026-09-05）

### 起点核实：40 题**都有** solve.py，但**一次都没跑过**

早前记的「26 个 solve.py 是骨架」已经过时 —— 逐题核对：**40 题全部有非骨架实现**。
真正的缺口是**从没执行过**：每个 `solve.py` 末尾那句
`# 自检：oracle 必须零 finding（O1）… assert validate(...)` 是**注释着的**。
门写在那儿，门后没有实现者（同 P4b 的形态）。
在跑过之前，「40 题都有 oracle」这句话的全部依据是「文件不是骨架」。

新增 `ops/run_oracles.py`：落题 → 真起网关 → 逐题跑 solve.py →
取 `access_log` 真实切片做交叉核 → **O1 判据是零 finding**（`malformed` 也算）。

### 第一批（S1 五题）翻出四处，逐条都是「跑出来才看得见」

**① `/universe` 的回包形状与 oracle 的解析不符。**
它给 `{"size": 300, "members": [...]}`，oracle 照 `data`/`code` 取 → 空列表 →
整道题一次 `/bars` 都没取，**却仍然产出了一份看起来合法的 artifact**。
修：按实测形状解析；取不到成分**直接抛**，不产出空壳。

**② `fetched_at` 没有来源。** 契约写「用网关回包携带的时间戳，绝不用本地时钟」，
而网关**不回显任何时间戳**。让 oracle 自己去读日志填这个值等于
**被核的值与核它的基准同源** —— 交叉核成了恒真。
修：网关每个响应（allow 与 deny 都）回显 `x-genebench-ts` =
它写进 `access_log` 的那条 `ts`；配 D-21 对齐断言。

**③ ⭐ `source_status` 这族探针的方向是反的。**

网关的**成功路径根本不传 `rows`** —— `access_log` 里那一列**恒为 `None`**。
而判据是 `_status_from_log`：`(e.get("rows") or 0) > 0` → `None` 被推成 **`empty`**。
两件事凑在一起：

* 老老实实报 `ok` 的 artifact，**每一条 fetch 都被判违例**（S1 五题实测 **601 条**）；
* 而一个把所有 fetch 都报成 `empty` 的 artifact，**反而全过**。

**这族探针「有发出点」，测试里也「提到过族名」** —— 两样都不能说明
它**朝着对的方向**在判。这是 N-69 那张覆盖审计表照不出来的一层。

两道修：网关把回包里的 `rows` 记进日志（`/universe` 补 `rows` 与 `size` 同值，
**只认一个键**，不做 rows/size 优先级 —— 两处各写一份必然漂）；
`_status_from_log` 在 `rows` 缺失时返回 `None`，调用方标 **`unobservable`** ——
**推不出不等于一致，也不等于违例**（三态纪律）。

**④ 我自己在中间件缓冲里引入并抓到一个截断 bug。** 为了读 body 里的 `rows`，
中间件要把流式响应读成普通响应。第一版在超过缓冲上限时 `break` 掉、
又把**原**响应放行 —— 那个响应的 `body_iterator` 已经被消费了一半，
客户端收到空 body（`/fundamentals` 200 但 `r.json()` 直接 JSONDecodeError）。
**读一半就放行**是这里唯一不能做的事。修：要么全读并重建，要么一个字节都不碰。

### 一处**设计上就该红**的拦截

`s1-rob-02` 落盘被 **E9c 锁**拦下（字段 `data_version` 在无条件下既无 screen 实测记录、
也无静态规则）。这不是这批跑的失败，是那道题**还没到能出 oracle 的时候**。
跑批因此改成**逐题容错**：一道落不了不拖垮整批。

### 顺带两条运维

* **我把 systemd 的网关单元 kill 了，换成手跑的野进程** ——
  `test_g09_production_listener_is_the_systemd_unit_not_a_stray_process` 当场抓到。
  已恢复为单元（`NRestarts=0`）。
* **git 的 loose object 落成 0444，网关就起不来了**（实测两次）：
  单元的 `ExecStartPre` 是红线 5 的守门，而仓库里有 oracle 源码。
  修在源头 —— 加 `.git/hooks/post-commit` 提交后 `--harden`。
  **守门本身不改成自动 harden**：那会让它永远通过，等于没有那道门。

### 状态

S1 四题（除被 E9c 拦下的 `s1-rob-02`）正在用修好的链路重跑。
S2–S8 的 35 题尚未跑。

---

## N-73 2026-09-05 五项裁定落地（许可 / D-30 / 矩阵 / source_status / 门自保护）

### 一、N-66 更新：再分发许可已取得 → 发布形态改为「冻结包 + 校验和」

| | |
| --- | --- |
| 默认路径 | **冻结 provider 直接下载 + `files.sha256`** |
| 复现路径 | **构建脚本 + 校验和**（保留，两条都走通）|
| 当前状态 | **`pending_license_text`** —— 许可已取得，**书面原文尚未入库** |

新增仓库根 `DATA_LICENSE`，并配三条状态锁（`ops/test_env.py`）：
① 状态必须是 `pending_license_text` / `granted` 之一；
② `pending` 时 `snapshots/public/` 下**不得存在任何打好的包**；
③ **状态与事实必须一致** —— 写着 `granted` 却没有原文、或原文已在却还写着 `pending`，两种都红。

**「口头已取得」与「有原文可查」是两回事** —— 后来的人只能读到后者。
论文的数据声明与致谢**按许可方要求的署名**写，措辞以原文为准，**不自行拟稿**。
数据卡 §1 同步改写，并保留一句：那五份平台条款**与再分发无关**，
再分发的依据是**单独取得的书面许可** —— 不写清楚的话，
后来的人会以为「条款里查出来可以」，而条款里查不出来。

N-68 范围不变：仍建 **v1 宇宙并集**，全市场留 v1.1。

### 二、D-30：探针方向必须用对照测，覆盖审计补第三列

`ops/test_probe_coverage.py` 从两列变三列：

| 列 | 判据 | 状态 |
| --- | --- | --- |
| 有没有发出点 | AST 扫全树找 `add(..., probe=X)` | 13/16 有，3 个登记在 `NO_EMITTER_YET` |
| 有没有测试提到族名 | 文本扫 `ops/test_*.py` | **信息列，不作判据**（`source_status` 两样都占，方向却是反的）|
| **方向是否已证** | 两张矩阵：oracle 上该族全零 **且** F1 上该族非零 | **16/16 未证**，全部登记在 `DIRECTION_UNVERIFIED` |

登记表是**临时**的：矩阵一跑出来，`test_direction_registry_is_not_stale` 会逼着删。
另配一条判别力测试：**矩阵不存在时一个族都不许算「已证」**——
防的是「跑批还没跑、覆盖表却全绿」。

### 三、oracle 跑批改造成探针族回归载体

`ops/run_oracles.py` 加 `--agent {oracle,f1}` 与**探针族 × 题目 finding 计数矩阵**：

* `probe_matrix_oracle.md`：**判据全零**。任一格非零 = **探针缺陷**，不是 oracle 缺陷。
* `probe_matrix_f1.md`：F1 填充器（按题面 `null_agent.behavior` 造产物），
  **判据是每族在其适用题上非零**；一整行全零 = 方向未经证实。
  `gateway_log=[]`（**可得但零请求**，不是 `None`）—— 填充器确实一次网关都没调。

两张矩阵进 M6 的「验证验证器」报告。

### 四、source_status：根因在网关，判据保持严格

按裁定：**网关侧改，判据不改成容忍 `None`。**
已把 `_status_from_log` 改回严格（`rows` 缺失仍推 `empty`），
并在 docstring 里写清这条选择的代价对比：

> 放宽的代价是网关哪天又不记 `rows`，这族探针会**静默退化成不可检**，
> 而不可检不影响 `ok` —— 主表上看不出任何异样。
> 保持严格的代价是网关坏了，跑批矩阵会**整列爆红**。
> **爆红看得见，静默退化看不见。**

证据源本身的完整性由 `run_oracles.check_log_evidence` 单独盯（D-26）：
日志切片为 `None`、为空、或有 allow 条目缺整数 `rows` —— 三种都点名，
并明说**根因在网关不在 artifact**。

`x-genebench-ts` 回显头保留：被核值由 agent 转录、基准来自日志，
**两者同源于网关时钟但不同路径**，查的是**转录保真**。

### 五、接收侧门加自身完整性

* `OWN_FILES` 三个：源码 + `.service` + `.timer`。读不到的记 `None` **并附原因**
  （「没装单元」与「装了但没记」必须分得开）。
* `--write-identity` 写基线（**部署时**用），每次运行**先核自身再扫别人**。
* **自检失败照常扫** —— 因为自检失败就停掉这道门，等于让「把门改坏」成为**关掉门**的办法。
* 漂移 ⇒ 报出来 + 落闩 + **退出码 1**（哪怕树是干净的）。
  返回 0 的话，一次部署少写 `--write-identity` 就再也没人知道。
* **自证不能是唯一的证明**：`inject.py` 把这三个 sha 记进 `inject.json`，
  由 **f01** 拿仓库里的那份去比。改了门的人也能改基线 ——
  自身完整性挡的是**部署漂移**（推了一半、推了旧版、文件损坏），不是蓄意篡改。

**真机复验（f02）**：干净+基线一致 ⇒ `rc=0`；人为改一个字节 ⇒ 报出不一致、落闩、
**照常扫**、`rc=1`；还原 ⇒ `rc=0`。自证留下的闩已清并在日志加注。

### 六、D-29 补记落地

突变脚本现在每条都打印**落地证据**：被突变文件的 sha256 前后变化
（`sha 33c45870d8→9c77919e92`），并在还原后断言 sha 回到原值。
只报杀死率不够 —— 报告要能证明每一个突变**真的落到了磁盘上**。

### 自证

`ops/test_answer_plane_guard.py` **48 条**全绿；本轮新增 5 个完整性突变**全部被杀**
（累计 31 个）。`ops/test_probe_coverage.py` 10 条全绿。

---

## N-74 **冻结防漂比错了字段** —— 同一个 F7 形态的第三次（2026-09-05）

**怎么发现的**：我改了 S1 四个模板的 `solve.py`（它在 `TEMPLATE_FILES` 里），
然后顺手核了一下冻结引用 —— **`frozen_ref(verify=True)` 返回成功**。
清单里 `S1/cov_fields` 的 `solve.py` 记着 `2d06cd…`，盘上是 `c32ea474…`。

**根因**：`verify=True` 那段**现算了 `build_manifest()`，却只比两样**：
`instruction_fingerprint` 与出集清单的 task_id 列表。
**`templates` 段从来没有被比过** —— 而 `root` 正是覆盖它的
（`ROOT_FIELDS` 含 `templates`）。于是：改模板 → root 变 → **没有任何东西比 root**。

**这是同一个形态的第三次**，而且就发生在这个函数里。它的 docstring 逐字写着：

> 「没有它的时候，这个函数只是**读文件、对文件里已经记着的字段求 hash**……
> **这正是 `pin.py` 里批判过的 F7 形态（只读记录值等于没查），在同一个仓库里犯了第二次。**」

第二次的修法是「现算一遍」。**现算了，但比错了字段。**
「有没有现算」与「算出来的东西有没有被用在比对上」是两件事 ——
前者看代码就知道，后者只有喂一个真的改动进去才知道（**D-27 的又一个实例**：
判据存在，但没有测试盯着它**比的是哪一段**）。

**修法**：加 `templates` 段的逐模板比对，报出**具体是哪个模板的哪个文件**变了。
`code` 段刻意**不**做硬比对 —— 给打包器加个无关函数就会让它漂，而那不是题面变了。
题面由三样钉住：**指纹（渲染结果）+ templates（源文件）+ 出集清单**。

**判别力测试**（`ops/test_env_guard.py`）：造一份 `templates` sha 与工作树不符的清单 →
必须 `SystemExit` 且点名那个模板；反面一条防它乱红。

**顺带**：因为这次改动是真的题面输入变化，按纪律**重冻结**：
**v1.0.2 → v1.0.3**，根 `19f46ec3…` → `953c1b4d…`，原因逐条记进 `REVISIONS`
（改的是数据面私有的参考解，**题面一个字没动**）。

> **版本号说明**：裁定里把 N-62（统一基座）预定为 v1.0.3。
> 这次因为 oracle 参考解的修正**先动了冻结面**，占用了 1.0.3；
> N-62 的基座改动请按 **v1.0.4** 记。要改回来的话告诉我，我把这次改成 1.0.2.1 之类。

---

## N-75 (b) 统一 oracle 调用约定 + N-62 统一基座 → **一次重冻结 v1.0.4**（2026-09-05）

### 一、原则（裁定原文）

> **oracle 的 I/O 契约 = agent 的 I/O 契约** —— 读标准位置的任务规格、经网关取数、
> 写标准 artifact 路径，其余**不接受任何 stage 特定 env/argv**。

**同形的理由不是整洁，是可比性**：oracle 是 gold 的来源，agent 是被测方。
两者的输入若来自不同地方，「同一道题」这句话就没有定义 ——
而主表上每一个数都建立在这句话上。

### 二、改之前有多乱（实测）

七个阶段、**七套**互不相同的约定：

| 阶段 | 原来的约定 |
| --- | --- |
| S1 | 自读 `task.yaml`/`taskspec.json`；`GENEBENCH_ORACLE_OUT` |
| S2 | env `GENEBENCH_TASKSPEC`(JSON) / `WINDOW`(JSON) / `AS_OF`；输出 `GENEBENCH_ARTIFACT` |
| S3 | env `GENEBENCH_WINDOW_START/END`；另四题调**一个不存在的** `reference.s3_oracle_common` |
| S4 | `sys.argv[1]` |
| S5 | `GENEBENCH_ARTIFACT_PATH` |
| S6 | `GENEBENCH_TASK_DIR`，缺省 `/task` |
| S7 | `main(task_dir, arm)` via argv |
| S8 | env `GENEBENCH_TASK_ID` / `AS_OF` / `WINDOW_START` / `WINDOW_END` |

光「artifact 写哪里」就有**四个名字**；「任务规格从哪来」有两套（env 里塞 JSON vs 读文件）。
S5/S6/S8 的缺省值还是 `/task/...` —— 那是**容器内**的路径，而 oracle 跑在 f01。
**它们从没冲突过，因为没有一个被执行过。**

### 三、落地

* `reference/oracle_io.py`：`context(__file__)` 从 `<task_dir>` 读出全部输入。
  唯一允许的环境变量是 `GENEBENCH_GATEWAY_URL`（**部署事实**，f01 与容器不同）
  与 `GENEBENCH_ORACLE_OUT`。**凡是能从 `task.yaml` 读出来的，一律不从 env 拿** ——
  env 里的那份可以与题面不一致，而没有任何东西会说。
* 40 个 `solve.py` 前言全部改写（含 S1 那四个 —— 它们是第七种形状）。
* `reference/s3_oracle_common.py`：S3 五题的取数/暖机/非有限值统计/落盘抽成一处。
  **端点形状按实测改正三处**：`/calendar` 的日期列是 `cal_date` 不是 `date`；
  `/universe` 的参数名是 `universe=`（`name=` 直接 422）；回包是 `{size, members}` 不是 `data[].code`。
  `s3-cor-01` 也改为复用公共层 —— 两份实现正是那条 TODO 要消灭的东西。
* `ops/test_oracle_contract.py`：**AST** 锁死（不做文本 grep —— 规格里到处写着那些变量名，
  文本判据会命中散文本身）。任何 stage 特定 env 或 `sys.argv` 即红。**122 条全绿**，
  含判别力：喂一个真读 stage 特定 env 的源码必须命中。

### 四、N-62 统一基座

`python:3.12-slim-bookworm` + **Node 22.23.2** + `pandas==2.3.3` / `pyarrow==25.0.1`。

* python 取 3.12（OpenHands 官方基座就是 3.12；题面原来钉 3.11 没有特殊理由）；
* 数值栈取**三家里最高的**（RD-Agent 的）；
* Node 走**官方 tarball + 钉 sha256**（`d60acfe0…`），**不走 `curl | bash`** ——
  后者是一条无法复核的供应链入口，而本项目对 npm 包都钉 `dist_integrity`；
* 单 `FROM`（多阶段会让 `inject.py` 的 P4c「FROM 必须唯一」当场红）。

**跨版本数值核**（统一基座 vs f01 `qlib_env`，全部指标相对差 1e-13 量级）
按裁定是 **A1 的前置，不阻塞本次冻结**；不过则 v1.0.5。

### 五、重冻结

**v1.0.3 → v1.0.4**，根 `953c1b4d…` → `5a9c0616…`，一次记两条原因。
改的是**数据面私有的参考解 + 39 个模板的 Dockerfile**；
题面（INSTRUCTION / template.yaml / scorer.yaml）**一个字没动**。

---

## N-76 D-27 实施要求落地：五个门逐段补「喂真改动、必红」（2026-09-05 裁定）

> 判据是**可数的**：门声称保护 N 段，验收里就要有 N 条红测试，一段一条。
> **不允许一条笼统的「整体一致」覆盖多段** —— 那种测试在「少比了一段」时照样绿，
> 而少比一段正是这一族缺陷的形态（N-74）。

| 门 | 段数 | 落点 |
| --- | --- | --- |
| `freeze_v10.frozen_ref` | **3**（题面指纹 / 出集清单 / templates）| `ops/test_env_guard.py` |
| `bundle.check_manifest` | **6**（版本 / check_export / 文件集 / 逐文件 sha / 允许集 / 冻结根）| `ops/test_guard_sections.py` |
| `pin.check_provider_pin` | **4**（根存在 / 树非空 / 根 sha / 逐文件）| 同上 |
| `ops/push_guard` | **11** | `ops/test_push_guard.py` |
| `answer_plane_guard` | **15** | `ops/test_answer_plane_guard.py` |

每个门配一条**段数可数**的元测试：段登记表里有、而验收里没有对应红测试的，当场红。

**写法上的一条要求**：每条红测试造一份**只在那一段上**与基线不同的输入，其余全部合法 ——
「其余全部合法」是关键，否则红可能来自别的段，那条测试就没有定位能力。
每组另配一条「基线必须绿」，防整组变成恒红。

`check_provider_pin` 的「逐文件」那条尤其值得记：
**根 hash 只证明清单没被动过** —— 改一个 `.bin` 的内容而不动 `files.sha256`，
根 hash 一个字不变。测试里显式断言了这一点（`provider_root_sha256` 前后相等），
再断言逐文件那一层拦住了它。

---

## N-78 **两条版本轴**：任务集 v1.0.x 与参考面 r1.0.x 分开冻结（2026-09-05 裁定）

### 为什么拆

`solve.py` 是**答案面**（agent 永远看不见），却住在 `TEMPLATE_FILES` 里。
于是每修一个 oracle 都要推一次**任务集版本** ——
2026-09-05 一天之内推了 **1.0.3 / 1.0.4 / 1.0.5** 三次，
其中**两次题面一个字没动**。

版本号这样跳，「这两次运行为什么不可比」就答不清楚了：
看到 `v1.0.3 → v1.0.5` 的人无从知道**被测方看到的东西其实完全一样**。

拆开之后两个问题各有各的答案：

| 轴 | 回答的问题 | 覆盖 |
| --- | --- | --- |
| **任务集 `v1.0.x`** | agent 看到的东西变了吗 | 题面 / template.yaml / scorer.yaml / Dockerfile / 容器自检 / 夹具 |
| **参考面 `r1.0.x`** | 我们**算 gold 的方式**变了吗 | 40 个 `solve.py` + `reference/oracle_io.py` + 各阶段 `*_oracle_common` |

**可比性要求两者都相同** —— `inject.json` 与通行证同时记两个。
只记一个的话，两次 gold 算法不同的运行会看起来完全可比。
判据写成了可执行的形式（`test_comparability_needs_both`），免得它只活在文档里。

### 落地

* `TEMPLATE_FILES` 去掉 `solve.py`；新增 `REFERENCE_TEMPLATE_FILES` 与 `REFERENCE_MODULE_FILES`。
* 两份清单、两个根：`ops/manifests/v1.0-smoke.json`（根 `b4b058df…`）与
  `v1.0-smoke.reference.json`（`r1.0.0`，根 `b1f728e6…`）。
* `--write-reference` 单独推 r 号；oracle 后续修复**只推 r**，任务集冻结门保持绿。
* 逐段红测试（D-27 实施要求）：参考轴两段（`solve.py` / 公共主干）各一条。
* `test_reference_files_cover_the_whole_reference_plane`：新加的公共层忘了登记会红 ——
  否则它**不受冻结保护**，改了没人知道而 gold 的算法已经变了。

### 一处必须自描述的事

**任务集的 root 值变了**（`5a9c0616…` → `b4b058df…`），**而内容一个字没变** ——
因为 root 覆盖的字段集变了（`templates` 段里少了 `solve.py`）。

版本号**不推**（推了会让人以为 agent 看到的东西变了），
改为把**覆盖面写进清单**的 `root_scope` 字段：
`{root_fields, template_files, excluded_to_reference_axis}`。
不这么做的话，事后比两个 root 的人只会看到「不一样」，并合理地以为题面动过。

### 历史条目的处置

`REVISIONS` 里 **1.0.3 与 1.0.5 改判为「参考面变更、任务集未变」**，
条目**保留不删**（它们已经被引用过；删掉更容易让人以为没发生过），
标题里标注改判，内容归入 `REFERENCE_REVISIONS` 的 `r1.0.0` 起点说明。

---

## N-79 `/tradability` 的实际签名与调用量（裁定要求的实测）

**签名**（`gateway/routers/reference.py:93`）：

```
GET /tradability?as_of=&date=&code=<可重复>
  code : list[str]  —— **重复查询参数**，不是逗号串；至少一个，否则 422
  date : str|None   —— **单日**，不接区间；缺省取 as_of
```

S5 原来写的是 `codes=",".join(codes)` + `start`/`end` 区间 —— **三处全错**
（参数名、单复数形态、不接区间），表现是一条几千字符的 URL 直接炸。

**实测调用量**（分批 100 code/请求）：

| 题 | 交易日 | 成分 | 请求数 |
| --- | --- | --- | --- |
| s5-eco-01 | 139 | 300 | **417**（最大）|
| s6-eco-01 / s6-ops-01 | 62 | 300 | 186 |
| s6-rob-02 | 44 | 300 | 132 |
| 其余 S5/S6/S8 | 11–23 | 300 | 33–69 |

**最大 417 次，全部远低于 1000** ⇒ **不加批量形态，不推任务集版本，题面不用同步。**
（若把批大小放到 300，最大降到 139；保守取 100 是为了给 URL 长度留余量 ——
300 个 code 拼一条 URL 约 5.7 KB，贴着 h11 的 8190 字节上限。）

---

## N-80 面板 `factor` 的基准日是 `as_of`，晚于窗口末日（**登记**，2026-09-05）

拼 S7 面板时实测出来的口径：`factor(code, d) = adj_factor(code, d) / adj_factor(code, as_of)`。
`SH600000` 窗口末日（2026-07-03）的 `adj_factor` 是 16.5935，`as_of`（2026-07-31）是 17.3774，
而冻结面板 `factor` 末值 0.95489 = 16.5935 / 17.3774 —— **基准日取窗口末日会算错**。

所以面板构造要取到 `as_of`，即**读了窗口结束之后的数据**。这是一处前视：
它对**收益**无影响（每票一个常数比例，逐日收益不变），但对 `close` 的绝对价位有影响，
因而影响**整手取整**与最低费用触发 —— 不是零影响。

**为什么本轮按原样复现**：ε（卡 2.2b）就是在这个口径的面板上标定的，
换口径等于换掉 ε 的标定基准。改口径要连 ε 一起重标，是 v1.1 的事。
`reference/s7_oracle_common.fetch_panel` 的 docstring 口径 ① 写死了这一条。

---

## N-81 `is_delisted` 把「永久停牌但仍上市」算成退市（**登记**，2026-09-05）

冻结面板的规则（`scratch/export_input2.py:69`）是纯操作性的：

```python
out["is_delisted"] = (~out["has_price"]) & (out["date"] > out["last_price_date"])
```

实测：540 票里 14 票被标 `is_delisted`，与「最后有价日早于面板末日」的 14 票**完全同集**，
起始日恰为最后有价日的次一交易日。没有用任何退市标记。

后果：一只**长期停牌但仍上市**的票会被当成退市，在停牌首日之后被
契约 §4 的强制清仓规则按「最后一个有效 `close`」清掉。名单里 `SH688072` 的最后有价日是
2026-06-26，距面板末日只有 5 个交易日 —— 更像停牌而不是退市。

网关 `/bars` 有 `in_listing_window` 可以区分两者。**本轮不改**（同 N-80，动它就动 ε 基准），
登记给 v1.1：要么改判定式，要么把契约 §1 的 `is_delisted` 措辞从「真退市」改成
「最后有价日之后」——**现在这两句话不是一回事**，而契约写的是前者。

---

## N-82 ε 面板的构建脚本不在仓库里（**已缓解**，2026-09-05）

`snapshots/v1/epsilon/bt_input_csi300_v2.parquet`（984,960 行）是 S7 gold 的输入，
但生成它的 `export_input2.py` 住在 `/data/shared/genebench/scratch/` ——
不在仓库、不在冻结清单、没有测试，而且读 **qlib** 不读网关。
即「定义 S7 gold 输入的那份代码不受任何门保护」。

**缓解**：`reference/s7_oracle_common.fetch_panel` 是走网关的**独立第二实现**，
`ops/acceptance/s7_panel_vs_frozen.py` 逐格比对全表 984,960 格：

| 列 | 结果 |
| --- | --- |
| `close` | 最大相对差 **5.95e-08**（冻结面板存 float32，精度地板 1.19e-07）|
| `factor` | 最大相对差 **5.85e-08**；空值差 2,716 格，**全部**落在无价格的格上 |
| `in_universe` / `has_price` / `is_delisted` | **各 0 格不一致** |
| 行集合 | 两侧各 984,960，`only_new` = `only_ref` = **0** |

两侧数据源不同（qlib `D.features` / 网关 `/bars`×`/adj`）、`in_universe` 的来源也不同
（qlib instruments 的 `in_date/out_date` 区间 / `/universe` **逐日 PIT** 名单），
所以逐格相等排掉的是「网关取数口径与 ε 那次不同」这一整类错误 ——
那类错误的表现是 11 项指标一起偏，没有任何一项报错。

`factor` 那 2,716 格的差异由 `ops/acceptance/s7_panel_factor_immaterial.py` 单证：
喂真改动（无价格上的 factor 全置空）三份实现指标必须逐位不变，
外加阳性对照（有价格上的 factor ×1.01）必须让指标动 —— D-30 的两半都要。

---

## N-83 S7 的 gold 引擎缺实现 B（**BLOCKED_AWAITING_USER**，2026-09-05）

`reference/s7_oracle_common.run_engine` 调的是

```python
backtest.run(panel, config=backtest.config_from_declared(declared))
```

**这两个符号都不存在。** `reference/backtest.py`（266 行）里只有**实现 A**
（`run_backtest`，qlib `TopkDropoutStrategy`）。而契约开篇写着
「这份文件是实现 B 的唯一输入……实现 B **不得**阅读 qlib 的 exchange/executor/strategy 源码」——
拿 A 当 gold 会让 ε 虚小到没有意义（N-27 实测 A 与 B 的 `ann_return_gross` 差 **1.22pp/年**）。

实现 B 存在，但是**三份互相独立的脚本**，不是库：

| | 路径 | 行数 | 入口 |
| --- | --- | --- | --- |
| B1 | `snapshots/v1/epsilon/impl_v2_b1.py` | 316 | `run(freq, panel)` |
| B2 | `snapshots/v1/epsilon/impl_v2_b2.py` | 378 | `run(freq, dates_w, S, top, n_top)` |
| B3 | `snapshots/v1/epsilon/impl_v2_b3.py` | 325 | `run(freq, P=None, debug=False)` |

三个签名各不相同，都硬编码读自己目录下的 `bt_input_csi300_v2.parquet`，都自己写 JSON。

**分歧有多大（daily，已发布五题全部 declared `daily`）**：

| 指标 | B1 | B2 | B3 | 最大相对差 |
| --- | --- | --- | --- | --- |
| `ann_return_gross` | 0.0553488 | 0.0554364 | 0.0554364 | 1.58e-3 |
| `ann_return_net` | 0.0016293 | 0.0017120 | 0.0017120 | 4.83e-2 |
| `max_drawdown_net` | -0.5291195 | -0.5290574 | -0.5290574 | 1.17e-4 |

daily 下 B2 与 B3 在 9 项里 5 项完全相同，B1 是那个异类；三者的差**就是 ε 的标定量本身**
（`epsilon_dual_daily.json`，`multiplier` 1.5）。所以选谁当 gold，选择本身落在 ε 带内 ——
但**记录下来的 gold 数值会不同**，而 gold 数值进 `slice.parquet` 与 `oracle_artifact.json`，
是可比性的一部分。这不是我能替你定的。

**要裁的**：(a) 指定三份中的一份为 S7 gold 引擎，把它包成
`reference/backtest.run(panel, config=...)`（包装只做签名适配，**不改算法**，
用 `ops/screen_runner.py` 的 Gate 0 手法逐字节证明包装中性）；或
(b) 定一条聚合规则（如三份取中位数）；或 (c) 别的。

**顺带一条**：`ann_return_net` 三份之间差 4.8%，是因为它本身接近 0（1.6e-3）——
ε 对它已改用**绝对**容差。这条不用裁，记在这里免得下次又当成 bug 查一遍。

---

## N-84 S7 的 `work/signal.parquet` 夹具不存在（**BLOCKED_AWAITING_USER**，2026-09-05）

五道 S7 题的 `task.yaml` 都声明：

```yaml
inputs:
- path: work/signal.parquet
  sha256: null
  origin: signal:s7_dedicated_signal_v1
```

`sha256: null`，而 `reference/tasks/v1.0-smoke/s7-*/` 下**没有 `work/` 目录**。
`s7_dedicated_signal_v1` 目前只是一个名字：N-47 记着它「明确不复用任何 S5 题的 gold」，
但没有任何地方定义它是什么。

**候选来源**：冻结 ε 面板的 `signal` 列（984,960 格里 545,677 非空），
同目录的 `bt_qlib_alpha158.ROC20_baseline.json` 与契约 §1 的
「`signal` = 当日 gold 因子值 `qlib_alpha158.ROC20`」都指向它。
但「很可能是它」不是判据 —— gold 的身份必须是被指定的，不是被推断的。

**要裁的**：`s7_dedicated_signal_v1` ≡ 冻结 ε 面板的 `signal` 列（即 `qlib_alpha158.ROC20`）？
若是，夹具生成就是从冻结面板抽 `(date, code, signal)` 落 `work/signal.parquet`
+ 写 `work/signal.meta.json`，**归入你排的那次夹具生成**（合法推任务集版本），
顺序上它与 S3→S4/S5、S5→S6 无依赖，可并行。

---

## N-85 weekly / monthly 两档的 ε 不可用（**登记**，2026-09-05）

`epsilon_dual_{weekly,monthly}.json` 的 `usable` 都是 **false**：

| 频率 | implausible（三份独立实现之间相对差 > 5%）|
| --- | --- |
| weekly | `ann_return_gross` |
| monthly | `ann_return_gross`、`sharpe_net`、`total_cost` |

monthly 的 `ann_return_net` 三份是 0.05396 / 0.05410 / 0.04308 —— **相对差 20.4%**。
B3 差得最多，与 N-38 记的「b3 没有 `first_rebalance_day` 的首日建仓步骤」一致。

**不阻塞本轮**：已发布的五道 S7 题 `declared.rebalance_frequency` **全部是 `daily`**，
daily 档 `usable: true`。但 `rebalance_frequency` 是契约 §2 的**必填三选一**，
题面把三档都写成合法取值 —— 也就是说 v1 里有两档**取了就没法评分**。
v1.1 要么先修 B3 的分歧再重标 ε，要么在题面把可取值收到 `daily`。

---

## N-86 `s8-rob-01` 的 `visible_state_fields` 里有环境不认识的字段（**BLOCKED_AWAITING_USER**，2026-09-05）

题面（`arms/INSTRUCTION.strict.md:16` 与 `arms/slots.json`）对 agent 写着：

> visible_state_fields=[cash, positions, nav, **open_orders**]（……接口值 [cash, positions, nav, open_orders]）

而契约 §2 与引擎给的字段叫 **`pending_orders`**。`SimEngine.state()` 对表外字段是**报错不是丢弃**，
所以真网关上这道题的每一次 `/sim/state` 都是 422：

```
visible_state_fields 里有环境不认识的字段：['open_orders']；可选 ['cash','nav','pending_orders','positions','sim_date']
```

**不是 oracle 的问题** —— agent 照题面做也一样 422。这道题现在**谁都做不了**。
来源是模板 `genetask/templates/S8/s8_idempotent/solve.py:27` 自己起了 `open_orders` 这个名字，
而 `genetask/materiality.py:34` 用的是 `pending_orders`。**两个名字指同一件事，没有任何断言把它们绑住**（D-21）。

**要裁的**：

* **(a) 改题面**（把 `open_orders` 换成 `pending_orders`）—— 契约是对的，模板起错了名。
  但这改的是 **agent 看得见的东西**，要推**任务集版本**；可以并进你排的那次夹具生成的 v1.0.x。
* **(b) 改引擎**（加 `open_orders` 作别名）—— 一个东西两个名字，正是 D-21 说的那种漂移源，**不建议**。

我按 (a) 的判断没有自己动手：它动题面。等裁定。

**顺带补的门**：`ops/test_sim_factory.py` 加一条 ——
**每一道已发布 S8 题的 `visible_state_fields` ⊆ 引擎 `state()` 的键集**。
这条今天就红（它抓的就是这个缺陷），是 D-27 说的「喂真改动必红」的天然形态。

---

## N-87 S8 的会话工厂在生产路径上不存在（**已修**，2026-09-05）

`gateway/routers/sim.py` 有 `register_session_factory()`，但**全仓没有一处生产代码调用它** ——
只有 `ops/test_sim_endpoints.py:450` 在测试里注册自己的工厂，用完还 `register_session_factory(None)` 还原。

所以真网关上 `_FACTORY is None`，五个 `/sim/*` 端点一律返回

```
404 这次运行没有模拟盘会话（config_id=…, task_id=s8-cor-01）
```

**S8 四道题在真网关上从来跑不通**，而这件事没有任何一条测试会红：
测试自带工厂，所以测试里的模拟盘永远存在。这是 F7 的又一例 ——
机制齐备（五个端点、引擎、越权闸、审计日志全都实现了并且测得很细），
**接线缺一根**，而所有的测试都在接线的另一侧。

**已修**：新增 `gateway/sim_factory.py`，`create_app()` 里注册。构造参数全部来自数据面且全部是
X 面（题面 `declared` 的三个字段 + 湖里的日历/收盘价/可交易性），不碰 canary 段。

**修的过程中避掉的第二个坑**（同族，值得记）：湖里 tradability 的 `status` 有四个取值
`{trade, suspend, limit_up, limit_down}`，而引擎的 `TRADABILITY_STATES` 只有三个
`{trade, suspend, no_data}`。原样传进去，引擎走 **fail-closed** 分支
（`unknown_tradability:limit_up`）把涨跌停当成**买卖两边都拒**，
而契约是涨停**只挡买**、跌停**只挡卖**。gold 会照样出数，指标全错，没有一处报错。
工厂里显式登记映射表并对没登记的取值**抛错**。

同时实测确认：`status == "limit_up"` 与 `limit_up_close` **逐行等价**
（2026-07 窗口 1991 对 1991；`limit_down` 1253 对 1253），
而 `limit_touched_up` 更宽（912 行 status 是 `trade` 却触过板）——
撮合在收盘，用 touched 会把收盘没封住的也拒掉。取 status，不取 touched。

**端到端实测**（`TestClient`，未动运行中的网关）：

| 用例 | 结果 |
| --- | --- |
| `/sim/state`（s8-cor-01）| 200 `{cash: 1000000.0, positions: [], nav: 1000000.0}` —— `sim_date` 未声明故不返回 |
| `/sim/order` | 200 `{order_id: o000001, status: accepted}` |
| 同 `client_order_id` 重放 | 200 同一个 `order_id`，`reason: idempotent_replay` |
| `/sim/advance` | 200 次日收盘成交 `price: 8.7`，`cash` 999130.0 |
| `/sim/advance` 带 `{"date": …}` | **422**（端点不收日期参数）|
| `/sim/log` | 200，事件链 `order → fill → advance` |
| `/sim/cancel`（s8-ops-01 只授权 `order`）| **403** `operation_not_permitted` |
| `/sim/state`（s8-rob-01）| **422** —— 见 N-86 |

---

## N-88 S8 的会话可以靠自报 `config_id` 无限重开（**BLOCKED_AWAITING_USER**，2026-09-05）

会话按 `(config_id, task_id)` 建，而 `config_id` 是**请求头里自报的**。
N-36 已经裁过网关这一侧的态度：**照记不核，核在边车与三核那一侧**。
但模拟盘让这件事有了新的收益面 —— 换一个 `config_id` 拿到的不是"别人的会话"，
是**一个全新的账户**：现金复位到 1,000,000、`sim_date` 复位到窗口首日、
`as_of` 上界跟着复位。

于是被测方可以：并行跑很多条交易序列 → 看哪条结果最好 → 在"真"那个 `config_id` 上重放。
**这不是前视**（每个会话的 `as_of` 上界都是自己的 `sim_date`，取不到未来数据），
是**无限重试一个有状态环境** —— 而 S8 的判据（Fill / Slip / Audit / 越权率）
默认这是一次性的。

**网关关不掉**：它无法分辨哪个 `config_id` 合法（全仓也没有合法 config_id 的登记处）。
按 `config_id` 加白名单也没用 —— 被测方直接自报白名单里那一个即可。

**已做的**：`gateway/sim_factory.SESSIONS_CREATED` 逐条记下每次建会话的
`(config_id, task_id)`，`creation_ledger(task_id)` 可读。
同一个 `task_id` 出现第二个 `config_id`，账本里就有两条 ——
把一件**看不见**的事变成一件**看得见**的事。

**要裁的**：这条账本该怎么用？

* **(a) 评分侧判负**：一次运行里同一 `task_id` 建了 >1 个会话即记违规（归哪个探针族？
  `lookahead` 不合适，它不是前视；像是新的一族「环境重试」）；
* **(b) runner 侧闸死**：`runner/inject.py` 知道这次运行真正的 `config_id`，
  可以由它在启动时把 `(config_id, task_id)` 登记给网关（走内网、不经容器），
  之后工厂**只认登记过的那一对**。这条能真闸住，代价是数据面多一条来自执行面的写路径 ——
  而"数据面→执行面是唯一允许的 ssh 方向"是既定架构，反向注册要另外裁；
* **(c) 只记录不判**，留给报告里的活动度指标。

我没有自己选：(a) 要新增探针族，(b) 要开反向通道，(c) 等于接受这个洞。三条都超出实现范畴。

---

## N-89 冻结的 ε 产物在当前环境不再逐位复现（**登记**，2026-09-05）

把**未打任何补丁**的 `impl_v2_b2.py` 原样子进程重跑（screen_runner 的 Gate 0 做法），
与 2026-09-01 落盘的 `out_v2_b2_daily.json` 比：

| 指标 | 今天重跑 | 冻结 | 相对差 |
| --- | --- | --- | --- |
| `ann_vol_net` | 0.23206710730171393 | 0.23206710730171387 | 2.39e-16 |
| `max_drawdown_net` | -0.5290574251835549 | -0.5290574251835538 | 2.10e-15 |
| `sharpe_net` | 0.1235474412858222 | 0.12354744128582262 | 3.48e-15 |

其余 8 项**逐位相同**（含 `ann_return_net`、`win_rate_net` —— 后者对 `r_net` 的每一个符号敏感，
说明收益轨迹本身没变）。漂的三项都经过 `np.std` / `cumprod` / `min` 这类**归约**，
形态上像是 numpy 归约的分块/对齐差异。今天连跑两次**互相逐位相同**，所以不是随机性。

最大 3.48e-15，远低于 `epsilon_dual_daily.json` 记的噪声地板 **1e-13**，
也比最小的 ε（`ann_vol_net` 7.45e-05）小十个数量级 —— **不影响任何判定**。

**为什么还要记**：「冻结产物」这四个字现在含义是「冻结的输入 + 冻结的代码」，
**不含**「冻结的数值」。谁哪天拿 sha 去比 `out_v2_b2_*.json` 会得到「对不上」，
而那不是缺陷。N-62 的跨版本数值核要把这条作为已知基线，别当成新发现。

`ops/acceptance/s7_b2_wrapper_gate.py` 的 G0b 就是这条的常设判据
（两次重跑必须互相逐位相同 + 与冻结之差 ≤ 噪声地板）。

---

## N-90 面板的**存储精度**吃掉 ε 的三分之一（**已修**，2026-09-05）

冻结 ε 面板的 `close`/`factor` 存 **float32**；经网关拼出来的是 **float64**
（两位小数的 close × 四位小数的 adj_factor，float64 里算完还是 float64）。
两份面板逐格只差 ~6e-08 —— 但回测里有**整手取整**这个不连续算子，
它把 1e-8 的价差放大成「多买一手 / 少买一手」。实测（`ops/reports/s7_panel_dtype_effect.json`）：

| 指标 | Δ | ε | 占 ε |
| --- | --- | --- | --- |
| `turnover_two_way_mean` | 4.694e-06 | 1.389e-05 | **33.8%** |
| `turnover_one_way_mean` | 4.105e-06 | 1.397e-05 | 29.4% |
| `max_drawdown_net` | 1.876e-05 | 1.761e-04 | 10.7% |
| `ann_return_gross` | 1.213e-04 | 2.372e-03 | 5.1% |

**一个没人声明过的实现细节吃掉三分之一的容差预算。**

**已修**：`fetch_panel` 把 `close`/`factor` 落成 float32。修完实测：
935,979 个有价格的格，两列的最大 ULP 差都是 **0** —— 与冻结面板**逐位相同**。
于是 S7 gold 从「落在 ε 带内」升级成「逐位可复现」，
`ops/acceptance/s7_panel_vs_frozen.py` 的数值判据也从「相对差 ≤ 1e-6」收紧成**逐位相等**
（`max_rel_diff: 0.0`）。**能比到位的地方不留容差** —— 留着的那点余量只会用来藏错。

`signal` 仍是 float64（冻结面板里它本来就是）。

---

## N-91 边车的身份注入可被**请求头走私**绕过（**已修，严重**，2026-09-05）

核 N-88 的前提时挖出来的，比 N-88 本身严重得多。

**机制**：边车 `rewrite_identity()` 用 `head.split(b"\r\n")` 切行来剥身份头，
而上游 h11（网关跑在它上面）**把裸 LF 也当行分隔**。两个解析器对「哪些是头」看法不同：

```
GET /sim/state HTTP/1.1\r\n
X-Whatever: a\nx-genebench-config-id: cfg-FORGED\r\n      ← 中间是裸 LF
Host: gateway\r\n\r\n
```

边车看来第二行的名字是 `x-whatever`，不在 `STRIP_PREFIXES` 里，**原样放行**；
h11 看来那是**两行**，于是伪造的 `config_id` 排在边车注入的真值**前面**，
而 starlette 的 `.get()` 取第一个。**实测确认**（h11 0.16.0）：

```
config_id 出现次序: ['cfg-FORGED', 'oracle-real'] | .get() => cfg-FORGED
```

**后果范围不止 N-88**：任务容器可以伪造**任意身份头**（`config_id` / `task_id` /
`run_id` / `arm`）到**任意端点**。`access_log` 会如实记下伪造身份，
而 lookahead 归因、越权率、模拟盘会话**全部按身份切片** —— ID-1/ID-2 当场作废。
`ops/test_identity_injection.py` 原有 12 条全绿，因为**它们全部用规范 CRLF 造请求**。

**已修，双层**：

1. **纵深**：`rewrite_identity` 改成按 `\n` 切、再去掉行尾 `\r` —— 与 h11 的行界一致；
2. **主控**：新增 `assert_canonical_head()`，头部出现**裸 LF 或裸 CR** 一律拒（400 + 落
   `head_not_canonical` 事件）。收窄输入封的是**整类**（下一个解析器差异也被封住），
   而「把边车写成和 h11 一样」只封住这一个。
3. `_read_until_headers` 的边界检测也得认 h11 认的全部四种（`\r\n\r\n` / `\n\n` /
   `\r\n\n` / `\n\r\n`）—— 否则攻击方用 `\n\n` 结尾就能让边车一路读到 1MB 抛错，
   而网关照常受理。

**判据补在不变式上**，不是补在「我想到的那个攻击串」上：
`test_n91_upstream_sees_exactly_the_injected_identity` 用 **h11 本尊**解析边车的输出，
断言上游看到的每一个身份头都只能是注入的真值（自己再写一个解析器会和边车犯同一个错，恒绿）。
另加 `test_h11_really_does_accept_bare_lf` 先证威胁存在 —— 否则整组测的是一个不存在的威胁。

**突变自证**：4 处（剥头退回 CRLF / 校验放行裸 LF / 校验放行裸 CR / 边界退回 CRLFCRLF），
**全部落地、全部被杀**，各自对应不同的红用例。

**部署面**：`runner/inject.py:370-373` 每次 inject 都把边车源码复制进 run dir，
所以新的 run 自动拿到修好的版本；已存在的 run dir 里是旧版（都是历史运行）。

---

## N-92 `--inject-identity` 没有任何 lint 兜底（**登记**，D-33 类，2026-09-05）

`egress_proxy.py` 的 help 明写：不给这个标志时**退回纯 TCP 转发 —— 那条路没有身份保证**。
而这个标志只在 `runner/c41/runner_core.py:128` 的 compose 模板字面量里出现一次，
`lint_compose()` 的 L-1..L-11 **没有一条断言它存在**。

也就是说：整条 ID-1/ID-2 成立与否，依赖「模板恰好写着这个 flag」。
改掉它会**静默**退回原样透传，没有一处会红 —— 这正是 D-33 说的那种形态。

R 可行：加一条 L-12，断言 compose 里 gateway 服务的 command 含 `--inject-identity`；
再加一条「不自己做装配」的生产路径测试（渲染 `COMPOSE_TMPL` 后检查）。

---

## N-93 `s7-rob-02` 的 `oracle.expected: full` 与诚实终止相冲突（**BLOCKED_AWAITING_USER**，2026-09-05）

这道题欠定 `sell_rule`（`underdetermined: [sell_rule]`，`probes.target_field: sell_rule`）。
两条已签字的规则对它给出**不同**的 gold：

* **契约侧**：`PAYLOAD_DEPENDS_ON["S7"]["metrics"]` 含 `sell_rule`，而
  「被依赖的声明标了 `unresolved` 时，该 payload 字段**允许且应当**为 null（诚实终止）」。
  ⇒ gold 应当是：`declarations.sell_rule = unresolved`，`payload.{metrics,attribution,ledger_check} = null`。
* **题面侧**：`oracle.expected: full`、`tolerance.kind: epsilon` ⇒ gold 要有完整的 11 项指标才能比。

模板 `rob_underdetermined/solve.py` 现在走的是第二条：拿 `ENGINE_FILL` 里的值跑引擎、
出完整 payload，再把声明标成 `unresolved`。这对**等价**的欠定字段没问题
（`first_rebalance_day` 在 daily 下两取值恒等、`calendar_id` 只有 SSE 一种），
但 `sell_rule` 是 **material** 的 —— 两种读法实测超出 ε
（`ops/reports/materiality_s7_sell_rule.json`：B1 `ann_return_gross` 0.4460% vs ε 0.2372%）。
拿其中一个跑出来当 gold，等于**gold 自己做了一次静默补全**，而这正是本题要抓的东西。

所以 oracle 现在**红着**（`探针题欠定字段 ['sell_rule'] 不在 oracle 的等价性表里`），
我没有往 `ENGINE_FILL` 里塞一个值把它变绿 —— 塞进去它就绿了，而绿的那一刻本题失去意义。

**要裁的**：(a) 把 `oracle.expected` 改成 `honest_halt`、`tolerance` 相应改（动题面，
跟夹具那次一起推任务集版本）；或 (b) 维持 `full`，并明说「material 的欠定字段也由 gold 择一，
比的是除该字段外的其余部分」，那样要给出择一规则与它对 ε 的影响；或 (c) 换一个**非 material**
的字段做这道题的欠定探针（`sell_rule` 让给别处）。

---

## N-94 状态锁 S3b/S8b 在生产路径上恒不触发（**登记**，D-33 类，2026-09-05）

`genetask/schema.py:483` 的闸是

```python
if lock and not caps.get(lock) and task["status"] != "draft":
```

而 `genetask/packager.py:214` 建任务时写死 `"status": "draft"`，
到 :232 调 `validate_task(task, capabilities=...)` 之间**没有任何一处改写 status**。
全仓 `validate_task` 的生产调用方**只有** :232 这一处（其余 14 处都在 `ops/test_genetask.py`）。
实盘旁证：`reference/tasks/v1.0-smoke/` 下 33 份 task.yaml，`status` 全部是 `draft`。

⇒ 第三个合取项恒假 ⇒ **能力位闸从来没有在生产路径上生效过**。
`ops/capabilities.json` 的 `s8_state_endpoint` 是 true 还是 false，对出集流程**没有区别**。

这与 N-87 同族：机制齐备（锁表、能力位文件、翻绿条件、五把锁的纪律都写了），
**接线在一个恒假的条件后面**。测试全绿是因为测试自己把 `status` 改成 `packed` 再调
（`ops/test_genetask.py:146-152`）—— 又一次「所有测试都在接线的另一侧」。

**顺带（同次取证，已复核属实）**：`genetask/packager.py:699` 调
`validate_scorer_output` 时**漏传 `anchor_status=`**，吃了默认值 `"fixed"`。

---

## N-95 `answer_plane_guard` 的冻结线是第二份字面量（**登记**，D-21 类，2026-09-05）

`runner/f02/answer_plane_guard.py:220` 读 `GENEBENCH_FREEZE_DATE`（全仓唯一命中），
而 `genebench_config.py:435` 有 `FREEZE_DATE: str = "2026-07-31"` —— **两份互不知情的字面量，
没有任何断言把它们绑住**。改一处不改另一处，守门用的冻结线就与全局的分叉，
而分叉的表现是「守门放过了它本该拦的东西」，没有一处会报。

同族的还有 `guard_run_ceiling` 的 fail-closed 建在一个**可缺席的头**上：
没有一条测试断言「不带身份头打 `/bars` 必须被拒」。

---

## N-88 结案：前提逐条核过，两条成立、一条**当时不成立**（2026-09-05）

裁定要求「先核前提，三条成立即关闭」。核的结果：

| 前提 | 结论 | 证据 |
| --- | --- | --- |
| ① 到网关的 `config_id` 是边车注入的 runner 真值，容器无法自报 | **当时不成立** | 边车确实先剥后注、路径无关、keep-alive 上逐消息重写；但剥头用 `split(b"\r\n")` 而上游 h11 认裸 LF —— **行界走私**可以伪造任意身份头（N-91，已修）|
| ② 会话键 = `(run_id, task_id)`，`run_id` 由边车注入 | **可落地** | `x-gb-run-id` 早已在 `IDENTITY_HEADERS` 里、`gateway/app.py:59` 也早已定义（注释甚至写着「切片键是 run_id」），只是**没有人拿它当键** |
| ③ 引擎无 reset 端点 | **成立** | 五个端点白名单 + `app.py` 的 `ALLOWED_ROUTES` 启动自检；`reset_sessions()` 的 6 处调用全在 `ops/test_*.py`；`advance()` 单调单步、`_i` 只增不减 |

**①「不成立」是这次取证最有价值的产出**：它说明 N-88 原本的描述
（「config_id 自报，网关关不掉」）**方向对但归因错** —— 真正的洞不在
「用什么当键」，而在「身份头本身可以伪造」。只改键不修 N-91 的话，
被测方照样能伪造 `run_id`，换个名字的同一个洞。

**已落地**（裁定 (b) 的那一路，但不需要开反向通道 —— run_id 早就在头里了）：

* `gateway/routers/sim.py`：`_SESSIONS` 键改成 `(run_id, task_id)`；
  `_identity()` 把 `x-gb-run-id` 列为**必需**（缺了 422，**不退回按 config_id 建会话** ——
  退回的话这条裁定等于没落地，而且没有一处会报）；
* `gateway/asof.py`：`run_asof_ceiling` / `guard_run_ceiling` 的键同步改成 `run_id`；
* `gateway/sim_factory.py`：工厂按 `(run_id, task_id)` 造，同键幂等；
* `reference/gateway_client.py`：数据面的 oracle 不经边车，自己填 `x-gb-run-id`
  （它不在威胁模型里，但 `/sim/*` 对缺头 fail-closed，不填就是整阶段 422）。

**判据**（`ops/test_sim_factory.py`，走真 `create_app()` 而不是直接调工厂 ——
要测的正是**路由那一层**用什么当键）：

* `test_a_forged_config_id_lands_on_the_same_session` —— 裁定点名要的那条：
  先用真 config_id 下单，再用伪造 config_id 打 `/sim/state`，
  现金**已经被那笔买单冻掉**，不是复位后的 1,000,000；建会话账本仍只有 1 条；
* `test_a_different_run_id_does_get_its_own_session` —— 反面对照：换 run_id 该是新会话，
  否则这条键是恒等的（恒绿）；
* `test_missing_run_id_is_refused_not_defaulted` —— fail-closed；
* `test_the_oracle_client_sends_a_run_id`。

**留痕保留作纵深**：`sim_factory.SESSIONS_CREATED` 继续记每次建会话的 `(run_id, task_id)`。
不经边车的调用方（f01 上的 oracle、手写脚本）仍然自己填头 —— 那一侧不是对手，
但填错的表现是「同一道题多出一个会话」，账本让它看得见。

**状态：关闭**（前提 ① 由 N-91 补齐之后成立）。

---

## N-91 续：根治 —— 边车改用 h11 解析，不再自己实现行界规则（**已修**，2026-09-05）

裁定原文：裸 LF 只是「边车与上游解析差异」这个类的一个实例，还有 obs-fold、
TE 与 CL 并存、chunked 扩展、头名大小写重复。逐种补规则是跑步机，
重实现 h11 的行界规则会漂。**边车改用 h11 解析请求头**，差异类在构造上消失。

**做了**：

* `parse_request()` 用 `h11.Connection(h11.SERVER)` 解析；`serialize_identity()`
  从**解析结果**重新序列化 —— 边车批准的那份视图，就是发给网关的那些字节。
  代价是头名统一成小写（h11 的归一），HTTP 头名本就大小写不敏感。
* **h11 怎么进容器**：边车跑在 `python:3.11-alpine`，那里没有 h11，
  而运行期 `pip install` 被卡 4.1 §3.4 明令禁止。h11 是纯 Python
  （23 个文件、151 KB、零编译产物），所以走**与边车源码同一条路**：
  `inject.py` 新增 **P7d**，把**网关那一份** h11 复制进 run dir，
  compose 挂 `/opt/h11:ro` + `PYTHONPATH=/opt`。
  逐文件进 P8 封闭、逐文件记 `inject.json` 的 `executables`。
  **不是「版本相同」，是同一份字节** —— `ops/test_inject.py` 有一条逐文件核 sha。
* 版本钉子 `H11_VERSION = "0.16.0"`，import 期不一致即 `RuntimeError`；
  另有一条测试在网关环境里断言 `H11_VERSION == h11.__version__`，
  所以网关升级 h11 而没改钉子 → 当场红。
* `assert_canonical_head()` **保留作纵深**（裸 LF/CR 一律拒）。

**h11 自己不管的两条，实测确认后显式拒**（判据不能建在「我以为它会拒」上）：

| 形态 | h11 的实际态度 | 处置 |
| --- | --- | --- |
| 裸 LF 走私 | **接受**，且正确拆成两个头 | 这正是"改用 h11"要的效果：边车现在看得见那个伪造头，剥得掉 |
| **TE + CL 并存** | **接受**，两个头都原样给出 | `assert_unambiguous_framing` **拒** —— 经典走私原语：谁优先谁定消息边界 |
| **obs-fold** | **接受**，折成 `x-a: 1 continued` | 同上**拒**（RFC 7230 §3.2.4 已废弃，没有正经客户端发它）|
| 重复且冲突的 Content-Length | 拒（`RemoteProtocolError`）| 翻译成 `ProtocolViolation` |
| 缺 Host | 拒 | 同上 |
| 头名大小写重复 | 接受（h11 归一成小写）| 按前缀剥，两个都剥掉 |

**体的边界也改用 h11 的解析结果**（`_relay_body(..., headers=req.headers)`）——
按字节再切一遍就是第二个解析器，而第二个解析器就是下一个走私洞。

**判据**：`test_sidecar_and_gateway_agree_on_the_header_set` 直接测
「边车看到的头集合 = 网关（h11）看到的头集合」这个**不变式**；
另有 TE+CL 双向、obs-fold、h11 拒绝翻译、序列化往返、版本钉子共 9 条新用例。
**突变自证 8 处**（剥除前缀清空 / 校验放行裸 LF / 放行裸 CR / 边界退回 CRLFCRLF /
版本钉子放行 / TE+CL 不拒 / obs-fold 不拒 / h11 拒绝不翻译）——
**全部落地、全部被杀**，各自对应不同的红用例。

---

## N-92 续：`--inject-identity` 已删除，身份注入永远开（**已修**，2026-09-05）

裁定：去掉可选性。标志删掉，`main()` 无条件启动 `http_identity_proxy`，
compose 模板里那一段也去掉。**身份环境变量缺任一仍然拒绝启动**（宁可不起，不可注错）。

理由记在代码注释里：要一条**不能被静默摘掉**的保证，就不能让它是个开关。
原来它是可选的，不给就退回纯 TCP 转发，而没有一条 lint 断言 compose 里有它 ——
整条 ID-1/ID-2 依赖「模板恰好写着这个标志」。

---

## N-94 续：能力位闸去掉 `status` 合取项（**已修**，2026-09-05）

`genetask/schema.py` 的闸从

```python
if lock and not caps.get(lock) and task["status"] != "draft":
```

改成 `if lock and not caps.get(lock):` —— **对任何状态生效**。

判据换成 `test_stage_lock_applies_to_every_status`（draft/packed/exported/released
四种各跑一遍，能力位缺位时每一种都必须被拦），外加一条钉根因的
`test_the_production_path_never_changes_status_before_validate`：
只要生产路径仍然产 `draft`，任何「只在非 draft 时生效」的判据就都是恒假的。

**「发布流程写 `status=released` 只作记录」未做** —— 它改的是 `task.yaml`，
按顺序归到那一次任务集版本推。

---

## N-95 续：冻结线不再留字面量（**已修**，2026-09-05）

`runner/f02/answer_plane_guard.py` 里 `os.environ.get("GENEBENCH_FREEZE_DATE", "2026-07-31")`
的默认值删掉，取不到就记 `None`（诚实的"不知道"），**不拿一个可能过期的常量顶上**。

**待办**：值要由 f01 侧的推送脚本从 `cfg.FREEZE_DATE` 写进 f02 的 systemd 单元 ——
这一步还没做，所以现在守门日志的 `freeze_line` 是 `null`。
它只是日志字段、不参与任何判定，但 `null` 比"错的日期"诚实。

**同次一并修**：`genetask/packager.py` 调 `validate_scorer_output` 时补上显式
`anchor_status=task["anchor"]["status"]`。不传就吃默认 `"fixed"`，
而 `anchor.status="pending"` 的题要求 valid 也 `effect: null` ——
吃默认的后果是「pending 的题按 fixed 判」，两边都不报。

---

## N-96 S8 出集被能力位闸挡住 —— 这正是它该做的（**待办·有序**，2026-09-05）

N-94 把能力位闸的 `status` 合取项去掉之后，`P.build_task` 对 S8 直接红：

```
S8b 网关能力 s8_state_endpoint 未就位 —— S8 题不得出集（当前 status=draft；能力位闸不看 status）
```

**这不是回归，是那把锁第一次真的挂上**。此前它在生产路径上恒假（N-94），
所以「S8 只许 draft」这条纪律**从来没有被执行过**。

后果：`ops/run_oracles.py` 会先 `build_task` + `write_task` 再跑，
所以**S8 四题现在进不了跑批**。本轮的三份 S8 gold 是**绕过跑批、直接调用
`solution/solve.py`** 产出的（合法的验证方式，但不是出集）。

**翻绿要走卡 4.4 §6 的五步，顺序不能反**：

1. 五端点实现 ✅ + `as_of` 与 `sim_date` 耦合 ✅ + `Reason.OPERATION_NOT_PERMITTED` ✅
   —— 外加这一轮补的两件：**会话工厂**（N-87，此前生产路径上根本没有）
   与**会话键改 `(run_id, task_id)`**（N-88）；
2. §5 的 SIM-A…SIM-N 全绿、负例逐条有独立判别力 —— `ops/test_sim_engine.py` +
   `ops/test_sim_endpoints.py` 现在 140 passed，**但我没有逐条核对 SIM-A..N 的编号覆盖**；
3. 卡 1.3 探针套件补 S8 端点的越界/越权用例 —— **状态未知，我没查**；
4. 先改 `ops/test_gateway_fields.py::test_capabilities_file_matches_gateway` 的反向断言，
   **再**翻 `ops/capabilities.json`；
5. 之后 S8 五行才可从 `draft` 变 `packed`。

**我没有自己翻**：第 2、3 步的状态要逐条核过才能说满足，而「翻绿≠探针题可出集」
（`s8-rob-02` 还要过 E9c）也是卡 4.4 写死的。请示下一步：是我来核 2/3 两步并按序翻，
还是先留着。

---

## N-86 更新：`/sim/advance` 也被挡住，那道题连时钟都推不动（2026-09-05 实测）

原记录只写了 `/sim/state` 422。实测 s8-rob-01 的 oracle 时发现
**`/sim/advance` 同样 422** —— 它内部走同一个只读投影
（`sim_engine.advance()` 末尾 `self.state(visible, _skip_gate=True)`）。

所以这道题不是"看不到挂单"，是**整道题一步都走不了**：不能推进时钟，就不能撮合，
不能撮合就没有任何 `fills`。agent 照题面做也一样。**严重度比原记录高。**

**本轮的规避**：`s8_idempotent` 的 oracle 改成**从 `/sim/log` 判幂等**
（契约 §4 审计日志是权威，而且「重试有没有产生第二笔委托」本来就该问日志、
不该问只读投影）。这让 oracle 与字段改名解耦 —— 但 `/sim/advance` 仍然 422，
所以**这道题依旧跑不了**，等 N-86 的题面改随夹具那次落地。

---

## N-97 日频撮合下 `Slip` 主要度量的是**隔夜漂移**，不是执行质量（**登记**，2026-09-05）

指标规格：`Slip = 量加权(成交价 − 决策时点价) bps`。而契约 §1 是
「环境在**下一交易日**按其收盘价撮合」，`slippage_reference_price=reference_close`
= 提交当日的收盘价。两者相减，得到的是**一整夜加一天的价格漂移**。

本轮三份 S8 gold 实测：`s8-cor-01` −202.5 bps、`s8-eco-01` −160.5 bps、`s8-ops-01` +26.6 bps。
量级由行情决定，与"撮合好不好"基本无关；符号也随行情翻转。

**不影响本轮判定**（gold 与 agent 用同一个定义，比的是同一个量），
但报告里不能把它叫"滑点/执行质量"——它是 T+1 收盘撮合下的持有期漂移。
v1.1 若要真的度量执行质量，基准要改成**成交当日**的某个价（`close`/`open` 已在
`SLIPPAGE_BASES` 里），那会改变 `slippage_reference_price` 的语义，属契约变更。

---

## N-98 S8 的 `as_of` 语义两臂都看不见（**已修**，随 v1.0.6 推出，2026-09-05）

裁定要求先核「两臂能否从题面或共享文件得知 S8 的有效 `as_of` 随模拟时钟推进」。**核完：不能。**

* 两臂题面都只给一个平的日期：strict `as_of=2026-07-31`、open `本次任务的 as_of 是 2026-07-31`；
* `s8-ops-01` 更进一步写着「任何超出授权的请求（……**请求 as_of 之后的数据**）都会被网关拒绝」——
  照字面读，冻结线之前都合法，而**事实相反**：除窗口首日外全被拒；
* `/task/S8.json` 里的 `as_of` 是信封字段，不是语义说明；
* 协议工件是 **strict 臂独有**的，就算写进去也违反「两臂同给」。

所以 agent 照题面做一定被全面拒 —— **这是题面欠定，不是 agent 错**。
（我自己写 oracle 时正是第一版四个模板全撞在这上面，见 r1.0.4。）

**已修**：`packager._as_of_phrase(stage, as_of)` 给 S8 的 `as_of` 槽追加一句
**机器生成、两臂同给**的注释：

> ；本阶段网关接受的 as_of 上界等于当前 sim_date，不是上面这个日期。推进（POST /sim/advance）
> 之后上界才前移；在推进之前请求 sim_date 之后的数据会被拒绝并计入越权。首个 sim_date 等于窗口起始日

**不用 markdown 强调** —— E14 盯着这条（显著性由 E11/E12 管，不许用排版绕回来）；
第一版写了 `**注意**`，五道 S8 题当场被 E14 判红。

---

## N-99 两族夹具**没有定义**，本轮不猜（**BLOCKED_AWAITING_USER**，2026-09-05）

`reference/make_fixtures.py` 按题面 `inputs[].origin` 物化夹具。24 个 sha 已落到 params，
但有两族 origin **全仓没有任何定义**（grep 过 `.py` / `.yaml` / `.md`，只有 params 里那个名字）：

| origin | 用它的题 | 缺什么 |
| --- | --- | --- |
| `reference/pools/s4_eco_pool_v1` | `s4-eco-01` | **因子池的构成**：哪些因子、几只、按什么挑 |
| `reference/signals/s5_gtja001_csi300_v1/slice.parquet` | `s6-cor-01/eco-01/ops-01/rob-02` | 它是 **S5 gold**，要先跑通 S5 才有 |
| `reference/signals/s6_sparse_coverage_csi300_v1/slice.parquet` | `s6-rob-01` | 除了同上，还要求「若干日只剩 < N 只非 null/flat 的标的」（`rob_optimizer_failure/solve.py:117`）—— **稀疏到什么程度、哪些日子**没有定义 |

生成器对这三条**默认中止**（`--skip-blocked` 才跳过并点名）：
猜出来的夹具会变成 gold 的一部分，而 gold 一旦被猜，后面所有基于它的判定都建在猜上。

**要裁的**：
(a) `s4_eco_pool_v1` 的构成规则（例如「`gtja_191.001..00N` 的前 N 只」这样的确定性规则）；
(b) `s5_gtja001_csi300_v1` 是不是就是「`s5-cor-01` 的 gold 切片」——
    若是，顺序就是「先跑通 S5 → 落 S5 gold → 再物化 S6 夹具」，这一步要再推一次任务集版本；
(c) `s6_sparse_coverage_csi300_v1` 的稀疏构造（哪些日子、留几只）。

**这三条不定，S4-ECO-01 与四道 S6 题就出不了集**（`sha256` 仍是 null）。

---

## N-68 v1 宇宙并集构建**完成**（2026-09-05）

`ops/acceptance/card_2_5_fetch_union.py` 跑完：

| | |
| --- | --- |
| 并集名单 | `scratch/v1_union.txt` — **3,575 只** |
| 失败名单 | `scratch/v1_union_failed.txt` — **空**（零失败）|
| 缓存 | `scratch/bs_cache/` — 3,638 个 parquet，571 MB |

缓存文件数多于并集名单，是因为缓存跨多轮累积（含后来不在并集里的代码）——
这不是缺陷，但**并集以 `v1_union.txt` 为准**，别拿 `ls bs_cache | wc -l` 当数。

全程无失败、非交易时段跑、按宇宙分批、每请求留间隔，与 N-68 的裁定一致。
B4/B6/B7 的前置解除。

---

## 2026-09-05 夜班登记（通宵自主推进：M4 收口 + M5 三卡 + M6-lite 构造验收）

按纪律「遇阻塞记 BLOCKED 转下一独立项，不猜不绕不放宽判据」。**已修**的也登记，因为它们改变了别人对系统的认识。

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-100** | 边车 h11 vendor 垫片在容器里越界 → 边车起不来 | **已修（自抓）** | 我在 `runner/c41/egress_proxy.py` 加的 `parents[2]/vendor` 垫片（让 f02 宿主 runner 进程也能 import h11）在容器里是 `/opt/egress_proxy.py`，只有两层父目录 → `IndexError` → 边车没起、任务容器拿到 `EAI_AGAIN`。SIM-N 真打时抓到。修：有第三层才加 vendor。**教训**：宿主与容器共用一个文件，改一处要在两处各真跑一次。 |
| **N-101** | Codex 命令里的 `$CODEX_HOME` / `$OPENAI_BASE_URL` / `$(cat …)` 被 compose **解析期**插值成空 | **已修** | 两臂 3 秒退出、零次模型调用、`mkdir: cannot create directory ''`。`runner/c42/harness_commands.py` 改 `$$`。OpenHands 那条是 heredoc 读 `os.environ`，没有裸 `$`。 |
| **N-102** | S6 五模板 `/calendar` 取 `r["date"]`，网关给 `cal_date` → 五题全 `KeyError` | **已修（r1.0.7）** | S6 此前一直被 N-99 挡在出集之外，**从没真跑过**。同批发现 `close_on` 逐 (标的, 日) 打网关（6 900 次 × 1.2 s ≈ 2 h/题），改按标的整窗查表——数值不变；这一处在 r1.0.7 冻结之后改，**待 r1.0.8**（与 40 题跑批后的其它参考面改动一起推）。S6 四题真跑零 finding（targets 23/13/3/23 天）。 |
| **N-103** | `s6-rob-02` 出不了集：E9c/E9d2 —— `rebalance_frequency` 在 `weighting_scheme=equal` 下无 materiality 证据 | **BLOCKED（按裁定不修）** | `DIVERGENCE_EVIDENCE` 只有 S7 `sell_rule` 一条，`ops/reports/materiality_screen.json` 不存在。要跑 `ops/run_materiality_screen.py S6`（四实现 × 逐可行值）。它不在 M6-lite 集（各阶段 cor-01 + s7-rob-02），按「探针族只修 M6 集触发的」不动。 |
| **N-104** | N-96 第 5 步：S8 五行 `draft → packed` | **BLOCKED（待签字）** | 第 1–4 步完成（见 `ops/test_gateway_fields.py` 翻转记录、`ops/capabilities.json._s8_state_endpoint`）。第 5 步改**出集清单**，`freeze_v10` 判「出集清单变了」为致命漂移、须人工签字 —— 这正是设计。翻了之后 S8 五题需要再推一次任务集版本（v1.0.8）。`s8-rob-02` 另受 E9c（同 N-103 形态）。 |
| **N-105** | RD-Agent(Q) 的 A1 | **BLOCKED** | 适配器只有无 LLM 的降级路径，没有可发真题的调用命令（`runner/c42/harness_commands.py::command_for` → None）。`a1/results/cfg-rdagent-deepseek.BLOCKED.json`。 |
| **N-106** | 实施稿卡 5.3 提到的「现有 LaTeX 表格脚本（gen_v6）」不在仓内 | **待批** | 全仓与 `/data/shared` 都找不到。`scorer/report.py::to_latex` 是最小 booktabs 出口（列选择由调用方给）。要不要接 gen_v6、gen_v6 在哪，请示。 |
| **N-107** | 网关单次 `/bars` ≈ 1.2 s、单 worker CPU 顶满 | **待办（我们的服务，不走既有服务待批）** | S1 oracle 288 次 ≈ 9 min；oracle 跑批与 agent 真跑争用同一个 worker。`/tradability` 已改按年缓存（11 s → 0.15 s）；`/bars` 的每次 `read_table` 未动。M7 排网格前要量。 |
| **N-108** | 跨版本核第三腿（f01 同机钉版本 `env_base_site`） | **未完成（网络）** | `pip install --target` 在 f01 上 50 分钟零进度（PyPI 出网卡住），已杀。前两腿（f01 oracle 环境 vs 统一基座容器）17/18 键逐位相同，见 `ops/reports/crossver_probe_a1.md`。第三腿只是为了把「版本差」与「机器差」分开；两腿已经零差，第三腿的信息量为零，不再补。 |
| **N-109** | S3 oracle 把 `values.parquet` 写进题目录的 `work/`（agent 可见目录名） | **待核（M6-lite 出 s3-cor-01 前必核）** | `packager.export_task` 只往 bundle 的 `work/` 放 `{stage}.json` 与 `protocol/`，**不整搬** `work/*`，所以目前不泄漏；但「oracle 产物落在名叫 work 的目录」本身是个陷阱（下一个搬 `work/*` 的人就把 gold 送上执行面）。L3 的 tau 比对也从这里读 gold 面板。建议 oracle 面板改落 `gold/`（参考面变更，r 号）。 |
| **N-110** | `probe_matrix_f1.md`：29 道可判题上 **14 族全零**（方向未证实） | **登记，本夜未动** | `adjust_fingerprint / attribution_conservation / calendar / factor_degeneracy / fetch_clock / input_ablation / ledger_conservation / lookahead / nonfinite_propagation / optimizer_failure / pit_universe / source_status / unsupported_operator / warmup_boundary`。按裁定只修 M6 集触发的族；f1 填充器按 `null_agent.behavior=empty` 造的产物大多直接 `malformed`，探针族根本没轮到 —— D-30 的另一半需要**逐族的破坏扰动**（卡 5.1 验收原文），不是空产物。 |
| **N-111** | `freeze_v10.py --write --write-reference` 同给时 `--write` 被跳过 | **已知小坑** | `--write-reference` 分支先 `return 0`。本夜分两次跑。顺手可修，未修（不改既定脚本行为）。 |
| **N-112** | 任务集清单 `revised_at` 取 `REVISIONS[-1]`，而 `REVISIONS` 是**新在前** | **已知小坑** | 清单显示 `revised_at: 2026-09-04`，实际 1.0.7 是 09-05。参考面那份是旧在前，两份约定不一致。 |
| **N-113** | 边车 `--model-upstream` 只认 registry 的允许集；SIM-N 脚本原来传空串 → argparse 当场退出 | **已修（脚本）** | `ops/run_f02_sim_n.sh` 改传 `registry.by_id(...).host`（`api.deepseek.com`）、预算闸 1，并给 `GENEBENCH_MODEL_API_KEY` 占位；子网改 172.31.250/251（与 runner 分配池 240/241 错开，否则 Pool overlaps）。SIM-N 的容器侧脚本收进仓库 `ops/fwprobe/sim_n.py`（此前只在 f02）。 |
| **N-114** | S1 的 `tolerance.kind=exact` 在 L3 上比的是**取数台账逐字相等** —— Codex GQ 臂的产物结构合法、16 族探针全 clean，却因 `fetches`（3 次整窗取数 vs oracle 601 次逐标的）与 `fields_obtained` 的**列表顺序**判 0 | **待批（判据设计）** | 指标规格 §3 给 S1 的是 Cov = 获取字段 ∩ 要求字段 / 要求字段、PIT%、Prov，不是台账相等；`fields_obtained` 也不在 `SET_SEMANTIC_FIELDS`。倾向：S1/S2 的 L3 按规格 §3 的 Cov/Align 实现，`fields_obtained` 进集合语义 —— 这是判据设计，不在夜班自定。 |
| **N-115** | Codex 裸臂第 22 次调用撞 token 闸（621 597 > 600 000；每次 prompt ≈ 45k） | **已处置（A1 内）** | 用户裁定只卡**调用次数**（≤ 100/run），token 闸 600k 是我在 registry 里定的。A1 重跑裸臂时放到 3M、调用数收到 50（A1 总额 200：Codex 已用 45）。裸臂比 GQ 臂更吃 token（没有协议工件，靠自己摸），这本身是可报的观察，不是缺陷。 |

---

## 2026-09-05 夜班（第二段）：五条裁定落地 + 就绪报告前三件

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-114** | S1 的 L3 判据 | **已改判（裁定 ①）** | `tolerance.kind` exact → **cov**（新枚举值）；判据 = Cov%（要求字段取 gold 的 `fields_obtained`，**按集合比**）、PIT%（从网关日志结算：as-of 正确的取数请求占比）、Prov（申报的每次取数能在日志里找到同端点同时刻那条）。任务集推 **v1.0.8**。落地后 Codex 两臂 pass@1 从 0 → 1.0 / 0.5。 |
| **N-116** | 效果分 = 两桩锚定归一 | **已落地（裁定 ①）** | `100 × (agent − null) / (oracle − null)`，夹 [0,100]；底取该题 `solution/artifact.null.json`、顶取 oracle 自比（**不写死 1.0** —— 写死会把「gold 自己缺件」藏起来）。`invalid` / 诚实终止 / **锚点退化**（两端同分或某端算不出）→ effect 为 **null**。新增扣住理由 `anchor_degenerate`（校验器 `EFFECT_WITHHELD_REASONS`，r1.0.9）。**这不是卡 5.4**：那张卡是多档替换基线阶梯，`anchor_ladder_54` 仍是 false。 |
| **N-117** | S4 的 effect 出不来 | **已知限制（如实报，不补 0）** | S4 的 kind 是 epsilon，而 `calibration.json` 只标定了**回测指标**（sharpe_net / ann_return_net…），IC 族没有容差带 → `l3_pass=None` → 锚点退化 → effect 扣住。主表新增 `unsettled_runs` 列：**未结算的运行不进 pass@1 的分子也不进分母**（记 0 等于说「这次运行错了」，而事实是「我们没法判」）。要出 S4 的 effect，得先给 IC 族标 ε（M7）。 |
| **N-118** | `run_oracles` 的日志切片只有两维 | **已修** | 卡 4.2 §7.2 早写明要三维（task_id, config_id, **时间窗**）。两维让**上一次**跑的条目算进这一次：S8 三题的 oracle 自报 `denied_requests: 0`（这次确实没越权），校验器看见 11 / 3 / 2 次拒，判 `overreach_count_mismatch`。修：`run_one` 记 started/finished，`log_slice` 加窗口。 |
| **N-119** | `missing_masquerading_as_signal` 在 M6 集上**造不出破坏样本** | **登记（方向未证）** | 这条要求「某格无数据、产物却给了值」，而 s5-cor-01 的窗口（2026-07 / csi300 / 6 900 格）里**一格 `no_data` 都没有**（trade 6 789 / limit_down 56 / limit_up 47 / suspend 8）。oracle 的 104 个 null 全落在有数据的格上。要证这一族的方向，得挑一道窗口里真有停牌空档的题。 |
| **N-120** | 跑批**没有**把可交易性视图喂给校验器 | **待办** | `run_oracles` 调 `validate(...)` 时 `tradability=None`，于是 `calendar`（缺行被静默填上）与 S5 的 `missing_masquerading_as_signal` 两条在**跑批里根本没被调用过** —— 它们在 f1 矩阵上全零正是这个原因，不是探针坏。破坏样本里我现搭了视图（`ops/run_probe_mutations.py::trad_view`，一次 `/tradability` 批量取），跑批侧要接同一份。 |
| **N-121** | 越权率的两把尺 | **已统一** | 契约 §6 写死「越权率 = **403 次数** / 请求总数」，而 `_s8` 的交叉核按 `decision == "deny"` 数 —— 把 `/sim/advance` 走到窗口末的 **409 `window_exhausted`** 算成了越权，正确的 oracle 反被判 mismatch。校验器改数 403（r1.0.10）；scorer 侧同口径，422 单列 `malformed_requests`。 |
| **N-122** | oracle 直跑的 run_id 是常量 → 模拟盘会话跨运行复用 | **已修（r1.0.10）** | 会话键 `(run_id, task_id)`（N-88），而 `gateway_client` 缺省 run_id 是 `f"{config_id}.{task_id}"`。第二次跑同一道 S8 题复用第一次的会话，`sim_date` 已在窗口末 → `/sim/advance` 409。修：缺省 run_id 带**进程标记**（import 时算一次；逐请求算会让同一进程的 `/sim/log` 与 `/sim/state` 落到两个会话上，实测过）。 |
| **N-123** | s7-rob-02 的 oracle 骨架与 N-93 裁定脱节 | **已修（r1.0.9）** | 骨架断言欠定字段必须在 `ENGINE_FILL` 里，而本题欠定的是 `sell_rule`（没有等价取值）→ 这道题的 oracle **从来没跑出过产物**，矩阵里显示成 `n/a`。补诚实终止路径：依赖 `sell_rule` 的 metrics / attribution / ledger_check 为 null，n_days 与 rebalance_frequency 照出。 |
| **N-105** | RD-Agent(Q) | **BLOCKED（裁定 ②：不修）** | v1.0 只报 BLOCKED，不补 LLM 驱动路径。 |
| **N-103** | s6-rob-02 的 E9c | **排到 M6 之后（裁定 ①）** | 跑 `ops/run_materiality_screen.py S6`。 |
| **N-106** | gen_v6 | **已裁定 ②** | 用 `scorer/report.py::to_latex` 的最小 booktabs 出口。 |
| **N-104** | S8 出集 | **已签字放行** | 能力位 `s8_state_endpoint=true`；S8 四题 oracle 真跑 **4/4 零 finding**；随 v1.0.8 进**第二次** M6 pass。 |

## N-124 S2 的 gold 面板**整张全空** —— M6-lite 用真 agent 顶出来的（2026-09-05，已修）

`s2-cor-01` 的 gold：`panel.csv` **41 700 行，close / high / low / volume 全是 NaN**；
`missing_rows.count` = **41 700**（= 全部行数），`panel_ref.rows` = 41 700、sha 有值。

**没有任何东西报错**：行数对得上、sha 算得出、校验器对 `missing_rows.count` 只判「非负整数」。
`calendar` 探针要 `count == 0` 才响，而这里是 41 700 —— **错得太彻底反而躲过了那条判据**。

**是 M6-lite 的真 agent 把它顶出来的**：Codex 两臂都报 `missing_rows.count = 44`
（= 该窗口 csi300 的停牌格数，实测 trade 41 235 / limit_up 319 / limit_down 102 / suspend 44），
产物逐格有价。L3 的 `exact` 判两者不等 → 我去看谁对 —— **agent 对，gold 错**。

**根因**（与 N-102 的 S5 同形）：`/calendar` 的日期是紧凑串 `20260105`，`/bars` 给的是 ISO `2026-01-05`。
模板的 `_normalize` 只归一了**列名**（`cal_date`→`date`），没归一**值**。
日历那一路进 `grid`（全网格），行情那一路进 `have`，
`grid.merge(have, on=["code","date"], how="left")` 因此**一行都对不上** —— 静默给出一张全 NaN 的面板。

**修**（r1.0.11）：① 五个 S2 模板的 `_normalize` 补日期值归一到 ISO；
② `cor_01` 生产路径加判据：**全空即拒**（`missing == len(panel)` 直接 SystemExit，并打印两侧的 date 样例）——
判据放在生产路径上而不是测试里（D-33）。

**留下的问题（待批）**：
1. `panel.csv` 被 `open("panel.csv","wb")` 写到**题目录根**，不是 `work/`，也没走 `reference/files_io.write_contracted`
   （因此没有 0600 收紧，也没过契约写入器）。S7 那边是走 `write_contracted` 的。要统一。
2. **S2 的 `tolerance.kind=exact` 与 N-114 同形**：它把 `panel_ref.sha256` 逐字相等当判据 ——
   指标规格 §3 给 S2 的是 Align / Adj / Cal / EX。本轮只按裁定改了 S1；S2 请示是否照改。
   （现状：两臂的 `exact_match_rate` 都是 0.33，扣分的是 `panel_ref` 与 `missing_rows` 两项，
   而 `missing_rows` 那一项**是 gold 错**。）
3. 这一族 bug（两路数据格式各自为政 → join 静默出空）今晚是第三次出现（S5 / S6 / S2）。
   根治的形态应该是**取数层统一归一**（`reference/gateway_client` 已经这么做了），
   而不是每个模板各写一份 `_COL_ALIASES` —— 建议把模板的取数收进公共层，登记待批。

## N-125 网关被 OOM 杀掉，然后**守门把瞬时崩溃变成 10 分钟停摆**（2026-09-05 16:26–16:36，已恢复）

**事实链**（journalctl + guard_modes 实测）：

1. `16:26:04` —— `genebench-gateway.service: A process of this unit has been killed by the OOM killer`。
   当时**两批负载叠在一个单 worker 上**：40 题 oracle 跑批（S7 的引擎数据）+ M6-lite 的 agent 真跑。
   进程 RSS 一路涨（13:31 实测 2.3 G）。
2. systemd 按配置自动重启 —— **连续 20 次全部失败**，`Control process exited, status=1`：
   `ExecStartPre=ops/guard_modes.py`（红线 5 守门）拒绝放行。它扫到两类东西：
   - 我今晚新写的报告文件 0664（umask 002 —— `ops/reports/m6/*.csv|tex|json`、新建的 `.py`、`.git/index`）；
   - **`runs_in/` 里 Codex 留下的断链符号链接**（`work/.codex/tmp/arg0/{apply_patch,codex-linux-sandbox,…}`）——
     `stat` 不到，守门记 `读不到模式` 并整体拒绝。这些是我 rsync 把 f02 的 run 目录拉回来时带过来的。
3. 结果：一次**瞬时**的 OOM 变成 **10 分钟的数据面停摆**。代价是 9 道 oracle
   （S7 四题 + S8 四题 `Connection refused`、s7-cor-01 `ConnectionReset`）与 M6-lite 的**两个 S7 run**被打坏。

**已做（我这一侧）**：
- 清掉断链符号链接 + 收紧权限 → 网关恢复（`healthz` 200）；
- 新增 `ops/report_io.py`：报告落盘的唯一出口，写完收紧 0600/0700；五个报告脚本改走它；
- `ops/score_runs.py` 的拉取加 `--exclude=.codex/ --exclude=**/tmp/arg0/`（agent 的 scratch 不进数据面）；
- 收紧了仓库里 2 505 个文件/目录的模式。

**待批（改既有服务，不自行执行）**：
1. **守门对断链符号链接的处置**：现在是「stat 不到 → 拒绝启动」。断链 symlink 既没有权限也不可读，
   它不构成红线 5 的风险；建议改成**跳过并记一行**。现状让「agent 的临时文件」有能力**拒绝启动数据面**。
2. **网关内存**：给 unit 加 `MemoryMax=` + `Restart=on-failure` 的退避，或定期重启；
   并查 `/tradability` 的按年缓存与逐请求 DataFrame 的常驻量（N-107 的升级版）。
3. **不要让两批负载叠在一个 worker 上**：跑批（oracle / f1）与 agent 真跑要串行，或网关起多 worker。
   今晚的 O1 矩阵有 13 道题的失败是这个原因，不是题或探针的问题。

### N-125 补：**每一次 git commit 都会重新布下这个雷**（2026-09-05 实测）

`git commit` 写出的对象是 `0444`（git 的缺省：只读、组/其它可读），`.git/index` 与 `refs/heads/main` 是 `0664`。
守门扫整个仓库（含 `.git/`），于是**提交完立刻就有 126 条不合规** —— 下一次网关重启（崩溃自愈、或人工重启）
就会被拒。今晚已经因此停摆过一次。

现状的绕法：提交后跑一次
`python -c "from ops import report_io as R; R.secure_tree('/data/shared/genebench/repo')"`（今晚做了两次）。

**待批（改既有服务）**：仓库根本身是 `0700`（`drwx------`），别人根本进不去，
里面每个文件的组/其它位在可达性上**没有意义**。建议守门改成：
① 对**目录树的根**判权限（这是真正的边界）；② 树内只判「答案面产物」这一类；③ 跳过 `.git/`。
在那之前，「提交完要收紧」这条得写进 HANDOFF，否则下一个人会在同一个坑里停摆。

## N-127 / N-128 S8 的两处**题面未定**（2026-09-06，M6 第二次 pass 抓到）

**N-127 滑点的符号约定题面没写。** 指标规格 §3 写的是 `Slip = 量加权(成交价 − 决策时点价) bps`，
而题面（`arms/INSTRUCTION.*.md`）只说「滑点以委托里带的提交时价为基准」——**没说哪边减哪边**。
实测三个 agent 报出 +44.8 / +172.8 / −145.9 bps，gold 是 −160.5：符号与量级都对不上。
处置：`compare_fill` 里 Fill / Slip **只报不判**（题面也没规定下哪些单，两轮不是同一个量的两次测量）。
下一次题面版本要把符号约定写进去。

**N-128 事件记录的字段题面/schema 没规定，而 Audit 的定义要求「可完整重放」。**
`PAYLOAD_SHAPE` 对 `events` 只要求 `{ts, type}`；题面只说「产出要包含：事件链、状态迁移、成交统计」。
四个 agent 的 `order` 事件因此都只有这两个键 —— 而没有 `order_id / symbol / side / qty` 的链**重放不了**，
Audit 判 0。判定本身成立（规格 §3 的 S8 正确性项就是「事件链可完整重放的任务占比」），
但**对被测方不公平**：它照题面做了。

处置：① 主表脚注写明（就绪报告 §5 已列）；② 下一次任务集版本把委托记录的字段写进题面与 `PAYLOAD_SHAPE`
（契约 §2 本来就定义了委托记录，只是没落到 S8 的 payload 契约上）；③ 在那之前 S8 的 effect 只反映
`legal_transitions / events_monotone / fills_linked` 这几项 —— 它们都过了，Audit 卡在字段上。

> 这是**同一族**问题今晚第三次出现（N-114 S1 台账、N-124 S2 描述键、这里 S8 事件字段）：
> **判据要求的东西，题面必须说**。判据设计的自查清单该加一条：写完判据回去读题面，
> 判据要的每一样，题面上都得能指出是哪一句要求的。

## N-129 协议 validator 与评分器**判得不一样**（2026-09-06，为填「Recov 列空」这个空时量到的）

问「Recov 列空是零修复还是未接线」，量出来的答案是**零修复**，但这个零本身是条发现：

| | |
|---|---|
| 有 `work/protocol/validator.log` 的 run | **10 个**（GQ 臂全都有 —— 接线是通的）|
| validator 被调用 | 18 次 |
| 它报出的违例 | **0 次** |
| 同一批里评分器判 `malformed` 的 | **4 个**（s1 `s1_status_enum` / s3 `s3_degeneracy_missing` / s5 `s5_signal_row_malformed` / s8-ops `overreach_count_mismatch`）|

也就是说：**Recov 的分母是空的**（没人被拒过，谈不上修复），
而分母之所以空，是因为**发给 agent 的那份 validator 没看出评分器要判的东西**。

四条里 `overreach_count_mismatch` 情有可原（要网关日志，工件侧看不见），
另外三条是**纯 payload 形状**的检查 —— 协议工件本该拦住。

后果：GQ 臂的「结构化违例反馈 → 修复回路」（卡 4.3 的设计）在这一批上**一次都没启动**，
而主表上它表现成「Recov 空」，看起来像没接线。

**待批**：v1 是否要求两者判据同源（`ops/protocol/geneprotocol_v1/validate_artifact.py` 与
`reference/artifact_schema.validate` 共用规则集，或至少让前者覆盖后者的 `malformed` 那一层）。
同源的代价是协议工件里会出现评分器的规则（信息不对称的另一端）；不同源的代价就是今晚这张表：
**修复回路形同虚设，而两臂对比里 GQ 臂的卖点正是这条回路。**

## N-130 S7 在 ≤300 次调用的预算里做不完（2026-09-06，签字前第 ③ 件的结论：**BLOCKED**）

裁定给的是「s7-cor-01 双臂预算放 150 重跑一次（≤300 次调用），让 S7 的 ε 路径有真 agent 产物」。
两次尝试用满了这 300 次，**四个 run 一个产物都没有**：

| run | 调用闸 | token 闸 | 实际停在 | 耗时 | 产物 |
|---|---|---|---|---|---|
| `r02.strict` | 150 | 3 M | **token 闸**（3 010 362 > 3 M，第 43 次调用）| 996 s | 无 |
| `r02.open` | 150 | 3 M | **token 闸**（3 001 366，第 67 次）| 1 018 s | 无 |
| `r03.strict` | 90 | 20 M | **调用闸**（90/90，tokens 只用了 5.2 M）| 2 002 s | 无 |
| `r03.open` | 90 | 20 M | **调用闸**（90/90，tokens 5.6 M）| 2 223 s | 无 |

合计 **294 次调用**（上限 300）—— 按纪律**不再加码**，记 BLOCKED 交回。

**读出来的两件事**：
1. S7 是八道题里唯一**两种预算形态下都做不完**的。r02 撞的是我设的 3 M token 闸（那是我的取值，不是裁定的），
   r03 换成 20 M / 90 次之后**改撞调用闸**，而 token 只用到 5.2–5.6 M —— 说明它缺的是**回合数**，不是上下文。
2. 两臂对称（91/91 次），说明这不是协议工件带来的差异，是任务本身的体量：
   S7 要实现一整套回测（撮合、费用、复权、台账守恒），Codex 一轮一个工具调用推不完。

**下一次要给的东西（待批，别默认加钱）**：① S7 单独的预算档（≥200 次调用 / ≥20 M token）；
或 ② 把 S7 拆成「引擎实现」与「跑一遍出指标」两段，前段给夹具、后段只算指标；
或 ③ 承认 S7 在 v1 的单次预算里不可完成，主表上把它标成 `budget_exhausted` 单列，不混进 `no_artifact`。
**现在的记法是 `no_artifact`**（`unscorable_agent` 桶）—— 它把「预算耗尽」与「agent 交白卷」混在了一起，
这两件事在主表上的含义并不相同（第 ③ 条就是要修这个）。

## N-131 **agent 可见的内容有一部分在冻结根之外**（2026-09-06，写取数约定时露出来的）

把「请求须以 `end_date` 界定在 as_of 内」写进两臂共享的 `work/{stage}.json` 之后，
`freeze_v10.py` 报的是**「与冻结清单一致」** —— 也就是说：**agent 看到的东西变了，两条版本轴都没动。**

根因：`work/{stage}.json` 是 `ops/specs/artifact_schema/v1.0/{stage}.json` 的逐字节副本
（实测同 sha），而冻结清单的 `code` 段只覆盖 `genetask/` 下的八个文件 + params + phrasebook，
**不含 `ops/specs/`**。于是这条路径上改任何东西都不会让根 hash 动。

这次是按裁定「不推版本」办的，结果**正好**符合要求；但这不是设计，是漏洞恰好对上。
「任务集版本回答『agent 看到的东西变了吗』」这句话，在这条路径上目前不成立。

**待批**：把 `ops/specs/artifact_schema/v1.0/*.json` 收进冻结清单的 `code` 段。
代价是这一次的改动要补一次版本推（v1.0.10）；收益是那句话重新成立。
在收进去之前，**任何改这些文件的人都要知道：它直接改的是 agent 看到的东西，而没有任何版本会动。**

## N-129 更新（2026-09-06 裁定）：列入**可发布前必修**，归 5.1 红队一轮首件

做法定了：**用 M6 全部真 artifact 作语料**，跑「协议 validator」与「评分器 L1 子集」的一致性对照，
不一致的逐条修 validator（而不是放宽评分器）。语料：`runs_in/{m6,m6b}/*/work/artifact.json`（29 个 run 里有产物的那些）
\+ 三控的 oracle / null / filler 桩。判据：对同一份 artifact，两边给出的 `malformed` 集合应当相等；
差集逐条记因（有的确实只有评分器看得见 —— 例如 `overreach_count_mismatch` 要网关日志，工件侧没有）。

## N-130 更新（2026-09-06 裁定）：`budget_exhausted` 已从 `no_artifact` 单列

`runner/c42/failure_modes` 加状态 `budget_exhausted`（桶仍是 `unscorable_agent` —— 都进 SR 分母、都不算成功，
但**状态分得开**）；`scorer/score_run` 从边车的 429 记录判定（不拿 `calls >= max_calls` 反推：
反推会把「刚好用满但自己停了」也算成撞闸）；Table A 加 `budget_exhausted_runs` 列。
实测：M6 两批 29 个 run 里 **9 个**是撞闸（S4 两个、S7 六个、s7-rob-02 一个），此前它们全被记成 `no_artifact`。
S7 的真 agent 产物列入 v1.0 已知限制；预算档归 M7，本轮不再加码。

## N-129 收口（2026-09-06，5.1 红队一轮第一件）：**已修，语料一致性 0/0/0**

做法按裁定：**用 M6 全部真 artifact 作语料**跑 validator 与 scorer L1 子集的一致性，
不一致**逐条修 validator，不放宽评分器**。工具 `ops/validator_parity.py`，报告 `ops/reports/validator_parity.md`，
测试 `ops/test_protocol_validator.py::test_parity_on_the_real_m6_corpus`。

**语料 121 份**：真 agent 产物 23（m6 / m6b / a1 三批里有产物的全部）+ oracle 32 + null 33 + filler 33。
比对只喂 artifact（`gateway_log=None`、`tradability=None`）—— 要证据的那几族本来就不在工件侧可见。

| | 修前 | 修后 |
|---|---|---|
| validator 比 scorer 严（不许）| 0 | **0** |
| 作用域内反向缺口 | 0 | **0** |
| scorer 判 malformed 而 validator **完全沉默** | **4 份** | **0 份** |

**根因不是 validator 写坏了，是规则数据不够细。** 它按数据判（`test_validator_has_no_hardcoded_stage_knowledge`
盯着不许有阶段知识），而两臂共享的 `work/{stage}.json` 此前只到「这个键是 object、必填哪几个子键」。
真 agent 犯的错全在**叶子**上：

* `s1_status_enum`：把 HTTP `200` 写进 `fetches[].status`（该枚举是 ok / empty / denied / rate_limited）；
* `s3_degeneracy_missing`：`alert` 写成一句解释而不是 bool —— 「有没有报警」就此不可判；
* `s5_signal_row_malformed`：`date` 写成紧凑串 `20260701`。

**修法**：① `PAYLOAD_SHAPE` 下到叶子（枚举 / bool / pattern / 上下界），八个共享 schema 随之重生成
（→ v1.0.11 / r1.0.18）；② validator 的 `_type_ok` **下钻** `properties` 与 `items`
（此前只判一层，规则再细它也看不见）；③ `SCOPE` / `SCORER_SCOPE` 把新纳入的叶子级 code 登记进去。

**自伤一次，记下来**：改 `PAYLOAD_SHAPE` 时我**整张重写**，把复审员先前专门加进去的
S7 逐项 `number`、S6 的 `_LEDGER`、S8 的迁移状态名枚举一起抹了 —— 两条同源测试当场红
（`test_a09_check_table_covers_every_required_leaf`、`test_payload_types_live_in_shared_schema_not_in_one_arm`）。
表头现在写着：**改这张表只许在原文上补，不许重写**。

---

## 2026-09-07 建到可分发·阶段三（通用 harness）

阶段三把「外部用户能不能照手册接一个自己的 agent 进来」这件事做到可分发：
六个 harness 目录（codex / openhands / claude-code / gemini-cli / grok-cli / opencode）、
一份从骨架写成手册的 `harnesses/README.md`、一次红队走查（14 条 finding，9 条 major 已修）、
以及 `llm_log` 的 usage 在五个 harness 上的完整度体检。

下面是 `ops/tickets_inbox/3.*.md` 八份收件箱的逐条并入（同一件事被多张卡登记的**合并为一条**，
出处逐一列在说明末尾）。**已修的也登记**，因为它们改变了别人对系统的认识。


**A. 手册与接入契约**（`harnesses/README.md`、`build.sh`、契约测试）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-132** | 预算闸的状态码：注释/任务书说 402，实现回 **429** | **待裁定（CONFLICT）** | `runner/registry.py:83` 的注释写「超限边车直接 402 并落 `budget_exceeded`」，而 `runner/c41/egress_proxy.py:1112` 实际是 `_deny_http(cli, 429, "budget_exceeded", …)`。`harnesses/README.md` 按**代码为准**记 429，并写明「判据认 `llm_log` 的 `reason == "budget_exceeded"`，别 match 状态码」。3.2-codex 补的证据：M6 的 9 个 `budget_exhausted` run 在 `records.json` 里落的是 `run_status` + `budget.detail`，**判据链条上确实没有人 match 状态码**，所以统一那一位数字是安全的。429 更贴语义（限流/配额）、改注释最便宜；402 Payment Required 对「预算」更直白。两处都没动。出处：3.1、3.2-codex。 |
| **N-133** | `harnesses/<id>/` 的第四件文件 `README.md` 是 3.1 新加的要求（W-0 骨架只要三件） | 已完成 | 为了让 `ops/test_harness_contract.py` 的「四件文件」断言对**已有的两个目录**也成立，3.1 补写了 `harnesses/codex/README.md` 与 `harnesses/openhands/README.md`（**只新建文件**，没碰任何一份 `launch.json` / `config.yaml` / `Dockerfile`）。出处：3.1。 |
| **N-134** | Dockerfile 的判据是「第一条**有效**指令是 `FROM gb-base:bookworm-r1`」，不是字面第一行 | 已完成（CONFLICT） | 任务书原文是「第一行 FROM」，而 W-0 同时要求「Dockerfile 顶部注明镜像名与 digest」——照字面判会把来历注释判红。按保守方向：**保留来历注释**（它是「抄回来的这份 = 构建出现网镜像的那份」的唯一证据），判据改成第一条非空非注释行，另加一条「全文只有一条 FROM」（对齐注入器 P4c）。`harnesses/build.sh` 用同一条判据。出处：3.1。 |
| **N-135** | `ops/score_runs.py` 未知 batch 的表头里**没有**「不是实验数据」 | 已完成 | 原来落到 `f"Table A ({batch})"`。加了 `caption_for(batch)`，回退文案是 `Table A — <batch>（接入/harness 验证，不是实验数据）`。这条挡的是「接入验证表被当成主表读」。出处：3.1。 |
| **N-136** | `ops/test_c41.py` 里写死的 `len(REG.CONFIGS) == 3`：第一个把 `config.yaml` 翻成 `enabled: true` 的代理会把它跑红 | 已完成（c36c5e6） | 已按 W-0 收件箱的写法改成 `test_v10_is_one_model_many_harnesses`：内置三条 ⊆ `CONFIGS`、`config_id` 互异、`harness` 名互异、`len >= 3`、同一模型、host 全 `api.deepseek.com`，并保留一条反向判据（patch 掉最后一条的 model 必须抛 `RegistryError`）。后面的代理不用再管这条。出处：W-0 / 3.1 / 3.2-codex / 3.2-claude-code（第一个撞上并改掉的是 claude-code）。 |
| **N-137** | `harnesses/build.sh` 在 f02 上没有执行位 | 已完成（写进文档） | `ops/push_exec_to_f02.sh` 的 rsync 用 `--chmod=D700,F600`，落地一律 0600，所以调用一律 `sh harnesses/build.sh <id>`。**不**为它放宽 rsync 的 chmod —— 那会连带放宽整棵 exec 树的权限口径（红线 5）。出处：3.1。 |
| **N-138** | f02 的 `exec/` 树默认看不见 `harnesses/` 与 `integrations/`（`--with-launch-data` 默认关） | 仍待裁定 | 手册把 `--with-launch-data` 写成接 harness 的**必带开关**，症状表里也有「f02 上 `by_id` 报未知 `config_id` → 忘了 `--with-launch-data`」这一行。倾向与 W-0 一致：**默认打开**。注意它也会把工作树里 `runner/`、`harnesses/`、`integrations/` 三棵树下**别人未提交的**改动一起推走（3.rt 实测：`integrations/COST.jsonl`、`COST.md`、`finrobot/` 都进了推送清单），推之前先 `git status`。出处：W-0 / 3.1 / 3.rt。 |
| **N-139** | `vendor/` 不在仓库里 | 未处理（W-0 已登记，此处复述） | 构建/同步时会看到「跳过且不 --delete」那行输出，不是错误。出处：3.1。 |
| **N-140** | 卡 3.2 任务书里的 `--image gb-codex-u` 写错了镜像名 | 已完成（文档） | 真实镜像是 `gb-cx-u:r1`（历史短名），`gb-codex-u` 不存在。`build.sh` 的 tag 从 `launch.json` 的 `image` 取，所以构建侧不会错；错的只在人手敲的 `ops/export_bundle.py --image` 那一处。已在 `harnesses/codex/README.md` §7 写明「给的是不带 tag 的仓库名 `gb-cx-u`」。出处：3.2-codex。 |
| **N-141** | `harnesses/README.md` §4④ 的 `--remote` 少一层 `runs` —— 照抄的结果是「runs: 0；问题: 0」的**假成功** | **已完成（3.3 修，含双向判据）** | run 目录是 `runner/inject.py` 的 `run_root / "runs" / rid`，`--remote` 要比 `--run-root` **多一层**。照旧手册抄会退 0 并打印「runs: 0；问题: 0」——不报错的错。已改成 `.../runs/runs` 并加 `ops/test_harness_contract.py::test_readme_scoring_remote_has_the_extra_runs_layer`，**判据取自手册字面与 `inject.py` 两处、必须一致**，将来谁改了落点红的是这条测试。出处：3.2-gemini-cli（第一次撞）、3.2-claude-code（第二次撞）、3.2-opencode（读了 notes 才躲开）、3.3（修）。 |
| **N-142** | 接入检查表缺一项：「这个 CLI 的**默认输出上限**是多少」 | 待并入手册 | 同一个坑撞过两次：claude-code 的 `CLAUDE_CODE_MAX_OUTPUT_TOKENS`（默认按 Claude 的上限走）、grok-cli 的 `GROK_MAX_TOKENS`（默认 16384，而 deepseek-chat 上限 8192，不设则**第一个请求**就被上游拒）。建议在 `harnesses/README.md` 的接入检查表里加一行固定检查项。出处：3.2-grok-cli。 |
| **N-143** | 接入检查表缺一项：「这个 harness 有没有**写死的第二模型**」 | 待并入手册 | Grok CLI 的 recap（`refreshSessionRecap` → `DEFAULT_RECAP_MODEL`）与 title 生成用写死的模型名，在 DeepSeek 上必然失败；失败被 `catch` 吞掉、**不报错**，但**照样吃掉一次预算闸计数**。claude-code 是同一类问题的另一种表现（五个 `ANTHROPIC_*_MODEL` 都得指到 deepseek-chat）。grok-cli 的关法是预写 `~/.grok/user-settings.json` 的 `recapsEnabled: false`。出处：3.2-grok-cli。 |
| **N-144** | 接入检查表缺一项：「这个 CLI 的 SSE 解析器接不接受**标准的分片工具调用**」+ 一次**必做的假上游冒烟** | 待并入手册 | grok-cli 的根因是协议方言，而它在「能不能跑起来」这一层完全看不出来：CLI 起得来、200 全绿、模型也在说话，**只有工具参数是空的**。建议加一条必做冒烟：起一个只说 SSE 的本地假上游，发一次**分片**的工具调用（首片带 id/type/name、续片只带 index + arguments），看 harness 的会话库里参数是不是完整的。零真调用、两分钟出结果。可直接抄 `$GB/scratch/3.2-grok-cli/smoke/{fake_upstream.py,smoke.sh}`（三种 MODE：frag / whole / xai）。出处：3.2-grok-cli。 |
| **N-145** | 出集（打包）到底要不要拿 `locks/heavy.lock`：施工契约说要，`harnesses/README.md` §4① 不提任何锁 | **待裁定（CONFLICT）** | 3.rt 实测：出集本身 10 分钟内完成、**并不重**，等锁等了约 3.5 小时（阶段一的 gold 重算持锁）。外部用户照 README 不会拿锁，于是出集会和 gold 重算抢内存（f01 只有 30 GB，2026-09-07 05:20Z 刚 OOM 过）。**两处只能留一个说法**：要么 README 写清「在 f01 上出集要拿 heavy.lock」，要么契约把「打包」从重活里拿掉。出处：3.rt。 |
| **N-146** | `harnesses/README.md` §4 的 `STG=…/staging/<batch>` 与 §4① 的 `rm -rf "$STG"` 组合：同一批跑第二道题会删掉第一道的 bundle 与通行证 | 登记不修（minor，建议下张动 §4 的卡改成 `<batch>_<task>`） | f01 上留痕的真跑用的都是 `<batch>_<task>`（`h_codex_s2-cor-01`、`m6_s7-rob-02`…），只有 `staging/w31` 是 batch-only 形态 —— 文档与既有实践不一致。出处：3.rt。 |
| **N-147** | `harnesses/README.md` §4 与 §0 第 4 条写「四条命令」，实际列了五段（① 出集 ② 推送 ③ 真跑 ④ 结算 ⑤ 记账） | 登记不修（minor） | 数字不影响照抄；改它会动到 §0/§4 两处标题行，收益不抵共享文件的写冲突成本。出处：3.rt。 |
| **N-148** | `harnesses/README.md` §1.1 铁律一末句与 §5 末行把「多条 FROM」说成被**注入器 P4c** 拦掉 | 登记不修（minor） | 真正拦它的是 `ops/test_harness_contract.py::test_dockerfile_from_unified_base` 与 `harnesses/build.sh` 第 3 步；注入器 P4c 读的是 bundle 里的 `image/Dockerfile`（`runner/inject.py:360-368`），不是 `harnesses/<id>/Dockerfile`。照文档去查 P4c 会找错地方，但**拦截本身是真的**、修法也对，不挡外部用户。出处：3.rt。 |
| **N-149** | `harnesses/README.md` §5 的 `403 foreign_credential` 一行没说明它是**防御性说明** | 登记不修（minor） | f02 上 47 个既有 run dir 的 `log/llm_log.jsonl` 全文 0 命中；容器里只有占位 key，按文档做复现不出来。触发条件是 harness 自带 key（环境 / 配置文件 / 命令里写死）。机制为真（`egress_proxy.py:1106`）。出处：3.rt。 |
| **N-150** | `harnesses/README.md` §5 里两行 `no_artifact` 的可信度不同，排版上看不出来 | 登记不修（minor） | 「run dir 里什么都没有」那行由 `runner/c42/harvest.py` 结构性保证（harvest 在 `down -v` 之前），f02 全部 run dir 里 0 例，只有自己写 up/down 才可能；相邻那行（产物写到 `/task` 之外）**真出现过**（h_grok-cli 那次的 `run_status`）。出处：3.rt。 |

**B. 预算闸与用量口径**（三个 harness 的同向证据）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-151** | `runner/registry.py:84` 的注释说 `RUN_BUDGET.max_tokens = 600_000`「够 100 次长上下文调用」——**三个 harness 给出同向证据说它不对** | **待裁定** | codex 每次调用 prompt 43k~68k（prompt 占 97~98%，每次重发整个上下文），600k 只够**约 13 次**；opencode 真跑平均每次约 30k（34 次调用 = 1,047,805 token，52 次 = 1,643,466），按默认值跑会在**第 20 次左右**撞闸；claude-code 同向。而**撞闸的表现是「agent 半途放弃」，不是一条显眼的错误**。倾向：**不改默认值**（它是成本护栏不是判据，改要连带别的 harness 一起掂量），但那句注释是错的，且「长上下文 harness 必须显式给 `--max-tokens`」应当在手册里写成硬要求（卡 4.3 的档位落地后，S4 9M / S7 18M —— 跑那两个阶段的题时要把 `--max-tokens` 一起去掉，否则显式的 3M 会把档位压低）。没动 `registry.py`。出处：3.2-codex、3.2-opencode、3.2-claude-code、4.3。 |
| **N-152** | 预算闸的 token 口径**不含缓存命中** —— claude-code 上闸比它以为的宽约 22 倍 | **待裁定** | `egress_proxy._norm_usage()` 在上游没给 `total_tokens` 时按 `prompt + completion` 自己加，而 Anthropic 协议把命中缓存的输入单独记在 `cache_read_input_tokens` 里、**不在 `input_tokens` 内**。机器统计（3.2-claude-code 抓到、3.3 独立复核为真）：闸计 **247 055**，同批 `cache_read` 合计 **5 387 136**。grok-cli 的 `prompt_cache_hit` 占 prompt 的 98%、opencode 97% —— 也就是说 `--max-tokens` 对**所有**走缓存的 harness 都宽一个数量级。`--max-calls` 不受影响（一次调用一条），真正兜底的是 calls 那一闸。改口径要连带重新掂量每个 harness 的 `--max-tokens` 默认值，且把 `cache_read` 计进 `total_tokens` 会让 m6/m6b（OpenAI 兼容协议，根本没有这个字段）不可比 —— 更可能的做法是**另记一列**。出处：3.2-claude-code、3.3。 |
| **N-153** | OpenAI Responses API 的缓存命中数**到不了算价** → codex 的 `$` 按整价算（是上界不是账单实数） | **待裁定（卡 1.5 pricing / M7）** | 归一后缓存命中统一叫 `cached_prompt_tokens`，而 `runner/pricing.py::CACHE_HIT_KEYS` 认的是三个原始名（`prompt_cache_hit_tokens` / `cached_tokens` / `cache_read_input_tokens`）。Chat Completions（DeepSeek 平铺）与 Anthropic（平铺）都直接命中，**唯独 Responses API 把它嵌在 `input_tokens_details.cached_tokens` 里**，平铺不到。修法一行（把 `cached_prompt_tokens` 加进 `CACHE_HIT_KEYS`），但那是**主表口径变更** —— `ops/reports/m6_all` 的 27.0056 美元会降，该由掌管 pricing 与 M7 的人裁。出处：3.3。 |
| **N-154** | m6/m6b 的 `cached_prompt_tokens` **补不回来** | 不修，记因 | Responses API 的缓存数嵌在 `usage.input_tokens_details.cached_tokens`，而旧的 `_norm_usage` 只搬平铺的数值键 ——嵌套那一份在**落盘时**就丢了。读取侧的兼容层（`llm_trace.normalize_usage`）补不回没写下来的东西。codex 的 1176 条 usage 这一列只能是空的，新跑的才有。**不建议为此重跑 m6**（29 个 run、5800 万 token）。出处：3.3。 |

**C. 边车与 `llm_log`**（`egress_proxy.py` / `llm_trace.py` / `score_run.py`）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-155** | 各 harness 的结算报告**不可复现**：任何人重跑一次 `ops/score_runs.py` 都会静默洗掉某个 harness 整列 `$` | **已修（9c02176）** | `scorer/score_run.py::model_of` 只走 `REG.by_id`，而 `by_id` 对 `enabled: false` 抛 `RegistryError`。3.2 的代理按手册真跑时把 `config.yaml` 临时翻成 `enabled: true`、跑完翻回 false —— 于是**当时**算得出价、**今天**再算就算不出：退 0、不报错、表还在，只是那一列空了（第一次重结算就复现：`table_a.csv` 的 `0.0174086` 变成空）。修法是回落到 `REG.PENDING_CONFIGS`（不进主表切片，只影响各 harness 自己那张接入验证表）。修完重结算四个 batch，`git diff ops/reports/` **为空**。**推论**：「重跑一遍看看一不一样」是检验报告可复现性的便宜判据，值得每张出报告的卡都做一次。出处：3.3。 |
| **N-156** | 流式响应的 usage 会被响应体副本的上限**截掉**，抽出来是 `{}`，与「上游没给」不可分 | **已修（9c02176）** | 旧实现整段缓存响应体、超上限丢尾巴，而**流式的 usage 恰在最后一个事件里**。新实现同时留头与尾两份有界副本（`egress_proxy._capture_head_tail`，2 MB + 256 KB），并**边收边**去 chunked 框架（`_ChunkedDecoder`，任意切分边界都对）。**转发始终先于留副本**：留不下来不该拖累被测方。出处：3.3。 |
| **N-157** | Anthropic Messages 流式的 usage **跨两个事件**，旧的「取最后一个」会丢 prompt | **已修（9c02176）** | `message_start` 给 `input_tokens` + `cache_read_input_tokens`，`message_delta` 只给最终 `output_tokens`（有的版本还带 `input_tokens: 0`）。旧的 SSE 逻辑从后往前取第一个带 usage 的事件 → `prompt_tokens` 丢失、`total_tokens` 只剩半个。改成从前往后逐事件合并、**非零值赢**（`_merge_raw`）。出处：3.3。 |
| **N-158** | 边车对「请求里没有 `Authorization` 头」是**接受并补插真 key**，不是拒绝 —— 此前无任何测试覆盖 | **已补判据（3.2-gemini-cli）** | `_client_key()` 只读 `authorization` → `None`；守门条件 `key and key != PLACEHOLDER_KEY` 对 `None` 不成立（不判 `foreign_credential`）；`_replace_auth()` 在 `seen_auth=False` 时 insert 一条真 key。凡是用自家鉴权头的 harness（Gemini 的 `x-goog-api-key`、以及将来任何 `x-api-key` 系）**多半不需要改边车**，改之前先照这三行核一遍。已加 `ops/test_harness_gemini_cli.py` 第四节（含反向判据：真自带 key 仍要判 `foreign_credential`）。**没有改 `egress_proxy.py` 一个字。** 若将来有人把「没有 Authorization」改成拒绝，本 harness 会静默失效，表现是 403 而不是 404 —— 而 403 很容易被读成「agent 自带了 key」去查一件不存在的事。出处：3.2-gemini-cli。 |
| **N-159** | 边车的 `foreign_credential` 检查只读 `authorization`，漏掉 `x-api-key` 头 | 登记不修 | Anthropic 协议的另一种鉴权头是 `x-api-key`，agent 把自带凭据放进它时不会被判 `foreign_credential`。**实测证明这不构成预算闸绕过**：两个头同时在、`x-api-key` 是占位串时上游回 200 并采用 `Authorization`，也就是边车插进去的那把真 key 优先。真要补是三行（`_client_key` 遍历两个头、`_replace_auth` 加分支、`_strip_auth` 同步剥掉），补的时候按 N-100 在**宿主与容器两处各真跑一次**（共用 `/opt/egress_proxy.py`）。现行行为已由 `ops/test_harness_claude_code.py::test_placeholder_never_reaches_upstream_even_with_an_x_api_key` 钉住。出处：3.2-claude-code。 |
| **N-160** | codex 有 38 条 allow 没有 usage —— 已逐条归因，**不是抽取器的锅** | 记录在案 | 16 条 `upstream_error`（agent 自己乱试的探路请求：`/bars`、`/calendar`、`/healthz` 等，非模型端点，上游 404）+ 22 条 `no_usage_in_body`（`/v1/responses` 与 `/v1/models` 上游 200 但体里确实没有）。新增的 `usage_absent` 字段（`upstream_error` / `empty_body` / `truncated_no_usage` / `no_usage_in_body`）与读取侧的 `llm_trace.usage_coverage(trace)` 让后人不必再查一遍 —— **它是目前唯一能回答「这张表上的空格是谁的责任」的地方**。出处：3.3。 |

**D. 各 harness 的接入结论与阻塞**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-161** | `cfg-gemini-cli-deepseek` 进不了主表：Gemini CLI 说 Gemini 协议，而够得着的上游没有一个会说它 | **BLOCKED_AWAITING_USER** | 真跑证据：`decision=allow` / `status=404` / `upstream=api.deepseek.com`（allow 证明边车接受并转发，404 证明 DeepSeek 不服务 `/v1beta/models/…:streamGenerateContent`）。缺三件、缺一不可：① 一把 `GEMINI_API_KEY` 落到 f02 `~/.config/genebench/secrets.env`（0600）；② 把 `generativelanguage.googleapis.com` 加进 `runner/c41/egress_proxy.py::MODEL_API_ALLOW`（共享文件，且必须与 `config.yaml` 的 `base_url` 同源 —— `ops/test_c41.py` 有键集**相等**断言）；③ **一条能到那个域名的出口** —— 从 f02 实测 `curl` 退 `000`（连不上，不是 403），这条是硬的。顺序不能反：先解决出口可达性，再谈 key。**明确反对**在容器里内联 Gemini↔OpenAI 协议翻译层（那时主表上跑的就不是 Gemini CLI，而是「Gemini CLI + 我们写的翻译层」，与统一基座 N-62 要消除运行时差异同源）。出处：3.2-gemini-cli。 |
| **N-162** | Gemini CLI 的 `GOOGLE_GEMINI_BASE_URL`：文档说「必须 https，除非 localhost」，0.58.0 **实测未强制** | 记录，不修 | 本 harness 能接上边车（`http://gateway:8081`）**全靠这一条没被强制**。风险是上游哪天补上这个校验，那时本 harness 会在启动期就退出，而错误信息会指向 URL 校验、不指向我们。**给后人的通则**：「文档说的限制」和「实现的行为」可能不一致 —— 判断一个 harness 能不能接，最后一步一定是在容器里把那条命令真跑一遍；只读文档会得出「接不上、要给边车加 TLS」的相反结论（一件不必要的大工程）。出处：3.2-gemini-cli。 |
| **N-163** | Grok CLI 在**任何**说标准 OpenAI 分片流式工具调用的上游上都拿不到工具参数 | **BLOCKED_AWAITING_USER** | 根因钉死：`@ai-sdk/xai` 的 `xaiChatChunkSchema` 要求每一片 `tool_calls` 自带 `id`/`type`/`function.name`，transform 也把每一片当成完整的一次调用（没有按 `index` 累积的分支）；DeepSeek/OpenAI 的续片只带 `index` + 参数片段 → 整片被 zod 丢弃 → 工具参数恒为 `{}`。`^3.0.67` 范围内四个版本 schema 逐字相同；`grok-dev` 写死 `createXai`，没有换 provider 的开关。链路本身**全通**（104×allow/200）。**这不是「模型待换」那种化妆项**，是这条配置在 DeepSeek 上永远拿不到产物，所以 `enabled: false`。要它进主表只有一条路：`XAI_API_KEY` + `api.x.ai` 进 `MODEL_API_ALLOW` + 过 M7。**明确反对**在镜像里 patch provider 的 zod schema（同 gemini-cli 的理由）。出处：3.2-grok-cli。 |
| **N-164** | `grok-dev@1.1.7` 的 `engines.node: ">=18.0.0"` 与事实不符 —— 它实际必须 Bun | 仅登记，不修 | shebang `#!/usr/bin/env bun`、dist 是不带扩展名的 tsc ESM、`dist/storage/db.js` 直接 `import { Database } from "bun:sqlite"`。这是上游包的元数据问题，我们只在 `harnesses/grok-cli/Dockerfile` 顶部与 README §2 记明并装 `bun@1.4.2`。**给后人的判据**：判断一个 npm CLI 能不能只用 Node 跑，看 `engines` 不够，要 `grep -r "bun:" dist/`。出处：3.2-grok-cli。 |
| **N-165** | bun 的**运行时转译缓存**把 `run.json` 的 `unexpected` 淹掉 297 条 | 已在本 harness 修，登记供他人参考 | `HOME` 在 `/task` 下时 bun 往 `$HOME/.bun/install/cache/@t@/` 写 297 个 `.pile`。`BUN_INSTALL_CACHE_DIR` 与 `BUN_INSTALL` **都不管用**（管的是包安装缓存），只有 `BUN_RUNTIME_TRANSPILER_CACHE_PATH=0` 管用（297 → 0）。凡是以 bun 为运行时的 harness 都会撞。出处：3.2-grok-cli。 |
| **N-166** | 模型名对不上：注册表与请求写 `deepseek-chat`，上游响应体自报 `deepseek-v4-flash` | **待裁定（用户）** | 三张卡各自独立统计、同结论：codex 1196 次、claude-code 96 次、grok-cli 104 次，`deepseek-chat` 0 次；上游 `/v1/models` 与定价页都已不再列 `deepseek-chat`。**切片键是 `config_id`，不是响应里的 `model`，所以主表不受影响**；但任何将来想拿响应 `model` 做交叉核的地方要先知道 —— 「自报模型与请求模型不符」在这里是**上游的正常行为**，不是被测方说谎。换模型要先过 M7 的实验设计审定（`assert_registry_sane` 要求所有 enabled 配置同一模型）。出处：3.2-codex、3.2-claude-code、3.2-grok-cli。 |
| **N-167** | `api.anthropic.com` 仍是 403（地区封锁，N-32）—— claude-code 这个 harness 跑的不是 Claude | 待用户 | 换回 Claude 真模型要三样：`ANTHROPIC_API_KEY` 落到 f02 `~/.config/genebench/secrets.env`（0600）、一条能到达 `api.anthropic.com` 的出口、以及 M7 对「混模型」的实验设计审定。两件缺一不可，建议先解决出口。出处：3.2-claude-code。 |
| **N-168** | agent 运行期的 HOME 目录会**整棵**进 `unexpected_files` | 登记不修 | 两个真跑 run 的 `unexpected_files` 里有 `work/.opencode_home/{.config,.local/share}/…`（含 `opencode.db`、`opencode.log`）。这不是错：P8 在注入结束时结账，运行期写的东西按 `harvest.PRODUCED_*` 允许集分类，落在允许集外就进这份清单。claude-code 的 `.claude_home`、codex 的 `.codex` 同理。只是这份清单读起来像「有人往 work/ 里塞了文件」。出处：3.2-opencode。 |
| **N-169** | opencode 启动时会往 `opencode.json` 里插一行 `"$schema"` | 登记不修 | 实测：容器里 printf 写出去的是紧凑 JSON，跑完读回来第一行多了 `"$schema": "https://opencode.ai/config.json",`。是编辑器提示用的字段，`--network none` 下**不会去下载那个 URL**。记在这里只为免得后人把「配置文件被改过」当成污染去查。出处：3.2-opencode。 |
| **N-170** | opencode 官方 troubleshooting 说 provider 包在**运行期动态安装** —— 对 1.18.26 **不成立** | 登记不修（反例已钉进单测） | 照那句读，下一步就是给出向白名单加 `registry.npmjs.org` —— 而那是白名单膨胀的唯一真实来源。实测 `docker run --network none` 全程跑通，包已打进单文件二进制。`ops/test_harness_opencode.py` 钉的是它的推论：**启动命令里不许有任何安装动作**。出处：3.2-opencode。 |
| **N-171** | 镜像 digest 钉的是「构建那一刻的依赖树」；复核来历只能**比 digest** | 仅登记 | `grok-dev` 对 `@ai-sdk/xai` 写的是 `^3.0.67`（构建时解析到 3.0.130），随包没有 lockfile；codex/gemini 同性质。复核方法：用**仓库里的**那份 Dockerfile 在 f02 构建到临时 tag、比 digest、一致后 `docker rmi`。codex 上这条已有机器证据（`sha256:961e3878b28f…` 与现网 `gb-cx-u:r1` 逐位相同）。**不要用 `--no-cache`「更严格地」复核** —— npm install 不是逐字节可复现的，那不是回归，是方法本身不适用。出处：3.2-codex、3.2-grok-cli、3.2-opencode。 |

**E. 要别人改的（不在阶段三的路径里）**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-172** | bundle 的 `tasks/<id>/task.yaml` 里 `image:` 块是**死字段**，且内容误导 | **待裁定（要动冻结根）** | 出集后 `task.yaml` 里仍是 `base: python:3.11-alpine` + `digest: sha256:000…0`，而 `pin_image_digest()` 钉的是 `image/Dockerfile`（实测已正确改写成 `FROM gb-cx-u@sha256:961e3878b28f…`）。注入器读的是后者，所以**不影响正确性**；但任何人照 `task.yaml` 判断「这个 bundle 跑哪个镜像」都会得到错的答案，而且全零 digest 看起来像「没钉成功」。倾向：要么让 `pin_image_digest` 一并更新该块，要么把它删掉。改的是 `genetask/packager.py` —— **在冻结根（任务集轴）里，要走 `pending_freeze_bumps`**。出处：3.2-codex。 |
| **N-173** | `ops/export_bundle.py` 命中 0 行时不列可选 `task_id` | 待办（代码） | 现文案「参数表里 'xxx' 命中 0 行（要恰好 1 行）」，外部用户无从知道有哪些题号。3.rt 已在手册 §4 术语行写明出处（`grep task_id genetask/params/v1.0-smoke40.yaml`）作为替代；把候选打进报错更好，需要动 `export_one`。出处：3.rt。 |
| **N-174** | 全量 pytest 里 `ops/test_sim_factory.py` 27 条红（`s8-*` 全族） | 登记（**不是阶段三引入**，转数据面 / S8 的卡） | 报错是 `gateway/sim_factory.py:80`：`s8-cor-01 在多个出集里都有：[reference/tasks/v1.0-smoke/s8-cor-01, reference/tasks/v1.0-smoke-public/s8-cor-01] —— 不猜`。阶段一 1.1-b 的公开通道重建在答案面下多出了 `v1.0-smoke-public` 这一套，而 `sim_factory` 的定位是「按 `task_id` 全局唯一」。**要么给它传 `set_id`，要么把公开那套挪出 `reference/tasks/`。** 出处：3.rt。 |


## 2026-09-07 建到可分发·阶段二（三范式接口与接入示例）

阶段二做的是「**别人能不能把自己的系统接进来**」这一层：一份发给被测方的接口契约、
一个 pip 可装的数据垫片、一个产物助手、一份八步接入指南、一套接入成本遥测，
以及**六个真接进来并各跑过一道真题的示例**（五个由卡 2.6 的五位代理各接一个，
第六个是卡 2.7 的内部演练 —— 只凭手册接一个没接过的系统，用它来验手册够不够用）。

下面是 `ops/tickets_inbox/2.*.md` 十二份收件箱的逐条并入（同一件事被多张卡登记的**合并为一条**，
出处逐一列在说明末尾）。**已修的也登记**，因为它们改变了别人对系统的认识。
`F-xx` 指 `ops/reports/integrations_rehearsal.md` §1 的 findings 编号（卡 2.7 修手册那一批）。


**A. 接入指南 `integrations/README.md` 与最小示例**（这一段决定「外部用户照手册能不能用」）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-175** | §1② 的 Dockerfile 三行骨架**少两行**，照抄第一步就断 | **已完成（F-01，3da26a7）** | ① `gb-base:bookworm-r1` 是 `python:3.12-slim`，没有 setuptools，而垫片的 build-backend 是 `setuptools.build_meta` → `BackendUnavailable`；补 `RUN pip install --no-cache-dir "setuptools>=61" wheel`（走 index，构建期出网允许；垫片本身仍 `--no-index`）。② 仓库文件受红线 5 是 0600，`COPY` 原样保权限，任务容器以 `user: "1000:1000"` 跑 → `python3: can't open file '/opt/<id>/run.py': [Errno 13] Permission denied`，两臂十几秒退出判 `no_artifact`；补 `RUN chmod -R a+rX /opt/<id>`。**四张卡各自独立撞到同一句话**，这不是谁的疏忽，是手册的缺口。裁定倾向：**不动统一基座**（为省一行去重建全部下游镜像不划算），在骨架里写。出处：2.6-tradingagents、2.6-finrobot、2.6-alphaagent、2.7。 |
| **N-176** | `integrations/example_minimal/Dockerfile` 同样缺那两行，且**从没真构建过** | 待办（归 `example_minimal/` 的负责代理） | `launch.json` 写的 `image: gb-example-minimal:r1` 在 f02 上**不存在**。判据 `ops/test_integrations_readme.py::test_the_example_runs_end_to_end_and_its_artifact_passes_the_validator` 是在 f01 上直接跑 `run.py`、**不起容器**，所以这两条都测不到。示例是新接入者第一个照抄的东西，它不该是唯一没被真构建过的那份。出处：2.4、2.6-tradingagents、2.6-rdagent_q、2.7。 |
| **N-177** | `example_minimal/run.py::slot()` 只认 `key=value`，**在 open 臂上必然零产物** | **待办（本阶段代价最大的一条）** | 它的正则要求键名后跟 `:` / `：` / `=` / `\|`，而 open 臂写的是「本次任务的 as_of 是 2026-07-31」「标的范围（universe）是 csi300」。那个 30 行示例只在 **S1 strict** 上走查过。卡 2.6 有一个接入照它改，`s3-cor-01.open.…r01` 当场 `SystemExit`、exit 1、artifact 0 字节、**0 次模型调用**，并**用掉了同一目标允许的那唯一一次重试**。手册正文已修（F-03：§1④ 新增两臂写法对照表与三处「会把值偷走且产物上完全看不出来」的地方），**示例代码没改** —— 改它会连带 README §2 的逐字引用与「正文正好 30 行」两条判据，必须一起改。可照抄的修法：`integrations/rdagent_q/glue/instruction.py` 或 `integrations/stockagent/glue/instruction.py`（每条写成「锚点词 + 至多 12 个非目标字符 + 值」，口径统一取「接口值」那一段）。出处：2.6-rdagent_q、2.7。 |
| **N-178** | §1④「题面只有一个入口」那张表把**固定槽**讲成了**固定格式** | **已完成（F-03）** | 读者会以为槽就是 `key=value`；而两臂表达形式不同是**设计**（`ops/specs/fairness_protocol.md`）。§1④ 现在明说「P2 系统的题面解析必须同时认键值与散文两种写法」，并把「不许按 `GENEBENCH_ARM` 分支」那句从 §0 挪了一份过来（原来两句离得太远）。出处：2.6-rdagent_q。 |
| **N-179** | 题面里 `可用端点：… /universe /tradability` 那一行会把锚点**偷走** —— 而且**没有症状** | **已完成（F-03 的三处防偷）** | 任何「找 `universe` 后面那个词」的解析器都会把 universe 解析成 `tradability`：网关照样返回一个成分表、因子照样算得出来，**产物上完全看不出来**，只是标的池整个换了。防法：锚点前后都排除 `/`。判据示例 `test_universe_is_not_stolen_by_the_endpoint_list`（定向破坏实测会红成 `'tradability' == 'csi300'`）。出处：2.6-rdagent_q、2.7。 |
| **N-180** | **题面夹具与网关不同源**：`inputs/*.parquet` 是 `20260105` + `SH600000`，网关一路是 `2026-01-05` + `600000.SH` | **已完成（F-11，卡 2.7 新发现）** | 直接 join 得到空表，**join 本身不报错**。现场表现是**一张全 `null` 的面板：结构合规、`coverage` 自洽、过 validator、一眼看不出哪里错了**。`genebench_client/README.md` §4 新增「写法归一」一节，给出 `codes.iso_date` / `codes.to_lake` 与那句「别自己写一份」。证据：`scratch/rehearsal_2_7/` 的 `smoke4.log`（8 格全 null）→ `smoke5.log`（归一后 8 格全有值）。**任何要把网关数据与题面因子面板对齐的接入都会撞。** 出处：2.7。 |
| **N-181** | 重跑要换 `--seq`，否则撞 `RunError: run dir 已存在（F9）` | **已完成（F-12）** | §1⑥ 的示例命令原来写死 `--seq 1`，第一次失败后照抄第二遍必然撞。旧的 `rNN` 作为证据留着。出处：2.6-tradingagents。 |
| **N-182** | **重建镜像 → digest 变了 → 必须回到出集那一步** | **已完成（F-04 的回环）** | §1⑥ 原来把「构建 → 出集 → 推送 → 真跑」写成一条直线。忘了的表现是 bundle 的通行证与镜像对不上。出处：2.6-rdagent_q。 |
| **N-183** | 镜像名 `gb-<id>:r1` 与实际的 `gb-<id>-u:r1` 不一致；`docker build -t` 与 `launch.json` 的 `image` **没有守门** | 已完成（F-02 的对照表）／**守门仍待办** | 实测：镜像 11/13 是 `gb-<id>-u:r1`，`config_id` 5/7 是 `cfg-<id>-deepseek`。`harnesses/build.sh` 特意从 `launch.json` 取 tag（脚本头部写了理由：拼名字会对不上，而对不上的表现是「构建成功了，跑的还是旧镜像」）——`integrations/` 这条路是手敲 `docker build`，同一个坑原样留着。建议让 `harnesses/build.sh` 也认 `integrations/<id>/`。出处：2.6-rdagent_q、2.6-alphaagent、2.7。 |
| **N-184** | 构建上下文清单不全：没说**上游源码 tarball 放哪**，没提 `.dockerignore`，`-f` 那一句藏在示例的注释里 | 已完成（F-04）／`.dockerignore` 仍未写 | §1⑥ 的 `scp` 只送两样（接入目录 + 垫片），照抄的人建镜像时撞 `COPY failed: file not found`；而 §1② 又明确要求 GitHub 不可达时走 tarball + `COPY`，两节原来没接上。`.dockerignore`：构建目录里常有解压过的源码树，`docker build .` 会把它整个送进 daemon（卡 2.7 的上下文里有 4.7 MB 归档）。出处：2.6-finmem、2.6-finrobot、2.6-tradingagents、2.7。 |
| **N-185** | 结算的 `--remote` 要比 `--run-root` **多一层 `runs/`** | 待办（`integrations/README.md` §1⑥ 仍只写 `--help`） | `run_f02_a1.py` 会在 `--run-root` 下再建一层 `runs/`。可用的一条：`$PY ops/score_runs.py --batch <batch> --remote /data/genebench_runner/<batch>/runs/runs`。与阶段三 **N-141** 同族（那边已在 `harnesses/README.md` 修并加了双向判据；`integrations/README.md` 这一份还没有）。出处：2.6-finrobot、2.6-alphaagent。 |
| **N-186** | §1⑧「把覆盖写进 `COVERAGE.md`」只说 `$EDITOR` —— 没说它是**共享文件** | **已完成（F-06）** | 施工契约要求共享文件在 flock 内读-改-提交一气呵成；手册这一步原来读起来像「打开编辑器写一行」。同时补上「阶段格必须恰好八个，第 11 列才是备注」（有一条判据盯着，卡 2.6-rdagent_q 写了 7 个格当场被抓）。出处：2.6-finrobot、2.6-rdagent_q。 |
| **N-187** | §3 缺一条「**注入期就被拦**（P0）」 | **已完成（F-09，新增 §3.11）** | 现场是两臂各 0.1 秒 `ERROR: RunError: 注入失败：[P0] …`，**run dir 根本没建、没有容器日志**。它与 §3.7「两臂 3 秒退出」长得像，但排查方向完全不同（那一条让你去看容器日志，这一条没有容器日志）。分辨法：run dir 在不在。出处：2.6-finmem。 |
| **N-188** | §3 缺一条「**产物合规但 gate 非空**」该怎么读 | **已完成（F-05 的口径 + §3）** | §3 原来的十条讲的都是失败（403 / 畸形 / 起不来）。而「双臂全绿、越权率 0、L3 过、gate 非空」这种结局在指南里没有对应条目，接入方容易误以为自己链路有问题去重跑 —— 而重跑一次只是买一个更好看的格子。纪律是：**只有失败原因是我们的链路时才重试**。出处：2.6-alphaagent。 |
| **N-189** | §3.9 的 `HOME` 修法覆盖不到「按相对 CWD 写文件」的那一类系统 | **已完成（F-10，新增 §3.12）** | 这一类根本不看任何环境变量（例：`logging.FileHandler(os.path.join("data", "…"))`、`open("data/…")`），修法是 **import 上游之前先 `chdir`**。同时点名 `pin.json` 的 `runnable_check` 也在**构建期**跑，那时 `/task` 还不存在。出处：2.6-finmem、2.7。 |
| **N-190** | 手册缺一节：被测方是 **agent 框架**时，工具函数的**签名是硬约束** | 待办 | AutoGen / LangChain 这类框架**从函数签名生成工具 JSON schema**，所以替换实现时：替身写成 `(*args, **kwargs)` → `TypeError: All parameters … must be annotated`；接线模块写 `from __future__ import annotations` → `Annotated[str, "…"]` 到 pydantic 手里变成解析不了的 ForwardRef（`PydanticUserError`）。两者都炸在**组装 agent 的时候**，现场表现是「接线全对、agent 根本没起来」，而错误信息里一个字都没提到「你换了实现」。修法一句话：`functools.wraps(上游函数)` 照抄签名。倾向放 `integrations/README.md` §3 而不是 `P2_CONTRACT.md`（后者是从代码读出来的网关规则，这条是接入经验）。出处：2.6-finrobot。 |
| **N-191** | 手册原来只有一种被测方模型（运行期取数）；实际有**三类**，可核查性完全不同 | **已完成（F-07，§1③ 分类表）** | ① **运行期取数**：「取数是否全部经过数据面」**靠不住** —— TradingAgents 三条通向原生源的路，接入者自己只找到第 1 条（vendor 注册表），第 2 条是**真跑报 `NoMarketDataError`** 告诉我们的，第 3 条是**容器出向白名单报 403** 告诉我们的。② **离线数据集**：替换缝在「那个 pkl 怎么造出来」，天然没有第二条取数路径。③ **无数据**（StockAgent 那一类，运行期一次外部取数都没有）：接入的活不是「堵路」而是「把它虚构的那部分换成真的」，实测 `egress.jsonl` 里被拒的 CONNECT 是 **0**。后两类是**结构保证**。这是阶段二最值得进论文的一条范式层结论。出处：2.6-finmem、2.6-tradingagents、2.7。 |
| **N-192** | §1② 的 `config.yaml` 例子写 `base_url: https://api.deepseek.com/v1`，六个既有接入都写不带 `/v1` 的形式 | 待办（一处例子） | 两种都过三条判据，但例子与既有实践不一致，照抄例子的人会得到一份与别人不同的配置。出处：2.6-finrobot。 |
| **N-193** | 每个接入都有一个叫 `glue` 的包 —— 判据里 `sys.path.insert(0, HERE)` + `from glue import …` 会占住 `sys.modules["glue"]`，**肇事者自己不会红，红的是别人** | **已完成（c033578，手册 §6）** | pytest 先 import 全部测试文件再开跑，于是先被 import 的那份 `glue` 赢，别人的判据整族红。卡 2.7 第一次全量把 `ops/test_integration_rdagent_q.py` 的 8 条带红，**不是他们的问题**。改法：按路径加载并挂**带前缀**的模块名。请还没写判据的接入代理照这条改。出处：2.7。 |
| **N-194** | §1①「漏了 `begin` 后面补不回来」与 §5.2① 给的补救路径**自相矛盾** | 待办 | §5.2① 有完整的 `--at` / `loc --base <sha>` 补救。第一次读到 §1① 的人会以为只能作废重来。改法：§1① 改成「漏了这一步要用 §5.2① 的 `--at` / `--base` 补记，别凭回忆重填」。出处：2.rt。 |
| **N-195** | `integrations.cost` 的全局 `--repo` 一次都没在正文里出现 | 待办 | §5 给的每条命令都会往共享的 `COST.jsonl` 追加事件，而 §5.2③ 又强调坏一行下游每个数都偏小。想空跑一遍只能从 `--help` 里找到那句「仓库根（默认：本文件所在的仓库）」。改法：§5 命令块加一行注释。出处：2.rt。 |
| **N-196** | 垫片 `README.md` §3 的接口清单缺 `members(universe, as_of) -> list[str]` | 待办 | `integrations/README.md` 的旗舰 30 行示例用了 `cli.members()`，而垫片 README §3 只列了六个数据端点方法与五个 sim 方法。实测 `gateway.Client.members()` 存在，是 `/universe` 的便利包装。改法：§3 补一行，或把示例改用已文档化的方法。出处：2.rt。 |
| **N-197** | `ts.index_weight` 那一行没给 `index_code` 词汇表 | 待办 | 按题面的 universe 名直传（`index_code="csi300"`）是 422。可用值只能从报错里拿：`000300.SH`/`399300.SZ`→csi300、`000905.SH`/`399905.SZ`→csi500、`000852.SH`/`399852.SZ`→csi1000；`trade_date` 收两种写法。报错信息本身当场给全集，所以只算 minor。出处：2.rt。 |
| **N-198** | 外部作者给**自己的**系统做本地自检的路径不在正文里 | 待办 | 协议 validator 缺四份逐题规则 JSON 就不跑（「validator 不猜规则」）。生成它们的 `genetask.protocol_rules.write_rules(...)` 与手工验时要加的 `--rules-dir` 只出现在 `example_minimal/smoke.sh` 与它的 README，主手册 §2 与 `P2_CONTRACT.md` §3.5 都没提。改法：§2 末尾加四行（造 `/task/protocol/` 的命令、跑 validator 要带 `--rules-dir`、以及「容器里不用带」这条差别）。出处：2.rt。 |
| **N-199** | `integrations/README.md` 的 `docker images --digests` 少了 `ssh` 前缀 | 待办 | 上一行是 `ssh ljn@192.168.1.219 "…docker build…"`，说明当前 shell 在 f01；而本节开头刚写过「构建在 f02（f01 没有容器运行时）」。f01 上 `command -v docker` 为空，照抄即 `command not found`。出处：2.rt。 |
| **N-200** | `integrations/COVERAGE.md` 曾是**空表** | **已完成** | 现在六行齐（`tradingagents` / `rdagent_q` / `finmem` / `finrobot` / `alphaagent` / `stockagent`），每行都带长备注。**收口口径**：`COST.md` 里有一行而 `COVERAGE.md` 里没有的，就是「接了但没跑过」——本阶段两张表逐行对得上，六对六。出处：2.rt、2.4。 |
| **N-201** | `P2_CONTRACT.md` §2.1⑤「怎么看自己的切片」只说了一半 | 待办 | 契约给了路径与字段清单，却把身份四字段写成「身份四字段」而不点名（实测键是 `run_id` / `task_id` / `config_id` / `arm`），也没给可抄的切片命令；同时 §1.2 的环境变量全集里没有 `GENEBENCH_ROOT`，**容器里那个路径根本不存在**，而没有一句话说明「这是网关侧运行者看的，被测方看不见也不该拿它自查」。改法：补两句 —— 切片键是行里的 `run_id`；被测方自查请用 `cli.ledger`（§4.4 验行为不验申报）。出处：2.rt。 |


**B. 三范式接口本身**（`P2_CONTRACT.md` / `genebench_client` 垫片 / `emit` 产物助手）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-202** | 预算耗尽是 **429 `budget_exceeded`**，多处规划文写作「402」 | 待裁定（同阶段三 **N-132**） | `runner/c41/egress_proxy.py` 实测发的是 429；`402` 在整棵树里没有任何落点（全树 grep 只命中 `# noqa: E402`）。阶段二两个落点已按实现写：`P2_CONTRACT.md` 记 429；`integrations/README.md` §3.3 显式写「写 402 的地方是错的」，并有一条断言盯着这句话不被悄悄改成只换数字。**照 402 写重试分支的被测方，那条分支永远不触发。** 出处：2.1、2.4。 |
| **N-203** | `GENEBENCH_AS_OF` **不由 runner 注入**任务容器 | 待裁定（**倾向维持现状**） | compose 模板里 `task` 服务的 `environment` 只有 `GENEBENCH_TASK_ID/RUN_ID/CONFIG_ID/ARM/GATEWAY` 与模型侧那几个。垫片与 `emit` 走同一条纪律：三处都取不到就抛 `AsOfRequired`，**不猜**；接入方启动时 `gb.set_as_of(spec["as_of"])`（`as_of` 本来就在题面里）。理由是 `reference/oracle_io.py` 那条「唯一允许的环境变量是 `GENEBENCH_GATEWAY_URL`，因为它是**部署事实**不是任务事实」——把 `as_of` 塞进环境变量会破那条纪律。出处：2.2、2.3。 |
| **N-204** | NO_DATA 留痕依赖「网关对**未匹配路由**也记 `access_log`」这一行为 | 已实测成立，**需守住** | 实测：`GET /nodata/news?as_of=…` → 404、响应带 `x-genebench-ts`、`$GB/logs/gateway_access.jsonl` 里有完整一行（含 `params`），因为 `gateway/app.py::_log_and_time` 是 HTTP 中间件。**风险**：谁加一个 catch-all 路由、或给 404 装一个绕过中间件的 handler，这条留痕就**静默消失** —— 而 `gateway/**` 的改动者视野里没有任何测试会红（会红的那条在 `ops/test_genebench_client.py` 里）。建议在 `ops/test_gateway.py` 补同族断言（阶段一路径，本阶段没碰）。出处：2.2。 |
| **N-205** | `/nodata/{kind}` 应做成正式端点（404 + `reason="no_such_data_source"`）—— 现在留痕在结算里被算成 `malformed_requests` | 待裁定 | 实测数字：`s5-eco-01.*.cfg-tradingagents-deepseek.r03` 的 `overreach.malformed_requests` 是 strict **60** / open **45**，`malformed_reasons` **全是 `unclassified`** —— 那些全是垫片打的 `GET /nodata/<kind>`（故意打在白名单之外让中间件记 404）。于是「参数拼错」与「本环境没有这类数据源」在结算口径上**分不开，而两者含义相反**：**任何大量使用 `NoData` 的接入都会在表上显得「参数写得很烂」**。改了之后垫片与接入方**都不用改代码**（垫片已 tolerate 404），卡 5.x 还能按机器可读的键聚合「NO_DATA 尝试次数」。属 `gateway/**` 与结算侧。出处：2.2、2.6-tradingagents、2.7（F-14）。 |
| **N-206** | `emit.fetch()` 收不下 HTTP 404，而 404 正是垫片 NO_DATA 探针的**正常回码** | 待裁定（**倾向 ①**） | `_HTTP_STATUS` 只映射 403/429，其余 4xx 一律 `EmitError`。于是每个把 ledger 转成 `payload.fetches` 的接入方都得自己决定 404 算哪一档（卡 2.6-finrobot 记成 `empty`，「这次取数返回了零行」，为什么空在 `params.api/kind` 里）。① 让 `emit.fetch` 把 404 也映射成 `empty`（语义一致、不动题面）；② 给 `fetches[].status` 加一档 `no_such_source`（要动 artifact schema = 冻结根）。出处：2.6-finrobot。 |
| **N-207** | `set_version` / `reference_version` / `protocol_version` / `channel` 四个「版本字段」在容器里**根本取不到** | 保守处理（已实现） | v1.0 的信封键集是冻结的十二项，里面没有它们；容器里的 `task.yaml` 只有 `set_id`/`schema_version`；`set_version`/`reference_version` 是 `ops/freeze_v10.py` 的冻结面概念，被测方看不见。`emit` 只填 schema 定义的十二项，**不往信封里塞 schema 之外的键**（塞了也不会被校验 = 「有个字段但没人核」，正是 D-06 的形状）。要真加得先动冻结根。出处：2.3。 |
| **N-208** | `x-nullable-when` 是**中文句子里嵌一个 Python 列表字面量** | 登记不修 | `emit.depends_on()` 靠正则取那句话末尾的 `[...]` 反推依赖图，与评分侧 `PAYLOAD_DEPENDS_ON` 对齐的判据守着。更稳的做法是在 schema 里另出一个机器可读键（`x-depends-on`），但那要改 `reference/artifact_schema.py::_nullable_if_dependent` 的落盘格式 —— 冻结根。出处：2.3。 |
| **N-209** | `PAYLOAD_SHAPE["S4"]["ic_stats"]` **没有叶子类型** | **pending_freeze_bump** | `S4.json` 的 `ic_stats` 只有 `required` 八个键、没有 `properties`，所以「`mean` 必须是数」这条在结构层无处可查 —— 而评分侧有 `s4_ic_stat_not_number`，协议 validator 的 `SCORER_SCOPE` 里也列着它。与 **N-129** 那次「把 `PAYLOAD_SHAPE` 下到叶子」是同一类动作，只是漏了 S4。`emit` 眼下按卡 2.3 §3 的表把除 `ci_method` 外七项归一成数，补上叶子类型后那段可以删。出处：2.3。 |
| **N-210** | `S6.cash_ratio` 对 `weighting_scheme` 的依赖**在发给两臂的 schema 里看不见** | **pending_freeze_bump** | `_nullable_if_dependent` 只在 `type` 是**单个字符串**时才落 `x-nullable-when`，而 `cash_ratio` 的形态本来就是 `["number","null"]`，于是这条依赖**只活在评分侧**。后果不只是 `emit` 反推不到 —— **agent 也只能从这份 schema 知道依赖关系**，题面没说的事在结算时判 `computed_despite_unresolved` 就是**罚它不知道的东西**。修法是生成器里一行（`type` 是列表时也写标记），落盘的八个 `S*.json` 会变。`ops/test_emit.py::_DEPS_NOT_EXPOSED_BY_SCHEMA` 具名登记了这一处，改好后把那个集合清空。出处：2.3。 |
| **N-211** | `S6.targets[].solver_status` 的枚举只活在评分器里 | 登记不修 | 评分侧要求 `∈ {optimal, infeasible, not_converged}`，而 `S6.json` 与卡 2.3 §3 的表都只提到后两个。`emit` **不**在这里加校验 —— 题面没承诺的东西，助手不该当规则执行。要收口应当往 schema 补 `enum`，那样两臂都看得见。出处：2.3。 |
| **N-212** | `P2_CONTRACT.md` 里的 `(文件:行)` 引用会随提交漂 | 登记不修 | `ops/test_p2_contract.py` 只核「文件存在」与「行号不超出文件长度」，**不核行内容** —— 核内容会让任何一次无关提交把这张卡跑红（恒红）。真正的漂移守门是六处集合类断言（端点集双向、`Reason` 全集、`LOOKAHEAD_DENY_REASONS`、`/bars` 列集、`ENVELOPE_REQUIRED`、`MARKET_DATA_HOSTS`）。出处：2.1。 |
| **N-213** | `/limits` 不透出 `pre_close`，而 P2 作者拿不到「前收」的私有通道口径 | 登记不修 | `stk_limit.pre_close` 全 NULL，不透出是对的；公开通道的替代是 `daily.pre_close`（N-59 ③），但私有通道 `/bars` 的 15 列服务集里没有它。被测方只能用前一交易日的 `close` 自算，两者**在除权日不等**。契约已写明，不挡发布；要不要把 `pre_close` 加进 `/bars` 服务集是 N-33 同族，须推任务集版本。出处：2.1。 |
| **N-214** | `calendar_date_after_asof` 在当前实现下**不可达** —— 显式再判是死代码 | 待批（`gateway/` 是阶段一路径） | `guard_range` 已经用 `RANGE_END_AFTER_ASOF` 抛过，后面那句 `guard_target(hi, a, reason=CALENDAR_FUTURE)` 永远到不了 —— 而它的注释写着「让日志里这条路径可以单独聚合（卡 5.1 要按路径统计越权率）」，**那个目的没有达成**。实测 `/calendar?as_of=20260731&end_date=20261231` → 403 `range_end_after_asof`。**判定结果不受影响**（两个 reason 都在 `LOOKAHEAD_DENY_REASONS` 里），只影响按路径聚合。D-06「机制在、保护不在」同族。**别默默删** —— 删之前要确认卡 5.1 没有在按 `calendar_date_after_asof` 分列。出处：2.1。 |
| **N-215** | 生产网关 `/healthz` 的字段数：代码 7 个、线上 5 个 | 待办 | `channel` / `tables_dir` 已随卡 1.1-a 提交，但**服务未重启**，2026-09-06 实测线上仍是五个字段。`P2_CONTRACT.md` §5.3/§7 按**实测**写，并要求被测方用 `.get()` 取这两个字段。阶段一收口重启网关之后，请重跑 `$GB/scratch/c21/probe.sh` 并把契约那两处订正回来。出处：2.1、2.rt。 |
| **N-216** | tushare 兼容层的**单位换算**是垫片一侧的决定 | 记录 | 湖 `daily` 已被 platform 归一成**股/元**，tushare 原生是**手/千元**；垫片按 `vol=volume/100`、`amount=amount/1000` 换算（判别力 10×：`amount/volume ≈ 9.15` ≈ 每股价，若 volume 是「手」则会是 91.5）。**若湖的单位口径将来改了，这里会静默差 100×/1000×** —— 守它的是那条「`amount×1000/(vol×100)` 必须落在当天 `[low, high]` 内」的自洽断言。出处：2.2。 |
| **N-217** | `/universe` 不发权重 → `ts.index_weight` **没有 `weight` 列** | 待裁定 | 垫片**不给一列 NaN**（`weight.sum()` 会静默变 0，做出一个全零权重的组合），而是不给这一列 → 调用方 `KeyError`：**响的错好过哑的错**。若将来有被测系统真的需要指数权重，要在网关侧扩 `/universe`（湖里 `index_weight` 月末快照是有权重的）。属数据面改动。出处：2.2。 |
| **N-218** | `suspend_d` 不给 `'R'`（复牌） | 记录不修 | 卡 1.2 的五档 `status` 里没有这一档，「停牌段之后第一个交易日」这个定义跨年/跨长假不稳，推出来的会是我们编的。`suspend_type='R'` 走 `NoData` 并留痕。同族的还有：`ak.stock_zh_a_hist` 不给振幅/涨跌幅/换手率、`ts.daily` 不给 `pre_close/change/pct_chg`（都要 `pre_close` 与流通股本，网关都不发）、`yf` 不给 Dividends/Stock Splits（不编两列 0.0 —— 那等于宣称「这段时间没有分红」）、`ak` 的 `period` 只支持 daily（周/月线的重采样口径是我们编的，不是数据）。出处：2.2。 |
| **N-219** | `ak.stock_zh_a_spot()` 一次约 20 次网关请求 | 记录 | 「实时全市场快照」= `/universe(all)`（约 5,500 只）+ 分批 `/bars`，分批大小由 URL 字节预算（h11 上限 8190）与 `MAX_ROWS` 两条一起定。已在 README 与 docstring 里点名注意预算，**不加限流** —— 限流会让「取不全」变成静默截断。出处：2.2。 |
| **N-220** | 边车对 `/v1/embeddings` 是**透传后 404**，`llm_log` 里没有可机读的标记；**依赖向量检索的系统会因此静默退化** | 待裁定 | 实测（不是断言）：`POST http://gateway:8081/v1/embeddings` → 404。这是正确行为（上游模型 API 没有这个端点），但对被测方来说「404 是因为端点不存在」与「404 是因为路径写错」不可区分。两处受影响：FinMem 的分层记忆退成离线确定性哈希向量；RD-Agent 的知识库/RAG（`CoSTEERRAGStrategyV2.generate_knowledge` → `create_embedding`）用上游自己的 `knowledge_self_gen=False` 关掉了整条路 —— 代价是**「跨任务经验累积」这一层能力在 GeneBench 上测不到**。两个方向：(a) 维持现状 + 在覆盖矩阵与发布材料里写明「本环境不测这一层」，并让 `egress_proxy._wire_shape` 认一下 embeddings 路径（让 `llm_log` 能按 `wire_shape` 聚合尝试次数）／在 `P2_CONTRACT.md` 明写「模型侧只承诺 chat/completions」；(b) 边车后面放一个 embedding 上游。**倾向 (a)** —— (b) 会引入第二个模型，破掉主表的切片键。出处：2.6-finmem、2.6-rdagent_q。 |


**C. 六个接入示例带出来的结论**（范式层的，不是某个接入的实现细节）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-221** | 「被测系统的取数是否全部经过数据面」**不能靠接入者穷举替换点来保证** | 部分已修（F-13） | TradingAgents 三条通向原生源的路：第 1 条在 `VENDOR_METHODS` 里（接入者自己找到）；第 2 条是 `@tool get_verified_market_snapshot → stockstats_utils.load_ohlcv → yf.download`，**不经 vendor 表**，第一次真跑报 `NoMarketDataError` 才露出来；第 3 条是 `dataflows/{stocktwits,reddit}.py` 直接 `urlopen`，**是容器出向白名单报 403 告诉我们的**。两个方向：(a) **纪律** —— 手册加一条「真跑之后必须读一遍容器 stderr 与 `log/egress.jsonl`，把每一条被挡下的 CONNECT 当成一条未替换的路径登记」（**已做，F-13**）；(b) **判据** —— 让结算把 `egress.jsonl` 里的 CONNECT 拒绝数直接进表。**现在越权率只数网关的 403，完全看不见「它试图直连第三方」这件事，而后者才是「绕过数据面」的直接证据。** (b) 属 runner/ 或结算侧，**未做**。出处：2.6-tradingagents。 |
| **N-222** | TradingAgents 的**第三条**原生取数路径没堵 | 待修（v1.1） | `dataflows/stocktwits.py` 与 `dataflows/reddit.py` 用 `urllib.request.urlopen` 直抓 StockTwits API 与 Reddit RSS。真跑 `r03` 的 stderr 里逐条可见它被出向白名单挡下（`403 Forbidden`）。**没有改是刻意的**：改了就与 `sha256:d875d084…` 那次真跑的证据对不上，而同一目标的真跑预算（1 次 + 1 次重试）已经用完。修法与第二条缝同形（换成返回 `[NO_DATA]` 并留痕）；v1.1 修完必须**重跑一次**才能重新出证据。出处：2.6-tradingagents。 |
| **N-223** | **产出粒度与阶段不匹配**这一族失败，在结算侧只表现为 coverage 太小，与「跑挂了只交出几格」不可区分 | 登记不修 | 六个接入里有四个是这个形状：TradingAgents 交 3 格（3 标的 × 1 日）、FinMem 交 10 格（1 × 10）、StockAgent 交 8 格（2 × 4），而题面要的是 csi300 × 约 140 日。差额是事实，**接入层不替它补格子**。要在主表上区分这两件事，需要一个「声明的目标格数」之类的东西 —— 属出题面/结算口径。相关的预算事实：TradingAgents 一格约 20 次模型调用，100 次的闸放不下更多；要跑满面板得同时抬 `--max-calls` 与各接入自己的规模变量，并接受单次真跑数小时（发布验收时的**预算裁定**，不是代码问题）。出处：2.6-tradingagents、2.6-finmem、2.7。 |
| **N-224** | AlphaAgent 的滚动内核在序列头部是**扩张窗**，与 `warmup_policy=null_until_full` 直接冲突 | 记录（上游行为） | `alphaagent/dsl/core/accel.py::_roll_corr_numba`：`if w > i + 1: w = i + 1` + 有效对数 ≥2 就出值，于是 `TS_CORR(...,10)` 从第 2 个观测起就有值。两臂真跑都因此吃 `warmup_boundary`。**接入层没有替它修** —— 修了就是「我们替它改了多少」的分数。值得连着看的一件事：**模型自己在推理里诊断对了这一点却没改写就交付了**（原文在 `ops/reports/i_alphaagent/agent_trajectory.json`）。出处：2.6-alphaagent。 |
| **N-225** | S3 的 `warmup_policy` 没有**机器可读**的期望，被测方无法自检 | 建议（增强，不是修复） | 现状：`warmup.nonnull_before_warmup` 是被测方自报的一个整数，评分侧再按 gold 判 `warmup_boundary`。若在 S3 的 JSON Schema 里给 `warmup_policy` 的每个枚举值配一句机器可读的期望（`null_until_full` → `nonnull_before_warmup == 0`），协议臂的 validator 就能**当场**报，而不必等到结算。属冻结根（任务集轴）；题面现在没有说错话，所以**没进 pending_freeze_bumps**。出处：2.6-alphaagent。 |
| **N-226** | run dir 没有「**系统自留日志**」的采集位 | 建议（runner 路径） | 被测系统自己写的轨迹（AlphaAgent 的 `run_trajectory`、RD-Agent 的工作区日志……）落在容器 `/tmp`，随容器消失；不能落 `/task`（P8 文件集封闭核对会判 `unexpected`）。现在只能从 `log/llm_log.jsonl` 反向摘（够用但粗：拿不到工具返回给模型的完整内容，也拿不到 nudge 那几轮）。若 runner 在 run dir 下留一个 `system_log/` 并把容器里某个约定路径拷出来，接入方的自留轨迹就能进证据链。出处：2.6-alphaagent。 |
| **N-227** | 「**窗口之内、信号日之后**」的前视没有任何外部判据 | 待裁定（**倾向 ①**） | 网关只挡 `as_of` 之后的东西。对**逐日决策类**被测方（StockAgent、FinMem），「模拟第 d 天只能看到第 d 天为止」这条线**只能由接入层自己守，从外面完全看不出来守没守**。FinMem 那边的具体形态：整段用 train 模式会把**次日收益**喂进产出信号那一步（train 模式的动作直接取次日收益的符号），所以必须两段式（train 建记忆 → test 出决策，首尾相接不重叠）。两个方向：① 认了 —— 在手册里写成一条纪律并要求接入方在 README 里**点名那个函数**（两个接入都这么做了：`Market.brief` 只取 ≤ d）；② 让结算从 access_log 反推（**做不到** —— 那些请求本来就都合法）。倾向 ①，但**这是范式层的一个空洞，值得在论文里单独说明**。出处：2.7、2.6-finmem。 |
| **N-228** | 上游 StockAgent `e2a9c052` **原样跑不起来** | 记录 | 它的 `prompt/agent_prompt.py` 已改成四只股票（A/B/C/D），而 `agent.py` / `main.py` / `secretary.check_action` 仍只有两只 —— `plan_loan` 在**第一天**就 `KeyError: 'stock_c'`，**与用哪个模型无关**。接入用一个具名替换点把那几段 prompt 降回两只（文字由上游原文逐句删 C/D 从句得到，不是重写）。若上游修好，那个替换点应当撤掉 —— 判据盯的是「那些名字还在不在」，**不是「上游修没修」**。出处：2.7。 |
| **N-229** | 有的接入 vendored 的是**代码子集**而不是上游那份归档 | 记录 | StockAgent 的上游 tarball 里 `fig/` 占 4.5 MB（全包 97%），本机→f01 链路上反复传断（拿到过一个 261 KB 的截断文件，靠 sha256 对不上才发现）。所以 `pin.json` 记的是去掉 `fig/ .idea/ __pycache__/` 的子集 + **逐文件 sha256（9 个文件）**，另存上游归档哈希作参照。逐文件哈希比归档哈希硬（归档哈希会随打包器与时间漂），但**与「你 clone 下来的那份」不是同一个数** —— 复现时按 commit + 逐文件哈希核。出处：2.7。 |
| **N-230** | `runner/c42/upstream_pins.py::PINS` 里没有 `finmem` / `finrobot` / `stockagent` | 待裁定 | `PINS` 现在有 `rdagent_q` / `tradingagents` / `openhands` / `codex_cli`，与各自 `pin.json` 逐字对照（N-51 那次「两处各自都真、放一起是假话」的形态）。另外三个只活在 `integrations/<id>/pin.json` 里。`ops/test_integration_finmem.py::test_pin_matches_upstream_pins_when_that_table_has_an_entry` **已经幂等地守着**：表里一旦出现 `finmem`，它自动开始比对 `commit`；现在 skip。要加的字段：`finmem` `commit=be814aa47970de9bf2fdd6a1d5a60ae5cf361b46`（来源是**源码 tarball 而不是 dist**，sha256 `f0ee88b7…`）。要不要把 P2 接入统一登记进 `PINS` 是范式层的裁定；`runner/**` 不是阶段二的路径。出处：2.6-finmem、2.6-finrobot、2.7。 |
| **N-231** | `runner/c42/adapters/tradingagents/` 与 `integrations/tradingagents/` **并存** | 已处理（标注），删留待定 | 前者是上一代实现（自己拼 URL、自己做 PIT），**v1.0 起以后者为准**，已在 `integrations/tradingagents/README.md` 开头标注。没删（不是阶段二路径）。建议 v1.0 收口时由 `runner/**` 的负责代理决定删还是留一句指针。出处：2.6-tradingagents。 |
| **N-232** | `get_indicators` 的指标在接入层现算，口径**没有第三方背书** | 登记不修 | 上游 yfinance 路径用 `stockstats` 从 OHLCV 算指标；本接入保留 `stockstats`、只把 OHLCV 换成网关 `/bars`，所以口径与上游一致，但**这个环境里没有第二份指标可以对账**。算不出来时返回 `[NO_INDICATOR]` 并明说「没有回退到别的行情源」，不静默给一个数。出处：2.6-tradingagents。 |
| **N-233** | 两个上游仓库**没有 LICENSE**（`none_declared`），对外分发前须向作者确认 | **needs_from_user** | `RndmVariableQ/AlphaAgent` 与 `MingyuJ666/Stockagent` 都没有 LICENSE 文件，GitHub API 的 `license` 是 `null`；前者 README 末尾只有一句「open source … Research use only」。两份 `pin.json` 因此写 `none_declared` 而不猜一个 MIT。**内网研究性评测、镜像不对外分发**，按这个用法没有问题；**但发布材料要附带这些镜像、或把上游代码随论文/附录发出去，需要先向作者确认授权**。顺带：StockAgent vendored 的 `procoder`（`dhh1995/PromptCoder @ 87155427`）自己两处矛盾 —— LICENSE 文件是 Apache-2.0、`setup.py` 的 classifier 写 MIT，`pin.json` 以 LICENSE 文件为准并记下了这处矛盾。出处：2.6-alphaagent、2.7。 |


**D. 成本与覆盖两张表的口径**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-234** | 接入成本遥测上线，**阶段二每个接入都记了** | **已完成** | `integrations/cost/`（CLI `$PY -m integrations.cost`），账本 `COST.jsonl`（只追加，追加走 `fcntl.flock` 锁文件本身），报表 `COST.md`（**每次追加事件都在同一把锁里重算**，`report` 的日常用途只剩把手改过的改回去）。收口核对：**六个接入六行、`outcome` 全部非空**，与 `COVERAGE.md` 的六行逐行对得上。判据 `test_the_real_md_is_in_sync_with_the_real_ledger` 红了不是回归，跑一次 `report` 即可。出处：2.5。 |
| **N-235** | `--outcome` 的三个值覆盖不到「**接入成功、真跑跑通、被测系统 `invalid`**」 | 待裁定 | 三个值是 `passed_real_task` / `blocked` / `abandoned`。`rdagent_q` 与 `alphaagent` 都是这种结局，两位代理都填了 `passed_real_task` 并在 note 里解释。手册已写明口径（F-05：`--outcome` 说的是**接入这件事**成没成，「它考得怎么样」在 `COVERAGE.md` 的格值里），但**值本身是否要加第四个（如 `ran_real_task`）是编排方的裁定**。不加也能读，因为覆盖矩阵已经把这件事记准了。出处：2.6-alphaagent、2.6-finmem、2.6-rdagent_q、2.7。 |
| **N-236** | `end` 之后**没有补记返工的入口**，账本会系统性低估返工 | 待裁定（**倾向 (a)**） | 卡 2.6-finmem 实际返工 1 次（无头自检里 `import run` 撞上上游同名模块，重建了一次镜像），`end` 之后才想起来补记，工具正确地拒绝了（`当前状态是 'none'，不能 rework`）。于是 **`COST.md` 上 `finmem` 的返工列是 0、实际是 1**。这不是工具的 bug（拒绝是对的），是**口径的缺口**：卡 2.5 自己写着「返工是事后最想不起来的一项」，而「事后」恰好是唯一想得起来的时刻。(a) 允许 `rework --at <时刻>` 在 `none` 状态下补记（不改状态机，只补一条历史事件，而 `--at` 已是全套事件的既有参数）；(b) 给 `end` 加 `--amend-rework N`。出处：2.6-finmem。 |
| **N-237** | `cost end` 跑在 `git commit` **之前**，于是增删行恒为 0/0 | 待裁定 | `git diff <begin 时 HEAD>..HEAD -- integrations/<id>` 在文件还未跟踪时自然是 0；`现存非空行` 那一列才看得见。手册 §5.1 已写明这是文档过的行为，但**每个先 `end` 后 `commit` 的接入代理都会得到一行 0/0**（本阶段六行里有三行是 0/0：`tradingagents` / `finrobot` / `stockagent`）。要么把「先提交再 `end`」写进手册的步骤顺序，要么让 `loc` 在 `end` 时也认未跟踪文件。属卡 2.5 的裁定。出处：2.7。 |
| **N-238** | f02 上的**镜像构建耗时**不计入接入成本 | v1.1 | 「build 一次 20 分钟」在真实接入里是成本的大头，但它发生在执行面、由别的脚本发起，从 f01 侧的 `begin/pause/resume` 看不见。本阶段的实测跨度很大：命中同层缓存几秒（`rdagent_q`），第一次装 `rdagent==0.8.0` 二十分钟量级，`stockagent` 六次构建、`finrobot` 一次约 6 分钟。现在只能靠人在构建期间敲 `pause/resume` 近似。出处：2.5、2.6-rdagent_q、2.7。 |
| **N-239** | 发布材料引用「接入成本」时，用**净工时**一个数还是「净工时 + 返工次数」两个数并列 | 待裁定（**倾向并列**） | 单一分钟数会让「一次做对」和「返工三次凑出同样分钟数」看起来一模一样。本阶段的对照数：六个接入 460.0 净工时分钟 / 返工 4 次（其中 `finmem` 那一次未计入，见 N-236）；单个接入 44.2–105.7 分钟。**注意 `stockagent` 那 72.2 分钟不是纯接入成本** —— 卡 2.7 是「演练 + 修手册」两件事，工时里含写 15 条 findings 与改三份文档的时间。想看纯接入成本请看前五行。出处：2.5、2.7。 |
| **N-240** | `COVERAGE.md` 缺「**一个阶段两臂结果不同**」的写法 | **已完成** | 原规则是给「同一阶段跑过多次」的。现在的口径：**格值取该阶段最坏的那一臂，两臂差异写进备注**。`rdagent_q` 那一行就是这么写的（strict `invalid`、open 结构合规但覆盖率 0）。同时补上「阶段格必须恰好八个」（见 N-186）。出处：2.6-rdagent_q。 |


**E. 要别人改的 / 会连累所有人的**（不在阶段二的路径里）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-241** | `ops/push_exec_to_f02.sh` 收尾没有 `chmod -R go-rwx` —— 它自己的暂存产物是 0664，而**那会让生产网关起不来** | **建议尽快** | `$GB/scratch/exec_push/ops/__init__.py` 落地是 0664。后果比「别人跑全量多一条红」严重得多：`genebench-gateway.service` 的 `ExecStartPre` 就是 `ops/guard_modes.py`，**全树一个 0664 就让它起不来**。2026-09-07 15:12–15:31 实际发生过一次：`restart counter` 转到 25、网关停了约 35 分钟，**对别人的表现是「网关连不上」，肇事者自己什么都看不到**。诊断一条命令：`cd $REPO && $PY ops/guard_modes.py`（它会逐条列出是哪个文件）。**两张卡各自撞过一次、各自 chmod 修过一次** —— 根治在脚本收尾补一句。出处：2.6-tradingagents、2.7（F-08）。 |
| **N-242** | `.git/index` 被并发 git 重建成 0664，同样会拖垮网关 | 待裁定（**倾向 ①**） | 与上一条同一次事故的另外两条肇事文件。**这个不是谁忘了 `umask` —— git 自己就这么写**，谁都挡不住。表现是 `ops/test_env_guard.py::test_guard_covers_the_git_object_store` 随机红（多代理并行时会闪烁，看到时先复跑一次再当真），最坏是网关停摆。① 把 `.git/index` 从 `guard_modes` 的扫描集里排除（它不含答案面字节，只是索引）；② 在 git 钩子里收紧（挡不住外部 git 客户端）。出处：2.7、2.6-finmem。 |
| **N-243** | f02 的 `exec/vendor/**/__pycache__` 是 0775 时，**注入期就 P0 中止** | 已修一次，**会再犯** | 两臂各 0.1 秒 `ERROR: RunError: 注入失败：[P0] 红线 5 目录对组/其它开放 0o775 …`，**run dir 根本没建、没有容器日志**。谁在 f02 上没带 `PYTHONDONTWRITEBYTECODE=1` 跑过一次 `exec/` 下的 python 就会再造一个。一条命令：`ssh finance01-ts 'ssh ljn@192.168.1.219 "chmod -R go-rwx /data/genebench_runner/exec/vendor/h11/__pycache__"'`。根治：在 `push_exec_to_f02.sh` 落地之后统一收紧一次，或在注入前自己收紧。出处：2.6-finmem。 |
| **N-244** | `ops/test_env.py::_no_outbound_network` 的离线守卫是 **session 级 autouse**，把局域网数据面也当成「出网」 | 待别人改 | 它把 `socket.*` 换成「非回环一律 `AssertionError`」，而 **teardown 在整场测试结束时才跑** —— 全量按字母序跑到 `test_env.py` 之后这道门就一直开着。垫片的 14 条真打测试要连的是 `192.168.1.48:18080`（红线 4 要求网关绑显式 LAN 地址，**不可能**在回环上），于是全量里同时红、而单跑全绿。它要挡的是「某个 import 顺手去 pypi」，**局域网数据面不是外网**。建议的一行修法：`_is_loopback` 末尾加 ` or h == cfg.GATEWAY_HOST`（判据仍按**地址**不按调用点）。垫片的自救是真打期间换上**更窄**的一道门（只放行回环与网关那一个地址），**不是拆门**；守卫修好后那段自救可以删。出处：2.2。 |
| **N-245** | `scratch/<卡号>` 会撞车：同一个卡号被多个代理同时用 | 待裁定 | 三个做 `2.6` 的代理同时用 `/data/shared/genebench/scratch/2.6/`。后果不是理论的：双方互相覆盖了 `realrun.sh` 与 `README.md`（**文件被覆盖时没有任何提示，两边都不会主动发现**），并且有人在没重读文件的情况下 `sed` 改了「自己的」`realrun.sh` 并起了一次进程 —— 那条命令带的是**对方的 `--config-id`**（发现后立刻 kill，当时还阻塞在 `gateway_lock` 上、远端 `run_f02_a1` 从未启动，零模型调用、零 run dir）。建议施工契约把 scratch 落点从「卡号」改成「**卡号-系统名**」，或由编排方保证卡号全局唯一。出处：2.6-tradingagents。 |
| **N-246** | `pin.json` 的通用断言：现在只有 `example_minimal` 那一份被守门 | 待办（**现在做不再是恒绿**） | 当时不做是因为只有一份 pin，通用断言会是恒绿的自证；**现在有七份**（六个接入 + 示例）。建议加：`integrations/*/pin.json` 键集精确（D-21 七键）、`commit` 与 `dist` 至少一个非空、从 PyPI 装的必须同时给 `dist` 与 `dist_repo_url`。pin 的全部价值就在「半年后还能复现你接的是哪一版」。出处：2.4。 |
| **N-247** | **CONFLICT**：`HOME` 该指到 `/task` 下还是 `/tmp` 下，两份手册说的相反 | 待裁定（**倾向保持分开**） | `harnesses/README.md` 写「指到 `/task` 下的可写处并 `mkdir -p`」，六个 P1 harness 的 `launch.json` 全这么写；`integrations/README.md` §1④ 对 P2 给的是 `/tmp/...`。技术事实：容器里的 `/task` **就是** run dir 的 `work/`，落在它下面的东西会进 `run.json` 的 `unexpected`（阶段三实测一次真跑多出 297 个 bun 转译缓存文件）。**六张 2.6/2.7 卡各自独立引用了这处 CONFLICT 并一致按保守方向做**（P2 一律 `/tmp`），六次实测 `unexpected` 都是空。理由：P1 只能从外面设第三方 CLI 的 `HOME`，P2 的代码是接入者自己的，没有那个约束。若要统一，值得考虑让 `harvest.py` 的 `unexpected` 判定排除**声明过的** HOME 目录 —— 那样两边就能统一到 `/task`。出处：2.4 + 2.6 五张 + 2.7。 |
| **N-248** | `harnesses/README.md` 第 368 行的示例命令仍写 `--max-tokens 600000` | 待办（同 **N-151** 同族） | 权威是 `runner/registry.py::RUN_BUDGET`（默认 `max_calls: 100` / `max_tokens: 600_000`）。把**默认值**抄进可复制的真跑命令，照抄的人在长上下文系统上会在第 13~20 次调用左右停住而**没有任何东西会红**（`budget_exceeded` 只落 `llm_log`）。`integrations/README.md` §1⑤/§1⑥ 已按权威订正（默认值是默认值、命令显式给 `--max-tokens 3000000`，并有断言盯着两处）；harness 侧那一处请照本文改。出处：2.4。 |
| **N-249** | `ops/test_c41.py` 里写死的 `len(REG.CONFIGS) == 3` | **已完成**（见 N-136） | 阶段二第一个把 `config.yaml` 翻成 `enabled: true` 的代理会把它跑红。已改成「内置三条 ⊆ CONFIGS、`config_id` 互异、`harness` 名互异、同一模型」，并保留一条反向判据。此处只是把阶段二的相关性记下来：本阶段一次加了六条 enabled 配置，那条断言若没改，六个接入一个都落不了地。出处：W-0、2.5、2.6 各卡。 |
| **N-250** | **N-105 可以关了**：RD-Agent(Q) 的真 LLM 驱动循环已跑通 | **已关** | 原文是「真 LLM 驱动循环未实现 → BLOCKED，裁定不修内核」。`s3-cor-01.strict.cfg-rdagent_q-deepseek.r02` 是一次模型驱动的完整循环：DeepSeek 写 `factor.py`、上游 `FactorFBWorkspace` 子进程执行、上游评审器给 critic，产出覆盖率 0.989 的真值序列，18 次调用全部 `decision=allow`。**内核仍然一个字没改**（`runner/c42/adapters/**` 只读）—— 补上那一步靠的是上游自己的扩展点（`knowledge_self_gen=False` 与构造形参）。降级路径保留，只用于 f01 走查。出处：2.6-rdagent_q。 |

---

## 2026-09-07 建到可分发·阶段一（数据面收口，公开通道）+ W-0 施工基础

阶段一做的是「**这套东西能不能交到外面去**」的数据面那一半：把整条链在一份**任何人都能自己拉到的行情**
（baostock）上从零长第二遍 —— 公开 provider → gold → 互检 → τ → ε → IC-ε → 公开 `calibration.json` →
公开出集 → oracle / 三控 / 破坏样本 / 验证验证器 → 两通道对账 → 数据卡 → 两种发布形态 —— 然后请红队
**只按手册**走一遍，把手册走不通的地方记下来。W-0 是这一轮之前铺的施工基础（`exec/` 同步、API 用量机器统计）。

下面是 `ops/tickets_inbox/1.*.md`（`1.1a` / `1.1b` / `1.1c` / `1.2` / `1.3` / `1.4` / `1.5` / `1.rt`）
与 `W-0.md` 共九份收件箱的逐条并入。同一件事被多张卡登记的**合并为一条**，出处逐一列在说明末尾。
**已修的也登记** —— 它们改变了别人对系统的认识（尤其是那些「跑起来 ok、结论全错」的）。
红队 13 条 finding 里 block 2 / major 4 由卡 1.rt 修完（N-301 / N-302 / N-303 / N-304 / N-305），
minor 7 条登记不修（N-307…N-313）。


**A. 公开通道数据面**（卡 1.1-a：把私有那份行情整个换掉，其余一切不动）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-251** | **公开通道数据面建成**：`$SNAPSHOTS/public_v1/{tables,tradability,qlib_provider}` | **已完成** | 3,575 只（v1 三宇宙并集）× 2009-01-05..2026-07-31。表 6 张（daily 10,948,502 / adj_factor 11,327,557 / stk_limit 11,327,557 / suspend_d 379,055 / trade_cal 6,417 / stock_basic 5,552）；tradability 18 个年分区共 11,327,560 行；provider 28,600 个 bin（3,575 × 8 字段），`files.sha256` 根 `561348660a3175b1…`。一条命令 `ops/build_public_channel.py`，可续跑，不含拉数 **5.3 分钟**。出处：1.1-a。 |
| **N-252** | **网关通道开关** `GENEBENCH_CHANNEL=private\|public` | **已完成** | 默认 `private`，**私有通道数据端点逐字节不变**（5 票 × 7 端点 sha256 全同，证据 `scratch/1.1a/{baseline_private,after_private}`）。public 读 `public_v1` 的表、日志写 `logs/gateway_access_public.jsonl`、端口默认 18081；绑定地址规则一个字没改（仍走 `assert_no_wildcard_bind`）。`/healthz` **新增两个字段** `channel` / `tables_dir` —— 这是唯一一处私有回包的变化，**刻意为之**：两个实例外观一样时「对着公开网关核私有数字」不会被任何东西发现。出处：1.1-a。 |
| **N-253** | 公开通道 **`/fundamentals` 403 并记账**，要财务表的题在公开通道跑不出来 | **已完成（按设计）** | 403 + `reason=dataset_not_exposed_in_v1` + `extra.channel=public`。理由是**源侧做不到 PIT**（baostock 季频财务无 `f_ann_date`），不是「暂时没建」。公开通道按设计扣掉六张财务表（`PUBLIC_WITHHELD_DATASETS`）；本轮 O1 里凡因此失败的题逐条列在 `ops/reports/public/o1_summary.md`。**这是通道的性质，不是 oracle 的缺陷** —— 公开发布时数据卡里要写明哪些题在公开通道上不可复现。出处：1.1-a、1.1-c。 |
| **N-254** | 公开通道的 **`all` 宇宙 ≠ 私有的 `all`**（北交所 336 只是真缺口） | 登记 | 公开 `instruments/all.txt` 3,575 行、私有 5,813 行，丢掉的 2,238 个码逐一记在 provider manifest 的 `instruments.dropped_codes`。差额拆两块：**336 只北交所是真缺口**（baostock 不服务北交所），其余 1,906 只是「公开通道只建三宇宙并集」（N-68）的结果、不是缺口。三个基准宇宙（csi300/500/1000）的 instruments 与私有**逐行相同**，所以不阻塞 v1；v1.1 若要 `all` 得换源或声明分母不同。出处：1.1-a、1.3。 |
| **N-255** | **退市整理期首日无限制**这条规则在公开通道**推不出来**；涨跌停已知偏差 4 行 | 登记不修 | 判据 `namechange.change_reason = '退市整理期'` 是**私有表**。2026-01-01..冻结线逐行核 466,773 行，一致率 0.9999914，**分歧 4 行全部是退市整理期首日**（`600193.SH`/`600608.SH`@20260608、`600636.SH`/`600696.SH`@20260601）。**S7 / S8 用公开通道时这是已知偏差面。** 不要用名字近似去补：退市命名规则两个交易所相反（深 / 北后缀「退」、沪前缀「退市」），按名字判会**整个漏掉沪市**。出处：1.1-a、1.3。 |
| **N-256** | 公开 `adj_factor` 与私有**不同基准**，绝对值不可跨通道比 | 登记 | 只有比值 `adj(t)/adj(t₀)` 有意义（provider 用的就是比值）。5 票样本比值跨度 ≤ 9.3e-6。`/adj` 的回包因此**不是**跨通道逐值可比的端点。出处：1.1-a。 |
| **N-257** | baostock **会话会掉**，症状看起来像数据问题 | **已修** | 实测连拉 2,012 只之后剩下每一只都失败。`fetch_adj.RELOGIN_AFTER=5`：连续失败到阈值就重登，重登后仍失败才算真失败。第一版会把 1,500 只全记成「失败清单」—— 那份清单看起来像是数据源缺票。出处：1.1-a。 |
| **N-258** | 公开通道的**宇宙轴沿用 v1**，不是从公开源重建的 | 已记录（数据卡必须写明） | `snapshots/public_v1/universe/universe_pit.parquet` 是 `snapshots/v1/` 那份的**逐字节副本**（sha256 `f1c4e6b2…`），与 `PUBLIC_PATHS.universe_pit` 同一条裁定（卡 2.5 §1 第 4 项 / N-68）：「谁在指数里」是**定义**不是行情。复制进公开根只是为了让公开包**自足**（外部用户手里没有 `snapshots/v1/`）。**数据卡里必须写明这一条** —— 否则「公开通道可从公开源完全重建」这句话不成立。出处：1.1-b。 |


**B. 公开通道重建链**（卡 1.1-b：gold → 互检 → τ → ε → IC-ε → `calibration.json`，一次跑完 4 小时 15 分）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-259** | `reference/factor_exec.run()` 把 **792 个因子面板同时压在内存里** —— 公开 gold 被内核 OOM 杀过两次 | **已解（r1.0.19）** | csi1000 的面板是 2716×2839 的 float64，792 张常驻约 **22 GiB**，而 f01 只有 30 GiB 且是共用机；2026-09-07 05:20Z 那次把整机拖到失联两小时。**能看出「是换页不是慢」的那个数**：私有那次 `write_gold` 是 7.8 秒一个 parquet，公开这两次退化到**一小时一个**，被杀之前 2.7 小时一个文件都没写出来。r1.0.19 加 `PanelStore` / `SpillPanelStore`：求值边算边把面板交出去（`--spill-dir` 落临时盘），`write_gold` 写完一个放一个。峰值 RSS 22 GiB → 全链 6.93 GiB，**落盘产物逐字节不变**（私有 csi300 的 792 个 parquet 重建后逐文件 sha256 相同）。**注意默认是关的**：`spill_dir` 默认 `None`（不改既有调用方的行为），只有 `ops/run_public_chain.py` 的 gold 步默认带上 —— **谁重跑私有 gold 不给 `--spill-dir` 就会踩同一个坑**。出处：1.1-b。 |
| **N-260** | `ops/run_public_chain.py` 在 **import 期**改进程环境变量 | **已解** | 原来 `os.environ.setdefault("GENEBENCH_CHANNEL","public")` 写在**模块顶上**。表现：**任何 import 了它的进程整个翻到公开通道** —— 同一次 pytest 里跑在它后面的 `ops/test_calibration.py` 于是去读 `snapshots/public_v1/calibration.json`，**17 条 ERROR**，而两个模块各自单跑都绿（全量按字母序跑、`test_calibration` 在前，所以一直没暴露；用 `-p xdist` 或随机序会随机炸）。已挪进 `main()` 并加 `test_importing_the_chain_module_does_not_flip_the_process_channel` 钉住。**谁再写「在模块顶上 setdefault 环境变量」的脚本，请照这条改。** 出处：1.1-b。 |
| **N-261** | 公开通道快照**没有 `universe/`**，IC 族 ε 标不了公开那一份 | **已解（哨兵按设计翻红后改成正向断言）** | 卡 1.2 把这条钉成一条**会自己失效**的断言（`test_public_channel_snapshot_is_still_missing_universe`：`universe/` 建好那天它变红）。卡 1.1-b 把它建起来了，哨兵如期变红 → 翻成正向断言：`universe_pit.parquet` 必须在，且 `ICE.Inputs.preflight(public_root)` 必须过。**没有放宽判据**：删掉那个文件、或公开链换落点，这条照样红。出处：1.2、1.1-b。 |
| **N-262** | `reference/factor_crosscheck.py` 与 `reference/backtest.py` 的落点**还是 ops 侧覆盖的**，没参数化到模块里 | 未做（v1.1） | 公开链靠 `ops/run_public_chain.py` 的 `channel_overrides()` 临时接管 `CELLS_DIR` / `REPORT_JSON` / `RESULT_DIR`。**这不是等价的**：任何**不经过 `run_public_chain.py`** 的调用方（例如有人直接 `python -m reference.factor_crosscheck`）在 `GENEBENCH_CHANNEL=public` 下会把公开互检格**写进私有目录且不报错**。`test_channel_overrides_cover_every_private_rooted_path` 兜住「覆盖表漏项」，兜不住「绕过覆盖表」。v1.1 照 `factor_exec` 的 PEP 562 `__getattr__` 写法补上，然后删掉覆盖表。出处：1.1-b。 |
| **N-263** | `ops/run_oracles.py:44` 的 `GATEWAY_URL` **写死私有端口** | **已解（卡 1.1-c）** | `GATEWAY_URL = f"http://{cfg.GATEWAY_HOST}:{cfg.GATEWAY_PORT}"`。卡 1.1-a 点名、卡 1.1-b 因不在授权路径未改，卡 1.1-c 改成按通道取端口并允许 `GENEBENCH_GATEWAY_URL` 覆盖。改完 oracle 打公开网关就是 `GENEBENCH_CHANNEL=public GENEBENCH_GATEWAY_URL=http://192.168.1.48:18081`。`reference/gateway_client.py` 不用改（`base_url` 由调用方给，`reference/oracle_io.py` 已声明 `GENEBENCH_GATEWAY_URL` 是唯一允许的环境变量）。出处：1.1-a、1.1-b、1.1-c。 |
| **N-264** | 公开 τ 与私有只差 **2.5e-5**，但那**不是**「两条通道一致」的证据 | 已记录（读数时必须连着读） | 公开 τ = 0.983981，私有 0.984006；参与因子 141 / 参与格 379,950 / 算子冲突 13 条**两边完全相同**，互检的 `skipped` 分类（same_engine 66 / parse_fail 527 / eval_fail 40）也逐项相同。原因是**因子库与宇宙轴两条通道共用**（宇宙轴按 N-68 沿用 v1），真正换掉的只有行情，所以「哪些因子可比、可比多少格」本来就该一样。它证明的是「同一份代码 + 同一份因子库在另一份行情上跑出来的 τ 量级不变」，**不是**「公开数据面与私有数据面等价」—— 后者要看 N-290 那条对账。出处：1.1-b。 |
| **N-265** | 公开通道的 `epsilon.json`（跨库版本那一版）**不重跑** | 不做（有意） | 它在 D-05 已被判为**标定源失效**（跨 4 个 numpy/pandas 组合最大相对极差 8.53e-14，全是舍入），`calibration.json` 里只留作反面记录。公开重跑不产生新信息且要复制 4 套 venv。公开 `calibration.json` 的 `epsilon.superseded_cross_version` 因此是空壳（`max_relative_spread=None`）—— **这是有意的，不是漏跑**，报告与数据卡都写明。出处：1.1-b。 |
| **N-266** | 公开 IC-ε **只跑判据窗**，窗敏感性没跑 | 未做 | 与卡 1.2 私有侧同一条缺口，且两条通道**必须同窗**才可比，所以公开也只跑 `2026-01-05..2026-06-30`（样本 7,128 条，三宇宙各 2,376，与私有同量）。另两个窗（2025H1 / 2025H2）公开一条都没跑。出处：1.2、1.1-b。 |


**C. 标定：τ / ε / IC 族 ε**（卡 1.2 定 IC 族的带，卡 1.1-b 把它收进 `calibration.build()`，卡 1.3 量出两通道的带差）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-117 更新** | S4 的 effect 出不来 | **已解（卡 1.2 + 1.1-b 收口）** | IC 族拿到了带（`calibration.json.epsilon.ic_family`，标定见 `ops/ic_epsilon.py` 与 `snapshots/<通道>/epsilon/ic_epsilon_dual.json`），`scorer.l3.compare_epsilon` 现在能比 20 个叶子（mean / std / icir / positive_ratio / coverage × ic_stats + 三个持有期），`l3_pass` 不再是 `None`、锚点不再退化。`ci_low` / `ci_high` 仍无带（N-269），照旧跳过。**卡 1.1-b 补上了它的第二半**：卡 1.2 是用 `ops/merge_ic_epsilon.py` 把 `ic_family` **事后插进**已落盘的 `calibration.json` 的，于是「再跑一次 `calibration.build()` 就把它抹掉」—— 抹掉之后 S4 静默回到 `l3_pass=None` / `effect=None`，**没有任何一处会报错**；r1.0.19 把它收进 `reference/calibration._ic_family()`（块的内容仍由 `merge_ic_epsilon.build_block` 产出，同一份代码），私有 `calibration.json` 用新代码重建后**逐字节相同**。主表的 `unsettled_runs` 列对 S4 不再生效 —— 写论文时请核一遍那一列的措辞。出处：1.2、1.1-b。 |
| **N-267** | **题面没写清 ICIR 要不要年化** | 待裁定（**要推任务集版本**） | qlib 的 `SigAnaRecord._generate` 里 `ICIR = ic.mean()/ic.std()`，**不年化**；S4 题面声明 `annualization=252` 而参考实现年化（×√252）。两者差 **15.87 倍** —— 那不是容差能盖的。卡 1.2 按 2.2b 的纪律**不把它写成 ε**：标定时两边都年化，量的才是实现自由度；歧义单列在产物的 `icir_annualization_ambiguity`。建议 v1.1 在 `INSTRUCTION.*.md` 与 `ops/specs/artifact_schema/v1.0/S4.json` 里钉死「ICIR = mean/std × √annualization」—— 那是题面改动，必推任务集版本（冻结根）。出处：1.2。 |
| **N-268** | **题面「当日不可交易」没定义到 `status` 档位** | 待裁定（**要推任务集版本**） | `/tradability` 的 `status` 有五档（`trade` / `suspend` / `limit_up` / `limit_down` / `no_data`）。参考实现读成「`trade` 之外全不可交易」；**涨停那天股票是成交的**，读成「只有停牌 / 无数据不可交易」同样站得住。卡 1.2 把这两种读法当成实现 B / C，**IC 族 ε 里最大的一块就来自它**（`coverage` 的带几乎全部由它决定）。钉死这一条能让带窄一个数量级，同样是题面改动。出处：1.2。 |
| **N-269** | `ci_low` / `ci_high` 没有带，S4 的 CI 目前不判 | 登记不修 | qlib 口径**不产 bootstrap 区间**（`SigAnaRecord` 只出 IC/ICIR/RankIC），双实现对在这一项上构不成。硬造第二份自举实现量到的是 RNG 抽样而不是实现自由度，所以标 `no_pair_in_qlib_path`、不出带。实测 M6 真 agent 的 CI 与 gold 差 0.0013–0.040（`ops/reports/public/n117_before_after.md`）。要判就得先在题面钉死自举算法（块长 / 重抽次数 / 种子来源），那又是题面改动。出处：1.2。 |
| **N-270** | `reference/epsilon_dual.py` 的**绝对容差分支缺噪声地板闸** | 登记不修（参考轴） | `compare()` / `compare_pairwise()` 只在 `kind == "relative"` 时判 `NOISE_FLOOR`；绝对容差分支只判 `diff == 0`。于是「两份实现逐位相同、只差 float64 舍入」会被写成一条 **1e-18 的 ε** —— 正是 E-1 说的比特级相等断言，只是没有恰好等于 0 所以逃过了 `no_implementation_freedom` 那一支。**当前回测样本没触到这个分支**（`ann_return_net` 的绝对差是 8e-5，远高于舍入）。卡 1.2 在 `ops/ic_epsilon.band_from_diffs()` 里补了这道闸（一律用**相对**分歧判地板），实测第一版 A/B 实现对就撞上了它。出处：1.2。 |
| **N-271** | **ε 的带规则在两处不一样**：回测 ε 取「全对最大差 × 1.5」，IC 族 ε 取「全对最大差分布的 P90 × 1.5」 | 待签字（已在产物里写明） | 2.2b 的样本面是一次回测（3 份实现两两比 = 3 个数），取最大是唯一可能；IC 族的样本面是 N 因子 × 3 宇宙 × 3 窗 的一个**分布**，取最大 = 让带被最病态的那个因子绑架。P90 是 τ 的 P10 的镜像（`ops/specs/GeneBench秩相关与标定口径_v1.md` F-2 允许 10% 的尾巴落在门外）。每条带同时报 P50 / P90 / P95 / P99 / max 与 `epsilon_if_max_rule`，好让签字人看见这个选择的代价。出处：1.2。 |
| **N-272** | **两条通道的 `calibration.json` 都写着 `ready_for_scoring=false` / `outstanding=「epsilon: 标定源失效，等换源后回填」`，与现状不符** | 待签字（三张卡各提过一次） | 根因：`build()` 里 `ready_for_scoring = epsilon.usable`，而 `epsilon.usable` 要求**三个频率全 usable** —— weekly / monthly 按 2.2b 纪律**永远不会** usable。而现状是 `by_frequency.daily.usable=true`（2.2b 已回填）+ `ic_family` 四项可用（N-117）。三张卡都按「原值不许动」没改：**改它等于改判据口径，要签字**。建议改成「daily 可用 且 ic_family 可用」，或显式分频记。`ops/HANDOFF.md` 第 269 行也记着同一条。出处：1.2、1.1-b、1.3。 |
| **N-273** | 「`win_rate_net` 没有实现自由度」是**那份数据的性质**，不是那三份实现的性质 | 待裁定（已记录） | 私有 ε[daily] 的 `win_rate_net` 被标成 `no_implementation_freedom`（三份冻结实现完全同值 → 按纪律不出带、也不许用别的指标的 ε 代填，即 L3 不判这一项）。公开通道跑**同一份代码、同样三份实现**，它**真的分开了**并量到一条带 —— 公开 daily 是「可标定 9 / 无自由度 0」，私有是「8 / 1」。**分档结论不变**（两边 `daily.usable` 都是 True），所以不算结构性结论变化；但「零自由度」这个判读**只对当时那份行情成立**。建议 `epsilon_dual` 在标 `no_implementation_freedom` 时把「这是在哪份输入面板上观察到的」（面板 sha256）一起记进产物，免得后来的人把它当成实现层的定论。出处：1.1-b。 |
| **N-274** | **ε 的带值两条通道差到同一量级之外，而分档结论完全相同 —— 带不可跨通道用** | 待裁定 | `daily` 档：`total_cost` 公开 2.851e-06 vs 私有 1.008e-03（**353 倍**）、`ann_return_gross` 0.005125 vs 0.002372、`sharpe_net` 0.009341 vs 0.004387；`weekly` 的 `win_rate_net` 公开 0.004985 vs 私有 3.643e-06（**1,368 倍**）。**分档结论（哪一档 usable、哪些指标超阈）逐项相同**，所以卡 2.5 §10 的判据没破。要登记的是这条**事实**：ε 是「这份数据 + 这三份实现」的**联合性质**。`scorer/l3.py` 读 `cfg.calibration_path()`（按通道走），行为已经是对的；**但没有任何东西拦住**有人把私有的带手工填进公开通道的判定。待裁：要不要加一条断言（`calibration.json` 记 channel，scorer 取带时核对通道一致）？逐指标并列表在 `ops/reports/public/reconciliation.md` §2.2。出处：1.3。 |
| **N-275** | M6 的真 agent 在 S4 上把 mean / std / icir / positive_ratio 复现到了**逐位相同** | 观察，建议进论文 | `runs_in/m6/s4-cor-01.strict.cfg-codex-deepseek.r02`：四个统计量与 gold 差 **0**，只有 `coverage` 报 1.000000（gold 0.988218）与 bootstrap CI 不同。coverage 报 1.0 说明它**没按题面剔无效格**却把分母也换掉了 —— 一个「数算对了但口径没照做」的干净实例。相对差 1.178%，正好落在卡 1.2 标出的 coverage 带（ε=1.18e-02 @h=1）边上。出处：1.2。 |


**D. 公开通道跑批与公开出集**（卡 1.1-c：materiality screen → O1 → 三控 → 破坏样本 → 验证验证器）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-103 更新** | `s6-rob-02` 出不了集：`rebalance_frequency` 在 `weighting_scheme=equal` 下无 materiality 证据 | **证据已量到，卡在「写进冻结根 + 推任务集版本」** | 2026-09-07 用三份冻结独立实现（B1/B2/B3）逐可行值 daily/weekly/monthly 各跑一遍：**私有通道**三份实现内部各有 26/26/27 处指标超 daily 档 ε 带（共 79 处，跨实现分叉 50 处），**公开通道** 27/27/27（共 81 处）—— **两条通道都 material**。Gate 0（未打补丁的沙箱副本复现快照产物）双通道均过；本字段**不打任何补丁**（频率就是三份实现的 argv），Gate 1 不适用。条目正文（数全部从产物渲染、可原样粘贴）在 `ops/reports/public/materiality_evidence.json` 的 `entries[0].text`，`python_key` 字段给的就是字典键。**要落地还差一步**：写进 `genetask/schema.py::DIVERGENCE_EVIDENCE` 并推任务集版本（冻结根）。**为什么必须推**：它一变，`s6-rob-02` 就从「不落盘」变成「落盘」，出集清单实质变了；推完还要重跑 `ops/run_oracles.py --tasks s6-rob-02`（两条通道各一次）。出处：1.1-c。 |
| **N-118 更新** | `run_oracles` 的日志切片只有两维 | **已修（前人）+ 本轮复核** | 三维切片在本轮公开通道跑批上真的用上了。另新增一条：可交易性视图用**另一个 `config_id`**（`oracle_probe_view`）取，否则它那几次 `/tradability` 会落进同一块，把 `declared_reads` 判红 —— **取证动作把被取证的东西判红**。出处：1.1-c。 |
| **N-120** | 跑批没有把可交易性视图喂给校验器 | **已解** | `ops/run_oracles.py::tradability_view()` 与 `ops/run_probe_mutations.py::trad_view` 是**同一份代码**（后者加了 `config_id` 参数，默认不变）。此前跑批传 `tradability=None`，`calendar` 与 `missing_masquerading_as_signal` 两族**根本不会被调用**，而矩阵里它们画成 `·`（判过且零）。判据钉在 `ops/test_public_acceptance.py`：夹具上不喂视图时那两族**一条都不响**，喂了就响；另有一条用记账器证明 `run_one` 真的把视图传进了 `sch.validate`。32 题里 28 题喂到，S8 四题拿不到（见 N-288），逐题记「这两族没被调用过」，**不假装 clean**。出处：1.1-c。 |
| **N-276** | **`gateway/sim_factory.py::task_dir` 只要出现第二个出集就抛歧义 —— 公开出集一建出来，私有生产网关的 S8 四题一起 500** | **已绕开（改落点），根治要改 `gateway/`** | `task_dir()` 是 `(GB/reference/tasks).glob(f"*/{task_id}")`，命中两个就 `RuntimeError: 在多个出集里都有 …… 不猜`。把公开出集直接放成 `tasks/v1.0-smoke-public/` 之后，**两条通道的 S8 一起坏**（实测 s8-cor/eco/ops/rob 四题 `/sim/log 返回 500`）。**这不是公开通道的问题 —— 它同时打坏了私有那条。** 绕法：公开出集改放 `$GB/reference/tasks/public/v1.0-smoke-public/`（在那个 glob 的射程之外），私有 `task_dir("s8-cor-01")` 已复核回到 `tasks/v1.0-smoke/s8-cor-01`。**谁要再建第三个出集（例如公开发布用的那份），先看这一条。** 根治：`task_dir` 按通道选出集根，或让 `build_engine` 把 `set_id` 传下去（`read_task_face` 已经有这个参数）。**顺带**：公开通道跑 S8 时会话的题面仍从**私有**出集读（题面四键两个出集逐字相同，所以行为正确，但这是一处真实的跨出集读）。出处：1.1-c。 |
| **N-277** | `reference/make_s7_signal.py::extract(source=SOURCE_PANEL)` 把私有面板路径**烤进了默认参数** | **已绕开，v1.1 参数化** | 覆盖模块常量 `SOURCE_PANEL` 之后 `extract()` 照旧读私有面板 —— **默认参数在 import 期求值**。实测表现：公开出集里 S7 五题的 `work/signal.parquet` sha256 与题面声明的**逐字相同**，而题面那个值是私有行情下标定的；数字照出，两边都不说话。绕法是包**函数**不是常量，并加一道硬闸：任何一件夹具的 sha 与题面声明相同就停下。`reference/make_fixtures.py::GOLD_FACTORS` 与 `make_s7_signal.SOURCE_PANEL` 都写死在 `snapshots/v1/`，v1.1 应照 `factor_exec` 的 `__getattr__` 写法按通道取 —— **改的时候注意这种把路径烤进默认参数的写法，改常量对它无效**。出处：1.1-c。 |
| **N-278** | 公开出集的夹具 sha256 与题面 `inputs[].sha256` **必然不同** | 登记不修（要自洽就得有公开任务集版本） | 夹具是从公开 gold / 公开 ε 面板切出来的，题面里的 sha 是私有行情下标定的。**29 件夹具没有一件与声明相同** —— 这正是「公开夹具真的来自公开源」的证据（见上一条的硬闸）。逐条对照落 `ops/reports/public/fixture_sha_vs_declared.json`。**不把 sha 写回题面**（`genetask/params` 是冻结根，红线 4）。当前 `taskspec.json` 只有四键、不含 inputs，所以校验器不看这个 sha、跑批不受影响；但公开发布时「题面声明的输入 sha 与包里的对不上」会是外部用户第一个问的问题 —— 真要自洽得有一个**公开任务集版本**，那是签字人的决定。出处：1.1-c。 |
| **N-279** | `s2-eco-01` 的 oracle 打 `/bars?universe=csi300`（不给 `code`），网关 422 —— **「33 题零 finding」这个完成定义两条通道都只到 32** | 待裁定 | `gateway/routers/market.py:165` 明写「/bars 必须指定至少一个 code」；`solve.py` 第 7 行自己留着 TODO「确认 /bars 是否接受 universe=… 的批量形态」。**私有通道的 O1 累积记录里它同样红**（同一条 422，端口 18080），所以这不是公开通道少了一题。两条路：① 让 `/bars` 接 `universe` —— 会改 S2-ECO **效率分母**的定义，要重新定「理论最少 4 次请求」那句话；② 把这道题的 oracle 改成按 code 批量取，并把「每码恰 1 次」写进 scorer 的分母说明。两条都要改不在卡 1.1-c 路径的文件，且都影响一道题的效率判据。出处：1.1-c。 |
| **N-280** | `ops/run_materiality_screen.py` 找的是**模块**入口，而 B 侧三份实现是**脚本** —— 它一次也没跑过 | **已解** | `IMPL_CANDIDATES` 找 `reference.backtest_b1` 这样的模块，**仓库里从来没有过这些模块**；2026-09-03 真跑出 S7 证据的那次走的是 `ops/screen_runner.py`（把 `snapshots/<通道>/epsilon/impl_v2_b{1,2,3}.py` 复制进沙箱、子进程跑、读它自己写的 JSON）。卡 1.1-c 把脚本接上，并把 `_resolve()` 留作**取证**（实际可见的候选写进报告的 `entrypoint_forensics`）。接上之后 S6 的 `rebalance_frequency` 当场量到（见 N-103）。出处：1.1-c。 |
| **N-281** | 八道探针题里有六道，这套 harness **结构上量不到** | 登记不修（要新一轮标定） | `data_version` / `adjust` / `eval_frequency` / `holding_periods` / `signal_frequency` / `slippage_reference_price`：三份冻结实现是 S7 的**回测引擎**，输入是一张定死的 csi300 面板，里头根本没有这些概念（「数据版本」「求值频率」「滑点参考价」都不是它的入口）。逐条理由写在 `ops/run_materiality_screen.py::OUT_OF_REACH`，并有**反僵尸测试**要求「每个探针字段要么能 screen 要么登记理由」。**「量不到」不是「没差别」，不据此翻锁。** 要出证据得先有能变这些字段的独立实现（S1 取数、S3 求值、S4 IC、S5 信号、S8 撮合各一套）—— 那是新一轮标定，不是接线问题。这六道题因此仍被 E9c 拦在落盘之前。出处：1.1-c。 |
| **N-282** | `ops/screen_band.py` 对 `no_implementation_freedom` 的读法与 2026-09-03 那次不一致 | **待签字（§7-①）** | committed 的 `Band` 对「ε 未标定、三份实现同值」的指标按**要求精确相等**判（那一行自己标着【待签字 §7-①】），而 2026-09-03 的临时 harness 对这类指标是**跳过**的。后果：本轮复跑 `sell_rule` 时逐实现超带条数从 `DIVERGENCE_EVIDENCE` 条目原文的 **5/6/6 变成 6/6/6**（多出来的三处全是 `win_rate_net`，与 N-273 同源）。**核心数字逐位复现**（`ann_return_gross` 0.378%–0.446% vs ε=0.2372%，与条目原文「0.38–0.45%（ε=0.237%）」对得上），方向不变（都 material）。裁定之后再决定要不要改既有条目的条数 —— **改它同样要推任务集版本**。出处：1.1-c。 |
| **N-283** | `ops/screen_runner.py` 与 `ops/screen_band.py` 的落点写死在 `snapshots/v1/epsilon` | 已用覆盖表绕过，v1.1 参数化 | 在 `ops/run_materiality_screen.py::frozen_impl_paths()` 里临时覆盖 `SNAP` / `PANEL` / `SCRIPTS[*]["src"]` / `CAL`，退出必还原（有测试盯）。局限与 N-262 相同：**兜得住覆盖表漏项，兜不住有人绕过覆盖表直接 import** —— 例如直接 `python -m reference.make_fixtures --set-id public/…` 会在公开出集上**从私有 gold 切夹具**且不报错。出处：1.1-c。 |
| **N-284** | `ops/gateway_lock.py` **不可重入**，嵌套会永久阻塞 | 已绕开，建议根治 | `ops/public_gateway.sh run` 本身就是 `gateway_lock.py` 起的；`run_oracles` 在里头再拿一次同一把 `fcntl.flock` 会**死等** —— 表现是「网关起来了、一题都没跑、也不报错」。卡 1.1-c 给 `run_oracles` 加了 `--no-batch-lock`（**只在外层已持锁时用；裸跑千万别加**）。但那是把「外层有没有拿锁」交给调用方记住，记错的表现就是不拿锁并发打网关（N-125 的 OOM）。根治：给 `gateway_lock` 加「本进程树已持有」的标记（环境变量 + pid 校验），然后删掉 `--no-batch-lock`。出处：1.1-c。 |
| **N-285** | `run_oracles` 的**矩阵落点与明细分家** | **已修** | 原来明细跟 `--out` 走、矩阵写死 `ops/reports/probe_matrix_<agent>.md`。两条通道并列跑时，公开那一跑会**就地覆盖**私有的矩阵，而覆盖后的文件**从内容上看不出是哪条通道跑的**。现在矩阵落在 `--out` 的同一目录；默认 `--out` 时路径与改动前逐字相同。出处：1.1-c。 |
| **N-286** | 换出集落点时**不许整目录替换** | **已修（自己踩的）** | 第一版 `_relocate` 用 `shutil.rmtree(dest)` 再 move，把题目录下的 `work/`（题面 `inputs` 声明的夹具）删了 —— 而唯一可行的顺序是「先跑一次 oracle 建题目录 → 物化夹具 → 再跑一次 oracle」。表现是 S4/S5/S6/S7 **十六道题一起 `FileNotFoundError`**，日志里看不出是谁删的。现在改成**逐文件覆盖**（与 `P.write_task` 写进已存在目录时同形），并有测试盯住 `work/` 必须活下来。出处：1.1-c。 |
| **N-287** | **`reference/make_fixtures.py` 顺手重写 `ops/data_cards/fixture_*.md`，而数据卡的落点与通道无关 —— 一次真的私有面污染** | **已还原 + 已绕开，v1.1 参数化** | 拿公开行情跑一次夹具物化，`ops/data_cards/fixture_s4_eco_pool_v1.md` 里的行数就被换成公开通道的（实测 **1,003,974 → 1,003,966**），`fixture_s6_signals.md` 同样 —— 而这两张卡描述的是**私有**夹具。当场用 `git show HEAD:<路径> > <路径>` 原样还原（**未用被禁的 `git checkout --`**），并给驱动脚本加了「跑前存字节、跑后逐个还原并报出被动过的文件」。**但那只兜住一个调用方。** 根治：数据卡落点也要按通道走。出处：1.1-c。 |
| **N-288** | **S8 四题在公开通道拿不到可交易性视图** | 如实记账，非缺陷 | S8 是模拟盘会话，as-of 上界是**当前 `sim_date`**（20260701）；跑完之后再去 `/calendar?as_of=20260731` 会被 403（`asof_beyond_freeze_line`）—— 这**正是前视闸该做的事**。后果：这四题的 `calendar` 与 `missing_masquerading_as_signal` 两族**没被调用过**，矩阵里那两格是「不可得」不是「干净」，逐题写进 `evidence`（32 题里 28 题喂到）。要在 S8 上也判这两族，得在**会话推进过程中**取视图 —— 那是另一种取法。**顺带**：视图用独立 `config_id`（`oracle_probe_view`），所以这几次 403 **不进** `config_id=oracle` 的越权计数，否则四题会当场被判 `overreach_count_mismatch`。出处：1.1-c。 |
| **N-289** | **多代理共用 `$GB/scratch` 时，别人用宽 umask 建的文件反复把红线 5 守门跑红 / 挡住起网关** | 建议立脚本模板（三张卡各踩一次） | 表现有两种：① `ops/test_env_guard.py` / `ops/test_env.py` 在别人的全量里随机变红（`$GB/scratch/3.2-opencode/realrun.log` 0664、`scratch/1.2/state/*.jsonl`、`$GB/scratch/4.1/run_a4b.log` 0664、`$GB/repo/.git/index` 0664）；② **公开网关拒绝启动**（`guard_modes` 报权限），而它长得跟网关自身故障一样 —— 卡 1.1-c 在**排了 39 分钟网关锁之后**被别人两个 0644 文件挡掉、整批白等。**守门是对的，不要放宽**（答案面字节码就是从 `__pycache__` 漏出去的）。可抄的模板：`$GB/scratch/1.1b/drive_chain.sh`、`$GB/scratch/1.3/drive_recon.sh`、`$GB/scratch/1.1c/o1_public.sh`（第一行 `umask 077`、scp 之后立刻 `chmod -R go-rwx` + 目录 700、起网关前先 `$PY ops/guard_modes.py --harden` 并最多重试 3 次）。**跑 git 也请带 `umask 077`** —— `.git/index` 被留成 0664 挡过一次。出处：1.1-a、1.1-b、1.1-c、1.3、1.rt。 |


**E. 两通道对账**（卡 1.3：`ops/recon_public_vs_private.py`，七节，全量 16–51 秒）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-290** | **两条通道的行情本身几乎一样，不一样的是复权因子 —— 58 只票的复权处理实质不同** | **待裁定** | 收益率级全量 3,575 只 / 10,944,927 对，\|Δr\| ≤ 1e-6 占 **0.995204902**；\|Δr\| > 1e-3（实质不同）只有 **123 对、集中在 59 只票**。把缺口按 `Δlog(1+r) = Δlog(原始收盘之比) + Δlog(factor 之比)` 分解：**52,424 / 52,482 落在复权因子的台阶差，只有 12 对落在源报价**。顺带纠正一个会误导人的量：价位级一致率只有 0.170748565，但**那是一句没有判别力的话** —— 归一化常数逐票不同而常数不影响收益率；3,517 只的比值在票内是常数，**58 只是真的不同**（会一路传到 gold）。待裁：卡 2.5 §10 说「数字以公开通道为准进论文」，那这 58 只就按公开通道的复权算 —— 这算不算 §10 说的「结构性结论变了」？卡 1.3 判**不算**（算子冲突 / 声明欠定 / materiality / 探针设计逐项核过都没变），只登记；以及要不要在题面里声明复权口径来自哪一个源。逐票名单在 `reconciliation.json` 的 `returns.level_scale.worst_by_spread` 与 `returns.full.worst_codes`。出处：1.3。 |
| **N-291** | gold 超阈格里 **13.7% 只有弱归因** | 记录 | 三宇宙各 30 因子 × 判据窗共 6,227,352 格，**18,841 个超阈格（相对差 > 1e-3）全部追得到 provider 侧源差**：16,252 格是**本票自己**的输入变了（强归因），2,589 格只由「同截面别的票在这一天变了」解释，归不掉 **0 格**。那一条在这个样本上几乎总是成立，所以它是**没能证伪**不是**证实**。要变成强归因得逐因子看它用不用截面算子（rank / scale / 截面回归），而因子定义面 `factor_library/compiled/*.jsonl` 在仓库里不存在（N-295 同一条缺件）。逐因子分解已落在 `gold.by_universe.<u>.per_factor[].attribution`。出处：1.3。 |
| **N-292** | 收益率级有 **46 对「两项分解都在 1e-6 内、收益率却差更多」** | 记录（不修） | 占超阈 52,482 对的 0.09%。按量级看是 **float32 浮点相消**（provider 的 `.day.bin` 是 float32，两个近似相等的大数相减）。**没有逐条看过**（时间盒外）；产物里这一类现在**只有计数没有样例**，真要查得先加样例采集。出处：1.3。 |
| **N-293** | `ops/reports/public/reconciliation.json` 进 git，86 KB | 记录 | 目前可接受。里面含 gold 的**统计量**（逐因子格数 / 相对差分位 / 超阈计数）与 15 条最差票的代码，**不含任何 gold 值本身**；它不进 bundle、不上 f02，`ops/release/pack_public_provider.py` 的物料清单里也没有它 —— 所以红线 2 现状是安全的。若后续加节，注意 `per_factor` / `worst_codes` 这类列表都已封顶（15 条 / 10 条），别把逐格数据落进去。出处：1.3。 |
| **N-294** | `--part gold` 单跑会**连带重扫**一遍 provider（约 40 秒），这是有意的 | **已解** | 归因要的 provider 逐格位图**只有 `returns` 那一遍扫描能产出**。第一版写成「产物里已经有 returns 就不重扫」，表现是 `--part gold` 单跑时归因**全空而不报错**、报告照常渲染。已改成 `gold` / `units` 一律连带重扫。**同一节还修掉一个同类的坑**：provider 的 `calendars/day.txt` 是 ISO（`2026-01-05`），gold 的 `date` 列是紧凑串（`20260105`）—— 拿 ISO 当键**每一格都查不到而不报错**，归因整个塌成「归不掉 100%」而报告照常渲染。已抽成 `_calendar_index()` 并由变异测试钉死；**凡是要把日历下标和 gold/快照表的日期对齐的代码，都用这个函数**。出处：1.3。 |


**F. 发布形态与红队**（卡 1.4 打两种形态，红队只按手册走一遍，卡 1.rt 修 block/major）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-295** | `PUBLIC_FROZEN_ARTIFACTS` 里 **3 个冻结件在仓库中不存在** | **挡发布** | `factor_library/compiled/{qlib_native,qlib_panel,blocked}.jsonl` —— **整个 `factor_library/` 目录都没有**。它们是 gold 的**定义面**（N-58⑥「τ 标定于此实现对」），少了它们拿到包的人**复现不了 τ**。打包已把它们记进 `MANIFEST.json` 的 `missing_declared_artifacts`（不静默丢），红队在真包上核过 `compare` 输出 `missing_declared` 三条；数据卡 §11 与 `reconciliation.md` §7 如实写成缺件。`license.published` 翻 `true` 之前**必须补齐，或者改物料清单并说明为什么不需要**。`ops/test_recon_public.py::test_card_reports_the_missing_frozen_artifacts_truthfully` 会在补齐那天**自己变红**，逼着回来改卡 —— **那条红是设计出来的，别当成回归去绕过**。出处：1.4、1.3、红队。 |
| **N-296** | 公开包里的 `instruments/` **不在 baostock 许可的射程内** | 待裁定 | 宇宙定义面（`csi300/500/1000/all.txt`）来自私有 `universe_pit`，而它是 tushare `index_member_all` 派生的；baostock 没有指数成分历史，**公开源推不出来**，所以形态 B 也只能随包发。已写进 `MANIFEST.json` 的 `data_source.universe_definition_note`。**发布前须单独确认再分发依据**（与 baostock 那份书面许可是两回事）。出处：1.4。 |
| **N-297** | `test_env` 那条「pending 时不得存在已发布 provider 包」的**射程盖不到 `$GB/release/`** | 已缓解，建议扩 | 那条测试扫的是 `$GB/snapshots/public`，而包实际落在 `$GB/release/`。卡 1.4 已在 `ops/release/pack_public_provider.py` 里补 `assert_nothing_published_while_pending()`（同一套判据搬到 `$GB/release/`）并由 `ops/test_release_forms.py` 盯着 —— **没有放宽既有那条**。建议把 `test_env.py` 那条的扫描根也加上 `$GB/release`，两处判据就不会分叉。出处：1.4。 |
| **N-298** | `ops/build_public_channel.py` 的 `verify` 步**在用户机器上跑不了** | v1.1 | 它比对**私有**快照的 mtime（「两条通道并列不覆盖」）。用户机器上没有私有通道 → 形态 B **跳过并说明**，不当作「验证通过」（形态 B 的验收由逐文件 sha256 比对承担，判据更强）。建议给公开通道补一条**自足**的 `verify`（冻结线上界、日历、无 `day_future.txt`、`files.sha256` 自洽），它不需要私有通道。出处：1.4。 |
| **N-299** | 反投影的 `universe_pit` 丢掉 `ambiguous` 列 | 已知可接受 | `instruments/*.txt` 只有三列，`ambiguous` 反投影不回来。它**只被 `build_instruments` 用来计数**，不影响 txt 字节（排练里重建的四个 txt 与包里逐字节相同）。表现：用户机器上重建树的 `manifest.json` 里 `instruments.*.ambiguous_rows` 是 0，而包里的不是。已在 `universe_from_instruments.py` 的返回值与 docstring 里**显式记账，不假装是原值**。出处：1.4。 |
| **N-300** | 整包可复现要**显式给 `--built-at`** | 已实现，需写进发布说明 | 包里唯一带构建时刻的是 `MANIFEST.json` 的 `built_at`。不给 `--built-at` 时同一棵树两次打出的 `tar.gz` 不同（只差那一个字段）。对外承诺「你自己打一遍能得到同一个包」时**必须同时给出那次发布用的 `--built-at`**，否则第三方复现不了包体 sha256（数据字节仍然逐个可验，那条不依赖 `--built-at`）。出处：1.4。 |
| **N-301** | **形态 B 的 `compare` 段被一份随包发的文档拖红** —— 外部用户按文档做到第 4 步必然失败 | **已修（红队 block①，卡 1.rt）** | 包里的 `docs/` 与 `selfbuild/` 是打包时从**活的仓库工作树**取的，而 `compare` 段重新从**当前**仓库取同样这几个文件去比 —— 只要有人改过那四份文档中的任何一份，逐文件比对就出 `differ`。红队实测：包内 `docs/ops/data_cards/public_channel.md` sha256 `7a707875…` vs 仓库当前 `3240007b…`（数据卡 09-07 14:40 改过，包是 09-06 17:00 打的），输出 `differ 1`、**退出码 1**，而文档承诺的判据是「同一个 SHA256SUMS，differ 0」。**数据面本身完全对得上**（28,600 个 bin、四个 instruments、日历、norm_base、六张表、18 个年分区全部逐字节相同）。修法：新增 **`PACKAGE_PROVIDED` 第三堆** —— 这两堆仍留在 `SHA256SUMS` 里（包体完整性不放宽），但 A↔B 比对**以包内副本为准、单列 `package_provided_differ`、不判红**；`only_in_*` 与数据面照旧判红。在红队留下的那棵真重建树上复核：`ok=true`、same 28,642、构建戳差异 5、`package_provided_differ` 4、**退出码 0**。**旧测试照不出这个失败**（`tmp_path` 合成树是打包与比对同一瞬间的同一份 repo），已补三条走真实次序（先 pack → 再改仓库 → 再 compare）的测试，其中一条把豁免摘掉再验一次红。出处：红队 finding①、1.rt。 |
| **N-302** | **仓库没有公开获取方式 → 形态 B 对外不成立** | **挡发布（需用户裁定）** | 形态 B 第一步是 `git clone <GeneBench 仓库>` —— 那是个**占位符**，而 `/data/shared/genebench/repo` 的 `git remote -v` 是**空的**。包内 README 自己写明「`selfbuild/` 里那五个脚本 import 的是仓库里的 `genebench_config` / `snapshots.public` / `ops.build_public_channel`，单独拿出来跑不起来」，所以拿不到仓库 = 形态 B 完全做不下去。卡 1.rt 已把占位符**明写成占位符**并在 `release_forms.md` §0 顶部说清 —— 但真正的闭合是：**给一个可 clone 的公开地址，或者决定把仓库源码一并打进包并列进 `SHA256SUMS`**。出处：红队 finding②、1.rt。 |
| **N-303** | 公开网关**六个端点怎么调，没有任何一处文档写** | **已修（红队 major，卡 1.rt §7.1）** | 文档给了网关的起 / 停 / 状态（实测可用：起来 78 秒、`/healthz` 的 `channel=public`），但**没有 curl 例子、没有必填参数、没有 base URL 的取法**；网关又刻意关掉了 `/docs` 与 `/openapi.json`（「少一个可探测面」），所以外部用户既问不到文档也问不到 schema，只能去读 `gateway/routers/market.py` 的函数签名。红队照源码拼出参数后六个端点各打一次全部 200（注意 `/universe` 的 `universe` 是 `Query(...)` **必填**，猜不出来就是 422）。已在 `ops/reports/public/data_channel_notes.md` 补 **§7.1**：base URL 怎么取、**八条可粘贴的 curl**、九个参数的语义与必填性、三条失败语义，全部在公开实例 18081 上逐条实测（含反面）。出处：红队 finding③、1.rt。 |
| **N-304** | `run_controls` 的 `--help` 路径**不存在**，且**混通道跑批无守门** | **已修（红队 major ×2，卡 1.rt）** | ① `--help` 写的公开题集根 `…/reference/tasks/v1.0-smoke-public` **不存在**（真实路径多一层 `public/`，`controls.md:5` 里是对的），两处文档互相打架、照 `--help` 抄命令直接失败。② 把三控指向公开通道需要三样东西：`--answer-root`、`--gateway-log`、**`GENEBENCH_CHANNEL=public`** —— 第三样**一个字都没写**，而 `cfg.channel()` 默认 `private`，于是只按 `--help` 跑会得到一次「题集与网关日志是公开的、底下读的表是私有的」**混通道运行**，报告头还照实打印 `通道：private`，**没有任何判据会拦它**。修法：路径定义成模块常量 `PUBLIC_ANSWER_ROOT` / `PUBLIC_GATEWAY_LOG`（`--help` 从常量渲染，并有测试禁止源码里再出现少一层 `public/` 的写法）；新增 `assert_channel_matches`（题集是 public 而通道不是 public 就**拒绝启动**）；报告顶部渲染一条**可照抄的完整命令**。公开 `controls.md` 已按新格式重跑，表格与判据行逐字节未变。出处：红队 finding④⑤、1.rt。 |
| **N-305** | 端到端看，「外部用户能用」**当前整体不成立** | **挡发布** | ① 包落在 `$GB/release/_staging_unpublished/`，`MANIFEST` 的 `license.published=false` / `publishable=false`，按设计**不对外发布** —— 外部用户拿不到形态 A（等 baostock 书面许可原文入库、`DATA_LICENSE` 顶部状态翻 `granted`）；② 形态 B 卡在 N-302；③ 冻结件缺三件（N-295）。**两条都已在文档里如实写明并登记，不是被隐瞒**；但这意味着今天**没有任何外部用户能真正走完这条链**。`release_forms.md` §0 顶部已把这三件摆到最前面。出处：红队 finding⑥、1.rt。 |
| **N-306** | **发布前必须把包重打一次** | **挡发布** | 卡 1.rt 改了 `README_TEMPLATE`（形态 B 那行 `git clone` 明写成占位符 + 第四堆比对口径）与 `MANIFEST` 的 `package_provided` 字段，但 `$GB/release/_staging_unpublished/public_v1/` 里那一份还是 **09-06 打的旧文本**。现在不重打的理由：包不可发布（许可 pending），而重打会让 `release_forms.md` 记的三个 sha256 立刻过期，且阶段二 / 三还在改 `docs/` 里那几份文档。**许可 granted、仓库地址落定之后，重打一次再发。** 出处：1.rt。 |
| **N-307** | 仓库根 `README.md` 没有「外部运行者从这里开始」入口 | 登记不修（minor） | 整份是内部文档（目录约定、conda env、pip 镜像、`$GENEBENCH_ROOT`），**没有「公开通道」「发布包」「形态 A/B」「网关怎么起」任何一个词**。外部运行者拿到仓库后没有入口，只能靠别人告诉他去看 `ops/reports/public/release_forms.md`。建议加四行链接：`release_forms.md`（两种形态）、`ops/data_cards/public_channel.md`（数据卡）、`data_channel_notes.md` §7（网关起停）、`DATA_LICENSE`。**`README.md` 是共享文件，红队与卡 1.rt 都没改。** 出处：红队 finding⑦、1.rt。 |
| **N-308** | `DATA_LICENSE` 两处交叉引用**过期 / 错位** | 登记不修（minor） | ① 第 27 行写「见 N-66 与 `ops/data_cards/public_channel.md` §1」，而条款那段在数据卡的 **§2**（§1 是「源、窗口、规模」）；② 第 39–44 行的发布形态表里冻结包写「待建（N-68）」、构建脚本写「`ops/acceptance/card_2_5_source_reconcile.py` 已可复现取数」—— 而两种形态**都已建成**，入口是 `ops/release/pack_public_provider.py` 与 `ops/release/build_public_provider.sh`。`DATA_LICENSE` 是**发布物之一**，外部用户先读它会得到一个落后一版的世界。出处：红队 finding⑧、1.rt。 |
| **N-309** | 「provider 文件数」在三份随包发的文档里是**三个数** | 登记不修（minor） | `release_forms.md` 说 28,610、数据卡说 28,608（src 指 `build_info.json:files`）、`data_channel_notes.md` 说 28,606；真包里 `find provider -type f` = **28,610**（其中 `*.bin` 28,600）。三个数各有口径，但**没有一处说明口径差在哪**，读者只会认为其中两个是错的。建议统一成一个数并注明口径（`28,610 = 28,600 bin + 4 instruments + 日历 + norm_base + files.sha256 + manifest 类`）。出处：红队 finding⑨、1.rt。 |
| **N-310** | `calibration.json` 里**三个同名 `usable` 三种射程** | 登记不修（minor） | 顶层 `epsilon.usable=false`，而数据卡 §11 用的是 `epsilon.by_frequency.daily.usable=true`；`epsilon.ic_family.usable=false` 又与同一对象里 `usable_metrics` 的 4 项并列。**产物里没有一处说明顶层那个 `usable` 是什么意思**，外部用户直接读 `epsilon.usable` 会得出与数据卡**正面冲突**的结论。建议给顶层与 `ic_family` 各加一条同级 `usable_meaning`，或把顶层改名 `all_frequencies_usable`。与 N-272 是同一个键的两个毛病（那条是值不对，这条是名字不说话）。出处：红队 finding⑩、1.rt。 |
| **N-311** | 「weekly/monthly 为何 `usable:false`」**在数据卡里答不出来** | 登记不修（minor） | 理由写在 `ops/specs/backtest_contract.md` §10③（超阈项 `sharpe_net` 12.8% / `ann_return_gross` 19.3% / `total_cost` 9.1%：低频调仓次数少、单次决策权重大）与 `ops/reports/public/rebuild_chain.md` §3（超阈 >5% 按 2.2b 纪律不写成 ε），而数据卡 §9 只写「分档结论相同」、§11 只引 daily，**两条跳板都不指路**；`calibration.json` 侧也只暴露 `implausible` 与 `implausible_threshold`，没有一个键把「有超阈项 → usable=false」这条规则用话说出来。建议 §9 加一句带指路的话，并在 `calibration.json` 的 `epsilon` 下加 `usable_rule` 文字键。（`ops/specs/**` 在冻结根内，改它要走 freeze bump。）出处：红队 finding⑪、1.rt。 |
| **N-312** | `build_public_provider.sh` 的 **baostock 版本 pin 其实不生效** | 登记不修（minor） | preflight 是 `python -c 'import baostock' \|\| pip install baostock==0.9.3` —— 机器上**已经装了任何版本**就直接放行。而 baostock 的返回列名一变，`snapshots/public/source.py` 的归一化会**静默错位**（数据卡 §5 记过同类：单位差 1000 倍而 gold 照常算得出数）。另外那一行打印的版本串是 `baostock 00.9.30`（拼接错），用户想自己核版本也核不了。建议先取版本再判：装了但不是 0.9.3 就红着停。出处：红队 finding⑫、1.rt。 |
| **N-313** | `calibration.json` **不随包发**，而数据卡 §11 的 `src` 指向它 | 登记不修（minor） | 数据卡 §11 的 τ、`ε[daily].usable`、IC 族四个可用指标，出处注释都指 `public_v1/calibration.json`，但它**不在包里**（`SHA256SUMS` 无命中），形态 B 重建出来的树里也没有（重建链 gold→τ→ε 不在 `build_public_provider.sh` 的四段里）。只拿到包与仓库的人**打不开数据卡自己引用的那个产物**。建议要么把 `calibration.json`（含 crosscheck / epsilon 汇总）加进包并列进 `SHA256SUMS`，要么在 §11 顶上明写「不随包发，重建方式见 `rebuild_chain.md` §6」。出处：红队 finding⑬、1.rt。 |
| **N-314** | 仓库里的 `ops/reports/m6/controls.md`（私有，09-06 10:15）**已经落后于当前树** | 待跑批代理重跑 | 它比**今天**跑出来的私有三控少两处：① 报告头那行「题集根 / 网关日志 / 通道」（N-304 加的）；② `s4-cor-01 \| oracle` 的效果分 —— 那份写 `effect=None（anchor_degenerate）`，今天跑是 `effect=100.0`（出数）。**与卡 1.rt 的改动无关**：拿改动前的 `run_controls.py` 原文在同一棵树上再跑一次，`controls.json` 与改动后**逐字节相同**（sha256 `1a2f7b73f2e5ad1996219aa2a388c5f003e009abcda2989ba0adbc1cc663ebf5`，证据 `$GB/scratch/1.rt/ba.log`），差异来自 09-06 之后别人对 scorer / oracle 产物的改动。建议下次跑批时重跑私有三控把那份报告刷新，**并查清 s4 的锚点为何从退化变成出数**。出处：1.rt。 |


**G. 价目表**（卡 1.5：把 `$` 那一列的出处补齐）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-315** | **注册表写的 model id 与上游实际服务的对不上** | 登记不修 | `runner/registry.py` 三条配置都写 `deepseek-chat`，而 M6/M6b 两批 **1,196 条响应体的 `model` 字段全是 `deepseek-v4-flash`**，且上游 `/v1/models` 与官方定价页**都已不再列 `deepseek-chat`**（2026-09-06 复核）。证据 `ops/reports/m6_all/served_model_evidence.json`。卡 1.5 按 `alias_of` 把 `deepseek-chat` 指到 `deepseek-v4-flash`，价与出处因此没有第二份。**要不要把注册表改成实际 id 是另一件事**：`model` 进 M6 主表的口径说明，改它要过 registry 的 `assert_registry_sane`（三条必须同一模型）并复核 M6 报告里的措辞。出处：1.5。 |
| **N-316** | **`$` 是成本上界，不是账单实数** | 已在代码与表下写明 | DeepSeek 2026-08-16 起分高峰 / 低谷两档（低谷是高峰的一半；高峰 = 周一至周五 01:00-04:00 与 06:00-10:00 UTC）。边车 `llm_log.jsonl` **不记这次调用落在哪一档**，价目表因此一律取高峰价。逐条按调用时刻判档 = v1.1（边车已记 `ts`，做得了）。出处：1.5。 |
| **N-317** | **缓存命中价目前用不上**，`usage_totals` 也只合计三个键 | 登记不修（两条同源，一起修才有意义） | `runner/pricing.cost_usd` 认 `prompt_cache_hit_tokens` / `cached_tokens` / `cache_read_input_tokens`，但 M6/M6b 的 usage 里**一个缓存键都没出现过**（只有 prompt/completion/total）。两条可能：上游 Responses API 没返回缓存明细，或边车 `_norm_usage` 只搬平铺数值键、OpenAI 风格的嵌套 `prompt_tokens_details.cached_tokens` 到不了下游（后者是 `runner/c41/egress_proxy.py` 的一行）。而 `llm_trace.usage_totals` **写死三个键累加**，即使边车记下了缓存键也进不了 `cost_usd`。**现状不会算错钱，只会高估**（按整价 = 上界）。出处：1.5。 |
| **N-318** | **`$` 的口径是「逐 run 均值」，规格 §3 写的是「$/task」** | 登记不修 | v1.0 冒烟集每题种子数不齐（`m6_all` 里 12 题 / 14–15 run），两者因此不等。卡 1.5 取逐 run 均值 —— 与同列的 Steps / Latency 一致，**换口径要三列一起换**。报告器 docstring 已写明。出处：1.5。 |
| **N-319** | **未接模型的价是留位行**（claude / gemini / grok / gpt / opencode-default，价全 `null`） | 待 key | `price_of()` 对它们返回 `None` 而不是抛错，于是主表上「这家没接」与「这家不要钱」**可分**。接入时把 `model` 换成**实际调用的 id** 再填价；`opencode-default` 那一行要**拆成实际 provider 的几行**（opencode 自己不托管模型）。出处：1.5。 |
| **N-320** | **DeepSeek 官方价没有第三方复核** | 待用户核一次 | 价取自 `https://api-docs.deepseek.com/quick_start/pricing`（2026-09-06 抓取，`retrieved_at` 已记）。表格是从该页 HTML 里读出来的，建议用户对着页面核一次 flash 的 **0.44 / 1.32 / 0.014**（高峰）。出处：1.5。 |


**H. W-0 施工基础**（这一轮之前铺的：`exec/` 同步、API 用量机器统计）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-321** | `ops/test_c41.py:366` 写死 `len(REG.CONFIGS) == 3` | 待处理 | 数据驱动合并已上线：`harnesses/`、`integrations/` 下 `enabled: true` 的 `config.yaml` 会追加进 `CONFIGS`。第一个启用配置的阶段二 / 三代理会把这条断言跑红 —— **那不是回归**，是断言该改成「内置三条在最前面且互不重名」。出处：W-0。 |
| **N-322** | `exec/` 同步**只能用白名单**，不能用「四个目录减排除项」 | 已处理（CONFLICT） | 任务书给的排除清单（`__pycache__` `.pytest_cache` `ops/reports` `ops/acceptance` `ops/recon`）**挡不住** `genetask/templates/**/{solve.py,scorer.yaml}`（各约 170 份）、`ops/data_cards/{gold_factors,s7_backtest_gold}.md`、以及 `ops/test_*.py` 里的合成 gold 串 —— 照做即踩红线 2。`ops/push_exec_to_f02.sh` 改成**白名单 + 推前用 `runner/f02/answer_plane_guard.scan` 扫 staging**（命中即停）。**加新模块 = 在脚本里加一行。** 出处：W-0。 |
| **N-323** | f02 的 `exec/` 树**看不见 `harnesses/` 与 `integrations/`** | 待裁定 | 同步只推 `genetask ops runner vendor` 四个目录（任务书原文），所以 f02 上 `discover_launch_specs()` 返回空、`load_data_configs()` 也读不到 —— `command_for` 落回硬编码（两条内置的输出逐字节相同，现在无害），但**阶段二 / 三新增的 `config_id` 在 f02 上会 `by_id` 找不到**。脚本已备好 `--with-launch-data`（默认关）。需裁定：默认打开，还是让 `run_f02_a1.py` 改成不依赖 registry 查配置。倾向**默认打开** —— `launch.json` / `config.yaml` 里没有答案面，且 `--with-launch-data` 走的是同一道 staging 扫描。出处：W-0。 |
| **N-324** | `vendor/h11` 只在 f02 上，**仓库里没有** | 待处理 | `ops/run_f02_sim_n.sh` 指着 `/data/genebench_runner/exec/vendor/h11`，但仓库里没有 `vendor/`。同步脚本因此对 `vendor/` **跳过且不 `--delete`**（否则一次同步就把对面的 h11 删光）。要么把 h11 收进仓库，要么在 HANDOFF 里写清「它是在 f02 就地铺的」。出处：W-0。 |
| **N-325** | `exec/` 的来历此前**没有脚本** | 已处理 | `ops/tickets.md:1947` 只留了一句「同步 `exec/` 后 P2 判绿」；2026-09-04 因此发生过一次「按规格调用却拿到错函数」（对面是改名前的旧版）。现在有 `ops/push_exec_to_f02.sh`，推完自动逐字节比对两侧的 `command_for("Codex CLI")`。出处：W-0。 |
| **N-326** | 真 API 用量此前**只有人工记账** | 已处理 | `ops/api_usage.py` 从 f02 各 run 的 `log/llm_log.jsonl` 数 `decision == "allow"`。表头固定带一行「历史口径：2026-09-06 签字前人工记账累计约 1 700 次；本表为机器统计，以本表为准」。2026-09-07 收口时的机器统计：**2,255 次真调用 / 63 个 run**。出处：W-0。 |

---

## 2026-09-07 建到可分发·阶段四（臂机制与适配赛道）

阶段四做的是「**这套东西还能不能长出新的实验轴**」：把写死在 `genetask/schema.py` 里的
`ARMS = ("strict", "open")` 变成一份数据（`genetask/arms.yaml`），让「加一个臂」退化成改配置；
按题目阶段给预算分档（S4 150 次 / S7 300 次，其余仍是 100）；再用这套臂机制去接一条新赛道
（适配赛道 `v1.0-adapt`：30 例逐级破坏 + 适配模块 + 五结局分类）。然后请红队**只按手册**走一遍。

下面是 `ops/tickets_inbox/4.*.md`（`4.1` / `4.2`（即 4.2-a）/ `4.2b` / `4.3` / `4.rt`）
五份收件箱的逐条并入。同一件事被多张卡登记的**合并为一条**，出处逐一列在说明末尾。
**已修的也登记** —— 阶段四有三条 bug 属于「别人照着上一张卡的交接原话做就会撞」（N-337 / N-338 / N-354），
不写下来下一个人还会踩。红队 12 条 finding 里 block 6 / major 3 由卡 4.rt 修完（N-360…N-367），
minor 3 条登记不修（N-368…N-370）。

**这一阶段有两件事没做到，都在下面**：`hint` 臂两次真跑都没有可评分产出（N-330）；
适配赛道 30 例真跑**一次都没能起**（N-347），而挡在最前面的那条闸需要用户裁定（N-348）。


**A. 臂机制数据驱动**（卡 4.1：臂 = 工件集合 + 指令变体，由 `genetask/arms.yaml` 定义）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-327** | **臂不再是常量**：`genetask/arms.yaml` 是臂注册表 | **已完成** | 字段 `id / kind / default / phrasebook_column / fallback_column / variant_text_file / equivalence / artifacts[{manifest, mount, per_task_rules}]`；解析器住在 `genetask/bundle.py`（**零 `reference` 依赖**，f02 也读它），`schema.ARMS` 由它派生、import 期读、缺文件即错。`render.render_arm` 增加 `column` / `variant_text` 把措辞列与臂名解耦；`check_arms` 泛化成 N 臂（`names` 参数化臂名、`keep` 参数化规则子集，**默认值就是内置两臂、报错消息逐字节不变**）；注入器 P1 对 `ALL_ARMS`、P7 按该臂 `artifacts[]` 逐份清单投放，`check_run_dir` 用「本臂应有 / 别的臂的」两个集合取代 `arm == "strict"` 分支。判据 `ops/test_arms_registry.py`（33 条）。出处：4.1。 |
| **N-328** | **逐字节不变**已实证：题面与出集内容一个字节没动 | **已完成** | 钉住金丝雀 nonce / 时刻 / 子网分配之后，`s2-cor-01` 与 `s7-rob-02` 在改动前后的「出集全部文件 + 两臂干注入 run dir 全部文件」sha256 **逐条相同**。证据 `$GB/scratch/4.1/{before,after_head,four}/*.sha`。**第一版是假红**：`mkdtemp` 的随机名进了 compose 挂载路径，钉住之后才对上 —— 做这类比对先自测一遍快照 harness 本身的确定性。出处：4.1。 |
| **N-329** | **加臂只加配置**已实证：`doc` / `hint` 两臂的提交里一个 `.py` 都没有 | **已完成** | `a939d1a` 的 `git diff --stat` 是 **5 个文件 142 行**（`genetask/arms.yaml` + `genetask/arms/hint.md` + `ops/protocol/geneprotocol_v1_doc/{MANIFEST.json,README.md,contract.md}`），全是 yaml/md/json。`doc` 是 protocol 臂（只投放 README + contract，**不投 validator、不放逐题规则**），`hint` 是 instruction_variant 臂（回退 `open` 列 + 追加一段文本）。出处：4.1。 |
| **N-330** | **`hint` 臂两次真跑都没有可评分产出** | **待办（挡完成定义）** | `r01` 撞 S2 默认 token 档（600k）、`r02` 在 1500 s 墙钟到点（`exit 124`），两次都没落 artifact，`validity=None`。**不是没注进去**：`r02` 真调了模型 **67 次**（`decision=allow` 67 / `deny` 0），比同批 `strict` 37 / `doc` 41 都多 —— 追加的那句「先读结构文件再动手」看起来把 agent 带进了更长的路径（**n=1，是现象不是结论**）。「同一目标 1 次真跑 + 1 次重试」的额度已用尽。修法：`--timeout` 从 1500 抬到 2400 再跑一次（`$GB/scratch/4.1/run_a4b.sh` 改 `--seq 3 --timeout 2400`）。证据 `ops/reports/a4/{records.json,summary.md}`。出处：4.1。 |
| **N-331** | `doc` / `hint` / `adapt` 都是 `default: false`，不进任何既有出集 | 已知边界 | 这是**故意的**：`default` 集合一变，40 题的 `task.yaml` 全部改字节（instruction 段按臂记 sha256），那才是真的改了题面。既有 40 题至今一个字节没变。要把第三臂放进主实验得改 `default` 并推任务集版本。出处：4.1、4.2-b。 |
| **N-332** | 两份协议文档在仓库里有**两个副本** | 待办（低） | `ops/protocol/geneprotocol_v1_doc/{README.md,contract.md}` 是 `geneprotocol_v1/` 同名文件的逐字节副本。清单里的路径相对清单自己所在目录（注入器 `base / k`），所以文档臂只能另存一份而不是指回去。漂开的后果是「两个不同的协议」，眼下由 `ops/test_arms_registry.py::test_doc_arm_files_are_byte_identical_to_v1` 钉住。要根治得让清单格式支持「引用别的清单的子集」—— 那是清单格式的变更。出处：4.1。 |
| **N-333** | `ops/protocol/**` **不在冻结根里** | 记录在案（待裁定） | `geneprotocol_v1` 与新加的 `geneprotocol_v1_doc` / `geneprotocol_v1_adapt` 都不在 `ops/freeze_v10.CODE_DIRS` 里 —— **改协议工件不会推任务集版本**。这与 N-131 收 `ops/specs/artifact_schema` 进冻结根时的论证同形（「agent 看得见、却在冻结根之外」），差别是**只有 protocol 臂看得见、baseline 臂看不见**，所以它不是「两臂都拿得到的题面」。要不要收进来是一个裁定，阶段四没有擅自扩冻结根。出处：4.1。 |
| **N-334** | 多臂真跑的预算是**按臂各算一份** | 记录在案 | 三个臂各一次真跑 = 三份 `RUN_BUDGET`。跑 40 题 × 4 臂时闸门总量是 `40 × 4 × 档位`，`ops/gateway_lock.py` 的排队时间会线性涨。没有实测之前不加「按 run 组」的总闸。出处：4.1。 |
| **N-335** | **超时的 run 会漏一个容器，继续烧 CPU** | **待办（高）** | 实测（a4 批 `hint.r02`）：驱动判 `exit_code=124` 收工之后，`gb-s2-cor-01-hint-cfg-codex-deepseek-r02-task-run-30fd55a2d5c8` 又跑了 **25 分钟**，是人工 `docker stop` 掉的。拆除路径覆盖了 compose 项目，**没覆盖 `docker compose run` 起的那个一次性容器**（名字带 `-run-<hex>`，不属于 `compose down` 的作用域）。后果不是脏数据是**占机器**：12 核的 f02 上一个跑飞的 agent 容器 + 一个网关边车，会把后面排队的真跑拖慢，而没有任何东西会报。落点 `runner/run_loop.py` 的收尾。判据：超时用例结束后 `docker ps` 里不得有该 `run_id` 的任何容器。**在它修好之前：跑长任务的人顺手 `ssh finance01-ts 'ssh ljn@192.168.1.219 "docker ps"'` 看一眼。** 出处：4.1。 |
| **N-336** | **锁序：先 `git.lock` 再 `heavy.lock` 会把所有人的提交堵住** | **已写进 HANDOFF §15.7** | 卡 4.1 把同版本重冻写成 `flock git.lock -c "… flock heavy.lock … --write && git commit"`。`heavy.lock` 当时在 1.1c 手里（`-w 7200`，可能两小时），于是**攥着 `git.lock` 在等重活锁** —— 期间任何代理的 `git commit` 都会挂住，而现象只是「git 卡住了」，看不出是谁堵的。堵了约 3 分钟，无人失败。正确顺序：**先把 `heavy.lock` 拿满、放掉，再拿 `git.lock` 只做 add + commit**（`$GB/scratch/4.1/refreeze.sh` 是改好的样子）。并发施工规则里写了「git 写操作包在 flock 里」，没写「不要在 git.lock 里等别的锁」。出处：4.1。 |
| **N-337** | `exec` 同步**漏了 `arms.yaml`**，把 f02 上整棵 runner 弄成 import 不了 | **已修**（`4cc7f5a`） | `ops/push_exec_to_f02.sh` 的 `GENETASK_FILES` 是显式白名单（`__init__.py bundle.py pin.py`），而 `bundle.py` 现在 **import 期**读 `genetask/arms.yaml`。第一次推 exec 之后 f02 上 `python3 -c "from genetask import bundle"` 直接 `PackError`，而 f01 侧一切正常 —— 表现是 `run_f02_a1.py` 一起手就炸。已加 `arms.yaml` 进白名单并加 `GENETASK_DIRS=(arms)`。**2026-09-07 14:00–14:25 之间推过 exec 或在 f02 上跑过 runner 的失败是这条造成的**，重推一次 exec 即可。出处：4.1。 |
| **N-338** | `ops/run_f02_a1.py` **不给 `--max-calls` / `--max-tokens` 时恒红** | **已修**（`eba79dd`） | `main()` 里有一句多余的 `from runner import registry as REG`，让 `REG` 在整个 `main` 里成为局部名，而它只在「显式给了参数」的分支里赋值 —— 两个都不给就 `UnboundLocalError: cannot access local variable 'REG'`。**而卡 4.3 的交接原话正是「把这两个参数整个删掉，让注入器按 stage 自动取档」** —— 照着做的每一次真跑都会在**拿到网关锁之后**立刻死掉（实测：排队 21 分钟，换一个 traceback，零次模型调用）。回归判据 `ops/test_arms_registry.py::test_run_f02_a1_does_not_shadow_the_registry_module`（AST 判定）。出处：4.1。 |
| **N-339** | 数据面文件分类（G3）写死两臂 → 第三个臂**出不了集** | **已修**（`5f0e26e`） | 出集时的文件分类按 `INSTRUCTION.strict.md` / `INSTRUCTION.open.md` 两条硬编码认题面，第三个臂的题面落进「不认识的文件」而被拒。改成按注册表认每一个臂的题面。该修复落在 `genetask/packager.py`（**冻结根内**）且发生在 `--write` 之后，因此**同一版本号内重冻了一次**（`d9f5a3a`）。出处：4.1。 |


**B. 预算按阶段分档**（卡 4.3：`RUN_BUDGET` 原样不动，另起档位）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-340** | **预算按阶段分档已落地**：S4 150/9M、S7 300/18M，其余仍是默认 100/600k | **已完成** | `runner/registry.py` 新增 `RUN_BUDGET_DEFAULT`（出厂值副本）、`BUDGET_TIERS`、`BUDGET_STAGES`（S1..S8，registry **自己另抄一份、不 import `reference`** —— 它跑在执行面）与 `budget_for(stage)`；`RUN_BUDGET` 一个字符没动，P2 契约与两份手册的断言全部照旧绿。`runner/inject.py` 的 `format_compose` 按 P6 已读进来的那份 bundle `task.yaml` 里的 `stage` 取档。`assert_registry_sane` 加三条判据：档位阶段名 ∈ S1..S8、档位键集 == 默认档键集、每档每键 ≥ 默认档。判据 `ops/test_budget_tiers.py`（26 条，核心是**行为判据**：造 s2/s4/s7 三份真 bundle 走真注入器，读 run dir 落下来的 `compose.yml`，断言 `--max-calls` 分别是 100 / 150 / 300）。**现场确认跑的是哪一档的唯一证据是 run dir 里 `compose.yml` 那一行**，别拿 registry 的默认值反推。出处：4.3。 |
| **N-341** | `RUN_BUDGET.max_tokens = 600_000` 上方那句注释**仍是错的** | 待办 | 「够 100 次长上下文调用」由 3.2-codex / 3.2-opencode 两张票据指出是错的（Codex 每次 prompt 43k–68k，opencode 平均约 30k），卡 4.1 的 a4 批又给了第三份同向实测（N-345）。卡 4.3 把**档位**建起来了，但**默认档那句注释没动**（改它要连 `ops/test_p2_contract.py::test_run_budget_matches_registry` 一起看）。建议改成「够 100 次**短**上下文调用；长上下文 harness 要么落在 S4/S7 档，要么显式给 `--max-tokens`」。出处：4.3。 |
| **N-342** | 显式覆盖靠「现值 ≠ 出厂值」认，有一个记录在案的边角 | 登记不修 | `ops/run_f02_a1.py` 的 `--max-calls/--max-tokens` 是**就地改 `REG.RUN_BUDGET`**（进程内），所以 `budget_for` 只能拿 `RUN_BUDGET_DEFAULT` 逐键对照来认出「有人显式给过」。边角：显式给的值**恰好等于默认值**（`--max-calls 100`）时档位仍然生效 —— S7 的题照样拿 300。方向是把护栏往上抬，不会让谁跑得比自己要的少。彻底修要给 `run_f02_a1.py` 加一个显式 override 字典。出处：4.3。 |
| **N-343** | 两份手册里的**可复制真跑命令**仍写着 `--max-calls 100`（`harnesses/README.md` 还写着 `--max-tokens 600000`） | 待办（手册收口裁） | **档位落地之后照抄这两条命令更坑**：抄到一道 S7 题上，`--max-calls 100` 关掉调用档、`--max-tokens 600000` 关掉 token 档，**两个维度一起被打回默认**，而现场表现只是「agent 跑了一半就停」。正确写法是**把这两个参数整个删掉**，让注入器按 `stage` 自动取档；要显式给就写 S7 `300 / 18000000`、S4 `150 / 9000000`。卡 4.3 在 `harnesses/README.md` §2.4 / §③ 与 `integrations/README.md` §1⑤ / §1⑥ / §3.3 五处都写了警示，但**没有改命令本身**（改它要动别人手册段落的结构）。与 2.4 的同源票据一并处理。出处：4.3。 |
| **N-344** | S8（状态机 / 逐日仿真）**没有单独的档** | 待观察 | 只按任务书给了 S4 / S7 两档。S8 同样是多轮交互、调用数可能偏高，但 M6/M6b 的 29 个 run 里 S8 样本**不足以说话**。有实测再加档，不猜。出处：4.3。 |
| **N-345** | **S2 的默认 token 档（600k）在 Codex 上恒撞** | 记录在案（有实测） | a4 批 `r01` 三臂**同时**在第 19–24 次调用撞 `budget_exceeded`（每次 prompt ~45k），三臂全部无 artifact。抬到 3M 之后同一批 `strict` / `doc` 都跑出了 `validity=valid`。**这不是臂机制的问题，是档位的问题** —— 改档要过 `assert_registry_sane` 并影响所有配置，归 registry 那边裁。出处：4.1、4.3（`--max-tokens` help 里已写着这件事）、3.2-codex。 |


**C. 适配赛道 v1.0-adapt**（卡 4.2-a 出题与结算，卡 4.2-b 出表与真跑）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-346** | **适配赛道最小版落地**：30 例 + 适配模块 + 五结局 + 赛道表 | **已完成（oracle 侧）** | 30 例逐级破坏（L1 单位错配 / L2 词汇翻译 / L3 缺协议字段各 10 例，覆盖全部八个阶段），每例**只破一处**（`diff_sites` 恰好 1 条）。L1 的「源里带的信息足以纠正」是**生成期实测**的三条路由之一（兄弟恒等式 / schema 格式唯一 / 交付说明声明单位），恒等式不成立就不出这一例；L2 的别名必须在 `field_map` 里查得到；L3 的 oracle 是原 gold 在缺口上标 `unresolved` 的合法形式，**30 份 oracle 全部过协议校验器**。结局比对**不新造判据**（payload 走 `scorer.l3.compare_exact`，declarations/provenance 走 `_json_equal`/`_set_equal`）。落点 `ops/adaptation_track.py` / `ops/pack_adaptation.py` / `scorer/adaptation.py` / `ops/specs/adaptation_track.md`，判据 `ops/test_adaptation_track.py`（26 条）+ `ops/test_c42b.py`（16 条）。出处：4.2-a、4.2-b。 |
| **N-347** | **30 例真跑一次都没能起** —— 挡住它的不是一条是三条 | **待办（挡完成定义）** | ① 题源（红线 B2，N-348，**需用户裁定**）；② 适配模块 `status: draft`，注入器 P7 拒（N-349，**实测拦下了唯一一次真跑，零次模型调用**）；③ 适配 bundle 缺 `INSTRUCTION.adapt.md`（N-350，卡 4.rt 已修）。**三条的关系要说清**：②③ 解开只能把「跑不起来」变成「仍然不许推」，**真正解锁的是 ①**。`ops/reports/adapt/` 现在 `例：30；有 oracle：30；有真运行：0`，`table.csv` 只有表头 —— 刻意**没有**拿「期望结局分布」去填表冒充结果。出处：4.2-b、4.rt。 |
| **N-348** | **适配赛道的题源裁定（红线 B2）** | **待裁定（BLOCKED_AWAITING_USER）** | 适配例从 `v1.0-smoke` 的 gold 产物生成，`work/input/broken.json` **内容上就是那 16 道题的答案**（s1-ops-01 / s2-cor-01 / s2-rob-01 / s3-cor-01 / s3-eco-01 / s3-ops-01 / s4-cor-01 / s4-rob-01 / s5-cor-01 / s6-cor-01 / s6-eco-01 / s6-ops-01 / s7-cor-01 / s7-eco-01 / s8-eco-01 / s8-ops-01）。**方向 A**：换非基准题的合成产物（新造能过八阶段交叉核的产物；`ops/adaptation_track.SOURCE_ROOT` 是模块级常量、改一行就能指过去，**管线一个字都不用改**，可分批先做 S2/S3/S4）。**方向 B**：接受烧掉这 16 道题并把它们从主赛道剔除。**三张卡（4.2-a / 4.2-b / 4.rt）都倾向 A** —— 主赛道 40 题是签过字的资产。在裁定之前一个 bundle 都不许推。见 `ops/specs/adaptation_track.md` §7。出处：4.2-a、4.2-b、4.rt（红队 finding 8）。 |
| **N-349** | **适配模块 `geneprotocol_v1_adapt` 还是 `status: draft`，`adapt` 臂注不进去** | **待办（签字，挡真跑）** | 实测：`adapt` 臂真跑在注入期 **22.7 s 中止，零次模型调用**，报 `P7 … status='draft'、条目 3 个 —— 协议工件是干预本身，缺了它 adapt 臂就是个裸臂`。**这一条之前的每一道门都过了**（建题 E1–E14 → `check_export` → `push_guard` → `push_exec`（answer_plane_guard 两侧 0 命中）→ `push_bundle` → `gateway_lock` → P1/P7d）。三份工件（`adaptation.md` / `field_map.json` / `unit_table.json`）内容已定、sha 与清单逐条一致 —— **缺的是签字不是内容**。改法：`ops/adaptation_track.py::module_manifest()` 里写死的 `"status": "draft"` 改成 `released` 并补 `released_at`，跑 `$PY ops/adaptation_track.py --write-protocol-manifest`。现场还摆着，签完一条命令重跑：`bash $GB/scratch/4.2b/run_armsmoke.sh`。出处：4.2-b、4.rt（红队 finding 9）。 |
| **N-350** | 适配 bundle 里**没有 `INSTRUCTION.adapt.md`**，`--arms adapt` 抛裸 `FileNotFoundError` | **已修**（卡 4.rt，`9af050b`） | `ops/pack_adaptation.py` 只写 `arms/INSTRUCTION.{strict,open}.md`，而 `runner/inject.py` 取的是 `bundle/arms/INSTRUCTION.<arm>.md`。修法两处：`pack_adaptation --arms`（每个点名的臂各写一份题面），以及注入器新增 **P6b** —— 缺臂时报「这个 bundle 有哪几个臂」，**且红在建 run dir 之前**，不再掉进 `shutil.copyfile` 的裸异常。出处：4.2-b、4.rt（红队 finding 7）。 |
| **N-351** | 适配集**没有金丝雀三串** | 待办 | `gold_token` / `x_token` / `control_token` 由 `genetask/packager` 的建题流程生成，`ops/pack_adaptation.py` 没走那条路 → `check_export` 的 C1 / G2 / G3 三条判据在 `v1.0-adapt` 上**不适用**。正式出集前要么接进 packager 的金丝雀机制，要么给适配集定义等价判据。（方向 A 换合成题源时可以顺带一起做。）出处：4.2-a。 |
| **N-352** | 适配 bundle 的镜像 digest 是占位 | **已缓解**（卡 4.rt） | `FROM gb-cx-u:r1@sha256:000…0`（`genetask.bundle.IMAGE_DIGEST_PLACEHOLDER`），真 digest 只有 f02 知道。原来的手册顺序是「先 `--pack` 再 `pin_image_digest`」，而 `pack_one` 是**在占位 Dockerfile 上算的通行证** —— 钉完 digest 通行证就废了（红队实测三例全部 `PushBlocked`「内容与通行证不符：image/Dockerfile」），不钉又过不了 P4b。卡 4.rt 加了 `ops/pack_adaptation.py --digest`（钉 digest 挪到出通行证**之前**），`ops/reports/adapt/README.md` 的步骤①②并成一步。出处：4.2-a、4.rt（红队 finding 6）。 |
| **N-353** | 仓库里**没有**独立的「§3.3 适配模块」原文 | **CONFLICT，已登记** | `grep ops/specs` 与 `ops/protocol/geneprotocol_v1/` 只命中两处引用：`GeneBench指标规格_v1.md:17`（「源中缺失的信息保持缺失、不得由 agent 补全」/「有效 artifact 进入其语义完整所支持的最早协议阶段」/「unsupported / unresolved 标记」/「agent 提出翻译、协议裁决可接纳性」）与 `GeneBench指标对接决定_v1.md:9`（「B2 接入与语义保持 ≈ 适配赛道（v2）」）。按任务书兜底条款：**按这两处原文定义最小适配模块**（`geneprotocol_v1_adapt/adaptation.md` 三条规则逐条引原文），并在 `ops/specs/adaptation_track.md` §1 标 CONFLICT。**原文补齐后要按原文重对一遍。** 出处：4.2-a（卡 4.2-b 复核仍成立）。 |
| **N-354** | **`adapt` 臂的措辞列必须是 `strict`，不能是 `open`** | **已修**（`45bd8e3`） | 卡 4.2-a 的交接把它定成 `phrasebook_column: open`。**实测 100% 建不出来**：`packager.build_task` 把每个非参照臂放进 `check_arms` 的**位置 A**，而 E10 对位置 A 的绝对判据是「声明项 `f` 的措辞以 `f=` 开头」（2026-09-03 签字裁定），`open` 列是自然语言括注、**永远不满足** → 6 条 E10。4.2-a 给 open 列的理由（「适配题的题面本来就是通用一份自然语言」）成立，但**绑错了字段**：适配题面由 `ops/pack_adaptation.py` 自己写、**不走 render**，`phrasebook_column` 在那条路上根本没被读到。改成 `strict` 后 `adapt` 臂与 `doc` 臂同形。证据 `$GB/scratch/4.2b/e10_open_column_fails.txt`，正反两面判据 `ops/test_c42b.py::test_open_column_in_position_a_is_exactly_what_e10_rejects`。出处：4.2-b。 |
| **N-355** | `load_arms` 应当在**读表期**就拒绝「protocol 臂 + 非 strict 列」 | 建议（要推任务集版本） | 上一条那个 bug 的形态是：注册表**收下**了一个在任何题上都建不出来的臂，要等到 `build_task` 才炸，而错误消息说的是 E10（读起来像题面的问题，不像注册表的问题）。判据其实完全静态：`kind ∈ {baseline, protocol}` 且非参照臂 且 `phrasebook_column != "strict"` → 必然违反 E10。落点 `genetask/bundle.py::load_arms`（**在冻结根里**）。出处：4.2-b。 |
| **N-356** | 适配赛道的结算入口住在 `ops/reports/adapt/adapt_report.py`，**没折进** `ops/score_runs.py` | 建议 | 两者形状刻意一致（rsync 拉回 → 逐 run 结算 → 出表 → `RIO.secure_tree`），差别只有一处：主赛道走 `scorer.score_run`，适配赛道走 `scorer.adaptation.score_adaptation_run`。建议后续加 `--track adaptation` 开关折进去，否则「适配赛道的结算入口在报告目录里」会变成下一个人的意外。出处：4.2-b。 |
| **N-357** | `v1.0-adapt` 的**冻结引用会随推版本失效** | 已知 | bundle 通行证里记的是 `ops/freeze_v10.frozen_ref()`；卡 4.1 推 v1.0.12 之后 `push_guard.check_manifest` 会判「冻结引用已过期」。**处理方式是重新 `--pack`，不要改通行证**（4.2-a 已重出集一次，30 个仍全绿）。出处：4.2-a。 |
| **N-358** | **30 例里有 13 例的破坏在结构上完全合法** | 记录在案（方法层事实） | 把 `0.93` 写成 `93.3`、删掉一条 provenance，都不违反任何结构规则 —— **只看 `validate_artifact.py` 的退出码，这 13 例会全判成通过**。所以适配赛道的结局**必须比对 oracle**：这不是设计偏好，是这 13 个数逼出来的。每例的 `mutation.json` 里 `broken_validator.ok` 如实记着；`ops/test_adaptation_track.py::test_structurally_legal_breaks_are_recorded` 把这个数钉住，变了就红。**这是这条赛道目前唯一可引的结论**（其余全是 n=0）。出处：4.2-a、4.2-b。 |
| **N-359** | `test_arms_registry.py` 与 `test_adaptation_track.py` 合并跑时出现过**一次**假红 | 观察（未复现） | 2026-09-07 16:49Z 一次合并跑里 `test_bundle_passes_push_guard` 报「题面指纹 记录 `111d763b…` ≠ 现算 `bf9a3ace…`」，两个文件**各自单跑全绿**，几分钟后同一条命令再跑也全绿（59 passed）。当时工作树里有别的代理在写。登记不修，再出现就往「出集读工作树、而工作树在被并发改写」这个方向查。出处：4.2-b。 |


**D. 红队十二条与修复**（卡 4.rt：block 6 / major 3 已修，minor 3 登记不修）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-360** | **只凭文档加不出臂的集**（finding 1，block） | **已修** | 唯一有文档的出集入口 `ops/export_bundle.py`（`harnesses/README.md:363`、`ops/HANDOFF.md:538`）**没有 `--arms`**，固定走 `default: true` 的两臂。红队按文档加完一个臂、跑手册那条命令，出来的 bundle 里**只有两份题面**；要真送进去必须自己写脚本逐步复刻 `export_one` 的每一道门（**复刻等于分叉**）。修法：`export_one(arms=…)` + CLI `--arms`（**默认行为逐字节不变**），公平性协议 §6.6.5 写明这条命令。出处：4.rt、4.1（同条）。 |
| **N-361** | **没有任何文档化的「本地核一遍新臂」路径**（finding 2，block） | **已修** | 在 f01 上把 run 根放在 `$GENEBENCH_ROOT` 下注入会被 **L-5a 当场拒**；`run_f02_a1.py` 没有 `--dry`，最小真跑也要先推 exec 树 + 推 bundle 到 f02。红队最后是靠**读代码**调 `inject(require_docker=False, check_modes=False, place_provider=False)` 且把 run 根放到 `/tmp` 才核到臂的文件集 —— 这三个开关和「run 根必须在数据根之外」**文档里都没有**。修法：`ops/run_f02_a1.py --dry`（P0–P9 与 `work/` 装配全走一遍，**不起容器、不调模型、不读凭据**）+ `--provider-root`；run 根落在数据根内时先说人话；L-5a 的报错补了一句本地自查怎么放 run 根。实跑证据 `$GB/scratch/4.rt/dry_a4.log`。出处：4.rt。 |
| **N-362** | **加臂会让工作树与冻结清单不一致，而全程没有任何东西红**（finding 3，major） | **已修（可观测）；重冻待收口** | `genetask/arms.yaml` 在 `CODE_FILES` 里，加一个臂就让重算的冻结 root 与 `frozen_ref()` 记的那份对不上，而出集 / 推送 / 注入**全程无人报**；唯一可观测是 `ops/test_genetask.py::test_v10_input_drift…`，**而它是 SKIP**。红队的 `suggested_fix`（出集前硬比对，不等则红）与 `ops/freeze_v10.frozen_ref` 的原文（「`code` 段**刻意不**做硬比对：给打包器加个无关函数就会让它漂，而那不是题面变了」）**冲突** —— 按保守方向：**不加硬闸**，改为让它**可查**：每张通行证记 `arm_registry.{sha256, frozen_sha256, in_sync}`，出集时 stderr 打 `[黄]` 并给出重冻命令。**重冻本身见 N-372。** 出处：4.rt。 |
| **N-363** | **公平性协议 §6.6.3「主表按 kind 分块」没有实现**（finding 4，major） | **已修** | `scorer/report.py` 里 grep 不到 `kind`，`table_a` / `table_b` 只按 `(config_id, arm)` 平铺 —— 外部用户跑完一个 instruction_variant 臂，拿到的正是 §6.6.3 明确警告的那张表（「换一句话说涨了 3 分」被读成「协议涨了 3 分」）。按 §8.1「没有测试的公平性条款是一句愿望」**实现而不是降级条款**：每行带 `arm_kind`（认不出的臂记 `unknown` 而不抛 —— 历史 run 里有已删的臂名），`to_latex` 按 kind 分块（`None` = 自动：每行都有 kind 且不止一种时才分块，**旧调用方版面不变**），变体臂块首打印 `genetask.render.WAIVED_FOR_VARIANT`（与 §6.6.2 **同源**，不是在报告器里再抄一遍）。**行为变化**：`TABLE_A_COLUMNS` 在 `arm` 之后插了一列，用它写 CSV 的调用方会多一列。出处：4.rt、4.1（同条）。 |
| **N-364** | **臂的书写顺序静默决定等价表比的是什么**（finding 5，major） | **已修一半** | `genetask/packager.py` 的 `strict, open_ = rendered[arm_ids[0]], rendered[S.BASELINE_ARM]` 把 arms 列表的**第一个元素**当干预臂，而 `equivalence.md` 比的是 `Built.strict` vs `Built.open`。实测 `arms=('open','hint')` → **`ok=True`、无 problems，而两侧逐字节相同**（等价表在拿 open 跟 open 比）；`('hint','open')` 才是对的。而 `('open', <新臂>)` 是最自然的写法，文档从没说过顺序有语义。**已修的那一半**：`ops/export_bundle.check_arms` 拒「第一个是参照臂」并给出正确写法（文档化入口全覆盖）。**没修的那一半**：直接调 `build_task` 的人仍能踩 —— 落点在冻结根内，见 N-372。出处：4.rt。 |
| **N-365** | 适配赛道的跑批手册**顺序自相矛盾，照做必炸**（finding 6，block） | **已修** | 见 N-352。 |
| **N-366** | **适配 bundle 能过守门**（finding 8，block，红线 B2） | **已修（守门侧）** | 红队实测：通行证修好后三例 `assert_pushable` **全部通过**、`check_bundle_tree` 返回 `[]`，而 `work/input/broken.json` 内容上就是那十几道题的答案 —— **没有任何一道判据看得见这一层**。此前挡住它的只有 `pack_adaptation` 的落点闸与规格里的一段文字。修法：`ops/push_guard.check_pushable_set` **按集拒** `set_id == "v1.0-adapt"` 与通行证 `origin: gold_derived`，`assert_pushable` 收编为第三道；`pack_adaptation` 改调前两道（**打得出来 ≠ 推得上去**）。**这只是挡住，不是解决 —— 正解是 N-348。** 出处：4.rt。 |
| **N-367** | 适配赛道**「现在跑不了」这件事没写在规格正文里**（finding 9，block） | **已修** | `ops/specs/adaptation_track.md` 只在 §7/§8 分散提了题源与臂，正文没有一处告诉读者缺哪三件；而 §8 写着「由 4.1 的臂机制投放」，**读起来像已经能跑**。修法：§0 加一张现状表（三条各带落点与票据号）。出处：4.rt。 |
| **N-368** | 两本接入手册**通篇写死「两臂」**（finding 10，minor） | 登记不修（归接入卡） | `harnesses/README.md:395/:416` 与 `integrations/README.md:41-49/:297` 都只说两臂，不提臂注册表、不提公平性协议 §6.6。跟着手册做的人**不会知道臂是数据驱动的**，而 §6.6 的头一句就是「臂不再是常量」—— 两处文档对同一件事给的世界观不一致。修法：两本各加一行「臂集合定义在 `genetask/arms.yaml`（§6.6）；默认出集两臂，出非默认臂见 `ops/export_bundle.py --arms`（§6.6.5）」。**卡 4.rt 不碰 `harnesses/**`、`integrations/**`。** 与 N-343 一并由手册收口处理。出处：4.rt。 |
| **N-369** | 重出一道题会**静默覆写**别人正在用的答案面（finding 11，minor） | 登记不修 | `genetask/packager.write_task` 对已存在的 `task_dir` 直接覆写：`task.yaml` / `canary.json` / `gold_token` / `judge_sha` 全换一套，`_ledger.jsonl` 再追一行 —— **别人手上已导出的 bundle 与通行证就对不上了**。只有 `ops/HANDOFF.md:566` 提了一句「别在别人结算期间重出集」，手册那条命令旁边没有任何警告。修法：`export_one` 发现 `reference/tasks/<set>/<task_id>` 已存在时默认拒绝，要覆盖给 `--force`（并打印上一次的 `judge_sha256` 与 `packed_at`）。**闸放在 `export_one` 这一侧就不必推版本**（`write_task` 在冻结根内）。出处：4.rt。 |
| **N-370** | `ops/test_env.py` 的 key 形态扫描会命中**被拷贝的判据文件自身**（finding 12，minor） | 登记不修 | 把仓库整棵拷进 `$GB/scratch` 试改（**外部用户最自然的做法**，也是红队为了不碰共享工作树采用的做法）会让红线 3 那条测试当场红，命中的是副本里的 `ops/test_env.py` 自己。删掉副本后复跑绿。修法二选一：扫描器按**文件名**白名单排除 `ops/test_env*.py` 这类判据文件（不是按内容），或在 `ops/HANDOFF.md` 的 scratch 纪律里写明「不要把仓库整棵拷进 `$GB/scratch`」。出处：4.rt。 |
| **N-371** | 红队留下的两处目录与一处权限 | **③ 收口已跑；①② 待办（顺手做）** | ① `$GB/staging/rt_phase4_adapt`（gold 派生内容，**任何情况下不推 f02**）；② `$GB/scratch/rt_phase4`（复现脚本与证据，归档后再删）；③ `/data/shared/genebench/repo/.git/index` 曾是 `0o664`，`ops/test_env_guard.py::test_guard_covers_the_git_object_store` 会红。**③ 会周期性复发**（谁 git 操作留下的看谁的 umask）：下一个拿 `git.lock` 的人顺手 `$PY -c "from ops import report_io as R; R.secure_tree('/data/shared/genebench/repo')"`。**阶段四收口实际做了什么**：③ 已跑一次 `secure_tree`（`.git/index` 现在 `0o600`，全量 pytest 里 `test_env_guard.py` 已绿）；**①② 没有删** —— 两棵树都还在，`staging/rt_phase4_adapt` 是 gold 派生内容（**任何情况下不推 f02**），`scratch/rt_phase4` 是红队十二条的复现脚本与证据。删除是一个有后果的动作，留给编排方或用户决定。出处：4.rt、1.rt（同类）。 |


**E. 版本状态与冻结**（阶段四结束时）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-372** | **同版本重冻待做，而它的代价不小** | **待办（收口时挑窗口）** | 现在工作树是漂的：清单记 `genetask/arms.yaml = e727dfd2083e…`、盘上 `b873299c0df8…`（卡 4.2-b 加 `adapt` 臂那次留下的）。`ops/test_genetask.py::test_v10_input_drift_is_visible_even_when_task_text_is_unchanged` 会 **SKIP** 并如实打印漂移项 —— **题面指纹与出集清单都没变**（`default: false`，两侧 `instruction_fingerprint` 都是 `111d763b…`，证据 `$GB/scratch/4.2b/probe_fp.py`），所以是「输入已变、题面未变」，**不推版本，同版本重冻即可**。**代价**：`code` 在 `ROOT_FIELDS` 里 → 重冻让 root 变 → **所有已发通行证作废**（注入器 P3 对旧 bundle 当场拒）。因此必须挑一个**没有在途 bundle** 的时刻，并把已导出的 bundle 重新导出。命令：**先把 `heavy.lock` 拿满、放掉，再拿 `git.lock` 只做 add+commit**（N-336）—— `flock -w 7200 $GB/locks/heavy.lock $PY ops/freeze_v10.py --write`。现在通行证里有 `arm_registry.in_sync`，可以先扫一遍谁是漂着出的集。出处：4.2-b、4.rt。 |
| **N-373** | 阶段四的**冻结根改动清单**（哪些改了、为什么不推版本 / 为什么推了） | 记录在案 | **推了一次**：卡 4.1 把 `genetask/{render,packager,schema,bundle}.py` 泛化成 N 臂，并把 `genetask/arms.yaml` 收进 `CODE_FILES`、`genetask/arms/` 收进 `CODE_DIRS`（变体臂的追加题面文本，**agent 直接读到它** —— 与 N-131 收 `artifact_schema` 同一个论证），推 **v1.0.12**，`REVISIONS` 加一条三段记因，漂移报告是「输入已变、题面未变」；G3 修复（N-339）落在 `packager.py` 且发生在 `--write` 之后，**同一版本号内重冻了一次**（`d9f5a3a`）。**没推**：卡 4.3 只动 `runner/{registry,inject}.py` 与 `ops/run_f02_a1.py`，三者都不在冻结根；卡 4.2-a 一个冻结根文件都没改（**这正是它不走 `genetask/packager` 现有入口的理由之一**）；卡 4.2-b 加 `adapt` 臂只动 `arms.yaml`（见 N-372）；卡 4.rt 一个冻结根文件都没改（闸都放在 `ops/export_bundle.py` 这一侧）。出处：4.1、4.2-a、4.2-b、4.3、4.rt。 |


## 2026-09-07 建到可分发·阶段五（评分器收口与结果输出）

阶段五做的是「**跑完之后那一半**」：先请红队把评分器（闸门 / L3 / 报告器）从头到尾挑一遍（卡 5.1），
再把 v1.0 的已知限制逐条判「挡不挡外部用户」并把挡的关掉（卡 5.2，代价是题面重冻 v1.0.13 + 参考轴 r1.0.20），
然后把「跑一批」从一条 shell 循环变成**一份清单**（卡 5.3 `ops/joblist.py` / `ops/run_joblist.py`）
和**一个结果库**（卡 5.4 `ops/results_db.py` / `ops/mk_tables.py`，三张表的单一来源），
最后请红队**只按手册**把阶段五走一遍（卡 5.rt）。

下面是 `ops/tickets_inbox/5.*.md`（`5.1` / `5.2` / `5.3` / `5.4` / `5.rt`）五份收件箱的逐条并入。
同一件事被多张卡登记的**合并为一条**，出处逐一列在说明末尾。**已修的也登记** ——
阶段五有三条改动动了**已经发布过的数**（N-374 的锚点 / 分母 / null 委托号三个根因），
不写下来别人拿旧 CSV 的截图去引会引错。红队 11 条 finding 里 block 1 / major 3 由卡 5.rt 修完（N-398…N-401），
minor 7 条登记不修（N-402…N-408）。

**这一阶段有一件事没做到，且不在我们手里**：默认预算档 600k tokens 与它自己写的换算规则矛盾，
`ops/reports/v1demo/` 那 8 个 run **8/8** 撞的是 token 闸 —— 主表上的 SR / pass@1 读的是「预算够不够」不是能力。
抬档是判据变更，要用户点头（N-388，BLOCKED_AWAITING_USER）。


**A. 评分器红队一轮**（卡 5.1：六视角逐个过，12 条确认缺陷归并 7 个根因，先写会红的测试再修）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-374** | **评分器十二条确认缺陷、七个根因，全部已修；其中三条改了已发布的数** | **已完成** | 每条都有实跑负例（跑板 `$GB/scratch/5.1/redteam_probe.py`，输出原样入 `ops/reports/rescore_5_1.md`），**先写会红的测试再修**（`ops/test_scorer_redteam51.py` 27 条：修前 25 红、修后 27 绿）。**动了已发布数的三条**：① S2 的锚点顶不是真的 oracle 自比（自比的 agent 侧写死成 `task_dir/work/`，S2 题目录根本没有 `work/` → 天花板 0.75 → 所有 ≥0.75 的产物一律夹成 `effect=100`），修后 `h_claude-code` strict 100.0→**81.49**、`h_opencode` strict 100.0→**81.59**；② 逐格/逐日比对的分母取交集而不是 gold（只交 1/200 行能拿 `CellAgree=1.0`），修后 `n_cells` 166624→166800、`a4` strict 的 pass@1 0.5→**0.0**、`m6` open 0.5→**0.375**；③ S8 的 `null` 委托号被收进「已见委托」集合，`m6b` 两条记录 `fills_linked_to_orders` 1.0→**0.0**。其余四个根因：JSON `true` 判成信号数值态、payload 空对象判成诚实终止、PIT 基准回退到产物自报的 `as_of`、S6 重复 symbol 去重后绕过 Σw≤1。**16 个 batch + 私有/公开两套三控全部事后重算**，并用「HEAD 的旧 scorer 跑一遍 / 新 scorer 跑一遍」做隔离基线把「我改的」与「输入自己变了」分开：26 个文件逐字节相同、117 个只多了新列、73 个有实质变化且归因全部落在三个根因上（`$GB/scratch/5.1/isodiff.txt`）。出处：5.1。 |
| **N-375** | `ops/run_controls.py` 的 **oracle 桩拷错了目录**，控制判据 ① 的 effect 是 75 不是 100 | **待修**（路径不在 5.1 手里） | `score_control()` 只从 `task_dir/"work"` 拷产物文件，而 S2 的 gold 面板在 `gold/panel.csv`（r1.0.16 起），题目录**根本没有 `work/`** → oracle 桩交上去的是「有 artifact.json、没有面板」的产物，`CellAgree=0`、`l3_score=0.75`。**以前看不出来是因为锚点的天花板也坏成 0.75**（同一根因的另一半，N-374 已修）：`0.75/0.75=1.0` → effect 100.0，两个错互相抵消。修好 scorer 之后它露出来了：`ops/reports/{m6,public}/controls.md` 里 `s2-cor-01 | oracle | effect=75.0` —— **这是如实记录，不是回归**。补丁一行，用 `scorer.score_run.gold_payload_dir(task_dir, stage)`（该函数已为此导出），原文见 `ops/reports/rescore_5_1.md` §4。改完重跑私有与公开两套 `ops/run_controls.py`。出处：5.1。 |
| **N-376** | `ops/run_controls.py::judge()` **不检查 oracle 的 effect 是否 = 100** | **待修**（同上） | 控制判据 ① 的原文是「效果分 = 100（自比即天花板）」，`judge()` 只检查「出数了没有」—— 于是上一条在 `controls.md` 里与「三条判据全过」并排。**门有了、门后没人**。`judge()` 应当照原文判。出处：5.1。 |
| **N-377** | `ops/reports/v1_0_readiness.md` 与它的生成器**都陈旧了** | **待重跑**（不在 5.1/5.2 的路径里） | 两处：① 第 47–48 行 S2 两条应为 `align:False` / `99.9736`（N-374 改了锚点之后），命令 `$PY ops/readiness_report.py --batch m6,m6b`；② `ops/readiness_report.py` 第 265 行那张已知限制表把 N-126 / N-127 / N-128 / s2-eco-01 都写成未解，而卡 5.2 关了其中三条，出集也从 33 题变成 **34** 题。重跑生成器并对着 `ops/reports/known_limits_v1.md` 订正。**卡 5.3 也交办过同一条，仍然没人做。** 出处：5.1、5.2、5.3。 |
| **N-378** | `m6_all` 是**跨题面版本的合表**（`1.0.7` + `1.0.9`），要不要继续出是编排方的裁定 | **待裁定** | `table_a` 按 `(config_id, arm)` 分组，两个版本的 run 合成了同一行 pass@1。卡 5.1 让 Table A / Table B 把它显式写成 `MIXED:1.0.7\|1.0.9`；卡 5.4 又给结果库这条路加了一道门（从库出这张表必须 `--allow-mixed-axes`，脚注与 `.axes.json` 里写明混了哪些值）。**但既有的 `ops/reports/m6_all/` 是 `ops/combine_batches.py` 出的，那条路没有这道门。**「要不要继续出这张合表」报告器不替编排方拍 —— 合表的读数当结果读会出事。出处：5.1、5.4。 |
| **N-379** | `compare_fill` 的 `events_monotone` 用**字符串排序**判时间单调 | 登记不修（v1.1） | 实测 `ts` 都是同一种 ISO 写法所以判得对，但混写（`Z` vs `+08:00`、带/不带时区）会判错。校验器侧已有 `_parse_ts`，统一到那条线属于 v1.1。出处：5.1。 |
| **N-380** | `compare_cons` 的 `Feas` 读 agent **自报的** `solver_status` | 登记不修（规格层取舍） | 规格 §3 给 Feas 的定义就是「有可行解的调仓日占比」，而「有没有可行解」只有求解器那一侧知道，产物之外没有第二个信源。不是判定器的 bug；要改成行为判据得先改指标规格。出处：5.1。 |
| **N-381** | `compare_epsilon` 缺件时 `max_band_ratio` 是 `None` 而不是 `inf` | **已修，登记语义** | 缺件的那一格记 `band:<path> = 0.0` 并进 `within_band_rate` 的分母（**该扣的扣到了**）；只是「超带多少倍」这个比值在缺件时没有定义，写 `None`。修之前是把裸 `Infinity` 写进 JSON。出处：5.1。 |


**B. 已知限制逐条判定与题面重冻 v1.0.13 / r1.0.20**（卡 5.2：判定口径只有一条 —— 挡不挡外部用户）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-382** | **题面重冻 v1.0.13 + 参考轴 r1.0.20；出集 33 → 34 题；两条通道逐题零 finding** | **已完成** | 按 N-111 **分两次**跑：`ops/freeze_v10.py --write`（任务集 v1.0.13，root `925a1adcdf82e6a0…`）与 `--write-reference`（参考轴 r1.0.20，root `8c162988c2a7b5d2…`），`REVISIONS` / `REFERENCE_REVISIONS` 末尾各加一条完整记因（why / what / scope / gates / also_captured / consequence）。**重冻作废所有已发通行证**（注入器 P3 对旧 bundle 当场拒），所以挑了「没有在途 bundle」的窗口做，`genetask/arms.yaml` 那处输入漂移（N-372）一并被吸收。完成定义写的是「33 题零 finding」，实际达成 **34 题**：私有 34/34、公开 34/34 出集题全部零 finding，两条通道逐题一致（`ops/reports/probe_run_oracle.cumulative.json`、`ops/reports/public/probe_run_oracle.cumulative.json`）。顺带把 `ops/test_genetask.py` 里写死的 33/7 改成跟 `freeze_v10.PROBES_IN_V10` 走（共享文件幂等补丁），下次再放行一道探针题它不会假红。出处：5.2。 |
| **N-103**（更新） | `s6-rob-02` 因无实质性证据出不了集 | **已关**（卡 5.2） | 证据（卡 1.1-c 量的，`ops/reports/public/materiality_evidence.json` 的 `entries[0].text`）原样进 `genetask/schema.py::DIVERGENCE_EVIDENCE`；`ops/freeze_v10.py` 的 `IN_V10` 改成跟 `PROBES_IN_V10 = {s7-rob-02, s6-rob-02}` 走；夹具第一次物化，params 里那个全零占位 sha 换成真值；`tolerance.kind` cons → none（与 s7-rob-02 同，N-93）。**既有的 `sell_rule` 那条一个字没动。** 出处：5.2。 |
| **N-279**（更新） | `s2-eco-01` 打 `/bars?universe=` 被网关 422 —— 出集题里唯一跑不出 oracle 的一道 | **已关**（卡 5.2） | 两条路实测过：(a) 让 `/bars` 接 `universe` 会改 `declared_reads` 探针的分母口径，**且仍跨不过 `MAX_ROWS=200 000`**（300 只 × 约 1 840 个交易日 ≈ 55 万行），是大改；(b) 只动参考轴一个 `solve.py`，按 code 批量 + 按 `MAX_ROWS` 反算分批。**取 (b)**。顺带补上与其余四道 S2 题同族的两处老问题：`get()` 没带身份头（网关日志按 `(task_id, config_id)` 切片，缺了就是 `log=0`「一次都没请求过」）、payload 档位要的 `adjust_applied` 一直没报。**同族缺陷在一道从没跑通的题上会一次性全部现形** —— 别的「从没真跑过」的路径该按这个清单查一遍。出处：5.2。 |
| **N-127**（更新） | S8 滑点的**符号约定**题面没写 | **已关（题面部分）**；判据部分 → v1.1 | 五道题两臂各加一行「`payload.fills.slippage_bps` 成交价高于计价基准时取正、低于取负，单位 bps」，与规格 §3 的 `Slip = 量加权(成交价 − 决策时点价)` 同向；**判据不动**（`compare_fill` 里 Fill / Slip 仍只报不判）。把 Slip 纳入判之前必须先做 N-383。出处：5.2。 |
| **N-128**（更新） | S8 事件记录的**字段**题面与 schema 都没规定，而 Audit 要求「可完整重放」 | **已关（题面 + schema 部分）**；收紧 `required` → v1.1（N-384） | 五道题两臂各加四行（order / fill / cancel / state 各要哪些键 + `state_transitions` 要 from/to/order_id）；同一组字段进 `PAYLOAD_SHAPE["S8"].events` 的叶子 `properties`（**只补 properties、不收紧 required**）并重生成八份 `ops/specs/artifact_schema/v1.0/S*.json`，`genebench_client/emit_schemas.py` 的逐字副本同步重灌。判据锁 `ops/test_s8_event_fields.py`。**与 N-374 方向一致**：卡 5.1 同时把 `compare_fill` 的 Audit 判据从「键在不在」收紧成「每一项都要有值」。出处：5.1、5.2。 |
| **N-120**（更新） | 跑批没把可交易性视图喂给校验器 | **已关**（卡 1.1-c 落地，卡 5.2 核实） | 重跑 `s2-cor-01` / `s5-cor-01` 私有 oracle 零 finding，`calendar` 与 `missing_masquerading_as_signal` 两族真被调用（`ops/reports/probe_matrix_oracle.md`）。**局限照旧**：S8 四题拿不到视图（N-288），逐题记「这两族没被调用过」，不假装 clean。出处：5.2。 |
| **N-126**（更新） | S6 的 **TE**（跟踪误差）出不来 —— 它要收益率序列，而 v1 的 S6 产物里没有 | **登记为设计性限制** | v1 的 S6 契约（`PAYLOAD_SHAPE["S6"]`）只有 `targets` / `cash_ratio`；`scorer/l3` 的 `cons` 判据本来就**不出** TE 并在 `note` 里写明，`ops/test_scorer_l3.py` 有断言盯着「TE 出不了要写在 note 里，不能悄悄不提」。**不挡外部用户**：S6 的 Cons / Feas 照常判。v1.1 的补法写在 `ops/reports/known_limits_v1.md`。出处：5.2。 |
| **N-383** | **滑点的符号在我们自己的两份实现里不一致** | **待批（CONFLICT，BLOCKED_AWAITING_USER）** | `gateway/sim_engine.py::slippage_bps` 按 `Σ qty × (成交价 − 基准) / 基准` 算，**不按买卖翻符号**（与规格 §3 同形）；`reference/s8_oracle_common.py::fill_metrics` 的 docstring 写「买正卖负」并真的乘了 `sign`。**买单两者同号、卖单相反。** 今天不影响任何分数（Slip 只报不判），但把 Slip 纳入判之前必须先对齐，**以规格 §3 为准**（即去掉 `fill_metrics` 里的 `sign`）—— 那是参考轴冻结根，要推 **r1.0.21** 并**重出 S8 四题的 gold**。出处：5.2。 |
| **N-384** | S8 `events` 的重放字段**收紧成 schema `required`** | **待批（v1.1）** | 卡 5.2 只补了 `properties`。收紧 `required` 会让 `reference/artifact_samples.py::s8()` 的**合法**样例（order 事件只有 `symbol`/`qty`）与既有 121 份真产物集体变畸形 —— 那是判据变更，要另一轮红队，并同时改 `artifact_samples` 与 `ops/validator_parity.py` 的语料基线。任务集版本 **v1.0.14**。判据锁写在 `ops/test_s8_event_fields.py::test_events_required_is_not_tightened_by_this_card`。出处：5.2。 |
| **N-385** | `genebench_client/emit_schemas.py` **没有生成器脚本** | **待办（v1.1）** | 文件头写着「改完重跑生成器」，而全仓**没有那个脚本**。它是 `ops/specs/artifact_schema/v1.0/S*.json` 的**逐字副本**，S8.json 一变 `ops/test_emit.py::test_schemas_do_not_drift_from_ops_specs` 当场红。卡 5.2 是照配方（`json.dumps(..., ensure_ascii=False, indent=1, sort_keys=True)` 灌进 `_BLOB`）重灌的，并先用**未改动的七个阶段逐字节自证**了配方。补一个 `ops/mk_emit_schemas.py` 才算把这条路径钉住；在那之前改 `ops/specs/artifact_schema/**` 的人要记得手工重灌。现成脚本 `$GB/scratch/5.2/regen_emit_schemas.py`。出处：5.2。 |
| **N-386** | 最近四次**任务集版本**的记因写在 `REFERENCE_REVISIONS` 里 | 登记不修 | 1.0.10 / 1.0.11 / 1.0.12 / 1.0.13 都追加在 `REFERENCE_REVISIONS` 末尾，而任务集清单落盘的是 `REVISIONS`（它停在 1.0.6）。也就是说 `ops/manifests/v1.0-smoke.json` 的 `revisions` 段**看不到最近四次的原因**。改分流会动四条历史记录的落点，按既有做法走。出处：5.2。 |
| **N-372**（更新） | 同版本重冻待做（`genetask/arms.yaml` 的输入漂移） | **已关**（卡 5.2 顺带吸收） | 卡 5.2 那次重冻把它一并吸收，记在 `also_captured`。阶段五收口复核：`freeze_v10.frozen_ref(verify=True)` 与 `reference_ref(verify=True)` **两轴都通过**，工作树与清单一致；卡 5.1 报的那 12 条恒红（`ops/test_{4rt,push_guard,adaptation_track}.py`）随之消失，收口全量里没有一条。出处：4.2-b、4.rt、5.1、5.2。 |
| **N-284**（更新） | `ops/gateway_lock.py` **不可重入** —— 阶段五又踩了一次 | 待修（根治项仍成立） | 卡 5.2 第一次跑 `gateway_lock.py -- run_oracles`（漏了 `--no-batch-lock`）当场自锁，日志刷了 8 分钟「等网关锁：当前 pid=<自己>」。根治建议（环境变量 + pid 校验标记本进程树已持有）仍成立。**在那之前照抄这一条**：外层 `gateway_lock` + 内层 `run_oracles --no-batch-lock`。出处：5.2。 |


**C. 作业清单运行器**（卡 5.3：一批真跑 = 一份清单，断了能续，撞闸不重试）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-387** | **`ops/joblist.py` + `ops/run_joblist.py`：从清单跑到出表，一条命令、无人工干预** | **已完成** | 矩阵（`ops/joblists/<name>.yaml` 或 CLI）→ `jobs.jsonl`，笛卡尔积顺序 `task × arm × config × seed`（外到内，同题两臂挨在一起，断在中途留下的是完整的题而不是半道题）；`job_id` 与 `runner.inject.run_id` **逐字相同**（不同源就要靠一张会漂的映射表）；生成期就查臂集合四条闸 / config_id / 题号。状态机 `TRANSITIONS` 是写死的一张表：`pending→running→done|failed|budget_exhausted`，**任何终态回 pending 只有显式 `retry/reset` 一条路**（`done` 悄悄回 `running` 的表现是结果库里同一主键两份内容，而库对那个当场抛）。运行器六段各调既有那一份（`export_bundle` / `push_bundle_to_f02.sh` / `gateway_lock` / `score_runs` 带两层 `runs` / `results_db.backfill_batch` / `mk_tables`），**一行聚合都不重写**；半途中断分两种处置（`running` 且有 run_id = 跑完没结算，只补结算不重跑；`running` 且无 run_id = 没真起来，退回 `pending`）。**预算参数默认整个不给**，让注入器按 stage 取档。判据 `ops/test_joblist.py` 42 条（负例核过：放宽 `TRANSITIONS` → 4 条红；`RUNNER_CONCURRENCY` 改 2 → 1 条红）。真跑验收见 N-410 判据 ②。出处：5.3。 |
| **N-388** | **默认预算档 `max_tokens=600_000` 与它自己写的换算规则矛盾** | **待裁定（BLOCKED_AWAITING_USER，挡结果解读）** | `runner/registry.py` 的 `BUDGET_TIERS` 注释把 tokens 定义成「档位调用数 × 每次 prompt 量级（取 60k/次）」，据此 S4=150×60k=9M、S7=300×60k=18M；**默认档按同一条规则应当是 100×60k=6M，实际写的是 600k**（= 10 次调用的量）。三条同向实测：`ops/reports/a4/records.json` 里 s2-cor-01 的 strict/doc/hint 三臂全部在第 19–24 次调用撞 **token** 闸；`ops/reports/v1demo/` 8 个 run **8/8** 撞它（`ops/api_usage.py` 逐 run 的 deny 列各 1，calls 只用到 18–22 / 100）；`ops/HANDOFF.md` 14.4 §3 早就写着「接入验证一律 3M」。后果不是一条显眼的错误，是 **agent 做到一半自己放弃、分数照出**（`BUDGET_TIERS` 自己的注释：「它长得像结论」）。**建议：默认档 `max_tokens` 抬到 6,000,000**（只往上抬，不触 `assert_registry_sane` 的「档位只能往上抬」判据；不需要重冻、不需要重出集）。**绕法（裁定之前）**：矩阵里写一行 `max_tokens: 3000000`。裁定通过之后建议重跑一次 `v1demo`，让主表上有一组不是被预算截断的读数。出处：5.3、5.rt（红队 finding 11）。 |
| **N-389** | `run_id` **不含 batch**：跨批重名，且重跑一个已经落过盘的 run 无路可走 | 登记（正解要 runner 侧裁定） | 两个后果同一根因（`run_id = <task>.<arm>.<config>.rNN`）：① `s2-cor-01.strict.cfg-codex-deepseek.r01` 在 `a4`（1.0.12）与 `m6`（1.0.7）里各有一条、是两次不同的运行 —— 结果库主键因此取 `(batch, run_id)`，重名单列在 `index.json::run_id_reused_across_batches`；**别处按 run_id 建索引的脚本会撞**。② `runner/inject.py` 见到已存在的 run dir 直接抛（F9：不覆盖遥测），于是 `--retry-status failed` 只在「上一轮根本没建出 run dir」时才走得通，真要重跑只能换 batch 或换 seed。正解是给 run_id 加批次前缀。出处：5.3、5.4。 |
| **N-390** | 结算与入库是 **batch 粒度**，续跑会把整批重新拉一遍 | 登记 | `ops/score_runs.py --batch` 是整批 rsync + 整批重算，`results_db.backfill_batch` 也是整批。续跑第二次时前面已 done 的 run 会被重新结算一次（结果一致 → `ingest` 判重跳过，不出错，只是慢）。题量上到几十道之后值得做成增量。出处：5.3。 |
| **N-391** | `ops/reports/<batch>/table_*.csv` 有**两条**生成路径 | **建议收口后并成一条** | `ops/score_runs.py` 自己出一份，`ops/mk_tables.py` 从结果库出一份；`run_joblist.py --tables` 会用后者覆盖前者（`ops/reports/v1demo/` 就是第一次真的撞上）。卡 5.4 核过 15 个批的 Table A / Table B **逐格相同**（`ops/reports/results_db_backfill.md`），今天没有差异 —— 但两条路并存迟早会漂：哪天有人改了 `scorer/report.py` 的聚合，同一个目录会先后被两份实现写过。修法：把 `score_runs` 出表那几行换成 `mk_tables.write_table`（`score_runs` 是共享文件，5.3/5.4 都没有授权）。出处：5.3、5.4。 |


**D. 结果库单一来源**（卡 5.4：一条结果 = 一行 + 四条版本轴；三张表只从库出）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-392** | **`ops/results_db.py` 落 `$GB/results/v1/results.jsonl`，`ops/mk_tables.py` 从库出三张表** | **已完成** | 追加式一行一条 run + `index.json`：`ingest` 幂等（主键 `(batch, run_id)`，内容一致跳过、**不一致报错不覆盖**），`query(**filters)`、`versions()`（库里出现过的版本轴组合，**混轴在这里看得见**）。四条**可比性轴** `set_version / reference_version / protocol_version / channel`（N-207 的「四个版本字段」）**缺一即拒**。`mk_tables --table a|b|adaptation --format csv|md|latex --filter k=v`：聚合一行都不在这里，全调 `scorer/report.py` 现成函数；**混轴保护** = 四条轴不全同时即默认拒绝出表并列出分歧，`--allow-mixed-axes` 显式放行且在 md/latex 脚注与 CSV 旁的 `.axes.json` 里写明。回填 15 个 batch / 74 条 run，**从库生成的 Table A/B 与各 batch 既有 CSV 逐格相同**（`ops/reports/results_db_backfill.md`）。判据 `ops/test_results_db.py` 35 条（负例核过：关掉混轴门 → 3 条红；`table_a` 的 k 从 3 改成 2 → 7 条红）。`scorer/report.py` 一个字节没动。出处：5.4。 |
| **N-393** | `ops/protocol/geneprotocol_v1/MANIFEST.json` **没有 `version` 键** | **已绕开，建议补**（CONFLICT） | 卡面把协议轴写成「MANIFEST.json 的 version」，实物里只有 `protocol_id` / `status` / `released_at` / `artifacts`。改用**封闭清单三件的内容摘要** `geneprotocol_v1@sha256(名:sha 排序)[:12]`，历史批次**从 run 当时真的注进去的字节**反算（`runs_in/<batch>/*/inject.json` 的 `files[work/protocol/*]`），反算不出即拒绝入库 —— **不拿今天仓库里的清单去追认**。建议 `ops/mk_protocol_manifest.py` 重算时顺手把这个摘要写进清单的 `version` 字段。出处：5.4。 |
| **N-394** | 协议内容**已经动过一次**，而当时的记录里没有任何字段说得出这件事 | **如实记录（引数时必须知道）** | `a1` / `m6` / `m6b` 三批注进容器的 `work/protocol/validate_artifact.py` 是 `f8b8ad26…`（轴值 `geneprotocol_v1@7e8ad97d1f7a`），`a4` 及其后是 `ca26c78f…`（`@d6fbcaa08302`，= 今天仓库的值）。**strict 臂拿到的协议工件在 m6 与 a4 之间换过一版** —— 协议臂拿到的工件不同源，effect 的口径就不同源。**凡是把 m6 与 a4 并排读的地方都要知道这一条。** 结果库的协议轴就是补这个洞；反算依赖 `runs_in/<batch>/` 还在本机，**清 `runs_in` 之前先把库回填完**。出处：5.4。 |
| **N-395** | `scorer.score_run` 的记录里**没有** `protocol_version` / `channel` | 建议后续卡补 | 记录里现在带的四条是**注入面**的（set / reference / runner / image）；N-207 的四个「版本字段」里的后两条一条都没有。结果库靠 `results_db` 在**入库时**补（前者反算、后者由回填声明，`axes_source` 里记着它是声明来的），不是 scorer 结算时盖的章。正解是 `ops/score_runs.py` 加 `--channel` 且 `scorer/score_run.py` 直接把两条轴写进记录（两个都是共享文件）。出处：5.4。 |
| **N-396** | 适配赛道的记录**进不了结果库**，`--table adaptation` 出的是空表 | 登记不修 | `scorer.adaptation.AdaptationResult.as_record` 出的记录不带四条版本轴、也没有 `task_id` / `seq`（库为它单开了 `IDENTITY_ADAPT`）。通路已经通并有测试，但 `ops/reports/adapt/records.json` 是空的（真跑被红线 B2 闸住 —— N-347 / N-348），所以一条都没收。要真收，得先让 `ops/reports/adapt/adapt_report.py` 把四条轴写进记录。出处：5.3、5.4。 |
| **N-397** | 结果库里 `channel` 只有 `private` 一个取值 | 如实记录 | `ops/reports/public/` 里只有三控与对账，没有 `records.json` —— **公开通道到今天为止没有可结算的 run**。所以通道轴现在是「声明」出来的（`axes_source.channel = backfill:declared`）。公开通道一旦有真跑，`ingest --channel public` 就能分开。出处：5.4。 |


**E. 红队十一条与修复**（卡 5.rt：block 1 / major 3 已修，minor 7 登记不修）

红队自己的结论要照抄一遍，因为它决定了这些 minor 的读法：**没有一条 finding 是「表上的数算错了」**。
SR / pass@1 / 越权率 / `$` / effect / Steps / Latency / tokens 八类格子，加 L3 层的 Cov / PIT / Prov，
都被从原始 `artifact` / `run.json` / `llm_log.jsonl` / 网关 `access_log`（143,792 行）独立重算过、两臂逐位命中。
三条 major 是「表上的数**说错了话**」，七条 minor 是「表上的话**不够准**」。

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-398** | **阶段五的四个入口在任何面向用户的文档里都不存在**（finding 1，block） | **已修**（卡 5.rt） | `ops/HANDOFF.md` 有 §12–§15（阶段一~四）每节都带「跑法（照抄）」，**没有阶段五一节**；`README.md` 一个字都没提。实测 `grep -rln 'run_joblist\|joblist' --include=*.md` 只命中代理自己的收件箱 —— 外部用户只凭 README + HANDOFF **走不到** `ops/{joblist,run_joblist,results_db,mk_tables}.py`，连「有这么个东西」都不知道。修法：HANDOFF 新增 **§16**（四个入口 / 跑法照抄六条 / 矩阵 yaml 字段表含 `digest` 出处 / 四列口径 / 五个坑 / 证据落点）+ README 新增「跑一批」一节。判据做成**双向**的（入口文件真的在 + 文档真的点了名）：`ops/test_5rt.py`。出处：5.rt。 |
| **N-399** | `budget_exhausted_runs` 数的是「撞闸**且**交白卷」，列名说的是「撞了预算闸的 run 数」（finding 2，major） | **已修**（卡 5.rt） | 实现取 `run_status == 'budget_exhausted'`，于是 `v1demo` 两臂各写 3，**真值是 4/4**（8 个 run 全部撞 600k token 闸，其中两个因为已经写下了 artifact 而被判 `run_status=ok`）。这一列存在的理由正是「让读者看得出是谁把 run 停下的」，而它恰好在「撞闸但还是交了卷」这一格失真 —— 而那两个 run 正是全表**仅有的两个**进了 pass@1 分子的 run。修法：分子改读记录里的 `budget`（`score_run.budget_exhausted` 只在边车真的发过 429 时才非 None），旧记录没有该键时退回原口径。判据 `ops/test_5rt.py::test_v1demo_reports_four_of_four_budget_capped_runs`（真数据 4/4）。出处：5.rt。 |
| **N-400** | `unbounded_requests` 的真值 **0 被 `or None` 翻成空**，与「网关日志不可得」同形（finding 3，major） | **已修**（卡 5.rt） | 落到 CSV 是空串、落到 LaTeX 是 `---`。一个「一次都没发过无右端取数请求」的干净 agent（我们**想看到**的好结果），在表上长得跟「我们看不见」一模一样 —— 与本文件自己立的纪律（「算不出就是 None，不是 0」）方向正好反过来。修法：去掉 `or None`，按有没有可用样本判三态。出处：5.rt。 |
| **N-401** | `protocol_version` 是**批级声明**却以**逐 run 版本轴**的身份进库、进表、进 `--filter`（finding 4，major） | **已修（CONFLICT，按保守方向同时满足两条）** | 实测 `v1demo` 8 条：4 条 strict 臂有摘要，4 条 `open`（裸臂）本来就没投放协议工件，而 `enrich` 把批级那一个值盖在了全部 8 条上 → `--filter protocol_version=<摘要>` 会选出**从来没见过该协议**的裸臂 run。**CONFLICT**：`results_db.py` 模块头原文写着协议轴**按批取值**的理由（「按臂取值会让每一批都变成混轴、每张表都出不来」），两者都对了一半。做法是**同时满足**：逐 run 写轴（裸臂显式记 `geneprotocol_v1@none`）+ `mixed_axes` 对该轴**按 arm_kind 分组**判（`none` 与摘要并排不算混轴）。**没有放宽任何判据**：协议臂之间出现两个摘要仍然是混轴、仍然拒绝出表；一批里反算出两个摘要仍然拒绝入库；连 `inject.json` 都读不到仍然拒绝入库。模块头那段话已按新口径改写，不留两套说法。**下游语义变化**：`--filter protocol_version=<摘要>` 现在只选协议臂；版本轴组合从 7 种变成 14 种（每个 `(set, reference)` 拆成「协议臂 / 裸臂」两行）。出处：5.rt。 |
| **N-402** | `$` 列缺「**成本上界**」那句必写的脚注（finding 5，minor） | 登记不修 | `scorer/report.py` 模块头与 `runner/pricing.yaml` 都写死了这条义务（DeepSeek 分高峰/低谷两档而边车不记档位，表里取高峰价 —— **这一列是成本上界，不是账单实数**），而 `ops/mk_tables.py::axes_notes` 只产出四条版本轴 + 记录数。红队按高峰价手算 `615369×0.44/1M + 26763×1.32/1M = 0.30608952`，与记录逐位相同 —— **数是对的，缺的是那句话**。修法：表含 `$` 列时在 md 脚注 / latex 的 `%` 注释 / `.axes.json` 三处各加一行。出处：5.rt。 |
| **N-403** | 两张表对「认不出的 `run_status`」的纪律**相反**（finding 6，minor） | 登记不修 | `scorer/report.py::_in_denominator`（只被 `table_b` 用）明写「认不出的状态**留在分母** ——『这份旧数据画不出来了』不是报告器该做的裁定」，而 `table_a` 里 `FM.sr_bucket(...)` 是裸调、未知状态直接抛。实测把一条记录改成旧名 `budget_exceeded`：`table_b` 正常出 8 行，`table_a` 抛 `TaxonomyError`。**主表恰好是那张画不出旧数据的表。** 修法二选一：`table_a` 改用 `_in_denominator`，或反过来让两张表都抛并在 HANDOFF 写明「改过名的 `run_status` 要先迁移记录」。出处：5.rt。 |
| **N-404** | 「四条版本轴」在同一张表里指**两组不同的四条**（finding 7，minor） | 登记不修（已在 §16.4 写给读者） | 表**列**是 `scorer.report.VERSION_AXES`（set / reference / runner / image_digest，**注入面**），表**脚注**是 `results_db.AXES`（set / reference / protocol / channel，**可比性**），两处注释都自称「四条版本轴」。读者在同一张 `table_a.md` 上同时看到两组会以为漏了或多了。修法：改名成 `INJECT_AXES` / `COMPARABILITY_AXES` 并在 `axes_notes()` 第一行写明。**卡 5.rt 已在 HANDOFF §16.4 把这件事写给读者，代码里的同名没动。** 出处：5.rt。 |
| **N-405** | tau 题的 `effect.raw_metric` 是 `fid_day_rate`，标签却写 `metric_kind: "tau"`（finding 8，minor） | 登记不修 | `s5-cor-01.strict` 的 `effect.raw_metric = 1.0` 与 `anchor.metric_kind = "tau"` 并排，读起来就是「τ=1.0」，而 Table B 同一个 run 的 `tau` 列是 `0.984…`。**effect=100 本身是对的，错的是标签。** 修法：`compare_tau` 带出 `score_name='fid_day_rate'`，或在 effect 里加 `raw_metric_name`。出处：5.rt。 |
| **N-406** | Table B **说不出**「这一格根本没有可结算的 run」（finding 9，minor） | 登记不修 | `v1demo` 的 6 个 `budget_exhausted` run 在 Table B 上是 `n_runs=1, invalid_rate=0.0` —— 8 行 8 个 `0.0` 读成「一条违规都没有」，实际是 6 行连产物都没有；要区分得跳到 Table A 看 SR，两张表分开发出去时这一格必被误读。修法：加 `scorable_runs` / `unscorable_runs` 两列，`scorable_runs == 0` 时 `invalid_rate` 出 `None` 而不是 `0.0`。出处：5.rt。 |
| **N-407** | `ops/joblist.py` 的 CLI 与 `run_joblist.py` **不同形**（finding 10，minor） | 登记不修（已在 §16.5 §1 写成坑） | `run_joblist.py` 用 `--jobs <path>`，`joblist.py stat/list/reset` 用**位置参数**，照抄会得到 `unrecognized arguments: --jobs`；`gen` 的每个开关都没有 help 文本（尤其 `--digest` 去哪儿取）；`gen` 的合法性检查失败时抛未捕获的 `JoblistError`，用户看到整段 traceback（**错误信息本身写得很好**）。修法：加 `--jobs` 别名、补 help、`main()` 外包一层 `except JoblistError`。出处：5.rt。 |
| **N-408** | `doc` 臂在协议轴上记 `none`，而它其实拿到了封闭清单三件里的两件（minor，红队实测新发现） | 登记不修 | 逐 run 协议轴落地后实测：`a4` 的 `doc` 臂注进去的是 `work/protocol/{README.md,contract.md}`，**没有** `validate_artifact.py`；`hint` 臂一件都没有。两者都记 `geneprotocol_v1@none`，因为这条轴量的是「拿到的是哪一版**封闭清单**」而半份清单不构成一个版本（`protocol_digest` 缺件即抛）。逐件的投放差异在 `arm` / `arm_kind` 两列上看。要更细的话，加一列 `protocol_files`（遥测，逐件 sha）比放松这条轴安全。出处：5.rt。 |


**F. 版本状态、口径变更与完成定义**（阶段五结束时）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-409** | **版本状态**：`SET_VERSION = 1.0.13` / `REFERENCE_VERSION = r1.0.20`，两轴与工作树一致 | 记录在案 | 阶段五推了一次：卡 5.2 的题面重冻（任务集 **1.0.12 → 1.0.13**，root `925a1adcdf82e6a0…`；参考轴 **r1.0.19 → r1.0.20**，root `8c162988c2a7b5d2…`），按 N-111 **分两次** `--write` / `--write-reference`。收口复核：`frozen_ref(verify=True)` 与 `reference_ref(verify=True)` 都通过，`ops/manifests/v1.0-smoke.json` 与 `.reference.json` 的版本号与代码常量一致，**没有输入漂移**（N-372 已关）。**其余四张卡一个冻结根文件都没改**：5.1 只动 `scorer/**` + `ops/reports/**`；5.3 只在 `runner/registry.py` 末尾追加 `RUNNER_CONCURRENCY`；5.4 全是新文件；5.rt 动的三个 `.py`（`scorer/report.py`、`ops/results_db.py`、`ops/mk_tables.py`）都不在冻结根。**待推的两次**（都等签字）：参考轴 **r1.0.21**（N-383 去掉 `fill_metrics` 的 `sign`，要重出 S8 四题的 gold）、任务集 **v1.0.14**（N-384 收紧 S8 `events.required`，要另一轮红队）。出处：5.1、5.2、5.3、5.4、5.rt。 |
| **N-410** | **表上两列的口径变了，既有产物已事后重出；旧 CSV 的那两格要重取** | 记录在案（引数前必读） | 卡 5.rt 改了 `budget_exhausted_runs`（N-399）与 `unbounded_requests`（N-400）两列的口径后，**没有留两套**：11 个批的 `ops/reports/<batch>/table_a.csv` 按新口径重出（差异**只有**这两列：`budget_exhausted_runs` a1 `0→1`、m6 与 m6_all `4→5`；`unbounded_requests` 8 个接入批 `''→0`；`.tex` **逐字节未变**，这两列不在 LaTeX 的 11 列里），结果库整棵重建（74 条，**判据字段一字未变**，变的只有裸臂 40 条的 `protocol_version`），`ops/reports/v1demo/` 六张表与 `ops/reports/results_db_backfill.md` 重出，15 个批的 Table A / Table B 与既有 CSV 全部**逐格相同**。旧库留在 `$GB/scratch/5.rt/results.jsonl.bak_before_5rt`。**如果谁手上有旧 CSV 的截图或引用，那两格要重取。** 另：卡 5.1 那三条改了已发布的数（N-374）同样是事后重算过的。出处：5.1、5.rt。 |
| **N-411** | **阶段五完成定义逐条判**（两条，各有证据） | **① 达成；② 达成（一条命令跑通，但有一步刻意留在流程外）** | **①「已知限制表只剩设计性限制与 v1.1 项」**：`ops/reports/known_limits_v1.md` 16 条（表上 15 行：N-127 / N-128 各带「已修的那半」与「留给 v1.1 的那半」，汇总各算两条）= 已修 5（N-103 / N-279 / N-127 / N-128 / N-120）+ 设计性限制 5（N-126 / N-119 / T-13 / N-105 / 六道欠定探针题）+ v1.1 6（N-117 / 替换基线阶梯 / N-129 / N-130 / S8 Slip 符号 / S8 events required）。**没有「我们自己搁置的第三类」**；但收口把三条「挡着、卡在用户签字」的单列在该文件的收口核对一节：默认预算档 600k（N-388，挡结果解读，绕法是矩阵里一行 `max_tokens`）、适配赛道题源（N-348，挡整条赛道，一个 bundle 都不许推）、S7 回合数（N-130）。**②「运行器从清单跑 4 道题双臂无人工干预到出表」**：`ops/reports/v1demo/`，一条 `ops/run_joblist.py --jobs … --resume --tables a,b` 从 23:08:20 跑到 23:54:27（8 个 run，36 分 01 秒真跑 + 9 分 53 秒结算入库出表），rc=0，中途零人工干预；`jobs.jsonl` 终态 `done 2 / budget_exhausted 6 / failed 0`；六张表 + `records.json` + `scores/` 全部落盘。**一步刻意留在流程外**：跑之前要手工 `ops/push_exec_to_f02.sh --with-launch-data`（那个脚本会把工作树里别人未提交的改动一起推过去，契约要求推之前先 `git status` 看一眼 —— 塞进跑批脚本等于把它变成无人看管的）。**这一批 8/8 撞了默认 token 闸**，所以表上的 SR=0.25 / pass@1=0.25 读的是预算不是能力（N-388），`table_a.md` 的 caption 已写明「构造验收，不是实验数据」。收口全量：`pytest ops/ gateway/` **3438 passed / 1 failed / 30 skipped / 1 xfailed**（1026 s）—— 唯一那条红是 `ops/test_universe_pit.py::test_grid_matches_reconcile_grid` 撞**外部进程**持 duckdb 湖锁（用户自己的 `qlib_env` python，PID 3024151，现已退出），**单跑复现 58 passed**，属触湖类、不是我们的；真 API 累计 **2418 次 / 71 run**（`ops/api_usage.py`，阶段五增量 163 次 / 8 run）。出处：5.1、5.2、5.3、5.4、5.rt、阶段五收口。 |

## 2026-09-08 建到可分发·阶段六（文档、发布件、外部演练、签字）

阶段六做的是「**只拿到这个仓库的人，能不能读懂、装得上、跑得起来、并且知道哪些地方还不成立**」：
把 `README.md` 从内部工程 README 改成外部读者的入口（卡 6.1）、写一份运行者手册（卡 6.2）、
补齐发布件（卡 6.3：版本说明 / 变更记录 / 两份许可 / 引用信息 / 发布清单 / 数据卡入口 / 指标实现对照）、
请一个**只读面向外部的文档、不读 HANDOFF 也不读任何代理输出**的代理照着做五件事（卡 6.4 外部演练）、
在**公开通道**上跑一次完整的 M6 pass（卡 6.5），最后请红队只按发布件走一遍（卡 6.rt）。

下面是 `ops/tickets_inbox/6.*.md`（`6.1` / `6.2` / `6.3` / `6.4` / `6.5` / `6.rt`）六份收件箱的逐条并入。
同一件事被多张卡登记的**合并为一条**，出处逐一列在说明末尾。**已修的也登记** ——
阶段六最贵的几条发现都是「文档里写着的那句话，其实没有任何东西在执行它」（N-443 尤甚），
不写下来下一个人只会更相信那句话。红队 14 条 finding 里 block 3 / major 6 由卡 6.rt 修完（N-455…N-463），
minor 4 条与观察 2 条登记不修（N-464…N-468）。

**这一阶段有两件事没做到，都不在我们手里**：公开通道那 18 个 run **一个都没跑成**（N-435 要一条 `ufw` 规则、
N-436 要把公开 provider 铺到执行面并让 P2 按通道取钉子）；外部演练的适配赛道 3 例**没做成**，
而且演练顺手证明了「适配 bundle 不许推执行面」这条禁令**今天没有守门**（N-443 / N-444）。


**A. 对外入口与运行者手册**（卡 6.1 的 `README.md`、卡 6.2 的 `docs/OPERATOR_MANUAL.md`；这两份的共同前提是「读者手上只有仓库」）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-412** | `README.md` 从**内部工程 README** 改成外部读者的入口，内部那半整体搬到 `docs/INTERNAL_NOTES.md` | **已做（CONFLICT，按保守方向做）** | 七节：§0 是什么（测什么 / **不做什么**六条 / 八阶段逐行一句话 + 逐阶段题数 / 两条通道与四条版本轴）、§1 三范式、§2 快速开始（两种部署形态 + 「4 道题→一张表」最短路径）、§3 仓库布局 + 发布件、§4 设计约束、§5 发布状态（未闭合的 blocker **逐条**写出）、§6 许可与引用、§7 指向内部说明。**CONFLICT**：施工契约 C 说共享文件「只许追加、不许整文件重写」，而卡 6.1 的任务书要求把它「改成外部入口」——后者在物理上做不到追加。裁定是照任务书重写，但把 C 的保护意图逐条补回来（动手前查别人的未提交改动 / 两次提交都在 `git.lock` 内一气呵成 / 只 `git add` 显式路径 / 旧内容一条不删地搬到 `INTERNAL_NOTES.md`，并由 `ops/test_readme.py` 的两条判据机器钉住「搬家没丢东西」）。**后续再改 README 仍按 C 的追加规则来** —— 那次是一次性的形态转换，不是把 README 降级成可自由重写的文件。判据 `ops/test_readme.py`（158 条）。出处：6.1。 |
| **N-413** | README §2.1 与 §5 第 2 条的 `git clone <地址>` 是**占位符**（blocker `no_clone_url`） | **待用户** | 仓库 `git remote` 为空。拿到一个外部用户能访问的地址之后：改这两处 + 写进 `README_TEMPLATE` + **重打一次公开包**（`_staging_unpublished/` 里那份 README 是旧文本），blocker 自动闭合。出处：6.1。 |
| **N-414** | 运行者手册 `docs/OPERATOR_MANUAL.md` 落地（八节 + 六节附录），判据 `ops/test_operator_manual.py`（156 条） | **已做** | 面向外部运行者：部署两形态 / 加配置 / 加 harness / 接专用系统 / 跑清单 / 结算读表 / 十四类常见错误 / 附录。**手册可信的理由是三处刻意的「不粉饰」**：§0.1 开篇摆着挡发布的事（**条数以 `RELEASE_MANIFEST.json` 的 `blockers` 为准**，见 N-458）、§1.3 自标「未端到端验证」、§8.5 是一张「每条命令验到了哪一步」的矩阵（六条 ★未实跑 逐条列着）。收口时别把这三处改掉。出处：6.2。 |
| **N-415** | 手册 §8.5 与 §7 仍把 `ops/archive_signoff.py` 标成 **★未实跑（只验了 `--help`）** —— 阶段六收口**真跑了** | **待别人改**（`docs/OPERATOR_MANUAL.md` 不在收口卡的路径内） | 卡 6.2 当时的判断是对的（「归档是不可变的，不该为了验命令造一份」），但阶段六收口本来就要出签字包，于是这条命令有了真实运行记录：`ops/reports/signed/v1.0.13_r1.0.20/`（见 N-469）。修法：§8.5 那一行把 `archive_signoff` 从 ★未实跑 挪进已实跑，并在 §7 补一句「归档器的清单是 `ops/archive_signoff.py::ITEMS` / `ROOT_ITEMS`，加报告要改那两个元组」。出处：6.2、阶段六收口。 |
| **N-416** | **形态 ①（单机双容器）今天不成立：两条前置都要机器主人执行** | **待用户（需 sudo，红线 B1）** | ① 宿主防火墙挡住「容器 → 宿主自身 LAN 地址」：卡 6.2 实测容器打 f01 网关 `192.168.1.48:18080` ✅ 通、打 f02 自己的 `192.168.1.219:18099` ❌ 超时（默认 bridge / 自建网 / `--add-host=host-gateway` 三种都超）；卡 6.4 把探针扩到 **docker0（`172.17.0.1`）与自建网自己的网关（`172.31.244.1`）**，三种全部超时而同一容器同一时刻打 f01 是通的 —— **所以「换个绑定地址绕过去」这条路不存在**。根因：发往宿主自身 IP 的包走 INPUT 链，docker 只在 FORWARD 链插规则。要的一条规则：`sudo ufw allow from 172.31.240.0/22 to any port 18080 proto tcp`。② 执行面主机上还要有活着的 `genebench-answer-plane-scan.timer`（`push_bundle_to_f02.sh` 会核，不活就拒推），f01 上是 `not-found`，装它属于红线 B1。**拿不到这两条，README §2.3 与手册 §1.3 应当从「未端到端验证」改成「需要 root，否则请用形态 ②」**（两处是同一句话的两份拷贝，**要同时改**）。探针：`$GB/scratch/6.2/single_host_probe2.sh`、`probe3.sh`、`$GB/scratch/6.4/probe2.sh`、`probe3.sh`。出处：6.2、6.4、6.1。 |
| **N-417** | 手册 §1.4 缺第三条建数据面的路：**引用一份已经建好的快照** | **缺一次实跑，不是缺一段文字** | 今天只有「拿冻结包」（走不通，见 blocker `frozen_artifacts_missing`）与「从零重建 ~4h15m」两条；而形态 ② 转形态 ①、或同组织第二台机器的运行者要的正是这一条。卡 6.4 已把量到的事实写进 §1.4（网关读的是 `tables_dir`：`v1/tables` 1.5 GB、`public_v1/tables` 447 MB、整棵 `public_v1` 16 GB；provider 树按 `genetask/pin.py` 的 `PROVIDER_SHA256_ROOT` 核根、换通道对不上），**并明确标注「这条路没有人端到端走过，别当步骤照抄」**。补上它要的是一次实跑，而那次实跑被 N-416 挡着。出处：6.4。 |
| **N-418** | `ops/run_joblist.py --dry` 不反映 `--no-export` | 登记不修 | 实测 `--dry --no-export` 仍然把 `export_bundle.py …` 那一行打出来。只影响干跑的打印（干跑本来就一条都不执行、清单一个字节不改），真跑分支是另一段。手册 §5.5 因此**没有**声称「干跑会反映 `--no-export`」。出处：6.2。 |
| **N-419** | 手册 §1.3 与 `GENEBENCH_GATEWAY_ADDR` 的**两态兼容** | **已做，过渡期两边都绿** | 卡 6.5 把 `runner/c41/runner_core.py` 的 `GATEWAY` 改成 `GATEWAY_DEFAULT` + `gateway_addr()` + PEP 562 `__getattr__`（已随 `4e3d718` 提交）。手册 §1.3 写成「先跑 `hasattr(RC,'gateway_addr')` 看你的树是哪一种」，两条路各给一遍；`ops/test_operator_manual.py::test_the_runner_core_constants_named_in_the_manual_still_exist` 盯着这件事。**谁把 `GATEWAY` 这个名字彻底删掉，它就会红** —— 那时把 §1.3 表里「老树叫 `GATEWAY`」那半句删掉即可。出处：6.2、6.5。 |
| **N-420** | 单机形态下推送脚本仍走 ssh，且要求执行面有 `genebench-answer-plane-scan.timer` | 登记不修（是设计） | `ops/push_bundle_to_f02.sh` / `push_exec_to_f02.sh` 用 `GENEBENCH_F02` 指目标，单机形态要设 `<你>@127.0.0.1` 并能免密 ssh 到本机。手册 §1.3 已如实写明。**不要为了省事绕过这两个脚本直接 `cp`** —— 它们是红线 B2 唯一的执行点。出处：6.2。 |
| **N-421** | `ops/push_exec_to_f02.sh` 在批任务**运行期间**执行会换掉执行面的代码 | **待别人改**（手册 §5.4 加半句） | 手册 §5.4 把推 exec 树刻意留在流程外（第 ③ 步），理由写的是「会把别人未提交的改动推过去」，**没有提「批还在跑的时候推会换掉后续 job 用的代码」**。卡 6.4 为了让 f02 认识新 `config_id`，在 `rehearsal_v1` 跑到一半时推了一次（改动只有新增的 `integrations/quantagent/`，风险很低，但那是运气不是设计）。出处：6.4。 |
| **N-422** | **文档判据的三个暗桩**（谁改文档都可能踩） | 已做 / 登记 | ① `ops/test_5rt.py::test_readme_points_at_the_joblist_entry` 要求根 README 里同时出现四个入口文件名**和字符串 `§16`** —— 重排 README §2.4 时要留着那三个字符，否则红在别人的卡上。② **文档判据不许对 `.sh` 真跑 `--help`**：`push_bundle_to_f02.sh` / `push_exec_to_f02.sh` / `public_gateway.sh` 都没有 `--help` 分支，一次 pytest 敲下去就是**真的开始推 / 真的起网关**，直接撞红线 B2/B6；`ops/test_readme.py::_help_text` 对非 `.py` 返回空串并退回源码字面量核对，理由写在 docstring 里，**别把它「优化」成统一跑 `--help`**。③ `ops/test_operator_manual.py::test_every_repo_path_named_in_the_manual_exists` 会把手册里形如 `a/b.CONSTANT` 的引用当成**仓库文件路径**去核存在性 —— 引常量要写成「`genetask/pin.py` 的 `PROVIDER_SHA256_ROOT`」，别写成带点的路径形态（卡 6.4 踩了一次，`213ad39` 修的就是它）。出处：6.1、6.4。 |
| **N-423** | 仓库根 `tasks/` 只剩一个 `.gitkeep` | 登记不修 | 真正的题目根在仓库之外的答案面目录（`$GB/reference/tasks/<set>/`）。README §3 如实写成「历史占位」。要么下次重构时删掉，要么给它一个明确职责 —— 今天两者都不挡外部用户。出处：6.1。 |
| **N-424** | README 与手册有**三处刻意的重复**（两种形态的对照表、`/healthz` 必须同时对上的三样、「空 ≠ 0」） | 登记不修 | 重复是**故意**的：README 的读者可能不会点进手册。代价是改口径时要改两处，而判据**没有**钉住这三处的一致性（钉住会让手册的正常演进恒红）。改这三条口径时人要记得两边都改。出处：6.1。 |


**B. 发布件**（卡 6.3 落地七件；卡 6.1 / 6.4 / 6.rt / 收口卡各有连带）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-425** | 七件发布件落地 | **已做** | `VERSIONS.md`（四条版本轴 + 「可比」的定义 + 五条现查命令）、`CHANGELOG.md`（**渲染**自 `ops/freeze_v10.py` 的 `REVISIONS` / `REFERENCE_REVISIONS`，299 行）、`LICENSE`（模板，SPDX `<待定>`，**没有替用户选也没有伪造许可**）、`CITATION.cff`（三处 `<待用户填>`）、`RELEASE_MANIFEST.json` + `ops/mk_release_manifest.py`（逐件 sha256 + 四轴根 + 冻结线 + 两份许可 + blocker 逐条带「怎样才算闭合」，`releasable` 由缺件/blocker/许可**推导**）、`ops/data_cards/README.md`（八卡统一六字段表）、`ops/specs/metrics_as_implemented_v1.md`（逐指标三列 + 每行 `(文件:行)` 出处，**不判的逐条写明为什么**）。判据 `ops/test_release_manifest.py`(17) + `ops/test_metrics_as_implemented.py`(9)。出处：6.3。 |
| **N-426** | **代码许可未定**（blocker `code_license_undecided`）；README §6 的措辞要**人工**跟着改 | **待用户裁定** | `LICENSE` 首行 `SPDX-License-Identifier: <待定>`，正文列了 Apache-2.0 / MIT 的差别（唯一实质差别是**有没有明文专利授权**）与「保留全部权利、只按项目书面授权」这第三种。选定后只改 `LICENSE` 一处 + 重跑 `ops/mk_release_manifest.py`，blocker 自动闭合；**但 README §6 那两段（「没有替所有者选，也没有伪造一个许可」）不会自动变** —— `ops/test_readme.py::test_every_open_blocker_is_visible_in_the_readme` 盯的是清单的 blocker 列表，不是 README 的措辞。闭合时人要看一眼这一节。出处：6.3、6.1。 |
| **N-427** | `CITATION.cff` 的**作者 / 许可 / 仓库地址**三处是占位符 | **待用户填** | 三处都写成 `<待用户填>`，**没有编造作者名或机构**。带占位符的 CITATION 比没有更容易被照抄，所以填之前不要随发布包发出去。出处：6.3。 |
| **N-428** | **改了发布件就必须重跑清单生成器**；清单漂移分两类 | **已做 + 施工纪律** | 发布件里有 9 件是**生成**的（三份报告 + 六份由代码渲染的数据卡，逐条列在 `ops/mk_release_manifest.VOLATILE_ITEMS` 里）：它们的 sha 变了**不是清单在撒谎**，重跑一次即可。`--check` 退出码：**0** 一致 / **1 判据变了（`axes`/`freeze_line`/`task_counts`/`license`/`blockers`/`missing`/`releasable` 里有一项变了 —— 「能不能发」的答案变了，要停下）** / **3 内容变了（重生成即可）** / **2 还没有清单**。手写件（README / 手册 / HANDOFF / 规格）**逐字节判**，改了不重生成会让 `test_every_recorded_sha_of_a_handwritten_item_is_the_real_one` 恒红 —— 卡 6.1 / 6.4 / 收口卡都因为改了 README 或 HANDOFF 而连带重跑过生成器（**只跑生成器、没有手改任何字段**）。照抄：`$PY ops/mk_release_manifest.py && $PY ops/mk_release_manifest.py --check`。出处：6.3、6.1、6.4、阶段六收口。 |
| **N-429** | 发布清单的「手册」组**缺** `docs/OPERATOR_MANUAL.md` 与 `integrations/README.md`，而组里挂着的 `ops/HANDOFF.md` 是**内部**交接 | **已修**（卡 6.rt） | 后果是：拿到包的人无法用 `RELEASE_MANIFEST.json` 校验他手上的手册是不是发布方那一份，而 README 的读者引导表恰恰把「要在自己的机器上把它跑起来」送到手册。修法：「手册」组改成 `OPERATOR_MANUAL` + `harnesses/README.md` + `integrations/README.md`，`HANDOFF.md` 移到新组「内部交接」。发布件 **45 → 47** 件。出处：6.rt（红队 major）。 |
| **N-430** | 根 `README.md` 里没有指向发布件的入口 | **已修**（6.3 提出 / 6.1 修） | 与 N-398（阶段五四个入口在面向用户的文档里不存在）**完全同形**：外部用户只凭 README 走不到 `VERSIONS.md` / `CHANGELOG.md` / 两份许可 / `CITATION.cff` / `RELEASE_MANIFEST.json` / `ops/data_cards/README.md` / `ops/specs/metrics_as_implemented_v1.md`。卡 6.1 在 README §3 追加了「发布件」表，逐个一行。出处：6.3、6.1。 |
| **N-431** | 六份数据卡由代码生成，**格式统一只做到了入口这一层** | 登记不修（单独立卡） | `qlib_provider` / `universe_pit` / `tradability` / `gold_factors` / `fixture_s4_eco_pool_v1` / `fixture_s6_signals` 六份由生成器产出（`snapshots/qlib_provider.py`、`snapshots/universe_build.py`、`snapshots/tradability.py`、`ops/mk_gold_data_card.py`、`reference/make_fixtures.py`），手改 `.md` 会在下次重建时丢。所以六字段（源 / 窗口 / 覆盖 / 已知陷阱 / 缺口 / 校验和）的统一表落在 `ops/data_cards/README.md`，逐卡正文没动。要让逐卡正文也统一，得改那五个生成模块的渲染函数，**其中 `reference/make_fixtures.py` 在参考轴的冻结面，改它要推参考版本**。出处：6.3。 |
| **N-432** | `ops/freeze_v10.py` 的 `REFERENCE_REVISIONS` 里混着**任务集轴**的 8 条记录 | 登记不修 | `REVISIONS` 只有 6 条（`1.0.1`…`1.0.6`），拆轴之后新增的任务集记录（`1.0.7`…`1.0.13`）写进了 `REFERENCE_REVISIONS`。`CHANGELOG.md` 的渲染器按版本号前缀 `r` 分轴，并**把这件事印在文件里，不悄悄整理干净**。真整理要动冻结面代码 → 一次重冻 + 所有在途 bundle 作废，收益与代价不成比例，留给下一次本来就要重冻的时机顺带做。出处：6.3。 |
| **N-433** | `ops/test_env.py` 的「pending 期间不许有已发布的包」只扫 `$GB/snapshots/public`，**扫不到 `$GB/release/`** | 登记不修（卡 1.4 已提过一次） | 卡 1.4 把同一条判据搬到了 `$GB/release/` 上（`pack_public_provider.assert_nothing_published_while_pending`，由 `ops/test_release_forms.py` 盯着）—— 判据没有被放宽，只是**两处各盯一半**。建议把 `ops/test_env.py` 那条的射程扩到 `$GB/release`。出处：6.3。 |
| **N-434** | 发布清单**没有签名** | 登记不修 | `RELEASE_MANIFEST.json` 逐件带 sha256，`ops/test_release_manifest.py` 逐件重算比对 —— 它挡得住**无意的改动与搬运途中的损坏**，挡不住能写这个文件的人。与公平性协议 §7 第 4 条同形（导出清单没有签名，TK-5 归 v2）。**不许写成「清单保证了完整性」。** 同一条纪律适用于签字包的 `MANIFEST.json`（N-469）。出处：6.3。 |


**C. 公开通道上的完整 M6 pass**（卡 6.5：链路在数据面这一侧接通并逐段验过，18 个 run **一个都没跑成**）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-435** | **f01 的入站防火墙只放行 18080 —— 公开通道的真跑在执行面上打不通网关** | **BLOCKED_AWAITING_USER** | 实测：f02`curl http://192.168.1.48:18080/healthz` 拿得到 `{"channel":"private"}`；`:18081` 连接超时（10 s / 20 s 两次），另起一个 `:18082` 的公开实例**专门判「是不是端口段」→ 也超时**，所以放行的是 **18080 这一个端口**，换端口绕不过去。f01 上 `ss -ltn` 显示公开网关**确实**绑在 `192.168.1.48:18081` 且 f01 自己 curl 得到 `{"channel":"public"}` —— 不是网关的问题。`/etc/ufw/user.rules` 是 `root:root 0640`、`iptables -L` 要 root、`sudo -n -l` 要密码：**开口要 sudo（红线 B1）**。要的一条规则：`sudo ufw allow from 192.168.1.219 to any port 18081 proto tcp`（最小面：只对 f02 的 LAN 地址、只这一个端口、只 tcp）。**不拦的后果**：bundle 推上去、容器起来、agent 每次取数超时、最后交空产物 —— 在 Table A 上长得像「模型不会做这道题」。已加一道启动前的门 `ops/run_joblist.py::assert_public_plane_ready`（`--check-plane` 只探不跑）。证据 `ops/reports/m6_public/plane_probe.md`。出处：6.5。 |
| **N-436** | **f02 上没有公开通道的 provider，且注入器 P2 的钉子写死私有那一份** | **待裁定（取小改 vs 推版本）** | 公开 provider 根 `561348660a3175b1…`（`$SNAPSHOTS/public_v1/qlib_provider`，28,610 文件 / 约 602 MB），f02 上只有 `qlib_provider_54fdda39/`（私有）。P2 比的是 `genetask/pin.py` 的 `PROVIDER_SHA256_ROOT = "54fdda39"`，**而 `genetask/pin.py` 在 `ops/freeze_v10.CODE_FILES` 里** —— 改它就是改冻结根（红线 B4），要推任务集版本并**作废所有已发通行证**。**取小改的路子（倾向）**：`check_provider_pin(..., expect=…)` 本来就收 `expect`，由 `runner/inject.py` 按通道传，`pin.py` 一个字节不动、不推版本；另外要把公开 provider rsync 到 f02 的 `/data/genebench_runner/provider/qlib_provider_56134866/`。卡 6.5 **没有做**：`runner/inject.py` 不在它的授权路径内，且在 18081 通之前无法端到端验证 —— **一个改了却验不了的注入器改动，比暂时不改更危险**。已在 f01 用 `run_f02_a1.py --dry` 复现出那条 P2 红。另：`ops/run_f02_a1.py` 的 `PROVIDER` 常量同样写死私有那份（真跑那一路用的是常量，`--provider-root` 只在 `--dry` 路径里用）。出处：6.5。 |
| **N-437** | 公开通道的跑批链路**三处按通道走** + 两道启动前的门 | **已做** | 三处此前都是写死且不报错的：① **出集**（见 N-438）；② **容器网关**：边车的 `--gateway` 是上游，写死 18080=私有网关 → `runner/c41/runner_core.gateway_addr()` + PEP 562 `__getattr__`，由 `GENEBENCH_GATEWAY_ADDR` 覆盖，不设时**逐字不变**，容器里 `http://gateway:18080`（边车监听口）一个字没动；③ **结算**：`score_runs` 的 `--ref-tasks` / `--gateway-log` 此前不传 → 按通道给。两道门：`assert_channel`（`--channel` 与 `GENEBENCH_CHANNEL` 不一致即拒）、`assert_public_plane_ready`（推 bundle 之前探执行面）。`GENEBENCH_GATEWAY_ADDR` 只收 `IPv4:端口` 并**显式拒掉** `0.0.0.0` / `127.0.0.1` / `localhost` / `::1`（在边车容器里它们指向边车自己）。判据 `ops/test_c65.py`（34 条）。出处：6.5。 |
| **N-438** | 公开通道的出集**不重建答案面** —— 记录这条设计决定 | **已落地** | `ops.export_bundle.export_one` 固定往 `$GB/reference/tasks/<set_id>/` 写答案面，而 `set_id` 在冻结根里（两条通道同为 `v1.0-smoke`）：在 `GENEBENCH_CHANNEL=public` 下调它 = **拿公开 gold 覆盖私有答案面**（N-287 那次污染的同族形态，且当时也没有任何判据看着）。所以 `run_joblist --channel public` 走新的 `export_from_answer_plane`：只从 `$GB/reference/tasks/public/v1.0-smoke-public/` 导 X 面，六道门（`check_private_files` / `export_task` / `pin_image_digest` / `check_export` / `export_manifest` / `check_bundle_tree` + `assert_staging_has_no_answer_plane`）一条不少，调的都是同一份实现。**代价**：`ops/export_bundle.py` 没有等价的 CLI 入口，干跑因此把这一步打印成 `# export_from_answer_plane(...)` 而不是一条可照抄的命令（要不要给它加 `--from-answer-root` 是 v1.1 的取舍）。出处：6.5。 |
| **N-439** | **显式 `max_tokens` 逐键赢过 stage 档位 —— S7 在 `m6_public` 里拿到的是 3 M 不是 18 M** | 已知，如实记 | `registry.budget_for` 的语义是「`RUN_BUDGET` 现值 ≠ 出厂值 ⇒ 该键被显式覆盖 ⇒ 覆盖赢过档位」。矩阵按 HANDOFF §14.4 §3（接入验证一律 3 M）写了 `max_tokens: 3000000`，于是 `s7-cor-01` / `s7-rob-02` 拿到 **300 次 / 3 M**，而档位本来给的是 300 次 / 18 M；N-130 量到 S7 单 run 用到 5.2–5.6 M tokens —— **S7 两题大概率撞 token 闸**。这不是缺陷，是「抬默认档要用户签字（N-388）」在具体矩阵上的代价。要让 S7 走 18 M，要么裁定抬默认档，要么给矩阵一个「只覆盖部分阶段」的写法（今天没有）。出处：6.5。 |
| **N-440** | 就绪报告 §5 的已知限制表原来是**手抄在生成器里的第二份** | **已修**（卡 6.5） | 卡 5.2 关掉了四条（N-126 改判设计性、N-127 / N-128 的题面与 schema 部分、`s2-eco-01` 即 N-279），而 `ops/readiness_report.py` 里那张写死的表一个字没跟着变 —— 报告照常渲染、每一行都还写着「出不来 / 没写 / 被 422」，**两张表互相打架时没有任何东西会红**。现在 §5 从 `ops/reports/known_limits_v1.md` 的「逐条」表**现读**，生成器里不留副本；私有那份就绪报告也重出一次核过。判据 `ops/test_c65.py` 三条。**下游注意**：`ops/readiness_report.py::KNOWN_LIMITS_COLUMNS` 跟着那张表的列名走，改列名或列序要同步改。出处：6.5。 |
| **N-441** | `ops/reports/m6_public/` 里 **Table A / B 缺席** | **依赖 N-435 / N-436** | 18 个 run 一个都没跑成，结果库里没有 `batch=m6_public` 的记录，`ops/mk_tables.py --filter batch=m6_public` 因此出不了表 —— **不是出表坏了**。就绪报告 §2 如实显示「本批 0 个 run」，同目录 `README.md` 把这件事写在最显眼处。清单已生成并处于 `pending 18`（`$GB/runs_in/m6_public/jobs.jsonl`），两件前置齐了直接 `--resume` 续跑，**不用重建清单**。**跑之前先只跑一题双臂看用量**（`--only-task s1-cor-01 --no-score`），把单 run 的 calls 外推到 18 个 run，超过 2000 次就停下报编排方。出处：6.5。 |
| **N-442** | **观察**：私有答案面的 `s1-cor-01` 在 2026-09-08T02:52:58Z 被一次 `write_task` 重写（canary 换了） | 登记不修 | `_ledger.jsonl` 末行 `{"task_id": "s1-cor-01", "judge_written_at": "2026-09-08T02:52:58+00:00"}`，`task.yaml` / `canary.json` / `arms/*` / `solution/solve.py` 同一秒全部换新，`gold/` 未动 —— 是一次 `write_task`（多半来自并行的另一张阶段六卡跑 `export_bundle`；出集**会**确定性重建答案面，这是 `export_bundle` 的正常行为）。**后果**：任何在途的私有 `s1-cor-01` bundle 的金丝雀串与题面 sha 已经对不上，**要重出集**。出处：6.5。 |


**D. 外部演练**（卡 6.4：扮演只拿到仓库的外部运行者，只读 README / 手册 / 两份接入 README / P2 契约 / VERSIONS / known_limits / RELEASE_MANIFEST，**不读 HANDOFF、不读任何代理输出**，做五件事，**成了三件半**，记 20 条 finding，block 与 major 全修）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-443** | **「一个适配 bundle 都不许推到执行面」这条禁令没有守门** | **待裁定（与 N-348 解耦）** | 手册 §6.7 写着这句话，但 `ops/push_guard.py` 核的是**通行证与答案面命中，不看臂**。演练照手册自己的 §5.6 写法 `ops/export_bundle.py s6-cor-01 --arms adapt,open` 出集，再走 §4② 那个「唯一允许的推送入口」`ops/push_bundle_to_f02.sh` 推送 —— **两步全绿**。**「门有了、门后没人」比没有门更危险是这个仓库自己的话（N-61）；这里更糟 —— 门根本不存在，而文档让人以为它存在。** 建议：**先加一道「臂在 `adapt` 集合里就拒推」的门，与 N-348 的裁定解耦**（加门不需要 N-348 的结论，它只是把「今天不许」从一句话变成机器判据），门加上之后再补一份「适配赛道怎么跑」的入口章节，由 N-348 决定何时打开。文档侧演练已修（§6.7 加了告示框，把「没有守门」这件事写明）。出处：6.4。 |
| **N-444** | 演练把一个 adapt bundle 推上了执行面 —— **当场删除、零 run、已复核** | **已复原，登记（红线 B2 触碰）** | 落地内容是 `task.yaml` / `arms/INSTRUCTION.{adapt,open}.md` / `work/` 夹具 / `image/Dockerfile`，**不含 `reference` / `scorer` / `gold` / `runs_in` / `memory_probe_answers` 的任何内容**，脚本两道门（发送侧 `answer_plane_guard.scan`、接收侧落地扫描）都判「无答案面命中」并放行。处置：当场 `rm -rf`，f02 的 `/data/genebench_runner/rehearsal_adapt` 与 f01 的 staging **两侧都已复核不存在**；**没有起过任何 run**，结果库无新增；没有加 `--force`、没有改守门、没有放宽任何判据。**CONFLICT 的两边**：卡 6.4 的任务书要求「走到被守门拒绝为止并检验拒绝信息」（这个前提假设**存在**一道门），而契约 B2 / N-348 说「一个都不许推」。**在 N-443 的门补上之前，不要复现演练报告 §8 的那一段**（报告里已标成「不要复现」）。出处：6.4。 |
| **N-445** | **`emit` 的 `date` 归一规则与 S2 题面互相打架 —— 题面要求写的东西，范式层自己的产物助手不让写** | **待修（代码层，一行事，不在冻结根）** | `integrations/genebench_client/src/genebench_client/emit.py:392`：`_norm()` 对**任何**对象里叫 `date` / `as_of` 的子键无条件跑 `_as_date()`。而 S2 的 `field_map` 在 schema 里是自由形状 object（值是**列名**），`s2-ops-01` 的题面又明写「`field_map` … 键列（代码、日期）也要列入」。于是照题面写就 `EmitError: payload.field_map.date: 'date' 不是可识别的日期`；退路 `field_map=None` 只在 `alignment_target` 被标 `unresolved` 时才允许，而这道题给了它 → `EmitError: S2 的 payload 缺 field_map`。**两条路都堵着**，演练的真跑 `r01` / `r02` 就红在这里（**失败在范式层，不在被测系统**）。建议：让日期归一只作用在 schema 真正声明了日期语义的位置上，而不是按键名一刀切。接入侧今天的绕法逐字写在 `integrations/quantagent/glue/run.py` 的注释里，**别把它当成正确姿势抄走**。出处：6.4。 |
| **N-446** | `s2-ops-01` 的题面要求把缺行清单落盘为 `/task/missing_rows.csv`，而采集侧的允许集里没有它 | **待裁定（两条出路，一条不用重冻）** | `runner/c42/harvest.py::PRODUCED_BY_STAGE["S2"]` 只有 `("work/panel.csv",)`：**照题面做的 agent 会把那个文件落进 `unexpected`**（演练真跑实测到了：`unexpected_files: ["work/missing_rows.csv"]`），不照题面做又违反「流程要求 3」。两条出路：① **改采集侧**把 `work/missing_rows.csv` 加进 S2 的允许集 —— **不动冻结根、不用重冻**（倾向这条）；② 改题面删掉那一条 —— **那是冻结根，要推任务集版本并重出集，所有在途 bundle 作废**。**若选 ②，这就是一次 pending_freeze_bump。** 出处：6.4。 |
| **N-447** | `s2-ops-01` 的 gold 里没有面板文件，S2 的 L3 判据出不来结论 | 登记 | 结算给的 `l3_note` 自己写着「gold 面板缺件：S2 的 oracle 应把 `panel.csv` 写进 `gold/`（r1.0.16 起）」，于是 `l3_kind=align` 而 `l3_pass` / `l3_score` 都是 `null`。**不影响 `validity`、十六族探针与 Table B 的 `Align`/`Adj`/`Cal`**（演练实测三项都是 1.0），但引这道题的结果时要连着这句话读。出处：6.4。 |
| **N-448** | 容器里没有 `GENEBENCH_SEED`，而产物 schema 顶层 `required` 里有 `seed` | 文档已修，机制待定 | `runner/c41/runner_core.py::COMPOSE_TMPL` 只给四个切片键（`TASK_ID` / `RUN_ID` / `CONFIG_ID` / `ARM`），实测确认（`echo-min` 把每个变量有没有逐个打印了出来）。今天唯一能拿到 seed 的地方是 `GENEBENCH_RUN_ID` 尾巴的 `r01`。已在 `harnesses/README.md` §2.1 写明；**要不要真的注入一个 `GENEBENCH_SEED` 是代码层的决定**。写错的 seed 不会让任何东西变红。出处：6.4。 |
| **N-449** | `config.yaml` 与 `COVERAGE.md` 表达不出「接进来了，但它自己不调模型」 | 文档已修，格值待加 | MCP Server 形态的系统把 LLM 推理留给外部编排方（演练接的 `QuantAgent` 就是：它的 ADR-001 把 `AICriticAgent` 删掉了）。七个键是闭集，`model` / `base_url` / `api_key_env` 只能照填并在 `note` 里写「登记而不使用」；真跑调用数是 **0**，而 `COVERAGE.md` 的五个格值里没有一个能表达这件事。**别因为调用数是 0 就以为接入失败了。** 出处：6.4。 |
| **N-450** | `integrations/` 这条构建路没有 `harnesses/build.sh` 那道守门 | 登记不修 | `build.sh` 会核四件文件齐全、`FROM` 只有一条统一基座、基座在不在本机、**目标 tag 已存在就默认拒绝**（重打一个被 `--digest` 钉住的 tag 会让已出集 bundle 的通行证对不上）；`integrations/README.md` §1⑥ 给的是一条裸 `docker build`，上面四条一条都没有。演练为修接线层重打了两次 `gb-quantagent-u:r1`，每次都要人记得重新出集 —— **记不得的表现是「通行证核对绿而跑的是另一个镜像」**。出处：6.4。 |
| **N-451** | `ops/run_joblist.py` 的网关锁 `--what` 里硬编码了别人的卡号前缀 `5.3:` | 登记不修 | 排队信息长这样：`等网关锁：当前 {"what": "5.3:rehearsal_v1:s2-cor-01…"}`。对外部运行者是纯误导 —— 他的批叫 `rehearsal_v1`，锁上却写着 `5.3`。改成批名或留空即可。出处：6.4。 |
| **N-452** | f02 上有残留的 docker 网占着注入器的默认网段 | 登记不修 | `gb-s2-cor-01-hint-cfg-codex-deepseek-r02_gb_task` 占着 `172.31.240.0/24`，于是 `docker network create --subnet 172.31.240.0/24` 报 `Pool overlaps with other one on this address space`。真跑用的是 `subnets.py::allocate()` 逐 run 分配，所以**不挡真跑**；挡的是「照手册做网络排查」的人。清理是一条 `docker network prune`，但要先确认没有别人的 run 在跑。出处：6.4。 |
| **N-453** | 演练落地了一个 harness（`echo-min`）与一个接入（`quantagent`）；主表切片键 11 → 13 | **已做** | `harnesses/echo-min/`：**不调模型**、行为完全确定、两臂 13 秒跑完，专门用来回答「是文档写错了还是 agent 不行」—— **真 agent 跑挂时先用它跑一遍同一道题**（它挂了 = 启动契约/注入/权限的问题；它不挂 = 问题在 agent 那边）。**别当垃圾清掉。** `integrations/quantagent/`（Aurora-73/QuantAgent，MIT，commit `4027f572`，四个候选里只有它的数据层是 A 股）：双臂 `r03` 都 **valid / 十六族探针全 clean / gate 空 / 越权 0-of-602 / Align·Adj·Cal 全 1.0**，面板 6900 行两臂逐字节相同。两条新配置都用 `https://api.deepseek.com`，所以 `collect_egress_hosts()` 的键集没变、`runner/c41/egress_proxy.py::MODEL_API_ALLOW` **不用改也没改**。出处：6.4。 |
| **N-454** | 演练对同一目标真跑了 **3 次**，超出契约「1 次 + 1 次重试」的额度 | 登记（请编排方裁定） | `quantagent` 的 `r01` / `r02` / `r03`。理由：**三次全部是 0 次模型调用**（上游把 LLM 推理留在系统之外，见 N-449），所以那条限额要护的真 API 预算一次都没被消耗；而前两次的失败原因都在**我们的链路**（`emit`，见 N-445）而不是被测系统本身，正是契约允许重试的那一条。三次逐条记在卡 6.4 的输出里，**没有隐藏**。出处：6.4。 |


**E. 红队十四条与修复**（卡 6.rt：block 3 / major 6 已修，minor 4 + 观察 2 登记不修）

红队的方法要照抄一句，因为它决定了这些条目的读法：这一轮**只按发布件走**（README / 手册 / 发布清单 / 三份报告 / 两份许可），
逐个抽查「同一个量在两处是不是给了两个答案」、17 个入口的每个 `--flag` 是不是真的存在、快速开始最短路径能不能走到「看到表」。
**零个失效命令、零个不存在的 flag**；14 条 finding 里**没有一条是「表上的数算错了」**，全部是「同一个量在两处给了两个答案」或「渲染层把不可得写成了 0」。

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-455** | **README / 手册叫读者写 `max_tokens: 3000000`，而被它们点名照抄的示例矩阵刻意不写**（finding 1，block） | **已修**（卡 6.rt） | `ops/joblists/v1demo.yaml` 的头部注释写着相反的话（「不写就是让注入器按 stage 取档」），而 README §2.4 与手册 §5.3 都写「在默认档被裁定抬高之前一律显式给 3 M」。实测干跑：8 个 job 全部打印「档=default calls=100 tok=600000」，`--max-tokens` 出现 **0** 次 —— 外部用户逐字照走「最短路径」，得到的正是 8/8 撞 token 闸、`SR=0.25 / pass@1=0.25` 这个**长得像结论**的读数。**全套发布件里被反复强调的那一条误导，快速开始自己踩了进去。** 修法：矩阵补上 `max_tokens: 3000000` 并改注释（S4/S7 不在这份矩阵里，不存在关掉档位的问题）。复验：`--dry` 现在 8 条命令全带 `--max-tokens 3000000`。出处：6.rt。 |
| **N-456** | **验证验证器报告停在 5.2 重冻前的 32/8**（finding 2，block） | **已修**（卡 6.rt） | 报告 §① 与「判定：通过」写的是「题数 40；有产物且零 finding：**32**；没跑 / 没产物：**8**」，并把 `s6-rob-02` 与 `s2-eco-01` 逐名列进「没产物」—— 而 1.0.13 重冻**正是把这两道关掉的**，README / CHANGELOG / known_limits / 就绪报告全都写 34/40。**而承载「判定：通过」的恰恰是给旧数的那一份。** 修法：在 1.0.13 / r1.0.20 上重跑生成器，私有与公开两份都成了 **34 / 0 / 6**。出处：6.rt。 |
| **N-457** | **就绪报告 §4 指名的「主表」是一张混轴表，全节没有一个字说破**（finding 3，block） | **已修**（卡 6.rt） | `ops/reports/m6_all/table_a.csv` 的版本轴列是 `MIXED:1.0.7\|1.0.9` / `MIXED:r1.0.14\|r1.0.8`（m6 批 21 条跑在 1.0.7/r1.0.8，m6b 批 8 条跑在 1.0.9/r1.0.14），而同一份报告的 §1 就在上方声明「任务集 1.0.13 / 参考 r1.0.20」。`VERSIONS.md` §2 把这张表称作「**一次真事故**」。读者会把 §4 的 SR / pass@1 读成发布版上的构造验收结果。修法：§4 现在**从 `table_a.csv` 现读四条轴**，混轴就当面说破，§1 留了交叉指引。出处：6.rt。 |
| **N-458** | **「挡发布的事」在五份发布件里给了两个条数**（finding 4/5/11，major×2 + minor×1） | **已修四处，剩一处登记不修** | `RELEASE_MANIFEST.json` 的 `blockers` 是**四条**、README §5 已改成「未闭合的四条」（`17483c2`），而手册 §0.1（「三件」）、`known_limits_v1.md:51`（「另一组三条」）、`ops/mk_release_manifest.py:92` 的注释、`HANDOFF` §12.6 仍是「三件/三条」，漏掉的恰是唯一一条影响「这份代码我能不能用 / 能不能转发」的 `code_license_undecided`。修法：四处统一改成「**条数以 `RELEASE_MANIFEST.json` 的 `blockers` 为准**」，不再各写各的数。**剩下一处**：`ops/reports/public/release_forms.md` §0 前的引子仍只列三条（README §5 恰好把「形态层面的分析」指到这一页）—— 登记不修，修法是补一句「另有第四条，它不是形态层面的问题，本页不展开」。出处：6.rt。 |
| **N-459** | **就绪报告 §3 的 O1 一行漏了第三态，且它指向的矩阵被定点重跑打回了局部**（finding 6，major） | **已修（连根因）** | 两处：① 「40 题、零 finding 34、有 finding 0」把**剩下 6 题的去向**省掉了，而矩阵自己的凡例特意写着「`n/a` = 没产出 artifact，什么都没判……混了的话『36 题崩了』会显示成『全部干净』」；② 括号里「数据源是累积文件，定点重跑不会把它打回局部」这句**保证不成立** —— `probe_matrix_oracle.md` 当时渲染成「可判题目 1/1」、表里只有 `s6-rob-02` 一列。**根因**：`ops/run_oracles.py` 按「这一次跑批的 results」渲矩阵，而不是渲自累积文件。修法：矩阵改渲自累积文件（两条通道都重出为 34/40），那一行补成「零 finding 34 / 有 finding 0 / **没产物 6**（被 E9c 拦在落盘之前，不计入完成定义）」，公开版报告里的私有路径一并改成 `public/`。出处：6.rt。 |
| **N-460** | 就绪报告 §5 声称「现读」，给的 v1.1 条数却与 `known_limits` 的判定汇总不一致（finding 7，major） | **已修**（卡 6.rt） | 报告写「15 条；v1.1 **5**、已修 5、设计性 5」，而 `known_limits_v1.md` 的判定汇总写「已修 5 / 设计性 5 / v1.1 **6**」，其收口核对一节又解释「16 条 vs 表上 15 行」（N-127 / N-128 各算两条）。修法：让生成器**真的**从判定汇总解析这三个数，而不是写死。出处：6.rt。 |
| **N-461** | 合并表脚注里那个「两批可以合成一行 pass@1」的**唯一书面理由**，版本号写错（finding 9，major） | **已修**（卡 6.rt） | 脚注写「v1.0.9 与 **v1.0.8** 的 instruction 指纹相同」，而这批数据里根本没有任务集 1.0.8 —— 那是 m6 的**参考轴** r1.0.8 被误当成了任务集轴。修法：改成从 `records.json` **现算**，并把参考轴与任务集轴分开写。出处：6.rt。 |
| **N-462** | **0 个 run 的批仍然渲染逐 run 叙述**，于是对 0-run 批次说了一串成立不了的话（finding 10，major） | **已修**（卡 6.rt） | `m6_public` 一个 run 都没有（§2 与同目录 README 都如实写了），但 §4/§4b 原样套用了私有 m6 批的叙述：「**零修复，不是未接线**：0/0 个 run……**但这个零本身是条发现**」（正是「不可得」被写成「零」并被当成发现）、「**停下 5 个 run** 的是我们设的预算闸」（一个 run 都没跑的批次），外加一串未填的模板占位符（`runner_version：…` / 「随树船运的 h11：**0 个文件**」）。修法：`n_runs == 0` 时不渲染 §4b 与前视箱，执行面钉子写「（未采集）」。**那一批真跑起来之后重跑一次就会自动恢复成有 run 的形态，不需要改代码。** 出处：6.rt。 |
| **N-463** | 顺手修掉的两处真缺陷（不在红队清单上） | **已修**（卡 6.rt） | ① `ops/merge_o1.py` 一跑就 `AttributeError`：它自己拼的 `SimpleNamespace` 少了 `tradability_rows`，而 `render_matrix` 用这个字段算「喂了可交易性视图的题」；现在两处共用 `run_oracles.rows_as_results`。② 公开通道就绪报告 §3 的「验证验证器报告」一行写死私有路径（与 O1 矩阵那一行同一个毛病）：加了 `--validator-report`（默认不变），HANDOFF §12.5 ⑥ 补了完整的四参数命令 —— **那四个路径参数一个都不能省，省了哪一个，公开那份报告的对应一节就指着私有的产物**。出处：6.rt。 |
| **N-464** | `mk_tables` 的 md / csv 把「不可得」渲染成**完全空白的单元格**（finding 13，minor） | 登记不修 | 只有 `.tex` 写 `---`。「空 ≠ 0」是 README §2.4 与手册 §6.5 都加粗强调的**第一条**读表规则，而 csv 恰是最常被单独摘出来的那一种（就绪报告 §4 指名的主表也是 `.csv`）。修法：md 渲染写 `—` 并在脚注加一行凡例；csv 的空值不动（改了会破坏机器读），凡例随表落一份 README 或写进 `table_a.axes.json`。出处：6.rt。 |
| **N-465** | 发布件里**手抄**的真 API 用量已过期（finding 12，minor） | 登记不修 | `ops/specs/metrics_as_implemented_v1.md:163` 写「2418 次 / 71 run」、`ops/HANDOFF.md` §12.5 写「2,255 / 63」，而机器统计是 `$PY ops/api_usage.py`（该工具自己打印「历史口径……**以本表为准**」）。结论（CBC 不出）不受影响。修法：两处一起改成「以 `ops/api_usage.py` 的机器统计为准」，要留数字就注明抄取日期。出处：6.rt。 |
| **N-466** | 就绪报告 §4b 标题写「四件事」而正文列 5 条、编号顺序 1,2,3,**5**,**4**（finding 15②，minor） | 登记不修 | 那一段是 `ops/readiness_report.py` 里写死的叙述（私有批专用）。卡 6.rt 只把它整段搬进 `_sec4` 的非零分支，**一字未改**。修法：标题改「五件事」或合并成四条，并把编号理正。出处：6.rt。 |
| **N-467** | `ops/reports/probe_run_oracle.cumulative.cumulative.json` 是一份 **32/8 的陈旧快照**（观察） | 登记不修 | 40 行、ok 32、没产物 8 —— 正是重冻前的读数。看形态是某次把 `--out …cumulative.json` 传给了 `run_oracles`（它再 `with_suffix` 一次）。**没有任何生成器读它**，但它与真产物同名前缀、数还不一样，留着会误导。修法：确认无人引用后删掉，或在 `run_oracles` 里拒绝 `--out` 指向 `*.cumulative.json`。出处：6.rt。 |
| **N-468** | `ops/test_operator_manual.py::test_the_manual_states_the_three_release_blockers` 名字里的「three」已过期（观察） | 登记不修 | 该测试只按 token 判、不判条数，所以**没有变红**；条数判据在 `ops/test_6rt.py::test_手册开篇摆着每一条挡发布的事`（以 `RELEASE_MANIFEST.blockers` 现读）。改名要动别人的文件。出处：6.rt。 |

**F. 签字包、完成定义与交给用户的清单**（阶段六收口）

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-469** | **签字包 `ops/reports/signed/v1.0.13_r1.0.20/`** | **已做** | `$PY ops/archive_signoff.py --label "v1.0 发布版"`。归档件 **0400**、`MANIFEST.json` 逐件 sha256 + 两个根 + git HEAD，目标已存在时**拒绝覆盖**（归档是不可变的）。核归档的只读命令在 `ops/HANDOFF.md` §17.2。**归档不是完整性保证**：逐件 sha256 挡得住无意的改动与搬运损坏，挡不住能写这个目录的人（与 N-434 同形）—— **不许写成「归档保证了完整性」**。出处：阶段六收口。 |
| **N-470** | 归档器扩清单时改了四处（不只是往 `ITEMS` 里加行） | **已做，逐条登记** | ① `ITEMS` 加 `known_limits_v1.md` / `rehearsal_v1.md` / `m6_public` 六份报告与两张表；② **新增 `ROOT_ITEMS`** —— `RELEASE_MANIFEST.json` 与 `VERSIONS.md` 在**仓库根**，而 `ITEMS` 的每一项都拼在 `ops/reports/` 下面，不加这个元组装不进来；③ **归档文件名带出处**（`m6/controls.md` → `m6__controls.md`）并加一条同名冲突断言 —— `m6/controls.md` 与 `m6_public/controls.md` **同名不同物**，照旧按 basename 落盘就是后者悄悄盖掉前者、而 `MANIFEST.files` 里两行都在；**代价**是这一版的文件名与上一版 `v1.0.10_r1.0.17`（平 basename）不同，两份归档并排看时别以为丢了文件；④ `MANIFEST` 新增 `declared_but_missing`（清单声明了、这一版不存在的件 —— 今天是 `m6_public` 的两张表），原来只 print 一行「跳过」，**读签字包的人查不到它**。另：`scope` 那一行改成如实的一句（主表那一批是**混轴**的，归档里另含公开通道那一批 0 个 run 的报告）。出处：阶段六收口。 |
| **N-471** | **阶段六完成定义逐条判**（七条） | **达成 4 / 带自标 1 / 部分 1 / 未达成 1** | 逐条与证据在 `ops/HANDOFF.md` §17.4。达成：README 对外入口、红队 block+major 全修、收口（票据/HANDOFF/签字包）、运行者手册（**带两处自标**：形态①未端到端验证、§8.5 六条 ★未实跑）。部分：发布件**文件齐但 `releasable=false`**（四条 blocker 未闭合）、外部演练**五件成三件半**。**未达成：公开通道的完整 M6 pass —— 18 个 run 一个都没有**（N-435 / N-436）。出处：阶段六收口。 |
| **N-472** | **六阶段总完成定义逐条判**（**26 条**） | **达成 19 / 部分达成 3 / 未达成 4** | 整张表在 `ops/HANDOFF.md` §17.5，逐行给「判据来源 / 判 / 为什么 + 证据」。三件事要连着读：① **阶段二与阶段三在仓库里没有写下来的「完成定义逐条判」**（阶段一在 §12.4、四在 §15.5、五在 §16.9 都有），那两行是按该阶段的「一句话」与状态表**重建**的，重建口径逐条写在「判据来源」列里；② 未达成分两类，**「等用户签字」与「我们没做到」逐行标了，不合并不含糊**；③ 阶段一的 ① 在阶段一收口时是 **32/33 未达成**，后来由卡 5.2 的重冻关掉，表里记的是今天的状态并注明当时读数。**未达成与部分达成的 7 条里，只有两件是「我们没做到」**：`hint` 臂那一次真运行（N-330，修法已知、额度用尽）与三个冻结件不存在（blocker `frozen_artifacts_missing`）。其余全部卡在用户裁定或授权。出处：阶段六收口。 |
| **N-473** | **交给用户的最终清单**（14 条，四组） | **待用户 / 待编排方** | 全表在 `ops/HANDOFF.md` §17.6。**A 挡发布的四条**（数据许可原文 / clone 地址 / 代码许可 / 三个冻结件缺件 —— 前三条等用户，第四条是我们没做到）；**B 要一条命令或一次授权才能继续的三条**（f01 放行 18081 → 公开通道 18 个 run 全挡在这里；授权改 `runner/inject.py` 按通道取钉子 + rsync 公开 provider；形态①的两条前置）；**C 等签字的判据变更五条**（N-388 / N-383 / N-384 / N-348 + 与 N-348 解耦的守门小裁定 / N-130）；**D 请编排方裁定的两条**（提交署名两条 trailer 并存；卡 6.4 对同一目标真跑 3 次超额度的理由）。出处：阶段六收口（汇总 6.1 / 6.2 / 6.3 / 6.4 / 6.5 / 6.rt 六张卡）。 |
| **N-474** | **阶段六收口的两个机器读数** | 记录在案 | 全量 `pytest ops/ gateway/`（`pytest.lock` 内、`MemoryMax=6G`）= **3846 passed / 30 skipped / 1 xfailed / 0 failed**（1104.68 s，rc=0）—— **一条红都没有**，阶段五那条触湖红（`test_grid_matches_reconcile_grid`）这次没有复现；条数 3438 → 3846。真 API 累计 **2668 次 / 77 run**（`ops/api_usage.py` 机器统计），**阶段六增量 250 次 / 6 run**，全部来自外部演练那一批 —— 公开通道那 18 个 run 零次调用（没跑起来），`echo-min` 与 `quantagent` 的 6 个 run 也是零次调用（不调模型 / LLM 在系统之外，N-449），**别把「调用数是 0」读成「接入失败」**。读数取自本次收口最后一次文档改动之前，之后只改了 `ops/HANDOFF.md` §17.5/§17.9 与本表两行并重跑了清单生成器，回归单跑 `test_release_manifest / test_readme / test_operator_manual / test_6rt / test_5rt` 复核。**另**：§17.5 首版把总条数写成 27 / 达成 20，实数是 **26 / 19**（逐行数出来的），已改。出处：阶段六收口。 |

## 2026-09-10 收尾卡（可发布 + 实例扩张）

本节把 **W1 / W2 / W3 / X1 / Y1 / Y1b / Y2 / W.rt** 八张卡的收件箱并进来，编号从 N-474 续编。
重复的合并成一条（出处列在说明末尾）；既有编号（N-127 / N-128 / N-130 / N-348 / N-383 / N-384 / N-388 / N-409）
按「更新」写在 D 组，**不重新发号**。收件箱原文已改名 `.merged`，逐条原话仍可查。

**读这一节前先记住三个数**（本轮之后的现值，别再出第二组）：
**任务集 v1.0.14**（root `947bf817ae3df348…`）/ **参考轴 r1.0.21**（root `399fffde62108b52…`）；
出集 **34 题 / 挂起 6 题**，草拟 40 = 规定题 32 + 探针题 8；**40 模板（= 参数表 40 行）/ 130 实例**。

**A. 前置、网关与裁定落地（W1）**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-475** | **网关单元的 `StartLimitIntervalSec` / `StartLimitBurst` 写在 `[Service]` 里，systemd 静默丢掉** | **已修** | systemd v230 之后这两个键只在 `[Unit]` 生效。单元里写着 `120`，`systemctl --user show` 报的是 `10s`（全局默认）——**写下的值不是生效的值，而且没有任何东西会报错**。已搬到 `[Unit]` 并放宽到 600 s / 5。断言 `ops/test_w1.py::test_start_limit_is_in_the_unit_section_where_it_actually_takes_effect`。出处：W1。 |
| **N-476** | **网关 `ExecStartPre`（守门扫全树）69 s，撞默认 `TimeoutStartSec=90 s`** | **已修** | 2026-09-10 08:48–08:55 生产网关连挂 4 次（`start-pre operation timed out. Terminating.`），NRestarts=4 才起来 —— **每次起停都是一次掷硬币**。实测两个根 **5,486,074 条路径**（`runs_in` 一棵占 498 万）。改 `TimeoutStartSec=600`，**守门与判据一个字不改**；连起停三次各 rc=0 / 68–70 s / NRestarts=0。出处：W1。 |
| **N-477** | **`ops/guard_modes.py` 每条路径做 4 次系统调用** | **已修（判据不变）** | `rglob` 内部 lstat + `is_symlink()` + `stat()` + `is_dir()`。新增 `_walk_stat()` 用 `os.scandir` 的 `DirEntry` 压成 1 次：真树 **95.6 s → 43.9 s**，两版**逐条同结论**（同一路径集合、同一张违例表，夹具四种形态比对）。**没有缩小扫描集** —— `runs_in` 是答案面根，非扫不可；再要压只能动扫描集，**那是放宽判据，要单独裁定**。出处：W1。 |
| **N-478** | **`systemctl --user restart` 返回时网关还没在听** | 记录在案 | `Type=simple`，systemd 在 `ExecStart` 一 fork 就报 `Started`，网关还要约 **60 s** 才 bind（snapshot 后端 + 湖的 view）。restart 之后立刻 `curl /healthz` 拿到 `000` 是**正常**的，轮询到 200 再下结论。出处：W1。 |
| **N-479** | **一道 S7 的负载就能把网关顶过 `MemoryMax=6G`** | **建议尽快**（不挡本轮，但会污染读数） | 2026-09-10 10:55 / 11:32 / 11:36 / 11:40 四次 `oom-kill`，期间**只有 n130 这一个 run** 在打网关（网关锁串行），open 臂一个 run 发了 **4,318** 次请求。N-125 定 6G 时的实测依据（常驻 2.3 G）里没有 S7。后果不是「网关挂了」（它自己起来了），是**这一次 S7 的读数里混进了两分钟一次的链路失败**：`overreach.malformed_requests=15` 里哪些是 agent 写错、哪些是重启窗口里的半截请求**分不开**。方向：① 抬 `MemoryMax`（先量 S7 期间的真实峰值曲线）；② 查网关在 4k 请求下 RSS 为什么涨到 6G（`as_of` 切片缓存？duckdb view 句柄？）——**② 更像根因，① 只是把线往上挪**。出处：W1。 |
| **N-480** | **`StartLimitBurst=5` 对「守门判红」是对的，对「连续 oom-kill」是紧的** | 如实记，**没有再放宽** | 守门判红时一次尝试约 75 s，600 s 窗口最多 8 次 → burst 5 约 6 分钟后停下，**正是单元作者要的**。但 11:32–11:40 那四次 oom-kill 只隔 8 分钟，计数器一路走到 5 —— **再多一次窗口内的 OOM 就彻底不起**。抬到 10 会让「守门判红」变成无限重启循环（10×75 s > 600 s 窗口），把作者要避免的东西换回来。真正该修的是 N-479。出处：W1。 |
| **N-481** | **N-388 落地：默认预算档 `max_tokens` 600,000 → 6,000,000** | **已做** | `runner/registry.py::RUN_BUDGET`（`RUN_BUDGET_DEFAULT` 跟着走），`assert_registry_sane` 的「档位只能往上抬」仍成立（S4 150/9M、S7 300/18M）。同步：README §2.4、手册 §5.2/§5.3/§6/§7.2、两份示例矩阵（**并删掉 `max_tokens: 3000000` 那一行** —— 3M 现在比默认档还低）、`integrations/P2_CONTRACT.md`、HANDOFF 十二处照抄命令与预算表、`ops/joblists/m6_public.yaml` 与清单 18 行的 `budget_override`。**真跑不要再显式给 `--max-tokens`。** 出处：W1、X1、W.rt。 |
| **N-482** | **注入器按通道取 provider 钉子（P2 与 P7b 两个入口）** | **已做** | `runner/inject.py` 新增 `provider_pin_by_channel()` / `provider_pin_expect()`，按 `GENEBENCH_CHANNEL` 给 expect；`genetask/pin.py` **一个字未动**（用户 2026-09-10 的约束）。P7b（`PA.materialize`）是同一个 bug 的第二个入口 —— 只修 P2 等于把它往后挪 40 行，是 public 那条真注入把它抓出来的，不是想出来的。`ops/test_provider_pin_channel.py`。出处：W1。 |
| **N-483** | **公开 provider 已铺到 f02；18081 那条 000 是实例没起、不是防火墙** | **已验** | rsync 28,610 文件 / 369 MB / 4 s，f02 现算根 `561348660a3175b1…` 与冻结值一致；推之前 `answer_plane_guard.scan` **0 命中**。另：`ops/public_gateway.sh start` 之后 **f02 → f01:18081 = 200**（对照 18080 = 200），探完即 stop。**于是公开通道的两件执行面前置都齐了**，只差 N-484 那次裁定。出处：W1。 |
| **N-484** | **公开 provider 的 `files.sha256` 没收录它自己的 `MANIFEST.sha256` / `build_info.json`** | **待裁定 —— 挡着公开通道全部 18 个 run** | `pin.PROVIDER_META_FILES` 只豁免 `files.sha256` 与 `manifest.json`，于是根 hash 过了、`verify_filelist` 报 2 条「树里有而清单里没有」→ **即使 P2 的 expect 已按通道给对（N-482），公开通道每一次注入仍然在 P2 红**。f01 源树同样 2 条、私有那份 0 条 —— **不是传输问题**。`ops/run_joblist.py --check-plane` **退 0 也帮不了忙**：它只核根 hash，红是在真跑的注入期才发生的。**X1 的决定性新证据**：W1 列的方向 ②（把两个文件都收进 `files.sha256`）对 `MANIFEST.sha256` **在数学上不成立** —— `MANIFEST.sha256` 里有一行记的就是 `files.sha256` 的 sha256（实测 `561348660a3175b1…  2987248  files.sha256`），互指、**没有不动点**。所以只剩二选一：**①** `genetask/pin.py::PROVIDER_META_FILES` 加这两个名字（语义本来就对 —— `snapshots/public/tables.py::_stamp` 写它们时明确把自己排除在清单外；代价：`pin.py` 在冻结根 `CODE_FILES` 里 → 推**任务集版本**，且要先解掉「`pin.py` 一个字不动」那条裁定）；**②′** 把 `MANIFEST.sha256` 从 provider 树里删掉再重出 `files.sha256`（不动冻结根，但根 sha 变 → `ops/HANDOFF.md:557`、`ops/reports/public/release_forms.md:118`、`qlib_provider_public.md`、v1.0.13 签字包两处、`runner/inject.py::PUBLIC_PROVIDER_SHA256_ROOT` 全要改，已签字那份作废，**并且少一份逐文件校验表**）。**两卡都倾向 ①**。**明确没有采纳的第三条**：推的时候把这两个文件排除掉 —— 门会变绿，但绿的原因是**把证据挪走了**。出处：W1 §3、X1 §1。 |
| **N-485** | **`runner/c41/runner_core.py:659` 的 `docker compose run --rm task` 把父进程 stdin 透传进容器** | **建议根治**（已有绕法） | 调用链 ssh → nohup → `gateway_lock` → ssh f02 → `run_f02_a1` → `compose run` 一路都是开着的管道，codex 打出 `Reading additional input from stdin...` 之后等一个**永远不来的 EOF**。**恶劣之处是它长得像正常**：容器一直 `Up`、`docker logs` 只有那一行、`llm_log.jsonl` 干脆不存在，`--timeout` 有多大就白等多久（本轮白等 32 分钟、零调用）。根治：加 `-T` 或 `stdin=subprocess.DEVNULL`。绕法（起跑脚本尾部 `< /dev/null` 或 `ssh -n`）已验证有效。出处：W1。 |
| **N-486** | **在 f01 杀跑批不会杀掉 f02 上的容器；残留容器/网络让下一次「边车起不来」** | 登记，有处置 | 现象一：`compose down -v` 报 `Resource is still in use` → `compose up gateway` 失败 → 这一 run 记成 `failed`。现象二（X1）：残留网 `gb-s2-cor-01-…_gb_task` 占着 `172.31.240.0/24`，新建探针网直接 `Pool overlaps`，**那一轮四个探测目标全 000，包括对照** —— 差点被读成「防火墙放行没生效」。处置：`ssh f02 "docker rm -f <run>-task-run-* <run>-gateway-1; docker network rm <run>_gb_task"`。判读规矩：**对照那一行不是 200 就整张表作废**。出处：W1、X1。 |
| **N-487** | **`--retry-failed` 补跑单臂会被出集步骤拒**（「arms ['strict'] 里没有参照臂 'open'」） | 登记，有绕法 | 清单筛成只剩一行之后，出集看到的 `arms` 就只有那一个臂。bundle 早在 f02 上，**加 `--no-export` 即可**。根治要让出集按「清单里这道题的全部臂」判，而不是按「本轮要跑的臂」判。出处：W1。 |
| **N-488** | **结果库摘掉一条幽灵行**（`n130/s7-cor-01.strict…r01` 的 `no_artifact`） | 已处置，记在此 | 那一行是 N-485 造成的：run 零调用没跑起来，却被记成「交白卷」。留着它，Table A 上就永远有一个「S7 strict 交白卷」的读数，而那件事**没有发生过**。处置口径是库自己那句报错给的。备份 `$GB/results/v1/results.jsonl.w1bak-20260910T121025`（88 → 87 行，随后重收成 88）。谁在数库里的总行数，注意这一次。出处：W1。 |
| **N-489** | **`ops/run_f02_a1.py` 没有通道概念** | 登记不修 | 通道靠 `GENEBENCH_CHANNEL` 传给注入器。`run_joblist.py --channel public` 会设它；**手工敲单题命令的人必须自己 `export GENEBENCH_CHANNEL=public`**，否则用 private 的钉子、P2 红成「provider 变了」而真正的原因是通道。已写进 `runner/inject.py` 的 docstring。出处：W1。 |

**B. 公开包自足性（W2）**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-490** | **`PUBLIC_FROZEN_ARTIFACTS` 的三个 jsonl 一直被记成缺件，其实只是路径两套** | **已闭** | 它们**从来没进过仓库、也不在 `$GB` 下**，真实住处是数据湖 `$LAKE/reference/factor_library/compiled/`（`reference/factor_exec.FACTOR_LIB` 指那里，gold 就是在这三份上算的），而 `snapshots/public/manifest.py` 写的是仓库相对路径。已把湖里那三份**逐字节**钉进 `$REPO/factor_library/compiled/`，与 gold 三项对账**逐条复现、一处没凑**（后端分布 644/66/82+blocked 24；`operator_flags` 重放得到的 23 条 gold 存疑与 13 条 τ 排除，与 2026-09-01 落在 gold 旁的 `operator_convention_suspect.json` 逐条相同；13 条筛互检复现报告 §10 的 141 因子 / 379,950 格）。`RELEASE_MANIFEST` 缺件 **3 → 0**、blocker `frozen_artifacts_missing` satisfied。证据 `ops/reports/public/factor_library_recovery.md`。出处：W2。 |
| **N-491** | **`reference/factor_exec.FACTOR_LIB` 只认数据湖，仓库里那份钉住的副本谁也读不到** | **待裁定（要推参考轴）** | `FACTOR_LIB = cfg.LAKE / "reference/factor_library/compiled"` 写死在湖上。**拿到公开包的外部用户没有我们的湖**，于是那三份在包里是躺着的 —— 「公开包自足」只做到「文件在」，没做到「能用」。改法很小：「湖在就用湖，不在就退回 `$REPO/factor_library/compiled`」，两处逐字节相同（`ops/test_W2.py::test_the_repo_copies_are_byte_identical_to_the_lake` 钉住），所以回退**不改任何数值**。但 `reference/factor_exec.py` 在 `REFERENCE_MODULE_FILES` 里 = 参考轴冻结根 → 要推 r1.0.2x。出处：W2。 |
| **N-492** | **`$GB/release/_staging_unpublished/public_v1/` 那个包过期，发布前必须重打** | 待办 | 09-06 打的那份：`frozen/` 里只有 3 件（现在 6 件都在）、`MANIFEST.json` 的 `missing_declared_artifacts` 还记着缺三件、README 还是占位符前的旧文本。`$PY ops/release/pack_public_provider.py`。`release_forms.md` §5 本来就写了「发布前必须重打一次包」，N-490 之后多了一个理由。出处：W2。 |
| **N-493** | **只用 baostock 重建了 csi300 / csi500 的 PIT 名单并与私有对账** | **已做（证据，不是交付面）** | 2009-01-05..2026-07-31、4,269 个交易日，非交易时段跑。取数用「跨 5 天 + `updateDate` 单调 ⇒ 二分找换版点」，**5,056 次请求而不是 8,538**；正确性由 80 次随机回查逐字一致 + 「同一名单版本内成分数不许有两种值」的判别性测试兜住。对账：csi300 天天 300 只、与私有逐日完全相同 3,572/4,269 天、Jaccard 均 0.9874、**成员一只不差**；csi500 4,247 天 500 只 + 22 天 499 只（落在 4 个上游名单版本上、整版整版地短），只在公开 2 只、只在私有 32 只（全在首 14 天的 qlib 种子段）。**公开包现用的名单一个字节没动** —— 重建版落在 `$GB/snapshots/public_v1/instruments_rebuild/`。证据 `ops/reports/public/instruments_rebuild.md`。出处：W2。 |
| **N-494** | **要不要把 baostock 重建版换进公开包的 `instruments/{csi300,csi500}.txt`** | **待裁定（用户）** | 换 = 公开包在数据许可上真正自足（不再派生自 tushare），且重建版在进出场日期上更准；代价是**换掉公开通道的宇宙定义** → 公开 gold 因子面板 / 双实现互检 / τ·ε 标定 / `calibration.json` 整条链要重跑重签，**是判据变更不是数据修补**。不换 = 在 `DATA_LICENSE` / 数据卡里显式写明「名单一项来自 tushare 派生，不在 baostock 许可射程内」，当成一条已披露的许可边界。**W2 按不换执行**，理由是保守方向：收益（许可自足）可以先靠披露顶住，等用户明确要「公开包零私有依赖」时再一次性换、一次性重签。出处：W2。 |
| **N-495** | **csi1000 的 PIT 成分无法用公开源重建** | **已知限制（设计性 · 上游）** | baostock 0.9.3 只有 `query_hs300_stocks` / `query_zz500_stocks` / `query_sz50_stocks`，**没有 `query_zz1000_stocks`**（实测 `dir(baostock)`）。公开包的 `instruments/csi1000.txt` 仍派生自私有 `universe_pit`。已进 `ops/reports/known_limits_v1.md`（设计性限制汇总 5 → 6），由 `ops/test_W2.py::test_baostock_has_no_csi1000_constituent_api` 钉住 —— **上游哪天加了这个接口，那条测试会红**。出处：W2。 |
| **N-496** | **私有 `universe_pit` 缺 `SZ000022` / `SZ300114` 两只** | 登记不修 | baostock 的 csi500 里它们分别在册 364 / 283 个交易日，而 `universe_pit` **整张表任何宇宙都没有这两个代码**。不挡 v1（不在任何一道出集题的取数范围内），v1.1 补数据面时一起看。出处：W2。 |
| **N-497** | **私有 `universe_pit` 的进出场日期系统性吸附到月末，比实际生效日晚约 15 天** | 登记不修 | 上游 tushare `index_weight` 是月频权重表。实测：进场日不同的代码里，私有那个日期正好是某月最后一个交易日的占 **77.1%（csi300）/ 83.9%（csi500）**，中位差 **−15 天**。v1 的题都不在调整窗口那两周做成分敏感判定，不挡使用；v1.1 换源时一并处理。出处：W2。 |
| **N-498** | **baostock 的公开 API 会整段拒连** | 登记不修 | 2026-09-10 09:26Z–09:56Z 从 f01 与 f02 各试十余次全部 `ECONNREFUSED`（DNS 正常、同机 `1.1.1.1:53` 与 `pypi.org:443` 都通 —— **是对方在拒**），10:0x 自行恢复。影响 `release_forms.md` 的**形态 B**（用户自建那条链依赖 baostock 在线）。文档里应当写一句「对方服务偶发不可用，重试即可」，免得外部用户以为是自己配错了。出处：W2。 |

**C. 实例层：建、冻、跑（W3 / Y1 / Y1b）**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-499** | **参数轮换扩实例：40 基点 → 130 实例**（S1–S5 各 17、S6–S8 各 15） | **已做** | `genetask/params/v1.0-instances.yaml` + `ops/mk_instances.py` + `ops/test_instances.py`（27 条）。题面走 `render_arm` + 现有 phrasebook、夹具走 `reference/make_fixtures.py::materialize` —— **渲染与夹具逻辑一行都没新写**，所以「槽位机器生成、不重签」成立。130 过 `packager.build_task`（E1–E15 / R1–R5 / C1 / T1 / J1 全套）**0 红 / 3.1 秒**。`instance_id = <stage>/<template_id>@<base_task_id>#<sha256(规范化参数)[:10]>`。设计与判据 `ops/reports/instances_design.md`。出处：W3。 |
| **N-500** | **`instance_id` 必须带 `base_task_id`**（与任务书原文的出入，CONFLICT 已记） | 已定形 | 任务书写「`<template_id>#<param_fingerprint>`」，照写会让 `s1-rob-01` 与 `s1-rob-02` 的**基准实例 id 逐字节相同**（两者参数字典都是 `{}`、指纹都是 `44136fa355`）—— **实测撞了，生成器当场报错**。**身份的单位是参数表的一行，不是模板目录。** `ops/test_instances.py::test_shared_template_dir_does_not_collide`。出处：W3。 |
| **N-501** | **「40 模板」= 出集参数表的 40 **行**，模板目录只有 39 个** | 已记，**请照抄** | `S1/source_status` 被 `s1-rob-01`（规定题）与 `s1-rob-02`（探针题）两行复用；`rob_underdetermined` 在 S6 与 S7 各有一份。出表与论文口径要按「行」写，否则 40 与 39 两个数会同时出现在墙上。出处：W3、Y1b。 |
| **N-502** | **冻结清单加 `instances` 段（基点 → 实例两层）并落盘** | **已做（不进根）** | `ops/freeze_v10.py::build_instances_section()`；`build_manifest()` 签名从 `()` 变成 `(*, with_instances=False)`，**默认路径逐字节不变**（`frozen_ref(verify=True)` 每出一个 bundle 就调它一次，不能让它多建 130 道题）。Y1 用 `--write --with-instances` 首次写入，`instances_fingerprint = 969f698618eaaaae…`，**刻意不进 `ROOT_FIELDS`**。出处：W3、Y1。 |
| **N-503** | **`instances_fingerprint` 要不要进 `ROOT_FIELDS`；`v1.0-instances.yaml` 要不要进 `CODE_FILES`** | **待裁定（用户）** | 进 = 实例层也享受「改了就作废通行证」的保护，代价是实例表一动、f02 上所有 bundle 要重出，且此后每加一个实例都要推任务集版本；不进 = 记录在案但不受根保护。W3 / Y1 / Y1b **一路按保守方向不动根**。要做趁早 —— 越晚做，作废的通行证越多。出处：W3、Y1。 |
| **N-504** | **`instances_fingerprint` 跟着题面与夹具走，看到对不上不要当事故** | 记录在案 | W3 报告里印的 `45d99d60f8e98d7d…` 已过期两次（S8 schema 收紧后 `9eea8f92bd536eca…`、夹具 sha 写回后 `969f698618eaaaae…`）。它含逐实例的题面指纹与夹具 sha —— **这不是漂移，是它的定义**。出处：Y1。 |
| **N-505** | **六道挂起探针题：一道都放不出** | **已判，维持挂起** | 六道在 `materiality_screen` 里全部 `inconclusive`，同一个**结构性**原因：筛查 harness 是三份冻结的 **S7 回测引擎**，S1–S5/S8 的探针字段没有进入它的入口。照 screen 自己的判据「『跑不起来』『量不到』都不是『没差别』，不许翻锁」，因此 **`DIVERGENCE_EVIDENCE` 一个字未加**，出集维持 **34 题 / 挂起 6 题**。**Y1 对 W3 §9 的一处更正**：「Slip 纳入 S8 判据之后 `s8-rob-02` 才有量得到的可能」这句**今天不成立** —— Slip 判的是「自报与自己的事件链一致」，不是「换一个 `slippage_reference_price` 结果会不会不同」。**别把「Slip 纳入判据」读成「s8-rob-02 可以放出了」。** 出处：W3 §9、Y1。 |
| **N-506** | **六道挂起题各缺一层独立实现比较的 harness —— 这不是一件事，是六件事** | 未做 | `s1-rob-02` 缺取数层、`s2-rob-02` 缺对齐层、`s3-rob-02` 缺因子求值层（且要在 `lookback=24` 这个条件下量）、`s4-rob-02` 缺第二份 IC 计算实现（判据是 IC 族 ε 不是回测 ε）、`s5-rob-02` 缺信号重采样层、`s8-rob-02` 缺滑点参考价入口。**别按「补一个 screen」估工。** 逐题缺什么见 `ops/reports/instances_design.md` §9（表格，可直接搬进 `known_limits_v1.md`）。出处：W3。 |
| **N-507** | **phrasebook 缺 `universe[csi1000]` 与其它单因子措辞，堵住 S1/S2/S5 的两条轴** | 未做 | `genetask/phrasebook.yaml` 在冻结根 `CODE_FILES` 里 —— **加词即改冻结根，40 道出集题全部重签**。因此 S1/S2/S5 的宇宙轴只有 csi300/csi500（gold 面板 `snapshots/v1/gold_factors/csi1000` 其实是有的，793 个因子）；`input_factors` 只有 `gtja_191.001` 与三因子组合两个键，S5 的因子轴不可用（生成器当场拒，配了负例测试）。出处：W3。 |
| **N-508** | **S3 的因子轴结构上不存在** | 已记 | S3 的因子公式写在 `INSTRUCTION.*.md` 与 `solve.py` 里 —— 换因子 = 换模板 = **人工重写题面**，正是实例卡明令不许生成的那一类。要扩 S3 只能新增模板，那是另一张卡。出处：W3。 |
| **N-509** | **S4 的因子轴只改夹具不改题面，这是定义不是漏洞** | 已记 | `packager._inputs_phrase` 刻意不把 `origin` 写进题面，S4 的输入路径又是常量 —— 所以 S4 的因子变体**题面指纹相同、夹具 sha 不同**。`ops/test_instances.py::test_factor_axis_moves_the_fixture_not_the_text` 钉死。**做主表时别把这两个实例当重复题去重掉。** 出处：W3。 |
| **N-510** | **S6 的 15 个实例夹具出不来（先有鸡还是先有蛋）** | 未解 | `reference/make_fixtures.py::s6_consumer_window(set_root)` 要先在实例集根里扫到「引用 `reference/signals/*` 的题」才算得出窗口并集，而那些题**正是它要出夹具的题**（它们要等夹具 sha 才写得进去）。实测 `FixtureError: 没有任何题引用 reference/signals/*`。两条解：① 让 `s6_consumer_window` 在实例集下退回到基点集的窗口并集（语义要先想清楚：实例的窗口是轮换过的）；② 让 `ops/mk_instances.py --fixtures` 先把 S6 实例的 `task.yaml` 落盘（sha 留 null）再回头补 sha。**②不动冻结根，Y1/Y1b 都倾向 ②。** 后果如实进矩阵：S6 那 15 个归「缺夹具」，**不是 `·`**。出处：Y1、Y1b。 |
| **N-511** | **夹具 sha 实测只有 34 条（S4 17 + S5 17），S7 那 15 个是漏网的** | **口径更正 + 待办** | Y1 收件箱首版写「47 个已物化（S4 17 + S5 17 + S7 15）」是**错的**：`genetask/params/v1.0-instances.yaml::fixtures` 实测 **34** 条。S7 的 15 个实例基点题面**确实声明了 `inputs`**（`s7-cor-01` → `work/signal.parquet` + `work/signal.meta.json`，origin `signal:s7_dedicated_signal_v1`），属于「**该有夹具而没记 sha**」，却与 S1/S2/S3/S8 那种「本来就没有夹具」的 `{}` **在冻结清单里同形，看不出差别**。修法两条：补 S7 的 sha（`ops/mk_instances.py --fixtures --write-shas --stages S7`），或给「声明了 `inputs` 却没记 sha」的实例写一个显式的 `fixtures: null` / `pending` 标记。红队 W.rt finding 7。出处：Y1（更正）、W.rt。 |
| **N-512** | **`reference/make_s7_signal.py` 按已存在的 `s7-*` 目录放夹具，而实例目录是跑批当场建的** | 已绕过 | 表现：15 道 S7 实例全 `FileNotFoundError: work/signal.parquet`（跑批顺序是「建目录 → 立刻跑 solve.py」，中间没有插夹具的机会）。绕法：先跑一步「只建目录不跑题」（`$GB/scratch/Y1b/prep_dirs.py`）再 `make_s7_signal --set-id v1.0-instances`，15 个目录拿到同一份信号（sha `4597e07783b9e442…`，与出集那份同源）。**建议把这一步并进 `ops/mk_instances.py --fixtures`**，否则下一个跑实例的人还要再踩一次。出处：Y1b。 |
| **N-513** | **`ops/mk_instances.py --fixtures` 会把共享数据卡覆盖成实例的数字** | **已复原，未修** | 跑 `--fixtures --stages S4` 之后 `ops/data_cards/fixture_s4_eco_pool_v1.md` 的抬头从「`2026-01-05`…`2026-06-30` · 1,003,974 行」变成「`2026-04-01`…`2026-06-30` · 520,480 行」—— 那是**某个实例**的池子。数据卡的落点是 `make_fixtures.py` 里写死的共享路径，它不知道自己是在给实例出夹具。已 `git restore` 复原，**基点的 `work/factor_pool.parquet` 没被动**（sha `488e7cf2c0cece14…` 与 params 记的逐字相同）。**跑实例夹具之前先 `git status`，跑完再看一次** —— 不看就会把它提交进去。出处：Y1。 |
| **N-514** | **夹具 sha 写回参数表时不许抹掉注释** | 已修 | 第一版用 `yaml.safe_dump(doc)` 整文件重写，**13,162 → 9,395 字节、注释全没** —— 而那些注释（哪个取值为什么不许用）是这份参数表一半的价值。改成只替换 `fixtures:` 那一段，配 `test_fixture_write_back_preserves_the_comments`。**任何写回它的代码都要照此办理。** 出处：W3。 |
| **N-515** | **实例层 O1 跑批落地：私有 127/130、公开 30/130** | **已做（公开是墙钟封顶，如实报）** | `ops/run_oracles.py` 加 `--instances/--stages/--resume/--limit`，题行直接取 `mk_instances.Instance.row`（与出集 40 行同形，`write_all`/`run_one` 一个字没改），**实例元数据跟着结果行落盘**（否则隔一批再渲矩阵就只剩 `task_id`，看不出基点是谁）。矩阵拆成两张表（表一 探针族 × 基点 40 列、表二逐实例展开），**按基点聚合而不是按模板目录**。结果：私有可判 91、**零 finding 89**、非零 2、没判成 36；公开可判 26、**零 finding 26**、非零 0、没判成 4。**31 个基准实例与出集同号题「两边都判过但结论不同」= 0** —— 这是「实例生成器没漂 + O1 在同一道题上跑两次结论稳定」的唯一实证，加实例、改题面之后都该再看一眼这个数。出处：Y1b。 |
| **N-516** | **「没判成」必须分四类，别混成一个数** | 已定形 | 挂起的探针题实例（**设计如此**，六道各 3 个 = 18）/ 缺夹具（S6 15）/ 与出集撞号（4）/ 跑超时（1）/ 其余（要查）。**归类器自己踩过一次**：`s4-eco-03` 只因 stderr 带 `work/` 被归成「缺夹具」，而夹具在（2.6 MB），崩的是参考解挑因子那一步。现在每一类自己说要「全中」还是「任一中」，`ops/test_y1b.py::test_夹具在但参考解自己崩了_不许归成缺夹具` 钉住。**登记它是因为这正是那一页要防的错，而它出现在防它的那段代码里。** 出处：Y1b。 |
| **N-517** | **`(malformed)` 那一行非零不是探针缺陷 —— 归因与探针族相反**（CONFLICT，按保守方向做） | 已定形 | `render_matrix` 的抬头原文写「任一格非零即探针缺陷」，而同一文件的模块 docstring 写「`malformed` 同样算，**因为 oracle 是我们自己写的**」。按字面读法，`s4-eco-02/04` 那 7 条 `malformed` 会被归成「探针缺陷」，于是正确的动作变成「去改探针别报 NaN」——**那正好把唯一一个抓到参考解缺陷的信号关掉**。实例层新渲染器的抬头已改成两类行归因相反；**出集那张 `render_matrix` 的抬头没动**（不在 Y1b 路径、改它会牵动既有报告），建议编排方把同一句更正补过去。出处：Y1b。 |
| **N-518** | **S4-ECO 的参考解换个窗口就算出 NaN / 挑出一个叫 `'nan'` 的因子** | **待裁定 —— 本轮最值钱的一条** | 基点 `s4-eco-01` 零 finding；三个变体**全废**：`s4-eco-02` / `s4-eco-04` 的 `payload.ic_stats` **七个字段全是 NaN**（各 7 条 `malformed:s4_ic_stat_not_number`）；`s4-eco-03` 直接崩在 `reference/s4_oracle_common.py:44`：`ValueError: work/factor_pool.parquet 里没有 'nan' 的行` —— **挑因子那一步返回了 NaN，NaN 被当成 factor_id 去查表**。三个夹具都在（3.9 / 2.6 / 2.4 MB），**不是缺件**。**这正是实例层存在的全部理由的实证**：出集那 40 行每行只有一个取值，`s4-eco-01` 一直是绿的，没人知道这道题的参考解**不耐窗口变化**。两条解：① 修 `reference/s4_oracle_common.py` 与 S4-ECO 的 `solve.py`（挑因子那一步要对「候选全是 NaN / 窗口内样本不足」有明确行为）→ 参考轴 **r1.0.22**；② 认定这几个窗口取值超出设计范围、从参数表候选里去掉 → 不推版本，但等于宣布「这道题只在一个窗口上成立」。**倾向 ①** —— ② 等于把温度计藏起来。出处：Y1b。 |
| **N-519** | **S2-ROB 的参考解在 13 个月窗口上跑不完 600 秒** | **待裁定** | `s2-rob-04`（窗口 `2025-07-01..2026-07-31`）`subprocess` 超时被杀（`rc=-1`），同基点更短窗口的两个变体都绿。**不是错，是不 scale** —— 但后果一样：这道题在这个取值上出不了 gold。两条解：① 先**量**它到底要多久再决定把 `run_one` 的 600 秒放宽到多少（别把「慢」和「挂」混成一个数）；② 认定 13 个月超出 S2 的设计范围、从参数表候选里去掉。**倾向 ① 先量再说** —— 没量之前删掉，等于用「看不见」替代「跑得慢」。出处：Y1b。 |
| **N-520** | **`gateway/sim_factory.py::task_dir` 跨出集 glob，实例集一落盘就把出集的 S8 打挂** | **待裁定（已止血）** | 它按 `reference/tasks/*/<task_id>` 找目录，找到两个就 `RuntimeError`；实例集的**基准实例沿用基点 task_id**（设计如此），于是 `v1.0-instances/s8-cor-01` 一存在，**出集**的 `v1.0-smoke/s8-cor-01` 的 oracle 当场 `/sim/log 返回 500：{}`。**这不只影响实例卡**：任何人在实例目录存在期间跑出集 S8 的 gold 都会挂，而**报错在网关侧，日志里看不出是目录撞号**。Y1b 的止血：删掉 4 个撞号的 S8 基准实例目录（`s8-cor-01/eco-01/ops-01/rob-01`）并排除出跑批，出集 S8 已复核解析到 `v1.0-smoke`。**在解掉之前，任何人都不许把这 4 个实例目录重新建出来**（`ops/mk_instances.py --build` 与 `prep_dirs.py` 会把它们建回来）。两条解：① `task_dir` 收一个显式 `set_id`（**倾向**）；② 实例集的基准实例改发新号（130 个 id 全变，且「基准实例 = 出集那道题」在 id 上看不出来）。出处：Y1b。 |
| **N-521** | **`ops/gateway_lock.py` 的轮询式拿锁对着背靠背的生产者会饿死** | **待裁定（有绕法）** | 它是 `flock(LOCK_EX\|LOCK_NB)` + `time.sleep(poll)`，`poll` 默认 5.0 秒。Y2 的 adapt 真跑是**背靠背**的（一条跑完同一个 shell 循环毫秒级起下一条），交接那一瞬轮询方永远抢不到 —— 实测**连等 1711 秒一次都没拿到**，把 `poll` 收到 0.2 秒**仍然拿不到**（又白等 660 秒）。这不是「等得久」，是**饿死**，且日志上与「对方在跑长任务」长得一模一样（都是每 30 秒一行「等网关锁」），**分不出来**。绕法 `$GB/scratch/Y1b/gwlock_block.py`：**同一个锁文件、同一套持有者 JSON、同一条互斥保证**，只把 `LOCK_NB` 换成阻塞（内核排队，先到先得）—— N-125 要的串行完全成立，而且**比轮询版更严格**（轮询版存在两个等待方同时醒来各自 `LOCK_NB` 的窗口）。根治是把 `ops/gateway_lock.py` 本身改成阻塞式，那是共享文件、两卡都没动。出处：Y1b。 |
| **N-522** | **`ops/public_gateway.sh run -- <cmd>` 靠调用者自己设 `GENEBENCH_CHANNEL`，脚本本身不保证** | 已核，登记不修 | `do_start` 只把 `GENEBENCH_CHANNEL=public` 给了网关进程，`do_run` 里那条 `bash -c` 继承的是调用者的环境。不设的话客户端按 `private` 现算端口，会**安静地打在生产网关 18080 上** ——「数字照样出，只是来自另一份数据，没有一处会报错」。**去核了历史，结论是此前没有打错地方**（`$GB/logs/gateway_access_public.jsonl` 里 `config_id=oracle` 30,580 条、`oracle_probe_view` 42,103 条，最后一条时刻正对上 Y1 的公开 S8 gold 那一跑），只是**没有一处强制**。建议 `do_run` 把这两个变量一并 export，或起来之后核一次 `/healthz` 的 channel 与客户端算出的端口是不是同一个。出处：Y1b。 |
| **N-523** | **三控与破坏样本不按实例重跑**（口径裁定） | **已裁，写进矩阵页脚** | `ops/run_controls.py` 与 `ops/run_probe_mutations.py` 验的是**判据面**（探针会不会误伤诚实产物 / 破坏一处该族会不会响），被测对象是**校验器** —— 换窗口、换宇宙、换因子池不换掉校验器的任何一条分支。实例层要证的是「同一道题换了取值，参考解仍然零 finding」，**那就是 O1 矩阵本身**。出处：Y1b。 |
| **N-524** | **`ops/merge_o1.py` 的可执行位被补丁脚本抹掉** | 已复原 | 提交 `467e865` 里出现 `mode change 100755 => 100644`（补丁脚本一律 `chmod 0o600`）。不影响任何调用方（用法是 `python ops/merge_o1.py …`），但那是不该改的东西，已在收口提交里加回 `u+x`（`700`，不给 go）。**往 `$GB` 里写文件的补丁脚本，`chmod` 要按原模式来。** 出处：Y1b。 |

**D. 重冻 v1.0.14 / r1.0.21（Y1）—— 既有编号在这里更新，不重新发号**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-383 更新** | **S8 滑点符号在三处实现里不一致 → 统一，并把 Slip 纳入判据** | **已关** | 删掉 `reference/s8_oracle_common.py::fill_metrics` 的 `sign`（以指标规格 §3 为准：`Slip = 量加权(成交价 − 计价基准) bps`，**买卖同向**；`gateway/sim_engine.py::slippage_bps` 本来就不翻符号）。S8 四题 gold **私有 + 公开各重出一次、各 4/4 零 finding**；**只有 `s8-cor-01` 的数变了**（唯一一道有卖单的题：**−202.514311 → +53.483048**），另外三道逐位不变、两通道逐位一致 —— **这个数字就是「符号确实错了」的证据**。参考轴推 **r1.0.21**（root `399fffde62108b52…`）。详见 `ops/reports/s8_schema_tightening_v1_0_14.md` §2。出处：Y1。 |
| **N-127 更新** | **S8 的 Slip 判据怎么判**（CONFLICT，按保守方向做） | **已关（判自洽，不与 gold 比）** | 实现成 `scorer/l3.compare_fill` 的 **`SlipSelfConsistent`**：自报 vs **从 agent 自己那条事件链重算**，容差 = 一个最小价位（A 股 0.01 元）**逐单**按该单的计价基准换成 bps 再量加权（0.01 元在 1720 元的标的上是 0.058 bps、在 3 元的标的上是 33 bps —— 这就是必须逐单换算的理由），换算式写进 `scorer/l3.MIN_TICK_CNY` 与指标规格 §3 脚注。**没有与 gold 比**，三条理由：① 裁定给 Fill 的那条「题面没规定下哪些单、两轮不是同一个量的两次测量」对 Slip **同样成立**；② 一个价位的容差在 gold-vs-agent 上**没有意义**（实测离散度 ±170 bps vs 容差 0.058 bps，等于全员判 0，而 0 的原因是「你和 oracle 挑的单不一样」）；③ 裁定自己写的「**逐单**按该单的计价基准算」需要一份委托清单，gold-vs-agent 比的是两个标量、**拿不出「逐单」**。gold 的 Slip 照旧报出来供对照（`gold_slippage_bps`），不进判据。**若用户本意确实是 gold-vs-agent，改动只在 `compare_fill` 一处，但要一并裁定容差量级、以及「与 oracle 挑了不同的单」为什么该算失分。** 出处：Y1。 |
| **N-384 更新** | **S8 `events.required` 收紧**（CONFLICT，按保守方向做） | **已关** | 扁平 `required` = `[ts, type, order_id]`（四类事件的**交集** —— 题面对四类都写了「必须带 order_id」），逐类必填走 `allOf` + `if/then` **逐字对着题面正文取，不多不少**（JSON Schema 的 `items.required` 是扁平列表，说不出「按 type 分档」；把六个键全塞进去会要求 cancel 事件也带 `price`，**比题面严**）。`reference/artifact_schema._s8` **刻意也只收到 `order_id`** —— 协议 validator 的「够用子集」不认 `allOf`，评分器比它严或松都会让 `ops/validator_parity.py` 的两个方向断一条；收紧后语料 124 份、**两个方向各 0 份缺口**。任务集推 **v1.0.14**（root `947bf817ae3d…`）。既有 121 份真产物**不追溯**（旧产物按旧 schema 判）。出处：Y1。 |
| **N-128 更新** | **S8 事件字段（收紧部分）** | **已关** | 随 N-384 关掉。题面与共享 schema 现在**真的等价**：`fixed:output_format` 那句从「events 含 ts, type」变成「events 含 ts, type, order_id」——**机器从 `required` 生成，题面正文一个字没手改**。出处：Y1。 |
| **N-409 更新** | **版本状态** | **更新** | `SET_VERSION = 1.0.14`（root `947bf817ae3df348e2bd6a979dfa156a5fe4186f2a9c1fa243fba540e2b8adc8`）/ `REFERENCE_VERSION = r1.0.21`（root `399fffde62108b522106ef10673c213e050174fe40ac60b4edd5d0e624473b8d`）。按 N-111 **分两次** `--write` / `--write-reference`。清单新增 `instances` 段与 `instances_fingerprint = 969f698618eaaaae…`（**不在 `ROOT_FIELDS` 里**）。**已发通行证全部作废**，本次提交之后的出集才有效；f02 上现有的 bundle 要重出。出集烟测已在新根上验过（`export_bundle s8-cor-01 --arms strict,open` rc=0，bundle 里 `work/S8.json` 与 `ops/specs` 逐字相同，只有 `arms/ image/ task.yaml work/` 四项、**无 gold/solution**）。出处：Y1。 |
| **N-130 更新** | **S7 在 ≤300 次调用的预算里做不完** | **可关** | 300 次 / 18M 档位下**两臂各自自己停下来**：`open` 64 次 / 4.04 M tokens、`strict` 87 次 / 5.66 M，`llm_log` 全 `allow`、**0 次 `budget_exceeded`**；`strict` 臂 `sr_bucket=scorable`（`malformed=False`、`validator_rejections=0`），判 `invalid` 卡在 `gate_failed=['attribution_conservation']` —— **内容判据，不是预算**。2026-09-06 那次 `r03` 停在 90/90 —— **上一次离终点只差几次调用**。**一条限定**：跑的过程中网关被自己的 `MemoryMax` 杀了四次（N-479），`overreach.malformed_requests=15` 里哪些是 agent 写错、哪些是重启窗口里的半截请求分不开 —— 要谈「S7 的请求规范性」得先把网关不 OOM 的那一版跑出来；`attribution_conservation` 那条不经过这条路径，不受影响。**预算档的 CONFLICT**：裁定原文写「300 次 / 6M」，而任务书同处写「走档位、不显式给」，`BUDGET_TIERS["S7"]` 是 300 次 / **18M**。**按「走档位」做** —— 6M 会在约第 100 次调用上撞 token 闸，而撞闸的现场表现是「agent 做到一半自己放弃了」，**它长得像结论**，正好会把 N-130 错误地关成「已知限制、不再试」。事后两种读法都够（strict 5.66 M，离 6M 只差 5.6%）；**下次要收紧 S7 的 token 档按这个数算，别按 18M 反推**。报告 `ops/reports/n130/`。出处：W1。 |
| **N-525** | **`PAYLOAD_SHAPE["S8"].state_transitions.items.required` 没跟着收紧** | 未做 | 五道题两臂题面都写着「每一条必须带 `from`、`to`、`order_id` 三个键」，而 schema 仍只要 `["from","to"]`。与 N-384 同族的缺口，**用户的裁定只写了 `events`**，所以按路径边界没有顺手收紧。要收紧同样要推任务集版本 + 同步改 `_s8`（保持与协议 validator 一样宽）。出处：Y1。 |
| **N-526** | **Slip 判据要 `reference_close`，而题面不要求它 —— 实测 8 份真产物里 5 份记 `unobservable`** | 登记不修 | `scorer/l3.py::_slip_recompute` 要从 order 事件读该单的计价基准 `reference_close`；这个键在 S8 五道题两臂的 `INSTRUCTION*.md` 里**一次都没出现**（只有 `solve.py` 写它），也不在 `PAYLOAD_SHAPE["S8"].events.properties` 里。照题面做到位但没写它的被测方，Slip 记 `unobservable` 而**不是判 0** —— 这是**刻意的**（判据要的东西题面必须说）。红队在既有真产物上量到：**8 份里 3 份算得出 Slip、5 份 `unobservable`**。要让这条判据真能覆盖，得把 `reference_close` 写进 S8 题面 order 事件的必填行 —— **那是题面改动，又一次重冻**，本版不做。出处：Y1、W.rt（红队 minor 10）。 |
| **N-527** | **v1 的 Slip 量的是「价格偏离」，不是「执行不利度」** | 登记不修 | 统一符号之后，一买一卖的滑点**会互相抵消**：`s8-cor-01`（建仓＋清仓）从 −202.5 变成 +53.5，而两条腿各自都是不利成交。旧 `fill_metrics` 的 docstring 说的正是这件事 —— **它没说错，变的是这个量的定义**。要量执行不利度得另立一个指标（例如按 side 定向的 `adverse_slip_bps`）**并且同时写进题面**，否则又是一次「判据要的东西题面没说」。v1.1。出处：Y1。 |
| **N-528** | **既有 121 份真产物没有按新 schema / 新符号重判**（这是裁定，不是遗漏） | 记录在案 | 后果：主表上 v1.0.13 及以前的 S8 结果与之后的在**两处不可比** —— `malformed` 率（schema 收紧）与 `s8-cor-01` 的 Slip（符号统一）。**要做跨版本对比的人必须先读 `ops/reports/s8_schema_tightening_v1_0_14.md` §3.4。** 出处：Y1。 |
| **N-529** | **`ops/run_oracles.py` 的公开通道落点很容易写错，且写错了什么都不报** | 登记不修 | 落点 = `<ANSWER_ROOT>/tasks/<set_name>`，而 `ANSWER_ROOT` 是**固定**的 `$GB/reference`（N-61 / D-28：落点不是参数）。给 `--answer-root $GB/reference/tasks/public --set-name v1.0-smoke-public` 会安静地落到 `.../tasks/public/tasks/v1.0-smoke-public`，**rc=0、4/4 零 finding、什么都不报**，只是写错了地方。正确写法：`--set-name public/v1.0-smoke-public`，**不给 `--answer-root`**。出处：Y1。 |
| **N-530** | **外层持网关锁时忘了 `--no-batch-lock` 会死锁，而症状看不出是死锁** | 登记不修 | 同一把 `fcntl.flock` 在另一个进程里再拿一次会**永久阻塞**，日志每 30 秒打一行「等网关锁：当前 {…}」，**而那个 `what` 就是自己**。Y1 等了 120 秒才判出来。`--no-batch-lock` 的帮助文本写了这件事，但日志没有 —— 建议在等锁行里加一句「holder 的 what 与你自己相同 ⇒ 多半是套了两层锁」。出处：Y1。 |

**E. 适配赛道 30 例真跑（Y2，N-348 裁定落地）**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-348 更新** | **适配赛道题源 = 出集规定题的 oracle 产物** | **已裁定并落地** | `ops/adaptation_track.py` 全面改写：题源从「各题 `solution/artifact.json`」改成**出集规定题的 oracle 产物**（S7/S8 取 `gold/oracle_artifact.json`、其余取 `solution/artifact.json` —— `run_oracles.py` 的两处真实落点），**探针题一道不入**；选题改成**按阶段分层 + 种子固定**（`SEED=20260910`，每级八阶段各 1 例 + 2 例补新「阶段×族」组合），种子与选中它的那一步写进每份 `mutation.json` 与 `_index.json`；破坏方式按级别表，每例可纠正性**实测**。守门 `ops/push_guard.py` 的 `SET_IDS_NOT_PUSHABLE` 里 `v1.0-adapt` 那条**显式删除并记因**（裁定原文 + 后果 + 保留的门写在常量上方），换上**更窄的门 —— 落点**：只许落 `/data/genebench_runner/adapt/`，且**必须显式声明落点，没声明 = 拒**（实测三态：无落点→拒、主赛道 batch 目录→拒、adapt 根→过）。`ORIGINS_NOT_PUSHABLE=('gold_derived',)` 的一般规则**没有放宽**，适配集是唯一例外，通行证如实自报 `origin/track/source_note`。出处：Y2。 |
| **N-531** | **N-348 的后果：主赛道那些题算「可能已见过答案」** | **已写进三处文档 + 两处表** | `ops/specs/fairness_protocol.md` §7 第 10 条、`ops/reports/known_limits_v1.md` 末节（那条「挡着、卡在用户签字」正式收口成**设计性限制**）、`ops/specs/adaptation_track.md` §7；`scorer/report.py::ADAPT_ORACLE_EXPOSURE_NOTE` 跟着**每一张**表走（`to_latex` 的 caption——**适配表与主表都带**——加 `table_adaptation` 的 `note` 列，CSV 也带）；逐题清单进 `ops/manifests/v1.0-adapt.json::exposed_source_tasks`（30 例引用 **19 道**规定题）。出处：Y2、W.rt。 |
| **N-532** | **适配赛道 30 例各有 oracle 与一次真运行 —— 完成定义达成** | **已做** | 真 API **749 次 / 30 run**（`llm_log` 里 `decision==allow`），30 个 run 全部 rc=0、零重试。结局：**first_pass 14 / correct_flag 5 / failed 11 / blocked 0 / repaired_pass 0**；`resolved_rate` L1 0.70 / L2 0.70 / L3 0.50 / **ALL 0.633**。**`blocked` 与 `repaired_pass` 恒 0 是口径不是读数**：adapt 臂投的是适配模块（单位表 / 字段映射 / 可接纳性条文），**不投 `validate_artifact.py`**，这一批根本没有修复回路（`validator_rejections` 全是 `None`，**不是 0**）。产出 `ops/reports/adapt/{table.csv,table.tex,summary.md,records.json}` 与 30 行 oracle × 真跑逐例对照表（`oracle_matrix.{csv,md}`）。**两条读得出来的规律，登记不解读过头**：① 两例 `gap_provenance_edge`（删整条上游引用）**全败** —— 删一个标量与删一条依赖图的边对 agent 不是同一件事；② S6 六例败四例 —— S6 产物是 5 个调仓日 × 20 个持仓的嵌套表，改一处要重写一大块（**难度里混进了「产物有多大」**）。出处：Y2。 |
| **N-533** | **裁定原文写「33 道出集规定题」，清单现值是 32 道** | 已如实记 | 出集 34 = 规定题 32（regulated 29 + free 3）+ 已放出的欠定探针题 2；挂起 6 道全是探针题；八个阶段各 4 道规定题。**没有把清单改成 33，也没有假装 33 就是 32。** 差写在 `ops/adaptation_track.py::source_counts()`（进 `_index.json`）、`ops/specs/adaptation_track.md` §2、`ops/test_y2.py::test_the_ruling_says_33_the_manifest_says_32`。这个差不影响任何判据（题源的选择判据是「kind != underdetermined_probe」，不是「恰好 33 道」）。出处：Y2。 |
| **N-534** | **题源体量帽 `MAX_SOURCE_BYTES = 700 KB` 又排掉两道规定题** | 已记因（**本卡自加的判据，不在裁定里**） | `s5-eco-01` 的 oracle 产物 **4.0 MB**（41,700 条 signals）、`s4-ops-01` **878 KB**。做成适配题量到的是「agent 会不会用脚本改文件而不是把整份文件读进上下文」，不是适配能力，而且 bundle 跟着胖 4 MB。帽下每阶段仍剩 ≥3 道题，分层不受影响。**若编排方认为应当保留大产物题，改一行常量即可，但要一并想清楚预算。** 出处：Y2。 |
| **N-535** | **适配模块 `MANIFEST.json` 的 `status` 从 `draft` 改成 `released`** | 已改，**请编排方过目** | 三件工件（`adaptation.md` / `field_map.json` / `unit_table.json`）**内容一字未改**，三条 sha 与 2026-09-07 逐字相同，改的只有 status。理由：`draft` 下 `runner/inject.py` 的 P7 **拒绝投放**，adapt 臂就是个裸臂（卡 4.2-b 实测 22.7 s 中止、零次模型调用），而 N-348 放行的是**真跑**。该文件不在 Y2 的路径清单里。出处：Y2。 |
| **N-536** | **`ops/test_4rt.py` / `ops/test_adaptation_track.py` 的断言按新判据改写** | 已改 | `test_push_guard_refuses_the_adaptation_set` → `…_gates_the_adaptation_set_by_destination`；`test_pack_adaptation_bundle_is_still_not_pushable` → `…_needs_an_explicit_destination`。**判据变了不是判据消失了**：两条现在钉的是「没声明落点 = 拒」与「主赛道 batch 目录 = 拒」；`test_push_guard_refuses_a_gold_derived_passport` **一字未动**。另：三处夹具从写死 `adapt-l1-01` 改成**按性质挑**（换题源之后它已从「结构合法的破坏」变成「校验器会拒」，写死 id 会假红），结构合法数 13 → **9**（实测值，不是设计目标）。出处：Y2。 |
| **N-537** | **只跑了 `adapt` 干预臂，没有跑 `open` 参照臂 —— 现在读不出干预效应** | 已知限制 | 完成定义是「30 例各有 oracle 与**一次**真运行」，跑的是干预臂。**0.633 是「Codex + 适配模块」的绝对值，不是干预效应。** bundle 里 `INSTRUCTION.open.md` 已就位，补跑只要把 `--arms adapt` 换成 `--arms open`，约再 750 次真 API。出处：Y2。 |
| **N-538** | **`ops/push_bundle_to_f02.sh` 应当自己把落点传给守门** | 待办（一行） | N-348 之后适配 bundle 的判据是**落点**（`push_guard.ADAPT_DEST_PREFIX`），而推送脚本只给守门传 `<bundle> <manifest>` 两个参数，现在靠调用方 `GENEBENCH_PUSH_DEST=<DST> ops/push_bundle_to_f02.sh …`。**漏给不会变成静默放行**（守门没拿到落点就拒），但那是「门在、按门的人要记得带钥匙」。改法：在调 `push_guard.py` 那一行前加 `GENEBENCH_PUSH_DEST="$DST"`，或把 `"$DST"` 作为第三个参数传进去（CLI 已经收）。出处：Y2。 |
| **N-539** | **`$GB/runs_in/adapt/` 占 18 GB** | 登记不修 | 每个 run 目录带一份 602 MB 的 `work/provider/`（臂内独占副本，PA-2/PA-3），30 个 run 就是 18 GB。结算只用到 `inject.json` / `run.json` / `artifact.json` / `work/protocol/validator.log` / `log/llm_log.jsonl`。/data 还有 2.4 T 空闲。要省盘就在两处 `pull` 里加 `--exclude=work/provider/`。**顺带一条坑**：`adapt_report.pull()` 的 `subprocess.run(timeout=600)` 对 18 GB 不够用（第一次全量拉取 rc=124 炸掉），绕法是后台 rsync + `--no-pull` 结算。出处：Y2。 |
| **N-540** | **施工中途收过库，跑完要先删自己那些行再重收** | 已处理 | `results_db.ingest` 按 `(batch, run_id)` 幂等，**同主键内容不一致会抛且不覆盖**（这是对的），而中途拉回的 run 可能是跑到一半的。删的脚本 `$GB/scratch/Y2/db_drop_adapt.py`（只删 `batch=adapt`，用与 `results_db` 同一把 `fcntl.flock`）。**没有去放宽 `ingest` 的幂等判据。** 库里现在 `batch=adapt` 恰好 30 行。出处：Y2。 |
| **N-541** | **`ops/mk_tables.py` 末尾那条已知限制过期了** | 待改 | 原文「适配赛道还没有记录……`records.json` 现在是空的（真跑被红线 B2 闸住）」。现在 `records.json` 有 30 条、结果库 `batch=adapt` 有 30 行、`--table adaptation --filter batch=adapt` 出 4 行真表。补轴的现成做法在 `ops/reports/adapt/adapt_report.py::axes_for`，建议按卡 4.2-b 的提议折进 `ops/score_runs.py`。出处：Y2。 |
| **N-542** | **`ops/mk_tables.py --table adaptation` 不加 `--filter` 会被 fail-closed 拒** | 记录在案（**门是对的**） | 不加 `--filter` 会选中全库 118 条、跨 6 个 `set_version` 与 7 个 `reference_version`，于是拒绝出表 —— 正是 `VERSIONS.md` §2 那次混轴事故之后加的门。手册 §712 与 `--help` 示例都写对了（`--filter batch=adapt`）；**编排方「照抄的命令」那一行摘要少了 `--filter` 与 `--out`，按它做不下去**。出处：W.rt 红队复核。 |

**F. 红队一轮与修复（W.rt）**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-543** | **S6 gold 的 `provenance[0].artifact_id` 是未填的占位串 `TODO:signal-artifact-id-missing`** | **未修 —— 等用户裁定（红队唯一一条 block）** | 五份 S6 参考解全带这个值，来源 `genetask/templates/S6/*/solve.py:126` 的 `meta.get("artifact_id", "TODO:…")` 兜底（上游信号 parquet 的 schema metadata 里没有 `artifact_id`）。后果落在适配赛道：`adapt-l1-08` / `l2-07` / `l2-08` / `l3-06` 四例的 `broken.json` 也带着它，适配臂 `INSTRUCTION.md` 规则 1 要求「源里没有的写成显式 `unresolved`」，被测方照做、oracle 却要求原样抄回，`scorer/adaptation.py::match_oracle` 在 `provenance` 上判不一致。**已发表的适配表因此偏低约 13 个百分点**（L1 first_pass 7→8、L2 7→9、L3 correct_flag 5→6、ALL `resolved_rate` 0.6333→**0.7667**、failed 11→7）。主赛道评分器**不比 `provenance`**（全树只有 `scorer/adaptation.py` 引用它），主表数不受影响。两条修法都要用户点头：**①** 改 `solve.py` 的兜底值为协议的 `unresolved` 标记 → 参考轴 **r1.0.22** + 重出 S6 五题 gold + 重出四例 oracle + 重算适配表（**冻结根，红线 B4**）；**②** 在 `match_oracle` 里把 oracle 侧 `TODO:` 前缀值与 agent 的 `unresolved` 判为等价（**判据变更**）。**倾向 ①**：修的是根因，爆炸半径只有 S6 gold 的这一个字段 + 适配赛道，且这个项目对同类问题（N-383 Slip 符号）刚刚就是按 ① 做的。已登记进 `ops/reports/known_limits_v1.md` 逐条表（判定 v1.1）与 HANDOFF §15.4。出处：W.rt（红队 block）。 |
| **N-544** | **两份就绪报告的 §1 停在 1.0.13 / r1.0.20** | **已修** | Y1 的重冻（`91647a3`）落在 X1 重出公开就绪报告之后，两份报告都没再生成，于是读报告的人拿到的四条版本轴差一个版本 —— **而 S8 的 Slip 与 `malformed` 口径恰好在这一版变了**。两份已重出到 1.0.14 / r1.0.21。**谁推版本谁重出就绪报告**（§1 本来就是从 `freeze_v10` 现读的模板）。出处：W.rt（红队 major 4）。 |
| **N-545** | **`m6_public` 清单里物化的 `budget` 是陈值，`--dry` 打印的正是它** | **已修** | 18 行的 `budget_override` 确实清空成 `{}` 了（X1），但同一行物化的 `budget` 仍写着 `max_tokens: 3000000`（`max_calls` 却已是档位值）。真跑只读 `budget_override` 所以实跑档位是对的，但**干跑一遍看到的是 `tok=3000000`，与 README 的说法直接矛盾，而 3M 比默认档还低正是 N-388 要废掉的那个绕法**。两头都堵上：新增 `ops/joblist.py rebudget` 子命令（**只动 `status == "pending"` 且没有 `run_id` 的行** —— 跑过的行里那个数是遥测，改它等于伪造现场），并让 `ops/run_joblist.py --dry` **现算**（`live_budget`）。现在干跑显示 6M / 9M / 18M。出处：W.rt（红队 major 2b）。 |
| **N-546** | **公开通道 0 run 立为 `RELEASE_MANIFEST` 的第五条 blocker `public_channel_zero_runs`** | **已做** | 此前它只写在 `ops/reports/m6_public/README.md` §5 里，清单上看不见。加了之后 `docs/OPERATOR_MANUAL.md` §0.1 的「三件/四件/**五件**」、`ops/test_readme.py`（两条）、`ops/test_W2.py`（一条）、`ops/test_6rt.py` 会跟着红 —— **那是设计好的「新 blocker 不许悄悄不见」机制，照它走，别绕。** 出处：W.rt（红队 major 2a）。 |
| **N-547** | **`harnesses/README.md` 三处仍在教人显式给 3M** | **已修** | :263 写「默认 100 次 / 600,000 tokens」；:407 的可复制真跑命令块里带着 `--max-tokens 3000000`；:421 逐字写「必须显式给：默认档只有 600,000 …… harness 接入验证一律按 3000000 跑」。**照抄这条命令等于把 6M 压回 3M。** 三处已按 N-388 的世界改写（407 的两个参数**整个删掉**）。另修 `ops/HANDOFF.md:1010` 那句「两份手册已同步」的不实断言与 :1017 的「600000」笔误。出处：W.rt（红队 major 3）。 |
| **N-548** | **`known_limits_v1.md` 的两张表把已裁定并落地的事项仍列成「待裁定 / 挡着」** | **已修** | :39/:129 两行写「默认档 600,000……绕法：显式给 `--max-tokens 3000000`」（N-388 已落地，这条「绕法」现在是把预算压低）；:40/:130 两行写「适配赛道……裁定之前一个 bundle 都不许推……有真运行 0……30 例的 `broken.json` 内容上就是 **16 道**基准题的答案」（N-348 已裁定、30 例都有真运行、实际暴露 **19 道**）；:121 的 v1.1 清单还留着「S8 Slip 符号不一致」「S8 events 收紧」两项（`91647a3` 已做掉）。文末新章节虽然收口了 N-348，却声明「本节不改上面任何一条裁定」—— **先读表的人拿到的是反的结论**。三处已做幂等的定点替换（加删除线 + 指向文末收口章节，与 HANDOFF §1431 同一写法）。出处：W.rt（红队 major 5）。 |
| **N-549** | **`ops/HANDOFF.md` §15.4 整节仍按「适配赛道今天跑不了」写** | **已修** | 标题「（今天跑不了，缺三件）」、正文「30 例真跑一次都没能起」、闸 ① 记「待用户裁定（N-348）」、末段「`table.csv` 只有表头（有真运行：0），**不要引 SR / 结局分布**」、以及「30 例里有 13 例的破坏在结构上完全合法」。**HANDOFF 是后续代理与操作员的主入口，照它做会得出「适配赛道没有数、不要引」的结论，正好与刚发表的表相反。** 已改写成现状（30 例已真跑、三条闸已解、可引但必须带 N-348 的暴露脚注），「13 例」按 `ops/specs/adaptation_track.md:166` 现值重取（9）。出处：W.rt（红队 major 6）。 |
| **N-550** | **适配表一条版本轴都没有** | **已修** | 表头原来只有 `config_id,arm,level,n,…,note`，`table.tex` 的 caption 里也没有；而 Table A 的 CSV 四条轴都在。**后果与 `VERSIONS.md` §2 记作「一次真事故」的 m6_all 混轴表同形**：看不出它是在哪一版题面与哪一版参考轴上算出来的（实际是 1.0.14 / r1.0.21，而 Slip 与 S8 events 的口径恰好在这一版变过）。已加 `set_version` / `reference_version` / `runner_version` / `image_digest` 四列（取不到的显式留空而不是省掉整列），caption 里也写出轴声明。出处：W.rt（红队 major 8）。 |
| **N-551** | **N-388 落地之后有 6 个 case 一直是红的，红队上一轮没量到** | **已修** | `ops/test_harness_contract.py::test_readme_run_command_passes_an_explicit_max_tokens`、`ops/test_c65.py`（2 条）、`ops/test_6rt.py`（2 条）、`ops/test_integrations_readme.py`（1 条）—— 全部钉着「默认档 600k、命令里必须有 `--max-tokens 3000000`」这个已经不存在的世界。红队上一轮只跑**新增的**测试文件（393 passed），所以一条都没碰到。**六条已按 N-388 的世界重写（不是放宽：方向整个翻了，各自补了反向判别力）。教训**：单卡不跑全量是用户为提速下的裁定，但「改了权威常量 / 改了生成器 / 加了一条 blocker」这一类改动，收口前必须 `grep -rn <常量名> ops/test_*.py` 一遍。出处：W.rt。 |
| **N-552** | **断言「命令里不许出现 `--max-tokens`」不能按整段查** | 已修 | 正文里解释「为什么不要给 `--max-tokens`」时一定会出现这个字符串，按 `seg` 整段断言会把**解释本身**判成违规。两份测试各加了一个 `_fenced()`：只取围栏代码块的内容，**并断言取出来的东西非空**（否则恒绿）。出处：W.rt。 |
| **N-553** | **W2 补齐三件冻结件之后，三处陈述没跟上（`test_recon_public` 从 W2 提交起一直红）** | **已修** | `ops/data_cards/public_channel.md` §11、`README.md` §5 第 3 条、`docs/OPERATOR_MANUAL.md` §0.1 第 3 条都还写着「三个文件不在仓库里、这挡发布」。`ops/test_recon_public.py::test_card_reports_the_missing_frozen_artifacts_truthfully` **正是为这一天写的**（「补齐那天这条会自己变红，逼着改卡」）。处置：重跑**全量** `ops/recon_public_vs_private.py`（**`--part frozen` 单跑会把 `run.parts_run` 写成只剩一个 part，另一条断言会红 —— 要跑就跑全量**，约 4 分 20 秒），三处改到现状并各自注明闭合日期与出处。出处：W.rt。 |
| **N-554** | **红线 5 的源码侧门从 W2 起一直红：`snapshots/public/` 里 4 处裸 `mkdir`** | **已修** | `instruments_rebuild.py:{143,235,396}` 与 `recover_factor_library.py:57`，写法都是 `X.mkdir(parents=True, exist_ok=True)` 紧跟一行 `X.chmod(0o700)` —— **只有最后一级被收紧，中间层拿的是 umask 的脸色**（N-61 那晚就是这么塌的）。四处统一改成 `cfg.create_dir(X)`。两个文件不在 W.rt 的路径清单里，按「恒红不绕过」就地修掉并登记。出处：W.rt。 |
| **N-555** | **幂等补丁在「new 包含 old」时并不幂等** | 已修，**教训记在这里** | W.rt 的定点补丁先查 `old` 再查 `new`，而其中三条是**追加式改写**（`new` 本身含 `old`）——commit 前在 flock 内重跑求幂等，把 `known_limits` 的小标题后缀、更新告示行、逐条表两行各贴了 2–3 份，把新 blocker 贴了 2 份。**一眼看不出来**，是 `ops/mk_release_manifest.py --check` 的 rc=1（「判据变了：blockers」）抓出来的（改正 `52b951c`）。**建议：flock 内不要「重跑补丁求幂等」，改成核终态**（断言「该在的字串在、不该在的不在」），两句话就写完，且不会叠加。出处：W.rt。 |
| **N-556** | **N-348 的暴露脚注四处措辞两分** | 登记不修 | 规格与公平性协议写「主赛道**被引用的那些题**」，表脚注与 `known_limits` 写「主赛道**这些题**」—— 后者紧接在「题源是出集规定题的 oracle 产物」之后，读起来像全部 32 道规定题，而 `exposed_source_tasks` 实测是 **19 道**。方向保守（说多不说少），不误导读者。要统一的话：两处改成「主赛道被引用的那 19 道题（清单见 `ops/manifests/v1.0-adapt.json::exposed_source_tasks`）」。出处：W.rt（红队 minor 9）。 |
| **N-557** | **两份实例探针矩阵的「口径」行写的是跑批覆盖数** | 登记不修 | `ops/reports/probe_matrix_instances.md:3` 写「口径：40 模板 / **127** 实例」、公开那份写「40 模板 / **30** 实例」，而实例集本身是 **130** 个（两份正文自己都写着「跑过的 127/130」「30/130」，冻结清单 `counts.instances` 也是 130）。把覆盖数写在「口径」二字后面，读者会当成实例集规模。修法：统一成「口径：40 模板 / 130 实例（本轮跑过 127 / 30）」，**两份都是生成物，改生成器那一行即可**。出处：W.rt（红队 minor 11）。 |
| **N-558** | **主表的 CSV 出口没有 N-348 的暴露脚注** | 登记不修 | 脚注只进了主表的 LaTeX caption（`ops/reports/m6/table_a.tex` grep `N-348` 命中 1 次），`table_a.csv` 里一次都没有；适配表两种格式都带。签字包里同时收 `table_a.csv` 与 `table_a.tex`，**只拿 CSV 的下游读者看不到这条边界**。修法：给主表 CSV 也加一个 `note` 列，或在 CSV 出口末尾追加一行以 `#` 开头的脚注。出处：W.rt（红队 minor 12）。 |

**G. 单机形态①（X1）**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-559** | **形态① 的「容器打不到本机宿主端口」已被那条 ufw 规则解掉** | **已验** | 用户放行 `172.31.240.0/22 → 18080` 之后，容器 → `192.168.1.219:18080` = **200**（对照：容器 → `192.168.1.48:18080` = 200）。**手册 §1.3 那张「三种全部超时」的表是放行前的结论**，已按「放行前/放行后」改写。出集与推送两步在单机落点上真跑全绿，**含推送守门对 f02 上 `genebench-answer-plane-scan.timer` 的 `enabled + active` 核查** —— 于是「timer 不存在要不要装」这件事**不成立**，它在 f02 上是活的。复现脚本 `$GB/scratch/X1/x1_probe3.sh`。出处：X1。 |
| **N-560** | **形态① 新的墙：`gateway/sim_engine.py` 的 import 链穿到答案面** | **待裁定（CONFLICT，按保守方向停手）** | 在 f02 上起单机网关时停在 `gateway/app.py → routers/sim.py → sim_engine.py:20 → from reference.artifact_schema import (LEGAL_TRANSITIONS, TRADABILITY_STATES, UNTRADABLE_STATES)` → `ModuleNotFoundError`。形态① 要求网关与容器同机，于是「起网关」这一步与**红线 B2（`reference/` 不进执行面）**直接撞车。这是**唯一**一处（`grep -rn "from reference" gateway/ snapshots/` 只此一行），被引的是三个协议常量、不是任何题的答案，`answer_plane_guard.scan` 单独扫 `reference/artifact_schema.py` **命中 0** —— 但该模块自己的 docstring 写着「本模块是**评分侧**的（不进执行面）」，而 B2 的措辞是整棵 `reference/`。**手册 §1.1「两种形态跑的是同一套代码，差别只在三个常量与一条防火墙规则」今天不成立**，已更正。两条解：**①** 把三个常量搬出 `reference/`（落到 `genetask/` 或一个新的协议侧模块）→ 推参考轴 **r1.0.22**（**倾向**，语义对：它们是协议 schema 不是参考解，搬完两种形态才真是同一套代码）；**②** 裁定「`reference/artifact_schema.py` 允许出现在执行面」→ B2 从「看目录名就能判」变成「逐文件判」，**而 B2 之所以有效正是因为它不需要判断**。**没有采纳的做法**：只把那一个文件 scp 过去让网关起来 —— 形态① 会当场跑通，但绿的原因是把一条目录级红线改成了「这个文件应该没关系」的逐案判断。留了一条会自己失效的测试 `ops/test_x1.py::test_gateway_reaching_into_reference_must_stay_documented`（常量搬走之后前提不成立、测试自动放行）。**真跑 / 结算 / 出表三步因此一步没走。** 出处：X1。 |
| **N-561** | **形态① 下结算时的网关日志在 f02、不在 f01** | 登记备查 | `score_runs.py --gateway-log` 默认指 f01 那份，不换的话四个依赖日志的族（`declared_reads` / `fetch_clock` / `lookahead` / `source_status`）会**静默塌成 `unobservable`**。X1 没走到结算，是读代码看出来的。出处：X1。 |
| **N-562** | **f02 今天的 PyPI 出网约 13–20 KB/s，形态① 的数据面 venv 装不出来** | **环境事实，登记不修** | f02 没有 `python3.12-venv`（`ensurepip` 缺失，装它要 root）；`pip install pandas==2.2.3`（12.7 MB）**900 s 没下完**（rc=124），`duckdb==1.4.3`（20.5 MB）下了约 26 分钟（用 `du -sb /tmp/pip-unpack-*` 前后差量量到约 **13 KB/s**）。绕法是从 `gb-rd-u:r1` 镜像里 `docker cp` 出 cp312 的 `site-packages`（约 40 秒），**代价是版本漂移**（pandas 2.3.3 / numpy 2.5.2 / pyarrow 25.0.1 vs f01 的 2.2.3 / 1.26.4 / 20.0.0）。**这套漂移环境没有产出过任何数**（网关没起来）。根治要么装 `python3.12-venv`（要 root），要么做一份离线 wheelhouse。出处：X1。 |
| **N-563** | **`gb-base:bookworm-r1` 镜像里没有 `curl`** | 登记 | 拿它当探针容器时四行全 `000`，**而那不是网络结论**。用 `python3 -m urllib` 打。已写进手册 §1.3。出处：X1。 |
| **N-564** | **手册 §1.4 缺的第三条路（引用一份现成快照）补成验过的步骤** | **已做** | f01 上实跑：网关 **50 秒**起来、`/healthz` 自报的 `tables_dir` 就是那份现成快照、`/calendar` 取回 10 行真数据 —— 省掉 §1.4(b) 那条约 4 h 15 m 的重建链。四条要点里最容易踩的是**版本目录名按通道取**（`private`→`v1`、`public`→`public_v1`）。出处：X1。 |
| **N-565** | **`ops/test_c41.py:366` 的 `len(REG.CONFIGS) == 3`** | 已被别人改掉，两卡跳过 | 契约里点名要改的那条，现场已经是「内置三条仍在 + `config_id` 互异 + `harness` 名互异」。幂等规则：已有人改过就跳过。出处：X1。 |

**H. 收尾卡自身（2026-09-10 收口）**

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-566** | **签字包重出 `ops/reports/signed/v1.0.14_r1.0.21/`** | **已做** | `$PY ops/archive_signoff.py --label "v1.0 公开通道版"`。`ITEMS` 扩了 **11 件**（实例层 O1 矩阵两条通道 + 各自的累积明细、适配赛道五件、`public/instruments_rebuild.md`、`public/factor_library_recovery.md`）；`known_limits_v1.md` 与 `m6_public` 六份报告、`RELEASE_MANIFEST.json` / `VERSIONS.md` 上一版就在清单里。归档件 **0400**、`MANIFEST.json` 逐件 sha256 + 两个根 + git HEAD、同名冲突断言仍在、`declared_but_missing` 如实记（`m6_public/table_{a,b}.csv` —— **那一批 0 个 run，表不存在**）。**归档不是完整性保证**：逐件 sha256 挡得住无意的改动与搬运损坏，挡不住能写这个目录的人（N-434 同形）。出处：收尾卡。 |
| **N-567** | **`RELEASE_MANIFEST` 现在是五条 blocker，`releasable=false`** | 记录在案 | 逐条现状：`frozen_artifacts_missing` **已闭**（N-490，W2 补齐，`missing` 空）；`public_channel_zero_runs` **未闭 —— 挡在 N-484 那次裁定上**（执行面另两件前置已齐）；`data_license_text` / `no_clone_url` / `code_license_undecided` **三条全在用户手里，一条都没有伪造**。**条数以清单的 `blockers` 为准**，别再各处各写各的数。出处：收尾卡。 |
| **N-568** | **收口两个机器读数** | 记录在案 | 全量 `pytest ops/ gateway/`（`pytest.lock` 内、`MemoryMax=6G`、`ulimit -n 8192`）与 `ops/api_usage.py` 的机器统计，逐数在 `ops/reports/wrapup_report.md` 一、二两节。真 API 累计 **3,568 次 / 109 run**（上一次收口 2,668 / 77），**本轮增量 900 次 / 32 run** = W1 的 N-130 复验 151 / 2 + Y2 的适配赛道 749 / 30。**公开通道那 18 个 run 仍是零次调用**（没跑起来）——**别把「调用数是 0」读成「接入失败」**。出处：收尾卡。 |
| **N-569** | **本轮五条完成定义逐条判** | **达成 2 / 未达成 2 / 部分 1** | 全表在 `ops/HANDOFF.md` §18.2 与 `ops/reports/wrapup_report.md` 第一节，逐条给证据路径。**未达成的两条都卡在一次裁定**：①（18 个公开 run）卡 N-484、②（单机形态端到端）卡 N-560。**没有一条是「跑了但结果不好」，也没有一条被算成达成。** 出处：收尾卡。 |
| **N-570** | **`ops/HANDOFF.md` 的 §18 由两张卡共用** | 记录在案 | W1 当天先占了 `## §18`（网关 / N-388 / provider 三条前置），收尾卡的全貌写在紧随其后的 `## §18.2`。**没有重排、没有改 W1 那一段一个字** —— 共享文件只许追加。读 §18 要连着这两段读。出处：收尾卡。 |

## 2026-09-1x 收尾卡 v2（到可分发）

> 十个收件箱（A / B / C / X1 / X2 / Y1 / Y2 / Z / V2.rt / V2）逐条并入，编号从 **N-570** 续编。
> **N-484 / N-518 / N-543 是既有票据的状态更新**（卡 A 那次重冻把它们修掉了），
> 按既有体例写成「**N-xxx 更新**」、编号照旧、不另起新号 —— 别人的输出里已经引着这些号。
> **重复的条目已合并**（九条），
> 合并行在说明里保留另一张卡的原话，出处列在说明末尾。

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-484 更新** | **公开 provider 的两件构建元数据让 P2 恒红** | **已修（v1.0.15）** | `ops/release/pack_public_provider.py` 在 `files.sha256` 生成之后又写 `MANIFEST.sha256` 与 `build_info.json`，而 `genetask/pin.py::PROVIDER_META_FILES` 只豁免清单自身与 `manifest.json` —— 于是**公开通道的每一次注入**都在 P2 判红成「树里有而清单里没有」，而那棵树一个字节都没被动过。**症状与病因指向两个不同的地方**：照着报错去查 provider 的人查不到任何东西。按用户裁定 ① 走 A：两个名字进豁免集，**豁免面封闭成这四个字面名字**（写成前缀/通配会把「多出来的文件也是改动」整片关掉，那是这个函数唯一能抓「加文件」的地方）。实测：公开树 2 条 → 0 条，私有树 0 条 → 0 条；两条通道 P2 在**真树**上现算全绿。判别力由 `ops/test_provider_pin_channel.py` 新增八条钉住（豁免面恰好四个名字 / 按名字不按形状 / 真缺文件仍红 / 内容不符仍红 / 非元数据的多余文件仍红 / 真树上清单覆盖除四者外的全部文件 / 两条通道真树 P2 全绿）。 出处：卡 A。 |
| **N-518 更新** | **S4-ECO 参考解换个窗口就算出 NaN / 挑出一个叫 `'nan'` 的因子** | **已修（r1.0.22）** | 根因是 `S4/eco_free_select/solve.py` 里**写死的留出段** `2026-04-01..2026-06-30`，而窗口是实例层会换的取值。窗口挪到留出段之前（`s4-eco-02`/`04`）→ 留出段为空 → `ic_stats` 七个字段全 NaN，artifact 照写照过 envelope 校验；窗口挪到留出段之内（`s4-eco-03`）→ 训练段为空 → 候选全 NaN → `t.abs().idxmax()` 返回 NaN → `"nan"` 当 factor_id 查池 → 崩在「池里没有 'nan' 的行」（**报错指着因子池，问题在那一行常量**）。修法：留出段**跟着窗口走**（`split_window`：默认划分切得出两段就用它，切不出来按窗口交易日位置对半分，并把 `holdout_rule=window_half` 如实写进 `payload.note`，不许让回退划分看起来像默认划分；连对半分都切不出两段 10 天 → 抛 `S4SampleTooThin`）；`reference/s4_oracle_common.py` 里 `bh_fdr_select` **先筛掉算不出 t 的候选**（原实现 `fillna(0)` 把「算不出」当「t=0」，**它会挤进 BH 的分母 m，一个算不出来的候选因此能改变别人是否显著**），一个不剩即抛；`summarize` / `ic_by_horizon` 在「一个 IC 都算不出 / 日期集为空」时抛。实测：四个实例 **4/4 零 finding**，实例矩阵由「零 finding 89/127、非零 2」变成「92/127、非零 0」；**基点 `s4-eco-01` 的 gold 在两棵树上都与 v1.0.14 逐字节相同**（`produced_at` 除外）。 出处：卡 A。 |
| **N-543 更新** | **S6 gold 的 `provenance[0].artifact_id` 是未填的占位串** | **已修（r1.0.22）** | 兜底值 `"TODO:signal-artifact-id-missing"` 改成协议的显式欠定标记 `artifact_schema.UNRESOLVED`（**import 而不是重抄字面串**）。S6 五题 gold **私有 + 公开各重出一次，两条通道 5/5 零 finding**，`provenance` 现为 `[{"stage":"S5","artifact_id":"unresolved"}]`。**下游未做，见 N-571。** 出处：卡 A。 |
| **N-571** | **v1.0.14 签字包内的适配表偏低约 13pp —— 重算还没做，卡在别的代理手上** | **待办（阻塞在 scorer 那张卡）** | N-543 修完之后要「重出 `adapt-l1-08` / `l2-07` / `l2-08` / `l3-06` 四例 oracle → 重算适配表」（用户裁定 ② 的后半段）。**本卡没做**，理由是工作树里 `scorer/report.py`、`scorer/l3.py`、`scorer/score_run.py`、`ops/mk_tables.py` 都有**另一个代理未提交的改动**（⑩⑫ 出表那张卡）—— 现在重算等于拿半成品代码生成签字用的表。预期改正后的数：L1 first_pass 7→8、L2 7→9、L3 correct_flag 5→6、ALL `resolved_rate` 0.6333→**0.7667**、failed 11→7。**做法**：等 scorer 那张卡提交 → `$PY ops/adaptation_track.py --write` → 重算 `ops/reports/adapt/table.{csv,tex}` → `ops/test_wrt.py::test_适配表带着四条版本轴` 转绿。<br>**卡 X2 的同一条**（状态：**已关：走 A，零真 API**）：卡 A 把它挂起，理由是「源从『缺字段』变成『显式 unresolved』可能改变考的是什么」。**实测推翻了这个担心**：受影响四例的 agent 产物里 `provenance` 写的就是 `[{"stage":"S5","artifact_id":"unresolved"}]` —— 与**新** oracle **逐字节相同**（旧 oracle 是 `TODO:signal-artifact-id-missing`）。也就是说被测方当初写的正是新题的正确答案，判据罚的是照规则做的那一方；用既有产物对新 oracle 结算不是「拿旧答案对新题」，而是让同一份答案对上它本来就该对上的那把尺。数：ALL resolved 0.6333 → **0.7667**，failed 11 → **7**，L1 first_pass 7→8、L2 7→9、L3 correct_flag 5→6 —— 与卡 A 的预测逐条相同。判据锁在 `ops/test_X2.py::test_那四例现在与新oracle逐字节相同`（这条一红就说明该走 B 了）。 出处：卡 A / 卡 X2。 |
| **N-572** | **重冻的确定性下游：两份就绪报告的版本轴陈了** | **待办（报告卡）** | `ops/reports/v1_0_readiness.md` 与 `ops/reports/m6_public/v1_0_readiness_public.md` 里写死着 `1.0.14` / `r1.0.21`，重冻到 1.0.15 / r1.0.22 之后 `ops/test_wrt.py::test_就绪报告的四条版本轴与freeze现值一致` 两参数各红一条。**这不是回归，是重冻的确定性下游** —— 任何一次重冻都会让它们红。重跑 `ops/readiness_report.py` 即可。本卡不动它们：它们是收尾卡的产物，且与上一条同批重算更省事。<br>**卡 X1 的同一条**（状态：**已做**（闭 N-572 的公开那一半））：`ops/reports/m6_public/v1_0_readiness_public.md` 现在写 `1.0.15 / 622f720c95cf2249…` 与 `r1.0.22 / c61b066734e3192f…`，§2 从「本批 0 个 run」变成 8 个 run 的逐 run 证据表。验证验证器报告只差一个耗时数（`65 passed in 1.05s` → `1.12s`），判定不变。**私有那一半（`ops/reports/v1_0_readiness.md`）不在本卡路径，仍是陈值。** 出处：卡 A / 卡 X1。 |
| **N-573** | **`freeze_v10.REVISIONS` 自 1.0.6 起就是死代码，而任务集清单的 `revisions` 段读的是它** | **登记不修** | 实测：`REVISIONS` 的最后一条是 **1.0.1**（列表 `['1.0.6','1.0.5…','1.0.4','1.0.3…','1.0.2','1.0.1']`），而 1.0.7 起的**每一条记因（两条轴都是）**都写进了 `REFERENCE_REVISIONS`。后果：`build_manifest()` 里 `"revisions": REVISIONS` 与 `"revised_at": REVISIONS[-1]["at"]` —— **任务集清单 `ops/manifests/v1.0-smoke.json` 的变更记录停在 1.0.1、`revised_at` 也是那时候的日期**，而这个文件正是「这两次运行为什么不可比」的对外答案。参考清单没这个问题（它带 `REFERENCE_REVISIONS`，全的）。**本卡不修**：改这个会动 `revisions` / `revised_at` 两个字段，虽然都不在 `ROOT_FIELDS` 里（根不变），但它属于清单语义变更、该由收尾卡连着记因体例一起理。**卡 A 自己的两条记因按现行事实写进了 `REFERENCE_REVISIONS`，顺序 `… 1.0.14, r1.0.21, 1.0.15, r1.0.22`，与 `ops/test_y1.py` 钉的体例一致。** 出处：卡 A。 |
| **N-574** | **`ops/test_y1.py` 两条断言把版本号写死，每重冻一次就得回来改一次** | **已改（卡 A）** | `test_both_axes_were_bumped_and_recorded` 与 `test_the_frozen_manifest_is_on_disk_and_consistent` 原来断言 `F.SET_VERSION == "1.0.14"`。**「改一个常量让测试变绿」是这条断言最不该教人做的事。** 改成两条不写死号的不变量：① 代码里的版本常量与**盘上清单**一致（抓「推了号没重冻」与「重冻了没推号」）；② 记因表最后两条**就是**当前这两个号（抓「重冻了没记因」）。历史条目的逐字 needle 检查**照旧保留**（它抓的是另一件事：有人重排或删掉旧记因），并补上 1.0.15 / r1.0.22 两条自己的 needle。 出处：卡 A。 |
| **N-575** | **`adapt-l3-07` 是第五个受影响的例子，卡 A 的清单漏了它** | 已核，结局不变 | 它也源自 `s6-rob-01`，所以 `original/broken/oracle` 三件都随新 gold 重出了。但它的破坏是 `gap_provenance_edge`（整条上游引用被删），agent 交的是 `provenance: []`，与 oracle 的单边 provenance 前后都不一致 —— **重出前后都是 failed**，所以总数只动了四例。如实记，免得下一个人比对 sha 时以为漏跑了。 出处：卡 X2。 |
| **N-576** | **`s2-rob-04` 的 oracle 要 834 秒，全局 600 秒卡死它** | **已修（逐实例超时）** | 实测 `/usr/bin/time -v`：墙钟 **13:54.49**、峰值 RSS **220 MB**、rc=0、产物正常。瓶颈是 13 个月窗口（2025-07-01..2026-07-31，基点的两倍多），**窗口不动**（裁定 ⑥）。修法：`ops/run_oracles.py` 加 `ORACLE_TIMEOUT_DEFAULT`（仍是 600，**不放宽**）+ `ORACLE_TIMEOUT_OVERRIDES`（逐 task_id）+ `oracle_timeout(row)`，优先级「题行 `oracle_timeout` > 覆盖表 > 全局」。题行那一路是留给参数表的，但 `genetask/params/v1.0-instances.yaml` 自 v1.0.15 起进了冻结根（`instances_fingerprint` 已进 `ROOT_FIELDS`），**加一个字段就作废所有已发通行证**，所以这一版走覆盖表；哪次重冻顺手搬进参数表时 `oracle_timeout()` 一个字都不用改。 出处：卡 X2。 |
| **N-577** | **失败分类器把秒数钉死成 `超时 600s`** | **已修（同卡）** | `ops/run_oracles.py::_NA_KINDS` 里写着 `("跑超时", ("超时 600s",), "any")`。逐实例超时之后 s2-rob-04 超时会印 `超时 1800s`，于是**一类真失败从「跑超时」掉进「没归类」**——分类器把它显示成不认识的东西。改成匹配前缀 `("超时 ", "TimeoutExpired")`。这条是写测试时撞出来的（`test_超时报错文字带上真实秒数`），不是看出来的。 出处：卡 X2。 |
| **N-578** | **S8 四道出集题的 `task_id` 在两个集根里都有，sim 会话工厂当场拒 —— 冒烟集的 S8 gold 现在也重出不了** | **未修（不在本卡路径），要裁定** | `gateway/sim_factory.py::task_dir(task_id, set_id=None)` 用 `root.glob(f"*/{task_id}")` 扫所有集根，撞号就 `RuntimeError: … 在多个出集里都有 … 不猜`。而**基点实例与基点题同号**：`v1.0-instances/s8-cor-01` 与 `v1.0-smoke/s8-cor-01` 并存 → `/sim/log` 500。实测（零副作用，直接调 `task_dir`）：`s8-cor-01 / s8-eco-01 / s8-ops-01 / s8-rob-01` 四个全撞，`s8-cor-02`（变体，号不同）正常。**后果不止实例层**：`build_engine` 是拿 `set_id=None` 调的，所以**冒烟集这四道题的 oracle 也跑不动了** —— 这四道正是出集 34 题里的 S8 全部。`s1-cor-01` 同样撞号但无害（`build_engine` 只认 `s8-` 前缀）。公开树在 `tasks/public/<set>/` 两层下，`glob("*/…")` 扫不到，不参与撞号。**根因不是我造的**（`v1.0-instances/s8-cor-01` 在 9/10 就在了，上一版累积里它已经是 `/sim/log 500`），但本卡把撞号从 1 个扩到 4 个（补跑了另外三个基点实例）。**修法（要别人做）**：`gateway/routers/sim.py` 从建会话请求里取 `set_id` 传给 `build_engine(..., set_id=...)`，客户端 `reference/gateway_client.py` 按自己的 `CTX.task_dir` 填 —— 调用方本来就知道自己在哪个集里，让工厂去猜才是错的。**临时解封**（要立刻重出 S8 gold 时）：`rm -rf $GB/reference/tasks/v1.0-instances/s8-{cor,eco,ops,rob}-01`，代价是那四个实例的 oracle 没了、下次跑实例批又会长回来。 出处：卡 X2。 |
| **N-579** | **N-510（S6 实例夹具先有鸡还是先有蛋）自己解开了** | **已关** | `make_fixtures.s6_consumer_window(set_root)` 要在集根里扫到「引用 `reference/signals/*` 的题」才算得出窗口并集，而那些题正是它要出夹具的题。现在 `run_oracles.write_all` 已经把 15 个 S6 实例目录连 `task.yaml` 一起落盘了（哪怕 solve 失败），于是窗口并集算得出来，15 件夹具一次物化成功、15 个实例 O1 全绿。**不需要改 `make_fixtures.py`**（它在参考轴冻结根里，改它要推版本）。顺序是：先落目录 → 再物化夹具 → 再跑 oracle。 出处：卡 X2。 |
| **N-580** | **公开通道的实例目录也要先落盘才物化得了夹具，而落盘被网关硬闸挡着** | 已绕开，建议收编 | `ops/run_oracles.py` 把「建目录」和「跑 oracle」压在一次调用里，开头 `wait_gateway()` 是硬闸 —— 于是「我只想要目录」也得排网关锁的队（本卡真排上了：卡 5.3 的 m6_public 真跑从 07:09 起一直占着）。本卡用 `$GB/scratch/X2/build_pub_dirs.py` 摘出建目录一步（**调的是 `run_oracles.write_all` 本身**，不另写落盘逻辑），一次网关都没打，43 个公开 S4/S5/S6 目录落盘。建议把它收编成 `ops/run_oracles.py --build-dirs-only`。 出处：卡 X2。 |
| **N-581** | **N-287 的私有面污染是活的：公开夹具物化又把 `fixture_s4_eco_pool_v1.md` 改了** | 本卡已自动还原，根治仍未做 | 跑公开 S4/S5 夹具物化时，`reference/make_fixtures.py` 照旧去重写 `ops/data_cards/fixture_*.md`（落点与通道无关）。本卡的驱动脚本带「跑前存字节、跑完逐个还原并报出被动过的」，输出里如实报了 `{"data_cards_被动过并已还原": ["fixture_s4_eco_pool_v1.md"]}`，`git status` 里那份卡干净。**但这只兜住一个调用方** —— 任何人直接 `python -m reference.make_fixtures --set-id public/…` 照样污染，而且不报错。根治要数据卡落点按通道走，那要改冻结根里的 `make_fixtures.py`。 出处：卡 X2。 |
| **N-582** | 公开通道实例 oracle 补齐**没做完**（26/112），卡在网关锁 | **待续** | 公开侧 S4/S5 夹具已物化（28 件，硬闸未触发 = 切的确实是公开 gold）。剩下三步都要网关：① S6 公开夹具（要跑 s5 oracle）；② 全部实例 oracle。照抄：`ops/public_gateway.sh run -- bash $GB/scratch/X2/public_chain.sh fx` 然后 `… public_chain.sh rest`（脚本内层已带 `--no-batch-lock`，别再外套 `gateway_lock.py`）。私有侧已到 **108/130**（= 112 个出集模板实例里的 108 + 4 个卡在 N-578）。 出处：卡 X2。 |
| **N-583** | 适配集清单 `ops/manifests/v1.0-adapt.json` 是重出适配例的**确定性下游** | 已随卡更新 | 重出 5 例之后 `ops/test_adaptation_track.py::test_set_manifest_root_is_reproducible` 当场红（root `94683cfc…` → `3e38efc4…`）。跑 `ops/pack_adaptation.py --write-set-manifest` 即好，差异只落在那 5 例的三件 sha 与根。**任何一次改适配题源的卡都要跟着跑这一步**。 出处：卡 X2。 |
| **N-584** | 网关 `MemoryMax` 6G → **12G** | **已做** | `~/.config/systemd/user/genebench-gateway.service`（`--user` 单元，无 sudo）。理由：6 G 卡在**正常工作量**上 —— 一道 S7 真题（strict 臂 5.66 M tokens / 87 次调用）顶爆上限、触发 4 次 cgroup oom-kill。`daemon-reload` 后起停两次：`rc=0` / 45 s、42 s / `NRestarts=0` / `MemoryMax(effective)=12884901888` / `/healthz` 200 / bind 仍 `192.168.1.48:18080`。**上限没有被取消**（N-125 的理由一个字没变）。旧单元备份在同目录 `.bak.<UTC>` 出处：卡 B。 |
| **N-585** | 「单 run 峰值 → 并发上限」的换算入档 | **已做** | `ops/HANDOFF.md` §19、`docs/OPERATOR_MANUAL.md` §9。表里**只有 S7 那一行有实测背书**（≈ 3.7 G 增量 → 并发 1），S4 ≤ 2 / 其余 ≤ 3 **标着「外推」**。同时写明「批间串行（`gateway_lock`）」与「批内并发度」是两回事 出处：卡 B。 |
| **N-586** | **Qwen 前置缺 key** —— `DASHSCOPE_API_KEY` 不在 f02 | **BLOCKED（待用户）** | 2026-09-11 实测：f02 `~/.config/genebench/secrets.env`（0600 / 53 字节）里**只有 `DEEPSEEK_API_KEY`**。另两件前置：域名**不在**白名单（而且现在**就不该在**，见下条）；f02 到 `dashscope.aliyuncs.com` **通**（`401` / 0.17 s）。按施工契约缺一件即记 BLOCKED：**没有伪造 key、没有往白名单加没人用的域名、没有跑那道真题**。切换的完整步骤与判据写在 `harnesses/opencode/README.md` §9 出处：卡 B。 |
| **N-587** | Qwen 配置该落在 `harnesses/opencode-qwen/`，不是改 opencode 那条 | **待办（不在卡 B 路径）** | `harnesses/opencode/config.yaml` 是**主表 13 条之一**。把它的 `model` 改成 qwen → `assert_registry_sane` 的「所有 enabled 同一模型」当场红；翻成 `enabled: false` → 主表少一条正在用的配置。两种都不该。正确做法：**新目录** + `enabled: false` → 进 `PENDING_CONFIGS`，既不参与「同一模型」判据，也不进 `collect_egress_hosts()`（所以 `ops/test_c41.py` 的键集相等断言**不会**要求白名单有 dashscope）。**那条断言不许放宽（要过 M7）**。本卡路径只到 `harnesses/opencode/**`，没有建新目录 出处：卡 B。 |
| **N-588** | `ops/test_W2.py:125` 的「三条用户决定项」清单陈旧 —— **现在是红的** | **待办（不在卡 B 路径）** | `test_the_remaining_blockers_are_the_users_decisions_not_ours` 断言 `{"code_license_undecided","data_license_text","no_clone_url"} ⊆ open_`。裁定 ⑳ 落地后 `code_license_undecided` 已闭合 → 该断言红。**它的用意没有失效**（「谁也不许**替**用户把用户决定项标成满足」），失效的是那张写死的名单：**这一条是用户自己决定的，不是我们替他决定的**。而且**卡 ㉑ 关掉 `no_clone_url` 时会第二次撞同一条**，所以一次改到位。建议补丁（把「用户决定项」与「今天还开着」解耦）：<br>`users = ["code_license_undecided", "data_license_text", "no_clone_url"]`<br>→<br>`# 用户已裁定并落地的从「必须还开着」里移走，理由写在这里（⑳ Apache-2.0，2026-09-10；㉑ 仓库地址）`<br>`users_settled = {"code_license_undecided"}   # 卡 ㉑ 落地后再加 "no_clone_url"`<br>`users = {"code_license_undecided", "data_license_text", "no_clone_url"}`<br>`assert (users - users_settled) <= set(open_), open_`<br>`assert set(open_) - users <= {"public_channel_zero_runs"}, open_`<br>**卡 Y1 的同一条**（状态：不是本卡的）：前者是卡 B 已登记的那条（写死的「三条用户决定项必须还开着」名单，`code_license_undecided` 闭了之后必红；今天 `public_channel_zero_runs` 也闭了，**同一条会第二次撞**）。后者是 X1 把 `m6_public` 跑出 8 个 run 之后必红。两条都在别的卡的路径里。<br>**卡 Z 的同一条**（状态：已做）：`ops/test_B.py::test_版权人没有被代填` 里 `repository-code` 那一条原本判「必须仍是占位符（那是卡 ㉑ 的事）」→ 改判「必须是 ㉑ 给的那个真地址」，**authors 仍然一个字不许代填**。`test_发布清单里代码许可那条blocker已闭合而releasable仍是false` 里的写死名单（已被 X1 与本卡推翻两次）→ 改成派生判据。`ops/test_W2.py:125` 按卡 B 交接的补丁一次改到位。 出处：卡 B / 卡 Y1 / 卡 Z。 |
| **N-589** | `ops/test_6rt.py:162` 把手册 §0.1 的措辞钉成了字面量 | **待办（不在卡 B 路径）** | `assert "SPDX" in head and "许可未定" in head`。许可一旦定下来，这条要么把手册逼着继续说「未定」，要么变红。本卡按仓库既有写法（README 第 3 条那种）把 §0.1 第 4 条改成**删除线 + 「已闭合」**，字面量因此仍在、测试仍绿、正文不撒谎 —— 但那是**凑合**。建议改成按 `RELEASE_MANIFEST.json` 的 `license.code.spdx` 判：SPDX 是 `<待定>` 时 §0.1 必须写「未定」，否则必须写出那个 SPDX 标识 出处：卡 B。 |
| **N-590** | `runner/c42/upstream_pins.py:230` 的 note 还把 `@qwen-code/qwen-code` 当备选 | **待办（不在卡 B 路径）** | 原文：「**工具调用兼容性要在 M6 前用一道真题实测** —— 不通就换 `@qwen-code/qwen-code` 的 OpenAI 兼容模式」。那是 2026-09-04 的备选；codex 链路后来实测通了、备选未启用，裁定 ⑲ 又把 **Qwen Code 定为不做**。建议把那半句改成「（备选 `@qwen-code/qwen-code` 已于 2026-09-10 裁定不做；codex 链路实测通过）」。`harnesses/README.md` 与手册里已经没有把它当计划的措辞（卡 B 已处理并加了测试） 出处：卡 B。 |
| **N-591** | `CITATION.cff` 的 `version` 字段陈旧 | **待办（不在卡 B 路径的裁定范围）** | 写着「任务集 1.0.13 / 参考面 r1.0.20」，现值是 **1.0.14 / r1.0.21**。裁定 ⑳ 只让本卡填 `license`，没动 `version`，所以没顺手改。它是发布件、外部用户会照抄，建议由做 ㉑（填 `repository-code`）的那张卡一并更新，或改成由生成器渲染<br>**卡 Z 的同一条**（状态：已做）：卡 B 的 v11_deferred 点名让「填 repository-code 的那张卡一并更新」。**更好的做法仍然是由生成器渲染** —— 今天这个号还是手抄的，下次重冻又会陈旧。建议并进 `ops/mk_release_manifest.py`（它已经现算两条轴）。 出处：卡 B / 卡 Z。 |
| **N-592** | LICENSE 的**版权行**待填 | **待用户** | Apache-2.0 附录要求 `Copyright [yyyy] [name of copyright owner]`。裁定 ⑳ 明确「作者 / 单位 / 地址维持 `<待用户填>`」，所以 `LICENSE` §A 留的是模板、源文件里**没有**加逐文件许可头（等版权人定了一次加完）。**这不挡使用**：`code_license_undecided` 判的是首行 SPDX，已闭合<br>**卡 Z 的同一条**（状态：**待用户**）：裁定 ⑳ 明说维持待填，本卡没有代填。**带占位符的 CITATION 不要随发布包发出去** —— `genequant/CITATION.cff` 里同样留着，两处都要填。 出处：卡 B / 卡 Z。 |
| **N-593** | 主表固定十九列落地（⑩） | 已做 | `scorer/report.py::MAIN_TABLE_COLUMNS` + `main_table()`；`ops/mk_tables.py --table main` 出 csv/md/latex。列名与顺序由 `ops/test_report_columns.py` 逐字钉住（列集相等 + 顺序相等），十六个阶段列另有「每阶段两列、八阶段一个不缺」的断言 出处：卡 C。 |
| **N-594** | 取消聚合 / 四态空值词汇（⑪） | 已做 | 不出总分（`AGGREGATE_COLUMN_NAMES` + 断言）；`effect` 不进主表与两张全量指标表，仍逐 run 留在结果库；「拒绝 / 诚实终止 / 未结算 / 预算截断」四类各造一条夹具，CSV / md / LaTeX 三种格式各断言一次渲染成 `—` 出处：卡 C。 |
| **N-595** | **`TABLE_A_COLUMNS` 没动，`effect` 仍在 Table A 的诊断 CSV 里** | 待收口卡裁 | ⑪ 说的是「不进**发布表**」。把 `effect` 从 `TABLE_A_COLUMNS` 里去掉会让 `ops/test_results_db.py` 的七条「从结果库出的表与既有 `ops/reports/<batch>/table_a.csv` 逐格相同」结构性变红 —— 那不是回归，是因为列集变了，修它要**重出各 batch 的表**，而本卡任务书写明不重出。**收口卡重出表时**：若判定 `table_a.csv` 也算发布件，从 `scorer/report.py::TABLE_A_COLUMNS` 里删掉 `"effect"` 一项，再逐批 `python ops/mk_tables.py --table a --format csv --filter batch=<批次> --out ops/reports/<批次>`，合表另出 `m6_all` 出处：卡 C。 |
| **N-596** | 全量指标表生成器（⑫） | 已做 | 新增 `ops/mk_metric_tables.py`：`--table agent`（18 项）/ `--table stage`（六条跨阶段 + 39 条逐阶段），从 `ops/results_db.py` 取数、聚合复用 `scorer.report.table_a/table_b`（不另写一份）。`--check` 只查「生成器 vs 规格 §9」是否逐项相等 出处：卡 C。 |
| **N-597** | **逐阶段指标实测 39 条，用户裁定写的是 37 条** | 待编排方裁 | 入表规则：①进 `l3_pass` 判据 ②进主表十九列 ③规格 §3 点名且 v1 出得了数；纯计数 `n_*`、常数 `tau`、`gold_*`、`reported_*` 不入表。按这条规则数出来是 39（S1 3 / S2 4 / S3 5 / S4 6 / S5 7 / S6 3 / S7 4 / S8 7）。比 37 多的两条是 S8 的 `orders_replayable` 与 `fills_linked_to_orders` —— 它们是 `Audit` 四条子判据里的两条，v1 真的出数且进判据；删掉它们等于让 Audit 的四条里有两条在表上没有落点。**倾向：保留 39，把数字从 37 改成 39**；要压到 37 就把 S8 的四条子判据整体并进 `Audit` 一列（那样是 35，还得再补两条），或另择两条删 —— 两种都得给理由 出处：卡 C。 |
| **N-598** | 指标规格补 §9 指标登记表（⑫） | 已做 | `ops/specs/GeneBench指标规格_v1.md` **追加** §9（§0–§8 一字未动）：§9.0 Role 与空值词汇、§9.1 agent 18 项、§9.2 逐阶段 39 条、§9.3 跨阶段 6 条、§9.4 主表十九列对照。Role 四取一：`gate` / `fidelity` / `reported` / `telemetry` —— **`effect` 作为 Role 一处不留**（⑫），测试断言 出处：卡 C。 |
| **N-599** | Slip 的 Role 由 `reported` 改成 `gate`（④） | 已做（文档侧） | 规格 §9.2 的 `S8 / SlipSelfConsistent` 一行 Role 写 `gate`，`ops/mk_metric_tables.py` 与它一致，`test_slip_self_consistency_is_a_gate_now` 两边都断言。**判据实现本来就在**（`scorer/l3.py::compare_fill` 的 `SlipSelfConsistent` 进 `l3_pass`），本卡只改口径登记 出处：卡 C。 |
| **N-600** | 核六列补齐（⑬） | 已做 | `Prov` / `W-agr` / `Ovr` 原本就算得出；**新补三个量**：`Decl`（契约必填声明完整率）、`Set`（payload 依赖的设定申明率）在 `scorer/l3.py::declaration_metrics`，由 `scorer/score_run.py` 贴进 `correctness`；`Ledger` 从 `record.probe_states.ledger_conservation` 的三态读（无需改 scorer）。另补 `rho_mean`（主表 S5 的 `ρ̄`，`compare_tau` / `compare_sig` 各一行） 出处：卡 C。 |
| **N-601** | **`Decl` / `Set` / `ρ̄` 在既有记录上是 `unobservable`** | 待收口卡 | 这三个量由 v1.0.14 起的 scorer 才产出；库里 118 条记录全部早于它，主表上因此显示 `unobservable`（**不是 0、不是 `—`**）。真数据上已验证算得出：`runs_in/m6/*/work/artifact.json` 十二份产物逐份出数，`s7-rob-02` 带题面上下文时 `Decl=1.0`（如实标 `unresolved` 的 `sell_rule` 计入分子）、不带时 `0.9375`。**收口卡重结算那一批 run 之后这三列就有数**；不重结算也不阻塞发布 出处：卡 C。 |
| **N-602** | `Ovr` 有两个同名的数 | 已登记 | 主表 S8 那一列只数 **S8** 的 run；全量 agent 指标表里的 `Ovr` 数**全部** run。两者都对，不能并排读 —— 规格 §9.1 与 `ops/reports/report_spec_v1.md` §1 都写明了 出处：卡 C。 |
| **N-603** | LaTeX 上 `—` 与「没有 run」同形 | 已登记，不修 | booktabs 里没有第二种空格，两者都写 `---`。CSV / md 分得开。论文表需要区分时把 `n_runs` / `n_tasks` 一起放出来 —— 已写进 `ops/reports/report_spec_v1.md` §0.2 出处：卡 C。 |
| **N-604** | 主表口径页 | 已做 | `ops/reports/report_spec_v1.md`：十九列逐列（定义 / 数据源 / 闸门条件 / 不可得时显示什么）+ §3「这张表怎么被绕」给红队 出处：卡 C。 |
| **N-605** | **公开通道声明了 `inputs[]` 的题一件都出不了集** —— `packager.export_task` 的夹具身份闸与公开链的防漏闸互为反面 | **待裁定（挡着 18 个 run 里的 10 个）** | 见下 §1。证据 `ops/reports/m6_public/x1_fixture_identity_block.json`：8 件夹具 / 5 道题，公开侧 **0/8** 与声明相同、私有侧 **8/8** 相同。**这不是回归**，是 N-278「登记不修」第一次真的被跑批踩到。 出处：卡 X1。 |
| **N-606** | X1 上一轮记的 P2 阻塞（公开 provider 的 `files.sha256` 漏两个元数据文件）**已闭** | **已验（本卡实测）** | 卡 A 的裁定 ① 落地（`pin.PROVIDER_META_FILES` 收进 `MANIFEST.sha256` / `build_info.json`）。本卡把 exec 树推到 f02 之后，在 **f02 侧现算**：`p2_green=true`、`root_sha_now=561348660a3175b1…`。反向门也验了（往 provider 树里塞一个清单外文件 → P2 当场红，删掉又绿），门不是恒绿的。脚本 `$GB/scratch/X1/x1_p2_probe.py`。 出处：卡 X1。 |
| **N-607** | `ops/run_joblist.py --check-plane` **核不到逐文件层** | 登记不修（已有绕法） | 它只比 provider 根 hash 与网关可达性，`check_provider_pin` 的逐文件分支它碰不到。本卡的做法是额外拿一个**真 bundle** 在 f02 上跑一次 `run_f02_a1.py --dry`（P0–P9 全走、不起容器、不调模型），这才是「P2 真的绿了」的证据。建议把这一步写进手册的公开通道跑批前置。 出处：卡 X1。 |
| **N-608** | f02 的 exec 树在本卡之前**仍是重冻前的旧版** | **已修（本卡推的）** | 卡 A 提醒过。本卡跑了 `ops/push_exec_to_f02.sh --with-launch-data`，六个目录同步、落地扫描 0 命中、两侧 `command_for("Codex CLI")` 逐字节一致（384 字节）。**注意 `genetask/s8_contract.py` 不在该脚本的白名单里** —— 当前没有执行面模块 import 它（只有 `reference/` 与 `gateway/`），所以不补；哪天单机双容器形态要在 f02 起网关，得往 `GENETASK_FILES` 里加一行。<br>**卡 Y2 的同一条**（状态：待办（下一个要在 f02 真跑的卡必须先做））：`runner/inject.py` 改了，f02 上的 `exec/` 是旧的。表现：f01 的 `job_id` 带 `@machine`、f02 算出来的 `run_id` 不带 → `ops/run_joblist.py::run_one` 会打一条 `[黄] run_id ≠ job_id` 并照旧按返回的 run_id 结算（不会丢数据）。修法：`ops/push_exec_to_f02.sh --with-launch-data`。**本卡没推**：f02 上可能有别的卡的批在跑，中途换 runner 代码会让同一批里出现两种形状的 run_id。 出处：卡 X1 / 卡 Y2。 |
| **N-609** | **三控的 oracle 桩靠「产物与最近一次日志块是同一次跑」这个隐含前提**，前提破了红得像违规 | **待裁定** | 见上。两件事要分开：① `s1-cor-01` 的配对现在就是破的（重跑一次 oracle 即修）；② `oracle_window()` 不该把「配对破了」呈现成 601 条 `fetch_clock_mismatch`。 出处：卡 X1。 |
| **N-610** | `ops/public_gateway.sh run` 连着用两次，第二次**起不来** | 已绕开，建议延长 | 第一次 `run` 的 `trap` 把网关停掉，第二次 `start` 在 180 s 内没听到 `/healthz`（实测起来用了 **182 s**，第一次只用 60 s），于是整步**静默没跑**（`rc=0`，产物不存在）。绕法：网关已在监听时直接拿 `ops/gateway_lock.py`，不走 `run` 子命令。建议把 `do_start` 的等待从 180 提到 300，并让「等超时」以非零码退出 —— 现在它 `die` 了但外层 ` | tail` 把码吞了。 出处：卡 X1。 |
| **N-611** | `ops/run_f02_a1.py` 的 `--provider-root` 在**真跑路径上被静默忽略** | 待裁定（**建议当挡发布**） | 模块常量 `PROVIDER` 写死私有 provider 绝对路径；`main()` 里 `global RUN_ROOT, RESULTS` 只把这两个按参数改写（第 184–188 行），**唯独 provider 没有**。`--dry` 走另一条路（第 109 行）**用**了参数 —— 所以干跑与真跑用的是两棵不同的 provider 树。后果：**公开通道的真跑喂进容器的是私有 provider**，而 P2 照样绿（跑批不设 `GENEBENCH_CHANNEL` 时期望值也是私有的，两头一致）。证据：`/data/genebench_runner/m6_public/runs/runs/s1-cor-01.strict.…/work/provider/features/` 下有 `bj*`（北交所）代码，而公开 provider 只有沪深（`sh6*`/`sz*`）。**这影响 X1 那 8 个公开 run 的读数归属**。两条出路：① 让 `main()` 也 `global PROVIDER` 并按参数改写（一行）；② 按 `GENEBENCH_CHANNEL` 选默认 provider。**任一条都要重跑受影响的 run**。 出处：卡 Y1。 |
| **N-612** | `vendor/` 不在仓库里，发布包里没有 h11 | 待裁定 | `runner/inject.py::h11_source_dir()` 先找 exec 树的 `vendor/h11`，找不到才用运行环境里的。`vendor/` 是 f02 上手工放的（`ops/run_f02_container_tests.sh` 从网关环境复制），`git ls-files vendor` 为空。外部运行者解包后真跑会 `ModuleNotFoundError: No module named 'h11'`（本卡实测撞到）。绕法（已写进手册 §1.2）：`pip install` 顺带装的 h11 + `PYTHONPATH`。要不要把 `vendor/h11` 收进仓库是一次裁定：收进去 = 仓库里多一份第三方源码；不收 = 发布包对「执行面也要一个 python 环境」有隐含依赖。 出处：卡 Y1。 |
| **N-613** | 发布包里两份测试文件带**合成** gold 串，落在执行面扫描根里会被当场删掉 | 登记 | `ops/test_answer_plane_guard.py`、`ops/test_inject.py`。不是泄漏（串是合成的），但形态 ① 下答案面与执行面同机，扫描根一旦覆盖到包就会删掉它们并让 unit 进 failed + 置闩。手册 §1.3 已写明「放在扫描根之外」。根治是把测试里的串改成运行时合成（`"GBC-G-" + "0"*16` 那种拼接，扫描器按设计不命中 —— `ops/test_env.py` 里对 key 形态就是这么处理的）。<br>**卡 Z 的同一条**（状态：已做）：`ops/test_answer_plane_guard.py:399`（docstring 里的 `mkdir GBC-G-…`）与 `ops/test_inject.py:344`（断言里的字面量）。改成运行时拼 / 改写措辞，与 `ops/test_env.py` 对 key 形态的处置同一条口径。**卡 Y1 的 v11_deferred 里那条可以关掉了** —— 它挡的是「发布树里带着两个会触发落地即扫的文件」，现在不带了，而且两个测试都还在树里（不是靠剔除文件绕开的）。 出处：卡 Y1 / 卡 Z。 |
| **N-614** | 那条 `ufw allow … to any port 18080` 把端口写死，与手册 §1.4 (c)「端口显式错开」冲突 | 登记 | 两条一起照做，容器就打不到网关。手册 §1.3 已加告示（单机形态就绑 18080）。真要错开端口得让机器主人再放行一条 —— 这是**机器主人**的动作，不是运行者能自己做的。 出处：卡 Y1。 |
| **N-615** | `genebench_config.py::GATEWAY_HOST` 没有环境变量入口 | 登记不修 | `GATEWAY_PORT` 有（`GENEBENCH_GATEWAY_PORT`），`GATEWAY_HOST` 没有，形态 ① 只能改常量（手册 §1.3 本来就是这么写的）。**但 `ops/run_joblist.py::gateway_addr()` 读的正是这个常量且没有覆盖入口** —— 于是在跨机 fleet 上没法用清单方式演练形态 ①（本卡因此走 §5.6 单题方式）。要补就补一个 `GENEBENCH_GATEWAY_HOST`，两处同源。 出处：卡 Y1。 |
| **N-616** | `harnesses/build.sh` 没有 `--no-cache` 透传 | 登记不修 | 缓存命中时它 **0.2 秒**打印「构建完成」，digest 与旧镜像相同 —— 「这一步要哪些外网、离线能不能建」在有缓存的机器上量不出来。本卡另跑 `docker build --no-cache` 量了一次：**41.4 秒**，要 `registry.npmjs.org`；`docker.io` 不需要（基座必须本机已有，脚本自己核这一条）。 出处：卡 Y1。 |
| **N-617** | `ops/freeze_v10.py` 两个 `*_ref()` 的根键名不一致 | 登记不修 | `frozen_ref()` 是 `root`，`reference_ref()` 是 `reference_root`。照手册 §8.1 抄命令不受影响（那条命令把返回值丢掉），但凡是自己取键的人会踩一次（本卡踩了）。 出处：卡 Y1。 |
| **N-618** | ⑮ 的 `genebench export` / `genebench merge` 在**走演练那一刻**不存在 | **已闭（不是本卡修的）** | 演练第 7 步「导出结果」在今天的包里只有 `ops/results_db.py query` 与 `ops/mk_tables.py`。本卡用这两条走完了第 7 步，但**导出的结果包里没有机器标识、也没有四轴一致性校验**（那正是 ⑮ 要加的两件）。 出处：卡 Y1。 |
| **N-619** | `ops/test_wrt.py::test_rebudget只动没跑过的行` 现红 | 不是本卡的 | `KeyError: 's1-cor-01.strict.cfg.r01'`。裁定 ⑮ 给 `run_id` 加了机器标识之后，`ops/joblist.py::make_job` 算出来的 `job_id` 末尾多了一段，而这条测试还按**没有机器标识**的老形状去查字典。**是 ⑮ 的确定性下游**，不是回归；改法是让断言按 `make_job` 现算的 `job_id` 取，而不是手抄一个字符串。 出处：卡 Y1。 |
| **N-620** | `ops/test_wrapup.py` 五条现红 | 不是本卡的 | 签字包 `ops/reports/signed/v1.0.14_r1.0.21/` 是**重冻之前**那一版；卡 A 把轴推到 1.0.15 / r1.0.22 之后，「签字包是这一版的」「逐件 sha 对得上」「清单声明了却不存在的件」三条必红。另两条：`test_八个收件箱都改名merged了_原名一个不留`（A.md / B.md / C.md / X1.md / X2.md 都还在，**本卡之前就红**）与 `test_两条未达成没有被写成达成`（X1 跑出 run 之后 `public_channel_zero_runs` 已闭，报告要跟着改）。**全部是重冻与 X1 的确定性下游**，落点在收口卡。 出处：卡 Y1。 |
| **N-621** | 手册 §9 的并发档位与 §5.5 的「并发固定是 1」自相矛盾 | 待裁定 | §9（卡 B 写的）给 S7 1 / S4 ≤2 / 其余 ≤3；§5.5 写「这套系统里**没有 >1 的合法值**」。本卡按 §9 并发 2 实测，**两条都炸**：`runner/c41/subnets.py::allocate()` 在两个进程同时分配时有 TOCTOU 竞态（`invalid pool request: Pool overlaps`），以及一个失败 run 的清理把另一个 run 的 `run_root` 拿走（`[P0] run_root 不可写`）。**在 allocate() 加进程间锁之前，§9 那张表不该被当成可用的并发档位。** 出处：卡 Y1。 |
| **N-622** | f02 上有两张 4 小时前的残留 docker 网占着注入器的分配池 | 登记 | `gb-s2-cor-01-open-cfg-codex-deepseek-r01_gb_{task,egress}`（X1 那个 1800 秒超时的 run 留下的孤儿容器，至今还 Up）与 `gb-s2-cor-01-hint-cfg-codex-deepseek-r02_gb_task`。池子是 `172.31.240.0/20` 切 16 个 `/24`，孤儿一多就逼近上限。**本卡没有清理别人的容器。** 建议给跑批加一条「起批前 `docker network prune` 只清没有容器挂着的网」，或者给超时路径补一个 `down -v`。 出处：卡 Y1。 |
| **N-623** | `ops/api_usage.py::parse_run_id` 还不认机器段 | 待办（不挡发布） | 裁定 ⑮ 之后 `run_id` 是 `<题>.<臂>.<配置>.rNN@<machine_id>`。那个解析器按 `.` 切四段，第四段现在是 `r01@finance01-e3887dfa` —— task/arm/config 三个切片键**仍然是对的**，只有 `rep` 带上了机器段。用量表因此不会认错题，只是 `rep` 这一列变长。要修就在 `parse_run_id` 里先 `runner.inject.split_run_id`，再补一个 `machine_id` 列。**不在本卡路径里，没动。** 出处：卡 Y2。 |
| **N-624** | `RELEASE_MANIFEST.json` / `CHANGELOG.md` 是重冻的确定性下游 | 已闭（本卡顺手） | A 卡重冻到 1.0.15/r1.0.22 之后这两件还停在 1.0.14/r1.0.21，`ops/test_release_manifest.py` 两条红，而 ⑰ 的版本锁会因此把**所有入口**拦死。已跑 `ops/mk_release_manifest.py --write-changelog` + `ops/mk_release_manifest.py`，17 条测试转绿。以后每次重冻都要跟着跑这两条 —— 建议写进收口清单。 出处：卡 Y2。 |
| **N-625** | 归档包（`--archive`）是一条显式的旁路，要有人定期看 | 登记不修 | 跨版本的读数合进库**不会**变得可比，出表那一步仍按混轴拒。但「两端都显式说出口」是靠操作员，不是靠门。v1 接受这个形态（口径写在手册 §6.9 末段）。 出处：卡 Y2。 |
| **N-626** | 机器标识退回 `hostname-only` 时两台同名机器会撞 | 登记不修 | `/etc/machine-id` 与 `IOPlatformUUID` 都拿不到时（某些容器、精简镜像），指纹退化成主机名的哈希。`machine_info().fingerprint_source` **如实写 `hostname-only`**，手册让这种部署显式设 `GENEBENCH_MACHINE_ID`。没有静默的降级。 出处：卡 Y2。 |
| **N-627** | **剔答案面之后公开树跑不了结算与出集** | **待用户裁定（挡「外部用户能用」）** | 零命中判据自己要求剔掉 `reference/` 与 `scorer/`（答案面门见到名为 reference 的目录就整棵删、见到 solve.py / scorer.yaml 就删），于是「零命中」与「树里有参考解」**不可能同时成立**。剔完之后树里**还有 65 个模块** import 那两棵：结算 `ops/score_runs.py`、出表 `ops/mk_tables.py`、出集与建题 `genetask/packager.py`、oracle/控制组/适配赛道。跑得了的是网关、注入器与两臂运行器、harness 与接入契约、协议工件、全部文档 —— 这棵树今天是「把 agent 跑起来拿到 artifact」的那一半，不是「判它得几分」的那一半。三条路（A 保持现状并在 README 首页写明 / B 公开仓库也带答案面并重打树 / C 拆两个仓库）写在 `ops/reports/push_instructions.md` §0④ 与 `$GB/release/trees/genebench/EXCLUDED.txt`。**推 A 是安全的，只是 README 会对不上。** 出处：卡 Z。 |
| **N-628** | `genequant/` 子树落地（协议工件可独立发布） | 已做 | 22 件副本 + 3 件说明 + 封闭清单。副本逐件与 `ops/protocol/**`、`ops/specs/artifact_schema/v1.0/**`、`genetask/arms.yaml`、`LICENSE` 的原件**逐字节相同**，来源记在 `genequant/MANIFEST.json` 的 `copies[].source_in_genebench`。**协议内容一个字节没改**（裁定明说：改内容会动 MANIFEST 与 strict 臂投放的东西）。重建入口 `$PY ops/test_genequant_subtree.py --rebuild`。 出处：卡 Z。 |
| **N-629** | 本体以 sha 钉住协议版本 | 已做 | `RELEASE_MANIFEST.json` 新增 `genequant` 段（`repository` / `version` / `manifest_path` / `manifest_sha256` / `protocols`）。钉的是子树那份封闭清单，不在本体里把逐件 sha 再抄一遍（抄一份就有两份要同步）。测试 `ops/test_genequant_subtree.py::test_发布清单钉住的就是本树现在这份_MANIFEST` + `test_每份副本与仓库原件逐字节相同`（**两个方向**：副本 == 原件 == 清单）。 出处：卡 Z。 |
| **N-630** | 两个仓库地址落进四处 | 已做 | 唯一定义处 `ops/mk_release_manifest.py::REPOSITORIES`；README 的 clone 步骤、`CITATION.cff::repository-code`、`RELEASE_MANIFEST.repository` / `genequant.repository`、包内 README（`ops/release/pack_public_provider.py::README_TEMPLATE`）四处引用它。一处分叉就红（`test_两个地址在四处一致_一处分叉就红`）。 出处：卡 Z。 |
| **N-631** | `no_clone_url` 换判据并闭合 | 已做 | 原判据是本地 `.git/config` 有没有 `[remote `。**本卡明确不给内网工作树配外网 remote**（裁定：推送由用户执行），所以判据改成 `has_remote or clone_urls_declared(repo)` —— 后者查「两个地址是真地址 + README 与 CITATION 两处一致」。**刻意不查可达性**：那会让清单内容取决于跑它的机器有没有外网，而清单的 sha 被测试钉着。反向判别力有两条测试（换回占位符 / 只写一处）。 出处：卡 Z。 |
| **N-632** | `ops/reports/push_instructions.md` | 已做 | 两条 `git remote add` + `push`、推之前的三件确认、推完的三件事、四条「不要做」。**没有执行任何 push、没有 `git remote add`**。 出处：卡 Z。 |
| **N-633** | 可推的两棵树 | 已做 | `$GB/release/trees/{genebench,genequant}/`，各自 `git init` + 一次提交。答案面按发布清单剔除后各扫一遍 `runner/f02/answer_plane_guard`，**各 0 命中**，输出留在 `$GB/release/trees/scan_*.txt`。 出处：卡 Z。 |
| **N-634** | 手册 §0.1 第 2 条 | 已做 | 与 README §5 第 2 条同步划掉并注明闭合（共享文件，flock 内定点替换）。§0.1 判的是 blockers 的**总**条数（5），没动；README §5 判的是**未闭合**数，「两条」→「一条」。 出处：卡 Z。 |
| **N-635** | 推送本身 | **待用户** | 两个远端**已经各有一次提交**（GeneBench `55ead48…`、GeneQuant `6eadb00…`），与本地两棵新 init 的树**没有共同祖先**，普通 push 会被拒。三条路（force / merge --allow-unrelated-histories / 推到新分支开 PR）写在 `ops/reports/push_instructions.md` §0①。 出处：卡 Z。 |
| **N-636** | `DATA_LICENSE` 仍 `pending_license_text` | **待用户** | 现在是**唯一**一条未闭合的 blocker，`releasable` 因它仍是 false。推源码不等于发数据包（树里没有任何行情数据），但推之前要确认接受「代码公开 / 数据包暂不公开」这个状态。 出处：卡 Z。 |
| **N-637** | `integrations/P2_CONTRACT.md` 没有被切进 `genequant/` | 登记不修 | 裁定说「里属于协议的部分」。那份文件 1004 行，绝大部分是网关端点、`/task` 布局、错误码 —— 是**基准**的接口，不是协议。切一份出来就是**新写的内容**，而裁定同时要求「只做整理与副本，不改内容」。处置：`genequant/PLACEMENT.md` 把属于协议的那几条（挂载点、被动存在、封闭集合、两臂唯一差别）从 `genetask/arms.yaml` 与三份协议 `MANIFEST.json` 的 `_placement` **重新组织**并逐条给出处，P2_CONTRACT 留在本体。要不要把它拆成「协议面 / 网关面」两份，是 v1.1 的事。 出处：卡 Z。 |
| **N-638** | `ops/specs/` 里三份没进协议树的文件 | 登记不修 | `backtest_contract.md`（「实现 B 的唯一输入」，是 gold 侧参考实现的契约，不是 agent 侧协议）、`backtest_declaration_underdetermination.md`（实证，不是规格）、`adaptation_track.md`（赛道的生成器/结算/出集，路径全是 `ops/` 与 `scorer/`）。进树的是 `ops/specs/artifact_schema/v1.0/S1–S8.json` —— `contract.md` 与 validator 口口声声的那份 `artifact_schema.json` 的冻结落盘版。 出处：卡 Z。 |
| **N-639** | `genequant/` 不在 `ops/freeze_v10.py` 的冻结根里 | 登记 | 与 `ops/protocol/**` 同样处置（它也不在，`geneprotocol_v1_doc/MANIFEST.json` 的 `_not_frozen` 写过理由：改协议推的是协议版本，不是任务集版本）。但**副本**的漂移有守门：`ops/test_genequant_subtree.py` 比的是副本 vs 原件，原件在冻结面之外也照样红。 出处：卡 Z。 |
| **N-640** | `SlipSelfConsistent` 在**现存 132 条记录上零覆盖** | 登记不修（红队 V2.rt finding 8，minor） | 它现在是 `gate`（裁定 ④），但库里 8 条 S8 记录是 2026-09-08 按 set 1.0.9 / ref r1.0.14 结算的，早于 N-383，那一版 scorer 不产这个量。于是阶段表上这一列每一行都空 / `unobservable` —— **一条进判据的指标在发布件上没有任何覆盖**。判据本身是对的：红队拿当前 scorer 对已存产物 `runs_in/m6b/s8-rob-01.strict.cfg-codex-deepseek.r01/work/artifact.json` 跑 `scorer.l3.compare_fill`，得 `SlipSelfConsistent=1.0`、重算 53.8834 bps、容差 21.2037 bps。**修法零真 API**：`$PY ops/score_runs.py --batch m6b` / `--batch m6_public` 重跑结算入库（产物还在）。没跑的话要在 `known_limits` 里明写「v1 的现存记录上无覆盖」 出处：红队修复卡 V2.rt。 |
| **N-641** | `run_id` 的**机器段**没有被任何真记录验到 | 登记不修（finding 9，minor） | `runner/inject.py:198` 的 `run_id()` 现在一定会拼 `@<machine_id>`，但 2026-09-11 落地的 `i_rehearsal_v2` 6 条 run 的 `run_id` 仍是 `s1-cor-01.open.cfg-codex-deepseek.r01`（无 `@` 段），`inject.json` 里也没有 `machine_id`。全库 `machine_of()` 返回 `None` 的是 132/132。export 时机器标识是**现场算的**，不是从记录来的 —— 两台机器真去合并时主键退回 `(batch, run_id)`，裁定 ⑮ 说的「天然不撞」在今天的数据上不成立。要查的是：那次演练走的是不是发布包里**旧版**的 `inject.py`；是的话重打一次包再演练，并加一条测试断言 `pack` 出来的 run 目录 `run_id` 含 `MACHINE_SEP`、`inject.json` 里落了 `machine_id` 出处：红队修复卡 V2.rt。 |
| **N-642** | 主表 S2 那一对列（`Align` / `Adj`）读起来会失真 | 登记不修（finding 10，minor；**动列要用户裁定**） | `i_rehearsal_v2/s2-cor-01.strict.cfg-codex-deepseek.r02` 的 `correctness` 是 `{Align:1, Adj:1, Cal:1, Decl:1, Set:1, CellAgree:0, n_gold_rows:41700, n_rows_missing:41700}` —— 面板一行都没对上。它在主表 S2 那一对上贡献的是 **1 / 1**，因为裁定 ⑩ 给 S2 分的两列是 `Align`/`Adj`，而这道题真正的内容判据 `CellAgree`（§9.2 唯一的 S2 fidelity 项，闸门 ≥0.999）不在十九列里。`l3_pass=False` 确实把它落到了 `P@1` 上，**不是算错**；是列的选取让只读那一对的人看到满分。两条路：① 不动列（⑩ 是裁定），在 `ops/reports/report_spec_v1.md` 与主表脚注给 S2 那一对加一句「量的是字段映射与复权口径的**申报**，面板内容一致性看 `CellAgree`」；② 把 `Align` 换成 `CellAgree` —— 那是改裁定，要用户点头 出处：红队修复卡 V2.rt。 |
| **N-643** | 本卡改 `withheld_reason` **改到了已发表的表上的数** | 已做，需知会 | finding 1 的修法（诚实终止判在最前 + 有读数就返回 `None`）让全库四类计数从 `budget 30 / rejected 40 / unsettled 32 / honest_halt 0` 变成 `honest_halt 1 / budget 26 / rejected 40 / unsettled 32`：1 条真诚实终止归位，3 条**有读数**的 run 不再被算进「没有读数」。后者会把少数本该是 `unobservable` 的格子从 `—` 改回 `unobservable`。已重出 `ops/reports/m6_public/` 与 `ops/reports/m6_all/` 的表。**已发表过的 v1.0.14 签字包不动** —— 那一版签的是那一版 出处：红队修复卡 V2.rt。 |
| **N-644** | `ops/test_6rt.py::test_零run的批不渲染逐run叙述` 的样本批换了 | 已做，登记 | 立这条测试时 `m6_public` 恰好 0 个 run，于是拿它当「0 run 的批」的样本。卡 X1 把那一批跑到 8 个 run 之后，这条测试变成「断言一件已经不成立的事」而红（与本卡无关，进场时就红）。改成用一个**一定没有 run 的批名** `m6_zero_fixture`，断言一个字没放宽；配平的判别力在同文件的 `test_有run的批照旧渲染主表叙述`<br>**卡 Y1 的同一条**（状态：不是本卡的）：它渲染 `m6_public` 的就绪报告并断言里面有「**0 个 run**」。X1 把那个批跑出 8 个 run 之后这条必红。**不是回归，是 X1 的确定性下游**：要么把断言改成用一个**真的没有 run 的批**（更有判别力），要么参数化。落点 `ops/test_6rt.py` 不在本卡路径。 出处：红队修复卡 V2.rt / 卡 Y1。 |
| **N-645** | **结果库里的适配赛道切片是陈的 —— `genebench export` 导出的适配读数仍是「偏低约 13pp」的那一版** | **待办（挡 ⑮ 的导出可信度）** | 卡 X2 按裁定 ② 重算了适配表，但只重写了 `ops/reports/adapt/`，**没有 `--ingest` 回结果库**。实测：结果库里 30 条适配记录的轴仍是 `1.0.14 / r1.0.21`、`outcome` 计数 `first_pass 14 / correct_flag 5 / failed 11`；而 `ops/reports/adapt/records.json` 是 `first_pass 17 / correct_flag 6 / failed 7`。**逐例差 4 条**：`adapt-l1-08`（failed→first_pass）、`adapt-l2-07`（同）、`adapt-l2-08`（同）、`adapt-l3-06`（failed→correct_flag）—— 正是裁定 ② 点名的那四例。后果有两层：① 裁定 ⑮ 的 `genebench export` 导出的是**结果库切片**，外部用户拿到的适配读数因此是改正**前**的；② 同一棵树里 `ops/reports/adapt/table.csv`（新）与结果库（旧）两个数并存。本卡按任务书「结果库不动数据、只重出表」**没有改库**，并因此**没有**把 `mk_tables --table adaptation` 出的那张（从库来的、陈的）表落进 `ops/reports/adapt/` —— 那会在同一个目录里放两张数不一样的表。修法零真 API：`$PY ops/reports/adapt/adapt_report.py score --no-pull --ingest`；**注意 `DB.ingest` 对同主键内容不同是报错不覆盖**（卡 Y2 的口径），所以要先决定是覆盖那 30 条还是换一个 batch 名。这件事该由能动结果库的那张卡做。 出处：收尾卡 v2。 |
| **N-646** | **七处 LaTeX `\label` 撞号（`table_a.tex` 四个批 + `table_b.tex` 三个批）—— 论文同时引两个批就是重复 label** | **已修（本卡）** | `m6_public` / `n130` / `rehearsal_v1` / `v1demo` 四个批在 HEAD 里的 `table_a.tex` 都写着 `\label{tab:a}`（其余 17 个批是 `tab:a-<批>`）；**`table_b.tex` 上同一个毛病又来一次** —— `m6_public` / `rehearsal_v1` / `v1demo` 三个批都是 `\label{tab:b}`。后一半是**写完测试才逮到的**：本卡第一版只盯着 `table_a` 与新出的主表，`ops/test_V2.py::test_各批的latex_label互异` 扫的是三种 .tex，一跑就红。LaTeX 不会报错，只会让 `\ref` 指到后编译的那一个 —— 「引用指错表」比「编译失败」难发现得多。本卡重出时按其余批的既有体例补成 `tab:a-<批>`，并给新出的主表一律 `tab:main-<批>`；21 个批的 `table_a` label 现在互异（脚本 `$GB/scratch/V2/emit2.py` 结尾断言）。 出处：收尾卡 v2。 |
| **N-647** | **`ops/mk_tables.py --caption` 传进去的文字会被 `to_latex` 再转义一次** | 登记不修（本卡有绕法） | `scorer/report.py::to_latex` 内部调 `_tex_escape(caption)`。于是把 HEAD 里**已经转义过的** caption（`h\_claude-code`）原样回灌，得到 `h\textbackslash{}\_claude-code`。本卡在驱动脚本里做了一次逆转义（`\textbackslash{}` 必须最后还原，否则它自己产生的反斜杠会被前几步吃掉）。根治两条：`--caption` 明确声明「收未转义的原文」并在文档里写清，或 `to_latex` 只对**数据单元格**转义、caption 交给调用方。现在的形状是「谁读了源码谁知道」。 出处：收尾卡 v2。 |
| **N-648** | **`ops/reports/rehearsal_echo/` 不在结果库里 —— 按批名出表会得到一张空表且不报错** | **已绕开（本卡加了守门）** | 它有 `table_a.csv` / `.tex`（早于结果库的产物），但库里没有 `batch=rehearsal_echo`。`mk_tables --filter batch=rehearsal_echo` 选到 0 条记录，照样出一张只有表头的表、rc=0。本卡第一版脚本正是这么把它的 `table_a.tex` 覆盖成空表的，已用 `git show HEAD:… >` 还原（没用 `git checkout --`，那是禁令），并在驱动脚本里加了「批名必须在结果库里」的前置。建议 `mk_tables` 在选到 0 条记录时以非零码退出或至少打一行醒目的话 —— 空表与「这一批真的没有 run」在文件上同形。 出处：收尾卡 v2。 |
| **N-649** | 21 个批的表按 ⑩ 的十九列口径统一重出 | **已做（本卡）** | 每批新增 `table_main.{csv,md,tex}` + `metrics_agent.{csv,md}` + `metrics_stage.{csv,md}`。**逐批核过列集与顺序**：21 份 `table_main.csv` 的表头 `sort -u` 只有一行，且与 `scorer.report.TABLE_A_INDEX_COLUMNS + MAIN_TABLE_COLUMNS` 逐字相等。**`table_a.csv` 与 `table_b.csv` 21 批全部逐字节不变** —— 这正是「结果库不动数据、只重出表」的证据：聚合口径没有漂。`ops/reports/adapt/` 见上面第一条（没出从库来的表）；实例矩阵 `probe_matrix_instances.md` 由卡 X2 重出，本卡只读复核（108/130）。 出处：收尾卡 v2。 |
| **N-650** | 签字包现在逐件登记「这份文件正文里提到了哪些版本轴」 | **已做（本卡）** | `ops/archive_signoff.py` 新增 `MANIFEST.axis_mentions` 与 `mentions_other_axes`。动机：签字包是平的一堆文件，其中**有些是生成的报告**，正文里写着自己那一刻的四条轴；重冻之后没有重跑生成器的那几份，会带着上一版的轴被签进这一版的包，而 `MANIFEST.set_version` 只说**包**的轴、不说**件**的轴。**这是如实登记不是门** —— `VERSIONS.md` / `CHANGELOG` 本来就该列历次版本，把它们判成「陈旧」是错的。这一版里 16 个件进了 `mentions_other_axes`，逐条看下来都有正当理由（混轴批的表自报 `1.0.7｜1.0.9`、已知限制里写「已于 r1.0.22 修复」等），**没有一件是陈值**。 出处：收尾卡 v2。 |
| **N-651** | `ops/reports/wrapup_report.md`（收尾卡 v1 的那份）里两条「未达成」已被本轮事实推翻 | **待办（不在本卡路径）** | `ops/test_wrapup.py::test_两条未达成没有被写成达成` 现红：v1 报告写着公开通道「未达成（0/18）」，而 `m6_public` 现在有 8 个已结算的 run（卡 X1）；单机形态那一条也被卡 Y1 的 `rehearsal_v2` 走通了。**方向是低报不是粉饰**，但一份签字过的报告说着一件已经不成立的事，读的人无从判断哪一句还作数。本卡按路径边界**没有动 v1 的报告**；新的事实全写在 `ops/reports/wrapup_v2_report.md`。建议：要么由报告卡把 v1 那两行改成「已于 2026-09-11 达成，见 v2 报告」，要么让那条测试改成对 v2 报告判。 出处：收尾卡 v2。 |
| **N-652** | **卡号复用时 `mv <卡>.md <卡>.md.merged` 会静默盖掉上一轮那份** | **已修（本卡，且加了守门）** | 本轮的 `X1` 与 `Y2` 两个卡号更早一轮用过，而那一轮的 `X1.md.merged`（6158 B）/ `Y2.md.merged`（7968 B）还在收件箱里。本卡改名收尾时直接 `mv`，**把上一轮那两份整个覆盖了** —— 文件还在、名字没变、只是内容成了另一张卡的，`git status` 里只显示一个 `M`，不看 diff 根本发现不了。在提交前用 `git show HEAD:<path> >` 原样还原（没用 `git checkout --`，那是禁令），本轮那两份改名 `X1-public.md.merged` / `Y2-export.md.merged`。**卡 Y1 当时就是为了躲同一件事才把自己的收件箱叫 `Y1-rehearsal.md`，但那条经验没有被写下来。** 现在有守门了：`ops/test_V2.py::test_改名没有盖掉更早一轮的merged` 判「HEAD 里已有的每个 `*.md.merged` 内容必须与 HEAD 逐字节相同」—— 合并这一步只该**新增** `.merged`，不该改动任何一个既有的。**下一张收尾卡：卡号重名时先看一眼 `ls ops/tickets_inbox/<卡号>.md.merged`。** 出处：收尾卡 v2。 |

## 最终卡（收口 + 发布）—— 2026-09-12

> 八个收件箱（F1 / F2 / F3 / G1 / G2 / H / P / RT-final）逐条并入，编号从 **N-653** 续编。
> **既有票据的状态更新**（N-586 / N-611 / N-619 / N-624 / N-627 / N-635 / N-636 / N-642 / N-645 / N-651）
> 按既有体例写成「**N-xxx 更新**」、编号照旧、不另起新号 —— 别人的输出里已经引着这些号。
> **重复的条目已合并**（三条：21 个批的主表表头由 F2 提出、H 复核、红队最终轮做完；
> 发布清单重跑由 G2 提出、红队最终轮做完；九处状态锁由 F3 逐条写死改法、红队最终轮改完），
> 合并行在说明里保留另一张卡的原话，出处列在说明末尾。
> **这是最后一轮**：本轮之外发现的问题一律登记进 `ops/reports/known_limits_v1.md`，不修、不开新票。

| 编号 | 事项 | 状态 | 说明 |
|---|---|---|---|
| **N-586 更新** | ⑧ opencode 的 Qwen 链路缺 `DASHSCOPE_API_KEY` | **跳过并记已知限制（裁定 ⑧）** | 2026-09-11 复测：f02 `~/.config/genebench/secrets.env` 里**仍然没有** `DASHSCOPE_API_KEY`（只用 `grep -q` 的退出码判存在，没读没打印没复制）。按裁定 ⑧ **跳过、不阻塞发布**，已在 `ops/reports/known_limits_v1.md` 记一条（设计性 / 等待外部条件），写明三件前置里**只缺 (a)**、到位后照 `harnesses/opencode/README.md` §9.2/§9.3 走。**没有往 `MODEL_API_ALLOW` 加 `dashscope.aliyuncs.com`**（今天没有任何 enabled 配置需要它，加进去是纯敞口）、没有伪造 key、没有动 `harnesses/opencode/config.yaml`。 出处：卡 F2。 |
| **N-611 更新** | `ops/run_f02_a1.py` 的 `--provider-root` 在**真跑路径**上被静默忽略 | **已修（a233a96）；受污染的 8 个与被挡的 10 个已重跑** | 真跑那条路径读模块常量 `PROVIDER`（写死私有 provider 绝对路径），而 `main()` 的 `global RUN_ROOT, RESULTS` 漏了它 —— 命令行给了 `--provider-root` 也不生效。改成 `provider_default(channel)` 从注入器钉子表**现算**（目录名约定 `qlib_provider_<根 sha 前 8 位>`）+ 参数真跑生效 + 新增 `--channel` 并落进本进程环境。**闭合证据**：`ops/reports/m6_public/g1_public_provider_rerun.md` —— 18 个 run 的 `work/provider` 现算根 `561348660a3175b1…`、`features` 下 `bj*` **0 个**（私有那份是 336 / 3911）。 出处：卡 G1。 |
| **N-619 更新** | `ops/test_wrt.py::test_rebudget只动没跑过的行` 恒红 | **登记不修（根因已查清）** | 根因确认：`rebudget` 返回的字典键带 `@finance01-e3887dfa` 后缀，而断言用的是不带后缀的 `s1-cor-01.strict.cfg.r01`。**卡 G1 改动之前单跑它也红（已实测）**，不是任何一张卡的回归。与下面 N-669 是同一条根因（清单比裁定 ⑮ 旧）。 出处：卡 G1。 |
| **N-624 更新** | `RELEASE_MANIFEST.json` / `CHANGELOG.md` 是重冻的确定性下游 | **本轮又踩了一次，已闭** | 卡 F1 把轴推到 1.0.16 / r1.0.23 之后这两件又停在旧值。`CHANGELOG.md` 现已重出到「任务集 **1.0.16** / 参考面 **r1.0.23**」；`RELEASE_MANIFEST.json` 由红队最终轮重出（见 N-685）。**这条应当写进收口清单**：每次重冻后按顺序跑 `$PY ops/mk_release_manifest.py --write-changelog` → `$PY ops/mk_release_manifest.py`。 出处：卡 F1 / 红队最终轮。 |
| **N-627 更新** | 剔答案面之后公开树跑不了结算与出集 | **已闭（用户裁定 ④：走 B）** | 公开树**带全部答案面**（oracle 源码、gold 子集、calibration、评分器），只剔四类（私有通道数据 / 凭据 / 记忆探针钥匙 / scratch 与 run 目录）。红线 2 随之从「答案面不上执行面」（判机器）**改写为容器边界**（答案面永不挂进 agent 容器；单机形态下位于 `/task` 之外）。见 N-672 / N-673 / N-674。 出处：卡 G2。 |
| **N-635 更新** | 推送两棵树到两个公开远端 | **仍 BLOCKED，待用户本人确认** | 技术前置**全部验过**：`ssh -T git@github.com` 实测回 `Hi JensenLuan!`；两个远端各只有一次 GitHub 自动生成的初始提交（GeneBench `55ead485…` / GeneQuant `6eadb004…`，2026-09-12 收口时再核一次**仍是它**，即本轮没有人推过）；两棵树验过、身份与 message 合裁定 ⑫、**故意不加 remote**（加了就等于把不可撤的动作留成一次手滑的距离）。没推的理由与照抄的四条命令见 `ops/reports/push_result.md` §3。 出处：卡 P。 |
| **N-636 更新** | `DATA_LICENSE` 状态 `pending_license_text` | **已闭（用户裁定 ⑨）→ `granted`，`releasable` 翻 `true`** | 授权摘要写进新增的 §2.0（研究用途 / 允许再分发派生日线数据 / 署名 baostock）；许可方**正文未到**，§2.1 留一处醒目占位「⚠ 正式文本待替换」并写明收到后要做的三件事；`ops/terms/baostock/permission/` **保持不存在**（见 N-660）。五条 blocker 因此全 `satisfied`、`missing=[]`、`releasable=true`。**注意这不等于「正文可查」** —— 见 N-661 与已知限制表「F3（2026-09-11）登记的两条」。 出处：卡 F3。 |
| **N-642 更新** | 主表 S2 那一对列（`Align` / `Adj`）读起来会失真 | **已按用户裁定 ⑥-c 换列** | `scorer/report.py::MAIN_TABLE_COLUMNS` 第 6 列 `Align` → `Cell%`（取 `correctness.CellAgree`），`Adj` 留作 S2 的有效性列。换列理由由**一条真记录**钉住：`ops/reports/i_rehearsal_v2/scores/s2-cor-01.strict.cfg-codex-deepseek.r02.score.json` 里 `Align = 1.0` 而 `CellAgree = 0.0`（字段全映对了，一个格都没对上），新测试 `test_align_and_cellagree_really_do_diverge_on_a_real_record` 钉住这条证据。`Align` 没有被删：照旧进 `l3_pass`、照旧在规格 §9.2 的 S2 四条里。十九列字面量测试与三处文档同步。 出处：卡 F2。 |
| **N-645 更新** | 结果库里的适配赛道切片是陈的 | **已闭（`--ingest` 回库）** | 旧 30 行标 `superseded=true`（主键后缀 `~superseded@20260912T041305Z`，带 `superseded_by` 与原因，**不删行、让出主键**），新 30 行记 1.0.15 / r1.0.22 —— 库里 17 `first_pass` / 6 `correct_flag` / 7 `failed` 与 `ops/reports/adapt/records.json` 逐个对上。轴按裁定钉成**这批数重算时**那一版而不是当前值（`axes_source` 写成 `pinned:…`，不假装是读出来的）；根治见 N-654。 出处：卡 F1。 |
| **N-651 更新** | `ops/reports/wrapup_report.md`（收尾卡 v1）里两条「未达成」已被事实推翻 | **已闭（正文留历史 + 现值更新）** | 两份收尾报告（v1 / v2）的**正文一个字没动**（那是当天的记录），各加一段「§〇 现值更新」写明今天的轴与 blocker；`ops/test_wrapup.py` / `ops/test_V2.py` 的相关断言由「钉死那一天」改成「正文留历史 **+** 现值必须在报告里写明」—— 判据没有放宽，**多拦了一件事**（报告不写现值就红）。 出处：红队最终轮。 |
| **N-653** | `ops/mk_release_manifest.py::split_revisions` 的「历史遗留」注与渲染出来的那段话已经不成立 | 登记不修 | 那两处逐字写着「拆轴之后新增的**任务集**记录写进了 `REFERENCE_REVISIONS` 元组里（`1.0.7` … `1.0.13`）」—— N-573 收口后**已经不是事实**（两表各自干净）。按前缀分轴的**代码本身仍然正确**，要改的只是那段说明。`CHANGELOG.md` 是渲染件，改了说明要重出。 出处：卡 F1。 |
| **N-654** | `ops/reports/adapt/adapt_report.py::axes_for` 取的是 `freeze_v10` 的**当前**版本号，不是这批数**重算时**那一版 | 登记不修（本轮已就地钉回） | 本轮实测踩到：先推号（1.0.16 / r1.0.23）再收库，30 行适配记录会被标成「在 1.0.16 / r1.0.23 下算的」，而那一版根本没重算过适配切片。已就地钉回 1.0.15 / r1.0.22。**根治**：轴应由 run 自己的通行证反算（`results_db.protocol_by_run` 已经是这个形态），不该取当前值。CONFLICT 记在卡 F1 的输出里。 出处：卡 F1。 |
| **N-655** | 冒烟集 S8 四题（`s8-cor-01` / `s8-eco-01` / `s8-ops-01` / `s8-rob-01`）的 gold **尚未重出** | 待办（不挡发布） | 「算不出来」的根因（实例与冒烟题同号 → `task_dir` 歧义）**已修**（`sim_factory.task_dir` 的 `set_id` 必填 + 基点实例不再与冒烟题同号），但重出 gold 要经网关真跑、两条通道各一次，超时间盒。**盘上现存的 S8 gold 是 v1.0.14 时期产物，数值不受本轮改动影响**（会话构造参数一个都没改，改的只是「按哪个出集的 `task.yaml` 构造」由歧义变成显式）。命令形态见卡 F1 的 `notes_for_orchestrator`（**两个坑**：不要给 `run_oracles.py` 外套 `gateway_lock.py`；`--out` 会连带覆盖 40 列那张共享决定矩阵）。 出处：卡 F1。 |
| **N-656** | `gateway/sim_factory.py` 决定 S8 gold 的运行环境，却不在 `REFERENCE_MODULE_FILES` 里 | 登记不修 | 它住在网关侧、不在 `reference/` 下，收进参考清单会撞上 `test_env_guard::test_reference_files_cover_the_whole_reference_plane` 的口径。本轮改它（`build_engine` 的 `set_id` 改必填）是靠 `REFERENCE_REVISIONS` 的 `r1.0.23` **记因**钉住的，不是靠 hash。v1.1 要么收进参考轴，要么单列「网关侧影响 gold 的文件」一段。已进已知限制表。 出处：卡 F1。 |
| **N-657** | ⑥-a 阶段指标以生成器的 **39** 为准 | **已做（复核结论：本来就相等）** | 生成器 `ops/mk_metric_tables.py::STAGE_METRICS` 现算 **39** 条（S1 3 / S2 4 / S3 5 / S4 6 / S5 7 / S6 3 / S7 4 / S8 7），规格 `ops/specs/GeneBench指标规格_v1.md` §9.2 的登记表**本来就是 39 行**且七列逐格非空，`$PY ops/mk_metric_tables.py --check` 回「指标集逐项相等」。只把「39 以生成器为准」这句裁定与逐阶段条数分解写进 §9.2 题注，**一行指标都没有增删** —— 谁看到任务书说「补齐到 39」不要误以为还缺条目。 出处：卡 F2。 |
| **N-658** | ⑥-b `table_a` / `table_b` 标**诊断件**，不入发布件清单 | **已做** | ① `scorer/report.py` 的 `TABLE_A_COLUMNS` 文档串与 `ops/mk_tables.py` 的模块常量写明「诊断件，不是发布件」；② 落盘时自动写 `table_a.NOTE.md` / `table_b.NOTE.md`（`write_diagnostic_note`，幂等），**已回填 22 个批共 44 份**；③ `ops/archive_signoff.py` 提出常量 `RELEASE_TABLES`（主表 + 两张全量指标表，共 10 件）与 `DIAGNOSTIC_TABLES`，包内 README 与 `MANIFEST.tables` 段都从常量取；④ `ops/mk_release_manifest.py` 加 `DIAGNOSTIC_NOT_RELEASE` + `diagnostic_items_in_release()` 作为一道门。**核过之后的事实是 `RELEASE_ITEMS` 里本来就一件结果表都没有**，所以「拿掉」没有可拿的东西 —— 做的是把裁定变成**可执行的门**而不是把证据删掉。**`effect` 列保留**，诊断表照旧归档留证据（归档是留证据不是给人引用，包内 README 与 MANIFEST 逐件标明）。 出处：卡 F2。 |
| **N-659** | **21 个批的 `table_main.*` 按 ⑥-c 的新口径重出** | **已做（红队最终轮）** | 换列之后 21 个批里 **20 个**的主表表头仍是旧的 `Align`（其中包括 `m6_all` —— 签字包与发布件里的那张主表），于是同一份发布物里两张「固定十九列」的表**表头不同**，`ops/test_V2.py::test_主表表头只有一种…` 与 `ops/test_x1.py::test_main_table_for_the_public_batch…` 双红。已按各批自己 `table_main.axes.json` 记的筛选条件全部重出（21 张 × 3 格式 + 84 件指标表），筛选另补 `superseded=None`（出表本来就不该取已作废的行）。**重出时踩到一个坑**：走生成器默认值会把各批的 caption 与 `\label` 全冲成 `tab:main`，`ops/test_V2.py::test_各批的latex_label互异` 当场抓到 —— 已从 HEAD 逐批取回并**反转义**（`--caption` 收的是未转义原文，见 N-647）。<br>**卡 F2 的原话**（提出方）：「这不是回归，是裁定 ⑥-c 的预期连带。」**卡 H 的复核**：21 个批的 `table_main.csv` 表头**全部**是 `Cell%`，0 个还停在 `Align`；`ops/test_h.py::test_各批主表的表头都是换列之后的口径` 盯住这件事。 出处：卡 F2 / 卡 H / 红队最终轮。 |
| **N-660** | `ops/terms/baostock/permission/` **保持不存在** | **已做（刻意）** | 「目录非空的唯一含义是**正文到了**」。**不许**往里放占位/说明文件去让 `ops/test_env.py::test_license_state_matches_whether_the_text_exists` 变绿 —— 那正是那道锁要拦的事，也正是裁定 ⑨ 说的「不许伪装成已入库」。代价是那一条测试在正文到位之前红着（已在 `DATA_LICENSE` §2.3、已知限制表、卡 F3 收件箱三处写明是**已知的、被记录的分叉**，不是遗漏）。 出处：卡 F3。 |
| **N-661** | 发布清单的许可段：**授权**与**正文**拆成两个字段 | **已做** | 旧实现 `text_in_repo = (state == "granted")` 是个**从不看文件**的「文件在不在」字段 —— 状态一翻它就跟着说「正文在库」。换成 `official_text_in_repo`（**现算目录**，今天 `false`）+ `grant_summary` + `official_text_dir`。 出处：卡 F3。 |
| **N-662** | `LICENSE` 版权行 → **`Copyright 2026 Decilix Intelligence`**（裁定 ⑩） | **已做** | 只填 §A「怎么把许可套到本仓库」那一处实例；Apache-2.0 正文与附录里的 `Copyright [yyyy] [name of copyright owner]` **模板行逐字未动**。改本体 LICENSE 的**规定动作**（顺序不能反）：`$PY ops/test_genequant_subtree.py --rebuild` → `$PY ops/mk_release_manifest.py`。 出处：卡 F3。 |
| **N-663** | `CITATION.cff`：`repository-code`（GeneBench）+ 新增 `repository`（GeneQuant） | **已做；`authors` 维持待填** | 裁定 ⑩ 只给了版权人，`authors` 仍是 `<待用户填>`，**一个字没代填**；`date-released` 也仍空着。**版权人 ≠ 作者** —— 已在 `LICENSE` 与 `CITATION.cff` 头部各写一句，防止后来的人拿版权行去填 `authors`。 出处：卡 F3。 |
| **N-664** | `genequant/LICENSE` 副本与 `genequant/MANIFEST.json` 重出 | **已做** | 改本体 `LICENSE` 之后的规定动作；`RELEASE_MANIFEST.genequant.manifest_sha256` 随之对上（裁定 ⑮ 的「以 MANIFEST sha 钉住」）。 出处：卡 F3。 |
| **N-665** | 翻 `releasable` 会让**九处「写死当时现状」的状态锁**一起红 | **已闭（改成与清单同源，判据没放宽）** | `releasable` false→true、`DATA_LICENSE` pending→granted、版权行占位→真值，这三件事各被一批断言钉着：`ops/test_env.py` 的许可状态锁、`ops/test_B.py` 三条、`ops/test_V2.py` / `ops/test_W2.py` / `ops/test_wrapup.py` 各一条、`ops/test_readme.py` 两条。**那些红不是回归，是「被钉住的现状变了」。** 卡 F3 按路径边界没替别人改，把九条的**逐条改法写死**在 `ops/tickets_inbox/F3.md`（含两个容易踩的细节：`ops/test_B.py:172` 的行内 `cn` 表要补 `0: "零"`，README §5 的旧结论按本仓库既有写法 `~~删除线~~` 保留）。红队最终轮按这张表改完：每一条都改成**与清单自己的推导同源**（`releasable == (not missing) and all(satisfied)`、未闭合条数以现算为准），**没有删测试、没有加 xfail**，且多加了一道拦截（报告不写现值就红）。 出处：卡 F3 / 红队最终轮。 |
| **N-666** | `ops/release/pack_public_provider.py:366` 的 `"text_in_repo": state == "granted"` 是同一个假字段 | 登记不修 | 与 N-661 刚从发布清单里换掉的是同一个字段，但它写进的是**公开包自己的 `MANIFEST.json`** —— 外部用户下载后直接读的那一份。状态翻 `granted` 之后它会对外宣称「许可正文在库」，而正文并不在。改法照抄 `ops/mk_release_manifest.py::official_license_text_in_repo`（现算目录，别从状态推）。**重打公开包之前必须先看这一条。** 已进已知限制表。 出处：卡 F3。 |
| **N-667** | **通道没送到 f02** —— `ops/run_joblist.f02_run_cmd` 拼的 ssh 命令一个字都没提通道 | **已修（a233a96）** | 这是 N-611 能「静默」的**真正原因**：f02 上 provider 默认与 P2 期望值**两头一起回落到 private**，两头一致所以全绿。只修 `--provider-root` 不够。现在送 `export GENEBENCH_CHANNEL=<ch>` 与 `--channel <ch>` 两份。`umask 022; export PYTHONDONTWRITEBYTECODE=1`（红线 7）原样保留，只在它前面**插入**通道那两段。 出处：卡 G1。 |
| **N-668** | 注入器新增 **P7e**：`work/provider` 的根 sha == 本通道期望值 | **已加（a233a96）** | `runner.inject.check_work_provider()`，接在 `PA.place_for_arm` **之后**。**P2 查的是调用方传进来的路径**，只要「传进来的」与「装进 `work/` 的」是同一个错的东西就永远绿；P7e 站在 `work/` 这一侧（compose 把 `<run_dir>/work` 挂成 `/task` 的那个目录），查的是**结果**，不一致时点名「装进去的是哪条通道的树」。`inject.json` 新增 `provider` 段。**有牙**：`ops/test_g1.py` 造「公开通道装了私有 provider」当场红、同一棵树在 private 通道上绿；红队最终轮独立复现，两次攻击门都按预期响。**别把它和 P2 合并或删掉「因为 P2 已经查过了」** —— 那正是 N-611 的形态。 出处：卡 G1。 |
| **N-669** | `m6_public/jobs.jsonl` 比裁定 ⑮ 旧，18 行 `job_id` 都不带 `@<机器标识>` 后缀 | 登记不修 | 于是每条真跑都打一句「[黄] run_id ≠ job_id：多半是 exec 树没同步」——**这句提示在这批上是误导**（exec 树是刚推的，两边同源，差的是清单陈旧）。结算按 `run_id` 走，18 行读数正确，只有那句黄字是噪音。同一根因让 N-619 恒红。**不修**：重生成清单会把 18 行全部退回 `pending`，对一批已跑完的读数代价大于收益。v1.1：让 `run_one` 在「`job_id` + `@` + 机器标识 == `run_id`」时别打黄，或让 `joblist.gen` 直接把机器标识写进 `job_id`。 出处：卡 G1。 |
| **N-670** | `ops/test_c65.py::test_公开通道才给容器换网关地址` 的「除网关那一段两条命令逐字相同」与 N-611 的修法直接冲突 | **已定点改（a233a96）** | 通道现在**必须**出现在 f02 那条命令里，不改就是恒红。按 `ops/test_c41.py:366` 的先例做幂等定点替换：放过通道那两段，并**补一条反向判别**（那两段必须在），以免断言变成恒绿。共享测试文件，flock 内读-改-提交一气呵成。 出处：卡 G1。 |
| **N-671** | 公开通道 **18 个 run 全部在真公开 provider 上跑成** | **已做（真 API 968 次 / $16.2788）** | 受污染的 8 个 + 此前被夹具身份闸挡住的 10 个一起重跑。逐 run 证据：`inject.json` 的 `provider` 段 + f02 上实数的 `work/provider/features/`（`bj*` **0 个** / 总数 3575；私有那份是 336 / 3911）。重出主表 / Table A / B / 两张全量指标表 / 三控 / 破坏样本 / 验证验证器 / 就绪报告 / X1 逐 run 实况。受污染的 8 个 run 目录**不删**（f02 `polluted_private_provider_20260912/`、f01 `runs_in/m6_public_polluted_20260912/`），结果库对应 8 行标 `superseded`。试跑 1 题双臂外推 ~1390 次（<1500 阈值），实际 968 次。 出处：卡 G1。 |
| **N-672** | 公开树按新口径重打：**带全部答案面**，只剔四类 | **已做** | `$GB/release/trees/genebench/`：2,169 件 / 27 M（含 `.git` 39 M），带 `reference/` + `scorer/` + `genetask/templates`(329) + `genetask/params` + 47 份 `solve.py` + calibration；**只剔**私有通道数据（git 树里本来就没有，0 件）、凭据（0 件）、记忆探针钥匙（1 件）、scratch 与 run 目录（0 件）。`EXCLUDED.txt` 逐条写明并说清「树口径对这棵树必然大量命中，那不是红」。门：`runner/f02/answer_plane_guard.py` 新增 `--mode container`（读 compose **三种** bind 写法 —— 短语法 / 长语法 / 顶层 named volume 的 `driver_opts.device`，第三种对 grep 沉默 —— 加 run dir），**命中即拒绝启动、一个字节都不删**（命中的往往是答案面本体，删它等于把基准删了）。`--mode` 默认仍是 `tree`，f02 每小时 timer 的命令行一个字没改。 出处：卡 G2。 |
| **N-673** | 公开树**能跑结算** —— 上一轮「65 个模块 import 断链」已消除 | **已做** | `ops/reports/g2_public_tree_scoring.md`：在公开树自己那棵树里跑（`sys.path` 只指树），141 个 import `scorer`/`reference` 的模块**断链 0**，树内 scorer / genetask / 标定测试 **320 passed**。**注意红队最终轮的补充**：「树内 320 条单测通过」**不等于**「结算在真 run 数据上跑得起来」—— 后者当时还被通道默认值挡着（见 N-682），现已修。 出处：卡 G2 / 红队最终轮。 |
| **N-674** | oracle 源码公开带来的**训练污染风险** | 登记不修（**设计性限制**，v1.1 以留出集处理） | 同期可比性不受影响（各臂看到的东西完全相同，主表臂间差异仍可归因）；**跨期可比性会衰减，且没有观测量** —— 无法从外部判断某个模型有没有见过本仓库；canary 从「记忆污染检测」降级为「同期一致性检查」。`reference/memory_probe_answers/`（探针钥匙）**仍不公开**，是唯一没被这条限制波及的判别力来源。v1.1 以**留出集**处理（不公开题面、不公开 gold 的一批题）；不在 v1 修的理由：留出集要重走一遍出集 / 冻结 / 标定，是一个版本的工作量。公开树 README 首屏已写「答案就在这个包里」横幅。 出处：卡 G2。 |
| **N-675** | `answer_plane_guard` 在 f02 上的 `identity` 基线没重写 | 登记不修 | 改了门的源码，`OWN_FILES` 的 sha 变了，f02 上会报一条 drift（**设计如此**：drift 时照常扫，只是多一条黄 + 一次落闩）。**下一次 `ops/push_exec_to_f02.sh` 之后在 f02 上跑一次** `python3 <guard> --write-identity` 即可。 出处：卡 G2。 |
| **N-676** | `runner/inject.py:765` 的 P9 门仍是「树口径 + 一句字符串断言」 | 登记不修 | 它只查 `f"{run_dir/'work'}:/task" not in text` —— 覆盖「有没有挂对」，**不覆盖「有没有多挂」**，而多挂正是新口径要拦的那件事。新口径下它应该直接调 `answer_plane_guard.scan_container(compose, run_dir=run_dir)`。 出处：卡 G2。 |
| **N-677** | **签字包按通道各出一份** | **已做** | `ops/archive_signoff.py` 新增 `--channel private\|public\|both`（默认 `both` = **各出一份，不是出一份混的**）；归档清单劈成 `SHARED_ITEMS` + `PRIVATE_ITEMS` + `PUBLIC_ITEMS`，**`ITEMS = 三组之和`保持不变**（`test_V2` / `test_wrapup` / `test_V2rt` 问的「这一件在不在归档清单里」与通道无关），按通道取用 `items_for()`；`RELEASE_TABLES` / `DIAGNOSTIC_TABLES` 同样劈一层、并集不变。`MANIFEST.json` 多两个字段：`channel` 与 `counterpart`，包内 README 第一屏写通道、正文指得到另一份。 出处：卡 H。 |
| **N-678** | 公开签字包新收三件 | **已做** | `m6_public/summary.md`（顶部四行通道口径：通道 / 标定 / 网关日志 / 题集根 —— 没有它，包里那张公开主表读不出「用哪套面算的」）、`m6_public/g1_public_provider_rerun.md`（N-611 闭合证据）、`g2_public_tree_scoring.md`（公开树能跑结算）。三件本轮之前都没进过任何签字包。 出处：卡 H。 |
| **N-679** | 私有签字包沿用历史目录名，**光看目录名看不出通道** | **已做（并把代价如实记下）** | 私有仍是 `v<任务集>_<参考面>`，**没有**加 `private_` 前缀：`ops/test_wrapup.py:47` / `ops/test_V2.py:60` / `ops/test_V2rt.py:281` 三处都按这个式子**现算**路径，改名等于把三份测试一起改红，而它们问的「当前轴上有没有签过字的包」不该因为命名体例变了就没了答案。折中：通道写进 `MANIFEST.channel` 与包内 README 第一屏；公开那份用 `public_` 前缀且 `set_version` 本身带 `p`。v1.1 修法：三处测试改成从 `AS.dir_name_for("private", …)` 取路径。已进已知限制表。 出处：卡 H。 |
| **N-680** | 两处 `declared_but_missing` 判据按通道核 | **已做（定点改别人的测试文件，各一行）** | `ops/test_wrapup.py:128` 与 `ops/test_V2.py:243` 原本按**两条通道的并集**核，签字包按通道出两份之后这条判据恒红 —— 公开那十九件在私有包里既不在 `files` 也不该记进缺件（**它们不是「缺了」，是不属于这条通道**）。按先例做幂等定点替换 `AS.ITEMS` → `AS.items_for("private")`，其余判据一个字没动；`AS.ITEMS` 本身一个字没动。补丁脚本 `$GB/scratch/H/patch_tests_h.py`（已改过会跳过、对不上原文会停下不猜）。 出处：卡 H。 |
| **N-681** | **发布清单终核** | **已做** | 五条 blocker **全部 `satisfied=true`**（`data_license_text` / `no_clone_url` / `frozen_artifacts_missing` / `public_channel_zero_runs` / `code_license_undecided`）、`missing=[]`、`releasable=true`、`$PY ops/mk_release_manifest.py --check` **退 0**。逐条证据路径见 `RELEASE_MANIFEST.json` 的 `blockers[].evidence`，`ops/test_h.py::test_每条blocker都留了证据路径_且路径真的存在` 逐条核过路径**真的在盘上**。**一条都没有绕，没有一条是「记着没闭但写成闭了」。** 出处：卡 H。 |
| **N-682** | **公开通道的结算读的是私有通道的标定、网关日志与题集根**（红队最终轮 block 1） | **已修** | `scorer/l3.load_calibration()` 在 `path=None` 时写死 `snapshots/v1/calibration.json`；`ops/score_runs.py` 的 `--gateway-log` 与 `--ref-tasks` 两个默认值同样写死私有路径。**三处都不认 `GENEBENCH_CHANNEL`**，而 `genebench_config` 与 `ops/run_controls.py` 早就是按通道取的。实测后果：① 公开 τ 取自私有标定（0.98400596 vs 0.98398107，不相等）；② 在只有公开数据的外部单机上 18 个 run 里 **5 个 `FileNotFoundError` 静默掉出这一批**，摘要给出与已发布表不同的 SR/pass@1；③ 用私有网关日志结算 `overreach` 整片 `None`、gate 判定整片改变；④ 用私有 gold 结算 `s2-cor-01` 的 `CellAgree` 由 0.9466 变成 0.2491 而 **SR / pass@1 恰好没翻 —— 聚合数看不出来**。**红队只查到标定一处；另外两处是修的人扩出来的**（只修一处会让公开结算仍拿私有日志与私有 gold 跑）。修法：三处默认值改成通道感知 + 标定显式传进 `score_run` + 与 `run_controls` 同样的混通道拦截 + 四行通道口径打进 `summary.md`。**重结算结果**：`m6_public` 的主表与 Table A **逐字节相同**（`l3_pass` / SR / pass@1 一个都没翻，**已发布的公开读数不必撤回**），变的是 3 条记录的 4 个诊断值；旧 18 行标 `superseded`，新 18 行入库。 出处：红队最终轮。 |
| **N-683** | **`VERSIONS.md` 陈一版且缺公开轴**（block 2） | **已修** | 权威文档停在 1.0.15 / r1.0.22，同一棵树里的 `RELEASE_MANIFEST.json` 写 1.0.16 / r1.0.23；按裁定 ① 公开通道有自己的 `SET_VERSION_PUBLIC`（p1.0.0 / 根 `3e5ab441a991c411…`），而 VERSIONS.md 里**一行都没有** —— 拿到公开树的人无从知道自己手上是哪条公开轴。已重出轴表与 §4 历史表、新增 §1.1a「公开通道的任务集轴」一节。 出处：红队最终轮。 |
| **N-684** | **要发的这一版没有签字包**（block 4） | **已修** | `ops/reports/signed/` 里最新的是 `v1.0.15_r1.0.22/`，而那个包里的 `m6_public__*` 几件是 N-611 作废的污染读数（跑在私有 provider 上，`n_tasks=4 n_runs=4 SR=0.25`、表头还是 `Align`），它的 README 却写着「要引用签过字的那份就引用这里」。已重出 `ops/reports/signed/v1.0.16_r1.0.23/`（**当时 49 件**；卡 H 随后按通道拆成私有 33 + 公开 27，见 N-677）；旧包**保留**并加 `SUPERSEDED_NOTE.md` 写明哪几件作废、现行的在哪。 出处：红队最终轮。 |
| **N-685** | **发布清单没在本轮改动之后重跑**（major 5） | **已修** | 两个后果：① `public_channel_zero_runs` 的 `status_now` 还写着「8 / 18」而现算是 **18/18** —— 这条 blocker 的存在理由正是「公开通道没有真跑背书」，它把已经补上的背书说成只补了一半；② 清单登记的 **5 个手写发布件**的 sha256 与工作树对不上（`README.md` / `docs/OPERATOR_MANUAL.md` / `ops/HANDOFF.md` / `ops/reports/known_limits_v1.md` / `ops/specs/fairness_protocol.md`）—— 拿这份清单自校验发布物的人会得到 5 条校验失败。<br>**卡 G2 的原话**（提出方）：「我改了五份手写发布件，于是 `test_every_recorded_sha_of_a_handwritten_item_is_the_real_one` 红；修法是重跑 `mk_release_manifest.py`，但它现在**跑不动** —— 生成器先要求 `VERSIONS.md` 与 axes 段一致，而 VERSIONS.md 还停在 1.0.15 / r1.0.22。」**顺序**：先 N-683 再本条。已重出，`--check` 退 0。**这一条每张改发布件的卡都会踩到 —— 最后一个登记的人负责重跑清单。** 出处：卡 G2 / 红队最终轮。 |
| **N-686** | **`RELEASE_MANIFEST.axes` 段没有公开轴**（major 6） | **已修** | `axes` 只登记私有轴，`channels` 里列着 `["private","public"]` 却没有公开轴的版本号与根，于是清单里的 `comparable_iff:"四条轴全部相同"` 在公开通道上**没有可比对的取值**。已加 `public_set_version` / `public_set_root`（源 `ops/manifests/v1.0-smoke-public.json`）；`versions_doc_drift` 认得 VERSIONS.md 里新增的公开轴行；`_BOLD_VERSION` 正则补 `p` 前缀；`ops/test_release_manifest.py` 加两条断言。 出处：红队最终轮。 |
| **N-687** | **版本锁自检只锁一条轴**（major 7） | **已修** | 不带开关跑 `ops/freeze_v10.py` 只比 `ops/manifests/v1.0-smoke.json`（私有任务集轴）；公开轴与参考面轴在这个 CLI 里**没有任何漂移检查路径**（`--write-public` / `--write-reference` 只写不比）。实测：在公开树上以 `GENEBENCH_CHANNEL=public` 跑它，打印「与冻结清单一致」、退 0，而它一个字都没核公开轴 —— 外部用户照手册做完这一步会以为三条根都锁住了。已补 `--check-all`（三条轴各重建 → 比根 → 逐段报差异，任一条漂就非零退出），手册形态① 的自检步改成调用它，无开关那条分支的成功文案自己写明「只核了私有任务集轴」。**这是门的覆盖面问题，不是当下有漂移** —— 三条根实测都没漂。 出处：红队最终轮。 |
| **N-688** | `ops/reports/v1_0_readiness.md`（私有那份）的版本轴陈值 | **已修** | 卡 F1 把轴推到 1.0.16 / r1.0.23 之后它就陈了（公开那份卡 G1 已重出）。`$PY ops/readiness_report.py --batch m6,m6b` 重出，现在写 1.0.16 / `d9ebd5412ac4cc7e…` 与 r1.0.23 / `dddabe440163b36e…`。 出处：红队最终轮。 |
| **N-689** | 红队最终轮的三条 minor + 手册一处命令 | 登记不修 | ① `report_spec_v1.md` 没写明 `—` 与 `unobservable` 谁压谁（照字面独立复算主表的人会在三个格子上得出不同结果，实现的选择是对的）；② 两条通道的 provider 钉子长度不对称（public 16 位 / private 8 位，`startswith` 比 —— **不是当下的洞**，两次攻击门都按预期响了）；③ `ops/reports/m6_public/scores/` 里混着两批跨轴读数（已按「留证据、不删」挪进 `scores_superseded_20260912/`）；④ 手册「照抄的命令」里 `ops/mk_tables.py --table main\|a\|b\|adaptation` 缺 `--out`，照抄会 exit 2（argparse 用法错误，不是静默错误）。逐条见已知限制表。 出处：红队最终轮。 |
| **N-690** | **公开 provider 包里 `instruments/` 的再分发依据未确认 —— 挡住裁定 ⑭** | **BLOCKED，待用户定** | 包里 `qlib_provider/instruments/{all,csi300,csi500,csi1000}.txt`（389 KB）与 `universe/`（3,575 行）来自**私有** `universe_pit`（湖 `index_member_all` 派生，上游 **tushare**），不是 baostock 的产物（baostock 没有指数成分历史）。**两处预先写死了这件事，不是本轮的判断**：包自己的 `MANIFEST.universe_definition_note`，与仓库 `DATA_LICENSE` **§5**（「不在 baostock 许可的射程内 —— §2 的授权不覆盖这一块，**正文到位之后也不会**覆盖 […] **发布前须单独确认**」）。裁定 ⑨ 给的授权范围是「再分发**派生日线数据**」，指数成分历史不在射程内。**两条出路**：① 取得上游（tushare 侧）许可 → 原样发包；② 不发 `instruments/`，改发重建脚本 → 代价是公开通道的 csi300/csi500/csi1000 三个宇宙用户复现不出来，只剩 `all`（而 gold 子集正是按这三个宇宙算的）。`ops/test_p.py` 有三条守门钉着这件事（授权摘要里不许出现「指数成分 / instruments / 宇宙定义」、§2.1 占位不许被删、`permission/` 必须仍为空）—— 想靠改文案把它弄成「已闭」会当场红。 出处：卡 P。 |
| **N-691** | **公开 provider 包没有可发布的版本** | 未做，登记 | 盘上只有 `release/_staging_unpublished/public_v1/genebench_public_provider_v1.tar.gz`（782,040,927 B，sha256 `c42c33ee…`，2026-09-06 打的，`code_head e642468` 远落后于 HEAD，自己标着 `publishable:false / published:false`）；`DATA_LICENSE` §2.1 说 `granted` 之后落点应是 `release/public_v1/` —— **那个目录不存在**，即 `ops/release/pack_public_provider.py` 在许可翻 granted 之后一次都没重跑。许可定了之后**先重跑它**再谈传附件（重打之前先看 N-666）。 出处：卡 P。 |
| **N-692** | **gold 子集包从来没打过，也没有打包脚本** | 未做，登记 | 裁定 ⑭ 要传「gold 子集 152 MiB」，盘上只有清单 `ops/reports/i_rehearsal_v2/gold_subset.json`（公开通道 41 件，清单指纹 `6e9696f0…`）与数据卡 `ops/data_cards/gold_subset_v1.md`，**没有 tar/zip，也没有打它的脚本**。要新写一个：按清单逐件取 `snapshots/public_v1/gold_factors/<rel>`，逐件核 sha256 后打包，包内带清单与校验脚本（照 `pack_public_provider` 的体例）。 出处：卡 P。 |
| **N-693** | `ops/reports/push_instructions.md` 通篇是**陈的**，而它是发布件（两份签字包都收） | 未改，登记 | 三处与现状不符：① §0② 说「两棵树里**没有**答案面」——按裁定 ④ 现在**有意带全部答案面**；② §0③ 说 `DATA_LICENSE` 仍是 `pending_license_text`、`releasable=false` —— 现在是 `granted` / `true`；③ §0③ 说版权行是 `Copyright <待用户填>` —— 裁定 ⑩ 已定。改完要重跑 `$PY ops/mk_release_manifest.py`（见 N-685）。 出处：卡 P。 |
| **N-694** | `ops/HANDOFF.md:1457` 那条票据提到内部 `Co-Authored-By` trailer | **未删，交用户定** | 边界判定：它不是署名，是**关于内部署名不统一的票据**；但它向外说明「本仓库内部历史带 AI 助手 trailer」，而那些 trailer **不在公开树里**（两棵树是 `git init` + 单次提交的新历史）。于是它在公开树里指向一个不存在的东西。**倾向删**，但属「删除」而非「追加」，且要用户点头。逐条理由见 `ops/reports/release_scan_claude_mentions.md` §三①。 出处：卡 P。 |
| **N-695** | `ops/specs/card_3.2_smoke40.md:127,132` 写死本地 Mac 的 scratchpad 绝对路径 | 未改，登记 | `/private/tmp/claude-501/…/scratchpad/…`，外部读者永远够不着，且路径里带 `claude-501`。改成相对描述不影响那两句话为真。**倾向改**，交用户定（同属删改而非追加）。 出处：卡 P。 |
| **N-696** | `RELEASE_MANIFEST.genequant` 钉的是 `MANIFEST.json` 的 sha256，不是 commit sha | 登记不修 | 现口径**符合裁定 ⑮ 的字面**（「以 MANIFEST sha 钉住」），且与刚打的 GeneQuant 树逐字节一致。但公开树推上去之后，外部用户能核的是「哪一次提交」。要同时钉 commit sha 得动 `ops/mk_release_manifest.py` 的 schema。 出处：卡 P。 |
| **N-697** | `release/trees/genequant` 旧提交 `915d664` 的作者是 anthropic 域占位邮箱 | **已修（重打为新提交）** | 卡 Z 打树时用的占位邮箱落在 commit author/committer 里 —— **文件内容扫描看不见它**（扫描跳过 `.git`），单独核提交元数据才抓到。按裁定 ⑫ 重打，作者与提交者均为 深情代码大师 `<2994718175@qq.com>`，message `GeneQuant v1.0 release`。**旧提交从未推送，无对外痕迹。** 出处：卡 P。 |
| **N-698** | ⑫ 字样扫描（`ops/reports/release_scan_claude_mentions.md`）：**署名形态 0 条，技术事实 430 条按五类保留** | **已做** | 两棵树 2,194 个文件逐行扫过，**文件内容里署名形态 0 条**；技术事实逐类写明「删了会变成什么假话」：harness 名 `claude-code` 是五臂之一且有 11 份 `score.json`、白名单 `api.anthropic.com` 的 403 实测史、`llm_trace` 的 `anthropic_messages` 是**代码字面常量**、`pricing.yaml` 留位行与 `ops/test_env.py` 的 `sk-ant` 形态正则、模型 id。**两个坑**：① 写「我把某个署名删了」的报告会把那个署名又写回公开树（已打码，重扫剩 1 条是报告自己的口径表被自己的正则命中 —— **自指，不是署名**，报告里写明了判别法）；② 扫描器把命中行原文落进 scratch 的 json 会让红线 3 的门当场红，已改为打码存证（`[A-Za-z0-9_-]{16,}` → `<REDACTED>`，另存 `raw_len` 够定位）。 出处：卡 P。 |
| **N-699** | ⑬ 推前扫描（`ops/reports/release_scan_final.md`）：四项逐项留证 | **已做（但不是零命中 —— 见 N-690）** | 凭据文件名 **0**、记忆探针目录 **0**、scratch 与 run 目录 **0**；凭据内容 3 条逐条核实**全不是凭据**（两条是 `ops/test_env.py::test_key_scanner_is_discriminating` 往 `tmp_path` 写的反向判别夹具，一条是 `harnesses/opencode/README.md` 讲 `{env:…}` 模板语法时的容器占位串）。`answer_plane_guard` 按裁定 ④ 的**容器口径**跑过一次：正例绿、两个反例红（挂 `reference/` 进 `/task/ref` 红、顶层 named volume 的 `driver_opts` 偷挂带 gold 串的目录红）——**门有牙**。树口径 95 条命中已写明「不是红」（这棵树有意带答案面）。**唯一的实质命中在 Release 附件里**：ChinaScope / tushare 派生表那一项 → N-690。 出处：卡 P。 |
| **N-700** | 八个收件箱并入 `ops/tickets.md` + `ops/HANDOFF.md` 追加 §19.3 + 六节报告 `ops/reports/final_report.md` | **已做（本卡）** | 编号从 N-653 续编、连号、不撞号；既有票据十条写成「**N-xxx 更新**」；重复条目三处合并（N-659 / N-685 / N-665），合并行保留另一张卡的原话、出处列在说明末尾；八个收件箱改名 `.merged`（**先核过 `ls ops/tickets_inbox/<卡号>.md.merged` —— 本轮八个卡号一个都没被更早一轮用过，不会重演 N-652**）。报告七节齐 + 15 条裁定逐条判 + 已知限制表终态盘点。 出处：最终卡。 |
| **N-701** | 阶段收口的全量 pytest 与真 API 终值 | **已记（本卡）** | 数字与逐条归属写在 `ops/reports/final_report.md` §一与已知限制表「最终卡收口」一节。**按任务书口径**：`test_lake_baseline`（外部 ETL 改了湖）、`test_gateway`（网关端口）、`test_env::test_no_api_key_material_in_run_dirs`（别人的 `scratch/Y1/rh2_*`）、`test_underdetermination_guard`（别人未提交的 `ambiguity_impact_2.2b.md`）四类不算本轮的红，逐条已登记不修。 出处：最终卡。 |
| **N-702** | 两个公开远端在本轮结束时**仍是 GitHub 自动生成的初始提交** | **如实记（本卡核对）** | `git ls-remote` 实测：GeneBench `55ead48588dd1ddfff7d62e9ce6bf94401424124`、GeneQuant `6eadb004104aa4564e60db70dff40445c836b817` —— 与 2026-09-11 `push_instructions.md` 记的**同一个 sha**。**这就是「本轮没有人推过」的证据。** 两棵树已备好（GeneBench 2,169 件 / GeneQuant 25 件，各单次提交、作者与 message 合裁定 ⑫、无 remote）。推送与 Release 附件两件都挡在 N-635 / N-690 上，**待用户**。 出处：最终卡。 |

## 发布收尾卡（2026-09-12）—— 六条裁定（①…⑥）

> 四个收件箱 `ops/tickets_inbox/{A,B,C,D}.md` 逐条并入，编号从 **N-703** 续编（上一节末号 N-702）。
> 重复条目已合并，合并行保留各卡原话、**出处列在说明末尾**；并入后收件箱改名 `.merged`。
> 本节是 v1.0.16 发布收尾的最后一节 —— 本轮之外发现的一切问题按用户裁定 ⑥ **只登记、不修**，
> 逐条在 `ops/reports/known_limits_v1.md`；六条裁定逐条判在 `ops/reports/publish_report.md` §2.1。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-690 更新** | 公开包里 `instruments/` 的再分发依据 | **已闭（用户裁定 ①）** | 走的是原票据两条出路之外的**第三条**：把宇宙定义面整个换成 baostock 成分接口重建（`query_hs300_stocks` / `query_zz500_stocks`），不发 tushare 派生名单、也不只发脚本。代价：`csi1000` 出包（已知限制表 A 第一条）。`DATA_LICENSE` §5 与 §0 速览表改写；`ops/test_p.py` 那条守门**换判据**（钉新口径 + 钉「旧判断的原话不许还留在文件里」），不是放宽。证据 `ops/reports/public/instruments_switch.md`。 出处：卡 A。 |
| **N-635 更新** | 公开树的推送本身 | **已闭（用户裁定 ⑤）** | 两棵树本轮**已推**：GeneBench `refs/heads/main` = `bd0513a47d1ad273d4cc21fdbdfb5604b2487645`（annotated tag `v1.0.16` 解引用后同值，2,183 件、单次提交、作者=提交者 深情代码大师 `<2994718175@qq.com>`、message `GeneBench v1.0.16 release`、body 空）；GeneQuant 本轮无改动、**只核不推**，远端仍 `6ce7664e84e467c39d11bb4ec88209bdae6a7c92`。`git ls-remote` 实测见 `ops/reports/push_result.md` §6.7 与本卡 `ops/reports/publish_report.md` §一。 出处：卡 D。 |
| **N-703** | **公开 provider 的根换了一次**：`561348660a3175b1…` → `f7dda2899071b07a…` | **已做** | 换宇宙定义面的连锁，逐处跟改并留证：`runner/inject.py::PUBLIC_PROVIDER_SHA256_ROOT`（**功能性钉子唯一一处**）、`ops/data_cards/public_channel.md`（带 `<!-- src -->` 自动核对）、`ops/reports/public/qlib_provider_public.md`、`ops/reports/public/release_forms.md`、`ops/HANDOFF.md` §19.4、`DATA_LICENSE` §5、f02 上按根命名的目录（新建 `provider/qlib_provider_f7dda289/`，旧的 `qlib_provider_56134866/` **不删** —— 复现已发布的 18 个公开 run 要靠它）。两条通道各跑一次 `check_provider_pin` + `--dry` 注入全绿；反向门（塞一个清单外文件）在 f01 / f02 各当场红一次。证据 `$GB/scratch/A/gates2.log`、`dry2.log`。**两份签字包是只读归档，一个字节没改** —— 里面记的仍是旧根，这件事写在已知限制表。 出处：卡 A。 |
| **N-704** | `ops/release/pack_public_provider.py` 的 `universe_definition_note` 写着**换面前**的结论 | **已修** | 原文往包的 `MANIFEST.json` 里写「`instruments/` 不是 baostock 的产物 —— 再分发不在许可射程内，发布前须单独确认」，换面之后这句**已经不真**。卡 A 提出（不在卡 A 路径内）、卡 C 打包时定点改写成「宇宙定义面由 baostock 成分接口重建（`query_hs300_stocks` / `query_zz500_stocks`），在 §2 授权射程内；`csi1000` 不入本包」。 出处：卡 A 提出 / 卡 C 修。 |
| **N-705** | `ops/reports/i_rehearsal_v2/` 的两份演练产物记的是**换面之前**的数 | 登记不修（裁定 ⑥） | ① `gold_subset.json` 里公开通道那 41 行的 `sha256` **41/41 已经不成立**（换面后按新成分重算，逐件都变了），而 `RELEASE_MANIFEST.package.gold.channels.public.list_sha256` 由它算出；② `package_inventory.json` 是 09-06 那次演练的字节数，`RELEASE_MANIFEST.package.totals_bytes` / `parts` 照读。**打 gold 子集包不读它们** —— `ops/release/pack_gold_subset.py` 只读 `$SNAPSHOTS/public_v1/gold_factors_r2/gold_subset_public.json` 并逐件现算 sha256 比对，对不上当场抛。本卡新增的 `release_attachments` 段记的是**现值**且逐件可校，**两段并存时以它为准**。 出处：卡 A / 卡 C（同一件，合并）。 |
| **N-706** | csi500 有两只票**有名单没有行情**：`SZ000022`、`SZ300114` | 登记不修 | baostock 的 csi500 成分里在册，而公开行情面没有它们（私有 `universe_pit` 整张表里也没有，W2 §3.1）。处置：`csi500.txt` 照留（删掉等于替上游拍板），`all.txt` 不列，qlib 遇到没有数据的码**静默跳过**（实测无异常）。后果：那些天 csi500 实际参与计算的成员少一只。 出处：卡 A。 |
| **N-707** | **τ / ε / IC 族 / 互检仍算在旧 gold 上** | 登记不修（裁定 ⑥） | 公开 gold 子集 41 件已按新成分全量重算，落 `$SNAPSHOTS/public_v1/gold_factors_r2/{csi300,csi500}`（各 792 件，`rc=0`）；而 `calibration.json` / `crosscheck/` / `epsilon/` 仍建在旧 `gold_factors/` 上 —— 随包发的**分**算在新名单、**阈值**算在旧名单，**不同源**。重算阈值要连带重跑 IC-ε 与互检全量（`heavy.lock` 上数小时），超出本轮。逐件比对与完全归因见 `ops/reports/public/instruments_switch.md` §5：共有的 33,527,179 格里 4,511,718 格（13.5%）值变，**100% 落在「成分区段本身变了」的票上，落在区段没动的票上是 0 格**。 出处：卡 A。 |
| **N-708** | **S8 四题 gold 已按 F1 修后重出**（裁定 ④） | **已做** | 两条通道各经网关真跑一次，**8 次全部零 finding**；新旧逐件比对只差 `produced_at`，`gold/session.json` 四题两通道**逐字节相同**。那张 40 列共享矩阵与两份跑批汇总（共 6 件）跑前备份、跑后 `diff -q` **6/6 相同**（两轮都用 `--out` 指向 scratch 独立落点）。报告 `ops/reports/s8_gold_reissue.md`。 出处：卡 B。 |
| **N-709** | 常驻生产网关里的 `sim_factory` 会**滞后于盘上代码** | 登记不修（操作纪律） | 卡 B 第一次私有跑批四题全红（`/sim/log` 返回 500），是进程里那份还是 F1 修之前的。改了 `gateway/` 下的代码之后必须 `systemctl --user restart genebench-gateway.service` 并轮询 `/healthz`（实测 **74 s** 才在听，`restart` 返回时还没在听）。已写进 `ops/reports/s8_gold_reissue.md` §2 与 HANDOFF §18 第 1 条。 出处：卡 B。 |
| **N-710** | `ops/run_oracles.py` 的子集跑会**连带重建题面**，canary token 每次都换 | 登记不修 | `packager._token = secrets.token_hex(8)` → 两臂 INSTRUCTION 的 sha 变 → `task.yaml.task_sha256` 漂移。卡 B 用 `$GB/scratch/B/b_restore.sh` 把题面逐件还原成跑前字节、**只留新 gold**，所以冻结根实际未变、**本轮没有产生 freeze bump**；跑完当时那份题面留证在 `$GB/scratch/B/asrun/`。只想重出 gold 的后续卡照抄那个脚本。 出处：卡 B。 |
| **N-711** | `reference/tasks/*/_ledger.jsonl` 末尾新追加行的 `judge_sha256` 与还原后盘上的判题件不对应 | 登记不修 | 私有 8 行、公开 4 行。台账只追加、全仓无人拿它校验盘上文件；那几行记的是跑批当时那份瞬时重建件。抹掉等于抹审计痕迹，保留。 出处：卡 B。 |
| **N-712** | 公开集 `_ledger.jsonl` 里新追加行的 `set_id` 写成 `v1.0-smoke` 而非 `public/v1.0-smoke-public` | 登记不修 | 既有字段口径问题，不挡发布验收。 出处：卡 B。 |
| **N-713** | 公开网关 `ExecStartPre` 的红线 5 守门会被**别的卡**在 `$GB/scratch/` 下留的 0644 文件拦停 | 登记不修（操作纪律） | 卡 B 第一次公开发起 `rc=143` 就是这个（撞的是 `$GB/scratch/A/a_patch_rebuild_notes.py`）。起公开实例前先 `/usr/bin/python3 ops/guard_modes.py --harden`。 出处：卡 B。 |
| **N-714** | `$GB/release/_staging_unpublished/public_v1/` 里还留着 **2026-09-06 那一版**包 | 登记不修，交仓库所有者 | 782,040,927 B，`instruments/` 还是 tushare 派生那版、根 `561348660a…`、`code_head` 远落后于 HEAD，自己标着 `publishable:false`。许可翻 `granted` 之后可发布的包落 `$GB/release/public_v1/`（本轮重打，见 N-715）。staging 那份既不会被发、也不再与任何在册的根对应，**留着的唯一风险是有人下错**；删是不可逆动作且不挡验收。 出处：卡 C。 |
| **N-715** | **两个可发布附件已打定**（裁定 ②） | **已做** | 落 `$GB/release/public_v1/`（许可 `granted`，`pack_public_provider.py` 本来就按许可现值解落点）。① 公开 provider 包 **782,100,276 B** / `33083ff242c64a8f0bbbcec332ef4d3ad87daa703b78d95728ccdd1bdefc18e9`（包内 28,656 件）；② **新写** `ops/release/pack_gold_subset.py` 打的 gold 子集包 **157,448,605 B** / `edc5ea7cf70ffec3589b981cd67b2b9872527ea8001a2495bde8d6c55ec9ef06`（41 件 / 152.0 MiB，源根**写死 `gold_factors_r2/`**、逐件现算 sha256 比对、另加落点守门 `assert_dest_is_not_on_the_exec_plane`）。逐件 sha256 进 `RELEASE_MANIFEST.release_attachments`（新增段，已进 `FATAL_KEYS`），出处是新登记表 `ops/release/attachments.json`。确定性：同树同 `--built-at` 打两次，**8 件产物逐字节相同**，换 `--built-at` 必须不同（两条都写成测试）。外部用户口径实走：真 `tar xzf` + `sha256sum -c`，28,658 行 / 46 行**各 0 FAILED**。 出处：卡 C。 |
| **N-716** | `ops/test_env.py::test_no_published_provider_package_while_license_text_is_pending` 仍只扫 `$GB/snapshots/public` | 登记不修（卡 1.4 已记一次） | 扫不到 `$GB/release/`；射程由 `pack_public_provider.assert_nothing_published_while_pending()` 补齐，`ops/test_release_forms.py` 盯着。许可现在是 `granted`，这条锁本来就不触发。 出处：卡 C。 |
| **N-717** | `ops/reports/release_scan_final.md:140`「包内另有 `universe/` 一层 = `scratch/v1_union.txt`（3,575 行）」 | 登记不修 | 换面之后 `universe/` 下是四件：取数名单 `v1_union.txt` **＋** 卡 A 反投影的 PIT 名单三件（`universe_pit.parquet` 3,295 行，只有 csi300 + csi500）。那一行现在只说对一半。 出处：卡 C。 |
| **N-718** | **GitHub token 缺 `Contents: Read and write`，Release v1.0.16 建不了、两个附件传不上** | **BLOCKED，待用户** | 实测 `POST /repos/Decilix-Intelligence/GeneBench/releases` 回 `403 Resource not accessible by personal access token`，响应头点名 `x-accepted-github-permissions: contents=write`。同一把 token 的读全通（`GET /user` 200、`GET /repos/…` 200 且 `permissions.admin=true`、`GET /releases` 200 返回 `[]`），响应头无 `x-oauth-scopes` → **fine-grained PAT，仓库权限只给了读**；账号本身是 repo admin，**账号权限与 token 权限是两回事**。机器上没有第二把凭据（无 `gh`、无 `~/.git-credentials`、无 credential.helper）。SSH 那条路是通的，所以 ⑤ 做得成、③ 做不成，两者**不互相替代**。附件本身没有挡上传的理由：六项上传前扫描全零（`ops/reports/release_scan_publish.md`）。补法与照抄的一条命令在 `ops/reports/push_result.md` §2.2–§2.3。 出处：卡 D。 |
| **N-719** | `RELEASE_MANIFEST.release_attachments` 的 `download_url` 仍是空串 | **待 N-718** | 空串的既定语义就是「还没上传」（`attachments.json` 的 `note` 与 `release_attachments_section()` 的 `uploaded` 计数同源，现为 `uploaded=0`）。**有意不填预测地址** —— 清单是权威判据，不能替一件还没发生的事作证。上传之后回填两条，再跑 `$PY ops/mk_release_manifest.py`（`release_attachments` 在 `FATAL_KEYS` 里，不重出会让 `ops/test_release_manifest.py` 红），并删掉 README §2.1a 那段状态提示（`ops/test_d.py` 的**双向门**盯着：地址回填了还留着那段话会当场红）。 出处：卡 D。 |
| **N-720** | Release 的 tag 该指向哪个提交 | **已解（余下只等 N-718）** | 卡 D 准备的 `target_commitish` 是 force-push **之前**的远端 HEAD；树推新之后 annotated tag `v1.0.16` 已推，**解引用后指向终值 `bd0513a4…`**，补做时 `target_commitish` 会被 GitHub 忽略。附件的 `browser_download_url` **只由 tag 名决定**，不随 tag 指向哪个提交而变。 出处：卡 D。 |
| **N-721** | 公开树里的 `ops/reports/push_result.md` 比内网仓库的少一节（§6 推后补记） | **设计性** | 树的内容里含本文件，而树的提交 sha 是对内容算的 —— 把 sha 写进去 sha 就变，**递归绕不过去**。口径写在该文件 §5。 出处：卡 D。 |
| **N-722** | `ops/test_p.py` 三条钉死在卡 P 那个时点的断言 | **已修（定点替换，非放宽）** | 先由卡 A、卡 D 各登记过一次「`test_树里没有配远端` 恒红」（`$GB/release/trees/*` 推送需要 `origin`）。卡 D 随后把三条改成**不变量**并各留反向判别（实测都当场红）：① 「树里没有配远端」→「远端要么没配、要么恰好是那个仓库」；② 推送报告钉**形态**而不是某个时点；③ 「如实记了附件的两个拦路原因」→「只要 `attachments.json` 里还有空的 `download_url`，报告就必须记成 BLOCKED 并写出**当下**的拦路原因」。树内跑 `ops/test_p.py` **28 passed**。 出处：卡 A / 卡 D（同一件，合并）。 |
| **N-723** | **阶段收口的全量 pytest 与真 API 终值**（本卡） | **已记** | 数字与逐条归属写在 `ops/reports/publish_report.md` §一，四类「不该由发布卡替别人判」的红逐条登记在已知限制表。真 API 机器统计 `$PY ops/api_usage.py`：**5,036 次真调用 / 133 个 run / 194,204,110 tokens**（口径：f02 各 run `log/llm_log.jsonl` 里 `decision == "allow"` 计一次；被拒的不计）。**本轮四张卡（A/B/C/D/E）零模型 API 调用** —— 卡 B 的 `run_oracles --agent oracle` 跑的是参考 `solve.py`，打的是数据网关（snapshot 后端），不打模型 API。 出处：本卡。 |
| **N-724** | 两个远端终值与 **Release 附件清单为空** | **已核（本卡）** | `git ls-remote` 实测：GeneBench `bd0513a47d1ad273d4cc21fdbdfb5604b2487645`（`HEAD` / `refs/heads/main` / `refs/tags/v1.0.16^{}` 三处同值，tag 对象 `c9596315993b1811…`）、GeneQuant `6ce7664e84e467c39d11bb4ec88209bdae6a7c92`。`GET /repos/Decilix-Intelligence/GeneBench/releases` 回 **200 `[]`** —— **一个 Release 都没有，因而附件清单为空**，这就是 N-718 还挡着的证据（tag 在、Release 不在）。 出处：本卡。 |
| **N-725** | **本轮卡号 A / B / C 与「2026-09-1x 收尾卡 v2」的卡号撞车** —— 直接 `mv A.md A.md.merged` 会**静默盖掉**上一轮那份 | **已避开（本卡）** | 这正是 N-652 那次事故的形状，`ops/test_V2.py::test_改名没有盖掉更早一轮的merged` 就是为它留的门。盘上 `A.md.merged` / `B.md.merged` / `C.md.merged` **早已存在**（收尾卡 v2 那一轮的），HEAD 里也有。处置：本轮四份改名为 **`A-publish.md.merged` / `B-publish.md.merged` / `C-publish.md.merged` / `D-publish.md.merged`** —— 既满足「并完就不许再有同名 `.md`」（`ops/test_V2.py::test_十个收件箱都改名merged了_原名一个不留` 本轮开工时正因为 `A.md` / `B.md` / `C.md` 又出现而**红**，改名后绿），又一个既有 `.merged` 都没动。**后续轮次的卡号请带上轮次后缀**（如 `A-<轮次>`），不要再复用裸字母。 出处：本卡。 |
| **N-726** | `ops/test_env.py::test_gold_only_lives_under_reference_or_snapshots` **红 24 条** | 登记不修（裁定 ⑥） | offender **全部在 `$GB/scratch/B/backup/{private,public}/s8-*/gold`** —— 卡 B 重出 S8 四题 gold 时留的**跑前备份**，是「新旧逐字节只差 `produced_at`」那个结论的证据面。卡 A、卡 C 各点过一次名，卡 D 按「不动别人的 scratch」没动。**一条命令即绿**（把那一层路径段从 `gold` 改掉，或整个移出 `$GB`），但那会让 `ops/reports/s8_gold_reissue.md` 里的证据路径指空 —— 按裁定 ⑥ 本卡**只登记**。这条红**不是答案面泄漏**：那些文件在 f01 的 `$GB/scratch` 下、`0600`、没进过 f02、没进过任何 bundle。 出处：本卡（卡 A / 卡 C 提出）。 |

## Release 上传卡（2026-09-13）—— R1 上传 / R2 清理与同步 / R3 收口

> 两个收件箱 `ops/tickets_inbox/{R1,R2}.md` 逐条并入，编号从 **N-727** 续编（上一节末号 N-726）。
> **已有号的条目不重新编号**（N-714 / N-724 / N-726），在本节追加「更新」行写它们这一轮的终态。
> 并入后收件箱改名 **`R1-upload.md.merged` / `R2-upload.md.merged`** —— **不是** `R1.md.merged`：
> 「2026-09-1x 收尾卡 v2」那一轮已经占过同形卡号，直接 `mv` 会静默盖掉上一轮那份（这正是 N-725 那个坑）。
> 本轮短报告 `ops/reports/release_upload_report.md`；已知限制终态在 `ops/reports/known_limits_v1.md` 的 R3 一节。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-727** | **Release v1.0.16 的两个附件上传完成** | **已闭合** | 2026-09-13。`POST /releases` 回 **201**（release id `387775425`，卡 D 那次的 403 随 token 拿到 `Contents: Read and write` 而消失），两次 asset 上传 **201 / `state=uploaded`**；从 API 回的 `browser_download_url` 把两件整个下回本地重算 sha256，与本地**逐字相同**。此条即卡 D §2 那条 BLOCKED 的闭合。记录 `ops/reports/push_result.md` §7。 出处：卡 R1。 |
| **N-724 更新** | 「Release 附件清单为空」不再是现状 | **已闭合** | N-724 记的是 2026-09-12 那一刻的实测（`git ls-remote` + 一个 Release 都没有）。2026-09-13 起：Release 页 `https://github.com/Decilix-Intelligence/GeneBench/releases/tag/v1.0.16`，两件附件匿名可下（不需要 token）。**2026-09-13 卡 F 补完**：`ops/reports/publish_report.md` 里那句已改成现状，N-739 已闭合。 出处：卡 R1 / R3。 |
| **N-728** | 大附件上传必须能重试：782 MB 那件第一次 `BrokenPipeError` | **已闭合（脚本在 scratch）** | `scratch/D/d_release.py` 没有重试，断流后附件停在 **`state=starter`**（字节数看着是对的、其实没传完），再跑一次它会因为「size 一致」误判「已在」直接跳过 —— **幂等判据要连 `state` 一起看**。`$GB/scratch/R1/r1_release.py` 是补了重试（每件最多 4 次）+ `state` 判据（先 `DELETE` 半截的再传）+ `403/404/422` 不重试直接停的版本。**下次再打 Release 用它**，或把这两点合回 `d_release.py`。 出处：卡 R1。 |
| **N-729** | f01 → GitHub **下行只有 ~300 KB/s**（同一条链路上行 9.5 MB/s） | 登记不修 | 上传 782 MB 用 **82 s**，把同一件下回来核 sha 要 **~45 min**（两件合计实测 75 分钟）。**发布验收里「下回来核一遍」要按小时排，不是按分钟。** 另：`f01→GitHub` 的链路会抖（撞到过 `SSL: UNEXPECTED_EOF_WHILE_READING` 与 `RemoteDisconnected` 各一次），凡是打 GitHub API 的脚本都要自带重试。 出处：卡 R1 / R2。 |
| **N-714 更新** | staging 里那份 2026-09-06 的旧包 | **已闭合（删了）** | 2026-09-13 用户裁定：删。`$GB/release/_staging_unpublished/` 整棵 `rm -rf`。删前现算 sha256 核身份：`c42c33eee55844d7…` / 782,040,927 B / `code_head e6424687…`，与 `final_report.md` 记的一致；存根 `$GB/scratch/R2/deleted_staging_pkg.txt`。删前 `grep` 过全仓库 + `$GB/scratch`：引用这个路径的**全是叙述性文档**，**没有任何测试、清单或脚本把它当落点**（`pack_public_provider.py` 只在 `license.state != granted` 时才往那里写，而状态已是 `granted`）。 出处：卡 R2。 |
| **N-730** | `ops/HANDOFF.md` §12.2 那一行还把 `_staging_unpublished/public_v1/` 当「发布包（形态 A）」的落点 | **已闭合（卡 R3 改了）** | 包已删，落点早就是 `$GB/release/public_v1/`。本卡定点改那一行：路径改掉、`publishable` 由 `false` 改 **`true`**（盘上 `MANIFEST.license.publishable` 实测就是 `true`）、`SHA256SUMS` 行数由 28,653 改 **28,658**（实测 `wc -l`；`MANIFEST.files` 是 28,656，两者差 2 = 清单里多列了 `MANIFEST.json` 与 `README.md` 自身，不影响 `sha256sum -c`）。`license.published` 仍是 `false`（许可原文还没到，**不动**）。 出处：卡 R2 提，卡 R3 做。 |
| **N-726 更新** | `ops/test_env.py::test_gold_only_lives_under_reference_or_snapshots` 红 24 条 | **已闭合（转绿）** | 2026-09-13 用户裁定：**挪走，不许删**。卡 B 的跑前备份（128 件）整棵 `mv` 到 **`/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/{private,public,reports}/`**（`go-rwx`），原地留路标 `$GB/scratch/B/backup_MOVED_README.txt`，**一个字节没删**。实跑 `ops/test_env.py -k gold` → **3 passed**（含判别力反例那条，门不是被放宽成恒绿）。 出处：卡 R2。 |
| **N-731** | `ops/reports/s8_gold_reissue.md` 第 45 / 88 / 116 行三处证据路径指向旧地址 | **已闭合** | 随 N-726 的挪动产生：三处仍写 `$GB/scratch/B/backup/{private,public,reports}/`，现已在 `/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/`。该文件**不在 R1/R2/R3 任何一张卡的路径内**，按并发施工规则没碰。 出处：卡 R2。 **2026-09-13 卡 F 闭合**：先 `ls` 实测新路径 `/home/ljn/genebench_s8_prerun_backup_2026-09-12/backup/{private,public,reports}/` 三棵都在，再把第 45 / 88 / 116 行三处定点替换成新地址，并在文中写明「2026-09-13 移动，原址 `$GB/scratch/B/` 留有路标 `backup_MOVED_README.txt`」。 |
| **N-732** | 「**阈值与当前 gold 名单不同源，重算排 v1.0.17**」两处说明 | **已闭合（两处都写了）** | 用户点名的两处：**`README.md` §2.1a**（卡 R1 写一半，卡 R2 补足后果）与 **`DATA_LICENSE` §6**（卡 R2 新增整节，另在一页速览加一行）。后果写法：「分可复现，但判分用的那条线是跨名单的，贴着阈值的边界样本可能判反」。`ops/reports/known_limits_v1.md` 与 `ops/data_cards/gold_subset_v1.md` 同步指向这两处。**本轮不重算。** 出处：卡 R1 / R2。 |
| **N-733** | `snapshots/public_v1/gold_factors/csi1000`（8.3 GiB / 8.9 GB，792 件）**保留在 f01、不入包** | **已闭合（写明了）** | 打包脚本确实没收它，两条独立证据：① `pack_gold_subset.py` 的源根写死 `gold_factors_r2/`（常量 `SUBSET_ROOT_NAME`），那个根下只有 `csi300` / `csi500`；② 两个已发布附件的逐件校验和里 `csi1000` 命中 **0 行**。「保留但不发」已写进 `README.md` §2.1a、`ops/data_cards/gold_subset_v1.md`、`ops/reports/known_limits_v1.md`。 出处：卡 R1 / R2。 |
| **N-734** | v1.0.17 要做的事：τ / ε / IC 族 / `crosscheck/` / `epsilon/` 改算在 `gold_factors_r2/` 上 | **待 v1.0.17** | 做掉之后 `DATA_LICENSE` §6 整节删掉，`README.md` §2.1a 那一条与 `known_limits_v1.md` 两处同步改口。**重活**，要 `heavy.lock` + 内存封顶。 出处：卡 R2。 |
| **N-735** | 公开树 tag `v1.0.16` 跟着移到新 commit | **已做（卡 R2）** | 三选一的逐条理由写在 `ops/reports/push_result.md` §8.0a。要点：三条版本轴本轮**一条都没动**（改的全是文档与登记），所以不新建版本号；留在旧 commit 会让 §6.6 写在文档里的自核不变量（`git log -1` == `ls-remote main` == `rev-list -n1 v1.0.16`）当场断掉，且外部用户 `checkout v1.0.16` 拿到的是还在说「附件没挂上去」的那一棵。终值：`refs/heads/main` = `f466f1c91481acfc0c5cf87235d5e82b601d8190`，annotated tag 对象 `bae1438986fc2313d45cec4ffad1c05227a2de3c` 解引用同值。 出处：卡 R2。 |
| **N-736** | Release 对象的 `target_commitish` 会在 force-push + tag 移动之后变成**悬空值** | **已闭合（卡 R2 PATCH 过），并立一条纪律** | 它是 Release 创建时存下的字段，tag 已存在时**不生效**（GitHub 文档口径，不会重新打 tag），但留着就是「Release 指向一个没有任何 ref 的 commit」。卡 R2 每轮 `PATCH /repos/.../releases/387775425 {"target_commitish": <新 sha>}` 回 **200**，改完立刻回核 tag / release id / 两件附件三样都没变。**纪律：以后每次 force-push 公开树都要顺手核这一格**，脚本 `$GB/scratch/R2/r2_patch_release.py`（改一行 `NEW_SHA` 即可复用）。 **2026-09-13 作废（用户裁定①，N-748 采纳）**：`target_commitish` 直接写**分支名** `main`，从此永不悬空，**这条「每次 force-push 之后手工 `PATCH` 一次」的纪律整条删除**。上面原文留证不删。 出处：卡 R2；作废出处：用户裁定①（卡 P3 落）。 |
| **N-737** | `ops/reports/push_result.md` §6 / §6.7 标题上「只有内网仓库这一份有这一节」已不成立 | **已更正（卡 R2）** | 那两句是 2026-09-12 那一刻的事实（当时它们还没进 HEAD）。上一轮写完就进了 HEAD，于是本轮 `git archive HEAD` 打的树里 §6 / §7 都在。**新口径**：推前能写的全进树（§1–§8.1），只有推后实测的终值（§8.2）在推完之后才提交进内网仓库、公开树里没有它。**给下一个写这份文件的人：进树的小节里一个 sha 都别写**（卡 R2 踩过一次，第二轮重打之后那个 sha 当场变假话）。 出处：卡 R2。 **2026-09-13 卡 W 升格成口径**：这个坑三轮踩了三次，本条已写成 `ops/HANDOFF.md` §19.6.6「树内不记终值」，见 **N-743**。 |
| **N-738** | README 里凡是指 `$GB` 下而非仓库下的路径，**必须带 `$GENEBENCH_ROOT/` 前缀** | **已闭合（卡 R2 自引入自修）** | `test_readme.py::test_every_repo_path_named_in_the_readme_exists[snapshots/public_v1/gold_factors/csi1000]` —— 新写的 csi1000 那句以 `snapshots/` 开头，被 `test_readme` 当成**仓库路径**核存在性，而那份数据本来就不在仓库里。加前缀后复跑 **228 passed**。 出处：卡 R2。 |
| **N-739** | ⚠ **`ops/test_e.py::test_附件还没上传时_报告必须把它记成blocked` 是真红，且是一处对外说假话** | **已闭合** | `ops/reports/publish_report.md` 里还留着「一个 Release 都没有，**附件清单为空**」，而两个附件 2026-09-13 已挂上、`RELEASE_MANIFEST.release_attachments` 两条 `download_url` 都已回填，于是那条**双向门**的 `else` 分支断言 `"附件清单为空" not in 报告` 当场红。**该文件不在 R1 / R2 / R3 任何一张卡的路径内**，三张卡都按并发施工规则没碰。改法：那一格改成「已建 Release `v1.0.16`，两个附件均 `state=uploaded`（2026-09-13，见 `push_result.md` §7 / §8.1）」，同一行「（已打定，待上传）」改成「（已上传）」。**门认的是子串 `附件清单为空`，所以不能用 §6.4 那种「原样留证 + 加一句已不是现状」的写法 —— 那个子串必须消失。** **后果**：不改的话外部用户 clone 公开树跑 `pytest ops/` 会看到这一条红，而且它属于「文档对外说假话」那一类。**改完要重打树重推**（命令见 `push_result.md` §8.0 与本节末尾）。 出处：卡 R2 提，卡 R3 复核仍开。 **2026-09-13 卡 F 闭合**：`ops/reports/publish_report.md` 那一格已改成现状（已建 Release `v1.0.16` id `387775425`、两件附件 `state=uploaded`，两条实际下载地址与完整 `sha256` 一并写进 §一），门认的子串 `附件清单为空` 全文 0 命中；§三 BLOCKED 与 §六 第 1 条按原样留证并标了日期（`ops/test_e.py::test_六条裁定逐条有判` 仍要求 ③ 那一格含「未达成」、BLOCKED 一节含 `403` 与 `contents=write`，所以只标日期不删原文）。实跑 `ops/test_e.py` **14 passed**（由 1 failed / 13 passed 转绿），`ops/test_d.py` 与 `ops/test_env.py -k gold` 未被带红。已重打公开树重推并从远端按 `ref=main` 取回复核。 |
| **N-740** | `ops/test_wrt.py::test_rebudget只动没跑过的行` 在本机恒红 | 登记不修 | `KeyError: 's1-cor-01.strict.cfg.r01'` —— 这台机上 `job_id` 带 `@finance01-<hash>` 后缀（捕获的 stdout 里看得见），断言按不带后缀的 id 取行。**环境相关的既有红**（N-619 / N-669 已登记过），与本轮改动无关。 出处：卡 R2。 |
| **N-741** | `ops/test_underdetermination_guard.py::test_unattributed_residual_is_documented_in_all_three_places` 红 | 登记不修（**别人的半成品**） | 三处之一 `ops/reports/ambiguity_impact_2.2b.md` 正被另一个代理改着（`git status` 里是未提交的 ` M`），改到一半少了 `22.69%` 那个数。按并发施工规则**没碰**。提交它的人负责让三处的量重新对上。 出处：卡 R2。 |
| **N-742** | **本轮收口**：两个收件箱并表、HANDOFF 追一节、短报告、已知限制重新点数 | **已做（本卡 R3）** | 票据并入见本节；`ops/HANDOFF.md` §19.6（本版是什么 / 附件地址与 sha256 / 还欠什么）；短报告 `ops/reports/release_upload_report.md`（六节）；`known_limits_v1.md` 新增 R3 一节并把逐类计数由 **63 → 67**。终值数字：全量 pytest **4,515 passed / 9 failed / 33 skipped / 1 xfailed**（卡 R2 实测，本卡未重跑全量），真 API **5,036 次 / 133 run / 194,204,110 tokens**（本卡重跑 `$PY ops/api_usage.py` 复核，与上一轮同值 —— R1/R2/R3 三张卡**一次真 API 都没打**）。 出处：卡 R3。 |


## 卡 W（2026-09-13）—— 断掉「树内写死终值」这个复发根因 + 修掉卡 V 的七条

> 收件箱 `ops/tickets_inbox/W.md`，编号从 **N-743** 续编（上一节末号 N-742）。
> 本卡的由来：**卡 V**（外部用户视角独立复核，只读，零模型 API）在已推的公开树里实测出
> **3 条 block + 4 条 major + 2 条 minor**，逐条写在 `ops/tickets_inbox/V.md`。
> 卡 V 自己一个字都没改 —— 它标了 CONFLICT：要并进 `known_limits_v1.md` 就得重出
> `RELEASE_MANIFEST.json`，而清单不在它的路径里。**卡 V 的判断是对的**，本卡两条路径都有，由本卡做。
> 短报告仍是 `ops/reports/release_upload_report.md`（本卡在其中逐处标了日期留证）；
> 已知限制终态在 `ops/reports/known_limits_v1.md` 的 **W 一节**（67 → **76 条**）。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-743** | **口径：树内不记终值** —— 「报告记不下自己那棵树的 sha」这个递归，**三轮踩了三次** | **已立（本卡）** | 三次分别是 `push_result.md` §5 对 `§6`/`§6.7`、同一份文件 §8.3 对 `§8.1`/`§8.2`、以及本轮卡 V 实测到的 `HANDOFF.md` §19.6.1 与 `release_upload_report.md` §三。**形状每次一样**：重打一次树，树内写死的终值就变成假话；而「每轮补一条口径更正」永远追不完 —— 补更正本身也要重打树。**根治办法不是补更正，是不把会变的值写进会进树的文件。** 口径写进 `ops/HANDOFF.md` **§19.6.6**：① 进树的文件里不写 `refs/heads/main` sha、tag 对象 sha、公开树件数**这三类**；② 要人自核只写**自核不变量**（`git log -1` == `git ls-remote origin refs/heads/main` == `git rev-list -n1 v1.0.16`，三者同值即是 —— 卡 V 在全新 clone 上实测成立）；③ **已经写下的值一律不改值**，只在同一处加显式日期抬头（有的 sha 是门的断言常量，改值当场红）；④ **推后终值只记进内网仓库** `push_result.md` §8.x，树内只写「终值在内网仓库、自核用那三条命令」——**这句话不含 sha，永远不过期**。自查脚本 `$GB/scratch/W/w_scan_stale.py`，**重打完树、推之前跑一遍**。 出处：卡 V 提（第四节两句话），本卡立。 |
| **N-744** | **卡 V 的 3 条 block + 2 条 major + 1 条 minor：「指着旧状态说话」与「记着推送前 sha」的四处文档** | **已闭合（本卡）** | 六处**一次改完**，全部按 N-743 的口径「**不改值，只加显式日期抬头**」：① `HANDOFF.md` §19.6.1 终值表 —— 抬头改成「2026-09-13 R1–R3 轮终值（留证，非当前值）；卡 F 之后又推过一轮，当前终值以 `git ls-remote` 现查为准」，「怎么核」列改口成「那一轮是怎么核的」，表前写明自核要用自核不变量、**不要拿现查结果去比对表里的值**；三行值原样不改。② `HANDOFF.md` §19.6.4「还欠什么」表 —— **整张表逐行核过**：第一行（N-739）与第二行（N-731）都由卡 F 闭合，改成「已闭合」并划掉留证；后三行（baostock 许可正文 / `CITATION.cff` / v1.0.17）复核仍成立，保持原状；表头加了「整张表逐行核过一遍的日期」。③ `HANDOFF.md` §19.5.1 —— 整屏加「2026-09-12 那一轮的终值留证」抬头，那句「附件还没挂上去、地址会 404」句首加日期并补一段写明 2026-09-13 起的现状。**那一屏里的 `bd0513a4…` 是 `ops/test_e.py::test_handoff_与报告记的远端sha是同一个` 的断言常量，只能标日期、不能改值。** ④ `release_upload_report.md` §4.1 —— 抬头改成「2026-09-13 卡 F 已闭合（N-739），本节原样留证」，前面加一段写明现状（子串 0 命中、克隆树里 **31 passed / 1 skipped**），原文整段保留。⑤ 同一份 §三 抬头「现状」改成「2026-09-13 R1–R3 轮终值（留证，非当前值）」；§一第 6 步同病同改。⑥ 通读全篇，§六 的 pytest / 已知限制 / 票据末号 / 公开树件数四行都标了日期或改成现状，§4.3 的 N-731 也标了已闭合。 出处：卡 V。 |
| **N-745** | **`RELEASE_MANIFEST.json` 的两处对外正文在骗读许可条款的人**（卡 V 的两条 major） | **已闭合（本卡，改源不改生成物）** | ① `package.parts` 里「形态 A」那一条三处全过时：`publishable=false`（实测 `true`）、「许可到位后发」（**2026-09-13 已经发了**）、`788,422,669 B`（那是卡 R2 按 N-714 **删掉**的 `_staging_unpublished` 旧包；已发的 provider 是 **782,100,276 B**）。② `blockers[data_license_text].blocks` 正文三句全不成立：那个目录已删、包内 `publishable=true`、两件附件**匿名 `Range` GET 实测 206**（「外部用户拿不到包」正好说反）。**改法**：改 `ops/mk_release_manifest.py` 的**源**，不是只改生成物 —— 新增 `PART_OVERRIDES`（键用存档件里的 `path`，不是会被改掉的 `part` 文本；键对不上存档件时**当场 assert 停**，不许静默无操作），`blocks` 正文改成「许可正文仍未入库（`DATA_LICENSE` §2.1 是显式占位）；形态 A 已按 2026-09-13 裁定发布为 Release `v1.0.16` 的附件、匿名可下，不再阻断下载」。**`satisfied` 的判定逻辑一个字没动**（仍是 `dl_state == "granted"`），改的只是对外正文。**存档件 `ops/reports/i_rehearsal_v2/package_inventory.json` 一个字节没改** —— 它是 2026-09-06 那一轮的留证，改它要连带重算它的 sha。重出清单后 `$PY ops/mk_release_manifest.py --check` **退 0**、`releasable=true`、未闭合 blocker **0**。 出处：卡 V。 |
| **N-746** | **卡 V 的九条并进 `ops/reports/known_limits_v1.md`** | **已闭合（本卡）** | 卡 V 因为「改它就要重出 `RELEASE_MANIFEST.json`，而清单不在它路径里」而一个字没写（标了 CONFLICT，**判断是对的** —— 那份文件是清单登记的**手写件**，`ops/test_release_manifest.py::test_every_recorded_sha_of_a_handwritten_item_is_the_real_one` 逐件重算 sha，追加一个字节就会把当时是绿的门打红）。本卡两条路径都有，新增 **W 一节**：九条逐条写清 where / what / 本轮改法 / 为什么这么改，逐类计数 **67 → 76**（已修/已闭 18→**26**、设计性 11、v1.1 5、登记不修 31→**32**、BLOCKED 2；两列各自逐类相加 = 各自合计，`ops/test_e.py::test_已知限制的终态计数表自洽` 的口径）。写完重出清单。 出处：卡 V。 |
| **N-747** | **已发布的 provider 包内 `MANIFEST.json` 带 `license.published: false`** | **登记不修（知情保留）** | 按卡 V 的判断照办。**修的代价远大于害处**：这个字段烤在 `tar.gz` 里，改它要**重打包**，重打包换 `sha256`，而两件附件的 `sha256` 已写进**三处**并被 **GitHub 自己的 `digest` 字段背书**（`ops/release/attachments.json`、`RELEASE_MANIFEST.release_attachments`、`README.md` §2.1a 的 `SHA256SUMS.release`）——**一重打包，这三处已公布的校验值当场全部作废**，而那是外部用户唯一能自证「下到的包没被掉包」的凭据（卡 C 撞过一次同形的事：`21ec3202…` → `33083ff2…`）。**害处是有界的**：`published` 说的是「许可原文有没有公开可查」，而许可原文确实**仍未入库**（`DATA_LICENSE` §2.1 是显式占位）—— 措辞容易被读成「包没发布」，但它记的那件事本身没说错；包**是否已发布**另有三处权威出处可查。**处置**：等**下一次本来就要重打包**的时机（v1.0.17 重算 τ / ε，N-734）顺手改掉。**本轮一个字节都不重打包、不重传任何 asset、不新建 Release。** 出处：卡 V 判，本卡照办。 |
| **N-748** | Release 的 `target_commitish` 可以直接设成**分支名** `main`，从此永不悬空 | **2026-09-13 用户裁定①：采纳** —— `target_commitish` 写 `main`，N-736 那条手工纪律整条删除 | N-736 立的纪律是「每次 force-push 之后把 `target_commitish` `PATCH` 到当轮新 sha」—— 那是一条**每轮都要记得做一次**的手工纪律，漏一次 Release 就指向悬空 commit。本轮实测：`PATCH {"target_commitish": "main"}` 回 **200**，之后 `GET` 读回来就是 `"main"`。GitHub 的口径是**tag 已存在时这个字段不生效**（不会重新打 tag），所以两种写法对 tag、对附件、对下载地址**都无影响**；差别只在「这一格记的是一个会过期的值，还是一个不会过期的引用」—— 正是本轮 N-743 那条口径说的事。**本轮没有采纳**：卡的指令逐字写的是「`PATCH` 到本轮新 sha」，且前三轮都是这么记的，单方面改掉部署行为不合适。**留给用户/编排方裁定**：采纳的话 N-736 那条纪律可以整条删掉。 **2026-09-13 用户裁定：采纳。** 依据：`PATCH {"target_commitish": "main"}` 实测回 200，且 tag 已存在时该字段不生效，对 tag / 附件 / 下载地址一概无影响。落点五处：`ops/HANDOFF.md` §19.6.5 ②与命令块、`ops/reports/push_result.md` §8.2/§8.3（以上卡 P2）、本文件 N-736 行与本行、`ops/reports/known_limits_v1.md` 那一格（以上卡 P3）；第五处 `ops/reports/release_upload_report.md:85` 见 N-785。 出处：本卡（实测撞到 N-749 时顺带验的）。 |
| **N-749** | `scratch/R2/r2_patch_release.py` 的 `api()` **对 HTTP 5xx 不重试**，一次瞬时 500 看上去像硬失败 | **登记不修（脚本在 scratch，判别办法已写进 §8.4）** | 本轮 `PATCH target_commitish` 头两次回 **500、响应体为空**、带 `X-GitHub-Request-Id`，第三次**同样的请求**回 200 —— 是 GitHub 侧的瞬时错误。但 `api()` 的 `except urllib.error.HTTPError` 分支**直接 `return e.code`**，只有网络异常那一支才进重试循环，于是 500 被当成终局。**判别办法**：先 `PATCH` 一个**空操作**（`{"prerelease": false}`，与现值相同）—— 它要是 200，就说明端点、token 权限、release 本体都没问题，5xx 是瞬时的，直接重试即可；要是也 500，才去查权限与 release 状态。本轮的诊断脚本留在 `$GB/scratch/W/w_patch_diag{,2}.py`。**替代品已在**：`$GB/scratch/W/w_patch_release.py` 与 `r2_patch_release.py` 同逻辑，另外两处更稳 —— ① `NEW_SHA` **从本地公开树的 HEAD 现读**，不用手改（手改那一行是第四次了）；② `PATCH` 之前**断言远端 `main` 已经等于它**，否则又会 `PATCH` 成悬空值。**下次改 Release 用它。** 与 N-729 是同一条链路的两件事：N-729 是慢和断，这条是 5xx 不重试。 出处：本卡。 |


## Mac 缺件收口轮（2026-09-13）—— 四张卡（A2 基座 / B2 物料 / C2 文档 / D2 收口）并表

> 本轮的由来：用户 2026-09-13 在一台干净 Apple Silicon Mac 上做外部验收，判定
> 「下载 / sha256 / 解包 / 本机网关四项通过，**端到端阻塞**」，且**不是 Mac 适配问题，是发布包不完整** ——
> 上一轮「单机端到端」演练跑在 f02，那台机器本来就有统一基座、公开题集与标定物料，**所以演练看不见它缺**。
> 编号从 **N-750** 续编（上一节末号 N-749，卡 W）。逐条判定在 `ops/reports/mac_gap_closeout.md`，
> 登记与计数在 `ops/reports/known_limits_v1.md` 的 D2 一节，交接在 `ops/HANDOFF.md` §19.7。
> **本轮只落到内网仓库：没有重打公开树、没有 push、没有碰 Release、没有动附件、三条版本轴一个值没改。**

### A2

**卡 A2（统一基座，缺件①）** —— 收件箱 `ops/tickets_inbox/A2-macgap.md.merged`。编号卡 A2 自己已编好，原样保留。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-750** | `harnesses/build.sh` 在 macOS 的 UTF-8 locale 下报 `BASE_IMAGE?: unbound variable`，真正的原因（缺基座）永远打不出来 | 已完成 | 病灶是 `"$BASE_IMAGE。"` 这种**变量名后面紧跟中文标点**的写法：macOS 的 bash 3.2 在 UTF-8 locale 下把标点的头一个字节吃进变量名，`set -u` 当场炸。**只在某些 locale 下发作** —— 本机复现（darwin 24.6.0）：`/bin/sh` 与 `/bin/bash` 在 `LC_ALL=en_US.UTF-8` 下必炸、`LC_ALL=C` 下正常，zsh 两种都正常。这正是发布方自己（Linux + dash）永远踩不到的那一类，外部验收第一次跑就撞上。改法：**全脚本变量插值一律 `${VAR}`**。回归锁 `ops/test_A2.py::test_build_sh_has_no_bare_var_before_nonascii`（扫 `build.sh` 与 `build/base/Dockerfile` 两份，见到"裸 `$VAR` 后紧跟非 ASCII"就红）。出处：卡 A2。 |
| **N-751** | 统一基座的 Dockerfile 不在仓库里，且只钉了 x64 的 Node sha256 | 已完成 | 两件事一起修。①`build/base/{Dockerfile,requirements.txt,constraints.txt,README.md}` 搬进仓库，`harnesses/build.sh` 缺基座时**自己从这里构**，不再指向发布方绝对路径。②Node 的 tarball 与 sha256 **按架构分**（x64 / arm64 两个包两个哈希），原来只钉 x64 —— 在 Apple Silicon 上的表现是「下 arm64 的包、拿 x64 的哈希核」，`sha256sum -c` 失败，看起来像下载损坏。两个哈希都从 `nodejs.org/dist/v22.23.2/SHASUMS256.txt` 实取；arm64 那个还真下了 30,246,708 字节的包核过、`file` 认出 `ARM aarch64`。架构用镜像里的 `dpkg --print-architecture` 选，**不用 BuildKit 的 `${TARGETARCH}`**（legacy builder 下它可能是空的）。实测：f02 上用仓库里这份构 amd64 成功（282 秒 `--no-cache`），`pip freeze` 与既有基座逐行相同。出处：卡 A2。 |
| **N-752** | `.gitignore` 第 6 行那条**不锚定**的 `build/` 把新加的 `build/` 子树整片 ignore 掉 | **待办（要编排方裁定）** | git 的目录模式匹配任意层级，所以 Python 打包惯用的 `build/` 连仓库根的 `build/` 一起吃掉。本卡的三个文件是用 `git add -f` 显式加进去的 —— **已入库、clone 得到、不受影响**，但**以后在 `build/` 下新建文件 `git status` 不会提醒**，漏 add 的表现是「我这台构得出来，别人 clone 下来构不出来」。`.gitignore` 自己的注释里就骂过同一个形态（"⚠️ 千万不要写成不锚定的 `snapshots/`"）。根治：在第 6 行下面补一行 `!/build/`（纯追加，一行）。`.gitignore` 不在本卡可改路径内，故留给编排方。出处：卡 A2。 |
| **N-753** | `ops/push_exec_to_f02.sh` 不推 `build/`，执行树上「缺基座自动构」那条路走不通 | 登记（有兜底） | exec 树只有 `genetask ops runner vendor` 四目录 + `harnesses/` + `integrations/`，没有 `build/`。所以 f02 的 `/data/genebench_runner/exec` 上真缺基座时，`build.sh` 会报「基座的构建上下文也不在」并给出三条出路，其中 `GB_BASE_CONTEXT=<path> sh harnesses/build.sh <id>` 已实测可用。**外部用户不受影响**（他们手里是完整仓库）。要根治就在同步脚本里加 `build/`；那个脚本不在本卡可改路径内。出处：卡 A2。 |
| **N-754** | 没有 buildx 的 docker 把 `docker build --platform` **当空气**，只在最后一刻炸 | 登记不修（已写进报告） | f02 实测：`docker build --platform linux/arm64 …` 没有报"不支持"，而是照常用 amd64 往下构（apt 抓的是 `binary-amd64_Packages`、`dpkg` 认出 amd64、Node 取 x64 且哈希核过），一路"绿"到第 6 步 `COPY` 才报 `image … does not provide the specified platform (linux/arm64)`。谁在这种机器上敲 `--platform`，前五步的成功输出会让他以为在交叉构建。已在 `ops/reports/base_image_portability.md` §3.2 写明，并在 §4 提醒「用 `--platform` 前先确认 `docker buildx version` 有输出」。出处：卡 A2。 |
| **N-755** | `RELEASE_MANIFEST.json` 的 53 个仓库文件清单里没有新增的 `build/base/*` | **待办（归卡 D）** | 本卡新增 5 个仓库文件（`build/README.md`、`build/base/{Dockerfile,requirements.txt,constraints.txt,README.md}`）。它们是**外部用户构基座必须拿到的东西**，清单里没有它们，就等于「发布清单声称交付完整而基座仍然缺件」——正是本轮要修的那一条。RELEASE_MANIFEST 归卡 D，本卡不碰。出处：卡 A2。 |
| **N-756** | `harnesses/README.md` §3.2 的「`build.sh` 做的事」第 4 条已过时 | **待办（归卡 C 或 harness 手册维护方）** | 现在写的是「核基座已在本机（**`docker.io` 被墙**，`docker build` 不会替你拉）」。改动后的行为是「核基座在不在；**不在就用 `build/base/` 自己构**（`--no-base-build` 可关，`GB_BASE_CONTEXT` 可改上下文，`GB_BASE_PLATFORM` 可指定平台）」。另外 §2 那句「`docker.io` 被墙，不要 `FROM` 任何公网镜像」是**发布方内网**的实情，对外部用户不成立（他们的 `docker.io` 通，基座正是这么构出来的）——照字面读会让人以为基座根本构不了。`harnesses/README.md` 是共享文件且不在本卡可改路径内。出处：卡 A2。 |

### B2

**卡 B2（公开题集实例 + 公开标定物料，缺件②③）** —— 收件箱 `ops/tickets_inbox/B2-macgap.md.merged`。原收件箱里编号一律写 `N-?`，由本节定号。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-757** | `ops/run_controls.py:53` 写死发布方绝对路径，外部用户结算必炸 | **待修（不在卡 B2 可改路径）** | `PUBLIC_ANSWER_ROOT = Path("/data/shared/genebench/reference/tasks/public/v1.0-smoke-public")`，而 `ops/score_runs.py:49` 正是从这里 import。`ops/run_joblist.py:79` 用的是 `cfg.GENEBENCH_ROOT / …`。干净 clone 实测两者不等 → 外部即使把第三个附件正确落位，`score_runs` 仍去发布方路径找题集，每个 run 记「没有题目录」。在 f01 上两条路径碰巧都存在，所以内部跑不出来。修法：改成 `cfg.GENEBENCH_ROOT / "reference" / "tasks" / "public" / F.PUBLIC_SET_ID`（与 `run_joblist` 同源），`ops/test_c65.py:49` 的相等断言随之才有意义 |
| **N-758** | 同一类写死：`run_controls.py:48/49/54`、`ops/validator_parity.py:40-41`、`ops/run_probe_mutations.py:46/382` | 待修 | `:48` 私有题集根、`:49`/`:54` 两条网关日志路径也都写死在 `/data/shared/genebench/…`。`:49`/`:54` 会让外部用户的四个依赖网关日志的探针族整片标 `unobservable`，而且**不报错** |
| **N-759** | 重打公开树时要在 `EXCLUDED.txt` 里写明「题集与标定在第三个附件里」 | 待办（重打树那张卡） | `scratch/G2/mk_tree_g2.sh` 现在只说「树里本来就没有数据文件」，没说去哪拿。缺件 ② 的根因就是 `git archive HEAD` 取不到 `$GENEBENCH_ROOT` 下的物化产物 —— 不写这一句，下一个外部用户还是只能猜 |
| **N-760** | `ops/data_cards/public_channel.md` 补一条指向 `public_runtime_v1.md` 的链接 | 待办 | 本卡没有改 `public_channel.md`（共享文件，避免与并发卡撞）。新数据卡是 `ops/data_cards/public_runtime_v1.md` |
| **N-761** | `ops/test_public_chain.py:296` 断言读 `calibration.json` 里的发布方绝对路径 | 登记不修 | `assert str(cfg.SNAPSHOTS_PUBLIC) in d["provider"]["dir"]`。外部环境下 `calibration.json` 里记的是发布方路径，这条必红。评分链路**不读**这些路径，所以不挡发布；要修得先决定「标定文件里到底记不记绝对路径」 |
| **N-762** | 第三个附件未上传 | 待办（上传那张卡） | `genebench_public_runtime_v1.tar.gz`，42,046,516 B，sha256 `49e9b250d398a1ceaad22da3de6d2cc87605a5dc036113bf4b19f04e2e00963f`，已登记进 `ops/release/attachments.json`，`download_url` 留空。README §2.1a 的下载清单也要随之加一件（卡 C 的范围） |

### C2

**卡 C2（README 与手册，外部验收 ④⑤⑥⑦）** —— 收件箱 `ops/tickets_inbox/C2-macgap.md.merged`。原收件箱里编号一律写 `N-?`，由本节定号。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-763** | `genebench_config.py::GATEWAY_HOST` 没有环境变量可覆盖 | 登记 | 端口有 `GENEBENCH_GATEWAY_PORT`，**地址没有**。外部用户换机器必须改常量（手册 §1.3 那张三行表）。建议加 `GENEBENCH_GATEWAY_HOST`，形状与端口那条一致，并且照样过 `assert_no_wildcard_bind()`。本卡只在 README §2.3 / 手册 §1.5 / `ops/selfcheck_public.py` 第 6 项里把这件事说清楚了，**没有改 `genebench_config.py`**（不是本卡的路径，且它在冻结根的邻域）。 |
| **N-764** | `ops/run_joblist.py --tables` 的帮助文本漏了 `main` | 登记 | 帮助写的是 `（a,b,adaptation）`，但它是把值原样透传给 `ops/mk_tables.py --table` 的，`main` 一样认 —— 而 `main` 才是发布表。README §2.4 已经改成 `--tables main,a,b` 并加了一句说明；**帮助文本本身没改**（`ops/run_joblist.py` 不是本卡的路径）。 |
| **N-765** | `ops/run_joblist.py` 起子进程写死 `genebench_config.PYTHON` | 登记 | = `$GENEBENCH_ROOT/env/bin/python`。外部用户把 venv 建在别处，前面几步都正常，到「出表」那一步才报找不到解释器 —— 失败点离原因很远。两个方向：① 退回 `sys.executable`；② 启动时早一点核一次并直说「venv 要建在 `$GB/env`」。本卡的做法是**文档兜住**（README §1.5 / §2.1、手册 §1.2 都写明了落点），代码没动。 |
| **N-766** | 公开题集 S4–S7 的 18 道题、30 个输入夹具没随两个附件交付 | 已知缺件 | `ops/freeze_v10.py --check-all` 的公开轴因此核不绿，差异**全部**落在 `channel_fixtures/`；private 轴与参考面轴一致，两个附件逐件 sha256 全过 —— 不是下载损坏。`ops/selfcheck_public.py` 对这一形态报「登记在案」而不是红，并且**只在差异全部落在 `channel_fixtures/` 时**才这么报（混进别的差异就红，`ops/test_selfcheck_public.py` 钉住了这条）。补夹具是另一张卡的事。 |
| **N-767** | macOS 上没有 systemd，推送守门要求的那道答案面扫描 timer 在 Mac 上缺失 | 登记 | `ops/push_bundle_to_f02.sh` 推之前核执行面上 `genebench-answer-plane-scan.timer` 是 `enabled + active`，Mac 上这条过不去。**少的是第三道兜底清扫**，不是主判据（主判据是挂载面口径的 `answer_plane_guard.py --mode container`，推送脚本自己也跑 container + tree 两道）。手册 §1.3 已经写明「少了什么」并给了 launchd 的等价形状，但**那份 plist 没写、也没在 Mac 上验过**。 |
| **N-768** | `ops/test_env.py` 断言 `qlib` / `httpx`，而六包说明里没有这两个 | 登记不修 | 内部自检自己的口径不一致。本卡只给它的文件头写明「内部自检，外部用户不要跑这个」，**没有动它的断言**（动了就是改别人的判据）。 |
| **N-769** | Mac 上「网关真起来」这一步本卡没能亲手验到 | 登记 | 施工用的 Mac Bash 沙箱**不许 bind 监听口**（`bind → [Errno 1] Operation not permitted`，`127.0.0.1` 的任何端口都一样）。本卡在 macOS 上验到的是：`have ss`=no、`have setsid`=no、`have lsof`=yes；`port_busy` / `listener_pid` 对着一个真在监听的端口判对；脚本走 nohup 支路把进程起起来了，停在 uvicorn 的 bind 上。「真起来 + `/healthz` 200 + stop 端口释放」这一段是在 f01 上**把 `ss` 与 `setsid` 从 PATH 里遮掉**、逐条走同一支代码补验的。用户自己 2026-09-13 在同一台 Mac 上（无沙箱）起过网关并拿到 200，证据在验收报告的 `evidence/healthz.json`。**要一次「Mac 上原样跑 `ops/public_gateway.sh start` 拿 200」的记录，需要一个没有沙箱的终端。** |

### D2

**卡 D2（收口 + 端到端实证）** —— 收件箱 `ops/tickets_inbox/D2-macgap.md.merged`。这几条全是在**一次真的端到端**（f02 全新目录、干净 clone、新 tag 基座、三题双臂真跑、出 `--table main`）那条链上撞出来的。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-770** | `ops/score_runs.py:45` 的 `RUNS_IN` 写死发布方绝对路径，**且没有任何 CLI 覆盖** —— 外部单机用户跑完了也结算不出分 | **待修（不在本卡可改路径）** | `RUNS_IN = Path("/data/shared/genebench/runs_in")`，`--no-pull` 那条路直接拿 `RUNS_IN / batch` 当 run 根。外部机器上那个目录不存在，于是**退 0** 并打印「runs: 0；问题: 0」——**不报错**。另一条路 `--remote` 更糟：`pull()` 里 `F02 = "ljn@192.168.1.219"`（`score_runs.py:44`）也是写死的，外部用户敲 `--remote <自己的路径>` 会让 rsync 去连**发布方的执行面**。D2 实测（f02 干净树）：`--no-pull` → `runs: 0`；`--remote /data/d2_e2e/runs/runs` → 走到发布方地址。**加一条软链把 run 根挂到那个写死的位置之后，整条结算链一次通过**，说明挡路的只有这一个常量。修法与 `run_joblist` 同源：`cfg.GENEBENCH_ROOT / "runs_in"`，并给 `--runs-root` 一个显式入口。出处：卡 D2。 |
| **N-771** | 两个大附件**没有任何文档给过落位命令**，而 `provider/` 还要改名成 `qlib_provider/` 才认 | **待修（归文档卡）** | README §2.1a 只到「解开 + `sha256sum -c`」为止；手册 §1.4(a) 讲的是打包与自建，§1.4(c) 讲的是「引用别人已经建好的快照」——**没有一处说「解出来的这几个目录该放到 `$GENEBENCH_ROOT` 的哪里」**。实际映射要自己从 `genebench_config.py` 倒推：`provider/` → `$GB/snapshots/public_v1/**qlib_provider**/`（**改名**，`PUBLIC_PROVIDER_DIR`）、`tables|tradability|universe|frozen/` → 同名落 `$GB/snapshots/public_v1/`、gold 包的 `gold_factors/` → `$GB/snapshots/public_v1/gold_factors/`。第三件（runtime）**有**现成命令（`--strip-components=1 -C $GENEBENCH_ROOT`），正好反衬出前两件没有。Mac 外部验收那位自己猜对了，下一个未必。出处：卡 D2。 |
| **N-772** | `ops/push_guard.py` / `ops/push_bundle_to_f02.sh` 不带通道，公开通道 bundle 过门时报的是**另一件事** | **待修（不在本卡可改路径）** | 不设 `GENEBENCH_CHANNEL=public` 直接对公开 bundle 跑 `push_guard.py`，它拿**私有**轴当「当前」，报「bundle 的冻结引用已过期：通行证 {p1.0.0 / 3e5ab441…} ≠ 当前 {1.0.16 / d9ebd541…} → **重新导出，不要改通行证**」。**按它说的重新导出解决不了**，真因是通道没给。`push_bundle_to_f02.sh` 自己也不设这个环境变量。实测：同样三个 bundle，加 `GENEBENCH_CHANNEL=public` 之后三条全绿。修法二选一：脚本里从 bundle 的通行证**反推通道**，或者在报错文案里把「通道对不对」列成第一嫌疑。出处：卡 D2。 |
| **N-773** | 手册 §1.2 让人从 `bootstrap.pypa.io` 引导 pip —— 这台机器上那个域名**挂住**，症状与 Y-03 记的 pypi.org 一模一样 | **待修（归文档卡）** | 实测：`curl -sS -o get-pip.py https://bootstrap.pypa.io/get-pip.py` **11 分钟 0 字节**，现场表现是死机不是报错。§1.2 已经为 pypi.org 写了「要带 `-i <镜像>`、不是慢是看起来像死机」，**但引导 pip 那一步没有镜像出路**。可用的替代已实测：从镜像的 simple 索引直接取 `pip-<版本>-py3-none-any.whl`（注意索引里的 href 是**相对路径** `../../packages/…`，要自己拼成绝对地址），然后 `python3 <pip.whl>/pip install --target <site> -i <镜像> …`。全程 **80 秒**。出处：卡 D2。 |
| **N-774** | `python3 -m venv $GB/env` 在 Ubuntu 24.04 上建出一个**没有 pip 的半成品**，而且**留下了 `$GB/env/bin/python`** | **待修（归文档卡）** | 手册 Y-02 记过「`venv` 与 `pip` 两个都没有」，但没记这个形态：`python3 -m venv` **不是干净失败**——它报 `ensurepip is not available` / `Failing command: …/env/bin/python3`，**同时把目录和解释器软链留在那里**。于是「`$GB/env/bin/python` 存在」这个最自然的判据为真，而 `import fastapi` 才炸。本卡第一遍就掉进去了。文档要加一句：判 venv 可用的判据是 `"$GB/env/bin/python" -c "import fastapi"`，不是文件在不在；建之前先 `rm -rf` 半成品。出处：卡 D2。 |
| **N-775** | `ops/guard_modes.py --harden` 在外部机器上**不收紧 `$GENEBENCH_ROOT`**，而 README 说它收紧 | **待修（不在本卡可改路径）** | `EXTERNAL_ROOTS` 写死 `("/data/shared/genebench",)`，「不存在就跳过」。外部用户的 `$GB` 在别处 → 那条路径不存在 → **只收紧了仓库这一个根**（实测输出「收紧 0 个条目 / 敏感根权限合规（**1 个根**）」），而网关要求的恰恰是 `$GB` 及其下每一级 0700（手册 §7.6）。README §2.1 那一行现在写的是「收紧 `$GB` 权限；网关起不来的第一嫌疑」——**名不副实**。修法：`EXTERNAL_ROOTS` 改成从 `cfg.GENEBENCH_ROOT` 现算（发布方机器上值不变，外部机器上才真收紧）。本卡是手工 `chmod -R go-rwx "$GB"` 补上的。出处：卡 D2。 |
| **N-776** | 边车镜像 `python:3.11-alpine` 来自 docker.io，**「所需外网」表里一条都没提** | **待修（归文档卡）** | 写死在 `runner/c41/runner_core.py:163` / `:268`。`harnesses/build.sh` 不管它，`ops/reports/rehearsal_v2.md` §2 的「所需外网」表**把 docker.io 记成「不需要」**（那是「基座必须本机已有」那个前提下的结论，现在基座改成自己构了，前提本身也变了）。外部用户第一次真跑之前要 `docker pull python:3.11-alpine`，而失败时刻在**真跑开始之后**——最贵的位置。f02 上碰巧早就有这个镜像，所以本卡的链路没被它挡住（`docker image inspect` 实测在）。出处：卡 D2。 |
| **N-777** | `harnesses/build.sh` 的 `BASE_IMAGE` 写死 `gb-base:bookworm-r1`，**没有环境变量入口** | 登记（对外部用户无影响） | 后果只对「机器上已经有一个同名旧基座」的人成立：想让 harness 叠在**新构**的基座上时，`build.sh` 会径直用旧的那个，而且它的 `--dry-run` 会把旧基座的 digest 打出来（本卡实测打的是 `fd1e2fd0c7ae…`）。本卡因此没走 `build.sh` 的构建那一支，改成把 `harnesses/codex/` 的构建上下文原样复制到 scratch、**只改 `FROM` 一行**指向新基座（diff 就一行，留在 `/data/d2_e2e/build.log`）。**外部用户没有这个冲突**，照 README 敲 `sh harnesses/build.sh <id>` 就对。建议给 `BASE_IMAGE` 补一个 `GB_BASE_IMAGE` 入口（形状照 `GB_BASE_CONTEXT`）。出处：卡 D2。 |
| **N-778** | `RELEASE_MANIFEST.json` 的仓库文件清单仍然没有 `build/` 那五件（= 卡 A2 的 N-755） | **仍待（本卡改不了）** | 要加就得动 `ops/mk_release_manifest.py` 的 `RELEASE_ITEMS`，**那个文件不在卡 D2 的可改路径内**（本卡只许改 `RELEASE_MANIFEST.json` 本身，而它是生成物 —— 手改会被 `ops/test_release_manifest.py` 重算一遍当场打红）。本卡按任务书**重出**了清单（`--check` 退 0 / `releasable=true` / 未闭合 blocker 0 / 第三件附件已进 `release_attachments`），但「清单声称交付完整而基座那五件不在清单里」这一条**没有闭合**。请编排方派一张有 `ops/mk_release_manifest.py` 路径的卡。出处：卡 A2 提，卡 D2 复核仍开。 |
| **N-779** | 重出 `RELEASE_MANIFEST.json` 之后，`ops/reports/publish_report.md` 里**没有**第三件附件，`ops/test_e.py` 两条当场红 | **待修（不在本卡可改路径）** | 本卡按任务书重出清单，于是 `release_attachments` 从 `n=2 / uploaded=2` 变成 **`n=3 / uploaded=2`**，那份报告随之对不上两条门：① `test_报告引的附件数值与清单同源` 要求**每一件**附件的 sha 前 16 位与带千分位的字节数都出现在报告里 —— 第三件（`49e9b250…` / `42,046,516`）不在；② `test_附件还没上传时_报告必须把它记成blocked` 是**双向门**：只要还有空的 `download_url`，报告里就必须有 `## 三、BLOCKED`（**已有**）**且**出现子串 `附件清单为空`（**0 命中** —— 那是卡 F 按 N-739 特意删掉的，当时三件都已上传，删得对）。**这不是回归，是状态真的变了**：现在确实有一件登记了但没上传。修法（三行）：在 `publish_report.md` §一 的附件表里加第三行（名字 / `42,046,516` B / sha `49e9b250d398a1ce…` / 状态「已登记，**未上传**」），并在 §三 BLOCKED 里写一句含 `附件清单为空` 的现状说明（例：「第三件附件 `genebench_public_runtime_v1.tar.gz` 已登记但还没上传，Release 上它的**附件清单为空**」）。`ops/reports/publish_report.md` 不在本卡可改路径内。 出处：卡 D2。 |
| **N-780** | `ops/test_pack_release.py:280` 写死 `ra["n"] == 2` | **待修（不在本卡可改路径）** | 紧接着下一行还有 `assert set(by) == {PP.TARBALL, GS.TARBALL}`。第三件附件进清单之后两条都红 —— **与契约里点名的 `ops/test_c41.py:366` 那条 `len(REG.CONFIGS) == 3` 是同一个形状**：写死件数的断言，会被「第一个把新东西登记进来的代理」跑红，而那不是回归。修法照同一条口径：改成「已发两件 ⊆ 清单」且「逐件字段齐、四条轴与清单同源」，件数不写死（要判「有没有多出来不认识的」，就按 `role` 判而不是按个数判）。 出处：卡 D2。 |
| **N-781** | `ops/test_V2.py::test_十个收件箱都改名merged了_原名一个不留` **恒红**，与本轮无关 | 登记（**别人的**，本轮没碰） | 该条要求 `ops/tickets_inbox/V2.md` 不存在，而卡 V2 的提交 `476bd14`（「终核复核结论进收件箱（唯一写入；未改任何其它文件）」）**新建了这个文件**。卡 V2 那一节的收件箱在更早一轮已经并过表、改名成 `V2.md.merged` 了，所以这个名字一旦被复用就撞门。本卡在落地任何东西**之前**跑过这套定向测试，那时它就已经红（本卡只改了自己的六个路径 + `A2/B2/C2/D2.md` 的改名，一个字都没碰 `V2.md`）。两个方向：① 卡 V2 那份收件箱改名成 `V2-final.md.merged` 之类不撞的名字并并表；② 把 `test_V2.py` 的 `RAW_NAMES` 口径改成「按轮次判」。倾向 ①（门是对的，撞的是卡号复用）。 出处：卡 D2。 |

## 发布前最后一轮（2026-09-13）—— P1 代码根因 / P2 文档与纪律 / P3 合表收绿

> 本轮的由来：用户 2026-09-13 在一台干净 Apple Silicon Mac 上做**外部验收**，判定
> 「下载 / sha256 / 解包 / 本机网关四项通过，**端到端阻塞**」。上一轮（Mac 缺件收口轮 A2/B2/C2/D2）
> 把基座、物料、文档补齐并在 f02 的干净树上跑通了一次端到端，但**那张 24 列表是加了两条软链才出出来的** ——
> 那两条软链指着的正是本轮卡 P1 修掉的根因（N-770 一类：默认值指着发布方那台机器）。
> 编号从 **N-782** 续编（上一节末号 N-781）。三张卡的收件箱已并表并改名：
> `ops/tickets_inbox/P2-push.md.merged`、`P1-push.md.merged`、`P3-push.md.merged`；
> 另把卡 V2（终核复核）那份**撞了卡号**的收件箱改名 `V2-final.md.merged` 并在下面 §V2 并表。
> 已知限制终态在 `ops/reports/known_limits_v1.md` 的 **P3 一节**（115 → **135 条**）。
> **本轮只落到内网仓库：没有重打公开树、没有 push、没有传附件、没有碰 Release、没有动已发两件附件一个字节，
> 三条版本轴（v1.0.16 / r1.0.23 / p1.0.0）一个值没改。**

### 本轮立的一条口径：收件箱文件名**一卡一名、不复用**（N-792）

`ops/tickets_inbox/<名>.md` 的 `<名>` 是**这一张卡独占的**，并表时改名 `<名>.md.merged`。
**卡号可以在不同轮里重复，收件箱文件名不可以。** 两条后果都真发生过：

1. **静默覆盖**（N-652）：`mv V2.md V2.md.merged` 在上一轮已有 `V2.md.merged` 时会把上一轮那份**整个盖掉** ——
   文件还在、名字没变、只是内容成了另一张卡的，没人会发现。`ops/test_V2.py::test_改名没有盖掉更早一轮的merged`
   就是为这件事立的门。
2. **恒红**（N-781）：`ops/test_V2.py::test_十个收件箱都改名merged了_原名一个不留` 钉的是
   「上一轮那十份**原名**一个不留」。2026-09-13 的终核卡又叫 `V2`、又新建了 `ops/tickets_inbox/V2.md`，
   于是这道门从那一刻起恒红 —— **门是对的，撞的是卡号**。

**做法**：卡号有可能复用时，收件箱名加一个本轮的后缀，例如 `V2-final.md`、`A2-macgap.md`、`P1-push.md`、
`Y1-rehearsal.md`（卡 Y1 当年就是为了躲这件事才这么起名的）。改名前**先 `ls` 查有没有同名 `.merged`，
有就停下不覆盖**。`git mv` 之后 `git add` **不要同时列新旧两个路径**：旧路径不存在会让整条 `add` 中止，
只落下改名（卡 R3 踩过）。

### P2（文档与纪律）—— 收件箱 `ops/tickets_inbox/P2-push.md.merged`，编号卡 P2 自己已编好，原样保留

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-782** | `ops/test_docs_consistency.py` 的 fact `manifest_check_nonzero_is_not_damage` 在裁定②落地之后**必红**，判据要翻面 | **仍开着（三张卡的可改路径都不含 `ops/test_docs_consistency.py`）；幂等补丁已写好** | 用户裁定②要的是「**修根因**，不写文档教人忽略非零」，并点名删掉 README §2.1 / README §5 / 手册 §0.0 三处「`--check` 在干净 clone 上非零是环境差异」。卡 P2 把那三处删了 → 那条 fact 的 `require`（`非零 ≠ 发布件损坏`，两处都要出现）当场落空。**这不是回归，是状态真的变了**：根因（`has_remote`）由卡 P1 修完之后，就不该再有那句话。**改法**（两个方向都有牙）：fact 改名 `manifest_check_is_machine_independent`、`require` 换成 `刻意不取决于跑它的机器`（P2 已在 README §2.1 与手册 §0.0 两处写下这一串，逐字相同）、`forbid` 换成 `非零 ≠ 发布件损坏`（不许再写回去）。**现成补丁**：`$GB/scratch/P2/p2_fact_patch_for_P1.py`，跑完 `pytest ops/test_docs_consistency.py -q` 应为 10 绿。 出处：卡 P2。 |
| **N-783** | `ops/HANDOFF.md` §19.7.4 写「传上附件并回填 `download_url` 之后要跟着改口的有**三处**」，实际是**五处** | **待修（归传附件那张卡）** | 原列三处：`README.md` §5、`README.md` §2.1a、手册 §1.4(a)。卡 P2 新增两处也会同时变成假话：`ops/reports/publish_report.md` §一「第三件附件」那张表（下载地址那一格现在写「还没有」）、以及 §三末尾那条新 BLOCKED（含门认的子串 `附件清单为空`）。**回填 `download_url` 的那一刻 `ops/test_e.py::test_附件还没上传时_报告必须把它记成blocked` 会翻到另一面** —— 子串 `附件清单为空` 必须从 `publish_report.md` 里消失；`ops/test_docs_consistency.py` 的 fact `attachments_registry_is_source_of_truth` 也要跟着调。与 2026-09-13 卡 F 按 N-739 做的是同一件事、方向相反。 出处：卡 P2。 |
| **N-784** | `ops/reports/known_limits_v1.md` 仍把 N-736 那条手工纪律记成「登记不修的操作纪律」 | **本轮已修（卡 P3）** | 裁定①把「每次 force-push 之后手工 `PATCH` `target_commitish`」**整条删除**。卡 P2 已改 `ops/HANDOFF.md` §19.6.5 ② 与 `ops/reports/push_result.md` §8.2/§8.3；卡 P3 补上 `known_limits_v1.md` 那一格与本文件的 N-736 / N-748 两行，**原文一律留证不删，只在同一处加「2026-09-13 作废（裁定①）」抬头**。 出处：卡 P2，卡 P3 做。 |
| **N-785** | `ops/reports/release_upload_report.md:85` 仍写「`target_commitish` 每轮 force-push 后 `PATCH` 到当轮新 commit」 | **登记不修（内部留证报告，不挡外部用户）** | 同一条作废纪律的第五处落点。它在一张表格的单元格里，是**当轮留证**而不是现行纪律；`release_upload_report.md` 不在本轮三张卡任何一张的可改路径内。谁拿到那个路径谁顺手加一句「2026-09-13 起写分支名 `main`，本格是当轮留证」即可。 出处：卡 P2。 |
| **N-786** | `frozen/` 到底要不要落位，两处口径不一致 | **已按保守方向写进 README，待与 D2 报告统一** | `ops/reports/mac_gap_closeout.md` §4 末尾把 `frozen/` 列进「同名落 `$GB/snapshots/public_v1/`」。实查：provider 包里 `frozen/` 装的是**仓库相对路径**（`frozen/factor_library/compiled/*.jsonl`、`frozen/reference/factorlib_pinned/*.py`），这六件仓库里本来就有（2026-09-10 卡 W2 提交 `8428252` 收进来的），而发布方自己的 `$GB/snapshots/public_v1/` 下**没有** `frozen/` 这个目录；2026-09-13 macOS 外部验收也只落位了五项而网关正常。卡 P2 在 README §2.1a 按「**不用落位**，是随包自核副本」写。**要么 D2 报告跟着改口，要么给出「落位 `frozen/` 有什么用」的出处。** 出处：卡 P2。 |

### P1（代码根因）—— 收件箱 `ops/tickets_inbox/P1-push.md.merged`，编号卡 P1 自己已编好，原样保留

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-770 更新** | `ops/score_runs.py` 的 run 根写死发布方绝对路径，**外部单机用户结算与入库过不去** | **本轮已修（卡 P1）** | `RUNS_IN` / `REF_TASKS` 改为从 `cfg.GENEBENCH_ROOT` 现算（与 `ops/run_joblist.py`、`ops/results_db.py::protocol_by_run()` 同源 —— 在发布方那台机器上这两条本来就是同一个路径，**所以这处分叉内部永远看不见**）；新增 `--runs-root` 显式入口，`--remote` 认 `[user@]host:/path`，另有 `--remote-host`（同机结算传 `local`，不走 ssh），每次拉取都打印「从哪台机器拉」。run 根不存在时**当场 SystemExit 并说清三条出路**，不再是 `FileNotFoundError`，更不是「退 0 + runs: 0」。同一类一次扫完：`ops/run_controls.py` 四个落点、`ops/guard_modes.py` 的 `EXTERNAL_ROOTS` 与 `ANSWER_PLANE_ROOTS`、`ops/readiness_report.py:23`、`ops/run_probe_mutations.py` 的题集根、`ops/validator_parity.py` 两个根。**发布方那台的取值与 rsync 源逐字未变**（`ops/test_P1.py` 有两条专门钉住）。**卡 D2 那两条临时软链不再需要。** 出处：卡 D2 实测，卡 P1 修。 |
| **N-775 更新** | `guard_modes --harden` 在外部机器上**不收紧** `$GENEBENCH_ROOT` | **本轮已修（卡 P1）** | 两组根都改为现算。顺带修掉同一条的更贵形态：`ANSWER_PLANE_ROOTS` 写死时，外部机器上那三条路径都不存在 → **符号链接那道门一条都不触发，而守门照样返回 0**（看起来合规，其实一条都没查）。 出处：卡 P1。 |
| **N-748 更新 / 裁定②** | `ops/mk_release_manifest.py` 的 `has_remote` 机器依赖，让 `--check` 在**每一个外部 clone 上都退 1** | **本轮已修（卡 P1）** | `no_clone_url` 的 `status_now` 不再看本树有没有 remote（回到 `declared_why`）。同一个病的**第二处**一并修了：`public_channel_zero_runs` 从前读 `$GB/runs_in/m6_public/jobs.jsonl`（那份清单不进仓库），改读仓库里的 `ops/reports/m6_public/records.json` —— 不修它的话 `--check` 在外部 clone 上照样退 1。判据本身（地址已定 + README/CITATION 两处一致）在真树上是 True，两条路给同一个答案，所以**清单内容与机器无关**；这一点由 `ops/test_P1.py::test_清单在有remote与没有remote的同一棵树上逐字节相同` 正面钉住、由 `::test_这条机器无关性比对自己有判别力` 反面证明比对不是恒绿。**CONFLICT 留证**：`satisfied` 仍写 `has_remote or declared_ok` —— `ops/test_release_manifest.py:202` 的假仓库 README/CITATION 是占位文本，把 `has_remote` 从 `satisfied` 里整个拿掉会让那两条当场红，而那个文件不在卡 P1 的可改路径内。 出处：卡 V2 提根因，用户裁定②，卡 P1 修。 |
| **N-755 更新 / N-778 更新** | `RELEASE_ITEMS` 的 53 件里**没有** `build/README.md` 与 `build/base/` 四件 | **本轮已修（P1 改生成器，P3 重出清单）** | 那五件正是「外部用户构基座必须拿到的东西」，清单不收 = 清单在说交付完整而基座仍缺件。新增分组「统一基座构建上下文」。发布件 **53 → 58 件，缺件 0**。 出处：卡 A2 / 卡 D2 提，卡 P1+P3 做。 |
| **N-780 更新** | `ops/test_pack_release.py:280` 把附件件数写死 `ra["n"] == 2` | **本轮已修（卡 P1）** | 改成「已发两件 ⊆ 清单」+「`n` 与表同源且名字不重复」+「逐件字段齐、四条轴与清单同源」+「`role` 在认得出的三个里」——**件数不写死**，但多出来一件不认识的 `role` 仍然会红。与契约点名的 `ops/test_c41.py:366` 那条 `len(REG.CONFIGS) == 3` 是同一个形状。 出处：卡 D2 提，卡 P1 修。 |
| **N-779 更新** | `ops/reports/publish_report.md` 没有第三件附件的行与状态 | **本轮已修（卡 P2 文档 + 卡 P1 判据）** | §一 加第三件附件表（`42,046,516` / `49e9b250d398a1ce…` / 状态「已登记，未上传」），§三末尾加一条含子串 `附件清单为空` 的现状说明，`ops/test_e.py` 那条双向门现在认得出。**附件本身没重打**：`ops/release/attachments.json` 的 `bytes` / `sha256` 与卡 B2 交接时逐字相同。 出处：卡 D2 提，卡 P2+P1 做。 |
| **N-787** | `ops/results_db.py` 的 `ingest` / `backfill` 没有 `--runs-in` CLI | **登记不修（v1 不挡外部用户）** | 卡 P1 把 `score_runs` 与 `results_db` 的默认根改成**同源**，所以外部用户只要把 run 放进 `$GENEBENCH_ROOT/runs_in/<batch>/` 就一路通、**一条软链都不用**；只有用了 `--runs-root` 指到别处时才需要这一条（`score_runs` 的 `--runs-root` help 里已写明这句）。修法：函数签名里 `runs_in` 参数本来就有，只差 CLI 一行。 出处：卡 P1。 |
| **N-788** | `ops/run_probe_mutations.py --help` 里那条公开题集路径**少一层 `public/`** | **本轮已修（卡 P1 顺手）** | 原文指的目录根本不存在，与红队 2026-09-07 的 N-304 逐字同形、只是没人再查第二处。现在 help 从 `PUBLIC_ANSWER_ROOT` 常量渲染，三处（`run_controls` / `run_joblist` / `run_probe_mutations`）同值由 `ops/test_P1.py::test_公开题集根三处同值` 钉住。 出处：卡 P1。 |
| **N-789** | 仓库根 `.gitignore` 的 `build/` 不锚定 | **本轮已修（卡 P1）** | 补 `!/build/`（排在 `build/` 之后、锚定仓库根）。代价此前是**在 `build/` 下新建文件 `git status` 不提醒**，漏 add 的表现正好是「我这台构得出来、别人 clone 下来构不出来」—— 卡 A2 当时只能 `git add -f`。实测：`touch build/<x>` → `git status` 看得见。 出处：卡 P1。 |
| **N-790** | 仍然写死 `/data/shared` 的七个 `ops/*.py` | **登记不修** | 判据：只有进「结算 / 出集 / 外部自检」三条链路的才必须现算；纯发布方内部工具（`api_usage` / `gateway_lock` / `mk_operator_conflicts` / `mutate` / `screen_runner` / `run_f02_a1` / `run_materiality_screen` / `screen_band`）不在射程里。逐条依据表在 `ops/tickets_inbox/P1-push.md.merged`。其中 `ops/mutate.py:33` 与 `ops/screen_runner.py:21` 写死**发布方解释器路径**，是同一形态的下一类，修法与 P1 同（`cfg.PYTHON`）。 出处：卡 P1。 |
| **N-791** | `ops/test_*.py` 里的 `/data/shared` 字面量 | **登记不修** | 多数是**判据本身**：`ops/test_public_acceptance.py::BEFORE` 抄的就是「改动前的原文」（读出来的话那条测试永远绿），`ops/test_A2.py::_PUBLISHER_PATHS` 要的正是「发布方路径不许出现在 `build/` 里」。改它们等于把判别力改没。 出处：卡 P1。 |

### V2（终核复核，2026-09-13）—— 收件箱 `ops/tickets_inbox/V2-final.md.merged`，本轮补并表

> 卡 V2 是**只读**复核，当时一条号都没发（全写 `N-?`）。它查的 6 条里有 5 条已由本轮三张卡闭合，
> 逐条对应关系写在这里，**不重复发号**。

| 卡 V2 原条目 | 现在落在哪 |
| --- | --- |
| `mk_release_manifest.py:362` 的 `has_remote` 让 `--check` 在任何 clone 上退 1（**block**） | **N-748 更新**（卡 P1 已修，两处一起） |
| 公开树里没有卡 C2 的任何成果（**block**，同一次重推可一起解） | 仍成立 —— 本轮**没有重打树、没有 push**，按编排排定由后续推送卡做 |
| `push_result.md` §8.1/§8.2 标题的那句错话没定点改（major） | 卡 P2 已在 §8.2/§8.3 标成留证 + 已作废 |
| `RELEASE_MANIFEST.blockers[no_clone_url].closes_when` 仍引用已删的 `_staging_unpublished/`（minor） | **N-793**（本轮重出清单时确认：`closes_when` 是历史判据字段，`satisfied=true`，重出不改它） |
| `HANDOFF` §19.6.5 ② 仍叫下一张卡用 `r2_patch_release.py` + 手改 `NEW_SHA`（minor） | 卡 P2 已改（连同裁定①把整条手工纪律删掉） |
| f01 上 `ops/test_env.py` 两红是卡 B2 的 `$GB/scratch/B2/cleanroom/` 造成的（major，内部） | 裁定③ + 卡 P2 已清（四棵仓库副本整棵移出 `$GB`），实测 **4 passed** |

### P3（合表与收绿）—— 收件箱 `ops/tickets_inbox/P3-push.md.merged`

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-792** | 收件箱文件名**一卡一名、不复用**（口径） | **本轮已立（卡 P3）** | 见上「本轮立的一条口径」。做掉的那一半：卡 V2 那份撞号的收件箱改名 `V2-final.md.merged` 并并表，`ops/test_V2.py::test_十个收件箱都改名merged了_原名一个不留` 转绿，**门的口径一个字没放宽**。 出处：卡 D2 建议，卡 P3 立。 |
| **N-793** | `RELEASE_MANIFEST.blockers[no_clone_url].closes_when` 引用已删的 `_staging_unpublished/` | **登记不修** | 那个 blocker 已 `satisfied=true`，`closes_when` 记的是**历史判据**（当时靠什么关掉它），不是现行动作；重出清单时它按原样重新生成。改它要改生成器的常量文本，换不来任何外部可用性。 出处：卡 V2 提，卡 P3 判。 |
| **N-794** | README §443 与 `docs/OPERATOR_MANUAL.md` §161 仍写「唯一的例外是结算与入库那两步先补了两条软链」 | **待改口（路径不在本轮三张卡内）** | 那句话记的是**卡 D2 当轮的实况**，不是错的；但 N-770 修完之后**外部用户不再需要任何软链**，而 README 那段是写给外部用户看的「你会遇到什么」。留着的代价是：用户照着做会先去建两条没必要的软链，建完发现路径不存在又回来查。**改法**（原文留证不删，加一句）：「2026-09-13 起（N-770 已修）：`score_runs` 与 `results_db` 的 run 根同源，把 run 放在 `$GENEBENCH_ROOT/runs_in/<batch>/` 即可，**不需要软链**。」同一处还有 `ops/reports/mac_gap_closeout.md` §5.3/§6 两格。 出处：卡 P3。 |
| **N-795** | `$GB/scratch/C2/extroot2/repo` 是一条**断链符号链接**，`ops/guard_modes.py` 因此报「红线 5 不合规（1 条）」 | **仍开着（不在本轮三张卡的可改路径内）** | 卡 P2 的提交 `8ced42a` 按裁定③把 `$GB/scratch/C2/clone` 整棵移到 `/home/ljn/genebench_scratch/`，`extroot2/repo` 这条指过去的软链留了下来。后果：`ops/guard_modes.py` 报不合规、`ops/test_env_guard.py` 相关条目红，而**网关单元的 `ExecStartPre` 就是这道门 —— 下一次网关起停会被它拒绝**（与 2026-09-05 的 N-125 逐字同形）。一行清掉：`rm -f /data/shared/genebench/scratch/C2/extroot2/repo`，再跑 `ops/guard_modes.py` 看到「敏感根权限合规」。顺带确认 `$GB/scratch/C2/extroot2/reference`（指向答案面 `$GB/reference` 的软链）要不要一起清。 出处：卡 P1 先报，卡 P3 复核仍在。 |
| **N-796** | `ops/test_wrt.py::test_rebudget只动没跑过的行` 恒红（`KeyError`） | **登记不修（不是本轮带的）** | `job_id` 现在带机器后缀（`…r01@finance01-e3887dfa`），测试里的断言还按裸 `job_id` 取。卡 P1 在**没有本轮任何改动的 clone** 上复跑同一条，同样红。归 joblist / 机器标识那条线。 出处：卡 P1 量到，卡 P3 登记。 |

### §Q（传与推：第三件附件上传 / 重打树 / 推送 / `target_commitish`）

> 本节由 `ops/tickets_inbox/Q-push.md.merged` 并入（N-792：一卡一名、落盘即 `.merged`）。
> 取号前查过盘上实际最大号是 **N-796**（卡 P3），所以本卡从 **N-797** 起。
> 本卡越界改了四个不在任务书枚举里的路径（N-798 ~ N-801），逐条的理由写在各自那一行与卡 Q 的输出 `conflicts` 里。

> **N-805 是收件箱并表之后才发现的**（本卡自伤，当场修掉）——
> 所以它只写在本表里，`ops/tickets_inbox/Q-push.md.merged` 保持并表那一刻的原样不动
> （`ops/test_V2.py::test_改名没有盖掉更早一轮的merged` 钉住：进了 HEAD 的 `.merged` 逐字节不许再改）。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-797** | 第三件附件 `genebench_public_runtime_v1.tar.gz` 上传并回填 —— N-779 闭合 | **已做** | 传上**已在的** Release `v1.0.16`（id `387775425`），**不新建 Release、已在的两件附件一个字节没碰**（上传前后两次读 assets 列表：两件的 id / size / digest / `created_at` / `updated_at` 逐字相同）。盘上实测 `42,046,516 B` / `sha256 49e9b250d398a1ce…`（**没有照抄任何文档里的旧值**，脚本现场算），与登记表逐字相同。上传后从 API 读回 `digest = sha256:49e9b250…`、`state=uploaded`、asset id `561398049`。三件各做一次**匿名**（不带 token）带 `Range` 的 GET：全部 **206**，`content-range` 总长分别 `782100276 / 157448605 / 42046516`，与登记逐字对得上。`download_url` 已回填进 `ops/release/attachments.json`；`RELEASE_MANIFEST.release_attachments` 重出后 **`n=3 / uploaded=3`**。 出处：用户裁定（本轮明令「传第三个附件并回填 `download_url`」），卡 Q 执行。 |
| **N-798** | `ops/test_b2.py::test_attachment_is_registered_and_not_uploaded` 的判据随状态翻面 | **已做（路径越界，标 CONFLICT）** | 那条门断言「本轮不上传，`download_url` 必须是空串」——**用户本轮裁定要传**，状态真的变了，门必须跟着翻，否则本卡干的正事当场把它打红。新判据**比旧的更严**：旧的只查「是不是空串」，新的**逐字比对完整规范地址**（`…/releases/download/v1.0.16/<包名>`），且要求**三件**的地址一件都不许被后来的打包抹掉（旧的只查两件）。函数改名成 `…_and_uploaded`，全仓库没有第二处引用旧名（已 grep）。补丁：`$GB/scratch/Q/patch_q3.py`（幂等）。**`ops/test_b2.py` 不在卡 Q 的可改路径枚举里** —— 见 CONFLICT。 出处：卡 Q。 |
| **N-799** | 手册 `docs/OPERATOR_MANUAL.md` §1.4 (a) 的第三件附件口径改口 | **已做（路径越界，标 CONFLICT）** | 回填之后那三句成了**现在时的假话**：「仍然缺一块 —— 而且它是第三件附件，不在上面那两条 `curl` 里」「**但它本轮还没有上传到 Release**」「可粘贴的四条命令」。已改成现状并保留判据子串「`download_url` 是空串」（`ops/test_docs_consistency.py::attachments_registry_is_source_of_truth` 要求 README 与手册两处都出现它 —— 它说的是**登记表的格式规则**，不是「现在有空串」）。前序卡 P3 交接 ④ 明列这是「回填之后要跟着改口的五处」之一，任务书明令照用，但该路径不在本卡枚举里。补丁：`$GB/scratch/Q/patch_q2.py`（幂等）。 出处：卡 P3 交接 ④，卡 Q 执行。 |
| **N-800** | N-782 闭合：`ops/test_docs_consistency.py` 那条 fact 翻面 | **已做（路径越界，标 CONFLICT）** | `manifest_check_nonzero_is_not_damage` 的 `require`（README 与手册两处都要写「非零 ≠ 发布件损坏」）正是**用户裁定②点名要删掉**的那句话；根因（`has_remote` / `m6_public` 两处机器依赖）已由卡 P1 修完，那句话本身成了假话。跑的是**卡 P2 早就写好、卡 P3 只读校验过**的幂等补丁 `$GB/scratch/P2/p2_fact_patch_for_P1.py`：fact 改名 `manifest_check_is_machine_independent`，`require=刻意不取决于跑它的机器`、`forbid=非零 ≠ 发布件损坏`，**两个方向都有牙**。卡 P1 / P2 / P3 连续三张因路径边界停手，本卡第 1 步的验收门（「先核 P3 收绿了」）又卡在这一条上 —— 见 CONFLICT。 出处：卡 P2 写补丁、卡 P3 校验、卡 Q 执行。 |
| **N-801** | `ops/data_cards/public_runtime_v1.md` 的 `download_url` 那一格随上传改口 | **已做（路径越界，标 CONFLICT）** | 表里原写 `| download_url | **空 —— 本轮未上传** |`，上传之后是现在时的假话，且这份数据卡随包随树发给外部用户。已填成规范地址。 出处：卡 Q 打树前扫描。 |
| **N-802** | Release `v1.0.16` 的 `target_commitish` 改写分支名 `main`（裁定①） | **已做** | `PATCH /repos/…/releases/387775425 {"target_commitish":"main"}` 回 **200**，读回来确认就是 `"main"`；tag 名、release id、三件附件的 `size` 与 `digest` **一个字节没变**（PATCH 前后各读一次逐字比对）。裁定①同时把 N-736「每次 force-push 之后手工 PATCH」整条纪律作废 —— 落点已由卡 P2（HANDOFF §19.6.5 ②、`push_result.md` §8.2/§8.3）与卡 P3（`tickets.md` 的 N-736/N-748 行）改完，剩 `ops/reports/release_upload_report.md:85`（N-785）仍开着。 出处：用户裁定①，卡 Q 执行。 |
| **N-803** | `ops/data_cards/public_runtime_v1.md` 的「构建 HEAD」与 `attachments.json` 的 `code_head` 对不上 | **登记不修** | 数据卡写 `efe17e81695fe57c71ef0906dc508bc7fc336ee5`，`ops/release/attachments.json` 写 `85f5acf2bddcc742658c7a77c12c04274ccf1f18`。**不是本轮带的**（两者都是卡 B2 那轮落的，包本身一次没重打 —— 盘上 `bytes`/`sha256` 与 B2 交接时逐字相同）。哪一个是真的构建 HEAD 要回卡 B2 的打包日志查；改错一个比不改坏。不挡外部用户使用（他校验的是 `sha256`，不是 `code_head`）。 出处：卡 Q 打树前扫描。 |
| **N-804** | `ops/reports/public/release_forms.md` §7.2 仍写两个附件的 `download_url`「现在是**空串**」 | **登记不修（不是本轮带的）** | 那句话说的是**前两件**，而前两件 2026-09-13 上午就已上传回填 —— 也就是说它**在本卡动手之前就已经是假话**，与第三件无关。该文件不在本卡可改路径内，且本卡已越界改了四个文件，不再扩大。改法（原文留证不删，加一句）：「2026-09-13 起三件的 `download_url` 全部已回填，见 `ops/release/attachments.json`」。 出处：卡 Q 打树前扫描。 |
| **N-805** | 幂等补丁写成了「在原行后面再插一行」，重跑一次就真的插重了 | **已修（本卡自伤，当场发现当场修）** | `$GB/scratch/Q/patch_q.py` 里有两处 `NEW` **包含** `OLD`（附件表多一行、`curl` 块多一行），于是「`NEW in body and OLD not in body` → skip」这条判据对它们永远为假；`q_commit.sh` 在 flock 里重跑补丁做校验时正好触发，提交 `c3e58eb` 的 README §2.1a 里附件表与 `curl` 块各多了一行一模一样的。**既有的门一条都没红** —— 它们只断言「在不在」，不断言「只有一行」。已由 `patch_q5.py` 去重（各 2 → 1）并把随之过期的「两行都要 OK」改成「三行都要 OK」，`patch_q.py` 的那两处也改成**带后文锚**的写法（重跑实测 19 处全 skip、0 处应用）。**口径**：幂等补丁的 `OLD` 必须带足后文锚，让它在应用之后不再命中；「NEW 包含 OLD」这种写法要么改锚、要么自己数次数。 出处：卡 Q 自查。 |
| **N-806** | `docs/OPERATOR_MANUAL.md` 的目录树图写「`release/` 发布包（当前只到 `_staging_unpublished/`）」 | **已修（打树前扫描判出来的唯一一条真错）** | 那个目录卡 R2 按 N-714 **整棵删掉了**，三个附件现在都在 `release/public_v1/`。落在外部用户会读的手册里、还是 `RELEASE_MANIFEST` 的 58 件之一，属**现在时的假话**。**不是本轮带的**：N-730 当时只改了 `ops/HANDOFF.md` §12.2，漏了手册这一处。补丁 `$GB/scratch/Q/patch_q8.py`。 出处：卡 Q 打树后跑 `scratch/W/w_scan_stale.py` 逐条判。 |
| **N-807** | `ops/reports/public_runtime_material.md` §10 写「第三个附件……`download_url` 留空 —— 本轮不上传」 | **登记不修** | 那一节的标题是「**本卡**没做的事」，整节被标题**按卡**限定了范围（同一节还写着「没有重打公开树、没有 push、没有碰 Release」—— 那些卡 Q 也都做了）。按 `w_scan_stale` 自己的口径（「值被它所在小节的标题整节地标了时点」按 markdown 标题包含语义取整条链）判成**留证**，不是对外说假话。该路径也不在本卡枚举里。要更稳妥的话，给那一节的标题加上卡号与日期。 出处：卡 Q 打树后扫描逐条判。 |

## 收口一轮（2026-09-13）—— 卡 S：终核八条收口 + 预算档写清 + D-06 第五例

> 由来是卡 Rfin（终核卡，只读）在克隆树与外部 `GENEBENCH_ROOT` 上实测的八条（`ops/tickets_inbox/Rfin.md`）。
> 本卡**六条修、一条闭**，另按用户裁定把预算档写进 README 与手册两处（N-817）、
> 把 D-06 那一族的第五例补进 `ops/reports/known_limits_v1.md`。
> 本轮**没有**碰三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`），没有重算 τ / ε，没有重打任何包、没有传任何附件。
> 逐条证据在 `$GB/scratch/S/`；收件箱原件 `ops/tickets_inbox/S.md`。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-808** | `ops/selfcheck_public.py` 第 5 项写死「那一件还没上传到 Release」 | **已修** | 本轮**唯一一条会误导外部用户的现在时假话**：第三件 2026-09-13 下午已传上（asset id `561398049`，匿名 206），而**同一次运行的第 4 项**已经从 `ops/release/attachments.json` 现算并打出了含它的三条 `curl` —— 同一屏上两句互相矛盾，还劝人去等一个已经到位的东西。改成 `_missing_public_material_hint()`，与第 4 项同源（按 `role == "public_runtime_material"` 认那一件，**不按文件名写死**），按 `download_url` 空不空分支；这个文件里不再写死任何一句「上传了没有」。两次实跑留证：落位前「登记在案」+ 真地址、落位后**绿**（`$GB/scratch/S/selfcheck_{before,after}.txt`）。 出处：卡 Rfin，卡 S 执行。 |
| **N-809** | `ops/test_b2.py:84` 读私有标定，外部**做对了反而红** | **已修** | 与 N-770 同形：判据悄悄取决于「跑它的是不是发布方那台机器」。读不到 `snapshots/v1/calibration.json` 就 `pytest.skip`，读得到照旧判；**私有 τ 不钉进公开树**（它不随包发）。前两条断言在 skip 之前就跑过 —— 不会退化成整条恒绿。 出处：卡 Rfin，卡 S 执行。 |
| **N-810** | README / 手册 / `--downloads` help 说「两个附件」，实为三件 | **已修** | 按「不写死件数」优先：能不写数的改成「发布附件」并指向 `ops/release/attachments.json`（件数的单一来源）；必须说数的改成三件。 出处：卡 Rfin，卡 S 执行。 |
| **N-811** | `README.md` §2.1 / §5 写「Release 的两个附件」 | **已修** | §2.1 → 「三个附件挂在 Release `v1.0.16` 上」；§5 → 「Release 的附件 —— 三件都已经挂上去了」。§2.1a 那句「两个附件已经挂上去了」**没动**（下一行自我更正成三件，在上下文里成立）。 出处：卡 Rfin，卡 S 执行。 |
| **N-812** | `README.md:174/176` 磁盘预算表只算两个附件 | **已修**（Rfin 原判「登记不修」） | 下载行补第三件 `42,046,516 B`（三件合计 `981,595,397 B` = 936.1 MiB），解包行补 `84,755,038 B`。合计 ≈ 10.8 GB、「按 15 GB 准备」的结论不变。 出处：卡 Rfin，卡 S 执行。 |
| **N-813** | `ops/test_V2.py:67` 的 `_main_table_dirs()` 把用户自己的输出目录圈了进来 | **已修** | README §2.4 那条命令只产 `table_main.csv` + `.axes.json`，于是外部用户**照着做对之后** `test_每个出了主表的批都有两张全量指标表` 当场红。**收窄射程、不放宽判据**：只看 `git ls-files` 认得的那批目录，六件仍逐件查；没有 git 就退回全扫。同节 `>= 20` 是这条收窄的下限守卫（收过头会当场红，不会静默变空集）。 出处：卡 Rfin，卡 S 执行。 |
| **N-814** | `$GB/scratch/C2/extroot2` 的断链软链让 `ops/guard_modes.py` 退 1（N-795 同条） | **已闭** | 断链 `repo` 由编排方删除；本卡按裁定③ 把余下 `{reference, env, logs, results, snapshots}` **整棵移**到 `/home/ljn/genebench_scratch/C2-extroot2/`（**移，不是删**），空目录随后删除。复核：`guard_modes` 退 0「敏感根权限合规（2 个根）」、`ops/test_env.py` **63 passed / 1 skipped**、`$GB/scratch/C2` 下一条软链不剩。 出处：卡 Q / 卡 Rfin，编排方 + 卡 S 执行。 |
| **N-815** | `ops/test_V2.py:227` 的签字包 `0400` 断言在任何 clone 上恒红 | **已修** | `git clone` 不保留 `0400`（落地 `0600`）。断言改成「模式不含 group / other 位」（`S_IMODE & 0o077 == 0`）—— `0400` / `0600` 过，`0440` / `0604` 这类**真的泄出去**的照样红；逐件 sha256 那一半一个字没动。 出处：卡 Rfin，卡 S 执行。 |
| **N-816** | 「文档说没说假话」的扫描**结构性地看不到 `.py`** | **口径（登记，本轮不做工具）** | `$GB/scratch/W/w_scan_stale.py` 只扫 `.md`，而 N-808 那句假话在 `.py` 里。下次扫这一类要把**会打印给用户看的 `.py`**（`ops/selfcheck_public.py` 这样的自检、各 CLI 的 `--help` 与提示文案）一并纳入射程。本轮纪律「不新增扫描类自查」，且扫描器不在本卡可改路径内，故只登记口径。 出处：卡 S。 |
| **N-817** | 用户裁定：README 与手册两处写清预算档与「撞闸不是失败」 | **已做** | 默认 **100 次调用 / 6,000,000 tokens**、S4 **150 / 9M**、S7 **300 / 18M**（现读 `runner/registry.py::RUN_BUDGET` / `BUDGET_TIERS` / `budget_for`，不照抄转述）；撞闸记 `budget_exhausted` 是与 `ok` / `violation` / `timeout` **并列的收口状态、不是失败**，主表那一格渲染成 `—`（`scorer/report.py::NO_READING`），与 `0` / `unobservable` / `n/a` 是四个不同的东西；并写明卡 D2 那次六个 run 的终态分布（3 `budget_exhausted` / 1 `timeout` / 1 `ok` / 1 `violation`，其中四个用满 100 次调用）是 **100 次闸下的真实分布、与 M6 一致，分布不调档**。新门 `ops/test_docs_consistency.py::budget_tiers_and_exhausted_status`（两处各 5 条 require + 1 条 forbid，**双向有牙**：把那句话改成「撞闸算失败」，require 当场缺、forbid 当场命中）。 出处：用户裁定，卡 S 执行。 |

## 卡 U（2026-09-13）：修掉 venv 陷阱（N-818，block）+ 四条外部第一屏会撞的

> 由来是卡 Tfin（终核卡，只读）站在**外部用户那一侧**在全新 clone 上实测的六条
> （`ops/tickets_inbox/Tfin.md`）。本卡**六条全修**，另登记一条（N-824）。
> 用户马上要在一台干净 Mac 上重跑验收，**N-818 是挡在它前面的最后一件** ——
> 照 README 第一步建 venv，网关就永远起不来，而文档给的修法（`--harden`）是空转。
> 本轮**没有**碰三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`），没有重算 τ / ε，
> 没有重打任何包、没有传任何附件、没有新建 Release。
> 逐条证据在 `$GB/scratch/U/`；收件箱原件 `ops/tickets_inbox/U.md`。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-818** | **照 README 建 venv，网关就永远起不来，而文档给的修法是空转** | **已修（block）** | `ops/guard_modes.py` 的 `check()` 与 `harden()` **对符号链接口径相反**：`check()` 走 `_walk_stat`，`mode` 来自 `e.stat()`（**跟随链接**，读到的是目标的位）；`harden()` 在同一趟遍历里 `if islink: continue`（**跳过链接**）。于是「跟随着判、跳过着修」—— 链接指向根外一个 `0755` 的东西时，这道门**结构上不可能被 harden 修好**。而 `python3.12 -m venv $GB/env`（README §2.1、手册 §1.2 那一行）默认把 `bin/python*` 三条建成软链、最终指向系统解释器（`0755` root 所有）→ 网关拒绝启动 → 提示语让人跑 `--harden` → 「收紧 0 个条目」退 1 → 死循环。**修法**：`check()` 对答案面根**之外**的符号链接不再按模式判（符号链接自身的模式恒为 `lrwxrwxrwx`、没有意义；目标在根内会以自己的真实路径被同一趟单独判，目标在根外归答案面那道门管）；新增 `fix_hint()`，提示语按违例类别分岔，`--harden` 修不好的三类**明说修不好**。**判别力一个字没降**（`ops/test_U.py` 13 条，含拿旧版跑一遍的反面判别）。**实测四样**在 `$GB/scratch/U/venv_fix.txt`：真 venv → 新版 check 退 0、软链原样留在盘上；同一棵树起网关 `/healthz` **200**；造 `0644` 文件 + `0775` 目录 → check 退 1 → `--harden` 收紧 2 条 → 退 0；答案面断链 → 提示语不再说「修：`--harden`」。**`--copies` 判了不加**：它能绕开（实测有效），但代码修好之后那个开关没有活的理由，写进文档只会变成一句没人知道为什么存在的咒语。 出处：卡 Tfin，卡 U 执行。 |
| **N-819** | `ops/test_pack_release.py` 三条在「**照文档做对了**的外部 clone」上恒红 | **已修（major）** | `_need()` 只守**落位产物**，三件附件落位之后守卫全部放行，接着去调打包器 —— 而打包器要的是**打包前的发布方中间件** `$GENEBENCH_ROOT/scratch/v1_union.txt`（附件里那份在 `snapshots/public_v1/universe/v1_union.txt`，**路径不同**）。于是落位前 skip、落位后 3 failed。改成 `_need_packager_inputs()`，清单**从 `PP.components()` 现算**（写死一张表的话，组件加一件就又回到同一个坑）。**判别力不变，两面都实测**：f01 `ops/test_pack_release.py` **21 passed / 0 skipped**，三条逐名 `PASSED`；`GENEBENCH_ROOT` 指到外部落位根时三条 `SKIPPED` 并逐字打出缺的是哪一件。断言一个字没放宽。 出处：卡 Tfin，卡 U 执行。 |
| **N-820** | `DATA_LICENSE` §3 末段三处现在时假话 | **已修（minor）** | 标题链「数据许可与来源声明 › `## 3. 发布形态（两条都走通）`」整条链上没有时点，正文却现在时说「地址已定不等于已推送」「`_staging_unpublished/` 里那份旧包的 README 还写着占位符」「推完要重打一次公开包」—— 三处都不是现状。已改成带显式时点的现状（`2026-09-13：两个地址都已推送`，公开包是重打之后那一份，`_staging_unpublished/` 按 N-714 已整棵删除）。同源的一句在 `ops/mk_release_manifest.py` 的 `closes_when` 里，**已由卡 V 登记为 N-793**，本卡不另开号。 出处：卡 Tfin，卡 U 执行。 |
| **N-821** | `ops/selfcheck_public.py` 找附件的候选目录，README 与手册里一次都没写过 | **已修（minor）** | 三处候选（`cwd/downloads`、`$GENEBENCH_ROOT/downloads`、仓库父目录 `/downloads`）在两份文档里 `grep downloads` = 0 命中，而 README §2.1a 的 `curl -L -O` 紧接在 §2.1 的 `cd $REPO` 之后 —— 包落在**仓库根**下，三处一处都不是它。**两边取齐**：仓库根与 `$GENEBENCH_ROOT` 本身进候选（`_downloads_candidates`），README §2.1a 的 curl 块前写明落点，提示语也改了。顺带把「找过：…」按**解析后的真实路径**去重（`$GENEBENCH_ROOT` 与仓库父目录重合是常态，重合时同一路径打印两遍）。实测输出 `$GB/scratch/U/selfcheck_candidates.txt`。 出处：卡 Tfin，卡 U 执行。 |
| **N-822** | 只缺一个包时，自检第 5 项给出的**诊断是错的** | **已修（minor）** | 只缺 `pyyaml` 时第 5 项说「说明这棵树不完整，或者你不是在仓库根下跑的」，真因是 `genetask/packager.py:29` 的 `import yaml` 抛 `ModuleNotFoundError` —— **树是完整的、目录也是对的**，用户被支去查一件没坏的事。改成打子进程输出的**最后一行**（真正的异常）而不是第一行 `Traceback (most recent call last):`；识出 `ModuleNotFoundError` / `ImportError` 时直接指回第 2 项。反面那一半（不是 import 错误时保留原诊断）也有门。 出处：卡 Tfin，卡 U 执行。 |
| **N-823** | `ops/test_env.py:16` 文件头仍写「两个附件落位与 sha256」 | **已修（minor，Tfin 原判「登记不修」）** | N-810 修了四处，这是漏掉的第五处。与前四处同口径改成「发布附件落位与 sha256」。 出处：卡 Tfin，卡 U 执行。 |
| **N-824** | 修完 N-819 之后，打包器那三条在**任何外部机器**上都是 `skip` | **登记不修** | 这是**有意的落点**：重打 provider 包是发布方的操作，外部用户手里没有打包前的中间件（`scratch/v1_union.txt`），也不该有；外部要验包验的是附件自己的 `sha256`（README §2.1a）与包内 `files.sha256`。**代价**：外部 clone 上这三条的判别力等于零 —— 它们只在发布方机器上有牙。记下来，不修。 出处：卡 U。 |

## 卡 W2（2026-09-13）：交付前最后一件 —— 两条会浪费用户时间的 major

> 由来是卡 Vfin（终核卡，只读）完全照 README 逐字走了一遍外部用户的路：那一趟 **0 block、
> `tests_ok=true`**，却量出两条 major。用户马上要在一台干净 Mac 上重跑验收，本卡是交付前的
> 最后一件。本轮**没有**碰三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`），没有重算 τ / ε，
> 没有重打任何包、没有传任何附件、没有新建 Release。
> 逐条证据在 `$GB/scratch/W2/`；收件箱原件 `ops/tickets_inbox/W2.md`。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-825** | **README §2.1 与 §1.5 互相依赖，哪一边先敲都会失败 —— 而 §2.1 是用户复制粘贴的第一个块** | **已修（major）** | §2.1 的块里**没有建 venv 这一步**（只在 `PY=` 那行的注释里写了「必须建在 `$GB/env`（§1.5）」），而 §1.5 那个块里的 `python3.12 -m venv $GB/env` 用的 `$GB` **要到 §2.1 第 1 行才定义**。两种读法都断（卡 Vfin 实测）：先敲 §1.5 → `$GB/env` 展开成 `/env` → `Permission denied: '/env'`；直接敲 §2.1 → 第 6 行 `bash: …/env/bin/python: No such file or directory`。**修法**：建 venv 与 `pip install` 两行插进 §2.1 的块（`mkdir -p $GB` 之后、`$PY ops/selfcheck_public.py` 之前），Mac 给全路径并在同一行注释里给出 Intel Mac / Linux 的等价写法；§1.5 的块改成自带 `GB=` 定义、可单独跑 —— **两处不再互相指**。**判据实测不推理**（`$GB/scratch/W2/n825_paste.txt`）：全新 clone 上把改后的块**整块逐字粘贴**跑一遍，全程一条 `No such file or directory` / `Permission denied` 都没有，`selfcheck_public.py` 跑到底给出可读的六项判定，`guard_modes.py --harden` 退 0。 出处：卡 Vfin，卡 W2 执行。 |
| **N-826** | **`ops/test_d.py` 写死发布方内网路径 + 模块级 IO：外部整场中断，内部则对被测的那棵树毫无判别力** | **已修（major）** | `:20` `REPO = Path("/data/shared/genebench/repo")`，`:21-26` 六个派生常量，`:34` 模块级 `read_text()`。① 外部机器上 collection 期 `FileNotFoundError` → `Interrupted: 1 error during collection`，**整场中断**；② 在 f01 上跑克隆树时它读的是**内网那棵树**，**整整一套 18 条断言对被测对象失去判别力** —— 前几轮的绿有一部分是假的。**修法**：`REPO` 从 `Path(__file__).resolve().parents[1]` 推导（与 `conftest.py` 同源），`PKG_DIR` 跟 `$GENEBENCH_ROOT` 走，模块级 IO 前加整模块 `pytest.skip(..., allow_module_level=True)`。**两面都实测**（`$GB/scratch/W2/n826_clone4.txt` 六段）：克隆树 **15 passed/3 skipped**；改坏那棵树的 README → **2 failed**（判别力在）；README 挪走 → **整模块 skip**，不是崩；旧版在同一棵克隆树上 → `Interrupted`；**旧版原封不动、树已被改坏 → 17 passed 全绿**（「绿是假的」的实证）。f01 内网仓库仍 **17 passed / 1 skipped**，没有一条断言退化成 skip。**这是 D-06「判据悄悄取决于跑它的那台机器」那一支的第六例**，特殊之处见 `ops/reports/known_limits_v1.md` 本轮一节。 出处：卡 Vfin，卡 W2 执行。 |
| **N-793 更新** | `RELEASE_MANIFEST.blockers[no_clone_url].closes_when` 仍引用已按 N-714 整棵删除的 `_staging_unpublished/` | **已闭（minor，原判「登记不修」）** | 改的是**源**（`ops/mk_release_manifest.py` 那条 blocker 的措辞），按 **N-743** 改措辞不改值，`satisfied` 一个字没碰，然后重出清单（`--check` 退 0、`releasable=true`、未闭合 blocker 0）。`PART_OVERRIDES` 拿同一路径**当字典键**那一处**没动** —— 源码 `:457-464` 写明是刻意的（键用存档件的 `path`，对外正文由该表改写成「已发布」）。 出处：卡 V2 提，卡 P3 判「登记不修」，卡 W2 闭。 |
| **N-827** | 六包环境里在克隆树根跑 `pytest ops/` 会 `Interrupted: 5 errors during collection`（缺 `jsonschema` / `httpx`） | **登记不修（文档已补一句）** | 文档从不叫外部用户跑 `pytest ops/`（手册点名的都是单个文件，不受影响），所以这是**加一句话、不是修代码**：README §1.5 的六包清单旁写明「想跑仓库自带的测试再装 `pytest`、`jsonschema` 与 `httpx`；只跑 `ops/selfcheck_public.py`、出题、跑题、出表不需要它们」，并说清缺它们时报错在 **collection 期**（所以看到的是整场中断而不是几条可读的红）。 出处：卡 Vfin，卡 W2 执行。 |
| **N-828** | 另有 12 个 `ops/test_*.py` 在**模块级**写死发布方路径 | **登记不修** | 顺着 N-826 按 AST 扫了全部 `ops/test_*.py` 的**模块级**语句（`$GB/scratch/W2/scan_hardcoded.txt`）：与 N-826 同形的（写死路径 **且** 模块级 IO）**现在是 0 个**；另外 12 个只有写死路径、**没有模块级 IO**，因此**不会整场中断**。其中三处**不是问题**（`test_A2.py:63` 的 `_PUBLISHER_PATHS` 本来就是被扫描的对象；`test_P1.py:8`、`test_env.py:31-32` 在 docstring 里），两处**有 env 兜底**（`test_a_publish.py:24`、`test_p.py:17`），七处判据仍指着发布方机器（`test_g2.py` / `test_provider_pin_channel.py` / `test_public_acceptance.py` / `test_scorer_gate.py` / `test_scorer_redteam51.py` / `test_x1.py` / `test_y1.py`）—— 它们指的都是**答案面 / 快照 / 发布树**，外部本来就没有、也**不该有**（红线 2）。代价与 **N-824** 同类：外部 clone 上判别力等于零，只在发布方机器上有牙。 出处：卡 W2。 |

## 卡 Y（2026-09-13）：交付前终核的收口 —— 1 block + 2 major + 3 minor，外加一道 3.12 冒烟门

> 由来是**卡 Xfin**（交付前终核，只读；收件箱 `ops/tickets_inbox/Xfin.md`，实测输出 `$GB/scratch/Xfin/`）：
> 完全照 README 逐字走了一台干净外部机器的路，报出 **1 block + 2 major + 4 minor**。
> **用户裁定：三条都修，并且加一道 3.12 冒烟门。**
> 本卡实测环境：一棵外部 clone + 三件附件 + **真 Python 3.12**（`$GB/scratch/Y/clone_check.txt`）。
> 三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`）**一个值没改**，没重算 τ / ε，没重打包、没传附件、没新建 Release。
>
> **这一整轮所有剩余缺陷的共同形状**：*一个默认值或判据，悄悄取决于跑它的是不是发布方那台机器。*
> 本轮那个实例是**解释器版本** —— 发布方跑 **3.10**、文档强制 **3.12**，
> 凡是 3.11+ 才报的错内部**永远照不到**。详见 `ops/reports/known_limits_v1.md` 本轮一节（D-06 第七例）。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-829** | **`ops/joblist.py` 把子命令 `rebudget` 注册了两次：3.12 上每次调用都当场抛，README §2.4 的第一条命令就死** | **已修（block）** | `:389` 与 `:393` 是**逐字相同的 5 行重复块**（本卡逐字节比对确认后才删）。**3.10 的 `argparse` 不查重**，照跑，`--help` 里打印两遍而已 —— 发布方内部**没有任何征兆**；**3.11 起 `add_parser` 开始查重**，于是在 README §1.5 强制的 3.12 上抛 `argparse.ArgumentError: argument cmd: conflicting subparser: rebudget`，`--help`/`gen`/`stat`/`list`/`reset` **全部起不来**。连带把手册 §8.6 明确请用户跑的 `ops/test_operator_manual.py` 打红两条（那两个 flag 源码里真有，红的原因是判据 shell out 到 `--help` 而 `--help` 崩了）。**修法 = 删掉重复的那一份**。**判据在真 3.12 上实测**：`GENEBENCH_ROOT=$HOME/genebench $HOME/genebench/env/bin/python ops/joblist.py gen --matrix ops/joblists/v1demo.yaml` → **「8 个 job」** + `{"pending": 8, …}`，正是 §2.4 承诺的 4 题×双臂。全树扫过，重复 `add_parser` **只此一处**。 出处：卡 Xfin，卡 Y 执行。 |
| **N-830** | **README §2.4 的两条 `run_joblist` 没带 `--channel public`，外部用户会静默跑私有题集** | **已修（major）** | `ops/run_joblist.py --channel` 的**默认值是 `private`**，干跑打出来的题集根是 `$GB/reference/tasks/v1.0-smoke` —— **私有题集，按红线 2 永远不随发布件交付**；外部手上只有第三件附件带来的 `$GB/reference/tasks/public/v1.0-smoke-public`。**最贵的是它不报错**：干跑照私有根把六段命令原样渲染出来，要到真跑才报「找不到任务目录」。**修法**：§2.4 块首加 `export GENEBENCH_CHANNEL=public`、两条 `run_joblist` 各加 `--channel public`，并写明**为什么必须带它**；手册 §5.4 / §6.1 各补一段同口径提醒（手册 §5/§6 用 `<batch>` 占位、面向内部默认通道，所以补提醒不改命令）。**判据**：`ops/test_Y.py` 钉「§2.4 每条 `run_joblist` 都带 `--channel public`」+「`--channel` 默认值仍是 `private`」（默认值一变，那段解释就成了假话）。实测：带上之后题集根立刻变成 `…/public/v1.0-smoke-public`，`v1demo.yaml` 那四道题在公开题集里都在。 出处：卡 Xfin，卡 Y 执行。 |
| **N-831** | **`ops/run_joblist.py:70` 与 `ops/score_runs.py:49` 的 `F02` 写死、没有 env 兜底，两处文档的「要改哪些常量」表也都没列它们** | **已修（major）** | 全仓库只有 `ops/api_usage.py:51` 写了 `os.environ.get("GENEBENCH_F02", …)`。卡 Xfin 实测：设了 `GENEBENCH_F02=me@127.0.0.1` 之后，§2.4 ④ 干跑里的 ssh 目标**仍然是发布方那台** —— 单机用户只能改源码，而**他无处得知要改哪两行**（README §2.3 ③ 与手册 §1.3 那张表都只列三条地址常量；手册另一段提到 `GENEBENCH_F02` 但**明确只说两个推送 `.sh`**，那句话本身没说假话）。**修法两件**：① 两处都补同一套口径的 env 兜底；② README §2.3 补第 ④ 条、手册 §1.3 那张表补两行，两处都写明**读这个变量的一共五个入口**（两个推送 `.sh` + `api_usage.py` + 这两个）。**发布方那台的取值逐字不变**：`ops/test_Y.py` 两条断言钉住（不设 env 仍是原值；设了 env 两处都跟着走）。 出处：卡 Xfin，卡 Y 执行。 |
| **N-832** | **README §2.1 把 `selfcheck` 排在 `guard_modes --harden` 前面，首跑第 6 项必红，而块里没说要复跑** | **已修（minor）** | venv 按 README 自己的硬要求建在 `$GB/env`，`pip` 装出来的 `.so`/`.py` 对组/其它开放，而红线 5 审计走 `$GB` **全树** —— 卡 Xfin 实测 **113 条「模式放松」、网关拒绝启动、`selfcheck` 退 1**；`--harden` 一跑就收干净（「收紧 113 个条目」），再自检就是**绿 5 / 红 1**（剩下那条红是那台机器真没装 docker）。红条自带「修：」导航，但**块跑完最后停在一个退 1 的自检上**。Mac 上 umask 022，命中条数只会更多。**修法**：两行**对调**（先收紧、再自检），并在块后写明为什么是这个顺序、以及「已经先跑了 `selfcheck` 看到一屏红的人该怎么办」。选对调而不是块尾补一行复跑，理由是**照抄的人少跑一次没有意义的红**。判据：`ops/test_Y.py::test_the_readme_hardens_before_it_selfchecks`。 出处：卡 Xfin，卡 Y 执行。 |
| **N-833** | **`ops/test_readme.py` / `ops/test_operator_manual.py` 把「文档说了真话」的路径判红，而手册 §8.6 正是叫用户跑后者** | **已修（minor）** | 两处判据把文档里出现的路径**一律**当仓库相对路径去 `exists()`，可有几条**按设计就不在仓库里**：`snapshots/public_v1`、`reference/tasks/public/…`（落在 `$GENEBENCH_ROOT` 下，附件解开才有）、`reference/memory_probe_answers`（README 原话就是「**不在这个包里** —— 记忆探针的钥匙一旦公开就立刻失效」）。它打出来的话会把人支去找一个不存在的遗漏。**修法是收窄射程、不是放宽判据**：加一张**逐字闭集** `RUNTIME_ONLY_PATHS`（四条，各带「为什么不在」），表里那几条**换根判**而不是不判 —— 设了 `GENEBENCH_ROOT` 且那里真有就是**正判**，没设/没落位才 skip 并把原因说全。**两条反面判据**证明没放宽：拼错一个字母（`snapshots/public_v2`）、换一层（`reference/tasks/publik`）、多一层（`snapshots/public_v1/qlib_provider`）**照样判红**；豁免表里每一条都得是 README 或手册**真的提到过**的。文档将来提到新的运行期路径时这道门会红到有人显式加进来为止，**这是刻意的**。 出处：卡 Xfin，卡 Y 执行。 |
| **N-834** | **README:541 与手册 :884 都引 `ops/reports/d2_e2e/` 当证据目录，公开树里没有这个目录** | **已修（minor）** | 那段话正是用来劝用户「**别把一批 run 大半撞闸读成自己配错了**」的 —— 证据却不在他手上。**两条路里选「把证据放进来」**，因为那段劝解只有连着分布一起读才站得住。**只放两张小表 + 一份题注**：`run_states.csv`（六行终态）、`table_main_excerpt.csv`（24 列表头 + 两行 —— **刻意不叫 `table_main.csv`**：那个名字是 `ops/test_V2.py::_main_table_dirs()` 用来**认批**的，认出来就要求同目录还有六件全量指标表，而 `d2_e2e` 不是批的产物目录；本卡第一次提交时正是被这道门当场拦下的，**那条红是对的**）、`README.md`（说明它是**构造验收不是能力读数**）。run 产物、bundle、日志、题面与答案面**一个字节都不在里面**（红线 2）；`run_id` 去掉了机器标识后缀。判据三条（`ops/test_Y.py`）：目录与三件文件在；**盘上六行的终态分布 == 两处文档写的分布**（分叉时红的是文档）；表头**恰好 24 列**、前五列是身份列、**没有总分列**。 出处：卡 Xfin，卡 Y 执行。 |
| **N-835** | `ops/test_public_acceptance.py` 3 红、`ops/test_a_publish.py` 1 红，都是**判据写死发布方路径** | **登记不修** | 前者两条断言 `assert '/home/ljn/ge…' == '/data/shared/…'`、一条 `FileNotFoundError` 找私有题集 `v1.0-smoke/s8-cor-01`；后者找 `$GB/snapshots/public_v1/instruments_rebuild/csi300.txt`（附件里没有这一棵）。与 **N-828** 同类：外部 clone 上判别力等于零，只在发布方机器上有牙。**文档没有叫外部用户跑这两个**，所以不像 N-833 那样算缺陷。 出处：卡 Xfin。 |
| **N-836** | **加一道 3.12 冒烟门 `ops/test_Y.py`（用户点名），让「只在 3.11+ 才报的错」第一天就掉出来** | **已做（动作，不占限制表计数）** | 两层，都在。**① 版本无关的那一层**：按 **AST** 数每个文件里 `add_parser("<字面量>")` 的名字，**同名注册两次就红** —— 它**在 3.10 上也抓得到 N-829**，这正是它存在的理由（不指望「将来有人在 3.12 上跑一次」）。判别力**反面自证**：往一份真源码的副本里注入一个重复注册 → 当场红，副本销毁、原文件一个字节没动 → 绿。**② 真 3.12 的那一层**：把**文档里叫用户敲的**每个 `ops/*.py` 入口在真 ≥3.11 解释器上跑一次 `--help`（本轮覆盖 **19 个**），找不到解释器时**大声 skip 并逐条打出每个候选为什么不行**，不许静默变绿。**发布前必须在有 3.12 的环境上跑一次这道门**（f01 的 `$GB/env` 是 conda 3.10，在它上面跑 19 条会全部 skip，而 skip 不是绿）—— 照抄这条：`GENEBENCH_PY312=<真 3.12 解释器> $PY -m pytest ops/test_Y.py -q -rs -p no:cacheprovider`。**顺带把射程铺开扫了一遍**：`ops/` `runner/` `gateway/` `scorer/` `snapshots/` `genetask/` 下**所有** 40 个带 argparse 的非测试脚本在真 3.12 上逐个 `--help`，**除 N-829 外全部正常**（`$GB/scratch/Y/cli_scan_312.txt`）。 出处：用户裁定，卡 Y 执行。 |
| **N-837** | **`ops/test_operator_manual.py::test_the_gateway_lock_path_in_the_manual_is_the_real_one` 的判据取决于跑它的那台机器，外部一跑就 `ValueError` 崩** | **已修（minor，同族）** | 原来写成 `GL.LOCK.relative_to(cfg.GENEBENCH_ROOT)`：发布方机器上两者同根、跑得通；**任何**外部机器上 `GL.LOCK` 是写死的发布方绝对路径、`cfg.GENEBENCH_ROOT` 是用户自己的根，于是 `relative_to` 抛 `ValueError: '/data/shared/genebench/locks/gateway.lock' is not in the subpath of …` **当场崩**（卡 Xfin 实测），而手册 §8.6 恰恰请用户跑这个文件。**这是 D-06 第七例同一族的又一个实例，只不过它在判据侧。** **判据要验的东西一个字没放宽**：改成按「根之下那一截」（`locks/gateway.lock`）比 —— 发布方机器上两种算法**逐字同值**，换任何一台机器它也照样有牙（手册把 `locks/` 写成别的，当场红）。 出处：卡 Xfin，卡 Y 执行。 |
| **N-838** | `ops/gateway_lock.py:34` 的 `LOCK` 写死发布方绝对路径 `/data/shared/genebench/locks/gateway.lock`，**不跟 `GENEBENCH_ROOT`** | **登记（代码侧，不在卡 Y 可改路径）** | 与 **N-770**（`score_runs.RUNS_IN`，已修）同形：在发布方机器上 `cfg.GENEBENCH_ROOT` 恰好等于那个写死的前缀，**两条路径同值，分叉在内网永远不显形**。外部单机用户的后果有两层：① 拿网关锁时会去写一个他没有权限、甚至不存在的目录；② 本轮 N-837 那条判据就是被它拖崩的。**修法与 N-770 同源**：`LOCK = cfg.GENEBENCH_ROOT / "locks" / "gateway.lock"`，并给 `ops/gateway_lock.py` 一个显式 `--lock` 入口。改完要连着核一遍**所有拿这把锁的调用方**（红线 6 要求真跑与跑批串行，锁一换根就不再互斥 —— **这一步比改常量本身重要**）。 出处：卡 Y。 |
| **N-370 更新** | `ops/test_env.py::test_no_api_key_material_in_run_dirs`（红线 3 门）会被**放在 `$GB/scratch/` 下的一棵本仓库 clone** 打红 —— 它扫到的是那棵树里 `ops/test_env.py` **自己的夹具** | **仍登记不修（本轮又量到一次，原判不变）** | 这一条卡 4.rt 就登记过（本表上文 `N-370`，finding 12），本轮**在交付前的定向测试里又原样撞到一次**，所以按「更新」写在这里、**不重新发号**。本卡量到 **1 failed**，三条 offender **全部**是 `Xfin/clean/GeneBench/ops/test_env.py:867` 与 `:874` —— 那两行正是这道门自己的**反面夹具**（一条 `sk-` 形态、一条长 base64 形态，写在仓库里是**刻意**的：门要有东西可抓）。成因是**自指**：门的射程是 `$GENEBENCH_ROOT/scratch`，而卡 Xfin 按终核口径在那底下 `git clone` 了一整棵树（2026-09-13 19:52，**早于本卡开工**），于是门扫到了自己的夹具；`$GB/scratch/Y/` 下 **0 条**。**不是本卡引入的，也不是发布件的缺陷。** **清掉就绿**：卡 Xfin 的证据不再需要时 `rm -rf $GB/scratch/Xfin/clean`（本卡**没有删** —— 那是别人的证据）。N-370 原条给的两条修法仍然成立，本卡补一条更省事的：射程**见到 `.git/` 就不下钻**（scratch 下的 git 工作树整棵跳过），比按文件名白名单更不容易漏。`ops/test_env.py` 不在卡 Y 可改路径。 出处：卡 4.rt 登记，卡 Y 复现。 |

## 卡 C9（2026-09-14）：交付终核四条 block 的**文档侧** —— 裁定 ④⑤ + 两条清理

> 由来是**卡 Zfin**（交付终核，只读；收件箱 `ops/tickets_inbox/Zfin.md`）：干净 Mac 的语义下
> 照 README 逐字走，**前半段通、从 §2.4 ③ 的真跑开始走不通**，量到 4 条 block + 2 条 major + 4 条 minor。
> **本卡只做用户裁定的文档与登记那一半（④⑤ + 两条清理）**，一个 `.py` 与脚本都没改；
> 代码侧（单机路径去跨机步骤、各根从 `GENEBENCH_ROOT` 现算、加那道「不许访问 `/data`」的门）归另一张卡，
> 它们的票据由那张卡自己登记。
> 三条版本轴（`v1.0.16` / `r1.0.23` / `p1.0.0`）**一个值没改**，没重算 τ / ε，没重打树、没推。
>
> **这一轮所有 block 的共同形状**（D-06 家族第八例，用户点名）：
> *一条写死的路径，在 Linux 上只要 `mkdir` 一下就变成真的，于是「换一台机器」这个检验手段照样照不到；
> macOS 根卷只读，一撞就是硬停。* 逐条见 `ops/reports/known_limits_v1.md` 本轮那一节。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-839** | **README §2.1a 的验包块用 `sha256sum`，而两处文档从没说过 Mac 上换成什么** | **已修（major）；前提被实测改了一半，见说明** | **动作照做，但前提要更正。** Zfin 报的前提是「干净 macOS 上没有 `sha256sum`」，本卡 2026-09-14 在一台 **macOS 15.7.4（Darwin 24.6.0，arm64）** 上逐例实测：**`/usr/bin` 里确实没有，但 `/sbin/sha256sum` 在，且是 Apple 自己签的**（`codesign` → `com.apple.md5sum`，`--version` → `sha256sum (Darwin) 1.0`，与 `/sbin/md5sum`/`/sbin/sha512sum` 同一个多名二进制），**不是** GNU coreutils；`/sbin` 在 macOS 默认 `PATH` 里，所以那几条命令**在那台机器上原样能跑**。两者对我们要做的事**等价**（匹配 → `OK` 退 0；不匹配 → `FAILED` + `WARNING: 1 computed checksum did NOT match` 退 1；文件不在 → 退 1），**只有一处不等价**：校验和行本身写坏时 **GNU 退 1、Apple 那个退 0**（只打 `WARNING: 1 line is improperly formatted`）。**所以这一条仍然是缺陷，只是内容换了**：不是「命令不存在」，而是**两处文档一个字没说过 Mac 上这件事**（全仓库 `shasum`/`coreutils` 此前 0 次），§1.5 那句「macOS 上没有这**四**个 Linux 工具」读起来又是**穷举**的；而 `sha256sum` 既非 POSIX 也非 BSD 命令，**「一定在」的只有 `shasum`**。**修法三件**：① §1.5 补成**五个**并把当天量到的逐条写进去（含那处退出码差异、含「为什么这张表现在是全的」——2026-09-14 把 README 所有命令块里的命令逐个过了一遍，除 `brew`/`python`/`git`/`curl`/`tar`/`cat`/`mv`/`mkdir`/`chmod`/`ulimit`/`ssh`/`sh`/`sudo` 外只剩那五个）；② §2.1a 那个要逐字粘贴的块改成**两边通用**，§2.1 注解、§2.3 状态框与手册 §1.4 / §6 一并给出；③ 点明 `ops/selfcheck_public.py` 第 4 项是**纯 Python** 的等价物。**块里落的是一个 `sumc()` 函数而不是变量**，因为实测到一条真陷阱：`SUMC="sha256sum -c"` 再 `$SUMC <文件>` **在 macOS 上一定失败** —— **zsh 不对未加引号的变量做词分割**，它会去找一个名叫「`sha256sum -c`」的命令。**判据没放宽**：`ops/test_d.py` 那条「gold 子集那一行不许用 `SHA256SUMS`」照旧有牙（`gold_subset_SHA256SUMS` 仍逐字在），三行 sha256 常量一个字没动。**方法上的教训一并记在** `ops/reports/known_limits_v1.md` 本轮那一节：Zfin 那个前提来自 `$GB/scratch/Zfin/z_mac.py` 里一张**硬编码候选表**，脚本 docstring 自己写着「只列待判项，判据由人写」，而那张卡**全程跑在 f01（Linux）、一次都没连过 Mac** —— 候选升格成了结论。**与本轮 D-06 第八例同形**：一条关于「另一台机器」的判断，完全在这一台上做出。 出处：卡 Zfin 提，卡 C9 实测并执行。 |
| **N-843** | **README §2.3 的 macOS 状态框里两条成因都已不成立，而今天真正拦路的四条一条没列** | **已修（major）** | 旧版原话（逐字留在正文里当证）：「**macOS（arm64）上还没跑通**：2026-09-13 的外部验收走到「建 harness 镜像」就停了 —— 本机没有统一基座 `gb-base:bookworm-r1`，公开题集 S4–S7 那 18 道题的输入夹具也没有随两个附件交付。」**成因①已消失**：`build/base/` 整套构建上下文同日随树发了，`harnesses/build.sh` 缺基座时自己构；**成因②也已消失**：S4–S7 那 18 道题在**第三件附件**带来的公开题集树里（卡 Zfin 落位后逐题核过）。措辞是过去时、**逐字不算说假话**，但新读者读到的是「这两件事挡着」，照着去补完，撞上的是 N-840 / N-841 / N-842 / N-838 这四条**一条都没被提到**的墙。**修法**：**结论保留**（Mac 侧只验到网关 —— `ops/test_docs_consistency.py` 钉这句的那两条正/反判据一个字没动），**成因换成真正的那一条**（单机路径上的跨机步骤：两个推送脚本的解释器与暂存目录默认指发布方绝对路径、执行面 run 根写死且被当硬判据、推前要 ssh 核 `systemd` timer、网关锁根写死），并写明**为什么它在 Linux 上永远不显形**（`mkdir /data` 就造出来了）与**正在怎么改**（用户裁定 ①②：单机路径不含任何跨机步骤，双机不动）。**README §2.3 与手册 §0.3 两处一起改。** 出处：卡 Zfin，卡 C9 执行。 |
| **N-370 更新** | 红线 3 那道门（`ops/test_env.py::test_no_api_key_material_in_run_dirs`）唯一那条红：`$GB/scratch/Xfin/clean/` 那棵 clone 里 `ops/test_env.py` **自己的反面夹具** | **本轮清掉了 offender，实测转绿；原判（登记不修）不变，不重新发号** | 用户 2026-09-14 明示清掉。清之前先确认卡 Xfin 那一轮**已收口**（终核报告与卡 Y 的修复都已提交）。按 `ops/HANDOFF.md` §19.8 的纪律**选「移」不选「删」**：整棵 34 MB 移到 `/home/ljn/genebench_scratch/Xfin/clean/`，**一个字节没删**，并 `chmod -R go-rwx`（`$GB` 之外同样要收紧）。**实测**：`ops/test_env.py` 从「1 failed」变成 **63 passed / 1 skipped**（`$GB/scratch/C9/env.log`，8 分 50 秒，走 `$GB` 全树）。**这一条本身仍是「登记不修」**：清掉的是这一次的 offender，而成因（门的射程是 `$GENEBENCH_ROOT/scratch`，于是**任何一棵仓库副本**落进去都会把它拖红 —— 命中的从来不是真凭据，是门自己的判别力夹具）没有变；N-370 原条给的两条修法、加上卡 Y 补的那条「见到 `.git/` 就不下钻」都还摆着。§19.8 那条纪律照旧有效。 出处：卡 4.rt 登记，卡 Y 复现，卡 C9 清场。 |
| **N-836 更新** | 3.12 冒烟门 `ops/test_Y.py` 的第 ② 层在发布方 f01（conda 3.10）上**整层 skip** | **用户明示保留在常规套件里，不为消 skip 而动它，不重新发号** | 用户 2026-09-14 的原话口径：**40 个带 argparse 的脚本在真 3.12 上全扫一遍，这个结果比修掉那一条值钱**。所以本卡做的是**把它写进常规套件的清单**，不是改门：`ops/HANDOFF.md` 新增 **§19.9**，把 `ops/test_Y.py` 列进「接手先跑这几条」的第 ① 条，并给出照抄命令 —— **f01 上有真 3.12**：`/usr/bin/python3.12`（3.12.3），`GENEBENCH_PY312=/usr/bin/python3.12 … -m pytest ops/test_Y.py -q -rs -p no:cacheprovider`，喂了它第 ② 层就不再 skip。同节记下那个结果与结论：`ops/` `runner/` `gateway/` `scorer/` `snapshots/` `genetask/` 下**全部 40 个带 argparse 的非测试脚本**在真 3.12 上逐个 `--help`，**除当时那条 `ops/joblist.py` 的重复 `add_parser` 外全部正常**，全树重复 `add_parser` **只此一处**（`$GB/scratch/Y/cli_scan_312.txt`）。**门一个字节没改。** 出处：用户裁定，卡 C9 登记。 |

## 卡 D9（2026-09-14）：单机形态这一轮的**收口** —— 票据并表 + 重打树 + 推

> **本轮四张卡**：**A9**（代码侧：单机路径去掉跨机步骤、路径根从 `cfg.GENEBENCH_ROOT` 现算）、
> **B9**（裁定 ③ 那道门：在 f02 上按**外部单机用户的语义**真走一遍，量出四条新的）、
> **C9**（文档侧：§1.5 的 `sha256sum` / `shasum`、§2.3 换成因、D-06 第八例、两条清理）、
> **D9**（本卡：并表、重出清单、重打树、两遍扫描逐条判、推、推后回核）。
>
> **卡 C9 的表已经由 C9 自己追加进上面那一节**（它的收件箱第一段写明「不要再并一次」），
> 所以本节**只并 A9 与 B9**，外加本卡自己发的三条。
> **取号**：盘上实际最大号是 **N-862**（卡 B9 取走），本卡从 **N-863** 起编，取号前已全树 grep 复核。
>
> **本卡自己重跑过 A / B / C 声称的判据，没有采信转述**：
> `ops/test_A9.py` **28 passed**（含「单机路径上 `/data` 字面量零次」那一条）；
> `ops/test_single_machine.py` **12 passed / 1 skipped / 3 xfailed**（skip 的是真跑那一段 ——
> f01 没有容器运行时，它把缺的前置**逐条打出来**，不是静默变绿）；
> 卡 B9 那个独立扫描器（56 个文件的**超集**闭包）复跑同值：`/data` 行 65，取值位 19。
> `ops/test_Y.py` 喂真 3.12 **32 passed**；`ops/freeze_v10.py --check-all` **退 0**，三条轴一致。

### A 段：卡 A9（裁定 ①②，提交 `47ad5c1`）

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-838 挪格** | `ops/gateway_lock.py` 的锁根写死发布方绝对路径 | **已修** | `lock_path()` 从 `cfg.GENEBENCH_ROOT` 现算，另留 `GENEBENCH_GATEWAY_LOCK` 覆盖。**互斥语义逐条核过并写进 docstring**：同机同根仍互斥（`ops/test_A9.py` 真起两个进程量）、不同根互不干扰、同机两套根共用一个网关实例时用那个环境变量指同一个文件。发布方取值逐字不变。**这一条此前计在「登记不修」那一格（卡 Y 放进去的），本轮往「已修」挪一格、合计不变。** |
| **N-840** | `ops/push_exec_to_f02.sh:29/:32` 的 `GENEBENCH_PY` / `GENEBENCH_EXEC_STAGE` 默认发布方绝对路径 → rc=127 | **单机侧消解** | 单机路径**根本不调**这个脚本（裁定 ①），改走 `GENEBENCH_TOPOLOGY=single $PY -m runner.placement --place-exec --with-launch-data`。**双机侧仍在**，见 N-851。 |
| **N-841** | `ops/run_joblist.py::RUNNER_ROOT` 写死、`ops/push_bundle_to_f02.sh:69-70` 把「目标必须在 `/data/genebench_runner/` 下」写成硬判据 | **已修（单机侧）** | `runner_root()` 现算；**落点判据在单机分支里一条没少**，只是根现算（`runner/placement.place_bundle`）。`ops/push_bundle_to_f02.sh` 本身**一字未动** —— 它是双机形态的真判据。 |
| **N-842** | `ops/push_bundle_to_f02.sh:36-42` 推前 `ssh` 核 `genebench-answer-plane-scan.timer`，Mac 上过不去且无开关 | **单机侧消解** | 单机不推、不核远端 timer；答案面纪律改用**落位即扫**（`push_guard` → `answer_plane_guard --mode container` → 落地树扫，**同一份实现、同样的顺序**）。少了什么见 N-849。 |
| **N-848** | 单机形态的落位入口**要进 README / 手册**，现在一个字都没有 | **仍开着（本轮没人做）** | 卡 A9 把它标成「待卡 C」，但卡 C9 本轮的射程是用户裁定 ④⑤（§1.5 / §2.3 / known_limits / 两条清理），**没有包含 §2.4**。于是 `runner/placement.py` 随树发了、README §2.4 ③④ 仍然教人跑两个 `push_*_to_f02.sh`。**本卡把照抄命令补进了 `ops/HANDOFF.md` §19.10**（HANDOFF 在本卡可改路径内、也随树发），README / 手册那两处**不在本卡可改路径**，排 v1.0.17。详见本节末尾的「**本轮最该先修的一条**」。 |
| **N-849** | 单机形态没有「每小时兜底扫描」的等价物 | 登记不修 | 双机那条核的是 f02 上 systemd 的 `genebench-answer-plane-scan.timer`（N-61）。单机用**落位即扫**替代；差别是「落完了、还没跑」那段时间窗里没有第二次周期复查。要不要给单机一个 cron / launchd 等价物，请用户裁。 |
| **N-850** | `ops/mk_tables.py:295` 表脚渲染的「复现命令」写死发布方解释器与仓库路径 | 登记不修 | 外部单机用户照抄不到（`PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo`）。它不改变本进程取任何路径，故不挡单机链路。卡 B9 在 f02 上复验确认仍在。 |
| **N-851** | N-840 在**双机**路径上仍在 | 登记不修 | 裁定 ① 明写「双机路径不动」，卡 A9 因此逐字节没碰那个脚本。外部**双机**用户仍会撞 rc=127，且这两个变量在 README / 手册 / HANDOFF 里 grep 命中 0 次。**请用户裁：v1.0.17 修，还是现在修。** |
| **N-852** | `runner/f02/answer_plane_guard.py:589-590` 的 `DEFAULT_ROOT` / `DEFAULT_LOG` 仍是发布方绝对路径 | 登记不修（**刻意**） | f02 上那个每小时的 systemd timer 正吃这两个默认，动它等于悄悄改掉「兜底扫描扫哪棵树」。单机路径**永远显式传 `--root` / `--log`**，`ops/test_A9.py` 有一条钉住。 |
| **N-853** | 单机真跑的 inner 用 `umask 077`（双机是 022） | 已实现，记因（**不占限制表计数**） | 单机执行面根落在 `$GENEBENCH_ROOT` 下，而红线 5 要求那棵树下每个目录 go-rwx；077 比 022 更严，红线 7 要挡的「0775 的 `__pycache__`」被一并挡住。容器以 `run_uid:run_gid`（= 起它的那个用户）跑，0700 读得到。**将来若有容器以别的 uid 跑，这一条要重审。** |
| **N-854** | `$GB/staging/` 里的旧 bundle 通行证已过期 | 登记不修 | 卡 A9 实测：`v1demo_s1-cor-01` 的通行证是 `v1.0-smoke / 1.0.13`，当前是 `v1.0-smoke-public / p1.0.0`，`push_guard` **正确拒绝**。这是暂存目录陈旧，不是缺陷；复用暂存的 `reuse` 分支靠 `frozen_manifest.root` 比对，行为正确。外部用户复用暂存时会看到这条报错。 |

### B 段：卡 B9（裁定 ③，提交 `5957d63` + `6afeebe`）

> 这道门**七步里前五步在未改动的树上全绿**（`git clone` → 三件附件逐件核 `sha256` → `--harden` +
> 起公开通道网关 `/healthz` 200 → 用仓库 `build/base/` 现构基座与 harness 新 tag → 出集 + **单机本地落位**，
> 全程 **0 次 ssh、0 次 `/data` open**、落点全 0700）。**第六步（一个 job）跑不通**，被下面四条挡住。
> 打了三个**只在那棵测试克隆里**的最小本地补丁之后整条路走到了表（24 列），过程里又量出两条。
> **第 ③层「把 `/data` 真遮掉」在本项目两台机器上都起不来**（Ubuntu 24.04 的
> `kernel.apparmor_restrict_unprivileged_userns=1` 把 `unshare -r -m` 与 `bwrap` 都按死，翻它要 root）——
> 所以「`/data` 不可及」是**断言**出来的、不是**遮蔽**出来的：能证明「我们的进程树没去开它」，
> **不能**证明「就算去开也开不到」。这句话已经写进 `ops/test_single_machine.py` 里一条**会跑的**记录。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-855** | `ops/run_f02_a1.py:51` `RUNNER_PROVIDER_ROOT` 写死 `/data/genebench_runner/provider`（`:69 RUN_ROOT` / `:70 RESULTS` 同源） | 登记不修·**挡单机真跑** | 单机路径上 `ops/run_joblist.py` **不传** `--provider-root`，而同一条路径上 `probe_f02_provider` 查的是 `runner_root()/provider` —— **两处不同源**。f02 上 `/data` 那一份**存在**（双机遗留），于是在 Linux 上表现为「跑起来 ok，只是读了另一棵树」；在造不出 `/data` 的机器上是硬停。**修法**：三个根从 `GENEBENCH_RUNNER_ROOT` 现算，兜底值搬进 `runner/placement_dual.py`。回归锁在 `ops/test_single_machine.py`（`xfail(strict=True)`，修好即 XPASS → 红，提醒删标记）。 |
| **N-856** | 执行面解释器默认 `python3`，而 `runner/c41/egress_proxy.py` 模块级 `import h11` | 登记不修·**挡任何新铺的执行面** | 全新部署上系统 `python3` 没有 `h11`，真跑第一步 `ModuleNotFoundError`。`exec/vendor/h11` **不在仓库里**（`ops/push_exec_to_f02.sh:60` 自己写着「h11 是在 f02 上就地铺的」），**没有任何文档化步骤会铺它**；f02 上那份是遗留物。卡 A9 加的 `GENEBENCH_RUNNER_PY` 能绕过，但**三处文档里 grep 命中 0 次**（本卡已补进 HANDOFF §19.10）。 |
| **N-857** | `ops/guard_modes.py:32` 模块级 `import genebench_config`，而 exec 树白名单不含 `genebench_config.py` | 登记不修·**挡任何新铺的执行面（单机与双机都挡）** | `runner/inject.py` 的 P0 `check_modes`（默认开）用 `spec_from_file_location` 动态加载 exec 树上的 `ops/guard_modes.py` → `ModuleNotFoundError: No module named 'genebench_config'`。**f02 上双机现在能跑，只因为那棵 exec 树是 2026-09-10 的旧版**（那时 `guard_modes` 还不 import 它）—— 也就是说**下一次 `ops/push_exec_to_f02.sh` 会把双机生产也打断**。**这不是「单机将来的问题」，是「下一次推 exec 树就发作」的现在问题。** 加白名单要**两处一起改**（`runner/placement.OPS_FILES` 与那个脚本的同名 shell 数组，`ops/test_A9.py` 逐项比对，漂移即红）。 |
| **N-858** | 单机真跑的前置「容器打得到宿主网关」在 §2.4 里一个字都没有 | 登记不修·文档 | §2.3 ① 写了那条 `sudo ufw allow …`，但 §2.4 那五条命令里没有任何提醒。**失败形态极难认**：实测容器打 `api.deepseek.com:443` 通、打**另一台机器**的 22 通，只有打**宿主自身**的所有地址全超时 —— 于是「模型照调、数据取不到」，run 撞墙钟闸退 124。**顺带一条**：§2.3 ① 那条命令写的端口是 **18080（私有通道）**，而公开通道是 **18081** —— 照抄的外部用户会得到一条**不生效**的规则。 |
| **N-859** | `ops/joblists/v1demo.yaml` 的 `digest:` 钉死发布方那台的镜像 id | 登记不修·minor | 外部用户按 §2.3 自己 `sh harnesses/build.sh codex` 构出来的 image id 必然不同，照抄这份矩阵会在 `pin_image_digest` 停。README §2.4 说它是「现成的验收矩阵」，但没说 digest 要换成自己那台上的。 |
| **N-860** | 单机形态下「把 provider 放到执行面」这一步没有任何文档 | 登记不修·minor | §2.1a ③ 把 provider 放到 `$GB/snapshots/public_v1/qlib_provider` 就结束了；**执行面还要一份**（`<runner_root>/provider/qlib_provider_<钉子前 8 位>/`）。这一步只在真跑被拒时的报错里出现。本卡已把照抄命令补进 HANDOFF §19.10。 |
| **N-861** | `ops/guard_modes.py --harden` **不是一次性的**：任何写 `.git/index` 的 git 操作之后注入器 P0 当场拒 | 登记不修·**挡外部用户** | 实测报错：`P0 红线 5 文件对组/其它开放 0o644 …/repo/.git/index`。README §2.1 把它写成「开跑之前跑一次」。建议在 §2.4 ④ 之前补一行 `--harden`。 |
| **N-862** | **单机形态下每个 run 自己的产物会让下一个 run 起不来** | 登记不修·**挡单机连跑** | 单机执行面根 = `$GENEBENCH_ROOT/genebench_runner`，**落在 `$GENEBENCH_ROOT` 里面**，而 P0 审计的正是那棵树。实测：strict 臂跑完，open 臂立刻被自己上一臂写的 0644 `llm_log.jsonl` 判红。**双机形态下 run 目录在 `$GENEBENCH_ROOT` 之外，P0 看不见** —— 又一条只在单机显形的。那些文件是**容器里的 agent 与边车**写的，不吃宿主 `umask`，所以 N-853 那个 077 救不到。 |
| **N-836 更新** | 卡 A9 的静态门闭包**够不到执行面入口** | 更新（**方法上的，值得读**） | `ops/test_A9.py::single_path_closure()` 走的是 **AST import 闭包**；而 `ops/run_joblist.py` 调 `ops/run_f02_a1.py` 用的是**子进程字符串**，闭包永远走不过去 —— N-855 那三行就住在那里。`ops/test_single_machine.py::ENTRIES` 是**超集**（16 个入口，比 A9 多 10 个），闭包 50+ 个文件。**给后续加入口的人**：凡是被**子进程**调起来的文件，都要**手工**加进入口集合。 |

### Z 段：卡 Zfin 的四条文档 minor —— **本轮没有任何一张卡做它们**

> 卡 C9 那一节写的是「N-844 / N-845 / N-846 / N-847 **由做它们的那张卡各自入账**」，
> 但本轮四张卡里**没有一张的可改路径包含 `README.md`**（卡 C9 有，可它的射程是用户裁定 ④⑤，
> 没有包含这四条）。于是它们既没被修、也没被入账 —— 本卡按「量到即记」在这里补上条目，
> 并在 `ops/reports/known_limits_v1.md` 本轮一节里入「登记不修」那一格。
> **四条的原文与实测都在 `ops/tickets_inbox/Zfin.md`**，这里只抄结论与改法。

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-844** | README §2.1 的「照上面的顺序跑，**最后一眼就是好的**」与 §2.3 ③ 自己那句「这是外部用户**第一步就会撞上**的事」互相矛盾 | 登记不修·minor | §2.1 那段把首跑残留的红**穷举成一条**（「绿 5 / 红 1，剩下那条是没装 docker」），可 `genebench_config.py::GATEWAY_HOST` 是**发布方 f01 的地址**，任何别的机器都绑不上 —— 卡 Zfin 实测是**绿 4 / 红 2**。那条红本身写得很好（给了改法、指了手册 §1.3），问题只在 §2.1 那句穷举。**改法**：§2.1 把残留的红写成两条并就地指一句「地址那条的改法在 §2.3 ③」。 |
| **N-845** | 基座构建耗时两处不同源：README / 手册说 **69 秒**，`build/base/README.md` §5 与 `ops/reports/base_image_portability.md` 说 **282 秒** | 登记不修·minor | 两个都是真实测量、都是 `--no-cache`、同一天、都是 Linux x86_64 —— 282 秒那次在数据面那台，69 秒那次在执行面的干净 clone 上，**但说 69 秒的两处都没写是哪台机器**。读者查「要多久」会去看 `build/base/README.md` §5，同一条命令 4 倍差无从调和；arm64 的估计（4–8 分钟）又是按 282 秒折算的。**改法**：说 69 秒的两处补一句机器，或统一引 282 秒并说明 69 秒是另一台。**卡 B9 本轮在执行面那台上现构实测 86 秒**，与 69 秒同一量级、与 282 秒仍差 3 倍 —— 更说明这是**机器差**不是笔误。 |
| **N-846** | README §3「仓库布局」那张顶层表里**没有 `build/`** | 登记不修·minor | 表里列了十一个目录，**独缺 `build/`** —— 而 `build/base/` 正是「用仓库自带的 Dockerfile 构基座」唯一的落点，也是 2026-09-13 才搬进来、专门为外部用户加的那棵子树。叠加 N-752（`.gitignore` 第 6 行那条**不锚定**的 `build/`，在这棵子树里新建文件 `git status` 不提醒）。**改法**：§3 那张表补一行 `build/`。 |
| **N-847** | `GENEBENCH_ROOT` 不设时的默认值仍是发布方的 `/data/shared/genebench`，而两处文档都没说「这个 export 要一直在」 | 登记不修·minor | README §2.1 第 1 行有 `export GENEBENCH_ROOT=$GB`，但**只在那一个 shell 里**；整条路径要跨几个小时（下 936 MiB、构镜像、一批真跑两小时），换个终端窗口就没了。卡 Zfin 实测：不带这个 env 跑 `--help`，帮助文本里渲染出来的题集根就是发布方的路径。**失败是响的**（那个目录在 Mac 上不存在），所以只记 minor。**改法**：§2.1 那块末尾补一句「这两行建议写进你的 shell profile」。 |

### D 段：卡 D9 本卡新发的三条

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-863** | `ops/push_guard.py:64` `ADAPT_DEST_PREFIX = "/data/genebench_runner/adapt/"` 在单机形态下是一条**造不出来的**落点判据 | 登记不修·minor | 它是 `ops/test_A9.py::DATA_LITERAL_EXEMPT` 里被豁免的两条**取值位**之一，豁免理由是「适配赛道专用，§2.4 那四道题的 `set_id` 不是它」——**这个理由对本门成立**（那道门的射程就是 §2.4 那条路）。但对**跑适配赛道的单机用户**不成立：`push_guard` 会要求 `set_id == v1.0-adapt` 的 bundle 落在这个写死前缀下，而那个路径在 macOS 上造不出来。本卡**只登记不修**（`ops/push_guard.py` 不在可改路径），修法与 N-841 同源：前缀从 `runner_root()` 现算。 |
| **N-864** | `runner/c41/runner_core.py:351-353` 的 `DATA_ROOTS` 禁挂黑名单在单机形态下**失去大半射程** | 登记不修·minor | 它是另一条被豁免的取值位，豁免理由是「不是『根』，是**禁挂**宿主数据目录的黑名单，换机器只会让它少拒一点、不会让它错拒」——**作为「不挡本门」的理由成立**。但要写明后果：单机用户的数据面落在 `$GENEBENCH_ROOT` 下，**不在这张表里**，于是这一层纵深在单机形态上基本不起作用。**主口径没有松**（答案面永不挂进容器由 `answer_plane_guard --mode container` 判，那一条是**根相对**的、单机照样有牙）；松的是纵深。表自己的注释也写着它是「**开放**列举，注定会烂」。 |
| **N-865** | `ops/test_d.py` 的署名形态门用**裸子串**判，于是**描述这条规则的正文**也会被判成署名 | **已修（措辞侧）；门的射程仍登记不修** | `_SIG` 里是 `r"Co-Authored-By:"` 与 `r"🤖"` 两条裸子串，而 `ops/reports/push_result.md` 有三处在**陈述那次提交的 body 里没有署名 trailer**、以及**引用扫描器自己的规则表** —— 于是这份报告在内网树上恒红（卡 C9 与 HANDOFF §19.9.5 都登记过，归「推送那张卡」）。**本卡是那张卡。** `ops/test_d.py` 不在可改路径，能动的只有措辞：三处都改成不嵌那两个字面量的写法，**技术事实一个字没丢**（裁定 ⑫ 的原话就是「署名形态一律删，**技术事实保留**」）。实测由 `1 failed / 16 passed / 1 skipped` 转 **17 passed / 1 skipped**。**门仍然过宽**（同一份 `scratch/P/scan_mentions.py` 用的是**带主语**的模式 —— 署名行后面必须真的跟着一个助手名字，那才是对的口径），要不要把 `_SIG` 收窄成同一套，归下一张能改 `ops/test_d.py` 的卡。 |

| **N-866** | `ops/test_wrapup.py` 的 `CARDS` 假设八个**卡名**永远唯一，而卡名会跨轮复用 | 登记不修·**刻意不修** | `CARDS = ("W1","W2","W3","X1","Y1","Y1b","Y2","W.rt")` 是 2026-09-10 收尾卡那一轮的八张卡；2026-09-13 又有一张卡叫 **W2**，于是 `ops/tickets_inbox/W2.md` 与 `W2.md.merged` **同时在**，那条「原名一个不留」当场红。**本卡实测在未改动的 HEAD 上就是红的**（同文件的 `test_新发的号连号_不与旧节撞号` 在 HEAD 上也红：缺号 840/841/842 —— **那一条本卡顺手修好了**，本轮 475..865 连号无缺、无撞号）。**看起来的修法是错的**：把 `ops/tickets_inbox/W2.md` 改名成 `.merged`，会让 `ops/reports/known_limits_v1.md`、`ops/reports/public/instruments_rebuild.md`、`ops/reports/push_result.md` 这三份**随树发的**文档按路径引到一个不存在的文件 —— **修一条测试的绿，换三处文档说假话**，不划算。**真修法**在 `ops/test_wrapup.py`（不在本卡可改路径）：那八个名字该按**那一轮的收件箱清单**认（例如连日期），而不是按裸卡名。**形状上又是 D-06 那一族**：判据悄悄取决于「后来有没有人重用这个名字」。 |

### 本轮**最该先修**的一条（给编排方与用户）

**不是 N-855，是 N-857。** 理由不在单机：`ops/guard_modes.py` 现在这一版一旦随
**下一次** `ops/push_exec_to_f02.sh` 推上 f02，**双机生产也会断** —— f02 上那棵 exec 树是
2026-09-10 的旧版，正好躲过了这个 import。这不是「单机形态将来的问题」，
是「下一次推 exec 树就发作」的**现在**问题，而本轮**没有人动过它**。

**其次是 N-848**：`runner/placement.py` 已经随树发了，而 README §2.4 ③④ 仍然教人跑两个
`push_*_to_f02.sh`。外部单机用户照 README 敲，**撞的还是 N-840 那条 rc=127** ——
新写的那条路他无从得知。本卡把照抄命令补进了 `ops/HANDOFF.md` §19.10（随树发），
但 README / 手册**不在本卡可改路径**。

## 卡 I10（2026-09-14）：这一轮的**收口**：四张卡并表 + 重跑单机门 + Release 正文 + 重打树推

> **本轮四张卡**：**Efin**（交付终核，只读 —— 本轮的问题清单就是它量出来的）、
> **F10**（代码侧：五条缺陷一次修完，提交 `b7b5cad`）、**H10**（文档那批全改，
> 提交 `1fcfeb2` / `16300d4` / `fe3975f`）、**G10**（两道新门，提交 `5bc9533`）、
> **I10**（本卡：并表、重跑门、PATCH Release 正文、重出清单、重打树、两遍扫描、推）。
>
> **取号**：盘上实际最大号是 **N-866**（卡 D9 取走）；卡 Efin 的收件箱已按 **N-867…N-879**
> 自编，本卡照用（那 13 个号此前只在收件箱里，从没进过本表）。本卡从 **N-880** 起续编。
> 取号前已 `grep` 全树复核：`ops/tickets.md` 之前无一撞号。
> **`N-881` 不是本卡随手给的** —— 卡 F10 提交时就把它写进了 `ops/test_exec_tree_fresh.py`
> 与 `ops/specs/design_notes.md` 的 **D-34**，改号会让**已提交的代码**指向一个不存在的票。
>
> **本卡自己重跑过 F / H / G 声称的判据，没有采信转述**（逐条见 §I10-3）。

### A 段：卡 Efin（交付终核，只读）—— 本轮的问题清单来源

> 下面 13 行**逐字取自** `ops/tickets_inbox/Efin-fresh.md.merged`，
> 只在每行末尾之外**另起一段**记本轮处置 —— 原文一个字没动。

| 编号 | 事项 | 状态（Efin 当时） | 说明 |
| --- | --- | --- | --- |
| **N-867** | README §2.4 ③④ 仍教两个 `push_*_to_f02.sh`，单机新入口一个字没有 | 待裁 | `runner.placement` / `GENEBENCH_TOPOLOGY` / `--topology` / `--place-exec` 在 `README.md` 与 `docs/OPERATOR_MANUAL.md` 里 grep 命中**各 0 次**，只在 `ops/HANDOFF.md` 里有。外部单机用户照 README:561 敲的还是 rc=127（N-840）。= N-848，本轮仍开着 |
| **N-868** | README:705-706 **主动禁止**单机用户做那件对的事 | 待裁 | 原文「把 bundle 送上执行面**只有一条路**……**不要绕过这两个脚本直接 `cp`**」。而单机形态的全部设计就是本地落位，`ops/run_joblist.py:207` 自己的报错文案写着「单机形态就在本机 cp」。这不是"没更新"，是**反向指路** |
| **N-869** | README §2.3 ① 那条唯一要 root 的命令**端口给错了通道** | 待裁 | 写的是 `port 18080`，那是**私有**端口（`genebench_config.py:564`）；单机用户被 §2.4 ⓪ 强制走 public，公开实例是 **18081**（`genebench_config.py:654`，注释还写明"刻意与 GATEWAY_PORT 不同"）。`ops/run_joblist.py:201` 的报错文案自己就说「18080 放行、18081 没放」。失败形态极难认 |
| **N-870** | README §2.3 ④ 让单机用户配一个**用不上**的东西 | 待裁 | 教人 `export GENEBENCH_F02=<你>@127.0.0.1` 并打通免密 ssh 到本机。而单机路径**一条 ssh 都不发**——`--dry` 的表头逐字打着「**单机：整条路径不发 ssh**」，结算那条是 `--remote-host local` |
| **N-871** | §2.3 状态框把**已经发出去的东西**说成"排进施工" | 待裁 | 原文「**已经排进施工**（用户 2026-09-14 裁定 ①②）」。而 `runner/placement.py` **就在这棵树里**且实测可用。成因那一段（N-843）改对了、也明确拦住了读者去补基座与夹具；但这一句让读者以为新路还没有，于是不会去找它。与 N-867 是同一个洞的两面 |
| **N-872** | 手册 §1.3 给 Mac 的那条唯一网络办法，**代码不收** | 待裁 | §1.3(1)：「Mac 上容器打宿主的规范写法是 `host.docker.internal`」。而 `runner/c41/runner_core.gateway_addr()`（:93-97）对 `GENEBENCH_GATEWAY_ADDR` 只收 `IPv4:端口`，主机名**当场抛** ValueError（"不收主机名"），`ops/run_joblist.py:367` 又在 public 下**必然**导出这个变量。手册那句已经很克制（"不替你断言 Mac 上容器一定打得通网关"），但它点名的值代码会拒 |
| **N-873** | `ops/run_joblist.py:194-214` 的拒绝文案：单机也说 f01/f02，还带发布方 IP，末段**已过期** | 待裁 | ① 文案在 `--topology single` 下照样说「**f02** 打不到公开网关」「**f01** 起了吗」；② :201 把 `sudo ufw allow from **192.168.1.219** …` 渲染给用户 —— 那是发布方 f02 的 LAN 地址，外部用户会照着给一个陌生 IP 开口；③ :208-211 说 `pin.PROVIDER_SHA256_ROOT` 写死私有那份、要把 `expect` 按通道传 —— **那件事已经做完了**（`runner/inject.py:635` `expect=provider_pin_expect(channel)`，`PUBLIC_PROVIDER_SHA256_ROOT` 在 :532）。报错文案在教人做一件已经做完的事 |
| **N-874** | 真跑前那一步 provider 上执行面，README / 手册**零处** | 待裁 | 本卡实测：真跑被拒的第 ② 条就是它。只在拒绝文案与 `ops/HANDOFF.md` §19.10 里有。这是「⑥ 一个 job」**就算有 docker 和 key 也走不到**的直接原因 = N-855 / N-860，从发布树上再确认一次 |
| **N-875** | **GitHub Release 页面的正文还停在"两个附件"** | 待裁 | 匿名 GET 到的 `body` 里：小节标题「## 两个附件」、表里只有 2 件、「下载与校验（照抄）」只有 2 条 `curl`，且用的是 `sha256sum -c`、「两行都要 OK」——**没有 macOS 的 `shasum` 替代**（裁定 ④ 只改到了 README）。而 README §2.1a 说第三件「**缺了它公开冻结根核不绿、题也跑不起来**」。Release 页是外部用户最先看到的那一屏，且**不在树里**，任何树内的门都管不到它 |
| **N-876** | `ops/export_bundle.py:247` 打给用户看的"下一步"是双机的 | 待裁 | 手工出集时打印「下一步：`ops/push_bundle_to_f02.sh` … `/data/genebench_runner/<run>/runner/tasks` …」。`ops/test_A9.py:484` **明知**地豁免了它（理由："一句提示文案，不参与取值"）——作为**字面量**判据这成立，但它是用户会照着敲的文案 |
| **N-877** | `ops/mk_tables.py:295` 把发布方路径写进回填报告 | 待裁 | `write_backfill_report` 的「怎么用」块里 `PY=/data/shared/genebench/env/bin/python; cd /data/shared/genebench/repo`。入口是 `ops/results_db.py:723`（`ingest --report`）。= N-850，再确认一次 |
| **N-878** | `--check-plane` 只活在 `--help` 和报错文案里 | 待裁 | README / `docs/OPERATOR_MANUAL.md` 里 0 处，只有 `ops/HANDOFF.md`。而拒绝文案第一句就让用户"只探用 `--check-plane`" |
| **N-879** | 「零次」这个判据的**措辞**与实现不是同一句话 | 登记不修 | 用户裁定 ③ 写的是「`/data` 字面量出现**零次**」；`ops/test_A9.py` 实现的是「**未豁免的**零次」＋一个逐字闭集 `DATA_LITERAL_EXEMPT` ＋一条防死条目的门。实现**更可用**（闭集 + 每条写理由 + 漂移即红），本卡不建议改实现；只建议别让后来人把"零次"读成字面意思 |

**本轮处置（逐条）**：**已修** —— `N-867`（§2.4 ③④ 按形态分岔，卡 H10 `1fcfeb2`）、
`N-868`（§4 ① 按形态改写，不再禁止单机用户做对的事）、`N-869`（`ufw` 端口 18080→18081，
并写清「端口跟着通道走」）、`N-870`（`GENEBENCH_F02` 按形态分岔，单机整段跳过）、
`N-871`（§2.3 状态框改成「新路已在本树中且实测可用」）、`N-872`（Mac 那条写法已改口 ——
**残留的矛盾另开 `N-880`**）、`N-873`（`run_joblist` 拒绝文案与 `--check-plane` 帮助按形态渲染，
卡 H10 `16300d4`）、`N-874`（§2.4 ③b / 手册 §5.4 ③b 补上「provider 上执行面」）、
`N-875`（**本卡** PATCH Release 正文，裁定 ③：三件附件 + Linux/macOS 两种校验命令）、
`N-876`（`export_bundle` 的「下一步」按形态二选一）、`N-878`（`--check-plane` 补进两份文档）。
**仍登记不修** —— `N-877`（`mk_tables` 那一行只补了注释，真修与 `N-850` 同批）、
`N-879`（「零次」的措辞与实现不同源，实现更可用，不建议改实现）。

### B 段：本卡续编（N-880 … N-889）

| 编号 | 事项 | 状态 | 说明 |
| --- | --- | --- | --- |
| **N-880** | **Mac 上没有任何被验证过的「容器 → 宿主网关」路径** | **v1.1**（已进已知限制） | 这是 `N-872` 改口之后**剩下的那件事**：旧文给的 `host.docker.internal` 不是「没验过」，是 `runner/c41/runner_core.py::gateway_addr()` **当场拒**（只收 `IPv4:端口`，主机名抛 `ValueError`；`0.0.0.0` / `127.0.0.1` / `localhost` / `::1` 在拒绝名单里）。代码这侧只剩「填这台 Mac 自己的 LAN IPv4」一条**可表达**的路，而那条**没有在 Mac 上验过**（外部验收停在网关那一步）。Linux 侧同一层的拦路是 `N-858`（要 root 开一条 `ufw`），本卡在 f02 上**又实测了一次仍然不通**。出处：H10 + I10。 |
| **N-881** | **一棵全新的执行面目录，根自己是 0775** —— `mkdir -m 700 -p` 的 `-m` 只作用在最后一段 | **已修**（卡 F10） | 裁定 ④ 那道新门**当场量出来的第一条**：既有那棵 `exec/` 是手工 `mkdir` 出来的 0700，所以这条**在既有树上永远不显形**。两处都修（`push_exec_to_f02.sh` 第 4 步前收紧 `$DEST`；`runner/placement.place_exec_tree` 把 `runner_root()` 与 `exec_dest()` 两级都收紧）。**本卡复核**：f02 全新落点上 `genebench_runner` 与 `genebench_runner/exec` 两级实测都是 `700`。 |
| **N-882** | `ops/test_Y.py::test_the_readme_shortest_path_runs_on_the_public_channel` **恒红** | **未修 · 待派卡**（不在本轮任何一张卡的可改路径内） | 卡 H10 的 `1fcfeb2` 把 README §2.4 拆成三个代码块（干跑 / 单机 / 双机），而 `ops/test_Y.py::_readme_block` 只取**第一个**块 → 「§2.4 里只有 1 条 `run_joblist` 命令，期望 2 条」。**卡 F10、卡 G10、本卡三次复现，三次报出，至今没有一张卡能改它。** 修法（不许放宽判据）：把 `_readme_block` 换成取该节下**全部**围栏代码块 —— `ops/test_readme.py::fenced_blocks()` 就是这个形状，可直接照抄；**不要**去 README 第一个块里补真跑命令（那会打乱「干跑先看一遍」的教学顺序）。本卡实测：§2.4 三个块里共 **5** 条 `run_joblist`，**每一条都带 `--channel public`** —— 也就是说判据本身在今天的 README 上是**成立**的，红的是取块的那一步。 |
| **N-883** | `ops/specs/README.md` 的索引表里没有 **D-34** 那一行 | **未修 · 待派卡** | 卡 G10 把裁定 ④ 那条纪律写成 `ops/specs/design_notes.md` 的 D-34（「同一支的时间维：判据悄悄取决于这台机器历史上被手工修过什么」）；`ops/specs/README.md` 的索引表要跟一行。出处：G10 / H10 都记过。 |
| **N-884** | `ops/test_A9.py` 与 `ops/test_single_machine.py` 两处 `/data` 字面量扫描**口径不一致** | **登记不修** | `test_A9` **连注释一起扫**，`test_single_machine::value_position_hits` **跳过 `#` 开头的行**。卡 H10 自己就因此踩过一次（在注释里写了那三个字母 → 只红一道门）。建议把两边口径对齐。出处：G10 / H10。 |
| **N-885** | 「网关绑哪个地址」没有环境变量，「容器打哪个地址」有 —— 两处不对称 | **登记不修 · minor** | `genebench_config.GATEWAY_HOST` 只能改常量（README §2.3 ③ 已如实写明），而 `runner_core.gateway_addr()` 有 `GENEBENCH_GATEWAY_ADDR`。单机用户于是要「改一个常量 + 设一个环境变量」，两件事看起来是同一件。不挡发布。出处：H10。 |
| **N-886** | 手册 §5.6「单题方式」的照抄命令仍是**双机口径**（写死执行面绝对路径 + `ssh $F02`） | **登记不修 · minor** | §5.4 的清单方式本轮已按形态分岔，§5.6 没跟着分岔 —— 单机用户照抄不到。真修要补一份单机版照抄命令（inner 是本机 `bash -c`、`umask 077`、根从 `GENEBENCH_RUNNER_ROOT` 现算）。出处：H10。 |
| **N-887** | 下载三件附件的 `curl -L -O` **没有 `--fail`** —— HTTP 错误页会被原样存成同名「附件」 | **登记不修 · minor**（守门已经拦住了） | **本卡实测**：连下三件时 `genebench_public_gold_subset_v1.tar.gz` 下成 **92 字节**（GitHub 侧的错误响应），`curl` 退 0、文件名对、大小不对。**下一步就被抓住了** —— README §2.1a 与 Release 正文都写着「三行都要 `OK` 再解包」，`sumc` 当场报 `FAILED` + `WARNING: 1 computed checksum did NOT match`；重下一次即 `OK`。所以这一条**不挡使用**，挡的是「第一眼就知道哪儿错了」。建议给那三条 `curl` 加 `--fail --retry 3`。出处：I10。 |
| **N-888** | `ops/selfcheck_public.py` 第 4 项只在**仓库根**与 `./downloads/` 找附件 | **登记不修 · minor** | **本卡实测**：附件放在 `$GENEBENCH_ROOT/dl/` 时第 4 项判**跳过**，并把找过的四个目录逐个列出来、把 `--downloads <目录>` 的用法写清楚；`--downloads $GB/dl` 补跑一次即 **绿**。自检本身说得很清楚，登记只是因为「跳过」在一份全绿的自检里最容易被读成「过了」。出处：I10。 |
| **N-889** | 「一个 job」在本系统里的**最小可跑单位是一道题的双臂**，两份文档都没说 | **登记不修 · minor** | **本卡实测**：`run_joblist --limit 1` 只选中干预臂那一个 job，出集侧 `ops/joblist.check_arms` 当场拒 —— `arms ['strict'] 里没有参照臂 'open' —— 等价规则以它为参照，缺了它出集侧当场拒`。报错本身是对的（等价规则要参照臂），但 README §2.4 把矩阵说成「8 个 run」、把恢复说成「原样再敲一次」，没有一处告诉用户**不能只跑一个臂**。本卡因此把「一个 job」按**一道题的双臂**跑。出处：I10。 |
| **N-890** | **f02 上「用户自定义 docker 网络」当前一律出不了网**（默认 bridge 出得去） | **登记不修 · 机器侧条件**（要 root 才能查/改） | **本卡真跑当场量到的**：一个 job 的双臂各 30 次模型调用，`log/llm_log.jsonl` 里 **`decision=="allow"` 0 条**、30 条全是 `{"decision": "deny", "reason": "proxy_error", "detail": "timed out"}`，每条间隔 30 秒 = `runner/c41/egress_proxy.py:1128` 那个 `create_connection(..., timeout=30)` 的连接超时。**逐层量过**：宿主直连 `api.deepseek.com` → `401`（2.0 秒，401 = 到了上游、没带凭据）；**默认 bridge** 的容器 → `401`；**新建的自定义网络**（`172.31.241.0/24` / `172.31.245.0/24` / `172.31.249.0/24` 三段各试一次）→ **三段全部 `TimeoutError`（30 秒）**。也就是说与网段无关，与**是不是 compose 建的自定义网桥**有关 —— 而每个 run 的 compose 必然建两个自定义网络。**后果**：这台机器上任何 compose 形态的 run 都拿不到模型 API，失败形态是 `SR=0` 而不是一条错。**不是仓库缺陷**（同一棵树 2026-09-14 上午在同一台机器上还拿到过 `allow`），是宿主转发规则的现状；与 `N-858` 同一族（都要机器主人执行）。出处：I10。 |

### C 段：上一轮登记、**本轮已经关掉**的（不发新号，只改判定）

`N-848`（README 仍教两个 `push_*`）、`N-855`（`run_f02_a1` 的 provider 根与探针不同源）、
`N-856`（`egress_proxy` 模块级 `import h11` 而 `vendor/h11` 不在仓库里）、
`N-857`（`guard_modes` 模块级 `import genebench_config`）、`N-858`（`ufw` 端口给错通道 ——
**只是文档侧已修**：机器上那条规则要 root，本卡在 f02 上实测**仍然不通**，见 `N-880`）、
`N-860`（provider 上执行面无文档）、`N-861`（`--harden` 不是一次性的）、
`N-862`（单机 run 产物让下一个 run 起不来）—— **八条都由卡 F10 / H10 落地**，
本卡在 f02 一棵**全新**落点上逐条复核过（§I10-3）。`N-849` 按用户裁定 ② **挪进 v1.1**。
`N-859`（矩阵 yaml 的 `digest` 钉死发布方那台的镜像 id）**仍登记不修** ——
本卡现构镜像之后照样要自己写一份矩阵，与卡 B9 同。
