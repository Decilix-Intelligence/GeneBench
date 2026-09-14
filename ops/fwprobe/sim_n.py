"""SIM-N：从 f02 的**任务容器**（internal 网络、只经边车）能不能打到 /sim/state。

判据（卡 4.4 §5）：**打得到**即过；打不到即说明它没挂在网关同端口下。
「打得到」= 答的是**我们的**体：有会话时 200 的状态体（cash / positions / nav，契约 §3），
或没会话时 404 且 reason 是我们自己的；路由没挂时答的是 FastAPI 的 `{"detail":"Not Found"}`。
（2026-09-04 首版写在端点落地之前，只认 404；2026-09-05 端点 + 会话工厂（N-87）落地后，
任务容器第一次打就是 200 —— 断言按契约更新。）

身份（ID-1..ID-5）的证据**不在响应体里**：边车剥掉 agent 发的全部身份头再注入 runner 真值，
网关按真值切片写 access_log。所以 [3]/[4] 在这里只负责「发 / 伪造」，核对在数据面 f01 的
`logs/gateway_access.jsonl` 里做：`run_id == "simn.r01"` 的每一条，task_id / config_id 必须都是 runner 真值。
"""
import json, os, urllib.error, urllib.request

gw = os.environ["GENEBENCH_GATEWAY"]
H = {"x-genebench-config-id": os.environ.get("GENEBENCH_CONFIG_ID", ""),
     "x-genebench-task-id": os.environ.get("GENEBENCH_TASK_ID", "")}
STATE_KEYS = {"cash", "positions", "nav"}


def hit(path, headers=H):
    req = urllib.request.Request(gw + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def ours(code, body):
    return (code == 200 and STATE_KEYS <= set(body)) or \
           (code == 404 and body.get("reason") == "dataset_not_exposed_in_v1")


code, body = hit("/sim/state")
print(f"[1] /sim/state -> {code} keys={sorted(body)[:6]}")
assert ours(code, body), f"打不到 /sim/state（或答的是路由级 404）：{code} {body}"
print("    打得到 ✓（答的是**我们的**体，不是 FastAPI 的 detail:Not Found）")

code2, body2 = hit("/sim/session")
print(f"[2] 未登记的第六条 /sim/session -> {code2} {json.dumps(body2, ensure_ascii=False)[:50]}")
assert code2 == 404 and body2.get("detail") == "Not Found", \
    "白名单外的路径居然可达 —— 逐条登记就是为了让它 404"

code3, body3 = hit("/sim/state", headers={})
print(f"[3] 一个身份头都不发 -> {code3}（身份核对在 f01 access_log：run_id=simn.r01）")
assert ours(code3, body3), body3

forged = {"x-genebench-config-id": "cfg-forged", "x-genebench-task-id": "t-forged",
          "x-gb-run-id": "forged.r99"}
code4, body4 = hit("/sim/state", headers=forged)
print(f"[4] agent 伪造身份 -> {code4}（若穿透，f01 日志里会出现 cfg-forged / t-forged / forged.r99）")
assert ours(code4, body4), body4

code5, _ = hit("/healthz")
print(f"[5] 对照：/healthz -> {code5}（说明网络与边车本身没问题）")
assert code5 == 200
print("\nSIM-N（容器侧）过：/sim/state 挂在网关同端口下，任务容器经既有白名单够得着；"
      "身份注入的核对见 f01 access_log。")
