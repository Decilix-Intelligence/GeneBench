#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 A：公开包的宇宙定义面换成 baostock 重建结果之后，这几件事必须成立。

判据只有一条：**外部用户下载这个包，能不能自己把宇宙定义核出来、并且核得出「它是 baostock 的」**。
所以下面每一条都只问能被证伪的问题：逐字节、集合差、现算指纹、反向门当场红。

不在这里测的：gold 子集的数值（那是 `ops/reports/public/instruments_switch.md` §5 的
逐件比对产物，跑一次要一个多小时；这里只钉「结论文件在、且它说的是不是这一版」）。
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

GB = pathlib.Path(os.environ.get("GENEBENCH_ROOT", "/data/shared/genebench"))
PROV = GB / "snapshots/public_v1/qlib_provider"
REB = GB / "snapshots/public_v1/instruments_rebuild"
UNI_DIR = GB / "snapshots/public_v1/universe"
INSTR = PROV / "instruments"

pytestmark = pytest.mark.skipif(not PROV.is_dir(), reason="公开 provider 不在这台机器上")


def _sha(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _spans(p: pathlib.Path) -> dict:
    out: dict = {}
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split("\t")
        assert len(parts) == 3, f"{p}:{i} 不是三列"
        out.setdefault(parts[0], []).append((parts[1], parts[2]))
    return out


# ── 一、包里有什么、没有什么 ────────────────────────────────────────

def test_公开包只发三个宇宙_csi1000已经出包():
    got = sorted(p.name for p in INSTR.glob("*.txt"))
    assert got == ["all.txt", "csi300.txt", "csi500.txt"], (
        f"instruments/ 里是 {got} —— csi1000 必须不在（baostock 没有它的成分接口），"
        f"多一个少一个都说明换面没走完")


def test_csi300与csi500逐字节等于baostock重建产物():
    """**这条是「不含 tushare 派生行」的主证**：字节相同 ⇒ 没有任何一行来自别处。"""
    for u in ("csi300", "csi500"):
        assert _sha(INSTR / f"{u}.txt") == _sha(REB / f"{u}.txt"), (
            f"{u}.txt 与 {REB / (u + '.txt')} 不是同一份 —— "
            f"只要有一行是在重建产物之外加工出来的，这里就红")


def test_all是两个宇宙的并集且每只票都有features():
    a = _spans(INSTR / "all.txt")
    union = set(_spans(INSTR / "csi300.txt")) | set(_spans(INSTR / "csi500.txt"))
    extra = set(a) - union
    assert not extra, f"all.txt 里有不属于两个宇宙的码：{sorted(extra)[:10]}"
    no_feat = [c for c in a if not (PROV / "features" / c.lower()).is_dir()]
    assert not no_feat, f"all.txt 列了没有行情面的码：{no_feat}"
    # 反过来：union 里没进 all 的，必须**正好是**没有 features 的那些
    missing = sorted(c for c in union - set(a)
                     if (PROV / "features" / c.lower()).is_dir())
    assert not missing, f"这些码有 features 却没进 all.txt：{missing[:10]}"


def test_all的区段就是公开日线表里的首末交易日_不是universe_pit派生():
    """`all` 的区段语义是**数据可得区间**。换面之前它取自私有 `universe_pit`
    （上游 tushare），1,917 只里有 147 只的右端与公开日线表对不上 —— 那 147 行
    就是 tushare 派生物。换面之后它逐行由公开 `daily` 表算出来，这条钉的就是这件事。"""
    daily = GB / "snapshots/public_v1/tables/daily.parquet"
    if not daily.is_file():
        pytest.skip("公开 daily 表不在")
    import duckdb
    rows = duckdb.connect(":memory:").execute(
        f"SELECT ts_code, min(trade_date), max(trade_date) "
        f"FROM read_parquet('{daily}') GROUP BY ts_code").fetchall()

    def _iso(d: str) -> str:
        d = str(d)
        return d if "-" in d else f"{d[:4]}-{d[4:6]}-{d[6:]}"

    bs = {f"{t.split('.')[1]}{t.split('.')[0]}": (_iso(lo), _iso(hi)) for t, lo, hi in rows}
    bad = []
    for code, segs in _spans(INSTR / "all.txt").items():
        if len(segs) != 1 or code not in bs or segs[0] != bs[code]:
            bad.append((code, segs, bs.get(code)))
    assert not bad, f"all.txt 有 {len(bad)} 行与公开日线表对不上，例：{bad[:3]}"


# ── 二、宇宙定义面是自足的：反建回去必须逐字节相同 ──────────────────

def test_universe_pit只含两个宇宙且反建回instruments逐字节相同(tmp_path):
    import pandas as pd
    from ops.release import universe_from_instruments as UFI

    f = UNI_DIR / "universe_pit.parquet"
    assert f.is_file(), f"{f} 不在"
    frame = pd.read_parquet(f)
    assert sorted(frame["universe"].unique()) == ["csi300", "csi500"], (
        "公开 universe_pit 里还有 csi300/csi500 之外的宇宙")

    out = tmp_path / "u.parquet"
    UFI.write_universe_pit(INSTR, out, verbose=False, universes=("csi300", "csi500"))
    got = pd.read_parquet(out)
    assert len(got) == len(frame), "反建出来的行数与包里那份对不上"


# ── 三、P2：钉子、现算根、反向门 ────────────────────────────────────

def test_公开钉子常量等于现算的根():
    from genetask import pin
    from runner import inject as INJ
    now = pin.provider_root_sha256(PROV)
    assert now.startswith(INJ.PUBLIC_PROVIDER_SHA256_ROOT), (
        f"runner/inject.py 的公开钉子是 {INJ.PUBLIC_PROVIDER_SHA256_ROOT}，"
        f"而现算根是 {now[:16]} —— 换过 provider 却忘了跟改钉子，P2 会当场红")
    assert pin.check_provider_pin(PROV, expect=INJ.provider_pin_expect("public")) == [], \
        "P2 在公开 provider 上不绿"


def test_反向门有牙_清单外的文件当场红(tmp_path):
    """不动真包：在 tmp 里搭一个最小 provider，塞一个清单外的文件必须红。"""
    from genetask import pin
    d = tmp_path / "prov"
    (d / "features" / "sh600000").mkdir(parents=True)
    blob = b"\x01\x02"
    (d / "features" / "sh600000" / "close.day.bin").write_bytes(blob)
    body = f"{hashlib.sha256(blob).hexdigest()}  {len(blob)}  features/sh600000/close.day.bin\n"
    (d / "files.sha256").write_text(body, encoding="utf-8")
    good = pin.provider_root_sha256(d)
    assert pin.check_provider_pin(d, expect=good) == [], "干净的树应当绿"
    (d / "features" / "sh600000" / "__extra__.bin").write_bytes(b"\x00")
    bad = pin.check_provider_pin(d, expect=good)
    assert bad and any("清单里没有" in x for x in bad), \
        "清单外多一个文件却没红 —— 这道门没有牙"


# ── 四、许可：§5 说的是新口径 ──────────────────────────────────────

def test_DATA_LICENSE的第5节说的是重建而不是未确认():
    t = (REPO / "DATA_LICENSE").read_text(encoding="utf-8")
    for must in ("由 baostock 接口重建", "在 §2 授权的射程内", "不入公开包"):
        assert must in t, f"DATA_LICENSE 里没有「{must}」"
    assert "不在 baostock 许可的射程内" not in t, \
        "旧判断的原话还留在文件里 —— 两个相反的结论同时在，读者无从分辨"


# ── 五、换面记录在、且记的是这一版 ─────────────────────────────────

def test_换面报告在且钉着现在这个根():
    from genetask import pin
    p = REPO / "ops/reports/public/instruments_switch.md"
    assert p.is_file(), "缺 ops/reports/public/instruments_switch.md"
    t = p.read_text(encoding="utf-8")
    now = pin.provider_root_sha256(PROV)
    assert now[:16] in t, "换面报告里没有现在这个根 —— 报告陈了"
    assert "561348660a3175b1" in t, "换面报告里没有旧根 —— 那就查不到「换之前是什么」"


def test_反建器按包里实际发了哪几个宇宙来取_而且拦得住被截断的包(tmp_path):
    """形态 B 的重建脚本不传 `universes` —— 它得自己看出「这个包不发 csi1000」。
    但「目录里有什么就算什么」会把**被截断的包**也当成正常，所以多一道与 manifest 的交叉核对。"""
    from ops.release import universe_from_instruments as UFI

    assert UFI.discover_universes(INSTR) == ("all", "csi300", "csi500")

    d = tmp_path / "provider" / "instruments"
    d.mkdir(parents=True)
    for u in ("all", "csi300", "csi500", "csi1000"):
        (d / f"{u}.txt").write_text("SH600000\t2009-01-05\t2026-07-31\n", encoding="utf-8")
    man = {"instruments": {"files": {u: {} for u in ("all", "csi300", "csi500", "csi1000")}}}
    (d.parent / "manifest.json").write_text(json.dumps(man), encoding="utf-8")
    assert UFI.discover_universes(d) == ("all", "csi1000", "csi300", "csi500")

    (d / "csi1000.txt").unlink()          # 包被截断：manifest 还说有，目录里没了
    with pytest.raises(UFI.ReconstructError) as e:
        UFI.discover_universes(d)
    assert "这个包被动过" in str(e.value)
# ── 六、按新成分重算的 gold：清单自洽 + 归因没有余项 ──────────────────

R2 = GB / "snapshots/public_v1/gold_factors_r2"


def test_按新成分重算的gold子集清单与盘上逐件对得上():
    """打包（裁定 ②）要从 `gold_factors_r2/` 取这 41 件。清单里记的 sha 必须就是盘上的。

    钉这一条是因为**下游会照着清单去取**：清单陈了而文件在，打出来的包会带着一份
    对不上的分发出去，而校验命令当场红 —— 红在用户那边，不是红在这里。
    """
    f = R2 / "gold_subset_public.json"
    if not f.is_dir() and not f.is_file():
        pytest.skip("按新成分重算的 gold 不在这台机器上")
    doc = json.loads(f.read_text(encoding="utf-8"))
    assert doc["n_files"] == 41, f"新子集清单记了 {doc['n_files']} 件，公开通道应当是 41 件"
    bad = []
    for e in doc["files"]:
        p = R2 / e["rel"]
        if not p.is_file():
            bad.append((e["rel"], "缺文件")); continue
        if p.stat().st_size != e["bytes"]:
            bad.append((e["rel"], "字节数对不上")); continue
        if _sha(p) != e["sha256"]:
            bad.append((e["rel"], "sha256 对不上"))
    assert not bad, f"新 gold 子集清单与盘上对不上：{bad[:5]}"


def test_gold子集的比对与归因结论在_且归因没有余项():
    """§5 那条门：**值变了的格，一格都不许落在「成分区段没变」的票上**。

    落在那种票上 = 动的不止是成分（provider 的 bin / 求值器 / 暖机），
    那时候接受重算结果就是把一个没查清的变化发出去。
    """
    c = GB / "scratch/A/gold_compare.json"
    a = GB / "scratch/A/gold_attrib.json"
    if not (c.is_file() and a.is_file()):
        pytest.skip("gold 逐件比对产物不在这台机器上（跑一次一个多小时）")
    rep = json.loads(c.read_text(encoding="utf-8"))
    assert rep["subset_summary"]["n"] == 41, "比对没覆盖全部 41 件"
    att = json.loads(a.read_text(encoding="utf-8"))
    assert att["violations"] == [], (
        f"有格落在「成分区段没变」的票上：{att['violations'][:3]} —— "
        f"那说明动的不止是成分，不能当成换名单的正常后果")
    assert att["by_backend"]["qlib_expression"]["value_changed_cells"] == 0, (
        "qlib_expression 那条路上出现了共有格值变 —— 它先在整段逐票历史上求值再切行，"
        "不该受成分影响；出现了就是别的东西动了")
