# 这张表里的两个 0 该怎么读（batch `h_grok-cli`）

**不要把这两个 0 和 m6 的数放进同一列。** 表头已经写了「接入/harness 验证，不是实验数据」，
但它长得像主表，所以这里再说一次。

`SR=0.0` 的意思是：**Grok CLI 在 DeepSeek 上一次工具调用也做不成**，
不是「Grok CLI 做这道题做得差」。

104 条 `llm_log` 里，除最后那条预算闸的 429 外全部 `decision=allow / status=200 /
upstream=api.deepseek.com` —— 链路、key 注入、预算闸、日志、出向白名单都是好的。
断点在客户端：`@ai-sdk/xai` 的流式 chunk schema 只认 xAI「一片 = 一次完整工具调用」的形状，
DeepSeek（以及 OpenAI 本身）的续片只带 `index` + 参数片段，被整片丢弃，
于是每一次工具调用的参数都是 `{}`。

* 根因、源码引用、以及一组零真调用的假上游对照实验：`harnesses/grok-cli/README.md` §5。
* 因此 `harnesses/grok-cli/config.yaml` 是 `enabled: false`，这条配置**不在主表**。

两个 run 的 `unexpected` 里各有 297 条 `*.pile` —— 那是 bun 的运行时转译缓存，
真跑之后已在 `launch.json` 里用 `BUN_RUNTIME_TRANSPILER_CACHE_PATH=0` 关掉（README §4⑤），
不是任务产物，也不是越权。
