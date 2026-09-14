"""N-42：benchmark 期网关不得持有 market.duckdb 的任何句柄（裁定 2026-09-04）。

**既是 N-42 的根治，也是冻结线的正确性要求**：backend 钉死 snapshot 时，
网关读的是 parquet 快照 —— 它根本不该碰湖。碰了不只是争锁，
更意味着一条「快照之外的数据通路」存在过。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                        # noqa: E402
from snapshots import lake                            # noqa: E402

CATALOG = "market.duckdb"


@pytest.mark.parametrize("sql,needs", [
    ("SELECT * FROM read_parquet(?)", False),
    ("SELECT a, b FROM read_parquet(?) WHERE d > ?", False),
    ("SELECT * FROM read_parquet(?) t WHERE t.a > 1", False),
    ("SELECT * FROM bars", True),
    ("SELECT * FROM read_parquet(?) JOIN tradability t ON 1=1", True),
    ("SELECT * FROM read_parquet(?) UNION SELECT * FROM bars", True),
    ("SELECT * FROM tradability", True),
])
def test_needs_catalog_predicate(sql, needs):
    """判据**保守**：只有确定不需要时才跳过 catalog。

    判错方向的代价不对称 —— 少开一次 = 查询失败并报错（响的）；
    多开一次 = 回到今天的争用（哑的）。所以宁可多开。
    第一版只查 `FROM`，**漏了 JOIN**（自测当场红）。
    """
    assert lake.needs_catalog(sql) is needs


def test_pure_parquet_query_opens_no_catalog(tmp_path):
    """行为层：纯 parquet 查询跑完，进程里不该多出 catalog 句柄。

    夹具用 pandas 写 parquet，**不自己 `duckdb.connect`** ——
    `test_lake_baseline.py` 有一条「除 lake.py 外全仓不得有第二处连接」，
    它当场抓到了我第一版（直连造夹具）。那条基线是对的：
    只读语义、重试、线程上限、fd 上限只在 lake.py 里被盯着，绕过就全丢了。
    """
    import pandas as pd
    pq = tmp_path / "t.parquet"
    pd.DataFrame({"a": [1]}).to_parquet(pq)
    before = _open_catalog_paths()
    df = lake.query("SELECT * FROM read_parquet(?)", [str(pq)])
    assert len(df) == 1
    assert _open_catalog_paths() == before, "纯 parquet 查询开了 catalog"


def _open_catalog_paths() -> set[str]:
    """本进程打开的 catalog 文件（用 /proc/self/fd，不依赖 lsof）。"""
    out = set()
    fd = Path("/proc/self/fd")
    if not fd.is_dir():
        return out
    for f in fd.iterdir():
        try:
            target = str(f.resolve())
        except OSError:
            continue
        if CATALOG in target:
            out.add(target)
    return out


@pytest.mark.skipif(shutil.which("lsof") is None, reason="没有 lsof")
def test_running_gateway_holds_no_catalog_handle():
    """**f01 上的实测断言**：常驻网关（backend=snapshot）不得持有 catalog 句柄。

    它同时守两件事：① N-42 的争用不会回来；
    ② benchmark 期确实没有「快照之外的数据通路」。
    """
    r = subprocess.run(["systemctl", "--user", "show", "genebench-gateway.service",
                        "-p", "MainPID", "--value"], capture_output=True, text=True)
    pid = (r.stdout or "").strip()
    if not pid or pid == "0":
        pytest.skip("网关没在跑")
    lsof = subprocess.run(["lsof", "-p", pid], capture_output=True, text=True)
    holding = [l for l in lsof.stdout.splitlines()
               if CATALOG in l and re.search(r"\s(REG|DIR)\s", l) and " mem " not in l]
    assert not holding, (
        "网关持有 market.duckdb 的句柄 —— backend 钉死 snapshot 时它读的是 parquet，"
        f"不该碰湖：\n  " + "\n  ".join(holding[:3]))
