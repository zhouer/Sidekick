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

        // Common function to broadcast messages
        const broadcastMessage = (senderPeerId, message) => {
            for (const [otherId, info] of this.clients) {
                // Broadcast to all other peers regardless of role
                if (otherId !== senderPeerId) {
                    info.ws.send(message);
                }
            }
        };

        // Send existing online peers to the new client immediately upon connection
        const sendPeerList = () => {
            for (const [otherId, info] of this.clients) {
                const ann = {
                    id: 0,
                    component: 'system',
                    type: 'announce',
                    payload: {
                        peerId: otherId,
                        role: info.role,
                        status: 'online',
                        version: info.version,
                        timestamp: info.timestamp
                    }
                };
                server.send(JSON.stringify(ann));
            }
        };

        // Send the current peer list immediately
        sendPeerList();

        // Handle incoming messages
        server.addEventListener('message', (event) => {
            let msg;
            try {
                msg = JSON.parse(event.data);
            } catch {
                return; // ignore non-JSON messages
            }
            const { component, type, payload } = msg;

            // Process system announce messages
            if (component === 'system' && type === 'announce') {
                const { peerId: id, role: r, status, version } = payload;
                peerId = id;

                if (status === 'online') {
                    // Register this client with timestamp
                    const timestamp = payload.timestamp || Date.now();
                    this.clients.set(id, { ws: server, role: r, version, timestamp });
                } else if (status === 'offline') {
                    // Remove client
                    this.clients.delete(id);
                }
            }

            // Relay all messages
            if (!peerId) return;
            const sender = this.clients.get(peerId);
            if (!sender) return;
            broadcastMessage(peerId, event.data);
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
                const offlineMsg = JSON.stringify(offline);
                // Use the common broadcastMessage function
                broadcastMessage(peerId, offlineMsg);
            }
        });

        // Return the client WebSocket to complete the upgrade
        return new Response(null, { status: 101, webSocket: client });
    }
}
