from __future__ import annotations

from typing import Any


PUBLIC_MODULE_STATUS_FIELDS = (
    "stablecoin_status",
    "crypto_etf_status",
    "crypto_derivatives_status",
    "cross_asset_status",
    "yen_carry_status",
    "energy_status",
    "coinbase_premium_status",
    "expectations_status",
    "context_status",
    "agent_status",
    "deploy_status",
)


def public_cycle_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the only runtime-cycle fields allowed in a public release."""
    status = str(payload.get("status") or "unknown")
    error_code = payload.get("public_error_code")
    successful_statuses = {"completed", "completed_degraded"}
    if not error_code and status not in successful_statuses | {"running"}:
        error_code = status
    modules = {
        field.removesuffix("_status"): payload.get(field)
        for field in PUBLIC_MODULE_STATUS_FIELDS
        if payload.get(field) is not None
    }
    return {
        "schema_version": "1.0",
        "cycle_id": payload.get("cycle_id") or payload.get("run_id"),
        "status": status,
        "started_at": payload.get("started_at"),
        "completed_at": payload.get("completed_at"),
        "success": status in successful_statuses,
        "error_code": error_code,
        "public_version": payload.get("deployment_release_id")
        or payload.get("run_id"),
        "modules": modules,
    }
