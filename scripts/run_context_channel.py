#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from liquidity_dashboard.context_channel import collect_context  # noqa: E402


def main() -> int:
    bundle = collect_context(ROOT)
    print(
        json.dumps(
            {
                "bundle_id": bundle["bundle_id"],
                "status": bundle["status"],
                "past_24h_count": len(bundle["past_24h"]),
                "future_90d_count": len(bundle["future_90d"]),
                "failed_sources": [
                    item["source_id"]
                    for item in bundle["source_health"]
                    if item["status"] != "ok"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if bundle["status"] != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
