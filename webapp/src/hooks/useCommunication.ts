import { useCallback } from 'react';
import { useWebSocket } from './useWebSocket';
import { usePyodide } from './usePyodide';
import { SentMessage } from '../types';

// Communication mode types
export type CommunicationMode = 'websocket' | 'script';

// Common status interface for both communication methods
export type CommunicationStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting' | 
                                 'initializing' | 'ready' | 'running' | 'stopping' | 'stopped' | 'error' | 'terminated';

// Get communication configuration based on URL path
export const getCommunicationConfig = (): {
  mode: CommunicationMode;
  wsUrl: string;
  scriptUrl: string;
} => {
  const pathname = window.location.pathname;
  const baseWsUrl = __WS_URL__;
  const baseScriptUrl = __SCRIPT_URL__;

  // Default to websocket mode
  let mode: CommunicationMode = 'websocket';
  let wsUrl = baseWsUrl;
  let scriptUrl = baseScriptUrl;

  // regex pattern to match both session and script paths
  const pathRegex = /\/(session|script)\/([^/]+)/;
  const match = pathname.match(pathRegex);

  if (match) {
    const pathType = match[1];
    const id = match[2];

    if (pathType === 'session') {
      mode = 'websocket';
      const url = new URL(baseWsUrl);
      url.searchParams.append('session', id);
      wsUrl = url.toString();
    } else if (pathType === 'script') {
      mode = 'script';
      const url = new URL(baseScriptUrl);
      url.pathname += id;
      scriptUrl = url.toString();
    }
  }

  return { mode, wsUrl, scriptUrl };
};

/**
 * Custom hook that provides a unified interface for communication,
 * abstracting over WebSocket and Pyodide script modes.
 * 
 * @param onMessageCallback - Callback function to handle incoming messages
 * @returns Object containing communication state and methods
 */
export function useCommunication(onMessageCallback: (message: any) => void) {
  // Get communication configuration based on URL path
  const { mode, wsUrl, scriptUrl } = getCommunicationConfig();

  // Use the appropriate communication hook based on mode
  const {
    isConnected: wsIsConnected,
    status: wsStatus,
    sendMessage: wsSendMessage
  } = useWebSocket(onMessageCallback, wsUrl, mode === 'websocket');

  const {
    status: pyodideStatus,
    sendMessage: pyodideSendMessage,
    runScript,
    stopScript
  } = usePyodide(onMessageCallback, scriptUrl, mode === 'script');

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
