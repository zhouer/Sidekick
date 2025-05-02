import { useState, useEffect, useCallback } from 'react';
import { useWebSocket } from './useWebSocket';
import { usePyodide } from './usePyodide';
import { SentMessage } from '../types';

// Communication mode types
export type CommunicationMode = 'websocket' | 'script';

// Common status interface for both communication methods
export type CommunicationStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 
                                 'initializing' | 'ready' | 'running' | 'stopping' | 'stopped' | 'error' | 'terminated';

/**
 * Custom hook that provides a unified interface for communication,
 * abstracting over WebSocket and Pyodide script modes.
 * 
 * @param onMessageCallback - Callback function to handle incoming messages
 * @returns Object containing communication state and methods
 */
export function useCommunication(onMessageCallback: (message: any) => void) {
  // Determine communication mode from Vite defined constants
  const [mode, setMode] = useState<CommunicationMode>(__COMMUNICATION_MODE__ as CommunicationMode);
  const scriptUrl = __SCRIPT_URL__ || '';

  // Use the appropriate communication hook based on mode
  const {
    isConnected: wsIsConnected,
    status: wsStatus,
    sendMessage: wsSendMessage
  } = useWebSocket(onMessageCallback, { enabled: mode === 'websocket' });

  const {
    status: pyodideStatus,
    sendMessage: pyodideSendMessage,
    runScript,
    stopScript
  } = usePyodide(onMessageCallback, { enabled: mode === 'script', scriptPath: scriptUrl });

  // Unified status and connection state
  const isConnected = mode === 'websocket' ? wsIsConnected : false;
  const status: CommunicationStatus = mode === 'websocket' ? wsStatus : pyodideStatus;

  // Unified send message function
  const sendMessage = useCallback((message: SentMessage | object, description?: string) => {
    if (mode === 'websocket') {
      wsSendMessage(message, description);
    } else {
      pyodideSendMessage(message, description);
    }
  }, [mode, wsSendMessage, pyodideSendMessage]);

  return {
    mode,
    isConnected,
    status,
    sendMessage,
    runScript: mode === 'script' ? runScript : undefined,
    stopScript: mode === 'script' ? stopScript : undefined
  };
}