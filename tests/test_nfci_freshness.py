from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from liquidity_channel.core import FetchError, FetchResponse, run_channel
from liquidity_channel.nfci_schedule import nfci_freshness, release_at
from liquidity_dashboard.model import _runtime_freshness, build_dashboard
from liquidity_dashboard.agent_runtime import run_agent_analysis
from build_public_release import build_release


UTC = timezone.utc
SOURCE = next(item for item in json.loads((ROOT / "config/sources.json").read_text())["sources"]
              if item["id"] == "fred_nfci")


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def metric(observed: str = "2026-10-02", *, available: bool = True) -> dict:
    return {
        "metric_id": "nfci", "source_id": SOURCE["id"], "group": SOURCE["group"],
        "observed_at": observed, "value": -0.494, "unit": "index",
        "quality_status": "fresh_network" if available else "data_conflict",
        "available_for_analysis": available,
    }


class NFCIScheduleTests(unittest.TestCase):
    def test_every_release_in_official_2026_calendar(self) -> None:
        # Transcribed 2026-10-15 from the Chicago Fed calendar, including its
        # December 2025 entries. Friday reference dates are explicit anchors.
        release_dates = """
        2025-12-03 2025-12-10 2025-12-17 2025-12-24 2025-12-31
        2026-01-07 2026-01-14 2026-01-22 2026-01-28
        2026-02-04 2026-02-11 2026-02-19 2026-02-25
        2026-03-04 2026-03-11 2026-03-18 2026-03-25
        2026-04-01 2026-04-08 2026-04-15 2026-04-22 2026-04-29
        2026-05-06 2026-05-13 2026-05-20 2026-05-28
        2026-06-03 2026-06-10 2026-06-17 2026-06-24
        2026-07-01 2026-07-08 2026-07-15 2026-07-22 2026-07-29
        2026-08-05 2026-08-12 2026-08-19 2026-08-26
        2026-09-02 2026-09-10 2026-09-16 2026-09-23 2026-09-30
        2026-10-07 2026-10-15 2026-10-21 2026-10-28
        2026-11-04 2026-11-12 2026-11-18 2026-11-25
        2026-12-02 2026-12-09 2026-12-16 2026-12-23 2026-12-30
        """.split()
        for index, expected in enumerate(release_dates):
            reference_end = date(2025, 11, 28) + timedelta(weeks=index)
            with self.subTest(reference_end=reference_end):
                expected_at = datetime.combine(date.fromisoformat(expected), datetime.min.time(),
                                               ZoneInfo("America/New_York")).replace(hour=8, minute=30)
                self.assertEqual(release_at(reference_end), expected_at.astimezone(UTC))

    def test_normal_week_and_holiday_release_boundaries(self) -> None:
        for observed, deadline in [
            ("2026-09-25", "2026-10-07T12:30:00Z"),
            ("2026-10-02", "2026-10-15T12:30:00Z"),
            ("2026-11-27", "2026-12-09T13:30:00Z"),
            ("2026-12-25", "2027-01-06T13:30:00Z"),
        ]:
            for delta, expected in [(-1, "waiting_release"), (0, "stale"), (1, "stale")]:
                with self.subTest(observed=observed, delta=delta):
                    result = nfci_freshness(SOURCE, observed, instant(deadline) + timedelta(seconds=delta))
                    self.assertEqual(result["status"], expected)
                    self.assertEqual(result["expires_at"], deadline)

    def test_dst_and_equivalent_timezones(self) -> None:
        for observed, deadline in [
            ("2026-02-20", "2026-03-04T13:30:00Z"),
            ("2026-02-27", "2026-03-11T12:30:00Z"),
            ("2026-10-23", "2026-11-04T13:30:00Z"),
        ]:
            for zone in [UTC, ZoneInfo("America/New_York"), ZoneInfo("Asia/Shanghai")]:
                with self.subTest(observed=observed, zone=zone):
                    now = (instant(deadline) - timedelta(seconds=1)).astimezone(zone)
                    self.assertEqual(nfci_freshness(SOURCE, observed, now)["status"], "waiting_release")
        self.assertEqual(nfci_freshness(SOURCE, "2026-10-02", datetime(2026, 10, 15, 12, 30))["status"], "stale")

    def test_observation_is_never_renewed_by_later_release_or_refetch(self) -> None:
        for now in ["2026-10-15T12:30:00Z", "2026-10-22T00:00:00Z", "2027-05-10T00:00:00Z"]:
            result = nfci_freshness(SOURCE, "2026-10-02", instant(now))
            self.assertEqual(result["status"], "stale")
            self.assertEqual(result["expires_at"], "2026-10-15T12:30:00Z")

    def test_new_reference_period_is_not_available_before_its_release(self) -> None:
        self.assertEqual(nfci_freshness(SOURCE, "2026-10-09", instant("2026-10-15T12:29:59Z"))["status"], "stale")
        result = nfci_freshness(SOURCE, "2026-10-09", instant("2026-10-15T12:30:00Z"))
        self.assertEqual(result["status"], "current")
        self.assertEqual(result["expires_at"], "2026-10-21T12:30:00Z")

    def test_historical_non_friday_and_other_sources_keep_age_policy(self) -> None:
        now = instant("2026-10-15T05:46:00Z")
        for observed in ["1985-12-27", "2026-10-01"]:
            self.assertIsNone(nfci_freshness(SOURCE, observed, now))
            self.assertEqual(_runtime_freshness(metric(observed), SOURCE, now=now)["runtime_freshness_status"], "stale")
        self.assertIsNone(nfci_freshness({"id": "other"}, "2026-10-02", now))
        other = _runtime_freshness(metric(), {"freshness_max_days": 12}, now=now)
        self.assertEqual(other["runtime_freshness_status"], "stale")

    def test_historical_as_of_and_publication_facts_are_preserved(self) -> None:
        original = metric()
        before = _runtime_freshness(original, SOURCE, now=instant("2026-10-15T05:46:00Z"))
        after = _runtime_freshness(original, SOURCE, now=instant("2026-10-15T12:30:00Z"))
        self.assertEqual(before["runtime_freshness_status"], "waiting_release")
        self.assertTrue(before["available_for_analysis"])
        self.assertFalse(after["available_for_analysis"])
        self.assertTrue(after["publication_available_for_analysis"])
        self.assertEqual(after["publication_quality_status"], "fresh_network")
        self.assertEqual(original, metric())
        conflicted = _runtime_freshness(metric(available=False), SOURCE, now=instant("2026-10-15T05:46:00Z"))
        self.assertFalse(conflicted["available_for_analysis"])
        self.assertEqual(conflicted["quality_status"], "data_conflict")


class Fetcher:
    def __init__(self, observed: str = "2026-10-02", *, fail: bool = False):
        self.observed = observed
        self.fail = fail

    def fetch(self, _url: str) -> FetchResponse:
        if self.fail:
            raise FetchError("test upstream unavailable")
        return FetchResponse(
            body=f"observation_date,NFCI\n{self.observed},-0.494\n".encode(),
            status_code=200, headers={}, fetched_at="2026-10-15T05:46:00Z",
            elapsed_ms=1, attempts=1,
        )


class NFCIIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        config = self.root / "config"
        config.mkdir()
        self.sources = config / "sources.json"
        self.sources.write_text(json.dumps({"sources": [SOURCE]}))
        self.policy = config / "publication-policy.json"
        self.policy.write_text(json.dumps({
            "minimum_fresh_metrics": 1, "maximum_unavailable_metrics": 0,
            "group_minimums": {"market_transmission": 1},
        }))

    def collect(self, now: str, fetcher: Fetcher) -> dict:
        return run_channel(self.sources, self.policy, self.root / "data", now=instant(now), fetcher=fetcher)

    def test_collection_cache_and_unchanged_network_expire_at_same_instant(self) -> None:
        first = self.collect("2026-10-15T05:46:00Z", Fetcher())
        self.assertEqual(first["metrics"]["nfci"]["quality_status"], "fresh_network")
        before = self.collect("2026-10-15T12:29:59Z", Fetcher(fail=True))
        self.assertEqual(before["metrics"]["nfci"]["quality_status"], "fresh_cache")
        snapshot_path = self.root / "data/snapshots/latest.json"
        published = snapshot_path.read_bytes()
        for now, fetcher, expected_status in [
            ("2026-10-15T12:30:00Z", Fetcher(), "stale_source"),
            ("2026-10-15T12:30:00.000001Z", Fetcher(fail=True), "stale_fallback"),
        ]:
            after = self.collect(now, fetcher)
            self.assertFalse(after["publication"]["analysis_allowed"])
            self.assertEqual(after["metrics"]["nfci"]["quality_status"], expected_status)
            self.assertEqual(snapshot_path.read_bytes(), published)
        updated = self.collect("2026-10-15T12:30:01Z", Fetcher("2026-10-09"))
        self.assertTrue(updated["publication"]["analysis_allowed"])

    def test_api_model_and_agent_gate_recheck_published_snapshot(self) -> None:
        self.collect("2026-10-15T05:46:00Z", Fetcher())
        before = build_dashboard(self.root, now=instant("2026-10-15T12:29:59Z"))
        self.assertEqual(before["status"]["data_status"]["code"], "waiting_release")
        self.assertEqual(before["status"]["data_status"]["runtime_eligible_metric_count"], 1)
        self.assertEqual(before["status"]["data_status"]["runtime_waiting_release_metric_count"], 1)
        after = build_dashboard(self.root, now=instant("2026-10-15T12:30:00Z"))
        self.assertFalse(after["status"]["analysis_allowed"])
        self.assertTrue(after["snapshot"]["publication"]["analysis_allowed"])
        invoker = Mock(side_effect=AssertionError("model must not run on expired data"))
        preflight = Mock(side_effect=AssertionError("preflight must not run on expired data"))
        blocked = run_agent_analysis(self.root, now=instant("2026-10-15T12:30:00Z"),
                                     invoker=invoker, preflight=preflight)
        self.assertEqual(blocked["state"], "blocked_by_data")
        invoker.assert_not_called()
        preflight.assert_not_called()

    def test_run_deadline_cache_path_uses_intraday_release_boundary(self) -> None:
        self.collect("2026-10-15T05:46:00Z", Fetcher())
        self.sources.write_text(json.dumps({"sources": [SOURCE], "request_policy": {"run_deadline_seconds": -1}}))
        before = self.collect("2026-10-15T12:29:59Z", Fetcher())
        after = self.collect("2026-10-15T12:30:00Z", Fetcher())
        self.assertTrue(before["metrics"]["nfci"]["available_for_analysis"])
        self.assertFalse(after["metrics"]["nfci"]["available_for_analysis"])

    def test_display_fallback_is_bounded_and_premature_row_is_not_analysed(self) -> None:
        premature = self.collect("2026-10-15T12:29:59Z", Fetcher("2026-10-09"))
        self.assertFalse(premature["publication"]["analysis_allowed"])
        self.collect("2026-10-15T05:46:00Z", Fetcher())
        expired = self.collect("2026-11-01T00:00:00Z", Fetcher(fail=True))
        self.assertEqual(expired["metrics"]["nfci"]["quality_status"], "unavailable")
        self.assertIsNone(expired["metrics"]["nfci"]["value"])

    def test_release_package_contains_calendar_logic_and_keeps_publication_facts(self) -> None:
        snapshot = self.collect("2026-10-15T05:46:00Z", Fetcher())
        for folder in ["web", "src"]:
            shutil.copytree(ROOT / folder, self.root / folder, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy2(ROOT / "pyproject.toml", self.root / "pyproject.toml")
        status = self.root / "data/status/latest-shadow-cycle.json"
        status.write_text(json.dumps({"status": "completed"}))
        output = self.root / "public-release"
        manifest = build_release(self.root, output)
        self.assertIn("src/liquidity_channel/nfci_schedule.py", {item["path"] for item in manifest["files"]})
        result = build_dashboard(output, now=instant("2026-10-15T05:46:00Z"))
        self.assertEqual(result["snapshot"]["run_id"], snapshot["run_id"])
        self.assertEqual(result["status"]["waiting_release"][0]["runtime_freshness_expires_at"], "2026-10-15T12:30:00Z")
        self.assertEqual(json.loads((output / "data/snapshots/latest.json").read_text()), snapshot)


if __name__ == "__main__":
    unittest.main()
