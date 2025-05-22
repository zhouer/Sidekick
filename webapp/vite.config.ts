import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Get version from package.json
const appVersion = JSON.stringify(process.env.npm_package_version || 'unknown');

// Define communication mode based on environment
// Use process.env.SCRIPT_URL if provided, otherwise default to websocket mode
const communicationMode = JSON.stringify(process.env.SCRIPT_URL ? 'script' : 'websocket');
const scriptUrl = JSON.stringify(process.env.SCRIPT_URL || '');
// const communicationMode = JSON.stringify('script');
// const scriptUrl = JSON.stringify('/test.py');

export default defineConfig(({ mode }) => {
  let wsUrl;
  const plugins = [react()];
  let wsHost, wsPort;

  if (mode === 'development') {
    // Dynamically import for development only
    const websocketServerPlugin = require('./vite-plugin-ws-server').default;
    wsHost = 'localhost';
    wsPort = 5163;
    wsUrl = JSON.stringify(`ws://${wsHost}:${wsPort}`);
    plugins.push(websocketServerPlugin({ host: wsHost, port: wsPort }));
  } else {
    wsUrl = JSON.stringify('wss://ws-sidekick.zhouer.workers.dev');
  }

  return {
    plugins,
    define: {
      '__APP_VERSION__': appVersion,
      '__COMMUNICATION_MODE__': communicationMode,
      '__WS_URL__': wsUrl,
      '__SCRIPT_URL__': scriptUrl,
    },
    server: {
      headers: {
        'Cross-Origin-Opener-Policy': 'same-origin',
        'Cross-Origin-Embedder-Policy': 'require-corp',
      },
    },
  };
})
