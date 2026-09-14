# `ops/reports/m6_public/` —— 公开通道上的 M6 pass（卡 6.5）

> 2026-09-08。**这一批的真跑没有发生**：链路已经接通并逐段验过，但执行面上还差两件，
> 两件都不在数据面手里。下面把「跑了什么、没跑什么、为什么」逐条摆开，不含形容词。

## 0. 一句话

**数据面这一侧的公开通道跑批链路已经接通并可复现；执行面差两件前置（f01 的 18081 对 f02 不通、
f02 上没有公开 provider），所以 18 个 run 一个都没跑。** 三控、逐族破坏样本、验证验证器报告
这三样**在公开通道上真跑过**，五部分判定**通过**。

## 1. 跑了的（都是公开通道，真跑）

| 件 | 产物 | 结论 |
| --- | --- | --- |
| 三控（oracle / null / filler）走完整评分器 | `controls.md` / `controls.json`（= `ops/reports/public/` 那一份的副本） | 27 条记录（9 题 × 3 桩），**三条判据全过**：oracle 每族零 finding；null 桶 `malformed` → SR 记 0；filler 在 `s7-rob-02` 上命中 `silent_completion` 且 effect 为 null |
| 逐族破坏样本（5.2 出集变了之后**重跑**一次） | `mutations.md` / `mutations.json` | 19 条中 **18 条**「该族响、其余不响」，覆盖 **14 族**；造不出的 1 条是 `s5-cor-01 / missing_masquerading_as_signal`（本题窗口一格 `no_data` 都没有，前提不成立 —— N-119，设计性限制） |
| 验证验证器报告（五部分） | `validator_validation_v1_public.md` | **判定：通过**。① 零误报 34 题有产物且零 finding、0 条 finding；② 必命中 38/38；③ 三态 `65 passed`；④ 破坏样本 18/19、14 族；⑤ 三控三条全绿 |
| v1.0 就绪报告（公开通道） | `v1_0_readiness_public.md` | §1 组件版本与冻结根、§3 三控与验证验证器、§5 已知限制**从 `known_limits_v1.md` 现读**；§2「本批 0 个 run」是**真的**，见下 |

## 2. 没跑的，以及为什么

18 个 run 的清单已经生成、状态全是 `pending`：`$GB/runs_in/m6_public/jobs.jsonl`
（矩阵 `ops/joblists/m6_public.yaml`：1 配置 × 双臂 × 9 题 × 1 种子）。
干跑逐条打印过、清单一个字节没改。真跑没起，卡在执行面这**两件**：

1. **f01 的入站防火墙没给 f02 放行 18081。** 实测 f02 打 18080 拿得到 healthz、打 18081 连接超时；
   f01 自己 curl 18081 拿得到 `{"channel":"public"}`，`ss -ltn` 也显示绑好了 —— 不是网关的问题。
   开这个口要 `sudo ufw`，而**红线 B1 是无 sudo**。要的一条规则：
   `sudo ufw allow from 192.168.1.219 to any port 18081 proto tcp`。
2. **f02 上没有公开通道的 provider。** 公开 provider 根是 `561348660a3175b1…`，
   f02 上只有私有那份 `qlib_provider_54fdda39/`。注入器 P2 比的钉子
   `genetask/pin.PROVIDER_SHA256_ROOT` 写死的是私有那份，而 `genetask/pin.py`
   在冻结根 `CODE_FILES` 里 —— 改它要推任务集版本（红线 B4）。
   取小改的路子：`check_provider_pin(..., expect=…)` 本来就收 `expect`，由 `runner/inject.py` 按通道传。

**这两件都不是「没时间做」，是各自要一次授权**（一条 ufw 规则 / 一次改注入器 + 一次 602 MB 传输）。
在它们齐之前跑，得到的不是「跑失败了」而是**两种会被读错的东西**：
网关不通 → 空产物，在 Table A 上长得像「模型不会做这道题」；provider 不在 → 18 次 P2 红，
长得像「注入器坏了」。所以加了一道前置门，**推 bundle 之前**先探这两件：

```bash
GENEBENCH_CHANNEL=public $PY ops/run_joblist.py --jobs $GB/runs_in/m6_public/jobs.jsonl \
    --channel public --check-plane          # 只探不跑；退出码 0 = 两件都齐
```

## 3. 两件齐了之后怎么跑（照抄）

```bash
GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo; ulimit -n 8192
ops/push_exec_to_f02.sh --with-launch-data     # 先 git status 看一眼（契约要求人看一眼）
ops/public_gateway.sh start                    # 公开网关起在 192.168.1.48:18081
GENEBENCH_CHANNEL=public $PY ops/run_joblist.py --jobs $GB/runs_in/m6_public/jobs.jsonl \
    --resume --channel public --tables a,b
ops/public_gateway.sh stop
```

**不要**包 `ops/public_gateway.sh run -- …`：那个子命令自己持 `gateway_lock`，
而运行器的每个 job 也去拿同一把锁 —— 锁不可重入（N-284），表现是
「网关起来了、一题都没跑、也不报错」。

## 4. 引这批数之前要知道的

* **规模就是 M6 的定义**：1 个验收配置 × 双臂 × 每阶段 1 题 + `s7-rob-02` × 1 种子。
  它证明的是「这条链路能把一次真运行变成一行主表」，**不是任何模型的能力**。
* **预算**：矩阵显式写了 `max_tokens: 3000000`（HANDOFF §14.4 §3 的「接入验证一律 3 M」）。
  显式值逐键赢过 stage 档位，所以 S7 两题拿到的是 300 次 / **3 M**，而不是档位的 300 次 / 18 M；
  N-130 量到 S7 单 run 用到 5.2–5.6 M —— **S7 两题大概率撞 token 闸**，撞了是终态、不自动重跑。
  抬默认档（600 k → 6 M）是用户签字项 N-388，本卡不动 `runner/registry.py` 的默认值。
* **Table A / B 缺席**是因为一个 run 都没有，不是出表坏了。清单是 `pending 18`，
  两件前置齐了 `--resume` 续跑即可，不用重建。

---

## 5. 2026-09-10 现状（卡 X1）

§2 列的**两件前置都齐了**，但**第三件冒出来了，18 个 run 仍然一个都没跑**。

| 前置 | 2026-09-08 | 2026-09-10 |
| --- | --- | --- |
| f01 的 18081 对 f02 放行 | 挡着 | **齐**（W1 实测 f02 → f01:18081 = 200；当时的 000 是公开实例没起，不是防火墙） |
| f02 上有公开 provider | 挡着 | **齐**（W1 推了 28,610 文件，根 `561348660a3175b1…` 现算一致） |
| — | — | **新：公开 provider 的 `files.sha256` 漏了自己两个元数据文件** → 注入期 P2 必红 |

第三件的现场（本卡复现）：

```
check_provider_pin(public, expect=561348660a3175b1) -> 2
   P2 树里有而清单里没有：MANIFEST.sha256
   P2 树里有而清单里没有：build_info.json
```

`--check-plane` **退 0** —— 它只核根 hash，核不到逐文件那一层；
**红是在真跑的注入期才发生**，而那时 18 个 run 会一起红在 P2。
两个方向、以及「方向 ② 对 `MANIFEST.sha256` 在数学上不成立（循环自指）」的证明，
见 `ops/tickets_inbox/X1.md` §1。**这一条不解，别排这 18 个 run。**

本卡另外做掉的三件：

* **清单里那行显式 `max_tokens: 3000000` 清掉了**（N-388）。§4 那段「矩阵显式写了 3 M ⋯
  S7 两题大概率撞 token 闸」**已经不是现状**：18 行的 `budget_override` 现在都是 `{}`，
  S1–S3/S5/S6/S8 走默认档 100 次 / **6 M**，S4 走 150 次 / 9 M，S7 走 300 次 / **18 M**。
  清单**没有重建**（逐行改一个键），备份 `jobs.jsonl.x1bak-20260910T131040`。
  N-130 量到 S7 单臂用 4.04 M / 5.66 M —— 18 M 的档里做得完。
* **三控与逐族破坏样本在公开通道重跑了一次**，落 `x1_rerun/`：
  `mutations.md` 与 2026-09-08 那份**逐字节一致**，`controls.md` 只差复现命令里那个
  `--out` 路径，两份 json 忽略时间戳后**相同** —— 口径没变。
* **就绪报告与验证验证器报告在公开通道重出**（`v1_0_readiness_public.md` /
  `ops/reports/public/validator_validation_v1_public.md`）。与上一版的差异只有三处：
  pytest 的墙钟、仓库 HEAD、以及 §5 多出 W2 新登记的那条已知限制 ——
  说明「§5 从 `known_limits_v1.md` 现读」这条改动**真的在起作用**。
