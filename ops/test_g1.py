#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 G1（N-611）：`--provider-root` 在真跑路径上被静默忽略 + 结果侧的 provider 门。

这三件事各自独立坏过，所以各自有一条红测试：

1. **参数被吞**。`ops/run_f02_a1.py` 真跑那条路径读模块常量 `PROVIDER`（写死私有
   provider 的绝对路径），`main()` 的 `global` 又漏了它 —— 于是 `--provider-root`
   只有 `--dry` 用得上。表现不是报错，是**公开通道的 run 喂给容器私有 provider 树**。
2. **通道没送到 f02**。`ops/run_joblist.f02_run_cmd` 拼的那条 ssh 命令里一个字都没提通道，
   f02 上于是两头都回落到 private：provider 默认是私有那份、P2 的期望值也是私有那个 ——
   **两头一致所以全绿**。
3. **P2 查的是输入，不是结果**。只要「传进来的」与「装进 work/ 的」是同一个错的东西，
   P2 永远绿。`runner.inject.check_work_provider`（P7e）站在 `work/` 这一侧补这一刀。

**判别法**（与 2026-09-11 实测证据同一套）：私有 provider 的 `features/` 下有 336 个
`bj*`（北交所）代码，公开 provider 只有沪深（3575 个，`bj*` 为 0）。
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import genebench_config as cfg                               # noqa: E402
from genetask import pin                                     # noqa: E402
from ops import run_f02_a1 as A1                             # noqa: E402
from ops import run_joblist as JL                            # noqa: E402
from runner import inject as INJ                             # noqa: E402
from runner import provider_adapter as PA                    # noqa: E402

PRIVATE_PROVIDER = cfg.SNAPSHOTS_V1 / "qlib_provider"
PUBLIC_PROVIDER = cfg.PUBLIC_PROVIDER_DIR


# ── ① provider 的默认值按通道走，且两条通道不可能指到对方那棵树 ────────────────
def test_provider_default_is_per_channel_and_derived_from_the_pin_table():
    priv, pub = A1.provider_default("private"), A1.provider_default("public")
    assert priv != pub, "两条通道的 provider 默认根相同 —— 那正是 N-611 的形态"
    assert priv.name == f"qlib_provider_{INJ.provider_pin_expect('private')[:8]}"
    assert pub.name == f"qlib_provider_{INJ.provider_pin_expect('public')[:8]}"
    assert priv.parent == pub.parent == A1.RUNNER_PROVIDER_ROOT


def test_unknown_channel_raises_instead_of_falling_back_to_private():
    with pytest.raises(Exception) as e:
        A1.provider_default("pubic")
    assert "不认识的通道" in str(e.value)


# ── ② `--provider-root` 在**真跑**路径上真的生效（N-611 的回归）────────────────
def _fake_manifest(tmp_path: Path) -> Path:
    m = {"task_id": "s1-cor-01", "frozen_manifest": {"root": "deadbeef" * 8}}
    p = tmp_path / "s1-cor-01.manifest.json"
    p.write_text(json.dumps(m), encoding="utf-8")
    return p


def _run_main(tmp_path, monkeypatch, argv: list[str]) -> dict:
    """跑一次 `main()`，把 `run_loop.run_once` 收到的关键字截下来。"""
    seen: dict = {}

    class _Res:
        run_id, run_dir, exit_code, elapsed_s = "rid", str(tmp_path / "nope"), 0, 1.0

    def fake_run_once(bundle, arm, **kw):
        seen.update(kw)
        seen["arm"] = arm
        return _Res()

    monkeypatch.setattr(A1.RL, "run_once", fake_run_once)
    monkeypatch.setattr(A1, "load_key", lambda: None)      # 不碰 secrets.env
    monkeypatch.setattr(A1.HC, "command_for", lambda h: 'sh -c "true"')
    # **先 setenv 再 delenv**，不要只 delenv：`main()` 会把通道**写进本进程环境**，
    # 而 `monkeypatch.delenv(..., raising=False)` 对一个本来就不存在的变量是空操作 ——
    # 它不记录任何状态，于是 teardown 也不会把 `main()` 写进去的那个值撤掉。
    # 后果实测过：`GENEBENCH_CHANNEL` 泄进整个 pytest 进程，
    # `ops/test_c65.py::test_没有人在import期把进程翻到另一条通道` 的子进程继承到它而误红。
    monkeypatch.setenv(INJ.CHANNEL_ENV, "private")   # 记下原状态（含「原本不存在」）
    monkeypatch.delenv(INJ.CHANNEL_ENV, raising=False)
    monkeypatch.setattr(sys, "argv", ["run_f02_a1.py"] + argv)
    assert A1.main() == 0
    return seen


def test_provider_root_flag_reaches_the_real_run(tmp_path, monkeypatch):
    """给了 `--provider-root` 就必须用它 —— 读模块常量的那一版在这里红。

    **落点必须在 `<执行面根>/provider` 下**（卡 F10 / N-855，2026-09-14）：真跑那条路径上
    `ops/run_f02_a1.assert_provider_same_source` 现在会拒掉别处的树 —— 探针
    （`ops/run_joblist.probe_f02_provider`）扫的就是那个父目录，读别处等于让探针替
    **另一棵树**担保，而两边都不报错（那正是 N-855）。
    **本条断言的内容一个字没变**：给了就必须用它，且拿到的不是模块常量 `A1.PROVIDER`；
    变的只是夹具的落点。目录不必真的存在 —— `run_once` 在这条测试里是假的。
    """
    want = A1.RUNNER_PROVIDER_ROOT / "qlib_provider_f10flag"
    seen = _run_main(tmp_path, monkeypatch, [
        "--bundle", str(tmp_path), "--manifest", str(_fake_manifest(tmp_path)),
        "--config-id", "cfg-codex-deepseek", "--arms", "strict",
        "--run-root", str(tmp_path / "runs"), "--results-dir", str(tmp_path / "res"),
        "--provider-root", str(want)])
    assert Path(seen["provider_root"]) == want, (
        f"真跑拿到的 provider 根是 {seen['provider_root']} —— `--provider-root` 又被吞了（N-611）")
    assert Path(seen["provider_root"]) != A1.PROVIDER


def test_without_the_flag_the_channel_picks_the_default(tmp_path, monkeypatch):
    for ch in ("private", "public"):
        seen = _run_main(tmp_path, monkeypatch, [
            "--bundle", str(tmp_path), "--manifest", str(_fake_manifest(tmp_path)),
            "--config-id", "cfg-codex-deepseek", "--arms", "strict", "--channel", ch,
            "--run-root", str(tmp_path / "runs"), "--results-dir", str(tmp_path / f"res_{ch}")])
        assert Path(seen["provider_root"]) == A1.provider_default(ch)
        # 通道也必须落进本进程环境 —— 注入器的 P2/P7e 从那里取
        assert os.environ[INJ.CHANNEL_ENV] == ch


# ── ③ 通道要送到 f02（此前那条 ssh 命令一个字都没提它）────────────────────────
def test_f02_command_carries_the_channel():
    job = {"batch": "m6_public", "task_id": "s1-cor-01", "config_id": "cfg-codex-deepseek",
           "arm": "strict", "seed": 1, "timeout_s": 1800}
    pub = JL.f02_run_cmd(job, "public")[-1]
    assert f"export {cfg.CHANNEL_ENV}=public;" in pub
    assert "--channel public" in pub
    pri = JL.f02_run_cmd(job, "private")[-1]
    assert f"export {cfg.CHANNEL_ENV}=private;" in pri
    assert "--channel private" in pri


# ── ④ P7e：结果侧的门，且**有牙** ──────────────────────────────────────────────
def _tiny_provider(root: Path, names: list[str]) -> str:
    """造一棵最小 provider 树（带 `files.sha256` 清单，`pin` 要它）。返回现算根。"""
    (root / "features").mkdir(parents=True)
    for n in names:
        d = root / "features" / n
        d.mkdir()
        (d / "close.day.bin").write_bytes(n.encode())
    (root / "calendars").mkdir()
    (root / "calendars" / "day.txt").write_text("2020-01-02\n", encoding="utf-8")
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "files.sha256":
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}")
    (root / "files.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return pin.provider_root_sha256(root)


def test_p7e_is_green_when_the_placed_tree_matches_the_channel(tmp_path, monkeypatch):
    work = tmp_path / "work"
    root = _tiny_provider(work / PA.WORK_PROVIDER_REL, ["sh600000", "sz000001"])
    monkeypatch.setattr(INJ, "provider_pin_by_channel",
                        lambda: {"private": "00" * 8, "public": root})
    assert INJ.check_work_provider(work, channel="public") == []


def test_p7e_reds_when_a_public_run_got_the_private_provider(tmp_path, monkeypatch):
    """「公开通道却装了私有 provider」必须当场红，并**点名装进去的是谁**。

    判别法与 2026-09-11 的实测证据同一套：私有那棵树里有 `bj*`（北交所）代码。
    """
    work = tmp_path / "work"
    placed = work / PA.WORK_PROVIDER_REL
    private_root = _tiny_provider(placed, ["sh600000", "sz000001", "bj832317", "bj920000"])
    public_root = _tiny_provider(tmp_path / "public_src", ["sh600000", "sz000001"])
    assert private_root != public_root
    monkeypatch.setattr(INJ, "provider_pin_by_channel",
                        lambda: {"private": private_root, "public": public_root})

    problems = INJ.check_work_provider(work, channel="public")
    assert problems, "公开通道装了私有 provider 而 P7e 绿 —— 这道门没有牙（N-611）"
    msg = "\n".join(problems)
    assert "P7e" in msg and "private" in msg, f"报错没点名装进去的是哪条通道：{msg}"
    # 同一棵树在 private 通道上是对的 —— 门认的是「通道 × 树」，不是「树本身好不好」
    assert INJ.check_work_provider(work, channel="private") == []
    # 实测证据的那一条：装进去的树里有 bj*，公开 provider 里没有
    assert list((placed / "features").glob("bj*")), "造错了：私有那棵树该有 bj* 代码"


def test_p7e_reds_when_provider_did_not_get_placed(tmp_path):
    problems = INJ.check_work_provider(tmp_path / "work", channel="private")
    assert problems and "不存在" in problems[0]


def test_p7e_is_wired_into_inject_and_recorded_in_inject_json():
    """门要**接在注入器里**，而且 `inject.json` 要记下这次用的是哪条通道的哪份 provider。"""
    src = (REPO / "runner" / "inject.py").read_text(encoding="utf-8")
    assert 'gate("P7e", check_work_provider(' in src, "P7e 没接进 inject()"
    assert '"provider": provider_rec,' in src, "inject.json 没记 provider 身份"
    i_place = src.index("PA.place_for_arm")
    i_gate = src.index('gate("P7e"')
    assert i_place < i_gate, "P7e 必须在 place_for_arm 之后 —— 它查的是结果"


# ── ⑤ 盘上两份冻结 provider 的判别法（证据的来源，不是构造）────────────────────
@pytest.mark.skipif(not (PRIVATE_PROVIDER / "features").is_dir()
                    or not (PUBLIC_PROVIDER / "features").is_dir(),
                    reason="f01 上没有这两份冻结 provider")
def test_the_two_frozen_providers_are_told_apart_by_bj_codes():
    pub = sorted(p.name for p in (PUBLIC_PROVIDER / "features").glob("bj*"))
    pri = sorted(p.name for p in (PRIVATE_PROVIDER / "features").glob("bj*"))
    assert pub == [], f"公开 provider 里出现了北交所代码 {pub[:5]} —— 公开集只有沪深"
    assert pri, "私有 provider 里没有 bj* —— 那条判别法不再成立，报告里的证据要改写"
