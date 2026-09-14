"""执行面（f02）用得到的 bundle 判据 —— **零 `reference/` 依赖**。

为什么单独一个模块（与 `genetask/pin.py` 同一个理由，卡 4.3 §1.1 的第二个实例）：
`genetask/packager.py` 顶层 `from genetask import schema as S`，而 `schema.py` 顶层
`from reference import artifact_schema` —— 在 f02 上 `import genetask.packager`
会把**答案面**拖上执行面，直接撞红线「reference/ 与 scorer/ 产物不对执行面暴露」。

§1.1 挡下了 `check_provider_pin`，但 §2 又把 `check_manifest` 放回了 `packager.py`；
这是同一个疏忽形态的第二次（**规格自己也会漏**）。判据放这里，`packager.py` 再导出，
`genetask.packager.check_manifest` 这个路径照样成立。

**零依赖的边界是可测的**：`ops/test_inject.py` 用 AST 扫本模块与 `runner/inject.py` 的
import 图，出现 `reference` 即红 —— 不靠"记得别 import"。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

#: 臂名**不再是常量** —— 见本文件末尾的臂注册表（卡 4.1）。
#: 源头是 `genetask/arms.yaml`；`schema.ARMS` 从这里再导出（那边拉 reference，
#: f02 上不能 import 它，所以解析器住在本模块）。`ops/test_genetask.py`
#: 断言两者相等的那条因此变成恒真 —— 留着：它钉的是「只有一个源头」这件事。

X_ALLOWED_FILES = ("task.yaml",)
X_ALLOWED_PREFIXES = ("arms/", "image/", "work/")
IMAGE_DIGEST_PLACEHOLDER = "sha256:" + "0" * 64

#: 通行证的版本。改结构必须改它 —— f02 侧遇到不认识的版本要红，而不是按老结构解析。
MANIFEST_VERSION = "1.0"


class PackError(ValueError):
    pass


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def lint_dockerfile(text: str) -> list[str]:
    """L1：FROM 带 digest；无 ADD http；无运行期 pip；COPY/ADD 源只能在 image/ 内。"""
    bad: list[str] = []
    froms = [l for l in text.splitlines() if l.strip().upper().startswith("FROM ")]
    if not froms:
        bad.append("L1 Dockerfile 没有 FROM")
    for l in froms:
        if not re.search(r"@sha256:[0-9a-f]{64}", l):
            bad.append(f"L1 FROM 必须带 digest：{l.strip()}")
    for l in text.splitlines():
        s = l.strip()
        if re.match(r"(?i)^ADD\s+https?://", s):
            bad.append(f"L1 禁止 ADD 远程 URL：{s}")
        if re.search(r"\b(pip3?|apt(-get)?|apk|npm)\s+(install|add)\b", s) and s.upper().startswith("RUN"):
            # 构建期装依赖允许（构建时联网）；运行期（CMD/ENTRYPOINT）不允许
            pass
        if re.match(r"(?i)^(CMD|ENTRYPOINT)\b", s) and re.search(r"\b(pip3?|apt(-get)?|apk|npm)\s+(install|add)\b", s):
            bad.append(f"L1 运行期装依赖：{s}")
        m = re.match(r"(?i)^(COPY|ADD)\s+(?:--\S+\s+)*(\S+)\s+\S+", s)
        if m:
            src = m.group(2)
            if src.startswith(("/", "..")) or "/../" in src or src.startswith("../"):
                bad.append(f"L1 COPY/ADD 源越出构建上下文 image/：{s}")
    return bad


_FORBIDDEN_IN_TESTS = ("reference", "gold", "answer", "probe", "memory_probe")


def _check_tests_source(text: str) -> list[str]:
    """G5：容器内 tests 不得 import reference.*、不得出现 gold/answer/probe 字样。"""
    bad = []
    if re.search(r"^\s*(from|import)\s+reference\b", text, re.M):
        bad.append("G5 tests 里 import 了 reference.*")
    for w in _FORBIDDEN_IN_TESTS:
        # 自查：`\b` 把下划线当单词字符 —— gold_ref / gold_token / probe_field 全逃掉。
        if re.search(rf"(?<![A-Za-z0-9]){w}(?![A-Za-z0-9])", text, re.I):
            bad.append(f"G5 tests 里出现禁用字样 {w!r}")
    return bad



#: 显式放弃冻结核验的哨兵。**必须显式写出来**，不能靠默认参数悄悄关掉。
SKIP_FROZEN_CHECK = "__SKIP_FROZEN_CHECK__"


def check_manifest(bundle_dir: Path, manifest: dict, *, expect_frozen_root: str) -> list[str]:
    """**f02 侧**：纯比对，不需要任何机密。空列表 = 绿。

    比五件事：① 通行证版本认得；② 文件集**精确相等**（多一个、少一个都是红）；
    ③ 每个 sha256 相等；④ 每条路径命中允许前缀；⑤ 通行证里 `check_export` 结论为空。

    第六件（裁定 2026-09-04）：`expect_frozen_root` 给了就核冻结清单根 —— 不一致记
    `frozen_manifest_mismatch`。**这是运行时那道门**：测试套里的防漂断言只在 f01 跑，
    bundle 一旦搬到 f02 就没人再问它是用哪个版本的模板构建的了。
    """
    bad: list[str] = []
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        return [f"通行证版本 {manifest.get('manifest_version')!r} ≠ {MANIFEST_VERSION} —— "
                f"不按老结构解析，直接红"]
    if manifest.get("check_export"):
        bad.append(f"通行证里 check_export 非空（{len(manifest['check_export'])} 条）—— "
                   f"这份 bundle 在 f01 就是红的")
    want = dict(manifest.get("files") or {})
    got = {str(p.relative_to(bundle_dir)): _sha(p.read_bytes())
           for p in sorted(bundle_dir.rglob("*")) if p.is_file()}
    for rel in sorted(set(want) - set(got)):
        bad.append(f"bundle 少文件 {rel}")
    for rel in sorted(set(got) - set(want)):
        bad.append(f"bundle 多文件 {rel} —— 通行证没记它，来路不明")
    for rel in sorted(set(want) & set(got)):
        if want[rel] != got[rel]:
            bad.append(f"bundle 文件 {rel} 的 sha256 与通行证不符")
    # G4 的允许集取**模块常量**，不取通行证自报的那两个字段：通行证跟着 bundle 一起搬，
    # 改通行证就能放宽白名单，等于让被查的一方定义什么叫合规（红队 2026-09-04，high）。
    # 通行证里那两个字段只作**记录**，与常量不符即红。
    for rel in sorted(got):
        if rel not in X_ALLOWED_FILES and not rel.startswith(X_ALLOWED_PREFIXES):
            bad.append(f"G4 bundle 里 {rel} 不在允许集 {X_ALLOWED_FILES}+{X_ALLOWED_PREFIXES}")
    if tuple(manifest.get("allowed_files") or ()) != X_ALLOWED_FILES or \
            tuple(manifest.get("allowed_prefixes") or ()) != X_ALLOWED_PREFIXES:
        bad.append(f"通行证记的允许集与本机常量不符 —— 说明 f01 与 f02 的 packager 版本漂了")
    if expect_frozen_root != SKIP_FROZEN_CHECK:
        got_root = (manifest.get("frozen_manifest") or {}).get("root")
        if not got_root:
            bad.append("frozen_manifest_mismatch 通行证没记冻结清单根 —— "
                       "无法确认这个 bundle 用的是哪一版模板（拒绝注入）")
        elif got_root != expect_frozen_root:
            bad.append(f"frozen_manifest_mismatch 冻结清单根 {got_root[:16]}… ≠ 期望 "
                       f"{expect_frozen_root[:16]}… —— 这个 bundle 是用**另一版**模板构建的，"
                       f"混进本批会让任务集版本对不上（拒绝注入）")
    return bad


# ============================================================== 臂注册表（卡 4.1）
#: 臂注册表的落点。**执行面也读它** —— 所以解析器住在本模块（零 `reference/` 依赖），
#: 而不是 `schema.py`（那里 `from reference import artifact_schema`，f02 上 import 即泄漏）。
ARMS_YAML = Path(__file__).resolve().parent / "arms.yaml"

#: 措辞表的列名全集。`genetask/phrasebook.yaml` 每条恰好给这两列
#: （`render.load_phrasebook` 在那一侧把它钉死），`render.FIXED_PHRASES` 同。
#: 臂可以有第三个名字，但它取措辞时必须落到这两列之一。
PHRASEBOOK_COLUMNS: tuple[str, ...] = ("strict", "open")

ARM_KINDS: tuple[str, ...] = ("baseline", "protocol", "instruction_variant")
EQUIVALENCE_MODES: tuple[str, ...] = ("e_rules", "instruction_variant_exception")
_ARM_KEYS = ("id", "kind", "default", "phrasebook_column", "fallback_column",
             "variant_text_file", "equivalence", "description", "artifacts")
_ARM_REQUIRED = ("id", "kind", "phrasebook_column", "equivalence", "description")
_ARTIFACT_KEYS = ("manifest", "mount", "per_task_rules")
_ARM_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")
#: mount 会被拼成 `work/<mount>/…` 并进 compose 的挂载 —— 只许单段、无 `.`、无 `/`。
_MOUNT_RE = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")


@dataclass(frozen=True)
class ArmArtifacts:
    manifest: str
    mount: str
    per_task_rules: bool = False


@dataclass(frozen=True)
class Arm:
    id: str
    kind: str
    default: bool
    phrasebook_column: str
    fallback_column: str | None
    variant_text_file: str | None
    equivalence: str
    description: str
    artifacts: tuple[ArmArtifacts, ...] = ()

    @property
    def is_baseline(self) -> bool:
        return self.kind == "baseline"

    @property
    def waives_e_rules(self) -> bool:
        return self.equivalence == "instruction_variant_exception"

    def column(self, columns: tuple[str, ...] = PHRASEBOOK_COLUMNS) -> str:
        """本臂实际取措辞的列。列不存在时按 `fallback_column` 回退（只有变体臂可以）。"""
        if self.phrasebook_column in columns:
            return self.phrasebook_column
        if self.kind != "instruction_variant":
            raise PackError(f"臂 {self.id!r}（kind={self.kind}）的措辞列 "
                            f"{self.phrasebook_column!r} 不在 {list(columns)} 里，"
                            f"而只有 instruction_variant 臂允许回退 —— "
                            f"baseline/protocol 臂回退等于悄悄换了题面")
        return self.fallback_column or "open"


def _arm_err(msg: str) -> PackError:
    return PackError(f"{ARMS_YAML}: {msg}")


def load_arms(path=None) -> tuple[Arm, ...]:
    """读臂注册表。**缺文件即错**，不是「那就当只有两臂」——

    静默默认值正是这张卡要消灭的东西：臂集合是实验设计的一部分，
    读不到它就没有任何人知道这次跑的是几臂。
    """
    import yaml                       # 局部 import：与 inject.py 同一个理由（f02 的软依赖）

    p = Path(path or ARMS_YAML)
    if not p.is_file():
        raise PackError(f"臂注册表不存在：{p} —— 没有它就没有臂集合的定义（卡 4.1）")
    doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or set(doc) != {"schema_version", "arms"}:
        raise _arm_err("顶层必须是 {schema_version, arms} 两个键")
    raw = doc.get("arms")
    if not isinstance(raw, list) or not raw:
        raise _arm_err("arms 必须是非空列表")

    out: list[Arm] = []
    seen: set[str] = set()
    for i, e in enumerate(raw):
        if not isinstance(e, dict):
            raise _arm_err(f"arms[{i}] 不是映射")
        extra = sorted(set(e) - set(_ARM_KEYS))
        miss = sorted(k for k in _ARM_REQUIRED if k not in e)
        if extra or miss:
            raise _arm_err(f"arms[{i}] 键集不对：多 {extra}，缺 {miss}（全集 {list(_ARM_KEYS)}）")
        aid = e["id"]
        if not isinstance(aid, str) or not _ARM_ID_RE.match(aid):
            raise _arm_err(f"arms[{i}] 的 id {aid!r} 不合法（要匹配 {_ARM_ID_RE.pattern}）—— "
                           f"它会进 run_id 与文件名")
        if aid in seen:
            raise _arm_err(f"臂名重复：{aid!r}")
        seen.add(aid)
        if e["kind"] not in ARM_KINDS:
            raise _arm_err(f"{aid}: kind={e['kind']!r} 不在 {list(ARM_KINDS)}")
        if e["equivalence"] not in EQUIVALENCE_MODES:
            raise _arm_err(f"{aid}: equivalence={e['equivalence']!r} 不在 {list(EQUIVALENCE_MODES)}")
        want_eq = "instruction_variant_exception" if e["kind"] == "instruction_variant" else "e_rules"
        if e["equivalence"] != want_eq:
            raise _arm_err(f"{aid}: kind={e['kind']} 必须配 equivalence={want_eq}（给的是 "
                           f"{e['equivalence']}）—— 两个字段说的是同一件事，不许各说各的")
        if not isinstance(e["description"], str) or not e["description"].strip():
            raise _arm_err(f"{aid}: description 不能为空 —— 臂是实验设计，没人读得懂的臂等于没有")
        col = e["phrasebook_column"]
        if not isinstance(col, str) or not col:
            raise _arm_err(f"{aid}: phrasebook_column 必须是非空字符串")
        fb = e.get("fallback_column")
        if fb is not None:
            if e["kind"] != "instruction_variant":
                raise _arm_err(f"{aid}: 只有 instruction_variant 臂可以声明 fallback_column —— "
                               f"baseline/protocol 臂回退措辞列等于悄悄换了题面")
            if fb not in PHRASEBOOK_COLUMNS:
                raise _arm_err(f"{aid}: fallback_column={fb!r} 不在 {list(PHRASEBOOK_COLUMNS)}")
        if col not in PHRASEBOOK_COLUMNS and e["kind"] != "instruction_variant":
            raise _arm_err(f"{aid}: phrasebook_column={col!r} 不在 {list(PHRASEBOOK_COLUMNS)}，"
                           f"而 kind={e['kind']} 不许回退")
        vtf = e.get("variant_text_file")
        if vtf is not None:
            if e["kind"] != "instruction_variant":
                raise _arm_err(f"{aid}: 只有 instruction_variant 臂可以有 variant_text_file")
            if not isinstance(vtf, str) or vtf.startswith("/") or ".." in Path(vtf).parts:
                raise _arm_err(f"{aid}: variant_text_file={vtf!r} 必须是本目录下的相对路径")
        arts_raw = e.get("artifacts") or []
        if not isinstance(arts_raw, list):
            raise _arm_err(f"{aid}: artifacts 必须是列表")
        if e["kind"] == "baseline" and arts_raw:
            raise _arm_err(f"{aid}: baseline 臂不许投放工件 —— 「裸臂独有文件集为空」"
                           f"是 §6.2 等号判据的另一半")
        arts: list[ArmArtifacts] = []
        mounts: set[str] = set()
        for j, a in enumerate(arts_raw):
            if not isinstance(a, dict) or set(a) - set(_ARTIFACT_KEYS) or "manifest" not in a or "mount" not in a:
                raise _arm_err(f"{aid}: artifacts[{j}] 必须是 {{manifest, mount[, per_task_rules]}}")
            man, mnt = a["manifest"], a["mount"]
            if not isinstance(man, str) or not man.endswith("MANIFEST.json") or man.startswith("/") \
                    or ".." in Path(man).parts:
                raise _arm_err(f"{aid}: artifacts[{j}].manifest={man!r} 必须是相对仓库根、"
                               f"以 MANIFEST.json 结尾的路径（封闭集合，见 §6.2）")
            if not isinstance(mnt, str) or not _MOUNT_RE.match(mnt):
                raise _arm_err(f"{aid}: artifacts[{j}].mount={mnt!r} 必须是单段目录名 "
                               f"（要匹配 {_MOUNT_RE.pattern}）—— 它会被拼进容器路径")
            if mnt in mounts:
                raise _arm_err(f"{aid}: mount {mnt!r} 在同一臂里出现两次 —— 后一份会覆盖前一份")
            mounts.add(mnt)
            arts.append(ArmArtifacts(manifest=man, mount=mnt,
                                     per_task_rules=bool(a.get("per_task_rules", False))))
        out.append(Arm(id=aid, kind=e["kind"], default=bool(e.get("default", False)),
                       phrasebook_column=col, fallback_column=fb, variant_text_file=vtf,
                       equivalence=e["equivalence"], description=e["description"].strip(),
                       artifacts=tuple(arts)))

    base = [a for a in out if a.is_baseline]
    if len(base) != 1:
        raise _arm_err(f"必须**恰好**一个 kind=baseline 的臂（现在 {len(base)} 个："
                       f"{[a.id for a in base]}）—— 等价规则要有唯一参照")
    if not base[0].default:
        raise _arm_err(f"baseline 臂 {base[0].id!r} 必须 default: true —— "
                       f"参照不在默认集合里，默认出集就没有可比对象")
    if not [a for a in out if a.default]:
        raise _arm_err("默认臂集合为空 —— 出集会得到一份没有题面的 bundle")
    if not [a for a in out if a.default and not a.is_baseline]:
        raise _arm_err(f"默认臂集合 {[a.id for a in out if a.default]} 里只有裸臂 —— "
                       f"没有干预臂的对照实验不是对照实验。删掉 strict 这类臂**必须在这里红**，"
                       f"而不是安静地出一份单臂的集：那时候分数照出、报表照排，"
                       f"只是「协议有没有用」这个问题再也没有被问过")
    return tuple(out)


ARM_REGISTRY: tuple[Arm, ...] = load_arms()
ARM_BY_ID: dict[str, Arm] = {a.id: a for a in ARM_REGISTRY}
#: **全部**登记的臂（P1 闸认它）。
ALL_ARMS: tuple[str, ...] = tuple(a.id for a in ARM_REGISTRY)
#: **默认出集的臂**，注册表顺序。`schema.ARMS` 就是它 —— task.yaml 的 instruction 段按此排序。
ARMS: tuple[str, ...] = tuple(a.id for a in ARM_REGISTRY if a.default)
#: 参照臂（kind=baseline）的 id。
BASELINE_ARM: str = next(a.id for a in ARM_REGISTRY if a.is_baseline)
#: 任何臂用到的 `work/` 下子目录全集 —— 通用复制必须**整体避开**它们，
#: 否则 bundle 里带着的工件会被放进每一个臂（那正好破了 §6.2 的等号判据）。
ARTIFACT_MOUNTS: tuple[str, ...] = tuple(sorted({s.mount for a in ARM_REGISTRY for s in a.artifacts}))


def arm_artifact_files(arm: str, repo_root=None) -> dict[str, str]:
    """该臂独有工件的**展开集**：`work/` 下相对路径 → sha256（清单里的封闭集合）。

    清单缺失即红（不是「那就当没有工件」）：没有清单就没有这个臂的封闭定义（§6.2）。
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
    out: dict[str, str] = {}
    for spec in ARM_BY_ID[arm].artifacts:
        mp = root / spec.manifest
        if not mp.is_file():
            raise PackError(f"臂 {arm!r} 的工件清单不存在：{mp} —— "
                            f"没有清单就没有这个臂的封闭定义（§6.2）")
        m = json.loads(mp.read_text(encoding="utf-8"))
        for k, v in dict(m["artifacts"]).items():
            out[f"{spec.mount}/{k}"] = v
    return out


def arm_manifest_status(arm: str, repo_root=None) -> list[tuple[str, str, int]]:
    """该臂每份清单的 `(manifest 相对路径, status, 条目数)` —— P7 的门读它。"""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[1]
    out = []
    for spec in ARM_BY_ID[arm].artifacts:
        m = json.loads((root / spec.manifest).read_text(encoding="utf-8"))
        out.append((spec.manifest, str(m.get("status", "unknown")), len(m.get("artifacts") or {})))
    return out
