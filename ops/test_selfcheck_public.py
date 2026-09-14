"""`ops/selfcheck_public.py` 的定向测试（卡 C2，2026-09-13）。

这一份**只测判断逻辑**，不起网关、不碰 docker、不下附件 ——
真跑的证据另在（f01 干净 clone 一次「什么都还没做」、一次「全就位」，见提交信息）。

判断逻辑里真正容易写错、也真正会骗人的是这三处，逐处钉住：

1. **`--check-all` 的输出怎么读。** 「公开轴漂了、差异全部落在 `channel_fixtures/`」
   要报「登记在案」；**差异里混进别的东西就必须报红** —— 否则这一项会变成恒绿。
2. **Docker 内存那条线画在哪。** Docker Desktop 的 UI 写「16 GB」时引擎自报
   `MemTotal` 是 16,748,077,056 B ≈ 15.6 GiB。门画在 16 GiB 会把照做的人判红，
   画在 15 GiB 才对；同时必须挡住默认的 8 GB。
3. **状态到退出码的映射。** 只有「红」退非零；`--strict` 下「跳过 / 登记在案」也算不通过。

跑法（不依赖 `/data`、不依赖网络）::

    python3 -m pytest ops/test_selfcheck_public.py -q
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "_gb_selfcheck_public", _REPO_ROOT / "ops" / "selfcheck_public.py")
assert _SPEC and _SPEC.loader
SC = importlib.util.module_from_spec(_SPEC)
sys.modules["_gb_selfcheck_public"] = SC
_SPEC.loader.exec_module(SC)


# --------------------------------------------------------------------------- #
# ① `--check-all` 输出的解析与分类
# --------------------------------------------------------------------------- #
三条轴全绿 = """\
[一致] 任务集（private）：清单记 1.0.16 / 现算 1.0.16
        根 现算 d9eb…
[一致] 任务集（public）：清单记 p1.0.0 / 现算 p1.0.0
        根 现算 3e5a…
[一致] 参考面：清单记 r1.0.23 / 现算 r1.0.23
"""

公开轴只差夹具 = """\
1 条轴漂了 —— 重冻的命令：--write / --write-public / --write-reference
[一致] 任务集（private）：清单记 1.0.16 / 现算 1.0.16
[**漂了**] 任务集（public）：清单记 p1.0.0 / 现算 p1.0.0
        根 现算 c563…
        根 清单 3e5a…  ← 不等
        差异 channel_fixtures/s4-cor-01
        差异 channel_fixtures/s7-rob-02
[一致] 参考面：清单记 r1.0.23 / 现算 r1.0.23
"""

公开轴还差别的 = 公开轴只差夹具.replace(
    "        差异 channel_fixtures/s7-rob-02\n",
    "        差异 channel_fixtures/s7-rob-02\n        差异 templates/s1_cor.yaml\n")

参考面漂了 = """\
[一致] 任务集（private）：清单记 1.0.16 / 现算 1.0.16
[一致] 任务集（public）：清单记 p1.0.0 / 现算 p1.0.0
[**漂了**] 参考面：清单记 r1.0.23 / 现算 r1.0.23
        差异 solve.py
"""


def test_解析能把三条轴与各自的差异分开():
    axes = SC._parse_freeze(公开轴只差夹具)
    assert set(axes) == set(SC.FREEZE_AXES)
    assert axes["任务集（private）"]["drifted"] is False
    assert axes["任务集（public）"]["drifted"] is True
    assert axes["参考面"]["drifted"] is False
    # 差异必须落到**它自己那条轴**上，不能全堆在最后一条
    assert axes["任务集（public）"]["diffs"] == [
        "channel_fixtures/s4-cor-01", "channel_fixtures/s7-rob-02"]
    assert axes["参考面"]["diffs"] == []


@pytest.fixture()
def classify(tmp_path: Path):
    """把一段 `--check-all` 输出喂给 check_freeze 的分类逻辑，拿回状态。

    `check_freeze` 会先确认 `ops/freeze_v10.py` 在不在（不在就直接红，那是对的），
    所以这里借一棵临时树顶上，只让**分类**这一段接受检验。
    """
    (tmp_path / "ops").mkdir()
    (tmp_path / "ops" / "freeze_v10.py").write_text("", encoding="utf-8")
    real_root, real_run = SC.REPO_ROOT, SC._run_in_repo
    SC.REPO_ROOT = tmp_path

    def _go(text: str, rc: int = 1) -> str:
        SC._run_in_repo = lambda cmd, env, timeout=60: (rc, text, "")
        return SC.check_freeze().status

    yield _go
    SC.REPO_ROOT, SC._run_in_repo = real_root, real_run


def test_三条轴全一致报绿(classify):
    assert classify(三条轴全绿, rc=0) == SC.GREEN


def test_公开轴只差夹具报登记在案而不是红(classify):
    """已知发布缺件 —— 判红会让外部用户以为是自己下坏了。"""
    assert classify(公开轴只差夹具) == SC.KNOWN


def test_公开轴差异混进别的东西就必须红(classify):
    """这一条是防「恒绿」的那一根钉子：`channel_fixtures/` 之外的差异不许被放过。"""
    assert classify(公开轴还差别的) == SC.RED


def test_参考面漂了必须红(classify):
    """参考面轴与 private 轴没有任何已知缺件，漂了就是漂了。"""
    assert classify(参考面漂了) == SC.RED


def test_没有freeze脚本就红(tmp_path: Path):
    real = SC.REPO_ROOT
    SC.REPO_ROOT = tmp_path
    try:
        assert SC.check_freeze().status == SC.RED
    finally:
        SC.REPO_ROOT = real


# --------------------------------------------------------------------------- #
# ② Docker 内存那条线
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("mem_bytes", "该不该过", "说明"), [
    (16_748_077_056, True, "Docker Desktop UI 设 16 GB 时引擎自报的实测值（≈15.6 GiB）"),
    (17_179_869_184, True, "整 16 GiB"),
    (8_485_076_992, False, "Docker Desktop 默认 8 GB 档的量级"),
    (15 * 1024 ** 3, True, "正好压线"),
    (15 * 1024 ** 3 - 1, False, "压线下一个字节"),
])
def test_docker内存门画在正确的位置(mem_bytes: int, 该不该过: bool, 说明: str):
    assert (mem_bytes >= SC.DOCKER_MEM_FLOOR) is 该不该过, 说明


def test_只当数据面时不查docker():
    """手册 §1.2：纯数据面那台不需要 docker。这时报「跳过」，不该把人判红。"""
    assert SC.check_docker("data").status == SC.SKIP


# --------------------------------------------------------------------------- #
# ③ 状态 → 退出码
# --------------------------------------------------------------------------- #
def _exit_code(statuses: list[str], strict: bool) -> int:
    items = []
    for i, st in enumerate(statuses):
        it = SC.Item(f"i{i}", f"第 {i} 项")
        it.set(st, "")
        items.append(it)
    real = SC.run_all
    SC.run_all = lambda args: items
    try:
        argv = ["--strict"] if strict else []
        return SC.main(argv)
    finally:
        SC.run_all = real


@pytest.mark.parametrize(("statuses", "strict", "want"), [
    ([SC.GREEN] * 6, False, 0),
    ([SC.GREEN] * 6, True, 0),
    ([SC.GREEN, SC.SKIP, SC.KNOWN, SC.GREEN, SC.GREEN, SC.GREEN], False, 0),
    ([SC.GREEN, SC.SKIP, SC.KNOWN, SC.GREEN, SC.GREEN, SC.GREEN], True, 1),
    ([SC.GREEN, SC.RED, SC.GREEN, SC.GREEN, SC.GREEN, SC.GREEN], False, 1),
    ([SC.GREEN, SC.RED, SC.GREEN, SC.GREEN, SC.GREEN, SC.GREEN], True, 1),
])
def test_退出码(statuses: list[str], strict: bool, want: int):
    assert _exit_code(statuses, strict) == want


def test_python版本门():
    it = SC.check_python()
    # 这份测试自己就跑在某个解释器上：跑得动 pytest 的解释器要么 ≥3.12 要么不是，
    # 两种情况下这一项的结论都必须和 sys.version_info 一致，不许两边都说得通。
    assert (it.status == SC.GREEN) is (sys.version_info[:2] >= SC.MIN_PY)


def test_六个包就是全部():
    """六个包这一行是演练里一个个试出来的，别人加减之前先在这里看见它。"""
    assert [n for n, _ in SC.SIX_PACKAGES] == [
        "fastapi", "uvicorn", "pandas", "pyarrow", "duckdb", "pyyaml"]
