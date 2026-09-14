# -*- coding: utf-8 -*-
"""TradingAgents ↔ GeneBench 的接线层（不改上游内核）。

两个模块：
* `gateway_vendors` —— 把上游 `tradingagents.dataflows.interface.VENDOR_METHODS`
  整表换成经 GeneBench 网关的实现（monkeypatch，不动上游源码）。
* `run` —— 容器入口：读题面 → 装接线 → 跑图 → `emit` 交产物。

镜像里它被 COPY 到 `/opt/tradingagents_glue/`，`run.py` 把 `/opt` 加进 `sys.path`
之后按包名 import。
"""
