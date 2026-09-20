#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_public_release import build_release  # noqa: E402


SAFE_TOKEN = re.compile(r"^[A-Za-z0-9._-]+$")
SAFE_REMOTE_ROOT = re.compile(r"^/[A-Za-z0-9._/-]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("deployment config must be a JSON object")
    if payload.get("enabled") is not True:
        raise ValueError("production deployment is disabled")
    for field in ("host", "user", "remote_root", "service_name", "public_url"):
        if not isinstance(payload.get(field), str) or not payload[field]:
            raise ValueError(f"deployment config is missing {field}")
    if not SAFE_TOKEN.fullmatch(payload["host"]):
        raise ValueError("deployment host is invalid")
    if not SAFE_TOKEN.fullmatch(payload["user"]):
        raise ValueError("deployment user is invalid")
    if not SAFE_TOKEN.fullmatch(payload["service_name"]):
        raise ValueError("deployment service_name is invalid")
    if not SAFE_REMOTE_ROOT.fullmatch(payload["remote_root"]):
        raise ValueError("deployment remote_root is invalid")
    identity = Path(str(payload.get("identity_file", ""))).expanduser()
    if not identity.is_file():
        raise FileNotFoundError(f"deployment identity is unavailable: {identity}")
    payload["identity_file"] = str(identity)
    known_hosts = Path(str(payload.get("known_hosts_file", ""))).expanduser()
    if not known_hosts.is_file():
        raise FileNotFoundError(f"known-hosts file is unavailable: {known_hosts}")
    payload["known_hosts_file"] = str(known_hosts)
    payload["port"] = int(payload.get("port", 22))
    payload["retain_releases"] = max(2, int(payload.get("retain_releases", 7)))
    return payload


def run_checked(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        input=input_text,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "command failed"
        raise RuntimeError(message[-4000:])
    return completed


def ssh_base(config: dict[str, Any]) -> list[str]:
    return [
        "/usr/bin/ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f'UserKnownHostsFile={config["known_hosts_file"]}',
        "-o",
        "ConnectTimeout=15",
        "-p",
        str(config["port"]),
        "-i",
        config["identity_file"],
        f'{config["user"]}@{config["host"]}',
    ]


ACTIVATE_SCRIPT = r"""
set -euo pipefail
root="$1"
release="$2"
service="$3"
release_dir="$root/releases/$release"
test -d "$release_dir"
PYTHONPATH="$release_dir/src" PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -c 'import sys; from pathlib import Path; from liquidity_dashboard.model import build_dashboard; result = build_dashboard(Path(sys.argv[1])); assert result.get("snapshot", {}).get("run_id")' "$release_dir"
previous="$(readlink "$root/current" 2>/dev/null || true)"
candidate="$root/current.next.$$"
ln -sfn "releases/$release" "$candidate"
mv -Tf "$candidate" "$root/current"

rollback() {
  if [ -n "$previous" ]; then
    ln -sfn "$previous" "$root/current.rollback.$$"
    mv -Tf "$root/current.rollback.$$" "$root/current"
    sudo -n /usr/bin/systemctl restart "$service" >/dev/null 2>&1 || true
  else
    rm -f "$root/current"
    sudo -n /usr/bin/systemctl stop "$service" >/dev/null 2>&1 || true
  fi
}

if ! sudo -n /usr/bin/systemctl restart "$service"; then
  rollback
  exit 21
fi

healthy=0
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  if /usr/bin/curl -fsS --max-time 3 http://127.0.0.1:8877/healthz >/dev/null; then
    healthy=1
    break
  fi
  sleep 1
done
if [ "$healthy" -ne 1 ]; then
  rollback
  exit 22
fi
printf 'previous=%s\n' "$previous"
"""


ROLLBACK_SCRIPT = r"""
set -euo pipefail
root="$1"
previous="$2"
service="$3"
if [ -n "$previous" ]; then
  ln -sfn "$previous" "$root/current.rollback.$$"
  mv -Tf "$root/current.rollback.$$" "$root/current"
  sudo -n /usr/bin/systemctl restart "$service"
else
  rm -f "$root/current"
  sudo -n /usr/bin/systemctl stop "$service"
fi
"""


CLEANUP_SCRIPT = r"""
set -euo pipefail
root="$1"
keep="$2"
current="$(readlink "$root/current" 2>/dev/null || true)"
count=0
find "$root/releases" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -r | while IFS= read -r release; do
  count=$((count + 1))
  if [ "$count" -le "$keep" ] || [ "releases/$release" = "$current" ]; then
    continue
  fi
  rm -rf -- "$root/releases/$release"
done
"""


def http_bytes(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": "macro-liquidity-deployer/1.0"})
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"public check returned HTTP {response.status}: {url}")
        return response.read(), response.headers.get_content_type()


def deploy(config_path: Path) -> dict[str, Any]:
    config = read_config(config_path)
    started_at = utc_now()
    status_path = ROOT / "data" / "status" / "latest-public-deploy.json"
    status: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "running",
        "started_at": started_at,
        "completed_at": None,
        "public_url": config["public_url"],
    }
    atomic_json(status_path, status)

    with tempfile.TemporaryDirectory(prefix="macro-liquidity-release-") as temporary:
        snapshot = json.loads(
            (ROOT / "data" / "snapshots" / "latest.json").read_text(encoding="utf-8")
        )
        snapshot_run_id = str(snapshot.get("run_id") or "")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        release_id = f"{stamp}-{snapshot_run_id[:15]}"
        if not SAFE_TOKEN.fullmatch(release_id):
            raise ValueError("generated release id is invalid")
        bundle = Path(temporary) / release_id
        manifest = build_release(ROOT, bundle)
        status.update(
            {
                "release_id": release_id,
                "snapshot_run_id": manifest["snapshot_run_id"],
                "agent_state": manifest.get("agent_state"),
                "agent_analysis_id": manifest.get("agent_analysis_id"),
            }
        )
        atomic_json(status_path, status)

        remote_release = f'{config["remote_root"]}/releases/{release_id}'
        base = ssh_base(config)
        run_checked(base + ["mkdir", "-p", "--", remote_release])

        ssh_transport = shlex.join(base[:-1])
        run_checked(
            [
                "/usr/bin/rsync",
                "-az",
                "--delete",
                "-e",
                ssh_transport,
                f"{bundle}/",
                f'{config["user"]}@{config["host"]}:{remote_release}/',
            ],
            timeout=300,
        )

        activation = run_checked(
            base
            + [
                "bash",
                "-s",
                "--",
                config["remote_root"],
                release_id,
                config["service_name"],
            ],
            input_text=ACTIVATE_SCRIPT,
        )
        previous = ""
        for line in activation.stdout.splitlines():
            if line.startswith("previous="):
                previous = line.removeprefix("previous=")

        try:
            base_url = config["public_url"].rstrip("/") + "/"
            health_body, _ = http_bytes(base_url + "healthz")
            health = json.loads(health_body)
            if health.get("status") != "ok":
                raise RuntimeError("public health response is invalid")
            dashboard_body, _ = http_bytes(base_url + "api/dashboard")
            dashboard = json.loads(dashboard_body)
            if dashboard.get("snapshot", {}).get("run_id") != snapshot_run_id:
                raise RuntimeError("public dashboard is serving a different snapshot")
            html, content_type = http_bytes(base_url)
            if b"<title>" not in html or content_type != "text/html":
                raise RuntimeError("public dashboard HTML is invalid")
        except Exception:
            run_checked(
                base
                + [
                    "bash",
                    "-s",
                    "--",
                    config["remote_root"],
                    previous,
                    config["service_name"],
                ],
                input_text=ROLLBACK_SCRIPT,
            )
            raise

        run_checked(
            base
            + [
                "bash",
                "-s",
                "--",
                config["remote_root"],
                str(config["retain_releases"]),
            ],
            input_text=CLEANUP_SCRIPT,
        )

    status.update(
        {
            "status": "published",
            "completed_at": utc_now(),
            "previous_release": previous or None,
        }
    )
    atomic_json(status_path, status)
    return status


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish a validated dashboard release to the production server."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "production-deploy.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status_path = ROOT / "data" / "status" / "latest-public-deploy.json"
    try:
        result = deploy(args.config)
    except Exception as exc:
        failure = {
            "schema_version": "1.0",
            "status": "failed",
            "completed_at": utc_now(),
            "error": str(exc),
        }
        atomic_json(status_path, failure)
        print(json.dumps(failure, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
