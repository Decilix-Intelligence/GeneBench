# 人工窗口记录（ops/env_window.md）

需要人到场（sudo / 物理访问）的变更一律先登记待批，再在窗口里执行，执行后把取证抄回这里。
「无 sudo 假设」是常态；这份文件是那条假设的**例外账本**。

| 窗口 | 项 | 命令 / 变更 | 取证 | 关联票 |
| --- | --- | --- | --- | --- |
| 2026-09-03 | 删客户端 NFS 挂载 | f02 删 fstab 行 `192.168.1.48:/data`；f01 删 `192.168.1.219:/data` | 两台 fstab 已无该行 | N-30 |
| 2026-09-03 | 关服务端导出 | f01 `/etc/exports` 注释 + `exportfs -ra` | `exportfs -v` **无输出** | W1-b |
| 2026-09-03 | 放行网关端口 | `ufw allow from 192.168.1.219 to any port 18080 proto tcp` | Rule added | T-12 |
| 2026-09-03 | 清 systemd 残留 | 两台 `daemon-reload` + `reset-failed` | `systemctl list-units --failed` 为空 | D-06 第 12 例 |

**顺序纪律**：删旁路先客户端后服务端（反了会让挂载在窗口内自己长回来）。
**状态纪律**：删配置之后要问「由它生成的运行时对象走了没有」—— systemd 的 mount 单元就是不会自己走的那种。
