"use strict";

const PREMIUM_RANGES = {"1d": "24 小时", "7d": "7 天", "1m": "30 天", "3m": "90 天", "1y": "1 年"};
const premiumState = {mode: "adjusted", range: "7d", request: 0};

function premiumNumber(value, digits = 2) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString("zh-CN", {maximumFractionDigits: digits, minimumFractionDigits: digits}) : "不可用";
}

function premiumBp(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? `${value > 0 ? "+" : ""}${premiumNumber(value)} bp` : "不可用";
}

function premiumTime(value, includeYear = false) {
  return value ? new Date(value).toLocaleString("zh-CN", {timeZone: "Asia/Shanghai", ...(includeYear ? {year: "numeric"} : {}), month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false}) : "暂无数据";
}

function coinbasePremiumPanel(data) {
  const channel = data.coinbase_premium || {};
  const summary = channel.summaries?.[premiumState.mode] || {};
  const fresh = summary.available_for_analysis;
  const status = cryptoChannelStatus(channel);
  const value = summary.value;
  const answer = !fresh ? "当前溢价暂不可用" : value > 0 ? `Coinbase 比 Binance 贵 ${premiumBp(value)}` : value < 0 ? `Coinbase 比 Binance 便宜 ${premiumBp(Math.abs(value)).replace("+", "")}` : "两所 BTC 价格相同";
  return `<div class="crypto-channel-panel premium-panel" aria-labelledby="premium-title">
    <div class="section-heading"><div><h3 id="premium-title">Coinbase 的 BTC 比 Binance 贵多少</h3><p>现货小时收盘价差，由本看板计算。</p></div><span class="quality-pill ${fresh ? status.className : "quality-unavailable"}">${fresh ? status.label : "数据缺失或过期"}</span></div>
    <div class="crypto-asset-switch" role="group" aria-label="溢价计算口径">
      <button type="button" data-premium-mode="adjusted" aria-pressed="${premiumState.mode === "adjusted"}">美元折算</button>
      <button type="button" data-premium-mode="raw" aria-pressed="${premiumState.mode === "raw"}">未折算</button>
    </div>
    <p class="premium-answer">${escapeHTML(answer)}</p>
    <p class="premium-caption">${fresh ? `截至北京时间 ${premiumTime(summary.observed_at)}；较前一小时 ${premiumBp(summary.latest_change)}` : "可查看历史；失效数据不进入今日分析。"}</p>
    <dl class="premium-summary">
      <div><dt>过去 24 小时平均溢价</dt><dd>${fresh ? premiumBp(summary.mean_24h) : "不可用"}</dd></div>
      <div><dt>过去 24 小时正溢价占比</dt><dd>${fresh && summary.positive_share_24h != null ? `${premiumNumber(summary.positive_share_24h, 1)}%` : "不可用"}</dd></div>
      <div><dt>连续${summary.streak_direction === "negative" ? "负" : "正"}溢价</dt><dd>${fresh && summary.streak_direction !== "zero" ? `${summary.streak_left_censored ? "至少 " : ""}${summary.streak_hours} 小时` : fresh ? "0 小时" : "不可用"}</dd></div>
    </dl>
    <p class="premium-caption">${premiumState.mode === "adjusted" ? "先将 Binance 的 USDT 报价折算为美元。" : "直接比较 USD 与 USDT 报价，会受 USDT 偏离 1 美元影响。"}1 bp = 0.01%。${summary.coverage_hours_24h === 24 ? "" : ` 最近24小时窗口有效数据 ${summary.coverage_hours_24h || 0}/24，缺失时不计算均值和占比。`}</p>
    <div class="chart-switch" role="group" aria-label="溢价图表时间范围">${Object.entries(PREMIUM_RANGES).map(([key, label]) => `<button class="chart-switch-button" type="button" data-premium-range="${key}" aria-pressed="${premiumState.range === key}">${label}</button>`).join("")}</div>
    <p class="premium-caption" data-premium-period>正在读取历史…</p>
    <div class="premium-chart" data-premium-chart aria-label="BTC价格与溢价共用时间轴"><div class="chart-state">正在读取历史…</div></div>
    <label class="premium-slider-label">拖动查看同一时点的价格与溢价<input data-premium-cursor type="range" min="0" max="0" value="0" disabled aria-label="选择价格与溢价的时点"></label>
    <div class="premium-readout" data-premium-readout aria-live="polite"></div>
    <details class="stablecoin-details"><summary>计算方法与数据来源</summary><div>
      <p>美元折算溢价 = (Coinbase BTC/USD ÷ (Binance BTC/USDT × USDT/USD) − 1) × 10000。</p>
      <p>未折算溢价 = (Coinbase BTC/USD ÷ Binance BTC/USDT − 1) × 10000。单位均为 bp。</p>
      <p>只比较同一小时已收盘的现货K线。90天和1年视图使用UTC完整自然日的24个小时均值；缺失留空。这里的历史收盘价不代表可以同时成交的报价。</p>
      <p>历史有效配对 ${channel.quality?.paired_hours ?? 0} 小时；两所BTC配对缺失 ${channel.quality?.missing_paired_hours ?? "未知"} 小时。USDT汇率缺失时，折算口径另留空。</p>
      <p>溢价表示相对价格强弱，不能单独证明机构买入，也不是资金净流入金额。</p>
      <p><a href="https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles" target="_blank" rel="noreferrer">Coinbase 数据说明 ↗</a> · <a href="https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints" target="_blank" rel="noreferrer">Binance 现货数据说明 ↗</a></p>
      ${(channel.sources || []).map(s => `<p>${escapeHTML(s.name)}：${escapeHTML(QUALITY_LABELS[s.quality_status] || s.quality_status)}，观察至 ${premiumTime(s.observed_at)}</p>`).join("")}
    </div></details>
  </div>`;
}

async function renderPremiumChart() {
  const container = document.querySelector("[data-premium-chart]");
  if (!container) return;
  const request = ++premiumState.request;
  const range = premiumState.range;
  const slider = document.querySelector("[data-premium-cursor]");
  const readout = document.querySelector("[data-premium-readout]");
  container.setAttribute("aria-busy", "true");
  try {
    const payload = await fetchSeriesPayload(`coinbase_premium_${premiumState.mode}_bp`, range);
    if (request !== premiumState.request || !container.isConnected) return;
    const points = (payload.points || []).filter(p => p.observed_at && Number.isFinite(p.btc_usd));
    const valid = points.filter(p => Number.isFinite(p.value));
    if (valid.length < 2) {
      container.innerHTML = '<div class="chart-state">这个时段没有足够的配对数据。可切换时间范围或口径。</div>';
      document.querySelector("[data-premium-period]").textContent = "没有用零替代缺失数据";
      return;
    }
    const daily = payload.cadence === "daily_mean";
    const period = document.querySelector("[data-premium-period]");
    period.textContent = `${daily ? points[0].period_date : premiumTime(points[0].observed_at)} 至 ${daily ? points.at(-1).period_date : premiumTime(points.at(-1).observed_at)} · ${daily ? "UTC完整日的小时均值" : "小时收盘，北京时间"} · ${valid.length} 个有效点`;
    const width = Math.max(280, Math.round(container.getBoundingClientRect().width));
    const height = 370, left = 68, right = width - 12;
    const t0 = Date.parse(points[0].observed_at), t1 = Date.parse(points.at(-1).observed_at);
    const x = p => left + (Date.parse(p.observed_at) - t0) / Math.max(1, t1 - t0) * (right - left);
    const step = daily ? 86400000 : 3600000;
    const panel = (key, top, bottom, label, zero) => {
      const vals = points.map(p => p[key]).filter(Number.isFinite);
      let lo = Math.min(...vals, ...(zero ? [0] : [])), hi = Math.max(...vals, ...(zero ? [0] : []));
      const pad = (hi - lo || Math.abs(hi) * 0.001 || 1) * 0.12;
      lo -= pad; hi += pad;
      const y = value => bottom - (value - lo) / (hi - lo) * (bottom - top);
      let path = "", previous = null;
      for (const p of points) {
        if (!Number.isFinite(p[key])) { previous = null; continue; }
        path += `${!previous || Date.parse(p.observed_at) - Date.parse(previous.observed_at) > step * 1.01 ? "M" : "L"}${x(p).toFixed(2)},${y(p[key]).toFixed(2)} `;
        previous = p;
      }
      const grids = [hi, (hi + lo) / 2, lo].map(v => `<line x1="${left}" x2="${right}" y1="${y(v)}" y2="${y(v)}" class="premium-grid"/><text x="${left - 8}" y="${y(v) + 4}" text-anchor="end">${premiumNumber(v, zero ? 1 : 0)}</text>`).join("");
      return `<text x="${left}" y="${top - 14}" class="premium-axis-title">${label}</text>${grids}${zero ? `<line x1="${left}" x2="${right}" y1="${y(0)}" y2="${y(0)}" class="premium-zero"/>` : ""}<path d="${path}" class="premium-line ${zero ? "premium-spread" : "premium-price"}"/>`;
    };
    container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="上图BTC美元价格，下图Coinbase溢价；正值更贵，负值更便宜">
      ${panel("btc_usd", 35, 154, daily ? "BTC 日均价格（美元）" : "BTC（美元）", false)}
      ${panel("value", 222, 340, daily ? "日均溢价（bp）" : "溢价（bp）", true)}
      <line data-premium-guide x1="${right}" x2="${right}" y1="30" y2="340" class="premium-guide"/>
      <text x="${left}" y="365">${new Date(t0).toLocaleDateString("zh-CN", {timeZone:"Asia/Shanghai",month:"numeric",day:"numeric"})}</text>
      <text x="${right}" y="365" text-anchor="end">${new Date(t1).toLocaleDateString("zh-CN", {timeZone:"Asia/Shanghai",month:"numeric",day:"numeric"})}</text>
    </svg>`;
    const select = index => {
      const p = points[index];
      slider.value = String(index);
      slider.setAttribute("aria-valuetext", `${premiumTime(p.observed_at)}，溢价${premiumBp(p.value)}`);
      const guide = container.querySelector("[data-premium-guide]");
      guide.setAttribute("x1", x(p)); guide.setAttribute("x2", x(p));
      readout.innerHTML = `<strong>${daily ? `${escapeHTML(p.period_date)} UTC日均` : `${premiumTime(p.observed_at)} 北京时间`}</strong><dl>
        <div><dt>Coinbase BTC/USD</dt><dd>$${premiumNumber(p.btc_usd)}</dd></div>
        <div><dt>Binance BTC/USDT</dt><dd>${premiumNumber(p.binance_btc_usdt)} USDT</dd></div>
        <div><dt>USDT/USD</dt><dd>$${premiumNumber(p.usdt_usd, 5)}</dd></div>
        <div><dt>美元折算溢价</dt><dd>${premiumBp(p.adjusted_bp)}</dd></div>
        <div><dt>未折算价差</dt><dd>${premiumBp(p.raw_bp)}</dd></div>
      </dl>`;
    };
    slider.disabled = false; slider.max = String(points.length - 1);
    slider.oninput = () => select(Number(slider.value));
    const svg = container.querySelector("svg");
    const locate = event => {
      const rect = svg.getBoundingClientRect();
      const pos = (event.clientX - rect.left) / rect.width * width;
      const time = t0 + Math.max(0, Math.min(1, (pos - left) / (right - left))) * (t1 - t0);
      let nearest = 0;
      points.forEach((p, i) => { if (Math.abs(Date.parse(p.observed_at) - time) < Math.abs(Date.parse(points[nearest].observed_at) - time)) nearest = i; });
      select(nearest);
    };
    svg.addEventListener("pointermove", event => { if (event.pointerType === "mouse") locate(event); });
    svg.addEventListener("click", locate);
    select(points.length - 1);
  } catch (error) {
    if (request === premiumState.request && container.isConnected) {
      container.innerHTML = '<div class="chart-state">溢价历史读取失败，请稍后刷新。</div>';
    }
  } finally {
    if (request === premiumState.request) container.removeAttribute("aria-busy");
  }
}

function bindPremiumInteractions(data) {
  document.querySelectorAll("[data-premium-mode]").forEach(button => button.addEventListener("click", () => {
    premiumState.mode = button.dataset.premiumMode;
    renderCryptoMarketContent(data);
  }));
  document.querySelectorAll("[data-premium-range]").forEach(button => button.addEventListener("click", () => {
    premiumState.range = button.dataset.premiumRange;
    renderCryptoMarketContent(data);
  }));
  requestAnimationFrame(renderPremiumChart);
}
