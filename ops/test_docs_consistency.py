"""卡 C2 的门：**同一事实在 README 与操作手册两处的状态不得相反**（用户明令，2026-09-13）。

为什么要这道门
--------------
外部验收（2026-09-13，macOS）逐条点名的一类问题是「两份文档互相打架」：
README §2.3 还写着单机形态「未端到端验证」，手册 §1.1/§1.3 已经写着演练跑通了；
手册 §1.4 (a) 还写着附件路线「今天走不通」，而附件当天就已经能匿名下载。
外部读者没有办法判断哪一句是现状 —— 两句都是我们自己写的。

这道门**不是通用扫描器**。它只钉住一张手写的表：几条**真的会打架**的事实，
每条写清「现在的状态是什么」，然后要求 README 与手册**都把它说出来**、
**都不许说反话**。改口只改一处的那次提交会在这里红掉。

判据形状
--------
每条事实 = ``Fact(id, 说的是什么, {文件: (必须出现的 pattern..., 不许出现的 pattern...)})``。

* **必须出现**（``require``）—— 这一处得把现状说出来。少一个就是「这边没改口」。
* **不许出现**（``forbid``）—— 这一处不许还留着相反的说法。命中一个就是「这边说了反话」。

两条匹配前的规范化，都是有意的：

1. **`「…」` 里的内容先去掉。** 本项目的文档约定：`「…」` 引的是**旧版原文**，
   留着是给读过旧版的人看见它去哪了，**不是现状陈述**。
   例：手册 §1.4 (a) 现在写「这条路今天通了」，同一段里用 `「今天走不通…」` 引了旧话 ——
   那不该把这道门判红。
2. **空白压成一个空格。** 判据跨行写才读得懂，正则不该为了换行位置而改。

跑法（**不依赖 `/data`、不依赖数据湖、不依赖发布方的解释器与网关地址**，
外部干净 clone 上原样能跑）::

    python3 -m pytest ops/test_docs_consistency.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
README = "README.md"
MANUAL = "docs/OPERATOR_MANUAL.md"

#: `「…」` = 引旧版原文，不是现状陈述 —— 匹配前去掉。
_QUOTE_OLD = re.compile(r"「[^」]*」")
_WS = re.compile(r"\s+")


def _normalized(rel: str) -> str:
    text = (REPO_ROOT / rel).read_text(encoding="utf-8")
    return _WS.sub(" ", _QUOTE_OLD.sub(" ", text))


# ── 公开/私有通道的端口：**从 `genebench_config.py` 现读**，不在本文件里再抄一遍 ──────
# （卡 G10，用户裁定 ⑤，2026-09-14）用 AST 读而不是 `import`：这道门的一条自我约束是
# 「外部干净 clone 上原样能跑，不依赖发布方的解释器与网关地址」，而 AST 读一个模块级
# 整数常量既不执行任何代码，也不需要那台机器上真有网关。**抄一份进测试**是另一条路，
# 它的代价本项目付过：两份清单 = 两个真相，而漂移的那一天没有人会红。
def _int_const(name: str) -> int:
    import ast
    src = (REPO_ROOT / "genebench_config.py").read_text(encoding="utf-8")
    for node in ast.parse(src).body:
        tgt = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            tgt = node.target.id
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and \
                isinstance(node.targets[0], ast.Name):
            tgt = node.targets[0].id
        if tgt == name and isinstance(node.value, ast.Constant) and \
                isinstance(node.value.value, int):
            return int(node.value.value)
    raise AssertionError(f"genebench_config.py 里读不到模块级整数常量 {name} —— "
                         f"它改名或改写法了，这道门的端口判据会跟着空掉，先修这里")


#: 公开通道端口（外部用户按 README §2.4 ⓪ 走的就是这条）。
PORT_PUBLIC: int = _int_const("GATEWAY_PUBLIC_PORT")
#: 私有通道端口（发布方内部那条）。**两个刻意不同**，`ufw` 那条规则写错哪一个都很难认。
PORT_PRIVATE: int = _int_const("GATEWAY_PORT")


class Fact:
    """一条事实，以及它在每份文档里必须/不许出现的说法。"""

    def __init__(self, ident: str, says: str, per_file: dict[str, tuple[list[str], list[str]]]):
        self.id = ident
        self.says = says
        self.per_file = per_file


FACTS: list[Fact] = [
    Fact(
        "attachments_route_works",
        "数据面 (a)「拿现成的冻结包」这条路是通的：两个附件已挂在 Release v1.0.16，匿名可下，"
        "sha256 已被外部验收实测核过",
        {
            README: (
                [r"两个附件已经挂上去了", r"匿名就能下"],
                [r"拿冻结包[^。]{0,40}走不通", r"附件[^。]{0,20}还没(上传|挂上去)"],
            ),
            MANUAL: (
                [r"这条路今天通了", r"匿名就能下"],
                [r"拿冻结包（形态 A）\*\* —— 今天走不通", r"附件[^。]{0,20}还没(上传|挂上去)"],
            ),
        },
    ),
    Fact(
        "form1_end_to_end",
        "形态 ① 单机：Linux 上已经端到端跑通（2026-09-11 演练），macOS/arm64 上还没有"
        "（2026-09-13 外部验收卡在建 harness 镜像）",
        {
            README: (
                [r"Linux 上这一形态已经端到端跑通", r"macOS（arm64）上还没跑通"],
                [r"这一形态未端到端验证", r"未端到端验证的只有一处"],
            ),
            MANUAL: (
                [r"Linux 上已经整条跑过", r"macOS（arm64）外部验收\*\*没走完\*\*"],
                [r"这一形态未端到端验证", r"未端到端验证的只有一处"],
            ),
        },
    ),
    Fact(
        "publication_table_is_main",
        "发布表是 `--table main`（19 指标列 + 5 身份列 = CSV 24 列）；`--table a` 是诊断表",
        {
            README: (
                [r"--table main", r"19 个指标列 \+ 5 个身份列 = CSV 24 列", r"诊断表"],
                [r"mk_tables\.py --table a --format md --filter batch=v1demo"],
            ),
            MANUAL: (
                [r"--table main", r"19 个指标列 \+ 5 个身份列 = CSV 24 列", r"诊断表"],
                [],
            ),
        },
    ),
    Fact(
        "python_min_312",
        "外部路径最低 Python 3.12（macOS 自带 3.9.6 不够）",
        {
            README: ([r"\*\*3\.12\+\*\*", r"3\.9\.6，不够"], [r"数据面 \*\*3\.10\+\*\*"]),
            MANUAL: ([r"\*\*3\.12\+\*\*", r"3\.9\.6，不够"], [r"数据面 \*\*3\.10\+\*\*"]),
        },
    ),
    Fact(
        "docker_mem_16g",
        "Docker 引擎可用内存最低 16 GB（Docker Desktop 默认只给 8 GB，不够）",
        {
            README: ([r"引擎可用内存 ≥ 16 GB", r"Docker Desktop 默认只给 8 GB"], []),
            MANUAL: ([r"引擎可用内存 ≥ 16 GB", r"Docker Desktop 默认只给 8 GB"], []),
        },
    ),
    Fact(
        "disk_15g_shortest_path",
        "外部用户走 (a) + 最短路径的磁盘下限 ≈ 15 GB（50 GB / 200 GB 是另外两档）",
        {
            README: ([r"最短路径 \*\*≈ 15 GB\*\*"], [r"\*\*50 GB\*\* 起步"]),
            MANUAL: ([r"最短路径 \*\*≈ 15 GB\*\*"], [r"\*\*50 GB\*\* 起步"]),
        },
    ),
    Fact(
        "test_env_is_internal",
        "`ops/test_env.py` 是发布方内部自检，外部用户不要跑；外部跑 `ops/selfcheck_public.py`",
        {
            README: (
                [r"ops/selfcheck_public\.py", r"`ops/test_env\.py`[^。]{0,40}不是给你跑的"],
                [r"pytest ops/test_env\.py"],
            ),
            MANUAL: (
                [r"ops/selfcheck_public\.py", r"`ops/test_env\.py`\*\* —— 断言"],
                [],
            ),
        },
    ),
    Fact(
        "attachments_registry_is_source_of_truth",
        "附件有几件、各自的 sha256 与下载地址，以 `ops/release/attachments.json` 为准 —— "
        "清单里可能有「登记了但还没上传」的条目（`download_url` 是空串）",
        {
            README: ([r"ops/release/attachments\.json", r"download_url` 是空串"], []),
            MANUAL: ([r"ops/release/attachments\.json", r"download_url` 是空串"], []),
        },
    ),
    Fact(
        # 2026-09-13：本条由 `manifest_check_nonzero_is_not_damage` 改写而来（用户裁定 ②）。
        # 旧判据要求两处都写「非零 ≠ 发布件损坏」—— 那是在教人忽略一个真问题。
        # 根因（`has_remote` 与 `m6_public` 两处机器依赖）修掉之后，那句话本身成了假话，
        # 所以判据翻面：现在两处都要说「清单不取决于跑它的机器」，且都不许写回那句旧话。
        "manifest_check_is_machine_independent",
        "`ops/mk_release_manifest.py --check` 生成的清单**不取决于跑它的机器**，"
        "外部干净 clone 上也退 0；文档里不许再写「非零是环境差异，忽略它」",
        {
            README: ([r"刻意不取决于跑它的机器"], [r"非零 ≠ 发布件损坏"]),
            MANUAL: ([r"刻意不取决于跑它的机器"], [r"非零 ≠ 发布件损坏"]),
        },
    ),
    Fact(
        # 用户 2026-09-13 裁定：预算档要在 README 与手册两处都写清，且「撞闸不是失败」
        # 这句话必须同时在两处 —— 外部用户最常把一批 `budget_exhausted` 读成自己配错了。
        "budget_tiers_and_exhausted_status",
        "默认预算档 100 次调用 / 6,000,000 tokens，S4 150 次 / 9M、S7 300 次 / 18M"
        "（`runner/registry.py::budget_for`）；撞闸记 `budget_exhausted`，"
        "那是与 ok / violation / timeout 并列的收口状态，不是失败，主表上渲染成 `—`",
        {
            README: (
                [r"100 次调用 / 6,000,000 tokens",
                 r"\*\*S4 150 次 / 9M\*\*、\*\*S7 300 次 / 18M\*\*",
                 r"撞闸记 `budget_exhausted`，那是一个收口状态，不是失败",
                 r"主表里那一格渲染成 `—`",
                 r"\*\*这六个 run 的分布不调档\*\*"],
                [r"撞(了)?闸[^。]{0,12}(算|记成)失败"],
            ),
            MANUAL: (
                [r"100 次调用 / 6,000,000 tokens",
                 r"\*\*S4 150 次 / 9M\*\*、\*\*S7 300 次 / 18M\*\*",
                 r"撞闸记 `budget_exhausted`，那是一个收口状态，不是失败",
                 r"主表里那一格渲染成 `—`",
                 r"\*\*这六个 run 的分布不调档\*\*"],
                [r"撞(了)?闸[^。]{0,12}(算|记成)失败"],
            ),
        },
    ),
    # ===================================================================
    # 卡 G10（用户裁定 ⑤，2026-09-14）：**文档门要对单机路径有断言。**
    #
    # 实测事实：`placement` / `topology` / `single` / `push_exec` 在这道门与
    # `ops/test_readme.py` 里**命中 0 次** —— 上一轮三道文档门全绿，却一条都没拦住
    # 交付终核在干净 Mac 上量到的那 3 条 block + 6 条 major。用户点破的就是这一句：
    # **门全绿却一条都没拦住，靠的是派卡时人对交接。**
    #
    # 下面五条的 `require` 里那些字符串，在卡 H10（2026-09-14）之前**两份文档里
    # 一次都没出现过** —— 所以「改回旧写法」对它们而言就是「这一句根本不在」，
    # 反证（`test_反证_…`）正是这么构造的，不是编一段假的旧文。
    # ===================================================================
    Fact(
        "single_machine_exec_and_bundle_placement",
        "单机形态铺 exec 树与 bundle 的入口是 `runner/placement.py`（`--place-exec`），"
        "不是推送脚本 —— 两份文档都要把这条路写出来，否则单机用户被反向指到另一台机器上",
        {
            README: (
                [r"runner/placement\.py", r"--place-exec", r"bundle 与 exec 树本来就在本机"],
                [],
            ),
            MANUAL: (
                [r"runner/placement\.py", r"--topology single --place-exec", r"在六段里自己落位"],
                [],
            ),
        },
    ),
    Fact(
        "topology_is_explicit_and_defaults_to_dual",
        "形态判据**显式**：`--topology single|dual` > `GENEBENCH_TOPOLOGY` > 默认 `dual`；"
        "没有 hostname / 路径存在性嗅探",
        {
            README: ([r"--topology single\|dual", r"GENEBENCH_TOPOLOGY", r"默认 `dual`"],
                     [r"默认 `single`"]),
            MANUAL: ([r"--topology single\|dual", r"GENEBENCH_TOPOLOGY", r"默认 `dual`"],
                     [r"默认 `single`"]),
        },
    ),
    Fact(
        "single_machine_real_run_carries_the_topology_flag",
        "真跑那条命令在单机分支上必须带 `--topology single` —— **不给就是双机**，"
        "单机用户会得到一条 `ssh` 到发布方执行面的命令，而那台机器不是他的",
        {
            README: ([r"--channel public --topology single"], []),
            MANUAL: ([r"ops/run_joblist\.py --topology single"], []),
        },
    ),
    Fact(
        "provider_on_the_exec_plane_is_a_documented_step",
        "执行面上还要一份 provider（目录名 `qlib_provider_<公开 provider 根 sha256 前 8 位>`，"
        "**那 8 位现算**），自查用 `--check-plane`；这一步此前两份文档里一个字都没有 —— "
        "它是「一个 job 就算有 docker、有 key 也走不到表」的直接原因",
        {
            README: ([r"provider_pin_expect\(", r"qlib_provider_\$P8", r"--check-plane"], []),
            MANUAL: ([r"provider_pin_expect\(", r"qlib_provider_\$P8", r"--check-plane"], []),
        },
    ),
    Fact(
        "ufw_rule_uses_the_public_channel_port",
        f"§2.3 ① 那条 `ufw allow` 的端口与**公开通道实际端口**同源"
        f"（现读 `genebench_config.GATEWAY_PUBLIC_PORT` = {PORT_PUBLIC}，"
        f"私有通道是 {PORT_PRIVATE}）。写错端口的失败形态极难认："
        f"容器起得来、模型照样调得动，只有数据网关打不通，run 一路空转到墙钟闸",
        {
            README: ([rf"port {PORT_PUBLIC} proto tcp", r"GATEWAY_PUBLIC_PORT"],
                     [rf"port {PORT_PRIVATE} proto tcp"]),
            MANUAL: ([rf"port {PORT_PUBLIC} proto tcp", r"GATEWAY_PUBLIC_PORT"], []),
        },
    ),
]


@pytest.fixture(scope="module")
def docs() -> dict[str, str]:
    return {rel: _normalized(rel) for rel in (README, MANUAL)}


def test_两份文档都在():
    for rel in (README, MANUAL):
        assert (REPO_ROOT / rel).is_file(), f"{rel} 不在 —— 这道门比的就是这两份"


@pytest.mark.parametrize("fact", FACTS, ids=[f.id for f in FACTS])
def test_同一事实两处状态不得相反(fact: Fact, docs: dict[str, str]):
    问题: list[str] = []
    for rel, (require, forbid) in fact.per_file.items():
        body = docs[rel]
        for pat in require:
            if not re.search(pat, body):
                问题.append(f"{rel}：没把现状说出来 —— 缺 /{pat}/")
        for pat in forbid:
            hit = re.search(pat, body)
            if hit:
                问题.append(f"{rel}：还留着相反的说法 —— 命中 /{pat}/ → {hit.group(0)[:80]!r}")
    assert not 问题, (
        f"\n事实 [{fact.id}]：{fact.says}\n"
        + "\n".join("  - " + x for x in 问题)
        + "\n\n同一事实在 README 与操作手册两处的状态不得相反 —— "
          "改口要两处一起改。（`「…」` 里引的旧版原文不算现状，这道门已经把它去掉了。）"
    )


def test_旧版原文的引号约定还在():
    """`「…」` 的去除是这道门的判据之一：真的有一处靠它才不会误判，钉住它。"""
    raw = (REPO_ROOT / MANUAL).read_text(encoding="utf-8")
    assert "「今天走不通" in raw, (
        "手册 §1.4 (a) 里那句用 `「…」` 引起来的旧版原文不见了。"
        "它是本门「引旧话不算现状」这条规范化规则的现场样本 —— "
        "要么把它留着，要么把这条规则和对应的 forbid 判据一起重新想过。"
    )
    assert "「今天走不通" not in _normalized(MANUAL), "规范化没有把 `「…」` 去掉"


# ===========================================================================
# 卡 G10：**判别力自证** —— 把这五条改回旧写法（= 那一句根本不在），这道门必须当场红
# ===========================================================================

#: 本卡加的那五条。反证只打这五条，不去动前面那些别的卡各自的判据。
G10_FACT_IDS: tuple[str, ...] = (
    "single_machine_exec_and_bundle_placement",
    "topology_is_explicit_and_defaults_to_dual",
    "single_machine_real_run_carries_the_topology_flag",
    "provider_on_the_exec_plane_is_a_documented_step",
    "ufw_rule_uses_the_public_channel_port",
)
G10_FACTS: list[Fact] = [f for f in FACTS if f.id in G10_FACT_IDS]


def test_本卡那五条都真的进了这张表():
    got = {f.id for f in FACTS}
    missing = [i for i in G10_FACT_IDS if i not in got]
    assert not missing, f"这几条没进 FACTS，反证就落在空处：{missing}"
    assert len(G10_FACTS) == len(G10_FACT_IDS)


def test_端口是现读出来的_不是抄进测试的():
    """端口读取器**没瞎**的下界断言：读不到时上面那条 Fact 会变成一条恒绿的空判据。"""
    assert isinstance(PORT_PUBLIC, int) and isinstance(PORT_PRIVATE, int)
    assert PORT_PUBLIC != PORT_PRIVATE, (
        "公开与私有通道端口读成同一个值了 —— `genebench_config.py` 里那两条注释写明"
        "它们**刻意不同**：「忘了设端口」的失败形态必须是起在公开口，不能是抢私有口")
    assert 1024 < PORT_PUBLIC < 65536 and 1024 < PORT_PRIVATE < 65536


@pytest.mark.parametrize("fact", G10_FACTS, ids=[f.id for f in G10_FACTS])
def test_反证_把单机那几句从文档里拿掉_这道门必须当场红(fact: Fact, docs: dict[str, str]):
    """**改回旧写法**：卡 H10 之前，这五条 `require` 的字符串在两份文档里命中 0 次。

    所以「旧写法」对它们而言就是**那一句根本不在** —— 这里逐条把它抹掉，
    再把同一份判据（**就是上面那个 test 函数本身**，不另写一份）喂给它，必须抛。
    不另写一份是有意的：两份判据 = 两个真相，反证很容易变成「反证自己那一份」。
    """
    broken = dict(docs)
    changed = False
    for rel, (require, _forbid) in fact.per_file.items():
        t = broken[rel]
        for pat in require:
            t2 = re.sub(pat, "（旧写法：这一句当时根本不在）", t)
            changed = changed or (t2 != t)
            t = t2
        broken[rel] = t
    assert changed, (
        f"[{fact.id}] 抹了一圈，副本逐字节没变 —— 这条反证是空的（`require` 的正则漂了？）")
    with pytest.raises(AssertionError):
        test_同一事实两处状态不得相反(fact, broken)


def test_反证_把ufw那条端口写回私有口_这道门必须当场红(docs: dict[str, str]):
    """上面那条反证只证了 `require` 那一半。`forbid` 那一半单独证一次：

    **不动**公开口那一句，只把私有口那条规则**补进 README** —— 只有 `forbid` 会响。
    这正是本轮改口之前 README 的写法（当时只有一条规则，端口是私有那个）。
    """
    fact = next(f for f in FACTS if f.id == "ufw_rule_uses_the_public_channel_port")
    broken = dict(docs)
    broken[README] = (broken[README] +
                      f" sudo ufw allow from <容器网段> to any port {PORT_PRIVATE} proto tcp ")
    with pytest.raises(AssertionError):
        test_同一事实两处状态不得相反(fact, broken)
