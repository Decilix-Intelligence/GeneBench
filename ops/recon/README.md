# 侦察归档索引（ops/recon/）

本目录存放 GeneBench 开工前两轮侦察的**原始产物**。归档时间 2026-08-30（卡 0.1）。

> **看这里之前先知道一件事**：两轮侦察的结论**不等权**。第二轮（readiness R1）**推翻了第一轮的若干条**。
> 凡两者冲突，**一律以 `readiness_r1.md` 为准**；第一轮文件保留只为留存证据链与当时的判断依据。
> 下面每个文件都标了它的**时间**与**可信度边界**——边界比结论重要。

---

## 文件清单

| 文件 | 是什么 | 采集时间 (UTC) | 权威度 |
|---|---|---|---|
| `readiness_r1.md` | 第二轮就绪度侦察报告，**含 R1 修订** | 2026-08-30 11:55–12:35（R1 补订 12:35） | ⭐ **最高。冲突时以此为准** |
| `readiness_r1.json` | 同上的机器可读版（同一次扫描的结构化产物） | 同上 | ⭐ 同上 |
| `data_lake_inventory_round1.html` | 第一轮数据湖清点（单页 HTML 报告） | 2026-08-30 上午（数据源为 2026-08-28 的覆盖率审计） | ⚠️ **部分条目已被 R1 修正，见下** |
| `probes/probe_*.py` | 第二轮实际跑的探测脚本（只读） | 2026-08-30 12:01–12:06 | 证据 |
| `probes/probe_*.out` | 上述脚本的原始 stdout（未加工） | 2026-08-30 12:01–12:06 | ⭐ **原始证据，不可再生成** |

**同源校验**：`readiness_r1.md` / `.json` 与 finance01 上 `~/genebench_inventory/` 里的原件 md5 一致
（`bf3ff7030ecb70e0c6f342fadd6ec2a1` / `eafc59dcd36701ba597bc1931ef24256`），本目录是拷贝而非再加工。

---

## 第一轮已被 R1 修正的条目（**不要照抄第一轮**）

| 主题 | 第一轮（`data_lake_inventory_round1.html`）说 | R1 修正为 |
|---|---|---|
| **ChinaScope / Smartag 覆盖区间** | `2008-01-01 → 2024-09-01`（**按包名写的**） | 🔴 **实际覆盖到 2026-02**。`news_region_label_*` 系列的最新一个是 `news_region_label_202601010000-202602010000.zip`，比包名上的 `20240901` 晚一年半。第一轮只看了 `news_company_label_*`，**整个 `news_region_label_*` 系列被漏掉了**。 |
| **qlib 当前 release** | `2026-08-04` | `cn_data` 实际指向 **community channel 的 `2026-08-26`**。`2026-08-04` 是 `current_release.txt`（local channel 指针），**已落后**。→ 以 `QLIB_RELEASE = ~/projects/data/qlib/releases/2026-08-26` 为准。 |
| **ufw 的放行机制** | （第一轮 readiness 初版）"finance01 的 ufw 规则是按接口放行的" | 🔴 **机制说错了**。规则里根本没有任何一条提到 tailscale。真实原因是两条**绕过**：① tailscale 把 ACCEPT 插在 ufw 之前（`ts-input` 链）；② `DEFAULT_FORWARD_POLICY=ACCEPT` 让 NodePort 走 FORWARD 绕开 INPUT。**观察到的现象没错，解释错了。** 原文见 `readiness_r1.md` A.2 的 "▶ R1" 小节，抄件在 `../env_baseline/ufw_finance01.txt`。 |
| **W1 的挂载地址** | "挂载地址与 ufw 规则要一并确认"（待定） | 已定论：**用 LAN `192.168.1.219`，不要用 tailscale 地址**；不需要动任何防火墙。→ 工单 **T-07**。 |
| **LXD 状态** | （侦察轮意外安装）finance02 上被 `lxd-installer` 触发装了 LXD snap | ✅ 已由用户 `snap remove --purge lxd` 移除并验证（2026-08-30 12:32 UTC）。**但 `lxd-installer` 包与 `/usr/sbin/lxc` 触发器仍在** → 工单 **T-03**。 |

**数据集计数三个口径并存，不是矛盾**：第一轮报 gold 层 **147** 个数据集、按主题列 **146** 个、覆盖率审计跑 **184** 个、DuckDB catalog 有 **150** 个只读 view。四个数字统计对象不同（落地目录 / 报告分组 / 审计清单 / view），引用时**必须带上口径**。

---

## 各文件的可信度边界

### `readiness_r1.md` / `readiness_r1.json`

**做到了**：严格只读扫描，写入范围仅 `~/genebench_inventory/`；A 节环境画像与 B 节八项数据确认均为实测；R1 补齐了 finance01 的 ufw 原文。

**明确没做到的（原文 D 节，照抄要点）**：

- **finance02 的 ufw 仍未读** → 工单 **T-05**。防火墙基线目前只有一半。
- **"NodePort 绕过 ufw"未直接取证** —— 是 `DEFAULT_FORWARD_POLICY=ACCEPT` + 实测连通性的**推断**，没抓过 iptables 链（要 `sudo iptables -t nat -L PREROUTING -n` 才算实证）。
- **ChinaScope 的 schema 是流式读 zip 前 24 KB 得到的**（两台都没装 `unzip`），**未验证文件尾部** —— 末行是否完整、有无多段 header 都不知道。只另解压了 3 个小字典文件。
- **848 个 Smartag 新闻包只抽查了 1 个**（2008–2009 那份）；`news_region_label_*` 系列**只做了目录级确认，未读 schema**。
- **`fin_secu_sam_product_calc_pit`（470 MB 解压）只读了头部**，实际标的数与期数覆盖未统计。
- **`index_weight` 的成分变动率没有实算**，只确认了它是月末快照。
- 时间盒 45 分钟内完成，未触发降采样。

### `data_lake_inventory_round1.html`

**做到了**：覆盖率审计口径的行数与覆盖区间（源为 2026-08-28 的审计，184 个数据集 0 重复键 / 0 空键）、标的数现算、采集管线台账统计、按严重程度排序的问题清单。第一轮独有、R1 未重复的有价值内容：**采集管线的 provider/run 分布**（38.9 万条 run，ok 27.8 万 / expected_empty 6.2 万 / schema_changed 4.8 万 / throttled 218 / failed 156）与**滞后数据集清单**（`hk_hold` 停在 2024-08-19、`irm_qa_sz` 2020-12-31、`stk_account` 2019-02-22、`index_basic` 2014-10-17）。

**边界**：

- **ChinaScope 区间按包名写的，已被 R1 推翻**（见上表第一行）。
- **可观测历史只有 27 天** —— 采集台账最早一条是 2026-08-03。任何"历史上一直如此"的判断都没有证据支撑。
- 报告本身是浏览时刻的快照，**没有版本号也没有再生成脚本**；数字随管线继续跑会漂。

### `probes/`

第二轮实际执行的四个只读探测脚本及其原始输出：

| 脚本 | 探测对象 | 输出 |
|---|---|---|
| `probe_b.py` | `catalog/market.duckdb`（150 个只读 view）的 schema 与样例 | `probe_b.out` |
| `probe_b2.py` | gold 层定向分区 `read_parquet`（`suspend_d` 等） | `probe_b2.out` |
| `probe_cs.py` | ChinaScope zip 的 entry 列表 | `probe_cs.out` |
| `probe_cs2.py` | ChinaScope zip 的流式 peek（前 24 KB） | `probe_cs2.out` |

**边界**：

- `.out` 是**原始 stdout，未加工**；`readiness_r1.md` 里的表格是它们的**人工归纳**。两者冲突时以 `.out` 为准。
- 脚本硬编码了绝对路径（`/home/ljn/projects/data/market_lake/...`、`/data/financial_data/ripple_alpha/...`），**不是可移植的工具**，重跑前先核路径。
- `probe_b*.py` 里 `duckdb.connect(..., read_only=True)` 是**强制约定**，不是可选项 —— catalog 是共享只读库，写模式打开会拿排他锁并妨碍生产管线。
- `probe_cs*.py` 会往 `~/genebench_inventory/tmp/` 写解压出的小字典文件（3 个，合计 < 550 KB），**那个 tmp 目录没有归档到这里**（内容是 vendor 数据，红线：ChinaScope 任何字节不进公开子集）。

---

## 重跑时的注意事项

```bash
# 只读探测的正确姿势（红线 2：数据湖只读）
ssh -o ConnectTimeout=60 -o ServerAliveInterval=15 ljn@finance01.tail642a54.ts.net '
  ulimit -n 8192                      # 不加这行，duckdb 查 gold 全表会 "Too many open files"
  /home/ljn/tools/miniconda3/envs/qlib_env/bin/python /path/to/probe_b.py
'
```

- **`ulimit -n 8192`**：duckdb 扫 gold 全表必踩 "Too many open files"。要么提 ulimit，要么直接 `read_parquet('<gold>/<ds>/<partition>/*.parquet')` 读定向分区。
- **catalog 必须 `read_only=True`**。
- 数据冻结线 **2026-07-31**：v1 的一切查询与快照上界不得超过它。第一轮/第二轮报告里出现的 `2026-08-xx` 覆盖区间是**侦察时的实际状态**，不是 v1 可用范围。

---

## 相关文件（本目录之外）

| 路径 | 内容 |
|---|---|
| `../GeneBench工程实施稿_v1.md` | 开工文档：架构定稿、里程碑与任务卡、决策 D1–D4、人工窗口清单 |
| `../tickets.md` | 待批工单台账 T-01…T-10（本目录里的每条"未做到"基本都在那里有对应票） |
| `../env_baseline/env_finance01.md` | finance01 环境事实的施工用速查（`readiness_r1.md` A.1 的浓缩） |
| `../env_baseline/ufw_finance01.txt` | finance01 ufw 规则原文抄件（`readiness_r1.md` A.2 R1 小节） |
| `../env_baseline/ufw_finance02.txt` | **尚不存在** —— 等 T-05 |
