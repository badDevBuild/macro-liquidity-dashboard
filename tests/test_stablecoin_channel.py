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
from liquidity_dashboard.stablecoin_channel import (  # noqa: E402
    build_stablecoin_payload,
    run_stablecoin_channel,
)


class FakeFetcher:
    def __init__(self, bodies: dict[str, bytes] | None = None, *, fail: bool = False):
        self.bodies = bodies or {}
        self.fail = fail

    def fetch(self, url: str) -> FetchResponse:
        if self.fail:
            raise FetchError("simulated failure")
        return FetchResponse(
            body=self.bodies[url],
            status_code=200,
            headers={"content-type": "application/json"},
            fetched_at="2026-08-31T01:00:00Z",
            elapsed_ms=5,
            attempts=1,
        )


def fixture_config() -> dict:
    return {
        "request_policy": {},
        "source": {
            "id": "defillama_stablecoins",
            "name": "DefiLlama stablecoin data",
            "source_owner": "DefiLlama",
            "authority": "trusted_aggregator",
            "cadence": "calendar_daily",
            "history_url": "https://example.com/history",
            "composition_url": "https://example.com/composition",
            "documentation_url": "https://example.com/docs",
            "freshness_max_days": 2,
            "cache_max_days": 3,
            "minimum_recent_daily_points": 28,
            "recent_window_days": 31,
            "supply_range_usd": [1_000_000_000, 10_000_000_000_000],
            "composition_warning_percent": 1,
            "composition_block_percent": 3,
            "daily_move_warning_percent": 5,
            "peg_basket_size": 10,
            "asset_ids": {"usdt": "1", "usdc": "2"},
        },
        "issuer_cross_checks": [],
    }


def fixture_bodies() -> tuple[bytes, bytes]:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    history = []
    for index in range(62):
        moment = start + timedelta(days=index)
        history.append(
            {
                "date": str(int(moment.timestamp())),
                "totalCirculating": {"peggedUSD": 300_000_000_000 + index * 100_000_000},
                "totalCirculatingUSD": {"peggedUSD": 299_000_000_000 + index * 100_000_000},
            }
        )
    assets = {
        "peggedAssets": [
            {
                "id": "1",
                "name": "Tether",
                "symbol": "USDT",
                "pegType": "peggedUSD",
                "price": 0.9998,
                "circulating": {"peggedUSD": 180_000_000_000},
                "circulatingPrevDay": {"peggedUSD": 179_800_000_000},
                "circulatingPrevWeek": {"peggedUSD": 179_000_000_000},
                "circulatingPrevMonth": {"peggedUSD": 177_000_000_000},
            },
            {
                "id": "2",
                "name": "USD Coin",
                "symbol": "USDC",
                "pegType": "peggedUSD",
                "price": 1.0001,
                "circulating": {"peggedUSD": 72_000_000_000},
                "circulatingPrevDay": {"peggedUSD": 71_900_000_000},
                "circulatingPrevWeek": {"peggedUSD": 71_500_000_000},
                "circulatingPrevMonth": {"peggedUSD": 70_000_000_000},
            },
            {
                "id": "3",
                "name": "Other Dollar",
                "symbol": "OTHER",
                "pegType": "peggedUSD",
                "price": 0.997,
                "circulating": {"peggedUSD": 54_100_000_000},
                "circulatingPrevDay": {"peggedUSD": 54_000_000_000},
                "circulatingPrevWeek": {"peggedUSD": 53_500_000_000},
                "circulatingPrevMonth": {"peggedUSD": 52_000_000_000},
            },
            {
                "id": "4",
                "name": "Yield Dollar",
                "symbol": "YIELD",
                "pegType": "peggedUSD",
                "yieldBearing": True,
                "price": 1.2,
                "circulating": {"peggedUSD": 100_000_000},
                "circulatingPrevDay": {"peggedUSD": 100_000_000},
                "circulatingPrevWeek": {"peggedUSD": 100_000_000},
                "circulatingPrevMonth": {"peggedUSD": 100_000_000},
            },
        ]
    }
    return json.dumps(history).encode(), json.dumps(assets).encode()


class StablecoinParserTests(unittest.TestCase):
    def test_keeps_legitimate_small_early_history(self) -> None:
        history, assets = fixture_bodies()
        rows = json.loads(history)
        rows.insert(
            0,
            {
                "date": str(int(datetime(2017, 1, 1, tzinfo=timezone.utc).timestamp())),
                "totalCirculating": {"peggedUSD": 109_970},
            },
        )
        payload = build_stablecoin_payload(
            json.dumps(rows).encode(),
            assets,
            fixture_config(),
            now=datetime(2026, 8, 31, 2, tzinfo=timezone.utc),
            run_id="run-early-history",
            fetched_at="2026-08-31T01:00:00Z",
        )
        self.assertEqual(
            payload["metrics"]["stablecoin_usd_supply"]["value"], 306_100.0
        )

    def test_uses_face_value_supply_and_builds_changes(self) -> None:
        history, assets = fixture_bodies()
        payload = build_stablecoin_payload(
            history,
            assets,
            fixture_config(),
            now=datetime(2026, 8, 31, 2, tzinfo=timezone.utc),
            run_id="run-1",
            fetched_at="2026-08-31T01:00:00Z",
        )
        total = payload["metrics"]["stablecoin_usd_supply"]
        self.assertEqual(total["value"], 306_100.0)
        self.assertEqual(total["changes"]["1w"]["change"], 700.0)
        self.assertEqual(len(payload["history"]), 62)
        self.assertEqual(payload["history"][0]["observed_at"], "2026-07-01")
        self.assertFalse(total["metadata"]["price_adjusted_market_cap_used"])
        self.assertAlmostEqual(
            payload["metrics"]["stablecoin_usdt_usdc_share"]["value"],
            252 / 306.2,
            places=4,
        )
        self.assertEqual(
            payload["metrics"]["stablecoin_core_max_depeg_bps"]["metadata"]["symbol"],
            "OTHER",
        )
        self.assertEqual(
            payload["metrics"]["stablecoin_core_max_depeg_bps"]["metadata"]
            ["excluded_yield_bearing"],
            1,
        )

    def test_rejects_future_history_observation(self) -> None:
        history, assets = fixture_bodies()
        rows = json.loads(history)
        rows.append(
            {
                "date": str(int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp())),
                "totalCirculating": {"peggedUSD": 306_200_000_000},
            }
        )
        with self.assertRaisesRegex(Exception, "future observation"):
            build_stablecoin_payload(
                json.dumps(rows).encode(),
                assets,
                fixture_config(),
                now=datetime(2026, 8, 31, tzinfo=timezone.utc),
                run_id="run-1",
                fetched_at="2026-08-31T01:00:00Z",
            )


class StablecoinChannelFallbackTests(unittest.TestCase):
    def test_fresh_cache_is_used_without_turning_missing_into_zero(self) -> None:
        history, assets = fixture_bodies()
        config = fixture_config()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "stablecoins.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            first = run_stablecoin_channel(
                config_path,
                root / "data",
                fetcher=FakeFetcher(
                    {
                        config["source"]["history_url"]: history,
                        config["source"]["composition_url"]: assets,
                    }
                ),
                now=datetime(2026, 8, 31, 2, tzinfo=timezone.utc),
            )
            second = run_stablecoin_channel(
                config_path,
                root / "data",
                fetcher=FakeFetcher(fail=True),
                now=datetime(2026, 9, 2, 2, tzinfo=timezone.utc),
            )
            self.assertTrue(first["available_for_analysis"])
            self.assertEqual(second["quality_status"], "fresh_cache")
            self.assertEqual(
                second["metrics"]["stablecoin_usd_supply"]["value"],
                first["metrics"]["stablecoin_usd_supply"]["value"],
            )
            self.assertNotEqual(
                second["metrics"]["stablecoin_usd_supply"]["value"], 0
            )

    def test_expired_cache_becomes_unavailable(self) -> None:
        history, assets = fixture_bodies()
        config = fixture_config()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "stablecoins.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            run_stablecoin_channel(
                config_path,
                root / "data",
                fetcher=FakeFetcher(
                    {
                        config["source"]["history_url"]: history,
                        config["source"]["composition_url"]: assets,
                    }
                ),
                now=datetime(2026, 8, 31, 2, tzinfo=timezone.utc),
            )
            failed = run_stablecoin_channel(
                config_path,
                root / "data",
                fetcher=FakeFetcher(fail=True),
                now=datetime(2026, 9, 5, 2, tzinfo=timezone.utc),
            )
            self.assertFalse(failed["available_for_analysis"])
            self.assertEqual(failed["status"], "unavailable")
            self.assertEqual(failed["metrics"], {})


if __name__ == "__main__":
    unittest.main()
