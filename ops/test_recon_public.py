# -*- coding: utf-8 -*-
"""卡 1.3 的测试：两通道对账脚本 + 公开通道数据卡的**出处核对**。

两类，判别力各自不同：

1. **对账脚本在夹具上可跑**。每一节的口径由一个**手造的小例子**钉住 ——
   例子里的答案是手算出来的，不是「跑一遍看看输出长什么样」。
   最要紧的两条是 :func:`test_gold_attribution_needs_the_compact_date_key`
   与 :func:`test_return_diff_is_decomposed_into_quote_step_and_adjustment_step`：
   前者对应一个**跑起来 ok、结论全错**的真错（日历文件是 ISO、gold 的 date 是紧凑串，
   键对不上的表现是「归不掉 100%」而不是抛异常）；后者钉住「收益率的差归到哪一类」。

2. **数据卡里每一个数都有出处**。卡里的写法是行内注释

       | 票数 | 3,575 |  <!-- src: public_v1/tables/build_info.json:codes=3575 -->

   测试把注释里的 `文件:键路径=值` 拆开，去那个文件里取那个键，比值。
   **允许格式化差异**（千分位、四舍五入到卡上显示的有效位）；
   **不允许**键不存在、值对不上、或者「注释里写的数在正文里根本没出现」。
   最后一条是防「注释对、正文错」——两处都要改才能骗过去，而那时候人已经在看数了。

数据卡是**手写**的（不像 `qlib_provider.md` 由代码生成），所以这套核对就是它与产物之间
唯一的绑定。`ops/test_public_limits.py::test_data_card_numbers_match_the_module`
管的是**口径常量**那一半，这里管的是**数**那一半，两边不重叠。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import genebench_config as cfg                                     # noqa: E402
from ops import recon_public_vs_private as R                       # noqa: E402
from snapshots import qlib_provider as qp                          # noqa: E402
from snapshots.public import manifest as PM                        # noqa: E402

CARD = cfg.DATA_CARDS / "public_channel.md"
REPORT_JSON = cfg.REPORTS / "public" / "reconciliation.json"
REPORT_MD = cfg.REPORTS / "public" / "reconciliation.md"


# =================================================================== 出处核对的机器

#: 卡里允许引用的源。**只有这三类** —— 引到别处去就是引到一个不会跟着产物走的数。
def resolve_source(name: str) -> Path:
    if name == "reconciliation.json":
        return REPORT_JSON
    if name.startswith("public_v1/"):
        return cfg.SNAPSHOTS_PUBLIC / name[len("public_v1/"):]
    raise KeyError(f"不认识的源 {name!r}；只认 reconciliation.json 与 public_v1/…")


_SEG = re.compile(r'\.([^.\[\]]+)|\["([^"]+)"\]|\[(\d+)\]')


def dig(obj, path: str):
    """键路径：``a.b["有.点的键"][0]``，末尾可加 ``|len`` 取长度。

    找不到就抛 ``KeyError`` —— **不返回 None**。返回 None 的话，卡上写 `—` 的地方
    会与「这个键根本不存在」变得没法区分。
    """
    want_len = path.endswith("|len")
    if want_len:
        path = path[:-len("|len")]
    cur = obj
    for m in _SEG.finditer("." + path if not path.startswith(("[", ".")) else path):
        key = m.group(1) or m.group(2)
        if key is None:
            cur = cur[int(m.group(3))]
            continue
        if not isinstance(cur, dict) or key not in cur:
            raise KeyError(f"{path} 里的 {key!r} 不存在")
        cur = cur[key]
    return len(cur) if want_len else cur


_NUM = re.compile(r"^[+-]?(\d+)?(?:\.(\d+))?(?:[eE][+-]?\d+)?$")
_TRUE = {"true", "True", "是"}
_FALSE = {"false", "False", "否"}


def _sig_digits(lit: str) -> int:
    m = _NUM.match(lit)
    if not m:
        return 0
    # **前导零不是有效位**：`0.0007228562` 是 7 位不是 10 位。
    # 按 10 位去比，`%.10g` 会把产物值渲染成 `0.0007228561962`，与卡上写的对不上，
    # 而卡上写的其实是对的 —— 这条错会把一张正确的卡判成红。
    digits = ((m.group(1) or "") + (m.group(2) or "")).lstrip("0")
    return max(1, len(digits))


def value_matches(value, literal: str) -> bool:
    """卡上写的 ``literal`` 与产物里的 ``value`` 是不是同一个数。

    允许的只有**格式化**差异：千分位逗号、以及四舍五入到卡上显示的**有效位数**。
    ``1.000000`` 与 ``0.99999982`` **不算相同** —— 把不是 1 的东西写成 1 正是要拦的。
    """
    lit = literal.strip().replace(",", "")
    if isinstance(value, bool):
        return (lit in _TRUE) if value else (lit in _FALSE)
    if value is None:
        return lit in {"—", "null", "None"}
    if isinstance(value, (int, float)) and _NUM.match(lit):
        if isinstance(value, int) and "." not in lit and "e" not in lit.lower():
            return value == int(lit)
        k = _sig_digits(lit)
        return float(f"%.{k}g" % float(value)) == float(f"%.{k}g" % float(lit))
    if isinstance(value, (list, tuple)):
        return (json.dumps(list(value), ensure_ascii=False) == lit
                or str(list(value)) == lit)
    return str(value).strip() == literal.strip()


_SRC = re.compile(r"<!--\s*src:\s*(?P<body>.+?)\s*-->")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
#: 出处标注的正文：``<源>:<键路径>=<值>``，或 ``n/a <理由>``（显式豁免，要写理由）。
_SPEC = re.compile(r"^(?P<file>[^\s:]+):(?P<key>[^=]+)=(?P<val>.*)$")


def parse_annotations(text: str) -> list[dict]:
    out = []
    for lineno, line in enumerate(text.split("\n"), 1):
        bare = _COMMENT.sub("", line)
        for m in _SRC.finditer(line):
            body = m.group("body")
            if body.startswith("n/a"):
                out.append({"line": lineno, "exempt": True, "why": body[3:].strip(),
                            "text": bare})
                continue
            sp = _SPEC.match(body)
            assert sp, f"第 {lineno} 行的 src 标注写法不对：{body!r}"
            out.append({"line": lineno, "exempt": False, "file": sp.group("file"),
                        "key": sp.group("key").strip(), "value": sp.group("val").strip(),
                        "text": bare})
    return out


def _token(literal: str) -> re.Pattern:
    """把标注里的值编成一个**整段**匹配（前后不能再接数字或小数点）。

    子串匹配在这里是有害的：正文被改成 `200901059` 之后，`20090105` 仍然是它的子串，
    于是「只改正文」这条变异会溜过去。
    """
    lit = re.escape(literal.strip().replace(",", ""))
    return re.compile(r"(?<![\d.])" + lit + r"(?![\d.])")


def check_card(text: str) -> list[str]:
    """核一遍卡，返回**问题清单**（空 = 通过）。返回清单而不是抛，是为了能一次看全。"""
    problems: list[str] = []
    cache: dict[str, object] = {}
    for a in parse_annotations(text):
        if a["exempt"]:
            if not a["why"]:
                problems.append(f"第 {a['line']} 行：n/a 豁免没写理由")
            continue
        try:
            p = resolve_source(a["file"])
        except KeyError as e:
            problems.append(f"第 {a['line']} 行：{e}")
            continue
        if a["file"] not in cache:
            if not p.is_file():
                problems.append(f"第 {a['line']} 行：源文件不存在 {p}")
                continue
            cache[a["file"]] = json.loads(p.read_text(encoding="utf-8"))
        try:
            v = dig(cache[a["file"]], a["key"])
        except (KeyError, IndexError, TypeError) as e:
            problems.append(f"第 {a['line']} 行：{a['file']} 里取不到 {a['key']}（{e}）")
            continue
        if not value_matches(v, a["value"]):
            problems.append(
                f"第 {a['line']} 行：{a['file']}:{a['key']} = {v!r}，卡上写的是 {a['value']!r}")
        # 千分位只是排版：正文写 `10,948,502`、标注写 `10948502` 是同一个数。
        # **必须整段匹配**：子串匹配会让「把 20090105 改成 200901059」骗过去。
        if not _token(a["value"]).search(a["text"].replace(",", "")):
            problems.append(
                f"第 {a['line']} 行：标注写的 {a['value']!r} 在这一行的正文里根本没出现"
                "（注释对、正文错，是这套核对唯一骗得过去的形态）")
    return problems


#: 需要出处的数：带千分位的整数、三位以上小数、科学计数。
#: 日期（`2026-07-31`）与节号（`§3`）不在其中。
_NEEDS_SRC = re.compile(r"\d{1,3}(?:,\d{3})+|\d\.\d{3,}|\d(?:\.\d+)?[eE][+-]?\d+")


# =================================================================== 数据卡

def test_card_exists_and_is_not_generated():
    assert CARD.is_file(), f"{CARD} 不存在"
    t = CARD.read_text(encoding="utf-8")
    assert "由 `ops/mk_gold_data_card.py` 生成" not in t, (
        "公开通道数据卡是手写的，不该带上「由代码生成」那句声明 —— "
        "带上了就会有人去改脚本而不是改卡")


def test_every_number_in_the_card_has_a_source_that_checks_out():
    problems = check_card(CARD.read_text(encoding="utf-8"))
    assert not problems, "数据卡的出处核不上：\n" + "\n".join(problems)


def test_the_checker_catches_a_wrong_number_in_the_body():
    """**判别力**：只改正文不改注释，必须红。"""
    t = CARD.read_text(encoding="utf-8")
    ann = [a for a in parse_annotations(t)
           if not a["exempt"] and a["value"] in a["text"]]
    assert ann, "卡里一条 src 标注都没有"
    a = ann[0]
    lines = t.split("\n")
    i = a["line"] - 1
    lines[i] = lines[i].replace(a["value"], a["value"] + "9", 1)
    assert check_card("\n".join(lines)), "正文里的数被改了，核对却说通过 —— 这套核对没有牙"


def test_the_checker_catches_a_wrong_number_in_the_annotation():
    """**判别力**：只改注释不改正文，也必须红。"""
    t = CARD.read_text(encoding="utf-8")
    ann = [a for a in parse_annotations(t) if not a["exempt"]]
    a = ann[0]
    lines = t.split("\n")
    i = a["line"] - 1
    lines[i] = lines[i].replace(f"={a['value']} -->", f"={a['value']}9 -->", 1)
    assert check_card("\n".join(lines)), "注释里的数被改了，核对却说通过"


def test_the_checker_catches_a_key_that_does_not_exist():
    t = ("| x | 1 |  <!-- src: reconciliation.json:"
         "returns.this_key_does_not_exist=1 -->\n")
    assert check_card(t), "键不存在，核对却说通过"


def test_rounding_is_allowed_but_rounding_a_non_one_up_to_one_is_not():
    assert value_matches(0.9999914312, "0.9999914")
    assert value_matches(0.000722856196225621, "0.0007228562"), "前导零不算有效位"
    assert value_matches(10948502, "10,948,502")
    assert value_matches(0.983981066, "0.983981")
    assert not value_matches(0.99999982, "1.000000"), (
        "把 0.99999982 写成 1.000000 必须判成不一致 —— "
        "「一致率 1」和「一致率 0.99999982」在读者那里是两回事")
    assert not value_matches(3575, "3576")


def test_lines_with_hard_numbers_carry_a_source():
    t = CARD.read_text(encoding="utf-8")
    ann_lines = {a["line"] for a in parse_annotations(t)}
    missing = []
    in_code = False
    for i, line in enumerate(t.split("\n"), 1):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or i in ann_lines:
            continue
        bare = _COMMENT.sub("", line)
        if _NEEDS_SRC.search(bare):
            missing.append(f"第 {i} 行：{line.strip()[:90]}")
    assert not missing, (
        "这些行上有需要出处的数，却没有 src 标注（确实不需要的写 "
        "`<!-- src: n/a 理由 -->` 显式豁免）：\n" + "\n".join(missing))


def test_card_cites_every_source_family():
    t = CARD.read_text(encoding="utf-8")
    files = {a["file"] for a in parse_annotations(t) if not a["exempt"]}
    assert "reconciliation.json" in files
    assert any(f.endswith("build_info.json") for f in files), (
        "卡里没有一处引 build_info.json —— 建集时的窗口 / 票数 / 文件数就没有出处了")
    assert "public_v1/calibration.json" in files, (
        "卡末尾的「τ 标定于此实现对」要引 calibration.json 里的 τ")


def test_card_reports_the_missing_frozen_artifacts_truthfully():
    """三个冻结件现在不存在。**补齐那天这条会自己变红**，逼着改卡，而不是让卡一直说缺件。"""
    t = CARD.read_text(encoding="utf-8")
    missing = [a for a in PM.PUBLIC_FROZEN_ARTIFACTS if not (_REPO / a).is_file()]
    for a in PM.PUBLIC_FROZEN_ARTIFACTS:
        assert a in t, f"卡里没列冻结件 {a}"
    if missing:
        assert "缺件" in t and "挡发布" in t, "有缺件，卡里必须写「缺件」与「挡发布」"
    else:
        assert "缺件" not in t, (
            "冻结件已经补齐了，卡里却还写着缺件 —— 这条红了就去改卡（顺带改 §7 的表）")


def test_card_keeps_the_public_channel_traps_it_is_supposed_to_carry():
    """卡 2.5 §8 点名要写进公开卡的那几件事，逐条在。"""
    t = CARD.read_text(encoding="utf-8")
    for token, why in [
        ("baostock", "源"),
        ("北交所", "覆盖面缺口"),
        ("tradestatus", "停牌在公开源里是有行 + tradestatus=0"),
        ("退市整理期", "涨跌停推导的已知误差"),
        ("change_reason", "退市整理期的判据取的是哪一列"),
        ("2026-07-06", "ST 5% 带的取消日"),
        ("复权", "复权口径"),
        ("τ 标定于此实现对", "冻结件那一节的声明"),
        ("reconciliation.md", "与私有通道的差异摘要要引对账报告"),
    ]:
        assert token in t, f"卡里缺「{token}」（{why}）"


def test_card_does_not_copy_private_channel_numbers():
    """卡 2.5 §8：**不抄私有通道的数字**。私有落点的字样出现在卡里就是抄了。"""
    t = CARD.read_text(encoding="utf-8")
    assert "snapshots/v1/gold_factors" not in t
    assert "snapshots/v1/tables" not in t
    for a in parse_annotations(t):
        if not a["exempt"]:
            assert not a["file"].startswith("v1/"), (
                f"第 {a['line']} 行引了私有通道的产物 {a['file']} —— "
                "公开卡只写公开通道自己的数")


# =================================================================== 对账脚本

def test_rel_is_symmetric_and_zero_safe():
    a = np.array([1.0, 0.0, -2.0, 1e-320])
    b = np.array([1.0, 0.0, 2.0, 0.0])
    r = R._rel(a, b)
    assert r[0] == 0.0 and r[1] == 0.0
    assert r[2] == pytest.approx(2.0)          # 反号 → 相对差 2
    assert r[3] == 0.0                         # 两边都在下溢地板之下 → 0，不是 inf
    assert np.allclose(r, R._rel(b, a))


def test_quantiles_on_an_empty_array_is_none_not_zero():
    q = R._quantiles(np.zeros(0))
    assert q["n"] == 0
    assert all(q[k] is None for k in ("min", "p50", "p90", "p99", "max")), (
        "空样本报 0 会被读成「完全一致」—— 必须是 None")


def test_expand_places_the_series_at_its_calendar_offset():
    v = R._expand(2, np.array([7.0, 8.0]), 5)
    assert np.isnan(v[0]) and np.isnan(v[1]) and v[2] == 7.0 and v[3] == 8.0
    assert np.isnan(v[4])


def test_attribution_tables_prefix_sums_count_the_window():
    bits = {"SH600000": np.array([False, True, False, False, False])}
    keys, D, C = R._attribution_tables(bits)
    assert list(keys) == ["SH600000"]
    assert D[0, 1] and not D[0, 0]
    # [t-2, t] 里有没有差异：t=3 有（第 1 天在窗内），t=4 没有
    assert (C[0, 4] - C[0, max(0, 3 - 2)]) > 0
    assert (C[0, 5] - C[0, max(0, 4 - 2)]) == 0


# ------------------------------------------------------- 夹具：provider / gold

def _mk_provider(root: Path, dates: list[str], series: dict[str, dict[str, list[float]]]):
    """按 qlib 布局造一个最小 provider。``series[qdir][field]`` 是整条日历上的值。"""
    (root / "calendars").mkdir(parents=True, exist_ok=True)
    (root / "calendars" / "day.txt").write_text("\n".join(dates) + "\n", encoding="utf-8")
    for qdir, fields in series.items():
        d = root / "features" / qdir
        d.mkdir(parents=True, exist_ok=True)
        for f in qp.FIELDS:
            qp.write_bin(d / f"{f}.day.bin", 0, np.array(fields[f], dtype="float64"))
    return qp.ProviderPaths(channel="fixture", provider_dir=root, tables_dir=root,
                            universe_pit=root / "u.parquet", data_card=root / "c.md")


def _flat(n: int, v: float) -> list[float]:
    return [v] * n


@pytest.fixture
def two_providers(tmp_path, monkeypatch):
    """两条通道，逐日相同的原始报价，但**复权因子在第 3 天走了不同的台阶**。

    手算：只有第 2→3 天那一对收益率会不同，且分解必须归到 `adjustment_step`。
    """
    dates = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]
    n = len(dates)
    raw = [10.0, 10.5, 11.0, 11.2]
    fac_a = [0.5, 0.5, 0.6, 0.6]                     # 公开：第 3 天抬了一档
    fac_b = [0.5, 0.5, 0.5, 0.5]                     # 私有：不抬

    def build(fac):
        close = [r * f for r, f in zip(raw, fac)]
        return {"sz000001": {
            "open": close, "high": [c * 1.01 for c in close],
            "low": [c * 0.99 for c in close], "close": close,
            "volume": _flat(n, 1000.0), "amount": [c * 1000.0 for c in close],
            "vwap": close, "factor": list(fac)}}

    pub = _mk_provider(tmp_path / "pub", dates, build(fac_a))
    priv = _mk_provider(tmp_path / "priv", dates, build(fac_b))
    monkeypatch.setattr(qp, "PUBLIC_PATHS", pub)
    monkeypatch.setattr(qp, "PRIVATE_PATHS", priv)
    return pub, priv


def test_return_diff_is_decomposed_into_quote_step_and_adjustment_step(two_providers):
    block, cell_diff, units = R.part_returns(verbose=False)
    at = block["attribution"]
    assert at["over"] == 1, "只有复权因子抬档的那一对该超阈"
    assert at["adjustment_step"] == 1
    assert at["raw_quote_step"] == 0 and at["neither"] == 0
    # 位图：第 3 天（下标 2）起两条通道的价位不同
    bits = cell_diff["SZ000001"]
    assert not bits[0] and not bits[1] and bits[2] and bits[3]
    assert block["full"]["return_pairs"] == 3
    assert block["full"]["agree_at_1e-6"] == 2


def test_a_constant_scale_difference_does_not_move_any_return(tmp_path, monkeypatch):
    """归一化常数不同 —— 价位级全不一样，收益率**一格都不能动**。

    这条是 §1.2 那句话的判据：拿价位级一致率当结论会得到「两条通道差得很远」，
    而实际上下游一个数都不受影响。
    """
    # 至少 10 天 —— `level_scale` 只统计有 10 个以上有效比值的票（少了没意义）
    dates = [f"2026-01-{d:02d}" for d in range(5, 20)]
    n = len(dates)
    raw = [10.0 + 0.5 * i for i in range(n)]

    def build(scale):
        close = [r * scale for r in raw]
        return {"sh600000": {
            "open": close, "high": close, "low": close, "close": close,
            "volume": _flat(n, 1.0), "amount": close, "vwap": close,
            "factor": _flat(n, scale)}}

    monkeypatch.setattr(qp, "PUBLIC_PATHS",
                        _mk_provider(tmp_path / "a", dates, build(1.0)))
    monkeypatch.setattr(qp, "PRIVATE_PATHS",
                        _mk_provider(tmp_path / "b", dates, build(3.0)))
    block, _, _ = R.part_returns(verbose=False)
    assert block["full"]["agree_rate"] == 1.0
    assert block["attribution"]["over"] == 0
    ls = block["level_scale"]
    assert ls["codes_constant_ratio"] == 1 and ls["codes_drifting_ratio"] == 0
    assert block["price_level"]["agree_rate"] == 0.0, (
        "价位级应当一格都不一致 —— 正因如此它不能当判据")


@pytest.fixture
def two_golds(tmp_path, monkeypatch):
    """两条通道各一份 gold（一个宇宙、一个因子、2 票 × 2 天），四格分别是：

    ===========  ======================================================
    格           设计
    ===========  ======================================================
    (A, d1)      逐位相同
    (A, d2)      差 5e-6 —— 在地板之上、超阈之下：算「逐位不同」不算超阈
    (B, d1)      差 1e-2 —— 超阈，且**当天有源差** → same_day_source_diff
    (B, d2)      差 1e-2 —— 超阈，**回看窗内也没有源差** → unattributed
    ===========  ======================================================
    """
    import duckdb
    dates = ["2026-01-05", "2026-01-06"]
    cal = tmp_path / "prov"
    (cal / "calendars").mkdir(parents=True)
    (cal / "calendars" / "day.txt").write_text("\n".join(dates) + "\n", encoding="utf-8")
    monkeypatch.setattr(qp, "PUBLIC_PATHS",
                        qp.ProviderPaths(channel="fixture", provider_dir=cal,
                                         tables_dir=cal, universe_pit=cal / "u",
                                         data_card=cal / "c"))
    pub = tmp_path / "pub" / "gold_factors" / "csi300"
    priv = tmp_path / "priv" / "gold_factors" / "csi300"
    pub.mkdir(parents=True)
    priv.mkdir(parents=True)
    rows_p = [("20260105", "SH600000", 1.0), ("20260106", "SH600000", 1.0 + 5e-6),
              ("20260105", "SH600001", 1.01), ("20260106", "SH600001", 1.01)]
    rows_v = [("20260105", "SH600000", 1.0), ("20260106", "SH600000", 1.0),
              ("20260105", "SH600001", 1.0), ("20260106", "SH600001", 1.0)]
    con = duckdb.connect(":memory:")
    for path, rows in ((pub / "f1.parquet", rows_p), (priv / "f1.parquet", rows_v)):
        con.execute("CREATE OR REPLACE TABLE t(date VARCHAR, code VARCHAR, value DOUBLE)")
        con.executemany("INSERT INTO t VALUES (?, ?, ?)", rows)
        con.execute("COPY t TO ? (FORMAT PARQUET)", [str(path)])
    con.close()
    monkeypatch.setattr(cfg, "SNAPSHOTS_PUBLIC", tmp_path / "pub")
    monkeypatch.setattr(cfg, "SNAPSHOTS_V1", tmp_path / "priv")
    monkeypatch.setattr(cfg, "UNIVERSES", ("csi300",))
    monkeypatch.setattr(R, "GOLD_WINDOW", ("20260101", "20260131"))
    monkeypatch.setattr(R, "GOLD_FACTORS_PER_UNIVERSE", 5)
    monkeypatch.setattr(R, "GOLD_LOOKBACK_DAYS", 250)
    # 源差位图：只有 SH600001 的第 1 天（下标 0）有源差
    return {"SH600000": np.array([False, False]),
            "SH600001": np.array([True, False])}


def test_gold_two_thresholds_and_attribution(two_golds):
    out = R.part_gold(two_golds, verbose=False)
    b = out["by_universe"]["csi300"]
    assert b["cells_both"] == 4
    assert b["cells_exact_equal"] == 1, "只有 (A, d1) 那一格逐位相同"
    assert b["cells_differ_at_floor"] == 3, "5e-6 那格也算「不是逐位相同」"
    assert b["cells_over_threshold"] == 2, "只有 1e-2 那两格算超阈"
    at = b["attribution"]
    assert at["same_day_source_diff"] == 1
    assert at["source_diff_within_lookback"] == 1, (
        "第 2 天没有当天源差，但回看窗里有 —— 该归到「传下来的」")
    assert at["cross_sectional_same_day"] == 0, "本票自己就能解释，不该落到弱归因那一类"
    assert at["unattributed"] == 0
    per = {f["factor"]: f for f in b["per_factor"]}
    assert per["f1"]["attribution"]["same_day_source_diff"] == 1


def test_gold_attribution_needs_the_compact_date_key(two_golds, monkeypatch):
    """**这条是本文件里最要紧的一条。**

    provider 的 `calendars/day.txt` 是 ISO（`2026-01-05`），gold 的 `date` 列是紧凑串
    （`20260105`）。用 ISO 当键，每一格都查不到 —— 而表现**不是报错**，是
    「归不掉 100%」，报告照样渲染得出来。真跑第一版就是这样过去的，
    所以这里用变异检验钉死：把那一折去掉，归因必须整个塌成 unattributed。
    """
    good = R.part_gold(two_golds, verbose=False)["by_universe"]["csi300"]["attribution"]
    assert good["unattributed"] == 0 and good["same_day_source_diff"] == 1

    def iso_keyed(path):                                   # 变异：忘了去掉横杠
        cal = [l.strip() for l in path.read_text().split("\n") if l.strip()]
        return {d: i for i, d in enumerate(cal)}

    monkeypatch.setattr(R, "_calendar_index", iso_keyed)
    bad = R.part_gold(two_golds, verbose=False)["by_universe"]["csi300"]["attribution"]
    assert bad["unattributed"] == 2 and bad["same_day_source_diff"] == 0, (
        "变异没被打红 —— 说明这条测试并没有在验日期键的形态")


def test_part_calibration_reports_the_delta_not_just_the_two_numbers(tmp_path, monkeypatch):
    def cal(tau, calibrated, usable):
        return {"built_at": "2026-01-01T00:00:00+00:00",
                "tau": {"value": tau, "universe": "csi300", "start": "a", "end": "b",
                        "comparable_factors": 2, "factors_used": 2, "cells_used": 10,
                        "excluded_operator_conflict": ["x"],
                        "degenerate_rule": {"cells_removed": 1}},
                "epsilon": {"by_frequency": {"daily": {
                    "by_metric": {m: {"epsilon": 0.1, "tolerance_kind": "relative",
                                      "status": "calibrated"} for m in calibrated},
                    "calibrated": calibrated, "implausible": [], "no_freedom": [],
                    "usable": usable}},
                    "ic_family": {"usable": False, "usable_metrics": ["mean"],
                                  "calibrated": ["mean"], "implausible": [],
                                  "no_freedom": [], "no_pair": [],
                                  "by_holding_period": {"1": {"by_metric": {
                                      "mean": {"epsilon": 0.02, "status": "calibrated",
                                               "tolerance_kind": "absolute"}}}}}},
                "ready_for_scoring": False}

    (tmp_path / "pub").mkdir()
    (tmp_path / "priv").mkdir()
    (tmp_path / "pub" / "calibration.json").write_text(
        json.dumps(cal(0.98, ["a", "b"], True)), encoding="utf-8")
    (tmp_path / "priv" / "calibration.json").write_text(
        json.dumps(cal(0.99, ["a"], True)), encoding="utf-8")
    monkeypatch.setattr(cfg, "SNAPSHOTS_PUBLIC", tmp_path / "pub")
    monkeypatch.setattr(cfg, "SNAPSHOTS_V1", tmp_path / "priv")
    out = R.part_calibration()
    assert out["tau"]["delta_abs"] == pytest.approx(0.01)
    assert out["tau"]["same_operator_conflicts"] is True
    assert out["epsilon_by_frequency"]["daily"]["calibrated_only_public"] == ["b"]
    assert out["epsilon_by_frequency"]["daily"]["calibrated_only_private"] == []
    assert out["ic_family"]["same_usable_metrics"] is True


def test_part_frozen_tells_the_truth_about_missing_artifacts():
    out = R.part_frozen()
    on_disk = [a for a in PM.PUBLIC_FROZEN_ARTIFACTS if not (_REPO / a).is_file()]
    assert out["missing"] == on_disk
    assert out["blocks_release"] is bool(on_disk)
    for a, info in out["present"].items():
        assert len(info["sha256"]) == 64


def test_render_does_not_crash_on_a_partial_report():
    """只跑了一节的产物也要渲染得出来 —— `--part` 是常用路径。"""
    md = R.render({"run": {"built_at": "x", "code_head": "0" * 40, "seconds": 1.0,
                           "public_root": "p", "private_root": "q"},
                   "frozen": R.part_frozen()})
    assert "## 7. 冻结件" in md and "## 1. 收益率级一致率" not in md


def test_main_writes_products_with_go_rwx(tmp_path):
    """红线 5：脚本自己落的文件必须 0600。"""
    out = tmp_path / "r.json"
    md = tmp_path / "r.md"
    assert R.main(["--part", "frozen", "--out", str(out), "--report", str(md),
                   "--quiet"]) == 0
    assert out.stat().st_mode & 0o077 == 0
    assert md.stat().st_mode & 0o077 == 0
    assert json.loads(out.read_text(encoding="utf-8"))["run"]["parts_run"] == ["frozen"]


# =================================================================== 产物本身

@pytest.mark.skipif(not REPORT_JSON.is_file(), reason="还没跑过 ops/recon_public_vs_private.py")
def test_the_shipped_report_is_a_full_run_not_a_smoke_run():
    d = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert d["run"].get("partial") is not True, (
        "仓库里这份对账是 --limit-codes 跑出来的冒烟结果，不能当发布件")
    assert set(d["run"]["parts_run"]) == set(R.PARTS)
    assert d["returns"]["coverage"]["codes_common"] == d["returns"]["coverage"]["codes_public"]


@pytest.mark.skipif(not REPORT_MD.is_file(), reason="还没跑过 ops/recon_public_vs_private.py")
def test_the_report_is_rendered_from_the_product_not_hand_written():
    t = REPORT_MD.read_text(encoding="utf-8")
    assert "由 `ops/recon_public_vs_private.py` 渲染" in t
    d = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    assert f"{d['returns']['full']['return_pairs']:,}" in t
