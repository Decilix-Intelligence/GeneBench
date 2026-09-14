# `example_minimal` —— 30 行的 P2 接入

这是一个**真能跑**的被测系统，不是示意代码。它存在的理由只有一个：
把 [`../README.md`](../README.md) 的八步压成一份**可以照着改**的东西。

[`run.py`](run.py) 正文恰好 30 行，做三件事 —— 正好是 P2 的三件责任：

1. 从 `/task/INSTRUCTION.md` 读题（**唯一题面**；`task.yaml` 不在容器里）；
2. 用垫片经网关取一段 bars（带 `as_of`、带身份头、显式 `fields`、闭区间）；
3. 用 `emit` 写 `/task/artifact.json`（S1 取数留痕）。

## 目录里的五件套

| 文件 | 说明 |
| --- | --- |
| [`run.py`](run.py) | 主程序，30 行 |
| [`Dockerfile`](Dockerfile) | `FROM gb-base:bookworm-r1` + 垫片 + `run.py`；依赖全在构建期装完 |
| [`launch.json`](launch.json) | 六个键；`paradigm: "P2"`；命令里的 `$` 写成 `$$` |
| [`config.yaml`](config.yaml) | 七个键；`enabled: false`（本例不调模型，这一条只作模板） |
| [`pin.json`](pin.json) | D-21 的七个键。本例是仓库自带代码，没有上游论文/仓库，所以前五项是 `null` —— **接真系统时它们不许是 `null`**，`commit` 与 `dist` 至少要有一个 |
| [`smoke.sh`](smoke.sh) | 在 f01 上不起容器地跑一遍并过 validator |

## 跑一遍

```bash
cd /data/shared/genebench/repo && sh integrations/example_minimal/smoke.sh
```

它会在 `$GENEBENCH_ROOT/scratch/example_minimal/task/` 造一份假题面，用**独立身份**
（`run_id=exmin.smoke.<pid>`、`config_id=example-minimal-smoke`）打生产网关，
把产物写出来，再造一份 strict 臂的 `/task/protocol/`，最后跑一次协议 validator。

**不需要 `gateway_lock`**：这是一次几十个请求以内的只读走查，且身份独立，
不与任何真跑的切片键冲突。

**`/task/protocol/` 是五件东西，不是一件。** 除 `validate_artifact.py` 外还有
**逐题生成的四份规则 JSON**（`artifact_schema.json` / `contract.json` /
`payload_depends_on.json` / `task.json`）—— 真跑时它们由注入器在 f01 生成后进 bundle，
`smoke.sh` 走的是同一条路（`genetask.protocol_rules.write_rules`），所以走查过的
就是容器里那一份。只把 `validate_artifact.py` 拷过去的话，它会当场说
「规则文件缺失：…/artifact_schema.json —— validator 不猜规则，缺一个就不跑」：
**那是对的行为，不是环境坏了。**

还有一个差别会绊人：**容器里不用带 `--rules-dir`**（注入器把四份 JSON 放在
`validate_artifact.py` 同目录，默认值正好是它），**在 f01 上手工验时要带**。

## 三件它刻意不做的事

* **不给 `as_of` 编默认值。** 槽位缺了当场退出。猜出来的那个值会让越界变成合法请求，
  而产物上完全看不出来。
* **不把越界窗口截回 `as_of`。** 题面给什么就送什么，由网关判 403 —— 自己截会让
  那次前视尝试在 access_log 上消失，而结算只认 access_log。
* **题面没给的口径标 `"unresolved"`，不填默认值。** 本例的 `data_version` 就是这样：
  假题面里没有这个口径，所以产物里它是显式的 `"unresolved"`，而不是随手写一个 `"v1"`。
  静默补全 (`silent_completion`) 是被单独测量的一族行为，不是"合理的工程决定"。

另外：`cli.ledger` 里**被拒的那些请求也在**，也照样进 `payload.fetches`。
如实记录尝试过的全部操作对你有利 —— 删掉不会让你得分，合法性判定在评分器那边，
它读的是网关日志，不是你的产物。

## LLM 怎么接

本例**不调模型**（S1 是取数留痕，没有需要模型判断的地方）。真要接只有两行：

```python
import os
from openai import OpenAI                      # 或任何兼容 SDK
llm = OpenAI(base_url=os.environ["OPENAI_BASE_URL"],   # 边车的反向代理
             api_key=os.environ["OPENAI_API_KEY"])     # 占位 key，照传即可
```

三条约束：

* **base URL 只从环境变量取**，绝不写死主机名 —— 写死就绕过了边车，
  那条路上没有 usage、没有预算闸、什么都看不见。
* **自带一把 key 直连 → 403 `foreign_credential`。**
* **每 run 100 次调用 / 600,000 tokens**，超了返回 **429 `budget_exceeded`**。
  预算耗尽不是故障，是这次运行结束了；把重试与自检的调用数算进去。

接了模型之后记得把 `launch.json` 的 `env_required` 补上
`OPENAI_BASE_URL` / `OPENAI_API_KEY`，并把 `config.yaml` 的 `enabled` 翻成 `true`。

## 换成你自己的题时要改的一处

[`run.py`](run.py) 的 `slot()` 用一条正则收题面固定槽的三种写法
（`- as_of: 2026-07-31`、表格行、`` `as_of` = ... ``）。你那道题的题面写法不同时，
**它会退出并告诉你缺哪个槽**，不会猜一个默认值继续跑。改 `slot()` 就行。
