from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_dashboard.agent_health import build_agent_health  # noqa: E402


class AgentHealthTests(unittest.TestCase):
    def write_success(self, root: Path, day: date) -> None:
        run_dir = root / "data" / "analysis" / "runs" / day.isoformat() / "analysis"
        run_dir.mkdir(parents=True)
        (run_dir / "context.json").write_text(
            json.dumps(
                {"snapshot_completed_at": f"{day.isoformat()}T06:31:00+08:00"}
            ),
            encoding="utf-8",
        )
        (run_dir / "status.json").write_text(
            json.dumps(
                {
                    "mode": "shadow",
                    "state": "shadow_ready",
                    "snapshot_run_id": f"run-{day.isoformat()}",
                    "analysis_id": f"analysis-{day.isoformat()}",
                    "completed_at": f"{day.isoformat()}T06:33:00+08:00",
                    "attempts": [
                        {
                            "validation_errors": [],
                            "tokens_used": 1000,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def write_approval(self, root: Path, approved: bool) -> None:
        (root / "config").mkdir(parents=True, exist_ok=True)
        (root / "config" / "agent-production-approval.json").write_text(
            json.dumps(
                {
                    "approved": approved,
                    "reviewed_at": "2026-09-10T08:00:00+08:00" if approved else None,
                    "reviewed_by": "user" if approved else None,
                    "review_note": "reviewed",
                }
            ),
            encoding="utf-8",
        )

    def test_fourteen_dates_still_wait_for_semantic_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = date(2026, 8, 28)
            for offset in range(14):
                self.write_success(root, start + timedelta(days=offset))
            self.write_approval(root, False)
            result = build_agent_health(root)

        self.assertTrue(result["deterministic_gate_passed"])
        self.assertEqual(result["state"], "awaiting_semantic_approval")
        self.assertFalse(result["hard_pass"])

    def test_hard_pass_requires_both_fourteen_dates_and_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            start = date(2026, 8, 28)
            for offset in range(14):
                self.write_success(root, start + timedelta(days=offset))
            self.write_approval(root, True)
            result = build_agent_health(root)

        self.assertEqual(result["state"], "hard_pass")
        self.assertTrue(result["hard_pass"])
        self.assertEqual(result["total_tokens_used"], 14_000)


if __name__ == "__main__":
    unittest.main()
