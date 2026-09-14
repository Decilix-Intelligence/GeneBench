# integrations/rdagent_q —— RD-Agent(Q) 作为被测方（P2）的镜像。
#
# 镜像名 gb-rdagent_q-u:r1；digest 与构建命令见本目录 README.md「镜像」一节。
#
# 构建上下文是 f02 上的 /data/genebench_runner/build/rdagent_q/，里面两个目录：
#   rdagent_q/（本目录）与 genebench_client/（垫片）。
#   在 f01：
#     scp -r integrations/rdagent_q integrations/genebench_client \
#            ljn@192.168.1.219:/data/genebench_runner/build/rdagent_q/
#   在 f02（只许从 f01 进）：
#     cd /data/genebench_runner/build/rdagent_q
#     docker build -t gb-rdagent_q-u:r1 -f rdagent_q/Dockerfile .
FROM gb-base:bookworm-r1

# 被测系统本体。**从 PyPI 装**（构建期可出网；docker.io 被墙但 PyPI 实测 200），
# 版本与字节摘要钉在 pin.json，与 runner/c42/upstream_pins.py 的 rdagent_q 同源。
# 这一行**逐字**照抄 gb-rd-u:r1 的构建行（f02 上 /data/genebench_runner/build/rd/Dockerfile），
# 为的是命中同一层构建缓存 —— 装出来的字节是同一份，构建从二十分钟变成几秒。
# 改动这一行不是笔误问题：它会重新解析依赖，装出一份与既有探针镜像不同的树。
RUN pip install --no-cache-dir "rdagent==0.8.0" 2>&1 | tail -3 && python -c "import rdagent; print('rd ok')"

# 取数垫片。走镜像不走 exec 树；--no-index 是因为它不在任何 index 上，
# 而且运行期装包被禁（运行期断网）。
COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client

# 接线层与入口。**内核一个字没改** —— glue/ 里全是子类、配置与数据落盘。
COPY rdagent_q/run.py /opt/rdagent_q/run.py
COPY rdagent_q/glue/ /opt/rdagent_q/glue/
# 仓库里这些文件是 0600（红线 5 要求 $GENEBENCH_ROOT 全树 go-rwx），COPY 原样带进镜像。
# 容器不一定以 root 跑（走查里就用 --user $(id -u)），那时 0600 的入口**读不了** ——
# 现场表现是 `python3: can't open file ... Permission denied`（实测撞过一次）。
RUN chmod -R a+rX /opt/rdagent_q

# 容器 HOME 不可写；指到可写层，**不要指到 /task 下**（那会破 P8 文件集封闭）。
ENV HOME=/tmp/h \
    XDG_CACHE_HOME=/tmp/h/.cache \
    PYTHONDONTWRITEBYTECODE=1 \
    LITELLM_LOCAL_MODEL_COST_MAP=True

RUN python3 -c "import rdagent, genebench_client, genebench_client.emit; print('rdagent_q image ok')"
