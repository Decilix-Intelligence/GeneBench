#!/usr/bin/env python3
"""卡 H：签字包**按通道各出一份** + 发布清单终核。

这份测试的对象是两件事：
① `ops/archive_signoff.py` 的通道划分**真的把两条通道分开了**（不是加了个参数、
   两份包内容一样）；
② `RELEASE_MANIFEST.json` 的五条 blocker 全闭、`releasable=true`、`--check` 退 0。

判据里有两条**反向判别**（`test_通道纯度的判据不是恒绿` / `test_共有件相同这条判据不是恒绿`）：
没有它们，「两份包互不越界」「共有件逐字节相同」这两条在任何实现下都会绿。
"""
from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from ops import archive_signoff as AS                        # noqa: E402

PY = sys.executable


def _pkg(channel: str) -> tuple[Path, dict]:
    sv, _sr, rv, _rr = AS._axes(channel)
    d = AS.ARCHIVE / AS.dir_name_for(channel, sv, rv)
    assert d.is_dir(), f"{channel} 通道的签字包不在：{d} —— 跑 `$PY ops/archive_signoff.py --channel both --force`"
    return d, json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))


# ============================================================ 1. 清单的通道划分

def test_三组清单互不相交_并起来恰好是ITEMS():
    """并集不变（`ops/test_V2.py` / `test_wrapup.py` / `test_V2rt.py` 问的是并集），
    但三组之间不许有一件同时属于两组 —— 同时属于就意味着它会被签进两份包里，
    而那正是「共有件」该走的路（`SHARED_ITEMS`），不是私有/公开件该走的路。"""
    s, p, q = set(AS.SHARED_ITEMS), set(AS.PRIVATE_ITEMS), set(AS.PUBLIC_ITEMS)
    assert not (s & p) and not (s & q) and not (p & q), "三组清单有重叠"
    assert s | p | q == set(AS.ITEMS), "三组并起来 ≠ ITEMS"
    assert len(AS.ITEMS) == len(set(AS.ITEMS)), "ITEMS 里有重复项"


def test_items_for_只给本通道的件():
    assert set(AS.items_for("private")) == set(AS.SHARED_ITEMS) | set(AS.PRIVATE_ITEMS)
    assert set(AS.items_for("public")) == set(AS.SHARED_ITEMS) | set(AS.PUBLIC_ITEMS)
    with pytest.raises(KeyError):
        AS.items_for("both")            # `both` 是命令行的开关，不是一条通道


def test_私有包沿用历史目录名_公开包一眼看得出通道():
    """`ops/test_wrapup.py` / `ops/test_V2.py` / `ops/test_V2rt.py` 三处都按
    `v{set_version}_{reference_version}` **现算**私有包的路径。改名 = 三处一起红，
    而它们问的「当前轴上有没有签过字的包」不该因为命名体例变了就没了答案。"""
    assert AS.dir_name_for("private", "1.0.16", "r1.0.23") == "v1.0.16_r1.0.23"
    name = AS.dir_name_for("public", "p1.0.0", "r1.0.23")
    assert name == "public_vp1.0.0_r1.0.23"
    assert "public" in name and "p1.0.0" in name, "公开包的名字里看不出通道或轴"


def test_发布表清单按通道劈开_并集不变():
    assert set(AS.RELEASE_TABLES) == set(AS.release_tables_for("private")) | set(AS.release_tables_for("public"))
    assert set(AS.DIAGNOSTIC_TABLES) == set(AS.diagnostic_tables_for("private")) | set(AS.diagnostic_tables_for("public"))
    for t in AS.release_tables_for("private"):
        assert t.startswith("m6_all/"), f"私有通道的发布表里混进了 {t}"
    for t in AS.release_tables_for("public"):
        assert t.startswith("m6_public/"), f"公开通道的发布表里混进了 {t}"


def test_诊断表一张都不在任何一份包的发布表清单里():
    """⑥-b/⑪：`table_a` / `table_b` 带 `effect` 等归一列，**不进发布表**。归档照旧。"""
    for ch in AS.CHANNELS:
        rel = set(AS.release_tables_for(ch))
        assert not (rel & set(AS.DIAGNOSTIC_TABLES)), f"{ch} 的发布表清单里有诊断表"
        _d, m = _pkg(ch)
        assert not (set(m["tables"]["release"]) & set(AS.DIAGNOSTIC_TABLES))
        # 但诊断表仍然**归档**（留证据）
        assert set(AS.diagnostic_tables_for(ch)) <= set(m["files"]), \
            f"{ch} 的包里没有诊断表 —— 归档是留证据，不是不收"


# ============================================================ 2. 两份包落盘之后

@pytest.mark.parametrize("channel", AS.CHANNELS)
def test_包在_轴对_通道对(channel):
    d, m = _pkg(channel)
    sv, sr, rv, rr = AS._axes(channel)
    assert m["channel"] == channel
    assert (m["set_version"], m["set_root"]) == (sv, sr)
    assert (m["reference_version"], m["reference_root"]) == (rv, rr)
    assert len(m["set_root"]) == 64 and len(m["reference_root"]) == 64
    assert d.name == AS.dir_name_for(channel, sv, rv)


@pytest.mark.parametrize("channel", AS.CHANNELS)
def test_逐件sha256对得上_且都是0400(channel):
    d, m = _pkg(channel)
    assert m["files"], "一个文件都没归档"
    for rel, sha in m["files"].items():
        p = d / AS._dst_name(rel)
        assert p.is_file(), f"{rel} 在 MANIFEST 里但盘上没有"
        assert hashlib.sha256(p.read_bytes()).hexdigest() == sha, f"{rel} 的 sha 对不上"
        assert stat.S_IMODE(p.stat().st_mode) == 0o400, f"{rel} 不是 0400"
    for extra in ("MANIFEST.json", "README.md"):
        assert stat.S_IMODE((d / extra).stat().st_mode) == 0o400, f"{extra} 不是 0400"


@pytest.mark.parametrize("channel", AS.CHANNELS)
def test_归档件加缺件恰好等于本通道清单_且这一版没有缺件(channel):
    d, m = _pkg(channel)
    declared = set(AS.items_for(channel)) | set(AS.ROOT_ITEMS)
    assert set(m["files"]) | set(m["declared_but_missing"]) == declared, \
        "归档件 + 缺件 ≠ 本通道清单 —— 有件被静默跳过了"
    assert m["declared_but_missing"] == [], f"{channel} 有缺件：{m['declared_but_missing']}"
    known = {AS._dst_name(r) for r in m["files"]} | {"MANIFEST.json", "README.md"}
    assert not [p.name for p in d.iterdir() if p.name not in known], "包里有 MANIFEST 没记的文件"


@pytest.mark.parametrize("channel", AS.CHANNELS)
def test_同名冲突断言还在_且本通道没有同名(channel):
    src = (_REPO / "ops" / "archive_signoff.py").read_text(encoding="utf-8")
    assert "归档文件名冲突" in src, "同名冲突断言被删了 —— 归档目录是平的，没有它就会静默覆盖"
    names = [AS._dst_name(r) for r in (*AS.items_for(channel), *AS.ROOT_ITEMS)]
    assert len(names) == len(set(names)), "本通道清单里有两件会落成同一个文件名"


def _off_channel(channel: str, files) -> list[str]:
    """这份包里有几件**不属于**本通道。判据只有一句，所以下面配了反向判别。"""
    other = set(AS.PUBLIC_ITEMS if channel == "private" else AS.PRIVATE_ITEMS)
    return sorted(set(files) & other)


def test_通道纯度_两份包互不越界():
    for ch in AS.CHANNELS:
        _d, m = _pkg(ch)
        assert not _off_channel(ch, m["files"]), \
            f"{ch} 的包里有另一条通道的件：{_off_channel(ch, m['files'])}"


def test_通道纯度的判据不是恒绿():
    """把公开通道的一件塞进私有包的文件表，`_off_channel` 必须当场点名。"""
    fake = dict.fromkeys(AS.items_for("private"), "")
    fake["m6_public/table_main.csv"] = ""
    assert _off_channel("private", fake) == ["m6_public/table_main.csv"]


def test_共有件在两份包里逐字节相同():
    _dp, mp = _pkg("private")
    _dq, mq = _pkg("public")
    shared = set(AS.SHARED_ITEMS) | set(AS.ROOT_ITEMS)
    assert shared <= set(mp["files"]) and shared <= set(mq["files"]), "共有件没有两份都收"
    diff = [r for r in sorted(shared) if mp["files"][r] != mq["files"][r]]
    assert not diff, f"共有件两份包里不一样：{diff} —— 两份包不是同一时刻出的"
    assert mp["git_head"] == mq["git_head"], "两份包的 HEAD 不同"


def test_共有件相同这条判据不是恒绿():
    """同一件在两份包里 sha 不同时必须被点名 —— 否则上一条在任何实现下都绿。"""
    a = {"known_limits_v1.md": "aa", "VERSIONS.md": "bb"}
    b = {"known_limits_v1.md": "aa", "VERSIONS.md": "cc"}
    assert [r for r in sorted(a) if a[r] != b[r]] == ["VERSIONS.md"]


def test_两份包互指得到():
    dp, mp = _pkg("private")
    dq, mq = _pkg("public")
    assert mp["counterpart"] == dq.name and mq["counterpart"] == dp.name
    for d, m in ((dp, mp), (dq, mq)):
        rd = (d / "README.md").read_text(encoding="utf-8")
        assert f"通道 `{m['channel']}`" in rd, "README 里没写通道"
        assert m["counterpart"] in rd, "README 没指向另一份包 —— 读包的人不知道还有一份"


def test_两份包合起来恰好是并集清单():
    _dp, mp = _pkg("private")
    _dq, mq = _pkg("public")
    assert set(mp["files"]) | set(mq["files"]) == set(AS.ITEMS) | set(AS.ROOT_ITEMS), \
        "两份包合起来 ≠ 并集清单 —— 有件谁都没收"


def test_公开包里没有私有批的表():
    """最直白的那条：公开包里不许出现 `m6_all__*`（私有批的数），反之亦然。"""
    dq, _mq = _pkg("public")
    assert not [p.name for p in dq.iterdir() if p.name.startswith("m6_all__")]
    dp, _mp = _pkg("private")
    assert not [p.name for p in dp.iterdir() if p.name.startswith("m6_public__")]


# ============================================================ 3. 发布清单终核

def _rm() -> dict:
    return json.loads((_REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))


def test_五条blocker全部satisfied_且releasable为真():
    rm = _rm()
    open_ = [b["id"] for b in rm["blockers"] if not b.get("satisfied")]
    assert not open_, f"还有未闭合的 blocker：{open_}"
    assert len(rm["blockers"]) == 5, f"blocker 条数变了：{len(rm['blockers'])}"
    assert rm["missing"] == [], f"发布件缺件：{rm['missing']}"
    assert rm["releasable"] is True


def test_每条blocker都留了证据路径_且路径真的存在():
    for b in _rm()["blockers"]:
        ev = b.get("evidence") or []
        assert ev, f"{b['id']} 没有证据路径"
        for rel in ev:
            assert (_REPO / rel).exists(), f"{b['id']} 的证据 {rel} 不在盘上"


def test_发布清单的check退0():
    r = subprocess.run([PY, "ops/mk_release_manifest.py", "--check"],
                       cwd=str(_REPO), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"--check 退 {r.returncode}\n{r.stdout}\n{r.stderr}"


def test_两条通道的轴都在发布清单里_且与两份签字包一致():
    axes = _rm()["axes"]
    _dp, mp = _pkg("private")
    _dq, mq = _pkg("public")
    assert (mp["set_version"], mp["set_root"]) == (axes["set_version"], axes["set_root"])
    assert (mq["set_version"], mq["set_root"]) == (axes["public_set_version"], axes["public_set_root"])
    for m in (mp, mq):
        assert (m["reference_version"], m["reference_root"]) == \
            (axes["reference_version"], axes["reference_root"])


def test_各批主表的表头都是换列之后的口径():
    """⑥-c：S2 的保真列由 `Align` 换成 `CellAgree`（表头 `Cell%`）。
    落盘的表不重出的话，签字包里签的就是旧口径那张。"""
    stale = []
    for f in sorted((_REPO / "ops" / "reports").glob("*/table_main.csv")):
        head = f.read_text(encoding="utf-8").splitlines()[0]
        if "Cell" not in head:
            stale.append(str(f.relative_to(_REPO)))
    assert not stale, f"这些批的主表还是旧表头：{stale}"
