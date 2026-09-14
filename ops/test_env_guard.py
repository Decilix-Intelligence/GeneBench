"""`ops/guard_modes.py` 自身的判别力：它必须抓得到放松，也不能恒红。"""
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
_spec = importlib.util.spec_from_file_location("_guard", _REPO / "ops" / "guard_modes.py")
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference" / "artifact_schema.py").write_text("x", encoding="utf-8")
    (tmp_path / "ops" / "manifests").mkdir(parents=True)
    (tmp_path / "ops" / "manifests" / "v1.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(G, "EXTERNAL_ROOTS", ())
    (tmp_path / "runner" / "f02").mkdir(parents=True)      # 新建目录也必须被覆盖
    (tmp_path / "runner" / "f02" / "v.py").write_text("x", encoding="utf-8")
    G.harden(tmp_path)
    return tmp_path


def test_guard_is_green_after_harden(fake_repo):
    assert G.check(fake_repo) == []


@pytest.mark.parametrize("rel,bit", [
    ("reference", stat.S_IRGRP | stat.S_IXGRP),
    ("reference/artifact_schema.py", stat.S_IROTH),
    ("ops/manifests", stat.S_IRWXO),
    ("ops/manifests/v1.json", stat.S_IWGRP),
])
def test_guard_catches_every_kind_of_loosening(fake_repo, rel, bit):
    """目录与文件、组与其它、读与写 —— 每一种放松都要抓到。
    本轮真实发生过的三次分别是：文件 0644、目录 0755、目录 0755。"""
    p = fake_repo / rel
    os.chmod(p, p.stat().st_mode | bit)
    bad = G.check(fake_repo)
    assert any(str(p) in x for x in bad), f"{rel} 放松了 {oct(bit)} 却没被抓到"
    assert G.harden(fake_repo) >= 1
    assert G.check(fake_repo) == []


def test_assert_modes_refuses_to_start(fake_repo):
    """**启动守门**：使用时刻检查，不只推送时刻。中间任何人 chmod 一下都不会有人知道。"""
    G.assert_modes(fake_repo, who="测试")                      # 合规时不抛
    os.chmod(fake_repo / "reference", 0o755)
    with pytest.raises(SystemExit, match="拒绝启动"):
        G.assert_modes(fake_repo, who="测试")


def test_harden_does_not_touch_owner_bits(fake_repo):
    """收紧只动组/其它位 —— 把属主的执行位也抹掉会让脚本跑不了。"""
    script = fake_repo / "reference" / "run.sh"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(script, 0o755)
    G.harden(fake_repo)
    assert script.stat().st_mode & 0o777 == 0o700


def test_guard_covers_newly_created_dirs_not_a_whitelist(fake_repo):
    """**主判据是封闭的**：根下的一切都要查，不是一张敏感目录白名单。

    第一版就是白名单，当场漏了两个：`runner/f02/`（新建目录）与
    `scratch/f02_bundle/reference/`（造 bundle 时建的，**里面有 gold**）。
    开放列举注定会烂 —— 这正是同一轮指令六里写过的话，却在守门里犯了一遍。
    """
    import os
    brand_new = fake_repo / "some" / "dir" / "nobody" / "listed"
    brand_new.mkdir(parents=True)
    os.chmod(brand_new, 0o755)
    bad = G.check(fake_repo)
    assert any(str(brand_new) in x for x in bad), \
        "白名单之外的新目录没被查到 —— 判据不是封闭的"
    assert not hasattr(G, "SENSITIVE_ROOTS"), "白名单还在，说明没改成封闭判据"


def test_no_logrotate_config_targets_the_access_log():
    """**access_log 永不自动轮转**（裁定 2026-09-04）。它是探针结算源：
    轮转落在某次 run 中间，切片缺一段，而**缺段看起来像「这段时间没请求」**。"""
    assert G.check_no_logrotate() == [], "发现了针对 access_log 的自动轮转配置"


def test_logrotate_check_actually_looks(tmp_path, monkeypatch):
    """判别力：造一个假的 logrotate 片段，必须被查到 ——
    否则这条检查只是「那台机器上恰好没有 logrotate」的另一种说法。"""
    d = tmp_path / "logrotate.d"
    d.mkdir()
    (d / "genebench").write_text(
        "/data/shared/genebench/logs/gateway_access.jsonl {\n  daily\n  rotate 7\n}\n",
        encoding="utf-8")
    monkeypatch.setattr(G, "LOGROTATE_DIRS", (str(d),))
    bad = G.check_no_logrotate()
    assert any("轮转配置" in x for x in bad), f"没查到假配置，实际 {bad}"
    (d / "genebench").write_text("/var/log/other.log {\n  daily\n}\n", encoding="utf-8")
    assert G.check_no_logrotate() == [], "不相干的轮转配置不该判红"


def test_unreadable_logrotate_dir_is_reported_not_skipped(tmp_path, monkeypatch):
    """**读不了 ≠ 查过了没有**。跳过会让「没找到」既表示干净又表示没查。"""
    d = tmp_path / "unreadable"
    d.mkdir()
    monkeypatch.setattr(G, "LOGROTATE_DIRS", (str(d),))
    import os
    os.chmod(d, 0o000)
    try:
        bad = G.check_no_logrotate()
        if os.geteuid() != 0:          # root 读得了任何目录，这条对它不成立
            assert any("读不了" in x for x in bad), f"实际 {bad}"
    finally:
        os.chmod(d, 0o700)


def test_guard_covers_pycache_because_it_holds_answer_plane_bytecode(tmp_path):
    """`__pycache__` 曾在 `SKIP_DIRS` 里，理由写着「缓存不含产物」——**那是错的**。

    `reference/__pycache__/*.pyc` 是答案面代码的编译副本，而
    `test_answer_artifacts_are_not_group_world_readable` 正是审计它。
    于是出现过一个尴尬状态：红线测试报红，`harden()` 却返回 0 ——
    守门自称封闭判据，漏掉的恰好是被审计的那一类。摘掉那条之后，
    第一次 harden 收紧了 **18890** 项（对照：白名单版第一次只碰 4 项）。
    """
    import ops.guard_modes as G
    assert "__pycache__" not in G.SKIP_DIRS, \
        "缓存目录里躺着 reference/ 与 scorer/ 的字节码，不能跳过"
    ref = tmp_path / "reference" / "__pycache__"
    ref.mkdir(parents=True)
    pyc = ref / "secret.cpython-310.pyc"
    pyc.write_bytes(b"answer-plane bytecode")
    pyc.chmod(0o664)
    assert G.check(tmp_path), "0664 的 pyc 没被 check 抓到 —— 判据还是漏的"
    G.harden(tmp_path)
    assert oct(pyc.stat().st_mode)[-3:] == "600", oct(pyc.stat().st_mode)
    assert G.check(tmp_path) == []


# --------------------------------------------------------------- D-23 逐条核（2026-09-04）

def test_no_dead_or_unfalsifiable_skips_in_the_guard():
    """D-23：**skip 的理由必须能被另一条测试证伪。**

    三条都摘掉了，各有实测理由：
    * `__pycache__` —— 里面是答案面代码的编译副本（红线测试正是审计它）；
    * `.git` —— `objects/` 里是 `reference/*.py` 的历次副本，实测确实有组/其它开放的条目；
    * `.venv` / `venv` —— 在本仓与 GENEBENCH_ROOT 下**都不存在**（环境叫 `env`）。
      一条从不触发的 skip 会让人以为某处被排除了，而实际上没有 —— 死 skip 与死白名单同族。
    """
    import ops.guard_modes as G
    assert G.SKIP_DIRS == frozenset(), f"又加回了 skip：{sorted(G.SKIP_DIRS)}"


def test_guard_covers_the_git_object_store(tmp_path):
    """`.git/objects/` 里是答案面源码的历次副本。摘掉那条 skip 之后
    第一次 harden 又收紧了 **1775** 项，而 git 照常可用。"""
    import ops.guard_modes as G
    obj = tmp_path / ".git" / "objects" / "ab"
    obj.mkdir(parents=True)
    blob = obj / "cdef0123456789"
    blob.write_bytes(b"a version of reference/artifact_schema.py")
    blob.chmod(0o664)
    assert G.check(tmp_path), "0664 的 git object 没被抓到"
    G.harden(tmp_path)
    assert G.check(tmp_path) == []


def test_unreadable_logrotate_file_is_reported_not_skipped(tmp_path, monkeypatch):
    """先前文件级的 `OSError` 是静默 `continue`，而目录级的同样错误被报成
    「读不了 ≠ 查过了没有」—— 同一条理由，两种处置。/etc/logrotate.d 下
    完全可能是 root:root 0600（今天恰好都可读，所以这个洞一直没露）。"""
    import ops.guard_modes as G
    d = tmp_path / "logrotate.d"
    d.mkdir()
    f = d / "secret"
    f.write_text("anything", encoding="utf-8")
    monkeypatch.setattr(G, "LOGROTATE_DIRS", (str(d),))
    assert G.check_no_logrotate() == []
    orig = G.Path.read_text

    def boom(self, *a, **k):
        if self.name == "secret":
            raise OSError("Permission denied")
        return orig(self, *a, **k)

    monkeypatch.setattr(G.Path, "read_text", boom)
    bad = G.check_no_logrotate()
    assert bad and "读不了" in bad[0], bad


# =============================================================== 冻结防漂（2026-09-05 实测补）

def test_frozen_ref_catches_a_changed_template_file(tmp_path, monkeypatch):
    """**改一个模板文件，`frozen_ref(verify=True)` 必须拦。**

    2026-09-05 实测：它**拦不住**。校验只比了「题面指纹」与「出集清单」，
    从来没比过 `templates` 段 —— 而 `solve.py` 在 `TEMPLATE_FILES` 里、
    进 `templates`、因而进 `root`。改了它：清单记 `2d06cd…`、盘上 `c32ea474…`，
    校验**返回成功**。

    **这是同一个 F7 形态的第三次**，而且就发生在这个函数里 ——
    它的 docstring 逐字写着「这正是 pin.py 里批判过的 F7 形态，在同一个仓库里犯了第二次」。
    第二次的修法是「现算一遍」，但**比错了字段**：现算了，没比到点子上。
    """
    import json as _json
    import sys as _sys
    from pathlib import Path as _P

    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    import ops.freeze_v10 as F

    man = _json.loads(_P(F.OUT).read_text(encoding="utf-8"))
    # 造一份「模板 sha 与工作树不符」的清单，其余一切照旧
    key = sorted(man["templates"])[0]
    man["templates"][key] = dict(man["templates"][key])
    man["templates"][key]["solve.py"] = "0" * 64
    fake = tmp_path / "frozen.json"
    fake.write_text(_json.dumps(man, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(F, "_VERIFIED", {}, raising=False)
    with pytest.raises(SystemExit) as e:
        F.frozen_ref(fake)
    assert "模板文件变了" in str(e.value) and key in str(e.value)


def test_frozen_ref_still_passes_on_an_unchanged_tree(monkeypatch):
    """反面：工作树与清单一致时不许乱红 —— 恒红的门与恒绿的一样会被绕过。"""
    import sys as _sys
    from pathlib import Path as _P

    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    import ops.freeze_v10 as F

    monkeypatch.setattr(F, "_VERIFIED", {}, raising=False)
    ref = F.frozen_ref()
    assert ref["root"] and ref["set_version"]


# --------------------------------------------------------------- D-27 实施要求：逐段红测试

def _freeze_mod():
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    import ops.freeze_v10 as F
    return F


def _manifest_copy(tmp_path, mutate):
    """造一份**只在一段上**与工作树不同的清单，其余全部合法。

    「其余全部合法」是关键 —— 否则红可能来自别的段，那条测试就没有定位能力。
    """
    import json as _json
    from pathlib import Path as _P

    F = _freeze_mod()
    man = _json.loads(_P(F.OUT).read_text(encoding="utf-8"))
    mutate(man)
    f = tmp_path / "frozen.json"
    f.write_text(_json.dumps(man, ensure_ascii=False), encoding="utf-8")
    return F, f


def test_frozen_ref_section_instruction_fingerprint(tmp_path, monkeypatch):
    """段一：**题面指纹**。"""
    F, f = _manifest_copy(tmp_path, lambda m: m.update(instruction_fingerprint="0" * 64))
    monkeypatch.setattr(F, "_VERIFIED", {}, raising=False)
    with pytest.raises(SystemExit) as e:
        F.frozen_ref(f)
    assert "题面指纹" in str(e.value)


def test_frozen_ref_section_released_tasks(tmp_path, monkeypatch):
    """段二：**出集清单**。"""
    def _drop(m):
        m["released_tasks"] = m["released_tasks"][:-1]
    F, f = _manifest_copy(tmp_path, _drop)
    monkeypatch.setattr(F, "_VERIFIED", {}, raising=False)
    with pytest.raises(SystemExit) as e:
        F.frozen_ref(f)
    assert "出集清单" in str(e.value)


def test_frozen_ref_section_templates(tmp_path, monkeypatch):
    """段三：**templates** —— 这一段原来没被比过（N-74）。"""
    def _touch(m):
        k = sorted(m["templates"])[0]
        m["templates"][k] = {**m["templates"][k], "solve.py": "0" * 64}
    F, f = _manifest_copy(tmp_path, _touch)
    monkeypatch.setattr(F, "_VERIFIED", {}, raising=False)
    with pytest.raises(SystemExit) as e:
        F.frozen_ref(f)
    assert "模板文件变了" in str(e.value)


def test_frozen_ref_sections_are_counted():
    """**判据是可数的**：门声称保护几段，验收里就要有几条红测试。

    这条把「三段」钉成一个数 —— 将来加了第四段却忘了补红测试，它会红。
    """
    import inspect
    src = inspect.getsource(_freeze_mod().frozen_ref)
    claimed = sum(src.count(k) for k in ("instruction_fingerprint", "released_tasks", "templates"))
    assert claimed >= 3
    here = Path(__file__).read_text(encoding="utf-8")
    for sect in ("instruction_fingerprint", "released_tasks", "templates"):
        assert f"test_frozen_ref_section_{sect}" in here, f"{sect} 段没有对应的红测试"


# --------------------------------------------------------------- 参考轴（裁定 2026-09-05：两条版本轴）

def _ref_manifest_copy(tmp_path, mutate):
    import json as _json
    from pathlib import Path as _P

    F = _freeze_mod()
    m = _json.loads(_P(F.REFERENCE_OUT).read_text(encoding="utf-8"))
    mutate(m)
    f = tmp_path / "ref.json"
    f.write_text(_json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return F, f


def test_reference_ref_baseline_is_green(monkeypatch):
    """防恒红：工作树与参考清单一致时不许乱红。"""
    F = _freeze_mod()
    monkeypatch.setattr(F, "_REF_VERIFIED", {}, raising=False)
    r = F.reference_ref()
    assert r["reference_version"].startswith("r") and r["reference_root"]


def test_reference_ref_section_solve_py(tmp_path, monkeypatch):
    """参考轴段一：**40 个 `solve.py`**。"""
    def _touch(m):
        k = sorted(m["reference_templates"])[0]
        m["reference_templates"][k] = {"solve.py": "0" * 64}
    F, f = _ref_manifest_copy(tmp_path, _touch)
    monkeypatch.setattr(F, "_REF_VERIFIED", {}, raising=False)
    with pytest.raises(SystemExit) as e:
        F.reference_ref(f)
    assert "参考解" in str(e.value)


def test_reference_ref_section_modules(tmp_path, monkeypatch):
    """参考轴段二：**公共主干**（`oracle_io` + 各阶段 `*_oracle_common`）。"""
    def _touch(m):
        k = sorted(m["reference_modules"])[0]
        m["reference_modules"][k] = "0" * 64
    F, f = _ref_manifest_copy(tmp_path, _touch)
    monkeypatch.setattr(F, "_REF_VERIFIED", {}, raising=False)
    with pytest.raises(SystemExit) as e:
        F.reference_ref(f)
    assert "参考模块" in str(e.value)


def test_reference_files_cover_the_whole_reference_plane():
    """**参考模块清单必须覆盖 `reference/` 下所有 oracle 公共层。**

    加了新的公共层却忘了写进 `REFERENCE_MODULE_FILES`，它就**不受冻结保护** ——
    改了没人知道，而 gold 的算法已经变了。
    """
    F = _freeze_mod()
    root = Path(__file__).resolve().parents[1]
    found = {f"reference/{p.name}" for p in (root / "reference").glob("*_oracle_common.py")}
    found.add("reference/oracle_io.py")
    missing = sorted(found - set(F.REFERENCE_MODULE_FILES))
    assert not missing, f"这些参考模块没进冻结清单：{missing}"


def test_solve_py_left_the_task_set_axis():
    """`solve.py` 是**答案面**，不许再出现在 agent 可见的那条轴上。

    它原来住在 `TEMPLATE_FILES` 里 —— 于是每修一个 oracle 都要推一次任务集版本，
    2026-09-05 一天推了三次，其中两次**题面一个字没动**。
    """
    F = _freeze_mod()
    assert "solve.py" not in F.TEMPLATE_FILES
    assert "solve.py" in F.REFERENCE_TEMPLATE_FILES


def test_root_scope_is_recorded_in_the_manifest():
    """root **覆盖什么**要写在清单里 —— 否则事后比两个 root 的人
    只会看到「不一样」，并合理地以为题面动过（拆轴那次 root 就是这样变的）。"""
    import json as _json
    F = _freeze_mod()
    m = _json.loads(Path(F.OUT).read_text(encoding="utf-8"))
    assert "root_scope" in m
    assert "solve.py" in m["root_scope"]["excluded_to_reference_axis"]
    assert "solve.py" not in m["root_scope"]["template_files"]
