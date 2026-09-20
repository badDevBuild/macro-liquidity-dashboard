#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from liquidity_dashboard.agent_runtime import (  # noqa: E402
    DEFAULT_MAX_ATTEMPTS,
    run_agent_analysis,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one evidence-checked Codex subscription analysis."
    )
    parser.add_argument("--mode", choices=("shadow", "publish"), default="shadow")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=480)
    parser.add_argument(
        "--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS
    )
    parser.add_argument(
        "--codex-cli",
        type=Path,
        default=Path.home() / ".local" / "bin" / "codex",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_agent_analysis(
        ROOT,
        publish=args.mode == "publish",
        force=args.force,
        timeout_seconds=args.timeout_seconds,
        max_attempts=args.max_attempts,
        cli_path=args.codex_cli,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("state") in {
        "shadow_ready",
        "published",
        "skipped_current",
        "blocked_by_data",
        "already_running",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
