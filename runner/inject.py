"""卡 4.3：双臂注入器。把一臂的题面与协议工件送进该臂**独占**的 run dir。

**跑在 f02（执行面）**，因此本模块只许 import `genetask.pin`、`genetask.packager` 的
无机密部分与标准库 —— **不得** import `genetask.schema`（它顶层拉 `reference/`，
会把答案面拖上执行面，卡 4.3 §1.1）。这条有一个 AST 断言守着（`ops/test_inject.py`）。

设计要点，每条对应一个失败模式：
* 顺序 P0–P9 固定（§5）。任一步返回非空 ⇒ `PackError`，**不吞、不降级、不 warning 继续**。
* 两臂差异是**等号**不是包含号（§6.2）：少给 strict 臂一个协议工件也满足 ⊆，
  那不是隔离失败而是**干预失败** —— 协议臂静默退化成半个裸臂，实验照跑、结论变成「协议没用」。
* run dir 按 `run_id`（含 config_id 与 seq）分层，不按 `<task_id>/<arm>` —— 否则重跑会静默覆盖遥测（F9）。
* 冻结核验（裁定 2026-09-04）：bundle 通行证记着构建所依据的冻结清单根，
  与本批期望值不符即拒绝注入。**测试套里的防漂断言只在 f01 跑**，bundle 搬到 f02 之后
  没人再问它是哪一版模板 —— 运行时缺这道门，漂了的模板照样进容器。
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from genetask import pin
from genetask.bundle import (ALL_ARMS, ARM_BY_ID, ARMS, ARTIFACT_MOUNTS,  # noqa: F401
                             IMAGE_DIGEST_PLACEHOLDER, PackError, SKIP_FROZEN_CHECK,
                             _check_tests_source, check_manifest, lint_dockerfile)
from runner import provider_adapter as PA
from runner.c41 import runner_core as RC
from runner import registry as REG
from runner.c41 import subnets as SUB
from runner.f02 import answer_plane_guard as APG

#: 协议工件清单（strict 臂独有）。**封闭**：每条带 sha256。
#: 「协议工件 = 某个目录里当时有的东西」是不可接受的定义 —— 那个目录会长东西（§6.2）。
PROTOCOL_MANIFEST = Path(__file__).resolve().parents[1] / "ops" / "protocol" / "geneprotocol_v1" / "MANIFEST.json"

#: 协议工件在 work/ 下的子目录 —— 容器里就是 /task/protocol/。
PROTOCOL_REL = "protocol"

#: 边车代码在 run dir 里的位置。
#:
#: **为什么它必须进 run dir**（T15 实测发现，2026-09-04）：原先 compose 挂的是
#: `/data/genebench_runner/egress_proxy.py` —— 一个 run dir **之外**的固定路径，
#: 不在任何同步或校验链路里。它与代码库漂开时，**表现是「身份注入静默失效」**：
#: 容器照跑、日志照写，只是记的是伪造值。T15 第一次红就是被这个绊的
#: （新代码进了 exec/，边车跑的还是旧版）。
#: 进 run dir 之后它走 P8 的文件集封闭，漂了当场红。
SIDECAR_REL = "egress_proxy.py"
#: 边车解析请求头用的 h11 —— **网关那一份**，复制进 run dir 挂给边车。
#: 不是"版本相同"，是**同一份字节**：sha 逐文件记进 `inject.json`。
H11_REL = "h11"

#: run dir 里允许出现的顶层项。多一个即红 —— run dir 有自己的形状，
#: **不能**拿 `check_export` 去扫它（那会把 INSTRUCTION.md / compose.yml / provider/ 全判成 G4）。
RUN_DIR_TOPLEVEL = ("bundle", "work", "log", "compose.yml", "inject.json",
                    SIDECAR_REL, H11_REL)

#: 磁盘余量阈值：满盘会让复制**截断**而不报错（P0 的理由）。
MIN_FREE_BYTES = 2 * 1024 ** 3


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha_file(p: Path) -> str:
    return _sha(p.read_bytes())


def runner_version() -> str:
    """**runner 自己**的版本（内容根 hash）。

    为什么必须记（裁定 2026-09-04）：runner 既不在容器里、也不在 run dir 里，
    但它决定**注入顺序与 env 契约** —— 换一版 runner，同一个 bundle 会注出不同的 run dir。
    不记版本，日后无法复现「当时是怎么注的」。

    用内容根 hash 而不是 git sha：执行面的 `exec/` 是打包同步过去的，**不是 git 仓库**
    （`ops/run_f02_container_tests.sh` 只搬执行面允许的那几个文件）。
    算法与 `pin.provider_root_sha256` 同一套 —— 相对路径 + 内容，目录名/mtime/owner 不进。
    """
    root = Path(__file__).resolve().parent
    parts: list[bytes] = []
    for f in sorted((p for p in root.rglob("*.py") if p.is_file()),
                    key=lambda p: str(p.relative_to(root)).encode()):
        rel = str(f.relative_to(root)).encode()
        parts.append(rel + b"\0" + hashlib.sha256(f.read_bytes()).hexdigest().encode() + b"\n")
    return hashlib.sha256(b"".join(parts)).hexdigest()


#: 机器标识（用户裁定 ⑮，2026-09-10）：`run_id` 末尾带上**这一次是哪台机器跑出来的**。
#:
#: 为什么要它：结果包要能在两台机器之间导出 / 合并（`ops/genebench_cli.py`）。
#: 不带机器标识的话，两台机器按同一份清单跑出来的 `run_id` **逐字相同** ——
#: 合并时是「同主键、内容不同」，结果库当场拒（`ops/results_db.py::ingest` 只追加不覆盖），
#: 两份都是真的读数却只能留一份。**这是一条身份，不是一条元信息。**
#:
#: 算法（都在 :func:`machine_fingerprint` / :func:`machine_id` 里，手册 §8.1 抄的是这段）::
#:
#:     fingerprint = sha256(b"genebench-machine-v1\0" + 稳定源).hexdigest()[:8]
#:     machine_id  = f"{主机名 slug（≤16 字符）}-{fingerprint}"
#:
#: 稳定源按顺序取**第一个拿得到的**：
#:
#: 1. 环境变量 ``GENEBENCH_MACHINE_ID`` —— 给了就**整个 machine_id 由它决定**（不是只换指纹）。
#:    跑批时 f01 把自己的值 export 给 f02（`ops/run_joblist.py::f02_run_cmd`），
#:    于是 `job_id`（f01 生成）与 `run_id`（f02 生成）**仍然逐字相同** ——
#:    两处不同源就要靠一张会漂的映射表，那是上一轮踩过的坑。
#: 2. ``/etc/machine-id`` 或 ``/var/lib/dbus/machine-id``（装机时生成，重启 / 改 IP / 换网卡都不变）。
#:    **哈希之后才用**：systemd 明文说这个值不该原样外露。
#: 3. macOS 的 ``IOPlatformUUID``。
#: 4. 都没有 → 退回主机名本身，`fingerprint_source` 如实记 ``hostname-only``：
#:    **这台机器的指纹不稳**（两台同名机会撞），要靠 ``GENEBENCH_MACHINE_ID`` 钉死。
#:
#: **不进算法的东西**：IP、MAC、容器 id、时间、cgroup、进程环境 —— 它们会变，
#: 而这条标识一旦变了，同一台机器导出的两个结果包在合并时就成了两台机器。
#: 主机名只做**可读前缀**，改主机名会换 `machine_id`（指纹那一半不变）；
#: 在意这件事的部署请显式给 ``GENEBENCH_MACHINE_ID``。
MACHINE_ID_ENV = "GENEBENCH_MACHINE_ID"
#: `run_id` 里机器标识的分隔符。**不能用 `.`** —— `run_id` 的前四段是用 `.` 切的
#: （`ops/api_usage.py::parse_run_id`），再加一段会让那个解析器整条认不出来。
MACHINE_SEP = "@"
MACHINE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
_MACHINE_ID_FILES = ("/etc/machine-id", "/var/lib/dbus/machine-id")
_MACHINE_FP_CACHE: dict = {}


def _slug(s: str, n: int = 16) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", str(s or "").strip().lower()).strip("-")
    return (out[:n].rstrip("-") or "host")


def _machine_source() -> tuple[str, str]:
    """(稳定源的原文, 它是从哪来的)。原文**只进哈希**，不进任何产物。"""
    for p in _MACHINE_ID_FILES:
        try:
            v = Path(p).read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if v:
            return v, p
    if sys.platform == "darwin":                            # pragma: no cover - 本项目不在 mac 上跑批
        try:
            out = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                 capture_output=True, text=True, timeout=10).stdout
            m = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out or "")
            if m:
                return m.group(1), "ioreg:IOPlatformUUID"
        except (OSError, subprocess.SubprocessError):
            pass
    return platform.node() or "unknown", "hostname-only"


def machine_fingerprint() -> tuple[str, str]:
    """`(8 位指纹, 来源)`。进程内缓存 —— 读的是不会变的东西，读一次就够。"""
    if "fp" not in _MACHINE_FP_CACHE:
        raw, src = _machine_source()
        fp = hashlib.sha256(b"genebench-machine-v1\0" + raw.encode("utf-8")).hexdigest()[:8]
        _MACHINE_FP_CACHE["fp"] = (fp, src)
    return _MACHINE_FP_CACHE["fp"]


def machine_id() -> str:
    """这台机器的标识。`GENEBENCH_MACHINE_ID` 给了就用它（**不缓存**：跑批时逐 job 可能改）。"""
    env = (os.environ.get(MACHINE_ID_ENV) or "").strip()
    if env:
        if not MACHINE_ID_RE.match(env):
            raise PackError(f"{MACHINE_ID_ENV}={env!r} 不是合法的机器标识："
                            f"要匹配 {MACHINE_ID_RE.pattern}（小写字母数字与减号；"
                            f"**不许有 `.` 或 `{MACHINE_SEP}`**，它们是 run_id 的分隔符）")
        return env
    fp, _ = machine_fingerprint()
    return f"{_slug(platform.node(), 16)}-{fp}"


def machine_info() -> dict:
    """进 `inject.json` / 结果包 MANIFEST 的那一份。**不含稳定源的原文。**"""
    fp, src = machine_fingerprint()
    env = (os.environ.get(MACHINE_ID_ENV) or "").strip()
    return {"machine_id": machine_id(), "hostname": platform.node(),
            "fingerprint": fp,
            "fingerprint_source": f"env:{MACHINE_ID_ENV}" if env else src,
            "algo": "sha256(b'genebench-machine-v1\\0' + 稳定源).hexdigest()[:8]"}


def run_id(task_id: str, arm: str, config_id: str, seq: int, machine: str | None = None) -> str:
    """``<task>.<arm>.<config>.rNN@<machine_id>``（用户裁定 ⑮）。

    **既有 run_id 不追溯** —— 库里 2026-09-10 之前的那 126 条没有 `@` 段，
    `ops/results_db.py::machine_of` 对它们返回 `None`，报告里按「机器未知」如实写。
    """
    m = machine or machine_id()
    return f"{task_id}.{arm}.{config_id}.r{int(seq):02d}{MACHINE_SEP}{m}"


def split_run_id(rid: str) -> tuple[str, str | None]:
    """``run_id`` → `(不带机器段的部分, machine_id 或 None)`。认不出机器段就如实给 None。"""
    base, sep, m = str(rid).partition(MACHINE_SEP)
    if not sep or not m:
        return str(rid), None
    return base, m


def compose_project(rid: str) -> str:
    """compose 项目名只接受 `[a-z0-9][a-z0-9_-]*`；带 `.` 或 `@` 会被 compose 直接拒。"""
    return "gb-" + re.sub(r"[^a-z0-9_-]+", "-", str(rid).lower())


def protocol_artifacts() -> dict[str, str]:
    """strict 臂独有的协议工件 → sha256。清单缺失即红（不是「那就当没有协议工件」）。"""
    if not PROTOCOL_MANIFEST.is_file():
        raise PackError(f"协议工件清单不存在：{PROTOCOL_MANIFEST} —— "
                        f"没有清单就没有 strict 臂的封闭定义（§6.2）")
    m = json.loads(PROTOCOL_MANIFEST.read_text(encoding="utf-8"))
    return dict(m["artifacts"])


def protocol_status() -> str:
    m = json.loads(PROTOCOL_MANIFEST.read_text(encoding="utf-8"))
    return str(m.get("status", "unknown"))


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _manifest(rel: str) -> dict:
    p = _REPO_ROOT / rel
    if not p.is_file():
        raise PackError(f"工件清单不存在：{p} —— 没有清单就没有这个臂的封闭定义（§6.2）")
    return json.loads(p.read_text(encoding="utf-8"))


def manifest_files(rel: str) -> dict[str, str]:
    """一份清单的封闭集合（相对清单目录的路径 → sha256）。

    **geneprotocol_v1 走 `protocol_artifacts()`**：那是既有的公开入口，
    「清单为空时 strict 臂必红」这条永久断言 monkeypatch 的就是它 ——
    绕开它去直接读文件，会让那个负例静默失效（恒绿的门与恒红的门一样坏）。
    """
    if (_REPO_ROOT / rel) == PROTOCOL_MANIFEST:
        return protocol_artifacts()
    return dict(_manifest(rel)["artifacts"])


def manifest_status(rel: str) -> str:
    """一份清单的 status。geneprotocol_v1 同上，走 `protocol_status()`。"""
    if (_REPO_ROOT / rel) == PROTOCOL_MANIFEST:
        return protocol_status()
    return str(_manifest(rel).get("status", "unknown"))


def arm_files(arm: str) -> dict[str, str]:
    """该臂**独有**投放的工件展开集：run dir 的 `work/` 下相对路径 → sha256。

    裸臂（`kind=baseline`）恒为空 —— 那是 §6.2 等号判据的另一半。
    """
    out: dict[str, str] = {}
    for spec in ARM_BY_ID[arm].artifacts:
        out.update({f"{spec.mount}/{k}": v for k, v in manifest_files(spec.manifest).items()})
    return out


def other_arm_files(arm: str) -> dict[str, str]:
    """**别的臂**的工件展开集，**减掉本臂自己的**。P8 用它判「这个臂拿到了不该有的东西」。

    减法是必须的：两个 protocol 臂可以共用同一个 `mount`（doc 臂与 strict 臂都落在
    `work/protocol/`，README.md / contract.md 还逐字节相同）。不减的话 strict 臂注入完
    会被 doc 臂的清单判成「出现了不该有的协议工件」—— 一个只在加了第二个 protocol 臂
    之后才冒出来的红，而现场会以为是新臂的问题。
    """
    mine = set(arm_files(arm))
    out: dict[str, str] = {}
    for other in ALL_ARMS:
        if other != arm:
            out.update({k: v for k, v in arm_files(other).items() if k not in mine})
    return out


# --------------------------------------------------------------- P0 前置自检

def _load_guard():
    """把 `ops/guard_modes.py` 从**这棵树自己**动态加载出来（P0 的启动守门）。

    单独一个函数只为一件事：让 `ops/test_F10.py` 能换掉它，**真造一个「守门没在查这棵树」
    的现场**，验 P0 当场红 —— 判别力不该只存在于读代码的人脑子里（红队 2026-09-07 finding 2）。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_guard", Path(__file__).resolve().parents[1] / "ops" / "guard_modes.py")
    if not (spec and spec.loader):
        return None
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g


def preflight(run_root: Path, *, require_docker: bool = True,
              check_modes: bool = True) -> list[str]:
    """P0。无 sudo 假设下这些都可能不成立，且失败形态都很安静。

    `check_modes`：**启动守门**（指令一，2026-09-04）。推送时刻绿不代表使用时刻绿 ——
    中间任何人 `chmod` 一下都不会有人知道，而注入器正要把东西复制进容器可见的目录。
    """
    bad: list[str] = []
    if check_modes:
        g = _load_guard()
        if g is not None:
            # **守门必须真的在查这棵树**（N-857，2026-09-14）。
            # `ops/guard_modes.py` 的 `genebench_config` import 改成可选之后，执行面上
            # `EXTERNAL_ROOTS` / `ANSWER_PLANE_ROOTS` 落空是**预期**的（那些路径在执行面上
            # 本来就不存在）—— 但「主判据 = 这棵树自己」不许跟着落空。
            # 静默跳过与恒绿同族，所以在这里**当场断言一次**：守门的审计根里必须有
            # 注入器自己这棵树，没有就红，不许把「什么都没查」读成绿。
            _self = Path(__file__).resolve().parents[1]
            if not any(Path(r).resolve() == _self for r in g.roots()):
                bad.append(f"P0 红线 5 守门没把注入器自己这棵树（{_self}）列进审计根 —— "
                           f"现有 {[str(r) for r in g.roots()][:4]}；"
                           f"守门什么都没查，不读成绿")
            for line in g.check()[:5]:
                bad.append(f"P0 {line}")
    run_root = Path(run_root)
    try:
        run_root.mkdir(parents=True, exist_ok=True)
        probe = run_root / ".inject_write_probe"
        probe.write_bytes(b"x")
        probe.unlink()
    except OSError as e:
        bad.append(f"P0 run_root 不可写：{run_root}（{e}）")
        return bad                      # 后面的检查都建立在可写之上
    st = shutil.disk_usage(run_root)
    if st.free < MIN_FREE_BYTES:
        bad.append(f"P0 磁盘余量 {st.free / 1024**3:.1f}G < {MIN_FREE_BYTES / 1024**3:.0f}G —— "
                   f"满盘会让复制**截断**而不报错，比复制失败更难查")
    if require_docker:
        try:
            r = subprocess.run(["docker", "compose", "version"],
                               capture_output=True, text=True, timeout=20)
            if r.returncode != 0:
                bad.append(f"P0 `docker compose version` 返回 {r.returncode}："
                           f"{(r.stderr or r.stdout).strip()[:200]}")
        except FileNotFoundError:
            bad.append("P0 找不到 docker —— 两台机器目前都没有容器运行时"
                       "（见 tickets：docker 未装、f02 敲 lxc 会触发 snap 安装）")
        except subprocess.TimeoutExpired:
            bad.append("P0 `docker compose version` 超时 —— daemon 可能没起")
    return bad


# --------------------------------------------------------------- P8 run dir 自检

#: 执行面上 h11 的落点：exec 树里的 `vendor/h11/`（由 `ops/run_f02_container_tests.sh`
#: 从**网关环境那一份**复制过去）。注入器在 f02 跑，f02 的 python3 **没有 h11、也没有 pip**
#: （2026-09-05 实测）—— 在这里 `import h11` 会让 P7d 当场炸，而且是在 f02 上炸。
#: 所以先找随树船运的那份，再退到 import（f01 本机跑测试时走这条）。
VENDOR_H11 = Path(RC.__file__).resolve().parents[2] / "vendor" / "h11"


def _model_upstream(config_id: str) -> str:
    """registry 里该配置的上游主机名（如 api.deepseek.com）。找不到就抛 —— 不许静默无上游。"""
    return REG.by_id(config_id).host


def h11_source_dir() -> Path:
    """h11 源码目录：优先 exec 树里的 `vendor/h11`；没有再取运行环境里的（f01）。"""
    if (VENDOR_H11 / "__init__.py").is_file():
        return VENDOR_H11
    import h11
    return Path(h11.__file__).resolve().parent


def place_h11(run_dir: Path) -> dict[str, str]:
    """把 h11 复制进 run dir（相对路径 → sha256）。

    只复制 `.py` 与 `py.typed`：`__pycache__` 是 cpython-310 的，
    而边车容器是 3.11-alpine，带过去只会被忽略，还平白进了封闭文件集。

    **拒绝任何编译产物**：alpine 是 musl，glibc 上编译的 `.so` 在那里根本加载不了，
    而表现是"边车起不来"而不是"h11 装错了"。h11 现在是纯 Python，
    这条是给它哪天不纯了准备的。
    """
    src = h11_source_dir()
    compiled = sorted(p.name for p in src.rglob("*") if p.suffix in (".so", ".pyd", ".dylib"))
    if compiled:
        raise RuntimeError(f"h11 带了编译产物 {compiled} —— 不能挂进 musl 容器；"
                           f"「边车与网关同一个解析器」这条要另想办法")
    dst = run_dir / H11_REL
    dst.mkdir(mode=0o700, parents=True, exist_ok=True)
    out: dict[str, str] = {}
    for f in sorted(src.iterdir()):
        if f.is_file() and (f.suffix == ".py" or f.name == "py.typed"):
            shutil.copyfile(f, dst / f.name)
            out[f"{H11_REL}/{f.name}"] = _sha_file(dst / f.name)
    return out


def check_run_dir(run_dir: Path, *, arm: str, protocol: dict[str, str],
                  expect_work: dict[str, str] | None = None,
                  expect_top: dict[str, str] | None = None,
                  forbidden: dict[str, str] | None = None) -> list[str]:
    """run dir 有自己的形状（§P8）：顶层项封闭、**work/ 文件集封闭**、协议工件按臂精确、无空文件。

    `expect_work`：本次注入**应该**放进 work/ 的东西（相对路径 → sha256）。
    原先没有这个参数 —— 于是 P8 只查顶层项与协议工件，往 `work/` 里塞任何文件都看不见，
    整段 P8 删掉全套测试仍绿（红队 2026-09-04，high）。

    `protocol`：**本臂**应有的工件（`arm_files(arm)`；裸臂是空的）。
    `forbidden`：**别的臂**的工件（`other_arm_files(arm)`）—— 出现即红。
    卡 4.1 之前这两件事靠 `arm == "strict"` 分支判断，臂名写死在注入器里。
    """
    bad: list[str] = []
    run_dir = Path(run_dir)
    for p in sorted(run_dir.iterdir()):
        if p.name not in RUN_DIR_TOPLEVEL:
            bad.append(f"P8 run dir 顶层多出 {p.name} —— 允许集 {RUN_DIR_TOPLEVEL}")
    work = run_dir / "work"
    if not (work / "INSTRUCTION.md").is_file():
        bad.append("P8 work/INSTRUCTION.md 不存在")
    have = {str(p.relative_to(work)) for p in work.rglob("*") if p.is_file()}
    want_proto = set(protocol)
    for rel in sorted(want_proto - have):
        bad.append(f"P8 {arm} 臂缺协议工件 {rel} —— 少一个就是**干预失败**，"
                   f"协议臂静默退化成半个裸臂（F8）")
    for rel in sorted(want_proto & have):
        if _sha_file(work / rel) != protocol[rel]:
            bad.append(f"P8 协议工件 {rel} 的 sha256 与清单不符")
    for rel in sorted(set(forbidden or {}) & have):
        bad.append(f"P8 {arm} 臂出现协议工件 {rel} —— 裸臂不该有它")
    # **run dir 顶层的可执行物也要封闭**（裁定 2026-09-04 的封闭推广）：
    # compose.yml 与 egress_proxy.py 都参与这次运行，原先只有 work/ 进封闭 ——
    # 而边车漂开那次的教训正是「参与运行的可执行物不在封闭里就会静默漂开」。
    if expect_top is not None:
        for rel, sha in sorted(expect_top.items()):
            p = run_dir / rel
            if not p.is_file():
                bad.append(f"P8 run dir 顶层缺 {rel}")
            elif sha and _sha_file(p) != sha:
                bad.append(f"P8 {rel} 的 sha256 与注入时不符 —— 它参与这次运行，不许漂")
    if expect_work is not None:
        want = dict(expect_work)
        want.update(protocol)
        for rel in sorted(set(want) - have):
            bad.append(f"P8 work/ 少了 {rel}")
        for rel in sorted(have - set(want)):
            bad.append(f"P8 work/ 多出 {rel} —— 本次注入没放过它，来路不明")
        for rel in sorted(set(want) & have):
            if want[rel] and _sha_file(work / rel) != want[rel]:
                bad.append(f"P8 work/{rel} 的 sha256 与注入时不符")
    for p in sorted(work.rglob("*")):
        if p.is_file() and p.stat().st_size == 0:
            bad.append(f"P8 work/{p.relative_to(work)} 是空文件 —— 多半是复制被截断")
    return bad


def arm_diff(strict_work: Path, open_work: Path) -> dict[str, list[str]]:
    # 形参名沿用 strict/open：第一个是**被查的臂**，第二个是**参照臂**（`BASELINE_ARM`）。
    """§6.2 的**等号**判据材料：两侧文件集之差与同名文件的 sha 差。"""
    def files(d: Path) -> dict[str, str]:
        return {str(p.relative_to(d)): _sha_file(p) for p in Path(d).rglob("*") if p.is_file()}
    s, o = files(strict_work), files(open_work)
    return {
        "strict_only": sorted(set(s) - set(o)),
        "open_only": sorted(set(o) - set(s)),
        "sha_differs": sorted(k for k in set(s) & set(o) if s[k] != o[k]),
    }


def check_arm_diff(strict_work: Path, open_work: Path, *, protocol: dict[str, str],
                   arm: str = "strict", base: str = "open") -> list[str]:
    """臂差异必须**精确等于**该臂的工件展开集（§6.2）。⊆ 抓不到「少给它一个」。

    `protocol` = 被查臂应有的工件（`arm_files(arm)` + 逐题规则）；
    `base` 是参照臂（`kind=baseline`），它**独有文件集必须为空** —— 那是等号的另一半。
    `arm`/`base` 只影响报错里的臂名，默认值就是内置两臂，消息逐字节不变。
    """
    d = arm_diff(strict_work, open_work)
    bad: list[str] = []
    if set(d["strict_only"]) != set(protocol):
        bad.append(f"E-ARM {arm} 臂独有文件集 ≠ 协议工件集："
                   f"缺 {sorted(set(protocol) - set(d['strict_only']))}，"
                   f"多 {sorted(set(d['strict_only']) - set(protocol))} —— "
                   f"这是**等号**不是包含号：少给 {arm} 一个协议工件，实验照跑而结论变成「协议没用」")
    if d["open_only"]:
        bad.append(f"E-ARM {base} 臂独有文件 {d['open_only']} —— 裸臂不该多出任何东西")
    if d["sha_differs"] != ["INSTRUCTION.md"]:
        bad.append(f"E-ARM 两臂同名文件里 sha 不同的应恰好只有 INSTRUCTION.md，实际 {d['sha_differs']}")
    if base and arm_files(base):
        bad.append(f"E-ARM 参照臂 {base!r} 在注册表里声明了工件 {sorted(arm_files(base))} —— "
                   f"baseline 臂独有文件集必须为空，否则「多出来的是干预」这句话不成立")
    return bad


# --------------------------------------------------------------- 注入主体

def verify_run_dir_unchanged(run_dir) -> list[str]:
    """**起容器之前**再核一次：注入之后有没有人动过 run dir。

    为什么需要（封闭推广时发现）：P8 在**注入结束时**跑，之后到 `docker compose up`
    之间的窗口没有任何门。实测证据：T5/T10 的探针脚本 `work/probe.py` 就是在注入之后
    写进去的，P8 一个字都没说 —— 容器于是跑了一个不在任何清单里的文件。
    """
    run_dir = Path(run_dir)
    inj_path = run_dir / "inject.json"
    if not inj_path.is_file():
        return [f"没有 inject.json：{run_dir} —— 这个 run dir 不是注入器造的"]
    inj = json.loads(inj_path.read_text(encoding="utf-8"))
    want = dict(inj.get("files") or {})
    bad: list[str] = []
    got = {}
    for p in sorted(run_dir.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(run_dir))
        if rel == "inject.json" or rel.startswith("log/"):
            continue                            # 自身与运行期日志不在封闭里
        got[rel] = _sha_file(p)
    for rel in sorted(set(want) - set(got) - {"inject.json"}):
        bad.append(f"注入后被删：{rel}")
    for rel in sorted(set(got) - set(want)):
        bad.append(f"注入后被加：{rel} —— 它不在任何清单里，容器却会看到它")
    for rel in sorted(set(got) & set(want)):
        if got[rel] != want[rel]:
            bad.append(f"注入后被改：{rel}")
    return bad


@dataclass
class Injected:
    run_dir: Path
    run_id: str
    arm: str
    config_id: str
    frozen_manifest: dict = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)


#: ── provider 钉子**按通道取**（用户裁定 2026-09-10，「provider 前置」）────────────────
#: 两条通道各有一份冻结 provider，根不同：
#:   * `private` → `genetask.pin.PROVIDER_SHA256_ROOT`（`$SNAPSHOTS/v1/qlib_provider`）
#:   * `public`  → `f7dda2899071b07a…`（`$SNAPSHOTS/public_v1/qlib_provider`，28,605 文件 / 346 MB）
#:     （2026-09-12 卡 A：宇宙定义面换成 baostock 成分接口重建、csi1000 出包，根从
#:     `561348660a3175b1…` 变成这一个；旧根只出现在 v1.0.16 / p1.0.0 的**只读签字归档**里）
#:
#: 在此之前 `inject()` 无条件用 private 那一个，于是公开通道的真跑在 P2 当场红，
#: 报错原文是「provider sha256 根 561348660a3175b1… ≠ 冻结值 54fdda39… —— provider 变了」
#: （`ops/reports/m6_public/plane_probe.md:61`）。**表现是「provider 变了」，
#: 实际是「问错了通道」** —— 照着报错去查 provider 的人什么也查不到。
#:
#: private 这一份**不在这里再抄一遍**：抄一份冻结常量必然漂，而漂的那天没有任何东西会报错
#: （`genetask/pin.py` 的模块 docstring 里写的就是这条）。只有 public 那个字面量是新的。
PUBLIC_PROVIDER_SHA256_ROOT = "f7dda2899071b07a"
PROVIDER_PIN_CHANNELS: tuple[str, ...] = ("private", "public")


def provider_pin_by_channel() -> dict[str, str]:
    """通道 → 冻结 provider 的 sha256 根。**运行时组装，不是模块级常量。**

    写成常量的那一版是错的：`pin.PROVIDER_SHA256_ROOT` 会在 import 期被拍成快照，
    之后谁改了它（v1.1 重钉、重载、`ops/test_inject.py::_patch_pin` 的 monkeypatch）
    都不再生效 —— **检查照跑，比的却是旧值**。`pin.check_provider_pin` 里那段
    「不用默认参数」的自查写的就是这条，本函数是它在通道这一层的同一条。
    """
    return {"private": pin.PROVIDER_SHA256_ROOT,
            "public": PUBLIC_PROVIDER_SHA256_ROOT}

#: 通道从环境变量取。**这里不 `import genebench_config`** —— 它不在
#: `ops/push_exec_to_f02.sh` 的白名单里，f02 上根本没有这个模块，
#: import 它的后果不是「少个默认值」，是**整棵 runner 在执行面 import 不了**（而 f01 侧一切正常）。
#: 两边的名字与默认值由 `ops/test_provider_pin_channel.py::test_channel_names_do_not_drift`
#: 逐字比对 —— 那条测试只在 f01 跑，那里两个模块都在。
CHANNEL_ENV = "GENEBENCH_CHANNEL"
DEFAULT_CHANNEL = "private"


def provider_pin_expect(channel: str | None = None) -> str:
    """这条通道该拿哪个 provider 钉子。**不认识的通道当场抛**，不回落到 private。

    为什么不回落（这是本函数唯一一条值得写下来的判断）：`GENEBENCH_CHANNEL=pubic`
    这样一个拼错，回落之后会让公开通道的 run 去比 private 的钉子 —— P2 照样红，
    而报错说的是「provider 变了」。人会去查 provider，查不到任何问题，
    因为问题根本不在 provider 上。**静默回落把一次拼写错误伪装成一次数据事故。**
    """
    ch = channel if channel is not None else (os.environ.get(CHANNEL_ENV) or DEFAULT_CHANNEL)
    ch = str(ch).strip()
    table = provider_pin_by_channel()
    if ch not in table:
        raise PackError(
            f"[P2] 不认识的通道 {ch!r}（{CHANNEL_ENV}）—— 认得的是 "
            f"{sorted(table)}。不回落到 {DEFAULT_CHANNEL}："
            f"回落之后 P2 会报「provider 变了」，而真正的原因是这里拼错了通道名")
    return table[ch]


def check_work_provider(work_dir, *, channel: str | None = None) -> list[str]:
    """P7e：**容器真正会挂进 `/task` 的那一份** provider 的根 sha == 本通道的期望值。

    为什么 P2 不够（N-611 的教训，别删这道门）：P2 比的是**调用方传进来的
    `provider_root`**。真跑那条路径上 `ops/run_f02_a1.py` 曾把 `--provider-root`
    静默丢掉、改读模块常量（写死私有 provider 的绝对路径），于是「传进来的」与
    「实际装进 `work/` 的」是同一个错的东西 —— **两头一致，P2 全绿**，
    公开通道的 18 个 run 喂给容器的却是私有 provider 树。
    实测证据：公开 run 的 `work/provider/features/` 下有 336 个 `bj*`（北交所）代码，
    而公开 provider 只有沪深（3575 个，`bj*` 为 0）。

    这道门站在 **`work/` 这一侧** —— 位置就是 compose 把 `<run_dir>/work` 挂成
    `/task` 的那个目录。它查的是**结果**，不是输入：调用方怎么绕过参数都改不了它。

    空列表 = 绿（与 `check_export` / `check_provider_pin` 同风格）。
    """
    work = Path(work_dir)
    d = work / PA.WORK_PROVIDER_REL
    ch = channel if channel is not None else (os.environ.get(CHANNEL_ENV) or DEFAULT_CHANNEL)
    if not d.is_dir():
        return [f"P7e {d} 不存在 —— provider 没进 work/，容器里 /task/{PA.WORK_PROVIDER_REL} "
                f"会是空的，而因子会「算出来了、就是数不对」"]
    want = provider_pin_expect(ch)
    got = PA.provider_root_sha256_of(d)
    if got.startswith(want):
        return []
    # **说清装进去的到底是谁**：报「不一致」的门会让人去查 provider，
    # 而真正的问题往往是「问对了通道、装错了树」。
    other = [k for k, v in provider_pin_by_channel().items() if got.startswith(v)]
    hint = (f"—— 装进去的是 **{other[0]} 通道**的那一份" if other
            else "—— 它不是任何一条已登记通道的冻结 provider")
    return [f"P7e work/provider 的现算根 {got[:16]}… ≠ 通道 {ch!r} 的期望 {want}… {hint}。"
            f"P2 只比调用方传进来的那个路径，拦不住这一类（N-611）："
            f"`--provider-root` 一度在真跑路径上被静默忽略"]


def inject(bundle_dir, arm: str, *, run_root, provider_root, config_id: str,
           manifest: dict, expect_frozen_root: str, command: str,
           seq: int = 1, require_docker: bool = True, check_modes: bool = True,
           place_provider: bool = True, subnets: dict | None = None,
           model_upstream: str | None = None, channel: str | None = None) -> Injected:
    """P0–P9。任一步非空即 `PackError` —— **不吞**。返回注入结果（含 run dir 与冻结引用）。"""
    # **注入器自己写规范路径**，不把调用方传进来的原样写进 compose。
    # 真实部署里 run_root 很容易带符号链接（macOS 的 /tmp → /private/tmp 就是；
    # 生产上 /data 挂载点也常有一层）。不 resolve 的话，L-5a 会拿注入器自己写的
    # 非规范路径判红 —— 门拦住的是自己人，而这个失败在 pytest 的 tmp_path 下看不见
    # （pytest 给的已经是解析过的路径），只在真机上炸。
    bundle_dir, run_root = Path(bundle_dir).resolve(), Path(run_root).resolve()

    def gate(step: str, problems: list[str]) -> None:
        if problems:
            raise PackError(f"[{step}] 注入中止（{len(problems)} 条）：\n  " + "\n  ".join(problems))

    gate("P0", preflight(run_root, require_docker=require_docker, check_modes=check_modes))
    # **全部登记的臂**（含 `default: false` 的）都可以注入 —— 臂集合由 `genetask/arms.yaml`
    # 定义，不是常量。没登记的臂名仍然当场红：拼错会安静地建出一个谁也不认识的 run dir。
    gate("P1", [] if arm in ALL_ARMS else [f"P1 臂名 {arm!r} 不在 {ALL_ARMS} —— "
                                            f"拼错会安静地建出第三个 run dir"])
    # P2 的 `expect` **按通道给**（用户裁定 2026-09-10）：不给的话 `check_provider_pin`
    # 在运行时取 private 的常量，公开通道的每一次真跑都会在这里红成「provider 变了」。
    gate("P2", pin.check_provider_pin(provider_root, expect=provider_pin_expect(channel)))
    gate("P3", check_manifest(bundle_dir, manifest, expect_frozen_root=expect_frozen_root))

    dockerfile = (bundle_dir / "image" / "Dockerfile").read_text(encoding="utf-8")
    gate("P4", lint_dockerfile(dockerfile))
    # 容器实际跑的镜像**从 Dockerfile 的 FROM 取**，不另给参数。
    # 原先 image 是 inject 的默认关键字参数（裸 tag `python:3.11-alpine`），
    # 与 P4/P4b 钉住的 Dockerfile digest 毫无关系，而且调用方可以给两臂传不同的值 ——
    # 没有任何一条规则会红（红队 2026-09-04，high）。
    froms = re.findall(r"(?im)^FROM\s+(\S+)", dockerfile)
    gate("P4c", [] if len(froms) == 1 else
         [f"P4c Dockerfile 有 {len(froms)} 条 FROM：{froms} —— "
          f"容器跑哪个镜像必须唯一确定"])
    # 「FROM 必须带 digest」由 P4 的 L1 管，这里**不再重复一道** ——
    # 重复的门会让人以为有两道保险，实则一道（我加过一条 P4d，实测它永远轮不到，
    # 因为 L1 先红；删掉比留着诚实）。
    image = froms[0]
    gate("P4b", [] if IMAGE_DIGEST_PLACEHOLDER not in dockerfile else
         [f"P4b 镜像 digest 还是占位值 {IMAGE_DIGEST_PLACEHOLDER[:20]}… —— "
          f"它能过 L1 的正则，却意味着跑的是**没钉住**的镜像：两臂各拉一次可能拿到不同镜像"])
    gate("P5", _check_tests_source((bundle_dir / "image" / "tests" / "test_outputs.py")
                                   .read_text(encoding="utf-8")))

    # P6b：**这个 bundle 里有没有这个臂**（红队 2026-09-07 finding 7）。
    # 在此之前没有这道门：把 `--arms adapt` 打在一个只出了默认两臂的 bundle 上，
    # 掉进 `shutil.copyfile` 的裸 `FileNotFoundError` —— 报错既不说这是臂的问题，
    # 也不说这个 bundle 到底有哪几个臂。**门放在建 run dir 之前**：建完再红会留下一个
    # 空 run dir，下一次同名注入被「run dir 已存在」二次拦住，看起来像另一个毛病。
    import yaml                                    # 局部 import：yaml 不是 f02 的硬依赖
    x = yaml.safe_load((bundle_dir / "task.yaml").read_text(encoding="utf-8"))
    _have_files = sorted(p.name[len("INSTRUCTION."):-len(".md")]
                         for p in (bundle_dir / "arms").glob("INSTRUCTION.*.md"))
    _have_yaml = sorted(x.get("instruction") or {})
    src = bundle_dir / "arms" / f"INSTRUCTION.{arm}.md"
    gate("P6b",
         ([] if src.is_file() else
          [f"P6b 臂 {arm!r} 的题面不在 bundle 的 arms/ 里 —— 这个 bundle 有 {_have_files}。"
           f"非默认臂要在出集时点名：`ops/export_bundle.py <task> --staging … --digest … "
           f"--arms <干预臂>,<参照臂>,{arm}`（公平性协议 §6.6.5）"])
         + ([] if arm in _have_yaml else
            [f"P6b bundle 的 task.yaml 的 instruction 段没有臂 {arm!r} —— 段里有 {_have_yaml}。"
             f"题面文件在而记录不在 = 这份 bundle 不认这个臂，sha 无从核对"]))

    rid = run_id(manifest["task_id"], arm, config_id, seq)
    run_dir = run_root / "runs" / rid
    if run_dir.exists():
        raise PackError(f"run dir 已存在：{run_dir} —— 不覆盖（覆盖会让磁盘证据与遥测行对不上，F9）")
    (run_dir / "work").mkdir(parents=True)
    (run_dir / "log").mkdir()
    shutil.copytree(bundle_dir, run_dir / "bundle")

    # P6：逐字节复制题面，核 sha 与 task.yaml 记的一致（`src` / `x` 由 P6b 备好 ——
    # 同一个文件读两次就有两种可能的答案）
    dst = run_dir / "work" / "INSTRUCTION.md"
    shutil.copyfile(src, dst)
    # 通行证的 task_id 是**记录**，bundle 的 task.yaml 才是这份 bundle 自己说的身份。
    # 只信通行证的话，一份通行证配错 bundle 也查不出来（红队 2026-09-04）。
    gate("P6a", [] if x["task_id"] == manifest["task_id"] else
         [f"P6a bundle 的 task.yaml 说自己是 {x['task_id']!r}，通行证说 "
          f"{manifest['task_id']!r} —— 通行证与 bundle 配错了"])
    want_sha = x["instruction"][arm]["sha256"]
    gate("P6", [] if _sha_file(dst) == want_sha else
         [f"P6 {arm} 臂题面 sha256 {_sha_file(dst)[:16]}… ≠ task.yaml 记的 {want_sha[:16]}…"])

    # P7：装配 work/ 其余内容；strict 臂再叠协议工件的**精确**文件集
    placed: dict[str, str] = {"INSTRUCTION.md": _sha_file(dst)}
    for p in sorted((bundle_dir / "work").rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(bundle_dir / "work")
        # **排除 protocol/**：bundle 里带着它（f01 生成的逐题规则），但它只给 strict 臂。
        # 通用复制会把它放进**两臂** —— 那正好破了 §6.2 的等号判据（裸臂拿到协议的东西）。
        # **排除全部工件挂载点**（`ARTIFACT_MOUNTS`，来自 arms.yaml）：bundle 里带着它们
        # （f01 生成的逐题规则住在 work/protocol/），但每个挂载点只属于声明了它的那个臂。
        # 通用复制会把它放进**每一个臂** —— 那正好破了 §6.2 的等号判据（裸臂拿到协议的东西）。
        if rel.parts and rel.parts[0] in ARTIFACT_MOUNTS:
            continue
        (run_dir / "work" / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, run_dir / "work" / rel)
        placed[str(rel)] = _sha_file(run_dir / "work" / rel)
    provider_rec: dict | None = None
    # P7b：provider 进该臂**独占**的 work/provider/（PA-2/PA-3）。
    # 放在 P8 之前，这样 provider 也进 run dir 的文件集封闭 —— 不是「放进去就不管了」。
    if place_provider:
        # `expect` 与 P2 同源（同一个通道、同一张表）。不给的话 `materialize` 会在
        # 运行时回落到 private 的冻结常量 —— **公开通道在这里红，报的还是「provider 变了」**。
        # 这是同一个 bug 的第二个入口：只修 P2 等于把它往后挪 40 行
        # （`ops/test_provider_pin_channel.py` 的 public 真注入把它抓了出来）。
        ref = PA.materialize(provider_root, run_root, expect=provider_pin_expect(channel))
        placed.update(PA.place_for_arm(ref, run_dir / "work"))
        # P7e（N-611）：**结果侧**再核一次 —— 上面两道核的都是「源」与「缓存」，
        # 这一道核的是「容器会挂进 /task 的那一份」。见 `check_work_provider` 的说明。
        gate("P7e", check_work_provider(run_dir / "work", channel=channel))
        provider_rec = {
            "channel": (channel if channel is not None
                        else (os.environ.get(CHANNEL_ENV) or DEFAULT_CHANNEL)),
            "expect": provider_pin_expect(channel),
            "source_root": str(Path(provider_root).resolve()),
            "sha256_root": ref.sha256_root,
            "n_files": ref.n_files,
        }
    # P7c：边车代码进 run dir（见 SIDECAR_REL 处的说明）
    sidecar_src = Path(RC.__file__).resolve().parent / "egress_proxy.py"
    gate("P7c", [] if sidecar_src.is_file() else [f"P7c 边车源码不存在：{sidecar_src}"])
    shutil.copyfile(sidecar_src, run_dir / SIDECAR_REL)
    # P7d：**网关那一份 h11** 进 run dir（裁定 2026-09-05：边车与网关跑同一个解析器）
    h11_placed = place_h11(run_dir)
    gate("P7d", [] if h11_placed else ["P7d h11 一个文件都没复制进来 —— "
                                       "边车 import 不到它会起不来（fail-closed），"
                                       "但那时候已经在跑了；这里就要红"])
    # 本臂**独有**投放的工件（`genetask/arms.yaml` 的 artifacts；裸臂恒空），
    # 与**别的臂**的工件（P8 拿它判「这个臂拿到了不该有的东西」）。
    proto = arm_files(arm)
    forbidden = other_arm_files(arm)
    for spec in ARM_BY_ID[arm].artifacts:
        # 空清单 / 未发布 = 「这个臂没有它的干预内容」。这不是「暂时没有」，是**干预失败**：
        # 实验照跑、分数照出，结论会变成「协议没用」（F8）。所以在这里红，而不是往下走。
        _status, _files = manifest_status(spec.manifest), manifest_files(spec.manifest)
        gate("P7", [] if (_status == "released" and _files) else
             [f"P7 {arm} 臂的协议工件清单 {spec.manifest} status={_status!r}、条目 {len(_files)} 个 —— "
              f"协议工件是干预本身，缺了它 {arm} 臂就是个裸臂。"
              f"在清单里落定内容并把 status 改成 released 之前，{arm} 臂不得注入"])
        base = (_REPO_ROOT / spec.manifest).parent
        missing = [k for k in _files if not (base / k).is_file()]
        gate("P7", [f"P7 协议工件源文件缺失 {missing}"] if missing else [])
        pdir = run_dir / "work" / spec.mount
        pdir.mkdir(parents=True, exist_ok=True)
        for k in _files:
            shutil.copyfile(base / k, pdir / k)
            placed[f"{spec.mount}/{k}"] = _sha_file(pdir / k)
        if spec.per_task_rules:
            # 逐题生成的四份规则 JSON（按题不同，因此不在封闭清单里，而是进文件集封闭）。
            # 生成器在 f01 侧 —— 它 import reference；注入器只搬**已经生成好**的文件。
            rules_src = bundle_dir / "work" / spec.mount
            if rules_src.is_dir():
                for f in sorted(rules_src.iterdir()):
                    if f.is_file():
                        shutil.copyfile(f, pdir / f.name)
                        placed[f"{spec.mount}/{f.name}"] = _sha_file(pdir / f.name)

    # P8：复制之后再核一次通行证 + run dir 自检
    gate("P8", check_manifest(run_dir / "bundle", manifest, expect_frozen_root=expect_frozen_root)
         + check_run_dir(run_dir, arm=arm, protocol=proto, forbidden=forbidden, expect_work=placed,
                         expect_top={SIDECAR_REL: _sha_file(run_dir / SIDECAR_REL),
                                     **h11_placed}))

    # IN-1：**按运行分配**子网。常量网段两臂并发必然抢同一个网 ——
    # docker 或者拒绝第二个，或者两个项目各自建网成功而地址重叠（更糟）。
    # 抢不到不许回落到默认值：那等于把并发问题变成静默的路由问题。
    alloc = dict(subnets) if subnets else SUB.allocate(require_docker=require_docker)

    # 预算档（卡 4.3）。`x` 是 P6 读进来的 bundle `task.yaml`。
    _budget = REG.budget_for(x.get("stage"))

    # P9：渲染 compose → lint → 落盘（**lint 在落盘前**，否则红了也已有一份能被 -f 直接用的文件躺着）
    text = RC.format_compose(
        task_id=manifest["task_id"],          # **真 task_id** —— 它是网关侧的切片键（N-36）
        run_id=rid, project=compose_project(rid),
        arm=arm, image=image, command=command, config_id=config_id,
        # 模型上游与预算**从 registry 按 config_id 取**（2026-09-05）。此前这里不传，
        # `format_compose` 缺省 `model_upstream=""`，边车 `if a.model_upstream:` 为假 ——
        # **模型反代根本不起**，任务容器里的 OPENAI_BASE_URL 指向一个没人听的端口。
        # `model_upstream=None` → 按 config_id 查 registry（生产路径；查不到就抛，不许静默无上游）。
        # 显式传空串 = **不起模型反代**（测试注入机制用；真跑绝不该这么传）。
        model_upstream=(_model_upstream(config_id) if model_upstream is None else model_upstream),
        # **预算按 bundle 自己声明的 stage 取档**（卡 4.3，2026-09-07）：S7 300 次 /
        # S4 150 次，其余走默认的 100。`stage` 取自 P6 已经读进来的那份 `task.yaml` ——
        # 不再开第二次读：同一个文件读两次就有两种可能的答案。
        # `ops/run_f02_a1.py --max-calls/--max-tokens` 显式给的值仍然赢过档位
        # （`REG.budget_for` 逐键判断），覆盖语义不变。
        max_calls=_budget["max_calls"], max_tokens=_budget["max_tokens"],
        task_subnet=alloc["task_subnet"], egress_subnet=alloc["egress_subnet"],
        gateway=RC.GATEWAY,
        proxy_py=str(run_dir / SIDECAR_REL),          # **本 run 自己的那份**，不是全局路径
        h11_dir=str(run_dir / H11_REL),
        # N-48 的 run_uid/run_gid 由 `format_compose` 补默认 —— 三处各自 format
        # 同一个模板正是漏字段的来源，现在只有一个出口。
        workdir=str(run_dir / "work"), logdir=str(run_dir / "log"))
    problems = RC.lint_compose(text, expect_workdir=run_dir / "work",
                               runs_root=run_root / "runs")
    if f"{run_dir / 'work'}:/task" not in text:
        problems.append(f"P9 compose 没把本 run 的 work/ 挂到 /task —— "
                        f"挂错目录会让两臂读到同一份题面")
    gate("P9", problems)
    (run_dir / "compose.yml").write_text(text, encoding="utf-8")

    # 边车 sha 记进 inject.json —— 它决定了身份注入用的是哪一版代码
    files = {str(p.relative_to(run_dir)): _sha_file(p)
             for p in sorted(run_dir.rglob("*")) if p.is_file()}
    inj = {"run_id": rid, "arm": arm, "config_id": config_id, "seq": seq,
           "task_id": manifest["task_id"],
           # **机器标识**（裁定 ⑮）：run_id 末尾那一段是从哪来的，事后要查得到。
           # 指纹的稳定源原文不在这里 —— 记的是哈希与来源名。
           "machine": machine_info(),
           "runner_version": runner_version(),
           "image": image,                      # 容器实际跑的镜像（带 digest，取自 Dockerfile）
           "executables": {                     # 参与这次运行的可执行物 —— 逐个记 sha
               SIDECAR_REL: _sha_file(run_dir / SIDECAR_REL),
               # 解析器也是"参与这次运行的可执行物"：边车与网关必须同一份 h11，
               # 版本不同 =「两个解析器看法不同」那一类洞回来了（N-91）。
               **h11_placed,
               "compose.yml": None,             # 落盘后补（见下）
           },
           # **这次运行用的是哪条通道的哪份 provider**（N-611）。不记的话，事后
           # 「这个 run 到底跑在公开 provider 上吗」只能靠翻 28 606 个文件名找 `bj*`。
           "provider": provider_rec,
           "frozen_manifest": dict(manifest.get("frozen_manifest") or {}),
           # **两条版本轴**（裁定 2026-09-05）：任务集回答「agent 看到的东西变了吗」，
           # 参考面回答「我们算 gold 的方式变了吗」。**可比性要求两者都相同** ——
           # 只记一个的话，两次 gold 算法不同的运行会看起来完全可比。
           "reference_manifest": dict(manifest.get("reference_manifest") or {}),
           "compose_project": compose_project(rid),
           "subnets": alloc,                    # IN-1：这次运行拿到的网段与判否依据
           # N-61：接收侧门的**三个自有文件**的 sha（裁定 2026-09-05）。
           # 门自己也核这三个 sha，但那是**自证** —— 改了门的人也能改基线。
           # 记进这里是为了让 **f01** 拿仓库里的那份去比：他证与自证要分开。
           "answer_plane_guard": APG.identity(),
           "protocol_artifacts": sorted(proto),
           "files": files}
    inj["executables"]["compose.yml"] = _sha_file(run_dir / "compose.yml")
    inj["files"]["compose.yml"] = inj["executables"]["compose.yml"]
    (run_dir / "inject.json").write_text(json.dumps(inj, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8")
    return Injected(run_dir=run_dir, run_id=rid, arm=arm, config_id=config_id,
                    frozen_manifest=inj["frozen_manifest"], files=files)
