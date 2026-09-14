<<fixed:preamble>>
请在模拟盘里做一轮“买入、持有、清仓”，这一轮跨过一个市场休市日。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
安排是：窗口里第一个能交易的日子，挑股票池里代码最小的两只，每只提交 100 股买入委托
窗口里最后一个能交易的日子，把持仓全部提交卖出委托
中间不得新增委托。
哪些日子能交易由你自己判断，并在结果里说明你的依据。
本次任务的口径（逐项）：
<<say_all>>
结果里要有：事件链（payload.events）记录每个事件，其中 type 取字段结构文件给的枚举，时间戳（ts）取网关服务器时间戳、按时间单调
状态迁移（payload.state_transitions）记录本轮发生的全部状态迁移
成交统计（payload.fills）报成交比例（payload.fills.fill_rate）与以成交量加权的滑点（payload.fills.slippage_bps）
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
