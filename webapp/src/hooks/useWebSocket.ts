// Sidekick/webapp/src/hooks/useWebSocket.ts
import { useState, useEffect, useRef, useCallback } from 'react';

type MessageHandler = (message: any) => void;

// 改用環境變數或設定檔來管理 URL
const WEBSOCKET_URL = 'ws://localhost:5163'; // 連接到 Node.js Server 的 WebSocket 端口

export function useWebSocket(onMessage: MessageHandler) {
    const [isConnected, setIsConnected] = useState(false);
    const ws = useRef<WebSocket | null>(null);

    const sendMessage = useCallback((message: any) => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify(message));
        } else {
            console.error('WebSocket is not connected.');
        }
    }, []);

    useEffect(() => {
        console.log(`Attempting to connect to WebSocket at ${WEBSOCKET_URL}...`);
        ws.current = new WebSocket(WEBSOCKET_URL);

        ws.current.onopen = () => {
            console.log('WebSocket Connected');
            setIsConnected(true);
        };

        ws.current.onclose = () => {
            console.log('WebSocket Disconnected');
            setIsConnected(false);
            // 可以加入重連邏輯
        };

        ws.current.onerror = (error) => {
            console.error('WebSocket Error:', error);
        };

        ws.current.onmessage = (event) => {
            try {
                const messageData = JSON.parse(event.data);
                // console.log('Message from server:', messageData);
                onMessage(messageData); // 將解析後的訊息傳遞給外部處理
            } catch (error) {
                console.error('Failed to parse message:', event.data, error);
            }
        };

        // Cleanup on component unmount
        return () => {
            ws.current?.close();
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [WEBSOCKET_URL]); // 依賴 onMessage 可能導致無限重連，需小心或移除

    return { isConnected, sendMessage };
}