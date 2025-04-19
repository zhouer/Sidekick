# Sidekick Web Application Development Guide

## 1. Overview

This document details the architecture and implementation of the Sidekick frontend React application, typically run within a VS Code Webview. It's intended for developers contributing to or extending the web application.

The WebApp's primary responsibilities are:
1.  Manage WebSocket connection to the Sidekick server.
2.  Receive command messages (`spawn`, `update`, `remove`) from the Hero (via server).
3.  Maintain UI state for most modules (`modulesById`, `moduleOrder`) using a reducer (`rootReducer`).
4.  Dynamically render visual modules based on received commands and current state, using definitions from `moduleRegistry`.
5.  Handle high-frequency `update` commands for specific modules (like Canvas) via imperative calls**, bypassing the reducer for performance.
6.  Handle user interactions within modules and send corresponding event/error messages back to the Hero (via server).

## 2. Tech Stack

*   **Framework:** React (v18+, functional components, hooks)
*   **Language:** TypeScript
*   **State Management:**
    *   React `useReducer` (centralized `AppState` in `App.tsx`) for module lifecycle (`spawn`/`remove`) and state-driven updates.
    *   `React.forwardRef` and `useImperativeHandle` for direct, performant updates on designated modules (e.g., Canvas).
*   **Build Tool:** Vite
*   **WebSocket:** Native browser API via `useWebSocket` hook.
*   **Styling:** CSS (global `App.css`, per-module `.css`).
*   **Canvas Drawing:** Native HTML Canvas 2D API, `OffscreenCanvas` (with fallback).

## 3. Project Structure

```
webapp/
├── public/
├── src/
│   ├── hooks/
│   │   └── useWebSocket.ts # Manages WebSocket connection & lifecycle
│   ├── modules/
│   │   ├── {moduleName}/   # Directory for each visual module
│   │   │   ├── *Component.tsx # React component (UI), potentially using forwardRef/useImperativeHandle
│   │   │   ├── *Logic.ts      # State logic (getInitialState, updateState - used for non-imperative)
│   │   │   ├── types.ts       # Module-specific TS types (State, Payloads)
│   │   │   └── *Component.css # Styles
│   │   └── moduleRegistry.ts # Maps module type string -> ModuleDefinition
│   ├── types/
│   │   └── index.ts        # Shared types (Messages, ModuleInstance, ModuleDefinition, ModuleHandle)
│   ├── App.css             # Global styles
│   ├── App.tsx             # Root component, reducer, main layout, imperative call routing
│   ├── index.css
│   └── main.tsx            # Entry point
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## 4. Core Implementation Details

### 4.1. WebSocket Communication (`useWebSocket` Hook)

*   Encapsulates connection (`ws://localhost:5163` by default), state (`isConnected`, `status`), reconnection logic.
*   Sends `system/announce` (`role: "sidekick"`, `status: "online"/"offline"`).
*   Used by `App.tsx` to receive messages (passed to `handleWebSocketMessage`) and send messages (via `handleModuleInteraction`).

### 4.2. State Management & Update Routing (`App.tsx`)

*   **`AppState`:** Central state (`modulesById`: `Map<string, ModuleInstance>`, `moduleOrder`: `string[]`, `heroStatus`: `HeroPeerInfo | null`). Stores core data for all modules, but *not* high-frequency update payloads for imperative modules.
*   **`rootReducer`:** Handles `AppAction` types. Now primarily responsible for:
    *   `PROCESS_SPAWN`: Adding new module instances to state.
    *   `PROCESS_REMOVE`: Removing module instances from state.
    *   `PROCESS_STATE_UPDATE`: Applying updates via `moduleDefinition.updateState` **only for non-imperative modules**.
    *   `PROCESS_SYSTEM_ANNOUNCE`: Updating `heroStatus`.
    *   `PROCESS_GLOBAL_CLEAR`: Clearing all modules from state.
    *   `CLEAR_ALL_MODULES_UI`: Handling UI-initiated clear actions.
*   **Imperative Ref Management:**
    *   `imperativeModuleRefs` (`useRef<Map<string, React.RefObject<ModuleHandle>>>`): Stores React refs pointing to the instances of components marked with `imperativeUpdate: true`.
    *   Refs are created/retrieved during rendering and passed to the respective `ModuleComponent`.
    *   An `useEffect` hook cleans up refs for modules that are removed from `moduleOrder`.
*   **Pending Updates Queue:**
    *   `pendingImperativeUpdates` (`useRef<Map<string, any[]>>`): Temporarily stores update payloads for imperative modules that arrive *before* the component's `ModuleHandle` (specifically `processUpdate` method) is ready.
*   **`handleWebSocketMessage` (Callback for `useWebSocket`):**
    *   Acts as the central routing point for incoming messages.
    *   Parses the message.
    *   **If `message.type === 'update'`**:
        *   Checks the `moduleRegistry` to see if the target module has `imperativeUpdate: true`.
        *   **Imperative Path:**
            1.  Retrieves the corresponding `moduleRef` from `imperativeModuleRefs`.
            2.  Checks if `moduleRef.current?.processUpdate` exists and is callable.
            3.  If yes: Calls `moduleRef.current.processUpdate(message.payload)` directly.
            4.  If no (component not fully mounted/handle not exposed yet): Adds `message.payload` to the `pendingImperativeUpdates` queue for that `moduleId`.
            5.  **Does not dispatch to the reducer.**
        *   **State-Driven Path (`imperativeUpdate: false`):**
            1.  Dispatches a `PROCESS_STATE_UPDATE` action to the `rootReducer`.
    *   For other message types (`spawn`, `remove`, `system/announce`, `global/clearAll`), it dispatches the corresponding action type to the `rootReducer`.
*   **`onModuleReady` (Callback Prop):**
    *   Passed from `App` to imperative module components.
    *   Called by the imperative component (e.g., `CanvasComponent`) within its initialization `useEffect` *after* `useImperativeHandle` has run.
    *   When triggered, `App` checks the `pendingImperativeUpdates` queue for that `moduleId`. If pending updates exist and the module's `processUpdate` handle is now available, it processes the queued updates sequentially and clears the queue for that module. This resolves the race condition where updates arrive before the component is ready.

### 4.3. Module System (`ModuleDefinition`, `moduleRegistry`)

*   **`ModuleDefinition` (`src/types/index.ts`):**
    *   Interface defining the contract for a module: `type` (string), `component` (React FC using `React.forwardRef`), `getInitialState`, `updateState`, `displayName?`.
    *   **`imperativeUpdate?: boolean`**: New optional flag. If `true`, `update` messages bypass the reducer and are handled via the `ModuleHandle`.
*   **`ModuleHandle` (`src/types/index.ts`):**
    *   Interface defining the methods exposed via `useImperativeHandle` for direct calls. Currently includes:
        *   `processUpdate(payload: any): void;`
*   **`moduleRegistry` (`src/modules/moduleRegistry.ts`):** A `Map` associating module type strings (e.g., `"grid"`) with their `ModuleDefinition` objects. `App.tsx` uses this to find the correct component and determine the update mechanism (`imperativeUpdate` flag).

### 4.4. Module Implementation Pattern (`src/modules/{moduleName}/`)

*   **`*Component.tsx`:**
    *   **Standard Modules (`imperativeUpdate: false`):** Render UI based on `state` prop received from `App`. Use `onInteraction` prop to send `event`/`error` messages back. Wrapped with `React.forwardRef` but may not use `useImperativeHandle` if no direct calls are needed.
    *   **Imperative Modules (`imperativeUpdate: true`, e.g., Canvas):**
        *   Must be wrapped with `React.forwardRef<ModuleHandle, Props>`.
        *   Uses `useImperativeHandle(ref, () => ({ processUpdate }), [processUpdate])` to expose the `processUpdate` method.
        *   **`processUpdate(payload)` function:** Contains the logic to directly apply the update payload (e.g., call Canvas API drawing methods). This logic was previously likely in a `useEffect` processing a command queue.
        *   Accepts an optional `onReady(id: string)` prop and calls it in an initialization `useEffect` *after* the component is fully set up (context obtained, handle exposed) to signal readiness to `App`.
        *   Still receives `state` prop for initial setup (e.g., width, height) but does *not* rely on `state` changes for updates triggered by `update` messages.
        *   Still uses `onInteraction` prop for sending `event`/`error` messages back.
*   **`*Logic.ts`:** Contains:
    *   `getInitialState`: Always required for spawning. Validates payload, returns initial state.
    *   `updateState`: **Only used if `imperativeUpdate` is false.** Pure function to calculate next state based on update payload. For imperative modules, this function might simply return the `currentState` as it won't be called for standard updates.
*   **`types.ts`:** Module-specific TS types. For imperative modules, the `State` type likely becomes simpler (e.g., Canvas no longer needs `commandQueue`). Payload types must match the `camelCase` protocol.
*   **`*Component.css`:** Module-specific styles.

### 4.5. Canvas Module Implementation (`src/modules/canvas/`) - Example Imperative Module

*   **`CanvasComponent.tsx`:**
    *   Wrapped in `forwardRef`.
    *   Implements `useImperativeHandle` to expose `processUpdate`.
    *   `processUpdate(payload)`:
        *   Parses `payload.action` and `payload.options`.
        *   Determines the target rendering context (onscreen or offscreen) based on `options.bufferId`.
        *   Directly calls the appropriate Canvas 2D API methods (`clearRect`, `fillRect`, `stroke`, `drawImage`, etc.) on the target context.
        *   Handles buffer creation/destruction by managing internal `offscreenCanvases` and `offscreenContexts` refs.
    *   **No longer uses `useEffect` to process a `commandQueue`**. Updates are handled synchronously within `processUpdate`.
    *   Calls the `onReady(id)` prop in its initialization `useEffect`.
    *   Click handling remains the same, using `onInteraction`.
*   **`canvasLogic.ts`:**
    *   `getInitialState`: Returns state with `width`, `height`.
    *   `updateState`: Now essentially a no-op, returning `currentState`.
*   **`types.ts`:**
    *   `CanvasState`: Only contains `width`, `height`. `commandQueue` is removed.
    *   `CanvasUpdatePayload`: No longer includes `commandId`.

## 5. Development Setup

1.  `cd Sidekick/webapp`
2.  `npm install`
3.  `npm run dev` (Starts Vite dev server and the WebSocket relay server via `vite-plugin-ws-server.ts`)
4.  Ensure Hero script connects to the correct WebSocket URL (`ws://localhost:5163` by default).

## 6. Build Process

*   `npm run build`: Creates optimized static assets in `webapp/dist/`. These files are intended to be served by the VS Code extension's Webview.

## 7. Styling

*   Global styles: `src/index.css`, `src/App.css`. Uses CSS variables derived from VS Code theme variables where possible.
*   Module-specific styles: Co-located `.css` files (e.g., `src/modules/grid/GridComponent.css`).
