# Sidekick Web Application

## 1. Overview

This directory contains the frontend React application for the Sidekick Visual Coding Buddy. Its primary responsibility is to:

1.  Establish a WebSocket connection to the Sidekick server (potentially part of the VS Code extension or a standalone server).
2.  Receive commands from the "Hero" (user's script, via the server) to `spawn`, `update`, or `remove` visual modules.
3.  Maintain the state for each active visual module instance (`Grid`, `Console`, `Viz`, `Canvas`).
4.  Render the appropriate React components for each module based on its current state.
5.  Send user interaction events (like grid clicks or console input) back to the Hero via the WebSocket connection.

This web application is typically embedded within a VS Code Webview (managed by the `Sidekick/extension/` component) but can be run independently using Vite's development server for UI development.

## 2. Tech Stack

*   **Framework:** React (functional components, hooks like `useReducer`, `useCallback`, `useMemo`)
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
│   ├── components/     # React components (GridModule, ConsoleModule, VizModule, CanvasModule)
│   │   ├── GridModule.css
│   │   ├── GridModule.tsx
│   │   ├── ConsoleModule.css
│   │   ├── ConsoleModule.tsx
│   │   ├── VizModule.css
│   │   ├── VizModule.tsx
│   │   ├── CanvasModule.css
│   │   ├── CanvasModule.tsx
│   │   └── ...
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
*   `src/types/index.ts` defines the `ModuleInstance` discriminated union and specific state types (`GridState`, `ConsoleState`, `VizState`, etc.).
*   The `moduleReducer` function in `App.tsx` processes incoming `HeroMessage` actions:
    *   **`spawn`:** Creates a new entry in the state map with the initial state for the specified module type.
    *   **`update`:** Finds the existing module instance by `target` ID.
        *   For `Viz`, it handles detailed variable updates (based on `change_type`, `path`, `value_representation`, etc.) using immutable helpers (`updateRepresentationAtPath`) and updates `lastChanges` for highlighting. Variable removal is handled via `change_type: "remove_variable"`.
        *   For `Canvas`, it **appends** new draw commands received in the payload to the `commandQueue` array within the module's state.
        *   For other modules (`Grid`, `Console`), it updates their state based on the specific payload.
    *   **`remove`:** Deletes the module instance entry from the map.
*   State updates are immutable, ensuring React re-renders correctly. State flows down as props to the individual module components.

### 4.3. Module Rendering (`App.tsx`, `*Module.tsx`)

*   `App.tsx` iterates through the `modules` state map.
*   A `switch` statement based on `module.type` renders the appropriate component (`GridModule`, `ConsoleModule`, `VizModule`, `CanvasModule`).
*   Each module component receives its `id` and specific `state` object as props.
*   Interactive modules (`GridModule`, `ConsoleModule`) receive an `onInteraction` prop function to send `notify` messages back up via the WebSocket.

### 4.4. `GridModule`

*   Renders an interactive grid based on the `GridState` (size, cell colors/text).
*   Handles click events on cells and calls `onInteraction` with a `notify` payload containing click coordinates (`{ event: "click", x: ..., y: ... }`).

### 4.5. `ConsoleModule`

*   Displays lines of text from `state.lines`.
*   Includes an input field and "Send" button for user input.
*   Handles user input submission (Enter key or button click) and calls `onInteraction` with a `notify` payload containing the submitted text (`{ event: 'submit', value: ... }`).

### 4.6. `VizModule` & `RenderValue`

*   Displays variables stored in `state.variables`.
*   Uses the recursive `RenderValue` component (`src/components/VizModule.tsx`) to display potentially complex/nested data structures defined by the `VizRepresentation` type.
*   `RenderValue` recursively builds the display, passing down the `currentPath` (an array of keys/indices) representing its position within the variable's structure.
*   **Highlighting:** Applies a temporary highlight animation to the specific data node whose path matches the `path` recorded in the `state.lastChanges` object for that variable, ensuring users see precisely what changed. Uses a dynamic `key` prop to re-trigger animations correctly.
*   Provides expand/collapse controls for viewing nested structures.
*   Applies specific styling based on data type (`viz-type-*`) and whether the value originated from an `ObservableValue` (`observable-tracked` class for the light blue background).

### 4.7. `CanvasModule`

*   Renders an HTML5 `<canvas>` element based on `state.width` and `state.height`.
*   Receives drawing instructions via the `state.commandQueue` array in its props.
*   Uses `useEffect` hooks and internal logic (including tracking the ID of the **last processed command** with `useRef`) to manage the 2D rendering context (`ctx`).
*   Processes the `commandQueue` **incrementally**, executing only commands that have arrived since the last processed one, ensuring they are drawn in the correct order.
*   This queue and tracking mechanism ensures that even rapidly received commands are drawn accurately **without loss or duplication**.
*   Supported commands include `clear`, `config`, `line`, `rect`, `circle`.

## 5. Setup & Development

1.  **Navigate:** `cd Sidekick/webapp`
2.  **Install:** `npm install` (or `yarn install`)
3.  **Run Dev Server:** `npm run dev` (or `yarn dev`)
4.  **Connect:** Open the provided URL (e.g., `http://localhost:5173`). For full functionality, ensure the corresponding Sidekick backend (e.g., the VS Code extension providing the WebSocket server at `ws://localhost:5163`) is running.

## 6. Build Process

*   **Command:** `npm run build` (or `yarn build`)
*   **Output:** Static files generated in `webapp/dist`.
*   **Serving:** These static files are typically served by the VS Code extension's Webview or potentially a standalone server in production/distribution scenarios.

## 7. Styling

*   Global styles: `src/App.css`.
*   Component styles: Co-located CSS files (e.g., `src/components/VizModule.css`), imported directly into the corresponding `.tsx` file. Uses standard CSS conventions.

## 8. Adding a New Visual Module

1.  **Define Protocol:** Specify message payloads for the new module in `PROTOCOL.md`.
2.  **Define Types:** Add state/instance types in `src/types/index.ts`.
3.  **Create Component:** Build the React component (`src/components/MyNewModule.tsx`) and its CSS (`MyNewModule.css`).
4.  **Update Reducer (`App.tsx`):** Add logic for `spawn`, `update`, `remove` for the new module type within the `moduleReducer`. If complex state updates are needed, consider adding helpers in `src/utils/`.
5.  **Update Renderer (`App.tsx`):** Add a `case` in the `renderModules` function to render the new component.
6.  **Update Python Library:** Create a corresponding class in the Python `sidekick` library (`libs/python/src/sidekick/`) to send the necessary commands.

## 9. Troubleshooting

*   **WebSocket Issues:** Check backend logs (e.g., VS Code Extension Output channel), browser console, and firewall settings. Ensure the connection URL (`ws://localhost:5163` by default) is correct.
*   **UI Not Updating:** Verify messages in backend/browser consoles. Check `target` IDs match. Ensure the `moduleReducer` correctly processes the message and creates *new* state objects/arrays (immutability) for updates. Debug component props and rendering logic using React DevTools.
*   **Viz Highlighting Issues:** Check the `path` being sent from Python and received in the reducer. Verify the `lastChanges` state in React DevTools. Ensure the `pathsAreEqual` comparison in `RenderValue` works as expected. Confirm the CSS animation (`viz-highlight-node`) is correctly defined and applied.
*   **Canvas Drawing Issues:** Ensure `commandId`s are unique. Check the browser console for drawing errors. Verify the `lastProcessedCommandId` logic in `CanvasModule.tsx` is correctly identifying new commands. Ensure the reducer is correctly appending to the `commandQueue`.
*   **Build Errors:** Address TypeScript errors reported by `npm run build`. Check type definitions (`src/types/index.ts`) and ensure imports are correct.