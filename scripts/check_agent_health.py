#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from liquidity_dashboard.agent_health import build_agent_health  # noqa: E402
from liquidity_dashboard.agent_runtime import atomic_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize the Agent shadow gate.")
    parser.add_argument("--days", type=int, default=14)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_agent_health(ROOT, required_days=args.days)
    atomic_json(ROOT / "data" / "status" / "agent-health-14d.json", payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
