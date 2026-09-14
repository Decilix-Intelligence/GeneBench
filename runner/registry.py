"""被测配置注册表（卡 4.2 §15 / 裁定 2026-09-04）。

⚠ **这三条是 M6 的「验收配置」，不是实验设计**（范围修正 2026-09-04）。

「同一模型三种 harness」是**验收时固定模型效应**的做法 —— 让「链路跑通了没有」
这个问题的答案不被模型差异搅进来。它**不构成主实验的配置矩阵**：
主实验要测什么、配几个模型、几个种子，由 **M7 的实验设计文档**定，审定之后才启动网格。

这句话必须同时写在 `ops/specs/fairness_protocol.md §6.5` —— 两者在代码里
长得一模一样（都是 `Config` 实例），**只能靠这句话分开**。一份验收配置被当成
实验设计读，就等于宣称了一个我们没有做过的比较。
**M6 阶段的任何数字不进论文、不称主表。**

---

**一个模型、三种 harness。** v1.0 冒烟的三条配置全部用 DeepSeek（OpenAI 兼容端点）：
把**模型效应固定**，主表上暴露出来的就只有 harness 与协议臂的差异。
这是「同一模型三种 harness」这个设计的全部意义 —— 换模型的比较留给 v1.1。

**为什么是 DeepSeek 而不是 Claude / GPT**（2026-09-04 实测）：
`api.openai.com` 从两台机 TCP 层不通；`api.anthropic.com` 返回 403（Cloudflare 地区封锁）。
直连可用的是 deepseek / dashscope / bigmodel / moonshot。
**不走代理绕地区限制**（条款问题）—— v1.1 在受支持地区起执行节点加入 tailnet，
那是基础设施票（N-54），不是本卡能就地解决的事。

**凭据不进这个文件、不进仓库、不进对话。** 由用户以环境变量落到 f02 的 runner 配置；
`ops/test_env.py::test_no_api_key_material_anywhere` 盯着仓库与 run dir 里不出现密钥模式。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

#: 出向白名单**只放模型 API 域名**。
#: 行情 / 新闻源一律不得入表 —— 放进去等于让被测系统**绕过数据面取数**：
#: 网关 `access_log` 会干干净净、卡 5.1 的前视探针全绿，而 as-of 强制已经失效。
MARKET_DATA_HOSTS: tuple[str, ...] = (
    "query1.finance.yahoo.com", "query2.finance.yahoo.com", "fc.yahoo.com",
    "finnhub.io", "www.alphavantage.co", "api.polygon.io", "news.google.com",
    "api.tiingo.com", "api.twelvedata.com", "www.reddit.com", "api.stocktwits.com",
    "api.polymarket.com", "api.stlouisfed.org",
)


@dataclass(frozen=True)
class Config:
    """一条被测配置。`config_id` 是主表的切片键，进 `x-genebench-config-id`。"""

    config_id: str
    harness: str
    model: str
    #: OpenAI 兼容端点的 base URL。**主机名由它派生**，不另抄一份。
    base_url: str
    #: 装凭据的环境变量名。**只有名字，没有值。**
    api_key_env: str
    note: str = ""

    @property
    def host(self) -> str:
        h = self.base_url.split("//", 1)[-1].split("/", 1)[0]
        return h.split(":", 1)[0].lower()


DEEPSEEK = "https://api.deepseek.com"

#: **M6 构造验收**的三条。**同一模型、三种 harness** —— 固定模型效应。
#: 不是配置矩阵（见模块 docstring 与 fairness_protocol §6.5）。
PURPOSE: str = "acceptance"          # ← 不是 "experiment"
#: **内置的三条**。数据驱动的那些（`harnesses/`、`integrations/` 下的 `config.yaml`）
#: 合并在它后面；内置这三条**不因为数据而改变**，也不许被数据覆盖。
#: `CONFIGS`（主表用的那个名字）在本文件靠后处由「内置 + 数据」拼出来。
BUILTIN_CONFIGS: tuple[Config, ...] = (
    Config("cfg-openhands-deepseek", "OpenHands", "deepseek-chat", DEEPSEEK,
           "DEEPSEEK_API_KEY", "通用软件工程 agent —— 自带工具循环与文件系统操作"),
    Config("cfg-codex-deepseek", "Codex CLI", "deepseek-chat", DEEPSEEK,
           "DEEPSEEK_API_KEY", "CLI harness，经 base URL 方式指到 DeepSeek"),
    Config("cfg-rdagent-deepseek", "RD-Agent(Q)", "deepseek-chat", DEEPSEEK,
           "DEEPSEEK_API_KEY", "领域专用（量化研究循环）—— 只落 S3，见卡 4.2 §18"),
)


#: **每 run 的模型调用预算**（裁定 2026-09-05 通宵：每 run 预算闸 ≤ 100 次；真 API 总上限 3000）。
#: 由注入器写进边车的 `--max-calls/--max-tokens`，超限边车直接 402 并落 `budget_exceeded`。
#: tokens 上限是**成本护栏不是判据**，与 `BUDGET_TIERS` 同一套换算：
#: 档位调用数 × 每次调用的 prompt 量级（实测 Codex 43k–68k、opencode 约 30k，取 60k/次）
#: → 100 × 60k = **6,000,000**。
#:
#: **N-388 已裁定（用户，2026-09-10）：600,000 → 6,000,000。** 600k 的后果是实测过的 ——
#: `ops/reports/v1demo/` 那 8 个 run **8/8** 撞 token 闸，`max_calls` 只用到 18–22 / 100，
#: 于是表上的 `SR` / `pass@1` 读的是「预算够不够」而不是能力。撞闸的现场表现不是一条
#: 显眼的错误，是「agent 做到一半自己放弃了」—— **它长得像结论**。
#:
#: 抬上来之后**真跑不要再显式给 `--max-tokens`**：显式给的逐键赢过档位，
#: 随手写一个 3M 上去等于把 S4 的 9M 与 S7 的 18M 一起打回去。
RUN_BUDGET: dict[str, int] = {"max_calls": 100, "max_tokens": 6_000_000}

#: `RUN_BUDGET` 的**出厂值副本**。它回答一个问题：「这个进程里有没有人显式覆盖过预算？」
#: `ops/run_f02_a1.py` 的 `--max-calls/--max-tokens` 是**就地改 `RUN_BUDGET`**（只在本进程生效），
#: 所以 `budget_for` 只能靠「现值 ≠ 出厂值」认出显式覆盖 —— 显式给的永远赢过档位。
#: 代价是一个记录在案的边角：显式给的值**恰好等于默认值**时，档位仍然生效。
#: 那个方向是把护栏往上抬，不会让谁跑得比自己要的少，因此不值得为它加一个状态变量。
RUN_BUDGET_DEFAULT: dict[str, int] = dict(RUN_BUDGET)

#: **按阶段的预算档**（裁定 2026-09-07，卡 4.3）。键是 bundle 的 `task.yaml` 里那个 `stage`；
#: 没列进来的阶段一律走默认档 —— 表里只写「与默认不同」的那几档，不抄一份全表。
#:
#: **为什么要分档**：默认的 100 次是按「一次问答式调用」定的，而 S4（因子/信号构造）
#: 与 S7（回测）是**多轮研究循环** —— agent 要实现、跑、看结果、再改。撞闸的表现不是
#: 一条显眼的错误，是「agent 做到一半自己放弃了」（`llm_log` 尾部一片 `budget_exceeded`，
#: 分数照出）。那是最坏的一种失败：**它长得像结论**。
#:
#: **tokens 怎么定的**：token 闸是**成本护栏不是判据**，所以按「档位调用数 × 每次调用的
#: prompt 量级」给一个够用的数，不精算。实测量级：Codex 每次 prompt 43k–68k
#: （`harnesses/codex/README.md` §2），opencode 平均约 30k（`harnesses/opencode/README.md`）——
#: 取 60k/次。S4 150 × 60k = 9,000,000；S7 300 × 60k = 18,000,000。
BUDGET_TIERS: dict[str, dict[str, int]] = {
    "S4": {"max_calls": 150, "max_tokens": 9_000_000},
    "S7": {"max_calls": 300, "max_tokens": 18_000_000},
}

#: 合法的阶段名。**本文件自己写一份**，不从 `reference.artifact_schema` import ——
#: `runner/` 跑在执行面，import `reference` 就是把答案面拖上执行面（红线 B2；
#: `ops/test_inject.py::test_t11_execution_plane_modules_never_reach_reference` 守着）。
#: 两处漂开由 `ops/test_budget_tiers.py` 逐字比对盯着。
BUDGET_STAGES: tuple[str, ...] = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")


def budget_for(stage: str | None) -> dict[str, int]:
    """这道题该用哪档预算。**逐键**决定，返回**新字典**（调用方改不脏这张表）。

    * 没给 stage / 不认识的 stage → 默认档。**不抛** —— 注入器跑在 f02，它拿到的
      stage 是 bundle 自己说的；为一个拼错的字符串中止注入，换来的是「真跑起不来」
      而不是「预算不对」。拼错的 stage 该红的地方在出集侧（`genetask/schema.py`）。
    * 显式覆盖（`RUN_BUDGET` 被就地改过）→ **覆盖值赢过档位**，逐键判断：
      只给了 `--max-calls` 的话，`max_tokens` 仍然走档位。
    """
    key = str(stage).strip().upper() if stage else ""
    tier = BUDGET_TIERS.get(key, {})
    out = dict(RUN_BUDGET)
    for k, v in tier.items():
        if RUN_BUDGET.get(k) == RUN_BUDGET_DEFAULT.get(k):     # 这一项没被显式覆盖过
            out[k] = v
    return out



def by_id(config_id: str) -> Config:
    for c in CONFIGS:
        if c.config_id == config_id:
            return c
    for c in PENDING_CONFIGS:
        if c.config_id == config_id:
            raise RegistryError(
                f"{config_id!r} 登记了但 **enabled: false**（见对应的 config.yaml）—— "
                f"它不在主表里。要用它先把开关翻过来，并复核 assert_registry_sane 的判据")
    raise RegistryError(f"未知 config_id {config_id!r}；可选 {[c.config_id for c in CONFIGS]}")


class RegistryError(RuntimeError):
    pass


def collect_egress_hosts() -> dict[str, str]:
    """生成 `MODEL_API_ALLOW`：**主机名 → 哪些被测配置需要它**。

    §15 的第一条断言（键集**相等**，不是包含）比的就是这个函数的输出与
    `c41/egress_proxy.py::MODEL_API_ALLOW`。手抄的那份必然漂 ——
    现表两条（anthropic / openai）的引用者写的还是「待 M6 复核」，
    也就是**没有任何真实配置需要它们**（N-32）。
    """
    out: dict[str, list[str]] = {}
    for c in CONFIGS:
        out.setdefault(c.host, []).append(c.config_id)
    return {h: "、".join(sorted(ids)) for h, ids in sorted(out.items())}


# ---------------------------------------------------------------------------
# 数据驱动的配置合并（W-0，2026-09-06）
# ---------------------------------------------------------------------------
#: 与 `runner/c42/harness_commands.py::LAUNCH_ROOTS` 是同一批目录 ——
#: 一个被测系统的**启动方式**（`launch.json`）与**配置**（`config.yaml`）住在一起。
#: 阶段二/三的代理各自只加自己那个目录，**不再改本文件**：这就是数据驱动的全部目的。
CONFIG_ROOTS: tuple[str, ...] = ("harnesses", "integrations")
CONFIG_FILE = "config.yaml"

#: `config.yaml` 的键**全集**。少一个或多一个都红 —— 多余键在这里是静默的，
#: 在写它的人眼里却像是生效了，而「写了没生效」比「写错了报错」难查一个数量级。
CONFIG_KEYS: tuple[str, ...] = (
    "config_id", "harness", "model", "base_url", "api_key_env", "note", "enabled")

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _one_config_sane(c: Config, where: str) -> None:
    """**逐条**判据（与 `assert_registry_sane` 的前三条同源）。

    `enabled: false` 的那些也要过这三条：它们今天不合并，明天翻开关就合并了，
    而**翻开关的那一刻没有人会重新审一遍 base_url 指到哪**。
    """
    if not c.base_url.startswith("https://"):
        raise RegistryError(f"{where}: base_url 必须是 https")
    if not c.api_key_env.endswith("_API_KEY"):
        raise RegistryError(f"{where}: 凭据环境变量名要以 _API_KEY 结尾")
    if c.host in MARKET_DATA_HOSTS:
        raise RegistryError(
            f"{where}: base_url 指向行情/新闻源 {c.host} —— "
            f"那等于让被测系统绕过数据面取数")


def config_files(repo_root=None) -> list[Path]:
    """两棵树下的全部 `config.yaml`，按路径排序 —— 顺序稳定，报错才可复现。"""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    out: list[Path] = []
    for r in CONFIG_ROOTS:
        base = root / r
        if not base.is_dir():
            continue
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            if (d / CONFIG_FILE).is_file():
                out.append(d / CONFIG_FILE)
    return out


def load_data_configs(repo_root=None) -> tuple[tuple[Config, ...], tuple[Config, ...]]:
    """读两棵树下的 `config.yaml`，返回 `(enabled, pending)`。

    `enabled: false` 的**只登记不合并**：进 `PENDING_CONFIGS`，不进 `CONFIGS`，
    因此既不参与「同一模型」判据，也不会被 `by_id` 找到。
    **登记而不生效是一个显式状态**，不是遗漏。
    """
    enabled: list[Config] = []
    pending: list[Config] = []
    for p in config_files(repo_root):
        try:
            import yaml
        except ImportError as e:                                # pragma: no cover
            raise RegistryError(
                f"{p} 在，但没有 PyYAML 解析它。**不要静默跳过** —— "
                f"跳过的表现正是「配置写了没生效」") from e
        try:
            raw = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise RegistryError(f"{p}: 读不出来（{type(e).__name__}: {e}）") from e
        if not isinstance(raw, dict):
            raise RegistryError(f"{p}: config.yaml 顶层必须是映射")
        missing = [k for k in CONFIG_KEYS if k not in raw]
        extra = [k for k in raw if k not in CONFIG_KEYS]
        if missing or extra:
            raise RegistryError(
                f"{p}: config.yaml 键集必须**恰好**是 {list(CONFIG_KEYS)}"
                f"（缺 {missing}；多 {extra}）")
        if not isinstance(raw["enabled"], bool):
            raise RegistryError(f"{p}: enabled 必须是布尔（读到 {raw['enabled']!r}）")
        for k in ("config_id", "harness", "model", "base_url", "api_key_env", "note"):
            if not isinstance(raw[k], str) or not raw[k].strip():
                raise RegistryError(f"{p}: {k} 必须是非空字符串（读到 {raw[k]!r}）")
        c = Config(raw["config_id"], raw["harness"], raw["model"],
                   raw["base_url"], raw["api_key_env"], raw["note"])
        _one_config_sane(c, str(p))
        (enabled if raw["enabled"] else pending).append(c)
    return tuple(enabled), tuple(pending)


def merge_configs(builtin=BUILTIN_CONFIGS, repo_root=None):
    """`(CONFIGS, PENDING_CONFIGS)`。数据里与内置**重名即红**。"""
    data, pending = load_data_configs(repo_root)
    builtin_ids = {c.config_id for c in builtin}
    for c in data:
        if c.config_id in builtin_ids:
            raise RegistryError(
                f"数据里的 config_id {c.config_id!r} 与内置的重名 —— "
                f"内置三条不许被数据悄悄换掉（要停用内置的是另一件事，得单独裁定）")
    return tuple(builtin) + tuple(data), pending


#: 主表的切片键集合 = **内置三条 + 数据里 `enabled: true` 的**。
CONFIGS, PENDING_CONFIGS = merge_configs()


def assert_registry_sane() -> None:
    """import 期跑。"""
    ids = [c.config_id for c in CONFIGS]
    if len(set(ids)) != len(ids):
        raise RegistryError(f"config_id 重复：{ids}")
    for c in CONFIGS:
        if not c.base_url.startswith("https://"):
            raise RegistryError(f"{c.config_id}: base_url 必须是 https")
        if not c.api_key_env.endswith("_API_KEY"):
            raise RegistryError(f"{c.config_id}: 凭据环境变量名要以 _API_KEY 结尾")
        if c.host in MARKET_DATA_HOSTS:
            raise RegistryError(
                f"{c.config_id} 的 base_url 指向行情/新闻源 {c.host} —— "
                f"那等于让被测系统绕过数据面取数")
    if PURPOSE != "acceptance":
        raise RegistryError(
            f"PURPOSE={PURPOSE!r} —— 这张表是 M6 的**验收配置**，不是实验设计。"
            f"要跑网格，先过 M7 的实验设计审定（实施稿 M7 节），"
            f"那时的配置矩阵另立一张表，不是改这里的一个字符串")
    models = {c.model for c in CONFIGS}
    if len(models) != 1:
        raise RegistryError(
            f"v1.0 的三条配置必须**同一模型**（实为 {sorted(models)}）—— "
            f"模型不固定的话，主表上 harness 差异与模型差异就分不开了")
    if len({c.harness for c in CONFIGS}) != len(CONFIGS):
        raise RegistryError("三条配置的 harness 必须互不相同")
    for st, tier in BUDGET_TIERS.items():
        if st not in BUDGET_STAGES:
            raise RegistryError(
                f"预算档位的阶段名 {st!r} 不在 {BUDGET_STAGES} —— 拼错的档位是**静默失效**的："
                f"`budget_for` 查不到它就回默认档，而写它的人以为已经生效了")
        if set(tier) != set(RUN_BUDGET_DEFAULT):
            raise RegistryError(
                f"档位 {st} 的键集 {sorted(tier)} ≠ 默认档 {sorted(RUN_BUDGET_DEFAULT)} —— "
                f"少一个键就是那一项悄悄回落到默认值")
        for k, v in tier.items():
            if v < RUN_BUDGET_DEFAULT[k]:
                raise RegistryError(
                    f"档位 {st} 的 {k}={v} 比默认档 {RUN_BUDGET_DEFAULT[k]} 还小 —— "
                    f"档位只能往上抬。要往下压是另一件事（得单独裁定），"
                    f"不能借着「分档」这个名义悄悄发生")


assert_registry_sane()
# ---------------------------------------------------------------------------
# 作业清单运行器的并发数（卡 5.3，2026-09-07）
# ---------------------------------------------------------------------------
#: `ops/run_joblist.py` 同时推进多少个 job。**默认 1。**
#:
#: 默认 1 不是保守，是这套系统里**没有 >1 的合法值**：网关是**单 worker**
#: （取证完整性要求 —— `access_log` 用进程内锁写，多 worker 会交错写坏行，
#: 而四个探针族靠这份日志结算，见 `ops/gateway_lock.py` 的模块 docstring），
#: 于是所有打网关的真跑都要先拿 `locks/gateway.lock`。把这个数调到 3，
#: 得到的是三个在 flock 上排队的线程 —— 墙钟一秒不省，日志却更难读。
#:
#: 它**仍然有意义**的地方是真跑之外那两步：出集（纯本机、按 task 互不相干）
#: 与结算/入库。运行器把它们放进同一个线程池，因此把这个数调大
#: 只会让「出集/推送」并行，真跑那一步照旧串行 —— 这就是
#: 「并发实现要与 gateway_lock 兼容」的全部含义。
#:
#: 什么时候可以调大：网关改成多 worker 且 `access_log` 换成可并发写的形式之后
#: （那是另一张卡，不是改这一行）。
RUNNER_CONCURRENCY: int = 1

if not isinstance(RUNNER_CONCURRENCY, int) or isinstance(RUNNER_CONCURRENCY, bool) or RUNNER_CONCURRENCY < 1:
    raise RegistryError(
        f"RUNNER_CONCURRENCY={RUNNER_CONCURRENCY!r} —— 必须是 ≥ 1 的整数。"
        f"0 或负数的表现是「一个 job 都不跑而且不报错」")
