from __future__ import annotations

import sqlite3
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from liquidity_dashboard.model import _proxy_history, _proxy_view
from liquidity_dashboard.agent_runtime import _analysis_delta


class DailyProxyTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("CREATE TABLE observations(metric_id, source_id, observed_at, value, unit, revision_count)")
        self.metrics = {}
        self.add("fed_total_assets", "2026-08-19", 10000)
        self.add("fed_total_assets", "2026-08-26", 11000)
        for day, tga in [("2026-08-19", 1000), ("2026-08-20", 1100), ("2026-08-21", 1200), ("2026-08-26", 1500), ("2026-08-27", 1600)]:
            self.add("tga_daily", day, tga)
            self.add("overnight_rrp", day, 2)
        self.add("tga_weekly", "2026-08-26", 99000)

    def tearDown(self):
        self.db.close()

    def add(self, metric, day, value):
        self.db.execute("INSERT INTO observations VALUES (?,?,?,?,?,0)",
                        (metric, metric, day, value, "usd_billions" if metric == "overnight_rrp" else "usd_millions"))
        self.metrics[metric] = {"source_id": metric, "observed_at": day, "value": value}

    def history(self):
        return _proxy_history(self.db, self.metrics)

    def test_daily_tga_never_week_average_and_fed_only_changes_once(self):
        points = self.history()
        self.assertEqual([p["value"] for p in points], [7000, 6900, 6800, 7500, 7400])
        self.assertEqual(points[-1]["value"] - points[-2]["value"], -100)
        self.assertEqual(points[-1]["component_dates"]["fed_total_assets"], "2026-08-26")
        self.assertNotIn("tga_weekly", points[-1]["component_dates"])

    def test_daily_missing_and_future_snapshot_data_never_filled(self):
        self.db.execute("DELETE FROM observations WHERE metric_id='overnight_rrp' AND observed_at='2026-08-20'")
        self.db.execute("INSERT INTO observations VALUES ('tga_daily','tga_daily','2026-09-01',1,'usd_millions',0)")
        self.assertNotIn("2026-08-20", [p["observed_at"] for p in self.history()])
        self.assertEqual(self.history()[-1]["observed_at"], "2026-08-27")

    def test_no_daily_tga_means_no_proxy_not_weekly_fallback(self):
        self.db.execute("DELETE FROM observations WHERE metric_id='tga_daily'")
        self.assertEqual(self.history(), [])
        self.assertIsNone(_proxy_view(self.metrics, [])["value"])

    def test_old_fed_value_expires(self):
        self.add("tga_daily", "2026-09-10", 1000)
        self.add("overnight_rrp", "2026-09-10", 2)
        self.assertEqual(self.history()[-1]["observed_at"], "2026-08-27")

    def test_current_value_trend_and_weekly_change_reconcile(self):
        for metric, delta, prior in [("fed_total_assets",1000,"2026-08-19"), ("tga_daily",100,"2026-08-26"), ("overnight_rrp",0,"2026-08-26")]:
            self.metrics[metric].update(latest_change=delta, latest_prior_observed_at=prior)
        view = _proxy_view(self.metrics, self.history())
        self.assertEqual(view["value"], view["trend_latest_value"])
        self.assertEqual(view["week_change"], 500)
        self.assertEqual(view["week_change"], view["trend_changes"]["1w"]["change"])
        self.assertEqual(sum(c["contribution_usd_millions"] for c in view["contributions"]), 500)
        self.assertEqual(view["latest_release_change"], 900)
        self.assertEqual(sum(c["contribution_usd_millions"] for c in view["latest_release_contributions"]), 900)
        periods = {c["id"]: c["comparison_period"] for c in view["latest_release_contributions"]}
        self.assertEqual(periods["fed_total_assets"], "最近一周")
        self.assertEqual(periods["tga_daily"], "最近一个数据日")

    def test_missing_latest_component_does_not_fallback_to_week_change(self):
        self.assertIsNone(_proxy_view(self.metrics, self.history())["latest_release_change"])

    def test_default_trend_is_one_calendar_year_not_366_observations(self):
        start = date(2024, 1, 1)
        history = []
        for index in range(500):
            observed = start + timedelta(days=index * 2)
            history.append({
                "observed_at": observed.isoformat(),
                "value": 1_000 + index,
                "component_values": {
                    "fed_total_assets": 2_000,
                    "tga_daily": 500,
                    "overnight_rrp": 0.5,
                },
                "component_dates": {},
            })
        metrics = {
            metric_id: {"available_for_analysis": True, "quality_status": "fresh_network"}
            for metric_id in ("fed_total_assets", "tga_daily", "overnight_rrp")
        }
        view = _proxy_view(metrics, history)
        latest = date.fromisoformat(history[-1]["observed_at"])
        first = date.fromisoformat(view["trend"][0]["observed_at"])
        self.assertLessEqual((latest - first).days, 366)
        self.assertLess(len(view["trend"]), 366)

    def test_method_migration_is_not_reported_as_market_flow(self):
        old = {"id": "net_liquidity_proxy_weekly", "value": 7000, "observed_at": "2026-08-26"}
        new = {**old, "value": 7400, "observed_at": "2026-08-27", "methodology_version": "daily-tga-v1"}
        with patch("liquidity_dashboard.agent_runtime._previous_validated_run", return_value=({"snapshot_run_id": "old", "net_liquidity_proxy_weekly": old}, {})):
            delta = _analysis_delta(Path("."), {"snapshot_run_id": "new", "net_liquidity_proxy_weekly": new})
        self.assertEqual(delta["derived_updates"], [])


if __name__ == "__main__":
    unittest.main()
