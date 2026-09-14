# -*- coding: utf-8 -*-
"""`runner/f02/answer_plane_guard.py` 的判据（N-61 补强，2026-09-05）。

这道门会**删文件**。所以每条测试要么证明它**该删的删了**，
要么证明它**不该删的一个都没碰** —— 后者和前者一样重要：
一个会误删 runner 自己代码的门，第一次误删之后就会被人关掉。
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "runner" / "f02"))
import answer_plane_guard as G                              # noqa: E402

GOLD = "GBC-G-" + "0123456789abcdef"


def _tree(root: Path) -> Path:
    """一棵**合法的**执行面树：bundle + run dir + 边车，含合法的 control/x 串。"""
    d = root / "runner_root"
    (d / "tasks" / "t1" / "work").mkdir(parents=True)
    (d / "runs" / "r1" / "log").mkdir(parents=True)
    (d / "exec" / "genetask").mkdir(parents=True)
    (d / "tasks" / "t1" / "task.yaml").write_text(
        "# x_token: GBC-X-" + "f" * 16 + "\ntask_id: t1\n", encoding="utf-8")
    (d / "tasks" / "t1" / "work" / "S1.json").write_text('{"stage":"S1"}', encoding="utf-8")
    (d / "runs" / "r1" / "log" / "egress.jsonl").write_text('{"ok":1}\n', encoding="utf-8")
    # `exec/genetask/bundle.py:77` 那句真注释：**含 `gold_token` 字样但不含串值**
    (d / "exec" / "genetask" / "bundle.py").write_text(
        "# 自查：`\\b` 把下划线当单词字符 —— gold_ref / gold_token / probe_field 全逃掉。\n",
        encoding="utf-8")
    (d / "runs" / "r1" / "INSTRUCTION.md").write_text(
        "校验串：GBC-C-" + "a" * 16 + "\n", encoding="utf-8")
    return d


# ---------------------------------------------------------------- 不该动的一个都不许动
def test_a_legitimate_execution_plane_tree_is_untouched(tmp_path):
    """**防恒红。** 一个会误删 runner 自己代码的门，第一次误删之后就会被人关掉。

    这棵树里故意放了三个**容易误伤**的东西：
    合法的 `GBC-C-`/`GBC-X-` 串、以及 `exec/genetask/bundle.py` 里那句
    真的含「gold_token」字样、却不含串值的注释。
    """
    d = _tree(tmp_path)
    before = sorted(p.relative_to(d) for p in d.rglob("*"))
    assert G.scan(d) == []
    rc = G.main(["--root", str(d), "--log", str(tmp_path / "l.jsonl")])
    assert rc == 0
    assert sorted(p.relative_to(d) for p in d.rglob("*")) == before
    assert not (tmp_path / "l.jsonl").exists(), "干净的一轮不该写日志"


@pytest.mark.parametrize("tok", ["GBC-C-" + "a" * 16, "GBC-X-" + "b" * 16,
                                 "GBC-G-" + "A" * 16, "GBC-G-" + "0" * 15])
def test_non_gold_token_shapes_are_not_matched(tmp_path, tok):
    """`GBC-C-`/`GBC-X-` 是**设计上要进执行面的**；大写十六进制与短一位都不是 gold 形状。"""
    d = tmp_path / "r"
    d.mkdir()
    (d / "f.txt").write_text(tok, encoding="utf-8")
    assert G.scan(d) == []


# ---------------------------------------------------------------- 该删的必须删
def test_the_actual_incident_shape(tmp_path):
    """**2026-09-05 当晚真的落在 f02 上的那棵树。**"""
    d = _tree(tmp_path)
    ref = d / "a1" / "reference" / "tasks" / "v1.0-smoke" / "s1-cor-01"
    ref.mkdir(parents=True)
    (ref / "canary.json").write_text(json.dumps({"gold_token": GOLD}), encoding="utf-8")
    (ref / "scorer.yaml").write_text(f"# gold_token: {GOLD}\n", encoding="utf-8")
    (ref / "solution").mkdir()
    (ref / "solution" / "solve.py").write_text("# oracle\n", encoding="utf-8")
    (ref / "_ledger.jsonl").write_text(json.dumps({"t": GOLD}) + "\n", encoding="utf-8")
    # 那晚还有一份**名字无辜**的：D 面 task.yaml 里第一行就是 `# gold_token: <串>`
    (ref / "task.yaml").write_text(f"# gold_token: {GOLD}\nstage: S1\n", encoding="utf-8")
    hits = G.scan(d)
    kinds = {h.kind for h in hits}
    assert {"answer_plane_dir", "answer_plane_name", "gold_token"} <= kinds, hits
    # 名字命中的那些，**内容里有 gold 串这件事也要记下来** ——
    # 事后评估一次泄漏有多重，靠的是内容，不是文件名。
    named = [h for h in hits if h.kind == "answer_plane_name" and h.path.endswith("canary.json")]
    assert named and "gold 串" in named[0].detail, named
    G.purge(hits, d, log_path=tmp_path / "l.jsonl")
    assert not (d / "a1" / "reference").exists(), "答案面目录没被删干净"
    assert G.scan(d) == [], "删完之后必须干净"


def test_gold_token_in_a_binary_file_with_an_innocent_name(tmp_path):
    """**只有内容判据能抓的形状**：名字无辜、路径无辜、二进制。

    「答案面的任何派生副本都是答案面」（D-24）—— 按后缀白名单扫等于给 `.parquet` 免检。
    """
    d = tmp_path / "r"
    (d / "runs" / "r1" / "work").mkdir(parents=True)
    p = d / "runs" / "r1" / "work" / "values.parquet"
    p.write_bytes(b"PAR1" + b"\x00" * 100 + GOLD.encode() + b"\x00" * 100)
    hits = G.scan(d)
    assert len(hits) == 1 and hits[0].kind == "gold_token", hits
    assert hits[0].sha256 and hits[0].size > 0, "删之前必须先记下 sha256 与字节数"


def test_gold_token_straddling_a_chunk_boundary_is_still_found(tmp_path):
    """**跨块边界**的串。重叠不够就会漏 —— 而漏了没有任何东西会说。"""
    d = tmp_path / "r"
    d.mkdir()
    p = d / "big.bin"
    pad = G._CHUNK - 8                      # 让串横跨第一块与第二块
    p.write_bytes(b"\x00" * pad + GOLD.encode() + b"\x00" * 64)
    assert G.has_gold(p) == GOLD
    assert [h.kind for h in G.scan(d)] == ["gold_token"]


@pytest.mark.parametrize("name", list(G.ANSWER_PLANE_NAMES))
def test_every_answer_plane_filename_is_caught_even_when_empty(tmp_path, name):
    """文件名判据是**第二层纵深**：一个空的 `solve.py` 里没有任何 gold 串。"""
    d = tmp_path / "r"
    (d / "runs" / "r1").mkdir(parents=True)
    (d / "runs" / "r1" / name).write_text("", encoding="utf-8")
    hits = G.scan(d)
    assert [h.kind for h in hits] == ["answer_plane_name"], hits


@pytest.mark.parametrize("dirname", list(G.ANSWER_PLANE_DIRS))
def test_answer_plane_dirname_is_caught_with_innocent_contents(tmp_path, dirname):
    """目录判据是**第三层**：目录名是答案面的，里面的文件名与内容都无辜。"""
    d = tmp_path / "r"
    (d / "work" / dirname).mkdir(parents=True)
    (d / "work" / dirname / "notes.md").write_text("# 只是笔记\n", encoding="utf-8")
    hits = G.scan(d)
    assert any(h.kind == "answer_plane_dir" for h in hits), hits
    G.purge(hits, d, log_path=tmp_path / "l.jsonl")
    assert not (d / "work" / dirname).exists()


# ---------------------------------------------------------------- 删除的边界
def test_refuses_to_delete_outside_the_root(tmp_path):
    """构造一条指向 root 之外的命中：必须**拒绝删除**并记下理由。"""
    d = tmp_path / "r"
    d.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("别碰我", encoding="utf-8")
    fake = G.Hit("../outside.txt", "gold_token", "构造", 3, "x")
    recs = G.purge([fake], d, log_path=tmp_path / "l.jsonl")
    assert outside.exists(), "删到 root 外面去了"
    assert recs[0]["extra"]["deleted"] is False
    assert "root 之外" in recs[0]["extra"]["error"]


def test_refuses_to_delete_the_root_itself(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    recs = G.purge([G.Hit(".", "answer_plane_dir", "构造", 0, "", is_dir=True)],
                   d, log_path=tmp_path / "l.jsonl")
    assert d.exists() and recs[0]["extra"]["deleted"] is False


def test_symlinks_are_not_followed_out_of_the_root(tmp_path):
    """跟进符号链接会让扫描走出 root，而删除阶段拒绝 root 之外 ——
    两者不一致就会留下一条「报了却删不掉」的永久红。"""
    outside = tmp_path / "out"
    outside.mkdir()
    (outside / "canary.json").write_text(GOLD, encoding="utf-8")
    d = tmp_path / "r"
    d.mkdir()
    os.symlink(outside, d / "link")
    assert G.scan(d) == []
    assert (outside / "canary.json").exists()


def test_unreadable_file_is_a_finding_and_is_not_deleted(tmp_path):
    """读不了 ≠ 查过了没有（F7）。而且**不许删** —— 删掉就没人知道它是什么了。"""
    d = tmp_path / "r"
    d.mkdir()
    p = d / "opaque.bin"
    p.write_bytes(b"x")
    os.chmod(p, 0o000)
    try:
        if os.access(p, os.R_OK):
            pytest.skip("本进程仍能读 0000 文件（root?），这条判据在此环境无法证伪")
        hits = G.scan(d)
        assert [h.kind for h in hits] == ["unreadable"], hits
        recs = G.purge(hits, d, log_path=tmp_path / "l.jsonl")
        assert p.exists() and recs[0]["extra"]["deleted"] is False
        assert "人工处置" in recs[0]["extra"]["error"]
    finally:
        os.chmod(p, 0o600)


def test_dry_run_deletes_nothing(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    (d / "canary.json").write_text(GOLD, encoding="utf-8")
    recs = G.purge(G.scan(d), d, log_path=tmp_path / "l.jsonl", dry_run=True)
    assert (d / "canary.json").exists()
    assert recs[0]["extra"]["deleted"] is False and "dry-run" in recs[0]["extra"]["error"]


# ---------------------------------------------------------------- 证据
def test_detected_is_logged_before_the_delete(tmp_path):
    """进程死在删的中途也要留得下证据 —— 所以 `detected` 先落盘、`purged` 后落盘。"""
    d = tmp_path / "r"
    d.mkdir()
    (d / "canary.json").write_text(GOLD, encoding="utf-8")
    log = tmp_path / "l.jsonl"
    G.purge(G.scan(d), d, log_path=log)
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    phases = [r["params"]["phase"] for r in rows]
    assert phases == ["detected", "purged"], phases
    assert all(r["reason"] == G.REASON and r["decision"] == "deny" for r in rows)
    assert rows[0]["extra"]["sha256"], "sha256 必须在删之前就记下来"
    assert rows[1]["extra"]["deleted"] is True


def test_log_file_and_dir_modes_are_tight(tmp_path):
    """日志里有被删物的路径与 sha256 —— 它自己也不许对组/其它开放。

    **现场把 umask 放回 002**：conftest 把会话 umask 收到 0077，
    那会让这条测试**恒绿**（`open()` 自己就落成 0600，`chmod` 删掉也不红），
    而 f02 上的 umask 是 002。恒绿的门与恒红的一样会被绕过（F7）。
    """
    old = os.umask(0o002)
    try:
        d = tmp_path / "r"
        d.mkdir()
        (d / "canary.json").write_text(GOLD, encoding="utf-8")
        log = tmp_path / "logs" / "answer_plane.jsonl"
        G.purge(G.scan(d), d, log_path=log)
        assert (os.stat(log).st_mode & 0o077) == 0, oct(os.stat(log).st_mode)
        assert (os.stat(log.parent).st_mode & 0o077) == 0
    finally:
        os.umask(old)


def test_record_shape_matches_gateway_access_log(tmp_path, monkeypatch):
    """**D-21 对齐断言**：两个独立来源写同一种记录，键集与键序必须相等。

    照着抄很容易，抄完之后网关加一个字段、这边不知道 —— 那时两份日志
    在 `jq` 里长得不一样，而没有任何东西会说。
    """
    from gateway import access_log as AL
    monkeypatch.setattr(AL, "ACCESS_LOG", tmp_path / "gw.jsonl")
    gw = AL.record(method="GET", path="/bars", params={}, as_of=None,
                   decision="deny", status=403, reason="asof_beyond_freeze",
                   extra={"x": 1}, path_override=None) if False else AL.record(
        method="GET", path="/bars", params={}, as_of=None, decision="deny",
        status=403, reason="asof_beyond_freeze", extra={"x": 1})
    mine = G.record(G.Hit("p", "gold_token", "d", 1, "s"), root="/r",
                    phase="detected", deleted=None)
    assert list(mine) == list(gw), f"键序不一致：\n本文件 {list(mine)}\n网关   {list(gw)}"
    assert list(mine) == list(G.RECORD_KEYS)


# ---------------------------------------------------------------- 退出码
def test_exit_codes(tmp_path):
    """0 = 干净；**1 = 有命中（不论删没删干净）**；2 = 扫不了。

    「删干净了」不等于「没发生过」—— 调用方要能靠退出码知道刚才发生了一次泄漏。
    """
    d = tmp_path / "r"
    d.mkdir()
    assert G.main(["--root", str(d), "--log", str(tmp_path / "l.jsonl")]) == 0
    (d / "canary.json").write_text(GOLD, encoding="utf-8")
    assert G.main(["--root", str(d), "--log", str(tmp_path / "l.jsonl")]) == 1
    assert not (d / "canary.json").exists()
    assert G.main(["--root", str(tmp_path / "nope"), "--log", str(tmp_path / "l.jsonl")]) == 2


# ---------------------------------------------------------------- 闩
def test_a_hit_trips_a_latch_that_a_clean_run_does_not_clear(tmp_path):
    """**在我不在场时留住证据。**

    真机实测（2026-09-05）：`SuccessExitStatus=0 1` 让 systemd 把一次真实拦截
    报成 `Result=success ExecMainStatus=0`；就算改成 failed，timer 每小时跑一次，
    下一次干净运行会把 failed 覆盖掉 —— 凌晨三点拦下的一次泄漏，早上就看不见了。
    """
    d = tmp_path / "r"
    d.mkdir()
    log = tmp_path / "logs" / "ap.jsonl"
    (d / "canary.json").write_text(GOLD, encoding="utf-8")
    assert G.main(["--root", str(d), "--log", str(log)]) == 1
    latch = G.latch_path(log)
    assert latch.exists(), "命中之后没有落闩"
    first = latch.read_text(encoding="utf-8")
    assert "canary.json" in first and GOLD[:10] not in first, \
        "闩里要有路径，但**不许有 gold 串本身** —— 证据要留，内容不留"
    # 干净的一轮：闩必须原样还在
    assert G.main(["--root", str(d), "--log", str(log)]) == 0
    assert latch.read_text(encoding="utf-8") == first, "干净的一轮把闩清掉了"


def test_a_second_incident_appends_and_does_not_overwrite(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    log = tmp_path / "logs" / "ap.jsonl"
    (d / "canary.json").write_text(GOLD, encoding="utf-8")
    G.main(["--root", str(d), "--log", str(log)])
    (d / "scorer.yaml").write_text(GOLD, encoding="utf-8")
    G.main(["--root", str(d), "--log", str(log)])
    txt = G.latch_path(log).read_text(encoding="utf-8")
    assert "canary.json" in txt and "scorer.yaml" in txt, "第二次事件把第一次顶掉了"


def test_latch_mode_is_tight(tmp_path):
    old = os.umask(0o002)
    try:
        d = tmp_path / "r"
        d.mkdir()
        log = tmp_path / "logs" / "ap.jsonl"
        (d / "canary.json").write_text(GOLD, encoding="utf-8")
        G.main(["--root", str(d), "--log", str(log)])
        assert (os.stat(G.latch_path(log)).st_mode & 0o077) == 0
    finally:
        os.umask(old)


# ---------------------------------------------------------------- 自噬（真机 2026-09-05 实测）
def test_the_guard_does_not_delete_its_own_log(tmp_path):
    """**门吃掉自己日志的那个循环。**

    真机实测：日志与闩都住在扫描根**里面**，而一条带完整串的注解写进日志之后，
    下一轮扫描把**日志自己**判成 `gold_token` 并删掉了 ——
    证据文件因为记录了证据而变成违禁品，整条审计链被它自己的门清空。
    """
    d = tmp_path / "r"
    (d / "logs").mkdir(parents=True)
    log = d / "logs" / "ap.jsonl"                 # 日志在扫描根**里面**
    log.write_text(json.dumps({"note": f"有人往里写了 {GOLD}"}) + "\n", encoding="utf-8")
    hits = G.scan(d)
    assert any(h.path.endswith("ap.jsonl") and h.kind == "gold_token" for h in hits), \
        "日志里的串没被扫出来 —— 那是豁免，不是修复"
    assert G.token_ref(GOLD).startswith("sha256:") and GOLD[:10] not in G.token_ref(GOLD)
    recs = G.purge(hits, d, log_path=log)
    assert log.exists(), "**门删掉了自己的日志**"
    mine = [r for r in recs if r["path"].endswith("ap.jsonl")][0]
    assert mine["extra"]["deleted"] is False and "拒绝自删" in mine["extra"]["error"]


def test_the_guard_does_not_delete_its_own_latch(tmp_path):
    d = tmp_path / "r"
    (d / "logs").mkdir(parents=True)
    log = d / "logs" / "ap.jsonl"
    (d / "canary.json").write_text(GOLD, encoding="utf-8")
    G.main(["--root", str(d), "--log", str(log)])
    latch = G.latch_path(log)
    assert latch.exists()
    latch.write_text(latch.read_text(encoding="utf-8") + f"\n有人写了 {GOLD}\n", encoding="utf-8")
    G.main(["--root", str(d), "--log", str(log)])
    assert latch.exists(), "**门删掉了自己的闩**"


def test_written_evidence_is_redacted(tmp_path):
    """**证据要留，内容不留。** 写出去的任何文本里不许出现完整 gold 串。"""
    d = tmp_path / "r"
    (d / "logs").mkdir(parents=True)
    log = d / "logs" / "ap.jsonl"
    (d / "work").mkdir()
    (d / "work" / "x.bin").write_bytes(GOLD.encode())
    G.main(["--root", str(d), "--log", str(log)])
    for f in (log, G.latch_path(log)):
        txt = f.read_text(encoding="utf-8")
        assert GOLD not in txt, f"{f.name} 里出现了完整 gold 串"
        # **一位都不留**：连 `GBC-G-` 前缀都不写，只写 sha256 引用。
        # 写前缀（原来是 `tok[:10]`）既漏 4 位十六进制，又让日志自己变成扫描目标。
        assert "GBC-G-" not in txt, f"{f.name} 里还有 gold 串的前缀"
        assert "sha256:" in txt, f"{f.name} 里没有可对照的哈希引用"


def test_redaction_pattern_is_derived_not_copied():
    """脱敏与扫描必须用**同一个**模式。抄一份会漂，漂了就等于没脱敏。"""
    assert G._GOLD_TEXT_RE.pattern == G.GOLD_TOKEN_RE.pattern.decode("ascii")
    assert G.redact(GOLD) != GOLD and "redacted" in G.redact(GOLD)
    assert G.redact("GBC-C-" + "a" * 16) == "GBC-C-" + "a" * 16, "只脱 gold，不动 control/x"


def test_owned_paths_are_reported_not_exempted(tmp_path):
    """拒绝自删 ≠ 豁免：它们照样被扫、照样进日志、照样落闩。

    豁免会造出一个「往日志里藏答案面」的口子。
    """
    d = tmp_path / "r"
    (d / "logs").mkdir(parents=True)
    log = d / "logs" / "ap.jsonl"
    log.write_text(f"{GOLD}\n", encoding="utf-8")
    rc = G.main(["--root", str(d), "--log", str(log)])
    assert rc == 1, "自己的日志里有串，必须仍然算命中"
    assert G.latch_path(log).exists(), "自己的日志命中也要落闩"


def test_a_path_containing_a_token_is_redacted_in_the_evidence(tmp_path):
    """**自噬循环的另一个入口**：串在**路径**里。

    `mkdir <一个以 gold 串命名的目录>` 之后，原样写进日志的 `path` 会让日志自己
    再次变成违禁品。脱敏必须覆盖路径，不只是 detail。
    """
    d = tmp_path / "r"
    (d / "logs").mkdir(parents=True)
    log = d / "logs" / "ap.jsonl"
    (d / GOLD).mkdir()
    (d / GOLD / "canary.json").write_text("{}", encoding="utf-8")
    rc = G.main(["--root", str(d), "--log", str(log)])
    assert rc == 1
    for f in (log, G.latch_path(log)):
        assert GOLD not in f.read_text(encoding="utf-8"), f"{f.name} 的 path 没脱敏"
    # 而且日志自己不许因此被下一轮吃掉
    assert G.main(["--root", str(d), "--log", str(log)]) == 0
    assert log.exists()


def test_named_answer_plane_file_that_also_holds_a_token_uses_a_hash_ref(tmp_path):
    """名字命中 + 内容也有串的那一支，同样只许写哈希引用。

    两支各写各的措辞，很容易只改一处 —— 所以两支都要有测试盯着。
    """
    d = tmp_path / "r"
    (d / "logs").mkdir(parents=True)
    log = d / "logs" / "ap.jsonl"
    (d / "canary.json").write_text(f'{{"gold_token": "{GOLD}"}}', encoding="utf-8")
    hits = G.scan(d)
    named = [h for h in hits if h.kind == "answer_plane_name"][0]
    assert "sha256:" in named.detail and "GBC-G-" not in named.detail, named.detail
    G.purge(hits, d, log_path=log)
    assert "GBC-G-" not in log.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 门不许吃掉自己
def test_the_guard_source_contains_no_literal_gold_token():
    """**自噬的真正成因**（2026-09-05 真机实测）。

    门必须谈论串的形状，所以它天然容易成为自己的猎物：
    我在一句注释里写了 `mkdir <一个完整的示例串>`，下一轮扫描把**门自己**删了，
    此后每次运行都是 `rc=2 文件不存在` —— 门把自己关掉了，而且**看起来像环境坏了**。

    示例串一律写成抽象形（`<gold 串>`），要构造真串就在运行时拼（本文件的 `GOLD` 就是）。
    """
    src = Path(G.__file__).read_text(encoding="utf-8")
    hits = G._GOLD_TEXT_RE.findall(src)
    assert not hits, f"门自己的源码里有完整 gold 串：{hits}"
    # 判别力：这条断言不是恒绿 —— 同一个判据对一个真串必须命中
    assert G._GOLD_TEXT_RE.findall(f"x {GOLD} y") == [GOLD]


def test_the_guard_does_not_delete_its_own_source(tmp_path, monkeypatch):
    """就算将来有人又往源码里写了一个串，门也只许**报**，不许**自删**。"""
    d = tmp_path / "r"
    (d / "logs").mkdir(parents=True)
    fake_src = d / "answer_plane_guard.py"
    fake_src.write_text(f"# 示例 {GOLD}\n", encoding="utf-8")
    monkeypatch.setattr(G, "__file__", str(fake_src))
    log = d / "logs" / "ap.jsonl"
    rc = G.main(["--root", str(d), "--log", str(log)])
    assert rc == 1, "门自己的源码里有串，必须仍然算命中"
    assert fake_src.exists(), "**门删掉了自己的源码**"


def test_redaction_leaves_no_gold_prefix_at_all():
    """脱敏后的文本里连 `GBC-G-` 都不许留。

    留前缀既让「日志里不许有 GBC-G-」这条断言站不住，
    也让人一眼看去以为还有残留 —— 而它其实已经不是串了。
    """
    out = G.redact(f"路径 /a/{GOLD}/b 里")
    assert GOLD not in out and "GBC-G-" not in out, out
    assert "gold:redacted" in out and "sha256:" in out


# ---------------------------------------------------------------- 路径里的串
def test_a_directory_named_after_a_token_is_caught(tmp_path):
    """**真机实测漏过一次**：目录名本身是串，里面的文件完全干净。

    前三条判据（内容 / 已知文件名 / 已知目录名）一条都不占，
    而目录名会随每一次 `ls` 泄漏出去。
    """
    d = tmp_path / "r"
    (d / GOLD).mkdir(parents=True)
    (d / GOLD / "note.txt").write_text("x", encoding="utf-8")   # 内容干净
    hits = G.scan(d)
    assert any(h.kind == "gold_token_in_path" for h in hits), hits
    G.purge(hits, d, log_path=tmp_path / "l.jsonl")
    assert not (d / GOLD).exists(), "以串命名的目录没被删"


def test_a_file_named_after_a_token_is_caught(tmp_path):
    d = tmp_path / "r"
    d.mkdir()
    (d / f"{GOLD}.txt").write_text("x", encoding="utf-8")
    hits = G.scan(d)
    assert [h.kind for h in hits] == ["gold_token_in_path"], hits
    G.purge(hits, d, log_path=tmp_path / "l.jsonl")
    assert not (d / f"{GOLD}.txt").exists()


def test_path_token_evidence_is_redacted_and_hash_referenced(tmp_path):
    d = tmp_path / "r"
    (d / "logs").mkdir(parents=True)
    log = d / "logs" / "ap.jsonl"
    (d / GOLD).mkdir()
    (d / GOLD / "x").write_text("x", encoding="utf-8")
    assert G.main(["--root", str(d), "--log", str(log)]) == 1
    for f in (log, G.latch_path(log)):
        t = f.read_text(encoding="utf-8")
        assert GOLD not in t and "GBC-G-" not in t, f"{f.name} 里有串或前缀"
        assert "sha256:" in t


# ---------------------------------------------------------------- 自身完整性（裁定 2026-09-05）
def test_identity_covers_the_three_own_files():
    ident = G.identity()
    assert len(ident) == 3, ident
    names = " ".join(ident)
    assert "answer_plane_guard.py" in names
    assert "genebench-answer-plane-scan.service" in names
    assert "genebench-answer-plane-scan.timer" in names


def test_unreadable_own_file_is_recorded_as_none_with_a_reason(tmp_path, monkeypatch):
    """**「没装单元」与「装了但没记」必须分得开** —— 读不到就记 `None` 并附原因，不省略。"""
    monkeypatch.setattr(G, "OWN_FILES", (str(tmp_path / "nope.txt"),))
    ident = G.identity()
    v = next(iter(ident.values()))
    assert v["sha256"] is None and "error" in v


def test_identity_drift_is_reported_and_the_scan_still_runs(tmp_path, monkeypatch):
    """**自检失败不许停掉这道门。**

    因为自检失败就不扫，等于让「把门改坏」成为**关掉门**的办法。
    正确行为：报出来、落闩，**照常扫**。
    """
    src = tmp_path / "guard_copy.py"
    src.write_text("# 假的门源码\n", encoding="utf-8")
    base = tmp_path / "id.json"
    monkeypatch.setattr(G, "OWN_FILES", (str(src),))
    monkeypatch.setattr(G, "identity_path", lambda: base)
    base.write_text(json.dumps({str(src): {"sha256": "0" * 64, "size": 1}}), encoding="utf-8")
    drift = G.check_identity()
    assert drift and "sha256 变了" in drift[0]

    d = tmp_path / "r"
    (d / "logs").mkdir(parents=True)
    (d / "canary.json").write_text(GOLD, encoding="utf-8")
    log = d / "logs" / "ap.jsonl"
    assert G.main(["--root", str(d), "--log", str(log)]) == 1
    assert not (d / "canary.json").exists(), "自检不一致就不扫了 —— 那正是不能有的行为"
    txt = log.read_text(encoding="utf-8")
    assert "guard_integrity" in txt, "完整性不一致没有进日志"
    assert G.latch_path(log).exists()


def test_no_baseline_is_not_a_drift(tmp_path, monkeypatch):
    """没有基线 ≠ 不一致。首次部署前不该凭空报红。"""
    monkeypatch.setattr(G, "identity_path", lambda: tmp_path / "absent.json")
    assert G.check_identity() == []


def test_inject_records_the_guard_identity():
    """**他证**：`inject.json` 里要有这三个 sha，好让 f01 拿仓库那份去比。

    门自己也核 —— 但改了门的人也能改基线，**自证不能是唯一的证明**。
    """
    import ast as _ast
    src = (Path(G.__file__).resolve().parents[2] / "runner" / "inject.py").read_text(encoding="utf-8")
    tree = _ast.parse(src)
    keys = {n.value for n in _ast.walk(tree)
            if isinstance(n, _ast.Constant) and isinstance(n.value, str)}
    assert "answer_plane_guard" in keys, "inject.json 里没记门的 identity"
    assert "APG.identity()" in src or "identity()" in src


def test_drift_alone_is_still_a_nonzero_exit(tmp_path, monkeypatch):
    """**树干净但门自己漂了** —— 退出码仍须非零。

    返回 0 的话，一次部署少写 `--write-identity` 就再也没人知道 ——
    而那正是「门还在、但已经不是我们部署的那份」的形态。
    """
    src = tmp_path / "guard_copy.py"
    src.write_text("# 假的门\n", encoding="utf-8")
    base = tmp_path / "id.json"
    base.write_text(json.dumps({str(src): {"sha256": "0" * 64, "size": 1}}), encoding="utf-8")
    monkeypatch.setattr(G, "OWN_FILES", (str(src),))
    monkeypatch.setattr(G, "identity_path", lambda: base)
    d = tmp_path / "clean"
    (d / "logs").mkdir(parents=True)
    (d / "work").mkdir()
    (d / "work" / "ok.json").write_text("{}", encoding="utf-8")
    log = d / "logs" / "ap.jsonl"
    assert G.scan(d) == [], "前提搭错：这棵树必须是干净的"
    assert G.main(["--root", str(d), "--log", str(log)]) == 1
    assert G.latch_path(log).exists()


def test_a_clean_tree_with_matching_identity_is_zero(tmp_path, monkeypatch):
    """反面：树干净 + 基线一致 ⇒ 0。防上一条把退出码写成恒 1。"""
    src = tmp_path / "guard_copy.py"
    src.write_text("# 门\n", encoding="utf-8")
    base = tmp_path / "id.json"
    monkeypatch.setattr(G, "OWN_FILES", (str(src),))
    monkeypatch.setattr(G, "identity_path", lambda: base)
    base.write_text(json.dumps(G.identity()), encoding="utf-8")
    assert G.check_identity() == []
    d = tmp_path / "clean"
    (d / "work").mkdir(parents=True)
    (d / "work" / "ok.json").write_text("{}", encoding="utf-8")
    assert G.main(["--root", str(d), "--log", str(tmp_path / "l.jsonl")]) == 0


# ---------------------------------------------------------------- D-27 实施要求：段数可数
#: 接收侧门声称保护的段。
CLAIMED_SECTIONS: dict[str, str] = {
    "gold_token_content": "test_gold_token_in_a_binary_file_with_an_innocent_name",
    "chunk_boundary": "test_gold_token_straddling_a_chunk_boundary_is_still_found",
    "answer_plane_name": "test_every_answer_plane_filename_is_caught_even_when_empty",
    "answer_plane_dirname": "test_answer_plane_dirname_is_caught_with_innocent_contents",
    "token_in_path": "test_a_directory_named_after_a_token_is_caught",
    "unreadable": "test_unreadable_file_is_a_finding_and_is_not_deleted",
    "delete_outside_root": "test_refuses_to_delete_outside_the_root",
    "delete_root_itself": "test_refuses_to_delete_the_root_itself",
    "symlink_escape": "test_symlinks_are_not_followed_out_of_the_root",
    "self_log": "test_the_guard_does_not_delete_its_own_log",
    "self_latch": "test_the_guard_does_not_delete_its_own_latch",
    "self_source": "test_the_guard_does_not_delete_its_own_source",
    "identity_drift": "test_identity_drift_is_reported_and_the_scan_still_runs",
    "evidence_redaction": "test_written_evidence_is_redacted",
    "latch_persistence": "test_a_hit_trips_a_latch_that_a_clean_run_does_not_clear",
}


def test_every_claimed_section_has_a_red_test():
    """**判据是可数的**（D-27 实施要求）。这道门会删文件，段数尤其不能少。"""
    here = Path(__file__).read_text(encoding="utf-8")
    missing = {s: t for s, t in CLAIMED_SECTIONS.items() if f"def {t}" not in here}
    assert not missing, f"这些段没有对应的红测试：{missing}"
    assert len(CLAIMED_SECTIONS) == 15
