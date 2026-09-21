#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from playwright.sync_api import sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser(description="Browser regression checks for the dashboard")
    parser.add_argument("--url", default="http://127.0.0.1:8876/")
    args = parser.parse_args()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 390, "height": 844}, service_workers="allow"
        )
        page = context.new_page()
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_function("navigator.serviceWorker.controller !== null")
        scroll_width = page.evaluate("document.documentElement.scrollWidth")
        viewport_width = page.evaluate("window.innerWidth")
        if scroll_width > viewport_width + 2:
            raise AssertionError(
                f"mobile page overflows horizontally: {scroll_width}>{viewport_width}"
            )

        # Reproduce the real homepage path: a slow network-backed 3m request,
        # immediately followed by the locally cached 1y selection.  The late
        # 3m response must not overwrite the visible 1y chart.
        click_race_result = page.evaluate(
            """async () => {
              const release = state.data.release_id;
              const original = window.fetch;
              window.fetch = (url, options = {}) => {
                if (!String(url).includes('api/series') || !String(url).includes('range=3m')) return original(url, options);
                return new Promise((resolve, reject) => {
                  const timer = setTimeout(() => resolve(new Response(JSON.stringify({
                    release_id: release,
                    points: [
                      {observed_at: '2099-01-01', value: 1},
                      {observed_at: '2099-01-02', value: 999999}
                    ]
                  }), {status: 200, headers: {'Content-Type': 'application/json'}})), 120);
                  options.signal?.addEventListener('abort', () => {
                    clearTimeout(timer);
                    reject(new DOMException('Aborted', 'AbortError'));
                  });
                });
              };
              document.querySelector('.trend-range-button[data-range="3m"]').click();
              await new Promise(resolve => setTimeout(resolve, 5));
              document.querySelector('.trend-range-button[data-range="1y"]').click();
              await new Promise(resolve => setTimeout(resolve, 160));
              return {
                selected: document.querySelector('.trend-range-button[data-range="1y"]').getAttribute('aria-pressed'),
                title: document.querySelector('[data-main-chart] circle title')?.textContent || ''
              };
            }"""
        )
        if click_race_result["selected"] != "true" or "2099" in click_race_result["title"]:
            raise AssertionError(f"real range buttons allowed a stale response to win: {click_race_result!r}")

        main_chart = page.locator("[data-main-chart] svg")
        main_chart.hover(position={"x": 140, "y": 110})
        main_tooltip = page.locator("[data-main-chart] .chart-tooltip:not([hidden])")
        if main_tooltip.count() != 1 or not main_tooltip.inner_text().strip():
            raise AssertionError("main trend chart did not expose a hover readout")
        main_chart.focus()
        main_chart.press("ArrowLeft")
        if not main_tooltip.inner_text().strip():
            raise AssertionError("main trend chart did not expose a keyboard readout")

        page.locator('a[data-view="transmission"]').click()
        page.wait_for_selector(".curve-svg")
        curve_chart = page.locator(".curve-svg")
        curve_chart.hover(position={"x": 150, "y": 80})
        curve_tooltip = page.locator(".curve-chart-shell .chart-tooltip:not([hidden])")
        if curve_tooltip.count() != 1 or "%" not in curve_tooltip.inner_text():
            raise AssertionError("Treasury curve did not expose both date and value details")

        curve_states = page.evaluate(
            """() => ({
              missing: treasuryCurvePanel({treasury_curve: {spreads: {spread_10y_2y: {label: '10Y-2Y', value: null, available_for_analysis: false, quality_status: 'unavailable'}}}}),
              stale: treasuryCurvePanel({treasury_curve: {spreads: {spread_10y_2y: {label: '10Y-2Y', value: 10, observed_at: '2026-01-01', available_for_analysis: false, quality_status: 'stale_fallback'}}}}),
              current: treasuryCurvePanel({treasury_curve: {spreads: {spread_10y_2y: {label: '10Y-2Y', value: 10, observed_at: '2026-09-20', available_for_analysis: true, quality_status: 'fresh_network'}}}})
            })"""
        )
        if "不判断是否倒挂" not in curve_states["missing"]:
            raise AssertionError("missing curve spread was not rendered as unknown")
        if "不代表当前状态" not in curve_states["stale"]:
            raise AssertionError("stale curve spread was presented as current")
        if "当前未倒挂" not in curve_states["current"]:
            raise AssertionError("current positive curve spread was not rendered correctly")

        evidence_result = page.evaluate(
            """async () => {
              let link = document.querySelector('[data-evidence-metric]');
              if (!link) {
                link = document.createElement('a');
                link.href = '#ledger';
                link.dataset.evidenceMetric = 'tga_daily';
                link.dataset.evidenceDate = '2026-09-17';
                link.textContent = '证据测试';
                document.body.append(link);
              }
              const metricId = link.dataset.evidenceMetric;
              link.click();
              await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
              const detail = [...document.querySelectorAll('#view-ledger .metric-disclosure')]
                .find(item => item.dataset.metricId === metricId);
              return {
                available: true,
                hash: location.hash,
                open: Boolean(detail?.open),
                metricId,
                scrollWidth: document.documentElement.scrollWidth,
                viewportWidth: innerWidth
              };
            }"""
        )
        if evidence_result.get("available") and (
            evidence_result["hash"] != "#ledger"
            or not evidence_result["open"]
            or evidence_result["scrollWidth"] > evidence_result["viewportWidth"] + 2
        ):
            raise AssertionError(f"evidence drill-down failed: {evidence_result!r}")

        cache_result = page.evaluate(
            """async () => {
              const cache = await caches.open('another-app-cache');
              await cache.put('/other-app-entry', new Response('keep'));
              await navigator.serviceWorker.getRegistration().then(registration => registration.update());
              await new Promise(resolve => setTimeout(resolve, 500));
              return {
                keys: await caches.keys(),
                kept: Boolean(await caches.match('/other-app-entry'))
              };
            }"""
        )
        if not cache_result["kept"] or "another-app-cache" not in cache_result["keys"]:
            raise AssertionError("service worker deleted another app's cache")

        responsive_checks = []
        for width, height in ((320, 700), (844, 390)):
            page.set_viewport_size({"width": width, "height": height})
            page.wait_for_timeout(250)
            measured = page.evaluate("({document: document.documentElement.scrollWidth, viewport: innerWidth})")
            if measured["document"] > measured["viewport"] + 2:
                raise AssertionError(f"responsive overflow at {width}x{height}: {measured!r}")
            responsive_checks.append(f"{width}x{height}")

        result = {
            "status": "passed",
            "mobile_width": {"document": scroll_width, "viewport": viewport_width},
            "range_race": "latest_selection_won",
            "real_range_click_race": "local_1y_selection_won",
            "curve_missing_state": "unknown_not_non_inverted",
            "chart_interactions": "pointer_and_keyboard_readouts_visible",
            "evidence_drill_down": "opened_matching_metric",
            "responsive_viewports": responsive_checks,
            "foreign_cache": "preserved",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
