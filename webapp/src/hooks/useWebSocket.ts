import { useState, useEffect, useRef, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { SentMessage, SystemAnnounceMessage } from '../types';
const RECONNECT_DELAY = 1000; // Initial reconnect delay in milliseconds (1 seconds)
const MAX_RECONNECT_ATTEMPTS = 10; // Max attempts before giving up
const RECONNECT_BACKOFF_FACTOR = 1.5; // Multiplier for exponential backoff
const MAX_RECONNECT_DELAY = 30000; // Maximum delay between reconnect attempts (30 seconds)

// --- Types ---
/** Possible connection statuses for the WebSocket hook. */
type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

/**
 * Custom React hook to manage a persistent WebSocket connection with automatic reconnection.
 *
 * @param onMessageCallback - A callback function that will be invoked with parsed incoming WebSocket messages.
 * @param wsUrl - The WebSocket URL to connect to.
 * @param enabled - Whether the WebSocket connection is enabled (default: true).
 * @returns An object containing:
 *  - `isConnected` (boolean): Whether the WebSocket is currently connected.
 *  - `status` (ConnectionStatus): The current detailed connection status.
 *  - `sendMessage` (function): A stable function to send messages over the WebSocket.
 */
export function useWebSocket(
  onMessageCallback: (message: any) => void,
  wsUrl: string,
  enabled: boolean = true
) {
    // --- State ---
    /** Current connection state (true if OPEN, false otherwise). */
    const [isConnected, setIsConnected] = useState(false);
    /** Detailed connection status string. */
    const [status, setStatus] = useState<ConnectionStatus>('disconnected');

    // --- Refs ---
    /** Holds the current WebSocket instance. Null if not connected/connecting. */
    const ws = useRef<WebSocket | null>(null);
    /** Tracks the number of consecutive reconnect attempts. */
    const reconnectAttempts = useRef(0);
    /** Stores the ID of the scheduled reconnect timer (returned by setTimeout). */
    const reconnectTimeoutId = useRef<number | null>(null);
    /** Stores the unique peer ID for this Sidekick client instance. */
    const peerIdRef = useRef<string | null>(null);
    /** Flag to indicate if disconnection was initiated manually by the client. */
    const manualDisconnect = useRef(false);

    // --- Effects ---
    /** Generate a unique Peer ID for this client instance on initial mount. */
    useEffect(() => {
        if (!enabled) {
            return;
        }

        if (!peerIdRef.current) {
            peerIdRef.current = `sidekick-${uuidv4()}`;
            console.log(`[useWebSocket] Generated Sidekick Peer ID: ${peerIdRef.current}`);
        }
    }, [enabled]);

    /** Effect to attempt initial connection on mount and handle cleanup on unmount. */
    useEffect(() => {
        if (!enabled) {
            return;
        }

        manualDisconnect.current = false; // Ensure flag is reset on mount
        console.log("[useWebSocket] Initial connection effect triggered.");
        connect(); // Attempt initial connection

        // Cleanup function: Called when the component unmounts.
        return () => {
            console.log("[useWebSocket] Unmounting component, disconnecting...");
            disconnect(); // Perform manual disconnect and cleanup
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [enabled]); // Run when enabled changes (connect/disconnect are stable due to useCallback)

    /** Effect to reset the manual disconnect flag if the connection successfully establishes later. */
    useEffect(() => {
        if (!enabled) {
            return;
        }

        if (status === 'connected') {
            manualDisconnect.current = false;
        }
    }, [status, enabled]);

    // --- Callback Functions (Memoized) ---

    /**
     * Stable function to send messages over the WebSocket connection.
     * Handles JSON stringification and checks connection state.
     * @param message - The message object to send (should conform to SentMessage or be a generic object).
     * @param description - Optional description for logging purposes.
     */
    const sendMessage = useCallback((message: SentMessage | object, description: string = "") => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            try {
                const messageString = JSON.stringify(message);
                ws.current.send(messageString);
                const msgType = (message as any)?.type || 'unknown'; // Extract type for logging
                const desc = description ? ` (${description})` : '';
                console.log(`[useWebSocket] Sent message (type: ${msgType})${desc}:`, message);
            } catch (e) {
                console.error(`[useWebSocket] Error sending message:`, message, e);
            }
        } else {
            console.warn('[useWebSocket] Cannot send message, WebSocket is not connected or open.', { readyState: ws.current?.readyState }, message);
        }
    }, []); // No dependencies, uses refs

    /**
     * Schedules the next reconnection attempt with exponential backoff.
     * Clears any existing reconnect timer.
     */
    const scheduleReconnect = useCallback(() => {
        // Abort if manually disconnected or max attempts reached
        if (manualDisconnect.current || reconnectAttempts.current >= MAX_RECONNECT_ATTEMPTS) {
            if (!manualDisconnect.current) {
                console.error(`[useWebSocket] Max reconnect attempts (${MAX_RECONNECT_ATTEMPTS}) reached. Giving up.`);
                setStatus('disconnected'); // Ensure final status is disconnected
            }
            return;
        }

        reconnectAttempts.current += 1;

        // Calculate delay with exponential backoff, capped at MAX_RECONNECT_DELAY
        const delay = Math.min(
            MAX_RECONNECT_DELAY,
            RECONNECT_DELAY * Math.pow(RECONNECT_BACKOFF_FACTOR, reconnectAttempts.current - 1)
        );

        console.log(`[useWebSocket] Scheduling reconnect attempt ${reconnectAttempts.current} in ${delay.toFixed(0)}ms...`);

        // Clear previous timer if it exists
        if (reconnectTimeoutId.current !== null) {
            clearTimeout(reconnectTimeoutId.current);
        }

        // Schedule the connection attempt
        reconnectTimeoutId.current = window.setTimeout(() => {
            // Double-check we weren't manually disconnected while waiting
            if (!manualDisconnect.current) {
                console.log(`[useWebSocket] Attempting reconnect #${reconnectAttempts.current}...`);
                setStatus('reconnecting'); // Set status before calling connect
                connect();
            } else {
                console.log("[useWebSocket] Reconnect timer fired, but manual disconnect was requested. Aborting reconnect.");
            }
        }, delay);
    }, []); // Depends on `connect` which is defined below

    /**
     * Initiates the WebSocket connection process.
     * Sets up event listeners (onopen, onclose, onerror, onmessage).
     */
    const connect = useCallback(() => {
        // Prevent connection if already connected/connecting or manually disconnected
        if (ws.current || manualDisconnect.current) {
            console.log(`[useWebSocket] Connect aborted. Current WebSocket: ${ws.current ? 'exists' : 'null'}, ReadyState: ${ws.current?.readyState}, Manual disconnect: ${manualDisconnect.current}`);
            return;
        }

        // Clear pending reconnect timer *before* creating new socket
        if (reconnectTimeoutId.current !== null) {
            clearTimeout(reconnectTimeoutId.current);
            reconnectTimeoutId.current = null;
            console.log("[useWebSocket] Cleared pending reconnect timer before new connection attempt.");
        }

        console.log(`[useWebSocket] Attempting to connect to ${wsUrl}...`);
        setStatus('connecting'); // Update status

        // Create the new WebSocket instance
        const socket = new WebSocket(wsUrl);
        ws.current = socket; // Store reference immediately

        // --- WebSocket Event Handlers ---

        socket.onopen = () => {
            // Guard against stale connection events: Ensure this event is for the *current* socket instance.
            if (ws.current !== socket) {
                console.warn("[useWebSocket] onopen: Stale connection attempt succeeded, closing it.");
                socket.close();
                return;
            }
            console.log(`[useWebSocket] WebSocket connection established.`);
            setIsConnected(true);
            setStatus('connected');
            reconnectAttempts.current = 0; // Reset reconnect counter on success

            // Send initial "announce online" message
            if (peerIdRef.current) {
                const announceMsg: SystemAnnounceMessage = {
                    id: 0, component: "system", type: "announce",
                    payload: { peerId: peerIdRef.current, role: "sidekick", status: "online", version: __APP_VERSION__, timestamp: Date.now() }
                };
                sendMessage(announceMsg, 'announce online');
            } else {
                console.error("[useWebSocket] Cannot send announce - Peer ID not generated.");
            }
        };

        socket.onclose = (event) => {
            console.warn(`[useWebSocket] WebSocket connection closed. Code: ${event.code}, Reason: ${event.reason}, Clean: ${event.wasClean}`);
            // Only process close event if it pertains to the current WebSocket instance
            if (ws.current === socket) {
                ws.current = null; // Clear the current WebSocket reference
                setIsConnected(false);
                // Trigger reconnect only if the disconnection was not manually initiated
                if (!manualDisconnect.current) {
                    setStatus('reconnecting');
                    scheduleReconnect(); // Schedule the next attempt
                } else {
                    setStatus('disconnected'); // Stay disconnected if manual
                    console.log("[useWebSocket] Manual disconnect confirmed by onclose event.");
                }
            } else {
                console.log("[useWebSocket] onclose: Ignoring event from a stale connection.");
            }
        };

        socket.onerror = (error) => {
            console.error('[useWebSocket] WebSocket error:', error);
            // Check if the error is for the current socket instance
            if (ws.current === socket) {
                // Update status to reflect error, onclose will handle reconnect scheduling
                setStatus('reconnecting');
            } else {
                console.log("[useWebSocket] onerror: Ignoring error from a stale connection.");
            }
        };

        socket.onmessage = (event) => {
            // Ignore messages from stale connections
            if (ws.current !== socket) {
                console.warn("[useWebSocket] onmessage: Ignoring message from a stale connection.");
                return;
            }
            try {
                const message = JSON.parse(event.data);
                // Forward the parsed message to the provided callback
                onMessageCallback(message);
            } catch (e) {
                console.error('[useWebSocket] Error parsing incoming JSON message:', event.data, e);
            }
        };
        // Dependencies: onMessageCallback, sendMessage, scheduleReconnect
        // scheduleReconnect depends on connect, creating a potential cycle if not handled carefully.
        // However, since they are memoized with useCallback and depend mostly on refs or stable functions,
        // this should be safe. Listing them explicitly clarifies intent.
    }, [wsUrl, onMessageCallback, sendMessage, scheduleReconnect]);

    /**
     * Manually closes the WebSocket connection and prevents automatic reconnection.
     * Attempts to send a final "announce offline" message.
     */
    const disconnect = useCallback(() => {
        if (manualDisconnect.current) {
            console.log("[useWebSocket] Manual disconnect already in progress or completed.");
            return; // Avoid redundant actions
        }
        console.log('[useWebSocket] Manual disconnect requested.');
        manualDisconnect.current = true; // Set flag FIRST to prevent race conditions
        setStatus('disconnected'); // Update status immediately

        // Clear any pending reconnect timer
        if (reconnectTimeoutId.current !== null) {
            clearTimeout(reconnectTimeoutId.current);
            reconnectTimeoutId.current = null;
            console.log("[useWebSocket] Cleared pending reconnect on manual disconnect.");
        }

        const socketToClose = ws.current; // Capture current socket reference
        ws.current = null; // Clear the ref immediately

        if (socketToClose) {
            // Attempt best-effort offline announcement only if connected or connecting
            if (peerIdRef.current && (socketToClose.readyState === WebSocket.OPEN || socketToClose.readyState === WebSocket.CONNECTING)) {
                const announceMsg: SystemAnnounceMessage = {
                    id: 0, component: "system", type: "announce",
                    payload: { peerId: peerIdRef.current, role: "sidekick", status: "offline", version: __APP_VERSION__, timestamp: Date.now() }
                };
                // Use the captured socket reference to send, as ws.current is now null
                try {
                    // Only send if OPEN, might fail if CONNECTING
                    if (socketToClose.readyState === WebSocket.OPEN) {
                        socketToClose.send(JSON.stringify(announceMsg));
                        console.log("[useWebSocket] Sent announce offline (manual disconnect).");
                    } else {
                        console.warn("[useWebSocket] Cannot send announce offline during manual disconnect, socket not OPEN.");
                    }
                } catch (e) {
                    console.error("[useWebSocket] Failed to send announce offline on manual disconnect:", e);
                }
            }
            console.log("[useWebSocket] Closing WebSocket connection manually...");
            socketToClose.close(1000, "Client disconnected manually"); // Use normal closure code
        } else {
            console.log("[useWebSocket] No active WebSocket connection to close manually.");
        }

        // Ensure state reflects disconnection
        setIsConnected(false);
        reconnectAttempts.current = 0; // Reset attempts as we are stopping

    }, [sendMessage]); // Depends on sendMessage for announce

    // --- Return Hook API ---
    return { isConnected, status, sendMessage };
}
