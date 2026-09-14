"""card 0.1 验收测试:环境与红线自检。

**内部自检 —— 外部用户不要跑这个**(卡 C2,2026-09-13)
------------------------------------------------------
本文件断言的是**发布方这套机器**的样子:`/data` 落点、内部数据湖(`market_lake`)、
发布方那个解释器与发布方的网关地址、以及 `/data` 上留 500 GiB。
拿到发布件的人在自己机器上跑它**必然红一片**,而那些红**不是缺陷** ——
2026-09-13 的 macOS 外部验收实测 **10 failed / 52 passed / 2 skipped**,
失败项逐条是 qlib/httpx(六包说明里没有)、写死的 `/data` 与 `market_lake` 路径、
写死的解释器与网关地址、以及那条 500 GiB 的磁盘断言。

**文件保留,它对内部仍然有用** —— 内部照常 `$PY -m pytest ops/test_env.py`。
变的只是:**README 的外部步骤里不再出现它**。

外部用户该跑的是 **`ops/selfcheck_public.py`**:只查外部环境能自己满足的六件事
(Python ≥ 3.12 / 六个包 / docker 在不在且内存够 / 发布附件落位与 sha256 /
三条冻结根 `--check-all` / 网关起不起得来),一条都不碰 `/data`、不碰数据湖、
不认发布方的解释器与地址。

设计约束
--------
* **完全离线**:不发起任何外网请求。唯一的 socket 操作是对内网地址做一次
  `bind()` 占位探测(不 listen、不 connect),测完立刻 `close()`。
* **只读**:对数据湖只做 `duckdb.connect(..., read_only=True)`,并在前后比对
  catalog 文件的 mtime/size 以证明"一个字节都没动"(红线 2)。
* **不硬编码路径**:除了 `sys.path` 自举那一行,所有路径都来自
  `genebench_config`(见该模块头部说明)。

跑法::

    cd /data/shared/genebench/repo
    /data/shared/genebench/env/bin/python -m pytest ops/test_env.py -v
"""

from __future__ import annotations

import ast
import os
import shutil
import socket
import stat
import sys
import tempfile
from pathlib import Path

import pytest

# --- sys.path 自举:让 ops/ 下的测试能 import 仓库根的 genebench_config -------
# 这是本文件里唯一的路径推导,且是**相对**的(ops/ 的上一级 = 仓库根),
# 不违反"绝对路径只许出现在 genebench_config"的约定。
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import genebench_config as cfg  # noqa: E402

#: `/data` 余量下限(红线 6:大体量产物只落 /data)
MIN_DATA_FREE_BYTES = 500 * 1024**3
#: `$GENEBENCH_ROOT` 必须的目录权限(红线 5:/data/shared 是 1777 公共目录)。
#: 判据来自配置模块,不在这里另写一份字面量。
REQUIRED_ROOT_MODE = cfg.REQUIRED_DIR_MODE

#: 递归权限审计**不下钻**的子树。豁免只是"不递归",子树根本身仍被逐个硬断言
#: `mode & FORBIDDEN_MODE_BITS == 0` —— 根不可穿越,里面是什么权限就都进不去。
#:
#: * ``cfg.ENV`` —— `conda create --clone` 出来的第三方目录树,约 2 万个条目,
#:   由 conda 按它自己的 umask 建,任何一次 `conda install/update` 都会重建;
#:   逐个 chmod 既改不干净又会被下次 conda 操作还原。**里面没有答案产物**
#:   (`reference/`、`scorer/` 都在 `repo/` 下)。
#: * ``cfg.REPO / ".git"`` —— git 自己建 `objects/xx`、`refs/**`,mode 由
#:   git 的 `adjust_shared_perm` + umask 决定,每次 commit/gc/fetch 都可能新建
#:   0775 的目录。**`.git` 里确实有答案代码的历史版本**,所以 `.git/` 这个根的
#:   0700 是硬要求 —— 它就在下面的审计范围内,豁免的只是它的子目录。
MODE_AUDIT_EXEMPT_SUBTREES: tuple[Path, ...] = (
    cfg.ENV,
    cfg.REPO / ".git",
)

#: 答案产物目录(红线 5 直接保护的对象)。这两个要 `== 0o700` 硬断言,
#: 不接受"更严也行"的宽松判据 —— 它们必须刚好是 0700,owner 要能读写执行。
ANSWER_DIRS: tuple[str, ...] = ("reference", "scorer")

_GIB = 1024**3


def _iter_audited_dirs():
    """`$GENEBENCH_ROOT` 下所有该审计的目录:根 + 每一级子目录。

    遇到 `MODE_AUDIT_EXEMPT_SUBTREES` 里的目录**照样 yield(要审)**,
    但不下钻。不跟随符号链接(conda env 里有大量 symlink)。
    """
    root = cfg.GENEBENCH_ROOT
    exempt = {p.resolve() for p in MODE_AUDIT_EXEMPT_SUBTREES}
    yield root
    for dirpath, dirnames, _files in os.walk(root, topdown=True, followlinks=False):
        here = Path(dirpath)
        descend: list[str] = []
        for name in sorted(dirnames):
            child = here / name
            yield child
            if child.resolve() not in exempt:
                descend.append(name)
        dirnames[:] = descend


@pytest.fixture(scope="session")
def report(request):
    """绕过 pytest 的输出捕获,把版本/实测值直接打到终端(`-v` 下可见)。"""
    tr = request.config.pluginmanager.get_plugin("terminalreporter")

    def _write(line: str) -> None:
        if tr is None:  # pragma: no cover - 只在没有终端插件时走到
            print(line)
        else:
            tr.write_line(f"    [env] {line}")

    return _write


@pytest.fixture(autouse=True, scope="session")
def _no_outbound_network():
    """把"离线可跑"从口号变成断言:整场测试期间,任何出网调用直接炸。

    只拦得住 python 层(C 扩展自己发的包拦不住),但足以挡住"某个 import
    顺手去 pypi / 下载 qlib 数据"这类真实事故。放行的只有 `bind()` ——
    它不发包,是本机占位探测。
    """
    real = {
        "connect": socket.socket.connect,
        "connect_ex": socket.socket.connect_ex,
        "getaddrinfo": socket.getaddrinfo,
        "create_connection": socket.create_connection,
    }

    def _is_loopback(target) -> bool:
        """**回环不是出网。**

        先前这个 fixture 把回环也拦了 —— 它是 session 级 autouse，一旦本模块
        先跑，后面所有模块的本地 socket 都会炸。`ops/test_c41.py` 的 SNI 用例
        起的是 `127.0.0.1` 的临时监听，属于被误伤的那一类：全量按字母序
        `test_c41` 在前，所以这个坑一直没露；显式换个顺序就当场 6 条红。

        判据按**地址**，不按调用点 —— 按调用点会变成一张白名单，
        而白名单要靠人记得往里加。
        """
        host = target[0] if isinstance(target, (tuple, list)) and target else target
        if not isinstance(host, str):
            return False
        h = host.strip("[]").lower()
        return h in ("localhost", "::1", "0.0.0.0", "") or h.startswith("127.")

    def _make(name, fn, addr_index):
        def wrapper(*args, **kwargs):
            if len(args) > addr_index and _is_loopback(args[addr_index]):
                return fn(*args, **kwargs)
            raise AssertionError(
                f"card 0.1 验收必须完全离线,却检测到出网调用 "
                f"{name} args={args[1:] or args}"
            )
        return wrapper

    socket.socket.connect = _make("connect", real["connect"], 1)
    socket.socket.connect_ex = _make("connect_ex", real["connect_ex"], 1)
    socket.getaddrinfo = _make("getaddrinfo", real["getaddrinfo"], 0)
    socket.create_connection = _make("create_connection", real["create_connection"], 0)
    try:
        yield
    finally:
        socket.socket.connect = real["connect"]
        socket.socket.connect_ex = real["connect_ex"]
        socket.getaddrinfo = real["getaddrinfo"]
        socket.create_connection = real["create_connection"]


# ===========================================================================
# 1. 数据栈依赖
# ===========================================================================

DATA_STACK = ["duckdb", "pandas", "pyarrow", "qlib"]


@pytest.mark.parametrize("modname", DATA_STACK)
def test_data_stack_importable(modname, report):
    """duckdb / pandas / pyarrow / qlib 可导入,并打印版本。"""
    import importlib

    mod = importlib.import_module(modname)
    version = getattr(mod, "__version__", "<no __version__>")
    report(f"{modname:<10} {version:<20} <- {getattr(mod, '__file__', '?')}")
    assert version != "<no __version__>", f"{modname} 没有 __version__"


# ===========================================================================
# 2. 网关依赖
# ===========================================================================

GATEWAY_STACK = ["fastapi", "uvicorn", "pydantic", "httpx", "pytest"]


@pytest.mark.parametrize("modname", GATEWAY_STACK)
def test_gateway_stack_importable(modname, report):
    """fastapi / uvicorn / pydantic / httpx / pytest 可导入,并打印版本。"""
    import importlib

    mod = importlib.import_module(modname)
    version = getattr(mod, "__version__", "<no __version__>")
    report(f"{modname:<10} {version:<20} <- {getattr(mod, '__file__', '?')}")
    assert version != "<no __version__>", f"{modname} 没有 __version__"


def test_running_interpreter_is_genebench_env(report):
    """跑测试的解释器就是 `cfg.ENV` 里那个(不是 PYTHON_BASE)。

    **隔离环境缺失 = 硬失败,不是 xfail。**
    这里曾经写成 `if not cfg.ENV.exists(): pytest.xfail(...)` —— 那是个逃生门:
    clone 一旦丢了,整套会输出 "N passed, 2 xfailed"、退出码 0,看着仍是绿灯,
    而实际上跑在只读的 `PYTHON_BASE` 上(红线 2)。"clone 没做完"属于施工没做完,
    不是已知豁免,必须红。
    """
    exe = Path(sys.executable).resolve()
    env_dir = cfg.ENV.resolve()
    report(f"python     = {exe}")
    report(f"cfg.PYTHON = {cfg.PYTHON}  (exists={cfg.PYTHON.exists()})")
    assert cfg.ENV.is_dir(), (
        f"隔离环境 {cfg.ENV} 不存在,当前跑在 {exe}。"
        f" 重建:conda create --clone qlib_env -p {cfg.ENV}"
    )
    assert cfg.PYTHON.exists(), f"cfg.PYTHON 指向的解释器不存在:{cfg.PYTHON}"
    assert cfg.PYTHON.resolve() == exe, (
        f"当前解释器 {exe} != cfg.PYTHON {cfg.PYTHON.resolve()};"
        f" 调用方必须统一走 cfg.PYTHON"
    )
    assert env_dir in exe.parents, (
        f"解释器 {exe} 不在隔离环境 {env_dir} 内。"
        f"禁止把包装进 PYTHON_BASE({cfg.PYTHON_BASE})。"
    )
    assert exe != cfg.PYTHON_BASE.resolve(), (
        "跑在只读的 PYTHON_BASE 上,隔离环境没生效(红线 2)"
    )


# ===========================================================================
# 3. 磁盘
# ===========================================================================


def test_data_partition_has_headroom(report):
    """`/data` 余量 > 500G。"""
    target = Path("/data")
    usage = shutil.disk_usage(target)
    report(
        f"{target}: total={usage.total / _GIB:.0f}G "
        f"used={usage.used / _GIB:.0f}G free={usage.free / _GIB:.0f}G"
    )
    assert usage.free > MIN_DATA_FREE_BYTES, (
        f"{target} 只剩 {usage.free / _GIB:.1f}G,低于下限 "
        f"{MIN_DATA_FREE_BYTES / _GIB:.0f}G"
    )


def test_genebench_root_lives_on_data(report):
    """`$GENEBENCH_ROOT` 落在 /data,不落 /home(红线 6)。"""
    root_dev = os.stat(cfg.GENEBENCH_ROOT).st_dev
    data_dev = os.stat("/data").st_dev
    home_dev = os.stat(Path.home()).st_dev
    report(
        f"st_dev: root={root_dev} /data={data_dev} home={home_dev}"
    )
    assert root_dev == data_dev, f"{cfg.GENEBENCH_ROOT} 不在 /data 分区上"
    assert root_dev != home_dev, f"{cfg.GENEBENCH_ROOT} 落在 /home 分区上(红线 6)"


# ===========================================================================
# 4. 网关端口 18080 空闲
# ===========================================================================


#: 这条测试用的**测试端口**。18080 留给生产网关（裁定 2026-09-04：网关按 M6 形态常驻）。
#:
#: 原先它绑 `cfg.GATEWAY_PORT` —— 网关一旦真起来，这条测试就永远红，
#: 而一条恒红的测试下一个人会把它注释掉。测的是「本机能不能在这个地址上绑端口」
#: （网络栈 + 红线 4 的通配绑定守门），换个端口一样测得到。
GATEWAY_TEST_PORT: int = 18099


def test_gateway_port_is_free(report):
    """网关端口在 `GATEWAY_HOST` 上空闲。bind 占位后**立刻**释放。

    刻意**不**设 `SO_REUSEADDR`:那会让 bind 在别人已 LISTEN 时也可能成功,
    等于把探测变成一句谎话。
    """
    host = cfg.assert_no_wildcard_bind(cfg.GATEWAY_HOST)
    port = GATEWAY_TEST_PORT
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        bound = sock.getsockname()
    except OSError as exc:
        pytest.fail(f"绑不上 {host}:{port} -> [{exc.errno}] {exc.strerror}")
    finally:
        sock.close()  # 测完立刻释放,不 listen、不留 TIME_WAIT 之外的痕迹
    report(f"bind ok  {bound[0]}:{bound[1]} (已释放)")
    assert bound == (host, port)

    # 释放确认:同一地址能再绑一次。
    again = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        again.bind((host, port))
    finally:
        again.close()


# ===========================================================================
# 5. GENEBENCH_ROOT:存在 / 可写 / 0700
# ===========================================================================


def test_genebench_root_exists_and_is_dir(report):
    report(f"GENEBENCH_ROOT = {cfg.GENEBENCH_ROOT}")
    assert cfg.GENEBENCH_ROOT.is_dir(), f"{cfg.GENEBENCH_ROOT} 不存在或不是目录"


def test_genebench_root_mode_is_0700(report):
    """根目录 mode 必须是 0700 —— `/data/shared` 是 1777 公共目录。

    这**只**是最外面那一道门。答案产物的权限由下面三条测试分别看住:
    `test_every_dir_under_root_blocks_group_and_world`(递归)、
    `test_answer_dirs_are_exactly_0700`、
    `test_answer_artifacts_are_not_group_world_readable`。
    """
    mode = stat.S_IMODE(os.stat(cfg.GENEBENCH_ROOT).st_mode)
    report(f"mode = {oct(mode)} (要求 {oct(REQUIRED_ROOT_MODE)})")
    assert mode == REQUIRED_ROOT_MODE, (
        f"{cfg.GENEBENCH_ROOT} mode={oct(mode)},要求 {oct(REQUIRED_ROOT_MODE)};"
        f" 修:chmod 700 {cfg.GENEBENCH_ROOT}"
    )


def test_every_dir_under_root_blocks_group_and_world(report):
    """递归审计:`$GENEBENCH_ROOT` 下**每一个**目录都不许对组/其它开放。

    为什么必须递归:本机 umask 是 **002**,`conda create`、`mkdir -p`、pytest
    的缓存目录一律落成 0775。只 stat 根目录的话,下一张卡在 `reference/` 或
    `scorer/` 里新建一个子目录,就会静默产出组/世界可读的**答案产物**,
    而测试全绿 —— 那正是这条测试要堵的洞。

    判据是 `mode & FORBIDDEN_MODE_BITS == 0`(比 0700 更严也算合规)。
    豁免子树见 `MODE_AUDIT_EXEMPT_SUBTREES`:只豁免"不下钻",子树根本身照审。
    """
    offenders: list[str] = []
    audited = 0
    for path in _iter_audited_dirs():
        audited += 1
        mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode & cfg.FORBIDDEN_MODE_BITS:
            offenders.append(f"{oct(mode)}  {path}")
    exempt_names = ", ".join(str(p) for p in MODE_AUDIT_EXEMPT_SUBTREES)
    report(
        f"目录权限审计:{audited} 个目录 <- {cfg.GENEBENCH_ROOT} "
        f"(不下钻:{exempt_names})"
    )
    assert not offenders, (
        f"{len(offenders)} 个目录对组/其它开放(红线 5);"
        f" 建目录请用 cfg.create_dir(),别裸 mkdir。\n"
        + "\n".join(offenders)
        + f"\n修:chmod -R go-rwx {cfg.REPO}"
    )


@pytest.mark.parametrize("name", ANSWER_DIRS)
def test_answer_dirs_are_exactly_0700(name, report):
    """`reference/` 与 `scorer/` 单独硬断言 `mode == 0700`(红线 5 的直接对象)。

    这两个目录装的是"答案"。上一条递归审计已经覆盖它们,这里再钉一条精确判据,
    是为了让失败信息直接指向红线 5,而不是淹没在一串路径里。
    """
    path = cfg.REPO / name
    assert path.is_dir(), f"{path} 不存在"
    mode = stat.S_IMODE(os.stat(path).st_mode)
    report(f"{name:<10} {path}  mode={oct(mode)}")
    assert mode == cfg.REQUIRED_DIR_MODE, (
        f"{path} mode={oct(mode)},要求 {oct(cfg.REQUIRED_DIR_MODE)}"
        f"(红线 5:答案产物不对执行面/旁人暴露);修:chmod 700 {path}"
    )


@pytest.mark.parametrize("name", ANSWER_DIRS)
def test_answer_artifacts_are_not_group_world_readable(name, report):
    """`reference/` 与 `scorer/` 里的**文件**也不许组/世界可读。

    目录 0700 已经挡住路径穿越,但一旦 T-01 搬家、或者有人把答案文件复制到
    别处,文件自身的权限位就是最后一道门。顺手也把 `__pycache__` 里的
    `.pyc`(答案代码的字节码)一起覆盖到 —— 那也是答案。
    """
    root = cfg.REPO / name
    offenders: list[str] = []
    checked = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        checked += 1
        mode = stat.S_IMODE(os.stat(path).st_mode)
        if mode & cfg.FORBIDDEN_MODE_BITS:
            offenders.append(f"{oct(mode)}  {path}")
    report(f"{name:<10} 文件权限审计:{checked} 个文件")
    assert not offenders, (
        f"{len(offenders)} 个答案文件对组/其它开放(红线 5);"
        f" 进程入口请调 cfg.harden_umask()。\n" + "\n".join(offenders)
    )


def test_genebench_root_is_writable(report):
    """真写一个临时文件再删掉 —— `os.access(W_OK)` 在 ACL 下会说谎。"""
    with tempfile.NamedTemporaryFile(
        dir=cfg.GENEBENCH_ROOT, prefix=".gb_write_probe_", suffix=".tmp"
    ) as fh:
        fh.write(b"genebench card 0.1 write probe\n")
        fh.flush()
        probe = Path(fh.name)
        assert probe.exists()
        report(f"write probe ok -> {probe.name}")
    assert not probe.exists(), "临时探针没清理掉"


@pytest.mark.parametrize(
    "attr", ["REPO", "ENV", "LOGS", "SNAPSHOTS", "RESULTS", "WHEELS", "OPS"]
)
def test_subdirs_exist(attr, report):
    """骨架目录齐活。

    ENV 曾经有一条 `pytest.xfail("conda clone 未完成")` 的逃生门,已删:
    隔离环境缺失是硬失败,理由见 `test_running_interpreter_is_genebench_env`。
    LOGS 是补进来的 —— `$GENEBENCH_ROOT/logs` 早就存在并写了 `conda_clone.log`,
    却没有对应的配置常量,属于"路径逃出单一配置常量约束",T-01 搬家时会掉队。
    """
    path = getattr(cfg, attr)
    report(f"{attr:<10} {path}  exists={path.exists()}")
    assert path.is_dir(), f"cfg.{attr} = {path} 不存在"


# ===========================================================================
# 6. 配置模块 + 红线 4(禁止通配绑定)
# ===========================================================================


def test_config_importable_and_paths_derive_from_root(report):
    report(f"genebench_config <- {cfg.__file__}")
    assert cfg.REPO == cfg.GENEBENCH_ROOT / "repo"
    assert cfg.ENV == cfg.GENEBENCH_ROOT / "env"
    assert cfg.LOGS == cfg.GENEBENCH_ROOT / "logs"
    assert cfg.SNAPSHOTS == cfg.GENEBENCH_ROOT / "snapshots"
    assert cfg.RESULTS == cfg.GENEBENCH_ROOT / "results"
    assert cfg.WHEELS == cfg.GENEBENCH_ROOT / "wheels"
    assert cfg.OPS == cfg.REPO / "ops"
    assert cfg.PYTHON == cfg.ENV / "bin" / "python"
    assert cfg.FREEZE_DATE == "2026-07-31", "数据冻结线被改动(红线 7)"
    assert cfg.GATEWAY_PORT == 18080
    assert cfg.GATEWAY_HOST == "192.168.1.48"
    assert cfg.REQUIRED_DIR_MODE == 0o700, "目录权限判据被放宽(红线 5)"
    assert cfg.FORBIDDEN_MODE_BITS == 0o077
    assert cfg.REQUIRED_UMASK == 0o077
    # 所有路径常量都必须派生自 GENEBENCH_ROOT 或显式的外部只读路径。
    # T-01 搬家只改 `_DEFAULT_ROOT` 一行,靠的就是这条。
    derived = ["REPO", "ENV", "LOGS", "SNAPSHOTS", "RESULTS", "WHEELS", "PIP_CONF"]
    for attr in derived:
        path = getattr(cfg, attr)
        assert cfg.GENEBENCH_ROOT in path.parents, (
            f"cfg.{attr} = {path} 不在 GENEBENCH_ROOT 下,T-01 搬家时会掉队"
        )


# ===========================================================================
# 6b. 建目录的唯一正确姿势(红线 5 的施工侧防线)
# ===========================================================================


def test_harden_umask_sets_required_umask():
    """`harden_umask()` 把 umask 收到 0077,并如实返回旧值;调用后能还原。"""
    previous = cfg.harden_umask()
    try:
        current = os.umask(0o077)  # 读一下当前值(顺带写回同值)
        assert current == cfg.REQUIRED_UMASK, (
            f"harden_umask() 之后 umask={oct(current)},不是 {oct(cfg.REQUIRED_UMASK)}"
        )
    finally:
        os.umask(previous)
        cfg.harden_umask()  # 会话其余部分继续用收紧后的 umask


def test_create_dir_is_0700_at_every_level_even_under_loose_umask(report):
    """`create_dir()` 在 **umask 002** 下也要让**每一级**都是 0700。

    这条是本机真实事故的回归测试:`os.makedirs(p, mode=0o700)` 在 Python 3.7+
    只把 mode 用在最后一级,**中间层拿的是 0o777 & ~umask** —— umask 002 下
    就是 0775。裸 mkdir 建出来的 `env/`、`logs/`、`ops/acceptance/` 全是 0775,
    就是这么来的。
    """
    previous = os.umask(0o002)  # 刻意还原成本机默认的宽松 umask
    try:
        with tempfile.TemporaryDirectory(
            dir=cfg.GENEBENCH_ROOT, prefix=".gb_mkdir_probe_"
        ) as tmp:
            deep = Path(tmp) / "a" / "b" / "c"
            returned = cfg.create_dir(deep)
            assert returned == deep and deep.is_dir()
            for level in (Path(tmp) / "a", Path(tmp) / "a" / "b", deep):
                mode = stat.S_IMODE(os.stat(level).st_mode)
                assert mode == cfg.REQUIRED_DIR_MODE, (
                    f"{level} mode={oct(mode)}(umask=002 下中间层没被 chmod 回来)"
                )
            report(f"create_dir 三级全 0700(umask=002 下)-> {deep}")
            # 幂等:已存在也不报错,且把歪掉的权限收敛回来
            os.chmod(deep, 0o775)
            cfg.create_dir(deep)
            assert stat.S_IMODE(os.stat(deep).st_mode) == cfg.REQUIRED_DIR_MODE
    finally:
        os.umask(previous)


def test_create_dir_rejects_group_or_world_readable_mode():
    """`create_dir(..., mode=0o755)` 必须当场拒绝 —— 别给红线 5 留后门。"""
    with pytest.raises(ValueError, match="红线 5"):
        cfg.create_dir(cfg.GENEBENCH_ROOT / ".gb_never_created", mode=0o755)
    assert not (cfg.GENEBENCH_ROOT / ".gb_never_created").exists()


def test_wildcard_bind_0_0_0_0_raises():
    """卡 0.1 点名的那一条:`assert_no_wildcard_bind('0.0.0.0')` 必须抛。"""
    with pytest.raises(ValueError, match="红线 4"):
        cfg.assert_no_wildcard_bind("0.0.0.0")


@pytest.mark.parametrize(
    "bad", ["0.0.0.0", "", "::", "*", "[::]", "  0.0.0.0  ", "::0", "0", None]
)
def test_wildcard_bind_variants_all_raise(bad):
    """通配地址的各种写法(含空串、IPv6、带空格、非字符串)都要拦住。"""
    with pytest.raises(ValueError):
        cfg.assert_no_wildcard_bind(bad)


@pytest.mark.parametrize("good", ["192.168.1.48", "127.0.0.1", "localhost"])
def test_non_wildcard_bind_passes(good):
    assert cfg.assert_no_wildcard_bind(good) == good.strip()


# ===========================================================================
# 7. 红线自检:数据湖 catalog 只读
# ===========================================================================


#: 只读打开 catalog 的重试次数。数据湖是**活的**:用户自己的爬虫/ETL 会周期性
#: 以读写方式打开 catalog 刷新 view 并 checkpoint,期间会短暂留下 `.wal`。
#: DuckDB 拒绝在存在非空 WAL 时以只读打开,所以这里必须能扛住瞬时冲突。
CATALOG_OPEN_RETRIES = 5
CATALOG_OPEN_BACKOFF_S = 1.0


def _connect_catalog_read_only():
    """只读打开 catalog,扛住外部写入者留下的瞬时 WAL。

    **只**用 ``read_only=True``。刻意不做"尝试读写打开应当失败"这种对称测试:
    那种测试在外部写入者恰好没持锁的窗口里会**真的打开并写**数据湖,
    等于用一次红线违规去证明红线 —— 不干。
    """
    import duckdb

    last = None
    for attempt in range(CATALOG_OPEN_RETRIES):
        try:
            return duckdb.connect(str(cfg.CATALOG), read_only=True)
        except Exception as exc:  # duckdb.IOException / duckdb.Error
            last = exc
            if attempt + 1 < CATALOG_OPEN_RETRIES:
                import time

                time.sleep(CATALOG_OPEN_BACKOFF_S)
    raise AssertionError(
        f"{CATALOG_OPEN_RETRIES} 次都没能以 read_only=True 打开 {cfg.CATALOG}:"
        f" {last!r}(外部 ETL 可能正持有非空 WAL)"
    )


def test_catalog_opens_read_only(report):
    """红线自检:`CATALOG` 能以 `read_only=True` 打开,且那条连接**写不动**。

    证据链是"连接本身是只读的",而不是"文件 mtime 没变" —— 后者不成立:
    数据湖在被用户自己的 ETL 持续写(见本卡 findings),拿 mtime 变化去指控
    我们,既会误报也会让测试变成掷骰子。
    """
    import duckdb

    catalog = cfg.CATALOG
    assert catalog.is_file(), f"catalog 不存在:{catalog}"

    before = catalog.stat()
    con = _connect_catalog_read_only()
    try:
        access_mode = con.execute(
            "SELECT current_setting('access_mode')"
        ).fetchone()[0]
        n_views = con.execute(
            "SELECT count(*) FROM duckdb_views() WHERE NOT internal"
        ).fetchone()[0]
        assert con.execute("SELECT 1").fetchone()[0] == 1

        # 这条连接必须是只读的 —— 引擎自己说了算,不靠我们自觉。
        assert str(access_mode).upper() == "READ_ONLY", (
            f"access_mode={access_mode!r},不是 READ_ONLY(红线 2)"
        )

        # 再从行为上验一遍:任何写语句都必须被引擎顶回来。
        for stmt in (
            "CREATE TABLE gb_redline_probe(i INTEGER)",
            "CREATE OR REPLACE VIEW gb_redline_probe_v AS SELECT 1",
        ):
            with pytest.raises(duckdb.Error):
                con.execute(stmt)
    finally:
        con.close()

    after = catalog.stat()
    report(
        f"catalog  {catalog}  access_mode={access_mode}  views={n_views}"
    )
    report(
        f"catalog  size={after.st_size} "
        f"mtime_moved_during_test={after.st_mtime_ns != before.st_mtime_ns}"
        f"  (外部 ETL 在写,非本测试所为)"
    )
    assert n_views > 0, "catalog 里一个 view 都没有,路径可能指错了"


#: 运行时拼出来的探针,免得本文件自己的扫描代码/文档被当成违规样本。
_CONNECT_NEEDLE = "duckdb" + ".connect("
_READ_ONLY_FLAG = "read_only" + "=True"

#: 内存库豁免。``duckdb.connect(":memory:")`` 根本没有文件可开，
#: 对它传 ``read_only=True`` 反而会报错（空的只读内存库无意义）。
#: 它碰不到湖的任何字节，不属于本条红线要管的范围 ——
#: “内存库里 read_parquet 直读 gold” 是另一条规则的事，由
#: ``test_lake_baseline.py::test_lake_is_the_only_module_that_connects_to_the_lake`` 管。
_IN_MEMORY_NEEDLE = ":memory:"


def test_every_duckdb_connect_in_repo_is_read_only(report):
    """红线 2 的静态防线:仓库里**每一处**打开 duckdb 的调用都必须带只读标志。

    离线、纯文本扫描,给后续卡当护栏 —— 免得哪天有人顺手写了个可写连接
    把湖搞坏(前车之鉴:一次 root 容器写入悄悄弄坏了 19 个爬虫)。
    """
    offenders: list[str] = []
    scanned = 0
    for py in sorted(_REPO_ROOT.rglob("*.py")):
        if any(part in {"__pycache__", "env", ".git"} for part in py.parts):
            continue
        scanned += 1
        lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
        for idx, line in enumerate(lines):
            if _CONNECT_NEEDLE not in line:
                continue
            window = " ".join(lines[idx : idx + 4])
            if _IN_MEMORY_NEEDLE in window:
                continue
            if _READ_ONLY_FLAG not in window:
                offenders.append(
                    f"{py.relative_to(_REPO_ROOT)}:{idx + 1}: {line.strip()}"
                )
    report(f"扫了 {scanned} 个 .py,可写 duckdb 连接 {len(offenders)} 处")
    assert not offenders, (
        f"以下调用没带 {_READ_ONLY_FLAG}:\n" + "\n".join(offenders)
    )


def test_gold_and_qlib_release_are_readable(report):
    """gold 层与 qlib 发布目录可读(只 listdir,不全表扫 —— 全扫会
    'Too many open files')。"""
    assert cfg.GOLD.is_dir(), f"gold 不存在:{cfg.GOLD}"
    assert cfg.QLIB_RELEASE.is_dir(), f"qlib release 不存在:{cfg.QLIB_RELEASE}"
    n_datasets = sum(1 for p in cfg.GOLD.iterdir() if p.is_dir())
    report(f"gold datasets = {n_datasets}  <- {cfg.GOLD}")
    report(f"qlib release  <- {cfg.QLIB_RELEASE}")
    assert n_datasets > 0


# ===========================================================================
# ssh 方向（D-16，2026-09-04）
# ===========================================================================


def test_f02_holds_no_ssh_private_key():
    """**反向 ssh 必须持续不存在**：f02 上不得有任何 ssh 私钥。

    f01（数据面，持有 gold / scorer / reference）→ f02（执行面，跑不可信 agent）
    是唯一允许的方向。f02 若能 ssh 回 f01，隔离就没有意义 ——
    容器逃逸之后的下一跳直接就是答案面。

    这条从 f01 发起检查（f01 有到 f02 的通道；反过来没有，这正是要守的）。
    """
    import subprocess
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
         "ljn@192.168.1.219",
         "ls -1 ~/.ssh/ 2>/dev/null | grep -E '^id_' || true"],
        capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"到 f02 的通道不可用：{r.stderr.strip()[:120]}")
    keys = [x for x in r.stdout.split() if x and not x.endswith(".pub")]
    assert not keys, (
        f"f02 上有 ssh 私钥 {keys} —— 反向通道一旦存在，"
        f"容器逃逸的下一跳就是答案面（D-16）")


# --------------------------------------------------------------- gold 不得外流（裁定 2026-09-04）

#: 「gold 模式」的路径判据。`gold` 是**路径段**，不是子串 ——
#: `goldman/` 这种目录名不该被误伤，而 `x/gold/y` 必须命中。
GOLD_SEGMENTS = frozenset({"gold"})
GOLD_NAMES = ("oracle_artifact.json", "slice.parquet", "n_days_check.json")

#: **只有这两个根**可以放答案面。`scratch/` 是暂存区，它会被 rsync 到执行面 ——
#: 答案面出现在那里等于一次静默的泄漏（2026-09-04 实测：
#: `scratch/f02_bundle/reference/tasks/v1.0-smoke/s1-cor-01/gold` 确实存在过，
#: 万幸是空的、且 f02 上没有对应物）。
GOLD_ALLOWED_ROOTS = ("reference", "snapshots")


def _gold_offenders(root: Path) -> list[str]:
    root = Path(root)
    bad = []
    for p in root.rglob("*"):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        parts = rel.parts
        looks_gold = (set(parts) & GOLD_SEGMENTS) or p.name in GOLD_NAMES
        if not looks_gold:
            continue
        if parts and parts[0] in GOLD_ALLOWED_ROOTS:
            continue
        bad.append(str(rel))
    return sorted(bad)


def test_gold_only_lives_under_reference_or_snapshots():
    """答案面只能在 `reference/` 与 `snapshots/` 下。

    暂存区尤其危险：`scratch/f02_bundle/` 是**要 rsync 到执行面的那份**，
    答案面落进去就跟着上了执行面，而且没有任何东西会报错。
    """
    assert _gold_offenders(cfg.GENEBENCH_ROOT) == [], (
        "答案面出现在允许的两个根之外 —— 暂存区里的一份会跟着 rsync 上执行面")


def test_gold_scanner_is_discriminating(tmp_path):
    """判别力：造一个坏输入喂它，必须命中。

    没有这条，上面那条在「gold 还没生成」的今天是**恒绿**的 ——
    而恒绿的门与恒红的门一样会被绕过（F7 的镜像面）。
    """
    (tmp_path / "scratch" / "f02_bundle" / "reference" / "tasks" / "t1" / "gold").mkdir(parents=True)
    (tmp_path / "scratch" / "f02_bundle" / "reference" / "tasks" / "t1" / "gold"
     / "slice.parquet").write_bytes(b"x")
    hits = _gold_offenders(tmp_path)
    assert any("gold" in h for h in hits), hits
    (tmp_path / "reference" / "tasks" / "t2" / "gold").mkdir(parents=True)
    (tmp_path / "reference" / "tasks" / "t2" / "gold" / "slice.parquet").write_bytes(b"x")
    assert not any(h.startswith("reference/") for h in _gold_offenders(tmp_path)), \
        "reference/ 下的答案面被误伤了"
    (tmp_path / "goldman_sachs_notes.md").write_text("x", encoding="utf-8")
    assert "goldman_sachs_notes.md" not in _gold_offenders(tmp_path), \
        "判据是路径**段**不是子串 —— goldman 不该命中"


# --------------------------------------------------------------- 凭据不进仓库（裁定 2026-09-04）

#: 密钥的**形状**。判据是「像密钥的字面量」，不是「变量名叫 key」——
#: 后者会把 `api_key_env = "DEEPSEEK_API_KEY"`（只有名字、没有值）也判红，
#: 而那正是我们要求的写法。
_KEY_SHAPES = (
    (r"sk-[A-Za-z0-9_\-]{20,}", "OpenAI / DeepSeek 形态"),
    (r"sk-ant-[A-Za-z0-9_\-]{20,}", "Anthropic 形态"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*[\"\']"
     r"[A-Za-z0-9_\-]{24,}[\"\']", "赋了一个长字面量的凭据变量"),
)

_KEY_SCAN_SUFFIXES = (".py", ".yaml", ".yml", ".json", ".toml", ".md", ".sh",
                      ".txt", ".cfg", ".ini", ".env")


def _public_strings() -> set[str]:
    """**具名例外**：设计上就是公开的那几串。

    只有一条：边车的占位 key。它从 `egress_proxy.PLACEHOLDER_KEY` **取**而不是
    在这里再抄一遍 —— 抄一遍的话，占位串改了这条例外就会指向一个不存在的值，
    而新的占位串会被判成泄漏（例外与被例外的东西必须同源）。

    例外的理由可被证伪：`ops/test_c41.py::test_placeholder_key_never_reaches_upstream`
    断言它**永不到达上游**（转发时被替换）。它公开是因为它没有任何权限。
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner" / "c41"))
    from egress_proxy import PLACEHOLDER_KEY      # noqa: E402
    return {PLACEHOLDER_KEY}


def _key_offenders(root: Path, *, skip: tuple[str, ...] = ()) -> list[str]:
    import re
    public = _public_strings()
    bad = []
    for p in Path(root).rglob("*"):
        if not p.is_file() or p.suffix not in _KEY_SCAN_SUFFIXES:
            continue
        rel = str(p.relative_to(root))
        if any(rel.startswith(x) for x in skip):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat, why in _KEY_SHAPES:
            for m in re.finditer(pat, text):
                if any(pub in m.group(0) for pub in public):
                    continue
                bad.append(f"{rel}:{text[:m.start()].count(chr(10)) + 1} {why}")
    return sorted(set(bad))


def test_no_api_key_material_in_the_repo():
    """**凭据不进仓库、不进对话**（裁定 2026-09-04）。由用户以环境变量落到 f02 的
    runner 配置；仓库里只允许出现**变量名**（`registry.Config.api_key_env`）。"""
    repo = Path(__file__).resolve().parents[1]
    # 本文件自己含有那几条正则，跳过它 —— 不跳的话这条测试永远红，
    # 而「永远红的门与永远绿的门一样会被绕过」。
    bad = _key_offenders(repo, skip=("ops/test_env.py", ".git/"))
    assert bad == [], f"仓库里出现了像密钥的字面量：{bad}"


def test_no_api_key_material_in_run_dirs():
    """run dir 会被 rsync、会被归档、会进结果库 —— 密钥落进去就跟着走。"""
    for root in (cfg.GENEBENCH_ROOT / "scratch",):
        if root.exists():
            assert _key_offenders(root) == [], root


def test_public_placeholder_is_exempt_but_nothing_else_is(tmp_path):
    """具名例外必须**窄**：占位串放行，形状相同的别的串照样抓。"""
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner" / "c41"))
    from egress_proxy import PLACEHOLDER_KEY
    (tmp_path / "ok.py").write_text(f'K = "{PLACEHOLDER_KEY}"\n', encoding="utf-8")
    assert _key_offenders(tmp_path) == [], "占位串被误判成泄漏"
    # 造一个**真的长串**（在运行时拼，别让本文件自己命中扫描器）。
    # 先前这里写的是 `\'K = "sk-" + "z" * 40\'` —— 那是**源码里的拼接表达式**，
    # 字面量只有 `sk-` 三个字符，扫描器当然不该命中。测试的坏输入造错了，
    # 而它「没红」看起来像例外开太宽。
    long_key = "sk" + "-" + "z" * 40
    (tmp_path / "bad.py").write_text(f'K = "{long_key}"\n', encoding="utf-8")
    assert _key_offenders(tmp_path), "例外开太宽 —— 别的 sk- 串也放行了"


def test_key_scanner_is_discriminating(tmp_path):
    """判别力：今天仓库里一把密钥都没有，不喂坏输入的话这条是**恒绿**的。"""
    (tmp_path / "leak.py").write_text(
        'API_KEY = "sk-abcdefghijklmnopqrstuvwxyz012345"\n', encoding="utf-8")
    assert _key_offenders(tmp_path), "像 OpenAI/DeepSeek 密钥的字面量没被抓到"
    (tmp_path / "leak.py").write_text(
        'api_key_env = "DEEPSEEK_API_KEY"\n', encoding="utf-8")
    assert _key_offenders(tmp_path) == [], \
        "只有**变量名**没有值 —— 那正是我们要求的写法，不该被误伤"
    (tmp_path / "leak.py").write_text(
        'token = "aWxsZWdhbGx5bG9uZ2Jhc2U2NHRva2VuMTIzNDU2"\n', encoding="utf-8")
    assert _key_offenders(tmp_path), "赋了长字面量的 token 没被抓到"


# ---------------------------------------------------------------- 红线 5 的**源码侧**判据

#: 会**产出或搬运答案素材**的数据面模块树。裸 mkdir 在这里等于 0775 的答案面目录。
_ANSWER_PLANE_TREES: tuple[str, ...] = ("genetask", "reference", "scorer", "snapshots")

#: 不下钻的子树，每条都写清**为什么**（理由要能被别的测试证伪）。
_BARE_MKDIR_EXEMPT: dict[str, str] = {
    "genetask/templates": "模板里的 solve.py 在**容器内**以被测 agent 身份跑，"
                          "拿不到 genebench_config，也不该拿到（零引用面）",
    "genetask/file_contract.py": "write_contracted 的**唯一**函数体，两个面共用；"
                                 "import 数据面配置会破坏它的零引用性质",
}


def test_no_bare_mkdir_in_answer_plane_modules():
    """答案面模块不许裸 `mkdir` / `os.makedirs` —— 一律走 `cfg.create_dir`。

    为什么补这条(2026-09-04, N-61)：全树目录审计只看**磁盘上现在有什么**，
    一条「跑起来会造 0775 目录」的代码路径在没人跑它之前是隐形的。
    那晚 `packager.write_task` / `export_task` / `protocol_rules.write_rules`
    三处同时中招，`_ledger.jsonl`（含 gold 素材）落成 **0664**。

    用 AST 判，不查散文 —— 否则本条注释里的 `mkdir` 字样会让门命中自己(D-25)。

    **边界**：执行面的 run dir 权限(`runner/inject.py`)不在此判据内 ——
    那是另一台机上的另一个问题，登记待办而不是顺手扩进来。
    """
    root = Path(cfg.GENEBENCH_ROOT) / "repo" if (Path(cfg.GENEBENCH_ROOT) / "repo").is_dir() \
        else Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    scanned = 0
    for tree in _ANSWER_PLANE_TREES:
        base = root / tree
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.py")):
            rel = str(f.relative_to(root))
            if any(rel == k or rel.startswith(k + "/") for k in _BARE_MKDIR_EXEMPT):
                continue
            scanned += 1
            tree_ast = ast.parse(f.read_text(encoding="utf-8"), filename=rel)
            for node in ast.walk(tree_ast):
                if not isinstance(node, ast.Call):
                    continue
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else \
                    (fn.id if isinstance(fn, ast.Name) else "")
                if name in ("mkdir", "makedirs"):
                    offenders.append(f"{rel}:{node.lineno} {name}(...)")
    assert scanned >= 10, f"只扫到 {scanned} 个文件 —— 判据可能扫空了(恒绿)"
    assert not offenders, (
        f"{len(offenders)} 处裸建目录(红线 5 的源码侧)；改用 cfg.create_dir()：\n  "
        + "\n  ".join(offenders))


def test_bare_mkdir_lint_can_actually_fail(tmp_path):
    """上一条的判别力：喂一段真的裸 mkdir 的源码，AST 判据必须认出来。

    不改仓库文件、不动被测函数的参数 —— 只证明「认得出来」这件事本身不是恒绿。
    """
    src = "from pathlib import Path\nPath('x').mkdir(parents=True)\nimport os\nos.makedirs('y')\n"
    hits = [n.func.attr for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("mkdir", "makedirs")]
    assert sorted(hits) == ["makedirs", "mkdir"]


def test_bare_mkdir_exemptions_still_exist():
    """豁免不能变成僵尸：被豁免的路径必须真的还在(D-23 —— 理由要可证伪)。"""
    root = Path(__file__).resolve().parents[1]
    for k in _BARE_MKDIR_EXEMPT:
        assert (root / k).exists(), f"豁免项 {k} 已不存在 —— 删掉它，别留着当摆设"


# --------------------------------------------------------------- 数据许可状态锁（N-66，2026-09-05）

#: `DATA_LICENSE` 的两种状态。`pending_license_text` = 许可已取得但**原文未入库**。
LICENSE_STATES = ("pending_license_text", "granted")
#: 许可原文的落点。状态翻 `granted` 之前它必须为空/不存在。
LICENSE_TEXT_DIR = Path(__file__).resolve().parents[1] / "ops" / "terms" / "baostock" / "permission"


def _license_state() -> str:
    f = Path(__file__).resolve().parents[1] / "DATA_LICENSE"
    assert f.is_file(), "仓库根缺 DATA_LICENSE"
    txt = f.read_text(encoding="utf-8")
    hits = [s for s in LICENSE_STATES if f"`{s}`" in txt or f"**状态：`{s}`**" in txt]
    assert hits, f"DATA_LICENSE 里读不出状态（应为 {LICENSE_STATES} 之一）"
    return hits[0]


def test_license_state_is_declared_and_known():
    assert _license_state() in LICENSE_STATES


def test_no_published_provider_package_while_license_text_is_pending():
    """**「口头已取得」与「有原文可查」是两回事** —— 后来的人只能读到后者。

    状态是 `pending_license_text` 时，不许存在任何已打包待发的 provider ——
    发布形态可以准备，发布本身要等原文。
    """
    if _license_state() != "pending_license_text":
        pytest.skip("许可原文已入库，本锁不适用")
    pub = Path(cfg.GENEBENCH_ROOT) / "snapshots" / "public"
    published = []
    if pub.is_dir():
        published = [str(p.relative_to(pub)) for p in pub.rglob("*")
                     if p.is_file() and p.suffix in (".tar", ".gz", ".tgz", ".zip")]
    assert not published, (
        f"许可原文还没入库，却已经有打好的包：{published[:5]}。"
        f"发布形态可以准备，发布本身要等原文")


def test_license_state_matches_whether_the_text_exists():
    """状态与事实必须一致 —— 两边各说各话时，读文件的人会信错的那个。"""
    state = _license_state()
    has_text = LICENSE_TEXT_DIR.is_dir() and any(LICENSE_TEXT_DIR.iterdir())
    if state == "granted":
        # 2026-09-11 用户裁定 ⑨ 把「授权」与「原文」拆开：授权已取得 → 状态 `granted`；
        # 许可方出具的**正文仍未到手** → DATA_LICENSE 里留一处**显式占位**，
        # `ops/terms/baostock/permission/` 保持为空。于是「granted ⇒ 目录里有原文」不再成立。
        # 要拦的事没变：**不许两样都没有** —— 没有原文又没有写明「待替换」的占位，
        # 就是把「有人口头说过」写成了「有文件可查」。
        doc = (_REPO_ROOT / "DATA_LICENSE").read_text(encoding="utf-8") if (_REPO_ROOT / "DATA_LICENSE").is_file() else ""
        placeholder = ("待替换" in doc) and ("占位" in doc)
        assert has_text or placeholder, (
            f"状态写着 granted，而 {LICENSE_TEXT_DIR} 里没有原文、DATA_LICENSE 里也没有"
            f"写明「待替换」的显式占位 —— 两样都没有等于把口头授权写成了有文件可查")
        if not has_text:
            assert "原样替换" in doc or "由仓库所有者" in doc, \
                "占位没写清楚由谁替换 —— 占位不写这一句就会被当成已入库"
    else:
        assert not has_text, (
            f"{LICENSE_TEXT_DIR} 里已经有原文了，状态却还是 {state} —— 去把状态改成 granted")


# ============================================================== 红线 5：答案面根下不许有符号链接（裁定 2026-09-05）
def test_guard_rejects_symlinks_under_answer_plane(tmp_path):
    """**断链的符号链接必须判违例，不是「读不到模式」**。

    2026-09-05：Codex 在 `work/.codex/tmp/arg0/` 留了一批断链 symlink，我 rsync 把 run 目录拉回数据面时
    带了进来。守门 `stat` 不到它们 → 记「读不到模式」→ 网关 `ExecStartPre` 拒绝启动 →
    OOM 后连续 20 次起不来，一次瞬时崩溃变成 10 分钟停摆（N-125）。
    """
    from ops import guard_modes as G
    root = tmp_path / "reference"
    (root / "tasks").mkdir(parents=True)
    (root / "tasks" / "a.json").write_text("{}", encoding="utf-8")
    for p in (root, root / "tasks", root / "tasks" / "a.json"):
        p.chmod(0o700 if p.is_dir() else 0o600)
    (root / "tasks" / "dangling").symlink_to("/nowhere/at/all")
    (root / "tasks" / "live").symlink_to(root / "tasks" / "a.json")
    old_roots, old_plane = G.EXTERNAL_ROOTS, G.ANSWER_PLANE_ROOTS
    try:
        G.EXTERNAL_ROOTS = (str(root),)
        G.ANSWER_PLANE_ROOTS = (str(root),)
        bad = [b for b in G.check(repo=tmp_path / "norepo") if "符号链接" in b]
    finally:
        G.EXTERNAL_ROOTS, G.ANSWER_PLANE_ROOTS = old_roots, old_plane
    assert len(bad) == 2, f"断链与活链都要判，实得 {bad}"
    assert any("断链" in b for b in bad) and any("指向" in b for b in bad)


def test_guard_does_not_reject_symlinks_outside_answer_plane(tmp_path):
    """**范围**：`GENEBENCH_ROOT` 下还挂着 conda 环境（5 000+ 条正常 symlink）——
    一刀切会让守门永远红，而永远红的门会被绕过（与恒绿同族）。"""
    from ops import guard_modes as G
    env = tmp_path / "env" / "bin"
    env.mkdir(parents=True)
    (env / "python3.10").write_text("#!/bin/sh\n", encoding="utf-8")
    (env / "python3.10").chmod(0o700)
    for p in (tmp_path / "env", env):
        p.chmod(0o700)
    (env / "python").symlink_to(env / "python3.10")
    old_roots, old_plane = G.EXTERNAL_ROOTS, G.ANSWER_PLANE_ROOTS
    try:
        G.EXTERNAL_ROOTS = (str(tmp_path),)
        G.ANSWER_PLANE_ROOTS = (str(tmp_path / "reference"),)
        bad = [b for b in G.check(repo=tmp_path / "norepo") if "符号链接" in b]
    finally:
        G.EXTERNAL_ROOTS, G.ANSWER_PLANE_ROOTS = old_roots, old_plane
    assert not bad, f"答案面之外的 symlink 不该判，实得 {bad}"


def test_harden_keeps_owner_execute_bit(tmp_path):
    """收紧权限**不许抹掉属主的执行位** —— 2026-09-05 抹过一次，
    `ops/push_bundle_to_f02.sh`（唯一的推送入口）当场 `Permission denied`。"""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ops import report_io as RIO
    f = tmp_path / "x.sh"
    f.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    f.chmod(0o755)
    RIO.secure_tree(tmp_path)
    assert f.stat().st_mode & 0o777 == 0o700, oct(f.stat().st_mode & 0o777)
