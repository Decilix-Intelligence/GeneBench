# -*- coding: utf-8 -*-
"""卡 2.5 §3 的验收：私有 `stk_limit` 当 oracle，**逐行**核涨跌停推导。

「我们有一份权威答案，就必须拿它逐行核推导，而不是『规则写对了应该就对』。」

输出卡要求的三样：**一致率 / 分歧清单 / 逐条归因**。
窗口用环境变量 `B3_START` / `B3_END` 给（默认 2026-07），落点用 `B3_OUT`。

**2026-01-01..07-31 全量实测：763,301 行，一致率 1.000000，0 行分歧。**
这个数是**改了四处规则之后**才拿到的 —— 四处全部是 oracle 逼出来的，
对着文档一处都查不出来：

1. 北交所取整是「不超过幅度」的**截断**，不是四舍五入（用四舍五入核，北交所只有 **52.4%**）；
2. ST 的 5% 带在 **2026-07-06 起取消**，而卡 §3 的规则表**没有生效日**；
3. 新股无限制窗口**沪深 5 天、北交所 1 天**，不是一个全局常数；
4. **退市整理期首日**无限制，且沪深命名规则相反（沪是前缀「退市」，深北是后缀「退」）——
   按名字判会**整个漏掉沪市**，表现是 8 行分歧散落在半年里、像随机噪声。
"""
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import pandas as pd
from snapshots import lake
from snapshots.public.limits import ORACLE_NO_LIMIT_SENTINEL, derive

START = os.environ.get("B3_START", "20260701")
END = os.environ.get("B3_END", "20260731")
OUT = pathlib.Path(os.environ.get("B3_OUT", "/data/shared/genebench/scratch"))

# **走 `snapshots/lake.py`，不自己 `duckdb.connect`**：
# 它统一了只读模式、重试与 `raise_open_file_limit`（这张表按 ts_code 分区，
# 直连时逐票查会撞 "Too many open files"），而且 `test_lake_baseline` 有一条门盯着
# 「谁绕过它直连了湖」—— 第一版就是被那条门当场抓住的。
with lake.catalog(threads=4) as con:
    # 交易日序号：先给日历编号，再用「当日序号 - 上市日序号 + 1」求上市以来的交易日数。
    con.execute("""CREATE TEMP TABLE calidx AS
        SELECT cal_date, row_number() OVER (ORDER BY cal_date) AS i
        FROM trade_cal WHERE exchange='SSE' AND is_open=1""")
    df = con.execute(f"""
    WITH lst AS (SELECT ts_code, min(list_date) AS list_date FROM stock_basic GROUP BY 1)
    SELECT s.trade_date, s.ts_code, s.up_limit, s.down_limit, d.pre_close AS pre,
       l.list_date, ct.i - cl.i + 1 AS days_listed,
       -- 退市整理期首日。判据取 `change_reason`，**不取名字** ——
       -- 命名规则**两个交易所不一样**：深/北是后缀「退」（国华退、云创退），
       -- 沪是前缀「退市」（退市华嵘、退市观典）。按后缀判会漏掉整个沪市，
       -- 而漏掉的表现是 8 行分歧散落在半年里，看起来像随机噪声。
       EXISTS (SELECT 1 FROM namechange n WHERE n.ts_code = s.ts_code
               AND n.change_reason = '退市整理期' AND n.start_date = s.trade_date) AS delist_d1,
       coalesce((SELECT n.name FROM namechange n
                 WHERE n.ts_code = s.ts_code AND n.start_date <= s.trade_date
                 ORDER BY n.start_date DESC LIMIT 1), '') AS name_on_day
    FROM stk_limit s
    LEFT JOIN daily d ON d.trade_date=s.trade_date AND d.ts_code=s.ts_code
    LEFT JOIN lst l ON l.ts_code = s.ts_code
    LEFT JOIN calidx ct ON ct.cal_date = s.trade_date
    LEFT JOIN calidx cl ON cl.cal_date = l.list_date
    WHERE s.trade_date BETWEEN '{START}' AND '{END}'
    """).df()
# ST 的判据是**当日名字以 ST / *ST 开头**（交易所的实际写法），不是「名字里含 ST」。
_nm = df.name_on_day.fillna("").str.replace(" ", "").str.upper()
# ST：去掉前导 `*` 之后以 ST 开头。S 股：以 S 开头但不是 ST（`S佳通`）。
df["is_st"] = _nm.str.lstrip("*").str.startswith("ST")
df["is_s"] = _nm.str.startswith("S") & ~_nm.str.startswith("ST")
print("oracle 行数：", len(df), "| 无前收：", int(df.pre.isna().sum()),
      "| 无上市日：", int(df.list_date.isna().sum()),
      "| 当日名判定为 ST：", int(df.is_st.sum()), "| S 股：", int(df.is_s.sum()), flush=True)

d = df.dropna(subset=["pre"]).copy()
out = []
for t in d.itertuples(index=False):
    dl = int(t.days_listed) if pd.notna(t.days_listed) else None
    L = derive(t.ts_code, t.trade_date, float(t.pre), is_st=bool(t.is_st),
               days_listed=dl, is_s_share=bool(t.is_s),
               delisting_first_day=bool(t.delist_d1))
    out.append((L.up, L.down, L.pct, L.reason))
d[["my_up", "my_down", "my_pct", "reason"]] = pd.DataFrame(out, index=d.index)

def matches(r):
    # `pd.DataFrame` 会把 None 变成 NaN —— 写 `is None` 的话新股那一支永远不匹配，
    # 而它表现成「推导错了 15 行」而不是「比较写错了」。
    if pd.isna(r.my_up):
        ex = ORACLE_NO_LIMIT_SENTINEL.get(r.ts_code[-2:])
        return bool(ex) and abs(r.up_limit - ex[0]) < 1e-6 and abs(r.down_limit - ex[1]) < 1e-6
    return abs(r.my_up - r.up_limit) < 1e-9 and abs(r.my_down - r.down_limit) < 1e-9
d["ok"] = [matches(r) for r in d.itertuples(index=False)]
d["branch"] = d.reason.str.split("；").str[0]

print(f"\n=== 一致率：{d.ok.mean():.6f}（{int(d.ok.sum())}/{len(d)}）===")
print("\n按规则分支：")
print(d.groupby("branch").ok.agg(["mean", "sum", "count"]).sort_values("count", ascending=False).to_string())

bad = d[~d.ok].copy()
print(f"\n=== 分歧 {len(bad)} 行 ===")
if len(bad):
    bad["implied_up"] = (bad.up_limit / bad.pre - 1).round(4)
    print("按 (规则分支, oracle 隐含涨幅) 归因（前 12）：")
    print(bad.groupby(["branch", "implied_up"]).size().sort_values(ascending=False).head(12).to_string())
    print("\n分歧清单样例：")
    print(bad[["trade_date","ts_code","pre","up_limit","my_up","down_limit","my_down",
               "implied_up","branch"]].head(15).to_string(index=False))
    bad.to_parquet(str(OUT / "b3_mismatch_") + START + "_" + END + ".parquet", index=False)
d.to_parquet(str(OUT / "b3_full_") + START + "_" + END + ".parquet", index=False)
print("\n落盘 scratch/b3_full_" + START + "_" + END + ".parquet")
