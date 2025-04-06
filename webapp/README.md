# Sidekick Web Application

## 1. Overview

This directory contains the frontend React application for the Sidekick Visual Coding Buddy. Its primary responsibility is to:

1.  Establish and manage a WebSocket connection to the Sidekick server (typically provided by the VS Code extension or a standalone server).
2.  Receive command messages (`type: "spawn"`, `type: "update"`, `type: "remove"`) from the "Hero" (Python script via the server) over WebSocket, expecting **`camelCase` keys** within the `payload`.
3.  Maintain the application state, primarily tracking active visual module instances (`modulesById`) and their rendering order (`moduleOrder`), using a centralized reducer (`rootReducer` in `App.tsx`).
4.  Use the `moduleRegistry` to find the appropriate `ModuleDefinition` for each incoming message based on the `module` type string.
5.  Delegate module-specific state initialization (`getInitialState`) and update calculations (`updateState`) to the pure functions registered in the `moduleRegistry` (typically found in `src/modules/*/{moduleName}Logic.ts`).
6.  Dynamically render the appropriate React component for each active module based on its type and current state, passing necessary props (`id`, `state`, `onInteraction?`).
7.  Send user interaction event messages (`type: "event"`) back to the Hero via the WebSocket connection when users interact with interactive UI elements (e.g., grid clicks, button presses, text submissions). These messages **MUST** also use `camelCase` keys in their `payload`.

This web application is designed to be embedded within a VS Code Webview or run standalone.

## 2. Tech Stack

*   **Framework:** React (v18+, functional components, hooks)
*   **Language:** TypeScript
*   **State Management:** React `useReducer` hook (in `App.tsx`) for central application state (`modulesById`, `moduleOrder`), delegating module-specific state calculations via `moduleRegistry`. Module logic functions (`updateState`) are responsible for immutability.
*   **Build Tool:** Vite
*   **WebSocket:** Native browser WebSocket API, managed via the `useWebSocket` custom hook.
*   **Styling:** Standard CSS (global `App.css` and per-module co-located `.css` files).

## 3. Project Structure

```
webapp/
├── public/             # Static assets
├── src/                # Source code
│   ├── hooks/          # Custom React hooks
│   │   └── useWebSocket.ts
│   ├── modules/        # Core application feature: Modules
│   │   ├── canvas/     # Example: Canvas Module directory
│   │   │   ├── CanvasComponent.css  # Component styles
│   │   │   ├── CanvasComponent.tsx  # Component UI
│   │   │   ├── canvasLogic.ts       # State initialization & update logic
│   │   │   └── types.ts             # Module-specific types (State, Payloads)
│   │   ├── console/    # Console Module directory
│   │   │   ├── ... (Component, CSS, Logic, Types)
│   │   ├── control/    # Control Module directory
│   │   │   ├── ...
│   │   ├── grid/       # Grid Module directory
│   │   │   ├── ...
│   │   ├── viz/        # Viz Module directory
│   │   │   ├── ...
│   │   └── moduleRegistry.ts # Central registry for all module definitions
│   ├── types/          # Shared application-level types
│   │   └── index.ts    # (e.g., ReceivedMessage, SentMessage, ModuleInstance, ModuleDefinition)
│   ├── App.css         # Global application styles
│   ├── App.tsx         # Root component (Reducer dispatch, Rendering loop, WS handling)
│   ├── index.css       # Base CSS
│   └── main.tsx        # Application entry point
├── index.html          # Vite HTML entry point
├── package.json        # Dependencies and scripts
├── tsconfig.json       # Main TypeScript config
├── tsconfig.node.json  # TS config for Vite/Node env
└── vite.config.ts      # Vite configuration
```

## 4. Core Concepts & Implementation Details

### 4.1. WebSocket Communication (`useWebSocket` hook)

*   **Location:** `src/hooks/useWebSocket.ts`
*   **Functionality:** Encapsulates establishing and maintaining the WebSocket connection (default `ws://localhost:5163`). Manages connection state (`isConnected`), message parsing (expects JSON), error handling, and provides a stable `sendMessage` function (sends JSON). Also handles sending `system/announce` messages.
*   **Integration:** Used by `App.tsx` to receive messages (forwarded to the reducer) and send interaction messages back to the Hero.

### 4.2. State Management (`App.tsx` - `useReducer`, `rootReducer`)

*   **Centralized State (`AppState`):** Managed by `useReducer` in `App.tsx`. Defined in `src/types/index.ts`. Contains:
    *   `modulesById: Map<string, ModuleInstance>`: Stores all active module instances, keyed by their unique ID. `ModuleInstance` holds `id`, `type` (string), and `state` (module-specific).
    *   `moduleOrder: string[]`: An array storing the IDs of active modules in creation order, dictating the rendering sequence.
*   **Root Reducer (`rootReducer`):** Acts as a central dispatcher based on incoming message `type` (`spawn`, `update`, `remove`, `announce`, `clearAll`).
    *   **Delegation:** Uses the `moduleRegistry` to find the correct `ModuleDefinition` based on the message's `module` type string.
    *   **Spawn:** Calls the registered `getInitialState(targetId, payload)` function to create the initial state. Validates required spawn payload fields (e.g., `numColumns`, `showInput`). Updates `modulesById` and `moduleOrder`.
    *   **Update:** Retrieves the current module instance, then calls the registered **pure** `updateState(currentState, payload)` function. If `updateState` returns a new object reference (indicating a change), the reducer updates the instance in `modulesById`. It relies on `updateState` to handle immutability correctly.
    *   **Remove:** Removes the instance from `modulesById` and filters its ID from `moduleOrder`.
    *   **Immutability:** The reducer ensures top-level state (`AppState`, `modulesById`, `moduleOrder`) updates are immutable. Module-specific state immutability is the responsibility of the `updateState` functions.

### 4.3. Module Definition & Registry (`ModuleDefinition`, `moduleRegistry.ts`)

*   **Contract (`ModuleDefinition`)**: Defined in `src/types/index.ts`. Interface specifying the requirements for any module:
    *   `type`: Unique string identifier (e.g., "grid", "console").
    *   `component`: React functional component for rendering. Must accept `id`, `state`, and optional `onInteraction`.
    *   `getInitialState`: Function `(instanceId, payload) => State` to create initial state.
    *   `updateState`: **Pure function** `(currentState, payload) => State` to calculate the next state. Must return a new object reference if state changes.
    *   `isInteractive?`: Optional boolean indicating if the module needs the `onInteraction` callback prop.
    *   `displayName?`: Optional user-friendly name for tooltips.
*   **Registry (`moduleRegistry.ts`)**:
    *   **Location:** `src/modules/moduleRegistry.ts`
    *   **Functionality:** A central `Map` mapping `type` strings to `ModuleDefinition` objects. Built-in modules are registered statically.
    *   **Usage:** Queried by `App.tsx`'s reducer and rendering logic.
    *   **Extensibility:** Key point for potential future dynamic plugin loading.

### 4.4. Module Structure (`src/modules/{moduleName}/`)

*   **Co-location:** Each module resides in its own directory.
*   **Contents:**
    *   `{ModuleName}Component.tsx`: React component for UI. Receives `id`, `state`, `onInteraction?`. Handles local UI state and user events. Calls `onInteraction` (if provided) with a `SentMessage` (`type: "event"`, using `camelCase` payload keys and correct event names like `inputText`).
    *   `{moduleName}Logic.ts`: Contains pure `getInitialState` and `updateState` functions. Handles module-specific state logic based on `camelCase` payloads from Hero (incl. required spawn fields). Responsible for returning new state objects on change. May include internal helpers.
    *   `types.ts`: Defines module-specific TypeScript interfaces (e.g., `GridState`, `GridUpdatePayload`, `ConsoleState`, `ConsoleNotifyPayload`). Payload interfaces should reflect `camelCase` keys and required fields (e.g., `numColumns`, `showInput`). Notify payloads define `event` names.
    *   `{ModuleName}Component.css`: Component-specific styles.

### 4.5. Module Components (`src/modules/*/ *Component.tsx`)

*   **General:** Functional components taking `id`, `state`, `onInteraction?`. Render based on `state`. Manage local UI state. Call `onInteraction` (if defined) with correctly formatted `ModuleEventMessage` (incl. `src`, `module`, `type: 'event'`, and `camelCase` `payload` with correct `event` like `inputText`).
*   **Specific Notes:**
    *   **`GridComponent.tsx`:** Renders based on `numColumns` and `numRows` from state. Sends `event` messages with `event: "click"`. Accepts optional `onInteraction`.
    *   **`ConsoleComponent.tsx`:** Conditionally renders input area based on `showInput` state. Sends `event` messages with `event: "inputText"`. Accepts optional `onInteraction`.
    *   **`ControlComponent.tsx`:** Renders dynamic controls based on `state.controls`. Sends `event` messages with `event: "click"` or `event: "inputText"`. Accepts optional `onInteraction`.
    *   **`VizComponent.tsx`:** Renders complex data recursively. Highlighting relies on `lastChanges`. Uses `observableTracked`. Not interactive (`onInteraction` not used).
    *   **`CanvasComponent.tsx`:** Renders `<canvas>`. Processes `commandQueue`. Executes drawing operations. Not interactive (`onInteraction` not used).

## 5. Setup & Development

1.  **Navigate:** `cd Sidekick/webapp`
2.  **Install:** `npm install` (or `yarn`)
3.  **Run Dev Server:** `npm run dev`
    *   Starts Vite's dev server (e.g., `http://localhost:5173`).
4.  **Connect:** Ensure the Sidekick backend (Python script or VS Code extension providing the WebSocket server at `ws://localhost:5163`) is running.

## 6. Build Process

*   **Command:** `npm run build`
*   **Output:** Static files (HTML, JS, CSS) in `webapp/dist/`.
*   **Deployment:** These files are typically served by the VS Code extension's Webview panel or packaged within an Electron app.

## 7. Styling

*   Global styles in `src/index.css` and `src/App.css`.
*   Module-specific styles co-located (e.g., `src/modules/grid/GridComponent.css`).

## 8. Adding a New Visual Module (Workflow)

1.  **Create Directory:** `src/modules/myNewModule/`.
2.  **Define Types (`types.ts`):** Create `types.ts`. Define `MyNewModuleState`, `MyNewModuleSpawnPayload` (incl. required fields), `MyNewModuleUpdatePayload`, `MyNewModuleNotifyPayload` (this is for the `event` message's payload) interfaces. Ensure payload interfaces use **`camelCase` keys**. Define correct `event` names within the notify payload type.
3.  **Implement Logic (`myNewModuleLogic.ts`):** Create `myNewModuleLogic.ts`. Implement and export:
    *   `getInitialState(instanceId, payload): MyNewModuleState` (handles `camelCase` payload, validates required fields).
    *   `updateState(currentState, payload): MyNewModuleState` (pure function, handles `camelCase` payload, returns new object on change).
4.  **Create Component (`MyNewModuleComponent.tsx`):** Create the React component. Define its props interface, making `onInteraction` optional if it's interactive. Render UI based on `props.state`. If interactive, handle events and call `props.onInteraction` (check if defined!) with a `ModuleEventMessage` containing a `camelCase` payload (matching your `MyNewModuleNotifyPayload`) and correct `event`.
5.  **Add Styles (`MyNewModuleComponent.css`):** Create and import CSS.
6.  **Register (`moduleRegistry.ts`):** Import component and logic functions. Add `registry.set('myNewModule', { type: 'myNewModule', component, getInitialState, updateState, isInteractive: true_or_false });`.
7.  **Protocol (`protocol.md`):** Document the `camelCase` payloads (including required spawn fields) and `event` message payloads (formerly notify) for your new module.
8.  **Python Lib (Optional):** Add a corresponding class in the Python library (`libs/python/src/sidekick/`) that sends the correct `camelCase` payloads (incl. required spawn fields). Update `libs/python/README.md` regarding the `on_message` callback receiving `event` messages.

## 9. Troubleshooting

*   **WebSocket Issues:** Check backend logs, browser DevTools (Network & Console), firewall, URL (`ws://localhost:5163`). Check `isConnected` state and `status` in `useWebSocket`. Look for `[useWebSocket]` logs.
*   **UI Not Updating / Incorrect State:** Verify incoming messages (Network tab) have correct `module`, `type`, `target`, and **`camelCase` `payload` keys/structure** (incl. required spawn fields like `numColumns`, `showInput`). Check console warnings/errors from `rootReducer` and specific `*Logic.ts` files (especially `getInitialState` validations). Ensure `updateState` functions are pure and return *new* object references on change. Use React DevTools to inspect component props (`id`, `state`) and `AppState`.
*   **Module Not Appearing:** Check `spawn` message is received with correct `target` and **all required payload fields** (`numColumns`, `numRows` for Grid; `showInput` for Console). Check console for errors during `getInitialState` (payload validation might fail). Check `moduleRegistry` registration. Check `moduleOrder` in React DevTools.
*   **Interaction Not Working:** Check `isInteractive` flag in `moduleRegistry`. Verify `onInteraction` is passed as a prop. Check component's event handlers call `onInteraction` (after checking it exists) with a `ModuleEventMessage` having the correct `src`, `module`, `type: 'event'`, and **`camelCase` `payload` keys/structure** with correct `event` name (e.g., `inputText`). Check Hero-side logs for received message processing.
*   **Console Input Not Showing:** Verify `ConsoleState` in React DevTools has `showInput: true`. Check `ConsoleComponent.tsx` conditional rendering logic. Ensure the `spawn` payload from Python correctly sent `showInput: true`.
*   **Grid Size Incorrect:** Verify `GridState` in React DevTools has correct `numColumns` and `numRows`. Ensure the `spawn` payload from Python sent correct values. Check `GridComponent.tsx` uses these state values in its render loops.