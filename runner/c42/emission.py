"""卡 4.2 §8：调用点 shim 协议 + parser。

每个适配器配一个**进容器的发射 shim**，写 `out/emission.jsonl`（容器里是
`/task/out/emission.jsonl`），一行一 JSON。**parser 只读 `emission.jsonl`**，
因而**框架无关**、可用夹具测试 —— 这是 A 档能占 2/3 的前提。

**判别力：为什么没有 shim 就是假绿**（两个具体的量）

* `nonfinite.replaced_count` **事后不可观测**：一个把 NaN 替换成 0 的实现，交出来的序列里
  恰好**没有 NaN** —— 事后扫描得到的永远是 `0`，而 `0` 与「真的没替换」**逐字节相同**。
  卡 2.3 的 `nonfinite_silently_replaced`（probe=`nonfinite_propagation`）因此**永远不会响**。
* `approximated_operators` 只在**生成代码那一刻**可见。事后扫描得到 `[]`，
  `operator_approximated` 探针同样永绿。

这两族探针在「不装 shim」的方案下**存在但保护为零** —— 机制在，保护不在。

**本模块产的是证据，不是字段**（裁定 2026-09-04）。先前的 `nonfinite_payload()`
拿 harness 重算的 inf/nan 加 shim 汇总的 replaced_count **拼出一个 payload 对象** ——
那是整个仓库里唯一一处真的在往 agent 的字段里写的代码，也正是「重算即替代」的实例：
替代之后，`nonfinite_silently_replaced` 比的是我们与我们自己。

现在的形态：`replaced_count` 由 **agent 自报**（它没写就是 `s3_nonfinite_missing`，
那是正确结论）；shim 的计数走 `nonfinite_replaced_count()` 落旁路 `harness_checks`，
与自报值比对，不一致即 finding（**agent 隐瞒了替换**）。

**「证据不可得」不得冒充「一致」**：没装 shim 时本模块返回 `None`，
`origin.cross_check` 判 `unverified` —— 不是 `agree`。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#: shim 相对 `/task` 的落点。与 harvest 的产出物清单同源。
EMISSION_REL = "out/emission.jsonl"

KINDS: tuple[str, ...] = (
    "declaration", "factor_values", "signal_row", "metric", "ledger_day",
    "fetch", "nonfinite_replace", "llm_call", "loop_boundary", "framework_error",
)


class EmissionError(RuntimeError):
    pass


def _check_kind(kind: str) -> str:
    if kind not in KINDS:
        raise EmissionError(
            f"未知发射类型 {kind!r}；合法值 {list(KINDS)}。"
            f"静默接受未知类型 = 让一个没人解析的量看起来被记录了")
    return kind


class Shim:
    """**容器内**的写入端。零依赖（只用标准库）—— 它要被复制进被测框架的进程里。

    钩在调用点上，在**事情发生的那一刻**写；`with` 退出即 flush。
    """

    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("GENEBENCH_EMISSION", f"/task/{EMISSION_REL}"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = None

    def __enter__(self) -> "Shim":
        self._fh = open(self.path, "a", encoding="utf-8")
        return self

    def __exit__(self, *exc) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def emit(self, kind: str, **fields) -> dict:
        rec = {"kind": _check_kind(kind), **fields}
        line = json.dumps(rec, ensure_ascii=False, sort_keys=False)
        if self._fh is not None:
            self._fh.write(line + "\n")
            self._fh.flush()
        else:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return rec


def parse_emissions(path) -> list[dict] | None:
    """读端。文件不存在 → `None`（**没装 shim**），存在且零行 → `[]`（**装了但没触发**）。

    与 §7 的三态同一条理由：`[]` 与 `None` 在数值上不可区分，而结论相反 ——
    前者说「这次没替换」，后者说「这次根本没测」。
    """
    p = Path(path)
    if not p.exists():
        return None
    out: list[dict] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as ex:
            raise EmissionError(f"{p}:{i} 不是 JSON：{ex}") from None
        if not isinstance(rec, dict) or "kind" not in rec:
            raise EmissionError(f"{p}:{i} 缺 kind")
        _check_kind(rec["kind"])
        out.append(rec)
    return out


def of_kind(emissions: list[dict] | None, kind: str) -> list[dict] | None:
    if emissions is None:
        return None
    return [e for e in emissions if e.get("kind") == _check_kind(kind)]


def nonfinite_replaced_count(emissions: list[dict] | None) -> int | None:
    """**证据侧**：shim 记下的替换次数。没装 shim → `None`（不可得），不是 `0`。

    为什么必须是 shim：一个把 NaN 替换成 0 的实现，交出来的序列里恰好**没有** NaN ——
    事后扫描得到的永远是 `0`，而 `0` 与「真的没替换」逐字节相同（§8.2）。
    R 在这个量上不可行，只有 S。
    """
    hits = of_kind(emissions, "nonfinite_replace")
    if hits is None:
        return None
    return sum(int(e.get("count", 1)) for e in hits)


#: 由 shim 提供证据的 payload 叶子（`origin.PAYLOAD_CHECK` 里 source=shim 且 evidence=shim_log 的那些）。
SHIM_EVIDENCED: dict[str, tuple[str, ...]] = {
    "S3": ("nonfinite.replaced_count", "approximated_operators"),
}


def harness_values(emissions: list[dict] | None, *, stage: str) -> dict:
    """给 `origin.cross_check_all` 的旁路证据字典。**只含 shim 能作证的叶子。**

    不可得的叶子给 `None` 而不是省略 —— 省略与「证据说 0」在下游不可分。
    """
    if stage != "S3":
        return {}
    return {"nonfinite.replaced_count": nonfinite_replaced_count(emissions),
            "approximated_operators": approximated_operators(emissions)}


def approximated_operators(emissions: list[dict] | None) -> list[str] | None:
    """S3 的 `payload.approximated_operators`。没装 shim → `None`（键不写）。

    装了 shim、真的一个都没近似 → `[]` —— 那是**有意义的零**，与 `None` 不是一回事。

    协议：**任何**一条发射都可以带 `approximated_operators: [算子名]`，由 shim 在
    「拿一个近似实现顶替原算子」的**那一刻**写下。不给它单独一个 kind 是因为近似发生在
    别的动作里（生成表达式、算值），单独一个 kind 会让 shim 必须多记一次时序。
    """
    if emissions is None:
        return None
    names: list[str] = []
    for e in emissions:
        for op in e.get("approximated_operators") or []:
            if not isinstance(op, str) or not op:
                raise EmissionError(f"approximated_operators 里有非法算子名 {op!r}")
            if op not in names:
                names.append(op)
    return names
