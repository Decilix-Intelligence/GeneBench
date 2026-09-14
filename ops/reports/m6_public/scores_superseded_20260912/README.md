# scores_superseded_20260912 —— 已作废的那一批读数（留证据，不删）

这 8 份 `*.score.json` 是 **N-611 之前**那批 m6_public 的结算结果：它们跑在**私有 provider**
上（`ops/run_f02_a1.py --provider-root` 被静默忽略），版本轴记的是 `set_version=1.0.15` /
`reference_version=r1.0.22`（私有轴），结果库里对应的行已标 `superseded`。

对应的 run 目录同样留着、同样挪开了：

* f01：`/data/shared/genebench/runs_in/m6_public_polluted_20260912/`
* f02：`/data/genebench_runner/.../polluted_private_provider_20260912/`

**现行的那一批**是 `../scores/` 下 18 份带 `@finance01-e3887dfa` 后缀的文件（公开 provider，
根 sha `561348660a3175b1…`，轴 p1.0.0 / r1.0.23）。任何 `glob("scores/*.score.json")` 的生成器
只应看到那 18 份 —— 这也是把这 8 份挪出 `scores/` 的唯一理由（红队最终轮 minor 8：
两批跨轴记录混在一个目录里，下一个人 glob 会拿到 26 条）。
