"""卡 4.3 验收闸门 T1–T18。

**做不了的那几条要显式记录，不是静默不写**：T5 / T10 / T12 / T15 需要真容器，
而两台机器目前都没有容器运行时（docker 未装；f02 敲 `lxc` 会触发 snap 安装）。
它们在这里是 `xfail(run=False)` + 一条说明，`test_container_gated_items_are_declared`
断言这份名单与实现状态一致 —— 缺检查要看得见，不能靠人记得。
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from copy import deepcopy

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from genetask import bundle as B                       # noqa: E402
from genetask import packager as P                     # noqa: E402
from genetask import pin                               # noqa: E402
from genetask import schema as S                       # noqa: E402
from runner import inject as INJ
from runner import provider_adapter as PA                       # noqa: E402
from runner.c41 import runner_core as RC               # noqa: E402

ALL_CAPS = {"n33_bars_open_amount_vwap": True, "s8_state_endpoint": True,
            "anchor_ladder_54": False}
PARAMS40 = _REPO / "genetask" / "params" / "v1.0-smoke40.yaml"

#: 需要真容器才能测的条目 —— 依赖未落地，**显式挂着**
CONTAINER_GATED = {
    "T5": "出向白名单：容器内连非白名单目标必须**快速拒绝**（<2s），不是超时",
    "T10": "容器内视角：/proc/mounts 无 nfs、ls /data 失败、import reference 抛错",
    "T12": "provider 等价：容器内 qlib 查询结果 == f01 冻结 provider 逐字节",
    "T15": "伪造身份头：网关 access_log 落的必须是 runner 真值（含同连接第二个请求）",
}


# --------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def rows():
    return P.load_params(PARAMS40)


@pytest.fixture(scope="module")
def exported(tmp_path_factory, rows):
    """造一份真 bundle + 通行证（f01 侧全流程）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_fz", _REPO / "ops" / "freeze_v10.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)

    root = tmp_path_factory.mktemp("f01")
    row = next(r for r in rows if r["task_id"] == "s1-cor-01")
    b = P.build_task(row, capabilities=ALL_CAPS)
    assert b.ok, b.problems
    task_dir = P.write_task(b, root / "reference", capabilities=ALL_CAPS)
    bundle = P.export_task(task_dir, root / "runner")
    # 钉 digest —— 这一步在真流程里也必须发生在出通行证之前（P4b 的门后实现者）
    assert P.pin_image_digest(bundle, "sha256:" + "a" * 64) == []
    ce = P.check_export(bundle, P.gold_sha_set(task_dir), b.task["canary"])
    assert ce == [], ce
    man = P.export_manifest(task_dir, bundle, check_export_result=ce,
                            frozen_ref=fz.frozen_ref())
    return {"task_dir": task_dir, "bundle": bundle, "manifest": man, "built": b,
            "frozen_root": fz.frozen_ref()["root"], "root": root}


def _write_filelist(root: Path) -> None:
    """按真 provider 的形状生成 `files.sha256`：`<sha256>  <size>  <relpath>` 每行一条。
    清单**不含自己**，也不含 manifest.json（与真树一致，2026-09-04 核实）。"""
    lines = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.name in ("files.sha256", "manifest.json"):
            continue
        b = f.read_bytes()
        lines.append(f"{hashlib.sha256(b).hexdigest()}  {len(b)}  {f.relative_to(root)}")
    (root / "files.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def provider(tmp_path):
    """一棵**假装是冻结 provider** 的树：带 `files.sha256`（真树就是靠它定根的），
    把 expect 设成它的现算根，这样正例可跑、负例仍真。"""
    d = tmp_path / "provider"
    (d / "calendars").mkdir(parents=True)
    (d / "calendars" / "day.txt").write_text("2026-07-01\n2026-07-02\n", encoding="utf-8")
    (d / "instruments").mkdir()
    (d / "instruments" / "csi300.txt").write_text("SH600000\t2026-01-01\t2026-12-31\n", encoding="utf-8")
    _write_filelist(d)
    return d


def _inject(exported, provider, arm, **kw):
    # check_modes=False：开发机上仓库本来就是 0755，守门自身的判别力由
    # ops/test_env_guard.py 单独测；这里测的是注入逻辑。
    return INJ.inject(exported["bundle"], arm,
                      run_root=kw.pop("run_root"), provider_root=provider,
                      config_id=kw.pop("config_id", "cfg-a"),
                      # 合成 config_id 不在 registry 里；这些用例测的是注入机制，不是模型通道。
                      model_upstream=kw.pop("model_upstream", ""),
                      manifest=exported["manifest"],
                      expect_frozen_root=kw.pop("expect_frozen_root", exported["frozen_root"]),
                      command=kw.pop("command", 'sh -c "true"'),
                      require_docker=False, check_modes=False, **kw)


def _patch_pin(monkeypatch, provider):
    """把冻结常量指到这棵测试 provider 树的现算根。
    改的是模块常量而不是默认参数 —— 见 pin.check_provider_pin 里那段自查。"""
    monkeypatch.setattr(pin, "PROVIDER_SHA256_ROOT", pin.provider_root_sha256(provider))


# --------------------------------------------------------------- IN-1（子网按运行分配）

def test_in1_allocation_reaches_compose_and_inject_json(exported, provider, tmp_path, monkeypatch):
    """**行为判据**：分配出来的网段必须同时出现在 compose 与 inject.json 里。

    只在源码里 grep 一个变量名不算 —— 那证明不了渲染时用的是它（D-20 已经犯过六次）。
    """
    from runner.c41 import subnets as SUB
    _patch_pin(monkeypatch, provider)
    fake = {"task_subnet": "172.31.246.0/24", "egress_subnet": "172.31.247.0/24",
            "pool": str(SUB.POOL), "docker_probe": "假分配（接线测试）",
            "reserved": [], "taken_at_alloc": []}
    monkeypatch.setattr(SUB, "allocate", lambda **kw: dict(fake))
    r = _inject(exported, provider, "strict", run_root=tmp_path / "rr")
    text = (r.run_dir / "compose.yml").read_text(encoding="utf-8")
    assert fake["task_subnet"] in text and fake["egress_subnet"] in text, \
        "compose 里用的不是分配到的网段"
    assert "172.31.240.0/24" not in text, "常量网段还在渲染结果里"
    inj = json.loads((r.run_dir / "inject.json").read_text(encoding="utf-8"))
    assert inj["subnets"] == fake, "分配依据没进 inject.json —— 事后无从复核撞网"


def test_in1_two_arms_do_not_share_a_subnet(exported, provider, tmp_path, monkeypatch):
    """两臂并发是常态。同一 runs 根下两次注入不许拿到重叠网段。"""
    import ipaddress

    from runner.c41 import subnets as SUB
    _patch_pin(monkeypatch, provider)
    handed: list[str] = []

    def alloc(**kw):
        a, b = SUB.pick_pair(taken=[ipaddress.ip_network(x) for x in handed])
        handed.extend([str(a), str(b)])
        return {"task_subnet": str(a), "egress_subnet": str(b), "pool": str(SUB.POOL),
                "docker_probe": "测试内分配", "reserved": [], "taken_at_alloc": list(handed)}

    monkeypatch.setattr(SUB, "allocate", alloc)
    rr = tmp_path / "rr"
    a = _inject(exported, provider, "strict", run_root=rr)
    b = _inject(exported, provider, "open", run_root=rr)
    ja = json.loads((a.run_dir / "inject.json").read_text(encoding="utf-8"))["subnets"]
    jb = json.loads((b.run_dir / "inject.json").read_text(encoding="utf-8"))["subnets"]
    for x in (ja["task_subnet"], ja["egress_subnet"]):
        for y in (jb["task_subnet"], jb["egress_subnet"]):
            assert not ipaddress.ip_network(x).overlaps(ipaddress.ip_network(y)), (ja, jb)


# --------------------------------------------------------------- T1

def test_t1_instruction_is_byte_identical(exported, provider, tmp_path, monkeypatch):
    _patch_pin(monkeypatch, provider)
    x = yaml.safe_load((exported["bundle"] / "task.yaml").read_text(encoding="utf-8"))
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    got = (r.run_dir / "work" / "INSTRUCTION.md").read_bytes()
    src = (exported["bundle"] / "arms" / "INSTRUCTION.open.md").read_bytes()
    assert got == src, "注入期改了字节 —— 渲染/变量替换/行尾归一化都算改"
    assert INJ._sha(got) == x["instruction"]["open"]["sha256"]


# --------------------------------------------------------------- T2（等号，不是包含号）

def test_t2_arm_diff_is_exactly_protocol_artifacts(tmp_path):
    """协议工件还没落地（status=pending），所以这里直接测**判据本身**的等号性质：
    ⊆ 会放行「少给 strict 一个」，等号不会。"""
    s, o = tmp_path / "s", tmp_path / "o"
    for d in (s, o):
        d.mkdir()
        (d / "INSTRUCTION.md").write_text("x" if d is s else "y", encoding="utf-8")
        (d / "S1.json").write_text("{}", encoding="utf-8")
    proto = {"PROTOCOL.md": "", "CHECKLIST.md": ""}
    (s / "PROTOCOL.md").write_text("p", encoding="utf-8")
    proto["PROTOCOL.md"] = INJ._sha_file(s / "PROTOCOL.md")
    proto["CHECKLIST.md"] = INJ._sha(b"c")
    bad = INJ.check_arm_diff(s, o, protocol=proto)
    assert any("≠ 协议工件集" in x for x in bad), \
        "少给 strict 一个协议工件必须红 —— 写成 ⊆ 时这里会绿（F8）"
    (s / "CHECKLIST.md").write_bytes(b"c")
    assert INJ.check_arm_diff(s, o, protocol=proto) == []
    (o / "EXTRA.md").write_text("e", encoding="utf-8")
    assert any("open 臂独有" in x for x in INJ.check_arm_diff(s, o, protocol=proto))


# --------------------------------------------------------------- T3

def test_t3_env_symmetric_difference_is_exactly_arm(exported, provider, tmp_path, monkeypatch):
    """env(strict) Δ env(open) == {"GENEBENCH_ARM"} —— 环境等价的断言。
    协议工件 released 之后这条才真的跑得起来（pending 时 strict 臂被门挡住）。"""
    _patch_pin(monkeypatch, provider)
    envs, works = {}, {}
    for arm in ("strict", "open"):
        r = _inject(exported, provider, arm, run_root=tmp_path / f"rr-{arm}")
        doc = yaml.safe_load((r.run_dir / "compose.yml").read_text(encoding="utf-8"))
        envs[arm] = doc["services"]["task"]["environment"]
        works[arm] = r.run_dir / "work"
    diff = {k for k in set(envs["strict"]) | set(envs["open"])
            if envs["strict"].get(k) != envs["open"].get(k)}
    # 规格 §6.3 原写「Δ == {GENEBENCH_ARM}」。加 GENEBENCH_RUN_ID 之后这条要更准：
    # run_id 里**结构性地**含 arm（`<task>.<arm>.<cfg>.rNN`），所以它两臂必然不同。
    # 判据因此变成两条：① 差异集合恰是这两个；
    # ② **RUN_ID 的差异只能来自 arm 那一段** —— 把 arm 换掉之后必须逐字相等，
    #    否则 run_id 就携带了额外的臂间差异（比如 seq 或 config 被按臂改了）。
    assert diff == {"GENEBENCH_ARM", "GENEBENCH_RUN_ID"}, f"环境等价被破：差异 {diff}"
    norm = {a: envs[a]["GENEBENCH_RUN_ID"].replace(f".{a}.", ".<ARM>.")
            for a in ("strict", "open")}
    assert norm["strict"] == norm["open"], \
        f"RUN_ID 除 arm 之外还有差异：{norm} —— 它携带了额外的臂间信息"
    assert envs["strict"]["GENEBENCH_CONFIG_ID"] == envs["open"]["GENEBENCH_CONFIG_ID"]
    assert envs["strict"]["GENEBENCH_TASK_ID"] == envs["open"]["GENEBENCH_TASK_ID"]


def test_t2_arm_diff_equals_protocol_artifacts_end_to_end(exported, provider, tmp_path,
                                                          monkeypatch):
    """§6.2 的**等号**判据，端到端。协议工件 released 之后才跑得了。

    差异必须**精确等于**协议工件集：⊆ 会放行「少给 strict 一个」，
    那不是隔离失败而是**干预失败** —— 协议臂静默退化成半个裸臂（F8）。
    """
    _patch_pin(monkeypatch, provider)
    works = {}
    for arm in ("strict", "open"):
        r = _inject(exported, provider, arm, run_root=tmp_path / f"rr2-{arm}")
        works[arm] = r.run_dir / "work"
    proto = {f"{INJ.PROTOCOL_REL}/{k}" for k in INJ.protocol_artifacts()}
    d = INJ.arm_diff(works["strict"], works["open"])
    strict_only = set(d["strict_only"])
    assert proto <= strict_only, f"strict 臂缺协议工件 {proto - strict_only}"
    # strict 臂独有的东西**只能是** protocol/ 下的（封闭清单 + 逐题规则 JSON）
    assert all(x.startswith(f"{INJ.PROTOCOL_REL}/") for x in strict_only), \
        f"strict 臂多出了协议目录之外的东西：{sorted(x for x in strict_only if '/' not in x)}"
    for name in ("artifact_schema.json", "contract.json", "payload_depends_on.json", "task.json"):
        assert f"{INJ.PROTOCOL_REL}/{name}" in strict_only, f"逐题规则 {name} 没进 strict 臂"
    # validator 在容器里真的能跑
    v = works["strict"] / INJ.PROTOCOL_REL / "validate_artifact.py"
    assert v.is_file() and v.read_text(encoding="utf-8").startswith("#!")
    assert d["open_only"] == [], f"裸臂多出 {d['open_only']} —— 反向污染"
    assert d["sha_differs"] == ["INSTRUCTION.md"], \
        f"两臂同名文件里 sha 不同的应恰好只有 INSTRUCTION.md，实际 {d['sha_differs']}"


def test_t3_env_diff_helper_compares_values_not_just_keys():
    a = {"GENEBENCH_ARM": "strict", "GENEBENCH_CONFIG_ID": "cfg-a"}
    b = {"GENEBENCH_ARM": "open", "GENEBENCH_CONFIG_ID": "cfg-b"}
    diff = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    assert diff == {"GENEBENCH_ARM", "GENEBENCH_CONFIG_ID"}, \
        "只比键集会让 config_id 不同也过 —— 环境等价断言必须比值"


# --------------------------------------------------------------- T4（provider 现算）

def test_t4_provider_pin_is_computed_not_read(provider, tmp_path):
    good = pin.provider_root_sha256(provider)
    assert pin.check_provider_pin(provider, expect=good) == []
    # ① 改一个字节
    f = provider / "calendars" / "day.txt"
    before = f.read_bytes()
    f.write_bytes(before + b"2026-07-03\n")
    assert before != f.read_bytes(), "突变空转 —— 判别力测试会恒绿"
    assert pin.check_provider_pin(provider, expect=good), "改一个字节必须红"
    f.write_bytes(before)
    # ② 删根文件
    f.unlink()
    assert pin.check_provider_pin(provider, expect=good), "缺文件必须红，不是 skip（F1）"
    f.write_bytes(before)
    # ③ 目录不存在
    assert pin.check_provider_pin(tmp_path / "nope", expect=good)
    # ④ 空树
    (tmp_path / "empty").mkdir()
    assert pin.check_provider_pin(tmp_path / "empty", expect=good)
    # ⑤ **F7 的真形态**：改一个文件的内容而**不动清单** —— 根 hash（= 清单的 sha256）
    #    一个字都不变，只有逐条现算才抓得到。这是「读记录值等于没查」的最硬实例。
    tampered = provider / "instruments" / "csi300.txt"
    orig = tampered.read_bytes()
    tampered.write_bytes(orig + b"SH600001\t2026-01-01\t2026-12-31\n")
    assert pin.provider_root_sha256(provider) == good, \
        "根 hash 不该变 —— 它算的是清单文件，而清单没动"
    bad = pin.check_provider_pin(provider, expect=good)
    assert any("内容与清单不符" in x for x in bad), \
        f"改内容不动清单必须被逐条现算抓到，实际 {bad}"
    tampered.write_bytes(orig)
    assert pin.check_provider_pin(provider, expect=good) == []

    # ⑥ 往树里塞一个清单外的文件 —— 多出来的文件也是改动
    sneak = provider / "instruments" / "sneak.txt"
    sneak.write_text("x", encoding="utf-8")
    assert any("树里有而清单里没有" in x
               for x in pin.check_provider_pin(provider, expect=good))
    sneak.unlink()


def test_provider_root_is_the_filelist_sha_not_a_homegrown_walk(provider):
    """**现算要算同一件东西**（2026-09-04 实测纠正）。

    冻结值 `54fdda39…` 是 provider 自带 `files.sha256` **这个文件**的 sha256（卡 2.1a 的算法）。
    我第一版自己定义了「relpath\0sha256 排序拼接」，对真 provider 算出 `c8506c5c…` ——
    现算是现算了，算的却不是同一件东西，于是这道门**永远红**。
    而一条恒红的门，下一个人会把 expect 改掉或跳过 —— 门就废了。
    """
    import hashlib as _h
    fl = provider / pin.PROVIDER_FILELIST
    assert pin.provider_root_sha256(provider) == _h.sha256(fl.read_bytes()).hexdigest()
    fl.unlink()
    with pytest.raises(FileNotFoundError, match="逐文件清单"):
        pin.provider_root_sha256(provider)


# --------------------------------------------------------------- T6（金丝雀按格式正则）

def test_t6_canary_by_regex_not_plaintext(exported):
    bundle = exported["bundle"]
    texts = {str(p.relative_to(bundle)): p.read_text(encoding="utf-8", errors="replace")
             for p in bundle.rglob("*") if p.is_file()}
    g = [f for f, t in texts.items() if re.search(r"GBC-G-[0-9a-f]{16}", t)]
    assert g == [], f"GBC-G-（gold）必须全树零命中，实际 {g}"
    x = [f for f, t in texts.items() if re.search(r"GBC-X-[0-9a-f]{16}", t)]
    assert x == ["task.yaml"], f"GBC-X- 只许在 task.yaml，实际 {x}"
    for arm in ("strict", "open"):
        n = len(re.findall(r"GBC-C-[0-9a-f]{16}", texts[f"arms/INSTRUCTION.{arm}.md"]))
        assert n == 1, f"{arm} 臂控制串出现 {n} 次"
    # 「零命中 = 扫描器坏了」的非空证明：同一个扫描器必须能在造出来的样本上命中
    # 串**运行时拼**，不写成字面量：这个文件要随发布树发出去，而落地即扫的那道门
    # （runner/f02/answer_plane_guard）扫的是**字节**，不认「这是一句测试」。
    # 与 ops/test_env.py 对 key 形态的处置同一条口径。
    probe = "x " + "GBC-G-" + "0123456789abcdef" + " y"
    assert re.search(r"GBC-G-[0-9a-f]{16}", probe), "扫描器本身是坏的"


# --------------------------------------------------------------- T7 / T8（子网与端口）

def test_t7_subnets_avoid_forbidden_ranges():
    import ipaddress
    forbidden = [ipaddress.ip_network(x) for x in ("10.42.0.0/16", "10.43.0.0/16",
                                                   "10.88.0.0/16", "10.40.0.0/13")]
    for net in (RC.TASK_SUBNET, RC.EGRESS_SUBNET):
        n = ipaddress.ip_network(net)
        for f in forbidden:
            assert not n.overlaps(f), f"{net} 与 {f} 重叠"
    # 反例：10.40.0.0/13 覆盖 10.42/16 —— 字符串前缀比对抓不到它
    assert ipaddress.ip_network("10.42.0.0/16").overlaps(ipaddress.ip_network("10.40.0.0/13"))
    assert not str(ipaddress.ip_network("10.42.0.0/16")).startswith("10.40.")


def test_t8_no_ports_in_v1(exported, provider, tmp_path, monkeypatch):
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    doc = yaml.safe_load((r.run_dir / "compose.yml").read_text(encoding="utf-8"))
    for name, svc in doc["services"].items():
        assert not svc.get("ports"), f"v1 下 {name} 不许有 ports（L-6），实际 {svc.get('ports')}"
    text = (r.run_dir / "compose.yml").read_text(encoding="utf-8")
    assert RC.lint_compose(text) == []
    bad = RC.lint_compose(text.replace("services:", 'services:\n  x:\n    ports:\n      - "8080:8080"\n', 1))
    assert bad, "裸端口映射必须被 lint 拦下"


# --------------------------------------------------------------- T9

def test_t9_dockerfile_lint_and_placeholder_digest(exported, provider, tmp_path, monkeypatch):
    _patch_pin(monkeypatch, provider)
    df = exported["bundle"] / "image" / "Dockerfile"
    text = df.read_text(encoding="utf-8")
    assert B.lint_dockerfile(text) == []
    assert B.IMAGE_DIGEST_PLACEHOLDER not in text, "fixture 已钉 digest"
    # 把 digest 退回占位 → P4b 必须红（改了 bundle 也会先被 P3 抓到，所以直接测 P4b 的判据）
    assert B.IMAGE_DIGEST_PLACEHOLDER in text.replace("sha256:" + "a" * 64,
                                                      B.IMAGE_DIGEST_PLACEHOLDER)


def test_pin_image_digest_refuses_bad_input(exported):
    assert P.pin_image_digest(exported["bundle"], "sha256:zz") , "形状不对必须红"
    assert P.pin_image_digest(exported["bundle"], B.IMAGE_DIGEST_PLACEHOLDER), \
        "把 digest 钉成占位值本身等于没钉"


# --------------------------------------------------------------- T11（AST 依赖闭包）

def _import_closure(mod_path: Path, *, seen=None) -> set[str]:
    """按 AST 递归展开仓库内模块的 import 图 —— grep 字面量抓不到间接依赖。"""
    seen = seen if seen is not None else set()
    names: set[str] = set()
    tree = ast.parse(mod_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
            mods = [node.module]
        else:
            continue
        for m in mods:
            f = _REPO / (m.replace(".", "/") + ".py")
            if f.is_file() and str(f) not in seen:
                seen.add(str(f))
                names |= _import_closure(f, seen=seen)
    return names


@pytest.mark.parametrize("mod", [
    "genetask/pin.py", "genetask/bundle.py", "runner/inject.py", "runner/run_loop.py",
    "runner/provider_adapter.py",
    # 卡 4.2 的采集器五件：跑在 f02，同一条纪律
    "runner/c42/failure_modes.py", "runner/c42/harvest.py", "runner/c42/origin.py",
    "runner/c42/identity.py", "runner/c42/visibility.py", "runner/c42/emission.py",
])
def test_t11_execution_plane_modules_never_reach_reference(mod):
    closure = _import_closure(_REPO / mod)
    assert "reference" not in closure, \
        f"{mod} 的 import 闭包里有 reference —— 在 f02 上 import 它会把答案面拖上执行面"
    r = subprocess.run([sys.executable, "-c",
                        f"import sys; sys.path.insert(0, {str(_REPO)!r}); "
                        f"import {mod[:-3].replace('/', '.')}; "
                        f"print('reference' in sys.modules)"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]
    assert r.stdout.strip() == "False", f"{mod} 实际拉起了 reference"


def test_t11_arms_constant_does_not_drift():
    assert B.ARMS == S.ARMS, "执行面副本与 schema.ARMS 漂了 —— 两份常量必须有断言钉住"


# --------------------------------------------------------------- T13（通行证）

def test_t13_manifest_catches_one_byte_change(exported, provider, tmp_path, monkeypatch):
    _patch_pin(monkeypatch, provider)
    f = exported["bundle"] / "work" / "S1.json"
    before = f.read_bytes()
    f.write_bytes(before + b"\n")
    assert before != f.read_bytes(), "突变空转 —— 判别力测试会恒绿"
    try:
        bad = B.check_manifest(exported["bundle"], exported["manifest"],
                               expect_frozen_root=exported["frozen_root"])
        assert any("sha256 与通行证不符" in x for x in bad)
        with pytest.raises(P.PackError, match=r"\[P3\]"):
            _inject(exported, provider, "open", run_root=tmp_path / "rr")
    finally:
        f.write_bytes(before)
    assert B.check_manifest(exported["bundle"], exported["manifest"],
                            expect_frozen_root=exported["frozen_root"]) == []


def test_t13_export_manifest_refuses_red_bundle(exported):
    with pytest.raises(P.PackError, match="拒绝出通行证"):
        P.export_manifest(exported["task_dir"], exported["bundle"],
                          check_export_result=["G4 假装这里有一条红"],
                          frozen_ref={"root": "x" * 64})


def test_t13_manifest_catches_extra_and_missing_files(exported, tmp_path):
    extra = exported["bundle"] / "work" / "sneak.txt"
    extra.write_text("x", encoding="utf-8")
    try:
        bad = B.check_manifest(exported["bundle"], exported["manifest"],
                               expect_frozen_root=exported["frozen_root"])
        assert any("多文件" in x for x in bad), "多一个文件必须红 —— 文件集是**精确相等**"
    finally:
        extra.unlink()


# --------------------------------------------------------------- 冻结核验（裁定 2026-09-04）

def test_frozen_manifest_gate_rejects_other_version(exported, provider, tmp_path, monkeypatch):
    _patch_pin(monkeypatch, provider)
    assert exported["manifest"]["frozen_manifest"]["root"] == exported["frozen_root"]
    bad = B.check_manifest(exported["bundle"], exported["manifest"],
                           expect_frozen_root="0" * 64)
    assert any("frozen_manifest_mismatch" in x for x in bad)
    with pytest.raises(P.PackError, match="frozen_manifest_mismatch"):
        _inject(exported, provider, "open", run_root=tmp_path / "rr",
                expect_frozen_root="0" * 64)


def test_frozen_manifest_gate_rejects_missing_ref(exported, provider, tmp_path, monkeypatch):
    _patch_pin(monkeypatch, provider)
    m = dict(exported["manifest"]); m["frozen_manifest"] = {}
    bad = B.check_manifest(exported["bundle"], m, expect_frozen_root=exported["frozen_root"])
    assert any("没记冻结清单根" in x for x in bad), \
        "通行证不记冻结引用时必须红 —— 否则老 bundle 会绕过这道门"


def test_frozen_manifest_is_recorded_in_inject_json(exported, provider, tmp_path, monkeypatch):
    """遥测要记 frozen_manifest 版本（进结果库，是论文里任务集版本的出处）。"""
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    inj = json.loads((r.run_dir / "inject.json").read_text(encoding="utf-8"))
    assert inj["frozen_manifest"]["root"] == exported["frozen_root"]
    assert inj["frozen_manifest"]["set_id"] == "v1.0-smoke"


# --------------------------------------------------------------- T14（重跑不覆盖）

def test_t14_two_seqs_produce_two_run_dirs(exported, provider, tmp_path, monkeypatch):
    _patch_pin(monkeypatch, provider)
    rr = tmp_path / "rr"
    a = _inject(exported, provider, "open", run_root=rr, seq=1)
    b = _inject(exported, provider, "open", run_root=rr, seq=2)
    assert a.run_dir != b.run_dir and a.run_dir.is_dir() and b.run_dir.is_dir()
    # 裁定 ⑮：run_id 末尾多了 `@<machine_id>`，seq 段不再在字符串末尾。
    assert INJ.split_run_id(a.run_id)[0].endswith(".r01")
    assert INJ.split_run_id(b.run_id)[0].endswith(".r02")
    with pytest.raises(P.PackError, match="不覆盖"):
        _inject(exported, provider, "open", run_root=rr, seq=1)


def test_run_id_and_compose_project_shapes():
    """裁定 ⑮（2026-09-10）：`run_id` 末尾带机器标识 —— 两台机器按同一份清单跑出来的 run
    不再逐字同名（否则结果包合并时是「同主键内容不同」，只能留一份）。

    原来这里钉的是 `"s1-cor-01.open.cfg-a.r03"` 这个字面量。**判别力一条没少**：前四段仍然
    逐字钉死，机器段单独钉形状与来源（`machine_id()` 那一份，不是随手拼的）。
    """
    rid = INJ.run_id("s1-cor-01", "open", "cfg-a", 3)
    base, machine = INJ.split_run_id(rid)
    assert base == "s1-cor-01.open.cfg-a.r03"
    assert machine == INJ.machine_id() and INJ.MACHINE_ID_RE.match(machine)
    assert rid == f"s1-cor-01.open.cfg-a.r03{INJ.MACHINE_SEP}{INJ.machine_id()}"
    proj = INJ.compose_project(rid)
    assert "." not in proj and INJ.MACHINE_SEP not in proj \
        and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", proj), \
        "compose 项目名带 . 或 @ 会被 compose 直接拒"


# --------------------------------------------------------------- T16/T17（TK-1 三条判据）

def test_t16_task_service_has_exactly_one_bind_to_this_run_work(exported, provider, tmp_path, monkeypatch):
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    doc = yaml.safe_load((r.run_dir / "compose.yml").read_text(encoding="utf-8"))
    vols = doc["services"]["task"].get("volumes") or []
    assert len(vols) == 1, f"任务服务的 bind 挂载数必须恰为 1，实际 {vols}"
    src = Path(str(vols[0]).split(":")[0])
    assert src.resolve() == (r.run_dir / "work").resolve(), \
        "必须 realpath 比对 —— 指向 work/ 的符号链接长得完全正确，字面量比会当场放行"


def test_t17_mount_is_under_runs_root_and_not_a_data_root(exported, provider, tmp_path, monkeypatch):
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    mnt = (r.run_dir / "work").resolve()
    runs_root = (tmp_path / "rr" / "runs").resolve()
    assert runs_root in mnt.parents
    data_roots = [Path("/data/shared"), Path("/data/market_lake_f02"),
                  Path("/data/genebench_runner/manifests"),
                  Path("/data/genebench_runner/provider")]
    for d in data_roots:
        assert d != mnt and d not in mnt.parents
    # 负例：run_root 落在数据根下时，判据 1 仍绿而本条必须红
    fake = Path("/data/market_lake_f02/runs/x/work")
    assert Path("/data/market_lake_f02") in fake.parents


def test_t18_three_bind_syntaxes_are_all_linted():
    """短语法 / type:bind 长语法 / named volume + driver_opts.device —— 三种都要被 lint 报。"""
    base = RC.render_compose("t", "open")
    a = base.replace("      - {}:/task".format(str(RC.task_dir("t") / "work")),
                     "      - /etc:/etc:ro", 1)
    long_syntax = base.replace(
        "    volumes:\n      - {}:/task".format(str(RC.task_dir("t") / "work")),
        "    volumes:\n      - type: bind\n        source: /etc\n        target: /etc", 1)
    named = base + ("volumes:\n  sneak:\n    driver_opts:\n      type: none\n"
                    "      device: /data/shared\n      o: bind\n")
    results = {"短语法": RC.lint_compose(a), "长语法": RC.lint_compose(long_syntax),
               "named+device": RC.lint_compose(named)}
    silent = [k for k, v in results.items() if not v]
    assert not silent, (f"这些 bind 写法当前**沉默**：{silent} —— "
                        f"沉默必须被观测到并记录，不能被推断为「大概能拦住」。"
                        f"结果全文：{results}")


# --------------------------------------------------------------- 挂起项的可见性

def test_container_gated_items_are_declared():
    """做不了的检查必须**看得见**。这条断言名单非空且每条都有理由 ——
    名单为空却仍没有容器，说明有人把挂起项悄悄删了。"""
    assert set(CONTAINER_GATED) == {"T5", "T10", "T12", "T15"}
    for k, why in CONTAINER_GATED.items():
        assert len(why) > 10, k
    # **不**拿「当前机器有没有 docker」当触发条件：开发机（Mac）有 docker，
    # 而执行面 f02 没有 —— 用本机状态判会在开发机上假红、在 f02 上假绿。
    # 解锁条件写在 tickets 里，由人在 f02 装上运行时之后来改这份名单。
    assert (_REPO / "ops" / "tickets.md").read_text(encoding="utf-8").count("容器运行时") >= 1, \
        "解锁条件必须在 tickets 里有落点，否则这四条会被永远忘掉"


@pytest.mark.parametrize("tid", sorted(CONTAINER_GATED))
def test_container_gated_placeholder(tid):
    pytest.skip(f"{tid} 需要真容器：{CONTAINER_GATED[tid]}（两台目前都没有容器运行时）")


def test_protocol_gate_blocks_strict_arm_when_artifacts_are_missing(exported, provider,
                                                                    tmp_path, monkeypatch):
    """**永久断言**：干预内容缺失时 strict 臂必红，实验不得静默降级成双裸臂。

    status 从 pending 翻到 released 之后，这条断言的**形式**从「pending 必红」
    变成「清单为空或 status 非 released 必红」，**语义不变**。
    """
    _patch_pin(monkeypatch, provider)
    assert INJ.protocol_status() == "released", "已发布"
    assert INJ.protocol_artifacts(), "清单非空"
    monkeypatch.setattr(INJ, "protocol_status", lambda: "pending")
    with pytest.raises(P.PackError, match="协议工件"):
        _inject(exported, provider, "strict", run_root=tmp_path / "rr-a")
    monkeypatch.setattr(INJ, "protocol_status", lambda: "released")
    monkeypatch.setattr(INJ, "protocol_artifacts", dict)
    with pytest.raises(P.PackError, match="协议工件"):
        _inject(exported, provider, "strict", run_root=tmp_path / "rr-b")


# --------------------------------------------------------------- T16 的五个负例（§8.1）

def _compose_with_task_volumes(vols: list[str], workdir: Path) -> str:
    base = RC.format_compose(
        task_id="t", run_id="t.open.cfg-a.r01", project="gb-t-open-cfg-a-r01",
        arm="open", image="python:3.11-alpine", command='sh -c "true"',
        config_id="cfg-a", task_subnet=RC.TASK_SUBNET, egress_subnet=RC.EGRESS_SUBNET,
        gateway=RC.GATEWAY, proxy_py="/x/egress_proxy.py", h11_dir="/x/h11",
        workdir=str(workdir), logdir=str(workdir.parent / "log"))
    block = "\n".join(f"      - {v}" for v in vols)
    return base.replace(f"      - {workdir}:/task", block, 1)


@pytest.mark.parametrize("case", ["父目录", "同级另一个 run", "符号链接", "绕路写法", "多挂一个"])
def test_t16_five_negatives_must_all_be_red(tmp_path, case):
    runs = tmp_path / "runs"
    work = runs / "r01" / "work"
    work.mkdir(parents=True)
    (runs / "r02" / "work").mkdir(parents=True)
    if case == "父目录":
        vols = [f"{runs / 'r01'}:/task"]
    elif case == "同级另一个 run":
        vols = [f"{runs / 'r02' / 'work'}:/task"]
    elif case == "符号链接":
        link = tmp_path / "link_to_work"
        link.symlink_to(work)
        vols = [f"{link}:/task"]
    elif case == "绕路写法":
        vols = [f"{runs / 'r01' / 'work' / '..' / 'work'}:/task"]
    else:
        vols = [f"{work}:/task", "/etc:/etc:ro"]
    text = _compose_with_task_volumes(vols, work)
    bad = RC.lint_compose(text, expect_workdir=work, runs_root=runs)
    assert bad, f"负例「{case}」必须红"
    assert any(x.startswith("L-5a") for x in bad), f"必须由 L-5a 拦下，实际 {bad}"


def test_t16_symlink_would_pass_a_literal_comparison(tmp_path):
    """证明「必须 realpath」这条不是多余的：符号链接在字面量比下长得完全正确。"""
    runs = tmp_path / "runs"; work = runs / "r01" / "work"; work.mkdir(parents=True)
    link = tmp_path / "link_to_work"; link.symlink_to(work)
    assert str(link) != str(work)                    # 字面量不同
    assert link.resolve() == work.resolve()          # realpath 相同
    text = _compose_with_task_volumes([f"{link}:/task"], work)
    bad = RC.lint_compose(text, expect_workdir=work, runs_root=runs)
    assert any("不是规范路径" in x for x in bad), \
        ("符号链接必须红：realpath 相等只在**检查时刻**成立，"
         f"链接可以在容器启动前被改指向别处。实际 {bad}")


def test_run_root_with_symlink_still_injects(exported, provider, tmp_path, monkeypatch):
    """真机上 run_root 常带一层符号链接（macOS 的 /tmp、生产的挂载点）。
    注入器必须自己 resolve —— 否则 L-5a 会拿注入器自己写的路径判红，拦住自己人。
    pytest 的 tmp_path 已经是解析过的，所以这条必须**显式造一个**符号链接。"""
    _patch_pin(monkeypatch, provider)
    real = tmp_path / "real_runs"
    real.mkdir()
    link = tmp_path / "linked_runs"
    link.symlink_to(real)
    r = _inject(exported, provider, "open", run_root=link)
    assert r.run_dir.is_dir()
    text = (r.run_dir / "compose.yml").read_text(encoding="utf-8")
    assert str(link) not in text, "compose 里不该留下非规范路径"
    assert str(real.resolve()) in text


def test_env_task_id_is_the_real_task_id_not_run_id(exported, provider, tmp_path, monkeypatch):
    """`GENEBENCH_TASK_ID` 进 `x-genebench-task-id` 头，而网关 access_log 的切片键、
    scorer 的切片、N-36 的 config_id 核对全挂在它上面。写成 run_id 会让切片**空** ——
    而空切片看起来就是「这次运行什么都没请求」，是 N-36 修过的同一个形态。"""
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr", config_id="cfg-a", seq=7)
    doc = yaml.safe_load((r.run_dir / "compose.yml").read_text(encoding="utf-8"))
    env = doc["services"]["task"]["environment"]
    assert env["GENEBENCH_TASK_ID"] == exported["manifest"]["task_id"] == "s1-cor-01"
    assert env["GENEBENCH_RUN_ID"] == r.run_id                      # 注入器与 compose 同一个值
    assert INJ.split_run_id(r.run_id)[0] == "s1-cor-01.open.cfg-a.r07"   # 裁定 ⑮：末尾多了机器段
    assert env["GENEBENCH_ARM"] == "open" and env["GENEBENCH_CONFIG_ID"] == "cfg-a"
    assert doc["name"] == INJ.compose_project(r.run_id) \
        == f"gb-s1-cor-01-open-cfg-a-r07-{INJ.machine_id()}"     # 裁定 ⑮：机器段跟着进项目名


# ===================================================== 红队 2026-09-04 补的判别力

def test_frozen_gate_cannot_be_disabled_by_forgetting_a_parameter(exported, provider, tmp_path,
                                                                  monkeypatch):
    """用户点名的那道门原先是 `expect_frozen_root: str | None = None` —— 忘了传就等于
    整道门消失，而"忘了传"没有任何提示。现在它是必填参数，放弃核验必须**显式**写哨兵。"""
    import inspect
    for fn in (B.check_manifest, INJ.inject):
        prm = inspect.signature(fn).parameters["expect_frozen_root"]
        assert prm.default is inspect.Parameter.empty, \
            f"{fn.__name__} 的 expect_frozen_root 有默认值 —— 门可以靠「忘了传」关掉"
    prm = inspect.signature(P.export_manifest).parameters["frozen_ref"]
    assert prm.default is inspect.Parameter.empty
    with pytest.raises(P.PackError, match="frozen_ref 必须带 root"):
        P.export_manifest(exported["task_dir"], exported["bundle"],
                          check_export_result=[], frozen_ref={})
    # 显式放弃仍然可以，但要写出来
    assert B.check_manifest(exported["bundle"], exported["manifest"],
                            expect_frozen_root=B.SKIP_FROZEN_CHECK) == []


def test_g4_whitelist_comes_from_the_constant_not_the_manifest(exported):
    """通行证跟着 bundle 一起搬。白名单读它自报的字段 = 让被查的一方定义什么叫合规。"""
    tampered = deepcopy(exported["manifest"])
    tampered["allowed_prefixes"] = list(B.X_ALLOWED_PREFIXES) + ["secret/"]
    sneak = exported["bundle"] / "secret"
    sneak.mkdir()
    (sneak / "gold.txt").write_text("x", encoding="utf-8")
    tampered["files"][str((sneak / "gold.txt").relative_to(exported["bundle"]))] = \
        B._sha(b"x")
    try:
        bad = B.check_manifest(exported["bundle"], tampered,
                               expect_frozen_root=exported["frozen_root"])
        assert any("不在允许集" in x for x in bad), "放宽白名单的通行证必须被顶回去"
        assert any("与本机常量不符" in x for x in bad)
    finally:
        shutil.rmtree(sneak)


def test_image_comes_from_the_dockerfile_not_a_call_parameter(exported, provider, tmp_path,
                                                              monkeypatch):
    """容器实际跑的镜像必须来自 P4/P4b 钉住的那份 Dockerfile。
    原先 image 是 inject 的默认关键字参数（裸 tag），与 digest 检查毫无关系，
    而且调用方能给两臂传不同的值 —— 没有任何一条规则会红。"""
    import inspect
    assert "image" not in inspect.signature(INJ.inject).parameters, \
        "image 不该是注入器的参数 —— 它得从 Dockerfile 取"
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    doc = yaml.safe_load((r.run_dir / "compose.yml").read_text(encoding="utf-8"))
    df = (exported["bundle"] / "image" / "Dockerfile").read_text(encoding="utf-8")
    from_line = re.search(r"(?im)^FROM\s+(\S+)", df).group(1)
    assert doc["services"]["task"]["image"] == from_line
    assert "@sha256:" in doc["services"]["task"]["image"], "必须带 digest"


def test_p8_recheck_is_not_dead_code(exported, provider, tmp_path, monkeypatch):
    """P8（复制之后重核）原先整段删掉全套测试仍绿。这里在**复制之后**动手脚，
    只有 P8 能抓到 —— P3 那时候已经跑完了。"""
    _patch_pin(monkeypatch, provider)
    real = shutil.copyfile

    def sabotage(src, dst, *a, **kw):
        out = real(src, dst, *a, **kw)
        d = Path(dst)
        if d.name == "INSTRUCTION.md":          # 题面复制完之后，往同目录塞一个文件
            (d.parent / "sneak.txt").write_text("injected after P3", encoding="utf-8")
        return out

    monkeypatch.setattr(shutil, "copyfile", sabotage)
    with pytest.raises(P.PackError) as ei:
        _inject(exported, provider, "open", run_root=tmp_path / "rr")
    assert "[P8]" in str(ei.value), f"只有 P8 能抓到复制后的改动，实际 {str(ei.value)[:200]}"


def test_tk1_criterion_2_is_exercised_by_lint(tmp_path):
    """TK-1 判据 2（挂载点必须在 runs_root 之下、且不落在任何数据根内）
    原先两个分支都能删掉而测试仍绿 —— T17 从头到尾没调用过 lint_compose。"""
    runs = tmp_path / "runs"
    work = runs / "r01" / "work"
    work.mkdir(parents=True)
    text = _compose_with_task_volumes([f"{work}:/task"], work)
    assert RC.lint_compose(text, expect_workdir=work, runs_root=runs) == []
    # 分支 a：挂载点不在 runs_root 之下
    other = tmp_path / "elsewhere" / "work"
    other.mkdir(parents=True)
    bad_a = RC.lint_compose(_compose_with_task_volumes([f"{other}:/task"], other),
                            expect_workdir=other, runs_root=runs)
    assert any("不在 runs 根" in x for x in bad_a), f"实际 {bad_a}"
    # 分支 b：挂载点落在数据根内（判据 1 对它是绿的 —— 路径可以既精确相等又落在湖里）
    data_root = Path(RC.DATA_ROOTS[0])
    fake = data_root / "runs" / "r01" / "work"
    text_b = _compose_with_task_volumes([f"{fake}:/task"], fake)
    bad_b = RC.lint_compose(text_b, expect_workdir=fake, runs_root=data_root / "runs")
    assert any("落在数据根" in x for x in bad_b), f"实际 {bad_b}"


def test_data_roots_do_not_drift_between_lint_and_spec():
    """DATA_ROOTS 是一份「封闭列举」。测试里再抄一份就会漂，两边都不报错。"""
    assert Path("/data") not in [Path(x) for x in RC.DATA_ROOTS], \
        "/data 本身进表会让规则恒红，下一个人会注释掉它"
    for d in RC.DATA_ROOTS:
        assert d.startswith("/data/"), d


def test_l5_sees_relative_and_interpolated_mount_sources(tmp_path):
    """L-5 原先只看以 `/` 开头的挂载源 —— 相对路径与 ${VAR} 插值对「恰为 1」和落点判据完全隐形。"""
    runs = tmp_path / "runs"
    work = runs / "r01" / "work"
    work.mkdir(parents=True)
    for src in ("./sneak", "../../data/shared", "${HOST_LAKE}"):
        text = _compose_with_task_volumes([f"{work}:/task", f"{src}:/x"], work)
        bad = RC.lint_compose(text, expect_workdir=work, runs_root=runs)
        assert bad, f"挂载源 {src!r} 完全隐形 —— 「恰为 1」和落点判据都没看见它"


def test_p2_provider_gate_is_reached_end_to_end(exported, provider, tmp_path, monkeypatch):
    """P2 原先只有单元级测试（test_t4 直接调 check_provider_pin）——
    把整条 `gate("P2", ...)` 从 inject 里删掉，全套仍绿。这里走端到端。"""
    _patch_pin(monkeypatch, provider)
    (provider / "calendars" / "day.txt").write_text("篡改\n", encoding="utf-8")
    with pytest.raises(P.PackError, match=r"\[P2\]"):
        _inject(exported, provider, "open", run_root=tmp_path / "rr")


def test_bare_tag_image_is_refused_by_p4(rows, provider, tmp_path, monkeypatch):
    """P4d：Dockerfile 的 FROM 必须带 digest。裸 tag 两臂各拉一次可能拿到不同镜像。

    **必须单独造一份 bundle**：在已有 bundle 上改 Dockerfile 会先被 P3（通行证 sha）
    抓到，于是判据 P4d 本身从没被执行过 —— 删掉它测试照样绿（红队 2026-09-04）。
    这里让 digest 在**出通行证之前**就是裸 tag，P3 一路绿灯，红的只能是 P4d。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("_fz2", _REPO / "ops" / "freeze_v10.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    root = tmp_path / "f01"
    row = next(r for r in rows if r["task_id"] == "s1-cor-01")
    b = P.build_task(row, capabilities=ALL_CAPS)
    task_dir = P.write_task(b, root / "reference", capabilities=ALL_CAPS)
    bundle = P.export_task(task_dir, root / "runner")
    df = bundle / "image" / "Dockerfile"
    df.write_text(re.sub(r"(?im)^(FROM\s+\S+?)@sha256:[0-9a-f]{64}", r"\1",
                         df.read_text(encoding="utf-8").replace(
                             B.IMAGE_DIGEST_PLACEHOLDER, "sha256:" + "b" * 64)),
                  encoding="utf-8")
    ce = P.check_export(bundle, P.gold_sha_set(task_dir), b.task["canary"])
    man = P.export_manifest(task_dir, bundle, check_export_result=ce,
                            frozen_ref=fz.frozen_ref())
    monkeypatch.setattr(pin, "PROVIDER_SHA256_ROOT", pin.provider_root_sha256(provider))
    with pytest.raises(P.PackError) as ei:
        INJ.inject(bundle, "open", run_root=tmp_path / "rr", provider_root=provider,
                   config_id="cfg-a", manifest=man, model_upstream="",
                   expect_frozen_root=fz.frozen_ref()["root"],
                   command='sh -c "true"', require_docker=False, check_modes=False)
    # 由 P4（lint_dockerfile 的 L1）拦下。我一度另加过一道 P4d 做同一件事，
    # 实测它永远轮不到 —— 重复的门只会让人以为有两道保险。
    assert "[P4]" in str(ei.value) and "FROM 必须带 digest" in str(ei.value)


def test_p6a_manifest_paired_with_the_wrong_bundle_is_refused(exported, provider, tmp_path,
                                                              monkeypatch):
    """通行证的 task_id 是**记录**，bundle 的 task.yaml 才是它自己说的身份。
    只信通行证的话，一份通行证配错 bundle 也查不出来。"""
    _patch_pin(monkeypatch, provider)
    m = deepcopy(exported["manifest"])
    m["task_id"] = "s9-fake-01"
    with pytest.raises(P.PackError) as ei:
        INJ.inject(exported["bundle"], "open", run_root=tmp_path / "rr",
                   provider_root=provider, config_id="cfg-a", manifest=m, model_upstream="",
                   expect_frozen_root=exported["frozen_root"],
                   command='sh -c "true"', require_docker=False, check_modes=False)
    assert "[P6a]" in str(ei.value), f"实际 {str(ei.value)[:160]}"


@pytest.mark.parametrize("src", ["./sneak", "../../data/shared", "${HOST_LAKE}", "~/lake"])
def test_l5c_non_absolute_source_is_refused_on_its_own(tmp_path, src):
    """L-5c 要**独立**判别：只挂一个非绝对路径（不多挂），这样「恰为 1」不会代它红。"""
    runs = tmp_path / "runs"
    work = runs / "r01" / "work"
    work.mkdir(parents=True)
    text = _compose_with_task_volumes([f"{src}:/task"], work)
    bad = RC.lint_compose(text, expect_workdir=work, runs_root=runs)
    assert any(x.startswith("L-5c") for x in bad), \
        f"挂载源 {src!r} 必须由 L-5c 独立拦下，实际 {bad}"


def test_frozen_gate_recomputes_and_catches_a_template_change(tmp_path):
    """**这道门必须现算**，不能只对清单文件里已经记着的字段求 hash。

    红队 2026-09-04 逐字复现过没有这一步的后果：改一个模板 → 题面真的变了 →
    通行证的 root **一个字都没变** → check_manifest 全绿 → inject 放行 →
    改过的题面进容器，而全套测试 35 passed。
    **这正是 `pin.py` 里批判过的 F7 形态（只读记录值等于没查），在同一个仓库犯了第二次。**

    突变加在**模板**上，不是加在期望常量上 —— 后者测的是字符串不等，
    不是这道门要抓的性质（原来那两条判别力测试就是这么写的，所以恒绿）。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("_fz3", _REPO / "ops" / "freeze_v10.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    assert fz.frozen_ref()["root"], "基线必须能出通行证"

    tpl = _REPO / "genetask" / "templates" / "S1" / "cov_fields" / "INSTRUCTION.open.md"
    orig = tpl.read_text(encoding="utf-8")
    anchor = "要求字段：close、volume、adj_factor。"
    assert orig.count(anchor) == 1, "锚点失效 —— 模板改了就要跟着改，别让负例静默空转"
    try:
        tpl.write_text(orig.replace(anchor, anchor[:-1] + "（复权可忽略）。", 1), encoding="utf-8")
        assert tpl.read_text(encoding="utf-8") != orig, "突变空转"
        fz._VERIFIED.clear()                       # 绕过进程内缓存
        with pytest.raises(SystemExit, match="题面指纹"):
            fz.frozen_ref()
    finally:
        tpl.write_text(orig, encoding="utf-8")
        fz._VERIFIED.clear()
    assert fz.frozen_ref()["root"], "还原后必须恢复"


def test_frozen_ref_verify_cannot_be_silently_skipped():
    """`verify` 是有默认值的，但默认必须是**开**。"""
    import importlib.util, inspect
    spec = importlib.util.spec_from_file_location("_fz4", _REPO / "ops" / "freeze_v10.py")
    fz = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fz)
    assert inspect.signature(fz.frozen_ref).parameters["verify"].default is True


def test_runs_root_is_not_inside_any_data_root():
    """主判据（在 runs_root 之下）与纵深（不在 DATA_ROOTS 内）不得互相打架 ——
    否则每个 run 都会被自己的纵深判红（指令六 sanity，2026-09-04）。"""
    runs_root = (RC.ROOT / "runs").resolve()
    for d in RC.DATA_ROOTS:
        dr = Path(d)
        assert dr != runs_root and dr not in runs_root.parents, \
            f"runs 根 {runs_root} 落在数据根 {d} 之内 —— 主判据与纵深互斥"


def test_protocol_pending_blocks_strict_arm_is_a_permanent_assertion():
    """**永久断言**（指令七②，2026-09-04）：协议工件缺失时 strict 臂必须红，
    实验**不得静默降级成双裸臂**。

    这条与「等协议工件落地后就可以删掉」相反 —— 它要留着：
    干预内容是 GQ 臂相对裸臂多出的**全部**东西，缺了它 strict 臂就是个裸臂，
    而实验照跑、分数照出、结论会变成「协议没用」（F8）。
    status 翻 released 之后，这条断言的形式从「pending 必红」变成
    「清单为空或文件缺失必红」，**语义不变**。
    """
    import inspect
    src = inspect.getsource(INJ.inject)
    # 卡 4.1 之后这道门不再按臂名分支（臂由 genetask/arms.yaml 定义），
    # 而是**按本臂声明的每一份清单**逐份查。语义不变：清单未发布或为空 → 该臂不得注入。
    assert "ARM_BY_ID[arm].artifacts" in src, \
        "臂的工件门被删了 —— 干预缺失时实验会静默降级成双裸臂"
    # 门的形状：released 且非空才放行
    assert '_status == "released" and _files' in src
    # 而「strict 臂到底有没有工件」这件事仍然是真的，不靠源码字符串证明
    assert INJ.arm_files("strict"), "strict 臂在注册表里没有工件 —— 它就是个裸臂了"
    assert INJ.arm_files("open") == {}, "裸臂声明了工件 —— §6.2 的等号另一半不成立"


def test_p0_startup_guard_refuses_when_modes_are_loose(tmp_path, monkeypatch):
    """**启动守门在使用时刻**（指令一）：推送时刻绿不代表使用时刻绿 ——
    中间任何人 chmod 一下都不会有人知道，而注入器正要往容器可见的目录里复制东西。

    **不依赖当前仓库的权限状态**：造一个临时的不合规树来测。
    第一版断言「开发机上仓库本来就是 0755，守门必须看得见」—— 那在 f01（合规）上假红，
    实测就红了一次。测试的前提条件要自己造，不能捡环境的。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("_g", _REPO / "ops" / "guard_modes.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    fake = tmp_path / "repo"
    (fake / "reference").mkdir(parents=True)
    (fake / "reference" / "x.py").write_text("x", encoding="utf-8")
    monkeypatch.setattr(g, "EXTERNAL_ROOTS", ())
    g.harden(fake)
    assert g.check(fake) == []
    import os
    os.chmod(fake / "reference", 0o755)
    assert any("红线 5" in x for x in g.check(fake))
    # P0 真的接了守门：check_modes=False 时不查，True 时走 guard
    import inspect
    assert "check_modes" in inspect.signature(INJ.preflight).parameters
    src = inspect.getsource(INJ.preflight)
    assert "guard_modes" in src, "P0 没有接上启动守门"
    assert INJ.preflight(tmp_path / "rr", require_docker=False, check_modes=False) == []


def test_sidecar_code_lives_in_the_run_dir_not_a_global_path(exported, provider, tmp_path,
                                                             monkeypatch):
    """边车代码必须进 run dir（T15 实测发现，2026-09-04）。

    原先 compose 挂的是 `/data/genebench_runner/egress_proxy.py` —— run dir **之外**的
    固定路径，不在任何同步或校验链路里。它与代码库漂开时的表现是
    **身份注入静默失效**：容器照跑、日志照写，只是记的是伪造值。
    T15 第一次红就是被这个绊的（新代码进了 exec/，边车跑的还是旧版）。
    """
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    sc = r.run_dir / INJ.SIDECAR_REL
    assert sc.is_file(), "边车代码没进 run dir"
    src = Path(RC.__file__).resolve().parent / "egress_proxy.py"
    assert sc.read_bytes() == src.read_bytes(), "与仓库里的那份不一致"
    text = (r.run_dir / "compose.yml").read_text(encoding="utf-8")
    assert str(sc) in text, "compose 没挂本 run 自己的那份"
    assert str(RC.ROOT / "egress_proxy.py") not in text, \
        "compose 还挂着全局路径 —— 它会与代码库漂开而无人知道"
    # 进了 inject.json 的文件集封闭
    inj = json.loads((r.run_dir / "inject.json").read_text(encoding="utf-8"))
    assert INJ.SIDECAR_REL in inj["files"], "边车 sha 没记进 inject.json"


# ===================================================== 封闭推广（裁定 2026-09-04）

def test_every_executable_in_the_run_is_closed_and_hashed(exported, provider, tmp_path,
                                                          monkeypatch):
    """**参与一次运行的可执行物，逐个在封闭里且 sha 记进 inject.json。**

    与 N-30（fstab）、P2（provider）同族：不在封闭里就会静默漂开，
    而漂开的表现是「跑了、绿了、只是跑的不是那一版」。
    """
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    inj = json.loads((r.run_dir / "inject.json").read_text(encoding="utf-8"))

    # ① 边车、compose、题面、schema、provider —— 每一个都在 files 里且 sha 非空
    must = [INJ.SIDECAR_REL, "compose.yml", "work/INSTRUCTION.md"]
    for rel in must:
        assert rel in inj["files"] and inj["files"][rel], f"{rel} 没记 sha"
    assert any(k.startswith("work/provider/") for k in inj["files"]), "provider 没进封闭"
    assert any(k.startswith("bundle/") for k in inj["files"]), "bundle 没进封闭"

    # ② runner 自己：不在容器也不在 run dir，但决定注入顺序与 env 契约
    assert len(inj["runner_version"]) == 64, "runner_version 缺失或不是 sha256"
    assert inj["runner_version"] == INJ.runner_version()

    # ③ 镜像：容器实际跑的那个，带 digest
    assert "@sha256:" in inj["image"], f"镜像没钉 digest：{inj['image']}"

    # ④ executables 是一张**显式**清单，不是「files 里恰好有」
    h11_files = {k for k in inj["executables"] if k.startswith(f"{INJ.H11_REL}/")}
    assert set(inj["executables"]) == {INJ.SIDECAR_REL, "compose.yml"} | h11_files
    for rel, sha in inj["executables"].items():
        assert sha == INJ._sha_file(r.run_dir / rel)

    # ⑤ **解析器也是可执行物**（裁定 2026-09-05）：边车用 h11 解析请求头，
    #    与网关必须是**同一份**。版本不同 =「两个解析器看法不同」那一类洞回来了（N-91），
    #    而它不会以任何别的方式表现出来 —— 所以 h11 逐文件进封闭、逐文件记 sha。
    assert h11_files, "h11 没进 executables —— 边车与网关同解析器这条就没有证据"
    assert f"{INJ.H11_REL}/__init__.py" in h11_files
    src = INJ.h11_source_dir()
    for rel in h11_files:
        assert inj["executables"][rel] == INJ._sha_file(src / Path(rel).name), \
            f"{rel} 与网关那一份不是同一个字节"


def test_p8_closes_the_run_dir_toplevel_not_just_work(exported, provider, tmp_path, monkeypatch):
    """顶层可执行物（compose.yml / egress_proxy.py）也在 P8 的封闭里 ——
    原先只有 work/ 进封闭，而边车漂开那次正是顶层的东西。"""
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    sc = r.run_dir / INJ.SIDECAR_REL
    # 卡 4.1：`protocol` = **本臂**应有的工件（裸臂为空），`forbidden` = 别的臂的。
    # 原先这里传的是 `protocol_artifacts()`（**不带 `protocol/` 前缀**的键），
    # 在旧实现的 else 分支里 `want_proto & have` 恒空 —— 那一半其实什么也没查。
    bad = INJ.check_run_dir(r.run_dir, arm="open", protocol=INJ.arm_files("open"),
                            forbidden=INJ.other_arm_files("open"),
                            expect_top={INJ.SIDECAR_REL: INJ._sha_file(sc)})
    assert bad == [], bad
    sc.write_text(sc.read_text(encoding="utf-8") + "\n# 偷改\n", encoding="utf-8")
    bad = INJ.check_run_dir(r.run_dir, arm="open", protocol=INJ.arm_files("open"),
                            forbidden=INJ.other_arm_files("open"),
                            expect_top={INJ.SIDECAR_REL: INJ._sha_file(sc) + "x"})
    assert any("sha256 与注入时不符" in x for x in bad)


def test_verify_run_dir_unchanged_catches_post_injection_writes(exported, provider, tmp_path,
                                                                monkeypatch):
    """**注入之后到起容器之间的窗口**原先没有任何门。

    实测证据：T5/T10 的探针脚本 `work/probe.py` 就是在注入之后写进去的，
    P8 一个字都没说 —— 容器于是跑了一个不在任何清单里的文件。
    """
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    assert INJ.verify_run_dir_unchanged(r.run_dir) == [], "刚注完就该是干净的"

    sneak = r.run_dir / "work" / "probe.py"
    sneak.write_text("print('我不在任何清单里')\n", encoding="utf-8")
    bad = INJ.verify_run_dir_unchanged(r.run_dir)
    assert any("注入后被加" in x and "probe.py" in x for x in bad), f"实际 {bad}"

    sneak.unlink()
    (r.run_dir / "work" / "INSTRUCTION.md").write_text("改过的题面", encoding="utf-8")
    assert any("注入后被改" in x for x in INJ.verify_run_dir_unchanged(r.run_dir))


def test_run_dir_log_dir_is_excluded_from_the_closure(exported, provider, tmp_path, monkeypatch):
    """`log/` 是**运行期产物**，不在封闭里 —— 否则容器一写日志复核就红。"""
    _patch_pin(monkeypatch, provider)
    r = _inject(exported, provider, "open", run_root=tmp_path / "rr")
    (r.run_dir / "log" / "egress.jsonl").write_text('{"event":"x"}\n', encoding="utf-8")
    assert INJ.verify_run_dir_unchanged(r.run_dir) == []
