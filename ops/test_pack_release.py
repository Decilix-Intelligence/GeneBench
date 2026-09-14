#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 C（裁定 ②）：两个发布附件的打包、确定性、与 `RELEASE_MANIFEST` 的登记。

这张卡要对外承诺三件事，每一件在这里都有一条**能被证伪**的门：

* **包里是换面之后的宇宙定义面** —— `provider/instruments/` 逐字节等于 baostock 重建
  产物、没有 `csi1000`；`universe/` 带上卡 A 反投影出来的 PIT 名单。
  反面：哪天有人把旧 `instruments/` 换回去，`test_包里的宇宙定义面…` 当场红。
* **gold 子集取自 `gold_factors_r2/`，逐件与清单一致** —— 反面：把源根指回旧
  `gold_factors/`，`GS.collect()` 必须抛（那 41 件的 sha 在旧树上已经全部不成立）。
* **连打两次逐字节相同** —— 在一棵小树上真打两遍比字节；并验判别力：
  **不给** `--built-at` 的两次**必须不同**（否则「确定性」这条测试是恒绿的）。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import genebench_config as cfg                          # noqa: E402
from ops import mk_release_manifest as MR               # noqa: E402
from ops.release import pack_gold_subset as GS          # noqa: E402
from ops.release import pack_public_provider as PP      # noqa: E402

GB = cfg.GENEBENCH_ROOT
PUB = GB / "snapshots" / cfg.PUBLIC_VERSION
REBUILD = PUB / "instruments_rebuild"
R2 = PUB / GS.SUBSET_ROOT_NAME


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _need(p: pathlib.Path):
    if not p.exists():
        pytest.skip(f"本机没有 {p}（只有数据面那台有）")


def _need_packager_inputs():
    """`PP.collect()` 的**全部必需输入**都在位才往下走（N-819，2026-09-13）。

    为什么不是「再补一条 `scratch/v1_union.txt`」：那正是这条坑的形状。
    原先的守卫只 `_need()` **落位产物**（`snapshots/public_v1/qlib_provider`、
    `universe/universe_pit.parquet`）—— 外部用户按 README §2.1a 把三件附件落位之后
    守卫**全部放行**，接着去调打包器，而打包器第一件要的是**打包前的发布方中间件**
    `$GENEBENCH_ROOT/scratch/v1_union.txt`：它既不在仓库里、也不在三件附件里
    （附件里那一份落在 `snapshots/public_v1/universe/v1_union.txt`，**路径不同**）。
    于是**落位前 skip、落位后 3 failed** —— 越照文档做对，越会看到红
    （2026-09-13 卡 Tfin 在全新外部 clone 上实测）。

    判据**从 `PP.components()` 现算**，不写死一张清单：组件加一件、源路径搬一次，
    写死的那张清单就又变回「落位之后反而红」。外部用户本来就不该重打 provider 包
    —— 那是发布方的操作，所以这里 `skip` 是对的落点；**发布方机器上这些输入全在**，
    三条照常真跑（判别力不变，见 `ops/test_U.py::test_打包器守卫在发布方机器上一条都不skip`）。
    """
    for comp in PP.components():
        if not comp.get("required"):
            continue
        kind, src = comp["kind"], pathlib.Path(comp["src"])
        if kind in ("dir", "file"):
            _need(src)
        elif kind == "pairs":
            for _arc, p in comp["pairs"]:
                _need(pathlib.Path(p))
        elif kind == "listed":
            for rel in comp["items"]:
                _need(src / rel)


# ================================================================== 1. 落点

def test_许可现值决定落点_granted时落可发布路径():
    """落点是**读出来的**，不是写死的：`DATA_LICENSE` 现在是 granted → 可发布路径。"""
    state = PP.read_license_state(REPO)
    assert state == "granted", f"DATA_LICENSE 现值是 {state} —— 本卡的前提变了，停下来看"
    assert PP.dest_for(state) == PP.published_dir()
    assert PP.dest_for("pending_license_text") == PP.staging_dir()
    assert GS.dest_default() == PP.published_dir()


def test_许可没到位时两个脚本都拒绝往可发布路径写(tmp_path):
    """判别力：把许可翻回 pending，两个脚本都必须拒绝 —— 不是只有形态 A 有这道门。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "DATA_LICENSE").write_text("**状态：`pending_license_text`**\n", encoding="utf-8")
    assert PP.read_license_state(repo) == "pending_license_text"
    with pytest.raises(PP.PackageError):
        PP.pack(gb_root=tmp_path / "gb", repo=repo, dest=PP.published_dir(tmp_path / "gb"),
                tar=False, verbose=False)
    with pytest.raises(GS.GoldPackError):
        GS.pack(gb_root=tmp_path / "gb", repo=repo, dest=PP.published_dir(tmp_path / "gb"),
                tar=False, verbose=False)


@pytest.mark.parametrize("bad", ["scratch/f02_bundle", "scratch/f02_bundle/x", "staging"])
def test_gold包拒绝落到会同步上执行面的路径(bad):
    """红线 2 的落点判据：gold 是答案面，发布目录可以，执行面的暂存区不行。"""
    with pytest.raises(GS.GoldPackError):
        GS.assert_dest_is_not_on_the_exec_plane(GB / bad)
    GS.assert_dest_is_not_on_the_exec_plane(PP.published_dir())      # 发布目录本身是允许的


# ================================================================== 2. 宇宙定义面

def test_包里的宇宙定义面是baostock重建的_没有csi1000():
    _need(PUB / "qlib_provider" / "instruments")
    _need_packager_inputs()
    entries = {e.arcname: e for e in PP.collect()[0]}
    inst = sorted(k for k in entries if k.startswith("provider/instruments/"))
    assert inst == ["provider/instruments/all.txt",
                    "provider/instruments/csi300.txt",
                    "provider/instruments/csi500.txt"], inst
    assert not [k for k in entries if "csi1000" in k], "csi1000 不入公开包（裁定 ①）"
    for uni in ("csi300", "csi500"):
        src = REBUILD / f"{uni}.txt"
        _need(src)
        assert entries[f"provider/instruments/{uni}.txt"].sha256 == _sha(src), (
            f"{uni}.txt 与 baostock 重建产物不再逐字节相同 —— "
            f"有人把旧 instruments 换回来了，或重建产物动了")


def test_包里的universe带上了卡A反投影的PIT名单():
    _need(PUB / "universe" / "universe_pit.parquet")
    _need_packager_inputs()
    names = {e.arcname for e in PP.collect()[0]}
    for want in ("universe/universe_pit.parquet", "universe/build_info.json",
                 "universe/MANIFEST.sha256"):
        assert want in names, f"{want} 不在包里 —— 宇宙定义面没进包（裁定 ①）"
    # 取数名单仍在，且**在 what 里被说清是取数名单不是宇宙定义**
    assert "universe/v1_union.txt" in names
    comp = next(c for c in PP.components() if c["prefix"] == "universe")
    assert "取数名单" in comp["what"] and "宇宙定义面" in comp["what"]
    bi = json.loads((PUB / "universe" / "build_info.json").read_text(encoding="utf-8"))
    assert set(bi["universes"]) == {"csi300", "csi500"}, bi["universes"]


def test_manifest的宇宙说明不再说它是tushare派生的():
    """旧文本写着「来自私有 universe_pit（tushare 派生）…发布前须单独确认」——
    换面之后那句话是**假的**。这条盯着它不许复活。"""
    _need(PUB / "qlib_provider")
    _need_packager_inputs()
    entries, missing = PP.collect()
    man = PP.build_manifest(entries, missing, state="granted", gb_root=None, repo=REPO,
                            dest=PP.published_dir(), built_at="2026-01-01T00:00:00+00:00")
    note = man["data_source"]["universe_definition_note"]
    assert "tushare index_member_all 派生" not in note
    assert "baostock" in note and "csi1000" in note


# ================================================================== 3. gold 子集

def test_gold子集从r2取_逐件与清单一致():
    _need(R2 / GS.SUBSET_LIST_NAME)
    entries, sub = GS.collect(R2, REPO)
    gold = [e for e in entries if e.arcname.startswith(GS.GOLD_PREFIX + "/")]
    assert len(gold) == sub["n_files"] == 41, (len(gold), sub.get("n_files"))
    assert sub["computed_on_instruments"].startswith("baostock")
    assert not [e for e in gold if "csi1000" in e.arcname]
    by_rel = {e.arcname.split("/", 1)[1]: e.sha256 for e in gold}
    assert all(by_rel[f["rel"]] == f["sha256"] for f in sub["files"])


def test_拿旧gold当源根必须当场红(tmp_path):
    """**判别力**：旧 `gold_factors/` 是换面之前的产物，那 41 件的 sha 已经全部不成立。
    照它打出去的包，用户按 README 校验就是红 —— 所以这里必须抛，不许静默重算。

    构造：把 r2 的清单原样搬到一个**指向旧树**的源根 —— 文件都在、路径都对，
    只有逐件 sha 对不上。抛的必须是「对不上」，不是「找不到」。
    """
    old = PUB / "gold_factors"
    _need(old / "csi300")
    _need(R2 / GS.SUBSET_LIST_NAME)
    fake = tmp_path / "old_root"
    fake.mkdir()
    (fake / GS.SUBSET_LIST_NAME).write_bytes((R2 / GS.SUBSET_LIST_NAME).read_bytes())
    for sub in ("csi300", "csi500"):
        (fake / sub).symlink_to(old / sub)
    with pytest.raises(GS.GoldPackError) as exc:
        GS.collect(fake, REPO)
    assert "对不上" in str(exc.value), str(exc.value)[:200]


def test_gold包只从公开快照取_不碰私有树():
    _need(R2 / GS.SUBSET_LIST_NAME)
    entries, _ = GS.collect(R2, REPO)
    priv = (GB / "snapshots" / "v1").resolve()
    for e in entries:
        assert priv not in e.src.resolve().parents, f"{e.arcname} 来自私有树 {e.src}"


# ================================================================== 4. 确定性

@pytest.fixture()
def small_tree(tmp_path):
    """一棵**能真打两个包**的小树。形态 A 的物料清单照 `PP.components()` 摆齐。"""
    from snapshots.public import manifest as PM
    gb, repo = tmp_path / "gb", tmp_path / "repo"
    pub = gb / "snapshots" / cfg.PUBLIC_VERSION

    def w(p: pathlib.Path, text: str) -> pathlib.Path:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    prov = pub / "qlib_provider"
    w(prov / "calendars" / "day.txt", "2009-01-05\n")
    for uni in ("csi300", "csi500", "all"):
        w(prov / "instruments" / f"{uni}.txt", "SH600000\t2009-01-05\t2026-07-31\n")
    (prov / "features" / "SH600000").mkdir(parents=True)
    (prov / "features" / "SH600000" / "close.day.bin").write_bytes(b"\x01\x02" * 8)
    w(prov / "files.sha256", "dead  features/SH600000/close.day.bin\n")
    w(prov / "manifest.json", "{}")
    w(pub / "tradability" / "year=2026" / "p.parquet", "t")
    for t in ("daily", "adj_factor", "stk_limit", "suspend_d", "trade_cal", "stock_basic"):
        w(pub / "tables" / f"{t}.parquet", t)
    w(gb / "scratch" / "v1_union.txt", "SH600000\n")
    w(pub / "universe" / "universe_pit.parquet", "u")
    w(pub / "universe" / "build_info.json", "{}")
    w(pub / "universe" / "MANIFEST.sha256", "cafe  universe_pit.parquet\n")

    w(repo / "DATA_LICENSE", "**状态：`granted`**\n")
    w(repo / "ops" / "data_cards" / "public_channel.md", "# 卡\n")
    w(repo / "ops" / "data_cards" / "gold_subset_v1.md", "# 子集卡\n")
    w(repo / "ops" / "reports" / "public" / "data_channel_notes.md", "# 记录\n")
    w(repo / "ops" / "reports" / "public" / "qlib_provider_public.md", "# provider\n")
    w(repo / "ops" / "reports" / "public" / "instruments_switch.md", "# 换面\n")
    for rel in PM.PUBLIC_FROZEN_ARTIFACTS:
        if rel.startswith("reference/"):
            w(repo / rel, f"# {rel}\n")
    for rel in ("build_public_provider.sh", "fetch_public_quotes.py",
                "universe_from_instruments.py", "rebuild_public_provider.py",
                "pack_public_provider.py"):
        w(repo / "ops" / "release" / rel, f"# {rel}\n")
    for name in ("v1.0-smoke.json", "v1.0-smoke-public.json", "v1.0-smoke.reference.json"):
        w(repo / "ops" / "manifests" / name, (REPO / "ops" / "manifests" / name)
          .read_text(encoding="utf-8"))

    # gold 子集的小源根：两件假 parquet + 逐件清单
    r2 = pub / GS.SUBSET_ROOT_NAME
    files = []
    for rel, body in (("csi300/f.001.parquet", b"aaa"), ("csi500/f.002.parquet", b"bbbb")):
        p = r2 / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
        files.append({"rel": rel, "bytes": len(body),
                      "sha256": hashlib.sha256(body).hexdigest()})
    w(r2 / GS.SUBSET_LIST_NAME, json.dumps(
        {"n_files": len(files), "computed_on_instruments": "baostock（夹具）",
         "provider_files_sha256_digest": "0" * 64, "files": files}, ensure_ascii=False))
    return gb, repo, r2


def _pack_both(gb, repo, r2, dest, built_at):
    a = PP.pack(gb_root=gb, repo=repo, dest=dest, tar=True, verbose=False, built_at=built_at)
    b = GS.pack(gb_root=gb, repo=repo, source_root=r2, dest=dest, tar=True, verbose=False,
                built_at=built_at)
    return a, b


def test_同一棵树同一个built_at连打两次逐字节相同(small_tree, tmp_path):
    gb, repo, r2 = small_tree
    at = "2026-09-12T00:00:00+00:00"
    d1, d2 = tmp_path / "d1", tmp_path / "d2"
    a1, g1 = _pack_both(gb, repo, r2, d1, at)
    a2, g2 = _pack_both(gb, repo, r2, d2, at)
    assert a1["tarball_sha256"] == a2["tarball_sha256"], "形态 A 的包两次打出来不一样"
    assert g1["tarball_sha256"] == g2["tarball_sha256"], "gold 子集包两次打出来不一样"
    for name in (PP.SUMS_NAME, PP.MANIFEST_NAME, PP.README_NAME,
                 GS.SUMS_NAME, GS.MANIFEST_NAME, GS.README_NAME):
        assert _sha(d1 / name) == _sha(d2 / name), name


def test_不给built_at的两次必须不同_否则上一条是恒绿的(small_tree, tmp_path):
    """**判别力**：`built_at` 是包里唯一的时刻。不写死它两次就该不同 ——
    如果这里也相同，说明上一条测的根本不是「确定性」。"""
    gb, repo, r2 = small_tree
    d1, d2 = tmp_path / "e1", tmp_path / "e2"
    a1, g1 = _pack_both(gb, repo, r2, d1, "2026-09-12T00:00:00+00:00")
    a2, g2 = _pack_both(gb, repo, r2, d2, "2026-09-12T00:00:01+00:00")
    assert a1["tarball_sha256"] != a2["tarball_sha256"]
    assert g1["tarball_sha256"] != g2["tarball_sha256"]


def test_包里不写打包机器的落点(small_tree, tmp_path):
    gb, repo, r2 = small_tree
    d = tmp_path / "d"
    _pack_both(gb, repo, r2, d, "2026-09-12T00:00:00+00:00")
    for name in (PP.MANIFEST_NAME, GS.MANIFEST_NAME):
        assert str(d) not in (d / name).read_text(encoding="utf-8"), name


def test_两个脚本的命令行都认built_at():
    for mod in ("ops/release/pack_public_provider.py", "ops/release/pack_gold_subset.py"):
        out = subprocess.run([sys.executable, str(REPO / mod), "--help"],
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr[-400:]
        assert "--built-at" in out.stdout, mod


# ================================================================== 5. 登记进 RELEASE_MANIFEST

#: 认得出的附件 `role`。**判「有没有多出来一件没人认识的」按 role 判，不按个数判**
#: （N-780）：写死件数的断言会被「第一个把新附件登记进来的代理」跑红，而那不是回归
#: —— 与 `ops/test_c41.py` 那条 `len(REG.CONFIGS) == 3` 同一个形状。
#: 三个值分别来自 ops/release/pack_public_provider.py、pack_gold_subset.py、
#: pack_public_runtime.py 写进 attachments.json 的 `role`。
KNOWN_ATTACHMENT_ROLES = {"public_provider", "public_gold_subset", "public_runtime_material"}


def test_附件逐件进了RELEASE_MANIFEST():
    m = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    ra = m["release_attachments"]
    by = {a["name"]: a for a in ra["attachments"]}
    # 已发的两件**必须在**清单里（⊆，不是 ==）；再登记第三、第四件不算回归。
    assert {PP.TARBALL, GS.TARBALL} <= set(by), sorted(by)
    # `n` 与表同源，而且名字不许重复 —— 重名会让「下到的这个是不是你们发的那一个」答不出来。
    assert ra["n"] == len(ra["attachments"]) == len(by), (ra["n"], sorted(by))
    # 多出来一件不认识的 role 仍然要有人看一眼。
    unknown = sorted(a["name"] for a in by.values() if a["role"] not in KNOWN_ATTACHMENT_ROLES)
    assert not unknown, f"清单里有 role 不认识的附件：{unknown}"
    for a in by.values():
        for k in MR.ATTACHMENT_FIELDS:
            assert k in a, k
        assert isinstance(a["bytes"], int) and a["bytes"] > 0
        assert len(a["sha256"]) == 64 and all(c in "0123456789abcdef" for c in a["sha256"])
        assert a["axes"]["set_version"] == m["axes"]["set_version"]
        assert a["axes"]["reference_root"] == m["axes"]["reference_root"]


def test_清单里记的sha就是盘上那个包的sha():
    """**清单的全部价值在这一条上**：外部用户拿 sha256 校下到的文件。"""
    m = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    dest = PP.published_dir()
    checked = 0
    for a in m["release_attachments"]["attachments"]:
        p = dest / a["name"]
        if not p.is_file():
            continue
        assert _sha(p) == a["sha256"], f"{a['name']}：清单与盘上的包对不上"
        assert p.stat().st_size == a["bytes"]
        checked += 1
    if not checked:
        pytest.skip(f"{dest} 下还没有打好的包（只有数据面那台有）")


def test_附件是判据字段_变了要停下来看():
    assert "release_attachments" in MR.FATAL_KEYS
    base = {"release_attachments": {"n": 2}, "files": {}}
    moved = {"release_attachments": {"n": 1}, "files": {}}
    fatal, drift = MR.classify_drift(moved, base)
    assert fatal == ["release_attachments"] and drift == []


def test_重新打包不会抹掉已回填的下载地址(tmp_path):
    """上传那一步（卡 D）回填 `download_url`，之后再打一次包不许把它清掉。"""
    repo = tmp_path / "repo"
    (repo / "ops" / "release").mkdir(parents=True)
    PP.record_attachment(repo, {"name": "x.tar.gz", "sha256": "a" * 64,
                                "download_url": "https://example.invalid/x.tar.gz"})
    PP.record_attachment(repo, {"name": "x.tar.gz", "sha256": "b" * 64, "download_url": ""})
    d = json.loads((repo / PP.ATTACHMENTS_JSON).read_text(encoding="utf-8"))
    assert len(d["attachments"]) == 1
    assert d["attachments"][0]["sha256"] == "b" * 64
    assert d["attachments"][0]["download_url"] == "https://example.invalid/x.tar.gz"


def test_登记表按名字排序且同名只有一条(tmp_path):
    repo = tmp_path / "repo"
    (repo / "ops" / "release").mkdir(parents=True)
    for n in ("z.tar.gz", "a.tar.gz", "z.tar.gz"):
        PP.record_attachment(repo, {"name": n, "sha256": "c" * 64, "download_url": ""})
    d = json.loads((repo / PP.ATTACHMENTS_JSON).read_text(encoding="utf-8"))
    assert [a["name"] for a in d["attachments"]] == ["a.tar.gz", "z.tar.gz"]


def test_清单仍然可发布():
    m = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    assert m["missing"] == [] and m["releasable"] is True
    assert [b["id"] for b in m["blockers"] if not b["satisfied"]] == []
