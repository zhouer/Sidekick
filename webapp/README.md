# Sidekick Web Application

## 1. Overview

This directory contains the frontend React application for the Sidekick Visual Coding Buddy. Its primary responsibility is to:

1.  Establish and manage a WebSocket connection to the Sidekick server (typically provided by the VS Code extension).
2.  Receive command messages (`spawn`, `update`, `remove`) from the "Hero" (Python script via the server) over WebSocket.
3.  Maintain the application state, including all active visual module instances (`Grid`, `Console`, `Viz`, `Canvas`, `Control`) and their creation order, using a centralized reducer.
4.  Render the appropriate React components for each module based on its current state and in the correct order.
5.  Send user interaction event messages (`notify`) back to the Hero via the WebSocket connection when users interact with UI elements (e.g., grid clicks, button presses, text submissions).

This web application is designed to be embedded within a VS Code Webview but includes development utilities (like a basic WebSocket echo server via Vite plugin) for independent UI development and testing.

## 2. Tech Stack

*   **Framework:** React (v18+, functional components, hooks)
*   **Language:** TypeScript
*   **Build Tool:** Vite
*   **State Management:** React `useReducer` hook (in `App.tsx`) for centralized application state management, emphasizing immutable updates.
*   **WebSocket:** Native browser WebSocket API, managed via the `useWebSocket` custom hook.
*   **Styling:** Standard CSS (using global `App.css` and per-component `.css` files).

## 3. Project Structure

```
webapp/
├── public/             # Static assets
├── src/                # Source code
│   ├── components/     # Module-specific React components & CSS
│   │   ├── GridModule.tsx
│   │   ├── ConsoleModule.tsx
│   │   ├── VizModule.tsx     # Includes RenderValue helper
│   │   ├── CanvasModule.tsx
│   │   └── ControlModule.tsx
│   ├── hooks/          # Custom React hooks
│   │   └── useWebSocket.ts
│   ├── types/          # Shared TypeScript type definitions
│   │   └── index.ts
│   ├── utils/          # Utility functions
│   │   └── stateUtils.ts # Immutable update helper for Viz
│   ├── App.css         # Global application styles
│   ├── App.tsx         # Root application component (state, routing, rendering)
│   ├── index.css       # Base CSS (often includes theme variables)
│   └── main.tsx        # Application entry point (renders App)
├── index.html          # Vite HTML entry point
├── package.json        # Dependencies and scripts
├── tsconfig.json       # Main TypeScript config
├── tsconfig.node.json  # TS config for Vite/Node env
├── vite.config.ts      # Vite configuration
└── vite-plugin-ws-server.ts # Optional Dev WS Echo Server
```

## 4. Core Concepts & Implementation Details

### 4.1. WebSocket Communication (`useWebSocket` hook)

*   **Location:** `src/hooks/useWebSocket.ts`
*   **Functionality:** Encapsulates establishing and maintaining the WebSocket connection (default target `ws://localhost:5163`).
*   **State:** Tracks connection status (`isConnected`).
*   **Message Handling:** Receives raw messages, parses them as JSON, and invokes the `onMessage` callback (provided by `App.tsx`) with the parsed data.
*   **Sending Messages:** Exports a stable `sendMessage` function that takes a JavaScript object, stringifies it to JSON, and sends it over the WebSocket. This is used by `App.tsx` to forward interaction events.
*   **Error Handling:** Includes basic logging for connection errors and closure. Consider adding auto-reconnect logic for robustness.

### 4.2. State Management (`App.tsx` - `useReducer`, `rootReducer`)

*   **Centralized State (`AppState`):** Managed by `useReducer` in the `App` component. Defined in `src/types/index.ts`, it contains:
    *   `modulesById: Map<string, ModuleInstance>`: Stores all active module instances, keyed by their unique `target` ID for efficient lookup and updates.
    *   `moduleOrder: string[]`: An array storing the IDs of active modules in the order they were created (`spawn`ed). This array dictates the rendering order in the UI.
*   **Reducer (`rootReducer`):** A pure function responsible for calculating the next state based on the current state and a dispatched `action`.
    *   **Actions:** Handles `PROCESS_MESSAGE` (for incoming Hero commands) and `CLEAR_ALL`.
    *   **Immutability:** CRITICAL principle. The reducer *never* modifies the existing `state` object, `modulesById` map, or `moduleOrder` array directly. It always returns a *new* `AppState` object containing new Map and Array instances when changes occur. This is achieved using `new Map(state.modulesById)`, `[...state.moduleOrder]`, and object spread (`...`) within helper functions.
    *   **Message Processing (`PROCESS_MESSAGE`):**
        *   Delegates logic based on `message.method` (`spawn`, `update`, `remove`).
        *   Uses helper functions (`handleSpawn`, `handleUpdate`) for cleaner organization.
    *   **Spawn (`handleSpawn`):** Creates the appropriate initial `ModuleInstance` based on `message.module`. Adds the new instance to `modulesById` and appends its ID to `moduleOrder`. Returns a new `AppState`.
    *   **Update (`handleUpdate`):** Finds the target module in `modulesById`. Delegates to module-specific helper functions (`updateGridState`, `updateVizState`, etc.) based on the module's `type`. These helpers parse the `payload` (expecting `camelCase` keys and the `action`/`options` structure), perform immutable updates on the module's internal `state`, and return `true` if a change occurred. `handleUpdate` then updates the `modulesById` map with the modified module instance (if changed) and returns a new `AppState` (keeping `moduleOrder` the same).
    *   **Remove:** Filters the target ID out of `moduleOrder` and deletes the entry from `modulesById`. Returns a new `AppState`.
    *   **Clear All:** Returns the initial empty `AppState`.

### 4.3. Module Rendering (`App.tsx` - `renderModules`)

*   The `renderModules` function iterates over the `moduleOrder` array (not the `modulesById` map).
*   For each ID in `moduleOrder`, it retrieves the corresponding `ModuleInstance` from the `modulesById` map.
*   A `switch` statement based on `module.type` renders the correct React component (e.g., `<GridModule />`, `<VizModule />`).
*   Necessary props (`key`, `id`, `state`, `onInteraction`) are passed down to each module component. Using `module.id` as the `key` ensures React efficiently handles updates, additions, and removals based on the stable order provided by `moduleOrder`.

### 4.4. Module Components (`src/components/*Module.tsx`)

*   **General Structure:** Each component is a functional React component receiving `id`, `state` (specific to its type, e.g., `GridState`), and potentially `onInteraction` as props.
*   **Rendering:** They render the UI based on the received `state` prop.
*   **Interaction:** Interactive modules (`Grid`, `Console`, `Control`) use the `onInteraction` callback prop to send `SidekickMessage` objects (with `method: 'notify'`, `src: id`, and a specific `payload`) back to `App.tsx` when a user action occurs.

#### Specific Component Details:

*   **`GridModule.tsx`:** Renders cells in a grid layout. Handles `onClick` on cells to trigger `onInteraction` with click coordinates. Uses `state.cells` to determine color/text.
*   **`ConsoleModule.tsx`:** Displays `state.lines`. Uses `useRef` and `useEffect` to auto-scroll the output area. Manages local input field state with `useState`. Triggers `onInteraction` on text submission.
*   **`VizModule.tsx` / `RenderValue.tsx`:**
    *   `VizModule` maps over `state.variables`.
    *   `RenderValue` is a recursive component rendering the `VizRepresentation` tree.
    *   Manages expand/collapse state locally using `useState`.
    *   Implements highlighting logic by comparing `currentPath` with `state.lastChanges[varName].path` and checking the timestamp. Uses dynamic React `key` prop changes to re-trigger CSS animations reliably. Applies `.observable-tracked` styling.
*   **`CanvasModule.tsx`:**
    *   Renders an HTML `<canvas>` element.
    *   Uses `useRef` for the canvas element and `useState` for the 2D rendering context (`ctx`).
    *   Crucially, uses another `useRef` (`lastProcessedCommandId`) to track the ID of the last successfully executed drawing command from the `state.commandQueue` prop.
    *   A `useEffect` hook processes *new* commands in the `commandQueue` (commands arriving after `lastProcessedCommandId`) synchronously, executing drawing operations on the `ctx`. This ensures commands are executed exactly once and in the correct order, even if React re-renders.
*   **`ControlModule.tsx`:**
    *   Renders controls dynamically based on the `state.controls` Map.
    *   Uses local `useState` (`inputValues`) to manage the state of text input fields within the component.
    *   Handles button clicks and text input submissions, calling `onInteraction` with the correct `controlId` and event details in the payload.

### 4.5. Immutable State Updates (`src/utils/stateUtils.ts`)

*   **`updateRepresentationAtPath`:** A key utility function used exclusively by the `viz` module's update logic in the reducer.
    *   **Purpose:** Given a `VizRepresentation` (representing a potentially complex/nested variable) and a `VizUpdatePayload` describing a granular change (e.g., setting an item in a list deep within the structure), this function immutably applies that change.
    *   **Mechanism:** It deeply clones the input `VizRepresentation`. Then, it navigates the cloned structure based on the `payload.options.path`. Finally, it applies the change (specified by `payload.action` and using data from `payload.options`) to the appropriate node within the cloned structure.
    *   **Importance:** This enables the `Viz` module to update its display efficiently without needing the entire variable representation resent from the Hero端 for every small change within an `ObservableValue`. It relies heavily on correct path information and representation structure provided in the payload. Includes helper functions `cloneRepresentation` and `findParentNode`.

## 5. Setup & Development

1.  **Navigate:** `cd Sidekick/webapp`
2.  **Install:** `npm install` (or `yarn`)
3.  **Run Dev Server:** `npm run dev`
    *   This typically starts Vite's dev server (e.g., `http://localhost:5173`).
    *   It *might* also activate the `vite-plugin-ws-server` (Echo server at `ws://localhost:5163`) if the plugin is enabled in `vite.config.ts`. Note this echo server is **only for basic connectivity testing** and does not replace the actual Sidekick backend logic.
4.  **Connect:** For full functionality, ensure the real Sidekick backend (Python library script or VS Code extension providing the WebSocket server at `ws://localhost:5163`) is running.

## 6. Build Process

*   **Command:** `npm run build`
*   **Output:** Static files (HTML, JS, CSS) generated in `webapp/dist/`.
*   **Deployment:** These static files are intended to be served by the VS Code extension's Webview panel.

## 7. Styling

*   Global styles in `src/index.css` and `src/App.css`.
*   Component-specific styles are co-located (e.g., `src/components/GridModule.css`). Uses standard CSS conventions.

## 8. Adding a New Visual Module (Workflow)

1.  **Protocol:** Define `spawn`/`update`/`remove`/`notify` payloads (using `camelCase` and `action`/`options`) in `protocol.md`.
2.  **Types (`src/types/index.ts`):** Add new state interface (e.g., `NewModuleState`), payload interfaces, and add the new module type to `ModuleType` and `ModuleInstance` unions.
3.  **Component (`src/components/`):** Create the React component (`.tsx`) and its CSS (`.css`). Implement rendering based on its state prop and call `onInteraction` if needed.
4.  **Reducer (`App.tsx`):**
    *   Add logic to `handleSpawn` to create the initial state.
    *   Create an `updateNewModuleState` helper function and add a case to `handleUpdate` to call it.
    *   The `remove` case in `rootReducer` handles cleanup automatically.
5.  **Rendering (`App.tsx`):** Add a `case` to the `switch` statement in `renderModules` to render the new component.
6.  **Python Library:** Create a corresponding Python class in `libs/python/src/sidekick/` that sends the correct messages.

## 9. Troubleshooting

*   **WebSocket Issues:** Check backend logs, browser DevTools (Network & Console), firewall, ensure URL matches (`ws://localhost:5163`). Check `isConnected` state.
*   **UI Not Updating / Incorrect State:** Verify incoming messages in DevTools Network tab. Check `console.warn`/`error` logs from the `rootReducer`. Ensure updates are immutable. Use React DevTools to inspect component props and state (`modulesById`, `moduleOrder`). Verify `target` IDs match.
*   **Modules Out of Order:** Check the `moduleOrder` array in React DevTools. Verify the `spawn` logic correctly pushes IDs and `remove` correctly filters IDs.
*   **Viz Highlighting Issues:** Check `lastChanges` state in React DevTools. Verify paths match between `lastChanges.path` and `RenderValue`'s `currentPath`. Ensure CSS animation (`viz-highlight-node`) is defined correctly and not overridden. Check highlight duration (`HIGHLIGHT_DURATION`).
*   **Canvas Drawing Issues:** Check browser console for errors during command execution in `CanvasModule`. Verify `commandId`s are unique and processed correctly using `lastProcessedCommandId`.
*   **Control Interactions Not Working:** Check browser console for logs from `ControlModule` event handlers. Verify the correct `controlId` is being sent in the `notify` payload. Check Python-side logs to see if the message is received and the callback is invoked.
*   **Build Errors:** Address TypeScript errors reported by `npm run build`. Check type definitions, imports, and component logic.