# -*- coding: utf-8 -*-
"""pin.json 的 runnable_check：这个镜像里到底装没装上。

**先 chdir**：上游 `log/custom_logger.py` 在 import 期就开一个相对 CWD 的
`FileHandler('log/test.txt')`，而基座的 WORKDIR 是 `/task` —— 不 chdir 的版本
在构建期实测报 `FileNotFoundError: [Errno 2] ... '/task/log/test.txt'`（build2.log）。
"""
import os, sys

os.makedirs("/tmp/rc/log", exist_ok=True)
os.chdir("/tmp/rc")
sys.path.insert(0, "/opt/stockagent/upstream")
import util, stock, secretary, procoder                      # noqa: E402
import genebench_client as gb                                # noqa: E402
from genebench_client import emit                            # noqa: E402

print("runnable_check", "stocks=%d" % len(util.STOCK_NAMES),
      "get_price=%s" % hasattr(stock.Stock, "get_price"),
      "secretary=%s" % hasattr(secretary, "run_api"),
      "procoder=%s" % procoder.__version__,
      "emit_s5=%s" % hasattr(emit, "emit_s5"))
