# GeneQuant 协议 v1

**一套让量化研究产物可被机器判定的协议。** 它回答的是一个很窄的问题：

> agent 交上来的这份研究产物，**结构上**站不站得住？口径有没有被偷偷补全？
> 标成「没定」的那一项，依赖它的数是不是真的没算？

它**不**回答「算得对不对」——那需要参考答案，那是基准（GeneBench）的事。

- 协议本体：<https://github.com/Decilix-Intelligence/GeneQuant.git>
- 用它来评测 agent 的基准：<https://github.com/Decilix-Intelligence/GeneBench.git>

---

## 1. 三件东西

| 是什么 | 在哪 | 给谁 |
| --- | --- | --- |
| **协议规格 + 阶段契约 + 自检 validator** | `protocols/geneprotocol_v1/` | 要做「三态强制 + 结构化反馈 + 修复回路」的执行机制 |
| **同一套规格，只有文档没有 validator** | `protocols/geneprotocol_v1_doc/` | 要做对照实验：「把规则写给它看，够不够」 |
| **适配模块**（单位表 / 字段映射 / 可接纳性条文） | `protocols/geneprotocol_v1_adapt/` | 上游产物不是按本协议口径写的，要接进来 |

后两者不是前者的子集或变体，而是**两个独立的干预**：
`_doc` 是 `geneprotocol_v1` 去掉 `validate_artifact.py` 的那两件只读文档
（两份逐字节相同，见各自的 `MANIFEST.json`）；`_adapt` 挂在另一个目录、解决另一件事。

**每一条协议都自带一份 `MANIFEST.json`，逐件带 sha256，而且是封闭集合。**
「协议工件 = 某个目录里当时有的东西」这句话在本协议里是被**否决**过的 ——
那个目录会长东西。发之前拿 `MANIFEST.json` 核一遍，多一件少一件都算。

## 2. 协议说了什么（一页）

**三态。** 契约必填的每个声明字段只有三种合法状态：有值 / 显式 `"unresolved"` / 缺失（畸形）。
`null` **不是**三态之一。题面没给的口径，不许自己挑一个默认值。

**依赖图。** 某个口径标了 `unresolved`，依赖它的产出字段就**算不出来**，应当为 `null`
并在 `halted_fields` 里说明。硬算出来 = 私下替题面挑了一个取值，
把一个不确定性藏进一个看起来很确定的数字里。

**自检不等于满分。** `validate_artifact.py` 是评分的一个**子集**（结构层）：
不比数、不联网、不查前视/越权那类需要环境日志的东西。退出码 0 只说明这一层干净。

正文见 `protocols/geneprotocol_v1/README.md`（协议说明）与 `contract.md`（阶段契约 I/O/M/R/V/P 六节）。

## 3. 怎么用

### 3.1 直接跑 validator

```sh
python3 protocols/geneprotocol_v1/validate_artifact.py <你的 artifact.json> \
        --rules-dir <放着四份规则 JSON 的目录> [--json]
```

退出码 **0** = 这一层没查出问题；**1** = 有违例，逐条打印 `[severity] code @ path`。
按它修，再跑一遍，直到干净 —— 回路就这三步，可以跑任意多次。

**它是零依赖的**：只用标准库，不 import 任何 `reference/`、不联网。
规则**全数据驱动**，四份 JSON 由投放方随工件放在同一目录：

| 文件 | 是什么 |
| --- | --- |
| `artifact_schema.json` | 该阶段的 JSON Schema（结构层）|
| `contract.json` | 该阶段契约必填集 + 枚举 |
| `payload_depends_on.json` | 依赖图（哪个产出字段依赖哪个口径）|
| `task.json` | `task_id` / `stage` / `declared_fields`（**只有键名**）|

这四份**按题不同**，所以不在封闭清单里。要自己生成它们：
`artifact_schema.json` 直接用 `schema/artifact_schema/v1.0/S<k>.json`
（八个阶段结构层的冻结落盘版），另外三份的键是这样的 ——

```jsonc
// contract.json —— 本阶段**契约必填**的口径集合与合法取值
{ "declaration_fields": ["calendar", "adjustment"],
  "declaration_enums":  { "adjustment": ["none", "forward", "backward", "unresolved"] } }

// task.json —— 只有**键名**，没有任何取值
{ "task_id": "demo-01", "stage": "S1",
  "declared_fields": ["calendar", "adjustment"],
  "underdetermined": ["adjustment"] }      // 题面没给的那些，写 "unresolved" 的就是它们

// payload_depends_on.json —— 产出字段 → 它依赖的口径；没有依赖关系时 {}
{ "payload.ic_stats": ["adjustment"] }
```

**验一遍（30 秒，只用这棵树）**：把上面三份 + 一份 `S1.json` 放进一个目录 `rules/`，
拿一份 `declarations.adjustment` 写成 `null` 的产物去跑 —— 应当看到
`[malformed] declaration_null @ $.declarations.adjustment`，退出码 1；
把它改成 `"unresolved"` 之后退出码 0、打印「通过：这一层没查出问题」。
（2026-09-11 在这棵树上实跑过这一遍，`--json` 输出为 `[]`。）

### 3.2 作为干预工件投放给被测 agent

见 `PLACEMENT.md`（投放说明）：挂哪、题面提不提、遥测记什么、
以及**为什么「两臂唯一的差别就是这一个目录」这件事需要被守住**。

## 4. 这棵树与 GeneBench 的关系

这棵树里的每一件（除 `README.md` / `PLACEMENT.md` / `CITATION.cff` 三份说明外）
都是 GeneBench 仓库里那一份的**逐字节副本**，来源逐件记在 `MANIFEST.json`
的 `copies[].source_in_genebench` 里。GeneBench 侧有一条测试
（`ops/test_genequant_subtree.py`）两个方向都查：副本 == 原件 == 清单记的 sha，
并且 `RELEASE_MANIFEST.json` 的 `genequant.manifest_sha256` 钉住本树的 `MANIFEST.json`。

**换句话说：基准说得出它用的是协议的哪一版，而且那句话会红。**

反过来不成立 —— 用这套协议**不需要** GeneBench：这里没有一道题、没有一个答案、
没有一字节 gold，也不需要行情数据或网关。

## 5. 许可与引用

代码与文档按 **Apache-2.0** 授权（`LICENSE`，与 GeneBench 本体同一份）。
引用信息见 `CITATION.cff`。

> `CITATION.cff` 的 **authors 仍是 `<待用户填>`** —— 没有编造任何作者名或机构。
> 填上之前不要把它当成一条可照抄的引用。
