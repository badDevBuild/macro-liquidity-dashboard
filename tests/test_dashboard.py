from __future__ import annotations

import http.client
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from liquidity_dashboard.model import (  # noqa: E402
    _event_calendar_view,
    _derived_spread_view,
    _history_rows,
    _runtime_freshness,
    _runtime_refresh_optional_view,
    build_series,
    calculate_aligned_spread,
    calculate_change_contributions,
    calculate_net_liquidity_proxy,
    calculate_streak,
    calculate_weekly_contributions,
)
from liquidity_dashboard.agent_analysis import (  # noqa: E402
    load_agent_analysis,
    validate_agent_payload,
)
from liquidity_dashboard.server import create_server  # noqa: E402
from liquidity_dashboard.public_status import public_cycle_status  # noqa: E402
from build_public_release import build_release  # noqa: E402


class DashboardCalculationTests(unittest.TestCase):
    def test_history_query_honors_publication_cutoff_for_same_day_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            connection = sqlite3.connect(Path(temporary) / "history.sqlite3")
            connection.row_factory = sqlite3.Row
            connection.executescript("""
                CREATE TABLE observations (
                    metric_id TEXT, source_id TEXT, observed_at TEXT, value REAL,
                    unit TEXT, first_seen_at TEXT, last_seen_at TEXT,
                    revision_count INTEGER
                );
                CREATE TABLE observation_versions (
                    run_id TEXT, metric_id TEXT, source_id TEXT, observed_at TEXT,
                    value REAL, unit TEXT, recorded_at TEXT, raw_sha256 TEXT
                );
            """)
            connection.execute(
                "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("m", "s", "2026-08-28", 90, "x", "2026-08-28T07:00:00Z", "2026-08-28T09:00:00Z", 1),
            )
            connection.executemany(
                "INSERT INTO observation_versions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("run-1", "m", "s", "2026-08-28", 100, "x", "2026-08-28T07:00:00Z", "a"),
                    ("run-2", "m", "s", "2026-08-28", 90, "x", "2026-08-28T09:00:00Z", "b"),
                ],
            )
            connection.commit()
            rows = _history_rows(
                connection,
                "m",
                "s",
                published_at="2026-08-28T08:00:00Z",
            )
            connection.close()
        self.assertEqual(rows[0]["value"], 100)

    def test_derived_spread_inherits_unavailable_component(self) -> None:
        spread = _derived_spread_view(
            "spread_test",
            "A − B",
            "a",
            "b",
            [{"observed_at": "2026-08-28", "value": 4.0}],
            [{"observed_at": "2026-08-28", "value": 3.0}],
            {
                "a": {"available_for_analysis": True, "quality_status": "fresh_network"},
                "b": {"available_for_analysis": False, "quality_status": "stale_runtime"},
            },
            streak_condition="positive",
        )
        self.assertEqual(spread["value"], 100.0)
        self.assertFalse(spread["available_for_analysis"])
        self.assertEqual(spread["quality_status"], "unavailable")

    def test_public_cycle_status_drops_paths_logs_and_error_details(self) -> None:
        public = public_cycle_status({
            "status": "completed_deploy_failed",
            "run_id": "run-1",
            "started_at": "2026-08-28T00:00:00Z",
            "completed_at": "2026-08-28T00:05:00Z",
            "agent_status": "ready",
            "agent_run_dir": "/Users/private/data/analysis",
            "agent_stderr_tail": "token=secret stack trace",
            "deployment_error": "ssh failed for private-host",
        })
        serialized = json.dumps(public)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("private-host", serialized)
        self.assertEqual(public["error_code"], "completed_deploy_failed")

    def test_public_cycle_status_treats_optional_degradation_as_completed(self) -> None:
        public = public_cycle_status({
            "status": "completed_degraded",
            "cycle_id": "cycle-1",
            "energy_status": "unavailable",
        })

        self.assertTrue(public["success"])
        self.assertIsNone(public["error_code"])
        self.assertEqual(public["modules"]["energy"], "unavailable")

    def test_runtime_freshness_expires_without_rewriting_publication_fact(self) -> None:
        result = _runtime_freshness(
            {
                "observed_at": "2026-08-01",
                "quality_status": "fresh_network",
                "available_for_analysis": True,
            },
            {"freshness_max_days": 5},
            now=datetime(2026, 8, 10, 7, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(result["publication_quality_status"], "fresh_network")
        self.assertTrue(result["publication_available_for_analysis"])
        self.assertEqual(result["runtime_freshness_status"], "stale")
        self.assertEqual(result["quality_status"], "stale_runtime")
        self.assertFalse(result["available_for_analysis"])

    def test_optional_daily_metric_also_expires_at_read_time(self) -> None:
        view = _runtime_refresh_optional_view(
            {
                "available_for_analysis": True,
                "quality_status": "fresh_network",
                "metrics": {
                    "example": {
                        "observed_at": "2026-08-01",
                        "cadence": "business_daily",
                        "quality_status": "fresh_network",
                        "available_for_analysis": True,
                        "value": 1,
                    }
                },
            },
            now=datetime(2026, 8, 10, 7, 30, tzinfo=timezone.utc),
        )
        self.assertFalse(view["available_for_analysis"])
        self.assertFalse(view["metrics"]["example"]["available_for_analysis"])

    def test_event_calendar_exposes_next_event_and_cache_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "context").mkdir(parents=True)
            payload = {
                "generated_at": "2026-08-30T00:00:00Z",
                "future_90d": [
                    {
                        "context_id": "ctx-1",
                        "category": "macro_release",
                        "release_type": "employment_situation",
                        "reference_period": "August 2026",
                        "title": "Employment Situation for August 2026",
                        "starts_at": "2026-09-04T12:30:00Z",
                        "source_id": "bls_release_calendar",
                        "source_name": "U.S. Bureau of Labor Statistics",
                        "source_tier": "official_primary",
                        "url": "https://www.bls.gov/schedule/news_release/empsit.htm",
                        "delivery_status": "verified_cache",
                    }
                ],
                "calendar_health": {"status": "ready"},
                "source_health": [
                    {
                        "source_id": "bls_release_calendar",
                        "label": "BLS 数据日程",
                        "status": "ok",
                        "delivery_status": "verified_cache",
                        "item_count": 3,
                    }
                ],
            }
            (root / "data" / "context" / "latest.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            view = _event_calendar_view(
                root, now=datetime(2026, 8, 30, 8, tzinfo=timezone.utc)
            )
        self.assertEqual(view["status"], "ready")
        self.assertEqual(
            view["next_event"]["release_type"], "employment_situation"
        )
        self.assertEqual(view["bls"]["delivery_status"], "verified_cache")

    def test_spreads_only_use_exact_common_observation_dates(self) -> None:
        left = [
            {"observed_at": "2026-08-25", "value": 3.64},
            {"observed_at": "2026-08-26", "value": 3.65},
        ]
        right = [
            {"observed_at": "2026-08-24", "value": 3.63},
            {"observed_at": "2026-08-26", "value": 3.62},
        ]
        self.assertEqual(
            calculate_aligned_spread(left, right),
            [{"observed_at": "2026-08-26", "value": 3.0}],
        )

    def test_inversion_streak_counts_valid_observations_not_calendar_days(self) -> None:
        points = [
            {"observed_at": "2026-08-21", "value": 1.0},
            {"observed_at": "2026-08-24", "value": -2.0},
            {"observed_at": "2026-08-25", "value": -3.0},
        ]
        self.assertEqual(
            calculate_streak(points, condition="negative"),
            {"active": True, "observations": 2, "start_date": "2026-08-24"},
        )

    def test_net_liquidity_proxy_converts_rrp_billions_to_millions(self) -> None:
        self.assertEqual(calculate_net_liquidity_proxy(10_000, 1_000, 2), 7_000)

    def test_net_liquidity_proxy_preserves_missing_value_semantics(self) -> None:
        self.assertIsNone(calculate_net_liquidity_proxy(10_000, None, 2))

    def test_latest_release_changes_reconcile_to_the_displayed_total(self) -> None:
        contributions = calculate_change_contributions(-14_787, -34_702, -0.246)
        by_id = {item["id"]: item for item in contributions}
        self.assertEqual(by_id["fed_total_assets"]["contribution_usd_millions"], -14_787)
        self.assertEqual(by_id["tga_daily"]["contribution_usd_millions"], 34_702)
        self.assertEqual(by_id["overnight_rrp"]["contribution_usd_millions"], 246)
        self.assertEqual(
            sum(item["contribution_usd_millions"] for item in contributions),
            20_161,
        )

    def test_weekly_contribution_signs_match_the_public_formula(self) -> None:
        current = {
            "fed_total_assets": 1_100,
            "tga_daily": 600,
            "overnight_rrp": 2,
        }
        previous = {
            "fed_total_assets": 1_000,
            "tga_daily": 500,
            "overnight_rrp": 3,
        }
        by_id = {
            item["id"]: item
            for item in calculate_weekly_contributions(current, previous)
        }
        self.assertEqual(by_id["fed_total_assets"]["value_usd_millions"], 100)
        self.assertEqual(by_id["tga_daily"]["value_usd_millions"], -100)
        self.assertEqual(by_id["overnight_rrp"]["value_usd_millions"], 1_000)
        self.assertEqual(by_id["tga_daily"]["raw_change_usd_millions"], 100)
        self.assertEqual(by_id["tga_daily"]["contribution_usd_millions"], -100)
        self.assertEqual(by_id["overnight_rrp"]["raw_change_usd_millions"], -1_000)
        self.assertEqual(by_id["overnight_rrp"]["contribution_usd_millions"], 1_000)
        self.assertEqual(by_id["overnight_rrp"]["effect"], "supportive")

    def test_weekly_contributions_fail_closed_when_a_component_is_missing(self) -> None:
        current = {
            "fed_total_assets": 1_100,
            "tga_daily": None,
            "overnight_rrp": 2,
        }
        previous = {
            "fed_total_assets": 1_000,
            "tga_daily": 500,
            "overnight_rrp": 3,
        }
        self.assertEqual(calculate_weekly_contributions(current, previous), [])


class AgentAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.metrics = {
            "tga_daily": {
                "metric_id": "tga_daily",
                "observed_at": "2026-08-26",
            "value": 959_435,
            "changes": {"1w": {"change": 23_029}},
            "available_for_analysis": True,
            "quality_status": "fresh_network",
            }
        }
        self.proxy = {
            "value": 5_771_021,
            "observed_at": "2026-08-26",
            "week_change": -38_047,
            "latest_release_change": 20_161,
            "trend_latest_value": 5_779_474,
            "trend_latest_observed_at": "2026-08-26",
            "trend_changes": {"1m": {"change": -137_905}},
            "available_for_analysis": True,
            "quality_status": "fresh_network",
            "methodology_version": "daily-tga-v1",
        }

    def artifact(self) -> dict:
        return {
            "schema_version": "1.5",
            "prompt_version": "macro-liquidity-morning-v10",
            "analysis_id": "analysis-1",
            "snapshot_run_id": "run-1",
            "context_bundle_id": "context-unavailable",
            "generated_at": "2026-08-28T07:00:00Z",
            "model": {
                "provider": "openai_codex_subscription",
                "id": "gpt-5.6-sol",
                "reasoning_effort": "medium",
            },
            "status": "ready",
            "overall_assessment": "tightening",
            "confidence": "medium",
            "headline": "财政现金回补压低了本周参考值",
            "summary": "账本方向偏紧，但仍需和利率及美元一起判断。",
            "market_bottom_line": "当前不是单向顺风，需要更多数据确认。",
            "daily_update": {
                "status": "comparison_unavailable",
                "headline": "暂无上一轮对比",
                "summary": "这是首次可用运行，暂时无法判断新发布了哪些数据。",
                "market_expectation_note": "市场预期暂无上一轮可比数据。",
                "evidence": [],
            },
            "layer_analysis": [
                {
                    "layer": layer,
                    "assessment": "tightening",
                    "conclusion": "测试层结论。",
                    "evidence": [{
                        "metric_id": "tga_daily",
                        "observed_at": "2026-08-26",
                        "value": 959_435,
                        "comparison_window": "1w",
                        "change": 23_029,
                    }],
                }
                for layer in (
                    "balance_sheet_liquidity",
                    "funding_and_rates",
                    "dollar_and_financial_conditions",
                    "risk_asset_transmission",
                )
            ],
            "market_implications": {
                market: {
                    "bias": "mixed",
                    "conclusion": "需要更多指标确认。",
                    "transmission": "通过融资条件间接传导。",
                    "confirm_metric_ids": ["tga_daily"],
                    "invalidate_metric_ids": ["tga_daily"],
                }
                for market in ("equities", "crypto")
            },
            "drivers": [
                {
                    "claim": "TGA 增加，对参考值形成抽水。",
                    "effect": "draining",
                    "evidence": [
                        {
                            "metric_id": "tga_daily",
                            "observed_at": "2026-08-26",
                            "value": 959_435,
                            "comparison_window": "1w",
                            "change": 23_029,
                        }
                    ],
                }
            ],
            "contradictions": [],
            "watch_items": [
                {
                    "trigger": "观察 TGA 是否回落",
                    "why": "回落会把现金重新推回银行体系。",
                    "metric_ids": ["tga_daily"],
                }
            ],
            "context_screening_note": "本轮没有可用的新闻事件上下文。",
            "context_assessments": [],
            "unknowns": [],
            "data_quality_note": "本轮核心数据通过检查。",
        }

    def test_missing_agent_artifact_does_not_block_dashboard_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = load_agent_analysis(
                Path(temporary),
                snapshot_run_id="run-1",
                analysis_allowed=True,
                metrics=self.metrics,
                proxy=self.proxy,
            )
        self.assertEqual(result["state"], "setup_pending")
        self.assertFalse(result["is_current"])

    def test_agent_artifact_is_published_only_when_evidence_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "analysis").mkdir(parents=True)
            (root / "data" / "analysis" / "latest.json").write_text(
                json.dumps(self.artifact()), encoding="utf-8"
            )
            result = load_agent_analysis(
                root,
                snapshot_run_id="run-1",
                analysis_allowed=True,
                metrics=self.metrics,
                proxy=self.proxy,
            )
        self.assertEqual(result["state"], "ready")
        self.assertTrue(result["is_current"])

    def test_verified_shadow_artifact_can_be_displayed_as_user_approved_pilot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir(parents=True)
            (root / "config" / "agent-dashboard-policy.json").write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "enabled": True,
                        "display_mode": "pilot_shadow",
                    }
                ),
                encoding="utf-8",
            )
            (root / "data" / "analysis" / "shadow").mkdir(parents=True)
            (root / "data" / "analysis" / "shadow" / "latest.json").write_text(
                json.dumps(self.artifact()), encoding="utf-8"
            )
            result = load_agent_analysis(
                root,
                snapshot_run_id="run-1",
                analysis_allowed=True,
                metrics=self.metrics,
                proxy=self.proxy,
            )
        self.assertEqual(result["state"], "pilot_ready")
        self.assertEqual(result["release_stage"], "pilot")
        self.assertTrue(result["is_current"])
        self.assertNotIn("试运行", result["message"])

    def test_production_artifact_takes_priority_over_pilot_shadow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir(parents=True)
            (root / "config" / "agent-dashboard-policy.json").write_text(
                json.dumps({"enabled": True, "display_mode": "pilot_shadow"}),
                encoding="utf-8",
            )
            (root / "data" / "analysis" / "shadow").mkdir(parents=True)
            shadow = self.artifact()
            shadow["headline"] = "影子分析"
            (root / "data" / "analysis" / "shadow" / "latest.json").write_text(
                json.dumps(shadow), encoding="utf-8"
            )
            production = self.artifact()
            production["headline"] = "正式分析"
            (root / "data" / "analysis" / "latest.json").write_text(
                json.dumps(production), encoding="utf-8"
            )
            result = load_agent_analysis(
                root,
                snapshot_run_id="run-1",
                analysis_allowed=True,
                metrics=self.metrics,
                proxy=self.proxy,
            )
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["release_stage"], "production")
        self.assertEqual(result["headline"], "正式分析")

    def test_agent_artifact_with_changed_number_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "analysis").mkdir(parents=True)
            artifact = self.artifact()
            artifact["drivers"][0]["evidence"][0]["change"] = -23_029
            (root / "data" / "analysis" / "latest.json").write_text(
                json.dumps(artifact), encoding="utf-8"
            )
            result = load_agent_analysis(
                root,
                snapshot_run_id="run-1",
                analysis_allowed=True,
                metrics=self.metrics,
                proxy=self.proxy,
            )
        self.assertEqual(result["state"], "invalid")
        self.assertFalse(result["is_current"])

    def test_metric_without_explicit_analysis_eligibility_fails_closed(self) -> None:
        metrics = json.loads(json.dumps(self.metrics))
        metrics["tga_daily"].pop("available_for_analysis")
        errors = validate_agent_payload(
            self.artifact(),
            metrics,
            self.proxy,
            {},
        )
        self.assertIn(
            "drivers contains evidence that does not match the snapshot",
            errors,
        )

    def test_background_analysis_allows_explicit_mixed_date_caveat(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "analysis").mkdir(parents=True)
            artifact = self.artifact()
            artifact["summary"] = "今日判断基于最新可用数据：联储为周值，财政现金为日值，不能称为当日净流出。"
            (root / "data" / "analysis" / "latest.json").write_text(
                json.dumps(artifact), encoding="utf-8"
            )
            result = load_agent_analysis(
                root,
                snapshot_run_id="run-1",
                analysis_allowed=True,
                metrics=self.metrics,
                proxy=self.proxy,
            )
        self.assertNotEqual(result["state"], "invalid")
        self.assertNotIn(
            "only daily_update may describe a change as today/current-day",
            result.get("validation_errors", []),
        )

    def test_agent_artifact_with_duplicate_watch_metrics_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "analysis").mkdir(parents=True)
            artifact = self.artifact()
            artifact["watch_items"][0]["metric_ids"] = ["tga_daily", "tga_daily"]
            (root / "data" / "analysis" / "latest.json").write_text(
                json.dumps(artifact), encoding="utf-8"
            )
            result = load_agent_analysis(
                root,
                snapshot_run_id="run-1",
                analysis_allowed=True,
                metrics=self.metrics,
                proxy=self.proxy,
            )
        self.assertEqual(result["state"], "invalid")
        self.assertFalse(result["is_current"])

    def test_official_future_schedule_is_a_valid_context_basis(self) -> None:
        artifact = self.artifact()
        artifact["context_assessments"] = [
            {
                "context_id": "event-1",
                "relevance": "relevant",
                "content_basis": "official_schedule",
                "what_happened": "美国劳工统计局计划发布就业报告。",
                "transmission": "结果可能通过政策利率预期影响短端利率。",
                "reason": "这是需要观察的官方时间窗。",
                "linked_metric_ids": ["tga_daily"],
            }
        ]
        errors = validate_agent_payload(
            artifact,
            self.metrics,
            self.proxy,
            {
                "event-1": {
                    "context_id": "event-1",
                    "kind": "scheduled_event",
                    "content_status": "official_schedule",
                }
            },
        )
        self.assertEqual(errors, [])

    def test_title_only_news_cannot_enter_main_agent_analysis(self) -> None:
        artifact = self.artifact()
        artifact["context_assessments"] = [
            {
                "context_id": "news-1",
                "relevance": "watch",
                "content_basis": "title_only",
                "what_happened": "标题提到利率变化。",
                "transmission": "可能影响融资条件。",
                "reason": "正文不可用。",
                "linked_metric_ids": ["tga_daily"],
            }
        ]
        errors = validate_agent_payload(
            artifact,
            self.metrics,
            self.proxy,
            {
                "news-1": {
                    "context_id": "news-1",
                    "kind": "past_news",
                    "content_status": "title_only",
                }
            },
        )
        self.assertIn(
            "context_assessments cannot analyze past news without content",
            errors,
        )

    def test_weekly_proxy_evidence_uses_the_weekly_value_and_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "analysis").mkdir(parents=True)
            artifact = self.artifact()
            artifact["drivers"][0]["evidence"] = [
                {
                    "metric_id": "net_liquidity_proxy_weekly",
                    "observed_at": "2026-08-26",
                    "value": 5_779_474,
                    "comparison_window": "1m",
                    "change": -137_905,
                }
            ]
            artifact["watch_items"][0]["metric_ids"] = [
                "net_liquidity_proxy_weekly"
            ]
            (root / "data" / "analysis" / "latest.json").write_text(
                json.dumps(artifact), encoding="utf-8"
            )
            result = load_agent_analysis(
                root,
                snapshot_run_id="run-1",
                analysis_allowed=True,
                metrics=self.metrics,
                proxy=self.proxy,
            )
        self.assertEqual(result["state"], "ready")
        self.assertTrue(result["is_current"])


class DashboardSeriesTests(unittest.TestCase):
    def test_etf_session_ranges_return_distinct_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "snapshots").mkdir(parents=True)
            (root / "data" / "snapshots" / "latest.json").write_text(
                "{}", encoding="utf-8"
            )
            etf_dir = root / "data" / "crypto" / "etf"
            etf_dir.mkdir(parents=True)
            points = [
                {"observed_at": f"2026-08-{day:02d}", "value": float(day)}
                for day in range(1, 26)
            ]
            payload = {
                "status": "ready",
                "quality_status": "fresh_network",
                "available_for_analysis": True,
                "metrics": {
                    "etf_btc_net_flow_latest": {
                        "metric_id": "etf_btc_net_flow_latest",
                        "source_id": "sosovalue_us_crypto_etf",
                        "source_name": "SoSoValue",
                        "source_url": "https://example.com",
                        "unit": "usd_millions",
                        "sparkline": points,
                    }
                },
                "quality": {"revision_count": 0},
            }
            (etf_dir / "latest.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            five_days = build_series(root, "etf_btc_net_flow_latest", "5d")
            twenty_days = build_series(root, "etf_btc_net_flow_latest", "20d")

            self.assertEqual(len(five_days["points"]), 5)
            self.assertEqual(len(twenty_days["points"]), 20)
            self.assertEqual(five_days["points"][0]["observed_at"], "2026-08-21")
            self.assertEqual(twenty_days["points"][0]["observed_at"], "2026-08-06")

    def test_series_uses_formal_snapshot_source_and_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "snapshots").mkdir(parents=True)
            snapshot = {
                "run_id": "run-1",
                "completed_at": "2026-08-02T00:00:00Z",
                "metrics": {
                    "fed_total_assets": {
                        "source_id": "primary",
                        "source_name": "Primary source",
                        "source_url": "https://example.com/primary",
                        "unit": "usd_millions",
                        "observed_at": "2026-08-01",
                    }
                }
            }
            (root / "data" / "snapshots" / "latest.json").write_text(
                json.dumps(snapshot), encoding="utf-8"
            )
            database = root / "data" / "channel.sqlite3"
            connection = sqlite3.connect(database)
            connection.executescript(
                """
                CREATE TABLE observations (
                    metric_id TEXT, source_id TEXT, observed_at TEXT, value REAL,
                    unit TEXT, revision_count INTEGER DEFAULT 0
                );
                CREATE TABLE observation_revisions (
                    metric_id TEXT, source_id TEXT, observed_at TEXT,
                    old_value REAL, new_value REAL, detected_at TEXT
                );
                """
            )
            connection.executemany(
                "INSERT INTO observations VALUES (?, ?, ?, ?, ?, 0)",
                [
                    ("fed_total_assets", "primary", "2025-01-01", 90, "usd_millions"),
                    ("fed_total_assets", "primary", "2026-07-01", 100, "usd_millions"),
                    ("fed_total_assets", "primary", "2026-08-01", 110, "usd_millions"),
                    ("fed_total_assets", "backup", "2026-08-01", 999, "usd_millions"),
                ],
            )
            connection.commit()
            connection.close()

            payload = build_series(root, "fed_total_assets", "3m")
            self.assertEqual(payload["source_id"], "primary")
            self.assertEqual([point["value"] for point in payload["points"]], [100, 110])

    def test_series_rejects_unknown_metric(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):
                build_series(Path(temporary), "not-a-metric", "3m")

    def test_stablecoin_series_keeps_full_history_out_of_dashboard_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "snapshots").mkdir(parents=True)
            (root / "data" / "snapshots" / "latest.json").write_text(
                "{}", encoding="utf-8"
            )
            (root / "data" / "stablecoins").mkdir(parents=True)
            payload = {
                "status": "ready",
                "quality_status": "fresh_network",
                "available_for_analysis": True,
                "source": {"source_id": "defillama_stablecoins"},
                "history": [
                    {"observed_at": "2024-01-01", "value": 100.0},
                    {"observed_at": "2025-01-01", "value": 120.0},
                    {"observed_at": "2026-01-01", "value": 140.0},
                ],
                "metrics": {
                    "stablecoin_usd_supply": {
                        "metric_id": "stablecoin_usd_supply",
                        "source_id": "defillama_stablecoins",
                        "source_name": "DefiLlama",
                        "source_url": "https://example.com",
                        "unit": "usd_millions",
                        "sparkline": [
                            {"observed_at": "2025-01-01", "value": 120.0},
                            {"observed_at": "2026-01-01", "value": 140.0},
                        ],
                    }
                },
            }
            (root / "data" / "stablecoins" / "latest.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )

            all_history = build_series(root, "stablecoin_usd_supply", "all")
            one_year = build_series(root, "stablecoin_usd_supply", "1y")
            self.assertEqual(len(all_history["points"]), 3)
            self.assertEqual(len(one_year["points"]), 2)

    def test_proxy_series_requires_common_daily_dates_and_carries_only_fed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "snapshots").mkdir(parents=True)
            snapshot = {
                "metrics": {
                    "fed_total_assets": {
                        "source_id": "fed",
                        "observed_at": "2026-01-14",
                        "value": 11_000,
                        "unit": "usd_millions",
                    },
                    "tga_daily": {
                        "source_id": "tga",
                        "observed_at": "2026-01-13",
                        "value": 1_200,
                        "unit": "usd_millions",
                    },
                    "overnight_rrp": {
                        "source_id": "rrp",
                        "observed_at": "2026-01-13",
                        "value": 3,
                        "unit": "usd_billions",
                    },
                }
            }
            (root / "data" / "snapshots" / "latest.json").write_text(
                json.dumps(snapshot), encoding="utf-8"
            )
            connection = sqlite3.connect(root / "data" / "channel.sqlite3")
            connection.execute(
                """
                CREATE TABLE observations (
                    metric_id TEXT, source_id TEXT, observed_at TEXT, value REAL,
                    unit TEXT, revision_count INTEGER DEFAULT 0
                )
                """
            )
            connection.executemany(
                "INSERT INTO observations VALUES (?, ?, ?, ?, ?, 0)",
                [
                    ("fed_total_assets", "fed", "2026-01-07", 10_000, "usd_millions"),
                    ("fed_total_assets", "fed", "2026-01-14", 11_000, "usd_millions"),
                    ("tga_daily", "tga", "2026-01-07", 1_000, "usd_millions"),
                    ("tga_daily", "tga", "2026-01-13", 1_200, "usd_millions"),
                    ("overnight_rrp", "rrp", "2026-01-07", 2, "usd_billions"),
                    ("overnight_rrp", "rrp", "2026-01-13", 3, "usd_billions"),
                ],
            )
            connection.commit()
            connection.close()

            payload = build_series(root, "net_liquidity_proxy", "1y")
            self.assertEqual([point["value"] for point in payload["points"]], [7_000, 5_800])
            self.assertEqual(payload["source_id"], "derived_daily_proxy")
            self.assertEqual(
                payload["points"][1]["component_dates"]["overnight_rrp"],
                "2026-01-13",
            )


class FrontendDeploymentTests(unittest.TestCase):
    def test_shadow_cycle_has_process_lock_timeout_and_cycle_scoped_status(self) -> None:
        runner = (PROJECT_ROOT / "scripts" / "run_shadow_cycle.py").read_text(encoding="utf-8")
        self.assertIn("fcntl.LOCK_EX | fcntl.LOCK_NB", runner)
        self.assertIn("--stage-timeout-seconds", runner)
        self.assertIn("subprocess.TimeoutExpired", runner)
        self.assertIn('STATUS_DIR / "cycles" / f"{cycle_id}.json"', runner)
        self.assertIn('environment["LIQUIDITY_CYCLE_ID"]', runner)

    def test_frontend_theme_switch_follows_system_and_persists_user_choice(self) -> None:
        index = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        styles = (PROJECT_ROOT / "web" / "assets" / "app.css").read_text(
            encoding="utf-8"
        )
        service_worker = (PROJECT_ROOT / "web" / "sw.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="theme-toggle"', index)
        self.assertIn('content="light dark"', index)
        self.assertIn('window.matchMedia("(prefers-color-scheme: dark)")', index)
        self.assertIn('document.documentElement.dataset.theme = theme', index)
        self.assertIn('localStorage.setItem(THEME_KEY, nextTheme)', app)
        self.assertIn('setAttribute("aria-pressed"', app)
        self.assertIn('html[data-theme="dark"]', styles)
        self.assertIn('assets/app.css?v=44', index)
        self.assertIn('assets/app.js?v=44', index)
        self.assertIn('assets/coinbase-premium.js?v=44', index)
        self.assertIn('assets/coinbase-premium.js?v=44', service_worker)
        self.assertIn('`${CACHE_PREFIX}shell-v44`', service_worker)
        self.assertIn('`${CACHE_PREFIX}data-v3`', service_worker)
        self.assertIn('key.startsWith(CACHE_PREFIX)', service_worker)
        self.assertNotIn('.filter((key) => ![SHELL_CACHE, DATA_CACHE].includes(key))', service_worker)

    def test_frontend_series_requests_are_release_bound_and_race_safe(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("seriesRequests: new WeakMap()", app)
        self.assertIn("previous.controller.abort()", app)
        self.assertIn("payload.release_id !== releaseId", app)
        self.assertIn("`${releaseId}:${metricId}:${rangeId}`", app)
        self.assertIn("minimumIndex", app)
        self.assertIn("maximumIndex", app)
        self.assertIn("_segmentStart", app)
        self.assertIn("chartDataTable(tablePoints, metric, rangeId)", app)
        self.assertIn("state.seriesRequests.delete(mainChart)", app)

    def test_frontend_missing_curve_values_never_claim_no_inversion(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("当前利差不可用，不判断是否倒挂", app)
        self.assertIn("只有历史值", app)
        self.assertNotIn("const inverted = numericOrNull(spread.value) < 0", app)

    def test_frontend_evidence_links_open_the_full_metric_registry(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-evidence-metric", app)
        self.assertIn("function openEvidenceMetric", app)
        self.assertIn("Object.values(data.metrics || {})", app)
        self.assertIn("Object.values(data.derived_metrics || {})", app)
        self.assertNotIn('analysis.watch_items?.[0]?.trigger || "这轮没有明显的反向信号。"', app)

    def test_all_line_chart_sizes_share_gap_segmentation(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(encoding="utf-8")
        self.assertIn("const segments = chartSegments(rawPoints, metric);", app)
        self.assertIn("const segmented = chartSegments(series.points, series);", app)
        self.assertGreaterEqual(app.count("_segmentStart"), 5)

    def test_derivatives_separates_price_change_from_funding_rate(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("价格与资金费率", app)
        self.assertIn("8 小时等价资金费率", app)
        self.assertIn("24 小时价格变化", app)
        self.assertIn("本期资金费率", app)
        self.assertIn("年化等价只用来比较", app)

    def test_cross_asset_panel_uses_one_mobile_chart_and_clear_boundaries(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        styles = (PROJECT_ROOT / "web" / "assets" / "app.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="flow-cross-asset"', app)
        self.assertIn('role="tablist" aria-label="选择跨资产比较"', app)
        self.assertIn("这是相对走势，不是资金流向", app)
        self.assertIn("广义美元不是 ICE DXY", app)
        self.assertIn("drawCrossAssetDualChart", app)
        self.assertIn(".cross-asset-tabs", styles)
        self.assertIn("min-height: 2.75rem", styles)

    def test_yen_carry_panel_separates_incentive_from_unwind_pressure(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        styles = (PROJECT_ROOT / "web" / "assets" / "app.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="flow-yen-carry"', app)
        self.assertIn("套息动力", app)
        self.assertIn("平仓压力", app)
        self.assertIn("不属于联储净流动性公式", app)
        self.assertIn('role="tablist" aria-label="选择日元套息图表"', app)
        self.assertIn("与套息平仓相符，不能证明因果", app)
        self.assertIn(".yen-carry-tabs", styles)
        self.assertIn("overflow-x: auto", styles)

    def test_frontend_separates_current_run_from_stability_gate(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        styles = (PROJECT_ROOT / "web" / "assets" / "app.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("SOAK_STATUS_LABELS", app)
        self.assertIn("soakStatusClass", app)
        self.assertIn("当前数据", app)
        self.assertIn("稳定性观察", app)
        self.assertIn("status-observing", styles)

    def test_frontend_uses_runtime_data_status_not_only_publication_status(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("function effectiveDataStatus(status)", app)
        self.assertIn('stale: "数据已过期"', app)
        self.assertIn("const currentStatusCode = effectiveDataStatus(data.status)", app)
        self.assertIn("当前数据已经过期", app)
        self.assertIn("status.service_status?.code", app)
        self.assertIn("status.update_status?.code", app)
        model = (PROJECT_ROOT / "src" / "liquidity_dashboard" / "model.py").read_text(encoding="utf-8")
        self.assertIn('publication_status == "publish_degraded"', model)
        self.assertIn('"analysis_eligible": runtime_analysis_allowed', model)

    def test_mobile_overview_places_real_trend_before_component_evidence(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        styles = (PROJECT_ROOT / "web" / "assets" / "app.css").read_text(
            encoding="utf-8"
        )

        trend_index = app.index('<section class="trend-panel"')
        evidence_index = app.index('<section class="overview-evidence"')
        self.assertLess(trend_index, evidence_index)
        self.assertIn('"trust"\n    "story"\n    "trend"\n    "evidence"', styles)
        self.assertIn(".overview-evidence", styles)

    def test_transmission_navigation_and_accessible_tabs_are_complete(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('class="transmission-jump-nav"', app)
        self.assertIn('id="flow-${escapeHTML(step.id)}"', app)
        self.assertIn('data-flow-target="flow-money_market"', app)
        self.assertIn('role="tabpanel"', app)
        self.assertIn('aria-controls="crypto-panel-', app)
        self.assertIn("moveCryptoTabFocus", app)
        self.assertIn("announceViewChange", app)

    def test_polymarket_policy_path_shows_cuts_and_hikes_without_netting(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('topic_id === "fed_hike_distribution"', app)
        self.assertIn("全年次数盘口", app)
        self.assertIn("降息和加息两组可能同时非零", app)
        self.assertIn("未归一化", app)
        self.assertIn("data-expectation-toggle", app)
        self.assertIn("高成交宏观盘口", app)
        self.assertIn("仅展示未到期市场", app)
        self.assertIn("topic.state === \"ready\"", app)

    def test_frontend_uses_plain_errors_and_no_accent_side_stripes(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        styles = (PROJECT_ROOT / "web" / "assets" / "app.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("plainChannelIssue", app)
        self.assertIn("RRP 停放资金", app)
        self.assertNotIn("border-left: 3px", styles)

    def test_stablecoin_section_is_explicitly_internal_crypto_liquidity(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("加密内部流动性", app)
        self.assertIn("链上美元容量正在怎样变化", app)
        self.assertIn("不代表资金已经买入加密资产", app)
        self.assertIn('data-stablecoin-chart', app)
        self.assertIn('stablecoin_core_max_depeg_bps', app)
        self.assertIn('data-stablecoin-mode="${id}"', app)
        self.assertIn('data-stablecoin-range="${id}"', app)
        self.assertIn('["1m", "3m", "1y", "5y", "all"]', app)
        self.assertIn("区间累计增减", app)

    def test_etf_ranges_only_show_distinct_available_history(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('const ETF_SESSION_RANGES = { "5d": 5, "20d": 20 }', app)
        self.assertIn("function distinctEtfRanges", app)
        self.assertIn("availableRanges.map", app)
        self.assertIn("历史每天自动累积", app)

    def test_tabs_preserve_independent_scroll_positions(self) -> None:
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("SCROLL_POSITIONS_KEY", app)
        self.assertIn("saveCurrentScrollPosition", app)
        self.assertIn("state.scrollPositions[state.view]", app)
        self.assertNotIn('window.scrollTo({ top: 0, behavior: "instant" })', app)

    def test_frontend_urls_are_safe_under_a_reverse_proxy_subpath(self) -> None:
        index = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
        app = (PROJECT_ROOT / "web" / "assets" / "app.js").read_text(
            encoding="utf-8"
        )
        manifest = json.loads(
            (PROJECT_ROOT / "web" / "manifest.webmanifest").read_text(
                encoding="utf-8"
            )
        )
        service_worker = (PROJECT_ROOT / "web" / "sw.js").read_text(
            encoding="utf-8"
        )

        self.assertIn('href="manifest.webmanifest"', index)
        self.assertNotIn('href="/assets/', index)
        self.assertNotIn('src="/assets/', index)
        self.assertIn('appUrl("api/dashboard")', app)
        self.assertIn('appUrl(`api/series?', app)
        self.assertIn('appUrl("sw.js")', app)
        self.assertEqual(manifest["start_url"], "./#overview")
        self.assertEqual(manifest["scope"], "./")
        self.assertEqual(manifest["icons"][0]["src"], "assets/icon.svg")
        self.assertIn("self.registration.scope", service_worker)
        self.assertNotIn('startsWith("/api/")', service_worker)
        self.assertIn('window.location.protocol === "file:"', index)
        self.assertIn('https://shushu.host/liquidity/', index)

    def test_public_release_is_validated_and_excludes_local_only_files(self) -> None:
        if not (PROJECT_ROOT / "data" / "snapshots" / "latest.json").is_file():
            self.skipTest("requires a local validated runtime snapshot")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "release"
            manifest = build_release(PROJECT_ROOT, output)
            paths = {item["path"] for item in manifest["files"]}
            self.assertEqual(
                manifest["snapshot_run_id"],
                json.loads(
                    (PROJECT_ROOT / "data" / "snapshots" / "latest.json").read_text(
                        encoding="utf-8"
                    )
                )["run_id"],
            )
            self.assertIn("data/channel.sqlite3", paths)
            self.assertIn("data/release.json", paths)
            release = json.loads((output / "data" / "release.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["release_id"], release["release_id"])
            self.assertTrue(manifest["release_id"].startswith("release-"))
            self.assertIn("data/analysis/shadow/latest.json", paths)
            if (PROJECT_ROOT / "data" / "cross-asset" / "latest.json").is_file():
                self.assertIn("data/cross-asset/latest.json", paths)
                self.assertIn("data/cross-asset/history.json", paths)
            self.assertNotIn("config/production-deploy.json", paths)
            self.assertNotIn("config/production-known-hosts", paths)
            self.assertNotIn("data/status/latest-agent-run.json", paths)
            self.assertNotIn("data/status/latest-run.json", paths)
            self.assertNotIn("data/status/latest-public-deploy.json", paths)
            self.assertFalse(any(path.startswith("data/raw/") for path in paths))
            self.assertFalse(any("__pycache__" in path for path in paths))
            self.assertFalse(any(path.endswith(("-wal", "-shm")) for path in paths))


class DashboardServerTests(unittest.TestCase):
    def test_series_api_rejects_a_different_release_identity(self) -> None:
        server_source = (PROJECT_ROOT / "src" / "liquidity_dashboard" / "server.py").read_text(encoding="utf-8")
        self.assertIn('requested_release_id != payload.get("release_id")', server_source)
        self.assertIn("HTTPStatus.CONFLICT", server_source)

    def test_api_errors_do_not_expose_internal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "web").mkdir()
            (root / "web" / "index.html").write_text("safe", encoding="utf-8")
            server = create_server(root, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=3
                )
                connection.request("GET", "/api/dashboard")
                response = connection.getresponse()
                body = response.read().decode("utf-8")
                self.assertEqual(response.status, 503)
                self.assertIn("dashboard data unavailable", body)
                self.assertNotIn(str(root), body)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_static_server_blocks_path_traversal_and_sets_security_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "web").mkdir()
            (root / "web" / "index.html").write_text("safe", encoding="utf-8")
            (root / "secret.txt").write_text("secret", encoding="utf-8")
            server = create_server(root, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=3
                )
                connection.request("GET", "/../secret.txt")
                response = connection.getresponse()
                body = response.read()
                self.assertEqual(response.status, 404)
                self.assertNotIn(b"secret", body)
                self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")

                connection.request("GET", "/missing-static-file.js")
                missing = connection.getresponse()
                missing.read()
                self.assertEqual(missing.status, 404)
                self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_server_follows_an_atomically_switched_current_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            releases = root / "releases"
            for name in ("one", "two"):
                (releases / name / "web").mkdir(parents=True)
                (releases / name / "web" / "index.html").write_text(
                    name, encoding="utf-8"
                )
            current = root / "current"
            current.symlink_to(releases / "one", target_is_directory=True)
            server = create_server(current, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = http.client.HTTPConnection(
                    "127.0.0.1", server.server_address[1], timeout=3
                )
                connection.request("GET", "/")
                first = connection.getresponse()
                self.assertEqual(first.read(), b"one")

                replacement = root / "current.next"
                replacement.symlink_to(releases / "two", target_is_directory=True)
                replacement.replace(current)

                connection.request("GET", "/")
                second = connection.getresponse()
                self.assertEqual(second.read(), b"two")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
