# -*- coding: utf-8 -*-
"""卡 4.rt（阶段四红队修复）的判据。

红队 2026-09-07 的十二条 findings 里，block 与 major 各自的落点：

| finding | 修在哪 | 这里的判据 |
| --- | --- | --- |
| 1 只凭文档加不出臂的集 | `ops/export_bundle.py::export_one(arms=…)` + CLI `--arms` | `test_export_one_can_出三臂的集` / `test_export_cli_takes_arms` |
| 2 没有文档化的本地自查路径 | `ops/run_f02_a1.py --dry` | `test_dry_run_root_refuses_data_roots` / `test_dry_check_compares_the_two_arms` |
| 3 加臂让工作树与冻结清单不一致而无人报 | 通行证记 `arm_registry` | `test_passport_records_arm_registry_freshness` |
| 4 §6.6.3 没实现 | `scorer/report.py` 的 `arm_kind` + 分块 | `test_table_a_carries_arm_kind` / `test_latex_blocks_by_kind_and_names_the_waived_rules` |
| 5 臂的书写顺序静默决定等价表比什么 | `export_bundle.check_arms` | `test_export_refuses_baseline_first_arm_order` |
| 6 pack→pin 顺序把通行证打废 | `ops/pack_adaptation.py --digest` | `test_pack_adaptation_pins_before_the_passport` |
| 7 适配 bundle 里没有 adapt 臂的题面 | `pack_adaptation --arms` + 注入器 P6b | `test_pack_adaptation_writes_every_named_arm` / `test_inject_p6b_names_the_arms_the_bundle_has` |
| 8 适配 bundle 能过守门（红线 B2） | `ops/push_guard.check_pushable_set` | `test_push_guard_refuses_the_adaptation_set` |

**不测**的：finding 9（适配模块 status=draft）是内容裁定不是代码，落点在
`ops/specs/adaptation_track.md` §0 的现状表；finding 10/11/12 是 minor，登记在
`ops/tickets_inbox/4.rt.md`。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                    # noqa: E402
from genetask import bundle as GB                                 # noqa: E402
from genetask import pin                                          # noqa: E402
from ops import export_bundle as EB                               # noqa: E402
from ops import push_guard as PG                                  # noqa: E402
from scorer import report as R                                    # noqa: E402

CAPS = json.loads((_REPO / "ops" / "capabilities.json").read_text(encoding="utf-8"))
FAKE_DIGEST = "sha256:" + "a" * 64
#: 第三个臂用 `hint`（`kind=instruction_variant`，无工件）——
#: 它与参照臂的差异恰好只有题面，正是 §6.2 等号最干净的一组。
THIRD_ARM = "hint"


# --------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def exported3(tmp_path_factory):
    """**三臂**出集：照手册那条命令（加 `--arms`），答案面落到 tmp。

    `ANSWER_ROOT` 改指 tmp 而不是 `$GENEBENCH_ROOT/reference` —— 出集会**覆写**
    同名题的答案面（judge_sha / gold_token 全换一套，红队 finding 11），
    在共享工作树上重出一道别人正在用的题是事故。
    """
    root = tmp_path_factory.mktemp("f01_4rt")
    old = EB.ANSWER_ROOT
    EB.ANSWER_ROOT = root / "reference"
    try:
        yield EB.export_one("s1-cor-01", root / "staging", FAKE_DIGEST,
                            capabilities=CAPS, arms=("strict", "open", THIRD_ARM))
    finally:
        EB.ANSWER_ROOT = old


@pytest.fixture
def provider(tmp_path):
    """一棵**假装是冻结 provider** 的树（形状与 ops/test_inject.py 的同款）。"""
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
        b = f.read_bytes()
        lines.append(f"{hashlib.sha256(b).hexdigest()}  {len(b)}  {f.relative_to(d)}")
    (d / "files.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


# --------------------------------------------------------------- finding 1 / 5：出集入口

def test_export_one_ships_the_third_arm(exported3):
    """**finding 1**：`--arms` 点名的臂真的进了 bundle（此前唯一有文档的出集入口固定两臂）。"""
    b = Path(exported3["bundle"])
    got = sorted(p.name for p in (b / "arms").glob("INSTRUCTION.*.md"))
    assert got == [f"INSTRUCTION.{a}.md" for a in sorted(("strict", "open", THIRD_ARM))], got
    assert exported3["arms"] == sorted(("strict", "open", THIRD_ARM))
    assert PG.check_bundle_tree(b) == []
    x = (b / "task.yaml").read_text(encoding="utf-8")
    assert f"{THIRD_ARM}:" in x, "task.yaml 的 instruction 段要记这个臂，否则注入器无 sha 可核"


def test_third_arm_differs_only_in_the_instruction(exported3):
    """三臂集里，非默认臂与参照臂的差异**只能**是题面（§6.2 / §6.6.4）。"""
    b = Path(exported3["bundle"])
    sha = {a: hashlib.sha256((b / "arms" / f"INSTRUCTION.{a}.md").read_bytes()).hexdigest()
           for a in ("strict", "open", THIRD_ARM)}
    assert sha[THIRD_ARM] != sha["open"], "变体臂与参照臂题面相同 = 它已经退化成参照臂的副本"
    assert sha["strict"] != sha["open"]


def test_export_refuses_baseline_first_arm_order():
    """**finding 5**：`--arms open,<新臂>` 会让等价表拿 open 跟 open 比 —— 必须当场拒。"""
    with pytest.raises(EB.ExportBlocked) as e:
        EB.check_arms([GB.BASELINE_ARM, THIRD_ARM])
    assert "第一个" in str(e.value) and "equivalence" in str(e.value)
    # 顺序对了就放行；不给这个参数 = 默认臂集合（行为逐字节不变）
    assert EB.check_arms([THIRD_ARM, GB.BASELINE_ARM]) == (THIRD_ARM, GB.BASELINE_ARM)
    assert EB.check_arms(None) is None


def test_export_refuses_unknown_arm_and_missing_baseline():
    with pytest.raises(EB.ExportBlocked) as e:
        EB.check_arms(["strict", "open", "no-such-arm"])
    assert "genetask/arms.yaml" in str(e.value)
    with pytest.raises(EB.ExportBlocked) as e:
        EB.check_arms(["strict"])
    assert GB.BASELINE_ARM in str(e.value)
    with pytest.raises(EB.ExportBlocked):
        EB.check_arms(["strict", "strict", "open"])


def test_export_cli_takes_arms(tmp_path, capsys):
    """CLI 上真的接了 `--arms`（手册照抄的是这条命令，不是那个函数）。"""
    rc = EB.main(["s1-cor-01", "--staging", str(tmp_path), "--digest", FAKE_DIGEST,
                  "--arms", f"{GB.BASELINE_ARM},{THIRD_ARM}"])
    assert rc == 1, "顺序错了必须红"
    assert "第一个" in capsys.readouterr().err


def test_export_cli_ships_the_third_arm(tmp_path, monkeypatch, capsys):
    """**手册那条命令**（不是那个函数）真的能出三臂的集 —— finding 1 的验收。"""
    monkeypatch.setattr(EB, "ANSWER_ROOT", tmp_path / "reference")
    rc = EB.main(["s1-cor-01", "--staging", str(tmp_path / "staging"), "--digest", FAKE_DIGEST,
                  "--arms", f"strict,{GB.BASELINE_ARM},{THIRD_ARM}"])
    assert rc == 0, capsys.readouterr().err
    b = tmp_path / "staging" / "tasks" / "s1-cor-01"
    assert sorted(p.name for p in (b / "arms").glob("INSTRUCTION.*.md")) == \
        [f"INSTRUCTION.{a}.md" for a in sorted(("strict", GB.BASELINE_ARM, THIRD_ARM))]
    m = json.loads((tmp_path / "staging" / "s1-cor-01.manifest.json").read_text(encoding="utf-8"))
    assert m["arms"] == sorted(("strict", GB.BASELINE_ARM, THIRD_ARM))
    assert PG.check_manifest(b, tmp_path / "staging" / "s1-cor-01.manifest.json") == []


# --------------------------------------------------------------- finding 3：冻结输入漂移

def test_passport_records_arm_registry_freshness(exported3, tmp_path, monkeypatch):
    """**finding 3**：通行证记下这次用的是哪一版臂注册表，与清单一致与否**可查**。"""
    got = exported3["arm_registry"]
    assert got["path"] == "genetask/arms.yaml"
    assert got["sha256"] == hashlib.sha256(
        (_REPO / "genetask" / "arms.yaml").read_bytes()).hexdigest()
    assert set(got["registered_arms"]) == set(GB.ALL_ARMS)
    m = json.loads(Path(exported3["manifest"]).read_text(encoding="utf-8"))
    assert m["arm_registry"] == got and m["arms"] == exported3["arms"]

    # 清单里记的是别的 sha 时，in_sync 必须是 false —— 这条以前只以 SKIP 的形式存在
    fake = tmp_path / "frozen.json"
    fake.write_text(json.dumps({"code": {"genetask/arms.yaml": "0" * 64}}), encoding="utf-8")
    monkeypatch.setattr(EB, "FROZEN_MANIFEST", fake)
    assert EB.arm_registry_freshness()["in_sync"] is False
    fake.write_text(json.dumps({"code": {"genetask/arms.yaml": got["sha256"]}}), encoding="utf-8")
    assert EB.arm_registry_freshness()["in_sync"] is True


# --------------------------------------------------------------- finding 2：本地自查

def test_dry_run_root_refuses_data_roots():
    """**finding 2**：run 根落在数据根之内会被 L-5a 拒 —— 这件事要在开跑前说清楚。"""
    RF = pytest.importorskip("ops.run_f02_a1")
    from runner.c41.runner_core import DATA_ROOTS
    with pytest.raises(SystemExit) as e:
        RF.dry_run_root(Path(DATA_ROOTS[0]) / "genebench" / "runs")
    assert "数据根" in str(e.value)
    assert RF.dry_run_root("/tmp/genebench_dry_test").is_absolute()


def test_dry_check_compares_the_two_arms(exported3, provider, tmp_path, monkeypatch, capsys):
    """**finding 2**：`--dry` 注入两臂并按 §6.2/§6.6.4 逐条比 —— 不起容器、不调模型。"""
    RF = pytest.importorskip("ops.run_f02_a1")
    monkeypatch.setattr(pin, "PROVIDER_SHA256_ROOT", pin.provider_root_sha256(provider))
    a = SimpleNamespace(bundle=exported3["bundle"], manifest=exported3["manifest"],
                        config_id="cfg-a", arms=f"{THIRD_ARM},{GB.BASELINE_ARM}", seq=1,
                        provider_root=str(provider), run_root=str(tmp_path / "dry"))
    assert RF.dry_check(a, 'sh -c "true"') == 0
    out = capsys.readouterr().out
    assert "[绿]" in out and "INSTRUCTION.md" in out


# --------------------------------------------------------------- finding 7：注入器 P6b

def test_inject_p6b_names_the_arms_the_bundle_has(exported3, provider, tmp_path, monkeypatch):
    """**finding 7**：bundle 里没有这个臂 → 有话说的门，不是裸 FileNotFoundError。"""
    from genetask.packager import PackError
    from runner import inject as INJ
    monkeypatch.setattr(pin, "PROVIDER_SHA256_ROOT", pin.provider_root_sha256(provider))
    absent = next(a for a in GB.ALL_ARMS if a not in exported3["arms"])
    manifest = json.loads(Path(exported3["manifest"]).read_text(encoding="utf-8"))
    with pytest.raises(PackError) as e:
        INJ.inject(exported3["bundle"], absent, run_root=tmp_path / "runs",
                   provider_root=provider, config_id="cfg-a", manifest=manifest,
                   expect_frozen_root=manifest["frozen_manifest"]["root"],
                   command='sh -c "true"', model_upstream="",
                   require_docker=False, check_modes=False, place_provider=False)
    msg = str(e.value)
    assert "P6b" in msg and THIRD_ARM in msg, msg
    assert not list((tmp_path / "runs").rglob("inject.json")), "红在建 run dir 之前，不留残骸"


# --------------------------------------------------------------- finding 8：按集拒推

def _fake_bundle(root: Path, set_id: str) -> Path:
    b = root / "tasks" / "x-01"
    b.mkdir(parents=True)
    (b / "task.yaml").write_text(f"schema_version: '1.0'\ntask_id: x-01\nset_id: {set_id}\n",
                                 encoding="utf-8")
    return b


def test_push_guard_gates_the_adaptation_set_by_destination(tmp_path, monkeypatch):
    """**判据变了，不是消失了**（2026-09-10 用户裁定 N-348，卡 Y2）。

    原来：形状全绿的 `v1.0-adapt` bundle **整集**不许推（红队 finding 8）。
    现在：整集拒**显式解除**（记因在 `ops/push_guard.py` 的 `SET_IDS_NOT_PUSHABLE` 上方），
    换成一道更窄的门 —— **落点**必须显式声明，且只许在 `ADAPT_DEST_PREFIX` 下。
    **不声明 = 拒**（不是放行）；推到主赛道的 batch 目录 = 拒。
    """
    monkeypatch.delenv(PG.DEST_ENV, raising=False)
    adapt = _fake_bundle(tmp_path / "a", "v1.0-adapt")
    smoke = _fake_bundle(tmp_path / "b", "v1.0-smoke")
    assert PG.check_bundle_tree(adapt) == []
    assert "v1.0-adapt" not in PG.SET_IDS_NOT_PUSHABLE, "N-348 已显式解除按集拒"
    bad = PG.check_pushable_set(adapt)
    assert bad and "落点不明" in bad[0], "没声明落点必须拒 —— 没声明不等于推对了地方"
    bad = PG.check_pushable_set(adapt, None, "/data/genebench_runner/m6/tasks/x-01")
    assert bad and "不在" in bad[0], "主赛道的 batch 目录仍然拒"
    assert PG.check_pushable_set(adapt, None, "/data/genebench_runner/adapt/tasks/x-01") == []
    monkeypatch.setenv(PG.DEST_ENV, "/data/genebench_runner/adapt/tasks/x-01")
    assert PG.check_pushable_set(adapt) == [], "环境变量这条路也要认"
    assert PG.check_pushable_set(smoke) == []
    with pytest.raises(PG.PushBlocked):
        PG.assert_pushable(smoke, tmp_path / "no-such-manifest.json")   # 老判据不受影响


def test_push_guard_refuses_a_gold_derived_passport(tmp_path):
    """通行证自报 `origin: gold_derived` 的 bundle 同样不许推（集名可以改，来源不能瞒）。"""
    b = _fake_bundle(tmp_path / "c", "v1.0-something")
    mp = tmp_path / "c" / "m.json"
    mp.write_text(json.dumps({"set_id": "v1.0-something", "origin": "gold_derived"}),
                  encoding="utf-8")
    bad = PG.check_pushable_set(b, mp)
    assert bad and "gold_derived" in bad[0]


# --------------------------------------------------------------- finding 6 / 7：适配出集

@pytest.fixture
def adapt_staging():
    """适配 bundle 的落点闸只认 `$GENEBENCH_ROOT/staging/` 下 —— 测试也照这条来。"""
    import shutil
    root = cfg.GENEBENCH_ROOT / "staging" / "4rt_pytest"
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _adapt_ready() -> bool:
    from ops import adaptation_track as AT
    return (AT.OUT_ROOT / "adapt-l1-01" / "broken.json").is_file()


def test_pack_adaptation_pins_before_the_passport(adapt_staging):
    """**finding 6**：`--digest` 在**出通行证之前**钉 —— 钉完的树与通行证一致。"""
    if not _adapt_ready():
        pytest.skip("适配产物还没生成")
    from genetask.bundle import IMAGE_DIGEST_PLACEHOLDER
    from ops import pack_adaptation as PK
    r = PK.pack_one("adapt-l1-01", adapt_staging, digest=FAKE_DIGEST, image="gb-cx-u:r1")
    b, m = Path(r["bundle"]), json.loads(Path(r["manifest"]).read_text(encoding="utf-8"))
    df = (b / "image" / "Dockerfile").read_bytes()
    assert IMAGE_DIGEST_PLACEHOLDER.encode() not in df, "占位 digest 还在 = P4b 会拒"
    assert FAKE_DIGEST.encode() in df
    assert m["files"]["image/Dockerfile"] == hashlib.sha256(df).hexdigest(), \
        "通行证记的是钉之前那份 = push_guard 与 P3 双红（红队实测的那条死路）"
    assert PG.check_manifest(b, r["manifest"]) == []


def test_pack_adaptation_writes_every_named_arm(adapt_staging):
    """**finding 7**：点名的臂各有一份题面；task.yaml 的 instruction 段与之对齐。"""
    if not _adapt_ready():
        pytest.skip("适配产物还没生成")
    import yaml
    from ops import pack_adaptation as PK
    r = PK.pack_one("adapt-l1-01", adapt_staging, digest=FAKE_DIGEST,
                    arms=("strict", "open", "adapt"))
    b = Path(r["bundle"])
    for arm in ("strict", "open", "adapt"):
        assert (b / "arms" / f"INSTRUCTION.{arm}.md").is_file(), arm
    t = yaml.safe_load((b / "task.yaml").read_text(encoding="utf-8"))
    assert sorted(t["instruction"]) == ["adapt", "open", "strict"]
    with pytest.raises(PK.PackBlocked):
        PK.pack_one("adapt-l1-01", adapt_staging, arms=("strict", "open", "no-such-arm"))


def test_pack_adaptation_bundle_needs_an_explicit_destination(adapt_staging, monkeypatch):
    """打得出来 ≠ 随便推：N-348 之后落点必须显式，且只许在适配根下（卡 Y2）。"""
    if not _adapt_ready():
        pytest.skip("适配产物还没生成")
    from ops import pack_adaptation as PK
    monkeypatch.delenv(PG.DEST_ENV, raising=False)
    r = PK.pack_one("adapt-l1-01", adapt_staging, digest=FAKE_DIGEST)
    with pytest.raises(PG.PushBlocked) as e:
        PG.assert_pushable(r["bundle"], r["manifest"])
    assert "落点不明" in str(e.value)
    PG.assert_pushable(r["bundle"], r["manifest"], "/data/genebench_runner/adapt/tasks/adapt-l1-01")


# --------------------------------------------------------------- finding 4：主表按 kind 分块

def _rec(arm: str, task: str = "s1-cor-01") -> dict:
    return {"config_id": "cfg-x", "arm": arm, "task_id": task, "stage": "S1",
            "run_status": "ok", "sr_bucket": "scorable", "validity": "valid",
            "l3_pass": True, "malformed": False, "correctness": {"f1": 1.0}}


def test_table_a_carries_arm_kind():
    """**finding 4**：每一行带 `arm_kind`，认不出的臂记 `unknown`（不抛）。"""
    rows = R.table_a([_rec("strict"), _rec(GB.BASELINE_ARM), _rec("hint"), _rec("gone-arm")])
    kinds = {r["arm"]: r["arm_kind"] for r in rows}
    assert kinds["strict"] == "protocol"
    assert kinds[GB.BASELINE_ARM] == "baseline"
    assert kinds["hint"] == "instruction_variant"
    assert kinds["gone-arm"] == "unknown"
    assert "arm_kind" in R.TABLE_A_COLUMNS
    assert all("arm_kind" in r for r in R.table_b([_rec("strict"), _rec("hint")]))


def test_latex_blocks_by_kind_and_names_the_waived_rules():
    """**§6.6.3**：instruction_variant 臂另起一块，块首写明它免了哪些等价规则。"""
    from genetask.render import WAIVED_FOR_VARIANT
    rows = R.table_a([_rec("strict"), _rec(GB.BASELINE_ARM), _rec("hint")])
    tex = R.to_latex(rows, R.TABLE_A_COLUMNS, caption="A", label="tab:a")
    assert r"\multicolumn" in tex, "不止一种 kind 时必须分块"
    assert "instruction\\_variant" in tex
    for code in WAIVED_FOR_VARIANT[:3]:
        assert code.replace("^", "\\^{}") in tex or code in tex, code
    # 块首必须在变体臂那一行**之前**（分块不是把说明堆在表尾）
    head = tex.index("instruction\\_variant")
    assert head < tex.index(" hint ") if " hint " in tex else True
    # 只有一种 kind 时不分块（单臂表不该多出一行标题）
    one = R.to_latex(R.table_a([_rec("strict")]), R.TABLE_A_COLUMNS, caption="A", label="t")
    assert r"\multicolumn" not in one
    # 显式关掉也不分块 —— 调用方要的是旧版面时不必删列
    off = R.to_latex(rows, R.TABLE_A_COLUMNS, caption="A", label="t", block_by_kind=False)
    assert r"\multicolumn" not in off


def test_waived_rules_come_from_the_same_place_as_the_check():
    """免例清单与建题时真的免掉的是**同一份** —— 报告器不许自己抄一份。"""
    from genetask.render import WAIVED_FOR_VARIANT
    assert R.waived_rules_for("instruction_variant") == tuple(WAIVED_FOR_VARIANT)
    assert R.waived_rules_for("protocol") == ()
    assert R.waived_rules_for("baseline") == ()
