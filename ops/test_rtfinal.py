# -*- coding: utf-8 -*-
"""最终卡 · 红队修复的判据（2026-09-12）。

钉住的是**四条 block + 两条 major 各自的那一件事**，不重复别处已有的门
（十九列有 `ops/test_report_columns.py`、发布清单有 `ops/test_release_manifest.py`、
签字包与主表表头有 `ops/test_V2.py`）。

这一轮修的都是同一个病：**通道感知的配置函数早就有了，入口没用它** ——
结算读标定、读网关日志、读题集根三处默认值都写死私有路径；版本锁自检只核一条轴；
发布清单只登记一条任务集轴。所以下面的测试形状也一样：**换通道，看默认值跟不跟着换**。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                    # noqa: E402
from ops import freeze_v10 as FZ                  # noqa: E402
from ops import score_runs as SRUNS               # noqa: E402
from scorer import l3 as L3                       # noqa: E402

PY = sys.executable


# ---------------------------------------------------------------- block 1

def test_标定的默认值跟着通道走(monkeypatch):
    """`load_calibration()` 在 path=None 时曾写死 `SNAPSHOTS_V1`。

    后果实测过两条：① 公开通道的分数是拿**私有** τ 算的（两条通道的 τ 不相等）；
    ② 在只有公开数据的外部单机上（手册形态①）它去读不存在的
    `snapshots/v1/calibration.json`，18 个 run 里 5 个 FileNotFoundError **静默掉队**。
    """
    import inspect
    src = inspect.getsource(L3.load_calibration)
    # 只看**代码**那一半：函数的 docstring 里正写着「这里曾写死 SNAPSHOTS_V1」，
    # 连 docstring 一起扫的话，这条测试会被自己的说明文字跑红。
    body = src.split(chr(34) * 3)[-1]
    assert "cfg.calibration_path()" in body, "默认值又被写死成某一条通道了"
    assert "SNAPSHOTS_V1" not in body, "又回落到私有快照了"

    monkeypatch.setenv("GENEBENCH_CHANNEL", "public")
    assert cfg.calibration_path() == cfg.snapshot_root("public") / "calibration.json"
    monkeypatch.setenv("GENEBENCH_CHANNEL", "private")
    assert cfg.calibration_path() == cfg.snapshot_root("private") / "calibration.json"
    assert cfg.calibration_path("public") != cfg.calibration_path("private")


def test_两条通道的τ确实不相等():
    """判别力：如果两条通道的标定恰好同值，上面那条测试就证明不了什么。"""
    a = L3.load_calibration(cfg.calibration_path("private"))["tau"]["value"]
    b = L3.load_calibration(cfg.calibration_path("public"))["tau"]["value"]
    assert a != b, "两条通道的 τ 同值 —— 读错通道就查不出来了，这条测试要换判别法"


def test_网关日志与题集根的默认值也跟着通道走(monkeypatch):
    """与标定同一个病的另外两处。三处一起错的表现是「跑得起来、数不一样」：
    实测用私有日志结算这 18 个公开 run，`overreach` 整片 None、gate 判定整片改变；
    用私有 gold 结算，`CellAgree` 由 0.9466 变成 0.2491 而 SR / pass@1 恰好没翻。"""
    monkeypatch.setenv("GENEBENCH_CHANNEL", "public")
    assert cfg.gateway_access_log().name == "gateway_access_public.jsonl"
    assert SRUNS.ref_tasks_for_channel() == SRUNS.PUBLIC_REF_TASKS
    monkeypatch.setenv("GENEBENCH_CHANNEL", "private")
    assert cfg.gateway_access_log().name == "gateway_access.jsonl"
    assert SRUNS.ref_tasks_for_channel() == SRUNS.REF_TASKS


def test_结算入口拦混通道(monkeypatch):
    """公开题集根 + 非公开通道 = 混通道结算，拒绝启动（与 `ops/run_controls.py` 同一道拦）。"""
    monkeypatch.setenv("GENEBENCH_CHANNEL", "private")
    with pytest.raises(SystemExit):
        SRUNS.assert_channel_matches(SRUNS.PUBLIC_REF_TASKS)


def test_公开批的结算摘要写明了它用的是哪一条通道的标定():
    """「读哪条通道的标定」必须是一次**看得见**的记录，而不是一次藏在默认值里的回落。"""
    p = _REPO / "ops" / "reports" / "m6_public" / "summary.md"
    t = p.read_text(encoding="utf-8")
    assert "通道: public" in t
    assert "snapshots/public_v1/calibration.json" in t
    assert "gateway_access_public.jsonl" in t
    assert "v1.0-smoke-public" in t


def test_公开批的分数用的是公开τ():
    """盘上那 18 份 score.json 里记的 τ 必须是**公开**那一份的值。"""
    want = L3.load_calibration(cfg.calibration_path("public"))["tau"]["value"]
    other = L3.load_calibration(cfg.calibration_path("private"))["tau"]["value"]
    d = _REPO / "ops" / "reports" / "m6_public" / "scores"
    seen = 0
    for f in sorted(d.glob("*@*.score.json")):
        tau = (json.loads(f.read_text(encoding="utf-8"))["record"].get("correctness") or {}).get("tau")
        if tau is None:
            continue
        seen += 1
        assert tau == want, f"{f.name} 记的 τ 是 {tau}"
        assert tau != other
    assert seen >= 2, "一份带 τ 的记录都没有 —— 判据前提不成立"


def test_已作废的那批读数不在现行scores目录里():
    """minor 8：`glob("scores/*.score.json")` 不该拿到跨轴的两批。"""
    d = _REPO / "ops" / "reports" / "m6_public" / "scores"
    assert d.is_dir()
    stale = [p.name for p in d.glob("*.score.json") if "@" not in p.name]
    assert not stale, f"没带 @host 后缀的旧读数还在 scores/ 里：{stale}"
    old = _REPO / "ops" / "reports" / "m6_public" / "scores_superseded_20260912"
    assert (old / "README.md").is_file(), "旧读数挪走了但没留说明"
    assert len(list(old.glob("*.score.json"))) == 8


# ---------------------------------------------------------------- block 2 / major 6

def test_VERSIONS里三条轴都是现值且公开轴在场():
    t = (_REPO / "VERSIONS.md").read_text(encoding="utf-8")
    for v in (FZ.SET_VERSION, FZ.SET_VERSION_PUBLIC, FZ.REFERENCE_VERSION):
        assert f"**{v}**" in t or f"**`{v}`**" in t, f"VERSIONS.md 里没有现值 {v}"
    pm = json.loads((_REPO / "ops/manifests/v1.0-smoke-public.json").read_text(encoding="utf-8"))
    assert pm["root"][:16] in t, "VERSIONS.md 里没有公开轴的根"


def test_发布清单的axes登记了公开轴():
    ax = json.loads((_REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))["axes"]
    pm = json.loads((_REPO / "ops/manifests/v1.0-smoke-public.json").read_text(encoding="utf-8"))
    assert ax["public_set_version"] == FZ.SET_VERSION_PUBLIC == pm["set_version"]
    assert ax["public_set_root"] == pm["root"]
    assert "public" in ax["channels"]


# ---------------------------------------------------------------- major 7

def test_check_all把三条轴一起核了():
    r = subprocess.run([PY, str(_REPO / "ops" / "freeze_v10.py"), "--check-all"],
                       capture_output=True, text=True, cwd=str(_REPO), timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr
    out = r.stdout
    for tag in ("任务集（private）", "任务集（public）", "参考面"):
        assert tag in out, f"--check-all 没报 {tag}"
    for v in (FZ.SET_VERSION, FZ.SET_VERSION_PUBLIC, FZ.REFERENCE_VERSION):
        assert v in out
    assert "三条轴全部与冻结清单一致" in out


def test_无开关那条分支自己说清只核了一条轴():
    """它只比 `ops/manifests/v1.0-smoke.json`。不写明的话，外部用户照手册做完
    这一步会以为三条根都锁住了（红队最终轮 major 7）。"""
    r = subprocess.run([PY, str(_REPO / "ops" / "freeze_v10.py")],
                       capture_output=True, text=True, cwd=str(_REPO), timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "只核了私有任务集轴" in r.stdout


def test_手册的版本锁自检那一步用的是check_all():
    t = (_REPO / "docs" / "OPERATOR_MANUAL.md").read_text(encoding="utf-8")
    assert "--check-all" in t
    assert "F.frozen_ref(verify=True); F.reference_ref(verify=True)" not in t, \
        "手册里还留着只核两条轴的旧写法"


# ---------------------------------------------------------------- block 3 的补充

def test_主表的latex_label互异且表头统一():
    """`ops/test_V2.py` 已经钉住这两条；这里只钉**重出时不要退化**的那一半：
    21 张表的 caption 不能全变成同一句（label 撞号就是这么来的）。"""
    caps, labs = [], []
    for p in sorted((_REPO / "ops" / "reports").glob("*/table_main.tex")):
        t = p.read_text(encoding="utf-8")
        m = re.search(r"\\caption\{(.*?)\}\n\\label\{(.*?)\}", t, re.S)
        assert m, f"{p} 取不到 caption/label"
        caps.append(m.group(1)); labs.append(m.group(2))
        assert r"\textbackslash{}\_" not in m.group(1), f"{p} 的 caption 被二次转义了"
    assert len(labs) == len(set(labs)), "label 撞号"
    assert len(set(caps)) >= len(caps) - 1, "caption 几乎全一样 —— 重出时把各批的文案冲掉了"
