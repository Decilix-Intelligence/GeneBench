# FinRobot（AI4Finance-Foundation，PyPI FinRobot==0.1.5）的 GeneBench 接入镜像。
#
# 构建上下文是 f02 上的 /data/genebench_runner/build/finrobot/，里面要有三样：
#   finrobot/           本目录（含 glue/ 与 requirements.gb.txt）
#   genebench_client/   垫片（integrations/genebench_client）
#   finrobot-0.1.5.tar.gz
#                       上游 sdist —— **不在 Dockerfile 里 curl**：构建网可达与否
#                       不是我们能保证的事，而"钉"靠的是字节摘要不是 URL。
#                       下载与两跳 scp 的命令在 README §2。
#
#   在 f01：
#     scp -r integrations/finrobot integrations/genebench_client \
#            ljn@192.168.1.219:/data/genebench_runner/build/finrobot/
#   在 f02（只许从 f01 进）：
#     cd /data/genebench_runner/build/finrobot
#     docker build -t gb-finrobot-u:r1 -f finrobot/Dockerfile .
FROM gb-base:bookworm-r1

# ① 垫片（取数 + emit）。走镜像不走 exec 树。
#
# 基座 python:3.12-slim **没有 setuptools**，而 genebench_client 的 build-backend
# 就是 setuptools.build_meta：直接 `--no-index --no-build-isolation` 会当场
# `BackendUnavailable`（卡 2.6-tradingagents 实测，已记票据）。所以先装构建后端
# （这一步走 index，构建期出网是允许的），垫片本身仍然 `--no-index`。
RUN pip install --no-cache-dir "setuptools>=61" wheel
COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client

# ② FinRobot 的依赖集（**不是上游 requirements.txt**，理由逐条写在文件里：
#    yfinance / tushare / pandas_datareader 有意不装，由垫片顶替）。
COPY finrobot/requirements.gb.txt /tmp/requirements.gb.txt
RUN pip install --no-cache-dir -r /tmp/requirements.gb.txt

# ③ 上游本体。**先核字节再装** —— 版本号不是钉，摘要才是。
#
# `--no-deps`：依赖已由上一层按本环境的口径装好，让 pip 再解一遍会把
#   yfinance / tushare 拖进来（那是绕过网关的路）。
# `--ignore-requires-python`：上游 setup.py 写的是 `>=3.10, <3.12`，
#   基座是 3.12。这是一处**已知偏离**，README §5 有它的实测依据
#   （import + 真跑都过；0.1.5 的代码里没有 3.12 移除的用法）。
ARG FR_VERSION=0.1.5
ARG FR_SHA256=62ac363ed5e23dd5628797bb5e6c2b392012dde9401a1e6d4110f50f5afc8291
COPY finrobot-${FR_VERSION}.tar.gz /tmp/finrobot.tar.gz
RUN set -eux; \
    echo "${FR_SHA256}  /tmp/finrobot.tar.gz" | sha256sum -c -; \
    pip install --no-cache-dir --no-deps --ignore-requires-python /tmp/finrobot.tar.gz; \
    rm -f /tmp/finrobot.tar.gz

# ④ 接线层（不改上游源码：monkeypatch data_source + 配置 + 入口）。
#
# **COPY 会原样带上宿主的文件权限**，而 $GENEBENCH_ROOT 全树受红线 5 守门、一律 0600 ——
# 于是接线层进了镜像也是 0600，而容器以**非 root** 跑：
# `can't open file '/opt/finrobot_glue/run.py': [Errno 13] Permission denied`，
# 两臂十几秒退出、`no_artifact`（卡 2.6-tradingagents 第一次真跑就是这么挂的）。
COPY finrobot/glue/ /opt/finrobot_glue/
RUN chmod -R a+rX /opt/finrobot_glue

# 容器以非 root 跑、HOME 不可写：全部指到可写层，**不要指到 /task 下**
# （那会往 run dir 的 work/ 里多放文件，破 P8 文件集封闭）。
ENV HOME=/tmp/h \
    XDG_CACHE_HOME=/tmp/h/.cache \
    MPLCONFIGDIR=/tmp/h/.mpl \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GENEBENCH_FR_SCRATCH=/tmp/fr

WORKDIR /task
