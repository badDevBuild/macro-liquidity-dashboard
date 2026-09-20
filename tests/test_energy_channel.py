from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_dashboard.energy_channel import (  # noqa: E402
    _change,
    _spread,
    parse_eia_series,
    parse_fred_series,
)


class EnergyChannelTests(unittest.TestCase):
    def test_fred_parser_keeps_missing_values_missing_and_rejects_future(self) -> None:
        now = datetime(2026, 9, 17, tzinfo=timezone.utc)
        points = parse_fred_series(
            b"observation_date,DCOILWTICO\n2026-09-14,105.2\n2026-09-15,.\n",
            series_id="DCOILWTICO",
            now=now,
        )
        self.assertEqual(points, [{"observed_at": "2026-09-14", "value": 105.2}])
        with self.assertRaisesRegex(Exception, "future observation"):
            parse_fred_series(
                b"observation_date,DCOILWTICO\n2026-09-18,106\n",
                series_id="DCOILWTICO",
                now=now,
            )

    def test_eia_parser_selects_exact_series_and_rejects_future(self) -> None:
        now = datetime(2026, 9, 17, tzinfo=timezone.utc)
        body = json.dumps({"response": {"data": [
            {"period": "2026-09-11", "series": "WCESTUS1", "value": "423429"},
            {"period": "2026-09-11", "series": "OTHER", "value": "1"},
        ]}}).encode()
        self.assertEqual(
            parse_eia_series(body, series_id="WCESTUS1", now=now),
            [{"observed_at": "2026-09-11", "value": 423429.0}],
        )
        future = json.dumps({"response": {"data": [
            {"period": "2026-09-18", "series": "WCESTUS1", "value": "1"}
        ]}}).encode()
        with self.assertRaisesRegex(Exception, "future observation"):
            parse_eia_series(future, series_id="WCESTUS1", now=now)

    def test_spread_uses_only_common_dates(self) -> None:
        wti = [
            {"observed_at": "2026-09-14", "value": 100},
            {"observed_at": "2026-09-15", "value": 102},
        ]
        brent = [
            {"observed_at": "2026-09-14", "value": 110},
            {"observed_at": "2026-09-16", "value": 115},
        ]
        self.assertEqual(
            _spread(wti, brent),
            [{"observed_at": "2026-09-14", "value": 10.0, "wti": 100.0, "brent": 110.0}],
        )

    def test_weekly_change_uses_nearest_observation_on_or_before(self) -> None:
        points = [
            {"observed_at": "2026-09-04", "value": 424000},
            {"observed_at": "2026-09-11", "value": 423000},
        ]
        change = _change(points, 7)
        self.assertEqual(change["change"], -1000.0)
        self.assertEqual(change["prior_observed_at"], "2026-09-04")


if __name__ == "__main__":
    unittest.main()
