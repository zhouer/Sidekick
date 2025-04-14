# Sidekick Web Application Development Guide

## 1. Overview

This document details the architecture and implementation of the Sidekick frontend React application, typically run within a VS Code Webview. It's intended for developers contributing to or extending the web application.

The WebApp's primary responsibilities are:
1.  Manage WebSocket connection to the Sidekick server.
2.  Receive command messages (`spawn`, `update`, `remove`) from the Hero (via server).
3.  Maintain UI state (`modulesById`, `moduleOrder`) using a reducer (`rootReducer`).
4.  Dynamically render visual modules based on received commands and current state, using definitions from `moduleRegistry`.
5.  Handle user interactions within modules and send corresponding event/error messages back to the Hero (via server).
6.  Adhere strictly to the [Sidekick Communication Protocol](./protocol.md), specifically regarding **handling and sending `camelCase` payloads**.

## 2. Tech Stack

*   **Framework:** React (v18+, functional components, hooks)
*   **Language:** TypeScript
*   **State Management:** React `useReducer` (centralized `AppState` in `App.tsx`), module logic delegated to pure functions (`getInitialState`, `updateState`). Immer may be used within `updateState` for immutability.
*   **Build Tool:** Vite
*   **WebSocket:** Native browser API via `useWebSocket` hook.
*   **Styling:** CSS (global `App.css`, per-module `.css`).

## 3. Project Structure

```
webapp/
├── public/
├── src/
│   ├── hooks/
│   │   └── useWebSocket.ts # Manages WebSocket connection & lifecycle
│   ├── modules/
│   │   ├── {moduleName}/   # Directory for each visual module
│   │   │   ├── *Component.tsx # React component (UI)
│   │   │   ├── *Logic.ts      # State logic (getInitialState, updateState)
│   │   │   ├── types.ts       # Module-specific TS types (State, Payloads)
│   │   │   └── *Component.css # Styles
│   │   └── moduleRegistry.ts # Maps module type string -> ModuleDefinition
│   ├── types/
│   │   └── index.ts        # Shared types (Messages, ModuleInstance, ModuleDefinition)
│   ├── App.css             # Global styles
│   ├── App.tsx             # Root component, reducer, main layout
│   ├── index.css
│   └── main.tsx            # Entry point
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## 4. Core Implementation Details

### 4.1. WebSocket Communication (`useWebSocket` Hook)

*   Encapsulates connection (`ws://localhost:5163`), state (`isConnected`, `status`), reconnection logic (backoff, max attempts), message parsing/sending (JSON).
*   Sends `system/announce` (`role: "sidekick"`, `status: "online"/"offline"`).
*   Used by `App.tsx` to receive messages (passed to reducer) and send messages (via `handleModuleInteraction`).

### 4.2. State Management (`App.tsx` - `useReducer`, `rootReducer`)

*   **`AppState`:** Central state (`modulesById`: `Map<string, ModuleInstance>`, `moduleOrder`: `string[]`, `heroStatus`: `HeroPeerInfo | null`).
*   **`rootReducer`:** Handles `AppAction` types (`PROCESS_MESSAGE`, `CLEAR_ALL_MODULES`).
    *   **Message Processing:**
        *   Parses incoming `ReceivedMessage`.
        *   Handles `system/announce` to update `heroStatus`.
        *   Handles `global/clearAll`.
        *   For `spawn`, `update`, `remove`: uses `moduleRegistry` to find the correct `ModuleDefinition`.
    *   **Module Logic Delegation:**
        *   `spawn`: Calls `moduleDefinition.getInitialState(target, payload)`. Adds new `ModuleInstance` to `modulesById` and `moduleOrder`.
        *   `update`: Calls **pure** `moduleDefinition.updateState(currentState, payload)`. Updates instance in `modulesById` **only if** a new state object reference is returned.
        *   `remove`: Deletes from `modulesById`, filters `moduleOrder`.
    *   **Immutability:** `rootReducer` ensures top-level state updates are immutable. Module-specific `updateState` functions are responsible for their own state immutability (e.g., using Immer or object spread).

### 4.3. Module System (`ModuleDefinition`, `moduleRegistry`)

*   **`ModuleDefinition` (`src/types/index.ts`):** Interface defining the contract for a module: `type` (string), `component` (React FC), `getInitialState` (function), `updateState` (pure function), `displayName?` (string).
*   **`moduleRegistry` (`src/modules/moduleRegistry.ts`):** A `Map` associating module type strings (e.g., `"grid"`) with their `ModuleDefinition` objects. Used by `rootReducer` and `App.tsx` rendering logic.

### 4.4. Module Implementation Pattern (`src/modules/{moduleName}/`)

*   **`*Component.tsx`:** React component receiving `id`, `state`, `onInteraction` props. Renders UI based on `state`. Manages local UI state if needed (e.g., input field value). Calls `onInteraction(message)` to send `event` or `error` messages back to Hero.
*   **`*Logic.ts`:** Contains:
    *   `getInitialState(instanceId, payload)`: **Must validate** the received `spawn` payload (checking required fields and structure). Throws error on invalid payload. Returns the initial state object.
    *   `updateState(currentState, payload)`: **Must be a pure function.** Calculates next state based on `update` payload. Handles immutability (returns new object reference only if state changed).
*   **`types.ts`:** Defines module-specific TypeScript types (e.g., `GridState`, `GridSpawnPayload`). Payload interfaces reflect the **`camelCase`** structure defined in `protocol.md`.
*   **`*Component.css`:** Module-specific styles.

### 4.5. Protocol Compliance: Handling `camelCase` Payloads

*   **Receiving:** The `rootReducer` passes the raw `payload` object (which is expected to have `camelCase` keys per the protocol) to the appropriate `getInitialState` or `updateState` function in `*Logic.ts`. These logic functions are responsible for reading the `camelCase` keys.
*   **Sending:** When a `*Component.tsx` calls `onInteraction`, it **must construct** the `SentMessage` (typically `ModuleEventMessage` or `ModuleErrorMessage`) with a `payload` object that uses **`camelCase` keys** and adheres to the structure defined in `protocol.md`.

## 5. Development Setup

1.  `cd Sidekick/webapp`
2.  `npm install`
3.  `npm run dev` (Starts Vite dev server and the WebSocket relay server via `vite-plugin-ws-server.ts`)
4.  Ensure Hero script connects to the correct WebSocket URL (`ws://localhost:5163` by default).

## 6. Build Process

*   `npm run build`: Creates optimized static assets in `webapp/dist/`. These files are intended to be served by the VS Code extension's Webview.

## 7. Styling

*   Global styles: `src/index.css`, `src/App.css`.
*   Module-specific styles: Co-located `.css` files (e.g., `src/modules/grid/GridComponent.css`).

## 8. Troubleshooting

*   **WebSocket Issues:** Check Hero logs, browser DevTools (Network -> WS, Console -> `[useWebSocket]`), URL matching, firewall. Check status indicators in Sidekick UI header.
*   **UI Not Updating / Incorrect State:** Use browser DevTools (Network -> WS) to inspect **incoming message payloads** - verify `module`, `type`, `target`, and that the **payload keys are `camelCase`**. Check browser console for errors from `rootReducer` or `*Logic.ts` (especially payload validation errors in `getInitialState`). Ensure `updateState` maintains immutability. Use React DevTools to inspect `AppState` and component props.
*   **Module Not Appearing:** Check `spawn` message reception and payload correctness. Check `moduleRegistry` for the type string. Check `moduleOrder` in React DevTools.
*   **Interaction Not Working:** Use `console.log` in component event handlers. Verify `onInteraction` is called with a valid `SentMessage` structure (including `module`, `type`, `src`, and a **`camelCase` payload** with the correct `event` name like `"click"` or `"inputText"`). Check Hero logs for event reception.