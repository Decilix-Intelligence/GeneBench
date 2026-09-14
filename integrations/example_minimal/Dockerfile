# example_minimal —— P2 接入的最小镜像。
#
# 构建上下文是 f02 上的 /data/genebench_runner/build/example_minimal/，
# 里面要有两个目录：example_minimal/（本目录）与 genebench_client/（垫片）。
#   在 f01：
#     scp -r integrations/example_minimal integrations/genebench_client \
#            ljn@192.168.1.219:/data/genebench_runner/build/example_minimal/
#   在 f02（只许从 f01 进）：
#     cd /data/genebench_runner/build/example_minimal
#     docker build -t gb-example-minimal:r1 -f example_minimal/Dockerfile .
#
# 三条硬约束都体现在下面：
#   ① 统一基座 gb-base:bookworm-r1（docker.io 被墙，不要 pull 新基础镜像）；
#   ② 依赖全部在**构建期**装完 —— 运行期断网，`pip install` 会当场撞死；
#   ③ 垫片走镜像不走 exec 树（exec 树同步的是 runner 的东西，不进任务容器）。
FROM gb-base:bookworm-r1

COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client

COPY example_minimal/run.py /opt/example_minimal/run.py

# 容器 HOME 不可写；把它指到可写层，**不要指到 /task 下**（那会破 P8 文件集封闭）。
ENV HOME=/tmp/h \
    XDG_CACHE_HOME=/tmp/h/.cache \
    PYTHONDONTWRITEBYTECODE=1
