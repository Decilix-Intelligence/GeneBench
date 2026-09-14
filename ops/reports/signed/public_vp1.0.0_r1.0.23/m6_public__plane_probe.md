# 执行面前置探针：实测记录（卡 6.5，2026-09-08）

> 公开通道真跑要的两件前置，逐条量过。命令与回包都在下面，**没有一句是推断**。
> 复现：`GENEBENCH_CHANNEL=public $PY ops/run_joblist.py --jobs $GB/runs_in/m6_public/jobs.jsonl --channel public --check-plane`

## ① f02 打不到公开网关

网关侧没问题 —— f01 上起得来、绑对了地址、`/healthz` 自报公开通道：

```
$ ops/public_gateway.sh start
（起来用了 105 秒）
[绿] 公开网关已起：http://192.168.1.48:18081 （pid 3034919）
{"ok":true,...,"bind":"192.168.1.48:18081","channel":"public",
 "tables_dir":"/data/shared/genebench/snapshots/public_v1/tables"}

$ ss -ltn | grep 1808
LISTEN 0 2048 192.168.1.48:18080 0.0.0.0:*
LISTEN 0 2048 192.168.1.48:18081 0.0.0.0:*
```

从 **f02** 打过来才是判据（网关就在 f01 上，f01 永远打得到自己）：

| 从 f02 打 f01 | 结果 |
| --- | --- |
| `curl http://192.168.1.48:18080/healthz` | `{"ok":true,...,"bind":"192.168.1.48:18080",...}` ✅ |
| `curl --max-time 20 http://192.168.1.48:18081/healthz` | `curl: (28) Connection timed out after 20002 ms` ❌ |
| `curl --max-time 12 http://192.168.1.48:18082/healthz` | `curl: (28) Connection timed out after 12003 ms` ❌ |

**18082 那一行是为了判规则形状**：起了一个 18082 的公开实例再从 f02 打，同样超时 ——
所以 f01 的入站规则放行的是 **18080 这一个端口**，不是一段端口。换个端口绕不过去。

拿不到规则原文（都要 root）：

```
$ ls -la /etc/ufw/user.rules   →  -rw-r----- 1 root root
$ head /etc/ufw/user.rules     →  Permission denied
$ iptables -L -n               →  Permission denied (you must be root)
$ sudo -n -l                   →  sudo: a password is required
```

**要的一条规则（请用户执行，红线 B1 无 sudo）**：

```bash
sudo ufw allow from 192.168.1.219 to any port 18081 proto tcp
```

## ② f02 上没有公开通道的 provider

```
数据面 $SNAPSHOTS/public_v1/qlib_provider  根 = 561348660a3175b17b906e2b4413e956959d7df4362939b0a85c67cf816c3a92
数据面 $SNAPSHOTS/v1/qlib_provider         根 = 54fdda39c60bf8486849c27862fbcb9878e2c9cc118886f9c96e1e57e3e2194d
f02   /data/genebench_runner/provider/     只有 qlib_provider_54fdda39/（根 54fdda39…）
```

注入器 P2 现算 provider 的 `files.sha256` 并比 `genetask/pin.PROVIDER_SHA256_ROOT`（`"54fdda39"`）。
把公开 bundle 拿去注入，P2 当场红 —— 本卡在 f01 上用 `--dry` 复现过：

```
[红] strict 注入失败：PackError: [P2] 注入中止（1 条）：
  P2 provider sha256 根 561348660a3175b1… ≠ 冻结值 54fdda39… —— provider 变了…
```

两步才能补上：

1. `rsync` 把 `$SNAPSHOTS/public_v1/qlib_provider`（28 610 个文件）推到 f02 的
   `/data/genebench_runner/provider/qlib_provider_56134866/`（方向 f01→f02）；
2. 让 P2 按通道取钉子。**`genetask/pin.py` 在 `ops/freeze_v10.CODE_FILES` 里**，改常量就是改冻结根
   （红线 B4，要推任务集版本并重出集）。取小改的路子：`check_provider_pin(..., expect=…)`
   本来就收 `expect`，由 `runner/inject.py` 按通道传，`pin.py` 一个字不动。

## ③ 链路本身已经验过（这两件之外的每一段）

| 段 | 怎么验的 | 结果 |
| --- | --- | --- |
| 矩阵 → 清单 | `ops/joblist.py gen --matrix ops/joblists/m6_public.yaml` | 18 个 job；S4 档 150、S7 档 300、其余 100；全部 `max_tokens=3000000` |
| 混通道门 | 不设 `GENEBENCH_CHANNEL` 直接 `--channel public` | 拒绝启动，报「--channel 与环境变量不一致」 |
| 干跑 | `--dry --channel public` | 六段命令逐条打印，题集根 / 网关日志 / 容器网关三处都是公开那一套；`jobs.jsonl` md5 前后相同 |
| 公开出集 | `export_from_answer_plane("s1-cor-01", …)` | 通行证 `frozen.root = 925a1adcdf82e6a0…`（= SET_VERSION 1.0.13）、`arm_registry.in_sync=true`；两条通道答案面的 `task.yaml` mtime 全程未变 |
| 注入 + compose | `run_f02_a1.py --dry`（f01，私有 provider） | 两臂 §6.2/§6.6.4 三条子句逐条对上；compose 里 `--gateway 192.168.1.48:18081`，容器里 `GENEBENCH_GATEWAY: "http://gateway:18080"` 一个字没动 |
