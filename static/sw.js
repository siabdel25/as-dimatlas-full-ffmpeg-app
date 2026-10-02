// Service worker : coquille de l'app en cache (démarrage instantané + page hors-ligne).
// Jamais de cache pour /api (tâches, médias, radio) : toujours le réseau.
const VERSION = "v1";
const CACHE = `videocoder-${VERSION}`;
const SHELL = ["/", "/app.css", "/app.js", "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.pathname.startsWith("/api/")) return;   // laisse passer (flux audio/vidéo, Range, etc.)

  // Même origine : réseau d'abord, repli sur le cache (toujours à jour, marche hors-ligne).
  // CDN (Vue, Bootstrap, polices) : cache d'abord, rempli au fil de l'eau.
  const memeOrigine = url.origin === location.origin;
  e.respondWith(
    memeOrigine
      ? fetch(req).then(r => { const c = r.clone(); caches.open(CACHE).then(ca => ca.put(req, c)); return r; })
          .catch(() => caches.match(req).then(r => r || caches.match("/")))
      : caches.match(req).then(r => r || fetch(req).then(n => {
          const c = n.clone(); caches.open(CACHE).then(ca => ca.put(req, c)); return n;
        }))
  );
});
