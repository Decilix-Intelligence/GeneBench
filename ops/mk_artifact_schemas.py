# -*- coding: utf-8 -*-
"""把 `reference/artifact_schema.json_schema()` 落盘到 ops/specs/artifact_schema/v<ver>/。

    $ENV -m ops.mk_artifact_schemas

**生成器是唯一来源**；`ops/test_artifact_schema.py` 断言落盘文件与生成器逐字一致（D-03）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from reference import artifact_schema as sch      # noqa: E402


def main() -> int:
    out = _REPO / "ops" / "specs" / "artifact_schema" / f"v{sch.SCHEMA_VERSION}"
    out.mkdir(parents=True, exist_ok=True)
    for stage in sch.STAGES:
        p = out / f"{stage}.json"
        p.write_text(json.dumps(sch.json_schema(stage), ensure_ascii=False, indent=2) + "\n",
                     encoding="utf-8")
        print(f"写出 {p.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
