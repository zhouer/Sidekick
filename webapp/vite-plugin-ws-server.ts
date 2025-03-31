// webapp/vite-plugin-ws-server.ts
import type { Plugin } from 'vite'
import { WebSocketServer, WebSocket } from 'ws'

export default function websocketServerPlugin(): Plugin {
    let started = false

    return {
        name: 'vite-plugin-ws-server',
        configureServer() {
            if (started) return
            started = true

            const PORT = 5163
            const wss = new WebSocketServer({ port: PORT })

            wss.on('connection', (ws: WebSocket) => {
                console.log('New client connected.')

                ws.on('message', (data) => {
                    let msg
                    try {
                        msg = JSON.parse(data.toString())
                        console.log('Received:', msg)
                    } catch (e) {
                        console.error('Invalid JSON:', e)
                        return
                    }

                    wss.clients.forEach((client) => {
                        if (client !== ws && client.readyState === WebSocket.OPEN) {
                            client.send(JSON.stringify(msg))
                        }
                    })
                })

                ws.on('close', () => {
                    console.log('Client disconnected.')
                })
            })

            console.log(`WebSocket server is listening on ws://localhost:${PORT}`)
        }
    }
}
