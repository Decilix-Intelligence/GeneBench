# integrations/finmem —— FinMem 作为被测方（P2）的镜像。
#
# 镜像名 gb-finmem-u:r1；digest 与构建命令见本目录 README.md「镜像」一节。
#
# 构建上下文是 f02 上的 /data/genebench_runner/build/finmem/，里面三样：
#   finmem/（本目录）、genebench_client/（垫片）、源码 tarball。
#   在 f01：
#     scp -r integrations/finmem integrations/genebench_client \
#            ljn@192.168.1.219:/data/genebench_runner/build/finmem/
#   在 f02（只许从 f01 进）：
#     cd /data/genebench_runner/build/finmem
#     docker build -t gb-finmem-u:r1 -f finmem/Dockerfile .
FROM gb-base:bookworm-r1

# ── 1. 一份 CPython 3.10 ────────────────────────────────────────────────
# 基座是 python:3.12（实测 `python3 -V` → 3.12.14），而 FinMem 的
# pyproject 写死 `python = ">= 3.10, < 3.11"`，冻结清单每一行也带同样的
# 环境标记。在 3.12 上 pip 会把每一行都判为不适用、**一个包都不装且不报错**；
# 就算强行去掉标记，faiss-cpu 1.7.4 与 pydantic 2.4.2 在 cp312 上也没有轮子。
# 所以这里用 uv 装一份独立的 CPython 3.10（构建期出网实测可达；docker.io 被墙，
# 但这条走的是 PyPI 与 astral 的发行包，不是拉基础镜像）。
RUN pip install --no-cache-dir "uv==0.12.10"
ENV UV_PYTHON_INSTALL_DIR=/opt/pys
RUN uv python install 3.10 && uv venv --python 3.10 /opt/finmem/venv

# ── 2. 依赖（上游自己的冻结清单，减 torch）─────────────────────────────
COPY finmem/requirements.gb.txt /opt/finmem/requirements.gb.txt
RUN uv pip install --python /opt/finmem/venv/bin/python --no-cache \
        "setuptools>=61" wheel pandas -r /opt/finmem/requirements.gb.txt

# ── 3. 被测系统本体（源码，钉 commit）──────────────────────────────────
# **不在 Dockerfile 里 clone/curl**：GitHub 在构建网里可不可达是一件会变的事
# （2026-09-07 实测 codeload 200，而 2.6-tradingagents 那一轮实测超时）。
# tarball 由构建者预先取好放进上下文，sha256 钉在 pin.json 里。
COPY FinMem-LLM-StockTrading-be814aa47970de9bf2fdd6a1d5a60ae5cf361b46.tar.gz \
     /opt/finmem/src.tar.gz
RUN mkdir -p /opt/finmem/src \
 && tar xzf /opt/finmem/src.tar.gz -C /opt/finmem/src --strip-components=1 \
 && rm -f /opt/finmem/src.tar.gz \
 # 上游仓库里带了一个 .env（示例占位）。容器里的凭据只能来自边车注入的环境变量，
 # 镜像里不留任何形似凭据的文件 —— 删掉，且我们的入口不调 load_dotenv()。
 && rm -f /opt/finmem/src/.env \
 # 一段 25 MB 的演示视频与一个示例数据 zip，运行不需要。
 && rm -f /opt/finmem/src/FinMem.mp4 /opt/finmem/src/data-pipeline/Fake-Sample-Data.zip \
 && rm -rf /opt/finmem/src/figures

# ── 4. 取数垫片 ────────────────────────────────────────────────────────
# 走镜像不走 exec 树；--no-index 是因为它不在任何 index 上，
# 而且运行期装包被禁（运行期断网）。
COPY genebench_client/ /opt/genebench_client/
RUN uv pip install --python /opt/finmem/venv/bin/python --no-cache \
        --no-index --no-build-isolation /opt/genebench_client

# ── 5. 接线层与入口 ────────────────────────────────────────────────────
# **内核一个字没改** —— glue/ 里全是子类、模块属性顶替与配置。
COPY finmem/run.py /opt/finmem/run.py
COPY finmem/glue/ /opt/finmem/glue/
COPY finmem/smoke_in_container.py /opt/finmem/smoke_in_container.py
# 仓库里这些文件是 0600（红线 5 要求 $GENEBENCH_ROOT 全树 go-rwx），COPY 原样带进镜像。
# 容器以 user 1000:1000 跑，那时 0600 的入口**读不了** —— 现场表现是
# `python3: can't open file ... Permission denied`（2.6-tradingagents 撞过一次）。
RUN chmod -R a+rX /opt/finmem /opt/genebench_client /opt/pys

# 容器 HOME 不可写；指到可写层，**不要指到 /task 下**（那会破 P8 文件集封闭）。
ENV HOME=/tmp/h \
    XDG_CACHE_HOME=/tmp/h/.cache \
    PYTHONDONTWRITEBYTECODE=1 \
    GENEBENCH_FINMEM_SRC=/opt/finmem/src \
    GENEBENCH_FINMEM_WORKDIR=/tmp/finmem

# runnable_check（pin.json 里逐字同一条）：装没装上、接线点在不在。
RUN /opt/finmem/venv/bin/python -c "import sys; sys.path[:0]=['/opt/finmem/src','/opt/finmem']; \
import puppy, puppy.memorydb as M, puppy.chat as C, genebench_client, genebench_client.emit; \
print(puppy.LLMAgent.__name__, puppy.MarketEnvironment.__name__, \
M.OpenAILongerThanContextEmb.__name__, C.ChatOpenAICompatible.__name__, 'finmem image ok')"
