# `build/` —— 镜像构建上下文

这棵子树放**构建镜像用的上下文**，不是 Python 打包意义上的 `build/`。

| 目录 | 是什么 |
|---|---|
| [`base/`](base/) | 统一基座 `gb-base:bookworm-r1`。所有 harness 的 `FROM` 都是它。 |

harness 自己的 `Dockerfile` 不在这里 —— 它们各自住在 `harnesses/<id>/`，
由 `harnesses/build.sh` 构建（那个脚本在本机缺基座时会先来 `base/` 把基座构出来）。

> **注意**：仓库根的 `.gitignore` 第 6 行有一条不锚定的 `build/`（Python 打包产物的
> 惯用模式，但 git 的目录模式匹配任意层级），所以这棵子树里的文件是用
> `git add -f` 显式加进来的。**在这里新建文件时 `git status` 不会提醒你**，
> 要自己记得 `git add -f`。根治办法是在 `.gitignore` 里补一行 `!/build/`，
> 见 `ops/tickets_inbox/A2.md` 的 N-752。
