# Sidekick Web Application

## 1. Overview

This directory contains the frontend React application for the Sidekick Visual Coding Buddy. Its primary responsibility is to:

1.  Establish and manage a WebSocket connection to the Sidekick server (typically provided by the VS Code extension or a standalone server).
2.  Receive command messages (`type: "spawn"`, `type: "update"`, `type: "remove"`) from the "Hero" (e.g., Python script via the server) over WebSocket. It expects message `payload` keys to be in **`camelCase`**.
3.  Maintain the application state, primarily tracking active visual module instances (`modulesById`) and their rendering order (`moduleOrder`), using a centralized reducer (`rootReducer` in `App.tsx`).
4.  Use the `moduleRegistry` to find the appropriate `ModuleDefinition` for each incoming message based on the `module` type string (e.g., "grid", "console").
5.  Delegate module-specific state initialization (`getInitialState`) and update calculations (`updateState`) to the pure functions registered in the `moduleRegistry` (typically found in `src/modules/*/{moduleName}Logic.ts`). These logic functions handle the incoming **`camelCase`** payloads.
6.  Dynamically render the appropriate React component for each active module based on its type and current state, passing necessary props (`id`, `state`, `onInteraction`).
7.  Send user interaction event messages (`type: "event"`) back to the Hero via the WebSocket connection when users interact with interactive UI elements (e.g., grid clicks, button presses, text submissions). These messages **must** also use **`camelCase`** keys in their `payload`.

This web application is designed to be embedded within a VS Code Webview or run standalone.

## 2. Tech Stack

*   **Framework:** React (v18+, functional components, hooks)
*   **Language:** TypeScript
*   **State Management:** React `useReducer` hook (in `App.tsx`) for central application state (`modulesById`, `moduleOrder`). Module-specific state logic is delegated via `moduleRegistry` to pure `updateState` functions, which are responsible for ensuring immutability (potentially using tools like Immer, as seen in `vizLogic.ts`).
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
*   **Functionality:** Encapsulates establishing (`ws://localhost:5163` default) and maintaining the WebSocket connection. Manages connection state (`isConnected`), message parsing (expects JSON), sending `system/announce` messages, error handling, and provides stable `sendMessage` (sends JSON) and message receiving capabilities.
*   **Integration:** Used by `App.tsx` to receive messages (which are then forwarded to the reducer) and to send interaction or error messages back to the Hero.

### 4.2. State Management (`App.tsx` - `useReducer`, `rootReducer`)

*   **Centralized State (`AppState`):** Managed by `useReducer` in `App.tsx`. Defined in `src/types/index.ts`. Contains:
    *   `modulesById: Map<string, ModuleInstance>`: Stores all active module instances, keyed by their unique ID (`target` from Hero messages). `ModuleInstance` holds `id`, `type` (string), and `state` (module-specific).
    *   `moduleOrder: string[]`: An array storing the IDs of active modules in creation order, dictating the rendering sequence.
    *   `heroStatus: HeroPeerInfo | null`: Tracks the announced status of the connected Hero peer.
*   **Root Reducer (`rootReducer`):** Acts as a central dispatcher based on incoming message `type` (`spawn`, `update`, `remove`, `announce`, `clearAll`).
    *   **Delegation:** Uses the `moduleRegistry` to find the correct `ModuleDefinition` based on the message's `module` type string.
    *   **Spawn:** Calls the registered `getInitialState(targetId, payload)` function. This function **must** validate the **`camelCase`** spawn `payload` (checking for required fields like `numColumns`, `showInput`) and throw an error if validation fails. On success, it adds the new instance to `modulesById` and `moduleOrder`.
    *   **Update:** Retrieves the current module instance, then calls the registered **pure** `updateState(currentState, payload)` function. This function handles the **`camelCase`** update `payload`. It **must** return a *new object reference* if the state changes, otherwise return the original `currentState`. The reducer then updates the instance in `modulesById`.
    *   **Remove:** Removes the instance from `modulesById` and filters its ID from `moduleOrder`.
    *   **Immutability:** The `rootReducer` ensures top-level state (`AppState`, `modulesById`, `moduleOrder`) updates are immutable. Module-specific state immutability within `updateState` is the responsibility of the individual module logic functions (using techniques like object spread or libraries like Immer).

### 4.3. Module Definition & Registry (`ModuleDefinition`, `moduleRegistry.ts`)

*   **Contract (`ModuleDefinition`)**: Defined in `src/types/index.ts`. An interface specifying the requirements for any visual module:
    *   `type`: Unique string identifier (e.g., "grid", "console"). **Must** match the `module` field in messages.
    *   `component`: React functional component for rendering. **Always receives** `id`, `state`, and `onInteraction` props.
    *   `getInitialState`: Function `(instanceId, payload) => State` to create initial state. **Must validate the `payload`**.
    *   `updateState`: **Pure function** `(currentState, payload) => State` to calculate the next state. **Must handle immutability** (return new object on change).
    *   `displayName?`: Optional user-friendly name for tooltips.
*   **Registry (`moduleRegistry.ts`)**:
    *   **Location:** `src/modules/moduleRegistry.ts`
    *   **Functionality:** A central `Map` mapping `type` strings (e.g., "grid") to their corresponding `ModuleDefinition` objects. Built-in modules are registered statically.
    *   **Usage:** Queried by `App.tsx`'s reducer and rendering logic to dynamically handle different module types.
    *   **Extensibility:** This registry is the key point for potential future dynamic plugin loading.

### 4.4. Module Structure (`src/modules/{moduleName}/`)

*   **Co-location:** Each module resides in its own directory for better organization.
*   **Contents:**
    *   `{ModuleName}Component.tsx`: The React component responsible for the module's UI. Receives `id`, `state`, and `onInteraction` props. Manages any local UI state (like input field values) and handles user interaction events (e.g., clicks, input changes). Calls the `onInteraction` callback (if needed) to send messages back to the Hero.
    *   `{moduleName}Logic.ts`: Contains the pure `getInitialState` and `updateState` functions. Handles all module-specific state logic based on **`camelCase`** payloads received from the Hero. **Responsible for validating incoming payloads** (especially required fields in `spawn`) and **ensuring state updates are immutable**. May include internal helper functions.
    *   `types.ts`: Defines module-specific TypeScript interfaces (e.g., `GridState`, `GridSpawnPayload`, `ConsoleEventPayload`). Payload interfaces **must** reflect the expected **`camelCase`** keys and required fields. Event payload interfaces define the structure of data sent back to the Hero (e.g., `{ event: 'click', x: number, y: number }`).
    *   `{ModuleName}Component.css`: Component-specific styles, scoped using standard CSS or CSS Modules if preferred.

### 4.5. Module Components (`src/modules/*/ *Component.tsx`)

*   **General:** Functional components taking `id` (string), `state` (module-specific), and `onInteraction` (function) as props. They render the UI based solely on the provided `state`. They may manage their own internal UI state (e.g., the current text in an input field before submission).
*   **Interaction:** When user interaction occurs that needs to be reported back to the Hero (e.g., clicking a grid cell, submitting text), the component **must** call the `onInteraction` prop function.
    *   It should first check if `onInteraction` exists (as a defensive measure).
    *   It must construct a valid `ModuleEventMessage` object, including:
        *   `module`: The module type string (e.g., "grid").
        *   `type`: Set to `"event"`.
        *   `src`: The `id` prop received by the component.
        *   `payload`: An object containing event-specific details (e.g., `{ event: 'click', x: 0, y: 0 }` or `{ event: 'inputText', value: 'user text' }`). This payload **must use `camelCase` keys**.
*   **Specific Notes:**
    *   **`GridComponent.tsx`:** Renders cells based on `state.cells`, `state.numColumns`, `state.numRows`. Calls `onInteraction` on cell click with `{ event: "click", x, y }`.
    *   **`ConsoleComponent.tsx`:** Renders lines from `state.lines`. Conditionally renders an input area based on `state.showInput`. Calls `onInteraction` on input submission with `{ event: "inputText", value }`.
    *   **`ControlComponent.tsx`:** Renders dynamic controls based on `state.controls` map. Calls `onInteraction` on button click (`{ event: "click", controlId }`) or text submission (`{ event: "inputText", controlId, value }`). Manages local input field values.
    *   **`VizComponent.tsx`:** Renders complex data structures recursively based on `state.variables`. Uses `state.lastChanges` for highlighting. Typically does not call `onInteraction`.
    *   **`CanvasComponent.tsx`:** Renders to an HTML5 `<canvas>`. Processes drawing commands from `state.commandQueue` in an effect. Typically does not call `onInteraction`.

## 5. Setup & Development

1.  **Navigate:** `cd Sidekick/webapp`
2.  **Install:** `npm install` (or `yarn`)
3.  **Run Dev Server:** `npm run dev`
    *   Starts Vite's development server (e.g., `http://localhost:5173`).
    *   Also starts the simple WebSocket relay server (via `vite-plugin-ws-server.ts`) on `ws://localhost:5163` (or as configured).
4.  **Connect:** Ensure the Sidekick "Hero" (e.g., your Python script using the `sidekick` library) is running and configured to connect to the WebSocket server (default `ws://localhost:5163`).

## 6. Build Process

*   **Command:** `npm run build`
*   **Output:** Generates static files (HTML, JS, CSS) optimized for production in the `webapp/dist/` directory.
*   **Deployment:** These built files are typically served by the VS Code extension's Webview panel or packaged within a standalone application (like Electron).

## 7. Styling

*   Global base styles and CSS variables can be found in `src/index.css`.
*   Overall application layout styles are in `src/App.css`.
*   Each module component has its own co-located CSS file (e.g., `src/modules/grid/GridComponent.css`) for specific styling.

## 8. Troubleshooting

*   **WebSocket Issues:**
    *   Check the Hero (Python) script's logs for connection errors.
    *   Check the browser's Developer Tools (Network tab -> WS, and Console tab) for connection status and errors. Check the `[useWebSocket]` logs.
    *   Verify the WebSocket URL matches (default `ws://localhost:5163`).
    *   Check firewall settings.
    *   Look at the connection status indicator in the Sidekick header UI.
*   **UI Not Updating / Incorrect State:**
    *   **Check Payloads:** Use browser DevTools (Network tab -> WS) to inspect incoming messages from the Hero. Verify `module`, `type`, `target` are correct. **Crucially, check that the `payload` object and all its nested keys use `camelCase`**.
    *   **Check Spawn Payloads:** Ensure `spawn` messages contain **all required fields** defined by the module's `getInitialState` function (e.g., `numColumns`/`numRows` for Grid, `showInput` for Console). Check the browser console for errors logged during `getInitialState` validation.
    *   **Check Reducer/Logic:** Look for warnings/errors in the browser console logged by `rootReducer` or specific `*Logic.ts` files.
    *   **Check Immutability:** Ensure `updateState` functions are pure and return a *new* object reference when state changes. Using Immer helps guarantee this.
    *   **Use React DevTools:** Inspect the `App` component's state (`AppState`) and the props being passed down to individual module components (`id`, `state`, `onInteraction`).
*   **Module Not Appearing:**
    *   Verify the `spawn` message is received correctly (see payload checks above).
    *   Check that the `module` type string in the message exists as a key in `src/modules/moduleRegistry.ts`.
    *   Check `moduleOrder` in React DevTools state to see if the module ID was added.
*   **Interaction Not Working (e.g., Clicks, Input):**
    *   Verify the module component's event handler (e.g., `onClick`, `onSubmit`) is being triggered (use `console.log`).
    *   Verify the event handler calls `onInteraction`.
    *   Verify the message passed to `onInteraction` has the correct structure: `{ module, type: 'event', src, payload: { event: '...', /* other camelCase keys */ } }`. **Ensure the `payload` uses `camelCase` and the correct `event` name** (e.g., "click", "inputText").
    *   Check the Hero script's logs to see if it received the event message correctly.
*   **Console Input Not Showing:**
    *   Verify the `spawn` message payload from Python included `showInput: true`.
    *   Check the `ConsoleState` in React DevTools has `showInput: true`.
    *   Check the conditional rendering logic (`{showInput && ...}`) in `ConsoleComponent.tsx`.
*   **Grid Size Incorrect:**
    *   Verify the `spawn` message payload from Python sent the correct `numColumns` and `numRows`.
    *   Check the `GridState` in React DevTools has the correct `numColumns` and `numRows`.
    *   Check that `GridComponent.tsx` uses these state values correctly in its rendering loops.
