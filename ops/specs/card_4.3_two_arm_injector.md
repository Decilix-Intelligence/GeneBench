# 卡 4.3：双臂注入器 —— 把 bundle 的两臂题面与协议工件送进容器，且**不改一个字节**

**代码**：`runner/inject.py`（注入器主体）、`runner/provider_adapter.py`（网关 snapshot → qlib provider）、
`genetask/pin.py`（provider 冻结根，`schema.py` 再导出）、`genetask/packager.py`（+ 导出清单，加法式）、
`runner/c41/runner_core.py`（+ run dir 与 compose 项目名按臂分裂，改既有）。
**验收**：`ops/test_inject.py`。**执行面**：finance02 = `192.168.1.219`，docker 29.1.3 / compose 2.40.3，
runner root `/data/genebench_runner/`。**上游**：卡 3.1 出 bundle，卡 4.1 出隔离与出向策略，卡 2.1a 出冻结 provider。

**设计来源声明**：本卡**没有从任何草案嫁接内容** —— 收到的草案数组为空。全文按签字人硬约束 + 当前 HEAD
的实测代码写成，凡结论都标了出处行号。可当第 0 版规格用，也可当收到真稿后的对照基线。

---

## 0. 本卡不做什么

| 不做 | 归谁 | 为什么在这里点名 |
| --- | --- | --- |
| **不改题面**（不渲染、不做模板替换、不做变量插值、不拼字符串） | 卡 3.1 | 这是本卡唯一的**否定式**核心职责，见 §5 P6 与 T1 |
| 不定义双臂题面的**语义**等价（E1–E13） | 卡 3.1 | 3.1 只保证**题面**等价；**环境**等价是 4.3 自己的责任（§6） |
| 不实现评分、不结算、不碰 gold/scorer | 卡 5.x | 红线 5：scorer 与 gold 永不进执行面 |
| 不定出向白名单的**条目** | 卡 4.1 §3.2 | 本卡只保证「注入不会往白名单里加条目」 |
| 不选模型、不定 `config_id` 矩阵 | 卡 5.x | 臂（arm）与配置（config_id）是**两个正交轴**，不要混（§6.3） |
| 不实现 RD-Agent(Q) 本身 | 被测方 | 本卡只交付它要的 provider 与目录契约（§7） |
| 不重建 provider、不加指数标的 | N-23 / 卡 2.1a | 重建会改 `files.sha256` 根 `54fdda39…`，需一次有意识的 v1.1 |
| 不装 docker、不改 ufw、不动 k3s、不改定时任务 | 待批 | 无 sudo 假设；一律登记 `ops/tickets.md`（§12） |
| 不做记忆探针 | 卡 3.2 / 5.1 | 裸 prompt、无双臂、无容器，不走本注入器 |

---

## 1. 三条必须先说的坏消息（都在当前 HEAD 上实测）

### 1.1 `check_provider_pin` 不存在，而且它**不能**照原样放进 `schema.py`

硬约束把 `genetask/schema.py::check_provider_pin` 当既有代码引用。实测 `schema.py` 的全部顶层定义是
`taskspec` / `x_view` / `json_schema` / `_is_date` / `validate_task` / `undeclared_fields` / `validate_set` / `canonical_json`。
**这个函数要连同 `PROVIDER_SHA256_ROOT` 一起写。** 任何写成「按约束调用 check_provider_pin」的稿子都在引用不存在的东西。

更麻烦的一层：`genetask/schema.py:21` 是 `from reference import artifact_schema as sch`（`packager.py:34`、
`materiality.py:21` 同）。**`import genetask.schema` 会把 `reference/` 拖上执行面** —— 直接撞硬约束
「`reference/` 与 `scorer/` 产物不对执行面暴露」。注入器跑在 f02，它 import 不了 `genetask.schema`。

**决定（I-1）**：常量与函数**定义在新文件 `genetask/pin.py`**，该文件只依赖 `hashlib` / `json` / `pathlib`；
`schema.py` 顶层 `from genetask.pin import PROVIDER_SHA256_ROOT, check_provider_pin` **再导出**，
硬约束点名的路径 `genetask.schema.check_provider_pin` 照样成立。
**为什么不复制一份到 runner**：两份冻结常量必然漂，而漂的那天没有任何东西会报错 —— 这正是要防的形态。
**配一条 import 期闸门**（T11）：`genetask/pin.py` 的 AST 依赖闭包里出现 `reference` 即红。

### 1.2 `packager.check_export` 的两个入参**都是数据面机密**，注入器不能在 f02 调它

`check_export(bundle_dir, gold_sha_set, canary) -> list[str]`（`packager.py:415`）要：

* `gold_sha_set` —— 由 `gold_sha_set(task_dir)`（`packager.py:403`）算自 `reference/tasks/…` 的 gold 切片与私有文件；
* `canary["gold_token"]` —— **gold 金丝雀的明文**。

把这两样送上 f02，等于**为了检查泄漏而先泄漏一次**：gold_token 的定义就是「执行面任何地方出现 = 泄漏」，
而你刚把它写进了执行面的一个文件。任何在 `inject()` 里直接调 `check_export` 的方案都踩这一条。

**决定（I-2，本卡最主要的结构性改动）**：`check_export` **只在 f01 导出时跑一次**，同时产出一份
**导出清单**（每文件 sha256 + 允许前缀 + 该次 `check_export` 的结论），落在 bundle **之外**
（`/data/genebench_runner/manifests/<task_id>.json` —— 落在 bundle 里会被 `X_ALLOWED_PREFIXES`
（`packager.py:46` = `task.yaml`/`arms/`/`image/`/`work/`）判成 G4 红）。
注入器在 f02 只跑 `check_manifest(bundle_dir, manifest)`：**纯 sha256 比对 + 前缀白名单**，不需要任何机密。

**为什么这样仍然够**（写成一句可检验的话）：

> 清单逐字节比对通过 ⟹ bundle 与「在 f01 上通过了 `check_export` 的那份 bundle」逐字节相同
> ⟹ 它的泄漏性质与那份相同。文件内容不变而泄漏出现，在物理上不可能。

清单换来的是**更强**的变更检测（钉死每个文件的 sha，而不只是「没有 gold 内容」），
让出的是「在 f02 现场重新判定泄漏」的能力 —— 而那个能力本来就要靠泄漏机密才能获得。

### 1.3 两臂今天**共用**一个 run dir、一个 compose 项目、一个子网 —— 环境等价现在是假的

`runner_core.py` 实测：

| 行 | 事实 | 后果 |
| --- | --- | --- |
| `task_dir()` = `ROOT/tasks/<task_id>` | run dir **不含 arm** | 两臂共用 `work/`，open 臂能读到 strict 臂残留的 `result.json` |
| `COMPOSE_TMPL` 首行 `name: gb-{task_id}` | 项目名**不含 arm** | 两臂并发时 A 臂的 `down -v`（`:341`）会拆掉 B 臂 |
| `TASK_SUBNET = "172.31.240.0/24"`（`:31`）常量 | 子网**不含 arm/run** | 两臂并发直接被 docker 以「地址池重叠」拒掉 |
| `run_id = f"{task_id}-{arm}"`（`:369`）+ `INSERT OR REPLACE`（`:281`） | run_id 不含 config_id/seq | **重跑静默覆盖上一行遥测**，历史消失且无告警 |
| `(d/"work"/"INSTRUCTION.md").write_text(body)`（`:312`），`body` 取自代码里硬编码的 `HELLO_TASK` | 题面来自**代码**不是 bundle | 这正是 4.3 要替换掉的那一行 |

卡 3.1 的 E1–E13 只保证**题面**等价。上面五条全是**环境**不等价，E1–E13 一条都管不到。
**规格里必须显式写：环境等价归 4.3。**

---

## 2. 落点与新增文件

```
genetask/pin.py             新：PROVIDER_SHA256_ROOT + check_provider_pin（零 reference 依赖）
genetask/schema.py          改：顶层再导出上面两个名字（硬约束点名的路径成立）
genetask/packager.py        改（加法）：export_manifest() / check_manifest()，不动 check_export 签名
runner/inject.py            新：注入器主体
runner/provider_adapter.py  新：网关 snapshot → qlib provider（复用卡 2.1a 冻结 provider）
runner/c41/runner_core.py   改：run dir / 项目名 / 子网 / run_id 按「运行」分裂；lint_compose 加 expect_workdir
ops/protocol/geneprotocol_v1/MANIFEST.json  新：strict 臂协议工件的**封闭**清单（每文件 sha256）
ops/test_inject.py          新：T1–T18 闸门（T16–T18 = TK-1 的三条判据，§8.1）
ops/tickets.md              改：登记 TK-1..TK-5，**不执行**
```

**大文件一律落 `/data`**：manifests、runs、provider 副本全在 `/data/genebench_runner/` 下，仓库里只有代码与清单。

---

## 3. 两面切分：哪一步在哪台机器上跑

| # | 步骤 | 机器 | 输入含机密？ | 依据 |
| --- | --- | --- | --- | --- |
| A | `build_task` / `write_task` / 渲染两臂 | f01 数据面 | 是（gold、solution、scorer） | 卡 3.1 |
| B | `export_task` 剥 D 键 | f01 | 是 | `packager.py:383` |
| C | `check_export` + `export_manifest` | **f01** | 是（gold_sha_set、gold_token） | §1.2 |
| D | 搬运 bundle + 清单 → f02 | f01→f02 | 否 | 只搬 bundle 与清单 |
| E | `check_manifest` + `check_provider_pin` + `inject` | **f02** | **否** | §1.2 / §1.1 |
| F | 起容器、跑、收产物、遥测 | f02 | 否 | 卡 4.1 |
| G | 金丝雀收尾扫描 | f02 | **否 —— 按格式正则，不按明文令牌** | §6.4 |
| H | 结算、判分 | f01 | 是 | 红线 5 |

**这张表是本卡的骨架。** 每加一个「注入器要检查 X」的要求，先问 X 的输入落在哪一列；
落在「是」那一列而步骤在 f02，就是在把机密往执行面搬。

---

## 4. 接口签名

```python
# genetask/pin.py —— 零 reference 依赖
PROVIDER_SHA256_ROOT = "54fdda39…"        # 卡 2.1a 签字冻结；改它必须走 N-23 的 v1.1 流程

def provider_root_sha256(provider_root: Path | str) -> str:
    """对 provider 树算根：把每个文件算成 f"{relpath}\\0{sha256(bytes)}\\n"，
    按 relpath 的**字节序**排序后拼接再 sha256。目录名、mtime、owner 一律不进。"""

def check_provider_pin(provider_root: Path | str, *,
                       expect: str = PROVIDER_SHA256_ROOT) -> list[str]:
    """核 provider 的 sha256 根。返回问题列表，空列表 = 绿（与 check_export 同风格）。
    **三条不得妥协**：
      1) 根**现算**，不读 provider 自带 manifest 里记的那个值 —— 只读记录值等于没查（F7）；
      2) provider_root 不存在 / 根文件缺失 / 树为空 → **返回非空**，不是「跳过」（F1）；
      3) 不一致时把「多了哪些 / 少了哪些 / 变了哪些」前 10 条列出来 —— 只说「不一致」无法定位。"""

# genetask/packager.py —— 加法，不动既有签名
def export_manifest(task_dir: Path, bundle_dir: Path, *,
                    check_export_result: list[str]) -> dict:
    """f01 侧：算 bundle 每文件 sha256 + 允许前缀 + 本次 check_export 结论 + 生成时间 + packager_version。
    `check_export_result` 非空时**拒绝出清单**（不给红的 bundle 发通行证）。"""

def check_manifest(bundle_dir: Path, manifest: dict) -> list[str]:
    """f02 侧：**纯比对**。文件集精确相等（多一个、少一个都是红）、每个 sha256 相等、
    每条路径命中 X_ALLOWED_PREFIXES、manifest 里 check_export 结论为空。不需要任何机密。"""

# runner/inject.py
def inject(bundle_dir: Path, arm: str, *, run_root: Path, provider_root: Path,
           config_id: str, capabilities: dict, seq: int = 1) -> Path:
    """把一臂的 instruction 与协议工件送进该臂**独占**的 run dir，返回 run dir。
    不改题面：只做逐字节复制 + sha256 核对。任一步非空即抛 packager.PackError，**不吞**。"""
```

**为什么统一用「返回问题列表」而不是抛异常/返回 bool**：仓库里 `check_export`、`lint_dockerfile`、
`lint_compose`、`validate_task` 全是这个形状，聚合与测试都靠它。返回 bool 的检查在聚合时会丢掉「红在哪」，
而「红在哪」是 §4 第 3 条要求的东西。

---

## 5. 注入顺序 P0–P9（固定，不可调换）

任一步返回非空 ⇒ `raise PackError`，**不吞、不降级、不「记个 warning 继续」**。

| # | 步骤 | 红的条件 | 为什么在这个位置 |
| --- | --- | --- | --- |
| **P0** | 前置自检：`docker compose version` 可跑、当前用户在 docker 组、`run_root` 可写、磁盘余量 > 阈值 | 任一不满足 | 无 sudo 假设下这些都可能不成立；**磁盘余量**尤其要查 —— 满盘会让 P6 的复制**截断**而不报错 |
| **P1** | `arm in schema.ARMS`（`schema.py:32` = `("strict","open")`） | 不在 | 拼错臂名会安静地建出第三个 run dir |
| **P2** | `check_provider_pin(provider_root)` | 非空 | **在做任何复制之前** —— provider 错了整批实验作废，越早红越省事 |
| **P3** | `check_manifest(bundle_dir, manifest)` | 非空 | 见 §1.2。这是 f02 上唯一合法的 bundle 完整性判据 |
| **P4** | `lint_dockerfile((bundle_dir/"image"/"Dockerfile").read_text())`（`packager.py:268`） | 非空 | L1：FROM 必须带 digest、无 `ADD http`、CMD/ENTRYPOINT 不装依赖 |
| **P4b** | 镜像 digest ≠ `IMAGE_DIGEST_PLACEHOLDER`（`packager.py:43` = `sha256:` + 64 个 `0`） | 是占位值 | 占位 digest 能过 L1 的正则，却意味着**跑的是没钉住的镜像**；两臂各跑一次可能拿到不同镜像 |
| **P5** | `_check_tests_source(...)`（`packager.py:297`） | 非空 | G5：容器内 tests 不得 `import reference.*` |
| **P6** | 复制 `arms/INSTRUCTION.{arm}.md` → `run/work/INSTRUCTION.md`，**逐字节**；核 `sha256 == task.yaml` 的 `instruction[arm].sha256` | 不等 | `json_schema()`（`schema.py:179`）已要求 `instruction.<arm>` 有 `path` + `sha256` 两个字段，判据现成 |
| **P7** | 按 §6.2 白名单装配 `run/work/` 其余内容；strict 臂再叠 `ops/protocol/geneprotocol_v1/MANIFEST.json` 的**精确**文件集 | 文件集 ≠ 清单 | 见 F8：协议工件少一个，strict 臂静默退化成半个裸臂 |
| **P8** | 复制**之后**再跑一次 `check_manifest`，并对 `run/work/` 跑 `check_run_dir()` | 非空 | 见 F2。**注意**：不能拿 `check_export` 去扫 run dir —— run dir 有 `INSTRUCTION.md`、`compose.yml`、`provider/`，会被 `X_ALLOWED_PREFIXES` 全判成 G4 红。run dir 有自己的形状，要自己的检查 |
| **P9** | 渲染 compose（§8）→ `lint_compose(text, expect_workdir=run/work)` → 落盘 | 非空 | lint 在**落盘前**跑；先落盘再 lint，红了也已经有一份可被 `docker compose -f` 直接用的文件躺在那 |

**P2 在 P3 之前的理由**：provider 是**整批**共享的，bundle 是**单题**的。先查共享的那个，
一次红能省掉 40 题 × 2 臂的无效注入。

---

## 6. run dir 布局，与「两臂差异」的**封闭**定义

### 6.1 布局

```
/data/genebench_runner/
  manifests/<task_id>.json              ← f01 发的通行证（§1.2）
  provider/<pin>/                        ← 冻结 provider 的本机缓存，按 sha256 根命名
  runs/<run_id>/                         ← run_id = f"{task_id}.{arm}.{config_id}.r{seq:02d}"
     bundle/                             ← bundle 的逐字节副本；check_manifest 直接指它
     work/                               ← 挂进容器的 /task（唯一的宿主可见目录，见 TK-1）
        INSTRUCTION.md                   ← 逐字节等于 bundle/arms/INSTRUCTION.<arm>.md
        <stage>.json                     ← artifact schema，export_task 已放进 bundle work/
        <inputs…>                        ← 题面里写的 /task/x.parquet 就是这里
        provider/                        ← §7；两臂各一份**独立**副本
        [协议工件…]                       ← 仅 strict 臂，且仅 MANIFEST.json 列出的那些
     log/                                ← egress.jsonl 等；每次运行自己一份
     compose.yml
     inject.json                         ← 注入清单：每个落盘文件的 sha256 + 来源 + 时间
```

**run dir 按 `run_id` 而不是 `<task_id>/<arm>` 分层的理由**：`run_id` 里要有 `config_id` 与 `seq`。
`runner_core.py:369` 现在的 `run_id = f"{task_id}-{arm}"` 配上 `:281` 的 `INSERT OR REPLACE`，
**重跑会静默覆盖上一次的遥测行**（F9）。目录与主键用同一个 `run_id`，磁盘上的证据与库里的行一一对应。

**docker compose 项目名**：`gb-` + `run_id` 里的 `.` 换成 `-`。compose 项目名只接受
`[a-z0-9][a-z0-9_-]*`，带 `.` 会被 compose 直接拒（这是**会当场报错**的那类问题，写下来是为了别在联调时才发现）。

### 6.2 两臂差异必须是**等号**，不是包含号

```
files(run_strict/work)  \  files(run_open/work)  ==  PROTOCOL_ARTIFACTS      （精确相等）
files(run_open/work)    \  files(run_strict/work) ==  ∅
两侧同名文件：除 INSTRUCTION.md 外，sha256 必须**逐个相等**
```

**为什么是等号**：写成「差异 ⊆ {INSTRUCTION.md, 协议工件白名单}」时，**少给** strict 臂一个协议工件
也满足 ⊆。那不是隔离失败，是**干预失败** —— 协议臂静默退化成半个裸臂，实验照跑、分数照出，
结论会变成「协议没用」。⊆ 抓不到它，等号能（F8）。

`PROTOCOL_ARTIFACTS` 取自 `ops/protocol/geneprotocol_v1/MANIFEST.json`，**每条带 sha256**。
「协议工件 = 某个目录里当时有的东西」是不可接受的定义 —— 那个目录会长东西。

> **卡 4.1（2026-09-07）**：臂与它投放的工件集合现在定义在 **`genetask/arms.yaml`**，
> 不再写死在注入器里。本节的 `PROTOCOL_ARTIFACTS` 对一般的臂读作
> **「该臂 `artifacts[]` 的展开集」**（`runner/inject.py::arm_files(arm)`），
> `strict` 臂的展开集逐字节仍是这份清单。三条子句、等号、逐题规则的处置全部不变。
> 泛化后的完整表述与指令变体臂的例外见**公平性协议 §6.6**。

### 6.3 臂（arm）与配置（config_id）是两个正交轴

环境等价断言只在**同 config_id、不同 arm** 的两个 run dir 之间成立。
容器环境变量里 `GENEBENCH_ARM` 两臂必然不同、`GENEBENCH_CONFIG_ID` 两臂必然相同：

```
env(run_strict) Δ env(run_open) == {"GENEBENCH_ARM"}          （对称差，精确相等）
```

`timeouts` 与 `image` 取自同一份 X task.yaml（`X_KEYS` 含二者，`schema.py:36`），
**不许按臂覆写**。裸臂时限短一点，得到的差异会被读成「协议提升了效果」—— 这是与被测变量同向的偏差，
它不会把结果打散，会把结果**排好序**（与卡 4.1 §4 对模型 cutoff 的论证同形）。

### 6.4 金丝雀收尾扫描按**格式正则**，不按明文令牌

`schema.py:146` 的 `_CANARY` 把三串的**格式**写死了：`GBC-G-[0-9a-f]{16}` / `GBC-C-…` / `GBC-X-…`。
执行面扫描一律用**不带锚的同款正则**，**不需要**、也**不许**拿到 gold_token 的明文：

| 串 | 执行面判据 | 命中处置 |
| --- | --- | --- |
| `GBC-G-` | run dir 全树**零命中** | run 级 `leaked`，单列，不计分、不进 gate_failed（卡 3.1 §5） |
| `GBC-X-` | 只许出现在 `bundle/task.yaml`（`export_task` 把它写成首行注释，`packager.py:392`） | 同上 |
| `GBC-C-` | 每臂 `INSTRUCTION.md` 里**恰好一次**，且两臂是同一个值 | 零命中 = **扫描器坏了**，该次扫描无效（非空证明） |

**这条同时解决了 §1.2 的残余问题**：C1 的非空证明不需要机密（token 就在本地 instruction 里），
G3 的 gold 检测也不需要机密（按格式抓，任何值都算）。**gold_token 的明文永远不离开 f01。**

**已知边界（承自卡 3.1）**：金丝雀只抓**文件级原样搬运**。parquet → CSV 重序列化会丢 metadata，
零命中 ≠ 无泄漏。内容级泄漏靠「oracle 不进容器 + `reference/` 0700」守，不靠这里。

### 6.5 身份在源头注入（N-36 修的是校验层，源头还没修）

N-36 修的是**校验层**：`validate(config_id=...)` 改成接受 runner 侧真值，对不上判 `config_id_mismatch`；
空切片配上「该 task_id 名下日志非空」判 `config_id_slice_empty`，绝不当成「零请求」
（`ops/tickets.md` 附录 X）。它**没有动日志是怎么写出来的**。网关侧实测：

* `gateway/app.py:45-46` 定义 `x-genebench-config-id` / `x-genebench-task-id`；
* `:82-83`（中间件）与 `:141-142`（异常处理器）**直接从请求头取**，无任何核对；
* 三处 `access_log.record()`（`:99` 参数畸形拒、`:114` 正常路径、`:132` 异常处理器）原样透传；
* `gateway/access_log.py:42-57` 的 `record()` 签名里只有 `config_id` / `task_id` ——
  **没有 `run_id`，也没有 `arm`**。

而这两个头是**任务容器自己填的**：`runner/c41/runner_core.py:317-319` 的样例 agent 就是
`os.environ.get("GENEBENCH_CONFIG_ID", "")` 直接塞进请求头。容器内环境变量可写、请求头可改，
所以**切片键的源头仍然是被测方的自报值** —— 校验层能抓「自报值 ≠ 本次运行的真值」，
抓不到「自报值被改成**另一次运行的**合法真值」。两臂并发跑同一个 config 时，
strict 臂完全可以把自己的请求记到 open 臂名下，两边的日志都还是「合法」的。

**改法：身份由代理边车在入口注入，不由客户端自报。**

任务容器到网关**只有一条路**：`gb_task` 是 `internal: true`，任务服务的
`GENEBENCH_GATEWAY=http://gateway:18080` 与 `HTTP_PROXY=http://gateway:3128` 都指向边车
（`runner_core.py:69-107`）。边车在**可信侧**、其环境变量由 compose 从 run dir 渲染，
容器内改不到 —— 它是唯一且可信的注入点。

| # | 规则 | 为什么 |
| --- | --- | --- |
| **ID-1** | **先剥后注**：先删掉客户端带来的 `X-GB-*` **全类**请求头（大小写不敏感，**含重复出现的同名头**），再写入 runner 真值。禁止「只追加不删除」 | **实测（starlette 1.3.1，网关所用版本）**：`Headers(raw=[(b"x-genebench-task-id", b"FAKE"), (…, b"REAL")]).get(...)` → **`"FAKE"`**，即 `.get()` 取**第一个**。`app.py:82-83` 用的正是 `.get()` —— 只追加不剥，客户端抢先写一份就赢了，注入等于没做 |
| **ID-2** | 注入四个字段：`run_id` / `task_id` / `config_id` / `arm`，值取**边车自己的环境变量** | 边车 env 由 runner 写死在 compose 里；任务容器与它不共享文件系统也不共享 env |
| **ID-3** | **切片键退化为 `run_id`** | `run_id = f"{task_id}.{arm}.{config_id}.r{seq:02d}"`（§6.1）已经**蕴含**臂、配置与第几次重跑，且与 run dir 一一对应（因而蕴含时间窗）。卡 4.2 §7.2 要的三重切片 `(task_id, config_id, [started_at, finished_at])` 被这一个键整体覆盖。**两臂并发同 config 也不串** —— arm 不同则 run_id 不同 |
| **ID-4** | `access_log.record()` **增列** `run_id` / `arm`（加法，默认 `None`，不动既有列与既有字段序） | 现签名里没有这两列（`access_log.py:42-57`）。不加列，注进来的真值没有地方落 |
| **ID-5** | 身份三核（卡 4.2 §6）**保留**，降为第二道防线 | 见下 |

**这条改动有一处不是免费的，必须写明**：边车今天在网关端口上是**纯 TCP 转发** ——
`c41/egress_proxy.py:245 forward_server()` 建连后交给 `:217 pipe()`，逐 65536 字节双向 splice，
**根本不解析 HTTP**。剥头 / 注头要求它在这条路径上升级成 **HTTP 层反向代理**。随之两条：
① keep-alive / 流水线连接上**每一个请求**都要重新剥注，「按连接盖一次章」不够；
② 请求体与 `Transfer-Encoding` / `Content-Length` 必须照搬不改 —— 注入器不许改数据面字节（§1 同纪律）。
这项改动落在卡 4.1 的 `egress_proxy.py` 上，走 §12 末尾「另需与卡 4.1 协调」那条。

**为什么三核不能因此取消（纵深防御）**：源头注入守的是**网关日志**这一条数据面。
artifact 信封里的 `(task_id, config_id, arm)` 是**另一条** —— 由 agent 写进产物，边车碰不到它。
三核比的正是这两条是否指向同一次运行；只修源头、删掉三核，等于允许信封自报成另一次运行的身份而无人比对。
两道防线守的不是同一个洞。

**负例（写成验收条件 T15）**：容器内伪造身份头，网关日志仍记 runner 真值。

---

## 7. provider 适配层：网关 snapshot → qlib provider

**硬约束**：RD-Agent(Q) 的数据走「网关 snapshot → qlib provider 适配层」，复用卡 2.1a 的冻结 provider，
**不接社区 channel**。

| # | 决定 | 为什么 |
| --- | --- | --- |
| PA-1 | 本机缓存 `/data/genebench_runner/provider/<pin>/`，目录名就是 sha256 根 | 目录名带 pin，「缓存里放的是哪一版」这个问题不可能答错；N-23 重建后是**新目录**，不是覆盖 |
| PA-2 | 物化后立刻 `check_provider_pin`，**再**入缓存；两臂从缓存**各复制一份**到 `run/work/provider/`，复制后**各自再核一次根** | 复制后重核是为了抓**截断** —— 盘满时 `copytree` 可能只写了一半而返回成功，症状是「因子算出来了，就是数不对」 |
| PA-3 | **两臂不共享** provider 目录、不共享只读挂载 | 共享一份等于共享一个可写入口；F5 的环境等价一旦破，双臂对照就不成立 |
| PA-4 | 适配层**只**从网关的 8 个端点取数（`/bars` 带 `fields`、`/universe`、`/calendar` 等），每次请求带 `as_of` 与 `x-genebench-task-id` | 网关 `access_log` 是卡 5.1 前视探针的数据面结算源；绕过它取数在日志里表现为**什么都没有**，而「什么都没有」与「这次没取数」不可区分 |
| PA-5 | 适配层禁止写 qlib 的社区 channel 配置；镜像构建期就把 `qlib` 的 `provider_uri` 钉到容器内路径 | 运行期改 provider_uri = 运行期换数据源，且 L-8 扫不到 |
| PA-6 | provider 物化在**注入期**（f02 runner 侧，可信方），不在容器里 | 容器里跑 = 让不可信方决定自己拿到什么数据 |

**一条必须实测、不许假设的事**：`ops/test_qlib_provider.py` 查的是「provider digest **与 manifest 里的绝对路径**」，
`reference.calibration` 的 `calibration.json` 里也记了 provider 的**绝对路径**（`ops/tickets.md:1249-1254`）。
容器内 provider 落在 `/task/provider/`，与 f01 上的绝对路径不同。
**判据（T12）**：容器内 `qlib.init(provider_uri=/task/provider)` 后跑一组固定查询，
结果必须与同一组查询在 f01 冻结 provider 上的结果**逐字节相同**。
路径无关性是**测出来的**，不是推出来的；若测不过，走 **TK-4 裁定（2026-09-03 已批准，§12）** ——
容器内同路径落盘 `/data/genebench/provider/`。**先测 T12，测过就不许用这条**：它是备用路径，不是默认路径。

---

## 8. compose 渲染约束（模板渲染，不手写）

沿用 `runner_core.py:69` 的 `COMPOSE_TMPL` 与 `lint_compose`（L-1..L-9 见卡 4.1 §5），本卡加四条：

| # | 规则 | 为什么 |
| --- | --- | --- |
| IN-1 | **子网按运行动态分配**：从 `172.31.240.0/20` 里取两个连续 /24（task + egress），登记在 `inject.json` | `TASK_SUBNET` 现在是常量（`:31`），两臂并发必然撞池；`/20` 给 8 个并发运行 |
| IN-2 | 候选子网必须与下列**全部**做 `ipaddress.ip_network().overlaps()` 判否：`10.42/16`、`10.43/16`、`10.88/16`、`192.168.1.0/24`（LAN）、`100.64.0.0/10`（tailscale CGNAT）、**以及 `docker network inspect` 当前已分配的每一个网段** | `lint_compose:197` 的 L-4 是**子串**匹配（`"10.42." in text`）。`10.40.0.0/13` **覆盖** 10.42/16 与 10.43/16，却一个禁用子串都不含 —— 当场假绿。docker 自己的默认地址池也在 172.16/12 里，硬编码一个 172.31.240 是在跟 docker 抢地址 |

**落地状态（2026-09-05，A4）**：**两条都已实现**，见 `runner/c41/subnets.py`。
IN-2 的判据从子串换成 `ipaddress.overlaps()`，保留集扩到五条并**每条写清是谁的**；
`10.40.0.0/13` 这个反例**已进 `negctl_lint.py`**（旧判据对它当场全绿，实测确认）。
IN-1 从 `172.31.240.0/20` 取连续 /24（8 组并发），与 `docker network inspect`
实时结果一起判否，结果写进 `inject.json`；池满**抛异常不回绕**。
`require_docker=False` 的路径**没有并发保证**，这句话会写进 `docker_probe` 字段。
| IN-3 | `command` **不写进 compose**，由镜像的 ENTRYPOINT 决定 | compose 里能写 command，就能给两臂写不同的 command，而 E1–E13 一个字都管不到 compose。命令进镜像后，运行期装依赖由 `lint_dockerfile`（`packager.py:268`）的 CMD/ENTRYPOINT 规则把住 |
| IN-4 | `lint_compose` 增开 `expect_workdir: Path | None = None`；给了就要求任务服务的 bind-mount 源**经 `realpath` 解析后**与它**精确相等**，且解析后的路径**在 runs 根之下、不在任何数据根之下**（DATA_ROOTS 清单见 §8.1）。**这是 TK-1 (a) 的落地形态**，验收见 T16–T18 | 现行 L-5（`:204-208`）只查 `"/tasks/" not in src`，是**子串**判定：`/data/genebench_runner/tasks/`（整棵树，含别的题）能过；而新布局 `runs/<run_id>/work` 里没有 `/tasks/`，**反而会被误判成红**。两个方向都错，必须改成等号。默认 `None` 保持卡 4.1 的 10 个负例原样绿 |

端口：v1 **任何服务都不得发布端口**（L-6）。L-1/L-2 的 `192.168.1.219:PORT:PORT` 格式规则保留 ——
它管的是「万一将来批准发布端口，格式得对」，不是 v1 的实际策略。两条不可互相替代（卡 4.1 §5 已论证）。

代理边车的两处宿主挂载（`egress_proxy.py:ro` 与 `log/`）在 **gateway 服务**上，L-5 只查 task 服务。
这不是遗漏：任务容器接的是 `internal: true` 的 `gb_task`，它看不见边车的文件系统。
**TK-1 裁定确认这条**：唯一例外只对 **task 服务**成立，边车的两处挂载按其所在服务另论，
但 `lint_compose` 必须**逐服务**判定，不许「整个文件里有几个 bind」这种全局计数（见 §8.1 第 3 条）。

### 8.1 TK-1 (a) 的可测形态：唯一 bind-mount 例外的三条判据

裁定保留「runner 为该次任务创建的工作目录」这一**唯一**例外（TK-1 选 (a)），
代价是 L-5 必须从子串判定收紧成下面三条。三条**全部**由 `lint_compose(expect_workdir=…)` 实现，
每条各配 `ops/test_inject.py` 的一个测试（T16 / T17 / T18）。

**判据 1（等号，经 realpath）**：任务服务的 bind 挂载**恰有一个**，其源
`Path(src).resolve(strict=True)` 与 `(run_dir/"work").resolve(strict=True)` **字符串精确相等**。
不许前缀、不许包含、不许 `startswith`。
**为什么必须先 `realpath`**：不解析时 `runs/<run_id>/work/../work`、尾斜杠、
以及**指向 `work/` 的符号链接**三种写法都能让「精确相等」失败或成功得莫名其妙 ——
而符号链接是最坏的一种：`src` 字面量长得完全正确，解析后落在别处。

**判据 2（落点，双向）**：解析后的路径必须满足
`RUNS_ROOT.resolve() in mnt.parents`（**在 runs 根之下**，且是真子孙不是自身），
**且**对 `DATA_ROOTS` 的每一条 `d`：`d != mnt and d not in mnt.parents`（**不在任何数据根之下**）。
**`RUNS_ROOT` 自身也要过第二个断言** —— 否则把 `run_root` 设成 `/data/market_lake_f02/runs`
就能让判据 1、判据 2 前半段同时为真，而挂进去的东西坐在湖里面。

`DATA_ROOTS`（**f02 实测，2026-09-03，`ls -ld /data/*/`**；清单是**封闭列举**，加一个新目录必须同步改这里）：

| 路径 | 权限 | 为什么在表内 |
| --- | --- | --- |
| `/data/market_lake_f02/` | `drwxr-xr-x`（world-readable） | N-29：40 GB 本地湖副本，45,661 文件。挂到它或它的任何父路径 = 直读整个湖，**不需要 NFS** |
| `/data/shared/` | `drwxrwxrwt`（world-writable, sticky） | 任何用户可写 —— 不可信方一旦可达即有写入面 |
| `/data/projects/` | `drwxrwxr-x root:root` | 非 genebench 资产，执行面无理由可达 |
| `/data/health/` | `drwxr-xr-x wx:wx` | 同上，且属另一个用户 |
| `/data/genebench_runner/manifests/` | — | f01 发的**通行证**（§1.2）。可写它 = 能伪造清单（TK-5 的同一条链） |
| `/data/genebench_runner/provider/` | — | 冻结 provider 的本机缓存。可写它 = 全批实验静默跑在错 provider 上（F1） |
| `/data/genebench_runner/{tasks,results,spike}/` | — | 旧布局与产物落点；`runs/` 之外的一切一律不可达 |

**`/data` 本身故意不在表内。** 它是 `RUNS_ROOT` 的祖先，写进 `DATA_ROOTS` 会让判据 2 永假、
整条规则恒红。`/data` 的可达性由判据 1 的等号封死 —— 挂 `/data` 时 `mnt != work`，当场红。
**这一条要写进代码注释**，否则下一个人会「顺手补全」这张表而把规则弄成恒红，然后把它注释掉。

> **实测旁注（2026-09-03）**：f02 的 `/etc/exports` 仍有活的
> `/data 192.168.1.48(rw,sync,no_subtree_check,root_squash)`（`showmount -e localhost` 确认，
> `rmtab` 为空 = 当前无人挂载）。即 `/data` 不只是本地数据根，还是一个**对 f01 开着的 rw 导出根**。
> 这条与 W1-b 的关闭记录冲突（见返回件），但不改变本节判据 —— 反而是它成立的又一个理由。

**判据 3（写法穷举）**：L-5 必须看得见 bind 的**三种**写法，只扫一种就是规则沉默：

| # | 写法 | 今天的 L-5 |
| --- | --- | --- |
| a | service 短语法 `volumes: ["<src>:/task"]` | 看得见（子串判定） |
| b | service 长语法 `volumes: [{type: bind, source: <src>, target: /task}]` | **看不见** |
| c | 顶层 named volume + `driver_opts: {type: none, device: <src>, o: bind}`，service 按名字引用 | **看不见** —— 这是一个**伪装成 named volume 的 bind mount** |

(c) 是最要命的一种：它在 service 的 `volumes:` 里长得和一个普通 named volume 一模一样，
「全用 named volume」这句话本身（TK-1 的备选 (b)）在它面前也是假的。
**判据 3 因此不是补丁，是把规则的观测面补齐** —— 与卡 3.1 §7h 那 38 处同一形态：
**规则沉默必须被观测到，不能被推断。**

---

## 9. 验收条件（每条 = `ops/test_inject.py` 里一个测试）

| # | 断言 | 这条会怎么**假绿** |
| --- | --- | --- |
| **T1** | `sha256(run/work/INSTRUCTION.md) == sha256(bundle/arms/INSTRUCTION.<arm>.md) == task.yaml.instruction[arm].sha256`；两臂各一条 | 注入期做了模板渲染 / 变量替换 / 行尾换行归一化 |
| **T2** | §6.2 的两条**等号**：`strict \ open == PROTOCOL_ARTIFACTS`、`open \ strict == ∅`；同名文件 sha 逐个相等（INSTRUCTION.md 除外） | 写成 `⊆` —— 少给协议工件也算过（F8） |
| **T3** | `env(strict) Δ env(open) == {"GENEBENCH_ARM"}`；`timeouts`、`image` digest 两臂逐字节相同 | 只比 env 的键集，不比值 |
| **T4** | 篡改 provider 任一字节 → `inject` 红；**删掉根文件 → 也红**；provider 目录不存在 → 红；只改 provider 自带 manifest 里记的 digest → **仍红**（因为是现算） | 缺文件被写成 skip（F1）；只读 manifest 记录值（F7） |
| **T5** | 容器内连非白名单目标 → **拒绝**且 `elapsed < 2s`；连 `192.168.1.48:18080` → 通 | 「拒绝」配成 60s 超时，测试照样绿（F4） |
| **T6** | 三串金丝雀按 §6.4 的**正则**判：`GBC-G-` 全树零命中、`GBC-X-` 只在 `bundle/task.yaml`、`GBC-C-` 每臂恰一次且两臂同值 | 拿明文 gold_token 上执行面来扫（§1.2）；或漏掉「零命中 = 扫描器坏了」的非空证明 |
| **T7** | 选出的两个子网与 §IN-2 的**全部**集合 `overlaps()` 为假，含 `docker network inspect` 的实时结果 | 只比字符串前缀 —— `10.40.0.0/13` 反例必须在测试里 |
| **T8** | 每条 ports（若有）匹配 `^192\.168\.1\.219:(\d+):\1$`；v1 下 `ports` 必须为空（L-6） | 只测格式，不测「v1 根本不许有」 |
| **T9** | `lint_dockerfile` 为空；镜像 digest ≠ `sha256:0…0` 占位值 | 只跑 lint，不查占位 digest（P4b） |
| **T10** | 容器内 `cat /proc/mounts` 无 nfs、无宿主 `/data`；`ls /data` 失败；`import reference` 抛 ImportError；run dir 全树无 `scorer`/`gold` 路径 | 在宿主上查而不是在容器里查 |
| **T11** | `genetask/pin.py` 的 **AST 依赖闭包**不含 `reference`；`import genetask.pin` 后 `"reference" not in sys.modules` | 只 grep 文件里的 `import reference` 字面量，抓不到间接依赖 |
| **T12** | 容器内 `qlib.init(provider_uri="/task/provider")` 的一组固定查询结果 == f01 冻结 provider 上同一组查询结果，逐字节 | 只比行数 / 只比 shape |
| **T13** | 用一个**被改过一个字节**的 bundle 走 `inject` → P3 红；用 `check_export` 结论非空的 manifest → `export_manifest` 拒绝出清单 | 清单只记文件集不记 sha |
| **T14** | 同 `(task_id, arm)` 连跑两次 seq=1/2 → 两行遥测**都在**，两个 run dir **都在** | `INSERT OR REPLACE` 覆盖了第一行而无人发现（F9） |
| **T15** | **伪造身份头的负例（§6.5）**：任务容器发一个请求，把 `x-genebench-task-id` / `x-genebench-config-id` 写成**另一次运行**的合法值，并自带一个 `X-GB-Run-Id` / `X-GB-Arm`；断言网关 `access_log` 落下的那一行 `run_id`/`task_id`/`config_id`/`arm` **逐个等于 runner 真值**，且**没有任何一个字段等于伪造值**。同一 keep-alive 连接上**连发两个**请求，第二个同样成立 | 只在边车入口断言（那里当然是真值），不去读网关**实际落下**的那一行；或只测第一个请求 —— 按连接盖一次章的实现能过第一个、漏掉第二个 |
| **T16** | **TK-1 判据 1**（§8.1）：任务服务 bind 挂载数**恰为 1**，且 `realpath(src) == realpath(run_dir/"work")`。**五个负例必须红**：① 挂父目录 `runs/<run_id>`；② 挂同级另一个 run 的 `work/`；③ `src` 是**指向 `work/` 的符号链接**；④ `runs/<run_id>/work/../work` 绕路写法；⑤ 挂两个 bind（一个对的 + 一个别的） | 用字面量字符串比而不 `realpath` —— ③ 当场放行，`src` 长得完全正确；或只查「有没有一个对的」而不查「有没有多的」，⑤ 放行 |
| **T17** | **TK-1 判据 2**（§8.1）：`RUNS_ROOT in mnt.parents` 为真；`DATA_ROOTS` 每一条都不是 `mnt` 也不在 `mnt.parents` 里。**负例**：`run_root=/data/market_lake_f02/runs` 时判据 1 仍绿而本条必须红；挂 `/data`、`/data/shared`、`/data/genebench_runner/manifests`、`/data/genebench_runner/provider` 各一例必须红 | 把 `/data` 也写进 `DATA_ROOTS` → 规则**恒红**，下一个人会把它注释掉；或只查 `mnt` 不查 `RUNS_ROOT` 自身的落点 |
| **T18** | **TK-1 判据 3**（§8.1）：三种 bind 写法（短语法 / `type: bind` 长语法 / 顶层 named volume 带 `driver_opts.device` + `o: bind`）**各一个负例**，`lint_compose` 三个都要报。**元测试**：把三个负例逐个喂给**改造前**的 L-5，必须实测到 (b)(c) **沉默** —— 沉默是被观测到的，不是被推断的 | 只扫 service 的 `volumes:` 短语法；(c) 在 service 段里长得和普通 named volume 一模一样，肉眼与 grep 都过 |

**闸门脚本必须 `exit ${PIPESTATUS[0]}`。** 管道吞退出码这个项目已经因此两次带红入库（`ed69380`、`f2dd812`）。

**判别力前置条件**：T2/T4/T13 都靠「改一个字节看它红不红」证明。凡此类测试一律先过
`packager.assert_mutated(before, after, what)`（`packager.py:504`）—— 突变空转会让判别力测试**恒绿**：
不是产物静默错，是**测试静默空**（卡 3.1 §7 修正一）。

---

## 10. 失败模式（全部是「静默失败 / 假绿」形态）

| # | 失败模式 | 症状 | 挡在哪 |
| --- | --- | --- | --- |
| **F1** | provider pin 文件缺失被当成「跳过」 | `ops/capabilities.json` 的 `n23_index_instrument: false`。N-23 一旦为指数标的重建 provider，冻结根就变；注入器若「找不到就放行」，**整批实验静默跑在错 provider 上**，没有任何东西报错 | P2 + T4：**缺文件 = 红** |
| **F2** | bundle 在导出之后、注入之前被改 | `check_export` 现在只在导出时跑一次。run dir 里被改过的 bundle 不会被发现 | P8 复制后**再跑一次** `check_manifest` |
| **F3** | 起容器成功 ≠ 容器活着 | `docker compose up -d` 返回 0 而容器随即退出；`runner_core.py:335` 对 `up -d gateway` 的返回码**根本没查** | 探活 + 带回退出码；`:364` 现有的「`starts != 1` 即抛」是同一族防线，保留 |
| **F4** | 出向「拒绝」写成「超时」 | 60s 超时也让 T5 变绿，而真实语义完全不同（超时意味着**有路由**，只是没回包） | T5 带**耗时上界** |
| **F5** | 两臂共用 run dir / volume / provider | open 臂读到 strict 臂残留的 `result.json`；今天的 `task_dir()` 正是这样（§1.3） | run_id 分层 + T2 + PA-3 |
| **F6** | 为让 RD-Agent(Q) 跑通偷偷装依赖 | 运行期装依赖是 L-8 红，且让镜像 digest **失去意义** —— 两臂各自装各自的，环境等价当场破 | L-8 + P4 + IN-3 |
| **F7** | pin 只读 provider 自带 manifest 里记的 digest | 任何篡改只要顺手改一下 manifest 就通过。**这种检查等于没有** | `provider_root_sha256` **现算** + T4 第四子句 |
| **F8** | 协议工件少给一个，strict 臂静默退化 | 不报错、跑得完、分数照出，结论变成「协议没用」。这是**干预失败**，不是隔离失败，⊆ 式断言抓不到 | §6.2 **等号** + T2 |
| **F9** | 重跑静默覆盖遥测 | `run_id = f"{task_id}-{arm}"`（`:369`）+ `INSERT OR REPLACE`（`:281`）：第二次跑把第一次的行**替换**掉，历史消失，无告警 | run_id 含 config_id + seq + T14 |
| **F10** | 盘满导致复制截断 | provider / 输入 parquet 复制到一半，文件存在、大小不对；因子算得出来，**就是数不对** | P0 余量检查 + PA-2 复制后重核根 |
| **F11** | 身份自报，两臂日志互串 | 网关 `access_log` 的 `task_id`/`config_id` 取自请求头（`app.py:82-83`），头由容器自己填（`runner_core.py:317-319`）。两臂并发同 config 时，一臂可把请求记到另一臂名下：**两边日志都合法**，`declared_reads` / 越权探针照常出结论 | §6.5 边车源头注入（ID-1 先剥后注 + ID-3 切片键 = `run_id`）+ T15；卡 4.2 §6 三核作第二道 |

**这十一条的共同形状**：分数会**静默地**偏，日志干干净净，探针全绿。
每一条的防线都必须是「有东西会红」，不是「我们不会那样做」。

---

## 11. 已知边界（写进论文的局限，不假装解决）

1. **金丝雀只抓文件级原样搬运**（§6.4）。转格式会丢 metadata，零命中 ≠ 无泄漏。
2. **注入器保证的是「送进去的题面与 bundle 逐字节相同」**，不保证「两臂题面语义等价」——
   后者归卡 3.1 的 E1–E13 与签字人抽查，本卡不重复也不背书。
3. **环境等价的断言集是封闭列举**（文件集、sha、env、timeouts、image、provider 根）。
   列举之外的差异（宿主内核参数、CPU 调度抖动、镜像层缓存命中差异）**没有覆盖**。
4. **`check_manifest` 不能在 f02 现场判定泄漏性质**，只能判定「与 f01 那份是否逐字节相同」（§1.2 的换取）。
   这条依赖「f01 侧 `check_export` 确实跑过且为空」—— 由 `export_manifest` 的拒发规则保证，
   但**清单本身没有签名**，能改 manifests 目录的人能伪造通行证。
   **TK-5 裁定（2026-09-03）：签名归 v1.1/v2，v1 不做。** 因此这条是 v1 的**已知边界**，不是待办：
   **完整性链在 f01→f02 这一跳上靠的是目录权限（`manifests/` 的属主与模式），不是密码学。**
   威胁模型说清楚：它挡得住**搬运途中的损坏与无意改动**（sha256 逐文件比对，比 `check_export` 更强），
   挡不住**能写 `manifests/` 的人**。v1 里那个人就是我们自己 —— 这不是「假装解决了」，
   是「我们知道它没解决，并且知道边界画在哪」。论文的局限性一节按这句话写，**不许写成「清单保证了完整性」**。
   v2 的形态已定：f01 侧对清单做 detached 签名，f02 侧 `check_manifest` 先验签再比对；
   拦在 v1 之外的不是设计而是密钥管理（引入 = 改既有系统，无 sudo 假设下不做）。
5. **模型权重里的前视**（卡 4.1 §4）网络策略与本卡一概看不见，归卡 3.2 / 5.1 的记忆探针测量并报告。

---

## 12. TK-1..TK-5：签字裁定（2026-09-03）—— 五条**全部落定**，不再是待批

| # | 裁定 | 形态 | 落点 |
| --- | --- | --- | --- |
| **TK-1** | **选 (a)** —— 保留唯一 bind-mount 例外，L-5 收紧为「挂载源与 run dir 精确相等」 | 现在就做 | §8 IN-4 + **§8.1 三条判据** + **T16 / T17 / T18** |
| **TK-2** | **缓办** —— 主机防火墙规则不做，登记保留 | 挂起（不阻塞 4.3） | §12.2 |
| **TK-3** | **先实测再定配额** —— 配额数字不拍脑袋，先测单份 provider 在 f02 上的落地体积 | 待办（带命令） | §12.3 |
| **TK-4** | **批准**（条件式）—— T12 测不过才启用容器内同路径落盘 `/data/genebench/provider/` | 备用路径 | §7 判据段 + §12.4 |
| **TK-5** | **归 v2** —— 清单签名 v1 不做，写进已知边界 | 已知边界 | **§11 第 4 条** + §12.5 |

**下面的原表保留原文**（2026-09-02 登记时的措辞），它记录的是「为什么这五条必须由签字人裁」——
裁定落定之后这段理由仍然要能被复核，所以不删不改。

| # | 事项 | 为什么必须由签字人裁 | 不裁的后果 |
| --- | --- | --- | --- |
| **TK-1** | **bind-mount 冲突裁决**。硬约束写「不得有宿主 bind-mount」；卡 4.1 FS-1 写「唯一例外是 runner 为该次任务创建的工作目录」，且 `lint_compose` 的 L-5 就是照这个例外实现的；`packager.py:239` 的注释明写「bundle 的 work/ 整目录挂到 /task（卡 4.1 compose）」，题面里的 `/task/x.parquet` 路径也是照这个写的。**两条不能同时成立。** 备选：(a) 保留唯一例外，把 L-5 收紧成与 run dir 精确相等（IN-4）；(b) 全用 named volume + `docker cp` 装配，代价是 `down -v` 会连证据一起删、且要改题面里的路径措辞 —— 而题面已过 E1–E13 与人工签字 | 这决定 4.3 的落地形态，选 (b) 要回头动卡 3.1 已签字的题面 | 两条互斥的规则同时挂在墙上，实现者只能挑一条，挑哪条都能被判违规 |
| **TK-2** | f02 出向默认拒绝的**主机防火墙**规则（改既有主机策略） | 改既有系统 + 无 sudo | 拓扑保证（`internal: true`）已覆盖绝大部分，但主机侧仍是空的 |
| **TK-3** | `/data/genebench_runner/runs/` 的**磁盘配额**与回收策略。每臂各一份 provider 副本（PA-3），40 题 × 2 臂 × N 次重跑。**先实测单份 provider 体积再定数**，别拍脑袋 | 配额落在既有磁盘策略上 | 盘满 → F10（复制截断，静默错数） |
| **TK-4** | provider 绝对路径依赖。若 T12 测不过（`ops/test_qlib_provider.py` 与 `calibration.json` 都记了绝对路径，`tickets.md:1249-1254`），需批准「容器内同路径落盘 `/data/genebench/provider/`」 | 涉及容器内路径与 FS-1 的关系 | 因子静默算错，且症状指向数据而不是路径 |
| **TK-5** | 导出清单的**签名**（§11 第 4 条）。当前清单是明文 JSON，能写 `manifests/` 的人能伪造通行证 | 引入密钥管理 = 改既有系统 | 完整性链在 f01→f02 这一跳上是靠目录权限而不是靠密码学 |

### 12.1 TK-1 裁定：选 (a)，L-5 收紧为「精确相等」

**决定**：保留卡 4.1 FS-1 的**唯一例外** —— 「runner 为该次任务创建的工作目录」。
备选 (b)（全 named volume + `docker cp`）**不采纳**，两个理由各自独立成立：
① `down -v` 会连证据一起删 —— 而 run dir 是遥测行的磁盘对应物（§6.1）；
② 要回头改卡 3.1 **已过 E1–E13 与人工签字**的题面里的 `/task/x.parquet` 措辞，
而那份签字**不能撤**（卡 3.1 §7b 的教训：机械规则每轮都在追人眼，人工签字是最后一道）。
为一条实现细节去动已签字的题面，代价与风险都落在错误的一侧。

**代价说清楚**：硬约束「不得有宿主 bind-mount」从此**不是字面真**。它的准确表述是
「**除该次运行自己的 `work/` 目录外**，不得有宿主 bind-mount」。这句话必须同步写进卡 4.1 FS-1，
两处措辞一致 —— **两条互斥规则同时挂在墙上**正是 TK-1 要消灭的东西，裁完还留着就等于没裁。

**落地形态见 §8.1 的三条判据**（等号经 realpath / 落点双向 / 写法穷举），验收 **T16 / T17 / T18**。
三条缺一不可：判据 1 单独成立时**符号链接**绕得过；判据 2 单独成立时同一 runs 根下**别的 run dir** 绕得过；
判据 3 缺席时前两条**根本没被执行** —— 规则看不见的写法，规则再严也管不到。

### 12.2 TK-2 裁定：缓办（登记保留，不阻塞 4.3）

**决定**：f02 出向默认拒绝的**主机防火墙**规则**本轮不做**，条目**保留登记**。

**为什么可以缓**：出向默认拒绝由**网络拓扑**保证 —— 任务容器接 `internal: true` 的 `gb_task`，
**根本没有默认路由**，不是「被规则挡住」（卡 4.1 §3.2）。拓扑保证的强度反而**高于** iptables：
`internal: true` 没有可被 `iptables -F`、docker 重启或另一个管理员清空的持久状态，
白名单是进版本库的**代码**（`egress_proxy.MODEL_API_ALLOW`）。

**为什么仍然要留着登记**：**主机侧仍是空的。** 拓扑保证覆盖的是「**经 compose 起的任务容器**」这一条路径；
它不覆盖宿主机自身的出向，也不覆盖任何**不经本 runner 起的**进程 —— 人手敲的 `docker run`、
将来某个 systemd unit、联调时临时起的容器。这就是「覆盖绝大部分」与「覆盖全部」之间的那个差，
而这个差**在被触发前不产生任何可见信号**（N-30 的教训：验收一项「已封堵」必须查**配置态**，
不能只查运行态；「当前没有越权出向」这个观测既不能证明它封了，也不能证明它没封）。

**缓办的确切含义**：不是「不重要」，是「4.3 不等它」。执行条件与 T-12 同 —— 需 sudo，
签字人下次到场的人工窗口执行；**执行后必须立刻复跑卡 4.1 的 NET-A/B/C 三条**
（加主机规则很可能把 NET-A 的网关白名单一并挡掉，那是当场可见的红，不是静默的 —— 所以顺序是先加规则后验收，不能反）。

### 12.3 TK-3 裁定：先实测 provider 体积，再定配额（待办，命令在下面）

**决定**：`/data/genebench_runner/runs/` 的配额与回收策略**本轮不定数**。定数之前必须有 **f02 上的实测**。

**已有的实测（f01 侧，2026-09-03，本轮跑的）**：

```
$ ssh finance01-ts 'du -sb /data/shared/genebench/snapshots/v1/qlib_provider'
494008883       # 表观字节数 ≈ 471 MiB
$ ssh finance01-ts 'du -sh /data/shared/genebench/snapshots/v1/qlib_provider'
602M            # 落盘占用 —— 比表观大 28%
$ ssh finance01-ts 'find /data/shared/genebench/snapshots/v1/qlib_provider -type f | wc -l'
46544           # = 46,542（files.sha256 记录的）+ files.sha256 + manifest.json，对得上
```

**这三个数正好说明为什么不许拍脑袋**：46,544 个小文件让**落盘占用比字节总数大 28%**（块与 inode 开销）。
按表观字节数定阈值会系统性地少算，少算的后果是 **F10（复制截断，静默错数）**——
不是磁盘报错，是因子算得出来、**就是数不对**。

**f02 实测（2026-09-05 现跑，第 1 步完成）**：

```
路径 /data/genebench_runner/provider/qlib_provider_54fdda39
表观 472M（494,008,883 字节） 落盘 602M 文件 46,544   /data 余 2.6T
```

**与 f01 逐项相同** —— 28% 的块开销在两台机上都成立，不是 f01 文件系统的特例。
**第 2 步（完整 run dir）待一次真跑**，当前被 N-62 阻塞。可给的界：
每个 run dir ≥ 一份 provider 副本 ≈ 602M ⇒ 40 题 × 2 臂 = 80 个 run dir ⇒ **一轮 ≈ 48 GB**。
**配额数字仍不定**（裁定原文：不许拍脑袋），状态由 `ops/status_lock.py` 钉住。

**待办（f02 侧；必须在 f02 上跑，文件系统不同，f01 的数不能直接搬）**：

```bash
# 1) 单份 provider 在 f02 上的真实落地占用（先搬一份进缓存，再量；<pin> = sha256 根目录名）
ssh finance02-ts 'du -sh --apparent-size /data/genebench_runner/provider/<pin>/ ; \
                  du -sh                 /data/genebench_runner/provider/<pin>/ ; \
                  find /data/genebench_runner/provider/<pin>/ -type f | wc -l'

# 2) 一个完整 run dir 的占用（bundle + work + provider 副本 + log），两臂各量一次
ssh finance02-ts 'du -sh /data/genebench_runner/runs/<run_id>/ ; \
                  du -sh /data/genebench_runner/runs/<run_id>/work/provider/'

# 3) 当前余量（2026-09-03 实测：/data 2.7T 总 / 2.6T 可用 / 2% used）
ssh finance02-ts 'df -h /data'
```

**定配额时必须用第 2 步的数 × (40 题 × 2 臂 × N 次重跑)**，不是第 1 步的数 ——
PA-3 明写两臂**各复制一份**，provider 副本数等于 **run dir 数**，不等于题数。
回收策略同样等这个数：先知道一轮完整跑占多少，才谈得上「留几轮」。

**在实测拿到之前的占位**：P0 的磁盘余量阈值取「单份 provider 落地占用 × 3」，
且 **P0 红即抛，不许降级成 warning**。占位阈值偏保守是对的，偏乐观等于把 F10 请进来。

### 12.4 TK-4 裁定：批准，但**是条件式的**

**决定**：**批准**「容器内同路径落盘 `/data/genebench/provider/`」。**触发条件唯一：§7 的 T12 测不过。**

**触发条件写死**：容器内 `qlib.init(provider_uri="/task/provider")` 后跑那组固定查询，
结果与 f01 冻结 provider 上同一组查询的结果**逐字节不同**
（不是「行数对不上」、不是「shape 一样就算过」—— T12 的假绿形态就写在 §9 那一行里）。
**T12 过 ⇒ 不许启用本条**，provider 留在 `/task/provider/`。

**启用后的形态**：run dir 里 provider 副本的**容器内挂载点**改为 `/data/genebench/provider/`；
**宿主侧源不变**，仍是 `runs/<run_id>/work/provider/`。只改容器内 target，不改宿主布局。

**代价，三条，都要写进论文的局限性**：

1. **容器内出现了 `/data` 这个路径前缀**，而卡 4.1 的验收 FS-A 是「容器内 `ls /data` **必须失败**」。
   启用本条后 FS-A 与 T10 必须**同步改写**成「容器内 `/data` 下**只存在 `genebench/provider/` 一条路径**，
   且 `cat /proc/mounts` 里该挂载的宿主源在 `runs/<run_id>/work/` 之下」。
   **不许留一条永远绿不了的旧断言在那** —— 恒红的断言最后都会被人注释掉，然后那条防线就没了。
2. **§8.1 判据 1 的等号管的是「宿主侧源」，不是容器内 target**。这一点本来就成立，
   但启用本条后它变成**唯一**的防线：容器内路径不再自带「只可能落在 work 下」的语义。
   判据 1 因此从「一条防线」升级为「最后一条防线」，**T16 的五个负例一个都不能少**。
3. **绝对路径依赖被固化，而不是被消除**。`ops/test_qlib_provider.py` 与 `calibration.json`
   里那两处绝对路径（`ops/tickets.md:1249-1254`）从此成为**契约的一部分**：
   以后改 provider 落点会连带改容器内路径。要在 `ops/data_cards/qlib_provider.md` 里显式记一笔。

**顺序纪律**：**先跑 T12，结果留档，再决定启不启用。** 不许因为「反正批了」就直接走同路径 ——
那样就永远不知道路径无关性到底成不成立，而这正是 §7 那句「测出来的，不是推出来的」要防的事。

### 12.5 TK-5 裁定：归 v2，写进已知边界

**决定**：导出清单的**签名**归 **v1.1 / v2**，v1 **不做**。正文落在 **§11「已知边界」第 4 条**（已改写）。

**一句话边界**：**清单没有签名；f01→f02 这一跳的完整性靠 `manifests/` 的目录权限，不靠密码学。**
它挡得住搬运途中的损坏与无意改动（逐文件 sha256，判据比 `check_export` 更强），
挡不住**能写 `manifests/` 的人**。这条进论文的局限性一节，**不许写成「清单保证了完整性」**。

**为什么现在不做**：签名要引入密钥管理 = 改既有系统，落在无 sudo 假设之外；
而 v1 的威胁模型里，能写 `manifests/` 的人就是我们自己。
**做一个假的密码学保证比没有更坏** —— 它会让人停止查目录权限。

**v2 的形态已经定了**（免得将来重新讨论一遍）：f01 侧对清单做 detached 签名，
f02 侧 `check_manifest` **先验签、再比对**；拦在 v1 之外的不是设计而是密钥管理。

**与 TK-1 的分工要说清楚，别互相冒充（D-09）**：TK-1 的 `DATA_ROOTS` 把
`/data/genebench_runner/manifests/` 列了进去（§8.1），即**容器一侧**够不到通行证目录。
这**不能替代签名** —— 签名防的威胁在**宿主侧**，不在容器侧。它只是把「不可信方能改通行证」
这条路径关掉了。访问防线与完整性防线是两条线。

---

**另需与卡 4.1 协调（改既有代码，非改既有系统，不进 tickets 但要在卡 4.1 的验收里留翻转记录）**：
`runner_core.py` 的 `task_dir` / `COMPOSE_TMPL` 的 `name:` / `TASK_SUBNET` / `run_id` 四处按 §1.3 分裂；
`lint_compose` 加 `expect_workdir`（默认 `None`，卡 4.1 的 10 个负例保持原样绿）。

**状态锁**：`ops/capabilities.json` 的 `provider_sha256_pinned` 当前为 `false`。
按卡 3.1 的 S3b/S8b 惯例，**锁未翻绿时 `inject` 只许 dry-run**（装配 run dir、跑全部检查、不起容器、遥测记
`status=dry_run`），不许产出计分运行。翻锁必须先有对应测试翻转的记录。
同理 `inject` 只接受 `status ∈ {"exported","signed"}`（`schema.py:31` 的 `STATUSES`），
`exported` 只许 dry-run，`signed` 才许计分。
