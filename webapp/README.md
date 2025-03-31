# Sidekick Web Application

## 1. Overview

This directory contains the frontend React application for the Sidekick Visual Coding Buddy. Its primary responsibility is to:

1.  Establish a WebSocket connection to the Sidekick server (potentially part of the VS Code extension or a standalone server).
2.  Receive commands from the "Hero" (user's script, via the server) to `spawn`, `update`, or `remove` visual modules.
3.  Maintain the state for each active visual module instance (`Grid`, `Console`, `Viz`, `Canvas`, `Control`).
4.  Render the appropriate React components for each module based on its current state.
5.  Send user interaction events (like grid clicks, console input, button clicks, text submissions) back to the Hero via the WebSocket connection.

This web application is typically embedded within a VS Code Webview (managed by the `Sidekick/extension/` component) but can be run independently using Vite's development server for UI development.

## 2. Tech Stack

*   **Framework:** React (functional components, hooks like `useReducer`, `useCallback`, `useMemo`, `useState`)
*   **Language:** TypeScript
*   **Build Tool:** Vite
*   **Styling:** Standard CSS (per-component `.css` files)
*   **WebSocket:** Native browser WebSocket API (managed via `useWebSocket` hook)
*   **State Management:** `useReducer` hook in `App.tsx` for centralized module state, utilizing immutable update patterns.

## 3. Project Structure

```
webapp/
├── public/             # Static assets served directly by Vite/server
├── src/                # Main source code directory
│   ├── components/     # React components (GridModule, ConsoleModule, VizModule, CanvasModule, ControlModule)
│   │   ├── GridModule.css
│   │   ├── GridModule.tsx
│   │   ├── ConsoleModule.css
│   │   ├── ConsoleModule.tsx
│   │   ├── VizModule.css
│   │   ├── VizModule.tsx
│   │   ├── CanvasModule.css
│   │   ├── CanvasModule.tsx
│   │   ├── ControlModule.css
│   │   └── ControlModule.tsx
│   ├── hooks/          # Custom React hooks (useWebSocket.ts)
│   ├── types/          # Shared TypeScript type definitions (index.ts)
│   ├── utils/          # Utility functions (stateUtils.ts for immutable updates)
│   ├── App.css         # Global application styles
│   ├── App.tsx         # Main application component (state mgmt, message routing)
│   ├── index.css       # Vite default global styles
│   └── main.tsx        # Application entry point
├── .eslintrc.cjs       # ESLint configuration (if using separate file)
├── index.html          # HTML entry point for Vite
├── package.json        # Project dependencies and scripts
├── tsconfig.json       # TypeScript configuration
├── tsconfig.node.json  # TypeScript config for Vite config file
└── vite.config.ts      # Vite build and dev server configuration
```

## 4. Core Concepts

### 4.1. WebSocket Communication (`useWebSocket` hook)

*   Located in `src/hooks/useWebSocket.ts`.
*   Manages the persistent WebSocket connection (default: `ws://localhost:5163`).
*   Handles connection lifecycle (open, close, error) and status (`isConnected`).
*   Parses incoming JSON messages and invokes the `handleWebSocketMessage` callback provided by `App.tsx`.
*   Exports a `sendMessage` function used by `App.tsx` to send JSON-formatted messages (like `notify` events) back to the server/Hero.

### 4.2. State Management (`App.tsx` with `useReducer`)

*   The central state (`Map<string, ModuleInstance>`) holds all active module instances, keyed by their unique `target` ID.
*   `src/types/index.ts` defines the `ModuleInstance` discriminated union and specific state types (`GridState`, `ConsoleState`, `VizState`, `CanvasState`, `ControlState`).
*   The `moduleReducer` function in `App.tsx` processes incoming `HeroMessage` actions:
    *   **`spawn`:** Creates a new entry in the state map with the initial state for the specified module type (e.g., `ControlState` starts with an empty `controls` Map).
    *   **`update`:** Finds the existing module instance by `target` ID.
        *   For `Viz`, handles detailed variable updates using immutable helpers and updates `lastChanges`.
        *   For `Canvas`, appends new draw commands to the `commandQueue` array.
        *   For `Control`, handles `"add"` and `"remove"` operations specified in the payload to modify the `controls` Map within the module's state.
        *   For other modules (`Grid`, `Console`), updates their state based on the specific payload.
    *   **`remove`:** Deletes the module instance entry from the map.
*   State updates are immutable. State flows down as props to the individual module components.

### 4.3. Module Rendering (`App.tsx`, `*Module.tsx`)

*   `App.tsx` iterates through the `modules` state map.
*   A `switch` statement based on `module.type` renders the appropriate component (`GridModule`, `ConsoleModule`, `VizModule`, `CanvasModule`, `ControlModule`).
*   Each module component receives its `id` and specific `state` object as props.
*   Interactive modules (`GridModule`, `ConsoleModule`, `ControlModule`) receive an `onInteraction` prop function to send `notify` messages back up via the WebSocket.

### 4.4. `GridModule`

*   Renders an interactive grid based on the `GridState`.
*   Handles cell clicks and calls `onInteraction` with a `notify` payload (`{ event: "click", x: ..., y: ... }`).

### 4.5. `ConsoleModule`

*   Displays lines of text from `state.lines`.
*   Includes an input field and button for user input.
*   Handles input submission and calls `onInteraction` with a `notify` payload (`{ event: 'submit', value: ... }`).

### 4.6. `VizModule` & `RenderValue`

*   Displays variables from `state.variables` using the recursive `RenderValue` component.
*   Applies highlight animations based on `state.lastChanges`, comparing the change path with the component's current path.
*   Provides expand/collapse controls and specific styling (`observable-tracked`).

### 4.7. `CanvasModule`

*   Renders an HTML5 `<canvas>`.
*   Receives draw commands via `state.commandQueue`.
*   Uses internal logic (refs, effects) to process the queue incrementally and execute commands on the 2D context, ensuring correct order and avoiding duplicates.

### 4.8. `ControlModule` 

*   Renders dynamic controls (buttons, text inputs) based on the `state.controls` Map.
*   Manages the internal state of text inputs locally using `useState`.
*   Handles button clicks (`event: "click"`) and text input submissions (`event: "submit"`) by calling `onInteraction` with a `notify` payload containing the `control_id` (and `value` for submit).

## 5. Setup & Development

1.  **Navigate:** `cd Sidekick/webapp`
2.  **Install:** `npm install` (or `yarn install`)
3.  **Run Dev Server:** `npm run dev` (or `yarn dev`)
4.  **Connect:** Open the URL (e.g., `http://localhost:5173`). Ensure the Sidekick backend (providing WebSocket at `ws://localhost:5163`) is running.

## 6. Build Process

*   **Command:** `npm run build` (or `yarn build`)
*   **Output:** Static files in `webapp/dist`.
*   **Serving:** Typically served by the VS Code extension's Webview.

## 7. Styling

*   Global styles: `src/App.css`.
*   Component styles: Co-located CSS files (e.g., `src/components/ControlModule.css`).

## 8. Adding a New Visual Module

1.  **Define Protocol:** Specify payloads in `PROTOCOL.md`.
2.  **Define Types:** Add types in `src/types/index.ts`.
3.  **Create Component:** Build the React component (`.tsx`) and CSS.
4.  **Update Reducer (`App.tsx`):** Add logic for `spawn`, `update`, `remove`.
5.  **Update Renderer (`App.tsx`):** Add a `case` in `renderModules`.
6.  **Update Python Library:** Create a corresponding class (`libs/python/src/sidekick/`).

## 9. Troubleshooting

*   **WebSocket Issues:** Check backend logs, browser console, firewall, URL (`ws://localhost:5163`).
*   **UI Not Updating:** Verify messages, `target` IDs. Ensure reducer applies updates immutably. Use React DevTools.
*   **Viz Highlighting:** Check `path` data, `lastChanges` state, path comparison logic, CSS animation.
*   **Canvas Drawing:** Ensure unique `commandId`s, check console for errors, verify `lastProcessedCommandId` logic.
*   **Control Issues:** Verify `control_id` uniqueness within a module. Check `notify` payload sent on interaction. Ensure reducer correctly adds/removes controls.
*   **Build Errors:** Address TypeScript errors (`npm run build`). Check types/imports.