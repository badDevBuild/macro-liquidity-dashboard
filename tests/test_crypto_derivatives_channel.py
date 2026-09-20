from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_channel.core import FetchError, FetchResponse  # noqa: E402
from liquidity_dashboard.crypto_derivatives_channel import (  # noqa: E402
    run_crypto_derivatives_channel,
)


class FakeDerivativesFetcher:
    def __init__(self, now: datetime, *, failed_venue: str | None = None, future: bool = False):
        self.now = now
        self.failed_venue = failed_venue
        self.timestamp = int(
            (now + timedelta(minutes=10) if future else now - timedelta(minutes=1)).timestamp()
            * 1000
        )

    def fetch(self, url: str) -> FetchResponse:
        venue = "binance" if "binance.com" in url else "okx" if "okx.com" in url else "bybit"
        if venue == self.failed_venue:
            raise FetchError(f"simulated {venue} failure")
        body = self._body(url)
        return FetchResponse(
            body=json.dumps(body).encode(),
            status_code=200,
            headers={"content-type": "application/json"},
            fetched_at=self.now.isoformat().replace("+00:00", "Z"),
            elapsed_ms=5,
            attempts=1,
        )

    def _body(self, url: str):
        timestamp = self.timestamp
        hour = 3600 * 1000
        day = 24 * hour
        if "fundingInfo" in url:
            return []
        if "binance.com" in url and "globalLongShortAccountRatio" in url:
            return [{
                "symbol": "BTCUSDT",
                "longAccount": "0.60",
                "shortAccount": "0.40",
                "longShortRatio": "1.5",
                "timestamp": timestamp,
            }]
        if "binance.com" in url and "takerlongshortRatio" in url:
            return [
                {
                    "buySellRatio": "1.5",
                    "buyVol": "60",
                    "sellVol": "40",
                    "timestamp": timestamp - (23 - index) * hour,
                }
                for index in range(24)
            ]
        if "binance.com" in url and "openInterestHist" in url:
            return [
                {"sumOpenInterestValue": "80000", "timestamp": timestamp - 7 * day},
                {"sumOpenInterestValue": "90000", "timestamp": timestamp - day},
                {"sumOpenInterestValue": "100000", "timestamp": timestamp - hour},
            ]
        if "binance.com" in url and "premiumIndex" in url:
            return {"markPrice": "100", "lastFundingRate": "0.0001", "time": timestamp}
        if "binance.com" in url and "openInterest" in url:
            return {"openInterest": "1000", "time": timestamp}
        if "binance.com" in url and "ticker/24hr" in url:
            return {"priceChangePercent": "5", "closeTime": timestamp}
        if "okx.com" in url and "long-short-account-ratio-contract" in url:
            return {"code": "0", "data": [[str(timestamp), "1.0"]]}
        if "okx.com" in url and "taker-volume-contract" in url:
            return {
                "code": "0",
                "data": [
                    [str(timestamp - (23 - index) * hour), "45", "55"]
                    for index in range(24)
                ],
            }
        if "okx.com" in url and "contracts/open-interest-history" in url:
            return {
                "code": "0",
                "data": [
                    [str(timestamp - hour), "0", "0", "200000"],
                    [str(timestamp - day), "0", "0", "180000"],
                    [str(timestamp - 7 * day), "0", "0", "160000"],
                ],
            }
        if "okx.com" in url and "open-interest" in url:
            return {"code": "0", "data": [{"oiUsd": "200000", "ts": str(timestamp)}]}
        if "okx.com" in url and "funding-rate" in url:
            return {
                "code": "0",
                "data": [
                    {
                        "fundingRate": "0.0002",
                        "fundingTime": str(timestamp),
                        "nextFundingTime": str(timestamp + 8 * 3600 * 1000),
                        "ts": str(timestamp),
                    }
                ],
            }
        if "okx.com" in url and "market/ticker" in url:
            return {"code": "0", "data": [{"last": "101", "open24h": "100", "ts": str(timestamp)}]}
        if "bybit.com" in url and "account-ratio" in url:
            return {
                "retCode": 0,
                "retMsg": "OK",
                "time": timestamp,
                "result": {
                    "list": [{
                        "symbol": "BTCUSDT",
                        "buyRatio": "0.55",
                        "sellRatio": "0.45",
                        "timestamp": str(timestamp),
                    }]
                },
            }
        if "bybit.com" in url and "market/open-interest" in url:
            return {
                "retCode": 0,
                "retMsg": "OK",
                "time": timestamp,
                "result": {
                    "list": [
                        {"openInterest": "3000", "timestamp": str(timestamp - hour)},
                        {"openInterest": "2700", "timestamp": str(timestamp - day)},
                        {"openInterest": "2400", "timestamp": str(timestamp - 7 * day)},
                    ]
                },
            }
        if "bybit.com" in url and "mark-price-kline" in url:
            return {
                "retCode": 0,
                "retMsg": "OK",
                "time": timestamp,
                "result": {
                    "list": [
                        [str(timestamp - hour), "100", "100", "100", "100"],
                        [str(timestamp - day), "100", "100", "100", "100"],
                        [str(timestamp - 7 * day), "100", "100", "100", "100"],
                    ]
                },
            }
        if "bybit.com" in url:
            return {
                "retCode": 0,
                "retMsg": "OK",
                "time": timestamp,
                "result": {
                    "list": [
                        {
                            "markPrice": "100",
                            "price24hPcnt": "0.02",
                            "openInterestValue": "300000",
                            "fundingRate": "0.0003",
                            "fundingIntervalHour": "8",
                        }
                    ]
                },
            }
        raise AssertionError(f"unexpected URL: {url}")


class OptionalSignalFailureFetcher(FakeDerivativesFetcher):
    def fetch(self, url: str) -> FetchResponse:
        if "bybit.com" in url and "account-ratio" in url:
            raise FetchError("simulated optional signal failure")
        return super().fetch(url)


class CryptoDerivativesChannelTests(unittest.TestCase):
    def test_aggregates_three_official_venues_without_claiming_full_market(self) -> None:
        now = datetime(2026, 8, 31, 6, 30, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = run_crypto_derivatives_channel(
                PROJECT_ROOT / "config" / "crypto-derivatives-sources.json",
                root,
                fetcher=FakeDerivativesFetcher(now),
                now=now,
            )
            btc = payload["assets"]["BTC"]
            self.assertEqual(payload["status"], "ready")
            self.assertEqual(btc["coverage"], ["binance", "bybit", "okx"])
            self.assertAlmostEqual(btc["open_interest_usd_millions"], 0.6)
            self.assertAlmostEqual(btc["funding_annualized_pct"], 25.55, places=4)
            self.assertAlmostEqual(
                btc["funding_8h_equivalent_pct"], 25.55 / (365 * 3), places=7
            )
            self.assertAlmostEqual(btc["price_change_24h_pct"], 2.0)
            self.assertAlmostEqual(btc["account_long_pct"], 55.0)
            self.assertAlmostEqual(btc["taker_buy_share_24h_pct"], 57.5)
            self.assertEqual(btc["account_coverage"], ["binance", "bybit", "okx"])
            self.assertEqual(btc["taker_coverage"], ["binance", "okx"])
            self.assertIn("不是全市场", payload["methodology"]["boundary"])
            self.assertAlmostEqual(
                payload["metrics"]["derivatives_btc_open_interest"]["changes"]["1d"]["change"],
                0.06,
            )
            self.assertAlmostEqual(
                payload["metrics"]["derivatives_btc_open_interest"]["changes"]["1w"]["percent_change"],
                25.0,
            )
            self.assertAlmostEqual(
                payload["metrics"]["derivatives_btc_account_long_share"]["value"], 55.0
            )
            self.assertAlmostEqual(
                payload["metrics"]["derivatives_btc_funding_8h_equivalent"]["value"],
                25.55 / (365 * 3),
                places=6,
            )
            oi_points = payload["metrics"]["derivatives_btc_open_interest"]["sparkline"]
            self.assertEqual(len(oi_points), 3)
            self.assertEqual(len({item["observed_at"][:10] for item in oi_points}), 3)

    def test_two_venues_are_usable_but_explicitly_degraded(self) -> None:
        now = datetime(2026, 8, 31, 6, 30, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            payload = run_crypto_derivatives_channel(
                PROJECT_ROOT / "config" / "crypto-derivatives-sources.json",
                Path(temporary),
                fetcher=FakeDerivativesFetcher(now, failed_venue="bybit"),
                now=now,
            )
            self.assertEqual(payload["status"], "degraded")
            self.assertTrue(payload["available_for_analysis"])
            self.assertEqual(payload["assets"]["BTC"]["venue_count"], 2)
            self.assertTrue(payload["quality"]["errors_by_asset"]["BTC"])

    def test_optional_signal_failure_does_not_block_core_derivatives(self) -> None:
        now = datetime(2026, 8, 31, 6, 30, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            payload = run_crypto_derivatives_channel(
                PROJECT_ROOT / "config" / "crypto-derivatives-sources.json",
                Path(temporary),
                fetcher=OptionalSignalFailureFetcher(now),
                now=now,
            )
            btc = payload["assets"]["BTC"]
            self.assertTrue(payload["available_for_analysis"])
            self.assertTrue(btc["available_for_analysis"])
            self.assertEqual(btc["venue_count"], 3)
            self.assertEqual(btc["account_coverage"], ["binance", "okx"])
            self.assertTrue(payload["quality"]["signal_errors_by_asset"]["BTC"])

    def test_future_exchange_timestamp_is_rejected(self) -> None:
        now = datetime(2026, 8, 31, 6, 30, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            payload = run_crypto_derivatives_channel(
                PROJECT_ROOT / "config" / "crypto-derivatives-sources.json",
                Path(temporary),
                fetcher=FakeDerivativesFetcher(now, future=True),
                now=now,
            )
            self.assertFalse(payload["available_for_analysis"])
            self.assertEqual(payload["metrics"], {})
            self.assertTrue(
                any(
                    "future timestamp" in error
                    for errors in payload["quality"]["errors_by_asset"].values()
                    for error in errors
                )
            )


if __name__ == "__main__":
    unittest.main()
