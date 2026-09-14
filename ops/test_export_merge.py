#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 Y2 的测试：**结果导出 / 合并**（裁定 ⑮）与 **版本锁**（裁定 ⑰）。

两条是裁定点名要的：

* `test_两台机器导出合并之后条数相加且一条都没被覆盖`
* `test_轴不一致的包合并时当场拒并列出分歧`（`set_version` 不同 → 退非零）

其余几条守着「这两条不是靠巧合绿的」：机器标识真的进了 `run_id`、`job_id` 与
`run_id` 同源、旧记录的主键**一个字节没变**、包被改过一个字节就拒、
以及反向门（轴一致时必须能合进去 —— 否则上面那条「拒」可以靠恒拒拿绿）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                              # noqa: E402
from ops import genebench_cli as CLI                        # noqa: E402
from ops import joblist as JL                               # noqa: E402
from ops import results_db as DB                            # noqa: E402
from runner import inject as INJ                            # noqa: E402

#: 一份**假装置**的四条轴。测试不去动真的冻结清单 —— 那是 A 卡的东西，
#: 而这里要判的是「比对与拒绝」这段逻辑，不是「轴从哪读」。
#: 「轴从哪读」另有 `test_axes_now_读的就是盘上那两份冻结清单` 守着。
FAKE_AXES = {
    "set_version": "9.9.9", "set_root": "a" * 64,
    "reference_version": "r9.9.9", "reference_root": "b" * 64,
    "channels": list(cfg.CHANNELS),
    "code_set_version": "9.9.9", "code_reference_version": "r9.9.9",
    "protocol_version_in_repo": "geneprotocol_v1@deadbeefcafe",
}


def _record(*, machine: str, batch: str, task: str = "s1-cor-01", arm: str = "open",
            config: str = "cfg-x", seed: int = 1, axes: dict | None = None,
            score: float = 1.0) -> dict:
    ax = axes or FAKE_AXES
    rid = INJ.run_id(task, arm, config, seed, machine=machine)
    rec = {
        "batch": batch, "task_id": task, "config_id": config, "arm": arm, "seed": seed,
        "seq": seed, "run_id": rid, "machine_id": machine, "track": "main",
        "set_version": ax["set_version"], "reference_version": ax["reference_version"],
        "protocol_version": DB.NO_PROTOCOL, "channel": "private",
        "l3_score": score,
    }
    for k in DB.RESULT_FIELDS:
        rec.setdefault(k, None)
    rec["validity"] = "valid"
    rec["run_status"] = "ok"
    return rec


@pytest.fixture()
def fake_install(tmp_path, monkeypatch):
    """把「本装置的四条轴」按死成 FAKE_AXES，**并给它配一份同值的发布清单**。

    后半句是必须的：`CLI.main` 的每个子命令入口都跑版本锁（⑰），不给假装置配一份对得上的
    清单的话，下面每一条测试都会在版本锁上退 3 —— 于是「合并因为轴不一致被拒」那一条
    会**因为另一个原因**拿到同一个退出码，绿得没有意义。版本锁自己的判别力由
    `test_改一条轴入口就拒` 守着。
    """
    monkeypatch.setattr(CLI, "axes_now", lambda repo=None: dict(FAKE_AXES))
    man = tmp_path / "FAKE_RELEASE_MANIFEST.json"
    man.write_text(json.dumps({"axes": {f: FAKE_AXES[f] for f in CLI.LOCK_FIELDS}},
                              ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv(CLI.RELEASE_MANIFEST_ENV, str(man))
    return dict(FAKE_AXES)


def _export(records, out_dir: Path, db_root: Path, *, machine: str) -> Path:
    """把 `records` 收进一个**独立的库**，再从那个库导一个包出来。"""
    DB.ingest(records, root=db_root)
    r = CLI.build_package(DB.load(db_root), out_dir=out_dir,
                          machine={"machine_id": machine, "hostname": machine,
                                   "fingerprint": machine[-8:], "fingerprint_source": "test",
                                   "algo": "test"},
                          selection={"filters": {}, "db_root": str(db_root)})
    return Path(r["package"])


# --------------------------------------------------------------- ⑮ 两条点名的测试

def test_两台机器导出合并之后条数相加且一条都没被覆盖(tmp_path, fake_install):
    """裁定 ⑮ 点名的第一条：两台机器导出、合并**无冲突**。"""
    a_db, b_db, local = tmp_path / "a", tmp_path / "b", tmp_path / "local"
    # 同一份清单（同 batch / 同题 / 同臂 / 同种子）在两台机器上各跑一遍 —— 这正是
    # 不带机器标识时会撞的那一种：run_id 逐字相同、内容不同。
    a_recs = [_record(machine="alpha-11111111", batch="shared", seed=s, score=0.1 * s) for s in (1, 2)]
    b_recs = [_record(machine="beta-22222222", batch="shared", seed=s, score=0.9 * s) for s in (1, 2)]
    assert {r["run_id"] for r in a_recs} & {r["run_id"] for r in b_recs} == set(), \
        "run_id 里没有机器段的话这两组就撞了 —— 那才是这条测试要防的东西"

    pkg_a = _export(a_recs, tmp_path / "out_a", a_db, machine="alpha-11111111")
    pkg_b = _export(b_recs, tmp_path / "out_b", b_db, machine="beta-22222222")

    ra = CLI.merge(pkg_a, db_root=local)
    rb = CLI.merge(pkg_b, db_root=local)
    assert (ra["added"], rb["added"]) == (2, 2)
    rows = DB.load(local)
    assert len(rows) == 4, "条数要相加"
    assert {DB.machine_of(r) for r in rows} == {"alpha-11111111", "beta-22222222"}
    #: 没被覆盖：两边各自的分数都还在，逐条对得上。
    by_key = {DB.key_of(r): r["l3_score"] for r in rows}
    for src in (a_recs, b_recs):
        for r in src:
            assert by_key[DB.key_of(r)] == r["l3_score"]

    #: 幂等：再合一遍，一条都不新增、也不报错。
    again = CLI.merge(pkg_a, db_root=local)
    assert (again["added"], again["duplicate"]) == (0, 2)
    assert len(DB.load(local)) == 4


def test_轴不一致的包合并时当场拒并列出分歧(tmp_path, fake_install, capsys):
    """裁定 ⑮ 点名的第二条：造一个 `set_version` 不同的包 → **退非零并列出分歧**。"""
    other = dict(FAKE_AXES, set_version="8.8.8", set_root="c" * 64)
    recs = [_record(machine="gamma-33333333", batch="other", seed=1, axes=other)]
    # 导出那台机器的装置轴就是 8.8.8（对它自己是常规包）。
    from unittest import mock
    with mock.patch.object(CLI, "axes_now", lambda repo=None: dict(other)):
        pkg = _export(recs, tmp_path / "out", tmp_path / "otherdb", machine="gamma-33333333")

    local = tmp_path / "local"
    with pytest.raises(CLI.AxisError) as e:
        CLI.merge(pkg, db_root=local)
    axes = [d["axis"] for d in e.value.divergences]
    assert "set_version" in axes and "set_root" in axes, axes
    assert "8.8.8" in str(e.value) and "9.9.9" in str(e.value), "分歧要把两边的值都印出来"
    assert not DB.results_path(local).exists(), "被拒时一条都不许写进库"

    #: 先确认**入口版本锁是绿的**（fake_install 配了对得上的清单）——
    #: 否则下面这个 3 是版本锁给的，而不是合并的四轴校验给的。
    assert CLI.check_release_axes()["ok"]
    rc = CLI.main(["--db", str(local), "merge", str(pkg)])
    assert rc == 3, "轴不一致 = 退出码 3"
    assert not DB.results_path(local).exists()


def test_dry跑完库里一条都没多(tmp_path, fake_install):
    """走查（2026-09-11）抓到的真 bug：`main()` 漏了 `dry=a.dry`，`merge --dry` 真的写了库，
    还照旧打「新增 N 条」。「只看看」把东西写进去，是这条链路上最贵的一种错。"""
    recs = [_record(machine="iota-99999999", batch="b", seed=s) for s in (1, 2)]
    pkg = _export(recs, tmp_path / "out", tmp_path / "src", machine="iota-99999999")
    local = tmp_path / "local"
    assert CLI.main(["--db", str(local), "merge", str(pkg), "--dry"]) == 0
    assert not DB.results_path(local).exists(), "--dry 不许落一个字节"
    #: 试算报的数要与真合的数对得上（否则「试算」没有意义）。
    assert CLI.merge(pkg, db_root=local, dry=True)["would_add"] == 2
    assert CLI.main(["--db", str(local), "merge", str(pkg)]) == 0
    assert len(DB.load(local)) == 2
    #: `--db` 写在子命令**后面**也要认（走查里按手册这么敲，argparse 当场拒）。
    other = tmp_path / "other"
    assert CLI.main(["merge", str(pkg), "--db", str(other)]) == 0
    assert len(DB.load(other)) == 2


def test_轴一致时合得进去(tmp_path, fake_install):
    """反向门：上一条的「拒」不能靠恒拒拿绿。"""
    recs = [_record(machine="delta-44444444", batch="ok", seed=1)]
    pkg = _export(recs, tmp_path / "out", tmp_path / "src", machine="delta-44444444")
    local = tmp_path / "local"
    assert CLI.main(["--db", str(local), "merge", str(pkg)]) == 0
    assert len(DB.load(local)) == 1


# --------------------------------------------------------------- 结果包本身

def test_导出的每条结果都带着四条轴(tmp_path, fake_install):
    """⑰ 的后半句。包里逐条检查 —— MANIFEST 写了不算，记录里真有才算。"""
    recs = [_record(machine="eps-55555555", batch="b", seed=s) for s in (1, 2)]
    pkg = _export(recs, tmp_path / "out", tmp_path / "src", machine="eps-55555555")
    with tarfile.open(pkg) as tf:
        names = tf.getnames()
        body = tf.extractfile([n for n in names if n.endswith("results.jsonl")][0]).read()
        man = json.loads(tf.extractfile([n for n in names if n.endswith("MANIFEST.json")][0]).read())
    rows = [json.loads(x) for x in body.decode("utf-8").splitlines() if x.strip()]
    assert len(rows) == 2
    for r in rows:
        for ax in DB.AXES:
            assert r.get(ax) not in (None, ""), f"{ax} 没带出去"
    assert man["axes"]["set_version"] == FAKE_AXES["set_version"]
    assert man["machine"]["machine_id"] == "eps-55555555"
    assert sorted(man["counts"]["by_batch"]) == ["b"]
    #: run 清单：一条 run 一行，带机器标识与四条轴。
    with tarfile.open(pkg) as tf:
        runs = json.loads(tf.extractfile([n for n in tf.getnames() if n.endswith("runs.json")][0]).read())
    assert len(runs) == 2 and {x["machine_id"] for x in runs} == {"eps-55555555"}
    assert all(set(x["axes"]) == set(DB.AXES) for x in runs)


def test_包被改过一个字节就拒(tmp_path, fake_install):
    recs = [_record(machine="zeta-66666666", batch="b", seed=1)]
    pkg = _export(recs, tmp_path / "out", tmp_path / "src", machine="zeta-66666666")
    raw = bytearray(pkg.read_bytes())
    raw[-40] ^= 0xFF                                        # 动 gzip 流里的一个字节
    pkg.write_bytes(bytes(raw))
    local = tmp_path / "local"
    rc = CLI.main(["--db", str(local), "merge", str(pkg)])
    assert rc == 5, "完整性坏了 = 退出码 5"
    assert not DB.results_path(local).exists()


def test_同主键内容不同时报错不覆盖(tmp_path, fake_install):
    """两台机器**同一个 machine_id** 却给出内容不同的同一条 run —— 结果库的老纪律，
    合并这条路上也必须成立（退 4，一条都不写）。"""
    a = [_record(machine="eta-77777777", batch="b", seed=1, score=0.1)]
    b = [_record(machine="eta-77777777", batch="b", seed=1, score=0.9)]
    pkg_a = _export(a, tmp_path / "oa", tmp_path / "da", machine="eta-77777777")
    pkg_b = _export(b, tmp_path / "ob", tmp_path / "db", machine="eta-77777777")
    local = tmp_path / "local"
    assert CLI.main(["--db", str(local), "merge", str(pkg_a)]) == 0
    assert CLI.main(["--db", str(local), "merge", str(pkg_b)]) == 4
    rows = DB.load(local)
    assert len(rows) == 1 and rows[0]["l3_score"] == 0.1, "先到的那条不许被覆盖"


def test_归档包要两端都显式说出口(tmp_path, fake_install):
    """跨版的读数：导出端要 `--archive`，合并端也要 —— 一端说了不算。"""
    old = dict(FAKE_AXES, set_version="1.0.7", reference_version="r1.0.8")
    recs = [_record(machine="theta-88888888", batch="old", seed=1, axes=old)]
    DB.ingest(recs, root=tmp_path / "src")
    with pytest.raises(CLI.AxisError):
        CLI.export(out_dir=tmp_path / "out", db_root=tmp_path / "src")
    r = CLI.export(out_dir=tmp_path / "out", db_root=tmp_path / "src", archive=True)
    man = r["manifest"]
    assert man["archive"] is True
    assert man["axes"]["set_version"] == "1.0.7" and man["axes"]["set_root"] is None, \
        "归档包不许拿本装置的 root 去追认另一版的读数"
    assert man["installation_axes"]["set_version"] == "9.9.9"
    local = tmp_path / "local"
    assert CLI.main(["--db", str(local), "merge", r["package"]]) == 3
    assert CLI.main(["--db", str(local), "merge", r["package"], "--archive"]) == 0
    assert len(DB.load(local)) == 1


# --------------------------------------------------------------- ⑮ run_id 的机器标识

def test_run_id_带机器标识且_job_id_与它同源():
    rid = INJ.run_id("s5-cor-01", "strict", "cfg-a", 7, machine="lab-01-abcdef12")
    assert rid == "s5-cor-01.strict.cfg-a.r07@lab-01-abcdef12"
    assert INJ.split_run_id(rid) == ("s5-cor-01.strict.cfg-a.r07", "lab-01-abcdef12")
    j = JL.make_job("tb", "s5-cor-01", "strict", "cfg-a", 7, stage="S5")
    assert j["job_id"] == INJ.run_id("s5-cor-01", "strict", "cfg-a", 7), \
        "job_id 与 run_id 不同源的话，「这个 job 跑出来的是哪个 run」要靠一张会漂的映射表"


def test_机器标识由环境变量钉死时两台机器算出同一个值(monkeypatch):
    """f01 跑批时把自己的标识 export 给 f02，靠的就是这条。"""
    monkeypatch.setenv(INJ.MACHINE_ID_ENV, "f01-pinned")
    assert INJ.machine_id() == "f01-pinned"
    assert INJ.run_id("s1-cor-01", "open", "c", 1).endswith("@f01-pinned")
    assert INJ.machine_info()["fingerprint_source"] == f"env:{INJ.MACHINE_ID_ENV}"
    monkeypatch.setenv(INJ.MACHINE_ID_ENV, "带点.的不行")
    with pytest.raises(Exception):
        INJ.machine_id()


def test_机器指纹不含稳定源原文也不随时间变():
    fp, src = INJ.machine_fingerprint()
    assert len(fp) == 16 or len(fp) == 8
    info = INJ.machine_info()
    assert info["fingerprint"] == fp
    #: 两次算出来必须一样（进程内缓存 + 稳定源）。
    assert INJ.machine_fingerprint() == (fp, src)
    blob = json.dumps(info, ensure_ascii=False)
    for p in INJ._MACHINE_ID_FILES:
        raw = Path(p).read_text(encoding="utf-8").strip() if Path(p).is_file() else None
        if raw:
            assert raw not in blob, "稳定源的原文不许进任何产物（systemd 明说这个值不该外露）"


def test_compose项目名认得出机器标识():
    proj = INJ.compose_project(INJ.run_id("s1-cor-01", "open", "cfg-a", 3, machine="m-1234abcd"))
    import re
    assert re.fullmatch(r"[a-z0-9][a-z0-9_-]*", proj), "compose 项目名不许带 . 或 @"
    assert proj.endswith("m-1234abcd")


def test_旧记录的主键一个字节都没变():
    """向后兼容：库里 2026-09-10 之前那些没有机器段的记录，键仍是 `(batch, run_id)`。

    这不是风格问题 —— 键一变，`ingest` 的幂等就没了，`run_joblist` 每跑完一批做的
    那次回填会在「同主键内容不同」上当场抛。
    """
    old = {"batch": "m6", "run_id": "s1-cor-01.open.cfg-a.r01"}
    assert DB.key_of(old) == "m6/s1-cor-01.open.cfg-a.r01"
    assert DB.machine_of(old) is None
    new = {"batch": "m6", "run_id": "s1-cor-01.open.cfg-a.r01@lab-1"}
    assert DB.key_of(new) == "lab-1/m6/s1-cor-01.open.cfg-a.r01@lab-1"
    assert DB.machine_of(new) == "lab-1"


def test_结果库与注入器用的是同一个分隔符():
    assert DB.MACHINE_SEP == INJ.MACHINE_SEP == "@"


# --------------------------------------------------------------- ⑰ 版本锁

def test_axes_now_读的就是盘上那两份冻结清单():
    ax = CLI.axes_now()
    ts = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    rf = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.reference.json").read_text(encoding="utf-8"))
    assert ax["set_version"] == ts["set_version"] and ax["set_root"] == ts["root"]
    assert ax["reference_version"] == rf["reference_version"]
    assert len(str(ax["reference_root"])) == 64


def test_今天这个仓库的版本锁是绿的():
    """恒绿的门看不出东西 —— 所以这一条与下面那条「改一条轴就拒」是一对。"""
    r = CLI.check_release_axes()
    assert r["ok"], format_div(r)


def format_div(r) -> str:
    return CLI.format_divergences(r["divergences"], where="test")


@pytest.mark.parametrize("axis", ["set_version", "set_root", "reference_version", "reference_root"])
def test_改一条轴入口就拒(tmp_path, axis):
    """裁定 ⑰ 点名的测试：**任一轴**与 RELEASE_MANIFEST 不一致 → 包拒绝运行。"""
    man = json.loads((_REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    man["axes"][axis] = "TAMPERED"
    p = tmp_path / "RELEASE_MANIFEST.json"
    p.write_text(json.dumps(man, ensure_ascii=False), encoding="utf-8")

    r = CLI.check_release_axes(manifest=p)
    assert not r["ok"] and [d["axis"] for d in r["divergences"]] == [axis]
    assert "怎么修" in CLI.format_divergences(r["divergences"], where="x")

    #: 两个入口都拒：genebench 子命令、跑批运行器。
    assert CLI.main(["--release-manifest", str(p), "axes"]) == 3
    assert CLI.main(["--release-manifest", str(p), "export", "--out", str(tmp_path / "o")]) == 3

    env_run = subprocess.run(
        [sys.executable, str(_REPO / "ops" / "run_joblist.py"), "--jobs", str(tmp_path / "none.jsonl"), "--dry"],
        capture_output=True, text=True, timeout=600,
        env={**__import__("os").environ, CLI.RELEASE_MANIFEST_ENV: str(p),
             "PYTHONDONTWRITEBYTECODE": "1"})
    assert env_run.returncode == 3, (env_run.returncode, env_run.stdout[-400:], env_run.stderr[-400:])
    assert "版本锁" in env_run.stderr and axis in env_run.stderr


def test_没有发布清单也拒(tmp_path):
    """发布包里少了 RELEASE_MANIFEST 不是「那就不校验了」，是「没有可比的一方」。"""
    r = CLI.check_release_axes(manifest=tmp_path / "不存在.json")
    assert not r["ok"] and r["divergences"][0]["axis"] == "RELEASE_MANIFEST"
    assert CLI.main(["--release-manifest", str(tmp_path / "不存在.json"), "axes"]) == 3


def test_代码常量与盘上清单分家时也拒(monkeypatch):
    """有人改了 freeze_v10.SET_VERSION 却没重冻 —— 这个装置「现在是哪一版」没有答案。"""
    ax = CLI.axes_now()
    bad = dict(ax, code_set_version="7.7.7")
    div = CLI.axis_divergences({f: ax[f] for f in CLI.LOCK_FIELDS}, bad)
    assert [d["axis"] for d in div] == ["code_set_version"]
    assert "没重冻" in div[0]["why"]
