# -*- coding: utf-8 -*-
"""卡 D（裁定 ③⑤）的门。

管四件事：
 ① README §2.1a 给的下载地址与校验和**就是**盘上那两个包的（三处同源：README / `attachments.json` /
    `RELEASE_MANIFEST.release_attachments`）；
 ② 「地址已回填」与「README 还写着没挂上去」**不许同时为真** —— 这是一条双向门：
    谁上传完回填了 `download_url`，就必须同时删掉 README 里那段状态提示，反之亦然；
 ③ 校验命令没把两个包的校验和文件名写混（gold 子集那份**不叫** `SHA256SUMS`）；
 ④ 本卡写的几份文件里没有署名形态字样（裁定 ⑫ 的口径：署名形态删、技术事实留）。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

# 2026-09-13 卡 W2（N-826）：**仓库根从本文件自身位置推导**，与 `conftest.py` 的
# `_REPO_ROOT` 同一套口径。此前这里写死的是**发布方内网路径**，两头都坏：
#  ① 在任何没有那个路径的机器上，下面的模块级 `read_text()` 抛 `FileNotFoundError`，
#     pytest 在 **collection 期整场中断**（`Interrupted: 1 error during collection`），
#     不是一条可读的红；
#  ② 在发布方机器上跑**克隆树**时，这些断言读的是内网那棵树而不是被测的那棵 ——
#     也就是说整套判据对「这棵克隆树对不对」**没有判别力**，绿是假的。
# 这是 D-06 家族「判据悄悄取决于跑它的那台机器」那一支的第六例。
REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
ATTACH = REPO / "ops" / "release" / "attachments.json"
MANIFEST = REPO / "RELEASE_MANIFEST.json"
SCAN = REPO / "ops" / "reports" / "release_scan_publish.md"
PUSH = REPO / "ops" / "reports" / "push_result.md"
#: 打包产物只在数据面那台上有；落点跟着 `$GENEBENCH_ROOT` 走（没设就按仓库的父目录猜），
#: 用它的那条断言本来就有 `p.exists()` 的 skip 保护。
PKG_DIR = Path(os.environ.get("GENEBENCH_ROOT") or REPO.parent) / "release" / "public_v1"

TAG = "v1.0.16"
BASE = f"https://github.com/Decilix-Intelligence/GeneBench/releases/download/{TAG}"
NAMES = ("genebench_public_provider_v1.tar.gz", "genebench_public_gold_subset_v1.tar.gz")
#: README §2.1a 里那段「还没挂上去」的状态提示，靠这句话认
PENDING_TELL = "这两个附件今天还没挂上去"

# 模块级 IO 的存在性保护：缺件时**跳过整个模块**，而不是让 collection 崩掉整场。
if not (README.is_file() and ATTACH.is_file()):
    pytest.skip(f"{README} 或 {ATTACH} 不在 —— 这份门只在仓库树里有意义",
                allow_module_level=True)

RD = README.read_text(encoding="utf-8")
AT = json.loads(ATTACH.read_text(encoding="utf-8"))
ATT_BY_NAME = {a["name"]: a for a in AT["attachments"]}


def section_21a() -> str:
    assert "### 2.1a" in RD, "README 里没有 §2.1a —— 外部用户没有地方拿现成的包"
    return RD.split("### 2.1a", 1)[1].split("\n### ", 1)[0]


# ══════════════════════════════════════════════ ① 三处同源

@pytest.mark.parametrize("name", NAMES)
def test_readme里的校验和与登记表逐字相同(name: str) -> None:
    sha = ATT_BY_NAME[name]["sha256"]
    body = section_21a()
    assert sha in body, (
        f"README §2.1a 里没有 {name} 的 sha256 {sha[:12]}… —— "
        f"重打过包就要同步这里，否则用户的 sha256sum -c 当场红")


@pytest.mark.parametrize("name", NAMES)
def test_readme里的下载地址是规范形式(name: str) -> None:
    assert f"{BASE}/{name}" in RD or (BASE in RD and name in section_21a()), (
        f"README 里找不到 {name} 的下载地址（应为 {BASE}/{name}，允许用变量拼）")


@pytest.mark.parametrize("name", NAMES)
def test_登记表记的字节数与盘上的包一致(name: str) -> None:
    p = PKG_DIR / name
    if not p.exists():
        pytest.skip(f"{p} 不在这台机器上（只有数据面那台有）")
    assert p.stat().st_size == ATT_BY_NAME[name]["bytes"], (
        f"{name} 盘上 {p.stat().st_size} B，登记表记 {ATT_BY_NAME[name]['bytes']} B —— "
        f"有人重打了包却没重跑打包脚本")


@pytest.mark.parametrize("name", NAMES)
def test_清单段与登记表逐字段相同(name: str) -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = {r["name"]: r for r in m["release_attachments"]["attachments"]}
    assert name in rows, f"RELEASE_MANIFEST.release_attachments 里没有 {name}"
    for k in ("bytes", "sha256", "download_url"):
        assert rows[name][k] == ATT_BY_NAME[name][k], (
            f"{name} 的 {k} 在清单与登记表里不一致 —— 回填之后忘了重跑 mk_release_manifest.py")


# ══════════════════════════════════════════════ ② 双向门

def test_地址回填与readme的状态提示必须同进同退() -> None:
    """**这是一条双向门，两个方向都要有牙。**

    上传完回填了 `download_url` 却留着 README 那段「还没挂上去」→ 文档在骗人；
    删了那段提示却没回填 `download_url` → 清单在骗人。任何一边先动都当场红。
    """
    filled = [n for n in NAMES if ATT_BY_NAME[n]["download_url"]]
    pending_note = PENDING_TELL in RD
    if filled and pending_note:
        raise AssertionError(
            f"{filled} 的 download_url 已回填，但 README §2.1a 还写着「{PENDING_TELL}」——"
            f"上传完请把那段引用块删掉")
    if not filled and not pending_note:
        raise AssertionError(
            f"两条 download_url 都还是空串（= 还没上传），但 README §2.1a 里已经没有"
            f"「{PENDING_TELL}」这段提示了 —— 那会让读者以为地址现在就能用")


def test_没上传的时候清单的uploaded计数是零() -> None:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    sec = m["release_attachments"]
    n = sum(1 for a in AT["attachments"] if a["download_url"])
    assert sec["uploaded"] == n, (
        f"清单记 uploaded={sec['uploaded']}，登记表里有地址的是 {n} 条 —— 重跑 mk_release_manifest.py")


# ══════════════════════════════════════════════ ③ 两个校验和文件不同名

def test_校验命令没把两个包的校验和文件名写混() -> None:
    body = section_21a()
    assert "gold_subset_SHA256SUMS" in body, (
        "README §2.1a 的校验命令里没有 gold_subset_SHA256SUMS —— "
        "gold 子集包的顶层校验和文件**不叫** SHA256SUMS，两个包解到同一个目录下会重名互覆")
    # gold 那一行必须用带前缀的名字
    gold_lines = [l for l in body.splitlines() if "gold_subset_v1 " in l or "gold_subset_v1/" in l]
    bad = [l for l in gold_lines if re.search(r"sha256sum -c SHA256SUMS(?!\.release)", l)]
    assert not bad, f"gold 子集那一行用了 SHA256SUMS 而不是 gold_subset_SHA256SUMS：{bad}"


def test_包体校验那一段两个sha都在() -> None:
    body = section_21a()
    for name in NAMES:
        line = f"{ATT_BY_NAME[name]['sha256']}  {name}"
        assert line in body, (
            f"README §2.1a 的 SHA256SUMS.release 里缺一行：`{line[:20]}…  {name}` —— "
            f"少一行用户就只校验了一个包")


# ══════════════════════════════════════════════ ④ 署名形态

_SIG = [
    r"Co-Authored-By:",
    r"(?i)generated\s+with\s+\[",
    r"🤖",
    r"noreply@anthropic\.com",
    r"(?i)written\s+by\s+claude",
]


@pytest.mark.parametrize("p", [README, SCAN, PUSH, REPO / "ops" / "tickets_inbox" / "D.md"],
                         ids=lambda p: p.name)
def test_本卡写的文件里没有署名形态(p: Path) -> None:
    if not p.exists():
        pytest.skip(f"{p} 不在")
    txt = p.read_text(encoding="utf-8")
    hits = [pat for pat in _SIG if re.search(pat, txt)]
    assert not hits, f"{p.name} 里有署名形态：{hits}（裁定 ⑫：署名形态一律删，技术事实保留）"


# ══════════════════════════════════════════════ 报告在不在、说的是不是实话

def test_上传前扫描报告在并且记着六项全零() -> None:
    assert SCAN.exists(), "ops/reports/release_scan_publish.md 不在 —— 上传前扫描没有留证"
    t = SCAN.read_text(encoding="utf-8")
    assert "PASS = true" in t, "扫描报告里没有 PASS = true"
    for tell in ("csi1000", "逐行", "凭据", "memory_probe_answers", "answer_plane_guard"):
        assert tell in t, f"扫描报告里没提 {tell} —— 六项少查了一项"


def test_推送报告没有声称release已经建好() -> None:
    t = PUSH.read_text(encoding="utf-8")
    filled = any(a["download_url"] for a in AT["attachments"])
    if not filled:
        assert "BLOCKED" in t, (
            "附件还没上传，push_result.md 却没有把它记成 BLOCKED —— "
            "一份说「传完了」的推送报告比没有报告坏")
