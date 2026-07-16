const CACHE_VERSION = 'v8';
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
                console.log('[SW] ✅ Notification shown');
                // Set app badge if supported and count > 0
                if ('setAppBadge' in navigator && data.badgeCount > 0) {
                    navigator.setAppBadge(data.badgeCount)
                        .then(() => console.log('[SW] ✅ Badge set to', data.badgeCount))
                        .catch(err => console.log('[SW] ❌ Failed to set badge:', err));
                } else if ('setAppBadge' in navigator && data.badgeCount === 0) {
                    // Optionally clear badge if count is 0
                    navigator.clearAppBadge()
                        .then(() => console.log('[SW] ✅ Badge cleared'))
                        .catch(err => console.log('[SW] ❌ Failed to clear badge:', err));
                } else {
                    console.log('[SW] ⚠️ Badge API not available');
                }
            })
            .catch(err => console.log('[SW] ❌ Notification error:', err))
    );
});

// ==============================================================
// 👆 NOTIFICATION CLICK HANDLER – opens the app and clears badge
// ==============================================================
self.addEventListener('notificationclick', function(event) {
    console.log('[SW] Notification clicked');
    event.notification.close();
    const url = event.notification.data?.url || '/';
    // Clear badge when notification is clicked
    if ('clearAppBadge' in navigator) {
        navigator.clearAppBadge()
            .then(() => console.log('[SW] ✅ Badge cleared on click'))
            .catch(err => console.log('[SW] ❌ Failed to clear badge:', err));
    }
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
