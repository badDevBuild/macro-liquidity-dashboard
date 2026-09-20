#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_channel import run_channel  # noqa: E402
from liquidity_channel.core import ChannelError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch, validate and atomically publish macro-liquidity data."
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=PROJECT_ROOT / "config" / "sources.json",
    )
    parser.add_argument(
        "--policy",
        type=Path,
        default=PROJECT_ROOT / "config" / "publication_policy.json",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=PROJECT_ROOT / "data",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Ignore environment HTTP proxy settings for this run.",
    )
    parser.add_argument(
        "--transport",
        choices=("curl", "urllib"),
        default="curl",
        help="HTTP transport. curl is the production default because its deadlines are bounded.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    def progress(event: dict[str, object]) -> None:
        if event["event"] == "source_start":
            print(
                f"[{event['index']}/{event['total']}] fetching {event['source_id']}...",
                file=sys.stderr,
                flush=True,
            )
        else:
            suffix = f" observed={event['observed_at']}" if event.get("observed_at") else ""
            error = event.get("error")
            if error:
                error_text = str(error).replace("\n", " ")[:180]
                suffix += f" error={error_text}"
            print(
                f"[{event['index']}/{event['total']}] {event['source_id']} "
                f"status={event['quality_status']}{suffix}",
                file=sys.stderr,
                flush=True,
            )

    try:
        snapshot = run_channel(
            args.sources.resolve(),
            args.policy.resolve(),
            args.data_dir.resolve(),
            direct=args.direct,
            transport=args.transport,
            progress=progress,
        )
    except ChannelError as exc:
        print(
            json.dumps(
                {"status": "channel_error", "error": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 3
    publication = snapshot["publication"]
    print(
        json.dumps(
            {
                "run_id": snapshot["run_id"],
                "status": publication["status"],
                "analysis_allowed": publication["analysis_allowed"],
                "coverage_ratio": publication["coverage_ratio"],
                "eligible_metric_count": publication["eligible_metric_count"],
                "unavailable_metric_count": publication["unavailable_metric_count"],
                "latest_status": str(args.data_dir / "status" / "latest-run.json"),
                "latest_snapshot": str(args.data_dir / "snapshots" / "latest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if publication["analysis_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
