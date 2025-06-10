import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Get version from package.json
const appVersion = JSON.stringify(process.env.npm_package_version || 'unknown');

export default defineConfig(({ mode }) => {
  let wsHost, wsPort, wsUrl;
  let scriptUrl;
  let plugins = [react()];
  let headers: Record<string, string> = {};

  if (mode === 'development' || mode === 'vscode') {
    wsHost = 'localhost';
    wsPort = 5163;
    wsUrl = JSON.stringify(`ws://${wsHost}:${wsPort}`);
    scriptUrl = JSON.stringify('http://localhost:5173');
  } else {
    wsUrl = JSON.stringify('wss://ws-sidekick.zhouer.workers.dev');
    scriptUrl = JSON.stringify('https://script-sidekick.zhouer.workers.dev');
  }

  if (mode === 'development') {
    const websocketServerPlugin = require('./vite-plugin-ws-server').default;
    plugins.push(websocketServerPlugin({ host: wsHost, port: wsPort }));
  }

  if (mode !== 'vscode') {
    // CORS headers are needed for SharedArrayBuffer used in Pyodide
    headers['Cross-Origin-Opener-Policy'] = 'same-origin';
    headers['Cross-Origin-Embedder-Policy'] = 'require-corp';
  }

  return {
    plugins,
    define: {
      '__APP_VERSION__': appVersion,
      '__WS_URL__': wsUrl,
      '__SCRIPT_URL__': scriptUrl,
    },
    server: {
      headers: headers,
    },
  };
})
