"""卡 4.3 §7：冻结 provider 的本机缓存与**两臂各一份独立副本**。

跑在 f02（执行面）—— 与 `runner/inject.py`、`genetask/bundle.py`、`genetask/pin.py` 同一条纪律：
**零 `reference/` 依赖**（AST + 子进程双自证，见 `ops/test_inject.py::test_t11_*`）。

六条决定（规格 §7 的 PA-1..PA-6），每条对应一个失败模式：

* **PA-1** 缓存目录名**就是** sha256 根 —— 「缓存里放的是哪一版」这个问题不可能答错；
  N-23 重建后是**新目录**，不是覆盖。
* **PA-2** 物化后立刻核根**再**入缓存；两臂各复制一份，**复制后各自再核一次**。
  复制后重核抓的是**截断**：盘满时 `copytree` 可能只写了一半而返回成功，
  症状是「因子算出来了，就是数不对」—— 一个不会抛异常的错误。
* **PA-3** 两臂**不共享** provider 目录、不共享只读挂载 ——
  共享一份等于共享一个可写入口，环境等价一旦破，双臂对照就不成立。
* **PA-6** 物化在**注入期**（f02 runner 侧，可信方），不在容器里 ——
  容器里跑 = 让不可信方决定自己拿到什么数据。

**根是现算的**（`pin.provider_root_sha256`），不读 provider 自带 manifest 里记的值。
这条在本仓库已经栽过两次（F7 的 provider 版、冻结门的模板版），不再重复第三次。
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from genetask import pin
from genetask.bundle import PackError

#: 容器内 provider 的落点（compose 把 run/work 挂成 /task）
CONTAINER_PROVIDER_URI = "/task/provider"

#: run dir 里 provider 的相对位置
WORK_PROVIDER_REL = "provider"


@dataclass
class ProviderRef:
    """一份**已核过根**的 provider 引用。"""
    root: Path
    sha256_root: str
    n_files: int


def cache_dir(cache_root, sha256_root: str) -> Path:
    """PA-1：目录名就是 sha256 根。"""
    return Path(cache_root) / "provider" / sha256_root


def materialize(source_root, cache_root, *, expect: str | None = None) -> ProviderRef:
    """把冻结 provider 物化进本机缓存（PA-1/PA-2/PA-6）。

    顺序**不可调换**：现算根 → 核 pin → **再**入缓存。
    先入缓存再核，等于把一份没验过的东西放进了「已验过」的位置，
    而下一次谁也说不清缓存里那个目录是怎么来的。
    """
    src = Path(source_root)
    problems = pin.check_provider_pin(src, expect=expect)
    if problems:
        raise PackError("provider 物化中止：\n  " + "\n  ".join(problems))
    root = pin.provider_root_sha256(src)
    dst = cache_dir(cache_root, root)
    if dst.exists():
        # 已在缓存：**仍然现算一次**再用。缓存目录名对不代表内容没被动过。
        got = pin.provider_root_sha256(dst)
        if got != root:
            raise PackError(f"缓存目录 {dst} 的现算根 {got[:16]}… ≠ 目录名 {root[:16]}… —— "
                            f"缓存被动过，不得使用")
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        got = pin.provider_root_sha256(dst)
        if got != root:
            raise PackError(f"入缓存后现算根 {got[:16]}… ≠ 源 {root[:16]}… —— "
                            f"复制被截断（盘满时 copytree 可能只写一半而返回成功）")
    return ProviderRef(root=dst, sha256_root=root,
                       n_files=sum(1 for p in dst.rglob("*") if p.is_file()))


def place_for_arm(ref: ProviderRef, work_dir) -> dict[str, str]:
    """PA-2/PA-3：从缓存**复制一份**到该臂独占的 `work/provider/`，复制后**再核一次根**。

    返回 `{相对路径: sha256}`，交给 P8 的 `expect_work` —— 这样 provider 也进
    run dir 的文件集封闭，而不是「放进去就不管了」。
    """
    work = Path(work_dir)
    dst = work / WORK_PROVIDER_REL
    if dst.exists():
        raise PackError(f"{dst} 已存在 —— 两臂**不共享** provider（PA-3），也不覆盖")
    shutil.copytree(ref.root, dst)
    got = pin.provider_root_sha256(dst)
    if got != ref.sha256_root:
        raise PackError(f"复制到 {dst} 后现算根 {got[:16]}… ≠ 缓存 {ref.sha256_root[:16]}… —— "
                        f"复制被截断；症状会是「因子算出来了，就是数不对」")
    out: dict[str, str] = {}
    import hashlib
    for p in sorted(dst.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(work))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def provider_root_sha256_of(path) -> str:
    """便捷别名 —— 测试与调用方不必再 import pin。"""
    return pin.provider_root_sha256(path)


def check_arms_do_not_share(strict_work, open_work) -> list[str]:
    """PA-3 的可测形态：两臂的 provider 必须是**两份**，且内容逐字节相同。"""
    a = Path(strict_work) / WORK_PROVIDER_REL
    b = Path(open_work) / WORK_PROVIDER_REL
    bad: list[str] = []
    for d in (a, b):
        if not d.is_dir():
            bad.append(f"PA-3 {d} 不存在 —— 该臂没拿到 provider")
    if bad:
        return bad
    if a.resolve() == b.resolve():
        bad.append(f"PA-3 两臂的 provider 是**同一个目录** {a.resolve()} —— "
                   f"共享一份等于共享一个可写入口，环境等价当场失效")
    if a.is_symlink() or b.is_symlink():
        bad.append("PA-3 provider 是符号链接 —— 那是共享的另一种写法")
    ra, rb = pin.provider_root_sha256(a), pin.provider_root_sha256(b)
    if ra != rb:
        bad.append(f"PA-3 两臂 provider 的根不同：{ra[:16]}… vs {rb[:16]}… —— "
                   f"两臂拿到的数据不一样，对照实验不成立")
    return bad
