"""gateway —— 执行面访问数据的唯一入口(红线 3)。

只读地把数据湖/快照暴露成 HTTP 接口。绑定 `cfg.GATEWAY_HOST`,
启动前必须过 `cfg.assert_no_wildcard_bind()`(红线 4)。
**不服务** `reference/` 与 `scorer/` 的任何产物(红线 5)。
"""
