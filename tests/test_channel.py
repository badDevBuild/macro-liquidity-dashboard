from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_channel.core import (  # noqa: E402
    FetchError,
    FetchResponse,
    Observation,
    evaluate_publication,
    parse_fred_csv,
    parse_h41_html,
    parse_treasury_tga,
    resolve_metric_outcomes,
    run_channel,
    source_as_of_date,
    validate_observations,
)


class FakeFetcher:
    def __init__(self, bodies: dict[str, bytes], failures: set[str] | None = None):
        self.bodies = bodies
        self.failures = failures or set()

    def fetch(self, url: str) -> FetchResponse:
        if url in self.failures:
            raise FetchError("simulated network failure")
        return FetchResponse(
            body=self.bodies[url],
            status_code=200,
            headers={"content-type": "text/csv"},
            fetched_at="2026-08-27T00:00:00Z",
            elapsed_ms=5,
            attempts=1,
        )


class ParserTests(unittest.TestCase):
    def test_fred_skips_missing_and_uses_latest_valid_row(self) -> None:
        source = {
            "id": "fred_test",
            "metric_id": "test_metric",
            "group": "g",
            "series_id": "TEST",
            "unit": "percent",
        }
        body = b"observation_date,TEST\n2026-08-24,3.5\n2026-08-25,.\n2026-08-26,3.7\n"
        observations = parse_fred_csv(body, source)
        self.assertEqual(observations[-1].observed_at, "2026-08-26")
        self.assertEqual(observations[-1].value, 3.7)

    def test_treasury_uses_current_closing_balance_payload_field(self) -> None:
        source = {
            "id": "treasury_tga",
            "metric_id": "tga_daily",
            "group": "fiscal_cash",
            "account_type": "Treasury General Account (TGA) Closing Balance",
            "unit": "usd_millions",
        }
        payload = {
            "data": [
                {
                    "record_date": "2026-08-25",
                    "account_type": source["account_type"],
                    "close_today_bal": "null",
                    "open_today_bal": "994137",
                }
            ]
        }
        observations = parse_treasury_tga(json.dumps(payload).encode(), source)
        self.assertEqual(observations[0].value, 994137.0)

    def test_h41_extracts_wednesday_value_from_named_row(self) -> None:
        source = {
            "id": "h41_assets",
            "metric_id": "fed_total_assets",
            "group": "fed_balance_sheet",
            "row_label": "Total assets",
            "numeric_index": 1,
            "unit": "usd_millions",
        }
        body = b"""
        <html><body><p>Wednesday Aug 19, 2026</p><table>
        <tr><td>Total assets</td><td>(0)</td><td>6,745,699</td>
        <td>- 14,256</td><td>+ 127,284</td></tr>
        </table></body></html>
        """
        observations = parse_h41_html(body, source)
        self.assertEqual(observations[0].observed_at, "2026-08-19")
        self.assertEqual(observations[0].value, 6745699.0)


class ConfigurationTests(unittest.TestCase):
    def test_broad_dollar_freshness_covers_weekly_h10_batch(self) -> None:
        registry = json.loads(
            (PROJECT_ROOT / "config" / "sources.json").read_text(encoding="utf-8")
        )
        source = next(
            item for item in registry["sources"] if item["id"] == "fred_dtwexbgs"
        )
        self.assertEqual(source["cadence"], "daily_observations_weekly_release")
        self.assertGreaterEqual(source["freshness_max_days"], 10)
        self.assertGreater(source["fallback_max_days"], source["freshness_max_days"])

    def test_iorb_uses_new_york_calendar_and_ignores_near_future_rows(self) -> None:
        registry = json.loads(
            (PROJECT_ROOT / "config" / "sources.json").read_text(encoding="utf-8")
        )
        source = next(
            item for item in registry["sources"] if item["id"] == "fred_iorb"
        )
        now = datetime(2026, 8, 30, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(source_as_of_date(source, now).isoformat(), "2026-08-29")
        observations = [
            Observation("iorb", "fred_iorb", "money_market", "2026-08-28", 3.65, "percent"),
            Observation("iorb", "fred_iorb", "money_market", "2026-08-29", 3.65, "percent"),
            Observation("iorb", "fred_iorb", "money_market", "2026-08-30", 4.25, "percent"),
        ]
        validated = validate_observations(
            observations, source, source_as_of_date(source, now)
        )
        self.assertEqual([item.observed_at for item in validated], ["2026-08-28", "2026-08-29"])
        self.assertEqual(validated[-1].value, 3.65)

    def test_generic_source_still_rejects_future_observation(self) -> None:
        source = {"id": "strict", "valid_range": [0, 10]}
        observations = [
            Observation("m", "strict", "g", "2026-08-30", 1.0, "percent")
        ]
        with self.assertRaisesRegex(Exception, "future-dated observation"):
            validate_observations(observations, source, datetime(2026, 8, 29).date())

    def test_iorb_policy_rejects_implausibly_far_future_row(self) -> None:
        source = {
            "id": "fred_iorb",
            "valid_range": [-1, 25],
            "future_observation_policy": "ignore_after_as_of",
            "future_observation_max_days": 7,
        }
        observations = [
            Observation("iorb", "fred_iorb", "g", "2026-09-20", 3.65, "percent")
        ]
        with self.assertRaisesRegex(Exception, "future-dated observation"):
            validate_observations(observations, source, datetime(2026, 8, 29).date())

    def test_iorb_policy_rejects_payload_with_only_future_rows(self) -> None:
        source = {
            "id": "fred_iorb",
            "valid_range": [-1, 25],
            "future_observation_policy": "ignore_after_as_of",
            "future_observation_max_days": 7,
        }
        observations = [
            Observation("iorb", "fred_iorb", "g", "2026-08-30", 3.65, "percent")
        ]
        with self.assertRaisesRegex(Exception, "no valid observations"):
            validate_observations(observations, source, datetime(2026, 8, 29).date())


class PublicationTests(unittest.TestCase):
    def make_outcome(self, metric: str, group: str, status: str):
        from liquidity_channel.core import SourceOutcome

        observation = Observation(metric, metric, group, "2026-08-26", 1.0, "x")
        return SourceOutcome(
            source_id=metric,
            metric_id=metric,
            group=group,
            quality_status=status,
            observation=observation if status != "unavailable" else None,
            error=None,
            attempts=1,
            elapsed_ms=1,
            fetched_at="2026-08-27T00:00:00Z",
            raw_sha256="a",
            source_url="https://example.com",
            source_name=metric,
            authority="official_primary",
            cadence="daily",
            age_days=1,
            available_for_analysis=status in {"fresh_network", "fresh_cache"},
        )

    def test_two_missing_can_publish_degraded(self) -> None:
        groups = ["a", "a", "b", "b", "c", "c"]
        outcomes = [
            self.make_outcome(
                f"m{i}",
                group,
                "unavailable" if i in {1, 3} else "fresh_network",
            )
            for i, group in enumerate(groups)
        ]
        policy = {
            "minimum_fresh_metrics": 4,
            "maximum_unavailable_metrics": 2,
            "group_minimums": {"a": 1, "b": 1, "c": 1},
            "eligible_quality_statuses": ["fresh_network", "fresh_cache"],
        }
        result = evaluate_publication(outcomes, policy)
        self.assertEqual(result["status"], "publish_degraded")
        self.assertTrue(result["analysis_allowed"])

    def test_group_quorum_blocks_even_with_high_overall_coverage(self) -> None:
        outcomes = [
            self.make_outcome("a1", "a", "unavailable"),
            self.make_outcome("a2", "a", "unavailable"),
            self.make_outcome("b1", "b", "fresh_network"),
            self.make_outcome("b2", "b", "fresh_network"),
            self.make_outcome("b3", "b", "fresh_network"),
            self.make_outcome("b4", "b", "fresh_network"),
        ]
        policy = {
            "minimum_fresh_metrics": 4,
            "maximum_unavailable_metrics": 2,
            "group_minimums": {"a": 1, "b": 1},
            "eligible_quality_statuses": ["fresh_network", "fresh_cache"],
        }
        result = evaluate_publication(outcomes, policy)
        self.assertEqual(result["status"], "block_analysis")
        self.assertFalse(result["analysis_allowed"])

    def test_same_date_source_disagreement_is_not_silently_selected(self) -> None:
        primary = self.make_outcome("metric", "g", "fresh_network")
        backup = self.make_outcome("metric", "g", "fresh_network")
        primary.source_id = "primary"
        backup.source_id = "backup"
        primary.observation = Observation("metric", "primary", "g", "2026-08-26", 10.0, "x")
        backup.observation = Observation("metric", "backup", "g", "2026-08-26", 12.0, "x")
        resolved, issues = resolve_metric_outcomes(
            [primary, backup],
            [
                {"id": "primary", "metric_id": "metric", "priority": 10},
                {"id": "backup", "metric_id": "metric", "priority": 20},
            ],
            {"reconciliation_tolerances": {"metric": 0.5}},
        )
        self.assertEqual(resolved[0].quality_status, "data_conflict")
        self.assertFalse(resolved[0].available_for_analysis)
        self.assertEqual(len(issues), 1)


class EndToEndTests(unittest.TestCase):
    def test_blocked_run_does_not_replace_published_snapshot(self) -> None:
        source = {
            "id": "fred_test",
            "name": "test",
            "metric_id": "test_metric",
            "group": "g",
            "authority": "official_primary",
            "url": "https://example.com/data.csv",
            "parser": "fred_csv",
            "series_id": "TEST",
            "unit": "percent",
            "cadence": "daily",
            "freshness_max_days": 3,
            "fallback_max_days": 5,
            "valid_range": [0, 10],
        }
        sources = {
            "request_policy": {"between_requests_seconds": 0},
            "sources": [source],
        }
        policy = {
            "minimum_fresh_metrics": 1,
            "maximum_unavailable_metrics": 0,
            "group_minimums": {"g": 1},
            "eligible_quality_statuses": ["fresh_network", "fresh_cache"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources_path = root / "sources.json"
            policy_path = root / "policy.json"
            sources_path.write_text(json.dumps(sources), encoding="utf-8")
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            body = b"observation_date,TEST\n2026-08-26,3.7\n"
            success = FakeFetcher({source["url"]: body})
            first = run_channel(
                sources_path,
                policy_path,
                root / "data",
                fetcher=success,
                now=datetime(2026, 8, 27, tzinfo=timezone.utc),
            )
            latest_path = root / "data" / "snapshots" / "latest.json"
            first_latest = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(first_latest["run_id"], first["run_id"])

            failure = FakeFetcher({}, failures={source["url"]})
            second = run_channel(
                sources_path,
                policy_path,
                root / "data",
                fetcher=failure,
                now=datetime(2026, 9, 10, tzinfo=timezone.utc),
            )
            self.assertEqual(second["publication"]["status"], "block_analysis")
            still_latest = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(still_latest["run_id"], first["run_id"])

    def test_network_failure_uses_still_fresh_cache(self) -> None:
        source = {
            "id": "fred_test",
            "name": "test",
            "metric_id": "test_metric",
            "group": "g",
            "authority": "official_primary",
            "url": "https://example.com/data.csv",
            "parser": "fred_csv",
            "series_id": "TEST",
            "unit": "percent",
            "cadence": "daily",
            "freshness_max_days": 3,
            "fallback_max_days": 5,
            "valid_range": [0, 10],
        }
        sources = {
            "request_policy": {"between_requests_seconds": 0},
            "sources": [source],
        }
        policy = {
            "minimum_fresh_metrics": 1,
            "maximum_unavailable_metrics": 0,
            "group_minimums": {"g": 1},
            "eligible_quality_statuses": ["fresh_network", "fresh_cache"],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sources_path = root / "sources.json"
            policy_path = root / "policy.json"
            sources_path.write_text(json.dumps(sources), encoding="utf-8")
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            body = b"observation_date,TEST\n2026-08-26,3.7\n"
            run_channel(
                sources_path,
                policy_path,
                root / "data",
                fetcher=FakeFetcher({source["url"]: body}),
                now=datetime(2026, 8, 27, tzinfo=timezone.utc),
            )
            second = run_channel(
                sources_path,
                policy_path,
                root / "data",
                fetcher=FakeFetcher({}, failures={source["url"]}),
                now=datetime(2026, 8, 28, tzinfo=timezone.utc),
            )
            self.assertEqual(second["metrics"]["test_metric"]["quality_status"], "fresh_cache")
            self.assertTrue(second["publication"]["analysis_allowed"])


if __name__ == "__main__":
    unittest.main()
