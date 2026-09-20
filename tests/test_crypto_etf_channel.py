from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_channel.core import FetchResponse  # noqa: E402
from liquidity_dashboard.crypto_etf_channel import run_crypto_etf_channel  # noqa: E402


class FakeEtfFetcher:
    def __init__(self, rows: dict[str, list[dict]]):
        self.rows = rows
        self.headers: list[dict[str, str]] = []

    def fetch(self, url: str, *, headers: dict[str, str] | None = None) -> FetchResponse:
        self.headers.append(headers or {})
        symbol = parse_qs(urlparse(url).query)["symbol"][0]
        return FetchResponse(
            body=json.dumps(
                {"code": 0, "message": "success", "data": self.rows[symbol]}
            ).encode(),
            status_code=200,
            headers={"content-type": "application/json"},
            fetched_at="2026-08-31T12:00:00Z",
            elapsed_ms=5,
            attempts=1,
        )


def fixture_config() -> dict:
    return {
        "schema_version": "1.0",
        "credential": {
            "env_var": "SOSOVALUE_API_KEY",
            "keychain_service": "",
        },
        "request_policy": {},
        "source": {
            "id": "sosovalue_us_crypto_etf",
            "name": "SoSoValue US Crypto ETF OpenAPI",
            "source_owner": "SoSoValue",
            "authority": "trusted_specialist",
            "cadence": "us_trading_daily_t_plus_1",
            "base_url": "https://example.com/openapi/v1",
            "summary_history_path": "/etfs/summary-history",
            "documentation_url": "https://example.com/docs",
            "country_code": "US",
            "request_limit": 50,
            "freshness_max_calendar_days": 5,
            "cache_max_calendar_days": 5,
            "assets": [
                {"symbol": "BTC", "label": "Bitcoin"},
                {"symbol": "ETH", "label": "Ethereum"},
                {"symbol": "SOL", "label": "Solana"},
            ],
        },
        "cross_checks": [],
    }


def fixture_rows() -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for index, symbol in enumerate(("BTC", "ETH", "SOL"), start=1):
        scale = index * 100_000_000
        result[symbol] = [
            {
                "date": "2026-08-30",
                "total_net_inflow": None,
                "total_value_traded": 9 * scale,
                "total_net_assets": 90 * scale,
                "cum_net_inflow": 12 * scale,
            },
            {
                "date": "2026-08-28",
                "total_net_inflow": -scale,
                "total_value_traded": 2 * scale,
                "total_net_assets": 80 * scale,
                "cum_net_inflow": 10 * scale,
            },
            {
                "date": "2026-08-29",
                "total_net_inflow": 2 * scale,
                "total_value_traded": 3 * scale,
                "total_net_assets": 82 * scale,
                "cum_net_inflow": 12 * scale,
            },
        ]
    return result


class CryptoEtfChannelTests(unittest.TestCase):
    def test_sorts_rows_and_uses_only_latest_settled_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(fixture_config()), encoding="utf-8")
            fetcher = FakeEtfFetcher(fixture_rows())
            payload = run_crypto_etf_channel(
                config_path,
                root / "data",
                fetcher=fetcher,
                api_key="test-key",
                now=datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
            )

            btc = payload["assets"]["BTC"]
            self.assertTrue(payload["available_for_analysis"])
            self.assertEqual(btc["observed_at"], "2026-08-29")
            self.assertEqual(btc["pending_date"], "2026-08-30")
            self.assertEqual(btc["latest"]["total_net_inflow"], 200.0)
            self.assertIsNone(btc["rolling"]["5_sessions_usd_millions"])
            self.assertEqual(
                btc["rolling"]["5_sessions_coverage"],
                {
                    "expected_sessions": 5,
                    "actual_sessions": 2,
                    "coverage_complete": False,
                    "missing_policy": "incomplete_window_is_null",
                },
            )
            self.assertIsNone(payload["metrics"]["etf_btc_net_flow_5d"]["value"])
            self.assertFalse(
                payload["metrics"]["etf_btc_net_flow_5d"]["available_for_analysis"]
            )
            self.assertEqual(
                payload["metrics"]["etf_btc_net_flow_latest"]["value"], 200.0
            )
            self.assertTrue(all(item == {"x-soso-api-key": "test-key"} for item in fetcher.headers))
            history = json.loads((root / "data" / "history.json").read_text())
            self.assertEqual(
                [row["date"] for row in history["assets"]["BTC"]],
                ["2026-08-28", "2026-08-29"],
            )

    def test_missing_key_is_explicit_and_does_not_invent_zero(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(fixture_config()), encoding="utf-8")
            payload = run_crypto_etf_channel(
                config_path,
                root / "data",
                environ={},
                now=datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
            )
            self.assertEqual(payload["status"], "unavailable")
            self.assertEqual(payload["credential_status"], "missing")
            self.assertFalse(payload["available_for_analysis"])
            self.assertEqual(payload["metrics"], {})

    def test_future_provider_date_is_rejected_per_asset(self) -> None:
        rows = fixture_rows()
        for asset_rows in rows.values():
            asset_rows[0]["date"] = "2026-09-03"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(fixture_config()), encoding="utf-8")
            payload = run_crypto_etf_channel(
                config_path,
                root / "data",
                fetcher=FakeEtfFetcher(rows),
                api_key="test-key",
                now=datetime(2026, 8, 31, 12, tzinfo=timezone.utc),
            )
            self.assertFalse(payload["available_for_analysis"])
            self.assertTrue(
                any("future trading date" in warning for warning in payload["quality"]["warnings"])
            )


if __name__ == "__main__":
    unittest.main()
