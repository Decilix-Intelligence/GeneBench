"""网关 systemd --user 单元的断言（裁定 2026-09-04）。

**读单元文件**，不读进程状态：进程可以是上一版单元起的，而单元文件才是下次重启的依据。
两条确认项 + 两条取证完整性项，每条都写在单元里、每条都在这里被读一遍。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

UNIT = Path(os.path.expanduser("~/.config/systemd/user/genebench-gateway.service"))
pytestmark = pytest.mark.skipif(not UNIT.is_file(),
                                reason=f"本机没有网关单元（它在 f01）：{UNIT}")


@pytest.fixture(scope="module")
def unit() -> str:
    return UNIT.read_text(encoding="utf-8")


def test_restart_on_failure(unit):
    """网关挂了要自己起来 —— 它是 M6 期间的常驻服务。"""
    assert "Restart=on-failure" in unit
    assert "RestartSec=" in unit


def test_backend_is_pinned_to_snapshot(unit):
    """**后端钉死 snapshot，不靠推断。**

    `default_backend()` 的默认是「manifest 在就 snapshot，否则 live」。
    benchmark 期落到 live 上意味着题目读的是当天的真实数据，
    而 as_of 冻结线、gold 与 ε 带全建立在快照之上 ——
    结果不可复现，且**没有人会收到提示**。
    """
    assert "Environment=GENEBENCH_GATEWAY_BACKEND=snapshot" in unit
    assert "GENEBENCH_GATEWAY_BACKEND=live" not in unit


def test_single_worker_is_a_forensic_requirement(unit):
    """单 worker 是**取证完整性**要求，不是性能取舍：access_log 用进程内锁，
    多 worker 会交错写坏行，而卡 5.1 的前视探针靠这份日志结算。"""
    assert "--workers 1" in unit
    assert "--workers 2" not in unit and "--workers 4" not in unit


def test_startup_guard_runs_before_the_gateway(unit):
    """守门在**使用时刻**：ExecStartPre 每次重启都跑，不合规拒绝启动。"""
    assert "ExecStartPre=" in unit and "guard_modes.py" in unit
    pre = [l for l in unit.splitlines() if l.startswith("ExecStartPre=")][0]
    assert not pre.startswith("ExecStartPre=-"), \
        "`-` 前缀会让守门失败也照常启动 —— 那等于没有守门"


def test_umask_keeps_systemd_created_logs_private(unit):
    """systemd 的 `append:` 用 umask 建文件，而本机 umask 是 002 ——
    不设 UMask 的话它会建出 0664 的日志，守门当场拦住网关自己（实测发生过）。"""
    assert "UMask=0077" in unit


def test_bind_is_the_lan_address_not_wildcard(unit):
    """绑定地址由 `cfg.assert_no_wildcard_bind` 守住，单元里不该出现覆盖它的东西。"""
    assert "0.0.0.0" not in unit and "--host" not in unit
