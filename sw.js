const CACHE_NAME = 'kurdish-charts-v1';
const urlsToCache = [
  '/aura-erbil/',
  '/aura-erbil/index.html',
  '/aura-erbil/charts_quant.js',
  '/aura-erbil/data/data.json'
];
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
  );
});
self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(response => response || fetch(event.request))
  );
});
