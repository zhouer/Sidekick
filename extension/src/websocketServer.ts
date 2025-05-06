import * as vscode from 'vscode';
import { WebSocketServer, WebSocket, AddressInfo } from 'ws';
import type { AnnouncePayload, PeerRole, SentMessage, ReceivedMessage } from './types'; // Adjust path as needed

// --- Type Definitions ---
interface PeerInfo {
    peerId: string;
    role: PeerRole;
    version: string;
    ws: WebSocket; // Keep reference to the WebSocket connection
}

// --- State Management ---
const connectedPeers = new Map<WebSocket, PeerInfo>(); // Map: WS -> PeerInfo
const lastAnnouncements = new Map<string, AnnouncePayload>(); // Map: peerId -> AnnouncePayload

let wss: WebSocketServer | null = null;
let serverPort: number = 5163; // Default, will be updated from config
let serverHost: string = 'localhost'; // Default
let isServerRunning = false;

// --- Logging ---
// Use VS Code OutputChannel for better visibility
const outputChannel = vscode.window.createOutputChannel("Sidekick Server");
function logInfo(message: string) {
    console.log(`[WSS] ${message}`);
    outputChannel.appendLine(`[INFO] ${message}`);
}
function logWarn(message: string) {
    console.warn(`[WSS] ${message}`);
    outputChannel.appendLine(`[WARN] ${message}`);
}
function logError(message: string, error?: any) {
    console.error(`[WSS] ${message}`, error);
    outputChannel.appendLine(`[ERROR] ${message}${error ? `: ${error}` : ''}`);
}

// --- Helper Functions (Adapted for VS Code logging) ---

function broadcastMessage(senderWs: WebSocket, message: object | string, description: string = ""): void {
    if (!wss) return;
    const messageString = typeof message === 'string' ? message : JSON.stringify(message);
    let recipients = 0;
    wss.clients.forEach((client) => {
        if (client !== senderWs && client.readyState === WebSocket.OPEN) {
            try {
                client.send(messageString);
                recipients++;
            } catch (e) {
                const recipientInfo = connectedPeers.get(client);
                const recipientId = recipientInfo ? recipientInfo.peerId : 'unknown';
                logError(`Broadcast error sending ${description || 'message'} to client ${recipientId}`, e);
            }
        }
    });
    if (description) {
        const msgType = (typeof message === 'object' && message !== null) ? (message as any).type : 'unknown';
        logInfo(`Broadcasted ${description} (type: ${msgType}) to ${recipients} recipients.`);
    }
}

function sendToClient(clientWs: WebSocket, message: object | string, description: string = ""): void {
    if (clientWs.readyState === WebSocket.OPEN) {
        try {
            const messageString = typeof message === 'string' ? message : JSON.stringify(message);
            clientWs.send(messageString);
            if (description) {
                const recipientInfo = connectedPeers.get(clientWs);
                const recipientId = recipientInfo ? recipientInfo.peerId : 'the target client';
                const msgType = (typeof message === 'object' && message !== null) ? (message as any).type : 'unknown';
                logInfo(`Sent ${description} (type: ${msgType}) to ${recipientId}.`);
            }
        } catch (e) {
            const recipientInfo = connectedPeers.get(clientWs);
            const recipientId = recipientInfo ? recipientInfo.peerId : 'unknown';
            logError(`Send error sending ${description || 'message'} to client ${recipientId}`, e);
        }
    } else {
        const recipientInfo = connectedPeers.get(clientWs);
        const recipientId = recipientInfo ? recipientInfo.peerId : 'the target client';
        logWarn(`Attempted to send ${description || 'message'} to ${recipientId}, but client state is ${clientWs.readyState}.`);
    }
}

// --- Main Server Logic ---

export function startWebSocketServer(): Promise<void> {
    return new Promise((resolve, reject) => {
        if (wss || isServerRunning) {
            logWarn('WebSocket server already running or starting.');
            resolve();
            return;
        }

        // Get configuration
        const config = vscode.workspace.getConfiguration('sidekick.websocket');
        serverPort = config.get<number>('port') ?? 5163;
        serverHost = config.get<string>('host') ?? 'localhost';

        logInfo(`Attempting to start WebSocket server on ${serverHost}:${serverPort}...`);
        wss = new WebSocketServer({ host: serverHost, port: serverPort });
        isServerRunning = true; // Assume starting

        wss.on('listening', () => {
            const address = wss?.address() as AddressInfo;
            logInfo(`WebSocket server started and listening on ws://${address.address}:${address.port}`);
            isServerRunning = true;
            resolve();
        });

        wss.on('connection', (ws: WebSocket, req) => {
            const remoteAddress = req.socket.remoteAddress || 'unknown address';
            const remotePort = req.socket.remotePort || 'unknown port';
            logInfo(`New client connection opened from ${remoteAddress}:${remotePort}`);

            ws.on('message', (data) => {
                let message: ReceivedMessage | SentMessage; // Accept both for relay
                const rawData = data.toString();
                try {
                    message = JSON.parse(rawData);
                    if (typeof message !== 'object' || message === null || !message.component || !message.type) {
                        throw new Error('Invalid message structure: missing component or type');
                    }
                    const senderInfo = connectedPeers.get(ws);
                    const senderId = senderInfo ? senderInfo.peerId : `${remoteAddress}:${remotePort}`;
                    logInfo(`Recv from ${senderId}: ${JSON.stringify(message)}`);
                } catch (e: any) {
                    logError(`Invalid JSON or message structure from ${remoteAddress}:${remotePort}: ${e.message || e}`, rawData);
                    return;
                }

                // --- Handle System Announce ---
                if (message.component === 'system' && message.type === 'announce') {
                    const payload = message.payload as AnnouncePayload;
                    if (!payload || !payload.peerId || !payload.role || !payload.status || !payload.version || typeof payload.timestamp !== 'number') {
                        logWarn(`Received invalid system/announce payload from ${remoteAddress}:${remotePort}: ${JSON.stringify(payload)}`);
                        return;
                    }
                    const { peerId, role, status, version, timestamp } = payload;
                    const peerDescription = `${role} peer ${peerId} (v${version})`;

                    if (status === 'online') {
                        logInfo(`ONLINE announce from ${peerDescription}`);
                        const peerInfo: PeerInfo = { peerId, role, version, ws };

                        // --- Send History ---
                        const historyAnnouncements: AnnouncePayload[] = [];
                        lastAnnouncements.forEach((announce, existingPeerId) => {
                            if (existingPeerId !== peerId && announce.status === 'online') {
                                historyAnnouncements.push(announce);
                            }
                        });
                        if (historyAnnouncements.length > 0) {
                            logInfo(`Sending ${historyAnnouncements.length} online peer announcements to ${peerId}`);
                            historyAnnouncements.forEach(histAnnounce => {
                                const historyMsg = { id: 0, component: 'system', type: 'announce', payload: histAnnounce };
                                sendToClient(ws, historyMsg, `history announce for ${histAnnounce.peerId}`);
                            });
                        }

                        // --- Store & Broadcast ---
                        connectedPeers.set(ws, peerInfo);
                        lastAnnouncements.set(peerId, payload);
                        broadcastMessage(ws, message, `ONLINE announce for ${peerId}`);

                    } else if (status === 'offline') {
                        logInfo(`OFFLINE announce from ${peerDescription}`);
                        const existingAnnounce = lastAnnouncements.get(peerId);
                        if (existingAnnounce) {
                            lastAnnouncements.set(peerId, { ...existingAnnounce, status: 'offline', timestamp });
                        } else {
                            lastAnnouncements.set(peerId, payload); // Record offline even if missed online
                        }
                        broadcastMessage(ws, message, `OFFLINE announce for ${peerId}`);
                        // Don't remove from connectedPeers here, wait for 'close'
                    } else {
                        logWarn(`Received system/announce from ${peerId} with unknown status: '${status}'`);
                    }
                } else {
                    // --- Relay Other Messages ---
                    const messageDescription = `${message.component}/${message.type}`;
                    const senderInfo = connectedPeers.get(ws);
                    const senderId = senderInfo ? senderInfo.peerId : `${remoteAddress}:${remotePort}`;
                    logInfo(`Relaying ${messageDescription} from ${senderId}`);
                    broadcastMessage(ws, message, messageDescription);
                }
            }); // End ws.on('message')

            ws.on('close', (code, reason) => {
                const reasonString = reason?.toString() || 'No reason given';
                const peerInfo = connectedPeers.get(ws);
                if (peerInfo) {
                    const { peerId, role, version } = peerInfo;
                    const peerDescription = `${role} peer ${peerId} (v${version})`;
                    logInfo(`Connection closed for ${peerDescription}. Code: ${code}, Reason: ${reasonString}`);

                    connectedPeers.delete(ws);
                    logInfo(`Removed ${peerId} from active connections map.`);

                    const lastAnnounce = lastAnnouncements.get(peerId);
                    if (lastAnnounce?.status !== 'offline') {
                        logWarn(`${peerId} disconnected abnormally (status was '${lastAnnounce?.status || 'unknown'}'). Generating offline announce.`);
                        const offlinePayload: AnnouncePayload = {
                            peerId, role, status: 'offline', version, timestamp: Date.now()
                        };
                        const offlineMsg = { id: 0, component: 'system', type: 'announce', payload: offlinePayload };
                        lastAnnouncements.set(peerId, offlinePayload);
                        broadcastMessage(ws, offlineMsg, `generated OFFLINE announce for ${peerId}`);
                    } else {
                        logInfo(`${peerId} disconnected gracefully (status was already offline).`);
                    }
                } else {
                    logInfo(`Connection closed for unidentified client from ${remoteAddress}:${remotePort}. Code: ${code}, Reason: ${reasonString}`);
                }
            }); // End ws.on('close')

            ws.on('error', (error) => {
                const peerInfo = connectedPeers.get(ws);
                const clientId = peerInfo ? peerInfo.peerId : `${remoteAddress}:${remotePort}`;
                logError(`WebSocket connection error for ${clientId}`, error);
            }); // End ws.on('error')
        }); // End wss.on('connection')

        wss.on('error', (error: NodeJS.ErrnoException) => {
            isServerRunning = false; // Mark as not running on error
            if (error.code === 'EADDRINUSE') {
                const errorMsg = `Port ${serverPort} is already in use. Cannot start Sidekick WebSocket server. (Is the Vite dev server running?)`;
                logError(errorMsg);
                vscode.window.showErrorMessage(errorMsg);
                reject(new Error(errorMsg));
            } else {
                logError('WebSocket Server error:', error);
                vscode.window.showErrorMessage(`Sidekick WebSocket Server error: ${error.message}`);
                reject(error);
            }
            wss = null; // Clear the server instance on error
            // Clear state maps
            connectedPeers.clear();
            lastAnnouncements.clear();
        });
    });
}

export function stopWebSocketServer(): Promise<void> {
    return new Promise((resolve) => {
        logInfo('Attempting to stop WebSocket server...');
        if (wss) {
            // Send offline announce for the server itself? Not really applicable.
            // Close all client connections gracefully
            wss.clients.forEach(client => {
                client.close(1001, 'Server shutting down'); // 1001 = Going Away
            });

            wss.close((err) => {
                if (err) {
                    logError('Error closing WebSocket server:', err);
                } else {
                    logInfo('WebSocket server closed successfully.');
                }
                wss = null;
                isServerRunning = false;
                connectedPeers.clear();
                lastAnnouncements.clear();
                resolve();
            });
        } else {
            logInfo('WebSocket server was not running.');
            isServerRunning = false; // Ensure flag is reset
            resolve();
        }
    });
}