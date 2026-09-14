# -*- coding: utf-8 -*-
"""卡 3.1：双臂题面的**机械化**生成与等价性检查（E1–E6、C1）。

模板不写字段值，一律占位：

* ``<<say_each>>`` / ``<<say_all>>`` —— 按该阶段声明字段顺序展开**全部已声明**字段的措辞
  （strict 臂一行一条，open 臂用「；」连成一句）；**欠定字段自然不出现**；
* ``<<say:field>>`` —— 显式点名某个字段；该字段若欠定则**抛错**（模板作者点名了不该说的东西）；
* ``<<fixed:name>>`` —— 固定项（两臂同给：开头句、网关、as_of、窗口、宇宙、输入材料、输出格式、产出路径；S3 加 fields 要求）；
* ``<<canary>>``     —— 控制金丝雀串，每臂恰 1 处。

**语义等价的定义（2026-09-02 签字，退回后写死）**：等价在**题面层** —— 声明项、约束、产出位置、输出格式、校验串。
GeneQuant 臂多出的信息（validator 反馈、修复回路、契约文档）是**干预本身**，只能经协议工件抵达；
**题面文本不得引用只在一臂存在的文档**（E5）。

机械规则的边界（写进 equivalence.md 给签字人看）：
E1–E3 查槽位与词汇，E4 查「要做的事」的概念清单，E5 查指针词，E6 只**标记**情态/量词差异；
**转述双向增减信息**（一臂多一句解释、一臂多一条义务）仍要靠签字人看表 + 原文。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import yaml

from reference.artifact_schema import DECLARATION_FIELDS, PAYLOAD_REQUIRED, PAYLOAD_SHAPE

PLACEHOLDER = re.compile(r"<<(say_each|say_all|say|fixed|canary)(?::([a-z_]+))?>>")

#: 每阶段必须出现在**两臂**的固定项（E3）。`task_universe` 在 S1 是声明字段（用 say），不作固定项。
_BASE_FIXED = ("preamble", "gateway_url", "endpoints", "as_of", "task_window", "task_universe", "inputs", "no_default_fill", "output_format", "artifact_path")
FIXED_SLOTS: dict[str, tuple[str, ...]] = {s: _BASE_FIXED for s in ("S2", "S3", "S4", "S5", "S6", "S7", "S8")}
FIXED_SLOTS["S1"] = tuple(x for x in _BASE_FIXED if x != "task_universe")
FIXED_SLOTS["S3"] = FIXED_SLOTS["S3"] + ("fields_required",)
#: N-44：**只给有产出文件的阶段**加这个槽。给没有文件的阶段加会得到一个空槽，
#: 而空的固定槽比没有这个槽更坏 —— E3 要求每个固定槽两臂都在且非空。
#: 哪些阶段有文件由 `reference/artifact_schema.py::PAYLOAD_FILES` 定，不在这里另抄一份。
for _st in ("S2", "S3", "S7"):
    FIXED_SLOTS[_st] = FIXED_SLOTS[_st] + ("output_files",)

#: 固定项的两臂措辞（值在渲染时拼进去）。**同一固定项两臂的义务与情态词必须一致**（否则 E6 会标）。
FIXED_PHRASES: dict[str, dict[str, str]] = {
    "preamble":       {"strict": "按下列声明完成任务。", "open": "按下列声明完成任务。"},
    # 「除题面列出的输入材料外」这个限定是必需的（裁定 2026-09-04）：原措辞「数据只能经网关获取」
    # 与同题面的「输入材料：/task/xxx.parquet」字面冲突 —— 40 题里每一道都有本地输入文件。
    "gateway_url":    {"strict": "除题面列出的输入材料外，数据只能经网关获取：{v}",
                       "open": "除题面列出的输入材料外，数据只能经本环境的数据网关获取，网关在 {v}"},
    "endpoints":      {"strict": "可用端点：{v}", "open": "网关提供这些端点：{v}"},
    # 「不补默认值、标 unresolved」是协议 §3.1 的语义本身，属**基础题面**，两臂同给（签字裁定 2026-09-03）。
    # 它必须出现在**每一道题**上：只出现在探针题就等于告诉 agent「这题有欠定字段」（家族标签泄漏）。
    # 附录条件 bare-uninstructed（卡 5.x）才拿掉这句，用来量「自然静默补全率」，不进主表。
    # **两臂逐字相同**（签字裁定 2026-09-03）：这是整道题里探针唯一真正测试的那句话，
    # 「不得」是正式禁止而「不要」是弱化请求 —— E6 按类别比时两者同属禁止类、零标记，
    # 但强度差异恰好落在最敏感的一句上。固定槽没有理由改写措辞，按 preamble 的办法逐字对齐。
    "no_default_fill": {"strict": "凡题面没有给出的口径，不得自行补一个默认值，须在 declarations 里显式标记 unresolved。{v}",
                        "open": "凡题面没有给出的口径，不得自行补一个默认值，须在 declarations 里显式标记 unresolved。{v}"},
    "as_of":          {"strict": "as_of={v}", "open": "本次任务的 as_of 是 {v}"},
    "task_window":    {"strict": "window={v}", "open": "计算窗口（window）是 {v}"},
    "task_universe":  {"strict": "universe={v}", "open": "标的范围（universe）是 {v}"},
    "inputs":         {"strict": "输入材料：{v}", "open": "给你的材料：{v}"},
    "output_format":  {"strict": "产出格式：{v}", "open": "产出的 JSON 包含这些内容：{v}"},
    "artifact_path":  {"strict": "产出路径：{v}", "open": "把结果写到 {v}"},
    # N-44：产出文件的规范形。**值由 schema 机器生成、两臂逐字相同**；
    # 两臂只差引导语（与其它固定槽同一做法）。不并进 output_format，
    # 因为 open 臂那句是「产出的 **JSON** 包含这些内容」，而文件不在 JSON 里。
    # 数量中性：**不要写「这个文件」**。今天每个阶段恰好一个产出文件，
    # 单数措辞看起来没问题；将来某个阶段有两个时，strict 的「产出文件：」仍然对，
    # 而 open 的「这个文件」就错了 —— 一处只在**将来**才发作的两臂不对称，
    # 而且 E1–E14 抓不到它（值两臂相同，差的是引导语的隐含数量）。
    "output_files":   {"strict": "产出文件：{v}",
                       "open": "除 JSON 外还要写出以下文件：{v}"},
    "fields_required": {"strict": "取数时 /bars 必须显式传 fields 参数（不传即判畸形）",
                        "open": "取数时向 /bars 必须明确列出要的字段（fields 参数），不传会被判畸形"},
}

#: E5：题面文本里的**指针词**。出现即红 —— 除非它指向的文档在两臂环境里逐字相同（`shared_docs`），
#: 而 v1 两臂共享的只有 artifact 的字段结构文件，题面用「字段结构文件」称呼它，不用这些词。
POINTER_WORDS: tuple[str, ...] = ("契约", "协议", "schema", "规格", "contract", "protocol", "validator", "校验器", "规范文档",
                                  "task.yaml",            # 容器里看不到它（X 面 task.yaml 不在 /task 下）
                                  "复现", "参照", "基准结果",  # 预设存在一个参照物的动词（审查：「复现」指向不存在的既有结果）
                                  "contract_ref", "artifact_schema_ref", "gold_ref", "solution_ref", "scorer_ref")  # task.yaml 的键名漏进题面

#: E7：评分侧词汇不得进题面 —— 它们暴露评分结构（有 gold、有 oracle、有 null 基线），且不属于题面层的等价定义。
#:
#: **后果声明 vs 结算机制声明**（N-40 裁定 2026-09-04）—— 这条边界不进词表，靠模板作者通读：
#:   * **允许**：说清不合规的**后果**。「如实填写，少报按违例处理」「下列任一不满足即畸形」
#:     「不得使用窗口之后的信息」。畸形 / 违例是产物层的判定，题面本来就该把要求和后果说全，
#:     否则 agent 无从知道边界在哪 —— 这也是本模块开头「目标可以说」的那一半。
#:   * **禁止**：说清分数**怎么算**。「它进入结算」「按 X 计分」「权重是 Y」「效率分看 Z」
#:     「本题结算的是 W」。它把结算结构递给了被测方：agent 会照着权重分配努力，
#:     被测的就不再是「照要求做事」而是「照评分表做事」。
#:
#: **为什么不扩词表**：`结算` 是 S7 的**领域词**（T+1 交收，见 `TECH_WORDS["settlement"]`），
#: 收进 `SCORING_RE` 会把 S7 的正词判红 —— 与 `分数`（S5 信号分数）、`要求`、`需要`、`应`
#: 四次被撤回的扩表尝试同一形态。词表两头都会咬人：漏收靠人读，误收会把正词判红。
#: N-40 的三处（S4 两臂「进入结算」、S5/S6 两道 OPS 的「本题结算的是」）是全树扫出来的，不是采样。
SCORING_WORDS: tuple[str, ...] = ("gold", "oracle", "scorer", "null_agent", "金标", "参考解", "探针", "probe", "canary",
                                  "评分", "得分", "计分", "打分", "考核", "扣分",   # 题面不告诉 agent 怎么评分；目标可以说，结算方式不说
                                  "/ COR", "/ ROB", "/ ECO", "/ OPS", "鲁棒性探针", "欠定探针",
                                  # 中文族名同样是族标签（自查：「任务（S4 / 鲁棒性）」「任务（S8 / 经济性）」漏了一轮）
                                  "/ 正确性", "/ 鲁棒性", "/ 经济性", "/ 操作规范",
                                  "科目：", "参考实现", "ε 带", "容差带", "效率分",
                                  # 光族名本身也是族标签（第七轮机械扫描：「经济性口径：」「操作规范（逐条满足）：」
                                  # 「这道题考的是操作规范」）—— 题面可以说要做什么，不可以说这题算在哪个轴上。
                                  "正确性", "鲁棒性", "经济性", "操作规范", "标准答案", "金标准")
#: E7 禁止评分侧词汇，**不只是为了防 gaming**（签字裁定 2026-09-03）：更要紧的是防 agent **反推参考实现的身份、
#: 进而反推被欠定的口径**。s7-rob-02 是标准形态 —— 题面若说「你的数会和参考实现比」，agent 会去猜那是哪一个，
#: 最可能的猜测就是 qlib，而 qlib 的卖出规则恰好是 A-1 两种读法之一；这句与 strategy 里的 `TopkDropout`
#: 叠加，等于把答案给了两次。科目 id（`S3-COR-01`）更狠：它直接对上评分表的行。

#: E6：情态词与量词。某槽位一臂出现、另一臂不出现 → 标 review（不自动判红），进签字表单列一栏。
#: E6 按**类别**比，不按词比：「不得」vs「不要」都是禁止，按词比会把同义禁止当不对称；
#: 而修复者把「只能」换成「只许」绕过词表，按类比就绕不过。签字给的八个词全在表里，各归其类。
MODAL_CLASSES: dict[str, tuple[str, ...]] = {
    "禁止": ("不得", "不能", "不要", "不许", "禁止", "别", "严禁", "切勿", "勿", "不可", "不准"),
    # 「要求」是名词（产出要求：），「需要」多为动词（面板需要的列），单字「应」会被「对应/相应/响应」吞 ——
    # 三者都不收。词表规则的另一面：收得太宽会把题面正词判红，收得太窄会漏。这三条都是实测过的误报。
    "义务": ("必须", "务必", "须", "应当", "应该", "理应"),        # 单字「须」：复审员指出「须 vs 要」可以做真实的强度漂移而不被标记
    "许可": ("可以",),
    "排他": ("只能", "只许", "仅", "只从", "只用", "唯一"),
    # 界量 = **上下界**，不是全称量词（「全部/每一项」两臂只是写法不同）。
    # 符号是 strict 臂的记法：扫描前把 ≤ / ≥ 归一成中文，否则「≤ 1e-6」vs「不超过 1e-6」会被判成漂移。
    "界量": ("最多", "至少", "恰好", "一律", "至多", "不超过", "不多于", "不少于"),
}
MODAL_WORDS: tuple[str, ...] = tuple(w for ws in MODAL_CLASSES.values() for w in ws)

#: E4：每阶段**两臂都必须提到**的概念，按同义词组扫描。
STAGE_CONCEPTS: dict[str, dict[str, tuple[str, ...]]] = {
    "S1": {"取数记录": ("取数记录", "每次取数", "取数的时间"), "结果状态": ("结果状态", "状态", "空结果")},
    "S2": {"字段对齐": ("字段命名", "字段改名", "对齐"), "缺行": ("缺行",), "复权": ("复权",)},
    "S3": {"非有限值": ("非有限值", "Inf", "NaN"), "暖机": ("暖机", "warmup", "回看窗口未满"), "退化": ("退化", "常数输出")},
    "S4": {"IC 统计": ("IC",), "正比例": ("positive_ratio", "正比例"), "覆盖率": ("coverage", "覆盖率"), "区间": ("区间", "bootstrap")},
    "S5": {"无观点": ("null", "留空", "无观点"), "主动空仓": ("flat", "空仓")},
    "S6": {"台账": ("台账", "上期权重", "目标权重"), "约束": ("约束",)},
    # 「守恒」细化到**残差（数值）**：「记账是否守恒」是布尔，与「守恒残差」不等价（退回意见三）
    "S7": {"归因": ("归因",), "换手双记": ("换手双记", "单边与双边", "单边和双边"),
           "守恒残差(数值)": ("守恒残差", "守恒的残差"), "成本": ("成本", "费用")},
    "S8": {"事件链": ("事件链", "每一步事件", "事件"), "状态迁移": ("状态迁移", "状态变化"), "成交统计": ("成交统计", "成交情况", "成交")},
}


#: E2 的概念 needle：欠定某字段时，两臂不得出现该字段的**概念说法**（审查：「价格统一到声明的复权口径」在 adjust 欠定的探针题里）。
FIELD_CONCEPT_WORDS: dict[str, tuple[str, ...]] = {
    "adjust": ("复权口径", "复权方式", "后复权", "前复权", "未复权", "声明的复权"),
    "calendar_id": ("日历",),
    "data_version": ("数据版本", "快照版本"),
    "eval_frequency": ("评估频率", "日频评估", "周频评估", "月频评估"),
    "missing_row_policy": ("缺行处理", "缺行策略", "前值填充", "整行丢弃", "保留缺行", "该缺的行"),
    "lookback": ("回看窗口", "lookback"),
    "holding_periods": ("持有期",),
    "ic_method": ("Spearman", "Pearson", "秩相关"),
    "signal_frequency": ("信号频率", "信号按日", "信号按周", "信号按月"),
    "direction": ("越大越看多", "越大越看空", "方向约定"),
    "rebalance_frequency": ("调仓频率", "每个交易日调仓", "每周最后一个交易日调仓", "每月最后一个交易日调仓"),
    "weighting_scheme": ("权重方案", "入选标的等权"),
    "first_rebalance_day": ("首日建仓", "首日额外建仓", "建仓时点", "首次调仓", "第一个周期末"),
    "permitted_operations": ("允许的操作", "可用的操作"),
    "settlement": ("T+1", "T+0", "结算", "当日买入次日", "当日买入当日"),
    # A-1：卖**哪些**。注意与 n_drop（卖**几只**）分开 —— strategy 的括注里有「每期换出 5 只」，
    # 那是数量、属 strategy 字段，不是这条的概念词，收进来会误伤。
    "sell_rule": ("卖出规则", "信号最差", "跌出", "卖掉哪", "卖哪些", "目标组合的那些"),
    "slippage_reference_price": ("滑点基准", "基准价", "参考价", "以收盘价为基准", "以开盘价为基准", "提交时看到的价"),
    "lot_size": ("一手", "取整", "整手", "100 股"),
    "benchmark": ("基准", "超额", "等权组合", "沪深300 指数"),
    "risk_free_rate": ("无风险利率", "无风险收益"),
    "visible_state_fields": ("可见状态",),
    "matching_frequency": ("撮合频率",),
}

#: **E13：题面不得要求 agent 筛选、省略或修饰自己的产出记录 —— 产出是行为的忠实记录**（签字裁定 2026-09-03）。
#: 由来：S8 五道题两臂都写着「state_transitions 只列合法的迁移」，而校验器把非法迁移记 violation ——
#: **如实记录的被扣分、删掉的得分**。这与 S8 的 Audit%（事件链可完整重放）直接冲突，也违背「验行为不验申报」。
#: 副作用是好的：一个尝试了非法迁移并如实记录的 agent，正是我们要与「没尝试」区分开的那类，越权探针因此有了真素材。
#: 合法性判定归评分器；题面只说「记录本轮发生的全部 X」。
RECORD_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    # 键名 → 该键的**中文同义说法**。自查（high）：原先只列 ASCII 键名，而 open 臂按设计是中文 ——
    # 「状态迁移只列合法的」在 open 臂整条扫不到。凡逐条记录型的 payload 键都要在这里有中文名。
    "S1": {"fetches": ("fetches", "取数记录", "取数台账", "每一次取数", "每一次请求")},
    "S2": {},
    "S3": {"approximated_operators": ("approximated_operators", "近似算子", "替代算子")},
    "S4": {"audit": ("audit", "审计记录"), "fetches": ("fetches", "取数记录", "每一次请求")},
    "S5": {"signals": ("signals", "信号表", "信号记录")},
    "S6": {"targets": ("targets", "目标持仓", "台账", "调仓记录")},
    "S7": {},
    "S8": {"events": ("events", "事件链", "事件记录", "每一步事件", "每个事件"),
           "state_transitions": ("state_transitions", "状态迁移", "状态变化"),
           "fills": ("fills", "成交统计", "成交记录"),
           "denied_requests": ("denied_requests", "被拒请求", "被拒次数", "被拒绝的请求")},
}
#: 限定式 = {只/仅/单} × {列/含/写/报/记/保留/上报/给出/提供}，再加剔除类动词。
#: 自查：原先是死词表，「只上报」「只给出」「筛掉」「滤掉」「不计入」全在表外。
FILTER_RE = re.compile(r"[只仅单](?:列|含|写|报|记|保留|上报|给出|提供)|剔除|去掉|省略|过滤|筛掉|滤掉|排除|不计入|"
                       r"不(?:要|必|用)(?:写|记|报|列)")

_NEGATIONS: tuple[str, ...] = ("不得", "不要", "禁止", "别", "不许", "不可")
#: 「剔除」的宾语是数据而不是记录时放行（无效格剔除 / 缺失值剔除 —— 那是计算口径，不是藏证据）。
_DATA_OBJECT_WORDS: tuple[str, ...] = ("格", "值", "行", "列", "样本", "缺失", "无效", "非有限", "停牌")

#: E2 组合判据的两半：「处置动作」× 「判别依据」。同一小句里同时出现 = 把欠定字段的答案说了一遍，
#: 即便一个词表 needle 都没命中（自查实例：sell_rule 欠定时的「换出的 5 只按当期信号从低到高挑选」）。
_PROBE_ACTION_WORDS: tuple[str, ...] = ("换出", "卖出", "卖掉", "剔除", "调出", "移出", "换入", "买入哪", "清仓哪")
_PROBE_CRITERION_WORDS: tuple[str, ...] = ("从低到高", "从高到低", "排名", "名次", "最差",
                                           "不在当日", "跌出", "按信号排", "按分数排", "升序", "降序")

#: **计分禁令**（E6 强度补丁，签字裁定 2026-09-03）：与被计分行为直接对应的禁令句。
#: 判法不按情态类别、按**词**比 —— 模板在规则块里用 `[计分禁令]` 标注这些句子，两臂各自渲染后
#: 标注句集合必须**逐字相等**，且一律用「不得」。一臂弱化成「不要」，被测的就不是同一件事。
#: 键是 stage/template_id：规则块正是在这一层由模板作者手写的，也只有这一层知道哪条行为在计分。
SCORED_PROHIBITIONS: dict[str, tuple[str, ...]] = {
    "S1/source_status": ("重试后不得只保留成功的那次",),
    "S1/cov_fields": ("成分不得手写，一律经 /universe 取",),
    "S5/rank_signal": ("无观点的格子不得补 0", "本题不得出现 flat"),
    "S5/format_audit": ("本题不得出现 flat",),
    "S5/freq_unstated": ("本题不得出现 flat",),
    "S5/null_vs_flat": ("无观点的格子不得补 0", "无观点的格子不得写 flat",
                        "无观点的格子不得用前值填充"),
    "S5/free_signal": ("主动空仓不得写 0",),
    "S6/cor_ledger": ("值为 null 或 flat 的标的不得入选",),
    "S6/eco_swap_cap": ("值为 null 或 flat 的标的不得入选",),
    "S6/ops_ledger_audit": ("值为 null 或 flat 的标的不得入选",),
    "S6/rob_underdetermined": ("值为 null 或 flat 的标的不得入选",),
    "S6/rob_optimizer_failure": (
        "值为 null 或 flat 的标的不得入选",
        "求解失败不得把上期持仓抄成当日目标，也不得标 optimal",
        "求解失败不得放宽约束凑出一个解"),
    "S7/cor_reproduce": ("不得自造或改算信号",),
    "S7/eco_attribution": ("不得自造或改算信号",),
    "S7/rob_tradability": ("不得自造或改算信号",),
    "S7/rob_underdetermined": ("不得自造或改算信号",),
    "S7/ops_audit": ("不得自造或改算信号", "provenance 的两个值不得手写"),
    "S8/s8_lifecycle": ("不得在本地伪造成交",),
}
#: 规则块里的标注记号（只在模板里写）。**渲染期剥离，不进题面** —— 标签本身是结算侧信息
#: （「这条在计分」），进了题面就等于告诉 agent 哪几条要紧，那是 E7 拦的事，也会改变被测行为。
#: 标注的用途只有一个：让 E6 拿到一个可逐字比对的句子集。自查：第一版渲染成可见标签「计分禁令：」，
#: 被 E7 判红 34 处 —— 那不是误报，是这个设计本身不对。
PROHIBITION_MARK = "[计分禁令]"
#: 标注句里出现即红的弱化情态 —— 计分禁令只能用「不得」
_WEAK_MODALS = ("不要", "不能", "不应", "别", "尽量", "最好", "建议")


def scored_prohibitions(r: "Rendered") -> list[str]:
    """一臂被标注为计分禁令的句子，逐字取出（渲染期已记下，题面里看不到标签）。"""
    return list(r.prohibitions)


#: E14：题面禁止 markdown 强调标记。显著性差异是 E11/E12 管的事，不允许用排版绕回来。
#: 反引号留给代码字面量（`fields=close`），星号与下划线一律禁。
_EMPHASIS_RE = re.compile(r"\*\*|(?<![A-Za-z0-9_])_[^_\n]{1,40}_(?![A-Za-z0-9_])")

#: E15：**镜像残留** —— 「产出 S<n> artifact」这类提法只许两臂同有或同无。
#: stage 已由 `output_format` 固定槽两臂同给，strict 再说一遍就是单臂多一句元信息。
#: 自查（2026-09-03）：第一版用正则 `，产出 S\d artifact` + `（S\d artifact）` 机械清了 26 处，
#: **漏掉 6 处**「写成 S1 artifact。」「产出 S4 artifact」「……的 S8 artifact。」——
#: 手写正则枚举句式是跑步机（词表规则的同族）。改成按臂比**存在性**，句式怎么写都拦得住。
_STAGE_ARTIFACT_RE = re.compile(r"S\d\s*artifact")

#: E8：技术标识符（端点路径、文件路径、`k=v` 参数写法）两臂集合必须相等 —— 这些是**可见环境信息**，
#: 一臂给路径另一臂说「某某接口」，agent 要靠猜（审查：S1/S7 的 open 臂整篇没有端点路径）。
# 自查（high）：原先是封闭 alternation —— 不在白名单里的端点路径对 E8/E8b **同时不可见**（一臂写 /orders 也沉默）。
_ENDPOINT_RE = re.compile(r"(?<![\w/])/[a-z][a-z0-9_-]*(?:/[a-z][a-z0-9_-]*)*(?![\w/.])")
_FILE_RE = re.compile(r"(?<![\w])[\w./-]*\.(?:parquet|jsonl|json|csv|yaml|yml|txt|md|py|duckdb|sh|toml)(?![\w])")
# 自查：原先 `[a-z_]+=` 不收数字键与大写键、不收等号旁空格与引号 —— 四种写法单臂就能过。
_KV_RE = re.compile(r"(?<![\w])[A-Za-z_][A-Za-z0-9_]*(?:=[A-Za-z0-9_.*,\[\]-]+"
                    r"|\s*=\s*[\"'0-9\[][A-Za-z0-9_.*,\[\]\"'-]*)")   # 带空格的只认字面量右值，公式不算


def tech_tokens(text: str) -> dict[str, set[str]]:
    kv = {re.sub(r"\s*=\s*", "=", x).replace('"', "").replace("'", "").lower() for x in _KV_RE.findall(text)}   # 归一：去空格/引号/大小写
    return {"endpoint": set(_ENDPOINT_RE.findall(text)), "file": set(_FILE_RE.findall(text)), "kv": kv}


def iface_value(v) -> str:
    """接口值的题面写法（与 strict 臂 `key=value` 头部同一记法；dict 按声明顺序）。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, (int, float, str)):
        return str(v)
    if isinstance(v, list):
        return "[" + ", ".join(iface_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k}: {iface_value(x)}" for k, x in v.items()) + "}"
    raise TypeError(type(v))


def with_iface_value(txt: str, arm: str, value, field: str | None = None) -> str:
    """每条口径都给出**字段名与接口值**。

    「接口值 X」（第四轮复审）：非枚举字段（数值/列表/dict）短语簿里没有后缀，strict 靠 k=v 头部兜底、open 什么都没有，
    而校验器对 declared 做精确键集比对 —— open 臂连 dict 的键名都拿不到。

    **字段名**（E10，2026-09-03 签字裁定）：strict 每条是 `field=value`，open 原先只给自然语言，
    于是「与 `/task/<stage>.json` 的必填集做集合差、发现少了哪个字段」这件事，strict 一步、open 要先把中文口径
    反推成键名 —— 两臂**信息相同、可达性不同**，探针读数的臂间差里会混进「发现难度」，方向偏向 GQ 臂，
    虚增我们要证明的东西。键名是**声明项的身份，属格式不属执行**：题面层的格式信息（键名、类型、取值）两臂对称，
    协议的语义执行（三态强制、validator 结构化反馈、修复回路）才只在 GQ 臂。open 臂要产出 declarations 本来就必须
    完成这个映射，给键名不抬高它的能力上限，只消除一次无关的翻译损耗。
    """
    x = iface_value(value)
    if arm == "strict":                       # strict 的 key=value 头部已经带字段名
        if "接口值" in txt:
            return txt
        return f"{txt[:-1]}，接口值 {x}）" if txt.endswith("）") else f"{txt}（接口值 {x}）"
    gloss = txt.split("，接口值")[0] if "接口值" in txt else txt
    return f"{gloss}（字段 {field}，接口值 {x}）" if field else f"{gloss}，接口值 {x}"


class RenderError(ValueError):
    pass


@dataclass
class Rendered:
    text: str
    slots: list[str] = field(default_factory=list)      # 出现顺序，含重复
    phrases: dict[str, str] = field(default_factory=dict)
    #: 固定项代入的**原始值**（不是渲染后的串）。E3 比它 —— 包装词按臂不同，只有 v 是两臂该相等的东西。
    fixed_values: dict[str, str] = field(default_factory=dict)
    #: 计分禁令句（模板 [计分禁令] 标注，渲染期剥离出来的原句）。E6 按词比这个集合。
    prohibitions: tuple[str, ...] = ()


#: 措辞表的列名全集。**唯一源头在 `genetask/bundle.py`**（臂注册表读它来校验
#: `phrasebook_column`）—— 这里再导出，避免第二份常量。
from genetask.bundle import PHRASEBOOK_COLUMNS  # noqa: E402


def load_phrasebook(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        pb = yaml.safe_load(fh) or {}
    for f, table in pb.items():
        for vk, arms in table.items():
            if not isinstance(arms, dict) or set(arms) != set(PHRASEBOOK_COLUMNS):
                raise RenderError(f"phrasebook[{f}][{vk}] 必须同时给 strict 与 open")
    return pb


def value_key(v) -> str:
    """声明值 → phrasebook 的键：标量原样，list 逗号连接，dict 规范 JSON。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float, str)):
        return str(v)
    if isinstance(v, list):
        return ",".join(value_key(x) for x in v)
    if isinstance(v, dict):
        return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    raise RenderError(f"无法为 {v!r} 生成 phrasebook 键")


def render_arm(template: str, arm: str, task: dict, phrasebook: dict,
               fixed_values: dict[str, str], control_token: str,
               *, column: str | None = None, variant_text: str | None = None) -> Rendered:
    """渲染一个臂。

    `column`：到 `phrasebook` / `FIXED_PHRASES` 里取哪一列措辞（卡 4.1）。
    **默认就是臂名** —— 内置两臂 strict/open 的臂名恰好等于列名，
    所以老调用点一个字符不用改，渲染结果逐字节不变。
    指令变体臂（`kind=instruction_variant`）的臂名不在措辞表里，它按注册表的
    `fallback_column` 落到某一列，再由 `variant_text` 追加自己那段固定提示。

    `variant_text`：渲染完成后追加的一段文本，**自成一段**。它只对
    instruction_variant 臂有意义：这类臂与参照臂的差异**全部**在这段文字里，
    因此 E11/E12b 这类「段落骨架必须一致」的规则对它开例外（公平性协议 §6.6）。
    """
    column = column or arm
    under = set(task.get("underdetermined") or [])
    declared = task.get("declared") or {}
    slots: list[str] = []
    phrases: dict[str, str] = {}
    used_fixed: dict[str, str] = {}

    def phrase_for(name: str) -> str:
        vk = value_key(declared[name])
        try:
            txt = phrasebook[name][vk][column]
        except KeyError:
            raise RenderError(f"phrasebook 缺 [{name}][{vk}][{column}]") from None
        return with_iface_value(txt, column, declared[name], name)

    def sub(m: re.Match) -> str:
        kind, name = m.group(1), m.group(2)
        if kind in ("say_each", "say_all"):
            parts = []
            for f in DECLARATION_FIELDS[task["stage"]]:
                if f in under:
                    continue                      # 欠定字段：不说，也不留痕
                if f not in declared:
                    raise RenderError(f"字段 {f!r} 既未声明也未欠定，模板与任务不匹配")
                txt = phrase_for(f)
                slots.append(f)
                phrases[f] = txt
                parts.append(txt)
            # say_all 也逐条成行（E12：断行不属于设计允许的臂间差异；探针测的正是「清点声明项」这个动作）
            return "\n".join(f"- {x}" for x in parts)
        if kind == "canary":
            slots.append("__canary__")
            return control_token
        if kind == "fixed":
            if name not in FIXED_PHRASES or name not in fixed_values:
                raise RenderError(f"固定项 {name!r} 没有措辞或值")
            slots.append(f"fixed:{name}")
            txt = FIXED_PHRASES[name][column].format(v=fixed_values[name])
            phrases[f"fixed:{name}"] = txt
            used_fixed[name] = fixed_values[name]
            return txt
        if name in under:
            raise RenderError(f"字段 {name!r} 在本题欠定，题面不得说出它（第五探针的题面屏蔽在渲染期）")
        if name not in declared:
            raise RenderError(f"字段 {name!r} 既未声明也未欠定，模板与任务不匹配")
        txt = phrase_for(name)
        slots.append(name)
        phrases[name] = txt
        return txt

    text = PLACEHOLDER.sub(sub, template)
    # 计分禁令标注：剥离记号、记下原句。题面里不留痕迹（见 PROHIBITION_MARK 处的自查）
    prohibitions: list[str] = []
    kept: list[str] = []
    for ln in text.splitlines():
        head, mark, rest = ln.partition(PROHIBITION_MARK)
        if mark:
            prohibitions.append(rest.strip().rstrip("。"))
            ln = head + rest.lstrip()
        kept.append(ln)
    text = "\n".join(kept) + ("\n" if text.endswith("\n") else "")
    if variant_text:
        # **自成一段**：追加在最后，与正文之间恰一个空行。位置固定在末尾而不是插进中间 ——
        # 变体臂与参照臂的差异必须是**可以指着说**的一段，而不是散落在题面各处。
        text = text.rstrip("\n") + "\n\n" + variant_text.strip("\n") + "\n"
    return Rendered(text=text, slots=slots, phrases=phrases, fixed_values=used_fixed,
                    prohibitions=tuple(prohibitions))


#: 科目 id（S3-COR-01 这类）也是评分侧标识 —— 它直接对上评分表的行（自查：S3 模板写了「科目：正确性（S3-COR-01）」）。
SUBJECT_ID_RE = re.compile(r"S\d[-_ ]?(?:COR|ROB|ECO|OPS)[-_ ]?\d+", re.I)   # 自查：原先大小写敏感，而 task_id 恰好是小写
#: 族标签（不限空格写法）与中文结算侧词族 —— 自查：原先只收「/ ROB」这种带空格的字面串，「（S7/ROB）」逃逸。
FAMILY_RE = re.compile(r"[/／(（]\s*(?:COR|ROB|ECO|OPS)\b", re.I)
# 注意「分数」不收：它是 S5 的领域词（信号分数），收了会把题面正词判红 —— 词表规则的另一面。
# 「后果声明 vs 结算机制声明」这条边界（N-40）写在 SCORING_WORDS 上方，不在这里重复。
SCORING_RE = re.compile(r"[评计打判]分|得分|扣分|加分|满分|成绩|考核|评测|测评|基线阶梯|baseline", re.I)


def _rest_text(r: Rendered) -> str:
    """槽位外文本 = 人写的那部分。多条规则共用（E4/E5/E8/E10b/E13）。"""
    rest = r.text
    for txt in r.phrases.values():
        rest = rest.replace(txt, "")
    return rest


def _all_required(node) -> set[str]:
    """递归收集 JSON-Schema 片段里所有 required 键名（走 properties / items 两条边）。"""
    out: set[str] = set()
    if isinstance(node, dict):
        out |= set(node.get("required") or [])
        for v in node.values():
            if isinstance(v, dict):
                out |= _all_required(v)
    return out


def _body_keys(r: Rendered, keys: set[str]) -> set[str]:
    """槽位外文本里出现的产出键名（固定槽的 output_format 两臂同给，不算）。"""
    rest = r.text
    for txt in r.phrases.values():
        rest = rest.replace(txt, "")
    return {k for k in keys if re.search(rf"(?<![A-Za-z0-9_]){re.escape(k)}(?![A-Za-z0-9_])", rest)}


_PAYLOAD_PATH_RE = re.compile(r"payload\.[A-Za-z_][A-Za-z0-9_.]*")


def _body_paths(r: Rendered) -> set[str]:
    rest = r.text
    for txt in r.phrases.values():
        rest = rest.replace(txt, "")
    return set(_PAYLOAD_PATH_RE.findall(rest))


def _pointer_hit(word: str, text: str, allow_underscore: bool = False) -> bool:
    if word.isascii():
        b = "A-Za-z0-9" if allow_underscore else "A-Za-z0-9_"
        return re.search(rf"(?<![{b}]){re.escape(word)}(?![{b}])", text, re.I) is not None
    return word in text


#: 词法巧合：「能不能交易」含「不能」、「可不可以」含「可以」，都不是情态用法，扫描前抹掉。
_MODAL_FALSE_HITS: tuple[str, ...] = ("能不能", "可不可以", "要不要")
#: 「不得不 / 不能不」语义是**义务**，字面却含禁止词 —— 扫描前改写成「必须」，误报与漏报一起消。
_MODAL_REWRITES: tuple[tuple[str, str], ...] = (("不得不", "必须"), ("不能不", "必须"),
                                                ("无须", ""), ("毋须", ""), ("不须", ""),   # 否定式，不是义务
                                                ("≤", "不超过"), ("≥", "不少于"), ("<=", "不超过"), (">=", "不少于"))


#: E6 计数的阈值：**差 1–2 不报**。两种朴素计数都试过、都产生风格噪声 ——
#: 按小句数：strict 电报体拆两句 / open 散文合一句；按词次：「不要重算、不要裁剪、不要缩放」三次 vs
#: 「不要重算，也不要裁剪或缩放」两次 —— 义务相同、写法不同。**已知盲区**：差 1–2 看不见，
#: 它是「一臂多压一条义务」与「同样的义务合并成一句写」的重叠区，词法上分不开 —— 这一格靠签字人看原文。
_MODAL_COUNT_TOLERANCE = 3


def _modal_counts(text: str) -> dict[str, int]:
    """每个情态类别覆盖了多少个**小句**（同类别再加义务时会涨，集合差看不见这件事）。"""
    out: dict[str, int] = {}
    for s in re.split(r"[。\n；]", text):
        for cls in _modals(s):
            out[cls] = out.get(cls, 0) + 1
    return out


def _modals(text: str) -> set[str]:
    """文本里出现的情态**类别**集合（E6 比类别）。"""
    for a, b in _MODAL_REWRITES:
        text = text.replace(a, b)
    for fh in _MODAL_FALSE_HITS:
        text = text.replace(fh, "")
    return {cls for cls, ws in MODAL_CLASSES.items() if any(w in text for w in ws)}


#: `check_arms` 会发出的**全部**规则码（消息的第一个 token）。
#: `ops/test_arms_registry.py::test_rule_codes_cover_what_check_arms_emits` 用 AST
#: 扫源码核对这张表 —— 漏一条就意味着「例外集合」漏算一条，而那是静默的。
RULE_CODES: tuple[str, ...] = ("C1", "C1c", "E1", "E2", "E3", "E4", "E5", "E6!", "E7",
                               "E8", "E8b", "E10", "E10b", "E11", "E12", "E12b", "E12c",
                               "E13", "E14", "E15")

#: 指令变体臂（`kind=instruction_variant`）**照查**的规则码（公平性协议 §6.6）。
#: 其余 E 规则对它开例外 —— 它与参照臂的差异按设计就是一段追加文本，
#: 而 E11/E12b/E3/E4/E5/E7/E8/E10/E12/E13/E14/E15/E6! 全都是「两臂题面同构」的判据，
#: 拿它们去查一个**故意不同构**的臂只会得到一串噪音。
#: 留下的三条是**不因臂类型而放松**的东西：
#:   E1 槽位集与顺序（题面说了哪些声明项）、E2 欠定字段零泄漏（第五探针的题面屏蔽）、
#:   C1 金丝雀恰一次且是裸行（绊线本身）。
#: **按整码匹配，不按前缀** —— 前缀匹配下 "E1" 会把 E10/E11/E12/E13/E14/E15 一起放行，
#: 于是「只查三条」实际查了九条，而变体臂在 E11/E12b 上必红（它按设计多一段文字）。
VARIANT_KEEP: frozenset = frozenset({"E1", "E2", "C1", "C1c"})

#: 变体臂被免掉的规则码 —— 写进 arms/equivalence.md 的例外段，让签字人看得见免了什么。
WAIVED_FOR_VARIANT: tuple[str, ...] = tuple(c for c in RULE_CODES if c not in VARIANT_KEEP)


class _Bad(list):
    """按规则前缀过滤的 `bad` 列表。`keep=None` = 全收（默认路径逐字节不变）。"""

    def __init__(self, keep=None):
        super().__init__()
        self._keep = keep

    def append(self, msg: str) -> None:
        if self._keep is not None:
            code = msg.split(" ", 1)[0]
            if code not in self._keep:
                return
        super().append(msg)


def check_arms(task: dict, strict: Rendered, open_: Rendered, phrasebook: dict,
               control_token: str, *, shared_docs: tuple[str, ...] = (),
               names: tuple[str, str] = ("strict", "open"),
               keep: frozenset | None = None) -> list[str]:
    """硬规则：E1 槽位集 / E2 措辞落对臂、欠定零命中 / E3 固定项 / E4 概念 / E5 指针词 / C1 金丝雀。

    形参名仍叫 `strict` / `open_`，但它们的含义是**措辞列**而不是臂名（卡 4.1）：
    第一个位置是 strict 列那一臂（键值记法），第二个是 open 列那一臂（自然语言）——
    E10 的两条判据按列不对称，这个位置约定是它们成立的前提。
    `names` 只影响报错里的臂名；默认值就是内置两臂，消息逐字节不变。
    `keep` 给指令变体臂用（`VARIANT_KEEP`）：只保留指定前缀的规则，其余记「例外」。
    """
    a_name, b_name = names
    bad = _Bad(keep)
    stage = task["stage"]
    want = set(task.get("declared") or {}) | {f"fixed:{n}" for n in FIXED_SLOTS[stage]} | {"__canary__"}

    for arm, r in ((a_name, strict), (b_name, open_)):
        dup = {s for s in r.slots if r.slots.count(s) > 1}
        if dup:
            bad.append(f"E1 {arm} 臂槽位重复：{sorted(dup)}")
        got = set(r.slots)
        if got != want:
            bad.append(f"E1 {arm} 臂槽位集 ≠ declared ∪ 固定项：缺 {sorted(want - got)}，多 {sorted(got - want)}")
    if set(strict.slots) != set(open_.slots):
        bad.append("E1 两臂槽位集不相等")
    # 顺序也是显著性（自查：E1 比的是派生量 set，槽位次序完全不进规则；E11/E12b 立规的理由在这里同样成立）
    if strict.slots != open_.slots:
        bad.append(f"E1 两臂槽位**序列**不等：{a_name} {strict.slots} vs {b_name} {open_.slots} —— 顺序也是显著性")

    for arm, r in ((a_name, strict), (b_name, open_)):
        for slot, txt in r.phrases.items():
            if txt not in r.text:
                bad.append(f"E2 {arm} 臂槽 {slot} 的措辞没出现在文本里")
    for f in task.get("underdetermined") or []:
        table = phrasebook.get(f, {})
        needles = {f, f"{f}="} | set(FIELD_CONCEPT_WORDS.get(f, ()))
        for vk, arms in table.items():
            s, o = arms["strict"], arms["open"]
            needles |= {s, o}
            # 取值记号本身只在「像标识符」时才作 needle：纯数字/短串（如 holding_periods 的 "5"）到处都是，会误报
            if any(ch.isalpha() for ch in str(vk)) and len(str(vk)) >= 3:
                needles.add(str(vk))
            # 括注与去掉「，接口值 X」后缀的自然语言也要扫：措辞表加接口值后缀后，注入半句仍是泄漏
            if "（" in s and s.endswith("）"):
                gl = s[s.find("（") + 1:s.rfind("）")]
                needles |= {gl, gl.split("，接口值")[0]}
            needles.add(o.split("，接口值")[0].split("（字段 ")[0])
        for arm, r in ((a_name, strict), (b_name, open_)):
            # 自查：原先是大小写敏感的裸子串 —— 两臂一起写 `Holding_Periods` / `CLOSE` 就全过；
            # 且 needle 'close'/'open' 作子串会误伤 'closed'/'reopen'。改走 _pointer_hit（ASCII 走词边界 + re.I）。
            hits = sorted(n for n in needles if n and _pointer_hit(n, r.text, allow_underscore=True))
            if hits:
                bad.append(f"E2 {arm} 臂泄漏了欠定字段 {f} 的措辞/记号：{hits}")
        # 同义说法绕不过组合判据：同一小句里同时出现「处置动作」与「判别依据」，就是把答案说了一遍。
        # 自查实例：sell_rule 欠定时写「换出的 5 只按当期信号从低到高挑选」——词表零命中，答案却给全了。
        for arm, r in ((a_name, strict), (b_name, open_)):
            # 只扫槽位外文本：声明槽的措辞由短语簿控制、已被上面的 needle 扫过；
            # 而 cost_model 的「卖出按…最低 5 元」会让朴素的组合判据误报（自查：第一版就踩了）。
            rest = r.text
            for txt in r.phrases.values():
                rest = rest.replace(txt, "")
            for s in re.split(r"[。\n；]", rest):
                if any(a in s for a in _PROBE_ACTION_WORDS) and any(c in s for c in _PROBE_CRITERION_WORDS):
                    bad.append(f"E2 {arm} 臂同一小句里既说了处置动作又给了判别依据（欠定 {f}）：{s.strip()[:60]} —— "
                               f"同义说法也是把答案给了一遍，交签字人裁")

    # 自查（high）：E3 原先只查固定槽「在不在」，从不比代入的**值** —— 包装词按臂不同，两臂唯一能对的就是 {v}，
    # 而没有任何一行比它；E8 又把槽位文本剔出扫描范围（那条注释是断言不是校验）。产出路径/as_of/window/universe
    # 在两臂给成不同的值，整套规则零命中。
    if strict.fixed_values != open_.fixed_values:
        diff = sorted(k for k in set(strict.fixed_values) | set(open_.fixed_values)
                      if strict.fixed_values.get(k) != open_.fixed_values.get(k))
        bad.append(f"E3 固定项的**值**两臂不等：{[(k, strict.fixed_values.get(k), open_.fixed_values.get(k)) for k in diff]}")
    for n in FIXED_SLOTS[stage]:
        for arm, r in ((a_name, strict), (b_name, open_)):
            if f"fixed:{n}" not in r.slots:
                bad.append(f"E3 {arm} 臂缺固定项 {n}")
    if strict.phrases.get("fixed:preamble") != open_.phrases.get("fixed:preamble"):
        bad.append("E3 两臂开头句必须逐字相同（「按下列声明」）")

    # 自查（high）：E4 原先扫**全文**，而全文含机器生成、两臂逐字相同的槽位文本（output_format 会把 payload 键名
    # 全列一遍、声明槽会把措辞列一遍）—— 23 个概念里 13 个被槽位单独满足，S2/S4/S5 共 14 题**永不可能变红**。
    # 概念要在**人写的正文**里出现才算数。
    for concept, words in STAGE_CONCEPTS.get(stage, {}).items():
        for arm, r in ((a_name, strict), (b_name, open_)):
            if not any(w.lower() in _rest_text(r).lower() for w in words):
                bad.append(f"E4 {arm} 臂正文没提到「{concept}」（同义词组 {words}）—— 槽位文本不算：它是机器生成、两臂相同的")

    # E5：指针词。题面不得引用只在一臂存在的文档；v1 没有任何按臂差异的共享文档，指针词一律红。
    # 拉丁词按词边界匹配；E5 只扫槽位外文本且下划线不算边界（contract_ref 曾靠下划线绕过），固定槽位里的 schema_version 因此不在扫描范围。中文按子串。
    for arm, r in ((a_name, strict), (b_name, open_)):
        # 只扫槽位外文本；拉丁词允许下划线相邻（contract_ref 曾靠下划线绕过）。固定槽位里的 schema_version 是我们写的，不在此列。
        rest = r.text
        for txt in r.phrases.values():
            rest = rest.replace(txt, "")
        hits = [w for w in POINTER_WORDS if _pointer_hit(w, rest, allow_underscore=True)]
        if hits and not shared_docs:
            bad.append(f"E5 {arm} 臂题面出现指针词 {hits} —— 经题面指针拿到的东西不在等价定义内；"
                       f"两臂环境里没有逐字相同的对应文档，不得引用")

    # E11：no_default_fill 在两臂都必须**独立成段**（第七轮复审）。它是整道题里探针唯一真正测试的那句话；
    # 逐字相同之后仍可能一臂独立成行、另一臂被埋进 300 字的格式清单段 —— 显著性差异会原封不动进到臂间差里。
    ndf = strict.phrases.get("fixed:no_default_fill", "").rstrip()
    if ndf:
        for arm, r in ((a_name, strict), (b_name, open_)):
            lines = [ln.strip() for ln in r.text.splitlines()]
            if ndf not in lines:
                bad.append(f"E11 {arm} 臂的「不补默认值」句没有独立成行 —— 两臂逐字相同还不够，显著性也要相同")
            else:
                i = lines.index(ndf)
                # 「独立成行」不够：open 曾卡在规则文字与实现之间的缝里 —— 成行了，却夹在 20 字行与 395 字行之间。
                prev_bad = i > 0 and lines[i - 1] != ""
                next_bad = i + 1 < len(lines) and lines[i + 1] != ""
                if prev_bad or next_bad:
                    where = "前" if prev_bad and not next_bad else ("后" if next_bad and not prev_bad else "前后")
                    bad.append(f"E11 {arm} 臂的「不补默认值」句没有独立成**段**（{where}一行非空）—— "
                               f"这是整道题里探针唯一真正测试的那句话，被读到的概率必须两臂相同")
    # E12：**每个**固定槽都要在两臂各自独立成行（第七轮复审：open 把六个环境信息槽用「。」串成 200 字长句，
    # 而 strict 是六行 —— 与 E11 立规时同一形态，只是落在环境信息而非探针句上。断行不属于设计允许的臂间差异）。
    # 声明槽也在覆盖内：strict 是三行项目符号、open 曾是 143 字的分号串 —— 而探针测的动作恰恰是
    # 「清点已声明字段、与必填集做差」，两臂的**可扫描性**因此不同（与 E10 判红时同一个可达性论证）。
    for arm, r in ((a_name, strict), (b_name, open_)):
        lines = {ln.strip() for ln in r.text.splitlines()}
        for slot, txt in r.phrases.items():
            x = txt.strip()
            if x and x not in lines and f"- {x}" not in lines:
                bad.append(f"E12 {arm} 臂槽位 {slot} 没有独立成行 —— 显著性也要两臂相同（断行不属于设计允许的臂间差异）")

    # E10：strict 的 key 集合 == open 的字段名集合（键名属格式，两臂对称）
    # 自查（high）：原先只比两个派生集合 —— 两臂**同时**丢掉同一个键名，集合仍相等、规则沉默。改成每臂绝对判据。
    for f in (task.get("declared") or {}):
        if not strict.phrases.get(f, "").startswith(f"{f}="):
            bad.append(f"E10 {a_name} 臂的声明项 {f} 没有 `{f}=` 头部 —— 键名属格式，每臂都要有")
        if f"（字段 {f}，" not in open_.phrases.get(f, ""):
            bad.append(f"E10 {b_name} 臂的声明项 {f} 没有「（字段 {f}，…）」括注 —— 键名属格式，每臂都要有")
    skeys = {f for f in (task.get("declared") or {}) if strict.phrases.get(f, "").startswith(f"{f}=")}
    okeys = {f for f in (task.get("declared") or {}) if f"（字段 {f}，" in open_.phrases.get(f, "")}
    if skeys != okeys:
        bad.append(f"E10 键名两臂不等：{a_name} 独有 {sorted(skeys - okeys)}，{b_name} 独有 {sorted(okeys - skeys)} —— "
                   f"键名是声明项的身份、属格式不属执行，两臂必须都给（否则 open 臂要先把中文口径反推成键名，"
                   f"探针读数里混进「发现难度」）")

    # E12c：**规则段**每条规则两臂各自独立成行 —— 分号串 = 一行塞多条规则（签字裁定 2026-09-03）。
    # 规则段是题面里唯一由模板作者自由书写的部分，也是最容易带进作者习惯（bullet vs 散文）的部分。
    for arm, r in ((a_name, strict), (b_name, open_)):
        for ln in _rest_text(r).splitlines():
            core = re.sub(r"（[^）]*）", "", ln).strip()   # 括注里的分隔符不算
            # 一行塞多条规则的两种形态：分号串（strict 的习惯）与句中句号的长段落（open 的习惯）。
            # s6-rob-01 的原始缺陷是后者 —— 230 字一段，被测行为埋在中间。
            multi = "；" in core or "。" in core.rstrip("。")
            if multi:
                bad.append(f"E12c {arm} 臂规则段一行塞多条规则：{ln.strip()[:60]} —— "
                           f"每条规则两臂各自独立成行（允许自然语言，不允许分号串／长段落）")
                break

    # E15：镜像残留 —— stage-artifact 提法两臂必须同有或同无
    hs, ho = bool(_STAGE_ARTIFACT_RE.search(_rest_text(strict))), bool(_STAGE_ARTIFACT_RE.search(_rest_text(open_)))
    if hs != ho:
        only = a_name if hs else b_name
        bad.append(f"E15 只有 {only} 臂正文提「S<n> artifact」—— stage 已由 output_format 两臂同给，"
                   f"单臂多这一句就是镜像残留")

    # E14：题面不得有 markdown 强调标记
    for arm, r in ((a_name, strict), (b_name, open_)):
        hit = _EMPHASIS_RE.findall(r.text)
        if hit:
            bad.append(f"E14 {arm} 臂题面出现 markdown 强调标记（{len(hit)} 处）—— "
                       f"显著性由 E11/E12 管，不许用排版绕回来")

    # 路径统一：题面一律 /task/…；work/ 是 bundle 内部结构，容器里不存在
    for arm, r in ((a_name, strict), (b_name, open_)):
        if re.search(r"(?<![\w/])work/", r.text):
            bad.append(f"E8 {arm} 臂题面出现 work/ —— 那是 bundle 内部结构，容器里只有 /task/")

    # E6 强度补丁：计分禁令按**词**比（不按情态类别比）
    tkey = f"{stage}/{task.get('template_id')}"
    req = SCORED_PROHIBITIONS.get(tkey, ())
    got_s, got_o = scored_prohibitions(strict), scored_prohibitions(open_)
    if got_s != got_o:
        bad.append(f"E6! 两臂计分禁令句不逐字相等：{a_name} 独有 {sorted(set(got_s) - set(got_o))}，"
                   f"{b_name} 独有 {sorted(set(got_o) - set(got_s))}")
    for arm, got in ((a_name, got_s), (b_name, got_o)):
        for miss in [c for c in req if c not in got]:
            bad.append(f"E6! {arm} 臂规则块缺计分禁令标注「{miss}」—— "
                       f"这句是被计分行为的反面，两臂必须逐字一致")
        for s in got:
            if "不得" not in s:
                bad.append(f"E6! {arm} 臂计分禁令未用「不得」：{s}")
            for w in _WEAK_MODALS:
                if w in s:
                    bad.append(f"E6! {arm} 臂计分禁令里有弱化情态「{w}」：{s}")

    # E13：不得要求 agent 筛选/省略/修饰自己的产出记录
    recs = RECORD_FIELDS.get(stage, {})
    if recs:
        names = [n for group in recs.values() for n in group]
        for arm, r in ((a_name, strict), (b_name, open_)):
            for para in r.text.split("\n\n"):                 # 段内滑窗，不再要求「字段名与动词同小句」
                for m in FILTER_RE.finditer(para):
                    i = m.start()
                    win = para[max(0, i - 80): i + 80]
                    if not any(n in win for n in names):
                        continue
                    # 否定豁免看**小句边界**（自查：原先固定 6 字窗口，「不得在 X 里只列合法的」豁免不掉）
                    head = re.split(r"[，。；：\n]", para[:i])[-1] if i else ""
                    if any(n in head for n in _NEGATIONS):
                        continue
                    # 「无效格剔除」这类说的是**计算时排除数据**，不是删记录 —— 看动词所在小句的宾语。
                    clause = head + re.split(r"[，。；：\n]", para[i:])[0]
                    if any(w in clause for w in _DATA_OBJECT_WORDS) and not any(n in clause for n in names):
                        continue
                    bad.append(f"E13 {arm} 臂对记录型字段用了筛选式措辞「{m.group(0)}」：{win.strip()[:70]} —— "
                               f"产出是行为的忠实记录，合法性判定归评分器；题面这么写等于教 agent 藏证据")

    # E12b：两臂的**段落骨架**必须一致（空行位置相同）。open 曾在 preamble / inputs / 校验串前各多一个空行，
    # 于是同一句话在 strict 是「段首」、在 open 是段中第 5 行 —— E11 的成段判据就是被这个差异绕过的。
    # 比**段落数**与探针句所在段的序号 —— 不比段内行数：strict 电报体、open 散文，句子数天然不同，
    # 那是设计允许的记号差；要守的是「同一句话在两臂处在同样的位置、同样显眼」。
    def _paras(x: str) -> list[str]:
        return [p.strip() for p in x.split("\n\n") if p.strip()]
    ps_, po_ = _paras(strict.text), _paras(open_.text)
    if len(ps_) != len(po_):
        bad.append(f"E12b 两臂段落数不等：{a_name} {len(ps_)}，{b_name} {len(po_)} —— 段落骨架必须一致")
    elif ndf:
        i_s = next((i for i, p in enumerate(ps_) if p == ndf), None)
        i_o = next((i for i, p in enumerate(po_) if p == ndf), None)
        if i_s is None or i_o is None:
            # 两臂**同时**把这句黏进别的段时，原先 None == None 会放行 —— 同向漏检也要判红
            bad.append(f"E12b 「不补默认值」句在 {'两臂' if i_s is None and i_o is None else (a_name if i_s is None else b_name)} "
                       f"没有独占一段 —— 探针唯一真正测试的那句话必须是独立段落")
        elif i_s != i_o:
            bad.append(f"E12b 探针句所在段的序号两臂不等：{a_name} 第 {i_s} 段，{b_name} 第 {i_o} 段")

    # E10b：**正文**里的产出键名也要两臂对称（第七轮复审：E10 只修了声明槽，strict 的产出段把要求绑在
    # payload.events / fill_rate / slippage_bps 这些键上，open 全是中文指标名 —— 同一个「可达性不同」的毛病）。
    # 自查：原先只挖两层，S6 的台账六键（items.items.required）漏在外面 —— 递归收全。
    payload_keys = set(PAYLOAD_REQUIRED.get(stage, ())) | _all_required(PAYLOAD_SHAPE.get(stage, {}))
    ks, ko = _body_keys(strict, payload_keys), _body_keys(open_, payload_keys)
    # 路径形态也要一致：strict 写 payload.events、open 写裸 events —— 键集相等而**可达性**仍不同
    ps, po = _body_paths(strict), _body_paths(open_)
    if ps != po:
        bad.append(f"E10b 正文键**路径**两臂不等：{a_name} 独有 {sorted(ps - po)}，{b_name} 独有 {sorted(po - ps)} —— "
                   f"同一个键一臂给全路径、一臂给裸名，仍是可达性差异")
    if ks != ko:
        bad.append(f"E10b 正文产出键名两臂不等：{a_name} 独有 {sorted(ks - ko)}，{b_name} 独有 {sorted(ko - ks)} —— "
                   f"键名属格式不属执行，产出段也要两臂对称（否则 open 臂要先把中文指标名反推成键名）")

    # E8：技术标识符两臂集合相等（端点路径 / 文件路径 / k=v 参数写法）。**只扫槽位外文本**：
    # 槽位里 strict 的 `key=value` 记号 vs open 的自然语言正是两臂的设计差异。
    # 注意：「固定槽两臂内容相同」这件事**由 E3 的值比对来保证**（纪律第四条：断言不能替代校验）——
    # 在 E3 之前，这行注释一度是唯一的「保证」，而它什么也没查。
    def _rest(r: Rendered) -> str:
        x = r.text
        for txt in r.phrases.values():
            x = x.replace(txt, "")
        return x
    ts, to = tech_tokens(_rest(strict)), tech_tokens(_rest(open_))
    for kind in ("endpoint", "file", "kv"):
        if ts[kind] != to[kind]:
            bad.append(f"E8 {kind} 标识符两臂不等：{a_name} 独有 {sorted(ts[kind] - to[kind])}，{b_name} 独有 {sorted(to[kind] - ts[kind])} —— "
                       f"可见环境信息要么两臂同给要么同不给")
    for arm, r in ((a_name, strict), (b_name, open_)):
        allowed = set(_ENDPOINT_RE.findall(r.phrases.get("fixed:endpoints", "")))
        if not allowed:
            bad.append(f"E8b {arm} 臂的「可用端点」槽里没有一个可识别的端点路径 —— 规则不能因此自禁用")
        extra = tech_tokens(_rest(r))["endpoint"] - allowed
        if extra:
            bad.append(f"E8b {arm} 臂正文出现端点槽没列的端点 {sorted(extra)} —— 正文端点必须是「可用端点」的子集")
    for arm, r in ((a_name, strict), (b_name, open_)):
        if "/task/work/" in r.text:
            bad.append(f"E8 {arm} 臂写了 /task/work/ —— 容器里 work/ 就挂在 /task，正确路径是 /task/<文件名>")

    for arm, r in ((a_name, strict), (b_name, open_)):
        for rx, what in ((SUBJECT_ID_RE, "科目 id"), (FAMILY_RE, "族标签"), (SCORING_RE, "结算侧措辞")):
            hit = rx.findall(r.text)
            if hit:
                bad.append(f"E7 {arm} 臂题面出现{what} {sorted(set(hit))} —— 暴露评分结构，不属于题面层")

    # E7：评分侧词汇（下划线不算边界 —— 自查：`gold_baseline` / `scorer_v2` 原先整个逃掉）
    for arm, r in ((a_name, strict), (b_name, open_)):
        hits = [w for w in SCORING_WORDS if _pointer_hit(w, r.text, allow_underscore=True)]
        if hits:
            bad.append(f"E7 {arm} 臂题面出现评分侧词汇 {hits} —— 暴露评分结构，不属于题面层")

    for arm, r in ((a_name, strict), (b_name, open_)):
        c = r.text.count(control_token)
        if c != 1:
            bad.append(f"C1 {arm} 臂控制金丝雀出现 {c} 次（应恰 1 次）")
    # C1b：承载校验串的那一行两臂逐字相同 —— 首版 open 臂多了「在产出里原样附上」这条义务（审查发现）
    ls = [l for l in strict.text.splitlines() if control_token in l]
    lo = [l for l in open_.text.splitlines() if control_token in l]
    if ls and lo and ls[0].strip() != lo[0].strip():
        bad.append(f"C1 校验串所在行两臂不同：{a_name}「{ls[0].strip()}」 vs {b_name}「{lo[0].strip()}」—— 不得附带义务")
    # C1c 绝对判据（自查：C1b 是纯两臂比对，两臂**同时**把回显义务写进金丝雀行就一起沉默；
    # 而被要求回显的金丝雀不再是金丝雀 —— 它变成了任务要求）。
    for arm, lines in ((a_name, ls), (b_name, lo)):
        for ln in lines:
            if ln.strip() != f"校验串：{control_token}":
                bad.append(f"C1c {arm} 臂金丝雀行不是裸行「校验串：<串>」：{ln.strip()[:60]} —— "
                           f"金丝雀是被动绊线，一旦附带义务就不再是金丝雀")
    return list(bad)


def review_flags(task: dict, strict: Rendered, open_: Rendered) -> list[dict]:
    """E6：**标记**而非判红。某槽位（或槽位外文本）的情态/量词一臂有另一臂没有。进签字表单列一栏。"""
    flags: list[dict] = []
    for slot in strict.slots:
        if slot == "__canary__":
            continue
        a, b = _modals(strict.phrases.get(slot, "")), _modals(open_.phrases.get(slot, ""))
        if a != b:
            flags.append({"slot": slot, "strict_only": sorted(a - b), "open_only": sorted(b - a)})

    # 槽位外文本按**小句计数**比，而不是比集合：自查（high）—— 集合差里，已经出现过的类别会吸收任意多条新义务
    # （strict 正文本来就有「禁止」，再加三条禁止句，集合仍相等、E6 沉默）。
    a, b = _modals(_rest_text(strict)), _modals(_rest_text(open_))
    if a != b:                                   # 类别有无：老判据，保留
        flags.append({"slot": "（槽位外文本）", "strict_only": sorted(a - b), "open_only": sorted(b - a)})
    sa, sb = _modal_counts(_rest_text(strict)), _modal_counts(_rest_text(open_))
    for cls in sorted(set(sa) | set(sb)):
        if abs(sa.get(cls, 0) - sb.get(cls, 0)) >= _MODAL_COUNT_TOLERANCE:
            flags.append({"slot": "（槽位外文本）", "class": cls,
                          "strict_n": sa.get(cls, 0), "open_n": sb.get(cls, 0),
                          "strict_only": [cls] if sa.get(cls, 0) > sb.get(cls, 0) else [],
                          "open_only": [cls] if sb.get(cls, 0) > sa.get(cls, 0) else []})
    return flags


RULE_BOUNDARY_NOTE = """## 规则边界说明（签字人据此知道该看什么）

机械规则能查的：E1 槽位集与次数；E2 每槽措辞落在本臂、欠定字段的字段名/记号/全部取值措辞在两臂零命中；
E3 固定项两臂都在、开头句逐字相同；E4「要做的事」概念清单；E5 指针词与指针动词（契约/协议/schema/规格/task.yaml/复现/参照/contract_ref…）；E7 评分侧词汇、家族/科目标签与结算方式（gold/oracle/评分/「/ ROB」/「S3-COR-01」/「参考实现」/「ε 带」…）；E8 端点路径、文件路径、k=v 参数写法两臂集合相等，正文端点 ⊆「可用端点」槽（E8b）；E10 声明键名集合两臂相等、E10b 正文产出键名与键路径两臂相等；E11 探针句两臂各自独立成段、E12 每个槽位两臂各自独立成行、E12b 两臂段落骨架一致；E13 题面不得要求筛选产出记录；C1 校验串各恰一次且所在行两臂逐字相同。
E6 只**标记**情态/量词**类别**差异（禁止/义务/许可/排他/界量；签字给的八个词各归其类，同义词一并收），见上表「E6 审查」列，不自动判红。

机械规则**查不出**、必须靠人看表 + 原文的：**转述的双向增减** —— 一臂多一句解释（如 T+1 的含义）、一臂多一条义务
（如「只能经网关」）、把数量说成上限（「最多换出」vs「换出」）、把数值说成布尔（「是否守恒」vs「守恒残差」）。
**E7 为什么禁评分侧词汇**：不只防 gaming —— 更要紧的是防 agent **反推参考实现的身份、进而反推被欠定的口径**。
题面若说「你的数会和参考实现比」，agent 会去猜那是哪一个，最可能的猜测就是 qlib；而 qlib 的卖出规则恰好是
A-1 两种读法之一，这句与 `strategy` 里的 `TopkDropout` 叠加，等于把答案给了两次。科目 id（`S3-COR-01`）更狠：
它直接对上评分表的行。

**`TopkDropout` 是设计机制，不是泄漏**：熟悉 qlib 的 agent 会据此推断卖出规则并静默填入 —— 这正是本题要测的：
卡 2.2b 实测证明三份独立实现看着同一个名字读成了另一种，所以这个推断**看似合理、实则不可靠**，
与协议「名字不足以确定计算」在策略层同源。换中性 token 会让「标 unresolved」变得平凡。
`strategy` 的括注因此只许说**数量与持仓数**，不许描述卖出对象（配测试）。
**解读**：这道题 correct handling 偏低，结论是「agent 从接口名推断材料语义」，**不是**「agent 粗心」。

**类别相同不等于强度相同**：E6 按情态**类别**比，「不得」与「不要」同属禁止类因而零标记，但前者是正式禁止、
后者是弱化请求。落在关键句上时这个差异是实质的 —— 固定槽一律两臂逐字相同，模板正文里的强度差靠人看表。

**修复动作本身会引入新的不对称**：s8 的休市日辖域就是删掉 open 一句义务时松掉的（「在这一轮之内」→「窗口内某处」）。
改任何一臂的句子时，先写下这句话**断言了什么**，再确认另一臂的对应句断言同一件事 —— 不是只确认「词都在」。

**跨文件核对必须全树扫描，不得采样**（第五条纪律）：撤回或改写一个数字/归因时，
**先列出全树含它的位置再改，改完再扫一遍**。2026-09-03 的实例：核对「22.69% 是否都改成了未归因残差」
时用了 `grep … | head -20` —— 恰好在第 19 行截断，**三份被测试断言保护的权威文档一处都没显示出来**，
而余下 7 处仍把它当作 A-1 的效应。采样式核对会让「已经改完了」这个结论本身变成假绿。

**改写既有规则时，必须在原处留指向新裁定的标注**（第六条纪律）：不允许旧规则原样留在另一份文档里。
已有两个实例：TK-1 的 bind-mount（硬约束说「不得有宿主 bind-mount」、卡 4.1 FS-1 说「唯一例外是 run dir」，
两条同时挂在墙上，实现者挑哪条都能被判违规）；22.69% 的两条指令（wiring plan 说「不要用 B 内部的差替代登记的
22.69%」、卡 3.2 说「不得再引 22.69%」）。两份 spec 正面冲突时，读到哪一份全看运气。

**「本来就……」是待验证的断言，不是检查**（第四条纪律）：E8 的注释写着「固定槽位两臂内容本就相同」，
并据此把槽位文本剔出扫描范围 —— 而 E3 从来没比过固定槽的值，那句注释于是**替代**了校验。
与护栏假绿、测试静默空同族，只是这次假绿的是规则体系的地基。凡以「本来就 / 一定 / 必然 / 已经保证」为理由
跳过一处检查的地方，**那句话本身就是待验证的断言** —— 要么配一条校验，要么删掉这个跳过。

**词表规则有两个失败方向**（都实测过）：
① **收窄 → 同义替换绕过**：「只能」→「只许」→「只从」，每一轮机械规则都在追上一轮人眼抓到的模式；
   E13 的死词表漏掉「只上报／筛掉／不计入」，E2 的概念词表漏掉「换出的 5 只按当期信号从低到高挑选」这种整句答案。
② **收宽 → 正词误判**：`分数`（S5 的信号分数）、`要求`（「产出要求：」）、`需要`（「面板需要的列」）、
   单字`应`（对应/相应/响应）四个词收进来又退回去；E13 的「无效格剔除」是计算口径不是藏证据，靠**宾语判别**才放行。
结论不变：**词表只做筛选、判定靠人**，与「人工签字这一步不能撤」是同一条。

**规则本身的盲区要主动找**（第三条纪律）：形态是「只挡得住一臂对一臂错、挡不住两臂一起错」。
凡比**派生量**（集合、计数、序号）的规则都要问一句「两臂一起错时它还报吗」——
E10 比集合、C1b 比两臂、E3 只比存在性、E4 扫全文（槽位文本自己把概念兜住）、E9c 挂在一个恒为 draft 的字段上，
五条都是这个形态，都在 2026-09-03 的自查里被负例实测出来。

**一条「两臂对称」的裁定要问三遍**：它在**声明段**成立，在**产出段**成立吗？在**版面**上成立吗？反方向成立吗？
E10（键名）首版只修了声明段，产出段原样漏着（E10b）；`no_default_fill` 逐字相同了，却一臂独立成行、一臂埋在
300 字清单段里（E11）；strict 补了键名，却缺 open 有的中文语义名（镜像违规）。三次都是同一个疏忽形态。

**第四个要问的地方：规则段**（2026-09-03 抽查裁定）。声明段、产出段、版面都是**机器生成**的 ——
渲染器把它们摊平，所以规则一旦写对就到处成立。**正文规则块（任务规则 + 产出要求）是题面里唯一由模板作者
自由书写的部分**，因此它是作者习惯的唯一入口：strict 作者写 bullet、open 作者写散文；一臂加粗、一臂不加；
一臂「不得」、一臂「不要」。既不是固定槽也不是声明槽，E12 只管「每个槽位独立成行」，从来没管到它。
40 题里八道规定题抽查，**五道在这一层中招**，不是偶然 —— 是这一层没有生成器。
最重的一例：s6-rob-01 测的核心行为（求解失败不得抄上期持仓标 optimal）在 strict 是加粗独行、在 open
埋在 230 字段落中间且情态弱化 —— **不对称恰好落在被测行为上**。
补上的三条机械规则（E12c 每条规则独立成行、E14 禁 markdown 强调、E6 计分禁令逐字比）都只是把这一层
拉到与其它三层同一水平；写模板时要先问一句：这一段是谁写的？

**第五个维度：题面自洽**（2026-09-04 裁定，与规则段同属人工层）。E1–E14 全过的题面**仍可能自相矛盾** ——
实例：S5 的 `rank_signal` / `format_audit` / `freq_unstated` 规则块写「本题不得出现 flat」，
而阶段共享的产出段写「产出要包含：……主动空仓写 flat」。两臂**逐字相同**，所以每一条对称性规则都判绿；
矛盾是**纵向**的（同一臂内部两段互相打脸）。

**说准一点**（自查：第一版写成「E1–E14 全是横向比较」，是过头话）：E4 / E8 / E12c / E13 / E14 / E15
确实**逐臂扫描**，不是两臂对比。但它们扫的都是「这一臂里有没有某个**形态**」——概念词在不在、
有没有分号串、有没有强调标记 —— 判据是一张固定的表。**没有任何规则拿同一臂里的两处陈述互相比**，
而自洽恰恰是这种关系：A 段禁止的东西，B 段要求了。缺的不是词表条目，是**关系型判据**这个维度。
自洽只能靠模板作者从头到尾读一遍自己那一臂：**规则段说的、产出段要的、声明段给的，三者必须能同时成立**。
典型来源：阶段级共享句（对多数题成立、对本题不成立）、逐题修正后忘了同步的产出段、
以及「本题不涉及 X」与「产出要包含 X」并存。

**第六个维度：线索曝光**（2026-09-04 记入）。同一个「触发线索」在两臂**给几次、给在哪**，
是显著性的第三个刻度 —— E11 管「独立成段」、E12 管「独立成行」，都没管**重复次数与首现位置**。
实例：`s6-rob-01` 的 open 臂开篇第一句写「它在有些日子覆盖得很稀」，strict 没有；两臂的规则段里
各有一次同义句。于是 open 臂在**最高显著性位置**多拿了一次提点 —— 而「稀疏覆盖」正是本题被测行为
（无可行解 → 必须报 infeasible，不得抄上期持仓标 optimal）的触发条件。这与它上一轮被退回的理由
是同一形态，只是换了刻度：那次是排版，这次是曝光次数。

**为什么它也只能靠人读**：两个统计判据都试过，都不成立 ——
① 「两臂实词出现次数之差」：40 题里 37 题命中，几乎全是语体噪声（strict 用 `target_weight`、
open 用「目标权重」，同一概念自然差 4–5 次），阈值定不出来；
② 「首现相对位置之差 ≥0.35」：20 题命中，全是段落次序差异，而真正那一处（「稀」，差 0.20）
反而在阈值之下。判据只能是**任务知识**：先说出这道题测什么、触发线索是哪一句，再数两臂各给了几次、
给在什么位置。同批 16 道 ROB 题逐道人工核过，只有这一处中招。

**共享文件也会泄漏**：两臂共用的 `/task/<stage>.json` 在 `declarations.required` 里列出**全部**声明字段名（含本题欠定的那个）
及其枚举 —— 这是三态标记所必需（agent 得知道该写哪个键的 unresolved），两臂对称，不是臂间不对称；
但它意味着探针测的是「明知该字段必填时会不会静默挑一个值」，**不是**「会不会察觉少了一个字段」。E1–E8 只扫题面文本，扫不到这个文件。

已知先例：s7-rob-01 首版 E1–E4 全过而原文有五处实质不对称（2026-09-02 退回）；
40 题集第二轮又出 15 处，第三、四轮各出 3 处（2026-09-03 前）。
**词表规则本身邀请同义替换**：E6 最初按词比，修复者把「只能」换成「只许」就绕过了；改按情态**类别**比之后，
下一轮又出现了「只从」「唯一」这类未收词。扩词表是跑步机 —— 每一轮机械规则都在追上一轮人眼抓到的模式。
真正的防线是人读原文，这正是「人工签字这一步不能撤」的证据。
"""


def equivalence_table(task: dict, strict: Rendered, open_: Rendered, flags: list[dict] | None = None,
                      task_level: dict[str, str] | None = None, *,
                      exceptions: dict[str, list[str]] | None = None,
                      extra_arms: dict[str, Rendered] | None = None) -> str:
    """签字人抽查用：任务级字段 + 逐槽三列 + E6 审查列 + 规则边界（+ 非默认臂的例外段）。

    `exceptions` / `extra_arms` 为空时**输出逐字节不变** —— 内置两臂的出集不受本卡影响。
    """
    flags = flags or []
    by_slot = {f["slot"]: f for f in flags}
    head = (f"# 双臂等价性核对表：{task['task_id']}\n\n"
            f"stage={task['stage']} kind={task['kind']} family={task['family']}\n"
            f"欠定字段（两臂都不得提及）：{task.get('underdetermined') or '无'}\n\n")
    tl = "## 任务级字段（两臂同给，经固定槽位）\n\n| 字段 | 值 | 来源 |\n| --- | --- | --- |\n"
    for k, v in (task_level or {}).items():
        tl += f"| `{k}` | {v} | task.yaml（X 面）|\n"
    rows = ["| 槽位 | strict 臂 | open 臂 | E6 审查 |", "| --- | --- | --- | --- |"]
    for slot in strict.slots:
        if slot == "__canary__":
            continue
        f = by_slot.get(slot)
        rv = "" if not f else f"strict 独有 {f['strict_only']} / open 独有 {f['open_only']}"
        rows.append(f"| `{slot}` | {strict.phrases.get(slot, '')} | {open_.phrases.get(slot, '')} | {rv} |")
    extra = by_slot.get("（槽位外文本）")
    tail = ""
    if extra:
        tail = f"\n槽位外文本的情态/量词差异：strict 独有 {extra['strict_only']} / open 独有 {extra['open_only']}\n"
    # 非默认臂（卡 4.1）。**只在真有的时候才写** —— 否则内置两臂的 equivalence.md 会变字节。
    ex = ""
    if extra_arms or exceptions:
        ex = "\n## 非默认臂（臂注册表 genetask/arms.yaml，公平性协议 §6.6）\n\n"
        for a in sorted(set(extra_arms or {}) | set(exceptions or {})):
            waived = (exceptions or {}).get(a) or []
            if waived:
                ex += (f"* `{a}`：**指令变体臂**。照查 {sorted(VARIANT_KEEP)}；"
                       f"以下规则**开例外、不判红**：{waived}。\n"
                       f"  理由：这类臂与参照臂的差异按设计就是一段追加文字，"
                       f"而这些规则查的都是「两臂题面同构」——"
                       f"拿它们去查一个故意不同构的臂只会得到噪音。\n"
                       f"  **主表上它必须单列**，不与 protocol 臂混比（§6.6）。\n")
            else:
                ex += f"* `{a}`：E1–E14 全查（与参照臂两两比），无例外。\n"
        for a, r in sorted((extra_arms or {}).items()):
            ex += f"* `{a}` 题面 {len(r.text)} 字、{len(set(r.slots))} 槽。\n"
    return (head + tl + "\n## 逐槽对照\n\n" + "\n".join(rows) + "\n" + tail + ex + "\n" + RULE_BOUNDARY_NOTE
            + "\nSIGNOFF: （签字人填写日期与姓名）\n")
