from __future__ import annotations

import csv
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_dashboard.yen_carry_channel import (  # noqa: E402
    YenCarryChannelError,
    align_spread,
    build_yen_carry_payload,
    parse_boj_series,
    parse_cftc_jpy_zip,
    parse_ecb_usd_jpy,
    parse_jsda_archive,
    parse_jsda_jgb_2y,
    realized_volatility,
)


UTC = timezone.utc


class YenCarryParserTests(unittest.TestCase):
    def test_ecb_cross_builds_usd_jpy_from_common_dates(self) -> None:
        body = (
            "CURRENCY,TIME_PERIOD,OBS_VALUE\n"
            "USD,2026-08-31,1.20\n"
            "JPY,2026-08-31,180.00\n"
            "USD,2026-09-01,1.25\n"
            "JPY,2026-09-01,181.25\n"
        ).encode()
        points = parse_ecb_usd_jpy(
            body, now=datetime(2026, 9, 2, tzinfo=UTC)
        )
        self.assertEqual(
            [(item["observed_at"], item["value"]) for item in points],
            [("2026-08-31", 150.0), ("2026-09-01", 145.0)],
        )

    def test_boj_ignores_future_null_but_rejects_future_value(self) -> None:
        base = {
            "STATUS": 200,
            "RESULTSET": [
                {
                    "SERIES_CODE": "STRDCLUCON",
                    "VALUES": {
                        "SURVEY_DATES": [20260901, 20260905],
                        "VALUES": [0.5, None],
                    },
                }
            ],
        }
        parsed = parse_boj_series(
            json.dumps(base).encode(),
            expected_codes={"STRDCLUCON"},
            now=datetime(2026, 9, 2, tzinfo=UTC),
        )
        self.assertEqual(parsed["STRDCLUCON"][-1]["observed_at"], "2026-09-01")
        base["RESULTSET"][0]["VALUES"]["VALUES"][1] = 0.6
        with self.assertRaisesRegex(YenCarryChannelError, "future value"):
            parse_boj_series(
                json.dumps(base).encode(),
                expected_codes={"STRDCLUCON"},
                now=datetime(2026, 9, 2, tzinfo=UTC),
            )

    def test_cftc_uses_leveraged_short_minus_long(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "FinFut26.txt",
                "Report_Date_as_YYYY-MM-DD,CFTC_Contract_Market_Code,"
                "Lev_Money_Positions_Long_All,Lev_Money_Positions_Short_All\n"
                "2026-08-25,097741,20000,65000\n",
            )
        points = parse_cftc_jpy_zip(
            buffer.getvalue(),
            contract_code="097741",
            now=datetime(2026, 9, 1, tzinfo=UTC),
        )
        self.assertEqual(points[0]["value"], 45000.0)

    def test_jsda_selects_latest_eligible_file_and_nearest_two_year_issue(self) -> None:
        page = b'<a href="./files/2026/ES260831.csv">old</a><a href="./files/2026/ES260901.csv">new</a>'
        relative, published = parse_jsda_archive(
            page, now=datetime(2026, 9, 1, tzinfo=UTC)
        )
        self.assertEqual(relative, "./files/2026/ES260901.csv")
        rows = [
            ["20260901", "02", "004880042", "JGB488(2)", "20280901", "1.7", "1.725"],
            ["20260901", "02", "004890042", "JGB489(2)", "20290501", "1.7", "1.800"],
        ]
        text = io.StringIO()
        writer = csv.writer(text)
        writer.writerows(rows)
        point = parse_jsda_jgb_2y(
            text.getvalue().encode(), publication_date=published
        )
        self.assertEqual(point["issue"], "JGB488(2)")
        self.assertEqual(point["value"], 1.725)

    def test_jsda_accepts_official_cp932_csv(self) -> None:
        row = "20260901,02,004880042,\"JGB488(2)\",20280901,1.7,1.725,\"（注）\"\n"
        point = parse_jsda_jgb_2y(
            row.encode("cp932"), publication_date=date(2026, 9, 1)
        )
        self.assertEqual(point["value"], 1.725)


class YenCarryCalculationTests(unittest.TestCase):
    def test_realized_volatility_and_spread_are_deterministic(self) -> None:
        start = date(2026, 7, 1)
        fx = [
            {
                "observed_at": (start + timedelta(days=index)).isoformat(),
                "value": 150.0 + (index % 3) * 0.5,
            }
            for index in range(25)
        ]
        self.assertEqual(len(realized_volatility(fx, window=20)), 5)
        spread = align_spread(
            [{"observed_at": "2026-09-01", "value": 4.1}],
            [{"observed_at": "2026-08-31", "value": 0.6}],
            first_key="us",
            second_key="jp",
        )
        self.assertEqual(spread[0]["value"], 3.5)
        self.assertEqual(spread[0]["component_dates"]["jp"], "2026-08-31")

    def test_payload_keeps_carry_states_outside_net_liquidity_formula(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            connection = sqlite3.connect(root / "data" / "channel.sqlite3")
            connection.execute(
                "CREATE TABLE observations (metric_id TEXT, source_id TEXT, observed_at TEXT, value REAL)"
            )
            start = date(2026, 6, 1)
            fx = []
            call = []
            jgb = []
            cftc = []
            swap = []
            for index in range(80):
                observed = (start + timedelta(days=index)).isoformat()
                fx.append({"observed_at": observed, "value": 150 - index * 0.04})
                call.append({"observed_at": observed, "value": 0.5})
                jgb.append({"observed_at": observed, "value": 0.8})
                swap.append({"observed_at": observed, "value": 1000 + index})
                for metric_id, source_id, value in (
                    ("treasury_3m_yield", "ust", 4.0 - index * 0.002),
                    ("treasury_2y_yield", "ust", 3.7 - index * 0.001),
                ):
                    connection.execute(
                        "INSERT INTO observations VALUES (?, ?, ?, ?)",
                        (metric_id, source_id, observed, value),
                    )
                if index % 7 == 0:
                    cftc.append(
                        {"observed_at": observed, "value": 60000 - index * 100}
                    )
            connection.commit()
            connection.close()
            history = {
                "series": {
                    "usd_jpy": fx,
                    "boj_call_rate": call,
                    "jgb_2y_proxy": jgb,
                    "cftc_leveraged_net_short": cftc,
                    "fx_swap_turnover": swap,
                },
                "revisions": [],
            }
            config = {
                "ecb_fx": {"id": "ecb", "name": "ECB", "documentation_url": "https://ecb.example"},
                "boj": {
                    "documentation_url": "https://boj.example",
                    "sources": [{}, {"id": "boj-swap", "name": "BOJ swap"}],
                },
                "cftc": {"id": "cftc", "name": "CFTC", "documentation_url": "https://cftc.example"},
                "jsda": {"documentation_url": "https://jsda.example"},
            }
            health = [
                {"series_id": series_id, "quality_status": "fresh_network"}
                for series_id in (
                    "usd_jpy",
                    "boj_call_rate",
                    "jgb_2y_proxy",
                    "cftc_leveraged_net_short",
                    "fx_swap_turnover",
                )
            ]
            payload, complete = build_yen_carry_payload(
                root,
                history,
                config,
                health,
                now=datetime(2026, 8, 20, tzinfo=UTC),
                run_id="test-run",
                fetched_at="2026-08-20T00:00:00Z",
            )
            self.assertIn("carry_incentive", payload["states"])
            self.assertIn("unwind_pressure", payload["states"])
            self.assertIn("不进入美联储净流动性公式", payload["methodology"]["role"])
            self.assertTrue(payload["available_for_analysis"])
            self.assertGreater(len(complete["derived"]["short_rate_spread"]), 20)


if __name__ == "__main__":
    unittest.main()
