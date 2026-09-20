from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .agent_analysis import load_agent_analysis
from .context_channel import load_context_bundle
from .cross_asset_channel import load_cross_asset_history, load_cross_asset_payload
from .energy_channel import load_energy_history, load_energy_payload
from .crypto_derivatives_channel import load_crypto_derivatives_payload
from .crypto_etf_channel import load_crypto_etf_payload
from .market_expectations import load_market_expectations
from .public_status import public_cycle_status
from .stablecoin_channel import load_stablecoin_payload
from .yen_carry_channel import load_yen_carry_history, load_yen_carry_payload
from .coinbase_premium import DEFINITIONS as PREMIUM_METRICS, load_payload as load_premium, build_history as premium_history


UTC = timezone.utc

GROUPS: dict[str, dict[str, Any]] = {
    "fed_balance_sheet": {
        "label": "美联储的账本",
        "short_label": "联储",
        "description": "看美联储是在放水，还是在收水",
        "flow_note": "美联储买入资产时，银行体系里的准备金通常会增加；资产到期或卖出时，准备金或 RRP 缓冲通常会减少。",
        "order": 1,
    },
    "fiscal_cash": {
        "label": "财政部的钱",
        "short_label": "财政",
        "description": "看政府是在收钱，还是把钱花回市场",
        "flow_note": "财政部发债或收税时，钱通常进入 TGA；政府花钱时，钱又回到银行和企业、个人的账户。",
        "order": 2,
    },
    "money_market": {
        "label": "短期借钱市场",
        "short_label": "货币市场",
        "description": "看借一晚美元贵不贵、顺不顺",
        "flow_note": "准备金、RRP 和回购市场共同影响短期现金够不够用。钱紧时，短期借款利率更容易突然上升。",
        "order": 3,
    },
    "market_transmission": {
        "label": "传到股票和加密",
        "short_label": "传导",
        "description": "看利率、美元和融资环境怎样改变市场",
        "flow_note": "利率和美元先改变安全资产的回报、借钱成本和投资者的风险意愿，之后才可能影响股票和加密价格。",
        "order": 4,
    },
}

METRICS: dict[str, dict[str, Any]] = {
    "fed_total_assets": {
        "label": "美联储总资产",
        "short_label": "联储总资产",
        "description": "美联储手里持有的国债、MBS 等资产一共值多少。",
        "direction_note": "它上升时，美联储通常在给金融系统更多基础资金；它下降时，通常在收回。还要和 TGA、RRP 一起看。",
        "order": 1,
    },
    "reserve_balances_weekly_average": {
        "label": "银行准备金（周均）",
        "short_label": "银行准备金",
        "description": "银行放在美联储、专门用来和其他银行结账的钱。",
        "direction_note": "准备金多，银行间付款通常更顺；但这些钱不会自动跑去买股票或加密。",
        "order": 2,
    },
    "tga_daily": {
        "label": "财政部现金（TGA，每日）",
        "short_label": "财政部现金",
        "description": "美国财政部放在美联储账户里的现金。这里看每日收盘余额。",
        "direction_note": "它上升，通常表示钱先从银行体系进入政府账户；它下降，通常表示政府正在把钱花回去。",
        "order": 1,
    },
    "tga_weekly": {
        "label": "财政部现金（TGA，周平均）",
        "short_label": "财政部现金周平均",
        "description": "同一账户的一周平均余额，不是周末余额，也不是一周变化金额。",
        "direction_note": "仅作独立参考，不参与流动性参考值及其历史走势计算。",
        "order": 2,
    },
    "overnight_rrp": {
        "label": "隔夜现金停车场（RRP）",
        "short_label": "RRP 现金",
        "description": "货币基金等机构把暂时不用的现金，在美联储安全停一晚的地方。",
        "direction_note": "它下降，说明这部分现金离开了停车场，但未必去买风险资产，也可能去买短期国债。",
        "order": 1,
    },
    "sofr": {
        "label": "SOFR",
        "short_label": "SOFR",
        "description": "拿美国国债作抵押，借一晚美元时常用的基准利率。",
        "direction_note": "它突然明显上升时，常表示市场里的短期现金正在变紧。",
        "order": 2,
    },
    "iorb": {
        "label": "银行准备金利息（IORB）",
        "short_label": "准备金利息",
        "description": "银行把准备金放在美联储，可以拿到的利息。",
        "direction_note": "它上升后，银行把钱安全放在美联储更划算，市场上其他短期利率通常也会跟着提高。",
        "order": 3,
    },
    "on_rrp_award_rate": {
        "label": "RRP 隔夜利率",
        "short_label": "RRP 利率",
        "description": "货币基金等机构把现金隔夜停在美联储时，可以拿到的利率。",
        "direction_note": "它是非银行机构的安全停泊价，也是短端利率走廊的一层地板。",
        "order": 4,
    },
    "effective_fed_funds_rate": {
        "label": "有效联邦基金利率",
        "short_label": "联邦基金利率",
        "description": "银行之间不押抵押品、互借一晚资金的实际平均利率。",
        "direction_note": "它告诉我们，美联储设定的利率目标，实际有没有传到银行间市场。",
        "order": 5,
    },
    "treasury_3m_yield": {
        "label": "3 个月期美债收益率",
        "short_label": "3M 美债",
        "description": "把钱借给美国政府 3 个月，市场要求的年化回报。",
        "direction_note": "它贴近当前政策利率和近期现金供求，是收益率曲线的最短端。",
        "order": 1,
    },
    "treasury_2y_yield": {
        "label": "2 年期美债收益率",
        "short_label": "2Y 美债",
        "description": "把钱借给美国政府 2 年，市场要求的年化回报。",
        "direction_note": "它对未来几次美联储利率路径很敏感，常比长债更快反应政策预期。",
        "order": 2,
    },
    "treasury_10y_yield": {
        "label": "10 年期美债收益率",
        "short_label": "10 年美债利率",
        "description": "把钱借给美国政府 10 年，市场要求的年化回报。",
        "direction_note": "它上升时，安全资产更有吸引力，企业借钱更贵，股票估值通常更难扩张。",
        "order": 3,
    },
    "treasury_30y_yield": {
        "label": "30 年期美债收益率",
        "short_label": "30Y 美债",
        "description": "把钱借给美国政府 30 年，市场要求的年化回报。",
        "direction_note": "它更受长期通胀、财政供给和期限风险补偿影响。",
        "order": 4,
    },
    "treasury_10y_real_yield": {
        "label": "10 年期实际利率",
        "short_label": "10 年实际利率",
        "description": "10 年美债收益率扣掉市场预期的通胀后，还剩下的真实回报。",
        "direction_note": "它上升时，持有安全资产更划算，对成长股和没有现金流的加密资产通常更不友好。",
        "order": 5,
    },
    "broad_dollar_index": {
        "label": "广义美元指数",
        "short_label": "广义美元",
        "description": "把美元和一篮子贸易伙伴货币相比，看美元整体是强还是弱。",
        "direction_note": "它上升时，全球借美元、还美元债通常更吃力。但它只反映美元价格，不等于美元数量。",
        "order": 6,
    },
    "nfci": {
        "label": "金融松紧温度计（NFCI）",
        "short_label": "NFCI",
        "description": "芝加哥联储把利率、信用和杠杆等数据合成的一只温度计。",
        "direction_note": "数值越高，通常越紧；低于零，通常表示环境比长期平均更宽松。",
        "order": 7,
    },
    "energy_wti_spot": {
        "label": "WTI 原油现货价",
        "short_label": "WTI 原油",
        "description": "美国西得州中质原油在库欣的现货价格。",
        "direction_note": "油价持续上涨会推高通胀和企业成本，可能让降息更难；下跌也可能是需求转弱。",
        "order": 1,
    },
    "energy_brent_spot": {
        "label": "Brent 原油现货价",
        "short_label": "Brent 原油",
        "description": "国际原油市场常用的 Brent 现货基准价格。",
        "direction_note": "它更容易反映全球供需和地缘供给风险。",
        "order": 2,
    },
    "energy_brent_wti_spread": {
        "label": "Brent 减 WTI 价差",
        "short_label": "Brent-WTI",
        "description": "Brent 现货价减去 WTI 库欣现货价。",
        "direction_note": "价差扩大常表示国际供给风险、运输瓶颈或美国本地库存条件与全球不同步。",
        "order": 3,
    },
    "energy_commercial_crude_stocks": {
        "label": "美国商业原油库存",
        "short_label": "商业原油库存",
        "description": "美国商业体系持有的原油库存，不包括战略石油储备。",
        "direction_note": "库存下降可能是供应变紧或需求较强；需要和价格、库欣库存和需求数据一起看。",
        "order": 4,
    },
    "energy_cushing_crude_stocks": {
        "label": "库欣原油库存",
        "short_label": "库欣库存",
        "description": "WTI 实物交割中心库欣地区的原油库存。",
        "direction_note": "持续下降会让 WTI 实物供应更紧，极低时价格和价差可能更敏感。",
        "order": 5,
    },
    "energy_spr_stocks": {
        "label": "美国战略石油储备",
        "short_label": "SPR",
        "description": "美国政府持有、用于能源安全的战略原油储备。",
        "direction_note": "政府释放 SPR 能在短期增加供应；回补则会增加政府买盘。",
        "order": 6,
    },
    "energy_gasoline_product_supplied": {
        "label": "美国成品汽油隐含需求",
        "short_label": "汽油需求",
        "description": "EIA 的成品汽油 product supplied，常作为美国汽油需求的高频代理。",
        "direction_note": "需求增强与库存下降同时出现时，供需趋紧的证据更强。",
        "order": 7,
    },
    "stablecoin_usd_supply": {
        "label": "美元稳定币总供给",
        "short_label": "稳定币总供给",
        "description": "所有美元锚定稳定币按面值计算的流通总量。",
        "direction_note": "它增加，表示加密市场里的链上美元容量变多；不代表这些钱已经买入 BTC 或其他资产。",
        "order": 1,
    },
    "stablecoin_usdt_supply": {
        "label": "USDT 流通量",
        "short_label": "USDT",
        "description": "USDT 按面值计算的流通量。",
        "direction_note": "用来判断稳定币供给变化主要是不是由 USDT 带动。",
        "order": 2,
    },
    "stablecoin_usdc_supply": {
        "label": "USDC 流通量",
        "short_label": "USDC",
        "description": "USDC 按面值计算的流通量。",
        "direction_note": "用来判断稳定币供给变化主要是不是由 USDC 带动。",
        "order": 3,
    },
    "stablecoin_other_supply": {
        "label": "其他美元稳定币流通量",
        "short_label": "其他稳定币",
        "description": "除 USDT 和 USDC 外，其他美元锚定稳定币按面值计算的流通量。",
        "direction_note": "它能看出供给扩张是否只集中在两个最大稳定币。",
        "order": 4,
    },
    "stablecoin_usdt_usdc_share": {
        "label": "USDT 与 USDC 供给占比",
        "short_label": "两大稳定币占比",
        "description": "USDT 和 USDC 流通量，占同一币种列表中美元稳定币总量的比例。",
        "direction_note": "占比越高，稳定币流动性越集中在两个最主要发行方。",
        "order": 5,
    },
    "stablecoin_core_max_depeg_bps": {
        "label": "主要稳定币最大偏离",
        "short_label": "最大脱锚偏离",
        "description": "按供给排序且有有效价格的主要美元稳定币中，价格偏离 1 美元最多的一项。",
        "direction_note": "偏离持续扩大时，稳定币本身可能正在制造风险；不能因为名义供给增加就判断流动性改善。",
        "order": 6,
    },
    "cross_asset_btc_spx_ratio": {
        "label": "BTC / 标普 500 相对强弱",
        "short_label": "BTC / 美股",
        "description": "1 枚 BTC 的美元价格除以标普 500 指数点位，用来看 BTC 相对美股走得更强还是更弱。",
        "direction_note": "比值上升只表示 BTC 跑赢标普 500，不代表资金正在从股票流入 BTC。",
        "order": 1,
    },
    "cross_asset_btc_gold_ratio": {
        "label": "BTC / 黄金相对强弱",
        "short_label": "BTC / 黄金",
        "description": "1 枚 BTC 相当于多少盎司 PAXG 所代表的黄金。",
        "direction_note": "比值上升表示 BTC 相对黄金更强。PAXG 是黄金代币代理，不是伦敦现货金定盘价。",
        "order": 2,
    },
    "cross_asset_btc_broad_dollar_corr_30d": {
        "label": "BTC 与广义美元 30 日相关性",
        "short_label": "30 日相关",
        "description": "在双方都有数据的最近 30 个观察日，比较 BTC 和广义美元的日收益率是否同向。",
        "direction_note": "越接近 -1 表示近期越常反向；越接近 +1 表示越常同向。相关不等于因果。",
        "order": 3,
    },
    "cross_asset_btc_broad_dollar_corr_90d": {
        "label": "BTC 与广义美元 90 日相关性",
        "short_label": "90 日相关",
        "description": "在双方都有数据的最近 90 个观察日，比较 BTC 和广义美元的日收益率是否同向。",
        "direction_note": "90 日窗口比 30 日更稳，但仍只描述同步程度，不能证明美元造成 BTC 涨跌。",
        "order": 4,
    },
    "yen_carry_usd_jpy": {
        "label": "美元兑日元",
        "short_label": "USD/JPY",
        "description": "1 美元可以兑换多少日元。数值下降表示日元升值。",
        "direction_note": "日元快速升值会抬高借日元、买其他资产这类交易的平仓压力，但不能单靠汇率证明平仓已经发生。",
        "order": 1,
    },
    "yen_carry_jpy_appreciation_5d": {
        "label": "日元近 5 个交易日升值幅度",
        "short_label": "日元 5 日升值",
        "description": "把美元兑日元的变化反向表达；正数表示日元升值。",
        "direction_note": "升值越快，日元融资者偿还日元时的压力通常越大。",
        "order": 2,
    },
    "yen_carry_short_rate_spread": {
        "label": "美日短端利差",
        "short_label": "短端利差",
        "description": "美国 3 个月国债收益率减去日本无担保隔夜拆借利率。",
        "direction_note": "利差越宽，未对冲的日元融资动力通常越强；利差快速收窄会削弱这项动力。",
        "order": 3,
    },
    "yen_carry_2y_rate_spread": {
        "label": "美日 2 年期利差",
        "short_label": "2 年期利差",
        "description": "美国 2 年期国债收益率减去一只剩余期限约两年的日本国债收益率。",
        "direction_note": "它帮助观察未来一段时间的政策利率差，但日本端是可复算的债券代理，不是恒定期限指数。",
        "order": 4,
    },
    "yen_carry_realized_volatility_20d": {
        "label": "美元兑日元 20 日波动率",
        "short_label": "汇率波动",
        "description": "根据最近 20 个交易日汇率变化计算的年化波动率。",
        "direction_note": "波动突然变大时，汇率风险可能盖过利差收益，套息交易更容易减仓。",
        "order": 5,
    },
    "yen_carry_cftc_leveraged_net_short": {
        "label": "杠杆基金日元净空仓",
        "short_label": "日元净空仓",
        "description": "CFTC 期货报告中，杠杆基金的日元空头合约数减去多头合约数。",
        "direction_note": "净空仓快速减少可作为回补日元空头的证据之一；它只覆盖报告期货，不是全球套息交易总规模。",
        "order": 6,
    },
    "yen_carry_fx_swap_turnover": {
        "label": "东京美元兑日元掉期成交额",
        "short_label": "外汇掉期成交",
        "description": "日本银行统计的东京市场美元兑日元掉期成交额。",
        "direction_note": "成交额放大说明融资和对冲活动更活跃，但这个数字本身不告诉我们交易方向。",
        "order": 7,
    },
    "yen_carry_carry_to_risk": {
        "label": "套息收益风险比",
        "short_label": "套息收益风险比",
        "description": "美日短端利差除以美元兑日元 20 日年化波动率。",
        "direction_note": "数值越高，利差相对汇率波动越有吸引力；它只是比较尺，不是预期收益。",
        "order": 8,
    },
}

CRYPTO_ASSET_LABELS = {"btc": "BTC", "eth": "ETH", "sol": "SOL"}
for _asset_id, _asset_label in CRYPTO_ASSET_LABELS.items():
    METRICS.update(
        {
            f"etf_{_asset_id}_net_flow_latest": {
                "label": f"{_asset_label} 美国现货 ETF 单日净流入",
                "short_label": f"{_asset_label} ETF 净流入",
                "description": "最近一个已经结算的美股交易日，所有美国现货 ETF 合计流入或流出的金额。",
                "direction_note": "正数表示这条受监管现货通道当日净买入，负数表示净赎回；当天尚未结算时不会当成零。",
                "order": 1,
            },
            f"etf_{_asset_id}_net_flow_5d": {
                "label": f"{_asset_label} 美国现货 ETF 近 5 个交易日净流入",
                "short_label": f"{_asset_label} ETF 5 日",
                "description": "最近 5 个已经结算的美股交易日净流入合计。",
                "direction_note": "用来过滤单日噪声，看 ETF 买盘或赎回是否持续。",
                "order": 2,
            },
            f"etf_{_asset_id}_net_flow_20d": {
                "label": f"{_asset_label} 美国现货 ETF 近 20 个交易日净流入",
                "short_label": f"{_asset_label} ETF 20 日",
                "description": "最近 20 个已经结算的美股交易日净流入合计。",
                "direction_note": "接近一个交易月，适合判断 ETF 资金方向是不是已经形成趋势。",
                "order": 3,
            },
            f"etf_{_asset_id}_aum": {
                "label": f"{_asset_label} 美国现货 ETF 总资产",
                "short_label": f"{_asset_label} ETF 资产",
                "description": "美国现货 ETF 管理的资产总额，会同时受资金申赎和币价变化影响。",
                "direction_note": "它不是纯资金流，所以不能单独用来判断当天买盘。",
                "order": 4,
            },
            f"etf_{_asset_id}_value_traded": {
                "label": f"{_asset_label} 美国现货 ETF 成交额",
                "short_label": f"{_asset_label} ETF 成交",
                "description": "最近一个已结算交易日的 ETF 成交金额。",
                "direction_note": "成交放大说明关注度上升，但买卖双方同时存在，不代表方向。",
                "order": 5,
            },
            f"derivatives_{_asset_id}_open_interest": {
                "label": f"{_asset_label} 永续合约未平仓金额",
                "short_label": f"{_asset_label} 未平仓",
                "description": "Binance、OKX、Bybit 的 USDT 永续合约名义未平仓金额合计。",
                "direction_note": "它上升表示杠杆仓位变多，但没有多空方向，必须和价格、资金费率一起看。",
                "order": 1,
            },
            f"derivatives_{_asset_id}_funding_annualized": {
                "label": f"{_asset_label} 永续合约加权年化资金费率",
                "short_label": f"{_asset_label} 年化等价费率",
                "description": "三家交易所资金费率按各自结算周期年化，再按未平仓金额加权。",
                "direction_note": "只用来比较费率高低，不是已经发生的全年持仓成本。",
                "order": 3,
            },
            f"derivatives_{_asset_id}_funding_8h_equivalent": {
                "label": f"{_asset_label} 永续合约 8 小时等价资金费率",
                "short_label": f"{_asset_label} 8h 资金费率",
                "description": "把三家交易所当前资金费率统一折算成 8 小时周期，再按未平仓金额加权。",
                "direction_note": "持续明显为正，通常说明多头更拥挤；持续明显为负，通常说明空头更拥挤。",
                "order": 2,
            },
            f"derivatives_{_asset_id}_price_change_24h": {
                "label": f"{_asset_label} 永续合约 24 小时价格变化",
                "short_label": f"{_asset_label} 24h 价格",
                "description": "三家交易所永续合约 24 小时价格变化的中位数。",
                "direction_note": "和未平仓量、资金费率组合使用，判断新增杠杆更像追涨、追空还是去杠杆。",
                "order": 3,
            },
            f"derivatives_{_asset_id}_account_long_share": {
                "label": f"{_asset_label} 永续合约多头账户占比",
                "short_label": f"{_asset_label} 多头账户",
                "description": "Binance、OKX、Bybit 多头账户占比的中位数，统计账户数量，不是持仓金额。",
                "direction_note": "明显偏离 50% 表示账户立场更拥挤，但不能据此判断资金规模或价格方向。",
                "order": 4,
            },
            f"derivatives_{_asset_id}_taker_buy_share_24h": {
                "label": f"{_asset_label} 永续合约 24 小时主动买入占比",
                "short_label": f"{_asset_label} 主动买入",
                "description": "Binance、OKX 过去 24 小时主动买入成交占比的中位数。",
                "direction_note": "高于 50% 表示近期吃单买盘更多，但它是成交方向，不是未平仓方向。",
                "order": 5,
            },
        }
    )

METRICS.update(PREMIUM_METRICS)
RANGE_DAYS = {"1m": 31, "3m": 93, "1y": 366, "5y": 1827}
ETF_SESSION_RANGES = {"5d": 5, "20d": 20}
CHANGE_WINDOWS = {"1w": 7, "1m": 31, "3m": 93, "1y": 366}

GLOSSARY = [
    {
        "term": "流动性参考值",
        "technical_term": "净流动性代理值",
        "plain": "把美联储总资产减去财政部现金和 RRP，观察金融体系里的水大致在增加还是减少。它是方向尺，不是可直接买股票的钱。",
    },
    {
        "term": "财政部现金",
        "technical_term": "TGA",
        "plain": "美国财政部放在美联储的账户。余额上升，钱通常先离开银行体系；余额下降，政府通常正在把钱花回去。",
    },
    {
        "term": "隔夜现金停车场",
        "technical_term": "RRP",
        "plain": "货币基金等机构把短期现金停在美联储一晚的地方。余额下降不等于这些钱一定进入股票或加密。",
    },
    {
        "term": "银行准备金",
        "technical_term": "Reserve balances",
        "plain": "银行放在美联储、用来和其他银行结账的钱。它多时，银行间付款通常更顺。",
    },
    {
        "term": "实际利率",
        "technical_term": "Real yield",
        "plain": "债券收益率扣掉市场预期的通胀。它越高，安全资产越有吸引力，风险资产通常越有压力。",
    },
    {
        "term": "金融松紧温度计",
        "technical_term": "NFCI",
        "plain": "把利率、信用和杠杆揉成一个数。数值越高通常越紧，越低通常越松。",
    },
    {
        "term": "短端利差",
        "technical_term": "SOFR−IORB / SOFR−EFFR",
        "plain": "比较市场真实借一晚美元的价格，和银行安全停钱能拿到的价格。持续转正、继续扩大，才更像资金压力；一天的小波动不能单独下结论。",
    },
    {
        "term": "收益率曲线倒挂",
        "technical_term": "Yield curve inversion",
        "plain": "短期美债利率高于长期美债利率。看板用 10Y−2Y 和 10Y−3M 的差值判断；差值小于零就是倒挂。",
    },
    {
        "term": "市场隐含概率",
        "technical_term": "Prediction-market implied probability",
        "plain": "交易者用真钱押注后形成的概率。它能说明市场在押什么，但不是事实，也不保证结果会发生。",
    },
    {
        "term": "稳定币供给",
        "technical_term": "Stablecoin supply",
        "plain": "加密网络里按 1 美元面值流通的稳定币总量。它增加，表示链上美元容量变多，但不等于这些钱已经买入加密资产。",
    },
    {
        "term": "日元套息交易",
        "technical_term": "Yen carry trade",
        "plain": "用成本较低的日元融资，再持有收益更高的资产。利差越宽通常越有吸引力；日元突然升值或汇率波动放大时，交易者更可能被迫减仓。",
    },
]


def _load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else (default or {})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default or {}


def _connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise FileNotFoundError(f"dashboard history database is missing: {path}")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def _iso_now(now: datetime | None = None) -> str:
    current = now or datetime.now(tz=UTC)
    return current.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _runtime_freshness(
    metric: dict[str, Any],
    source: dict[str, Any] | None,
    *,
    now: datetime | None,
) -> dict[str, Any]:
    """Re-evaluate freshness at read time without erasing publication facts."""
    result = dict(metric)
    result["publication_quality_status"] = metric.get("quality_status")
    result["publication_available_for_analysis"] = (
        metric.get("available_for_analysis") is True
    )
    observed_at = metric.get("observed_at")
    max_days = (source or {}).get("freshness_max_days")
    if not observed_at or not isinstance(max_days, (int, float)):
        result["runtime_freshness_status"] = "not_recalculated"
        return result
    current = (now or datetime.now(tz=UTC)).astimezone(UTC).date()
    try:
        observed = _parse_date(str(observed_at))
    except ValueError:
        result["runtime_freshness_status"] = "invalid_observation_date"
        result["available_for_analysis"] = False
        result["quality_status"] = "unavailable"
        return result
    age_days = max(0, (current - observed).days)
    result["age_days"] = age_days
    result["runtime_freshness_max_days"] = int(max_days)
    if age_days > int(max_days):
        result["runtime_freshness_status"] = "stale"
        result["quality_status"] = "stale_runtime"
        result["available_for_analysis"] = False
    else:
        result["runtime_freshness_status"] = "current"
    return result


def _cadence_freshness_days(cadence: Any) -> int | None:
    value = str(cadence or "").lower()
    if not value:
        return None
    if "continuous" in value:
        return 1
    if "us_trading" in value or "business_daily" in value:
        return 5
    if "calendar_daily" in value or value == "daily":
        return 2
    if "weekly" in value or "week" in value:
        return 10
    if "month" in value:
        return 45
    if "quarter" in value:
        return 120
    return None


def _runtime_refresh_optional_view(
    view: dict[str, Any], *, now: datetime | None
) -> dict[str, Any]:
    refreshed = dict(view)
    metrics: dict[str, dict[str, Any]] = {}
    for metric_id, metric in view.get("metrics", {}).items():
        if not isinstance(metric, dict):
            continue
        max_days = _cadence_freshness_days(metric.get("cadence"))
        metrics[metric_id] = (
            _runtime_freshness(
                metric,
                {"freshness_max_days": max_days},
                now=now,
            )
            if max_days is not None
            else dict(metric)
        )
    refreshed["metrics"] = metrics
    if metrics:
        refreshed["available_for_analysis"] = any(
            metric.get("available_for_analysis") is True
            for metric in metrics.values()
        )
        if not refreshed["available_for_analysis"]:
            refreshed["quality_status"] = "stale_runtime"
    return refreshed


def _source_registry(root: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    payload = _load_json(root / "config" / "sources.json", {"sources": []})
    sources = [item for item in payload.get("sources", []) if isinstance(item, dict)]
    return sources, {item["id"]: item for item in sources if item.get("id")}


def _history_rows(
    connection: sqlite3.Connection,
    metric_id: str,
    source_id: str,
    *,
    since: str | None = None,
    until: str | None = None,
    published_at: str | None = None,
) -> list[dict[str, Any]]:
    has_versions = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'observation_versions'"
    ).fetchone()
    if published_at and has_versions:
        date_filters = ""
        date_parameters: list[Any] = []
        if since:
            date_filters += " AND observed_at >= ?"
            date_parameters.append(since)
        if until:
            date_filters += " AND observed_at <= ?"
            date_parameters.append(until)
        rows = connection.execute(
            f"""
            WITH ranked AS (
                SELECT observed_at, value, unit,
                       ROW_NUMBER() OVER (
                           PARTITION BY observed_at ORDER BY recorded_at DESC
                       ) AS row_number
                FROM observation_versions
                WHERE metric_id = ? AND source_id = ? AND recorded_at <= ?
            ), selected AS (
                SELECT observed_at, value, unit, 0 AS revision_count
                FROM ranked
                WHERE row_number = 1 {date_filters}
            ), legacy AS (
                SELECT o.observed_at, o.value, o.unit, o.revision_count
                FROM observations o
                WHERE o.metric_id = ? AND o.source_id = ?
                  AND o.first_seen_at <= ? {date_filters.replace('observed_at', 'o.observed_at')}
                  AND NOT EXISTS (
                      SELECT 1 FROM observation_versions v
                      WHERE v.metric_id = o.metric_id
                        AND v.source_id = o.source_id
                        AND v.observed_at = o.observed_at
                        AND v.recorded_at <= ?
                  )
            )
            SELECT * FROM selected
            UNION ALL
            SELECT * FROM legacy
            ORDER BY observed_at ASC
            """,
            [
                metric_id,
                source_id,
                published_at,
                *date_parameters,
                metric_id,
                source_id,
                published_at,
                *date_parameters,
                published_at,
            ],
        ).fetchall()
        return [dict(row) for row in rows]
    parameters: list[Any] = [metric_id, source_id]
    where = "metric_id = ? AND source_id = ?"
    if since:
        where += " AND observed_at >= ?"
        parameters.append(since)
    if until:
        where += " AND observed_at <= ?"
        parameters.append(until)
    rows = connection.execute(
        f"""
        SELECT observed_at, value, unit, revision_count
        FROM observations
        WHERE {where}
        ORDER BY observed_at ASC
        """,
        parameters,
    ).fetchall()
    return [dict(row) for row in rows]


def _prior_row(
    connection: sqlite3.Connection,
    metric_id: str,
    source_id: str,
    latest_observed_at: str,
    days: int = 7,
) -> dict[str, Any] | None:
    target = (_parse_date(latest_observed_at) - timedelta(days=days)).isoformat()
    row = connection.execute(
        """
        SELECT observed_at, value, unit, revision_count
        FROM observations
        WHERE metric_id = ? AND source_id = ? AND observed_at <= ?
        ORDER BY observed_at DESC
        LIMIT 1
        """,
        (metric_id, source_id, target),
    ).fetchone()
    return dict(row) if row else None


def _previous_observation_row(
    connection: sqlite3.Connection,
    metric_id: str,
    source_id: str,
    latest_observed_at: str,
) -> dict[str, Any] | None:
    """Return the immediately preceding native observation for the same source."""
    row = connection.execute(
        """
        SELECT observed_at, value, unit, revision_count
        FROM observations
        WHERE metric_id = ? AND source_id = ? AND observed_at < ?
        ORDER BY observed_at DESC
        LIMIT 1
        """,
        (metric_id, source_id, latest_observed_at),
    ).fetchone()
    return dict(row) if row else None


def _round(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None


def _change_view(
    connection: sqlite3.Connection,
    metric_id: str,
    source_id: str,
    latest_observed_at: str,
    latest_value: float | None,
    days: int,
) -> dict[str, Any]:
    prior = _prior_row(connection, metric_id, source_id, latest_observed_at, days)
    change = latest_value - prior["value"] if latest_value is not None and prior else None
    percent_change = (
        change / abs(prior["value"]) * 100
        if change is not None and prior and prior["value"] != 0
        else None
    )
    return {
        "days": days,
        "change": _round(change),
        "percent_change": _round(percent_change, 3),
        "prior_value": _round(prior["value"]) if prior else None,
        "prior_observed_at": prior["observed_at"] if prior else None,
    }


def _change_from_rows(
    rows: list[dict[str, Any]],
    latest_observed_at: str,
    latest_value: float | None,
    days: int,
) -> dict[str, Any]:
    target = (_parse_date(latest_observed_at) - timedelta(days=days)).isoformat()
    prior = next(
        (row for row in reversed(rows) if str(row.get("observed_at")) <= target),
        None,
    )
    change = latest_value - prior["value"] if latest_value is not None and prior else None
    percent_change = (
        change / abs(prior["value"]) * 100
        if change is not None and prior and prior["value"] != 0
        else None
    )
    return {
        "days": days,
        "change": _round(change),
        "percent_change": _round(percent_change, 3),
        "prior_value": _round(prior["value"]) if prior else None,
        "prior_observed_at": prior["observed_at"] if prior else None,
    }


def _metric_view(
    metric_id: str,
    metric: dict[str, Any],
    connection: sqlite3.Connection,
    *,
    source: dict[str, Any] | None = None,
    now: datetime | None = None,
    published_at: str | None = None,
) -> dict[str, Any]:
    metric = _runtime_freshness(metric, source, now=now)
    definition = METRICS.get(metric_id, {})
    value = metric.get("value") if isinstance(metric.get("value"), (int, float)) else None
    sparkline: list[dict[str, Any]] = []
    changes: dict[str, dict[str, Any]] = {}
    source_id = metric.get("source_id")
    observed_at = metric.get("observed_at")
    previous_observation: dict[str, Any] | None = None
    if source_id and observed_at:
        since = (_parse_date(observed_at) - timedelta(days=370)).isoformat()
        sparkline = _history_rows(
            connection,
            metric_id,
            source_id,
            since=since,
            until=str(observed_at),
            published_at=published_at,
        )
        previous_observation = next(
            (
                row
                for row in reversed(sparkline)
                if str(row.get("observed_at")) < str(observed_at)
            ),
            None,
        )
        changes = {
            window: _change_from_rows(
                sparkline,
                observed_at,
                value,
                days,
            )
            for window, days in CHANGE_WINDOWS.items()
        }
    weekly = changes.get("1w", {})
    latest_change = (
        value - previous_observation["value"]
        if value is not None and previous_observation
        else None
    )
    return {
        **metric,
        "label": definition.get("label", metric_id),
        "short_label": definition.get("short_label", definition.get("label", metric_id)),
        "description": definition.get("description", ""),
        "direction_note": definition.get("direction_note", ""),
        "order": definition.get("order", 99),
        "week_change": weekly.get("change"),
        "week_percent_change": weekly.get("percent_change"),
        "week_prior_value": weekly.get("prior_value"),
        "week_prior_observed_at": weekly.get("prior_observed_at"),
        "latest_change": _round(latest_change),
        "latest_prior_value": (
            _round(previous_observation["value"]) if previous_observation else None
        ),
        "latest_prior_observed_at": (
            previous_observation["observed_at"] if previous_observation else None
        ),
        "changes": changes,
        "sparkline": [
            {"observed_at": row["observed_at"], "value": row["value"]}
            for row in sparkline
        ],
    }


def _nearest_on_or_before(
    rows: list[dict[str, Any]],
    target: date,
    start_index: int,
) -> tuple[dict[str, Any] | None, int]:
    index = start_index
    while index + 1 < len(rows) and _parse_date(rows[index + 1]["observed_at"]) <= target:
        index += 1
    if index < 0 or index >= len(rows) or _parse_date(rows[index]["observed_at"]) > target:
        return None, index
    return rows[index], index


def _proxy_history(
    connection: sqlite3.Connection,
    metric_views: dict[str, dict[str, Any]],
    *,
    since: str | None = None,
    published_at: str | None = None,
) -> list[dict[str, Any]]:
    """Daily closing-balance series, never WTREGEN's weekly average.

    Treasury and RRP must share an observation date. Only weekly Fed assets
    may carry forward (at most 10 days). This is revised observation-date
    history, not a reconstruction of information available at each timestamp.
    """
    source_ids = {
        "fed": metric_views.get("fed_total_assets", {}).get("source_id"),
        "tga": metric_views.get("tga_daily", {}).get("source_id"),
        "rrp": metric_views.get("overnight_rrp", {}).get("source_id"),
    }
    if any(not source_id for source_id in source_ids.values()):
        return []

    history_since = None
    if since:
        history_since = (_parse_date(since) - timedelta(days=14)).isoformat()
    fed_rows = _history_rows(
        connection,
        "fed_total_assets",
        source_ids["fed"],
        since=history_since,
        published_at=published_at,
    )
    tga_rows = _history_rows(
        connection,
        "tga_daily",
        source_ids["tga"],
        since=history_since,
        published_at=published_at,
    )
    rrp_rows = _history_rows(
        connection,
        "overnight_rrp",
        source_ids["rrp"],
        since=history_since,
        published_at=published_at,
    )
    if not fed_rows or not tga_rows or not rrp_rows:
        return []

    # Do not let a backfill newer than the formal snapshot leak into this view.
    limits = {key: metric_views.get(metric, {}).get("observed_at") for key, metric in (
        ("fed", "fed_total_assets"), ("tga", "tga_daily"), ("rrp", "overnight_rrp")
    )}
    fed_rows = [r for r in fed_rows if limits["fed"] and r["observed_at"] <= limits["fed"]]
    rrp_by_date = {r["observed_at"]: r for r in rrp_rows if limits["rrp"] and r["observed_at"] <= limits["rrp"]}
    fed_index = -1
    points: list[dict[str, Any]] = []
    since_date = _parse_date(since) if since else None
    for tga in tga_rows:
        if not limits["tga"] or tga["observed_at"] > limits["tga"]:
            continue
        anchor = _parse_date(tga["observed_at"])
        rrp = rrp_by_date.get(tga["observed_at"])
        fed, fed_index = _nearest_on_or_before(fed_rows, anchor, fed_index)
        if not fed or not rrp:
            continue
        if (anchor - _parse_date(fed["observed_at"])).days > 10:
            continue
        if since_date and anchor < since_date:
            continue
        value = calculate_net_liquidity_proxy(fed["value"], tga["value"], rrp["value"])
        if value is None:
            continue
        points.append(
            {
                "observed_at": tga["observed_at"],
                "value": _round(value),
                "component_values": {
                    "fed_total_assets": fed["value"], "tga_daily": tga["value"],
                    "overnight_rrp": rrp["value"],
                },
                "component_dates": {
                    "fed_total_assets": fed["observed_at"],
                    "tga_daily": tga["observed_at"],
                    "overnight_rrp": rrp["observed_at"],
                },
            }
        )
    return points


def _point_change(points: list[dict[str, Any]], days: int) -> dict[str, Any]:
    if not points:
        return {
            "days": days,
            "change": None,
            "percent_change": None,
            "prior_value": None,
            "prior_observed_at": None,
        }
    latest = points[-1]
    target = _parse_date(latest["observed_at"]) - timedelta(days=days)
    prior = next(
        (point for point in reversed(points) if _parse_date(point["observed_at"]) <= target),
        None,
    )
    change = latest["value"] - prior["value"] if prior else None
    percent_change = (
        change / abs(prior["value"]) * 100
        if change is not None and prior and prior["value"] != 0
        else None
    )
    return {
        "days": days,
        "change": _round(change),
        "percent_change": _round(percent_change, 3),
        "prior_value": _round(prior["value"]) if prior else None,
        "prior_observed_at": prior["observed_at"] if prior else None,
    }


def calculate_aligned_spread(
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    *,
    scale: float = 100.0,
) -> list[dict[str, Any]]:
    """Return left minus right only on dates present in both source series."""
    left_by_date = {
        str(item.get("observed_at")): item.get("value")
        for item in left_rows
        if isinstance(item.get("value"), (int, float))
    }
    right_by_date = {
        str(item.get("observed_at")): item.get("value")
        for item in right_rows
        if isinstance(item.get("value"), (int, float))
    }
    return [
        {
            "observed_at": observed_at,
            "value": _round(
                (float(left_by_date[observed_at]) - float(right_by_date[observed_at]))
                * scale,
                3,
            ),
        }
        for observed_at in sorted(set(left_by_date) & set(right_by_date))
    ]


def calculate_streak(
    points: list[dict[str, Any]], *, condition: str
) -> dict[str, Any]:
    """Count consecutive valid observations at the end of a derived series."""
    if not points or condition not in {"positive", "negative"}:
        return {"active": False, "observations": 0, "start_date": None}
    predicate = (
        (lambda value: value > 0)
        if condition == "positive"
        else (lambda value: value < 0)
    )
    latest_value = points[-1].get("value")
    if not isinstance(latest_value, (int, float)) or not predicate(float(latest_value)):
        return {"active": False, "observations": 0, "start_date": None}
    count = 0
    start_date = None
    for point in reversed(points):
        value = point.get("value")
        if not isinstance(value, (int, float)) or not predicate(float(value)):
            break
        count += 1
        start_date = point.get("observed_at")
    return {"active": True, "observations": count, "start_date": start_date}


def _series_for_metric(
    connection: sqlite3.Connection,
    metric_views: dict[str, dict[str, Any]],
    metric_id: str,
    *,
    since: str | None = None,
    published_at: str | None = None,
) -> list[dict[str, Any]]:
    source_id = metric_views.get(metric_id, {}).get("source_id")
    snapshot_observed_at = metric_views.get(metric_id, {}).get("observed_at")
    if not source_id or not snapshot_observed_at:
        return []
    return _history_rows(
        connection,
        metric_id,
        source_id,
        since=since,
        until=str(snapshot_observed_at),
        published_at=published_at,
    )


def _derived_spread_view(
    metric_id: str,
    label: str,
    left_metric_id: str,
    right_metric_id: str,
    left_rows: list[dict[str, Any]],
    right_rows: list[dict[str, Any]],
    component_views: dict[str, dict[str, Any]],
    *,
    streak_condition: str,
) -> dict[str, Any]:
    points = calculate_aligned_spread(left_rows, right_rows)
    latest = points[-1] if points else {}
    changes = {
        window: _point_change(points, days)
        for window, days in CHANGE_WINDOWS.items()
    }
    latest_change = (
        _round(float(points[-1]["value"]) - float(points[-2]["value"]), 3)
        if len(points) >= 2
        else None
    )
    left_view = component_views.get(left_metric_id, {})
    right_view = component_views.get(right_metric_id, {})
    components_available = (
        left_view.get("available_for_analysis") is True
        and right_view.get("available_for_analysis") is True
    )
    quality_status = (
        "fresh_network"
        if components_available
        and left_view.get("quality_status") == "fresh_network"
        and right_view.get("quality_status") == "fresh_network"
        else "fresh_cache"
        if components_available
        else "unavailable"
    )
    available_for_analysis = bool(
        components_available
        and latest.get("value") is not None
        and latest.get("observed_at")
    )
    return {
        "metric_id": metric_id,
        "label": label,
        "left_metric_id": left_metric_id,
        "right_metric_id": right_metric_id,
        "formula": f"{left_metric_id} − {right_metric_id}",
        "unit": "basis_points",
        "source_id": "derived_from_selected_snapshot_sources",
        "source_name": "由正式快照中的两个基础指标计算",
        "quality_status": quality_status,
        "available_for_analysis": available_for_analysis,
        "methodology_version": "aligned_common_date_spread_v2",
        "component_quality": {
            left_metric_id: {
                "source_id": left_view.get("source_id"),
                "quality_status": left_view.get("quality_status"),
                "available_for_analysis": left_view.get("available_for_analysis") is True,
                "snapshot_observed_at": left_view.get("observed_at"),
            },
            right_metric_id: {
                "source_id": right_view.get("source_id"),
                "quality_status": right_view.get("quality_status"),
                "available_for_analysis": right_view.get("available_for_analysis") is True,
                "snapshot_observed_at": right_view.get("observed_at"),
            },
        },
        "value": latest.get("value"),
        "observed_at": latest.get("observed_at"),
        "latest_change": latest_change,
        "changes": changes,
        "streak": calculate_streak(points, condition=streak_condition),
        "history": points[-366:],
    }


def _funding_rates_view(
    connection: sqlite3.Connection,
    metric_views: dict[str, dict[str, Any]],
    *,
    published_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    rate_ids = (
        "sofr",
        "effective_fed_funds_rate",
        "iorb",
        "on_rrp_award_rate",
    )
    since = (date.today() - timedelta(days=400)).isoformat()
    rows = {
        metric_id: _series_for_metric(
            connection, metric_views, metric_id, since=since
            , published_at=published_at
        )
        for metric_id in rate_ids
    }
    definitions = (
        ("spread_sofr_iorb", "SOFR − IORB", "sofr", "iorb"),
        (
            "spread_sofr_effr",
            "SOFR − EFFR",
            "sofr",
            "effective_fed_funds_rate",
        ),
        (
            "spread_effr_iorb",
            "EFFR − IORB",
            "effective_fed_funds_rate",
            "iorb",
        ),
        (
            "spread_effr_on_rrp",
            "EFFR − RRP 利率",
            "effective_fed_funds_rate",
            "on_rrp_award_rate",
        ),
    )
    spreads = {
        metric_id: _derived_spread_view(
            metric_id,
            label,
            left_id,
            right_id,
            rows[left_id],
            rows[right_id],
            metric_views,
            streak_condition="positive",
        )
        for metric_id, label, left_id, right_id in definitions
    }
    primary = spreads["spread_sofr_iorb"]
    pipe = spreads["spread_sofr_effr"]
    primary_value = primary.get("value")
    pipe_value = pipe.get("value")
    positive_days = primary.get("streak", {}).get("observations", 0)
    if not (
        primary.get("available_for_analysis") is True
        and pipe.get("available_for_analysis") is True
    ):
        state = "unavailable"
        conclusion = "基础利率数据当前不可用于分析，暂时不判断短端资金压力。"
    elif (
        isinstance(primary_value, (int, float))
        and primary_value > 0
        and positive_days >= 3
        and isinstance(pipe_value, (int, float))
        and pipe_value > 0
    ):
        state = "pressure"
        conclusion = "短期美元融资成本持续高于银行安全停钱的回报，需要警惕资金压力。"
    elif (
        isinstance(primary_value, (int, float))
        and primary_value > 0
    ) or (
        isinstance(pipe_value, (int, float))
        and pipe_value >= 5
    ):
        state = "watch"
        conclusion = "短端出现偏离，但持续时间或幅度还不足以确认系统性资金压力。"
    elif primary_value is None or pipe_value is None:
        state = "unavailable"
        conclusion = "关键利差没有共同观察日期，暂时不能判断短端资金压力。"
    else:
        state = "normal"
        conclusion = "短端利差仍在常见范围内，暂未看到持续的融资压力信号。"
    levels = [metric_views[metric_id] for metric_id in rate_ids if metric_id in metric_views]
    return (
        {
            "state": state,
            "conclusion": conclusion,
            "levels": levels,
            "spreads": spreads,
            "reading_rule": "重点看 SOFR−IORB 和 SOFR−EFFR 是否持续转正并扩大；单日波动不直接等于准备金短缺。",
        },
        spreads,
    )


def _common_curve_points(
    rows: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    if not rows or any(not values for values in rows.values()):
        return []
    by_metric = {
        metric_id: {
            str(item["observed_at"]): item["value"]
            for item in values
            if isinstance(item.get("value"), (int, float))
        }
        for metric_id, values in rows.items()
    }
    common_dates = set.intersection(*(set(values) for values in by_metric.values()))
    return [
        {
            "observed_at": observed_at,
            "values": {
                metric_id: _round(float(values[observed_at]), 4)
                for metric_id, values in by_metric.items()
            },
        }
        for observed_at in sorted(common_dates)
    ]


def _curve_snapshot(
    points: list[dict[str, Any]], *, days_back: int = 0
) -> dict[str, Any] | None:
    if not points:
        return None
    if days_back == 0:
        return points[-1]
    target = _parse_date(points[-1]["observed_at"]) - timedelta(days=days_back)
    return next(
        (
            point
            for point in reversed(points)
            if _parse_date(point["observed_at"]) <= target
        ),
        None,
    )


def _treasury_curve_view(
    connection: sqlite3.Connection,
    metric_views: dict[str, dict[str, Any]],
    *,
    published_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    maturity_ids = (
        "treasury_3m_yield",
        "treasury_2y_yield",
        "treasury_10y_yield",
        "treasury_30y_yield",
    )
    since = (date.today() - timedelta(days=400)).isoformat()
    rows = {
        metric_id: _series_for_metric(
            connection, metric_views, metric_id, since=since
            , published_at=published_at
        )
        for metric_id in maturity_ids
    }
    curve_points = _common_curve_points(rows)
    spread_definitions = (
        (
            "spread_10y_2y",
            "10Y − 2Y",
            "treasury_10y_yield",
            "treasury_2y_yield",
        ),
        (
            "spread_10y_3m",
            "10Y − 3M",
            "treasury_10y_yield",
            "treasury_3m_yield",
        ),
        (
            "spread_30y_10y",
            "30Y − 10Y",
            "treasury_30y_yield",
            "treasury_10y_yield",
        ),
    )
    spreads = {
        metric_id: _derived_spread_view(
            metric_id,
            label,
            left_id,
            right_id,
            rows[left_id],
            rows[right_id],
            metric_views,
            streak_condition="negative",
        )
        for metric_id, label, left_id, right_id in spread_definitions
    }
    latest = _curve_snapshot(curve_points)
    curve_available = all(
        metric_views.get(metric_id, {}).get("available_for_analysis") is True
        for metric_id in maturity_ids
    ) and all(
        spread.get("available_for_analysis") is True for spread in spreads.values()
    )
    return (
        {
            "state": "ready" if latest and curve_available else "unavailable",
            "maturities": [
                {"metric_id": metric_id, "label": METRICS[metric_id]["short_label"]}
                for metric_id in maturity_ids
            ],
            "snapshots": {
                "latest": latest,
                "1w": _curve_snapshot(curve_points, days_back=7),
                "1m": _curve_snapshot(curve_points, days_back=31),
            },
            "spreads": spreads,
            "reading_rule": "10Y−2Y 或 10Y−3M 小于 0 才叫倒挂；连续天数按有共同数据的交易日计算。",
        },
        spreads,
    )


def _expectation_metrics(
    expectations: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    generated_at = str(expectations.get("generated_at") or "")[:10] or None
    for topic in expectations.get("topics", []):
        if not isinstance(topic, dict) or topic.get("state") != "ready":
            continue
        analysis_eligible = topic.get("analysis_eligible") is True
        freshness_status = str(topic.get("freshness_status") or "not_configured")
        quality_status = (
            "fresh_network"
            if analysis_eligible
            else "stale"
            if freshness_status in {"stale", "unknown"}
            else "needs_review"
        )
        for outcome in topic.get("outcomes", []):
            if not isinstance(outcome, dict) or not outcome.get("outcome_id"):
                continue
            metric_id = str(outcome["outcome_id"])
            result[metric_id] = {
                "metric_id": metric_id,
                "label": f"Polymarket：{topic.get('label')}—{outcome.get('label')}",
                "value": outcome.get("probability"),
                "observed_at": str(outcome.get("updated_at") or generated_at)[:10],
                "unit": "probability",
                "latest_change": outcome.get("change_1d"),
                "changes": {
                    "1w": {"change": outcome.get("change_1w")},
                    "1m": {"change": outcome.get("change_1m")},
                },
                "source_name": "Polymarket",
                "source_url": topic.get("url"),
                "evidence_class": "market_expectation",
                "quality": topic.get("quality"),
                "quality_status": quality_status,
                "available_for_analysis": analysis_eligible,
                "age_days": (
                    round(float(topic["age_hours"]) / 24, 3)
                    if isinstance(topic.get("age_hours"), (int, float))
                    else None
                ),
            }
    return result


def calculate_net_liquidity_proxy(
    fed_assets_usd_millions: float | None,
    tga_usd_millions: float | None,
    rrp_usd_billions: float | None,
) -> float | None:
    """Return Fed assets - TGA - RRP in USD millions, or null when incomplete."""
    if None in (fed_assets_usd_millions, tga_usd_millions, rrp_usd_billions):
        return None
    return float(fed_assets_usd_millions) - float(tga_usd_millions) - float(rrp_usd_billions) * 1000


def calculate_change_contributions(
    fed_change_usd_millions: float | None,
    tga_change_usd_millions: float | None,
    rrp_change_usd_billions: float | None,
) -> list[dict[str, Any]]:
    """Break a proxy change into Fed, TGA, and RRP formula contributions."""
    if None in (
        fed_change_usd_millions,
        tga_change_usd_millions,
        rrp_change_usd_billions,
    ):
        return []
    fed_change = float(fed_change_usd_millions)
    tga_change = float(tga_change_usd_millions)
    rrp_change_millions = float(rrp_change_usd_billions) * 1000
    contributions = [
        {
            "id": "fed_total_assets",
            "label": "美联储资产",
            "raw_change_usd_millions": _round(fed_change),
            "contribution_usd_millions": _round(fed_change),
            "value_usd_millions": _round(fed_change),
            "formula": "Δ联储总资产",
        },
        {
            "id": "tga_daily",
            "label": "财政部现金",
            "raw_change_usd_millions": _round(tga_change),
            "contribution_usd_millions": _round(-tga_change),
            "value_usd_millions": _round(-tga_change),
            "formula": "−ΔTGA",
        },
        {
            "id": "overnight_rrp",
            "label": "RRP 停车场现金",
            "raw_change_usd_millions": _round(rrp_change_millions),
            "contribution_usd_millions": _round(-rrp_change_millions),
            "value_usd_millions": _round(-rrp_change_millions),
            "formula": "−ΔRRP",
        },
    ]
    for item in contributions:
        value = item["contribution_usd_millions"]
        item["effect"] = "supportive" if value > 0 else "draining" if value < 0 else "neutral"
    return sorted(
        contributions,
        key=lambda item: abs(item["contribution_usd_millions"]),
        reverse=True,
    )


def calculate_weekly_contributions(
    current: dict[str, float | None],
    previous: dict[str, float | None],
) -> list[dict[str, Any]]:
    required = ("fed_total_assets", "tga_daily", "overnight_rrp")
    if any(current.get(key) is None or previous.get(key) is None for key in required):
        return []
    return calculate_change_contributions(
        float(current["fed_total_assets"]) - float(previous["fed_total_assets"]),
        float(current["tga_daily"]) - float(previous["tga_daily"]),
        float(current["overnight_rrp"]) - float(previous["overnight_rrp"])
    )


def _proxy_view(
    metrics: dict[str, dict[str, Any]],
    history: list[dict[str, Any]],
) -> dict[str, Any]:
    keys = ("fed_total_assets", "tga_daily", "overnight_rrp")
    latest_point = history[-1] if history else {}
    current = latest_point.get("component_values", {})
    current_value = latest_point.get("value")
    weekly_change = _point_change(history, 7)
    previous_value = weekly_change.get("prior_value")
    previous_point = next((p for p in history if p["observed_at"] == weekly_change.get("prior_observed_at")), {})
    previous = previous_point.get("component_values", {})
    latest_changes = {
        key: metrics.get(key, {}).get("latest_change")
        for key in keys
    }
    latest_release_change = calculate_net_liquidity_proxy(
        latest_changes["fed_total_assets"],
        latest_changes["tga_daily"],
        latest_changes["overnight_rrp"],
    )
    latest_release_contributions = calculate_change_contributions(
        latest_changes["fed_total_assets"],
        latest_changes["tga_daily"],
        latest_changes["overnight_rrp"],
    )
    for item in latest_release_contributions:
        metric = metrics.get(item["id"], {})
        item.update({
            "cadence": metric.get("cadence"),
            "comparison_period": "最近一周" if item["id"] == "fed_total_assets" else "最近一个数据日",
            "observed_at": metric.get("observed_at"),
            "prior_observed_at": metric.get("latest_prior_observed_at"),
            "fetched_at": metric.get("fetched_at"),
        })
    change = current_value - previous_value if current_value is not None and previous_value is not None else None
    if change is None:
        direction = "unavailable"
        headline = "这周的水量变化暂时算不出来"
    elif change > 0:
        direction = "improving"
        headline = "按这组账本数据看，这周的水变多了"
    elif change < 0:
        direction = "tightening"
        headline = "按这组账本数据看，这周的水变少了"
    else:
        direction = "flat"
        headline = "按这组账本数据看，这周几乎没变"
    trend = history[-366:]
    components_available = all(
        metrics.get(key, {}).get("available_for_analysis") is True for key in keys
    )
    quality_status = (
        "fresh_network"
        if components_available
        and all(metrics.get(key, {}).get("quality_status") == "fresh_network" for key in keys)
        else "fresh_cache"
        if components_available
        else "unavailable"
    )
    return {
        "id": "net_liquidity_proxy",
        "label": "流动性参考值",
        "technical_label": "净流动性代理值",
        "formula": "美联储总资产 - 财政部现金 - RRP",
        "unit": "usd_millions",
        "methodology_version": "daily-tga-v1",
        "quality_status": quality_status,
        "available_for_analysis": bool(components_available and current_value is not None),
        "value": _round(current_value),
        "observed_at": latest_point.get("observed_at"),
        "week_prior_value": _round(previous_value),
        "week_change": _round(change),
        "latest_release_change": _round(latest_release_change),
        "latest_release_formula": "Δ美联储总资产 - Δ财政部现金 - ΔRRP",
        "latest_release_method": "最新变化合计：联储用周变化，TGA、RRP 用日变化；不是同一天的净变化。",
        "direction": direction,
        "headline": headline,
        "trend": trend,
        "trend_latest_value": trend[-1]["value"] if trend else None,
        "trend_latest_observed_at": trend[-1]["observed_at"] if trend else None,
        "trend_changes": {
            window: _point_change(history, days)
            for window, days in CHANGE_WINDOWS.items()
        },
        "trend_method": "走势使用同日的每日 TGA 和 RRP，联储资产沿用该日或之前最近的周值（最多10天）。缺少同日数据就跳过，不用周平均补齐；周、月变化都从这条日序列计算。历史按数据日期展示，可能含后续修订，不代表当时已公开的信息。",
        "coverage": {
            "first_observed_at": history[0]["observed_at"] if history else None,
            "last_observed_at": latest_point.get("observed_at"),
            "point_count": len(history),
            "missing_policy": "仅保留 TGA 与 RRP 均有数据的日期，不补零或替换周平均",
        },
        "components": [
            {
                "metric_id": key,
                "label": METRICS[key]["short_label"],
                "value": current.get(key),
                "observed_at": latest_point.get("component_dates", {}).get(key),
                "fetched_at": metrics.get(key, {}).get("fetched_at"),
                "week_prior_observed_at": previous_point.get("component_dates", {}).get(key),
            }
            for key in keys
        ],
        "contributions": calculate_weekly_contributions(current, previous),
        "latest_release_contributions": latest_release_contributions,
        "caveat": "它只帮助我们观察水量方向，不代表这些钱能直接买股票或加密，也不是买卖信号。",
    }


def _source_views(
    snapshot: dict[str, Any],
    source_list: list[dict[str, Any]],
    health: dict[str, Any],
) -> list[dict[str, Any]]:
    selected = {
        metric.get("source_id")
        for metric in snapshot.get("metrics", {}).values()
        if isinstance(metric, dict)
    }
    latest_health = snapshot.get("source_health", {})
    rates = health.get("source_rates", {})
    result = []
    for source in source_list:
        outcome = latest_health.get(source.get("id"), {})
        rate = rates.get(source.get("id"), {})
        result.append(
            {
                "source_id": source.get("id"),
                "name": source.get("name"),
                "metric_id": source.get("metric_id"),
                "metric_label": METRICS.get(source.get("metric_id"), {}).get(
                    "label", source.get("metric_id")
                ),
                "group": source.get("group"),
                "authority": source.get("authority"),
                "source_owner": source.get("source_owner"),
                "url": source.get("url"),
                "cadence": source.get("cadence"),
                "release_schedule_note": source.get("release_schedule_note"),
                "selected": source.get("id") in selected,
                "quality_status": outcome.get("quality_status", "unavailable"),
                "observed_at": outcome.get("observed_at"),
                "fetched_at": outcome.get("fetched_at"),
                "age_days": outcome.get("age_days"),
                "error": outcome.get("error"),
                "eligible_rate_14d": rate.get("eligible_rate"),
                "observed_days_14d": rate.get("runs", 0),
            }
        )
    return result


def _stablecoin_view(root: Path) -> dict[str, Any]:
    payload = load_stablecoin_payload(root)
    metrics: dict[str, dict[str, Any]] = {}
    for metric_id, metric in payload.get("metrics", {}).items():
        if not isinstance(metric, dict):
            continue
        definition = METRICS.get(metric_id, {})
        metrics[metric_id] = {
            **metric,
            "label": definition.get("label", metric_id),
            "short_label": definition.get(
                "short_label", definition.get("label", metric_id)
            ),
            "description": definition.get("description", ""),
            "direction_note": definition.get("direction_note", ""),
            "order": definition.get("order", 99),
        }
    public_payload = {key: value for key, value in payload.items() if key != "history"}
    return {**public_payload, "metrics": metrics}


def _stablecoin_source_view(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source", {})
    return {
        "source_id": source.get("source_id", "defillama_stablecoins"),
        "name": source.get("name", "DefiLlama stablecoin data"),
        "metric_id": "stablecoin_usd_supply",
        "metric_label": METRICS["stablecoin_usd_supply"]["label"],
        "group": "crypto_liquidity",
        "authority": source.get("authority", "trusted_aggregator"),
        "source_owner": source.get("source_owner", "DefiLlama"),
        "url": source.get("url", "https://defillama.com/docs/api"),
        "cadence": source.get("cadence", "calendar_daily"),
        "release_schedule_note": "每天采集一次。它是可信行业聚合数据，不是政府或央行官方统计。",
        "selected": bool(payload.get("available_for_analysis")),
        "quality_status": payload.get("quality_status", "unavailable"),
        "observed_at": source.get("observed_at"),
        "fetched_at": source.get("fetched_at"),
        "age_days": source.get("age_days"),
        "error": source.get("error"),
        "eligible_rate_14d": None,
        "observed_days_14d": 0,
    }


def _optional_crypto_view(payload: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, dict[str, Any]] = {}
    for metric_id, metric in payload.get("metrics", {}).items():
        if not isinstance(metric, dict):
            continue
        definition = METRICS.get(metric_id, {})
        metrics[metric_id] = {
            **metric,
            "label": definition.get("label", metric_id),
            "short_label": definition.get(
                "short_label", definition.get("label", metric_id)
            ),
            "description": definition.get("description", ""),
            "direction_note": definition.get("direction_note", ""),
            "order": definition.get("order", 99),
        }
    return {**payload, "metrics": metrics}


def _crypto_etf_source_view(payload: dict[str, Any]) -> dict[str, Any]:
    source = payload.get("source", {})
    assets = payload.get("assets", {})
    observed = max(
        (
            str(item.get("observed_at"))
            for item in assets.values()
            if isinstance(item, dict) and item.get("observed_at")
        ),
        default=None,
    )
    return {
        "source_id": source.get("source_id", "sosovalue_us_crypto_etf"),
        "name": source.get("name", "SoSoValue US Crypto ETF OpenAPI"),
        "metric_id": "etf_btc_net_flow_latest",
        "metric_label": METRICS["etf_btc_net_flow_latest"]["label"],
        "group": "crypto_etf",
        "authority": source.get("authority", "trusted_specialist"),
        "source_owner": source.get("source_owner", "SoSoValue"),
        "url": source.get(
            "url", "https://sosovalue.gitbook.io/soso-value-api-doc/2.-etf/etf.md"
        ),
        "cadence": source.get("cadence", "us_trading_daily_t_plus_1"),
        "release_schedule_note": "美股收盘后 T+1 更新；只使用已经结算的净流入。",
        "selected": bool(payload.get("available_for_analysis")),
        "quality_status": payload.get("quality_status", "unavailable"),
        "observed_at": observed,
        "fetched_at": source.get("fetched_at"),
        "age_days": None,
        "error": source.get("error"),
        "eligible_rate_14d": None,
        "observed_days_14d": 0,
    }


def _crypto_derivatives_source_view(payload: dict[str, Any]) -> dict[str, Any]:
    assets = payload.get("assets", {})
    observed = max(
        (
            str(item.get("observed_at"))
            for item in assets.values()
            if isinstance(item, dict) and item.get("observed_at")
        ),
        default=None,
    )
    fetched = max(
        (
            str(item.get("fetched_at"))
            for item in assets.values()
            if isinstance(item, dict) and item.get("fetched_at")
        ),
        default=None,
    )
    errors = payload.get("quality", {}).get("errors_by_asset", {})
    return {
        "source_id": "official_usdt_perpetuals_3_venues",
        "name": "Binance、OKX、Bybit 官方 USDT 永续",
        "metric_id": "derivatives_btc_open_interest",
        "metric_label": METRICS["derivatives_btc_open_interest"]["label"],
        "group": "crypto_derivatives",
        "authority": "official_primary_multi_source",
        "source_owner": "Binance / OKX / Bybit",
        "url": "https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api",
        "cadence": "continuous_sampled_daily",
        "release_schedule_note": "市场连续更新；看板每天采集一次晨间快照。",
        "selected": bool(payload.get("available_for_analysis")),
        "quality_status": payload.get("quality_status", "unavailable"),
        "observed_at": observed,
        "fetched_at": fetched,
        "age_days": 0 if observed else None,
        "error": json.dumps(errors, ensure_ascii=False) if errors else None,
        "eligible_rate_14d": None,
        "observed_days_14d": 0,
    }


def _cross_asset_view(root: Path) -> dict[str, Any]:
    payload = load_cross_asset_payload(root)
    metrics: dict[str, dict[str, Any]] = {}
    for metric_id, metric in payload.get("metrics", {}).items():
        if not isinstance(metric, dict):
            continue
        definition = METRICS.get(metric_id, {})
        metrics[metric_id] = {
            **metric,
            "label": definition.get("label", metric_id),
            "short_label": definition.get(
                "short_label", definition.get("label", metric_id)
            ),
            "description": definition.get("description", ""),
            "direction_note": definition.get("direction_note", ""),
            "order": definition.get("order", 99),
        }
    return {**payload, "metrics": metrics}


def _cross_asset_source_views(payload: dict[str, Any]) -> list[dict[str, Any]]:
    labels = {
        "btc_usd": METRICS["cross_asset_btc_spx_ratio"]["label"],
        "paxg_usd": METRICS["cross_asset_btc_gold_ratio"]["label"],
        "sp500": METRICS["cross_asset_btc_spx_ratio"]["label"],
        "broad_dollar_index": METRICS["cross_asset_btc_broad_dollar_corr_30d"]["label"],
    }
    metric_ids = {
        "btc_usd": "cross_asset_btc_spx_ratio",
        "paxg_usd": "cross_asset_btc_gold_ratio",
        "sp500": "cross_asset_btc_spx_ratio",
        "broad_dollar_index": "cross_asset_btc_broad_dollar_corr_30d",
    }
    result = []
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        series_id = str(source.get("series_id") or "")
        result.append(
            {
                "source_id": source.get("source_id", series_id or "cross_asset"),
                "name": source.get("name", "跨资产数据源"),
                "metric_id": metric_ids.get(
                    series_id, "cross_asset_btc_spx_ratio"
                ),
                "metric_label": labels.get(series_id, "跨资产相对强弱"),
                "group": "cross_asset",
                "authority": source.get("authority", "trusted_specialist"),
                "source_owner": source.get("source_owner"),
                "url": source.get("url"),
                "cadence": source.get("cadence", "us_market_close_daily"),
                "release_schedule_note": "每天更新，只按双方都有数据的共同日期比较。",
                "selected": bool(source.get("available_for_analysis")),
                "quality_status": source.get("quality_status", "unavailable"),
                "observed_at": source.get("observed_at"),
                "fetched_at": source.get("fetched_at"),
                "age_days": source.get("age_days"),
                "error": source.get("error"),
                "eligible_rate_14d": None,
                "observed_days_14d": 0,
            }
        )
    return result


def _energy_view(root: Path) -> dict[str, Any]:
    payload = load_energy_payload(root)
    metrics: dict[str, dict[str, Any]] = {}
    for metric_id, metric in payload.get("metrics", {}).items():
        if not isinstance(metric, dict):
            continue
        definition = METRICS.get(metric_id, {})
        metrics[metric_id] = {
            **metric,
            "label": definition.get("label", metric_id),
            "short_label": definition.get("short_label", definition.get("label", metric_id)),
            "description": definition.get("description", ""),
            "direction_note": definition.get("direction_note", ""),
            "order": definition.get("order", 99),
        }
    return {**payload, "metrics": metrics}


def _energy_source_views(payload: dict[str, Any]) -> list[dict[str, Any]]:
    source_metric_ids = {
        "wti_spot": "energy_wti_spot",
        "brent_spot": "energy_brent_spot",
        "commercial_crude_stocks": "energy_commercial_crude_stocks",
        "cushing_crude_stocks": "energy_cushing_crude_stocks",
        "spr_stocks": "energy_spr_stocks",
        "gasoline_product_supplied": "energy_gasoline_product_supplied",
    }
    result = []
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        metric_id = source_metric_ids.get(str(source.get("series_id")), "energy_wti_spot")
        cadence = source.get("cadence")
        result.append({
            "source_id": source.get("source_id", source.get("series_id", "energy")),
            "name": source.get("name", "能源数据源"),
            "metric_id": metric_id,
            "metric_label": METRICS.get(metric_id, {}).get("label", metric_id),
            "group": "energy",
            "authority": source.get("authority", "official"),
            "source_owner": source.get("source_owner"),
            "url": source.get("url"),
            "cadence": cadence,
            "release_schedule_note": "工作日更新。" if cadence == "business_daily" else "EIA 通常每周三发布，假日周可顺延。",
            "selected": bool(source.get("available_for_analysis")),
            "quality_status": source.get("quality_status", "unavailable"),
            "observed_at": source.get("observed_at"),
            "fetched_at": source.get("fetched_at"),
            "age_days": source.get("age_days"),
            "error": source.get("error"),
            "eligible_rate_14d": None,
            "observed_days_14d": 0,
        })
    return result


def _yen_carry_view(root: Path) -> dict[str, Any]:
    payload = load_yen_carry_payload(root)
    metrics: dict[str, dict[str, Any]] = {}
    for metric_id, metric in payload.get("metrics", {}).items():
        if not isinstance(metric, dict):
            continue
        definition = METRICS.get(metric_id, {})
        metrics[metric_id] = {
            **metric,
            "label": definition.get("label", metric_id),
            "short_label": definition.get(
                "short_label", definition.get("label", metric_id)
            ),
            "description": definition.get("description", ""),
            "direction_note": definition.get("direction_note", ""),
            "order": definition.get("order", 99),
        }
    return {**payload, "metrics": metrics}


def _yen_carry_source_views(payload: dict[str, Any]) -> list[dict[str, Any]]:
    metric_ids = {
        "usd_jpy": "yen_carry_usd_jpy",
        "boj_call_rate": "yen_carry_short_rate_spread",
        "jgb_2y_proxy": "yen_carry_2y_rate_spread",
        "cftc_leveraged_net_short": "yen_carry_cftc_leveraged_net_short",
        "fx_swap_turnover": "yen_carry_fx_swap_turnover",
    }
    notes = {
        "usd_jpy": "欧洲工作日更新；由 ECB 的欧元兑美元和欧元兑日元参考汇率交叉计算。",
        "boj_call_rate": "日本工作日更新；用于计算美日短端利差。",
        "jgb_2y_proxy": "日本工作日发布；页面日期对应发布日，报价来自前一工作日 15:00。",
        "cftc_leveraged_net_short": "每周五发布，仓位观察日通常是周二。",
        "fx_swap_turnover": "日本工作日更新；成交额只表示活动强弱，不表示方向。",
    }
    result = []
    for source in payload.get("sources", []):
        if not isinstance(source, dict):
            continue
        series_id = str(source.get("series_id") or "")
        metric_id = metric_ids.get(series_id, "yen_carry_usd_jpy")
        result.append(
            {
                "source_id": source.get("source_id", series_id or "yen_carry"),
                "name": source.get("name", "日元套息数据源"),
                "metric_id": metric_id,
                "metric_label": METRICS.get(metric_id, {}).get("label", metric_id),
                "group": "yen_carry",
                "authority": source.get("authority"),
                "source_owner": source.get("source_owner"),
                "url": source.get("url"),
                "cadence": source.get("cadence"),
                "release_schedule_note": notes.get(series_id, "按来源原生频率更新。"),
                "selected": bool(source.get("available_for_analysis")),
                "quality_status": source.get("quality_status", "unavailable"),
                "observed_at": source.get("observed_at"),
                "fetched_at": source.get("fetched_at"),
                "age_days": source.get("age_days"),
                "error": source.get("error"),
                "eligible_rate_14d": None,
                "observed_days_14d": 0,
            }
        )
    return result


def _event_calendar_view(
    root: Path, *, now: datetime | None = None
) -> dict[str, Any]:
    current = (now or datetime.now(tz=UTC)).astimezone(UTC)
    bundle = load_context_bundle(root)
    if not bundle:
        return {
            "status": "unavailable",
            "message": "未来事件日历暂不可用",
            "generated_at": None,
            "age_hours": None,
            "next_event": None,
            "events": [],
            "bls": None,
        }

    def parse_moment(value: Any) -> datetime | None:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    generated = parse_moment(bundle.get("generated_at"))
    age_hours = (
        max(0.0, (current - generated).total_seconds() / 3600)
        if generated is not None
        else None
    )
    future_cutoff = current + timedelta(days=90)
    events = []
    for event in bundle.get("future_90d", []):
        if not isinstance(event, dict):
            continue
        starts = parse_moment(event.get("starts_at"))
        if starts is None or not current <= starts <= future_cutoff:
            continue
        events.append(
            {
                key: event.get(key)
                for key in (
                    "context_id",
                    "category",
                    "release_type",
                    "reference_period",
                    "title",
                    "starts_at",
                    "source_id",
                    "source_name",
                    "source_tier",
                    "url",
                    "delivery_status",
                    "verified_at",
                    "schedule_id",
                )
            }
        )
    events.sort(key=lambda item: str(item.get("starts_at") or ""))
    calendar_health = (
        bundle.get("calendar_health")
        if isinstance(bundle.get("calendar_health"), dict)
        else {}
    )
    status = str(calendar_health.get("status") or "unavailable")
    if age_hours is None or age_hours > 168:
        status = "unavailable"
    elif age_hours > 36 and status == "ready":
        status = "degraded"
    messages = {
        "ready": "未来事件日历已更新",
        "degraded": "部分日历来源使用缓存或尚未更新",
        "unavailable": "未来事件日历暂不可用",
    }
    source_health = [
        item
        for item in bundle.get("source_health", [])
        if isinstance(item, dict)
        and item.get("source_id")
        in {
            "fomc_calendar",
            "bea_release_schedule",
            "bls_release_calendar",
            "treasury_auction_schedule",
        }
    ]
    bls = next(
        (
            {
                key: item.get(key)
                for key in (
                    "source_id",
                    "label",
                    "status",
                    "delivery_status",
                    "item_count",
                    "verified_at",
                    "cache_age_days",
                    "upstream_error",
                    "error",
                )
            }
            for item in source_health
            if item.get("source_id") == "bls_release_calendar"
        ),
        None,
    )
    return {
        "status": status,
        "message": messages.get(status, messages["unavailable"]),
        "generated_at": bundle.get("generated_at"),
        "age_hours": round(age_hours, 1) if age_hours is not None else None,
        "next_event": events[0] if events else None,
        "events": events[:12],
        "event_count": len(events),
        "bls": bls,
        "sources": source_health,
    }


def build_dashboard(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    root = root.resolve()
    snapshot = _load_json(root / "data" / "snapshots" / "latest.json")
    if not snapshot:
        raise FileNotFoundError("no formal dashboard snapshot is available")
    health = _load_json(root / "data" / "status" / "health-14d.json")
    agent_health = _load_json(root / "data" / "status" / "agent-health-14d.json")
    shadow_internal = _load_json(root / "data" / "status" / "latest-shadow-cycle.json")
    shadow = public_cycle_status(shadow_internal)
    source_list, source_by_id = _source_registry(root)
    with closing(_connect_readonly(root / "data" / "channel.sqlite3")) as connection:
        metric_views = {
            metric_id: _metric_view(
                metric_id,
                metric,
                connection,
                source=source_by_id.get(str(metric.get("source_id") or "")),
                now=now,
                published_at=str(snapshot.get("completed_at") or "") or None,
            )
            for metric_id, metric in snapshot.get("metrics", {}).items()
            if isinstance(metric, dict)
        }
        publication_cutoff = str(snapshot.get("completed_at") or "") or None
        proxy_history = _proxy_history(
            connection, metric_views, published_at=publication_cutoff
        )
        funding_rates, funding_spreads = _funding_rates_view(
            connection, metric_views, published_at=publication_cutoff
        )
        treasury_curve, curve_spreads = _treasury_curve_view(
            connection, metric_views, published_at=publication_cutoff
        )
    stablecoin_liquidity = _runtime_refresh_optional_view(
        _stablecoin_view(root), now=now
    )
    stablecoin_metrics = stablecoin_liquidity.get("metrics", {})
    crypto_etf = _runtime_refresh_optional_view(
        _optional_crypto_view(load_crypto_etf_payload(root)), now=now
    )
    crypto_derivatives = _runtime_refresh_optional_view(
        _optional_crypto_view(load_crypto_derivatives_payload(root)), now=now
    )
    cross_asset = _runtime_refresh_optional_view(_cross_asset_view(root), now=now)
    yen_carry = _runtime_refresh_optional_view(_yen_carry_view(root), now=now)
    energy = _runtime_refresh_optional_view(_energy_view(root), now=now)
    coinbase_premium = _runtime_refresh_optional_view(
        load_premium(root, now=now), now=now
    )
    crypto_etf_metrics = crypto_etf.get("metrics", {})
    crypto_derivatives_metrics = crypto_derivatives.get("metrics", {})
    cross_asset_metrics = cross_asset.get("metrics", {})
    yen_carry_metrics = yen_carry.get("metrics", {})
    energy_metrics = energy.get("metrics", {})
    all_metrics = {
        **metric_views,
        **stablecoin_metrics,
        **crypto_etf_metrics,
        **crypto_derivatives_metrics,
        **cross_asset_metrics,
        **yen_carry_metrics,
        **energy_metrics,
        **coinbase_premium.get("metrics", {}),
    }
    market_expectations = load_market_expectations(root)
    event_calendar = _event_calendar_view(root, now=now)
    expectation_metrics = _expectation_metrics(market_expectations)
    derived_metrics = {
        **funding_spreads,
        **curve_spreads,
        **expectation_metrics,
    }
    layers = []
    for group_id, group in sorted(GROUPS.items(), key=lambda item: item[1]["order"]):
        group_metrics = sorted(
            [item for item in metric_views.values() if item.get("group") == group_id],
            key=lambda item: item.get("order", 99),
        )
        check = snapshot.get("publication", {}).get("group_checks", {}).get(group_id, {})
        layers.append(
            {
                "group_id": group_id,
                **group,
                "metrics": group_metrics,
                "quality": check,
            }
        )
    publication = snapshot.get("publication", {})
    unavailable = [
        metric
        for metric in metric_views.values()
        if not metric.get("available_for_analysis")
    ]
    nonfresh = [
        metric
        for metric in metric_views.values()
        if metric.get("quality_status") not in {"fresh_network", "fresh_cache"}
    ]
    runtime_stale = [
        metric
        for metric in metric_views.values()
        if metric.get("runtime_freshness_status") == "stale"
    ]
    runtime_analysis_allowed = bool(publication.get("analysis_allowed")) and not runtime_stale
    runtime_eligible_count = sum(
        metric.get("available_for_analysis") is True for metric in metric_views.values()
    )
    data_status_code = (
        "stale"
        if runtime_stale
        else "ready"
        if runtime_analysis_allowed
        else "degraded"
    )
    proxy = _proxy_view(metric_views, proxy_history)
    agent_analysis = load_agent_analysis(
        root,
        snapshot_run_id=str(snapshot.get("run_id") or ""),
        analysis_allowed=runtime_analysis_allowed,
        metrics={**all_metrics, **derived_metrics},
        proxy=proxy,
    )
    return {
        "schema_version": "2.7",
        "release_id": snapshot.get("run_id"),
        "generated_at": _iso_now(now),
        "snapshot": {
            "run_id": snapshot.get("run_id"),
            "started_at": snapshot.get("started_at"),
            "completed_at": snapshot.get("completed_at"),
            "publication": publication,
            "revision_count_detected": snapshot.get("revision_count_detected", 0),
            "reconciliation_issues": snapshot.get("reconciliation_issues", []),
        },
        "status": {
            "code": publication.get("status", "block_analysis"),
            "analysis_allowed": runtime_analysis_allowed,
            "service_status": {"code": "ok", "message": "网页服务正常"},
            "update_status": {
                "code": shadow.get("status") or shadow.get("state") or "unknown",
                "completed_at": shadow.get("completed_at"),
            },
            "data_status": {
                "code": data_status_code,
                "runtime_eligible_metric_count": runtime_eligible_count,
                "runtime_stale_metric_count": len(runtime_stale),
                "checked_at": _iso_now(now),
            },
            "coverage_ratio": publication.get("coverage_ratio", 0),
            "eligible_metric_count": publication.get("eligible_metric_count", 0),
            "total_metric_count": publication.get("total_metric_count", len(metric_views)),
            "unavailable": unavailable,
            "nonfresh": nonfresh,
            "runtime_stale": runtime_stale,
            "warnings": publication.get("warnings", []),
            "shadow_cycle": shadow,
            "soak": health,
            "agent_soak": agent_health,
        },
        "proxy": proxy,
        "funding_rates": funding_rates,
        "treasury_curve": treasury_curve,
        "market_expectations": market_expectations,
        "event_calendar": event_calendar,
        "derived_metrics": derived_metrics,
        "agent_analysis": agent_analysis,
        "stablecoin_liquidity": stablecoin_liquidity,
        "crypto_etf": crypto_etf,
        "crypto_derivatives": crypto_derivatives,
        "cross_asset": cross_asset,
        "yen_carry": yen_carry,
        "energy": energy,
        "coinbase_premium": coinbase_premium,
        "layers": layers,
        "metrics": all_metrics,
        "sources": [
            *_source_views(snapshot, source_list, health),
            _stablecoin_source_view(stablecoin_liquidity),
            _crypto_etf_source_view(crypto_etf),
            _crypto_derivatives_source_view(crypto_derivatives),
            *_cross_asset_source_views(cross_asset),
            *_yen_carry_source_views(yen_carry),
            *_energy_source_views(energy),
            *coinbase_premium.get("sources", []),
        ],
        "glossary": GLOSSARY,
        "methodology": {
            "fact_label": "官方数据",
            "calculation_label": "确定性计算",
            "missing_value_semantics": snapshot.get(
                "missing_value_semantics", "null means unavailable; it never means zero"
            ),
            "agent_analysis": {
                "state": agent_analysis["state"],
                "message": agent_analysis["message"],
            },
        },
    }


def _build_series(root: Path, metric_id: str, range_id: str = "3m") -> dict[str, Any]:
    root = root.resolve()
    if metric_id in PREMIUM_METRICS:
        return premium_history(root, metric_id, range_id)
    cross_asset_series_ids = {"cross_asset_broad_dollar_btc"}
    energy_chart_ids = {"energy_price_comparison"}
    yen_carry_chart_ids = {
        "yen_carry_fx_volatility",
        "yen_carry_rate_spreads",
        "yen_carry_positioning",
        "yen_carry_risk_sync",
    }
    if metric_id not in {
        *METRICS,
        "net_liquidity_proxy",
        *cross_asset_series_ids,
        *energy_chart_ids,
        *yen_carry_chart_ids,
    }:
        raise ValueError("unknown metric_id")
    allowed_ranges = {*RANGE_DAYS, "all"}
    if metric_id.startswith("etf_"):
        allowed_ranges.update(ETF_SESSION_RANGES)
    if range_id not in allowed_ranges:
        raise ValueError("unknown range")
    snapshot = _load_json(root / "data" / "snapshots" / "latest.json")
    if metric_id.startswith("energy_"):
        channel = load_energy_payload(root)
        history = load_energy_history(root)
        raw = history.get("series", {}) if isinstance(history.get("series"), dict) else {}
        derived = history.get("derived", {}) if isinstance(history.get("derived"), dict) else {}
        source_map = {
            "energy_wti_spot": (raw, "wti_spot"),
            "energy_brent_spot": (raw, "brent_spot"),
            "energy_brent_wti_spread": (derived, "brent_wti_spread"),
            "energy_commercial_crude_stocks": (raw, "commercial_crude_stocks"),
            "energy_cushing_crude_stocks": (raw, "cushing_crude_stocks"),
            "energy_spr_stocks": (raw, "spr_stocks"),
            "energy_gasoline_product_supplied": (raw, "gasoline_product_supplied"),
        }
        if metric_id == "energy_price_comparison":
            wti = {str(item.get("observed_at")): item.get("value") for item in raw.get("wti_spot", []) if isinstance(item, dict) and item.get("observed_at")}
            brent = {str(item.get("observed_at")): item.get("value") for item in raw.get("brent_spot", []) if isinstance(item, dict) and item.get("observed_at")}
            points = [{"observed_at": key, "wti": wti[key], "brent": brent[key]} for key in sorted(set(wti) & set(brent))]
            label, unit = "WTI 与 Brent 原油价格", "usd_per_barrel"
            source_id, source_name, source_url = "fred_eia_oil_spot", "FRED / EIA 原油现货价", "https://fred.stlouisfed.org/"
        else:
            container, key = source_map[metric_id]
            points = list(container.get(key, []))
            metric = channel.get("metrics", {}).get(metric_id, {})
            label = METRICS.get(metric_id, {}).get("label", metric_id)
            unit = metric.get("unit")
            source_id = metric.get("source_id")
            source_name = metric.get("source_name")
            source_url = metric.get("source_url")
        points = [item for item in points if isinstance(item, dict) and item.get("observed_at")]
        if range_id != "all" and points:
            cutoff = _parse_date(points[-1]["observed_at"]) - timedelta(days=RANGE_DAYS[range_id])
            points = [item for item in points if _parse_date(item["observed_at"]) >= cutoff]
        return {
            "metric_id": metric_id,
            "label": label,
            "range": range_id,
            "source_id": source_id,
            "source_name": source_name,
            "source_url": source_url,
            "unit": unit,
            "points": points,
            "revisions": history.get("revisions", [])[-20:],
        }
    if metric_id.startswith("yen_carry_"):
        channel = load_yen_carry_payload(root)
        history = load_yen_carry_history(root)
        raw = history.get("series", {}) if isinstance(history.get("series"), dict) else {}
        derived = history.get("derived", {}) if isinstance(history.get("derived"), dict) else {}

        if metric_id == "yen_carry_fx_volatility":
            fx = {
                str(item.get("observed_at")): item.get("value")
                for item in raw.get("usd_jpy", [])
                if isinstance(item, dict) and item.get("observed_at")
            }
            volatility = {
                str(item.get("observed_at")): item.get("value")
                for item in derived.get("realized_volatility_20d", [])
                if isinstance(item, dict) and item.get("observed_at")
            }
            points = [
                {
                    "observed_at": observed_at,
                    "usd_jpy": fx[observed_at],
                    "realized_volatility_20d": volatility[observed_at],
                }
                for observed_at in sorted(set(fx) & set(volatility))
            ]
            label, unit = "美元兑日元与汇率波动", "multi_series"
        elif metric_id == "yen_carry_rate_spreads":
            combined: dict[str, dict[str, Any]] = {}
            for item in derived.get("short_rate_spread", []):
                if isinstance(item, dict) and item.get("observed_at"):
                    combined.setdefault(str(item["observed_at"]), {"observed_at": item["observed_at"]})["short_rate_spread"] = item.get("value")
            for item in derived.get("two_year_rate_spread", []):
                if isinstance(item, dict) and item.get("observed_at"):
                    combined.setdefault(str(item["observed_at"]), {"observed_at": item["observed_at"]})["two_year_rate_spread"] = item.get("value")
            points = [combined[key] for key in sorted(combined)]
            label, unit = "美日利差", "percentage_points"
        elif metric_id == "yen_carry_positioning":
            points = list(raw.get("cftc_leveraged_net_short", []))
            label, unit = "杠杆基金日元净空仓", "contracts"
        elif metric_id == "yen_carry_risk_sync":
            points = list(derived.get("risk_sync", []))
            label, unit = "日元、BTC 与标普 500 同步变化", "normalized_index"
        else:
            source_map = {
                "yen_carry_usd_jpy": (raw, "usd_jpy"),
                "yen_carry_jpy_appreciation_5d": (derived, "jpy_appreciation_5d"),
                "yen_carry_short_rate_spread": (derived, "short_rate_spread"),
                "yen_carry_2y_rate_spread": (derived, "two_year_rate_spread"),
                "yen_carry_realized_volatility_20d": (derived, "realized_volatility_20d"),
                "yen_carry_cftc_leveraged_net_short": (raw, "cftc_leveraged_net_short"),
                "yen_carry_fx_swap_turnover": (raw, "fx_swap_turnover"),
                "yen_carry_carry_to_risk": (derived, "carry_to_risk"),
            }
            container, key = source_map[metric_id]
            points = list(container.get(key, []))
            metric = channel.get("metrics", {}).get(metric_id, {})
            label = METRICS.get(metric_id, {}).get("label", metric_id)
            unit = metric.get("unit")

        points = [
            item for item in points
            if isinstance(item, dict) and item.get("observed_at")
        ]
        if range_id != "all" and points:
            cutoff = _parse_date(points[-1]["observed_at"]) - timedelta(
                days=RANGE_DAYS[range_id]
            )
            points = [
                item for item in points
                if _parse_date(item["observed_at"]) >= cutoff
            ]
        metric = channel.get("metrics", {}).get(metric_id, {})
        return {
            "metric_id": metric_id,
            "label": label,
            "range": range_id,
            "source_id": metric.get("source_id", "yen_carry_aligned"),
            "source_name": metric.get("source_name", "官方来源按共同观察日计算"),
            "source_url": metric.get("source_url"),
            "unit": unit,
            "points": points,
            "revisions": history.get("revisions", [])[-20:],
        }
    if metric_id.startswith("cross_asset_"):
        channel = load_cross_asset_payload(root)
        history = load_cross_asset_history(root)
        comparison_map = {
            "cross_asset_btc_spx_ratio": "btc_spx",
            "cross_asset_btc_gold_ratio": "btc_gold",
            "cross_asset_broad_dollar_btc": "broad_dollar_btc",
        }
        comparison_id = comparison_map.get(metric_id)
        if comparison_id:
            points = [
                item
                for item in history.get("comparisons", {}).get(comparison_id, [])
                if isinstance(item, dict) and item.get("observed_at")
            ]
            if range_id != "all" and points:
                cutoff = _parse_date(points[-1]["observed_at"]) - timedelta(
                    days=RANGE_DAYS[range_id]
                )
                points = [
                    item
                    for item in points
                    if _parse_date(item["observed_at"]) >= cutoff
                ]
            metric = channel.get("metrics", {}).get(metric_id, {})
            labels = {
                "cross_asset_broad_dollar_btc": "BTC 与广义美元相对走势",
            }
            return {
                "metric_id": metric_id,
                "label": labels.get(metric_id, METRICS.get(metric_id, {}).get("label", metric_id)),
                "range": range_id,
                "source_id": metric.get("source_id", "cross_asset_aligned"),
                "source_name": metric.get("source_name", "按共同观察日对齐"),
                "source_url": metric.get("source_url"),
                "unit": metric.get("unit", "normalized_index"),
                "points": points,
                "revisions": history.get("revisions", [])[-20:],
            }
        metric = channel.get("metrics", {}).get(metric_id)
        if not isinstance(metric, dict):
            raise ValueError("cross-asset metric is unavailable")
        return {
            "metric_id": metric_id,
            "label": METRICS[metric_id]["label"],
            "range": range_id,
            "source_id": metric.get("source_id"),
            "source_name": metric.get("source_name"),
            "source_url": metric.get("source_url"),
            "unit": metric.get("unit"),
            "points": metric.get("sparkline", []),
            "revisions": [],
        }
    if metric_id.startswith("etf_"):
        channel = load_crypto_etf_payload(root)
        metric = channel.get("metrics", {}).get(metric_id)
        if not isinstance(metric, dict):
            raise ValueError("ETF metric is unavailable")
        points = [
            item
            for item in metric.get("sparkline", [])
            if isinstance(item, dict)
            and item.get("observed_at")
            and isinstance(item.get("value"), (int, float))
        ]
        if range_id in ETF_SESSION_RANGES:
            points = points[-ETF_SESSION_RANGES[range_id] :]
        elif range_id != "all" and points:
            cutoff = _parse_date(points[-1]["observed_at"]) - timedelta(
                days=RANGE_DAYS[range_id]
            )
            points = [
                item
                for item in points
                if _parse_date(item["observed_at"]) >= cutoff
            ]
        return {
            "metric_id": metric_id,
            "label": METRICS[metric_id]["label"],
            "range": range_id,
            "source_id": metric.get("source_id"),
            "source_name": metric.get("source_name"),
            "source_url": metric.get("source_url"),
            "unit": metric.get("unit"),
            "points": points,
            "revisions": [],
            "revision_count": channel.get("quality", {}).get("revision_count", 0),
        }
    if metric_id.startswith("derivatives_"):
        channel = load_crypto_derivatives_payload(root)
        metric = channel.get("metrics", {}).get(metric_id)
        if not isinstance(metric, dict):
            raise ValueError("derivatives metric is unavailable")
        points = [
            item
            for item in metric.get("sparkline", [])
            if isinstance(item, dict)
            and item.get("observed_at")
            and isinstance(item.get("value"), (int, float))
        ]
        if range_id != "all" and points:
            cutoff = _parse_date(points[-1]["observed_at"]) - timedelta(
                days=RANGE_DAYS[range_id]
            )
            points = [
                item
                for item in points
                if _parse_date(item["observed_at"]) >= cutoff
            ]
        return {
            "metric_id": metric_id,
            "label": METRICS[metric_id]["label"],
            "range": range_id,
            "source_id": metric.get("source_id"),
            "source_name": metric.get("source_name"),
            "source_url": metric.get("source_url"),
            "unit": metric.get("unit"),
            "points": points,
            "revisions": [],
        }
    if metric_id.startswith("stablecoin_"):
        stablecoin = load_stablecoin_payload(root)
        metric = stablecoin.get("metrics", {}).get(metric_id)
        if not isinstance(metric, dict):
            raise ValueError("stablecoin metric is unavailable")
        definition = METRICS.get(metric_id, {})
        metric = {
            **metric,
            "label": definition.get("label", metric_id),
            "short_label": definition.get(
                "short_label", definition.get("label", metric_id)
            ),
        }
        points = (
            stablecoin.get("history", [])
            if metric_id == "stablecoin_usd_supply"
            else metric.get("sparkline", [])
        )
        if not points:
            points = metric.get("sparkline", [])
        if range_id != "all" and points:
            latest_date = _parse_date(points[-1]["observed_at"])
            cutoff = latest_date - timedelta(days=RANGE_DAYS[range_id])
            points = [
                item
                for item in points
                if _parse_date(item["observed_at"]) >= cutoff
            ]
        return {
            "metric_id": metric_id,
            "label": metric.get("label", metric_id),
            "range": range_id,
            "source_id": metric.get("source_id"),
            "source_name": metric.get("source_name"),
            "source_url": metric.get("source_url"),
            "unit": metric.get("unit"),
            "points": points,
            "revisions": [],
        }
    if metric_id == "net_liquidity_proxy":
        with closing(_connect_readonly(root / "data" / "channel.sqlite3")) as connection:
            metric_views = {
                item_id: _metric_view(
                    item_id,
                    metric,
                    connection,
                    published_at=str(snapshot.get("completed_at") or "") or None,
                )
                for item_id, metric in snapshot.get("metrics", {}).items()
                if isinstance(metric, dict)
            }
            latest_date = metric_views.get("tga_daily", {}).get("observed_at")
            since = None
            if latest_date and range_id != "all":
                since = (
                    _parse_date(latest_date) - timedelta(days=RANGE_DAYS[range_id])
                ).isoformat()
            points = _proxy_history(
                connection,
                metric_views,
                since=since,
                published_at=str(snapshot.get("completed_at") or "") or None,
            )
        return {
            "metric_id": metric_id,
            "label": "流动性参考值",
            "range": range_id,
            "source_id": "derived_daily_proxy",
            "source_name": "每日 TGA、每日 RRP 与最近联储周值；仅展示可配对的日期",
            "methodology_version": "daily-tga-v1",
            "source_url": None,
            "unit": "usd_millions",
            "points": points,
            "revisions": [],
        }
    metric = snapshot.get("metrics", {}).get(metric_id)
    if not isinstance(metric, dict) or not metric.get("source_id"):
        raise ValueError("metric is unavailable in the formal snapshot")
    source_id = metric["source_id"]
    with closing(_connect_readonly(root / "data" / "channel.sqlite3")) as connection:
        snapshot_observed_at = metric.get("observed_at")
        since = None
        if snapshot_observed_at and range_id != "all":
            since = (
                _parse_date(str(snapshot_observed_at)) - timedelta(days=RANGE_DAYS[range_id])
            ).isoformat()
        points = _history_rows(
            connection,
            metric_id,
            source_id,
            since=since,
            until=str(snapshot_observed_at) if snapshot_observed_at else None,
            published_at=str(snapshot.get("completed_at") or "") or None,
        )
        revisions = connection.execute(
            """
            SELECT observed_at, old_value, new_value, detected_at
            FROM observation_revisions
            WHERE metric_id = ? AND source_id = ?
            ORDER BY detected_at DESC LIMIT 20
            """,
            (metric_id, source_id),
        ).fetchall()
    return {
        "metric_id": metric_id,
        "label": METRICS[metric_id]["label"],
        "range": range_id,
        "source_id": source_id,
        "source_name": metric.get("source_name"),
        "source_url": metric.get("source_url"),
        "unit": metric.get("unit"),
        "points": [
            {"observed_at": row["observed_at"], "value": row["value"]}
            for row in points
        ],
        "revisions": [dict(row) for row in revisions],
    }


def build_series(root: Path, metric_id: str, range_id: str = "3m") -> dict[str, Any]:
    root = root.resolve()
    payload = _build_series(root, metric_id, range_id)
    snapshot = _load_json(root / "data" / "snapshots" / "latest.json")
    return {
        **payload,
        "release_id": snapshot.get("run_id"),
        "snapshot_run_id": snapshot.get("run_id"),
    }
