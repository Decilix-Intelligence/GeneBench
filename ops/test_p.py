# -*- coding: utf-8 -*-
"""卡 P（⑪–⑮ 推送两棵树 + Release 附件）的判据。

本卡的结论是「树备好了、扫描做完了、**推送与 Release 没做**」，
所以这些测试钉的是**两件事**：
  ① 两棵树确实达到了可推的状态（身份 / 单次提交 / 四类扫描干净）；
  ② 挡住 ⑭ 的那条许可事实**确实存在于仓库里**，不是本卡编出来的托词。
每一组都配了反向判别，防恒绿。
"""
import json
import os
import re
import subprocess

import pytest

GB = os.environ.get("GENEBENCH_ROOT", "/data/shared/genebench")
REPO = os.path.join(GB, "repo")
TREES = os.path.join(GB, "release", "trees")
R = os.path.join(REPO, "ops", "reports")

TREE_SPEC = {
    "genebench": "GeneBench v1.0.16 release",
    "genequant": "GeneQuant v1.0 release",
}
AUTHOR = "深情代码大师 <2994718175@qq.com>"

needs_trees = pytest.mark.skipif(
    not os.path.isdir(os.path.join(TREES, "genebench", ".git")),
    reason="发布树不在盘上（只有 f01 的数据面有）",
)


def _git(tree, *args):
    return subprocess.run(
        ["git", "-C", os.path.join(TREES, tree)] + list(args),
        capture_output=True, text=True, check=True).stdout.strip()


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ── 一、三份报告在盘上且说了该说的 ──────────────────────────────────────
@pytest.mark.parametrize("name", [
    "release_scan_final.md",
    "release_scan_claude_mentions.md",
    "push_result.md",
])
def test_三份报告都在(name):
    assert os.path.isfile(os.path.join(R, name)), f"{name} 不在 ops/reports/ 下"


def test_扫描报告逐项都有结论_四项加容器口径():
    t = _read(os.path.join(R, "release_scan_final.md"))
    for 项 in ("凭据", "tushare", "记忆探针", "scratch", "answer_plane_guard"):
        assert 项 in t, f"推前扫描报告里没有「{项}」这一项"
    # 反向判别：报告不许把「有命中」写成「零命中」
    assert "不是零命中" in t, "报告没有如实说明它不是零命中的（②那一项有命中）"


def test_字样报告两节齐全_且保留那节逐条给了理由():
    t = _read(os.path.join(R, "release_scan_claude_mentions.md"))
    assert "已删（署名）" in t and "保留（技术事实）" in t, "两节缺一"
    # 保留的每一类都要写「删了会变成什么假话」——这是裁定 ⑫ 的要求
    assert t.count("删了会变成什么假话") >= 4, "保留那节没有逐类给出「删了会变成假话」的理由"


def test_推送报告说清了树与release各自的状态():
    """卡 P 那一版钉「未执行」三个字；卡 D 已经把树推上去了，那条断言不再成立。

    留下来的**不变量**是形态而不是某一个时点的状态：这份报告必须同时说清
    **树推没推**与 **Release 建没建**，并且给出 `ls-remote` 证据与照抄的推送命令。
    """
    t = _read(os.path.join(R, "push_result.md"))
    assert "ls-remote" in t, "没有记远端状态"
    assert "push --force origin" in t, "没有给出照抄的推送命令"
    assert ("未执行" in t) or ("forced update" in t), (
        "既没说「未执行」、也没记下 force-push 的结果 —— 树到底推没推读不出来")
    assert ("Release" in t) and (("BLOCKED" in t) or ("browser_download_url" in t)), (
        "没说清 Release 与两个附件的状态（要么记成 BLOCKED，要么给出真实的下载地址）")


# ── 二、两棵树达到了可推状态（裁定 ⑫）────────────────────────────────
@needs_trees
@pytest.mark.parametrize("tree,subject", sorted(TREE_SPEC.items()))
def test_每棵树只有一次提交(tree, subject):
    assert _git(tree, "rev-list", "--count", "HEAD") == "1", f"{tree} 不是单次提交"


@needs_trees
@pytest.mark.parametrize("tree,subject", sorted(TREE_SPEC.items()))
def test_作者与提交者都是指定身份(tree, subject):
    got = _git(tree, "log", "--format=%an <%ae>|%cn <%ce>", "-1")
    assert got == f"{AUTHOR}|{AUTHOR}", f"{tree} 的身份是 {got}"


@needs_trees
@pytest.mark.parametrize("tree,subject", sorted(TREE_SPEC.items()))
def test_提交信息恰为指定串且没有署名trailer(tree, subject):
    assert _git(tree, "log", "--format=%s", "-1") == subject
    body = _git(tree, "log", "--format=%b", "-1")
    assert body == "", f"{tree} 的 message body 不为空：{body!r}"
    full = _git(tree, "log", "--format=%B", "-1")
    for 署名 in ("Co-Authored-By", "Generated with", "🤖", "anthropic", "Anthropic"):
        assert 署名 not in full, f"{tree} 的提交信息里有署名字样 {署名}"


@needs_trees
@pytest.mark.parametrize("tree,subject", sorted(TREE_SPEC.items()))
def test_树的远端要么没配_要么恰好是那个仓库(tree, subject):
    """卡 P 当时有意不加 remote（推送不是它的事），钉的是 `remote == ""`。
    收尾卡与卡 D 为了推送把 origin 配上了 —— 于是那条断言从此恒红。

    **不变量不是「没有 remote」，是「没配错地方」**：一棵带全部答案面的公开树
    指向别的仓库才是事故，指向它自己那个仓库是正常工作状态。
    """
    want = {"genebench": "git@github.com:Decilix-Intelligence/GeneBench.git",
            "genequant": "git@github.com:Decilix-Intelligence/GeneQuant.git"}[tree]
    names = _git(tree, "remote").split()
    if not names:
        return                                   # 没配：卡 P 那个状态，仍然合法
    assert names == ["origin"], f"{tree} 配了不止一个 remote：{names}"
    got = _git(tree, "remote", "get-url", "origin")
    assert got == want, f"{tree} 的 origin 指向 {got}，不是 {want}"


# ── 三、四类扫描在树上确实干净（裁定 ⑬）──────────────────────────────
def _walk(tree):
    root = os.path.join(TREES, tree)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        yield dirpath, dirnames, filenames


@needs_trees
@pytest.mark.parametrize("tree", sorted(TREE_SPEC))
def test_树里没有记忆探针钥匙(tree):
    for dirpath, dirnames, _ in _walk(tree):
        assert "memory_probe_answers" not in dirnames, f"{dirpath} 下有记忆探针目录"


@needs_trees
@pytest.mark.parametrize("tree", sorted(TREE_SPEC))
def test_树里没有scratch与run目录(tree):
    for dirpath, dirnames, _ in _walk(tree):
        for bad in ("scratch", "runs", "runs_in", "run_dirs"):
            assert bad not in dirnames, f"{dirpath} 下有 {bad}/"


@needs_trees
@pytest.mark.parametrize("tree", sorted(TREE_SPEC))
def test_树里没有凭据文件(tree):
    pats = (r"\.env$", r"^\.env", r"^secrets", r"\.pem$", r"\.key$",
            r"^id_ed25519", r"^id_rsa", r"^\.netrc$")
    for dirpath, _, filenames in _walk(tree):
        for fn in filenames:
            for p in pats:
                assert not re.search(p, fn), f"{os.path.join(dirpath, fn)} 像凭据文件"


@needs_trees
@pytest.mark.parametrize("tree", sorted(TREE_SPEC))
def test_树里没有行情数据文件(tree):
    """树里可以有报告表与因子库编译产物，但**不许有行情面板**。
    判据用体积：真正的行情单件都是几百 MB（snapshots/ 里的 daily.parquet 330 MB）。"""
    root = os.path.join(TREES, tree)
    for dirpath, _, filenames in _walk(tree):
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in (".parquet", ".duckdb", ".feather"):
                p = os.path.join(dirpath, fn)
                raise AssertionError(f"{os.path.relpath(p, root)} 是行情数据形态的文件")


# 反向判别：上面四条不是恒绿的 —— 同一套判据对一个人造的坏树必须当场红
@needs_trees
def test_四类判据有牙(tmp_path):
    (tmp_path / "reference" / "memory_probe_answers").mkdir(parents=True)
    (tmp_path / "secrets.env").write_text("PLACEHOLDER\n", encoding="utf-8")
    (tmp_path / "scratch").mkdir()
    (tmp_path / "daily.parquet").write_bytes(b"\x00")
    names = {p.name for p in tmp_path.rglob("*")}
    assert "memory_probe_answers" in names
    assert "secrets.env" in names
    assert "scratch" in names
    assert "daily.parquet" in names


# ── 四、挡住 ⑭ 的那条许可事实**确实在仓库里** ────────────────────────
def test_DATA_LICENSE里写明instruments由baostock接口重建且csi1000出包():
    """**这条换过一次判据（2026-09-12，用户裁定 ①，卡 A）。**

    原先钉的是「`instruments/` 的再分发**未确认**」—— 那时公开包的宇宙定义面是私有
    `universe_pit`（上游 tushare）派生的。裁定 ① 把定义面换成 **baostock 成分接口重建**，
    于是那条事实本身不再成立，钉着它就是钉一句**已经不真**的话。
    换成钉新的那条，判别力不减：三条断言各对应 §5 的一个可证伪事实
    （重建 / 射程 / csi1000 出包），任何一条被偷偷改回去都会红。
    """
    t = _read(os.path.join(REPO, "DATA_LICENSE"))
    assert "instruments/" in t, "DATA_LICENSE 里没提 instruments/"
    assert "由 baostock 接口重建" in t, \
        "DATA_LICENSE §5 没有写明宇宙定义面是 baostock 接口重建的"
    assert "在 §2 授权的射程内" in t, "DATA_LICENSE §5 没有写明它落在授权射程内"
    assert "`csi1000` 不入公开包" in t or "**不入公开包**" in t, \
        "DATA_LICENSE §5 没有写明 csi1000 不入公开包 —— 那是这次换面的代价，不许省略"
    assert "不在 baostock 许可的射程内" not in t, \
        "§5 里还留着旧判断的原话 —— 两个相反的结论同时在文件里，读者无从分辨"


def test_baostock的授权摘要只覆盖日线_不覆盖宇宙定义():
    """裁定 ⑨ 闭的是 data_license_text；它给的范围是「派生日线数据」。
    这条钉住「摘要里没有把指数成分也写进去」—— 有人若偷偷扩写授权范围，这里当场红。"""
    t = _read(os.path.join(REPO, "DATA_LICENSE"))
    assert "再分发派生日线数据" in t, "授权摘要不见了或被改写"
    seg = t[t.index("### 2.0"):t.index("### 2.1")]
    for 越界 in ("指数成分", "instruments", "宇宙定义"):
        assert 越界 not in seg, f"授权摘要 §2.0 里出现了 {越界} —— 授权范围被扩写了"


def test_许可正文仍是显式占位_没有被伪装成已入库():
    t = _read(os.path.join(REPO, "DATA_LICENSE"))
    assert "正式文本待替换" in t, "§2.1 的显式占位不见了"
    perm = os.path.join(REPO, "ops", "terms", "baostock", "permission")
    assert not os.path.isdir(perm) or not os.listdir(perm), \
        "ops/terms/baostock/permission/ 非空 —— 那个目录非空的唯一含义是「正文到了」"


def test_附件没上传就必须把当下的拦路原因写出来():
    """卡 P 那一版钉的三条（`instruments` 的再分发依据未确认、包不是可发布版本、
    gold 子集根本没打过包）**在卡 A 与卡 C 已经全部解决**——
    钉死它们等于要求报告去记一个已经不存在的世界。

    留下来的不变量：**只要登记表里还有空的 `download_url`（= 还没上传），
    这份报告就必须把当下的拦路原因写出来，并且记成 BLOCKED。**
    全部回填之后这条自动让路（那时该记的是下载地址，`test_d.py` 盯着）。
    """
    t = _read(os.path.join(R, "push_result.md"))
    at = json.loads(_read(os.path.join(REPO, "ops", "release", "attachments.json")))
    pending = [a["name"] for a in at["attachments"] if not a["download_url"]]
    if not pending:
        assert "browser_download_url" in t or "releases/download/" in t, (
            "登记表里两条都回填了，报告却没有记下载地址")
        return
    assert "BLOCKED" in t, (
        f"{pending} 还没上传，报告却没有把它记成 BLOCKED —— "
        f"一份说「传完了」的推送报告比没有报告坏")
    assert "附件" in t and ("403" in t or "许可" in t or "权限" in t), (
        "报告没有写出当下挡住上传的是什么")


# ── 五、票据 ────────────────────────────────────────────────────────
def test_票据在_且是表格():
    # 收口卡并入 ops/tickets.md 之后会把收件箱改名 `.merged`（施工契约）——
    # 两个名字任一在即可，并完之后只剩 `.merged`。
    p = os.path.join(REPO, "ops", "tickets_inbox", "P.md")
    if not os.path.isfile(p):
        p = p + ".merged"
    assert os.path.isfile(p), "ops/tickets_inbox/P.md（或 .merged）不在"
    t = _read(p)
    assert "| 编号 | 事项 | 状态 | 说明 |" in t, "票据不是约定的表格格式"
    assert "BLOCKED" in t, "票据里没有记 BLOCKED 项"
