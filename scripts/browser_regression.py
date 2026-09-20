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

        race_result = page.evaluate(
            """async () => {
              const release = (await (await fetch('api/dashboard')).json()).release_id;
              const original = window.fetch;
              window.fetch = (url, options = {}) => {
                if (!String(url).includes('api/series')) return original(url, options);
                const range = new URL(url, location.href).searchParams.get('range');
                const delay = range === '1y' ? 120 : 10;
                const value = range === '1y' ? 111 : 222;
                return new Promise((resolve, reject) => {
                  const timer = setTimeout(() => resolve(new Response(JSON.stringify({
                    release_id: release,
                    points: [
                      {observed_at: '2026-01-01', value: 0},
                      {observed_at: '2026-01-02', value}
                    ]
                  }), {status: 200, headers: {'Content-Type': 'application/json'}})), delay);
                  options.signal?.addEventListener('abort', () => {
                    clearTimeout(timer);
                    reject(new DOMException('Aborted', 'AbortError'));
                  });
                });
              };
              const container = document.createElement('div');
              container.className = 'chart-shell';
              container.style.width = '360px';
              document.body.append(container);
              loadSeries('tga_daily', '1y', container);
              await new Promise(resolve => setTimeout(resolve, 5));
              await loadSeries('tga_daily', '1m', container);
              await new Promise(resolve => setTimeout(resolve, 150));
              return container.querySelector('circle title')?.textContent;
            }"""
        )
        if race_result != "1月2日：2.2 亿美元":
            raise AssertionError(f"stale series response won the race: {race_result!r}")

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

        result = {
            "status": "passed",
            "mobile_width": {"document": scroll_width, "viewport": viewport_width},
            "range_race": "latest_selection_won",
            "foreign_cache": "preserved",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
