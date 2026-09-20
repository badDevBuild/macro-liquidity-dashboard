from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_dashboard.bls_schedule import (  # noqa: E402
    load_verified_bls_schedule,
    promote_bls_candidate,
    validate_bls_candidate,
)


UTC = timezone.utc


def candidate(now: datetime) -> dict:
    events = []
    definitions = [
        (
            "employment_situation",
            "Employment Situation for August 2026",
            "August 2026",
            "2026-09-04T12:30:00Z",
            "https://www.bls.gov/schedule/news_release/empsit.htm",
            "BLS schedule lists Sep. 04, 2026 at 08:30 AM for the August 2026 Employment Situation.",
        ),
        (
            "cpi",
            "Consumer Price Index for August 2026",
            "August 2026",
            "2026-09-11T12:30:00Z",
            "https://www.bls.gov/schedule/news_release/cpi.htm",
            "BLS schedule lists Sep. 11, 2026 at 08:30 AM for the August 2026 Consumer Price Index.",
        ),
        (
            "ppi",
            "Producer Price Index for August 2026",
            "August 2026",
            "2026-09-10T12:30:00Z",
            "https://www.bls.gov/schedule/news_release/ppi.htm",
            "BLS schedule lists Sep. 10, 2026 at 08:30 AM for the August 2026 Producer Price Index.",
        ),
    ]
    for release_type, title, reference_period, starts_at, source_url, evidence in definitions:
        events.append(
            {
                "release_type": release_type,
                "title": title,
                "reference_period": reference_period,
                "starts_at": starts_at,
                "timezone": "America/New_York",
                "source_url": source_url,
                "source_name": "U.S. Bureau of Labor Statistics",
                "evidence_text": evidence,
            }
        )
    return {
        "schema_version": "1.0",
        "candidate_id": "candidate-test",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "producer": {
            "type": "codex_scheduled_task",
            "model": "gpt-5.6-sol",
            "reasoning_effort": "medium",
        },
        "events": events,
    }


class BLSScheduleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 30, 0, tzinfo=UTC)

    def test_valid_candidate_is_promoted_and_loaded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = root / "candidate.json"
            candidate_path.write_text(json.dumps(candidate(self.now)), encoding="utf-8")
            result = promote_bls_candidate(root, candidate_path, now=self.now)
            self.assertTrue(result["promoted"])
            loaded = load_verified_bls_schedule(root, now=self.now + timedelta(days=2))
            self.assertEqual(loaded["status"], "verified_cache")
            self.assertTrue(loaded["usable"])
            self.assertEqual(len(loaded["events"]), 3)

    def test_non_official_source_is_rejected(self) -> None:
        payload = candidate(self.now)
        payload["events"][0]["source_url"] = "https://example.com/fake"
        result = validate_bls_candidate(payload, now=self.now)
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("official BLS" in error for error in result["errors"]))

    def test_all_three_release_types_are_required_in_near_window(self) -> None:
        payload = candidate(self.now)
        payload["events"] = [
            item for item in payload["events"] if item["release_type"] != "ppi"
        ]
        result = validate_bls_candidate(payload, now=self.now)
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("near-term coverage" in error for error in result["errors"]))

    def test_large_change_to_prior_near_event_requires_review(self) -> None:
        prior = candidate(self.now)
        payload = candidate(self.now)
        payload["events"][0]["starts_at"] = "2026-09-12T12:30:00Z"
        payload["events"][0]["evidence_text"] = (
            "BLS schedule lists Sep. 12, 2026 at 08:30 AM for the August 2026 Employment Situation."
        )
        result = validate_bls_candidate(payload, now=self.now, prior=prior)
        self.assertEqual(result["status"], "needs_review")
        self.assertTrue(any("moved" in warning for warning in result["warnings"]))

    def test_verified_cache_expires_after_fourteen_days(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = root / "candidate.json"
            candidate_path.write_text(json.dumps(candidate(self.now)), encoding="utf-8")
            promote_bls_candidate(root, candidate_path, now=self.now)
            loaded = load_verified_bls_schedule(root, now=self.now + timedelta(days=15))
            self.assertEqual(loaded["status"], "expired")
            self.assertFalse(loaded["usable"])


if __name__ == "__main__":
    unittest.main()
