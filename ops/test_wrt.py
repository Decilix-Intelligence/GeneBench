# -*- coding: utf-8 -*-
"""卡 W.rt（红队修复收尾）的判据。

红队十二条 finding：一条 block（S6 gold 的 `provenance` 占位串）**没有修** —— 两条修法
一条要动参考轴冻结根（红线 B4 禁止施工侧直接动）、一条要改评分判据（本卡的纪律是不改判据），
所以它按契约 D 记 blocked 并如实登记进 `ops/reports/known_limits_v1.md`；七条 major 在这里钉住；
四条 minor 登记在 `ops/tickets_inbox/W.rt.md`。

**这里不重复别处已经钉住的东西**（预算档本身有 `ops/test_budget_tiers.py`，
适配赛道有 `ops/test_y2.py`），只钉「红队量到的那件事今天还在不在」。
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

from ops import freeze_v10 as FZ                              # noqa: E402
from runner import registry as REG                            # noqa: E402

REPORTS = _REPO / "ops" / "reports"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def _inbox(name: str) -> str:
    """收件箱并进 ops/tickets.md 之后会改名 `.merged`（2026-09-10 收尾卡）——
    两个名字都认。找不到返回空串，调用方自己断言非空。"""
    d = _REPO / "ops" / "tickets_inbox"
    for cand in (d / f"{name}.md", d / f"{name}.md.merged"):
        if cand.is_file():
            return cand.read_text(encoding="utf-8")
    return ""


def _fenced(seg: str) -> str:
    parts = seg.split("```")
    return "\n".join(parts[i] for i in range(1, len(parts), 2))


# ============================================================ finding 3：两份手册漏同步 N-388

@pytest.mark.parametrize("rel,start,end", [
    ("harnesses/README.md", "### ③ 真跑", "### ④ 结算"),
    ("integrations/README.md", "### ⑥", "### ⑦"),
])
def test_可复制的真跑命令里一个预算参数都没有(rel, start, end):
    """N-388 之后显式给的值**逐键赢过 stage 档位** —— 照抄一个 `--max-tokens 3000000`
    会把默认档（6M）压回 3M，把 S4 的 9M / S7 的 18M 一起打回去。W1 同步了四处文档，
    **漏了这两份**，而它们正是 harness 接入方与被测方照抄的那两份（红队 W.rt finding 3）。"""
    txt = _read(_REPO / rel)
    assert txt, rel
    cmd = _fenced(txt[txt.find(start):txt.find(end)])
    assert cmd.strip(), f"{rel} 取不到命令块 —— 断言会恒绿"
    assert "--max-tokens" not in cmd, rel
    assert "--max-calls" not in cmd, rel


@pytest.mark.parametrize("rel", ["harnesses/README.md", "integrations/README.md"])
def test_两份手册写的默认档就是registry的现值(rel):
    txt = _read(_REPO / rel)
    n = REG.RUN_BUDGET["max_tokens"]
    assert f"{n:,}" in txt or str(n) in txt, f"{rel} 没写出默认档 {n}"
    # **裁定要留痕**：读者得知道这个数是什么时候、按谁的裁定变的。
    assert "N-388" in txt, f"{rel} 没写出 N-388 这次裁定"


def test_HANDOFF_不再声称两份手册已同步():
    txt = _read(_REPO / "ops" / "HANDOFF.md")
    assert "`integrations/P2_CONTRACT.md` 与两份手册已同步" not in txt
    assert "harnesses 那条还写着 `--max-tokens 600000`" not in txt or "~~" in txt


# ============================================================ finding 6：HANDOFF §15.4

def test_HANDOFF的适配赛道一节不再说跑不了():
    txt = _read(_REPO / "ops" / "HANDOFF.md")
    seg = txt[txt.find("### 15.4"):txt.find("### 15.5")]
    assert seg, "§15.4 取不到"
    assert "今天跑不了，缺三件" not in seg
    assert "**但 30 例真跑一次都没能起**" not in seg
    assert "**不要引** SR / 结局分布" not in seg
    assert "待用户裁定（N-348）" not in seg
    # 可引，但必须带脚注。
    assert "N-348" in seg and "脚注" in seg


# ============================================================ finding 4：两份就绪报告的 §1

@pytest.mark.parametrize("rel", [
    "ops/reports/v1_0_readiness.md",
    "ops/reports/m6_public/v1_0_readiness_public.md",
])
def test_就绪报告的四条版本轴与freeze现值一致(rel):
    """两份报告的 §1 本来就是从 `ops/freeze_v10` 现读的模板 —— 只要有人推了版本而没有重出，
    它们就会停在上一版。Y1 推 1.0.14 / r1.0.21 之后两份都停在 1.0.13 / r1.0.20
    （红队 W.rt finding 4），而 S8 的 Slip 与 malformed 口径恰好在这一版变过。"""
    txt = _read(_REPO / rel)
    assert txt, rel
    sec = txt[txt.find("## 1. 组件版本与冻结根"):txt.find("## 2.")]
    assert f"**{FZ.SET_VERSION}**" in sec, (rel, FZ.SET_VERSION)
    assert f"**{FZ.REFERENCE_VERSION}**" in sec, (rel, FZ.REFERENCE_VERSION)
    root = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.json").read_text(
        encoding="utf-8"))["root"]
    assert root[:16] in sec, (rel, root[:16])


# ============================================================ finding 5：known_limits 的两张表

def test_known_limits里已裁定的两条不再摆成待裁定():
    kl = _read(REPORTS / "known_limits_v1.md")
    assert kl
    # N-388 的旧「绕法」今天会把预算压低 —— 它只许以带删除线的历史身份留着。
    for row in re.findall(r"^\|.*N-388.*\|$", kl, re.M):
        assert "~~" in row, f"N-388 那一行没加删除线：{row[:120]}"
    for row in re.findall(r"^\|.*N-348.*\|$", kl, re.M):
        assert "~~" in row or "已裁定" in row, f"N-348 那一行没收口：{row[:120]}"
    assert "就是 16 道基准题的答案" not in kl, "「16 道」没改成 19 道"
    assert "19 道" in kl
    assert "exposed_source_tasks" in kl


def test_known_limits新登记了S6占位串与公开通道0run():
    kl = _read(REPORTS / "known_limits_v1.md")
    assert "TODO:signal-artifact-id-missing" in kl, "S6 gold 的占位串一条都没登记（红队 block）"
    assert "公开通道一个 run 都没有" in kl


def test_判定汇总的条数与逐条表对得上():
    """§5 的就绪报告从这张汇总表**现读**条数，所以它必须自洽：
    汇总的三档加起来 = 逐条表的行数 + 两条各算两半的（N-127 / N-128）。"""
    from ops.readiness_report import KNOWN_LIMITS, known_limits_verdict_summary
    text = KNOWN_LIMITS.read_text(encoding="utf-8")
    summ = known_limits_verdict_summary(text)
    assert summ, "判定汇总解析不出来"
    total = sum(int(v) for _, v in summ)
    from ops.readiness_report import _md_table
    body = [r for r in _md_table(text, "## 逐条") if r and r[0] != "编号"]
    assert body, "逐条表解析不出来"
    # 差 1：`N-127` 与 `N-128` 各带两半（题面部分已修 / 判据部分留 v1.1），
    # 汇总把它们各算两条，而逐条表里各占一行。差值本身就是这条纪律的读数。
    assert total == len(body) + 1, (total, len(body))


# ============================================================ finding 8：适配表的版本轴

def test_适配表带着四条版本轴():
    from scorer import report as R
    for ax in R.VERSION_AXES:
        assert ax in R.TABLE_ADAPTATION_COLUMNS, ax
    head = _read(REPORTS / "adapt" / "table.csv").splitlines()[0].split(",")
    for ax in R.VERSION_AXES:
        assert ax in head, ax
    rows = _read(REPORTS / "adapt" / "table.csv").splitlines()[1:]
    assert rows, "适配表一行数据都没有"
    i_set, i_ref = head.index("set_version"), head.index("reference_version")
    for ln in rows:
        cells = ln.split(",")
        assert cells[i_set] == FZ.SET_VERSION, ln[:80]
        assert cells[i_ref] == FZ.REFERENCE_VERSION, ln[:80]
    tex = _read(REPORTS / "adapt" / "table.tex")
    assert FZ.SET_VERSION in tex and FZ.REFERENCE_VERSION in tex, "caption 里没有轴声明"


# ============================================================ finding 2：清单里的预算是陈的

def test_dry打印的预算是现算的不是清单里物化的():
    """`--dry` 此前打印清单里物化的 `budget`（生成那一刻的读数）。N-388 抬档之后那是陈值 ——
    操作员干跑一遍看到 `tok=3000000`，与 README §5 写的 6M 直接矛盾（红队 W.rt finding 2）。"""
    from ops import run_joblist as RJ
    for stage, want in (("S1", REG.RUN_BUDGET), ("S4", REG.BUDGET_TIERS["S4"]),
                        ("S7", REG.BUDGET_TIERS["S7"])):
        live = RJ.live_budget({"stage": stage, "budget_override": {}})
        assert live["max_tokens"] == want["max_tokens"], (stage, live)
    # 显式覆盖仍然赢 —— 否则上面三条恒绿。
    assert RJ.live_budget({"stage": "S7", "budget_override": {"max_tokens": 1}})["max_tokens"] == 1


def test_公开通道清单里物化的预算已经重新物化():
    import genebench_config as cfg
    from ops import run_joblist as RJ
    p = cfg.GENEBENCH_ROOT / "runs_in" / "m6_public" / "jobs.jsonl"
    if not p.is_file():
        pytest.skip("没有 m6_public 清单")
    rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert rows
    for r in rows:
        if r["status"] != "pending" or r.get("run_id"):
            continue                      # 跑过的行里那个 budget 是遥测，不许改
        assert r["budget"] == RJ.live_budget(r), r["job_id"]


def test_rebudget只动没跑过的行(tmp_path):
    """跑过的行里的 `budget` 是遥测（「这一行当时按哪档跑的」），改它等于伪造现场。"""
    from ops import joblist as JL
    p = tmp_path / "jobs.jsonl"
    stale = {"max_calls": 100, "max_tokens": 3_000_000}
    rows = [
        JL.make_job("b", "s1-cor-01", "strict", "cfg", 1, stage="S1"),
        JL.make_job("b", "s2-cor-01", "strict", "cfg", 1, stage="S2"),
    ]
    rows[0]["budget"] = dict(stale)
    rows[1]["budget"] = dict(stale)
    rows[1]["status"] = "done"
    rows[1]["run_id"] = "s2-cor-01.strict.cfg.r01"
    JL.save(p, rows)
    JL.main(["rebudget", str(p)])
    after = {r["job_id"]: r for r in JL.load(p)}
    assert after["s1-cor-01.strict.cfg.r01"]["budget"]["max_tokens"] == REG.RUN_BUDGET["max_tokens"]
    assert after["s2-cor-01.strict.cfg.r01"]["budget"] == stale, "跑过的行被改了"


def test_发布清单把公开通道0run写成显式一条():
    import genebench_config as cfg
    from ops import mk_release_manifest as MR
    m = json.loads((_REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))
    b = next(x for x in m["blockers"] if x["id"] == "public_channel_zero_runs")
    p = cfg.GENEBENCH_ROOT / "runs_in" / "m6_public" / "jobs.jsonl"
    if p.is_file():
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        n_run = sum(1 for r in rows if r.get("run_id"))
        assert b["satisfied"] is (n_run > 0), (b["status_now"], n_run)
    assert MR.public_channel_runs() is not None or not p.is_file()
    # 假仓库上这条必须「不适用」—— 否则 test_release_manifest 那条反向判别力会被它拖红。
    assert MR.blockers(Path("/nonexistent"), [], "granted", "Apache-2.0")
    bl = next(x for x in MR.blockers(Path("/nonexistent"), [], "granted", "Apache-2.0")
              if x["id"] == "public_channel_zero_runs")
    assert bl["satisfied"] is True


# ============================================================ finding 7：Y1 收件箱的 47

def test_Y1收件箱把47改成34并把S7那15个登记上():
    txt = _inbox("Y1")
    assert txt, "Y1 的收件箱（Y1.md 或 Y1.md.merged）不在"
    assert "**47 个夹具已物化**" not in txt
    assert "**34 个夹具已物化**" in txt
    assert "S7 的 15 个" in txt
    import yaml
    spec = yaml.safe_load((_REPO / "genetask" / "params" / "v1.0-instances.yaml").read_text(
        encoding="utf-8"))
    fx = spec.get("fixtures") or {}
    assert len(fx) == 34, f"夹具块实测 {len(fx)} 条 —— 收件箱里的数要跟着改"
    # 并进票据之后，这条更正必须在 ops/tickets.md 里也找得到（收件箱会改名，票据不会）
    assert "夹具 sha 实测只有 34 条" in _read(_REPO / "ops" / "tickets.md")


# ============================================================ 本卡自己的收件箱

def test_收件箱四条minor都登记了():
    txt = _inbox("W.rt")
    assert txt, "W.rt 的收件箱（W.rt.md 或 W.rt.md.merged）不在"
    tickets = _read(_REPO / "ops" / "tickets.md")
    for k in ("reference_close", "probe_matrix_instances", "table_a.csv", "19 道"):
        assert k in txt, k
        # 并进票据之后，四条 minor 在 ops/tickets.md 里也要找得到 —— 合并不许把它们弄丢
        assert k in tickets, f"{k} 没有并进 ops/tickets.md"
