# -*- coding: utf-8 -*-
"""卡 Y1b 的判据：**实例层** oracle 跑批 + **按实例**出的 O1 矩阵。

这一页钉住的是**口径**：`40 模板 / N 实例`。实例不是新题 —— 它是出集参数表的
同一行沿 window / universe / factor_pool 换了取值。把两者加成一个数
（「130 道题」「170 道题」）是本卡最容易犯、也最难被发现的错，
所以这里让它在测试里就红。

第二件钉住的事：**「不可得」与「零」不许长得一样**。实例层比出集层更容易踩 ——
S6 的 15 个实例现在连夹具都没有（Y1 的 v11_deferred），它们跑出来是
「什么都没判」；把那一列画成 `·` 就等于宣布「S6 的探针全干净」。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ops import run_oracles as RO                       # noqa: E402
from reference.artifact_schema import PROBE_IDS         # noqa: E402

REPORTS = REPO / "ops" / "reports"
MATRIX = REPORTS / "probe_matrix_instances.md"
DETAIL = REPORTS / "probe_run_instances.cumulative.json"
MATRIX_PUB = REPORTS / "public" / "probe_matrix_instances.md"
DETAIL_PUB = REPORTS / "public" / "probe_run_instances.cumulative.json"

#: 出集参数表的行数 = 「模板」数。**不是模板目录数（39）** ——
#: `S1/source_status` 被 `s1-rob-01` 与 `s1-rob-02` 两行复用。
N_TEMPLATES = 40
N_INSTANCES = 130

_FAM = sorted(PROBE_IDS)[0]


def _row(task_id: str, base: str, *, ok: bool, probes=None, findings=None,
         note: str = "", stage: str = "S1") -> dict:
    return {"task_id": task_id, "stage": stage, "template_id": "t", "ok": ok,
            "rc": 0 if ok else 1, "log_rows": 1, "note": note, "evidence": [],
            "probes": probes or {}, "at": "2026-09-10T00:00:00+00:00",
            "tradability_rows": 1, "stderr_tail": "", "findings": findings or [],
            "instance_id": f"S1/t@{base}#{task_id}", "base_task_id": base,
            "is_base": task_id == base, "fingerprint": "0" * 10, "params_norm": {}}


# ------------------------------------------------------------ 实例行来源

def test_实例行有130个且task_id互不相同():
    rows, meta = RO.instance_rows()
    assert len(rows) == N_INSTANCES, f"实例数变了：{len(rows)}"
    ids = [r["task_id"] for r in rows]
    assert len(set(ids)) == len(ids), "实例 task_id 撞了 —— 两份题面会互相覆盖"
    assert set(meta) == set(ids)


def test_基准实例正好40个_那才是模板数():
    """40 个基准实例 = 出集参数表的 40 行。**口径的锚就在这里**。"""
    _, meta = RO.instance_rows()
    bases = {m["base_task_id"] for m in meta.values()}
    assert len(bases) == N_TEMPLATES, f"基点数变了：{len(bases)}"
    assert sum(1 for m in meta.values() if m["is_base"]) == N_TEMPLATES


def test_按阶段筛得动():
    rows, meta = RO.instance_rows("S1,S2")
    assert {m["stage"] for m in meta.values()} == {"S1", "S2"}
    assert 0 < len(rows) < N_INSTANCES


# ------------------------------------------------------------ 元数据必须落盘

def test_实例元数据跟着结果行一起落盘():
    """不落盘的话，隔一批再渲矩阵就只剩 `task_id` —— 而 `s4-rob-05` 这个号
    是发出来的，从它看不出基点是谁。矩阵于是聚合不了。"""
    r = RO.Result("s4-rob-05", "S4", "tpl")
    r.ran, r.rc, r.artifact = True, 0, Path("x")
    meta = {"s4-rob-05": {"instance_id": "S4/tpl@s4-rob-01#abc", "base_task_id": "s4-rob-01",
                          "is_base": False, "fingerprint": "abc", "params_norm": {"window": "w"}}}
    row = RO._result_row(r, meta)
    assert row["base_task_id"] == "s4-rob-01"
    assert row["instance_id"].endswith("#abc")
    assert row["params_norm"] == {"window": "w"}
    # 没有 meta 时不许自己编一个
    assert "base_task_id" not in RO._result_row(r, {})


# ------------------------------------------------------------ 矩阵语义

def test_没产出artifact的实例画na而不是点():
    """恒绿的门与恒红的一样会被绕过：把「什么都没判」画成 `·`，
    S6 那 15 个就会显示成「探针全干净」。"""
    rows = [_row("a-01", "a-01", ok=True),
            _row("a-02", "a-01", ok=False, note="夹具不在")]
    md = RO.render_matrix_instances(rows)
    assert "没产出 artifact、因而什么都没判的 1" in md
    assert "零 finding 的实例 1/2" in md
    assert "夹具不在" in md, "不可判的实例必须逐条给出原因"


def test_基点全军覆没时整列是na():
    rows = [_row("b-01", "b-01", ok=False, note="崩了")]
    md = RO.render_matrix_instances(rows)
    line = [x for x in md.splitlines() if x.startswith(f"| `{_FAM}` |")][0]
    assert "n/a" in line, "一个实例都没产出时不许画 `·`"


def test_按基点聚合而不是按模板目录聚合():
    """`S1/source_status` 被两行参数复用。按模板目录聚合会把两道题的实例混成一列。"""
    rows = [_row("s1-rob-01", "s1-rob-01", ok=True),
            _row("s1-rob-02", "s1-rob-02", ok=True)]
    md = RO.render_matrix_instances(rows)
    head = [x for x in md.splitlines() if x.startswith("| 探针族 |")][0]
    assert "s1-rob-01" in head and "s1-rob-02" in head, "两行参数必须是两列"


def test_非零的实例逐条列原因():
    rows = [_row("c-01", "c-01", ok=False, probes={_FAM: 2},
                 findings=["某某字段对不上"])]
    md = RO.render_matrix_instances(rows)
    assert "某某字段对不上" in md
    assert f"`{_FAM}`×2" in md


def test_口径行写的是模板与实例两个数():
    rows = [_row("d-01", "d-01", ok=True)]
    md = RO.render_matrix_instances(rows)
    assert f"**口径：{N_TEMPLATES} 模板 / 1 实例。**" in md
    assert "不是新题" in md


def test_矩阵写明三控与破坏样本不按实例重跑():
    """这是本卡的一条裁定。报告里不写，读者会以为漏跑了。"""
    md = RO.render_matrix_instances([_row("e-01", "e-01", ok=True)])
    assert "三控与破坏样本不按实例重跑" in md
    assert "run_probe_mutations" in md and "run_controls" in md


# ------------------------------------------------------------ 与真产物对账（会自己失效的测试）

@pytest.mark.skipif(not DETAIL.is_file(), reason="私有实例明细还没落盘")
def test_私有矩阵的实例数与明细文件一致():
    rows = json.loads(DETAIL.read_text(encoding="utf-8"))
    md = MATRIX.read_text(encoding="utf-8")
    assert f"**口径：{N_TEMPLATES} 模板 / {len(rows)} 实例。**" in md, \
        "矩阵抬头的实例数与明细文件对不上 —— 有一份是旧的"
    zero = sum(1 for r in rows if (r.get("ok") or r.get("findings")) and not (r.get("probes") or {}))
    assert f"**零 finding 的实例 {zero}/{len(rows)}**" in md


@pytest.mark.skipif(not DETAIL.is_file(), reason="私有实例明细还没落盘")
def test_矩阵的列数不超过模板数():
    """实例摊成列就是 130 列。摊错了这条会红。"""
    rows = json.loads(DETAIL.read_text(encoding="utf-8"))
    md = MATRIX.read_text(encoding="utf-8")
    head = [x for x in md.splitlines() if x.startswith("| 探针族 |")][0]
    ncol = len(head.split("|")) - 4          # 去掉首尾空段、探针族、行合计
    assert ncol == len({r.get("base_task_id") or r["task_id"] for r in rows})
    assert ncol <= N_TEMPLATES


@pytest.mark.skipif(not DETAIL.is_file(), reason="私有实例明细还没落盘")
def test_明细里每一行都带得出基点():
    rows = json.loads(DETAIL.read_text(encoding="utf-8"))
    missing = [r["task_id"] for r in rows if not r.get("base_task_id")]
    assert not missing, f"这些行没带实例元数据，矩阵聚合不了：{missing[:8]}"


# ------------------------------------------------------------ 没判成的归类

def test_夹具在但参考解自己崩了_不许归成缺夹具():
    """**这条是被实测打脸打出来的**（s4-eco-03，2026-09-10）。

    它的 stderr 是 `ValueError: work/factor_pool.parquet 里没有 'nan' 的行` ——
    夹具**在**（2.6 MB 就在那儿），崩的是参考解自己挑因子那一步（挑出了一个叫
    `'nan'` 的因子）。归类器原来是「命中任一关键词」，于是只因为带了 `work/`
    就把它归成「缺夹具」。**把「参考解崩了」显示成「缺件」，正是这一页要防的事。**
    """
    r = _row("z-01", "z-01", ok=False,
             note="", stage="S4")
    r["stderr_tail"] = ("  File \"reference/s4_oracle_common.py\", line 44\n"
                        "ValueError: work/factor_pool.parquet 里没有 'nan' 的行")
    assert RO._why_not_evaluated(r) == "其余（要查）"


def test_真的缺夹具才归缺夹具():
    r = _row("z-02", "z-02", ok=False)
    r["stderr_tail"] = "FileNotFoundError: /…/v1.0-instances/s6-cor-01/work/signal.parquet"
    assert RO._why_not_evaluated(r) == "缺夹具"


def test_跑超时单独一类():
    """超时与「崩了」不是一回事：前者是这道题在这个取值下**太慢**（s2-rob-04 把窗口
    拉到 13 个月就超了 600 秒），后者是算错了。混一类就看不出「参考解不 scale」。"""
    r = _row("z-03", "z-03", ok=False)
    r["stderr_tail"] = "超时 600s"
    assert RO._why_not_evaluated(r) == "跑超时"


def test_抬头把malformed与探针族的归因分开写():
    """探针族非零 = 探针缺陷；`(malformed)` 非零 = **oracle 自己的产物格式不对**。
    两者归因相反，混着写会让「参考解算出 NaN」被读成「探针误伤」。"""
    md = RO.render_matrix_instances([_row("z-04", "z-04", ok=True)])
    assert "两类行的归因是相反的" in md
    assert "oracle 自己的产物格式不对" in md


# ------------------------------------------------------------ 基准实例 vs 出集同题

def test_一致性对照把真告警与基础设施分开(monkeypatch):
    """「两边都判过但结论不同」才是告警。把「实例层根本没判成」也算进去的话，
    三条已知的基础设施故障（缺夹具 / 撞号）会把真告警埋掉。"""
    monkeypatch.setattr(RO, "_export_set_o1",
                        lambda ch: {"g-01": True, "g-02": True, "g-03": True})
    rows = [
        _row("g-01", "g-01", ok=True),                                  # 一致
        _row("g-02", "g-02", ok=False, note="夹具不在"),                 # 没判成 → 基础设施
        _row("g-03", "g-03", ok=False, probes={_FAM: 1},
             findings=["真的判出来了"]),                                  # 判过且不同 → 告警
    ]
    for r in rows:
        r["is_base"] = True
    md = RO.render_matrix_instances(rows)
    assert "**一致 1**" in md
    assert "两边都判过但结论不同 1（这一栏非零就是告警）" in md
    assert "实例层没判成、对不上的 1" in md
    assert "**告警** `g-03`" in md
    assert "没判成 `g-02`" in md


def test_出集结论取不到时不当成一致(monkeypatch):
    """取不到就是没结论。当成一致 = 拿「读不到文件」冒充「对上了」。"""
    monkeypatch.setattr(RO, "_export_set_o1", lambda ch: {})
    r = _row("h-01", "h-01", ok=True)
    r["is_base"] = True
    md = RO.render_matrix_instances([r])
    assert "**出集那批的结论取不到**" in md
    assert "不当成一致" in md


def test_基准实例之外的行不进一致性对照(monkeypatch):
    """变体的 task_id 是发号发出来的（s4-rob-05），出集里那个号是别的题 ——
    拿它去比就是在比两道不同的题。"""
    monkeypatch.setattr(RO, "_export_set_o1", lambda ch: {"i-02": False})
    r = _row("i-02", "i-01", ok=True)          # is_base 默认 False（task_id != base）
    md = RO.render_matrix_instances([r])
    assert "一致性对照" not in md


def test_整阶段缺席与零散漏跑分开说(monkeypatch):
    """「S4 整个阶段都没跑」是**范围没覆盖到**；「S1 还差 3 个」才是漏跑。
    混成一张 100 条的清单，读者要自己数才看得出来。"""
    monkeypatch.setattr(RO, "_roster", lambda: (4, {"a-01": "i/a-01", "a-02": "i/a-02",
                                                    "b-01": "i/b-01", "b-02": "i/b-02"}))
    monkeypatch.setattr(RO, "_roster_stages", lambda: {"a-01": "S1", "a-02": "S1",
                                                       "b-01": "S4", "b-02": "S4"})
    md = RO.render_matrix_instances([_row("a-01", "a-01", ok=True, stage="S1")])
    assert "跑过的 1/4 个实例" in md
    assert "整个阶段一个都没跑：S4" in md
    assert "S1 还差 1 个" in md


# ------------------------------------------------------------ merge_o1

def test_只渲不并不写明细文件(tmp_path):
    src = tmp_path / "p.cumulative.json"
    src.write_text(json.dumps([_row("f-01", "f-01", ok=True)]), encoding="utf-8")
    patch = tmp_path / "p.json"
    patch.write_text("[]", encoding="utf-8")
    before = patch.read_text(encoding="utf-8")
    out = tmp_path / "m.md"
    rc = subprocess.run(
        [sys.executable, str(REPO / "ops" / "merge_o1.py"), "--instances", "--render-only",
         "--patch", str(patch), "--matrix", str(out), "--channel", "private"],
        cwd=str(REPO), capture_output=True, text=True, timeout=180)
    assert rc.returncode == 0, rc.stderr[-800:]
    assert out.is_file() and "口径：40 模板 / 1 实例" in out.read_text(encoding="utf-8")
    assert patch.read_text(encoding="utf-8") == before, "--render-only 不许写明细"
