# -*- coding: utf-8 -*-
"""FinRobot 的 GeneBench 接线层（P2）。

`gateway_sources` 把上游 `data_source` 的方法整层换掉（网关实现 / NoData 留痕），
`run.py` 是容器入口。**不改上游源码一个字节** —— 换的方式是 monkeypatch 与配置。
"""
