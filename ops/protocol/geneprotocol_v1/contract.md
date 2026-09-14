# 阶段契约（人读版）

机器可读版在 `contract.json`，validator 读的是那一份。两份说的是同一件事。

## I —— 输入

题面的「输入材料」一节列出你能读的文件，都在 `/task/` 下。
除此之外的数据**只能经网关取**（题面给了地址与端点清单）。
网关按 `as_of` 截断：请求晚于 `as_of` 的数据会被拒。

## O —— 输出

一个 JSON 文件，写到题面「产出路径」指定的位置（通常是 `/task/artifact.json`）。
顶层必含字段、`payload` 必含字段、各子字段的键名，都在 `artifact_schema.json` 里；
题面的「产出格式」一节是同一份内容的自然语言版。

## M —— 语义

`contract.json` 的 `declaration_fields` 是本阶段**契约必填**的口径集合，
`declaration_enums` 给出各字段的合法取值。

**这不是「题面给了什么」**，而是「这个阶段的计算要定下哪些口径才是良定义的」。
题面可能没给其中某一项 —— 那时候用 `"unresolved"`，见下。

## R —— 不得推断的字段

题面**没有给出**的口径，不得自行补一个默认值。

具体到本题，`task.json` 的 `underdetermined` 列出了这些字段。
对它们：在 `declarations` 里写 `"unresolved"`，并且**不要**产出依赖它们的数
（`payload_depends_on.json` 给出依赖关系）。

为什么不许挑一个：不同的合理取值会给出不同的数。挑一个而不说，
等于把一个不确定性藏进了一个看起来很确定的数字里。

## V —— 自检

```
python3 /task/protocol/validate_artifact.py /task/artifact.json
```

见 `README.md`。它查结构，不查对错。

## P —— 出处

`provenance` 记录你这份产出依赖的上游产物（`{stage, artifact_id}`）。
题面若给了上游元数据文件（如 `signal.meta.json`），两个值从那里读，不要手写。
