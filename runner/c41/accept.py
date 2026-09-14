# -*- coding: utf-8 -*-
"""卡 4.1 六条验收。每条给出实测，不给出推断。"""
from __future__ import annotations
import json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, "/data/genebench_runner")
from runner_core import render_compose, lint_compose, db, ROOT

TID = "accept-0001"
d = ROOT / "tasks" / TID
(d / "work").mkdir(parents=True, exist_ok=True)
(d / "log").mkdir(parents=True, exist_ok=True)

PROBE = r'''
import json, os, socket, subprocess
def tcp(host, port, t=4):
    try:
        socket.create_connection((host, port), timeout=t).close(); return True
    except Exception: return False
out = {}
out["FS_A_ls_data_fails"]   = subprocess.run(["ls","/data"],capture_output=True).returncode != 0
out["FS_B_no_host_data_mnt"]= " /data " not in open("/proc/mounts").read()
out["NET_A_gateway_ok"]     = tcp("gateway", 18080)
out["NET_A_direct_gw"]      = tcp("192.168.1.48", 18080)
out["NET_B_kubeapi_blocked"]= not tcp("192.168.1.48", 6443)
out["NET_C_f02_blocked"]    = not tcp("192.168.1.219", 22)
out["NET_D_public_blocked"] = not tcp("1.1.1.1", 443)
json.dump(out, open("/task/probe.json","w")); print(json.dumps(out))
'''
(d / "work" / "probe.py").write_text(PROBE, encoding="utf-8")
c = render_compose(TID, "strict", command='sh -c "python3 /task/probe.py"')
bad = lint_compose(c)
assert not bad, bad
cf = d / "compose.yml"; cf.write_text(c, encoding="utf-8")

subprocess.run(["docker","compose","-f",str(cf),"up","-d","gateway"],capture_output=True,text=True)
time.sleep(3)
r = subprocess.run(["docker","compose","-f",str(cf),"run","--rm","task"],
                   capture_output=True,text=True,timeout=180)
subprocess.run(["docker","compose","-f",str(cf),"down","-v"],capture_output=True,text=True)
p = d / "work" / "probe.json"
res = json.loads(p.read_text()) if p.exists() else {}
print("=== 隔离探测 ===")
for k,v in res.items():
    print(f"  {'✅' if v else '❌'}  {k} = {v}")
if not res: print("  探针没跑起来:", r.stdout[-400:], r.stderr[-400:])
print("\n=== 代理日志 ===")
el = d / "log" / "egress.jsonl"
if el.exists():
    for line in el.read_text().splitlines()[-6:]:
        print("  " + line[:150])
else:
    print("  (无)")
