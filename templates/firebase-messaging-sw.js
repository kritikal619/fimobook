importScripts("/static/js/renewal-push-sw.js?v=20261009-pwa-push-1");

const CACHE_NAME = "fimobook-pwa-v3";
const OFFLINE_URL = "/static/offline.html";
const PRECACHE_URLS = [
  OFFLINE_URL,
  "/static/icons/pwa-icon-192.png",
  "/static/icons/pwa-icon-512.png",
  "/static/icons/pwa-maskable-192.png?v=20260914-2",
  "/static/icons/pwa-maskable-512.png?v=20260914-2",
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    return;
  }

  if (url.origin !== self.location.origin || !url.pathname.startsWith("/static/")) return;
  // Partial requests must reach the network without using a full-file cache entry.
  if (request.headers.has("range")) return;

  event.respondWith(
    caches.match(request).then((cached) => {
      const updated = fetch(request).then(async (response) => {
        if (response.status === 200 && response.type === "basic") {
          try {
            const cache = await caches.open(CACHE_NAME);
            await cache.put(request, response.clone());
          } catch (error) {
            console.warn("Static asset cache write failed:", error);
          }
        }
        return response;
      });
      event.waitUntil(updated.then(() => undefined).catch(() => undefined));
      return cached || updated;
    })
  );
});

// Keep legacy FCM coupon subscriptions working without making the PWA worker
// depend on loading a third-party SDK. Native renewal/coupon events are handled
// (and stopped) by the first push listener above.
self.addEventListener("push", (event) => {
  let payload;
  try { payload = event.data.json(); } catch (_) { return; }
  const notification = payload.notification || {};
  const data = payload.data || {};
  if (!notification.title && data.type !== "coupon") return;
  event.waitUntil(self.registration.showNotification(notification.title || "FC모바일 쿠폰", {
    body: notification.body || "새 쿠폰이 도착했습니다.",
    icon: "/static/icons/android-launchericon-192-192.png",
    badge: "/static/icons/android-launchericon-72-72.png",
    data: { url: data.url || payload.fcmOptions?.link || "/coupons/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(event.notification?.data?.url || "/coupons/", self.location.origin);
  const url = target.origin === self.location.origin ? target.href : self.location.origin + "/coupons/";
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) {
          return client.navigate(url).then(() => client.focus());
        }
      }
      if (clients.openWindow) return clients.openWindow(url);
      return undefined;
    })
  );
});
