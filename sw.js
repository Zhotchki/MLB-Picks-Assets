const CACHE='mlb-picks-pwa-v4';
const ASSETS=['./?pwa=4','./index.html','./manifest.webmanifest?v=4','./apple-touch-icon.png?v=4'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(Promise.all([caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))),self.clients.claim()])));
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(u.origin===location.origin)e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});