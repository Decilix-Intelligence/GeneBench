# -*- coding: utf-8 -*-
"""`genebench_client.emit` —— 从 DataFrame / dict / list 构造合规的 `artifact.json`。

一句话：把「我算出来的东西」交给它，它负责把**格式**这一层做对 ——
三态声明字段齐、依赖图上的诚实终止、版本与信封字段、日期 ISO、代码写法、
数值不是字符串、枚举取值合法。业务值一个都不替你想。

最短用法::

    from genebench_client import emit

    art = emit.emit_s5(
        signals=df,                                   # 列 date / symbol / value
        declarations={"value_semantics": "rank", "signal_frequency": "daily",
                      "direction": "higher_is_long", "universe_ref": "csi300",
                      "missing_policy": "keep_null", "input_factors": ["gtja_191.001"]},
        as_of="2026-07-31",
    )
    art.write("/task/artifact.json")

助手**保证**的（这些是格式，不是判断）
--------------------------------------
1. **三态齐全**：该阶段契约要求的每一个声明字段都在。你没给的、或给了 `None` 的，
   一律写显式 ``"unresolved"`` —— **不填默认值**。缺失 ≠ 标记，而
   `"unresolved"` ≠ `null`（`null` 被 S5 的「无观点」占了）。
2. **依赖图（诚实终止）**：某个声明被标 `unresolved` 时，schema 里 `x-nullable-when`
   指着它的那些 payload 字段应当是 `null`。你没给 → 助手写 `null`；
   你给了完整的值 → 助手**抛** `HonestHaltConflict`，不静默丢弃你的数
   （「口径不知道」和「数算出来了」不能同时为真）。
3. **信封与版本**：`schema_version` 定死 v1.0；`task_id` / `config_id` / `arm` /
   `artifact_id` 从参数或 compose 注入的环境变量取；`as_of` 从参数或
   `gb.set_as_of()` 取，**取不到就抛 `AsOfRequired`，不猜**。
4. **写法归一**：紧凑日期 `20260731` → `2026-07-31`；`datetime` / `pandas.Timestamp`
   → ISO；股票代码 → `600000.SH` 这一种写法（湖/网关口径，`codes.to_lake`）；
   `numpy.int64` / `numpy.float64` → 原生 int / float；能转的数字字符串 → 数
   （schema 说 `number` 就不能是 `"0.31"`）；枚举取值不在表里当场报错。

助手**不做**的（做了就是替被测系统答题）
----------------------------------------
* **不猜业务值**：欠定的口径不填默认；`fill_rate` 不由 `fills / orders` 推；
  S7 少一个指标就报错，**不补 0**（`{}` 与 `0` 会被下游 `.get(k, 0)` 读成真 0）。
* **不补欠定字段**：S7 的探针字段你不给，产物里就是 `"unresolved"` ——
  这正是 validator 判「欠定被诚实标记」所需要的那个显式状态。
* **不静默重排**：S8 事件时间倒序 → 报错，不替你排（顺序错本身就是要被看见的事）。
* **不把 NaN 变成 0 或 null**：碰到 NaN / Inf 当场报错，让你自己决定是
  `null`（无观点）还是 `"flat"`（主动空仓）—— 这两件事在 S5 上判法完全不同。

规则来源
--------
只有 `emit_schemas.SCHEMAS`（= `ops/specs/artifact_schema/v1.0/S*.json` 的逐字副本，
也就是发给两臂的 `/task/S{k}.json`）与协议 validator 的判据。
**零 `reference/` 依赖** —— 与包里其余模块同一条纪律，`ops/test_emit.py` 用 AST 锁着。

自检
----
协议臂的容器里有 `/task/protocol/validate_artifact.py`，写完跑一遍::

    python3 /task/protocol/validate_artifact.py /task/artifact.json

它是评分的**子集**（不含网关日志探针、不比数）。emit 保证的是它管的那一层。
"""
from __future__ import annotations

import ast
import datetime as _dt
import json
import os
import re
from pathlib import Path
from typing import Any

from .codes import CodeError, iso_date, to_lake
from .emit_schemas import SCHEMAS, SCHEMA_VERSION, STAGES
from .errors import AsOfRequired, GenebenchClientError

__all__ = [
    "Artifact", "EmitError", "HonestHaltConflict", "UNRESOLVED", "FLAT",
    "context", "declaration_fields", "payload_keys", "depends_on", "fetch",
    "emit", "emit_s1", "emit_s2", "emit_s3", "emit_s4", "emit_s5", "emit_s6",
    "emit_s7", "emit_s8",
]

#: 声明字段的第三态。**不是 `null`**（`null` 是 S5 的「无观点」，语义不能复用）。
UNRESOLVED = "unresolved"
#: S5 的「主动空仓」。与 `null`（无观点）是两个状态。
FLAT = "flat"

#: compose 注入的身份（`runner/c41/runner_core.py` 的 task 服务 environment）。
TASK_ID_ENV = "GENEBENCH_TASK_ID"
CONFIG_ID_ENV = "GENEBENCH_CONFIG_ID"
ARM_ENV = "GENEBENCH_ARM"
RUN_ID_ENV = "GENEBENCH_RUN_ID"
SEED_ENV = "GENEBENCH_SEED"
AS_OF_ENV = "GENEBENCH_AS_OF"
#: 产物落点。题面的 `artifact_path` 就是这个（bundle 的 task.yaml）。
ARTIFACT_PATH_ENV = "GENEBENCH_ARTIFACT_PATH"
DEFAULT_ARTIFACT_PATH = "/task/artifact.json"


class EmitError(GenebenchClientError):
    """构造期就能看出来的问题。**当场抛，不产出半成品** ——
    一份「差一点」的 artifact 会一路走到结算侧才被判畸形，那时已经没人能修了。"""


class HonestHaltConflict(EmitError):
    """声明标了 `unresolved`，却又把依赖它的数算了出来。

    这在评分侧是 `computed_despite_unresolved`（违例，探针族 underdetermined）：
    口径不知道还能出数，等于私下挑了一个取值。助手不替你选一边 ——
    要么把声明填上（你其实知道），要么别给这个 payload 字段（你确实不知道）。
    """


class _Missing:
    def __repr__(self) -> str:            # pragma: no cover - 只为报错好看
        return "<未给>"


_MISSING = _Missing()


class Artifact(dict):
    """一份 artifact。就是 `dict`（`json.dumps` 直接可用），多一个 `write()`。"""

    def write(self, path: "str | Path | None" = None, *, indent: int = 1) -> Path:
        """落盘并返回路径。默认写 ``$GENEBENCH_ARTIFACT_PATH`` 或 ``/task/artifact.json``。"""
        p = Path(path or os.environ.get(ARTIFACT_PATH_ENV) or DEFAULT_ARTIFACT_PATH)
        if p.parent and not p.parent.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(indent=indent) + "\n", encoding="utf-8")
        return p

    def to_json(self, *, indent: int = 1) -> str:
        # allow_nan=False：NaN / Infinity 不是合法 JSON，写出去下游 json.load 会拿到
        # 一个 float('nan') 并一路算下去。这里宁可炸。
        return json.dumps(self, ensure_ascii=False, indent=indent, allow_nan=False)


# ============================================================== schema 派生的规则

def _schema(stage: str) -> dict:
    if stage not in SCHEMAS:
        raise EmitError(f"未知阶段 {stage!r}，只有 {list(STAGES)}")
    return SCHEMAS[stage]


def _decl_spec(stage: str) -> dict:
    return _schema(stage)["properties"]["declarations"]


def _pay_spec(stage: str) -> dict:
    return _schema(stage)["properties"]["payload"]


def declaration_fields(stage: str) -> tuple[str, ...]:
    """该阶段契约要求的声明字段（键集必须**精确等于**它 —— 多一个就是 `declaration_extra`）。"""
    return tuple(_decl_spec(stage).get("required", ()))


def payload_keys(stage: str) -> tuple[str, ...]:
    """该阶段 payload 的必填键。"""
    return tuple(_pay_spec(stage).get("required", ()))


_DEPS_RE = re.compile(r"\[([^\]]*)\]\s*$")


def depends_on(stage: str) -> dict[str, tuple[str, ...]]:
    """依赖图：``{payload 键: (它依赖的声明字段, ...)}``。

    直接从 schema 的 ``x-nullable-when`` 反推 —— 那句话的末尾就是生成器写下的
    ``sorted([...])``。不另抄一份表：抄的那份必然漂（本仓库栽过三次）。

    **它只知道 schema 说出来的那些。** 已知一处没说出来的：`S6.cash_ratio` 的形态
    本来就是 `["number", "null"]`，落盘时那个标记被跳过了，于是它对
    `weighting_scheme` 的依赖在题面里看不见。emit 不替它补（补了就是第二份规则），
    已登记 `ops/tickets_inbox/2.3.md`。
    """
    out: dict[str, tuple[str, ...]] = {}
    for key, spec in (_pay_spec(stage).get("properties") or {}).items():
        note = spec.get("x-nullable-when")
        if not isinstance(note, str):
            continue
        m = _DEPS_RE.search(note)
        if not m:                                     # pragma: no cover - 题面改写法才会走到
            raise EmitError(f"{stage}.{key} 的 x-nullable-when 读不出依赖清单：{note!r}")
        got = ast.literal_eval("[" + m.group(1) + "]")
        out[key] = tuple(str(x) for x in got)
    return out


# ============================================================== 值的归一

def _is_nan(x: Any) -> bool:
    return x != x


def _plain(x: Any) -> Any:
    """numpy / pandas 标量 → 原生 Python。不认识的原样返回。"""
    item = getattr(x, "item", None)
    if callable(item) and getattr(x, "shape", ()) == ():
        try:
            return x.item()
        except Exception:                              # pragma: no cover
            return x
    return x


def _jsonify(val: Any, path: str, *, dates: bool = True) -> Any:
    """任意 Python 值 → JSON 可写的值。**不做语义决定**，只做写法。"""
    val = _plain(val)
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (_dt.datetime,)):
        return val.isoformat()
    if isinstance(val, _dt.date):
        return val.isoformat()
    if isinstance(val, float):
        if _is_nan(val) or val in (float("inf"), float("-inf")):
            raise EmitError(
                f"{path} 是 {val!r} —— 助手不替你决定它该变成 0、null 还是 'flat'。"
                f"这三件事在评分侧判法完全不同（0 是一个数，null 是无观点，'flat' 是主动空仓）")
        return val
    if isinstance(val, (int, str)):
        return val
    if isinstance(val, dict):
        out = {}
        for k, v in val.items():
            kk = str(k)
            sub = f"{path}.{kk}"
            if kk == "params":
                # 你真正发出去的那次请求的参数。助手**一个字符都不改** ——
                # 改写它就等于让产物申报的请求与网关日志里那条对不上。
                out[kk] = _jsonify(v, sub, dates=False)
            elif dates and kk in ("date", "as_of") and v is not None:
                out[kk] = _as_date(v, sub)
            else:
                out[kk] = _jsonify(v, sub, dates=dates)
        return out
    if isinstance(val, (list, tuple)):
        return [_jsonify(v, f"{path}[{i}]", dates=dates) for i, v in enumerate(val)]
    if _is_nan(val):                                   # pandas.NaT / pd.NA
        raise EmitError(f"{path} 是缺失值（NaT/NA）—— 助手不替你决定它的含义")
    raise EmitError(f"{path} 是 {type(val).__name__}，不知道怎么写进 JSON；请先转成"
                    f" dict / list / 数 / 字符串 / None")


def _as_date(val: Any, path: str) -> str:
    try:
        return iso_date(_plain(val))
    except CodeError as e:
        raise EmitError(f"{path}: {e}") from None


def _as_int(val: Any, path: str, spec: dict) -> int:
    v = _plain(val)
    if isinstance(v, bool):
        raise EmitError(f"{path} 是 bool —— bool 不是整数（JSON 里 true ≠ 1）")
    if isinstance(v, float):
        if not v.is_integer():
            raise EmitError(f"{path}={v!r} 不是整数")
        v = int(v)
    elif isinstance(v, str):
        try:
            v = int(v.strip())
        except ValueError:
            raise EmitError(f"{path}={val!r} 不是整数") from None
    elif not isinstance(v, int):
        raise EmitError(f"{path}={val!r} 不是整数")
    lo = spec.get("minimum")
    if lo is not None and v < lo:
        raise EmitError(f"{path}={v} 小于 schema 的下界 {lo}")
    return v


def _as_number(val: Any, path: str, spec: dict) -> float:
    v = _plain(val)
    if isinstance(v, bool):
        raise EmitError(f"{path} 是 bool —— bool 不是数")
    if isinstance(v, str):
        try:
            v = float(v.strip())
        except ValueError:
            raise EmitError(f"{path}={val!r} 不是数（schema 说 number，字符串不算）") from None
    if not isinstance(v, (int, float)):
        raise EmitError(f"{path}={val!r} 不是数")
    v = float(v)
    if _is_nan(v) or v in (float("inf"), float("-inf")):
        raise EmitError(f"{path} 是 {v!r} —— 非有限数写不进 artifact，请自己决定怎么表示")
    for key, ok in (("minimum", lambda a, b: a >= b), ("maximum", lambda a, b: a <= b)):
        bound = spec.get(key)
        if bound is not None and not ok(v, bound):
            raise EmitError(f"{path}={v} 越出 schema 的 {key}={bound}")
    if spec.get("exclusiveMinimum") is not None and not v > spec["exclusiveMinimum"]:
        raise EmitError(f"{path}={v} 必须 > {spec['exclusiveMinimum']}")
    return v


def _as_string(val: Any, path: str, spec: dict) -> str:
    v = _plain(val)
    if isinstance(v, (_dt.datetime, _dt.date)):
        v = v.isoformat()
    if isinstance(v, bool) or not isinstance(v, str):
        raise EmitError(f"{path}={val!r} 必须是字符串")
    pat = spec.get("pattern")
    if pat:
        # 按写法逐个试：原样 → 去空白 → 小写（sha256 常见大写）→ ISO 日期。
        # 归一是**写法**，不是内容 —— 试不出来就报错，不硬塞。
        cands = [v, v.strip(), v.strip().lower()]
        try:
            cands.append(iso_date(v))
        except CodeError:
            pass
        for c in cands:
            if re.fullmatch(pat, c):
                v = c
                break
        else:
            raise EmitError(f"{path}={val!r} 不合 schema 的写法 {pat}")
    if len(v) < spec.get("minLength", 0):
        raise EmitError(f"{path} 是空串 —— schema 要求非空")
    return v


def _norm(spec: dict, val: Any, path: str) -> Any:
    """按 schema 的一小块归一一个值。spec 为空 = 无约束，只做写法转换。"""
    if val is None:
        return None
    if "anyOf" in spec:
        for branch in spec["anyOf"]:
            if "const" in branch and val == branch["const"]:
                return branch["const"]
        errs = []
        for branch in spec["anyOf"]:
            if "const" in branch:
                continue
            try:
                return _norm(branch, val, path)
            except EmitError as e:
                errs.append(str(e))
        raise EmitError(f"{path}={val!r} 不合任何一支 anyOf：{errs}")
    if "enum" in spec:
        v = _plain(val)
        if not isinstance(v, str):
            raise EmitError(f"{path}={val!r} —— 枚举字段必须是字符串，"
                            f"不接受 dict/list/数 包装；可选 {spec['enum']}")
        if v not in spec["enum"] and v.strip() in spec["enum"]:
            v = v.strip()
        if v not in spec["enum"]:
            raise EmitError(f"{path}={v!r} 不在 {spec['enum']}")
        return v
    t = spec.get("type")
    types = list(t) if isinstance(t, list) else ([t] if t else [])
    types = [x for x in types if x != "null"]
    if not types:
        return _jsonify(val, path)
    if "integer" in types:
        return _as_int(val, path, spec)
    if "number" in types:
        return _as_number(val, path, spec)
    if "boolean" in types:
        v = _plain(val)
        if not isinstance(v, bool):
            raise EmitError(f"{path}={val!r} 必须是 true/false（0/1 不算）")
        return v
    if "string" in types:
        return _as_string(val, path, spec)
    if "array" in types:
        items = _records(val, path)
        item_spec = spec.get("items") or {}
        out = [_norm(item_spec, x, f"{path}[{i}]") for i, x in enumerate(items)]
        if len(out) < spec.get("minItems", 0):
            raise EmitError(f"{path} 至少要有 {spec['minItems']} 项")
        if spec.get("uniqueItems") and len(out) != len({json.dumps(x, sort_keys=True) for x in out}):
            raise EmitError(f"{path} 的元素不得重复")
        return out
    if "object" in types:
        v = _plain(val)
        if not isinstance(v, dict):
            raise EmitError(f"{path}={val!r} 必须是对象")
        props = spec.get("properties") or {}
        out: dict[str, Any] = {}
        for k, sub in v.items():
            kk = str(k)
            if kk in props:
                out[kk] = _norm(props[kk], sub, f"{path}.{kk}")
            elif kk == "params":
                out[kk] = _jsonify(sub, f"{path}.{kk}", dates=False)
            elif kk in ("date", "as_of") and sub is not None:
                out[kk] = _as_date(sub, f"{path}.{kk}")
            else:
                out[kk] = _jsonify(sub, f"{path}.{kk}")
        miss = [k for k in (spec.get("required") or ()) if k not in out]
        if miss:
            raise EmitError(f"{path} 缺 {miss}（schema 要求）—— 助手不替你补：补出来的那个值会被当成你算的")
        return out
    return _jsonify(val, path)                          # pragma: no cover


def _records(val: Any, path: str) -> list:
    """DataFrame / list[dict] / tuple → list。DataFrame 按行取。"""
    if val is None:
        raise EmitError(f"{path} 不能是 None")
    if hasattr(val, "to_dict") and hasattr(val, "columns"):        # pandas.DataFrame
        return val.to_dict(orient="records")
    if hasattr(val, "to_dict") and hasattr(val, "index") and not isinstance(val, dict):
        raise EmitError(f"{path} 是 Series —— 请给 DataFrame 或 list[dict]，"
                        f"Series 少了列名，助手猜不出哪一列是什么")
    if isinstance(val, (list, tuple)):
        return list(val)
    raise EmitError(f"{path} 要 DataFrame 或 list，实得 {type(val).__name__}")


# ============================================================== 信封

def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


#: `context()` 认得的参数。多打一个字母就被静默忽略是最难查的那类错，所以这里查。
_CONTEXT_KEYS = ("task_id", "config_id", "arm", "as_of", "seed", "artifact_id", "produced_at")


def context(**over: Any) -> dict:
    """解析信封的身份字段。参数优先，其次是 compose 注入的环境变量。

    取不到就抛 —— **不猜**。猜一个 `task_id` 出来，评分侧的日志切片会静默切空
    （红队 rt05：改一个字母就把整族交叉核关掉），而产物上完全看不出来。
    """
    unknown = sorted(set(over) - set(_CONTEXT_KEYS))
    if unknown:
        raise EmitError(f"不认识这些参数：{unknown}。信封字段只有 {list(_CONTEXT_KEYS)}；"
                        f"payload 的键在各 emit_sN 的签名里，声明走 declarations=…")

    def pick(key: str, env_name: str) -> str:
        v = over.get(key)
        if v is None:
            v = _env(env_name)
        v = str(v).strip()
        if not v:
            raise EmitError(
                f"{key} 取不到：既没有传参，环境变量 {env_name} 也是空的。"
                f"容器里它由 compose 注入；在 f01 上直跑请显式传 {key}=…")
        return v

    task_id = pick("task_id", TASK_ID_ENV)
    config_id = pick("config_id", CONFIG_ID_ENV)
    arm = pick("arm", ARM_ENV)

    as_of = over.get("as_of") or _env(AS_OF_ENV)
    if not as_of:
        from . import get_as_of                        # 延迟 import：包根已装配好
        as_of = get_as_of()
    if not as_of:
        raise AsOfRequired(
            "as_of 取不到。它在题面的 task.yaml 里；启动时 `gb.set_as_of(spec['as_of'])`，"
            "或者 `emit_sN(..., as_of=...)`。**不猜** —— 猜出来的那个值会让越界变成合法请求。")
    as_of = _as_date(as_of, "as_of")

    seed = over.get("seed")
    if seed is None:
        seed = _env(SEED_ENV) or 0
    seed = _as_int(seed, "seed", {"minimum": 0})

    artifact_id = over.get("artifact_id") or _env(RUN_ID_ENV) or f"{task_id}.{arm}.{config_id}"
    produced_at = over.get("produced_at")
    if produced_at is None:
        produced_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    elif isinstance(produced_at, (_dt.datetime, _dt.date)):
        produced_at = produced_at.isoformat()

    return {"task_id": task_id, "config_id": config_id, "arm": arm, "as_of": as_of,
            "seed": seed, "artifact_id": str(artifact_id).strip(),
            "produced_at": str(produced_at)}


def _provenance(upstream: Any, stage: str, artifact_id: str) -> list:
    """`provenance` 是**列表**（可以为空）。每条是 {stage, artifact_id}。

    也收 ``{"S3": "…"}`` 或 ``["S3:…"]`` 这两种顺手的写法。
    """
    if upstream is None:
        return []
    out = []
    items: list = []
    if isinstance(upstream, dict):
        items = [{"stage": k, "artifact_id": v} for k, v in upstream.items()]
    else:
        items = _records(upstream, "provenance")
    for i, ref in enumerate(items):
        if isinstance(ref, str) and ":" in ref:
            st, _, aid = ref.partition(":")
            ref = {"stage": st.strip(), "artifact_id": aid.strip()}
        if not isinstance(ref, dict):
            raise EmitError(f"provenance[{i}] 须为 {{stage, artifact_id}}，实得 {ref!r}")
        st, aid = str(ref.get("stage", "")).strip().upper(), str(ref.get("artifact_id", "")).strip()
        if st not in STAGES or not aid:
            raise EmitError(f"provenance[{i}] 须为 {{stage ∈ {list(STAGES)}, artifact_id 非空}}，实得 {ref!r}")
        if st == stage and aid == artifact_id:
            raise EmitError(f"provenance[{i}] 引用了自己 —— 引用链成环，不可重放")
        out.append({"stage": st, "artifact_id": aid})
    return out


# ============================================================== 三态与依赖图

def _declarations(stage: str, given: "dict | None") -> dict:
    spec = _decl_spec(stage)
    props = spec.get("properties") or {}
    required = declaration_fields(stage)
    given = dict(given or {})
    extra = sorted(set(given) - set(required))
    if extra:
        raise EmitError(
            f"{stage} 的声明里多出 {extra} —— 键集必须**精确等于**契约必填集 "
            f"{list(required)}（多一个在评分侧就是 declaration_extra）")
    out: dict[str, Any] = {}
    for f in required:
        val = given.get(f, _MISSING)
        if val is _MISSING or val is None:
            # 没给 = 没有口径可写 → 显式标记。**不填默认值**：填了就是静默补全（第五探针）。
            out[f] = UNRESOLVED
            continue
        if isinstance(val, str) and val.strip() == UNRESOLVED:
            out[f] = UNRESOLVED
            continue
        out[f] = _norm(props.get(f, {}), val, f"declarations.{f}")
    return out


def _halted(stage: str, decl: dict) -> dict[str, tuple[str, ...]]:
    """本次产出里因为「口径被标 unresolved」而应当诚实终止的 payload 键。"""
    return {k: tuple(d for d in deps if decl.get(d) == UNRESOLVED)
            for k, deps in depends_on(stage).items()
            if any(decl.get(d) == UNRESOLVED for d in deps)}


def _payload(stage: str, given: dict, decl: dict, extra: "dict | None") -> dict:
    spec = _pay_spec(stage)
    props = spec.get("properties") or {}
    halted = _halted(stage, decl)
    out: dict[str, Any] = {}
    for key in payload_keys(stage):
        val = given.get(key, _MISSING)
        sub = props.get(key) or {}
        why = halted.get(key)
        if val is _MISSING or val is None:
            if why:
                out[key] = None                        # 诚实终止：口径不知道，数就不出
            elif key in _OPTIONAL_NULL.get(stage, ()):
                out[key] = None                        # 留位字段：可为 null，但必须存在
            else:
                raise EmitError(
                    f"{stage} 的 payload 缺 {key}（它不在诚实终止的范围里 —— "
                    f"依赖 {list(depends_on(stage).get(key, ())) or '无'}）。"
                    f"助手不替你补：补出来的那个值会被当成你算的。")
            continue
        if why:
            val = _halt_partial(stage, key, sub, val, why)
            if val is None:
                out[key] = None
                continue
        out[key] = _norm(sub, val, f"payload.{key}")
    for k, v in (extra or {}).items():
        # 档位追加的字段（`adjust_applied` / `search_count` / …）。schema 里没有它们的
        # 形态，助手只做写法转换，不编内容。
        if k in out:
            raise EmitError(f"extra 里的 {k} 与 payload 必填键重名")
        out[str(k)] = _jsonify(v, f"payload.{k}")
    return out


#: 「可为 null 但必须存在」的留位字段（题面明写 v1 可空）。**不是**诚实终止。
_OPTIONAL_NULL: dict[str, tuple[str, ...]] = {"S6": ("cash_ratio",)}


def _halt_partial(stage: str, key: str, sub: dict, val: Any, why: tuple) -> Any:
    """诚实终止范围内，调用方**给了**东西时怎么办。

    * 给的是一个对象、而 schema 要求的子键**没给全** → 把没给的那几个写 `null`
      （叶子级的诚实终止：S8 的 `fills.slippage_bps` 依赖 `slippage_reference_price`，
      `fill_rate` 不依赖，整块置 null 会把 `fill_rate` 的检查一起摘掉）；
    * 给全了 → 抛 `HonestHaltConflict`。口径不知道还能出数，评分侧就是
      `computed_despite_unresolved`。
    """
    need = tuple((sub.get("required") or ()))
    if isinstance(val, dict) and need:
        missing = [k for k in need if val.get(k, None) is None]
        if missing:
            return {**{k: None for k in missing}, **{k: v for k, v in val.items()}}
    raise HonestHaltConflict(
        f"{stage}.payload.{key} 给了值，但它依赖的口径 {list(why)} 被标了 {UNRESOLVED!r} —— "
        f"两件事不能同时为真。要么把这些声明填上（你其实知道口径），"
        f"要么别给 {key}（助手会写 null，那是诚实终止）")


# ============================================================== 总入口

def emit(stage: str, *, declarations: "dict | None" = None, payload: "dict | None" = None,
         upstream: Any = None, extra: "dict | None" = None, **ctx: Any) -> Artifact:
    """通用构造。八个 `emit_sN` 是它的具名外壳（参数名就是 payload 的键）。"""
    stage = str(stage).strip().upper()
    _schema(stage)
    c = context(**ctx)
    decl = _declarations(stage, declarations)
    pay = _payload(stage, dict(payload or {}), decl, extra)
    return Artifact({
        "schema_version": SCHEMA_VERSION,
        "artifact_id": c["artifact_id"],
        "stage": stage,
        "task_id": c["task_id"],
        "config_id": c["config_id"],
        "arm": c["arm"],
        "seed": c["seed"],
        "as_of": c["as_of"],
        "produced_at": c["produced_at"],
        "provenance": _provenance(upstream, stage, c["artifact_id"]),
        "declarations": decl,
        "payload": pay,
    })


def _pack(**kw: Any) -> dict:
    return {k: v for k, v in kw.items() if v is not _MISSING}


# ---------------------------------------------------------------- S1

#: HTTP 状态 → `fetches[].status` 的枚举。**HTTP 码本身不是这个枚举**
#: （真语料里有 artifact 写 `"status": 200`，那是畸形）。
#: 200 还要看行数：0 行是 `empty`，不是 `ok` —— 「空结果 / 拒绝 / 限流」必须可分辨。
_HTTP_STATUS = {403: "denied", 429: "rate_limited"}
_FETCH_STATUS = ("ok", "empty", "denied", "rate_limited")


def fetch(endpoint: str, params: dict, *, fetched_at: Any, rows: Any = None,
          status: Any = None, error: Any = None) -> dict:
    """拼一条 `S1.payload.fetches[]`。

    `status` 可以直接给枚举值，也可以给 HTTP 码（200 + rows==0 → `empty`），
    或者把网关抛的异常传给 `error`（`LookaheadDenied` → `denied`、
    `RateLimited` → `rate_limited`）。都没给就按 `rows` 判 ok / empty。

    `fetched_at` **原样保留**（字符串不重排格式）—— 评分侧要求它逐字等于某条网关
    日志的 `ts`，改写一个字符这族探针就整族失效。只有 `datetime` 才转 ISO。
    """
    from .errors import LookaheadDenied, RateLimited
    if isinstance(fetched_at, (_dt.datetime, _dt.date)):
        fetched_at = fetched_at.isoformat()
    st = status
    if isinstance(st, str) and st in _FETCH_STATUS:
        pass
    elif error is not None:
        if isinstance(error, LookaheadDenied):
            st = "denied"
        elif isinstance(error, RateLimited):
            st = "rate_limited"
        else:
            raise EmitError(f"不知道 {type(error).__name__} 该算哪一档 —— "
                            f"请显式给 status ∈ {list(_FETCH_STATUS)}")
    elif isinstance(st, int) and not isinstance(st, bool):
        if st in _HTTP_STATUS:
            st = _HTTP_STATUS[st]
        elif 200 <= st < 300:
            st = "empty" if (rows is not None and int(rows) == 0) else "ok"
        else:
            raise EmitError(f"HTTP {st} 落不进 {list(_FETCH_STATUS)} —— 请显式给 status")
    elif st is None:
        if rows is None:
            raise EmitError("既没给 status 也没给 rows —— 助手不猜这次取数是成功还是被拒")
        st = "empty" if int(rows) == 0 else "ok"
    else:
        raise EmitError(f"status={status!r} 不在 {list(_FETCH_STATUS)}")
    return {"endpoint": str(endpoint), "params": _jsonify(dict(params), "params", dates=False),
            "fetched_at": fetched_at, "status": st,
            "rows": None if rows is None else _as_int(rows, "rows", {"minimum": 0})}


def emit_s1(*, fetches: Any, fields_obtained: Any, **kw: Any) -> Artifact:
    """S1 取数留痕。

    `fetches`：DataFrame / list[dict]，每行 `{endpoint, params, fetched_at, status, rows}`
    （`emit.fetch()` 帮你拼）。`status` 是四值枚举，**不是 HTTP 码**。
    """
    return emit("S1", payload=_pack(fetches=fetches, fields_obtained=fields_obtained), **kw)


# ---------------------------------------------------------------- S2

def emit_s2(*, panel_ref: Any = _MISSING, field_map: Any = _MISSING,
            missing_rows: Any = _MISSING, adjust_applied: Any = _MISSING, **kw: Any) -> Artifact:
    """S2 对齐面板。`missing_rows` 收 `{"count": n}`，也收一个整数。

    `adjust_applied` 只有「复权处理结果」那一档的题要（题面的 `S2.json` 里会有它）；
    别的题不要给。
    """
    if missing_rows is not _MISSING and not isinstance(missing_rows, dict) and missing_rows is not None:
        missing_rows = {"count": missing_rows}
    extra = None if adjust_applied is _MISSING else {"adjust_applied": adjust_applied}
    return emit("S2", payload=_pack(panel_ref=panel_ref, field_map=field_map,
                                    missing_rows=missing_rows), extra=extra, **kw)


# ---------------------------------------------------------------- S3

def emit_s3(*, factor_id: Any = _MISSING, expression: Any = _MISSING, values_ref: Any = _MISSING,
            nonfinite: Any = _MISSING, warmup: Any = _MISSING,
            approximated_operators: Any = _MISSING, degeneracy: Any = _MISSING, **kw: Any) -> Artifact:
    """S3 因子实现。

    `approximated_operators` **必须显式给**（通常是 `[]`）—— 空列表与「没写」在
    评分侧不是一件事：前者是「我没做近似」，后者是缺字段。
    `warmup` 收 `{"nonnull_before_warmup": n}`，也收一个整数。
    """
    if warmup is not _MISSING and not isinstance(warmup, dict) and warmup is not None:
        warmup = {"nonnull_before_warmup": warmup}
    return emit("S3", payload=_pack(factor_id=factor_id, expression=expression,
                                    values_ref=values_ref, nonfinite=nonfinite, warmup=warmup,
                                    approximated_operators=approximated_operators,
                                    degeneracy=degeneracy), **kw)


# ---------------------------------------------------------------- S4

#: `ic_stats` 里**不是数**的那一项。schema 只到「必填这八个键」这一层（没有叶子类型），
#: 而卡 2.3 §3 的表把七项统计量写成数、`ci_method` 写成方法名，评分侧也有
#: `s4_ic_stat_not_number` 这个 code —— 所以这里按「除了 ci_method 都是数」归一。
_S4_NON_NUMERIC = ("ci_method",)


def emit_s4(*, ic_stats: Any = _MISSING, **kw: Any) -> Artifact:
    """S4 IC 统计。八个键一个都不能少；除 `ci_method` 外七项都必须是**数**，
    `"0.031"` 这种字符串会被归一成 `0.031`（schema 说 number，字符串不算）。"""
    if isinstance(ic_stats, dict):
        ic_stats = {k: (v if (k in _S4_NON_NUMERIC or v is None)
                        else _as_number(v, f"payload.ic_stats.{k}", {}))
                    for k, v in ic_stats.items()}
    return emit("S4", payload=_pack(ic_stats=ic_stats), **kw)


# ---------------------------------------------------------------- S5

def emit_s5(*, signals: Any = _MISSING, coverage: Any = _MISSING, **kw: Any) -> Artifact:
    """S5 信号。

    `signals`：DataFrame（列 `date` / `symbol` / `value`）或 list[dict]。
    `value` 三态：数 / `None`（无观点）/ `"flat"`（主动空仓）。**NaN 会报错** ——
    它到底是哪一个只有你知道，而 `no_data` 的格子里放数在评分侧就是 fillna 的形态。

    `coverage` 不给就**数出来**（`n_valued` / `n_null` / `n_flat`）——
    这是清点，不是编值；自报统计与内容不符在评分侧是畸形。给了就核，对不上当场报错。
    """
    kwargs = dict(kw)
    decl_preview = _declarations("S5", kwargs.get("declarations"))
    halted = _halted("S5", decl_preview)
    if signals is not _MISSING and signals is not None and "signals" not in halted:
        rows = [_signal_row(r, i) for i, r in enumerate(_records(signals, "payload.signals"))]
        signals = rows
        counted = {"n_valued": sum(1 for r in rows if r["value"] is not None and r["value"] != FLAT),
                   "n_null": sum(1 for r in rows if r["value"] is None),
                   "n_flat": sum(1 for r in rows if r["value"] == FLAT)}
        if coverage is _MISSING or coverage is None:
            coverage = counted
        else:
            got = {k: _as_int(coverage[k], f"coverage.{k}", {"minimum": 0})
                   for k in ("n_valued", "n_null", "n_flat") if k in coverage}
            bad = {k: (v, counted[k]) for k, v in got.items() if v != counted[k]}
            if bad:
                raise EmitError(f"自报的 coverage 与 signals 的内容不符（键: 你写的, 实际数）：{bad}")
            coverage = counted
    return emit("S5", payload=_pack(signals=signals, coverage=coverage), **kwargs)


def _signal_row(r: Any, i: int) -> dict:
    path = f"payload.signals[{i}]"
    if not isinstance(r, dict):
        raise EmitError(f"{path} 须为 {{date, symbol, value}}，实得 {type(r).__name__}")
    miss = [k for k in ("date", "symbol", "value") if k not in r]
    if miss:
        raise EmitError(f"{path} 缺 {miss} —— 「没有观点」要写 value=None，不是不写这一行")
    val = _plain(r["value"])
    if isinstance(val, str):
        if val.strip() != FLAT:
            raise EmitError(f"{path}.value={val!r} —— 只能是数 / None（无观点）/ {FLAT!r}（主动空仓）")
        val = FLAT
    elif val is not None:
        if isinstance(val, float) and _is_nan(val):
            raise EmitError(
                f"{path}.value 是 NaN —— 助手不替你决定：None（我没观点）、{FLAT!r}"
                f"（我主动空仓）还是一个数？在 S5 上这三件事判法完全不同。"
                f"（如果你本来写的就是 None：DataFrame 的浮点列会把 None 存成 NaN，"
                f"到这里已经分不开了 —— 用 "
                f"df[\'value\'] = df[\'value\'].astype(object).where(df[\'value\'].notna(), None) "
                f"或直接传 list[dict]。）")
        val = _as_number(val, f"{path}.value", {})
    out = {k: v for k, v in r.items() if k not in ("date", "symbol", "value")}
    out = _jsonify(out, path)
    out.update({"date": _as_date(r["date"], f"{path}.date"),
                "symbol": _symbol(r["symbol"], f"{path}.symbol"), "value": val})
    return out


def _symbol(s: Any, path: str) -> str:
    """代码归一到湖/网关的写法（`600000.SH`）。认不出来的原样留下（可能是指数或自定义标的）。"""
    v = _plain(s)
    if not isinstance(v, str) or not v.strip():
        raise EmitError(f"{path}={s!r} 必须是非空字符串")
    try:
        return to_lake(v)
    except CodeError:
        return v.strip()


# ---------------------------------------------------------------- S6

def emit_s6(*, targets: Any = _MISSING, cash_ratio: Any = _MISSING, **kw: Any) -> Artifact:
    """S6 目标组合。

    `targets`：list[dict]，每项 `{date, solver_status, positions}`；`positions` 的每行
    要有台账六字段 `symbol / score / previous_weight / target_weight / delta_weight /
    reference_close`（也收 DataFrame）。`delta_weight` 没给就按
    `target_weight − previous_weight` 补上 —— 那是定义式，不是业务判断。

    `cash_ratio` 是 N-26 的留位字段：v1 可以是 `null`，但**必须存在**。
    """
    if targets is not _MISSING and targets is not None:
        days = []
        for i, day in enumerate(_records(targets, "payload.targets")):
            if not isinstance(day, dict):
                raise EmitError(f"payload.targets[{i}] 须为 {{date, solver_status, positions}}")
            day = dict(day)
            pos = day.get("positions")
            if pos is not None:
                day["positions"] = [_position(p, f"payload.targets[{i}].positions[{j}]")
                                    for j, p in enumerate(_records(pos, f"payload.targets[{i}].positions"))]
            days.append(day)
        targets = days
    return emit("S6", payload=_pack(targets=targets,
                                    cash_ratio=None if cash_ratio is _MISSING else cash_ratio), **kw)


_LEDGER = ("symbol", "score", "previous_weight", "target_weight", "delta_weight", "reference_close")


def _position(p: Any, path: str) -> dict:
    if not isinstance(p, dict):
        raise EmitError(f"{path} 须为持仓台账行 {list(_LEDGER)}")
    p = dict(p)
    if "delta_weight" not in p or p.get("delta_weight") is None:
        tw, pw = p.get("target_weight"), p.get("previous_weight")
        if tw is None or pw is None:
            raise EmitError(f"{path} 缺 delta_weight，而 target_weight / previous_weight "
                            f"也不全 —— 助手只按定义式补（target − previous），不猜")
        p["delta_weight"] = _as_number(tw, f"{path}.target_weight", {}) - \
            _as_number(pw, f"{path}.previous_weight", {})
    miss = [k for k in _LEDGER if k not in p]
    if miss:
        raise EmitError(f"{path} 缺台账字段 {miss}")
    out = _jsonify({k: v for k, v in p.items() if k not in _LEDGER}, path)
    out["symbol"] = _symbol(p["symbol"], f"{path}.symbol")
    for k in _LEDGER[1:]:
        out[k] = _as_number(p[k], f"{path}.{k}", {})
    return out


# ---------------------------------------------------------------- S7

def emit_s7(*, metrics: Any = _MISSING, n_days: Any = _MISSING, ledger_check: Any = _MISSING,
            attribution: Any = _MISSING, rebalance_frequency: Any = _MISSING, **kw: Any) -> Artifact:
    """S7 回测。

    `metrics` 十一项一个都不能少，**turnover 双记**（one-way 与 two-way 是两个数，
    不是一个数的两种叫法）。少一项就报错 —— 助手不补 0（`{}` / `0` 会被下游
    `.get(k, 0)` 读成真 0，直接进阶段均值与排名）。

    `payload.rebalance_frequency` 是**回显**声明值（契约 §7），不给就自动回显；
    `ledger_check` 收 `{"max_abs_residual": x}`，也收一个数。
    """
    if ledger_check is not _MISSING and not isinstance(ledger_check, dict) and ledger_check is not None:
        ledger_check = {"max_abs_residual": ledger_check}
    if metrics is not _MISSING and isinstance(metrics, dict):
        need = tuple((_pay_spec("S7")["properties"]["metrics"].get("required") or ()))
        miss = [k for k in need if k not in metrics]
        if miss:
            raise EmitError(
                f"S7 的 metrics 缺 {miss} —— 助手**不补 0**：`{{}}` 与 `0` 在下游会被 "
                f".get(k, 0) 读成真 0，进阶段均值与排名。算不出来就说算不出来（把对应口径标 "
                f"{UNRESOLVED!r}，整份 metrics 走诚实终止）")
    if rebalance_frequency is _MISSING:
        rebalance_frequency = _declarations("S7", kw.get("declarations")).get("rebalance_frequency")
    return emit("S7", payload=_pack(metrics=metrics, n_days=n_days,
                                    rebalance_frequency=rebalance_frequency,
                                    ledger_check=ledger_check, attribution=attribution), **kw)


# ---------------------------------------------------------------- S8

def emit_s8(*, events: Any = _MISSING, state_transitions: Any = _MISSING, fills: Any = _MISSING,
            overreach: Any = _MISSING, **kw: Any) -> Artifact:
    """S8 模拟盘。

    `events` 按时间**单调不减**；乱序会报错，助手**不替你排** ——
    顺序本身就是「事件链可重放」这条判据要看的东西。
    `overreach` 收 `{"denied_requests": n}`，也收一个整数（它必须等于网关日志里的
    403 次数，评分侧不采信自报）。
    """
    if overreach is not _MISSING and not isinstance(overreach, dict) and overreach is not None:
        overreach = {"denied_requests": overreach}
    if events is not _MISSING and events is not None:
        # 拷一层再动 —— 助手不改调用方手里的那个 list[dict]
        rows = [dict(e) if isinstance(e, dict) else e for e in _records(events, "payload.events")]
        _check_monotonic(rows)
        events = rows
    return emit("S8", payload=_pack(events=events, state_transitions=state_transitions,
                                    fills=fills, overreach=overreach), **kw)


def _check_monotonic(rows: list) -> None:
    last = None
    last_seq = None
    for i, e in enumerate(rows):
        if not isinstance(e, dict):
            raise EmitError(f"payload.events[{i}] 须为 {{ts, type, …}}")
        ts = e.get("ts")
        if isinstance(ts, (_dt.datetime, _dt.date)):
            ts = ts.isoformat()
            e["ts"] = ts
        cur = _parse_ts(ts)
        if cur is None:
            raise EmitError(f"payload.events[{i}].ts={ts!r} 不是可解析的 ISO 时刻")
        if last is not None and cur < last:
            raise EmitError(
                f"payload.events[{i}].ts={ts!r} 早于上一条 —— 事件链必须按时间单调。"
                f"助手不替你排序：顺序错本身就是「可重放」这条判据要看的东西")
        last = cur
        seq = e.get("seq")
        if seq is not None:
            seq = _as_int(seq, f"payload.events[{i}].seq", {})
            if last_seq is not None and seq < last_seq:
                raise EmitError(f"payload.events[{i}].seq={seq} 比上一条小 —— seq 必须单调不减")
            last_seq = seq


def _parse_ts(s: Any) -> "_dt.datetime | None":
    if not isinstance(s, str) or not s.strip():
        return None
    x = s.strip().replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(x)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
