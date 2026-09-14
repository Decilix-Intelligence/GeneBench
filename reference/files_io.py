"""数据面（gold 侧）的薄封装：从**冻结件**取契约，调**唯一的那份**写入函数体。

写入函数体在 `genetask/file_contract.py` —— 它必须是零 `reference` 依赖的，
因为执行面的适配器也要调它，而执行面不得 import `reference/`（T11）。
把函数体放这里，执行面就只能自己再抄一份，那正是 §9「与 gold 同一函数体」要防的事。
"""
from __future__ import annotations

from pathlib import Path

from genetask.file_contract import (FileContractError, read_contracted,  # noqa: F401
                                    sha256_of, write_contracted as _write)
from reference.artifact_schema import payload_files


def spec_for(stage: str, ref: str | None = None, profile: str | None = None) -> dict:
    from genetask.file_contract import spec_for as _spec
    return _spec(stage, ref, specs=payload_files(stage, profile))


def write_contracted(df, stage: str, out_dir, *, ref: str | None = None,
                     profile: str | None = None):
    """gold 侧入口。spec 取自**冻结件**，不取执行面的那份镜像。

    写完**收紧到 0600**（红线 5）。收紧放在这一层而不是 `file_contract.write_contracted`：
    那个函数体执行面的适配器也在调，且被要求零 `reference` 依赖 ——
    在共享体里改权限会连带改掉执行面的产物属性。gold 是答案面，收紧只该发生在 gold 这一侧。
    """
    out = _write(df, spec_for(stage, ref, profile), out_dir)
    try:
        Path(out).chmod(0o600)
    except OSError:
        pass
    return out
