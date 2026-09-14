#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡 6.5：公开通道上的完整 M6 pass —— 接通链路那几处改动的红测。

这张卡改的是**通道会不会静默串**。串了的表现全都不是报错：

* 出集串了 → 拿公开 gold 覆盖私有答案面（N-287 同族）；
* 容器打的网关串了 → 报告头写着 public、数字来自 private（N-304 同族）；
* 结算的题集根 / 日志串了 → 拿私有 gold 判公开产物、四个日志族静默塌成 unobservable。

所以本文件的每一条都在钉「两条通道**分得开**」，而不是「跑得通」。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                     # noqa: E402
from ops import joblist as JL                      # noqa: E402
from ops import run_joblist as RJ                  # noqa: E402
from runner.c41 import runner_core as RC           # noqa: E402

MATRIX = _REPO / "ops" / "joblists" / "m6_public.yaml"
GW_ENV = RC.GATEWAY_ADDR_ENV


# ============================================================ 落点按通道分开

def test_两条通道的题集根与日志各是各的():
    assert RJ.answer_root("private") == cfg.GENEBENCH_ROOT / "reference" / "tasks" / "v1.0-smoke"
    # 多的那一层 `public/` 是必须的（N-276）：并列放会让 `sim_factory.task_dir` 命中两个出集。
    assert RJ.answer_root("public").parent.name == "public"
    assert RJ.answer_root("public") != RJ.answer_root("private")
    assert RJ.gateway_log("public").name == "gateway_access_public.jsonl"
    assert RJ.gateway_log("private").name == "gateway_access.jsonl"
    assert RJ.gateway_log("public") != RJ.gateway_log("private")


def test_三控与跑批的四个落点常量同源():
    """跑批侧与三控侧的落点必须逐字相同 —— 第二份手写的代价 N-304 量过（help 里少一层 public/）。"""
    from ops import run_controls as RCTL
    assert RJ.answer_root("public") == RCTL.PUBLIC_ANSWER_ROOT
    assert RJ.gateway_log("public") == RCTL.PUBLIC_GATEWAY_LOG
    assert RJ.answer_root("private") == RCTL.ANSWER_ROOT
    assert RJ.gateway_log("private") == RCTL.GATEWAY_LOG


def test_容器打的网关端口按通道取():
    assert RJ.gateway_addr("private") == f"{cfg.GATEWAY_HOST}:{cfg.GATEWAY_PORT}"
    assert RJ.gateway_addr("public") == f"{cfg.GATEWAY_HOST}:{cfg.GATEWAY_PUBLIC_PORT}"
    assert cfg.GATEWAY_PUBLIC_PORT != cfg.GATEWAY_PORT


# ============================================================ 混通道的门

def test_channel_与环境变量不一致时拒绝启动(monkeypatch):
    monkeypatch.setenv("GENEBENCH_CHANNEL", "private")
    with pytest.raises(SystemExit) as e:
        RJ.assert_channel("public")
    assert "不一致" in str(e.value)
    monkeypatch.setenv("GENEBENCH_CHANNEL", "public")
    assert RJ.assert_channel("public") == "public"


def test_未知通道名当场拒(monkeypatch):
    monkeypatch.setenv("GENEBENCH_CHANNEL", "private")
    with pytest.raises(SystemExit):
        RJ.assert_channel("publik")


def test_私有通道下前置探针不碰执行面(monkeypatch):
    """`assert_public_plane_ready` 在私有通道上必须**一个 ssh 都不发** ——
    否则私有跑批平白多两次跨机往返，且 f02 掉线时私有批会跟着红。"""
    def _boom(*a, **k):                                        # noqa: ANN001
        raise AssertionError("私有通道不该发 ssh")
    monkeypatch.setattr(RJ, "_sh", _boom)
    assert RJ.assert_public_plane_ready("private") == {"channel": "private", "checked": False}


# ============================================================ f02 那一条命令

def _cmd(channel: str, override: dict | None = None) -> str:
    """`m6_public` 那一行今天的样子：`budget_override` 是**空的**（N-388 之后 18 行都清空了），
    于是命令里一个预算参数都不给，注入器按 `stage` 取档。`override` 只给「显式覆盖仍然传得下去」
    那条反向断言用。"""
    job = {"batch": "m6_public", "task_id": "s1-cor-01", "config_id": "cfg-codex-deepseek",
           "arm": "strict", "seed": 1, "timeout_s": 1800, "stage": "S1",
           "budget_override": dict(override or {})}
    return RJ.f02_run_cmd(job, channel)[-1]


def test_公开通道才给容器换网关地址():
    pub, pri = _cmd("public"), _cmd("private")
    assert f"export {GW_ENV}={cfg.GATEWAY_HOST}:{cfg.GATEWAY_PUBLIC_PORT};" in pub
    assert GW_ENV not in pri
    # 除了**通道相关的那几段**，两条命令逐字相同 —— 通道不该顺手改别的东西。
    # （N-611 之后通道**必须**送到 f02：`export GENEBENCH_CHANNEL=` 与 `--channel ` 两处。
    #  此前这条命令一个字都没提通道，f02 上于是两头回落到 private —— provider 默认是私有
    #  那份、P2 的期望值也是私有那个，**两头一致所以全绿**，而公开通道的 18 个 run
    #  喂给容器的是私有 provider 树。所以「逐字相同」的判据要放过这两段，不能放过别的。）
    def _strip(cmd: str, ch: str) -> str:
        return (cmd.replace(f"export {GW_ENV}={cfg.GATEWAY_HOST}:{cfg.GATEWAY_PUBLIC_PORT}; ", "")
                   .replace(f"export {cfg.CHANNEL_ENV}={ch}; ", "")
                   .replace(f"--channel {ch} ", ""))
    assert _strip(pub, "public") == _strip(pri, "private")
    # 通道那两段本身**必须在**（否则上面的 _strip 会把这条断言变成恒绿）
    for ch, cmd in (("public", pub), ("private", pri)):
        assert f"export {cfg.CHANNEL_ENV}={ch};" in cmd and f"--channel {ch} " in cmd


def test_预算参数一个都不传_让注入器按_stage_取档():
    """N-388（2026-09-10）之后 `m6_public` 的 18 行 `budget_override` 全部清空，
    于是 `f02_run_cmd` 一个预算参数都不传 —— 不传 = 注入器按 `stage` 取档
    （默认 100 次 / 6M、S4 150 / 9M、S7 300 / 18M）。

    原断言要求命令里出现 `--max-tokens 3000000`，那是默认档只有 600k 时文档化的绕法；
    清单清空之后它一直红（`KeyError: max_tokens`）。"""
    pub = _cmd("public")
    assert "--max-tokens" not in pub, "显式给 --max-tokens 会逐键压过 stage 档位（N-388）"
    assert "--max-calls" not in pub          # 不写 = 让注入器按 stage 取档（S4 150 / S7 300）
    # **反向判别力**：清单里真写了覆盖时，它必须仍然传得下去 —— 否则上面两条恒绿。
    ov = _cmd("public", {"max_tokens": 3_000_000})
    assert "--max-tokens 3000000" in ov


def test_结算按通道给题集根与日志():
    pub, pri = RJ.score_cmd("m6_public", "public"), RJ.score_cmd("m6_public", "private")
    assert "--ref-tasks" in pub and str(RJ.answer_root("public")) in pub
    assert "--gateway-log" in pub and str(RJ.gateway_log("public")) in pub
    assert str(RJ.answer_root("private")) in pri
    # 两层 runs —— 少一层 `score_runs.py` 退 0 并打印「runs: 0」，不报错的错（HANDOFF 14.4 §1）
    assert pub[pub.index("--remote") + 1].endswith("/runs/runs")


def test_私有那条结算命令与score_runs的默认值一致():
    """私有通道显式传的两个值必须**等于**`score_runs.py` 自己的默认值 ——
    不等的话「不传」与「传了」会得到两份不同的结算，而两处都不会红。"""
    from ops import score_runs as SRN
    pri = RJ.score_cmd("x", "private")
    assert pri[pri.index("--ref-tasks") + 1] == str(SRN.REF_TASKS)
    ap_default = "/data/shared/genebench/logs/gateway_access.jsonl"
    assert pri[pri.index("--gateway-log") + 1] == ap_default


# ============================================================ 注入器给容器的网关地址

def test_不设环境变量时地址逐字不变(monkeypatch):
    monkeypatch.delenv(GW_ENV, raising=False)
    assert RC.gateway_addr() == "192.168.1.48:18080" == RC.GATEWAY_DEFAULT
    assert RC.GATEWAY == RC.GATEWAY_DEFAULT          # PEP 562：属性仍在，只是现算


def test_环境变量能把上游换到公开网关(monkeypatch):
    monkeypatch.setenv(GW_ENV, "192.168.1.48:18081")
    assert RC.GATEWAY == "192.168.1.48:18081"


@pytest.mark.parametrize("bad", ["nope", "gateway:18081", "192.168.1.48", "192.168.1.48:0",
                                 "192.168.1.48:70000", "999.1.1.1:18081", "0.0.0.0:18081",
                                 "127.0.0.1:18081", "localhost:18081"])
def test_地址形状不对当场抛而不是静默回落(monkeypatch, bad):
    """静默回落的表现是「以为在跑公开通道，其实打的是私有网关」—— 正是要拦的那件事。"""
    monkeypatch.setenv(GW_ENV, bad)
    with pytest.raises(ValueError):
        RC.gateway_addr()


def test_compose_里换的是上游而不是容器里那个端口(monkeypatch):
    """边车的 `--gateway` 是**上游**；容器里的 `GENEBENCH_GATEWAY` 是**边车自己的监听端口**。
    把后者跟着改动的话，任务容器会去连一个没人听的端口，而边车照常起着。"""
    monkeypatch.setenv(GW_ENV, "192.168.1.48:18081")
    text = RC.render_compose("s1-cor-01", "strict")
    assert "--gateway 192.168.1.48:18081" in text
    assert 'GENEBENCH_GATEWAY: "http://gateway:18080"' in text
    monkeypatch.delenv(GW_ENV, raising=False)
    text2 = RC.render_compose("s1-cor-01", "strict")
    assert "--gateway 192.168.1.48:18080" in text2
    assert 'GENEBENCH_GATEWAY: "http://gateway:18080"' in text2


# ============================================================ 公开出集不重建答案面

def test_公开出集读的是答案面而不是重建它():
    """`export_from_answer_plane` 的源码里**不许**出现 `build_task` / `write_task`。

    这不是风格问题：`export_bundle.export_one` 的落点是 `$GB/reference/tasks/<set_id>/`，
    而 `set_id` 在冻结根里（两条通道同为 `v1.0-smoke`）——在公开通道上调它
    等于拿公开 gold 覆盖私有答案面（N-287 那次污染的同族形态）。
    """
    # 查**字节码里的名字**而不是源码文本：docstring 与报错文案里正说着这件事
    # （「非默认臂要在 build_task 那一步点名」），按文本查会把说明当成调用。
    names = set(RJ.export_from_answer_plane.__code__.co_names)
    assert not names & {"build_task", "write_task", "export_one"}, sorted(names)
    assert {"export_task", "export_manifest", "pin_image_digest", "check_export"} <= names


def test_答案面里没有这道题时说清怎么建(tmp_path):
    with pytest.raises(RJ.RunJoblistError) as e:
        RJ.export_from_answer_plane("s1-cor-01", tmp_path / "stage", "sha256:" + "0" * 64,
                                    answer_root=tmp_path / "nowhere")
    assert "run_oracles" in str(e.value)                # 报错里带着「怎么把它建出来」


def test_答案面没渲染的臂出不了集(tmp_path):
    import yaml
    td = tmp_path / "ans" / "s1-cor-01"
    td.mkdir(parents=True)
    (td / "task.yaml").write_text(yaml.safe_dump({"task_id": "s1-cor-01",
                                                  "instruction": {"open": "x"}}), encoding="utf-8")
    with pytest.raises(RJ.RunJoblistError) as e:
        RJ.export_from_answer_plane("s1-cor-01", tmp_path / "stage", "sha256:" + "0" * 64,
                                    answer_root=tmp_path / "ans", want_arms=("strict", "open"))
    assert "strict" in str(e.value)


# ============================================================ 矩阵

def test_矩阵摊平成十八个job():
    jobs = JL.gen(JL.load_matrix(MATRIX))
    assert len(jobs) == 18
    assert len({j["task_id"] for j in jobs}) == 9
    assert {j["arm"] for j in jobs} == {"strict", "open"}
    assert {j["seed"] for j in jobs} == {1}
    assert len({j["job_id"] for j in jobs}) == 18


def test_矩阵覆盖八个阶段外加一道探针题():
    jobs = JL.gen(JL.load_matrix(MATRIX))
    stages = {j["stage"] for j in jobs}
    assert stages == {f"S{i}" for i in range(1, 9)}
    assert "s7-rob-02" in {j["task_id"] for j in jobs}


def test_矩阵两行预算都不写_档位原样生效():
    """`max_calls` / `max_tokens` 两行都不写 = 让注入器按 stage 取档（S4 150 / S7 300）；
    写上任何一个都等于把那一维的档位关掉。

    2026-09-10 之前这里断言矩阵写着 `max_tokens: 3000000`（默认档只有 600k 时的绕法）——
    N-388 抬档之后那一行按裁定清掉了，断言跟着翻（`KeyError: max_tokens` 一直红）。"""
    from runner import registry as REG
    m = JL.load_matrix(MATRIX)
    assert m.get("max_calls") is None
    assert m.get("max_tokens") is None, "矩阵写死 max_tokens 会逐键压过 stage 档位（N-388）"
    by = {j["task_id"]: j for j in JL.gen(m)}
    assert by["s4-cor-01"]["budget"]["max_calls"] == 150
    assert by["s7-cor-01"]["budget"]["max_calls"] == 300
    assert by["s7-rob-02"]["budget"]["max_calls"] == 300
    assert by["s1-cor-01"]["budget"]["max_calls"] == 100
    assert by["s1-cor-01"]["budget"]["max_tokens"] == REG.RUN_BUDGET["max_tokens"]
    assert by["s4-cor-01"]["budget"]["max_tokens"] == REG.BUDGET_TIERS["S4"]["max_tokens"]
    assert by["s7-cor-01"]["budget"]["max_tokens"] == REG.BUDGET_TIERS["S7"]["max_tokens"]


def test_矩阵的九道题在公开答案面里都在():
    for t in JL.load_matrix(MATRIX)["tasks"]:
        assert (RJ.answer_root("public") / t / "task.yaml").is_file(), t


def test_干预臂写在前面():
    """出集把 `arm_ids[0]` 当干预臂写进等价表；写反了会得到一张 open vs open 的全绿空表（N-364）。"""
    from genetask import bundle as GB
    arms = JL.check_arms(JL.load_matrix(MATRIX)["arms"])
    assert arms[0] != GB.BASELINE_ARM and GB.BASELINE_ARM in arms


# ============================================================ 就绪报告的已知限制表

def test_已知限制表从裁定文件现读():
    from ops import readiness_report as RR
    lines, stat = RR.known_limits_rows()
    assert stat["n"] >= 10
    body = "\n".join(lines)
    assert str(RR.KNOWN_LIMITS.relative_to(_REPO)) in body
    # `s2-eco-01` 那条在裁定文件里的编号是 **N-279**（就绪报告原来那张手抄表用的是题号）。
    for num in ("N-126", "N-127", "N-128", "N-279", "N-103", "N-120"):
        assert f"| {num} " in body, num
    assert "s2-eco-01" in body          # 题号出现在 N-279 那一行的正文里


def test_那四条已关的限制不再被写成未解():
    """卡 5.2 关掉了 N-126（改判设计性）/ N-127 / N-128（题面与 schema 部分）/ s2-eco-01（N-279）。

    生成器里原来手抄了一张写死的表，四条都还写着「出不来 / 没写 / 被 422」——
    报告照常渲染、`known_limits_v1.md` 与它并存且互相打架，**没有任何东西会红**。
    """
    from ops import readiness_report as RR
    rows = {r[0]: r for r in RR._md_table(RR.KNOWN_LIMITS.read_text(encoding="utf-8"), "## 逐条")
            if len(r) == 4}
    for num in ("N-127", "N-128", "N-279", "N-120", "N-103"):
        assert "已修" in rows[num][2], (num, rows[num][2])
    assert "设计性" in rows["N-126"][2]


def test_生成器里不再留第二份手抄的限制表():
    src = (_REPO / "ops" / "readiness_report.py").read_text(encoding="utf-8")
    assert "S6 的 **TE**（跟踪误差）出不来" not in src
    assert "`/bars?universe=` 被网关 422" not in src
    assert "*_kl_lines" in src


# ============================================================ 通道纪律（回归护栏）

def test_没有人在import期把进程翻到另一条通道():
    """N-260：`os.environ.setdefault("GENEBENCH_CHANNEL", …)` 写在模块顶上的话，
    **任何 import 它的进程整个翻到那条通道**，而两个模块各自单跑都绿。"""
    code = ("import os, sys; sys.path.insert(0, %r);"
            "import ops.run_joblist, ops.readiness_report, runner.c41.runner_core;"
            "print(os.environ.get('GENEBENCH_CHANNEL', '<unset>'))") % str(_REPO)
    r = subprocess.run([sys.executable, "-c", code], cwd=str(_REPO),
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-800:]
    assert r.stdout.strip() == "<unset>"
