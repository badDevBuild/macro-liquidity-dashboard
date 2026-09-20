# Coinbase / Binance BTC 现货溢价

入口：传导 → 加密管道 → Coinbase 溢价。每日北京时间07:30，既有 run_shadow_cycle.py 在 Agent 之前执行 run_coinbase_premium.py。

使用公开的 Coinbase BTC-USD、Coinbase USDT-USD 和 Binance BTCUSDT 现货小时K线。第一轮回补366天，此后重取最近48小时并按UTC小时更新缓存。每个成功分页即保存检查点；失败可重试。每个原始响应保存URL、获取时间和SHA-256。公开包仅携带 latest.json 和 history.json。

- raw_bp = (Coinbase BTC/USD ÷ Binance BTC/USDT − 1) × 10000。
- adjusted_bp = (Coinbase BTC/USD ÷ (Binance BTC/USDT × Coinbase USDT/USD) − 1) × 10000。
- observed_at 是UTC小时结束时间，只保留已收盘、有交易量的K线；同一小时最后成交价不保证同一秒成交，不能视为可成交套利报价。
- 24小时均值和正溢价占比需要完整24小时，否则为null。连续同向时长在零值、反向或缺口处停止；left_censored表示被历史边界或缺口截断，显示“至少”。
- 24小时/7天/30天展示小时收盘；90天/1年展示完整UTC自然日的24个小时均值。对每小时溢价取算术均值，不用日均价格重算溢价。缺口断线，不补零、不前向填充。
- 观察时间超过30小时即失效，包括网站读取时复核，失效指标不可用于Agent引用；原始口径与美元折算口径分别判断可用性。
- 独立可选通道，采集失败不阻断其他数据、分析和发布。两个口径的历史都可查看，调整口径不能用原始口径冒充。

Agent收到最新值、24小时统计、连续时长和最近48小时价格/价差。指标通过既有数字/日期/比较窗口校验；解释不得认定美国机构买入、资金净流入或无风险套利。

运行：`python3 scripts/run_coinbase_premium.py`。验证：`python3 -m unittest discover -s tests -p 'test_coinbase_premium.py' -v`。
