#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from liquidity_dashboard.bls_schedule import promote_bls_candidate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a BLS schedule candidate and promote it only after a hard pass."
    )
    parser.add_argument(
        "--candidate",
        type=Path,
        default=ROOT / "data" / "context" / "schedules" / "bls" / "candidate.json",
    )
    args = parser.parse_args()
    result = promote_bls_candidate(ROOT, args.candidate)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("promoted") else 2


if __name__ == "__main__":
    raise SystemExit(main())
