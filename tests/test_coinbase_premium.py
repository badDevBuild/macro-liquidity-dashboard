import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from liquidity_dashboard.coinbase_premium import (
    align_points, parse_candles, summarize, build_payload, build_history, load_payload,
)
from liquidity_channel.core import iso_z, atomic_write_json
from liquidity_dashboard.agent_analysis import expected_evidence


class PremiumTests(unittest.TestCase):
    def setUp(self):
        self.end = datetime(2026, 9, 8, 0, tzinfo=timezone.utc)

    def points(self, hours=24):
        return [{"observed_at": iso_z(self.end - timedelta(hours=hours-i-1)),
                 "btc_usd": 100., "binance_btc_usdt": 100., "usdt_usd": 1.,
                 "binance_btc_usd": 100., "raw_bp": 2., "adjusted_bp": 2.} for i in range(hours)]

    def test_fx_adjustment_and_missing_fx(self):
        p = align_points({"coinbase_btc_usd": {"a": 100, "b": 101},
                          "binance_btc_usdt": {"a": 100, "b": 100},
                          "coinbase_usdt_usd": {"a": 1.01}})
        self.assertEqual(p[0]["raw_bp"], 0)
        self.assertAlmostEqual(p[0]["adjusted_bp"], -99.009901, places=6)
        self.assertIsNone(p[1]["adjusted_bp"])
        self.assertEqual(p[1]["raw_bp"], 100)

    def test_only_closed_aligned_candles_and_no_volume_gap(self):
        start = self.end - timedelta(hours=2)
        rows = [[start.timestamp(), 90, 110, 100, 101, 2],
                [(start + timedelta(hours=1)).timestamp(), 90, 110, 100, 102, 0],
                [self.end.timestamp(), 90, 110, 100, 103, 1]]
        p = parse_candles(json.dumps(rows), "coinbase", start, self.end + timedelta(hours=1), self.end)
        self.assertEqual(p, {iso_z(start + timedelta(hours=1)): 101})
        rows[0][0] += 60
        with self.assertRaises(ValueError):
            parse_candles(json.dumps(rows), "coinbase", start, self.end, self.end)

    def test_binance_milliseconds_matches_coinbase(self):
        start = self.end - timedelta(hours=1)
        row = [start.timestamp()*1000, "99", "103", "98", "102", "4", self.end.timestamp()*1000-1]
        self.assertEqual(parse_candles(json.dumps([row]), "binance", start, self.end, self.end), {iso_z(self.end): 102})

    def test_missing_hour_never_becomes_zero_or_a_longer_streak(self):
        points = self.points()
        points.pop(-3)
        summary = summarize(points, "adjusted", self.end)
        self.assertIsNone(summary["mean_24h"])
        self.assertIsNone(summary["positive_share_24h"])
        self.assertEqual(summary["coverage_hours_24h"], 23)
        self.assertEqual(summary["streak_hours"], 2)
        self.assertTrue(summary["streak_left_censored"])
        points.pop(-2)
        self.assertIsNone(summarize(points, "adjusted", self.end)["latest_change"])

    def test_complete_window_stale_gating_and_evidence_contract(self):
        payload = build_payload(self.points(), [], self.end, "test")
        summary = payload["summaries"]["adjusted"]
        self.assertEqual(summary["mean_24h"], 2)
        self.assertEqual(summary["positive_share_24h"], 100)
        metric_id = "coinbase_premium_adjusted_bp"
        evidence = expected_evidence({"metric_id": metric_id, "comparison_window": None}, payload["metrics"], {})
        self.assertEqual(evidence["value"], 2)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            atomic_write_json(root / "data/crypto/coinbase-premium/latest.json", payload)
            stale = load_payload(root, self.end + timedelta(hours=31))
            self.assertFalse(stale["available_for_analysis"])
            self.assertIsNone(expected_evidence({"metric_id": metric_id, "comparison_window": None}, stale["metrics"], {}))

    def test_history_ranges_and_complete_daily_means(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            points = self.points(24 * 100)
            # Changing FX means the average of hourly premiums differs from a ratio of daily mean prices.
            points[-2]["adjusted_bp"] = 26
            atomic_write_json(root / "data/crypto/coinbase-premium/history.json", {"points": points})
            mid = "coinbase_premium_adjusted_bp"
            self.assertEqual(len(build_history(root, mid, "1d")["points"]), 24)
            self.assertEqual(len(build_history(root, mid, "7d")["points"]), 168)
            daily = build_history(root, mid, "3m")
            self.assertEqual(len(daily["points"]), 90)
            self.assertEqual(daily["points"][-1]["value"], 3)
            self.assertEqual(daily["points"][-1]["period_date"], "2026-09-07")
            points.pop(-2)
            atomic_write_json(root / "data/crypto/coinbase-premium/history.json", {"points": points})
            self.assertEqual(len(build_history(root, mid, "3m")["points"]), 89)
            self.assertEqual(build_history(root, "coinbase_premium_adjusted_mean_24h", "3m")["points"], [])

    def test_adjustment_missing_does_not_disable_raw(self):
        points = self.points()
        for p in points:
            p["adjusted_bp"] = None
        payload = build_payload(points, [], self.end, "test")
        self.assertTrue(payload["available_for_analysis"])
        self.assertFalse(payload["summaries"]["adjusted"]["available_for_analysis"])
        self.assertTrue(payload["summaries"]["raw"]["available_for_analysis"])


if __name__ == "__main__":
    unittest.main()
