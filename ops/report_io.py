"""报告落盘的唯一出口：**写完就收紧到 0600 / 0700**（红线 5）。

为什么值一个模块：网关的 `ExecStartPre=ops/guard_modes.py` 在**服务启动时**扫敏感根，
任何 0664 的文件都会让它拒绝起服务。2026-09-05 实测过一次完整的因果链 ——
网关被 OOM 杀掉 → systemd 自动重启 → 守门发现我新写的报告文件是 0664（umask 002）→
**连续 20 次拒绝启动** → 一次瞬时崩溃变成 10 分钟的数据面停摆，
把 9 道 oracle 与两个 S7 的 M6 run 一起打坏。

所以：**报告也是答案面的东西**，写它的每一处都必须走这里，不许再 `write_text` 裸写。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import genebench_config as cfg                      # noqa: E402

DIR_MODE = cfg.REQUIRED_DIR_MODE                    # 0700，与红线 5 同源（不再自己写一个字面量）
FILE_MODE = 0o600


def secure_dir(path) -> Path:
    """建目录一律走 `cfg.create_dir` —— 裸 `mkdir` 的中间层只受 umask 管（本机 002 → 0775）。
    `ops/test_env.py::test_no_bare_mkdir_in_answer_plane_modules` 会把裸的那种当场判红。"""
    return cfg.create_dir(path)


def write_text(path, text: str) -> Path:
    p = Path(path)
    secure_dir(p.parent)
    p.write_text(text, encoding="utf-8")
    p.chmod(FILE_MODE)
    return p


def write_json(path, obj, *, indent: int = 1) -> Path:
    return write_text(path, json.dumps(obj, ensure_ascii=False, indent=indent) + "\n")


#: 组 + 其它的全部位（镜像 `ops/guard_modes._GO_BITS`）。
_GO_BITS = 0o077


def secure_tree(root) -> int:
    """把一棵已经写出来的树收紧：**只剥组/其它位**，属主位原样留着。返回改了几个。

    2026-09-05 踩过：早先这里拍平成 0600，把 `ops/push_bundle_to_f02.sh` 与 `.git/hooks/post-commit`
    的**执行位**一起抹了 —— 推送入口当场 `Permission denied`。红线 5 管的是「别人能不能看」，
    不是「属主能不能执行」；`guard_modes.harden()` 从一开始就是 `mode & ~_GO_BITS`，这里跟它同语义。
    符号链接跳过（chmod 跟着目标走，且答案面根下本来就不许有 —— 那是 `check()` 的事）。
    """
    n = 0
    root = Path(root)
    for p in [root, *root.rglob("*")]:
        if p.is_symlink():
            continue
        try:
            mode = p.stat().st_mode & 0o777
            if mode & _GO_BITS:
                p.chmod(mode & ~_GO_BITS)
                n += 1
        except OSError:
            continue
    return n
