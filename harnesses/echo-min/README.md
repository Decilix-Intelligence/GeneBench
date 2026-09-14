# `echo-min` —— 不调模型的最小 harness

**它不是一个 agent。** 它是一段 115 行的确定性脚本，用来回答一个问题：
**`harnesses/README.md` 的启动契约写对了没有？**

真 agent 跑挂的时候，「文档写错了」与「agent 自己不行」这两件事混在一起
（`harnesses/README.md` §5 那一族「两臂 3 秒退出」的排查条目就是这么来的）。
`echo-min` 把它们分开：它没有能力可言，所以它跑挂了**只可能**是启动契约的问题。

## 它做什么

1. 读 `/task/INSTRUCTION.md`，打印字符数（不打印内容）；
2. 找 `/task/<stage>.json` 结构契约，从 `properties.declarations.required` 取声明键；
3. 看 `/task/protocol/` 在不在（**只有 strict 臂该有**）；
4. 打印启动契约那张环境变量表里每个变量**有没有**（不打印值 —— `OPENAI_API_KEY`
   是公开的占位串，但打印它没有意义）；
5. 把一份产物写到 `/task/artifact.json`：身份三键（`task_id` / `config_id` / `arm`）
   **逐字取环境变量**，所有口径写 `"unresolved"`。

## 模型端点

**本 harness 不调模型。** `env_required` 里仍然列了 `OPENAI_BASE_URL` / `OPENAI_API_KEY`，
因为它要**回声**这两个变量在不在 —— 那正是启动契约里最容易静默出错的一格
（`env_required` 只登记、不校验，名字抄错不会有任何东西变红）。

要把它改成会调模型的 harness：`base_url` 只从 `OPENAI_BASE_URL` 取，
`api_key` 照传 `OPENAI_API_KEY` 那个占位串，真 key 由边车替换。
**不要写死主机名** —— 写死就绕过了边车，预算闸 / `llm_log` / 出向白名单三样同时失效。

## 已知限制

* **它必然拿不到分数。** 所有口径写 `"unresolved"`、payload 是空壳，
  结算大概率判 `malformed` 或 `invalid`。**这是设计**：它验的是链路，不是能力。
  别把它的 run 放进任何一张能力表里读。
* **`HOME` 指到 `/task/.echo-min`**，按 `harnesses/README.md` §1.2 第 1 条写。
  代价是容器退出后 `run.json` 的 `unexpected` 里会出现 `.echo-min/`。
  P2 那份手册（`integrations/README.md` §1④）对自己的代码给的是 `/tmp`，
  两份的差异在那里有原文标注（CONFLICT，不是笔误）。
* **它不打网关**，所以越权率一族探针在它的 run 上没有样本。

## 构建

```sh
# f01
ops/push_exec_to_f02.sh --with-launch-data
# f02（从 f01 发起）
ssh ljn@192.168.1.219 'cd /data/genebench_runner/exec && sh harnesses/build.sh echo-min'
```

构建完把 digest 回填到 `Dockerfile` 顶部的来历注释里，出集时用它。
