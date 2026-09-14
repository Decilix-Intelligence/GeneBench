# -*- coding: utf-8 -*-
"""**§12 状态锁**：把卡 4.3 §12 五条签字裁定的**当前状态**钉住（线 A / A3）。

裁定签完之后会发生两件事，两件都没有信号：

1. **实现漂开裁定**。TK-1 把 L-5 收紧成「挂载源与 run dir 精确相等」，
   但卡 4.1 的规则表里那一行写的还是旧措辞。**两条互斥规则同时挂在墙上**
   正是 TK-1 要消灭的东西 —— 裁完还留着就等于没裁。
2. **「挂起 / 待办 / 未启用」悄悄变成了「做了」**。TK-2（主机防火墙）、
   TK-4（容器内同路径 provider）、TK-5（清单签名）三条的当前状态都是「没做」，
   而「没做」这件事**只在有人去查的时候才可观测**。哪天有人顺手加了一条 ufw 规则、
   或者把 provider 挂到 `/data/genebench/provider`，没有任何测试会红。

所以这里把状态写成**表**，每条配一个**现实判据**（不是读这张表自己的字段 —— 那是 F7）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CARD_43 = REPO / "ops" / "specs" / "card_4.3_two_arm_injector.md"
CARD_41 = REPO / "ops" / "specs" / "card_4.1_container_isolation.md"

#: TK-1 收紧后的 L-5 判据措辞。**两张卡必须都出现它** —— 这是「两处措辞一致」的可测形式。
L5_TIGHTENED_PHRASE = "挂载源与 run dir 精确相等"

#: TK-4 的备用路径。**当前未启用** —— 它出现在实现代码里就说明启用了。
TK4_CONTAINER_PATH = "/data/genebench/provider"


@dataclass(frozen=True)
class Ruling:
    """一条签字裁定的**当前状态**。`reality` 说清「怎么验这条状态还是真的」。"""

    tk: str
    decision: str
    state: str            # 已实现 / 挂起 / 待办 / 未启用 / 归 v2
    reality: str          # 判据一句话（对应 test_status_lock.py 里的一条）


RULINGS: tuple[Ruling, ...] = (
    Ruling("TK-1", "保留唯一 bind-mount 例外，L-5 收紧为「挂载源与 run dir 精确相等」",
           "已实现",
           "lint_compose 对同一 runs 根下的**别的** run dir 必须报红；"
           "且卡 4.1 与卡 4.3 两处措辞一致"),
    Ruling("TK-2", "主机防火墙规则缓办，登记保留",
           "挂起",
           "仓库里没有任何**执行** ufw/iptables 的调用（出现在散文里不算做了）"),
    Ruling("TK-3", "先实测 provider 落地体积再定配额",
           "实测已有·配额待定",
           "f02 侧单份 provider 体积已实测并记进卡；配额数字仍不许硬编码"),
    Ruling("TK-4", "容器内同路径落盘 /data/genebench/provider —— 条件式批准，T12 过则不许启用",
           "未启用",
           "实现代码里不出现该容器内路径；卡 4.1 的 FS-A「ls /data 必须失败」仍是活断言"),
    Ruling("TK-5", "清单签名归 v2，v1 不做",
           "归 v2",
           "通行证里没有签名字段，check_manifest 也不验签；边界写在已知边界里"),
)


def ruling(tk: str) -> Ruling:
    for r in RULINGS:
        if r.tk == tk:
            return r
    raise KeyError(f"没有 {tk} 这条裁定")


#: TK-3 的 f02 实测（2026-09-05 现跑，与 f01 逐项相同）。
#: **记数不是为了好看**：46,544 个小文件让落盘占用比表观字节大 28%，
#: 按表观定阈值会系统性少算，少算的后果是 F10（复制截断，静默错数）。
TK3_F02_MEASUREMENT = {
    "path": "/data/genebench_runner/provider/qlib_provider_54fdda39",
    "apparent_bytes": 494008883,      # 472 MiB
    "on_disk_human": "602M",
    "files": 46544,
    "data_free_human": "2.6T",
    "note": "第 2 步（完整 run dir 占用）待一次真跑 —— 被 N-62 阻塞。"
            "可给的界：每个 run dir ≥ 一份 provider 副本 ≈ 602M，"
            "40 题 × 2 臂 = 80 个 run dir ⇒ 一轮 ≈ 48 GB。",
}
