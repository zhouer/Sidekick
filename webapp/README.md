# Sidekick Web Application

## 1. Overview

This directory contains the frontend React application for the Sidekick Visual Coding Buddy. Its primary responsibility is to:

1.  Establish and manage a WebSocket connection to the Sidekick server (typically provided by the VS Code extension or a standalone server).
2.  Receive command messages (`spawn`, `update`, `remove`) from the "Hero" (Python script via the server) over WebSocket, expecting **`camelCase` keys** within the `payload`.
3.  Maintain the application state, primarily tracking active visual module instances (`modulesById`) and their rendering order (`moduleOrder`), using a centralized reducer (`rootReducer` in `App.tsx`).
4.  Use the `moduleRegistry` to find the appropriate `ModuleDefinition` for each incoming message based on the `module` type string.
5.  Delegate module-specific state initialization (`getInitialState`) and update calculations (`updateState`) to the pure functions registered in the `moduleRegistry` (typically found in `src/modules/*/{moduleName}Logic.ts`).
6.  Dynamically render the appropriate React component for each active module based on its type and current state, passing necessary props (`id`, `state`, `onInteraction?`).
7.  Send user interaction event messages (`notify`) back to the Hero via the WebSocket connection when users interact with interactive UI elements (e.g., grid clicks, button presses, text submissions). These messages **MUST** also use `camelCase` keys in their `payload`.

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
│   │   └── index.ts    # (e.g., HeroMessage, SidekickMessage, ModuleInstance, ModuleDefinition)
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
*   **Functionality:** Encapsulates establishing and maintaining the WebSocket connection (default `ws://localhost:5163`). Manages connection state (`isConnected`), message parsing (expects JSON), error handling, and provides a stable `sendMessage` function (sends JSON).
*   **Integration:** Used by `App.tsx` to receive messages (forwarded to the reducer) and send interaction messages back to the Hero.

### 4.2. State Management (`App.tsx` - `useReducer`, `rootReducer`)

*   **Centralized State (`AppState`):** Managed by `useReducer` in `App.tsx`. Defined in `src/types/index.ts`. Contains:
    *   `modulesById: Map<string, ModuleInstance>`: Stores all active module instances, keyed by their unique ID. `ModuleInstance` holds `id`, `type` (string), and `state` (module-specific).
    *   `moduleOrder: string[]`: An array storing the IDs of active modules in creation order, dictating the rendering sequence.
*   **Root Reducer (`rootReducer`):** Acts as a central dispatcher based on incoming message `method` (`spawn`, `update`, `remove`).
    *   **Delegation:** Uses the `moduleRegistry` to find the correct `ModuleDefinition` based on the message's `module` type string.
    *   **Spawn:** Calls the registered `getInitialState(targetId, payload)` function to create the initial state. Updates `modulesById` and `moduleOrder`.
    *   **Update:** Retrieves the current module instance, then calls the registered **pure** `updateState(currentState, payload)` function. If `updateState` returns a new object reference (indicating a change), the reducer updates the instance in `modulesById`. It relies on `updateState` to handle immutability correctly.
    *   **Remove:** Removes the instance from `modulesById` and filters its ID from `moduleOrder`.
    *   **Immutability:** The reducer ensures top-level state (`AppState`, `modulesById`, `moduleOrder`) updates are immutable. Module-specific state immutability is the responsibility of the `updateState` functions.

### 4.3. Module Definition & Registry (`ModuleDefinition`, `moduleRegistry.ts`)

*   **Contract (`ModuleDefinition`)**: Defined in `src/types/index.ts`. Interface specifying the requirements for any module:
    *   `type`: Unique string identifier (e.g., "grid", "console").
    *   `component`: React functional component for rendering.
    *   `getInitialState`: Function `(instanceId, payload) => State` to create initial state.
    *   `updateState`: **Pure function** `(currentState, payload) => State` to calculate the next state. Must return a new object reference if state changes.
    *   `isInteractive?`: Optional boolean indicating if the module needs the `onInteraction` callback prop.
*   **Registry (`moduleRegistry.ts`)**:
    *   **Location:** `src/modules/moduleRegistry.ts`
    *   **Functionality:** A central `Map` mapping `type` strings to `ModuleDefinition` objects. Built-in modules are registered statically.
    *   **Usage:** Queried by `App.tsx`'s reducer and rendering logic.
    *   **Extensibility:** Key point for potential future dynamic plugin loading.

### 4.4. Module Structure (`src/modules/{moduleName}/`)

*   **Co-location:** Each module resides in its own directory.
*   **Contents:**
    *   `{ModuleName}Component.tsx`: React component for UI. Receives `id`, `state`, `onInteraction?`. Handles local UI state and user events. Calls `onInteraction` with `SidekickMessage` (using `camelCase` payload keys).
    *   `{moduleName}Logic.ts`: Contains pure `getInitialState` and `updateState` functions. Handles module-specific state logic based on `camelCase` payloads from Hero. Responsible for returning new state objects on change. May include internal helpers (e.g., `vizLogic.ts`'s `applyModification`).
    *   `types.ts`: Defines module-specific TypeScript interfaces (e.g., `GridState`, `GridUpdatePayload`). Payload interfaces should reflect `camelCase` keys (e.g., `controlType: "textInput"`).
    *   `{ModuleName}Component.css`: Component-specific styles.

### 4.5. Module Components (`src/modules/*/ *Component.tsx`)

*   **General:** Functional components taking `id`, `state`, `onInteraction?`. Render based on `state`. Manage local UI state. Call `onInteraction` with correctly formatted `SidekickMessage` (incl. `src`, `module`, `method`, and `camelCase` `payload`).
*   **Specific Notes:**
    *   **`VizComponent.tsx` / `RenderValue.tsx`:** Renders complex data recursively. `RenderValue` manages local expand/collapse. Highlighting relies on `lastChanges` timestamp from `VizState`. Uses `observableTracked` (camelCase). Complex state *calculation* logic (`applyModification`) resides in `vizLogic.ts`.
    *   **`CanvasComponent.tsx`:** Renders `<canvas>`. Uses `useEffect` and `useRef` to manage 2D context. Processes the `commandQueue` (containing full update payloads with `commandId`) from props exactly once per command ID using `lastProcessedCommandId`. Executes drawing operations as a side effect. The state update logic in `canvasLogic.ts` just adds commands to the queue.
    *   **`ControlComponent.tsx`:** Renders dynamic controls based on `state.controls`. Manages local input values. Reads config using `camelCase` keys (`initialValue`, `buttonText`). Renders based on `type: "button"` or `type: "textInput"`. Sends `notify` messages with `camelCase` keys in payload (`controlId`, `value?`).

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
2.  **Define Types (`types.ts`):** Create `types.ts`. Define `MyNewModuleState`, `MyNewModuleSpawnPayload`, `MyNewModuleUpdatePayload`, `MyNewModuleNotifyPayload` interfaces. Ensure payload interfaces use **`camelCase` keys**.
3.  **Implement Logic (`myNewModuleLogic.ts`):** Create `myNewModuleLogic.ts`. Implement and export:
    *   `getInitialState(instanceId, payload): MyNewModuleState` (handles `camelCase` payload).
    *   `updateState(currentState, payload): MyNewModuleState` (pure function, handles `camelCase` payload, returns new object on change).
4.  **Create Component (`MyNewModuleComponent.tsx`):** Create the React component. Render UI based on `props.state`. If interactive, handle events and call `props.onInteraction` with a `SidekickMessage` containing a `camelCase` payload.
5.  **Add Styles (`MyNewModuleComponent.css`):** Create and import CSS.
6.  **Register (`moduleRegistry.ts`):** Import component and logic functions. Add `registry.set('myNewModule', { type: 'myNewModule', component, getInitialState, updateState, isInteractive });`.
7.  **Protocol (`protocol.md`):** Document the `camelCase` payloads for your new module.
8.  **Python Lib (Optional):** Add a corresponding class in the Python library (`libs/python/src/sidekick/`) that sends the correct `camelCase` payloads. Update `libs/python/README.md`.

## 9. Troubleshooting

*   **WebSocket Issues:** Check backend logs, browser DevTools (Network & Console), firewall, URL (`ws://localhost:5163`). Check `isConnected` state.
*   **UI Not Updating / Incorrect State:** Verify incoming messages (Network tab) have correct `module`, `method`, `target`, and **`camelCase` `payload` keys/structure**. Check console warnings/errors from `rootReducer` and specific `*Logic.ts` files. Ensure `updateState` functions are pure and return *new* object references on change. Use React DevTools to inspect component props (`id`, `state`) and `AppState`.
*   **Module Not Appearing:** Check `spawn` message is received with correct `target`. Check `moduleRegistry` registration. Check `moduleOrder` in React DevTools. Check console for errors during `getInitialState` or initial render.
*   **Interaction Not Working:** Check `isInteractive` flag in `moduleRegistry`. Verify `onInteraction` is passed as a prop. Check component's event handlers call `onInteraction` with a `SidekickMessage` having the correct `src`, `module`, `method: 'notify'`, and **`camelCase` `payload` keys/structure**. Check Hero-side logs for received message processing.
*   **Viz Highlighting/Update Issues:** Check console logs from `vizLogic.ts` (`applyModification`). Verify incoming `update` payload has correct `action`/`variableName`/`options` structure with `camelCase` keys. Check `lastChanges` state in React DevTools. Ensure `RenderValue` uses `observableTracked` (camelCase).
*   **Canvas Drawing Issues:** Check console for errors in `CanvasComponent.tsx` `useEffect`. Verify incoming `update` payload includes unique `commandId`. Check `lastProcessedCommandId` state. Ensure `ctx` is not null.
*   **Control Issues:** Check `add`/`remove` payloads sent from Python have correct `action`/`controlId`/`options` structure with `camelCase` config keys and `controlType: "textInput"` or `"button"`. Check `ControlComponent` reads config using `camelCase` and renders based on the correct `type`. Check `notify` messages sent from `ControlComponent` have correct `event`, `controlId` (camelCase), and `value?`.