"use strict";

const CACHE_KEY = "macro-liquidity-dashboard:v2:last-formal-snapshot";
const THEME_KEY = "macro-liquidity-theme";
const SCROLL_POSITIONS_KEY = "macro-liquidity-scroll-positions:v1";
const THEME_META_COLORS = { light: "#f2f7f4", dark: "#18211e" };
const VIEW_IDS = ["overview", "transmission", "ledger", "data"];
const RANGE_LABELS = { "1m": "1 月", "3m": "3 月", "1y": "1 年", "5y": "5 年", all: "全部" };
const RANGE_DAYS_CLIENT = { "1m": 31, "3m": 93, "1y": 366, "5y": 1827 };
const ETF_RANGE_LABELS = { "5d": "5 日", "20d": "20 日", "3m": "3 月", "1y": "1 年", all: "全部" };
const ETF_SESSION_RANGES = { "5d": 5, "20d": 20 };
const STABLECOIN_MODE_LABELS = { supply: "总供给", change: "区间累计增减" };
const CROSS_ASSET_LABELS = {
  btc_spx: "BTC / 美股",
  btc_gold: "BTC / 黄金",
  broad_dollar_btc: "美元 / BTC"
};
const YEN_CARRY_MODE_LABELS = {
  fx_volatility: "汇率波动",
  rate_spreads: "美日利差",
  positioning: "杠杆仓位",
  risk_sync: "风险同步"
};
const CRYPTO_TAB_LABELS = { stablecoins: "稳定币", etf: "ETF", premium: "Coinbase 溢价", derivatives: "衍生品" };
const DERIVATIVES_MODE_LABELS = {
  open_interest: "未平仓",
  funding_8h_equivalent: "8 小时费率",
  account_long_share: "多头账户",
  taker_buy_share_24h: "主动买入"
};
const CHANGE_LABELS = { since_previous_run: "上一轮后", latest_release: "最新一次", "1w": "1 周", "1m": "1 月", "3m": "3 月", "1y": "1 年" };
const LAYER_LABELS = {
  balance_sheet_liquidity: "账本水量",
  funding_and_rates: "融资与利率",
  dollar_and_financial_conditions: "美元与金融条件",
  risk_asset_transmission: "风险资产传导"
};
const MARKET_BIAS_LABELS = { tailwind: "偏顺风", headwind: "偏逆风", mixed: "混合", uncertain: "不确定" };
const CONTENT_BASIS_LABELS = {
  full_text: "已读正文",
  summary: "依据发布方摘要",
  official_schedule: "官方日程",
  title_only: "仅有标题，不作为主要依据",
  fetch_error: "正文未取到，不作为主要依据"
};
const GROUP_LABELS = {
  fed_balance_sheet: "联储",
  fiscal_cash: "财政",
  money_market: "货币市场",
  market_transmission: "市场传导",
  crypto_liquidity: "加密内部流动性",
  crypto_etf: "加密 ETF",
  crypto_derivatives: "加密衍生品",
  coinbase_premium: "Coinbase现货溢价",
  cross_asset: "跨资产相对强弱",
  yen_carry: "日元套息",
  energy: "油价与库存"
};
const STATUS_LABELS = {
  publish: "数据正常",
  publish_degraded: "部分数据缺失",
  block_analysis: "暂不新增分析",
  ready: "数据正常",
  degraded: "部分数据不可用",
  stale: "数据已过期"
};
const SOAK_STATUS_LABELS = {
  passed: "稳定性已通过",
  not_ready: "稳定性观察中"
};
const VIEW_LABELS = {
  overview: "晨报",
  transmission: "专题",
  ledger: "指标",
  data: "状态"
};
const QUALITY_LABELS = {
  fresh_network: "刚从来源更新",
  fresh_cache: "缓存仍在有效期",
  stale_fallback: "使用旧数据",
  stale_source: "数据已过期",
  unavailable: "不可用",
  data_conflict: "不同来源对不上",
  needs_review: "异常待复核"
};
const AUTHORITY_LABELS = {
  official_primary: "直接来自官方",
  trusted_sro: "行业自律组织官方数据",
  official_republisher: "官方数据转发站",
  official_redistributor: "官方数据转发站",
  trusted_aggregator: "可信行业聚合源（非官方）",
  trusted_specialist: "可信专业数据源（非官方）",
  official_primary_multi_source: "多家交易所官方接口",
  mixed_official_and_primary: "官方市场数据与官方统计组合",
  mixed_official_and_trusted_sro: "官方数据与行业自律组织数据"
};
const CADENCE_LABELS = {
  daily: "每天",
  business_daily: "每个工作日",
  calendar_daily: "每天",
  weekly: "每周",
  daily_observations_weekly_release: "每周一次，一次公布多天数据",
  us_trading_daily_t_plus_1: "美股交易日后更新",
  continuous_sampled_daily: "连续市场，每天取一次晨间快照",
  hourly_sampled_daily: "小时数据，每天07:30更新",
  us_market_close_daily: "每个美国市场收盘日"
};
const CALENDAR_STATUS_LABELS = {
  ready: "日历正常",
  degraded: "部分使用缓存",
  unavailable: "日历暂不可用"
};
const RELEASE_TYPE_LABELS = {
  employment_situation: "美国就业报告",
  cpi: "美国消费者通胀（CPI）",
  ppi: "美国生产者价格（PPI）",
  eia_weekly_petroleum_status_report: "EIA 周度石油报告"
};
const AGENT_STATE_LABELS = {
  ready: "本轮已完成",
  limited: "证据有限",
  pilot_ready: "已更新",
  pilot_limited: "证据有限",
  setup_pending: "等待接入",
  stale: "等待本轮分析",
  invalid: "校验未通过",
  blocked_by_data: "数据未通过检查"
};
const ASSESSMENT_LABELS = {
  easing: "环境偏松",
  tightening: "环境偏紧",
  mixed: "信号混合",
  uncertain: "暂时无法判断"
};
const CONFIDENCE_LABELS = { low: "低置信度", medium: "中等置信度", high: "高置信度" };
const CONTEXT_RELEVANCE_LABELS = {
  relevant: "和当前数据有关",
  watch: "后面要看",
  already_reflected: "可能已部分反映"
};

const state = {
  data: null,
  view: "overview",
  renderedViews: new Set(),
  ledgerFilter: "all",
  seriesCache: new Map(),
  seriesRequests: new WeakMap(),
  scrollPositions: loadScrollPositions(),
  stablecoinChart: { mode: "supply", range: "1y" },
  crossAsset: { comparison: "btc_spx", range: "1y" },
  yenCarry: { mode: "fx_volatility", range: "1y" },
  energy: { mode: "price", range: "1y" },
  cryptoMarket: {
    tab: "stablecoins",
    etfAsset: "BTC",
    etfRange: "20d",
    derivativesAsset: "BTC",
    derivativesMode: "open_interest",
    derivativesRange: "1m"
  },
  offline: false
};

function loadScrollPositions() {
  const empty = Object.fromEntries(VIEW_IDS.map((view) => [view, 0]));
  try {
    const stored = JSON.parse(sessionStorage.getItem(SCROLL_POSITIONS_KEY) || "null");
    if (!stored || typeof stored !== "object") return empty;
    VIEW_IDS.forEach((view) => {
      const value = Number(stored[view]);
      if (Number.isFinite(value) && value >= 0) empty[view] = value;
    });
  } catch {
    // The current session still works when storage is unavailable.
  }
  return empty;
}

function persistScrollPositions() {
  try {
    sessionStorage.setItem(SCROLL_POSITIONS_KEY, JSON.stringify(state.scrollPositions));
  } catch {
    // Private browsing may block storage; in-memory positions still work.
  }
}

function saveCurrentScrollPosition() {
  if (!VIEW_IDS.includes(state.view)) return;
  state.scrollPositions[state.view] = Math.max(0, window.scrollY || 0);
  persistScrollPositions();
}

function appUrl(path) {
  return new URL(String(path).replace(/^\/+/, ""), document.baseURI);
}

const elements = {
  refresh: document.querySelector("#refresh-button"),
  themeToggle: document.querySelector("#theme-toggle"),
  themeColor: document.querySelector("#theme-color"),
  compactStatus: document.querySelector("#compact-status"),
  brandDate: document.querySelector("#brand-date"),
  offlineBanner: document.querySelector("#offline-banner"),
  live: document.querySelector("#live-region")
};

function storedTheme() {
  try {
    const theme = localStorage.getItem(THEME_KEY);
    return theme === "light" || theme === "dark" ? theme : null;
  } catch {
    return null;
  }
}

function systemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme, persist = false) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = nextTheme;
  document.documentElement.style.colorScheme = nextTheme;
  if (elements.themeColor) elements.themeColor.content = THEME_META_COLORS[nextTheme];
  if (elements.themeToggle) {
    const targetLabel = nextTheme === "dark" ? "切换到日间模式" : "切换到夜间模式";
    elements.themeToggle.setAttribute("aria-label", targetLabel);
    elements.themeToggle.setAttribute("title", targetLabel);
    elements.themeToggle.setAttribute("aria-pressed", String(nextTheme === "dark"));
  }
  if (persist) {
    try {
      localStorage.setItem(THEME_KEY, nextTheme);
    } catch {
      // Storage may be unavailable in private browsing. The current page still switches.
    }
  }
}

function initializeTheme() {
  applyTheme(storedTheme() || document.documentElement.dataset.theme || systemTheme());
  elements.themeToggle?.addEventListener("click", () => {
    const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(nextTheme, true);
    elements.live.textContent = nextTheme === "dark" ? "已切换到夜间模式" : "已切换到日间模式";
  });
  const preference = window.matchMedia("(prefers-color-scheme: dark)");
  const followSystemTheme = (event) => {
    if (!storedTheme()) applyTheme(event.matches ? "dark" : "light");
  };
  if (preference.addEventListener) preference.addEventListener("change", followSystemTheme);
  else preference.addListener?.(followSystemTheme);
}

function escapeHTML(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url.href : "#";
  } catch {
    return "#";
  }
}

function roundForDisplay(value, digits = 2) {
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0
  }).format(value);
}

function numericOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function plainAgentText(value) {
  return String(value ?? "")
    .replaceAll("隔夜现金停车场（RRP）", "隔夜逆回购（RRP）停放资金")
    .replaceAll("隔夜现金停车场", "RRP 停放资金")
    .replaceAll("RRP 停车场现金", "RRP 停放资金")
    .replaceAll("RRP 现金", "RRP 停放资金")
    .replace(/\bfull_text\b/g, "已读正文")
    .replace(/\bsummary\b/g, "发布方摘要")
    .replace(/\btitle_only\b/g, "仅有标题")
    .replace(/\bfetch_error\b/g, "正文未取到")
    .replace(/(-?\d+\.\d{3,})(?=\s*万亿美元)/g, (match) => roundForDisplay(Number(match), 2))
    .replace(/(-?\d+\.\d{2,})(?=\s*亿美元)/g, (match) => roundForDisplay(Number(match), 1));
}

function plainChannelIssue(value) {
  const text = String(value ?? "").trim();
  const staleAccount = text.match(/^(?:okx 账户多空比:\s*)?OKX account ratio is stale at (.+)$/i);
  if (staleAccount) {
    return `OKX 多空账户比已过期，本轮未采用。最后时间：${formatDateTime(staleAccount[1])}`;
  }
  return plainAgentText(text)
    .replaceAll("account ratio", "账户多空比")
    .replaceAll("is stale at", "已过期，最后时间：");
}

function normalizeDashboardCopy(data) {
  if (!data || typeof data !== "object") return data;
  const normalizeMetric = (metric) => {
    if (metric?.metric_id !== "overnight_rrp") return;
    metric.label = "隔夜逆回购（RRP）停放资金";
    metric.short_label = "RRP 停放资金";
  };
  Object.values(data.metrics || {}).forEach(normalizeMetric);
  (data.layers || []).flatMap((layer) => layer.metrics || []).forEach(normalizeMetric);
  (data.proxy?.latest_release_contributions || []).forEach((item) => {
    if (item.id === "overnight_rrp") item.label = "RRP 停放资金";
  });
  (data.glossary || []).forEach((item) => {
    if (item.technical_term === "RRP" || item.term === "隔夜现金停车场") {
      item.term = "RRP 停放资金";
      item.technical_term = "隔夜逆回购（RRP）";
    }
  });
  return data;
}

function formatUsdMillions(value, signed = false) {
  if (!Number.isFinite(value)) return "不可用";
  const sign = signed ? (value > 0 ? "+" : value < 0 ? "−" : "") : value < 0 ? "−" : "";
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000) return `${sign}${roundForDisplay(absolute / 1_000_000, 2)} 万亿美元`;
  if (absolute >= 100) return `${sign}${roundForDisplay(absolute / 100, absolute >= 10_000 ? 0 : 1)} 亿美元`;
  return `${sign}${roundForDisplay(absolute, 1)} 百万美元`;
}

function formatUsd(value) {
  const numeric = numericOrNull(value);
  if (numeric === null) return "不可用";
  const sign = numeric < 0 ? "−" : "";
  const absolute = Math.abs(numeric);
  if (absolute >= 100_000_000) return `${sign}${roundForDisplay(absolute / 100_000_000, 2)} 亿美元`;
  if (absolute >= 10_000) return `${sign}${roundForDisplay(absolute / 10_000, 1)} 万美元`;
  if (absolute >= 1_000) return `${sign}${roundForDisplay(absolute / 1_000, 1)} 千美元`;
  return `${sign}${roundForDisplay(absolute, 0)} 美元`;
}

function formatMetricValue(metric, compact = false) {
  const value = numericOrNull(metric?.value);
  if (value === null) return "不可用";
  if (metric.unit === "usd_millions") return formatUsdMillions(value);
  if (metric.unit === "usd_billions") {
    const billions = Math.abs(value);
    const sign = value < 0 ? "−" : "";
    return `${sign}${roundForDisplay(billions * 10, compact ? 1 : 2)} 亿美元`;
  }
  if (metric.unit === "percent") return `${roundForDisplay(value, 3)}%`;
  if (metric.unit === "annualized_percent") return `${roundForDisplay(value, 2)}%`;
  if (metric.unit === "percentage_points") return `${roundForDisplay(value, 2)}%`;
  if (metric.unit === "basis_points") return `${roundForDisplay(value, 2)} 个基点`;
  if (metric.unit === "jpy_per_usd") return `${roundForDisplay(value, 2)} 日元`;
  if (metric.unit === "contracts") return `${roundForDisplay(value, 0)} 张`;
  if (metric.unit === "probability") return `${roundForDisplay(value * 100, 1)}%`;
  if (metric.unit === "gold_ounces") return `${roundForDisplay(value, 2)} 盎司`;
  if (metric.unit === "usd_per_barrel") return `${roundForDisplay(value, 2)} 美元/桶`;
  if (metric.unit === "thousand_barrels") return `${roundForDisplay(value / 1000, 2)} 百万桶`;
  if (metric.unit === "thousand_barrels_per_day") return `${roundForDisplay(value / 1000, 2)} 百万桶/日`;
  if (metric.unit === "correlation") return roundForDisplay(value, 2);
  if (metric.unit === "ratio") return roundForDisplay(value, 4);
  if (metric.unit === "index_2006_100" || metric.unit === "index") return roundForDisplay(value, 4);
  return roundForDisplay(value, 4);
}

function formatSignedPercent(value, digits = 2) {
  const numeric = numericOrNull(value);
  if (numeric === null) return "不可用";
  const sign = numeric > 0 ? "+" : numeric < 0 ? "−" : "";
  return `${sign}${roundForDisplay(Math.abs(numeric), digits)}%`;
}

function formatMetricDelta(metric) {
  const value = numericOrNull(metric?.week_change);
  if (value === null) return { text: "暂无周度可比", className: "delta-neutral" };
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  const absolute = Math.abs(value);
  let formatted;
  if (metric.unit === "usd_millions") formatted = formatUsdMillions(value, true);
  else if (metric.unit === "usd_billions") formatted = `${sign}${roundForDisplay(absolute * 10, 2)} 亿美元`;
  else if (metric.unit === "percent") formatted = `${sign}${roundForDisplay(absolute, 3)} 个百分点`;
  else formatted = `${sign}${roundForDisplay(absolute, 4)}`;
  return {
    text: `一周 ${formatted}`,
    className: "delta-neutral"
  };
}

function formatLatestMetricDelta(metric) {
  const value = numericOrNull(metric?.latest_change);
  const cadence = metric?.cadence;
  const prefix = cadence === "weekly" ? "较上次周数据" : "较上一条数据";
  return value === null ? `${prefix}：暂无可比` : `${prefix}：${formatChangeValue(metric, value)}`;
}

function formatDate(value) {
  if (!value) return "日期未知";
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return escapeHTML(value);
  return `${month}月${day}日`;
}

function formatChartDate(value, rangeId) {
  if (!value) return "日期未知";
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return value;
  return ["1y", "5y", "all"].includes(rangeId) ? `${year}/${month}/${day}` : `${month}月${day}日`;
}

function formatDateTime(value) {
  if (!value) return "时间未知";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return escapeHTML(value);
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(parsed);
}

function formatCadence(value) {
  return CADENCE_LABELS[value] || value || "未知";
}

function statusClass(code) {
  const displayCode = code === "ready"
    ? "publish"
    : code === "degraded"
      ? "publish_degraded"
      : code === "stale"
        ? "block_analysis"
        : code;
  return `status-${String(displayCode || "block_analysis").replaceAll(/[^a-z_]/g, "")}`;
}

function effectiveDataStatus(status) {
  return status?.data_status?.code || status?.code || "block_analysis";
}

function soakStatusClass(code) {
  if (code === "passed") return "status-publish";
  if (code === "not_ready") return "status-observing";
  return "status-block_analysis";
}

function qualityClass(code) {
  return `quality-${String(code || "unavailable").replaceAll(/[^a-z_]/g, "")}`;
}

function metricById(id) {
  return state.data?.metrics?.[id] || state.data?.derived_metrics?.[id] || null;
}

function displayMetricById(id) {
  if (id === "net_liquidity_proxy") return state.data?.proxy || null;
  if (id === "net_liquidity_proxy_weekly") {
    const proxy = state.data?.proxy;
    return proxy ? {
      ...proxy,
      id,
      label: "流动性参考值（日序列趋势）",
      short_label: "趋势参考值",
      value: proxy.trend_latest_value,
      observed_at: proxy.trend_latest_observed_at,
    } : null;
  }
  return metricById(id);
}

function formatChangeValue(metric, value) {
  const numeric = numericOrNull(value);
  if (numeric === null) return "暂无可比数据";
  const sign = numeric > 0 ? "+" : numeric < 0 ? "−" : "";
  const absolute = Math.abs(numeric);
  if (metric?.unit === "usd_millions") return formatUsdMillions(numeric, true);
  if (metric?.unit === "usd_billions") return `${sign}${roundForDisplay(absolute * 10, 2)} 亿美元`;
  if (metric?.unit === "percent") return `${sign}${roundForDisplay(absolute, 3)} 个百分点`;
  if (metric?.unit === "annualized_percent" || metric?.unit === "percentage_points") return `${sign}${roundForDisplay(absolute, 2)} 个百分点`;
  if (metric?.unit === "basis_points") return `${sign}${roundForDisplay(absolute, 2)} 个基点`;
  if (metric?.unit === "jpy_per_usd") return `${sign}${roundForDisplay(absolute, 2)} 日元`;
  if (metric?.unit === "contracts") return `${sign}${roundForDisplay(absolute, 0)} 张`;
  if (metric?.unit === "probability") return `${sign}${roundForDisplay(absolute * 100, 1)} 个百分点`;
  if (metric?.unit === "gold_ounces") return `${sign}${roundForDisplay(absolute, 2)} 盎司`;
  if (metric?.unit === "usd_per_barrel") return `${sign}${roundForDisplay(absolute, 2)} 美元/桶`;
  if (metric?.unit === "thousand_barrels") return `${sign}${roundForDisplay(absolute / 1000, 2)} 百万桶`;
  if (metric?.unit === "thousand_barrels_per_day") return `${sign}${roundForDisplay(absolute / 1000, 2)} 百万桶/日`;
  if (metric?.unit === "correlation") return `${sign}${roundForDisplay(absolute, 2)}`;
  return `${sign}${roundForDisplay(absolute, 4)}`;
}

function contributionValue(item) {
  return numericOrNull(item?.contribution_usd_millions ?? item?.value_usd_millions);
}

function balanceMovement(value) {
  const numeric = numericOrNull(value);
  if (numeric === null) return "变化不可用";
  if (numeric === 0) return "没有变化";
  return `${numeric > 0 ? "增加" : "减少"} ${formatUsdMillions(Math.abs(numeric))}`;
}

function contributionMovement(value) {
  const numeric = numericOrNull(value);
  if (numeric === null) return "对参考值的影响不可用";
  if (numeric === 0) return "没有改变参考值";
  return `让参考值${numeric > 0 ? "增加" : "减少"} ${formatUsdMillions(Math.abs(numeric))}`;
}

function plainMetricMovement(metric, change) {
  const numeric = numericOrNull(change);
  if (numeric === null) return "暂无可比数据";
  if (numeric === 0) return "没变";
  return `${numeric > 0 ? "增加" : "减少"} ${formatChangeValue(metric, Math.abs(numeric)).replace(/^\+/, "")}`;
}

function componentChangeRow(metric, label, changeLabel) {
  if (!metric) return "";
  const change = metric.latest_change;
  const currentDate = formatDate(metric.observed_at);
  const priorDate = metric.latest_prior_observed_at ? formatDate(metric.latest_prior_observed_at) : "无上期";
  return `
    <div class="component-change-row">
      <div class="component-change-name"><strong>${escapeHTML(label)}</strong><span>${escapeHTML(changeLabel === "日变化" ? "每日更新" : "每周更新")}</span></div>
      <span class="component-change-date">${escapeHTML(priorDate)} → ${escapeHTML(currentDate)}</span>
      <b>${escapeHTML(changeLabel)}：${escapeHTML(plainMetricMovement(metric, change))}</b>
    </div>`;
}

function evidenceText(data, evidence) {
  let metric;
  if (evidence.metric_id === "net_liquidity_proxy_latest_release") {
    metric = data.proxy ? {
      ...data.proxy,
      label: "流动性参考值（各项最新发布）",
      short_label: "最新参考值",
      value: evidence.value,
    } : null;
  } else if (evidence.metric_id === "net_liquidity_proxy_weekly") {
    metric = data.proxy ? {
      ...data.proxy,
      label: "流动性参考值（日序列趋势）",
      short_label: "趋势参考值",
      value: evidence.value,
    } : null;
  } else if (evidence.metric_id === "net_liquidity_proxy") {
    metric = data.proxy ? {...data.proxy, value: evidence.value} : null;
  } else {
    const sourceMetric = data.metrics?.[evidence.metric_id] || data.derived_metrics?.[evidence.metric_id];
    metric = sourceMetric ? {...sourceMetric, value: evidence.value} : null;
  }
  if (!metric) return evidence.metric_id || "未知指标";
  const date = evidence.observed_at ? ` · ${formatDate(evidence.observed_at)}` : "";
  const window = evidence.comparison_window;
  const change = window ? ` · ${CHANGE_LABELS[window] || window}变化 ${formatChangeValue(metric, evidence.change)}` : "";
  return `${metric.short_label || metric.label} ${formatMetricValue(metric, true)}${date}${change}`;
}

function analysisClaimList(data, items, emptyText) {
  if (!Array.isArray(items) || !items.length) return `<p class="agent-empty-copy">${escapeHTML(emptyText)}</p>`;
  return `<ul class="agent-claim-list">${items.map((item) => `
    <li>
      <strong>${escapeHTML(plainAgentText(item.claim || "未命名结论"))}</strong>
      <span>${(item.evidence || []).map((evidence) => evidenceLink(data, evidence.metric_id, evidenceText(data, evidence), evidence)).join("；")}</span>
    </li>`).join("")}</ul>`;
}

function dailyUpdateEvidence(data, dailyUpdate) {
  const items = Array.isArray(dailyUpdate?.evidence) ? dailyUpdate.evidence : [];
  if (!items.length) return `<p class="agent-empty-copy">没有新发布的官方数据。</p>`;
  return `<ul class="agent-daily-evidence">${items.map((evidence) => `<li>${evidenceLink(data, evidence.metric_id, evidenceText(data, evidence), evidence)}</li>`).join("")}</ul>`;
}

function evidenceLink(data, metricId, label, evidence = {}) {
  const resolvedId = metricId === "net_liquidity_proxy_latest_release" || metricId === "net_liquidity_proxy_weekly"
    ? "net_liquidity_proxy"
    : metricId;
  const analysisId = data.agent_analysis?.analysis_id || "";
  return `<a href="#ledger" data-evidence-metric="${escapeHTML(resolvedId || "")}" data-evidence-window="${escapeHTML(evidence.comparison_window || "")}" data-evidence-date="${escapeHTML(evidence.observed_at || "")}" data-evidence-analysis="${escapeHTML(analysisId)}">${escapeHTML(label)}</a>`;
}

function contextMetricById(data, id) {
  if (id === "net_liquidity_proxy" || id === "net_liquidity_proxy_latest_release") return data.proxy || null;
  if (id === "net_liquidity_proxy_weekly") {
    return data.proxy ? {
      ...data.proxy,
      label: "流动性参考值（日序列趋势）",
      value: data.proxy.trend_latest_value,
      observed_at: data.proxy.trend_latest_observed_at,
    } : null;
  }
  return data.metrics?.[id] || data.derived_metrics?.[id] || null;
}

function contextMetricLinks(data, item, eventMode) {
  const metrics = [...new Set(item.linked_metric_ids || [])]
    .map((id) => contextMetricById(data, id))
    .filter(Boolean)
    .slice(0, 4);
  if (!metrics.length) return "";
  return `<div class="context-metric-links"><span>${eventMode ? "公布前看" : "关联数据"}</span>${metrics.map((metric) => evidenceLink(data, metric.metric_id || metric.id, `${metric.short_label || metric.label} ${formatMetricValue(metric, true)}`)).join("")}</div>`;
}

function contextBasisLabel(item) {
  if (item.kind === "scheduled_event") return "官方日程";
  return CONTENT_BASIS_LABELS[item.content_basis] || item.content_basis || "内容状态未知";
}

function contextAssessmentRows(data, items, eventMode) {
  return `<ul class="agent-context-list">${items.map((item) => {
    const moment = eventMode ? item.starts_at : item.published_at;
    const timeLabel = eventMode ? `事件时间 ${formatDateTime(moment)}` : `发布 ${formatDateTime(moment)}`;
    const reference = eventMode && item.reference_period ? `<span>参考期 ${escapeHTML(plainReferencePeriod(item.reference_period))}</span>` : "";
    const sourceName = eventMode ? eventSourceLabel(item) : item.source_name || "来源未知";
    const explanation = eventMode
      ? `<p><strong>当前背景：</strong>${escapeHTML(item.reason)}</p><p><strong>可能影响：</strong>${escapeHTML(item.transmission || item.reason)}</p>`
      : `<p><strong>发生了什么：</strong>${escapeHTML(item.what_happened || item.reason)}</p><p><strong>怎么影响：</strong>${escapeHTML(item.transmission || item.reason)}</p><p><strong>为什么今天要看：</strong>${escapeHTML(item.reason)}</p>`;
    return `<li>
      <div><span class="context-relevance">${escapeHTML(CONTEXT_RELEVANCE_LABELS[item.relevance] || item.relevance)}</span><span>${escapeHTML(sourceName)} · ${escapeHTML(timeLabel)}</span>${reference}</div>
      <a href="${escapeHTML(safeUrl(item.url))}" target="_blank" rel="noreferrer">${escapeHTML(eventMode ? eventPlainTitle(item) : item.title || "未命名新闻")}</a>
      ${explanation}
      ${contextMetricLinks(data, item, eventMode)}
      <small>${escapeHTML(contextBasisLabel(item))}</small>
    </li>`;
  }).join("")}</ul>`;
}

function contextAssessmentSections(data, items) {
  if (!Array.isArray(items) || !items.length) {
    return `<p class="agent-empty-copy">这轮没有筛出足以改变判断的新闻或事件。</p>`;
  }
  const news = items.filter((item) => item.kind !== "scheduled_event");
  const events = items.filter((item) => item.kind === "scheduled_event");
  return `<div class="agent-context-groups">
    ${news.length ? `<section class="agent-context-group"><header><h3>过去 24 小时的相关新闻</h3><span>${news.length} 条</span></header><p>正文或发布方摘要经过筛选后，才会进入这里。</p>${contextAssessmentRows(data, news, false)}</section>` : ""}
    ${events.length ? `<section class="agent-context-group"><header><h3>未来需要留意的事件</h3><span>${events.length} 条</span></header><p>这些是官方时间窗，不代表结果；旁边列出公布前应观察的当前指标。</p>${contextAssessmentRows(data, events, true)}</section>` : ""}
  </div>`;
}

function contextAssessmentSummary(items) {
  const list = Array.isArray(items) ? items : [];
  const news = list.filter((item) => item.kind !== "scheduled_event").length;
  const events = list.length - news;
  return `相关新闻 ${news} 条 · 未来事件 ${events} 条`;
}

function layerAnalysis(data, items) {
  if (!Array.isArray(items) || !items.length) return "";
  return `<div class="agent-layer-list">${items.map((item) => `
    <div class="agent-layer-row">
      <div><strong>${escapeHTML(LAYER_LABELS[item.layer] || item.layer)}</strong><span>${escapeHTML(ASSESSMENT_LABELS[item.assessment] || item.assessment)}</span></div>
      <p>${escapeHTML(plainAgentText(item.conclusion))}</p>
    </div>`).join("")}</div>`;
}

function marketImplications(items) {
  const markets = [["equities", "股票"], ["crypto", "加密"]];
  return `<div class="agent-market-list">${markets.map(([id, label]) => {
    const item = items?.[id] || {};
    return `<div class="agent-market-row">
      <div><strong>${label}</strong><span>${escapeHTML(MARKET_BIAS_LABELS[item.bias] || item.bias || "不确定")}</span></div>
      <p>${escapeHTML(plainAgentText(item.conclusion || "证据不足。"))}</p>
      <small>${escapeHTML(plainAgentText(item.transmission || ""))}</small>
    </div>`;
  }).join("")}</div>`;
}

function renderAgentAnalysis(data) {
  const analysis = data.agent_analysis || data.methodology?.agent_analysis || {};
  const stateLabel = AGENT_STATE_LABELS[analysis.state] || "状态未知";
  if (!analysis.is_current) {
    return `
      <section class="dashboard-section agent-section" aria-labelledby="agent-title">
        <div class="section-heading">
          <div><p class="eyebrow">Agent 晨间分析</p><h2 id="agent-title">等待一份通过证据核对的分析</h2></div>
          <span class="agent-state agent-state-${escapeHTML(analysis.state || "setup_pending")}">${escapeHTML(stateLabel)}</span>
        </div>
        <div class="notice"><strong>数据和分析分开运行</strong><span>${escapeHTML(analysis.message || "Agent 分析暂时不可用，官方数据仍会正常更新。")}</span></div>
      </section>`;
  }

  const model = analysis.model || {};
  const dailyUpdate = analysis.daily_update || {};
  const counterSignal = analysis.contradictions?.[0]?.claim || "这轮没有观察到明显的反向信号。";
  const watches = Array.isArray(analysis.watch_items) && analysis.watch_items.length
    ? `<ul class="agent-watch-list">${analysis.watch_items.map((item) => `<li><strong>${escapeHTML(plainAgentText(item.trigger))}</strong><span>${escapeHTML(plainAgentText(item.why))}</span></li>`).join("")}</ul>`
    : `<p class="agent-empty-copy">今天没有新增观察条件。</p>`;
  const unknowns = Array.isArray(analysis.unknowns) && analysis.unknowns.length
    ? `<ul class="agent-unknown-list">${analysis.unknowns.map((item) => `<li>${escapeHTML(plainAgentText(item))}</li>`).join("")}</ul>`
    : "";
  return `
    <section class="dashboard-section agent-section" aria-labelledby="agent-title">
      <div class="section-heading">
        <div><p class="eyebrow">Agent 晨间分析 · 不是买卖指令</p><h2 id="agent-title">${escapeHTML(analysis.headline)}</h2></div>
        <span class="agent-state agent-state-${escapeHTML(analysis.state)}">${escapeHTML(stateLabel)}</span>
      </div>
      <div class="agent-summary">
        <div class="agent-assessment"><strong>${escapeHTML(ASSESSMENT_LABELS[analysis.overall_assessment] || analysis.overall_assessment)}</strong><span>${escapeHTML(CONFIDENCE_LABELS[analysis.confidence] || analysis.confidence)}</span></div>
        <p>${escapeHTML(plainAgentText(analysis.summary))}</p>
      </div>
      <div class="agent-daily-update daily-${escapeHTML(dailyUpdate.status || "comparison_unavailable")}">
        <div><span>和上一轮相比</span><strong>${escapeHTML(dailyUpdate.headline || "暂时无法对比")}</strong></div>
        <p>${escapeHTML(plainAgentText(dailyUpdate.summary || "这一轮没有可用的对比结果。"))}</p>
        <small>${escapeHTML(plainAgentText(dailyUpdate.market_expectation_note || "市场预期暂无新变化。"))}</small>
      </div>
      <div class="agent-key-points">
        <div><span>最重要影响</span><p>${escapeHTML(plainAgentText(analysis.market_bottom_line || analysis.summary || "证据不足。"))}</p></div>
        <div><span>反向信号</span><p>${escapeHTML(plainAgentText(counterSignal))}</p></div>
      </div>
      <div class="agent-detail-stack">
        <details class="agent-detail-block">
          <summary>完整分析层次</summary>
          <div class="agent-full-analysis">
            ${layerAnalysis(data, analysis.layer_analysis)}
            ${marketImplications(analysis.market_implications)}
          </div>
        </details>
        <details class="agent-detail-block">
          <summary>为什么得出这个判断</summary>
          <div class="agent-evidence-groups">
            <div><h3>今天更新的数据</h3>${dailyUpdateEvidence(data, dailyUpdate)}</div>
            <div><h3>仍在影响判断的背景</h3>${analysisClaimList(data, analysis.drivers, "没有足够证据列出主要背景。")}</div>
            <div><h3>与主判断相反的信号</h3>${analysisClaimList(data, analysis.contradictions, "这轮没有明显的反向信号。")}</div>
          </div>
        </details>
        <details class="agent-detail-block">
          <summary>新闻与未来事件 <span>${escapeHTML(contextAssessmentSummary(analysis.context_assessments))}</span></summary>
          <p class="agent-screening-note">${escapeHTML(plainAgentText(analysis.context_screening_note || "未提供筛选说明。"))}</p>
          ${contextAssessmentSections(data, analysis.context_assessments)}
        </details>
        <details class="agent-detail-block">
          <summary>接下来看什么</summary>
          <h3>观察条件</h3>${watches}
          ${unknowns ? `<h3>还不能确定</h3>${unknowns}` : ""}
          <p class="agent-data-note">${escapeHTML(plainAgentText(analysis.data_quality_note))}</p>
        </details>
      </div>
      <footer class="agent-meta"><span>${escapeHTML(`${model.id || "未知模型"} · ${formatDateTime(analysis.generated_at)}`)}</span></footer>
    </section>`;
}

function statusNotice(data) {
  const runtimeCode = effectiveDataStatus(data.status);
  if (runtimeCode === "stale") {
    const stale = (data.status.runtime_stale || []).map((item) => item.label).join("、");
    return `<div class="notice notice-error"><strong>当前数据已经过期</strong><span>${escapeHTML(stale || "关键指标")} 超过了允许的更新时间。网页仍可浏览，但不会把旧数据当成今天的新信号，也不会生成新的 Agent 判断。</span></div>`;
  }
  const code = data.status.code;
  if (code === "publish") return "";
  const missing = data.status.unavailable.map((item) => item.label).join("、");
  if (code === "publish_degraded") {
    return `<div class="notice notice-warning"><strong>有少量数据暂时缺失</strong><span>缺少 ${escapeHTML(missing || "少量非关键指标")}。其他数据通过了检查，页面会继续更新。</span></div>`;
  }
  return `<div class="notice notice-error"><strong>这次先不生成新判断</strong><span>关键数据失效或不同来源对不上。页面只展示上一份通过检查的数据，不把缺失值当成零。</span></div>`;
}

function eventPlainTitle(event) {
  if (RELEASE_TYPE_LABELS[event?.release_type]) return RELEASE_TYPE_LABELS[event.release_type];
  const title = String(event?.title || "");
  if (title.includes("U.S. International Trade in Goods and Services")) return "美国贸易收支";
  if (title.includes("Personal Income and Outlays")) return "美国个人收入与支出";
  if (title.startsWith("GDP")) return "美国 GDP、企业利润等数据";
  if (title.includes("FOMC")) return "美联储议息会议";
  const auction = title.match(/美国财政部\s+(.+?)\s+国债拍卖/);
  if (auction) {
    const tenor = auction[1]
      .replace("10-Year TIPS", "10 年期抗通胀")
      .replace("30-Year", "30 年期")
      .replace("20-Year", "20 年期")
      .replace("10-Year", "10 年期");
    return `美国财政部 ${tenor}国债拍卖`;
  }
  return title || "关键宏观事件";
}

function plainReferencePeriod(value) {
  const months = {
    January: "1月", February: "2月", March: "3月", April: "4月",
    May: "5月", June: "6月", July: "7月", August: "8月",
    September: "9月", October: "10月", November: "11月", December: "12月",
  };
  const match = String(value || "").match(/^([A-Za-z]+)\s+(\d{4})$/);
  return match && months[match[1]] ? `${match[2]}年${months[match[1]]}` : String(value || "");
}

function eventSourceLabel(event) {
  const labels = {
    bls_release_calendar: "美国劳工统计局",
    bea_release_schedule: "美国经济分析局",
    fomc_calendar: "美联储",
    treasury_auction_schedule: "美国财政部",
  };
  return labels[event?.source_id] || event?.source_name || "官方日程";
}

function eventCountdown(value) {
  const target = new Date(value);
  if (Number.isNaN(target.valueOf())) return "时间待确认";
  const hours = (target.valueOf() - Date.now()) / 3_600_000;
  if (hours < 0) return "已经开始";
  if (hours < 24) return `${Math.max(1, Math.ceil(hours))} 小时后`;
  return `${Math.ceil(hours / 24)} 天后`;
}

function calendarDeliveryLabel(bls) {
  const status = bls?.delivery_status;
  if (status === "fresh_official") return "BLS 官方直连";
  if (status === "verified_cache") return `BLS 已校验缓存${Number.isFinite(Number(bls.cache_age_days)) ? `，${Number(bls.cache_age_days)} 天前核验` : ""}`;
  if (status === "stale_verified_cache") return `BLS 较旧缓存${Number.isFinite(Number(bls.cache_age_days)) ? `，${Number(bls.cache_age_days)} 天前核验` : ""}`;
  if (status === "expired") return "BLS 缓存已过期";
  return "BLS 日历暂不可用";
}

function renderEventCalendar(data) {
  const calendar = data.event_calendar || {};
  const status = CALENDAR_STATUS_LABELS[calendar.status] ? calendar.status : "unavailable";
  const next = calendar.next_event;
  const upcoming = (calendar.events || []).slice(0, 6);
  const summaryTitle = next ? eventPlainTitle(next) : "暂时没有可确认的关键日程";
  const summaryTime = next
    ? `${formatDateTime(next.starts_at)}，${eventCountdown(next.starts_at)}`
    : "等待下一轮日历更新";
  const sourceLine = calendarDeliveryLabel(calendar.bls);
  const eventRows = upcoming.length
    ? `<ol class="event-calendar-list">${upcoming.map((event) => `
        <li>
          <time datetime="${escapeHTML(event.starts_at || "")}">${escapeHTML(formatDateTime(event.starts_at))}</time>
          <span><strong>${escapeHTML(eventPlainTitle(event))}</strong><small>${escapeHTML(event.reference_period ? `对应 ${plainReferencePeriod(event.reference_period)}` : eventSourceLabel(event))}</small></span>
          <a href="${escapeHTML(safeUrl(event.url))}" target="_blank" rel="noreferrer" aria-label="查看${escapeHTML(eventPlainTitle(event))}的官方来源">来源</a>
        </li>`).join("")}</ol>`
    : `<p class="event-calendar-empty">当前没有通过检查的未来事件，Agent 不会自行补写日期。</p>`;
  return `
    <details class="event-calendar-strip calendar-${escapeHTML(status)}">
      <summary>
        <span class="calendar-state"><i aria-hidden="true"></i>${escapeHTML(CALENDAR_STATUS_LABELS[status])}</span>
        <span class="calendar-next"><small>下一项关键日程</small><strong>${escapeHTML(summaryTitle)}</strong></span>
        <span class="calendar-when">${escapeHTML(summaryTime)}</span>
        <span class="disclosure-caret" aria-hidden="true">›</span>
      </summary>
      <div class="event-calendar-detail">
        <div class="event-calendar-meta"><strong>${escapeHTML(calendar.message || "未来事件日历状态未知")}</strong><span>${escapeHTML(sourceLine)}。事件只提示波动时间窗，不预测结果。</span></div>
        ${eventRows}
      </div>
    </details>`;
}

function renderOverview(data) {
  const proxy = data.proxy;
  const status = data.status;
  const currentStatusCode = effectiveDataStatus(status);
  const trendChanges = proxy.trend_changes || {};
  const weeklyChange = numericOrNull(trendChanges["1w"]?.change);
  const latestReleaseChange = numericOrNull(proxy.latest_release_change);
  const observationCurrent = proxy.available_for_analysis === true;
  const headlineChange = observationCurrent ? latestReleaseChange : null;
  const direction = headlineChange === null ? "unavailable" : headlineChange > 0 ? "improving" : headlineChange < 0 ? "tightening" : "flat";
  const directionClass = `direction-${direction}`;
  const currentProxyValue = numericOrNull(proxy.value);
  const currentValue = currentProxyValue === null ? "不可用" : formatUsdMillions(currentProxyValue);
  const changeValue = headlineChange === null ? "无法计算" : formatUsdMillions(headlineChange, true);
  const overviewHeadline = !observationCurrent
    ? `正在查看 ${formatDate(proxy.observed_at)} 的上次有效快照`
    : latestReleaseChange === null
    ? "最新变化还无法合计"
    : latestReleaseChange > 0 && weeklyChange !== null && weeklyChange < 0
      ? "最新数据回流，但近一周仍在减少"
      : latestReleaseChange < 0 && weeklyChange !== null && weeklyChange > 0
        ? "最新数据抽水，但近一周仍在增加"
        : latestReleaseChange > 0
          ? "最新数据合计，资金水量增加"
          : latestReleaseChange < 0
            ? "最新数据合计，资金水量减少"
            : "最新数据合计，资金水量没变";
  const trendCards = ["1m", "3m", "1y"].map((windowId) => {
    const item = trendChanges[windowId] || {};
    const numeric = numericOrNull(item.change);
    const className = numeric !== null && numeric > 0 ? "delta-positive" : numeric !== null && numeric < 0 ? "delta-negative" : "delta-neutral";
    return `
      <div class="trend-stat">
        <span>比 ${escapeHTML(CHANGE_LABELS[windowId])}前</span>
        <strong class="${className}">${escapeHTML(formatChangeValue(proxy, item.change))}</strong>
        <small>${item.prior_observed_at ? `起点 ${escapeHTML(formatDate(item.prior_observed_at))}` : "历史不足"}</small>
      </div>`;
  }).join("");

  const overviewContributions = proxy.latest_release_contributions || [];
  const maxDriver = Math.max(1, ...overviewContributions.map((item) => Math.abs(contributionValue(item) || 0)));
  const drivers = overviewContributions.length
    ? overviewContributions.map((item) => {
        const contribution = contributionValue(item) || 0;
        const width = Math.max(2, Math.abs(contribution) / maxDriver * 48);
        const x = contribution < 0 ? 50 - width : 50;
        return `
          <div class="driver-row">
            <div class="driver-label">
              <strong>${escapeHTML(item.label)}</strong>
              <span>账户本身：${escapeHTML(balanceMovement(item.raw_change_usd_millions))}</span>
            </div>
            <div class="driver-measure">
              <span class="driver-value ${contribution > 0 ? "delta-positive" : contribution < 0 ? "delta-negative" : "delta-neutral"}">对参考值 ${escapeHTML(formatUsdMillions(contribution, true))}</span>
              <svg class="driver-track" viewBox="0 0 100 10" preserveAspectRatio="none" aria-hidden="true">
                <rect class="driver-track-bg" x="0" y="0" width="100" height="10" rx="5"></rect>
                <line class="driver-axis" x1="50" y1="0" x2="50" y2="10"></line>
                <rect class="driver-bar ${escapeHTML(item.effect)}" x="${x.toFixed(2)}" y="0" width="${width.toFixed(2)}" height="10" rx="5"></rect>
              </svg>
            </div>
          </div>`;
      }).join("")
    : `<div class="notice"><strong>历史还不够</strong><span>三个分项还没有完整的一周前数据，所以这次不画原因条。</span></div>`;

  const signalConfig = [
    ["reserve_balances_weekly_average", "银行结账的钱", "准备金多时，银行间付款通常更顺。"],
    ["treasury_10y_real_yield", "安全资产的真实回报", "实际利率上升时，风险资产通常更有压力。"],
    ["broad_dollar_index", "美元整体强弱", "美元走强时，全球借美元和还美元债通常更吃力。"],
    ["nfci", "金融松紧温度计", "NFCI 越高通常越紧，越低通常越松。"]
  ];
  const signals = signalConfig.map(([metricId, plainName, note]) => {
    const metric = data.metrics[metricId];
    if (!metric) return "";
    const change3m = metric.changes?.["3m"]?.change;
    const numeric = numericOrNull(change3m);
    const magnitude = numeric !== null
      ? formatChangeValue(metric, Math.abs(numeric)).replace(/^\+/, "")
      : "";
    const movement = numeric !== null
      ? `比 3 个月前${numeric > 0 ? "高" : numeric < 0 ? "低" : "几乎不变"} ${escapeHTML(magnitude)}`
      : "3 个月变化暂时不可用";
    return `
      <article class="signal-row">
        <div class="signal-copy">
          <span>${escapeHTML(plainName)}</span>
          <strong>${escapeHTML(metric.short_label)} · ${escapeHTML(formatMetricValue(metric, true))}</strong>
          <p>${movement}。${escapeHTML(note)}</p>
        </div>
        <div class="mini-chart" data-mini-metric="${escapeHTML(metricId)}" aria-label="${escapeHTML(metric.short_label)}过去一年走势"></div>
      </article>`;
  }).join("");

  const layers = data.layers.map((layer, index) => {
    const visibleMetrics = layer.metrics.slice(0, 2);
    const metricLines = visibleMetrics.map((metric) => `${escapeHTML(metric.short_label)} ${escapeHTML(formatMetricValue(metric, true))}`);
    return `
      <a href="#transmission" class="group-${escapeHTML(layer.group_id)}">
        <span class="layer-index">${index + 1}</span>
        <span class="layer-copy">
          <strong>${escapeHTML(layer.label)}</strong>
          <span>${escapeHTML(layer.description)}</span>
        </span>
        <span class="layer-metrics">${metricLines.map((line) => `<span>${line}</span>`).join("")}</span>
      </a>`;
  }).join("");

  const glossary = (data.glossary || []).map((item) => `
    <details class="term-disclosure">
      <summary><strong>${escapeHTML(item.term)}</strong><span>准确名称：${escapeHTML(item.technical_term)}</span></summary>
      <p>${escapeHTML(item.plain)}</p>
    </details>`).join("");

  const latestRun = data.snapshot.completed_at;
  const runtimeEligibleCount = status.data_status?.runtime_eligible_metric_count ?? status.eligible_metric_count;
  const fedWeekly = data.metrics.fed_total_assets;
  const tgaDaily = data.metrics.tga_daily;
  const rrpDaily = data.metrics.overnight_rrp;
  const fundingSpread = data.funding_rates?.spreads?.spread_sofr_iorb;
  const curveSpread = data.treasury_curve?.spreads?.spread_10y_2y;
  const fedExpectation = data.market_expectations?.topics?.find((item) => item.topic_id === "fed_policy_distribution" && item.state === "ready");
  const fedHikeExpectation = data.market_expectations?.topics?.find((item) => item.topic_id === "fed_hike_distribution" && item.state === "ready");
  const fundingShort = data.funding_rates?.state === "pressure" ? "压力上升" : data.funding_rates?.state === "watch" ? "需要留意" : data.funding_rates?.state === "normal" ? "正常" : "数据不完整";
  const fundingValue = numericOrNull(fundingSpread?.value);
  const fundingDetail = fundingValue === null
    ? "SOFR 与准备金利息的差值不可用"
    : fundingValue === 0
      ? "SOFR 与准备金利息持平"
      : `SOFR 比准备金利息${fundingValue > 0 ? "高" : "低"} ${roundForDisplay(Math.abs(fundingValue), 2)} 个基点`;
  const curveValue = numericOrNull(curveSpread?.value);
  const curveCurrent = curveSpread?.available_for_analysis !== false && !["stale_source", "stale_fallback", "unavailable"].includes(curveSpread?.quality_status);
  const curveShort = curveValue === null
    ? "当前无法判断"
    : !curveCurrent
      ? "只有历史值"
      : curveValue < 0
        ? `倒挂 ${Number(curveSpread?.streak?.observations || 0)} 个有效日`
        : "当前未倒挂";
  const curveDetail = curveValue === null
    ? "10 年期与 2 年期收益率差不可用"
    : `10 年期收益率比 2 年期${curveValue >= 0 ? "高" : "低"} ${roundForDisplay(Math.abs(curveValue), 2)} 个基点`;
  const yenStates = data.yen_carry?.states || {};
  const yenPressureShort = yenStates.unwind_pressure?.label || "数据不完整";
  const yenIncentiveShort = yenStates.carry_incentive?.label || "套息动力未知";
  const yenAppreciation = numericOrNull(data.metrics?.yen_carry_jpy_appreciation_5d?.value);
  const usdJpy = numericOrNull(data.metrics?.yen_carry_usd_jpy?.value);
  const yenDetail = yenAppreciation === null || usdJpy === null
    ? "日元升值速度或汇率波动数据不可用"
    : `日元近 5 个交易日 ${formatSignedPercent(yenAppreciation)}；USD/JPY ${roundForDisplay(usdJpy, 2)}`;
  const wtiMetric = data.metrics?.energy_wti_spot;
  const wtiOneWeek = numericOrNull(wtiMetric?.changes?.["1w"]?.percent_change);
  const oilShort = !wtiMetric?.available_for_analysis ? "数据不完整" : wtiOneWeek === null ? "最新价可用" : Math.abs(wtiOneWeek) > 3 ? `油价一周${wtiOneWeek > 0 ? "上涨" : "下跌"}较明显` : "油价一周变化不大";
  const oilDetail = !wtiMetric?.available_for_analysis ? "WTI 或 Brent 本轮不可用" : `WTI ${formatMetricValue(wtiMetric, true)}；1 周 ${wtiOneWeek === null ? "暂无可比" : formatSignedPercent(wtiOneWeek)}`;
  const policyExpectationShort = (topic, action) => {
    if (!topic?.top_outcome) return `${action}：不可用`;
    const top = topic.top_outcome;
    const stale = ["stale", "unknown"].includes(topic.freshness_status) ? " · 数据较旧" : "";
    return `${top.display_label || top.label} · ${roundForDisplay(Number(top.probability) * 100, 1)}%${stale}`;
  };
  document.querySelector("#view-overview").innerHTML = `
    ${statusNotice(data)}
    <div class="morning-grid">
      <details class="trust-panel" aria-labelledby="trust-title">
        <summary id="trust-title">
          <span class="status-pill ${statusClass(currentStatusCode)}">${escapeHTML(STATUS_LABELS[currentStatusCode] || "状态未知")}</span>
          <span class="trust-summary-meta">${runtimeEligibleCount}/${status.total_metric_count} 项当前可用 · ${escapeHTML(formatDateTime(latestRun))} 更新</span>
          <span class="disclosure-caret" aria-hidden="true">›</span>
        </summary>
        <div class="trust-detail">
          <div class="trust-stats">
            <div class="trust-stat"><strong>${runtimeEligibleCount}/${status.total_metric_count}</strong><span>现在可用</span></div>
            <div class="trust-stat"><strong>${status.eligible_metric_count}/${status.total_metric_count}</strong><span>发布时通过</span></div>
            <div class="trust-stat"><strong>${roundForDisplay((status.coverage_ratio || 0) * 100, 0)}%</strong><span>数据完整度</span></div>
            <div class="trust-stat"><strong>${escapeHTML(formatDateTime(latestRun))}</strong><span>北京时间更新</span></div>
          </div>
          <div class="notice"><strong>为什么日期不一样</strong><span>各机构的发布时间不同。每条数据都保留自己的日期。</span></div>
        </div>
      </details>

      <section class="overview-story" aria-labelledby="overview-title">
        <h1 id="overview-title">${escapeHTML(overviewHeadline)}</h1>
        <div class="proxy-delta ${directionClass}">
          <strong>${escapeHTML(changeValue)}</strong>
          <span class="proxy-formula">${escapeHTML(proxy.latest_release_formula || `Δ${proxy.formula}`)}</span>
          <span class="proxy-period">${escapeHTML(proxy.latest_release_method || "各项按自己最近两次发布值计算。")}</span>
        </div>
      </section>

      <section class="trend-panel" aria-labelledby="trend-title">
        <div class="trend-panel-heading">
          <div><p class="eyebrow">先看走势</p><h2 id="trend-title">资金水量走势</h2></div>
          <div class="range-controls trend-range-controls" role="group" aria-label="选择流动性参考值的历史区间">
            ${["3m", "1y", "5y", "all"].map((id) => `<button class="trend-range-button range-button" type="button" data-range="${id}" aria-pressed="${id === "1y"}">${escapeHTML(RANGE_LABELS[id])}</button>`).join("")}
          </div>
        </div>
        <div class="chart-shell chart-shell-main" data-main-chart><div class="chart-state">正在准备一年走势</div></div>
        <div class="trend-stats">${trendCards}</div>
        <p class="chart-method">${escapeHTML(proxy.trend_method || "每日 TGA、RRP 与最近联储周值计算。")}</p>
        <p class="chart-method">${proxy.coverage?.first_observed_at ? `可用历史：${escapeHTML(formatChartDate(proxy.coverage.first_observed_at, "all"))} 至 ${escapeHTML(formatChartDate(proxy.coverage.last_observed_at, "all"))}，${proxy.coverage.point_count} 个数据日。更早区间暂无每日配对数据。` : "暂无完整的每日配对数据。"}</p>
      </section>

      <section class="overview-evidence" aria-label="公式组成项和计算说明">
        <div class="component-change-list" aria-label="公式组成项的最新变化">
          ${componentChangeRow(fedWeekly, "美联储总资产", "周变化")}
          ${componentChangeRow(tgaDaily, "财政部现金", "日变化")}
          ${componentChangeRow(rrpDaily, "RRP 停放资金", "日变化")}
        </div>
        <div class="proxy-current"><span>同日配对参考值 · ${escapeHTML(formatDate(proxy.observed_at))}</span><b>${escapeHTML(currentValue)}</b></div>
        <details class="plain-explainer"><summary>这个“参考值”到底是什么？</summary><p>它的准确名称是“${escapeHTML(proxy.technical_label || "净流动性代理值")}”。算法是：${escapeHTML(proxy.formula)}。它像一把方向尺，帮助看水是在变多还是变少，不是一个真实账户余额。</p></details>
      </section>

    </div>

    <a class="macro-status-strip" href="#transmission" aria-label="查看短端资金压力、收益率曲线、日元套息、油价和全年政策次数盘口">
      <span><small>短端融资</small><strong>${escapeHTML(fundingShort)}</strong><b>${escapeHTML(fundingDetail)}</b></span>
      <span><small>收益率曲线</small><strong>${escapeHTML(curveShort)}</strong><b>${escapeHTML(curveDetail)}</b></span>
      <span><small>日元套息</small><strong>${escapeHTML(yenPressureShort)}</strong><b>${escapeHTML(`${yenIncentiveShort}；${yenDetail}`)}</b></span>
      <span><small>油价与通胀</small><strong>${escapeHTML(oilShort)}</strong><b>${escapeHTML(oilDetail)}</b></span>
      <span class="macro-policy-status"><small>政策路径 · Polymarket</small><strong>全年次数盘口</strong><b class="policy-path-lines"><em>${escapeHTML(policyExpectationShort(fedExpectation, "降息"))}</em><em>${escapeHTML(policyExpectationShort(fedHikeExpectation, "加息"))}</em></b></span>
    </a>

    ${renderEventCalendar(data)}

    ${renderAgentAnalysis(data)}

    <section class="dashboard-section" aria-labelledby="signals-title">
      <div class="section-heading"><div><h2 id="signals-title">再用四条线交叉检查</h2><p>参考值只看联储、财政部和 RRP。下面四条线再检查银行结算、真实利率、美元和整体金融环境。</p></div></div>
      <div class="signal-list">${signals}</div>
    </section>

    <section class="dashboard-section" aria-labelledby="drivers-title">
      <div class="section-heading"><div><h2 id="drivers-title">最新变化从哪来</h2><p>向右是支持，向左是抽走。</p></div></div>
      <div class="driver-list">${drivers}</div>
      <p class="notice"><strong>这条线不能告诉你什么</strong><span>${escapeHTML(proxy.caveat)}</span></p>
    </section>

    <section class="dashboard-section" aria-labelledby="layers-title">
      <div class="section-heading"><div><h2 id="layers-title">这股水怎样走到市场</h2><p>先看联储和财政部，再看短期借钱市场，最后才看股票和加密。</p></div></div>
      <div class="layer-overview">${layers}</div>
    </section>

    <section class="dashboard-section" aria-labelledby="terms-title">
      <div class="section-heading"><div><h2 id="terms-title">专业词，先说人话</h2><p>点开就能看到一句白话解释，同时保留准确名称。</p></div></div>
      <div class="term-list">${glossary}</div>
    </section>`;

  bindOverviewInteractions();
}

function formatBp(value, signed = true) {
  const numeric = numericOrNull(value);
  if (numeric === null) return "不可用";
  const sign = signed ? (numeric > 0 ? "+" : numeric < 0 ? "−" : "") : "";
  return `${sign}${roundForDisplay(Math.abs(numeric), 2)} 个基点`;
}

function formatProbabilityChange(value) {
  const numeric = numericOrNull(value);
  if (numeric === null) return "暂无可比数据";
  const sign = numeric > 0 ? "+" : numeric < 0 ? "−" : "";
  return `${sign}${roundForDisplay(Math.abs(numeric) * 100, 1)} 个百分点`;
}

function genericFlowMetrics(metrics) {
  return metrics.map((metric) => {
    const week = formatMetricDelta(metric);
    const showWeek = metric.cadence !== "weekly";
    return `
      <div class="flow-metric">
        <div class="flow-metric-copy">
          <span class="flow-metric-kicker">${escapeHTML(metric.short_label)} · ${escapeHTML(formatCadence(metric.cadence))} · ${escapeHTML(formatDate(metric.observed_at))}</span>
          <strong>${escapeHTML(formatMetricValue(metric, true))}</strong>
          <span>${escapeHTML(formatLatestMetricDelta(metric))}${showWeek ? ` · ${escapeHTML(week.text)}` : ""}</span>
        </div>
        <div class="mini-chart flow-mini-chart" data-flow-mini-metric="${escapeHTML(metric.metric_id)}" aria-label="${escapeHTML(metric.short_label)}过去一个月走势"></div>
      </div>`;
  }).join("");
}

function fundingPanel(data) {
  const funding = data.funding_rates || {};
  const stateLabels = {
    normal: "暂未见压力",
    watch: "需要观察",
    pressure: "资金压力上升",
    unavailable: "数据不完整"
  };
  const levels = (funding.levels || []).map((metric) => `
    <div class="rate-level">
      <span>${escapeHTML(metric.short_label || metric.label)}</span>
      <strong>${escapeHTML(formatMetricValue(metric, true))}</strong>
      <small>${escapeHTML(formatDate(metric.observed_at))}</small>
    </div>`).join("");
  const primaryIds = ["spread_sofr_iorb", "spread_sofr_effr", "spread_effr_iorb", "spread_effr_on_rrp"];
  const spreads = primaryIds.map((id) => funding.spreads?.[id]).filter(Boolean).map((spread) => {
    const positive = numericOrNull(spread.value) > 0;
    const streak = spread.streak?.active ? `连续 ${spread.streak.observations} 个有效日为正` : "当前未持续为正";
    return `
      <div class="spread-row">
        <div class="spread-copy">
          <span>${escapeHTML(spread.label)}</span>
          <strong class="${positive ? "spread-alert" : ""}">${escapeHTML(formatBp(spread.value))}</strong>
          <small>${escapeHTML(formatDate(spread.observed_at))} · ${escapeHTML(streak)}</small>
        </div>
        <div class="mini-chart spread-mini-chart" data-derived-mini="${escapeHTML(spread.metric_id)}" aria-label="${escapeHTML(spread.label)}近一年走势"></div>
      </div>`;
  }).join("");
  return `
    <div class="special-analysis funding-analysis">
      <div class="analysis-status-row">
        <div><p class="eyebrow">短端资金压力</p><h3>${escapeHTML(funding.conclusion || "关键利差暂时不可用")}</h3></div>
        <span class="analysis-state state-${escapeHTML(funding.state || "unavailable")}">${escapeHTML(stateLabels[funding.state] || "状态未知")}</span>
      </div>
      <div class="rate-levels">${levels}</div>
      <div class="spread-list">${spreads}</div>
      <p class="reading-rule">${escapeHTML(funding.reading_rule || "")}</p>
    </div>`;
}

function curveChart(curve) {
  const latest = curve?.snapshots?.latest;
  const prior = curve?.snapshots?.["1w"];
  if (!latest?.values) return `<div class="chart-state">四个期限还没有同一天的数据</div>`;
  const ids = (curve.maturities || []).map((item) => item.metric_id);
  const labels = (curve.maturities || []).map((item) => item.label);
  const series = [latest, prior].filter((item) => item?.values);
  const values = series.flatMap((item) => ids.map((id) => numericOrNull(item.values[id])).filter((value) => value !== null));
  if (!values.length) return `<div class="chart-state">收益率曲线数据不足</div>`;
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  if (minimum === maximum) { minimum -= 0.1; maximum += 0.1; }
  const width = 360;
  const height = 190;
  const left = 34;
  const right = 16;
  const top = 20;
  const bottom = 34;
  const x = (index) => left + index * ((width - left - right) / Math.max(1, ids.length - 1));
  const y = (value) => top + (maximum - value) / (maximum - minimum) * (height - top - bottom);
  const pathFor = (snapshot) => ids.map((id, index) => `${index ? "L" : "M"}${x(index).toFixed(1)} ${y(Number(snapshot.values[id])).toFixed(1)}`).join(" ");
  const latestDots = ids.map((id, index) => `<circle class="curve-dot-latest" cx="${x(index).toFixed(1)}" cy="${y(Number(latest.values[id])).toFixed(1)}" r="3"></circle>`).join("");
  const priorDots = prior ? ids.map((id, index) => `<circle class="curve-dot-prior" cx="${x(index).toFixed(1)}" cy="${y(Number(prior.values[id])).toFixed(1)}" r="3"></circle>`).join("") : "";
  const xLabels = labels.map((label, index) => `<text x="${x(index).toFixed(1)}" y="${height - 8}" text-anchor="middle">${escapeHTML(label)}</text>`).join("");
  return `
    <div class="curve-legend"><span><i class="legend-latest"></i>${escapeHTML(formatDate(latest.observed_at))}</span>${prior ? `<span><i class="legend-prior"></i>${escapeHTML(formatDate(prior.observed_at))}</span>` : ""}</div>
    <svg class="curve-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="美债收益率曲线，最新数据和一周前比较">
      <line class="curve-grid" x1="${left}" y1="${top}" x2="${left}" y2="${height - bottom}"></line>
      <line class="curve-grid" x1="${left}" y1="${height - bottom}" x2="${width - right}" y2="${height - bottom}"></line>
      ${prior ? `<path class="curve-line curve-line-prior" d="${pathFor(prior)}"></path>` : ""}
      <path class="curve-line curve-line-latest" d="${pathFor(latest)}"></path>
      <g class="curve-dots curve-dots-prior">${priorDots}</g>
      <g class="curve-dots curve-dots-latest">${latestDots}</g>
      ${xLabels}
      <text class="curve-axis-label" x="2" y="${top + 4}">${escapeHTML(`${roundForDisplay(maximum, 2)}%`)}</text>
      <text class="curve-axis-label" x="2" y="${height - bottom + 4}">${escapeHTML(`${roundForDisplay(minimum, 2)}%`)}</text>
    </svg>`;
}

function bindCurveChartExplorer(container, curve) {
  const svg = container?.querySelector(".curve-svg");
  const latest = curve?.snapshots?.latest;
  const prior = curve?.snapshots?.["1w"];
  const maturities = curve?.maturities || [];
  if (!svg || !latest?.values || !maturities.length) return;
  const latestDots = [...svg.querySelectorAll(".curve-dot-latest")];
  const priorDots = [...svg.querySelectorAll(".curve-dot-prior")];
  const samples = maturities.map((maturity, index) => {
    const latestValue = numericOrNull(latest.values[maturity.metric_id]);
    const priorValue = numericOrNull(prior?.values?.[maturity.metric_id]);
    const values = [];
    if (latestValue !== null && latestDots[index]) values.push({
      label: formatDate(latest.observed_at),
      formatted: `${roundForDisplay(latestValue, 2)}%`,
      y: Number(latestDots[index].getAttribute("cy")),
      tone: 1
    });
    if (priorValue !== null && priorDots[index]) values.push({
      label: formatDate(prior.observed_at),
      formatted: `${roundForDisplay(priorValue, 2)}%`,
      y: Number(priorDots[index].getAttribute("cy")),
      tone: 2
    });
    return {
      heading: maturity.label,
      observed_at: latest.observed_at,
      x: Number(latestDots[index]?.getAttribute("cx")),
      values
    };
  });
  bindChartExplorer(container, samples, {plotTop: 20, plotBottom: 156, title: "美债收益率曲线"});
}

function treasuryCurvePanel(data) {
  const curve = data.treasury_curve || {};
  const spreadIds = ["spread_10y_2y", "spread_10y_3m", "spread_30y_10y"];
  const rows = spreadIds.map((id) => curve.spreads?.[id]).filter(Boolean).map((spread) => {
    const value = numericOrNull(spread.value);
    const isCurrent = spread.available_for_analysis !== false && !["stale_source", "stale_fallback", "unavailable"].includes(spread.quality_status);
    const inverted = value !== null && value < 0;
    const stateText = value === null
      ? "当前利差不可用，不判断是否倒挂"
      : !isCurrent
        ? `这是 ${formatDate(spread.observed_at)} 的历史值，不代表当前状态`
        : inverted && spread.streak?.active
          ? `已倒挂 ${spread.streak.observations} 个有效日 · 从 ${formatDate(spread.streak.start_date)} 开始`
          : inverted
            ? "当前倒挂，持续天数暂不可用"
            : "当前未倒挂";
    return `<div class="curve-spread-row"><span>${escapeHTML(spread.label)}</span><strong class="${isCurrent && inverted ? "spread-alert" : ""}">${value === null ? "不可用" : escapeHTML(formatBp(value))}</strong><small>${escapeHTML(stateText)}</small></div>`;
  }).join("");
  return `
    <div class="special-analysis curve-analysis">
      <div class="analysis-status-row"><div><p class="eyebrow">美债收益率曲线</p><h3>看短端、政策预期和长期定价怎样一起变化</h3></div></div>
      <div class="curve-chart-shell">${curveChart(curve)}</div>
      <div class="curve-spreads">${rows}</div>
      <p class="reading-rule">${escapeHTML(curve.reading_rule || "")}</p>
    </div>`;
}

function marketExpectationsPanel(data) {
  const expectations = data.market_expectations || {};
  let featuredHeadingAdded = false;
  const topicRows = (expectations.topics || []).filter((topic) => topic.state === "ready").map((topic) => {
    const featured = topic.selection_role === "featured";
    const sectionLead = featured && !featuredHeadingAdded
      ? `<div class="expectation-group-label"><strong>高成交宏观盘口</strong><span>仅展示未到期市场，按 24 小时成交额排序</span></div>`
      : "";
    if (featured) featuredHeadingAdded = true;
    const allOutcomes = topic.outcomes || [];
    const visibleCount = topic.presentation === "binary" ? 1 : 3;
    const outcomes = allOutcomes.slice(0, visibleCount);
    const extraOutcomes = topic.policy_action ? allOutcomes.slice(visibleCount) : [];
    const topOutcome = topic.top_outcome || outcomes[0] || {};
    const topLabel = topOutcome.display_label || topOutcome.label || "暂无结果";
    const summaryLead = topic.presentation === "multi_market"
      ? `关注盘口：${topLabel}`
      : topic.topic_id === "us_recession_probability"
        ? `“${topLabel}”的市场概率`
        : `最可能：${topLabel}`;
    const dailySummary = numericOrNull(topOutcome.change_1d) === null
      ? "当日暂无可比数据"
      : `当日 ${formatProbabilityChange(topOutcome.change_1d)}`;
    const activitySummary = featured ? ` · 24 小时成交 ${formatUsd(topic.volume_24h_usd)}` : "";
    const probabilityBar = (outcome) => `
      <div class="probability-row">
        <div><span>${escapeHTML(outcome.display_label || outcome.label)}</span><strong>${escapeHTML(`${roundForDisplay(Number(outcome.probability) * 100, 1)}%`)}</strong></div>
        <div class="probability-track"><i style="width:${Math.max(0, Math.min(100, Number(outcome.probability) * 100)).toFixed(1)}%"></i></div>
        <small>当日 ${escapeHTML(formatProbabilityChange(outcome.change_1d))} · 一周 ${escapeHTML(formatProbabilityChange(outcome.change_1w))} · 一月 ${escapeHTML(formatProbabilityChange(outcome.change_1m))}</small>
      </div>`;
    const bars = outcomes.map(probabilityBar).join("");
    const extraId = `expectation-extra-${topic.topic_id}`;
    const extraBars = extraOutcomes.length
      ? `<button class="expectation-more-button" type="button" data-expectation-toggle="${escapeHTML(extraId)}" aria-controls="${escapeHTML(extraId)}" aria-expanded="false">查看其余 ${extraOutcomes.length} 个结果</button><div class="expectation-extra" id="${escapeHTML(extraId)}" hidden>${extraOutcomes.map(probabilityBar).join("")}</div>`
      : "";
    const freshness = ["stale", "unknown"].includes(topic.freshness_status)
      ? "数据更新时间超过本看板门槛，只展示，不作为当前主要依据"
      : topic.quality === "liquid"
        ? "成交和深度达到本看板门槛"
        : "成交偏薄，只作低权重观察";
    const probabilitySum = numericOrNull(topic.probability_sum);
    const overround = numericOrNull(topic.overround_percentage_points);
    const sumDetail = probabilitySum === null
      ? ""
      : `<dt>原始盘口合计</dt><dd>${escapeHTML(`${roundForDisplay(probabilitySum * 100, 2)}%${overround === null || overround === 0 ? "" : `（${overround > 0 ? "高于" : "低于"} 100% ${roundForDisplay(Math.abs(overround), 2)} 个百分点）`}，未归一化`)}</dd>`;
    const policyRule = topic.policy_action
      ? `<p class="policy-count-rule">这是全年累计次数盘口。降息和加息两组可能同时非零，不能相减成净政策路径。</p>`
      : "";
    return `${sectionLead}
      <details class="expectation-row" ${topic.topic_id === "fed_policy_distribution" ? "open" : ""}>
        <summary><span><strong>${escapeHTML(topic.display_label || topic.label)}</strong><small>${escapeHTML(`${summaryLead} · ${dailySummary}${activitySummary}`)}</small></span><span>${escapeHTML(`${roundForDisplay(Number(topOutcome.probability || 0) * 100, 1)}%`)}</span></summary>
        <div class="expectation-detail">
          ${bars}
          ${extraBars}
          <dl class="expectation-meta">
            <dt>市场原题</dt><dd>${escapeHTML(topic.title || "不可用")}</dd>
            <dt>市场截止</dt><dd>${escapeHTML(formatDateTime(topic.end_date))}</dd>
            <dt>数据更新</dt><dd>${escapeHTML(formatDateTime(topic.updated_at))}</dd>
            <dt>24 小时成交</dt><dd>${escapeHTML(formatUsd(topic.volume_24h_usd))}</dd>
            <dt>可用流动性</dt><dd>${escapeHTML(formatUsd(topic.liquidity_usd))}</dd>
            ${featured ? `<dt>为什么展示</dt><dd>${escapeHTML(topic.selection_reason || "在未到期的宏观候选中，24 小时成交较活跃。")}</dd>` : ""}
            ${sumDetail}
          </dl>
          <p>${escapeHTML(freshness)}。概率是市场价格隐含的押注，不是官方预测。</p>
          ${policyRule}
          <a class="inline-link" href="${escapeHTML(safeUrl(topic.url))}" target="_blank" rel="noreferrer">查看市场规则与盘口 <span aria-hidden="true">↗</span></a>
        </div>
      </details>`;
  }).join("");
  const cme = expectations.cme_fedwatch || {};
  return `
    <div class="special-analysis expectations-analysis">
      <div class="analysis-status-row"><div><p class="eyebrow">市场预期</p><h3>真钱押注在预期什么，而不是结果一定会发生什么</h3></div><span class="analysis-state state-${escapeHTML(expectations.status || "unavailable")}">${expectations.status === "ready" ? "已更新" : expectations.status === "degraded" ? "部分可用" : "暂不可用"}</span></div>
      <div class="expectation-list">${topicRows || `<div class="notice"><strong>当前没有可展示的未到期市场</strong><span>已到期、已关闭或数据过旧的盘口不会出现在这里。</span></div>`}</div>
      <details class="cme-status"><summary><strong>${escapeHTML(cme.label || "CME 利率押注")}</strong><span>等待官方数据权限</span></summary><p>${escapeHTML(cme.message || "当前没有结构化数据。")}</p><a class="inline-link" href="${escapeHTML(safeUrl(cme.source_url))}" target="_blank" rel="noreferrer">查看官方页面 <span aria-hidden="true">↗</span></a></details>
      <p class="reading-rule">Polymarket 是预测市场，不是官方数据。页面保留原始盘口，不把加息和降息次数互减成净利率路径。</p>
    </div>`;
}

function bindMarketExpectationInteractions() {
  document.querySelectorAll("[data-expectation-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.expectationToggle || "");
      if (!target) return;
      const expanded = button.getAttribute("aria-expanded") === "true";
      target.hidden = expanded;
      button.setAttribute("aria-expanded", String(!expanded));
      const count = target.querySelectorAll(".probability-row").length;
      button.textContent = expanded ? `查看其余 ${count} 个结果` : "收起其他结果";
    });
  });
}

function stablecoinChange(metric, windowId, fallback = "暂无可比") {
  const change = metric?.changes?.[windowId]?.change;
  return numericOrNull(change) === null ? fallback : formatChangeValue(metric, change);
}

function stablecoinDirection(metric) {
  const weekly = numericOrNull(metric?.changes?.["1w"]?.percent_change);
  if (weekly === null) return "最近一周暂时无法比较";
  if (weekly > 0.1) return "最近一周供给增加，链上美元容量扩张";
  if (weekly < -0.1) return "最近一周供给减少，链上美元容量收缩";
  return "最近一周变化不大，链上美元容量基本持平";
}

function stablecoinPegReading(metric) {
  const value = numericOrNull(metric?.value);
  if (value === null) return {label: "锚定状态不可用", className: "quality-unavailable", detail: "主要稳定币价格暂时没有通过检查。"};
  const symbol = metric?.metadata?.symbol || "主要稳定币";
  const price = numericOrNull(metric?.metadata?.price);
  const priceText = price === null ? "价格不可用" : `$${roundForDisplay(price, 5)}`;
  if (value > 100) return {label: "锚定风险", className: "quality-needs_review", detail: `${symbol} 偏离最多，为 ${roundForDisplay(value, 1)} 个基点，当前 ${priceText}。`};
  if (value > 30) return {label: "需要留意", className: "quality-fresh_cache", detail: `${symbol} 偏离最多，为 ${roundForDisplay(value, 1)} 个基点，当前 ${priceText}。`};
  return {label: "锚定正常", className: "quality-fresh_network", detail: `主要稳定币暂未出现明显脱锚，最大偏离来自 ${symbol}，为 ${roundForDisplay(value, 1)} 个基点。`};
}

function stablecoinDestinationSummary(data) {
  const stablecoins = data.stablecoin_liquidity || {};
  const total = data.metrics?.stablecoin_usd_supply;
  if (!stablecoins.available_for_analysis || !total) return "稳定币数据暂不可用，不影响上面的宏观判断。";
  return `${stablecoinDirection(total)}。`;
}

function stablecoinPanel(data) {
  const stablecoins = data.stablecoin_liquidity || {};
  const total = data.metrics?.stablecoin_usd_supply;
  const peg = data.metrics?.stablecoin_core_max_depeg_bps;
  const source = stablecoins.source || {};
  const statusLabel = stablecoins.quality_status === "fresh_cache"
    ? "使用有效缓存"
    : stablecoins.available_for_analysis ? "数据已更新" : "暂不可用";
  const statusClassName = stablecoins.quality_status === "fresh_cache"
    ? "quality-fresh_cache"
    : stablecoins.available_for_analysis ? "quality-fresh_network" : "quality-unavailable";
  if (!stablecoins.available_for_analysis || !total) {
    return `
      <div class="crypto-channel-panel stablecoin-section" aria-labelledby="stablecoin-title">
        <div class="section-heading">
          <div><h3 id="stablecoin-title">稳定币数据暂不可用</h3></div>
          <span class="quality-pill ${statusClassName}">${escapeHTML(statusLabel)}</span>
        </div>
        <div class="notice notice-warning"><strong>核心看板照常更新</strong><span>${escapeHTML(source.error || "稳定币是可选数据，不会阻断宏观数据和 Agent 的其他分析。")}</span></div>
      </div>`;
  }

  const composition = stablecoins.composition || {};
  const pegReading = stablecoinPegReading(peg);
  const items = Array.isArray(composition.items) ? composition.items : [];
  const compositionRows = composition.available && items.length
    ? items.map((item) => {
        const share = Math.max(0, Math.min(1, Number(item.share) || 0));
        return `<div class="stablecoin-composition-row">
          <div><strong>${escapeHTML(item.label)}</strong><span>${escapeHTML(roundForDisplay(share * 100, 1))}%</span></div>
          <div class="stablecoin-share-track" aria-hidden="true"><i style="width:${share * 100}%"></i></div>
          <p><span>${escapeHTML(formatUsdMillions(Number(item.value)))}</span><small>一周 ${escapeHTML(formatChangeValue({unit: item.unit}, item.change_1w))}</small></p>
        </div>`;
      }).join("")
    : `<p class="stablecoin-empty">分项和总量暂未对齐，本轮只显示总供给。</p>`;
  const warnings = stablecoins.quality?.warnings || [];
  return `
    <div class="crypto-channel-panel stablecoin-section" aria-labelledby="stablecoin-title">
      <div class="section-heading">
        <div><h3 id="stablecoin-title">链上美元容量正在怎样变化</h3></div>
        <span class="quality-pill ${statusClassName}">${escapeHTML(statusLabel)}</span>
      </div>
      <p class="stablecoin-answer">${escapeHTML(stablecoinDirection(total))}。这说明可用于加密结算的美元容量发生变化，不代表资金已经买入加密资产。</p>
      <div class="stablecoin-trend-layout">
        <div class="stablecoin-reading">
          <span>美元稳定币总供给 · ${escapeHTML(formatDate(total.observed_at))}</span>
          <strong>${escapeHTML(formatMetricValue(total, true))}</strong>
          <dl>
            <div><dt>1 日</dt><dd>${escapeHTML(stablecoinChange(total, "1d"))}</dd></div>
            <div><dt>7 日</dt><dd>${escapeHTML(stablecoinChange(total, "1w"))}</dd></div>
            <div><dt>30 日</dt><dd>${escapeHTML(stablecoinChange(total, "1m"))}</dd></div>
          </dl>
        </div>
        <div class="stablecoin-chart-pane">
          <div class="stablecoin-chart-toolbar">
            <div class="stablecoin-control-group">
              <span>看什么</span>
              <div class="stablecoin-control-options" role="group" aria-label="选择稳定币图表内容">
                ${Object.entries(STABLECOIN_MODE_LABELS).map(([id, label]) => `<button class="chart-switch-button" type="button" data-stablecoin-mode="${id}" aria-pressed="${state.stablecoinChart.mode === id}">${escapeHTML(label)}</button>`).join("")}
              </div>
            </div>
            <div class="stablecoin-control-group">
              <span>时间区间</span>
              <div class="stablecoin-control-options" role="group" aria-label="选择稳定币历史区间">
                ${["1m", "3m", "1y", "5y", "all"].map((id) => `<button class="chart-switch-button" type="button" data-stablecoin-range="${id}" aria-pressed="${state.stablecoinChart.range === id}">${escapeHTML(RANGE_LABELS[id])}</button>`).join("")}
              </div>
            </div>
          </div>
          <div class="stablecoin-chart-caption" aria-live="polite">
            <strong data-stablecoin-chart-title>美元稳定币总供给</strong>
            <span data-stablecoin-chart-subtitle>按面值计算，过去 1 年</span>
          </div>
          <div class="chart-shell stablecoin-chart" data-stablecoin-chart aria-label="美元稳定币走势"><div class="chart-state">正在准备图表…</div></div>
        </div>
      </div>
      <div class="stablecoin-diagnostics">
        <section aria-labelledby="stablecoin-mix-title">
          <header><h3 id="stablecoin-mix-title">供给由谁组成</h3><span>同一次币种列表</span></header>
          <div class="stablecoin-composition">${compositionRows}</div>
        </section>
        <section aria-labelledby="stablecoin-peg-title">
          <header><h3 id="stablecoin-peg-title">锚定是否稳定</h3><span class="quality-pill ${pegReading.className}">${escapeHTML(pegReading.label)}</span></header>
          <p>${escapeHTML(pegReading.detail)}</p>
          <small>只检查按供给排序且有有效价格的主要美元稳定币。</small>
        </section>
      </div>
      <details class="stablecoin-details">
        <summary>口径、来源和数据状态</summary>
        <div>
          <dl class="method-grid">
            <dt>这组数据是什么</dt><dd>${escapeHTML(stablecoins.methodology?.role || "加密内部流动性")}</dd>
            <dt>总供给怎么算</dt><dd>${escapeHTML(stablecoins.methodology?.supply || "按面值流通量计算")}</dd>
            <dt>数据来自哪里</dt><dd>${escapeHTML(source.source_owner || "DefiLlama")}，可信行业聚合源，不是政府或央行官方统计</dd>
            <dt>看板获取时间</dt><dd>${escapeHTML(formatDateTime(source.fetched_at))}（北京时间）</dd>
            <dt>总量与分项差异</dt><dd>${escapeHTML(roundForDisplay(Number(composition.difference_percent || 0), 2))}%；两个接口可能异步刷新，不强行凑平</dd>
          </dl>
          ${warnings.length ? `<div class="notice notice-warning"><strong>本轮说明</strong><span>${escapeHTML(warnings.join(" "))}</span></div>` : ""}
          <a class="inline-link" href="${escapeHTML(safeUrl(source.url))}" target="_blank" rel="noreferrer">查看数据说明 <span aria-hidden="true">↗</span></a>
        </div>
      </details>
    </div>`;
}

function stablecoinCumulativeChange(rawPoints) {
  const points = (rawPoints || []).filter((point) => numericOrNull(point?.value) !== null);
  if (!points.length) return [];
  const startValue = Number(points[0].value);
  return points.map((point) => ({
    ...point,
    value: Number(point.value) - startValue
  }));
}

function stablecoinChartMetric(total, mode) {
  if (mode !== "change") return total;
  return {
    ...total,
    label: "稳定币区间累计增减",
    short_label: "区间累计增减",
    chart_include_zero: true,
    chart_signed: true
  };
}

async function renderStablecoinChart(data) {
  const container = document.querySelector("[data-stablecoin-chart]");
  const title = document.querySelector("[data-stablecoin-chart-title]");
  const subtitle = document.querySelector("[data-stablecoin-chart-subtitle]");
  const total = data.metrics?.stablecoin_usd_supply;
  if (!container || !total) return;
  const mode = state.stablecoinChart.mode;
  const rangeId = state.stablecoinChart.range;
  const requestKey = `${mode}:${rangeId}`;
  container.setAttribute("aria-busy", "true");
  container.innerHTML = `<div class="chart-state">正在读取 ${escapeHTML(RANGE_LABELS[rangeId])}历史…</div>`;
  try {
    let rawPoints = rangeId === "1y" ? total.sparkline || [] : [];
    if (rawPoints.length < 2) {
      rawPoints = (await fetchSeriesPayload("stablecoin_usd_supply", rangeId)).points || [];
    }
    if (`${state.stablecoinChart.mode}:${state.stablecoinChart.range}` !== requestKey) return;
    const points = mode === "change" ? stablecoinCumulativeChange(rawPoints) : rawPoints;
    const metric = stablecoinChartMetric(total, mode);
    if (title) title.textContent = mode === "change" ? "相对区间起点的累计增减" : "美元稳定币总供给";
    if (subtitle) {
      const dateSpan = points.length >= 2
        ? `${formatChartDate(points[0].observed_at, rangeId)} → ${formatChartDate(points.at(-1).observed_at, rangeId)}`
        : RANGE_LABELS[rangeId];
      const change = mode === "change" && points.length
        ? `，期间${formatChangeValue(total, points.at(-1).value)}`
        : "";
      subtitle.textContent = mode === "change"
        ? `每个点减去区间起点，${dateSpan}${change}`
        : `按面值计算，${dateSpan}`;
    }
    drawChart(container, points, metric, rangeId);
  } catch (error) {
    if (`${state.stablecoinChart.mode}:${state.stablecoinChart.range}` !== requestKey) return;
    container.innerHTML = `<div class="chart-state">历史读取失败。${escapeHTML(error.message || "请稍后刷新")}</div>`;
  } finally {
    if (`${state.stablecoinChart.mode}:${state.stablecoinChart.range}` === requestKey) {
      container.removeAttribute("aria-busy");
    }
  }
}

function bindStablecoinChartInteractions(data) {
  document.querySelectorAll("[data-stablecoin-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      state.stablecoinChart.mode = button.dataset.stablecoinMode || "supply";
      document.querySelectorAll("[data-stablecoin-mode]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
      renderStablecoinChart(data);
    });
  });
  document.querySelectorAll("[data-stablecoin-range]").forEach((button) => {
    button.addEventListener("click", () => {
      state.stablecoinChart.range = button.dataset.stablecoinRange || "1y";
      document.querySelectorAll("[data-stablecoin-range]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
      renderStablecoinChart(data);
    });
  });
  requestAnimationFrame(() => renderStablecoinChart(data));
}

function cryptoChannelStatus(channel) {
  if (channel?.quality_status === "fresh_cache") {
    return { label: "使用有效缓存", className: "quality-fresh_cache" };
  }
  if (channel?.available_for_analysis) {
    return { label: "数据已更新", className: "quality-fresh_network" };
  }
  return { label: "暂不可用", className: "quality-unavailable" };
}

function cryptoAssetButtons(kind, selected) {
  return ["BTC", "ETH", "SOL"].map((symbol) => `
    <button class="chart-switch-button" type="button" data-${kind}-asset="${symbol}" aria-pressed="${selected === symbol}">${symbol}</button>`).join("");
}

function filterChartRange(rawPoints, rangeId) {
  const points = (rawPoints || []).filter((point) => point?.observed_at && numericOrNull(point?.value) !== null);
  if (rangeId === "all" || !points.length) return points;
  const latest = Date.parse(points.at(-1).observed_at);
  const cutoff = latest - (RANGE_DAYS_CLIENT[rangeId] || 31) * 86_400_000;
  return points.filter((point) => Date.parse(point.observed_at) >= cutoff);
}

function filterEtfChartRange(rawPoints, rangeId) {
  const points = (rawPoints || []).filter((point) => point?.observed_at && numericOrNull(point?.value) !== null);
  const sessions = ETF_SESSION_RANGES[rangeId];
  if (sessions) return points.slice(-sessions);
  return filterChartRange(points, rangeId);
}

function distinctEtfRanges(rawPoints) {
  const candidates = ["5d", "20d", "3m", "1y", "all"];
  const seen = new Set();
  const ranges = [];
  candidates.forEach((id) => {
    const points = filterEtfChartRange(rawPoints, id);
    if (!points.length) return;
    const signature = `${points.length}:${points[0].observed_at}:${points.at(-1).observed_at}`;
    if (seen.has(signature)) return;
    seen.add(signature);
    ranges.push(id);
  });
  return ranges.length ? ranges : ["all"];
}

function etfFlowSentence(asset, latestMetric, fiveDayMetric) {
  const latest = numericOrNull(latestMetric?.value);
  const fiveDay = numericOrNull(fiveDayMetric?.value);
  if (latest === null) return `${asset} ETF 还没有已结算的资金流，不能判断方向。`;
  const daily = latest > 0 ? "净流入" : latest < 0 ? "净流出" : "净流量为零";
  const recent = fiveDay === null
    ? "近 5 个交易日暂时无法合计"
    : fiveDay > 0 ? "近 5 个交易日合计仍是净流入" : fiveDay < 0 ? "近 5 个交易日合计仍是净流出" : "近 5 个交易日流入流出相抵";
  return `${asset} 最近一个已结算交易日${daily}，${recent}。这是现货申赎通道，不代表价格一定同方向变化。`;
}

function etfPanel(data) {
  const channel = data.crypto_etf || {};
  const symbol = state.cryptoMarket.etfAsset;
  const asset = channel.assets?.[symbol];
  const status = cryptoChannelStatus(channel);
  if (!channel.available_for_analysis || !asset?.available_for_analysis) {
    const waitingForKey = channel.credential_status === "missing";
    return `
      <div class="crypto-channel-panel etf-panel" aria-labelledby="etf-title">
        <div class="section-heading">
          <div><h3 id="etf-title">${waitingForKey ? "等待 SoSoValue API Key" : "ETF 数据暂不可用"}</h3><p>BTC、ETH、SOL 分开记录，不会把缺失数据当成零。</p></div>
          <span class="quality-pill ${status.className}">${escapeHTML(status.label)}</span>
        </div>
        <div class="crypto-asset-switch" role="group" aria-label="选择 ETF 资产">${cryptoAssetButtons("etf", symbol)}</div>
        <div class="notice notice-warning"><strong>其他看板照常更新</strong><span>${escapeHTML(channel.source?.error || "ETF 是可选数据，不会阻断宏观、稳定币和衍生品分析。")}</span></div>
        <details class="stablecoin-details"><summary>口径和数据源</summary><div><p>只使用美国现货 ETF 已经结算的日净流入。当天仍为空的记录不会当成 0。</p><a class="inline-link" href="https://sosovalue.gitbook.io/soso-value-api-doc/2.-etf/etf.md" target="_blank" rel="noreferrer">查看 SoSoValue 接口说明 <span aria-hidden="true">↗</span></a></div></details>
      </div>`;
  }
  const prefix = `etf_${symbol.toLowerCase()}`;
  const latest = data.metrics?.[`${prefix}_net_flow_latest`];
  const fiveDay = data.metrics?.[`${prefix}_net_flow_5d`];
  const twentyDay = data.metrics?.[`${prefix}_net_flow_20d`];
  const aum = data.metrics?.[`${prefix}_aum`];
  const flowHistory = latest?.sparkline || [];
  const availableRanges = distinctEtfRanges(flowHistory);
  if (!availableRanges.includes(state.cryptoMarket.etfRange)) {
    state.cryptoMarket.etfRange = availableRanges.includes("20d") ? "20d" : availableRanges[0];
  }
  const firstHistoryDate = flowHistory[0]?.observed_at;
  const lastHistoryDate = flowHistory.at(-1)?.observed_at;
  const historyCoverage = flowHistory.length
    ? `当前有 ${flowHistory.length} 个已结算交易日：${formatDate(firstHistoryDate)}至${formatDate(lastHistoryDate)}。历史每天自动累积。`
    : "历史正在从每天的已结算数据开始累积。";
  const pending = asset.pending_date
    ? `<div class="notice notice-neutral"><strong>${escapeHTML(formatDate(asset.pending_date))} 仍在结算</strong><span>本页继续使用 ${escapeHTML(formatDate(asset.observed_at))} 的已结算数据，不把空值写成零。</span></div>`
    : "";
  const warnings = channel.quality?.warnings || [];
  return `
    <div class="crypto-channel-panel etf-panel" aria-labelledby="etf-title">
      <div class="section-heading">
        <div><h3 id="etf-title">美国现货 ETF 的钱在流入还是流出</h3><p>只看已经结算的交易日，BTC、ETH、SOL 各算各的。</p></div>
        <span class="quality-pill ${status.className}">${escapeHTML(status.label)}</span>
      </div>
      <div class="crypto-asset-switch" role="group" aria-label="选择 ETF 资产">${cryptoAssetButtons("etf", symbol)}</div>
      <p class="stablecoin-answer">${escapeHTML(etfFlowSentence(symbol, latest, fiveDay))}</p>
      <div class="crypto-summary-grid">
        <div><span>最近一个交易日</span><strong class="${numericOrNull(latest?.value) >= 0 ? "delta-positive" : "delta-negative"}">${escapeHTML(formatMetricValue(latest, true))}</strong><small>${escapeHTML(formatDate(latest?.observed_at))}</small></div>
        <div><span>近 5 个交易日</span><strong>${escapeHTML(formatMetricValue(fiveDay, true))}</strong><small>已结算日合计</small></div>
        <div><span>近 20 个交易日</span><strong>${escapeHTML(formatMetricValue(twentyDay, true))}</strong><small>约一个交易月</small></div>
        <div><span>ETF 总资产</span><strong>${escapeHTML(formatMetricValue(aum, true))}</strong><small>含币价变化</small></div>
      </div>
      ${pending}
      <div class="crypto-chart-block">
        <div class="stablecoin-chart-toolbar">
          <div class="stablecoin-control-group"><span>时间区间</span><div class="stablecoin-control-options" role="group" aria-label="选择 ETF 历史区间">
            ${availableRanges.map((id) => `<button class="chart-switch-button" type="button" data-etf-range="${id}" aria-pressed="${state.cryptoMarket.etfRange === id}">${escapeHTML(ETF_RANGE_LABELS[id])}</button>`).join("")}
          </div></div>
        </div>
        <p class="crypto-history-note">${escapeHTML(historyCoverage)}</p>
        <div class="stablecoin-chart-caption"><strong data-etf-chart-title>${symbol} ETF 每日净流入</strong><span data-etf-chart-subtitle>正数流入，负数流出</span></div>
        <div class="chart-shell crypto-chart" data-etf-chart aria-label="${symbol} ETF 每日净流入走势"><div class="chart-state">正在准备图表…</div></div>
      </div>
      <details class="stablecoin-details"><summary>口径、来源和数据状态</summary><div>
        <dl class="method-grid">
          <dt>这组数据是什么</dt><dd>美国现货 ETF 的日净申购赎回，是加密现货资金通道，不进入宏观流动性公式</dd>
          <dt>结算规则</dt><dd>只用 net_inflow 已经有数值的交易日；空值表示尚未结算或不可用</dd>
          <dt>数据来自哪里</dt><dd>SoSoValue OpenAPI；Farside 只作人工交叉核对</dd>
          <dt>长期历史</dt><dd>接口约返回最近一个月；看板每天落库后逐步积累</dd>
        </dl>
        ${warnings.length ? `<div class="notice notice-warning"><strong>本轮说明</strong><span>${escapeHTML(warnings.join(" "))}</span></div>` : ""}
        <a class="inline-link" href="${escapeHTML(safeUrl(channel.source?.url))}" target="_blank" rel="noreferrer">查看数据说明 <span aria-hidden="true">↗</span></a>
      </div></details>
    </div>`;
}

function derivativesSentence(symbol, openInterest, priceChange, funding8h, fundingAnnualized, accountLong, takerBuy) {
  if (![openInterest, priceChange, funding8h].every((metric) => numericOrNull(metric?.value) !== null)) {
    return `${symbol} 衍生品缺少必要数据，不能判断杠杆状态。`;
  }
  const price = Number(priceChange.value);
  const rate8h = Number(funding8h.value);
  const annualized = numericOrNull(fundingAnnualized?.value);
  const account = numericOrNull(accountLong?.value);
  const taker = numericOrNull(takerBuy?.value);
  const parts = [
    `未平仓 ${formatMetricValue(openInterest, true)}`,
    `24 小时价格${price >= 0 ? "上涨" : "下跌"} ${roundForDisplay(Math.abs(price), 2)}%`,
    `8 小时等价资金费率 ${formatSignedPercent(rate8h, 4)}`
  ];
  if (annualized !== null) parts.push(`年化等价 ${formatSignedPercent(annualized, 2)}`);
  if (account !== null) parts.push(`多头账户 ${roundForDisplay(account, 1)}%`);
  if (taker !== null) parts.push(`主动买入 ${roundForDisplay(taker, 1)}%`);
  return `${symbol}：${parts.join("；")}。`;
}

function derivativesPanel(data) {
  const channel = data.crypto_derivatives || {};
  const symbol = state.cryptoMarket.derivativesAsset;
  const asset = channel.assets?.[symbol];
  const status = cryptoChannelStatus(channel);
  if (!channel.available_for_analysis || !asset?.available_for_analysis) {
    return `
      <div class="crypto-channel-panel derivatives-panel" aria-labelledby="derivatives-title">
        <div class="section-heading"><div><h3 id="derivatives-title">衍生品数据暂不可用</h3><p>少于两家有效交易所时，看板不会给出杠杆判断。</p></div><span class="quality-pill ${status.className}">${escapeHTML(status.label)}</span></div>
        <div class="crypto-asset-switch" role="group" aria-label="选择衍生品资产">${cryptoAssetButtons("derivatives", symbol)}</div>
        <div class="notice notice-warning"><strong>没有用 0 代替缺失</strong><span>${escapeHTML((asset?.errors || channel.quality?.warnings || ["等待下一次官方接口采集"]).map(plainChannelIssue).join("；"))}</span></div>
      </div>`;
  }
  const prefix = `derivatives_${symbol.toLowerCase()}`;
  const openInterest = data.metrics?.[`${prefix}_open_interest`];
  const funding8h = data.metrics?.[`${prefix}_funding_8h_equivalent`];
  const fundingAnnualized = data.metrics?.[`${prefix}_funding_annualized`];
  const priceChange = data.metrics?.[`${prefix}_price_change_24h`];
  const accountLong = data.metrics?.[`${prefix}_account_long_share`];
  const takerBuy = data.metrics?.[`${prefix}_taker_buy_share_24h`];
  const oiDay = openInterest?.changes?.["1d"];
  const oiWeek = openInterest?.changes?.["1w"];
  const accountValue = numericOrNull(accountLong?.value);
  const takerValue = numericOrNull(takerBuy?.value);
  const venueRows = (asset.venues || []).map((venue) => `
    <div class="derivatives-venue-row">
      <strong>${escapeHTML(venue.venue_name || venue.venue)}</strong>
      <span><small>未平仓</small>${escapeHTML(formatUsdMillions(Number(venue.open_interest_usd_millions)))}</span>
      <span><small>本期资金费率 · ${escapeHTML(roundForDisplay(Number(venue.funding_interval_hours), 0))} 小时</small>${escapeHTML(formatSignedPercent(venue.funding_rate_per_interval_pct, 4))}<small>年化等价 ${escapeHTML(formatSignedPercent(venue.funding_annualized_pct, 2))}</small></span>
      <span><small>多头账户</small>${numericOrNull(venue.account_long_pct) === null ? "不可用" : escapeHTML(`${roundForDisplay(Number(venue.account_long_pct), 1)}%`)}</span>
      <span><small>24 小时主动买入</small>${numericOrNull(venue.taker_buy_share_24h_pct) === null ? "未覆盖" : escapeHTML(`${roundForDisplay(Number(venue.taker_buy_share_24h_pct), 1)}%`)}</span>
    </div>`).join("");
  const errors = [...(asset.errors || []), ...(asset.signal_errors || [])];
  const venueCount = Number(asset.venue_count || asset.venues?.length || 0);
  const expectedVenueCount = Number(asset.expected_venue_count || 3);
  return `
    <div class="crypto-channel-panel derivatives-panel" aria-labelledby="derivatives-title">
      <div class="section-heading"><div><h3 id="derivatives-title">杠杆是在增加，还是正在退潮</h3><p>把未平仓、价格和资金费率放在一起看。</p></div><span class="quality-pill ${status.className}">${escapeHTML(asset.quality_status === "fresh_cache" ? "使用有效缓存" : `${asset.venue_count}/3 家可用`)}</span></div>
      <div class="crypto-asset-switch" role="group" aria-label="选择衍生品资产">${cryptoAssetButtons("derivatives", symbol)}</div>
      <p class="stablecoin-answer">${escapeHTML(derivativesSentence(symbol, openInterest, priceChange, funding8h, fundingAnnualized, accountLong, takerBuy))}</p>
      <div class="crypto-summary-grid derivatives-summary-grid">
        <div><span>${escapeHTML(`${venueCount}/${expectedVenueCount} 家未平仓合计`)}</span><strong>${escapeHTML(formatMetricValue(openInterest, true))}</strong><small>24 小时 ${oiDay?.percent_change === null || oiDay?.percent_change === undefined ? "不可比" : `${oiDay.percent_change >= 0 ? "+" : "−"}${roundForDisplay(Math.abs(oiDay.percent_change), 2)}%`} · 7 天 ${oiWeek?.percent_change === null || oiWeek?.percent_change === undefined ? "不可比" : `${oiWeek.percent_change >= 0 ? "+" : "−"}${roundForDisplay(Math.abs(oiWeek.percent_change), 2)}%`}</small></div>
        <div><span>8 小时等价资金费率</span><strong>${escapeHTML(formatSignedPercent(funding8h?.value, 4))}</strong><small>${escapeHTML(`${venueCount}/${expectedVenueCount} 家按未平仓加权`)} · 年化等价 ${escapeHTML(formatSignedPercent(fundingAnnualized?.value, 2))}</small></div>
        <div><span>24 小时价格变化</span><strong>${escapeHTML(formatSignedPercent(priceChange?.value, 2))}</strong><small>三家永续合约价格变化中位数</small></div>
        <div><span>多头账户占比</span><strong>${accountValue === null ? "不可用" : escapeHTML(`${roundForDisplay(accountValue, 1)}%`)}</strong><small>${escapeHTML(`${asset.account_coverage?.length || 0}/3 家中位数`)} · 统计账户，不是资金</small></div>
        <div><span>24 小时主动买入占比</span><strong>${takerValue === null ? "不可用" : escapeHTML(`${roundForDisplay(takerValue, 1)}%`)}</strong><small>${escapeHTML(`${asset.taker_coverage?.length || 0}/2 家中位数`)} · 成交方向，不是持仓</small></div>
      </div>
      <div class="crypto-chart-block">
        <div class="stablecoin-chart-toolbar">
          <div class="stablecoin-control-group"><span>看什么</span><div class="stablecoin-control-options" role="group" aria-label="选择衍生品图表内容">
            ${Object.entries(DERIVATIVES_MODE_LABELS).map(([id, label]) => `<button class="chart-switch-button" type="button" data-derivatives-mode="${id}" aria-pressed="${state.cryptoMarket.derivativesMode === id}">${escapeHTML(label)}</button>`).join("")}
          </div></div>
          <div class="stablecoin-control-group"><span>时间区间</span><div class="stablecoin-control-options" role="group" aria-label="选择衍生品历史区间">
            ${["1m", "3m", "1y", "all"].map((id) => `<button class="chart-switch-button" type="button" data-derivatives-range="${id}" aria-pressed="${state.cryptoMarket.derivativesRange === id}">${escapeHTML(RANGE_LABELS[id])}</button>`).join("")}
          </div></div>
        </div>
        <div class="stablecoin-chart-caption"><strong data-derivatives-chart-title>${symbol} 永续未平仓</strong><span data-derivatives-chart-subtitle>同一覆盖范围才比较变化</span></div>
        <div class="chart-shell crypto-chart" data-derivatives-chart aria-label="${symbol} 衍生品走势"><div class="chart-state">正在准备图表…</div></div>
      </div>
      <div class="derivatives-venues" aria-label="各交易所明细">${venueRows}</div>
      ${errors.length ? `<div class="notice notice-warning"><strong>部分附加信号缺失</strong><span>核心未平仓和资金费率仍可用。${escapeHTML(errors.map(plainChannelIssue).join("；"))}</span></div>` : ""}
      <details class="stablecoin-details"><summary>口径、覆盖和限制</summary><div>
        <dl class="method-grid"><dt>覆盖什么</dt><dd>Binance、OKX、Bybit 的 BTC、ETH、SOL USDT 永续合约</dd><dt>未平仓怎么算</dt><dd>三家名义未平仓金额相加；24 小时和 7 天变化来自同一批交易所的官方历史快照</dd><dt>资金费率怎么看</dt><dd>主值把各交易所当前费率折算成 8 小时等价，再按未平仓金额加权。年化等价只用来比较，不是已经发生的全年持仓成本</dd><dt>多空比是什么</dt><dd>三家多头账户占比的中位数。一个大账户和一个小账户都只算一个账户</dd><dt>主动买入是什么</dt><dd>Binance、OKX 过去 24 小时主动买入成交占比的中位数；Bybit 暂不在这项覆盖内</dd><dt>没有覆盖</dt><dd>其他交易所、币本位、季度交割、全市场爆仓和期权</dd></dl>
        <p class="reading-rule">本页是三家交易所的覆盖样本，不代表全市场。未平仓增加既可能是多头，也可能是空头。</p>
      </div></details>
    </div>`;
}

function cryptoMarketPanel(data) {
  return `
    <section id="flow-crypto" class="dashboard-section crypto-market-section" data-crypto-market aria-labelledby="crypto-market-title">
      <div class="section-heading"><div><p class="eyebrow">加密资金管道</p><h2 id="crypto-market-title">把链上现金、现货买盘和杠杆分开看</h2><p>对照稳定币、ETF、交易所现货价差与衍生品走势。</p></div></div>
      <div class="crypto-market-tabs" role="tablist" aria-label="选择加密资金维度">
        ${Object.entries(CRYPTO_TAB_LABELS).map(([id, label]) => `<button id="crypto-tab-${id}" type="button" role="tab" data-crypto-tab="${id}" aria-controls="crypto-panel-${id}" aria-selected="${state.cryptoMarket.tab === id}" tabindex="${state.cryptoMarket.tab === id ? "0" : "-1"}">${escapeHTML(label)}</button>`).join("")}
      </div>
      ${Object.keys(CRYPTO_TAB_LABELS).map((id) => `<div id="crypto-panel-${id}" role="tabpanel" aria-labelledby="crypto-tab-${id}" tabindex="0" data-crypto-panel="${id}"${state.cryptoMarket.tab === id ? "" : " hidden"}></div>`).join("")}
    </section>`;
}

async function renderEtfChart(data) {
  const container = document.querySelector("[data-etf-chart]");
  if (!container) return;
  const symbol = state.cryptoMarket.etfAsset;
  const rangeId = state.cryptoMarket.etfRange;
  const metricId = `etf_${symbol.toLowerCase()}_net_flow_latest`;
  const metric = data.metrics?.[metricId];
  const requestKey = `${symbol}:${rangeId}`;
  container.setAttribute("aria-busy", "true");
  try {
    let points = filterEtfChartRange(metric?.sparkline || [], rangeId);
    if (points.length < 2) points = (await fetchSeriesPayload(metricId, rangeId)).points || [];
    if (`${state.cryptoMarket.etfAsset}:${state.cryptoMarket.etfRange}` !== requestKey) return;
    const subtitle = document.querySelector("[data-etf-chart-subtitle]");
    if (subtitle) subtitle.textContent = points.length >= 2
      ? `${formatChartDate(points[0].observed_at, rangeId)} → ${formatChartDate(points.at(-1).observed_at, rangeId)}；正数流入，负数流出`
      : "历史正在从每天的已结算数据开始积累";
    drawSignedBarChart(container, points, {...metric, chart_include_zero: true}, rangeId);
  } catch (error) {
    if (`${state.cryptoMarket.etfAsset}:${state.cryptoMarket.etfRange}` === requestKey) {
      container.innerHTML = `<div class="chart-state">历史读取失败。${escapeHTML(error.message || "请稍后刷新")}</div>`;
    }
  } finally {
    if (`${state.cryptoMarket.etfAsset}:${state.cryptoMarket.etfRange}` === requestKey) container.removeAttribute("aria-busy");
  }
}

async function renderDerivativesChart(data) {
  const container = document.querySelector("[data-derivatives-chart]");
  if (!container) return;
  const symbol = state.cryptoMarket.derivativesAsset;
  const mode = state.cryptoMarket.derivativesMode;
  const rangeId = state.cryptoMarket.derivativesRange;
  const metricId = `derivatives_${symbol.toLowerCase()}_${mode}`;
  const metric = data.metrics?.[metricId];
  const requestKey = `${symbol}:${mode}:${rangeId}`;
  container.setAttribute("aria-busy", "true");
  try {
    let points = filterChartRange(metric?.sparkline || [], rangeId);
    if (points.length < 2) points = (await fetchSeriesPayload(metricId, rangeId)).points || [];
    if (`${state.cryptoMarket.derivativesAsset}:${state.cryptoMarket.derivativesMode}:${state.cryptoMarket.derivativesRange}` !== requestKey) return;
    const title = document.querySelector("[data-derivatives-chart-title]");
    const subtitle = document.querySelector("[data-derivatives-chart-subtitle]");
    const titles = {
      open_interest: `${symbol} 永续未平仓`,
      funding_8h_equivalent: `${symbol} 8 小时等价资金费率`,
      account_long_share: `${symbol} 多头账户占比`,
      taker_buy_share_24h: `${symbol} 24 小时主动买入占比`
    };
    if (title) title.textContent = titles[mode] || `${symbol} 衍生品走势`;
    if (subtitle) subtitle.textContent = points.length >= 2
      ? `${formatChartDate(points[0].observed_at, rangeId)} → ${formatChartDate(points.at(-1).observed_at, rangeId)}；${["account_long_share", "taker_buy_share_24h"].includes(mode) ? "50% 是多空或买卖平衡线" : "只比较相同覆盖范围"}`
      : "今天开始落库，至少需要两个快照才能画走势";
    const chartMetric = mode === "funding_8h_equivalent"
      ? {...metric, chart_include_zero: true}
      : ["account_long_share", "taker_buy_share_24h"].includes(mode)
        ? {...metric, chart_reference: 50}
        : metric;
    drawChart(container, points, chartMetric, rangeId);
  } catch (error) {
    if (`${state.cryptoMarket.derivativesAsset}:${state.cryptoMarket.derivativesMode}:${state.cryptoMarket.derivativesRange}` === requestKey) {
      container.innerHTML = `<div class="chart-state">历史读取失败。${escapeHTML(error.message || "请稍后刷新")}</div>`;
    }
  } finally {
    if (`${state.cryptoMarket.derivativesAsset}:${state.cryptoMarket.derivativesMode}:${state.cryptoMarket.derivativesRange}` === requestKey) container.removeAttribute("aria-busy");
  }
}

function renderActiveCryptoChart(data) {
  if (state.cryptoMarket.tab === "premium") renderPremiumChart();
  if (state.cryptoMarket.tab === "stablecoins" && data.stablecoin_liquidity?.available_for_analysis) renderStablecoinChart(data);
  if (state.cryptoMarket.tab === "etf" && data.crypto_etf?.available_for_analysis) renderEtfChart(data);
  if (state.cryptoMarket.tab === "derivatives" && data.crypto_derivatives?.available_for_analysis) renderDerivativesChart(data);
}

function bindCryptoPanelInteractions(data) {
  if (state.cryptoMarket.tab === "premium") {
    bindPremiumInteractions(data);
    return;
  }
  if (state.cryptoMarket.tab === "stablecoins") {
    bindStablecoinChartInteractions(data);
    return;
  }
  document.querySelectorAll("[data-etf-asset]").forEach((button) => button.addEventListener("click", () => {
    state.cryptoMarket.etfAsset = button.dataset.etfAsset || "BTC";
    renderCryptoMarketContent(data);
  }));
  document.querySelectorAll("[data-etf-range]").forEach((button) => button.addEventListener("click", () => {
    state.cryptoMarket.etfRange = button.dataset.etfRange || "20d";
    document.querySelectorAll("[data-etf-range]").forEach((candidate) => {
      candidate.setAttribute("aria-pressed", String(candidate === button));
    });
    renderEtfChart(data);
  }));
  document.querySelectorAll("[data-derivatives-asset]").forEach((button) => button.addEventListener("click", () => {
    state.cryptoMarket.derivativesAsset = button.dataset.derivativesAsset || "BTC";
    renderCryptoMarketContent(data);
  }));
  document.querySelectorAll("[data-derivatives-mode]").forEach((button) => button.addEventListener("click", () => {
    state.cryptoMarket.derivativesMode = button.dataset.derivativesMode || "open_interest";
    renderCryptoMarketContent(data);
  }));
  document.querySelectorAll("[data-derivatives-range]").forEach((button) => button.addEventListener("click", () => {
    state.cryptoMarket.derivativesRange = button.dataset.derivativesRange || "1m";
    renderCryptoMarketContent(data);
  }));
  requestAnimationFrame(() => renderActiveCryptoChart(data));
}

function renderCryptoMarketContent(data) {
  document.querySelectorAll("[data-crypto-panel]").forEach((item) => {
    item.hidden = item.dataset.cryptoPanel !== state.cryptoMarket.tab;
  });
  const panel = document.querySelector(`[data-crypto-panel="${state.cryptoMarket.tab}"]`);
  if (!panel) return;
  panel.innerHTML = state.cryptoMarket.tab === "etf"
    ? etfPanel(data)
    : state.cryptoMarket.tab === "premium"
      ? coinbasePremiumPanel(data)
    : state.cryptoMarket.tab === "derivatives"
      ? derivativesPanel(data)
      : stablecoinPanel(data);
  bindCryptoPanelInteractions(data);
}

function selectCryptoTab(button, data, focus = false) {
  state.cryptoMarket.tab = button.dataset.cryptoTab || "stablecoins";
  document.querySelectorAll("[data-crypto-tab]").forEach((item) => {
    const selected = item === button;
    item.setAttribute("aria-selected", String(selected));
    item.setAttribute("tabindex", selected ? "0" : "-1");
  });
  renderCryptoMarketContent(data);
  elements.live.textContent = `已切换到${CRYPTO_TAB_LABELS[state.cryptoMarket.tab] || "加密数据"}`;
  if (focus) button.focus();
}

function moveCryptoTabFocus(button, direction, data) {
  const tabs = [...document.querySelectorAll("[data-crypto-tab]")];
  const currentIndex = Math.max(0, tabs.indexOf(button));
  const nextIndex = direction === "home"
    ? 0
    : direction === "end"
      ? tabs.length - 1
      : (currentIndex + direction + tabs.length) % tabs.length;
  selectCryptoTab(tabs[nextIndex], data, true);
}

function bindCryptoMarketInteractions(data) {
  document.querySelectorAll("[data-crypto-tab]").forEach((button) => {
    button.addEventListener("click", () => selectCryptoTab(button, data));
    button.addEventListener("keydown", (event) => {
      const directions = {ArrowLeft: -1, ArrowRight: 1, Home: "home", End: "end"};
      if (!(event.key in directions)) return;
      event.preventDefault();
      moveCryptoTabFocus(button, directions[event.key], data);
    });
  });
  renderCryptoMarketContent(data);
}

function yenCarryPanel(data) {
  const channel = data.yen_carry || {};
  const metrics = data.metrics || {};
  const states = channel.states || {};
  const incentive = states.carry_incentive || {};
  const pressure = states.unwind_pressure || {};
  const available = Boolean(channel.available_for_analysis);
  const quality = channel.quality_status || "unavailable";
  const statusLabel = quality === "fresh_cache" ? "使用有效缓存" : available ? "数据已更新" : "核心数据暂不可用";
  const metricIds = [
    "yen_carry_usd_jpy",
    "yen_carry_jpy_appreciation_5d",
    "yen_carry_short_rate_spread",
    "yen_carry_realized_volatility_20d",
    "yen_carry_cftc_leveraged_net_short",
    "yen_carry_fx_swap_turnover"
  ];
  const metricCards = metricIds.map((metricId) => {
    const metric = metrics[metricId];
    if (!metric) return "";
    return `<div><span>${escapeHTML(metric.short_label || metric.label)}</span><strong>${escapeHTML(formatMetricValue(metric, true))}</strong><small>${escapeHTML(formatDate(metric.observed_at))} · ${escapeHTML(formatCadence(metric.cadence))}</small></div>`;
  }).join("");
  const warningCount = Number(channel.quality?.warnings?.length || 0);
  return `
    <section id="flow-yen-carry" class="dashboard-section yen-carry-section" aria-labelledby="yen-carry-title">
      <div class="section-heading">
        <div><p class="eyebrow">日元融资与套息平仓压力</p><h2 id="yen-carry-title">利差还有没有吸引力，平仓压力有没有升温</h2><p>这是风险放大器，不属于联储净流动性公式。</p></div>
        <span class="quality-pill ${qualityClass(quality)}">${escapeHTML(statusLabel)}</span>
      </div>
      <div class="yen-state-grid" aria-label="日元套息当前状态">
        <article class="yen-state yen-state-incentive yen-state-${escapeHTML(incentive.code || "unknown")}"><span>套息动力</span><strong>${escapeHTML(incentive.label || "证据不足")}</strong><p>${escapeHTML(incentive.reason || "利差或汇率波动数据不足。")}</p></article>
        <article class="yen-state yen-state-pressure yen-state-${escapeHTML(pressure.code || "unknown")}"><span>平仓压力</span><strong>${escapeHTML(pressure.label || "证据不足")}</strong><p>${escapeHTML(pressure.reason || "日元升值或仓位数据不足。")}</p></article>
      </div>
      <div class="yen-metric-grid">${metricCards}</div>
      <div class="yen-carry-tabs" role="tablist" aria-label="选择日元套息图表">
        ${Object.entries(YEN_CARRY_MODE_LABELS).map(([id, label]) => `<button id="yen-carry-tab-${id}" type="button" role="tab" data-yen-carry-mode="${id}" aria-selected="${state.yenCarry.mode === id}" tabindex="${state.yenCarry.mode === id ? "0" : "-1"}">${escapeHTML(label)}</button>`).join("")}
      </div>
      <div class="cross-asset-toolbar">
        <span>时间区间</span>
        <div class="stablecoin-control-options" role="group" aria-label="选择日元套息历史区间">
          ${["1m", "3m", "1y", "5y", "all"].map((id) => `<button class="chart-switch-button" type="button" data-yen-carry-range="${id}" aria-pressed="${state.yenCarry.range === id}">${escapeHTML(RANGE_LABELS[id])}</button>`).join("")}
        </div>
      </div>
      <div class="cross-asset-chart-heading">
        <div><strong data-yen-carry-chart-title>日元强弱与汇率波动</strong><span data-yen-carry-chart-subtitle>所选区间起点 = 100</span></div>
        <div class="cross-asset-legend" data-yen-carry-legend></div>
      </div>
      <div class="chart-shell chart-shell-main yen-carry-chart" data-yen-carry-chart aria-label="日元套息走势"><div class="chart-state">正在准备图表…</div></div>
      <p class="chart-method" data-yen-carry-method>日元升值速度和汇率波动同时上升时，才更像平仓压力正在增强。</p>
      <details class="stablecoin-details yen-carry-details">
        <summary>判断规则、数据源和限制${warningCount ? ` · ${warningCount} 项来源提示` : ""}</summary>
        <div>
          <dl class="method-grid">
            <dt>套息动力</dt><dd>看美日短端利差相对过去 5 年的位置，并用汇率波动交叉检查。</dd>
            <dt>平仓压力</dt><dd>看日元近 5 日升值、20 日波动率、利差收窄和 CFTC 日元空仓回补；达到各自 5 年高位才触发预警。</dd>
            <dt>汇率</dt><dd>ECB 官方参考汇率交叉计算 USD/JPY；数值下降表示日元升值。</dd>
            <dt>日本利率</dt><dd>日本银行无担保隔夜利率；2 年端使用 JSDA 剩余期限约两年的国债代理。</dd>
            <dt>仓位</dt><dd>CFTC 杠杆基金日元期货净空仓，每周更新；不代表全球套息交易总规模。</dd>
            <dt>外汇掉期</dt><dd>日本银行东京市场成交额，只表示活动强弱，不表示交易方向。</dd>
            <dt>风险同步</dt><dd>日元升值与 BTC、标普下跌同时出现，只能说与套息平仓相符，不能证明因果。</dd>
          </dl>
        </div>
      </details>
    </section>`;
}

function drawYenMultiChart(container, rawPoints, specs, {rangeId, normalize = false, reference = null} = {}) {
  if (!container) return;
  const usableSpecs = specs.map((spec, index) => {
    const raw = (rawPoints || []).filter((point) => point?.observed_at && numericOrNull(point?.[spec.key]) !== null);
    if (!raw.length) return {...spec, index, points: []};
    const base = Number(raw[0][spec.key]);
    const points = raw.map((point) => {
      const value = Number(point[spec.key]);
      const transformed = spec.inverse ? 1 / value : value;
      const transformedBase = spec.inverse ? 1 / base : base;
      return {
        observed_at: point.observed_at,
        value: normalize && transformedBase ? transformed / transformedBase * 100 : transformed
      };
    });
    return {...spec, index, points};
  }).filter((series) => series.points.length);
  const allPoints = usableSpecs.flatMap((series) => series.points);
  if (allPoints.length < 2) {
    container.innerHTML = `<div class="chart-state">这个区间还没有足够的历史数据。</div>`;
    return;
  }
  const values = allPoints.map((point) => Number(point.value));
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  if (minimum === maximum) { minimum -= 1; maximum += 1; }
  const span = maximum - minimum;
  minimum -= span * 0.06;
  maximum += span * 0.06;
  const dates = allPoints.map((point) => point.observed_at).sort();
  const firstDate = dates[0];
  const lastDate = dates.at(-1);
  const firstTime = Date.parse(`${firstDate.slice(0, 10)}T00:00:00Z`);
  const lastTime = Date.parse(`${lastDate.slice(0, 10)}T00:00:00Z`);
  const timeSpan = Math.max(1, lastTime - firstTime);
  const measuredWidth = Math.round(container.clientWidth || 980);
  const width = Math.max(272, Math.min(980, measuredWidth));
  const isNarrow = width <= 420;
  const height = isNarrow ? 220 : 270;
  const left = isNarrow ? 10 : 20;
  const right = isNarrow ? 58 : 78;
  const top = 18;
  const bottom = 34;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const yFor = (value) => top + (maximum - Number(value)) / (maximum - minimum) * plotHeight;
  const lines = usableSpecs.map((series) => {
    const segmented = chartSegments(series.points, series);
    const points = segmented.flatMap((segment) => downsample(segment, Math.max(8, Math.floor(320 / Math.max(1, segmented.length)))).map((point, index) => ({...point, _segmentStart: index === 0})));
    const coordinates = points.map((point) => {
      const moment = Date.parse(`${point.observed_at.slice(0, 10)}T00:00:00Z`);
      return [left + (moment - firstTime) / timeSpan * plotWidth, yFor(point.value)];
    });
    const path = coordinates.map(([x, y], index) => `${points[index]._segmentStart ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
    const last = coordinates.at(-1);
    const lastPoint = points.at(-1);
    return `<path class="chart-line yen-line yen-line-${series.index + 1}" d="${path}"></path><circle class="yen-dot yen-dot-${series.index + 1}" cx="${last[0].toFixed(2)}" cy="${last[1].toFixed(2)}" r="4"><title>${escapeHTML(`${series.label}：${roundForDisplay(lastPoint.value, normalize ? 1 : 2)}`)}</title></circle>`;
  }).join("");
  const referenceLine = reference !== null && minimum <= reference && maximum >= reference
    ? `<line class="chart-zero-line" x1="${left}" y1="${yFor(reference).toFixed(2)}" x2="${left + plotWidth}" y2="${yFor(reference).toFixed(2)}"><title>参考线 ${reference}</title></line>`
    : minimum <= 0 && maximum >= 0
      ? `<line class="chart-zero-line" x1="${left}" y1="${yFor(0).toFixed(2)}" x2="${left + plotWidth}" y2="${yFor(0).toFixed(2)}"><title>零线</title></line>`
      : "";
  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(`${specs.map((item) => item.label).join("、")}，${RANGE_LABELS[rangeId] || rangeId}走势`)}">
      <line class="chart-grid" x1="${left}" y1="${top}" x2="${left + plotWidth}" y2="${top}"></line>
      <line class="chart-grid" x1="${left}" y1="${top + plotHeight / 2}" x2="${left + plotWidth}" y2="${top + plotHeight / 2}"></line>
      <line class="chart-grid" x1="${left}" y1="${top + plotHeight}" x2="${left + plotWidth}" y2="${top + plotHeight}"></line>
      ${referenceLine}${lines}
      <text class="chart-label" x="${left + plotWidth + 8}" y="${top + 4}">${escapeHTML(roundForDisplay(maximum, normalize ? 1 : 2))}</text>
      <text class="chart-label" x="${left + plotWidth + 8}" y="${top + plotHeight + 4}">${escapeHTML(roundForDisplay(minimum, normalize ? 1 : 2))}</text>
      <text class="chart-label" x="${left}" y="${height - 8}">${escapeHTML(formatChartDate(firstDate, rangeId))}</text>
      <text class="chart-label" text-anchor="end" x="${left + plotWidth}" y="${height - 8}">${escapeHTML(formatChartDate(lastDate, rangeId))}</text>
    </svg>`;
  const sampleDates = [...new Set(allPoints.map((point) => point.observed_at))].sort();
  bindChartExplorer(container, sampleDates.map((observedAt) => {
    const moment = Date.parse(`${observedAt.slice(0, 10)}T00:00:00Z`);
    const valuesAtDate = usableSpecs.map((series) => {
      const point = series.points.find((item) => item.observed_at === observedAt);
      if (!point) return null;
      return {
        label: series.label,
        formatted: normalize ? `${roundForDisplay(point.value, 1)}（起点=100）` : `${roundForDisplay(point.value, 3)}`,
        y: yFor(point.value),
        tone: series.index + 1
      };
    }).filter(Boolean);
    return {
      observed_at: observedAt,
      x: left + (moment - firstTime) / timeSpan * plotWidth,
      values: valuesAtDate
    };
  }), {plotTop: top, plotBottom: top + plotHeight, title: specs.map((item) => item.label).join("与")});
}

async function renderYenCarryChart(data) {
  const container = document.querySelector("[data-yen-carry-chart]");
  if (!container) return;
  const mode = state.yenCarry.mode;
  const rangeId = state.yenCarry.range;
  const requestKey = `${mode}:${rangeId}`;
  const metricIds = {
    fx_volatility: "yen_carry_fx_volatility",
    rate_spreads: "yen_carry_rate_spreads",
    positioning: "yen_carry_positioning",
    risk_sync: "yen_carry_risk_sync"
  };
  const title = document.querySelector("[data-yen-carry-chart-title]");
  const subtitle = document.querySelector("[data-yen-carry-chart-subtitle]");
  const legend = document.querySelector("[data-yen-carry-legend]");
  const method = document.querySelector("[data-yen-carry-method]");
  container.setAttribute("aria-busy", "true");
  container.innerHTML = `<div class="chart-state">正在读取 ${escapeHTML(RANGE_LABELS[rangeId])}历史…</div>`;
  try {
    const payload = await fetchSeriesPayload(metricIds[mode], rangeId);
    if (`${state.yenCarry.mode}:${state.yenCarry.range}` !== requestKey) return;
    const points = payload.points || [];
    if (mode === "fx_volatility") {
      title.textContent = "日元强弱与汇率波动";
      subtitle.textContent = "区间起点 = 100；日元线向上表示升值";
      legend.innerHTML = `<span><i class="legend-line yen-legend-1"></i>日元强弱</span><span><i class="legend-line yen-legend-2"></i>20 日波动率</span>`;
      method.textContent = "两条线只比较变化速度，不比较绝对数值。上方卡片保留 USD/JPY 与波动率的实际读数。";
      drawYenMultiChart(container, points, [
        {key: "usd_jpy", label: "日元强弱", inverse: true},
        {key: "realized_volatility_20d", label: "20 日波动率"}
      ], {rangeId, normalize: true, reference: 100});
    } else if (mode === "rate_spreads") {
      title.textContent = "美日利差";
      subtitle.textContent = "百分点；利差收窄会削弱套息动力";
      legend.innerHTML = `<span><i class="legend-line yen-legend-1"></i>3M−日本隔夜</span><span><i class="legend-line yen-legend-2"></i>2Y−日本 2Y 代理</span>`;
      method.textContent = "短端利差是美国 3M 美债减日本隔夜利率；2 年端的日本国债是 JSDA 可复算代理，历史会从本模块上线后逐日累积。";
      drawYenMultiChart(container, points, [
        {key: "short_rate_spread", label: "美日短端利差"},
        {key: "two_year_rate_spread", label: "美日 2 年期利差"}
      ], {rangeId});
    } else if (mode === "positioning") {
      title.textContent = "杠杆基金日元净空仓";
      subtitle.textContent = "CFTC 周度期货仓位；空头合约减多头合约";
      legend.innerHTML = `<span><i class="legend-line yen-legend-1"></i>净空仓</span>`;
      method.textContent = "净空仓快速下降说明杠杆基金正在回补日元空头，但这只是 CFTC 报告期货的一部分。";
      drawChart(container, points, data.metrics?.yen_carry_cftc_leveraged_net_short || {label: "日元净空仓", unit: "contracts"}, rangeId);
    } else {
      title.textContent = "日元、BTC 与标普 500";
      subtitle.textContent = "共同观察日，区间起点 = 100";
      legend.innerHTML = `<span><i class="legend-line yen-legend-1"></i>日元强弱</span><span><i class="legend-line yen-legend-2"></i>BTC</span><span><i class="legend-line yen-legend-3"></i>标普 500</span>`;
      method.textContent = "三条线只显示同步变化。日元升值与风险资产下跌同时发生，只能说与套息平仓相符，不能证明因果。";
      drawYenMultiChart(container, points, [
        {key: "jpy_strength", label: "日元强弱"},
        {key: "btc_usd", label: "BTC"},
        {key: "sp500", label: "标普 500"}
      ], {rangeId, normalize: true, reference: 100});
    }
  } catch (error) {
    if (`${state.yenCarry.mode}:${state.yenCarry.range}` === requestKey) {
      container.innerHTML = `<div class="chart-state">这组历史暂时读不到。${escapeHTML(error.message || "请稍后刷新")}</div>`;
    }
  } finally {
    if (`${state.yenCarry.mode}:${state.yenCarry.range}` === requestKey) container.removeAttribute("aria-busy");
  }
}

function selectYenCarryMode(button, data, focus = false) {
  state.yenCarry.mode = button.dataset.yenCarryMode || "fx_volatility";
  document.querySelectorAll("[data-yen-carry-mode]").forEach((item) => {
    const selected = item === button;
    item.setAttribute("aria-selected", String(selected));
    item.setAttribute("tabindex", selected ? "0" : "-1");
  });
  renderYenCarryChart(data);
  elements.live.textContent = `已切换到${YEN_CARRY_MODE_LABELS[state.yenCarry.mode]}`;
  if (focus) button.focus();
}

function bindYenCarryInteractions(data) {
  document.querySelectorAll("[data-yen-carry-mode]").forEach((button) => {
    button.addEventListener("click", () => selectYenCarryMode(button, data));
    button.addEventListener("keydown", (event) => {
      const direction = {ArrowLeft: -1, ArrowRight: 1, Home: "home", End: "end"}[event.key];
      if (direction === undefined) return;
      event.preventDefault();
      const tabs = [...document.querySelectorAll("[data-yen-carry-mode]")];
      const current = Math.max(0, tabs.indexOf(button));
      const next = direction === "home" ? 0 : direction === "end" ? tabs.length - 1 : (current + direction + tabs.length) % tabs.length;
      selectYenCarryMode(tabs[next], data, true);
    });
  });
  document.querySelectorAll("[data-yen-carry-range]").forEach((button) => button.addEventListener("click", () => {
    state.yenCarry.range = button.dataset.yenCarryRange || "1y";
    document.querySelectorAll("[data-yen-carry-range]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    renderYenCarryChart(data);
  }));
  requestAnimationFrame(() => renderYenCarryChart(data));
}

function crossAssetPanel(data) {
  const channel = data.cross_asset || {};
  const available = Boolean(channel.available_for_analysis);
  const quality = channel.quality_status || "unavailable";
  const statusLabel = quality === "fresh_cache" ? "使用有效缓存" : available ? "数据已更新" : "暂不可用";
  return `
    <section id="flow-cross-asset" class="dashboard-section cross-asset-section" aria-labelledby="cross-asset-title">
      <div class="section-heading">
        <div><p class="eyebrow">跨资产相对强弱</p><h2 id="cross-asset-title">BTC 相对谁更强</h2><p>比较同一日期的收盘数据。这是相对走势，不是资金流向。</p></div>
        <span class="quality-pill ${qualityClass(quality)}">${escapeHTML(statusLabel)}</span>
      </div>
      <div class="cross-asset-tabs" role="tablist" aria-label="选择跨资产比较">
        ${Object.entries(CROSS_ASSET_LABELS).map(([id, label]) => `<button id="cross-asset-tab-${id}" type="button" role="tab" data-cross-asset-comparison="${id}" aria-selected="${state.crossAsset.comparison === id}" tabindex="${state.crossAsset.comparison === id ? "0" : "-1"}">${escapeHTML(label)}</button>`).join("")}
      </div>
      <div class="cross-asset-reading" aria-live="polite">
        <strong data-cross-asset-answer>${available ? "正在读取相对走势…" : "跨资产数据暂不可用"}</strong>
        <span data-cross-asset-detail>${available ? "图表起点统一设为 100，方便直接比较。" : "核心宏观数据和晨间分析仍会照常更新。"}</span>
      </div>
      <div class="cross-asset-toolbar">
        <span>时间区间</span>
        <div class="stablecoin-control-options" role="group" aria-label="选择跨资产历史区间">
          ${["1m", "3m", "1y", "5y", "all"].map((id) => `<button class="chart-switch-button" type="button" data-cross-asset-range="${id}" aria-pressed="${state.crossAsset.range === id}">${escapeHTML(RANGE_LABELS[id])}</button>`).join("")}
        </div>
      </div>
      <div class="cross-asset-chart-heading">
        <div><strong data-cross-asset-chart-title>跨资产走势</strong><span data-cross-asset-chart-subtitle>只使用共同观察日</span></div>
        <div class="cross-asset-legend" data-cross-asset-legend></div>
      </div>
      <div class="chart-shell chart-shell-main cross-asset-chart" data-cross-asset-chart aria-label="跨资产相对走势"><div class="chart-state">正在准备图表…</div></div>
      <details class="stablecoin-details cross-asset-details">
        <summary>口径和数据源</summary>
        <div><p data-cross-asset-method>比值和相关性都由程序在共同观察日上计算，不用模型补数。</p><dl class="method-grid"><dt>BTC</dt><dd>Coinbase BTC-USD，纽约时间 16:00 收盘</dd><dt>美股</dt><dd>FRED 转发的 S&amp;P 500 日收盘</dd><dt>黄金</dt><dd>Coinbase PAXG-USD 代理，不是伦敦现货金定盘价</dd><dt>美元</dt><dd>美联储广义美元指数（不是 ICE DXY）</dd><dt>缺口处理</dt><dd>不前向填充；只比较双方都有数据的日期</dd></dl></div>
      </details>
    </section>`;
}

function normalizeCrossAssetPoints(points, key) {
  const usable = (points || []).filter((point) => point?.observed_at && numericOrNull(point?.[key]) !== null);
  if (!usable.length) return [];
  const base = Number(usable[0][key]);
  if (!Number.isFinite(base) || base === 0) return [];
  return usable.map((point) => ({observed_at: point.observed_at, value: Number(point[key]) / base * 100}));
}

function crossAssetIntervalChange(points, key) {
  if (!Array.isArray(points) || points.length < 2) return null;
  const first = numericOrNull(points[0]?.[key]);
  const last = numericOrNull(points.at(-1)?.[key]);
  return first === null || last === null || first === 0 ? null : (last / first - 1) * 100;
}

function formatCorrelation(value) {
  const numeric = numericOrNull(value);
  return numeric === null ? "不可用" : roundForDisplay(numeric, 2);
}

function drawCrossAssetDualChart(container, rawPoints, rangeId) {
  if (!container) return;
  const points = (rawPoints || []).filter((point) => point?.observed_at && numericOrNull(point.btc_usd) !== null && numericOrNull(point.broad_dollar_index) !== null);
  if (points.length < 2) {
    container.innerHTML = `<div class="chart-state">这个区间还没有足够的共同观察日。</div>`;
    return;
  }
  const btc = normalizeCrossAssetPoints(points, "btc_usd");
  const dollar = normalizeCrossAssetPoints(points, "broad_dollar_index");
  const sampledDates = downsample(points, 320).map((point) => point.observed_at);
  const sampledSet = new Set(sampledDates);
  const series = [
    {id: "btc", label: "BTC", points: btc.filter((point) => sampledSet.has(point.observed_at))},
    {id: "dollar", label: "广义美元", points: dollar.filter((point) => sampledSet.has(point.observed_at))}
  ];
  const values = series.flatMap((item) => item.points.map((point) => Number(point.value)));
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  if (minimum === maximum) { minimum -= 1; maximum += 1; }
  const padding = Math.max((maximum - minimum) * 0.06, 0.5);
  minimum -= padding;
  maximum += padding;
  const measuredWidth = Math.round(container.clientWidth || 980);
  const width = Math.max(272, Math.min(980, measuredWidth));
  const isNarrow = width <= 420;
  const height = isNarrow ? 210 : 270;
  const left = isNarrow ? 10 : 20;
  const right = isNarrow ? 54 : 76;
  const top = 18;
  const bottom = 34;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const firstTime = Date.parse(`${points[0].observed_at.slice(0, 10)}T00:00:00Z`);
  const lastTime = Date.parse(`${points.at(-1).observed_at.slice(0, 10)}T00:00:00Z`);
  const timeSpan = Math.max(1, lastTime - firstTime);
  const buildCoordinates = (items) => items.map((point) => {
    const timestamp = Date.parse(`${point.observed_at.slice(0, 10)}T00:00:00Z`);
    return [
      left + (timestamp - firstTime) / timeSpan * plotWidth,
      top + (maximum - Number(point.value)) / (maximum - minimum) * plotHeight
    ];
  });
  const lines = series.map((item) => {
    const coordinates = buildCoordinates(item.points);
    const path = coordinates.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
    const last = coordinates.at(-1);
    return `<path class="chart-line cross-asset-line-${item.id}" d="${path}"></path><circle class="cross-asset-dot cross-asset-dot-${item.id}" cx="${last[0].toFixed(2)}" cy="${last[1].toFixed(2)}" r="4"><title>${escapeHTML(`${item.label}：${roundForDisplay(item.points.at(-1).value, 1)}（起点=100）`)}</title></circle>`;
  }).join("");
  const accessible = `BTC 与广义美元${RANGE_LABELS[rangeId] || rangeId}归一化走势，从 ${formatChartDate(points[0].observed_at, rangeId)} 到 ${formatChartDate(points.at(-1).observed_at, rangeId)}`;
  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(accessible)}">
      <line class="chart-grid" x1="${left}" y1="${top}" x2="${left + plotWidth}" y2="${top}"></line>
      <line class="chart-grid" x1="${left}" y1="${top + plotHeight / 2}" x2="${left + plotWidth}" y2="${top + plotHeight / 2}"></line>
      <line class="chart-grid" x1="${left}" y1="${top + plotHeight}" x2="${left + plotWidth}" y2="${top + plotHeight}"></line>
      <line class="chart-zero-line" x1="${left}" y1="${(top + (maximum - 100) / (maximum - minimum) * plotHeight).toFixed(2)}" x2="${left + plotWidth}" y2="${(top + (maximum - 100) / (maximum - minimum) * plotHeight).toFixed(2)}"><title>区间起点 = 100</title></line>
      ${lines}
      <text class="chart-label" x="${left + plotWidth + 8}" y="${top + 4}">${escapeHTML(roundForDisplay(maximum, 1))}</text>
      <text class="chart-label" x="${left + plotWidth + 8}" y="${top + plotHeight + 4}">${escapeHTML(roundForDisplay(minimum, 1))}</text>
      <text class="chart-label" x="${left}" y="${height - 8}">${escapeHTML(formatChartDate(points[0].observed_at, rangeId))}</text>
      <text class="chart-label" text-anchor="end" x="${left + plotWidth}" y="${height - 8}">${escapeHTML(formatChartDate(points.at(-1).observed_at, rangeId))}</text>
    </svg>`;
  bindChartExplorer(container, points.map((point, index) => {
    const timestamp = Date.parse(`${point.observed_at.slice(0, 10)}T00:00:00Z`);
    const btcPoint = btc[index];
    const dollarPoint = dollar[index];
    return {
      observed_at: point.observed_at,
      x: left + (timestamp - firstTime) / timeSpan * plotWidth,
      values: [
        {label: "BTC", formatted: `${roundForDisplay(btcPoint.value, 1)}（起点=100）`, y: top + (maximum - Number(btcPoint.value)) / (maximum - minimum) * plotHeight, tone: 1},
        {label: "广义美元", formatted: `${roundForDisplay(dollarPoint.value, 1)}（起点=100）`, y: top + (maximum - Number(dollarPoint.value)) / (maximum - minimum) * plotHeight, tone: 2}
      ]
    };
  }), {plotTop: top, plotBottom: top + plotHeight, title: "BTC 与广义美元"});
}

async function renderCrossAssetChart(data) {
  const container = document.querySelector("[data-cross-asset-chart]");
  if (!container) return;
  const comparison = state.crossAsset.comparison;
  const rangeId = state.crossAsset.range;
  const requestKey = `${comparison}:${rangeId}`;
  const metricIds = {
    btc_spx: "cross_asset_btc_spx_ratio",
    btc_gold: "cross_asset_btc_gold_ratio",
    broad_dollar_btc: "cross_asset_broad_dollar_btc"
  };
  const metricId = metricIds[comparison];
  const channelComparison = data.cross_asset?.comparisons?.[comparison] || {};
  const answer = document.querySelector("[data-cross-asset-answer]");
  const detail = document.querySelector("[data-cross-asset-detail]");
  const title = document.querySelector("[data-cross-asset-chart-title]");
  const subtitle = document.querySelector("[data-cross-asset-chart-subtitle]");
  const legend = document.querySelector("[data-cross-asset-legend]");
  const method = document.querySelector("[data-cross-asset-method]");
  container.setAttribute("aria-busy", "true");
  container.innerHTML = `<div class="chart-state">正在读取 ${escapeHTML(RANGE_LABELS[rangeId])}历史…</div>`;
  try {
    const payload = await fetchSeriesPayload(metricId, rangeId);
    if (`${state.crossAsset.comparison}:${state.crossAsset.range}` !== requestKey) return;
    const points = payload.points || [];
    if (comparison === "broad_dollar_btc") {
      const btcChange = crossAssetIntervalChange(points, "btc_usd");
      const dollarChange = crossAssetIntervalChange(points, "broad_dollar_index");
      const correlation30 = data.metrics?.cross_asset_btc_broad_dollar_corr_30d?.value;
      const correlation90 = data.metrics?.cross_asset_btc_broad_dollar_corr_90d?.value;
      if (answer) answer.textContent = `BTC ${formatSignedPercent(btcChange)}；广义美元 ${formatSignedPercent(dollarChange)}`;
      if (detail) detail.textContent = `截至 ${formatDate(points.at(-1)?.observed_at || channelComparison.observed_at)}；30 日相关 ${formatCorrelation(correlation30)}，90 日相关 ${formatCorrelation(correlation90)}。`;
      if (title) title.textContent = "BTC 与广义美元走势";
      if (subtitle) subtitle.textContent = "同一起点 = 100；广义美元不是 ICE DXY";
      if (legend) legend.innerHTML = `<span><i class="legend-line legend-btc"></i>BTC</span><span><i class="legend-line legend-dollar"></i>广义美元</span>`;
      if (method) method.textContent = "两条线都把所选区间的第一个共同观察日设为 100。30/90 日数字是日收益率相关性，相关不等于因果。";
      drawCrossAssetDualChart(container, points, rangeId);
    } else {
      const usable = points.filter((point) => numericOrNull(point?.value) !== null);
      const intervalChange = crossAssetIntervalChange(usable, "value");
      const latest = usable.at(-1);
      const normalized = normalizeCrossAssetPoints(usable, "value");
      const isStock = comparison === "btc_spx";
      const target = isStock ? "标普 500" : "黄金";
      if (answer) answer.textContent = `BTC 相对${target}在该区间 ${formatSignedPercent(intervalChange)}`;
      if (detail) detail.textContent = isStock
        ? `截至 ${formatDate(latest?.observed_at)}；BTC ${formatUsd(latest?.btc_usd)}，标普 500 ${roundForDisplay(latest?.sp500, 1)} 点。`
        : `截至 ${formatDate(latest?.observed_at)}；1 枚 BTC 相当于 ${roundForDisplay(latest?.value, 2)} 盎司 PAXG 代表的黄金。`;
      if (title) title.textContent = `BTC / ${target} 相对走势`;
      if (subtitle) subtitle.textContent = "区间起点 = 100；线向上表示 BTC 相对更强";
      if (legend) legend.innerHTML = `<span><i class="legend-line legend-btc"></i>BTC / ${target}</span>`;
      if (method) method.textContent = isStock
        ? "每个共同日期用 BTC-USD 除以标普 500 点位，再把所选区间起点设为 100。上升只表示 BTC 相对跑赢。"
        : "每个共同日期用 BTC-USD 除以 PAXG-USD，再把所选区间起点设为 100。PAXG 是黄金代理，不是伦敦现货金定盘价。";
      drawChart(container, normalized, {label: `BTC / ${target}`, unit: "index", chart_reference: 100}, rangeId);
    }
  } catch (error) {
    if (`${state.crossAsset.comparison}:${state.crossAsset.range}` === requestKey) {
      container.innerHTML = `<div class="chart-state">这组历史暂时读不到。${escapeHTML(error.message || "请稍后刷新")}</div>`;
      if (answer) answer.textContent = "这组比较暂时不可用";
      if (detail) detail.textContent = "不会把缺失数据当成 0，也不影响其他看板数据。";
    }
  } finally {
    if (`${state.crossAsset.comparison}:${state.crossAsset.range}` === requestKey) container.removeAttribute("aria-busy");
  }
}

function selectCrossAssetComparison(button, data, focus = false) {
  state.crossAsset.comparison = button.dataset.crossAssetComparison || "btc_spx";
  document.querySelectorAll("[data-cross-asset-comparison]").forEach((item) => {
    const selected = item === button;
    item.setAttribute("aria-selected", String(selected));
    item.setAttribute("tabindex", selected ? "0" : "-1");
  });
  renderCrossAssetChart(data);
  elements.live.textContent = `已切换到${CROSS_ASSET_LABELS[state.crossAsset.comparison]}`;
  if (focus) button.focus();
}

function bindCrossAssetInteractions(data) {
  document.querySelectorAll("[data-cross-asset-comparison]").forEach((button) => {
    button.addEventListener("click", () => selectCrossAssetComparison(button, data));
    button.addEventListener("keydown", (event) => {
      const direction = {ArrowLeft: -1, ArrowRight: 1, Home: "home", End: "end"}[event.key];
      if (direction === undefined) return;
      event.preventDefault();
      const tabs = [...document.querySelectorAll("[data-cross-asset-comparison]")];
      const current = Math.max(0, tabs.indexOf(button));
      const next = direction === "home" ? 0 : direction === "end" ? tabs.length - 1 : (current + direction + tabs.length) % tabs.length;
      selectCrossAssetComparison(tabs[next], data, true);
    });
  });
  document.querySelectorAll("[data-cross-asset-range]").forEach((button) => button.addEventListener("click", () => {
    state.crossAsset.range = button.dataset.crossAssetRange || "1y";
    document.querySelectorAll("[data-cross-asset-range]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    renderCrossAssetChart(data);
  }));
  requestAnimationFrame(() => renderCrossAssetChart(data));
}

function energyChangeText(metric, windowId = "1w") {
  const item = metric?.changes?.[windowId];
  if (!item || numericOrNull(item.percent_change) === null) return "暂无可比历史";
  return `${CHANGE_LABELS[windowId] || windowId} ${formatSignedPercent(Number(item.percent_change))}`;
}

function energyPanel(data) {
  const energy = data.energy || {};
  const wti = data.metrics?.energy_wti_spot;
  const brent = data.metrics?.energy_brent_spot;
  const spread = data.metrics?.energy_brent_wti_spread;
  const inventoryIds = ["energy_commercial_crude_stocks", "energy_cushing_crude_stocks", "energy_spr_stocks", "energy_gasoline_product_supplied"];
  const inventory = inventoryIds.map((id) => data.metrics?.[id]).filter(Boolean);
  const statusLabel = energy.available_for_analysis ? (energy.status === "ready" ? "已更新" : "部分可用") : "暂不可用";
  const priceAnswer = !wti?.available_for_analysis || !brent?.available_for_analysis
    ? "油价数据不完整，不做方向判断"
    : `WTI ${formatMetricValue(wti, true)}，${energyChangeText(wti)}；Brent ${formatMetricValue(brent, true)}，${energyChangeText(brent)}`;
  const curveNote = energy.curve?.status === "ready"
    ? "WTI 近月曲线已更新"
    : "WTI 近月曲线：当前没有可持续更新的免费官方数据，不用 2024 年旧值补写";
  return `
    <section id="flow-energy" class="dashboard-section energy-section" aria-labelledby="energy-title">
      <div class="section-heading">
        <div><p class="eyebrow">外部通胀与金融条件</p><h2 id="energy-title">油价是在推高通胀，还是在反映需求走弱</h2></div>
        <span class="analysis-state state-${escapeHTML(energy.status || "unavailable")}">${escapeHTML(statusLabel)}</span>
      </div>
      <p class="energy-answer">${escapeHTML(priceAnswer)}。价格只是第一层，还要用每周库存和新闻区分供给冲击与需求走弱。</p>
      <div class="energy-toolbar" role="group" aria-label="选择油价图表内容">
        ${[["price", "WTI / Brent"], ["spread", "Brent-WTI 价差"]].map(([id, label]) => `<button class="chart-switch-button" type="button" data-energy-mode="${id}" aria-pressed="${state.energy.mode === id}">${label}</button>`).join("")}
      </div>
      <div class="energy-chart-heading"><strong data-energy-chart-title>WTI 与 Brent 现货价</strong><span data-energy-chart-subtitle>美元/桶</span></div>
      <div class="chart-shell energy-chart" data-energy-chart><div class="chart-state">正在读取油价历史…</div></div>
      <div class="stablecoin-control-options" role="group" aria-label="选择油价历史区间">
        ${["1m", "3m", "1y", "5y", "all"].map((id) => `<button class="chart-switch-button" type="button" data-energy-range="${id}" aria-pressed="${state.energy.range === id}">${escapeHTML(RANGE_LABELS[id])}</button>`).join("")}
      </div>
      <div class="energy-legend" data-energy-legend><span><i class="legend-line yen-legend-1"></i>WTI</span><span><i class="legend-line yen-legend-2"></i>Brent</span></div>
      <p class="reading-rule" data-energy-method>两条线都是现货价格，不是期货连续合约。</p>
      <div class="energy-structure-row">
        <div><span>Brent-WTI 价差</span><strong>${escapeHTML(spread?.available_for_analysis ? formatMetricValue(spread, true) : "不可用")}</strong><small>${escapeHTML(spread?.observed_at ? `${formatDate(spread.observed_at)} · ${energyChangeText(spread)}` : "无可用日期")}</small></div>
        <p>${escapeHTML(curveNote)}</p>
      </div>
      <div class="energy-inventory">
        <div class="section-heading compact-heading"><div><h3>每周供需验证</h3><p>这些数据不是当日值，每条都保留 EIA 的观察日。</p></div></div>
        <div class="flow-metrics">${genericFlowMetrics(inventory)}</div>
      </div>
      <p class="notice"><strong>不进入流动性公式</strong><span>油价会通过通胀预期、降息路径和企业成本影响风险资产，但它不是美联储账本里的水。</span></p>
    </section>`;
}

async function renderEnergyChart(data) {
  const container = document.querySelector("[data-energy-chart]");
  if (!container) return;
  const requestKey = `${state.energy.mode}:${state.energy.range}`;
  container.setAttribute("aria-busy", "true");
  container.innerHTML = `<div class="chart-state">正在读取 ${escapeHTML(RANGE_LABELS[state.energy.range])}历史…</div>`;
  try {
    const metricId = state.energy.mode === "price" ? "energy_price_comparison" : "energy_brent_wti_spread";
    const payload = await fetchSeriesPayload(metricId, state.energy.range);
    if (`${state.energy.mode}:${state.energy.range}` !== requestKey) return;
    const title = document.querySelector("[data-energy-chart-title]");
    const subtitle = document.querySelector("[data-energy-chart-subtitle]");
    const legend = document.querySelector("[data-energy-legend]");
    const method = document.querySelector("[data-energy-method]");
    if (state.energy.mode === "price") {
      title.textContent = "WTI 与 Brent 现货价";
      subtitle.textContent = "美元/桶";
      legend.innerHTML = `<span><i class="legend-line yen-legend-1"></i>WTI</span><span><i class="legend-line yen-legend-2"></i>Brent</span>`;
      method.textContent = "两条线按共同观察日对齐，都是官方现货价格，不是期货连续合约。";
      drawYenMultiChart(container, payload.points || [], [{key: "wti", label: "WTI"}, {key: "brent", label: "Brent"}], {rangeId: state.energy.range});
    } else {
      title.textContent = "Brent 减 WTI 价差";
      subtitle.textContent = "美元/桶；扩大不等于单一原因";
      legend.innerHTML = `<span><i class="legend-line yen-legend-1"></i>Brent-WTI</span>`;
      method.textContent = "价差需要结合库欣库存、运输瓶颈和国际供给新闻解读。";
      drawChart(container, payload.points || [], data.metrics?.energy_brent_wti_spread || {label: "Brent-WTI", unit: "usd_per_barrel"}, state.energy.range);
    }
  } catch (error) {
    if (`${state.energy.mode}:${state.energy.range}` === requestKey) container.innerHTML = `<div class="chart-state">油价历史暂时读不到。${escapeHTML(error.message || "请稍后刷新")}</div>`;
  } finally {
    if (`${state.energy.mode}:${state.energy.range}` === requestKey) container.removeAttribute("aria-busy");
  }
}

function bindEnergyInteractions(data) {
  document.querySelectorAll("[data-energy-mode]").forEach((button) => button.addEventListener("click", () => {
    state.energy.mode = button.dataset.energyMode || "price";
    document.querySelectorAll("[data-energy-mode]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    renderEnergyChart(data);
  }));
  document.querySelectorAll("[data-energy-range]").forEach((button) => button.addEventListener("click", () => {
    state.energy.range = button.dataset.energyRange || "1y";
    document.querySelectorAll("[data-energy-range]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
    renderEnergyChart(data);
  }));
  requestAnimationFrame(() => renderEnergyChart(data));
}

function renderTransmission(data) {
  const fed = data.layers.find((layer) => layer.group_id === "fed_balance_sheet") || {metrics: []};
  const fiscal = data.layers.find((layer) => layer.group_id === "fiscal_cash") || {metrics: []};
  const market = data.layers.find((layer) => layer.group_id === "market_transmission") || {metrics: []};
  const remainingMarket = market.metrics.filter((metric) => !["treasury_3m_yield", "treasury_2y_yield", "treasury_10y_yield", "treasury_30y_yield"].includes(metric.metric_id));
  const steps = [
    {id: "fed_balance_sheet", title: "宏观账本：美联储", note: fed.flow_note, body: `<div class="flow-metrics">${genericFlowMetrics(fed.metrics)}</div>`},
    {id: "fiscal_cash", title: "宏观账本：财政部", note: fiscal.flow_note, body: `<div class="flow-metrics">${genericFlowMetrics(fiscal.metrics)}</div>`},
    {id: "money_market", title: "融资与定价：短期资金", note: "先看四个隔夜利率之间的差值，再判断现金是否真的变紧。", body: fundingPanel(data)},
    {id: "market_transmission", title: "融资与定价：利率曲线与市场预期", note: "收益率曲线告诉我们不同期限的利率定价；预测市场补充说明交易者当前押注什么。", body: `${treasuryCurvePanel(data)}${marketExpectationsPanel(data)}<div class="flow-metrics">${genericFlowMetrics(remainingMarket)}</div>`}
  ].map((step) => `
    <section id="flow-${escapeHTML(step.id)}" class="flow-step group-${escapeHTML(step.id)}">
      <article class="flow-panel"><h2>${escapeHTML(step.title)}</h2><p>${escapeHTML(step.note || "")}</p>${step.body}</article>
    </section>`).join("");

  document.querySelector("#view-transmission").innerHTML = `
    <header class="page-header">
      <div><p class="eyebrow">从账本到市场</p><h1 id="transmission-title">先看资金价格，再看市场押注</h1></div>
      <p>官方数据回答“发生了什么”；利差和曲线回答“资金是否变紧”；预测市场只补充“交易者正在押什么”。</p>
    </header>
    <nav class="transmission-jump-nav" aria-label="快速查看传导阶段">
      <button type="button" data-flow-target="flow-fed_balance_sheet">联储财政</button>
      <button type="button" data-flow-target="flow-money_market">短端融资</button>
      <button type="button" data-flow-target="flow-market_transmission">市场定价</button>
      <button type="button" data-flow-target="flow-yen-carry">日元套息</button>
      <button type="button" data-flow-target="flow-energy">油价</button>
      <button type="button" data-flow-target="flow-cross-asset">相对强弱</button>
      <button type="button" data-flow-target="flow-crypto">加密管道</button>
    </nav>
    <div class="flow-map">${steps}</div>
    ${yenCarryPanel(data)}
    ${energyPanel(data)}
    ${crossAssetPanel(data)}
    <section class="dashboard-section" aria-labelledby="destinations-title">
      <div class="section-heading"><div><h2 id="destinations-title">股票和加密在最后一站</h2><p>同样的流动性环境，遇到不同的增长、通胀和杠杆状态，结果可能完全不同。</p></div></div>
      <div class="transmission-destinations">
        <article class="destination"><h3>股票</h3><p>利率下降有利于估值和融资，但如果背后是盈利衰退，股价仍可能承压。</p></article>
        <article class="destination"><h3>加密</h3><p>美元融资环境决定大背景；${escapeHTML(stablecoinDestinationSummary(data))}</p></article>
      </div>
    </section>
    ${cryptoMarketPanel(data)}`;

  bindCurveChartExplorer(document.querySelector(".curve-chart-shell"), data.treasury_curve);

  document.querySelectorAll("[data-flow-mini-metric]").forEach((container) => {
    const metric = metricById(container.dataset.flowMiniMetric);
    const recent = pointsWithinDays(metric?.sparkline || [], 31);
    requestAnimationFrame(() => drawMiniChart(container, recent.points, metric, recent.label));
  });
  document.querySelectorAll("[data-derived-mini]").forEach((container) => {
    const metric = metricById(container.dataset.derivedMini);
    const recent = pointsWithinDays(metric?.history || [], 366);
    requestAnimationFrame(() => drawMiniChart(container, recent.points, metric, recent.label));
  });
  document.querySelectorAll("[data-flow-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.flowTarget || "");
      if (!target) return;
      document.querySelectorAll("[data-flow-target]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
      target.scrollIntoView({behavior: "smooth", block: "start"});
      elements.live.textContent = `已跳到${button.textContent}`;
    });
  });
  bindMarketExpectationInteractions();
  bindYenCarryInteractions(data);
  bindEnergyInteractions(data);
  bindCrossAssetInteractions(data);
  bindCryptoMarketInteractions(data);
}

function ledgerMetric(metric, chartAvailable = true) {
  const delta = formatMetricDelta(metric);
  const quality = QUALITY_LABELS[metric.quality_status] || "状态未知";
  const changes = ["1w", "1m", "3m", "1y"].map((windowId) => {
    const item = metric.changes?.[windowId] || {};
    return `<div><span>比 ${escapeHTML(CHANGE_LABELS[windowId])}前</span><strong>${escapeHTML(formatChangeValue(metric, item.change))}</strong></div>`;
  }).join("");
  return `
    <details class="metric-disclosure" data-group="${escapeHTML(metric.group || "derived")}" data-metric-id="${escapeHTML(metric.metric_id || metric.id)}">
      <summary class="metric-summary">
        <span class="metric-name"><strong>${escapeHTML(metric.label)}</strong><span>${escapeHTML(GROUP_LABELS[metric.group] || (metric.group === "derived" ? "公式与市场概率" : "其他指标"))} · ${escapeHTML(formatDate(metric.observed_at))}</span></span>
        <span class="metric-reading"><strong>${escapeHTML(formatMetricValue(metric))}</strong><span class="${delta.className}">${escapeHTML(delta.text)}</span></span>
        <svg class="disclosure-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7.5 5 5 5-5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7"></path></svg>
      </summary>
      <div class="metric-detail">
        <div class="metric-definition">
          <span class="quality-pill ${qualityClass(metric.quality_status)}">${escapeHTML(quality)}</span>
          <div><strong>它是什么</strong><p>${escapeHTML(metric.description)}</p></div>
          <div><strong>平时怎么读</strong><p>${escapeHTML(metric.direction_note)}</p></div>
        </div>
        <div class="metric-change-grid" aria-label="不同时间长度的变化">${changes}</div>
        ${chartAvailable ? `<div class="range-controls" role="group" aria-label="选择历史区间">
          ${Object.entries(RANGE_LABELS).map(([id, label]) => `<button class="range-button" type="button" data-range="${id}" aria-pressed="${id === "1y"}">${escapeHTML(label)}</button>`).join("")}
        </div>
        <div class="chart-shell" data-chart-for="${escapeHTML(metric.metric_id || metric.id)}"><div class="chart-state">展开后显示一年走势</div></div>` : `<div class="chart-state">这是公式结果或市场概率，当前发布包只保留本轮证据，不会凭空补历史线。</div>`}
        <dl class="method-grid">
          <dt>这条数据的日期</dt><dd>${escapeHTML(metric.observed_at || "不可用")}</dd>
          <dt>用来做周比较的日期</dt><dd>${escapeHTML(metric.week_prior_observed_at || "历史不足")}</dd>
          <dt>多久公布一次</dt><dd>${escapeHTML(formatCadence(metric.cadence))}</dd>
          <dt>数据来自哪里</dt><dd>${escapeHTML(metric.source_name || "未知来源")}</dd>
        </dl>
        <a class="inline-link" href="${escapeHTML(safeUrl(metric.source_url))}" target="_blank" rel="noreferrer">查看原始数据 <span aria-hidden="true">↗</span></a>
      </div>
    </details>`;
}

function renderLedger(data) {
  const baseMetrics = Object.values(data.metrics || {});
  const derivedMetrics = Object.values(data.derived_metrics || {}).map((metric) => ({
    description: "由页面所列基础数据或市场概率确定性生成。",
    direction_note: "请结合数值日期、可用状态和对应专题解读。",
    group: "derived",
    ...metric,
  }));
  const proxyMetric = {...data.proxy, metric_id: "net_liquidity_proxy", group: "derived", description: `公式：${data.proxy.formula}。`, direction_note: data.proxy.trend_method};
  const metrics = [proxyMetric, ...baseMetrics, ...derivedMetrics].filter((metric, index, items) => {
    const id = metric.metric_id || metric.id;
    return id && items.findIndex((candidate) => (candidate.metric_id || candidate.id) === id) === index;
  });
  const filters = [
    ["all", "全部"],
    ["fed_balance_sheet", "联储"],
    ["fiscal_cash", "财政"],
    ["money_market", "货币市场"],
    ["market_transmission", "市场传导"],
    ["crypto_liquidity", "加密内部"],
    ["crypto_etf", "ETF"],
    ["crypto_derivatives", "衍生品"],
    ["cross_asset", "跨资产"],
    ["yen_carry", "日元套息"],
    ["energy", "原油"],
    ["derived", "公式与概率"]
  ];
  document.querySelector("#view-ledger").innerHTML = `
    <header class="page-header">
      <div><p class="eyebrow">指标与证据</p><h1 id="ledger-title">${metrics.length} 条指标和本轮证据</h1></div>
      <p>点开任意一条，就能看 1 周、1 月、3 月、1 年的变化，也能切换完整历史。没有拿到的数据会写“不可用”，不会写成零。</p>
    </header>
    <div class="filters" role="group" aria-label="按宏观层级筛选">
      ${filters.map(([id, label]) => `<button class="filter-button" type="button" data-filter="${id}" aria-pressed="${id === state.ledgerFilter}">${escapeHTML(label)}</button>`).join("")}
    </div>
    <div class="ledger-list">${metrics.map((metric) => ledgerMetric(metric, Boolean((data.metrics || {})[metric.metric_id]) || metric.metric_id === "net_liquidity_proxy")).join("")}</div>`;
  bindLedgerInteractions();
  applyLedgerFilter();
}

function sourceDisclosure(source) {
  const rate = numericOrNull(source.eligible_rate_14d);
  const rateText = rate === null ? "样本不足" : `${roundForDisplay(rate * 100, 0)}%`;
  const selected = source.selected ? "这次使用" : "备用或用来对照";
  const quality = QUALITY_LABELS[source.quality_status] || "状态未知";
  const note = source.release_schedule_note
    ? `<div class="notice"><strong>它通常什么时候更新</strong><span>${escapeHTML(source.release_schedule_note)}</span></div>`
    : "";
  const error = source.error
    ? `<div class="notice notice-warning"><strong>最近错误</strong><span>${escapeHTML(source.error)}</span></div>`
    : "";
  return `
    <details class="source-disclosure">
      <summary class="source-row">
        <span class="source-name"><strong>${escapeHTML(source.metric_label)}</strong><span>${escapeHTML(source.source_owner || source.name)} · ${escapeHTML(selected)}</span></span>
        <span class="source-status"><span class="quality-pill ${qualityClass(source.quality_status)}">${escapeHTML(quality)}</span><span>最近成功率 ${escapeHTML(rateText)}</span></span>
        <svg class="disclosure-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7.5 5 5 5-5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7"></path></svg>
      </summary>
      <div class="source-detail">
        <dl>
          <dt>具体来源</dt><dd>${escapeHTML(source.name || source.source_id)}</dd>
          <dt>是否官方</dt><dd>${escapeHTML(AUTHORITY_LABELS[source.authority] || source.authority)}</dd>
          <dt>数据日期</dt><dd>${escapeHTML(source.observed_at || "不可用")}</dd>
          <dt>看板获取时间</dt><dd>${escapeHTML(formatDateTime(source.fetched_at))}</dd>
          <dt>多久更新一次</dt><dd>${escapeHTML(formatCadence(source.cadence))}</dd>
          <dt>最近观察样本</dt><dd>${Number(source.observed_days_14d || 0)} 个观测日</dd>
        </dl>
        ${note}${error}
        <a href="${escapeHTML(safeUrl(source.url))}" target="_blank" rel="noreferrer">查看原始来源 <span aria-hidden="true">↗</span></a>
      </div>
    </details>`;
}

function renderData(data) {
  const status = data.status;
  const currentStatusCode = effectiveDataStatus(status);
  const serviceCode = status.service_status?.code || "unknown";
  const updateCode = status.update_status?.code || "unknown";
  const updateLabel = updateCode === "completed" ? "最近一次更新完成" : updateCode === "running" ? "正在更新" : updateCode === "unknown" ? "更新状态未知" : `更新状态：${updateCode}`;
  const soak = status.soak || {};
  const agentSoak = status.agent_soak || {};
  const observed = Number(soak.observed_distinct_days || 0);
  const required = Math.max(1, Number(soak.required_distinct_days || 14));
  const agentObserved = Number(agentSoak.observed_distinct_dates || 0);
  const agentRequired = Math.max(1, Number(agentSoak.required_distinct_dates || 14));
  const progress = Math.min(100, observed / required * 100);
  const soakCode = soak.status || "not_ready";
  const soakLabel = SOAK_STATUS_LABELS[soakCode] || "稳定性状态未知";
  const unavailable = status.unavailable.length
    ? status.unavailable.map((metric) => metric.label).join("、")
    : "无";
  const anomalyMap = new Map();
  (status.unavailable || []).forEach((metric) => anomalyMap.set(metric.metric_id || metric.label, `${metric.label}：本轮不可用`));
  (status.runtime_stale || []).forEach((metric) => anomalyMap.set(metric.metric_id || metric.label, `${metric.label}：数据已过期`));
  (status.warnings || []).forEach((warning, index) => anomalyMap.set(`warning-${index}`, plainChannelIssue(warning)));
  const anomalyItems = [...anomalyMap.values()];
  const anomalyPanel = anomalyItems.length
    ? `<section class="dashboard-section" aria-labelledby="anomaly-title"><div class="section-heading"><div><p class="eyebrow">需要先知道</p><h2 id="anomaly-title">本轮有 ${anomalyItems.length} 项数据问题</h2></div></div><ul class="agent-unknown-list">${anomalyItems.map((item) => `<li>${escapeHTML(item)}</li>`).join("")}</ul></section>`
    : `<section class="dashboard-section" aria-labelledby="anomaly-title"><div class="section-heading"><div><p class="eyebrow">需要先知道</p><h2 id="anomaly-title">本轮没有会改变解读的数据问题</h2></div></div></section>`;
  document.querySelector("#view-data").innerHTML = `
    <header class="page-header">
      <div><p class="eyebrow">每个数字从哪来</p><h1 id="data-title">${status.total_metric_count} 条核心指标，${data.sources.length} 条来源线路</h1></div>
      <p>这里会告诉你：更新有没有成功、这次用了哪个来源、数据是不是太旧。</p>
    </header>

    ${anomalyPanel}
    <section class="dashboard-section" aria-labelledby="gate-title">
      <div class="section-heading"><div><h2 id="gate-title">本次更新和长期稳定性</h2><p>一次更新成功，不代表数据通道已经完成连续观察。</p></div></div>
      <div class="status-split-grid">
        <div><span>当前数据</span><strong>${status.data_status?.runtime_eligible_metric_count ?? status.eligible_metric_count}/${status.total_metric_count} 条现在可用</strong><span class="status-pill ${statusClass(currentStatusCode)}">${escapeHTML(STATUS_LABELS[currentStatusCode] || "状态未知")}</span></div>
        <div><span>稳定性观察</span><strong>${observed}/${required} 个数据日</strong><span class="status-pill ${soakStatusClass(soakCode)}">${escapeHTML(soakLabel)}</span></div>
      </div>
      <div class="soak-progress">
        <div class="progress-header"><strong>${observed}/${required} 天</strong><span>${roundForDisplay(progress, 0)}%</span></div>
        <progress class="progress-track" aria-label="稳定性观察进度" max="${required}" value="${Math.min(observed, required)}">${roundForDisplay(progress, 0)}%</progress>
      </div>
      <div class="notice"><strong>观察仍在继续</strong><span>已记录的 ${observed} 个数据日中，可正常发布的比例是 ${roundForDisplay(Number(soak.publishable_rate || 0) * 100, 0)}%。Agent 另有 ${agentObserved}/${agentRequired} 个观察日。</span></div>
      <dl class="method-grid">
        <dt>网页服务</dt><dd>${serviceCode === "ok" ? "正常" : "异常"}</dd>
        <dt>自动更新</dt><dd>${escapeHTML(updateLabel)}</dd>
        <dt>当前数据</dt><dd>${escapeHTML(STATUS_LABELS[currentStatusCode] || "状态未知")}</dd>
        <dt>这次更新编号</dt><dd>${escapeHTML(data.snapshot.run_id || "无")}</dd>
        <dt>完成时间</dt><dd>${escapeHTML(formatDateTime(data.snapshot.completed_at))}（北京时间）</dd>
        <dt>拿到的数据</dt><dd>${status.eligible_metric_count}/${status.total_metric_count} 条通过检查</dd>
        <dt>没有拿到</dt><dd>${escapeHTML(unavailable)}</dd>
        <dt>历史数据被修改</dt><dd>${Number(data.snapshot.revision_count_detected || 0)} 条</dd>
        <dt>不同来源对不上</dt><dd>${Number(data.snapshot.reconciliation_issues?.length || 0)} 条</dd>
        <dt>Agent 网页状态</dt><dd>${data.agent_analysis?.is_current ? "本轮分析已显示" : "等待本轮分析"}</dd>
        <dt>Agent 稳定性观察</dt><dd>${agentObserved}/${agentRequired} 个观察日</dd>
      </dl>
    </section>

    <section class="dashboard-section" aria-labelledby="sources-title">
      <div class="section-heading"><div><h2 id="sources-title">逐条检查来源</h2><p>“这次使用”的数据进入页面；备用来源只在主线路坏掉或需要对照时使用。</p></div></div>
      <div class="source-list">${data.sources.map(sourceDisclosure).join("")}</div>
    </section>

    <section class="dashboard-section" aria-labelledby="method-title">
      <div class="section-heading"><div><h2 id="method-title">哪些是事实，哪些是分析</h2><p>原始数据、公式结果和 Agent 解读分开显示，不会混成一句话。</p></div></div>
      <dl class="method-grid">
        <dt><span class="evidence-label">原始数据</span></dt><dd>数字、日期和来源状态来自官方线路或官方数据转发站。</dd>
        <dt><span class="evidence-label">公式算出来</span></dt><dd>流动性参考值和三个分项都使用页面公开的公式，任何人都可以复算。</dd>
        <dt><span class="evidence-label">Agent 解读</span></dt><dd>${escapeHTML(data.methodology.agent_analysis.message)} Agent 只解释信号组合，不改数字，也不代替公开公式。</dd>
        <dt>没有数据时</dt><dd>显示“不可用”，永远不会把缺失数据写成 0。</dd>
      </dl>
    </section>`;
}

function bindOverviewInteractions() {
  const proxy = state.data?.proxy;
  const mainChart = document.querySelector("[data-main-chart]");
  if (mainChart && proxy) {
    requestAnimationFrame(() => drawChart(mainChart, proxy.trend || [], proxy, "1y"));
  }

  document.querySelectorAll("[data-mini-metric]").forEach((container) => {
    const metric = metricById(container.dataset.miniMetric);
    requestAnimationFrame(() => drawMiniChart(container, metric?.sparkline || [], metric));
  });

  document.querySelectorAll(".trend-range-button").forEach((button) => {
    button.addEventListener("click", async () => {
      document.querySelectorAll(".trend-range-button").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
      const rangeId = button.dataset.range || "1y";
      if (rangeId === "1y" && proxy?.trend?.length) {
        const previous = state.seriesRequests.get(mainChart);
        if (previous) previous.controller.abort();
        state.seriesRequests.delete(mainChart);
        drawChart(mainChart, proxy.trend, proxy, rangeId);
        return;
      }
      await loadSeries("net_liquidity_proxy", rangeId, mainChart);
    });
  });
}

function bindLedgerInteractions() {
  document.querySelectorAll("#view-ledger .filter-button").forEach((button) => {
    button.addEventListener("click", () => {
      state.ledgerFilter = button.dataset.filter || "all";
      document.querySelectorAll(".filter-button").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
      applyLedgerFilter();
    });
  });

  document.querySelectorAll("#view-ledger .metric-disclosure").forEach((details) => {
    details.addEventListener("toggle", () => {
      if (!details.open || details.dataset.loaded === "true") return;
      details.dataset.loaded = "true";
      const metricId = details.dataset.metricId;
      const metric = metricById(metricId);
      drawChart(details.querySelector(".chart-shell"), metric?.sparkline || [], metric, "1y");
    });
  });

  document.querySelectorAll("#view-ledger .range-button").forEach((button) => {
    button.addEventListener("click", async () => {
      const details = button.closest(".metric-disclosure");
      const metricId = details?.dataset.metricId;
      if (!metricId) return;
      details.open = true;
      details.querySelectorAll(".range-button").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
      await loadSeries(metricId, button.dataset.range || "1y", details.querySelector(".chart-shell"));
    });
  });
}

function applyLedgerFilter() {
  document.querySelectorAll(".metric-disclosure").forEach((details) => {
    details.hidden = state.ledgerFilter !== "all" && details.dataset.group !== state.ledgerFilter;
  });
}

function openEvidenceMetric(metricId, evidenceLink = null) {
  if (!metricId) return;
  state.ledgerFilter = "all";
  setView("ledger", true);
  requestAnimationFrame(() => {
    const details = [...document.querySelectorAll("#view-ledger .metric-disclosure")]
      .find((item) => item.dataset.metricId === metricId);
    if (!details) {
      elements.live.textContent = "这条证据当前没有可展开的指标详情";
      return;
    }
    details.hidden = false;
    details.open = true;
    const analysisId = evidenceLink?.dataset.evidenceAnalysis;
    const evidenceDate = evidenceLink?.dataset.evidenceDate;
    const windowId = evidenceLink?.dataset.evidenceWindow;
    const note = [analysisId ? `分析 ${analysisId}` : "", evidenceDate ? `证据日期 ${evidenceDate}` : "", windowId ? `对比窗口 ${CHANGE_LABELS[windowId] || windowId}` : ""].filter(Boolean).join(" · ");
    let evidenceMeta = details.querySelector(".evidence-context-note");
    if (note) {
      if (!evidenceMeta) {
        evidenceMeta = document.createElement("p");
        evidenceMeta.className = "evidence-context-note";
        details.querySelector(".metric-detail")?.prepend(evidenceMeta);
      }
      evidenceMeta.textContent = `你从 Agent 证据进入：${note}。下方数值为当前发布版，若日期不同，以上述证据日期为准。`;
    }
    details.scrollIntoView({behavior: "smooth", block: "start"});
    details.querySelector("summary")?.focus({preventScroll: true});
  });
}

function downsample(points, maximum = 320) {
  if (points.length <= maximum) return points;
  const interior = points.slice(1, -1);
  const bucketCount = Math.max(1, Math.floor((maximum - 2) / 2));
  const sampled = [points[0]];
  for (let bucket = 0; bucket < bucketCount; bucket += 1) {
    const start = Math.floor(bucket * interior.length / bucketCount);
    const end = Math.floor((bucket + 1) * interior.length / bucketCount);
    const slice = interior.slice(start, Math.max(start + 1, end));
    if (!slice.length) continue;
    let minimumIndex = 0;
    let maximumIndex = 0;
    slice.forEach((point, index) => {
      if (Number(point.value) < Number(slice[minimumIndex].value)) minimumIndex = index;
      if (Number(point.value) > Number(slice[maximumIndex].value)) maximumIndex = index;
    });
    [...new Set([minimumIndex, maximumIndex])]
      .sort((left, right) => left - right)
      .forEach((index) => sampled.push(slice[index]));
  }
  sampled.push(points.at(-1));
  return sampled.slice(0, maximum);
}

function chartGapThresholdDays(metric) {
  const cadence = String(metric?.cadence || "");
  if (cadence.includes("quarter")) return 120;
  if (cadence.includes("month")) return 45;
  if (cadence.includes("week")) return 15;
  if (cadence.includes("continuous")) return 3;
  return 5;
}

function chartSegments(rawPoints, metric) {
  const valid = (rawPoints || []).filter((point) => point?.observed_at && numericOrNull(point.value) !== null);
  const thresholdMs = chartGapThresholdDays(metric) * 86_400_000;
  const segments = [];
  let current = [];
  valid.forEach((point) => {
    const time = Date.parse(`${point.observed_at.slice(0, 10)}T00:00:00Z`);
    const previous = current.at(-1);
    const previousTime = previous ? Date.parse(`${previous.observed_at.slice(0, 10)}T00:00:00Z`) : null;
    if (previousTime !== null && time - previousTime > thresholdMs) {
      if (current.length) segments.push(current);
      current = [];
    }
    current.push(point);
  });
  if (current.length) segments.push(current);
  return segments;
}

function chartDataTable(points, metric, rangeId) {
  const rows = points.slice(-30).reverse().map((point) => `
    <tr>
      <td>${escapeHTML(formatChartDate(point.observed_at, rangeId))}</td>
      <td>${escapeHTML(chartAxisValue(point.value, metric))}</td>
    </tr>`).join("");
  return `
    <details class="chart-data-table">
      <summary>查看数据明细（${points.length} 条）</summary>
      <div class="chart-data-scroll">
        <table><thead><tr><th>日期</th><th>数值</th></tr></thead><tbody>${rows}</tbody></table>
      </div>
      ${points.length > 30 ? `<p>表格显示最近 30 条；接口保留本时间范围的全部 ${points.length} 条数据。</p>` : ""}
    </details>`;
}

function chartAxisValue(value, metric, compact = false) {
  const numeric = Number(value);
  const signed = Boolean(metric?.chart_signed);
  const sign = numeric > 0 && signed ? "+" : numeric < 0 ? "−" : "";
  const absolute = Math.abs(numeric);
  if (metric?.unit === "usd_millions") {
    const formatted = formatUsdMillions(numeric, signed);
    return compact ? formatted.replace("美元", "") : formatted;
  }
  if (metric?.unit === "usd_billions") return `${sign}${roundForDisplay(absolute * 10, 2)} 亿${compact ? "" : "美元"}`;
  if (metric?.unit === "percent") return `${sign}${roundForDisplay(absolute, 2)}%`;
  if (metric?.unit === "annualized_percent" || metric?.unit === "percentage_points") return `${sign}${roundForDisplay(absolute, 2)}%`;
  if (metric?.unit === "basis_points") return `${sign}${roundForDisplay(absolute, 2)} 个基点`;
  if (metric?.unit === "jpy_per_usd") return `${sign}${roundForDisplay(absolute, 2)}`;
  if (metric?.unit === "contracts") return `${sign}${roundForDisplay(absolute, 0)} 张`;
  if (metric?.unit === "probability") return `${sign}${roundForDisplay(absolute * 100, 1)}%`;
  if (metric?.unit === "gold_ounces") return `${sign}${roundForDisplay(absolute, 2)} 盎司`;
  if (metric?.unit === "usd_per_barrel") return `${sign}${roundForDisplay(absolute, 2)}`;
  if (metric?.unit === "thousand_barrels" || metric?.unit === "thousand_barrels_per_day") return `${sign}${roundForDisplay(absolute / 1000, 1)}`;
  if (metric?.unit === "correlation") return `${sign}${roundForDisplay(absolute, 2)}`;
  return `${sign}${roundForDisplay(absolute, 3)}`;
}

function pointsWithinDays(rawPoints, days) {
  const points = (rawPoints || []).filter((point) => point?.observed_at);
  if (points.length < 2) return { points, label: "最近几次" };
  const latest = Date.parse(`${points.at(-1).observed_at.slice(0, 10)}T00:00:00Z`);
  const cutoff = latest - days * 86_400_000;
  const recent = points.filter((point) => Date.parse(`${point.observed_at.slice(0, 10)}T00:00:00Z`) >= cutoff);
  const labels = {31: "过去一个月", 93: "过去三个月", 366: "过去一年", 1827: "过去五年"};
  return recent.length >= 2
    ? { points: recent, label: labels[days] || `过去 ${days} 天` }
    : { points: points.slice(-8), label: "最近几次" };
}

let chartExplorerSequence = 0;

function chartLegend(items, extraClass = "") {
  const entries = (items || []).filter((item) => item?.label);
  if (!entries.length) return "";
  return `<div class="chart-legend ${escapeHTML(extraClass)}" aria-label="图例">${entries.map((item) => `
    <span><i class="chart-legend-swatch chart-tone-${Number(item.tone) || 1}"></i>${escapeHTML(item.label)}</span>`).join("")}</div>`;
}

function bindChartExplorer(container, samples, {plotTop = 0, plotBottom = 100, title = "图表"} = {}) {
  const svg = container?.querySelector("svg");
  const usable = (samples || []).filter((sample) => Number.isFinite(sample?.x) && Array.isArray(sample?.values) && sample.values.length);
  if (!container || !svg || !usable.length) return;

  const namespace = "http://www.w3.org/2000/svg";
  const viewBox = svg.viewBox?.baseVal;
  const viewWidth = viewBox?.width || 1;
  const tooltipId = `chart-tooltip-${++chartExplorerSequence}`;
  const tooltip = document.createElement("div");
  tooltip.className = `chart-tooltip${container.classList.contains("mini-chart") ? " chart-tooltip-compact" : ""}`;
  tooltip.id = tooltipId;
  tooltip.setAttribute("role", "status");
  tooltip.setAttribute("aria-live", "polite");
  tooltip.hidden = true;
  container.appendChild(tooltip);

  const layer = document.createElementNS(namespace, "g");
  layer.classList.add("chart-hover-layer");
  layer.setAttribute("aria-hidden", "true");
  const guide = document.createElementNS(namespace, "line");
  guide.classList.add("chart-hover-guide");
  guide.setAttribute("y1", String(plotTop));
  guide.setAttribute("y2", String(plotBottom));
  layer.appendChild(guide);
  svg.appendChild(layer);

  svg.setAttribute("tabindex", "0");
  svg.setAttribute("focusable", "true");
  svg.setAttribute("aria-describedby", tooltipId);
  svg.classList.add("chart-explorer");

  let activeIndex = usable.length - 1;
  let pinned = false;

  const hide = () => {
    tooltip.hidden = true;
    layer.hidden = true;
  };
  const show = (index) => {
    activeIndex = Math.max(0, Math.min(usable.length - 1, index));
    const sample = usable[activeIndex];
    guide.setAttribute("x1", sample.x.toFixed(2));
    guide.setAttribute("x2", sample.x.toFixed(2));
    layer.querySelectorAll("circle").forEach((node) => node.remove());
    sample.values.forEach((item) => {
      if (!Number.isFinite(item.y)) return;
      const marker = document.createElementNS(namespace, "circle");
      marker.classList.add("chart-hover-dot", `chart-tone-${Number(item.tone) || 1}`);
      marker.setAttribute("cx", sample.x.toFixed(2));
      marker.setAttribute("cy", Number(item.y).toFixed(2));
      marker.setAttribute("r", "4");
      layer.appendChild(marker);
    });
    const heading = sample.heading || formatChartDate(sample.observed_at, "all");
    tooltip.innerHTML = `<strong>${escapeHTML(heading)}</strong>${sample.values.map((item) => `
      <span><i class="chart-tooltip-swatch chart-tone-${Number(item.tone) || 1}"></i><b>${escapeHTML(item.label || title)}</b><em>${escapeHTML(item.formatted)}</em></span>`).join("")}`;
    tooltip.style.left = `${Math.max(18, Math.min(82, sample.x / viewWidth * 100))}%`;
    tooltip.hidden = false;
    layer.hidden = false;
    svg.setAttribute("aria-label", `${title}，${heading}，${sample.values.map((item) => `${item.label} ${item.formatted}`).join("，")}`);
  };
  const nearestIndex = (clientX) => {
    const rect = svg.getBoundingClientRect();
    const svgX = (clientX - rect.left) / Math.max(1, rect.width) * viewWidth;
    let nearest = 0;
    usable.forEach((sample, index) => {
      if (Math.abs(sample.x - svgX) < Math.abs(usable[nearest].x - svgX)) nearest = index;
    });
    return nearest;
  };

  svg.addEventListener("pointermove", (event) => {
    if (event.pointerType === "touch") return;
    pinned = false;
    show(nearestIndex(event.clientX));
  });
  svg.addEventListener("pointerleave", () => { if (!pinned) hide(); });
  svg.addEventListener("click", (event) => {
    pinned = true;
    show(nearestIndex(event.clientX));
  });
  svg.addEventListener("focus", () => show(activeIndex));
  svg.addEventListener("blur", () => { if (!pinned) hide(); });
  svg.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(event.key)) return;
    event.preventDefault();
    if (event.key === "Escape") {
      pinned = false;
      hide();
      return;
    }
    pinned = true;
    if (event.key === "Home") activeIndex = 0;
    else if (event.key === "End") activeIndex = usable.length - 1;
    else activeIndex += event.key === "ArrowRight" ? 1 : -1;
    show(activeIndex);
  });
  hide();
}

function drawMiniChart(container, rawPoints, metric, periodLabel = "过去一年") {
  if (!container) return;
  const segments = chartSegments(rawPoints, metric);
  const points = segments.flatMap((segment) => downsample(segment, Math.max(8, Math.floor(120 / Math.max(1, segments.length)))).map((point, index) => ({...point, _segmentStart: index === 0})));
  if (points.length < 2) {
    container.innerHTML = `<span class="mini-chart-empty">历史不足</span>`;
    return;
  }
  const values = points.map((point) => Number(point.value));
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  if (minimum === maximum) {
    minimum -= 1;
    maximum += 1;
  }
  const width = 180;
  const height = 58;
  const padding = 4;
  const firstTime = Date.parse(`${points[0].observed_at.slice(0, 10)}T00:00:00Z`);
  const lastTime = Date.parse(`${points.at(-1).observed_at.slice(0, 10)}T00:00:00Z`);
  const timeSpan = Math.max(1, lastTime - firstTime);
  const coordinates = points.map((point) => {
    const time = Date.parse(`${point.observed_at.slice(0, 10)}T00:00:00Z`);
    const x = padding + (time - firstTime) / timeSpan * (width - padding * 2);
    const y = padding + (maximum - Number(point.value)) / (maximum - minimum) * (height - padding * 2);
    return [x, y];
  });
  const path = coordinates.map(([x, y], index) => `${points[index]._segmentStart ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
  const last = coordinates.at(-1);
  const label = `${metric?.short_label || "指标"}${periodLabel}，从 ${chartAxisValue(values[0], metric)} 变为 ${chartAxisValue(values.at(-1), metric)}`;
  container.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(label)}">
      <path class="mini-chart-baseline" d="M${padding} ${height - padding}H${width - padding}"></path>
      <path class="mini-chart-line" d="${path}"></path>
      <circle class="mini-chart-dot" cx="${last[0].toFixed(2)}" cy="${last[1].toFixed(2)}" r="3"></circle>
    </svg>`;
  bindChartExplorer(container, points.map((point, index) => ({
    observed_at: point.observed_at,
    x: coordinates[index][0],
    values: [{label: metric?.short_label || metric?.label || "数值", formatted: chartAxisValue(point.value, metric), y: coordinates[index][1], tone: 1}]
  })), {plotTop: padding, plotBottom: height - padding, title: metric?.short_label || metric?.label || "指标"});
}

function drawSignedBarChart(container, rawPoints, metric, rangeId) {
  if (!container) return;
  const points = (rawPoints || []).filter((point) => numericOrNull(point?.value) !== null);
  if (points.length < 2) {
    container.innerHTML = `<div class="chart-state">${points.length ? "这个时间段只有一个已结算交易日，还看不出资金流趋势。" : "这个时间段还没有已结算数据，看板不会把空值画成零。"}</div>`;
    return;
  }
  const values = points.map((point) => Number(point.value));
  let minimum = Math.min(0, ...values);
  let maximum = Math.max(0, ...values);
  if (minimum === maximum) {
    minimum -= 1;
    maximum += 1;
  }
  const span = maximum - minimum;
  minimum -= span * 0.06;
  maximum += span * 0.06;
  const measuredWidth = Math.round(container.clientWidth || 720);
  const width = Math.max(272, Math.min(720, measuredWidth));
  const isNarrow = width <= 420;
  const height = isNarrow ? 190 : 220;
  const left = isNarrow ? 10 : 20;
  const right = isNarrow ? 72 : 104;
  const top = 18;
  const bottom = 34;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const zeroY = top + (maximum / (maximum - minimum)) * plotHeight;
  const slot = plotWidth / points.length;
  const barWidth = Math.max(1, Math.min(12, slot * 0.68));
  const bars = points.map((point, index) => {
    const value = Number(point.value);
    const valueY = top + (maximum - value) / (maximum - minimum) * plotHeight;
    const x = left + slot * index + (slot - barWidth) / 2;
    const y = Math.min(zeroY, valueY);
    const heightValue = Math.max(1, Math.abs(zeroY - valueY));
    const className = value >= 0 ? "chart-bar-positive" : "chart-bar-negative";
    return `<rect class="${className}" x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${heightValue.toFixed(2)}"><title>${escapeHTML(`${formatChartDate(point.observed_at, rangeId)}：${formatChangeValue(metric, value)}`)}</title></rect>`;
  }).join("");
  const accessible = `${metric?.label || "ETF 净流入"}，从 ${formatChartDate(points[0].observed_at, rangeId)} 到 ${formatChartDate(points.at(-1).observed_at, rangeId)}；正数流入，负数流出`;
  container.innerHTML = `
    ${chartLegend([{label: "净流入", tone: 5}, {label: "净流出", tone: 6}], "chart-legend-bars")}
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(accessible)}">
      <line class="chart-grid" x1="${left}" y1="${top}" x2="${left + plotWidth}" y2="${top}"></line>
      <line class="chart-grid" x1="${left}" y1="${top + plotHeight}" x2="${left + plotWidth}" y2="${top + plotHeight}"></line>
      <line class="chart-zero-line" x1="${left}" y1="${zeroY.toFixed(2)}" x2="${left + plotWidth}" y2="${zeroY.toFixed(2)}"></line>
      ${bars}
      <text class="chart-label" x="${left + plotWidth + 8}" y="${top + 4}">${escapeHTML(chartAxisValue(maximum, metric, isNarrow))}</text>
      <text class="chart-label" x="${left + plotWidth + 8}" y="${top + plotHeight + 4}">${escapeHTML(chartAxisValue(minimum, metric, isNarrow))}</text>
      <text class="chart-label" x="${left}" y="${height - 8}">${escapeHTML(formatChartDate(points[0].observed_at, rangeId))}</text>
      <text class="chart-label" text-anchor="end" x="${left + plotWidth}" y="${height - 8}">${escapeHTML(formatChartDate(points.at(-1).observed_at, rangeId))}</text>
    </svg>
    ${chartDataTable(points, metric, rangeId)}`;
  bindChartExplorer(container, points.map((point, index) => {
    const value = Number(point.value);
    return {
      observed_at: point.observed_at,
      x: left + slot * index + slot / 2,
      values: [{
        label: value >= 0 ? "净流入" : "净流出",
        formatted: formatChangeValue(metric, value),
        y: top + (maximum - value) / (maximum - minimum) * plotHeight,
        tone: value >= 0 ? 5 : 6
      }]
    };
  }), {plotTop: top, plotBottom: top + plotHeight, title: metric?.label || "ETF 净流入"});
}

function drawChart(container, rawPoints, metric, rangeId) {
  if (!container) return;
  const segments = chartSegments(rawPoints, metric);
  const tablePoints = segments.flat();
  const points = segments.flatMap((segment) =>
    downsample(segment, Math.max(8, Math.floor(320 / Math.max(1, segments.length))))
      .map((point, index) => ({...point, _segmentStart: index === 0}))
  );
  if (points.length < 2) {
    container.innerHTML = `<div class="chart-state">${points.length ? "这个时间段只有一个数据点，还画不出走势。" : "这个时间段还没有历史数据，看板不会凭空补线。"}</div>`;
    return;
  }
  const values = points.map((point) => Number(point.value));
  let minimum = Math.min(...values);
  let maximum = Math.max(...values);
  const chartReference = numericOrNull(metric?.chart_reference);
  if (chartReference !== null) {
    minimum = Math.min(minimum, chartReference);
    maximum = Math.max(maximum, chartReference);
    const referenceSpan = Math.max(maximum - minimum, 1);
    minimum -= referenceSpan * 0.06;
    maximum += referenceSpan * 0.06;
  }
  if (metric?.chart_include_zero) {
    minimum = Math.min(minimum, 0);
    maximum = Math.max(maximum, 0);
    const span = Math.max(maximum - minimum, 1);
    minimum -= span * 0.06;
    maximum += span * 0.06;
  }
  if (minimum === maximum) {
    const padding = Math.max(Math.abs(minimum) * 0.02, 1);
    minimum -= padding;
    maximum += padding;
  }
  const isMain = container.classList.contains("chart-shell-main");
  const maximumWidth = isMain ? 980 : 720;
  const measuredWidth = Math.round(container.clientWidth || maximumWidth);
  const width = Math.max(272, Math.min(maximumWidth, measuredWidth));
  const isNarrow = width <= 420;
  const height = isMain ? (isNarrow ? 210 : 270) : isNarrow ? 190 : 220;
  const left = isNarrow ? 10 : 20;
  const right = isNarrow ? 72 : 104;
  const top = 18;
  const bottom = 34;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const firstTime = Date.parse(`${points[0].observed_at.slice(0, 10)}T00:00:00Z`);
  const lastTime = Date.parse(`${points.at(-1).observed_at.slice(0, 10)}T00:00:00Z`);
  const timeSpan = Math.max(1, lastTime - firstTime);
  const coordinates = points.map((point) => {
    const time = Date.parse(`${point.observed_at.slice(0, 10)}T00:00:00Z`);
    const x = left + (time - firstTime) / timeSpan * plotWidth;
    const y = top + (maximum - Number(point.value)) / (maximum - minimum) * plotHeight;
    return [x, y];
  });
  const path = coordinates.map(([x, y], index) => `${points[index]._segmentStart ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
  const last = coordinates.at(-1);
  const zeroY = metric?.chart_include_zero
    ? top + (maximum - 0) / (maximum - minimum) * plotHeight
    : null;
  const referenceY = chartReference === null
    ? null
    : top + (maximum - chartReference) / (maximum - minimum) * plotHeight;
  const metricLabel = metric?.label || "该指标";
  const gapNote = segments.length > 1 ? `；有 ${segments.length - 1} 处数据缺口，折线已断开` : "";
  const accessible = `${metricLabel} ${RANGE_LABELS[rangeId] || rangeId}趋势，从 ${formatChartDate(points[0].observed_at, rangeId)} 到 ${formatChartDate(points.at(-1).observed_at, rangeId)}${gapNote}`;
  container.innerHTML = `
    ${chartLegend([{label: metricLabel, tone: 1}], "chart-legend-single")}
    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(accessible)}">
      <line class="chart-grid" x1="${left}" y1="${top}" x2="${left + plotWidth}" y2="${top}"></line>
      <line class="chart-grid" x1="${left}" y1="${top + plotHeight / 2}" x2="${left + plotWidth}" y2="${top + plotHeight / 2}"></line>
      <line class="chart-grid" x1="${left}" y1="${top + plotHeight}" x2="${left + plotWidth}" y2="${top + plotHeight}"></line>
      ${zeroY === null ? "" : `<line class="chart-zero-line" x1="${left}" y1="${zeroY.toFixed(2)}" x2="${left + plotWidth}" y2="${zeroY.toFixed(2)}"></line>`}
      ${referenceY === null ? "" : `<line class="chart-zero-line" x1="${left}" y1="${referenceY.toFixed(2)}" x2="${left + plotWidth}" y2="${referenceY.toFixed(2)}"><title>${escapeHTML(`${roundForDisplay(chartReference, 1)}% 平衡线`)}</title></line>`}
      <path class="chart-line" d="${path}"></path>
      <circle class="chart-dot" cx="${last[0].toFixed(2)}" cy="${last[1].toFixed(2)}" r="4"><title>${escapeHTML(`${formatChartDate(points.at(-1).observed_at, rangeId)}：${chartAxisValue(values.at(-1), metric)}`)}</title></circle>
      <text class="chart-label" x="${left + plotWidth + 8}" y="${top + 4}">${escapeHTML(chartAxisValue(maximum, metric, isNarrow))}</text>
      <text class="chart-label" x="${left + plotWidth + 8}" y="${top + plotHeight + 4}">${escapeHTML(chartAxisValue(minimum, metric, isNarrow))}</text>
      <text class="chart-label" x="${left}" y="${height - 8}">${escapeHTML(formatChartDate(points[0].observed_at, rangeId))}</text>
      <text class="chart-label" text-anchor="end" x="${left + plotWidth}" y="${height - 8}">${escapeHTML(formatChartDate(points.at(-1).observed_at, rangeId))}</text>
    </svg>
    ${chartDataTable(tablePoints, metric, rangeId)}`;
  bindChartExplorer(container, points.map((point, index) => ({
    observed_at: point.observed_at,
    x: coordinates[index][0],
    values: [{label: metricLabel, formatted: chartAxisValue(point.value, metric), y: coordinates[index][1], tone: 1}]
  })), {plotTop: top, plotBottom: top + plotHeight, title: metricLabel});
}

async function fetchSeriesPayload(metricId, rangeId, signal) {
  const releaseId = state.data?.release_id || state.data?.snapshot?.run_id || "unknown";
  const cacheId = `${releaseId}:${metricId}:${rangeId}`;
  let payload = state.seriesCache.get(cacheId);
  if (payload) return payload;
  const response = await fetch(appUrl(`api/series?metric_id=${encodeURIComponent(metricId)}&range=${encodeURIComponent(rangeId)}&release_id=${encodeURIComponent(releaseId)}`), { cache: "no-store", signal });
  if (!response.ok) throw new Error(`历史数据请求失败，状态码 ${response.status}`);
  payload = await response.json();
  if (payload.release_id !== releaseId) throw new Error("历史数据版本和当前页面不一致，请刷新后重试");
  state.seriesCache.set(cacheId, payload);
  return payload;
}

async function loadSeries(metricId, rangeId, container) {
  if (!container) return;
  const previous = state.seriesRequests.get(container);
  if (previous) previous.controller.abort();
  const request = {metricId, rangeId, controller: new AbortController()};
  state.seriesRequests.set(container, request);
  container.innerHTML = `<div class="chart-state">正在读取 ${escapeHTML(RANGE_LABELS[rangeId] || rangeId)}历史…</div>`;
  try {
    const payload = await fetchSeriesPayload(metricId, rangeId, request.controller.signal);
    if (state.seriesRequests.get(container) !== request) return;
    drawChart(container, payload.points, displayMetricById(metricId), rangeId);
  } catch (error) {
    if (error?.name === "AbortError" || state.seriesRequests.get(container) !== request) return;
    container.innerHTML = `<div class="chart-state">历史读取失败。${escapeHTML(error.message || "请稍后刷新")}</div>`;
  } finally {
    if (state.seriesRequests.get(container) === request) state.seriesRequests.delete(container);
  }
}

function renderView(view, data) {
  if (state.renderedViews.has(view)) return;
  if (view === "overview") renderOverview(data);
  else if (view === "transmission") renderTransmission(data);
  else if (view === "ledger") renderLedger(data);
  else if (view === "data") renderData(data);
  state.renderedViews.add(view);
}

function renderAll(data) {
  normalizeDashboardCopy(data);
  document.querySelector(".primary-nav").hidden = false;
  state.renderedViews.clear();
  const view = currentHashView();
  document.querySelectorAll(".view").forEach((section) => section.replaceChildren());
  renderView(view, data);
  const currentStatusCode = effectiveDataStatus(data.status);
  const statusLabel = STATUS_LABELS[currentStatusCode] || "状态未知";
  elements.compactStatus.className = `compact-status ${statusClass(currentStatusCode)}`;
  elements.compactStatus.textContent = statusLabel;
  elements.brandDate.textContent = `${formatDateTime(data.snapshot.completed_at)} 更新`;
  setView(view, false);
}

function currentHashView() {
  const candidate = window.location.hash.replace("#", "");
  return VIEW_IDS.includes(candidate) ? candidate : "overview";
}

function announceViewChange(view, focusHeading = false) {
  const section = document.querySelector(`#view-${view}`);
  elements.live.textContent = `已打开${VIEW_LABELS[view] || "页面"}`;
  if (!focusHeading) return;
  const heading = section?.querySelector("h1");
  if (!heading) return;
  heading.setAttribute("tabindex", "-1");
  heading.focus({preventScroll: true});
}

function setView(view, updateHash = true, options = {}) {
  const nextView = VIEW_IDS.includes(view) ? view : "overview";
  saveCurrentScrollPosition();
  state.view = nextView;
  if (state.data) renderView(state.view, state.data);
  document.querySelectorAll(".view").forEach((section) => {
    section.hidden = section.id !== `view-${state.view}`;
  });
  document.querySelectorAll(".primary-nav a").forEach((link) => {
    if (link.dataset.view === state.view) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  if (updateHash && window.location.hash !== `#${state.view}`) history.pushState(null, "", `#${state.view}`);
  const savedPosition = Number(state.scrollPositions[state.view]) || 0;
  requestAnimationFrame(() => {
    const maximumPosition = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    window.scrollTo({ top: Math.min(savedPosition, maximumPosition), behavior: "instant" });
    if (state.view === "transmission") renderActiveCryptoChart(state.data);
    if (options.announce) announceViewChange(state.view, options.focusHeading);
  });
}

function showOffline(offline) {
  state.offline = offline;
  elements.offlineBanner.hidden = !offline;
}

function showFatalError(error) {
  document.querySelector(".primary-nav").hidden = true;
  VIEW_IDS.forEach((view, index) => {
    const section = document.querySelector(`#view-${view}`);
    section.hidden = index !== 0;
    if (index === 0) {
      section.innerHTML = `
        <div class="error-state">
          <p class="eyebrow">数据未加载</p>
          <h1>暂时拿不到看板数据</h1>
          <p>${escapeHTML(error.message || "数据服务不可用。")} 请确认看板服务正在运行，再点一次重试。</p>
          <button class="retry-button" type="button">重新读取数据</button>
        </div>`;
      section.querySelector(".retry-button").addEventListener("click", () => loadDashboard(true));
    }
  });
  elements.compactStatus.className = "compact-status status-block_analysis";
  elements.compactStatus.textContent = "读取失败";
}

async function loadDashboard(force = false) {
  elements.refresh.disabled = true;
  elements.refresh.classList.add("is-refreshing");
  try {
    const response = await fetch(appUrl("api/dashboard"), { cache: "no-store" });
    if (!response.ok) throw new Error(`数据读取失败，状态码 ${response.status}`);
    const servedFromOfflineCache = response.headers.get("X-Dashboard-Cache") === "offline";
    const data = await response.json();
    state.data = data;
    state.seriesCache.clear();
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(data));
    } catch {
      // Private browsing or storage pressure should not block the live view.
    }
    showOffline(servedFromOfflineCache || !navigator.onLine);
    renderAll(data);
    elements.live.textContent = force ? "数据已刷新" : "数据已经读完";
  } catch (error) {
    let cached = null;
    try {
      cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
    } catch {
      cached = null;
    }
    if (cached?.snapshot) {
      state.data = cached;
      showOffline(true);
      renderAll(cached);
      elements.live.textContent = "网络不可用，正在显示设备缓存";
    } else {
      showFatalError(error);
    }
  } finally {
    elements.refresh.disabled = false;
    elements.refresh.classList.remove("is-refreshing");
  }
}

document.querySelectorAll(".primary-nav a, .brand").forEach((link) => {
  link.addEventListener("click", (event) => {
    const view = link.dataset.view || link.getAttribute("href")?.replace("#", "");
    if (!VIEW_IDS.includes(view)) return;
    event.preventDefault();
    setView(view, true, {announce: true, focusHeading: event.detail === 0});
  });
});

document.addEventListener("click", (event) => {
  const link = event.target.closest("[data-evidence-metric]");
  if (!link) return;
  event.preventDefault();
  openEvidenceMetric(link.dataset.evidenceMetric, link);
});

window.addEventListener("hashchange", () => setView(currentHashView(), false, {announce: true}));
window.addEventListener("online", () => {
  showOffline(false);
  loadDashboard(true);
});
window.addEventListener("offline", () => showOffline(true));
window.addEventListener("pagehide", saveCurrentScrollPosition);
let cryptoChartResizeTimer = null;
window.addEventListener("resize", () => {
  window.clearTimeout(cryptoChartResizeTimer);
  cryptoChartResizeTimer = window.setTimeout(() => {
    if (state.view === "transmission") {
      renderCrossAssetChart(state.data);
      renderActiveCryptoChart(state.data);
    }
  }, 160);
});
elements.refresh.addEventListener("click", () => loadDashboard(true));
initializeTheme();

if ("scrollRestoration" in history) history.scrollRestoration = "manual";

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register(appUrl("sw.js")).catch(() => {}));
}

loadDashboard();
