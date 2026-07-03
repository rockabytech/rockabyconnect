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
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Cached app assets');
                return cache.addAll(urlsToCache);
            })
            .catch(err => console.log('Cache failed:', err))
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
    const cacheWhitelist = [CACHE_NAME];
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheWhitelist.indexOf(cacheName) === -1) {
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
});

// ==============================================================
// 🔔 PUSH NOTIFICATION HANDLER
// ==============================================================
self.addEventListener('push', function(event) {
    let data = {};
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = {
                title: 'RockabyConnect',
                body: event.data.text() || 'New update',
                url: '/',
                icon: '/static/icon-192.png',
                badge: '/static/icon-192.png'
            };
        }
    }

    const title = data.title || 'RockabyConnect';
    const options = {
        body: data.body || 'You have a new notification.',
        icon: data.icon || '/static/icon-192.png',
        badge: data.badge || '/static/icon-192.png',
        data: {
            url: data.url || '/'
        },
        vibrate: [200, 100, 200],
        requireInteraction: true
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

// ==============================================================
// 👆 NOTIFICATION CLICK HANDLER
// ==============================================================
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    const url = event.notification.data?.url || '/';
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true })
            .then(windowClients => {
                // Check if there is already a window/tab open with the target URL
                for (let client of windowClients) {
                    if (client.url === url && 'focus' in client) {
                        return client.focus();
                    }
                }
                // If not, open a new window
                if (clients.openWindow) {
                    return clients.openWindow(url);
                }
            })
    );
});
