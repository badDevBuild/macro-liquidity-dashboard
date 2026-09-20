#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from liquidity_dashboard.cross_asset_channel import run_cross_asset_channel  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect optional BTC cross-asset comparisons without blocking macro publication."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "cross-asset-sources.json",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=ROOT / "data" / "cross-asset",
    )
    parser.add_argument("--direct", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = run_cross_asset_channel(
        ROOT,
        args.config.resolve(),
        args.data_dir.resolve(),
        direct=args.direct,
    )
    print(
        json.dumps(
            {
                "run_id": payload.get("run_id"),
                "status": payload.get("status"),
                "quality_status": payload.get("quality_status"),
                "available_for_analysis": payload.get("available_for_analysis"),
                "comparisons": {
                    key: {
                        "available_for_analysis": value.get("available_for_analysis"),
                        "observed_at": value.get("observed_at"),
                    }
                    for key, value in payload.get("comparisons", {}).items()
                    if isinstance(value, dict)
                },
                "latest_path": str(args.data_dir / "latest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if payload.get("available_for_analysis") else 2


if __name__ == "__main__":
    raise SystemExit(main())
