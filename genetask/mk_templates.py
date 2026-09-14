# -*- coding: utf-8 -*-
"""生成八阶段各一份**基础模板**（卡 3.1 的实例化验收用；卡 3.2 按科目扩模板）。

每个模板目录：template.yaml（slots）、INSTRUCTION.strict.md、INSTRUCTION.open.md、Dockerfile、
tests/test_outputs.py、scorer.yaml、solve.py。题面全部用占位符，不写字段值。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reference.artifact_schema import DECLARATION_FIELDS   # noqa: E402
from reference import artifact_schema as sch          # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "templates"

GOALS = {
    # 两臂各自措辞，但**要做的事**必须一一对应（E4 按 STAGE_CONCEPTS 扫）。
    "S1": ("经数据网关取指定窗口的日线，把每次取数（含空结果与被拒）的时间与结果状态如实记录。",
           "查出指定窗口内的日线数据，如实记录每次取数（含空结果与被拒）的时间与结果状态。"),
    "S2": ("把网关返回的日线对齐到 market_view 的字段命名，处理缺行与复权。",
           "把取到的数据整理成标准面板：字段命名对齐、处理复权、缺行照实保留。"),
    "S3": ("按给定表达式实现因子并在窗口内计算，产出里要有 values_ref、nonfinite 非有限值计数、warmup 暖机期、degeneracy 退化报警。",
           "实现题面给的因子并算出每日每票的值，如实报告非有限值（Inf/NaN）、暖机期与退化情况"
           "（产出里要有 values_ref、nonfinite、warmup、degeneracy 这几个键）。"),
    "S4": ("在声明的评估设定下计算因子的 IC 统计（均值、标准差、positive_ratio、coverage、block-bootstrap 区间）。",
           "评估这个因子的预测能力：IC 的均值、标准差、正比例（positive_ratio）、覆盖率（coverage）和 bootstrap 置信区间。"),
    "S5": ("由输入因子构造信号，无观点的格子写 null、主动空仓写 flat。",
           "把因子变成交易信号\n没有观点的地方留空（null），明确不持有的地方标记为空仓（flat）。"),
    "S6": ("在声明的约束与目标下把信号变成 TargetPosition（台账六字段）。",
           "根据信号和约束给出目标持仓，每只票写清上期权重、目标权重与变动（台账六字段）。"),
    "S7": ("对给定信号做回测，报告收益、风险、换手（单边与双边分别报）、成本、记账守恒残差与收益归因。",
           "对这个信号做回测，报告收益、风险、换手（单边与双边分别报）、成本、记账守恒的残差，以及收益归因。"),
    "S8": ("在模拟交易环境里按日提交与撤销委托，记录事件链、状态迁移与成交统计。",
           "在模拟盘里下单交易，把每一步事件、状态变化和成交情况都记录下来。"),
}

DOCKERFILE = """FROM python:3.12-slim-bookworm@sha256:0000000000000000000000000000000000000000000000000000000000000000
# 依赖一律在构建期装（构建时联网、运行时断网，卡 4.1 L-8）。真 digest 在 f02 export 时钉。
#
# **统一基座**（N-62 裁定 2026-09-05）。为什么不是三个 harness 各用各的官方基座：
# 三条配置的全部意义是「同一模型、三种 harness，**固定模型效应**」。
# 实测三个基座是 python:3.12-slim / node:22-slim / RD-Agent 自带，
# pandas 只有 RD 那个有、且版本与题面钉的不一致 —— 那样主表上「harness 差异」
# 这一列里就混进了运行时差异，而 S2/S3/S7 的产出是 parquet/csv 数值，
# pandas 与 pyarrow 版本恰恰会影响它们。
#
# python 取 3.12（OpenHands 官方基座就是 3.12；题面原来钉 3.11 没有特殊理由）。
# 数值栈取**三个 harness 要求里最高的那个**（RD-Agent 的 2.3.3 / 25.0.1）。
ARG NODE_VERSION=22.23.2
ARG NODE_SHA256=d60acfe00a2932254bb0ad20e01b0d74397a0875595de719654b214f4b03f307
# Node 走**官方 tarball + 钉 sha256**，不走 `curl | bash` 的安装脚本 ——
# 后者是一条无法复核的供应链入口，而本项目对 npm 包都钉 dist_integrity。
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates xz-utils; \
    curl -fsSLo /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz"; \
    echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c -; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1; \
    rm -f /tmp/node.tar.xz; \
    apt-get purge -y curl xz-utils; apt-get autoremove -y; rm -rf /var/lib/apt/lists/*; \
    node --version; npm --version
RUN pip install --no-cache-dir pandas==2.3.3 pyarrow==25.0.1
COPY tests/ /opt/tests/
WORKDIR /task
CMD ["sh", "-c", "sleep 3600"]
"""

TESTS = """# 容器内自检：只查结构，不查对错（对错由数据面 scorer 结算）。
import json, os, pathlib

def test_artifact_exists_and_is_structural():
    p = pathlib.Path("/task/artifact.json")
    assert p.exists(), "没有产出 /task/artifact.json"
    a = json.loads(p.read_text(encoding="utf-8"))
    assert isinstance(a.get("schema_version"), str), "schema_version 必须是字符串"
    assert a.get("stage") == os.environ.get("GENEBENCH_STAGE", a.get("stage"))
    assert a.get("task_id") == os.environ.get("GENEBENCH_TASK_ID", a.get("task_id"))
"""

SCORER = """# scorer.yaml —— 本题的结算配置（数据面私有，含 gold_token）
task_id: <<task_id>>
gold_token: <<gold_token>>
validator: reference.artifact_schema.validate
taskspec: taskspec.json
"""

SOLVE = """# oracle 参考解（数据面私有；在 f01 直跑，经网关 snapshot 后端产 artifact）。gold_token: <<gold_token>>
# 本卡只放骨架；各科目的具体解法由卡 3.2 填。
def main():
    raise SystemExit("solve.py 骨架：由卡 3.2 按科目实现")

if __name__ == "__main__":
    main()
"""


def instruction(stage: str, arm: str) -> str:
    strict_goal, open_goal = GOALS[stage]
    fields = DECLARATION_FIELDS[stage]
    lines = []
    uni = "" if stage == "S1" else "<<fixed:task_universe>>"
    if arm == "strict":
        lines.append("<<fixed:preamble>>")
        lines.append(f"任务（{stage}）：{strict_goal}")
        lines.append("<<fixed:gateway_url>>")
        lines.append("<<fixed:endpoints>>")
        lines.append("<<fixed:as_of>>")
        lines.append("<<fixed:task_window>>")
        if uni:
            lines.append(uni)
        lines.append("<<fixed:inputs>>")
        if stage == "S3":
            lines.append("<<fixed:fields_required>>")
        lines.append("本次任务的口径（逐项）：")
        lines.append("<<say_each>>")
        lines.append("")                      # E11：探针句独立成**段**
        lines.append("<<fixed:no_default_fill>>")
        lines.append("")
        lines.append("<<fixed:output_format>>")
        # N-44：只给有产出文件契约的阶段加。给没有的加会得到一个**空**固定槽，
        # 而空槽比没有这个槽更坏（E3 要求每个固定槽两臂都在且非空）。
        if sch.payload_files(stage):
            lines.append("<<fixed:output_files>>")
        lines.append("<<fixed:artifact_path>>")
        lines.append("校验串：<<canary>>")
    else:
        lines.append("<<fixed:preamble>>")
        lines.append(f"{open_goal}")
        # E12：固定槽各占一行（断行不属于设计允许的臂间差异）；E12b：两臂段落骨架一致
        lines.append("<<fixed:gateway_url>>")
        lines.append("<<fixed:endpoints>>")
        lines.append("<<fixed:as_of>>")
        lines.append("<<fixed:task_window>>")
        if uni:
            lines.append(uni)
        lines.append("<<fixed:inputs>>")
        if stage == "S3":
            lines.append("<<fixed:fields_required>>")
        lines.append("本次任务的口径（逐项）：")
        lines.append("<<say_all>>")            # say_all 现在也逐条成行（E12 覆盖声明槽）
        lines.append("")
        lines.append("<<fixed:no_default_fill>>")
        lines.append("")
        lines.append("<<fixed:output_format>>")
        # N-44：只给有产出文件契约的阶段加。给没有的加会得到一个**空**固定槽，
        # 而空槽比没有这个槽更坏（E3 要求每个固定槽两臂都在且非空）。
        if sch.payload_files(stage):
            lines.append("<<fixed:output_files>>")
        lines.append("<<fixed:artifact_path>>")
        lines.append("校验串：<<canary>>")
    return "\n".join(lines) + "\n"


def main() -> None:
    for stage in DECLARATION_FIELDS:
        d = OUT / stage / "base"
        __import__("genebench_config").create_dir(d / "tests")   # 红线 5：不裸 mkdir
        (d / "template.yaml").write_text(
            "slots: [" + ", ".join(DECLARATION_FIELDS[stage]) + "]\n", encoding="utf-8")
        (d / "INSTRUCTION.strict.md").write_text(instruction(stage, "strict"), encoding="utf-8")
        (d / "INSTRUCTION.open.md").write_text(instruction(stage, "open"), encoding="utf-8")
        (d / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
        (d / "tests" / "test_outputs.py").write_text(TESTS, encoding="utf-8")
        (d / "scorer.yaml").write_text(SCORER, encoding="utf-8")
        (d / "solve.py").write_text(SOLVE, encoding="utf-8")
        print("模板", d if not str(d).startswith(str(HERE)) else d.relative_to(HERE))


if __name__ == "__main__":
    main()
