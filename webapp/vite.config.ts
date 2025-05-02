// webapp/vite.config.ts

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import websocketServerPlugin from './vite-plugin-ws-server'

// Get version from package.json
const appVersion = JSON.stringify(process.env.npm_package_version || 'unknown');

// Define WebSocket server configuration
const wsHost = 'localhost';
const wsPort = 5163;
const wsUrl = JSON.stringify(`ws://${wsHost}:${wsPort}`);

// Define communication mode based on environment
// Use process.env.SCRIPT_URL if provided, otherwise default to websocket mode
const communicationMode = JSON.stringify(process.env.SCRIPT_URL ? 'script' : 'websocket');
const scriptUrl = JSON.stringify(process.env.SCRIPT_URL || '');

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    websocketServerPlugin({ host: wsHost, port: wsPort })
  ],
  define: {
    '__APP_VERSION__': appVersion,
    '__COMMUNICATION_MODE__': communicationMode,
    '__WS_URL__': wsUrl,
    '__SCRIPT_URL__': scriptUrl,
  },
  worker: {
    format: 'es' // Use ES modules format instead of IIFE for workers
  },
})
