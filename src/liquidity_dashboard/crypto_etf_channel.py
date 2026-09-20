from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import subprocess
from datetime import date, datetime, timezone
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
NEW_YORK = ZoneInfo("America/New_York")
SCHEMA_VERSION = "1.0"
ELIGIBLE_STATUSES = {"fresh_network", "fresh_cache"}


class CryptoEtfChannelError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_date(value: Any) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise CryptoEtfChannelError(f"invalid ETF trading date: {value!r}") from exc


def _resolve_api_key(
    config: dict[str, Any], *, environ: dict[str, str] | None = None
) -> str | None:
    credential = config.get("credential") if isinstance(config.get("credential"), dict) else {}
    environment = environ if environ is not None else os.environ
    env_name = str(credential.get("env_var") or "SOSOVALUE_API_KEY")
    candidate = str(environment.get(env_name) or "").strip()
    if candidate:
        return candidate
    service = str(credential.get("keychain_service") or "").strip()
    if not service:
        return None
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", service, "-w"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def _unwrap_response(body: bytes, symbol: str, *, as_of: date) -> list[dict[str, Any]]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CryptoEtfChannelError(f"{symbol} ETF response is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("code") not in (0, "0"):
        message = payload.get("message") if isinstance(payload, dict) else None
        raise CryptoEtfChannelError(f"{symbol} ETF API failed: {message or 'invalid response'}")
    raw_rows = payload.get("data")
    if not isinstance(raw_rows, list):
        raise CryptoEtfChannelError(f"{symbol} ETF response is missing data rows")
    rows: dict[str, dict[str, Any]] = {}
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        observed = _parse_date(raw.get("date"))
        if observed > as_of:
            raise CryptoEtfChannelError(
                f"{symbol} ETF response contains future trading date {observed.isoformat()}"
            )
        row = {
            "date": observed.isoformat(),
            "total_net_inflow": _finite_number(raw.get("total_net_inflow")),
            "total_value_traded": _finite_number(raw.get("total_value_traded")),
            "total_net_assets": _finite_number(raw.get("total_net_assets")),
            "cum_net_inflow": _finite_number(raw.get("cum_net_inflow")),
        }
        previous = rows.get(row["date"])
        if previous is not None and previous != row:
            raise CryptoEtfChannelError(
                f"{symbol} ETF response contains conflicting row for {row['date']}"
            )
        rows[row["date"]] = row
    if not rows:
        raise CryptoEtfChannelError(f"{symbol} ETF response contains no usable rows")
    return [rows[key] for key in sorted(rows)]


def _save_raw(
    data_dir: Path,
    symbol: str,
    run_id: str,
    response: FetchResponse,
    url: str,
) -> str:
    digest = hashlib.sha256(response.body).hexdigest()
    raw_path = data_dir / "raw" / symbol.lower() / f"{run_id}-{digest[:12]}.json"
    atomic_write_bytes(raw_path, response.body)
    atomic_write_json(
        raw_path.with_suffix(".json.meta.json"),
        {
            "source_id": "sosovalue_us_crypto_etf",
            "asset": symbol,
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


def _numbers_equal(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(float(left), float(right), rel_tol=1e-10, abs_tol=0.01)


def _merge_history(
    previous: dict[str, Any] | None,
    incoming: dict[str, list[dict[str, Any]]],
    *,
    updated_at: str,
) -> dict[str, Any]:
    history = copy.deepcopy(previous) if isinstance(previous, dict) else {}
    assets = history.get("assets") if isinstance(history.get("assets"), dict) else {}
    revisions = history.get("revisions") if isinstance(history.get("revisions"), list) else []
    for symbol, rows in incoming.items():
        by_date = {
            str(item.get("date")): item
            for item in assets.get(symbol, [])
            if isinstance(item, dict) and item.get("date")
        }
        for row in rows:
            if row.get("total_net_inflow") is None:
                continue
            key = row["date"]
            old = by_date.get(key)
            if old is not None and any(
                not _numbers_equal(old.get(field), row.get(field))
                for field in (
                    "total_net_inflow",
                    "total_value_traded",
                    "total_net_assets",
                    "cum_net_inflow",
                )
            ):
                revisions.append(
                    {
                        "asset": symbol,
                        "date": key,
                        "detected_at": updated_at,
                        "old": old,
                        "new": row,
                    }
                )
            by_date[key] = row
        assets[symbol] = [by_date[key] for key in sorted(by_date)]
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": updated_at,
        "assets": assets,
        "revisions": revisions[-500:],
    }


def _usd_millions(value: float | None) -> float | None:
    return round(value / 1_000_000, 4) if value is not None else None


def _metric(
    metric_id: str,
    value: float | None,
    observed_at: str | None,
    fetched_at: str | None,
    source: dict[str, Any],
    quality_status: str,
    *,
    unit: str = "usd_millions",
    sparkline: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "group": "crypto_etf",
        "source_id": source["id"],
        "source_name": source["name"],
        "source_url": source["documentation_url"],
        "authority": source["authority"],
        "cadence": source["cadence"],
        "quality_status": quality_status,
        "available_for_analysis": value is not None and quality_status in ELIGIBLE_STATUSES,
        "value": round(value, 4) if value is not None else None,
        "unit": unit,
        "observed_at": observed_at,
        "age_days": None,
        "fetched_at": fetched_at,
        "latest_change": None,
        "changes": {},
        "sparkline": sparkline or [],
        "metadata": metadata or {},
    }


def _streak(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"direction": "none", "sessions": 0}
    latest_value = float(rows[-1]["total_net_inflow"])
    direction = "inflow" if latest_value > 0 else "outflow" if latest_value < 0 else "flat"
    sessions = 0
    for row in reversed(rows):
        value = float(row["total_net_inflow"])
        current = "inflow" if value > 0 else "outflow" if value < 0 else "flat"
        if current != direction:
            break
        sessions += 1
    return {"direction": direction, "sessions": sessions}


def _asset_payload(
    symbol: str,
    label: str,
    settled_rows: list[dict[str, Any]],
    latest_response_rows: list[dict[str, Any]] | None,
    *,
    source: dict[str, Any],
    now: datetime,
    fetched_at: str | None,
    fetch_error: str | None,
) -> dict[str, Any]:
    as_of = now.astimezone(NEW_YORK).date()
    latest = settled_rows[-1] if settled_rows else None
    latest_date = _parse_date(latest["date"]) if latest else None
    age_days = (as_of - latest_date).days if latest_date else None
    fresh_limit = int(source["freshness_max_calendar_days"])
    cache_limit = int(source["cache_max_calendar_days"])
    if latest is None or age_days is None or age_days > cache_limit:
        quality_status = "unavailable"
    elif fetch_error is None and age_days <= fresh_limit:
        quality_status = "fresh_network"
    elif age_days <= cache_limit:
        quality_status = "fresh_cache"
    else:
        quality_status = "unavailable"
    response_latest = latest_response_rows[-1] if latest_response_rows else None
    pending_date = None
    if (
        response_latest
        and response_latest.get("total_net_inflow") is None
        and (latest is None or response_latest["date"] > latest["date"])
    ):
        pending_date = response_latest["date"]
    recent_5 = settled_rows[-5:]
    recent_20 = settled_rows[-20:]
    rolling_5 = sum(float(row["total_net_inflow"]) for row in recent_5) if recent_5 else None
    rolling_20 = sum(float(row["total_net_inflow"]) for row in recent_20) if recent_20 else None
    prefix = f"etf_{symbol.lower()}"
    observed_at = latest["date"] if latest else None
    flow_points = [
        {"observed_at": row["date"], "value": _usd_millions(row["total_net_inflow"])}
        for row in settled_rows
    ]
    metrics = {
        f"{prefix}_net_flow_latest": _metric(
            f"{prefix}_net_flow_latest",
            _usd_millions(latest.get("total_net_inflow")) if latest else None,
            observed_at,
            fetched_at,
            source,
            quality_status,
            sparkline=flow_points,
            metadata={"asset": symbol, "window": "latest_settled_session"},
        ),
        f"{prefix}_net_flow_5d": _metric(
            f"{prefix}_net_flow_5d",
            _usd_millions(rolling_5),
            observed_at,
            fetched_at,
            source,
            quality_status,
            metadata={"asset": symbol, "window": "last_5_settled_sessions"},
        ),
        f"{prefix}_net_flow_20d": _metric(
            f"{prefix}_net_flow_20d",
            _usd_millions(rolling_20),
            observed_at,
            fetched_at,
            source,
            quality_status,
            metadata={"asset": symbol, "window": "last_20_settled_sessions"},
        ),
        f"{prefix}_aum": _metric(
            f"{prefix}_aum",
            _usd_millions(latest.get("total_net_assets")) if latest else None,
            observed_at,
            fetched_at,
            source,
            quality_status,
            metadata={"asset": symbol},
        ),
        f"{prefix}_value_traded": _metric(
            f"{prefix}_value_traded",
            _usd_millions(latest.get("total_value_traded")) if latest else None,
            observed_at,
            fetched_at,
            source,
            quality_status,
            metadata={"asset": symbol},
        ),
    }
    for metric in metrics.values():
        metric["age_days"] = age_days
    return {
        "symbol": symbol,
        "label": label,
        "status": "settlement_pending" if pending_date else "settled",
        "quality_status": quality_status,
        "available_for_analysis": quality_status in ELIGIBLE_STATUSES and latest is not None,
        "observed_at": observed_at,
        "pending_date": pending_date,
        "age_days": age_days,
        "fetch_error": fetch_error,
        "latest": {
            key: (_usd_millions(value) if key != "date" else value)
            for key, value in (latest or {}).items()
        }
        if latest
        else None,
        "rolling": {
            "5_sessions_usd_millions": _usd_millions(rolling_5),
            "20_sessions_usd_millions": _usd_millions(rolling_20),
        },
        "streak": _streak(settled_rows),
        "history": flow_points,
        "metrics": metrics,
    }


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
        "credential_status": "missing",
        "source": {
            "source_id": source["id"],
            "name": source["name"],
            "source_owner": source["source_owner"],
            "authority": source["authority"],
            "cadence": source["cadence"],
            "url": source["documentation_url"],
            "fetched_at": None,
            "error": error,
        },
        "assets": {},
        "metrics": {},
        "quality": {
            "warnings": ["ETF 数据暂不可用，不影响宏观数据和其他加密指标更新。"],
            "missing_value_semantics": "null 表示尚未结算或不可用，永远不表示 0。",
        },
        "cross_checks": config.get("cross_checks", []),
        "methodology": {
            "role": "ETF 只观察受监管现货通道的实际申购赎回，不进入宏观流动性公式。",
            "settlement": "只使用 net_inflow 已经结算的交易日；当天空值不会被当成零。",
        },
    }


def run_crypto_etf_channel(
    config_path: Path,
    data_dir: Path,
    *,
    direct: bool = False,
    fetcher: Any | None = None,
    api_key: str | None = None,
    now: datetime | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)
    run_id = current.strftime("%Y%m%dT%H%M%S.%fZ")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("source"), dict):
        raise CryptoEtfChannelError("ETF source configuration is invalid")
    source = config["source"]
    key = api_key or _resolve_api_key(config, environ=environ)
    if not key:
        payload = _unavailable_payload(
            config,
            now=current,
            run_id=run_id,
            error="SoSoValue API Key 尚未配置",
        )
        atomic_write_json(data_dir / "runs" / f"{run_id}.json", payload)
        atomic_write_json(data_dir / "latest.json", payload)
        return payload

    transport = fetcher or CurlFetcher(config.get("request_policy", {}), direct=direct)
    as_of = current.astimezone(NEW_YORK).date()
    incoming: dict[str, list[dict[str, Any]]] = {}
    response_rows: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    fetched_times: list[str] = []
    for asset in source.get("assets", []):
        symbol = str(asset.get("symbol") or "").upper()
        if not symbol:
            continue
        query = urlencode(
            {
                "symbol": symbol,
                "country_code": source["country_code"],
                "limit": int(source["request_limit"]),
            }
        )
        url = f"{source['base_url']}{source['summary_history_path']}?{query}"
        try:
            response = transport.fetch(url, headers={"x-soso-api-key": key})
            rows = _unwrap_response(response.body, symbol, as_of=as_of)
            _save_raw(data_dir, symbol, run_id, response, url)
            incoming[symbol] = rows
            response_rows[symbol] = rows
            fetched_times.append(response.fetched_at)
        except (FetchError, CryptoEtfChannelError, KeyError, TypeError, ValueError) as exc:
            errors[symbol] = str(exc)

    generated_at = iso_z(current)
    history_path = data_dir / "history.json"
    history = _merge_history(_load_object(history_path), incoming, updated_at=generated_at)
    atomic_write_json(history_path, history)
    assets_payload: dict[str, dict[str, Any]] = {}
    metrics: dict[str, dict[str, Any]] = {}
    labels = {
        str(item.get("symbol") or "").upper(): str(item.get("label") or item.get("symbol") or "")
        for item in source.get("assets", [])
        if isinstance(item, dict)
    }
    for symbol, label in labels.items():
        asset_payload = _asset_payload(
            symbol,
            label,
            [
                row
                for row in history.get("assets", {}).get(symbol, [])
                if isinstance(row, dict) and row.get("total_net_inflow") is not None
            ],
            response_rows.get(symbol),
            source=source,
            now=current,
            fetched_at=max(fetched_times) if fetched_times else None,
            fetch_error=errors.get(symbol),
        )
        assets_payload[symbol] = asset_payload
        metrics.update(asset_payload["metrics"])
    available_assets = [
        item for item in assets_payload.values() if item.get("available_for_analysis")
    ]
    pending_assets = [item["symbol"] for item in assets_payload.values() if item.get("pending_date")]
    quality_status = (
        "fresh_network"
        if len(available_assets) == len(assets_payload) and not errors
        else "fresh_cache"
        if available_assets
        else "unavailable"
    )
    status = "ready" if quality_status == "fresh_network" else "degraded" if available_assets else "unavailable"
    warnings = [f"{symbol}：{message}" for symbol, message in sorted(errors.items())]
    if pending_assets:
        warnings.append(
            f"{', '.join(pending_assets)} 最新交易日仍在结算，页面继续使用各自最近一个已结算交易日。"
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at,
        "status": status,
        "quality_status": quality_status,
        "available_for_analysis": bool(available_assets),
        "credential_status": "configured",
        "source": {
            "source_id": source["id"],
            "name": source["name"],
            "source_owner": source["source_owner"],
            "authority": source["authority"],
            "cadence": source["cadence"],
            "url": source["documentation_url"],
            "fetched_at": max(fetched_times) if fetched_times else None,
            "error": "; ".join(warnings) if warnings else None,
        },
        "assets": assets_payload,
        "metrics": metrics,
        "quality": {
            "warnings": warnings,
            "available_asset_count": len(available_assets),
            "expected_asset_count": len(assets_payload),
            "revision_count": len(history.get("revisions", [])),
            "missing_value_semantics": "null 表示尚未结算或不可用，永远不表示 0。",
        },
        "cross_checks": config.get("cross_checks", []),
        "methodology": {
            "role": "ETF 只观察受监管现货通道的实际申购赎回，不进入宏观流动性公式。",
            "settlement": "只使用 net_inflow 已经结算的交易日；当天空值不会被当成零。",
            "history": "接口只返回最近约一个月；看板每天落库，自行积累长期历史。",
            "cross_check": "Farside 仅作人工抽查，不参与自动发布门禁。",
        },
    }
    if available_assets:
        atomic_write_json(data_dir / "last-good.json", payload)
    atomic_write_json(data_dir / "runs" / f"{run_id}.json", payload)
    atomic_write_json(data_dir / "latest.json", payload)
    return payload


def load_crypto_etf_payload(root: Path) -> dict[str, Any]:
    payload = _load_object(root / "data" / "crypto" / "etf" / "latest.json")
    if payload is not None:
        return payload
    config_path = root / "config" / "crypto-etf-sources.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        return _unavailable_payload(
            config,
            now=utc_now(),
            run_id="not-run",
            error="尚未运行 ETF 数据通道",
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "quality_status": "unavailable",
        "available_for_analysis": False,
        "assets": {},
        "metrics": {},
        "quality": {"warnings": ["ETF 数据通道尚未配置。"]},
    }
