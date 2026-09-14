# -*- coding: utf-8 -*-
"""卡 6.rt（阶段六红队修复）的判据。

红队查出 3 条 block + 6 条 major，**每一条都是「两份发布件对同一个量给两个答案」或
「文档让读者做 A、被点名照抄的文件写着 B」**。这份测试要挡住的就是它们再次分叉：

  ① 示例矩阵与两份文档对 `max_tokens` 的说法必须一致（block）；
  ② 验证验证器报告 ① 的三个数必须等于累积产物现算的三个数（block）；
  ③ 就绪报告 §4 指的主表若是混轴表，报告里必须当面说破（block）；
  ④ 手册 §0.1 的 blocker 条数以 `RELEASE_MANIFEST.json` 为准，且不许漏掉代码许可那条（major）；
  ⑤ 「挡发布的事有几条」不许在别处写死（major）；
  ⑥ 就绪报告 §3 的 O1 一行必须三态齐全、且指向**本通道**的产物（major）；
  ⑦ 就绪报告 §5 的条数必须与 `known_limits_v1.md` 的判定汇总同字（major）；
  ⑧ 发布清单的「手册」组必须是外部用户真要读的那几件（major）；
  ⑨ 合并表的脚注版本号从记录现算，不手抄（major）；
  ⑩ 0 个 run 的批不许渲染逐 run 叙述与「0」形态的执行面钉子（major）；
  ⑪ 探针矩阵渲自累积文件 —— 定点重跑不许把它打回局部（major）。

**恒绿防护**：几条断言都带「提取器真的找到了东西」的下界（题数 > 0、行数 > 0），
否则一个匹配不到任何东西的正则同样是全绿的。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

REPORTS = REPO / "ops" / "reports"
MANIFEST = json.loads((REPO / "RELEASE_MANIFEST.json").read_text(encoding="utf-8"))


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


# ============================================================ ① 示例矩阵的 max_tokens

MATRIX = REPO / "ops" / "joblists" / "v1demo.yaml"


def test_示例矩阵两行预算都不写():
    """N-388（2026-09-10 用户裁定）之后：默认档已是 100 次 / **6,000,000** tokens，
    `max_tokens: 3000000` 比默认档还低，写上去是**把预算压下去**；而且显式值逐键赢过
    `BUDGET_TIERS`，会把 S4 的 9M 与 S7 的 18M 一起打回去。所以示例矩阵两行都不写。

    这条断言 2026-09-10 之前要求的正好相反（那时默认档只有 600k，绕法是显式给 3M）——
    矩阵按 N-388 清掉那一行之后它一直红。文档与示例仍然必须同向，只是同向到另一边。"""
    m = yaml.safe_load(MATRIX.read_text(encoding="utf-8"))
    assert "max_tokens" not in m, "示例矩阵写了 max_tokens —— 显式值逐键压过 stage 档位（N-388）"
    assert "max_calls" not in m, "写死 max_calls 会把 stage 档位机制关掉（S4 150 / S7 300）"


def test_示例矩阵生成的八个_job_都走默认档():
    """矩阵不写预算 ⇒ 每个 job 的 `budget_override` 是空的、`budget` 就是 stage 档位的读数。
    四道题都是 S1/S2/S3/S5（矩阵刻意避开 S4/S7），所以八个 job 全是默认档。"""
    from ops import joblist as JL
    from runner import registry as REG
    jobs = JL.gen(JL.load_matrix(MATRIX))
    assert len(jobs) == 8
    assert all(j["budget_override"] == {} for j in jobs), "矩阵不写预算，override 就该是空的"
    assert all(j["budget"]["max_tokens"] == REG.RUN_BUDGET["max_tokens"] for j in jobs)
    assert all(j["budget"]["max_calls"] == 100 for j in jobs)     # 默认档没被关掉


def test_两份文档不再说示例矩阵刻意不写():
    """手册 §5.2 曾写「`v1demo.yaml` 刻意不写 `max_tokens`……抄结构，别抄预算那一行」。
    矩阵改了之后这句话就成了新的误导 —— 它必须跟着改。"""
    manual = _read(REPO / "docs" / "OPERATOR_MANUAL.md")
    assert manual, "手册不在"
    assert "刻意不写 `max_tokens`" not in manual
    assert "3000000" in manual


# ============================================================ ② 验证验证器报告 ① 的三个数

def _o1_counts(o1_dir: Path) -> tuple[int, int, int, int]:
    rows = json.loads((o1_dir / "probe_run_oracle.cumulative.json").read_text(encoding="utf-8"))
    clean = sum(1 for r in rows if r.get("ok") is True)
    dirty = sum(1 for r in rows if r.get("findings"))
    absent = sum(1 for r in rows if r.get("ok") is not True and not r.get("findings"))
    return len(rows), clean, dirty, absent


@pytest.mark.parametrize("report,o1_dir", [
    (REPORTS / "validator_validation_v1.md", REPORTS),
    (REPORTS / "public" / "validator_validation_v1_public.md", REPORTS / "public"),
])
def test_验证验证器报告的零误报计数与累积产物一致(report: Path, o1_dir: Path):
    """这份报告承载「判定：通过」。它曾停在 5.2 重冻**之前**的读数（32/8），
    而同一批发布件里的另外四处都写 34/6 —— 两个互相矛盾的完成度读数，
    且给错的那一份是承载判定的那一份。"""
    txt = _read(report)
    assert txt, f"{report} 不在"
    n, clean, dirty, absent = _o1_counts(o1_dir)
    assert n >= 40 and clean > 0, "累积产物自己就是空的，下面的断言会恒绿"
    line = next(ln for ln in txt.splitlines() if ln.startswith("- 题数："))
    assert f"题数：{n}；有产物且零 finding：{clean}；有 finding：{dirty}；" in line, line
    assert f"没跑 / 没产物（不算零误报）：{absent}" in line, line


# ============================================================ ③ 主表混轴必须说破

def _table_axes(csv_path: Path) -> dict:
    from ops.readiness_report import _axes_of_table
    return _axes_of_table(csv_path)


def test_就绪报告在主表混轴时当面说破():
    """§4 把 `ops/reports/m6_all/table_a.csv` 指名为「主表」，而那张表自报
    `MIXED:1.0.7|1.0.9` / `MIXED:r1.0.14|r1.0.8` —— 比 §1 声明的发布版落后两次重冻。
    `VERSIONS.md` §2 把它记作「一次真事故」。报告必须自己说出来。"""
    txt = _read(REPORTS / "v1_0_readiness.md")
    assert txt, "就绪报告不在"
    ta = REPORTS / "m6_all" / "table_a.csv"
    axes = _table_axes(ta)
    assert axes, "table_a.csv 读不出轴，断言会恒绿"
    mixed = [k for k, v in axes.items() if any(str(x).startswith("MIXED:") for x in v)]
    sec4 = txt.split("## 4. 主表")[1].split("## 4b")[0]
    if mixed:
        assert "混轴表" in sec4, "主表是混轴的，§4 却一个字没提"
        for k in mixed:
            assert k in sec4, f"§4 没写出混的是哪条轴：{k}"
        assert "## 1. 组件版本" in txt and "§4 的主表与本节不是同一组轴" in txt, \
            "§1 与 §4 之间没有交叉指引"
    else:
        assert "混轴表" not in sec4, "主表不是混轴的，却挂着混轴告示"


def test_合并表脚注的版本号是现算的():
    """脚注是「把两批合成同一行 pass@1」的唯一书面理由。它曾把 m6 的**参考轴** `r1.0.8`
    当成任务集轴写成「v1.0.9 与 v1.0.8」—— 理由里的版本号错了，读者没法判断合并成不成立。"""
    recs = json.loads((REPORTS / "m6_all" / "records.json").read_text(encoding="utf-8"))
    assert recs, "records.json 是空的"
    summary = _read(REPORTS / "m6_all" / "summary.md")
    assert "v1.0.8" not in summary, "脚注里那个不存在于本批数据的版本号还在"
    for b in sorted({r["batch"] for r in recs}):
        sets = sorted({str(r["set_version"]) for r in recs if r["batch"] == b})
        refs = sorted({str(r["reference_version"]) for r in recs if r["batch"] == b})
        assert f"`{b}` = 任务集 " + " / ".join(sets) in summary, (b, sets)
        assert " / ".join(refs) in summary, (b, refs)
    src = _read(REPO / "ops" / "combine_batches.py")
    assert "v1.0.9 与 v1.0.8 的 instruction 指纹相同" not in src, "生成器里那句手抄的还在"


# ============================================================ ④⑤ 挡发布的条数

def test_手册开篇摆着每一条挡发布的事():
    head = _read(REPO / "docs" / "OPERATOR_MANUAL.md").split("### 0.2")[0]
    assert head, "手册 §0.1 读不到"
    n = len(MANIFEST["blockers"])
    assert n >= 3
    assert {3: "三件", 4: "四件", 5: "五件"}[n] in head, f"§0.1 的条数与 blockers（{n} 条）对不上"
    # 漏掉的那条恰是唯一一条影响「这份代码我能不能用、能不能转发」的
    assert "SPDX" in head and "许可未定" in head, "§0.1 没写代码许可未定"
    assert "RELEASE_MANIFEST.json" in head, "§0.1 没写权威条数以发布清单为准"


def test_别处不再把挡发布的条数写死():
    """同一个量在五份发布件里三份说三、两份说四。治法不是把三改成四（下次还会分叉），
    是**不在别处写条数**，只指向 `RELEASE_MANIFEST.json` 的 `blockers`。"""
    kl = _read(REPORTS / "known_limits_v1.md")
    assert kl, "known_limits 不在"
    assert "那是另一组三条" not in kl
    assert "以该文件为准" in kl
    src = _read(REPO / "ops" / "mk_release_manifest.py")
    assert "三件挡发布的事之一" not in src


# ============================================================ ⑥ §3 的 O1 一行

@pytest.mark.parametrize("report,o1_dir", [
    (REPORTS / "v1_0_readiness.md", REPORTS),
    (REPORTS / "m6_public" / "v1_0_readiness_public.md", REPORTS / "public"),
])
def test_就绪报告的O1一行三态齐全且指向本通道(report: Path, o1_dir: Path):
    """曾写「40 题、零 finding 34、有 finding 0」——**剩下 6 题的去向被省掉了**，
    而矩阵自己的凡例特意写着「`n/a` 与 `·` 不能混」。公开版还把矩阵指到私有路径。"""
    txt = _read(report)
    assert txt, f"{report} 不在"
    n, clean, dirty, absent = _o1_counts(o1_dir)
    line = next(ln for ln in txt.splitlines() if ln.startswith("- O1 矩阵"))
    for tok in (f"**{n} 题**", f"零 finding **{clean}**", f"有 finding **{dirty}**",
                f"**没产物 {absent}**"):
        assert tok in line, (tok, line)
    rel = str(o1_dir.relative_to(REPO))
    assert f"{rel}/probe_matrix_oracle.md" in line, f"矩阵指的不是本通道那一份：{line}"
    assert f"{rel}/probe_run_oracle.cumulative.json" in line, f"数据源指的不是本通道那一份：{line}"


# ============================================================ ⑦ §5 的条数

def test_就绪报告的已知限制条数与裁定文件同字():
    """§5 声称「现读」，却把逐条表的行数当成了判定条数（15 vs 16）——
    同一个量在两份都进 RELEASE_MANIFEST 的报告里给出两个答案。"""
    from ops.readiness_report import KNOWN_LIMITS, known_limits_verdict_summary
    summ = known_limits_verdict_summary(KNOWN_LIMITS.read_text(encoding="utf-8"))
    assert summ, "判定汇总表解析不出来，断言会恒绿"
    total = sum(int(v) for _, v in summ)
    for report in (REPORTS / "v1_0_readiness.md",
                   REPORTS / "m6_public" / "v1_0_readiness_public.md"):
        txt = _read(report)
        if not txt:
            continue
        line = next(ln for ln in txt.splitlines() if ln.startswith("> **本节从"))
        assert f"判定 {total} 条" in line, (report.name, line)
        for k, v in summ:
            assert f"{k.split('（')[0]} {v}" in line, (report.name, k, v, line)


# ============================================================ ⑧ 发布清单的「手册」组

def test_发布清单里的手册是外部用户真要读的那几件():
    """清单声称「发布件逐件 sha256」，而 `docs/OPERATOR_MANUAL.md` 与 `integrations/README.md`
    整个不在里面；名为「手册」的那一件 `ops/HANDOFF.md`，手册 §0 自己说明它是**内部交接**文档。
    拿到包的人于是无法用清单校验他手上的手册。"""
    from ops import mk_release_manifest as MR
    manuals = MR.RELEASE_ITEMS["手册"]
    for rel in ("docs/OPERATOR_MANUAL.md", "harnesses/README.md", "integrations/README.md"):
        assert rel in manuals, f"「手册」组里没有 {rel}"
        assert (REPO / rel).is_file(), f"{rel} 不存在"
    assert "ops/HANDOFF.md" not in manuals, "内部交接文档不该挂在「手册」组"
    declared = {r for items in MR.RELEASE_ITEMS.values() for r in items}
    assert "ops/HANDOFF.md" in declared, "HANDOFF 也不该整个消失，它应当在「内部交接」那一组"
    files = MANIFEST["files"]
    assert {"docs/OPERATOR_MANUAL.md", "integrations/README.md"} <= set(files), \
        "落盘的 RELEASE_MANIFEST.json 还没刷新（跑一次 ops/mk_release_manifest.py）"
    assert files["docs/OPERATOR_MANUAL.md"]["group"] == "手册"
    assert files["ops/HANDOFF.md"]["group"] != "手册"


# ============================================================ ⑩ 0 个 run 的批

def test_零run的批不渲染逐run叙述(tmp_path: Path):
    """0 个 run 的批不许套用私有批的叙述：
    「validator 被调用 0 次…**但这个零本身是条发现**」「停下 5 个 run 的是预算闸」——
    一个 run 都没有的批「停下 5 个 run」。执行面钉子还漏出未填的模板占位 `…`。

    **对象换成一个一定没有 run 的批名**（2026-09-11，V2.rt 修复卡）：立这条测试时
    `m6_public` 恰好 0 个 run，于是拿它当样本；卡 X1 把那一批跑到 8 个 run 之后，
    这条测试就变成「断言一件已经不成立的事」而红 —— 而它要守的东西（0 run 的批
    不渲染逐 run 叙述）一点没变。判别力由下一条 `test_有run的批照旧渲染主表叙述` 配平。
    """
    out = tmp_path / "zero.md"
    r = subprocess.run(
        [sys.executable, "ops/readiness_report.py", "--batch", "m6_zero_fixture",
         "--reports-dir", "ops/reports/public", "--o1-dir", "ops/reports/public",
         "--out", str(out)],
        cwd=str(REPO), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-1500:]
    txt = out.read_text(encoding="utf-8")
    assert "**0 个 run**" in txt
    assert "## 4b" not in txt, "0 run 的批还在渲染「这一批里值得单独说的四件事」"
    for ghost in ("停下 5 个 run", "但这个零本身是条发现", "零修复，不是未接线"):
        assert ghost not in txt, f"0 run 的批上出现了对它不成立的叙述：{ghost}"
    assert "（未采集）" in txt, "执行面钉子没写「未采集」"
    assert not re.search(r"`…`", txt), "报告里还有未填的模板占位 `…`"
    assert "这一批的真跑没有发生" in txt, "顶部没有提示这一批没跑"


def test_有run的批照旧渲染主表叙述():
    txt = _read(REPORTS / "v1_0_readiness.md")
    assert "## 4b" in txt and "停下 5 个 run" in txt, "有 run 的那一批的叙述被误伤了"


# ============================================================ ⑪ 探针矩阵渲自累积文件

@pytest.mark.parametrize("d", [REPORTS, REPORTS / "public"])
def test_探针矩阵覆盖累积文件的全部题目(d: Path):
    """`run_oracles --tasks a,b` 会把 `probe_run_oracle.json` 整份覆盖。矩阵此前渲的是
    「这一次跑批的 results」，于是定点重跑一道题，40 题的矩阵就地变成「可判题目 1/1」——
    而两份报告都写着「定点重跑不会把它打回局部」。"""
    n, clean, dirty, absent = _o1_counts(d)
    mat = _read(d / "probe_matrix_oracle.md")
    assert mat, f"{d}/probe_matrix_oracle.md 不在"
    assert f"**可判题目 {clean + dirty}/{n}**" in mat, mat.split("\n")[10:12]
    if absent:
        assert f"因而不可判的 {absent} 题" in mat


def test_矩阵还原器与合并器同源():
    """`ops/merge_o1.py` 自己拼过一份 SimpleNamespace，少了 `tradability_rows` ——
    `render_matrix` 用它算「喂了可交易性视图的题」，合并一跑就 AttributeError。"""
    from ops import run_oracles as RO
    src = _read(REPO / "ops" / "merge_o1.py")
    assert "RO.rows_as_results(rows)" in src
    rows = json.loads((REPORTS / "probe_run_oracle.cumulative.json").read_text(encoding="utf-8"))
    md = RO.render_matrix(RO.rows_as_results(rows), agent="oracle", tier="full")
    assert "可判题目" in md and "喂了可交易性视图的题" in md
