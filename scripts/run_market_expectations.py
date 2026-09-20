#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from liquidity_dashboard.market_expectations import collect_expectations  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect optional prediction-market context.")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "market-expectations.json",
    )
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    result = collect_expectations(config, args.data_dir)
    print(
        json.dumps(
            {
                "status": result.get("status"),
                "generated_at": result.get("generated_at"),
                "ready_topic_count": sum(
                    item.get("state") == "ready" for item in result.get("topics", [])
                ),
                "topic_count": len(result.get("topics", [])),
                "warnings": result.get("warnings", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
