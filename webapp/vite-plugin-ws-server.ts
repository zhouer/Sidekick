// webapp/vite-plugin-ws-server.ts
import type { Plugin } from 'vite';
import { WebSocketServer, WebSocket, AddressInfo } from 'ws'; // Import AddressInfo
import type { AnnouncePayload, PeerRole } from './src/types';

// Define the expected configuration options for the plugin
interface WebSocketPluginOptions {
    host: string;
    port: number;
}

// --- State Maps (remain the same) ---
// Map: WebSocket instance -> { peerId, role, version }
const connectedPeers = new Map<WebSocket, { peerId: string, role: string, version: string }>();
// Map: peerId -> AnnouncePayload (last known state)
const lastAnnouncements = new Map<string, AnnouncePayload>();

// --- Helper Functions (remain mostly the same, added logging) ---

/**
 * Broadcasts a message to all connected clients except the sender.
 * Logs the broadcast attempt.
 */
function broadcastMessage(wss: WebSocketServer, senderWs: WebSocket, message: object | string, description: string = ""): void {
    const messageString = typeof message === 'string' ? message : JSON.stringify(message);
    let recipients = 0;
    wss.clients.forEach((client) => {
        if (client !== senderWs && client.readyState === WebSocket.OPEN) {
            try {
                client.send(messageString);
                recipients++;
            } catch (e) {
                // Get peerId if available for better logging
                const recipientInfo = connectedPeers.get(client);
                const recipientId = recipientInfo ? recipientInfo.peerId : 'unknown';
                console.error(`[WSS][Broadcast] Error sending ${description || 'message'} to client ${recipientId}:`, e);
            }
        }
    });
    if (description) {
        console.log(`[WSS][Broadcast] Broadcasted ${description} to ${recipients} recipients.`);
    }
}

/**
 * Sends a message to a specific client.
 * Logs the send attempt.
 */
function sendToClient(clientWs: WebSocket, message: object | string, description: string = ""): void {
    if (clientWs.readyState === WebSocket.OPEN) {
        try {
            const messageString = typeof message === 'string' ? message : JSON.stringify(message);
            clientWs.send(messageString);
            if (description) {
                const recipientInfo = connectedPeers.get(clientWs); // Try to get peerId
                const recipientId = recipientInfo ? recipientInfo.peerId : 'the target client';
                console.log(`[WSS][Send] Sent ${description} to ${recipientId}.`);
            }
        } catch (e) {
            const recipientInfo = connectedPeers.get(clientWs);
            const recipientId = recipientInfo ? recipientInfo.peerId : 'unknown';
            console.error(`[WSS][Send] Error sending ${description || 'message'} to client ${recipientId}:`, e);
        }
    } else {
        const recipientInfo = connectedPeers.get(clientWs);
        const recipientId = recipientInfo ? recipientInfo.peerId : 'the target client';
        console.warn(`[WSS][Send] Attempted to send ${description || 'message'} to ${recipientId}, but client state is ${clientWs.readyState}.`);
    }
}

// --- Vite Plugin Implementation ---
export default function websocketServerPlugin(options: WebSocketPluginOptions): Plugin {
    // Use the provided host and port from options
    const { host, port } = options;
    let serverStarted = false;

    return {
        name: 'vite-plugin-ws-server',
        configureServer() {
            if (serverStarted) return;
            serverStarted = true;

            // Create WebSocket server with specified host and port
            const wss = new WebSocketServer({ host, port });

            wss.on('listening', () => {
                // Get the actual address info after the server starts listening
                const address = wss.address() as AddressInfo;
                console.log(`[WSS] WebSocket server started and listening on ws://${address.address}:${address.port}`);
            });

            wss.on('connection', (ws: WebSocket, req) => {
                // Log incoming connection with remote address if available
                const remoteAddress = req.socket.remoteAddress || 'unknown address';
                const remotePort = req.socket.remotePort || 'unknown port';
                console.log(`[WSS] New client connection opened from ${remoteAddress}:${remotePort}`);

                ws.on('message', (data) => {
                    let message: any;
                    const rawData = data.toString();

                    // --- Message Parsing and Basic Validation ---
                    try {
                        message = JSON.parse(rawData);
                        if (typeof message !== 'object' || message === null || !message.module || !message.method) {
                            throw new Error('Invalid message structure: missing module or method');
                        }
                        // Log parsed message content for clarity
                        console.log(`[WSS][Recv] From ${remoteAddress}:${remotePort}: ${JSON.stringify(message)}`);
                    } catch (e: any) {
                        console.error(`[WSS][Error] Invalid JSON or message structure from ${remoteAddress}:${remotePort}: ${e.message || e}`, rawData);
                        // ws.close(1003, "Invalid message format"); // Optionally close
                        return;
                    }

                    // --- Handle System Announce Messages ---
                    if (message.module === 'system' && message.method === 'announce') {
                        const payload = message.payload as AnnouncePayload;
                        // Payload validation
                        if (!payload || typeof payload !== 'object' || !payload.peerId || !payload.role || !payload.status || !payload.version || typeof payload.timestamp !== 'number') {
                            console.warn(`[WSS][Announce] Received invalid or incomplete payload from ${remoteAddress}:${remotePort}:`, payload);
                            return;
                        }

                        const { peerId, role, status, version, timestamp } = payload;
                        const peerDescription = `${role} peer ${peerId} (v${version})`; // Reusable description

                        if (status === 'online') {
                            console.log(`[WSS][Announce] ONLINE from ${peerDescription}`);
                            const peerInfo = { peerId, role, version };

                            // --- Send History ---
                            // Gather announcements of other currently online peers
                            const historyAnnouncements: AnnouncePayload[] = [];
                            lastAnnouncements.forEach((announce, existingPeerId) => {
                                if (existingPeerId !== peerId && announce.status === 'online') {
                                    historyAnnouncements.push(announce);
                                }
                            });
                            // Send the history list to the newly connected peer
                            if (historyAnnouncements.length > 0) {
                                console.log(`[WSS][History] Sending ${historyAnnouncements.length} online peer announcements to ${peerId}`);
                                historyAnnouncements.forEach(histAnnounce => {
                                    const historyMsg = { id: 0, module: 'system', method: 'announce', payload: histAnnounce };
                                    sendToClient(ws, historyMsg, `history announce for ${histAnnounce.peerId}`);
                                });
                            } else {
                                console.log(`[WSS][History] No other online peers found for ${peerId}`);
                            }

                            // --- Store Peer Info ---
                            // Associate WebSocket connection with peer identity
                            connectedPeers.set(ws, peerInfo);
                            // Update the central state with the latest announcement
                            lastAnnouncements.set(peerId, payload);

                            // --- Broadcast Online Status ---
                            broadcastMessage(wss, ws, message, `ONLINE announce for ${peerId}`);

                        } else if (status === 'offline') {
                            // Handle graceful offline announcement
                            console.log(`[WSS][Announce] OFFLINE from ${peerDescription}`);

                            // Update stored status for this peer
                            const existingAnnounce = lastAnnouncements.get(peerId);
                            if (existingAnnounce) {
                                lastAnnouncements.set(peerId, { ...existingAnnounce, status: 'offline', timestamp });
                            } else {
                                // Record the offline status even if 'online' was missed
                                lastAnnouncements.set(peerId, payload);
                                console.warn(`[WSS][Announce] Recorded offline status for ${peerId} which was not previously known as online.`);
                            }

                            // Broadcast the offline status to others
                            broadcastMessage(wss, ws, message, `OFFLINE announce for ${peerId}`);
                            // Don't remove from connectedPeers here; wait for 'close' event

                        } else {
                            // Handle unknown status values
                            console.warn(`[WSS][Announce] Received system/announce from ${peerId} with unknown status: '${status}'`);
                        }

                    } else {
                        // --- Broadcast Other Message Types ---
                        // Relay module/global messages without deep inspection
                        const messageDescription = `${message.module}/${message.method}`;
                        // Log broadcast with peer ID if available
                        const senderInfo = connectedPeers.get(ws);
                        const senderId = senderInfo ? senderInfo.peerId : `${remoteAddress}:${remotePort}`;
                        console.log(`[WSS][Relay] Broadcasting ${messageDescription} from ${senderId}`);
                        broadcastMessage(wss, ws, message, messageDescription);
                    }
                }); // End ws.on('message')

                ws.on('close', (code, reason) => {
                    const reasonString = reason?.toString() || 'No reason given';
                    // --- Handle Disconnection ---
                    const peerInfo = connectedPeers.get(ws);

                    if (peerInfo) {
                        const { peerId, role, version } = peerInfo;
                        const peerDescription = `${role} peer ${peerId} (v${version})`;
                        console.log(`[WSS][Close] Connection closed for ${peerDescription}. Code: ${code}, Reason: ${reasonString}`);

                        // Clean up active connection mapping
                        connectedPeers.delete(ws);
                        console.log(`[WSS][State] Removed ${peerId} from active connections map.`);

                        // Check if peer already announced offline gracefully
                        const lastAnnounce = lastAnnouncements.get(peerId);
                        if (lastAnnounce?.status === 'offline') {
                            console.log(`[WSS][Close] ${peerId} disconnected gracefully (status was already offline).`);
                        } else {
                            // Abnormal disconnect: Status was 'online' or unknown
                            console.warn(`[WSS][Close] ${peerId} disconnected abnormally (status was '${lastAnnounce?.status || 'unknown'}'). Generating offline announce.`);

                            // Generate and broadcast an offline announcement
                            const offlinePayload: AnnouncePayload = {
                                peerId,
                                role: role as PeerRole,
                                status: 'offline',
                                version,
                                timestamp: Date.now()
                            };
                            const offlineMsg = { id: 0, module: 'system', method: 'announce', payload: offlinePayload };

                            // Update central state
                            lastAnnouncements.set(peerId, offlinePayload);

                            // Broadcast to remaining peers
                            // 'ws' is already closed, so broadcast won't send to it
                            broadcastMessage(wss, ws, offlineMsg, `generated OFFLINE announce for ${peerId}`);
                        }
                    } else {
                        // Client disconnected before identifying itself
                        console.log(`[WSS][Close] Connection closed for unidentified client from ${remoteAddress}:${remotePort}. Code: ${code}, Reason: ${reasonString}`);
                    }
                }); // End ws.on('close')

                ws.on('error', (error) => {
                    // Log errors associated with a specific connection
                    const peerInfo = connectedPeers.get(ws);
                    const clientId = peerInfo ? peerInfo.peerId : `${remoteAddress}:${remotePort}`;
                    console.error(`[WSS][Error] WebSocket connection error for ${clientId}:`, error);
                    // The 'close' event will likely handle cleanup
                }); // End ws.on('error')

            }); // End wss.on('connection')

            wss.on('error', (error: NodeJS.ErrnoException) => { // Add type for error
                // Handle server-level errors
                if (error.code === 'EADDRINUSE') {
                    console.error(`[WSS][Fatal] Port ${port} is already in use. Cannot start WebSocket server.`);
                    // Consider exiting the process or notifying the user more explicitly
                    // process.exit(1);
                } else {
                    console.error('[WSS][Fatal] WebSocket Server error:', error);
                }
                // Mark as not started if server fails to listen
                serverStarted = false;
            });

        } // End configureServer
    }; // End Plugin object
} // End websocketServerPlugin