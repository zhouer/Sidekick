# Sidekick Web Application

## 1. Overview

This directory contains the frontend React application for the Sidekick Visual Coding Buddy. Its primary responsibility is to:

1.  Establish and manage a WebSocket connection to the Sidekick server (typically provided by the VS Code extension or a standalone server).
2.  Receive command messages (`spawn`, `update`, `remove`) from the "Hero" (Python script via the server) over WebSocket.
3.  Maintain the application state, primarily tracking active visual module instances (`modulesById`) and their rendering order (`moduleOrder`), using a centralized reducer (`App.tsx`).
4.  Delegate module-specific state initialization and updates to registered module logic functions found via the `moduleRegistry`.
5.  Dynamically render the appropriate React component for each active module based on its type (obtained from the `moduleRegistry`) and current state.
6.  Send user interaction event messages (`notify`) back to the Hero via the WebSocket connection when users interact with interactive UI elements (e.g., grid clicks, button presses, text submissions).

This web application is designed to be embedded within a VS Code Webview or run standalone (e.g., via Electron) but includes development utilities for independent UI development and testing.

## 2. Tech Stack

*   **Framework:** React (v18+, functional components, hooks)
*   **Language:** TypeScript
*   **Build Tool:** Vite
*   **State Management:** React `useReducer` hook (in `App.tsx`) for central application state (`modulesById`, `moduleOrder`), delegating module-specific state calculations.
*   **WebSocket:** Native browser WebSocket API, managed via the `useWebSocket` custom hook.
*   **Styling:** Standard CSS (using global `App.css` and per-module co-located `.css` files).

## 3. Project Structure

```
webapp/
├── public/             # Static assets
├── src/                # Source code
│   ├── hooks/          # Custom React hooks
│   │   └── useWebSocket.ts
│   ├── modules/        # Core application feature: Modules
│   │   ├── canvas/     # Example: Canvas Module directory
│   │   │   ├── CanvasModule.css  # Component styles
│   │   │   ├── CanvasModule.tsx  # Component UI
│   │   │   ├── canvasLogic.ts    # State initialization & update logic
│   │   │   └── types.ts          # Module-specific types (State, Payloads)
│   │   ├── console/    # Console Module directory
│   │   │   ├── ... (Component, CSS, Logic, Types)
│   │   ├── control/    # Control Module directory
│   │   │   ├── ...
│   │   ├── grid/       # Grid Module directory
│   │   │   ├── ...
│   │   ├── viz/        # Viz Module directory
│   │   │   ├── ...     # (VizLogic.ts contains updateRepresentationAtPath etc.)
│   │   └── moduleRegistry.ts # Central registry for all module definitions
│   ├── types/          # Shared application-level types
│   │   └── index.ts    # (e.g., HeroMessage, SidekickMessage, ModuleInstance, ModuleDefinition)
│   ├── App.css         # Global application styles
│   ├── App.tsx         # Root application component (Reducer dispatch, Rendering loop, WS handling)
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
*   **Functionality:** Encapsulates establishing and maintaining the WebSocket connection (default `ws://localhost:5163`). Manages connection state (`isConnected`), message parsing, error handling, and provides a stable `sendMessage` function.
*   **Integration:** Used by `App.tsx` to receive messages (forwarded to the reducer) and send interaction messages back to the Hero. Consider adding auto-reconnect logic for improved robustness.

### 4.2. State Management (`App.tsx` - `useReducer`, `rootReducer`)

*   **Centralized State (`AppState`):** Managed by `useReducer` in `App.tsx`. Defined in `src/types/index.ts`, it primarily contains:
    *   `modulesById: Map<string, ModuleInstance>`: Stores all active module instances, keyed by their unique ID. `ModuleInstance` is now a generic type holding `id`, `type` (string), and `state` (any).
    *   `moduleOrder: string[]`: An array storing the IDs of active modules in the order they were created (`spawn`ed), dictating the rendering sequence.
*   **Generic Reducer (`rootReducer`):** Acts as a central dispatcher based on incoming message `method` (`spawn`, `update`, `remove`).
    *   **Delegation:** It **does not** contain logic specific to any module type. Instead, it uses the `moduleRegistry` to find the correct `ModuleDefinition` based on the message's `module` type string.
    *   **Spawn:** Calls the registered `getInitialState(targetId, payload)` function for the specific module type to create the initial state. Updates `modulesById` and `moduleOrder`.
    *   **Update:** Retrieves the current module instance, then calls the registered `updateState(currentState, payload)` function for that module type. If `updateState` returns a new object reference (indicating a change), the reducer updates the instance in `modulesById`.
    *   **Remove:** Removes the instance from `modulesById` and filters its ID from `moduleOrder`.
    *   **Immutability:** Crucial principle. The reducer ensures the top-level `AppState`, `modulesById` Map, and `moduleOrder` Array references are updated immutably when changes occur. Module-specific immutability is now the responsibility of the `updateState` functions defined in `*Logic.ts`.

### 4.3. Module Definition & Registry (`ModuleDefinition`, `moduleRegistry.ts`)

*   **Contract (`ModuleDefinition`)**: Defined in `src/types/index.ts`. This interface specifies the "contract" any module must fulfill to be integrated into the application. It requires:
    *   `type`: A unique string identifier (e.g., "grid", "console").
    *   `component`: The React functional component used for rendering.
    *   `getInitialState`: A function to create the initial state for an instance.
    *   `updateState`: A **pure function** to calculate the next state based on the current state and an update payload. Must return a new object reference if the state changes.
    *   `isInteractive?`: An optional boolean flag indicating if the module needs the `onInteraction` callback prop.
*   **Registry (`moduleRegistry.ts`)**:
    *   **Location:** `src/modules/moduleRegistry.ts`
    *   **Functionality:** A central `Map` that registers all known `ModuleDefinition` objects, mapping the `type` string to its definition. Currently, built-in modules are registered statically via imports.
    *   **Usage:** `App.tsx`'s reducer and rendering logic query this registry to get the appropriate logic functions and components for each module type.
    *   **Extensibility:** This registry is the key integration point for a future dynamic plugin system (where plugins would call a `registerModule` function to add their definitions at runtime).

### 4.4. Module Structure (`src/modules/{moduleName}/`)

*   **Co-location:** Each module now resides in its own directory (e.g., `src/modules/grid/`).
*   **Contents:** Typically contains:
    *   `{ModuleName}Module.tsx`: The React component for UI rendering and handling local UI state/interactions.
    *   `{moduleName}Logic.ts`: Contains the module's `getInitialState` and `updateState` logic (pure functions). May include internal helper functions (like `vizLogic.ts` containing `updateRepresentationAtPath`).
    *   `types.ts`: Defines TypeScript interfaces specific to this module (e.g., `GridState`, `GridUpdatePayload`).
    *   `{ModuleName}Module.css`: Styles specific to the component.

### 4.5. Module Components (`src/modules/*/ *Module.tsx`)

*   **General Structure:** Functional React components receiving `id`, `state` (typed specifically within the component using imports from its local `types.ts`), and potentially `onInteraction` as props.
*   **Responsibilities:**
    *   Render the UI based solely on the received `state` prop.
    *   Manage any purely local UI state using React hooks (e.g., input values, expand/collapse toggles).
    *   Handle user interaction events (clicks, key presses, form submissions).
    *   If interactive (`isInteractive: true` in definition), call the `onInteraction` prop with a correctly formatted `SidekickMessage` to notify the Hero backend.
    *   Handle UI-specific side effects using `useEffect` (e.g., `CanvasModule` executes drawing commands; `ConsoleModule` handles auto-scrolling).

#### Specific Component Notes:

*   **`VizModule.tsx` / `RenderValue.tsx`:** Renders complex, potentially nested data structures. `RenderValue` is recursive. Manages expand/collapse state locally. Highlighting logic depends on `lastChanges` timestamp in the `VizState`. Complex state *calculation* logic (like `updateRepresentationAtPath`) now resides in `vizLogic.ts`.
*   **`CanvasModule.tsx`:** Renders an HTML `<canvas>`. Uses `useEffect` and `useRef` to manage the 2D context and, critically, to process the `commandQueue` from props exactly once and in order, executing the actual drawing operations as a side effect. The state update logic in `canvasLogic.ts` simply adds commands to the queue.

## 5. Setup & Development

1.  **Navigate:** `cd Sidekick/webapp`
2.  **Install:** `npm install` (or `yarn`)
3.  **Run Dev Server:** `npm run dev`
    *   Starts Vite's dev server (e.g., `http://localhost:5173`).
4.  **Connect:** Ensure the Sidekick backend (Python script or VS Code extension providing the WebSocket server at `ws://localhost:5163`) is running for full functionality.

## 6. Build Process

*   **Command:** `npm run build`
*   **Output:** Static files (HTML, JS, CSS) generated in `webapp/dist/`.
*   **Deployment:** These files are typically served by the VS Code extension's Webview panel or packaged within an Electron app.

## 7. Styling

*   Global base styles in `src/index.css` and `src/App.css`.
*   Module-specific styles are now co-located with their components (e.g., `src/modules/grid/GridModule.css`). Standard CSS conventions are used. Consider CSS Modules or CSS-in-JS for larger-scale projects if needed.

## 8. Adding a New Visual Module (Workflow - Revised)

1.  **Create Directory:** Create a new folder under `src/modules/` (e.g., `src/modules/myNewModule/`).
2.  **Define Types (`types.ts`):** Inside the new directory, create `types.ts`. Define interfaces for the module's state (`MyNewModuleState`) and any specific spawn/update/notify payloads it uses.
3.  **Implement Logic (`myNewModuleLogic.ts`):** Create `myNewModuleLogic.ts`. Implement and export:
    *   `getInitialState(instanceId, payload): MyNewModuleState`
    *   `updateState(currentState, payload): MyNewModuleState` (ensure it's pure and handles immutability).
4.  **Create Component (`MyNewModule.tsx`):** Create the React component file. Implement the UI rendering based on `props.state` (typed as `MyNewModuleState`). If interactive, handle events and call `props.onInteraction`.
5.  **Add Styles (`MyNewModule.css`):** Create the CSS file and import it into the component.
6.  **Register (`moduleRegistry.ts`):**
    *   Import the component and logic functions into `src/modules/moduleRegistry.ts`.
    *   Add a new entry using `registry.set('myNewModule', { ... });`, providing the `type` string, imported component, logic functions, and `isInteractive` flag.
7.  **Protocol (Optional but Recommended):** Update `protocol.md` to document the payloads for your new module type.

## 9. Troubleshooting

*   **WebSocket Issues:** Check backend logs, browser DevTools (Network & Console), firewall, ensure URL matches (`ws://localhost:5163`). Check `isConnected` state in the UI.
*   **UI Not Updating / Incorrect State:** Verify incoming messages in DevTools Network tab. Check `console.warn`/`error` logs from the `rootReducer` in `App.tsx` and specific `*Logic.ts` files. Ensure `updateState` functions are returning *new* object references on change. Use React DevTools to inspect component props (`id`, `state`) and the central `AppState` (`modulesById`, `moduleOrder`).
*   **Module Not Appearing:** Check `spawn` message is received. Check `moduleRegistry` for correct registration. Check `moduleOrder` in React DevTools. Check browser console for errors during `getInitialState` or initial render.
*   **Interaction Not Working:** Check `isInteractive` flag in `moduleRegistry`. Verify `onInteraction` is passed as a prop in `App.tsx`'s render logic. Check component's event handlers and the structure of the `SidekickMessage` being sent. Check Hero-side logs.
*   **Viz Highlighting/Update Issues:** Check console logs from `vizLogic.ts`. Verify `updateRepresentationAtPath` is correctly calculating the new representation and returning a new object. Check `lastChanges` state in React DevTools.
*   **Canvas Drawing Issues:** Check browser console for errors during command execution in `CanvasModule.tsx` `useEffect`. Verify `commandId`s are unique and processed correctly using `lastProcessedCommandId`. Ensure `ctx` is not null.
