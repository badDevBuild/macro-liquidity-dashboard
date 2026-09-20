from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class NginxPatchTests(unittest.TestCase):
    def test_patcher_requires_an_explicit_config_and_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "dashboard.conf"
            anchor = "    # dashboard insertion point"
            config.write_text(f"server {{\n{anchor}\n}}\n", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / "deploy" / "server" / "patch_nginx_liquidity.py"),
                    "--config",
                    str(config),
                    "--anchor",
                    anchor,
                    "--url-prefix",
                    "/macro",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            updated = config.read_text(encoding="utf-8")
            self.assertIn("location = /macro", updated)
            self.assertIn("proxy_pass http://127.0.0.1:8877/", updated)
            self.assertEqual(updated.count(anchor), 1)


if __name__ == "__main__":
    unittest.main()
