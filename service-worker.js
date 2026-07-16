const CACHE_VERSION = 'v8'; // increment every time you change this file
const CACHE_NAME = 'rockabyconnect-' + CACHE_VERSION;
const urlsToCache = [
    '/',
    '/static/pngwing.com.png',
    '/static/icon-72.png',
    '/static/icon-96.png',
    '/static/icon-128.png',
    '/static/icon-144.png',
    '/static/icon-152.png',
    '/static/icon-192.png',
    '/static/icon-384.png',
    '/static/icon-512.png'
];

// ----- INSTALL -----
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return cache.addAll(urlsToCache);
        })
    );
});

// ----- ACTIVATE (delete old caches) -----
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('[SW] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// ----- FETCH (serve from cache if available) -----
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request).then(response => {
            return response || fetch(event.request);
        })
    );
});

// ==============================================================
// 🔔 PUSH NOTIFICATION HANDLER – reads payload from server
// ==============================================================
self.addEventListener('push', function(event) {
    console.log('[SW] 🚀 Push event received');

    let data = {
        title: 'RockabyConnect',
        body: 'You have a new notification',
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        url: '/',
        badgeCount: 0
    };

    if (event.data) {
        try {
            const parsed = event.data.json();
            console.log('[SW] Parsed JSON payload:', parsed);
            data.title = parsed.title || data.title;
            data.body = parsed.body || data.body;
            data.icon = parsed.icon || data.icon;
            data.badge = parsed.badge || data.badge;
            data.url = parsed.url || data.url;
            data.badgeCount = parsed.badgeCount || 0;
        } catch (e) {
            const raw = event.data.text();
            console.log('[SW] Raw text payload:', raw);
            data.body = raw || data.body;
        }
    } else {
        console.log('[SW] No payload data');
    }

    const options = {
        body: data.body,
        icon: data.icon,
        badge: data.badge,
        vibrate: [200, 100, 200, 100, 200],
        requireInteraction: true,
        data: {
            url: data.url,
            badgeCount: data.badgeCount
        }
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
            .then(() => {
                // Set app badge if supported (PWA installed on Android)
                if ('setAppBadge' in navigator && data.badgeCount > 0) {
                    navigator.setAppBadge(data.badgeCount);
                }
                console.log('[SW] ✅ Notification shown. Badge count:', data.badgeCount);
            })
            .catch(err => console.log('[SW] ❌ Notification error:', err))
    );
});

// ==============================================================
// 👆 NOTIFICATION CLICK HANDLER – opens the app (PWA or browser)
// ==============================================================
self.addEventListener('notificationclick', function(event) {
    console.log('[SW] Notification clicked');
    event.notification.close();
    const url = event.notification.data?.url || '/';

    event.waitUntil(
        // Try to find an existing client window (the PWA)
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(windowClients => {
                // If there’s already a window with the same URL, focus it
                for (let client of windowClients) {
                    if (client.url === url && 'focus' in client) {
                        return client.focus();
                    }
                }
                // Otherwise open a new window – this will open in the PWA if installed
                return clients.openWindow(url);
            })
            .then(client => {
                if (!client) {
                    // Fallback: if openWindow fails, try to navigate the existing client
                    return clients.matchAll({ type: 'window', includeUncontrolled: true })
                        .then(clients => {
                            if (clients.length > 0) {
                                return clients[0].navigate(url);
                            }
                        });
                }
            })
            .catch(err => console.log('[SW] Notification click error:', err))
    );
});
