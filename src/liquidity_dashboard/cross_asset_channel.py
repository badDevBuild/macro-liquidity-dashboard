from __future__ import annotations

import copy
from bisect import bisect_right
import csv
import hashlib
import io
import json
import math
import sqlite3
import time
from contextlib import closing
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from liquidity_channel.core import (
    CurlFetcher,
    FetchError,
    FetchResponse,
    atomic_write_bytes,
    atomic_write_json,
    iso_z,
    utc_now,
)


UTC = timezone.utc
SCHEMA_VERSION = "1.0"
ELIGIBLE_STATUSES = {"fresh_network", "fresh_cache"}
CHANGE_WINDOWS = {"1d": 1, "1w": 7, "1m": 31, "3m": 93, "1y": 366}


class CrossAssetChannelError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _number(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise CrossAssetChannelError(f"{label} is missing")
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise CrossAssetChannelError(f"{label} is not numeric") from exc
    if not math.isfinite(parsed):
        raise CrossAssetChannelError(f"{label} is not finite")
    return parsed


def parse_coinbase_candles(
    body: bytes, *, product_id: str, now: datetime
) -> list[dict[str, Any]]:
    try:
        rows = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CrossAssetChannelError(f"{product_id} candles are not valid JSON") from exc
    if not isinstance(rows, list):
        raise CrossAssetChannelError(f"{product_id} candles are not an array")
    points: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        try:
            timestamp = int(row[0])
            close = _number(row[4], f"{product_id} close")
        except (TypeError, ValueError, CrossAssetChannelError):
            continue
        observed = datetime.fromtimestamp(timestamp, tz=UTC)
        if observed > now + timedelta(minutes=5):
            raise CrossAssetChannelError(
                f"{product_id} contains future candle {iso_z(observed)}"
            )
        if close <= 0:
            raise CrossAssetChannelError(f"{product_id} close is not positive")
        points[timestamp] = {
            "started_at": iso_z(observed),
            "close": round(close, 8),
        }
    return [points[key] for key in sorted(points)]


def sample_new_york_close(
    candles: list[dict[str, Any]],
    *,
    start_date: date,
    end_date: date,
    timezone_name: str = "America/New_York",
    close_hour: int = 16,
    max_staleness_hours: int = 0,
) -> list[dict[str, Any]]:
    timezone_local = ZoneInfo(timezone_name)
    by_started_at = {
        datetime.fromisoformat(str(item["started_at"]).replace("Z", "+00:00")):
        item
        for item in candles
        if item.get("started_at") and isinstance(item.get("close"), (int, float))
    }
    ordered_times = sorted(by_started_at)
    sampled: list[dict[str, Any]] = []
    current = start_date
    while current <= end_date:
        close_local = datetime.combine(
            current, clock_time(hour=close_hour), tzinfo=timezone_local
        )
        close_utc = close_local.astimezone(UTC)
        target_start = close_utc - timedelta(hours=1)
        selected_time = target_start if target_start in by_started_at else None
        if selected_time is None and max_staleness_hours > 0:
            index = bisect_right(ordered_times, target_start) - 1
            candidate = ordered_times[index] if index >= 0 else None
            if (
                candidate is not None
                and candidate + timedelta(hours=1)
                >= close_utc - timedelta(hours=max_staleness_hours)
            ):
                selected_time = candidate
        if selected_time is not None:
            candle = by_started_at[selected_time]
            candle_end = selected_time + timedelta(hours=1)
            staleness_minutes = int((close_utc - candle_end).total_seconds() / 60)
            sampled.append(
                {
                    "observed_at": current.isoformat(),
                    "value": round(float(candle["close"]), 8),
                    "sampled_at": iso_z(candle_end),
                    "staleness_minutes": staleness_minutes,
                }
            )
        current += timedelta(days=1)
    return sampled


def parse_fred_sp500(body: bytes, *, series_id: str, now: datetime) -> list[dict[str, Any]]:
    try:
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise CrossAssetChannelError("S&P 500 history is not UTF-8 CSV") from exc
    if not reader.fieldnames or "observation_date" not in reader.fieldnames:
        raise CrossAssetChannelError("S&P 500 CSV is missing observation_date")
    if series_id not in reader.fieldnames:
        raise CrossAssetChannelError(f"S&P 500 CSV is missing {series_id}")
    points: dict[str, float] = {}
    for row in reader:
        raw = row.get(series_id)
        if raw in (None, "", "."):
            continue
        try:
            observed = date.fromisoformat(str(row.get("observation_date"))[:10])
            value = _number(raw, "S&P 500 close")
        except (ValueError, CrossAssetChannelError):
            continue
        if observed > now.date():
            raise CrossAssetChannelError(
                f"S&P 500 contains future observation {observed.isoformat()}"
            )
        if value <= 0:
            raise CrossAssetChannelError("S&P 500 close is not positive")
        points[observed.isoformat()] = round(value, 6)
    if not points:
        raise CrossAssetChannelError("S&P 500 CSV has no usable observations")
    return [
        {"observed_at": observed_at, "value": value}
        for observed_at, value in sorted(points.items())
    ]


def parse_yahoo_sp500(body: bytes, *, now: datetime) -> list[dict[str, Any]]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CrossAssetChannelError("Yahoo S&P 500 history is not valid JSON") from exc
    chart = payload.get("chart") if isinstance(payload, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise CrossAssetChannelError("Yahoo S&P 500 response has no chart result")
    result = results[0]
    timestamps = result.get("timestamp")
    indicators = result.get("indicators")
    quotes = indicators.get("quote") if isinstance(indicators, dict) else None
    closes = quotes[0].get("close") if isinstance(quotes, list) and quotes and isinstance(quotes[0], dict) else None
    if not isinstance(timestamps, list) or not isinstance(closes, list):
        raise CrossAssetChannelError("Yahoo S&P 500 response is missing timestamps or closes")
    if len(timestamps) != len(closes):
        raise CrossAssetChannelError("Yahoo S&P 500 timestamps and closes do not match")
    new_york = ZoneInfo("America/New_York")
    points: dict[str, float] = {}
    for raw_timestamp, raw_close in zip(timestamps, closes):
        if raw_close is None:
            continue
        try:
            observed_moment = datetime.fromtimestamp(int(raw_timestamp), tz=UTC)
            value = _number(raw_close, "Yahoo S&P 500 close")
        except (TypeError, ValueError, OSError, OverflowError, CrossAssetChannelError):
            continue
        observed = observed_moment.astimezone(new_york).date()
        if observed > now.astimezone(new_york).date():
            raise CrossAssetChannelError(
                f"Yahoo S&P 500 contains future observation {observed.isoformat()}"
            )
        if value <= 0:
            raise CrossAssetChannelError("Yahoo S&P 500 close is not positive")
        points[observed.isoformat()] = round(value, 6)
    if not points:
        raise CrossAssetChannelError("Yahoo S&P 500 response has no usable closes")
    return [
        {"observed_at": observed_at, "value": value}
        for observed_at, value in sorted(points.items())
    ]


def _save_raw(
    data_dir: Path,
    source_id: str,
    run_id: str,
    response: FetchResponse,
    url: str,
    *,
    suffix: str,
) -> None:
    digest = hashlib.sha256(response.body).hexdigest()
    raw_path = data_dir / "raw" / source_id / f"{run_id}-{suffix}-{digest[:12]}"
    is_json = suffix.startswith("chunk") or suffix.endswith("json")
    atomic_write_bytes(raw_path.with_suffix(".json" if is_json else ".csv"), response.body)
    atomic_write_json(
        raw_path.with_suffix(".meta.json"),
        {
            "source_id": source_id,
            "url": url,
            "fetched_at": response.fetched_at,
            "http_status": response.status_code,
            "attempts": response.attempts,
            "elapsed_ms": response.elapsed_ms,
            "sha256": digest,
            "byte_count": len(response.body),
        },
    )


def _fetch_coinbase_series(
    fetcher: Any,
    data_dir: Path,
    source: dict[str, Any],
    coinbase: dict[str, Any],
    *,
    start: datetime,
    end: datetime,
    run_id: str,
    now: datetime,
    pause_seconds: float,
) -> tuple[list[dict[str, Any]], str]:
    chunk = timedelta(hours=int(coinbase["chunk_hours"]))
    granularity = int(coinbase["granularity_seconds"])
    cursor = start.astimezone(UTC)
    candles: dict[str, dict[str, Any]] = {}
    fetched_at = ""
    chunk_index = 0
    while cursor < end:
        chunk_end = min(cursor + chunk, end)
        query = urlencode(
            {
                "granularity": granularity,
                "start": iso_z(cursor),
                "end": iso_z(chunk_end),
            }
        )
        url = (
            f"{str(coinbase['base_url']).rstrip('/')}/products/"
            f"{source['product_id']}/candles?{query}"
        )
        response = fetcher.fetch(url)
        _save_raw(
            data_dir,
            source["id"],
            run_id,
            response,
            url,
            suffix=f"chunk-{chunk_index:04d}",
        )
        for point in parse_coinbase_candles(
            response.body, product_id=source["product_id"], now=now
        ):
            candles[point["started_at"]] = point
        fetched_at = max(fetched_at, response.fetched_at)
        cursor = chunk_end
        chunk_index += 1
        if pause_seconds > 0:
            time.sleep(pause_seconds)
    sampled = sample_new_york_close(
        [candles[key] for key in sorted(candles)],
        start_date=start.astimezone(ZoneInfo(coinbase["close_timezone"])).date(),
        end_date=end.astimezone(ZoneInfo(coinbase["close_timezone"])).date(),
        timezone_name=coinbase["close_timezone"],
        close_hour=int(coinbase["close_hour"]),
        max_staleness_hours=int(source["max_close_staleness_hours"]),
    )
    if not sampled:
        raise CrossAssetChannelError(f"{source['product_id']} has no sampled closes")
    return sampled, fetched_at


def _merge_points(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
    *,
    series_id: str,
    detected_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged = {
        str(item.get("observed_at")): dict(item)
        for item in existing
        if isinstance(item, dict) and item.get("observed_at")
    }
    revisions: list[dict[str, Any]] = []
    for item in incoming:
        key = str(item.get("observed_at") or "")
        if not key:
            continue
        previous = merged.get(key)
        if (
            previous
            and isinstance(previous.get("value"), (int, float))
            and isinstance(item.get("value"), (int, float))
            and not math.isclose(
                float(previous["value"]), float(item["value"]), rel_tol=1e-10, abs_tol=1e-8
            )
        ):
            revisions.append(
                {
                    "series_id": series_id,
                    "observed_at": key,
                    "old_value": previous["value"],
                    "new_value": item["value"],
                    "detected_at": detected_at,
                }
            )
        merged[key] = dict(item)
    return [merged[key] for key in sorted(merged)], revisions


def align_ratio(
    numerator: list[dict[str, Any]],
    denominator: list[dict[str, Any]],
    *,
    numerator_key: str,
    denominator_key: str,
) -> list[dict[str, Any]]:
    left = {
        str(item.get("observed_at")): item
        for item in numerator
        if isinstance(item, dict) and isinstance(item.get("value"), (int, float))
    }
    right = {
        str(item.get("observed_at")): item
        for item in denominator
        if isinstance(item, dict) and isinstance(item.get("value"), (int, float))
    }
    result = []
    for observed_at in sorted(set(left) & set(right)):
        numerator_value = float(left[observed_at]["value"])
        denominator_value = float(right[observed_at]["value"])
        if denominator_value == 0:
            continue
        result.append(
            {
                "observed_at": observed_at,
                "value": round(numerator_value / denominator_value, 10),
                numerator_key: numerator_value,
                denominator_key: denominator_value,
                "component_dates": {
                    numerator_key: observed_at,
                    denominator_key: observed_at,
                },
            }
        )
    return result


def align_dual_series(
    first: list[dict[str, Any]],
    second: list[dict[str, Any]],
    *,
    first_key: str,
    second_key: str,
) -> list[dict[str, Any]]:
    first_by_date = {
        str(item.get("observed_at")): float(item["value"])
        for item in first
        if isinstance(item, dict) and isinstance(item.get("value"), (int, float))
    }
    second_by_date = {
        str(item.get("observed_at")): float(item["value"])
        for item in second
        if isinstance(item, dict) and isinstance(item.get("value"), (int, float))
    }
    return [
        {
            "observed_at": observed_at,
            first_key: first_by_date[observed_at],
            second_key: second_by_date[observed_at],
            "component_dates": {
                first_key: observed_at,
                second_key: observed_at,
            },
        }
        for observed_at in sorted(set(first_by_date) & set(second_by_date))
    ]


def return_correlation(
    points: list[dict[str, Any]],
    *,
    first_key: str,
    second_key: str,
    window: int,
) -> float | None:
    if len(points) < window + 1:
        return None
    selected = points[-(window + 1) :]
    first_returns: list[float] = []
    second_returns: list[float] = []
    for previous, current in zip(selected, selected[1:]):
        first_previous = float(previous[first_key])
        second_previous = float(previous[second_key])
        if first_previous == 0 or second_previous == 0:
            return None
        first_returns.append(float(current[first_key]) / first_previous - 1)
        second_returns.append(float(current[second_key]) / second_previous - 1)
    first_mean = sum(first_returns) / len(first_returns)
    second_mean = sum(second_returns) / len(second_returns)
    covariance = sum(
        (left - first_mean) * (right - second_mean)
        for left, right in zip(first_returns, second_returns)
    )
    first_variance = sum((value - first_mean) ** 2 for value in first_returns)
    second_variance = sum((value - second_mean) ** 2 for value in second_returns)
    denominator = math.sqrt(first_variance * second_variance)
    return round(covariance / denominator, 6) if denominator else None


def _nearest_on_or_before(
    points: list[dict[str, Any]], target: date
) -> dict[str, Any] | None:
    for point in reversed(points):
        if date.fromisoformat(str(point["observed_at"])[:10]) <= target:
            return point
    return None


def _change(points: list[dict[str, Any]], days: int) -> dict[str, Any]:
    if not points:
        return {
            "days": days,
            "change": None,
            "percent_change": None,
            "prior_value": None,
            "prior_observed_at": None,
        }
    latest = points[-1]
    prior = _nearest_on_or_before(
        points, date.fromisoformat(latest["observed_at"]) - timedelta(days=days)
    )
    if prior is None:
        return {
            "days": days,
            "change": None,
            "percent_change": None,
            "prior_value": None,
            "prior_observed_at": None,
        }
    change = float(latest["value"]) - float(prior["value"])
    percent = change / abs(float(prior["value"])) * 100 if prior["value"] else None
    return {
        "days": days,
        "change": round(change, 8),
        "percent_change": round(percent, 4) if percent is not None else None,
        "prior_value": round(float(prior["value"]), 8),
        "prior_observed_at": prior["observed_at"],
    }


def _metric(
    metric_id: str,
    points: list[dict[str, Any]],
    *,
    unit: str,
    source_id: str,
    source_name: str,
    source_url: str,
    quality_status: str,
    fetched_at: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest = points[-1] if points else None
    changes = {key: _change(points, days) for key, days in CHANGE_WINDOWS.items()}
    previous = points[-2] if len(points) >= 2 else None
    return {
        "metric_id": metric_id,
        "group": "cross_asset",
        "source_id": source_id,
        "source_name": source_name,
        "source_url": source_url,
        "authority": "mixed_official_and_primary",
        "cadence": "us_market_close_daily",
        "quality_status": quality_status,
        "available_for_analysis": bool(latest) and quality_status in ELIGIBLE_STATUSES,
        "value": round(float(latest["value"]), 8) if latest else None,
        "unit": unit,
        "observed_at": latest.get("observed_at") if latest else None,
        "fetched_at": fetched_at,
        "latest_change": (
            round(float(latest["value"]) - float(previous["value"]), 8)
            if latest and previous
            else None
        ),
        "latest_prior_value": previous.get("value") if previous else None,
        "latest_prior_observed_at": previous.get("observed_at") if previous else None,
        "week_change": changes["1w"]["change"],
        "week_prior_value": changes["1w"]["prior_value"],
        "week_prior_observed_at": changes["1w"]["prior_observed_at"],
        "changes": changes,
        "sparkline": points[-370:],
        "metadata": metadata or {},
    }


def _correlation_metric(
    metric_id: str,
    value: float | None,
    observed_at: str | None,
    *,
    window: int,
    quality_status: str,
    fetched_at: str | None,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "group": "cross_asset",
        "source_id": "coinbase_btc_and_fed_broad_dollar",
        "source_name": "Coinbase BTC-USD 与美联储广义美元指数",
        "source_url": "https://fred.stlouisfed.org/series/DTWEXBGS",
        "authority": "mixed_official_and_primary",
        "cadence": "daily_observations_weekly_release",
        "quality_status": quality_status,
        "available_for_analysis": value is not None and quality_status in ELIGIBLE_STATUSES,
        "value": value,
        "unit": "correlation",
        "observed_at": observed_at,
        "fetched_at": fetched_at,
        "latest_change": None,
        "week_change": None,
        "changes": {},
        "sparkline": [],
        "metadata": {
            "window_common_observations": window,
            "method": "双方共同观察日的日收益率 Pearson 相关性",
            "causality": False,
        },
    }


def _series_age_days(points: list[dict[str, Any]], now: datetime) -> int | None:
    if not points:
        return None
    return max(0, (now.date() - date.fromisoformat(points[-1]["observed_at"])).days)


def _source_health(
    source: dict[str, Any],
    points: list[dict[str, Any]],
    *,
    now: datetime,
    fetched_at: str | None,
    network_ok: bool,
    error: str | None,
) -> dict[str, Any]:
    age_days = _series_age_days(points, now)
    limit = int(
        source["freshness_max_days"] if network_ok else source["cache_max_days"]
    )
    if not points or age_days is None or age_days > limit:
        quality_status = "unavailable" if not points else "stale_source"
    else:
        quality_status = "fresh_network" if network_ok else "fresh_cache"
    return {
        "source_id": source["id"],
        "series_id": source.get("series_id") or source.get("series_key"),
        "name": source["name"],
        "source_owner": source["source_owner"],
        "authority": source["authority"],
        "cadence": source["cadence"],
        "url": source["documentation_url"],
        "quality_status": quality_status,
        "available_for_analysis": quality_status in ELIGIBLE_STATUSES,
        "observed_at": points[-1]["observed_at"] if points else None,
        "fetched_at": fetched_at,
        "age_days": age_days,
        "error": error,
    }


def _load_broad_dollar(root: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    database = root / "data" / "channel.sqlite3"
    if not database.is_file():
        raise CrossAssetChannelError("main channel database is unavailable")
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """
            SELECT source_id FROM observations
            WHERE metric_id = ?
            ORDER BY observed_at DESC LIMIT 1
            """,
            (source["series_id"],),
        ).fetchone()
        if row is None:
            raise CrossAssetChannelError("broad dollar series is unavailable")
        rows = connection.execute(
            """
            SELECT observed_at, value FROM observations
            WHERE metric_id = ? AND source_id = ?
            ORDER BY observed_at ASC
            """,
            (source["series_id"], row["source_id"]),
        ).fetchall()
    return [
        {"observed_at": item["observed_at"], "value": round(float(item["value"]), 6)}
        for item in rows
    ]


def build_cross_asset_payload(
    history: dict[str, Any],
    config: dict[str, Any],
    source_health: list[dict[str, Any]],
    *,
    now: datetime,
    run_id: str,
    fetched_at: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    series = history.get("series", {})
    health_by_series = {
        str(item.get("series_id")): item for item in source_health if item.get("series_id")
    }
    btc_spx = align_ratio(
        series.get("btc_usd", []),
        series.get("sp500", []),
        numerator_key="btc_usd",
        denominator_key="sp500",
    )
    btc_gold = align_ratio(
        series.get("btc_usd", []),
        series.get("paxg_usd", []),
        numerator_key="btc_usd",
        denominator_key="paxg_usd",
    )
    broad_dollar_btc = align_dual_series(
        series.get("btc_usd", []),
        series.get("broad_dollar_index", []),
        first_key="btc_usd",
        second_key="broad_dollar_index",
    )

    def comparison_quality(*series_ids: str) -> str:
        statuses = [
            health_by_series.get(series_id, {}).get("quality_status", "unavailable")
            for series_id in series_ids
        ]
        if any(status not in ELIGIBLE_STATUSES for status in statuses):
            return "unavailable"
        return "fresh_cache" if "fresh_cache" in statuses else "fresh_network"

    btc_spx_quality = comparison_quality("btc_usd", "sp500")
    btc_gold_quality = comparison_quality("btc_usd", "paxg_usd")
    dollar_btc_quality = comparison_quality("btc_usd", "broad_dollar_index")
    metrics = {
        "cross_asset_btc_spx_ratio": _metric(
            "cross_asset_btc_spx_ratio",
            btc_spx,
            unit="ratio",
            source_id="coinbase_btc_and_fred_sp500",
            source_name=f"Coinbase BTC-USD 与 {health_by_series.get('sp500', {}).get('name', 'S&P 500 收盘数据')}",
            source_url=health_by_series.get("sp500", {}).get("url") or config["sp500"]["documentation_url"],
            quality_status=btc_spx_quality,
            fetched_at=fetched_at,
            metadata={
                "interpretation": "上升只表示 BTC 相对标普 500 更强，不表示资金从股票流入 BTC。",
                "alignment": "只使用双方都有正式数据的同一天，不前向填充。",
            },
        ),
        "cross_asset_btc_gold_ratio": _metric(
            "cross_asset_btc_gold_ratio",
            btc_gold,
            unit="gold_ounces",
            source_id="coinbase_btc_and_paxg",
            source_name="Coinbase BTC-USD 与 PAXG-USD",
            source_url=config["coinbase"]["sources"][1]["documentation_url"],
            quality_status=btc_gold_quality,
            fetched_at=fetched_at,
            metadata={
                "interpretation": "表示 1 枚 BTC 相当于多少盎司 PAXG 所代表的黄金。",
                "gold_proxy": "PAXG-USD",
                "caveat": "PAXG 是黄金代币代理，盘中价格可能与伦敦现货金略有偏差。",
            },
        ),
    }
    latest_dollar_date = broad_dollar_btc[-1]["observed_at"] if broad_dollar_btc else None
    metrics["cross_asset_btc_broad_dollar_corr_30d"] = _correlation_metric(
        "cross_asset_btc_broad_dollar_corr_30d",
        return_correlation(
            broad_dollar_btc,
            first_key="btc_usd",
            second_key="broad_dollar_index",
            window=30,
        ),
        latest_dollar_date,
        window=30,
        quality_status=dollar_btc_quality,
        fetched_at=fetched_at,
    )
    metrics["cross_asset_btc_broad_dollar_corr_90d"] = _correlation_metric(
        "cross_asset_btc_broad_dollar_corr_90d",
        return_correlation(
            broad_dollar_btc,
            first_key="btc_usd",
            second_key="broad_dollar_index",
            window=90,
        ),
        latest_dollar_date,
        window=90,
        quality_status=dollar_btc_quality,
        fetched_at=fetched_at,
    )
    comparisons = {
        "btc_spx": {
            "label": "BTC / 美股",
            "available_for_analysis": metrics["cross_asset_btc_spx_ratio"]["available_for_analysis"],
            "quality_status": btc_spx_quality,
            "observed_at": metrics["cross_asset_btc_spx_ratio"]["observed_at"],
            "latest": btc_spx[-1] if btc_spx else None,
            "changes": metrics["cross_asset_btc_spx_ratio"]["changes"],
            "point_count": len(btc_spx),
        },
        "btc_gold": {
            "label": "BTC / 黄金",
            "available_for_analysis": metrics["cross_asset_btc_gold_ratio"]["available_for_analysis"],
            "quality_status": btc_gold_quality,
            "observed_at": metrics["cross_asset_btc_gold_ratio"]["observed_at"],
            "latest": btc_gold[-1] if btc_gold else None,
            "changes": metrics["cross_asset_btc_gold_ratio"]["changes"],
            "point_count": len(btc_gold),
        },
        "broad_dollar_btc": {
            "label": "美元 / BTC",
            "available_for_analysis": dollar_btc_quality in ELIGIBLE_STATUSES and bool(broad_dollar_btc),
            "quality_status": dollar_btc_quality,
            "observed_at": latest_dollar_date,
            "latest": broad_dollar_btc[-1] if broad_dollar_btc else None,
            "correlation_30d": metrics["cross_asset_btc_broad_dollar_corr_30d"]["value"],
            "correlation_90d": metrics["cross_asset_btc_broad_dollar_corr_90d"]["value"],
            "point_count": len(broad_dollar_btc),
        },
    }
    warnings = [
        f"{item['name']}：{item.get('error')}"
        for item in source_health
        if item.get("error")
    ]
    available = any(item.get("available_for_analysis") for item in comparisons.values())
    quality_status = (
        "fresh_cache"
        if any(item.get("quality_status") == "fresh_cache" for item in comparisons.values())
        else "fresh_network" if available else "unavailable"
    )
    latest_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": iso_z(now),
        "status": "degraded" if warnings or not all(item.get("available_for_analysis") for item in comparisons.values()) else "ready",
        "quality_status": quality_status,
        "available_for_analysis": available,
        "metrics": metrics,
        "comparisons": comparisons,
        "sources": source_health,
        "quality": {
            "warnings": warnings,
            "missing_value_semantics": "null 表示不可用，永远不表示 0。",
            "revision_count": len(history.get("revisions", [])),
        },
        "methodology": {
            "role": "比较 BTC 与美股、黄金和美元的相对走势，不进入宏观流动性参考值公式。",
            "alignment": "所有比较只使用双方都有数据的共同日期，不对周末或节假日前向填充。",
            "bitcoin_close": "BTC 与 PAXG 取纽约时间 16:00 结束的小时收盘；PAXG 无成交时最多回看 8 小时并记录延迟。",
            "dollar": "美元使用美联储广义美元指数，不是 ICE DXY。",
            "correlation": "相关性使用共同观察日的日收益率计算，只描述同步关系，不证明因果。",
        },
    }
    complete_history = {
        **history,
        "schema_version": SCHEMA_VERSION,
        "updated_at": iso_z(now),
        "comparisons": {
            "btc_spx": btc_spx,
            "btc_gold": btc_gold,
            "broad_dollar_btc": broad_dollar_btc,
        },
    }
    return latest_payload, complete_history


def run_cross_asset_channel(
    root: Path,
    config_path: Path,
    data_dir: Path,
    *,
    direct: bool = False,
    fetcher: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    run_id = current.strftime("%Y%m%dT%H%M%S.%fZ")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise CrossAssetChannelError("cross-asset source configuration is invalid")
    transport = fetcher or CurlFetcher(config.get("request_policy", {}), direct=direct)
    previous_history = _load_object(data_dir / "history.json") or {
        "series": {},
        "revisions": [],
    }
    series = copy.deepcopy(previous_history.get("series", {}))
    previous_latest = _load_object(data_dir / "latest.json") or {}
    previous_health = {
        str(item.get("series_id")): item
        for item in previous_latest.get("sources", [])
        if isinstance(item, dict) and item.get("series_id")
    }
    fetched_at_values: list[str] = []
    source_health: list[dict[str, Any]] = []
    revisions = list(previous_history.get("revisions", []))
    history_days = int(config["history_days"])
    overlap_days = int(config["overlap_days"])
    pause_seconds = float(config.get("request_pause_seconds", 0)) if fetcher is None else 0.0

    for source in config["coinbase"]["sources"]:
        series_id = source["series_id"]
        existing = series.get(series_id, [])
        if existing:
            first_date = date.fromisoformat(existing[-1]["observed_at"]) - timedelta(days=overlap_days)
        else:
            first_date = current.date() - timedelta(days=history_days)
        local_zone = ZoneInfo(config["coinbase"]["close_timezone"])
        start = datetime.combine(first_date, clock_time.min, tzinfo=local_zone).astimezone(UTC)
        end = current
        network_ok = False
        error = None
        fetched_at = None
        try:
            incoming, fetched_at = _fetch_coinbase_series(
                transport,
                data_dir,
                source,
                config["coinbase"],
                start=start,
                end=end,
                run_id=run_id,
                now=current,
                pause_seconds=pause_seconds,
            )
            merged, detected = _merge_points(
                existing,
                incoming,
                series_id=series_id,
                detected_at=iso_z(current),
            )
            series[series_id] = merged
            revisions.extend(detected)
            network_ok = True
            if fetched_at:
                fetched_at_values.append(fetched_at)
        except (FetchError, CrossAssetChannelError, KeyError, TypeError, ValueError) as exc:
            error = str(exc)
            fetched_at = previous_health.get(series_id, {}).get("fetched_at")
        source_health.append(
            _source_health(
                source,
                series.get(series_id, []),
                now=current,
                fetched_at=fetched_at,
                network_ok=network_ok,
                error=error,
            )
        )

    sp500 = config["sp500"]
    sp500_existing = series.get(sp500["series_key"], [])
    sp500_ok = False
    sp500_error = None
    sp500_fetched_at = None
    sp500_selected_source = sp500
    try:
        start_date = (current.date() - timedelta(days=history_days)).isoformat()
        url = sp500["url_template"].format(start_date=start_date)
        fred_transport = transport if fetcher is not None else CurlFetcher(
            {
                **config.get("request_policy", {}),
                "timeout_seconds": sp500.get("primary_timeout_seconds", 15),
                "max_attempts": 1,
            },
            direct=direct,
        )
        response = fred_transport.fetch(url)
        _save_raw(data_dir, sp500["id"], run_id, response, url, suffix="history")
        incoming = parse_fred_sp500(response.body, series_id=sp500["series_id"], now=current)
        merged, detected = _merge_points(
            sp500_existing,
            incoming,
            series_id=sp500["series_key"],
            detected_at=iso_z(current),
        )
        series[sp500["series_key"]] = merged
        revisions.extend(detected)
        sp500_ok = True
        sp500_fetched_at = response.fetched_at
        fetched_at_values.append(response.fetched_at)
    except (FetchError, CrossAssetChannelError, KeyError, TypeError, ValueError) as exc:
        primary_error = str(exc)
        fallback = sp500.get("fallback", {})
        try:
            period1 = int(
                datetime.combine(
                    current.date() - timedelta(days=history_days),
                    clock_time.min,
                    tzinfo=UTC,
                ).timestamp()
            )
            period2 = int((current + timedelta(days=1)).timestamp())
            fallback_url = fallback["url_template"].format(
                period1=period1, period2=period2
            )
            response = transport.fetch(fallback_url)
            _save_raw(
                data_dir,
                fallback["id"],
                run_id,
                response,
                fallback_url,
                suffix="history-json",
            )
            incoming = parse_yahoo_sp500(response.body, now=current)
            merged, detected = _merge_points(
                sp500_existing,
                incoming,
                series_id=sp500["series_key"],
                detected_at=iso_z(current),
            )
            series[sp500["series_key"]] = merged
            revisions.extend(detected)
            sp500_ok = True
            sp500_fetched_at = response.fetched_at
            fetched_at_values.append(response.fetched_at)
            sp500_selected_source = fallback
            sp500_error = f"FRED 本轮未响应，已使用 Yahoo Finance 备用源。{primary_error}"
        except (FetchError, CrossAssetChannelError, KeyError, TypeError, ValueError) as fallback_exc:
            sp500_error = f"FRED: {primary_error}; Yahoo Finance: {fallback_exc}"
            sp500_fetched_at = previous_health.get(sp500["series_key"], {}).get("fetched_at")
    source_health.append(
        _source_health(
            {**sp500_selected_source, "series_id": sp500["series_key"]},
            series.get(sp500["series_key"], []),
            now=current,
            fetched_at=sp500_fetched_at,
            network_ok=sp500_ok,
            error=sp500_error,
        )
    )

    dollar = config["broad_dollar"]
    dollar_ok = False
    dollar_error = None
    try:
        incoming = _load_broad_dollar(root, dollar)
        merged, detected = _merge_points(
            series.get(dollar["series_key"], []),
            incoming,
            series_id=dollar["series_key"],
            detected_at=iso_z(current),
        )
        series[dollar["series_key"]] = merged
        revisions.extend(detected)
        dollar_ok = True
    except (CrossAssetChannelError, sqlite3.Error, KeyError, TypeError, ValueError) as exc:
        dollar_error = str(exc)
    source_health.append(
        _source_health(
            {**dollar, "series_id": dollar["series_key"]},
            series.get(dollar["series_key"], []),
            now=current,
            fetched_at=iso_z(current) if dollar_ok else previous_health.get(dollar["series_key"], {}).get("fetched_at"),
            network_ok=dollar_ok,
            error=dollar_error,
        )
    )

    history = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": iso_z(current),
        "series": series,
        "comparisons": previous_history.get("comparisons", {}),
        "revisions": revisions[-200:],
    }
    latest, history = build_cross_asset_payload(
        history,
        config,
        source_health,
        now=current,
        run_id=run_id,
        fetched_at=max(fetched_at_values, default=iso_z(current) if dollar_ok else None),
    )
    atomic_write_json(data_dir / "history.json", history)
    atomic_write_json(data_dir / "runs" / f"{run_id}.json", latest)
    atomic_write_json(data_dir / "latest.json", latest)
    if latest.get("available_for_analysis"):
        atomic_write_json(data_dir / "last-good.json", latest)
    return latest


def load_cross_asset_payload(root: Path) -> dict[str, Any]:
    payload = _load_object(root / "data" / "cross-asset" / "latest.json")
    if payload is not None:
        return payload
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "quality_status": "unavailable",
        "available_for_analysis": False,
        "metrics": {},
        "comparisons": {},
        "sources": [],
        "quality": {
            "warnings": ["跨资产比较尚未采集，不影响核心宏观数据和晨间分析。"],
            "missing_value_semantics": "null 表示不可用，永远不表示 0。",
        },
        "methodology": {
            "role": "比较 BTC 与美股、黄金和美元的相对走势，不进入宏观流动性参考值公式。"
        },
    }


def load_cross_asset_history(root: Path) -> dict[str, Any]:
    return _load_object(root / "data" / "cross-asset" / "history.json") or {
        "series": {},
        "comparisons": {},
        "revisions": [],
    }
