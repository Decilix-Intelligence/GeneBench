# -*- coding: utf-8 -*-
"""重新钉版本：把平台 factorlib 的三个模块拷进 ``reference/factorlib_pinned/``。

    cd $REPO && $GENEBENCH_ROOT/env/bin/python ops/vendor_factorlib.py

**这不是日常脚本。** 跑它意味着**换掉参考实现**，而 gold 因子值与 τ 都建立在它上面 ——
跑完必须重算 gold、重标 τ、重新签字。N-21 的 B 方案会用到它。

**为什么不 import 平台的活代码**：平台是既有服务且会变；gold 是 τ 的输入、τ 要签字。
provider 已经冻了，参考实现不冻等于只冻了一半。

**为什么不自己重写**：那 66 条方言公式的语义与 `alpha001 -0.5` 都是**因子库自己的口径**，
重写等于凭空造出第二套语义，而 τ 恰恰标定在"两个实现有多一致"上。

**踩过的坑**：``shutil.copy2`` 会把上游文件的 **POSIX ACL 一起带过来**。
平台那个目录在带 ACL 的文件系统上，拷过来的文件 ``ls`` 显示 ``-rw-------+`` ——
基础模式看着是 600，但 ACL 让 `ops/test_env.py` 的答案面审计闸门变红。
所以这里用 ``copyfile``（只拷内容）+ 显式 ``chmod``，并在最后剥一次 ACL。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg  # noqa: E402

SRC = Path("/home/ljn/projects/quant/platform/src/quant_platform/factorlib")
DST = cfg.REPO / "reference" / "factorlib_pinned"
FILES: tuple[str, ...] = ("formula.py", "qlib_loader.py", "qlib_ops.py")

DOC = '''"""平台 factorlib 的**钉版本**副本（仅取卡 2.1b 需要的三个模块）。

来源与逐文件 sha256 见 ``PROVENANCE.json``；由 ``ops/vendor_factorlib.py`` 生成。

* ``ops/test_factor_exec.py::test_vendored_factorlib_matches_its_own_pin``
  核对它没被就地改过；
* ``::test_vendored_factorlib_still_matches_upstream`` 在上游漂移时**红给你看** ——
  红了不是让你去改代码，是让你**有意识地**重新钉版本，并且知道
  重新钉意味着 gold 因子值可能变、τ 要重标。

**不要 import 平台的活代码**：那会让 gold 随平台一起变。
"""
'''


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(SRC.parents[2]), *args],
                          capture_output=True, text=True).stdout.strip()


def main() -> int:
    cfg.harden_umask()
    if not SRC.is_dir():
        raise SystemExit(f"上游不可读：{SRC}")
    cfg.create_dir(DST)
    prov: dict = {
        "vendored_at": __import__("datetime").date.today().isoformat(),
        "source_dir": str(SRC),
        "platform_git_rev": _git("rev-parse", "HEAD") or None,
        "platform_worktree_dirty": bool(_git("status", "--porcelain")),
        "why": ("平台是既有服务且会变；gold 因子值是 τ 的输入、τ 要签字。"
                "provider 已经冻了，参考实现不冻等于只冻了一半。"),
        "rerun_consequence": "重新钉版本 = 必须重算 gold、重标 τ、重新签字。",
        "files": {},
    }
    for name in FILES:
        s, d = SRC / name, DST / name
        shutil.copyfile(s, d)          # 只拷内容：copy2 会把 ACL 一起带过来
        d.chmod(0o600)
        prov["files"][name] = {"sha256": _sha256(s), "bytes": s.stat().st_size}
        print(f"  {name:<16} {prov['files'][name]['sha256'][:16]}…  {s.stat().st_size} B")

    (DST / "__init__.py").write_text(DOC, encoding="utf-8")
    (DST / "__init__.py").chmod(0o600)
    (DST / "PROVENANCE.json").write_text(
        json.dumps(prov, ensure_ascii=False, indent=2), encoding="utf-8")
    (DST / "PROVENANCE.json").chmod(0o600)
    DST.chmod(0o700)
    if shutil.which("setfacl"):
        subprocess.run(["setfacl", "-b", str(DST), *[str(DST / n) for n in FILES]],
                       capture_output=True)
    print(f"platform git rev = {prov['platform_git_rev']} dirty={prov['platform_worktree_dirty']}")
    print(f"→ {DST}")
    print("⚠ 重新钉版本后必须：重算 gold（reference.factor_exec）、"
          "重跑互检（reference.factor_crosscheck）、重标 τ、重新签字。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
