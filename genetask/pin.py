"""冻结物的钉子：常量 + 比对函数，**零依赖**（只用标准库）。

为什么单独一个文件（卡 4.3 §1.1 的发现）：`genetask/schema.py` 顶层 `from reference import artifact_schema`，
而注入器与适配层跑在**执行面**（f02）—— 在那里 `import genetask.schema` 会把 `reference/` 拖上执行面，
直接撞红线「reference/ 与 scorer/ 产物不对执行面暴露」。所以钉子放这里，`schema.py` 再导出，
`genetask.schema.check_provider_pin` 这个路径照样成立。

**为什么不在 runner 里复制一份常量**：两份冻结常量必然漂，而漂的那天没有任何东西会报错 ——
正是 D-06 家族要防的形态。
"""
from __future__ import annotations

import hashlib
import pathlib

#: 卡 2.1a 冻结 provider 的 sha256 根（前 8 位；完整值在 f01 的 provider manifest 里）。
#: N-23 若为指数标的重建 provider（v1.1），这个值会变 —— 适配层必须重新钉，**不一致即红**。
PROVIDER_SHA256_ROOT = "54fdda39"
PROVIDER_PIN_LOCK = "provider_sha256_pinned"


#: provider 自带的**逐文件清单**（`<sha256>  <size>  <relpath>` 每行一条）。
#: 冻结值 `PROVIDER_SHA256_ROOT` 就是**这个文件本身**的 sha256（卡 2.1a 的算法，2026-09-04 核实）。
PROVIDER_FILELIST = "files.sha256"
#: 清单自身与 provider 元数据 —— 它们不在清单里（清单不含自己）。
#: `MANIFEST.sha256` 与 `build_info.json` 是**公开 provider 打包器**
#: （`ops/release/pack_public_provider.py`）随树写出的两件构建元数据。它们写在
#: `files.sha256` 生成**之后**，所以和清单自身一样不可能出现在清单里。
#:
#: 不豁免它们的后果不是「多报两条」（用户裁定 ① 走 A，2026-09-10；实测 2026-09-10）：
#: `check_provider_pin` 会在**公开通道的每一次注入**上判 P2 红成
#: 「树里有而清单里没有：MANIFEST.sha256」—— 而那棵树一个字节都没被动过。
#: 症状说的是「provider 被改了」，病因却是「打包器多写了两个文件」，
#: 照着报错去查 provider 的人什么也查不到（与 `runner/inject.py::provider_pin_expect`
#: 里那段「静默回落把拼写错误伪装成数据事故」是同一族的错）。
#: 实测：公开树 2 条 → 0 条；私有树 0 条 → 0 条（私有树里这两个文件本就不存在）。
#:
#: **豁免面必须封闭成这四个字面名字**：写成「凡是 *.json 都放过」或「凡是大写开头都放过」，
#: 就等于把「多出来的文件也是改动」这条判据整片关掉 —— 而那是这个函数唯一能抓到
#: 「加文件」这一类改动的地方。`ops/test_provider_pin_channel.py` 钉着两件事：
#: 豁免名单恰好是这四个，且清单覆盖树里**除这四个之外**的每一个文件。
PROVIDER_META_FILES = frozenset({PROVIDER_FILELIST, "manifest.json",
                                 "MANIFEST.sha256", "build_info.json"})


def provider_root_sha256(provider_root) -> str:
    """**现算** provider 的根 = 现算 `files.sha256` 这个文件的 sha256。

    为什么是它而不是我自己定义的一套遍历（2026-09-04 实测纠正）：
    冻结值 `54fdda39…` 就是这个文件的 sha256（卡 2.1a 定的算法）。
    我第一版自己定义了「relpath\0sha256 排序拼接」，算出来是 `c8506c5c…` ——
    **现算是现算了，算的却不是同一件东西**，于是这道门永远红。
    而一条恒红的门，下一个人会把 expect 改掉或干脆跳过 —— 门就废了。

    「现算」的要点是**不读被查方自报的记录值**（F7），不是「换一套自己的算法」。
    这里现算清单文件本身，再由 `verify_filelist()` 现算树里每个文件与清单逐条比对 ——
    两步合起来才等价于「整棵树没被动过」，且每一步都不采信 manifest.json 里记的数。
    """
    root = pathlib.Path(provider_root)
    if not root.is_dir():
        raise FileNotFoundError(f"provider 根不存在或不是目录：{root}")
    fl = root / PROVIDER_FILELIST
    if not fl.is_file():
        raise FileNotFoundError(f"provider 缺少逐文件清单 {PROVIDER_FILELIST}：{root}")
    return hashlib.sha256(fl.read_bytes()).hexdigest()


def verify_filelist(provider_root, *, sample: int | None = None) -> list[str]:
    """按 `files.sha256` **逐条现算**树里的文件。空列表 = 绿。

    根 hash 只证明「清单没被动过」；这一步才证明「树与清单一致」。
    两步都要 —— 只做前者，换掉一个 .bin 而不动清单就通过了。

    `sample`：只抽查前 N 条（46542 个文件全算约需数十秒）。
    **抽查会在返回值里说明自己抽了多少** —— 「查过了」与「抽查过」不是一回事。
    """
    root = pathlib.Path(provider_root)
    fl = root / PROVIDER_FILELIST
    if not fl.is_file():
        return [f"provider 缺少 {PROVIDER_FILELIST}"]
    bad: list[str] = []
    lines = [l for l in fl.read_text(encoding="utf-8").splitlines() if l.strip()]
    listed = set()
    todo = lines if sample is None else lines[:sample]
    for line in todo:
        want, _size, rel = line.split(None, 2)
        listed.add(rel)
        f = root / rel
        if not f.is_file():
            bad.append(f"清单里有而树里没有：{rel}")
            continue
        if hashlib.sha256(f.read_bytes()).hexdigest() != want:
            bad.append(f"内容与清单不符：{rel}")
    if sample is None:
        actual = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}
        for rel in sorted(actual - {l.split(None, 2)[2] for l in lines} - PROVIDER_META_FILES):
            bad.append(f"树里有而清单里没有：{rel} —— 多出来的文件也是改动")
    return bad


def check_provider_pin(provider_root, *, expect: str | None = None) -> list[str]:
    """卡 4.3 P2：核 provider 的 sha256 根。空列表 = 绿（与 check_export 同风格）。

    三条不得妥协（§4）：① 根现算；② 树不存在 / 为空 → **返回非空**，不是「跳过」（F1）；
    ③ 不一致时列出前 10 条差异 —— 只说「不一致」无法定位。
    """
    # **运行时**取常量，不用默认参数：默认参数在函数定义时求值，
    # 之后谁改了 PROVIDER_SHA256_ROOT（重载、monkeypatch、v1.1 重钉）都不会生效 ——
    # 那种失效是安静的：检查照跑，比的却是旧值。
    expect = PROVIDER_SHA256_ROOT if expect is None else expect
    root = pathlib.Path(provider_root)
    if not root.is_dir():
        return [f"P2 provider 根不存在：{root} —— 这是红，不是「跳过检查」（F1）"]
    files = [p for p in root.rglob("*") if p.is_file()]
    if not files:
        return [f"P2 provider 树为空：{root} —— 空树也能算出一个稳定的 sha256，"
                f"但那不是冻结 provider（F1）"]
    got = provider_root_sha256(root)
    if got.startswith(expect):
        # 根 hash 只证明**清单**没被动过。换掉一个 .bin 而不动清单，根 hash 一个字不变 ——
        # 所以必须再按清单逐条现算一遍（46542 个文件约 2 秒，不值得抽查）。
        return [f"P2 {x}" for x in verify_filelist(root)]
    sample = sorted(str(p.relative_to(root)) for p in files)[:10]
    return [f"P2 provider sha256 根 {got[:16]}… ≠ 冻结值 {expect}… —— provider 变了"
            f"（N-23 的 v1.1 重建？）：{len(files)} 个文件，前 10 个 {sample}；"
            f"不得静默继续 —— 整批实验的可比性挂在这个值上"]


def check_recorded_pin(actual_sha256: str | None) -> list[str]:
    """**记录值**比对：拿别人告诉你的那个根与冻结值比。

    ⚠️ 这只是「记录说它是什么」，不是「它是什么」——**不是完整性判据**。
    完整性判据是 `check_provider_pin()`（规格 §4 的名字，现算的那个）。

    改名的理由（2026-09-04）：规格 §4 把 `check_provider_pin` 定义成
    `(provider_root, *, expect)` 的**现算**函数，而代码一度让记录值版占着这个名字，
    现算版叫 `check_provider_pin_root`。**符号名与规格对不上**，
    卡 4.2 接线时按规格调用会拿到错的那个 —— 而拿到的那个永远返回绿。
    **代码从规格**：现算版占用规格里的名字。

    它还留着是因为适配层拿得到的只有 manifest（拿不到整棵树）；
    但它的返回值**不能**当成「provider 没被动过」的证据。
    """
    if not actual_sha256:
        return [f"N-23 适配层拿不到 provider 的 sha256 根 —— 无法确认用的是冻结 provider"
                f"（应为 {PROVIDER_SHA256_ROOT}…）"]
    if not str(actual_sha256).startswith(PROVIDER_SHA256_ROOT):
        return [f"N-23 provider sha256 根 {str(actual_sha256)[:16]}… ≠ 冻结值 {PROVIDER_SHA256_ROOT}… —— "
                f"provider 变了（v1.1 重建？）：适配层要重新钉 sha256，并复核 gold 是否受影响，不得静默继续"]
    return []
