from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
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
SCHEMA_VERSION = "1.0"
ELIGIBLE_STATUSES = {"fresh_network", "fresh_cache"}
CHANGE_WINDOWS = {"1d": 1, "1w": 7, "1m": 31, "3m": 93, "1y": 366}


class EnergyChannelError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def _number(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise EnergyChannelError(f"{label} is missing")
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise EnergyChannelError(f"{label} is not numeric") from exc
    if not math.isfinite(parsed):
        raise EnergyChannelError(f"{label} is not finite")
    return parsed


def parse_fred_series(body: bytes, *, series_id: str, now: datetime) -> list[dict[str, Any]]:
    try:
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise EnergyChannelError("FRED oil history is not UTF-8 CSV") from exc
    if not reader.fieldnames or "observation_date" not in reader.fieldnames:
        raise EnergyChannelError("FRED oil CSV is missing observation_date")
    if series_id not in reader.fieldnames:
        raise EnergyChannelError(f"FRED oil CSV is missing {series_id}")
    points: dict[str, float] = {}
    for row in reader:
        raw = row.get(series_id)
        if raw in (None, "", "."):
            continue
        try:
            observed = date.fromisoformat(str(row.get("observation_date"))[:10])
            value = _number(raw, series_id)
        except (ValueError, EnergyChannelError):
            continue
        if observed > now.date():
            raise EnergyChannelError(f"{series_id} contains future observation {observed}")
        if value <= 0:
            raise EnergyChannelError(f"{series_id} is not positive")
        points[observed.isoformat()] = round(value, 6)
    if not points:
        raise EnergyChannelError(f"{series_id} has no usable observations")
    return [{"observed_at": key, "value": points[key]} for key in sorted(points)]


def parse_eia_series(body: bytes, *, series_id: str, now: datetime) -> list[dict[str, Any]]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EnergyChannelError("EIA petroleum response is not valid JSON") from exc
    response = payload.get("response") if isinstance(payload, dict) else None
    rows = response.get("data") if isinstance(response, dict) else None
    if not isinstance(rows, list):
        raise EnergyChannelError("EIA petroleum response has no data array")
    points: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict) or str(row.get("series")) != series_id:
            continue
        try:
            observed = date.fromisoformat(str(row.get("period"))[:10])
            value = _number(row.get("value"), series_id)
        except (ValueError, EnergyChannelError):
            continue
        if observed > now.date():
            raise EnergyChannelError(f"{series_id} contains future observation {observed}")
        if value < 0:
            raise EnergyChannelError(f"{series_id} is negative")
        points[observed.isoformat()] = round(value, 6)
    if not points:
        raise EnergyChannelError(f"{series_id} has no usable observations")
    return [{"observed_at": key, "value": points[key]} for key in sorted(points)]


def _save_raw(data_dir: Path, source_id: str, run_id: str, response: FetchResponse, url: str, suffix: str) -> None:
    digest = hashlib.sha256(response.body).hexdigest()
    base = data_dir / "raw" / source_id / f"{run_id}-{suffix}-{digest[:12]}"
    extension = ".json" if suffix.endswith("json") else ".csv"
    atomic_write_bytes(base.with_suffix(extension), response.body)
    atomic_write_json(base.with_suffix(".meta.json"), {
        "source_id": source_id,
        "url": url,
        "fetched_at": response.fetched_at,
        "http_status": response.status_code,
        "attempts": response.attempts,
        "elapsed_ms": response.elapsed_ms,
        "sha256": digest,
        "byte_count": len(response.body),
    })


def _merge(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], *, series_id: str, detected_at: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    merged = {str(item.get("observed_at")): dict(item) for item in existing if isinstance(item, dict) and item.get("observed_at")}
    revisions = []
    for item in incoming:
        key = str(item.get("observed_at") or "")
        if not key:
            continue
        previous = merged.get(key)
        if previous and isinstance(previous.get("value"), (int, float)) and not math.isclose(float(previous["value"]), float(item["value"]), rel_tol=1e-10, abs_tol=1e-8):
            revisions.append({"series_id": series_id, "observed_at": key, "old_value": previous["value"], "new_value": item["value"], "detected_at": detected_at})
        merged[key] = dict(item)
    return [merged[key] for key in sorted(merged)], revisions


def _nearest(points: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    for item in reversed(points):
        if date.fromisoformat(str(item["observed_at"])[:10]) <= target:
            return item
    return None


def _change(points: list[dict[str, Any]], days: int) -> dict[str, Any]:
    if not points:
        return {"days": days, "change": None, "percent_change": None, "prior_value": None, "prior_observed_at": None}
    latest = points[-1]
    prior = _nearest(points, date.fromisoformat(str(latest["observed_at"])[:10]) - timedelta(days=days))
    if not prior:
        return {"days": days, "change": None, "percent_change": None, "prior_value": None, "prior_observed_at": None}
    change = float(latest["value"]) - float(prior["value"])
    pct = change / abs(float(prior["value"])) * 100 if prior["value"] else None
    return {"days": days, "change": round(change, 6), "percent_change": round(pct, 4) if pct is not None else None, "prior_value": prior["value"], "prior_observed_at": prior["observed_at"]}


def _health(source: dict[str, Any], points: list[dict[str, Any]], *, now: datetime, fetched_at: str | None, network_ok: bool, error: str | None) -> dict[str, Any]:
    age = (now.date() - date.fromisoformat(points[-1]["observed_at"])).days if points else None
    limit = int(source["freshness_max_days"] if network_ok else source["cache_max_days"])
    status = "unavailable" if not points else "stale_source" if age is None or age > limit else "fresh_network" if network_ok else "fresh_cache"
    return {
        "source_id": source["id"], "series_id": source["series_key"], "name": source["name"],
        "source_owner": source["source_owner"], "authority": source["authority"], "cadence": source["cadence"],
        "url": source["documentation_url"], "quality_status": status, "available_for_analysis": status in ELIGIBLE_STATUSES,
        "observed_at": points[-1]["observed_at"] if points else None, "fetched_at": fetched_at, "age_days": age, "error": error,
    }


def _metric(source: dict[str, Any], points: list[dict[str, Any]], health: dict[str, Any]) -> dict[str, Any]:
    latest = points[-1] if points else None
    previous = points[-2] if len(points) >= 2 else None
    changes = {key: _change(points, days) for key, days in CHANGE_WINDOWS.items()}
    return {
        "metric_id": source["metric_id"], "group": "energy", "source_id": source["id"], "source_name": source["name"],
        "source_url": source["documentation_url"], "authority": source["authority"], "cadence": source["cadence"],
        "quality_status": health["quality_status"], "available_for_analysis": bool(latest) and health["quality_status"] in ELIGIBLE_STATUSES,
        "value": latest.get("value") if latest else None, "unit": source["unit"], "observed_at": latest.get("observed_at") if latest else None,
        "fetched_at": health.get("fetched_at"), "latest_change": round(float(latest["value"]) - float(previous["value"]), 6) if latest and previous else None,
        "latest_prior_value": previous.get("value") if previous else None, "latest_prior_observed_at": previous.get("observed_at") if previous else None,
        "week_change": changes["1w"]["change"], "week_prior_value": changes["1w"]["prior_value"], "week_prior_observed_at": changes["1w"]["prior_observed_at"],
        "changes": changes, "sparkline": points[-370:],
    }


def _spread(wti: list[dict[str, Any]], brent: list[dict[str, Any]]) -> list[dict[str, Any]]:
    left = {item["observed_at"]: float(item["value"]) for item in wti}
    right = {item["observed_at"]: float(item["value"]) for item in brent}
    return [{"observed_at": key, "value": round(right[key] - left[key], 6), "wti": left[key], "brent": right[key]} for key in sorted(set(left) & set(right))]


def _spread_metric(points: list[dict[str, Any]], statuses: list[str], fetched_at: str | None) -> dict[str, Any]:
    quality = "unavailable" if not points or any(status not in ELIGIBLE_STATUSES for status in statuses) else "fresh_cache" if "fresh_cache" in statuses else "fresh_network"
    source = {"metric_id": "energy_brent_wti_spread", "id": "fred_brent_wti_aligned", "name": "Brent 与 WTI 官方现货价差", "documentation_url": "https://fred.stlouisfed.org/", "authority": "official_redistributor", "cadence": "business_daily", "unit": "usd_per_barrel"}
    health = {"quality_status": quality, "fetched_at": fetched_at}
    return _metric(source, points, health)


def run_energy_channel(root: Path, config_path: Path, data_dir: Path, *, direct: bool = False, fetcher: Any | None = None, now: datetime | None = None) -> dict[str, Any]:
    current = (now or utc_now()).astimezone(UTC)
    run_id = current.strftime("%Y%m%dT%H%M%S.%fZ")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    transport = fetcher or CurlFetcher(config.get("request_policy", {}), direct=direct)
    previous_history = _load_object(data_dir / "history.json") or {"series": {}, "derived": {}, "revisions": []}
    previous_latest = _load_object(data_dir / "latest.json") or {}
    previous_health = {str(item.get("series_id")): item for item in previous_latest.get("sources", []) if isinstance(item, dict)}
    series = copy.deepcopy(previous_history.get("series", {}))
    revisions = list(previous_history.get("revisions", []))
    source_health: list[dict[str, Any]] = []
    fetched_values: list[str] = []
    start_date = (current.date() - timedelta(days=int(config.get("history_days", 1900)))).isoformat()

    for source in config.get("prices", []):
        ok = False; error = None; fetched_at = None
        try:
            url = source["url_template"].format(start_date=start_date)
            response = transport.fetch(url)
            _save_raw(data_dir, source["id"], run_id, response, url, "history")
            incoming = parse_fred_series(response.body, series_id=source["series_id"], now=current)
            series[source["series_key"]], detected = _merge(series.get(source["series_key"], []), incoming, series_id=source["series_key"], detected_at=iso_z(current))
            revisions.extend(detected); ok = True; fetched_at = response.fetched_at; fetched_values.append(response.fetched_at)
        except (FetchError, EnergyChannelError, KeyError, TypeError, ValueError) as exc:
            error = str(exc); fetched_at = previous_health.get(source["series_key"], {}).get("fetched_at")
        source_health.append(_health(source, series.get(source["series_key"], []), now=current, fetched_at=fetched_at, network_ok=ok, error=error))

    api_key = os.environ.get("EIA_API_KEY", "DEMO_KEY")
    for source in config.get("weekly", []):
        ok = False; error = None; fetched_at = None
        try:
            query = urlencode({"api_key": api_key, "frequency": "weekly", "data[0]": "value", "facets[series][]": source["series_id"], "start": start_date, "sort[0][column]": "period", "sort[0][direction]": "asc", "offset": 0, "length": 2000})
            url = f"https://api.eia.gov/v2/{source['route']}/data/?{query}"
            response = transport.fetch(url)
            safe_url = url.replace(api_key, "DEMO_KEY" if api_key == "DEMO_KEY" else "REDACTED")
            _save_raw(data_dir, source["id"], run_id, response, safe_url, "history-json")
            incoming = parse_eia_series(response.body, series_id=source["series_id"], now=current)
            series[source["series_key"]], detected = _merge(series.get(source["series_key"], []), incoming, series_id=source["series_key"], detected_at=iso_z(current))
            revisions.extend(detected); ok = True; fetched_at = response.fetched_at; fetched_values.append(response.fetched_at)
        except (FetchError, EnergyChannelError, KeyError, TypeError, ValueError) as exc:
            error = str(exc); fetched_at = previous_health.get(source["series_key"], {}).get("fetched_at")
        source_health.append(_health(source, series.get(source["series_key"], []), now=current, fetched_at=fetched_at, network_ok=ok, error=error))

    health_by_series = {item["series_id"]: item for item in source_health}
    sources = [*config.get("prices", []), *config.get("weekly", [])]
    metrics = {source["metric_id"]: _metric(source, series.get(source["series_key"], []), health_by_series[source["series_key"]]) for source in sources}
    spread = _spread(series.get("wti_spot", []), series.get("brent_spot", []))
    metrics["energy_brent_wti_spread"] = _spread_metric(spread, [health_by_series.get("wti_spot", {}).get("quality_status", "unavailable"), health_by_series.get("brent_spot", {}).get("quality_status", "unavailable")], max(fetched_values, default=None))
    warnings = [f"{item['name']}：{item['error']}" for item in source_health if item.get("error")]
    available = any(metric.get("available_for_analysis") for metric in metrics.values())
    quality = "fresh_cache" if any(metric.get("quality_status") == "fresh_cache" for metric in metrics.values()) else "fresh_network" if available else "unavailable"
    latest = {
        "schema_version": SCHEMA_VERSION, "run_id": run_id, "generated_at": iso_z(current),
        "status": "degraded" if warnings or not all(metric.get("available_for_analysis") for metric in metrics.values()) else "ready",
        "quality_status": quality, "available_for_analysis": available, "metrics": metrics, "sources": source_health,
        "curve": config.get("curve", {}),
        "quality": {"warnings": warnings, "missing_value_semantics": "null 表示不可用，永远不表示 0。", "optional_channel": True},
        "methodology": {
            "role": "油价是外部通胀和金融条件因子，不进入美联储总资产减 TGA 减 RRP 的流动性参考值。",
            "frequency": "WTI 和 Brent 为工作日；库存、SPR 和汽油隐含需求为每周。",
            "interpretation": "先看价格方向，再用库存和新闻区分供给冲击与需求走弱。周数据不写成当日变化。",
            "curve": config.get("curve", {}).get("note"),
        },
    }
    history = {"schema_version": SCHEMA_VERSION, "updated_at": iso_z(current), "series": series, "derived": {"brent_wti_spread": spread}, "revisions": revisions[-200:]}
    atomic_write_json(data_dir / "history.json", history)
    atomic_write_json(data_dir / "runs" / f"{run_id}.json", latest)
    atomic_write_json(data_dir / "latest.json", latest)
    if available:
        atomic_write_json(data_dir / "last-good.json", latest)
    return latest


def load_energy_payload(root: Path) -> dict[str, Any]:
    payload = _load_object(root / "data" / "energy" / "latest.json")
    if payload is not None:
        return payload
    return {"schema_version": SCHEMA_VERSION, "status": "unavailable", "quality_status": "unavailable", "available_for_analysis": False, "metrics": {}, "sources": [], "curve": {"status": "unavailable"}, "quality": {"warnings": ["油价通道尚未采集，不影响核心宏观流动性结论。"]}, "methodology": {"role": "外部通胀与金融条件因子，不进入流动性参考值。"}}


def load_energy_history(root: Path) -> dict[str, Any]:
    return _load_object(root / "data" / "energy" / "history.json") or {"series": {}, "derived": {}, "revisions": []}
