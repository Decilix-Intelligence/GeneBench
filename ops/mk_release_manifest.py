#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 6.3：**发布清单**（`RELEASE_MANIFEST.json`）与 **CHANGELOG** 的生成器。

发布清单回答一个问题：**今天这个仓库能不能对外发？** 答案不是一句话，是一组可查的事实：

* 每一件发布件的 `sha256`（不存在的进 `missing`，**不静默丢**）；
* 四条版本轴的当前值与两条冻结轴的根 hash；
* 冻结线；
* 两份许可各自的状态（**数据**许可与**代码**许可是两件事，缺一都不能发）；
* 三件**挡发布**的事，逐条带证据路径与「怎样才算闭合」。

`releasable` 是**推导出来的，不是写上去的**：任何一件缺件、任何一条 blocker 未闭合、
任何一份许可未定 → `false`。**不允许手改这个字段** —— `ops/test_release_manifest.py`
会重算一遍并逐字段比对，而且**两个方向都查**（全满足时必须 true，逐条翻回去必须 false）。

**漂移分两类**（与 `ops/freeze_v10.py` 同一条纪律）：判据字段变了是**致命**，
某份生成件重跑一次换了 sha 只是**要重新生成清单** —— 「不一样」这三个字本身没有信息量。

用法::

    python ops/mk_release_manifest.py                 # 生成 RELEASE_MANIFEST.json
    python ops/mk_release_manifest.py --check         # 只比对，不写
                                                      #   0 一致
                                                      #   1 **判据变了**（能不能发的答案变了）
                                                      #   3 只有内容 sha 漂了（重新生成即可）
                                                      #   2 还没有落盘的清单
    python ops/mk_release_manifest.py --write-changelog   # 渲染 CHANGELOG.md

**CHANGELOG 不手抄**：它从 `ops/freeze_v10.py` 的 `REVISIONS` / `REFERENCE_REVISIONS`
渲染。那两个元组里各有一半不是自己轴的记录（历史遗留，见 :func:`split_revisions`），
渲染器按版本号前缀分轴，**并把这件事印在文件里**，不悄悄整理干净。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

MANIFEST = _REPO / "RELEASE_MANIFEST.json"
CHANGELOG = _REPO / "CHANGELOG.md"

#: 发布件清单，按用途分组。**声明在这里的每一件都要么有 sha256、要么进 `missing`。**
#: 分组名会原样进清单，外部用户按组读。
RELEASE_ITEMS: dict[str, tuple[str, ...]] = {
    "入口与许可": (
        "README.md", "VERSIONS.md", "CHANGELOG.md",
        "LICENSE", "DATA_LICENSE", "CITATION.cff",
    ),
    "数据卡": (
        "ops/data_cards/README.md",
        "ops/data_cards/qlib_provider.md", "ops/data_cards/universe_pit.md",
        "ops/data_cards/tradability.md", "ops/data_cards/gold_factors.md",
        "ops/data_cards/s7_backtest_gold.md", "ops/data_cards/public_channel.md",
        "ops/data_cards/fixture_s4_eco_pool_v1.md", "ops/data_cards/fixture_s6_signals.md",
        # Y1 ⑯：gold 只发子集，这张卡是「少了什么、还能不能复现」的答案
        "ops/data_cards/gold_subset_v1.md",
    ),
    "口径与协议": (
        "ops/specs/GeneBench指标规格_v1.md",
        "ops/specs/GeneBench指标对接决定_v1.md",
        "ops/specs/GeneBench秩相关与标定口径_v1.md",
        "ops/specs/metrics_as_implemented_v1.md",
        "ops/specs/fairness_protocol.md",
        "ops/specs/backtest_contract.md",
        "integrations/P2_CONTRACT.md",
    ),
    "artifact schema": tuple(
        f"ops/specs/artifact_schema/v1.0/S{k}.json" for k in range(1, 9)),
    "冻结清单": (
        "ops/manifests/v1.0-smoke.json",
        "ops/manifests/v1.0-smoke.reference.json",
    ),
    "报告": (
        "ops/reports/known_limits_v1.md",
        "ops/reports/v1_0_readiness.md",
        "ops/reports/validator_validation_v1.md",
        "ops/reports/calibration_spec_v1.md",
        "ops/reports/public/release_forms.md",
        # Y1 ⑭：有没有人只凭这个包 + 手册真的走过一遍 —— 外部用户会问的第二个问题
        "ops/reports/rehearsal_v2.md",
    ),
    # 外部用户必读的三件：README 的读者引导表分别把人送到这三处
    # （「要在自己的机器上把它跑起来」→ 运行者手册；「加一个 harness」→ harnesses/README；
    #  「有一个专用量化系统想作为被测方」→ integrations/README）。
    # **`ops/HANDOFF.md` 不在这一组**：它是**内部交接**文档（手册 §0 自己写明「口径以本手册为准」），
    # 混在「手册」里会让拿到包的人用清单去校验交接文档、而真正的手册根本不在清单里
    # （红队阶段六 major：OPERATOR_MANUAL 与 integrations/README 此前整个漏列）。
    # ㉑：协议工件那棵可独立发布的子树。清单只收它的**四件说明 + 封闭清单** ——
    # 逐件协议工件的 sha 在 `genequant/MANIFEST.json` 里，这里收的是那份清单本身。
    "协议子树（GeneQuant）": (
        "genequant/MANIFEST.json", "genequant/README.md",
        "genequant/PLACEMENT.md", "genequant/CITATION.cff",
    ),
    "手册": ("docs/OPERATOR_MANUAL.md", "harnesses/README.md", "integrations/README.md"),
    "内部交接（非面向外部运行者）": ("ops/HANDOFF.md",),
    # N-755 / N-778：**统一基座的构建上下文**。2026-09-13 的 Mac 外部验收正好卡在这里 ——
    # `harnesses/build.sh` 要求本机已有 `gb-base:bookworm-r1`，缺它时只让人去一台
    # 他没有的机器上找。这五件是「拿到这份清单的人自己构得出基座」的全部输入；
    # 清单不收它们 = 清单说交付完整，而基座仍然缺件。
    "统一基座构建上下文": (
        "build/README.md",
        "build/base/Dockerfile", "build/base/requirements.txt",
        "build/base/constraints.txt", "build/base/README.md",
    ),
}

#: 公开包声明必带的冻结件（gold 的定义面，「τ 标定于此实现对」）。
#: **单独成组**，因为它们的缺件是挡发布的事之一 —— 混进上面的组会读不出来。
#: （条数不写死在注释里：`blockers` 生成几条就是几条，2026-09-08 是四条。）
#: **⑥-b（2026-09-11 用户裁定）：诊断件不进发布件清单。**
#: 这里放的是**文件名**（不是路径）——  诊断表逐批都有一份，路径写不全。
#: `RELEASE_ITEMS` 现在一件都没有（结果表本来就不在发布件清单里，发布表在签字包的
#: `ops/archive_signoff.py::RELEASE_TABLES` 里登记）；这个常量是**一道门**，
#: 拦的是下一个「顺手把 table_a 加进清单」的人 —— 加进去不会报错，
#: 而清单是外部读者判断「哪些件是这一版发的」的唯一出处。
#: 判据：`ops/test_report_columns.py::test_table_a_is_never_a_release_table`。
DIAGNOSTIC_NOT_RELEASE: frozenset[str] = frozenset({
    "table_a.csv", "table_a.md", "table_a.tex",
    "table_b.csv", "table_b.md", "table_b.tex",
    "table_a.axes.json", "table_b.axes.json",
})


def diagnostic_items_in_release() -> list[str]:
    """发布件清单里混进来的诊断件（空 = 干净）。⑥-b 的可执行形态。"""
    return sorted(rel for items in RELEASE_ITEMS.values() for rel in items
                  if rel.rsplit("/", 1)[-1] in DIAGNOSTIC_NOT_RELEASE)


FROZEN_GROUP = "公开包冻结件（PUBLIC_FROZEN_ARTIFACTS）"

#: 数据许可的两种状态，与 `ops/test_env.py::LICENSE_STATES` 同源，**值不许分叉**。
LICENSE_STATES: tuple[str, ...] = ("pending_license_text", "granted")

FREEZE_LINE = "2026-07-31"

#: ㉑ 的两个目标仓库地址（用户 2026-09-11 裁定）。**这里是它们唯一的定义处** ——
#: README / CITATION / 发布清单 / 协议子树四处都从这里核对，各写一遍就会漂。
REPOSITORIES: dict[str, str] = {
    "genebench": "https://github.com/Decilix-Intelligence/GeneBench.git",
    "genequant": "https://github.com/Decilix-Intelligence/GeneQuant.git",
}

#: 协议子树（可独立发布的那棵）的清单与版本。**本体以这份清单的 sha 钉住它用的协议版本。**
GENEQUANT_MANIFEST = "genequant/MANIFEST.json"
GENEQUANT_VERSION = "v1"

#: 占位符的形状。判「地址定了没有」不能只判「这行里有没有一个像 URL 的东西」——
#: `<仓库地址：尚未公开>` 里也有尖括号和汉字，看着像个值。
_PLACEHOLDER = ("待用户填", "尚未公开", "占位符", "<地址", "<仓库地址", "TODO")


def clone_urls_declared(repo: Path) -> tuple[bool, str]:
    """**「有没有可 clone 的地址」的判据**（2026-09-11 换过一次，理由写在这里）。

    原判据是本地 `.git/config` 里有没有 `[remote `。它在「地址根本还没定」的阶段是对的，
    今天却判错了方向：**本地加一个 remote 既不让外部用户拿到仓库，也不是施工方该做的事**
    —— 那会把一棵内网工作树指向外网。推送由仓库所有者执行。

    换成两件**本地可查、且与外部用户真正会读的东西同源**的事实：

    1. 两个地址都是真地址（不是占位符）；
    2. **README 的 clone 步骤**与 **CITATION.cff 的 `repository-code`** 用的是同一个地址。

    刻意**不**查可达性（`git ls-remote`）：那会让这份清单的内容取决于跑它的机器有没有外网，
    于是同一棵树在两台机器上生成出两份不同的清单，而清单的 sha 是被测试钉住的。
    可达性是**推送那一刻**的事，证据留在 `ops/reports/push_instructions.md`。
    """
    readme = repo / "README.md"
    cit = repo / "CITATION.cff"
    for name, url in REPOSITORIES.items():
        if any(t in url for t in _PLACEHOLDER):
            return False, f"{name} 的地址还是占位符：{url}"
    if not readme.is_file() or REPOSITORIES["genebench"] not in readme.read_text(
            encoding="utf-8", errors="replace"):
        return False, "README.md 的 clone 步骤里没有那个真地址"
    if not cit.is_file():
        return False, "CITATION.cff 不在"
    line = next((x for x in cit.read_text(encoding="utf-8", errors="replace").splitlines()
                 if x.startswith("repository-code:")), "")
    if REPOSITORIES["genebench"] not in line or any(t in line for t in _PLACEHOLDER):
        return False, f"CITATION.cff 的 repository-code 没写成真地址：{line.strip() or '（没有这一行）'}"
    return True, "两个地址已定，README 与 CITATION.cff 两处一致"


def genequant_section(repo: Path) -> dict:
    """㉑ 第 2 条：**本体以 MANIFEST sha 钉住所用的 genequant 版本。**

    钉的是协议子树自己那份封闭清单（`genequant/MANIFEST.json`，逐件带 sha256），
    **不在这里把逐件 sha 再抄一遍** —— 抄一份就有两份要同步，而两份必然漂。
    「子树里那几件与 `ops/protocol/` 下的原件逐字节相同」由
    `ops/test_genequant_subtree.py` 两个方向查。
    """
    p = repo / GENEQUANT_MANIFEST
    return {
        "repository": REPOSITORIES["genequant"],
        "version": GENEQUANT_VERSION,
        "manifest_path": GENEQUANT_MANIFEST,
        "manifest_sha256": _sha(p) if p.is_file() else None,
        "protocols": ["geneprotocol_v1", "geneprotocol_v1_doc", "geneprotocol_v1_adapt"],
        "how_to_refresh": ("改了协议工件之后：ops/test_genequant_subtree.py --rebuild "
                           "→ 再跑本生成器。顺序倒过来的话清单钉的是上一版，而两边都不会红。"),
    }

#: **每跑一次生成器就会换一份 sha 的发布件。** 它们的内容漂移是正常的（报告是生成的，
#: 数据卡由代码渲染），**不是清单在撒谎**。发布前重跑一次 `mk_release_manifest.py` 即可。
#: 把它们与「手写件」分开，是为了让 `ops/test_release_manifest.py` 对手写件保持逐字节的判别力：
#: 一份手写件的 sha 对不上，那是真问题；`v1_0_readiness.md` 的 sha 变了，那只是它又跑了一次。
VOLATILE_ITEMS: frozenset[str] = frozenset({
    "ops/reports/v1_0_readiness.md",            # ops/readiness_report.py 现算
    "ops/reports/validator_validation_v1.md",   # 验证验证器报告，跑批后重出
    "ops/reports/calibration_spec_v1.md",       # ops/render_calibration_spec.py 现算
    "ops/data_cards/qlib_provider.md",          # snapshots/qlib_provider.py::render_data_card
    "ops/data_cards/universe_pit.md",           # snapshots/universe_build.py::render_data_card
    "ops/data_cards/tradability.md",            # snapshots/tradability.py
    "ops/data_cards/gold_factors.md",           # ops/mk_gold_data_card.py
    "ops/data_cards/fixture_s4_eco_pool_v1.md", # reference/make_fixtures.py
    "ops/data_cards/fixture_s6_signals.md",     # reference/make_fixtures.py
})

#: **判据字段**：这些变了意味着「能不能发」这个答案变了 —— `--check` 判致命（退出 1）。
#: `files` 不在其中：一份报告重跑一次就换 sha，那只要重生成清单（退出 3），
#: 与 `ops/freeze_v10.py` 区分「致命漂移」与「输入已变、题面未变」是同一条纪律。
FATAL_KEYS: tuple[str, ...] = ("axes", "freeze_line", "task_counts", "license",
                               "blockers", "missing", "releasable",
                               # ㉑：地址与协议 pin。协议工件悄悄变了要**停下来看**，
                               # 不是「某份报告又跑了一次」那一类 sha 漂。
                               "repository", "genequant",
                               # 裁定 ②：附件变了 = **外部用户下到的东西变了**，
                               # 那不是「某份报告又跑了一次」那一类 sha 漂，要停下来看。
                               "release_attachments")


class ReleaseManifestError(RuntimeError):
    pass


# ------------------------------------------------------------------ 工具

def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def frozen_artifacts() -> tuple[str, ...]:
    from snapshots.public import manifest as PM
    return tuple(PM.PUBLIC_FROZEN_ARTIFACTS)


def data_license_state(repo: Path | None = None) -> str:
    """读 `DATA_LICENSE` 顶部的状态。**解析口径与 `ops/test_env.py` 一字不差。**"""
    f = (repo or _REPO) / "DATA_LICENSE"
    if not f.is_file():
        raise ReleaseManifestError("仓库根缺 DATA_LICENSE")
    txt = f.read_text(encoding="utf-8")
    hits = [s for s in LICENSE_STATES if f"`{s}`" in txt or f"**状态：`{s}`**" in txt]
    if not hits:
        raise ReleaseManifestError(f"DATA_LICENSE 里读不出状态（应为 {LICENSE_STATES} 之一）")
    return hits[0]


#: 许可正文的落点。**目录非空的唯一含义是「正文到了」** —— 不许放占位/说明文件充数
#: （`DATA_LICENSE` §2.1 与 `ops/test_env.py::LICENSE_TEXT_DIR` 同一个口径）。
LICENSE_TEXT_DIR = ("ops", "terms", "baostock", "permission")


def official_license_text_in_repo(repo: Path | None = None) -> bool:
    """baostock 的**书面正文**在不在库。

    **这一条刻意不从状态字段推**。2026-09-11 的裁定把两件事拆开了：
    授权已经取得（顶部状态 `granted`，摘要在 `DATA_LICENSE` §2.0），
    而许可方出具的**正文**还没到（§2.1 是一处显式占位）。
    旧实现写的是 `text_in_repo = (state == "granted")` —— 状态一翻，
    这个字段就跟着说「正文在库」，而它是清单里唯一回答「有没有文件可查」的地方。
    **一个从来不看文件的「文件在不在」字段，比没有这个字段更坏。**
    """
    d = (repo or _REPO).joinpath(*LICENSE_TEXT_DIR)
    return d.is_dir() and any(d.iterdir())


def code_license_id(repo: Path | None = None) -> str:
    """读 `LICENSE` 的 SPDX 标识。**未定时返回 `<待定>`，不猜一个许可。**

    伪造一个许可比没有许可更糟：外部用户会照着它做出分发决定。
    """
    f = (repo or _REPO) / "LICENSE"
    if not f.is_file():
        return "<缺文件>"
    m = re.search(r"SPDX-License-Identifier:\s*(\S+)", f.read_text(encoding="utf-8"))
    return m.group(1) if m else "<无 SPDX 行>"


def code_license_decided(spdx: str) -> bool:
    """许可算不算「已定」。`<待定>` / `<缺文件>` / `<无 SPDX 行>` 一律不算。"""
    return bool(spdx) and not spdx.startswith("<")


# ------------------------------------------------------------------ 挡发布的三件事

def public_channel_runs(repo: Path | None = None) -> tuple[int, int] | None:
    """公开通道**结算出来的 run**：`(有 run_id 的条数, 总条数)`。没有产物 → `None`（不适用）。

    出处 2026-09-13（卡 P1）从 `$GENEBENCH_ROOT/runs_in/m6_public/jobs.jsonl`
    换成了**仓库里**的 `ops/reports/m6_public/records.json`。理由与
    `clone_urls_declared` 的 docstring 是同一条：**这份清单的内容不许取决于跑它的那台机器**。
    跑批清单落在 `$GENEBENCH_ROOT` 下、**不进仓库**，于是任何 clone 上这一条都读成
    「不适用」、而发布方那台读成「18 / 18」—— 同一棵树在两台机器上生成出两份不同的清单，
    `blockers` 又在 `FATAL_KEYS` 里，`--check` 因此在**每一个外部 clone 上**退 1。
    2026-09-13 的 Mac 外部验收实测到的正是这一条（README §5 把退 1 定义成「判据变了，停下」）。

    换出处不换结论：这条 blocker 要的是**背书**（公开通道到底跑出过 run 没有），
    而结算产物 `records.json` 正是那份背书，并且它随树走。两个数取自同一份记录，
    所以「有 run 的条数 == 总条数」是常态；判据仍然**反向可证伪** ——
    一条记录都没有（文件不在、不是表、或空表）就不满足。
    """
    p = (repo or _REPO) / "ops" / "reports" / "m6_public" / "records.json"
    if not p.is_file():
        return None
    try:
        recs = json.loads(p.read_text(encoding="utf-8"))
    except Exception:                                                  # noqa: BLE001
        return None
    if not isinstance(recs, list):
        return None
    return sum(1 for r in recs if isinstance(r, dict) and r.get("run_id")), len(recs)


def blockers(repo: Path, missing: list[str], dl_state: str, spdx: str) -> list[dict]:
    """四件挡发布的事 + 代码许可。**逐条给「怎样才算闭合」，不写「见某某内部票据」。**"""
    pub = public_channel_runs(repo)
    has_remote = bool((repo / ".git" / "config").is_file()
                      and re.search(r"^\[remote ", (repo / ".git" / "config").read_text(
                          encoding="utf-8", errors="replace"), re.M))
    declared_ok, declared_why = clone_urls_declared(repo)
    frozen_missing = [m for m in missing if m in set(frozen_artifacts())]
    return [
        {
            "id": "data_license_text",
            "what": "baostock 的书面再分发许可（**授权**取得没有）",
            "status_now": (f"DATA_LICENSE = `{dl_state}`；许可方出具的正文"
                           + ("已入库" if official_license_text_in_repo(repo)
                              else "**仍未入库**，DATA_LICENSE §2.1 是一处显式占位")),
            # 2026-09-13 卡 W（N-745）：这段对外正文按已发布的事实改写。原文写的是
            # 2026-09-06 那一轮的形态，三句到 2026-09-13 已全部不成立：
            #   ① `$GB/release/_staging_unpublished/` 卡 R2 按 N-714 整棵删了；
            #   ② 包内 `MANIFEST.license.publishable` 实测是 `true`；
            #   ③ 两件附件 2026-09-13 已发布，匿名（不带 token）`Range` GET 实测 **206**，
            #      「外部用户拿不到包」正好说反。
            # 这一条 `satisfied` 判的是**授权**（`dl_state == "granted"`），不是正文，
            # 所以它本来就不闸任何东西 —— **判定逻辑不动**，只改这段会被人当真的正文。
            "blocks": "许可正文仍未入库（DATA_LICENSE §2.1 是显式占位）；"
                      "形态 A 已按 2026-09-13 裁定发布为 Release v1.0.16 的附件、"
                      "匿名可下，不再阻断下载",
            # 2026-09-11 裁定 ⑨：闭合判据是**授权**，不是**正文**。两件事被拆开的理由
            # 写在 DATA_LICENSE 顶部：授权决定「能不能发」，正文决定「有没有文件可查」。
            # 正文那一步没有消失 —— 它记在 DATA_LICENSE §2.1 的占位里，删掉占位而不放正文
            # 就是把「有人口头说过」写成了「有文件可查」。
            "closes_when": "顶部状态为 granted 且 DATA_LICENSE §2.0 写明授权范围"
                           "（用途 / 允许的行为 / 署名要求）；"
                           "**正文到位是后续一步**：放进 ops/terms/baostock/permission/ 之后，"
                           "把 §2.1 的占位换成对它的文件名/日期/签署方的引用",
            "evidence": ["DATA_LICENSE", "ops/reports/public/release_forms.md",
                         "ops/terms/baostock/index.json"],
            "satisfied": dl_state == "granted",
        },
        {
            "id": "no_clone_url",
            "what": "仓库**没有可 clone 的地址**",
            # 两种证据都算：本地配了 remote，或者地址已定且写进了外部用户真会读的两处。
            # 后者才是这个 blocker 真正要的东西 —— 一个只存在于本机 .git/config 里的 remote
            # 对拿到包的人毫无用处。判据的完整理由见 `clone_urls_declared` 的 docstring。
            # 2026-09-13 卡 P1（用户裁定 ②）：这一格**不许取决于本树有没有 remote**。
            # 内网 `$GB/repo` 没有远端，而**任何 clone 都有 origin** —— 于是同一棵树
            # 在两台机器上生成出两份不同的清单；`blockers` 在 `FATAL_KEYS` 里，
            # `--check` 因此在每一个外部 clone 上退 1，而 README §5 把退 1 定义成
            # 「判据变了（停下）」。判据本身的完整理由见 `clone_urls_declared` 的 docstring：
            # 刻意不查与「跑它的那台机器」有关的事实。
            # 判别力见 `ops/test_P1.py::test_清单在有remote与没有remote的同一棵树上逐字节相同`。
            "status_now": declared_why,
            "blocks": "形态 B（用户自建）：第一步是「拿一份完整仓库」，"
                      "地址是占位符时这一步走不下去",
            # 2026-09-13 卡 W2（N-793）：末句原文引用的 `release/_staging_unpublished/`
            # 已按 N-714 整棵删除，对读者是一条指向不存在目录的线索。`closes_when` 记的是
            # **当年靠什么关掉它**，所以措辞改、判据不动（`satisfied` 那一格一个字没碰）。
            "closes_when": "给出两个真地址并写进 README 的 clone 步骤与 CITATION.cff 的 "
                           "repository-code（本清单的 repository / genequant.repository 与它们同源）；"
                           "**推送本身由仓库所有者执行**，推完再按新地址重打一次公开包"
                           "（当年那批打包前的中间件里留着写占位符的旧 README）",
            "evidence": ["README.md", "CITATION.cff", "ops/reports/push_instructions.md",
                         "ops/reports/public/release_forms.md"],
            # `satisfied` 这一格保留「本地有 remote」作为**第二条证据**：真树上判据本身
            # （地址已定、README 与 CITATION.cff 两处一致）就是 True，两条路给同一个答案，
            # 所以清单的内容仍然与机器无关；而 `ops/test_release_manifest.py` 的反向判别力
            # （假仓库 remote=False ⇒ 挡住发布）靠的正是这一格。
            "satisfied": has_remote or declared_ok,
        },
        {
            "id": "frozen_artifacts_missing",
            "what": "PUBLIC_FROZEN_ARTIFACTS 声明的冻结件缺件",
            "status_now": (f"缺 {len(frozen_missing)} 件：{frozen_missing}"
                           if frozen_missing else "全部到位"),
            "blocks": "缺的是 gold 的**定义面**（「τ 标定于此实现对」）——"
                      "少了它们，拿到包的人**复现不了 τ**",
            "closes_when": "把 factor_library/compiled/ 三个 jsonl 补齐，"
                           "或改 snapshots/public/manifest.py 的清单并说明为什么不需要",
            "evidence": ["snapshots/public/manifest.py",
                         "ops/reports/public/release_forms.md"],
            "satisfied": not frozen_missing,
        },
        {
            "id": "public_channel_zero_runs",
            "what": "**公开通道的真跑背书** —— `m6_public` 的 18 行清单立项时全是 `pending`",
            "status_now": ("不适用（本树不是数据面仓库，或没有 m6_public 清单）" if pub is None
                           else f"m6_public：{pub[0]} 个有 run 的行 / 共 {pub[1]} 行"),
            "blocks": "公开通道的就绪报告 §4 / §4b 渲染不出逐 run 证据（报告自己说了）——"
                      "「外部用户按手册跑得通」这条在**公开通道**上没有实测背书。"
                      "不挡外部用户自己跑",
            "closes_when": "`$PY ops/run_joblist.py --jobs $GB/runs_in/m6_public/jobs.jsonl --resume` "
                           "至少跑出一个 run 并结算入库，再重出 "
                           "`ops/reports/m6_public/v1_0_readiness_public.md`",
            "evidence": ["ops/reports/m6_public/README.md",
                         "ops/reports/m6_public/v1_0_readiness_public.md"],
            "satisfied": pub is None or pub[0] > 0,
        },
        {
            "id": "code_license_undecided",
            "what": "**代码许可未定** —— 这是用户的决定，不由施工方替他选",
            "status_now": f"SPDX-License-Identifier: {spdx}",
            "blocks": "整个仓库的对外分发：没有许可的代码，别人不知道能不能用",
            "closes_when": "用户选定一个许可（建议 Apache-2.0 或 MIT，差别写在 LICENSE 里），"
                           "把 SPDX 行与正文换成该许可的原文",
            "evidence": ["LICENSE"],
            "satisfied": code_license_decided(spdx),
        },
    ]


# ------------------------------------------------------------------ 清单


# ------------------------------------------------------------------ ⑯ 包体与 gold 子集

#: 包体盘点与 gold 子集的现算产物。**清单只引用、不重算** ——
#: 重算要扫 15 GB 的 gold，而清单是每次发布前都要跑的东西。
PACKAGE_INVENTORY = "ops/reports/i_rehearsal_v2/package_inventory.json"
GOLD_SUBSET = "ops/reports/i_rehearsal_v2/gold_subset.json"

#: 2026-09-13 卡 W（N-745）：`package_inventory.json` 是 2026-09-06 那一轮演练的**存档件**，
#: 里面「形态 A」那一条的三处字面量到今天全部过时 ——
#:   `publishable=false` → 包内 `MANIFEST.license.publishable` 实测 `true`；
#:   「许可到位后发」    → 2026-09-13 **已经发了**（Release `v1.0.16` 的附件，匿名可下）；
#:   `788,422,669` B     → 那是卡 R2 按 N-714 **删掉**的 `_staging_unpublished` 旧包，
#:                         已发布的 provider 是 `782,100,276` B。
#: **存档件不改**（它是那一轮的留证，且改了要连带重算它的 sha），
#: 在这里按已发布的事实改写**清单里的对外正文**。`RELEASE_MANIFEST.json` 是机器可读的权威件，
#: 这三条里任何一条都够让读许可条款的人对「这个包到底能不能用」判反（卡 V 2026-09-13 实测）。
#: 键用存档件里的 `path` 而不是 `part` 文本 —— 文本会被本表改掉，路径不会。
PART_OVERRIDES: dict[str, dict] = {
    "release/_staging_unpublished/public_v1": {
        "part": "已打好的公开数据包（形态 A）—— **2026-09-13 已发布**",
        "bytes": 782100276,
        "ship": "**已发布**：Release `v1.0.16` 的附件 "
                "`genebench_public_provider_v1.tar.gz`，匿名可下（不需要 token）；"
                "包内 `MANIFEST.license.publishable=true`",
    },
}

#: **发布附件登记表**（由 `ops/release/pack_public_provider.py` 与
#: `ops/release/pack_gold_subset.py` 写）。两个附件落在 `$GB/release/<public>/` ——
#: 那是机器本地路径，仓库里看不到。清单要逐件记附件的 `sha256`，出处就是这张表。
ATTACHMENTS = "ops/release/attachments.json"

#: 一件附件在清单里要记全的字段。**少一项就是让下载的人答不出一个问题**：
#: 我下到的这个 tar.gz 是不是你们发的那一个（`name`/`bytes`/`sha256`）、
#: 它是从哪一版代码打出来的（`code_head`/`built_at`）、
#: 它属于哪四条轴（`axes`）、上哪儿下（`download_url`，上传后回填）。
ATTACHMENT_FIELDS: tuple[str, ...] = (
    "name", "role", "what", "bytes", "sha256", "files_inside", "bytes_inside",
    "built_at", "code_head", "axes", "download_url")


def release_attachments_section(repo: Path) -> dict:
    """GitHub Release 的附件逐件登记。**没打包就如实说没打**，不猜一个数。

    `download_url` 是空串时 `uploaded` 记 0 —— 「还没上传」与「上传了但地址没记」
    在这里是同一件事，都当没上传。回填由上传那一步做。
    """
    out: dict = {"source": ATTACHMENTS,
                 "note": "由两个打包脚本生成；download_url 在上传到 GitHub Release 之后回填"}
    p = repo / ATTACHMENTS
    if not p.is_file():
        out["attachments"] = []
        out["n"] = 0
        out["uploaded"] = 0
        out["state"] = ("缺件 —— 还没打包（ops/release/pack_public_provider.py / "
                        "ops/release/pack_gold_subset.py）")
        return out
    d = json.loads(p.read_text(encoding="utf-8"))
    rows = [{k: a.get(k) for k in ATTACHMENT_FIELDS} for a in d.get("attachments", [])]
    rows.sort(key=lambda r: r.get("name") or "")
    out["attachments"] = rows
    out["n"] = len(rows)
    out["uploaded"] = sum(1 for r in rows if r.get("download_url"))
    out["state"] = "已打包" if rows else "登记表是空的"
    return out

#: 最低配置。**每一条都要说得出出处** —— 没有出处的最低配置是猜的，
#: 而拿到包的人会照着它去准备机器。口径与 `docs/OPERATOR_MANUAL.md` §0.0、
#: `README.md` §1.5 同源（`ops/test_y1_rehearsal.py` 盯着三处不分叉）。
MIN_SPEC: dict = {
    "ram_data_plane_gb": {"min": 16, "why": "网关常驻 ≈ 2.3 GB；一道 S7 真题把它顶过 6 GB 上限并触发 4 次 oom-kill，上限现为 12 GiB"},
    "ram_data_plane_rebuild_gb": {"min": 30, "why": "run_public_chain 的 gold 重算：792 个面板常驻 22 GiB"},
    "ram_exec_plane_gb": {"min": 16, "why": "一次真跑起两个容器"},
    "ram_single_node_gb": {"min": 30, "why": "上面两条相加的上界"},
    "disk_gb": {"min": 50, "rebuild": 200, "why": "包解开 1.52 GiB；每个 run 目录约 600 MB（逐 run 物化 provider 树）"},
    "docker": {"min": "24 + compose v2", "tested": "29.1.3 / compose 2.40.3",
               "why": "纯数据面那台不需要 docker"},
    "python_data_plane": {"min": "3.10", "tested": "3.10 与 3.12",
                          "deps": ["fastapi", "uvicorn", "pandas", "pyarrow", "duckdb", "pyyaml"],
                          "why": "仓库里没有 requirements 文件，六个包是演练里试出来的（手册 §1.2）"},
}


def package_section(repo: Path) -> dict:
    """发布包有多大、gold 发的是哪一份。**两件产物缺了就如实说缺**，不猜一个数。"""
    out: dict = {"min_spec": MIN_SPEC,
                 "inventory_source": PACKAGE_INVENTORY, "gold_subset_source": GOLD_SUBSET}
    inv_p, sub_p = repo / PACKAGE_INVENTORY, repo / GOLD_SUBSET
    if inv_p.is_file():
        inv = json.loads(inv_p.read_text(encoding="utf-8"))
        out["totals_bytes"] = inv.get("totals")
        # 覆盖表键错了就当场停，不许静默无操作 —— 存档件换了形状要有人知道。
        stray = sorted(set(PART_OVERRIDES) - {p.get("path") for p in inv.get("parts", [])})
        assert not stray, f"PART_OVERRIDES 里有存档件已经没有的 path：{stray}"
        out["parts"] = [dict({k: p[k] for k in ("part", "bytes", "ship")},
                             **PART_OVERRIDES.get(p.get("path") or "", {}))
                        for p in inv.get("parts", [])]
    else:
        out["inventory"] = "缺件"
    if sub_p.is_file():
        d = json.loads(sub_p.read_text(encoding="utf-8"))
        out["gold"] = {
            "ships": "subset",
            "why": "全量超过 5 GB 的发布线（裁定 ⑯）",
            "n_factors": d.get("n_factors"),
            "limitation": (d.get("rule") or {}).get("limitation"),
            "data_card": "ops/data_cards/gold_subset_v1.md",
            "channels": {k: {"n_files": v["n_files"], "bytes": v["bytes"],
                             "full_bytes": v["full_bytes"],
                             "missing": len(v["missing"]),
                             "list_sha256": hashlib.sha256(
                                 "".join(f"{f['rel']}\0{f['sha256']}\n"
                                         for f in v["files"]).encode()).hexdigest()}
                         for k, v in (d.get("channels") or {}).items()},
        }
    else:
        out["gold"] = "缺件"
    return out


def build(repo: Path | None = None) -> dict:
    repo = repo or _REPO
    from ops import freeze_v10 as F

    groups: dict[str, tuple[str, ...]] = dict(RELEASE_ITEMS)
    groups[FROZEN_GROUP] = frozen_artifacts()

    files: dict[str, dict] = {}
    missing: list[str] = []
    for group, items in groups.items():
        for rel in items:
            p = repo / rel
            if p.is_file():
                files[rel] = {"group": group, "sha256": _sha(p), "bytes": p.stat().st_size}
            else:
                missing.append(rel)
                files[rel] = {"group": group, "sha256": None, "bytes": None}

    ts = json.loads((repo / "ops" / "manifests" / "v1.0-smoke.json").read_text(encoding="utf-8"))
    rf = json.loads((repo / "ops" / "manifests" / "v1.0-smoke.reference.json").read_text(encoding="utf-8"))
    #: 公开通道那条任务集轴（裁定 ①）。`channels` 里列着 public 却不给它的版本号与根，
    #: 等于让公开树的持有者答不出「我这份是哪条公开轴」（红队最终轮 major 6）。
    ps = json.loads((repo / "ops" / "manifests" / "v1.0-smoke-public.json").read_text(encoding="utf-8"))

    dl = data_license_state(repo)
    spdx = code_license_id(repo)
    bl = blockers(repo, missing, dl, spdx)
    releasable = (not missing) and all(b["satisfied"] for b in bl)

    return {
        "schema_version": 1,
        "generated_by": "ops/mk_release_manifest.py",
        "note": ("`releasable` 是推导出来的：任何缺件、任何未闭合的 blocker、"
                 "任何一份未定的许可 → false。手改这个字段会被 "
                 "ops/test_release_manifest.py 当场抓到。"),
        "axes": {
            "set_version": ts["set_version"], "set_root": ts.get("root"),
            #: **公开通道有自己的一条任务集轴**（裁定 ①）：题面与私有逐字相同，
            #: 换掉的是集名、版本号、记因，外加夹具真值进根 —— 所以根不同、版本号不同。
            "public_set_version": ps["set_version"], "public_set_root": ps.get("root"),
            "reference_version": rf["reference_version"],
            "reference_root": F.reference_root(rf),
            "protocol_version": "geneprotocol_v1@<逐 run 反算，见 VERSIONS.md §1.3>",
            "channels": ["private", "public"],
            "comparable_iff": "四条轴全部相同",
        },
        "package": package_section(repo),
        # 裁定 ②：两个附件逐件 sha256 进清单。**外部用户校验包体的唯一权威出处**。
        "release_attachments": release_attachments_section(repo),
        # ㉑：两个仓库地址与协议 pin。`repository` 是本体的 clone 地址，
        # `genequant` 那段回答「这份基准用的是协议的哪一版」。
        "repository": REPOSITORIES["genebench"],
        "genequant": genequant_section(repo),
        "freeze_line": FREEZE_LINE,
        "task_counts": ts.get("counts"),
        "license": {
            # 授权与正文**分开记**（裁定 ⑨）：`state` 说授权，
            # `official_text_in_repo` 说文件 —— 后者现算，不从前者推。
            "data": {"state": dl, "file": "DATA_LICENSE",
                     "grant_summary": "研究用途；允许再分发派生日线数据；署名 baostock",
                     "official_text_in_repo": official_license_text_in_repo(repo),
                     "official_text_dir": "/".join(LICENSE_TEXT_DIR)},
            "code": {"spdx": spdx, "file": "LICENSE", "decided": code_license_decided(spdx)},
        },
        "blockers": bl,
        "missing": sorted(missing),
        "releasable": releasable,
        "files": dict(sorted(files.items())),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def classify_drift(cur: dict, old: dict) -> tuple[list[str], list[str]]:
    """把漂移分成两类：**判据变了**（致命）与**内容重生成了**（重跑一次即可）。

    返回 `(fatal_keys, sha_drift_paths)`。分类的意义与 `ops/freeze_v10.py` 一样：
    「不一样」这三个字本身没有信息量 —— 要说清是「能不能发的答案变了」
    还是「某份报告又跑了一次」。
    """
    fatal = [k for k in FATAL_KEYS if cur.get(k) != old.get(k)]
    drift = sorted(k for k in set(cur.get("files", {})) | set(old.get("files", {}))
                   if (cur.get("files", {}).get(k) or {}).get("sha256")
                   != (old.get("files", {}).get(k) or {}).get("sha256"))
    return fatal, drift


#: VERSIONS.md 正文里**加粗的**版本号与**根前缀**：`**1.0.15**` / `**`r1.0.22`**` / `` `622f720c…` ``。
#: 公开轴的版本号是 `p1.0.0` —— 正则里漏掉 `p` 前缀，公开那一行的加粗版本号就**一个都匹配不到**，
#: 于是「写错了也不报」。三条轴的前缀：私有无、参考面 `r`、公开 `p`。
_BOLD_VERSION = re.compile(r"\*\*`?([rp]?\d+\.\d+\.\d+)`?\*\*")
_ROOT_PREFIX = re.compile(r"`([0-9a-f]{16})…`")


def versions_doc_drift(axes: dict, repo: Path | None = None) -> list[str]:
    """`VERSIONS.md` **正文**里的四轴字符串 vs `axes` 段。不一致就逐条说清。

    为什么要单独查这一条（红队 V2.rt finding 2）：`VERSIONS.md` 是四条轴的**权威文档**，
    而没有任何一道门读它的**正文**。`genebench_cli.py axes` 比的是「清单声明 vs 现算值 vs
    代码常量」；文件完整性比的是 sha，而清单是在文件之后生成的，所以文件里写错了版本号，
    sha 照样对得上。结果是 2026-09-10 之后正文停在 1.0.14 / r1.0.21，而别处全是 1.0.15 /
    r1.0.22 —— 唯一一份说错的文件，恰好是 CHANGELOG 顶部指着读者去看的那一份。

    判法：扫每一张表里第一格含「任务集」/「参考面」的行，行内**加粗的**版本号必须等于
    该轴的当前值，行内出现的**根前缀**必须等于该轴现算根的前 16 位。
    只认加粗与反引号形态 —— 正文里讲历史时提到旧版本号是正常的，不该被判成漂移。
    """
    repo = Path(repo or _REPO)
    doc = repo / "VERSIONS.md"
    if not doc.is_file():
        return [f"{doc} 不存在 —— 四条轴没有权威文档"]
    want = {"任务集": axes["set_version"], "参考面": axes["reference_version"],
            #: 公开任务集轴（裁定 ①）。**它必须在这份权威文档里看得见** ——
            #: 拿到公开树的人要核的正是这一条，而 `set_version` 那一行答的是私有轴。
            "公开任务集": axes.get("public_set_version")}
    root = {"任务集": str(axes["set_root"])[:16], "参考面": str(axes["reference_root"])[:16],
            "公开任务集": str(axes.get("public_set_root"))[:16]}
    #: 公开轴的行长什么样：第一格里同时有「任务集」与「公开」。判公开**优先于**判私有，
    #: 否则公开那一行会被当成私有轴的行，拿 p1.0.0 的根去比 1.0.16 的根。
    def _axis_of(cell: str) -> str | None:
        if "任务集" in cell and "公开" in cell:
            return "公开任务集"
        if "任务集" in cell:
            return "任务集"
        if "参考面" in cell:
            return "参考面"
        return None

    #: 当前值表与 §4 历史表各一行 —— 三条轴都按这个数要求（公开轴 2026-09-12 起同样两处）。
    need = {"任务集": 2, "参考面": 2, "公开任务集": 2}
    bad: list[str] = []
    seen = {k: 0 for k in want}
    for line in doc.read_text(encoding="utf-8").splitlines():
        cells = line.split("|")
        if len(cells) < 3 or not line.lstrip().startswith("|"):
            continue
        axis = _axis_of(cells[1])
        for _ in ([axis] if axis else []):
            seen[axis] += 1
            for got in _BOLD_VERSION.findall(line):
                if got != want[axis]:
                    bad.append(f"VERSIONS.md 的「{axis}」行写着 **{got}**，axes 段是 {want[axis]}")
            for got in _ROOT_PREFIX.findall(line):
                if got != root[axis]:
                    bad.append(f"VERSIONS.md 的「{axis}」行写着根 `{got}…`，现算根是 `{root[axis]}…`")
    for axis, n in seen.items():
        if n < need[axis]:
            bad.append(f"VERSIONS.md 里只找到 {n} 行「{axis}」—— 当前值表与 §4 历史表至少各一行")
    return bad


def _comparable(m: dict) -> dict:
    """去掉每次生成都会变的字段，供 `--check` 逐字段比对。"""
    return {k: v for k, v in m.items() if k != "generated_at"}


# ------------------------------------------------------------------ CHANGELOG

def split_revisions() -> tuple[list[dict], list[dict]]:
    """把两个记因元组按**版本号前缀**分回两条轴。

    历史遗留（不整理、只说明）：`ops/freeze_v10.py` 的 `REFERENCE_REVISIONS` 里
    **同时**放着任务集轴的记录（`1.0.7` / `1.0.8` … `1.0.13`）—— 拆轴之后新加的
    任务集记录写进了参考元组。按前缀 `r` 分轴是唯一不改冻结根就能分对的办法；
    改那两个元组要动 `ops/freeze_v10.py`（冻结面的代码），是另一回事。
    """
    from ops import freeze_v10 as F
    both = list(F.REVISIONS) + list(F.REFERENCE_REVISIONS)
    ref = [r for r in both if str(r.get("version", "")).startswith("r")]
    task = [r for r in both if not str(r.get("version", "")).startswith("r")]
    return task, ref


def _key(rev: dict) -> tuple:
    """版本号里的数字序，用于倒序。解析不出来的排最前（它们是带说明的特殊条目）。"""
    nums = re.findall(r"\d+", str(rev.get("version", "")))
    return tuple(int(x) for x in nums[:3]) if nums else (0, 0, 0)


def _render_axis(title: str, revs: list[dict]) -> list[str]:
    out = [f"## {title}", ""]
    for r in sorted(revs, key=_key, reverse=True):
        out.append(f"### `{r.get('version')}` — {r.get('at', '?')}　（票据 {r.get('ticket', '—')}）")
        out.append("")
        for label, key in (("**为什么**", "why"), ("**改了什么**", "what"),
                           ("**射程**", "scope"), ("**闸门 / 证据**", "gates")):
            v = r.get(key)
            if v:
                out.append(f"* {label}：{v}")
        out.append("")
    return out


MILESTONES = (
    ("M0", "环境闸门与湖基线", "落点、权限红线、数据湖只读基线；`ops/test_env.py` 的递归权限审计从这里开始"),
    ("M1", "数据面：宇宙 / 可交易性 / as-of 网关 / 快照表",
     "`universe_pit`（三源合成 + 在市窗口闸门）、`tradability`（五档互斥 status）、"
     "只读 HTTP 网关（绑显式地址，不绑 0.0.0.0）"),
    ("M2", "冻结 provider + gold + τ/ε 标定 + artifact schema",
     "自建 qlib provider（日历里**物理上没有**冻结线之后的交易日）、三宇宙 792 因子的 gold、"
     "τ = 0.984006、ε 分档（只有 daily 可用）、八阶段 artifact schema v1.0"),
    ("M3", "出题与打包：v1.0 冒烟集冻结",
     "40 题起草 / 34 题出集；冻的是**输入**（模板 + 措辞表 + 参数表 + 渲染器代码），不是渲染产物"),
    ("M4", "runner 隔离拓扑、出向白名单、两臂注入器",
     "容器隔离、出向代理只放模型 API 域名、两臂 work/ 文件集的**等号**判据"),
    ("M5", "结算面：闸门 + L3 + 主表", "有效性闸门语义（invalid 而非低分）、四种 L3 比法、Table A/B"),
    ("M6", "跑批与结果库", "作业清单 → 结果库（四条版本轴缺一即拒）→ 三张表（混轴默认拒绝出表）"),
    ("阶段一~六", "从「跑得起来」到「可分发」",
     "公开数据通道、三范式接入、通用 harness、臂机制与适配赛道、跑批与结果库、发布件"),
)


def render_changelog() -> str:
    from ops import freeze_v10 as F
    task, ref = split_revisions()
    lines = [
        "# CHANGELOG",
        "",
        "> **本文件是渲染出来的，不要手改。**",
        "> 生成器 `ops/mk_release_manifest.py --write-changelog`，",
        "> 数据源 `ops/freeze_v10.py` 的 `REVISIONS` / `REFERENCE_REVISIONS`。",
        "> 想改一条记录就去改那两个元组 —— 那里才是「这两次运行为什么不可比」的答案所在。",
        "",
        f"当前：任务集 **{F.SET_VERSION}** / 参考面 **{F.REFERENCE_VERSION}**。",
        "四条版本轴与「可比」的定义见 [`VERSIONS.md`](VERSIONS.md)。",
        "",
        "> **一处历史遗留，照实说**：拆轴之后新增的**任务集**记录写进了",
        "> `REFERENCE_REVISIONS` 元组里（`1.0.7` … `1.0.13`）。本文件按版本号前缀 `r` 分轴，",
        "> 所以它们出现在「任务集轴」一节 —— 元组本身没有整理，整理它要动冻结面的代码。",
        "",
        "---",
        "",
    ]
    lines += _render_axis(f"任务集轴（`set_version`，{len(task)} 条记录）", task)
    lines += ["---", ""]
    lines += _render_axis(f"参考面轴（`reference_version`，{len(ref)} 条记录）", ref)
    lines += ["---", "", "## 本仓库的里程碑", "",
              "版本轴记的是「题面 / gold 变没变」，里程碑记的是「这套东西长成了什么样」。",
              "两者不同步：一个里程碑里可能一次版本都没推。", "",
              "| 里程碑 | 是什么 | 一句话 |", "| --- | --- | --- |"]
    for mid, what, one in MILESTONES:
        lines.append(f"| **{mid}** | {what} | {one} |")
    lines += ["",
              "**「可分发」的完成定义不是「跑得通」**：它要求外部用户照手册能把这套东西用起来。",
              "今天还差三件事，逐条在 [`RELEASE_MANIFEST.json`](RELEASE_MANIFEST.json) 的 `blockers` 里，",
              "也逐条在 [`ops/reports/known_limits_v1.md`](ops/reports/known_limits_v1.md) 的收口核对一节里。",
              ""]
    return "\n".join(lines)


# ------------------------------------------------------------------ CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成 RELEASE_MANIFEST.json / CHANGELOG.md")
    ap.add_argument("--check", action="store_true", help="只比对落盘的清单与现算的，不写")
    ap.add_argument("--write-changelog", action="store_true", help="渲染 CHANGELOG.md")
    a = ap.parse_args(argv)

    try:
        from ops import report_io as RIO
        _write_json, _write_text = RIO.write_json, RIO.write_text
    except Exception:                                   # 独立使用时的退化路径
        def _write_json(p, obj, *, indent=1):
            Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=indent) + "\n",
                               encoding="utf-8")
            Path(p).chmod(0o600)
            return Path(p)

        def _write_text(p, text):
            Path(p).write_text(text, encoding="utf-8")
            Path(p).chmod(0o600)
            return Path(p)

    if a.write_changelog:
        _write_text(CHANGELOG, render_changelog())
        print(f"CHANGELOG → {CHANGELOG}")
        return 0

    cur = build()
    if a.check:
        if not MANIFEST.is_file():
            print(f"没有落盘的清单（{MANIFEST}）—— 先跑一次不带 --check 的", file=sys.stderr)
            return 2
        old = json.loads(MANIFEST.read_text(encoding="utf-8"))
        #: 先查权威文档：正文写错了版本号，sha 与 axes 段都照样对得上（红队 V2.rt finding 2）。
        vdrift = versions_doc_drift(cur["axes"])
        if vdrift:
            print("**VERSIONS.md 的正文与 axes 段对不上**（它是四条轴的权威文档）：\n  "
                  + "\n  ".join(vdrift), file=sys.stderr)
            return 1
        fatal, drift = classify_drift(cur, old)
        if fatal:
            print("**判据变了**（能不能发的答案变了，重新生成并复核）：" + ", ".join(fatal),
                  file=sys.stderr)
            return 1
        if drift:
            vol = [d for d in drift if d in VOLATILE_ITEMS]
            hand = [d for d in drift if d not in VOLATILE_ITEMS]
            print("内容已变、判据未变（重新生成即可）：\n"
                  f"  生成件（正常）：{vol}\n  手写件（看一眼改了什么）：{hand}", file=sys.stderr)
            return 3
        print(f"与落盘清单一致；releasable={cur['releasable']}")
        return 0

    _write_json(MANIFEST, cur)
    print(f"发布清单 → {MANIFEST}")
    print(f"  任务集 {cur['axes']['set_version']} / 参考面 {cur['axes']['reference_version']}")
    print(f"  发布件 {len(cur['files'])} 件，缺件 {len(cur['missing'])} 件")
    print(f"  数据许可 {cur['license']['data']['state']} / 代码许可 {cur['license']['code']['spdx']}")
    print(f"  未闭合的 blocker：{[b['id'] for b in cur['blockers'] if not b['satisfied']]}")
    print(f"  releasable = {cur['releasable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
