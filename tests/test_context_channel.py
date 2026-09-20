from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from liquidity_dashboard.context_channel import collect_context, _future_eia_wpsr  # noqa: E402
from liquidity_dashboard.bls_schedule import promote_bls_candidate  # noqa: E402


def _bls_candidate(now: datetime) -> dict:
    definitions = [
        ("employment_situation", "Employment Situation for August 2026", "2026-09-04T12:30:00Z", "empsit"),
        ("ppi", "Producer Price Index for August 2026", "2026-09-10T12:30:00Z", "ppi"),
        ("cpi", "Consumer Price Index for August 2026", "2026-09-11T12:30:00Z", "cpi"),
    ]
    events = []
    for release_type, title, starts_at, slug in definitions:
        local_day = {"empsit": "Sep. 04", "ppi": "Sep. 10", "cpi": "Sep. 11"}[slug]
        events.append(
            {
                "release_type": release_type,
                "title": title,
                "reference_period": "August 2026",
                "starts_at": starts_at,
                "timezone": "America/New_York",
                "source_url": f"https://www.bls.gov/schedule/news_release/{slug}.htm",
                "source_name": "U.S. Bureau of Labor Statistics",
                "evidence_text": f"BLS schedule lists {local_day}, 2026 at 08:30 AM for {title}.",
            }
        )
    return {
        "schema_version": "1.0",
        "candidate_id": "context-test",
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "producer": {"type": "test"},
        "events": events,
    }


class ContextChannelTests(unittest.TestCase):
    def test_eia_schedule_honors_holiday_exception_and_caps_events(self) -> None:
        body = b"""
        <p>after 10:30 a.m. eastern time on Wednesday</p>
        <table><tr><th>October 9, 2026</th><td>October 15, 2026</td><td>Thursday</td><td>12:00 p.m.</td><td>Holiday</td></tr></table>
        """
        source = {
            "id": "eia_wpsr_schedule",
            "source_name": "U.S. Energy Information Administration",
            "source_tier": "official_primary",
            "url": "https://www.eia.gov/petroleum/supply/weekly/schedule.php",
            "max_events": 4,
        }
        events = _future_eia_wpsr(
            body,
            source,
            "sha",
            "raw",
            now=datetime(2026, 9, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(len(events), 4)
        self.assertNotIn("2026-10-14", [item["starts_at"][:10] for item in events])
        self.assertIn("2026-10-15", [item["starts_at"][:10] for item in events])
        holiday = next(item for item in events if item["starts_at"].startswith("2026-10-15"))
        self.assertIn("假日顺延", holiday["title"])

    def test_bls_403_uses_fresh_verified_cache_without_degrading_bundle(self) -> None:
        now = datetime(2026, 8, 30, 0, tzinfo=timezone.utc)
        config = {
            "past_hours": 24,
            "future_days": 90,
            "sources": [
                {
                    "id": "bls_release_calendar",
                    "label": "BLS 数据日程",
                    "handler": "future_bls_ics",
                    "source_name": "U.S. Bureau of Labor Statistics",
                    "source_tier": "official_primary",
                    "url": "https://www.bls.gov/schedule/news_release/bls.ics",
                    "required": False,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config" / "context-sources.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            candidate_path = root / "candidate.json"
            candidate_path.write_text(json.dumps(_bls_candidate(now)), encoding="utf-8")
            self.assertTrue(
                promote_bls_candidate(root, candidate_path, now=now)["promoted"]
            )
            bundle = collect_context(
                root,
                now=now,
                fetcher=lambda _url: (_ for _ in ()).throw(RuntimeError("HTTP 403")),
            )
        self.assertEqual(bundle["status"], "ready")
        self.assertEqual(len(bundle["future_90d"]), 3)
        self.assertTrue(
            all(
                item["content_status"] == "official_schedule"
                for item in bundle["future_90d"]
            )
        )
        source = bundle["source_health"][0]
        self.assertEqual(source["delivery_status"], "verified_cache")
        self.assertEqual(source["status"], "ok")
        self.assertIn("403", source["upstream_error"])
        self.assertEqual(bundle["calendar_health"]["status"], "ready")

    def test_bls_ics_uses_new_york_dst_for_november_release(self) -> None:
        config = {
            "past_hours": 24,
            "future_days": 90,
            "sources": [
                {
                    "id": "bls_release_calendar",
                    "label": "BLS 数据日程",
                    "handler": "future_bls_ics",
                    "source_name": "U.S. Bureau of Labor Statistics",
                    "source_tier": "official_primary",
                    "url": "https://www.bls.gov/schedule/news_release/bls.ics",
                    "required": False,
                }
            ],
        }
        body = b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nDTSTART:20261110T083000\nSUMMARY:Consumer Price Index\nEND:VEVENT\nEND:VCALENDAR\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config" / "context-sources.json").write_text(
                json.dumps(config), encoding="utf-8"
            )
            bundle = collect_context(
                root,
                now=datetime(2026, 10, 1, tzinfo=timezone.utc),
                fetcher=lambda _url: body,
            )
        self.assertEqual(bundle["future_90d"][0]["starts_at"], "2026-11-10T13:30:00Z")
        self.assertEqual(
            bundle["future_90d"][0]["content_status"], "official_schedule"
        )

    def test_direct_rss_article_is_enriched_and_archived(self) -> None:
        config = {
            "past_hours": 24,
            "future_days": 90,
            "article_max_chars": 2000,
            "sources": [{
                "id": "publisher",
                "label": "publisher",
                "handler": "past_rss",
                "source_name": "Trusted Publisher",
                "source_tier": "trusted_publisher",
                "url": "https://example.com/feed",
                "fetch_article_content": True,
                "required": False,
            }],
        }
        rss = b"""<rss><channel><item><title>Fed policy changed</title>
          <link>https://example.com/article</link><description>Short publisher summary.</description>
          <pubDate>Fri, 28 Aug 2026 05:00:00 GMT</pubDate></item></channel></rss>"""
        article = b"""<html><head><meta name="description" content="Fallback description for this article."></head>
          <body><p>This is a sufficiently long first paragraph about Federal Reserve policy and market liquidity conditions for extraction.</p>
          <p>This is a second sufficiently long paragraph explaining how the policy change may affect short term funding rates and risk assets.</p>
          <p>This final paragraph adds enough verified article text to cross the full text extraction threshold while remaining deterministic for the test.</p>
          <p>This additional paragraph discusses Treasury yields, dollar funding, and the conditions that would confirm or reject the initial interpretation.</p></body></html>"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config" / "context-sources.json").write_text(json.dumps(config), encoding="utf-8")
            payloads = {"https://example.com/feed": rss, "https://example.com/article": article}
            bundle = collect_context(
                root,
                now=datetime(2026, 8, 28, 8, tzinfo=timezone.utc),
                fetcher=lambda url: payloads[url],
            )
            item = bundle["past_24h"][0]
            self.assertEqual(item["content_status"], "full_text")
            self.assertIn("Federal Reserve policy", item["content"])
            self.assertTrue((root / item["content_raw_ref"]).exists())
            self.assertEqual(bundle["source_health"][0]["article_full_text_count"], 1)

    def test_filters_old_news_and_far_future_events(self) -> None:
        config = {
            "past_hours": 24,
            "future_days": 90,
            "max_past_items": 24,
            "max_future_items": 24,
            "trusted_publishers": ["Reuters"],
            "sources": [
                {
                    "id": "news",
                    "label": "news",
                    "handler": "past_google_news_rss",
                    "source_name": "Google News RSS",
                    "source_tier": "trusted_republisher",
                    "url": "https://example.com/news",
                },
                {
                    "id": "fomc",
                    "label": "fomc",
                    "handler": "future_fomc_html",
                    "source_name": "Federal Reserve Board",
                    "source_tier": "official_primary",
                    "url": "https://example.com/fomc",
                },
            ],
        }
        rss = b"""<rss><channel>
          <item><title>Fresh macro news</title><link>https://example.com/fresh</link><pubDate>Fri, 28 Aug 2026 05:00:00 GMT</pubDate><source url=\"https://reuters.com\">Reuters</source></item>
          <item><title>Old macro news</title><link>https://example.com/old</link><pubDate>Wed, 26 Aug 2026 05:00:00 GMT</pubDate><source url=\"https://reuters.com\">Reuters</source></item>
          <item><title>Untrusted macro news</title><link>https://example.com/no</link><pubDate>Fri, 28 Aug 2026 05:00:00 GMT</pubDate><source url=\"https://unknown.test\">Unknown</source></item>
        </channel></rss>"""
        fomc = b"""<h4>2026 FOMC Meetings</h4>
          <div class=\"fomc-meeting__month\"><strong>September</strong></div><div class=\"fomc-meeting__date\">15-16*</div>
          <div class=\"fomc-meeting__month\"><strong>December</strong></div><div class=\"fomc-meeting__date\">8-9*</div>"""

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config" / "context-sources.json").write_text(json.dumps(config), encoding="utf-8")
            payloads = {"https://example.com/news": rss, "https://example.com/fomc": fomc}
            bundle = collect_context(
                root,
                now=datetime(2026, 8, 28, 8, tzinfo=timezone.utc),
                fetcher=lambda url: payloads[url],
            )

        self.assertEqual([item["title"] for item in bundle["past_24h"]], ["Fresh macro news"])
        self.assertEqual(len(bundle["future_90d"]), 1)
        self.assertIn("September", bundle["future_90d"][0]["title"])

    def test_optional_source_failure_keeps_bundle_usable(self) -> None:
        config = {
            "past_hours": 24,
            "future_days": 90,
            "sources": [
                {
                    "id": "optional",
                    "label": "optional",
                    "handler": "past_rss",
                    "source_name": "Official",
                    "source_tier": "official_primary",
                    "url": "https://example.com/fail",
                    "required": False,
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config").mkdir()
            (root / "config" / "context-sources.json").write_text(json.dumps(config), encoding="utf-8")
            bundle = collect_context(
                root,
                now=datetime(2026, 8, 28, 8, tzinfo=timezone.utc),
                fetcher=lambda _url: (_ for _ in ()).throw(RuntimeError("temporary failure")),
            )
        self.assertEqual(bundle["status"], "partial")
        self.assertEqual(bundle["past_24h"], [])
        self.assertEqual(bundle["source_health"][0]["status"], "error")


if __name__ == "__main__":
    unittest.main()
