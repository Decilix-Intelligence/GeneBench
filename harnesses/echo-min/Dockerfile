# 来源：本仓库 `harnesses/echo-min/`（卡 6.4 外部演练新建）。
#   镜像名 gb-echo-min-u:r1
#   digest sha256:32e2ed7d847c66d5244f313a372e7d4f52a5346776c6967ffbdf22ff7647b6fe
#   基座   gb-base:bookworm-r1（统一基座，N-62）
#
# 这是一个**不调模型**的最小 harness：它只验证 harnesses/README.md 的启动契约
# （四件文件、六个键、$$ 规则、环境变量表、产物落点），不验证任何 agent 能力。
FROM gb-base:bookworm-r1
COPY echo_driver.py /opt/echo-min/echo_driver.py
# 仓库文件是 0600（红线 5 要求 $GENEBENCH_ROOT 全树 go-rwx），COPY 保模式，
# 而任务容器以非 root 跑 —— 少了下面这行就是 Permission denied，
# 表现与「两臂 3 秒退出」一模一样（integrations/README.md §1②）。
RUN chmod -R a+rX /opt/echo-min && python3 -c "import ast,sys;ast.parse(open('/opt/echo-min/echo_driver.py').read());print('echo-min driver ok')"
