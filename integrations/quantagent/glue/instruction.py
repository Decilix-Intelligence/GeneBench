"""题面解析 —— 两臂的写法都要认。

`integrations/README.md` §1④「题面有两种写法，你的解析器必须两种都认」列了
三处「会把值偷走、而且产物上完全看不出来」的地方，这份解析器逐条防住：

1. `可用端点：… /universe /tradability` —— 任何「找 universe 后面那个词」的正则
   都会取到 `tradability`。**防法**：锚点前排除 `/` 与 `_`，锚点后必须有真正的赋值记号。
2. 口径行里的 `universe_ref=csi300@2026-07-31` 带一个恰好等于 as_of 的日期。
   **防法**：以 `- ` 开头的口径行不参与 as_of / window / universe 的取值。
3. open 臂的口径行里散文与接口值并存。**防法**：口径行只取「接口值」后面那一段。
"""
import re

#: 口径行（`- ` 开头）不参与三个固定槽的取值 —— 见模块 docstring 第 2 条。
_SLOT_LINE_SKIP = re.compile(r"^\s*[-*]\s")

#: 锚点：前面不能是 `/` 或 `_`（防 `/universe`、`universe_ref`），
#: 后面允许至多十来个非目标字符，再接一个真正的赋值记号。
_ANCHOR = r"(?<![/_\w]){k}(?![_\w])[^\n=:：]{{0,14}}?[=:：是]\s*"


def _candidate_lines(text):
    for line in text.splitlines():
        if _SLOT_LINE_SKIP.match(line):
            continue
        yield line


def slot(text, key, pattern=r"[^\s，。,;)）]+"):
    """从固定槽取值。取不到就抛 —— **不猜默认值**。

    猜一个 as_of 出来会把越界变成合法请求，而产物上完全看不出来。
    """
    rx = re.compile(_ANCHOR.format(k=re.escape(key)) + f"(?P<v>{pattern})")
    for line in _candidate_lines(text):
        m = rx.search(line)
        if m:
            return m.group("v").strip("`\"'")
    raise SystemExit(
        f"题面里没有取到槽位 {key!r}。**不猜默认值** —— 请按题面的两种写法改 slot()。")


def window(text):
    """窗口两端。strict 是 `window=A 到 B`，open 是「计算窗口（window）是 A 到 B」。"""
    rx = re.compile(_ANCHOR.format(k="window") + r"(?P<a>\d{4}-\d{2}-\d{2})\s*[到至~\-]+\s*(?P<b>\d{4}-\d{2}-\d{2})")
    for line in _candidate_lines(text):
        m = rx.search(line)
        if m:
            return m.group("a"), m.group("b")
    raise SystemExit("题面里没有取到 window 的两端。**不猜默认值**。")


#: 口径行统一取「接口值」后面那一段 —— 两臂的这一段是逐字相同的。
_IFACE = re.compile(r"接口值\s*(?P<v>[^\s，。）)]+)")
#: 字段名的两种写法：`- X=` 与 `（字段 X，`
_FIELD = re.compile(r"^\s*[-*]\s*(?P<f>[a-zA-Z_][\w]*)\s*=|（字段\s*(?P<g>[a-zA-Z_][\w]*)\s*[，,]")


def declarations(text):
    """逐条口径 → {字段名: 接口值}。只读 `- ` 开头的口径行。"""
    out = {}
    for line in text.splitlines():
        if not _SLOT_LINE_SKIP.match(line):
            continue
        mf, mv = _FIELD.search(line), _IFACE.search(line)
        if not mf or not mv:
            continue
        out[(mf.group("f") or mf.group("g"))] = mv.group("v")
    return out
