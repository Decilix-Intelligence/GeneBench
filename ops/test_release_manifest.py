# -*- coding: utf-8 -*-
"""卡 6.3：`RELEASE_MANIFEST.json` 与它的生成器 `ops/mk_release_manifest.py`。

清单回答的是「今天这个仓库能不能对外发」。这个答案**必须是推导出来的**，
不是写上去的 —— 一个手改就能翻成 `true` 的 `releasable` 字段没有任何价值。

四类判据：

1. **判据字段与工作树一致**（轴 / 许可 / blockers / missing / releasable 现算一遍逐字段比对）；
   `files` 的内容漂移**不判红** —— 发布件里有一批是生成的，每跑一次生成器就换一份 sha，
   把那种漂移写成红会让这条测试对别人的正常工作恒红。它由 `--check` 的退出码 3 报出来；
2. **许可未定时 `releasable` 必须 false**，且**反向**：全部条件满足时必须 true
   （只查一个方向的话，一个恒为 false 的实现也会全绿）。
   2026-09-11 起真仓库本身就落在 true 那一侧（五条 blocker 全闭合），
   于是假仓库那一组测的是 false 方向，真仓库那一条测的是 true 方向；
3. **清单里每个文件都存在**；不存在的进 `missing` 并让 `releasable` 变 false；
4. **缺件不静默**：`missing` 里的每一条都真的不在工作树上，且它在 `files` 里的 `sha256` 是 null。

第 2 条的两个方向用**造出来的假仓库**跑，不改真仓库：一个全都满足、一个只把许可翻回 pending。
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

from ops import mk_release_manifest as MR                      # noqa: E402

MANIFEST = REPO / "RELEASE_MANIFEST.json"


def loaded() -> dict:
    assert MANIFEST.is_file(), (
        f"{MANIFEST} 不存在 —— 先跑 `python ops/mk_release_manifest.py`")
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ 1. 与工作树一致

def test_the_judgement_sections_match_the_worktree():
    """**判据字段**（轴 / 许可 / blockers / missing / releasable）必须与现算的一致。

    `files` 不在这一条里：`ops/reports/v1_0_readiness.md` 这类**生成件**每跑一次生成器
    就换一份 sha，把它算进「不一致」会让这条测试对别人的正常工作恒红 ——
    那种红没有信息量。内容漂移由 `mk_release_manifest.py --check` 报（退出 3），
    与 `ops/freeze_v10.py` 区分「致命漂移」与「输入已变、题面未变」是同一条纪律。
    """
    fatal, _ = MR.classify_drift(MR.build(), loaded())
    assert not fatal, (
        f"发布清单的判据字段与工作树不符（{fatal}）—— **「能不能发」的答案变了**，"
        f"重跑 `python ops/mk_release_manifest.py` 并复核")


def test_every_recorded_sha_of_a_handwritten_item_is_the_real_one():
    """逐件重算 sha256。**清单的全部价值就在这一条上。**

    生成件（`MR.VOLATILE_ITEMS`）只核「文件在、sha 是 64 位十六进制」——
    它们的内容会随生成器重跑而变，那不是清单在撒谎。
    """
    bad = []
    for rel, rec in loaded()["files"].items():
        p = REPO / rel
        if rec["sha256"] is None:
            continue
        if not p.is_file():
            bad.append(f"{rel}：清单里有 sha，文件却不在")
            continue
        if len(rec["sha256"]) != 64 or not all(c in "0123456789abcdef" for c in rec["sha256"]):
            bad.append(f"{rel}：sha 不是 64 位十六进制")
            continue
        if rel in MR.VOLATILE_ITEMS:
            continue
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != rec["sha256"]:
            bad.append(f"{rel}：清单 {rec['sha256'][:12]}… ≠ 实际 {got[:12]}…（**手写件**）")
    assert not bad, "发布件的校验和对不上：\n  " + "\n  ".join(bad)


def test_volatile_items_are_really_generated_ones():
    """**豁免名单不许当垃圾桶**：每一条都得真的在 `RELEASE_ITEMS` 里，且真的存在。

    没有这一条的话，往 `VOLATILE_ITEMS` 里塞一个手写件就能让上面那条闭嘴。
    """
    declared = {rel for items in MR.RELEASE_ITEMS.values() for rel in items}
    stray = sorted(MR.VOLATILE_ITEMS - declared)
    assert not stray, f"VOLATILE_ITEMS 里有不在发布清单里的条目：{stray}"
    gone = sorted(v for v in MR.VOLATILE_ITEMS if not (REPO / v).is_file())
    assert not gone, f"VOLATILE_ITEMS 里有不存在的文件（删掉它，别留着当摆设）：{gone}"


def test_drift_classifier_separates_a_judgement_change_from_a_content_refresh():
    """**判别力**：两类漂移必须被分开，否则「不一样」这三个字没有信息量。"""
    base = {"axes": {"set_version": "1.0.13"}, "releasable": False,
            "files": {"a.md": {"sha256": "0" * 64}}}
    same = json.loads(json.dumps(base))
    assert MR.classify_drift(base, same) == ([], [])

    refreshed = json.loads(json.dumps(base))
    refreshed["files"]["a.md"]["sha256"] = "1" * 64
    fatal, drift = MR.classify_drift(refreshed, base)
    assert fatal == [] and drift == ["a.md"], "内容重生成被误判成判据变更"

    judged = json.loads(json.dumps(base))
    judged["releasable"] = True
    fatal, drift = MR.classify_drift(judged, base)
    assert "releasable" in fatal and drift == [], "判据变更没有被判致命"


# ------------------------------------------------------------------ 2. 缺件不静默

def test_missing_files_are_listed_and_block_the_release():
    m = loaded()
    for rel in m["missing"]:
        assert not (REPO / rel).is_file(), (
            f"{rel} 在 missing 里，实际却存在 —— 清单在撒谎（重新生成一次）")
        assert m["files"][rel]["sha256"] is None, f"{rel} 既在 missing 里又有 sha"
    if m["missing"]:
        assert m["releasable"] is False, "有缺件却说可以发布"


def test_the_three_frozen_artifacts_are_still_declared_missing_or_present_consistently():
    """`PUBLIC_FROZEN_ARTIFACTS` 是 gold 的**定义面**，少了它们复现不了 τ。

    这一条不假设「今天缺三件」（补齐了就该绿）；它只要求
    **声明与事实一致**，且缺件时 blocker 不许是 satisfied。
    """
    m = loaded()
    declared = set(MR.frozen_artifacts())
    really_missing = sorted(d for d in declared if not (REPO / d).is_file())
    assert set(m["missing"]) & declared == set(really_missing), (
        "冻结件的缺件清单与事实不符")
    bl = next(b for b in m["blockers"] if b["id"] == "frozen_artifacts_missing")
    assert bl["satisfied"] == (not really_missing)


# ------------------------------------------------------------------ 3. releasable 的两个方向

def _fake_repo(tmp: Path, *, data_license: str, spdx: str, remote: bool,
               drop: tuple[str, ...] = ()) -> Path:
    """造一个**结构上完整**的假仓库：声明的每一件都写一个占位文件。

    真仓库不动。这样才能测「全部满足 ⇒ true」那个方向 —— 真仓库今天满足不了。
    """
    groups = dict(MR.RELEASE_ITEMS)
    groups[MR.FROZEN_GROUP] = MR.frozen_artifacts()
    for items in groups.values():
        for rel in items:
            if rel in drop:
                continue
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"占位：{rel}\n", encoding="utf-8")
    (tmp / "DATA_LICENSE").write_text(data_license, encoding="utf-8")
    (tmp / "LICENSE").write_text(f"SPDX-License-Identifier: {spdx}\n", encoding="utf-8")
    # 两份冻结清单要能被 json 读，且带 reference_root 需要的字段
    (tmp / "ops" / "manifests").mkdir(parents=True, exist_ok=True)
    (tmp / "ops" / "manifests" / "v1.0-smoke.json").write_text(
        json.dumps({"set_version": "1.0.13", "root": "0" * 64, "counts": {"released": 34}}),
        encoding="utf-8")
    (tmp / "ops" / "manifests" / "v1.0-smoke.reference.json").write_text(
        json.dumps({"set_id": "v1.0-smoke", "reference_version": "r1.0.20",
                    "reference_templates": {}, "reference_modules": {}}),
        encoding="utf-8")
    # **公开任务集轴那一份**（裁定 ①）：`axes` 段从它取 public_set_version / public_set_root。
    # 假仓库里少了它，`build()` 会 FileNotFoundError —— 假仓库的结构要与真仓库同形。
    (tmp / "ops" / "manifests" / "v1.0-smoke-public.json").write_text(
        json.dumps({"set_id": "v1.0-smoke-public", "set_version": "p1.0.0",
                    "root": "1" * 64, "channel": "public", "counts": {"released": 34}}),
        encoding="utf-8")
    git = tmp / ".git"
    git.mkdir(exist_ok=True)
    (git / "config").write_text(
        '[core]\n\trepositoryformatversion = 0\n'
        + ('[remote "origin"]\n\turl = https://example.invalid/genebench.git\n' if remote else ""),
        encoding="utf-8")
    return tmp


GRANTED = "# 数据许可\n\n**状态：`granted`**\n\n原文见 ops/terms/baostock/permission/。\n"
PENDING = "# 数据许可\n\n**状态：`pending_license_text`**\n\n原文待入库。\n"


def test_everything_satisfied_makes_it_releasable(tmp_path):
    """**反向判别力**：条件全满足时必须 true。没有这一条，恒 false 的实现也全绿。"""
    r = _fake_repo(tmp_path, data_license=GRANTED, spdx="Apache-2.0", remote=True)
    m = MR.build(r)
    assert m["missing"] == [], m["missing"]
    assert [b["id"] for b in m["blockers"] if not b["satisfied"]] == []
    assert m["releasable"] is True


@pytest.mark.parametrize("kw,blocker", [
    ({"data_license": PENDING}, "data_license_text"),
    ({"spdx": "<待定>"}, "code_license_undecided"),
    ({"remote": False}, "no_clone_url"),
    ({"drop": ("ops/data_cards/README.md",)}, None),
])
def test_each_condition_alone_blocks_the_release(tmp_path, kw, blocker):
    """逐条单独翻回去，`releasable` 都必须变 false —— **一条一条查，不合并**。"""
    base = dict(data_license=GRANTED, spdx="Apache-2.0", remote=True)
    base.update(kw)
    m = MR.build(_fake_repo(tmp_path, **base))
    assert m["releasable"] is False, f"只翻了 {kw}，仍然说可以发布"
    if blocker:
        bl = next(b for b in m["blockers"] if b["id"] == blocker)
        assert bl["satisfied"] is False
    else:
        assert m["missing"], "删了一个发布件却没进 missing"


def test_release_is_possible_today_and_says_on_what(tmp_path):
    """真仓库今天**可发布**，而且每一条闭合都说得出判据。

    2026-09-11（卡 F3）：原文是「今天**不**可发布，而且说得出是哪几条」，
    并在正文里写明「如果挡发布的事真的闭合了，把这条改成断言 true，
    并在 ops/tickets_inbox/ 里留一条记录」—— 五条 blocker 最后一条
    （`data_license_text`）随裁定 ⑨ 闭合，记录在 `ops/tickets_inbox/F3.md`。

    **翻过来之后这条测试要钉的东西没变**：`releasable` 必须是**推导**出来的。
    所以正反两面一起钉 —— 既要 true，也要「没有任何一条未闭合、没有任何缺件」，
    还要每条 blocker 仍然写得出闭合判据。一个恒 true 的实现过不了第二、三句。
    """
    m = loaded()
    open_ = [b["id"] for b in m["blockers"] if not b["satisfied"]]
    assert m["releasable"] is True, (
        f"真仓库被判成不可发布 —— 未闭合：{open_}，缺件：{m['missing']}。"
        f"如果这是真的（有 blocker 被重新打开、或发布件缺了），"
        f"把这条测试翻回「断言 false」，别改生成器去迁就它")
    assert not open_, f"releasable=true 却还有未闭合的 blocker：{open_}"
    assert not m["missing"], f"releasable=true 却有缺件：{m['missing']}"
    for b in m["blockers"]:
        assert b["closes_when"], f"{b['id']} 没写「怎样才算闭合」"
        assert "内部票据" not in b["closes_when"], (
            f"{b['id']} 的闭合条件写成了「见某某内部票据」—— 外部用户读不到票据")


def test_the_grant_and_the_official_text_are_two_separate_facts(tmp_path):
    """**授权**与**正文**是两件事，清单里必须分两个字段记（裁定 ⑨）。

    旧实现写的是 `text_in_repo = (state == "granted")`：状态一翻，
    这个字段就跟着说「正文在库」—— 而它是清单里唯一回答「有没有文件可查」的地方。
    判别力就在这里：**同一个 `granted` 状态**下，目录空与不空必须读出不同的值。
    """
    m = loaded()
    assert m["license"]["data"]["state"] == "granted"
    assert m["license"]["data"]["grant_summary"], "授权摘要是空的"

    d = REPO.joinpath(*MR.LICENSE_TEXT_DIR)
    really = d.is_dir() and any(d.iterdir())
    assert m["license"]["data"]["official_text_in_repo"] is really, (
        f"清单说正文{'在' if m['license']['data']['official_text_in_repo'] else '不在'}库，"
        f"而 {d} 的事实相反")

    # 反向：造两棵只差一个文件的树，同一个 granted 状态下必须读出不同的值
    empty = tmp_path / "empty"
    (empty.joinpath(*MR.LICENSE_TEXT_DIR)).mkdir(parents=True)
    assert MR.official_license_text_in_repo(empty) is False
    filled = tmp_path / "filled"
    dd = filled.joinpath(*MR.LICENSE_TEXT_DIR)
    dd.mkdir(parents=True)
    (dd / "permission.pdf").write_bytes(b"%PDF-1.4\n")
    assert MR.official_license_text_in_repo(filled) is True, (
        "正文放进去了还说不在 —— 这个字段就白设了")


# ------------------------------------------------------------------ 4. 轴与许可

def test_axes_match_the_frozen_manifests():
    m, ts = loaded(), json.loads(
        (REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    rf = json.loads(
        (REPO / "ops" / "manifests" / "v1.0-smoke.reference.json").read_text(encoding="utf-8"))
    assert m["axes"]["set_version"] == ts["set_version"]
    assert m["axes"]["reference_version"] == rf["reference_version"]
    assert m["axes"]["channels"] == ["private", "public"]


def test_license_states_agree_with_the_files():
    m = loaded()
    assert m["license"]["data"]["state"] == MR.data_license_state()
    assert m["license"]["code"]["spdx"] == MR.code_license_id()


def test_data_license_states_do_not_fork_from_test_env():
    """状态字面量与 `ops/test_env.py::LICENSE_STATES` **同源，值不许分叉**。

    分叉的表现是两处各说各话，而读文件的人会信错的那个。
    """
    src = (REPO / "ops" / "test_env.py").read_text(encoding="utf-8")
    for s in MR.LICENSE_STATES:
        assert f'"{s}"' in src, f"{s!r} 在 ops/test_env.py 里找不到 —— 两处的状态集分叉了"


# ------------------------------------------------------------------ 5. CHANGELOG

def test_changelog_is_rendered_not_handwritten():
    ch = REPO / "CHANGELOG.md"
    assert ch.is_file(), "缺 CHANGELOG.md"
    on_disk = ch.read_text(encoding="utf-8")
    assert on_disk == MR.render_changelog(), (
        "CHANGELOG.md 与渲染结果不符 —— 它是生成的，改记录要去改 "
        "ops/freeze_v10.py 的 REVISIONS / REFERENCE_REVISIONS，"
        "然后 `python ops/mk_release_manifest.py --write-changelog`")


def test_changelog_covers_both_axes_and_loses_nothing():
    task, ref = MR.split_revisions()
    from ops import freeze_v10 as F
    assert len(task) + len(ref) == len(F.REVISIONS) + len(F.REFERENCE_REVISIONS), (
        "分轴时丢了记录 —— 渲染器少印一条，就等于把一次「为什么不可比」的答案丢了")
    body = MR.render_changelog()
    for r in list(F.REVISIONS) + list(F.REFERENCE_REVISIONS):
        assert f"`{r['version']}`" in body, f"CHANGELOG 里没有 {r['version']}"


def test_axes_里有公开轴的版本号与根(tmp_path):
    """裁定 ①：公开通道有**自己的**任务集轴。`channels` 里列着 public 而 `axes` 只登记私有
    版本号与根的话，`comparable_iff:"四条轴全部相同"` 在公开通道上没有可比对的取值 ——
    公开树的持有者答不出「我这份是哪条公开轴」（红队最终轮 major 6）。"""
    r = _fake_repo(tmp_path, data_license=GRANTED, spdx="Apache-2.0", remote=True)
    ax = MR.build(r)["axes"]
    assert ax["public_set_version"] == "p1.0.0"
    assert ax["public_set_root"] == "1" * 64
    assert ax["public_set_root"] != ax["set_root"], "两条轴的根不该相同 —— 夹具真值只进公开根"


def test_真仓库的公开轴与freeze现值一致():
    """`axes` 里的公开轴不是手抄的：它必须等于 `ops/freeze_v10.py` 的常量与现算根。"""
    import json as _json
    from ops import freeze_v10 as FZ
    ax = MR.build(MR._REPO)["axes"]
    pm = _json.loads((MR._REPO / "ops" / "manifests" / "v1.0-smoke-public.json").read_text(encoding="utf-8"))
    assert ax["public_set_version"] == FZ.SET_VERSION_PUBLIC == pm["set_version"]
    assert ax["public_set_root"] == FZ.manifest_root(pm) == pm["root"]
