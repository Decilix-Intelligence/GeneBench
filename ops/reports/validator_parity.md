# 协议 validator × 评分器 L1 子集一致性（N-129，语料 = M6 全部真 artifact）

语料 **121** 份：真 agent 产物 23、oracle 32、null 33、filler 33。

> 比对只喂 artifact（`gateway_log=None`、`tradability=None`）—— 要证据的那几族本来就不在工件侧可见。

## 判定

- **validator 比 scorer 严**（不许）：0 份
- **作用域内反向缺口**（scorer 报、validator 沉默）：0 份
- **scorer 报了而 validator 完全沉默**（不限作用域）：0 份 —— 修复回路在这些产物上没启动

## 作用域外、但只看 artifact 就能判的 scorer code（扩作用域的候选）

| code | 出现份数 |
| --- | ---: |
