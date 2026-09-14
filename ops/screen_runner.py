#!/usr/bin/env python3
"""B 侧三份独立实现是**脚本**不是库：复制到沙箱、打最小开关补丁、子进程跑、读它自己写的 JSON。

不修改 `/data/shared/genebench/snapshots` 下的任何文件；补丁只加**一个由环境变量驱动的开关**，
不动排序键、不动 n_drop 上限、不动可交易性过滤。默认值一律等于该实现打补丁前的原读法 ——
Gate 1 会逐字节验证这一点（不然测出来的分叉是补丁的，不是实现的）。

补丁不用 `patch -p0`：方案里的 diff 带「约 :202」这种近似锚点，模糊匹配会**悄悄打歪**。
这里全部走带断言的精确替换 —— 锚点必须唯一命中，否则立刻报错。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

PY = "/data/shared/genebench/env/bin/python"
SNAP = Path("/data/shared/genebench/snapshots/v1/epsilon")
PANEL = SNAP / "bt_input_csi300_v2.parquet"

SCRIPTS: dict[str, dict] = {
    "B1": {"src": SNAP / "impl_v2_b1.py", "argv": ["{freq}"], "out": "out_v2_b1_{freq}.json"},
    "B2": {"src": SNAP / "impl_v2_b2.py", "argv": ["{freq}"], "out": "out_v2_b2_{freq}.json"},
    "B3": {"src": SNAP / "impl_v2_b3.py", "argv": [],         "out": "out_v2_b3_{freq}.json"},
}
#: 不进比较：字符串与机械计数（n_days 另行对账）。
SKIP_METRICS = ("n_days", "rebalance_frequency", "total_cost_source", "freq")

_SW = ('\n# --- screen 开关（materiality 用；只加开关，不改算法）---------------------------\n'
       'import os as _os\n'
       '_GB_SELL_RULE = _os.environ.get("GB_SELL_RULE", "dropped_from_target")\n'
       '# ------------------------------------------------------------------------------\n')

#: 每个补丁 = [(锚点, 替换)]；锚点在目标文件里必须**恰好出现一次**。
SWITCH_EDITS: dict[str, dict[str, list[tuple[str, str]]]] = {
    "P-SELL": {
        "B1": [("INPUT = HERE / \"bt_input_csi300_v2.parquet\"",
                "INPUT = HERE / \"bt_input_csi300_v2.parquet\"" + _SW),
               ("            (hold > 0) & (~is_target[t]) & sellable[t] & (buy_day < t)",
                "            (hold > 0) & (np.ones_like(is_target[t]) if _GB_SELL_RULE == \"worst_n_drop\""
                " else (~is_target[t])) & sellable[t] & (buy_day < t)")],
        "B2": [("INPUT = os.path.join(BASE, \"bt_input_csi300_v2.parquet\")",
                "INPUT = os.path.join(BASE, \"bt_input_csi300_v2.parquet\")" + _SW),
               ("                cand = held[~np.isin(held, tgt)]",
                "                cand = held if _GB_SELL_RULE == \"worst_n_drop\" else held[~np.isin(held, tgt)]")],
        "B3": [("INPUT = os.path.join(HERE, \"bt_input_csi300_v2.parquet\")",
                "INPUT = os.path.join(HERE, \"bt_input_csi300_v2.parquet\")" + _SW),
               ("            cand = held & ~target_mask[t] & can_sell[t] & ~bought_today",
                "            cand = held & (np.ones_like(target_mask[t]) if _GB_SELL_RULE == \"worst_n_drop\""
                " else ~target_mask[t]) & can_sell[t] & ~bought_today")],
    },
    # first_rebalance_day：b1/b2 都用「强制把窗口首日置为调仓日」实现 window_start；
    # b3 **根本没有这一步**（rebalance_days 不碰首日）—— 这是一处未登记的实现分歧，已记 N-38。
    # 日频下三份的调仓掩码本来就是全 True，所以这个开关在日频下按构造无效 —— 正好当阴性对照。
    "P-FRD": {
        "B1": [("HERE = Path(__file__).resolve().parent",
                "HERE = Path(__file__).resolve().parent\nimport os as _os2\n"
                "_GB_FRD = _os2.environ.get(\"GB_FIRST_REBALANCE_DAY\", \"window_start\")"),
               ("    keep[0] = True                                        # 首日建仓",
                "    if _GB_FRD == \"window_start\":\n"
                "        keep[0] = True                                    # 首日建仓（开关：screen）")],
        "B2": [("INPUT = os.path.join(BASE, \"bt_input_csi300_v2.parquet\")",
                "INPUT = os.path.join(BASE, \"bt_input_csi300_v2.parquet\")\n"
                "_GB_FRD = os.environ.get(\"GB_FIRST_REBALANCE_DAY\", \"window_start\")"),
               ("    mask[0] = True",
                "    if _GB_FRD == \"window_start\":\n        mask[0] = True")],
    },
}
#: 打了补丁但开关取「各自的原读法」时的环境 —— Gate 1 用它验证补丁中性。
NATIVE_ENV: dict[str, dict[str, dict[str, str]]] = {
    "P-SELL": {"B1": {}, "B2": {}, "B3": {}},          # 三份默认都是 dropped_from_target
    "P-FRD": {"B1": {}, "B2": {}},                     # b1/b2 默认强制首日建仓 = window_start
}


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class Sandbox:
    def __init__(self, root: Path, patch: str | None = None):
        self.root, self.patch = Path(root), patch
        self.manifest = {"harness": "ops/screen_runner.py", "patch": patch,
                         "impls": {}, "runs": [], "gates": {}}

    def prepare(self, impl: str) -> Path:
        spec = SCRIPTS[impl]
        d = self.root / impl
        d.mkdir(parents=True, exist_ok=True)
        dst = d / spec["src"].name
        shutil.copy2(spec["src"], dst)                       # 源永远只读
        link = d / PANEL.name
        if not link.exists():
            link.symlink_to(PANEL)
        rec = {"src": str(spec["src"]), "src_sha256": sha256(spec["src"])}
        if self.patch:
            src = dst.read_text(encoding="utf-8")
            for anchor, repl in SWITCH_EDITS[self.patch][impl]:
                n = src.count(anchor)
                if n != 1:
                    raise RuntimeError(f"补丁 {self.patch}/{impl} 锚点命中 {n} 次（应为 1）：{anchor[:60]!r}")
                src = src.replace(anchor, repl)
            dst.write_text(src, encoding="utf-8")
            rec |= {"patch": self.patch, "patched_sha256": sha256(dst),
                    "anchors": [a[:48] for a, _ in SWITCH_EDITS[self.patch][impl]]}
        self.manifest["impls"][impl] = rec
        return d

    def run(self, impl: str, freq: str, env: dict[str, str]) -> dict:
        spec, d = SCRIPTS[impl], self.root / impl
        out = d / spec["out"].format(freq=freq)
        out.unlink(missing_ok=True)                          # 不许读上一次的残留
        argv = [a.format(freq=freq) for a in spec["argv"]]
        t0 = time.time()
        proc = subprocess.run([PY, spec["src"].name, *argv], cwd=d, check=True,
                              env={**os.environ, **env}, capture_output=True, text=True, timeout=1800)
        rec = json.loads(out.read_text())
        self.manifest["runs"].append({"impl": impl, "freq": freq, "env": env,
                                      "wall_s": round(time.time() - t0, 2),
                                      "out_sha256": sha256(out), "stderr_tail": proc.stderr[-300:]})
        return rec

    @staticmethod
    def metrics(rec: dict) -> dict[str, float]:
        return {k: v for k, v in rec.items()
                if k not in SKIP_METRICS and isinstance(v, (int, float)) and not isinstance(v, bool)}

    def dump(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest, ensure_ascii=False, indent=1), encoding="utf-8")


#: 复现判据的噪声底。实测：同一脚本同一输入两次跑，指标相对差 ~1e-15（BLAS 线程与归约顺序），
#: **产物不是逐字节可复现的**。ε 带最小的一项是 1e-3 量级，1e-12 与它差九个数量级 —— 用它当"复现"的门槛
#: 既能挡住真正的行为改变，又不会把浮点噪声读成"harness 改了结果"。实测偏差入 manifest，不藏。
REPRO_REL_TOL = 1e-12


def _max_rel(a: dict, b: dict) -> tuple[float, str]:
    worst, name = 0.0, ""
    for k in set(a) | set(b):
        x, y = a.get(k), b.get(k)
        if x is None or y is None:
            return float("inf"), k
        m = max(abs(x), abs(y))
        r = abs(x - y) / m if m > 0 else 0.0
        if r > worst:
            worst, name = r, k
    return worst, name


def _ref(impl: str, freq: str) -> dict:
    return json.loads((SNAP / SCRIPTS[impl]["out"].format(freq=freq)).read_text())


def gate_baseline(root: Path, impls=("B1", "B2", "B3"), freq: str = "daily") -> list[str]:
    """Gate 0：**未打补丁**的沙箱副本必须复现快照里的产物 —— harness 自证不改行为。"""
    sb, bad = Sandbox(root / "gate0", patch=None), []
    for impl in impls:
        sb.prepare(impl)
        got = sb.run(impl, freq, env={})
        rel, worst = _max_rel(Sandbox.metrics(got), Sandbox.metrics(_ref(impl, freq)))
        sb.manifest.setdefault("repro", {})[f"{impl}/{freq}"] = {"max_rel": rel, "worst_metric": worst}
        if rel > REPRO_REL_TOL:
            bad.append(f"{impl}/{freq} 相对差 {rel:.3e}（{worst}）")
    sb.manifest["gates"]["baseline_reproduces"] = not bad
    sb.dump(root / "gate0" / "MANIFEST.json")
    return bad


def gate_patch_neutral(root: Path, patch: str, impls=("B1", "B2", "B3"), freq: str = "daily") -> list[str]:
    """Gate 1：打了补丁、开关取各自原读法时，结果必须与快照逐指标相同。不同 = 补丁动了算法。"""
    sb, bad = Sandbox(root / "neutral", patch=patch), []
    for impl in impls:
        sb.prepare(impl)
        got = sb.run(impl, freq, env=NATIVE_ENV[patch][impl])
        rel, worst = _max_rel(Sandbox.metrics(got), Sandbox.metrics(_ref(impl, freq)))
        sb.manifest.setdefault("repro", {})[f"{impl}/{freq}"] = {"max_rel": rel, "worst_metric": worst}
        if rel > REPRO_REL_TOL:
            bad.append(f"{impl}/{freq} 相对差 {rel:.3e}（{worst}）—— 补丁动了算法")
    sb.manifest["gates"]["patch_neutral"] = not bad
    sb.dump(root / "neutral" / "MANIFEST.json")
    return bad
