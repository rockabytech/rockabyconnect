const CACHE_VERSION = 'v3'; // increment when you update this file
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
    console.log('[SW] Push event received');

    let data = {
        title: 'RockabyConnect',
        body: 'You have a new notification',
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        url: '/'
    };

    if (event.data) {
        try {
            const parsed = event.data.json();
            data.title = parsed.title || data.title;
            data.body = parsed.body || data.body;
            data.icon = parsed.icon || data.icon;
            data.badge = parsed.badge || data.badge;
            data.url = parsed.url || data.url;
        } catch (e) {
            // If payload is not JSON, use the raw text as body
            data.body = event.data.text() || data.body;
        }
    }

    const options = {
        body: data.body,
        icon: data.icon,
        badge: data.badge,
        vibrate: [200, 100, 200, 100, 200],
        requireInteraction: true,
        data: {
            url: data.url
        }
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
            .then(() => console.log('[SW] Notification shown'))
            .catch(err => console.log('[SW] Notification error:', err))
    );
});

// ==============================================================
// 👆 NOTIFICATION CLICK HANDLER – opens the app
// ==============================================================
self.addEventListener('notificationclick', function(event) {
    console.log('[SW] Notification clicked');
    event.notification.close();
    const url = event.notification.data?.url || '/';
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(windowClients => {
                for (let client of windowClients) {
                    if (client.url === url && 'focus' in client) {
                        return client.focus();
                    }
                }
                if (clients.openWindow) {
                    return clients.openWindow(url);
                }
            })
    );
});
