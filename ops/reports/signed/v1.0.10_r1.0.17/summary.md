# M6 构造验收合并表（m6 + m6b）

| 批 | run 数 |
| --- | --- |
| `m6` | 21 |
| `m6b` | 8 |

## Table A

- cfg-codex-deepseek / open：SR=0.5 pass@1=0.3333333333333333 ProgressRate=0.5 effect=100.0 Steps=42.714285714285715 Latency=755.0779999999999 越权率=0.021021021021021023 未结算=0
- cfg-codex-deepseek / strict：SR=0.5416666666666666 pass@1=0.25 ProgressRate=0.5416666666666666 effect=100.0 Steps=41.06666666666667 Latency=582.7464666666668 越权率=0.044676409185803755 未结算=1

> 两次 pass 的**题面**同源（v1.0.9 与 v1.0.8 的 instruction 指纹相同，只改了 D 面的判据键）；
> 判据按各自那一批结算时的版本。逐行来源见 `records.json` 的 `batch` 字段。
