# GeneQuant 协议 v1

这个目录在容器里挂在 `/task/protocol/`。**题面不会提到它** —— 发现并使用它是你的事。

## 修复回路

产出 `artifact.json` 之后、交卷之前：

```
python3 /task/protocol/validate_artifact.py /task/artifact.json
```

* **退出码 0**：这一层没查出问题。
* **退出码 1**：有违例，逐条打印 `[severity] code @ path` 与说明。按它修，**再跑一遍**，直到干净。
* 要机器可读的输出加 `--json`，每条是 `{code, severity, path, msg}`。

回路就三步：**跑 validator → 按违例修 → 再跑**。它可以跑任意多次。

## 它检查什么，不检查什么

| 查 | 不查 |
| --- | --- |
| 信封字段齐不齐、类型对不对 | **对错**（不比数，没有参考答案） |
| 声明集对契约必填集的完整性；三态（有值 / `unresolved` / 缺失）| 前视、越权这类需要**网关日志**的检查 |
| 枚举取值 | 任何联网的东西 |
| 依赖图：口径标了 `unresolved`，依赖它的数就不该算出来 | |
| 内部一致性（如 coverage 三项计数与 signals 对得上）| |

**退出码 0 不等于满分。** 它是评分的一个**子集**——结构层。
算得对不对、有没有偷看未来的数据，都在这一层之外。

## 三态

契约必填的每个声明字段，只有三种合法状态：

1. **有值** —— 题面给了口径，照抄；
2. **显式 `"unresolved"`** —— 题面**没给**这一项，你也不该替它挑一个；
3. **缺失** —— 一律畸形。

`null` **不是**三态之一。不确定就写 `"unresolved"`，不要写 `null`、不要留空、不要猜一个默认值。

依赖图跟着三态走：某个口径标了 `unresolved`，依赖它的产出字段就**算不出来**，
应当为 `null` 并在 `halted_fields` 里说明。把数硬算出来 = 私下替题面挑了一个取值。

## 文件

| 文件 | 是什么 |
| --- | --- |
| `validate_artifact.py` | 自检 CLI（上面那条命令）|
| `contract.md` | 本阶段契约的人读版：I/O/M/R/V/P 六节 |
| `contract.json` | 同一份契约的机器可读版（validator 读它）|
| `artifact_schema.json` | 本阶段 artifact 的 JSON Schema |
| `payload_depends_on.json` | 依赖图：哪个产出字段依赖哪些声明 |
| `task.json` | 本题的上下文（stage、哪些口径题面没给）|

规则**全在数据里**。validator 不内置任何阶段知识——换一道题就是换这几个 JSON。
