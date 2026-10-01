const CACHE='mlb-picks-pwa-v13';
const ASSETS=['./?pwa=13','./index.html','./manifest.webmanifest?v=13','./apple-touch-icon.png?v=13','./slip-builder.js?v=13','./nav-fix.js?v=13'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(Promise.all([caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))),self.clients.claim()])));
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(u.origin===location.origin)e.respondWith(fetch(e.request).catch(()=>caches.match(e.request)));});