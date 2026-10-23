/* Zweef — service worker: de app werkt ook offline.
   Verhoog VERSIE bij elke wijziging aan de bestanden, dan haalt de app de nieuwe versie op. */
'use strict';

var VERSIE = 'zweef-v1';
var THREE_URL = 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js';

var BESTANDEN = [
  './',
  'index.html',
  'style.css',
  'manifest.json',
  'scripts/app.js',
  'scripts/audio.js',
  'scripts/worlds/ruimte.js',
  'scripts/worlds/canyon.js',
  'scripts/worlds/wolken.js',
  'icons/icon-192.png',
  'icons/icon-512.png',
  'icons/icon-maskable-192.png',
  'icons/icon-maskable-512.png',
  'icons/apple-touch-icon.png',
  'icons/favicon-32.png',
  'materiaal/audio/ruimte/ruimte.mp3',
  'materiaal/audio/canyon/canyon.mp3',
  'materiaal/audio/wolken/wolken.mp3',
  THREE_URL
];

// Elk bestand apart: ontbreekt er één, dan lukt de installatie toch.
self.addEventListener('install', function (e) {
  e.waitUntil(
    caches.open(VERSIE).then(function (c) {
      return Promise.all(BESTANDEN.map(function (u) {
        return c.add(u).catch(function () { /* overslaan */ });
      }));
    }).then(function () { return self.skipWaiting(); })
  );
});

// Oude caches opruimen
self.addEventListener('activate', function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== VERSIE; })
        .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin && req.url !== THREE_URL) return;

  // Eerst de cache (werkt offline), anders het netwerk en bijschrijven
  e.respondWith(
    caches.match(req, { ignoreSearch: true }).then(function (hit) {
      if (hit) return hit;
      return fetch(req).then(function (res) {
        if (res && res.ok && res.status === 200) {
          var kopie = res.clone();
          caches.open(VERSIE).then(function (c) { c.put(req, kopie); });
        }
        return res;
      }).catch(function () {
        if (req.mode === 'navigate') return caches.match('index.html');
      });
    })
  );
});
