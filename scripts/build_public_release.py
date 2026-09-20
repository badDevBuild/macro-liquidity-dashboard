#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from liquidity_dashboard.model import build_dashboard  # noqa: E402
from liquidity_dashboard.public_status import public_cycle_status  # noqa: E402


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def copy_file(source: Path, destination: Path, *, required: bool = True) -> bool:
    if not source.is_file():
        if required:
            raise FileNotFoundError(source)
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def backup_database(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source_db:
        with closing(sqlite3.connect(destination)) as destination_db:
            source_db.backup(destination_db)
            result = destination_db.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("release database did not pass integrity_check")
            destination_db.execute("PRAGMA journal_mode=DELETE")
            destination_db.commit()


def selected_analysis(root: Path, snapshot_run_id: str) -> tuple[Path | None, dict[str, Any] | None]:
    for candidate in (
        root / "data" / "analysis" / "latest.json",
        root / "data" / "analysis" / "shadow" / "latest.json",
    ):
        if not candidate.is_file():
            continue
        payload = read_json(candidate)
        if payload.get("snapshot_run_id") == snapshot_run_id:
            return candidate, payload
    return None, None


def file_inventory(root: Path) -> list[dict[str, Any]]:
    inventory = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name == "release-manifest.json":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        inventory.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
    return inventory


def validate_public_json(root: Path) -> None:
    forbidden_fragments = (
        "/Users/",
        "Traceback (most recent call last)",
        "Authorization: Bearer ",
        "x-soso-api-key",
        "sk-proj-",
    )
    for path in root.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        match = next((item for item in forbidden_fragments if item in text), None)
        if match:
            raise ValueError(
                f"public JSON contains forbidden internal fragment {match!r}: "
                f"{path.relative_to(root)}"
            )


def build_release(source_root: Path, output_root: Path) -> dict[str, Any]:
    source_root = source_root.resolve()
    output_root = output_root.absolute()
    if output_root.exists():
        raise FileExistsError(f"release output already exists: {output_root}")
    output_root.mkdir(parents=True)

    try:
        shutil.copytree(source_root / "web", output_root / "web")
        shutil.copytree(
            source_root / "src",
            output_root / "src",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        shutil.copytree(
            source_root / "config",
            output_root / "config",
            ignore=shutil.ignore_patterns(
                "production-deploy.json", "production-known-hosts"
            ),
        )
        copy_file(source_root / "pyproject.toml", output_root / "pyproject.toml")

        snapshot_path = source_root / "data" / "snapshots" / "latest.json"
        snapshot = read_json(snapshot_path)
        snapshot_run_id = str(snapshot.get("run_id") or "")
        if not snapshot_run_id:
            raise ValueError("latest snapshot has no run_id")
        publication = snapshot.get("publication") or {}
        if publication.get("status") not in {"publish", "publish_degraded"}:
            raise ValueError("latest snapshot is not allowed to publish")

        copy_file(snapshot_path, output_root / "data" / "snapshots" / "latest.json")
        backup_database(
            source_root / "data" / "channel.sqlite3",
            output_root / "data" / "channel.sqlite3",
        )
        copy_file(
            source_root / "data" / "expectations" / "latest.json",
            output_root / "data" / "expectations" / "latest.json",
            required=False,
        )
        copy_file(
            source_root / "data" / "stablecoins" / "latest.json",
            output_root / "data" / "stablecoins" / "latest.json",
            required=False,
        )
        for channel in ("etf", "derivatives", "coinbase-premium"):
            for filename in ("latest.json", "history.json"):
                copy_file(
                    source_root / "data" / "crypto" / channel / filename,
                    output_root / "data" / "crypto" / channel / filename,
                    required=False,
                )
        for filename in ("latest.json", "history.json"):
            copy_file(
                source_root / "data" / "cross-asset" / filename,
                output_root / "data" / "cross-asset" / filename,
                required=False,
            )
        for filename in ("latest.json", "history.json"):
            copy_file(
                source_root / "data" / "yen-carry" / filename,
                output_root / "data" / "yen-carry" / filename,
                required=False,
            )
        for filename in ("latest.json", "history.json"):
            copy_file(
                source_root / "data" / "energy" / filename,
                output_root / "data" / "energy" / filename,
                required=False,
            )

        status_source = source_root / "data" / "status"
        for status_name in ("health-14d.json", "agent-health-14d.json"):
            copy_file(
                status_source / status_name,
                output_root / "data" / "status" / status_name,
                required=False,
            )
        cycle_status = read_json(status_source / "latest-shadow-cycle.json")
        write_json(
            output_root / "data" / "status" / "latest-shadow-cycle.json",
            public_cycle_status(cycle_status),
        )

        context_latest = source_root / "data" / "context" / "latest.json"
        copy_file(
            context_latest,
            output_root / "data" / "context" / "latest.json",
            required=False,
        )

        analysis_path, analysis = selected_analysis(source_root, snapshot_run_id)
        if analysis_path and analysis:
            relative_analysis = analysis_path.relative_to(source_root)
            copy_file(analysis_path, output_root / relative_analysis)
            analysis_context_receipt = analysis_path.with_name("latest-context.json")
            copy_file(
                analysis_context_receipt,
                output_root / analysis_context_receipt.relative_to(source_root),
            )
            context_bundle_id = analysis.get("context_bundle_id")
            if context_bundle_id and context_bundle_id != "context-unavailable":
                context_run = (
                    source_root
                    / "data"
                    / "context"
                    / "runs"
                    / f"{context_bundle_id}.json"
                )
                copy_file(
                    context_run,
                    output_root
                    / "data"
                    / "context"
                    / "runs"
                    / context_run.name,
                )

        dashboard = build_dashboard(output_root)
        if dashboard.get("snapshot", {}).get("run_id") != snapshot_run_id:
            raise ValueError("release snapshot does not match the source snapshot")
        validate_public_json(output_root)

        manifest = {
            "schema_version": "1.0",
            "built_at": utc_now(),
            "snapshot_run_id": snapshot_run_id,
            "publication_status": publication.get("status"),
            "agent_state": dashboard.get("agent_analysis", {}).get("state"),
            "agent_analysis_id": dashboard.get("agent_analysis", {}).get("analysis_id"),
            "files": file_inventory(output_root),
        }
        (output_root / "release-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest
    except Exception:
        shutil.rmtree(output_root, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build one validated, self-contained public dashboard release."
    )
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_release(args.source_root, args.output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
