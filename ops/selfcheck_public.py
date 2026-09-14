#!/usr/bin/env python3
"""外部用户自检：**只查外部环境能自己满足的项**（卡 C2，2026-09-13 落地）。

这一份和 `ops/test_env.py` 是两件东西，别搞混：

* `ops/test_env.py` —— **发布方的内部自检**。它假定 `/data` 落点、数据湖
  （`market_lake`）、发布方那个解释器与发布方的网关地址都在。**外部用户不要跑它**，
  在干净机器上必然红一片，而那些红不是缺陷。
* 本文件 —— **外部自检**。只查「拿到发布件的人自己能满足」的六件事：
  Python 版本、六个依赖包、Docker 在不在且内存够、发布附件落位与 sha256、
  三条冻结根、网关起不起得来。**不碰 `/data`、不碰数据湖、不认发布方的解释器与地址。**

跑法（在仓库根下，用你自己的解释器）::

    python3 ops/selfcheck_public.py                      # 单机形态（默认）
    python3 ops/selfcheck_public.py --role data          # 只当数据面（这台不需要 docker）
    python3 ops/selfcheck_public.py --downloads ~/dl     # 附件放在别处
    python3 ops/selfcheck_public.py --json out.json      # 机读结果
    python3 ops/selfcheck_public.py --strict             # 「跳过」和「登记在案」也算不通过

退出码：``0`` = 没有红条；``1`` = 有红条；``2`` = 自检自己炸了。

**四种状态**（`--strict` 下后三种都算不通过）：

* ``绿``     —— 查过了，对的。
* ``红``     —— 查过了，不对。**这条不修就往下走，后面会变成看不懂的报错。**
* ``跳过``   —— 前置还没做（附件还没下、答案面还没落位）。不是缺陷，是「还没轮到」。
* ``登记在案`` —— 查出来确实不一致，但这是**已知的发布缺件**，不是你这台机器的问题；
  条目里写了对应的登记编号。

本文件**不写任何东西到磁盘**（`--json` 除外），网关那一项起完就停。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: 外部路径的最低 Python。Mac 自带的 3.9 明确不够；3.12 是外部路径唯一有实测背书的版本。
MIN_PY: tuple[int, int] = (3, 12)

#: 六个依赖包（仓库里没有 requirements 文件，这一行就是全部）。左=装的名字，右=import 的名字。
SIX_PACKAGES: tuple[tuple[str, str], ...] = (
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pandas", "pandas"),
    ("pyarrow", "pyarrow"),
    ("duckdb", "duckdb"),
    ("pyyaml", "yaml"),
)

#: Docker 可用内存下限。**注意不是 16 GiB**：Docker Desktop 的 UI 写「16 GB」时
#: `docker info` 自报的 `MemTotal` 实测是 16,748,077,056 B ≈ 15.6 GiB（引擎自己留了一截）。
#: 门设在 16 GiB 会把「已经按文档调到 16 GB 的人」判红，所以设在 15 GiB。
#: 对照：Docker Desktop 默认 8 GB 自报 ≈ 8.5e9 B，离这条线差得很远，不会误放。
DOCKER_MEM_FLOOR = 15 * 1024 ** 3

#: 三条轴在 `ops/freeze_v10.py --check-all` 输出里的名字。
FREEZE_AXES = ("任务集（private）", "任务集（public）", "参考面")

#: 已知的发布缺件：公开任务集轴漂，且差异**全部**落在 `channel_fixtures/`。
#: 成因是公开题集的输入夹具（S4–S7 共 18 道题）不在仓库里、也不在前两件附件里（它们在
#: `public_runtime_material` 那一件），不是你下坏了。缺件到底在哪一件、挂没挂上去，
#: 由 `_public_material()` 从 `ops/release/attachments.json` **现算**（N-808）。
KNOWN_PUBLIC_FIXTURE_PREFIX = "channel_fixtures/"

GREEN, RED, SKIP, KNOWN = "绿", "红", "跳过", "登记在案"


class Item:
    def __init__(self, ident: str, title: str) -> None:
        self.id = ident
        self.title = title
        self.status = SKIP
        self.detail = ""
        self.fix = ""

    def set(self, status: str, detail: str, fix: str = "") -> "Item":
        self.status, self.detail, self.fix = status, detail, fix
        return self

    def as_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "status": self.status,
                "detail": self.detail, "fix": self.fix}


# --------------------------------------------------------------------------- #
# ① Python 版本
# --------------------------------------------------------------------------- #
def check_python() -> Item:
    it = Item("python", f"Python ≥ {MIN_PY[0]}.{MIN_PY[1]}")
    got = sys.version_info[:3]
    where = sys.executable
    if got[:2] >= MIN_PY:
        return it.set(GREEN, f"{got[0]}.{got[1]}.{got[2]}（{where}）")
    return it.set(
        RED,
        f"当前是 {got[0]}.{got[1]}.{got[2]}（{where}）",
        "Mac 自带的 python3 通常是 3.9，不够。装一个 3.12 再建独立环境："
        "`brew install python@3.12` 之后 "
        "`/opt/homebrew/bin/python3.12 -m venv ~/genebench-env`；"
        "然后用 `~/genebench-env/bin/python ops/selfcheck_public.py` 重跑。",
    )


# --------------------------------------------------------------------------- #
# ② 六个依赖包
# --------------------------------------------------------------------------- #
def check_deps() -> Item:
    it = Item("deps", "六个依赖包")
    missing: list[str] = []
    have: list[str] = []
    for pip_name, mod_name in SIX_PACKAGES:
        try:
            __import__(mod_name)
        except Exception:  # noqa: BLE001 —— import 失败的原因五花八门，都算「没有」
            missing.append(pip_name)
        else:
            have.append(pip_name)
    if not missing:
        return it.set(GREEN, "六个都在：" + " ".join(have))
    return it.set(
        RED,
        "缺 " + " ".join(missing),
        "仓库里没有 requirements 文件，这六个就是全部："
        f"`{Path(sys.executable).name} -m pip install " + " ".join(n for n, _ in SIX_PACKAGES) + "`"
        "（国内直连 pypi.org 挂住过 40 分钟，慢就加 "
        "`-i https://pypi.tuna.tsinghua.edu.cn/simple`）",
    )


# --------------------------------------------------------------------------- #
# ③ Docker
# --------------------------------------------------------------------------- #
def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, "", "命令不存在"
    except subprocess.TimeoutExpired:
        return 124, "", f"超过 {timeout} 秒没返回"
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _gib(n: float) -> str:
    return f"{n / 1024 ** 3:.1f} GiB"


def check_docker(role: str) -> Item:
    it = Item("docker", f"Docker 可用且内存 ≥ {_gib(DOCKER_MEM_FLOOR)}")
    if role == "data":
        return it.set(SKIP, "--role data：这台只当数据面，数据面不需要 docker",
                      "要在这台机器上跑题就改成 --role single 再查一遍")
    if shutil.which("docker") is None:
        return it.set(RED, "PATH 里没有 docker",
                      "装 Docker Desktop（Mac）或 docker-ce（Linux），要 ≥ 24 且带 compose v2")
    rc, ver, err = _run(["docker", "version", "--format", "{{.Server.Version}}"])
    if rc != 0 or not ver:
        return it.set(RED, f"`docker version` 不通：{err or ver or rc}",
                      "Docker 装了但引擎没起来 —— 先把 Docker Desktop 打开（或 `systemctl start docker`）")
    rc, mem, err = _run(["docker", "info", "--format", "{{.MemTotal}}"])
    if rc != 0 or not mem.isdigit():
        return it.set(RED, f"引擎 {ver}，但 `docker info` 读不到 MemTotal：{err or mem}", "")
    total = int(mem)
    if total < DOCKER_MEM_FLOOR:
        return it.set(
            RED,
            f"引擎 {ver}，但可用内存只有 {_gib(total)}（{total} B）",
            "Docker Desktop 默认只给 8 GB，跑不动两个容器。"
            "Docker Desktop → Settings → Resources → Memory limit 调到 **16 GB** 再 Apply & restart；"
            "Linux 上则是宿主机内存本身要够。",
        )
    return it.set(GREEN, f"引擎 {ver}，可用内存 {_gib(total)}（{total} B）")


# --------------------------------------------------------------------------- #
# ④ 发布附件
# --------------------------------------------------------------------------- #
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _dedup(paths: list[Path]) -> list[Path]:
    """按**解析后的真实路径**去重，保序。

    `$GENEBENCH_ROOT` 与「仓库的父目录」重合是常态（README §2.1 的 `REPO=$GB/repo`），
    重合时那句「找过：…」会把同一个路径**打印两遍** —— 读的人合理地以为查了两个地方
    （2026-09-13 卡 Tfin 实测两遍 `…/gb/downloads`）。
    """
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        try:
            key = str(p.resolve())
        except OSError:                                   # pragma: no cover
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _downloads_candidates(explicit: str | None) -> list[Path]:
    """附件可能在哪儿。**README 写的落点必须在这张表里**（N-821，2026-09-13）。

    原先三处（`cwd/downloads`、`$GENEBENCH_ROOT/downloads`、仓库父目录 `/downloads`）
    在 README 与手册里**一次都没出现过**（全树 `grep downloads` 两份文档 = 0 命中），
    而 README §2.1a 的 `curl -L -O` 紧接在 §2.1 的 `cd $REPO` 之后 —— 包落在**仓库根**下，
    三处一处都不是它。于是外部用户照文档做完，第一次自检必然看到「还没找到附件」。
    这一版两边取齐：**仓库根**与 `$GENEBENCH_ROOT` 本身都进候选，README §2.1a 也写明了落点。
    """
    if explicit:
        return [Path(explicit).expanduser()]
    out = []
    env = os.environ.get("GENEBENCH_DOWNLOADS", "").strip()
    if env:
        out.append(Path(env).expanduser())
    out.append(Path.cwd() / "downloads")
    root = os.environ.get("GENEBENCH_ROOT", "").strip()
    if root:
        out.append(Path(root) / "downloads")
    out.append(REPO_ROOT.parent / "downloads")
    out.append(REPO_ROOT)                                 # README §2.1a 的 curl 就落在这里
    out.append(Path.cwd())
    if root:
        out.append(Path(root))
    return _dedup(out)


def _load_attachments() -> list[dict]:
    """`ops/release/attachments.json` 里的条目；读不出来就回空表（调用方按空表退让）。"""
    reg = REPO_ROOT / "ops" / "release" / "attachments.json"
    try:
        return list(json.loads(reg.read_text(encoding="utf-8"))["attachments"])
    except Exception:  # noqa: BLE001
        return []


def _public_material() -> dict | None:
    """哪一件附件装着公开题集树与公开标定物料。**按 `role` 认，不按名字写死。**"""
    for e in _load_attachments():
        if e.get("role") == "public_runtime_material":
            return e
    return None


def check_attachments(explicit: str | None) -> Item:
    it = Item("attachments", "发布附件落位与 sha256")
    reg = REPO_ROOT / "ops" / "release" / "attachments.json"
    if not reg.is_file():
        return it.set(RED, f"读不到 {reg.relative_to(REPO_ROOT)}",
                      "这个文件是附件名/字节数/sha256 的唯一来源，缺了说明这棵树不完整")
    try:
        entries = json.loads(reg.read_text(encoding="utf-8"))["attachments"]
    except Exception as exc:  # noqa: BLE001
        return it.set(RED, f"{reg.name} 解析不了：{exc}", "")
    # 件数**从清单读**，不写死 —— 发布件加一件就该跟着变，而写死的数字不会报错。
    it.title = f"发布附件落位与 sha256（清单登记 {len(entries)} 件）"

    # `download_url` 是空串 = **这一件还没上传到 Release**，外部用户今天拿不到它。
    # 把它判红是冤枉人；当没这回事也不行 —— 它缺了后面会变成别的报错。所以分开说。
    published = [e for e in entries if (e.get("download_url") or "").strip()]
    pending = [e for e in entries if not (e.get("download_url") or "").strip()]
    pending_note = ""
    if pending:
        pending_note = ("\n    还有 " + str(len(pending)) + " 件登记了但**还没上传到 Release**（"
                        + "、".join(e["name"] for e in pending)
                        + "）—— `ops/release/attachments.json` 里它们的 `download_url` 是空串。"
                        "缺了会在后面变成别的报错，不是这一项判红。")

    for cand in _downloads_candidates(explicit):
        if not cand.is_dir():
            continue
        if any((cand / e["name"]).is_file() for e in entries):
            break
    else:
        names = " / ".join(e["name"] for e in published) or "（清单里一件都还没上传）"
        urls = "\n".join(f"    curl -L -O {e['download_url']}" for e in published)
        return it.set(
            SKIP,
            f"还没找到附件（{names}）—— 找过：" +
            "、".join(str(p) for p in _downloads_candidates(explicit)) + pending_note,
            "已经挂上去的那几件匿名就能下，不需要 token：\n" + urls +
            "\n  在**仓库根**下直接跑（README §2.1a 就是这么写的）自检就找得到；"
            "也可以放进 `./downloads/`，或者用 `--downloads <目录>` 指过来。",
        )

    bad: list[str] = []
    ok: list[str] = []
    absent_pending: list[str] = []
    for e in entries:
        f = cand / e["name"]
        if not f.is_file():
            (absent_pending if e in pending else bad).append(
                f"{e['name']}：不在 {cand}" + ("（还没上传，拿不到是正常的）" if e in pending else ""))
            continue
        size = f.stat().st_size
        if size != e["bytes"]:
            bad.append(f"{e['name']}：字节数 {size}，清单记 {e['bytes']} —— 没下全")
            continue
        got = _sha256(f)
        if got != e["sha256"]:
            bad.append(f"{e['name']}：sha256 {got}，清单记 {e['sha256']}")
        else:
            ok.append(f"{e['name']}（{size} B）")
    if bad:
        return it.set(RED, f"目录 {cand}\n    " + "\n    ".join(bad),
                      "删掉重下。下载命令见 README §2.1a；下完先 `sha256sum -c` 再解包。"
                      "附件到底有几件、各自的 sha256 与地址，以 `ops/release/attachments.json` 为准。")
    detail = f"目录 {cand}，{len(ok)} 件逐字对上：\n    " + "\n    ".join(ok)
    if absent_pending:
        detail += "\n    " + "\n    ".join(absent_pending)
    return it.set(GREEN, detail + pending_note)


# --------------------------------------------------------------------------- #
# ⑤ 三条冻结根
# --------------------------------------------------------------------------- #
def _parse_freeze(text: str) -> dict[str, dict]:
    """把 `--check-all` 的输出拆成 {轴名: {'drifted': bool, 'diffs': [...]}}。"""
    out: dict[str, dict] = {}
    cur: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        for axis in FREEZE_AXES:
            if line.startswith("[") and axis in line and "]" in line:
                cur = axis
                out[axis] = {"drifted": "漂" in line.split("]", 1)[0], "diffs": []}
                break
        else:
            if cur and line.startswith("差异 "):
                out[cur]["diffs"].append(line[len("差异 "):].strip())
    return out


def check_freeze() -> Item:
    it = Item("freeze", "三条冻结根（private / public / 参考面）")
    script = REPO_ROOT / "ops" / "freeze_v10.py"
    if not script.is_file():
        return it.set(RED, "没有 ops/freeze_v10.py", "这棵树不完整")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    rc, out, err = _run_in_repo([sys.executable, str(script), "--check-all"], env, timeout=1800)
    axes = _parse_freeze(out + "\n" + err)
    missing = [a for a in FREEZE_AXES if a not in axes]
    if missing:
        # **打子进程的最后一行，不是第一行**（N-822，2026-09-13）。
        # 第一行永远是 `Traceback (most recent call last):` —— 它不含任何信息，
        # 而真因在最后一行。实测只缺 `pyyaml` 时：`genetask/packager.py:29` 的
        # `import yaml` 抛 `ModuleNotFoundError`，第 2 项已经把它报红了，
        # 而这一项却写「说明这棵树不完整，或者你不是在仓库根下跑的」——
        # **树是完整的、目录也是对的**，用户被支去查一件没坏的事。
        lines = [l for l in (out + "\n" + err).splitlines() if l.strip()]
        last = lines[-1] if lines else ""
        if "ModuleNotFoundError" in last or "ImportError" in last:
            return it.set(
                RED,
                f"`--check-all` 起不来 —— 它缺一个 python 包（退出码 {rc}）：{last}",
                "**这不是树不完整、也不是目录不对**：回**第 2 项**，把六个包装齐"
                "（`fastapi uvicorn pandas pyarrow duckdb pyyaml`），这一项会跟着变绿。",
            )
        return it.set(
            RED,
            f"`--check-all` 没有报出 {'、'.join(missing)}（退出码 {rc}）"
            + ("；它说：" + last if last else ""),
            "三条轴里 private 与参考面只读仓库自己，$GENEBENCH_ROOT 是空的也该算得出来。"
            "算不出来说明这棵树不完整，或者你不是在仓库根下跑的。",
        )

    drifted = [a for a in FREEZE_AXES if axes[a]["drifted"]]
    if not drifted:
        return it.set(GREEN, "三条轴与 RELEASE_MANIFEST 逐字相同")

    pub = "任务集（public）"
    only_public = drifted == [pub]
    pub_diffs = axes[pub]["diffs"] if pub in axes else []
    all_fixtures = bool(pub_diffs) and all(d.startswith(KNOWN_PUBLIC_FIXTURE_PREFIX) for d in pub_diffs)
    if only_public and all_fixtures:
        return it.set(
            KNOWN,
            f"private 与参考面一致；公开轴漂了，{len(pub_diffs)} 条差异**全部**落在 "
            f"`{KNOWN_PUBLIC_FIXTURE_PREFIX}`",
            _missing_public_material_hint(),
        )
    lines = [f"{a}：" + ("漂了" if axes[a]["drifted"] else "一致") for a in FREEZE_AXES]
    if pub_diffs:
        lines.append("公开轴差异：" + "、".join(pub_diffs[:8]) + ("…" if len(pub_diffs) > 8 else ""))
    return it.set(
        RED, "\n    ".join(lines),
        "**不要**用 `--write*` 去把它重冻绿 —— 那是把判据改成现状。"
        "先确认你解包的是发布件本身、$GENEBENCH_ROOT 指对了。",
    )


def _missing_public_material_hint() -> str:
    """第 5 项「登记在案」那一条的下文。

    **与第 4 项同源**（都读 `ops/release/attachments.json`）—— 这里曾经写死着
    「那一件的 `download_url` 还是空串 —— 还没上传到 Release。等它挂上去……」，
    而同一次运行的第 4 项已经把那一件的 `curl` 地址打出来了：
    外部用户在同一屏上读到互相矛盾的两句，还被劝去等一个已经到位的东西（N-808）。
    **这个文件里不许再出现任何一句写死的「上传了没有」。**
    """
    head = ("这是已知的发布缺件，不是你下坏了 —— 包的逐件 sha256 是另外查的。"
            "缺的是整棵公开题集树（`reference/tasks/public/v1.0-smoke-public/`）"
            "与公开标定物料。")
    e = _public_material()
    if e is None:
        return (head + "它在哪一件附件里、那一件挂没挂上去，"
                "以 `ops/release/attachments.json` 为准（这棵树里读不到那份清单）。")
    name = e.get("name", "（清单里没有名字）")
    url = (e.get("download_url") or "").strip()
    if url:
        return (head + f"它在附件 `{name}` 里，**已经挂在 Release 上**，匿名就能下：\n"
                f"    curl -L -O {url}\n"
                "  下完按 README §2.1a 落位（`sha256` 与第 4 项同一份清单），这一条就绿。")
    return (head + f"它已经打成附件 `{name}` 登记在 `ops/release/attachments.json` 里，"
            "但那一件的 `download_url` 还是空串 —— **还没上传到 Release**。"
            "等它挂上去、按 README §2.1a 落位之后这一条就绿。详见 README §5「发布状态」。")


def _run_in_repo(cmd: list[str], env: dict, timeout: int = 60) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, capture_output=True,
                           text=True, timeout=timeout)
    except FileNotFoundError:
        return 127, "", "命令不存在"
    except subprocess.TimeoutExpired:
        return 124, "", f"超过 {timeout} 秒没返回"
    return p.returncode, p.stdout, p.stderr


# --------------------------------------------------------------------------- #
# ⑥ 网关
# --------------------------------------------------------------------------- #
def _free_port(host: str) -> int:
    with socket.socket() as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


def _bindable(host: str) -> bool:
    try:
        with socket.socket() as s:
            s.bind((host, 0))
        return True
    except OSError:
        return False


def _get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310 —— 只打本机显式地址
            return int(r.status), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return int(e.code), ""
    except Exception:  # noqa: BLE001
        return 0, ""


def check_gateway(start: bool) -> Item:
    it = Item("gateway", "网关起得来、/healthz 回 200")
    try:
        sys.path.insert(0, str(REPO_ROOT))
        import genebench_config as cfg  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        return it.set(RED, f"import genebench_config 就炸了：{exc}", "先把上面「六个依赖包」修绿")

    host = cfg.GATEWAY_HOST
    try:
        cfg.assert_no_wildcard_bind(host)
    except Exception as exc:  # noqa: BLE001
        return it.set(RED, f"GATEWAY_HOST={host!r} 过不了通配绑定这道红线：{exc}",
                      "网关只许绑显式地址，不许 0.0.0.0")

    if not _bindable(host):
        return it.set(
            RED, f"`genebench_config.py::GATEWAY_HOST` 现在是 {host}，**这台机器绑不上它**",
            "这个常量没有环境变量可覆盖（端口有 `GENEBENCH_GATEWAY_PORT`，地址没有）。"
            "把它改成本机地址：单机形态用 `127.0.0.1`（容器要打它就用本机 LAN 地址）。手册 §1.3 有三处要一起改。",
        )

    tables = Path(cfg.snapshot_tables_dir("public")) if hasattr(cfg, "snapshot_tables_dir") else None
    if tables is None or not tables.is_dir():
        return it.set(
            SKIP, f"绑定地址 {host} 没问题，但快照表目录还没落位（{tables}）",
            "把附件解出来的 `tables/` 接到 `$GENEBENCH_ROOT/snapshots/public_v1/tables`"
            "（软链就行），再跑一次这一项。",
        )
    if not start:
        return it.set(SKIP, f"--no-start-gateway：只查到「地址能绑 + 表在位（{tables}）」为止", "")

    port = _free_port(host)
    env = dict(
        os.environ,
        GENEBENCH_CHANNEL="public",
        GENEBENCH_GATEWAY_PORT=str(port),
        GENEBENCH_GATEWAY_BACKEND="snapshot",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUNBUFFERED="1",
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "gateway.run", "--workers", "1"],
        cwd=str(REPO_ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    base = f"http://{host}:{port}"
    t0 = time.time()
    code, body = 0, ""
    try:
        # 等 300 秒不是保守：网关的 import 链（fastapi+pandas+pyarrow+duckdb+snapshots.*）
        # 在发布方那台机器上实测要 41 秒才开始监听。
        while time.time() - t0 < 300:
            if proc.poll() is not None:
                tail = (proc.stdout.read() if proc.stdout else "")[-1200:]
                return it.set(RED, f"进程起来就退了（退出码 {proc.returncode}）：\n{tail}",
                              "$GB 下一个 0644 的文件就足够让它拒绝启动。"
                              "**照上面那段里网关自己打的「修：」那一行做** —— "
                              "它按违例的类别分了岔，`--harden` 收不掉的那几类会明说"
                              "（`ops/guard_modes.py::fix_hint`，N-818）。")
            code, body = _get(base + "/healthz", timeout=3)
            if code == 200:
                break
            time.sleep(1)
        took = int(time.time() - t0)
        if code != 200:
            return it.set(RED, f"等了 {took} 秒，{base}/healthz 还是不回 200", "")
        try:
            h = json.loads(body)
        except Exception:  # noqa: BLE001
            return it.set(RED, f"/healthz 回了 200 但不是 JSON：{body[:200]}", "")
        if h.get("channel") != "public":
            return it.set(
                RED, f"起来了，但 `channel` 是 {h.get('channel')!r}，不是 public：{body[:300]}",
                "「只看 ok:true 不够」—— 起了个私有实例却以为在跑公开通道，"
                "数字看起来全对，只是来自另一份数据。",
            )
        bind = str(h.get("bind", ""))
        if bind.startswith("0.0.0.0"):
            return it.set(RED, f"起来了，但绑在 {bind} —— 通配绑定是红线", "")
        return it.set(
            GREEN,
            f"{took} 秒起来；{base}/healthz = 200，"
            f"channel={h.get('channel')}、backend={h.get('backend')}、bind={bind}、"
            f"freeze_line={h.get('freeze_line')}（查完已停，端口已释放）",
        )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)


# --------------------------------------------------------------------------- #
def run_all(args: argparse.Namespace) -> list[Item]:
    items = [check_python(), check_deps(), check_docker(args.role),
             check_attachments(args.downloads), check_freeze(),
             check_gateway(start=not args.no_start_gateway)]
    return items


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="GeneBench 外部自检：只查外部环境能自己满足的项（不是 ops/test_env.py）")
    ap.add_argument("--role", default="single", choices=("single", "data", "exec"),
                    help="这台机器干什么：single=数据面+执行面同机（默认）；"
                         "data=只当数据面（不需要 docker）；exec=只当执行面")
    ap.add_argument("--downloads", default=None,
                    help="发布附件放在哪个目录（有几件以 ops/release/attachments.json 为准）")
    ap.add_argument("--no-start-gateway", action="store_true",
                    help="网关那一项只查到「地址能绑 + 表在位」为止，不真起")
    ap.add_argument("--strict", action="store_true",
                    help="「跳过」与「登记在案」也算不通过（你认为一切都该就位时用）")
    ap.add_argument("--json", default=None, help="把机读结果写到这个文件")
    args = ap.parse_args(argv)

    print(f"GeneBench 外部自检 —— 仓库 {REPO_ROOT}")
    print(f"解释器 {sys.executable}")
    print(f"GENEBENCH_ROOT = {os.environ.get('GENEBENCH_ROOT') or '（没设，用默认值）'}")
    print(f"形态 --role {args.role}\n")

    items = run_all(args)
    for i, it in enumerate(items, 1):
        print(f"[{it.status}] {i}. {it.title}")
        if it.detail:
            print("    " + it.detail.replace("\n", "\n    "))
        if it.fix and it.status != GREEN:
            print("    → " + it.fix.replace("\n", "\n      "))
        print()

    reds = [it for it in items if it.status == RED]
    softs = [it for it in items if it.status in (SKIP, KNOWN)]
    print("—" * 60)
    print(f"绿 {sum(1 for it in items if it.status == GREEN)} / "
          f"红 {len(reds)} / 跳过 {sum(1 for it in items if it.status == SKIP)} / "
          f"登记在案 {sum(1 for it in items if it.status == KNOWN)}")
    if reds:
        print("要处理：" + "、".join(it.title for it in reds))
    elif softs and args.strict:
        print("--strict：还有没就位的项 —— " + "、".join(it.title for it in softs))
    elif softs:
        print("没有红条。还有没轮到的项（不算不通过）：" + "、".join(it.title for it in softs))
    else:
        print("六项全绿。")

    if args.json:
        Path(args.json).write_text(
            json.dumps({"repo": str(REPO_ROOT), "python": sys.version,
                        "role": args.role,
                        "items": [it.as_dict() for it in items]},
                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"（机读结果写到了 {args.json}）")

    if reds:
        return 1
    if args.strict and softs:
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
