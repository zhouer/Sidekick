# Sidekick Web Application

## 1. Overview

This directory contains the frontend React application for the Sidekick Visual Coding Buddy. Its primary responsibility is to:

1.  Establish and manage a WebSocket connection to the Sidekick server (typically provided by the VS Code extension or a standalone server).
2.  Receive command messages (`spawn`, `update`, `remove`) from the "Hero" (e.g., Python script via the server) over WebSocket.
3.  Maintain the application state, primarily the collection of active visual module instances and their rendering order, using a centralized reducer in `App.tsx`.
4.  Delegate module-specific logic: Utilize a central `moduleRegistry` to dynamically access module-specific state initialization (`getInitialState`) and update logic (`updateState`).
5.  Render modules dynamically: Look up the appropriate React component for each active module instance via the `moduleRegistry` and render them in the correct order.
6.  Send user interaction event messages (`notify`) back to the Hero via the WebSocket connection when users interact with UI elements (for modules marked as interactive).

This web application is designed to be embedded within a VS Code Webview or run standalone (e.g., via Electron) but includes development utilities for independent UI development and testing. The architecture emphasizes decoupling module logic to facilitate extension and potential plugin systems.

## 2. Tech Stack

*   **Framework:** React (v18+, functional components, hooks)
*   **Language:** TypeScript
*   **Build Tool:** Vite
*   **State Management:** React `useReducer` hook (in `App.tsx`) for centralized application state (module instances and order). Module-specific state logic is delegated.
*   **WebSocket:** Native browser WebSocket API, managed via the `useWebSocket` custom hook.
*   **Styling:** Standard CSS (using global `App.css` and per-component `.css` files).

## 3. Project Structure

```text
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
│   ├── modules/        # Module logic, types, and registration
│   │   ├── grid/
│   │   │   ├── gridLogic.ts
│   │   │   └── types.ts
│   │   ├── console/
│   │   │   ├── consoleLogic.ts
│   │   │   └── types.ts
│   │   ├── viz/
│   │   │   ├── vizLogic.ts  # Contains logic previously in stateUtils
│   │   │   └── types.ts
│   │   ├── canvas/
│   │   │   ├── canvasLogic.ts
│   │   │   └── types.ts
│   │   ├── control/
│   │   │   ├── controlLogic.ts
│   │   │   └── types.ts
│   │   └── moduleRegistry.ts # Central registry for module definitions
│   ├── types/          # Shared TypeScript type definitions (generic)
│   │   └── index.ts
│   ├── App.css         # Global application styles
│   ├── App.tsx         # Root application component (state mgmt, rendering, WS connection)
│   ├── index.css       # Base CSS (often includes theme variables)
│   └── main.tsx        # Application entry point (renders App)
├── index.html          # Vite HTML entry point
├── package.json        # Dependencies and scripts
├── tsconfig.json       # Main TypeScript config
├── tsconfig.node.json  # TS config for Vite/Node env
└── vite.config.ts      # Vite configuration
```

## 4. Core Concepts & Implementation Details

### 4.1. WebSocket Communication (`useWebSocket` hook)

*   **Location:** `src/hooks/useWebSocket.ts`
*   **Functionality:** Encapsulates establishing and maintaining the WebSocket connection (default target `ws://localhost:5163`).
*   **Message Handling:** Receives raw messages, parses them as JSON, and invokes the `onMessage` callback (provided by `App.tsx`) with the parsed data.
*   **Sending Messages:** Exports a stable `sendMessage` function used by `App.tsx` to forward interaction events (`SidekickMessage`) back to the Hero.

### 4.2. State Management (`App.tsx` - `useReducer`, `rootReducer`)

*   **Centralized State (`AppState`):** Managed by `useReducer` in the `App` component. Defined in `src/types/index.ts`, it primarily contains:
    *   `modulesById: Map<string, ModuleInstance>`: Stores all active module instances, keyed by their unique `target`/instance ID. The `ModuleInstance` type here is generic.
    *   `moduleOrder: string[]`: An array storing the IDs of active modules in the order they were created (`spawn`ed). This dictates the rendering order.
*   **Generic Reducer (`rootReducer`):** A pure function responsible for calculating the next `AppState`.
    *   **Delegation**: It no longer contains logic specific to individual module types. Instead, when processing `spawn` or `update` messages, it looks up the corresponding `ModuleDefinition` in the `moduleRegistry` based on the message's `module` type string.
    *   **Spawn**: Calls the registered `moduleDefinition.getInitialState(target, payload)` to create the initial state for the new module instance.
    *   **Update**: Calls the registered `moduleDefinition.updateState(currentState, payload)` to get the potentially updated state for an existing module instance. It checks if the returned state object reference is different from the current one to determine if an update occurred.
    *   **Remove**: Handles removing the instance from `modulesById` and `moduleOrder` directly.
    *   **Immutability:** The reducer ensures immutability by always creating new `Map` and `Array` instances when the state changes, triggering React's re-rendering mechanism.

### 4.3. Module Definition and Registry (`src/modules/`)

*   **`ModuleDefinition` Interface (`src/types/index.ts`)**: Defines the contract that every module type must adhere to. It includes:
    *   `type: string`: The unique identifier for the module type.
    *   `component: React.FC<any>`: The React component used for rendering.
    *   `getInitialState: (id, payload) => State`: Function to create the initial state.
    *   `updateState: (currentState, payload) => State`: Pure function to update the state based on a payload.
    *   `isInteractive?: boolean`: Optional flag indicating if the module needs the `onInteraction` callback.
*   **Module Logic (`src/modules/*/ *Logic.ts`)**: Each module type has its own file containing the implementations of `getInitialState` and `updateState`. These functions handle the specific payload structures and state transitions for that module. Crucially, `updateState` must return a new state object reference if a change occurred, otherwise return the original reference. Immutable update logic (like the complex updates for Viz) is contained within these files.
*   **Module Types (`src/modules/*/types.ts`)**: Each module type defines its specific State interface (e.g., `GridState`) and any specific Spawn/Update/Notify Payload interfaces it uses.
*   **Central Registry (`src/modules/moduleRegistry.ts`)**:
    *   Imports all built-in module components and logic functions.
    *   Creates a `Map<string, ModuleDefinition>`.
    *   Registers each built-in module by creating a `ModuleDefinition` object and adding it to the map, keyed by the module type string (e.g., `registry.set('grid', { type: 'grid', component: GridModule, ... })`).
    *   Exports the `moduleRegistry` map for use by `App.tsx`.

### 4.4. Module Rendering (`App.tsx` - `renderModules`)

*   Iterates over the `moduleOrder` array.
*   For each ID, retrieves the `ModuleInstance` from `modulesById`.
*   Looks up the corresponding `ModuleDefinition` in the `moduleRegistry` using `moduleInstance.type`.
*   Retrieves the `component` from the definition.
*   Prepares props, **conditionally adding** the `onInteraction` callback only if `moduleDefinition.isInteractive` is true.
*   Renders the `ModuleComponent`, passing the `key` prop directly and spreading the remaining props (`id`, `state`, optional `onInteraction`).

### 4.5. Module Components (`src/components/*Module.tsx`)

*   **Structure:** Functional React components receiving props like `id`, `state` (typed specifically within the component, e.g., `GridModule` expects `state: GridState`), and optionally `onInteraction`.
*   **Rendering:** Render the UI based on the received `state` prop.
*   **Interaction:** If `isInteractive` is true for the module type, the component will receive the `onInteraction` prop. It calls this function with a `SidekickMessage` object when a relevant user action occurs (e.g., grid click, console submit).

### 4.6. Immutable State Updates (Module Logic)

*   The responsibility for performing immutable updates now lies *within* each module's `updateState` function in its respective `*Logic.ts` file.
*   For simple modules, this might involve simple spread syntax (`...currentState`).
*   For complex modules like `viz`, the specific logic (previously in `stateUtils.ts`, involving deep cloning and path-based updates) is now encapsulated within `src/modules/viz/vizLogic.ts`.

## 5. Setup & Development

1.  **Navigate:** `cd Sidekick/webapp`
2.  **Install:** `npm install` (or `yarn`)
3.  **Run Dev Server:** `npm run dev`
    *   Starts Vite's dev server (e.g., `http://localhost:5173`).
4.  **Connect:** Ensure the Sidekick backend (Python script or VS Code extension providing the WebSocket server at `ws://localhost:5163`) is running for full functionality.

## 6. Build Process

*   **Command:** `npm run build`
*   **Output:** Static files (HTML, JS, CSS) generated in `webapp/dist/`.
*   **Deployment:** These static files are intended to be served by the VS Code extension's Webview panel or an Electron application shell.

## 7. Styling

*   Global styles in `src/index.css` and `src/App.css`.
*   Component-specific styles are co-located (e.g., `src/components/GridModule.css`).

## 8. Adding a New Visual Module (Workflow)

1.  **Component (`src/components/`):** Create the React component (`NewModule.tsx`) and its CSS (`NewModule.css`). Define its props, including `state` (typed specifically) and `onInteraction` if needed.
2.  **Types (`src/modules/newModule/types.ts`):** Create a `types.ts` file. Define and export the specific state interface (e.g., `NewModuleState`) and any specific Payload interfaces (`NewModuleSpawnPayload`, `NewModuleUpdatePayload`, `NewModuleNotifyPayload`) needed.
3.  **Logic (`src/modules/newModule/newModuleLogic.ts`):** Create a `logic.ts` file.
    *   Import types from `./types`.
    *   Implement and export `getInitialState(id, payload: NewModuleSpawnPayload): NewModuleState`.
    *   Implement and export `updateState(currentState: NewModuleState, payload: NewModuleUpdatePayload): NewModuleState`. Ensure this function handles immutability correctly.
4.  **Registration (`src/modules/moduleRegistry.ts`):**
    *   Import the `NewModule` component and `* as newModuleLogic` functions.
    *   Add a new entry to the `registry` map:
        ```typescript
        registry.set('newModule', { // Use the unique string type identifier
            type: 'newModule',
            component: NewModule,
            getInitialState: newModuleLogic.getInitialState,
            updateState: newModuleLogic.updateState,
            isInteractive: true, // or false, depending on the module
        });
        ```
5.  **Protocol (`protocol.md`):** Document the new module's type string and its specific `spawn`, `update`, and `notify` payload structures (using `camelCase` keys).
6.  **Backend Library:** Create a corresponding class/interface in the backend library (e.g., Python) to send the correct messages for this new module type.

## 9. Troubleshooting

*   **WebSocket Issues:** Check backend logs, browser DevTools (Network & Console), firewall, ensure URL matches (`ws://localhost:5163`). Check `isConnected` state in UI.
*   **Module Not Appearing/Updating:**
    *   Verify incoming messages (`spawn`, `update`) in DevTools Network tab. Check `target` ID and `module` type string.
    *   Check `console.warn`/`error` logs from the `rootReducer` in `App.tsx` (e.g., "Unknown module type", "Module not found").
    *   Check `console.warn`/`error` logs from the specific module's `*Logic.ts` file (e.g., invalid payload).
    *   Ensure the module is correctly registered in `moduleRegistry.ts`.
    *   In the module's `updateState` logic, verify that a *new* state object reference is returned when changes occur. Use `console.log` or React DevTools to compare state before and after the reducer runs.
*   **Interaction Not Working:**
    *   Verify `isInteractive: true` is set for the module in `moduleRegistry.ts`.
    *   Check browser console for logs from the module component's event handlers.
    *   Verify the `onInteraction` prop is being called with the correct `SidekickMessage` structure.
    *   Check backend logs to see if the `notify` message is received.
*   **Viz Highlighting/Update Issues:** Check console logs from `vizLogic.ts` (specifically `updateRepresentationAtPath` and `applyUpdateToParent`) to trace state transformations. Use React DevTools to inspect the `state` prop passed to `VizModule` and `RenderValue`.
*   **Build Errors:** Address TypeScript errors reported by `npm run build`. Check type definitions, imports, and logic in both shared types and module-specific files.