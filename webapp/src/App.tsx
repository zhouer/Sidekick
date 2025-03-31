// Sidekick/webapp/src/App.tsx
import { useCallback, useReducer } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import {
  // Message types
  HeroMessage,
  SidekickMessage,
  // Module instance union and specific state types
  ModuleInstance,
  GridState,
  ConsoleState,
  VizState,
  CanvasState,
  ControlState, // <-- ADDED
  // Specific payload types
  CanvasSpawnPayload,
  CanvasUpdatePayload,
  CanvasDrawCommand,
  VizUpdatePayload,
  ControlUpdatePayload, // <-- ADDED
  ControlDefinition // <-- ADDED
} from './types';
import { updateRepresentationAtPath } from './utils/stateUtils'; // Helper for Viz state updates
// Import all module components
import GridModule from './components/GridModule';
import ConsoleModule from './components/ConsoleModule';
import VizModule from './components/VizModule';
import CanvasModule from './components/CanvasModule';
import ControlModule from './components/ControlModule'; // <-- ADDED
import './App.css'; // Global styles

// Define the type for actions dispatched to the reducer
type ModuleAction =
    | { type: 'PROCESS_MESSAGE'; message: HeroMessage } // Action for incoming Hero messages
    | { type: 'CLEAR_ALL' };                         // Action to remove all modules

/**
 * Reducer function managing the state of all Sidekick modules.
 * It takes the current state map and an action, returning the new state map.
 * Ensures immutability: always returns a new Map instance on changes.
 */
function moduleReducer(state: Map<string, ModuleInstance>, action: ModuleAction): Map<string, ModuleInstance> {
  // Create a mutable copy for this update cycle.
  const newModules = new Map(state);

  switch (action.type) {
      // Handle incoming messages from the Hero script
    case 'PROCESS_MESSAGE': {
      const message = action.message;
      // Validate basic message structure
      if (!message || !message.method || !message.target || !message.module) {
        console.warn("Reducer: Received incomplete message:", message);
        return state; // Return original state if invalid
      }
      const { module: moduleType, method, target, payload } = message;

      // Process based on the message method (spawn, update, remove)
      switch (method) {
          // --- Handle 'spawn': Create a new module ---
        case 'spawn': {
          if (newModules.has(target)) { // Prevent duplicates
            console.warn(`Reducer: ${moduleType} Spawn failed: Duplicate ID "${target}"`);
            return state;
          }
          // Initialize state based on module type
          if (moduleType === 'grid') {
            const p = payload as { size?: [number, number] };
            newModules.set(target, { id: target, type: 'grid', state: { size: p?.size || [10, 10], cells: {} } });
          } else if (moduleType === 'console') {
            const p = payload as { text?: string };
            newModules.set(target, { id: target, type: 'console', state: { lines: p?.text ? [p.text] : [] } });
          } else if (moduleType === 'viz') {
            newModules.set(target, { id: target, type: 'viz', state: { variables: {}, lastChanges: {} } });
          } else if (moduleType === 'canvas') {
            const p = payload as CanvasSpawnPayload;
            if (!p || !p.width || !p.height) { console.error(`Reducer: Canvas Spawn failed: Invalid payload for "${target}"`, p); return state; }
            newModules.set(target, { id: target, type: 'canvas', state: { width: p.width, height: p.height, bgColor: p.bgColor || '#FFFFFF', commandQueue: [] } });
          } else if (moduleType === 'control') { // <-- ADD 'control' spawn
            newModules.set(target, { id: target, type: 'control', state: { controls: new Map() } }); // Initialize with empty controls map
          } else {
            console.warn(`Reducer: Spawn failed: Unknown module type "${moduleType}"`);
            return state;
          }
          console.log(`Reducer: Spawned module: ${target} (${moduleType})`);
          break;
        }

          // --- Handle 'update': Modify an existing module ---
        case 'update': {
          const currentModule = newModules.get(target);
          if (!currentModule) { // Ensure module exists
            console.warn(`Reducer: Update failed: Module "${target}" not found.`);
            return state;
          }

          // Apply updates based on module type
          if (currentModule.type === 'grid') {
            const gridUpdate = payload as { x?: number; y?: number; color?: string | null; text?: string | null; fill_color?: string };
            const currentState = currentModule.state as GridState; const updatedCells = { ...currentState.cells }; // New cells object
            if (gridUpdate.fill_color !== undefined) { for (let y = 0; y < currentState.size[1]; y++) for (let x = 0; x < currentState.size[0]; x++) updatedCells[`${x},${y}`] = { ...(updatedCells[`${x},${y}`] || {}), color: gridUpdate.fill_color }; }
            else if (gridUpdate.x !== undefined && gridUpdate.y !== undefined) { const key = `${gridUpdate.x},${gridUpdate.y}`; updatedCells[key] = { color: gridUpdate.color !== undefined ? gridUpdate.color : currentState.cells[key]?.color, text: gridUpdate.text !== undefined ? gridUpdate.text : currentState.cells[key]?.text }; }
            else { return state; } // Invalid payload
            newModules.set(target, { ...currentModule, state: { ...currentState, cells: updatedCells } }); // Update with new state

          } else if (currentModule.type === 'console') {
            const consoleUpdate = payload as { text?: string; clear?: boolean };
            const currentState = currentModule.state as ConsoleState; let updatedLines = currentState.lines;
            if (consoleUpdate.clear === true) { updatedLines = []; } // New empty array
            else if (consoleUpdate.text !== undefined) { updatedLines = [...currentState.lines, consoleUpdate.text]; } // New array with appended line
            newModules.set(target, { ...currentModule, state: { lines: updatedLines } }); // Update with new state

          } else if (currentModule.type === 'canvas') {
            const canvasUpdate = payload as CanvasUpdatePayload;
            if (!canvasUpdate || !canvasUpdate.command || !canvasUpdate.options) { console.warn(`Reducer: Invalid canvas update payload for "${target}":`, payload); return state; }
            const currentState = currentModule.state as CanvasState;
            const newCommand: CanvasDrawCommand = { ...canvasUpdate, commandId: canvasUpdate.commandId || `${Date.now()}-${Math.random()}` };
            const updatedQueue = [...currentState.commandQueue, newCommand]; // New array with appended command
            newModules.set(target, { ...currentModule, state: { ...currentState, commandQueue: updatedQueue } }); // Update with new state

          } else if (currentModule.type === 'viz') {
            const vizPayload = payload as VizUpdatePayload;
            if (!vizPayload || !vizPayload.variable_name || !vizPayload.change_type || !vizPayload.path) { console.warn("Reducer: Invalid viz update payload:", payload); return state; }
            const currentState = currentModule.state as VizState;
            const { variable_name, change_type, path } = vizPayload;
            let newVariablesState = { ...currentState.variables }; // New variables object
            let variableRemoved = false;
            if (change_type === 'remove_variable') { if (newVariablesState[variable_name]) { delete newVariablesState[variable_name]; variableRemoved = true; console.log(`Reducer: Viz removed variable: ${target}/${variable_name}`); } else { return state; } }
            else if (newVariablesState[variable_name]) { try { newVariablesState[variable_name] = updateRepresentationAtPath( currentState.variables[variable_name], vizPayload ); } catch (e) { console.error(`Reducer: Error applying viz update for ${variable_name} path ${path}:`, e); return state; } }
            else { if (change_type === 'set' && path.length === 0 && vizPayload.value_representation) { newVariablesState[variable_name] = vizPayload.value_representation; console.log(`Reducer: Viz created variable via 'set' update: ${target}/${variable_name}`); } else { console.warn(`Reducer: Viz update failed: Variable ${variable_name} not found for change type ${change_type}.`); return state; } }
            const newLastChanges = { ...currentState.lastChanges }; // New lastChanges object
            if (variableRemoved) { delete newLastChanges[variable_name]; } else { newLastChanges[variable_name] = { change_type: change_type, path: path, timestamp: Date.now() }; }
            newModules.set(target, { ...currentModule, state: { variables: newVariablesState, lastChanges: newLastChanges } }); // Update with new state

          } else if (currentModule.type === 'control') { // <-- ADD 'control' update
            const controlPayload = payload as ControlUpdatePayload;
            if (!controlPayload || !controlPayload.operation || !controlPayload.control_id) { console.warn(`Reducer: Invalid control update payload for "${target}":`, payload); return state; }
            const currentState = currentModule.state as ControlState;
            const updatedControls = new Map(currentState.controls); // Create new Map for controls
            if (controlPayload.operation === 'add') { // Handle adding a control
              if (!controlPayload.control_type || !controlPayload.config) { console.warn(`Reducer: Invalid 'add' control payload (missing type or config):`, payload); return state; }
              const newControlDef: ControlDefinition = { id: controlPayload.control_id, type: controlPayload.control_type, config: controlPayload.config || {} };
              updatedControls.set(controlPayload.control_id, newControlDef);
              console.log(`Reducer: Control ${target}: Added control ${controlPayload.control_id}`);
            } else if (controlPayload.operation === 'remove') { // Handle removing a control
              if (updatedControls.has(controlPayload.control_id)) { updatedControls.delete(controlPayload.control_id); console.log(`Reducer: Control ${target}: Removed control ${controlPayload.control_id}`); }
              else { console.warn(`Reducer: Control ${target}: Control ID ${controlPayload.control_id} not found for removal.`); return state; }
            } else { console.warn(`Reducer: Control ${target}: Unknown operation ${controlPayload.operation}`); return state; }
            newModules.set(target, { ...currentModule, state: { controls: updatedControls } }); // Update with new state
          }
          //--------------------------------------------------
          else {
            console.warn(`Reducer: Update failed: Unknown module type encountered for target "${target}":`, currentModule);
            return state;
          }
          break; // End 'update' case
        }

          // --- Handle 'remove': Delete a module instance ---
        case 'remove': {
          if (!newModules.has(target)) { return state; } // Ignore if already removed
          newModules.delete(target);
          console.log(`Reducer: Removed module: ${target}`);
          break; // End 'remove' case
        }

        default:
          console.warn('Reducer: Received unknown method:', method);
          return state;
      } // end inner switch (method)
      // Return the (potentially) modified map
      return newModules;
    } // end case 'PROCESS_MESSAGE'

      // --- Handle 'CLEAR_ALL': Remove all modules ---
    case 'CLEAR_ALL': {
      console.log("Reducer: Clearing all modules");
      return new Map<string, ModuleInstance>(); // Return a new empty map
    }

    default:
      // If action type is unknown, return current state
      return state;
  } // end outer switch (action.type)
}


/**
 * Main Application Component.
 * Manages WebSocket connection, module state via reducer, and renders modules.
 */
function App() {
  // Setup state management with useReducer
  const [modules, dispatchModules] = useReducer(moduleReducer, new Map<string, ModuleInstance>());

  // Callback for WebSocket hook to process incoming messages
  const handleWebSocketMessage = useCallback((messageData: any) => {
    if (typeof messageData === 'object' && messageData !== null) {
      dispatchModules({ type: 'PROCESS_MESSAGE', message: messageData as HeroMessage });
    } else { console.error("App: Received non-object message from WebSocket:", messageData); }
  }, []); // dispatchModules is stable

  // Initialize WebSocket connection
  const { isConnected, sendMessage } = useWebSocket(handleWebSocketMessage);

  // Callback passed to interactive modules to send messages back to Hero
  const handleModuleInteraction = useCallback((interactionMessage: SidekickMessage) => {
    console.log("App: Sending interaction to Hero:", interactionMessage);
    sendMessage(interactionMessage);
  }, [sendMessage]); // Depends on sendMessage from useWebSocket

  // Callback for the Clear All button
  const clearAllModules = useCallback(() => {
    dispatchModules({ type: 'CLEAR_ALL' });
  }, []); // dispatchModules is stable

  // Function to render the appropriate component for each active module
  const renderModules = () => {
    return Array.from(modules.values()).map(module => {
      switch (module.type) {
        case 'grid': return <GridModule key={module.id} id={module.id} state={module.state as GridState} onInteraction={handleModuleInteraction} />;
        case 'console': return <ConsoleModule key={module.id} id={module.id} state={module.state as ConsoleState} onInteraction={handleModuleInteraction} />;
        case 'viz': return <VizModule key={module.id} id={module.id} state={module.state as VizState} />;
        case 'canvas': return <CanvasModule key={module.id} id={module.id} state={module.state as CanvasState} />;
        case 'control': return <ControlModule key={module.id} id={module.id} state={module.state as ControlState} onInteraction={handleModuleInteraction} />; // <-- ADD control case
        default: console.error("App: Attempting to render unknown module type:", module); return null;
      }
    });
  };

  // Main component layout
  return (
      <div className="App">
        <header className="App-header">
          <h1>Sidekick</h1>
          <p>WebSocket: {isConnected ? 'Connected' : 'Disconnected'}</p>
          <button onClick={clearAllModules}>Clear All</button>
        </header>
        <main className="App-main">
          {/* Render all modules based on the current state */}
          {renderModules()}
        </main>
      </div>
  );
}

export default App;