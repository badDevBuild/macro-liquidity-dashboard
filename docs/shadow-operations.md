# 14 天影子运行

## 每日调度

生产采集主机可以使用 LaunchAgent、systemd timer 或 cron，在北京时间每天 07:30 执行 `scripts/run_shadow_cycle.py --notify`。调度文件通常包含本机绝对路径，因此不进入公共仓库。

影子周期依次完成：

1. 检查磁盘剩余空间；
2. 执行官方来源抓取和发布门禁；
3. 生成数据通道的 14 天健康检查；
4. 收集稳定币总供给、USDT/USDC/其他分项和锚定健康；该通道失败时回退到 3 天内的有效缓存，再超时则标为不可用，但不阻断核心宏观数据；
5. 收集 ETF、加密衍生品、跨资产与日元套息数据；这些都是可选通道，失败时明确降级但不阻断核心宏观发布；
6. 收集过去 24 小时新闻和未来 90 天事件；
7. 数据允许分析时，用当前 Codex 订阅运行一次 Sol 中等推理的影子分析；
8. 生成 Agent 的 14 天健康检查；
9. 写入 `data/status/latest-shadow-cycle.json`；
10. 仅在数据分析被阻止、运行失败、Agent 分析失败或磁盘低于硬门槛时发送本机通知。

Agent 分析失败不会改变数据周期的成功状态。相同快照已经成功分析过时，Agent 任务会幂等跳过，不会重复消耗订阅用量。

## 状态文件

- `data/status/latest-run.json`：最近一次数据通道尝试；
- `data/status/latest-shadow-cycle.json`：最近一次完整影子周期；
- `data/status/health-14d.json`：14 天硬门禁进度；
- `data/status/latest-agent-run.json`：最近一次 Agent 尝试或幂等跳过状态；
- `data/status/agent-health-14d.json`：Agent 的 14 个有效观察日和人工批准进度；
- `data/snapshots/latest.json`：最近一次通过发布门禁的正式快照。
- `data/context/latest.json`：最近一份 24 小时新闻和 90 天事件包；
- `data/stablecoins/latest.json`：最近一份稳定币数据；`fresh_network` 表示当日抓取，`fresh_cache` 表示使用 3 天内缓存，`unavailable` 不等于 0；
- `data/yen-carry/latest.json`：最近一次日元套息状态和可用性；`history.json` 保存原始与派生历史；
- `data/analysis/shadow/latest.json`：最近一次通过证据校验的分析，网页可直接显示；
- `data/analysis/latest.json`：生产分析；Agent 门禁通过前应不存在。

## 磁盘策略

当前只启用监测，不自动删除任何原始证据。剩余空间低于 20 GiB 时记录警告，低于 5 GiB 时阻止抓取并发送通知。原始响应保留和归档期限需要在观察真实增长率后单独确认，不能未经授权自动删除。

## 手动验证

```bash
python3 scripts/run_shadow_cycle.py              # 数据成功后自动运行 Agent 影子分析
python3 scripts/run_shadow_cycle.py --skip-agent # 仅验证确定性数据通道
python3 scripts/check_channel_health.py --days 14
python3 scripts/run_context_channel.py
python3 scripts/run_agent_analysis.py --mode shadow
python3 scripts/check_agent_health.py --days 14
```

`scripts/run_agent_analysis.py --mode publish` 不是日常试跑命令。它会先读取 `data/status/agent-health-14d.json`，只有其中 `hard_pass=true` 才允许写生产分析。
