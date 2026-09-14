# -*- coding: utf-8 -*-
"""镜像内自检（无模型调用）。真跑之前先答四个问题：

1. 上游装进去了吗（`pin.json::runnable_check`）？
2. `compat.install()` 之后 `import finrobot.agents.workflow` 走得通吗
   （那条路上有 `functional/quantitative.py` 的模块层 `import yfinance`）？
3. 接线装得上吗、`assert_no_native_datasource()` 会不会漏网？
4. 换上去的取数真的经网关吗（打一次 `/universe` + 一次 `/bars`，看 ledger）？

**跑法**（在 f02）：
    docker run --rm -e GENEBENCH_GATEWAY=http://192.168.1.48:18080 \
      -e GENEBENCH_TASK_ID=smoke -e GENEBENCH_CONFIG_ID=cfg-finrobot-deepseek \
      -e GENEBENCH_ARM=smoke -e GENEBENCH_RUN_ID=smoke-finrobot \
      -v /data/genebench_runner/build/finrobot/finrobot/smoke_in_container.py:/tmp/smoke.py:ro \
      gb-finrobot-u:r1 python3 /tmp/smoke.py
"""
from __future__ import annotations

import json
import os
import sys

AS_OF = os.environ.get("SMOKE_AS_OF", "2026-07-31")
START, END = os.environ.get("SMOKE_START", "2026-07-01"), os.environ.get("SMOKE_END", "2026-07-04")

ok = True


def check(name: str, fn):
    global ok
    try:
        out = fn()
    except Exception as exc:                                        # noqa: BLE001
        ok = False
        import traceback
        print(f"[FAIL] {name}: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return None
    print(f"[ok]   {name}: {out}")
    return out


import genebench_client as gb                                       # noqa: E402
from genebench_client import compat                                 # noqa: E402

compat.install()
gb.set_as_of(AS_OF)

check("upstream import", lambda: __import__("finrobot").__name__)
check("data_source", lambda: __import__("finrobot.data_source", fromlist=["x"]).__all__)
check("workflow", lambda: __import__("finrobot.agents.workflow", fromlist=["SingleAssistant"]).SingleAssistant.__name__)

sys.path.insert(0, "/opt")
from finrobot_glue import gateway_sources as GS                     # noqa: E402

check("install()", lambda: len(GS.install()))
check("assert_no_native_datasource", lambda: GS.assert_no_native_datasource() or "clean")
check("assert_market_data_seam_closed", lambda: GS.assert_market_data_seam_closed() or "closed")


def _leak_is_caught():
    """定向破坏：给 YFinanceUtils 加一个没记号的方法，那道门必须红。"""
    from finrobot import data_source as DS
    DS.YFinanceUtils.get_something_new = lambda *a, **k: "native!"
    try:
        GS.assert_no_native_datasource()
    except RuntimeError as exc:
        del DS.YFinanceUtils.get_something_new
        return f"caught: {str(exc)[:60]}"
    del DS.YFinanceUtils.get_something_new
    raise AssertionError("加了一个原生方法，守门却没红 —— 这道门是恒绿的")


check("守门会红（定向破坏）", _leak_is_caught)

# 库里那张 toolkit 表拿到的必须是换过的函数（agent_library 在模块层抓函数对象）。
def _library_is_patched():
    from finrobot.agents.agent_library import library
    # 这一趟里 `workflow` 是在 install() **之前** import 的（故意的：真跑时任何
    # 一条早 import 都会让 library 抓到原生实现）。patch_library 就是那道补救。
    GS.patch_library(library)
    names = []
    for fn in library["Market_Analyst"]["toolkits"]:
        if not getattr(fn, GS.MARK, False):
            raise AssertionError(f"library 里的 {getattr(fn, '__name__', fn)} 还是上游原件")
        names.append(fn.__name__)
    return names


check("agent_library 的工具表已换", _library_is_patched)


def _agent_builds():
    """把工具真注册一遍（autogen 从签名生成 JSON schema）—— 不打模型。"""
    from finrobot.agents.agent_library import library
    from finrobot.agents.workflow import SingleAssistant
    library["Market_Analyst"]["toolkits"] = (
        list(library["Market_Analyst"]["toolkits"]) + list(GS.ADDED_TOOLS))
    a = SingleAssistant("Market_Analyst", {
        "config_list": [{"model": "deepseek-chat", "base_url": "http://sidecar.invalid/v1",
                         "api_key": "PLACEHOLDER"}],
        "timeout": 5, "temperature": 0, "cache_seed": None},
        max_consecutive_auto_reply=2,
        code_execution_config={"work_dir": "/tmp/fr/coding", "use_docker": False})
    tools = [t["function"]["name"] for t in a.assistant.llm_config["tools"]]
    if "get_index_constituents" not in tools:
        raise AssertionError(f"新增工具没注册上：{tools}")
    return tools


check("SingleAssistant 组得起来、工具注册得上", _agent_builds)

# 真打一次网关（轻量：一次 /universe + 一次 /bars）
def _gateway_roundtrip():
    txt = GS.get_index_constituents("csi300", END)
    n = int(txt.split(":")[1].split()[0])
    head = GS.get_stock_data("csi300", START, END, "close,volume")
    return f"universe={n} bars_head={head.splitlines()[1]}"


check("经网关取数", _gateway_roundtrip)


def _nodata_traced():
    from finrobot import data_source as DS
    msg = DS.FinnHubUtils.get_company_news("600000.SH", START, END)
    if not msg.startswith("NO_DATA:"):
        raise AssertionError(f"新闻不该有：{msg[:80]}")
    paths = [e["path"] for e in gb.client().ledger]
    if not any(p.startswith("/nodata") for p in paths):
        raise AssertionError(f"NO_DATA 没在数据面留痕：{paths}")
    return msg[:60]


check("NoData 留痕", _nodata_traced)

led = gb.client().ledger
print("[ledger]")
for e in led:
    print("   ", json.dumps({k: e[k] for k in ("path", "status", "rows", "ts")}, ensure_ascii=False))
print("[fields_obtained]", GS.fields_obtained())
print("RESULT", "SMOKE-OK" if ok else "SMOKE-FAILED")
sys.exit(0 if ok else 1)
