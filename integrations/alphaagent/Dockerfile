# AlphaAgent（RndmVariableQ/AlphaAgent @ b42cb397，论文 arXiv:2502.16789）
# 作为 GeneBench 被测方（P2）的镜像。
#
# 构建上下文是 f02 的 /data/genebench_runner/build/alphaagent/，里面恰好三样：
#   alphaagent/                      ← 仓库里 integrations/alphaagent 的副本
#   genebench_client/                ← 取数垫片与产物助手的源码副本
#   alphaagent-b42cb397.tar.gz       ← 上游源码（**不进仓库**，怎么取见 README §2）
# 构建命令（在 f02）：
#   docker build -t gb-alphaagent-u:r1 -f alphaagent/Dockerfile .
FROM gb-base:bookworm-r1

# ── ⓪ 构建后端。gb-base 里**没有** setuptools（pip list 只有 numpy/pandas/pyarrow 等
#    七个），而下一层的 `--no-build-isolation` 要求后端已在位 ——
#    不装这一行，构建停在 `BackendUnavailable: Cannot import 'setuptools.build_meta'`
#    （实测；finrobot 的 Dockerfile 也有同一行，是本基座的共同前提而非本接入的特例）。
RUN pip install --no-cache-dir "setuptools>=61" wheel

# ── ① 垫片：源码 COPY 进来离线装。**不要** pip install genebench-client 去公网拿 ——
#    它不在任何 index 上，且运行期装包是被禁止的。
COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client

# ── ② AlphaAgent 的运行期依赖，**逐个都是被 import 到的**（静态遍历它 43 个模块得出）：
#      pyparsing      DSL 解析器（alphaagent/dsl/core/parser.py）
#      joblib         算子层并行（alphaagent/dsl/core/operators.py 顶层 import）
#      requests       alphaagent/data/tushare_client.py 顶层 import（重试用的异常类型）
#      python-dotenv  同上（load_dotenv）
#      openai         经边车的模型客户端；run_trajectory 只用 .chat.completions.create
#
#    **明确不装的四类**，每一条都有理由（详见 README §3）：
#      tushare      行情源客户端。红线 5 不给被测系统一条绕过数据面的路；
#                   `import tushare` 由垫片的 compat 层在进程内顶替（glue/bootstrap.py）。
#      numba        alphaagent/dsl/core/accel.py 里是 try/except ImportError 的**可选**加速
#                   （没有它 njit 退化成恒等装饰器，内核走纯 Python 循环，数值结果不变）。
#                   装它要把基座的 numpy 2.5.2 降到 <2 —— 那是动统一基座的数值栈，
#                   而 S3 的产出正是 parquet 数值。宁可慢，不动基座。
#      agentscope   mining extra 的另一条 agent 路（scripts/factor_mining_agentscope.py）。
#                   本接入走的是 alphaagent.factor.mining.loop 这条原生 OpenAI 工具调用路。
#      lightgbm / scikit-learn   model extra，本接入不做模型训练。
RUN pip install --no-cache-dir \
      pyparsing==3.2.5 \
      joblib==1.5.2 \
      requests==2.32.5 \
      python-dotenv==1.1.1 \
      openai==2.7.1

# ── ③ 上游本体。GitHub 在 f02 的构建网里不保证可达，所以走
#    「本地 Mac 下载 tarball（记 commit 与 sha256）→ scp 两跳 → COPY 进来」这条正路，
#    **不在 Dockerfile 里 git clone**。**先核字节再装** —— commit 号不是钉，摘要才是。
#    `--no-deps`：依赖已由上一层按本环境的口径装好；让 pip 再解一遍会把
#    tushare 与 numba 拖进来，前者是绕过网关的路，后者要降 numpy。
ARG AA_COMMIT=b42cb397025510da44355db9dcf278304321f589
ARG AA_SHA256=cddabb7ea2c3df31bf3cfb5f8c8be95427f2913b80965b3d180164a14e274581
COPY alphaagent-b42cb397.tar.gz /tmp/alphaagent.tar.gz
RUN set -eux; \
    echo "${AA_SHA256}  /tmp/alphaagent.tar.gz" | sha256sum -c -; \
    mkdir -p /tmp/aa && tar xzf /tmp/alphaagent.tar.gz -C /tmp/aa; \
    pip install --no-cache-dir --no-deps "/tmp/aa/AlphaAgent-${AA_COMMIT}"; \
    rm -rf /tmp/aa /tmp/alphaagent.tar.gz

# ── ④ 接线层（不改上游源码：sys.modules 顶替 + 同形替换 + 配置）。
#
#    放在 /opt/gb_alphaagent 而不是 /opt/alphaagent：后者会让
#    `python3 /opt/alphaagent/run.py` 把自己的目录放进 sys.path[0]，
#    与 site-packages 里的 `alphaagent` 包抢同一个顶层名字。
#
#    **COPY 会原样带上宿主的文件权限**，而 $GENEBENCH_ROOT 全树受红线 5 守门、
#    一律 0600 —— 于是接线层进了镜像也是 0600，而容器以**非 root** 跑：
#    `can't open file '/opt/gb_alphaagent/run.py': [Errno 13] Permission denied`，
#    两臂十几秒退出、判 no_artifact（卡 2.6-tradingagents 第一次真跑就是这么挂的）。
COPY alphaagent/run.py alphaagent/smoke.py /opt/gb_alphaagent/
COPY alphaagent/glue/ /opt/gb_alphaagent/glue/
RUN chmod -R a+rX /opt/gb_alphaagent

# 运行期断网（除边车与网关）。HOME 指到可写的 /tmp，**不指到 /task**：
# 容器里的 /task 就是 run dir 的 work/，落在它下面的东西会进 run.json 的
# unexpected（integrations/README.md §1④）。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp/h
WORKDIR /task
