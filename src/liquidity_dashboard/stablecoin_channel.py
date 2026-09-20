from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
SOURCE_ID = "defillama_stablecoins"
ELIGIBLE_STATUSES = {"fresh_network", "fresh_cache"}


class StablecoinChannelError(RuntimeError):
    pass


def _json_object(body: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StablecoinChannelError(f"{label} did not return valid JSON") from exc
    if not isinstance(payload, dict):
        raise StablecoinChannelError(f"{label} did not return a JSON object")
    return payload


def _json_array(body: bytes, label: str) -> list[Any]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StablecoinChannelError(f"{label} did not return valid JSON") from exc
    if not isinstance(payload, list):
        raise StablecoinChannelError(f"{label} did not return a JSON array")
    return payload


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _epoch_date(value: Any) -> date:
    try:
        timestamp = int(str(value))
        return datetime.fromtimestamp(timestamp, tz=UTC).date()
    except (TypeError, ValueError, OSError, OverflowError) as exc:
        raise StablecoinChannelError(f"invalid stablecoin history date: {value!r}") from exc


def _nested_usd(item: dict[str, Any], field: str) -> float | None:
    nested = item.get(field)
    if not isinstance(nested, dict):
        return None
    return _finite_number(nested.get("peggedUSD"))


def _history_points(
    raw_rows: list[Any], *, today: date, source: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str]]:
    points: dict[str, float] = {}
    warnings: list[str] = []
    low, high = [float(value) for value in source["supply_range_usd"]]
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        observed = _epoch_date(raw.get("date"))
        if observed > today:
            raise StablecoinChannelError(
                f"stablecoin history contains future observation {observed.isoformat()}"
            )
        value = _nested_usd(raw, "totalCirculating")
        if value is None:
            continue
        # Stablecoin supply was legitimately tiny in the early history. Keep
        # those observations for the long chart and apply the configured
        # contemporary range only to the recent validation window below.
        if value <= 0 or value > high:
            raise StablecoinChannelError(
                f"stablecoin supply {value} is outside configured range"
            )
        key = observed.isoformat()
        previous = points.get(key)
        if previous is not None and not math.isclose(previous, value, rel_tol=1e-12):
            raise StablecoinChannelError(f"conflicting stablecoin supply for {key}")
        points[key] = value
    ordered = [
        {"observed_at": observed_at, "value": value / 1_000_000}
        for observed_at, value in sorted(points.items())
    ]
    if not ordered:
        raise StablecoinChannelError("stablecoin history has no usable USD observations")
    latest_date = date.fromisoformat(ordered[-1]["observed_at"])
    age_days = (today - latest_date).days
    if age_days > int(source["freshness_max_days"]):
        raise StablecoinChannelError(
            f"stablecoin history is {age_days} days old; freshness limit is {source['freshness_max_days']}"
        )
    recent_days = int(source["recent_window_days"])
    cutoff = latest_date - timedelta(days=recent_days - 1)
    recent_points = [
        item
        for item in ordered
        if date.fromisoformat(item["observed_at"]) >= cutoff
    ]
    recent_count = len(recent_points)
    recent_out_of_range = [
        item for item in recent_points if not low <= float(item["value"]) * 1_000_000 <= high
    ]
    if recent_out_of_range:
        first = recent_out_of_range[0]
        raise StablecoinChannelError(
            "recent stablecoin supply "
            f"{float(first['value']) * 1_000_000} on {first['observed_at']} "
            "is outside configured range"
        )
    minimum = int(source["minimum_recent_daily_points"])
    if recent_count < minimum:
        raise StablecoinChannelError(
            f"stablecoin history has only {recent_count}/{recent_days} recent daily points"
        )
    if recent_count < recent_days:
        warnings.append(
            f"最近 {recent_days} 天有 {recent_count} 个日度观测，达到门槛但并非每天都有数据。"
        )
    return ordered, warnings


def _nearest_on_or_before(
    points: list[dict[str, Any]], target: date
) -> dict[str, Any] | None:
    for item in reversed(points):
        if date.fromisoformat(item["observed_at"]) <= target:
            return item
    return None


def _change(
    points: list[dict[str, Any]], latest: dict[str, Any], days: int
) -> dict[str, Any]:
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
        "change": round(change, 4),
        "percent_change": round(percent, 4) if percent is not None else None,
        "prior_value": round(float(prior["value"]), 4),
        "prior_observed_at": prior["observed_at"],
    }


def _component_change(
    current: float, prior: float | None, days: int, observed_at: date
) -> dict[str, Any]:
    if prior is None:
        return {
            "days": days,
            "change": None,
            "percent_change": None,
            "prior_value": None,
            "prior_observed_at": None,
        }
    current_m = current / 1_000_000
    prior_m = prior / 1_000_000
    change = current_m - prior_m
    percent = change / abs(prior_m) * 100 if prior_m else None
    return {
        "days": days,
        "change": round(change, 4),
        "percent_change": round(percent, 4) if percent is not None else None,
        "prior_value": round(prior_m, 4),
        "prior_observed_at": (observed_at - timedelta(days=days)).isoformat(),
    }


def _base_metric(
    metric_id: str,
    value: float | None,
    unit: str,
    observed_at: str,
    fetched_at: str,
    source: dict[str, Any],
    *,
    changes: dict[str, dict[str, Any]] | None = None,
    sparkline: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    change_map = changes or {}
    latest = change_map.get("1d", {})
    return {
        "metric_id": metric_id,
        "group": "crypto_liquidity",
        "source_id": source["id"],
        "source_name": source["name"],
        "source_url": source["documentation_url"],
        "authority": source["authority"],
        "cadence": source["cadence"],
        "quality_status": "fresh_network",
        "available_for_analysis": value is not None,
        "value": round(value, 4) if value is not None else None,
        "unit": unit,
        "observed_at": observed_at,
        "age_days": 0,
        "fetched_at": fetched_at,
        "latest_change": latest.get("change"),
        "latest_prior_value": latest.get("prior_value"),
        "latest_prior_observed_at": latest.get("prior_observed_at"),
        "week_change": change_map.get("1w", {}).get("change"),
        "week_prior_value": change_map.get("1w", {}).get("prior_value"),
        "week_prior_observed_at": change_map.get("1w", {}).get("prior_observed_at"),
        "changes": change_map,
        "sparkline": sparkline or [],
        "metadata": metadata or {},
    }


def _asset_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_assets = payload.get("peggedAssets")
    if not isinstance(raw_assets, list):
        raise StablecoinChannelError("stablecoin composition is missing peggedAssets")
    assets = [
        item
        for item in raw_assets
        if isinstance(item, dict)
        and item.get("pegType") == "peggedUSD"
        and _nested_usd(item, "circulating") is not None
    ]
    identifiers = [str(item.get("id") or "") for item in assets]
    if not identifiers or any(not identifier for identifier in identifiers):
        raise StablecoinChannelError("stablecoin composition contains a missing asset id")
    if len(identifiers) != len(set(identifiers)):
        raise StablecoinChannelError("stablecoin composition contains duplicate asset ids")
    return assets


def _sum_field(assets: list[dict[str, Any]], field: str) -> float | None:
    values = [_nested_usd(item, field) for item in assets]
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _asset_metric(
    asset: dict[str, Any],
    metric_id: str,
    observed_at: date,
    fetched_at: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    current = _nested_usd(asset, "circulating")
    if current is None:
        raise StablecoinChannelError(f"{metric_id} has no circulating supply")
    changes = {
        "1d": _component_change(
            current, _nested_usd(asset, "circulatingPrevDay"), 1, observed_at
        ),
        "1w": _component_change(
            current, _nested_usd(asset, "circulatingPrevWeek"), 7, observed_at
        ),
        "1m": _component_change(
            current, _nested_usd(asset, "circulatingPrevMonth"), 30, observed_at
        ),
    }
    return _base_metric(
        metric_id,
        current / 1_000_000,
        "usd_millions",
        observed_at.isoformat(),
        fetched_at,
        source,
        changes=changes,
        metadata={
            "asset_id": str(asset.get("id")),
            "symbol": str(asset.get("symbol") or ""),
            "name": str(asset.get("name") or ""),
            "price": _finite_number(asset.get("price")),
            "observation_method": "当前列表没有独立时间戳，日期使用本次抓取日。",
        },
    )


def _other_metric(
    assets: list[dict[str, Any]],
    usdt: dict[str, Any],
    usdc: dict[str, Any],
    observed_at: date,
    fetched_at: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    current = _sum_field(assets, "circulating")
    usdt_current = _nested_usd(usdt, "circulating")
    usdc_current = _nested_usd(usdc, "circulating")
    if current is None or usdt_current is None or usdc_current is None:
        raise StablecoinChannelError("cannot calculate other stablecoin supply")

    def prior(field: str) -> float | None:
        total = _sum_field(assets, field)
        first = _nested_usd(usdt, field)
        second = _nested_usd(usdc, field)
        if total is None or first is None or second is None:
            return None
        return total - first - second

    other = current - usdt_current - usdc_current
    changes = {
        "1d": _component_change(other, prior("circulatingPrevDay"), 1, observed_at),
        "1w": _component_change(other, prior("circulatingPrevWeek"), 7, observed_at),
        "1m": _component_change(other, prior("circulatingPrevMonth"), 30, observed_at),
    }
    return _base_metric(
        "stablecoin_other_supply",
        other / 1_000_000,
        "usd_millions",
        observed_at.isoformat(),
        fetched_at,
        source,
        changes=changes,
        metadata={"asset_count": max(0, len(assets) - 2)},
    )


def _peg_metric(
    assets: list[dict[str, Any]],
    observed_at: date,
    fetched_at: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    ranked = sorted(
        assets,
        key=lambda item: _nested_usd(item, "circulating") or 0,
        reverse=True,
    )
    basket: list[dict[str, Any]] = []
    excluded_yield_bearing = 0
    for asset in ranked:
        # Yield-bearing tokens such as USYC accrue income into NAV, so a price
        # above $1 is not a depeg. They remain in supply totals but must not be
        # compared with payment stablecoins that target a constant $1 price.
        if asset.get("yieldBearing") is True:
            excluded_yield_bearing += 1
            continue
        price = _finite_number(asset.get("price"))
        supply = _nested_usd(asset, "circulating")
        if price is None or supply is None:
            continue
        basket.append(
            {
                "asset_id": str(asset.get("id")),
                "symbol": str(asset.get("symbol") or asset.get("name") or "未知"),
                "name": str(asset.get("name") or ""),
                "price": round(price, 8),
                "supply_usd_millions": round(supply / 1_000_000, 4),
                "deviation_bps": round(abs(price - 1) * 10_000, 4),
            }
        )
        if len(basket) >= int(source["peg_basket_size"]):
            break
    if not basket:
        return _base_metric(
            "stablecoin_core_max_depeg_bps",
            None,
            "basis_points",
            observed_at.isoformat(),
            fetched_at,
            source,
        )
    largest = max(basket, key=lambda item: item["deviation_bps"])
    return _base_metric(
        "stablecoin_core_max_depeg_bps",
        largest["deviation_bps"],
        "basis_points",
        observed_at.isoformat(),
        fetched_at,
        source,
        metadata={
            "symbol": largest["symbol"],
            "price": largest["price"],
            "basket_size": len(basket),
            "excluded_yield_bearing": excluded_yield_bearing,
            "basket": basket,
        },
    )


def build_stablecoin_payload(
    history_body: bytes,
    composition_body: bytes,
    config: dict[str, Any],
    *,
    now: datetime,
    run_id: str,
    fetched_at: str,
) -> dict[str, Any]:
    source = config["source"]
    today = now.astimezone(UTC).date()
    points, warnings = _history_points(
        _json_array(history_body, "stablecoin history"), today=today, source=source
    )
    latest = points[-1]
    latest_date = date.fromisoformat(latest["observed_at"])
    total_changes = {
        "1d": _change(points, latest, 1),
        "1w": _change(points, latest, 7),
        "1m": _change(points, latest, 31),
        "3m": _change(points, latest, 93),
        "1y": _change(points, latest, 366),
    }
    one_year_cutoff = latest_date - timedelta(days=366)
    one_year_points = [
        item for item in points if date.fromisoformat(item["observed_at"]) >= one_year_cutoff
    ]
    total_metric = _base_metric(
        "stablecoin_usd_supply",
        float(latest["value"]),
        "usd_millions",
        latest["observed_at"],
        fetched_at,
        source,
        changes=total_changes,
        sparkline=one_year_points,
        metadata={
            "calculation": "DefiLlama totalCirculating.peggedUSD，按面值计算，换算为百万美元。",
            "price_adjusted_market_cap_used": False,
        },
    )

    assets = _asset_rows(_json_object(composition_body, "stablecoin composition"))
    by_id = {str(item["id"]): item for item in assets}
    usdt = by_id.get(str(source["asset_ids"]["usdt"]))
    usdc = by_id.get(str(source["asset_ids"]["usdc"]))
    if usdt is None or usdc is None:
        raise StablecoinChannelError("stablecoin composition is missing USDT or USDC")
    component_date = today
    usdt_metric = _asset_metric(
        usdt, "stablecoin_usdt_supply", component_date, fetched_at, source
    )
    usdc_metric = _asset_metric(
        usdc, "stablecoin_usdc_supply", component_date, fetched_at, source
    )
    other_metric = _other_metric(
        assets, usdt, usdc, component_date, fetched_at, source
    )
    peg_metric = _peg_metric(assets, component_date, fetched_at, source)
    list_total = _sum_field(assets, "circulating")
    if list_total is None:
        raise StablecoinChannelError("stablecoin composition total is unavailable")
    aggregate_total = float(latest["value"]) * 1_000_000
    mismatch_percent = abs(list_total - aggregate_total) / aggregate_total * 100
    warning_threshold = float(source["composition_warning_percent"])
    block_threshold = float(source["composition_block_percent"])
    composition_available = mismatch_percent <= block_threshold
    if mismatch_percent > warning_threshold:
        warnings.append(
            f"总量历史接口与币种列表相差 {mismatch_percent:.2f}%，分项按独立列表口径展示。"
        )

    current_usdt = _nested_usd(usdt, "circulating") or 0
    current_usdc = _nested_usd(usdc, "circulating") or 0
    share_metric = _base_metric(
        "stablecoin_usdt_usdc_share",
        (current_usdt + current_usdc) / list_total,
        "probability",
        component_date.isoformat(),
        fetched_at,
        source,
        metadata={"denominator": "同一次币种列表中的美元锚定资产面值总量"},
    )

    if not composition_available:
        for metric in (usdt_metric, usdc_metric, other_metric, share_metric):
            metric["quality_status"] = "data_conflict"
            metric["available_for_analysis"] = False
        warnings.append("分项和总量差异超过 3%，本轮不让 Agent 使用分项。")

    day_change = total_changes["1d"].get("percent_change")
    daily_warning = (
        isinstance(day_change, (int, float))
        and abs(float(day_change)) > float(source["daily_move_warning_percent"])
    )
    if daily_warning:
        warnings.append(
            f"稳定币总供给单日变化 {day_change:.2f}%，超过异常复核阈值，本轮降低可信状态。"
        )

    metrics = {
        item["metric_id"]: item
        for item in (
            total_metric,
            usdt_metric,
            usdc_metric,
            other_metric,
            share_metric,
            peg_metric,
        )
    }
    if daily_warning:
        total_metric["quality_status"] = "needs_review"
        total_metric["available_for_analysis"] = False

    status = "degraded" if warnings or not composition_available or daily_warning else "ready"
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": iso_z(now),
        "status": status,
        "quality_status": "fresh_network",
        "available_for_analysis": any(
            item.get("available_for_analysis") for item in metrics.values()
        ),
        "source": {
            "source_id": source["id"],
            "name": source["name"],
            "source_owner": source["source_owner"],
            "authority": source["authority"],
            "cadence": source["cadence"],
            "url": source["documentation_url"],
            "history_url": source["history_url"],
            "composition_url": source["composition_url"],
            "fetched_at": fetched_at,
            "observed_at": latest["observed_at"],
            "age_days": (today - latest_date).days,
            "error": None,
        },
        # Keep the complete aggregate history in the release for the on-demand
        # series API. The dashboard summary exposes only the one-year
        # sparkline so the normal morning payload stays compact.
        "history": points,
        "metrics": metrics,
        "composition": {
            "available": composition_available,
            "captured_at": fetched_at,
            "list_total_usd_millions": round(list_total / 1_000_000, 4),
            "aggregate_total_usd_millions": round(float(latest["value"]), 4),
            "difference_percent": round(mismatch_percent, 4),
            "asset_count": len(assets),
            "items": [
                {
                    "metric_id": item["metric_id"],
                    "label": label,
                    "value": item["value"],
                    "unit": item["unit"],
                    "change_1w": item.get("changes", {}).get("1w", {}).get("change"),
                    "share": round(float(item["value"]) / (list_total / 1_000_000), 6),
                }
                for item, label in (
                    (usdt_metric, "USDT"),
                    (usdc_metric, "USDC"),
                    (other_metric, "其他"),
                )
            ],
        },
        "quality": {
            "warnings": warnings,
            "recent_daily_point_count": sum(
                date.fromisoformat(item["observed_at"])
                >= latest_date - timedelta(days=int(source["recent_window_days"]) - 1)
                for item in points
            ),
            "recent_window_days": int(source["recent_window_days"]),
            "composition_difference_percent": round(mismatch_percent, 4),
            "missing_value_semantics": "null 表示不可用，永远不表示 0。",
        },
        "issuer_cross_checks": config.get("issuer_cross_checks", []),
        "methodology": {
            "role": "加密内部流动性，只用于观察链上美元容量，不进入宏观流动性参考值公式。",
            "supply": "总供给使用美元锚定资产的面值流通量，不使用价格调整后的市值。",
            "interpretation": "供给增加表示链上美元容量增加，不代表资金已经买入 BTC 或其他资产。",
            "composition": "总量历史和币种列表可能异步刷新，分项不与总量强行凑成完全相等。",
            "peg": f"排除价格会随收益上涨的生息型代币后，从按供给排序且有价格的前 {int(source['peg_basket_size'])} 个美元稳定币中，找出偏离 1 美元最多的一项。",
        },
    }


def _save_raw(
    data_dir: Path, label: str, run_id: str, response: FetchResponse, url: str
) -> None:
    digest = hashlib.sha256(response.body).hexdigest()
    raw_path = data_dir / "raw" / label / f"{run_id}-{digest[:12]}.json"
    atomic_write_bytes(raw_path, response.body)
    atomic_write_json(
        raw_path.with_suffix(".json.meta.json"),
        {
            "source_id": SOURCE_ID,
            "part": label,
            "url": url,
            "fetched_at": response.fetched_at,
            "http_status": response.status_code,
            "attempts": response.attempts,
            "elapsed_ms": response.elapsed_ms,
            "sha256": digest,
            "byte_count": len(response.body),
        },
    )


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _cached_payload(
    previous: dict[str, Any], *, now: datetime, run_id: str, error: str, max_days: int
) -> dict[str, Any] | None:
    fetched_at = str(previous.get("source", {}).get("fetched_at") or "")
    try:
        fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=UTC)
    age_days = max(0, (now.astimezone(UTC).date() - fetched.astimezone(UTC).date()).days)
    if age_days > max_days:
        return None
    cached = copy.deepcopy(previous)
    cached.update(
        {
            "run_id": run_id,
            "generated_at": iso_z(now),
            "status": "degraded",
            "quality_status": "fresh_cache",
            "available_for_analysis": True,
        }
    )
    cached["source"]["age_days"] = age_days
    cached["source"]["error"] = error
    cached.setdefault("quality", {}).setdefault("warnings", []).append(
        f"本次抓取失败，使用 {age_days} 天内缓存。"
    )
    for metric in cached.get("metrics", {}).values():
        if not isinstance(metric, dict):
            continue
        metric["quality_status"] = "fresh_cache"
        metric["age_days"] = age_days
        metric["available_for_analysis"] = metric.get("value") is not None
    return cached


def _unavailable_payload(
    config: dict[str, Any], *, now: datetime, run_id: str, error: str
) -> dict[str, Any]:
    source = config["source"]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": iso_z(now),
        "status": "unavailable",
        "quality_status": "unavailable",
        "available_for_analysis": False,
        "source": {
            "source_id": source["id"],
            "name": source["name"],
            "source_owner": source["source_owner"],
            "authority": source["authority"],
            "cadence": source["cadence"],
            "url": source["documentation_url"],
            "history_url": source["history_url"],
            "composition_url": source["composition_url"],
            "fetched_at": None,
            "observed_at": None,
            "age_days": None,
            "error": error,
        },
        "metrics": {},
        "composition": {"available": False, "items": []},
        "quality": {
            "warnings": ["稳定币数据暂不可用，不影响核心宏观数据和分析。"],
            "missing_value_semantics": "null 表示不可用，永远不表示 0。",
        },
        "issuer_cross_checks": config.get("issuer_cross_checks", []),
        "methodology": {
            "role": "加密内部流动性，只用于观察链上美元容量，不进入宏观流动性参考值公式。"
        },
    }


def run_stablecoin_channel(
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
    if not isinstance(config, dict) or not isinstance(config.get("source"), dict):
        raise StablecoinChannelError("stablecoin source configuration is invalid")
    source = config["source"]
    fetcher = fetcher or CurlFetcher(config.get("request_policy", {}), direct=direct)
    try:
        history_response = fetcher.fetch(source["history_url"])
        composition_response = fetcher.fetch(source["composition_url"])
        _save_raw(data_dir, "history", run_id, history_response, source["history_url"])
        _save_raw(
            data_dir,
            "composition",
            run_id,
            composition_response,
            source["composition_url"],
        )
        payload = build_stablecoin_payload(
            history_response.body,
            composition_response.body,
            config,
            now=current,
            run_id=run_id,
            fetched_at=max(history_response.fetched_at, composition_response.fetched_at),
        )
        atomic_write_json(data_dir / "last-good.json", payload)
    except (FetchError, StablecoinChannelError, KeyError, TypeError, ValueError) as exc:
        error = str(exc)
        previous = _load_object(data_dir / "last-good.json")
        payload = (
            _cached_payload(
                previous,
                now=current,
                run_id=run_id,
                error=error,
                max_days=int(source["cache_max_days"]),
            )
            if previous
            else None
        )
        if payload is None:
            payload = _unavailable_payload(
                config, now=current, run_id=run_id, error=error
            )
    atomic_write_json(data_dir / "runs" / f"{run_id}.json", payload)
    atomic_write_json(data_dir / "latest.json", payload)
    return payload


def load_stablecoin_payload(root: Path) -> dict[str, Any]:
    payload = _load_object(root / "data" / "stablecoins" / "latest.json")
    if payload is not None:
        return payload
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "quality_status": "unavailable",
        "available_for_analysis": False,
        "source": {
            "source_id": SOURCE_ID,
            "name": "DefiLlama stablecoin data",
            "source_owner": "DefiLlama",
            "authority": "trusted_aggregator",
            "cadence": "calendar_daily",
            "url": "https://defillama.com/docs/api",
            "error": "尚未运行稳定币数据通道",
        },
        "metrics": {},
        "composition": {"available": False, "items": []},
        "quality": {
            "warnings": ["稳定币数据尚未采集，不影响核心宏观数据。"],
            "missing_value_semantics": "null 表示不可用，永远不表示 0。",
        },
        "methodology": {
            "role": "加密内部流动性，只用于观察链上美元容量，不进入宏观流动性参考值公式。"
        },
    }
