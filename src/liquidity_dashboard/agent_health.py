from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


UTC = timezone.utc
BEIJING = ZoneInfo("Asia/Shanghai")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _beijing_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(BEIJING).date().isoformat()


def build_agent_health(root: Path, *, required_days: int = 14) -> dict[str, Any]:
    root = root.resolve()
    records_by_date: dict[str, list[dict[str, Any]]] = {}
    status_paths = sorted(
        (root / "data" / "analysis" / "runs").glob("*/*/status.json")
    )
    for status_path in status_paths:
        status = _read_json(status_path)
        if status.get("mode") != "shadow":
            continue
        context = _read_json(status_path.parent / "context.json")
        observed_date = _beijing_date(context.get("snapshot_completed_at"))
        if not observed_date:
            continue
        records_by_date.setdefault(observed_date, []).append(
            {
                "state": status.get("state"),
                "snapshot_run_id": status.get("snapshot_run_id"),
                "analysis_id": status.get("analysis_id"),
                "completed_at": status.get("completed_at"),
                "attempts": status.get("attempts", []),
                "status_path": str(status_path),
            }
        )

    dates = sorted(records_by_date, reverse=True)[:required_days]
    date_rows: list[dict[str, Any]] = []
    for observed_date in sorted(dates):
        records = records_by_date[observed_date]
        successes = [record for record in records if record.get("state") == "shadow_ready"]
        chosen = max(
            successes or records,
            key=lambda item: str(item.get("completed_at") or ""),
        )
        attempts = chosen.get("attempts") if isinstance(chosen.get("attempts"), list) else []
        final_attempt = attempts[-1] if attempts else {}
        tokens_used = sum(
            int(attempt.get("tokens_used") or 0)
            for attempt in attempts
            if isinstance(attempt, dict)
        )
        date_rows.append(
            {
                "observed_date": observed_date,
                "success": bool(successes),
                "snapshot_run_id": chosen.get("snapshot_run_id"),
                "analysis_id": chosen.get("analysis_id"),
                "attempt_count": len(attempts),
                "first_attempt_success": bool(successes)
                and len(attempts) == 1
                and not final_attempt.get("initial_validation_errors")
                and not final_attempt.get("auto_repair_actions"),
                "recovered": bool(successes)
                and (
                    len(attempts) > 1
                    or bool(final_attempt.get("auto_repair_actions"))
                ),
                "final_validation_errors": final_attempt.get("validation_errors", []),
                "tokens_used": tokens_used,
            }
        )

    successful_dates = [row for row in date_rows if row["success"]]
    deterministic_gate_passed = (
        len(date_rows) >= required_days
        and len(successful_dates) == len(date_rows)
        and all(not row["final_validation_errors"] for row in successful_dates)
    )
    approval = _read_json(root / "config" / "agent-production-approval.json")
    approved = approval.get("approved") is True
    hard_pass = deterministic_gate_passed and approved
    if hard_pass:
        state = "hard_pass"
    elif deterministic_gate_passed:
        state = "awaiting_semantic_approval"
    else:
        state = "collecting"
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(tz=UTC).isoformat().replace("+00:00", "Z"),
        "state": state,
        "required_distinct_dates": required_days,
        "observed_distinct_dates": len(date_rows),
        "successful_distinct_dates": len(successful_dates),
        "remaining_success_dates": max(required_days - len(successful_dates), 0),
        "first_attempt_success_dates": sum(
            1 for row in successful_dates if row["first_attempt_success"]
        ),
        "retry_success_dates": sum(
            1 for row in successful_dates if not row["first_attempt_success"]
        ),
        "total_tokens_used": sum(row["tokens_used"] for row in date_rows),
        "deterministic_gate_passed": deterministic_gate_passed,
        "semantic_approval": {
            "approved": approved,
            "reviewed_at": approval.get("reviewed_at"),
            "reviewed_by": approval.get("reviewed_by"),
            "review_note": approval.get("review_note"),
        },
        "hard_pass": hard_pass,
        "dates": date_rows,
    }
