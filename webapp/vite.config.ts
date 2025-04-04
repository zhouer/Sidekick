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

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    websocketServerPlugin({ host: wsHost, port: wsPort })
  ],
  define: {
    '__APP_VERSION__': appVersion,
    '__WS_URL__': wsUrl,
  },
})
