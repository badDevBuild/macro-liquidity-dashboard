from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_dashboard.cross_asset_channel import (  # noqa: E402
    align_dual_series,
    align_ratio,
    build_cross_asset_payload,
    parse_coinbase_candles,
    parse_fred_sp500,
    parse_yahoo_sp500,
    return_correlation,
    sample_new_york_close,
)


class CrossAssetParserTests(unittest.TestCase):
    def test_samples_new_york_close_without_forward_fill(self) -> None:
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        candles = parse_coinbase_candles(
            json.dumps(
                [
                    [1785783600, 99, 102, 100, 101, 1],
                    [1785870000, 101, 104, 102, 103, 1],
                ]
            ).encode(),
            product_id="BTC-USD",
            now=now,
        )
        points = sample_new_york_close(
            candles,
            start_date=datetime(2026, 8, 3).date(),
            end_date=datetime(2026, 8, 4).date(),
        )
        self.assertEqual(
            [(point["observed_at"], point["value"]) for point in points],
            [("2026-08-03", 101.0), ("2026-08-04", 103.0)],
        )
        self.assertTrue(all(point["staleness_minutes"] == 0 for point in points))

    def test_paxg_can_use_recent_pre_close_trade_and_records_delay(self) -> None:
        candles = [
            {
                "started_at": "2026-08-03T17:00:00Z",
                "close": 2400.0,
            }
        ]
        points = sample_new_york_close(
            candles,
            start_date=datetime(2026, 8, 3).date(),
            end_date=datetime(2026, 8, 3).date(),
            max_staleness_hours=8,
        )
        self.assertEqual(points[0]["value"], 2400.0)
        self.assertEqual(points[0]["staleness_minutes"], 120)

    def test_fred_parser_ignores_missing_values_and_rejects_future_dates(self) -> None:
        now = datetime(2026, 8, 5, tzinfo=timezone.utc)
        points = parse_fred_sp500(
            b"observation_date,SP500\n2026-08-03,6400.1\n2026-08-04,.\n",
            series_id="SP500",
            now=now,
        )
        self.assertEqual(points, [{"observed_at": "2026-08-03", "value": 6400.1}])
        with self.assertRaisesRegex(Exception, "future observation"):
            parse_fred_sp500(
                b"observation_date,SP500\n2026-08-06,6401\n",
                series_id="SP500",
                now=now,
            )

    def test_yahoo_parser_uses_new_york_observation_date(self) -> None:
        body = json.dumps(
            {
                "chart": {
                    "result": [
                        {
                            "timestamp": [1785763800, 1785850200],
                            "indicators": {"quote": [{"close": [6400.1, None]}]},
                        }
                    ],
                    "error": None,
                }
            }
        ).encode()
        points = parse_yahoo_sp500(
            body, now=datetime(2026, 8, 5, tzinfo=timezone.utc)
        )
        self.assertEqual(points, [{"observed_at": "2026-08-03", "value": 6400.1}])


class CrossAssetCalculationTests(unittest.TestCase):
    def test_ratio_uses_only_exact_common_dates(self) -> None:
        btc = [
            {"observed_at": "2026-08-01", "value": 100},
            {"observed_at": "2026-08-02", "value": 110},
            {"observed_at": "2026-08-03", "value": 120},
        ]
        stock = [
            {"observed_at": "2026-08-01", "value": 10},
            {"observed_at": "2026-08-03", "value": 12},
        ]
        ratio = align_ratio(
            btc,
            stock,
            numerator_key="btc_usd",
            denominator_key="sp500",
        )
        self.assertEqual([item["observed_at"] for item in ratio], ["2026-08-01", "2026-08-03"])
        self.assertEqual([item["value"] for item in ratio], [10.0, 10.0])

    def test_return_correlation_uses_returns_not_levels(self) -> None:
        points = []
        first = 100.0
        second = 100.0
        for index in range(6):
            if index:
                first *= 1.01 if index % 2 else 0.99
                second *= 0.99 if index % 2 else 1.01
            points.append(
                {
                    "observed_at": f"2026-08-{index + 1:02d}",
                    "btc_usd": first,
                    "broad_dollar_index": second,
                }
            )
        correlation = return_correlation(
            points,
            first_key="btc_usd",
            second_key="broad_dollar_index",
            window=5,
        )
        self.assertAlmostEqual(correlation or 0, -1.0, places=3)

    def test_payload_labels_broad_dollar_as_not_dxy(self) -> None:
        dates = [f"2026-04-{day:02d}" for day in range(1, 10)]
        history = {
            "series": {
                "btc_usd": [
                    {"observed_at": observed, "value": 80_000 + index * 100}
                    for index, observed in enumerate(dates)
                ],
                "paxg_usd": [
                    {"observed_at": observed, "value": 3_000 + index}
                    for index, observed in enumerate(dates)
                ],
                "sp500": [
                    {"observed_at": observed, "value": 6_000 + index}
                    for index, observed in enumerate(dates)
                ],
                "broad_dollar_index": [
                    {"observed_at": observed, "value": 120 - index * 0.1}
                    for index, observed in enumerate(dates)
                ],
            },
            "revisions": [],
        }
        health = [
            {
                "series_id": series_id,
                "name": series_id,
                "quality_status": "fresh_network",
            }
            for series_id in ("btc_usd", "paxg_usd", "sp500", "broad_dollar_index")
        ]
        config = {
            "sp500": {"documentation_url": "https://example.com/sp500"},
            "coinbase": {
                "sources": [
                    {"documentation_url": "https://example.com/btc"},
                    {"documentation_url": "https://example.com/paxg"},
                ]
            },
        }
        payload, complete = build_cross_asset_payload(
            history,
            config,
            health,
            now=datetime(2026, 4, 10, tzinfo=timezone.utc),
            run_id="run-1",
            fetched_at="2026-04-10T00:00:00Z",
        )
        self.assertTrue(payload["available_for_analysis"])
        self.assertIn("不是 ICE DXY", payload["methodology"]["dollar"])
        self.assertEqual(
            len(complete["comparisons"]["btc_spx"]), len(dates)
        )
        aligned = align_dual_series(
            history["series"]["btc_usd"],
            history["series"]["broad_dollar_index"],
            first_key="btc_usd",
            second_key="broad_dollar_index",
        )
        self.assertEqual(len(aligned), len(dates))


if __name__ == "__main__":
    unittest.main()
