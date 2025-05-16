# Sidekick System Architecture

## 1. Overview

This document provides a high-level technical overview of the Sidekick system architecture. It explains the main components, their responsibilities, how they interact, and the core design principles. This is intended for developers contributing to Sidekick or seeking a conceptual understanding of its structure.

Sidekick's architecture is built on the principle of **separation of concerns**. The user's programming logic (the "Hero" script using the `sidekick-py` library) communicates with the visual presentation layer (the "Sidekick" UI, typically a React WebApp). This communication is facilitated by a **`ConnectionService`** within the Python library, which in turn uses a **`CommunicationManager`** to handle the underlying transport (WebSockets for CPython, direct JavaScript calls for Pyodide).

When using WebSockets, a central server component (typically hosted within the VS Code extension) acts as a message relay.

## 2. Core Components

```mermaid
graph TD
    subgraph "Hero (User Program with sidekick-py)"
        UserScript[User Python Script]
        SidekickComponents[sidekick.Grid, sidekick.Button, etc.]
        ConnectionService[ConnectionService]
        TaskManager[core.TaskManager]
        PyodideChannel[core.PyodideCommunicationManager (Pyodide)]
        WebSocketChannel[core.WebSocketCommunicationManager (CPython)]
    end

    subgraph "Sidekick Infrastructure"
        WSServer[WebSocket Server (VS Code Extension)]
        ReactApp[Sidekick UI (React WebApp)]
    end

    UserScript --> SidekickComponents
    SidekickComponents --> ConnectionService

    ConnectionService --> TaskManager
    ConnectionService --> PyodideChannel
    ConnectionService --> WebSocketChannel

    PyodideChannel <-->|JS Bridge| ReactApp
    WebSocketChannel <-->|WebSocket + JSON| WSServer
    WSServer <--> |WebSocket + JSON| ReactApp

```

The system consists of several key parts:

1.  **Hero (User Program + `sidekick-py` Library):**
    *   **User Python Script:** The end-user's script (e.g., a `.py` file) containing the logic to be visualized or interacted with.
    *   **Sidekick Components (`sidekick.Grid`, etc.):** High-level Python classes users instantiate (e.g., `grid = sidekick.Grid(5,5)`). These components use the `ConnectionService` to send commands and register handlers.
    *   **`ConnectionService` (`sidekick.connection.ConnectionService`):** The central orchestrator within `sidekick-py`. It manages the Sidekick-specific connection lifecycle (activation, peer discovery, `global/clearAll`), queues messages, serializes/deserializes data, and dispatches incoming UI events to the correct Python component handlers. It uses a `CommunicationManager` for actual transport.
    *   **`core.TaskManager` (`sidekick.core.TaskManager`):** An abstraction for managing an asyncio event loop.
        *   In **CPython**, it runs a loop in a separate thread, allowing the main user script to be synchronous while Sidekick's communication happens asynchronously.
        *   In **Pyodide**, it uses the existing event loop provided by the Pyodide environment (typically in a Web Worker).
    *   **`core.CommunicationManager` (`sidekick.core.CommunicationManager`):** An abstraction for the raw communication channel.
        *   **`WebSocketCommunicationManager` (CPython):** Uses the `websockets` library to connect to the Sidekick WebSocket Server.
        *   **`PyodideCommunicationManager` (Pyodide):** Uses direct JavaScript function calls (via `pyodide.ffi` and `js` module) to communicate with the Sidekick UI running on the main browser thread (typically via a Web Worker bridge).

2.  **Sidekick Infrastructure (External to `sidekick-py`):**
    *   **WebSocket Server (Typically within VS Code Extension):** Acts as a message relay between `WebSocketCommunicationManager` (Hero) and the Sidekick UI (ReactApp) when not using Pyodide.
    *   **Sidekick UI (React Web Application):** The frontend (usually in a VS Code Webview or standalone page) responsible for rendering visual components, handling user interactions, and communicating back to the Hero.

## 3. Key Interaction Flows & Lifecycle

*   **Activation:**
    *   When the first Sidekick component is created or an explicit `sidekick.activate_connection()` is called, the `ConnectionService` initiates its activation sequence.
    *   This involves:
        1.  Ensuring the `TaskManager`'s loop is running.
        2.  Creating and connecting the appropriate `CommunicationManager` (WebSocket or Pyodide bridge).
        3.  Sending a "hero online" `system/announce` message.
        4.  Waiting for a "sidekick UI online" `system/announce` message from the ReactApp.
        5.  Sending a `global/clearAll` message to the UI.
        6.  Processing any queued messages.
    *   In **CPython**, `sidekick.activate_connection()` (and implicitly, the first component creation) **blocks** until this sequence is complete or fails.
    *   In **Pyodide**, activation is **non-blocking**. Messages sent during activation are queued.
*   **Command Flow (Hero -> UI):** Python components call methods (e.g., `grid.set_color()`). These generate protocol messages that `ConnectionService` sends via the `CommunicationManager` to the UI to update visual elements.
*   **Event Flow (UI -> Hero):** User interactions in the UI (e.g., button click) generate protocol messages. These are received by the `CommunicationManager`, passed to `ConnectionService`, which then deserializes and dispatches them to the appropriate Python component's registered event handler.
*   **Peer Discovery (`system/announce`):** Hero and Sidekick UI announce their presence (`online`/`offline`) to facilitate readiness checks.

## 4. High-Level Architectural Concepts

*   **Asynchronous Core:** The `sidekick.core` layer (`TaskManager`, `CommunicationManager`) is designed to be asynchronous (`async/await`).
*   **Synchronous Facade (for CPython):** `ConnectionService` and the public `sidekick` API provide a primarily synchronous and blocking interface for CPython users to simplify usage, while managing async operations internally via the `TaskManager`.
*   **Pyodide Integration:** For Pyodide, the library leverages the browser's event loop. Blocking operations are avoided, and `async` APIs like `sidekick.run_forever_async()` are provided.
*   **Communication Mechanism:**
    *   **CPython:** WebSockets (via `websockets` library) to `ws://localhost:5163` (default).
    *   **Pyodide:** JavaScript bridge (`postMessage` between Worker and Main Thread, using `js` module and `pyodide.ffi`).
    *   Messages are JSON strings. The Sidekick [Communication Protocol](./protocol.md) defines message structure.
*   **State Management & Update Mechanisms (UI):**
    *   The React WebApp maintains UI state. Details on state-driven vs. imperative updates for UI components can be found in the [WebApp Development Guide](./webapp-development.md).
*   **Modularity:** The system revolves around components (Grid, Console, etc.), each having a Python class and a corresponding React UI component, linked by type strings in the protocol.
*   **Reactivity (`ObservableValue`):** Works as before, with `Viz` subscribing to `ObservableValue` changes and `ConnectionService` sending granular updates.

## 5. Technology Stack Summary

*   **Hero Library (`sidekick-py`):**
    *   Python 3.7+
    *   `websockets` (for CPython WebSocket communication)
    *   `pyodide` (when running in Pyodide environment)
*   **Sidekick Server (VS Code Extension):** Node.js, `ws` library.
*   **Sidekick UI (WebApp):** React, TypeScript, Vite.
*   **VS Code Integration:** VS Code API.

## 6. Extensibility

*   **New Visual Components:** Requires Python class implementation, React component, and protocol definition updates.
*   **New Hero Languages:** Requires a client library adhering to the [Communication Protocol](./protocol.md) and capable of interacting with one of the supported transports.