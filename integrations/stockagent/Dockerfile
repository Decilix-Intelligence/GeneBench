# StockAgent（P2 接入）。构建上下文 = /data/genebench_runner/build/stockagent/，
# 里面有：stockagent/（本目录）、genebench_client/（垫片）、两个源码 tarball。
FROM gb-base:bookworm-r1

# ① 基座里没有 setuptools —— 少这一行，下面那条 `--no-build-isolation` 当场
#    `BackendUnavailable: Cannot import 'setuptools.build_meta'`（实测，build1.log）。
RUN pip install --no-cache-dir "setuptools>=61" wheel

# ② 取数垫片与产物助手（不走 exec 树，只走镜像）
COPY genebench_client/ /opt/genebench_client/
RUN pip install --no-cache-dir --no-index --no-build-isolation /opt/genebench_client

# ③ 接线层与本接入的依赖
COPY stockagent/ /opt/stockagent/
RUN pip install --no-cache-dir -r /opt/stockagent/requirements.gb.txt

# ④ 上游本体：两个源码 tarball（PyPI 上都没有；sha256 在 pin.json 里，构建期核）
COPY stockagent-src-e2a9c05.tar.gz promptcoder-8715542.tar.gz /tmp/src/
RUN cd /tmp/src \
 && echo "b041089917679424d2f071668e21058a895e5a01c973eec6c7f983dc2fd30f8a  stockagent-src-e2a9c05.tar.gz" > SUMS \
 && echo "09009210ee85e812717dfc76180f778e677f24ef4bf7f1f6dbd0b3ecc5909832  promptcoder-8715542.tar.gz" >> SUMS \
 && sha256sum -c SUMS \
 && mkdir -p /opt/stockagent/upstream \
 && tar xzf stockagent-src-e2a9c05.tar.gz --strip-components=1 -C /opt/stockagent/upstream \
 && tar xzf promptcoder-8715542.tar.gz \
 && cd dhh1995-PromptCoder-* \
 && pip install --no-cache-dir --no-deps . \
 && rm -rf /tmp/src

# ⑤ 仓库文件是 0600（$GENEBENCH_ROOT 全树受红线 5 守门），COPY 保模式，而容器以非 root 跑。
#    构建上下文里这些文件确实是 0600（f02 上 `ls -la` 实测），少这一行就是
#    `python3: can't open file '/opt/stockagent/run.py': [Errno 13] Permission denied`。
RUN chmod -R a+rX /opt/stockagent /opt/genebench_client

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

# ⑥ runnable_check 单独放一个文件（它要先 chdir，塞不进一行 `python3 -c`）。
RUN pip freeze > /opt/stockagent/resolved_deps.txt && python3 /opt/stockagent/runnable_check.py
