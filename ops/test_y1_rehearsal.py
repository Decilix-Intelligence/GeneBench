# -*- coding: utf-8 -*-
"""卡 Y1 的判据：⑯ 包体与最低配置、⑱ secrets 手册、⑭ 从零演练。

**文件名**：`ops/test_y1.py` 已经被更早一轮的另一张卡占着（那份钉的是冻结清单的体例），
所以本卡叫 `test_y1_rehearsal.py` —— 两个模块名不同，pytest 不会撞。

**这份测试要挡住的是哪一类失败**：手册首页那几个数字是**手抄**的。
包体会变（重出一次报告就变）、子集会变（加一个实例就可能多一个因子）、
最低 RAM 会变（网关上限调过一次）。手抄的数字漂了**不会让任何别的测试变红**，
而「拿到包的人照着它准备机器」正是这几个数字的全部用途。
所以逐条对着**现算的产物**核，并且核**两个方向**：
手册说的要能在产物里找到，产物里的关键数也要在手册里出现过。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
MAN = REPO / "docs" / "OPERATOR_MANUAL.md"
RM = REPO / "README.md"
CARD = REPO / "ops" / "data_cards" / "gold_subset_v1.md"
SUBSET = REPO / "ops" / "reports" / "i_rehearsal_v2" / "gold_subset.json"
INV = REPO / "ops" / "reports" / "i_rehearsal_v2" / "package_inventory.json"
REHEARSAL = REPO / "ops" / "reports" / "rehearsal_v2.md"

MANUAL_TEXT = MAN.read_text(encoding="utf-8")
README_TEXT = RM.read_text(encoding="utf-8")


def mib(n: int) -> str:
    return f"{n/1048576:.1f} MiB"


def gib(n: int) -> str:
    return f"{n/1073741824:.2f} GiB"


# ============================================================ 产物在不在

@pytest.mark.parametrize("p", [SUBSET, INV, CARD, REHEARSAL])
def test_每件产物都在(p: Path):
    assert p.exists(), f"{p.relative_to(REPO)} 不在 —— 手册 §0.0 指着它"
    assert p.stat().st_size > 200, f"{p.relative_to(REPO)} 太小，像个占位文件"


# ============================================================ ⑯ 包体与子集

def test_子集清单自洽_件数与字节与逐件sha都对得上():
    d = json.loads(SUBSET.read_text(encoding="utf-8"))
    for label, ch in d["channels"].items():
        assert ch["missing"] == [], f"{label} 有缺件：{ch['missing'][:5]}"
        assert ch["n_files"] == len(ch["files"]), f"{label} 的 n_files 与 files 长度不一致"
        assert ch["bytes"] == sum(f["bytes"] for f in ch["files"]), f"{label} 的合计字节对不上"
        for f in ch["files"]:
            assert re.fullmatch(r"[0-9a-f]{64}", f["sha256"]), f"{label}/{f['rel']} 的 sha 形状不对"
        rels = [f["rel"] for f in ch["files"]]
        assert rels == sorted(rels), f"{label} 的清单没有排序 —— 排序是「两份包能不能逐行 diff」的前提"
        assert len(set(rels)) == len(rels), f"{label} 的清单里有重复行"


def test_子集确实远小于全量_并且这件事写进了手册():
    d = json.loads(SUBSET.read_text(encoding="utf-8"))
    pub = d["channels"]["public"]
    assert pub["full_bytes"] > 5 * 1024 ** 3, (
        "全量 gold 已经不超 5 GB 了 —— 那么「只发子集」这条裁定的前提没了，回去看 ⑯")
    assert pub["bytes"] < pub["full_bytes"] / 10, "子集没有小一个数量级，值不值得单发要重新算"
    assert gib(pub["full_bytes"]) in MANUAL_TEXT, "手册 §0.0 里的全量体积与现算对不上"
    assert mib(pub["bytes"]) in MANUAL_TEXT, "手册 §0.0 里的子集体积与现算对不上"
    assert f"{pub['n_files']} " in MANUAL_TEXT or f"{pub['n_files']} 件" in CARD.read_text(encoding="utf-8")


def test_数据卡里的清单指纹是现算的():
    """指纹 = 把「哪些文件、各自什么 sha」压成一个数。手改任何一件都会变。"""
    d = json.loads(SUBSET.read_text(encoding="utf-8"))
    card = CARD.read_text(encoding="utf-8")
    for label in ("public", "private"):
        ch = d["channels"][label]
        want = hashlib.sha256(
            "".join(f"{f['rel']}\0{f['sha256']}\n" for f in ch["files"]).encode()).hexdigest()
        assert want in card, f"数据卡里的 {label} 清单指纹与现算不一致（现算 {want[:16]}…）"


def test_数据卡写明了子集不能做什么():
    """**这一条是判别力**：只写「小了多少」而不写「少了什么就做不了」，
    读者会以为子集与全量等价。`build_pool` 的选取要扫全族每一条 —— 子集推不出那 30 条。"""
    card = CARD.read_text(encoding="utf-8")
    assert "s4_eco_pool_v1" in card
    assert "不能" in card and "全量" in card, "数据卡没写清子集做不了什么"


def test_包体盘点与手册首页同源():
    inv = json.loads(INV.read_text(encoding="utf-8"))
    t = inv["totals"]
    assert gib(t["必发_加答案面_bytes"]) in MANUAL_TEXT, "手册 §0.0 的「合计」与现算对不上"
    assert gib(t["必发_加答案面_bytes"]) in README_TEXT, "README §1.5 的包体与现算对不上"
    assert t["必发合计_bytes"] < t["若发全量gold_bytes"], "盘点里「发子集」反而更大，算错了"


# ============================================================ ⑯ 最低配置：两处不许分叉

_MIN = ("16 GB", "30 GB", "50 GB", "200 GB")


@pytest.mark.parametrize("token", _MIN)
def test_最低配置在手册首页与README里都写着且一致(token: str):
    assert token in MANUAL_TEXT, f"手册 §0.0 没写 {token}"
    assert token in README_TEXT, f"README §1.5 没写 {token}"


def test_最低配置有出处而不是拍脑袋():
    """每一行都要说得出「这个数是怎么来的」—— 没有出处的最低配置是猜的。"""
    head = MANUAL_TEXT.split("### 0.1 五件挡着", 1)[0]
    assert "### 0.0 最低配置与包体" in head
    for src in ("2.3 GB", "22 GiB", "29.1.3", "2.40.3"):
        assert src in head, f"§0.0 缺一条出处：{src}"


def test_docker版本要求与前置表不分叉():
    assert "29.1.3" in MANUAL_TEXT and "2.40.3" in MANUAL_TEXT


# ============================================================ ⑱ secrets

def test_手册写全了secrets的格式位置权限():
    assert "#### 2.4.1 格式、位置、权限（⑱）" in MANUAL_TEXT
    seg = MANUAL_TEXT.split("#### 2.4.1", 1)[1].split("### 2.5", 1)[0]
    for must in ("~/.config/genebench/secrets.env", "0600", "api_key_env",
                 "GENEBENCH_MODEL_API_KEY", "compose.yml"):
        assert must in seg, f"§2.4.1 缺一件：{must}"


def test_手册给了一条真能验证容器看不见真key的命令():
    seg = MANUAL_TEXT.split("#### 2.4.1", 1)[1].split("### 2.5", 1)[0]
    assert 'grep -n "API_KEY"' in seg, "§2.4.1 没给出可粘贴的验证命令"
    placeholder = "sk-" + "genebench-placeholder"
    assert placeholder in seg, "§2.4.1 没写出占位 key 长什么样 —— 读者无从判断自己看到的是不是真值"


def test_0600这条要求与代码同源():
    """手册说「不是 0600 就拒绝」，代码里必须真的这么写 —— 否则手册在替代码许诺。"""
    src = (REPO / "ops" / "run_f02_a1.py").read_text(encoding="utf-8")
    assert "0o600" in src and "SystemExit" in src, "run_f02_a1.load_key 不再核权限了，手册要改"


# ============================================================ ⑭ 演练报告

def test_演练报告有findings表且每条都判了严重度():
    t = REHEARSAL.read_text(encoding="utf-8")
    rows = [l for l in t.splitlines() if l.startswith("| Y-")]
    assert len(rows) >= 10, f"findings 只有 {len(rows)} 条 —— 一次真演练不会这么干净"
    for r in rows:
        assert any(s in r for s in ("block", "major", "minor")), f"这一条没判严重度：{r[:60]}"


def test_演练报告逐条记了所需外网():
    t = REHEARSAL.read_text(encoding="utf-8")
    for host in ("bootstrap.pypa.io", "registry.npmjs.org", "docker.io"):
        assert host in t, f"外网清单里缺 {host}"


def test_形态一的结论是三行对照而不是一句话():
    """**判别力**：只说「通了」没有信息量。默认 bridge 那一行不通才说明是 ufw 那条规则在起作用。"""
    assert "172.17" in MANUAL_TEXT, "§1.3 少了「默认 bridge 不在放行网段里」那一行对照"
    assert "默认 bridge" in MANUAL_TEXT


def test_四条版本轴现在真的给了四条():
    seg = MANUAL_TEXT.split("### 8.1", 1)[1].split("### 8.2", 1)[0]
    for axis in ("set_version", "reference_version", "protocol_version", "GENEBENCH_CHANNEL"):
        assert axis in seg, f"§8.1 仍然查不到 {axis}"
