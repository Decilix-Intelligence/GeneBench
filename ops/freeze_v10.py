#!/usr/bin/env python3
"""v1.0 冒烟集冻结清单（M3 收口，放行 2026-09-04）。

**冻什么**：决定题面的**输入**，不是渲染产物。
`canary.control_token` 是每次打包新生成的 nonce（`secrets`），所以同一份模板两次 build
出来的 `instruction[arm].sha256` **必然不同** —— 拿渲染产物的 sha 当基准会永远对不上。
真正稳定的是：模板文件 + 措辞表 + 参数表 + 渲染器/规则代码。这四样任一变动，题面就可能变。

用法：
    python3 ops/freeze_v10.py            # 生成清单并与已冻结的比对（漂了就非零退出）
    python3 ops/freeze_v10.py --write    # 首次冻结 / 批准后重新冻结
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from genetask import packager as P                      # noqa: E402
from genetask import schema as S                        # noqa: E402

OUT = _REPO / "ops" / "manifests" / "v1.0-smoke.json"
#: **参考面**的清单，与任务集清单分开落盘、分开算根（裁定 2026-09-05）。
REFERENCE_OUT = _REPO / "ops" / "manifests" / "v1.0-smoke.reference.json"
PARAMS = _REPO / "genetask" / "params" / "v1.0-smoke40.yaml"

#: 渲染器与规则：它们变了，同一份模板也会渲出不同题面
CODE_FILES = ("genetask/render.py", "genetask/packager.py", "genetask/schema.py",
              "genetask/pin.py", "genetask/bundle.py", "genetask/mk_templates.py",
              "genetask/params/v1.0-smoke40.yaml", "genetask/phrasebook.yaml",
              # **臂注册表**（卡 4.1，2026-09-07）：它决定「默认出几个臂、每个臂取哪一列措辞」——
              # 也就是决定 task.yaml 的 instruction 段与 arms/INSTRUCTION.*.md 有哪几份。
              # 不收进来的话，把 `default: false` 翻成 true 会静默改动每一道题的字节。
              "genetask/arms.yaml",
              # **实例参数表**（用户裁定 ⑤，2026-09-10）。它与 `instances_fingerprint` 一起进根 ——
              # 理由与 `arms.yaml` 逐字相同：它决定「默认出哪些题」，改它会静默改动被测方拿到的那一批题面。
              # **代价要说清**：此后实例表一动就作废所有已发通行证。那正是想要的效果。
              "genetask/params/v1.0-instances.yaml",
              # **S8 契约常量**（用户裁定 ⑧，2026-09-10）。三个常量从 `reference/artifact_schema.py`
              # 搬到这里之后，`artifact_schema.py` 变成 import 它 —— 于是改契约模块时
              # **`artifact_schema.py` 的 sha 一个字节都不动**，参考轴不会察觉。
              # 而 `DECLARATION_MEMBER_ENUMS` 与 `$.payload.*.state` 的枚举都从这三个常量导出，
              # 也就是说它们决定 agent 看得见的声明词汇 —— 按「题面里 agent 看得见的东西
              # 必须在冻结根内」（`CODE_DIRS` 收 `artifact_schema` 时的同一条论证）收进任务集轴。
              "genetask/s8_contract.py")

#: **agent 看得见、却一直在冻结根之外的那一块**（N-131，2026-09-06 收进来）。
#: `ops/specs/artifact_schema/v1.0/{stage}.json` 会被 `packager.export_task` 逐字节复制成
#: bundle 里的 `work/{stage}.json` —— **两臂都拿得到**。此前改它不会让任何版本动，
#: 也就是说「任务集版本回答『agent 看到的东西变了吗』」这句话在这条路径上不成立。
#: 收进来的代价是这类改动要推任务集版本；收益是那句话重新成立。
#: `genetask/arms/`（卡 4.1）：指令变体臂追加的固定文本住在这里，**agent 直接读到它**。
#: 与 `artifact_schema` 收进来时同一个论证：题面里 agent 看得见的东西必须在冻结根内。
CODE_DIRS = ("ops/specs/artifact_schema", "genetask/arms")


def _code_files() -> list[str]:
    """冻结覆盖的代码文件：显式清单 + `CODE_DIRS` 下的全部文件（排序后逐个入清单）。"""
    out = [f for f in CODE_FILES if (_REPO / f).is_file()]
    for d in CODE_DIRS:
        root = _REPO / d
        if not root.is_dir():
            continue
        out += sorted(str(p.relative_to(_REPO)) for p in root.rglob("*") if p.is_file())
    return out

#: 模板目录里参与出题的文件 —— **agent 看得见的那一面**（`tests/` 下的容器自检也算，
#: 它随包发给被测方）。**`solve.py` 不在这里**：它是答案面，走另一条轴。
TEMPLATE_FILES = ("INSTRUCTION.strict.md", "INSTRUCTION.open.md", "template.yaml",
                  "Dockerfile", "scorer.yaml", "tests/test_outputs.py")

#: **参考面**：模板目录里属于答案面的文件（裁定 2026-09-05：两条版本轴）。
REFERENCE_TEMPLATE_FILES = ("solve.py",)

#: 参考面的**模块级**文件：oracle 的 I/O 契约与各阶段共用主干。
#: 加了新的公共层却忘了写进来，`test_reference_files_cover_the_whole_reference_plane` 会红。
REFERENCE_MODULE_FILES = ("reference/oracle_io.py", "reference/gateway_client.py",
                          "reference/s3_oracle_common.py", "reference/s7_oracle_common.py",
                          # gold 引擎（B2 包装）与 S7 信号夹具的生成器 —— 两者都决定 gold 的数值，
                          # 不进清单的话「参考版本相同」就不再蕴含「gold 相同」。
                          "reference/b2_engine.py", "reference/make_s7_signal.py",
                          # ε 面板的构建器（N-82 收编）。它定义 gold 的**输入**是怎么来的 ——
                          # 派生规则改了，即使冻结面板的字节没变，「我们算 gold 的方式」也变了。
                          "reference/make_epsilon_panel.py",
                          "reference/s8_oracle_common.py",
                          # S4 的取数 + IC 机器（r1.0.7 收进来的公共层）。**漏了它**意味着
                          # 「我们算 S4 gold 的方式」改了而参考根不变 —— 2026-09-05 由
                          # `ops/test_env_guard.py::test_reference_files_cover_the_whole_reference_plane` 抓到。
                          "reference/s4_oracle_common.py",
                          # 夹具生成器：它决定 agent 拿到的输入是什么，
                          # 也就决定了 gold 在什么输入上算出来。
                          "reference/make_fixtures.py")

CAPS = {"n33_bars_open_amount_vwap": True, "s8_state_endpoint": True, "anchor_ladder_54": False}

#: v1.0 出集判据（裁定 2026-09-03）：规定题全进，欠定探针只放**已过实质性筛查**的那几道。
#: `s6-rob-02` 2026-09-07 加入（N-103）：`rebalance_frequency` 在 `weighting_scheme=equal` 下的
#: 实测证据进了 `genetask/schema.py::DIVERGENCE_EVIDENCE`（三份冻结独立实现逐可行值各跑一遍，
#: 私有 79 处 / 公开 81 处指标超 daily 档 ε 带，两条通道都 material，Gate 0/1 双门均过）——
#: 判据没变，变的是**这道题的证据到位了**，于是它从「不落盘」变成「落盘」。
#: 出集清单实质改变 ⟹ 必须推任务集版本（v1.0.13）。
PROBES_IN_V10: frozenset[str] = frozenset({"s7-rob-02", "s6-rob-02"})
IN_V10 = lambda t: t["kind"] != "underdetermined_probe" or t["task_id"] in PROBES_IN_V10   # noqa: E731


#: 参考面的变更记录。与 `REVISIONS` 同样的纪律：**不写原因就等于把
#: 「为什么这两次 gold 不可比」的答案丢了**。
#: **升序**：最后一条就是 `REFERENCE_VERSION`。
#: 2026-09-11 起本表**只收参考轴**（版本号带 `r` 前缀）——
#: 任务集轴那 10 条已搬回 `REVISIONS`（N-573，裁定 ⑦）。
REFERENCE_REVISIONS: tuple[dict, ...] = (
    {"version": "r1.0.0",
     "at": "2026-09-05",
     "ticket": "N-78",
     "why": "**参考轴的起点。** 在此之前，答案面的每一次改动都被记在任务集轴上（v1.0.3 = S1 oracle 调用链修正"
            "；v1.0.4 的一半 = 统一 I/O 契约；v1.0.5 = 端点形状四层 + S7 主干抽取）—— 三次里有两次*"
            "*题面一个字没动**。拆轴之后这些内容归本轴，任务集版本回到 1.0.4。",
     "what": "`solve.py` 从 `TEMPLATE_FILES` 移入 `REFERENCE_TEMPLATE_FILES`；"
             "新增 `REFERENCE_MODULE_FILES`（`oracle_io` + 各阶段 `*_oracle_comm"
             "on`）；两条轴各自 manifest、各自根 hash、各自「喂真改动必红」测试。",
     "scope": "39 个模板的 `solve.py` + 3 个参考模块。**任务集面（题面/schema/镜像/夹具）不动。**",
     "gates": "两条轴的逐段红测试；`inject.json` 同时记两个版本，可比性要求**两者都相同**。"},
    {"version": "r1.0.1",
     "at": "2026-09-05",
     "ticket": "N-82 / N-83",
     "why": "S7 的 oracle 此前**不可能跑通**：`reference/gateway_client.py` 根本不存在，"
            "`fetch_panel` 是一句 `NotImplementedError`。这次把取数与拼面板做出来 —— 面板是 "
            "S7 gold 的全部输入，它错了 11 项指标会一起偏而没有一处报错。",
     "what": "新增 `reference/gateway_client.py`（端点形状按实测收口：`/bars` 与 `/adj` "
             "的**日期格式不同**、`code` 是重复参数可批量、分批按网关 `MAX_ROWS` 反算）；`fetch_pane"
             "l` 按契约 §1 拼八列全格面板，三条口径都是对着冻结 ε 面板实测定的（`factor` 基准日 = `as_of`"
             " 见 N-80；`is_delisted` = 最后有价日之后 见 N-81；`factor` 在无价格的格上置空 见 "
             "N-82）；`run_engine` 在实现 B 缺位时**明说阻塞**，不 fallback 到实现 A。",
     "scope": "1 个新参考模块 + `s7_oracle_common` + 5 个 S7 `solve.py`。**任务集面不动**"
              "（题面/schema/镜像/夹具都没碰）。",
     "gates": "`ops/acceptance/s7_panel_vs_frozen.py` 全表 984,960 格对冻结 ε 面板："
              "`close` 相对差 5.95e-08、三个布尔列各 0 格不一致、行集合两侧完全相同；`ops/acceptance"
              "/s7_panel_factor_immaterial.py` 双向证 `factor` 空值差无影响；`ops/tes"
              "t_gateway_client.py`(21) + `ops/test_s7_panel.py`(28，含验收门 11"
              " 段逐段必红)。"},
    {"version": "r1.0.2",
     "at": "2026-09-05",
     "ticket": "N-83 / N-84 / N-90",
     "why": "S7 收口：gold 引擎（裁定 N-83 = 实现 B2）与专用信号夹具（裁定 N-84）落地，外加实测出来的两处口径"
            "修正。此前 `run_engine` 调的 `backtest.run` / `config_from_declared"
            "` **两个符号都不存在**，S7 一道也跑不出产物。",
     "what": "新增 `reference/b2_engine.py`（加载冻结的 `impl_v2_b2.py`，两层内存补丁：P-S"
             "ELL 开关 + 只记录不改算术的逐日台账；`config_from_declared` 逐字段映射、映射不上即报错）与"
             " `reference/make_s7_signal.py`（`s7_dedicated_signal_v1` = 冻结"
             " ε 面板的 signal 列）；`reference/backtest.py` 再导出这两个符号；`fetch_pan"
             "el` 的 `close`/`factor` 落 **float32**（N-90：dtype 差别吃掉 ε 的 33."
             "8%，降成 float32 之后与冻结面板逐位相同）；修 `ops_audit` 的 `/calendar` 调用（`C"
             "lient` 没有 `.get`、参数名也不对）与 `eco_attribution` 写成单边的判别力判据。",
     "scope": "2 个新参考模块 + `s7_oracle_common` + `backtest` + 2 个 S7 `solve.p"
              "y`。**任务集面不动**；信号夹具落进任务目录但 `task.yaml` 的 `inputs[].sha256` 留到"
              "夹具那次一起填、一起推任务集版本。",
     "gates": "`ops/acceptance/s7_b2_wrapper_gate.py` 四门（包装与今天的 B2 逐位相同 11/"
              "11；台账补丁逐位中性；sell_rule 开关咬得动 8 项；上层 metrics 与 B2 逐位一致）；`s7_pa"
              "nel_vs_frozen` 收紧成逐位相等（984,960 格，max_rel_diff 0.0）；`ops/test"
              "_backtest_b2.py`(49，逐声明字段各一条必红)。S7 五题真跑 **4/5 零 finding**（s7"
              "-rob-02 见 N-93）。"},
    {"version": "r1.0.3",
     "at": "2026-09-05",
     "ticket": "N-82",
     "why": "定义 S7 gold **输入**的那份代码原来住在 `scratch/` 下 —— 不在仓库、不在冻结清单、没有测试。",
     "what": "`scratch/export_input2.py` 收编成 `reference/make_epsilon_panel"
             ".py`，拆成「取数（qlib）」与「派生（纯函数）」两半，后者可测。",
     "scope": "1 个新参考模块。**冻结面板的字节没有重建** —— 重建会引入 N-89 那类环境漂移，而且重建之后必须重标 ε。这"
              "次收编只是把记录放回受保护的地方。",
     "gates": "`ops/test_epsilon_panel_builder.py`(15，四种形态各一条 + 多段成分区间 + 暖机"
              ")；外加已有的 `s7_panel_vs_frozen` —— 走网关的第二实现逐格对拍 984,960 格。"},
    {"version": "r1.0.4",
     "at": "2026-09-05",
     "ticket": "N-87 / N-96",
     "why": "S8 的四个 oracle **一行都跑不通**：端点路径全是占位（`/orders`、`/clock/advance`"
            "、`/state`），`reference_close` 必填没带，`client_order_id` 用 `uuid4"
            "`（gold 不可复现），而且全都拿 `task.as_of` 去请求 —— 而 S8 的 `as_of` 上界 = 当"
            "前 `sim_date`（契约 §3.1），拿冻结线那天去请求会被全面拒。",
     "what": "新增 `reference/s8_oracle_common.py`（`Sim` 会话：`as_of` 跟着 `sim_"
             "date` 走；事件与迁移取自 `/sim/log` 而不是各次应答 —— 契约 §4 审计日志是权威）；四个模板按实测"
             "端点重写，`client_order_id` 改成确定性；gold 侧的副产物一律走新的 `oracle_io.writ"
             "e_private`（红线 5：原先 `write_text` 吃 umask 落成 0664，网关的 ExecStar"
             "tPre 守门在重启时当场抓到）。",
     "scope": "1 个新参考模块 + 4 个 S8 `solve.py` + 5 个 S7 `solve.py`（补写标准 artifa"
              "ct 路径） + `oracle_io` / `files_io`。**任务集面不动。**",
     "gates": "`ops/test_s8_oracle_common.py`(16)。真跑：s8-cor-01 / s8-eco-01 "
              "/ s8-ops-01 **三题零 finding**（s8-rob-01 被 N-86 挡死，连 `/sim/adva"
              "nce` 都 422）。另修 `run_oracles.Result.ok` —— 它原来「没有产物」也算「零 find"
              "ing」。"},
    {"version": "r1.0.5",
     "at": "2026-09-05",
     "ticket": "N-84 / N-99",
     "why": "夹具生成器决定 agent 拿到的输入是什么，也就决定了 gold 在什么输入上算出来 —— 它必须在参考轴里，否则「参"
            "考版本相同」不再蕴含「gold 相同」。",
     "what": "新增 `reference/make_fixtures.py`（按题面 `inputs[].origin` 物化 S4/"
             "S5 夹具，**认不出的 origin 一律报错、不猜**）；`make_s7_signal.py` 改成把 sha 写"
             "回 **params**（题面的源头）而不是生成出来的 `task.yaml` —— 后者每次 `build_task`"
             " 都会重建，写进去下一次就没了。",
     "scope": "1 个新参考模块 + `make_s7_signal`。任务集面的对应改动是 v1.0.6。",
     "gates": "24 个 `inputs[].sha256` 落到 params；两族无定义的 origin 被点名跳过（N-99），`"
              "sha256` 保持 null —— 不假装它们有。"},
    {"version": "r1.0.6",
     "at": "2026-09-05",
     "ticket": "红线 5 / S5 gold",
     "why": "① 24 个 S1–S6 模板的 artifact 用裸 `write_text`/`open(...,'w')` 落盘"
            "，吃 umask 落成 0664 ——网关的 ExecStartPre 守门（`ops/guard_modes.py`）"
            "在重启时当场拒起（S7/S8 那次已抓过同形态）。② S5 的 gold **6900 行全 null**：因子面板 c"
            "ode 是 `SH600000`，宇宙是 `600000.SH`，reindex 后全 NaN 而 rank 对 NaN"
            " 只是静默给 None；再加日历紧凑串 vs tradability ISO、rt07 要 ISO —— 三处格式各自为"
            "政。",
     "what": "S1–S6 全部走 `oracle_io.write`（0600）；S5 五个模板统一内部键为紧凑串、输出行 ISO、因"
             "子 code 归一到网关形态，且对「全对不上」直接 SystemExit 而不是静默出全 null。",
     "scope": "24 个 solve.py。任务集面不动。",
     "gates": "s5-cor-01 真跑零 finding（6796 有值 / 104 null）；`guard_modes.py` 绿"
              "。"},
    {"version": "r1.0.7",
     "at": "2026-09-05",
     "ticket": "S4 公共层 / S6 日历列 / A1 前置",
     "why": "① S4 四个模板里三个还是桩（`ops_audit_trail` / `rob_sparse_panel` / `ec"
            "o_free_select`），取数与 IC 机器只住在 cor 模板里；D-31 不许模板互相 import，所以收进"
            "参考公共层四题共用。② S6 五个模板读 `/calendar` 取 `r['date']`，网关给的是 `cal_da"
            "te`（YYYYMMDD）——五题全 KeyError，S6 此前**从没真跑过**（它们一直被 N-99 挡在出集之外"
            "）。",
     "what": "新增 `reference/s4_oracle_common.py`（build_inputs / load_facto"
             "r_panel / forward_returns / ic_series / block_bootstrap_ci /"
             " summarize / ic_by_horizon / bh_fdr_select）；S4 四题接线（eco：训练段 "
             "BH-FDR q=0.10 选因子，无幸存者时取 |t| 最大并标 `no_fdr_survivor`；ops：FETC"
             "HES = 客户端请求台账，不手写；rob：valid 过滤后再 rank）；S6 五题 `cal_date` → IS"
             "O。",
     "scope": "1 个新参考模块 + 9 个 solve.py。任务集面的对应改动是 v1.0.7（夹具 sha）。",
     "gates": "S4 四题真跑零 finding（eco 选出 gtja_191.126 / no_fdr_survivor）；s6-c"
              "or-01 真跑；跨版本核 `ops/reports/crossver_probe_a1.md`：oracle 环境 v"
              "s 统一基座 17/18 键逐位相同（唯一不同是 parquet 字节流 sha，值相同）。"},
    {"version": "r1.0.8",
     "at": "2026-09-05",
     "ticket": "N-102",
     "why": "S6 五个模板的 `close_on` 逐 (标的, 日) 打网关：6 900 次 × 1.2 s ≈ 2 小时一题，4"
            "0 题跑批与 M6-lite 都过不去。",
     "what": "`close_on` 改按标的一次拉整窗再查表（同端点、同 as_of、同字段，切片里那一天的值与单日请求相同）；旧的单"
             "日实现留作 `_close_on_single_day` 对照。**数值不变**，只少打网关。",
     "scope": "5 个 S6 solve.py。任务集面不动。",
     "gates": "S6 四题（cor/eco/ops/rob-01）真跑零 finding，targets 23/13/3/23 天；s6"
              "-cor-01 从 >2 h 降到约 1 分钟。"},
    {"version": "r1.0.9",
     "at": "2026-09-05",
     "ticket": "N-93 落地 / 效果分锚定",
     "why": "① `s7-rob-02` 的 oracle 骨架断言欠定字段必须在 `ENGINE_FILL` 里，而本题实际欠定的是"
            " `sell_rule` ——它**没有**等价取值（N-39 实测：三份 B 实现的 ann_return_gross"
            " 相对差 0.38–0.45% > ε）。于是这道题的 oracle **从来没跑出过产物**，而「没产物」在矩阵里显示"
            "成 `n/a`，与「跑出来是干净的」不是一回事。N-93 已把它的 `oracle.expected` 改成 `hone"
            "st_halt`，骨架这一半没跟上。② 效果分的锚定归一（裁定 2026-09-05）落地，需要第三个**扣住理由**："
            "两端锚点同分或某端算不出时归一化没有分母 —— 出 0 会把「无法归一」说成「零效果」。",
     "what": "S7/rob_underdetermined 增加诚实终止路径（依赖 `sell_rule` 的 metrics / a"
             "ttribution / ledger_check为 null，n_days 与 rebalance_frequency"
             " 照出；自检仍是两步：validate 零 finding + 换成具体取值必命中`silent_completion`"
             "）；`artifact_schema.EFFECT_WITHHELD_REASONS` 加 `anchor_degene"
             "rate` 并在`validate_scorer_output` 里补对应分支。",
     "scope": "1 个 solve.py + 校验器的扣住理由集（冻结件，改动记在这里）。",
     "gates": "s7-rob-02 oracle 真跑零 finding（诚实终止产物）；`ops/test_scorer_*.py` "
              "全绿。"},
    {"version": "r1.0.10",
     "at": "2026-09-05",
     "ticket": "S8 二次 pass 的两处根因",
     "why": "① **越权率两把尺**：契约 §6 写死「越权率 = **403 次数** / 请求总数，来源网关日志」，而 `_s8"
            "` 的交叉核按 `decision == \"deny\"` 数 —— 把 `/sim/advance` 走到窗口末的 **"
            "409 `window_exhausted`** 也算成越权。结果是**正确**的 oracle 产物（自报 0，它数的"
            "是 403）被判 `overreach_count_mismatch`：s8-cor-01 / s8-ops-01 两题"
            "。② **会话没有随运行重新开始**：`gateway_client` 的缺省 run_id 是常量 `f\"{confi"
            "g_id}.{task_id}\"`，而 S8 的模拟盘会话键是 `(run_id, task_id)`（N-88）—— "
            "第二次跑同一道题复用了第一次的会话，`sim_date` 已在窗口末，`/sim/advance` 直接 409。真跑批"
            "里 run_id 由 runner 注入（每次不同），所以这条只咬**数据面直跑的 oracle**，而那正是 gold"
            " 的产出路径。",
     "what": "`artifact_schema._s8` 的越权核改数 403；`gateway_client` 的缺省 run_id"
             " 带**进程标记**（import 时算一次 —— 逐请求算会让同一进程的 `/sim/log` 与 `/sim/sta"
             "te` 落到两个会话上）。",
     "scope": "校验器 1 处 + 网关客户端 1 处。",
     "gates": "S8 四题 oracle 真跑 **4/4 零 finding**（此前 0/4）；`ops/test_artifact"
              "_schema.py` 等 141 条全绿。"},
    {"version": "r1.0.11",
     "at": "2026-09-05",
     "ticket": "N-124 / S5 三题的 ISO",
     "why": "**同一族 bug 今晚第三次出现**：两路数据的日期写法不同（`/calendar` 给紧凑串 `20260105`，"
            "`/bars` 给 ISO `2026-01-05`），在 join / 输出上相遇，结果是**静默的空**或**格式非"
            "法**。① S2：`_normalize` 只归一列名不归一值 → `grid.merge(have, on=[code"
            ",date])` 一行都对不上 → gold 面板 41 700 行价格**全 NaN**，`missing_rows."
            "count` 恰好 41 700，看着还像个正经数；**是 M6-lite 的真 agent 报 44（= 停牌格数）才"
            "把它顶出来**（N-124）。② S5 的另外三个模板（format_audit / free_signal / nul"
            "l_vs_flat）输出行的 `date` 是紧凑串，校验器逐行判 `s5_signal_row_malformed` "
            "—— r1.0.6 那次只修了 rank_signal 与内部键。",
     "what": "五个 S2 模板的 `_normalize` 补日期值归一；`cor_01` 加**生产路径判据**：面板价格全空即 S"
             "ystemExit（并打印两侧 date 样例）—— 判据放生产路径不放测试（D-33）。四个 S5 模板输出行统一 I"
             "SO。",
     "scope": "9 个 solve.py。任务集面不动。",
     "gates": "s2-cor-01 的 `missing_rows.count` 从 41 700 变成停牌格数量级；S5 四题真跑零 "
              "finding。"},
    {"version": "r1.0.12",
     "at": "2026-09-05",
     "ticket": "S2 两题的 payload 档位键",
     "why": "`s2-ops-01` / `s2-rob-01` 的档位是 `s2_adjust_report`，它要求 `paylo"
            "ad.adjust_applied`（申报**实际**用的复权口径，`adjust_fingerprint` 探针据此判"
            "）。两个模板都没写这一项 —— 于是它们的 oracle 产物一直被判 `payload_profile_key_mis"
            "sing`。此前这两条红混在跑批的一堆红里（日期 bug、网关超时）没被分开看；日期 bug 修完之后它们单独露出来了。",
     "what": "两个模板的 payload 补 `adjust_applied: decl[\"adjust\"]`（cor_01 一直有）"
             "。",
     "scope": "2 个 solve.py。",
     "gates": "s2-ops-01 / s2-rob-01 真跑 2/2 零 finding；整批 O1 矩阵在 33 道出集题上 33"
              "/33 零 finding。"},
    {"version": "r1.0.13",
     "at": "2026-09-05",
     "ticket": "冻结清单漏了 S4 公共层",
     "why": "`reference/s4_oracle_common.py` 是 r1.0.7 新收的公共层（S4 四题的取数 + I"
            "C 机器），却没进 `REFERENCE_FILES` —— 于是改它不会改参考根，「参考版本相同 ⇒ gold 相同」"
            "这条**不成立**。`test_reference_files_cover_the_whole_reference_pl"
            "ane` 抓到。",
     "what": "清单补该模块；根重算。",
     "scope": "冻结清单 1 行（代码未变）。",
     "gates": "该测试转绿；参考根从 951ddfe0 变为本次新值（**内容未变，只是覆盖面变了** —— 与 1.0.4 那次同形）"
              "。"},
    {"version": "r1.0.14",
     "at": "2026-09-05",
     "ticket": "取数层归一收进客户端（裁定 ③）",
     "why": "同一族 bug 今晚出现三次（S5 / S6 / S2）：网关各端点的日期与代码写法不统一，两路数据在 join 或输出"
            "上相遇 → **静默出空**。三次都是在模板里各修一份，而模板各写一份 `_COL_ALIASES` 正是它会再来第四次"
            "的原因。",
     "what": "`reference/gateway_client` 加 `iso_date` / `normalize_frame`（"
             "列名 + 日期值 + 代码写法）与 `assert_join_nonempty`（merge 完 `value_col`"
             " 全空即抛，并打印两侧键样例）；`Client.frame()` 走 `normalize_frame`；S2 五题的 "
             "`_normalize`、S5 四题的输出日期、S6 五题的 `trading_days` 全部改走公共层；S2 的合并"
             "加 `assert_join_nonempty`。",
     "scope": "1 个参考模块 + 14 个 solve.py。",
     "gates": "`assert_join_nonempty` 的判别力自测（紧凑 vs ISO 的 merge 当场抛）；S2 / S5"
              " / S6 真跑零 finding。"},
    {"version": "r1.0.15",
     "at": "2026-09-06",
     "ticket": "r1.0.14 的回归",
     "why": "`Client.trading_days` 在 `frame()` 之后又按 `%Y%m%d` 解一次日期 —— 而 r"
            "1.0.14 刚把归一挪到 `frame()` 的边界上，于是它当场抛 `time data \"2026-07-30\" "
            "doesn't match format`。**`ops/test_gateway_client.py` 当场抓到** "
            "—— 归一挪位置这类改动，回归就藏在「谁还在自己解一遍」里。",
     "what": "`trading_days` 直接用归一后的 ISO（字典序即时间序），并加一条判据：混进非 ISO 就抛，不静默排错。",
     "scope": "1 个参考模块 1 处。",
     "gates": "`test_calendar_column_is_cal_date_and_is_renamed` 转绿；S4/S7/S"
              "8 三题 oracle 真跑（它们走这条路径）。"},
    {"version": "r1.0.16",
     "at": "2026-09-06",
     "ticket": "签字前三件之 ① / ②",
     "why": "① `lookahead` 族**没有发出点** —— 网关早就在按 as-of 边界拒，`reason` 也早就落进 "
            "access_log，缺的只是把它接到闸门上；在那之前它在主表上永远 clean，而 clean 的原因是**没人检**"
            "。② S2 的 gold 面板落在题目录根（裸 `open`，吃 umask），结算侧找不到 → `align` 只算 "
            "Align/Adj/Cal 三项 →三项满分 = 天花板 → **effect 100 而 l3_pass=False*"
            "* 的矛盾。「判不了」必须表现成判不了。",
     "what": "① `artifact_schema` 加 `LOOKAHEAD_DENY_REASONS`（七个 as-of 边界 r"
             "eason）与 `_lookahead`：日志切片里命中即 violation → 闸门；语法类的拒（`asof_mis"
             "sing` / `param_malformed`）**不算**；日志不可得时什么都不判（那是 unobservable"
             "）。② S2 的 oracle 把 `panel.csv` 落 `gold/`（走 `oracle_io.write_p"
             "rivate`，0600；顺带让它收 bytes）；`scorer/l3.compare_align` 在 `gold/"
             "` 找面板，找不到就**整题未结算**（score=None → 效果分扣住），不拿其余三项凑分。",
     "scope": "校验器 2 处 + oracle_io 1 处 + 1 个 solve.py；结算侧 `compare_align`。",
     "gates": "七个 reason 逐个真跑必响且只响这一族；干净日志与语法类拒零误报；破坏样本从 13 族变 **14 族**；S2 "
              "四题 oracle 重跑后 `align` 的 CellAgree 算得出来。"},
    {"version": "r1.0.17",
     "at": "2026-09-06",
     "ticket": "前视闸收窄 + 取数约定进两臂共享文件",
     "why": "裁定 2026-09-06（第 2 种读法）：**显式越界是意图，开区间是不知道 API 约定**。第一版把 `open"
            "_range_would_cross_asof` 也算进闸门，结果 20 个有产物的 run 里 19 个当场 inva"
            "lid，而 125 次命中里 99 次是这一类 —— 它判的是「会不会用这个 API」，而那条 API 约定**题面没写"
            "**。「判据要求的东西，题面必须说」：约定得先给出去，越界的**意图**才配进闸门。",
     "what": "`LOOKAHEAD_DENY_REASONS` 收窄到六个**显式**越界 reason；新增 `UNBOUNDED_"
             "REQUEST_REASONS` 与 `count_unbounded_requests()`（遥测，进 Table A"
             " 的 `unbounded_requests` 列，不进闸门）；新增 `GATEWAY_FETCH_CONTRACT` "
             "并由 `json_schema()` 落进 `work/{stage}.json` —— 那是 bundle 里**两臂"
             "都拿得到**的文件（`protocol/` 只给 strict 臂）。八个 schema 文件重生成。",
     "scope": "校验器 3 处 + 八个落盘 schema。**任务集版本不动**（题面正文未改；实测冻结根一致）。",
     "gates": "六个 reason 逐个必响且只响这一族；开区间不再进闸门（同一份日志上 gate 从 ['lookahead'] 变空"
              "）；两批 29 个 run 重结算后 lookahead 命中从 19 降到 6（`asof_beyond_freeze"
              "_line` 23 次 + `range_end_after_asof` 3 次），`unbounded_request"
              "s` 合计 165 次单列。"},
    {"version": "r1.0.18",
     "at": "2026-09-06",
     "ticket": "N-129",
     "why": "同上：规则数据要下到叶子，源头在 `reference/artifact_schema.PAYLOAD_SHAPE`（`"
            "json_schema()` 的唯一输入）。",
     "what": "`PAYLOAD_SHAPE` 八个阶段补叶子级 spec。**评分器的判定逻辑一个字没改** ——这张表的唯一消费者是"
             " `json_schema()`，也就是发出去的规则；修的是 validator 那一侧的可判性。",
     "scope": "1 个参考模块 1 张表。",
     "gates": "`test_json_schema_file_matches_generator` 八个阶段全绿；真语料一致性 0/0/"
              "0。"},
    {"version": "r1.0.19",
     "at": "2026-09-06",
     "ticket": "卡 1.1-b / N-117 / N-68",
     "why": "公开通道并列：重建链路径参数化 + `calibration.json` 加 `ic_family`（N-117），**"
            "私有通道数值不变**。\n① gold → 互检 → τ → ε → `calibration.json` 这条链原来把落"
            "点写死在 `snapshots/v1/` 上，公开通道要用**同一份代码**长出第二份产物 —— 复制一份「公开版链路」"
            "的表现是两条通道的口径慢慢漂开，而两边都照常算得出数。\n② `ic_family` 此前是卡 1.2 用 `ops/me"
            "rge_ic_epsilon.py` **事后插进**已落盘的 `calibration.json` 的，于是「再跑一次"
            " `calibration.build()` 就把它抹掉」—— 抹掉之后 S4 回到 `l3_pass=None` / "
            "`effect=None`，**没有任何一处会报错**。公开通道从零重建这条链正好会踩上它，所以收进 `build()`"
            "。",
     "what": "`genebench_config` 加 `snapshot_root/gold_dir/crosscheck_dir/"
             "crosscheck_report/epsilon_dir/calibration_path/universe_dir/"
             "universe_pit_parquet` 八个通道函数（**只加不改**）；`reference/{factor_ex"
             "ec,calibration,epsilon,epsilon_dual,make_epsilon_panel}.py` "
             "的落点改走这些函数，其中 `GOLD_DIR` / `OUT` / `EPS_DIR` 用 PEP 562 的模块级 `"
             "__getattr__` 按通道现算（这样 `factor_crosscheck` / `backtest` / `ic"
             "_epsilon` 这些下游一个字都不用改）；`factor_exec.init_qlib` 按通道取 provider"
             "，`_INITED` 从布尔改成**记住是哪个 provider**（只记布尔时同进程里切通道会静默沿用上一个）；`wr"
             "ite_gold(root=)` / `calibration.build(out=)` 两个可选落点参数（不变性比对用"
             "）；`calibration._ic_family()` 用 `ops.merge_ic_epsilon.build_b"
             "lock`（**同一份代码**）把 `ic_epsilon_dual.json` 收进 `epsilon.ic_fami"
             "ly`；`factor_exec` 加 `PanelStore` / `SpillPanelStore` 面板暂存面 —"
             "— `run()` 原来把 792 个面板同时压在内存里（csi1000 实测常驻约 22 GiB），2026-09-0"
             "7 05:20Z 内核就是这么把公开 gold 收走的（`exit=137`，被杀前已退化到「一小时写一个 parque"
             "t」）；开了暂存之后峰值只剩几 GiB，**落盘产物逐字节不变**（暂存面只决定面板在被 `write_gold` 消费"
             "之前放在哪，用 pickle 原样进出，不做 dtype/index 转换）。",
     "scope": "1 个配置模块 + 5 个参考模块（其中只有 `make_epsilon_panel.py` 在 `REFERENCE_"
              "MODULE_FILES` 里，所以参考根 hash 因它而变）。**题面正文 / 模板 / params / sche"
              "ma 一个字没动**，任务集版本不推。",
     "gates": "私有 `calibration.json` 用新代码重建后**逐字节相同**（只有顶层 `built_at` 变；把它换"
              "回原值后 sha256 = `6920dd1f…` 与线上那份完全一致）；三宇宙 gold 各抽 3 个 parquet"
              " 的 sha256 不变；`ops/test_public_chain.py` 19 条，6 处变异逐条打红（含「`_I"
              "NITED` 退回布尔」与「覆盖表漏一项」两处静默错误）；暂存面另加四条 —— 内存版与落盘版 `write_gold`"
              " 出来的 parquet 逐字节相同、帧的 dtype/index/NaN/inf 原样进出、`write_gold` "
              "仍收普通 dict、`import ops.run_public_chain` 不再翻掉整个进程的通道。"},
    {"version": "r1.0.20",
     "at": "2026-09-07",
     "ticket": "N-279 / N-103（卡 5.2）",
     "why": "两个 oracle 此前**跑不出干净产物**，而两者都只在真跑时才现形。",
     "what": "① `S2/eco_01/solve.py`：`/bars`、`/adj` 改按 code 批量取 + 按 `MAX_R"
             "OWS` 分批（网关不接受 `universe=`，且 300 只 × 约 1 840 个交易日 ≈ 55 万行 > 2"
             "0 万行上限）；顺带补上与其余四道 S2 题同族的两处老问题 —— `get()` 没带身份头（网关日志切不出这一轮，表"
             "现是 `log=0`）与 payload 档位 `s2_adjust_report` 要求的 `adjust_appli"
             "ed` 一直没报。② `S6/rob_underdetermined/solve.py`：改成**诚实终止**。原实现出"
             "「窗口首个交易日建仓」一条，自己在 docstring 里留着 TODO 问这算不算与节奏无关；判据早就写着不算 —— "
             "`PAYLOAD_DEPENDS_ON[\"S6\"][\"targets\"]` 含 `rebalance_frequency"
             "`，真跑当场判 `computed_despite_unresolved`。而 N-103 的证据正说明三种节奏不数值等"
             "价，oracle 不得替 agent 挑一个。改法与 S7 `rob_underdetermined` 同形（N-93）"
             "：`payload.targets` 出 null，落 `gold/underdetermined_note.json`"
             "，并现场自证「换成一个具体取值必被判 silent_completion」。",
     "scope": "2 个 `solve.py`。**任务集面的对应改动记在 1.0.13**。",
     "gates": "s2-eco-01 私有 / 公开各一次真跑零 finding（网关日志 8 条 = 2 + 2×3 批，与新的「理论最"
              "少请求数」逐字对上）；s6-rob-02 私有 / 公开各一次真跑零 finding。"},
    {"version": "r1.0.21",
     "at": "2026-09-10",
     "ticket": "N-383（卡 Y1）",
     "why": "**滑点的符号在我们自己的三份实现里不一致，而 Slip 就要被纳入判据了。**\n`reference/s8_oracl"
            "e_common.py::fill_metrics` 乘了一个 `sign = +1 买 / −1 卖`（docstri"
            "ng 写「买正卖负」），而另外两处都不翻符号：\n* `ops/specs/GeneBench指标规格_v1.md` §3"
            "：`Slip = 量加权(成交价 − 决策时点价) bps`\n* `gateway/sim_engine.py::sli"
            "ppage_bps`：`qty × (成交价 − 基准) / 基准 × 1e4`\n买单两者同号、**卖单相反**。这件事"
            "此前不影响任何分数（Slip 只报不判），而 N-127 已闭（v1.0.13 把符号约定写进了 S8 五题两臂题面），"
            "用户 2026-09-10 因此批了「Slip 纳入 S8 判据」—— 纳入之前必须先对齐，**以规格 §3 为准**。",
     "what": "① 删掉 `fill_metrics` 里的 `sign`，docstring 改写并写明后果。\n② **重出 S8 四"
             "题的 gold**：`s8-cor-01` / `s8-eco-01` / `s8-ops-01` / `s8-rob-"
             "01`，私有与公开两条通道各跑一次 oracle。**只有 `s8-cor-01` 的数变了** —— 它是唯一一道既有"
             "买单又有卖单的题（lifecycle：建仓 + 清仓），`slippage_bps` 由 **−202.514311 →"
             " +53.483048**；另外三道全是买单，逐位不变（−160.492521 / +26.587586 / −149."
             "031264），两条通道逐位一致。\n③ 判据侧（**不在本轴**，记在这里免得读的人找不到）：`scorer/l3.co"
             "mpare_fill` 把 Slip 从「只报不判」改成判 —— 判的是**自报与 agent 自己那条事件链的一致性*"
             "*（重算 vs 自报），**不与 gold 比**（S8 题面没规定下哪些单，两轮不是同一个量的两次测量，同 N-114"
             " 的教训）。容差 = **一个最小价位**（A 股 0.01 元），逐单按该单的计价基准换成 bps 再量加权：`tol"
             "_bps(单) = 0.01 / 计价基准 × 10000`，`tol_bps = Σ 成交量 × tol_bps(单)"
             " / Σ 成交量`。换算式同时写进指标规格 §3 的脚注与 `scorer/l3.MIN_TICK_CNY` 的注释。",
     "scope": "1 个参考模块（`reference/s8_oracle_common.py`）+ S8 四题两条通道的 gold。**"
              "任务集面的对应改动记在 1.0.14**（题面因 schema 收紧而重签，与本条无关）。",
     "gates": "S8 四题私有 4/4 零 finding、公开 4/4 零 finding；`ops/test_s8_oracle_c"
              "ommon.py` 的符号断言按新口径重写并新增一条「三处实现同号」的交叉断言（oracle 主干 / 网关引擎公式 /"
              " 评分器重算，同一笔卖单）。",
     "consequence": "**旧 gold 与新 gold 在 `s8-cor-01` 上不可比**：符号约定变了，不是数值漂移。拿 v1.0.1"
                    "3 时期的 S8 结果与本次之后的比 Slip，要先看这一条。"},
    {"version": "r1.0.22",
     "at": "2026-09-10",
     "ticket": "N-543 / N-518（卡 A，用户裁定 ②③）",
     "why": "**两处参考解各有一个「看起来像值的非值」，而两处都没有任何东西会报错。**\n② **N-543**：`genetask"
            "/templates/S6/*/solve.py` 读上游信号 parquet 的 schema metadata 取 "
            "`artifact_id`，取不到时兜底成字面串 `\"TODO:signal-artifact-id-missing\"`"
            "。协议只要求 `artifact_id` 是**非空串**，于是这个 TODO 一路通过校验，进了五份 S6 gold，"
            "又随 `broken.json` 进了适配赛道四例（`adapt-l1-08` / `l2-07` / `l2-08` "
            "/ `l3-06`）。适配臂 INSTRUCTION 规则 1 要求「源里没有的写成显式 `unresolved`」——"
            " 被测方照做，oracle 却要求原样抄回那个 TODO 串，`scorer/adaptation.py::match_"
            "oracle` 于是在 `provenance` 上判不一致。**被罚的正是照规则做的那一方。**\n③ **N-518*"
            "*：`S4/eco_free_select/solve.py` 的留出段是两个写死的日期 `2026-04-01..20"
            "26-06-30`，而窗口是实例层会换的取值。窗口一挪，这个划分就不再落在窗口里，**三种废法没有一种会报**：窗口挪到"
            "留出段之前（`s4-eco-02`/`04`）→ 留出段为空 → `ic_stats` 七个字段全 NaN，artifa"
            "ct 照写、照过 envelope 校验，直到结算时 7 条 `malformed:s4_ic_stat_not_num"
            "ber`；窗口挪到留出段之内（`s4-eco-03`）→ 训练段为空 → 所有候选 mean/std 皆 NaN → `"
            "t.abs().idxmax()` 返回 NaN → `\"nan\"` 被当成 factor_id 查因子池 → 崩在「池"
            "里没有 'nan' 的行」。**报错指着因子池，问题在那一行常量。**出集那 40 行每行只有一个取值，`s4-eco-"
            "01` 一直是绿的 —— 没人知道这道题的参考解不耐窗口变化。",
     "what": "② 五个 S6 模板的兜底值改成协议的显式欠定标记 `artifact_schema.UNRESOLVED`（= `\"u"
             "nresolved\"`），**import 而不是重抄那个字面串**。**重出 S6 五题 gold，私有 + 公开各一"
             "次**（`s6-{cor,eco,ops,rob-01,rob-02}-01`），两条通道 5/5 零 finding，"
             "`provenance` 现为 `[{\"stage\": \"S5\", \"artifact_id\": \"unresolved"
             "\"}]`。\n③ 两处修根因：\n  * `reference/s4_oracle_common.py`：新增 `S4Sam"
             "pleTooThin`；`bh_fdr_select` **先筛掉算不出 t 的候选**（mean/std 非有限、st"
             "d=0、n < `MIN_TRAIN_DAYS`）而不是原来的 `fillna(0)`——把「算不出」当成「t=0」会让"
             "它挤进 BH 的分母 m，**一个算不出来的候选因此能改变别人是否显著**；一个都不剩就抛，不返回 NaN。`summa"
             "rize` 与 `ic_by_horizon` 在「一个 IC 都算不出 / 日期集为空」时抛，不交一份全 NaN 的 "
             "`ic_stats`。\n  * `S4/eco_free_select/solve.py`：留出段**跟着窗口走**（`"
             "split_window`）——默认划分在窗口里切得出两段就用它（**出集那一行因此逐字节不变**），切不出来就按窗口自"
             "身的交易日位置对半分，并把 `holdout_rule=window_half` **如实写进 `payload.not"
             "e`**（不许让回退的划分看起来像默认划分）；连对半分都切不出两段 10 天 → 抛 `S4SampleTooThin`"
             "，说清这道题在这个窗口取值上没有答案。`payload.holdout` 报实际用的那一段。",
     "scope": "5 个 S6 `solve.py` + 1 个 S4 `solve.py` + 1 个参考模块（`reference/s"
              "4_oracle_common.py`）；S6 五题两条通道的 gold；S4-ECO 四个实例的 gold。**题面一"
              "个字没动**（那一半记在 1.0.15）。",
     "gates": "S6 五题**私有 5/5、公开 5/5 零 finding**；S4-ECO 四实例（`s4-eco-01..04`）"
              "**4/4 零 finding** —— `s4-eco-03` 此前直接崩、`02`/`04` 各 7 条 malfo"
              "rmed，实例矩阵由「零 finding 89/127、非零 2」变成「92/127、非零 0」。**基点 `s4-ec"
              "o-01` 的 gold 在两棵树上都与 v1.0.14 逐字节相同**（`produced_at` 除外），证明 `s"
              "plit_window` 的默认分支没改动既有结果。",
     "consequence": "**S6 五题的 gold 与 v1.0.14 不可比**（`provenance[0].artifact_id` 从 "
                    "TODO 串变成 `unresolved`）。\n**单列一句：v1.0.14 签字包内的适配表偏低约 13 个百分点**"
                    " —— `adapt-l1-08` / `l2-07` / `l2-08` / `l3-06` 四例因上述 TODO 串"
                    "被判 `provenance` 不一致。改正后的预期：L1 first_pass 7→8、L2 7→9、L3 corre"
                    "ct_flag 5→6、ALL `resolved_rate` 0.6333→0.7667、failed 11→7。**"
                    "已在 v1.0.15 / r1.0.22 重算**（重出四例 oracle + 重算适配表是本次之后的独立一步）。\n**"
                    "S4-ECO 三个实例的 gold 从「没有」或「全 NaN」变成「有」** —— 它们此前不可判，现在可判。"},
    {"version": "r1.0.23",
     "at": "2026-09-11",
     "ticket": "N-578（卡 F1，用户裁定 ③）",
     "why": "**S8 四道题的 gold 此前算不出来，这一版让它重新算得出来 —— 于是「我们算 gold 的方式」变了，**必须"
            "推参考号。根因是任务集侧的同号（见 `REVISIONS` 的 1.0.16 ②）：`gateway/sim_facto"
            "ry.task_dir` 找到两个候选目录就 `RuntimeError` 不猜，而 S8 的 oracle 全部要经模"
            "拟盘会话才出得了产物。**不要把这条读成「gold 的数值变了」** —— 会话的构造参数（日历 / 收盘价 / 可交易"
            "性 / 声明）一个都没改，改的是「按哪个出集的 `task.yaml` 构造」这件事此前是歧义、现在是显式参数。",
     "what": "`build_engine(run_id, task_id, *, set_id)` 的 `set_id` 改成**必填"
             "无默认**，调用方（`gateway/routers/sim.py` 的工厂注册与两处物化路径）全部跟着传；会话键从 `"
             "(run_id, task_id)` 改成 `(run_id, task_id, set_id)`。冒烟集 S8 四题（"
             "s8-cor-01 / s8-eco-01 / s8-ops-01 / s8-rob-01）的 gold 重出。",
     "scope": "**参考清单的字节没动**（40 个 `solve.py` 与 `REFERENCE_MODULE_FILES` 逐个 "
              "sha 相同）——变的是参考版本号本身，它在 `REFERENCE_ROOT_FIELDS` 里，所以参考根跟着变。**"
              "一处要照实说**：`gateway/sim_factory.py` 决定 S8 gold 的运行环境，却**不在** `"
              "REFERENCE_MODULE_FILES` 里（它住在网关侧，不在 `reference/` 下）——也就是说改它不"
              "会让参考根自己动，这一次是靠这条记因钉住的。已登记进 `ops/reports/known_limits_v1.md`。",
     "gates": "`ops/test_f1.py::test_sim_factory_set_id_is_required` 与 `tes"
              "t_task_dir_no_longer_guesses_between_two_sets`；`ops/test_sim"
              "_factory.py` 全绿。"},
)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


#: 清单根 hash 只覆盖**决定题面的部分**（code + templates + 出集清单 + 题面指纹），
#: 题集版本。v1.0 → v1.0.1 的原因见 `REVISIONS`。
SET_VERSION = "1.0.16"

#: **参考版本**（答案面：40 个 `solve.py` + `reference/oracle_io.py` + 各阶段公共主干）。
#:
#: **为什么要拆两条轴**（裁定 2026-09-05）：`solve.py` 是**答案面**，agent 永远看不见它；
#: 而它原来住在 `TEMPLATE_FILES` 里，于是每修一个 oracle 都要推一次**任务集版本** ——
#: 2026-09-05 一天之内推了 1.0.3 / 1.0.4 / 1.0.5 三次，其中两次**题面一个字没动**。
#: 版本号一旦这样跳，「这两次运行为什么不可比」就答不清楚了：
#: 看到 v1.0.3 → v1.0.5 的人无从知道被测方看到的东西其实完全一样。
#:
#: 拆开之后：**任务集版本**回答「agent 看到的东西变了吗」，
#: **参考版本**回答「我们算 gold 的方式变了吗」。可比性要求**两者都相同** ——
#: `inject.json` 与结果记录同时记两个。
REFERENCE_VERSION = "r1.0.23"

#: 每次重冻结留一条。**不是 changelog 装饰** —— 它是「这两次运行为什么不可比」的答案，
#: 而根 hash 只告诉你「不一样」，不告诉你「哪不一样、为什么」。
#: **升序**：最后一条就是 `SET_VERSION`（`ops/test_f1.py` 有一条盯着）。
#: ⚠ `1.0.3` 与 `1.0.5` 事后判定为「参考面变更、任务集未变」（裁定 2026-09-05 拆轴）。
#: 保留原条目不删 —— 它们已经被引用过；那两次的内容改记在 `REFERENCE_REVISIONS` 里。
#: 删掉比留着更容易让人以为没发生过。
#: **`1.0.7` … `1.0.15` 这 10 条 2026-09-11 从 `REFERENCE_REVISIONS` 搬回本表**
#: （N-573，裁定 ⑦）：拆轴之后新增的任务集记因一直写错了地方，于是本表停在 1.0.6
#: 变成死表，而 `build_manifest` 的 `revised_at` 取的正是它。逐字未改，只换了位置。
REVISIONS: tuple[dict, ...] = (
    {"version": "1.0.1",
     "at": "2026-09-04",
     "ticket": "N-44",
     "why": "三处产出物题面无路径与规范形（S3 values / S2 panel / S7 逐日序列），而 values_ref."
            "sha256 是被计分的量 —— agent 不知道往哪写、写什么格式，两个同样正确的实现字节不同，跨实现比对本就不成立"
            "。",
     "what": "artifact_schema 加 PAYLOAD_FILES（路径/格式/列序/排序/索引），packager._ou"
             "tput_files_phrase 机器生成，新增固定槽 fixed:output_files （两臂同给），S2/S3"
             "/S7 共 15 题（出集 13 题）的两臂模板各插一行。",
     "scope": "S2/S3/S7；S1/S4/S5/S6/S8 的题面逐字不变。",
     "gates": "E1–E14 全过 40 题；三条突变（两臂列序漂开 / 缺槽 / 路径写 work/）分别被 E3 / E1 / E8"
              " 拦下。",
     "also_captured": "本次重冻同时收进两处**与题面无关**的既有输入漂移：genetask/pin.py（N-42 的 check_prov"
                      "ider_pin 符号名对齐，提交 aa0a63a，上次冻结之后）与 genetask/packager.py 的第三桩"
                      " default_fill_minus_probe。它们此前由 `test_v10_input_drift_is_vis"
                      "ible_even_when_task_text_is_unchanged` 以 skip 形式可见（不判红，因为「输入"
                      "变而题面没变」是开发常态）。",
     "consequence": "根 hash 变了 → **已构建的 bundle 通行证全部作废**（`expect_frozen_root` 对不上"
                    "，注入器 P3 当场拒）。f02 上的 bundle 需要重新导出。这是对的：题面确实不同了。"},
    {"version": "1.0.2",
     "at": "2026-09-04",
     "ticket": "N-58①",
     "why": "「可用端点」固定槽是一个**不按 stage 区分**的字面量，于是 `/fundamentals` 写进了每一道题两臂"
            "的槽里 —— 每个 agent 都被告知可以查财报，而 v1 没有一道题需要它（40 题 gold 侧零调用，三条独立检"
            "索一致）。render 的 E8b 只管「正文端点 ⊆ 槽」，槽里多列一个不会被任何检查拦下。",
     "what": "端点清单改为按 stage 生成（`packager.stage_endpoints`）：v1 六个数据端点 + S8 "
             "的五个 sim 端点；`/fundamentals` 进 `V1_WITHHELD_ENDPOINTS`，出现在任何阶段"
             "即 import 期抛。同批：TradingAgents 适配器的 `get_fundamentals` 改接 `NO_"
             "SOURCE`。",
     "scope": "全部 40 题的 `fixed:endpoints` 槽（S1–S7 少一个端点，S8 同）。",
     "gates": "E1–E14 全过 40 题；`stage_endpoints` 的突变（把 /fundamentals 加回）必抛；另"
              "加一条断言：发放的端点必须都在网关 ALLOWED_ROUTES 里（发一个不存在的端点会得到 404，而 404 与越"
              "权在越权率上分不开）。",
     "note": "判据是**「agent 看不到即不存在越权」**，不是「调了返 403」——后者会把一次我们自己造成的诱导记成被测方的越"
             "权率。"},
    {"version": "1.0.3（**已改判为参考面变更**）",
     "at": "2026-09-05",
     "ticket": "N-72",
     "why": "40 题的 oracle **一次都没跑过** —— 每个 `solve.py` 末尾那句「自检：oracle 必须零 "
            "finding（O1）… assert validate(...)」是**注释着的**。真跑之后，S1 的四个参考解在三"
            "处上不成立：① `/universe` 的回包是 `{size, members}` 而解析按 `{rows, data"
            "[].code}` 写 —— 取到空列表，整道题一次 `/bars` 都没取，**却仍然产出一份看起来合法的 artif"
            "act**；② `fetched_at` 契约要求用网关回包的时间戳，而网关**不回显任何时间戳**；③ 行数字段名逐端"
            "点不同，缺省按 0 处理会把「没认出回包」判成 `empty`。",
     "what": "S1 四个模板的 `solve.py`：按实测形状解析 `/universe`（取 `members`，取不到成分**直"
             "接抛**而不是产出空壳）；`fetched_at` 只认新加的 `x-genebench-ts` 响应头（**不读日志自"
             "己填** —— 那会让被核值与基准同源，交叉核成恒真）；行数取 `rows`/`size`/列表长度，取不到**不默认 "
             "0**。",
     "scope": "S1 的四个模板（cov_fields / lean_fetch / prov_ledger / source_stat"
              "us），覆盖 s1-cor-01 / s1-rob-01 / s1-eco-01 / s1-ops-01 四题。**题面"
              "（INSTRUCTION / template.yaml / scorer.yaml / Dockerfile）一个字没"
              "动** —— 改的是数据面私有的参考解。",
     "gates": "四题真跑过 O1（零 finding），网关日志切片非空（602–2249 条）；同批修好冻结防漂本身 —— 它原来**"
              "比不到 `templates` 段**，正是这次改动没被它拦下的原因（见 N-74）。"},
    {"version": "1.0.4",
     "at": "2026-09-05",
     "ticket": "N-75 + N-62",
     "why": "**两条原因，一次重冻结**（裁定 2026-09-05）。\n① oracle 的调用约定有**六套**：七个阶段各写各"
            "的，光「artifact 写哪里」就有四个名字（`GENEBENCH_ORACLE_OUT` / `GENEBENCH_"
            "ARTIFACT` / `GENEBENCH_ARTIFACT_PATH` / `sys.argv[1]`），两套「任务"
            "规格从哪来」（env 里塞 JSON vs 读文件）。它们从没冲突过，因为**没有一个被执行过**。\n② 三个 harn"
            "ess 的镜像基座互不相同（python:3.12-slim / node:22-slim / RD 自带），panda"
            "s 只有 RD 那个有且版本与题面钉的不一致 —— 而三条配置的全部意义是「同一模型、三种 harness，**固定模型"
            "效应**」。基座不同，主表上「harness 差异」这一列里就混进了运行时差异。",
     "what": "① 立契约：**oracle 的 I/O 契约 = agent 的 I/O 契约** —— 读标准位置的任务规格（`<t"
             "ask_dir>/task.yaml` + `taskspec.json`）、经网关取数、写标准 artifact 路径"
             "；唯一允许的环境变量是 `GENEBENCH_GATEWAY_URL`（**部署事实**，不是任务事实）与 `GENEB"
             "ENCH_ORACLE_OUT`。实现在 `reference/oracle_io.py`，40 个 `solve.py"
             "` 的前言全部改写；S3 五题的取数/暖机/落盘抽到 `reference/s3_oracle_common.py`（那"
             "条 TODO 落地）。`ops/test_oracle_contract.py` 用 **AST** 锁死：任何 sta"
             "ge 特定 env 或 `sys.argv` 即红。\n② 基座换成 `python:3.12-slim-bookworm"
             "` + **Node 22.23.2**（官方 tarball + 钉 sha256，不走 `curl | bash`）"
             "，数值栈取三家里最高的 `pandas==2.3.3` / `pyarrow==25.0.1`。",
     "scope": "① 40 题全部（改的是**数据面私有的参考解**，题面 INSTRUCTION / template.yaml / s"
              "corer.yaml 一个字没动）；② 39 个模板的 `Dockerfile`（在 `TEMPLATE_FILES` "
              "里，进冻结面）。",
     "gates": "契约锁 122 条全绿（含判别力：喂一个真读 stage 特定 env 的源码必须命中）；S3 端点形状按实测改正三处（"
              "`/calendar` 的 `cal_date`、`/universe` 的 `universe=` 参数、回包 `me"
              "mbers`）。**跨版本数值核（统一基座 vs f01 qlib_env，全部指标相对差 1e-13 量级）是 A1 "
              "的前置，不阻塞本次冻结；不过则 v1.0.5。**"},
    {"version": "1.0.4（拆轴后 root 重算，**内容未变**）",
     "at": "2026-09-05",
     "ticket": "N-78",
     "why": "两条版本轴拆开（裁定 2026-09-05）：`solve.py` 是答案面，移出 `TEMPLATE_FILES`。*"
            "*任务集的内容一个字没变**（题面 / schema / 镜像 / 夹具都还是 1.0.4 那份），但 root 覆盖的"
            "字段集变了，所以 root 值变了：`5a9c0616…` → `b4b058df…`。",
     "what": "root 的覆盖面写进清单的 `root_scope` 字段 —— 事后比两个 root 的人能看出「不一样」是因为覆盖"
             "面变了，而不是题面动了。版本号**不推**：推了会让人以为 agent 看到的东西变了。",
     "scope": "只改 root 的覆盖面定义。答案面内容改在参考轴 r1.0.0。",
     "gates": "两条轴各自的逐段红测试；`inject.json` 同时记两个版本。"},
    {"version": "1.0.5（**已改判为参考面变更**）",
     "at": "2026-09-05",
     "ticket": "N-77",
     "why": "统一调用约定之后 40 题真跑，露出的**全部是端点形状的错误假设** ——每一处都只在真跑时才现形，而这些 oracl"
            "e 从来没跑过：\n① `pd.DataFrame(r.json()[\"rows\"])` —— `rows` 是**行数（"
            "整数）**，数据在 `data` 里（S2/S5 共 10 个模板，那句 TODO「与响应体键名对齐」一直没做）；\n② "
            "`/calendar` 的参数是 `start_date`/`end_date`，写 `start`/`end` **直"
            "接 403**；日期列是 `cal_date` 不是 `date`；\n③ `/universe` 的参数是 `unive"
            "rse=`（`name=` **直接 422**），回包是 `{size, members}` 而不是 `data[]."
            "code`；\n④ `/adj` 给 `ts_code`/`trade_date`，与 `/bars` 的 `code`/"
            "`date` 不同名；\n⑤ S2 的 `get()` **一个身份头都没带** —— 网关日志按 (task_id, c"
            "onfig_id) 切片，缺了这一半就切不出来，表现是「oracle 一次网关都没请求过」而其实请求了几百次；\n⑥ S3"
            " 的日历索引没命名 → `stack()` 后 `reset_index()` 给出 `level_0` → `emit"
            "` 里 KeyError。",
     "what": "在**取数边界**上归一一次（列名别名表 + `/universe` 摊平 + 身份头），比在十几个调用点各改各的可靠 "
             "—— 漏一个只在真跑时才现形。S3 公共层给日历索引命名 `date`。S7 的共用主干抽到 `reference/s7"
             "_oracle_common.py`（D-31 推论：**模板不许 import 兄弟模板**，否则落到任务目录的那份不"
             "自足），并加 AST 锁 `test_a_template_never_imports_another_template"
             "`。",
     "scope": "S2 五个 + S5 五个 + S3 公共层 + S7 五个模板。**题面一个字没动**，改的全是数据面私有的参考解。",
     "gates": "契约锁 162 条全绿；`s3-cor-01` 与 `s2-cor-01` 已能跑通并产出 artifact。**S7 "
              "的 `fetch_panel` 与 S8 的取数仍是 `NotImplementedError`** ——抽取只解决了自"
              "足性，不代表能跑，这一点不许被「已抽取」四个字盖过去。"},
    {"version": "1.0.6",
     "at": "2026-09-05",
     "ticket": "N-84 / N-86 / N-93 / N-98 / E15",
     "why": "**这一次改的是 agent 看得见的东西**，所以推任务集版本（前几次都只推参考轴）。四件事挤在同一次里，是因为它们都"
            "要重签题面，分开推等于让同一批题面有四个版本。**跳过 1.0.5**：那个号在下面已经被占用（2026-09-05 拆"
            "轴时改判为参考面变更），复用会出现两个同号条目。",
     "what": "① **夹具落地**（N-84）：S7 的 `s7_dedicated_signal_v1`、S4 的 `factor_"
             "panel`、S5 的 `inputs/*` 与清单，共 24 个 `inputs[].sha256` 从 null 填"
             "成真值 —— 夹具此前**没有身份**，换一份没有任何东西会报。② **N-86 改名**：`open_orders` "
             "→ `pending_orders`。原名让 `s8-rob-01` 的每一次 `/sim/state` **与 `/s"
             "im/advance`** 都 422，agent 照题面做也一样，那道题谁都做不了。③ **N-93**：`s7-ro"
             "b-02` 的 `oracle.expected` → `honest_halt`、`tolerance.kind` →"
             " `none`；并把 `oracle.expected` 改成由 `kind` 全映射决定（原来是二分支，探针题被静默归"
             "到 `full`，而 `full` 要求 gold 对被欠定字段择一填上 —— 那正是本题要抓的静默补全）。④ **S8"
             " 的 `as_of` 语义**（N-98）：题面只给一个平的冻结线日期，而 S8 的有效上界随模拟时钟走；`s8-ops"
             "-01` 更写着「请求 as_of 之后的数据会被拒」，照字面读是反的。补一句机器生成的注释，**两臂同给**。",
     "scope": "params（24 个 sha + 1 处改名 + 1 处 tolerance）、phrasebook（改名）、pack"
              "ager（oracle.expected 全映射 + S8 as_of 注释）、schema（新增 lint E15）。",
     "gates": "E15 扫全集 40 题**零命中**（首扫命中 1 题，即 N-86）；40 题 build 全 ok；`ops/te"
              "st_vocabulary_e15.py` 含词汇表与引擎的对齐断言与逐类必红。**两族夹具仍无定义**（S4 的 `s"
              "4_eco_pool_v1`、S6 的两个信号），见 N-99 —— 它们的 `sha256` 还是 null，本次不假"
              "装它们有。"},
    {"version": "1.0.7",
     "at": "2026-09-05",
     "ticket": "N-99",
     "why": "N-99 裁定的三族夹具落地 —— agent 拿到的输入多了三份此前**没有定义**的文件（S4-ECO 的因子池、S"
            "6 的稠密/稀疏信号），`inputs[].sha256` 从 null 变成真值，题面因此重签。S4-ECO-01 与"
            "五道 S6 题此前**出不了集**（N-99），这一次是它们第一次有身份。",
     "what": "① `s4_eco_pool_v1`：30 因子（gtja_191 / worldquant_101 / qlib_al"
             "pha158 各 10，按 ID 排序等距抽样，剔退化与覆盖 <95%）；② `s5_gtja001_csi300_v1"
             "`：S5 oracle（s5-cor-01）gold 的信号；③ `s6_sparse_coverage`：每第 7 个"
             "交易日只留 3 个最小代码。三者 sha 写回 params；数据卡 `ops/data_cards/fixture_s"
             "4_eco_pool_v1.md`、`fixture_s6_signals.md`。",
     "scope": "params（S4 pool 1 个 sha + S6 五题的信号 sha）。模板与措辞表不动。",
     "gates": "s4-cor-01 / s4-eco-01 / s4-ops-01 / s4-rob-01 真跑零 finding；S6"
              " 真跑记在 r1.0.7。"},
    {"version": "1.0.8",
     "at": "2026-09-05",
     "ticket": "N-114 / N-104",
     "why": "① **N-114**：S1 的 `tolerance.kind=exact` 让 L3 比「取数台账逐字相等」，而题面"
            "**没有**规定取数粒度 ——Codex 两臂（整窗 3 条 / 逐标的 602 条）都合法、16 族探针全 clean"
            "，却双双判 0。指标规格 §3 给 S1 的是Cov% / PIT% / Prov。签字裁定改判据。② **N-104*"
            "*：S8 的能力位闸（`s8_state_endpoint`）翻绿，五道 S8 题第一次真的能出集 ——此前 `free"
            "ze_v10.CAPS` 里写着 True、而运行时的 `ops/capabilities.json` 是 False，"
            "冻结清单里它们已在 `released_tasks`，生产路径上却一道都建不出来。",
     "what": "params：五个 S1 行 `tolerance.kind` exact → cov（新增枚举值，`genetask/"
             "schema.py::TOLERANCE_KINDS`）。S8 五题的出集不改清单（它们本来就在 `released_t"
             "asks`），改的是运行时能力位。",
     "scope": "params（5 行）+ schema 枚举。模板、措辞表、夹具都不动。",
     "gates": "40 题重建全 ok；S8 五题 oracle 真跑；A1 与 M6-lite 用新判据重结算（不重跑 agent）。"},
    {"version": "1.0.9",
     "at": "2026-09-05",
     "ticket": "判据全仓改判（裁定 ②）",
     "why": "`exact`（结构化 payload 逐键相等）**把 gold 的写法当成了标准答案**。两条实测：S1 上它让两份"
            "都合法、16 族探针全 clean 的产物判 0（N-114）；S2 上它让与 gold **逐字节相同**（同一个 s"
            "ha256）的面板仍判 0.33 —— 扣的是 gold 的 dict 多带 `n_symbols` / `policy"
            "_applied` 这类描述键。判据必须是**指标规格 §3 的量**，不是写法。",
     "what": "params 的 `tolerance.kind`：S2 五题 → `align`（Align / Adj / Cal "
             "+ 面板逐格比对）、S5 三题 → `sig`（三态一致率 + 逐日秩相关用已标定 τ）、S6 五题 → `cons`（"
             "Cons / Feas + 权重一致度）、S8 五题 → `fill`（Fill / Slip / Audit）。**全"
             "仓再无 `exact`**；`ops/test_scorer_l3.py::test_exact_only_for_fi"
             "le_sha_tasks` 把这条钉住。",
     "scope": "params 18 行 + schema 枚举。模板与措辞表不动，题面指纹不变。",
     "gates": "40 题重建全 ok；M6-lite 的 8 题按新判据重结算（不重跑 agent）。"},
    {"version": "1.0.10",
     "at": "2026-09-06",
     "ticket": "N-131",
     "why": "`ops/specs/artifact_schema/v1.0/{stage}.json` 会被逐字节复制成 bundl"
            "e 里的 `work/{stage}.json`（**两臂都拿得到**），却不在冻结清单的 `code` 段里 —— 改"
            "它，agent 看到的东西就变了，而两条版本轴一动不动。2026-09-06 往里写取数约定时实测到这一点（freeze"
            " 报「与冻结清单一致」）。「任务集版本回答『agent 看到的东西变了吗』」这句话，在这条路径上本来不成立。",
     "what": "冻结清单的 `code` 段改为「显式清单 + `CODE_DIRS` 下的全部文件」，把 `ops/specs/art"
             "ifact_schema/` 收进来。**文件内容本身这次没有再改**（取数约定是上一步 r1.0.17 写进去的）——"
             "变的是 `root_scope`：根覆盖的范围大了 8 个文件。",
     "scope": "冻结脚本 1 处；清单里新增 8 个 `code` 条目。题面正文、模板、params 一个字没动。",
     "gates": "根 hash 变（范围变了，**内容未变**，与 1.0.4 那次同形）；`instruction_fingerprin"
              "t` 不变；40 题重建全 ok；两份报告的版本行改 v1.0.10 / r1.0.17。"},
    {"version": "1.0.11",
     "at": "2026-09-06",
     "ticket": "N-129（5.1 红队一轮首件）",
     "why": "发给 GQ 臂的 validator 与评分器 L1 **判得不一样**：10 个带 `validator.log` 的"
            "真 run 里它报了 0 条，同批评分器判 `malformed` 的有 4 个。根因不是 validator 写坏了，"
            "是**规则数据不够细** ——`work/{stage}.json`（两臂共享）此前只到「这个键是 object、必填哪"
            "几个子键」，而真 agent 犯的错在叶子上：HTTP 200 写进 `status`、一句话写进 `alert`、紧凑"
            "串写进 `date`。",
     "what": "`PAYLOAD_SHAPE` 下到叶子（枚举 / bool / pattern / 上下界），八个 schema 文件"
             "随之重生成 ——**agent 拿到的规则变严变全了**，所以推任务集版本。",
     "scope": "`reference/artifact_schema.PAYLOAD_SHAPE` + 8 个落盘 schema（它们在"
              " code 段里，v1.0.10 起）。题面正文、模板、params 未动。",
     "gates": "121 份真语料（23 份真 agent 产物 + 三控 98 份）上：validator 比 scorer 严 **0"
              "** 份、作用域内反向缺口 **0** 份、scorer 报而 validator 沉默 **0** 份（修前是 4 份"
              "）。工具 `ops/validator_parity.py`，测试 `test_parity_on_the_real_m"
              "6_corpus`。"},
    {"version": "1.0.12",
     "at": "2026-09-07",
     "ticket": "卡 4.1（臂机制数据驱动）",
     "why": "**题面与出集内容逐字节不变，推的是「输入变了」这条轴。**臂名此前是 `genetask/schema.py:32` "
            "的一个元组，等价规则按「两臂成对」写死，注入器把「协议工件」与 `strict` 这个名字绑死 —— 加一个臂要改五处代"
            "码、改完还要重签题面。本次把臂集合变成数据（`genetask/arms.yaml`）之后，**决定题面的输入里多了一份"
            "文件**：它说了默认出几个臂、每个臂取哪一列措辞、变体臂追加哪一段文字。不把它收进冻结根，「把 default: fal"
            "se 翻成 true」这一下会静默改动每一道题的字节而版本号纹丝不动。",
     "what": "① `CODE_FILES` 收 `genetask/arms.yaml`，`CODE_DIRS` 收 `genetas"
             "k/arms/`（变体臂的追加文本，agent 直接读到它）；② 渲染器/规则代码（render / packager "
             "/ schema / bundle）本身按 N 臂泛化，它们本来就在 `CODE_FILES` 里，这次内容变了；③ 数"
             "据面文件分类（`packager.EXPORTED_FILES`，G3）改成按注册表展开题面文件名 ——原先写死 str"
             "ict/open 两条，第三个臂的题面会被判「未归类」而整份题导不出去（出四臂 bundle 时实测撞到，与①②同属本卡"
             "，同一个版本号内重冻）。",
     "scope": "**templates 根与 released_tasks 根一个字节没动** —— 漂移报告是「输入已变、题面未变（重"
              "冻即可）」。新登记的 `doc` / `hint` 两臂是 `default: false`，不进任何既有出集：40 题"
              "的 `task.yaml` instruction 段仍是`{strict, open}` 两条，`task_sha25"
              "6` 未变。",
     "gates": "钉住金丝雀 nonce / 时刻 / 子网分配之后，s2-cor-01 与 s7-rob-02 在改动前后的「出集全部文"
              "件 + 两臂干注入 run dir 全部文件」sha256 逐条相同（`/data/shared/genebench/s"
              "cratch/4.1/{before,after}`，harness 自身的确定性另测一遍）。`ops/test_arm"
              "s_registry.py` 31 条；`ops/test_inject.py` / `ops/test_genetas"
              "k.py` / `ops/test_c41.py` / `ops/test_p2_contract.py` / `ops"
              "/test_budget_tiers.py` 413 条全绿。"},
    {"version": "1.0.13",
     "at": "2026-09-07",
     "ticket": "N-103 / N-127 / N-128 / N-279 / N-126（卡 5.2）",
     "why": "**出集清单实质变了**（N-103），外加两处「判据要求的东西题面没说」的补齐（N-127 / N-128）。五件事挤"
            "在同一次里，是因为它们都要重签题面，分开推等于让同一批题面有五个版本；而这是阶段五唯一一个没有在途 bundle 的窗口"
            "。",
     "what": "① **N-103**：`genetask/schema.py::DIVERGENCE_EVIDENCE` 加 `(\"r"
             "ebalance_frequency\", ((\"weighting_scheme\", \"equal\"),))` 一条（正"
             "文由卡 1.1-c 的 `ops/reports/public/materiality_evidence.json` 原"
             "样搬来：三份冻结独立实现逐可行值各跑一遍，私有 26/26/27 共 79 处、公开 27/27/27 共 81 处指标"
             "超 daily 档 ε 带，两条通道都 material，Gate 0 双门均过、本字段不打补丁故 Gate 1 不适用"
             "）。**既有的 `sell_rule` 那条一个字没动。**证据到位 ⟹ `s6-rob-02` 从「不落盘」变成「落盘"
             "」，于是 `IN_V10` 的探针白名单从 `{s7-rob-02}` 变成 `{s7-rob-02, s6-rob-0"
             "2}`，出集从 33 题变成 **34 题**；它的夹具 `work/signal_s5_gtja001_csi300_"
             "v1.parquet` 第一次物化，params 里那个全零占位 sha 换成真值；`tolerance.kind` 由"
             " `cons` 改 `none`（与 s7-rob-02 同，N-93：诚实终止之后 gold 没有 targets 可"
             "比）。② **N-127 滑点符号约定**：S8 五道题**两臂**题面各加一行 —— `payload.fills.s"
             "lippage_bps` 成交价高于计价基准时取正、低于取负，单位 bps。方向与指标规格 §3 的 `Slip = 量"
             "加权(成交价 − 决策时点价)` 同向。**判据不动**：`scorer/l3.compare_fill` 里 Fill"
             " / Slip 仍只报不判（改判据要另一轮红队）。③ **N-128 事件记录字段**：同样五道题两臂各加四行，写明 `"
             "payload.events` 的 order / fill / cancel / state 事件各必须带哪些键、`p"
             "ayload.state_transitions` 每条必须带 from / to / order_id；同一组字段补进"
             " `reference/artifact_schema.PAYLOAD_SHAPE[\"S8\"].events` 的叶子 "
             "`properties`（**只补不重写**，且**不收紧 required** —— 收紧会让既有合法样例与 121 "
             "份真产物集体变畸形，那是判据变更），八份 `ops/specs/artifact_schema/v1.0/S*.json"
             "` 由 `ops/mk_artifact_schemas.py` 重生成（只有 S8.json 变），`genebenc"
             "h_client/emit_schemas.py` 里那份逐字副本同步重灌。④ **N-279 s2-eco-01**："
             "oracle 打 `/bars?universe=csi300` 不给 `code`，网关 422，两条通道同一条红 —"
             "— 「33 题零 finding」卡的就是它。取小改那条：只动参考轴的 `solve.py`，按 code 批量取并按网"
             "关 `MAX_ROWS` 反算分批（不动 `gateway/routers/market.py`，那会改 `declar"
             "ed_reads` 探针的分母口径且仍跨不过行数上限）。⑤ **N-126**：S6 的 TE 本来就没进 v1 判据（"
             "`scorer/l3` 出 note 说明），本次只登记，不改判据。",
     "scope": "题面：S8 十份 `INSTRUCTION.{strict,open}.md`（每份 +5 行）。冻结根其余：`gene"
              "task/schema.py`（DIVERGENCE_EVIDENCE +1 条）、`genetask/params/v"
              "1.0-smoke40.yaml`（s6-rob-02 的 1 个 sha + 1 处 tolerance）、`ops/"
              "specs/artifact_schema/v1.0/S8.json`。出集清单 33 → 34 题。S1–S7 的题面"
              "逐字不变。",
     "gates": "40 题 build 全过 E1–E15/C1 零 problems；`ops/test_s8_event_fields"
              ".py` 38 条；O1 两条通道各重跑受影响的题并合进累积记录 —— **私有 34/40、公开 34/40 零 fi"
              "nding**，两条通道逐题一致，not-ok 的六题就是仍无实质性证据、被 E9c 拦在落盘之前的六道欠定探针（s1/"
              "s2/s3/s4/s5/s8-rob-02）。也就是说**出集的 34 题全部零 finding**，完成定义里的「33"
              " 题」达成并多一题。",
     "also_captured": "本次重冻同时吸收一处**与本卡无关**的既有输入漂移：`genetask/arms.yaml`（清单记 e727dfd2"
                      "083e…、盘上 b873299c0df8…）——卡 4.2-b 加 adapt 臂时留下的，此前以「输入已变、题面未变"
                      "」的形式挂着。",
     "consequence": "根 hash 变了 → **已发通行证全部作废**（`expect_frozen_root` 对不上，注入器 P3 当场"
                    "拒）。阶段五后续的出集必须在这次重冻**之后**做。"},
    {"version": "1.0.14",
     "at": "2026-09-10",
     "ticket": "N-384 / N-383 / W3 实例层 / 六道欠定探针（卡 Y1）",
     "why": "**agent 看得见的东西变了两处，都是「判据要的东西题面/schema 没说清」的收尾。**\n① **N-384**"
            "：`PAYLOAD_SHAPE[\"S8\"].events` 的 `required` 此前只有 `{ts, type}`"
            " ——而 Audit 的定义是「事件链可完整重放」，只有这两个键的链**重放不了**。卡 5.2 把字段写进了题面与 s"
            "chema 的 `properties`，但**刻意没收紧 `required`**（当时的理由：会让合法样例与既有 1"
            "21 份真产物集体变畸形，那是判据变更）。用户 2026-09-10 批了这次判据变更 —— 于是共享 schema 与"
            "题面**第一次真的等价**：题面说「order 事件必须带 order_id、symbol、side、qty」，sche"
            "ma 现在也这么要求。\n② **N-383 的题面侧后果**：`fixed:output_format` 固定槽是**机"
            "器从 schema 的 `required` 生成**的，收紧之后 S8 五道题两臂的那一句从「events 含 ts,"
            " type」变成「events 含 ts, type, order_id」—— 题面确实不同了，必须推版本。（N-383"
            " 本身是参考轴的事，记在 r1.0.21。）\n③ **实例层第一次进清单**（W3）：40 个基点 × 窗口/宇宙/因子"
            "池 → 130 个实例。它**不进根**（见 `root_scope` 与 `INSTANCES_NOTE`），所以不影"
            "响已发通行证；但「有哪些实例、每个实例的题面指纹与夹具 sha 是什么」从此有记录。\n④ **六道欠定探针题仍然挂起**"
            "：W3 逐题判过，六道在 `materiality_screen` 里全部 `inconclusive`，而且是同一个结"
            "构性原因（筛查 harness 是三份冻结的 S7 回测引擎，S1–S5/S8 的探针字段根本没有进入它的入口）。照 s"
            "creen 自己的判据「量不到不是没差别」，**一道都不放出**，`DIVERGENCE_EVIDENCE` 一个字未加"
            "。出集维持 **34 题 / 挂起 6 题**。",
     "what": "① `reference/artifact_schema.PAYLOAD_SHAPE[\"S8\"].events.item"
             "s`：扁平 `required` 收紧成 `[ts, type, order_id]`（四类事件的**交集** —— 题"
             "面对 order/fill/cancel/state 都写了「必须带 order_id」）；逐类的那一半走 `allOf"
             "` + `if/then`，逐字对着题面正文取：order → order_id/symbol/side/qty，fil"
             "l → +price，cancel → order_id，state → order_id/state。**为什么不把逐"
             "类必填写进扁平 required**：那会要求 cancel 事件也带 price。\n② `ops/specs/arti"
             "fact_schema/v1.0/S*.json` 八份由 `ops/mk_artifact_schemas.py` 重"
             "生成（**只有 S8.json 变**），`genebench_client/emit_schemas.py` 的逐字副"
             "本同步重灌。\n③ `reference/artifact_schema._s8` 补一条：每条事件都要有非空 `orde"
             "r_id`。**只收到 order_id 为止** —— 协议 validator（`ops/protocol/gene"
             "protocol_v1`）的「够用子集」不认 `allOf`，评分器收得比它严会让 `ops/validator_par"
             "ity.py` 的两个方向之一当场断。逐类字段仍由 L3 的 Audit 判（`scorer/l3.REPLAY_FIE"
             "LDS`，且要求**有值**不只是键在）。\n④ `reference/artifact_samples.py::s8()"
             "` 的合法样例补齐 order_id/side（并带上 `reference_close`，让 N-383 的 Slip"
             " 自洽判据在样例上演示得出来）；`ops/test_emit.py` 的 S8 最小样例、红队用例 `rt34_env2"
             "_03_S8_ts_mixed_precision_false_reject.json` 同补。\n⑤ 判据锁 `ops/"
             "test_s8_event_fields.py::test_events_required_is_not_tighten"
             "ed_by_this_card` 换成三条新锁（扁平 required 是什么 / 逐类 required 逐字对题面 "
             "/ 两者是交集关系）。\n⑥ 实例层：`build_manifest(with_instances=True)` 第一次落"
             "盘，`instances` 段 130 条 + `instances_fingerprint`。130 个实例里 **4"
             "7 个的夹具已物化**（S1–S5 与 S7），S6 的 15 个**没有** —— `reference/make_f"
             "ixtures.s6_consumer_window` 要先在实例集根里看到引用 `reference/signals/"
             "*` 的题，而那些题正是它要出夹具的题（先有鸡还是先有蛋）。如实记 `fixtures: {}`，不假装有。",
     "scope": "题面：S8 十份 `arms/INSTRUCTION.{strict,open}.md` 的 `fixed:output"
              "_format` 槽（机器生成，各 +1 个键名 `order_id`）—— **题面正文一个字没手改**。冻结根其余："
              "`ops/specs/artifact_schema/v1.0/S8.json`。S1–S7 的题面逐字不变。出集清单不"
              "变（34 题）。清单新增 `instances` / `instances_fingerprint` 两段（**不在 `"
              "ROOT_FIELDS` 里**）。",
     "gates": "40 题 build 全过 E1–E15/C1 零 problems；130 个实例 build 全过（`ops/mk_"
              "instances.py --build` red=0）；`ops/test_s8_event_fields.py` /"
              " `test_emit.py` / `test_artifact_schema.py` / `test_scorer_l"
              "3.py` / `test_protocol_validator.py` / `test_artifact_redtea"
              "m.py` / `test_genetask.py` / `test_c42.py` / `test_instances"
              ".py` 定向全绿；S8 四题 oracle **私有 / 公开各一次真跑，4/4 零 finding**（gold 重"
              "出，见 r1.0.21）。",
     "consequence": "根 hash 变了 → **已发通行证全部作废**（`expect_frozen_root` 对不上，注入器 P3 当场"
                    "拒）。Y1 之后的出集必须在这次重冻**之后**做。**既有产物不追溯**：v1.0.13 及以前跑出来的 121 份真"
                    "产物按**旧 schema** 判 —— 它们的 order 事件多数只有 `{ts, type}`，按新 schema"
                    " 会集体畸形，但那不是它们的错（题面当时没这么要求）。见 `ops/reports/s8_schema_tighteni"
                    "ng_v1_0_14.md`。"},
    {"version": "1.0.15",
     "at": "2026-09-10",
     "ticket": "N-484 / N-543 / N-518（卡 A，用户裁定 ①②③⑤⑧）",
     "why": "**一次重冻，压四件动冻结根的事** —— 分四次推版本等于让同一批题面有四个号，而其中三件题面一个字都没动。四件各自的"
            "病灶：\n① **N-484**：公开 provider 的打包器在 `files.sha256` 生成之后又写了 `MA"
            "NIFEST.sha256` 与 `build_info.json` 两件构建元数据，而 `genetask/pin.p"
            "y::PROVIDER_META_FILES` 只豁免清单自身与 `manifest.json` —— 于是**公开通道"
            "的每一次注入**都在 P2 判红成「树里有而清单里没有」，而那棵树一个字节都没被动过。症状说 provider 被改了，"
            "病因是打包器多写了两个文件；照着报错去查 provider 的人查不到任何东西。\n⑤ **实例层此前不在根内**：根只覆"
            "盖出集那 34 道题，而实例层有 130 道。换掉整张实例参数表，根 hash 一个字不变 —— 也就是说根答不出「这一"
            "次被测方拿到的是哪一批题」。\n⑧ **`gateway/sim_engine.py` 有全树唯一一条「网关 import"
            " 答案面」**（`from reference.artifact_schema import LEGAL_TRANSIT"
            "IONS, TRADABILITY_STATES, UNTRADABLE_STATES`）。红线 B2 不许 `refe"
            "rence/` 上执行面，于是单机双容器形态里网关**根本 import 不起来**，手册 §1.1「两种形态跑同一套代"
            "码」那句话不成立。\n② ③ 是参考轴的事，记在 r1.0.22。",
     "what": "① `PROVIDER_META_FILES` 加 `MANIFEST.sha256` 与 `build_info.js"
             "on`，**豁免面封闭成这四个字面名字**（写成前缀/通配会把「多出来的文件也是改动」整片关掉）。实测：公开树 2 条报"
             "错 → 0 条，私有树 0 条 → 0 条。\n⑤ `instances_fingerprint` 进 `ROOT_FIE"
             "LDS`；`genetask/params/v1.0-instances.yaml` 进 `CODE_FILES`。连带"
             "两处：`build_manifest()` 默认翻成 `with_instances=True`（不算就没这个字段，`m"
             "anifest_root` 直接 KeyError）；`frozen_ref(verify=True)` 的现算比对**"
             "补上实例指纹**（不补的话「实例表改了没重冻」不会被任何一处发现 —— 本文件骂过三次的 F7 形态的第四次）。\n⑧ 三"
             "个 S8 契约常量抽成 `genetask/s8_contract.py`（**零依赖**，不 import `refe"
             "rence/`）；`reference/artifact_schema.py` 与 `gateway/sim_engin"
             "e.py` 双双改成引用它，**值逐字节不变**（改前改后快照 sha256 同为 `315a9ba4fa860b7c…"
             "`，见 `ops/reports/s8_contract_parity.txt`）。该文件同时进 `CODE_FILES"
             "`：它现在是 `DECLARATION_MEMBER_ENUMS` 与 `$.payload.*.state` 枚举的唯"
             "一来源，而 `artifact_schema.py` 改成 import 之后**改契约模块不会让参考轴的 sha 动一"
             "下**。",
     "scope": "**题面逐字不变，出集清单不变（34 题）** —— 本次三件都不改任何 agent 读得到的正文。根 hash 变的原"
              "因是：`code` 段多了两个文件（实例参数表、S8 契约模块）、`genetask/pin.py` 的 sha 变了、"
              "且 `ROOT_FIELDS` 多了 `instances_fingerprint` 一项（**覆盖面变了也会让根变**"
              "，2026-09-05 拆轴时踩过一次，所以 `root_scope` 记着覆盖面）。",
     "gates": "`ops/test_provider_pin_channel.py`（两条通道真注入 + 新增 ① 的八条：豁免面恰好四"
              "个名字 / 按名字不按形状 / 真缺文件仍红 / 内容不符仍红 / 非元数据的多余文件仍红 / 真树上清单覆盖除四者外全"
              "部 / 两条通道 P2 真树全绿）；`ops/test_s8_contract.py`（新，AST 判 `gateway"
              "/**` 零 `import reference` + 干净子进程真 import 引擎数 `sys.modules` "
              "里的 `reference.*` = 0 + 三常量逐个与合并 sha 比对 + `is` 同一对象不是两份相等的 + "
              "全树只有一处定义）；`ops/test_freeze*.py` / `ops/test_y1.py` 定向全绿。",
     "consequence": "根 hash 变了 → **已发通行证全部作废**（`expect_frozen_root` 对不上，注入器 P3 当场"
                    "拒），f02 上的 bundle 要重新导出；X1/X2 的出集必须在本次提交**之后**做。\n**⑤ 的长期后果要单独"
                    "记住**：从这一版起，**实例表改一行就作废所有已发通行证**。这是收进根换来的判别力的价格，不是意外。"},
    {"version": "1.0.16",
     "at": "2026-09-11",
     "ticket": "N-605 / N-578 / N-573（卡 F1，用户裁定 ①③⑦）",
     "why": "**四件事挤在同一次重冻里**，因为它们每一件都动到「根覆盖什么」，分四次推等于让同一批题面有四个版本。\n① **公开通"
            "道分轴**（N-605，裁定 ① 走 B）：公开链此前**借用私有轴的号**，而它的夹具字节与私有的根本不同（实测 `s"
            "4-cor-01/work/factor_panel.parquet` 公开侧 `034c4526…` ≠ 私有侧 `c"
            "8ed955e…`）。同一个 `set_version` 指向两批不同字节的题，「这两次运行可比吗」在公开通道上**答不"
            "出来**；而且公开通道那 5 道带 `inputs` 的题（s4-cor-01 / s5-cor-01 / s6-cor"
            "-01 / s7-cor-01 / s7-rob-02）**一道都出不了集** —— `export_task` 的夹具"
            "身份闸拿私有声明去核公开字节，必然不符。\n② **实例 ID 一律带参数指纹**（N-578，裁定 ③）：基点实例此前*"
            "*沿用基点题的 task_id**，于是 `v1.0-instances/s8-cor-01` 与 `v1.0-smok"
            "e/s8-cor-01` 同号。`gateway/sim_factory.task_dir` 靠 glob 找题目录，同"
            "号就是歧义，它按设计**当场 RuntimeError 不猜** —— 结果是 **S8 四道题的 gold 现在一份都"
            "重算不出来**。\n③ **sim 会话键带 set_id**（裁定 ③）：会话键原来是 `(run_id, task_i"
            "d)`，而 `task_id` 在两个出集里可以重名。同号不同题共用一个会话，表现是「账户里有一批不属于这道题的持仓」，"
            "没有一处会报。\n④ **`REVISIONS` 复活**（N-573，裁定 ⑦）：拆轴之后新增的任务集记因**全写进了 "
            "`REFERENCE_REVISIONS`**（1.0.7 … 1.0.15 共 10 条），`REVISIONS` 停"
            "在 1.0.6 变成死表，而 `build_manifest` 的 `revised_at` 取的正是它 —— 清单里那"
            "个日期从 2026-09-05 起就没动过。",
     "what": "① `SET_VERSION_PUBLIC` 与私有轴并列，公开清单落 `ops/manifests/v1.0-smok"
             "e-public.json`；公开根多一段 `channel_fixtures`（公开树上夹具的**真实** sha），"
             "`frozen_ref(channel=…)` / `check_manifest(..., channel=…)` 按"
             "通道取根。`genetask/packager.export_task(..., channel=…)` 按通道处理夹具"
             "身份：**私有通道逐字节不变**（仍是「声明什么就必须是什么」），公开通道把**盘上真值**写进导出的 X `task."
             "yaml`，并保留防漏闸 —— 公开夹具的 sha **等于**私有声明值即当场红（那意味着私有数据漏进了公开树）。\n②"
             " `ops/mk_instances.allocate_task_ids`：基点实例不再沿用基点题号，在变体发完号之后继"
             "续顺序发号（变体编号**一个都不动**），`row` 跟着写 `set_id=v1.0-instances` 与带指纹的"
             " `subject_id`。\n③ `gateway/sim_factory.task_dir` / `read_task"
             "_face` / `build_engine` 的 `set_id` **必填无默认**；`gateway/router"
             "s/sim.py` 的 `_SESSIONS` 键改成 `(run_id, task_id, set_id)`，工厂注册"
             "时一并登记本进程服务的 `set_id`（`GENEBENCH_SET_ID`，默认 `v1.0-smoke`）。\n④ "
             "10 条任务集记因从 `REFERENCE_REVISIONS` **搬**进 `REVISIONS`（逐字未改），两个"
             "元组一律升序（最后一条 = 当前号），`ops/manifests/v1.0-smoke.json` 的变更记录由它重出"
             "。",
     "scope": "冻结根内只动了 `genetask/packager.py`（export_task 的通道分支）。实例表 `genet"
              "ask/params/v1.0-instances.yaml` **字节未变** —— 它记的是 `{instance_"
              "id: 夹具 sha}`，而 `instance_id` 本来就带参数指纹；发号规则换掉的是 `task_id`，于是变"
              "的是清单里的 `instances` 段与 `instances_fingerprint`（40 个基点实例换了号，13"
              "0 个变体一个都没动）。**题面一个字没动** —— 私有通道同一道题改前改后的 bundle 逐文件 sha256 相"
              "同（证据见 `ops/reports/f1_private_export_bitwise.md`）。",
     "gates": "`ops/test_f1.py`：公开通道 5 道带 inputs 的题出得了集 / 防漏闸喂一件与私有声明相同的夹具当"
              "场红 / 私有导出逐字节不变 / 基点实例与冒烟题不再同号 / `task_dir` 对四道 S8 不再 Runtime"
              "Error / `REVISIONS[-1]['version'] == SET_VERSION`；外加 `ops/te"
              "st_instances.py`、`ops/test_sim_factory.py`、`ops/test_y1.py`、"
              "`ops/test_release_manifest.py` 定向重跑。"},
)

#: 不含 released_at 这类元数据 —— 否则改一句说明文字就会让所有已构建的 bundle 作废。
#: **也不含 revisions** —— 同理：补一句变更说明不该让已构建的 bundle 全部作废。
#: 但 `set_version` **在**根里：改题面必须让根变，而版本号是人读的那一面。
#: `instances_fingerprint` **2026-09-10 收进根**（用户裁定 ⑤）。它此前刻意不在根里，
#: 理由是「加一个实例不该让所有已发 bundle 通行证作废」。收进来就是接受那个代价：
#: **此后实例表一动，所有已发通行证当场作废**（`frozen_ref` 比的就是根）。
#: 换来的是根重新回答得了「被测方这一次拿到的那批题是哪一批」——
#: 实例层有 130 道题，而根只覆盖出集那 34 道时，换掉整张实例表根一个字不变。
ROOT_FIELDS = ("set_id", "set_version", "code", "templates", "released_tasks",
               "instruction_fingerprint", "instances_fingerprint")

#: 渲染期 nonce 的形状（`genetask/schema.py` 的 `^GBC-C-[0-9a-f]{16}$`）。
#: 算题面指纹前必须把它抹平 —— 否则指纹每次都变，等于没有指纹。
_NONCE_RE = re.compile(r"GBC-[A-Z]-[0-9a-f]{16}")


def instruction_fingerprint(built: dict) -> str:
    """**题面本身**的指纹：40 题 × 2 臂的渲染文本，抹掉 nonce 后拼起来算 sha256。

    为什么它比「代码 + 模板的 sha256」更该是判据：那两样是**输入**，改了不一定改题面
    （比如给 packager 加一个与渲染无关的函数）。题面指纹回答的是签字人真正关心的那个问题 ——
    **题面变了没有**。两个都留：输入 hash 抓「有人动了会影响渲染的东西」，
    题面指纹抓「动完之后题面到底变没变」。

    抹 nonce 用**格式正则**而不是具体串（与 §6.4 金丝雀收尾扫描同一个理由）：
    具体串每次都不同，拿它去 replace 需要先知道它是什么，而那正是要抹掉的东西。
    """
    parts = []
    for tid in sorted(built):
        b = built[tid]
        for arm in ("strict", "open"):
            txt = _NONCE_RE.sub("<NONCE>", getattr(b, arm).text)
            parts.append(f"{tid}\0{arm}\0{hashlib.sha256(txt.encode()).hexdigest()}\n")
    return hashlib.sha256("".join(parts).encode()).hexdigest()


def _root_field(manifest: dict, k: str):
    """取一个 `ROOT_FIELDS` 字段。**缺了当场说清楚**，不让它裸成 KeyError（⑤）。

    `instances_fingerprint` 2026-09-10 进根之后，拿一份老清单（或
    `build_manifest(with_instances=False)` 的结果）来算根会缺这个键，
    而裸 KeyError 只会说 `'instances_fingerprint'` —— 看到的人无从知道
    是「清单太老」还是「代码写错了」。
    """
    if k not in manifest:
        raise SystemExit(
            f"清单缺 `{k}`，算不出根 —— 它在 `ROOT_FIELDS` 里。"
            f"若这是 v1.0.14 及以前落盘的清单：那时它还不在根里（用户裁定 ⑤ 之前），"
            f"重跑 `python3 ops/freeze_v10.py --write` 生成新清单；"
            f"若来自 `build_manifest(with_instances=False)`：那个开关 2026-09-10 起默认 True，"
            f"显式传 False 就算不出根")
    return manifest[k]


def manifest_root(manifest: dict) -> str:
    """冻结清单的根 hash（卡 4.3 注入时核冻结的比对基准，裁定 2026-09-04）。

    只取 ROOT_FIELDS，按 `sort_keys` 规范化后 sha256。`released_tasks` 只取 task_id 序列 ——
    同一批题的元数据（family / subject_id 这类）改了不该让 bundle 作废，**题面变了才该**。
    """
    # **根覆盖什么由清单自己的 `set_id` 决定**（① 2026-09-11）：公开清单多一段
    # `channel_fixtures`。写成「调用方传通道」的话，漏传一次就会拿私有覆盖面去算公开根 ——
    # 而那个根算得出来、比得过、且**对公开夹具一无所知**。
    fields = PUBLIC_ROOT_FIELDS if manifest.get("set_id") == PUBLIC_SET_ID else ROOT_FIELDS
    core = {k: _root_field(manifest, k) for k in fields if k != "released_tasks"}
    core["released_task_ids"] = [t["task_id"] for t in manifest["released_tasks"]]
    blob = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


#: ================================================================ 公开通道的版本轴
#:
#: **为什么公开通道要有自己的号**（N-605，用户裁定 ① 走 B，2026-09-11）：
#: 两条通道的**题面逐字相同**，但 agent 拿到的**夹具字节不同** —— 公开夹具由公开 provider
#: 重算，实测 `s4-cor-01/work/factor_panel.parquet` 公开侧 `034c4526…` ≠ 私有侧 `c8ed955e…`。
#: 借用私有号的话，同一个 `set_version` 指向两批不同字节的题，
#: 「这两次运行可比吗」在公开通道上**答不出来**；而且公开通道那 5 道带 `inputs` 的题
#: 出集时必然撞上夹具身份闸（拿私有声明去核公开字节），**一道都出不去**。
#:
#: 两条通道**各自的冻结根与通行证**：私有根覆盖 `ROOT_FIELDS`，
#: 公开根多一段 `channel_fixtures`（公开树上夹具的真实 sha）——
#: 那正是两条通道唯一不同的东西，不进根就等于公开通行证钉不住公开夹具。
SET_VERSION_PUBLIC = "p1.0.0"

#: 公开出集的目录名与清单落点。与 `ops/run_joblist.PUBLIC_ANSWER_ROOT` 同值
#: （那边是跑批侧的常量，这边是冻结侧的；值不一致的表现是「冻的是一批、跑的是另一批」）。
PUBLIC_SET_ID = "v1.0-smoke-public"
OUT_PUBLIC = _REPO / "ops" / "manifests" / "v1.0-smoke-public.json"

#: 公开根的覆盖面 = 私有那些 + 夹具真值。
PUBLIC_ROOT_FIELDS = ROOT_FIELDS + ("channel_fixtures",)

#: 公开轴的记因。纪律与 `REVISIONS` 逐字相同。
REVISIONS_PUBLIC: tuple[dict, ...] = (
    {"version": "p1.0.0", "at": "2026-09-11", "ticket": "N-605（卡 F1，用户裁定 ① 走 B）",
     "why": "**公开轴的起点。** 在此之前公开通道借用私有的 `set_version`，"
            "而两条通道的夹具字节根本不同 —— 于是「公开通道的这两次运行可比吗」"
            "只能靠私有轴的号来答，而那个号对公开夹具一无所知。"
            "连带后果：公开通道 5 道带 `inputs` 的题（s4-cor-01 / s5-cor-01 / s6-cor-01 / "
            "s7-cor-01 / s7-rob-02）**一道都出不了集**。",
     "what": "公开清单落 `ops/manifests/v1.0-smoke-public.json`，`set_id` = `v1.0-smoke-public`；"
             "公开根在私有 `ROOT_FIELDS` 之上多一段 `channel_fixtures`（公开树上夹具的真实 sha）；"
             "`frozen_ref(channel=…)` 按通道取根，默认值取 `GENEBENCH_CHANNEL` —— "
             "`ops/run_joblist.py` 已经强制 `--channel` 与该环境变量一致，"
             "所以出集 / 推送 / 注入三处调用点**一个字都不用改**就按通道走对了根。",
     "scope": "公开轴自己。**私有轴的根与已发通行证不受影响**："
              "`build_manifest()` 不传通道时逐字段与改前相同。",
     "gates": "`ops/test_f1.py`：公开 5 道带 inputs 的题出得了集 / 防漏闸（公开夹具字节与私有声明相同即红）/ "
              "私有导出逐字节不变 / 公开根 ≠ 私有根 / 公开清单的 `set_version` 是公开号。"},
)


def public_answer_root() -> Path:
    import genebench_config as _cfg
    return _cfg.GENEBENCH_ROOT / "reference" / "tasks" / "public" / PUBLIC_SET_ID


def build_channel_fixtures(root: Path | None = None) -> dict:
    """公开树上**真实**的夹具 sha：`{task_id: {相对路径: sha256}}`。

    只收题面 `inputs[]` 声明过的那些 —— oracle 产物与伴生文件不是 agent 的输入，
    收进来会让「跑没跑过 oracle」改变公开根。
    """
    import yaml
    r = Path(root) if root else public_answer_root()
    out: dict[str, dict[str, str]] = {}
    if not r.is_dir():
        return out
    for d in sorted(p for p in r.iterdir() if p.is_dir()):
        f = d / "task.yaml"
        if not f.is_file():
            continue
        t = yaml.safe_load(f.read_text(encoding="utf-8"))
        got = {}
        for i in (t.get("inputs") or []):
            p = d / i["path"]
            if p.is_file():
                got[i["path"]] = _sha(p)
        if got:
            out[str(t.get("task_id") or d.name)] = dict(sorted(got.items()))
    return dict(sorted(out.items()))


def assert_channel(ch: "str | None") -> str:
    import genebench_config as _cfg
    return _cfg.assert_channel(ch)


_VERIFIED: dict[str, str] = {}          # 进程内缓存：现算一次要 build 40 题，别每道题都算


def manifest_path_for(channel: "str | None" = None) -> Path:
    """该通道的清单落点。**默认取 `GENEBENCH_CHANNEL`** —— 出集 / 推送 / 注入三处
    调用点因此不用各自传参：`ops/run_joblist.py` 已经强制 `--channel` 与它一致。"""
    return OUT_PUBLIC if assert_channel(channel) == "public" else OUT


def frozen_ref(manifest_path: Path = None, *, verify: bool = True,
               channel: "str | None" = None) -> dict:
    """给 bundle 通行证用的**最小**冻结引用：set_id + 版本 + 根 hash。

    不放清单全文：`held_tasks`（哪些题被挂起）与 `prohibitions`（计分禁令原句）
    没必要随 bundle 搬到执行面 —— 注入器只需要一个能比对的根。

    `verify=True`（默认）：**现算**一遍，与清单文件里记的比对，不一致即抛。

    为什么这一步不能省（红队 2026-09-04 逐字复现）：没有它的时候，这个函数只是
    「读文件、对文件里已经记着的字段求 hash」—— 改一个模板、题面真的变了，
    而通行证的 root **一个字都没变**，`check_manifest` 全绿、inject 放行、
    改过的题面照样进容器。**这正是 `pin.py` 里批判过的 F7 形态（只读记录值等于没查），
    在同一个仓库里犯了第二次。**

    比对而不是直接用现算值的理由：良性代码改动（给打包器加个无关函数）会让现算根漂动，
    直接用它会让所有已发通行证作废；而「记录 + 现算比对」既钉住了题面，又让重冻这件事
    保持显式（`freeze_v10.py --write` 那一步）。
    """
    path = manifest_path or manifest_path_for(channel)
    if not Path(path).is_file():
        raise SystemExit(f"没有已冻结的清单：{path} —— 先 `python3 ops/freeze_v10.py "
                         f"{'--write-public' if Path(path) == OUT_PUBLIC else '--write'}`")
    m = json.loads(Path(path).read_text(encoding="utf-8"))
    recorded = manifest_root(m)
    if verify:
        key = str(path)
        if _VERIFIED.get(key) != recorded:
            cur = build_manifest(channel=("public" if m.get("set_id") == PUBLIC_SET_ID
                                          else "private"))
            if m.get("set_id") == PUBLIC_SET_ID and \
                    cur.get("channel_fixtures") != m.get("channel_fixtures"):
                raise SystemExit(
                    "公开清单与公开树不符：**夹具字节变了** —— 公开通道的夹具真值在公开根里"
                    "（`PUBLIC_ROOT_FIELDS`），不比的话「公开夹具换了一份而通行证一个字不变」"
                    "不会被任何一处发现；先人工签字再 "
                    "`python3 ops/freeze_v10.py --write-public`")
            if cur["instruction_fingerprint"] != m.get("instruction_fingerprint"):
                raise SystemExit(
                    f"冻结清单与工作树不符：题面指纹 记录 "
                    f"{str(m.get('instruction_fingerprint'))[:16]}… ≠ 现算 "
                    f"{cur['instruction_fingerprint'][:16]}… —— **题面变了**，"
                    f"不得出通行证；先人工签字再 `python3 ops/freeze_v10.py --write`")
            if [x["task_id"] for x in cur["released_tasks"]] != \
                    [x["task_id"] for x in m["released_tasks"]]:
                raise SystemExit("冻结清单与工作树不符：出集清单变了 —— 不得出通行证")
            # **实例指纹也要比**（⑤，2026-09-10）。它进了 `ROOT_FIELDS`，所以「实例表改了
            # 而没重冻」会让现算根与记录根分叉 —— 而这个函数返回的是**记录根**。
            # 不比的话：改一行实例参数、通行证的 root 一个字不变、bundle 照出，
            # 而 bundle 里那批题已经不是清单描述的那批。**与上面模板文件那一段同一个理由，
            # 同一个 F7 形态**，这里是它的第四次。
            if cur.get("instances_fingerprint") != m.get("instances_fingerprint"):
                raise SystemExit(
                    f"冻结清单与工作树不符：**实例表变了** —— 记录 "
                    f"{str(m.get('instances_fingerprint'))[:16]}… ≠ 现算 "
                    f"{str(cur.get('instances_fingerprint'))[:16]}…；不得出通行证。"
                    f"先人工签字再 `python3 ops/freeze_v10.py --write`"
                    f"（实例表 2026-09-10 起在冻结根内，用户裁定 ⑤）")
            # **模板文件本身也要比**（2026-09-05 实测补）。
            #
            # 这一段原来**没有** —— 校验只比了题面指纹与出集清单。
            # 于是改一个 `solve.py`（它在 `TEMPLATE_FILES` 里、进 `templates` 段、
            # 因而进 `root`），指纹与清单都不动，**校验照样全绿**：
            # 实测 `S1/cov_fields/solve.py` 清单记 `2d06cd…`、盘上是 `c32ea474…`，
            # 而 `frozen_ref(verify=True)` 返回成功。
            #
            # **这是同一个 F7 形态的第三次** —— 而且就发生在这个函数里：
            # 它的 docstring 逐字写着「这正是 pin.py 里批判过的 F7 形态，在同一个仓库里犯了第二次」。
            # 第二次的修法是「现算一遍」，但**比错了字段** —— 现算了，没比到点子上。
            #
            # `code` 段刻意**不**做硬比对：给打包器加个无关函数就会让它漂，
            # 而那不是题面变了。题面由三样钉住：**指纹（渲染结果）+ templates（源文件）+ 出集清单**。
            drift = {k: (m["templates"].get(k), v)
                     for k, v in cur["templates"].items() if m["templates"].get(k) != v}
            drift.update({k: (v, None) for k, v in m["templates"].items()
                          if k not in cur["templates"]})
            if drift:
                head = sorted(drift)[:3]
                detail = []
                for k in head:
                    was, now = drift[k]
                    changed = sorted({f for f, _ in
                                      set((was or {}).items()) ^ set((now or {}).items())})
                    detail.append(f"{k}: " + "、".join(changed[:4]))
                raise SystemExit(
                    f"冻结清单与工作树不符：**模板文件变了**（{len(drift)} 个模板）——\n  "
                    + "\n  ".join(detail)
                    + "\n不得出通行证；先人工签字再 `python3 ops/freeze_v10.py --write`")
            _VERIFIED[key] = recorded
    return {"set_id": m["set_id"],
            # **人读的那一半**：`root` 已经随 set_version 变（它在 ROOT_FIELDS 里），
            # 但通行证里只有 root 的话，人看到两个 bundle 只能比 hash 不能比版本。
            "set_version": m.get("set_version"),
            "status": m["status"], "released_at": m["released_at"],
            "root": recorded}


#: **实例层**（W3，2026-09-10）。清单从「模板一层」变成「模板与实例两层」：
#: 基点 = 出集参数表的 40 行；实例 = 沿窗口 / 宇宙 / 因子池换取值得到的约 130 个变体。
#: 逐实例记 id / 参数 / 题面指纹 / 夹具 sha，结构与写入在 `ops/mk_instances.py`。
#:
#: **2026-09-10 收进 `ROOT_FIELDS`**（用户裁定 ⑤）。原注在这里写的是「刻意不进根，
#: 要不要收由 Y1 定」——现在定了：收。连带两处必须跟着改，否则根本算不出根：
#: ① `build_manifest()` 的默认从「不算实例段」翻成 **`with_instances=True`** ——
#:    `manifest_root()` 取的是 `ROOT_FIELDS` 里的每一个字段，不算就是 KeyError；
#: ② `frozen_ref(verify=True)` 的现算比对**要比上这个指纹** —— 不比的话，
#:    「实例表改了但没重冻」这件事不会被任何一处发现，而那正是这个文件的 docstring
#:    连着骂过三次的 F7 形态（只读记录值等于没查）。
#: 代价实测：`build_instances_section()` 在 f01 上 3.0 秒 / 峰值 23 MB，进程内由
#: `_VERIFIED` 缓存，一个进程只付一次。原注说的「白付的钱」现在买到了东西。
def build_instances_section() -> dict:
    """实例层清单（W3）。惰性 import：`ops/mk_instances.py` 反过来要 import 本模块的 CAPS 校验。"""
    from ops import mk_instances as MI
    return MI.manifest_section()


def instances_fingerprint(section: dict) -> str:
    from ops import mk_instances as MI
    return MI.instances_fingerprint(section)


def build_manifest(*, with_instances: bool = True, channel: str = "private") -> dict:
    rows = P.load_params(PARAMS)
    built = {r["task_id"]: P.build_task(r, capabilities=CAPS) for r in rows}
    red = {k: b.problems for k, b in built.items() if not b.ok}
    if red:
        raise SystemExit(f"构建有红，不得冻结：{red}")

    templates: dict[str, dict[str, str]] = {}
    for r in rows:
        key = f"{r['stage']}/{r['template_id']}"
        if key in templates:
            continue
        d = _REPO / "genetask" / "templates" / r["stage"] / r["template_id"]
        templates[key] = {f: _sha(d / f) for f in TEMPLATE_FILES if (d / f).is_file()}

    released, drafted = [], []
    for r in rows:
        t = built[r["task_id"]].task
        row = {"task_id": t["task_id"], "stage": t["stage"], "family": t["family"],
               "subject_id": t["subject_id"], "kind": t["kind"],
               "template_id": t["template_id"], "payload_profile": t["payload_profile"],
               "underdetermined": t["underdetermined"],
               "prohibitions": list(built[r["task_id"]].strict.prohibitions)}
        (released if IN_V10(t) else drafted).append(row)

    m = {
        "set_id": "v1.0-smoke",
        #: 题集版本。**改题面就要动它** —— 根 hash 变了而版本号不变，
        #: 「同一个 v1.0 的两次运行」就会指向两份不同的题面，而主表上看不出来。
        "set_version": SET_VERSION,
        #: **root 覆盖什么**，写在清单里而不是只写在代码里。
        #: 2026-09-05 拆轴时 `solve.py` 移出了 `templates` 段 —— 题面内容一个字没变，
        #: **但 root 值变了**，因为它覆盖的字段集变了。不把覆盖面记下来的话，
        #: 事后比两个 root 的人只会看到「不一样」，并合理地以为题面动过。
        "root_scope": {"root_fields": list(ROOT_FIELDS),
                       "template_files": list(TEMPLATE_FILES),
                       "excluded_to_reference_axis": list(REFERENCE_TEMPLATE_FILES)},
        "status": "released",
        "released_at": "2026-09-04",
        "revised_at": REVISIONS[-1]["at"] if REVISIONS else None,
        #: **变更原因逐条留档**。重冻结不写原因，等于把「为什么这两次结果不可比」
        #: 的答案丢了 —— 半年后没人分得清。
        "revisions": REVISIONS,
        "freeze_line": "2026-07-31",
        "counts": {"drafted": len(rows), "released": len(released), "held": len(drafted)},
        "note": ("冻的是**输入**：模板文件 + 措辞表 + 参数表 + 渲染器/规则代码。"
                 "canary.control_token 每次打包是新 nonce，所以 instruction[arm].sha256 "
                 "两次 build 必然不同 —— **不要**拿渲染产物的 sha 当基准。"),
        "instruction_fingerprint": instruction_fingerprint(built),
        "code": {f: _sha(_REPO / f) for f in _code_files()},
        "templates": templates,
        "released_tasks": sorted(released, key=lambda x: x["task_id"]),
        "held_tasks": sorted(drafted, key=lambda x: x["task_id"]),
        "packager_version": S.PACKAGER_VERSION,
    }
    if with_instances:
        sec = build_instances_section()
        m["instances"] = sec
        m["instances_fingerprint"] = instances_fingerprint(sec)
    if assert_channel(channel) == "public":
        # **题面那一半逐字段与私有相同**（同一批模板、同一张参数表、同一个题面指纹）——
        # 公开轴换掉的只有三样：集名、版本号、记因；外加**多一段**夹具真值。
        m["set_id"] = PUBLIC_SET_ID
        m["set_version"] = SET_VERSION_PUBLIC
        m["revisions"] = REVISIONS_PUBLIC
        m["revised_at"] = REVISIONS_PUBLIC[-1]["at"] if REVISIONS_PUBLIC else None
        m["channel"] = "public"
        m["channel_fixtures"] = build_channel_fixtures()
        m["root_scope"] = {**m["root_scope"], "root_fields": list(PUBLIC_ROOT_FIELDS),
                           "channel_fixtures": ("公开树上 inputs[] 声明的夹具真实 sha —— "
                                                "两条通道唯一不同的东西，所以它在公开根里")}
        m["note"] = (m["note"] + " **公开通道**：题面与私有逐字相同，夹具字节不同；"
                     "夹具真值进根，所以换一份公开夹具而不重冻，通行证当场对不上。")
    return m


REFERENCE_ROOT_FIELDS = ("set_id", "reference_version", "reference_templates", "reference_modules")

_REF_VERIFIED: dict[str, str] = {}


def build_reference_manifest() -> dict:
    """**参考面**的清单：40 个 `solve.py` + 参考模块。**不含任何 agent 看得见的东西。**"""
    rows = P.load_params(PARAMS)
    tpl: dict[str, dict[str, str]] = {}
    for r in rows:
        key = f"{r['stage']}/{r['template_id']}"
        if key in tpl:
            continue
        d = _REPO / "genetask" / "templates" / r["stage"] / r["template_id"]
        tpl[key] = {f: _sha(d / f) for f in REFERENCE_TEMPLATE_FILES if (d / f).is_file()}
    mods = {f: _sha(_REPO / f) for f in REFERENCE_MODULE_FILES if (_REPO / f).is_file()}
    missing = [f for f in REFERENCE_MODULE_FILES if not (_REPO / f).is_file()]
    if missing:
        raise SystemExit(f"参考模块缺文件：{missing} —— 缺文件不等于「这一版没有它」")
    return {
        "set_id": "v1.0-smoke",
        "reference_version": REFERENCE_VERSION,
        "revisions": REFERENCE_REVISIONS,
        "reference_templates": tpl,
        "reference_modules": mods,
        "note": ("**答案面**：40 个 oracle 参考解与它们的公共主干。agent 永远看不见这些。"
                 "与任务集清单分开编号 —— 前者回答「我们算 gold 的方式变了吗」，"
                 "后者回答「agent 看到的东西变了吗」。可比性要求**两者都相同**。"),
    }


def reference_root(manifest: dict) -> str:
    payload = {k: manifest.get(k) for k in REFERENCE_ROOT_FIELDS}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def reference_ref(manifest_path: Path = None, *, verify: bool = True) -> dict:
    """参考面的最小引用。`verify=True` **现算并逐段比对**（D-27 实施要求）。

    两段：`reference_templates`（40 个 solve.py）与 `reference_modules`（公共主干）。
    **一段一条红测试**，不许一条笼统的「整体一致」覆盖两段。
    """
    path = manifest_path or REFERENCE_OUT
    if not path.is_file():
        raise SystemExit(f"参考清单不在：{path} —— 先 `python3 ops/freeze_v10.py --write-reference`")
    m = json.loads(path.read_text(encoding="utf-8"))
    recorded = reference_root(m)
    if verify:
        key = str(path)
        if _REF_VERIFIED.get(key) != recorded:
            cur = build_reference_manifest()
            for sect, label in (("reference_templates", "参考解（solve.py）"),
                                ("reference_modules", "参考模块（公共主干）")):
                drift = {k: v for k, v in cur[sect].items() if m.get(sect, {}).get(k) != v}
                drift.update({k: None for k in m.get(sect, {}) if k not in cur[sect]})
                if drift:
                    raise SystemExit(
                        f"参考清单与工作树不符：**{label}变了**（{len(drift)} 项）——"
                        f"{sorted(drift)[:4]}\n不得出通行证；"
                        f"先 `python3 ops/freeze_v10.py --write-reference` 并在 "
                        f"REFERENCE_REVISIONS 记因")
            _REF_VERIFIED[key] = recorded
    return {"set_id": m["set_id"], "reference_version": m["reference_version"],
            "reference_root": recorded}


def build_manifest_with_root() -> dict:
    m = build_manifest()          # 含实例段：`instances_fingerprint` 在 ROOT_FIELDS 里（⑤）
    m["root"] = manifest_root(m)          # 自记根：人工核对与 bundle 通行证比的是同一个数
    return m


def _diff_sections(old: dict, cur: dict, sections: tuple[str, ...]) -> list[str]:
    """逐段逐键比 sha，返回「哪个文件不一样」的清单（空 = 这几段一致）。"""
    out: list[str] = []
    for sect in sections:
        o, c = old.get(sect) or {}, cur.get(sect) or {}
        if not isinstance(o, dict) or not isinstance(c, dict):
            if o != c:
                out.append(f"{sect}（整段不同）")
            continue
        for k in sorted(set(o) | set(c)):
            if o.get(k) != c.get(k):
                out.append(f"{sect}/{k}")
    return out


def check_all() -> int:
    """**三条轴一起核**（红队最终轮 major 7）：私有任务集轴 / 公开任务集轴 / 参考面轴。

    无开关的那条分支只核私有任务集轴 —— 手册形态① 的「版本锁自检」照它做完，
    外部用户会以为三条根都锁住了，而公开轴与参考面轴一个字都没核。
    这里把三条各重建一次、比根、逐段报差异；任一条漂了就非零退出。
    """
    rows: list[tuple[str, str, str, str, list[str]]] = []
    bad = 0

    # 私有任务集轴
    cur = build_manifest_with_root()
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
    rows.append(("任务集（private）", str(cur["set_version"]), str(old.get("set_version")),
                 cur["root"], _diff_sections(old, cur, ("code", "templates"))))

    # 公开任务集轴 —— 夹具真值在它的根里，所以换一份公开夹具而不重冻当场对得出来
    pm = build_manifest(channel="public")
    pm["root"] = manifest_root(pm)
    pold = json.loads(OUT_PUBLIC.read_text(encoding="utf-8")) if OUT_PUBLIC.is_file() else {}
    rows.append(("任务集（public）", str(pm["set_version"]), str(pold.get("set_version")),
                 pm["root"], _diff_sections(pold, pm, ("code", "templates", "channel_fixtures"))))

    # 参考面轴
    rm = build_reference_manifest()
    rroot = reference_root(rm)
    rold = json.loads(REFERENCE_OUT.read_text(encoding="utf-8")) if REFERENCE_OUT.is_file() else {}
    rows.append(("参考面", str(rm["reference_version"]), str(rold.get("reference_version")),
                 rroot, _diff_sections(rold, rm, ("reference_templates", "reference_modules"))))

    for name, ver_now, ver_rec, root_now, diffs in rows:
        root_rec = None
        if name.startswith("任务集（private"):
            root_rec = old.get("root")
        elif name.startswith("任务集（public"):
            root_rec = pold.get("root")
        else:
            root_rec = reference_root(rold) if rold else None
        ok = (not diffs) and ver_now == ver_rec and (root_rec is None or root_rec == root_now)
        mark = "一致" if ok else "**漂了**"
        print(f"[{mark}] {name}：清单记 {ver_rec} / 现算 {ver_now}")
        print(f"        根 现算 {root_now}")
        if root_rec and root_rec != root_now:
            print(f"        根 清单 {root_rec}  ← 不等")
        for d in diffs[:20]:
            print(f"        差异 {d}")
        if len(diffs) > 20:
            print(f"        …… 还有 {len(diffs) - 20} 条")
        if not ok:
            bad += 1
    if bad:
        print(f"{bad} 条轴漂了 —— 重冻的命令：--write / --write-public / --write-reference", file=sys.stderr)
        return 1
    print("三条轴全部与冻结清单一致。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="落盘任务集清单（首次冻结或批准后重冻）")
    ap.add_argument("--write-reference", action="store_true",
                    help="落盘**参考面**清单（oracle 改动后推 r 号）")
    ap.add_argument("--write-public", action="store_true",
                    help="落盘**公开通道**清单（N-605：公开轴自己的 SET_VERSION_PUBLIC 与根）")
    ap.add_argument("--with-instances", action="store_true",
                    help="**已成默认、保留只为向后兼容**：`instances_fingerprint` 2026-09-10 进了 "
                         "`ROOT_FIELDS`（用户裁定 ⑤），没有实例段就算不出根，所以 `--write` 一律带实例段。"
                         "加不加这个开关结果相同")
    ap.add_argument("--instances-dry", action="store_true",
                    help="只打印实例层的漂移报告（不写盘、不推版本）")
    ap.add_argument("--check-all", action="store_true",
                    help="**三条轴一起核**：私有任务集轴 / 公开任务集轴 / 参考面轴。"
                         "不带开关的那条分支只核私有任务集轴")
    a = ap.parse_args()
    if a.check_all:
        return check_all()
    if a.write_reference:
        rm = build_reference_manifest()
        REFERENCE_OUT.parent.mkdir(parents=True, exist_ok=True)
        REFERENCE_OUT.write_text(json.dumps(rm, ensure_ascii=False, indent=1) + "\n",
                                 encoding="utf-8")
        _REF_VERIFIED.clear()
        print(f"参考面已冻结 → {REFERENCE_OUT}")
        print(f"  参考版本 {rm['reference_version']}  根 {reference_root(rm)}")
        print(f"  {len(rm['reference_templates'])} 个模板的 solve.py / "
              f"{len(rm['reference_modules'])} 个参考模块")
        return 0
    if a.write_public:
        pm = build_manifest(channel="public")
        pm["root"] = manifest_root(pm)
        OUT_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
        OUT_PUBLIC.write_text(json.dumps(pm, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        _VERIFIED.clear()
        print(f"公开通道已冻结 → {OUT_PUBLIC}")
        print(f"  公开版本 {pm['set_version']}  根 {pm['root']}")
        print(f"  夹具真值 {sum(len(v) for v in pm['channel_fixtures'].values())} 件 / "
              f"{len(pm['channel_fixtures'])} 道题")
        return 0
    if a.instances_dry:
        # **只看漂移，不写盘**（W3 收口时的用法）：现算实例层，与已冻结清单里记的比。
        sec = build_instances_section()
        fp = instances_fingerprint(sec)
        old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.is_file() else {}
        was = old.get("instances_fingerprint")
        print(json.dumps({"bases": sec["counts"]["bases"],
                          "instances": sec["counts"]["instances"],
                          "per_stage": sec["counts"]["per_stage"],
                          "instances_fingerprint": fp,
                          "recorded": was,
                          "drift": (was is not None and was != fp),
                          "note": ("清单里还没有 instances 段 —— 首次写入用 "
                                   "`--write --with-instances`（要先人工签字）")
                          if was is None else "已记录，比对如上"},
                         ensure_ascii=False, indent=1))
        return 0
    # `build_manifest()` 自 2026-09-10 起默认带实例段（⑤），根也是在带着它的清单上算的。
    # **不要在这里再算一遍**：`build_instances_section()` 要 3 秒、130 道题重建一次，
    # 而且算完覆盖回去会让人以为根是在覆盖之前算的 —— 那正是要避免的读法。
    cur = build_manifest_with_root()
    assert "instances_fingerprint" in cur, "build_manifest 没带实例段 —— 它在 ROOT_FIELDS 里"
    if a.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(cur, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"已冻结 → {OUT}")
        print(f"  根 hash {cur['root']}")
        print(f"  {cur['counts']['drafted']} 题起草 / {cur['counts']['released']} 题出集 / "
              f"{cur['counts']['held']} 题挂起；模板 {len(cur['templates'])} 个")
        return 0
    if not OUT.is_file():
        print(f"没有已冻结的清单（{OUT}）—— 先跑一次 --write", file=sys.stderr)
        return 2
    old = json.loads(OUT.read_text(encoding="utf-8"))
    inputs, fatal = [], []
    for sect in ("code", "templates"):
        for k in sorted(set(old[sect]) | set(cur[sect])):
            if old[sect].get(k) != cur[sect].get(k):
                inputs.append(f"{sect}/{k}")
    if "instruction_fingerprint" not in old:
        # 别把「旧清单没有这个字段」说成「题面变了」—— 那是会让人白查一遍的误报。
        inputs.append("旧清单没有 instruction_fingerprint（本次新增字段）—— 重冻一次即可")
    elif old["instruction_fingerprint"] != cur["instruction_fingerprint"]:
        fatal.append("**题面指纹变了** —— 题面本身不同了，必须人工签字后才可重冻")
    if [t["task_id"] for t in old["released_tasks"]] != [t["task_id"] for t in cur["released_tasks"]]:
        fatal.append("**出集清单变了**")
    if fatal:
        print("冻结漂移（致命）：\n  " + "\n  ".join(fatal + inputs), file=sys.stderr)
        return 1
    if inputs:
        # 输入变了但题面没变：常见于给打包器加与渲染无关的代码。报出来但不判致命 ——
        # 重冻即可，不必惊动签字人。**不要**因为「反正题面没变」就不报：
        # 输入变了意味着下一次改动可能就会改到题面，记录在案才追得回来。
        print("输入已变、题面未变（重冻即可）：\n  " + "\n  ".join(inputs), file=sys.stderr)
        return 3
    print(f"与冻结清单一致（{cur['counts']['released']} 题出集，模板 {len(cur['templates'])} 个）")
    print("  注意：这条分支**只核了私有任务集轴**（ops/manifests/v1.0-smoke.json）。"
          "公开任务集轴与参考面轴要 `--check-all`。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
