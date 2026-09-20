from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
import math
import re
import sqlite3
import zipfile
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin

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


class YenCarryChannelError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _number(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise YenCarryChannelError(f"{label} is missing")
    try:
        parsed = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise YenCarryChannelError(f"{label} is not numeric") from exc
    if not math.isfinite(parsed):
        raise YenCarryChannelError(f"{label} is not finite")
    return parsed


def _parse_date(value: Any, label: str) -> date:
    text = str(value or "").strip()
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date()
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise YenCarryChannelError(f"{label} has invalid date {text!r}") from exc


def parse_ecb_usd_jpy(body: bytes, *, now: datetime) -> list[dict[str, Any]]:
    try:
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    except UnicodeDecodeError as exc:
        raise YenCarryChannelError("ECB FX response is not UTF-8 CSV") from exc
    required = {"CURRENCY", "TIME_PERIOD", "OBS_VALUE"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise YenCarryChannelError("ECB FX CSV is missing required columns")
    legs: dict[str, dict[str, float]] = {"USD": {}, "JPY": {}}
    for row in reader:
        currency = str(row.get("CURRENCY") or "").upper()
        if currency not in legs:
            continue
        raw = row.get("OBS_VALUE")
        if raw in (None, "", "."):
            continue
        observed = _parse_date(row.get("TIME_PERIOD"), "ECB FX")
        if observed > now.date():
            raise YenCarryChannelError(
                f"ECB FX contains future observation {observed.isoformat()}"
            )
        value = _number(raw, f"ECB {currency}/EUR")
        if value <= 0:
            raise YenCarryChannelError(f"ECB {currency}/EUR is not positive")
        legs[currency][observed.isoformat()] = value
    points = []
    for observed_at in sorted(set(legs["USD"]) & set(legs["JPY"])):
        usd = legs["USD"][observed_at]
        jpy = legs["JPY"][observed_at]
        points.append(
            {
                "observed_at": observed_at,
                "value": round(jpy / usd, 6),
                "jpy_per_eur": round(jpy, 6),
                "usd_per_eur": round(usd, 6),
            }
        )
    if not points:
        raise YenCarryChannelError("ECB FX CSV has no aligned USD and JPY rows")
    return points


def parse_boj_series(
    body: bytes,
    *,
    expected_codes: set[str],
    now: datetime,
) -> dict[str, list[dict[str, Any]]]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise YenCarryChannelError("BOJ response is not valid JSON") from exc
    if str(payload.get("STATUS")) != "200":
        raise YenCarryChannelError(
            f"BOJ API returned {payload.get('STATUS')}: {payload.get('MESSAGE')}"
        )
    resultset = payload.get("RESULTSET")
    if not isinstance(resultset, list):
        raise YenCarryChannelError("BOJ response is missing RESULTSET")
    result: dict[str, list[dict[str, Any]]] = {}
    for item in resultset:
        if not isinstance(item, dict):
            continue
        code = str(item.get("SERIES_CODE") or "")
        if code not in expected_codes:
            continue
        values = item.get("VALUES")
        dates = values.get("SURVEY_DATES") if isinstance(values, dict) else None
        observations = values.get("VALUES") if isinstance(values, dict) else None
        if not isinstance(dates, list) or not isinstance(observations, list):
            raise YenCarryChannelError(f"BOJ {code} is missing dates or values")
        if len(dates) != len(observations):
            raise YenCarryChannelError(f"BOJ {code} date/value lengths do not match")
        points = []
        for raw_date, raw_value in zip(dates, observations):
            if raw_value is None:
                continue
            observed = _parse_date(raw_date, f"BOJ {code}")
            if observed > now.date():
                raise YenCarryChannelError(
                    f"BOJ {code} contains future value {observed.isoformat()}"
                )
            points.append(
                {
                    "observed_at": observed.isoformat(),
                    "value": round(_number(raw_value, f"BOJ {code}"), 8),
                }
            )
        if not points:
            raise YenCarryChannelError(f"BOJ {code} has no usable observations")
        result[code] = points
    missing = expected_codes - set(result)
    if missing:
        raise YenCarryChannelError(f"BOJ response is missing codes {sorted(missing)}")
    return result


def parse_cftc_jpy_zip(
    body: bytes,
    *,
    contract_code: str,
    now: datetime,
) -> list[dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
        names = [name for name in archive.namelist() if name.lower().endswith(".txt")]
        if len(names) != 1:
            raise YenCarryChannelError("CFTC archive does not contain one text report")
        text = archive.read(names[0]).decode("utf-8-sig")
    except (zipfile.BadZipFile, UnicodeDecodeError, KeyError) as exc:
        raise YenCarryChannelError("CFTC response is not a valid report archive") from exc
    reader = csv.DictReader(io.StringIO(text))
    required = {
        "Report_Date_as_YYYY-MM-DD",
        "CFTC_Contract_Market_Code",
        "Lev_Money_Positions_Long_All",
        "Lev_Money_Positions_Short_All",
    }
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise YenCarryChannelError("CFTC report is missing leveraged-money columns")
    points: dict[str, dict[str, Any]] = {}
    for row in reader:
        if str(row.get("CFTC_Contract_Market_Code") or "").strip() != contract_code:
            continue
        observed = _parse_date(row.get("Report_Date_as_YYYY-MM-DD"), "CFTC JPY")
        if observed > now.date():
            raise YenCarryChannelError(
                f"CFTC JPY contains future observation {observed.isoformat()}"
            )
        long_positions = _number(
            row.get("Lev_Money_Positions_Long_All"), "CFTC leveraged long"
        )
        short_positions = _number(
            row.get("Lev_Money_Positions_Short_All"), "CFTC leveraged short"
        )
        points[observed.isoformat()] = {
            "observed_at": observed.isoformat(),
            "value": round(short_positions - long_positions, 2),
            "long_contracts": round(long_positions, 2),
            "short_contracts": round(short_positions, 2),
        }
    if not points:
        raise YenCarryChannelError("CFTC report has no Japanese yen contract rows")
    return [points[key] for key in sorted(points)]


def parse_jsda_archive(body: bytes, *, now: datetime) -> tuple[str, date]:
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise YenCarryChannelError("JSDA archive page is not UTF-8") from exc
    candidates = []
    for match in re.finditer(r'href=["\']([^"\']*ES(\d{6})\.csv)["\']', text, re.I):
        publication_date = datetime.strptime(match.group(2), "%y%m%d").date()
        if publication_date <= now.date():
            candidates.append((publication_date, match.group(1)))
    if not candidates:
        raise YenCarryChannelError("JSDA archive page has no eligible daily CSV")
    publication_date, relative_url = max(candidates)
    return relative_url, publication_date


def parse_jsda_jgb_2y(
    body: bytes,
    *,
    publication_date: date,
    minimum_remaining_days: int = 550,
    maximum_remaining_days: int = 910,
) -> dict[str, Any]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = body.decode("cp932")
        except UnicodeDecodeError as exc:
            raise YenCarryChannelError("JSDA bond CSV has an unsupported encoding") from exc
    rows = csv.reader(io.StringIO(text))
    target_days = 730
    candidates = []
    for row in rows:
        if len(row) < 7 or not re.fullmatch(r"JGB\d+\(2\)", str(row[3]).strip()):
            continue
        maturity = _parse_date(row[4], "JSDA maturity")
        remaining_days = (maturity - publication_date).days
        if not minimum_remaining_days <= remaining_days <= maximum_remaining_days:
            continue
        yield_value = _number(row[6], "JSDA average compound yield")
        if yield_value >= 999:
            continue
        candidates.append((abs(remaining_days - target_days), -maturity.toordinal(), row, maturity, remaining_days, yield_value))
    if not candidates:
        raise YenCarryChannelError("JSDA CSV has no usable JGB issue near two years")
    _, _, row, maturity, remaining_days, yield_value = min(candidates)
    return {
        "observed_at": publication_date.isoformat(),
        "value": round(yield_value, 6),
        "issue": str(row[3]).strip(),
        "maturity_date": maturity.isoformat(),
        "remaining_days": remaining_days,
        "date_semantics": "JSDA publication date; quotations are from 15:00 on the prior business day",
    }


def realized_volatility(
    points: list[dict[str, Any]], *, window: int = 20
) -> list[dict[str, Any]]:
    usable = [
        item
        for item in points
        if item.get("observed_at") and isinstance(item.get("value"), (int, float))
    ]
    result = []
    for index in range(window, len(usable)):
        sample = usable[index - window : index + 1]
        returns = [
            math.log(float(current["value"]) / float(previous["value"]))
            for previous, current in zip(sample, sample[1:])
            if float(previous["value"]) > 0 and float(current["value"]) > 0
        ]
        if len(returns) != window:
            continue
        mean = sum(returns) / len(returns)
        variance = sum((value - mean) ** 2 for value in returns) / max(1, len(returns) - 1)
        result.append(
            {
                "observed_at": usable[index]["observed_at"],
                "value": round(math.sqrt(variance) * math.sqrt(252) * 100, 6),
            }
        )
    return result


def _nearest_on_or_before(
    points: list[dict[str, Any]], target: date, *, max_days: int | None = None
) -> dict[str, Any] | None:
    for item in reversed(points):
        observed = _parse_date(item.get("observed_at"), "series")
        if observed <= target:
            if max_days is not None and (target - observed).days > max_days:
                return None
            return item
    return None


def align_spread(
    first: list[dict[str, Any]],
    second: list[dict[str, Any]],
    *,
    first_key: str,
    second_key: str,
    max_lag_days: int = 4,
) -> list[dict[str, Any]]:
    result = []
    for left in first:
        observed = _parse_date(left.get("observed_at"), first_key)
        right = _nearest_on_or_before(second, observed, max_days=max_lag_days)
        if right is None:
            continue
        left_value = float(left["value"])
        right_value = float(right["value"])
        result.append(
            {
                "observed_at": observed.isoformat(),
                "value": round(left_value - right_value, 6),
                first_key: left_value,
                second_key: right_value,
                "component_dates": {
                    first_key: observed.isoformat(),
                    second_key: right["observed_at"],
                },
            }
        )
    return result


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
    revisions = []
    for item in incoming:
        key = str(item.get("observed_at") or "")
        if not key:
            continue
        previous = merged.get(key)
        if (
            previous
            and isinstance(previous.get("value"), (int, float))
            and isinstance(item.get("value"), (int, float))
            and not math.isclose(float(previous["value"]), float(item["value"]), rel_tol=1e-10, abs_tol=1e-8)
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
    extension = ".zip" if suffix.endswith("zip") else ".json" if suffix.endswith("json") else ".csv" if suffix.endswith("csv") else ".html"
    atomic_write_bytes(Path(f"{raw_path}{extension}"), response.body)
    atomic_write_json(
        Path(f"{raw_path}.meta.json"),
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


def _load_main_series(root: Path, metric_id: str) -> list[dict[str, Any]]:
    database = root / "data" / "channel.sqlite3"
    if not database.is_file():
        return []
    with closing(sqlite3.connect(f"file:{database}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        source = connection.execute(
            "SELECT source_id FROM observations WHERE metric_id = ? ORDER BY observed_at DESC LIMIT 1",
            (metric_id,),
        ).fetchone()
        if source is None:
            return []
        rows = connection.execute(
            "SELECT observed_at, value FROM observations WHERE metric_id = ? AND source_id = ? ORDER BY observed_at ASC",
            (metric_id, source["source_id"]),
        ).fetchall()
    return [
        {"observed_at": row["observed_at"], "value": round(float(row["value"]), 8)}
        for row in rows
    ]


def _main_metric_quality(
    root: Path,
    metric_id: str,
    points: list[dict[str, Any]],
    *,
    now: datetime,
    fallback_max_age_days: int = 8,
) -> str:
    """Honor the formal snapshot gate for U.S. rate components.

    The database intentionally retains history even when today's source fails.
    A derived yen-carry spread must therefore not turn that retained history back
    into an apparently current observation. Tests and standalone fixtures without
    a formal snapshot fall back to an explicit age check.
    """
    snapshot = _load_object(root / "data" / "snapshots" / "latest.json") or {}
    metric = (snapshot.get("metrics") or {}).get(metric_id)
    if isinstance(metric, dict):
        quality = str(metric.get("quality_status") or "unavailable")
        if metric.get("available_for_analysis") is True and quality in ELIGIBLE_STATUSES:
            return quality
        return "unavailable"
    age_days = _age_days(points, now)
    return (
        "fresh_cache"
        if age_days is not None and age_days <= fallback_max_age_days
        else "unavailable"
    )


def _load_cross_asset_series(root: Path) -> dict[str, list[dict[str, Any]]]:
    payload = _load_object(root / "data" / "cross-asset" / "history.json") or {}
    series = payload.get("series")
    return series if isinstance(series, dict) else {}


def _age_days(points: list[dict[str, Any]], now: datetime) -> int | None:
    if not points:
        return None
    return max(0, (now.date() - _parse_date(points[-1]["observed_at"], "series")).days)


def _source_health(
    source: dict[str, Any],
    points: list[dict[str, Any]],
    *,
    now: datetime,
    fetched_at: str | None,
    network_ok: bool,
    error: str | None,
) -> dict[str, Any]:
    age_days = _age_days(points, now)
    limit = int(source["freshness_max_days"] if network_ok else source["cache_max_days"])
    if not points or age_days is None or age_days > limit:
        quality = "unavailable" if not points else "stale_source"
    else:
        quality = "fresh_network" if network_ok else "fresh_cache"
    return {
        "source_id": source["id"],
        "series_id": source["series_id"],
        "name": source["name"],
        "source_owner": source["source_owner"],
        "authority": source["authority"],
        "cadence": source["cadence"],
        "url": source.get("documentation_url"),
        "quality_status": quality,
        "available_for_analysis": quality in ELIGIBLE_STATUSES,
        "observed_at": points[-1]["observed_at"] if points else None,
        "fetched_at": fetched_at,
        "age_days": age_days,
        "error": error,
    }


def _change(points: list[dict[str, Any]], days: int) -> dict[str, Any]:
    if not points:
        return {"days": days, "change": None, "percent_change": None, "prior_value": None, "prior_observed_at": None}
    latest = points[-1]
    target = _parse_date(latest["observed_at"], "series") - timedelta(days=days)
    prior = _nearest_on_or_before(points, target)
    if prior is None:
        return {"days": days, "change": None, "percent_change": None, "prior_value": None, "prior_observed_at": None}
    change = float(latest["value"]) - float(prior["value"])
    percent = change / abs(float(prior["value"])) * 100 if float(prior["value"]) else None
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
    cadence: str,
    quality_status: str,
    fetched_at: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    latest = points[-1] if points else None
    previous = points[-2] if len(points) > 1 else None
    changes = {key: _change(points, days) for key, days in CHANGE_WINDOWS.items()}
    return {
        "metric_id": metric_id,
        "group": "yen_carry",
        "source_id": source_id,
        "source_name": source_name,
        "source_url": source_url,
        "authority": "mixed_official_and_trusted_sro",
        "cadence": cadence,
        "quality_status": quality_status,
        "available_for_analysis": bool(latest) and quality_status in ELIGIBLE_STATUSES,
        "value": round(float(latest["value"]), 8) if latest else None,
        "unit": unit,
        "observed_at": latest.get("observed_at") if latest else None,
        "fetched_at": fetched_at,
        "latest_change": round(float(latest["value"]) - float(previous["value"]), 8) if latest and previous else None,
        "latest_prior_value": previous.get("value") if previous else None,
        "latest_prior_observed_at": previous.get("observed_at") if previous else None,
        "week_change": changes["1w"]["change"],
        "week_prior_value": changes["1w"]["prior_value"],
        "week_prior_observed_at": changes["1w"]["prior_observed_at"],
        "changes": changes,
        "sparkline": points[-370:],
        "metadata": metadata or {},
    }


def _percentile(values: list[float], current: float | None) -> float | None:
    if current is None or len(values) < 20:
        return None
    usable = sorted(value for value in values if math.isfinite(value))
    if len(usable) < 20:
        return None
    below_or_equal = sum(value <= current for value in usable)
    return round(below_or_equal / len(usable) * 100, 1)


def _rolling_change_values(
    points: list[dict[str, Any]], days: int, *, invert: bool = False
) -> list[dict[str, Any]]:
    result = []
    for index, point in enumerate(points):
        prior = _nearest_on_or_before(points[: index + 1], _parse_date(point["observed_at"], "series") - timedelta(days=days))
        if prior is None or not float(prior["value"]):
            continue
        change = (float(point["value"]) / float(prior["value"]) - 1) * 100
        result.append({"observed_at": point["observed_at"], "value": round(-change if invert else change, 6)})
    return result


def _rolling_absolute_reduction(points: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    result = []
    for index, point in enumerate(points):
        prior = _nearest_on_or_before(points[: index + 1], _parse_date(point["observed_at"], "series") - timedelta(days=days))
        if prior is None:
            continue
        result.append({"observed_at": point["observed_at"], "value": round(float(prior["value"]) - float(point["value"]), 6)})
    return result


def _risk_sync(
    usd_jpy: list[dict[str, Any]], cross_asset: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    fx = {item["observed_at"]: float(item["value"]) for item in usd_jpy}
    btc = {item["observed_at"]: float(item["value"]) for item in cross_asset.get("btc_usd", [])}
    spx = {item["observed_at"]: float(item["value"]) for item in cross_asset.get("sp500", [])}
    return [
        {
            "observed_at": observed_at,
            "usd_jpy": fx[observed_at],
            "jpy_strength": round(1 / fx[observed_at], 10),
            "btc_usd": btc[observed_at],
            "sp500": spx[observed_at],
        }
        for observed_at in sorted(set(fx) & set(btc) & set(spx))
        if fx[observed_at] > 0 and btc[observed_at] > 0 and spx[observed_at] > 0
    ]


def _combined_quality(health_by_series: dict[str, dict[str, Any]], *series_ids: str) -> str:
    statuses = [health_by_series.get(series_id, {}).get("quality_status", "unavailable") for series_id in series_ids]
    if any(status not in ELIGIBLE_STATUSES for status in statuses):
        return "unavailable"
    return "fresh_cache" if "fresh_cache" in statuses else "fresh_network"


def build_yen_carry_payload(
    root: Path,
    history: dict[str, Any],
    config: dict[str, Any],
    source_health: list[dict[str, Any]],
    *,
    now: datetime,
    run_id: str,
    fetched_at: str | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    series = history.get("series", {})
    usd_jpy = series.get("usd_jpy", [])
    call_rate = series.get("boj_call_rate", [])
    cftc = series.get("cftc_leveraged_net_short", [])
    jgb_2y = series.get("jgb_2y_proxy", [])
    swap_turnover = series.get("fx_swap_turnover", [])
    ust_3m = _load_main_series(root, "treasury_3m_yield")
    ust_2y = _load_main_series(root, "treasury_2y_yield")
    short_spread = align_spread(ust_3m, call_rate, first_key="ust_3m", second_key="boj_call_rate")
    spread_2y = align_spread(ust_2y, jgb_2y, first_key="ust_2y", second_key="jgb_2y_proxy", max_lag_days=3)
    volatility = realized_volatility(usd_jpy, window=20)
    carry_to_risk = []
    for point in short_spread:
        observed = _parse_date(point["observed_at"], "short spread")
        vol = _nearest_on_or_before(volatility, observed, max_days=4)
        if vol and float(vol["value"]) > 0:
            carry_to_risk.append(
                {
                    "observed_at": point["observed_at"],
                    "value": round(float(point["value"]) / float(vol["value"]), 8),
                    "rate_spread": point["value"],
                    "realized_volatility": vol["value"],
                }
            )
    jpy_appreciation = _rolling_change_values(usd_jpy, 5, invert=True)
    spread_compression = _rolling_absolute_reduction(short_spread, 20)
    cftc_covering = _rolling_absolute_reduction(cftc, 28)
    risk_sync = _risk_sync(usd_jpy, _load_cross_asset_series(root))
    health_by_series = {str(item.get("series_id")): item for item in source_health}
    fx_quality = _combined_quality(health_by_series, "usd_jpy")
    call_quality = _combined_quality(health_by_series, "boj_call_rate")
    cftc_quality = _combined_quality(health_by_series, "cftc_leveraged_net_short")
    jsda_quality = _combined_quality(health_by_series, "jgb_2y_proxy")
    swap_quality = _combined_quality(health_by_series, "fx_swap_turnover")
    ust_3m_quality = _main_metric_quality(
        root, "treasury_3m_yield", ust_3m, now=now
    )
    ust_2y_quality = _main_metric_quality(
        root, "treasury_2y_yield", ust_2y, now=now
    )
    short_quality = (
        "unavailable"
        if ust_3m_quality not in ELIGIBLE_STATUSES
        else "fresh_cache"
        if "fresh_cache" in {ust_3m_quality, call_quality}
        else call_quality
    )
    spread_2y_quality = (
        "unavailable"
        if ust_2y_quality not in ELIGIBLE_STATUSES
        else "fresh_cache"
        if "fresh_cache" in {ust_2y_quality, jsda_quality}
        else jsda_quality
    )
    metrics = {
        "yen_carry_usd_jpy": _metric(
            "yen_carry_usd_jpy", usd_jpy, unit="jpy_per_usd", source_id=config["ecb_fx"]["id"], source_name=config["ecb_fx"]["name"], source_url=config["ecb_fx"]["documentation_url"], cadence="business_daily", quality_status=fx_quality, fetched_at=fetched_at,
            metadata={"direction": "USD/JPY 下跌表示日元升值；日元快速升值会增加套息平仓压力。"},
        ),
        "yen_carry_jpy_appreciation_5d": _metric(
            "yen_carry_jpy_appreciation_5d", jpy_appreciation, unit="percent", source_id=config["ecb_fx"]["id"], source_name="ECB USD/JPY 确定性计算", source_url=config["ecb_fx"]["documentation_url"], cadence="business_daily", quality_status=fx_quality, fetched_at=fetched_at,
            metadata={"formula": "-(USD/JPY 当前值 ÷ 5日前值 - 1) × 100；正数表示日元升值。"},
        ),
        "yen_carry_short_rate_spread": _metric(
            "yen_carry_short_rate_spread", short_spread, unit="percentage_points", source_id="ust_3m_and_boj_call_rate", source_name="美国 3M 国债与日本隔夜利率", source_url=config["boj"]["documentation_url"], cadence="business_daily", quality_status=short_quality, fetched_at=fetched_at,
            metadata={"formula": "美国 3M 国债收益率 - 日本无担保隔夜拆借利率", "role": "未对冲美元资产相对日元融资成本的简化代理。"},
        ),
        "yen_carry_2y_rate_spread": _metric(
            "yen_carry_2y_rate_spread", spread_2y, unit="percentage_points", source_id="ust_2y_and_jsda_jgb_2y", source_name="美国 2Y 国债与 JSDA 日本 2年券代理", source_url=config["jsda"]["documentation_url"], cadence="business_daily", quality_status=spread_2y_quality, fetched_at=fetched_at,
            metadata={"formula": "美国 2Y 国债收益率 - 剩余期限约两年的日本国债收益率", "caveat": "日本端不是恒定期限指数，且 JSDA 日期是发布日，报价来自前一工作日 15:00。"},
        ),
        "yen_carry_realized_volatility_20d": _metric(
            "yen_carry_realized_volatility_20d", volatility, unit="annualized_percent", source_id=config["ecb_fx"]["id"], source_name="ECB USD/JPY 20日已实现波动率", source_url=config["ecb_fx"]["documentation_url"], cadence="business_daily", quality_status=fx_quality, fetched_at=fetched_at,
            metadata={"formula": "最近20个共同交易日对数收益率标准差 × √252"},
        ),
        "yen_carry_cftc_leveraged_net_short": _metric(
            "yen_carry_cftc_leveraged_net_short", cftc, unit="contracts", source_id=config["cftc"]["id"], source_name=config["cftc"]["name"], source_url=config["cftc"]["documentation_url"], cadence="weekly", quality_status=cftc_quality, fetched_at=fetched_at,
            metadata={"formula": "杠杆基金日元空头合约 - 多头合约", "caveat": "只覆盖 CFTC 报告期货仓位，不代表全球日元套息交易总规模。"},
        ),
        "yen_carry_fx_swap_turnover": _metric(
            "yen_carry_fx_swap_turnover", swap_turnover, unit="usd_millions", source_id=config["boj"]["sources"][1]["id"], source_name=config["boj"]["sources"][1]["name"], source_url=config["boj"]["documentation_url"], cadence="business_daily", quality_status=swap_quality, fetched_at=fetched_at,
            metadata={"caveat": "成交额只表示活动强弱，不告诉我们资金方向。"},
        ),
        "yen_carry_carry_to_risk": _metric(
            "yen_carry_carry_to_risk", carry_to_risk, unit="ratio", source_id="yen_carry_derived", source_name="短端利差与汇率波动率", source_url=config["boj"]["documentation_url"], cadence="business_daily", quality_status="fresh_cache" if short_quality == "fresh_cache" or fx_quality == "fresh_cache" else "fresh_network" if short_quality in ELIGIBLE_STATUSES and fx_quality in ELIGIBLE_STATUSES else "unavailable", fetched_at=fetched_at,
            metadata={"formula": "短端利差 ÷ USD/JPY 20日年化已实现波动率", "role": "只用于比较利差相对汇率风险是否划算。"},
        ),
    }

    eligible_short_spread = (
        short_spread if short_quality in ELIGIBLE_STATUSES else []
    )
    spread_percentile = _percentile(
        [float(item["value"]) for item in eligible_short_spread],
        metrics["yen_carry_short_rate_spread"]["value"]
        if eligible_short_spread
        else None,
    )
    vol_percentile = _percentile([float(item["value"]) for item in volatility], metrics["yen_carry_realized_volatility_20d"]["value"])
    if spread_percentile is None or vol_percentile is None:
        incentive_code, incentive_label = "unknown", "证据不足"
    elif spread_percentile >= 67 and vol_percentile <= 67:
        incentive_code, incentive_label = "strong", "套息动力较强"
    elif spread_percentile <= 33 or vol_percentile >= 85:
        incentive_code, incentive_label = "weak", "套息动力较弱"
    else:
        incentive_code, incentive_label = "medium", "套息动力一般"

    pressure_inputs = [
        ("日元近5日快速升值", jpy_appreciation, False),
        ("汇率波动明显放大", volatility, False),
        (
            "美日短端利差快速收窄",
            spread_compression if short_quality in ELIGIBLE_STATUSES else [],
            False,
        ),
        ("杠杆基金正在回补日元空仓", cftc_covering, True),
    ]
    pressure_evidence = []
    for label, points, weekly in pressure_inputs:
        current = float(points[-1]["value"]) if points else None
        percentile = _percentile([float(item["value"]) for item in points], current)
        active = current is not None and current > 0 and percentile is not None and percentile >= 80
        pressure_evidence.append(
            {"label": label, "value": current, "percentile": percentile, "active": active, "cadence": "weekly" if weekly else "business_daily", "observed_at": points[-1]["observed_at"] if points else None}
        )
    active_count = sum(bool(item["active"]) for item in pressure_evidence)
    fx_percentile = pressure_evidence[0]["percentile"]
    vol_pressure_percentile = pressure_evidence[1]["percentile"]
    if sum(item["percentile"] is not None for item in pressure_evidence) < 2:
        pressure_code, pressure_label = "unknown", "证据不足"
    elif active_count >= 3 or ((fx_percentile or 0) >= 90 and (vol_pressure_percentile or 0) >= 80):
        pressure_code, pressure_label = "high", "平仓压力偏高"
    elif active_count >= 1:
        pressure_code, pressure_label = "warming", "平仓压力升温"
    else:
        pressure_code, pressure_label = "low", "暂未见集中平仓"

    latest_appreciation = metrics["yen_carry_jpy_appreciation_5d"]["value"]
    latest_vol = metrics["yen_carry_realized_volatility_20d"]["value"]
    states = {
        "carry_incentive": {
            "code": incentive_code,
            "label": incentive_label,
            "rate_spread_percentile_5y": spread_percentile,
            "volatility_percentile_5y": vol_percentile,
            "reason": f"短端利差 {metrics['yen_carry_short_rate_spread']['value']:.2f} 个百分点；20日汇率波动率 {latest_vol:.1f}%。" if isinstance(metrics["yen_carry_short_rate_spread"]["value"], (int, float)) and isinstance(latest_vol, (int, float)) else "利差或汇率波动数据不足。",
        },
        "unwind_pressure": {
            "code": pressure_code,
            "label": pressure_label,
            "active_trigger_count": active_count,
            "available_trigger_count": sum(item["percentile"] is not None for item in pressure_evidence),
            "evidence": pressure_evidence,
            "reason": f"日元近5个交易日升值 {latest_appreciation:.2f}%，20日波动率 {latest_vol:.1f}%；4项预警触发 {active_count} 项。" if isinstance(latest_appreciation, (int, float)) and isinstance(latest_vol, (int, float)) else "日元升值或波动数据不足。",
        },
    }
    warnings = [f"{item['name']}：{item['error']}" for item in source_health if item.get("error")]
    core_available = all(metrics[key]["available_for_analysis"] for key in ("yen_carry_usd_jpy", "yen_carry_short_rate_spread", "yen_carry_realized_volatility_20d"))
    available_count = sum(bool(item.get("available_for_analysis")) for item in metrics.values())
    quality_status = "fresh_cache" if any(item.get("quality_status") == "fresh_cache" for item in metrics.values() if item.get("available_for_analysis")) else "fresh_network" if core_available else "unavailable"
    latest_payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": iso_z(now),
        "status": "degraded" if warnings or available_count < len(metrics) else "ready",
        "quality_status": quality_status,
        "available_for_analysis": core_available,
        "metrics": metrics,
        "states": states,
        "charts": {
            "fx_and_volatility": {"available_for_analysis": bool(usd_jpy and volatility), "point_count": min(len(usd_jpy), len(volatility))},
            "rate_spreads": {"available_for_analysis": metrics["yen_carry_short_rate_spread"]["available_for_analysis"], "point_count": len(short_spread), "two_year_point_count": len(spread_2y)},
            "positioning": {"available_for_analysis": bool(cftc), "point_count": len(cftc)},
            "risk_sync": {"available_for_analysis": len(risk_sync) >= 2, "point_count": len(risk_sync)},
        },
        "sources": source_health,
        "quality": {
            "warnings": warnings,
            "available_metric_count": available_count,
            "total_metric_count": len(metrics),
            "missing_value_semantics": "null 表示不可用，永远不表示 0。",
            "revision_count": len(history.get("revisions", [])),
        },
        "methodology": {
            "role": "观察日元融资是否仍有吸引力，以及日元快速升值时的套息平仓压力；不进入美联储净流动性公式。",
            "scope": "无法直接量出全球日元套息交易总规模。CFTC 只是一部分期货仓位，外汇掉期成交额只表示活动，不表示方向。",
            "states": "状态由可复算规则生成：比较近5年滚动分位，80分位以上记为预警；不是 Agent 主观打分。",
            "risk_sync": "日元升值与 BTC/标普下跌同时出现，只能说与套息平仓相符，不能单独证明因果。",
        },
    }
    complete_history = {
        **history,
        "schema_version": SCHEMA_VERSION,
        "updated_at": iso_z(now),
        "derived": {
            "short_rate_spread": short_spread,
            "two_year_rate_spread": spread_2y,
            "realized_volatility_20d": volatility,
            "carry_to_risk": carry_to_risk,
            "jpy_appreciation_5d": jpy_appreciation,
            "spread_compression_20d": spread_compression,
            "cftc_covering_4w": cftc_covering,
            "risk_sync": risk_sync,
        },
    }
    return latest_payload, complete_history


def run_yen_carry_channel(
    root: Path,
    config_path: Path,
    data_dir: Path,
    *,
    direct: bool = False,
    fetcher: Any | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or utc_now()).astimezone(UTC)
    run_id = current.strftime("%Y%m%dT%H%M%S.%fZ")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise YenCarryChannelError("yen-carry source configuration is invalid")
    transport = fetcher or CurlFetcher(config.get("request_policy", {}), direct=direct)
    previous_history = _load_object(data_dir / "history.json") or {"series": {}, "revisions": []}
    previous_latest = _load_object(data_dir / "latest.json") or {}
    previous_health = {str(item.get("series_id")): item for item in previous_latest.get("sources", []) if isinstance(item, dict)}
    series = copy.deepcopy(previous_history.get("series", {}))
    revisions = list(previous_history.get("revisions", []))
    source_health = []
    fetched_values = []
    history_days = int(config["history_days"])
    overlap_days = int(config["overlap_days"])

    ecb = config["ecb_fx"]
    ecb_existing = series.get(ecb["series_id"], [])
    ecb_start = current.date() - timedelta(days=overlap_days if ecb_existing else history_days)
    ecb_url = ecb["url_template"].format(start_date=ecb_start.isoformat())
    ecb_ok, ecb_error, ecb_fetched = False, None, None
    try:
        response = transport.fetch(ecb_url)
        _save_raw(data_dir, ecb["id"], run_id, response, ecb_url, suffix="history-csv")
        incoming = parse_ecb_usd_jpy(response.body, now=current)
        series[ecb["series_id"]], detected = _merge_points(ecb_existing, incoming, series_id=ecb["series_id"], detected_at=iso_z(current))
        revisions.extend(detected)
        ecb_ok, ecb_fetched = True, response.fetched_at
        fetched_values.append(response.fetched_at)
    except (FetchError, YenCarryChannelError, KeyError, TypeError, ValueError) as exc:
        ecb_error = str(exc)
        ecb_fetched = previous_health.get(ecb["series_id"], {}).get("fetched_at")
    source_health.append(_source_health(ecb, series.get(ecb["series_id"], []), now=current, fetched_at=ecb_fetched, network_ok=ecb_ok, error=ecb_error))

    for boj_source in config["boj"]["sources"]:
        existing = series.get(boj_source["series_id"], [])
        start = current.date() - timedelta(days=overlap_days if existing else history_days)
        query = urlencode({"format": "json", "lang": "en", "db": boj_source["database"], "code": boj_source["code"], "startDate": start.strftime("%Y%m"), "endDate": current.strftime("%Y%m")})
        url = f"{config['boj']['base_url']}?{query}"
        ok, error, fetched = False, None, None
        try:
            response = transport.fetch(url)
            _save_raw(data_dir, boj_source["id"], run_id, response, url, suffix="history-json")
            parsed = parse_boj_series(response.body, expected_codes={boj_source["code"]}, now=current)
            series[boj_source["series_id"]], detected = _merge_points(existing, parsed[boj_source["code"]], series_id=boj_source["series_id"], detected_at=iso_z(current))
            revisions.extend(detected)
            ok, fetched = True, response.fetched_at
            fetched_values.append(response.fetched_at)
        except (FetchError, YenCarryChannelError, KeyError, TypeError, ValueError) as exc:
            error = str(exc)
            fetched = previous_health.get(boj_source["series_id"], {}).get("fetched_at")
        source_health.append(_source_health({**boj_source, "documentation_url": config["boj"]["documentation_url"]}, series.get(boj_source["series_id"], []), now=current, fetched_at=fetched, network_ok=ok, error=error))

    cftc = config["cftc"]
    cftc_existing = series.get(cftc["series_id"], [])
    first_year = current.year if cftc_existing else current.year - int(config["cftc_history_years"]) + 1
    cftc_incoming = []
    cftc_ok, cftc_error, cftc_fetched = False, None, None
    cftc_errors = []
    for year in range(first_year, current.year + 1):
        url = cftc["url_template"].format(year=year)
        try:
            response = transport.fetch(url)
            _save_raw(data_dir, cftc["id"], run_id, response, url, suffix=f"{year}-zip")
            cftc_incoming.extend(parse_cftc_jpy_zip(response.body, contract_code=cftc["contract_code"], now=current))
            cftc_ok, cftc_fetched = True, response.fetched_at
            fetched_values.append(response.fetched_at)
        except (FetchError, YenCarryChannelError, KeyError, TypeError, ValueError) as exc:
            cftc_errors.append(f"{year}: {exc}")
    if cftc_incoming:
        series[cftc["series_id"]], detected = _merge_points(cftc_existing, cftc_incoming, series_id=cftc["series_id"], detected_at=iso_z(current))
        revisions.extend(detected)
    if cftc_errors:
        cftc_error = "; ".join(cftc_errors)
    if not cftc_fetched:
        cftc_fetched = previous_health.get(cftc["series_id"], {}).get("fetched_at")
    source_health.append(_source_health(cftc, series.get(cftc["series_id"], []), now=current, fetched_at=cftc_fetched, network_ok=cftc_ok, error=cftc_error))

    jsda = config["jsda"]
    jsda_existing = series.get(jsda["series_id"], [])
    archive_url = jsda["archive_url_template"].format(year=current.year)
    jsda_ok, jsda_error, jsda_fetched = False, None, None
    try:
        archive_response = transport.fetch(archive_url)
        _save_raw(data_dir, jsda["id"], run_id, archive_response, archive_url, suffix="archive-html")
        relative_url, publication_date = parse_jsda_archive(archive_response.body, now=current)
        csv_url = urljoin(jsda["csv_base_url"], relative_url)
        csv_response = transport.fetch(csv_url)
        _save_raw(data_dir, jsda["id"], run_id, csv_response, csv_url, suffix="latest-csv")
        point = parse_jsda_jgb_2y(csv_response.body, publication_date=publication_date, minimum_remaining_days=int(jsda["minimum_remaining_days"]), maximum_remaining_days=int(jsda["maximum_remaining_days"]))
        series[jsda["series_id"]], detected = _merge_points(jsda_existing, [point], series_id=jsda["series_id"], detected_at=iso_z(current))
        revisions.extend(detected)
        jsda_ok, jsda_fetched = True, max(archive_response.fetched_at, csv_response.fetched_at)
        fetched_values.extend([archive_response.fetched_at, csv_response.fetched_at])
    except (FetchError, YenCarryChannelError, KeyError, TypeError, ValueError) as exc:
        jsda_error = str(exc)
        jsda_fetched = previous_health.get(jsda["series_id"], {}).get("fetched_at")
    source_health.append(_source_health(jsda, series.get(jsda["series_id"], []), now=current, fetched_at=jsda_fetched, network_ok=jsda_ok, error=jsda_error))

    history = {"schema_version": SCHEMA_VERSION, "series": series, "revisions": revisions[-500:]}
    payload, complete_history = build_yen_carry_payload(root, history, config, source_health, now=current, run_id=run_id, fetched_at=max(fetched_values) if fetched_values else None)
    atomic_write_json(data_dir / "history.json", complete_history)
    if payload.get("available_for_analysis"):
        atomic_write_json(data_dir / "last-good.json", payload)
    atomic_write_json(data_dir / "runs" / f"{run_id}.json", payload)
    atomic_write_json(data_dir / "latest.json", payload)
    return payload


def load_yen_carry_payload(root: Path) -> dict[str, Any]:
    return _load_object(root / "data" / "yen-carry" / "latest.json") or {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "quality_status": "unavailable",
        "available_for_analysis": False,
        "metrics": {},
        "states": {},
        "charts": {},
        "sources": [],
        "quality": {"warnings": ["日元套息数据尚未生成。"]},
        "methodology": {"role": "日元套息是独立风险因子，不进入净流动性公式。"},
    }


def load_yen_carry_history(root: Path) -> dict[str, Any]:
    return _load_object(root / "data" / "yen-carry" / "history.json") or {
        "schema_version": SCHEMA_VERSION,
        "series": {},
        "derived": {},
        "revisions": [],
    }
