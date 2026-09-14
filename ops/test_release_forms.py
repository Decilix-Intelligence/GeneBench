# -*- coding: utf-8 -*-
"""卡 1.4：发布形态两条都走通。

**这里的每一条都能红**：夹具是一棵真的小树，打的是真的 tar，比的是真的 sha256。
恒绿的检查（"目录存在吗"之类）一条都不留 —— 那种检查通过了也说明不了任何事。

判别力集中在五处：

1. `SHA256SUMS` / `MANIFEST.json` / tar **三者自洽** —— 改任何一个文件的一个字节，
   三处都要跟着变，且 `compare()` 必须指出是哪个文件；
2. **确定性**：同一棵树打两次，tar 字节相同（不然"校验和"这个词没有意义）；
3. **答案面守门**：往物料里塞一个 `scorer/` 文件，打包必须拒绝；
4. **许可锁**：`pending_license_text` 时往可发布路径写包必须拒绝，
   且 MANIFEST 的 `published` 必须是 `false`；
5. **随包副本的漂移**（2026-09-07 红队）：包打完之后有人改了仓库里的数据卡 ——
   数据一个字节没变，而 `compare()` 当时把它记成 `differ` 并退 1，
   于是形态 B 对**所有人**都是红的。夹具在这里必须走「先 pack，**再改仓库**，
   再 compare」这条真实次序，不能打包与比对同一瞬间取同一份 repo（那样照不出漂移）。
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
import tarfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import genebench_config as cfg                              # noqa: E402
from ops.release import pack_public_provider as PP          # noqa: E402
from ops.release import universe_from_instruments as UFI    # noqa: E402
from snapshots.public import manifest as PM                 # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]

LICENSE_PENDING = """# 数据许可与来源声明

**状态：`pending_license_text`** —— 再分发许可已取得，书面原文尚未入库。

## 2. 许可原文

> 待入库。
"""
LICENSE_GRANTED = LICENSE_PENDING.replace("pending_license_text", "granted")

#: 夹具里的 instruments —— 三列，`SHxxxxxx\\t起\\t止`，与真 provider 同形状。
INSTRUMENTS = {
    "csi300": "SH600000\t2009-01-05\t2010-06-30\nSZ000001\t2009-01-05\t2026-07-31\n",
    "csi500": "SZ000002\t2011-01-04\t2026-07-31\n",
    "csi1000": "SH600001\t2015-01-05\t2020-12-31\n",
    "all": "SH600000\t2009-01-05\t2026-07-31\nSZ000001\t2009-01-05\t2026-07-31\n"
           "SZ000002\t2009-01-05\t2026-07-31\nSH600001\t2009-01-05\t2026-07-31\n",
}


def _write(p: pathlib.Path, text: str) -> pathlib.Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture()
def tree(tmp_path):
    """一棵**能真打包**的小树：数据根 + 仓库根。"""
    gb = tmp_path / "gb"
    repo = tmp_path / "repo"
    pub = gb / "snapshots" / cfg.PUBLIC_VERSION

    prov = pub / "qlib_provider"
    _write(prov / "calendars" / "day.txt", "2009-01-05\n2026-07-31\n")
    for uni, body in INSTRUMENTS.items():
        _write(prov / "instruments" / f"{uni}.txt", body)
    (prov / "features" / "SH600000").mkdir(parents=True)
    (prov / "features" / "SH600000" / "close.day.bin").write_bytes(b"\x00\x01\x02\x03" * 8)
    _write(prov / "files.sha256", "deadbeef  features/SH600000/close.day.bin\n")
    _write(prov / "manifest.json", json.dumps({"built_at": "2026-09-06T00:00:00+00:00"}))
    _write(prov / "build_info.json", json.dumps({"built_at": "x", "code_head": "y"}))
    _write(prov / "MANIFEST.sha256", "cafe  manifest.json\n")

    _write(pub / "tradability" / "year=2026" / "part-0.parquet", "not-really-parquet")
    _write(pub / "tradability" / "build_info.json", "{}")
    for t in ("daily", "adj_factor", "stk_limit", "suspend_d", "trade_cal", "stock_basic"):
        _write(pub / "tables" / f"{t}.parquet", f"table-{t}")
    _write(pub / "tables" / "build_info.json", "{}")
    # 不进包的两块：中间产物与断点标记
    _write(pub / "build" / "quotes.parquet", "huge-intermediate")
    _write(pub / "state" / "tables.done", "{}")
    _write(gb / "scratch" / "v1_union.txt", "SH600000\nSZ000001\n")
    # 宇宙定义面（2026-09-12 裁定 ①）：`universe/` 下除了取数名单，还必须带上
    # 卡 A 用 baostock 成分接口重建的 PIT 名单。它是**必需件**，缺了 collect() 当场抛。
    _write(pub / "universe" / "universe_pit.parquet", "not-really-parquet")
    _write(pub / "universe" / "build_info.json", "{}")
    _write(pub / "universe" / "MANIFEST.sha256", "cafe  universe_pit.parquet\n")

    _write(repo / "DATA_LICENSE", LICENSE_PENDING)
    _write(repo / "ops" / "data_cards" / "public_channel.md", "# 数据卡\n")
    _write(repo / "ops" / "reports" / "public" / "data_channel_notes.md", "# 建设记录\n")
    _write(repo / "ops" / "reports" / "public" / "qlib_provider_public.md", "# provider 卡\n")
    for rel in PM.PUBLIC_FROZEN_ARTIFACTS:
        if rel.startswith("reference/"):
            _write(repo / rel, f"# {rel}\n")
    for rel in ("ops/release/build_public_provider.sh", "ops/release/fetch_public_quotes.py",
                "ops/release/universe_from_instruments.py",
                "ops/release/rebuild_public_provider.py",
                "ops/release/pack_public_provider.py"):
        _write(repo / rel, f"# {rel}\n")
    return gb, repo


# ------------------------------------------------------------------ 三件产物自洽

def test_pack_produces_three_artifacts_and_manifest_hashes_match_files(tree):
    gb, repo = tree
    out = PP.pack(gb_root=gb, repo=repo, tar=True, verbose=False)
    dest = pathlib.Path(out["dest"])
    man = json.loads((dest / PP.MANIFEST_NAME).read_text(encoding="utf-8"))

    entries, _ = PP.collect(gb, repo)
    assert man["files"] == len(entries) > 0
    # 逐文件 sha256 必须与磁盘上的真实字节一致 —— 一个都不许对不上
    for e in entries:
        assert man["sha256"][e.arcname] == hashlib.sha256(e.src.read_bytes()).hexdigest(), e.arcname
    assert man["bytes"] == sum(e.size for e in entries)
    # 包里不许出现打包机器的落点（那会让包不可复现）
    assert "dest" not in man and str(dest) not in json.dumps(man, ensure_ascii=False)
    assert (dest / PP.TARBALL).is_file() and (dest / PP.SUMS_NAME).is_file()


def test_manifest_sha256_is_falsifiable(tree):
    """把一个源文件改一个字节，MANIFEST 里对应的哈希**必须**跟着变。

    这条是给上一条兜底的：上一条只证明"两边一致"，一致也可能是两边都从
    同一个错值抄的。这里动真字节，看它认不认得出来。
    """
    gb, repo = tree
    before = json.loads(json.dumps(PP.build_manifest(*PP.collect(gb, repo), state="pending_license_text",
                                                     gb_root=gb, repo=repo, dest=gb)["sha256"]))
    victim = gb / "snapshots" / cfg.PUBLIC_VERSION / "tables" / "daily.parquet"
    victim.write_text("table-daily-TAMPERED", encoding="utf-8")
    after = PP.build_manifest(*PP.collect(gb, repo), state="pending_license_text",
                              gb_root=gb, repo=repo, dest=gb)["sha256"]
    changed = [k for k in before if before[k] != after[k]]
    assert changed == ["tables/daily.parquet"], changed


def test_sums_file_is_sha256sum_c_compatible(tree):
    gb, repo = tree
    out = PP.pack(gb_root=gb, repo=repo, tar=True, verbose=False)
    dest = pathlib.Path(out["dest"])
    with tarfile.open(dest / PP.TARBALL, "r:gz") as tar:
        try:
            tar.extractall(dest / "x", filter="data")
        except TypeError:                                   # pragma: no cover (py<3.12)
            tar.extractall(dest / "x")
    root = dest / "x" / PP.PACKAGE_NAME
    r = subprocess.run(["sha256sum", "-c", PP.SUMS_NAME], cwd=root,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    # 解开的树里，SHA256SUMS 覆盖的文件数 == 树里除 SHA256SUMS 外的文件数
    listed = set(PP.parse_sums((root / PP.SUMS_NAME).read_text(encoding="utf-8")))
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert listed == on_disk - {PP.SUMS_NAME}


def test_tar_is_byte_deterministic(tree):
    """同一棵树打两次，字节相同。**不同就说明"校验和"这个词没有意义。**"""
    gb, repo = tree
    a = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=True, verbose=False)["dest"]) / PP.TARBALL
    first = a.read_bytes()
    b = a.with_name("second.tar.gz")
    entries, _ = PP.collect(gb, repo)
    PP.write_tar(b, entries, [("X", b"x")])
    PP.write_tar(a.with_name("third.tar.gz"), entries, [("X", b"x")])
    assert b.read_bytes() == a.with_name("third.tar.gz").read_bytes()
    assert len(first) > 0
    # 换一个字节，包体必须变
    (gb / "snapshots" / cfg.PUBLIC_VERSION / "tables" / "daily.parquet").write_text("Z")
    entries2, _ = PP.collect(gb, repo)
    PP.write_tar(a.with_name("fourth.tar.gz"), entries2, [("X", b"x")])
    assert a.with_name("fourth.tar.gz").read_bytes() != b.read_bytes()


def test_whole_package_is_reproducible_given_the_same_built_at(tree):
    """**整包**可复现：同一棵树 + 同一个 `--built-at` → tar.gz 逐字节相同。

    不写死 `built_at` 时包体会变（MANIFEST 里有构建时刻）—— 那是有意的，
    但对外承诺「你也能打出同一个包」时必须给得出这条口径。
    """
    gb, repo = tree
    stamp = "2026-09-06T00:00:00+00:00"
    first = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=True, verbose=False,
                                 built_at=stamp)["dest"]) / PP.TARBALL
    a = first.read_bytes()
    # **换一个落点**再打一次：包体不许因为"打到哪儿"而变。
    # （实测踩过：MANIFEST 里写了 dest，同一棵树打到两个目录差 97 字节。）
    other = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=True, verbose=False,
                                 dest=gb.parent / "elsewhere", built_at=stamp)["dest"]) / PP.TARBALL
    assert other.read_bytes() == a, "换个落点包体就变了 —— MANIFEST 里混进了打包机器的路径"
    second = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=True, verbose=False,
                                  built_at=stamp)["dest"]) / PP.TARBALL
    assert second.read_bytes() == a
    third = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=True, verbose=False,
                                 built_at="2026-09-07T00:00:00+00:00")["dest"]) / PP.TARBALL
    assert third.read_bytes() != a, "换了 built_at 包体却没变 —— MANIFEST 没进包？"


def test_tar_entries_carry_no_timestamps_or_owner(tree):
    gb, repo = tree
    dest = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=True, verbose=False)["dest"])
    with tarfile.open(dest / PP.TARBALL, "r:gz") as tar:
        members = tar.getmembers()
    assert members, "空包"
    for m in members:
        assert m.mtime == 0 and m.uid == 0 and m.gid == 0 and m.uname == "" and m.gname == "", m.name
        assert m.name.startswith(PP.PACKAGE_NAME + "/"), m.name
    assert [m.name for m in members] == sorted(m.name for m in members), "条目没排序 = 不确定"


# ------------------------------------------------------------------ 许可锁

def test_published_is_false_and_dest_is_staging_while_license_pending(tree):
    gb, repo = tree
    assert PP.read_license_state(repo) == "pending_license_text"
    out = PP.pack(gb_root=gb, repo=repo, tar=False, verbose=False)
    dest = pathlib.Path(out["dest"])
    assert dest == PP.staging_dir(gb), dest
    man = json.loads((dest / PP.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert man["license"]["state"] == "pending_license_text"
    assert man["license"]["published"] is False
    assert man["license"]["publishable"] is False


def test_packing_into_the_publishable_path_is_refused_while_pending(tree):
    gb, repo = tree
    with pytest.raises(PP.PackageError, match="拒绝往可发布路径"):
        PP.pack(gb_root=gb, repo=repo, dest=PP.published_dir(gb), tar=False, verbose=False)


def test_publishable_flips_only_when_the_license_text_is_in(tree):
    """状态翻 `granted` 之后落点与 `publishable` 都要跟着翻 —— 否则这个字段是摆设。"""
    gb, repo = tree
    (repo / "DATA_LICENSE").write_text(LICENSE_GRANTED, encoding="utf-8")
    out = PP.pack(gb_root=gb, repo=repo, tar=False, verbose=False)
    assert pathlib.Path(out["dest"]) == PP.published_dir(gb)
    man = json.loads((pathlib.Path(out["dest"]) / PP.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert man["license"]["publishable"] is True
    assert man["license"]["published"] is False, "publishable ≠ published：发不发是人的决定"


def test_release_guard_catches_an_archive_sitting_in_the_publishable_path(tree):
    gb, repo = tree
    pub = PP.published_dir(gb)
    pub.mkdir(parents=True)
    (pub / "genebench_public_provider_v1.tar.gz").write_bytes(b"\x1f\x8b")
    with pytest.raises(PP.PackageError, match="许可原文还没入库"):
        PP.assert_nothing_published_while_pending(gb, repo)
    # 原文入库（状态翻 granted）之后同一棵树不再报 —— 锁盯的是状态，不是路径
    (repo / "DATA_LICENSE").write_text(LICENSE_GRANTED, encoding="utf-8")
    PP.assert_nothing_published_while_pending(gb, repo)


def test_license_state_parser_agrees_with_test_env(tree):
    """两处解析口径分叉 = 两个文件各说各话。这里钉死它们读出同一个值。"""
    from ops import test_env as TE
    _, repo = tree
    assert tuple(PP.LICENSE_STATES) == tuple(TE.LICENSE_STATES)
    assert PP.read_license_state(REPO) == TE._license_state()


# ------------------------------------------------------------------ 答案面守门（红线 2）

def test_answer_plane_content_is_refused(tree):
    gb, repo = tree
    bad = PP.Entry("frozen/scorer/l3.py", repo / "DATA_LICENSE", 1, "0" * 64)
    with pytest.raises(PP.PackageError, match="答案面"):
        PP.assert_no_answer_plane([bad])


def test_reference_allowlist_is_exactly_the_frozen_artifacts(tree):
    """`reference/` 只放行物料清单明列的那几个；多一个都要红。"""
    gb, repo = tree
    ok = [PP.Entry(f"frozen/{a}", repo / "DATA_LICENSE", 1, "0" * 64)
          for a in PP.REFERENCE_ALLOWLIST]
    PP.assert_no_answer_plane(ok)
    with pytest.raises(PP.PackageError, match="白名单外"):
        PP.assert_no_answer_plane(ok + [PP.Entry("frozen/reference/solve.py",
                                                 repo / "DATA_LICENSE", 1, "0" * 64)])
    assert set(PP.REFERENCE_ALLOWLIST) <= set(PM.PUBLIC_FROZEN_ARTIFACTS)


def test_real_package_carries_no_answer_plane_paths(tree):
    """真物料清单本身不许把答案面写进去（清单是代码，会被改）。"""
    for comp in PP.components(tree[0], REPO):
        for rel in comp.get("items", []):
            assert not rel.startswith(("scorer/", "runs_in/", "gold/")), rel
            if rel.startswith("reference/"):
                assert rel in PM.PUBLIC_FROZEN_ARTIFACTS, rel


def test_intermediate_and_state_are_not_in_the_package(tree):
    """`build/`（409MB 中间产物）与 `state/`（断点）不该进包。"""
    gb, repo = tree
    names = {e.arcname for e in PP.collect(gb, repo)[0]}
    assert not [n for n in names if "/build/" in n or n.endswith(".done")], sorted(names)
    assert "provider/files.sha256" in names and "universe/v1_union.txt" in names


def test_missing_declared_frozen_artifact_is_recorded_not_swallowed(tree):
    """清单声明了但仓库里没有的冻结件，必须出现在 MANIFEST 里 —— 不许静默丢。"""
    gb, repo = tree
    victim = repo / PP.REFERENCE_ALLOWLIST[0]
    victim.unlink()
    entries, missing = PP.collect(gb, repo)
    assert f"frozen/{PP.REFERENCE_ALLOWLIST[0]}" in missing
    man = PP.build_manifest(entries, missing, state="pending_license_text",
                            gb_root=gb, repo=repo, dest=gb)
    assert man["missing_declared_artifacts"] == missing and missing


# ------------------------------------------------------------------ 形态 B：比对

def test_compare_is_green_on_the_same_tree_and_red_on_one_flipped_byte(tree):
    gb, repo = tree
    dest = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=False, verbose=False)["dest"])
    sums = dest / PP.SUMS_NAME
    rep = PP.compare(sums, gb_root=gb, repo=repo)
    assert rep["ok"] and rep["differ"] == [] and rep["same"] > 0

    (gb / "snapshots" / cfg.PUBLIC_VERSION / "tables" / "daily.parquet").write_text("X")
    rep2 = PP.compare(sums, gb_root=gb, repo=repo)
    assert rep2["ok"] is False and rep2["differ"] == ["tables/daily.parquet"]


def test_build_stamped_differences_are_reported_separately_not_as_failures(tree):
    """构建戳文件（带 built_at / 绝对路径）两次构建必然不同 —— 它们要单列一堆，
    **不能**混进 `differ` 把真问题淹掉；但也**不能**从 SHA256SUMS 里删掉。"""
    gb, repo = tree
    dest = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=False, verbose=False)["dest"])
    prov = gb / "snapshots" / cfg.PUBLIC_VERSION / "qlib_provider"
    (prov / "manifest.json").write_text(json.dumps({"built_at": "2026-09-07T00:00:00+00:00"}))
    (prov / "build_info.json").write_text(json.dumps({"built_at": "z", "code_head": "w"}))
    rep = PP.compare(dest / PP.SUMS_NAME, gb_root=gb, repo=repo)
    assert rep["ok"] is True, rep["differ"]
    assert set(rep["build_stamped_differ"]) == {"provider/manifest.json",
                                                "provider/build_info.json"}
    listed = PP.parse_sums((dest / PP.SUMS_NAME).read_text(encoding="utf-8"))
    assert "provider/manifest.json" in listed


def test_build_stamped_patterns_are_not_zombies(tree):
    """每条 `BUILD_STAMPED` 模式都必须真的命中包里的文件（D-23：豁免要可证伪）。"""
    gb, repo = tree
    names = [e.arcname for e in PP.collect(gb, repo)[0]]
    import fnmatch
    for pat, why in PP.BUILD_STAMPED.items():
        assert [n for n in names if fnmatch.fnmatch(n, pat)], f"{pat} 一个都命不中 —— 删掉它"
        assert why.strip(), pat


# ------------------------------------------------------------------ 形态 B：随包副本漂移

def _doc_in_repo(repo: pathlib.Path) -> pathlib.Path:
    return repo / "ops" / "data_cards" / "public_channel.md"


def test_a_doc_changed_after_packing_does_not_turn_form_b_red(tree, monkeypatch):
    """**打包之后**有人改了仓库里的数据卡 —— 数据一个字节没变，形态 B 不许因此变红。

    这是红队 2026-09-07 实测到的真实失败：包是 09-06 打的，数据卡 09-07 改过，
    `compare` 输出 `differ 1 → 退出码 1`，而那一跑的 28,645 个数据文件全部相同。
    次序是判别力所在：**先 pack，再改仓库，再 compare**。
    """
    gb, repo = tree
    dest = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=False, verbose=False)["dest"])
    sums = dest / PP.SUMS_NAME
    assert PP.compare(sums, gb_root=gb, repo=repo)["ok"]

    doc = _doc_in_repo(repo)
    doc.write_text(doc.read_text(encoding="utf-8") + "\n新增一节：§12 补一句话。\n",
                   encoding="utf-8")
    rep = PP.compare(sums, gb_root=gb, repo=repo)
    assert rep["ok"] is True, rep["differ"]
    assert rep["differ"] == []
    assert rep["package_provided_differ"] == ["docs/ops/data_cards/public_channel.md"]
    # 仍然在 SHA256SUMS 里 —— 包体完整性要它（`sha256sum -c` 校的是包内副本）
    assert "docs/ops/data_cards/public_channel.md" in PP.parse_sums(
        sums.read_text(encoding="utf-8"))

    # **豁免要可证伪**：把这条豁免摘掉，同一个场景必须变红（否则上面那几行说明不了什么）
    monkeypatch.setattr(PP, "PACKAGE_PROVIDED", {})
    red = PP.compare(sums, gb_root=gb, repo=repo)
    assert red["ok"] is False
    assert red["differ"] == ["docs/ops/data_cards/public_channel.md"]


def test_a_selfbuild_script_changed_after_packing_is_reported_not_red(tree):
    """`selfbuild/` 同理：脚本改版不改已发布的那份数据。"""
    gb, repo = tree
    dest = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=False, verbose=False)["dest"])
    (repo / "ops" / "release" / "fetch_public_quotes.py").write_text(
        "# 改过了\n", encoding="utf-8")
    rep = PP.compare(dest / PP.SUMS_NAME, gb_root=gb, repo=repo)
    assert rep["ok"] is True and rep["differ"] == []
    assert rep["package_provided_differ"] == ["selfbuild/ops/release/fetch_public_quotes.py"]


def test_the_exemption_does_not_leak_onto_the_data_plane(tree):
    """**豁免的射程**：文档被改的同时数据也被改 —— 数据那条必须照旧判红。

    这条是上面两条的反面。豁免宽一格的表现是「文档漂移把数据漂移一起吞了」，
    而那正是这份校验和唯一承诺的东西。
    """
    gb, repo = tree
    dest = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=False, verbose=False)["dest"])
    doc = _doc_in_repo(repo)
    doc.write_text(doc.read_text(encoding="utf-8") + "改了\n", encoding="utf-8")
    (gb / "snapshots" / cfg.PUBLIC_VERSION / "tables" / "daily.parquet").write_text("X")
    rep = PP.compare(dest / PP.SUMS_NAME, gb_root=gb, repo=repo)
    assert rep["ok"] is False
    assert rep["differ"] == ["tables/daily.parquet"]
    assert rep["package_provided_differ"] == ["docs/ops/data_cards/public_channel.md"]


def test_package_provided_patterns_are_not_zombies(tree):
    """每条 `PACKAGE_PROVIDED` 模式都必须真的命中包里的文件，且带理由（D-23）。"""
    gb, repo = tree
    names = [e.arcname for e in PP.collect(gb, repo)[0]]
    import fnmatch
    for pat, why in PP.PACKAGE_PROVIDED.items():
        assert [n for n in names if fnmatch.fnmatch(n, pat)], f"{pat} 一个都命不中 —— 删掉它"
        assert why.strip(), pat


def test_package_provided_never_covers_the_data_plane(tree):
    """豁免只许盖住「来自仓库工作树」的那两堆。数据面沾上一个就是判据被架空。"""
    gb, repo = tree
    covered = {e.arcname for e in PP.collect(gb, repo)[0] if e.package_provided}
    assert covered, "一个都没盖住 —— 那这张表是死的"
    for name in covered:
        assert name.split("/", 1)[0] in ("docs", "selfbuild"), name
    data = [e.arcname for e in PP.collect(gb, repo)[0]
            if e.arcname.split("/", 1)[0] in ("provider", "tables", "tradability",
                                              "universe", "frozen")]
    assert data and not (set(data) & covered)


def test_compare_flags_files_only_on_one_side(tree):
    gb, repo = tree
    dest = pathlib.Path(PP.pack(gb_root=gb, repo=repo, tar=False, verbose=False)["dest"])
    extra = gb / "snapshots" / cfg.PUBLIC_VERSION / "tables" / "surprise.parquet"
    extra.write_text("surprise")
    rep = PP.compare(dest / PP.SUMS_NAME, gb_root=gb, repo=repo)
    assert rep["only_in_rebuild"] == ["tables/surprise.parquet"] and rep["ok"] is False
    extra.unlink()
    (gb / "snapshots" / cfg.PUBLIC_VERSION / "tables" / "daily.parquet").unlink()
    rep2 = PP.compare(dest / PP.SUMS_NAME, gb_root=gb, repo=repo)
    assert rep2["only_in_package"] == ["tables/daily.parquet"] and rep2["ok"] is False


# ------------------------------------------------------------------ 形态 B：宇宙定义面反建

def test_universe_reconstruction_round_trips_byte_for_byte(tree):
    """从 `instruments/*.txt` 反建的行，再渲染回去必须与原文**逐字节相同**。

    这是形态 B 的命门：宇宙定义面公开源推不出来，只能随包发；
    反投影错一格（码的写法 / 日期形态 / 排序）都会让重建的 provider 悄悄错。
    """
    gb, _ = tree
    ins = gb / "snapshots" / cfg.PUBLIC_VERSION / "qlib_provider" / "instruments"
    rows = UFI.read_instruments(ins, universes=tuple(INSTRUMENTS))
    by_uni: dict[str, list[str]] = {}
    for r in rows:
        num, ex = r["code"].split(".")
        iso = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:]}"          # noqa: E731
        by_uni.setdefault(r["universe"], []).append(
            f"{ex}{num}\t{iso(r['in_date_compact'])}\t{iso(r['out_date_compact'])}")
    for uni, body in INSTRUMENTS.items():
        assert "\n".join(by_uni[uni]) + "\n" == body, uni


def test_universe_reconstruction_refuses_a_broken_instruments_file(tree):
    gb, _ = tree
    ins = gb / "snapshots" / cfg.PUBLIC_VERSION / "qlib_provider" / "instruments"
    (ins / "csi300.txt").write_text("SH600000\t2009-01-05\n", encoding="utf-8")
    with pytest.raises(UFI.ReconstructError, match="不是三列"):
        UFI.read_instruments(ins, universes=("csi300",))
    (ins / "csi300.txt").write_text("", encoding="utf-8")
    with pytest.raises(UFI.ReconstructError, match="空的"):
        UFI.read_instruments(ins, universes=("csi300",))
    (ins / "csi300.txt").unlink()
    with pytest.raises(UFI.ReconstructError, match="缺"):
        UFI.read_instruments(ins, universes=("csi300",))


def test_qlib_code_inverse_agrees_with_the_provider(tree):
    from snapshots.qlib_provider import qlib_code
    for lake in ("600000.SH", "000001.SZ", "301234.SZ"):
        assert UFI.qlib_to_lake(qlib_code(lake)) == lake
    with pytest.raises(UFI.ReconstructError):
        UFI.qlib_to_lake("600000")


# ------------------------------------------------------------------ 形态 B 的脚本本身

def test_selfbuild_scripts_shipped_in_the_package_all_exist_in_the_repo():
    """包里 `selfbuild/` 列的每个脚本都要真的在仓库里 —— 少一个，用户就自建不成。"""
    listed = [rel for c in PP.components(cfg.GENEBENCH_ROOT, REPO)
              if c["prefix"] == "selfbuild" for rel in c["items"]]
    assert listed
    for rel in listed:
        assert (REPO / rel).is_file(), rel


def test_build_public_provider_sh_is_syntactically_valid_and_refuses_missing_args():
    sh = REPO / "ops" / "release" / "build_public_provider.sh"
    assert subprocess.run(["bash", "-n", str(sh)], capture_output=True).returncode == 0
    r = subprocess.run(["bash", str(sh), "--root", "/tmp/nope"], capture_output=True, text=True)
    assert r.returncode == 2, r.stdout + r.stderr


def test_fetch_wrapper_does_not_carry_its_own_trading_hours_rule():
    """取数守门只许有一份实现。包装器里再写一份 = 留了个可以悄悄放宽的副本。"""
    src = (REPO / "ops" / "release" / "fetch_public_quotes.py").read_text(encoding="utf-8")
    assert "def assert_not_trading_hours" not in src
    assert "card_2_5_fetch_union" in src
    import importlib
    fu = importlib.import_module("ops.acceptance.card_2_5_fetch_union")
    assert hasattr(fu, "assert_not_trading_hours") and hasattr(fu, "main")


def test_cli_dry_run_runs_on_the_fixture(tree, capsys):
    gb, repo = tree
    rc = PP.main(["--root", str(gb), "--repo", str(repo), "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0 and "pending_license_text" in out and "provider" in out and "docs" in out
