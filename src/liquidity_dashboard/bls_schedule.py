from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
SCHEMA_VERSION = "1.0"
RELEASE_RULES = {
    "employment_situation": "employment situation",
    "cpi": "consumer price index",
    "ppi": "producer price index",
}
FRESH_CACHE_DAYS = 7
MAX_CACHE_DAYS = 14
MAX_EVENT_HORIZON_DAYS = 120
NEAR_TERM_COVERAGE_DAYS = 45
MAX_AUTOMATIC_DATE_SHIFT_DAYS = 3


def _utc_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is not a valid ISO datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


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


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _official_bls_url(value: Any) -> bool:
    parsed = urlparse(str(value))
    return parsed.scheme == "https" and parsed.hostname in {"bls.gov", "www.bls.gov"}


def _normalized_event(event: dict[str, Any], starts: datetime) -> dict[str, Any]:
    return {
        "release_type": str(event.get("release_type", "")).strip(),
        "title": re.sub(r"\s+", " ", str(event.get("title", ""))).strip(),
        "reference_period": re.sub(
            r"\s+", " ", str(event.get("reference_period", ""))
        ).strip(),
        "starts_at": _utc_iso(starts),
        "timezone": "America/New_York",
        "source_url": str(event.get("source_url", "")).strip(),
        "source_name": "U.S. Bureau of Labor Statistics",
        "evidence_text": re.sub(
            r"\s+", " ", str(event.get("evidence_text", ""))
        ).strip(),
    }


def validate_bls_candidate(
    candidate: dict[str, Any],
    *,
    now: datetime | None = None,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current = (now or datetime.now(tz=UTC)).astimezone(UTC)
    errors: list[str] = []
    warnings: list[str] = []
    normalized: list[dict[str, Any]] = []

    if candidate.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    try:
        generated_at = _parse_datetime(candidate.get("generated_at"), "generated_at")
        if generated_at > current + timedelta(minutes=10):
            errors.append("generated_at is in the future")
        if generated_at < current - timedelta(days=7):
            errors.append("candidate is older than 7 days")
    except ValueError as exc:
        errors.append(str(exc))
        generated_at = current

    events = candidate.get("events")
    if not isinstance(events, list) or not events:
        errors.append("events must be a non-empty list")
        events = []

    seen: set[tuple[str, str]] = set()
    for index, event in enumerate(events):
        prefix = f"events[{index}]"
        if not isinstance(event, dict):
            errors.append(f"{prefix} must be an object")
            continue
        release_type = str(event.get("release_type", "")).strip()
        expected_term = RELEASE_RULES.get(release_type)
        if expected_term is None:
            errors.append(f"{prefix}.release_type is not recognized")
        title = str(event.get("title", "")).strip()
        if not title or (expected_term and expected_term not in title.lower()):
            errors.append(f"{prefix}.title does not match {release_type or 'release type'}")
        if not str(event.get("reference_period", "")).strip():
            errors.append(f"{prefix}.reference_period is required")
        if not _official_bls_url(event.get("source_url")):
            errors.append(f"{prefix}.source_url must be an official BLS https URL")
        if event.get("timezone") != "America/New_York":
            errors.append(f"{prefix}.timezone must be America/New_York")
        try:
            starts = _parse_datetime(event.get("starts_at"), f"{prefix}.starts_at")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not current - timedelta(days=1) <= starts <= current + timedelta(
            days=MAX_EVENT_HORIZON_DAYS
        ):
            errors.append(f"{prefix}.starts_at is outside the accepted horizon")
        local_starts = starts.astimezone(NEW_YORK)
        if (local_starts.hour, local_starts.minute) != (8, 30):
            errors.append(f"{prefix}.starts_at must be 08:30 America/New_York")
        evidence = str(event.get("evidence_text", "")).strip()
        month_token = local_starts.strftime("%b").lower()
        if (
            len(evidence) < 35
            or "08:30" not in evidence
            or str(local_starts.year) not in evidence
            or month_token not in evidence.lower()
        ):
            errors.append(f"{prefix}.evidence_text does not support the date and time")
        key = (release_type, starts.isoformat())
        if key in seen:
            errors.append(f"{prefix} duplicates another release type and timestamp")
        seen.add(key)
        normalized.append(_normalized_event(event, starts))

    near_types = {
        event["release_type"]
        for event in normalized
        if current <= _parse_datetime(event["starts_at"], "starts_at")
        <= current + timedelta(days=NEAR_TERM_COVERAGE_DAYS)
    }
    missing_near = set(RELEASE_RULES) - near_types
    if missing_near:
        errors.append(
            "near-term coverage is missing: " + ", ".join(sorted(missing_near))
        )

    if prior and isinstance(prior.get("events"), list):
        prior_by_key = {
            (
                str(event.get("release_type", "")),
                str(event.get("reference_period", "")).strip().lower(),
            ): event
            for event in prior["events"]
            if isinstance(event, dict)
        }
        current_by_key = {
            (event["release_type"], event["reference_period"].lower()): event
            for event in normalized
        }
        for key, old_event in prior_by_key.items():
            try:
                old_starts = _parse_datetime(old_event.get("starts_at"), "prior.starts_at")
            except ValueError:
                continue
            if not current <= old_starts <= current + timedelta(
                days=NEAR_TERM_COVERAGE_DAYS
            ):
                continue
            new_event = current_by_key.get(key)
            if new_event is None:
                warnings.append(
                    f"near-term {key[0]} {key[1]} disappeared from the candidate"
                )
                continue
            new_starts = _parse_datetime(new_event["starts_at"], "starts_at")
            shift_days = abs((new_starts - old_starts).total_seconds()) / 86400
            if shift_days > MAX_AUTOMATIC_DATE_SHIFT_DAYS:
                warnings.append(
                    f"near-term {key[0]} {key[1]} moved by {shift_days:.1f} days"
                )

    status = "invalid" if errors else ("needs_review" if warnings else "valid")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "checked_at": _utc_iso(current),
        "candidate_id": candidate.get("candidate_id"),
        "candidate_generated_at": _utc_iso(generated_at),
        "event_count": len(normalized),
        "errors": errors,
        "warnings": warnings,
        "events": sorted(normalized, key=lambda item: item["starts_at"]),
    }


def promote_bls_candidate(
    root: Path,
    candidate_path: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    current = (now or datetime.now(tz=UTC)).astimezone(UTC)
    candidate_payload = _load_json(candidate_path)
    if candidate_payload is None:
        raise ValueError(f"candidate is not valid JSON: {candidate_path}")
    base = root / "data" / "context" / "schedules" / "bls"
    serialized = json.dumps(
        candidate_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    stamp = current.strftime("%Y%m%dT%H%M%SZ")
    archived_candidate = base / "candidates" / f"{stamp}-{digest[:12]}.json"
    _atomic_json(archived_candidate, candidate_payload)

    prior = _load_json(base / "latest.json")
    validation = validate_bls_candidate(
        candidate_payload,
        now=current,
        prior=prior,
    )
    validation["candidate_sha256"] = digest
    validation["candidate_ref"] = str(archived_candidate.relative_to(root))
    validation_path = base / "validation" / f"{stamp}-{digest[:12]}.json"
    _atomic_json(validation_path, validation)
    _atomic_json(base / "validation" / "latest.json", validation)

    result = {
        "status": validation["status"],
        "promoted": False,
        "candidate_sha256": digest,
        "candidate_ref": str(archived_candidate.relative_to(root)),
        "validation_ref": str(validation_path.relative_to(root)),
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "event_count": validation["event_count"],
    }
    if validation["status"] != "valid":
        return result

    schedule_id = f"bls-{stamp}-{digest[:8]}"
    verified = {
        "schema_version": SCHEMA_VERSION,
        "schedule_id": schedule_id,
        "status": "verified",
        "verified_at": _utc_iso(current),
        "candidate_id": candidate_payload.get("candidate_id"),
        "candidate_generated_at": validation["candidate_generated_at"],
        "candidate_sha256": digest,
        "producer": candidate_payload.get("producer", {}),
        "source_name": "U.S. Bureau of Labor Statistics",
        "events": validation["events"],
        "validation": {
            "checked_at": validation["checked_at"],
            "event_count": validation["event_count"],
            "warnings": validation["warnings"],
        },
    }
    verified_path = base / "verified" / f"{schedule_id}.json"
    _atomic_json(verified_path, verified)
    _atomic_json(base / "latest.json", verified)
    result.update(
        {
            "status": "verified",
            "promoted": True,
            "schedule_id": schedule_id,
            "verified_ref": str(verified_path.relative_to(root)),
        }
    )
    return result


def load_verified_bls_schedule(
    root: Path, *, now: datetime | None = None
) -> dict[str, Any]:
    current = (now or datetime.now(tz=UTC)).astimezone(UTC)
    path = root.resolve() / "data" / "context" / "schedules" / "bls" / "latest.json"
    payload = _load_json(path)
    if payload is None:
        return {
            "status": "unavailable",
            "usable": False,
            "age_days": None,
            "verified_at": None,
            "events": [],
            "error": "no verified BLS schedule cache",
        }
    try:
        verified_at = _parse_datetime(payload.get("verified_at"), "verified_at")
    except ValueError as exc:
        return {
            "status": "invalid_cache",
            "usable": False,
            "age_days": None,
            "verified_at": payload.get("verified_at"),
            "events": [],
            "error": str(exc),
        }
    if verified_at > current + timedelta(minutes=10):
        return {
            "status": "invalid_cache",
            "usable": False,
            "age_days": None,
            "verified_at": _utc_iso(verified_at),
            "events": [],
            "error": "verified_at is in the future",
        }
    age_days = max(0, (current.date() - verified_at.date()).days)
    if age_days <= FRESH_CACHE_DAYS:
        status, usable = "verified_cache", True
    elif age_days <= MAX_CACHE_DAYS:
        status, usable = "stale_verified_cache", True
    else:
        status, usable = "expired", False
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    return {
        "status": status,
        "usable": usable,
        "age_days": age_days,
        "verified_at": _utc_iso(verified_at),
        "schedule_id": payload.get("schedule_id"),
        "source_name": payload.get("source_name"),
        "events": events if usable else [],
        "error": None if usable else "verified BLS schedule cache is older than 14 days",
    }
