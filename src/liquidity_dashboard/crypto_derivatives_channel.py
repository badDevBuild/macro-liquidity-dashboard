from __future__ import annotations

import copy
import hashlib
import json
import math
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

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
SCHEMA_VERSION = "1.1"
ELIGIBLE_STATUSES = {"fresh_network", "fresh_cache"}
SOURCE_ID = "official_usdt_perpetuals_3_venues"
OPEN_INTEREST_METHODOLOGY_VERSION = "single_sided_v2"


class CryptoDerivativesChannelError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _number(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise CryptoDerivativesChannelError(f"{label} is missing")
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise CryptoDerivativesChannelError(f"{label} is not numeric") from exc
    if not math.isfinite(parsed):
        raise CryptoDerivativesChannelError(f"{label} is not finite")
    return parsed


def _milliseconds(value: Any, label: str) -> datetime:
    milliseconds = _number(value, label)
    try:
        return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise CryptoDerivativesChannelError(f"{label} is not a valid timestamp") from exc


def _json_payload(response: FetchResponse, label: str) -> Any:
    try:
        return json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CryptoDerivativesChannelError(f"{label} did not return valid JSON") from exc


def _first_row(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CryptoDerivativesChannelError(f"{label} response is not an object")
    code = payload.get("code")
    if code not in (None, "0", 0):
        raise CryptoDerivativesChannelError(
            f"{label} API failed: {payload.get('msg') or payload.get('retMsg') or code}"
        )
    result = payload.get("result")
    rows: Any
    if isinstance(result, dict):
        rows = result.get("list")
    else:
        rows = payload.get("data")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise CryptoDerivativesChannelError(f"{label} response has no data row")
    return rows[0]


def _rows(payload: Any, label: str) -> list[Any]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        code = payload.get("code")
        ret_code = payload.get("retCode")
        if code not in (None, "0", 0) or ret_code not in (None, 0, "0"):
            raise CryptoDerivativesChannelError(
                f"{label} API failed: {payload.get('msg') or payload.get('retMsg') or code or ret_code}"
            )
        result = payload.get("result")
        rows = result.get("list") if isinstance(result, dict) else payload.get("data")
    else:
        rows = None
    if not isinstance(rows, list) or not rows:
        raise CryptoDerivativesChannelError(f"{label} response has no data rows")
    return rows


def _latest_dict_row(payload: Any, label: str, timestamp_key: str) -> dict[str, Any]:
    candidates = [item for item in _rows(payload, label) if isinstance(item, dict)]
    if not candidates:
        raise CryptoDerivativesChannelError(f"{label} response has no object rows")
    return max(candidates, key=lambda item: _number(item.get(timestamp_key), f"{label} timestamp"))


def _validate_account_share(long_pct: float, short_pct: float, label: str) -> None:
    if not (0 <= long_pct <= 100 and 0 <= short_pct <= 100):
        raise CryptoDerivativesChannelError(f"{label} account share is outside 0-100%")
    if abs(long_pct + short_pct - 100) > 1:
        raise CryptoDerivativesChannelError(f"{label} long and short shares do not add to 100%")


def _validate_history_points(points: list[dict[str, Any]], *, now: datetime, label: str) -> list[dict[str, Any]]:
    clean: dict[str, dict[str, Any]] = {}
    for point in points:
        observed = _parse_moment(point.get("observed_at"))
        value = point.get("open_interest_usd_millions")
        if observed is None or value is None:
            continue
        if observed > now + timedelta(minutes=5):
            raise CryptoDerivativesChannelError(
                f"{label} contains future timestamp {iso_z(observed)}"
            )
        numeric = _number(value, f"{label} open interest")
        if numeric <= 0:
            raise CryptoDerivativesChannelError(f"{label} open interest is not positive")
        clean[iso_z(observed)] = {
            "observed_at": iso_z(observed),
            "open_interest_usd_millions": round(numeric, 6),
            "methodology_version": point.get("methodology_version"),
        }
    if not clean:
        raise CryptoDerivativesChannelError(f"{label} has no usable history points")
    return [clean[key] for key in sorted(clean)]


def _prior_open_interest(
    points: list[dict[str, Any]],
    current_observed_at: str,
    *,
    hours: int,
) -> dict[str, Any] | None:
    current = _parse_moment(current_observed_at)
    if current is None:
        return None
    target = current - timedelta(hours=hours)
    tolerance_hours = 3 if hours <= 24 else 8
    candidates: list[tuple[float, dict[str, Any]]] = []
    for point in points:
        observed = _parse_moment(point.get("observed_at"))
        if observed is None or observed >= current:
            continue
        # Prefer a full window. A point after the target would describe less
        # than 24 hours / 7 days even when it is equally close.
        if observed > target + timedelta(minutes=5):
            continue
        distance = abs((observed - target).total_seconds()) / 3600
        if distance <= tolerance_hours:
            candidates.append((distance, point))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _save_raw(
    data_dir: Path,
    venue: str,
    asset: str,
    endpoint: str,
    run_id: str,
    response: FetchResponse,
    url: str,
) -> str:
    digest = hashlib.sha256(response.body).hexdigest()
    stem = f"{run_id}-{endpoint}-{digest[:12]}"
    raw_path = data_dir / "raw" / venue / asset.lower() / f"{stem}.json"
    atomic_write_bytes(raw_path, response.body)
    atomic_write_json(
        raw_path.with_suffix(".json.meta.json"),
        {
            "source_id": SOURCE_ID,
            "venue": venue,
            "asset": asset,
            "endpoint": endpoint,
            "url": url,
            "fetched_at": response.fetched_at,
            "http_status": response.status_code,
            "attempts": response.attempts,
            "elapsed_ms": response.elapsed_ms,
            "sha256": digest,
            "byte_count": len(response.body),
        },
    )
    return digest


def _fetch(
    transport: Any,
    data_dir: Path,
    venue: str,
    asset: str,
    endpoint: str,
    run_id: str,
    url: str,
) -> tuple[Any, FetchResponse]:
    response = transport.fetch(url)
    _save_raw(data_dir, venue, asset, endpoint, run_id, response, url)
    return _json_payload(response, f"{venue} {asset} {endpoint}"), response


def _validated_observed_at(
    timestamps: list[datetime],
    *,
    now: datetime,
    freshness_minutes: int,
    label: str,
) -> datetime:
    if not timestamps:
        raise CryptoDerivativesChannelError(f"{label} has no observation timestamp")
    for timestamp in timestamps:
        if timestamp > now + timedelta(minutes=5):
            raise CryptoDerivativesChannelError(
                f"{label} contains future timestamp {iso_z(timestamp)}"
            )
        if now - timestamp > timedelta(minutes=freshness_minutes):
            raise CryptoDerivativesChannelError(
                f"{label} is stale at {iso_z(timestamp)}"
            )
    # An aggregate cannot be newer than its oldest required component.
    return min(timestamps)


def _validate_record(
    record: dict[str, Any], asset_config: dict[str, Any]
) -> dict[str, Any]:
    low, high = [float(item) for item in asset_config["price_range_usd"]]
    price = float(record["price_usd"])
    if not low <= price <= high:
        raise CryptoDerivativesChannelError(
            f"price {price} is outside configured range [{low}, {high}]"
        )
    open_interest = float(record["open_interest_usd_millions"])
    if not 0 < open_interest < 10_000_000:
        raise CryptoDerivativesChannelError("open interest is outside a plausible range")
    funding = float(record["funding_annualized_pct"])
    if abs(funding) > 10_000:
        raise CryptoDerivativesChannelError("annualized funding is outside a plausible range")
    if abs(float(record["price_change_24h_pct"])) > 99:
        raise CryptoDerivativesChannelError("24-hour price change is outside a plausible range")
    return record


def _binance_record(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    asset_config: dict[str, Any],
    *,
    interval_hours: float,
    now: datetime,
    freshness_minutes: int,
) -> dict[str, Any]:
    base = "https://fapi.binance.com/fapi/v1"
    premium, premium_response = _fetch(
        transport,
        data_dir,
        "binance",
        asset,
        "premium-index",
        run_id,
        f"{base}/premiumIndex?{urlencode({'symbol': symbol})}",
    )
    interest, interest_response = _fetch(
        transport,
        data_dir,
        "binance",
        asset,
        "open-interest",
        run_id,
        f"{base}/openInterest?{urlencode({'symbol': symbol})}",
    )
    ticker, ticker_response = _fetch(
        transport,
        data_dir,
        "binance",
        asset,
        "ticker-24h",
        run_id,
        f"{base}/ticker/24hr?{urlencode({'symbol': symbol})}",
    )
    if not all(isinstance(item, dict) for item in (premium, interest, ticker)):
        raise CryptoDerivativesChannelError("Binance response shape is invalid")
    price = _number(premium.get("markPrice"), "Binance mark price")
    funding_decimal = _number(premium.get("lastFundingRate"), "Binance funding rate")
    observed = _validated_observed_at(
        [
            _milliseconds(premium.get("time"), "Binance premium time"),
            _milliseconds(interest.get("time"), "Binance open-interest time"),
            _milliseconds(ticker.get("closeTime"), "Binance ticker time"),
        ],
        now=now,
        freshness_minutes=freshness_minutes,
        label="Binance",
    )
    record = {
        "venue": "binance",
        "venue_name": "Binance",
        "symbol": symbol,
        "observed_at": iso_z(observed),
        "fetched_at": max(
            premium_response.fetched_at,
            interest_response.fetched_at,
            ticker_response.fetched_at,
        ),
        "price_usd": round(price, 8),
        "price_change_24h_pct": round(
            _number(ticker.get("priceChangePercent"), "Binance 24h price change"), 6
        ),
        "open_interest_usd_millions": round(
            _number(interest.get("openInterest"), "Binance open interest")
            * price
            / 1_000_000,
            4,
        ),
        "open_interest_methodology_version": OPEN_INTEREST_METHODOLOGY_VERSION,
        "funding_rate_per_interval_pct": round(funding_decimal * 100, 8),
        "funding_interval_hours": round(interval_hours, 4),
        "funding_annualized_pct": round(
            funding_decimal * (24 / interval_hours) * 365 * 100, 6
        ),
    }
    return _validate_record(record, asset_config)


def _okx_record(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    asset_config: dict[str, Any],
    *,
    now: datetime,
    freshness_minutes: int,
) -> dict[str, Any]:
    base = "https://www.okx.com/api/v5"
    interest_payload, interest_response = _fetch(
        transport,
        data_dir,
        "okx",
        asset,
        "open-interest",
        run_id,
        f"{base}/public/open-interest?{urlencode({'instType': 'SWAP', 'instId': symbol})}",
    )
    funding_payload, funding_response = _fetch(
        transport,
        data_dir,
        "okx",
        asset,
        "funding-rate",
        run_id,
        f"{base}/public/funding-rate?{urlencode({'instId': symbol})}",
    )
    ticker_payload, ticker_response = _fetch(
        transport,
        data_dir,
        "okx",
        asset,
        "ticker",
        run_id,
        f"{base}/market/ticker?{urlencode({'instId': symbol})}",
    )
    interest = _first_row(interest_payload, "OKX open interest")
    funding = _first_row(funding_payload, "OKX funding")
    ticker = _first_row(ticker_payload, "OKX ticker")
    price = _number(ticker.get("last"), "OKX last price")
    open_24h = _number(ticker.get("open24h"), "OKX 24h open")
    funding_decimal = _number(funding.get("fundingRate"), "OKX funding rate")
    current_funding_time = _milliseconds(
        funding.get("fundingTime"), "OKX funding time"
    )
    next_funding_time = _milliseconds(
        funding.get("nextFundingTime"), "OKX next funding time"
    )
    interval_hours = (next_funding_time - current_funding_time).total_seconds() / 3600
    if not 0 < interval_hours <= 24:
        interval_hours = 8.0
    observed = _validated_observed_at(
        [
            _milliseconds(interest.get("ts"), "OKX open-interest time"),
            _milliseconds(funding.get("ts"), "OKX funding snapshot time"),
            _milliseconds(ticker.get("ts"), "OKX ticker time"),
        ],
        now=now,
        freshness_minutes=freshness_minutes,
        label="OKX",
    )
    record = {
        "venue": "okx",
        "venue_name": "OKX",
        "symbol": symbol,
        "observed_at": iso_z(observed),
        "fetched_at": max(
            interest_response.fetched_at,
            funding_response.fetched_at,
            ticker_response.fetched_at,
        ),
        "price_usd": round(price, 8),
        "price_change_24h_pct": round((price / open_24h - 1) * 100, 6),
        "open_interest_usd_millions": round(
            _number(interest.get("oiUsd"), "OKX open interest USD") / 1_000_000,
            4,
        ),
        "open_interest_methodology_version": OPEN_INTEREST_METHODOLOGY_VERSION,
        "funding_rate_per_interval_pct": round(funding_decimal * 100, 8),
        "funding_interval_hours": round(interval_hours, 4),
        "funding_annualized_pct": round(
            funding_decimal * (24 / interval_hours) * 365 * 100, 6
        ),
    }
    return _validate_record(record, asset_config)


def _bybit_record(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    asset_config: dict[str, Any],
    *,
    now: datetime,
    freshness_minutes: int,
) -> dict[str, Any]:
    url = "https://api.bybit.com/v5/market/tickers?" + urlencode(
        {"category": "linear", "symbol": symbol}
    )
    payload, response = _fetch(
        transport, data_dir, "bybit", asset, "ticker", run_id, url
    )
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        raise CryptoDerivativesChannelError(
            f"Bybit API failed: {payload.get('retMsg') if isinstance(payload, dict) else 'invalid response'}"
        )
    row = _first_row(payload, "Bybit ticker")
    interval_hours = _number(
        row.get("fundingIntervalHour") or 8, "Bybit funding interval"
    )
    funding_decimal = _number(row.get("fundingRate"), "Bybit funding rate")
    observed = _validated_observed_at(
        [_milliseconds(payload.get("time"), "Bybit response time")],
        now=now,
        freshness_minutes=freshness_minutes,
        label="Bybit",
    )
    record = {
        "venue": "bybit",
        "venue_name": "Bybit",
        "symbol": symbol,
        "observed_at": iso_z(observed),
        "fetched_at": response.fetched_at,
        "price_usd": round(_number(row.get("markPrice"), "Bybit mark price"), 8),
        "price_change_24h_pct": round(
            _number(row.get("price24hPcnt"), "Bybit 24h price change") * 100, 6
        ),
        "open_interest_usd_millions": round(
            _number(
                row.get("singleOpenInterestValue"),
                "Bybit single-sided open interest value",
            )
            / 1_000_000,
            4,
        ),
        "open_interest_methodology_version": OPEN_INTEREST_METHODOLOGY_VERSION,
        "funding_rate_per_interval_pct": round(funding_decimal * 100, 8),
        "funding_interval_hours": round(interval_hours, 4),
        "funding_annualized_pct": round(
            funding_decimal * (24 / interval_hours) * 365 * 100, 6
        ),
    }
    return _validate_record(record, asset_config)


def _binance_account_signal(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    *,
    now: datetime,
    freshness_minutes: int,
) -> dict[str, Any]:
    url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?" + urlencode(
        {"symbol": symbol, "period": "1h", "limit": 1}
    )
    payload, _ = _fetch(
        transport, data_dir, "binance", asset, "account-long-short", run_id, url
    )
    row = _latest_dict_row(payload, "Binance account ratio", "timestamp")
    long_pct = _number(row.get("longAccount"), "Binance long account share") * 100
    short_pct = _number(row.get("shortAccount"), "Binance short account share") * 100
    _validate_account_share(long_pct, short_pct, "Binance")
    observed = _validated_observed_at(
        [_milliseconds(row.get("timestamp"), "Binance account-ratio time")],
        now=now,
        freshness_minutes=freshness_minutes,
        label="Binance account ratio",
    )
    return {
        "account_long_pct": round(long_pct, 4),
        "account_short_pct": round(short_pct, 4),
        "account_long_short_ratio": round(long_pct / short_pct, 6) if short_pct else None,
        "account_ratio_observed_at": iso_z(observed),
    }


def _okx_account_signal(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    *,
    now: datetime,
    freshness_minutes: int,
) -> dict[str, Any]:
    url = "https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio-contract?" + urlencode(
        {"instId": symbol, "period": "1H", "limit": 1}
    )
    payload, _ = _fetch(
        transport, data_dir, "okx", asset, "account-long-short", run_id, url
    )
    rows = [item for item in _rows(payload, "OKX account ratio") if isinstance(item, list) and len(item) >= 2]
    if not rows:
        raise CryptoDerivativesChannelError("OKX account ratio response has no usable row")
    row = max(rows, key=lambda item: _number(item[0], "OKX account-ratio time"))
    ratio = _number(row[1], "OKX long-short account ratio")
    if ratio < 0:
        raise CryptoDerivativesChannelError("OKX long-short account ratio is negative")
    long_pct = ratio / (1 + ratio) * 100
    short_pct = 100 - long_pct
    _validate_account_share(long_pct, short_pct, "OKX")
    observed = _validated_observed_at(
        [_milliseconds(row[0], "OKX account-ratio time")],
        now=now,
        freshness_minutes=freshness_minutes,
        label="OKX account ratio",
    )
    return {
        "account_long_pct": round(long_pct, 4),
        "account_short_pct": round(short_pct, 4),
        "account_long_short_ratio": round(ratio, 6),
        "account_ratio_observed_at": iso_z(observed),
    }


def _bybit_account_signal(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    *,
    now: datetime,
    freshness_minutes: int,
) -> dict[str, Any]:
    url = "https://api.bybit.com/v5/market/account-ratio?" + urlencode(
        {"category": "linear", "symbol": symbol, "period": "1h", "limit": 1}
    )
    payload, _ = _fetch(
        transport, data_dir, "bybit", asset, "account-long-short", run_id, url
    )
    row = _latest_dict_row(payload, "Bybit account ratio", "timestamp")
    long_pct = _number(row.get("buyRatio"), "Bybit long account share") * 100
    short_pct = _number(row.get("sellRatio"), "Bybit short account share") * 100
    _validate_account_share(long_pct, short_pct, "Bybit")
    observed = _validated_observed_at(
        [_milliseconds(row.get("timestamp"), "Bybit account-ratio time")],
        now=now,
        freshness_minutes=freshness_minutes,
        label="Bybit account ratio",
    )
    return {
        "account_long_pct": round(long_pct, 4),
        "account_short_pct": round(short_pct, 4),
        "account_long_short_ratio": round(long_pct / short_pct, 6) if short_pct else None,
        "account_ratio_observed_at": iso_z(observed),
    }


def _taker_signal(
    rows: list[tuple[datetime, float, float]],
    *,
    now: datetime,
    freshness_minutes: int,
    label: str,
) -> dict[str, Any]:
    if len(rows) < 18:
        raise CryptoDerivativesChannelError(f"{label} has fewer than 18 hourly rows")
    rows = sorted(rows, key=lambda item: item[0])
    observed = _validated_observed_at(
        [rows[-1][0]],
        now=now,
        freshness_minutes=freshness_minutes,
        label=label,
    )
    span_hours = (rows[-1][0] - rows[0][0]).total_seconds() / 3600
    if span_hours < 17:
        raise CryptoDerivativesChannelError(f"{label} does not cover a usable 24-hour window")
    buy = sum(item[1] for item in rows)
    sell = sum(item[2] for item in rows)
    if buy < 0 or sell < 0 or buy + sell <= 0:
        raise CryptoDerivativesChannelError(f"{label} volume is invalid")
    return {
        "taker_buy_share_24h_pct": round(buy / (buy + sell) * 100, 4),
        "taker_sell_share_24h_pct": round(sell / (buy + sell) * 100, 4),
        "taker_window_start": iso_z(rows[0][0]),
        "taker_window_end": iso_z(observed),
    }


def _binance_taker_signal(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    *,
    now: datetime,
    freshness_minutes: int,
) -> dict[str, Any]:
    url = "https://fapi.binance.com/futures/data/takerlongshortRatio?" + urlencode(
        {"symbol": symbol, "period": "1h", "limit": 24}
    )
    payload, _ = _fetch(
        transport, data_dir, "binance", asset, "taker-volume-24h", run_id, url
    )
    rows = [
        (
            _milliseconds(row.get("timestamp"), "Binance taker time"),
            _number(row.get("buyVol"), "Binance taker buy volume"),
            _number(row.get("sellVol"), "Binance taker sell volume"),
        )
        for row in _rows(payload, "Binance taker volume")
        if isinstance(row, dict)
    ]
    return _taker_signal(
        rows,
        now=now,
        freshness_minutes=freshness_minutes,
        label="Binance taker volume",
    )


def _okx_taker_signal(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    *,
    now: datetime,
    freshness_minutes: int,
) -> dict[str, Any]:
    url = "https://www.okx.com/api/v5/rubik/stat/taker-volume-contract?" + urlencode(
        {"instId": symbol, "period": "1H", "limit": 24}
    )
    payload, _ = _fetch(
        transport, data_dir, "okx", asset, "taker-volume-24h", run_id, url
    )
    # OKX returns [timestamp, sell volume, buy volume].
    rows = [
        (
            _milliseconds(row[0], "OKX taker time"),
            _number(row[2], "OKX taker buy volume"),
            _number(row[1], "OKX taker sell volume"),
        )
        for row in _rows(payload, "OKX taker volume")
        if isinstance(row, list) and len(row) >= 3
    ]
    return _taker_signal(
        rows,
        now=now,
        freshness_minutes=freshness_minutes,
        label="OKX taker volume",
    )


def _binance_open_interest_history(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    url = "https://fapi.binance.com/futures/data/openInterestHist?" + urlencode(
        {"symbol": symbol, "period": "1h", "limit": 169}
    )
    payload, _ = _fetch(
        transport, data_dir, "binance", asset, "open-interest-history", run_id, url
    )
    points = [
        {
            "observed_at": iso_z(_milliseconds(row.get("timestamp"), "Binance OI history time")),
            "open_interest_usd_millions": _number(
                row.get("sumOpenInterestValue"), "Binance OI history value"
            )
            / 1_000_000,
            "methodology_version": OPEN_INTEREST_METHODOLOGY_VERSION,
        }
        for row in _rows(payload, "Binance OI history")
        if isinstance(row, dict)
    ]
    return _validate_history_points(points, now=now, label="Binance OI history")


def _okx_open_interest_history(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    base = "https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-history"
    url = base + "?" + urlencode({"instId": symbol, "period": "1H", "limit": 100})
    payload, _ = _fetch(
        transport, data_dir, "okx", asset, "open-interest-history", run_id, url
    )
    raw_rows = [item for item in _rows(payload, "OKX OI history") if isinstance(item, list) and len(item) >= 4]
    if raw_rows:
        oldest = min(_number(row[0], "OKX OI history time") for row in raw_rows)
        if now - datetime.fromtimestamp(oldest / 1000, tz=UTC) < timedelta(days=7, hours=4):
            older_url = base + "?" + urlencode(
                {"instId": symbol, "period": "1H", "end": int(oldest - 1), "limit": 100}
            )
            older_payload, _ = _fetch(
                transport, data_dir, "okx", asset, "open-interest-history-older", run_id, older_url
            )
            raw_rows.extend(
                item
                for item in _rows(older_payload, "OKX older OI history")
                if isinstance(item, list) and len(item) >= 4
            )
    points = [
        {
            "observed_at": iso_z(_milliseconds(row[0], "OKX OI history time")),
            "open_interest_usd_millions": _number(row[3], "OKX OI history USD") / 1_000_000,
            "methodology_version": OPEN_INTEREST_METHODOLOGY_VERSION,
        }
        for row in raw_rows
    ]
    return _validate_history_points(points, now=now, label="OKX OI history")


def _bybit_open_interest_history(
    transport: Any,
    data_dir: Path,
    run_id: str,
    asset: str,
    symbol: str,
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    interest_url = "https://api.bybit.com/v5/market/open-interest?" + urlencode(
        {"category": "linear", "symbol": symbol, "intervalTime": "1h", "limit": 169}
    )
    mark_url = "https://api.bybit.com/v5/market/mark-price-kline?" + urlencode(
        {"category": "linear", "symbol": symbol, "interval": "60", "limit": 169}
    )
    interest_payload, _ = _fetch(
        transport, data_dir, "bybit", asset, "open-interest-history", run_id, interest_url
    )
    mark_payload, _ = _fetch(
        transport, data_dir, "bybit", asset, "mark-price-history", run_id, mark_url
    )
    prices = {
        str(row[0]): _number(row[4], "Bybit historical mark close")
        for row in _rows(mark_payload, "Bybit mark-price history")
        if isinstance(row, list) and len(row) >= 5
    }
    points = []
    for row in _rows(interest_payload, "Bybit OI history"):
        if not isinstance(row, dict):
            continue
        timestamp = str(row.get("timestamp"))
        price = prices.get(timestamp)
        if price is None:
            continue
        points.append(
            {
                "observed_at": iso_z(_milliseconds(timestamp, "Bybit OI history time")),
                "open_interest_usd_millions": _number(
                    row.get("singleOpenInterest"),
                    "Bybit single-sided OI history value",
                )
                * price
                / 1_000_000,
                "methodology_version": OPEN_INTEREST_METHODOLOGY_VERSION,
            }
        )
    return _validate_history_points(points, now=now, label="Bybit OI history")


def _binance_intervals(
    transport: Any, data_dir: Path, run_id: str
) -> tuple[dict[str, float], str | None]:
    url = "https://fapi.binance.com/fapi/v1/fundingInfo"
    try:
        payload, _ = _fetch(
            transport, data_dir, "binance", "ALL", "funding-info", run_id, url
        )
        if not isinstance(payload, list):
            raise CryptoDerivativesChannelError("Binance funding-info shape is invalid")
        intervals = {
            str(row.get("symbol")): _number(
                row.get("fundingIntervalHours"), "Binance funding interval"
            )
            for row in payload
            if isinstance(row, dict) and row.get("symbol")
        }
        return intervals, None
    except (FetchError, CryptoDerivativesChannelError, TypeError, ValueError) as exc:
        return {}, str(exc)


def _parse_moment(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _aggregate_open_interest_change(
    records: list[dict[str, Any]],
    current_value: float,
    *,
    hours: int,
) -> dict[str, Any]:
    priors: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for record in records:
        history = record.get("open_interest_history")
        if not isinstance(history, list):
            history = []
        prior = _prior_open_interest(
            history,
            str(record.get("observed_at")),
            hours=hours,
        )
        if (
            prior is None
            or record.get("open_interest_methodology_version")
            != OPEN_INTEREST_METHODOLOGY_VERSION
            or prior.get("methodology_version")
            != OPEN_INTEREST_METHODOLOGY_VERSION
        ):
            return {
                "days": round(hours / 24, 4),
                "change": None,
                "percent_change": None,
                "prior_value": None,
                "prior_observed_at": None,
                "coverage_matched": False,
                "method": "official_venue_history",
            }
        priors.append((record, prior))
    prior_value = sum(float(item[1]["open_interest_usd_millions"]) for item in priors)
    delta = current_value - prior_value
    prior_times = [
        _parse_moment(item[1].get("observed_at"))
        for item in priors
        if _parse_moment(item[1].get("observed_at")) is not None
    ]
    return {
        "days": round(hours / 24, 4),
        "change": round(delta, 6),
        "percent_change": round(delta / abs(prior_value) * 100, 4) if prior_value else None,
        "prior_value": round(prior_value, 6),
        "prior_observed_at": iso_z(min(prior_times)) if prior_times else None,
        "coverage_matched": True,
        "method": "official_venue_history",
        "coverage": sorted(item[0]["venue"] for item in priors),
        "prior_observed_at_by_venue": {
            item[0]["venue"]: item[1]["observed_at"] for item in priors
        },
    }


def _aggregate_asset(
    asset: str,
    label: str,
    records: list[dict[str, Any]],
    *,
    minimum_venues: int,
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    if len(records) < minimum_venues:
        return None, [f"{asset} 只有 {len(records)}/{minimum_venues} 家有效交易所"]
    median_price = statistics.median(float(item["price_usd"]) for item in records)
    accepted = [
        item
        for item in records
        if abs(float(item["price_usd"]) / median_price - 1) <= 0.02
    ]
    excluded = sorted({item["venue_name"] for item in records} - {item["venue_name"] for item in accepted})
    if excluded:
        warnings.append(f"{asset} 剔除价格偏离超过 2% 的交易所：{', '.join(excluded)}")
    if len(accepted) < minimum_venues:
        return None, warnings + [f"{asset} 价格一致性校验后不足 {minimum_venues} 家"]
    open_interest = sum(float(item["open_interest_usd_millions"]) for item in accepted)
    funding = sum(
        float(item["funding_annualized_pct"])
        * float(item["open_interest_usd_millions"])
        for item in accepted
    ) / open_interest
    # Normalize every venue's current funding to the same eight-hour window
    # before presenting a cross-venue aggregate. The annualized value remains
    # a secondary comparison scale, not a realized yearly cost.
    funding_8h_equivalent = funding / (365 * 3)
    venues = sorted(item["venue"] for item in accepted)
    observed = min(_parse_moment(item["observed_at"]) for item in accepted)
    fetched = max(str(item["fetched_at"]) for item in accepted)
    account_records = [
        item for item in accepted if item.get("account_long_pct") is not None
    ]
    if len(account_records) >= minimum_venues:
        account_long = statistics.median(
            float(item["account_long_pct"]) for item in account_records
        )
        account_short = 100 - account_long
        account_venues = sorted(item["venue"] for item in account_records)
        account_observed = min(
            _parse_moment(item["account_ratio_observed_at"])
            for item in account_records
        )
    else:
        account_long = account_short = account_observed = None
        account_venues = []
        warnings.append(
            f"{asset} 账户多空比只有 {len(account_records)}/{minimum_venues} 家有效交易所"
        )
    taker_records = [
        item for item in accepted if item.get("taker_buy_share_24h_pct") is not None
    ]
    if len(taker_records) >= 2:
        taker_buy = statistics.median(
            float(item["taker_buy_share_24h_pct"]) for item in taker_records
        )
        taker_sell = 100 - taker_buy
        taker_venues = sorted(item["venue"] for item in taker_records)
        taker_observed = min(
            _parse_moment(item["taker_window_end"]) for item in taker_records
        )
        taker_window_start = max(
            _parse_moment(item["taker_window_start"]) for item in taker_records
        )
    else:
        taker_buy = taker_sell = taker_observed = taker_window_start = None
        taker_venues = []
        warnings.append(f"{asset} 主动买卖量只有 {len(taker_records)}/2 家有效交易所")
    open_interest_changes = {
        "1d": _aggregate_open_interest_change(accepted, open_interest, hours=24),
        "1w": _aggregate_open_interest_change(accepted, open_interest, hours=24 * 7),
    }
    return (
        {
            "symbol": asset,
            "label": label,
            "observed_at": iso_z(observed),
            "fetched_at": fetched,
            "quality_status": "fresh_network",
            "available_for_analysis": True,
            "coverage": venues,
            "coverage_key": "+".join(venues),
            "venue_count": len(venues),
            "open_interest_usd_millions": round(open_interest, 4),
            "open_interest_methodology_version": OPEN_INTEREST_METHODOLOGY_VERSION,
            "open_interest_changes": open_interest_changes,
            "funding_8h_equivalent_pct": round(funding_8h_equivalent, 8),
            "funding_annualized_pct": round(funding, 6),
            "price_usd": round(statistics.median(float(item["price_usd"]) for item in accepted), 8),
            "price_change_24h_pct": round(
                statistics.median(float(item["price_change_24h_pct"]) for item in accepted),
                6,
            ),
            "account_long_pct": round(account_long, 4) if account_long is not None else None,
            "account_short_pct": round(account_short, 4) if account_short is not None else None,
            "account_long_short_ratio": round(account_long / account_short, 6)
            if account_long is not None and account_short
            else None,
            "account_observed_at": iso_z(account_observed) if account_observed else None,
            "account_coverage": account_venues,
            "account_coverage_key": "+".join(account_venues) if account_venues else None,
            "taker_buy_share_24h_pct": round(taker_buy, 4) if taker_buy is not None else None,
            "taker_sell_share_24h_pct": round(taker_sell, 4) if taker_sell is not None else None,
            "taker_observed_at": iso_z(taker_observed) if taker_observed else None,
            "taker_window_start": iso_z(taker_window_start) if taker_window_start else None,
            "taker_coverage": taker_venues,
            "taker_coverage_key": "+".join(taker_venues) if taker_venues else None,
            "venues": [
                {key: value for key, value in item.items() if key != "open_interest_history"}
                for item in accepted
            ],
        },
        warnings,
    )


def _merge_history(
    previous: dict[str, Any] | None,
    aggregates: dict[str, dict[str, Any]],
    *,
    now: datetime,
    max_days: int,
) -> dict[str, Any]:
    history = copy.deepcopy(previous) if isinstance(previous, dict) else {}
    assets = history.get("assets") if isinstance(history.get("assets"), dict) else {}
    cutoff = now - timedelta(days=max_days)
    for asset, aggregate in aggregates.items():
        by_day: dict[str, dict[str, Any]] = {}
        for item in assets.get(asset, []):
            if not isinstance(item, dict) or not item.get("observed_at"):
                continue
            if (
                item.get("funding_8h_equivalent_pct") is None
                and item.get("funding_annualized_pct") is not None
            ):
                item = dict(item)
                item["funding_8h_equivalent_pct"] = round(
                    float(item["funding_annualized_pct"]) / (365 * 3), 8
                )
            observed = _parse_moment(item.get("observed_at"))
            if observed is None or observed < cutoff:
                continue
            day = iso_z(observed)[:10]
            existing = by_day.get(day)
            existing_time = _parse_moment(existing.get("observed_at")) if existing else None
            if existing_time is None or observed >= existing_time:
                by_day[day] = item
        for change in aggregate.get("open_interest_changes", {}).values():
            if not isinstance(change, dict) or not change.get("coverage_matched"):
                continue
            prior_observed_at = change.get("prior_observed_at")
            prior_value = change.get("prior_value")
            if prior_observed_at is None or prior_value is None:
                continue
            day = str(prior_observed_at)[:10]
            seed = dict(by_day.get(day, {}))
            seed.update(
                {
                    "observed_at": seed.get("observed_at") or prior_observed_at,
                    "coverage": seed.get("coverage") or aggregate.get("coverage", []),
                    "coverage_key": seed.get("coverage_key") or aggregate.get("coverage_key"),
                    "open_interest_usd_millions": prior_value,
                    "open_interest_methodology_version": OPEN_INTEREST_METHODOLOGY_VERSION,
                }
            )
            by_day[day] = seed
        point = {
            key: aggregate.get(key)
            for key in (
                "observed_at",
                "coverage",
                "coverage_key",
                "open_interest_usd_millions",
                "open_interest_methodology_version",
                "funding_8h_equivalent_pct",
                "funding_annualized_pct",
                "price_usd",
                "price_change_24h_pct",
                "account_long_pct",
                "account_short_pct",
                "account_long_short_ratio",
                "account_observed_at",
                "account_coverage",
                "account_coverage_key",
                "taker_buy_share_24h_pct",
                "taker_sell_share_24h_pct",
                "taker_observed_at",
                "taker_window_start",
                "taker_coverage",
                "taker_coverage_key",
            )
        }
        by_day[str(point["observed_at"])[:10]] = point
        assets[asset] = sorted(
            by_day.values(), key=lambda item: str(item.get("observed_at") or "")
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": iso_z(now),
        "assets": assets,
    }


def _change(
    points: list[dict[str, Any]],
    latest: dict[str, Any],
    field: str,
    *,
    hours: int,
    coverage_key_field: str = "coverage_key",
    methodology_version_field: str | None = None,
) -> dict[str, Any]:
    latest_time = _parse_moment(latest.get("observed_at"))
    if latest_time is None or latest.get(field) is None:
        prior = None
    else:
        candidates = []
        for item in points[:-1]:
            observed = _parse_moment(item.get("observed_at"))
            if (
                observed is None
                or item.get(field) is None
                or item.get(coverage_key_field) != latest.get(coverage_key_field)
                or (
                    methodology_version_field is not None
                    and item.get(methodology_version_field)
                    != latest.get(methodology_version_field)
                )
            ):
                continue
            age_hours = (latest_time - observed).total_seconds() / 3600
            if hours * 0.75 <= age_hours <= hours * 1.75:
                candidates.append((abs(age_hours - hours), item))
        prior = min(candidates, key=lambda pair: pair[0])[1] if candidates else None
    if prior is None:
        return {
            "days": round(hours / 24, 4),
            "change": None,
            "percent_change": None,
            "prior_value": None,
            "prior_observed_at": None,
            "coverage_matched": False,
        }
    current_value = float(latest[field])
    prior_value = float(prior[field])
    delta = current_value - prior_value
    return {
        "days": round(hours / 24, 4),
        "change": round(delta, 6),
        "percent_change": round(delta / abs(prior_value) * 100, 4) if prior_value else None,
        "prior_value": round(prior_value, 6),
        "prior_observed_at": prior["observed_at"],
        "coverage_matched": True,
    }


def _metric(
    metric_id: str,
    value: float | None,
    unit: str,
    aggregate: dict[str, Any],
    *,
    changes: dict[str, dict[str, Any]],
    sparkline: list[dict[str, Any]],
    observed_at: str | None = None,
    coverage: list[str] | None = None,
    coverage_key: str | None = None,
    scope: str | None = None,
    source_name: str | None = None,
) -> dict[str, Any]:
    one_day = changes.get("1d", {})
    one_week = changes.get("1w", {})
    return {
        "metric_id": metric_id,
        "group": "crypto_derivatives",
        "source_id": SOURCE_ID,
        "source_name": source_name or "Binance、OKX、Bybit 官方 USDT 永续合计",
        "source_url": "https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api",
        "authority": "official_primary_multi_source",
        "cadence": "continuous_sampled_daily",
        "quality_status": aggregate.get("quality_status", "unavailable"),
        "available_for_analysis": value is not None
        and aggregate.get("quality_status") in ELIGIBLE_STATUSES,
        "value": round(value, 6) if value is not None else None,
        "unit": unit,
        "observed_at": observed_at or aggregate.get("observed_at"),
        "age_days": 0,
        "fetched_at": aggregate.get("fetched_at"),
        "latest_change": one_day.get("change"),
        "latest_prior_value": one_day.get("prior_value"),
        "latest_prior_observed_at": one_day.get("prior_observed_at"),
        "week_change": one_week.get("change"),
        "week_prior_value": one_week.get("prior_value"),
        "week_prior_observed_at": one_week.get("prior_observed_at"),
        "changes": changes,
        "sparkline": sparkline,
        "metadata": {
            "asset": aggregate.get("symbol"),
            "coverage": coverage if coverage is not None else aggregate.get("coverage", []),
            "coverage_key": coverage_key or aggregate.get("coverage_key"),
            "scope": scope or "Binance、OKX、Bybit 的 USDT 永续；不是全市场",
            "methodology_version": (
                aggregate.get("open_interest_methodology_version")
                if metric_id.endswith("_open_interest")
                else "venue_weighted_v1"
            ),
        },
    }


def _asset_metrics(
    asset: str,
    aggregate: dict[str, Any],
    points: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if (
        aggregate.get("funding_8h_equivalent_pct") is None
        and aggregate.get("funding_annualized_pct") is not None
    ):
        aggregate["funding_8h_equivalent_pct"] = round(
            float(aggregate["funding_annualized_pct"]) / (365 * 3), 8
        )
    for point in points:
        if (
            point.get("funding_8h_equivalent_pct") is None
            and point.get("funding_annualized_pct") is not None
        ):
            point["funding_8h_equivalent_pct"] = round(
                float(point["funding_annualized_pct"]) / (365 * 3), 8
            )
    definitions = {
        "open_interest": ("open_interest_usd_millions", "usd_millions", "coverage_key"),
        "funding_8h_equivalent": ("funding_8h_equivalent_pct", "percent", "coverage_key"),
        "funding_annualized": ("funding_annualized_pct", "percent", "coverage_key"),
        "price_change_24h": ("price_change_24h_pct", "percent", "coverage_key"),
        "account_long_share": ("account_long_pct", "percent", "account_coverage_key"),
        "taker_buy_share_24h": ("taker_buy_share_24h_pct", "percent", "taker_coverage_key"),
    }
    result: dict[str, dict[str, Any]] = {}
    for suffix, (field, unit, coverage_key_field) in definitions.items():
        comparable_points = points
        if suffix == "open_interest":
            comparable_points = [
                item
                for item in points
                if item.get("open_interest_methodology_version")
                == aggregate.get("open_interest_methodology_version")
            ]
        if suffix == "open_interest" and isinstance(aggregate.get("open_interest_changes"), dict):
            changes = aggregate["open_interest_changes"]
        else:
            changes = {
                "1d": _change(
                    points,
                    points[-1],
                    field,
                    hours=24,
                    coverage_key_field=coverage_key_field,
                ) if points else {},
                "1w": _change(
                    points,
                    points[-1],
                    field,
                    hours=24 * 7,
                    coverage_key_field=coverage_key_field,
                ) if points else {},
            }
        sparkline = [
            {"observed_at": item["observed_at"], "value": item[field]}
            for item in comparable_points
            if item.get(field) is not None
        ]
        metric_id = f"derivatives_{asset.lower()}_{suffix}"
        if suffix == "account_long_share":
            metric_kwargs = {
                "observed_at": aggregate.get("account_observed_at"),
                "coverage": aggregate.get("account_coverage", []),
                "coverage_key": aggregate.get("account_coverage_key"),
                "scope": "三家交易所的账户多空占比中位数；统计账户数量，不是资金或仓位规模",
                "source_name": "Binance、OKX、Bybit 官方账户多空比",
            }
        elif suffix == "taker_buy_share_24h":
            metric_kwargs = {
                "observed_at": aggregate.get("taker_observed_at"),
                "coverage": aggregate.get("taker_coverage", []),
                "coverage_key": aggregate.get("taker_coverage_key"),
                "scope": "Binance、OKX 过去 24 小时主动买入占比的中位数；不是持仓方向",
                "source_name": "Binance、OKX 官方主动买卖量",
            }
        else:
            metric_kwargs = {}
        result[metric_id] = _metric(
            metric_id,
            aggregate.get(field),
            unit,
            aggregate,
            changes=changes,
            sparkline=sparkline,
            **metric_kwargs,
        )
    return result


def _cached_asset(
    previous: dict[str, Any] | None,
    asset: str,
    *,
    now: datetime,
    cache_minutes: int,
) -> dict[str, Any] | None:
    if not isinstance(previous, dict):
        return None
    candidate = previous.get("assets", {}).get(asset)
    if not isinstance(candidate, dict):
        return None
    fetched = _parse_moment(candidate.get("fetched_at"))
    if fetched is None or now - fetched > timedelta(minutes=cache_minutes):
        return None
    cached = copy.deepcopy(candidate)
    cached["quality_status"] = "fresh_cache"
    cached["available_for_analysis"] = True
    cached["cache_age_minutes"] = round((now - fetched).total_seconds() / 60, 1)
    return cached


def _unavailable_asset(asset: str, label: str, errors: list[str]) -> dict[str, Any]:
    return {
        "symbol": asset,
        "label": label,
        "quality_status": "unavailable",
        "available_for_analysis": False,
        "observed_at": None,
        "fetched_at": None,
        "coverage": [],
        "venue_count": 0,
        "errors": errors,
        "metrics": {},
    }


def run_crypto_derivatives_channel(
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
    if not isinstance(config, dict) or not isinstance(config.get("assets"), dict):
        raise CryptoDerivativesChannelError("derivatives source configuration is invalid")
    transport = fetcher or CurlFetcher(config.get("request_policy", {}), direct=direct)
    freshness_minutes = int(config.get("freshness_max_minutes", 30))
    signal_freshness_minutes = int(config.get("signal_freshness_max_minutes", 120))
    cache_minutes = int(config.get("cache_max_minutes", 180))
    minimum_venues = int(config.get("minimum_venues", 2))
    previous = _load_object(data_dir / "latest.json")
    interval_map, interval_error = _binance_intervals(transport, data_dir, run_id)
    assets: dict[str, dict[str, Any]] = {}
    successful_aggregates: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    errors_by_asset: dict[str, list[str]] = {}
    signal_errors_by_asset: dict[str, list[str]] = {}
    for asset, asset_config in config["assets"].items():
        label = str(asset_config.get("label") or asset)
        records: list[dict[str, Any]] = []
        asset_errors: list[str] = []
        asset_signal_errors: list[str] = []
        symbols = asset_config.get("symbols", {})
        collectors = {
            "binance": lambda: _binance_record(
                transport,
                data_dir,
                run_id,
                asset,
                symbols["binance"],
                asset_config,
                interval_hours=float(interval_map.get(symbols["binance"], 8)),
                now=current,
                freshness_minutes=freshness_minutes,
            ),
            "okx": lambda: _okx_record(
                transport,
                data_dir,
                run_id,
                asset,
                symbols["okx"],
                asset_config,
                now=current,
                freshness_minutes=freshness_minutes,
            ),
            "bybit": lambda: _bybit_record(
                transport,
                data_dir,
                run_id,
                asset,
                symbols["bybit"],
                asset_config,
                now=current,
                freshness_minutes=freshness_minutes,
            ),
        }
        account_collectors = {
            "binance": lambda: _binance_account_signal(
                transport,
                data_dir,
                run_id,
                asset,
                symbols["binance"],
                now=current,
                freshness_minutes=signal_freshness_minutes,
            ),
            "okx": lambda: _okx_account_signal(
                transport,
                data_dir,
                run_id,
                asset,
                symbols["okx"],
                now=current,
                freshness_minutes=signal_freshness_minutes,
            ),
            "bybit": lambda: _bybit_account_signal(
                transport,
                data_dir,
                run_id,
                asset,
                symbols["bybit"],
                now=current,
                freshness_minutes=signal_freshness_minutes,
            ),
        }
        taker_collectors = {
            "binance": lambda: _binance_taker_signal(
                transport,
                data_dir,
                run_id,
                asset,
                symbols["binance"],
                now=current,
                freshness_minutes=signal_freshness_minutes,
            ),
            "okx": lambda: _okx_taker_signal(
                transport,
                data_dir,
                run_id,
                asset,
                symbols["okx"],
                now=current,
                freshness_minutes=signal_freshness_minutes,
            ),
        }
        history_collectors = {
            "binance": lambda: _binance_open_interest_history(
                transport, data_dir, run_id, asset, symbols["binance"], now=current
            ),
            "okx": lambda: _okx_open_interest_history(
                transport, data_dir, run_id, asset, symbols["okx"], now=current
            ),
            "bybit": lambda: _bybit_open_interest_history(
                transport, data_dir, run_id, asset, symbols["bybit"], now=current
            ),
        }
        for venue, collector in collectors.items():
            try:
                record = collector()
            except (FetchError, CryptoDerivativesChannelError, KeyError, TypeError, ValueError) as exc:
                asset_errors.append(f"{venue}: {exc}")
                continue
            optional_collectors = [
                ("账户多空比", account_collectors.get(venue)),
                ("主动买卖量", taker_collectors.get(venue)),
                ("未平仓历史", history_collectors.get(venue)),
            ]
            for signal_name, signal_collector in optional_collectors:
                if signal_collector is None:
                    continue
                try:
                    signal = signal_collector()
                    if signal_name == "未平仓历史":
                        record["open_interest_history"] = signal
                    else:
                        record.update(signal)
                except (FetchError, CryptoDerivativesChannelError, KeyError, TypeError, ValueError) as exc:
                    asset_signal_errors.append(f"{venue} {signal_name}: {exc}")
            records.append(record)
        aggregate, aggregate_warnings = _aggregate_asset(
            asset, label, records, minimum_venues=minimum_venues
        )
        warnings.extend(aggregate_warnings)
        if asset_errors:
            errors_by_asset[asset] = asset_errors
        if asset_signal_errors:
            signal_errors_by_asset[asset] = asset_signal_errors
        if aggregate is not None:
            aggregate["errors"] = asset_errors
            aggregate["signal_errors"] = asset_signal_errors
            successful_aggregates[asset] = aggregate
            assets[asset] = aggregate
            continue
        cached = _cached_asset(
            previous, asset, now=current, cache_minutes=cache_minutes
        )
        if cached is not None:
            cached["errors"] = asset_errors + aggregate_warnings
            assets[asset] = cached
            warnings.append(f"{asset} 本轮采集不足，使用 {cached['cache_age_minutes']} 分钟内缓存")
        else:
            assets[asset] = _unavailable_asset(
                asset, label, asset_errors + aggregate_warnings
            )

    history_path = data_dir / "history.json"
    history = _merge_history(
        _load_object(history_path),
        successful_aggregates,
        now=current,
        max_days=int(config.get("history_max_days", 400)),
    )
    atomic_write_json(history_path, history)
    metrics: dict[str, dict[str, Any]] = {}
    for asset, asset_payload in assets.items():
        if not asset_payload.get("available_for_analysis"):
            continue
        points = [
            item
            for item in history.get("assets", {}).get(asset, [])
            if isinstance(item, dict)
        ]
        asset_metrics = _asset_metrics(asset, asset_payload, points)
        asset_payload["metrics"] = asset_metrics
        asset_payload["history"] = points
        metrics.update(asset_metrics)
    available_assets = [
        item for item in assets.values() if item.get("available_for_analysis")
    ]
    cached_assets = [
        item for item in available_assets if item.get("quality_status") == "fresh_cache"
    ]
    if (
        len(available_assets) == len(assets)
        and not cached_assets
        and not errors_by_asset
        and not signal_errors_by_asset
    ):
        status = "ready"
        quality_status = "fresh_network"
    elif available_assets:
        status = "degraded"
        quality_status = "fresh_cache" if cached_assets else "fresh_network"
    else:
        status = "unavailable"
        quality_status = "unavailable"
    if interval_error:
        warnings.append("Binance 未返回资金费率周期调整表，按常规 8 小时周期计算。")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": iso_z(current),
        "status": status,
        "quality_status": quality_status,
        "available_for_analysis": bool(available_assets),
        "assets": assets,
        "metrics": metrics,
        "coverage": {
            "scope": "Binance、OKX、Bybit 的 USDT 永续合约",
            "not_covered": ["其他交易所", "币本位合约", "季度交割合约", "全市场爆仓", "期权"],
            "minimum_venues": minimum_venues,
            "venues": config.get("venues", {}),
        },
        "quality": {
            "warnings": warnings,
            "errors_by_asset": errors_by_asset,
            "signal_errors_by_asset": signal_errors_by_asset,
            "available_asset_count": len(available_assets),
            "expected_asset_count": len(assets),
            "missing_value_semantics": "null 表示不可用，永远不表示 0。",
        },
        "methodology": {
            "role": "观察杠杆资金拥挤度，不进入宏观流动性公式。",
            "open_interest": "三家交易所 USDT 永续单边名义未平仓金额相加；Bybit 明确使用 singleOpenInterest 字段；24 小时和 7 天变化只比较同一批交易所、同一方法版本的官方历史快照。",
            "open_interest_methodology_version": OPEN_INTEREST_METHODOLOGY_VERSION,
            "funding": "各交易所资金费率按实际周期年化，再按未平仓金额加权。",
            "account_ratio": "三家多头账户占比取中位数；统计账户数量，不代表仓位或资金规模。",
            "taker_flow": "Binance、OKX 过去 24 小时主动买入占比分别计算后取中位数；代表成交方向，不代表持仓方向。",
            "direction": "未平仓量本身没有多空方向，必须和价格与资金费率一起看。",
            "boundary": "这是三家交易所的覆盖样本，不是全市场。",
        },
    }
    if available_assets:
        atomic_write_json(data_dir / "last-good.json", payload)
    atomic_write_json(data_dir / "runs" / f"{run_id}.json", payload)
    atomic_write_json(data_dir / "latest.json", payload)
    return payload


def load_crypto_derivatives_payload(root: Path) -> dict[str, Any]:
    payload = _load_object(root / "data" / "crypto" / "derivatives" / "latest.json")
    if payload is not None:
        # Older snapshots only stored the annualized comparison value. Derive
        # the exact eight-hour equivalent on read so a frontend release does
        # not depend on a successful network refresh first.
        assets = payload.get("assets", {})
        payload_metrics = payload.setdefault("metrics", {})
        methodology_version = payload.get("methodology", {}).get(
            "open_interest_methodology_version"
        )
        if methodology_version != OPEN_INTEREST_METHODOLOGY_VERSION:
            for metric_id, metric in payload_metrics.items():
                if not isinstance(metric, dict) or not metric_id.endswith(
                    ("_open_interest", "_funding_8h_equivalent", "_funding_annualized")
                ):
                    continue
                metric["publication_quality_status"] = metric.get("quality_status")
                metric["quality_status"] = "needs_methodology_refresh"
                metric["available_for_analysis"] = False
                metric.setdefault("metadata", {})["migration_required"] = (
                    OPEN_INTEREST_METHODOLOGY_VERSION
                )
            payload.setdefault("quality", {}).setdefault("warnings", []).append(
                "未平仓量与资金费率权重仍是旧双边口径；刷新为 single_sided_v2 前不进入分析。"
            )
        for asset, asset_payload in assets.items():
            if not isinstance(asset_payload, dict) or not asset_payload.get(
                "available_for_analysis"
            ):
                continue
            annualized = asset_payload.get("funding_annualized_pct")
            if (
                asset_payload.get("funding_8h_equivalent_pct") is None
                and annualized is not None
            ):
                asset_payload["funding_8h_equivalent_pct"] = round(
                    float(annualized) / (365 * 3), 8
                )
            points = asset_payload.get("history", [])
            if not isinstance(points, list):
                points = []
            for point in points:
                if (
                    isinstance(point, dict)
                    and point.get("funding_8h_equivalent_pct") is None
                    and point.get("funding_annualized_pct") is not None
                ):
                    point["funding_8h_equivalent_pct"] = round(
                        float(point["funding_annualized_pct"]) / (365 * 3), 8
                    )
            metric_id = f"derivatives_{asset.lower()}_funding_8h_equivalent"
            if payload_metrics.get(metric_id, {}).get("value") is None:
                metric = _asset_metrics(asset, asset_payload, points).get(metric_id)
                if metric is not None:
                    payload_metrics[metric_id] = metric
                    asset_payload.setdefault("metrics", {})[metric_id] = metric
        return payload
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "quality_status": "unavailable",
        "available_for_analysis": False,
        "assets": {},
        "metrics": {},
        "coverage": {
            "scope": "Binance、OKX、Bybit 的 USDT 永续合约",
            "not_covered": ["全市场爆仓", "期权"],
        },
        "quality": {"warnings": ["衍生品数据通道尚未运行。"]},
    }
