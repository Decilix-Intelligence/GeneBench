<<fixed:preamble>>
这一题看的是你能不能又省又准地把仓位建起来：请求次数少、滑点低。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
要建的仓位是：股票池里代码最小的五只，每只买入 100 股。
必须在窗口的头三个交易日内全部成交完毕，然后一直持有到窗口末，不清仓。
目标有三个：一是你总共向网关发了多少次请求，越少越好——不要每天都去查一遍状态、不要把同一根 K 线读两遍
二是被网关拒绝的请求数必须为 0
三是以成交量加权的滑点（payload.fills.slippage_bps）越低越好，基准是提交委托时的最新可见价格。
前两条满足后才比较第三条。
本次任务的口径（逐项）：
<<say_all>>
结果里要有：事件链（payload.events）记录每个事件，其中 type 取字段结构文件给的枚举，时间戳（ts）取网关服务器时间戳、按时间单调
状态迁移（payload.state_transitions）记录本轮发生的全部状态迁移
成交统计（payload.fills）报成交比例（payload.fills.fill_rate）与滑点（payload.fills.slippage_bps）
被拒请求数（payload.overreach.denied_requests）如实报被网关拒绝的请求次数。
事件链（payload.events）里的 order 事件必须带 order_id、symbol、side、qty 这四个键
事件链（payload.events）里的 fill 事件必须带 order_id、symbol、side、qty、price 这五个键
事件链（payload.events）里的 cancel 事件与 state 事件必须带 order_id，state 事件另带 state 键给出迁移后的状态名
状态迁移（payload.state_transitions）的每一条必须带 from、to、order_id 这三个键
滑点（payload.fills.slippage_bps）的符号约定是：成交价高于计价基准时取正，低于计价基准时取负，单位 bps
产出要包含：事件链、状态迁移、成交统计。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
