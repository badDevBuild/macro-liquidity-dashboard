from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .context_channel import load_context_bundle


REQUIRED_TEXT_FIELDS = (
    "schema_version",
    "prompt_version",
    "analysis_id",
    "snapshot_run_id",
    "context_bundle_id",
    "generated_at",
    "overall_assessment",
    "confidence",
    "headline",
    "summary",
    "market_bottom_line",
    "context_screening_note",
    "data_quality_note",
)
EVIDENCE_SECTIONS = ("drivers", "contradictions")
ALLOWED_ASSESSMENTS = {"easing", "tightening", "mixed", "uncertain"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_STATUSES = {"ready", "insufficient_evidence"}
ALLOWED_WINDOWS = {
    "since_previous_run",
    "latest_release",
    "1d",
    "1w",
    "1m",
    "3m",
    "1y",
}
ALLOWED_EFFECTS = {"supportive", "draining", "mixed", "neutral"}
ALLOWED_CONTEXT_RELEVANCE = {"relevant", "watch", "already_reflected"}
ALLOWED_CONTENT_BASIS = {
    "full_text",
    "summary",
    "official_schedule",
    "title_only",
    "fetch_error",
}
ALLOWED_MARKET_BIASES = {"tailwind", "headwind", "mixed", "uncertain"}
REQUIRED_LAYERS = {
    "balance_sheet_liquidity",
    "funding_and_rates",
    "dollar_and_financial_conditions",
    "risk_asset_transmission",
}
ALLOWED_DAILY_UPDATE_STATUSES = {
    "new_data",
    "no_official_updates",
    "partial_update",
    "comparison_unavailable",
}
AGENT_SCHEMA_VERSION = "1.5"
AGENT_PROMPT_VERSION = "macro-liquidity-morning-v9"
AGENT_MODEL_PROVIDER = "openai_codex_subscription"
AGENT_MODEL_ID = "gpt-5.6-sol"
AGENT_REASONING_EFFORT = "medium"


def _base(state: str, message: str) -> dict[str, Any]:
    return {
        "state": state,
        "message": message,
        "is_current": False,
    }


def _read_payload(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _same_number(left: Any, right: Any) -> bool:
    if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
        return False
    return math.isclose(float(left), float(right), rel_tol=1e-9, abs_tol=1e-6)


def _proxy_metric(
    metric_id: str,
    proxy: dict[str, Any],
    weekly_proxy: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return one canonical metric view for either raw or compact proxy data."""
    proxy_changes = proxy.get("changes")
    if not isinstance(proxy_changes, dict):
        proxy_changes = {}
    if metric_id == "net_liquidity_proxy":
        one_week = proxy_changes.get("1w")
        if not isinstance(one_week, dict):
            one_week = {"change": proxy.get("week_change")}
        return {
            "value": proxy.get("value"),
            "observed_at": proxy.get("observed_at"),
            "changes": {"1w": one_week},
        }
    if metric_id == "net_liquidity_proxy_latest_release":
        latest_release = proxy_changes.get("latest_release")
        if not isinstance(latest_release, dict):
            latest_release = {"change": proxy.get("latest_release_change")}
        return {
            "value": proxy.get("value"),
            "observed_at": proxy.get("observed_at"),
            "changes": {"latest_release": latest_release},
        }
    if metric_id == "net_liquidity_proxy_weekly":
        if isinstance(weekly_proxy, dict):
            return weekly_proxy
        return {
            "value": proxy.get("trend_latest_value"),
            "observed_at": proxy.get("trend_latest_observed_at"),
            "changes": proxy.get("trend_changes", {}),
        }
    return None


def _metric_for_evidence(
    metric_id: Any,
    metrics: dict[str, dict[str, Any]],
    proxy: dict[str, Any],
    weekly_proxy: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(metric_id, str):
        return None
    if metric_id.startswith("net_liquidity_proxy"):
        return _proxy_metric(metric_id, proxy, weekly_proxy)
    metric = metrics.get(metric_id)
    return metric if isinstance(metric, dict) else None


def _delta_update(
    metric_id: str, analysis_delta: dict[str, Any] | None
) -> dict[str, Any] | None:
    for section in ("official_updates", "derived_updates", "risk_asset_updates"):
        section_items = (analysis_delta or {}).get(section, [])
        if not isinstance(section_items, list):
            continue
        update = next(
            (
                item
                for item in section_items
                if isinstance(item, dict) and item.get("metric_id") == metric_id
            ),
            None,
        )
        if isinstance(update, dict):
            return update
    return None


def expected_evidence(
    evidence: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
    proxy: dict[str, Any],
    analysis_delta: dict[str, Any] | None = None,
    weekly_proxy: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build the sole valid evidence object for a requested metric/window.

    A named comparison window is unavailable unless its change is numeric. This
    deliberately keeps ``window=<name>, change=null`` distinct from a valid
    point-in-time citation, where both fields are null.
    """
    metric_id = evidence.get("metric_id")
    metric = _metric_for_evidence(metric_id, metrics, proxy, weekly_proxy)
    if not isinstance(metric, dict) or metric.get("available_for_analysis") is False:
        return None

    value = metric.get("value")
    observed_at = metric.get("observed_at")
    if not isinstance(value, (int, float)):
        return None

    window = evidence.get("comparison_window")
    if window is None:
        return {
            "metric_id": metric_id,
            "observed_at": observed_at,
            "value": value,
            "comparison_window": None,
            "change": None,
        }
    if window not in ALLOWED_WINDOWS:
        return None

    if window == "since_previous_run":
        update = _delta_update(str(metric_id), analysis_delta)
        if not isinstance(update, dict):
            return None
        update_value = update.get("value")
        change = update.get("change")
        if not isinstance(update_value, (int, float)) or not isinstance(
            change, (int, float)
        ):
            return None
        return {
            "metric_id": metric_id,
            "observed_at": update.get("observed_at"),
            "value": update_value,
            "comparison_window": window,
            "change": change,
        }

    if window == "latest_release" and metric_id not in {
        "net_liquidity_proxy",
        "net_liquidity_proxy_latest_release",
        "net_liquidity_proxy_weekly",
    }:
        change = metric.get("latest_change")
    else:
        changes = metric.get("changes")
        window_data = changes.get(window) if isinstance(changes, dict) else None
        if not isinstance(window_data, dict) or window_data.get("coverage_matched") is False:
            return None
        change = window_data.get("change")
    if not isinstance(change, (int, float)):
        return None
    return {
        "metric_id": metric_id,
        "observed_at": observed_at,
        "value": value,
        "comparison_window": window,
        "change": change,
    }


def valid_evidence_options(
    metric_id: str,
    metrics: dict[str, dict[str, Any]],
    proxy: dict[str, Any],
    analysis_delta: dict[str, Any] | None = None,
    weekly_proxy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """List exact evidence objects that both analysis and repair may cite."""
    options: list[dict[str, Any]] = []
    for window in (
        "since_previous_run",
        "latest_release",
        "1d",
        "1w",
        "1m",
        "3m",
        "1y",
        None,
    ):
        option = expected_evidence(
            {"metric_id": metric_id, "comparison_window": window},
            metrics,
            proxy,
            analysis_delta,
            weekly_proxy,
        )
        if option is not None and option not in options:
            options.append(option)
    return options


def _evidence_matches(
    evidence: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
    proxy: dict[str, Any],
    analysis_delta: dict[str, Any] | None = None,
    weekly_proxy: dict[str, Any] | None = None,
) -> bool:
    expected = expected_evidence(
        evidence, metrics, proxy, analysis_delta, weekly_proxy
    )
    if expected is None:
        return False
    for field in (
        "metric_id",
        "observed_at",
        "value",
        "comparison_window",
        "change",
    ):
        submitted = evidence.get(field)
        canonical = expected.get(field)
        if isinstance(canonical, (int, float)):
            if not _same_number(submitted, canonical):
                return False
        elif submitted != canonical:
            return False
    return True


def _validate_payload(
    payload: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
    proxy: dict[str, Any],
    context_items: dict[str, dict[str, Any]] | None = None,
    analysis_delta: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_TEXT_FIELDS:
        if not isinstance(payload.get(field), str) or not payload[field].strip():
            errors.append(f"{field} is required")
    if payload.get("schema_version") != AGENT_SCHEMA_VERSION:
        errors.append("schema_version is invalid")
    if payload.get("prompt_version") != AGENT_PROMPT_VERSION:
        errors.append("prompt_version is invalid")
    if payload.get("status") not in ALLOWED_STATUSES:
        errors.append("status is invalid")
    if payload.get("overall_assessment") not in ALLOWED_ASSESSMENTS:
        errors.append("overall_assessment is invalid")
    if payload.get("confidence") not in ALLOWED_CONFIDENCE:
        errors.append("confidence is invalid")
    model = payload.get("model")
    if not isinstance(model, dict) or not all(
        isinstance(model.get(field), str) and model[field].strip()
        for field in ("provider", "id", "reasoning_effort")
    ):
        errors.append("model provider and id are required")
    elif model != {
        "provider": AGENT_MODEL_PROVIDER,
        "id": AGENT_MODEL_ID,
        "reasoning_effort": AGENT_REASONING_EFFORT,
    }:
        errors.append("model metadata does not match the configured runtime")
    for section in (*EVIDENCE_SECTIONS, "watch_items"):
        if not isinstance(payload.get(section), list):
            errors.append(f"{section} must be a list")
    if not isinstance(payload.get("unknowns"), list):
        errors.append("unknowns must be a list")
    if not isinstance(payload.get("context_assessments"), list):
        errors.append("context_assessments must be a list")
    if not isinstance(payload.get("layer_analysis"), list):
        errors.append("layer_analysis must be a list")
    if not isinstance(payload.get("market_implications"), dict):
        errors.append("market_implications must be an object")
    daily_update = payload.get("daily_update")
    if not isinstance(daily_update, dict):
        errors.append("daily_update must be an object")
    else:
        expected_daily_status = (analysis_delta or {}).get(
            "status", "comparison_unavailable"
        )
        if daily_update.get("status") not in ALLOWED_DAILY_UPDATE_STATUSES:
            errors.append("daily_update.status is invalid")
        elif daily_update.get("status") != expected_daily_status:
            errors.append("daily_update.status does not match the deterministic comparison")
        for field in ("headline", "summary", "market_expectation_note"):
            if not isinstance(daily_update.get(field), str) or not daily_update[field].strip():
                errors.append(f"daily_update.{field} is required")
        daily_evidence = daily_update.get("evidence")
        if not isinstance(daily_evidence, list):
            errors.append("daily_update.evidence must be a list")
        else:
            if expected_daily_status in {"new_data", "partial_update"} and not daily_evidence:
                errors.append("daily_update with new official data must include evidence")
            if expected_daily_status in {"no_official_updates", "comparison_unavailable"} and daily_evidence:
                errors.append("daily_update must not invent evidence when no official data changed")
            official_ids = {
                item.get("metric_id")
                for item in (analysis_delta or {}).get("official_updates", [])
                if isinstance(item, dict)
            }
            for evidence in daily_evidence:
                if (
                    not isinstance(evidence, dict)
                    or evidence.get("comparison_window") != "since_previous_run"
                    or evidence.get("metric_id") not in official_ids
                    or not _evidence_matches(
                        evidence, metrics, proxy, analysis_delta
                    )
                ):
                    errors.append("daily_update contains evidence that does not match the previous run")
    for section in EVIDENCE_SECTIONS:
        for item in payload.get(section, []) if isinstance(payload.get(section), list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("claim"), str):
                errors.append(f"{section} contains an invalid claim")
                continue
            if item.get("effect") not in ALLOWED_EFFECTS:
                errors.append(f"{section} contains an invalid effect")
            evidence_items = item.get("evidence")
            if not isinstance(evidence_items, list) or not evidence_items:
                errors.append(f"{section} claim has no evidence")
                continue
            for evidence in evidence_items:
                if not isinstance(evidence, dict) or not _evidence_matches(
                    evidence, metrics, proxy, analysis_delta
                ):
                    errors.append(f"{section} contains evidence that does not match the snapshot")
    if payload.get("status") == "ready" and not payload.get("drivers"):
        errors.append("ready analysis must include at least one evidenced driver")
    layer_names: list[str] = []
    for item in payload.get("layer_analysis", []) if isinstance(payload.get("layer_analysis"), list) else []:
        if not isinstance(item, dict):
            errors.append("layer_analysis contains an invalid item")
            continue
        layer = item.get("layer")
        layer_names.append(layer)
        if layer not in REQUIRED_LAYERS:
            errors.append("layer_analysis contains an unknown layer")
        if item.get("assessment") not in ALLOWED_ASSESSMENTS:
            errors.append("layer_analysis contains an invalid assessment")
        if not isinstance(item.get("conclusion"), str) or not item["conclusion"].strip():
            errors.append("layer_analysis contains an invalid conclusion")
        evidence_items = item.get("evidence")
        if not isinstance(evidence_items, list) or not evidence_items:
            errors.append("layer_analysis item has no evidence")
        else:
            for evidence in evidence_items:
                if not isinstance(evidence, dict) or not _evidence_matches(
                    evidence, metrics, proxy, analysis_delta
                ):
                    errors.append("layer_analysis contains evidence that does not match the snapshot")
    if set(layer_names) != REQUIRED_LAYERS or len(layer_names) != len(REQUIRED_LAYERS):
        errors.append("layer_analysis must contain each required layer exactly once")

    known_metric_ids = set(metrics) | {
        "net_liquidity_proxy",
        "net_liquidity_proxy_latest_release",
        "net_liquidity_proxy_weekly",
    }
    market_implications = payload.get("market_implications", {})
    for market in ("equities", "crypto"):
        item = market_implications.get(market) if isinstance(market_implications, dict) else None
        if not isinstance(item, dict):
            errors.append(f"market_implications.{market} is required")
            continue
        if item.get("bias") not in ALLOWED_MARKET_BIASES:
            errors.append(f"market_implications.{market} has an invalid bias")
        for field in ("conclusion", "transmission"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"market_implications.{market}.{field} is required")
        for field in ("confirm_metric_ids", "invalidate_metric_ids"):
            metric_ids = item.get(field)
            if not isinstance(metric_ids, list) or not metric_ids:
                errors.append(f"market_implications.{market}.{field} is required")
            elif any(metric_id not in known_metric_ids for metric_id in metric_ids):
                errors.append(f"market_implications.{market}.{field} contains an unknown metric")
            elif len(metric_ids) != len(set(metric_ids)):
                errors.append(f"market_implications.{market}.{field} contains duplicate metrics")
    for item in payload.get("watch_items", []) if isinstance(payload.get("watch_items"), list) else []:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(field), str) and item[field].strip()
            for field in ("trigger", "why")
        ):
            errors.append("watch_items contains an invalid item")
            continue
        metric_ids = item.get("metric_ids")
        if not isinstance(metric_ids, list) or not metric_ids or any(
            metric_id not in metrics
            and metric_id not in {"net_liquidity_proxy", "net_liquidity_proxy_latest_release", "net_liquidity_proxy_weekly"}
            for metric_id in metric_ids
        ):
            errors.append("watch_items contains an unknown metric")
        elif len(metric_ids) != len(set(metric_ids)):
            errors.append("watch_items contains duplicate metrics")
    if isinstance(payload.get("unknowns"), list) and any(
        not isinstance(item, str) or not item.strip() for item in payload["unknowns"]
    ):
        errors.append("unknowns contains an invalid item")
    known_context = context_items or {}
    seen_context: set[str] = set()
    for item in payload.get("context_assessments", []) if isinstance(payload.get("context_assessments"), list) else []:
        if not isinstance(item, dict):
            errors.append("context_assessments contains an invalid item")
            continue
        context_id = item.get("context_id")
        if not isinstance(context_id, str) or context_id not in known_context:
            errors.append("context_assessments contains an unknown context item")
        elif context_id in seen_context:
            errors.append("context_assessments contains a duplicate context item")
        else:
            seen_context.add(context_id)
        if item.get("relevance") not in ALLOWED_CONTEXT_RELEVANCE:
            errors.append("context_assessments contains an invalid relevance")
        source_item = known_context.get(context_id, {}) if isinstance(context_id, str) else {}
        content_basis = item.get("content_basis")
        expected_basis = source_item.get("content_status") or (
            "official_schedule"
            if source_item.get("kind") == "scheduled_event"
            else "title_only"
        )
        if content_basis not in ALLOWED_CONTENT_BASIS or content_basis != expected_basis:
            errors.append("context_assessments content basis does not match the source")
        if (
            source_item.get("kind") == "past_news"
            and content_basis in {"title_only", "fetch_error"}
        ):
            errors.append("context_assessments cannot analyze past news without content")
        for field in ("what_happened", "transmission", "reason"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                errors.append(f"context_assessments contains an invalid {field}")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            errors.append("context_assessments contains an invalid reason")
        metric_ids = item.get("linked_metric_ids")
        if not isinstance(metric_ids, list) or any(
            metric_id not in metrics
            and metric_id not in {"net_liquidity_proxy", "net_liquidity_proxy_latest_release", "net_liquidity_proxy_weekly"}
            for metric_id in metric_ids
        ):
            errors.append("context_assessments contains an unknown metric")
        elif len(metric_ids) != len(set(metric_ids)):
            errors.append("context_assessments contains duplicate metrics")
        if item.get("relevance") == "already_reflected" and source_item.get("kind") == "past_news":
            published = str(source_item.get("published_at") or "")[:10]
            linked_dates = []
            for metric_id in metric_ids if isinstance(metric_ids, list) else []:
                if metric_id == "net_liquidity_proxy_latest_release":
                    linked_dates.append(str(proxy.get("observed_at") or "")[:10])
                elif metric_id == "net_liquidity_proxy_weekly":
                    linked_dates.append(str(proxy.get("trend_latest_observed_at") or "")[:10])
                elif metric_id == "net_liquidity_proxy":
                    linked_dates.append(str(proxy.get("observed_at") or "")[:10])
                else:
                    linked_dates.append(str(metrics.get(metric_id, {}).get("observed_at") or "")[:10])
            if not published or not any(date_value and date_value >= published for date_value in linked_dates):
                errors.append("already_reflected lacks a linked observation at or after the news")

    def text_values(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            result: list[str] = []
            for nested in value.values():
                result.extend(text_values(nested))
            return result
        if isinstance(value, list):
            result = []
            for nested in value:
                result.extend(text_values(nested))
            return result
        return []

    if any("百万美元" in text for text in text_values(payload)):
        errors.append("analysis prose must use Chinese 亿美元/万亿美元 units instead of 百万美元")
    # Mixed observation dates are supported. Temporal prose (including negated
    # caveats) is interpreted by the Agent; evidence dates/windows are validated
    # above. A keyword match cannot establish a false same-day claim.
    return errors


def validate_agent_payload(
    payload: dict[str, Any],
    metrics: dict[str, dict[str, Any]],
    proxy: dict[str, Any],
    context_items: dict[str, dict[str, Any]] | None = None,
    analysis_delta: dict[str, Any] | None = None,
) -> list[str]:
    """Validate an Agent artifact against the exact deterministic snapshot views."""
    return _validate_payload(payload, metrics, proxy, context_items, analysis_delta)


def _analysis_context(root: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    snapshot_id = re_safe_component(str(payload.get("snapshot_run_id") or ""))
    analysis_id = re_safe_component(str(payload.get("analysis_id") or ""))
    if not snapshot_id or not analysis_id:
        return None
    return _read_payload(
        root / "data" / "analysis" / "runs" / snapshot_id / analysis_id / "context.json"
    )


def re_safe_component(value: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-_")


def load_agent_analysis(
    root: Path,
    *,
    snapshot_run_id: str,
    analysis_allowed: bool,
    metrics: dict[str, dict[str, Any]],
    proxy: dict[str, Any],
) -> dict[str, Any]:
    """Load a verified Agent artifact without ever blocking deterministic data."""
    if not analysis_allowed:
        return _base(
            "blocked_by_data",
            "关键数据没有通过检查，所以今天不让 Agent 生成新分析。数据页面会说明具体原因。",
        )

    analysis_path = root / "data" / "analysis" / "latest.json"
    release_stage = "production"
    if not analysis_path.exists():
        policy = _read_payload(root / "config" / "agent-dashboard-policy.json") or {}
        if (
            policy.get("enabled") is True
            and policy.get("display_mode") == "pilot_shadow"
        ):
            analysis_path = root / "data" / "analysis" / "shadow" / "latest.json"
            release_stage = "pilot"
    payload = _read_payload(analysis_path)
    if payload is None:
        return _base(
            "setup_pending",
            "Agent 还没有生成这一轮分析。官方数据和公式仍会更新，页面不会用固定文案冒充分析。",
        )

    if payload.get("snapshot_run_id") != snapshot_run_id:
        result = _base(
            "stale",
            "最新数据已经更新，但 Agent 还没完成这一轮分析。旧分析不会冒充今天的判断。",
        )
        result.update(
            {
                "generated_at": payload.get("generated_at"),
                "snapshot_run_id": payload.get("snapshot_run_id"),
                "release_stage": release_stage,
            }
        )
        return result

    bundle_id = payload.get("context_bundle_id")
    bundle = load_context_bundle(root, bundle_id) if bundle_id != "context-unavailable" else None
    context_items = {
        item["context_id"]: item
        for item in (bundle or {}).get("past_24h", []) + (bundle or {}).get("future_90d", [])
        if isinstance(item, dict) and isinstance(item.get("context_id"), str)
    }
    analysis_context = _analysis_context(root, payload)
    if not analysis_context:
        sidecar = _read_payload(analysis_path.with_name("latest-context.json"))
        if (
            sidecar
            and sidecar.get("snapshot_run_id") == payload.get("snapshot_run_id")
            and sidecar.get("analysis_id") == payload.get("analysis_id")
        ):
            analysis_context = sidecar
    analysis_context = analysis_context or {}
    analysis_delta = analysis_context.get("analysis_delta")
    errors = _validate_payload(
        payload,
        metrics,
        proxy,
        context_items,
        analysis_delta if isinstance(analysis_delta, dict) else None,
    )
    if errors:
        result = _base(
            "invalid",
            "Agent 已生成内容，但证据校验没有通过，所以这份分析没有发布。",
        )
        result["validation_errors"] = errors
        result["release_stage"] = release_stage
        return result

    result = dict(payload)
    if release_stage == "pilot":
        result["state"] = (
            "pilot_ready" if payload["status"] == "ready" else "pilot_limited"
        )
    else:
        result["state"] = "ready" if payload["status"] == "ready" else "limited"
    result["release_stage"] = release_stage
    result["is_current"] = True
    result["message"] = (
        "Agent 已完成本轮分析，数字和日期已核对。"
        if payload["status"] == "ready"
        else "Agent 已完成分析，但证据不足，只显示能确认的部分。"
    )
    enriched_context = []
    for assessment in result.get("context_assessments", []):
        source_item = context_items.get(assessment.get("context_id"), {})
        enriched_context.append(
            {
                **assessment,
                "kind": source_item.get("kind"),
                "category": source_item.get("category"),
                "title": source_item.get("title"),
                "source_id": source_item.get("source_id"),
                "source_name": source_item.get("source_name"),
                "url": source_item.get("url"),
                "published_at": source_item.get("published_at"),
                "starts_at": source_item.get("starts_at"),
                "content_status": source_item.get("content_status"),
                "release_type": source_item.get("release_type"),
                "reference_period": source_item.get("reference_period"),
            }
        )
    result["context_assessments"] = enriched_context
    result["context_status"] = (bundle or {}).get("status", "unavailable")
    result["context_counts"] = {
        "past_24h": len((bundle or {}).get("past_24h", [])),
        "future_90d": len((bundle or {}).get("future_90d", [])),
    }
    return result
