# -*- coding: utf-8 -*-
"""卡 3.1：GeneTask 打包器 —— 参数行 → 数据面全量任务 → 执行面 bundle。

实例化顺序（D-11 固化，**不可调换**）：
  ① 行 → taskspec + scorer.yaml 落盘、写 ledger（判据先落盘）
  ② 材料 inputs（本卡只登记，物化由模板的 inputs 步骤在 f01 完成）
  ③ 渲染两臂（欠定字段在渲染期屏蔽）
  ④ 拼全量 task.yaml
  ⑤ 校验（字典级 + 双臂 + 文件级）
  ⑥ oracle / null 干跑（O1 / N1）
  ⑦ export() 剥 D 键落执行面

用法：
    python -m genetask.packager build  --params genetask/params/v1.0-smoke.yaml --out <reference_root>
    python -m genetask.packager export --task <reference_root>/tasks/<set>/<id> --runner <runner_root>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

import genebench_config as cfg
from genetask import render as R
from genetask import materiality as MAT
from genetask import schema as S
from reference import artifact_schema as sch

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
PHRASEBOOK = HERE / "phrasebook.yaml"

GATEWAY_URL = "http://gateway:18080"
ARTIFACT_PATH = "/task/artifact.json"
#: 镜像 digest 占位：**真 digest 在 f02 export 时钉**（L1 只查格式；status 升到 exported 前必须换成真值）。

#: 执行面 bundle 允许出现的相对路径前缀。
# 自查：前缀白名单让 `task.yaml.bak` / `task.yamlsecret` 全部放行 —— 改成精确文件名 + 目录前缀两段判据。
# 执行面判据都在 genetask/bundle.py（零 reference 依赖，卡 4.3 §1.1 的第二个实例）；
# 这里再导出，`genetask.packager.<name>` 的既有路径不变。
from genetask.bundle import (ARMS as _BUNDLE_ARMS, IMAGE_DIGEST_PLACEHOLDER,  # noqa: E402,F401
                             MANIFEST_VERSION, PackError as _BundlePackError,
                             X_ALLOWED_FILES, X_ALLOWED_PREFIXES,
                             _check_tests_source, check_manifest, lint_dockerfile)


PackError = _BundlePackError            # 单一定义在 genetask/bundle.py


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(b: bytes | str) -> str:
    if isinstance(b, str):
        b = b.encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def _token(prefix: str) -> str:
    return f"GBC-{prefix}-{secrets.token_hex(8)}"


# ============================================================== 参数表

PARAM_COLUMNS: tuple[str, ...] = (
    "task_id", "stage", "family", "subject_id", "kind", "template_id",
    "as_of", "window", "universe", "declared", "underdetermined",
    "inputs", "gold_args", "null_behavior", "tolerance", "timeouts",
)


#: payload 档位是**模板**的属性（产出要求就在模板里写），不是参数行的属性 —— 所以不进 PARAM_COLUMNS。
PAYLOAD_PROFILE_BY_TEMPLATE: dict[str, str] = {
    "S2/cor_01": "s2_adjust_report",
    "S2/rob_01": "s2_adjust_report",
    "S2/eco_01": "s2_adjust_report",
    "S2/ops_01": "s2_adjust_report",
    # S2/rob_02_probe 故意不给：那道题欠定 adjust，字段名不能进它的共享结构文件
    "S4/eco_free_select": "s4_free_select",
}
for _k, _v in PAYLOAD_PROFILE_BY_TEMPLATE.items():
    if _v not in sch.PAYLOAD_PROFILES:
        raise RuntimeError(f"PAYLOAD_PROFILE_BY_TEMPLATE[{_k}] 指向未知档位 {_v}")


def profile_for(stage: str, template_id: str) -> str | None:
    return PAYLOAD_PROFILE_BY_TEMPLATE.get(f"{stage}/{template_id}")


def load_params(path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    rows = doc.get("rows") or []
    for i, r in enumerate(rows):
        missing = [c for c in PARAM_COLUMNS if c not in r]
        extra = [c for c in r if c not in PARAM_COLUMNS]
        if missing or extra:
            raise PackError(f"参数行 {i}（{r.get('task_id')}）列集不对：缺 {missing}，多 {extra}")
    return [{"set_id": doc.get("set_id", "v1.0-smoke"), **r} for r in rows]


# ============================================================== 模板

@dataclass
class Template:
    stage: str
    template_id: str
    strict: str
    open: str
    dockerfile: str
    tests: str
    scorer: str
    solve: str
    slots: set[str]

    def text_for(self, column: str) -> str:
        """按**措辞列**取题面模板（卡 4.1）。模板目录里只有 `INSTRUCTION.<列>.md` 两份 ——
        新臂不新增模板文件，它复用某一列的模板，差异走 `arms.yaml` 的 `variant_text_file`。"""
        if column == "strict":
            return self.strict
        if column == "open":
            return self.open
        raise PackError(f"模板没有 {column!r} 列（只有 {list(R.PHRASEBOOK_COLUMNS)}）")


def load_template(stage: str, template_id: str) -> Template:
    d = TEMPLATES / stage / template_id
    if not d.is_dir():
        raise PackError(f"模板 {stage}/{template_id} 不存在")
    rd = lambda n: (d / n).read_text(encoding="utf-8")   # noqa: E731
    meta = yaml.safe_load(rd("template.yaml")) or {}
    return Template(stage, template_id, rd("INSTRUCTION.strict.md"), rd("INSTRUCTION.open.md"),
                    rd("Dockerfile"), rd("tests/test_outputs.py"), rd("scorer.yaml"), rd("solve.py"),
                    set(meta.get("slots") or []))


def _variant_text(spec) -> str | None:
    """指令变体臂要追加的固定文本（`arms.yaml` 的 `variant_text_file`，相对 `genetask/`）。

    **不许静默为空**：声明了文件却读不到，说明这个臂的干预内容不存在 ——
    那时候跑出来的是一个「叫 hint 但什么也没提示」的臂，而结论会写成「提示没用」（F8 同形）。
    """
    if not getattr(spec, "variant_text_file", None):
        return None
    p = Path(__file__).resolve().parent / spec.variant_text_file
    if not p.is_file():
        raise PackError(f"臂 {spec.id!r} 的变体文本不存在：{p} —— "
                        f"声明了干预内容却没有内容，跑出来的是个空壳臂")
    txt = p.read_text(encoding="utf-8").strip("\n")
    if not txt.strip():
        raise PackError(f"臂 {spec.id!r} 的变体文本是空的：{p}")
    return txt


# ============================================================== 构建

@dataclass
class Built:
    task: dict                      # 全量（D 面）
    strict: R.Rendered
    open: R.Rendered
    scorer_yaml: str
    solve_py: str
    dockerfile: str
    tests_py: str
    ledger_entry: dict
    problems: list[str] = field(default_factory=list)
    review: list[dict] = field(default_factory=list)          # E6 审查标记（不影响 ok）
    task_level: dict = field(default_factory=dict)            # 两臂同给的任务级字段
    #: **本次渲染的全部臂**（注册表顺序）：`{arm_id: Rendered}`。卡 4.1 之前只有两臂，
    #: `strict` / `open` 两个字段就是全部；现在它们是本字典里那两条的别名，留着不删 ——
    #: 等价性规则、equivalence.md、几十条既有断言都按「strict 列 / open 列」写，
    #: 它们要的是**列**而不是任意臂。
    arms: dict = field(default_factory=dict)
    #: 非默认臂被免掉的等价规则（`{arm_id: [规则前缀…]}`），写进 arms/equivalence.md 的例外段。
    arm_exceptions: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.problems


def build_task(row: dict, *, capabilities: dict | None = None, phrasebook: dict | None = None,
               now: str | None = None, arms: "list[str] | tuple[str, ...] | None" = None) -> Built:
    """建一道题。

    `arms`：要渲染哪些臂（`genetask/arms.yaml` 里登记过的 id）。
    **默认是注册表里 `default: true` 的那些**（= `S.ARMS`，内置 strict/open）——
    非默认臂只有显式点名才渲染，所以「往注册表里加一个臂」不会改动任何既有出集的字节。
    """
    pb = phrasebook or R.load_phrasebook(PHRASEBOOK)
    tpl = load_template(row["stage"], row["template_id"])
    now = now or _now()
    canary = {"gold_token": _token("G"), "control_token": _token("C"), "x_token": _token("X")}
    tid, stage = row["task_id"], row["stage"]
    is_probe = row["kind"] == "underdetermined_probe"

    # ① 判据先落盘：taskspec + scorer.yaml → judge_sha256 → ledger
    taskspec = {"task_id": tid, "stage": stage,
                "declared": deepcopy(row["declared"]), "underdetermined": list(row["underdetermined"])}
    scorer_yaml = tpl.scorer.replace("<<task_id>>", tid).replace("<<gold_token>>", canary["gold_token"])
    judge_sha = _sha(S.canonical_json(taskspec) + "\n" + scorer_yaml)
    judge_at = now
    ledger = {"task_id": tid, "set_id": row["set_id"], "judge_sha256": judge_sha, "judge_written_at": judge_at}

    # ③ 渲染两臂（判据落盘之后）
    profile = profile_for(stage, row["template_id"])
    endpoints = _endpoints_phrase(stage)
    fixed = {"preamble": "", "as_of": _as_of_phrase(stage, row["as_of"]),
             "gateway_url": GATEWAY_URL, "artifact_path": ARTIFACT_PATH,
             "output_files": _output_files_phrase(row["stage"], row.get("payload_profile")),
             "endpoints": endpoints, "no_default_fill": "",
             "task_window": f"{row['window']['start']} 到 {row['window']['end']}",
             "task_universe": row["universe"],
             "inputs": _inputs_phrase(row["inputs"] or []),
             "output_format": _output_format_phrase(stage, profile),
             "fields_required": ""}
    partial = {"task_id": tid, "stage": stage, "kind": row["kind"], "family": row["family"],
               "declared": row["declared"], "underdetermined": row["underdetermined"]}
    problems: list[str] = []
    arm_ids = tuple(arms) if arms else S.ARMS
    unknown = [a for a in arm_ids if a not in S.ARM_BY_ID]
    if unknown:
        raise PackError(f"未登记的臂 {unknown} —— 先写进 genetask/arms.yaml（卡 4.1）")
    if S.BASELINE_ARM not in arm_ids:
        raise PackError(f"要渲染的臂 {list(arm_ids)} 里没有参照臂 {S.BASELINE_ARM!r} —— "
                        f"等价规则以它为参照，缺了它没有任何东西可比")
    rendered: dict[str, R.Rendered] = {}
    try:
        for _a in arm_ids:
            _spec = S.ARM_BY_ID[_a]
            rendered[_a] = R.render_arm(tpl.text_for(_spec.column()), _a, partial, pb, fixed,
                                        canary["control_token"], column=_spec.column(),
                                        variant_text=_variant_text(_spec))
    except (R.RenderError, PackError) as e:
        problems.append(f"RENDER {e}")
        rendered = {a: R.Rendered(text="") for a in arm_ids}
    strict, open_ = rendered[arm_ids[0]], rendered[S.BASELINE_ARM]
    arms_at = _now()

    # ④ 全量 task.yaml
    task = {
        "schema_version": S.SCHEMA_VERSION, "task_id": tid, "set_id": row["set_id"], "task_sha256": None,
        "stage": stage, "as_of": row["as_of"], "window": dict(row["window"]), "universe": row["universe"],
        "instruction": {a: {"path": f"arms/INSTRUCTION.{a}.md", "sha256": _sha(rendered[a].text)}
                        for a in arm_ids},
        "image": {"base": "python:3.11-alpine", "digest": IMAGE_DIGEST_PLACEHOLDER},
        "timeouts": dict(row["timeouts"]),
        "inputs": [dict(i) for i in (row["inputs"] or [])],
        "artifact_path": ARTIFACT_PATH,
        "contract_ref": ["ops/specs/backtest_contract.md"] if stage == "S7" else [],
        "artifact_schema_ref": f"ops/specs/artifact_schema/v{sch.SCHEMA_VERSION}/{stage}.json",
        "payload_profile": profile,
        # 规则块的计分禁令表按 (stage, template_id) 取键 —— 规则块正是模板这一层的东西。
        # 自查：这个键原先不在 task 里，E6 的「规范句必须在」那半个检查因此**恒不触发**
        # （2026-09-03 被 test_e6_missing_annotation_is_red 抓到）。
        "template_id": row["template_id"],
        "status": "draft", "packed_at": None, "packager_version": S.PACKAGER_VERSION,
        "declared": deepcopy(row["declared"]), "underdetermined": list(row["underdetermined"]),
        "kind": row["kind"], "family": row["family"], "subject_id": row["subject_id"],
        "probes": {"armed": sorted(set(S.STAGE_REQUIRED_PROBES[stage]) | ({"underdetermined"} if is_probe else set())),
                   "expected_unobservable": [], "target_field": row["underdetermined"][0] if is_probe and row["underdetermined"] else None},
        "gold_ref": ({"path": f"reference/tasks/{row['set_id']}/{tid}/gold/slice.parquet", "manifest_sha256": None,
                      "args": dict(row["gold_args"])} if row["gold_args"] is not None else None),
        "solution_ref": f"reference/tasks/{row['set_id']}/{tid}/solution/solve.py",
        # **走全映射**（结构锁，见 `schema.ORACLE_EXPECTED_BY_KIND`）：
        # 原来是 `"validate_only" if kind == "free" else "full"` —— 三分支写成两分支，
        # 探针题于是被静默归到 `full`，而 `full` 要求 gold 出完整 payload，
        # 也就是要求 gold 对被欠定的字段**择一填上**。那正是本题要抓的静默补全（N-93）。
        "oracle": {"expected": S.ORACLE_EXPECTED_BY_KIND[row["kind"]]},
        "null_agent": {"behavior": row["null_behavior"], "expected_findings": _expected_null_findings(row["null_behavior"], is_probe)},
        "scorer_ref": f"reference/tasks/{row['set_id']}/{tid}/scorer.yaml",
        "tolerance": dict(row["tolerance"]),
        "anchor": {"status": "pending" if row["kind"] == "free" else "fixed", "floor": None, "ceiling": None},
        "judge_sha256": judge_sha, "judge_written_at": judge_at, "canary": canary,
    }
    task["task_sha256"] = _sha(S.canonical_json({k: v for k, v in task.items() if k != "task_sha256"}))

    # ⑤ 校验
    problems += S.validate_task(task, capabilities=capabilities)
    review: list[dict] = []
    exceptions: dict[str, list[str]] = {}
    if not problems or all(p.startswith(("S3b", "S8b")) for p in problems):
        base = rendered[S.BASELINE_ARM]
        for _a in arm_ids:
            if _a == S.BASELINE_ARM:
                continue
            _spec = S.ARM_BY_ID[_a]
            if _spec.waives_e_rules:
                # 指令变体臂：只查 E1/E2 欠定/C1，其余记「例外」（公平性协议 §6.6）。
                problems += R.check_arms(task, rendered[_a], base, pb, canary["control_token"],
                                         names=(_a, S.BASELINE_ARM), keep=R.VARIANT_KEEP)
                exceptions[_a] = sorted(R.WAIVED_FOR_VARIANT)
            else:
                # kind ∈ {baseline, protocol}：E1–E14 全查，两两 vs 参照臂。
                problems += R.check_arms(task, rendered[_a], base, pb, canary["control_token"],
                                         names=(_a, S.BASELINE_ARM))
        review = R.review_flags(task, strict, open_)
        problems += lint_dockerfile(tpl.dockerfile)
        problems += _check_tests_source(tpl.tests)
    if judge_at > arms_at:
        problems.append("J1 判据落盘时间晚于臂渲染时间 —— 顺序反了")
    # E9d4（形式判据，2026-09-03 签字）：探针字段的**可行值**不得与固定槽内容重叠 ——
    # S8 的 permitted_operations 取值就是端点名（order / cancel），而「可用端点」槽写着 /sim/order：
    # 欠定它必被 E2 判成题面泄漏，且端点清单本身已经把这些操作告诉了 agent。
    if task["kind"] == "underdetermined_probe" and task["underdetermined"]:
        pf = task["underdetermined"][0]
        fixed_text = " ".join(v for k, v in strict.phrases.items() if k.startswith("fixed:"))
        # 自查（high）：原先只收「字符串且长度 ≥3」的可行值 —— data_version 的 v1/v2、lookback 的 10/20、
        # holding_periods 的 [1] 全部逃逸。改成把可行值统一转成题面记法再匹配，短 token 走词边界。
        vals = {R.iface_value(x) for v in MAT.feasible_values(pf) for x in (v if isinstance(v, list) else [v])}
        clash = sorted(v for v in vals if v and R._pointer_hit(v, fixed_text, allow_underscore=True))
        if clash:
            problems.append(f"E9d4 探针字段 {pf} 的可行值 {clash} 与固定槽内容重叠 —— "
                            f"固定槽已经把它告诉了 agent，欠定它只会被 E2 判成题面泄漏")

    tpl_slots = tpl.slots
    if not tpl_slots:                       # 自查：原先空集自动豁免 —— 删掉 template.yaml 的 slots 键即可绕过 T1
        problems.append("T1 模板 template.yaml 没有声明 slots（空集不豁免）")
    elif tpl_slots != set(task["declared"]) | set(task["underdetermined"]):
        problems.append(f"T1 模板 slots {sorted(tpl_slots)} 与本题声明字段全集不等")

    b = Built(task, strict, open_, scorer_yaml, tpl.solve.replace("<<gold_token>>", canary["gold_token"]),
              tpl.dockerfile, tpl.tests, ledger, problems)
    b.arms = {a: rendered[a] for a in arm_ids}
    b.arm_exceptions = exceptions
    b.review = review
    b.task_level = {"as_of": row["as_of"], "window": fixed["task_window"], "universe": row["universe"],
                    "inputs": fixed["inputs"], "output_format": fixed["output_format"]}
    return b


def _inputs_phrase(inputs: list[dict]) -> str:
    if not inputs:
        return "无；所需数据全部经网关获取"
    # 只给路径与数据截止日。`origin` 是数据面的来源说明（可能含 gold/信号 id 等评分侧词汇），**不进题面**。
    # 写**容器内**路径：bundle 的 work/ 整目录挂到 /task（卡 4.1 compose），所以 work/x.parquet 在容器里是 /task/x.parquet
    return "；".join(f"/task/{str(i['path']).split('/', 1)[-1]}（数据截至 {i['max_date']}）" for i in inputs)


def _output_format_phrase(stage: str, profile: str | None = None) -> str:
    """从 artifact schema 生成「输出格式」固定槽位的值 —— 字段名、必填、结构文件位置，两臂同给。"""
    env = ", ".join(sch.ENVELOPE_REQUIRED)
    pay = ", ".join(sch.payload_required(stage, profile))
    # 评分器硬要求精确键名的子字段，两臂都要能看到（审查：S7 的 11 个指标键两臂题面都没给）
    sub = []
    for k, shape in sch.payload_shape(stage, profile).items():
        req = shape.get("required") or (shape.get("items") or {}).get("required")
        if req:
            sub.append(f"{k} 含 {', '.join(req)}")
    subtxt = ("；子字段：" + "；".join(sub)) if sub else ""
    return (f"JSON 顶层必含 {env}（stage 写 {stage}）；declarations 里逐项写上面的口径：键名用每条给出的字段名，取值用每条给出的接口值；payload 必含 {pay}{subtxt}；"
            f"完整字段结构文件在 /task/{stage}.json")


#: **按 stage 生成的可用端点**（裁定 2026-09-04，N-58①）。
#:
#: 先前是一个**不按 stage 区分**的字面量，于是 `/fundamentals` 写进了**每一道题**
#: 两臂的「可用端点」槽 —— 每个 agent 都被告知可以查财报，而 v1 没有一道题需要它。
#: `render.py` 的 E8b 只管「正文端点 ⊆ 槽」，**槽里多列一个不会被任何检查拦下**。
#:
#: **判据是「agent 看不到即不存在越权」，不是「调了返 403」** ——
#: 后者会把一次我们自己造成的诱导记成被测方的越权率。
#:
#: v1 的六个数据端点对应范围核定的七项（`/bars` 一个端点压着日线/停牌/上市退市/
#: 涨跌停四项，见 N-58 补记）；S8 另加五个 sim 端点。
#: **`/fundamentals` 不在任何 v1 阶段里** —— 6 张财务快照留私有通道，不进公开包。
V1_DATA_ENDPOINTS: tuple[str, ...] = (
    "/bars", "/adj", "/calendar", "/limits", "/universe", "/tradability",
)
SIM_ENDPOINTS: tuple[str, ...] = (
    "/sim/state", "/sim/order", "/sim/cancel", "/sim/advance", "/sim/log",
)
#: 不许出现在任何 v1 阶段的端点。**空集不是判据，这张表才是。**
V1_WITHHELD_ENDPOINTS: tuple[str, ...] = ("/fundamentals",)


def stage_endpoints(stage: str) -> tuple[str, ...]:
    out = V1_DATA_ENDPOINTS + (SIM_ENDPOINTS if stage == "S8" else ())
    bad = [e for e in out if e in V1_WITHHELD_ENDPOINTS]
    if bad:
        raise ValueError(f"{stage} 的端点清单里出现了 v1 不发放的端点 {bad}")
    return out


#: S8 的 `as_of` 语义补注（裁定 2026-09-05）。**机器生成、两臂同给。**
#:
#: 由来：题面只给一个平的 `as_of=<冻结线>`，而 S8 的有效上界**随模拟时钟走**
#: （契约 §3.1：本次运行内网关的 `as_of` 上界 = 当前 `sim_date`，推进之后才前移）。
#: 照题面拿 `2026-07-31` 去请求，除窗口首日外**全部被拒**。
#: `s8-ops-01` 的题面更进一步写着「请求 as_of 之后的数据会被拒」——
#: 照字面读，冻结线之前都合法，而事实相反。**这是题面欠定，不是 agent 错**：
#: 2026-09-05 核过两臂与共享文件，没有任何一处说得出这条耦合。
#: **不用 markdown 强调**（E14：显著性由 E11/E12 管，不许用排版绕回来）。
S8_AS_OF_NOTE = (
    "；本阶段网关接受的 as_of 上界等于当前 sim_date，不是上面这个日期。"
    "推进（POST /sim/advance）之后上界才前移；在推进之前请求 sim_date 之后的数据"
    "会被拒绝并计入越权。首个 sim_date 等于窗口起始日")


def _as_of_phrase(stage: str, as_of: str) -> str:
    return f"{as_of}{S8_AS_OF_NOTE}" if stage == "S8" else as_of


def _endpoints_phrase(stage: str) -> str:
    return " ".join(stage_endpoints(stage))


def _output_files_phrase(stage: str, profile: str | None = None) -> str:
    """从 schema 的 `files` 节生成「产出文件」固定槽（N-44）。**两臂同给、机器生成。**

    先前 `values_ref.sha256` / `panel_ref.sha256` 是被计分的量，而题面从没说
    「哪个文件、什么格式、怎么排序」—— 两个同样正确的实现字节不同，比对本就不成立。
    这句话把规范形写进题面：路径、格式、列序、排序键、索引，一条都不能省。
    """
    specs = sch.payload_files(stage, profile)
    if not specs:
        return ""
    out = []
    for f in specs:
        cols = "、".join(f["columns"])
        bits = [f"{f['path']}（{f['format']}）", f"列按此顺序：{cols}",
                f"按 {'、'.join(f['sort'])} 升序排序", "不写行索引" if not f.get("index") else "写行索引"]
        if f.get("dtypes"):
            bits.append("；".join(f"{k} 为 {v}" for k, v in f["dtypes"].items()))
        if f.get("float_format"):
            bits.append(f"浮点按 {f['float_format']} 格式化")
        if f.get("header"):
            bits.append("首行为列名")
        if f.get("encoding"):
            bits.append(f"编码 {f['encoding']}")
        out.append("，".join(bits))
    return "；另外交出 ".join([out[0]] + out[1:]) if len(out) > 1 else out[0]


def _expected_null_findings(behavior: str, is_probe: bool) -> list[str]:
    if behavior == "empty":
        return ["payload_missing", "declarations_missing"]
    if behavior == "default_fill":
        return ["silent_completion"] if is_probe else ["declaration_mismatch"]
    return ["s1_fetches_missing", "payload_missing"]


# ============================================================== 文件级规则

# ============================================================== 落盘（数据面）

def write_task(b: Built, reference_root: Path, *, capabilities: dict | None = None) -> Path:
    """数据面全量落盘。**私有文本文件都植入 gold_token**（G3，taskspec.json 除外——它只许四键）。

    自查（high）：E9c/E9d2 原先挂在 `task["status"] != "draft"` 上，而 build_task 硬编码 status="draft" ——
    生产路径上两条锁**永远不触发**。门槛因此移到**落盘这个动作**上：探针题要落盘，必须锁翻绿且有实测证据。
    """
    if not b.ok:
        raise PackError("有问题的任务不落盘：\n  " + "\n  ".join(b.problems))
    t = b.task
    if t["kind"] == "underdetermined_probe":
        # 逐字段**带条件**（裁定 2026-09-03）：materiality 依赖任务其余声明，
        # 一个条件下的结论不能搬到另一个条件上用。
        pf = (t["underdetermined"] or [None])[0]
        cond = S.evidence_condition(pf, t["declared"])
        basis = S.evidence_for(pf, t["declared"]) or S.static_material_rule(pf, t["declared"])
        if not basis:
            raise PackError(f"E9c/E9d2 探针题 {t['task_id']} 不落盘：字段 {pf} 在条件 {cond or '（无条件）'} 下"
                            f"既无 screen 实测记录、也无 FIELD_MATERIAL_WHEN 静态规则 —— "
                            f"先跑 ops/run_materiality_screen.py 或补静态前提")
    d = Path(reference_root) / "tasks" / t["set_id"] / t["task_id"]
    for sub in ("solution", "gold", "arms"):
        # 裸 mkdir 的中间层只受 umask 管（本机 002 → **0775 的答案面目录**，红线 5）。
        # `cfg.create_dir` 保证**每一新建层级**都是 0700，包括 set 级那层 ——
        # `_ledger.jsonl` 就住在那里。2026-09-04 实测踩到，见 N-61。
        cfg.create_dir(d / sub)
    g = t["canary"]["gold_token"]
    _w(d / "task.yaml", f"# gold_token: {g}\n" + yaml.safe_dump(t, allow_unicode=True, sort_keys=False))
    _w(d / "taskspec.json", json.dumps(S.taskspec(t), ensure_ascii=False, indent=1))
    _w(d / "scorer.yaml", b.scorer_yaml)
    _w(d / "canary.json", json.dumps({**t["canary"], "note": f"gold_token {g} 只许出现在数据面"}, indent=1))
    _w(d / "solution" / "solve.py", b.solve_py)
    _arms = b.arms or {"strict": b.strict, "open": b.open}
    for _a, _r in _arms.items():
        _w(d / "arms" / f"INSTRUCTION.{_a}.md", _r.text)
    _w(d / "arms" / "slots.json", json.dumps({"gold_token": g, **{a: r.phrases for a, r in _arms.items()}}, ensure_ascii=False, indent=1))
    _w(d / "arms" / "equivalence.md", R.equivalence_table(t, b.strict, b.open, b.review, b.task_level,
                                                          exceptions=b.arm_exceptions,
                                                          extra_arms={a: r for a, r in _arms.items()
                                                                      if a not in ("strict", "open")})
       + f"\n<!-- gold_token: {g} -->\n")
    _w(d / "image.Dockerfile", b.dockerfile)
    _w(d / "tests_test_outputs.py", b.tests_py)
    ledger = Path(reference_root) / "tasks" / t["set_id"] / "_ledger.jsonl"
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(b.ledger_entry, ensure_ascii=False) + "\n")
    ledger.chmod(0o600)          # 它在 d 之外，下面那圈 rglob 收不到
    for p in d.rglob("*"):
        p.chmod(0o700 if p.is_dir() else 0o600)
    d.chmod(0o700)
    return d


def _w(p: Path, text: str) -> None:
    cfg.create_dir(p.parent)
    p.write_text(text, encoding="utf-8")
    p.chmod(0o600)


#: 数据面目录里的文件分三类。**类别是封闭的**：出现不在任何一类里的文件本身就是 G3 违规
#: （一个没归类的文件，既不知道它能不能出去，也不知道它有没有植入金丝雀 —— D-06 形状）。
PRIVATE_ONLY_FILES: frozenset[str] = frozenset({
    "task.yaml", "scorer.yaml", "canary.json", "solution/solve.py", "arms/equivalence.md", "arms/slots.json",
})                      # 必须含 gold_token，永不出数据面
#: 会原样进执行面：**不得**含 gold_token。题面那几条**按臂注册表展开**（卡 4.1）——
#: 写死两条的话，第三个臂的题面会被判成「未归类」而整份题导不出去。
#: 用 `ALL_ARMS` 而不是 `ARMS`：非默认臂只有显式点名才渲染，但**一旦渲染出来它就是题面**。
EXPORTED_FILES: frozenset[str] = frozenset(
    {f"arms/INSTRUCTION.{_a}.md" for _a in S.ALL_ARMS}
    | {"image.Dockerfile", "tests_test_outputs.py"})
KEY_ONLY_FILES: frozenset[str] = frozenset({"taskspec.json"})   # 只许四键，不得含 gold_token


def _oracle_products(stage: str) -> set[str]:
    """该阶段 oracle/agent 会写出的 payload 文件名（`reference.artifact_schema.PAYLOAD_FILES`）。
    生成器本来就 import reference（只在 f01 跑），这里同源。"""
    from reference.artifact_schema import PAYLOAD_FILES
    return {Path(f["path"]).name for f in PAYLOAD_FILES.get(stage, ())}


def check_private_files(task_dir: Path) -> list[str]:
    """G3：私有文件含 gold_token、会导出的文件不含、taskspec 只四键、没有未归类文件；G1：目录 0700。"""
    bad = []
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    g = task["canary"]["gold_token"]
    products = _oracle_products(task["stage"])
    for p in sorted(task_dir.rglob("*")):
        if p.is_dir():
            continue
        rel = str(p.relative_to(task_dir))
        if rel.startswith("gold/"):
            continue                                  # gold 切片由 manifest 与 parquet metadata 管
        if rel.startswith("solution/") and rel != "solution/solve.py":
            # oracle 跑批的产物（`solution/artifact.json` / `artifact.null.json`）：**答案面**，
            # 不进 bundle（export_task 只复制 X 面），也不含 gold_token（它是 oracle 的输出，
            # 不是模板）。原来这里对它报「未归类」，于是任何跑过 oracle 的题都导不出去（2026-09-05）。
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if rel in PRIVATE_ONLY_FILES:
            if g not in text:
                bad.append(f"G3 私有文件 {rel} 不含 gold_token")
        elif rel in EXPORTED_FILES or rel in KEY_ONLY_FILES:
            if g in text:
                bad.append(f"G3 {rel} 会进执行面/只许四键，却含 gold_token")
        elif p.name in products:
            # oracle 跑出来的 payload 文件（`PAYLOAD_FILES` 同名：values.parquet / panel.csv / ledger.parquet…）。
            # oracle 与 agent 同一份 I/O 契约（D-31），所以它落在题目录里的 work/ 或题根 —— **答案面**，
            # 不出集、也不含 gold_token（它是 oracle 的输出，不是模板）。N-109：名叫 work 的目录里有 gold，
            # 判据必须写在这里，不能靠人记得。
            continue
        elif rel.startswith("work/"):
            # 题面 `inputs[]` 声明的夹具及其伴生文件（.meta.json / inputs/manifest.json）：**X 面**，随 bundle
            # 出去（`export_task`），所以不得含 gold_token。2026-09-05 之前没有任何夹具存在，这一类从未出现过。
            if g in text:
                bad.append(f"G3 {rel} 会随 bundle 进执行面，却含 gold_token")
        else:
            bad.append(f"G3 未归类的文件 {rel} —— 不知道它能不能出数据面")
    # 自查：原先只查顶层目录一处 —— arms/ solution/ gold/ 与每个文件的权限完全不查。
    for p_ in [task_dir, *sorted(task_dir.rglob("*"))]:
        m = p_.stat().st_mode & 0o777
        want = 0o700 if p_.is_dir() else 0o600
        if m != want:
            bad.append(f"G1 {p_.relative_to(task_dir.parent)} 权限 {oct(m)} ≠ {oct(want)}")
    return bad


# ============================================================== 导出（执行面）

def channel_inputs(task: dict, task_dir: Path, x: dict, channel: str) -> dict:
    """按通道决定导出的 X `task.yaml` 里 `inputs[].sha256` 写什么（N-605，裁定 ①）。

    **private：逐字节不变。** 声明什么就是什么 —— 夹具与声明不符由下面那道身份闸拦，
    那正是 N-84 立的规矩（「题面就是夹具的身份」）。

    **public：写盘上真值。** 公开夹具由公开 provider 重算，字节与私有的**必然不同**；
    而两条通道的题面来自同一张参数表，声明值只有一个（私有那个）。
    拿私有声明去核公开字节 = 公开通道 5 道带 `inputs` 的题一道都出不了集。

    公开链的防漏闸**不是删掉那道闸，是把它反过来用**：公开夹具的 sha **等于**
    私有声明值，意味着私有那一份漏进了公开树（或者公开 provider 根本没生效）——
    当场红。这条判据比原来那条更有牙：原来那条只说「不一样就红」，
    而公开通道上「不一样」是正常的，真正该红的是「一样」。
    """
    if channel != "public":
        return x
    xs = deepcopy(x)
    for item in (xs.get("inputs") or []):
        p = Path(task_dir) / item["path"]
        if not p.is_file():
            continue            # 「声明了却没生成」由出集入口拦（见 export_task 末尾那段注释）
        real = _sha(p.read_bytes())
        want = item.get("sha256")
        if want and real == want:
            raise PackError(
                f"公开通道的夹具 {item['path']} 与**私有声明**逐字节相同（{real[:12]}…）—— "
                f"这意味着私有那一份漏进了公开树，或者公开 provider 根本没生效。"
                f"两条通道的夹具由各自的 provider 重算，字节相同不是巧合。不出集。")
        item["sha256"] = real
    return xs


def export_task(task_dir: Path, runner_root: Path, *, channel: str | None = None) -> Path:
    """剥 D 键落执行面 bundle。X task.yaml 键集 == X_KEYS（G4），三串金丝雀各归各位。

    `channel`：`None` = 取 `GENEBENCH_CHANNEL`（默认 `private`，**行为与本参数不存在时
    逐字节相同**）。公开通道的差别只有一处 —— 夹具身份按 `channel_inputs` 的口径判。
    """
    ch = cfg.assert_channel(channel)
    task = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
    x = channel_inputs(task, task_dir, S.x_view(task), ch)
    x["status"] = "exported"
    out = Path(runner_root) / "tasks" / task["task_id"]
    cfg.create_dir(out / "arms")
    cfg.create_dir(out / "image" / "tests")
    cfg.create_dir(out / "work")
    _w(out / "task.yaml", f"# x_token: {task['canary']['x_token']}\n" + yaml.safe_dump(x, allow_unicode=True, sort_keys=False))
    # **按这份 task.yaml 自己记的臂集合**搬题面，不按常量 —— 显式多渲染了非默认臂的题，
    # 出集要把那些臂一起带走；只渲染了默认两臂的题，这里与 `S.ARMS` 等价（逐字节不变）。
    for a in task["instruction"]:
        _w(out / "arms" / f"INSTRUCTION.{a}.md", (task_dir / "arms" / f"INSTRUCTION.{a}.md").read_text(encoding="utf-8"))
    _w(out / "image" / "Dockerfile", (task_dir / "image.Dockerfile").read_text(encoding="utf-8"))
    _w(out / "image" / "tests" / "test_outputs.py", (task_dir / "tests_test_outputs.py").read_text(encoding="utf-8"))
    # 有档位的题，共享结构文件按该题生成（两臂同一份 —— 这才是要守的不变量）；
    # 没档位的照抄阶段级 spec，测试防漂。
    if task.get("payload_profile"):
        _w(out / "work" / f"{task['stage']}.json",
           json.dumps(sch.json_schema(task["stage"], task["payload_profile"]), ensure_ascii=False, indent=1) + "\n")
    else:
        schema_src = Path(__file__).resolve().parents[1] / task["artifact_schema_ref"]
        if schema_src.exists():
            _w(out / "work" / f"{task['stage']}.json", schema_src.read_text(encoding="utf-8"))
    # 协议工件的**逐题规则**（GQ 臂用）。生成器 import reference，所以只能在 f01 跑；
    # 注入器搬已经生成好的文件。放在 bundle 的 work/protocol/ 下 —— 两臂都带着它，
    # 但只有 strict 臂会被注入器搬进 run dir（open 臂不放，见 §6.2 的等号判据）。
    from genetask import protocol_rules as _pr
    _pr.write_rules(task, out / "work" / "protocol")
    # 夹具随 bundle：题目录 work/ 下除 oracle 产物之外的一切（题面 `inputs[]` 声明的文件及其伴生文件）。
    # 声明了 sha256 的逐个核对 —— 题面就是它的身份（N-84）；声明了却不在题目录里的，不出集（夹具没生成）。
    products = _oracle_products(task["stage"])
    # **按导出的那一份判**（不是按答案面那一份）：私有通道两者逐字相同；
    # 公开通道 `channel_inputs` 已经把真值写进去了，这里因此变成一道恒真的复核 ——
    # 真正的公开判据在 `channel_inputs` 里（与私有声明相同即红）。
    declared = {i["path"]: i.get("sha256") for i in (x.get("inputs") or [])}
    src_work = task_dir / "work"
    if src_work.is_dir():
        for p in sorted(src_work.rglob("*")):
            if not p.is_file() or p.name in products:
                continue
            rel = str(p.relative_to(task_dir))
            raw = p.read_bytes()
            want = declared.get(rel)
            if want and _sha(raw) != want:
                raise PackError(f"夹具 {rel} 的 sha256 与题面声明不符（{_sha(raw)[:12]}… ≠ {want[:12]}…）—— 不出集")
            dst = out / rel
            cfg.create_dir(dst.parent)
            dst.write_bytes(raw)
            dst.chmod(0o600)
    # 「声明了却没生成」不在这里拦：本函数只是搬运；出集的唯一入口 ops/export_bundle.py 负责核对
    # 每个声明的输入都真的在 bundle 里（那里是 ExportBlocked）。单测里按 params 建的题没跑过夹具生成器，
    # 让 export_task 自己拦会把测试逼成「先造假夹具」（D-33 的反面）。
    return out


def gold_sha_set(task_dir: Path) -> set[str]:
    """G2 的比对集：gold 切片 + 私有文件（会原样导出的文件天然与 bundle 相同，不算）。"""
    out = set()
    for p in task_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(task_dir))
        if rel.startswith("gold/") or rel in PRIVATE_ONLY_FILES or rel in KEY_ONLY_FILES:
            out.add(_sha(p.read_bytes()))
    return out


def check_export(bundle_dir: Path, gold_sha_set: set[str], canary: dict) -> list[str]:
    """G2 bundle 无 gold 文件；G4 X 键集精确、x_token 只在 task.yaml；C1 控制串每臂恰一次；G3 gold_token 零命中。"""
    bad = []
    x = yaml.safe_load((bundle_dir / "task.yaml").read_text(encoding="utf-8"))
    if set(x) != set(S.X_KEYS):
        bad.append(f"G4 X task.yaml 键集 ≠ X_KEYS：缺 {sorted(set(S.X_KEYS) - set(x))}，多 {sorted(set(x) - set(S.X_KEYS))}")
    for p in sorted(bundle_dir.rglob("*")):
        if p.is_dir():
            continue
        rel = str(p.relative_to(bundle_dir))
        if rel not in X_ALLOWED_FILES and not rel.startswith(X_ALLOWED_PREFIXES):
            bad.append(f"G4 执行面出现不允许的文件 {rel}")
        data = p.read_bytes()
        if _sha(data) in gold_sha_set:
            bad.append(f"G2 执行面文件 {rel} 与某个 gold 文件逐字节相同")
        text = data.decode("utf-8", errors="replace")
        if canary["gold_token"] in text:
            bad.append(f"G3 执行面文件 {rel} 含 gold_token")
        if rel != "task.yaml" and canary["x_token"] in text:
            bad.append(f"G4 x_token 出现在 {rel}（只许在 task.yaml）")
    for a in x["instruction"]:
        n = (bundle_dir / "arms" / f"INSTRUCTION.{a}.md").read_text(encoding="utf-8").count(canary["control_token"])
        if n != 1:
            bad.append(f"C1 {a} 臂控制串出现 {n} 次")
    return bad


# ============================================================== 通行证（卡 4.3 §4）
_DIGEST_RE = re.compile(r"@(sha256:[0-9a-f]{64})")


#: `FROM <repo>[:tag]@<digest>` 的 repo 部分。钉 digest 时可一并把 repo 换成执行面上
#: 真有的那个镜像名（2026-09-05 通宵：统一基座还没建，A1 先在现有 harness 镜像上跑，
#: 偏离记进报告）。**只换 repo，不动别的**；不给就照旧只换 digest。
_FROM_RE = re.compile(r"(?im)^(FROM\s+)([^\s@]+)(@sha256:[0-9a-f]{64}|@" + re.escape(IMAGE_DIGEST_PLACEHOLDER) + r")")


def pin_image_digest(bundle_dir: Path, digest: str, *, image: str | None = None) -> list[str]:
    """把 bundle 里 Dockerfile 的**占位** digest 换成真 digest。空列表 = 成功。

    为什么需要这个函数（卡 4.3 P4b 实测发现，2026-09-04）：模板里写的是
    `IMAGE_DIGEST_PLACEHOLDER`，注释说「真 digest 在 f02 export 时钉」——
    但 `export_task` 并不钉，也没有别的地方钉。**门（P4b）有了，门后没有实现者**：
    注入器会拦下每一个 bundle，而拦下的理由是一件本该有人做却没人做的事。

    必须在 `export_manifest` **之前**调用 —— 通行证记的是钉好之后的 sha256。
    """
    digest = str(digest)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        return [f"digest 形状不对：{digest[:24]}… —— 必须是 sha256: + 64 位十六进制"]
    if digest == IMAGE_DIGEST_PLACEHOLDER:
        return ["拒绝把 digest 钉成占位值本身 —— 那等于没钉"]
    df = Path(bundle_dir) / "image" / "Dockerfile"
    text = df.read_text(encoding="utf-8")
    if IMAGE_DIGEST_PLACEHOLDER not in text:
        got = _DIGEST_RE.findall(text)
        return [] if got else [f"Dockerfile 里既没有占位 digest 也没有真 digest：{df}"]
    text = text.replace(IMAGE_DIGEST_PLACEHOLDER, digest)
    if image:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*(:[A-Za-z0-9._-]+)?", image):
            return [f"镜像名形状不对：{image!r}"]
        text, n = _FROM_RE.subn(lambda m: f"{m.group(1)}{image}{m.group(3)}", text)
        if n != 1:
            return [f"FROM 行改名失败：命中 {n} 处（要恰好 1 处）"]
    df.write_text(text, encoding="utf-8")
    return []


def export_manifest(task_dir: Path, bundle_dir: Path, *,
                    check_export_result: list[str],
                    frozen_ref: dict, reference_ref: dict | None = None) -> dict:
    """**f01 侧**：给一个已经过 `check_export` 的 bundle 发通行证。

    为什么要有这东西（§1.2）：`check_export` 的两个入参（`gold_sha_set`、`canary`）
    **都是数据面机密**，f02 上不能调它。所以完整性判据必须在 f01 算好、随 bundle 搬过去，
    f02 只做**纯比对**（`check_manifest`）。

    `check_export_result` 非空时**拒绝出清单** —— 不给红的 bundle 发通行证。
    这条不是礼貌性检查：通行证一旦发出，f02 侧就没有任何别的手段能发现 bundle 是红的。

    `frozen_ref`：本次构建所依据的冻结清单引用（`ops/freeze_v10.frozen_ref()`，
    裁定 2026-09-04）。注入器拿它核「这个 bundle 是不是用漂了的模板构建的」——
    冻结防漂断言只活在测试套里，**运行时缺这道门，漂了的模板照样进容器**。
    """
    if check_export_result:
        raise PackError(f"check_export 有 {len(check_export_result)} 条红，拒绝出通行证："
                        f"{check_export_result[:3]}")
    # 冻结引用**必填**：做成可选默认 None 的话，忘了传就等于整道门消失，
    # 而"忘了传"不会有任何提示（红队 2026-09-04，high）。
    if not (frozen_ref or {}).get("root"):
        raise PackError("frozen_ref 必须带 root —— 不记冻结清单根的通行证等于没有这道门")
    files = {}
    for p in sorted(bundle_dir.rglob("*")):
        if p.is_file():
            files[str(p.relative_to(bundle_dir))] = _sha(p.read_bytes())
    x = yaml.safe_load((bundle_dir / "task.yaml").read_text(encoding="utf-8"))
    return {
        "manifest_version": MANIFEST_VERSION,
        "task_id": x["task_id"], "set_id": x["set_id"], "stage": x["stage"],
        "packager_version": S.PACKAGER_VERSION,
        "allowed_files": list(X_ALLOWED_FILES), "allowed_prefixes": list(X_ALLOWED_PREFIXES),
        "check_export": [],                      # 空 = 绿；上面已保证
        "frozen_manifest": dict(frozen_ref),
        # **参考面的引用**（裁定 2026-09-05：两条版本轴）。可选是为了让既有调用方不当场炸，
        # 但 `ops/test_genetask.py` 有一条盯着「真流程里必须传」——
        # 默认 None 若无人盯，就等于这条轴从来没被记过。
        "reference_manifest": dict(reference_ref or {}),
        "files": files,
    }


# ============================================================== O1 / N1

def LEGAL_SKELETON(task: dict) -> dict:
    """拿卡 2.3 的合法样例当骨架（结构层用）——F1 要的是「结构对、只有声明被静默补全」的产物。"""
    from reference import artifact_samples as _smp
    base = deepcopy(_smp.LEGAL[task["stage"]].artifact)
    base["config_id"] = "filler"
    return base


def null_artifact(task: dict, behavior: str) -> dict:
    """按 behavior 生成 null_agent 的产物（用于 N1 判别力验收）。"""
    base = {"schema_version": sch.SCHEMA_VERSION, "artifact_id": f"{task['task_id']}-null", "stage": task["stage"],
            "task_id": task["task_id"], "config_id": "null", "arm": "strict", "seed": 0, "as_of": task["as_of"],
            "produced_at": _now(), "provenance": []}
    if behavior == "empty":
        return base
    if behavior == "default_fill":
        decl = deepcopy(task["declared"])
        # 欠定字段静默补一个「默认值」；已声明字段改一个口径
        for f in task["underdetermined"]:
            decl[f] = _some_default(f)
        if not task["underdetermined"]:
            f = next(iter(decl))
            decl[f] = _some_other(f, decl[f])
        return {**base, "declarations": decl, "payload": {}}
    if behavior == "default_fill_minus_probe":
        # 卡 4.2 §18.2 的第三桩：declarations **齐**，只把欠定字段的键**删掉**。
        # 存在的理由：`empty` 停在更外层的 `declarations_missing`，
        # 覆盖不到 `underdetermined_field_missing` —— §4 规则 (b) 因此没有正例。
        decl = deepcopy(task["declared"])
        for f in task["underdetermined"]:
            decl.pop(f, None)
        return {**base, "declarations": decl, "payload": {}}
    return {**base, "declarations": deepcopy(task["declared"]), "payload": {"copied": True}}


def _some_default(f: str):
    enum = sch.DECLARATION_ENUMS.get(f)
    if enum:
        return enum[0]
    return {"holding_periods": [1, 5, 20], "lookback": 20}.get(f, "default")


def _some_other(f: str, cur):
    """给 O1 用的**必然不同**的值：枚举取另一个；字符串加后缀；数加一；列表加元素；dict 加键。"""
    enum = sch.DECLARATION_ENUMS.get(f)
    if enum:
        for v in enum:
            if v != cur:
                return v
    if isinstance(cur, bool):
        return not cur
    if isinstance(cur, (int, float)):
        return cur + 1
    if isinstance(cur, str):
        return cur + "_x"
    if isinstance(cur, list):
        return [*cur, "extra"] if cur and isinstance(cur[0], str) else [*cur, 99]
    if isinstance(cur, dict):
        return {**cur, "extra": 1}
    return cur


def filler_artifact(task: dict) -> dict:
    """**F1 对照 agent**：把每个欠定字段填上「最合理的默认值」并把数**照常算出来**。

    为什么 N1/O1 不够（签字裁定 2026-09-03）：null_agent 什么都不产出 → 畸形，**根本没走静默补全那条路**；
    oracle 诚实终止 → 走的是正确路径。两者都没碰探针真正要抓的行为。
    materiality 只证明**字段本身**有效；F1 证明**整条判定链**（schema → 校验器 → 闸门 → scorer 三态）
    对静默补全真的会响。
    """
    base = deepcopy(LEGAL_SKELETON(task))
    decl = deepcopy(task["declared"])
    for f in task["underdetermined"]:
        decl[f] = _some_default(f)              # 最合理的默认值 —— 一个称职的 agent 会这么填
    base["declarations"] = decl
    base["task_id"] = task["task_id"]
    return base


def check_filler(task: dict) -> list[str]:
    """F1：填了默认值并出数的产物**必须**触发 silent_completion，且效果分记 invalid。"""
    if not task["underdetermined"]:
        return []
    art = filler_artifact(task)
    assert_mutated({"declarations": {**task["declared"], **{f: None for f in task["underdetermined"]}}},
                   {"declarations": art["declarations"]}, "F1 default_filler")
    v = sch.validate(art, task=S.taskspec(task))
    bad = []
    if "silent_completion" not in v.codes:
        bad.append(f"F1 default_filler 没有触发 silent_completion（实得 {sorted(v.codes) or '全绿'}）—— "
                   f"整条判定链对静默补全不响，探针题的判别力是空的")
    if "underdetermined" not in v.gate_failed:
        bad.append(f"F1 silent_completion 没有进 underdetermined 闸门（gate_failed={v.gate_failed}）")
    # 效果分：闸门失败 → scorer 必须记 invalid 且 effect 为 null
    sc = {"schema_version": sch.SCHEMA_VERSION, "validity": "invalid", "gate_failed": v.gate_failed,
          "correctness": {"placeholder": 1.0}, "effect": None}
    # **显式传 `anchor_status`**（2026-09-05）：不传就吃默认 `"fixed"` ——
    # 而 `anchor.status="pending"` 的题（自由发挥题、卡 5.4 前）要求 valid 也
    # `effect: null`。吃默认的后果是「pending 的题按 fixed 判」，两边都不报。
    sv = sch.validate_scorer_output(sc, anchor_status=str(
        (task.get("anchor") or {}).get("status", "fixed")))
    if not sv.ok:
        bad.append(f"F1 对应的 scorer 输出不合法：{[str(f) for f in sv.findings][:2]}")
    return bad


def check_null(task: dict) -> list[str]:
    """N1：null 产物必须 ≥1 finding 且 ⊆ expected_findings。"""
    art = null_artifact(task, task["null_agent"]["behavior"])
    if task["null_agent"]["behavior"] == "default_fill":
        assert_mutated({"declarations": task["declared"]}, {"declarations": art.get("declarations")}, "N1 default_fill")
    v = sch.validate(art, task=S.taskspec(task))
    if v.ok:
        return ["N1 null_agent 的产物居然通过了校验 —— 题目没有判别力"]
    exp = set(task["null_agent"]["expected_findings"])
    if not v.codes & exp:
        return [f"N1 null 产物的 findings {sorted(v.codes)} 与预期 {sorted(exp)} 无交集"]
    return []


def assert_mutated(before, after, what: str = "突变") -> None:
    """靠突变证明判别力的地方，突变函数本身要先证明**至少改变了一个字节**（2026-09-02 签字修正）。

    否则突变空转、判别力测试恒绿 —— D-06 家族的又一形态：不是产物静默错，是**测试静默空**。
    O1 的 v1 就栽在这里（无枚举字段的 _some_other 返回原值）。
    """
    if S.canonical_json(before) == S.canonical_json(after):
        raise PackError(f"{what}空转：突变前后逐字节相同，判别力测试会恒绿")


def check_oracle(task: dict, oracle_artifact: dict) -> list[str]:
    """O1：oracle 产物零 finding；且做一次已知突变必须变红（否则校验是空的）。"""
    ts = S.taskspec(task)
    v = sch.validate(oracle_artifact, task=ts)
    bad = []
    if not v.ok:
        bad.append("O1 oracle 产物没过校验：" + "; ".join(str(f) for f in v.findings[:5]))
    mut = deepcopy(oracle_artifact)
    if task["underdetermined"]:
        f = task["underdetermined"][0]
        mut["declarations"][f] = _some_default(f)          # 探针题：填默认值必须红
        want = "silent_completion"
    else:
        f = next(iter(task["declared"]))
        mut["declarations"][f] = _some_other(f, task["declared"][f])
        want = "declaration_mismatch"
    assert_mutated(oracle_artifact, mut, f"O1 对 {f} 的突变")
    vm = sch.validate(mut, task=ts)
    if want not in vm.codes:
        bad.append(f"O1 已知突变（{f}）没有让校验变红（期望 {want}，实得 {sorted(vm.codes)}）—— 校验为空")
    return bad


# ============================================================== CLI

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["build", "export"])
    p.add_argument("--params")
    p.add_argument("--out")
    p.add_argument("--task")
    p.add_argument("--runner")
    p.add_argument("--capabilities")
    a = p.parse_args()
    caps = json.loads(Path(a.capabilities).read_text()) if a.capabilities else None
    if a.cmd == "build":
        rows = load_params(a.params)
        built = [build_task(r, capabilities=caps) for r in rows]
        bad = S.validate_set([b.task for b in built], require_full=True)   # 出包本来就该是完整集
        for b in built:
            print(("OK  " if b.ok else "BAD ") + b.task["task_id"] + ("" if b.ok else "\n    " + "\n    ".join(b.problems)))
        for x in bad:
            print("SET " + x)
        if a.out and all(b.ok for b in built) and not bad:
            for b in built:
                print("写出", write_task(b, Path(a.out)))
        return 0 if all(b.ok for b in built) and not bad else 1
    out = export_task(Path(a.task), Path(a.runner))
    print("导出", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
