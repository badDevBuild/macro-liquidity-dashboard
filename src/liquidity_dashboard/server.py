from __future__ import annotations

import argparse
import json
import logging
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .model import build_dashboard, build_series


LOGGER = logging.getLogger(__name__)


SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class DashboardHandler(BaseHTTPRequestHandler):
    project_root = Path.cwd()
    web_root = Path.cwd() / "web"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers(self, content_type: str, *, cache_control: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", cache_control)
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._headers("application/json; charset=utf-8", cache_control="no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message, "status": status.value}, status)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path == "/healthz":
            self._json({"status": "ok"})
            return
        if parsed.path == "/api/dashboard":
            try:
                self._json(build_dashboard(self.project_root))
            except (FileNotFoundError, OSError, ValueError) as exc:
                LOGGER.exception("dashboard payload is unavailable: %s", exc)
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "dashboard data unavailable")
            return
        if parsed.path == "/api/status":
            try:
                dashboard = build_dashboard(self.project_root)
                self._json({"snapshot": dashboard["snapshot"], "status": dashboard["status"]})
            except (FileNotFoundError, OSError, ValueError) as exc:
                LOGGER.exception("dashboard status is unavailable: %s", exc)
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "dashboard data unavailable")
            return
        if parsed.path == "/api/series":
            query = parse_qs(parsed.query)
            metric_id = query.get("metric_id", [""])[0]
            range_id = query.get("range", ["3m"])[0]
            requested_release_id = query.get("release_id", [""])[0]
            try:
                payload = build_series(self.project_root, metric_id, range_id)
                if requested_release_id and requested_release_id != payload.get("release_id"):
                    self._error(HTTPStatus.CONFLICT, "dashboard release changed; refresh required")
                    return
                self._json(payload)
            except ValueError as exc:
                LOGGER.info("invalid series request: %s", exc)
                self._error(HTTPStatus.BAD_REQUEST, "invalid metric or range")
            except (FileNotFoundError, OSError) as exc:
                LOGGER.exception("dashboard series is unavailable: %s", exc)
                self._error(HTTPStatus.SERVICE_UNAVAILABLE, "dashboard data unavailable")
            return
        self._serve_static(parsed.path)

    def _serve_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "index.html"
        requested = (self.web_root / relative).resolve()
        web_root = self.web_root.resolve()
        if not requested.is_relative_to(web_root):
            self._error(HTTPStatus.NOT_FOUND, "resource not found")
            return
        if not requested.is_file():
            self._error(HTTPStatus.NOT_FOUND, "resource not found")
            return
        try:
            body = requested.read_bytes()
        except OSError:
            self._error(HTTPStatus.NOT_FOUND, "resource not found")
            return
        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
            "application/javascript",
            "application/manifest+json",
        }:
            content_type += "; charset=utf-8"
        cache_control = (
            "no-cache" if requested.name in {"index.html", "sw.js"} else "public, max-age=3600"
        )
        self.send_response(HTTPStatus.OK)
        self._headers(content_type, cache_control=cache_control)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(
    project_root: Path,
    host: str = "127.0.0.1",
    port: int = 8876,
) -> ThreadingHTTPServer:
    # Keep the configured path itself stable. Production points this at a
    # `current` symlink so a validated release can be switched atomically
    # without leaving data and static files from different releases in view.
    root = project_root.absolute()
    handler = type(
        "ConfiguredDashboardHandler",
        (DashboardHandler,),
        {"project_root": root, "web_root": root / "web"},
    )
    return ThreadingHTTPServer((host, port), handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the macro liquidity dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    server = create_server(args.project_root, args.host, args.port)
    print(f"Macro liquidity dashboard: http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
