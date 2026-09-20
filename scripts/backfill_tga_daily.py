#!/usr/bin/env python3
"""Bounded, auditable official daily TGA backfill. Does not publish a snapshot."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from liquidity_channel.core import (
    ChannelStore, CurlFetcher, atomic_write_json, iso_z, utc_now,
    parse_treasury_tga, validate_observations,
)


def backfill(root: Path, *, direct: bool = False) -> dict:
    config = json.loads((root / "config/sources.json").read_text())
    source = next(s for s in config["sources"] if s["id"] == "treasury_tga_daily")
    fetcher = CurlFetcher({**config["request_policy"], "timeout_seconds": 45}, direct=direct)
    now = utc_now()
    run_id = "tga-backfill-" + now.strftime("%Y%m%dT%H%M%SZ")
    store = ChannelStore(root / "data")
    try:
        parts = urlsplit(source["url"])
        query = dict(parse_qsl(parts.query))
        query.update({"sort": "record_date", "page[size]": "1000"})
        batches, all_dates = [], set()
        expected_count = None
        for page in range(1, 21):
            query["page[number]"] = str(page)
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
            response = fetcher.fetch(url)
            digest, raw_path = store.save_raw({**source, "url": url}, run_id, response)
            payload = json.loads(response.body)
            meta = payload["meta"]
            if expected_count is None:
                expected_count = int(meta["total-count"])
            elif expected_count != int(meta["total-count"]):
                raise ValueError("Treasury changed during pagination; retry the backfill")
            rows = validate_observations(parse_treasury_tga(response.body, source), source, now.date())
            dates = {r.observed_at for r in rows}
            if len(dates) != len(rows) or dates & all_dates:
                raise ValueError("duplicate TGA dates; no history imported")
            all_dates |= dates
            batches.append((rows, digest, response.fetched_at, raw_path))
            if page >= int(meta["total-pages"]):
                break
        if len(all_dates) != expected_count:
            raise ValueError("incomplete TGA pagination; no history imported")
        revisions = sum(store.upsert_observations(rows, run_id, seen, digest)
                        for rows, digest, seen, _ in batches)
        receipt = {"run_id": run_id, "status": "verified", "count": len(all_dates),
                   "first_observed_at": min(all_dates), "last_observed_at": max(all_dates),
                   "revisions": revisions, "raw_refs": [b[3] for b in batches],
                   "completed_at": iso_z(utc_now()), "snapshot_changed": False}
        atomic_write_json(root / "data/status/latest-tga-backfill.json", receipt)
        return receipt
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direct", action="store_true")
    args = parser.parse_args()
    print(json.dumps(backfill(ROOT, direct=args.direct), ensure_ascii=False, indent=2))
