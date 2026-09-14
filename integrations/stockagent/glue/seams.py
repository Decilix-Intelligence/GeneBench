# -*- coding: utf-8 -*-
"""接线层 —— 全部是替换点，**上游一个字节没改**。

登记在 `REPLACEMENTS` 里的每一条都有一条判据盯着「上游那个名字还在不在」：
上游改名 / 挪位置时，我们要的是**当场红**，而不是「替换表打印得漂漂亮亮、
系统手里拿的还是原生实现」。

五处替换，各自的理由：

1. **模型分派**（`agent.Agent.run_api` / `secretary.run_api`）。上游按模型名分派：
   `'gpt' in model` 走 openai、`'gemini' in model` 走 google —— `deepseek-chat`
   **两条都不匹配，`run_api` 隐式返回 `None`**。上游对返回值只判 `resp == ""`，
   `None` 不等于 `""`，于是它会带着 `None` 走进 `secretary.check_loan`，
   在 `isinstance(resp, str)` 那里判 False、退回「格式错」并重试三次 —— 症状是
   「跑完了、一次交易都没有、也没有任何报错」。这是本接入第一处必须换的东西。
2. **`google.generativeai`**。`agent.py` 顶层 `import google.generativeai as genai`，
   而 `requirements.txt` 里**没有这个包**（上游自己的缺口）。我们不装它：
   它是另一家模型 API 的客户端，装了等于在镜像里留一条通向边车之外的路。
   顶替成一个「任何属性访问都抛」的陷阱模块 —— import 得过，真去用就炸。
3. **参考价**（`stock.Stock.get_price`）。上游的价格是内生的（A/B 两只虚构股票，
   初值写死在 `util.py`，之后由 agent 自己的撮合推动）。要让它对**真实标的**
   做判断，agent 看到的参考价必须是真实的 PIT 价格。替换后：撮合仍然按 agent
   自己报的价成交（`main.handle_action` 用的是 `action["price"]`），
   只有「今天这只股票多少钱」这一句换成网关来的收盘价。
   **这是一处替换，不是一处修复** —— 代价写在 README §4.1。
4. **首日基本面块**（`agent.FIRST_DAY_FINANCIAL_REPORT` / `FIRST_DAY_BACKGROUND_KNOWLEDGE`）。
   上游把四家虚构公司的三年财报**写死在 prompt 里**。对真实标的，那段文字是
   假信息，必须换掉。换成：真实代码、当天（含）之前的价量、题面给的因子值，
   以及一句「本环境没有财报数据源」——**并且真的去网关打一次 `/nodata/fundamentals`**，
   让这次「它想要财报」在 access_log 上留一行。
5. **落盘位置**。`log/custom_logger.py` 在 **import 期**就 `FileHandler('log/test.txt')`，
   `record.py` 往 `res/*.xlsx` 写 —— 两个都是**相对 CWD** 的路径。容器的 working_dir
   是 `/task`，也就是 run dir 的 `work/` 本身，落进去就破 P8 文件集封闭。
   所以在 `import` 上游之前先 `chdir` 到 `/tmp/...` 并把两个目录建好。
   注意顺序：**chdir 必须在 import 之前**，因为那个 FileHandler 是 import 期开的。
"""
from __future__ import annotations

import os
import pathlib
import sys
import types
from typing import Any, Callable

#: 每条是 (模块, 属性路径, 一句话)。判据按这张表逐条做存在性检查。
REPLACEMENTS: tuple[tuple[str, str, str], ...] = (
    ("agent", "Agent.run_api", "模型分派：deepseek-chat 两条分支都不匹配"),
    ("agent", "Agent.run_api_gpt", "上游的 openai 分支（我们不走它，但它必须还在）"),
    ("agent", "Agent.run_api_gemini", "上游的 gemini 分支（同上）"),
    ("agent", "Agent.plan_stock", "逐次决策：包一层只为记录，不改返回值"),
    ("agent", "Agent.plan_loan", "逐日贷款决策：包一层只为记录当前 sim 日"),
    ("agent", "FIRST_DAY_FINANCIAL_REPORT", "写死的三年财报（星号导入进 agent 命名空间的那一份）"),
    ("agent", "FIRST_DAY_BACKGROUND_KNOWLEDGE", "写死的公司背景（同上）"),
    ("secretary", "run_api", "Secretary 自己那条模型调用"),
    ("stock", "Stock.get_price", "参考价：内生 → 网关来的 PIT 收盘价"),
    ("util", "AGENTS_NUM", "规模闸：交易员数"),
    ("util", "TOTAL_DATE", "规模闸：模拟天数"),
    ("util", "TOTAL_SESSION", "规模闸：每日交易时段数"),
)

SCRATCH = pathlib.Path(os.environ.get("GENEBENCH_SA_SCRATCH", "/tmp/gb_stockagent"))


def prepare_cwd() -> pathlib.Path:
    """**必须在 import 上游之前调用。** 见模块 docstring 第 5 条。"""
    for sub in ("log", "res"):
        (SCRATCH / sub).mkdir(parents=True, exist_ok=True)
    os.chdir(SCRATCH)
    return SCRATCH


class _Trap(types.ModuleType):
    """任何属性访问都抛。装不上的东西**不能**顶替成一个「什么都返回 None」的假货 ——
    那样真走到那条路时是静默的错，而我们要的是当场炸。"""

    def __getattr__(self, name: str) -> Any:
        raise RuntimeError(
            f"google.generativeai.{name}：本镜像**故意不装** Gemini 客户端。"
            " 模型只经边车（OPENAI_BASE_URL），别的模型 API 在这个环境里不存在。")


def install_gemini_trap() -> None:
    """`agent.py` 顶层 import 它；不装就 import 不了，装了就多一条出网的路。"""
    if "google.generativeai" in sys.modules:
        return
    pkg = sys.modules.get("google")
    if pkg is None:
        pkg = types.ModuleType("google")
        pkg.__path__ = []  # type: ignore[attr-defined]
        sys.modules["google"] = pkg
    trap = _Trap("google.generativeai")
    sys.modules["google.generativeai"] = trap
    setattr(pkg, "generativeai", trap)


# ------------------------------------------------------------------ 模型侧

class Sidecar:
    """经边车的 chat。**base_url 只从环境变量取**，一个主机名都不写死。"""

    def __init__(self, *, model: str | None = None, max_calls: int | None = None) -> None:
        base = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_API_BASE")
        if not base:
            raise RuntimeError("OPENAI_BASE_URL 不在环境里 —— 模型只经边车，没有别的路。")
        from openai import OpenAI  # 构建期装好的
        self.model = model or os.environ.get("GENEBENCH_MODEL", "deepseek-chat")
        self._client = OpenAI(base_url=base, api_key=os.environ.get("OPENAI_API_KEY", ""))
        # 自设的调用上限：留出余量给格式重试，免得撞到边车的闸时
        # 整轮模拟停在一半（那样产物只有前几天，而**产物上看不出来是撞闸**）。
        self.max_calls = int(os.environ.get("GENEBENCH_SA_MAX_CALLS", max_calls or 90))
        self.calls = 0
        self.stopped_reason: str | None = None

    def chat(self, messages: list[dict], temperature: float = 1.0) -> str:
        if self.calls >= self.max_calls:
            self.stopped_reason = self.stopped_reason or "self_cap"
            return ""
        self.calls += 1
        try:
            rsp = self._client.chat.completions.create(
                model=self.model, messages=messages, temperature=temperature)
        except Exception as exc:  # noqa: BLE001 —— 上游对失败的约定就是空串
            text = str(exc)
            if "budget_exceeded" in text or "429" in text:
                self.stopped_reason = self.stopped_reason or "budget_exceeded"
            else:
                self.stopped_reason = self.stopped_reason or f"api_error: {text[:120]}"
            return ""
        return rsp.choices[0].message.content or ""


def install_model_seam(agent_mod, secretary_mod, sidecar: Sidecar) -> None:
    """把两处模型调用都换成边车。**保留上游自己的对话历史语义** ——
    `run_api_gpt` 是把整段 `chat_history` 一起送出去的，那是它的设计，不是缺陷。"""

    def run_api(self, prompt: str, temperature: float = 1.0) -> str:
        self.chat_history.append({"role": "user", "content": prompt})
        out = sidecar.chat(self.chat_history, temperature)
        if out:
            self.chat_history.append({"role": "assistant", "content": out})
        return out

    agent_mod.Agent.run_api = run_api
    secretary_mod.run_api = lambda model, prompt, temperature=0: sidecar.chat(
        [{"role": "user", "content": prompt}], temperature)


# ------------------------------------------------------------------ 上游自身的不一致

#: 上游 HEAD 的 `prompt/agent_prompt.py` 已经改成**四只股票**（A/B/C/D），
#: 而 `agent.py` / `main.py` / `secretary.check_action` 仍然只有两只（A/B）。
#: 后果不是「跑得慢一点」：`plan_loan` 在**第一天**就
#: `KeyError: 'stock_c'`（procoder 的 `content.format(**x)`，实测 smoke2.log）——
#: 也就是说**这个 commit 原样跑不起来，与用哪个模型无关**。
#:
#: 修法是把这几段 prompt 降回引擎真正支持的两只。下面的文字是**我们的**，
#: 由上游原文逐句删掉 C/D 从句得到（不是重写，也没有加新的指示）。
TWO_STOCK_PROMPTS: tuple[str, ...] = (
    "LASTDAY_FORUM_AND_STOCK_PROMPT", "DECIDE_IF_LOAN_PROMPT",
    "DECIDE_BUY_STOCK_PROMPT", "BUY_STOCK_RETRY_PROMPT",
    "NEXT_DAY_ESTIMATE_PROMPT", "NEXT_DAY_ESTIMATE_RETRY",
    "SEASONAL_FINANCIAL_REPORT", "BACKGROUND_PROMPT",
)

_BACKGROUND = """
    You are a stock trader, and you will simulate your interactions with other traders in the market.
    There are two stocks in the market, named A and B.
    Next, follow the instructions to complete your trading actions.
    """

_LASTDAY = """
    After the close of trading yesterday, the stock prices of Company A and Company B
    were {stock_a_price} dollars per share and {stock_b_price} dollars per share,
    respectively. Posts by other traders on the forum are as follows:
    {lastday_forum_message}
    """

_DECIDE_IF_LOAN = """
    It is the {date} day, and your current character is {character}.
    You hold {stock_a} shares of Company A, {stock_b} shares of Company B,
    now you have {cash} dollars in cash and {debt} in your loan situation.
    You need to decide whether to continue the loan and the amount of the loan.
    The alternative type is {loan_type_prompt}, and you should use the number to select a loan type.
    The loan amount shall not exceed {max_loan}.

    Return the result as json, for example:
    {{"loan": "yes", "loan_type": 3, "amount": 1000}}

    If no loan is required, return:
    {{"loan" : "no"}}
    """

_DECIDE_BUY = """
    It is the {time} trading session on the {date} day, and after the previous session,
    the stock price of Company A is {stock_a_price} and the stock price of Company B is
    {stock_b_price}.
    In the current session, the buy and sell order of stock A is {stock_a_deals},
    and the buy and sell order of stock B is {stock_b_deals}.
    You currently hold {stock_a} shares of Company A, {stock_b} shares of Company B,
    and {cash} yuan in cash.
    You need to decide whether to buy/sell shares of Company A or Company B,
    and how much to buy/sell and at what price.
    You can refer to the current share price and the market to determine the price yourself,
    not the current share price. The quantity must be an integer.
    We encourage you to buy and sell more. You can only answer one json action.
    Return the result as json, for example:
    {{"action_type":"buy"|"sell", "stock":"A"|"B", amount: 100, price : 30.1}}
    If neither buy nor sell, return:
    {{"action_type" : "no"}}
    """

_BUY_RETRY = """
    The following questions appeared in the action format you last answered:
    {fail_response}.
    You should return the result as json, for example:
    {{"action_type":"buy"|"sell", "stock":"A"|"B", amount: 100, price: 30.1}}
    If neither buy nor sell, return:
    {{"action_type" : "no"}}
    Please answer again. You can only answer one json action.
    """

_ESTIMATE = """
    Based on the market information and forum information of the current trading day, please estimate whether you
    will buy and sell stock A and stock B tomorrow and whether you will choose a loan.
    Actions that are expected to take place are marked yes, and actions that will not take place are marked no.
    Return the result in JSON format, for example:
    {{"buy_A":"yes", "buy_B":"no", "sell_A":"yes", "sell_B":"no", "loan":"yes"}}
    """

_ESTIMATE_RETRY = """
    The following questions appeared in the format you last answered:
    {fail_response}.
    Return the result in JSON format, for example:
    {{"buy_A":"yes", "buy_B":"no", "sell_A":"yes", "sell_B":"no", "loan":"yes"}}
    Please answer again.
    """

_SEASONAL = """
    Stock A: {stock_a_report}
    Stock B: {stock_b_report}
    """

_TWO_STOCK_CONTENT = {
    "BACKGROUND_PROMPT": _BACKGROUND,
    "LASTDAY_FORUM_AND_STOCK_PROMPT": _LASTDAY,
    "DECIDE_IF_LOAN_PROMPT": _DECIDE_IF_LOAN,
    "DECIDE_BUY_STOCK_PROMPT": _DECIDE_BUY,
    "BUY_STOCK_RETRY_PROMPT": _BUY_RETRY,
    "NEXT_DAY_ESTIMATE_PROMPT": _ESTIMATE,
    "NEXT_DAY_ESTIMATE_RETRY": _ESTIMATE_RETRY,
    "SEASONAL_FINANCIAL_REPORT": _SEASONAL,
}


def install_two_stock_prompts(agent_mod) -> list[str]:
    """把 C/D 从题面里删掉。

    两个坑，各踩了一次：

    1. `agent.py` 是 `from prompt.agent_prompt import *` 拿到这些名字的，
       所以要改的是 **`agent` 命名空间里的那一份**（改 `prompt.agent_prompt` 无效）。
    2. procoder 的 `NamedBlock` **不把 content 存成属性**：
       `NamedBlock.__init__` 把它塞进 `_modules["content"]`（一个 `Single`，
       正文在 `.prompt` 上）。`obj.content = "..."` 只是挂了一个没人读的属性 ——
       **不报错，也不生效**，症状是「替换打印得漂漂亮亮，KeyError 一字不改」（实测 smoke3.log）。
       所以这里是**新造一个同类对象**，名字与 refname 原样带过去。
    """
    done: list[str] = []
    for name in TWO_STOCK_PROMPTS:
        obj = getattr(agent_mod, name, None)
        if obj is None or name not in _TWO_STOCK_CONTENT:
            continue
        fresh = type(obj)(name=getattr(obj, "_name", name),
                          content=_TWO_STOCK_CONTENT[name],
                          refname=getattr(obj, "_refname", None))
        setattr(agent_mod, name, fresh)
        done.append(name)
    return done
