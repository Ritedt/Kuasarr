// Kuasarr Service Worker
// Minimal PWA support: precache static assets, offline fallback

const CACHE_NAME = 'kuasarr-static-v1';

// Static assets to precache
const PRECACHE_ASSETS = [
  '/static/logo.png',
  '/static/logo-192.png',
  '/static/manifest.webmanifest'
];

// Install: precache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activate: clean old caches, claim clients
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: cache-first for static assets, network-first for everything else
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Only handle same-origin requests
  if (url.origin !== location.origin) {
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        return cached || fetch(event.request).then((response) => {
          // Cache new static assets
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // API and other requests: network-first with offline fallback
  event.respondWith(
    fetch(event.request)
      .catch(() => {
        // Return offline page for navigation requests
        if (event.request.mode === 'navigate') {
          return new Response(
            `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kuasarr - Offline</title>
  <style>
    :root {
      --bg: #181a1b;
      --fg: #f1f1f1;
      --primary: #0d6efd;
    }
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      background: var(--bg);
      color: var(--fg);
      font-family: system-ui, sans-serif;
      text-align: center;
      padding: 1rem;
    }
    h1 { margin-bottom: 0.5rem; }
    p { color: #aaa; margin: 0.5rem 0; }
    button {
      margin-top: 1rem;
      padding: 0.75rem 1.5rem;
      background: var(--primary);
      color: #fff;
      border: none;
      border-radius: 0.5rem;
      font-size: 1rem;
      cursor: pointer;
    }
    button:hover { opacity: 0.9; }
  </style>
</head>
<body>
  <h1>📡 You're Offline</h1>
  <p>Kuasarr requires an internet connection to function.</p>
  <p>Please check your network and try again.</p>
  <button onclick="location.reload()">🔄 Retry</button>
</body>
</html>`,
            {
              status: 503,
              statusText: 'Service Unavailable',
              headers: { 'Content-Type': 'text/html; charset=utf-8' }
            }
          );
        }
        // For non-navigation requests, just fail
        return new Response('Offline', { status: 503 });
      })
  );
});
