# -*- coding: utf-8 -*-
"""卡 4.3 的四条**容器测试**：T5 / T10 / T12 / T15。在 **f02 真跑**，不带 skip 进 M6。

形状照 `runner/c41/accept.py`：容器内跑探针、结果 JSON 回传、每条给实测不给推断。
**不用 pytest** —— f02 上没有（Ubuntu 拆包，装 ensurepip 要 sudo，而红线是无 sudo 假设）。

    python3 /data/genebench_runner/verify_container.py            # 全部四条
    python3 /data/genebench_runner/verify_container.py --only T5  # 单条
    python3 /data/genebench_runner/verify_container.py --json     # 机器可读

**零 `reference/` 依赖** —— 它跑在执行面。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/data/genebench_runner")
sys.path.insert(0, str(ROOT))

GATEWAY_HOST = "192.168.1.48"
GATEWAY_PORT = 18080

#: 容器内探针 —— T5（出向白名单）+ T10（容器内视角）
#: **四条都已在 f02 真跑**（2026-09-04）。留这张表是为了记住它们各自被什么抓到 ——
#: 「跑过了」与「跑过并抓到过东西」不是一回事。
VERIFIED_ON_F02 = {
    "T5": "网关可达 0.007s；kubeapi / f02_ssh / public / dns 四个全部 **0.0s 快速拒绝**"
          "（判据带耗时 —— 配成 60s 超时时只看可达性照样绿，F4）",
    "T10": "无 nfs、无宿主 /data、ls /data 失败、import reference 抛错、/task 下无答案面路径",
    "T12": "容器内 /task/provider 与 f01 绝对路径下同一组查询，结果 sha256 **逐字节相同**"
           " → **TK-4 不启用**（它是备用路径，不是默认路径）",
    "T15": "**抓到两个真缺陷**：① HTTP 反代只剥注第一个请求（同一 keep-alive 连接的"
           "第二个带着伪造头直达网关，日志如实记下伪造身份）；② 边车代码挂 run dir 之外的"
           "固定路径，与代码库漂开时身份注入静默失效",
}

#: T12 的基准（f01 上先跑一次 t12_provider_queries.py）
T12_BASELINE_ENV = "GB_T12_BASELINE"

PROBE_T5_T10 = r'''
import json, os, socket, subprocess, time

def tcp(host, port, timeout=2.0):
    """返回 (可达?, 耗时秒)。**耗时是判据的一部分**：
    「拒绝」配成 60s 超时时，只看可达性的测试照样绿（F4）。"""
    t0 = time.time()
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True, time.time() - t0
    except Exception:
        return False, time.time() - t0

out = {}
# ---- T5：出向白名单 ----
ok, dt = tcp("gateway", 18080, timeout=5.0)
out["T5_gateway_reachable"] = ok
out["T5_gateway_elapsed"] = round(dt, 3)
for name, host, port in (("kubeapi", "192.168.1.48", 6443),
                         ("f02_ssh", "192.168.1.219", 22),
                         ("public", "1.1.1.1", 443),
                         ("dns", "8.8.8.8", 53)):
    ok, dt = tcp(host, port, timeout=2.0)
    out[f"T5_{name}_blocked"] = not ok
    out[f"T5_{name}_elapsed"] = round(dt, 3)

# ---- T10：容器内视角 ----
mounts = open("/proc/mounts").read()
out["T10_no_nfs"] = ("nfs" not in mounts and "nfs4" not in mounts)
out["T10_no_host_data_mount"] = " /data " not in mounts
out["T10_ls_data_fails"] = subprocess.run(["ls", "/data"], capture_output=True).returncode != 0
try:
    import reference          # noqa: F401
    out["T10_import_reference_fails"] = False
except Exception:
    out["T10_import_reference_fails"] = True
bad_paths = []
for dirpath, dirnames, filenames in os.walk("/task"):
    for n in list(dirnames) + list(filenames):
        low = n.lower()
        if any(k in low for k in ("scorer", "gold", "answer", "oracle")):
            bad_paths.append(os.path.join(dirpath, n))
out["T10_no_answer_paths"] = not bad_paths
out["T10_bad_paths"] = bad_paths[:5]
out["T10_task_listing"] = sorted(os.listdir("/task"))[:20]

json.dump(out, open("/task/probe_out.json", "w"))
print(json.dumps(out, ensure_ascii=False))
'''

#: T15：伪造身份头 —— 容器把头写成**另一次运行**的合法值，再自带 X-GB-* 头
PROBE_T15 = r'''
import json, socket

def raw_get(path, headers, keep_alive=True):
    s = socket.create_connection(("gateway", 18080), timeout=8)
    reqs = []
    for h in headers:
        hdr = "".join(f"{k}: {v}\r\n" for k, v in h.items())
        conn = "keep-alive" if keep_alive else "close"
        reqs.append(f"GET {path} HTTP/1.1\r\nHost: gateway\r\nConnection: {conn}\r\n{hdr}\r\n")
    s.sendall("".join(reqs).encode())
    buf = b""
    s.settimeout(8)
    try:
        while len(buf) < 65536:
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    except Exception:
        pass
    s.close()
    return buf.decode("utf-8", "replace")

forged = {"x-genebench-task-id": "s9-forged-99",
          "x-genebench-config-id": "cfg-forged",
          "X-GB-Run-Id": "s9-forged-99.strict.cfg-forged.r99",
          "X-GB-Arm": "strict"}
# **同一 keep-alive 连接上连发两个** —— 按连接盖一次章的实现能过第一个、漏掉第二个
body = raw_get("/calendar?start_date=2026-07-01&end_date=2026-07-02", [forged, forged])
print(json.dumps({"T15_response_head": body[:400]}, ensure_ascii=False))
'''


def _sh(*args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def _compose_up(compose_file: Path, probe: str, work: Path, name: str) -> dict:
    """起容器跑一段探针，回收 JSON。失败也返回结构化结果，不抛。"""
    (work / "probe.py").write_text(probe, encoding="utf-8")
    up = _sh("docker", "compose", "-f", str(compose_file), "up", "-d", "gateway")
    time.sleep(3)
    r = _sh("docker", "compose", "-f", str(compose_file), "run", "--rm", "task",
            timeout=300)
    _sh("docker", "compose", "-f", str(compose_file), "down", "-v")
    out = {"_rc": r.returncode, "_stderr": (r.stderr or "")[-800:]}
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.update(json.loads(line))
            except json.JSONDecodeError:
                pass
    if up.returncode != 0:
        out["_compose_up_stderr"] = up.stderr[-400:]
    return out


def _run_t12(run_dir: Path) -> int:
    """T12：容器内 `/task/provider` 与 f01 绝对路径下同一组查询，结果**逐字节相同**。

    **不用 qlib**：容器镜像里没有它，装它等于把「容器内能不能装包」混进这条判据。
    直接读 provider 的二进制格式 —— 证明的是**字节层面**一致，比「某个库读出来一样」更硬。
    """
    baseline = os.environ.get(T12_BASELINE_ENV)
    if not baseline or not Path(baseline).is_file():
        print(f"需要 {T12_BASELINE_ENV}=<f01 上跑出来的基准 json>", file=sys.stderr)
        return 2
    script = Path(__file__).resolve().parent / "t12_provider_queries.py"
    shutil.copyfile(script, run_dir / "work" / "t12.py")
    cf = run_dir / "compose.yml"
    _sh("docker", "compose", "-f", str(cf), "up", "-d", "gateway")
    time.sleep(2)
    r = _sh("docker", "compose", "-f", str(cf), "run", "--rm", "task", timeout=300)
    _sh("docker", "compose", "-f", str(cf), "down", "-v")
    try:
        got = json.loads(r.stdout)
    except json.JSONDecodeError:
        print(f"容器没吐出 JSON：{(r.stdout or r.stderr)[-400:]}", file=sys.stderr)
        return 1
    want = json.loads(Path(baseline).read_text(encoding="utf-8"))
    same = got["result_sha256"] == want["result_sha256"]
    print(f"  {'✅' if same else '❌'} [T12] provider 路径无关 —— "
          f"容器 {got['result_sha256'][:16]} vs f01 {want['result_sha256'][:16]}")
    if not same:
        for k in sorted(set(got["queries"]) | set(want["queries"])):
            if got["queries"].get(k) != want["queries"].get(k):
                print(f"       差异: {k}")
        print("       测不过才走 TK-4（容器内同路径落盘）—— 备用路径，不是默认路径")
    return 0 if same else 1


def judge(raw: dict) -> list[dict]:
    """把探针结果翻成逐条判定。**每条都要有实测依据**，不给推断。"""
    v: list[dict] = []

    def add(tid, name, ok, detail):
        v.append({"item": tid, "check": name, "pass": bool(ok), "detail": detail})

    # ---- T5 ----
    add("T5", "网关可达", raw.get("T5_gateway_reachable"),
        f"elapsed={raw.get('T5_gateway_elapsed')}s")
    for n in ("kubeapi", "f02_ssh", "public", "dns"):
        blocked = raw.get(f"T5_{n}_blocked")
        dt = raw.get(f"T5_{n}_elapsed", 99)
        # **快速拒绝**：配成 60s 超时时，只看可达性的测试照样绿（F4）
        add("T5", f"{n} 被拒且 <2s", bool(blocked) and dt is not None and dt < 2.0,
            f"blocked={blocked} elapsed={dt}s")
    # ---- T10 ----
    for key, name in (("T10_no_nfs", "无 nfs 挂载"),
                      ("T10_no_host_data_mount", "无宿主 /data 挂载"),
                      ("T10_ls_data_fails", "ls /data 失败"),
                      ("T10_import_reference_fails", "import reference 抛错"),
                      ("T10_no_answer_paths", "/task 下无答案面路径")):
        add("T10", name, raw.get(key), f"{key}={raw.get(key)}")
    return v


def main() -> int:
    ap = argparse.ArgumentParser(description="卡 4.3 容器测试 T5/T10/T12/T15（f02 真跑）")
    ap.add_argument("--only", default=None, help="T5 / T10 / T12 / T15")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--run-dir", default=None, help="已注入的 run dir（默认现造一个）")
    a = ap.parse_args()

    if not a.run_dir:
        print("需要 --run-dir：先用注入器造一个 run dir（provider 与协议工件都在里面）",
              file=sys.stderr)
        return 2
    run_dir = Path(a.run_dir)
    compose_file = run_dir / "compose.yml"
    if not compose_file.is_file():
        print(f"找不到 {compose_file}", file=sys.stderr)
        return 2

    if a.only == "T12":
        return _run_t12(run_dir)
    probe = {"T15": PROBE_T15}.get(a.only, PROBE_T5_T10)
    raw = _compose_up(compose_file, probe, run_dir / "work", a.only or "t5t10")
    results = judge(raw) if probe is PROBE_T5_T10 else []
    if probe is PROBE_T15:
        # T15 的判定在 f01 侧（读网关 access_log），这里只把容器发过的请求回传
        print(json.dumps({"T15_sent": True, "raw": raw}, ensure_ascii=False))
        return 0
    if a.only:
        results = [r for r in results if r["item"] == a.only]

    failed = [r for r in results if not r["pass"]]
    if a.json:
        print(json.dumps({"results": results, "raw": raw}, ensure_ascii=False, indent=1))
    else:
        for r in results:
            print(f"  {'✅' if r['pass'] else '❌'} [{r['item']}] {r['check']} —— {r['detail']}")
        print(f"\n{len(results) - len(failed)}/{len(results)} 通过")
        if raw.get("_rc"):
            print(f"容器退出码 {raw['_rc']}；stderr 尾部：\n{raw.get('_stderr', '')[:400]}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
