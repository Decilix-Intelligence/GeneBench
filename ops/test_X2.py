# -*- coding: utf-8 -*-
"""卡 X2 的判据锁：逐实例 oracle 超时（⑥）、适配表重算（②）、实例覆盖与排除口径（⑦）。

三件事各自锁住的是**曾经出过错的那一面**，不是「函数返回了个数」：

* ⑥ 全局超时**不许**被放宽 —— 放宽全局等于把「哪道题真的慢」从此看不见；
* ② 适配表的四条版本轴必须跟着重冻走，且摘要里要留得住「上一版偏低约 13pp」这句话；
* ⑦ 「没产出 artifact」的实例必须**按原因分类**列出来，且不可得不许与零长得一样。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from ops import run_oracles as RO                                   # noqa: E402


# ============================================================== ⑥ 逐实例 oracle 超时

def test_全局超时没有被放宽():
    """覆盖表的全部意义就是**不动**全局。有人把 600 调大时这条要红。"""
    assert RO.ORACLE_TIMEOUT_DEFAULT == 600
    assert RO.oracle_timeout({"task_id": "s1-cor-01"}) == 600


def test_s2_rob_04_拿到自己的超时():
    """实测 834 s（13:54.49）—— 600 s 卡死它，1800 s 给 2.2 倍留量。"""
    assert RO.oracle_timeout({"task_id": "s2-rob-04"}) == 1800
    assert RO.ORACLE_TIMEOUT_OVERRIDES["s2-rob-04"] > 834


def test_题行里的字段优先于覆盖表():
    """留给参数表那一路：等哪次重冻把 `oracle_timeout` 搬进实例表，这个函数不用改。"""
    assert RO.oracle_timeout({"task_id": "s2-rob-04", "oracle_timeout": 900}) == 900
    assert RO.oracle_timeout({"task_id": "s1-cor-01", "oracle_timeout": 42}) == 42


@pytest.mark.parametrize("bad", [0, -1, "abc", 3.5e400])
def test_非法超时当场拒不静默顶上(bad):
    """给个默认值顶上 = 「我设了超时」与「超时没生效」长得一样。"""
    with pytest.raises(SystemExit):
        RO.oracle_timeout({"task_id": "t", "oracle_timeout": bad})


def test_超时报错文字带上真实秒数():
    """原来写死 `超时 600s`。覆盖生效后还印 600 的话，日志会**指证一个没发生的事实**。"""
    src = (_REPO / "ops" / "run_oracles.py").read_text(encoding="utf-8")
    assert 'f"超时 {tmo}s"' in src
    assert "timeout=tmo" in src
    # 失败分类器**不许钉死秒数**：钉了的话 s2-rob-04 的 `超时 1800s` 会掉出「跑超时」这一类，
    # 于是一类真失败被显示成「没归类」—— 正是 _NA_KINDS 那段注释要防的事。
    assert '("跑超时", ("超时 600s",), "any")' not in src
    assert '("跑超时", ("超时 ", "TimeoutExpired"), "any")' in src


# ============================================================== ② 适配表

_ADAPT = _REPO / "ops" / "reports" / "adapt"


def test_适配表的版本轴跟着重冻走():
    """v1.0.14 那版的数是在旧参考轴上算的。轴不跟着动 = 混轴表（VERSIONS.md §2 记作一次真事故）。"""
    from ops import freeze_v10 as F
    rows = [l.split(",") for l in
            (_ADAPT / "table.csv").read_text(encoding="utf-8").splitlines()[1:] if l.strip()]
    head = (_ADAPT / "table.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    si, ri = head.index("set_version"), head.index("reference_version")
    assert rows, "table.csv 一行都没有"
    for r in rows:
        assert r[si] == F.SET_VERSION, f"表里 set_version={r[si]}，freeze 现值 {F.SET_VERSION}"
        assert r[ri] == F.REFERENCE_VERSION


def test_摘要留得住上一版偏低那句话():
    """这句话是「这两次运行为什么不可比」的对外答案，不是装饰。"""
    s = (_ADAPT / "summary.md").read_text(encoding="utf-8")
    assert "本版为准" in s
    assert "13 个百分点" in s
    assert "TODO:signal-artifact-id-missing" in s, "要说得出偏低的根因是哪个占位串"


def test_那四例现在与新oracle逐字节相同():
    """② 的判据：**不是**「重算之后数字变好了」，是「被测方当初写的就是新 oracle 的值」。

    这条一红，说明重算用的是「对另一道题的答案」（N-114 的教训），该走重跑而不是重算。
    """
    from reference import artifact_schema as sch
    import genebench_config as cfg
    ad = cfg.GENEBENCH_ROOT / "reference" / "adaptation" / "v1.0-adapt"
    ri = cfg.GENEBENCH_ROOT / "runs_in" / "adapt"
    for ex in ("adapt-l1-08", "adapt-l2-07", "adapt-l2-08", "adapt-l3-06"):
        o = json.loads((ad / ex / "oracle.json").read_text(encoding="utf-8"))
        art = o.get("artifact") or o
        run = ri / f"{ex}.adapt.cfg-codex-deepseek.r01" / "work" / "artifact.json"
        if not run.is_file():
            pytest.skip(f"{ex} 的 agent 产物不在本机")
        agent = json.loads(run.read_text(encoding="utf-8"))
        assert agent["provenance"] == art["provenance"], f"{ex} 的 provenance 对不上"
        assert art["provenance"][0]["artifact_id"] == sch.UNRESOLVED


def test_结局分布是重算后的那一版():
    recs = json.loads((_ADAPT / "records.json").read_text(encoding="utf-8"))
    dist: dict = {}
    for r in recs:
        dist[r["outcome"]] = dist.get(r["outcome"], 0) + 1
    assert dist == {"first_pass": 17, "correct_flag": 6, "failed": 7}, dist


# ============================================================== ⑦ 实例覆盖与排除口径

_MATRIX = _REPO / "ops" / "reports" / "probe_matrix_instances.md"


def test_实例矩阵口径仍是40模板130实例():
    m = _MATRIX.read_text(encoding="utf-8")
    assert "40 模板 / 130 实例" in m


def test_没产出的实例按原因分类列出():
    """「没产出 22 个」不是答案 —— 18 个是设计如此、4 个是缺陷，归因相反。"""
    m = _MATRIX.read_text(encoding="utf-8")
    assert "挂起的探针题实例（设计如此）" in m
    assert "与出集撞号（sim 会话工厂）" in m


def test_挂起模板的实例本来就不进出集():
    """130 = 34 道出集模板的 112 个实例 + 6 道挂起模板的 18 个。
    挂起模板的实例拿不到 oracle 是**设计如此**，不是我们没跑到。"""
    import yaml
    from ops import mk_instances as MI
    man = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    released = {(t["task_id"] if isinstance(t, dict) else t) for t in man["released_tasks"]}
    spec = yaml.safe_load((_REPO / "genetask" / "params" / "v1.0-instances.yaml").read_text(encoding="utf-8"))
    insts = MI.enumerate_instances(spec)
    assert len(insts) == 130
    held = [i for i in insts if i.base_task_id not in released]
    assert len(held) == 18, f"挂起模板的实例应是 18 个，实得 {len(held)}"
    assert len(insts) - len(held) == 112


def test_S6实例的夹具都物化了():
    """N-510（先有鸡还是先有蛋）：实例任务目录落盘之后 `s6_consumer_window` 就扫得到了。"""
    import genebench_config as cfg
    root = cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-instances"
    s6 = sorted(d for d in root.iterdir() if d.is_dir() and d.name.startswith("s6-"))
    assert len(s6) == 15, [d.name for d in s6]
    for d in s6:
        got = sorted(p.name for p in (d / "work").glob("signal_*.parquet"))
        assert len(got) == 1, f"{d.name} 的信号夹具：{got}"
