import { useState, useEffect, useRef, useCallback } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { SentMessage, SystemAnnounceMessage } from '../types';

type WorkerMessage = {
  type: 'init' | 'run' | 'stop';
  scriptUrl: string;
};

// Pyodide execution status
export type PyodideStatus = 'initializing' | 'ready' | 'running' | 'stopping' | 'stopped' | 'error' | 'terminated';

// Worker response types
type WorkerStatusResponse = {
  type: PyodideStatus;
  error?: string;
};

type WorkerSidekickResponse = {
  type: 'sidekick';
  data: any;
};

type WorkerResponse = WorkerStatusResponse | WorkerSidekickResponse;

// Hook options
interface UsePyodideOptions {
  enabled: boolean;
  scriptPath: string;
}

/**
 * Custom React hook to manage Pyodide execution in a web worker.
 * 
 * @param onMessageCallback - Callback function to handle messages from the Python script
 * @param options - Configuration options for the hook
 * @returns Object containing Pyodide state and control methods
 */
export function usePyodide(
  onMessageCallback: (message: any) => void,
  options: UsePyodideOptions
) {
  // State
  const [status, setStatus] = useState<PyodideStatus>('initializing');
  const [error, setError] = useState<string | null>(null);
  const [scriptUrl, setScriptUrl] = useState<string | null>(null);

  // Refs
  const workerRef = useRef<Worker | null>(null);
  const peerIdRef = useRef<string | null>(null);
  const pendingRunRef = useRef<boolean>(false);
  const offlineReceivedRef = useRef<boolean>(false);

  // Generate a unique peer ID for this client instance
  useEffect(() => {
    if (!peerIdRef.current) {
      peerIdRef.current = `sidekick-${uuidv4()}`;
      console.log(`[usePyodide] Generated Sidekick Peer ID: ${peerIdRef.current}`);
    }
  }, []);

  // Send a message to the Python script
  const sendMessage = useCallback((message: SentMessage | object, description: string = "") => {
    if (!workerRef.current) {
      console.warn('[usePyodide] Cannot send message, worker is not ready.', message);
      return;
    }

    try {
      workerRef.current.postMessage({
        type: 'sidekick',
        message
      });
      const msgType = (message as any)?.type || 'unknown';
      const desc = description ? ` (${description})` : '';
      console.log(`[usePyodide] Sent message (type: ${msgType})${desc}:`, message);
    } catch (e) {
      console.error(`[usePyodide] Error sending message:`, message, e);
    }
  }, []);

  // Send announcement message (online/offline) to the Python script
  const sendAnnounceMessage = useCallback((status: 'online' | 'offline') => {
    if (peerIdRef.current) {
      const announceMsg: SystemAnnounceMessage = {
        id: 0, module: "system", type: "announce",
        payload: { peerId: peerIdRef.current, role: "sidekick", status, version: __APP_VERSION__, timestamp: Date.now() }
      };
      sendMessage(announceMsg, `announce ${status}`);
    }
  }, [sendMessage]);

  // Initialize the worker
  const initializeWorker = useCallback(() => {
    console.log('[usePyodide] Initializing worker');

    // Clean up any existing worker before creating a new one
    if (workerRef.current) {
      console.log('[usePyodide] Terminating existing worker before initializing a new one');
      workerRef.current.terminate();
      workerRef.current = null;
    }

    setStatus('initializing');
    setError(null);

    // Create a new worker
    const worker = new Worker(new URL('../workers/pyodideWorker.js', import.meta.url), { type: 'module' });
    workerRef.current = worker;

    // Handle messages from the worker
    worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
      const response = event.data;

      if (response.type === 'ready') {
        setStatus(response.type);

        if (pendingRunRef.current) {
          pendingRunRef.current = false;
          if (workerRef.current) {
            console.log('[usePyodide] Running script');
            workerRef.current.postMessage({ type: 'run' });
          }
        }
      } else if (response.type === 'running') {
        setStatus(response.type);

        sendAnnounceMessage('online');
      } else if (response.type === 'terminated' || response.type === 'stopped' || response.type === 'error') {
        setStatus(response.type);

        if (response.error) {
          setError(response.error);
        }

        if (!offlineReceivedRef.current) {
          onMessageCallback({'id': 0, 'module': 'system', 'type': 'announce', 'payload': {'role': 'hero', 'status': 'offline'}});
        }

        if (workerRef.current) {
          console.log('[usePyodide] Clearing worker reference');
          workerRef.current.terminate();
          workerRef.current = null;
        }
      } else if (response.type === 'sidekick') {
        const msg: any = response.data;
        if (msg.type === 'announce' && msg.payload.status === 'offline') {
          offlineReceivedRef.current = true;
        }

        onMessageCallback(response.data);
      } else {
        console.warn('[usePyodide] Unknown message type:', response);
      }
    };

    // Handle worker errors
    worker.onerror = (event) => {
      if (event.message.includes('KeyboardInterrupt')) {
        console.log('[usePyodide] Worker interrupted by user');
        return;
      }

      console.error('[usePyodide] Worker error:', event);
      setStatus('error');
      setError('Worker error: ' + event.message);
    };

    // Initialize the worker with the script path
    if (scriptUrl) {
      worker.postMessage({
        type: 'init',
        scriptPath: scriptUrl
      });
    }

    return worker;
  }, [scriptUrl, onMessageCallback, sendAnnounceMessage]);

  // Initialize Pyodide when enabled
  useEffect(() => {
    if (!options.enabled || !options.scriptPath) {
      return;
    }

    console.log(`[usePyodide] Initializing with script: ${options.scriptPath}`);
    setScriptUrl(options.scriptPath);

    // Initialize the worker
    initializeWorker();

    // Cleanup function
    return () => {
      console.log('[usePyodide] Cleaning up worker');
      if (workerRef.current) {
        workerRef.current.terminate();
        workerRef.current = null;
      }
    };
  }, [options.enabled, options.scriptPath, initializeWorker]);

  // Run the Python script
  const runScript = useCallback(() => {
    if (status === 'stopped' || status === 'error' || status === 'terminated') {
      console.log(`[usePyodide] Worker is in ${status} state, reinitializing before running script`);
      pendingRunRef.current = true;
      initializeWorker();
      return;
    }

    if (!workerRef.current || status !== 'ready') {
      console.warn(`[usePyodide] Cannot run script, worker is not ready. Current status: ${status}`);
      return;
    }

    console.log('[usePyodide] Running script');
    workerRef.current.postMessage({ type: 'run' });
  }, [status, initializeWorker]);

  // Stop the Python script
  const stopScript = useCallback(() => {
    if (!workerRef.current) {
      console.warn('[usePyodide] Cannot stop script, worker is not available');
      return;
    }

    console.log('[usePyodide] Stopping script');
    setStatus('stopping');
    sendAnnounceMessage('offline');
    workerRef.current.postMessage({ type: 'stop' });
  }, [sendAnnounceMessage]);

  return {
    status,
    error,
    sendMessage,
    runScript,
    stopScript
  };
}
