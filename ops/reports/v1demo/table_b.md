# Table B — GeneBench 结果库（筛选：batch=v1demo）；构造验收 / 接入验证，**不是实验数据**

| arm | arm_kind | config_id | image_digest | n_runs | reference_version | runner_version | set_version | Cov | PIT | Prov | day_coverage | fid_day_rate | honest_halts | invalid_rate | n_days | n_fetches | n_gold_days | n_non_data_requests | n_requests | n_runs_denom | pit_misses | rho_median | rho_p10 | stage | tau | unobservable_probes_mean |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| open | baseline | cfg-codex-deepseek | gb-cx-u@sha256:961e3878b28f… | 1 | r1.0.20 | 33ab773224a4… | 1.0.13 | 1 | 0.430769 | 1 |  |  | 0 | 0 |  | 4 |  | 6 | 65 | 1 | 37 |  |  | S1 |  | 0 |
| open | baseline | cfg-codex-deepseek | gb-cx-u@sha256:961e3878b28f… | 1 | r1.0.20 | 33ab773224a4… | 1.0.13 |  |  |  |  |  | 0 | 0 |  |  |  |  |  | 1 |  |  |  | S2 |  | 0 |
| open | baseline | cfg-codex-deepseek | gb-cx-u@sha256:961e3878b28f… | 1 | r1.0.20 | 33ab773224a4… | 1.0.13 |  |  |  |  |  | 0 | 0 |  |  |  |  |  | 1 |  |  |  | S3 |  | 0 |
| open | baseline | cfg-codex-deepseek | gb-cx-u@sha256:961e3878b28f… | 1 | r1.0.20 | 33ab773224a4… | 1.0.13 |  |  |  |  |  | 0 | 0 |  |  |  |  |  | 1 |  |  |  | S5 |  | 0 |
| strict | protocol | cfg-codex-deepseek | gb-cx-u@sha256:961e3878b28f… | 1 | r1.0.20 | 33ab773224a4… | 1.0.13 |  |  |  |  |  | 0 | 0 |  |  |  |  |  | 1 |  |  |  | S1 |  | 0 |
| strict | protocol | cfg-codex-deepseek | gb-cx-u@sha256:961e3878b28f… | 1 | r1.0.20 | 33ab773224a4… | 1.0.13 |  |  |  |  |  | 0 | 0 |  |  |  |  |  | 1 |  |  |  | S2 |  | 0 |
| strict | protocol | cfg-codex-deepseek | gb-cx-u@sha256:961e3878b28f… | 1 | r1.0.20 | 33ab773224a4… | 1.0.13 |  |  |  |  |  | 0 | 0 |  |  |  |  |  | 1 |  |  |  | S3 |  | 0 |
| strict | protocol | cfg-codex-deepseek | gb-cx-u@sha256:961e3878b28f… | 1 | r1.0.20 | 33ab773224a4… | 1.0.13 |  |  |  | 1 | 1 | 0 | 0 | 23 |  | 23 |  |  | 1 |  | 1 | 1 | S5 | 0.984006 | 0 |

> set_version = 1.0.13
> reference_version = r1.0.20
> protocol_version = geneprotocol_v1@d6fbcaa08302（裸臂在协议轴上记 `geneprotocol_v1@none` —— 它们不投放协议工件，与协议臂并排不算混轴）
> channel = private
> 记录数 8；筛选 batch=v1demo
