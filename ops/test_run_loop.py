# -*- coding: utf-8 -*-
"""卡 4.1/4.3 的正式 run 循环（`runner/run_loop.py`）。

**不起容器**：这里测的是循环的**结构**——允许集判据、两次复核的位置、
`down -v` 的不变量。真跑在 f02（`runner/f02/`），归 B 档。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from runner import run_loop as RL
from runner.c42 import harvest as HV

_REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------- 允许集判据

def test_nothing_allowed_before_up_is_actually_empty():
    assert RL.NOTHING_ALLOWED == (), \
        "起容器前的允许集非空 = P8 之后到 up 之间有一条缝，探针脚本正是从那儿进去的"


@pytest.mark.parametrize("rel,allow,want", [
    ("work/artifact.json", ("work/artifact.json",), True),
    ("work/artifact.json", ("work/artifact.jsonx",), False),
    ("log/egress.jsonl", ("log/",), True),
    ("log", ("log/",), False),                     # 目录名本身不是前缀命中
    ("log_evil/x", ("log/",), False),              # ← 少一个 / 就会放行它
    ("work/out/emission.jsonl", ("work/out/",), True),
    ("work/out_evil/probe.py", ("work/out/",), False),
    ("anything", (), False),
])
def test_allowed_prefix_has_a_boundary(rel, allow, want):
    assert RL._allowed(rel, allow) is want


def test_allowlist_comes_from_the_harvester():
    """裁定 2026-09-04：定义产出物的人定义允许集。手抄一份在 run_loop 里，
    采集器改了产出物它不会跟着改 —— 而漂开的方向是**放行**。"""
    src = (_REPO / "runner" / "run_loop.py").read_text(encoding="utf-8")
    assert "produced_allowlist" in src
    assert "EXPECTED_ARTIFACTS" not in src, "占位清单没收干净"
    assert RL.HV.produced_allowlist("S3", "strict") == HV.produced_allowlist("S3", "strict")


# --------------------------------------------------------------- verify_unchanged

class _FakeInject:
    """只替 `verify_run_dir_unchanged` 的返回值 —— 突变落在**门保护的对象**上
    （run dir 的变化清单），不落在门的参数上。"""

    def __init__(self, lines):
        self.lines = lines

    def verify_run_dir_unchanged(self, run_dir):
        return list(self.lines)


def _patch(monkeypatch, lines):
    monkeypatch.setattr(RL.INJ, "verify_run_dir_unchanged",
                        _FakeInject(lines).verify_run_dir_unchanged)


def test_verify_unchanged_lets_through_only_additions_on_the_list(monkeypatch, tmp_path):
    _patch(monkeypatch, ["注入后被加：work/artifact.json —— 来路不明"])
    assert RL.verify_unchanged(tmp_path, allow=("work/artifact.json",), stage="退出之后") == []
    assert RL.verify_unchanged(tmp_path, allow=RL.NOTHING_ALLOWED, stage="up 之前") != [], \
        "起容器前允许集为空，任何新增都必须红"


def test_verify_unchanged_never_forgives_a_modification(monkeypatch, tmp_path):
    """允许集是**加法**：它只放行新增。被改 / 被删在任何阶段都不许。"""
    _patch(monkeypatch, ["注入后被改：work/artifact.json"])
    bad = RL.verify_unchanged(tmp_path, allow=("work/artifact.json",), stage="退出之后")
    assert bad and "被改" in bad[0]
    _patch(monkeypatch, ["注入后被删：work/INSTRUCTION.md"])
    assert RL.verify_unchanged(tmp_path, allow=("work/",), stage="退出之后")


def test_verify_unchanged_stamps_the_stage(monkeypatch, tmp_path):
    _patch(monkeypatch, ["注入后被加：work/probe.py —— 来路不明"])
    bad = RL.verify_unchanged(tmp_path, allow=(), stage="up 之前")
    assert bad[0].startswith("[up 之前]"), \
        "两次复核的报错分不开的话，看日志的人不知道文件是什么时候进来的"


# --------------------------------------------------------------- 循环的形状

def test_loop_verifies_before_up_and_after_exit():
    """两次复核**都要在**，且一次在 up 之前、一次在容器退出之后。"""
    src = (_REPO / "runner" / "run_loop.py").read_text(encoding="utf-8")
    i_before = src.index('stage="up 之前"')
    i_up = src.index('"up", "-d"')
    i_after = src.index('stage="退出之后"')
    assert i_before < i_up < i_after, "复核跑到了 compose up 的另一边"
    assert src.index('"down", "-v"') < i_after, "退出后复核在 down 之前跑 = 还没退出就查"


def test_down_is_in_a_finally():
    src = (_REPO / "runner" / "run_loop.py").read_text(encoding="utf-8")
    tail = src[src.index("except subprocess.TimeoutExpired"):]
    assert tail.index("finally:") < tail.index('"down", "-v"'), \
        "down 不在 finally 里 —— 超时那次的容器会留下来，下一个 run 撞上残留"


def test_run_json_and_inject_json_stay_separate(tmp_path):
    res = RL.RunResult(run_id="r1", run_dir=tmp_path, arm="open", config_id="c",
                       exit_code=0, started_at="s", finished_at="f", elapsed_s=1.0,
                       new_files={"work/artifact.json": "ab" * 32}, unexpected=[])
    RL._write_run_json(res)
    got = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert got["run_id"] == "r1" and "new_files" in got
    assert "files" not in got, "inject.json 记「注入了什么」，run.json 记「跑出了什么」"
