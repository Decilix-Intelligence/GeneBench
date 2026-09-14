"""W1 第 3 项：P2 的 provider 钉子**按通道取**（用户裁定 2026-09-10）。

在此之前 `inject()` 无条件用 private 那一个，公开通道的每一次真跑都在 P2 红成
「provider 变了」（`ops/reports/m6_public/plane_probe.md:61` 就是那条报错原文）。
**症状与病因指向两个不同的地方** —— 照着报错去查 provider 的人什么也查不到，
所以这里每条通道都要有一次**真注入**（不是只 grep 常量表）。
"""
from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import bundle as B                       # noqa: E402
from genetask import packager as P                     # noqa: E402
from genetask import pin                               # noqa: E402
from runner import inject as INJ                       # noqa: E402

ALL_CAPS = {"n33_bars_open_amount_vwap": True, "s8_state_endpoint": True,
            "anchor_ladder_54": False}
PARAMS40 = _REPO / "genetask" / "params" / "v1.0-smoke40.yaml"


# ------------------------------------------------------------------ 夹具

@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    """一份真 bundle + 通行证。与 `ops/test_inject.py::exported` 同一套流程 ——
    **不 import 那个模块**：跨测试文件借夹具会让两边的 `tmp_path_factory` 作用域纠缠。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_fz_ch", _REPO / "ops" / "freeze_v10.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)

    root = tmp_path_factory.mktemp("f01ch")
    row = next(r for r in P.load_params(PARAMS40) if r["task_id"] == "s1-cor-01")
    b = P.build_task(row, capabilities=ALL_CAPS)
    assert b.ok, b.problems
    task_dir = P.write_task(b, root / "reference", capabilities=ALL_CAPS)
    bundle = P.export_task(task_dir, root / "runner")
    assert P.pin_image_digest(bundle, "sha256:" + "a" * 64) == []
    ce = P.check_export(bundle, P.gold_sha_set(task_dir), b.task["canary"])
    assert ce == [], ce
    man = P.export_manifest(task_dir, bundle, check_export_result=ce, frozen_ref=fz.frozen_ref())
    return {"bundle": bundle, "manifest": man, "frozen_root": fz.frozen_ref()["root"]}


@pytest.fixture
def provider(tmp_path):
    """一棵**形状与真 provider 相同**的小树（靠 `files.sha256` 定根）。"""
    d = tmp_path / "provider"
    (d / "calendars").mkdir(parents=True)
    (d / "calendars" / "day.txt").write_text("2026-07-01\n2026-07-02\n", encoding="utf-8")
    (d / "instruments").mkdir()
    (d / "instruments" / "csi300.txt").write_text("SH600000\t2026-01-01\t2026-12-31\n",
                                                  encoding="utf-8")
    lines = []
    for f in sorted(d.rglob("*")):
        if not f.is_file() or f.name in ("files.sha256", "manifest.json"):
            continue
        raw = f.read_bytes()
        lines.append(f"{hashlib.sha256(raw).hexdigest()}  {len(raw)}  {f.relative_to(d)}")
    (d / "files.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


def _inject(exported, provider, run_root, **kw):
    return INJ.inject(exported["bundle"], "open", run_root=run_root, provider_root=provider,
                      config_id="cfg-a", model_upstream="", manifest=exported["manifest"],
                      expect_frozen_root=exported["frozen_root"], command='sh -c "true"',
                      require_docker=False, check_modes=False, **kw)


# ------------------------------------------------- 两条通道各一次真注入

@pytest.mark.parametrize("channel,const_owner,const_name", [
    ("private", pin, "PROVIDER_SHA256_ROOT"),
    ("public", INJ, "PUBLIC_PROVIDER_SHA256_ROOT"),
])
def test_each_channel_pins_its_own_provider(exported, provider, tmp_path, monkeypatch,
                                            channel, const_owner, const_name):
    """**钉子对得上**：把该通道的冻结根指到这棵测试树，注入必须走过 P2。

    通道从 `GENEBENCH_CHANNEL` 取 —— 这里连环境变量一起测，因为 f02 上就是这么给的。
    """
    monkeypatch.setenv(INJ.CHANNEL_ENV, channel)
    monkeypatch.setattr(const_owner, const_name, pin.provider_root_sha256(provider))
    r = _inject(exported, provider, tmp_path / f"rr-{channel}")
    assert r.run_dir.is_dir()


@pytest.mark.parametrize("channel", ["private", "public"])
def test_each_channel_rejects_the_other_providers_root(exported, provider, tmp_path,
                                                       monkeypatch, channel):
    """**钉子对不上**：不动冻结常量，测试树的根与它必然不同 → P2 当场红，且报错点名 P2。

    这条是判别力：上面那条只证明「对得上能过」，不证明「对不上会拦」。
    """
    monkeypatch.setenv(INJ.CHANNEL_ENV, channel)
    with pytest.raises(B.PackError) as e:
        _inject(exported, provider, tmp_path / f"rr-bad-{channel}")
    assert "[P2]" in str(e.value) and "provider" in str(e.value)


def test_the_two_channels_do_not_share_a_pin():
    """两条通道的钉子必须是**两个不同的值** —— 相同就说明有一边抄错了，
    而抄错的后果是「公开通道跑起来一切正常」，没有任何东西会报错。"""
    t = INJ.provider_pin_by_channel()
    assert set(t) == set(INJ.PROVIDER_PIN_CHANNELS)
    assert t["private"] != t["public"]
    assert t["private"] == pin.PROVIDER_SHA256_ROOT, "private 必须**引用**冻结常量，不许抄一份"


def test_unknown_channel_is_refused_not_defaulted():
    """拼错的通道名当场抛。回落到 private 会把一次拼写错误伪装成一次数据事故。"""
    with pytest.raises(B.PackError, match="不认识的通道"):
        INJ.provider_pin_expect("pubic")
    assert INJ.provider_pin_expect("public") == INJ.PUBLIC_PROVIDER_SHA256_ROOT


def test_the_pin_table_is_assembled_at_call_time(monkeypatch):
    """**运行时取常量，不用 import 期快照**（`pin.check_provider_pin` 里那段自查的同一条）。
    写成模块级 dict 的那一版会让 v1.1 重钉与既有测试的 monkeypatch 一起静默失效。"""
    monkeypatch.setattr(pin, "PROVIDER_SHA256_ROOT", "deadbeef")
    assert INJ.provider_pin_expect("private") == "deadbeef"


# ---------------------------------------------------------- 防漂 / 执行面

def test_channel_names_do_not_drift():
    """`runner/inject.py` 自己写了一份通道名与默认值（f02 上没有 `genebench_config`）。
    两份必然漂 —— 所以在 f01 这一侧逐字比对。"""
    import genebench_config as C
    assert INJ.CHANNEL_ENV == C.CHANNEL_ENV
    assert INJ.DEFAULT_CHANNEL == C.DEFAULT_CHANNEL
    assert set(INJ.PROVIDER_PIN_CHANNELS) == set(C.CHANNELS)


def test_inject_still_does_not_import_genebench_config():
    """`genebench_config` 不在 `ops/push_exec_to_f02.sh` 的白名单里 —— import 它的后果
    不是「少个默认值」，是**整棵 runner 在 f02 上 import 不了**，而 f01 侧一切正常。"""
    tree = ast.parse((_REPO / "runner" / "inject.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not a.name.startswith("genebench_config") for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("genebench_config")


@pytest.mark.skipif(not Path("/data/shared/genebench/snapshots/public_v1/qlib_provider").is_dir(),
                    reason="公开 provider 只在 f01 上")
def test_public_pin_is_the_real_public_provider_root():
    """钉子对着**真树现算的根**，不是抄报告里那串字。"""
    got = pin.provider_root_sha256("/data/shared/genebench/snapshots/public_v1/qlib_provider")
    assert got.startswith(INJ.PUBLIC_PROVIDER_SHA256_ROOT), got


# ---------------------------------------------------------- ① provider 元数据豁免
#
# 用户裁定 ① 走 A（2026-09-10）：`MANIFEST.sha256` 与 `build_info.json` 进 `PROVIDER_META_FILES`。
# 这一段要钉的**不是「豁免生效了」**（那是恒绿的门），是两件相反的事：
#   ① 豁免面恰好是那四个名字，一个不多；
#   ② 清单仍然覆盖树里**除这四个之外**的每一个文件，真缺文件 / 真多文件照旧判红。

REAL_TREES = {"private": Path("/data/shared/genebench/snapshots/v1/qlib_provider"),
              "public": Path("/data/shared/genebench/snapshots/public_v1/qlib_provider")}


def test_the_exemption_is_exactly_these_four_names():
    """写成前缀 / 后缀 / 通配的豁免会把「多出来的文件也是改动」整片关掉 ——
    而那是 `verify_filelist` 唯一能抓到「加文件」这一类改动的地方。"""
    assert pin.PROVIDER_META_FILES == frozenset(
        {"files.sha256", "manifest.json", "MANIFEST.sha256", "build_info.json"})
    assert pin.PROVIDER_FILELIST in pin.PROVIDER_META_FILES


@pytest.fixture
def provider_with_meta(provider):
    """在小树上补出真公开 provider 的形状：清单**之后**才写的两件构建元数据。"""
    (provider / "MANIFEST.sha256").write_text("deadbeef  0  whatever\n", encoding="utf-8")
    (provider / "build_info.json").write_text('{"built_at": "2026-09-10"}', encoding="utf-8")
    return provider


def test_the_two_build_metadata_files_no_longer_make_the_gate_red(provider_with_meta):
    """病灶复现：不豁免它们时，一棵**一个字节都没被动过**的公开树会在 P2 判红成
    「树里有而清单里没有」—— 症状说 provider 被改了，病因是打包器多写了两个文件。"""
    assert pin.verify_filelist(provider_with_meta) == []


@pytest.mark.parametrize("name", ["MANIFEST.sha256", "build_info.json"])
def test_the_exemption_is_by_name_not_by_shape(provider_with_meta, name):
    """同名文件豁免，**改名一个字母就不豁免** —— 证明这是四个字面名字，不是某种形状规则。"""
    (provider_with_meta / name).rename(provider_with_meta / (name + ".bak"))
    bad = pin.verify_filelist(provider_with_meta)
    assert any((name + ".bak") in b for b in bad), bad


def test_a_genuinely_missing_file_is_still_red(provider_with_meta):
    """**恒绿的门没有意义**：清单里有、树里没有，必须照旧红。"""
    victim = provider_with_meta / "calendars" / "day.txt"
    victim.unlink()
    bad = pin.verify_filelist(provider_with_meta)
    assert any("calendars/day.txt" in b for b in bad), bad


def test_a_changed_file_is_still_red(provider_with_meta):
    """内容对不上清单也照旧红 —— 根 hash 只证明清单没被动过，这一步才证明树与清单一致。"""
    (provider_with_meta / "calendars" / "day.txt").write_text("2099-01-01\n", encoding="utf-8")
    bad = pin.verify_filelist(provider_with_meta)
    assert any("内容与清单不符" in b for b in bad), bad


def test_an_extra_file_that_is_not_meta_is_still_red(provider_with_meta):
    """豁免了两件元数据，**不等于**豁免了「加文件」。塞一个别的进去必须红。"""
    (provider_with_meta / "features" ).mkdir(parents=True, exist_ok=True)
    (provider_with_meta / "features" / "sneaky.bin").write_bytes(b"x")
    bad = pin.verify_filelist(provider_with_meta)
    assert any("features/sneaky.bin" in b for b in bad), bad


@pytest.mark.parametrize("channel", sorted(REAL_TREES))
@pytest.mark.skipif(not REAL_TREES["public"].is_dir(), reason="真 provider 树只在 f01 上")
def test_the_filelist_covers_every_file_but_the_four(channel):
    """**在真树上**逐条比：清单列的集合 ∪ 四个豁免名 必须等于树里的全部文件。

    这条比 `verify_filelist(...) == []` 强：后者只说「没报错」，
    这里说的是「覆盖面到底是什么」—— 豁免多放过一个文件，上面那条不会红，这条会。
    """
    root = REAL_TREES[channel]
    listed = {l.split(None, 2)[2] for l in
              (root / pin.PROVIDER_FILELIST).read_text(encoding="utf-8").splitlines() if l.strip()}
    actual = {str(f.relative_to(root)) for f in root.rglob("*") if f.is_file()}
    extra = sorted(actual - listed - pin.PROVIDER_META_FILES)
    assert not extra, f"{channel} 树里这些文件既不在清单里也不是豁免的元数据：{extra[:10]}"
    assert not sorted(listed - actual), "清单里有而树里没有"


@pytest.mark.parametrize("channel", sorted(REAL_TREES))
@pytest.mark.skipif(not REAL_TREES["public"].is_dir(), reason="真 provider 树只在 f01 上")
def test_p2_is_green_on_the_real_tree_of_each_channel(channel):
    """`inject()` 里那一行原样调一遍。公开通道此前**每一次注入**都在这里红
    （`ops/reports/m6_public/plane_probe.md:61` 是那条报错原文）。"""
    bad = pin.check_provider_pin(REAL_TREES[channel], expect=INJ.provider_pin_expect(channel))
    assert bad == [], bad
