/*
 * Workforce CRM service worker.
 *
 * Scope: the static app shell only.
 *
 * Deliberately NOT cached: any response under the API base path. Business data (attendance,
 * ledger, salary, complaints, audit) must never be persisted in Cache Storage
 * (AGENTS.md section 8 - sensitive data exposure). Read-only screens still show the last
 * fetched data from the in-memory TanStack Query cache, which is cleared on sign-out.
 *
 * Attendance, claiming, submissions and financial actions are never queued for background
 * replay (docs/07_UI_SPEC.md section 5.5): a failed mutation must fail visibly so verification
 * is evaluated at the recorded event time.
 */

const VERSION = 'v1';
const SHELL_CACHE = `workforce-shell-${VERSION}`;
const ASSET_CACHE = `workforce-assets-${VERSION}`;

const SHELL_ASSETS = [
  '/offline',
  '/manifest.webmanifest',
  '/icons/icon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .catch(() => undefined)
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((key) => key !== SHELL_CACHE && key !== ASSET_CACHE).map((key) => caches.delete(key))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') self.skipWaiting();
});

function isApiRequest(url) {
  return url.pathname.startsWith('/api/');
}

function isStaticAsset(url) {
  return (
    url.pathname.startsWith('/_next/static/') ||
    url.pathname.startsWith('/icons/') ||
    url.pathname === '/manifest.webmanifest'
  );
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  if (url.origin !== self.location.origin) return;

  // Never cache API traffic; never serve a stale business record.
  if (isApiRequest(url)) return;

  // Mutations are always network-only.
  if (request.method !== 'GET') return;

  if (request.mode === 'navigate') {
    event.respondWith(
      (async () => {
        try {
          const response = await fetch(request);
          return response;
        } catch {
          const cache = await caches.open(SHELL_CACHE);
          const cached = await cache.match(request);
          if (cached) return cached;
          const offline = await cache.match('/offline');
          if (offline) return offline;
          return new Response('Offline', { status: 503, headers: { 'Content-Type': 'text/plain' } });
        }
      })()
    );
    return;
  }

  if (isStaticAsset(url)) {
    event.respondWith(
      (async () => {
        const cache = await caches.open(ASSET_CACHE);
        const cached = await cache.match(request);
        if (cached) return cached;
        try {
          const response = await fetch(request);
          if (response.ok) await cache.put(request, response.clone());
          return response;
        } catch {
          return new Response('', { status: 504 });
        }
      })()
    );
  }
});