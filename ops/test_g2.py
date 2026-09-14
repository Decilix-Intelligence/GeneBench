# -*- coding: utf-8 -*-
"""卡 G2 的判据：**红线 2 从「答案面不上执行面」改写为「答案面永不挂进 agent 容器」**。

这道门改了口径，最容易出的事不是「写错了」，而是**改完之后没牙了** ——
判据从「扫一棵树」换成「扫挂载面」，而挂载面有三种写法、还可以指向一个此刻不存在的路径。
所以下面每一条要么证明**该红的当场红**，要么证明**该绿的没被误伤**。

另一半是公开树：它现在**带全部答案面**（用户裁定 N-627 走 B），
于是「树里有没有 solve.py」这个老判据反了过来 —— 没有它才是错的。
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "runner" / "f02"))
import answer_plane_guard as G                                    # noqa: E402

TREE = Path("/data/shared/genebench/release/trees/genebench")
TREES = TREE.parent
GOLD = "GBC-G-" + "0123456789abcdef"


# ════════════════════════════════ 夹具 ════════════════════════════════
def _run_dir(tmp_path: Path) -> Path:
    """一个**干净**的 run dir：work/ + log/，没有任何答案面。"""
    run = tmp_path / "runs" / "r1"
    (run / "work").mkdir(parents=True)
    (run / "log").mkdir(parents=True)
    (run / "work" / "task.yaml").write_text("task_id: s1-cor-01\n", encoding="utf-8")
    (run / "work" / "INSTRUCTION.md").write_text("做这道题。\n", encoding="utf-8")
    return run


def _compose(tmp_path: Path, body: str, name="compose.yml") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _goldbox(tmp_path: Path, name="gold") -> Path:
    """一份**真的带 gold 串**的目录 —— 名字是中性的，只有内容出卖它。"""
    d = tmp_path / name
    d.mkdir()
    (d / "s1-cor-01.json").write_text(json.dumps({"gold_token": GOLD}), encoding="utf-8")
    return d


# ═══════════════════ 一、这道门必须仍然有牙（任务书点名的那一条）═══════════════════
def test_mounting_gold_into_task_is_red(tmp_path):
    """**任务书点名的判据**：造一次「把 gold 挂进 /task」，必须当场红。

    这是整张卡的底：口径可以改，**牙不许掉**。
    """
    run = _run_dir(tmp_path)
    gold = _goldbox(tmp_path)
    cf = _compose(tmp_path, f"""\
        services:
          task:
            image: gb-cx-u:r1
            working_dir: /task
            volumes:
              - {run / 'work'}:/task
              - {gold}:/task/gold:ro
        """)
    hits = G.scan_container(cf, run_dir=run)
    assert hits, "把 gold 挂进 /task 居然判绿 —— **门没牙了**"
    assert any(h.kind == "gold_token" for h in hits)
    assert G.main(["--mode", "container", "--compose", str(cf), "--run-dir", str(run),
                   "--log", str(tmp_path / "l.jsonl")]) == 1


def test_mounting_the_reference_tree_into_task_is_red(tmp_path):
    """`reference/` 是目录名判据。挂它进容器 = 把 oracle 源码交给被测方。"""
    run = _run_dir(tmp_path)
    ref = tmp_path / "pkg" / "reference"
    ref.mkdir(parents=True)
    (ref / "solve.py").write_text("# oracle\n", encoding="utf-8")
    cf = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - {run / 'work'}:/task
              - {ref}:/task/ref:ro
        """)
    hits = G.scan_container(cf, run_dir=run)
    assert [h.kind for h in hits] == ["answer_plane_dir"]
    assert "/task/ref" in hits[0].detail


def test_a_mount_source_that_does_not_exist_yet_is_still_red(tmp_path):
    """**声明本身就是违规。**

    `- /x/reference:/task/ref` 这一条，哪怕 `reference/` 此刻还没建出来也要红 ——
    容器起来的那一刻它就在那儿了。「检查时不存在」与「运行时不存在」是两个时刻
    （同 `runner_core.lint_compose` 的 L-5a 那条 TOCTOU）。
    """
    run = _run_dir(tmp_path)
    ghost = tmp_path / "not_yet" / "reference"
    assert not ghost.exists()
    cf = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - {run / 'work'}:/task
              - {ghost}:/task/ref
        """)
    hits = G.scan_container(cf, run_dir=run)
    assert [h.kind for h in hits] == ["answer_plane_dir"]


def test_a_missing_neutral_source_is_a_finding_not_a_green(tmp_path):
    """源不存在、名字也中性：**扫不了 ≠ 扫过了没问题**（F7 同一条）。"""
    run = _run_dir(tmp_path)
    cf = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - {run / 'work'}:/task
              - {tmp_path / 'nope'}:/task/extra
        """)
    assert [h.kind for h in G.scan_container(cf, run_dir=run)] == ["unreadable"]


@pytest.mark.parametrize("syntax", ["short", "long", "driver_opts"])
def test_all_three_bind_syntaxes_are_seen(tmp_path, syntax):
    """三种 bind 写法一条都不许漏。

    第三种（顶层 named volume 的 `driver_opts: {type: none, device: …, o: bind}}`）
    在 service 段里长得和普通 named volume **一模一样**，肉眼与 grep 都过 ——
    2026-09-04 红队在 `lint_compose` 上实测过它，这里的判据与那边同源。
    """
    run = _run_dir(tmp_path)
    gold = _goldbox(tmp_path)
    bodies = {
        "short": f"""\
            services:
              task:
                volumes:
                  - {run / 'work'}:/task
                  - {gold}:/task/g:ro
            """,
        "long": f"""\
            services:
              task:
                volumes:
                  - {{type: bind, source: {gold}, target: /task/g, read_only: true}}
            """,
        "driver_opts": f"""\
            services:
              task:
                volumes:
                  - {run / 'work'}:/task
                  - sneak:/task/g
            volumes:
              sneak:
                driver_opts: {{type: none, device: {gold}, o: bind}}
            """,
    }
    hits = G.scan_container(_compose(tmp_path, bodies[syntax], f"c_{syntax}.yml"))
    assert any(h.kind == "gold_token" for h in hits), f"{syntax} 写法漏了"


def test_the_sidecar_service_is_watched_too(tmp_path):
    """信任边界是**容器**，不是服务名 `task`。挂给边车的一样要判。"""
    gold = _goldbox(tmp_path)
    cf = _compose(tmp_path, f"""\
        services:
          task:
            volumes: []
          gateway:
            volumes:
              - {gold}:/var/log/gb
        """)
    hits = G.scan_container(cf)
    assert any(h.kind == "gold_token" for h in hits)
    assert "gateway" in hits[0].path


def test_run_dir_holding_an_answer_plane_file_is_red(tmp_path):
    """判据②：run dir 里不得出现答案面（它是 agent 写得到、事后要归档的地方）。"""
    run = _run_dir(tmp_path)
    (run / "work" / "scorer.yaml").write_text("# 口径\n", encoding="utf-8")
    hits = G.scan_mount_face([], run_dir=run)
    assert [h.kind for h in hits] == ["answer_plane_name"]
    assert hits[0].path.startswith("run_dir/")


# ═══════════════════ 二、该绿的不许误伤（防恒红）═══════════════════
def test_the_real_compose_shape_is_green(tmp_path):
    """**照抄 `runner/c41/runner_core.COMPOSE_TMPL` 的形状**：只挂 work/ 与 log/。

    一个会把正常 run 判红的门，第一次误判之后就会被人关掉。
    """
    run = _run_dir(tmp_path)
    h11 = tmp_path / "h11"
    h11.mkdir()
    (h11 / "__init__.py").write_text("", encoding="utf-8")
    proxy = tmp_path / "egress_proxy.py"
    proxy.write_text("# 边车\n", encoding="utf-8")
    cf = _compose(tmp_path, f"""\
        services:
          gateway:
            volumes:
              - {proxy}:/opt/egress_proxy.py:ro
              - {h11}:/opt/h11:ro
              - {run / 'log'}:/var/log/gb
          task:
            working_dir: /task
            volumes:
              - {run / 'work'}:/task
        """)
    assert G.scan_container(cf, run_dir=run) == []
    assert G.main(["--mode", "container", "--compose", str(cf), "--run-dir", str(run),
                   "--log", str(tmp_path / "l.jsonl")]) == 0
    assert not (tmp_path / "l.jsonl").exists(), "干净的一轮不该写日志"


def test_legitimate_control_tokens_in_the_run_dir_are_not_answer_plane(tmp_path):
    """`GBC-C-` / `GBC-X-` 是**设计上要进容器的**，不许被误判。"""
    run = _run_dir(tmp_path)
    (run / "work" / "INSTRUCTION.md").write_text(
        "校验串：GBC-C-" + "a" * 16 + "\nx：GBC-X-" + "b" * 16 + "\n", encoding="utf-8")
    assert G.scan_mount_face([], run_dir=run) == []


# ═══════════════════ 三、处置：容器模式**一个字节都不删** ═══════════════════
def test_container_mode_deletes_nothing(tmp_path):
    """**与树模式相反，且必须相反。**

    容器模式命中的往往是答案面**本体**（`$GB/reference`、gold、公开树的 `scorer/`）——
    它只是被错误地挂了进去。删它等于把基准本身删了。
    """
    run = _run_dir(tmp_path)
    gold = _goldbox(tmp_path)
    victim = gold / "s1-cor-01.json"
    before = victim.read_bytes()
    cf = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - {gold}:/task/g
        """)
    assert G.main(["--mode", "container", "--compose", str(cf), "--run-dir", str(run),
                   "--log", str(tmp_path / "l.jsonl")]) == 1
    assert victim.exists() and victim.read_bytes() == before, "**容器模式删了东西**"
    recs = [json.loads(l) for l in (tmp_path / "l.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(r["extra"]["deleted"] is False for r in recs)


def test_container_mode_has_its_own_reason_code(tmp_path):
    """两道门的处置不同，日志里必须分得开。"""
    assert G.REASON_MOUNT != G.REASON
    run = _run_dir(tmp_path)
    gold = _goldbox(tmp_path)
    cf = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - {gold}:/task/g
        """)
    G.main(["--mode", "container", "--compose", str(cf), "--run-dir", str(run),
            "--log", str(tmp_path / "l.jsonl")])
    recs = [json.loads(l) for l in (tmp_path / "l.jsonl").read_text(encoding="utf-8").splitlines()]
    assert recs and all(r["reason"] == G.REASON_MOUNT for r in recs)
    # 记录形状仍与网关 access_log 同键同序（改口径不许把这条对齐断言弄丢）
    assert tuple(recs[0]) == G.RECORD_KEYS


def test_a_container_hit_trips_the_latch(tmp_path):
    """闩要留住证据 —— 命中之后的下一次干净扫描不许把它清掉。"""
    run = _run_dir(tmp_path)
    gold = _goldbox(tmp_path)
    log = tmp_path / "l.jsonl"
    cf_bad = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - {gold}:/task/g
        """, "bad.yml")
    G.main(["--mode", "container", "--compose", str(cf_bad), "--log", str(log)])
    latch = G.latch_path(log)
    assert latch.is_file()
    body = latch.read_text(encoding="utf-8")
    cf_ok = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - {run / 'work'}:/task
        """, "ok.yml")
    assert G.main(["--mode", "container", "--compose", str(cf_ok), "--log", str(log)]) == 0
    assert latch.read_text(encoding="utf-8") == body, "干净的一轮把闩清掉了"


def test_written_container_evidence_is_redacted(tmp_path):
    """证据要留、内容不留 —— gold 串不许原样落进日志或闩。"""
    gold = _goldbox(tmp_path)
    log = tmp_path / "l.jsonl"
    cf = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - {gold}:/task/g
        """)
    G.main(["--mode", "container", "--compose", str(cf), "--log", str(log)])
    for p in (log, G.latch_path(log)):
        assert GOLD not in p.read_text(encoding="utf-8")
        assert "GBC-G-" not in p.read_text(encoding="utf-8")


# ═══════════════════ 四、看不懂的挂载不许放行 ═══════════════════
def test_an_unparsable_volume_entry_is_a_finding(tmp_path):
    """看不懂 ≠ 没有挂载（D-23）。"""
    cf = _compose(tmp_path, """\
        services:
          task:
            volumes:
              - {read_only: true}
        """)
    assert [h.kind for h in G.scan_container(cf)] == ["unreadable"]


@pytest.mark.parametrize("src", ["./sneak", "../../data/shared", "~/gold", "${SNEAK}"])
def test_a_non_absolute_mount_source_is_a_finding(tmp_path, src):
    """相对路径 / `~` / `${VAR}`：compose **运行时**才解析，此刻判不了它指向哪。"""
    cf = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - "{src}:/task/x"
        """)
    assert [h.kind for h in G.scan_container(cf)] == ["unreadable"]


def test_bad_yaml_is_rc2_not_a_green(tmp_path):
    """解析不了要**响**，不许当成「查过了没有挂载」。"""
    cf = tmp_path / "c.yml"
    cf.write_text("services: [:\n", encoding="utf-8")
    with pytest.raises(G.GuardError):
        G.compose_mounts(cf)
    assert G.main(["--mode", "container", "--compose", str(cf),
                   "--log", str(tmp_path / "l.jsonl")]) == 2


def test_container_mode_with_nothing_to_look_at_is_rc2(tmp_path):
    """什么都不给的一次「绿」是假的。"""
    assert G.main(["--mode", "container", "--log", str(tmp_path / "l.jsonl")]) == 2


# ═══════════════════ 五、树模式没有被改坏（它降为第二道，不是退役）═══════════════════
def test_tree_mode_is_still_the_default(tmp_path):
    """f02 上那个每小时 timer 的命令行**一个字没改** —— 默认值动了就等于把它悄悄改了。"""
    d = tmp_path / "r"
    (d / "a1" / "reference").mkdir(parents=True)
    (d / "a1" / "reference" / "solve.py").write_text("# oracle\n", encoding="utf-8")
    assert G.main(["--root", str(d), "--log", str(tmp_path / "l.jsonl")]) == 1
    assert not (d / "a1" / "reference").exists(), "树模式该删的没删 —— 第二道也塌了"


def test_tree_mode_still_deletes_while_container_mode_does_not(tmp_path):
    """两道门的处置**相反**，这件事本身要有断言，不能只写在注释里。"""
    d = tmp_path / "r"
    d.mkdir()
    box = _goldbox(d, "gold")
    victim = box / "s1-cor-01.json"
    cf = _compose(tmp_path, f"""\
        services:
          task:
            volumes:
              - {box}:/task/g
        """)
    assert G.main(["--mode", "container", "--compose", str(cf),
                   "--log", str(tmp_path / "c.jsonl")]) == 1
    assert victim.exists(), "容器模式删了"
    assert G.main(["--root", str(d), "--log", str(tmp_path / "t.jsonl")]) == 1
    assert not victim.exists(), "树模式没删"


# ═══════════════════ 六、口径改写落到了文档与推送脚本上 ═══════════════════
DOCS = ("README.md", "docs/OPERATOR_MANUAL.md",
        "ops/specs/fairness_protocol.md", "ops/HANDOFF.md")


@pytest.mark.parametrize("rel", DOCS)
def test_each_doc_carries_the_new_wording_and_keeps_the_old_one(rel):
    """新口径要写明，**旧表述的历史说明也要留着** —— 否则下一个人会以为它一直是这样。"""
    s = (_REPO / rel).read_text(encoding="utf-8")
    assert "容器" in s and "挂进" in s, f"{rel} 没有容器边界的表述"
    assert "答案面不上执行面" in s, f"{rel} 把旧表述删了 —— 历史说明必须保留"
    assert "v1.0.16" in s, f"{rel} 没写口径是从哪一版开始改的"


def test_push_bundle_gates_on_the_container_mode():
    s = (_REPO / "ops/push_bundle_to_f02.sh").read_text(encoding="utf-8")
    assert "--mode container" in s
    assert "answer_plane_guard.py" in s
    # ④ 的落地树扫描必须还在（第二道没被换掉）
    assert "--root" in s and "落地扫描" in s


def test_push_exec_explains_why_the_tree_scan_stays():
    """保留第二道可以，但**要写清为什么** —— 任务书原话。"""
    s = (_REPO / "ops/push_exec_to_f02.sh").read_text(encoding="utf-8")
    assert "第二道" in s
    assert "exec/ 树不挂进任务容器" in s or "exec/ 不挂进任务容器" in s


# ═══════════════════ 七、公开树：判据反了过来 ═══════════════════
needs_tree = pytest.mark.skipif(not TREE.is_dir(),
                                reason=f"公开树不在这台机器上（{TREE}）—— 它由卡 G2 在 f01 上打")


@needs_tree
def test_the_public_tree_carries_the_whole_answer_plane():
    """**老判据反过来了**：上一版要求树里没有 `solve.py`，本版要求它在。"""
    assert (TREE / "reference").is_dir()
    assert (TREE / "scorer" / "score_run.py").is_file()
    assert (TREE / "genetask" / "templates").is_dir()
    assert (TREE / "genetask" / "params").is_dir()
    assert (TREE / "reference" / "calibration.py").is_file()
    assert len(list(TREE.rglob("solve.py"))) > 0, "参考实现不在树里 —— 外部用户算不出分"
    assert len(list(TREE.rglob("scorer.yaml"))) > 0


@needs_tree
def test_the_public_tree_has_no_memory_probe_keys():
    """记忆探针钥匙是唯一没被这次公开波及的判别力来源 —— 它公开就立刻失效。"""
    assert not (TREE / "reference" / "memory_probe_answers").exists()
    assert not list(TREE.rglob("memory_probe_answers"))


@needs_tree
def test_the_public_tree_has_no_credentials():
    pats = ("*.env", ".env*", "secrets*", "*.pem", "*.key", "id_ed25519*", "id_rsa*")
    found = [p for pat in pats for p in TREE.rglob(pat)
             if p.is_file() and ".git" not in p.parts]
    assert found == [], f"公开树里有凭据形态的文件：{found}"


@needs_tree
def test_the_public_tree_has_no_scratch_or_run_dirs():
    for name in ("scratch", "runs", "runs_in"):
        assert not (TREE / name).exists(), f"公开树里有 {name}/"


@needs_tree
def test_the_public_tree_readme_warns_on_the_first_screen():
    """外部用户**必须知道「答案在包里」** —— 任务书第 5 条。"""
    s = (TREE / "README.md").read_text(encoding="utf-8")
    head = s[:6000]
    assert "答案就在这个包里" in head, "警示不在首屏"
    assert "训练语料" in head, "没说清跨期比较的风险"
    assert "memory_probe_answers" in head, "没说清钥匙不在包里"


@needs_tree
def test_the_excluded_file_names_only_the_four_classes():
    s = (TREE / "EXCLUDED.txt").read_text(encoding="utf-8")
    for k in ("私有通道数据", "凭据", "记忆探针钥匙", "scratch 与 run 目录"):
        assert k in s, f"EXCLUDED.txt 没写 {k}"
    assert "带全部答案面" in s


@needs_tree
def test_the_scoring_evidence_shows_zero_broken_imports():
    """上一轮那个「65 个模块 import 断链」必须**有数为证**地没有了。"""
    s = (_REPO / "ops/reports/g2_public_tree_scoring.md").read_text(encoding="utf-8")
    assert "断链 0 个" in s, "证据里没有「断链 0 个」这句话"
    assert "320 passed" in s or "passed" in s


@needs_tree
def test_the_container_evidence_has_one_green_and_two_reds():
    p = TREES / "scan_genebench_container.txt"
    assert p.is_file()
    s = p.read_text(encoding="utf-8")
    assert s.count("[红，符合预期]") == 2
    assert "[绿]" in s
    assert "**[绿 —— 门坏了]**" not in s


@needs_tree
def test_the_tree_scan_evidence_says_the_hits_are_expected():
    """树口径对这棵树必然大量命中。**那不是红**，而这件事必须写在证据里，
    否则下一个人看到 95 条命中会以为发布包漏了答案面。"""
    s = (TREES / "scan_genebench_tree.txt").read_text(encoding="utf-8")
    assert "不是红" in s
    assert "树口径命中" in s
