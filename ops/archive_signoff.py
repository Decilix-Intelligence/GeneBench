#!/usr/bin/env python3
"""把**交签的那一版**归档成一个不可变的目录：两份报告 + 主表 + 那一刻的两条版本轴与冻结根。

为什么要归档而不是「看仓库当前状态」：报告是**生成**的，跑一次就覆盖一次。
签字签的是**某一版**，那一版必须能在半年后原样取出来 —— 否则「签过字的报告」只是一个文件名。
归档目录按 `v<任务集>_r<参考面>` 命名，内容只读（0400），并附一份 `MANIFEST.json`
（逐文件 sha256 + 两个根 + git HEAD），谁改动过一眼可查。

**卡 H（2026-09-12，裁定 ① 走 B）：签字包按通道出两份。**
公开通道有**自己的** `SET_VERSION_PUBLIC`（`p1.0.0`）与自己的冻结根，它的报告与表
读的是公开标定、公开网关日志、公开题集根（见 `ops/score_runs.py` 的通道感知默认值）。
把两条通道的件混在一个包里签，读包的人分不出手上这张主表是哪条通道的数 ——
`m6_all__table_main.csv` 与 `m6_public__table_main.csv` 躺在同一个平目录里，
只差文件名里的六个字母，而它们的**轴不同**（`1.0.16` vs `p1.0.0`）。
所以两份包各自只收本通道的表与报告，`MANIFEST.json` 里多一个 `channel` 字段，
包内 README 第一行就写通道。跨通道通用的口径件（已知限制、报告规格、演练、投放说明、
发布清单、版本轴、协议子树清单）**两份都收** —— 它们不属于任何一条通道。

用法：python ops/archive_signoff.py [--label 签字版] [--channel private|public|both] [--force]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from ops import report_io as RIO                      # noqa: E402

ARCHIVE = _REPO / "ops" / "reports" / "signed"

#: 两条通道。`both`（默认）= 各出一份，不是出一份混的。
CHANNELS: tuple[str, ...] = ("private", "public")

#: 通道 → 它那条任务集轴的冻结清单。参考轴两条通道共用一份
#: （冻结根的参考轴部分 = `reference/` 模块 + `solve.py`，与通道无关）。
_SET_MANIFEST: dict[str, str] = {
    "private": "v1.0-smoke.json",
    "public": "v1.0-smoke-public.json",
}

#: **⑥-b（2026-09-11 用户裁定）：发布表就这三种 —— 主表 + 两张全量指标表。**
#: 这两个常量是「哪张能引用」这句话的唯一出处：包内 README、`MANIFEST.json` 的
#: `tables` 段、以及 `ops/test_report_columns.py` 的判据都从这里取。
#: 分成两个常量而不是一句注释，是因为注释拦不住下一个往 `release` 里塞一行的人。
#: **卡 H**：再按通道劈一层 —— 一份包里只出现本通道的那几张。
#: `RELEASE_TABLES` / `DIAGNOSTIC_TABLES` 仍是**两条通道的并集**，因为
#: `ops/test_report_columns.py` 问的是「全仓库哪些表算发布表」，与包无关。
RELEASE_TABLES_BY_CHANNEL: dict[str, tuple[str, ...]] = {
    "private": ("m6_all/table_main.csv", "m6_all/table_main.tex",
                "m6_all/metrics_agent.csv", "m6_all/metrics_agent.md",
                "m6_all/metrics_stage.csv", "m6_all/metrics_stage.md"),
    "public": ("m6_public/table_main.csv", "m6_public/table_main.tex",
               "m6_public/metrics_agent.csv", "m6_public/metrics_stage.csv"),
}
RELEASE_TABLES: tuple[str, ...] = tuple(
    t for ch in CHANNELS for t in RELEASE_TABLES_BY_CHANNEL[ch])

#: 诊断表。**照旧归档**（`ITEMS` 里有它们）—— 归档是留证据，不是给人引用。
#: 「不进发布件清单」与「不归档」是两件事：删掉它们，逐格核对就没有了对照面。
DIAGNOSTIC_TABLES_BY_CHANNEL: dict[str, tuple[str, ...]] = {
    "private": ("m6_all/table_a.csv", "m6_all/table_a.tex", "m6_all/table_b.csv"),
    "public": ("m6_public/table_a.csv", "m6_public/table_b.csv"),
}
DIAGNOSTIC_TABLES: tuple[str, ...] = tuple(
    t for ch in CHANNELS for t in DIAGNOSTIC_TABLES_BY_CHANNEL[ch])

# ---------------------------------------------------------------- 归档清单
# 三组，都相对 `ops/reports/`：跨通道的口径件、私有通道的件、公开通道的件。
# `ROOT_ITEMS` 相对**仓库根**，两份包都收。
# 清单里声明了但这一版不存在的件，进 MANIFEST 的 `declared_but_missing`
# —— 只 print 一行「跳过」的话，读签字包的人查不到它，会以为清单就是落盘的这些。

#: 跨通道：不属于任何一条通道的口径与证据件，两份包都收。
#:   * `known_limits_v1.md` —— 全仓库一份，两条通道的限制都记在里面；
#:   * `report_spec_v1.md` —— 十九列的逐列定义与闸门条件。没有它，
#:     签字包里的主表就是一张没有量纲说明的表；
#:   * `rehearsal_v1.md` / `rehearsal_v2.md` —— ⑭ 从零演练（形态 ① 第一次端到端）的
#:     逐步记录，它是「只凭发布包 + 手册能不能用」这句话唯一的证据；
#:   * `push_instructions.md` —— ㉑ 的投放说明（推之前确认什么、推完做什么）。
SHARED_ITEMS: tuple[str, ...] = (
    "known_limits_v1.md", "report_spec_v1.md",
    "rehearsal_v1.md", "rehearsal_v2.md", "push_instructions.md",
)

#: 私有通道（任务集轴 `1.0.x`）：主批 `m6_all` 的表与报告、`m6` 的三控与破坏样本、
#: oracle / 实例层 O1 矩阵、跨版本探针、适配赛道那一套。
#: **主表在前**（红队 V2.rt finding 6）：⑩ 的固定十九列是**发布表**，
#: `table_a` 是内部诊断表（它带 `effect` 那一列，而 ⑪ 明写 effect 不进发布表）。
#: **⑥-b（2026-09-11）**：诊断表**仍然归档**（留证据），但它不在 `RELEASE_TABLES` 里，
#: 包内 README 与 `MANIFEST.json` 的 `tables` 段都从那两个常量取，不再各写一份。
PRIVATE_ITEMS: tuple[str, ...] = (
    "v1_0_readiness.md", "validator_validation_v1.md",
    "m6_all/table_main.csv", "m6_all/table_main.tex",
    "m6_all/table_a.csv", "m6_all/table_b.csv", "m6_all/table_a.tex", "m6_all/summary.md",
    "m6_all/metrics_agent.csv", "m6_all/metrics_agent.md",
    "m6_all/metrics_stage.csv", "m6_all/metrics_stage.md",
    "m6/controls.md", "m6/mutations.md",
    "probe_matrix_oracle.md", "probe_run_oracle.cumulative.json",
    "crossver_probe_a1.md", "a1_m4_report.md",
    # 2026-09-10（收尾卡）：实例层 O1 矩阵 ——「40 模板 / 130 实例」这个口径只在
    # 这一页与它的累积明细里成立，不归档就只剩仓库里会被下一次跑批覆盖的那一份。
    "probe_matrix_instances.md", "probe_run_instances.cumulative.json",
    # 适配赛道那一套（Y2，N-348 裁定之后第一次有真运行）—— 表 + 逐例对照 + 明细一起归档，
    # 因为表上的 0.633 单独看读不出「30 例各跑了一次 adapt 臂」。
    "adapt/table.csv", "adapt/table.tex", "adapt/summary.md",
    "adapt/oracle_matrix.md", "adapt/records.json",
)

#: 公开通道（任务集轴 `p1.0.0`）：`m6_public` 那一批的表与报告、公开侧的实例层 O1、
#: 公开包自足性的两份证据（因子库三件冻结件的来历、instruments 的公开源重建与对账）。
#: **卡 H 新收三件**（本轮之前不存在或没进过任何包）：
#:   * `m6_public/summary.md` —— 红队最终轮之后它落着四行通道口径
#:     （通道 / 标定 / 网关日志 / 题集根）。没有它，包里那张公开主表读不出「用哪套面算的」；
#:   * `m6_public/g1_public_provider_rerun.md` —— N-611 的闭合证据：这 18 个 run 跑在
#:     **真公开 provider** 上（`features` 下 `bj*` 0 个）。缺了它，公开主表的数没有来历；
#:   * `g2_public_tree_scoring.md` —— 公开树能跑结算（断链 0、树内 320 passed）的验收，
#:     它是「公开包拿到手能用」这句话的证据，属于公开通道。
PUBLIC_ITEMS: tuple[str, ...] = (
    "m6_public/README.md", "m6_public/v1_0_readiness_public.md",
    "m6_public/validator_validation_v1_public.md", "m6_public/controls.md",
    "m6_public/mutations.md", "m6_public/plane_probe.md",
    "m6_public/table_main.csv", "m6_public/table_main.tex",
    "m6_public/table_a.csv", "m6_public/table_b.csv",
    "m6_public/metrics_agent.csv", "m6_public/metrics_stage.csv",
    "m6_public/summary.md", "m6_public/g1_public_provider_rerun.md",
    "g2_public_tree_scoring.md",
    "public/probe_matrix_instances.md", "public/probe_run_instances.cumulative.json",
    "public/instruments_rebuild.md", "public/factor_library_recovery.md",
)

#: 两条通道的并集。**不要**拿它当某一份包的清单 —— 按通道取用 `items_for()`。
#: 留着它是因为 `ops/test_V2.py` / `ops/test_wrapup.py` / `ops/test_V2rt.py` 问的是
#: 「这一件在不在归档清单里」，那是个与通道无关的问题。
ITEMS: tuple[str, ...] = SHARED_ITEMS + PRIVATE_ITEMS + PUBLIC_ITEMS

#: `genequant/MANIFEST.json` 是㉑ 那棵协议子树的封闭清单（25 件逐件 sha256）。
#: 归档它 = 把「这一版签的是哪一版协议工件」钉死；`RELEASE_MANIFEST.json` 的
#: `genequant.manifest_sha256` 指的就是这个文件，两者一起存才对得上。
#: 三件都与通道无关（发布清单里两条轴都在、`VERSIONS.md` 列着两条通道的轴），两份包都收。
ROOT_ITEMS = ("RELEASE_MANIFEST.json", "VERSIONS.md", "genequant/MANIFEST.json")

_SCOPE: dict[str, str] = {
    "private": ("**私有通道**（任务集轴 `1.0.x`）。主表（`m6_all`）= Codex 统一基座 · "
                "M6-lite 两次 pass（**混轴**，见 `v1_0_readiness.md` §4）；另含 `m6` 的三控与"
                "破坏样本、oracle 与实例层 O1 矩阵、跨版本探针、适配赛道那一套。"
                "私有通道的夹具与标定**不公开**，这份包是内部签字用的完整记录。"),
    "public": ("**公开通道**（任务集轴 `p1.0.0`）。题面与私有逐字相同、**夹具字节不同**；"
               "结算读的是公开标定 / 公开网关日志 / 公开题集根（见 `m6_public__summary.md` "
               "顶部四行）。18 个 run 全部跑在**真公开 provider** 上（N-611，见 "
               "`m6_public__g1_public_provider_rerun.md`）。这份包 = 外部读者复现公开数字"
               "所需的全部表与报告。"),
}


def items_for(channel: str) -> tuple[str, ...]:
    """这条通道的归档清单（相对 `ops/reports/`）。"""
    if channel == "private":
        return SHARED_ITEMS + PRIVATE_ITEMS
    if channel == "public":
        return SHARED_ITEMS + PUBLIC_ITEMS
    raise KeyError(f"未知通道：{channel}")


def release_tables_for(channel: str) -> tuple[str, ...]:
    return RELEASE_TABLES_BY_CHANNEL[channel]


def diagnostic_tables_for(channel: str) -> tuple[str, ...]:
    return DIAGNOSTIC_TABLES_BY_CHANNEL[channel]


def dir_name_for(channel: str, set_version: str, reference_version: str) -> str:
    """归档目录名。

    私有沿用历史体例 `v<任务集>_<参考面>` —— `ops/test_wrapup.py` / `ops/test_V2.py` /
    `ops/test_V2rt.py` 三处都按这个式子**现算**路径，改名等于把三份测试一起改红，
    而它们问的是「当前轴上有没有签过字的包」，那个问题的答案不该因为改了命名体例而变。
    公开加 `public_` 前缀，且它的 `set_version` 本身就带 `p`（`p1.0.0`）——
    `public_vp1.0.0_r1.0.23` 一眼看得出通道与两条轴。
    """
    stem = f"v{set_version}_{reference_version}"
    return stem if channel == "private" else f"{channel}_{stem}"


def _dst_name(rel: str) -> str:
    """归档目录是平的，但文件名要保住出处：`m6/controls.md` 与 `m6_public/controls.md`
    同名不同物，都落成 `controls.md` 就是后者悄悄盖掉前者、而 MANIFEST 里两行都在。"""
    return rel.replace("/", "__")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


#: 任务集轴 `1.0.x` / `p1.0.x` 与参考轴 `r1.0.x` 的字面形状。
_AXIS_RE = re.compile(r"(?<![\w.])(r?p?1\.0\.\d+)(?![\w.])")


def _axis_mentions(p: Path) -> list[str]:
    """这个归档件的正文里提到了哪些版本轴。

    为什么要记：签字包是平的一堆文件，而其中**有些是生成的报告**——
    它们的正文里写着自己那一刻的四条版本轴。重冻之后没有重跑生成器的那几份，
    会带着**上一版**的轴被签进这一版的包里，而 `MANIFEST.json` 的
    `set_version` 只说包的轴、不说件的轴，读包的人对不出来。

    这是**如实登记，不是门** —— `VERSIONS.md` / `CHANGELOG` 这类文件本来就该
    列出历次版本，把它判成「陈旧」是错的。所以只记事实，由读的人判。
    """
    if p.suffix.lower() not in (".md", ".json", ".csv", ".tex", ".txt", ".yaml", ".yml"):
        return []
    try:
        txt = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return sorted(set(_AXIS_RE.findall(txt)))


def _axes(channel: str) -> tuple[str, str, str, str]:
    """(任务集版本, 任务集根, 参考面版本, 参考面根)。任务集轴按通道取，参考轴共用。"""
    ts = json.loads((_REPO / "ops" / "manifests" / _SET_MANIFEST[channel]).read_text(encoding="utf-8"))
    rf = json.loads((_REPO / "ops" / "manifests" / "v1.0-smoke.reference.json").read_text(encoding="utf-8"))
    from ops.freeze_v10 import reference_root
    return ts["set_version"], ts["root"], rf["reference_version"], reference_root(rf)


def _counterpart_dir(channel: str) -> str:
    """另一条通道那份包的目录名 —— 两份包互相指得到，读包的人才知道还有一份。"""
    other = "public" if channel == "private" else "private"
    o_sv, _sr, o_rv, _rr = _axes(other)
    return dir_name_for(other, o_sv, o_rv)


def _readme(channel: str, out: Path, label: str, manifest: dict) -> str:
    rows = []
    what = {
        "m6_all/table_main.csv": "**发布表**：⑩ 的固定十九列（`SR / P@1 / $` + 每阶段两列）",
        "m6_all/table_main.tex": "同上，LaTeX 形态",
        "m6_all/metrics_agent.csv": "**发布表**：⑫ 的全量 agent 指标表（18 项）",
        "m6_all/metrics_agent.md": "同上，Markdown 形态",
        "m6_all/metrics_stage.csv": "**发布表**：⑫ 的全量阶段指标表（六条跨阶段 + 39 条逐阶段）",
        "m6_all/metrics_stage.md": "同上，Markdown 形态",
        "m6_public/table_main.csv": "**发布表**：⑩ 的固定十九列，公开通道那一批",
        "m6_public/table_main.tex": "同上，LaTeX 形态",
        "m6_public/metrics_agent.csv": "**发布表**：⑫ 的全量 agent 指标表（18 项），公开通道",
        "m6_public/metrics_stage.csv": "**发布表**：⑫ 的全量阶段指标表，公开通道",
    }
    for rel in release_tables_for(channel):
        rows.append(f"| `{_dst_name(rel)}` | {what.get(rel, '**发布表**')} |")
    for rel in diagnostic_tables_for(channel):
        stem = Path(rel).stem                       # table_a / table_b —— 各自的 NOTE 各归各的
        rows.append(f"| `{_dst_name(rel)}` | **内部诊断表，不是发布件**（⑥-b）：带 `effect` 等归一列。"
                    "⑪ 裁定 effect **不进任何发布表** —— 归档它是留证据，不是给人引用。"
                    f"仓库里每份 `{stem}.csv` 旁边有一份 `{stem}.NOTE.md` 写着同一句话 |")
    other_ch = "public" if channel == "private" else "private"
    other = "公开" if other_ch == "public" else "私有"
    o_sv, _o_sr, o_rv, _o_rr = _axes(other_ch)
    other_dir = dir_name_for(other_ch, o_sv, o_rv)
    return "\n".join([
        f"# 签字包 {out.name}（{label}）—— {'私有' if channel == 'private' else '公开'}通道", "",
        f"* 通道 `{channel}`",
        f"* 任务集 `{manifest['set_version']}`（根 `{manifest['set_root'][:16]}…`）",
        f"* 参考面 `{manifest['reference_version']}`（根 `{manifest['reference_root'][:16]}…`）",
        f"* git HEAD `{manifest['git_head'][:12]}`", "",
        manifest["scope"], "",
        f"> **这份包只装本通道的件。**{other}通道那一份在 `ops/reports/signed/{other_dir}/`。",
        "> 两条通道的题面逐字相同、**夹具字节不同**，因此任务集轴不同、数不可直接合并 ——",
        "> 「可比」的判据是四条轴全部相同（见 `RELEASE_MANIFEST.json` 的 `axes.comparable_iff`）。",
        "> 跨通道通用的口径件（已知限制 / 报告规格 / 演练 / 投放说明 / 发布清单 / 版本轴 /",
        "> 协议子树清单）两份包里都有，且逐字节相同。", "",
        "## 哪张表能引用", "",
        "| 文件 | 是什么 |", "| --- | --- |", *rows, "",
        "## 口径与证据", "",
        "| 文件 | 是什么 |", "| --- | --- |",
        "| `report_spec_v1.md` | 十九列逐列的定义 / 数据源 / 闸门条件 / 不可得时显示什么 |",
        "| `known_limits_v1.md` | 已知限制表（两条通道的都在里面） |",
        "| `rehearsal_v2.md` | ⑭ 从零演练：只凭发布包 + 手册在一台干净机器上走通七步的逐步记录 |",
        "| `push_instructions.md` | ㉑ 的投放说明：推之前确认什么、推完做什么、四条不要做 |",
        "| `genequant__MANIFEST.json` | ㉑ 协议子树的封闭清单（逐件 sha256）；"
        "`RELEASE_MANIFEST.json` 的 `genequant.manifest_sha256` 指的就是它 |",
        "| `VERSIONS.md` | 四条版本轴的正文（含公开通道那一行）与历次变更 |", "",
        "文件全部 0400；逐文件 sha256 与两条版本轴在 `MANIFEST.json` 里。改过即对不上。", ""])


def emit(channel: str, label: str, force: bool) -> Path:
    """出一份签字包，返回它的目录。"""
    sv, sr, rv, rr = _axes(channel)
    out = ARCHIVE / dir_name_for(channel, sv, rv)
    if out.exists() and not force:
        raise SystemExit(f"{out} 已存在 —— 归档是不可变的。要重签就先推版本，或显式 --force")
    if out.exists():
        #: 包里的文件是 0400（归档不是工作副本），`copy2` 覆盖不了它们 ——
        #: `--force` 以前在**已经存在的**归档上一定 PermissionError，等于没有 force。
        #: 先放开写位再整目录删掉：重签就是重签，不是往旧包里塞新文件。
        for q in sorted(out.rglob("*"), reverse=True):
            try:
                q.chmod(0o600 if q.is_file() else 0o700)
            except OSError:                                    # noqa: PERF203
                pass
        shutil.rmtree(out)
    RIO.secure_dir(out)
    files: dict[str, str] = {}
    missing: list[str] = []
    taken: dict[str, str] = {}
    mentions: dict[str, list[str]] = {}
    todo = ([(r, _REPO / "ops" / "reports" / r) for r in items_for(channel)]
            + [(r, _REPO / r) for r in ROOT_ITEMS])
    for rel, src in todo:
        if not src.is_file():
            print(f"  缺件（清单里声明了、这一版不存在）：{rel}")
            missing.append(rel)
            continue
        name = _dst_name(rel)
        if name in taken:                      # 宁可拒绝归档，也不要一份「看起来齐全」的签字包
            raise SystemExit(f"归档文件名冲突：{rel} 与 {taken[name]} 都会落成 {name}")
        taken[name] = rel
        dst = out / name
        shutil.copy2(src, dst)
        dst.chmod(0o400)                       # 只读：归档不是工作副本
        files[rel] = _sha(dst)
        seen = _axis_mentions(dst)
        if seen:
            mentions[rel] = seen
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(_REPO),
                          capture_output=True, text=True, timeout=30).stdout.strip()
    manifest = {
        "label": label,
        "channel": channel,
        "set_version": sv, "set_root": sr,
        "reference_version": rv, "reference_root": rr,
        "git_head": head,
        "scope": _SCOPE[channel],
        "counterpart": _counterpart_dir(channel),
        "tables": {
            "release": list(release_tables_for(channel)),
            "internal_diagnostic": list(diagnostic_tables_for(channel)),
            "why": ("发布表 = ⑩ 的固定十九列（主表）+ ⑫ 的两张全量指标表，就这三种（⑥-b）。"
                    "诊断表带 `effect` 等聚合/归一列，⑪ 明写它们**不进发布表** —— "
                    "归档它们是为了留证据，不是为了给人引用；每份 `table_a.csv` 旁边"
                    "还有一份 `table_a.NOTE.md` 写着同一句话。"
                    "**卡 H**：一份包里只列本通道的表，两条通道的主表不再躺在同一个平目录里。"),
        },
        "files": files,
        "declared_but_missing": missing,
        "axis_mentions": mentions,
        "mentions_other_axes": sorted(
            rel for rel, vs in mentions.items()
            if any(v not in (sv, rv) for v in vs)),
        "axis_mentions_note": (
            "逐件登记正文里提到的版本轴。**这是事实登记不是判据** —— `VERSIONS.md` / "
            "`CHANGELOG` 本来就列历次版本。但一份**生成的报告**出现在 "
            "`mentions_other_axes` 里，多半是重冻之后没有重跑它的生成器，"
            "于是它带着上一版的轴被签进了这一版的包。"),
        "note": ("签字签的是这一版。报告是生成的，仓库里的那几份会被下一次跑批覆盖 —— "
                 "要引用「签过字的那份」就引用这里。文件 0400，改过即与 MANIFEST 的 sha 对不上。"),
    }
    RIO.write_json(out / "MANIFEST.json", manifest)
    (out / "MANIFEST.json").chmod(0o400)
    #: 包内 README：通道 + 哪张表是发布表、哪张是诊断表。归档目录是平的，文件名里看不出这两件事。
    (out / "README.md").write_text(_readme(channel, out, label, manifest), encoding="utf-8")
    (out / "README.md").chmod(0o400)
    print(f"[{channel}] 归档 {len(files)} 个文件 → {out}")
    print(f"  任务集 {sv}（根 {sr[:16]}…） / 参考面 {rv}（根 {rr[:16]}…） / HEAD {head[:12]}")
    if missing:
        print(f"  declared_but_missing：{len(missing)} 件 —— {', '.join(missing)}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="签字版")
    ap.add_argument("--channel", default="both", choices=(*CHANNELS, "both"),
                    help="出哪条通道的包；both（默认）= 两条通道**各出一份**，不是出一份混的")
    ap.add_argument("--force", action="store_true", help="目标已存在时覆盖（默认拒绝：归档是不可变的）")
    a = ap.parse_args(argv)
    for ch in (CHANNELS if a.channel == "both" else (a.channel,)):
        emit(ch, a.label, a.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
