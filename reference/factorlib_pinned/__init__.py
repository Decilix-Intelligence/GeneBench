"""平台 factorlib 的**钉版本**副本（仅取卡 2.1b 需要的三个模块）。

来源与逐文件 sha256 见 ``PROVENANCE.json``；由 ``ops/vendor_factorlib.py`` 生成。

* ``ops/test_factor_exec.py::test_vendored_factorlib_matches_its_own_pin``
  核对它没被就地改过；
* ``::test_vendored_factorlib_still_matches_upstream`` 在上游漂移时**红给你看** ——
  红了不是让你去改代码，是让你**有意识地**重新钉版本，并且知道
  重新钉意味着 gold 因子值可能变、τ 要重标。

**不要 import 平台的活代码**：那会让 gold 随平台一起变。
"""
