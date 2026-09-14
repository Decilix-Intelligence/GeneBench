# -*- coding: utf-8 -*-
"""卡 1.1-c 的判据：跑批这四个脚本能不能**真的**跑在公开通道上，以及 N-120 那条视图。

这些测试盯的是四类「不报错的错」——它们全都长成「跑起来 ok」：

1. **端口写死**：`run_oracles` 原来把 `cfg.GATEWAY_PORT` 拼进 `GATEWAY_URL`，
   还用它**覆盖**子进程的 `GENEBENCH_GATEWAY_URL`。于是 `GENEBENCH_CHANNEL=public`
   跑出来的 oracle 全打在私有网关上：数字照出，只是来自另一份数据。
2. **日志写死**：切片读私有 `gateway_access.jsonl`，而公开网关写的是
   `gateway_access_public.jsonl`。切出来永远是空的，`check_log_evidence`
   会把它读成「oracle 一次网关都没请求过」。
3. **落点写死**：矩阵与题集目录都指向私有那一份，公开那一跑**就地覆盖**私有的产物，
   覆盖之后从内容上看不出是哪条通道跑的。
4. **视图没喂（N-120）**：`tradability=None` 时 `calendar` 与
   `missing_masquerading_as_signal` 两条检查**根本不会被调用**，而矩阵里它们显示为
   `·`（判过且零）。不可得与零长得一样 —— 这是 `None` / `[]` 那一族错误（红队 rt18）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                              # noqa: E402
from ops import run_controls as RC                          # noqa: E402
from ops import run_materiality_screen as MS                # noqa: E402
from ops import run_oracles as RO                           # noqa: E402
from ops import run_probe_mutations as RM                   # noqa: E402
from ops import validator_validation_report as VV           # noqa: E402

#: 改动前写死在源码里的那些字面量。**测试盯的是「默认值一个字节没动」**，
#: 所以这里抄的是改动前的原文，不是从模块里读出来的（读出来的话这条测试永远绿）。
BEFORE = {
    "gateway_url": "http://192.168.1.48:18080",
    "access_log": "/data/shared/genebench/logs/gateway_access.jsonl",
    "answer_root": "/data/shared/genebench/reference/tasks/v1.0-smoke",
    "reports_m6": str(_REPO / "ops" / "reports" / "m6"),
    "o1_dir": str(_REPO / "ops" / "reports"),
}


# ------------------------------------------------------------------ ① 端口
def test_gateway_url_follows_the_channel(monkeypatch):
    monkeypatch.delenv("GENEBENCH_GATEWAY_URL", raising=False)
    monkeypatch.delenv("GENEBENCH_CHANNEL", raising=False)
    assert RO.gateway_url() == BEFORE["gateway_url"], "私有通道的默认值必须与改动前逐字相同"
    monkeypatch.setenv("GENEBENCH_CHANNEL", "public")
    assert RO.gateway_url() == f"http://{cfg.GATEWAY_HOST}:{cfg.GATEWAY_PUBLIC_PORT}"
    assert RO.gateway_url() != BEFORE["gateway_url"], "公开通道不能还打在私有端口上"


def test_gateway_url_lets_the_deployment_env_win(monkeypatch):
    """`GENEBENCH_GATEWAY_URL` 是 `reference/oracle_io.py` 声明的**唯一**允许的环境变量。

    原来它会被 `run_one` 用写死的值覆盖掉 —— 设了也没用，而没有一处会说。
    """
    monkeypatch.setenv("GENEBENCH_CHANNEL", "public")
    monkeypatch.setenv("GENEBENCH_GATEWAY_URL", "http://10.0.0.9:1234")
    assert RO.gateway_url() == "http://10.0.0.9:1234"


def test_module_attribute_gateway_url_is_computed_not_frozen(monkeypatch):
    """`GATEWAY_URL` 仍是模块属性（既有调用方不用改），但**按通道现算**。"""
    monkeypatch.delenv("GENEBENCH_GATEWAY_URL", raising=False)
    monkeypatch.setenv("GENEBENCH_CHANNEL", "public")
    assert RO.GATEWAY_URL.endswith(f":{cfg.GATEWAY_PUBLIC_PORT}")
    assert "GATEWAY_URL" not in vars(RO), "写成模块常量的话它在 import 期就定死了"


# ------------------------------------------------------------------ ② 日志
def test_log_slice_reads_the_channel_log(monkeypatch, tmp_path):
    """两条通道的账本不能混：切片必须去读**本通道**那一份。"""
    assert str(cfg.gateway_access_log("private")) == BEFORE["access_log"]
    pub = cfg.gateway_access_log("public")
    assert pub != cfg.gateway_access_log("private")
    assert pub.name == "gateway_access_public.jsonl"

    fake = tmp_path / "gw.jsonl"
    fake.write_text(json.dumps({"task_id": "t1", "config_id": "oracle",
                                "ts": "2026-01-01T00:00:00+00:00", "decision": "allow",
                                "rows": 3}) + "\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "gateway_access_log", lambda ch=None: fake)
    assert len(RO.log_slice("t1")) == 1
    monkeypatch.setattr(cfg, "gateway_access_log", lambda ch=None: tmp_path / "nope.jsonl")
    assert RO.log_slice("t1") is None, "文件不存在 = 不可得（None），不是可得且零条（[]）"


def test_mutations_log_block_reads_the_channel_log(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "gateway_access_log", lambda ch=None: tmp_path / "nope.jsonl")
    assert RM.log_block("t1") is None


# ------------------------------------------------------------------ ③ 落点
def test_defaults_did_not_move():
    """公开通道是**并列**不是覆盖：私有那几个默认值一个字节都不许动。"""
    assert str(RC.ANSWER_ROOT) == BEFORE["answer_root"]
    assert str(RC.GATEWAY_LOG) == BEFORE["access_log"]
    assert str(RM.ANSWER_ROOT) == BEFORE["answer_root"]
    assert str(VV.REPORTS_DIR) == BEFORE["reports_m6"]
    assert str(VV.O1_DIR) == BEFORE["o1_dir"]


def test_relocate_moves_the_task_set_and_its_ledger(tmp_path):
    """`P.write_task` 的落点是 `<root>/tasks/<set_id>/`，而 `set_id` 在冻结根里。

    公开通道要一个**并列**的目录名（`v1.0-smoke-public`），只能落到暂存根再整体搬。
    搬的时候 `_ledger.jsonl` 必须跟着走 —— 留在暂存根里的话，公开那一批的台账行
    会在下一次跑批时**混进私有台账**（write_task 是 append）。
    """
    stage = tmp_path / ".stage-x"
    (stage / "tasks" / "v1.0-smoke" / "t1" / "solution").mkdir(parents=True)
    (stage / "tasks" / "v1.0-smoke" / "t1" / "solution" / "a.json").write_text("1")
    (stage / "tasks" / "v1.0-smoke" / "_ledger.jsonl").write_text('{"t":"t1"}\n')
    dest = tmp_path / "tasks" / "v1.0-smoke-public"
    out = RO._relocate({"t1": stage / "tasks" / "v1.0-smoke" / "t1"}, stage, dest)
    assert out["t1"] == dest / "t1"
    assert (dest / "t1" / "solution" / "a.json").read_text() == "1"
    assert (dest / "_ledger.jsonl").read_text() == '{"t":"t1"}\n'
    assert not stage.exists(), "暂存根必须删掉：留着的话同一道题在两个地方各有一份"


def test_relocate_keeps_the_fixtures_already_in_work(tmp_path):
    """**搬家不许删掉 `work/`。**

    题面 `inputs` 声明的夹具（S4 因子面板 / S5 输入清单 / S6·S7 信号）住在 `<task>/work/`，
    由 `reference/make_fixtures.py` 与 `reference/make_s7_signal.py` 物化，而唯一可行的顺序是
    「先跑一次 oracle 建题目录 → 物化夹具 → 再跑一次 oracle」。整目录替换会在第二次跑批时
    把夹具删干净 —— 2026-09-07 实测：S4/S5/S6/S7 十六道题一起 `FileNotFoundError`，
    而日志里看不出是谁删的。
    """
    stage = tmp_path / ".stage-x"
    src_task = stage / "tasks" / "v1.0-smoke" / "t1"
    (src_task / "solution").mkdir(parents=True)
    (src_task / "solution" / "solve.py").write_text("new")
    dest = tmp_path / "tasks" / "public" / "v1.0-smoke-public"
    (dest / "t1" / "work").mkdir(parents=True)
    (dest / "t1" / "work" / "factor_panel.parquet").write_text("夹具")
    (dest / "t1" / "solution" / "artifact.json").parent.mkdir(parents=True, exist_ok=True)
    (dest / "t1" / "solution" / "artifact.json").write_text("上一轮的产物")

    RO._relocate({"t1": src_task}, stage, dest)
    assert (dest / "t1" / "work" / "factor_panel.parquet").read_text() == "夹具"
    assert (dest / "t1" / "solution" / "solve.py").read_text() == "new"
    assert (dest / "t1" / "solution" / "artifact.json").is_file(), \
        "write_task 写进已存在目录时不会删产物，搬家这一步也不许删"


def test_set_name_may_carry_one_directory_level():
    """公开出集必须放在 `tasks/public/v1.0-smoke-public/`，不能直接放 `tasks/v1.0-smoke-public/`。

    `gateway/sim_factory.py::task_dir` 找 S8 会话是 `(reference/tasks).glob(f"*/{task_id}")`，
    命中两个就抛「在多个出集里都有 …… 不猜」。直接并列会让**私有生产网关**的 S8 四题一起 500 ——
    2026-09-07 实测踩到（公开出集一建出来，私有那条通道也跟着坏）。
    """
    import inspect
    src = inspect.getsource(RO.write_all)
    assert 'set_name.replace("/", "_")' in src, "暂存目录名里带斜杠会当场炸"
    from gateway import sim_factory as SF
    root = Path("/data/shared/genebench/reference/tasks")
    if (root / "public" / "v1.0-smoke-public" / "s8-cor-01" / "task.yaml").is_file():
        # **glob 已经没了**（N-578，2026-09-11）：`task_dir` 的 `set_id` 必填，
        # 公开出集因此连「落进射程」这件事都不成立了。判据改成更强的那条：
        # 给定 set_id 只会落到那个集里，公开那一份不会被拿来构造私有会话。
        assert SF.task_dir("s8-cor-01", "v1.0-smoke") == root / "v1.0-smoke" / "s8-cor-01"
        import pytest as _pt
        with _pt.raises(FileNotFoundError):
            SF.task_dir("s8-cor-01", "public")


def test_matrix_lands_next_to_the_detail_file():
    """矩阵与明细同目录。分开放的后果是公开那一跑**就地覆盖**私有的矩阵。

    **判据盯的是不变量（矩阵路径从 `out.parent` 算），不是某一行源码的字面。**
    原来这里比的是整行 `mat = out.parent / f"probe_matrix_{a.agent}.md"`；
    Y1b 给实例层加了第二个矩阵名（`probe_matrix_instances.md`）之后，
    那条字面断言当场红 —— 而它要守的东西（矩阵跟着 `--out` 走）一个字都没变。
    按字面比的断言拦不住真正的回归，却会拦住每一次正当的改动。
    """
    import inspect
    src = inspect.getsource(RO.main)
    assert "mat = out.parent / " in src, \
        "矩阵不跟着 --out 走的话，两条通道会互相覆盖对方的矩阵"
    assert 'f"probe_matrix_{a.agent}.md"' in src, "出集那张矩阵仍按 agent 命名"
    assert '"probe_matrix_instances.md"' in src, "实例层那张矩阵有自己的名字（Y1b）"


# ------------------------------------------------------------------ ④ N-120 视图
_TRAD_GATED = ("missing_rows_silently_filled", "missing_masquerading_as_signal")


def test_two_probes_are_silent_without_the_tradability_view():
    """**这条测试就是 N-120 本身**：不喂视图，这两条检查一次都不会被调用。

    夹具取自 `reference/artifact_samples.ILLEGAL`（红队手写的最小非法样例，各自带 `trad`）。
    喂了视图 → 命中；不喂 → **零 finding**。而矩阵里「零 finding」画的是 `·`，
    与「判过且干净」一模一样。
    """
    from reference import artifact_samples as AS
    from reference.artifact_schema import validate

    seen = set()
    for ill in AS.ILLEGAL:
        if ill.code not in _TRAD_GATED or ill.trad is None:
            continue
        seen.add(ill.code)
        with_view = validate(ill.artifact, task=ill.task, gateway_log=ill.log,
                             tradability=ill.trad, config_id=AS.CFG)
        without = validate(ill.artifact, task=ill.task, gateway_log=ill.log,
                           tradability=None, config_id=AS.CFG)
        assert ill.code in with_view.codes, f"{ill.name}：喂了视图也没命中"
        assert ill.code not in without.codes, (
            f"{ill.name}：不喂视图居然也命中了 —— 那这条测试就盯不住 N-120 了")
    assert seen == set(_TRAD_GATED), f"两族的夹具都要在：实得 {sorted(seen)}"


def test_families_gated_on_the_view_are_calendar_and_underdetermined():
    """点名是**哪两族**受视图门控 —— 族名换了这条会红，报告里的说法就得跟着改。"""
    from reference import artifact_samples as AS
    from reference.artifact_schema import validate

    fams = set()
    for ill in AS.ILLEGAL:
        if ill.code in _TRAD_GATED and ill.trad is not None:
            v = validate(ill.artifact, task=ill.task, gateway_log=ill.log,
                         tradability=ill.trad, config_id=AS.CFG)
            fams |= {f.probe for f in v.findings if f.probe}
    assert fams == {"calendar", "underdetermined"}, fams


def test_run_one_feeds_the_view_into_validate(monkeypatch, tmp_path):
    """跑批**真的**把视图传进 `sch.validate` —— 不是「有个函数能取到视图」。

    造一个最小题目录：`solve.py` 只负责写产物，校验器换成记账器。
    这样测的是 `run_one` 的接线，与 schema 的具体判据无关。
    """
    td = tmp_path / "t1"
    (td / "solution").mkdir(parents=True)
    (td / "solution" / "solve.py").write_text(
        "import json, os\n"
        "open(os.environ['GENEBENCH_ORACLE_OUT'], 'w').write(json.dumps({'ok': 1}))\n",
        encoding="utf-8")
    (td / "taskspec.json").write_text(json.dumps({"task_id": "t1"}), encoding="utf-8")
    (td / "task.yaml").write_text(yaml.safe_dump(
        {"task_id": "t1", "as_of": "2026-07-31",
         "window": {"start": "2026-07-01", "end": "2026-07-31"},
         "universe": "csi300", "payload_profile": "p"}), encoding="utf-8")

    view = {("2026-07-01", "SH600000"): "no_data"}
    monkeypatch.setattr(RO, "log_slice", lambda *a, **k: [])
    monkeypatch.setattr("ops.run_probe_mutations.trad_view", lambda task, **kw: view)

    seen: dict = {}

    class _V:
        findings: list = []

    def _validate(art, **kw):
        seen.update(kw)
        return _V()

    monkeypatch.setattr(RO.sch, "validate", _validate)
    res = RO.run_one(td, {"task_id": "t1", "stage": "S1", "template_id": "x"})
    assert res.rc == 0 and res.artifact is not None
    assert seen.get("tradability") == view, "视图没进 validate —— N-120 没接上"
    assert res.tradability_rows == 1

    seen.clear()
    res2 = RO.run_one(td, {"task_id": "t1", "stage": "S1", "template_id": "x"},
                      tradability=False)
    assert seen.get("tradability") is None and res2.tradability_rows is None


def test_view_failure_is_reported_not_swallowed(monkeypatch):
    """取不到视图 → `(None, 一句话)`。**不许**静静地退回 None：
    那样报告里那两族会显示成「判过且干净」，而它们一次都没被调用过。"""
    def _boom(task, **kw):
        raise RuntimeError("网关不通")

    monkeypatch.setattr("ops.run_probe_mutations.trad_view", _boom)
    view, note = RO.tradability_view({"task_id": "t1"})
    assert view is None
    assert "没被调用过" in note and "RuntimeError" in note


def test_view_is_taken_under_a_separate_config_id():
    """视图那几次 `/tradability` 不许记成 `oracle`。

    `run_controls.oracle_window` 与 `run_probe_mutations.log_block` 是按
    「间隔 > 2 分钟」切块取最后一块 —— 视图请求混进那一块的话，
    `declared_reads` 会看见几次题面没声明的读取：**取证动作把被取证的东西判红**。
    """
    import inspect
    assert RO.TRAD_VIEW_CONFIG_ID != RO.ORACLE_CONFIG_ID
    assert "config_id" in inspect.signature(RM.trad_view).parameters
    assert inspect.signature(RM.trad_view).parameters["config_id"].default == "oracle", \
        "破坏样本那一侧的默认身份不许动"
    assert "config_id=TRAD_VIEW_CONFIG_ID" in inspect.getsource(RO.tradability_view)


# ------------------------------------------------------------------ ⑤ 三控落点
def test_controls_gateway_log_reaches_score_run(monkeypatch, tmp_path):
    """`--gateway-log` 不是装饰：它必须一路到 `scorer.score_run`。"""
    td = tmp_path / "t1"
    (td / "solution").mkdir(parents=True)
    (td / "solution" / "artifact.json").write_text(json.dumps({"config_id": "oracle"}))
    (td / "task.yaml").write_text(yaml.safe_dump({"task_id": "t1"}), encoding="utf-8")
    seen: dict = {}

    def _score(rd, task_dir, out_dir=None, gateway_log_path=None):
        seen["log"] = gateway_log_path
        return {"record": {}}

    monkeypatch.setattr(RC.SR, "score_run", _score)
    monkeypatch.setattr(RC, "oracle_window", lambda tid: RC.WIDE)
    RC.score_control(td, "oracle", tmp_path / "s", tmp_path / "o",
                     gateway_log=Path("/tmp/x.jsonl"))
    assert seen["log"] == Path("/tmp/x.jsonl")
    seen.clear()
    RC.score_control(td, "oracle", tmp_path / "s2", tmp_path / "o")
    assert seen["log"] == RC.GATEWAY_LOG, "不传时必须回到私有那份（默认不变）"


# ------------------------------------------------------------------ ⑥ screen
def test_every_probe_field_is_either_screenable_or_registered():
    """**反僵尸**：题集里每一个探针字段，要么这套 harness 能screen，要么登记为「量不到」并写明理由。

    新加一道探针题却两边都没登记时，这条会红 —— 而不是让那道题静静地落进
    「跑了、没结论」的缝里。
    """
    from genetask import packager as P

    fields = {(r.get("underdetermined") or [None])[0]
              for r in P.load_params(str(MS.PARAMS)) if r.get("underdetermined")}
    fields.discard(None)
    known = set(MS.FROZEN_SCREENS) | set(MS.OUT_OF_REACH)
    assert fields <= known, f"没有登记的探针字段：{sorted(fields - known)}"
    assert not (set(MS.FROZEN_SCREENS) & set(MS.OUT_OF_REACH)), \
        "同一个字段不能既能screen 又量不到"


def test_out_of_reach_reasons_are_reasons():
    """「量不到」要写清是**为什么**量不到。一句「跑不起来」不算理由。"""
    for f, why in MS.OUT_OF_REACH.items():
        assert len(why) >= 20, f"{f} 的理由太短"
        assert "跑不起来" not in why


def test_frozen_impl_paths_points_and_restores(tmp_path):
    """覆盖表用完必须还原。留一个指向公开根的模块常量下去 =「公开 screen 读了私有快照」，
    两边都不报错。"""
    from ops import screen_band as sb
    from ops import screen_runner as sr

    before = (sr.SNAP, sr.PANEL, sb.CAL, {k: v["src"] for k, v in sr.SCRIPTS.items()})
    eps = cfg.epsilon_dir("public")
    with MS.frozen_impl_paths(eps):
        assert sr.SNAP == eps and sb.CAL == eps
        assert all(Path(v["src"]).parent == eps for v in sr.SCRIPTS.values())
    assert (sr.SNAP, sr.PANEL, sb.CAL) == before[:3]
    assert {k: v["src"] for k, v in sr.SCRIPTS.items()} == before[3]


def test_frozen_impl_paths_refuses_a_directory_without_the_impls(tmp_path):
    """缺件要**当场停**并点名缺哪一件 —— 不是跑到一半才在某个 impl 上炸。"""
    with pytest.raises(SystemExit) as e:
        with MS.frozen_impl_paths(tmp_path):
            pass
    assert "缺件" in str(e.value)


def test_public_screen_report_says_material_for_s6_and_s7():
    """本卡跑出来的公开通道 screen 结论：`s6-rob-02`（N-103）与 `s7-rob-02` 都 material。

    这条测试盯的是**产物**：报告没跑过、或者结论退回 inconclusive 时它会红。
    另六道题**必须**是 inconclusive —— 若哪天它们变成 material，说明有人给
    这套 harness 接了新的入口，那时这条也该跟着改（而不是悄悄地过）。
    """
    p = _REPO / "ops" / "reports" / "public" / "materiality_screen.json"
    if not p.is_file():
        pytest.skip("公开 screen 还没跑过")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["channel"] == "public"
    assert d["gates"]["baseline_reproduces"] is True
    assert d["gates"]["patch_neutral:P-SELL"] is True
    got = {t: v["verdict"] for t, v in d["tasks"].items()}
    assert got["s6-rob-02"] == "material" and got["s7-rob-02"] == "material"
    assert {t for t, v in got.items() if v == "material"} == {"s6-rob-02", "s7-rob-02"}


# ------------------------------------------------------------------ ⑦ 三控指向公开通道（红队 1.rt）

def test_public_answer_root_is_not_forked_into_a_second_literal():
    """`--help` 里那条公开题集路径**必须从常量渲染**，不许再手写一份。

    红队 2026-09-07 实测：help 里手写的是 `.../reference/tasks/v1.0-smoke-public`，
    **少了一层 `public/`，那个路径不存在**；而 `ops/reports/public/controls.md`
    的报告头写的是对的。照着 `--help` 抄命令直接失败，两处文档互相打架。
    这条盯的是「同一个事实只有一处定义」——源码里不许再出现少一层的那种写法。
    """
    import inspect
    text = inspect.getsource(RC)
    assert "tasks/public/v1.0-smoke-public" in str(RC.PUBLIC_ANSWER_ROOT)
    assert "tasks/v1.0-smoke-public" not in text.replace("tasks/public/v1.0-smoke-public", "")
    # help 文本由常量渲染：改常量，help 跟着变
    ap_help = _controls_help()
    assert str(RC.PUBLIC_ANSWER_ROOT) in ap_help.replace("\n", "").replace(" ", "")
    assert str(RC.PUBLIC_GATEWAY_LOG) in ap_help.replace("\n", "").replace(" ", "")


def _controls_help() -> str:
    """`run_controls.py --help` 的全文（不起子进程：直接让 argparse 渲染）。"""
    import argparse
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        RC.main(["--help"])
    return buf.getvalue()


@pytest.mark.parametrize("root,channel,refused", [
    (RC.PUBLIC_ANSWER_ROOT, "private", True),
    (RC.PUBLIC_ANSWER_ROOT, "public", False),
    (RC.ANSWER_ROOT, "private", False),
    (RC.ANSWER_ROOT, "public", False),
])
def test_mixed_channel_batch_is_refused(monkeypatch, root, channel, refused):
    """**公开题集 + 非公开通道 = 拒绝启动**。

    这一格此前没有任何判据拦：`cfg.channel()` 默认 private，只传 `--answer-root`
    与 `--gateway-log` 跑出来的是「题集与网关日志是公开的、底下读的表是私有的」，
    报告头照实打印 `通道：private`，三条判据照样全过 ——
    数字看起来都对，只是来自另一份数据（红队 2026-09-07）。
    """
    monkeypatch.setattr(RC._cfg, "channel", lambda: channel)
    if refused:
        with pytest.raises(SystemExit) as e:
            RC.assert_channel_matches(Path(root))
        msg = str(e.value)
        assert "拒绝启动" in msg and "GENEBENCH_CHANNEL=public" in msg
    else:
        RC.assert_channel_matches(Path(root))


def test_the_channel_guard_reads_the_path_not_the_disk(monkeypatch):
    """题集根**不存在**时也要判得出通道 —— 那正是最该拦的一次（路径抄错 + 通道没设）。"""
    monkeypatch.setattr(RC._cfg, "channel", lambda: "private")
    with pytest.raises(SystemExit):
        RC.assert_channel_matches(Path("/nowhere/reference/tasks/public/v1.0-smoke-public"))
    assert RC.looks_public(Path("/x/y/v1.0-smoke-public")) is True
    assert RC.looks_public(Path("/x/y/v1.0-smoke")) is False


def test_reproduce_command_carries_the_three_things_help_alone_does_not(monkeypatch):
    """报告顶部那条命令要能**照抄就跑**：题集 + 日志 + 通道 + 网关锁，一样都不能少。"""
    monkeypatch.setattr(RC._cfg, "channel", lambda: "public")
    cmd = RC.reproduce_command(RC.PUBLIC_ANSWER_ROOT, RC.PUBLIC_GATEWAY_LOG, Path("/tmp/out"))
    assert "GENEBENCH_CHANNEL=public" in cmd
    assert str(RC.PUBLIC_ANSWER_ROOT) in cmd and str(RC.PUBLIC_GATEWAY_LOG) in cmd
    assert "public_gateway.sh run --" in cmd, "红线 6：跑批要包在网关锁里"
    monkeypatch.setattr(RC._cfg, "channel", lambda: "private")
    cmd2 = RC.reproduce_command(RC.ANSWER_ROOT, RC.GATEWAY_LOG, Path("/tmp/out"))
    assert "GENEBENCH_CHANNEL=private" in cmd2 and "gateway_lock.py" in cmd2
