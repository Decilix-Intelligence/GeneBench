# -*- coding: utf-8 -*-
"""FinMem 接入的接线层。

**这里没有一行改到 FinMem 的内核。** 三处替换都是模块属性顶替（monkeypatch）
或子类，替换点与被替换的对象逐个写在各模块的 docstring 里：

| 模块 | 替换的是 | 上游的哪个东西 |
| --- | --- | --- |
| `chat_seam.py` | `puppy.agent.ChatOpenAICompatible` | `puppy/chat.py::ChatOpenAICompatible.parse_response` 只认 gpt/gemini-pro/tgi |
| `embedding_seam.py` | `puppy.memorydb.OpenAILongerThanContextEmb` | `puppy/memorydb.py:56` 在 `MemoryDB.__init__` 里写死的那一行 |
| `env_data.py` | FinMem 的 `data-pipeline/`（离线阶段） | `run.py` 读的那个 `env_data.pkl` |

`ops/test_integration_finmem.py` 对前两处做**存在性检查**：属性必须真的在被替换的
模块里（装不起来就 skip 并说明）。替换一个不存在的名字不会报错，只会静默无效 ——
那正是最看不见的失效。
"""
