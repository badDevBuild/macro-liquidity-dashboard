from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import json
import math
import os
import random
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


UTC = timezone.utc
ELIGIBLE_STATUSES = {"fresh_network", "fresh_cache"}


class ChannelError(RuntimeError):
    pass


class FetchError(ChannelError):
    def __init__(
        self, message: str, *, attempts: int = 0, elapsed_ms: int | None = None
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.elapsed_ms = elapsed_ms


class ParseError(ChannelError):
    pass


@dataclass(frozen=True)
class Observation:
    metric_id: str
    source_id: str
    group: str
    observed_at: str
    value: float
    unit: str


@dataclass
class FetchResponse:
    body: bytes
    status_code: int
    headers: dict[str, str]
    fetched_at: str
    elapsed_ms: int
    attempts: int


@dataclass
class SourceOutcome:
    source_id: str
    metric_id: str
    group: str
    quality_status: str
    observation: Observation | None
    error: str | None
    attempts: int
    elapsed_ms: int | None
    fetched_at: str | None
    raw_sha256: str | None
    source_url: str
    source_name: str
    authority: str
    cadence: str
    age_days: int | None
    available_for_analysis: bool


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def iso_z(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError) as exc:
        raise ParseError(f"invalid observation date: {value!r}") from exc


def parse_number(value: Any) -> float:
    if value is None:
        raise ParseError("numeric value is null")
    text = str(value).strip().replace(",", "")
    if text.lower() in {"", ".", "null", "none", "n/a", "na"}:
        raise ParseError(f"numeric value is missing: {value!r}")
    try:
        number = float(text)
    except ValueError as exc:
        raise ParseError(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(number):
        raise ParseError(f"non-finite numeric value: {value!r}")
    return number


def parse_accounting_number(value: Any) -> float:
    text = " ".join(str(value).replace("\u2212", "-").split())
    negative_parentheses = text.startswith("(") and text.endswith(")")
    if negative_parentheses:
        text = text[1:-1]
    text = text.replace(",", "").replace(" ", "")
    if text.startswith("+"):
        text = text[1:]
    number = parse_number(text)
    return -abs(number) if negative_parentheses else number


def parse_fred_csv(body: bytes, source: dict[str, Any]) -> list[Observation]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError("FRED payload is not UTF-8 CSV") from exc
    series_id = source["series_id"]
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "observation_date" not in reader.fieldnames:
        raise ParseError("FRED CSV is missing observation_date")
    if series_id not in reader.fieldnames:
        raise ParseError(f"FRED CSV is missing series column {series_id}")
    observations: list[Observation] = []
    for row in reader:
        raw_value = row.get(series_id)
        if raw_value in (None, "", "."):
            continue
        observed_at = parse_iso_date(row["observation_date"]).isoformat()
        observations.append(
            Observation(
                metric_id=source["metric_id"],
                source_id=source["id"],
                group=source["group"],
                observed_at=observed_at,
                value=parse_number(raw_value),
                unit=source["unit"],
            )
        )
    if not observations:
        raise ParseError("FRED CSV contained no usable observations")
    return observations


def parse_nyfed_reference_rate(body: bytes, source: dict[str, Any]) -> list[Observation]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError("New York Fed payload is not valid JSON") from exc
    rows = payload.get("refRates")
    if not isinstance(rows, list):
        raise ParseError("New York Fed JSON is missing refRates")
    observations: list[Observation] = []
    for row in rows:
        if row.get("type") != source.get("rate_type"):
            continue
        observations.append(
            Observation(
                metric_id=source["metric_id"],
                source_id=source["id"],
                group=source["group"],
                observed_at=parse_iso_date(row.get("effectiveDate")).isoformat(),
                value=parse_number(row.get("percentRate")),
                unit=source["unit"],
            )
        )
    if not observations:
        raise ParseError("New York Fed JSON contained no matching rates")
    return observations


def parse_treasury_tga(body: bytes, source: dict[str, Any]) -> list[Observation]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError("Treasury payload is not valid JSON") from exc
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ParseError("Treasury JSON is missing data")
    expected_account = source["account_type"]
    observations: list[Observation] = []
    for row in rows:
        if row.get("account_type") != expected_account:
            continue
        # Fiscal Data currently puts the closing TGA value in open_today_bal
        # while close_today_bal is the literal string "null". Prefer the
        # semantically named field if it later becomes populated, otherwise use
        # the documented current payload field and preserve this check in tests.
        candidates = [row.get("close_today_bal"), row.get("open_today_bal")]
        value: float | None = None
        for candidate in candidates:
            try:
                value = parse_number(candidate)
                break
            except ParseError:
                continue
        if value is None:
            raise ParseError("Treasury TGA row has no usable balance field")
        observations.append(
            Observation(
                metric_id=source["metric_id"],
                source_id=source["id"],
                group=source["group"],
                observed_at=parse_iso_date(row.get("record_date")).isoformat(),
                value=value,
                unit=source["unit"],
            )
        )
    if not observations:
        raise ParseError("Treasury JSON contained no matching TGA rows")
    return observations


class _H41TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.page_text: list[str] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self.page_text.append(cleaned)
        if self._cell is not None:
            self._cell.append(data)


def parse_h41_html(body: bytes, source: dict[str, Any]) -> list[Observation]:
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ParseError("H.4.1 payload is not UTF-8 HTML") from exc
    parser = _H41TableParser()
    parser.feed(text)
    flattened = " ".join(parser.page_text)
    import re

    date_match = re.search(
        r"Wednesday\s+([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})", flattened
    )
    if not date_match:
        raise ParseError("H.4.1 HTML is missing the Wednesday observation date")
    try:
        observed_at = datetime.strptime(date_match.group(1), "%b %d, %Y").date().isoformat()
    except ValueError as exc:
        raise ParseError("H.4.1 HTML contains an invalid Wednesday date") from exc

    expected_label = " ".join(source["row_label"].split())
    matches = [
        row for row in parser.rows if row and " ".join(row[0].split()) == expected_label
    ]
    occurrence = int(source.get("row_occurrence", 0))
    if occurrence >= len(matches):
        raise ParseError(f"H.4.1 HTML row not found: {expected_label!r}")
    numeric_values: list[float] = []
    for cell in matches[occurrence][1:]:
        try:
            numeric_values.append(parse_accounting_number(cell))
        except ParseError:
            continue
    numeric_index = int(source["numeric_index"])
    if numeric_index >= len(numeric_values):
        raise ParseError(
            f"H.4.1 row {expected_label!r} has only {len(numeric_values)} numeric cells"
        )
    return [
        Observation(
            metric_id=source["metric_id"],
            source_id=source["id"],
            group=source["group"],
            observed_at=observed_at,
            value=numeric_values[numeric_index],
            unit=source["unit"],
        )
    ]


PARSERS: dict[str, Callable[[bytes, dict[str, Any]], list[Observation]]] = {
    "fred_csv": parse_fred_csv,
    "nyfed_reference_rate": parse_nyfed_reference_rate,
    "treasury_tga": parse_treasury_tga,
    "h41_html": parse_h41_html,
}


def validate_observations(
    observations: Iterable[Observation], source: dict[str, Any], as_of_date: date
) -> list[Observation]:
    valid_range = source.get("valid_range")
    future_policy = source.get("future_observation_policy", "reject")
    future_max_days = int(source.get("future_observation_max_days", 0))
    deduplicated: dict[str, Observation] = {}
    for observation in observations:
        observed_date = parse_iso_date(observation.observed_at)
        if observed_date > as_of_date:
            future_days = (observed_date - as_of_date).days
            if (
                future_policy == "ignore_after_as_of"
                and future_days <= future_max_days
            ):
                continue
            raise ParseError(
                f"future-dated observation {observation.observed_at} for {source['id']}"
            )
        if valid_range:
            low, high = valid_range
            if not low <= observation.value <= high:
                raise ParseError(
                    f"value {observation.value} outside [{low}, {high}] for {source['id']}"
                )
        previous = deduplicated.get(observation.observed_at)
        if previous and previous.value != observation.value:
            raise ParseError(
                f"conflicting duplicate date {observation.observed_at} for {source['id']}"
            )
        deduplicated[observation.observed_at] = observation
    if not deduplicated:
        raise ParseError(f"no valid observations for {source['id']}")
    return sorted(deduplicated.values(), key=lambda item: item.observed_at)


def source_as_of_date(source: dict[str, Any], now: datetime) -> date:
    """Return the source-local calendar date used for temporal validation."""
    timezone_name = str(source.get("as_of_timezone", "UTC"))
    try:
        source_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ParseError(
            f"unknown as_of_timezone {timezone_name!r} for {source['id']}"
        ) from exc
    aware_now = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
    return aware_now.astimezone(source_timezone).date()


class HttpFetcher:
    def __init__(self, request_policy: dict[str, Any], direct: bool = False):
        self.timeout = float(request_policy.get("timeout_seconds", 25))
        self.max_attempts = int(request_policy.get("max_attempts", 3))
        self.base_backoff = float(request_policy.get("base_backoff_seconds", 1.0))
        self.user_agent = str(
            request_policy.get("urllib_user_agent", "macro-liquidity-dashboard/0.1")
        )
        handlers: list[Any] = []
        if direct:
            handlers.append(urllib.request.ProxyHandler({}))
        self.opener = urllib.request.build_opener(*handlers)

    def fetch(self, url: str) -> FetchResponse:
        last_error: Exception | None = None
        started = time.monotonic()
        attempts_done = 0
        for attempt in range(1, self.max_attempts + 1):
            attempts_done = attempt
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json,text/csv,text/plain;q=0.9,*/*;q=0.5",
                    "Accept-Encoding": "identity",
                },
            )
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    body = response.read()
                    status_code = int(response.status)
                    if status_code != 200:
                        raise FetchError(f"unexpected HTTP status {status_code}")
                    if not body:
                        raise FetchError("empty response body")
                    return FetchResponse(
                        body=body,
                        status_code=status_code,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        fetched_at=iso_z(utc_now()),
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        attempts=attempt,
                    )
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in {408, 425, 429, 500, 502, 503, 504}:
                    break
            except (urllib.error.URLError, TimeoutError, OSError, FetchError) as exc:
                last_error = exc
            if attempt < self.max_attempts:
                delay = self.base_backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                time.sleep(delay)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        raise FetchError(
            f"fetch failed after {attempts_done} attempts and {elapsed_ms} ms: {last_error}",
            attempts=attempts_done,
            elapsed_ms=elapsed_ms,
        )


class CurlFetcher:
    """Bounded HTTP transport using the system curl binary.

    curl gives us separate connection and whole-request deadlines. That matters
    in production because urllib's timeout may not bound every response-read
    phase consistently across Python and TLS implementations.
    """

    def __init__(self, request_policy: dict[str, Any], direct: bool = False):
        self.connect_timeout = float(request_policy.get("connect_timeout_seconds", 6))
        self.timeout = float(request_policy.get("timeout_seconds", 20))
        self.max_attempts = int(request_policy.get("max_attempts", 2))
        self.base_backoff = float(request_policy.get("base_backoff_seconds", 1.0))
        self.user_agent = request_policy.get("curl_user_agent")
        self.direct = direct
        self._response_cache: dict[str, FetchResponse] = {}

    @staticmethod
    def _parse_headers(raw_headers: bytes) -> dict[str, str]:
        text = raw_headers.decode("iso-8859-1", errors="replace")
        blocks = [block for block in text.replace("\r\n", "\n").split("\n\n") if block.strip()]
        headers: dict[str, str] = {}
        for block in blocks:
            lines = block.splitlines()
            if not lines or not lines[0].startswith("HTTP/"):
                continue
            candidate: dict[str, str] = {}
            for line in lines[1:]:
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                candidate[key.strip().lower()] = value.strip()
            headers = candidate
        return headers

    def fetch(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> FetchResponse:
        extra_headers = headers or {}
        for name, value in extra_headers.items():
            if not name or any(character in name for character in "\r\n:"):
                raise FetchError("invalid request header name")
            if any(character in str(value) for character in "\r\n"):
                raise FetchError("invalid request header value")
        cache_key = json.dumps(
            [url, sorted(extra_headers)], ensure_ascii=True, separators=(",", ":")
        )
        if cache_key in self._response_cache:
            return self._response_cache[cache_key]
        started = time.monotonic()
        last_error: Exception | None = None
        attempts_done = 0
        for attempt in range(1, self.max_attempts + 1):
            attempts_done = attempt
            with tempfile.TemporaryDirectory(prefix="liquidity-fetch-") as temporary:
                body_path = Path(temporary) / "body"
                headers_path = Path(temporary) / "headers"
                command = [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--location",
                    "--http1.1",
                    "--connect-timeout",
                    str(self.connect_timeout),
                    "--max-time",
                    str(self.timeout),
                    "--header",
                    "Accept: application/json,text/csv,text/plain;q=0.9,*/*;q=0.5",
                    "--header",
                    "Accept-Encoding: identity",
                    "--dump-header",
                    str(headers_path),
                    "--output",
                    str(body_path),
                    "--write-out",
                    "%{http_code}",
                ]
                if extra_headers:
                    # Keep credentials out of the process command line. curl can
                    # read one header per line from a file inside its private
                    # temporary directory; that directory is removed after the
                    # bounded request completes.
                    header_path = Path(temporary) / "extra-headers"
                    header_path.write_text(
                        "".join(
                            f"{name}: {value}\n"
                            for name, value in extra_headers.items()
                        ),
                        encoding="utf-8",
                    )
                    header_path.chmod(0o600)
                    command.extend(["--header", f"@{header_path}"])
                if self.user_agent:
                    command.extend(["--user-agent", str(self.user_agent)])
                if self.direct:
                    command.extend(["--noproxy", "*"])
                command.append(url)
                try:
                    result = subprocess.run(
                        command,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=self.timeout + 5,
                    )
                    status_text = result.stdout.strip()
                    status_code = int(status_text[-3:]) if len(status_text) >= 3 else 0
                    if result.returncode != 0:
                        stderr = result.stderr.strip() or f"curl exit {result.returncode}"
                        raise FetchError(f"{stderr}; HTTP {status_code}")
                    if status_code != 200:
                        raise FetchError(f"unexpected HTTP status {status_code}")
                    body = body_path.read_bytes() if body_path.exists() else b""
                    if not body:
                        raise FetchError("empty response body")
                    raw_headers = headers_path.read_bytes() if headers_path.exists() else b""
                    response = FetchResponse(
                        body=body,
                        status_code=status_code,
                        headers=self._parse_headers(raw_headers),
                        fetched_at=iso_z(utc_now()),
                        elapsed_ms=int((time.monotonic() - started) * 1000),
                        attempts=attempt,
                    )
                    self._response_cache[cache_key] = response
                    return response
                except (
                    FileNotFoundError,
                    OSError,
                    ValueError,
                    subprocess.TimeoutExpired,
                    FetchError,
                ) as exc:
                    last_error = exc
            if attempt < self.max_attempts:
                delay = self.base_backoff * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                time.sleep(delay)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        raise FetchError(
            f"curl fetch failed after {attempts_done} attempts and {elapsed_ms} ms: {last_error}",
            attempts=attempts_done,
            elapsed_ms=elapsed_ms,
        )


class ChannelStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.raw_dir = data_dir / "raw"
        self.runs_dir = data_dir / "runs"
        self.snapshots_dir = data_dir / "snapshots"
        self.status_dir = data_dir / "status"
        for directory in (
            self.raw_dir,
            self.runs_dir,
            self.snapshots_dir,
            self.status_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        self._lock_handle = (data_dir / "channel.lock").open("a+b")
        try:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._lock_handle.close()
            raise ChannelError("another data-channel run already holds channel.lock") from exc
        try:
            self.db = sqlite3.connect(data_dir / "channel.sqlite3")
        except BaseException:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            self._lock_handle.close()
            raise
        self.db.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.db.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS observations (
                metric_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL,
                group_name TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                raw_sha256 TEXT NOT NULL,
                revision_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (metric_id, source_id, observed_at)
            );
            CREATE TABLE IF NOT EXISTS observation_revisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                metric_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                old_value REAL NOT NULL,
                new_value REAL NOT NULL,
                detected_at TEXT NOT NULL,
                raw_sha256 TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS source_runs (
                run_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                metric_id TEXT NOT NULL,
                quality_status TEXT NOT NULL,
                observed_at TEXT,
                fetched_at TEXT,
                error TEXT,
                attempts INTEGER NOT NULL,
                elapsed_ms INTEGER,
                raw_sha256 TEXT,
                PRIMARY KEY (run_id, source_id)
            );
            CREATE TABLE IF NOT EXISTS channel_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                error TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_observations_latest
                ON observations (metric_id, source_id, observed_at DESC);
            CREATE INDEX IF NOT EXISTS idx_channel_runs_started
                ON channel_runs (started_at DESC);
            """
        )
        self.db.commit()

    def close(self) -> None:
        try:
            self.db.close()
        finally:
            fcntl.flock(self._lock_handle.fileno(), fcntl.LOCK_UN)
            self._lock_handle.close()

    def start_run(self, run_id: str, started_at: str) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT INTO channel_runs (run_id, started_at, status)
                VALUES (?, ?, 'running')
                """,
                (run_id, started_at),
            )

    def finish_run(
        self, run_id: str, status: str, completed_at: str, error: str | None = None
    ) -> None:
        with self.db:
            self.db.execute(
                """
                UPDATE channel_runs
                SET completed_at = ?, status = ?, error = ?
                WHERE run_id = ?
                """,
                (completed_at, status, error, run_id),
            )

    def save_raw(
        self, source: dict[str, Any], run_id: str, response: FetchResponse
    ) -> tuple[str, str]:
        digest = sha256_bytes(response.body)
        content_type = response.headers.get("content-type", "")
        extension = ".json" if "json" in content_type or response.body.lstrip().startswith(b"{") else ".csv"
        directory = self.raw_dir / source["id"]
        directory.mkdir(parents=True, exist_ok=True)
        raw_path = directory / f"{run_id}-{digest[:12]}{extension}"
        atomic_write_bytes(raw_path, response.body)
        metadata = {
            "source_id": source["id"],
            "url": source["url"],
            "fetched_at": response.fetched_at,
            "http_status": response.status_code,
            "attempts": response.attempts,
            "elapsed_ms": response.elapsed_ms,
            "content_type": content_type,
            "etag": response.headers.get("etag"),
            "last_modified": response.headers.get("last-modified"),
            "sha256": digest,
            "byte_count": len(response.body),
        }
        atomic_write_json(raw_path.with_suffix(raw_path.suffix + ".meta.json"), metadata)
        return digest, str(raw_path)

    def upsert_observations(
        self,
        observations: Iterable[Observation],
        run_id: str,
        seen_at: str,
        raw_sha256: str,
    ) -> int:
        revisions = 0
        with self.db:
            for observation in observations:
                existing = self.db.execute(
                    """
                    SELECT value FROM observations
                    WHERE metric_id = ? AND source_id = ? AND observed_at = ?
                    """,
                    (observation.metric_id, observation.source_id, observation.observed_at),
                ).fetchone()
                if existing is None:
                    self.db.execute(
                        """
                        INSERT INTO observations (
                            metric_id, source_id, observed_at, value, unit, group_name,
                            first_seen_at, last_seen_at, raw_sha256, revision_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                        (
                            observation.metric_id,
                            observation.source_id,
                            observation.observed_at,
                            observation.value,
                            observation.unit,
                            observation.group,
                            seen_at,
                            seen_at,
                            raw_sha256,
                        ),
                    )
                elif float(existing["value"]) != observation.value:
                    revisions += 1
                    self.db.execute(
                        """
                        INSERT INTO observation_revisions (
                            run_id, metric_id, source_id, observed_at, old_value,
                            new_value, detected_at, raw_sha256
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            observation.metric_id,
                            observation.source_id,
                            observation.observed_at,
                            float(existing["value"]),
                            observation.value,
                            seen_at,
                            raw_sha256,
                        ),
                    )
                    self.db.execute(
                        """
                        UPDATE observations
                        SET value = ?, unit = ?, group_name = ?, last_seen_at = ?,
                            raw_sha256 = ?, revision_count = revision_count + 1
                        WHERE metric_id = ? AND source_id = ? AND observed_at = ?
                        """,
                        (
                            observation.value,
                            observation.unit,
                            observation.group,
                            seen_at,
                            raw_sha256,
                            observation.metric_id,
                            observation.source_id,
                            observation.observed_at,
                        ),
                    )
                else:
                    self.db.execute(
                        """
                        UPDATE observations
                        SET last_seen_at = ?, raw_sha256 = ?
                        WHERE metric_id = ? AND source_id = ? AND observed_at = ?
                        """,
                        (
                            seen_at,
                            raw_sha256,
                            observation.metric_id,
                            observation.source_id,
                            observation.observed_at,
                        ),
                    )
        return revisions

    def latest_cached(self, source: dict[str, Any]) -> Observation | None:
        row = self.db.execute(
            """
            SELECT metric_id, source_id, group_name, observed_at, value, unit
            FROM observations
            WHERE metric_id = ? AND source_id = ?
            ORDER BY observed_at DESC
            LIMIT 1
            """,
            (source["metric_id"], source["id"]),
        ).fetchone()
        if row is None:
            return None
        return Observation(
            metric_id=row["metric_id"],
            source_id=row["source_id"],
            group=row["group_name"],
            observed_at=row["observed_at"],
            value=float(row["value"]),
            unit=row["unit"],
        )

    def record_outcome(self, run_id: str, outcome: SourceOutcome) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO source_runs (
                    run_id, source_id, metric_id, quality_status, observed_at,
                    fetched_at, error, attempts, elapsed_ms, raw_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    outcome.source_id,
                    outcome.metric_id,
                    outcome.quality_status,
                    outcome.observation.observed_at if outcome.observation else None,
                    outcome.fetched_at,
                    outcome.error,
                    outcome.attempts,
                    outcome.elapsed_ms,
                    outcome.raw_sha256,
                ),
            )


def observation_age(observation: Observation, today: date) -> int:
    return (today - parse_iso_date(observation.observed_at)).days


def source_outcome_from_cache(
    source: dict[str, Any],
    cached: Observation | None,
    error: str,
    today: date,
    *,
    attempts: int = 0,
    elapsed_ms: int | None = None,
    fetched_at: str | None = None,
    raw_sha256: str | None = None,
) -> SourceOutcome:
    if cached is None:
        status = "unavailable"
        age_days = None
        available = False
    else:
        age_days = observation_age(cached, today)
        if age_days <= int(source["freshness_max_days"]):
            status = "fresh_cache"
            available = True
        elif age_days <= int(source["fallback_max_days"]):
            status = "stale_fallback"
            available = False
        else:
            status = "unavailable"
            available = False
            cached = None
    return SourceOutcome(
        source_id=source["id"],
        metric_id=source["metric_id"],
        group=source["group"],
        quality_status=status,
        observation=cached,
        error=error,
        attempts=attempts,
        elapsed_ms=elapsed_ms,
        fetched_at=fetched_at,
        raw_sha256=raw_sha256,
        source_url=source["url"],
        source_name=source["name"],
        authority=source["authority"],
        cadence=source["cadence"],
        age_days=age_days,
        available_for_analysis=available,
    )


def collect_source(
    source: dict[str, Any],
    fetcher: Any,
    store: ChannelStore,
    run_id: str,
    now: datetime,
) -> tuple[SourceOutcome, int]:
    today = source_as_of_date(source, now)
    response: FetchResponse | None = None
    raw_sha256: str | None = None
    try:
        response = fetcher.fetch(source["url"])
        raw_sha256, _ = store.save_raw(source, run_id, response)
        parser_name = source["parser"]
        parser = PARSERS.get(parser_name)
        if parser is None:
            raise ParseError(f"unknown parser {parser_name!r}")
        observations = validate_observations(parser(response.body, source), source, today)
        latest = observations[-1]
        age_days = observation_age(latest, today)
        if age_days > int(source["fallback_max_days"]):
            raise ParseError(
                f"latest observation is {age_days} days old, beyond fallback limit"
            )
        revisions = store.upsert_observations(
            observations, run_id, response.fetched_at, raw_sha256
        )
        if age_days <= int(source["freshness_max_days"]):
            status = "fresh_network"
            available = True
            error = None
        else:
            status = "stale_source"
            available = False
            error = (
                f"latest observation is {age_days} days old; "
                f"freshness limit is {source['freshness_max_days']}"
            )
        outcome = SourceOutcome(
            source_id=source["id"],
            metric_id=source["metric_id"],
            group=source["group"],
            quality_status=status,
            observation=latest,
            error=error,
            attempts=response.attempts,
            elapsed_ms=response.elapsed_ms,
            fetched_at=response.fetched_at,
            raw_sha256=raw_sha256,
            source_url=source["url"],
            source_name=source["name"],
            authority=source["authority"],
            cadence=source["cadence"],
            age_days=age_days,
            available_for_analysis=available,
        )
        return outcome, revisions
    except (FetchError, ParseError, KeyError, TypeError, ValueError) as exc:
        cached = store.latest_cached(source)
        attempts = response.attempts if response else int(getattr(exc, "attempts", 0))
        elapsed_ms = (
            response.elapsed_ms
            if response
            else getattr(exc, "elapsed_ms", None)
        )
        return (
            source_outcome_from_cache(
                source,
                cached,
                str(exc),
                today,
                attempts=attempts,
                elapsed_ms=elapsed_ms,
                fetched_at=response.fetched_at if response else None,
                raw_sha256=raw_sha256,
            ),
            0,
        )


def resolve_metric_outcomes(
    outcomes: list[SourceOutcome],
    sources: list[dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[list[SourceOutcome], list[dict[str, Any]]]:
    priority_by_source = {
        source["id"]: int(source.get("priority", 100)) for source in sources
    }
    ordered_metrics = list(dict.fromkeys(source["metric_id"] for source in sources))
    status_rank = {
        "fresh_network": 0,
        "fresh_cache": 1,
        "stale_source": 2,
        "stale_fallback": 3,
        "unavailable": 4,
    }

    def candidate_key(outcome: SourceOutcome) -> tuple[int, int, int]:
        age = outcome.age_days if outcome.age_days is not None else 999999
        return (
            age,
            status_rank.get(outcome.quality_status, 99),
            priority_by_source.get(outcome.source_id, 100),
        )

    resolved: list[SourceOutcome] = []
    reconciliation_issues: list[dict[str, Any]] = []
    tolerances = policy.get("reconciliation_tolerances", {})
    for metric_id in ordered_metrics:
        candidates = [item for item in outcomes if item.metric_id == metric_id]
        if not candidates:
            continue
        selected = min(candidates, key=candidate_key)
        eligible = [item for item in candidates if item.quality_status in ELIGIBLE_STATUSES]
        tolerance = tolerances.get(metric_id)
        if tolerance is not None and len(eligible) > 1:
            by_date_and_unit: dict[tuple[str, str], list[SourceOutcome]] = {}
            for item in eligible:
                if item.observation is None:
                    continue
                key = (item.observation.observed_at, item.observation.unit)
                by_date_and_unit.setdefault(key, []).append(item)
            conflicts: list[dict[str, Any]] = []
            for (observed_at, unit), comparable in by_date_and_unit.items():
                if len(comparable) < 2:
                    continue
                values = [item.observation.value for item in comparable if item.observation]
                if max(values) - min(values) > float(tolerance):
                    conflicts.append(
                        {
                            "observed_at": observed_at,
                            "unit": unit,
                            "tolerance": float(tolerance),
                            "candidates": [
                                {
                                    "source_id": item.source_id,
                                    "value": item.observation.value if item.observation else None,
                                }
                                for item in comparable
                            ],
                        }
                    )
            if conflicts:
                message = f"cross-source disagreement for {metric_id}"
                selected = replace(
                    selected,
                    quality_status="data_conflict",
                    available_for_analysis=False,
                    error=message,
                )
                reconciliation_issues.append(
                    {
                        "metric_id": metric_id,
                        "severity": "high",
                        "message": message,
                        "conflicts": conflicts,
                    }
                )
        resolved.append(selected)
    return resolved, reconciliation_issues


def evaluate_publication(
    outcomes: list[SourceOutcome], policy: dict[str, Any]
) -> dict[str, Any]:
    eligible_statuses = set(policy.get("eligible_quality_statuses", ELIGIBLE_STATUSES))
    eligible = [item for item in outcomes if item.quality_status in eligible_statuses]
    unavailable = [item for item in outcomes if item.quality_status not in eligible_statuses]
    total = len(outcomes)
    group_counts: dict[str, dict[str, int | bool]] = {}
    for group, minimum in policy["group_minimums"].items():
        group_total = sum(item.group == group for item in outcomes)
        group_eligible = sum(
            item.group == group and item.quality_status in eligible_statuses
            for item in outcomes
        )
        group_counts[group] = {
            "eligible": group_eligible,
            "total": group_total,
            "minimum": int(minimum),
            "passed": group_eligible >= int(minimum),
        }
    minimum_count = int(policy["minimum_fresh_metrics"])
    maximum_missing = int(policy["maximum_unavailable_metrics"])
    groups_passed = all(bool(item["passed"]) for item in group_counts.values())
    allowed = (
        len(eligible) >= minimum_count
        and len(unavailable) <= maximum_missing
        and groups_passed
    )
    if not allowed:
        status = "block_analysis"
    elif unavailable:
        status = "publish_degraded"
    else:
        status = "publish"
    warnings = [
        {
            "metric_id": item.metric_id,
            "source_id": item.source_id,
            "quality_status": item.quality_status,
            "error": item.error,
            "observed_at": item.observation.observed_at if item.observation else None,
        }
        for item in unavailable
    ]
    return {
        "status": status,
        "analysis_allowed": allowed,
        "eligible_metric_count": len(eligible),
        "unavailable_metric_count": len(unavailable),
        "total_metric_count": total,
        "coverage_ratio": round(len(eligible) / total, 4) if total else 0.0,
        "group_checks": group_counts,
        "warnings": warnings,
    }


def outcome_to_metric(outcome: SourceOutcome) -> dict[str, Any]:
    observation = outcome.observation
    return {
        "metric_id": outcome.metric_id,
        "source_id": outcome.source_id,
        "source_name": outcome.source_name,
        "source_url": outcome.source_url,
        "authority": outcome.authority,
        "group": outcome.group,
        "cadence": outcome.cadence,
        "quality_status": outcome.quality_status,
        "available_for_analysis": outcome.available_for_analysis,
        "value": observation.value if observation else None,
        "unit": observation.unit if observation else None,
        "observed_at": observation.observed_at if observation else None,
        "age_days": outcome.age_days,
        "fetched_at": outcome.fetched_at,
        "fetch_attempts": outcome.attempts,
        "fetch_elapsed_ms": outcome.elapsed_ms,
        "raw_sha256": outcome.raw_sha256,
        "error": outcome.error,
    }


def run_channel(
    sources_path: Path,
    policy_path: Path,
    data_dir: Path,
    *,
    direct: bool = False,
    transport: str = "curl",
    fetcher: Any | None = None,
    now: datetime | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    now = now or utc_now()
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    run_id = now.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    started_at = iso_z(now)
    source_config = load_json(sources_path)
    policy = load_json(policy_path)
    sources = source_config.get("sources", [])
    if not sources:
        raise ChannelError("source registry is empty")
    source_ids = [source["id"] for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ChannelError("source registry contains duplicate source id values")
    request_policy = source_config.get("request_policy", {})
    if fetcher is None:
        if transport == "curl":
            fetcher = CurlFetcher(request_policy, direct=direct)
        elif transport == "urllib":
            fetcher = HttpFetcher(request_policy, direct=direct)
        else:
            raise ChannelError(f"unsupported transport {transport!r}")
    request_delay = float(request_policy.get("between_requests_seconds", 0.0))
    run_deadline = float(request_policy.get("run_deadline_seconds", 300))
    run_started_monotonic = time.monotonic()
    store = ChannelStore(data_dir)
    outcomes: list[SourceOutcome] = []
    revision_count = 0
    store.start_run(run_id, started_at)
    try:
        for index, source in enumerate(sources):
            if progress:
                progress(
                    {
                        "event": "source_start",
                        "index": index + 1,
                        "total": len(sources),
                        "source_id": source["id"],
                    }
                )
            if time.monotonic() - run_started_monotonic > run_deadline:
                outcome = source_outcome_from_cache(
                    source,
                    store.latest_cached(source),
                    f"run deadline of {run_deadline:g} seconds exceeded",
                    now.date(),
                )
                revisions = 0
            else:
                outcome, revisions = collect_source(source, fetcher, store, run_id, now)
            outcomes.append(outcome)
            revision_count += revisions
            store.record_outcome(run_id, outcome)
            if progress:
                progress(
                    {
                        "event": "source_complete",
                        "index": index + 1,
                        "total": len(sources),
                        "source_id": source["id"],
                        "metric_id": source["metric_id"],
                        "quality_status": outcome.quality_status,
                        "observed_at": outcome.observation.observed_at
                        if outcome.observation
                        else None,
                        "error": outcome.error,
                    }
                )
            if request_delay and index < len(sources) - 1:
                time.sleep(request_delay)
        resolved_outcomes, reconciliation_issues = resolve_metric_outcomes(
            outcomes, sources, policy
        )
        publication = evaluate_publication(resolved_outcomes, policy)
        completed_at = iso_z(utc_now())
        snapshot = {
            "schema_version": "1.0",
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "publication": publication,
            "revision_count_detected": revision_count,
            "reconciliation_issues": reconciliation_issues,
            "metrics": {
                outcome.metric_id: outcome_to_metric(outcome)
                for outcome in resolved_outcomes
            },
            "source_health": {
                outcome.source_id: outcome_to_metric(outcome) for outcome in outcomes
            },
            "missing_value_semantics": "null means unavailable; it never means zero",
        }
        run_path = store.runs_dir / f"{run_id}.json"
        atomic_write_json(run_path, snapshot)
        atomic_write_json(store.status_dir / "latest-run.json", snapshot)
        if publication["analysis_allowed"]:
            snapshot_path = store.snapshots_dir / f"{run_id}.json"
            atomic_write_json(snapshot_path, snapshot)
            atomic_write_json(store.snapshots_dir / "latest.json", snapshot)
        store.finish_run(run_id, publication["status"], completed_at)
        return snapshot
    except BaseException as exc:
        try:
            store.finish_run(
                run_id,
                "failed",
                iso_z(utc_now()),
                f"{type(exc).__name__}: {str(exc)[:1000]}",
            )
        except Exception:
            pass
        raise
    finally:
        store.close()
