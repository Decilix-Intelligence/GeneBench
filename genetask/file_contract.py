"""产出文件契约的**执行面副本 + 唯一写入函数体**（N-44）。

**为什么不放在 `reference/`**：写端有两个 —— gold 在数据面（f01），
适配器在执行面（f02），而执行面**不得 import `reference/`**
（`ops/test_inject.py::test_t11_execution_plane_modules_never_reach_reference`）。
把写入函数体放在 reference 里，执行面就只能自己再抄一份 —— 而那正是 §9
「与 gold 同一函数体」要防的事。

所以：**契约是数据**（`FILE_SPECS`，镜像自 `reference.artifact_schema.PAYLOAD_FILES`，
同源断言在 `ops/test_c42.py`），**函数体只有一份**（本模块），两侧都调它。
`reference/files_io.py` 是数据面的薄封装，从冻结件取 spec 再调这里。
"""
from __future__ import annotations

from pathlib import Path

#: **镜像**。改这里之前先改 `reference/artifact_schema.py::PAYLOAD_FILES` ——
#: 那份是契约，这份是副本，同源断言盯着它们别漂。
FILE_SPECS: dict[str, tuple[dict, ...]] = {
    "S2": ({"ref": "panel_ref", "path": "/task/panel.csv", "format": "csv",
            "columns": ("symbol", "date", "close", "high", "low", "volume"),
            "sort": ("symbol", "date"), "header": True, "index": False,
            "float_format": "%.6f", "encoding": "utf-8"},),
    "S3": ({"ref": "values_ref", "path": "/task/values.parquet", "format": "parquet",
            "columns": ("date", "code", "value"), "sort": ("date", "code"),
            "dtypes": {"value": "float64"}, "index": False},),
    "S7": ({"ref": "ledger_ref", "path": "/task/ledger.parquet", "format": "parquet",
            "columns": ("date", "cash", "mv", "total_assets", "r_gross", "r_net"),
            "sort": ("date",), "index": False},),
}


class FileContractError(RuntimeError):
    pass


def spec_for(stage: str, ref: str | None = None, *, specs=None) -> dict:
    got = specs if specs is not None else FILE_SPECS.get(stage, ())
    if not got:
        raise FileContractError(f"{stage} 没有产出文件契约")
    if ref is None:
        if len(got) != 1:
            raise FileContractError(f"{stage} 有 {len(got)} 个产出文件，必须指名 ref")
        return got[0]
    for f in got:
        if f["ref"] == ref:
            return f
    raise FileContractError(f"{stage} 没有 ref={ref!r} 的产出文件")


def write_contracted(df, spec: dict, out_dir) -> Path:
    """按契约把 `df` 写成规范形，返回落盘路径。**唯一的一份函数体。**

    列序、排序、索引、dtype 一条不许省 —— 少一条，两个同样正确的实现字节就不同，
    而字节摘要是被计分的量（N-44 的病灶）。
    """
    cols = list(spec["columns"])
    missing = [c for c in cols if c not in getattr(df, "columns", [])]
    if missing:
        raise FileContractError(
            f"产出文件缺列 {missing} —— 契约列是 {cols}，实得 {list(getattr(df, 'columns', []))}")
    out = df.reset_index(drop=True)[cols].copy()
    for c, dt in (spec.get("dtypes") or {}).items():
        out[c] = out[c].astype(dt)
    out = out.sort_values(list(spec["sort"])).reset_index(drop=True)
    p = Path(out_dir) / Path(spec["path"]).name
    p.parent.mkdir(parents=True, exist_ok=True)
    if spec["format"] == "parquet":
        out.to_parquet(p, index=bool(spec.get("index")))
    elif spec["format"] == "csv":
        kw = {"index": bool(spec.get("index")), "header": bool(spec.get("header", True))}
        if spec.get("float_format"):
            kw["float_format"] = spec["float_format"]
        p.write_bytes(out.to_csv(**kw).encode(spec.get("encoding", "utf-8")))
    else:
        raise FileContractError(f"未知格式 {spec['format']}")
    return p


def sha256_of(path) -> str:
    """`values_ref.sha256` / `panel_ref.sha256` 的口径：**文件字节**摘要。

    不是重新序列化后的摘要 —— 重新序列化会引入 pandas / pyarrow 版本差异，
    而契约要的是「你交出来的那个文件」的摘要。
    """
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_contracted(path, spec: dict):
    """按契约读回来。写端与读端共用同一份 spec —— 口径只有一处。"""
    import pandas as pd
    p = Path(path)
    df = pd.read_parquet(p) if spec["format"] == "parquet" else pd.read_csv(p)
    miss = [c for c in spec["columns"] if c not in df.columns]
    if miss:
        raise FileContractError(f"{p.name} 缺列 {miss} —— 与契约不符")
    return df[list(spec["columns"])]
