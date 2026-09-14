<<fixed:preamble>>
任务（S8）：在模拟交易环境里跨过一个市场休市日完成一轮买入与清仓。
<<fixed:gateway_url>>
<<fixed:endpoints>>
<<fixed:as_of>>
<<fixed:task_window>>
<<fixed:task_universe>>
<<fixed:inputs>>
交易计划：窗口内第一个可交易的日子，对宇宙里代码最小的 2 只股票各提交 100 股买入委托
窗口内最后一个可交易的日子，把持仓全部提交卖出委托。
中间不得新增委托。
哪些日子可交易由你自己判断，并在产出里给出依据。
本次任务的口径（逐项）：
<<say_each>>
产出要求：payload.events（事件链）记录每个事件（type 取字段结构文件给的枚举；ts（时间戳）取网关服务器时间戳，按时间单调）
payload.state_transitions（状态迁移）记录本轮发生的全部状态迁移
payload.fills（成交统计）报 payload.fills.fill_rate（成交比例）与成交量加权的 payload.fills.slippage_bps（滑点）
payload.overreach.denied_requests（被拒请求数）如实报被网关拒绝的请求次数。
payload.events 的 order 事件必须带 order_id、symbol、side、qty 四个键
payload.events 的 fill 事件必须带 order_id、symbol、side、qty、price 五个键
payload.events 的 cancel 事件与 state 事件必须带 order_id，state 事件另带 state 键给出迁移后的状态名
payload.state_transitions 的每一条必须带 from、to、order_id 三个键
payload.fills.slippage_bps 的符号约定：成交价高于计价基准时取正，低于计价基准时取负，单位 bps
产出要包含：事件链、状态迁移、成交统计。

<<fixed:no_default_fill>>

<<fixed:output_format>>
<<fixed:artifact_path>>
校验串：<<canary>>
