# QuantAgent（Aurora-73/QuantAgent，MIT）× GeneBench P2 接入。
#   镜像名 gb-quantagent-u:r1
#   digest sha256:<构建后回填>
#   基座   gb-base:bookworm-r1（统一基座，N-62）
#
# 构建上下文 = `/data/genebench_runner/build/quantagent/`，里面有三样：
#   quantagent/            本接入目录（本文件所在处）
#   genebench_client/      取数垫片
#   quantagent-4027f572.tar.gz + SUMS   上游源码 tarball（pin.json 里那个 sha256 在这里起作用）
FROM gb-base:bookworm-r1

# 基座是 python:3.12-slim 血统，**不带 setuptools** —— 少了这行，
# 下一行 --no-build-isolation 当场 BackendUnavailable，而报文一个字都不提你少装了什么。
RUN pip install --no-cache-dir "setuptools>=61" wheel

COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client

# 上游依赖里**只装这两个**。刻意不装 akshare / baostock / pytdx：
# 那三个是行情库，装上等于给上游留了三条绕过数据面的路（README §1③ 第一类
# 「运行期取数」靠不住）。不装它们，上游的 HAS_BAOSTOCK / HAS_PYTDX 就是 False，
# 兜底路径落到 akshare —— 而容器里的 `akshare` 是我们挂上去的网关门面。
RUN pip install --no-cache-dir "loguru>=0.7" "duckdb>=1.0" "pyyaml>=6.0" "pydantic>=2.0" "pydantic-settings>=2.0"

COPY quantagent-4027f572.tar.gz SUMS /tmp/src/
RUN cd /tmp/src && sha256sum -c SUMS \
 && mkdir -p /opt/quantagent/upstream \
 && tar xzf quantagent-4027f572.tar.gz -C /opt/quantagent/upstream --strip-components=1 \
 && rm -rf /tmp/src

COPY quantagent/glue/ /opt/quantagent/glue/
# 仓库文件是 0600（红线 5），COPY 保模式，而容器以非 root 跑 ——
# 少了这行就是 Permission denied，症状与「两臂 3 秒退出」一模一样。
RUN chmod -R a+rX /opt/quantagent /opt/genebench_client \
 && python3 -c "import sys;sys.path.insert(0,'/opt/quantagent/upstream');import data.provider as p;print('upstream ok, akshare=',p.HAS_AKSHARE,'baostock=',p.HAS_BAOSTOCK,'pytdx=',p.HAS_PYTDX)"
