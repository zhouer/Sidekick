# Sidekick Server-Side Development Guide (Cloudflare)

## 1. Overview and Architecture

This document describes the structure and implementation of Sidekick's server-side components running on Cloudflare. These components primarily provide a scalable, low-latency WebSocket message relay service and host the Sidekick UI web application. Cloudflare was chosen for its global network, which helps reduce latency for both the WebSocket server and the UI, and for its Workers and Durable Objects capabilities, enabling efficient WebSocket handling.

This guide focuses primarily on the **WebSocket Server** component.

### 1.1. Cloudflare's Role in the Sidekick Architecture

*   **Optional Message Relay:** The Cloudflare WebSocket server is an optional component in the Sidekick ecosystem. It primarily serves as a message relay between the Hero (Python script) and the Sidekick UI in CPython mode, especially when the local server (e.g., built into the VS Code extension) is unavailable or when a cloud-based fallback is desired.
*   **Globally Distributed Infrastructure:** Cloudflare's global network helps reduce latency for both WebSocket server connections and the Sidekick UI, improving the experience for users worldwide.
*   Provides a scalable WebSocket relay service.
*   Offers globally distributed hosting for the Sidekick UI (via Cloudflare Pages).

### 1.2. Core Technology Choices

*   **Cloudflare Workers:** The serverless compute environment used to run the WebSocket server logic.
*   **Durable Objects:** Provide state management and isolation for WebSocket connections, ensuring each session is handled independently.
*   **Cloudflare Pages:** Used to host the Sidekick UI (React WebApp), integrating with GitHub for automated deployments.

### 1.3. Workflow Overview (WebSocket Server)

1.  A client (Hero or Sidekick UI) initiates a WebSocket connection request.
2.  The request is routed to a specific Durable Object based on the `sessionId` provided in the URL.
3.  The Durable Object instance accepts the WebSocket connection and immediately sends the list of all currently online peers to the newly connected client.
4.  The Durable Object then handles subsequent message processing and broadcasting for that session.

## 2. Durable Object: `Session` Class (`cloudflare/ws/index.js`)

Each `Session` Durable Object (DO) instance represents an isolated Sidekick communication session, responsible for managing WebSocket connections and message broadcasting among all peers within that session.

### 2.1. Responsibilities

*   Manage all WebSocket connections within a single `sessionId`.
*   Track connected clients (Hero and Sidekick UI peers) with their roles, versions, and connection timestamps.
*   Relay messages between all peers within the same `sessionId`, broadcasting each message to all other peers regardless of their role.
*   Send the current list of online peers to newly connected clients immediately upon connection.
*   Process `system/announce` messages for peer tracking and state synchronization, **emphasizing that peers should proactively send `offline` messages upon graceful disconnection.**

### 2.2. Key Properties and Methods

*   `this.state`: The Durable Object's state (though the provided example primarily uses the in-memory `this.clients` Map for session state).
*   `this.clients`: A `Map` storing `peerId -> { ws: WebSocket, role: string, version: string, timestamp }`.
*   `fetch(request)`: The entry point for the DO, handling WebSocket upgrade requests.
*   `broadcastMessage(senderPeerId, message)`: A helper function that broadcasts a message to all peers except the sender.
*   `sendPeerList()`: A helper function that sends the list of all currently online peers to a newly connected client immediately upon connection.
*   `server.addEventListener('message', callback)`: Handles incoming messages from connected clients.
    *   Parses the message (expected to be JSON).
    *   Handles `system/announce` messages:
        *   `status: 'online'`: Registers the client, and broadcasts its online status to other peers in the session.
        *   `status: 'offline'` (sent proactively by the peer): Removes the client from the clients map.
    *   Relays all messages to all other peers in the session.
*   `server.addEventListener('close', callback)`: Handles **abnormal** client disconnections (i.e., when the WebSocket connection drops without a prior `offline` announce from the peer).
    *   **Relays an `offline` message on behalf of the disconnected peer:** If a client disconnects without sending an `offline` message, the server generates and broadcasts an `offline` announce message to other peers in the session.
    *   Removes the client from `this.clients`.
*   `server.addEventListener('error', callback)`: Handles WebSocket connection errors.

### 2.3. State Management and Isolation

*   Each `sessionId` maps to a unique `Session` Durable Object instance, ensuring that messages and states for different sessions are completely isolated.
*   The `this.clients` Map within each DO instance ensures that messages are only relayed among peers belonging to the same session.

## 3. Protocol Interaction (Server Perspective)

The Cloudflare WebSocket server interacts with peers according to the Sidekick communication protocol.

### 3.1. Connection and `system/announce` Handling

*   **Initial Connection:**
    1.  When a client connects, the server immediately sends a list of all currently online peers to the newly connected client using the `sendPeerList()` function.
    2.  This happens before any messages are processed from the client.

*   **`online`:**
    1.  The server registers the new peer (`peerId`, `role`, `version`, `ws` connection, and `timestamp`) in its `clients` map for the session.
    2.  The server broadcasts the message to all other peers in the session using the `broadcastMessage()` function.

*   **`offline` (proactively sent by peer):**
    1.  The server removes the client from its `clients` map.
    2.  The server broadcasts the message to all other peers in the session using the `broadcastMessage()` function.

*   **Server-Relayed `offline` (for abnormal disconnections):**
    1.  When the server detects an unexpected WebSocket connection closure (i.e., the `close` event fires without a preceding `offline` announce from that peer), it assumes the peer has disconnected abnormally.
    2.  The server then constructs an `offline` `system/announce` message on behalf of the disconnected peer, including the peer's role and version information.
    3.  This server-generated `offline` message is broadcast to all *other remaining* peers in the session using the `broadcastMessage()` function. This is crucial because when messages are relayed through a server, one peer cannot directly detect if another peer has disconnected; the server must facilitate this notification.

### 3.2. General Message Relaying

*   For messages other than `system/announce`, the server acts as a simple relay.
*   The server broadcasts all messages to all other peers in the session, regardless of their role, using the `broadcastMessage()` function.
*   The server does not inspect the `payload` of these application-level messages.
*   The message relaying logic is implemented in a way that a message from any peer is sent to all other peers in the same session, allowing for flexible communication patterns beyond just Hero-to-Sidekick UI communication.
