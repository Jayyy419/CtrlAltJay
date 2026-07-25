// Bumping this string is what makes browsers notice a new service-worker
// script and go through install/activate again — without it, a change to
// the fetch logic below never reaches anyone already registered.
const CACHE_NAME = "ctrlaltjay-v12";
const PRECACHE_URLS = [
  "/",
  "/static/images/PersonalLogo.ico",
];
// style.css/script.js are no longer precached here: they're now requested
// with a ?v=<mtime> cache-busting query (see inject_asset_version() in
// app.py), so a fixed, unversioned URL in this list would just accumulate
// as a permanently stale entry that the network-first fetch handler below
// never touches.

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
