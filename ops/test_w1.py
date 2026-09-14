"""W1：网关起动可靠性 + 红线 5 守门遍历改写的判别力。

两件事各自可证伪：
* 单元文件 —— **读文件，不读进程状态**（进程可能是上一版单元起的，单元文件才是下次重启的依据，
  与 `ops/test_gateway_unit.py` 同一条理由）。这里只加 W1 改的那两项，既有断言留在那个文件里。
* `guard_modes._walk_stat` —— 新遍历必须与老遍历（`_walk` + `p.stat()`）**逐条同结论**。
  它换的是系统调用次数，不是判据；一旦漂开，网关会因为一条不存在的违例拒绝启动，
  或者放过一条真的违例 —— 后者没有任何东西会报错。
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import importlib.util                                            # noqa: E402
_spec = importlib.util.spec_from_file_location("_guard_w1", _REPO / "ops" / "guard_modes.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

UNIT = Path(os.path.expanduser("~/.config/systemd/user/genebench-gateway.service"))
unit_only = pytest.mark.skipif(not UNIT.is_file(),
                               reason=f"本机没有网关单元（它在 f01）：{UNIT}")


# ────────────────────────────── 单元文件 ──────────────────────────────

def _sections(text: str) -> dict[str, list[str]]:
    """把单元文件切成 段名 → 该段的非注释行。"""
    out: dict[str, list[str]] = {}
    cur = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            cur = line[1:-1]
            out.setdefault(cur, [])
        elif line and not line.startswith("#") and cur:
            out[cur].append(line)
    return out


def _secs(v: str) -> float:
    """systemd 的时间串 → 秒（只认这里用得到的那几种写法）。"""
    v = v.strip()
    if v.endswith("min"):
        return float(v[:-3]) * 60
    if v.endswith("s"):
        return float(v[:-1])
    return float(v)


@pytest.fixture(scope="module")
def unit() -> str:
    return UNIT.read_text(encoding="utf-8")


@unit_only
def test_start_timeout_covers_the_guard_scan(unit):
    """`ExecStartPre` 是**扫全树**的守门，2026-09-10 实测 548 万条路径 / 69 s（热 cache）。

    默认的 90 s 让每次起停都成了一次掷硬币 —— 08:48–08:55 连挂 4 次
    （`start-pre operation timed out. Terminating.`），NRestarts=4 才起来。
    $GB 只会长大，所以要的是一个数量级的余量，不是「刚好够」。
    """
    svc = _sections(unit).get("Service", [])
    vals = [l.split("=", 1)[1] for l in svc if l.startswith("TimeoutStartSec=")]
    assert vals, "[Service] 里没有 TimeoutStartSec —— 默认 90 s 兜不住扫全树的守门"
    assert _secs(vals[-1]) >= 300, f"TimeoutStartSec={vals[-1]} 太小：守门实测就要 69 s，且只会更慢"


@unit_only
def test_start_limit_is_in_the_unit_section_where_it_actually_takes_effect(unit):
    """**写下的值必须就是生效的值。**

    systemd v230 之后 `StartLimitIntervalSec` / `StartLimitBurst` 只在 `[Unit]` 生效；
    写在 `[Service]` 里被解析器丢掉，而 `systemctl show` 报的是全局默认（实测 10 s）——
    单元里明明写着 120 s。没有任何东西会报错，这正是 D-06 家族的形态。
    """
    sec = _sections(unit)
    for key in ("StartLimitIntervalSec", "StartLimitBurst"):
        in_unit = [l for l in sec.get("Unit", []) if l.startswith(key + "=")]
        in_svc = [l for l in sec.get("Service", []) if l.startswith(key + "=")]
        assert in_unit, f"{key} 不在 [Unit] 段 —— 放在别处不生效"
        assert not in_svc, f"{key} 出现在 [Service] 段：那一份**会被静默丢掉**"


@unit_only
def test_the_guard_itself_is_not_weakened(unit):
    """放宽的只有超时与退避。守门本身与它的判据一个字不改。"""
    assert "ExecStartPre=" in unit and "guard_modes.py" in unit
    pre = [l for l in unit.splitlines() if l.startswith("ExecStartPre=")][0]
    assert not pre.startswith("ExecStartPre=-"), "`-` 前缀会让守门失败也照常启动 —— 那等于没有守门"
    assert "--harden" not in pre, "启动守门不许顺手 harden：那是把「拒绝启动」换成「悄悄改掉」"


# ────────────────────────── 守门遍历的判别力 ──────────────────────────

def _old_check(repo: Path) -> list[str]:
    """W1 之前那一版 `check()` 的**逐字复刻**（`_walk` + `p.stat()`），只作比对基线。"""
    bad = list(G.check_no_logrotate())
    for root in G.roots(repo):
        for p in G._walk(root):
            if p.is_symlink() and G._under_answer_plane(p):
                try:
                    tgt = os.readlink(p)
                except OSError:
                    tgt = "?"
                state = "断链" if not p.exists() else "指向 " + str(tgt)[:60]
                bad.append(f"红线 5 答案面根下出现符号链接（{state}）{p}")
                continue
            try:
                mode = p.stat().st_mode
            except OSError as e:
                bad.append(f"读不到模式 {p}（{e}）")
                continue
            if mode & G._GO_BITS:
                kind = "目录" if p.is_dir() else "文件"
                bad.append(f"红线 5 {kind}对组/其它开放 {oct(mode & 0o777)} {p}")
    return bad


@pytest.fixture
def messy(tmp_path, monkeypatch):
    """一棵**每种形态各一条**的树：正常文件、0755 目录、0644 文件、
    好链接、断链、指向目录的链接（不许下钻）。"""
    monkeypatch.setattr(G, "EXTERNAL_ROOTS", ())
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "ok.py").write_text("x", encoding="utf-8")
    (tmp_path / "loose_dir").mkdir()
    (tmp_path / "loose_dir" / "loose.txt").write_text("x", encoding="utf-8")
    (tmp_path / "away").mkdir()
    (tmp_path / "away" / "inside.txt").write_text("x", encoding="utf-8")
    os.symlink(tmp_path / "reference" / "ok.py", tmp_path / "good_link")
    os.symlink(tmp_path / "nowhere.py", tmp_path / "broken_link")
    os.symlink(tmp_path / "away", tmp_path / "dir_link")
    G.harden(tmp_path)
    os.chmod(tmp_path / "loose_dir", 0o755)
    os.chmod(tmp_path / "loose_dir" / "loose.txt", 0o644)
    return tmp_path


def test_walk_stat_matches_the_rglob_walk(messy):
    """**路径集合**逐条相同 —— 包括「不下钻符号链接目录」这一条。"""
    a = {str(p) for p in G._walk(messy)}
    b = {str(p) for p, _l, _m, _e in G._walk_stat(messy)}
    assert a == b, f"遍历集合漂了：只在老的里 {sorted(a - b)[:5]}；只在新的里 {sorted(b - a)[:5]}"
    assert not any("dir_link/" in x for x in b), "不许下钻符号链接目录（`rglob` 本来就不跟随）"


def test_check_verdict_is_unchanged(messy):
    """**结论**逐条相同：新老两版对同一棵树给同一张违例表。"""
    assert sorted(G.check(messy)) == sorted(_old_check(messy))


def test_the_loosenings_are_still_caught(messy):
    """判别力没被优化掉：0755 目录与 0644 文件都要在表里，harden 之后转绿。"""
    bad = G.check(messy)
    assert any("loose_dir" in x and "0o755" in x for x in bad), bad
    assert any("loose.txt" in x and "0o644" in x for x in bad), bad
    assert G.harden(messy) >= 2
    # 收紧之后只剩断链那一条 —— 它是**故意留在夹具里**的：`broken_link` 不在答案面根下，
    # 于是走的是「读不到模式 ≠ 查过了没有」那条判据，新老两版都必须照报不误。
    rest = G.check(messy)
    assert all("broken_link" in x and "读不到模式" in x for x in rest), rest


def test_broken_symlink_is_reported_not_skipped(messy, monkeypatch):
    """断链在答案面根下是**违例**，不是「跳过」—— 2026-09-05 就是它们让网关连挂 20 次。"""
    monkeypatch.setattr(G, "ANSWER_PLANE_ROOTS", (str(messy),))
    bad = G.check(messy)
    assert any("broken_link" in x and "断链" in x for x in bad), bad
    assert any("good_link" in x and "指向" in x for x in bad), bad


def test_stat_still_follows_symlinks(messy):
    """链接自己的位是 0777；判据看的必须是**目标**的位（与原来的 `p.stat()` 同语义）。
    否则每一条正常链接都会变成违例 —— 恒红的门会被绕过。"""
    got = {str(p): (islink, mode) for p, islink, mode, _e in G._walk_stat(messy)}
    islink, mode = got[str(messy / "good_link")]
    assert islink and mode is not None
    assert not (mode & G._GO_BITS), f"跟随链接后应当是收紧过的目标 {oct(mode)}"


# ─────────────────────────── N-388：默认预算档 ───────────────────────────

def test_default_budget_tier_is_six_million_tokens():
    """N-388 已裁定（2026-09-10）：默认档 `max_tokens` 600,000 → 6,000,000。

    600k 的后果是实测过的：`ops/reports/v1demo/` 那 8 个 run **全部**撞 token 闸，
    调用数只用到 18–22 / 100 —— 表上的 SR / pass@1 读的是「预算够不够」，不是能力。
    6M 与 `BUDGET_TIERS` 自己的换算规则同源（档位调用数 × 60k/次，100 × 60k）。
    """
    from runner import registry as REG
    assert REG.RUN_BUDGET["max_tokens"] == 6_000_000
    assert REG.RUN_BUDGET_DEFAULT["max_tokens"] == 6_000_000
    assert REG.RUN_BUDGET["max_calls"] == 100


def test_the_stage_tiers_survive_the_higher_default():
    """抬默认档会把「档位只能往上抬」那条判据踩红 —— S4 9M / S7 18M 仍然合法，核一遍。"""
    from runner import registry as REG
    REG.assert_registry_sane()
    for st, tier in REG.BUDGET_TIERS.items():
        for k, v in tier.items():
            assert v >= REG.RUN_BUDGET_DEFAULT[k], f"{st}.{k}={v} 掉到默认档以下"
    assert REG.budget_for(None)["max_tokens"] == 6_000_000
    assert REG.budget_for("S4")["max_tokens"] == 9_000_000
    assert REG.budget_for("S7") == {"max_calls": 300, "max_tokens": 18_000_000}
