from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_dashboard.agent_runtime import (  # noqa: E402
    _analysis_delta,
    _codex_subprocess_environment,
    _repair_diagnostics,
    build_agent_prompt,
    build_runtime_schema,
    run_agent_analysis,
)
from liquidity_dashboard.agent_analysis import _evidence_matches  # noqa: E402


class AgentRuntimeTests(unittest.TestCase):
    def test_codex_subprocess_environment_drops_unrelated_credentials(self) -> None:
        environment = _codex_subprocess_environment(
            {
                "HOME": "/tmp/example-home",
                "PATH": "/usr/bin",
                "CODEX_HOME": "/tmp/example-codex",
                "SOSOVALUE_API_KEY": "do-not-forward",
                "AWS_SECRET_ACCESS_KEY": "do-not-forward",
                "HTTPS_PROXY": "https://user:password@proxy.example:443",
                "NO_PROXY": "127.0.0.1,localhost",
            }
        )
        self.assertEqual(environment["HOME"], "/tmp/example-home")
        self.assertEqual(environment["CODEX_HOME"], "/tmp/example-codex")
        self.assertEqual(environment["RUST_LOG"], "error")
        self.assertNotIn("SOSOVALUE_API_KEY", environment)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", environment)
        self.assertNotIn("HTTPS_PROXY", environment)
        self.assertEqual(environment["NO_PROXY"], "127.0.0.1,localhost")

    @staticmethod
    def prepare_root(root: Path) -> None:
        config_dir = root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / "agent-analysis.schema.json").write_text(
            (PROJECT_ROOT / "config" / "agent-analysis.schema.json").read_text(
                encoding="utf-8"
            ),
            encoding="utf-8",
        )

    def dashboard(self, *, allowed: bool = True) -> dict:
        publication = {
            "status": "publish" if allowed else "block_analysis",
            "analysis_allowed": allowed,
            "coverage_ratio": 1.0 if allowed else 0.5,
        }
        return {
            "snapshot": {
                "run_id": "run-1",
                "completed_at": "2026-08-28T06:31:00Z",
                "publication": publication,
                "revision_count_detected": 0,
                "reconciliation_issues": [],
            },
            "status": {
                "analysis_allowed": allowed,
                "coverage_ratio": publication["coverage_ratio"],
                "eligible_metric_count": 1 if allowed else 0,
                "total_metric_count": 1,
                "warnings": [],
                "unavailable": [],
                "nonfresh": [],
            },
            "proxy": {
                "id": "net_liquidity_proxy",
                "label": "流动性参考值",
                "technical_label": "净流动性代理值",
                "formula": "美联储总资产 - 财政部现金 - RRP",
                "unit": "usd_millions",
                "value": 5_771_021,
                "observed_at": "2026-08-26",
                "week_change": -38_047,
                "latest_release_change": 20_161,
                "trend_changes": {},
                "trend": [],
                "components": [],
                "contributions": [],
            },
            "metrics": {
                "tga_daily": {
                    "metric_id": "tga_daily",
                    "group": "fiscal_cash",
                    "label": "财政部现金",
                    "source_id": "treasury_tga_daily",
                    "source_name": "Treasury General Account closing balance",
                    "source_url": "https://example.com/tga",
                    "authority": "official_primary",
                    "cadence": "business_daily",
                    "unit": "usd_millions",
                    "value": 959_435,
                    "observed_at": "2026-08-26",
                    "quality_status": "fresh_network",
                    "available_for_analysis": True,
                    "age_days": 2,
                    "changes": {"1w": {"change": 23_029}},
                    "sparkline": [],
                }
            },
        }

    def model_payload(self, *, change: float = 23_029) -> dict:
        return {
            "schema_version": "1.5",
            "prompt_version": "model-guessed-version",
            "analysis_id": "model-guessed-id",
            "snapshot_run_id": "model-guessed-run",
            "context_bundle_id": "model-guessed-context",
            "generated_at": "2020-01-01T00:00:00Z",
            "model": {
                "provider": "model-guessed-provider",
                "id": "model-guessed-id",
                "reasoning_effort": "high",
            },
            "status": "ready",
            "overall_assessment": "tightening",
            "confidence": "medium",
            "headline": "财政现金回补对参考值形成压力",
            "summary": "账本方向偏紧，但仍需结合利率和美元确认。",
            "market_bottom_line": "当前不是单向顺风，需等利率与美元确认。",
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
                        "change": change,
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
                    "claim": "财政部现金上升，对参考值形成抽水。",
                    "effect": "draining",
                    "evidence": [
                        {
                            "metric_id": "tga_daily",
                            "observed_at": "2026-08-26",
                            "value": 959_435,
                            "comparison_window": "1w",
                            "change": change,
                        }
                    ],
                }
            ],
            "contradictions": [],
            "watch_items": [
                {
                    "trigger": "观察财政部现金是否回落",
                    "why": "回落会按公式支持流动性参考值。",
                    "metric_ids": ["tga_daily"],
                }
            ],
            "context_screening_note": "本轮没有可用的新闻事件上下文。",
            "context_assessments": [],
            "unknowns": [],
            "data_quality_note": "测试数据通过门禁。",
        }

    @staticmethod
    def preflight(_cli_path: Path) -> tuple[str, None]:
        return "codex-cli 0.150.1", None

    def test_shadow_run_normalizes_metadata_and_does_not_publish(self) -> None:
        calls = 0

        def invoke(prompt, output_path, schema_path, cli_path, timeout_seconds):
            nonlocal calls
            calls += 1
            self.assertIn("<context>", prompt)
            output_path.write_text(
                json.dumps(self.model_payload(), ensure_ascii=False), encoding="utf-8"
            )
            return {"exit_code": 0, "elapsed_seconds": 1.0, "error": None}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare_root(root)
            with patch(
                "liquidity_dashboard.agent_runtime.build_dashboard",
                return_value=self.dashboard(),
            ):
                result = run_agent_analysis(
                    root,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=1,
                )
            shadow = json.loads(
                (root / "data" / "analysis" / "shadow" / "latest.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertFalse((root / "data" / "analysis" / "latest.json").exists())

        self.assertEqual(calls, 1)
        self.assertEqual(result["state"], "shadow_ready")
        self.assertEqual(shadow["snapshot_run_id"], "run-1")
        self.assertEqual(shadow["prompt_version"], "macro-liquidity-morning-v9")
        self.assertEqual(shadow["context_bundle_id"], "context-unavailable")
        self.assertEqual(shadow["model"]["id"], "gpt-5.6-sol")
        self.assertEqual(shadow["model"]["reasoning_effort"], "medium")

    def test_current_shadow_snapshot_is_idempotent(self) -> None:
        calls = 0

        def invoke(prompt, output_path, schema_path, cli_path, timeout_seconds):
            nonlocal calls
            calls += 1
            output_path.write_text(json.dumps(self.model_payload()), encoding="utf-8")
            return {"exit_code": 0, "elapsed_seconds": 1.0, "error": None}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare_root(root)
            with patch(
                "liquidity_dashboard.agent_runtime.build_dashboard",
                return_value=self.dashboard(),
            ):
                first = run_agent_analysis(
                    root,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=1,
                )
                second = run_agent_analysis(
                    root,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=1,
                )

        self.assertEqual(first["state"], "shadow_ready")
        self.assertEqual(second["state"], "skipped_current")
        self.assertEqual(calls, 1)

    def test_bad_evidence_fails_closed(self) -> None:
        def invoke(prompt, output_path, schema_path, cli_path, timeout_seconds):
            output_path.write_text(
                json.dumps(self.model_payload(change=-23_029)), encoding="utf-8"
            )
            return {"exit_code": 0, "elapsed_seconds": 1.0, "error": None}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare_root(root)
            with patch(
                "liquidity_dashboard.agent_runtime.build_dashboard",
                return_value=self.dashboard(),
            ):
                result = run_agent_analysis(
                    root,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=1,
                )
            self.assertFalse(
                (root / "data" / "analysis" / "shadow" / "latest.json").exists()
            )

        self.assertEqual(result["state"], "failed")
        self.assertIn(
            "drivers contains evidence that does not match the snapshot",
            result["attempts"][0]["validation_errors"],
        )

    def test_runtime_schema_constrains_snapshot_reference_ids(self) -> None:
        base_schema = json.loads(
            (PROJECT_ROOT / "config" / "agent-analysis.schema.json").read_text(
                encoding="utf-8"
            )
        )
        context = {
            "metrics": {"tga_daily": {}},
            "news_and_events": {
                "past_24h": [{"context_id": "ctx-news-1"}],
                "future_90d": [],
            },
        }
        schema = build_runtime_schema(base_schema, context)

        metric_enum = schema["$defs"]["marketImplication"]["properties"][
            "confirm_metric_ids"
        ]["items"]["enum"]
        context_enum = schema["$defs"]["contextAssessment"]["properties"][
            "context_id"
        ]["enum"]
        self.assertIn("tga_daily", metric_enum)
        self.assertIn("net_liquidity_proxy_latest_release", metric_enum)
        self.assertEqual(context_enum, ["ctx-news-1"])

    def test_runtime_schema_allows_daily_evidence_window(self) -> None:
        base_schema = json.loads(
            (PROJECT_ROOT / "config" / "agent-analysis.schema.json").read_text(
                encoding="utf-8"
            )
        )
        context = {"metrics": {"derivatives_btc_price_change_24h": {}}}
        schema = build_runtime_schema(base_schema, context)

        windows = schema["$defs"]["evidence"]["properties"][
            "comparison_window"
        ]["enum"]
        self.assertIn("1d", windows)

    def test_daily_derivatives_evidence_uses_the_canonical_validator(self) -> None:
        metric_id = "derivatives_btc_price_change_24h"
        metrics = {
            metric_id: {
                "metric_id": metric_id,
                "value": 5.1652,
                "observed_at": "2026-09-04T07:30:00Z",
                "available_for_analysis": True,
                "changes": {
                    "1d": {"change": 5.4225, "coverage_matched": True},
                    "1w": {"change": None, "coverage_matched": False},
                },
            }
        }
        delta = {
            "official_updates": [],
            "derived_updates": [],
            "risk_asset_updates": [
                {
                    "metric_id": metric_id,
                    "observed_at": "2026-09-04T07:30:00Z",
                    "value": 5.1652,
                    "change": 5.4225,
                }
            ],
        }
        daily = {
            "metric_id": metric_id,
            "observed_at": "2026-09-04T07:30:00Z",
            "value": 5.1652,
            "comparison_window": "1d",
            "change": 5.4225,
        }
        missing_week = {
            **daily,
            "comparison_window": "1w",
            "change": None,
        }
        since_previous = {
            **daily,
            "comparison_window": "since_previous_run",
        }

        self.assertTrue(_evidence_matches(daily, metrics, {}, delta))
        self.assertFalse(_evidence_matches(missing_week, metrics, {}, delta))
        self.assertTrue(_evidence_matches(since_previous, metrics, {}, delta))

    def test_repair_diagnostics_identifies_named_window_with_null_change(self) -> None:
        metric_id = "derivatives_btc_funding_8h_equivalent"
        context = {
            "metrics": {
                metric_id: {
                    "metric_id": metric_id,
                    "value": 0.0042,
                    "observed_at": "2026-09-04T07:30:00Z",
                    "available_for_analysis": True,
                    "changes": {
                        "1d": {"change": 0.0003, "coverage_matched": True},
                        "1w": {"change": None, "coverage_matched": False},
                    },
                }
            },
            "net_liquidity_proxy": {},
            "net_liquidity_proxy_weekly": {},
            "analysis_delta": {},
            "news_and_events": {"past_24h": [], "future_90d": []},
        }
        submitted = {
            "metric_id": metric_id,
            "observed_at": "2026-09-04T07:30:00Z",
            "value": 0.0042,
            "comparison_window": "1w",
            "change": None,
        }
        diagnostics = _repair_diagnostics(
            {
                "drivers": [{"evidence": [submitted]}],
                "contradictions": [],
                "layer_analysis": [],
            },
            context,
            ["drivers contains evidence that does not match the snapshot"],
        )

        issues = diagnostics["evidence_reference_issues"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["path"], "drivers[0].evidence[0]")
        self.assertIsNone(issues[0]["expected"])
        self.assertIn(
            "1d",
            [option["comparison_window"] for option in issues[0]["valid_options"]],
        )
        self.assertIn(
            None,
            [option["comparison_window"] for option in issues[0]["valid_options"]],
        )

    def test_invalid_derivatives_window_is_repaired_from_exact_options(self) -> None:
        prompts: list[str] = []
        dashboard = self.dashboard()
        metric_id = "derivatives_btc_price_change_24h"
        dashboard["metrics"][metric_id] = {
            "metric_id": metric_id,
            "group": "crypto_derivatives",
            "label": "BTC 24 小时价格变化",
            "source_id": "crypto_derivatives",
            "unit": "percent",
            "value": 5.1652,
            "observed_at": "2026-09-04T07:30:00Z",
            "quality_status": "fresh_network",
            "available_for_analysis": True,
            "changes": {
                "1d": {"change": 5.4225, "coverage_matched": True},
                "1w": {"change": None, "coverage_matched": False},
            },
            "sparkline": [],
        }

        def invoke(prompt, output_path, schema_path, cli_path, timeout_seconds):
            prompts.append(prompt)
            payload = self.model_payload()
            payload["drivers"][0]["evidence"] = [
                {
                    "metric_id": metric_id,
                    "observed_at": "2026-09-04T07:30:00Z",
                    "value": 5.1652,
                    "comparison_window": "1w" if len(prompts) == 1 else "1d",
                    "change": None if len(prompts) == 1 else 5.4225,
                }
            ]
            if len(prompts) == 2:
                self.assertIn(
                    "valid_evidence_options_for_referenced_ids", prompt
                )
                self.assertIn('"comparison_window":"1d"', prompt)
                self.assertIn("drivers[0].evidence[0]", prompt)
            output_path.write_text(json.dumps(payload), encoding="utf-8")
            return {"exit_code": 0, "elapsed_seconds": 1.0, "error": None}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare_root(root)
            with patch(
                "liquidity_dashboard.agent_runtime.build_dashboard",
                return_value=dashboard,
            ):
                result = run_agent_analysis(
                    root,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=2,
                )

        self.assertEqual(result["state"], "shadow_ready")
        self.assertEqual(len(prompts), 2)
        self.assertTrue(result["recovered"])
        self.assertEqual(result["recovery_method"], "targeted_agent_repair")

    def test_concatenated_metric_ids_are_repaired_without_guessing(self) -> None:
        calls = 0

        def invoke(prompt, output_path, schema_path, cli_path, timeout_seconds):
            nonlocal calls
            calls += 1
            runtime_schema = json.loads(schema_path.read_text(encoding="utf-8"))
            allowed = runtime_schema["$defs"]["marketImplication"]["properties"][
                "confirm_metric_ids"
            ]["items"]["enum"]
            self.assertIn("tga_daily", allowed)
            payload = self.model_payload()
            payload["market_implications"]["crypto"]["confirm_metric_ids"] = [
                "tga_daily','net_liquidity_proxy_latest_release"
            ]
            output_path.write_text(json.dumps(payload), encoding="utf-8")
            return {"exit_code": 0, "elapsed_seconds": 1.0, "error": None}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare_root(root)
            with patch(
                "liquidity_dashboard.agent_runtime.build_dashboard",
                return_value=self.dashboard(),
            ):
                result = run_agent_analysis(
                    root,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=3,
                )
            shadow = json.loads(
                (root / "data" / "analysis" / "shadow" / "latest.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(calls, 1)
        self.assertEqual(result["state"], "shadow_ready")
        self.assertTrue(result["recovered"])
        self.assertEqual(result["recovery_method"], "deterministic_reference_repair")
        self.assertEqual(
            shadow["market_implications"]["crypto"]["confirm_metric_ids"],
            ["tga_daily", "net_liquidity_proxy_latest_release"],
        )
        self.assertTrue(result["attempts"][0]["initial_validation_errors"])
        self.assertEqual(result["attempts"][0]["validation_errors"], [])

    def test_validation_failure_uses_targeted_repair_prompt(self) -> None:
        prompts: list[str] = []

        def invoke(prompt, output_path, schema_path, cli_path, timeout_seconds):
            prompts.append(prompt)
            payload = self.model_payload()
            if len(prompts) == 1:
                payload["market_implications"]["crypto"][
                    "confirm_metric_ids"
                ] = ["unknown_metric"]
            output_path.write_text(json.dumps(payload), encoding="utf-8")
            return {"exit_code": 0, "elapsed_seconds": 1.0, "error": None}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare_root(root)
            with patch(
                "liquidity_dashboard.agent_runtime.build_dashboard",
                return_value=self.dashboard(),
            ):
                result = run_agent_analysis(
                    root,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=3,
                )

        self.assertEqual(result["state"], "shadow_ready")
        self.assertEqual(len(prompts), 2)
        self.assertIn("你是宏观流动性晨间分析的修复器", prompts[1])
        self.assertIn("market_implications.crypto.confirm_metric_ids", prompts[1])
        self.assertIn("unknown_metric", prompts[1])
        self.assertEqual(result["attempts"][1]["kind"], "targeted_repair")
        self.assertTrue(result["recovered"])
        self.assertEqual(result["recovery_method"], "targeted_agent_repair")

    def test_over_limit_concatenated_ids_fall_back_to_targeted_repair(self) -> None:
        prompts: list[str] = []
        dashboard = self.dashboard()
        for index in range(8):
            metric_id = f"test_metric_{index}"
            dashboard["metrics"][metric_id] = {
                "metric_id": metric_id,
                "group": "crypto_derivatives",
                "label": metric_id,
                "unit": "index",
                "value": float(index),
                "observed_at": "2026-08-26",
                "quality_status": "fresh_network",
                "available_for_analysis": True,
                "changes": {},
                "sparkline": [],
            }

        def invoke(prompt, output_path, schema_path, cli_path, timeout_seconds):
            prompts.append(prompt)
            payload = self.model_payload()
            if len(prompts) == 1:
                payload["market_implications"]["crypto"][
                    "confirm_metric_ids"
                ] = [
                    "test_metric_0",
                    "test_metric_1",
                    "test_metric_2",
                    "test_metric_3",
                    "test_metric_4",
                    "test_metric_5','test_metric_6','test_metric_7",
                ]
            else:
                payload["market_implications"]["crypto"][
                    "confirm_metric_ids"
                ] = [f"test_metric_{index}" for index in range(6)]
            output_path.write_text(json.dumps(payload), encoding="utf-8")
            return {"exit_code": 0, "elapsed_seconds": 1.0, "error": None}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.prepare_root(root)
            with patch(
                "liquidity_dashboard.agent_runtime.build_dashboard",
                return_value=dashboard,
            ):
                result = run_agent_analysis(
                    root,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=3,
                )

        self.assertEqual(result["state"], "shadow_ready")
        self.assertEqual(len(prompts), 2)
        self.assertEqual(result["attempts"][0]["auto_repair_actions"], [])
        self.assertIn("test_metric_5','test_metric_6','test_metric_7", prompts[1])
        self.assertEqual(result["attempts"][1]["kind"], "targeted_repair")

    def test_data_gate_blocks_before_any_model_call(self) -> None:
        def invoke(*_args):
            raise AssertionError("model must not run when the data gate is closed")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch(
                "liquidity_dashboard.agent_runtime.build_dashboard",
                return_value=self.dashboard(allowed=False),
            ):
                result = run_agent_analysis(
                    root,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=1,
                )

        self.assertEqual(result["state"], "blocked_by_data")

    def test_publish_mode_is_blocked_until_agent_gate_hard_passes(self) -> None:
        def invoke(*_args):
            raise AssertionError("model must not publish before the Agent gate passes")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "data" / "status").mkdir(parents=True)
            (root / "data" / "status" / "agent-health-14d.json").write_text(
                json.dumps({"state": "collecting", "hard_pass": False}),
                encoding="utf-8",
            )
            with patch(
                "liquidity_dashboard.agent_runtime.build_dashboard",
                return_value=self.dashboard(),
            ):
                result = run_agent_analysis(
                    root,
                    publish=True,
                    invoker=invoke,
                    preflight=self.preflight,
                    max_attempts=1,
                )

        self.assertEqual(result["state"], "blocked_by_agent_gate")

    def test_previous_validated_snapshot_drives_daily_update_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "data" / "analysis" / "runs" / "run-0" / "analysis-0"
            run_dir.mkdir(parents=True)
            previous_context = {
                "snapshot_run_id": "run-0",
                "snapshot_completed_at": "2026-08-27T06:30:00Z",
                "metrics": {
                    "tga_daily": {
                        "metric_id": "tga_daily",
                        "label": "财政部现金",
                        "source_id": "treasury_tga_daily",
                        "unit": "usd_millions",
                        "value": 900_000,
                        "observed_at": "2026-08-27",
                    }
                },
                "market_expectations": {"topics": []},
                "data_quality": {"unavailable": []},
            }
            (run_dir / "context.json").write_text(
                json.dumps(previous_context), encoding="utf-8"
            )
            (run_dir / "validated.json").write_text(
                json.dumps(
                    {
                        "analysis_id": "analysis-0",
                        "generated_at": "2026-08-27T06:31:00Z",
                        "headline": "旧判断",
                    }
                ),
                encoding="utf-8",
            )
            current_context = {
                "snapshot_run_id": "run-1",
                "metrics": {
                    "tga_daily": {
                        "metric_id": "tga_daily",
                        "label": "财政部现金",
                        "source_id": "treasury_tga_daily",
                        "unit": "usd_millions",
                        "value": 890_000,
                        "observed_at": "2026-08-28",
                    }
                },
                "market_expectations": {"topics": []},
                "data_quality": {"unavailable": []},
                "reconciliation_issues": [],
            }
            delta = _analysis_delta(root, current_context)

        self.assertEqual(delta["status"], "new_data")
        self.assertEqual(delta["official_updates"][0]["metric_id"], "tga_daily")
        self.assertEqual(delta["official_updates"][0]["change"], -10_000)

    def test_agent_prompt_forbids_netting_hike_and_cut_markets(self) -> None:
        prompt = build_agent_prompt({"market_expectations": {"topics": []}})
        self.assertIn("年度降息次数和年度加息次数都是全年累计盘口", prompt)
        self.assertIn("不得把两组最高概率互减", prompt)
        self.assertIn("probabilities_normalized=false", prompt)

    def test_agent_prompt_keeps_cross_asset_interpretation_boundaries(self) -> None:
        prompt = build_agent_prompt(
            {
                "metrics": {},
                "cross_asset": {"available_for_analysis": True},
            }
        )
        self.assertIn("BTC/美股与 BTC/黄金只表示相对强弱", prompt)
        self.assertIn("PAXG-USD 代理", prompt)
        self.assertIn("不是 ICE DXY", prompt)
        self.assertIn("相关不是因果也不是预测", prompt)

    def test_agent_prompt_keeps_yen_carry_outside_net_liquidity(self) -> None:
        prompt = build_agent_prompt(
            {
                "metrics": {},
                "yen_carry": {"available_for_analysis": True},
            }
        )
        self.assertIn("日元套息不进入净流动性参考值", prompt)
        self.assertIn("分开判断 carry_incentive 与 unwind_pressure", prompt)
        self.assertIn("不代表全球日元套息规模", prompt)
        self.assertIn("与套息平仓相符", prompt)

    def test_event_switch_is_marked_not_comparable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = root / "data" / "analysis" / "runs" / "run-0" / "analysis-0"
            run_dir.mkdir(parents=True)
            previous_context = {
                "snapshot_run_id": "run-0",
                "snapshot_completed_at": "2025-12-31T06:30:00Z",
                "metrics": {},
                "market_expectations": {
                    "topics": [
                        {
                            "topic_id": "fed_hike_distribution",
                            "event_id": "2025-event",
                            "updated_at": "2025-12-31T05:00:00Z",
                            "top_outcome": {
                                "outcome_id": "old-1",
                                "probability": 0.6,
                            },
                        }
                    ]
                },
                "data_quality": {"unavailable": []},
            }
            (run_dir / "context.json").write_text(
                json.dumps(previous_context), encoding="utf-8"
            )
            (run_dir / "validated.json").write_text(
                json.dumps({"analysis_id": "analysis-0"}), encoding="utf-8"
            )
            current_context = {
                "snapshot_run_id": "run-1",
                "metrics": {},
                "market_expectations": {
                    "topics": [
                        {
                            "topic_id": "fed_hike_distribution",
                            "event_id": "2026-event",
                            "updated_at": "2026-01-01T05:00:00Z",
                            "top_outcome": {
                                "outcome_id": "new-1",
                                "probability": 0.4,
                            },
                        }
                    ]
                },
                "data_quality": {"unavailable": []},
                "reconciliation_issues": [],
            }
            delta = _analysis_delta(root, current_context)

        update = delta["market_expectation_updates"][0]
        self.assertTrue(update["event_changed"])
        self.assertEqual(update["comparison_status"], "new_event_not_comparable")
        self.assertIsNone(update["probability_change_percentage_points"])


if __name__ == "__main__":
    unittest.main()
