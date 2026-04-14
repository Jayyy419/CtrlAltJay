const CACHE_NAME = "ctrlaltjay-v8";
const PRECACHE_URLS = [
  "/",
  "/static/css/style.css",
  "/static/js/script.js",
  "/static/images/PersonalLogo.ico",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);

  // Only cache same-origin requests — skip CDN, analytics, external resources
  if (url.origin !== self.location.origin) return;

  // Skip API calls and admin endpoints — always go to network
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/admin")) return;

  // Network-first for same-origin static assets and pages
  event.respondWith(
    fetch(request)
      .then((response) => {
        // Only cache valid responses (not errors, not opaque)
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      })
      .catch(() => caches.match(request))
  );
});
