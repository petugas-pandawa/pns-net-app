// sw.js — PNS.NET (reset mode)
// Unregister semua service worker lama lalu hapus semua cache

self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.map(k => caches.delete(k))))
      .then(() => self.clients.matchAll())
      .then(clients => clients.forEach(c => c.postMessage('SW_RESET')))
      .then(() => self.registration.unregister())
  );
});
