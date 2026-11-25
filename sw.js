/* Wie hier vroeger Zweef heeft geopend, heeft nog een oude service worker die pagina's uit
   zijn cache toont. Deze vervanger wist die cache en schrijft zichzelf uit. */
'use strict';
self.addEventListener('install', function () { self.skipWaiting(); });
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys()
      .then(function (keys) { return Promise.all(keys.map(function (k) { return caches.delete(k); })); })
      .then(function () { return self.registration.unregister(); })
      .then(function () { return self.clients.matchAll({ type: 'window' }); })
      .then(function (ramen) { ramen.forEach(function (r) { r.navigate(r.url); }); })
  );
});
