# -*- coding: utf-8 -*-
"""**oracle 的 I/O 契约 —— 与 agent 的 I/O 契约同形**（裁定 2026-09-05）。

> 读**标准位置**的任务规格 → 经**网关**取数 → 写**标准 artifact 路径**。
> 其余**不接受任何 stage 特定的 env / argv**。

**为什么立这条原则**：40 题的 oracle 一次都没跑过，于是七个阶段长出了
**六套互不相同的调用约定** —— 光「artifact 写哪里」就有四个名字
（`GENEBENCH_ORACLE_OUT` / `GENEBENCH_ARTIFACT` / `GENEBENCH_ARTIFACT_PATH` /
`sys.argv[1]`），还有两套「任务规格从哪来」（env 里塞 JSON vs 读文件）。
它们从没冲突过，因为**没有一个被执行过**。

**同形的理由不是整洁，是可比性**：oracle 是 gold 的来源，agent 是被测方。
两者的输入若来自不同的地方，「同一道题」这句话就没有定义 ——
而主表上每一个数都建立在这句话上。

**落点**（`solve.py` 位于 `<task_dir>/solution/solve.py`）：

| | |
| --- | --- |
| 任务规格 | `<task_dir>/task.yaml` + `<task_dir>/taskspec.json` |
| 网关 | `GENEBENCH_GATEWAY_URL`（**唯一**允许的环境变量，因为它是**部署事实**不是任务事实）|
| 产出 | `GENEBENCH_ORACLE_OUT`，缺省 `<task_dir>/solution/artifact.json` |

`GENEBENCH_GATEWAY_URL` 是唯一例外：网关地址在 f01 与容器里不同，
那是**部署**的差异，不是**题目**的差异。凡是能从 task.yaml 读出来的东西，
一律不许再从 env 拿 —— env 里的那份可以与题面不一致，而没有任何东西会说。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

#: 唯一允许的 stage 无关环境变量（部署事实）。
GATEWAY_ENV = "GENEBENCH_GATEWAY_URL"
OUT_ENV = "GENEBENCH_ORACLE_OUT"
DEFAULT_GATEWAY = "http://192.168.1.48:18080"

#: oracle 固定以这个身份走网关。日志按 `(task_id, config_id)` 切片，
#: 而 `config_id` **不是**被测方能选的东西。
CONFIG_ID = "oracle"
ARM = "strict"


class OracleIOError(RuntimeError):
    pass


@dataclass(frozen=True)
class Context:
    """一次 oracle 运行的全部输入。**都从任务目录读出来，没有一样来自 env。**"""

    task_dir: Path
    task: dict
    spec: dict
    gateway: str
    out: Path

    @property
    def task_id(self) -> str:
        return self.task["task_id"]

    @property
    def stage(self) -> str:
        return self.task["stage"]

    @property
    def as_of(self) -> str:
        return self.task["as_of"]

    @property
    def window(self) -> dict:
        return dict(self.task["window"])

    @property
    def universe(self) -> str:
        return self.task.get("universe")

    @property
    def declarations(self) -> dict:
        """已声明字段原样回填；**欠定字段写显式 `"unresolved"`**。

        不是 `null`、也不是缺失 —— 三者在校验器里是三个不同的结论
        （`declaration_mismatch` / `underdetermined_field_missing` / 静默通过）。
        """
        d = dict(self.spec["declared"])
        for f in self.spec["underdetermined"]:
            d[f] = "unresolved"
        return d

    def headers(self) -> dict:
        return {"x-genebench-task-id": self.task_id, "x-genebench-config-id": CONFIG_ID}


def context(solve_file: str) -> Context:
    """从 `solve.py` 的位置推出全部输入。

    `solve.py` 住在 `<task_dir>/solution/`，所以任务目录是它的**祖父**目录。
    读不到规格就抛 —— **不猜、不用默认值**：一个用默认值跑出来的 oracle
    会产出一份看起来合法、却与题面无关的 gold。
    """
    import yaml

    td = Path(solve_file).resolve().parent.parent
    ty, ts = td / "task.yaml", td / "taskspec.json"
    for f in (ty, ts):
        if not f.is_file():
            raise OracleIOError(
                f"任务规格缺失：{f}。oracle 必须从**标准位置**读规格 —— "
                f"读不到就停，不许用默认值跑出一份与题面无关的 gold")
    task = yaml.safe_load(ty.read_text(encoding="utf-8"))
    spec = json.loads(ts.read_text(encoding="utf-8"))
    if task.get("task_id") != spec.get("task_id"):
        raise OracleIOError(
            f"task.yaml 与 taskspec.json 的 task_id 不一致："
            f"{task.get('task_id')!r} vs {spec.get('task_id')!r} —— "
            f"两个独立来源的同一个标识符必须对齐（D-21）")
    return Context(
        task_dir=td, task=task, spec=spec,
        gateway=os.environ.get(GATEWAY_ENV, DEFAULT_GATEWAY).rstrip("/"),
        out=Path(os.environ.get(OUT_ENV) or (td / "solution" / "artifact.json")),
    )


def envelope(ctx: Context, payload: dict, *, schema_version: str = "1.0",
             provenance: list | None = None) -> dict:
    """标准信封。`produced_at` 用本地时钟 —— 它是**产出时刻**，不是取数时刻。

    取数时刻是 `payload.fetches[i].fetched_at`，那个**必须**来自网关回显的
    `x-genebench-ts`（见 `gateway/app.py::TS_HEADER`），两者不要混。
    """
    import datetime as _dt

    return {
        "schema_version": schema_version,
        "artifact_id": f"{ctx.task_id}-{CONFIG_ID}",
        "stage": ctx.stage,
        "task_id": ctx.task_id,
        "config_id": CONFIG_ID,
        "arm": ARM,
        "seed": 0,
        "as_of": ctx.as_of,
        "produced_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="milliseconds"),
        "provenance": list(provenance or []),
        "declarations": ctx.declarations,
        "payload": payload,
    }


def write_private(path: Path, obj) -> Path:
    """写 JSON 并**立刻收紧到 0600**（红线 5）。

    oracle 除了标准 artifact 路径还会往 `gold/` 里落副产物（逐日台账、会话摘要……）。
    那些 `write_text` 一律吃 umask，落出来是 **0664** —— 组与其它可读，
    而 gold 是答案面。2026-09-05 网关的 ExecStartPre 守门（`ops/guard_modes.py`）
    在重启时抓到两条，S7 的产物其实也一直是 0664，只是网关一直没重启所以没现形。
    **副产物也是答案面**：写它们要走这里，不要各写各的 `write_text`。
    """
    import json as _json
    import genebench_config as cfg
    cfg.create_dir(Path(path).parent)
    if isinstance(obj, (bytes, bytearray)):
        # 面板 / 台账这类**已经按契约编好码**的副产物（S2 的 panel.csv 就是 `to_csv(...).encode("utf-8")`）：
        # 原样落，不要再过一遍 str —— 过一遍就可能改行尾、改浮点写法，而那两样都进 sha。
        Path(path).write_bytes(bytes(obj))
    else:
        Path(path).write_text(
            obj if isinstance(obj, str) else _json.dumps(obj, ensure_ascii=False, indent=1),
            encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return Path(path)


def write(ctx: Context, artifact: dict) -> Path:
    """写到标准路径并收紧权限。返回落点。"""
    import genebench_config as cfg

    cfg.create_dir(ctx.out.parent)          # 裸 mkdir 的中间层受 umask 管 → 0775（红线 5）
    ctx.out.write_text(json.dumps(artifact, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(ctx.out, 0o600)
    except OSError:
        pass
    return ctx.out
