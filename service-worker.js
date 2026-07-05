const CACHE_NAME = 'rockabyconnect-v1';
const urlsToCache = [
    '/',
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
    console.log('[SW] Install event');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('[SW] Cached app assets');
                return cache.addAll(urlsToCache);
            })
            .catch(err => console.log('[SW] Cache failed:', err))
    );
});

// ----- FETCH -----
self.addEventListener('fetch', event => {
    event.respondWith(
        caches.match(event.request)
            .then(response => {
                return response || fetch(event.request);
            })
            .catch(() => {
                return caches.match('/');
            })
    );
});

// ----- ACTIVATE -----
self.addEventListener('activate', event => {
    console.log('[SW] Activate event');
    const cacheWhitelist = [CACHE_NAME];
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheWhitelist.indexOf(cacheName) === -1) {
                        console.log('[SW] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// ==============================================================
// 🔔 PUSH NOTIFICATION HANDLER - MINIMAL TEST VERSION
// ==============================================================
self.addEventListener('push', function(event) {
    console.log('[SW] 🚀 Push event received!', event);
    
    // Simple notification with NO icon, NO badge, NO vibrate
    const title = '🔔 RockabyConnect';
    const options = {
        body: 'You have a new notification!',
        requireInteraction: true,
        silent: false,
        data: {
            url: '/'
        }
    };
    
    console.log('[SW] Showing notification:', title, options);

    event.waitUntil(
        self.registration.showNotification(title, options)
            .then(() => console.log('[SW] ✅ Notification shown successfully'))
            .catch(err => console.log('[SW] ❌ Failed to show notification:', err))
    );
});

// ==============================================================
// 👆 NOTIFICATION CLICK HANDLER
// ==============================================================
self.addEventListener('notificationclick', function(event) {
    console.log('[SW] Notification clicked:', event);
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
