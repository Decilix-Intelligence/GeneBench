"""符号名与规格对齐（指令四①，2026-09-04）。

规格 §4 把 `check_provider_pin` 定义成 `(provider_root, *, expect)` 的**现算**函数。
代码一度让**记录值**版占着这个名字（现算版叫 `check_provider_pin_root`）——
卡 4.2 接线时按规格调用会拿到错的那个，**而拿到的那个永远返回绿**。
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import pin                                  # noqa: E402
from genetask import schema as S                          # noqa: E402


def test_spec_symbol_is_the_recomputing_one():
    """`check_provider_pin` 必须是规格 §4 那个签名：`(provider_root, *, expect)`。"""
    sig = inspect.signature(pin.check_provider_pin)
    params = list(sig.parameters)
    assert params[0] == "provider_root", f"第一个参数应是 provider_root，实际 {params}"
    assert "expect" in sig.parameters
    assert sig.parameters["expect"].kind is inspect.Parameter.KEYWORD_ONLY


def test_recorded_value_check_has_a_different_name():
    """记录值比对**不是**完整性判据，不许占规格里的名字。"""
    assert hasattr(pin, "check_recorded_pin")
    assert not hasattr(pin, "check_provider_pin_root"), "旧名字还在，会有人继续用它"
    sig = inspect.signature(pin.check_recorded_pin)
    assert list(sig.parameters) == ["actual_sha256"]


def test_spec_path_still_resolves():
    """规格点名的路径 `genetask.schema.check_provider_pin` 必须成立，且指向现算那个。"""
    assert S.check_provider_pin is pin.check_provider_pin
    assert "provider_root" in inspect.signature(S.check_provider_pin).parameters


def test_recorded_check_cannot_prove_integrity(tmp_path):
    """把两者的**判别力差异**钉死：记录值版对一棵被改过的树照样返回绿。"""
    import hashlib
    d = tmp_path / "prov"
    (d / "calendars").mkdir(parents=True)
    (d / "calendars" / "day.txt").write_text("2026-07-01\n", encoding="utf-8")
    b = (d / "calendars" / "day.txt").read_bytes()
    (d / "files.sha256").write_text(
        f"{hashlib.sha256(b).hexdigest()}  {len(b)}  calendars/day.txt\n", encoding="utf-8")
    root = pin.provider_root_sha256(d)
    assert pin.check_provider_pin(d, expect=root) == []

    (d / "calendars" / "day.txt").write_text("2099-01-01\n", encoding="utf-8")
    # 记录值版**根本看不见那棵树** —— 它只拿到一个字符串。
    # 递给它冻结值本身，它就说绿，不管树被改成什么样。
    assert pin.check_recorded_pin(pin.PROVIDER_SHA256_ROOT) == [], \
        "记录值版只比字符串 —— 这正是它不能当完整性判据的理由"
    assert pin.check_provider_pin(d, expect=root), "现算版必须抓到"
    # 差异的实质：一个的入参是**路径**，另一个是**别人告诉你的数**
    import inspect as _i
    assert "provider_root" in _i.signature(pin.check_provider_pin).parameters
    assert "actual_sha256" in _i.signature(pin.check_recorded_pin).parameters
