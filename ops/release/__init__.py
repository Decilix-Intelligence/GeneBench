# -*- coding: utf-8 -*-
"""发布形态（卡 1.4）。

两条形态，**都要走通并计时**（`DATA_LICENSE` §3 / 卡 2.5 §9）：

* **形态 A** —— 冻结 provider 打包下载：`pack_public_provider.py`；
* **形态 B** —— 用户自建 + 校验和比对：`build_public_provider.sh`
  （`fetch_public_quotes.py` / `universe_from_instruments.py` / `rebuild_public_provider.py`）。

两条的判据是**同一个** `SHA256SUMS`：形态 B 在用户机器上重建出来的 provider
必须与形态 A 包里的**逐文件字节相同**。相同才说明「不下载我们的包也能独立验证」。
"""
