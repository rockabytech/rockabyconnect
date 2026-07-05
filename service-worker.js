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
// 🔔 PUSH NOTIFICATION HANDLER
// ==============================================================
self.addEventListener('push', function(event) {
    console.log('[SW] 🚀 Push event received!', event);
    
    let data = {};
    if (event.data) {
        try {
            data = event.data.json();
            console.log('[SW] Parsed push data:', data);
        } catch (e) {
            console.log('[SW] Failed to parse JSON, using text:', e);
            data = {
                title: 'RockabyConnect',
                body: event.data.text() || 'New update',
                url: '/'
            };
        }
    } else {
        console.log('[SW] No data in push event');
    }

    const title = data.title || 'RockabyConnect';
    const options = {
        body: data.body || 'You have a new notification.',
        // Remove icon and badge temporarily to test
        data: {
            url: data.url || '/'
        },
        vibrate: [200, 100, 200],
        requireInteraction: true,
        // Add these to make it more visible
        silent: false,
        renotify: true
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
