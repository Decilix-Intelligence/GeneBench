# -*- coding: utf-8 -*-
"""compose lint 的负例对照：每条规则都必须真的能拦住 —— **而且必须是被它自己拦住的**。

「全红」还不够。一个负例可能因为**别的**规则红，那被测的那条规则其实是空的
（D-06：机制在，保护不在）。所以每个负例都写明期望命中的规则号，逐条核对。

在 f02 上：``python3 negctl_lint.py``；在数据面机器上由 ``ops/test_c41.py`` 跑同一组用例。
"""
import sys
from pathlib import Path

for _p in ("/data/genebench_runner", str(Path(__file__).resolve().parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from runner_core import lint_compose, render_compose      # noqa: E402

BASE = render_compose("negctl", "strict")

#: 负例 -> (改动, 期望命中的规则号)
CASES: dict[str, tuple[str, str]] = {
    "L-1 裸端口映射 8080:8080": (
        BASE.replace("    networks: [gb_task]\n    depends_on",
                     '    networks: [gb_task]\n    ports:\n      - "8080:8080"\n    depends_on'),
        "L-1"),
    "L-2 端口绑 0.0.0.0 而非 LAN": (
        BASE.replace("    networks: [gb_task]\n    depends_on",
                     '    networks: [gb_task]\n    ports:\n      - "0.0.0.0:8080:8080"\n    depends_on'),
        "L-2"),
    "L-3 任务网络不是 internal": (
        BASE.replace("    internal: true\n", ""),
        "L-3"),
    "L-4 网段撞 k3s pod cidr": (
        BASE.replace("172.31.240.0/24", "10.42.9.0/24"),
        "L-4"),
    # **子串判据的盲区**：10.40.0.0/13 覆盖 10.42/16 与 10.43/16，
    # 却一个禁用子串都不含。原来的 `"10.42." in text` 对它完全沉默（卡 4.3 §IN-2）。
    "L-4 超网覆盖 k3s（子串判据看不见）": (
        BASE.replace("172.31.240.0/24", "10.40.0.0/13"),
        "L-4"),
    "L-4 网段撞 tailscale CGNAT": (
        BASE.replace("172.31.240.0/24", "100.100.7.0/24"),
        "L-4"),
    "L-5 任务容器挂宿主机 /data": (
        BASE.replace("    volumes:\n      - /data/genebench_runner/tasks",
                     "    volumes:\n      - /data:/host_data:ro\n      - /data/genebench_runner/tasks"),
        "L-5"),
    # 关键负例：格式完全合规（绑了 LAN 地址），L-1/L-2 都不会响 ——
    # 它证明 L-6 不是 L-1/L-2 的重复，而是独立的一条策略。
    "L-6 代理服务发布端口（格式合规）": (
        BASE.replace("    networks: [gb_task, gb_egress]\n",
                     '    networks: [gb_task, gb_egress]\n    ports:\n      - "192.168.1.219:3128:3128"\n'),
        "L-6"),
    "L-7 任务服务也接了出向网络": (
        BASE.replace("    networks: [gb_task]\n    depends_on",
                     "    networks: [gb_task, gb_egress]\n    depends_on"),
        "L-7"),
    "L-8 运行期 pip install": (
        BASE.replace('command: sh -c "sleep 3600"',
                     'command: sh -c "pip install pandas && sleep 3600"'),
        "L-8"),
    "L-8b 环境里塞了 PIP_INDEX_URL": (
        BASE.replace('      GENEBENCH_ARM: "strict"\n',
                     '      GENEBENCH_ARM: "strict"\n'
                     '      PIP_INDEX_URL: "https://pypi.tuna.tsinghua.edu.cn/simple"\n'),
        "L-8"),
    "L-9 NO_PROXY 里没有 gateway": (
        BASE.replace('      NO_PROXY: "gateway,localhost,127.0.0.1"\n',
                     '      NO_PROXY: "localhost,127.0.0.1"\n'),
        "L-9"),
}

REVERSE = BASE.replace("name: gb-negctl", "name: gb-negctl  # 只改注释")


def main() -> int:
    print("基线（应通过）:", lint_compose(BASE) or "通过")
    if lint_compose(BASE):
        print("**基线就不干净 —— 后面的负例都不作数**")
        return 1

    ok = True
    for name, (text, want) in CASES.items():
        found = lint_compose(text)
        hit = [v for v in found if v.startswith(want)]
        good = bool(hit)
        ok &= good
        print(f"{'红 ✅' if good else '❌'}  {name}"
              f"{'' if good else f'  ← 期望 {want}，实得 {[v[:6] for v in found] or 0}'}")
        if hit:
            print(f"      {hit[0][:118]}")

    rev_clean = not lint_compose(REVERSE)
    ok &= rev_clean
    print(f"{'绿 ✅' if rev_clean else '红 ❌'}  反向对照：只改注释应仍通过")
    print(f"{len(CASES)} 例全部由**各自的**规则拦下" if ok else "**有漏网或串号 —— lint 无效**")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
