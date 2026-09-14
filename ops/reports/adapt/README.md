# 适配赛道 v1.0-adapt：结算与出表（卡 4.2-b → 卡 Y2 重写）

**这批数现在是什么**：30 例各有 oracle，**并各有一次真运行**（卡 Y2，2026-09-10）。
`oracle_matrix.{csv,md}` 是 30 行 oracle × 真跑逐例对照；`table.{csv,tex}` 是按
config × arm × level 的五结局。**完成定义是「30 例各有 oracle 与一次真运行」，
不是「都要通过」** —— 结局分布如实报。

> **脚注（N-348，2026-09-10 用户裁定）**：本赛道的题源是**出集规定题的 oracle 产物**
> （探针题不入），这些产物随适配 bundle 进入执行面。
> **跑过适配赛道的被测方，主赛道被引用的那些题算「可能已见过答案」。**
> 逐题清单见 `ops/manifests/v1.0-adapt.json` 的 `exposed_source_tasks`；
> 口径见 `ops/specs/fairness_protocol.md` §7 第 10 条、`ops/reports/known_limits_v1.md` 末节、
> `ops/specs/adaptation_track.md` §7。这句话跟着每一张表走
> （`scorer/report.py::ADAPT_ORACLE_EXPOSURE_NOTE`：`to_latex` 的 caption + `table.csv` 的 `note` 列）。

## 出表（不需要有真跑也跑得通）

```bash
cd /data/shared/genebench/repo
PY=/data/shared/genebench/env/bin/python

$PY ops/reports/adapt/adapt_report.py matrix                     # 只出 30 行 oracle 矩阵，不碰 f02
$PY ops/reports/adapt/adapt_report.py score --remote /data/genebench_runner/adapt/runs/runs
$PY ops/reports/adapt/adapt_report.py score --no-pull            # 已经拉过就别再拉
```

产物：`oracle_matrix.csv` / `oracle_matrix.md`（30 行：level / 题 / 破坏 / 期望 / 实际 / calls）、
`table.csv` / `table.tex`（走 `scorer/report.py::table_adaptation`）、`records.json`、`summary.md`。

## 从零到一次真跑（六步，照抄）

```bash
GB=/data/shared/genebench; PY=$GB/env/bin/python; cd $GB/repo

# ① 生成 30 例（答案面）。**种子固定**：同一份题源上重跑逐字相同。
$PY ops/adaptation_track.py --plan          # 只看选出来哪 30 例
$PY ops/adaptation_track.py --write

# ② 出 30 个 bundle **并在同一步钉真 digest**（红队 2026-09-07 finding 6）：
#    通行证是在**钉好之后**的树上算的。先 pack 再单独 pin，通行证记的是占位那一份，
#    push_guard 必报「内容与通行证不符：image/Dockerfile」、注入器 P3 同样红；不钉又过不了 P4b。
#    默认臂集合 adapt,open,strict —— **第一个必须是干预臂**（N-364）；
#    少写一个臂，注入时 P6b 当场拒（finding 7）。
$PY ops/pack_adaptation.py --pack --write-set-manifest \
    --digest sha256:961e3878b28fc13ef2600254c4c4cbaceb7c337e2944fc173eaba1335752561a \
    --image gb-cx-u:r1

# ③ 推 exec 树（带上 arms.yaml 与 ops/protocol/；白名单已覆盖）。
#    **适配模块的 MANIFEST.json 必须是 released** —— draft 下注入器 P7 拒绝投放，
#    adapt 臂就是个裸臂（实测：22.7 s 中止、零次模型调用）。
$PY ops/adaptation_track.py --write-protocol-manifest
ops/push_exec_to_f02.sh --with-launch-data

# ④ 逐例推 bundle（只走守门脚本）。**落点必须显式声明**（N-348 之后保留的那道更窄的门）：
#    不给 GENEBENCH_PUSH_DEST = 拒；给一个主赛道的 batch 目录 = 拒。
for d in $GB/staging/adapt_bundles/tasks/*/; do id=$(basename $d)
  GENEBENCH_PUSH_DEST=/data/genebench_runner/adapt/tasks \
  ops/push_bundle_to_f02.sh $d /data/genebench_runner/adapt/tasks \
      $GB/staging/adapt_bundles/$id.manifest.json
done

# ⑤ 真跑（**从 f01 侧包 gateway_lock**；每例 --arms adapt）。
#    **不显式给 --max-tokens / --max-calls**（N-388 已裁定）：让注入器按 stage 取档，
#    默认档已经是 6M。先跑 1–2 例看单 run 用量再批跑。
$PY ops/gateway_lock.py --what "Y2: <id> adapt 真跑" -- \
  ssh -o ConnectTimeout=120 ljn@192.168.1.219 \
  "umask 022; export PYTHONDONTWRITEBYTECODE=1; cd /data/genebench_runner/exec && \
   python3 ops/run_f02_a1.py --bundle /data/genebench_runner/adapt/tasks/<id> \
     --manifest /data/genebench_runner/adapt/tasks/<id>.manifest.json \
     --config-id cfg-codex-deepseek --arms adapt --seq 1 --timeout 1500 \
     --run-root /data/genebench_runner/adapt/runs --results-dir /data/genebench_runner/adapt/results"

# ⑥ 结算 + 出表（上面那一节）。
```

**踩过的坑，照抄的时候留意**：

* `run_f02_a1.py` **跑在 f02**。在 f01 上直接跑它，第一件事就是 `FileNotFoundError:
  /data/genebench_runner/adapt/tasks/<id>.manifest.json` —— 那个路径只在对面存在。
* 推送脚本把 manifest 落在 `<DST>/<bundle 名>.manifest.json`，所以 `--manifest` 要写
  `…/tasks/<id>.manifest.json`，不是 `…/tasks/<id>/manifest.json`。
* 网关锁是**全机一把**：别的卡在跑批时，这里会安静地等（日志每 30 秒打一行「等网关锁：当前 {…}」）。
  那是对的，不要绕开（N-125）。
