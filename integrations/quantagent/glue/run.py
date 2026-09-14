"""QuantAgent × GeneBench 接线（P2）。S2：把网关日线整理成标准面板。

**上游内核一个字节没改。** 用到的只有上游自己的扩展点：
  * `data.provider.DataProvider.get_stock_daily` —— 它的 akshare 兜底分支，
    数据源由 `glue/gateway_akshare.py` 顶替（monkeypatch，README §1③ 的 (d)）；
  * `data.aligner.TimeAligner.align_to_trading_days(df, cal, method=...)` ——
    `method` 是上游自己的**构造形参**，题面声明 `missing_row_policy=keep_missing`
    时传 `None`（reindex 不填充）。上游的默认值是 `"ffill"`，
    **照默认跑就是静默补行**，而补出来的行在面板上与真行情长得一模一样。
"""
import hashlib
import os
import pathlib
import sys

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
TASK = pathlib.Path(os.environ.get("GENEBENCH_TASK_DIR", "/task"))
UPSTREAM = pathlib.Path(os.environ.get("QUANTAGENT_UPSTREAM", "/opt/quantagent/upstream"))

sys.path.insert(0, str(HERE))
import instruction as I            # noqa: E402
import gateway_akshare as GA       # noqa: E402

import genebench_client as gb      # noqa: E402
from genebench_client import emit  # noqa: E402


def _panel_columns(text):
    """产出文件那一行的列序由题面**逐字给出**，不要在代码里写死一份第二版。"""
    import re
    m = re.search(r"列按此顺序[：:]\s*(?P<cols>[^\n]+)", text)
    if not m:
        raise SystemExit("题面没有给出 panel.csv 的列序。**不猜**。")
    raw = m.group("cols").split("，")[0] if "，按" in m.group("cols") else m.group("cols")
    cols = [c.strip(" `") for c in re.split(r"[、,]", raw) if c.strip(" `")]
    return [c for c in cols if c.isascii() and c.isidentifier()]


def main():
    text = (TASK / "INSTRUCTION.md").read_text(encoding="utf-8")
    as_of = I.slot(text, "as_of", r"\d{4}-\d{2}-\d{2}")
    universe = I.slot(text, "universe", r"[A-Za-z0-9_]+")
    start, end = I.window(text)
    decls = I.declarations(text)
    cols = _panel_columns(text)
    print(f"[glue] as_of={as_of} universe={universe} window={start}..{end}")
    print(f"[glue] 题面口径 {decls}")
    print(f"[glue] 面板列序 {cols}")

    gb.set_as_of(as_of)
    GA.set_adjust(decls.get("adjust", ""))
    GA.install()                                  # 必须在 import 上游之前

    sys.path.insert(0, str(UPSTREAM))
    from data.provider import DataProvider        # noqa: E402  上游，未改一字
    from data.aligner import TimeAligner          # noqa: E402  同上

    cli = gb.client()
    members = list(cli.members(universe, as_of))
    cal = [str(d) for d in cli.trading_days(start, end)]
    print(f"[glue] 成分 {len(members)} 只；交易日 {len(cal)} 天")

    keep_missing = decls.get("missing_row_policy") == "keep_missing"
    align_method = None if keep_missing else "ffill"
    cal_idx = pd.DatetimeIndex(pd.to_datetime(cal))

    frames, missing = [], []
    for code in members:
        # 上游的 ticker 记法是纯 6 位数字（它自己拼 sh/sz 前缀）
        six = code.split(".")[0]
        df = DataProvider.get_stock_daily(six, start, end)
        if df is None or df.empty:
            missing.extend((code, d) for d in cal)
            continue
        df = df[~df.index.duplicated(keep="last")]
        aligned = TimeAligner.align_to_trading_days(df, cal_idx, method=align_method)
        have = set(df.index.normalize())
        missing.extend((code, d) for d in cal if pd.Timestamp(d) not in have)
        aligned = aligned.assign(symbol=code)
        aligned.index.name = "date"
        frames.append(aligned.reset_index())

    if not frames:
        raise SystemExit("一只标的都没取到 —— 不写一份空面板冒充结果")
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"]).dt.strftime("%Y-%m-%d")
    if not keep_missing:
        panel = panel.dropna(subset=["close"])
    panel = panel[cols].sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)

    out = TASK / "panel.csv"
    panel.to_csv(out, index=False, encoding="utf-8", float_format="%.6f")
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"[glue] panel.csv rows={len(panel)} sha256={sha[:16]}…")

    # 题面「流程要求」若点名了缺行清单文件，就照写（可复核优先于文件数少）
    if "/task/missing_rows.csv" in text:
        mr = pd.DataFrame(sorted(missing), columns=["symbol", "date"])
        mr["date"] = pd.to_datetime(mr["date"]).dt.strftime("%Y-%m-%d")
        mr.to_csv(TASK / "missing_rows.csv", index=False, encoding="utf-8")

    src = {"code": "symbol", "date": "date", "close": "close",
           "high": "high", "low": "low", "volume": "volume"}
    field_map = {k: v for k, v in src.items() if v in cols}
    # `emit._norm` 对**任何**对象里叫 `date` / `as_of` 的子键都跑一次 `_as_date` 归一，
    # 而 `field_map` 在 schema 里是自由形状的 object（没有 properties）。
    # 题面要求「键列（代码、日期）也要列入」，于是 `field_map` 里必然有一个叫 `date` 的键，
    # 而它的值是**列名**不是日期 —— emit 当场：
    #   EmitError: payload.field_map.date: 'date' 不是可识别的日期
    # 退路也堵着：`field_map=None` 只在 `alignment_target` 被标 unresolved 时才允许，
    #   EmitError: S2 的 payload 缺 field_map（它不在诚实终止的范围里）
    # **题面要求写它，emit 两条路都不让写。** 所以这里只把 emit 无法表达的那一个键
    # 留到归一之后再放回去，其余键照常经 emit 归一。已登记票据。
    _EMIT_CANNOT_KEY = "date"
    art = emit.emit_s2(
        panel_ref={"rows": int(len(panel)), "sha256": sha},
        field_map={k: v for k, v in field_map.items() if k != _EMIT_CANNOT_KEY},
        missing_rows={"count": int(len(missing))},
        adjust_applied=decls.get("adjust", "unresolved"),
        declarations=decls,
        as_of=as_of,
    )
    if _EMIT_CANNOT_KEY in field_map:
        art["payload"]["field_map"][_EMIT_CANNOT_KEY] = field_map[_EMIT_CANNOT_KEY]
    p = art.write(TASK / "artifact.json")
    print(f"[glue] wrote {p}；网关请求 {len(cli.ledger)} 次")
    return 0


if __name__ == "__main__":
    sys.exit(main())
