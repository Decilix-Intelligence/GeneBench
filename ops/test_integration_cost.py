# -*- coding: utf-8 -*-
"""卡 2.5 验收：接入成本遥测（`integrations/cost/`）。

这份遥测的价值全在**它记的数是真的**上。所以判据分三类：

1. **算得对** —— active minutes 去掉暂停段；LOC 与 `git diff --numstat` 逐数相同。
2. **算得出来的东西不许被绕过** —— 状态机拒绝不合法的转移；不带时区的时刻直接红；
   坏账本当场炸而不是跳过（跳过的表现是数偏小，和「这个接入很省事」长得一样）。
3. **表不许和账本漂开** —— 追加事件会在同一把锁里重算 `COST.md`；
   手改过的 `COST.md` 被 `report` 改回去；仓库里那两份**当前就是同步的**。

夹具是一个**真 git 仓库**（`tmp_path`），不是 mock：LOC 那一条要测的正是
「我们喊的 git 命令和 git 自己算的一样」，对着 mock 测它等于什么也没测。
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from integrations import cost as C  # noqa: E402

T0 = datetime(2026, 9, 6, 8, 0, 0, tzinfo=timezone.utc)


def at(minutes: int) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat()


def _git(repo, *args) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True)
    return p.stdout


@pytest.fixture()
def repo(tmp_path) -> Path:
    """一个最小的真仓库：有 `integrations/`，有一次初始提交（于是有 HEAD）。"""
    r = tmp_path / "repo"
    (r / "integrations" / "demo").mkdir(parents=True)
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    (r / "README.md").write_text("# 夹具\n", encoding="utf-8")
    _git(r, "add", "README.md")
    _git(r, "commit", "-q", "-m", "init")
    return r


def run(repo, *argv) -> int:
    return C.main(["--repo", str(repo), *argv])


def events(repo):
    return C.read_events(repo)


# ===========================================================================
# 1. active minutes
# ===========================================================================
def test_active_minutes_excludes_the_pause_segment(repo):
    """begin→pause→resume→end：挂钟 60 分钟，暂停 30 分钟，净工时必须是 **30**。

    这一条同时是判别力测试：如果实现忘了减暂停段，它会给出 60 —— 两个数差得开，
    不会出现「碰巧也对」。
    """
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    run(repo, "pause", "--system", "demo", "--at", at(20), "--note", "等网关锁")
    run(repo, "resume", "--system", "demo", "--at", at(50))
    run(repo, "end", "--system", "demo", "--outcome", "passed_real_task", "--at", at(60))

    evs = events(repo)
    assert [e["event"] for e in evs] == ["begin", "pause", "resume", "end"]
    end = evs[-1]
    assert end["active_minutes"] == 30.0, evs
    #: 挂钟是 60 —— 把它写进断言，免得哪天实现「碰巧」把两个数弄成一样。
    assert (C.parse_ts(end["ts"]) - C.parse_ts(evs[0]["ts"])).total_seconds() / 60 == 60.0
    assert end["outcome"] == "passed_real_task"
    assert end["who"] == "agent", "end 要把 begin 记的 who 带过来"


def test_two_pause_segments_both_come_off(repo):
    run(repo, "begin", "--system", "demo", "--who", "human", "--at", at(0))
    for a, b in ((10, 15), (40, 70)):
        run(repo, "pause", "--system", "demo", "--at", at(a))
        run(repo, "resume", "--system", "demo", "--at", at(b))
    run(repo, "end", "--system", "demo", "--outcome", "blocked", "--at", at(100))
    assert events(repo)[-1]["active_minutes"] == 100.0 - 5 - 30


def test_ending_while_paused_counts_the_pause_up_to_the_end(repo):
    """暂停着收尾 —— 那段暂停算到 `end` 为止。**照实记**，不为了好看算成在干活。"""
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    run(repo, "pause", "--system", "demo", "--at", at(10))
    run(repo, "end", "--system", "demo", "--outcome", "abandoned", "--at", at(30))
    assert events(repo)[-1]["active_minutes"] == 10.0


def test_multiple_sessions_add_up(repo):
    for base, out in ((0, "blocked"), (1000, "passed_real_task")):
        run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(base))
        run(repo, "end", "--system", "demo", "--outcome", out, "--at", at(base + 25))
    row = C.summarize(events(repo))["rows"][0]
    assert row["sessions"] == 2
    assert row["active_minutes"] == 50.0
    assert row["outcome"] == "passed_real_task", "结局取最后一段"


# ===========================================================================
# 2. LOC
# ===========================================================================
def _numstat_by_git(repo, base, system) -> tuple[int, int]:
    out = _git(repo, "diff", "--numstat", f"{base}..HEAD", "--", f"integrations/{system}")
    a = d = 0
    for line in out.splitlines():
        c = line.split("\t")
        if len(c) >= 3 and c[0] != "-":
            a += int(c[0])
            d += int(c[1])
    return a, d


def test_loc_matches_what_git_itself_says(repo):
    """增删行必须与 `git diff --numstat` 逐数相同 —— 我们只是在转述 git，不是在自己数。"""
    d = repo / "integrations" / "demo"
    #: 先落一份**已在基线里**的文件 —— 否则 `base..HEAD` 只会有加行，
    #: 「删行」那一半判据就恒为 0（恒绿）。
    (d / "README.md").write_text("一\n二\n三\n四\n五\n", encoding="utf-8")
    _git(repo, "add", "integrations/demo")
    _git(repo, "commit", "-q", "-m", "demo 起手")

    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    base = C.git_head(repo)

    (d / "launch.json").write_text('{\n  "harness": "Demo"\n}\n', encoding="utf-8")
    (d / "README.md").write_text("一\n二\n四\n五\n", encoding="utf-8")      # 删掉「三」
    _git(repo, "add", "integrations/demo")
    _git(repo, "commit", "-q", "-m", "接入 demo")

    want_a, want_d = _numstat_by_git(repo, base, "demo")
    got = C.loc_for(repo, "demo", base)
    assert (got["loc_added"], got["loc_deleted"]) == (want_a, want_d)
    assert (want_a, want_d) == (3, 1), f"夹具的形状变了：{want_a}/{want_d}"
    #: 现存非空行：launch.json 3 行 + README 4 行。
    assert got["loc_total"] == 3 + 4


def test_loc_total_sees_uncommitted_work(repo):
    """未提交的工作只在「现存非空行」里看得见 —— 这正是要有第三个数的理由。"""
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    base = C.git_head(repo)
    (repo / "integrations" / "demo" / "Dockerfile").write_text(
        "FROM gb-base:bookworm-r1\n\nRUN true\n", encoding="utf-8")
    got = C.loc_for(repo, "demo", base)
    assert (got["loc_added"], got["loc_deleted"]) == (0, 0), "还没提交，diff 必须是 0"
    assert got["loc_total"] == 2


def test_loc_skips_generated_and_binary(repo):
    d = repo / "integrations" / "demo"
    (d / "__pycache__").mkdir()
    (d / "__pycache__" / "x.cpython-310.pyc").write_bytes(b"\x00\x01\x02\n\n")
    (d / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
    (d / "k.txt").write_text("a\nb\n", encoding="utf-8")
    assert C.count_nonblank(d) == 2


def test_loc_is_a_query_not_an_event(repo, capsys):
    """`loc` 看一眼不该记一笔 —— 否则「看了几眼」会混进「干了多少活」。"""
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    before = len(events(repo))
    run(repo, "loc", "--system", "demo")
    capsys.readouterr()
    assert len(events(repo)) == before


# ===========================================================================
# 3. 返工
# ===========================================================================
def test_rework_is_counted_and_carries_a_reason(repo):
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    run(repo, "rework", "--system", "demo", "--why", "容器 HOME 不可写，命令重写", "--at", at(5))
    run(repo, "rework", "--system", "demo", "--why", "base_url 写死了主机名", "--at", at(9))
    run(repo, "end", "--system", "demo", "--outcome", "passed_real_task", "--at", at(20))
    evs = events(repo)
    assert [e["rework_count"] for e in evs if e["event"] == "rework"] == [1, 2]
    assert evs[1]["note"] == "容器 HOME 不可写，命令重写"
    assert evs[-1]["rework_count"] == 2
    assert C.summarize(evs)["rows"][0]["rework_count"] == 2


def test_end_rework_flag_adds_one(repo):
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    run(repo, "end", "--system", "demo", "--outcome", "blocked", "--rework", "--at", at(3))
    assert events(repo)[-1]["rework_count"] == 1


# ===========================================================================
# 4. 状态机与坏输入：算不出来的时候必须**炸**，不许猜
# ===========================================================================
@pytest.mark.parametrize("pre, bad", [
    ([], ["pause"]),
    ([], ["resume"]),
    ([], ["end", "--outcome", "blocked"]),
    ([], ["rework", "--why", "x"]),
    (["begin"], ["begin", "--who", "agent"]),
    (["begin"], ["resume"]),
    (["begin", "pause"], ["pause"]),
])
def test_illegal_transitions_are_refused(repo, pre, bad):
    for i, ev in enumerate(pre):
        extra = ["--who", "agent"] if ev == "begin" else []
        run(repo, ev, "--system", "demo", "--at", at(i), *extra)
    n = len(events(repo))
    with pytest.raises(C.CostError):
        run(repo, bad[0], "--system", "demo", "--at", at(90), *bad[1:])
    assert len(events(repo)) == n, "被拒的转移不许留下事件"


def test_a_typo_in_system_is_warned_about_not_swallowed(repo, capsys):
    """写错 id 会照样记账，而 LOC 永远是 0 —— **0 和「一行没改」在表上长得一样**。
    所以要提醒；但不报错，因为「先 begin 再 mkdir」是正当顺序。"""
    run(repo, "begin", "--system", "dmeo", "--who", "agent", "--at", at(0))
    assert "还不在" in capsys.readouterr().err

    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    assert "还不在" not in capsys.readouterr().err, "目录在的时候不该唠叨"


def test_a_zero_loc_end_says_so(repo, capsys):
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    capsys.readouterr()
    run(repo, "end", "--system", "demo", "--outcome", "passed_real_task", "--at", at(5))
    assert "三个数全是 0" in capsys.readouterr().err


def test_naive_timestamp_is_refused(repo):
    """不带时区的时刻会静默偏 8 小时，而偏 8 小时的工时看起来只是「那天干得久」。"""
    with pytest.raises(C.CostError, match="没有时区"):
        run(repo, "begin", "--system", "demo", "--who", "agent",
            "--at", "2026-09-06T08:00:00")


def test_a_broken_ledger_line_blows_up_with_its_line_number(repo):
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    p = C.jsonl_path(repo)
    p.write_text(p.read_text(encoding="utf-8") + "{ 不是 JSON\n", encoding="utf-8")
    with pytest.raises(C.CostError, match=r":2 "):
        events(repo)


def test_a_ledger_line_missing_a_key_blows_up(repo):
    p = C.jsonl_path(repo)
    p.write_text(json.dumps({"ts": at(0), "system": "demo", "event": "begin"}) + "\n",
                 encoding="utf-8")
    with pytest.raises(C.CostError, match="键集"):
        events(repo)


def test_every_written_record_has_exactly_the_twelve_fields(repo):
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    run(repo, "pause", "--system", "demo", "--at", at(1))
    run(repo, "resume", "--system", "demo", "--at", at(2))
    run(repo, "rework", "--system", "demo", "--why", "w", "--at", at(3))
    run(repo, "end", "--system", "demo", "--outcome", "blocked", "--at", at(4))
    for raw in C.jsonl_path(repo).read_text(encoding="utf-8").splitlines():
        assert list(json.loads(raw)) == list(C.FIELDS), raw


def test_the_axes_are_the_ones_the_card_named():
    assert C.OUTCOMES == ("passed_real_task", "blocked", "abandoned")
    assert C.WHO == ("agent", "human")
    assert C.EVENTS == ("begin", "pause", "resume", "rework", "end")


# ===========================================================================
# 5. 报表：从 JSONL 生成，且不许和账本漂开
# ===========================================================================
def test_report_is_generated_from_the_jsonl(repo):
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    run(repo, "pause", "--system", "demo", "--at", at(10))
    run(repo, "resume", "--system", "demo", "--at", at(40))
    run(repo, "rework", "--system", "demo", "--why", "重写命令", "--at", at(45))
    run(repo, "end", "--system", "demo", "--outcome", "passed_real_task", "--at", at(60))

    path, summary = C.write_report(repo)
    md = path.read_text(encoding="utf-8")
    assert path == C.md_path(repo)
    assert summary["rows"][0]["active_minutes"] == 30.0
    assert "| `demo` |" in md
    assert "30.0" in md and "passed_real_task" in md and "生成" in md
    #: 表是**算出来的**，不是账本的复印件：挂钟 60 分钟一个字都不该出现在净工时列。
    row = [ln for ln in md.splitlines() if ln.startswith("| `demo`")][0]
    assert "| 30.0 |" in row and "| 60.0 |" not in row


def test_report_rewrites_a_hand_edited_md(repo):
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    run(repo, "end", "--system", "demo", "--outcome", "blocked", "--at", at(7))
    C.md_path(repo).write_text("# 我手改的\n", encoding="utf-8")
    C.write_report(repo)
    assert "我手改的" not in C.md_path(repo).read_text(encoding="utf-8")


def test_appending_an_event_regenerates_the_md_in_the_same_lock(repo):
    """漂被**做没了**，不是靠「记完事件记得跑 report」这条纪律 ——
    纪律问题最后总会发生。"""
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    assert "进行中" in C.md_path(repo).read_text(encoding="utf-8")
    run(repo, "end", "--system", "demo", "--outcome", "abandoned", "--at", at(12))
    md = C.md_path(repo).read_text(encoding="utf-8")
    assert "abandoned" in md and "12.0" in md


def test_report_on_an_empty_ledger_is_green(repo):
    path, summary = C.write_report(repo)
    assert summary["total"]["systems"] == 0
    assert "还没有接入记录" in path.read_text(encoding="utf-8")


def test_two_systems_each_get_a_row_in_first_begin_order(repo):
    (repo / "integrations" / "b").mkdir()
    run(repo, "begin", "--system", "demo", "--who", "agent", "--at", at(0))
    run(repo, "begin", "--system", "b", "--who", "human", "--at", at(1))
    run(repo, "end", "--system", "b", "--outcome", "blocked", "--at", at(6))
    run(repo, "end", "--system", "demo", "--outcome", "passed_real_task", "--at", at(30))
    rows = C.summarize(events(repo))["rows"]
    assert [r["system"] for r in rows] == ["demo", "b"]
    assert [r["active_minutes"] for r in rows] == [30.0, 5.0]


# ===========================================================================
# 6. 仓库里那两份现在就是好的
# ===========================================================================
def test_the_real_ledger_parses():
    C.read_events(_REPO_ROOT)                       # 坏了就在这里炸，带行号


def test_the_real_md_is_in_sync_with_the_real_ledger():
    """`COST.md` 必须**正好**是当前账本算出来的样子。

    红了怎么办：`$PY -m integrations.cost report` —— 一条命令，不是一次调查。
    """
    want = C.render_markdown(C.summarize(C.read_events(_REPO_ROOT)))
    got = C.md_path(_REPO_ROOT).read_text(encoding="utf-8")
    assert got == want, "COST.md 和 COST.jsonl 漂了；跑 `python -m integrations.cost report`"


def test_the_ledger_and_md_are_not_group_or_world_readable():
    """红线 5：`$GB` 全树 go-rwx。这两份就在 `$GB/repo/integrations/` 下。"""
    for p in (C.jsonl_path(_REPO_ROOT), C.md_path(_REPO_ROOT)):
        assert p.is_file(), p
        assert p.stat().st_mode & 0o077 == 0, f"{p} 是 {oct(p.stat().st_mode & 0o777)}"


def test_cost_dir_is_not_mistaken_for_an_integration():
    """`integrations/cost/` 是工具不是接入：它没有 `launch.json` / `config.yaml`，
    于是两处发现入口都不会把它当成一个被测系统（W-0 的判据是「目录里有没有那个文件」）。"""
    d = _REPO_ROOT / "integrations" / "cost"
    assert d.is_dir()
    assert not (d / "launch.json").exists() and not (d / "config.yaml").exists()
    from runner.c42 import harness_commands as HC
    assert d not in HC.launch_dirs(_REPO_ROOT)
    from runner import registry as REG
    assert all(d not in p.parents for p in REG.config_files(_REPO_ROOT))
