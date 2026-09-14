# -*- coding: utf-8 -*-
"""网关启动入口。

    cd $REPO && ulimit -n 8192 && $GENEBENCH_ROOT/env/bin/python -m gateway.run

两条**启动即拒绝**的守门，都不是只写在 docstring 里：

1. **绑定地址不可配** —— 写死走 `cfg.assert_no_wildcard_bind(cfg.GATEWAY_HOST)`。
   让"绕过"比"遵守"更费事，是红线 4 唯一靠得住的形态。
2. **`--workers > 1` 直接拒绝启动** —— `access_log` 用的是**进程内**锁
   （`threading.Lock`）。多 worker 下每个进程各持一把锁，同时往同一个
   `gateway_access.jsonl` 追加，**会交错写坏行**。而卡 5.1 的前视探针要靠这份
   日志做事后结算：损坏的形态是"某几行 JSON 解析不了"，
   最坏情况是**越权记录恰好落在坏行里**，探针读不到就等于没发生过。
   所以这不是性能取舍，是取证完整性 —— 宁可不启动。

   要上多 worker，先把日志换成每 worker 一个文件或走 syslog，
   再把这个守门改掉，并同步改 `ops/test_m1_followups.py` 里盯着它的测试。
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import genebench_config as cfg


def assert_single_worker(workers: "int | None") -> int:
    """`workers` 只能是 1（或不给）。

    Raises:
        RuntimeError: 请求了多 worker。
    """
    n = 1 if workers is None else int(workers)
    if n != 1:
        raise RuntimeError(
            f"拒绝以 workers={n} 启动。access_log 用进程内 threading.Lock，"
            f"多 worker 会并发追加同一个 {cfg.LOGS / 'gateway_access.jsonl'}，"
            f"交错写坏行；卡 5.1 的前视探针要靠这份日志结算，"
            f"坏行 = 越权记录可能读不到 = 等于没发生过。"
            f"要上多 worker，先改日志方案（每 worker 一个文件 / syslog）。"
        )
    return n


def main(argv: "list[str] | None" = None) -> int:
    import uvicorn

    parser = argparse.ArgumentParser(description="GeneBench as-of 数据网关")
    parser.add_argument(
        "--workers", type=int, default=1,
        help="只接受 1。>1 会被拒绝，理由见模块 docstring。",
    )
    args = parser.parse_args(argv)

    try:
        workers = assert_single_worker(args.workers)
    except RuntimeError as exc:
        print(f"启动被拒绝：{exc}", file=sys.stderr)
        return 2

    cfg.harden_umask()
    cfg.create_dir(cfg.LOGS)

    # **启动守门**（指令一，2026-09-04）：敏感根的权限在**使用时刻**再核一次。
    # 推送时刻绿不代表使用时刻绿 —— 中间任何人 chmod 一下都不会有人知道，
    # 而网关正要往日志里写取证数据、并从 reference/ 之外的地方读快照。
    import importlib.util
    _spec = importlib.util.spec_from_file_location(
        "_guard", pathlib.Path(__file__).resolve().parents[1] / "ops" / "guard_modes.py")
    if _spec and _spec.loader:
        _g = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_g)
        _g.assert_modes(who="网关")
    host = cfg.assert_no_wildcard_bind(cfg.GATEWAY_HOST)
    # 端口按通道取（卡 1.1-a）：private 无环境变量时仍是 18080，与既有一致；
    # public 无环境变量时是 **18081** —— 「忘了设端口」的失败形态必须是
    # 「起在 18081」，不能是「抢生产网关的 18080」。绑定地址规则一个字没改。
    port = cfg.gateway_port()
    print(f"[网关] channel={cfg.channel()} bind={host}:{port} "
          f"tables={cfg.snapshot_tables_dir()}", flush=True)
    uvicorn.run(
        "gateway.app:app",
        host=host,
        port=port,
        workers=workers,
        log_level="warning",
        access_log=False,   # 我们自己写结构化 access_log，不要 uvicorn 那份
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
