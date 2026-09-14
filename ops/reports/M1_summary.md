# M1 收口小结

生成于 `2026-08-31T18:20Z` · 数据冻结线 `2026-07-31` · 仓库 HEAD `9c498fd`（收口提交前）·
依赖快照版本：qlib release `2026-08-26`、湖 catalog `market.duckdb`（150 view，只读）、gold 数据集 147 个。

---

## 一句话结论

**M1 四张卡里交付了两张。** 卡 1.1（PIT 宇宙）与卡 1.2（可交易性视图）完整交付、验收通过、可送人工放行；
**卡 1.3（as-of 网关）与卡 1.4（快照版本化）没有开工** —— 仓库里没有实现、没有测试、没有 manifest、没有进程。
按实施稿"M1 是整个 v1 的承重墙"的定位，**承重墙砌了一半，M2 不能在这上面起梁。**

---

## 1. 四张卡的状态与验收结论

| 卡 | 内容 | 交付 | 验收裁决 | 证据 |
| --- | --- | --- | --- | --- |
| **1.1** | PIT 宇宙（源A 湖 `index_weight` / 源B qlib instruments / 三源合并出 `universe_pit`）+ 对账报告 | ✅ 完整 | **PASS**（合议：as-submitted **FAIL**，5 条阻塞当场修完后 PASS） | `progress.md` 的 `1.1` / `1.1-verdict` 行；`ops/reports/universe_reconciliation.md`（42 KB，本轮已复核仍自洽） |
| **1.2** | 可交易性视图 `tradability`（三方 join 分开"停牌"与"数据缺失"，触板分收盘/盘中两口径） | ✅ 完整 | **PASS**（as-submitted **FAIL**，D1–D3 三条阻塞在 `1.2-fix` / `1.2-fix2` 修完；D4–D7 判非阻塞 → N-09…N-12） | `progress.md` 的 `1.2` / `1.2-fix` / `1.2-fix2` 行；`test_tradability.py` 40 项 → **45 项** |
| **1.3** | as-of 网关（FastAPI，绑 `192.168.1.48:18080`，7 个端点族，`as_of` 强制 + 越界 403 + `access_log`） | ❌ **未开工** | **无裁决**（无可裁之物） | `gateway/` 只有 12 行 `__init__.py`；`grep -rn "FastAPI(\|APIRouter\|@app\."` = 0 处；无 `ops/test_gateway.py`；`18080` 无人监听 |
| **1.4** | 快照版本化（v1 依赖表 parquet 快照 + manifest 记 sha256/行数 + 网关双后端） | ❌ **未开工** | **无裁决** | `find $SNAPSHOTS -iname '*manifest*'` = 0；`$SNAPSHOTS/v1/` 里只有卡 1.1/1.2 的产物 |

### 验收命令与输出（本轮实跑）

```
cd /data/shared/genebench/repo && ulimit -n 8192 \
  && /data/shared/genebench/env/bin/python -m pytest ops/ -q
```

| 次序 | 输出 | 判定 |
| --- | --- | --- |
| 第 1 次 | `1 failed, 474 passed, 29 errors in 156.86s` | **链路抖动，非回退**：30 个问题同因 —— 外部湖 ETL 持 `market.duckdb` 写锁（`Conflicting lock is held in .../qlib_env/bin/python3.10 (PID 242817)`），`lake.open_catalog()` 重试 5 次后放弃 |
| 重跑受影响的两个文件 | `76 passed in 7.73s` | ✅ |
| 第 2 次全量 | `504 passed in 137.50s`（exit=0） | ✅ **验收通过** |
| 第 3 次全量（收口改动后） | **`505 passed in 137.49s`**（exit=0） | ✅ **收口后仍通过** |
| 对账负控 | `ops/negctl_universe_reconcile.py` 三项判别力全部复现（半开区间 +55,657、日历日展开 +83,251、贴片不合并段数 ×11.7 而成员日不变） | ✅ |

**测试基数对账**：收口改动前 `pytest ops/ --collect-only -q` = **504 tests collected**，
与"基线 499 − 1 + 6 = 504"（只有 `test_tradability.py` 从 40 项变 45 项，无测试被删）**一致**。
收口后为 **505** —— 多出的一项是本轮新增的负控
`test_freeze_line_scanner_still_catches_a_real_violation`，**没有任何一项被删除或跳过**，
来历见 `ops/reports/gateway_probe_report.md` §6.3。

---

## 2. 两份交付报告

| 报告 | 状态 | 本轮做了什么 |
| --- | --- | --- |
| `ops/reports/universe_reconciliation.md` | ✅ **可放行** | **复核，未重写**。三项独立验证全过（见 §2.1）；只微调了抬头，补上"依赖的快照版本"一行 |
| `ops/reports/gateway_probe_report.md` | ⚠️ **不可据以放行网关** | **新写**。因为网关不存在，它记录的是"地基查过了没有"，不是"网关对不对"。**报告开篇即声明它不含任何探针结果** |

### 2.1 宇宙对账报告的复核结论（独立复算，不看单测）

| 复核项 | 方法 | 结果 |
| --- | --- | --- |
| 数由生成器现算，不是写死 | 现场 `ur.build()` + `ur.render_markdown()`，与落盘 `.md` 去时间戳后逐字比对 | ✅ **完全相同**（sha 前 16 位 `14f6a59e30f7daa3` 两侧一致） |
| JSON 与 md 同源 | 现算 `res` 与落盘 `.json` 去 `generated_at_utc` 后深比 | ✅ **完全相同** |
| 20 条签字清单四要素完整 | 逐条查字段 | ✅ 20 条，每条含 `code` / `universe` / `class_label` / `disagreement_span` / `source_a_says` / `source_b_says` / `verdict` / `basis` + 签字栏 —— **超过四要素** |
| 分层不是"全砸在最大那类" | 查 `quota_by_class` | ✅ 6 类：基期缺口 4 / 代码映射 3 / 退市响应 3 / 整段有无 3 / 月末粒度 4 / 换仓格点 3 |
| 抽样种子可复现 | 查 `parameters` | ✅ 种子 `20260731`，方法 `sha256(f"{seed}|{universe}|{code}")` 升序取前 300，**不依赖随机数发生器** |
| 冻结线 | 扫全文所有 ISO 日期 | ✅ **0 个**超过 `2026-07-31` |

> 报告自身已登记的弱点（N-08：20 条"依据"去重后只有 8 种文本）本轮**未修** ——
> 它是可读性问题不是正确性问题，改它要动生成器模板并重算全套产物，不该混进收口轮。

---

## 3. 遗留问题

### 3.1 本轮新增（N-13 … N-15、T-11）

| ID | 标题 | 级别 | 为什么 |
| --- | --- | --- | --- |
| **N-13** | 卡 1.3 as-of 网关未交付 | 🔴 **阻塞 M2** | 执行面访问数据的唯一入口（红线 3）不存在；卡 3.2 的 S1/S8、卡 4.1 的路由与 `access_log` 落库、卡 5.1 的前视探针全部悬空 |
| **N-14** | 卡 1.4 快照版本化未交付 | 🔴 **阻塞 M2** | "v1 评测一律走 snapshot"今天无法执行；卡 2.1 的 792 条因子要"经网关 snapshot 后端喂入"，后端不存在 |
| **N-15** | 三大报表 vip 口径的 `f_ann_date` 存在大量 NULL | 🔴 **阻塞卡 1.3 的正确性** | `income_vip` 5,708 行 NULL（2026Q1 占 5,686 行 / 5,678 只票 = 该季 27.7%），成因是分区间 schema 漂移 + 视图 `union_by_name=true`。**"NULL 就放行"的兜底写法 = 全市场级前视泄漏**。已实测缓解事实：这 5,678 只票每一只都同时有非 NULL 行（"只有 NULL 行"的票 = 0），所以**严格丢弃是安全的默认**，但必须被断言 |
| **T-11** | `/etc/fstab` 第 17 行有一条**已启用**的 nfs4 客户端条目 | 🔴 **待批（sudo）** | `192.168.1.219:/data /mnt/finance02-data nfs4 rw,...,_netdev,nofail`。当前 `/proc/mounts` 无 NFS（**没挂上**），但**重启即自动挂** —— 与红线 3"执行面不挂任何 NFS"直接冲突，是 T-06 那块敞口的另一半。**不是我们加的**：fstab mtime `2026-08-18 06:27:35`，早于施工 12 天 |

### 3.2 既有遗留（N-01 … N-12，本轮未动）

* **N-01 … N-08** —— 卡 1.1 合议判为非阻塞（metadata 缺口、容差过宽、时间戳脏 git、docstring 口径、绝对路径字面量、守门测试缺位、权限审计只审目录、签字依据文本重复）。详见 `ops/tickets.md` 附录 C。
* **N-09 … N-12** —— 卡 1.2 独立验收判为非阻塞（`limit_list_d` 交叉验证的月份依赖、`tradability_at()` 两种"查不到"同返 `None`、退市行被判成 `suspend`、冻结线外验收切片未留票）。详见附录 D。
* **T-01 … T-10** —— 需要特权或人工窗口，`ops/tickets.md` 正文。其中与 M1 强相关的两条：
  **T-01**（`/data/genebench` 规范落点，当前临时寄在 `/data/shared`）与
  **T-06**（`/etc/exports` 把整块 `/data` 以 rw 导给 finance02 —— 网关旁路）。

### 3.3 待批项一条都没被自行执行（逐条取证）

| 项 | 断言 | 实测 |
| --- | --- | --- |
| T-01 | `/data` 仍 root 755 | `owner=root:root mode=755` ✅ |
| T-01 | `/data/genebench` 不存在 | `ls: cannot access '/data/genebench': No such file or directory` ✅ |
| T-01 | `_DEFAULT_ROOT` 未动 | 仍 `/data/shared/genebench` ✅ |
| T-03 | `lxd-installer` 仍在 dpkg | `ii lxd-installer 4ubuntu0.1 all` ✅ |
| T-06 | `/etc/exports` 未改 | mtime `2026-08-18 06:27:34`、md5 `57ac93d0c5d48b42e3094d9412ffd7c1`、内容仍是那一行 rw 导出 ✅ |
| T-07 | 无 NFS 客户端挂载 | `mount -t nfs,nfs4` 空、`/proc/mounts` 无 nfs 行 ✅（fstab 里那条**已启用但未挂**，见 T-11） |
| T-09 | systemd `--user` timer 仍 21 个 | `list-timers --all` = **21**（`list-unit-files --type=timer` = 23，其中 2 个 `disabled`：`quant-datahub-light-daily`、`systemd-tmpfiles-clean`）✅ |
| 红线 2 | `qlib_env` 未被写入 | 目录 mtime `2026-08-02 15:50`、site-packages mtime `2026-08-21 19:14`、`find -newermt 2026-08-30` = **0 个文件**、conda-meta 32 包 ✅ |

**红线 1（无 sudo）与红线 2（不改既有服务/配置）本轮未被触碰。**

### 3.4 残留常驻进程复核

| 检查 | 实测 |
| --- | --- |
| `18080` 是否在听 | ❌ 无（两次绑定实验后均已释放） |
| `192.168.1.48` 上任何监听 | 零 |
| 探针进程 `bindctl` | 无残留 |
| `$GENEBENCH_ROOT/env` 解释器的常驻进程 | 零 |
| 临时脚本 | `$GENEBENCH_ROOT/scratch/m1/` 已 `rm -rf` |
| 既有服务 | `mlflow ui`（`127.0.0.1:5000`）、`quantlab`（`0.0.0.0:8000`）照旧运行，**均非本轮启动，未触碰** |

**网关是关掉的 —— 它从未被打开过。**

---

## 4. M2 开工前必须先解决什么

按依赖顺序，**前三条是硬前置，缺一条 M2 就是在空气上盖楼**。

### 4.1 硬前置（不解决就不能开 M2）

1. **补做卡 1.3（as-of 网关）** —— N-13。
   实施稿把它定义成"执行面访问数据的唯一入口"，M2 的卡 2.1 明写"数据经网关 snapshot 后端喂入"。
   **开工前先定死两件事**：
   (a) `f_ann_date` 的 NULL 口径（N-15）—— 建议 `f_ann_date IS NOT NULL AND f_ann_date <= as_of`，
       并配一条"放行 NULL 会多出多少行"的负控；
   (b) `update_flag` 多版本的取版规则 —— 2026Q1 有 5,678 组多版，**本轮没有定论也没有探针**，
       这是 PIT 里比 `f_ann_date` 更容易错的一半。
   **验收照 `ops/reports/gateway_probe_report.md` 表 A 的 G-01…G-10 逐条建 `ops/test_gateway.py`**，
   那张表就是为这件事写的。
2. **补做卡 1.4（快照版本化）** —— N-14。
   没有 manifest 就没有"两后端一致"的判据，也没有"v1 评测走 snapshot"的执行力。
   注意 `$SNAPSHOTS/v1/` 现在已经被卡 1.1/1.2 的产物占用，**卡 1.4 的 parquet 快照要另起子目录**，
   否则 manifest 会把别人的产物一起算进去。
3. **确定 `access_log` 的格式** —— 它是卡 5.1 前视探针的**唯一**数据源，
   而卡 5.1 是 v1 的"验证验证器"。日志格式定错，L1 探针整族要返工。
   最少要有：`config_id` / `task_id` / 请求全文 / `as_of` / 目标日期 / 判定结果（放行 or 403）/ 时间戳。

### 4.2 需要人工窗口（可与 M2 并行，但越晚成本越高）

4. **T-01：建 `/data/genebench` 规范落点并搬家。** 一条 `sudo install -d`，配置只改一行
   （`genebench_config.py` 的 `_DEFAULT_ROOT`）。**越晚做，要改的引用越多** —— 现在 `snapshots/v1/` 已有 199 MB。
5. **T-06 + T-11：封两条 NFS 旁路。** `/etc/exports` 的 rw 导出（T-06）与 fstab 里那条已启用的客户端条目（T-11）
   是同一块敞口的两半。**网关拦不住文件系统旁路** —— 网关做得再对，这两条开着，红线 3 就是一句话。
   **T-06 的建议动作里请顺手在 finance02 上跑一条 `id ljn`**：若它是 uid 1000，
   `root_squash` 挡不住它读走 `/data/shared/genebench`（含将来的 `reference/`、`scorer/`），
   "答案隔离"这条今天**尚未证实**。

### 4.3 建议但不阻塞

6. **给 `assert_no_wildcard_bind()` 补 IPv6。** 现有断言只认 IPv4 字面量，
   而 finance01 有 tailnet IPv6（`fd7a:115c:a1e0::6201:28cf`）、`ss` 里也有 `[::]` 监听。
   网关若来日绑 `::` 或双栈，现有闸门**拦不住**。
7. **把网关报告 §4 的 PIT 数字变成正式探针**（`ops/test_gateway_pit.py`）。
   现在它们躺在 markdown 里，来源脚本已按纪律删除 —— **会过期且没人发现**。
   对照组：宇宙对账报告的每个数字都由生成器现算，重跑必得同一份，这才是该有的样子。
8. **清 N-01 … N-12。** 都是非阻塞，但 N-06（两个新模块缺"禁绝对路径字面量"守门测试）
   与 N-07（权限审计只审目录不审文件）是**闸门缺位**，会让下一次同类问题继续漏过去，
   建议与 T-01 搬家同批做掉。

---

## 5. 收口自检

| 项 | 状态 |
| --- | --- |
| `ops/progress.md` 完整 | ✅ append-only，本轮追加 `M1-收口` 一行；卡号列覆盖 `0.1` → `M1-收口` |
| 全量验收留档 | ✅ `ops/acceptance/M1-close-full_suite.txt`（505 passed）+ `M1-close-full_suite-first_run.txt`（含写锁抖动原文）+ `M1-close-negctl_reconcile.txt` |
| 两份报告 | ✅ `ops/reports/universe_reconciliation.md`（复核+微调）、`ops/reports/gateway_probe_report.md`（新写） |
| 票据 | ✅ `ops/tickets.md` 新增 T-11 与附录 E（N-13…N-15），速览表已同步 |
| git | ✅ 已提交，工作区干净 |
| 临时文件 | ✅ `$GENEBENCH_ROOT/scratch/m1/` 已删；repo 内未落任何探针脚本（`test_lake_baseline` 的"只有 lake.py 能连湖"护栏未被触发） |
| 常驻进程 | ✅ 无（见 §3.4） |
