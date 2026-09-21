const CACHE_PREFIX = "macro-liquidity-";
const SHELL_CACHE = `${CACHE_PREFIX}shell-v48`;
const DATA_CACHE = `${CACHE_PREFIX}data-v3`;
const scopedUrl = (path) => new URL(path, self.registration.scope).href;
const scopedPath = (path) => new URL(path, self.registration.scope).pathname;
const SHELL = [
  self.registration.scope,
  scopedUrl("index.html"),
  scopedUrl("assets/app.css?v=48"),
  scopedUrl("assets/coinbase-premium.js?v=47"),
  scopedUrl("assets/app.js?v=48"),
  scopedUrl("assets/icon.svg"),
  scopedUrl("manifest.webmanifest")
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key.startsWith(CACHE_PREFIX) && ![SHELL_CACHE, DATA_CACHE].includes(key))
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith(scopedPath("api/"))) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(DATA_CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(async () => {
          const cached = await caches.match(request);
          if (!cached) return Response.error();
          const headers = new Headers(cached.headers);
          headers.set("X-Dashboard-Cache", "offline");
          return new Response(await cached.blob(), {
            status: cached.status,
            statusText: cached.statusText,
            headers
          });
        })
    );
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(SHELL_CACHE).then((cache) => cache.put(scopedUrl("index.html"), copy));
          }
          return response;
        })
        .catch(() => caches.match(scopedUrl("index.html")))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => cached || fetch(request))
  );
});
