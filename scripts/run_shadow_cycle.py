#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS_DIR = ROOT / "data" / "status"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def notify(message: str) -> None:
    script = f'display notification "{message}" with title "宏观流动性数据通道"'
    subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one auditable shadow cycle.")
    parser.add_argument("--notify", action="store_true")
    parser.add_argument(
        "--skip-agent",
        action="store_true",
        help="Run only the deterministic data channel and skip Codex analysis.",
    )
    parser.add_argument(
        "--skip-deploy",
        action="store_true",
        help="Do not publish a validated snapshot to the production dashboard.",
    )
    parser.add_argument("--minimum-free-gib", type=float, default=20.0)
    parser.add_argument("--hard-stop-free-gib", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = utc_now()
    free_gib = shutil.disk_usage(ROOT).free / (1024**3)
    cycle: dict[str, object] = {
        "started_at": started_at,
        "completed_at": None,
        "free_gib_before": round(free_gib, 2),
        "minimum_free_gib": args.minimum_free_gib,
        "hard_stop_free_gib": args.hard_stop_free_gib,
        "disk_warning": free_gib < args.minimum_free_gib,
        "channel_exit_code": None,
        "health_exit_code": None,
        "stablecoin_exit_code": None,
        "stablecoin_status": "pending",
        "crypto_etf_exit_code": None,
        "crypto_etf_status": "pending",
        "crypto_derivatives_exit_code": None,
        "crypto_derivatives_status": "pending",
        "cross_asset_exit_code": None,
        "cross_asset_status": "pending",
        "yen_carry_exit_code": None,
        "yen_carry_status": "pending",
        "energy_exit_code": None,
        "energy_status": "pending",
        "context_exit_code": None,
        "expectations_exit_code": None,
        "expectations_status": "pending",
        "agent_exit_code": None,
        "agent_health_exit_code": None,
        "agent_status": "pending",
        "deploy_status": "pending",
        "deploy_exit_code": None,
        "status": "running",
    }
    atomic_json(STATUS_DIR / "latest-shadow-cycle.json", cycle)

    if free_gib < args.hard_stop_free_gib:
        cycle.update(
            {
                "completed_at": utc_now(),
                "status": "blocked_low_disk",
                "error": "free disk is below the hard-stop threshold",
            }
        )
        atomic_json(STATUS_DIR / "latest-shadow-cycle.json", cycle)
        if args.notify:
            notify("磁盘空间低于硬门槛，今天的数据运行已阻止。")
        return 4

    channel = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_data_channel.py"),
            "--direct",
        ],
        cwd=ROOT,
        check=False,
    )
    cycle["channel_exit_code"] = channel.returncode

    health = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_channel_health.py"),
            "--days",
            "14",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["health_exit_code"] = health.returncode
    if health.stdout.strip():
        try:
            health_payload = json.loads(health.stdout)
            atomic_json(STATUS_DIR / "health-14d.json", health_payload)
            print(json.dumps(health_payload, ensure_ascii=False, indent=2))
        except json.JSONDecodeError:
            cycle["health_parse_error"] = health.stdout[-1000:]
    if health.stderr.strip():
        cycle["health_stderr"] = health.stderr[-1000:]

    latest_run_path = STATUS_DIR / "latest-run.json"
    if latest_run_path.exists():
        latest_run = json.loads(latest_run_path.read_text(encoding="utf-8"))
        cycle["run_id"] = latest_run.get("run_id")
        cycle["publication_status"] = latest_run.get("publication", {}).get("status")
        cycle["analysis_allowed"] = latest_run.get("publication", {}).get(
            "analysis_allowed"
        )

    stablecoins = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_stablecoin_channel.py"),
            "--direct",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["stablecoin_exit_code"] = stablecoins.returncode
    if stablecoins.stdout.strip():
        try:
            stablecoin_payload = json.loads(stablecoins.stdout)
            cycle["stablecoin_status"] = stablecoin_payload.get("status", "unknown")
            cycle["stablecoin_quality_status"] = stablecoin_payload.get(
                "quality_status"
            )
            cycle["stablecoin_observed_at"] = stablecoin_payload.get("observed_at")
        except json.JSONDecodeError:
            cycle["stablecoin_status"] = "invalid_runner_output"
            cycle["stablecoin_stdout_tail"] = stablecoins.stdout[-2000:]
    if stablecoins.stderr.strip():
        cycle["stablecoin_stderr_tail"] = stablecoins.stderr[-2000:]

    crypto_etf = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_crypto_etf_channel.py"),
            "--direct",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["crypto_etf_exit_code"] = crypto_etf.returncode
    if crypto_etf.stdout.strip():
        try:
            etf_payload = json.loads(crypto_etf.stdout)
            cycle["crypto_etf_status"] = etf_payload.get("status", "unknown")
            cycle["crypto_etf_quality_status"] = etf_payload.get("quality_status")
            cycle["crypto_etf_credential_status"] = etf_payload.get(
                "credential_status"
            )
            cycle["crypto_etf_available_assets"] = etf_payload.get(
                "available_assets", []
            )
        except json.JSONDecodeError:
            cycle["crypto_etf_status"] = "invalid_runner_output"
            cycle["crypto_etf_stdout_tail"] = crypto_etf.stdout[-2000:]
    if crypto_etf.stderr.strip():
        cycle["crypto_etf_stderr_tail"] = crypto_etf.stderr[-2000:]

    crypto_derivatives = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_crypto_derivatives_channel.py"),
            "--direct",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["crypto_derivatives_exit_code"] = crypto_derivatives.returncode
    if crypto_derivatives.stdout.strip():
        try:
            derivatives_payload = json.loads(crypto_derivatives.stdout)
            cycle["crypto_derivatives_status"] = derivatives_payload.get(
                "status", "unknown"
            )
            cycle["crypto_derivatives_quality_status"] = derivatives_payload.get(
                "quality_status"
            )
            cycle["crypto_derivatives_available_assets"] = derivatives_payload.get(
                "available_assets", []
            )
        except json.JSONDecodeError:
            cycle["crypto_derivatives_status"] = "invalid_runner_output"
            cycle["crypto_derivatives_stdout_tail"] = crypto_derivatives.stdout[-2000:]
    if crypto_derivatives.stderr.strip():
        cycle["crypto_derivatives_stderr_tail"] = crypto_derivatives.stderr[-2000:]

    cross_asset = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_cross_asset_channel.py"),
            "--direct",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["cross_asset_exit_code"] = cross_asset.returncode
    if cross_asset.stdout.strip():
        try:
            cross_asset_payload = json.loads(cross_asset.stdout)
            cycle["cross_asset_status"] = cross_asset_payload.get(
                "status", "unknown"
            )
            cycle["cross_asset_quality_status"] = cross_asset_payload.get(
                "quality_status"
            )
            cycle["cross_asset_comparisons"] = cross_asset_payload.get(
                "comparisons", {}
            )
        except json.JSONDecodeError:
            cycle["cross_asset_status"] = "invalid_runner_output"
            cycle["cross_asset_stdout_tail"] = cross_asset.stdout[-2000:]
    if cross_asset.stderr.strip():
        cycle["cross_asset_stderr_tail"] = cross_asset.stderr[-2000:]

    yen_carry = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_yen_carry_channel.py"),
            "--direct",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["yen_carry_exit_code"] = yen_carry.returncode
    if yen_carry.stdout.strip():
        try:
            yen_payload = json.loads(yen_carry.stdout)
            cycle["yen_carry_status"] = yen_payload.get("status", "unknown")
            cycle["yen_carry_quality_status"] = yen_payload.get(
                "quality_status"
            )
            cycle["yen_carry_states"] = yen_payload.get("states", {})
        except json.JSONDecodeError:
            cycle["yen_carry_status"] = "invalid_runner_output"
            cycle["yen_carry_stdout_tail"] = yen_carry.stdout[-2000:]
    if yen_carry.stderr.strip():
        cycle["yen_carry_stderr_tail"] = yen_carry.stderr[-2000:]

    energy = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_energy_channel.py"), "--direct"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["energy_exit_code"] = energy.returncode
    if energy.stdout.strip():
        try:
            energy_payload = json.loads(energy.stdout)
            cycle["energy_status"] = energy_payload.get("status", "unknown")
            cycle["energy_quality_status"] = energy_payload.get("quality_status")
        except json.JSONDecodeError:
            cycle["energy_status"] = "invalid_runner_output"
            cycle["energy_stdout_tail"] = energy.stdout[-2000:]
    if energy.stderr.strip():
        cycle["energy_stderr_tail"] = energy.stderr[-2000:]

    premium = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_coinbase_premium.py"), "--direct"],
        cwd=ROOT, check=False, capture_output=True, text=True,
    )
    cycle["coinbase_premium_exit_code"] = premium.returncode
    try:
        cycle["coinbase_premium_status"] = json.loads(premium.stdout).get("status", "unknown")
    except (ValueError, AttributeError):
        cycle["coinbase_premium_status"] = "unavailable"
    if premium.stderr.strip():
        cycle["coinbase_premium_stderr_tail"] = premium.stderr[-2000:]

    expectations = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_market_expectations.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["expectations_exit_code"] = expectations.returncode
    if expectations.stdout.strip():
        try:
            expectations_payload = json.loads(expectations.stdout)
            cycle["expectations_status"] = expectations_payload.get(
                "status", "unknown"
            )
            cycle["expectations_ready_topic_count"] = expectations_payload.get(
                "ready_topic_count", 0
            )
            cycle["expectations_topic_count"] = expectations_payload.get(
                "topic_count", 0
            )
        except json.JSONDecodeError:
            cycle["expectations_status"] = "invalid_runner_output"
            cycle["expectations_stdout_tail"] = expectations.stdout[-2000:]
    if expectations.stderr.strip():
        cycle["expectations_stderr_tail"] = expectations.stderr[-2000:]

    context = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_context_channel.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["context_exit_code"] = context.returncode
    if context.stdout.strip():
        try:
            context_payload = json.loads(context.stdout)
            cycle["context_status"] = context_payload.get("status")
            cycle["context_bundle_id"] = context_payload.get("bundle_id")
            cycle["context_counts"] = {
                "past_24h": context_payload.get("past_24h_count", 0),
                "future_90d": context_payload.get("future_90d_count", 0),
            }
            cycle["context_failed_sources"] = context_payload.get("failed_sources", [])
        except json.JSONDecodeError:
            cycle["context_status"] = "invalid_runner_output"
            cycle["context_stdout_tail"] = context.stdout[-2000:]
    if context.stderr.strip():
        cycle["context_stderr_tail"] = context.stderr[-2000:]

    if args.skip_agent:
        cycle["agent_status"] = "skipped_by_flag"
    elif channel.returncode == 0 and cycle.get("analysis_allowed") is True:
        agent = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_agent_analysis.py"),
                "--mode",
                "shadow",
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        cycle["agent_exit_code"] = agent.returncode
        if agent.stdout.strip():
            try:
                agent_payload = json.loads(agent.stdout)
                cycle["agent_status"] = agent_payload.get("state", "unknown")
                cycle["agent_analysis_id"] = agent_payload.get("analysis_id")
                cycle["agent_run_dir"] = agent_payload.get("run_dir")
            except json.JSONDecodeError:
                cycle["agent_status"] = "invalid_runner_output"
                cycle["agent_stdout_tail"] = agent.stdout[-2000:]
        if agent.stderr.strip():
            cycle["agent_stderr_tail"] = agent.stderr[-2000:]
        if agent.returncode != 0 and args.notify:
            notify("今天的数据已更新，但 Agent 分析没有通过校验。")
    else:
        cycle["agent_status"] = "skipped_by_data_gate"

    agent_health = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_agent_health.py"),
            "--days",
            "14",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    cycle["agent_health_exit_code"] = agent_health.returncode
    if agent_health.stdout.strip():
        try:
            agent_health_payload = json.loads(agent_health.stdout)
            cycle["agent_gate_state"] = agent_health_payload.get("state")
            cycle["agent_gate_progress"] = {
                "observed_distinct_dates": agent_health_payload.get(
                    "observed_distinct_dates"
                ),
                "required_distinct_dates": agent_health_payload.get(
                    "required_distinct_dates"
                ),
                "hard_pass": agent_health_payload.get("hard_pass"),
            }
        except json.JSONDecodeError:
            cycle["agent_health_stdout_tail"] = agent_health.stdout[-1000:]
    if agent_health.stderr.strip():
        cycle["agent_health_stderr"] = agent_health.stderr[-1000:]

    if channel.returncode == 0:
        cycle["status"] = "completed"
    elif channel.returncode == 2:
        cycle["status"] = "completed_analysis_blocked"
        if args.notify:
            notify("今天的数据已保存，但质量门禁阻止了分析。")
    else:
        cycle["status"] = "failed"
        if args.notify:
            notify("今天的数据通道运行失败，请查看运行日志。")
    cycle["completed_at"] = utc_now()
    cycle["free_gib_after"] = round(shutil.disk_usage(ROOT).free / (1024**3), 2)
    atomic_json(STATUS_DIR / "latest-shadow-cycle.json", cycle)

    deploy_failed = False
    deploy_config_path = ROOT / "config" / "production-deploy.json"
    deploy_enabled = False
    try:
        deploy_config = json.loads(deploy_config_path.read_text(encoding="utf-8"))
        deploy_enabled = deploy_config.get("enabled") is True
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        deploy_config = {}

    if args.skip_deploy:
        cycle["deploy_status"] = "skipped_by_flag"
    elif channel.returncode != 0:
        cycle["deploy_status"] = "skipped_by_data_gate"
    elif not deploy_enabled:
        cycle["deploy_status"] = "not_configured"
    else:
        deployment = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "deploy_public_dashboard.py")],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        cycle["deploy_exit_code"] = deployment.returncode
        if deployment.stdout.strip():
            try:
                deployment_payload = json.loads(deployment.stdout)
                cycle["deploy_status"] = deployment_payload.get("status", "unknown")
                cycle["deployment_release_id"] = deployment_payload.get("release_id")
                cycle["deployment_public_url"] = deployment_payload.get("public_url")
                cycle["deployment_error"] = deployment_payload.get("error")
            except json.JSONDecodeError:
                cycle["deploy_status"] = "invalid_runner_output"
                cycle["deployment_stdout_tail"] = deployment.stdout[-2000:]
        if deployment.stderr.strip():
            cycle["deployment_stderr_tail"] = deployment.stderr[-2000:]
        if deployment.returncode != 0:
            deploy_failed = True
            cycle["status"] = "completed_deploy_failed"
            if args.notify:
                notify("今天的数据已经更新，但公网看板发布失败，服务器仍保留上一版。")

    atomic_json(STATUS_DIR / "latest-shadow-cycle.json", cycle)
    if deploy_failed:
        return 5
    return 0 if channel.returncode in {0, 2} else channel.returncode


if __name__ == "__main__":
    raise SystemExit(main())
