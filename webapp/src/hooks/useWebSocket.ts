// Sidekick/webapp/src/hooks/useWebSocket.ts
import { useState, useEffect, useRef, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { AnnouncePayload, SentMessage, SystemAnnounceMessageToSend } from '../types';

// Use the URL injected by Vite's define config
// Fallback needed only if run outside Vite build context (e.g., tests)
const WS_URL = (typeof __WS_URL__ !== 'undefined') ? __WS_URL__ : 'ws://localhost:5163';

export function useWebSocket(onMessage: (message: any) => void) {
    const [isConnected, setIsConnected] = useState<boolean>(false);
    const webSocketRef = useRef<WebSocket | null>(null);
    const peerIdRef = useRef<string | null>(null);
    const onMessageRef = useRef(onMessage);

    useEffect(() => {
        onMessageRef.current = onMessage;
    }, [onMessage]);

    useEffect(() => {
        if (!peerIdRef.current) {
            peerIdRef.current = `sidekick-${uuidv4()}`;
            console.log(`[useWebSocket] Generated Sidekick Peer ID: ${peerIdRef.current}`);
        }
    }, []);

    // --- Refactored sendAnnounce to be internal ---
    const internalSendMessage = useCallback((message: object) => {
        if (!webSocketRef.current || webSocketRef.current.readyState !== WebSocket.OPEN) {
            console.warn(`[useWebSocket] Cannot send message, WebSocket not open. State: ${webSocketRef.current?.readyState}`);
            return false; // Indicate send failure
        }
        try {
            const messageString = JSON.stringify(message);
            webSocketRef.current.send(messageString);
            return true; // Indicate send success
        } catch (error) {
            console.error("[useWebSocket] Failed to stringify or send message:", message, error);
            return false; // Indicate send failure
        }
    }, []); // No dependencies, uses refs

    const sendAnnounce = useCallback((status: AnnouncePayload['status']) => {
        if (!peerIdRef.current) {
            console.error("[useWebSocket] Cannot send announce, peerId not generated.");
            return;
        }
        const payload: AnnouncePayload = {
            peerId: peerIdRef.current,
            role: "sidekick", status: status, version: __APP_VERSION__, timestamp: Date.now()
        };
        const message: SystemAnnounceMessageToSend = { id: 0, module: "system", method: "announce", payload: payload };
        if (internalSendMessage(message)) {
            console.log(`[useWebSocket] Sent announce: ${status}`);
        }
    }, [internalSendMessage]); // Depends on stable internalSendMessage

    // --- Connection useEffect ---
    useEffect(() => {
        // If a WebSocket connection already exists, don't create a new one
        // (This check helps prevent duplicates if cleanup is somehow delayed)
        if (webSocketRef.current) {
            console.warn('[useWebSocket] Connection attempt skipped, WebSocket ref already exists.');
            return;
        }

        console.log('[useWebSocket] useEffect: Attempting to connect...');
        const ws = new WebSocket(WS_URL);
        webSocketRef.current = ws; // Assign immediately

        ws.onopen = () => {
            console.log('[useWebSocket] WebSocket connection established.');
            setIsConnected(true);
            sendAnnounce("online");
        };

        ws.onmessage = (event) => {
            console.debug('[useWebSocket] Raw message received:', event.data);
            try {
                const messageData = JSON.parse(event.data);
                onMessageRef.current(messageData);
            } catch (error) {
                console.error('[useWebSocket] Failed to parse incoming message:', event.data, error);
            }
        };

        ws.onerror = (error) => {
            console.error('[useWebSocket] WebSocket error:', error);
            // Error often precedes close, let onclose handle state update
        };

        ws.onclose = (event) => {
            // Check ref *before* logging to avoid logging closure of an old instance
            if (webSocketRef.current === ws) {
                console.log(`[useWebSocket] WebSocket connection closed. Code: ${event.code}, Reason: ${event.reason || 'No reason given'}`);
                setIsConnected(false);
                webSocketRef.current = null; // Clear the ref *here*
            } else {
                console.log(`[useWebSocket] Close event received for an old/mismatched WebSocket instance.`);
            }
        };

        // --- Cleanup function ---
        return () => {
            console.log('[useWebSocket] useEffect: Cleanup running...');
            const wsToClose = webSocketRef.current; // Capture ref at cleanup time
            webSocketRef.current = null; // **Crucially, clear the ref immediately**
            setIsConnected(false); // Update state immediately

            if (wsToClose) {
                console.log('[useWebSocket] useEffect: Closing WebSocket connection...');
                wsToClose.onopen = null; // Remove handlers to prevent calls after cleanup
                wsToClose.onmessage = null;
                wsToClose.onerror = null;
                wsToClose.onclose = null; // Especially important!
                if (wsToClose.readyState === WebSocket.OPEN || wsToClose.readyState === WebSocket.CONNECTING) {
                    wsToClose.close(1000, "Client cleanup"); // Close with normal code
                }
            } else {
                console.log('[useWebSocket] useEffect: Cleanup - No active WebSocket instance to close.');
            }
        };
        // }, [sendAnnounce]); // Keep dependency as sendAnnounce is stable due to useCallback([])
    }, [sendAnnounce, internalSendMessage]); // Include internalSendMessage as well, though it's also stable

    // Public sendMessage function (no change needed here)
    const sendMessage = useCallback((message: SentMessage) => {
        internalSendMessage(message);
    }, [internalSendMessage]);

    return { isConnected, sendMessage };
}