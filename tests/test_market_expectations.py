from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_dashboard.market_expectations import (  # noqa: E402
    _update_history,
    normalize_event,
    select_event,
    select_featured_events,
)


class MarketExpectationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topic = {
            "topic_id": "fed_policy_distribution",
            "label": "全年美联储降息次数",
            "title_pattern": r"^How many Fed rate cuts in [0-9]{4}\?$",
            "presentation": "distribution",
            "policy_action": "cut",
            "target_year": "current",
            "require_neg_risk": True,
            "maximum_age_hours": 36,
            "minimum_liquidity_usd": 10000,
            "minimum_volume_24h_usd": 1000,
        }
        self.event = {
            "id": "51456",
            "slug": "how-many-fed-rate-cuts-in-2026",
            "title": "How many Fed rate cuts in 2026?",
            "active": True,
            "closed": False,
            "archived": False,
            "negRisk": True,
            "endDate": "2026-12-31T00:00:00Z",
            "updatedAt": "2026-08-29T10:00:00Z",
            "liquidity": 4_000_000,
            "volume24hr": 160_000,
            "markets": [
                {
                    "id": "m0",
                    "question": "Will no Fed rate cuts happen in 2026?",
                    "groupItemTitle": "0 (0 bps)",
                    "groupItemThreshold": "0",
                    "active": True,
                    "closed": False,
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.8", "0.2"]',
                    "oneDayPriceChange": -0.01,
                    "oneWeekPriceChange": 0.02,
                    "liquidityNum": 100_000,
                    "volume24hr": 50_000,
                },
                {
                    "id": "m1",
                    "question": "Will 1 Fed rate cut happen in 2026?",
                    "groupItemTitle": "1 (25 bps)",
                    "groupItemThreshold": "1",
                    "active": True,
                    "closed": False,
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.2", "0.8"]',
                    "oneDayPriceChange": 0.01,
                    "oneWeekPriceChange": -0.02,
                    "liquidityNum": 90_000,
                    "volume24hr": 40_000,
                },
            ],
        }

    def test_select_event_rejects_closed_and_expired_results(self) -> None:
        closed = {**self.event, "id": "old", "closed": True, "volume24hr": 999_999}
        selected = select_event(
            {"events": [closed, self.event]},
            self.topic,
            now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        self.assertEqual(selected["id"], "51456")

    def test_normalize_event_hides_expired_child_markets(self) -> None:
        event = json.loads(json.dumps(self.event))
        event["markets"][0]["endDate"] = "2026-08-28T00:00:00Z"
        event["markets"][1]["endDate"] = "2026-12-31T00:00:00Z"
        result = normalize_event(
            event,
            self.topic,
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        self.assertEqual([item["market_id"] for item in result["outcomes"]], ["m1"])

    def test_normalize_event_rejects_an_expired_event_even_if_active(self) -> None:
        expired = {**self.event, "endDate": "2026-08-28T00:00:00Z"}
        with self.assertRaisesRegex(Exception, "closed or expired"):
            normalize_event(
                expired,
                self.topic,
                now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
            )

    def test_featured_markets_rank_by_volume_and_limit_each_query(self) -> None:
        def event(event_id: str, volume: float, end_date: str = "2026-12-31T00:00:00Z") -> dict:
            return {
                **self.event,
                "id": event_id,
                "title": f"Macro event {event_id}",
                "endDate": end_date,
                "volume24hr": volume,
                "liquidity": 20_000,
            }

        query_a = {"query": "a", "title_pattern": "Macro event"}
        query_b = {"query": "b", "title_pattern": "Macro event"}
        selected = select_featured_events(
            [
                (query_a, {"events": [event("a1", 9000), event("a2", 8000)]}),
                (
                    query_b,
                    {"events": [event("expired", 99_000, "2026-08-28T00:00:00Z"), event("b1", 7000)]},
                ),
            ],
            {
                "max_items": 3,
                "max_items_per_query": 1,
                "minimum_liquidity_usd": 5000,
                "minimum_volume_24h_usd": 500,
            },
            excluded_event_ids=set(),
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        self.assertEqual([item[1]["id"] for item in selected], ["a1", "b1"])

    def test_nonexclusive_featured_event_keeps_multiple_markets_without_summing(self) -> None:
        event = json.loads(json.dumps(self.event))
        event["negRisk"] = False
        event["markets"][0]["outcomePrices"] = '["0.3", "0.7"]'
        event["markets"][1]["outcomePrices"] = '["0.7", "0.3"]'
        topic = {
            "topic_id": "featured_polymarket_example",
            "label": "美债区间",
            "presentation": "multi_market",
            "selection_role": "featured",
            "minimum_liquidity_usd": 0,
            "minimum_volume_24h_usd": 0,
        }
        result = normalize_event(
            event,
            topic,
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(result["presentation"], "multi_market")
        self.assertEqual(len(result["outcomes"]), 2)
        self.assertEqual(result["top_outcome"]["market_id"], "m1")
        self.assertIsNone(result["probability_sum"])

    def test_select_event_locks_policy_market_to_current_year(self) -> None:
        next_year = {
            **self.event,
            "id": "next-year",
            "title": "How many Fed rate cuts in 2027?",
            "endDate": "2027-12-31T00:00:00Z",
            "volume24hr": 9_000_000,
        }
        selected = select_event(
            {"events": [next_year, self.event]},
            self.topic,
            now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        self.assertEqual(selected["id"], "51456")

    def test_distribution_maps_yes_prices_and_preserves_market_quality(self) -> None:
        result = normalize_event(
            self.event,
            self.topic,
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(result["quality"], "liquid")
        self.assertEqual(result["display_label"], "2026 年全年美联储降息次数")
        self.assertEqual(result["top_outcome"]["label"], "0 (0 bps)")
        self.assertEqual(result["top_outcome"]["display_label"], "降息 0 次")
        self.assertEqual(result["top_outcome"]["probability"], 0.8)
        self.assertIsNone(result["expected_value"])
        self.assertEqual(result["probability_sum"], 1.0)
        self.assertEqual(result["overround_percentage_points"], 0.0)
        self.assertFalse(result["probabilities_normalized"])
        self.assertEqual(result["freshness_status"], "fresh")
        self.assertTrue(result["analysis_eligible"])
        self.assertEqual(result["outcomes"][1]["change_1d"], 0.01)

    def test_hike_distribution_preserves_overround_and_open_bucket(self) -> None:
        topic = {
            **self.topic,
            "topic_id": "fed_hike_distribution",
            "label": "全年美联储加息次数",
            "title_pattern": r"^How many Fed rate hikes in [0-9]{4}\?$",
            "policy_action": "hike",
        }
        prices = [0.26, 0.45, 0.255, 0.047, 0.0105, 0.0005]
        event = {
            **self.event,
            "id": "626860",
            "slug": "how-many-fed-rate-hikes-in-2026",
            "title": "How many Fed rate hikes in 2026?",
            "liquidity": 65_248,
            "volume24hr": 12_766,
            "markets": [
                {
                    "id": f"h{count}",
                    "question": f"Will {count} Fed rate hikes happen in 2026?",
                    "groupItemTitle": f"{count}{'+' if count == 5 else ''} ({count * 25}{'+' if count == 5 else ''} bps)",
                    "groupItemThreshold": str(count),
                    "active": True,
                    "closed": False,
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": json.dumps(
                        [str(probability), str(1 - probability)]
                    ),
                    "liquidityNum": 10_000,
                    "volume24hr": 2_000,
                }
                for count, probability in enumerate(prices)
            ],
        }
        result = normalize_event(
            event,
            topic,
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(result["display_label"], "2026 年全年美联储加息次数")
        self.assertEqual(result["top_outcome"]["display_label"], "加息 1 次")
        self.assertEqual(result["probability_sum"], 1.023)
        self.assertEqual(result["overround_percentage_points"], 2.3)
        self.assertEqual(result["outcomes"][-1]["display_label"], "加息 5 次以上")
        self.assertIsNone(result["expected_value"])

    def test_stale_policy_market_is_not_agent_eligible(self) -> None:
        stale = {**self.event, "updatedAt": "2026-08-27T00:00:00Z"}
        result = normalize_event(
            stale,
            self.topic,
            now=datetime(2026, 8, 29, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(result["freshness_status"], "stale")
        self.assertFalse(result["analysis_eligible"])

    def test_history_does_not_join_different_event_ids(self) -> None:
        history = {
            "schema_version": "1.0",
            "topics": {
                "fed_hike_distribution": [
                    {
                        "observed_at": "2025-12-31",
                        "event_id": "old-event",
                        "outcomes": {},
                    }
                ]
            },
        }
        topic = {
            "topic_id": "fed_hike_distribution",
            "state": "ready",
            "event_id": "new-event",
            "outcomes": [
                {"outcome_id": "h0", "label": "0", "probability": 0.4}
            ],
        }
        updated = _update_history(history, [topic], "2026-01-01T06:30:00Z")
        self.assertEqual(topic["history_event_id"], "new-event")
        self.assertTrue(topic["history_reset"])
        self.assertEqual(len(topic["history"]), 1)
        self.assertEqual(topic["history"][0]["event_id"], "new-event")
        self.assertEqual(len(updated["topics"]["fed_hike_distribution"]), 2)


if __name__ == "__main__":
    unittest.main()
