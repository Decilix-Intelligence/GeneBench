# `openhands` —— OpenHands（P1 通用软件工程 agent）

| | |
|---|---|
| harness 名 | `OpenHands` |
| 镜像 | `gb-oh-u:r1`，digest `sha256:ccfae0c3fd9164fbd460396f99e8d1dc935eea79d00779755124d3884abf6f18` |
| 版本 | `openhands-ai==1.11.0`（PyPI，构建期装在统一基座上） |
| 范式 | P1 |
| 内置配置 | `cfg-openhands-deepseek`（本目录的 `config.yaml` 因此 `enabled: false`） |

## 怎么把模型指到 OpenAI 兼容端点

**这个版本没有 CLI。** 2026-09-05 在 f02 离线实测：`openhands-ai==1.11.0` 只装了
`openhands.sdk` 与几个 server，`openhands` 命令与 `python -m openhands.core.main`
**都不存在**。所以 `launch.json` 的 `command` 里内联了一段最小 SDK 驱动（heredoc）：

```python
llm = LLM(model="openai/deepseek-chat", api_key=os.environ["LLM_API_KEY"],
          base_url=os.environ["LLM_BASE_URL"], temperature=0.0)
agent = Agent(llm=llm, tools=get_default_tools(enable_browser=False))
conv = Conversation(agent, workspace="/task")
conv.send_message(open("/task/INSTRUCTION.md", encoding="utf-8").read())
conv.run(); conv.close()
```

要点：

* 走的是 **`LLM_BASE_URL` / `LLM_API_KEY`** 这一对（不是 `OPENAI_*`）—— 两对变量
  容器里都有、指向同一个边车端口，`env_required` 里列哪一对就用哪一对。
* `model="openai/deepseek-chat"` 的 `openai/` 前缀是 litellm 的 provider 前缀，
  意思是"按 OpenAI 兼容协议说话"，不是真去 openai.com。
* **驱动内联在命令里，不落文件。** 不能把它写成 `work/driver.py`：`work/` 是 P8
  文件集封闭的，多一个文件当场红。
* `enable_browser=False`：`gb_task` 网络是 `internal: true`，浏览器工具只会超时，
  而超时会被记成 agent 的失败。

## 已知限制 / 踩过的坑

* **`HOME` 必须指到 `/task` 下。** SDK 的 `LLMProfileStore` 要写 `~/.openhands/profiles`；
  容器以 uid 1000 跑、HOME 不可写 → 2026-09-05 实测 `PermissionError: /.openhands`，
  **两臂 20 秒退出、零次调用**。命令里 `export HOME=/task/.oh_home && mkdir -p $$HOME`。
* heredoc 那段是 Python，读 `os.environ`，**没有裸 `$`**，所以它不受 N-101 的
  compose 插值影响；但 heredoc 外面那半句（`mkdir -p $$HOME`）受，照样写 `$$`。
* 版本升级要重看这份：`get_default_tools` 与 `Conversation(workspace=…)` 的签名
  在 1.x 里动过。升级 = 换镜像 tag + 换 digest + 改本文件，不是原地覆盖 `gb-oh-u:r1`。
