# -*- coding: utf-8 -*-
"""记忆这一头：FinMem 的向量后端。

## 替换的是上游的哪个东西

`puppy/memorydb.py` 的 `MemoryDB.__init__` 第 56 行**写死**了向量后端：

    self.emb_func = OpenAILongerThanContextEmb(**self.emb_config)
    self.emb_dim = self.emb_func.get_embedding_dimension()

`OpenAILongerThanContextEmb`（`puppy/embedding.py`）走
`langchain_community.embeddings.OpenAIEmbeddings`，模型 `text-embedding-ada-002`。
它没有注入点 —— 所以接线层顶替的是**模块属性** `puppy.memorydb.OpenAILongerThanContextEmb`
（那一行到运行时才查名字，顶替对它有效）。

## 为什么要替

分层记忆是 FinMem 的核心，没有向量后端它一步都跑不动。而本环境的模型经边车
路由到 `deepseek-chat`，**embeddings 是不是可用是一件要实测的事，不是一件可以断言的事**。
所以这里的做法是：

1. **先真打一次**（一次，全进程只一次）：`POST {OPENAI_BASE_URL}/embeddings`。
   成功就用它，维度取回包里那个，`backend="remote"`。
   —— 这一次探针也会进边车的 `llm_log`，是这条结论的证据。
2. 打不通（非 200 / 形状不对 / 连不上）就退到**离线确定性向量**，
   `backend="offline_hash"`，并把 `status` 与原因记进 `report()`，由
   `run.py` 打到 stderr、写进 `/tmp` 的接入报告。

**这是一处替换，不是一处「没有数据」。** 它会改变检索质量，因此写在
`README.md` 的「已知限制」里，而不是藏在代码注释里。

## 离线向量是什么

哈希袋（hashing trick）：正则切出词/CJK 单字 → `blake2b` 定址与定号 →
`log(1+tf)` 累加 → L2 归一。**确定性、零网络、零模型文件**。
它保的是「字面重合的两段文字相似」，保不了「语义相近但用词不同的两段文字相似」。

空文本给一个由常量派生的固定非零向量：本环境每一天都没有新闻，而上游对
「今天没有新闻」的处理是往短期记忆里塞一个空串（`environment.py` 的
`cur_news = {self.symbol: ''}`）。全零向量在 `IndexFlatIP` 下与任何查询的内积
都是 0，检索退化成任取；固定非零向量至少是**确定的**。
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Any, List, Union

import numpy as np

#: ada-002 的维度。远端可用时以回包实际长度为准。
DEFAULT_DIM = 1536

#: 空文本的定位常量（只影响「空记忆」这一条向量落在哪，不影响任何真实文本）。
_EMPTY_TOKEN = "\x00genebench-empty\x00"

_TOKEN = re.compile(r"[a-z0-9]+|[一-鿿]")

#: 全进程只探一次。四个 MemoryDB 各自 new 一个后端，不该打四次网。
_PROBE: dict[str, Any] | None = None


def _base_url() -> str | None:
    for k in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "LLM_BASE_URL"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v.rstrip("/")
    return None


def probe(model: str) -> dict[str, Any]:
    """真打一次 `/embeddings`。**永不抛** —— 探针失败是一个结论，不是一次崩溃。"""
    global _PROBE
    if _PROBE is not None:
        return _PROBE
    out: dict[str, Any] = {"backend": "offline_hash", "dim": DEFAULT_DIM,
                           "model": model, "status": None, "reason": None}
    if (os.environ.get("GENEBENCH_FINMEM_EMB_PROBE") or "1").strip() not in ("1", "true", "yes"):
        out["reason"] = "probe_disabled_by_env"
        _PROBE = out
        return out
    base = _base_url()
    if not base:
        out["reason"] = "no_base_url_env"
        _PROBE = out
        return out
    out["endpoint"] = f"{base}/embeddings"
    try:
        import httpx

        rsp = httpx.post(
            out["endpoint"],
            headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '-')}",
                     "Content-Type": "application/json"},
            json={"model": model, "input": ["genebench embedding probe"]},
            timeout=60.0,
        )
        out["status"] = rsp.status_code
        if rsp.status_code != 200:
            out["reason"] = f"http_{rsp.status_code}"
            out["body_head"] = rsp.text[:300]
        else:
            vec = rsp.json()["data"][0]["embedding"]
            out["backend"] = "remote"
            out["dim"] = len(vec)
            out["reason"] = "ok"
    except Exception as exc:  # noqa: BLE001
        out["reason"] = f"{type(exc).__name__}: {exc}"[:300]
    _PROBE = out
    return out


def _hash_vec(text: str, dim: int) -> np.ndarray:
    vec = np.zeros(dim, dtype="float32")
    toks = _TOKEN.findall((text or "").lower()) or [_EMPTY_TOKEN]
    counts: dict[str, int] = {}
    for t in toks:
        counts[t] = counts.get(t, 0) + 1
    for tok, tf in counts.items():
        h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(h[:4], "big") % dim
        sign = 1.0 if h[4] & 1 else -1.0
        vec[idx] += sign * math.log1p(tf)
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


class GatewayEmb:
    """顶替 `puppy.memorydb.OpenAILongerThanContextEmb` 的向量后端。

    签名与上游一致（`emb_config` 是题面之外的配置，逐字来自上游的
    `config/tsla_gpt_config.toml` 的 `[agent.agent_1.embedding.detail]`）。
    """

    def __init__(self, openai_api_key: Union[str, None] = None,
                 embedding_model: str = "text-embedding-ada-002",
                 chunk_size: int = 5000, verbose: bool = False) -> None:
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.verbose = verbose
        self.info = probe(embedding_model)
        self.backend = self.info["backend"]
        self.dim = int(self.info["dim"])

    # 上游只用这两个入口。
    def get_embedding_dimension(self) -> int:
        return self.dim

    def __call__(self, text: Union[List[str], str]) -> np.ndarray:
        if isinstance(text, str):
            text = [text]
        if not text:
            # 上游在「新闻是空列表」时会走到这里；返回形状对的空矩阵，
            # 让 faiss 自己按 0 行处理，而不是让 np.array([]) 变成一维。
            return np.zeros((0, self.dim), dtype="float32")
        if self.backend == "remote":
            return self._remote(list(text))
        return np.vstack([_hash_vec(t, self.dim) for t in text]).astype("float32")

    def _remote(self, texts: List[str]) -> np.ndarray:
        import httpx

        rsp = httpx.post(
            self.info["endpoint"],
            headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '-')}",
                     "Content-Type": "application/json"},
            json={"model": self.embedding_model, "input": texts},
            timeout=120.0,
        )
        rsp.raise_for_status()
        data = sorted(rsp.json()["data"], key=lambda d: d.get("index", 0))
        return np.array([d["embedding"] for d in data], dtype="float32")


def install(puppy_memorydb_module) -> type:
    setattr(puppy_memorydb_module, "OpenAILongerThanContextEmb", GatewayEmb)
    return GatewayEmb


def assert_seam_installed(puppy_memorydb_module) -> None:
    cur = getattr(puppy_memorydb_module, "OpenAILongerThanContextEmb")
    if cur is not GatewayEmb:
        raise AssertionError(
            "puppy.memorydb.OpenAILongerThanContextEmb 还是上游那一个 —— "
            "它会去 langchain 的 OpenAIEmbeddings 取向量。")
