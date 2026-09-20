"""Reproducible, optional hourly spot comparison. No synthetic gap filling."""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

from liquidity_channel.core import CurlFetcher, atomic_write_json, atomic_write_bytes, iso_z

UTC = timezone.utc
HOUR = timedelta(hours=1)
RANGES = {"1d": 1, "7d": 7, "1m": 30, "3m": 90, "1y": 365}
DEFINITIONS = {}
for mode, name in (("adjusted", "美元折算"), ("raw", "未折算")):
    for suffix, label, unit in (
        ("bp", "溢价", "basis_points"),
        ("mean_24h", "24小时平均溢价", "basis_points"),
        ("positive_share_24h", "24小时正溢价占比", "percent"),
        ("streak_hours", "连续同向小时数", "hours"),
    ):
        DEFINITIONS[f"coinbase_premium_{mode}_{suffix}"] = {
            "label": f"Coinbase {label}（{name}）", "unit": unit,
            "description": "Coinbase 相对 Binance 现货的价格差异；1 bp = 0.01%。",
            "direction_note": "正值表示 Coinbase 更贵；不能据此认定机构买入或资金净流入。",
            "order": 100,
        }


def read_json(path):
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def moment(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def parse_candles(body, venue, start, end, now):
    rows = json.loads(body)
    if not isinstance(rows, list):
        raise ValueError("行情返回值不是数组")
    points = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < (7 if venue == "binance" else 6):
            raise ValueError("K线字段不完整")
        opened = datetime.fromtimestamp(float(row[0]) / (1000 if venue == "binance" else 1), UTC)
        closed = opened + HOUR
        if opened.minute or opened.second or opened.microsecond:
            raise ValueError("小时K线时间未对齐")
        if not start <= opened < end or closed > now:
            continue
        price, volume = float(row[4]), float(row[5])
        if not math.isfinite(price) or price <= 0 or not math.isfinite(volume) or volume < 0:
            raise ValueError("价格或成交量异常")
        if volume == 0:
            continue
        if venue == "binance" and abs(float(row[6]) / 1000 - closed.timestamp()) > 0.01:
            raise ValueError("Binance K线收盘时间异常")
        key = iso_z(closed)
        if key in points and points[key] != price:
            raise ValueError("同一小时存在冲突价格")
        points[key] = price
    return points


def align_points(series):
    cb, bn, fx = (series.get(key, {}) for key in ("coinbase_btc_usd", "binance_btc_usdt", "coinbase_usdt_usd"))
    result = []
    for stamp in sorted(cb.keys() & bn.keys()):
        rate = fx.get(stamp)
        adjusted = bn[stamp] * rate if rate is not None else None
        result.append({
            "observed_at": stamp, "btc_usd": cb[stamp], "binance_btc_usdt": bn[stamp],
            "usdt_usd": rate, "binance_btc_usd": adjusted,
            "raw_bp": round((cb[stamp] / bn[stamp] - 1) * 10000, 6),
            "adjusted_bp": round((cb[stamp] / adjusted - 1) * 10000, 6) if adjusted else None,
        })
    return result


def summarize(points, mode, now, max_age=30):
    key = f"{mode}_bp"
    eligible = [p for p in points if p.get(key) is not None]
    if not eligible:
        return {"available_for_analysis": False, "observed_at": None, "value": None, "coverage_hours_24h": 0}
    latest = eligible[-1]
    stamp = moment(latest["observed_at"])
    fresh = timedelta(0) <= now - stamp <= timedelta(hours=max_age)
    window = [p for p in eligible if stamp - timedelta(hours=24) < moment(p["observed_at"]) <= stamp]
    lookup = {p["observed_at"]: p for p in eligible}
    previous = lookup.get(iso_z(stamp - HOUR))
    direction = "positive" if latest[key] > 0 else "negative" if latest[key] < 0 else "zero"
    streak, cursor = 0, stamp
    while direction != "zero":
        item = lookup.get(iso_z(cursor))
        if not item or (item[key] > 0) != (latest[key] > 0) or item[key] == 0:
            break
        streak += 1
        cursor -= HOUR
    return {
        "available_for_analysis": fresh, "observed_at": latest["observed_at"],
        "value": latest[key], "latest_change": latest[key] - previous[key] if previous else None,
        "latest_prior_value": previous[key] if previous else None,
        "latest_prior_observed_at": previous["observed_at"] if previous else None,
        "mean_24h": round(sum(p[key] for p in window) / 24, 6) if len(window) == 24 else None,
        "positive_share_24h": round(sum(p[key] > 0 for p in window) / 24 * 100, 4) if len(window) == 24 else None,
        "coverage_hours_24h": len(window), "streak_hours": streak, "streak_direction": direction,
        "streak_left_censored": iso_z(cursor) not in lookup and direction != "zero",
        "window_start": iso_z(stamp - timedelta(hours=24)), "window_end": iso_z(stamp),
    }


def build_payload(points, sources, now, run_id, max_age=30):
    summaries = {mode: summarize(points, mode, now, max_age) for mode in ("adjusted", "raw")}
    metrics = {}
    for mode, summary in summaries.items():
        required_sources = [s for s in sources if mode == "adjusted" or s.get("source_id") != "coinbase_usdt_usd"]
        used_cache = any(s.get("error") for s in required_sources)
        fetched_at = max((s.get("fetched_at") for s in required_sources if s.get("fetched_at")), default=iso_z(now))
        for suffix in ("bp", "mean_24h", "positive_share_24h", "streak_hours"):
            metric_id = f"coinbase_premium_{mode}_{suffix}"
            value = summary.get("value" if suffix == "bp" else suffix)
            ready = summary["available_for_analysis"] and value is not None
            metrics[metric_id] = {
                **DEFINITIONS[metric_id], "metric_id": metric_id, "group": "coinbase_premium",
                "value": value, "observed_at": summary["observed_at"], "fetched_at": fetched_at,
                "available_for_analysis": ready, "quality_status": ("fresh_cache" if used_cache else "fresh_network") if ready else "unavailable",
                "source_id": "coinbase_binance_spot_hourly", "source_name": "Coinbase / Binance 官方现货小时K线",
                "source_url": "https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles",
                "authority": "official_primary_multi_source", "cadence": "hourly_sampled_daily",
                "latest_change": summary.get("latest_change") if suffix == "bp" else None,
                "latest_prior_value": summary.get("latest_prior_value") if suffix == "bp" else None,
                "latest_prior_observed_at": summary.get("latest_prior_observed_at") if suffix == "bp" else None,
                "changes": {}, "sparkline": [],
                "metadata": {"mode": mode, "window_start": summary.get("window_start"), "window_end": summary.get("window_end"),
                             "coverage_hours_24h": summary.get("coverage_hours_24h"), "streak_direction": summary.get("streak_direction"),
                             "streak_left_censored": summary.get("streak_left_censored")},
            }
    ready = summaries["raw"]["available_for_analysis"]
    warnings = [f"{s['name']}：{s['error']}" for s in sources if s.get("error")]
    if not summaries["adjusted"]["available_for_analysis"]:
        warnings.append("美元折算数据暂不可用；可切换查看未折算价差。")
    return {
        "schema_version": "1.0", "run_id": run_id, "generated_at": iso_z(now), "max_age_hours": max_age,
        "status": "ready" if ready and not warnings else "degraded" if ready else "unavailable",
        "quality_status": "fresh_network" if ready and not warnings else "fresh_cache" if ready else "unavailable",
        "available_for_analysis": ready, "summaries": summaries, "metrics": metrics, "sources": sources,
        "quality": {"warnings": warnings, "paired_hours": len(points),
                    "missing_paired_hours": int((moment(points[-1]['observed_at']) - moment(points[0]['observed_at'])).total_seconds() / 3600) + 1 - len(points) if points else None},
        "recent_observations": points[-48:],
        "methodology": {
            "raw": "(Coinbase BTC/USD ÷ Binance BTC/USDT − 1) × 10000，单位 bp，未调整 USD/USDT。",
            "adjusted": "(Coinbase BTC/USD ÷ (Binance BTC/USDT × Coinbase USDT/USD) − 1) × 10000。",
            "alignment": "仅配对同一UTC小时的已收盘现货K线；小时收盘价是各市场该小时最后成交价，并非同步可成交报价。",
            "aggregation": "24小时统计需24个有效小时；日均需24个有效小时，UTC自然日，不包含未结束日期。",
            "interpretation": "正值表示Coinbase更贵。相对价差不证明美国机构买入，不等于资金净流入，不是扣除费用后的套利收益。",
        },
    }


def run_channel(root, *, direct=False, now=None, fetcher=None):
    now = now or datetime.now(UTC)
    config = read_json(root / "config/coinbase-premium-sources.json")
    data_dir = root / "data/crypto/coinbase-premium"
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / ".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fetcher = fetcher or CurlFetcher(config["request_policy"], direct=direct)
        run_id = now.strftime("%Y%m%dT%H%M%SZ")
        end = now.replace(minute=0, second=0, microsecond=0)
        earliest = end - timedelta(days=config["history_days"])
        series, health = {}, []
        for source in config["sources"]:
            source_id = source["id"]
            cache_path = data_dir / "cache" / f"{source_id}.json"
            cached = read_json(cache_path)
            values = {k: v for k, v in cached.get("points", {}).items() if earliest < moment(k) <= end}
            cursor = max(earliest, moment(cached["covered_until"]) - timedelta(hours=config["overlap_hours"])) if cached.get("covered_until") else earliest
            error, fetched_at = None, cached.get("fetched_at")
            try:
                while cursor < end:
                    stop = min(cursor + timedelta(hours=config["chunk_hours"]), end)
                    if source["venue"] == "coinbase":
                        url = f"{source['base_url']}/products/{source['symbol']}/candles?" + urlencode({"granularity": 3600, "start": iso_z(cursor), "end": iso_z(stop)})
                    else:
                        url = f"{source['base_url']}/api/v3/klines?" + urlencode({"symbol": source["symbol"], "interval": "1h", "startTime": int(cursor.timestamp()*1000), "endTime": int(stop.timestamp()*1000)-1, "limit": 1000})
                    response = fetcher.fetch(url)
                    digest = hashlib.sha256(response.body).hexdigest()
                    raw_path = data_dir / "raw" / source_id / f"{run_id}-{cursor.strftime('%Y%m%dT%H')}-{digest[:12]}.json"
                    atomic_write_bytes(raw_path, response.body)
                    atomic_write_json(raw_path.with_suffix(".meta.json"), {"url": url, "fetched_at": response.fetched_at, "sha256": digest})
                    incoming = parse_candles(response.body, source["venue"], cursor, stop, now)
                    if not incoming:
                        raise ValueError("请求时段没有有效小时K线")
                    # Replace this entire returned interval, retaining actual gaps.
                    values = {k: v for k, v in values.items() if not cursor < moment(k) <= stop}
                    values.update(incoming)
                    cursor, fetched_at = stop, response.fetched_at
                    atomic_write_json(cache_path, {"covered_until": iso_z(cursor), "fetched_at": fetched_at, "points": values})
            except Exception as exc:
                error = str(exc)[:300]
            series[source_id] = values
            latest = max(values) if values else None
            fresh = bool(latest) and now - moment(latest) <= timedelta(hours=config["max_age_hours"])
            health.append({"source_id": source_id, "name": source["name"], "url": source["url"], "group": "coinbase_premium",
                           "metric_id": "coinbase_premium_adjusted_bp" if source_id.endswith("usdt_usd") else "coinbase_premium_raw_bp",
                           "metric_label": "Coinbase现货溢价", "authority": "official_primary", "cadence": "hourly_sampled_daily",
                           "release_schedule_note": "每天07:30补齐已收盘小时数据", "observed_at": latest, "fetched_at": fetched_at,
                           "selected": fresh, "available_for_analysis": fresh, "error": error,
                           "quality_status": "fresh_cache" if fresh and error else "fresh_network" if fresh else "unavailable"})
        points = align_points(series)
        payload = build_payload(points, health, now, run_id, config["max_age_hours"])
        atomic_write_json(data_dir / "history.json", {"schema_version": "1.0", "run_id": run_id, "points": points})
        atomic_write_json(data_dir / "latest.json", payload)
        return payload


def load_payload(root, now=None):
    payload = copy.deepcopy(read_json(root / "data/crypto/coinbase-premium/latest.json"))
    now = now or datetime.now(UTC)
    for source in payload.get("sources", []):
        if not source.get("observed_at") or not timedelta(0) <= now - moment(source["observed_at"]) <= timedelta(hours=payload.get("max_age_hours", 30)):
            source.update(available_for_analysis=False, selected=False, quality_status="stale_source")
    for metric in payload.get("metrics", {}).values():
        if not metric.get("observed_at") or not timedelta(0) <= now - moment(metric["observed_at"]) <= timedelta(hours=payload.get("max_age_hours", 30)):
            metric.update(available_for_analysis=False, quality_status="stale_source")
    for mode, summary in payload.get("summaries", {}).items():
        summary["available_for_analysis"] = payload["metrics"][f"coinbase_premium_{mode}_bp"]["available_for_analysis"]
    payload["available_for_analysis"] = any(s.get("available_for_analysis") for s in payload.get("summaries", {}).values())
    if not payload["available_for_analysis"]:
        payload.update(status="unavailable", quality_status="stale_source")
    return payload


def build_history(root, metric_id, range_id):
    if range_id not in RANGES:
        raise ValueError("unknown premium range")
    mode = "adjusted" if "adjusted" in metric_id else "raw"
    key = f"{mode}_bp"
    if metric_id not in {"coinbase_premium_adjusted_bp", "coinbase_premium_raw_bp"}:
        return {"metric_id": metric_id, "range": range_id, "points": [], "message": "该统计值使用最近24小时；历史溢价请在Coinbase溢价页查看。"}
    points = read_json(root / "data/crypto/coinbase-premium/history.json").get("points", [])
    if points:
        end = moment(points[-1]["observed_at"])
        if range_id in {"3m", "1y"}:
            end = end.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = end - timedelta(days=RANGES[range_id])
        points = [p for p in points if cutoff < moment(p["observed_at"]) <= end]
    if range_id in {"3m", "1y"}:
        days = defaultdict(list)
        for point in points:
            days[(moment(point["observed_at"]) - HOUR).date().isoformat()].append(point)
        daily = []
        for day, rows in sorted(days.items()):
            valid = [p for p in rows if p.get(key) is not None]
            if len(valid) != 24:
                continue
            item = {"observed_at": iso_z(moment(day) + timedelta(days=1)), "period_date": day, "hours": 24}
            for field in ("btc_usd", "binance_btc_usdt", "usdt_usd", "binance_btc_usd", "raw_bp", "adjusted_bp"):
                item[field] = sum(p[field] for p in rows) / 24 if all(p.get(field) is not None for p in rows) else None
            daily.append(item)
        points = daily
    return {"metric_id": metric_id, "range": range_id, "mode": mode, "unit": "basis_points",
            "cadence": "daily_mean" if range_id in {"3m", "1y"} else "hourly",
            "points": [{**p, "value": p.get(key)} for p in points], "source_name": "Coinbase / Binance 官方现货K线"}
