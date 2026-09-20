#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ELIGIBLE = {"fresh_network", "fresh_cache"}
PUBLISHABLE = {"publish", "publish_degraded"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the data-channel soak window.")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--minimum-publishable-rate", type=float, default=0.90)
    parser.add_argument("--minimum-source-rate", type=float, default=0.85)
    parser.add_argument("--abandoned-after-minutes", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=max(args.days + 2, 16))
    db = sqlite3.connect(args.data_dir / "channel.sqlite3")
    db.row_factory = sqlite3.Row
    try:
        runs = db.execute(
            """
            SELECT run_id, started_at, completed_at, status, error
            FROM channel_runs
            WHERE started_at >= ?
            ORDER BY started_at ASC
            """,
            (cutoff.isoformat().replace("+00:00", "Z"),),
        ).fetchall()
        latest_by_day: dict[str, sqlite3.Row] = {}
        abandoned = []
        for run in runs:
            started = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
            day = started.date().isoformat()
            if run["status"] == "running" and now - started > timedelta(
                minutes=args.abandoned_after_minutes
            ):
                abandoned.append(run["run_id"])
            if run["status"] != "running":
                latest_by_day[day] = run

        selected_days = sorted(latest_by_day)[-args.days :]
        selected_runs = [latest_by_day[day] for day in selected_days]
        selected_ids = [run["run_id"] for run in selected_runs]
        status_counts: dict[str, int] = defaultdict(int)
        for run in selected_runs:
            status_counts[run["status"]] += 1
        publishable_days = sum(
            run["status"] in PUBLISHABLE for run in selected_runs
        )
        publishable_rate = (
            publishable_days / len(selected_runs) if selected_runs else 0.0
        )

        source_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"eligible": 0, "runs": 0}
        )
        if selected_ids:
            placeholders = ",".join("?" for _ in selected_ids)
            rows = db.execute(
                f"""
                SELECT source_id, quality_status
                FROM source_runs
                WHERE run_id IN ({placeholders})
                """,
                selected_ids,
            ).fetchall()
            for row in rows:
                source_stats[row["source_id"]]["runs"] += 1
                source_stats[row["source_id"]]["eligible"] += int(
                    row["quality_status"] in ELIGIBLE
                )
        source_rates = {
            source_id: {
                **counts,
                "eligible_rate": round(
                    counts["eligible"] / counts["runs"], 4
                )
                if counts["runs"]
                else 0.0,
            }
            for source_id, counts in sorted(source_stats.items())
        }
        low_sources = [
            source_id
            for source_id, stats in source_rates.items()
            if stats["eligible_rate"] < args.minimum_source_rate
        ]

        gate_passed = (
            len(selected_days) >= args.days
            and publishable_rate >= args.minimum_publishable_rate
            and not abandoned
            and not low_sources
        )
        result = {
            "status": "passed" if gate_passed else "not_ready",
            "as_of": now.isoformat().replace("+00:00", "Z"),
            "required_distinct_days": args.days,
            "observed_distinct_days": len(selected_days),
            "selected_days": selected_days,
            "publishable_days": publishable_days,
            "publishable_rate": round(publishable_rate, 4),
            "minimum_publishable_rate": args.minimum_publishable_rate,
            "status_counts": dict(sorted(status_counts.items())),
            "abandoned_running_runs": abandoned,
            "minimum_source_rate": args.minimum_source_rate,
            "sources_below_threshold": low_sources,
            "source_rates": source_rates,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if gate_passed else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
