# -*- coding: utf-8 -*-
"""卡 4.1 验收：臂 = 投放的工件集合 + 指令变体，由 `genetask/arms.yaml` 定义，不写死在代码里。

**这份测试要挡住的四种静默失败**：

1. 注册表被改成一个「只有裸臂」的集合 —— 分数照出、报表照排，只是「协议有没有用」
   这个问题再也没有被问过（`test_registry_refuses_a_baseline_only_default_set`）；
2. 泛化把内置两臂的出集改了字节 —— 那等于在没人签字的情况下换了题面
   （`test_builtin_two_arms_export_is_byte_identical`）；
3. 指令变体臂的「例外」变成「什么都不查」—— E1/E2 欠定/C1 三条必须照查
   （`test_variant_arm_still_checked_on_e1_e2_c1`）；
4. 新臂的工件集与它自己的清单漂开 —— 少给一个就是**干预失败**而不是隔离失败
   （`test_doc_arm_injects_exactly_its_manifest`）。
"""
from __future__ import annotations

import ast
import copy
import hashlib
import importlib
import importlib.util
import json
import re
import shutil
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import bundle as B                      # noqa: E402
from genetask import packager as P                    # noqa: E402
from genetask import pin                              # noqa: E402
from genetask import render as R                      # noqa: E402
from genetask import schema as S                      # noqa: E402
from runner import inject as INJ                      # noqa: E402

ALL_CAPS = {"n33_bars_open_amount_vwap": True, "s8_state_endpoint": True,
            "anchor_ladder_54": False}
PARAMS40 = _REPO / "genetask" / "params" / "v1.0-smoke40.yaml"
ARMS_YAML = _REPO / "genetask" / "arms.yaml"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# --------------------------------------------------------------- 注册表本身

def test_arms_yaml_is_the_single_source_of_arm_names():
    """`schema.ARMS` / `bundle.ARMS` 都从 arms.yaml 派生，不是第二份常量。"""
    assert S.ARMS == B.ARMS, "两份常量漂了 —— 那正是本卡要消灭的东西"
    doc = yaml.safe_load(ARMS_YAML.read_text(encoding="utf-8"))
    want_all = tuple(a["id"] for a in doc["arms"])
    want_default = tuple(a["id"] for a in doc["arms"] if a.get("default"))
    assert B.ALL_ARMS == want_all, "ALL_ARMS 与 arms.yaml 的顺序/内容不一致"
    assert S.ARMS == want_default, "默认臂集合与 arms.yaml 的 default 标记不一致"


def test_builtin_arm_order_is_strict_then_open():
    """**顺序不许动**：task.yaml 的 instruction 段按 `ARMS` 排，换了顺序就换了字节。"""
    assert S.ARMS == ("strict", "open"), \
        f"内置两臂的顺序变成了 {S.ARMS} —— task.yaml 的 instruction 段会跟着变字节"
    assert B.BASELINE_ARM == "open", "参照臂必须是裸臂 open"


def test_baseline_arm_has_no_artifacts_and_is_unique():
    base = [a for a in B.ARM_REGISTRY if a.is_baseline]
    assert len(base) == 1, f"kind=baseline 的臂有 {len(base)} 个 —— 等价规则要有唯一参照"
    assert base[0].artifacts == (), "裸臂声明了工件 —— §6.2 等号判据的另一半不成立"
    assert INJ.arm_files(base[0].id) == {}, "裸臂的工件展开集非空"


def test_every_registered_arm_is_usable_end_to_end():
    """登记了就必须能用：措辞列取得到、工件清单读得到、变体文本在。"""
    pb = R.load_phrasebook(P.PHRASEBOOK)
    for a in B.ARM_REGISTRY:
        col = a.column()
        assert col in R.PHRASEBOOK_COLUMNS, f"{a.id} 落到了不存在的列 {col}"
        for f, table in pb.items():
            for vk, cols in table.items():
                assert col in cols, f"phrasebook[{f}][{vk}] 缺 {col} 列（臂 {a.id}）"
        assert INJ.arm_files(a.id) is not None
        if a.variant_text_file:
            assert (_REPO / "genetask" / a.variant_text_file).is_file(), \
                f"{a.id} 声明了变体文本却没有文件 —— 那是个空壳臂"


# --------------------------------------------------------------- schema 负例

def _load_variant(tmp_path: Path, mutate) -> None:
    """把 arms.yaml 拷一份、改掉、用 `load_arms` 读 —— 不动仓库里的那份。"""
    doc = yaml.safe_load(ARMS_YAML.read_text(encoding="utf-8"))
    mutate(doc)
    p = tmp_path / "arms.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return B.load_arms(p)


def test_registry_refuses_a_baseline_only_default_set(tmp_path):
    """**删掉 strict 必须红**：只剩裸臂的集合不是对照实验。"""
    def drop_strict(doc):
        doc["arms"] = [a for a in doc["arms"] if a["id"] != "strict"]
    with pytest.raises(B.PackError, match="只有裸臂"):
        _load_variant(tmp_path, drop_strict)


def test_registry_refuses_a_missing_file(tmp_path):
    with pytest.raises(B.PackError, match="臂注册表不存在"):
        B.load_arms(tmp_path / "nope.yaml")


@pytest.mark.parametrize("mutate,pat", [
    (lambda d: d["arms"].append(dict(d["arms"][0], id="strict")), "臂名重复"),
    (lambda d: d["arms"][0].__setitem__("kind", "magic"), "kind="),
    (lambda d: d["arms"][0].__setitem__("id", "Strict"), "不合法"),
    (lambda d: d["arms"][1].__setitem__("artifacts", [{"manifest": "x/MANIFEST.json", "mount": "p"}]),
     "baseline 臂不许投放工件"),
    (lambda d: d["arms"][1].__setitem__("fallback_column", "strict"),
     "只有 instruction_variant 臂可以声明 fallback_column"),
    (lambda d: d["arms"][0]["artifacts"][0].__setitem__("mount", "a/b"), "mount="),
    (lambda d: d["arms"][0]["artifacts"][0].__setitem__("manifest", "/etc/MANIFEST.json"), "manifest="),
    (lambda d: d["arms"][0]["artifacts"][0].__setitem__("manifest", "ops/x.json"), "manifest="),
    (lambda d: d["arms"][0].__setitem__("equivalence", "instruction_variant_exception"), "必须配 equivalence"),
    (lambda d: d["arms"][0].__setitem__("description", "  "), "description 不能为空"),
    (lambda d: [a.__setitem__("kind", "protocol") for a in d["arms"] if a["id"] == "open"],
     "恰好.*一个 kind=baseline|只有裸臂|baseline"),
    (lambda d: d["arms"][0].__setitem__("zzz", 1), "键集不对"),
])
def test_registry_schema_negatives(tmp_path, mutate, pat):
    """schema 的判别力：每条规则都要有一个真的会被它挡住的坏输入。"""
    with pytest.raises(B.PackError, match=pat):
        _load_variant(tmp_path, mutate)


def test_a_new_protocol_arm_needs_no_code(tmp_path):
    """**加臂只加配置**：造一个仓库里没有的臂，走完 `load_arms` → `arm_files` 全程。"""
    man = tmp_path / "MANIFEST.json"
    (tmp_path / "NOTE.md").write_text("测试用工件\n", encoding="utf-8")
    man.write_text(json.dumps({"status": "released",
                               "artifacts": {"NOTE.md": _sha((tmp_path / "NOTE.md").read_bytes())}}),
                   encoding="utf-8")

    def add(doc):
        doc["arms"].append({"id": "probe-arm", "kind": "protocol", "default": False,
                            "phrasebook_column": "strict", "equivalence": "e_rules",
                            "description": "临时臂（测试）",
                            "artifacts": [{"manifest": str(man.relative_to(man.anchor)),
                                           "mount": "probe"}]})
    reg = _load_variant(tmp_path, add)
    got = [a for a in reg if a.id == "probe-arm"]
    assert got and got[0].artifacts[0].mount == "probe", "新臂没被识别 —— 加臂还是得改代码"


# --------------------------------------------------------------- 逐字节不变

@pytest.fixture(scope="module")
def rows():
    return P.load_params(PARAMS40)


def _build(row, arms=None):
    return P.build_task(row, capabilities=ALL_CAPS, **({"arms": arms} if arms else {}))


def test_builtin_two_arms_export_is_byte_identical(tmp_path, rows, monkeypatch):
    """内置两臂的出集**不受注册表里其它臂影响**。

    判据：把 doc / hint 从注册表里拿掉重建一次，与现注册表建的那次逐字节比。
    金丝雀是每次新生成的 nonce，所以这里把 `_token` / `_now` 钉住 ——
    不钉的话「两次出集不同」的原因是 nonce，而不是代码（这条会永远假红）。
    """
    row = next(r for r in rows if r["task_id"] == "s2-cor-01")

    def one(out: Path, registry):
        import itertools
        c = itertools.count(1)
        monkeypatch.setattr(P, "_token", lambda p: "GBC-{}-{:016x}".format(p, next(c)))
        monkeypatch.setattr(P, "_now", lambda: "2026-01-01T00:00:00+00:00")
        monkeypatch.setattr(S, "ARM_BY_ID", {a.id: a for a in registry})
        monkeypatch.setattr(S, "ARMS", tuple(a.id for a in registry if a.default))
        b = _build(row)
        assert b.ok, b.problems
        td = P.write_task(b, out / "ref", capabilities=ALL_CAPS)
        bd = P.export_task(td, out / "run")
        return {str(p.relative_to(bd)): _sha(p.read_bytes())
                for p in sorted(bd.rglob("*")) if p.is_file()}

    two_only = tuple(a for a in B.ARM_REGISTRY if a.id in ("strict", "open"))
    a = one(tmp_path / "a", two_only)
    b = one(tmp_path / "b", B.ARM_REGISTRY)
    assert a == b, ("注册表里多登记了非默认臂就改变了内置两臂的出集 —— "
                    f"差异 {sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))}")
    assert "arms/INSTRUCTION.doc.md" not in b, "非默认臂被默认渲染了 —— 那会改动每一份既有出集"


def test_task_yaml_instruction_keeps_arm_order(rows):
    row = next(r for r in rows if r["task_id"] == "s2-cor-01")
    b = _build(row)
    assert list(b.task["instruction"]) == list(S.ARMS) == ["strict", "open"], \
        "instruction 段的键序变了 —— task_sha256 会跟着变"


# --------------------------------------------------------------- 变体臂

@pytest.fixture(scope="module")
def four(rows, tmp_path_factory):
    """一份四臂的题（strict / open / doc / hint）。非默认臂要显式点名才渲染。"""
    row = next(r for r in rows if r["task_id"] == "s2-cor-01")
    b = P.build_task(row, capabilities=ALL_CAPS, arms=("strict", "open", "doc", "hint"))
    assert b.ok, b.problems
    root = tmp_path_factory.mktemp("four")
    td = P.write_task(b, root / "ref", capabilities=ALL_CAPS)
    bd = P.export_task(td, root / "run")
    return {"built": b, "task_dir": td, "bundle": bd, "root": root}


def test_hint_arm_renders_from_fallback_column_and_appends_its_text(four):
    b = four["built"]
    hint, open_ = b.arms["hint"], b.arms["open"]
    assert hint.slots == open_.slots, "变体臂的槽位序列必须与参照臂相同（E1 照查）"
    assert hint.text.startswith(open_.text.rstrip("\n")[:200]), \
        "变体臂没有落到 fallback 列 —— 它应当与 open 臂共用措辞"
    tail = (_REPO / "genetask" / "arms" / "hint.md").read_text(encoding="utf-8").strip("\n")
    assert hint.text.rstrip("\n").endswith(tail), "变体文本没被追加"
    assert hint.text != open_.text, "变体臂与参照臂逐字相同 —— 那它就不是一个臂"


def test_variant_arm_still_checked_on_e1_e2_c1(four, rows):
    """例外 ≠ 什么都不查。E1 槽位 / E2 欠定零泄漏 / C1 金丝雀三条照查。"""
    b = four["built"]
    pb = R.load_phrasebook(P.PHRASEBOOK)
    tok = b.task["canary"]["control_token"]
    base, hint = b.arms["open"], b.arms["hint"]
    assert R.check_arms(b.task, hint, base, pb, tok, names=("hint", "open"),
                        keep=R.VARIANT_KEEP) == [], "干净的变体臂不该有红"

    # ① 金丝雀被复制了一份 → C1 必红
    bad_c1 = copy.deepcopy(hint)
    bad_c1.text += f"\n校验串：{tok}\n"
    out = R.check_arms(b.task, bad_c1, base, pb, tok, names=("hint", "open"), keep=R.VARIANT_KEEP)
    assert any(x.startswith("C1 ") for x in out), out

    # ② 槽位少一个 → E1 必红
    bad_e1 = copy.deepcopy(hint)
    bad_e1.slots = bad_e1.slots[:-1]
    out = R.check_arms(b.task, bad_e1, base, pb, tok, names=("hint", "open"), keep=R.VARIANT_KEEP)
    assert any(x.startswith("E1 ") for x in out), out

    # ③ 例外确实是**例外**而不是「顺便也过了」：追加一段文字必然破 E11/E12b，
    #    不开例外时它是红的 —— 这条把「免掉了什么」变成可观测的。
    full = R.check_arms(b.task, hint, base, pb, tok, names=("hint", "open"))
    assert any(x.split(" ", 1)[0] in R.WAIVED_FOR_VARIANT for x in full), \
        f"变体臂在全规则下竟然全绿 —— 那说明「例外」这件事没有被测到：{full}"


def test_exceptions_are_recorded_in_equivalence_md(four):
    b, td = four["built"], four["task_dir"]
    assert set(b.arm_exceptions) == {"hint"}, b.arm_exceptions
    assert set(b.arm_exceptions["hint"]) == set(R.WAIVED_FOR_VARIANT)
    md = (td / "arms" / "equivalence.md").read_text(encoding="utf-8")
    assert "非默认臂" in md and "§6.6" in md, "例外没写进签字人看的那张表"
    for code in ("E11", "E12b"):
        assert code in md, f"{code} 被免掉了却没写在例外段里"
    assert "单列" in md, "主表上变体臂要单列这句话没进 equivalence.md"


def test_rule_codes_cover_what_check_arms_emits():
    """`RULE_CODES` 必须与 `check_arms` 真正发出的码一致 —— 漏一条 = 例外集合漏算一条。"""
    src = (_REPO / "genetask" / "render.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "check_arms")
    got = set()
    for n in ast.walk(fn):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "append" and n.args):
            continue
        a = n.args[0]
        parts = a.values if isinstance(a, ast.JoinedStr) else [a]
        head = parts[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            got.add(head.value.split(" ", 1)[0])
    assert got == set(R.RULE_CODES), \
        f"RULE_CODES 与实际发出的码不等：源码多 {sorted(got - set(R.RULE_CODES))}，" \
        f"表里多 {sorted(set(R.RULE_CODES) - got)}"


def test_variant_keep_matches_whole_codes_not_prefixes():
    """`E1` 按前缀会把 E10–E15 一起放行 —— 那时候「只查三条」实际查了九条。"""
    assert "E11" not in R.VARIANT_KEEP and "E11" in R.WAIVED_FOR_VARIANT
    b = R._Bad(R.VARIANT_KEEP)
    b.append("E11 假消息")
    b.append("E12b 假消息")
    b.append("E1 真消息")
    assert list(b) == ["E1 真消息"], f"整码匹配失效：{list(b)}"


# --------------------------------------------------------------- 工件投放

def test_doc_arm_files_are_byte_identical_to_v1():
    """文档臂是 geneprotocol_v1 的**子集副本** —— 两份漂开就等于两个不同的协议。"""
    v1 = _REPO / "ops" / "protocol" / "geneprotocol_v1"
    dc = _REPO / "ops" / "protocol" / "geneprotocol_v1_doc"
    m1 = json.loads((v1 / "MANIFEST.json").read_text(encoding="utf-8"))["artifacts"]
    md = json.loads((dc / "MANIFEST.json").read_text(encoding="utf-8"))["artifacts"]
    assert set(md) < set(m1), f"文档臂的工件不是 v1 的真子集：{sorted(md)} vs {sorted(m1)}"
    assert "validate_artifact.py" not in md, \
        "验证器进了文档臂 —— 那它就不是文档臂了，两条臂在测同一件事"
    for n, sha in md.items():
        assert m1[n] == sha, f"{n} 的 sha 在两份清单里不同"
        assert (dc / n).read_bytes() == (v1 / n).read_bytes(), f"{n} 两份副本逐字节不同"
        assert _sha((dc / n).read_bytes()) == sha, f"{n} 与自己清单记的 sha 不符"


@pytest.fixture
def provider(tmp_path):
    d = tmp_path / "provider"
    (d / "calendars").mkdir(parents=True)
    (d / "calendars" / "day.txt").write_text("2026-07-01\n2026-07-02\n", encoding="utf-8")
    (d / "instruments").mkdir()
    (d / "instruments" / "csi300.txt").write_text("SH600000\t2026-01-01\t2026-12-31\n", encoding="utf-8")
    lines = []
    for f in sorted(d.rglob("*")):
        if not f.is_file() or f.name in ("files.sha256", "manifest.json"):
            continue
        raw = f.read_bytes()
        lines.append(f"{_sha(raw)}  {len(raw)}  {f.relative_to(d)}")
    (d / "files.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return d


@pytest.fixture
def injected(four, provider, tmp_path, monkeypatch):
    """四个臂各注一次（干注入，不要 docker）。"""
    monkeypatch.setattr(pin, "PROVIDER_SHA256_ROOT", pin.provider_root_sha256(provider))
    spec = importlib.util.spec_from_file_location("_fz", _REPO / "ops" / "freeze_v10.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    from runner.c41 import subnets as SUB
    monkeypatch.setattr(SUB, "allocate", lambda **kw: {
        "task_subnet": "172.31.246.0/24", "egress_subnet": "172.31.247.0/24",
        "pool": "172.31.240.0/20", "docker_probe": "假分配", "reserved": [], "taken_at_alloc": []})
    bd = four["bundle"]
    assert P.pin_image_digest(bd, "sha256:" + "a" * 64) == []
    man = P.export_manifest(four["task_dir"], bd, check_export_result=[], frozen_ref=fz.frozen_ref())
    out = {}
    for arm in ("strict", "open", "doc", "hint"):
        r = INJ.inject(bd, arm, run_root=tmp_path / f"rr-{arm}", provider_root=provider,
                       config_id="cfg-a", model_upstream="", manifest=man,
                       expect_frozen_root=fz.frozen_ref()["root"], command='sh -c "true"',
                       require_docker=False, check_modes=False)
        out[arm] = r.run_dir / "work"
    return out


def test_doc_arm_injects_exactly_its_manifest(injected):
    """文档臂拿到的**恰好**是它自己清单里那几件 —— 不多不少（§6.2 的等号，泛化版）。"""
    bad = INJ.check_arm_diff(injected["doc"], injected["open"],
                             protocol=INJ.arm_files("doc"), arm="doc", base="open")
    assert bad == [], bad
    got = {str(p.relative_to(injected["doc"])) for p in injected["doc"].rglob("*") if p.is_file()}
    assert not any(x.endswith("validate_artifact.py") for x in got), \
        "验证器进了文档臂 —— 那两条臂就在测同一件事"
    for name in ("artifact_schema.json", "contract.json", "payload_depends_on.json", "task.json"):
        assert f"protocol/{name}" not in got, \
            f"逐题规则 {name} 进了文档臂 —— 它的 per_task_rules 是 false"


def test_strict_arm_is_unchanged_by_the_new_arms(injected):
    """加了 doc 臂之后 strict 臂拿到的东西**一个字节没变**。"""
    proto = dict(INJ.arm_files("strict"))
    got = {str(p.relative_to(injected["strict"])): _sha(p.read_bytes())
           for p in injected["strict"].rglob("*") if p.is_file()}
    for rel, sha in proto.items():
        assert got.get(rel) == sha, f"strict 臂的 {rel} 与清单不符"
    for name in ("artifact_schema.json", "contract.json", "payload_depends_on.json", "task.json"):
        assert f"protocol/{name}" in got, f"逐题规则 {name} 没进 strict 臂"


def test_baseline_arm_has_nothing_of_its_own(injected):
    """裸臂独有文件集必须为空 —— 等号的另一半。"""
    for arm in ("strict", "doc", "hint"):
        d = INJ.arm_diff(injected[arm], injected["open"])
        assert d["open_only"] == [], f"参照臂相对 {arm} 多出 {d['open_only']} —— 反向污染"
    d = INJ.arm_diff(injected["hint"], injected["open"])
    assert d["strict_only"] == [], f"指令变体臂多出了文件 {d['strict_only']} —— 它只该差一段题面"
    assert d["sha_differs"] == ["INSTRUCTION.md"], d["sha_differs"]


def test_p1_gate_accepts_registered_arms_and_refuses_typos(four, provider, tmp_path, monkeypatch):
    monkeypatch.setattr(pin, "PROVIDER_SHA256_ROOT", pin.provider_root_sha256(provider))
    with pytest.raises(P.PackError, match="P1 臂名"):
        INJ.inject(four["bundle"], "strcit", run_root=tmp_path / "rr", provider_root=provider,
                   config_id="cfg-a", model_upstream="", manifest={"task_id": "x"},
                   expect_frozen_root="x", command='sh -c "true"',
                   require_docker=False, check_modes=False)


def test_g3_classifies_every_registered_arm_instruction(four):
    """数据面文件分类（G3）必须认得**每一个**臂的题面。

    实测发现（出四臂 bundle 时踩到）：`EXPORTED_FILES` 里写死了 strict/open 两条，
    第三个臂的题面于是被判成「未归类的文件」，整份题导不出去。
    类别封闭是对的 —— 没归类的文件既不知道能不能出去、也不知道有没有植入金丝雀；
    **要跟着注册表走的是类别的内容，不是这条纪律**。
    """
    for a in B.ALL_ARMS:
        assert f"arms/INSTRUCTION.{a}.md" in P.EXPORTED_FILES, \
            f"{a} 臂的题面不在 EXPORTED_FILES 里 —— 出集时会被判「未归类」"
    assert P.check_private_files(four["task_dir"]) == [], \
        "四臂题目录过不了 G3/G1 自检"
    # 题面是**会出去**的那一类：不得含 gold_token（负例方向由 G3 自己查，这里钉住归类）
    assert not (P.EXPORTED_FILES & P.PRIVATE_ONLY_FILES), "同一个文件被归进两类"


def test_run_f02_a1_does_not_shadow_the_registry_module():
    """`ops/run_f02_a1.py::main` 里不许再 import 一次 registry。

    **为什么这条测试住在本文件里**：卡 4.1 的三臂真跑就是经这条路径发的，而它**恒红** ——
    `main()` 里那句局部 import 让 REG 成为局部名，只在「显式给了 --max-calls/--max-tokens」
    的分支里被赋值，于是**不给这两个参数就 UnboundLocalError**。
    卡 4.3 的交接原话恰恰是「把这两个参数整个删掉，让注入器按 stage 自动取档」——
    照着做的每一次真跑都会在拿到网关锁之后立刻死掉（本卡实测，排队 21 分钟换一个 traceback）。

    判据是 AST 不是 grep：注释里解释「为什么不要再 import」的那段话不该把自己判红。
    """
    src = (_REPO / "ops" / "run_f02_a1.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "main")
    shadowed = [n for n in ast.walk(fn)
                if isinstance(n, (ast.Import, ast.ImportFrom))
                and any((al.asname or al.name).split(".")[0] == "REG" for al in n.names)]
    assert not shadowed, ("main() 里又 import 了一次 registry —— REG 变成局部名，"
                          "不给 --max-calls/--max-tokens 时下面的 REG.by_id 会 UnboundLocalError")
    assert re.search(r"^from runner import registry as REG", src, re.M), \
        "顶层的 registry import 被删了"
