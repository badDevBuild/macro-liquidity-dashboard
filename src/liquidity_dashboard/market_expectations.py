from __future__ import annotations

import json
import math
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


UTC = timezone.utc

MONTH_LABELS = {
    "january": "1 月",
    "february": "2 月",
    "march": "3 月",
    "april": "4 月",
    "may": "5 月",
    "june": "6 月",
    "july": "7 月",
    "august": "8 月",
    "september": "9 月",
    "october": "10 月",
    "november": "11 月",
    "december": "12 月",
}


class ExpectationsError(RuntimeError):
    pass


def _iso_now(now: datetime | None = None) -> str:
    current = now or datetime.now(tz=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _fetch_json(url: str, timeout_seconds: int) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "/usr/bin/curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            str(timeout_seconds),
            url,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds + 5,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or f"curl exited {completed.returncode}"
        raise ExpectationsError(message[:300])
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ExpectationsError("Polymarket returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ExpectationsError("Polymarket response is not an object")
    return payload


def _future(value: Any, now: datetime) -> bool:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC) >= now.astimezone(UTC)


def _event_year(event: dict[str, Any]) -> int | None:
    match = re.search(r"\b(20\d{2})\b", str(event.get("title") or ""))
    return int(match.group(1)) if match else None


def _target_year(topic: dict[str, Any], now: datetime) -> int | None:
    target = topic.get("target_year")
    if target == "current":
        return now.astimezone(UTC).year
    try:
        return int(target) if target is not None else None
    except (TypeError, ValueError):
        return None


def _is_neg_risk_event(event: dict[str, Any]) -> bool:
    return event.get("negRisk") is True or event.get("enableNegRisk") is True


def _age_hours(value: Any, now: datetime) -> float | None:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    seconds = (now.astimezone(UTC) - moment.astimezone(UTC)).total_seconds()
    return round(max(0.0, seconds / 3600), 3)


def select_event(
    payload: dict[str, Any], topic: dict[str, Any], *, now: datetime
) -> dict[str, Any] | None:
    pattern = re.compile(str(topic.get("title_pattern") or ".*"), re.IGNORECASE)
    target_year = _target_year(topic, now)
    candidates = []
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        if event.get("active") is not True or event.get("closed") is True:
            continue
        if event.get("archived") is True or not _future(event.get("endDate"), now):
            continue
        if not pattern.search(str(event.get("title") or "")):
            continue
        if target_year is not None and _event_year(event) != target_year:
            continue
        if topic.get("require_neg_risk") is True and not _is_neg_risk_event(event):
            continue
        liquidity = _number(event.get("liquidity")) or 0.0
        volume_24h = _number(event.get("volume24hr")) or 0.0
        candidates.append((volume_24h, liquidity, event))
    return max(candidates, default=(0.0, 0.0, None), key=lambda item: item[:2])[2]


def _display_outcome(
    topic: dict[str, Any], label: str, threshold: float | None
) -> str:
    action = str(topic.get("policy_action") or "")
    if action in {"cut", "hike"} and threshold is not None:
        count = int(threshold)
        suffix = "次以上" if "+" in label else "次"
        return f"{'降息' if action == 'cut' else '加息'} {count} {suffix}"
    topic_id = str(topic.get("topic_id") or "")
    if topic_id == "us_inflation_distribution":
        return f"同比 {label}"
    if topic_id == "us_recession_probability":
        return "会发生"
    return label


def _display_topic(event: dict[str, Any], topic: dict[str, Any]) -> str:
    title = str(event.get("title") or "")
    year_match = re.search(r"\b(20\d{2})\b", title)
    year = year_match.group(1) if year_match else ""
    topic_id = topic.get("topic_id")
    action = str(topic.get("policy_action") or "")
    if action in {"cut", "hike"}:
        action_label = "降息" if action == "cut" else "加息"
        return f"{year} 年全年美联储{action_label}次数" if year else f"全年美联储{action_label}次数"
    if topic_id == "us_inflation_distribution":
        month_match = re.match(r"([A-Za-z]+)", title)
        month = MONTH_LABELS.get(
            month_match.group(1).lower() if month_match else "", "下一次"
        )
        return f"{month}美国同比通胀"
    if topic_id == "us_recession_probability":
        return f"{year} 年底前美国进入衰退" if year else "美国进入衰退"
    return str(topic.get("label") or title)


def _market_outcome(
    market: dict[str, Any], topic: dict[str, Any]
) -> dict[str, Any] | None:
    outcomes = _json_list(market.get("outcomes"))
    prices = _json_list(market.get("outcomePrices"))
    if len(outcomes) != len(prices) or not outcomes:
        return None
    try:
        yes_index = next(
            index for index, outcome in enumerate(outcomes)
            if str(outcome).strip().lower() == "yes"
        )
    except StopIteration:
        yes_index = 0
    probability = _number(prices[yes_index])
    if probability is None or not 0 <= probability <= 1:
        return None
    label = str(
        market.get("groupItemTitle")
        or market.get("question")
        or outcomes[yes_index]
    ).strip()
    threshold = _number(market.get("groupItemThreshold"))
    return {
        "outcome_id": f"polymarket_{market.get('id')}",
        "market_id": str(market.get("id") or ""),
        "label": label,
        "display_label": _display_outcome(topic, label, threshold),
        "question": str(market.get("question") or ""),
        "probability": round(probability, 6),
        "change_1d": _number(market.get("oneDayPriceChange")),
        "change_1w": _number(market.get("oneWeekPriceChange")),
        "change_1m": _number(market.get("oneMonthPriceChange")),
        "liquidity_usd": _number(market.get("liquidityNum") or market.get("liquidity")),
        "volume_24h_usd": _number(market.get("volume24hr")),
        "updated_at": market.get("updatedAt"),
        "threshold": threshold,
    }


def normalize_event(
    event: dict[str, Any],
    topic: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(tz=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    if topic.get("require_neg_risk") is True and not _is_neg_risk_event(event):
        raise ExpectationsError("selected distribution is not a neg-risk event")
    outcomes = []
    for market in event.get("markets", []):
        if not isinstance(market, dict):
            continue
        if market.get("active") is not True or market.get("closed") is True:
            continue
        item = _market_outcome(market, topic)
        if item:
            outcomes.append(item)
    if not outcomes:
        raise ExpectationsError("selected event has no usable market probabilities")
    presentation = str(topic.get("presentation") or "binary")
    if presentation == "binary":
        outcomes = outcomes[:1]
    policy_action = str(topic.get("policy_action") or "")
    if presentation == "distribution" and policy_action in {"cut", "hike"}:
        thresholds = [item.get("threshold") for item in outcomes]
        if any(value is None or value < 0 for value in thresholds):
            raise ExpectationsError("policy distribution has an invalid threshold")
        if len(set(thresholds)) != len(thresholds):
            raise ExpectationsError("policy distribution has duplicate thresholds")
        display_outcomes = sorted(outcomes, key=lambda item: item["threshold"])
    else:
        display_outcomes = sorted(
            outcomes, key=lambda item: item["probability"], reverse=True
        )
    top_outcome = max(outcomes, key=lambda item: item["probability"])
    liquidity = _number(event.get("liquidity")) or 0.0
    volume_24h = _number(event.get("volume24hr")) or 0.0
    minimum_liquidity = float(topic.get("minimum_liquidity_usd", 0))
    minimum_volume = float(topic.get("minimum_volume_24h_usd", 0))
    quality = (
        "liquid"
        if liquidity >= minimum_liquidity and volume_24h >= minimum_volume
        else "thin"
    )
    probability_sum = None
    overround_percentage_points = None
    if presentation == "distribution":
        probability_sum = round(sum(item["probability"] for item in outcomes), 6)
        overround_percentage_points = round((probability_sum - 1.0) * 100, 3)
    maximum_age_hours = _number(topic.get("maximum_age_hours"))
    age_hours = _age_hours(event.get("updatedAt"), current)
    if maximum_age_hours is None:
        freshness_status = "not_configured"
    elif age_hours is None:
        freshness_status = "unknown"
    elif age_hours <= maximum_age_hours:
        freshness_status = "fresh"
    else:
        freshness_status = "stale"
    analysis_eligible = quality == "liquid" and freshness_status not in {
        "stale",
        "unknown",
    }
    slug = str(event.get("slug") or "")
    return {
        "topic_id": topic["topic_id"],
        "label": topic["label"],
        "display_label": _display_topic(event, topic),
        "presentation": presentation,
        "policy_action": policy_action or None,
        "state": "ready",
        "quality": quality,
        "freshness_status": freshness_status,
        "age_hours": age_hours,
        "analysis_eligible": analysis_eligible,
        "event_id": str(event.get("id") or ""),
        "event_year": _event_year(event),
        "neg_risk": _is_neg_risk_event(event),
        "title": str(event.get("title") or ""),
        "url": f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com",
        "end_date": event.get("endDate"),
        "updated_at": event.get("updatedAt"),
        "liquidity_usd": liquidity,
        "volume_24h_usd": volume_24h,
        "probability_sum": probability_sum,
        "overround_percentage_points": overround_percentage_points,
        "probabilities_normalized": False,
        "expected_value": None,
        "expected_value_reason": (
            "次数分布含开放区间且原始盘口未归一化，不展示平均次数。"
            if policy_action in {"cut", "hike"}
            else None
        ),
        "top_outcome": top_outcome,
        "outcomes": display_outcomes,
    }


def _load_history(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"schema_version": "1.1", "topics": {}}
    return payload if isinstance(payload, dict) else {"schema_version": "1.1", "topics": {}}


def _update_history(
    history: dict[str, Any], topics: list[dict[str, Any]], generated_at: str
) -> dict[str, Any]:
    day = generated_at[:10]
    topic_history = history.setdefault("topics", {})
    for topic in topics:
        if topic.get("state") != "ready":
            continue
        points = topic_history.setdefault(topic["topic_id"], [])
        event_id = topic.get("event_id")
        had_other_event = any(
            item.get("event_id") and item.get("event_id") != event_id
            for item in points
            if isinstance(item, dict)
        )
        had_current_event = any(
            item.get("event_id") == event_id
            for item in points
            if isinstance(item, dict)
        )
        point = {
            "observed_at": day,
            "event_id": topic.get("event_id"),
            "outcomes": {
                item["outcome_id"]: {
                    "label": item["label"],
                    "probability": item["probability"],
                }
                for item in topic.get("outcomes", [])
            },
        }
        points[:] = [item for item in points if item.get("observed_at") != day]
        points.append(point)
        points.sort(key=lambda item: item.get("observed_at", ""))
        points[:] = points[-180:]
        current_event_points = [
            item for item in points if item.get("event_id") == event_id
        ]
        topic["history"] = current_event_points[-90:]
        topic["history_event_id"] = event_id
        topic["history_reset"] = had_other_event and not had_current_event
    history["schema_version"] = "1.1"
    history["updated_at"] = generated_at
    return history


def collect_expectations(
    config: dict[str, Any], data_dir: Path, *, now: datetime | None = None
) -> dict[str, Any]:
    current = now or datetime.now(tz=UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    generated_at = _iso_now(current)
    provider = config.get("provider", {})
    base_url = str(provider.get("base_url") or "https://gamma-api.polymarket.com")
    request = config.get("request", {})
    timeout_seconds = int(request.get("timeout_seconds", 25))
    limit = int(request.get("max_results_per_type", 10))
    topics: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    for topic in config.get("topics", []):
        if not isinstance(topic, dict):
            continue
        query = urlencode({"q": topic.get("query", ""), "limit_per_type": limit})
        try:
            payload = _fetch_json(f"{base_url}/public-search?{query}", timeout_seconds)
            event = select_event(payload, topic, now=current)
            if event is None:
                raise ExpectationsError("no active matching event")
            topics.append(normalize_event(event, topic, now=current))
        except (ExpectationsError, subprocess.TimeoutExpired) as exc:
            message = str(exc)[:300]
            topics.append(
                {
                    "topic_id": topic.get("topic_id"),
                    "label": topic.get("label"),
                    "presentation": topic.get("presentation"),
                    "state": "unavailable",
                    "message": message,
                    "outcomes": [],
                    "history": [],
                }
            )
            warnings.append({"topic_id": str(topic.get("topic_id")), "message": message})
    ready_count = sum(item.get("state") == "ready" for item in topics)
    if ready_count == len(topics) and topics:
        status = "ready"
    elif ready_count:
        status = "degraded"
    else:
        status = "unavailable"
    history_path = data_dir / "expectations" / "history.json"
    history = _update_history(_load_history(history_path), topics, generated_at)
    payload = {
        "schema_version": "1.1",
        "generated_at": generated_at,
        "status": status,
        "provider": provider,
        "methodology": {
            "label": "市场隐含概率，不是事实或预测结论",
            "rules": [
                "概率直接读取 Polymarket 市场价格，并保留成交量与流动性。",
                "互斥分布保留原始盘口合计与相对 100% 的差值，不静默归一化。",
                "年度加息和降息次数是两组累计盘口，不能互减成净政策路径。",
                "低流动性市场标为 thin，不作为强证据。",
                "预测市场缺失不会阻断官方数据与 Agent 分析。",
            ],
        },
        "cme_fedwatch": config.get("cme_fedwatch", {}),
        "topics": topics,
        "warnings": warnings,
    }
    _atomic_json(history_path, history)
    _atomic_json(data_dir / "expectations" / "latest.json", payload)
    return payload


def load_market_expectations(root: Path) -> dict[str, Any]:
    path = root / "data" / "expectations" / "latest.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {
            "schema_version": "1.0",
            "status": "unavailable",
            "generated_at": None,
            "topics": [],
            "warnings": [{"message": "市场预期数据尚未生成"}],
        }
    return payload if isinstance(payload, dict) else {"status": "unavailable", "topics": []}
