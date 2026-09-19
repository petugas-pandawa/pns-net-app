// PNS.NET — Service Worker (Fase 5)
// Tujuan: app shell (index.html, manifest, sw.js sendiri) tetap bisa dibuka
// walau HP benar-benar tanpa internet. Data (via sync) tetap lewat IndexedDB,
// bukan lewat cache ini.

const CACHE_NAME = 'pnsnet-shell-v2'; // dinaikkan supaya cache lama otomatis diganti
const SHELL_FILES = [
  './',
  './index.html',
  './manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // JANGAN cache request ke Apps Script API — itu harus selalu live/fresh
  // (fallback offline untuk data ditangani oleh IndexedDB di index.html, bukan di sini)
  if (url.hostname.includes('script.google.com') || url.hostname.includes('script.googleusercontent.com')) {
    return; // biarkan lewat langsung, tidak diintervensi service worker
  }

  // App shell: cache-first, supaya tetap kebuka walau offline total
  event.respondWith(
    caches.match(event.request).then((cached) => {
      if (cached) return cached;
      return fetch(event.request).then((response) => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
        }
        return response;
      }).catch(() => cached);
    })
  );
});
