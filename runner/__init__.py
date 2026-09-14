"""runner —— 执行面:跑被测 agent / 提交。

只能通过网关拿数据(红线 3)。禁止 import `reference` 或 `scorer`,
禁止直接读数据湖、读 `cfg.SNAPSHOTS` 里的答案侧产物。
"""
