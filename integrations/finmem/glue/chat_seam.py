# -*- coding: utf-8 -*-
"""模型这一头：让 FinMem 的 chat 层认识「OpenAI 兼容的第三方端点」。

## 替换的是上游的哪个东西

`puppy/chat.py::ChatOpenAICompatible` 按**模型名前缀**分三条路
（`gpt` / `gemini-pro` / `tgi`），`parse_response` 对这三者之外的模型名
**当场 `NotImplementedError`**：

    def parse_response(self, response):
        if self.model.startswith("gpt"): ...
        elif self.model.startswith("gemini-pro"): ...
        elif self.model.startswith("tgi"): ...
        else: raise NotImplementedError(f"Model {self.model} not implemented")

本环境的模型是 `deepseek-chat`（经边车的 OpenAI 兼容口）。**请求那一头本来就对**
—— `__init__` 的 else 分支给的正是 `Authorization: Bearer` + JSON，
`guardrail_endpoint()` 的 else 分支发的正是 `{"model": …, "messages": […]}`。
只有**读响应**那一步不认。所以接线层只做一件事：**子类覆盖 `parse_response`**，
按 OpenAI 兼容的 wire 形状取 `choices[0].message.content`。

不改内核（改了 `pin.json` 的 `commit` 就不再是那份字节），也不谎报模型名 ——
把 `model` 写成 `gpt-…` 去骗那个 `startswith` 会让 payload 里的模型名与
真正被调用的模型对不上，而边车与 `llm_log` 记的是 payload 里那个名字。

## base URL 只从环境变量取

`end_point` 由 `build_chat_config()` 从 `OPENAI_BASE_URL` / `OPENAI_API_BASE` /
`LLM_BASE_URL` 拼出来（`{base}/chat/completions`），**没有任何写死的主机名**：
写死就绕过了边车，那条路上没有 usage、没有预算闸、什么都看不见。
"""
from __future__ import annotations

import os
from typing import Any

#: 顺序即优先级。三个都没有就退出 —— 不猜一个端点。
BASE_URL_ENVS = ("OPENAI_BASE_URL", "OPENAI_API_BASE", "LLM_BASE_URL")


def base_url() -> str:
    for k in BASE_URL_ENVS:
        v = (os.environ.get(k) or "").strip()
        if v:
            return v.rstrip("/")
    raise SystemExit("OPENAI_BASE_URL / OPENAI_API_BASE / LLM_BASE_URL 都没设 —— "
                     "模型只能经边车，写死主机名会绕开预算闸与 usage 归属。")


def make_subclass(upstream_cls):
    """按上游的类造一个只覆盖 `parse_response` 的子类。"""

    class GatewayChatOpenAICompatible(upstream_cls):  # type: ignore[misc,valid-type]
        """只覆盖读响应那一步；请求那一头逐字沿用上游的 else 分支。"""

        def parse_response(self, response) -> str:  # noqa: D102
            body = response.json()
            try:
                return body["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                # 不吞：形状不对就报出来。静默返回空串会让「模型没答」
                # 与「答了但我们没解析」在日志里长得一模一样。
                raise RuntimeError(
                    f"边车返回的不是 OpenAI 兼容的 chat 形状：{str(body)[:400]}") from exc

    return GatewayChatOpenAICompatible


def install(puppy_agent_module, puppy_chat_module) -> type:
    """把 `puppy.agent` 手里的 `ChatOpenAICompatible` 换成子类。

    换的是 **`puppy.agent` 模块命名空间里的那个名字** —— `agent.py` 是
    `from .chat import ChatOpenAICompatible`，它持有的是自己那份引用，
    只改 `puppy.chat` 对它无效（这一条是 `install()` 存在的全部理由）。
    """
    upstream = getattr(puppy_chat_module, "ChatOpenAICompatible")
    sub = make_subclass(upstream)
    setattr(puppy_agent_module, "ChatOpenAICompatible", sub)
    return sub


def assert_seam_installed(puppy_agent_module, puppy_chat_module) -> None:
    """替换之后必须成立；**替换之前必须不成立**（非空证明见 smoke）。"""
    cur = getattr(puppy_agent_module, "ChatOpenAICompatible")
    base = getattr(puppy_chat_module, "ChatOpenAICompatible")
    if cur is base or not issubclass(cur, base):
        raise AssertionError("puppy.agent.ChatOpenAICompatible 还是上游那一个 —— "
                             "非 gpt/gemini/tgi 的模型名会在 parse_response 里炸。")


def build_chat_config(model: str, system_message: str) -> dict[str, Any]:
    """`config["chat"]`：三个键是上游 `__init__` 强制取的，多的会被当作 payload 参数。

    **不要加 `max_token_short`** —— 上游一旦看见它就会去 `TextTruncator`
    里 `AutoTokenizer.from_pretrained(...)`，那是运行期下载模型，容器里断网。
    """
    return {
        "end_point": f"{base_url()}/chat/completions",
        "model": model,
        "system_message": system_message,
    }
