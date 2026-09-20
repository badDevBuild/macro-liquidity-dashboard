# 宏观流动性看板

一个移动端优先、可下钻核对的宏观流动性看板。它用官方或可信转发数据，把联储、财政、货币市场、利率、全球美元与加密内部资金管道放在同一套每日观察框架里。

源码采用 [MIT License](LICENSE)。仓库只包含程序、测试、公共配置和通用文档；运行数据库、新闻正文、Agent 上下文、分析产物、日志、生产服务器配置与个人投资记录都不会提交。

## 当前已经实现

- 16 个核心宏观指标，以及 6 个稳定币总量、分项和锚定健康指标；
- 原始响应、SQLite 历史、修订记录和每次来源运行记录；
- 允许缺 1–2 项但会明确披露的分组发布门禁；
- 总览、传导、账本、数据健康四个页面；
- 流动性参考值的 3 个月、1 年、5 年和完整周度走势，以及三个分项的周度贡献；
- 银行准备金、实际利率、美元和 NFCI 四条交叉检查线；
- 每个指标的 1 周、1 月、3 月、1 年变化、历史曲线、日期、来源和质量说明；
- 日频指标显示上一数据日与一周变化，周频指标显示上一周变化；
- Agent 晨间分析的数据契约、证据校验入口和失败降级界面；
- 当前 ChatGPT 订阅驱动的 Codex Agent 影子任务，固定使用 `gpt-5.6-sol` 和中等推理；
- Agent 运行锁、相同快照幂等跳过、8 分钟超时、快照绑定输出 Schema、两次分层恢复和完整审计产物；
- Agent 分析已显示在网页，14 日观察与人工语义复核继续记录稳定性；
- Agent 每天同时读取过去 24 小时的可信新闻和未来 90 天的官方事件日程；
- Polymarket 市场预期同时追踪当年美联储降息次数与加息次数，保留原始盘口合计、流动性、成交额和日/周/月变化；两组累计次数不互减成净政策路径；
- 每日稳定币通道：总供给、USDT、USDC、其他稳定币、1 日/7 日/30 日变化和主要美元稳定币锚定状态；
- 稳定币数据来自可信行业聚合源 DefiLlama，不进入宏观流动性参考值公式，也不把供给增加等同于买入加密资产；
- 每日加密衍生品通道：BTC、ETH、SOL 在 Binance、OKX、Bybit 的 USDT 永续未平仓、资金费率、价格变化和账户多空占比；
- 未平仓量提供同覆盖的官方 24 小时与 7 天变化；主动买入占比使用 Binance、OKX 的 24 小时公开成交方向，和账户多空比都不等同于资金方向；
- 跨资产相对强弱：BTC/标普 500、BTC/黄金代理以及美联储广义美元指数与 BTC 的同尺度走势；
- 跨资产图表支持 1 个月、3 个月、1 年、5 年和全部历史，只使用双方都有正式数据的共同日期，不填补周末和节假日；
- BTC/黄金使用 Coinbase PAXG-USD 作为黄金代理；美元图使用美联储广义美元指数，不冒充 ICE DXY；
- 日元套息模块分开显示“套息动力”和“平仓压力”，并追踪 USD/JPY、美日短端与 2 年期利差、汇率波动、CFTC 杠杆基金日元净空仓和东京外汇掉期成交；
- 日元套息图表可切换汇率与波动、美日利差、杠杆仓位、日元与 BTC/标普同步变化；它是独立风险因子，不进入宏观流动性参考值公式；
- 白话名称、准确术语和可展开的专业词解释；
- 手机底部导航、桌面侧边导航、PWA 安装和正式快照离线回退；
- 页面错误态、数据降级态、键盘焦点、减少动态效果和高对比模式；
- 北京时间每天 07:30 的数据、新闻、Agent 分析与生产发布任务；
- 公网 HTTPS 地址、原子版本切换、失败回滚和最近 7 版保留。

## 在线演示

维护者当前提供一个公开只读演示：<https://shushu.host/liquidity/>。这是个人托管实例，不是本项目运行所必需的服务。

演示服务器只展示已经校验的发布包。官方数据采集、新闻整理和 Codex Agent 分析留在采集主机上，不向网页服务器上传 Codex 登录信息、本机部署配置、原始抓取文件或运行日志。

## 安装与首次运行

需要 Python 3.11 或更高版本。项目核心代码没有第三方 Python 运行依赖。

```bash
git clone https://github.com/badDevBuild/macro-liquidity-dashboard.git
cd macro-liquidity-dashboard
python3 -m unittest discover -s tests -v
python3 scripts/run_data_channel.py --direct
python3 scripts/serve_dashboard.py --host 127.0.0.1 --port 8876
```

打开 `http://127.0.0.1:8876/`。首次采集会在本地创建 `data/`，该目录默认不进入 Git。

部分可选通道需要凭证：

- EIA 可使用公开的 `DEMO_KEY`，也可通过 `EIA_API_KEY` 提供自己的 Key；
- BTC、ETH、SOL ETF 数据需要 `SOSOVALUE_API_KEY`，macOS 也可使用配置中声明的 Keychain service；
- Agent 晨间分析调用已登录的 Codex CLI，不需要把 OpenAI API Key 写进项目。

可复制 [.env.example](.env.example) 查看变量名称。项目不会自动读取 `.env`；请通过系统环境、进程管理器或安全的密钥存储注入。

## 本地运行

```bash
python3 scripts/serve_dashboard.py --host 127.0.0.1 --port 8876
```

然后打开 `http://127.0.0.1:8876/`。服务只读地访问正式快照和 SQLite，不触发抓取，也不会修改指标历史。8876 是本项目的默认本地端口，避免占用既有的 8765 服务。

生产实例可用 cron、systemd timer 或 macOS LaunchAgent 在北京时间每天 07:30 执行 `scripts/run_shadow_cycle.py --notify`。顺序是核心宏观数据采集和质量检查、稳定币、ETF、衍生品、跨资产与日元套息数据、过去 24 小时新闻和未来 90 天事件、Codex Agent 分析、生产发布。可选市场通道或 Agent 失败时，仍可发布通过质量检查的核心数据；关键数据未通过或上传失败时，应继续保留上一份完整版本。

## 验证

```bash
python3 -m unittest discover -s tests -v
python3 scripts/run_data_channel.py --direct
python3 scripts/check_channel_health.py --days 14
python3 scripts/run_yen_carry_channel.py --direct
python3 scripts/run_agent_analysis.py --mode shadow
python3 scripts/check_agent_health.py --days 14
```

## 文档

- [看板运行与部署边界](docs/dashboard-operations.md)
- [数据通道与质量语义](docs/data-channel.md)
- [14 天影子运行](docs/shadow-operations.md)
- [产品语境](PRODUCT.md)
- [已确认的设计 brief](docs/dashboard-design-brief.md)
- [界面设计系统](DESIGN.md)
- [v2 趋势图与数据对齐设计](docs/dashboard-v2-trend-design.md)
- [Agent 晨间分析生产落地设计](docs/agent-analysis-design.md)
- [生产部署与每日更新](docs/production-deployment.md)
- [现场数据通道验证报告](reports/data-channel-validation/report.html)

页面只使用公开市场数据，因此默认没有登录；如果加入持仓、交易记录等私人数据，必须另加访问控制，不能直接放进现有公开接口。Agent 已接入每日流程，通过证据校验的结果才会显示在网页；稳定性继续通过 14 日观察和人工语义复核记录。
