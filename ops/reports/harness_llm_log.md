# harness × llm_log 完整度（卡 3.3）

生成于 2026-09-07 07:52Z，由 `ops/reports/harness_llm_log.md` 的生成脚本
（`$GB/scratch/3.3/{survey33,table33,mkreport}.py`）现算，**表里没有一个数是手抄的**。

这张表回答一件事：**主表 Table A 的 `Steps / tokens / $` 三列，五个 harness 上都有数吗；**
**没数的那些，是链路的问题还是抽取器的问题。**

## 一、五行汇总

| harness | batch | wire 形状 | allow 调用 / 其中有 usage | 缺 usage 的原因 | Steps | tokens | `$` (USD) |
|---|---|---|---|---|---|---|---|
| **codex** | `m6_all` | `responses`×1196、`unknown`×18 | 1176/1214 | `no_usage_in_body`×22、`upstream_error`×16 | 29/29（合计 1214） | 29/29：57,029,348 + 1,449,016 | 29/29：27.0056 |
| **claude-code** | `h_claude-code` | `anthropic_messages`×97 | 96/97 | `no_usage_in_body`×1 | 2/2（合计 97） | 2/2：117,955 + 129,100 | 2/2：0.2223 |
| **gemini-cli** | `h_gemini-cli` | `unknown`×4 | 0/4 | `upstream_error`×4 | 2/2（合计 2） | 0/2：— | 0/2：— |
| **grok-cli** | `h_grok-cli` | `chat_completions`×104 | 104/104 | — | 2/2（合计 104） | 2/2：1,644,194 + 7,089 | 2/2：0.7328 |
| **opencode** | `h_opencode` | `chat_completions`×86 | 86/86 | — | 2/2（合计 86） | 2/2：2,647,912 + 43,359 | 2/2：1.2223 |

列的读法：`a/b` 是「b 个 run 里有 a 个这一列有数」。tokens 写成 `prompt + completion`（全 batch 合计）。

## 二、三个「—」各是什么意思（本卡的要点）

表上有三处空格，**它们的原因两两不同**，而在改这张卡之前它们长得一模一样：

1. **gemini-cli 的 tokens 与 `$` 都是 —。** 四条 allow 记录 status 全 404：
   Gemini CLI 说的是 Gemini 协议（`/v1beta/models/…:streamGenerateContent`），
   而 `api.deepseek.com` 不服务这个协议。**上游拒绝、根本没有 usage** ——
   `llm_trace.usage_absent_reason` 给的是 `upstream_error`。
   这个空格**必须是空的**：写 0 会被读成「这次几乎没花 token」，而真相是「我们一个 token 都没买到」。
2. **codex 有 38 条 allow 没有 usage**（22 `no_usage_in_body` + 16 `upstream_error`）。
   16 条 404 是 agent 自己乱试的探路请求（`/bars`、`/calendar`、`/healthz` 这些，不是模型端点）；
   22 条是 `/v1/responses` 与 `/v1/models` 上游 200 但体里确实没有 usage。两者都不是抽取器的锅。
3. **`$` 一度整列消失过 —— 那才是真问题，本卡修掉了。** 见第四节。

## 三、三种 wire 形状都覆盖到了，流式也是

| 形状 | 谁在走 | usage 键 | 缓存命中键 | 流式怎么给 |
|---|---|---|---|---|
| `chat_completions` | grok-cli、opencode | `prompt_tokens` / `completion_tokens` | `prompt_cache_hit_tokens`（DeepSeek）、`prompt_tokens_details.cached_tokens`（OpenAI） | 最后一个 chunk（`stream_options.include_usage`） |
| `responses` | codex | `input_tokens` / `output_tokens` | `input_tokens_details.cached_tokens` | `response.completed` 事件上 |
| `anthropic_messages` | claude-code（经 DeepSeek 的 `/anthropic`） | `input_tokens` / `output_tokens` | `cache_read_input_tokens` | **跨两个事件**：`message_start` 给 input、`message_delta` 给 output |

归一后统一是 `prompt_tokens / completion_tokens / cached_prompt_tokens / total_tokens` 再加一个 `wire_shape`。
**原始键一律保留** —— `runner/pricing.py::CACHE_HIT_KEYS` 认的是各家的原始名，只留归一键会让 `$` 列变。

Anthropic 那一行的「跨两个事件」是这次唯一一处**不能照搬**的：
旧实现对 SSE 是「从后往前找第一个带 usage 的事件」，用在 Anthropic 上会取到 `message_delta`，
于是 `prompt_tokens` 丢失、`total_tokens` 只剩半个。新实现改成**从前往后逐事件合并、非零值赢**
（`egress_proxy._merge_raw`）。`ops/test_llm_usage_shapes.py::test_anthropic_stream_must_merge_two_events_not_take_the_last_one` 钉着这一条。

## 四、重结算的结果：**逐字节等于已提交的那份**（这是本节的结论）

四个 batch 用 `ops/score_runs.py --batch h_<id> --no-pull` 重跑一遍，
`git diff --stat ops/reports/` **空**。也就是说新的抽取器在既有证据上**一个数都没改**。

但第一次重结算不是这样 —— 它悄悄**弄丢了 grok-cli 的整列 `$`**，还把 gemini-cli 的 `cost_model` 抹成 null：

```
-cfg-grok-cli-deepseek,open,...,4.0,0.0174086,24.467,...
+cfg-grok-cli-deepseek,open,...,4.0,,24.467,...
```

真因与本卡的抽取器无关，是一条**报告不可复现**的老账：
`scorer/score_run.py::model_of` 只走 `REG.by_id`，而 `by_id` 对 `enabled: false` 抛 `RegistryError`。
3.2 的两位代理真跑时按手册把 config.yaml 临时翻成 `enabled: true`、跑完翻回 false ——
于是**当时**算得出价、**今天**再算就算不出。任何人重跑一次结算都会把那一列洗掉，且不报错。

修法（`model_of` 回落到 `REG.PENDING_CONFIGS`）在本卡提交里，理由是这两个 None 同形异义：

| config | `cost_model` | `cost_usd` | 该读成 |
|---|---|---|---|
| gemini-cli | `deepseek-chat` | `None` | **有价、无用量** —— 上游 404，一个 token 都没买到 |
| grok-cli | `deepseek-chat` | `0.733…` | 真花了这么多钱（104 条 usage 条条有数） |
| oracle / null\_agent | `None` | `None` | 根本没调模型 |

`PENDING_CONFIGS` 不进主表切片（切片键集是 `CONFIGS`），所以这一改只影响各 harness 自己那张
「接入验证，不是实验数据」的表，动不到 m6 / a1 的历史数。

## 五、边车侧新增的三个字段（2026-09-07 起的记录才有）

| 字段 | 什么时候写 | 用来回答 |
|---|---|---|
| `usage.wire_shape` | 每条有 usage 的 allow | 这条走的哪种协议（先看 path，认不出再看键名） |
| `response_bytes` / `response_truncated` | 每条 allow | 「usage 抽不到」是上游没给，还是**我们的副本被截了** |
| `usage_absent` | 只在没抽到 usage 时 | `upstream_error` / `empty_body` / `truncated_no_usage` / `no_usage_in_body` |

`response_truncated` 这条是有代价才加的：旧实现整段缓存响应体，超过上限就丢尾巴，
而**流式的 usage 恰恰在最后一个事件里** —— 一次长流式响应抽出来是 `{}`，与「上游没给」不可分。
新实现同时留**头**和**尾**两份有界副本（`_capture_head_tail`），并**边收边**去 chunked 框架
（`_ChunkedDecoder`，任意切分边界都对）。转发始终先于留副本：留不下来不该拖累被测方。

## 六、历史记录里补不回来的一件事

codex 的 1176 条 usage **没有 `cached_prompt_tokens`**：
Responses API 把它嵌在 `usage.input_tokens_details.cached_tokens` 里，
而旧的 `_norm_usage` 只搬平铺的数值键，嵌套那一份在**落盘时**就丢了。
读取侧补不回没写下来的东西 —— 这一列对 m6/m6b 只能是空的，新跑的才有。
（`llm_trace.normalize_usage` 是读取侧的历史兼容层：能补的都补了，补不了的就是补不了。）

## 七、复现

```sh
cd /data/shared/genebench/repo
PY=/data/shared/genebench/env/bin/python
$PY /data/shared/genebench/scratch/3.3/survey33.py > /data/shared/genebench/scratch/3.3/survey33.json
$PY /data/shared/genebench/scratch/3.3/table33.py  > /data/shared/genebench/scratch/3.3/table33.json
$PY /data/shared/genebench/scratch/3.3/mkreport.py
bash /data/shared/genebench/scratch/3.3/rescore33.sh   # 四个 batch 重结算；git diff 应为空
```

N-100（边车宿主/容器两侧各真跑一次）的容器侧那次：
`/data/genebench_runner/n100/runs/runs/s2-cor-01.strict.cfg-opencode-deepseek.r01`，
30 条 allow 条条有 usage 且带 `wire_shape` 与 `cached_prompt_tokens`，6 条 `429 budget_exceeded`（`--max-calls 30`）。
宿主侧是 `ops/test_c41.py`。
