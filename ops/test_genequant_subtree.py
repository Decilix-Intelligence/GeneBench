#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 ㉑：**`genequant/` 子树**——可独立发布的那棵协议工件——的守门与重建。

为什么要有这棵树：协议（GeneQuant）与基准（GeneBench）是**两件可以分开被人用的东西**。
一个只想用「三态声明 + 依赖图 + validator」这套产物协议的人，不需要拿 15 GB 的 gold、
不需要网关、不需要 34 道题。所以协议工件整理成一棵自带 README / LICENSE / MANIFEST /
CITATION 的树，单独有一个仓库地址。

**这棵树里没有一个字节是新写的协议内容。** 逐件是仓库里那一份的**副本**
（`SOURCES` 给出每一件的来源），加四份**说明性**的新文件（`OWN`）。
改协议内容要改的是 `ops/protocol/` 下的原件 —— 改副本会被下面的
:func:`test_每份副本与仓库原件逐字节相同` 当场抓到。

**这条测试就是「钉住」二字的实现**（裁定 ㉑ 第 2 条）：
`RELEASE_MANIFEST.json` 的 `genequant.manifest_sha256` 钉住本树的 MANIFEST，
而本树的 MANIFEST 逐件钉住原件的 sha256。于是「benchmark 本体以 MANIFEST sha
钉住所用的 genequant 版本」是一条**可以红**的断言，不是一句话。

重建（改了原件、或改了本树的四份说明文件之后）::

    $PY ops/test_genequant_subtree.py --rebuild     # 重新复制 + 重出 genequant/MANIFEST.json
    $PY ops/mk_release_manifest.py                  # 重出 RELEASE_MANIFEST（pin 会跟着变）

顺序不能倒 —— 倒过来的话清单钉的是上一版的 MANIFEST，而**两边都不会红**。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ROOT = REPO / "genequant"
MANIFEST = ROOT / "MANIFEST.json"

#: 子树里**每一件副本**：`子树内路径 -> 仓库内原件路径`。
#: 这张表是封闭的 —— 「协议工件 = 某个目录里当时有的东西」在 `geneprotocol_v1/MANIFEST.json`
#: 的 `_closed_set` 里已经被否决过一次，这里是同一条纪律的第二处落点。
SOURCES: dict[str, str] = {
    # —— 三条协议各自的规格 / 契约 / validator / 适配模块（逐件从 ops/protocol/ 取）
    "protocols/geneprotocol_v1/README.md": "ops/protocol/geneprotocol_v1/README.md",
    "protocols/geneprotocol_v1/contract.md": "ops/protocol/geneprotocol_v1/contract.md",
    "protocols/geneprotocol_v1/validate_artifact.py":
        "ops/protocol/geneprotocol_v1/validate_artifact.py",
    "protocols/geneprotocol_v1/MANIFEST.json": "ops/protocol/geneprotocol_v1/MANIFEST.json",
    "protocols/geneprotocol_v1_doc/README.md": "ops/protocol/geneprotocol_v1_doc/README.md",
    "protocols/geneprotocol_v1_doc/contract.md": "ops/protocol/geneprotocol_v1_doc/contract.md",
    "protocols/geneprotocol_v1_doc/MANIFEST.json":
        "ops/protocol/geneprotocol_v1_doc/MANIFEST.json",
    "protocols/geneprotocol_v1_adapt/adaptation.md":
        "ops/protocol/geneprotocol_v1_adapt/adaptation.md",
    "protocols/geneprotocol_v1_adapt/field_map.json":
        "ops/protocol/geneprotocol_v1_adapt/field_map.json",
    "protocols/geneprotocol_v1_adapt/unit_table.json":
        "ops/protocol/geneprotocol_v1_adapt/unit_table.json",
    "protocols/geneprotocol_v1_adapt/MANIFEST.json":
        "ops/protocol/geneprotocol_v1_adapt/MANIFEST.json",
    # —— 结构层：contract.md 与 validator 口口声声的那份 `artifact_schema.json` 的冻结落盘版
    **{f"schema/artifact_schema/v1.0/S{k}.json":
       f"ops/specs/artifact_schema/v1.0/S{k}.json" for k in range(1, 9)},
    # —— 投放说明的**机读源**：臂 = 投放的工件集合，这件事由 arms.yaml 定义而不是写死在代码里
    "placement/arms.yaml": "genetask/arms.yaml",
    # —— 许可：与本体同一份 Apache-2.0（逐字节相同，不另拟一份）
    "LICENSE": "LICENSE",
}

#: 子树自己的说明件（**不是副本**，没有仓库原件可比）。它们的 sha 照样进 MANIFEST ——
#: 「封闭集合」要封的是整棵树，留一个不进清单的角落等于没封。
OWN: tuple[str, ...] = ("README.md", "PLACEMENT.md", "CITATION.cff")

#: 两个目标仓库地址与协议版本号的**唯一定义处**是 `ops/mk_release_manifest.py` ——
#: 这里只引用。各写一遍的两份常量必然漂，而漂的表现是「测试全绿、发出去的地址是旧的」。
from ops import mk_release_manifest as MR  # noqa: E402

VERSION = MR.GENEQUANT_VERSION


def repositories() -> dict[str, str]:
    return dict(MR.REPOSITORIES)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest() -> dict:
    """本树的 MANIFEST。**刻意没有时间戳** —— 带时间戳的话每重建一次
    `RELEASE_MANIFEST` 钉的那个 sha 就变一次，pin 就退化成噪声。"""
    repos = repositories()
    return {
        "manifest_version": 1,
        "protocol_suite": "genequant",
        "version": VERSION,
        "protocols": ["geneprotocol_v1", "geneprotocol_v1_doc", "geneprotocol_v1_adapt"],
        "repository": repos["genequant"],
        "benchmark_repository": repos["genebench"],
        "_what_this_is": (
            "GeneQuant 协议 v1 的可独立发布副本：三条协议的规格与契约、artifact 自检 "
            "validator、适配模块、结构层 schema、投放说明。**不含任何一道题、任何答案、"
            "任何 gold** —— 那些是 GeneBench 本体的东西。"),
        "_closed_set": (
            "copies + own + 本文件 = 整棵树，一个不多一个不少。"
            "ops/test_genequant_subtree.py 两个方向都查（多一个文件也红）。"),
        "_copies_are_copies": (
            "copies 里每一件与 GeneBench 仓库里 source 那一份**逐字节相同**；"
            "改协议内容要改原件再 --rebuild，改副本会被测试抓到。"),
        "generated_by": "ops/test_genequant_subtree.py --rebuild",
        "copies": {rel: {"sha256": sha256(ROOT / rel),
                         "bytes": (ROOT / rel).stat().st_size,
                         "source_in_genebench": src}
                   for rel, src in sorted(SOURCES.items())},
        "own": {rel: {"sha256": sha256(ROOT / rel), "bytes": (ROOT / rel).stat().st_size}
                for rel in sorted(OWN)},
    }


def rebuild() -> list[str]:
    """复制 + 重出 MANIFEST。返回真正被写过的路径（幂等：内容相同就不动）。"""
    written: list[str] = []
    for rel, src in SOURCES.items():
        s, d = REPO / src, ROOT / rel
        if not s.is_file():
            raise SystemExit(f"[红] 源件不存在：{src}")
        data = s.read_bytes()
        if not d.is_file() or d.read_bytes() != data:
            d.parent.mkdir(parents=True, exist_ok=True)
            d.write_bytes(data)
            d.chmod(0o600)
            written.append(rel)
    for rel in OWN:
        if not (ROOT / rel).is_file():
            raise SystemExit(f"[红] 子树自己的说明件缺失，先写它：genequant/{rel}")
    new = json.dumps(build_manifest(), ensure_ascii=False, indent=1) + "\n"
    if not MANIFEST.is_file() or MANIFEST.read_text(encoding="utf-8") != new:
        MANIFEST.write_text(new, encoding="utf-8")
        MANIFEST.chmod(0o600)
        written.append("MANIFEST.json")
    return written


# ================================================================ 测试

@pytest.fixture(scope="module")
def M() -> dict:
    assert MANIFEST.is_file(), "genequant/MANIFEST.json 不在 —— 跑 --rebuild"
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_每份副本与仓库原件逐字节相同(M):
    """**这条红了就说明协议内容被改过而 pin 没跟着走。**

    两个方向都查：副本 == 原件，且两者都 == MANIFEST 记的那个 sha。
    只查「副本 == MANIFEST」的话，把原件和副本一起改掉就能全绿 ——
    那正是「以 MANIFEST sha 钉住」要防的事。
    """
    bad = []
    for rel, src in SOURCES.items():
        orig, copy = REPO / src, ROOT / rel
        assert orig.is_file(), f"源件不见了：{src}"
        assert copy.is_file(), f"副本不见了：genequant/{rel}（跑 --rebuild）"
        so, sc = sha256(orig), sha256(copy)
        rec = M["copies"].get(rel, {})
        if not (so == sc == rec.get("sha256")):
            bad.append(f"{rel}: 原件 {so[:12]} / 副本 {sc[:12]} / 清单 {str(rec.get('sha256'))[:12]}")
        assert rec.get("source_in_genebench") == src, f"{rel} 的来源记错了"
    assert not bad, "协议工件漂了（改原件 → --rebuild → mk_release_manifest）：\n" + "\n".join(bad)


def test_子树自己的说明件也在清单里且_sha_对得上(M):
    for rel in OWN:
        p = ROOT / rel
        assert p.is_file(), f"genequant/{rel} 不在"
        assert M["own"][rel]["sha256"] == sha256(p), f"genequant/{rel} 改过但没 --rebuild"


def test_清单是封闭集合_多一个文件也红(M):
    """封闭的意思是**两个方向**：清单里的都在，树里的都在清单里。

    只查前一个方向的话，往树里丢一个文件不会红 —— 而「协议工件 = 目录里当时有的东西」
    这条在 geneprotocol_v1 的 MANIFEST 里已经被否决过一次。
    """
    on_disk = {str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file()}
    declared = set(M["copies"]) | set(M["own"]) | {"MANIFEST.json"}
    assert on_disk == declared, (
        f"树里多出来的：{sorted(on_disk - declared)}；清单里缺的：{sorted(declared - on_disk)}")


def test_树里没有字节码和编辑器残留():
    """`ops/protocol/geneprotocol_v1/` 里躺着两个 `.pyc`（跑过 validator 留下的）——
    照目录整个拷会把它们一起带走，而 `__pycache__` 的 0775 会把红线 5 的守门跑红。"""
    junk = sorted(str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
                  if p.is_file() and (p.suffix in {".pyc", ".pyo", ".orig", ".rej", ".swp"}
                                      or "__pycache__" in p.parts or p.name.startswith(".#")))
    assert not junk, f"genequant/ 里有不该发出去的东西：{junk}"


def test_三条协议自己的封闭清单在副本里仍然成立(M):
    """副本树里的 `protocols/<id>/MANIFEST.json` 说的 sha，要等于副本树里那几个文件的 sha。

    这一条与上面那条不同：上面比的是「副本 vs 原件」，这一条比的是
    「副本树内部自洽」—— 拿到 GeneQuant 仓库的人只有这棵树，他能核的就是这一层。
    """
    for pid in ("geneprotocol_v1", "geneprotocol_v1_doc", "geneprotocol_v1_adapt"):
        d = ROOT / "protocols" / pid
        man = json.loads((d / "MANIFEST.json").read_text(encoding="utf-8"))
        assert man["protocol_id"] == pid
        for name, want in man["artifacts"].items():
            got = sha256(d / name)
            assert got == want, f"{pid}/{name}: 副本 {got[:12]} ≠ 协议清单 {want[:12]}"


def test_没有答案面混进协议树():
    """协议工件按设计**不含任何一道题的答案**（三份 MANIFEST 的 `_what_this_is` 都这么写）。
    这里不信那句话，用执行面那道门现扫一遍。"""
    from runner.f02 import answer_plane_guard as G
    hits = G.scan(ROOT)
    assert not hits, f"genequant/ 里扫出答案面：{hits}"


def test_许可是与本体同一份_Apache_2_0():
    a, b = (ROOT / "LICENSE").read_bytes(), (REPO / "LICENSE").read_bytes()
    assert a == b, "子树的 LICENSE 与本体那份不是同一份（不许另拟一份）"
    assert a.decode("utf-8").splitlines()[0].strip() == "SPDX-License-Identifier: Apache-2.0"


def test_子树的_CITATION_没有留仓库地址占位符():
    """`repository-code` 是本卡要填的字段之一。作者仍是 `<待用户填>`（裁定 ⑳ 明说维持），
    但**地址**这一处不许再留占位 —— 留着的话 `no_clone_url` 的判据就是假的。"""
    txt = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    line = next(x for x in txt.splitlines() if x.startswith("repository-code:"))
    assert repositories()["genequant"] in line, line
    assert "待用户填" not in line and "尚未公开" not in line, line


# ---------------------------------------------------------------- pin 与两个地址

def test_发布清单钉住的就是本树现在这份_MANIFEST():
    """裁定 ㉑ 第 2 条的正身：**「仓库里那份协议工件的 sha 与被钉住的值相等」**。"""
    rm = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    gq = rm["genequant"]
    assert gq["manifest_path"] == "genequant/MANIFEST.json"
    assert gq["manifest_sha256"] == sha256(MANIFEST), (
        "RELEASE_MANIFEST 钉的是上一版的 genequant/MANIFEST.json —— "
        "顺序是 --rebuild 之后再跑 mk_release_manifest.py")
    assert gq["version"] == VERSION
    assert gq["repository"] == repositories()["genequant"]


def test_两个地址在四处一致_一处分叉就红():
    """地址写在四个地方，**判据是它们相等**，不是「某一处长得像个 URL」。"""
    from ops import mk_release_manifest as MR
    repos = repositories()
    rm = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    assert rm["repository"] == repos["genebench"]
    assert rm["genequant"]["repository"] == repos["genequant"]

    cit = (REPO / "CITATION.cff").read_text(encoding="utf-8")
    rc = next(x for x in cit.splitlines() if x.startswith("repository-code:"))
    assert repos["genebench"] in rc, rc
    assert "待用户填" not in rc, "CITATION.cff 的 repository-code 还是占位符"

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert repos["genebench"] in readme, "README 的 clone 步骤没换成真地址"
    assert MR.clone_urls_declared(REPO)[0], MR.clone_urls_declared(REPO)[1]


def test_no_clone_url_已闭合_且判据不是本地_git_remote():
    """本地加一个 remote 既不让外部用户拿到仓库、也不是我们该做的事（那会把内网工作树
    指向外网）。所以判据换成了「地址已定且四处一致」—— 换判据要有**反向**证明。"""
    rm = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    bl = next(b for b in rm["blockers"] if b["id"] == "no_clone_url")
    assert bl["satisfied"] is True, bl["status_now"]
    cfg = (REPO / ".git" / "config").read_text(encoding="utf-8")
    assert "[remote " not in cfg, (
        "本地仓库被加了 remote —— 本卡明确不做这件事（推送由用户执行）")


def test_把地址换回占位符就必须重新挡住发布(tmp_path):
    """**反向判别力**。没有这一条，一个恒真的 `satisfied` 也全绿。"""
    from ops import mk_release_manifest as MR
    (tmp_path / "README.md").write_text("拿一份仓库：git clone <地址：尚未公开>\n", encoding="utf-8")
    (tmp_path / "CITATION.cff").write_text('repository-code: "<待用户填>"\n', encoding="utf-8")
    ok, why = MR.clone_urls_declared(tmp_path)
    assert ok is False and why, "占位符没有被判成占位符"


def test_少了任何一处声明都不算地址已定(tmp_path):
    """四处只写一处不算 —— 外部用户读的是 README，工具读的是 CITATION 与清单。"""
    from ops import mk_release_manifest as MR
    (tmp_path / "README.md").write_text(
        f"git clone {repositories()['genebench']}\n", encoding="utf-8")
    (tmp_path / "CITATION.cff").write_text('repository-code: "<待用户填>"\n', encoding="utf-8")
    ok, why = MR.clone_urls_declared(tmp_path)
    assert ok is False and "CITATION" in why, why


def test_两个地址是_https_且以_git_结尾():
    """ssh 形态（`git@github.com:…`）对没有账号的人 clone 不了；
    少 `.git` 后缀在多数托管上能跑，但 `git ls-remote` 的口径不统一。"""
    for k, u in repositories().items():
        assert u.startswith("https://github.com/"), (k, u)
        assert u.endswith(".git"), (k, u)


if __name__ == "__main__":
    if "--rebuild" in sys.argv:
        w = rebuild()
        print(f"[rebuild] 写了 {len(w)} 件：{w}" if w else "[rebuild] 已是最新，一个字节没动")
        print("下一步：$PY ops/mk_release_manifest.py   # 让 RELEASE_MANIFEST 的 pin 跟上")
    else:
        raise SystemExit("用法：python ops/test_genequant_subtree.py --rebuild（测试用 pytest 跑）")
