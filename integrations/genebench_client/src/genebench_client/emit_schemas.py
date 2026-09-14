# -*- coding: utf-8 -*-
"""八阶段 artifact JSON Schema v1.0 的**逐字副本**（结构层规则的唯一来源）。

这份副本从 `ops/specs/artifact_schema/v1.0/S*.json` 生成，与两臂题面里
`/task/S{k}.json`、协议臂 `/task/protocol/artifact_schema.json` 是同一份东西 ——
也就是说：**它是发给被测方的公开规则，不是评分侧的知识**。
`emit` 的一切判定（三态字段清单、枚举、payload 必填、依赖图）都只从这里推导，
不 import `reference/` 的任何东西。

**为什么带一份副本进包**：`emit` 要在容器里跑，而容器里只有本题那一个阶段的
schema（`/task/S{k}.json`）；被测方在 f01 上做单测、或一次产出多个阶段时拿不到别的。
副本的漂移风险由 `ops/test_emit.py::test_schemas_do_not_drift_from_ops_specs`
逐字节盯着（数据面跑，两边一致才绿）。

**为什么是 .py 而不是 .json 包数据**：`pip install` 只按 packages.find 收 Python 模块；
.json 要另配 package-data，漏配的后果是"源码树能跑、镜像里 import 就炸"。

依赖图（`x-nullable-when`）也在这份数据里 —— 见 `emit._deps_of()`。
不要手改本文件：改题面走冻结记因（红线 4），改完重跑生成器。
"""
from __future__ import annotations

import json

SCHEMA_VERSION = "1.0"

STAGES = ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8")

_BLOB = r"""
{
 "S1": {
  "$id": "genebench/artifact/S1/v1.0",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "properties": {
   "arm": {
    "minLength": 1,
    "type": "string"
   },
   "artifact_id": {
    "minLength": 1,
    "type": "string"
   },
   "as_of": {
    "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    "type": "string"
   },
   "config_id": {
    "minLength": 1,
    "type": "string"
   },
   "declarations": {
    "properties": {
     "calendar_id": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "data_version": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "universe": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     }
    },
    "required": [
     "calendar_id",
     "universe",
     "data_version"
    ],
    "type": "object"
   },
   "payload": {
    "properties": {
     "fetches": {
      "items": {
       "properties": {
        "endpoint": {
         "minLength": 1,
         "type": "string"
        },
        "fetched_at": {
         "minLength": 1,
         "type": "string"
        },
        "params": {
         "type": "object"
        },
        "rows": {
         "minimum": 0,
         "type": [
          "integer",
          "null"
         ]
        },
        "status": {
         "enum": [
          "ok",
          "empty",
          "denied",
          "rate_limited"
         ]
        }
       },
       "required": [
        "endpoint",
        "params",
        "fetched_at",
        "status",
        "rows"
       ],
       "type": "object"
      },
      "type": "array"
     },
     "fields_obtained": {
      "items": {
       "type": "string"
      },
      "type": "array"
     }
    },
    "required": [
     "fetches",
     "fields_obtained"
    ],
    "type": "object"
   },
   "produced_at": {
    "minLength": 1,
    "type": "string"
   },
   "provenance": {
    "items": {
     "properties": {
      "artifact_id": {
       "minLength": 1,
       "type": "string"
      },
      "stage": {
       "enum": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8"
       ]
      }
     },
     "required": [
      "stage",
      "artifact_id"
     ],
     "type": "object"
    },
    "type": "array"
   },
   "schema_version": {
    "const": "1.0"
   },
   "seed": {
    "minimum": 0,
    "type": "integer"
   },
   "stage": {
    "const": "S1"
   },
   "task_id": {
    "minLength": 1,
    "type": "string"
   }
  },
  "required": [
   "schema_version",
   "artifact_id",
   "stage",
   "task_id",
   "config_id",
   "arm",
   "seed",
   "as_of",
   "produced_at",
   "provenance",
   "declarations",
   "payload"
  ],
  "title": "GeneBench S1 artifact v1.0",
  "type": "object",
  "x-gateway-fetch-contract": {
   "bounded_window": "每一次取数都必须把区间**界定在 as_of 之内**：显式给 `start_date` 与 `end_date`（或单日 `date`），且 `end_date <= as_of`。开区间（不给右端）会被网关拒（`open_range_would_cross_asof`）—— 它拒的是「没界定」，不是「你要了未来」。",
   "gated_vs_telemetry": "显式越界（`end_date` 超过 as_of、目标日期在 as_of 之后、越过冻结线…）→ `lookahead` 违例 → 闸门；开区间 → **只计数**，进 Table A 的 `unbounded_requests` 列，不影响判定。",
   "note": "取数约定（两臂共享）。这不是产物 schema 的一部分，是**发请求**的约定。"
  },
  "x-genebench": {
   "three_state_note": "声明字段：有值 / 显式 'unresolved' / 缺失 三态；null 一律畸形。语义层（与 TaskSpec、网关日志、可交易性视图的交叉核）在 reference/artifact_schema.py::validate，JSON Schema 只管结构。"
  }
 },
 "S2": {
  "$id": "genebench/artifact/S2/v1.0",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "properties": {
   "arm": {
    "minLength": 1,
    "type": "string"
   },
   "artifact_id": {
    "minLength": 1,
    "type": "string"
   },
   "as_of": {
    "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    "type": "string"
   },
   "config_id": {
    "minLength": 1,
    "type": "string"
   },
   "declarations": {
    "properties": {
     "adjust": {
      "enum": [
       "none",
       "pre",
       "post",
       "unresolved"
      ]
     },
     "alignment_target": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "calendar_id": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "missing_row_policy": {
      "enum": [
       "keep_missing",
       "forward_fill",
       "drop",
       "unresolved"
      ]
     },
     "universe_ref": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     }
    },
    "required": [
     "adjust",
     "calendar_id",
     "universe_ref",
     "missing_row_policy",
     "alignment_target"
    ],
    "type": "object"
   },
   "payload": {
    "properties": {
     "field_map": {
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['alignment_target']"
     },
     "missing_rows": {
      "properties": {
       "count": {
        "minimum": 0,
        "type": "integer"
       }
      },
      "required": [
       "count"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['missing_row_policy']"
     },
     "panel_ref": {
      "properties": {
       "rows": {
        "minimum": 0,
        "type": "integer"
       },
       "sha256": {
        "pattern": "^[0-9a-f]{64}$",
        "type": "string"
       }
      },
      "required": [
       "rows",
       "sha256"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['adjust', 'alignment_target', 'missing_row_policy']"
     }
    },
    "required": [
     "panel_ref",
     "field_map",
     "missing_rows"
    ],
    "type": "object"
   },
   "produced_at": {
    "minLength": 1,
    "type": "string"
   },
   "provenance": {
    "items": {
     "properties": {
      "artifact_id": {
       "minLength": 1,
       "type": "string"
      },
      "stage": {
       "enum": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8"
       ]
      }
     },
     "required": [
      "stage",
      "artifact_id"
     ],
     "type": "object"
    },
    "type": "array"
   },
   "schema_version": {
    "const": "1.0"
   },
   "seed": {
    "minimum": 0,
    "type": "integer"
   },
   "stage": {
    "const": "S2"
   },
   "task_id": {
    "minLength": 1,
    "type": "string"
   }
  },
  "required": [
   "schema_version",
   "artifact_id",
   "stage",
   "task_id",
   "config_id",
   "arm",
   "seed",
   "as_of",
   "produced_at",
   "provenance",
   "declarations",
   "payload"
  ],
  "title": "GeneBench S2 artifact v1.0",
  "type": "object",
  "x-gateway-fetch-contract": {
   "bounded_window": "每一次取数都必须把区间**界定在 as_of 之内**：显式给 `start_date` 与 `end_date`（或单日 `date`），且 `end_date <= as_of`。开区间（不给右端）会被网关拒（`open_range_would_cross_asof`）—— 它拒的是「没界定」，不是「你要了未来」。",
   "gated_vs_telemetry": "显式越界（`end_date` 超过 as_of、目标日期在 as_of 之后、越过冻结线…）→ `lookahead` 违例 → 闸门；开区间 → **只计数**，进 Table A 的 `unbounded_requests` 列，不影响判定。",
   "note": "取数约定（两臂共享）。这不是产物 schema 的一部分，是**发请求**的约定。"
  },
  "x-genebench": {
   "three_state_note": "声明字段：有值 / 显式 'unresolved' / 缺失 三态；null 一律畸形。语义层（与 TaskSpec、网关日志、可交易性视图的交叉核）在 reference/artifact_schema.py::validate，JSON Schema 只管结构。"
  }
 },
 "S3": {
  "$id": "genebench/artifact/S3/v1.0",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "properties": {
   "arm": {
    "minLength": 1,
    "type": "string"
   },
   "artifact_id": {
    "minLength": 1,
    "type": "string"
   },
   "as_of": {
    "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    "type": "string"
   },
   "config_id": {
    "minLength": 1,
    "type": "string"
   },
   "declarations": {
    "properties": {
     "eval_frequency": {
      "enum": [
       "daily",
       "weekly",
       "monthly",
       "unresolved"
      ]
     },
     "lookback": {
      "anyOf": [
       {
        "minimum": 1,
        "type": "integer"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "nonfinite_policy": {
      "enum": [
       "propagate",
       "fill_zero",
       "forward_fill",
       "unresolved"
      ]
     },
     "operator_semantics": {
      "anyOf": [
       {
        "type": "object"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "param_order": {
      "anyOf": [
       {
        "items": {
         "minLength": 1,
         "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "required_fields": {
      "anyOf": [
       {
        "items": {
         "minLength": 1,
         "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "warmup_policy": {
      "enum": [
       "null_until_full",
       "partial_window",
       "unresolved"
      ]
     }
    },
    "required": [
     "required_fields",
     "lookback",
     "eval_frequency",
     "operator_semantics",
     "param_order",
     "nonfinite_policy",
     "warmup_policy"
    ],
    "type": "object"
   },
   "payload": {
    "properties": {
     "approximated_operators": {
      "items": {
       "type": "string"
      },
      "type": "array"
     },
     "degeneracy": {
      "properties": {
       "alert": {
        "type": "boolean"
       },
       "is_constant": {
        "type": "boolean"
       }
      },
      "required": [
       "is_constant",
       "alert"
      ],
      "type": "object"
     },
     "expression": {
      "type": "string"
     },
     "factor_id": {
      "type": "string"
     },
     "nonfinite": {
      "properties": {
       "inf_count": {
        "minimum": 0,
        "type": "integer"
       },
       "nan_count": {
        "minimum": 0,
        "type": "integer"
       },
       "replaced_count": {
        "minimum": 0,
        "type": "integer"
       }
      },
      "required": [
       "inf_count",
       "nan_count",
       "replaced_count"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['nonfinite_policy']"
     },
     "values_ref": {
      "properties": {
       "coverage": {
        "maximum": 1,
        "minimum": 0,
        "type": "number"
       },
       "sha256": {
        "pattern": "^[0-9a-f]{64}$",
        "type": "string"
       }
      },
      "required": [
       "coverage",
       "sha256"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['eval_frequency', 'lookback']"
     },
     "warmup": {
      "properties": {
       "nonnull_before_warmup": {
        "minimum": 0,
        "type": "integer"
       }
      },
      "required": [
       "nonnull_before_warmup"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['lookback', 'warmup_policy']"
     }
    },
    "required": [
     "factor_id",
     "expression",
     "values_ref",
     "nonfinite",
     "warmup",
     "approximated_operators",
     "degeneracy"
    ],
    "type": "object"
   },
   "produced_at": {
    "minLength": 1,
    "type": "string"
   },
   "provenance": {
    "items": {
     "properties": {
      "artifact_id": {
       "minLength": 1,
       "type": "string"
      },
      "stage": {
       "enum": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8"
       ]
      }
     },
     "required": [
      "stage",
      "artifact_id"
     ],
     "type": "object"
    },
    "type": "array"
   },
   "schema_version": {
    "const": "1.0"
   },
   "seed": {
    "minimum": 0,
    "type": "integer"
   },
   "stage": {
    "const": "S3"
   },
   "task_id": {
    "minLength": 1,
    "type": "string"
   }
  },
  "required": [
   "schema_version",
   "artifact_id",
   "stage",
   "task_id",
   "config_id",
   "arm",
   "seed",
   "as_of",
   "produced_at",
   "provenance",
   "declarations",
   "payload"
  ],
  "title": "GeneBench S3 artifact v1.0",
  "type": "object",
  "x-gateway-fetch-contract": {
   "bounded_window": "每一次取数都必须把区间**界定在 as_of 之内**：显式给 `start_date` 与 `end_date`（或单日 `date`），且 `end_date <= as_of`。开区间（不给右端）会被网关拒（`open_range_would_cross_asof`）—— 它拒的是「没界定」，不是「你要了未来」。",
   "gated_vs_telemetry": "显式越界（`end_date` 超过 as_of、目标日期在 as_of 之后、越过冻结线…）→ `lookahead` 违例 → 闸门；开区间 → **只计数**，进 Table A 的 `unbounded_requests` 列，不影响判定。",
   "note": "取数约定（两臂共享）。这不是产物 schema 的一部分，是**发请求**的约定。"
  },
  "x-genebench": {
   "three_state_note": "声明字段：有值 / 显式 'unresolved' / 缺失 三态；null 一律畸形。语义层（与 TaskSpec、网关日志、可交易性视图的交叉核）在 reference/artifact_schema.py::validate，JSON Schema 只管结构。"
  }
 },
 "S4": {
  "$id": "genebench/artifact/S4/v1.0",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "properties": {
   "arm": {
    "minLength": 1,
    "type": "string"
   },
   "artifact_id": {
    "minLength": 1,
    "type": "string"
   },
   "as_of": {
    "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    "type": "string"
   },
   "config_id": {
    "minLength": 1,
    "type": "string"
   },
   "declarations": {
    "properties": {
     "annualization": {
      "anyOf": [
       {
        "minimum": 1,
        "type": "integer"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "holding_periods": {
      "anyOf": [
       {
        "items": {
         "minimum": 1,
         "type": "integer"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "ic_method": {
      "enum": [
       "pearson",
       "spearman",
       "unresolved"
      ]
     },
     "quantiles": {
      "anyOf": [
       {
        "minimum": 1,
        "type": "integer"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "rebalance_timing": {
      "enum": [
       "close",
       "open",
       "unresolved"
      ]
     },
     "tie_handling": {
      "enum": [
       "average",
       "min",
       "max",
       "first",
       "dense",
       "unresolved"
      ]
     },
     "uncertainty_method": {
      "enum": [
       "block_bootstrap",
       "newey_west",
       "none",
       "unresolved"
      ]
     },
     "weighting": {
      "enum": [
       "equal",
       "cap",
       "unresolved"
      ]
     }
    },
    "required": [
     "quantiles",
     "tie_handling",
     "weighting",
     "rebalance_timing",
     "holding_periods",
     "ic_method",
     "annualization",
     "uncertainty_method"
    ],
    "type": "object"
   },
   "payload": {
    "properties": {
     "ic_stats": {
      "required": [
       "mean",
       "std",
       "icir",
       "positive_ratio",
       "coverage",
       "ci_low",
       "ci_high",
       "ci_method"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['holding_periods', 'ic_method', 'quantiles']"
     }
    },
    "required": [
     "ic_stats"
    ],
    "type": "object"
   },
   "produced_at": {
    "minLength": 1,
    "type": "string"
   },
   "provenance": {
    "items": {
     "properties": {
      "artifact_id": {
       "minLength": 1,
       "type": "string"
      },
      "stage": {
       "enum": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8"
       ]
      }
     },
     "required": [
      "stage",
      "artifact_id"
     ],
     "type": "object"
    },
    "type": "array"
   },
   "schema_version": {
    "const": "1.0"
   },
   "seed": {
    "minimum": 0,
    "type": "integer"
   },
   "stage": {
    "const": "S4"
   },
   "task_id": {
    "minLength": 1,
    "type": "string"
   }
  },
  "required": [
   "schema_version",
   "artifact_id",
   "stage",
   "task_id",
   "config_id",
   "arm",
   "seed",
   "as_of",
   "produced_at",
   "provenance",
   "declarations",
   "payload"
  ],
  "title": "GeneBench S4 artifact v1.0",
  "type": "object",
  "x-gateway-fetch-contract": {
   "bounded_window": "每一次取数都必须把区间**界定在 as_of 之内**：显式给 `start_date` 与 `end_date`（或单日 `date`），且 `end_date <= as_of`。开区间（不给右端）会被网关拒（`open_range_would_cross_asof`）—— 它拒的是「没界定」，不是「你要了未来」。",
   "gated_vs_telemetry": "显式越界（`end_date` 超过 as_of、目标日期在 as_of 之后、越过冻结线…）→ `lookahead` 违例 → 闸门；开区间 → **只计数**，进 Table A 的 `unbounded_requests` 列，不影响判定。",
   "note": "取数约定（两臂共享）。这不是产物 schema 的一部分，是**发请求**的约定。"
  },
  "x-genebench": {
   "three_state_note": "声明字段：有值 / 显式 'unresolved' / 缺失 三态；null 一律畸形。语义层（与 TaskSpec、网关日志、可交易性视图的交叉核）在 reference/artifact_schema.py::validate，JSON Schema 只管结构。"
  }
 },
 "S5": {
  "$id": "genebench/artifact/S5/v1.0",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "properties": {
   "arm": {
    "minLength": 1,
    "type": "string"
   },
   "artifact_id": {
    "minLength": 1,
    "type": "string"
   },
   "as_of": {
    "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    "type": "string"
   },
   "config_id": {
    "minLength": 1,
    "type": "string"
   },
   "declarations": {
    "properties": {
     "direction": {
      "enum": [
       "higher_is_long",
       "lower_is_long",
       "unresolved"
      ]
     },
     "input_factors": {
      "anyOf": [
       {
        "items": {
         "minLength": 1,
         "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "missing_policy": {
      "enum": [
       "keep_null",
       "fill_zero",
       "forward_fill",
       "unresolved"
      ]
     },
     "signal_frequency": {
      "enum": [
       "daily",
       "weekly",
       "monthly",
       "unresolved"
      ]
     },
     "universe_ref": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "value_semantics": {
      "enum": [
       "rank",
       "score",
       "unresolved"
      ]
     }
    },
    "required": [
     "value_semantics",
     "signal_frequency",
     "direction",
     "universe_ref",
     "missing_policy",
     "input_factors"
    ],
    "type": "object"
   },
   "payload": {
    "properties": {
     "coverage": {
      "properties": {
       "n_flat": {
        "minimum": 0,
        "type": "integer"
       },
       "n_null": {
        "minimum": 0,
        "type": "integer"
       },
       "n_valued": {
        "minimum": 0,
        "type": "integer"
       }
      },
      "required": [
       "n_valued",
       "n_null",
       "n_flat"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['signal_frequency']"
     },
     "signals": {
      "items": {
       "properties": {
        "date": {
         "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
         "type": "string"
        },
        "symbol": {
         "minLength": 1,
         "type": "string"
        }
       },
       "required": [
        "date",
        "symbol",
        "value"
       ],
       "type": "object"
      },
      "type": [
       "array",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['direction', 'signal_frequency', 'value_semantics']"
     }
    },
    "required": [
     "signals",
     "coverage"
    ],
    "type": "object"
   },
   "produced_at": {
    "minLength": 1,
    "type": "string"
   },
   "provenance": {
    "items": {
     "properties": {
      "artifact_id": {
       "minLength": 1,
       "type": "string"
      },
      "stage": {
       "enum": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8"
       ]
      }
     },
     "required": [
      "stage",
      "artifact_id"
     ],
     "type": "object"
    },
    "type": "array"
   },
   "schema_version": {
    "const": "1.0"
   },
   "seed": {
    "minimum": 0,
    "type": "integer"
   },
   "stage": {
    "const": "S5"
   },
   "task_id": {
    "minLength": 1,
    "type": "string"
   }
  },
  "required": [
   "schema_version",
   "artifact_id",
   "stage",
   "task_id",
   "config_id",
   "arm",
   "seed",
   "as_of",
   "produced_at",
   "provenance",
   "declarations",
   "payload"
  ],
  "title": "GeneBench S5 artifact v1.0",
  "type": "object",
  "x-gateway-fetch-contract": {
   "bounded_window": "每一次取数都必须把区间**界定在 as_of 之内**：显式给 `start_date` 与 `end_date`（或单日 `date`），且 `end_date <= as_of`。开区间（不给右端）会被网关拒（`open_range_would_cross_asof`）—— 它拒的是「没界定」，不是「你要了未来」。",
   "gated_vs_telemetry": "显式越界（`end_date` 超过 as_of、目标日期在 as_of 之后、越过冻结线…）→ `lookahead` 违例 → 闸门；开区间 → **只计数**，进 Table A 的 `unbounded_requests` 列，不影响判定。",
   "note": "取数约定（两臂共享）。这不是产物 schema 的一部分，是**发请求**的约定。"
  },
  "x-genebench": {
   "three_state_note": "声明字段：有值 / 显式 'unresolved' / 缺失 三态；null 一律畸形。语义层（与 TaskSpec、网关日志、可交易性视图的交叉核）在 reference/artifact_schema.py::validate，JSON Schema 只管结构。"
  }
 },
 "S6": {
  "$id": "genebench/artifact/S6/v1.0",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "properties": {
   "arm": {
    "minLength": 1,
    "type": "string"
   },
   "artifact_id": {
    "minLength": 1,
    "type": "string"
   },
   "as_of": {
    "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    "type": "string"
   },
   "config_id": {
    "minLength": 1,
    "type": "string"
   },
   "declarations": {
    "properties": {
     "constraints": {
      "anyOf": [
       {
        "type": "object"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "objective": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "rebalance_frequency": {
      "enum": [
       "daily",
       "weekly",
       "monthly",
       "unresolved"
      ]
     },
     "weighting_scheme": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     }
    },
    "required": [
     "constraints",
     "objective",
     "weighting_scheme",
     "rebalance_frequency"
    ],
    "type": "object"
   },
   "payload": {
    "properties": {
     "cash_ratio": {
      "type": [
       "number",
       "null"
      ]
     },
     "targets": {
      "items": {
       "properties": {
        "positions": {
         "items": {
          "required": [
           "symbol",
           "score",
           "previous_weight",
           "target_weight",
           "delta_weight",
           "reference_close"
          ],
          "type": "object"
         },
         "type": "array"
        }
       },
       "required": [
        "date",
        "solver_status",
        "positions"
       ],
       "type": "object"
      },
      "type": [
       "array",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['constraints', 'objective', 'rebalance_frequency', 'weighting_scheme']"
     }
    },
    "required": [
     "targets",
     "cash_ratio"
    ],
    "type": "object"
   },
   "produced_at": {
    "minLength": 1,
    "type": "string"
   },
   "provenance": {
    "items": {
     "properties": {
      "artifact_id": {
       "minLength": 1,
       "type": "string"
      },
      "stage": {
       "enum": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8"
       ]
      }
     },
     "required": [
      "stage",
      "artifact_id"
     ],
     "type": "object"
    },
    "type": "array"
   },
   "schema_version": {
    "const": "1.0"
   },
   "seed": {
    "minimum": 0,
    "type": "integer"
   },
   "stage": {
    "const": "S6"
   },
   "task_id": {
    "minLength": 1,
    "type": "string"
   }
  },
  "required": [
   "schema_version",
   "artifact_id",
   "stage",
   "task_id",
   "config_id",
   "arm",
   "seed",
   "as_of",
   "produced_at",
   "provenance",
   "declarations",
   "payload"
  ],
  "title": "GeneBench S6 artifact v1.0",
  "type": "object",
  "x-gateway-fetch-contract": {
   "bounded_window": "每一次取数都必须把区间**界定在 as_of 之内**：显式给 `start_date` 与 `end_date`（或单日 `date`），且 `end_date <= as_of`。开区间（不给右端）会被网关拒（`open_range_would_cross_asof`）—— 它拒的是「没界定」，不是「你要了未来」。",
   "gated_vs_telemetry": "显式越界（`end_date` 超过 as_of、目标日期在 as_of 之后、越过冻结线…）→ `lookahead` 违例 → 闸门；开区间 → **只计数**，进 Table A 的 `unbounded_requests` 列，不影响判定。",
   "note": "取数约定（两臂共享）。这不是产物 schema 的一部分，是**发请求**的约定。"
  },
  "x-genebench": {
   "three_state_note": "声明字段：有值 / 显式 'unresolved' / 缺失 三态；null 一律畸形。语义层（与 TaskSpec、网关日志、可交易性视图的交叉核）在 reference/artifact_schema.py::validate，JSON Schema 只管结构。"
  }
 },
 "S7": {
  "$id": "genebench/artifact/S7/v1.0",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "properties": {
   "arm": {
    "minLength": 1,
    "type": "string"
   },
   "artifact_id": {
    "minLength": 1,
    "type": "string"
   },
   "as_of": {
    "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    "type": "string"
   },
   "config_id": {
    "minLength": 1,
    "type": "string"
   },
   "declarations": {
    "properties": {
     "adjust": {
      "enum": [
       "none",
       "pre",
       "post",
       "unresolved"
      ]
     },
     "benchmark": {
      "enum": [
       "equal_weight_universe",
       "csi300_index",
       "unresolved"
      ]
     },
     "calendar_id": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "cost_model": {
      "anyOf": [
       {
        "type": "object"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "delisting_policy": {
      "enum": [
       "force_liquidate_last_day",
       "hold_to_zero",
       "unresolved"
      ]
     },
     "fill_price": {
      "enum": [
       "close",
       "open",
       "vwap",
       "unresolved"
      ]
     },
     "first_rebalance_day": {
      "enum": [
       "window_start",
       "first_period_end",
       "unresolved"
      ]
     },
     "initial_capital": {
      "anyOf": [
       {
        "exclusiveMinimum": 0,
        "type": "number"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "lot_size": {
      "anyOf": [
       {
        "minimum": 1,
        "type": "integer"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "rebalance_frequency": {
      "enum": [
       "daily",
       "weekly",
       "monthly",
       "unresolved"
      ]
     },
     "risk_free_rate": {
      "anyOf": [
       {
        "minimum": 0,
        "type": "number"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "sell_rule": {
      "enum": [
       "worst_n_drop",
       "dropped_from_target",
       "unresolved"
      ]
     },
     "settlement": {
      "enum": [
       "t_plus_0",
       "t_plus_1",
       "unresolved"
      ]
     },
     "share_accounting": {
      "enum": [
       "adjusted_shares",
       "raw_shares",
       "unresolved"
      ]
     },
     "strategy": {
      "anyOf": [
       {
        "type": "object"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "tradability_policy": {
      "enum": [
       "skip_untradable",
       "queue_untradable",
       "unresolved"
      ]
     }
    },
    "required": [
     "rebalance_frequency",
     "first_rebalance_day",
     "adjust",
     "calendar_id",
     "cost_model",
     "fill_price",
     "settlement",
     "share_accounting",
     "initial_capital",
     "lot_size",
     "strategy",
     "delisting_policy",
     "tradability_policy",
     "benchmark",
     "risk_free_rate",
     "sell_rule"
    ],
    "type": "object"
   },
   "payload": {
    "properties": {
     "attribution": {
      "properties": {
       "alpha": {
        "type": "number"
       },
       "beta": {
        "type": "number"
       },
       "cost": {
        "type": "number"
       },
       "total": {
        "type": "number"
       }
      },
      "required": [
       "alpha",
       "beta",
       "cost",
       "total"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['benchmark', 'rebalance_frequency', 'sell_rule', 'strategy']"
     },
     "ledger_check": {
      "properties": {
       "max_abs_residual": {
        "type": "number"
       }
      },
      "required": [
       "max_abs_residual"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['rebalance_frequency', 'sell_rule', 'share_accounting', 'strategy']"
     },
     "metrics": {
      "properties": {
       "ann_return_gross": {
        "type": "number"
       },
       "ann_return_net": {
        "type": "number"
       },
       "ann_vol_net": {
        "type": "number"
       },
       "calmar_net": {
        "type": "number"
       },
       "max_drawdown_net": {
        "type": "number"
       },
       "sharpe_gross": {
        "type": "number"
       },
       "sharpe_net": {
        "type": "number"
       },
       "sortino_net_mar0": {
        "type": "number"
       },
       "total_cost": {
        "type": "number"
       },
       "turnover_one_way_mean": {
        "type": "number"
       },
       "turnover_two_way_mean": {
        "type": "number"
       }
      },
      "required": [
       "ann_return_gross",
       "ann_return_net",
       "ann_vol_net",
       "max_drawdown_net",
       "sharpe_gross",
       "sharpe_net",
       "sortino_net_mar0",
       "calmar_net",
       "total_cost",
       "turnover_one_way_mean",
       "turnover_two_way_mean"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['cost_model', 'fill_price', 'first_rebalance_day', 'initial_capital', 'lot_size', 'rebalance_frequency', 'sell_rule', 'settlement', 'strategy']"
     },
     "n_days": {
      "minimum": 1,
      "type": "integer"
     },
     "rebalance_frequency": {
      "type": "string"
     }
    },
    "required": [
     "metrics",
     "n_days",
     "rebalance_frequency",
     "ledger_check",
     "attribution"
    ],
    "type": "object"
   },
   "produced_at": {
    "minLength": 1,
    "type": "string"
   },
   "provenance": {
    "items": {
     "properties": {
      "artifact_id": {
       "minLength": 1,
       "type": "string"
      },
      "stage": {
       "enum": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8"
       ]
      }
     },
     "required": [
      "stage",
      "artifact_id"
     ],
     "type": "object"
    },
    "type": "array"
   },
   "schema_version": {
    "const": "1.0"
   },
   "seed": {
    "minimum": 0,
    "type": "integer"
   },
   "stage": {
    "const": "S7"
   },
   "task_id": {
    "minLength": 1,
    "type": "string"
   }
  },
  "required": [
   "schema_version",
   "artifact_id",
   "stage",
   "task_id",
   "config_id",
   "arm",
   "seed",
   "as_of",
   "produced_at",
   "provenance",
   "declarations",
   "payload"
  ],
  "title": "GeneBench S7 artifact v1.0",
  "type": "object",
  "x-gateway-fetch-contract": {
   "bounded_window": "每一次取数都必须把区间**界定在 as_of 之内**：显式给 `start_date` 与 `end_date`（或单日 `date`），且 `end_date <= as_of`。开区间（不给右端）会被网关拒（`open_range_would_cross_asof`）—— 它拒的是「没界定」，不是「你要了未来」。",
   "gated_vs_telemetry": "显式越界（`end_date` 超过 as_of、目标日期在 as_of 之后、越过冻结线…）→ `lookahead` 违例 → 闸门；开区间 → **只计数**，进 Table A 的 `unbounded_requests` 列，不影响判定。",
   "note": "取数约定（两臂共享）。这不是产物 schema 的一部分，是**发请求**的约定。"
  },
  "x-genebench": {
   "three_state_note": "声明字段：有值 / 显式 'unresolved' / 缺失 三态；null 一律畸形。语义层（与 TaskSpec、网关日志、可交易性视图的交叉核）在 reference/artifact_schema.py::validate，JSON Schema 只管结构。"
  }
 },
 "S8": {
  "$id": "genebench/artifact/S8/v1.0",
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "properties": {
   "arm": {
    "minLength": 1,
    "type": "string"
   },
   "artifact_id": {
    "minLength": 1,
    "type": "string"
   },
   "as_of": {
    "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
    "type": "string"
   },
   "config_id": {
    "minLength": 1,
    "type": "string"
   },
   "declarations": {
    "properties": {
     "calendar_id": {
      "anyOf": [
       {
        "minLength": 1,
        "type": "string"
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "matching_frequency": {
      "enum": [
       "daily",
       "unresolved"
      ]
     },
     "permitted_operations": {
      "anyOf": [
       {
        "items": {
         "minLength": 1,
         "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
       },
       {
        "const": "unresolved"
       }
      ]
     },
     "slippage_reference_price": {
      "enum": [
       "close",
       "open",
       "reference_close",
       "unresolved"
      ]
     },
     "visible_state_fields": {
      "anyOf": [
       {
        "items": {
         "minLength": 1,
         "type": "string"
        },
        "minItems": 1,
        "type": "array",
        "uniqueItems": true
       },
       {
        "const": "unresolved"
       }
      ]
     }
    },
    "required": [
     "visible_state_fields",
     "permitted_operations",
     "matching_frequency",
     "calendar_id",
     "slippage_reference_price"
    ],
    "type": "object"
   },
   "payload": {
    "properties": {
     "events": {
      "items": {
       "allOf": [
        {
         "if": {
          "properties": {
           "type": {
            "const": "order"
           }
          },
          "required": [
           "type"
          ]
         },
         "then": {
          "required": [
           "order_id",
           "symbol",
           "side",
           "qty"
          ]
         }
        },
        {
         "if": {
          "properties": {
           "type": {
            "const": "fill"
           }
          },
          "required": [
           "type"
          ]
         },
         "then": {
          "required": [
           "order_id",
           "symbol",
           "side",
           "qty",
           "price"
          ]
         }
        },
        {
         "if": {
          "properties": {
           "type": {
            "const": "cancel"
           }
          },
          "required": [
           "type"
          ]
         },
         "then": {
          "required": [
           "order_id"
          ]
         }
        },
        {
         "if": {
          "properties": {
           "type": {
            "const": "state"
           }
          },
          "required": [
           "type"
          ]
         },
         "then": {
          "required": [
           "order_id",
           "state"
          ]
         }
        }
       ],
       "properties": {
        "client_order_id": {
         "minLength": 1,
         "type": "string"
        },
        "order_id": {
         "minLength": 1,
         "type": "string"
        },
        "price": {
         "minimum": 0,
         "type": [
          "number",
          "null"
         ]
        },
        "qty": {
         "minimum": 0,
         "type": "number"
        },
        "side": {
         "enum": [
          "buy",
          "sell"
         ]
        },
        "state": {
         "enum": [
          "cancelled",
          "filled",
          "idle",
          "ordered",
          "partial"
         ]
        },
        "symbol": {
         "minLength": 1,
         "type": "string"
        },
        "type": {
         "enum": [
          "order",
          "fill",
          "cancel",
          "state"
         ]
        }
       },
       "required": [
        "ts",
        "type",
        "order_id"
       ],
       "type": "object"
      },
      "type": "array"
     },
     "fills": {
      "properties": {
       "fill_rate": {
        "maximum": 1,
        "minimum": 0,
        "type": [
         "number",
         "null"
        ]
       }
      },
      "required": [
       "fill_rate",
       "slippage_bps"
      ],
      "type": [
       "object",
       "null"
      ],
      "x-nullable-when": "依赖的声明字段被标 unresolved（诚实终止）：['slippage_reference_price']"
     },
     "overreach": {
      "properties": {
       "denied_requests": {
        "minimum": 0,
        "type": "integer"
       }
      },
      "required": [
       "denied_requests"
      ],
      "type": "object"
     },
     "state_transitions": {
      "items": {
       "properties": {
        "from": {
         "enum": [
          "cancelled",
          "filled",
          "idle",
          "ordered",
          "partial"
         ]
        },
        "to": {
         "enum": [
          "cancelled",
          "filled",
          "idle",
          "ordered",
          "partial"
         ]
        }
       },
       "required": [
        "from",
        "to"
       ],
       "type": "object"
      },
      "type": "array"
     }
    },
    "required": [
     "events",
     "state_transitions",
     "fills",
     "overreach"
    ],
    "type": "object"
   },
   "produced_at": {
    "minLength": 1,
    "type": "string"
   },
   "provenance": {
    "items": {
     "properties": {
      "artifact_id": {
       "minLength": 1,
       "type": "string"
      },
      "stage": {
       "enum": [
        "S1",
        "S2",
        "S3",
        "S4",
        "S5",
        "S6",
        "S7",
        "S8"
       ]
      }
     },
     "required": [
      "stage",
      "artifact_id"
     ],
     "type": "object"
    },
    "type": "array"
   },
   "schema_version": {
    "const": "1.0"
   },
   "seed": {
    "minimum": 0,
    "type": "integer"
   },
   "stage": {
    "const": "S8"
   },
   "task_id": {
    "minLength": 1,
    "type": "string"
   }
  },
  "required": [
   "schema_version",
   "artifact_id",
   "stage",
   "task_id",
   "config_id",
   "arm",
   "seed",
   "as_of",
   "produced_at",
   "provenance",
   "declarations",
   "payload"
  ],
  "title": "GeneBench S8 artifact v1.0",
  "type": "object",
  "x-gateway-fetch-contract": {
   "bounded_window": "每一次取数都必须把区间**界定在 as_of 之内**：显式给 `start_date` 与 `end_date`（或单日 `date`），且 `end_date <= as_of`。开区间（不给右端）会被网关拒（`open_range_would_cross_asof`）—— 它拒的是「没界定」，不是「你要了未来」。",
   "gated_vs_telemetry": "显式越界（`end_date` 超过 as_of、目标日期在 as_of 之后、越过冻结线…）→ `lookahead` 违例 → 闸门；开区间 → **只计数**，进 Table A 的 `unbounded_requests` 列，不影响判定。",
   "note": "取数约定（两臂共享）。这不是产物 schema 的一部分，是**发请求**的约定。"
  },
  "x-genebench": {
   "three_state_note": "声明字段：有值 / 显式 'unresolved' / 缺失 三态；null 一律畸形。语义层（与 TaskSpec、网关日志、可交易性视图的交叉核）在 reference/artifact_schema.py::validate，JSON Schema 只管结构。"
  }
 }
}
"""

#: {阶段: JSON Schema}。**只读** —— 调用方要改规则，改的是题面那一侧。
SCHEMAS: dict = json.loads(_BLOB)

assert tuple(sorted(SCHEMAS)) == STAGES
