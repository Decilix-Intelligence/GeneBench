"""echo-min —— GeneBench 最小 P1 harness 的驱动程序。

它**不调用模型**，只做启动契约文档（`harnesses/README.md`）声称的四件事：
  ① HOME 指到可写处并 mkdir（由 launch.json 的 command 做）；
  ② 以 `/task/INSTRUCTION.md` 的内容为题面；
  ③ base URL 只从 env_required 列的变量取（本 harness 不调模型，只把变量读出来回声）；
  ④ 结束前把产物写到 `/task/artifact.json`。

存在的理由是**验证那份文档**：一个不调模型、行为完全确定的容器，
把「启动契约有没有写对」与「agent 聪不聪明」这两件事分开。
所有口径一律写 "unresolved" —— 它没有读题的能力，这是诚实的自报，
不是静默补全（`integrations/README.md` §1④ 的第 1 条）。
"""
import json
import os
import pathlib
import sys
import datetime

TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))


def _default_for(spec):
    """按 JSON Schema 的 type 给一个**空**的占位值。

    刻意不猜业务值：数组给 []、对象给 {}、字符串给 "unresolved"。
    数值型给 0 会被读成「量到了，值就是零」（手册 §6.5「空 ≠ 0」），
    所以这里对数值型**不填**，让判据看见「缺」而不是看见一个编出来的 0。
    """
    t = spec.get("type")
    if t == "array":
        return []
    if t == "object":
        return {}
    if t == "string":
        return "unresolved"
    if "enum" in spec:
        return spec["enum"][0]
    return None


def main():
    stage = os.environ.get("GENEBENCH_STAGE") or ""
    task_id = os.environ.get("GENEBENCH_TASK_ID", "")
    if not stage:
        stage = task_id.split("-", 1)[0].upper() if task_id else ""

    instruction = ""
    p = TASK / "INSTRUCTION.md"
    if p.exists():
        instruction = p.read_text(encoding="utf-8")

    # 结构契约：题面同级的 <stage>.json（大小写两种都试，文档只写了 `/task/{stage}.json`）
    contract = None
    for name in (f"{stage}.json", f"{stage.lower()}.json"):
        c = TASK / name
        if c.exists():
            contract = json.loads(c.read_text(encoding="utf-8"))
            break

    decls, payload = {}, {}
    if contract:
        props = contract.get("properties", {})
        for k in props.get("declarations", {}).get("required", []):
            decls[k] = "unresolved"
        pay = props.get("payload", {})
        for k in pay.get("required", []):
            v = _default_for(pay.get("properties", {}).get(k, {}))
            if v is not None:
                payload[k] = v

    as_of = "unresolved"
    for line in instruction.splitlines():
        if "as_of" in line:
            for tok in line.replace("=", " ").replace("：", " ").replace(":", " ").split():
                t = tok.strip("`\"'，。,;)")
                if len(t) == 10 and t[4] == "-" and t[7] == "-":
                    as_of = t
                    break
        if as_of != "unresolved":
            break

    art = {
        "schema_version": "1.0",
        "artifact_id": f"echo-min:{os.environ.get('GENEBENCH_RUN_ID', 'norun')}",
        "stage": stage,
        # 身份三键逐字取环境变量 —— harness 不许代写、不许改写成一致
        "task_id": task_id,
        "config_id": os.environ.get("GENEBENCH_CONFIG_ID", ""),
        "arm": os.environ.get("GENEBENCH_ARM", ""),
        "seed": int(os.environ.get("GENEBENCH_SEED", "1") or 1),
        "as_of": as_of,
        "produced_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "provenance": [],
        "declarations": decls,
        "payload": payload,
    }
    out = TASK / "artifact.json"
    out.write_text(json.dumps(art, ensure_ascii=False, indent=2), encoding="utf-8")

    # 回声：证明启动契约里那几样东西真的到了容器里（值不打印，只打印有没有）
    print("echo-min: 启动契约自检")
    print(f"  INSTRUCTION.md   {len(instruction)} 字符")
    print(f"  结构契约          {'有' if contract else '没有'}（找的是 /task/{stage}.json）")
    print(f"  /task/protocol/  {'有' if (TASK / 'protocol').is_dir() else '没有'}（只有 strict 臂该有）")
    for k in ("OPENAI_BASE_URL", "OPENAI_API_KEY", "GENEBENCH_GATEWAY",
              "GENEBENCH_TASK_ID", "GENEBENCH_RUN_ID", "GENEBENCH_CONFIG_ID", "GENEBENCH_ARM"):
        print(f"  {k:<20} {'有' if os.environ.get(k) else '**没有**'}")
    print(f"  HOME={os.environ.get('HOME', '')} 可写={os.access(os.environ.get('HOME', '/'), os.W_OK)}")
    print(f"  写出 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
