// webapp/vite.config.ts

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import websocketServerPlugin from './vite-plugin-ws-server'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    websocketServerPlugin()
  ],
})
