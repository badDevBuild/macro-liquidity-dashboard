#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from liquidity_dashboard.coinbase_premium import run_channel

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--direct", action="store_true")
    args = parser.parse_args()
    result = run_channel(ROOT, direct=args.direct)
    print(json.dumps({k: result[k] for k in ("run_id", "status", "quality", "summaries")}, ensure_ascii=False, indent=2))
    sys.exit(0 if result["available_for_analysis"] else 2)
