# Sidekick Web Application

## 1. Overview

This directory contains the frontend React application for the Sidekick Visual Coding Buddy. Its primary responsibility is to:

1.  Establish a WebSocket connection to the Sidekick server (Node.js backend).
2.  Receive commands from the "Hero" (user's script, via the server) to spawn, update, or remove visual modules.
3.  Maintain the state for each active visual module instance (`Grid`, `Console`, `Viz`, `Canvas`).
4.  Render the appropriate React components for each module based on its current state.
5.  Send user interaction events (like grid clicks or console input) back to the Hero via the WebSocket connection.

This web application is hosted by the accompanying Node.js server (`Sidekick/server/`) but can be run independently using Vite's development server.

## 2. Tech Stack

*   **Framework:** React (functional components, hooks)
*   **Language:** TypeScript
*   **Build Tool:** Vite
*   **Styling:** Standard CSS (per-component files)
*   **WebSocket:** Native browser WebSocket API (managed via `useWebSocket` hook)
*   **State Management:** `useReducer` hook in `App.tsx` for centralized module state.

## 3. Project Structure

```
webapp/
├── public/             # Static assets served directly by Vite/server
├── src/                # Main source code directory
│   ├── components/     # React components (GridModule, ConsoleModule, VizModule, CanvasModule)
│   │   ├── GridModule.css
│   │   ├── GridModule.tsx
│   │   ├── ConsoleModule.css
│   │   ├── ConsoleModule.tsx
│   │   ├── VizModule.css
│   │   ├── VizModule.tsx
│   │   ├── CanvasModule.css
│   │   ├── CanvasModule.tsx
│   │   └── ... (potential shared sub-components like RenderValue for Viz)
│   ├── hooks/          # Custom React hooks (useWebSocket.ts)
│   ├── types/          # Shared TypeScript type definitions (index.ts)
│   ├── App.css         # Global application styles
│   ├── App.tsx         # Main application component (state mgmt, message routing)
│   ├── index.css       # Vite default global styles
│   └── main.tsx        # Application entry point
├── index.html          # HTML entry point for Vite
├── package.json        # Project dependencies and scripts
├── tsconfig.json       # TypeScript configuration
├── tsconfig.node.json  # TypeScript config for Vite config file
└── vite.config.ts      # Vite build and dev server configuration
```

## 4. Core Concepts

### 4.1. WebSocket Communication (`useWebSocket` hook)

*   Located in `src/hooks/useWebSocket.ts`.
*   Manages the persistent WebSocket connection to `ws://localhost:5163` (default).
*   Handles connection lifecycle (open, close, error) and status (`isConnected`).
*   Parses incoming JSON messages and invokes the `handleWebSocketMessage` callback provided by `App.tsx`.
*   Exports a `sendMessage` function used by `App.tsx` (via `handleModuleInteraction`) to send JSON-formatted messages (like `notify` events) back to the server/Hero.

### 4.2. State Management (`App.tsx` with `useReducer`)

*   The central state (`Map<string, ModuleInstance>`) holds all active module instances, keyed by their unique `instance_id`.
*   `src/types/index.ts` defines the `ModuleInstance` discriminated union (`GridModuleInstance`, `ConsoleModuleInstance`, etc.) and specific state types (`GridState`, `ConsoleState`, etc.).
*   The `moduleReducer` function in `App.tsx` processes incoming `HeroMessage` actions:
    *   **`spawn`:** Creates a new entry in the map with the initial state for the specified module type.
    *   **`update`:** Finds the existing module instance by `target` ID, determines its type, and updates its `state` based on the message `payload`. Ensures immutability for React state updates.
    *   **`remove`:** Deletes the module instance entry from the map.
    *   **`remove_var`:** Specific to `viz`, removes a variable entry from the `VizState.variables` map.
*   State updates flow down as props to the individual module components.

### 4.3. Module Rendering (`App.tsx`, `*Module.tsx`)

*   `App.tsx` iterates through the `modules` state map.
*   A `switch` statement based on `module.type` renders the appropriate component (`GridModule`, `ConsoleModule`, `VizModule`, `CanvasModule`).
*   Each module component receives its `id` and specific `state` object as props.
*   Interactive modules (`GridModule`, `ConsoleModule`) receive an `onInteraction` prop to send `notify` messages back up.

### 4.4. `GridModule`

*   Renders an interactive grid based on the `GridState` (size, cell colors/text).
*   Handles click events on cells and calls `onInteraction` with a `notify` payload containing click coordinates.

### 4.5. `ConsoleModule`

*   Displays lines of text from `state.lines`.
*   Includes an input field and "Send" button for user input.
*   Handles user input submission (Enter key or button click) and calls `onInteraction` with a `notify` payload containing the submitted text (`{ event: 'submit', value: ... }`).

### 4.6. `VizModule` & `RenderValue`

*   Displays variables stored in `state.variables`.
*   Uses the recursive `RenderValue` component to display potentially complex/nested data structures defined by the `VizRepresentation` type (including primitives, lists, sets, dicts with typed keys, objects).
*   `RenderValue` provides expand/collapse controls and applies styling based on type and the `observable_tracked` flag.
*   Applies highlight animations based on `changeInfo` derived from `VizState.lastChanges`.

### 4.7. `CanvasModule`

*   Renders an HTML5 `<canvas>` element based on `state.width` and `state.height`.
*   Uses `useEffect` hooks to manage the 2D rendering context and execute drawing commands received via `state.lastCommand`. Supports commands like `clear`, `config`, `line`, `rect`, `circle`.

## 5. Setup & Development

1.  **Navigate:** `cd Sidekick/webapp`
2.  **Install:** `npm install` (or `yarn install`)
3.  **Run:** `npm run dev` (or `yarn dev`)
4.  **Connect:** Open the provided URL (e.g., `http://localhost:5173`). Ensure the backend server (`Sidekick/server/`) is running.

## 6. Build Process

*   **Command:** `npm run build` (or `yarn build`)
*   **Output:** Static files generated in `webapp/dist`.
*   **Serving:** The Node.js server (`Sidekick/server/`) serves these files in production.

## 7. Styling

*   Global styles: `src/App.css`.
*   Component styles: Co-located CSS files (e.g., `src/components/GridModule.css`), imported directly into the corresponding `.tsx` file.

## 8. Adding a New Visual Module

1.  **Define Protocol:** Specify message payloads for the new module in `PROTOCOL.md`.
2.  **Define Types:** Add state/instance types in `src/types/index.ts`.
3.  **Create Component:** Build the React component (`src/components/MyModule.tsx`) and CSS.
4.  **Update Reducer (`App.tsx`):** Add logic for `spawn`, `update`, etc., for the new module type.
5.  **Update Renderer (`App.tsx`):** Add a `case` in `renderModules`.
6.  **Update Python Library:** Create a corresponding class in the Python `sidekick` library.

## 9. Troubleshooting

*   **WebSocket Issues:** Check server logs (`Sidekick/server/`), browser console, firewall settings. Default port is `5163`.
*   **UI Not Updating:** Verify messages in server/browser consoles. Check `target` IDs. Ensure the `moduleReducer` creates new state objects/arrays for updates. Debug component props and rendering logic.
*   **Build Errors:** Address TypeScript errors reported by `npm run build`. Check type definitions and imports.
*   **Canvas Issues:** Ensure valid commands/options are sent. Check browser console for canvas context errors.