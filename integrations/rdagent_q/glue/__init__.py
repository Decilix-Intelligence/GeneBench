# -*- coding: utf-8 -*-
"""RD-Agent(Q) 的接线层。**不改被测系统内核** —— 全部是子类 / 配置 / 数据落盘。

每一处替换都在 `bootstrap.REPLACEMENTS`（配置入口）与 `scenario` 的模块 docstring
（唯一一处方法覆写）里写清了「顶替的是上游哪个对象的哪个属性、为什么」。
`ops/test_integration_rdagent_q.py` 拿这份清单去 import 上游做属性存在性检查。
"""
from . import bootstrap, develop, instruction, panel, scenario  # noqa: F401

__all__ = ["bootstrap", "develop", "instruction", "panel", "scenario"]
