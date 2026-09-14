# -*- coding: utf-8 -*-
"""卡 3.3：**llm_log 的 usage 在三种 wire 形状上都抽得出来**（含流式）。

守的是一件具体的事：主表的 `Steps / tokens / $` 三列有没有数，
取决于边车能不能从上游的响应里抽到 `usage`。而上游的形状有三种：

* **Chat Completions**（DeepSeek / OpenAI 兼容）：`usage.prompt_tokens / completion_tokens`；
* **Responses API**（Codex CLI 走这条）：`usage.input_tokens / output_tokens`
  （+ `input_tokens_details.cached_tokens`），SSE 里挂在 `response.completed` 上；
* **Anthropic Messages**（Claude Code 经 DeepSeek 的 `/anthropic` 走这条）：
  `usage.input_tokens / output_tokens`（+ `cache_read_input_tokens`），
  流式时**跨两个事件**：`message_start` 给 input、`message_delta` 给 output。

三条判据合起来说一句话：**抽不到就是 `None`，不是 0。**
0 会被主表读成「这次几乎没花 token」，而真相是「我们没测到」——
这与 `llm_trace.load` 的三态、`pricing.cost_usd` 的缺价纪律是同一条。
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from runner.c42 import llm_trace as LT              # noqa: E402


def _load_ep():
    """边车是**单文件**挂进容器的（`/opt/egress_proxy.py`），按路径 import 与它同构。"""
    p = _REPO / "runner" / "c41" / "egress_proxy.py"
    spec = importlib.util.spec_from_file_location("gb_egress_proxy_3_3", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ep = _load_ep()

# --------------------------------------------------------------------- 夹具

#: ① Chat Completions，非流式。DeepSeek 把缓存命中平铺成 `prompt_cache_hit_tokens`。
CHAT_JSON = json.dumps({
    "id": "x", "object": "chat.completion", "model": "deepseek-chat",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
    "usage": {"prompt_tokens": 1200, "completion_tokens": 300, "total_tokens": 1500,
              "prompt_cache_hit_tokens": 1024, "prompt_cache_miss_tokens": 176},
}).encode()

#: ① 流式版：usage 只在最后一个 chunk 上（`stream_options.include_usage`）。
CHAT_SSE = (
    b'data: {"choices":[{"delta":{"content":"o"}}],"usage":null}\n\n'
    b'data: {"choices":[{"delta":{"content":"k"}}],"usage":null}\n\n'
    b'data: {"choices":[],"usage":{"prompt_tokens":1200,"completion_tokens":300,'
    b'"total_tokens":1500,"prompt_cache_hit_tokens":1024}}\n\n'
    b'data: [DONE]\n\n'
)

#: ② Responses API，SSE。usage 嵌在 `response.usage`，只在 `response.completed` 上。
#:    `response.created` 先到，且它的 `usage` 是 `null` —— 抽取器不能被它带偏。
RESP_SSE = (
    b'event: response.created\n'
    b'data: {"type":"response.created","response":{"id":"r1","status":"in_progress",'
    b'"usage":null}}\n\n'
    b'event: response.output_text.delta\n'
    b'data: {"type":"response.output_text.delta","delta":"ok"}\n\n'
    b'event: response.completed\n'
    b'data: {"type":"response.completed","response":{"id":"r1","status":"completed",'
    b'"usage":{"input_tokens":1200,"output_tokens":300,"total_tokens":1500,'
    b'"input_tokens_details":{"cached_tokens":1024}}}}\n\n'
)

#: ③ Anthropic Messages，SSE。**input 与 output 在两个不同的事件上** ——
#:    取「最后一个带 usage 的事件」会把 prompt 抹成 0。
ANTHROPIC_SSE = (
    b'event: message_start\n'
    b'data: {"type":"message_start","message":{"id":"m1","model":"deepseek-chat",'
    b'"usage":{"input_tokens":1200,"output_tokens":1,"cache_read_input_tokens":1024,'
    b'"cache_creation_input_tokens":0}}}\n\n'
    b'event: content_block_delta\n'
    b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"ok"}}\n\n'
    b'event: message_delta\n'
    b'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},'
    b'"usage":{"input_tokens":0,"output_tokens":300}}\n\n'
)

#: ③ 非流式版（Anthropic 不回 `total_tokens` —— 归一时必须自己补）。
ANTHROPIC_JSON = json.dumps({
    "id": "m1", "type": "message", "role": "assistant",
    "content": [{"type": "text", "text": "ok"}],
    "usage": {"input_tokens": 1200, "output_tokens": 300,
              "cache_read_input_tokens": 1024, "cache_creation_input_tokens": 0},
}).encode()

CASES = (
    ("chat_completions", CHAT_JSON, "/v1/chat/completions"),
    ("chat_completions", CHAT_SSE, "/v1/chat/completions"),
    ("responses", RESP_SSE, "/v1/responses"),
    ("anthropic_messages", ANTHROPIC_SSE, "/anthropic/v1/messages?beta=true"),
    ("anthropic_messages", ANTHROPIC_JSON, "/anthropic/v1/messages?beta=true"),
)

#: 五条夹具**必须抽出同一组数** —— 它们是同一次调用在五种线上的写法。
EXPECT = {"prompt_tokens": 1200, "completion_tokens": 300,
          "cached_prompt_tokens": 1024, "total_tokens": 1500}


# --------------------------------------------------------------------- 判据

@pytest.mark.parametrize("shape,body,path", CASES)
def test_three_wire_shapes_and_streaming_agree(shape, body, path):
    """三种形状 + 流式，抽出来的四个数逐个相等，`wire_shape` 也对得上。"""
    got = ep._extract_usage(body, path)
    assert got, f"{shape} / {path} 一个 usage 都没抽到"
    for k, v in EXPECT.items():
        assert got.get(k) == v, f"{shape}: {k} 抽成 {got.get(k)}，应是 {v}\n{got}"
    assert got["wire_shape"] == shape, f"{path} 判成了 {got['wire_shape']}"


def test_anthropic_stream_must_merge_two_events_not_take_the_last_one():
    """反向判据：`message_delta` 里 `input_tokens` 是 0 —— 取最后一个就会把 prompt 抹成 0。

    这条不是重复上面那条：上面测的是**结果对**，这条钉的是**为什么用合并而不是取最后一个**。
    把合并换成「后来者一律赢」，这条会红而上面那条也会红；
    把合并换成「取最后一个带 usage 的事件」，只有这条能说清坏在哪。
    """
    last_only = json.loads(ANTHROPIC_SSE.decode().rsplit("data: ", 1)[1])
    assert last_only["usage"]["input_tokens"] == 0, "夹具本身要保留这个 0，否则判据是空的"
    got = ep._extract_usage(ANTHROPIC_SSE, "/anthropic/v1/messages?beta=true")
    assert got["prompt_tokens"] == 1200
    assert got["completion_tokens"] == 300, "output 必须取 message_delta 的终值，不是 message_start 的占位 1"


def test_missing_usage_is_none_not_zero():
    """**缺 usage → None，不是 0。** 三处都要成立：边车、单条记录、整条轨迹。"""
    assert ep._extract_usage(b"", "/v1/chat/completions") == {}
    assert ep._extract_usage(b"not json at all") == {}
    assert LT.usage_of({"decision": "allow", "usage": {}}) is None
    assert LT.usage_of({"decision": "allow"}) is None
    assert LT.usage_totals([{"decision": "allow", "path": "/v1/chat/completions"}]) is None
    assert LT.usage_totals(None) is None


def test_gemini_cli_404_reads_as_upstream_refused_not_zero_tokens():
    """gemini-cli 的两个 run 是 **404 零 usage**（协议不合，上游拒了）。

    它必须读成「上游拒绝、无 usage」，不能读成「这次用了 0 个 token」——
    后者会在主表上把一次**没跑成**的运行画成一次**很省**的运行。
    """
    rec = {"decision": "allow", "status": 404, "response_body": "",
           "path": "/v1beta/models/deepseek-chat:streamGenerateContent?alt=sse"}
    assert LT.usage_of(rec) is None
    assert LT.usage_absent_reason(rec) == "upstream_error"
    cov = LT.usage_coverage([rec])
    assert cov == {"calls": 1, "with_usage": 0, "missing": 1,
                   "missing_reasons": {"upstream_error": 1},
                   "wire_shapes": {"unknown": 1}}


def test_the_two_alias_tables_are_the_same_table():
    """边车与 `llm_trace` 各有一份归一表（边车要单文件挂进容器，不能 import）。

    两份**必须逐字相等** —— 与 `MODEL_API_ALLOW` / `collect_egress_hosts()` 同一条纪律：
    漂了之后的表现是「宿主上算得出、容器里算不出」，而那在主表上只是一个空格。
    """
    assert ep._USAGE_ALIASES == LT.USAGE_ALIASES
    assert ep._CACHED_KEYS == LT.CACHED_KEYS
    assert ep._DETAIL_KEYS == LT.DETAIL_KEYS
    assert ep.WIRE_SHAPES == LT.WIRE_SHAPES


def test_read_side_normalizes_history_written_before_this_card():
    """历史 llm_log 里没有 `cached_prompt_tokens` / `wire_shape` —— 读取侧要能补上。

    h_claude-code 的记录长这样（边车当时已把 `input_tokens` 别名成 `prompt_tokens`，
    但缓存键是原样的 `cache_read_input_tokens`）。
    """
    old = {"decision": "allow", "status": 200, "path": "/anthropic/v1/messages?beta=true",
           "usage": {"prompt_tokens": 1461, "completion_tokens": 1377, "total_tokens": 2838,
                     "cache_creation_input_tokens": 0, "cache_read_input_tokens": 58368}}
    u = LT.usage_of(old)
    assert u["cached_prompt_tokens"] == 58368
    assert u["wire_shape"] == "anthropic_messages"
    assert u["total_tokens"] == 2838, "已有 total 不许被重算覆盖"


def test_cached_tokens_are_a_separate_column_not_folded_into_total():
    """`cached_prompt_tokens` **另记一列**，不并进 `total_tokens`。

    并进去会让 m6/m6b 那批走 Responses API、压根没有这个字段的历史 run 不可比 ——
    成本护栏的收益不抵可比性的损失（裁定见 `ops/tickets_inbox/3.3.md`）。
    这条同时钉住 `$` 列不变：`runner/pricing.CACHE_HIT_KEYS` 认的是**原始**键名，
    `cached_prompt_tokens` 不在其中，所以加这一列不会动任何历史的 `$`。
    """
    from runner import pricing as PR
    tot = LT.usage_totals([{"decision": "allow", "path": "/v1/chat/completions",
                            "usage": {"prompt_tokens": 100, "completion_tokens": 10,
                                      "total_tokens": 110, "prompt_cache_hit_tokens": 64}}])
    assert tot["total_tokens"] == 110, "总数里不许混进缓存读"
    assert tot["cached_prompt_tokens"] == 64
    assert "cached_prompt_tokens" not in PR.CACHE_HIT_KEYS, (
        "把它加进 CACHE_HIT_KEYS 会**改掉已经发布的 $ 列** —— 要改先过裁定")


# --------------------------------------------------------------------- 流式尾巴

def _chunked(payload: bytes, size: int = 4096) -> bytes:
    out = bytearray()
    for i in range(0, len(payload), size):
        part = payload[i:i + size]
        out += b"%x\r\n" % len(part) + part + b"\r\n"
    out += b"0\r\n\r\n"
    return bytes(out)


class _FakeSock:
    """把一段字节按固定块吐出来的假 socket；`sendall` 收到的原样存下。"""

    def __init__(self, data: bytes = b"", step: int = 3001):
        self._d, self._step, self.sent = data, step, bytearray()

    def recv(self, n):
        k = min(n, self._step, len(self._d))
        out, self._d = self._d[:k], self._d[k:]
        return out

    def sendall(self, b):
        self.sent += b


def test_chunked_decoder_matches_whole_shot_dechunk():
    """增量去分块与整段 `_dechunk` 必须逐字节一致（任意切分边界）。"""
    payload = (b"event: x\ndata: " + b"A" * 12345 + b"\n\n") * 3
    wire = _chunked(payload)
    for step in (1, 7, 4096, 100000):
        dec = ep._ChunkedDecoder()
        got = bytearray()
        for i in range(0, len(wire), step):
            got += dec.feed(wire[i:i + step])
        assert bytes(got) == payload, f"step={step}"
    assert ep._dechunk(wire) == payload


def test_usage_survives_a_stream_bigger_than_the_capture_cap():
    """**这张卡的根因判据。**

    留副本是有界的（一次流式响应可以很大），而**流式的 usage 在最后一个事件里**。
    只留头不留尾时，任何超过上限的流式响应抽出来都是 `{}` ——
    而 `{}` 与「上游没给 usage」在下游不可分，主表上就是 `Steps` 有数、`tokens/$` 是空。
    m6 里 16 条 `/v1/responses`、200、体大于 20000 字符却没有 usage 的记录，正是这个形状。
    """
    filler = b"".join(b'data: {"type":"response.output_text.delta","delta":"%d"}\n\n' % i
                      for i in range(3000))
    body = RESP_SSE[:RESP_SSE.index(b"event: response.completed")] + filler \
        + RESP_SSE[RESP_SSE.index(b"event: response.completed"):]
    assert len(body) > 150_000
    head = b"HTTP/1.1 200 OK\r\ntransfer-encoding: chunked\r\n\r\n"
    src, dst = _FakeSock(_chunked(body)), _FakeSock()
    h, t, n = ep._capture_head_tail(src, dst, head, b"", cap=50_000, tail_cap=20_000)

    assert n == len(body) and len(h) == 50_000, "副本必须是有界的，否则这条测的不是同一件事"
    assert ep._extract_usage(h, "/v1/responses") == {}, "只看头抽不到 —— 那正是坏掉的那一版"
    got = ep.usage_from_parts([h, t], "/v1/responses")
    assert got["prompt_tokens"] == 1200 and got["completion_tokens"] == 300
    assert got["cached_prompt_tokens"] == 1024
    # 转发出去的必须是**原样的线上字节**，一个不多一个不少。
    assert dst.sent == _chunked(body)


def test_capture_head_tail_passes_through_non_chunked_bodies():
    """`content-length` 的响应也要走同一条路（Codex 的 `/v1/models` 就是非流式 JSON）。"""
    head = b"HTTP/1.1 200 OK\r\ncontent-length: %d\r\n\r\n" % len(CHAT_JSON)
    src, dst = _FakeSock(CHAT_JSON), _FakeSock()
    h, t, n = ep._capture_head_tail(src, dst, head, b"")
    assert h == CHAT_JSON and n == len(CHAT_JSON) and dst.sent == CHAT_JSON
    assert ep._extract_usage(h, "/v1/chat/completions")["total_tokens"] == 1500


def test_usage_coverage_separates_our_fault_from_theirs():
    """`missing_reasons` 要能把「上游拒了」与「我们没留住」分开。

    混成一个数就分不开责任 —— 而这两件事的下一步动作完全不同：
    前者去看 harness 的协议，后者去看边车的副本上限。
    """
    trace = [
        {"decision": "allow", "status": 200, "path": "/v1/chat/completions",
         "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}},
        {"decision": "allow", "status": 404, "path": "/v1beta/models/x:streamGenerateContent"},
        {"decision": "allow", "status": 200, "path": "/v1/responses",
         "response_body": "event: response.created", "response_truncated": True},
        {"decision": "deny", "reason": "budget_exceeded", "status": 429},
    ]
    cov = LT.usage_coverage(trace)
    assert cov["calls"] == 3, "被拒的那条不是一次模型调用"
    assert cov["with_usage"] == 1 and cov["missing"] == 2
    assert cov["missing_reasons"] == {"truncated_no_usage": 1, "upstream_error": 1}
    assert LT.usage_coverage(None) is None
