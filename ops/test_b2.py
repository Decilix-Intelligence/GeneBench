# -*- coding: utf-8 -*-
"""卡 B2：公开运行物料包（第三个 Release 附件）的定向测试。

判据分三堆：

* **打包器的两道硬门真的会咬** —— 夹具与已冻清单不符、`calibration.json` 与
  `calibration.sha256` 不符，都必须当场抛。这两道门是本包存在的理由：
  「打了一个包，用户解开之后冻结根还是对不上」正是本卡要修的病，
  不能让修法本身重犯一次。
* **不许带出去的东西真的带不出去** —— 私有题集 / 私有快照 / 记忆探针钥匙 /
  凭据形态。反过来：`solution/` 与 `gold/` **必须放行**（有意带答案面，见数据卡 §5）。
* **落点与登记** —— 落点不在会同步到执行面的路径上；附件登记在
  `ops/release/attachments.json` 里，`download_url` 已于 2026-09-13 回填（卡 Q 上传）。

不在这里跑的：真打包（2.7 s / 42 MB，属重活，走 flock）与干净 clone 判据
（`$GB/scratch/B2/cleanroom.sh`，原始输出记在 `ops/reports/public_runtime_material.md` §8）。
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

import genebench_config as cfg
from ops import freeze_v10 as F
from ops.release import pack_public_runtime as PR

REPO = pathlib.Path(__file__).resolve().parents[1]

#: 冻结值。**写在这里是有意的**：本卡的判据就是「现算根回到这个值」，
#: 从清单里读一遍等于用被测对象证明被测对象（`pin.py` 批判过的 F7 形态）。
PUBLIC_ROOT_FROZEN = "3e5ab441a991c4115a6c0fb988715f583e22ee303f582f1302fd3197fb183538"


# ---------------------------------------------------------------- 两道硬门

def test_fixtures_gate_passes_on_the_real_tree():
    """18 道题 / 30 件夹具，现算与已冻清单逐件相同。"""
    fx = PR.assert_fixtures_match_frozen()
    assert fx["tasks"] == 18
    assert fx["files"] == 30
    assert fx["set_version"] == "p1.0.0"
    assert fx["public_root_recorded"] == PUBLIC_ROOT_FROZEN


def test_fixtures_gate_bites_when_the_tree_is_empty(tmp_path):
    """门要会咬：题集空了就拒绝打包，而不是打出一个让用户对不上根的包。"""
    (tmp_path / "reference" / "tasks" / "public" / F.PUBLIC_SET_ID).mkdir(parents=True)
    with pytest.raises(PR.RuntimePackError) as e:
        PR.assert_fixtures_match_frozen(gb_root=tmp_path)
    assert "只在清单" in str(e.value)


def test_fixtures_gate_bites_when_one_fixture_is_missing(tmp_path):
    """少一件也要咬 —— 这正是外部验收撞到的形态（整段缺 / 少几件，表现相同）。"""
    src = PR.tasks_source()
    dst = tmp_path / "reference" / "tasks" / "public" / F.PUBLIC_SET_ID
    dst.mkdir(parents=True)
    # 只搬 18 道带 inputs 的题的 task.yaml + 夹具，然后故意漏掉其中一件
    man = json.loads(F.OUT_PUBLIC.read_text(encoding="utf-8"))["channel_fixtures"]
    dropped = None
    for tid, files in man.items():
        (dst / tid).mkdir()
        (dst / tid / "task.yaml").write_bytes((src / tid / "task.yaml").read_bytes())
        for rel in files:
            if dropped is None:
                dropped = f"{tid}/{rel}"
                continue
            p = dst / tid / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((src / tid / rel).read_bytes())
    assert dropped is not None
    with pytest.raises(PR.RuntimePackError):
        PR.assert_fixtures_match_frozen(gb_root=tmp_path)


def test_calibration_gate_passes_and_reports_the_public_tau():
    c = PR.assert_calibration_intact()
    assert c["sha256"] == (cfg.snapshot_root("public") / "calibration.sha256"
                           ).read_text(encoding="utf-8").split()[0]
    # 公开 τ ≠ 私有 τ：两份是各自算的，不是把私有那份复制过来改了个名。
    #
    # **N-809**：私有标定 `$GENEBENCH_ROOT/snapshots/v1/calibration.json` **不随包发**
    # —— 三件附件里一件都没有（公开那份在 `snapshots/public_v1/`）。这一行原来无条件读它，
    # 于是外部用户**正确落位之后**这条仍然 `FileNotFoundError`：判据悄悄取决于
    # 「跑它的是不是发布方那台机器」，而这件事在内网永远看不见（与 N-770 同形）。
    # 私有 τ 的值**不往公开树里钉**（它是私有通道的标定），所以改成：读不到就 skip，
    # 读得到（= 发布方那台）就照旧判。上面两条断言是外部真正跑得动的那一半，
    # 它们在 skip 之前**已经跑过了** —— 这一条不会退化成整条恒绿。
    priv_path = cfg.SNAPSHOTS_V1 / "calibration.json"
    if not priv_path.is_file():
        pytest.skip(f"私有标定不随包发，只有发布方那台有：{priv_path}")
    priv = json.loads(priv_path.read_text(encoding="utf-8"))
    assert c["tau"] != priv["tau"]["value"]


def test_calibration_gate_bites_on_sha_mismatch(tmp_path):
    ss = tmp_path / "snapshots" / cfg.PUBLIC_VERSION
    ss.mkdir(parents=True)
    (ss / "calibration.json").write_text('{"tau": {"value": 1.0}}', encoding="utf-8")
    (ss / "calibration.sha256").write_text("0" * 64 + "  calibration.json\n", encoding="utf-8")
    with pytest.raises(PR.RuntimePackError) as e:
        PR.assert_calibration_intact(gb_root=tmp_path)
    assert "calibration.sha256" in str(e.value)


# ---------------------------------------------------------------- 带什么 / 不带什么

@pytest.mark.parametrize("arc", [
    "reference/tasks/private/v1.0-smoke/s1-cor-01/task.yaml",
    "snapshots/v1/calibration.json",
    "reference/memory_probe_answers/keys.json",
    "runs_in/m6_public/run-1/run.json",
    "snapshots/public_v1/secrets.env",
    "snapshots/public_v1/.env.local",
    "reference/tasks/public/x/id_ed25519",
    "reference/tasks/public/x/server.pem",
    "reference/tasks/public/x/api.key",
])
def test_forbidden_content_is_refused(arc):
    e = PR.PP.Entry(arc, pathlib.Path("/dev/null"), 0, "0" * 64)
    with pytest.raises(PR.RuntimePackError):
        PR.assert_no_forbidden([e])


@pytest.mark.parametrize("arc", [
    f"reference/tasks/public/{F.PUBLIC_SET_ID}/s2-cor-01/solution/solve.py",
    f"reference/tasks/public/{F.PUBLIC_SET_ID}/s2-cor-01/solution/artifact.json",
    f"reference/tasks/public/{F.PUBLIC_SET_ID}/s2-cor-01/gold/panel.csv",
    f"reference/tasks/public/{F.PUBLIC_SET_ID}/s4-cor-01/scorer.yaml",
    f"snapshots/{cfg.PUBLIC_VERSION}/calibration.json",
    f"snapshots/{cfg.PUBLIC_VERSION}/epsilon/epsilon_dual_daily.json",
])
def test_answer_plane_is_deliberately_allowed(arc):
    """`solution/` / `gold/` / `scorer.yaml` **必须放行** —— 不带就算不出分
    （`scorer/score_run.py:328` 把 `task_dir/work` 当 gold 目录）。
    红线 2 在 v1.0.16 是**容器边界**口径，不是「包里不许有」。"""
    PR.assert_no_forbidden([PR.PP.Entry(arc, pathlib.Path("/dev/null"), 0, "0" * 64)])


def test_no_second_literal_for_the_public_set_id():
    """题集目录名只许有一处定义（`freeze_v10.PUBLIC_SET_ID`）。
    在打包器里再抄一份的表现是「打的是一批、冻的是另一批」（N-605 那个病）。"""
    src = (REPO / "ops" / "release" / "pack_public_runtime.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    assert f'"{F.PUBLIC_SET_ID}"' not in code
    assert F.PUBLIC_SET_ID in str(PR.tasks_source())


def test_tasks_source_follows_gb_root(tmp_path):
    """落点跟着 `$GENEBENCH_ROOT` 走 —— 外部用户的根不是发布方的根。"""
    assert PR.tasks_source(tmp_path) == (
        tmp_path / "reference" / "tasks" / "public" / F.PUBLIC_SET_ID)
    assert PR.snapshot_source(tmp_path) == tmp_path / "snapshots" / cfg.PUBLIC_VERSION


# ---------------------------------------------------------------- 落点与登记

def test_dest_is_not_on_the_exec_plane():
    from ops.release.pack_gold_subset import (
        GoldPackError, assert_dest_is_not_on_the_exec_plane)
    assert_dest_is_not_on_the_exec_plane(PR.dest_default())      # 默认落点必须过
    for bad in ("staging", "runs_in", "scratch/f02_bundle", "release/trees"):
        with pytest.raises(GoldPackError):
            assert_dest_is_not_on_the_exec_plane(cfg.GENEBENCH_ROOT / bad)


def test_attachment_is_registered_and_uploaded():
    """2026-09-13（卡 Q）：本条由 `…_and_not_uploaded` 翻面而来。

    卡 B2 当轮的判据是「本轮不上传，`download_url` 必须是空串」。用户当日裁定把这件
    传上已发布的 Release `v1.0.16`，**状态真的变了**，所以门跟着翻到另一面 ——
    而且比旧判据更严：旧的只查「是不是空串」，新的**逐字比对完整规范地址**
    （tag + 包名），并要求**三件**的地址一件都不许被后来的打包抹掉。
    """
    d = json.loads((REPO / "ops" / "release" / "attachments.json").read_text(encoding="utf-8"))
    by = {a["name"]: a for a in d["attachments"]}
    a = by.get(PR.TARBALL)
    assert a is not None, f"{PR.TARBALL} 没登记进 attachments.json"
    assert a["role"] == "public_runtime_material"
    assert a["axes"]["public_set_root"] == PUBLIC_ROOT_FROZEN
    base = "https://github.com/Decilix-Intelligence/GeneBench/releases/download/v1.0.16"
    assert a["download_url"] == f"{base}/{PR.TARBALL}", (
        "2026-09-13 这件已经传上 Release v1.0.16 —— `download_url` 要回填成规范地址；"
        "重打包不许把它抹回空串")
    # 三件的下载地址**都不许被后来的打包抹掉**
    for name in ("genebench_public_provider_v1.tar.gz",
                 "genebench_public_gold_subset_v1.tar.gz",
                 PR.TARBALL):
        assert by[name]["download_url"] == f"{base}/{name}", f"{name} 的下载地址被抹掉或改坏了"


def test_packed_tarball_matches_its_registration():
    """包在盘上时，字节数与 sha256 必须与登记一致。"""
    tarball = PR.dest_default() / PR.TARBALL
    if not tarball.is_file():
        pytest.skip(f"{tarball} 不在（还没打包）")
    d = json.loads((REPO / "ops" / "release" / "attachments.json").read_text(encoding="utf-8"))
    a = next(x for x in d["attachments"] if x["name"] == PR.TARBALL)
    assert tarball.stat().st_size == a["bytes"]
    assert PR.PP._sha256(tarball) == a["sha256"]


# ---------------------------------------------------------------- tables/manifest.json

def test_public_channel_does_not_need_tables_manifest(monkeypatch):
    """外部验收问过的那一条：公开通道**不需要** `tables/manifest.json`。

    `gateway/backends.default_backend()` 只在**私有**分支才看它
    （`SNAPSHOT_MANIFEST` 恒指 `snapshots/v1/tables/`）；公开通道在上一行
    就无条件返回 `snapshot`。这条断言是为了让下一个人不用再撞一次。
    """
    from gateway import backends as B
    monkeypatch.setenv("GENEBENCH_CHANNEL", "public")
    monkeypatch.delenv("GENEBENCH_GATEWAY_BACKEND", raising=False)
    assert B.default_backend() == "snapshot"
    assert "v1/tables" in str(B.SNAPSHOT_MANIFEST) and "public" not in str(B.SNAPSHOT_MANIFEST)


# ---------------------------------------------------------------- 交付文档

def test_report_and_data_card_carry_the_install_command():
    rep = (REPO / "ops" / "reports" / "public_runtime_material.md").read_text(encoding="utf-8")
    card = (REPO / "ops" / "data_cards" / "public_runtime_v1.md").read_text(encoding="utf-8")
    for t in (rep, card):
        assert "--strip-components=1" in t and "$GENEBENCH_ROOT" in t
        assert PUBLIC_ROOT_FROZEN in t
        assert PR.TARBALL in t
    # 根因必须写明是「git archive 取不到 $GENEBENCH_ROOT 下的物化产物」
    assert "git archive" in rep
    # 不许出现 key 形态的字面量（红线 3 门）
    assert not re.search(r"sk-[A-Za-z0-9]{8,}", rep + card)
