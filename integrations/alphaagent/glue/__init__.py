# -*- coding: utf-8 -*-
"""AlphaAgent 的 GeneBench 接线层。

四个模块按 run.py 里的顺序读：
  bootstrap  —— 摆环境 + 把 `tushare` 顶替成经网关的垫片（必须在 import alphaagent 之前）
  instruction—— /task/INSTRUCTION.md → spec（两臂写法都认，取不到就抛）
  panel      —— 网关的 bars → AlphaAgent DSL 面板
  agent      —— 用系统自己的 run_trajectory 跑一遍，工具与 prompt 是同形替换

**不改系统内核**：这四个模块一行 alphaagent 的代码都没有改写，替换点逐处写在
各自的模块 docstring 里（bootstrap 一处 sys.modules，agent 两处同形替换）。
"""
