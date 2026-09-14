# -*- coding: utf-8 -*-
"""卡 A2：统一基座搬进仓库 + `harnesses/build.sh` 能在干净机器上自救（2026-09-13）。

**这份测试守的是「一台只有 Docker 的干净机器，光凭这棵树能不能构出基座」**。
2026-09-13 的 Mac 外部验收在这一条上阻塞：`harnesses/build.sh` 要求本机已有
`gb-base:bookworm-r1`，而构它的 Dockerfile **不在仓库里**，脚本只让用户去
发布方一台他没有的机器上找。三件事因此必须有 import 期就响的门：

1. `build/base/` 那一套在仓库里，而且 Node 的 tarball 是**按架构**选的 ——
   只钉 x64 的哈希时，Apple Silicon 上必然「下 arm64 的包、拿 x64 的哈希核」，
   失败信息是 `sha256sum: WARNING: 1 computed checksum did NOT match`，
   看起来像下载损坏，而真正的原因是这份 Dockerfile 只认一个架构。
2. `harnesses/build.sh` 里**不许有不带花括号、后面紧跟非 ASCII 字符的变量插值**。
   macOS 的 bash 3.2 在 UTF-8 locale 下会把中文标点的头一个字节吃进变量名，
   于是 `set -u` 报 `BASE_IMAGE?: unbound variable` —— 用户看到的是这句，
   而不是「你缺基座」。实测 `LC_ALL=C` 下同一行正常，所以这是个**只在某些
   locale 下发作**的 bug，恰恰是最难被发布方自己踩到的那一类（N-750）。
3. 报错文案里不许再出现发布方的绝对路径 —— 外部用户照着它去查，什么也查不到。
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BASE_DIR = REPO / "build" / "base"
BASE_DOCKERFILE = BASE_DIR / "Dockerfile"
BUILD_SH = REPO / "harnesses" / "build.sh"
REPORT = REPO / "ops" / "reports" / "base_image_portability.md"

#: 统一基座（N-62）。
BASE_IMAGE = "gb-base:bookworm-r1"

#: `python:3.12-slim-bookworm` 的 **OCI image index** digest。钉 index 而不是钉
#: 某一架构的镜像 digest，是「同一行 FROM 在 x86_64 与 arm64 上都解析得出」的前提。
PYTHON_INDEX_DIGEST = "sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254"

#: 两个架构的 Node tarball sha256，取自 nodejs.org 的 SHASUMS256.txt（2026-09-13 实取）。
NODE_VERSION = "22.23.2"
NODE_SHA_AMD64 = "d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307"
NODE_SHA_ARM64 = "fff4078c5def658577f92c88db7db3bc0072924bfb93fe52c1e744a54e94abb8"

#: 既有 `gb-base:bookworm-r1` 里 `pip freeze --all` 的实测结果（去掉 pip 自身，
#: 它是基础镜像自带的）。constraints 与它对不上 = 新构出来的基座数值栈变了。
FROZEN_PINS = {
    "numpy": "2.5.2",
    "pandas": "2.3.3",
    "pyarrow": "25.0.1",
    "python-dateutil": "2.9.0.post0",
    "pytz": "2026.3.post1",
    "six": "1.17.0",
    "tzdata": "2026.3",
}

#: 不带花括号、且后面紧跟一个非 ASCII 字符的变量插值。
_BARE_VAR_BEFORE_NONASCII = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*(?=[^\x00-\x7f])")

#: 发布方内网的绝对路径。外部用户手里没有这些路径。
_PUBLISHER_PATHS = ("/data/genebench_runner", "/data/shared/genebench", "192.168.1.219")


# ---------------------------------------------------------------------------
# ① build/base/ 那一套在仓库里，而且认两个架构
# ---------------------------------------------------------------------------
def test_base_build_context_is_in_the_repo():
    """基座的构建上下文必须在仓库里 —— 这正是外部验收阻塞的那一件。"""
    assert BASE_DOCKERFILE.is_file(), (
        "缺 build/base/Dockerfile。没有它，clone 下来的人构不出统一基座，"
        "harnesses/build.sh 只能让他去一台他没有的机器上找。"
    )
    for f in ("requirements.txt", "constraints.txt", "README.md"):
        assert (BASE_DIR / f).is_file(), f"缺 build/base/{f}"


def test_base_from_pins_the_multi_arch_index_digest():
    """`FROM` 钉的是 index digest，所以同一行在 amd64 与 arm64 上都解析得出。"""
    txt = BASE_DOCKERFILE.read_text(encoding="utf-8")
    froms = [ln.strip() for ln in txt.splitlines() if ln.strip().startswith("FROM ")]
    assert len(froms) == 1, f"build/base/Dockerfile 应当只有 1 条 FROM，现在有 {len(froms)} 条"
    assert PYTHON_INDEX_DIGEST in froms[0], f"FROM 没有钉 {PYTHON_INDEX_DIGEST}：{froms[0]}"


def test_node_tarball_is_selected_per_architecture():
    """Node 的包与哈希是**按架构分的**；只钉一个 = 另一个架构上必然核不过。"""
    txt = BASE_DOCKERFILE.read_text(encoding="utf-8")
    assert NODE_SHA_AMD64 in txt, "缺 x64 的 Node sha256"
    assert NODE_SHA_ARM64 in txt, "缺 arm64 的 Node sha256"
    assert NODE_SHA_AMD64 != NODE_SHA_ARM64, "两个架构的哈希不可能相同 —— 抄错了"
    assert f"NODE_VERSION={NODE_VERSION}" in txt
    # 两个 tarball 名字都要出现在选择分支里
    assert "linux-${nodeArch}.tar.xz" in txt, "tarball 名字没有按架构拼"
    for arch in ("amd64", "arm64"):
        assert re.search(rf"^\s*{arch}\)", txt, re.M), f"case 里没有 {arch} 分支"


def test_arch_comes_from_dpkg_not_buildkit_targetarch():
    """架构从 `dpkg --print-architecture` 取：legacy builder 下 TARGETARCH 可能是空的，

    而空值会落到「不支持的架构」分支 —— 报出来的原因跟真正的原因无关。
    """
    txt = BASE_DOCKERFILE.read_text(encoding="utf-8")
    assert "dpkg --print-architecture" in txt, "架构不是从 dpkg 取的"
    code = [ln for ln in txt.splitlines() if not ln.strip().startswith("#")]
    assert not any(re.search(r"\bARG\s+TARGETARCH\b", ln) for ln in code), \
        "声明了 ARG TARGETARCH —— legacy builder 下它是空的，会落到「不支持的架构」分支"


def test_requirements_and_constraints_pin_the_measured_stack():
    """依赖清单与既有基座里 `pip freeze` 的实测结果一致。"""
    req = (BASE_DIR / "requirements.txt").read_text(encoding="utf-8")
    assert "pandas==2.3.3" in req and "pyarrow==25.0.1" in req

    con = (BASE_DIR / "constraints.txt").read_text(encoding="utf-8")
    pins = {}
    for ln in con.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        assert "==" in ln, f"constraints 里有没钉死的行：{ln!r}"
        name, ver = ln.split("==", 1)
        pins[name.strip()] = ver.strip()
    assert pins == FROZEN_PINS, (
        f"constraints 与既有基座 gb-base:bookworm-r1 的 pip freeze 对不上：\n"
        f"  清单 {pins}\n  实测 {FROZEN_PINS}"
    )


# ---------------------------------------------------------------------------
# ② harnesses/build.sh：locale 无关、shell 无关、不指发布方路径
# ---------------------------------------------------------------------------
def test_build_sh_has_no_bare_var_before_nonascii():
    """**N-750 的回归锁**。

    `"$BASE_IMAGE。"` 这种写法在 macOS 的 bash 3.2 + UTF-8 locale 下，
    中文标点的头一个字节会被吃进变量名，`set -u` 当场报 unbound variable ——
    于是「你缺基座」这句人话永远打不出来。一律写 `${BASE_IMAGE}` 就没有这件事。
    """
    for path in (BUILD_SH, BASE_DOCKERFILE):
        txt = path.read_text(encoding="utf-8")
        bad = []
        for i, ln in enumerate(txt.splitlines(), 1):
            for m in _BARE_VAR_BEFORE_NONASCII.finditer(ln):
                bad.append(f"{path.name}:{i}: {m.group(0)} 后面紧跟非 ASCII —— 改成 ${{…}}")
        assert not bad, "变量插值后面紧跟非 ASCII 字符，必须带花括号：\n" + "\n".join(bad)


@pytest.mark.parametrize("shell", ["sh", "bash", "zsh"])
def test_build_sh_parses_in_every_target_shell(shell):
    """Linux 的 dash、macOS 的 /bin/sh(bash 3.2) 与 zsh 下都要能解析。"""
    exe = shutil.which(shell)
    if exe is None:
        pytest.skip(f"本机没有 {shell}")
    r = subprocess.run([exe, "-n", str(BUILD_SH)], capture_output=True, text=True)
    assert r.returncode == 0, f"{shell} -n 不过：{r.stderr}"


def _code_lines(path: Path) -> str:
    """去掉整行注释 —— 锁守的是**代码**，不是行文。

    文件头那段兼容性说明里就写着「不用 `sed -i`」，按整个文件搜必然自己把自己判红。
    """
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines()
                      if not ln.lstrip().startswith("#"))


def test_build_sh_avoids_gnu_only_constructs():
    """`sed -i` / `readlink -f` / `mapfile` 在 macOS 上行为不同或根本没有。"""
    code = _code_lines(BUILD_SH)
    for bad in ("sed -i", "readlink -f", "mapfile", "declare -A", "grep -P"):
        assert bad not in code, f"build.sh 用了 GNU/bash 专有的 {bad!r}"


def test_build_sh_points_at_the_repo_not_at_the_publisher():
    """报错文案里不许出现发布方的绝对路径或内网地址。"""
    txt = BUILD_SH.read_text(encoding="utf-8")
    for p in _PUBLISHER_PATHS:
        assert p not in txt, f"build.sh 里还留着发布方的 {p!r} —— 外部用户照它去查，什么也查不到"
    # 报错文案是用户唯一能看到的东西，所以代码行里更要干净。
    code = _code_lines(BUILD_SH)
    for p in _PUBLISHER_PATHS:
        assert p not in code


def test_build_sh_builds_the_base_from_the_repo_when_missing():
    """缺基座时自己从仓库里的 build/base/ 构，而不是让用户去别处找。"""
    txt = BUILD_SH.read_text(encoding="utf-8")
    assert BASE_IMAGE in txt, "build.sh 里没提统一基座 —— 那它就没在核 FROM"
    assert "build/base" in txt, "build.sh 没提基座的构建上下文在 build/base"
    assert 'docker build -t "${BASE_IMAGE}" "${BASE_CONTEXT}"' in txt, \
        "build.sh 没有真的去构基座"
    assert "GB_BASE_CONTEXT" in txt, "没有给「树里没有 build/」的机器留出口"
    assert "--no-base-build" in txt, "没有给「我不想让它自动构」留出口"


def test_base_presence_is_probed_before_anything_expensive():
    """基座在不在，要在 Dockerfile 检查与 tag 解析**之前**判掉并记住。

    它是第一次跑最常见的失败，此前的表现却是一句 `unbound variable`。
    """
    txt = BUILD_SH.read_text(encoding="utf-8")
    probe = txt.index("BASE_PRESENT=1")
    from_check = txt.index('case "${FIRST}" in')
    assert probe < from_check, "基座在不在的判断排在 FROM 检查之后了"


# ---------------------------------------------------------------------------
# ③ 报告在，且 harness 的 FROM 没被改动
# ---------------------------------------------------------------------------
def test_portability_report_exists():
    assert REPORT.is_file(), "缺 ops/reports/base_image_portability.md"
    txt = REPORT.read_text(encoding="utf-8")
    assert "实测" in txt and "查实" in txt, "报告必须分清哪一层是实测、哪一层是查实"


def test_harness_dockerfiles_still_use_the_unified_base():
    """本卡没有动 harness 的基座引用 —— 动了就会让所有已出集 bundle 的通行证对不上。"""
    hdirs = sorted(p for p in (REPO / "harnesses").iterdir() if p.is_dir() and not p.name.startswith("."))
    assert hdirs, "harnesses/ 下一个 harness 都没有？"
    for d in hdirs:
        df = d / "Dockerfile"
        if not df.is_file():
            continue
        first = next(ln.strip() for ln in df.read_text(encoding="utf-8").splitlines()
                     if ln.strip() and not ln.strip().startswith("#"))
        assert first == f"FROM {BASE_IMAGE}", f"{df}: 第一条指令是 {first!r}"
