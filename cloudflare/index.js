export default {
    async fetch(request, env) {
        const url = new URL(request.url);
        // Only handle WebSocket upgrade path
        if (url.pathname === '/') {
            const sessionId = url.searchParams.get('session');
            if (!sessionId) {
                return new Response('Missing session id', { status: 400 });
            }
            // Route request to the Durable Object managing this session
            const objectId = env.SESSION_NAMESPACE.idFromName(sessionId);
            const durable = env.SESSION_NAMESPACE.get(objectId);
            return durable.fetch(request);
        }
        return new Response('Not found', { status: 404 });
    }
};

export class Session {
    constructor(state, env) {
        this.state = state;
        this.env = env;
        // Map of peerId -> { ws, role, version }
        this.clients = new Map();
    }

    async fetch(request) {
        // Enforce WebSocket upgrade
        if (request.headers.get('Upgrade') !== 'websocket') {
            return new Response('Expected WebSocket', { status: 426 });
        }

        // Create client-server WebSocket pair
        const [client, server] = new WebSocketPair();
        server.accept();

        let peerId = null;

        // Handle incoming messages
        server.addEventListener('message', (event) => {
            let msg;
            try {
                msg = JSON.parse(event.data);
            } catch {
                return; // ignore non-JSON messages
            }
            const { component, type, payload } = msg;

            // Announce messages carry role information
            if (component === 'system' && type === 'announce') {
                const { peerId: id, role: r, status, version } = payload;
                peerId = id;

                if (status === 'online') {
                    // Register this client
                    this.clients.set(id, { ws: server, role: r, version });

                    // Send existing online announcements to new client
                    for (const [otherId, info] of this.clients) {
                        if (otherId !== id) {
                            const ann = {
                                id: 0,
                                component: 'system',
                                type: 'announce',
                                payload: {
                                    peerId: otherId,
                                    role: info.role,
                                    status: 'online',
                                    version: info.version,
                                    timestamp: Date.now()
                                }
                            };
                            server.send(JSON.stringify(ann));
                        }
                    }

                    // Broadcast this client's online announce to others
                    for (const [otherId, info] of this.clients) {
                        if (otherId !== id) info.ws.send(event.data);
                    }

                } else if (status === 'offline') {
                    // Remove client and broadcast offline status
                    this.clients.delete(id);
                    for (const [, info] of this.clients) {
                        info.ws.send(event.data);
                    }
                }
                return;
            }

            // Relay all other messages between roles
            if (!peerId) return;
            const sender = this.clients.get(peerId);
            if (!sender) return;
            for (const [otherId, info] of this.clients) {
                if (info.role !== sender.role) {
                    info.ws.send(event.data);
                }
            }
        });

        // Handle unexpected disconnection
        server.addEventListener('close', () => {
            if (peerId && this.clients.has(peerId)) {
                const info = this.clients.get(peerId);
                const { role: r, version: v } = info;
                this.clients.delete(peerId);
                const offline = {
                    id: 0,
                    component: 'system',
                    type: 'announce',
                    payload: {
                        peerId,
                        role: r,
                        status: 'offline',
                        version: v,
                        timestamp: Date.now()
                    }
                };
                for (const [, c] of this.clients) {
                    c.ws.send(JSON.stringify(offline));
                }
            }
        });

        // Return the client WebSocket to complete the upgrade
        return new Response(null, { status: 101, webSocket: client });
    }
}
