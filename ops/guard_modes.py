#!/usr/bin/env python3
"""红线 5 的**守门**：敏感根的权限模式，在**使用时刻**检查，不只在推送时刻。

为什么要有这个文件（指令一，2026-09-04）：`tar xzf` 保留打包机（macOS）的宽松模式，
本轮**三次**把敏感目录放松成 0755（`reference/artifact_schema.py`、`genetask/templates/`、
`ops/manifests/`），每次都靠事后 `chmod` 补救，而且只 chmod 想到的那几个路径。
事后补救的问题不是麻烦，是**它依赖人记得**：漏掉的那个目录不会有任何提示。

两处用它：
* **推送脚本**：解包 → `harden()` → `check()`，不过即中止，**不进全量**；
* **启动守门**：网关 / scorer / 注入器启动时 `assert_modes()`，不合规**拒绝启动**。
  推送时刻绿不代表使用时刻绿 —— 中间任何人 `chmod` 一下都不会有人知道。

**`check()` 与 `harden()` 对符号链接必须同一个口径**（N-818，2026-09-13）：
两者口径相反的那一版让「照 README 建 venv」变成一道死锁 —— 判的是链接**目标**的位
（系统解释器 0755），修的时候却跳过链接，于是 `--harden` 永远收紧 0 个条目、
网关永远拒绝启动，而提示语还在让人再跑一次 `--harden`。详见 `check()` 里那段注释。
"""
from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# ── `genebench_config` 是**发布方的配置**，执行面那棵树里没有它（N-857，2026-09-14）──
# 这一行原先是**模块级** `import genebench_config as _cfg`，而 `runner/inject.py` 的 P0
# （`check_modes`）正是动态加载本文件 —— 于是**任何新铺的执行面第一次真跑就炸在 P0 上**。
# f02 上双机现在能跑，只因为那棵 exec 树是 2026-09-10 的旧版（与仓库当前版 md5 不同）：
# 下一次 `ops/push_exec_to_f02.sh` 会把**双机生产**一起打断。
#
# **取舍**（两条各有代价，选了 ②）：
# ① 把 `genebench_config.py` 收进 exec 白名单（`runner/placement.OPS_FILES` +
#    `ops/push_exec_to_f02.sh` 的同名数组）—— 代价是把发布方的 807 行数据面地图
#    （湖 / gold / reference / runs_in 的绝对路径、网关绑定地址与端口）送上跑 agent 的那台机器，
#    而且要为「仓库根下的文件」在两处白名单里新造一套机制（现在两处都只认 `ops/` 下的文件）。
# ② 惰性 / 可选 import —— 代价是执行面上 `EXTERNAL_ROOTS` / `ANSWER_PLANE_ROOTS` 落空。
#
# 选 ② 的**判据**：那两张表在执行面上**本来就全是不存在的路径**（`roots()` 按 `exists()` 过滤，
# f02 上根本没有 `/data/shared/genebench`），所以落空**不改变任何一条真实判据**；而
# **主判据（`REPO_IS_THE_ROOT` = 这棵树自己）照旧全量跑**。
# **不是静默跳过**，两道当场证明：
#   * `ops/test_F10.py::test_没有_genebench_config_的树上守门照样咬得动` —— 一棵没有
#     `genebench_config.py` 的树里造 0644 文件 / 0775 目录 / 0775 `__pycache__`，`check()` 全抓到；
#   * `runner/inject.preflight` 另有一条断言：加载到的守门必须把**注入器自己这棵树**
#     列进 `roots()`，否则 P0 直接红（`ops/test_F10.py` 换掉 `_load_guard` 验它）。
try:
    import genebench_config as _cfg      # noqa: E402
except ModuleNotFoundError:              # 执行面：这棵树里没有发布方配置，**这是预期**
    _cfg = None                          # type: ignore[assignment]

#: 本进程有没有拿到发布方配置。`main()` 会把它连同审计根一起打出来 —— 不许无声降级。
CONFIG_AVAILABLE: bool = _cfg is not None

#: **主判据 = 整个仓库根**（与 `ops/test_env.py` 同一个判据）。
#:
#: 第一版写成一张敏感目录白名单，**当场漏了两个**：`runner/f02/`（新建的目录）
#: 与 `scratch/f02_bundle/reference/`（造 bundle 时建的，**里面有 gold**，0775）。
#: 白名单是**开放列举**，注定会烂 —— 这正是我在同一轮的指令六里写过的话
#: （DATA_ROOTS 的主次），却在自己的守门里犯了一遍。
#: 主判据必须是**封闭**的：根下的一切都不得对组/其它开放。
REPO_IS_THE_ROOT = True

#: 仓库根之外还要守的（数据面产物与临时区）。不存在就跳过 —— 它们只在 f01 上有。
#: 这一张仍是开放列举，所以它只是**纵深**，不是判据本身。
EXTERNAL_ROOTS: tuple[str, ...] = ((str(_cfg.GENEBENCH_ROOT),) if _cfg is not None else ())

#: 不进审计的目录名。
#:
#: **`__pycache__` 曾经在这张表里，理由写着「缓存不含产物」—— 那是错的**
#: （2026-09-04 实测）：`reference/__pycache__/*.pyc` 就是**答案面代码的编译副本**，
#: 而 `ops/test_env.py::test_answer_artifacts_are_not_group_world_readable` 正是审计它。
#: 于是出现了一个尴尬的状态：红线测试报红，`harden()` 却返回 0 —— 守门自称封闭判据，
#: 而漏掉的恰好是被审计的那一类。`conftest.py` 的注释里早就写着
#: 「0775 的 `__pycache__` 里躺着 `scorer/` 的字节码」，只是没人把它接到这张表上。
#: **`.git` 也摘掉了**（D-23 逐条核，2026-09-04）：`.git/objects/` 里是
#: `reference/*.py` 的**历次副本**（实测 1626 个对象），而且实测确实有组/其它开放的条目
#: （`.git/index`、`.git/refs/heads/main`、若干 object）。
#: 「版本库内部」不是一条可证伪的理由 —— 与 `__pycache__` 那条同款。
#:
#: `.venv` / `venv` 也摘掉了：两者在本仓与 `GENEBENCH_ROOT` 下**都不存在**
#: （python 环境叫 `env`，本来就在审计范围里）—— 一条**从不触发**的 skip
#: 会让人以为某处被排除了，而实际上没有。死 skip 与死白名单同族。
SKIP_DIRS: frozenset[str] = frozenset()

_GO_BITS = stat.S_IRWXG | stat.S_IRWXO          # 组 + 其它的全部位

#: **access_log 是探针结算源**，轮转策略定死（裁定 2026-09-04）：
#: append-only、按日分文件、**永不自动轮转**；归档只在 M6 结算完成后手动做。
#:
#: 为什么不能自动轮转：轮转落在某次 run 中间，切片就缺一段 ——
#: 而**缺段看起来像「这段时间没请求」**。前视探针零命中、越权率 0、
#: declared_reads「完全一致」（两边都是空的），每一条都绿、每一条都没测到东西。
#: 这是 D-06 的第 N 个形态，与「空切片看起来像什么都没请求」同族。
ACCESS_LOG_NAME = "gateway_access.jsonl"
#: 会自动轮转它的配置该出现的地方。存在即红。
LOGROTATE_DIRS: tuple[str, ...] = ("/etc/logrotate.d", "/usr/lib/systemd/system",
                                   "/etc/systemd/system")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def roots(repo: Path | None = None) -> list[Path]:
    repo = repo or _repo_root()
    # `RUN_PRODUCT_ROOTS` 从审计里剪掉（N-862），但它下面的**代码树** `exec/`
    # 作为独立的根**加回来** —— 剪的是 run 产物，不是执行面的代码。
    out = ([repo] + [Path(x) for x in EXTERNAL_ROOTS]
           + [Path(x) / "exec" for x in RUN_PRODUCT_ROOTS])
    seen, uniq = set(), []
    for p in out:
        if p.exists() and str(p.resolve()) not in seen:
            seen.add(str(p.resolve()))
            uniq.append(p)
    return uniq


#: **答案面根**：gold / 参考题目录、以及从执行面拉回来的 run 目录。
#: 符号链接的禁令只在这几棵树下生效（裁定 2026-09-05）——
#: `GENEBENCH_ROOT` 下还挂着 conda 环境（`env` / `env_c`），那里的 5 000 多条 symlink 是正常的，
#: 一刀切会把守门变成永远红，而**永远红的门会被绕过**（与恒绿同族）。
#: 三条都**从 `cfg` 现算**（2026-09-13 卡 P1）：写死的话，`$GENEBENCH_ROOT` 在别处的
#: 机器上这三条路径都不存在 —— 符号链接那道门于是一条都不触发，**而守门照样返回 0**。
ANSWER_PLANE_ROOTS: tuple[str, ...] = ((
    str(_cfg.GENEBENCH_ROOT / "reference"),
    str(_cfg.GENEBENCH_ROOT / "runs_in"),
    str(_cfg.GENEBENCH_ROOT / "gold"),
) if _cfg is not None else ())


def _run_product_roots() -> tuple[str, ...]:
    """**执行面的 run 产物根** —— 从模式审计里剪掉（N-862，2026-09-14）。

    病灶（卡 B9 单机门实测）：单机形态下执行面根落在 `$GENEBENCH_ROOT` **里面**
    （`$GENEBENCH_ROOT/genebench_runner`，见 `runner/placement.runner_root`），
    而 P0 审计的正是 `EXTERNAL_ROOTS` 那棵树 —— 于是**上一个 run 自己写出来的 0644 产物
    让下一个 run 起不来**。容器里 agent 按它自己的 umask 写 `work/` 下的文件，那不是
    「有人把敏感根 chmod 松了」；拿红线 5 判它只会让这道门恒红，而**恒红的门会被绕过**
    （与恒绿同族，`check_no_logrotate` 里已经为同一条理由收窄过一次判据）。
    双机形态下 run 目录在 `$GENEBENCH_ROOT` 之外，P0 本来就看不见它们 ——
    这条剪枝做的事就是**让单机与双机看见同一批东西**。

    **判别力不许降低，所以只剪这一棵、而且 `exec/` 单独加回来**（见 `roots()`）：
    * 答案面字节落进 run 根 → 归 `runner/f02/answer_plane_guard.py` 的**树口径**扫描
      （每次落位 / 推送后都跑，命中即删），那本来就不是模式位这道门的活；
    * 代码树（`<run 产物根>/exec`）里 0775 的 `__pycache__` / 0644 的文件 → **照样红**。
    `ops/test_F10.py::test_run_产物剪枝不许伤到判别力` 两面各造一个当场证明。

    取值与 `runner/placement.runner_root()` **同源**：`GENEBENCH_RUNNER_ROOT` 赢过默认，
    不设它时取 `$GENEBENCH_ROOT/genebench_runner`。**发布方那台上这个路径不存在**
    （双机的执行面根是 `/data/genebench_runner`，在 `$GENEBENCH_ROOT` 之外），
    剪一棵不存在的树 = 行为逐字节不变。
    """
    v = (os.environ.get("GENEBENCH_RUNNER_ROOT") or "").strip()
    if v:
        return (str(Path(v)),)
    if _cfg is None:
        return ()
    return (str(_cfg.GENEBENCH_ROOT / "genebench_runner"),)


RUN_PRODUCT_ROOTS: tuple[str, ...] = _run_product_roots()


def _under_answer_plane(p: Path) -> bool:
    sp = str(p)
    return any(sp == r or sp.startswith(r + "/") for r in ANSWER_PLANE_ROOTS)


def _walk(root: Path):
    """按根遍历，跳过版本库内部与缓存。**目录与文件都产出**。"""
    yield root
    for p in root.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p



def _walk_stat(root: Path, skip: "frozenset[str]" = frozenset()):
    """与 `_walk` **同一个遍历集合**，但每条路径只做一次 `readdir`/`stat`。
    产出 `(Path, islink, mode | None, err | None)`。

    为什么值一个函数（W1，2026-09-10 实测）：`check()` 原先对每条路径做 4 次系统调用
    （`rglob` 内部的 lstat + `is_symlink()` + `stat()` + `is_dir()`），而两个根加起来是
    **5,486,074 条路径**（`runs_in` 一棵就 498 万）—— 一趟 **69 s**（热 cache，冷的更久）。
    而这道门是网关的 `ExecStartPre`，单元里的 `TimeoutStartSec` 当时是默认的 90 s：
    **每次起停都是一次掷硬币**（2026-09-10 08:48–08:55 连挂 4 次，NRestarts=4 才起来）。
    `os.scandir` 的 `DirEntry` 把 `readdir` 带回来的类型信息缓存下来，同一个判据 **26 s**（2.6×）。

    **判据一个字不改**，逐条对齐 `_walk` + 原 `check()`：
    * 产出集合 = 根自己 + 根下递归的每一条（`SKIP_DIRS` 里的名字不进、也不下钻）；
    * **不下钻符号链接目录**（`rglob` 本来就不跟随）；
    * `mode` 是 **`stat()` 跟随链接**的结果（与原来的 `p.stat()` 同语义），
      断链取不到就把异常放进 `err` —— 「读不到 ≠ 查过了没有」那条判据照旧。
    `ops/test_w1.py::test_walk_stat_matches_the_rglob_walk` 拿一棵带断链/正常链接/
    0755 目录/0644 文件的夹具，把两条路径的结论逐条比对。
    """
    import os as _os
    r = str(root)
    if r in skip:                     # N-862：整棵剪掉（`skip` 默认空 → 与本改动之前同集合）
        return
    try:
        st = _os.stat(r)
        yield root, _os.path.islink(r), st.st_mode, None
    except OSError as e:
        yield root, False, None, e
    stack = [r]
    while stack:
        d = stack.pop()
        try:
            it = _os.scandir(d)
        except OSError:
            continue                      # 目录本身的问题由它那一条（上面的 stat）记
        with it:
            for e in it:
                if e.name in SKIP_DIRS or e.path in skip:
                    continue          # `skip` 里的整棵不产出、也不下钻（N-862）
                try:
                    islink = e.is_symlink()
                except OSError:
                    islink = False
                try:
                    mode, err = e.stat().st_mode, None     # 跟随链接，与 `p.stat()` 同语义
                except OSError as ex:
                    mode, err = None, ex
                yield Path(e.path), islink, mode, err
                if not islink:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                    except OSError:
                        pass

#: `LOGROTATE_DIRS` 里只有第一个是**轮转配置专用**目录；后两个是 systemd 单元目录，
#: 底下绝大多数东西与轮转无关。判据因此按目录分。
#: 按**目录名**判，不按绝对路径 —— 绝对路径的那版在任何非 `/etc` 的
#: 测试夹具上都不成立，于是判别力测试造不出来（而造不出来的判别力就等于没有）。
_ROTATE_CONF_DIRNAMES = ("logrotate.d",)
_ROTATE_UNIT_SUFFIXES = (".timer", ".service")


def _could_rotate(dirname: str, f) -> bool:
    """这个文件**有可能**是一份会轮转 access_log 的配置吗？

    读不了它的时候用得上：读得了就直接看内容，读不了才需要这个保守判据。
    """
    from pathlib import Path as _P
    if _P(dirname).name in _ROTATE_CONF_DIRNAMES:
        return True                       # 轮转专用目录，里面每个文件都算
    return f.name.endswith(_ROTATE_UNIT_SUFFIXES)


def check_no_logrotate() -> list[str]:
    """**不存在针对 access_log 的自动轮转配置**（裁定 2026-09-04）。

    查两类：logrotate 的配置片段、systemd 的 timer/service。
    找不到配置目录本身不算问题（那台机器上就没有 logrotate）——
    但**找得到目录却读不了**要报出来：读不了 = 查不了，与「查了、没有」不是一回事。
    """
    bad: list[str] = []
    for d in LOGROTATE_DIRS:
        p = Path(d)
        if not p.is_dir():
            continue
        try:
            entries = list(p.iterdir())
        except OSError as e:
            bad.append(f"读不了 {d}（{e}）—— 读不了 ≠ 查过了没有")
            continue
        for f in entries:
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                # 与上面那句「读不了 ≠ 查过了没有」同一条理由 —— 但**判据要收窄**：
                # `LOGROTATE_DIRS` 里有 `/etc/systemd/system`，那底下躺着一堆
                # 与轮转无关、root 私有的东西（实测 `k3s-agent.service.env` 0600）。
                # 把它们一律报出来，这道门就**恒红** —— 而恒红的门与恒绿的一样会被绕过
                # （F7 的镜像面）。所以只报**可能是轮转配置**的那些：
                # logrotate 的配置目录下一律报；systemd 目录下只报 timer/service。
                if _could_rotate(d, f):
                    bad.append(f"读不了 {f}（{e}）—— 读不了 ≠ 查过了没有")
                continue
            if ACCESS_LOG_NAME in text or "genebench/logs" in text:
                bad.append(f"发现针对 access_log 的轮转配置：{f} —— "
                           f"轮转落在某次 run 中间会让切片缺一段，"
                           f"而缺段看起来像「这段时间没请求」（D-06）")
    return bad


def check(repo: Path | None = None) -> list[str]:
    """空列表 = 绿（与 check_export 同风格）。**目录与文件都查**。"""
    bad: list[str] = list(check_no_logrotate())
    prune = frozenset(RUN_PRODUCT_ROOTS)
    for root in roots(repo):
        for p, islink, mode, err in _walk_stat(root, prune):
            # **答案面根下不许有符号链接**（裁定 2026-09-05）。三条理由：
            # ① 它的权限位是链接自己的（0777），`stat` 看的是目标 —— 两边都不能拿来判；
            # ② 目标可以在根**之外**，等于给答案面开一个守门看不见的出口；
            # ③ 断链的（Codex 在 `.codex/tmp/arg0/` 留了一堆）连 `stat` 都不成 ——
            #    2026-09-05 就是它们让网关连续 20 次起不来（N-125）。
            # 所以不再「跳过」也不再按「读不到模式」记：**一律判违例**，让带进来的人处理掉。
            if islink and _under_answer_plane(p):
                try:
                    tgt = os.readlink(p)
                except OSError:
                    tgt = "?"
                state = "断链" if not p.exists() else "指向 " + str(tgt)[:60]
                bad.append(f"红线 5 答案面根下出现符号链接（{state}）{p}")
                continue
            if err is not None:
                bad.append(f"读不到模式 {p}（{err}）")
                continue
            if islink:
                # **答案面根之外的符号链接不按模式判**（N-818，2026-09-13）。
                #
                # 病灶是 `check()` 与 `harden()` 对同一条路径**口径相反**：这里的 `mode`
                # 来自 `e.stat()`（**跟随链接**，读到的是目标的位），而 `harden()` 对
                # 符号链接 `continue`（不替人改目标）。于是「跟随着判、跳过着修」——
                # 只要链接指向根外一个 0755 的东西，这道门就**结构上不可能被 harden 修好**。
                #
                # 它在发布方这台机器上永远不显形：`$GB/env` 是 conda 环境，
                # `python -> python3.10` 指向**同一棵树里**一个已经 0700 的实体文件，
                # 链条在根内终止。而 `python3.12 -m venv $GB/env` 在 POSIX 上默认把
                # `bin/python` / `bin/python3` / `bin/python3.12` 建成符号链接，
                # 最终指向**系统解释器**（Linux `/usr/bin/python3.12`、Mac `/opt/homebrew/…`，
                # 0755 且 root 所有）—— 也就是 README §2.1 / 手册 §1.2 让外部用户敲的那一行。
                # 实测（2026-09-13 卡 Tfin）：干净 venv → check 3 条红 → `--harden`
                # 打印「收紧 0 个条目」退 1 → 再 check 仍 3 条红，**网关永远起不来**。
                #
                # **为什么「跳过」是对的，而不是判别力的损失**：
                # ① 符号链接**自身**的模式在 POSIX 上恒为 `lrwxrwxrwx`，拿它判等于恒红；
                # ② 目标若在根内，它会以**自己的真实路径**被这趟遍历单独查到、单独判 ——
                #    这里再判一次只是重复，且重复的那一次改不动；
                # ③ 目标若在根外，那是「链接指到哪去了」的问题，归答案面那道门
                #    （上面 `_under_answer_plane` 那一条）管，不在这里重造一个管不了的。
                # **判别力不变**：根下一个真实的 0644 文件 / 0775 目录照样判红
                # （`ops/test_U.py::test_根下真实的0644文件和0775目录照样判红` 当场证明）。
                continue
            if mode & _GO_BITS:
                kind = "目录" if stat.S_ISDIR(mode) else "文件"
                bad.append(f"红线 5 {kind}对组/其它开放 {oct(mode & 0o777)} {p}")
    return bad


# 违例文本 → 这一类**是不是 `--harden` 修得好**。分类按 `check()` 自己产出的四种前缀走。
def fix_hint(bad: list[str]) -> str:
    """给这一批违例配一句**真能照着做**的修法。

    为什么值一个函数（N-818，2026-09-13）：原先 `assert_modes()` 对**任何**违例
    都只说一句「修：`python3 ops/guard_modes.py --harden`」。而 `check()` 报得出
    三类 `harden()` **结构上修不好**的东西 —— 答案面根下的符号链接（harden 不替人删）、
    读不到模式的断链（chmod 不到）、access_log 的轮转配置（根本不是权限）。
    外部用户照那句话做，看到的是「收紧 0 个条目」+ 同样的三条红，**再跑一次还是**——
    一句修不好的提示比没有提示更贵：它让人以为自己哪一步敲错了。
    """
    modes = [x for x in bad if "对组/其它开放" in x]
    links = [x for x in bad if "答案面根下出现符号链接" in x]
    unread = [x for x in bad if x.startswith("读不到模式")]
    rest = [x for x in bad if x not in modes and x not in links and x not in unread]
    parts: list[str] = []
    if modes:
        parts.append(f"模式放松的 {len(modes)} 条（对组/其它开放）：跑 "
                     f"`python3 ops/guard_modes.py --harden`")
    if links:
        parts.append(f"答案面根下的符号链接 {len(links)} 条：**`--harden` 修不好**"
                     f"（它不替人删东西）—— 自己把这些链接删掉，或换成实体文件")
    if unread:
        parts.append(f"读不到模式的 {len(unread)} 条（多半是断链）：**`--harden` 修不好** ——"
                     f"把断链删掉，或把它指向的东西补回来")
    if rest:
        parts.append(f"其余 {len(rest)} 条：**`--harden` 修不好** —— 照上面每条自己那句话处理")
    if not parts:
        parts.append("跑 `python3 ops/guard_modes.py --harden`")
    return "修：" + "；".join(parts)


def harden(repo: Path | None = None) -> int:
    """统一收紧。返回改动的条目数。**不逐个列举路径** —— 逐个列举正是漏掉的原因。"""
    n = 0
    prune = frozenset(RUN_PRODUCT_ROOTS)
    for root in roots(repo):
        for p, islink, mode, err in _walk_stat(root, prune):
            if islink:
                continue          # 符号链接由 `check()` 判违例；`harden` 不替人删东西
            if err is not None:
                continue
            if mode & _GO_BITS:
                os.chmod(p, mode & ~_GO_BITS)
                n += 1
    return n


#: git 自己造文件时用的模式（N-861）。见 `harden_git_repos`。
GIT_SHARED_MODE = "0600"


def harden_git_repos(repo: Path | None = None) -> list[str]:
    """让 `--harden` 变成**一次性的**（N-861，2026-09-14）。

    病灶：`harden()` 是一次 `chmod`，而 git **每次**写 `.git/index` / `refs/heads/*` /
    新 object 都按 umask 现造新文件 —— 实测（2026-09-14，f01，`umask 022`）：
    `chmod -R go-rwx` 之后**再提交一次**，`.git/` 下当场回来 **8** 条组/其它可读的条目
    （`index`、`refs/heads/master`、3 个 object 目录 + 3 个 object），`assert_modes()`
    下一次启动又红，而提示语还是「跑 `--harden`」—— 一条**永远修不完**的修法，
    与「修不好的提示」（N-818）同族。

    `core.sharedRepository = 0600` 让 git 自己按 0600 造。**同一个实测**：设了它以后再提交一次，
    `.git/` 下 **0** 条（工作树里那个新文件仍按 umask 造，那是真内容，照旧该被抓）。
    只写**仓库自己的** `.git/config`，不碰 `--global`、不碰任何系统配置（红线 B1）。
    返回真正改了的仓库路径；已经是 `GIT_SHARED_MODE` 的不重复写（幂等）。
    """
    done: list[str] = []
    for root in roots(repo):
        if not (root / ".git").is_dir():
            continue
        try:
            cur = subprocess.run(["git", "-C", str(root), "config", "--get",
                                  "core.sharedRepository"],
                                 capture_output=True, text=True, timeout=30)
            if (cur.stdout or "").strip() == GIT_SHARED_MODE:
                continue
            w = subprocess.run(["git", "-C", str(root), "config",
                                "core.sharedRepository", GIT_SHARED_MODE],
                               capture_output=True, text=True, timeout=30)
            if w.returncode == 0:
                done.append(str(root))
        except (OSError, subprocess.SubprocessError):
            continue                      # 没有 git / 不是仓库：不是这道门要判的事
    return done


def assert_modes(repo: Path | None = None, *, who: str = "进程") -> None:
    """**启动守门**：不合规就拒绝启动。网关 / scorer / 注入器在 import 期或 main 里调它。"""
    bad = check(repo)
    if bad:
        raise SystemExit(
            f"[{who}] 拒绝启动：敏感根的权限不合规（红线 5），{len(bad)} 条：\n  "
            + "\n  ".join(bad[:10])
            + "\n" + fix_hint(bad))


def main() -> int:
    ap = argparse.ArgumentParser(description="红线 5 敏感根权限守门")
    ap.add_argument("--harden", action="store_true", help="统一收紧后再查")
    ap.add_argument("--repo", default=None)
    a = ap.parse_args()
    repo = Path(a.repo) if a.repo else None
    if a.harden:
        n = harden(repo)
        g = harden_git_repos(repo)
        print(f"收紧 {n} 个条目"
              + (f"；另给 {len(g)} 个 git 仓库设了 core.sharedRepository={GIT_SHARED_MODE}"
                 f"（N-861：不设它，下一次 git 操作又把 .git/index 造成 0644）" if g else ""))
    # **把审计根打出来**（N-857）：`genebench_config` 不在时降级是预期的，
    # 但降级必须**看得见** —— 无声降级与恒绿同族。
    _r = "；".join(str(x) for x in roots(repo))
    _note = "" if CONFIG_AVAILABLE else "（本进程没有 genebench_config：执行面形态，" \
                                       "EXTERNAL_ROOTS / ANSWER_PLANE_ROOTS 为空，主判据照旧）"
    bad = check(repo)
    if bad:
        print(f"审计根：{_r}{_note}", file=sys.stderr)
        print(f"红线 5 不合规（{len(bad)} 条）：\n  " + "\n  ".join(bad[:20]), file=sys.stderr)
        # 命令行也打同一句修法 —— 否则「跑了 --harden 还是红」这条路上没有任何下一步。
        print(fix_hint(bad), file=sys.stderr)
        return 1
    print(f"审计根：{_r}{_note}")
    print(f"敏感根权限合规（{len(roots(repo))} 个根）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
