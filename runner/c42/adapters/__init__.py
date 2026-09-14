"""卡 4.2 的框架适配层。

**一条总纪律（§1）：适配层永不代 agent 做决定。**
适配器只做四件事里的两件 —— **转录**与**切片**；重算与标注不可检归 `origin` / `visibility`。

结构上怎么保证：适配器**不能直接构造 artifact 字段**。它交出的是
`(值, 来源)` 二元组，经 `origin.transcribe_declarations` / `origin.transcribe_payload`
出口 —— 非 `agent_artifact` 的声明、非 agent 字节的 payload 值都在那里被拒。
「不得填 declarations」因此不是一条注释，是一条走不通的路。
"""
