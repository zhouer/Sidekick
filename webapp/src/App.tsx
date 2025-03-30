// Sidekick/webapp/src/App.tsx
import { useCallback, useReducer } from 'react'; // React import needed for JSX
import { useWebSocket } from './hooks/useWebSocket';
import {
  HeroMessage,        // Message from Python Hero
  ModuleInstance,     // Union type for any module instance state
  GridState,          // Specific state types
  ConsoleState,
  VizState,
  CanvasState,
  SidekickMessage,    // Message to Python Hero
  CanvasSpawnPayload, // Specific payload types
  CanvasUpdatePayload,
  CanvasDrawCommand,
  VizUpdatePayload
} from './types';
import { updateRepresentationAtPath } from './utils/stateUtils'; // Helper for immutable Viz updates
import GridModule from './components/GridModule';             // Module components
import ConsoleModule from './components/ConsoleModule';
import VizModule from './components/VizModule';
import CanvasModule from './components/CanvasModule';
import './App.css'; // Global styles

// Define the type for actions dispatched to the reducer
type ModuleAction =
    | { type: 'PROCESS_MESSAGE'; message: HeroMessage } // Action to handle incoming messages
    | { type: 'CLEAR_ALL' };                         // Action to remove all modules

/**
 * Reducer function to manage the state of all active Sidekick modules.
 * Takes the current state (Map of module ID -> module instance) and an action,
 * returns the new state map. State updates MUST be immutable.
 * @param state - The current Map of module instances.
 * @param action - The action to process.
 * @returns The new state Map.
 */
function moduleReducer(state: Map<string, ModuleInstance>, action: ModuleAction): Map<string, ModuleInstance> {
  // Create a mutable copy of the state map for this update cycle.
  // The function will return this new map (or the original state if no changes).
  const newModules = new Map(state);

  switch (action.type) {
      // Handle incoming messages from the Hero (Python script)
    case 'PROCESS_MESSAGE': {
      const message = action.message;
      // Basic validation of the incoming message structure
      if (!message || !message.method || !message.target || !message.module) {
        console.warn("Received incomplete message:", message);
        return state; // Return original state if message is invalid
      }
      const { module: moduleType, method, target, payload } = message;

      // Handle different methods (spawn, update, remove)
      switch (method) {
          // --- Handle 'spawn': Create a new module instance ---
        case 'spawn': {
          // Prevent spawning if a module with the same ID already exists
          if (newModules.has(target)) {
            console.warn(`${moduleType} Spawn failed: Duplicate target ID "${target}"`);
            return state;
          }
          // Create initial state based on module type and payload
          if (moduleType === 'grid') {
            const gridPayload = payload as { size?: [number, number] };
            const initialState: GridState = { size: gridPayload?.size || [10, 10], cells: {} };
            newModules.set(target, { id: target, type: 'grid', state: initialState });
          } else if (moduleType === 'console') {
            const consolePayload = payload as { text?: string };
            const initialState: ConsoleState = { lines: consolePayload?.text ? [consolePayload.text] : [] };
            newModules.set(target, { id: target, type: 'console', state: initialState });
          } else if (moduleType === 'viz') {
            // Viz module starts empty, variables are added via 'update' messages
            const initialState: VizState = { variables: {}, lastChanges: {} };
            newModules.set(target, { id: target, type: 'viz', state: initialState });
          } else if (moduleType === 'canvas') {
            const canvasPayload = payload as CanvasSpawnPayload;
            if (!canvasPayload || !canvasPayload.width || !canvasPayload.height) {
              console.error(`Canvas Spawn failed: Invalid payload for target "${target}"`, payload);
              return state;
            }
            // Initialize with empty command queue
            const initialState: CanvasState = {
              width: canvasPayload.width,
              height: canvasPayload.height,
              bgColor: canvasPayload.bgColor || '#FFFFFF',
              commandQueue: [] // Start with an empty queue
            };
            newModules.set(target, { id: target, type: 'canvas', state: initialState });
          } else {
            console.warn(`Spawn failed: Unknown module type "${moduleType}"`);
            return state;
          }
          console.log(`Spawned module: ${target} (${moduleType})`);
          break; // End 'spawn' case
        }

          // --- Handle 'update': Modify an existing module instance ---
        case 'update': {
          const currentModule = newModules.get(target);
          // Ensure the module exists before trying to update it
          if (!currentModule) {
            console.warn(`Update failed: Module with ID "${target}" not found.`);
            return state;
          }

          // Apply updates based on the module type
          if (currentModule.type === 'grid') {
            const gridUpdate = payload as { x?: number; y?: number; color?: string | null; text?: string | null; fill_color?: string };
            const currentState = currentModule.state as GridState;
            // Create a new cells object for immutability
            const updatedCells = { ...currentState.cells };
            if (gridUpdate.fill_color !== undefined) { // Handle fill operation
              for (let y = 0; y < currentState.size[1]; y++) {
                for (let x = 0; x < currentState.size[0]; x++) {
                  updatedCells[`${x},${y}`] = { ...(updatedCells[`${x},${y}`] || {}), color: gridUpdate.fill_color };
                }
              }
            } else if (gridUpdate.x !== undefined && gridUpdate.y !== undefined) { // Handle single cell update
              const key = `${gridUpdate.x},${gridUpdate.y}`;
              updatedCells[key] = {
                // Use new value if provided, otherwise keep existing
                color: gridUpdate.color !== undefined ? gridUpdate.color : currentState.cells[key]?.color,
                text: gridUpdate.text !== undefined ? gridUpdate.text : currentState.cells[key]?.text,
              };
            } else { return state; } // Invalid payload for grid update
            // Update the module state with the new cells object
            newModules.set(target, { ...currentModule, state: { ...currentState, cells: updatedCells } });

          } else if (currentModule.type === 'console') {
            const consoleUpdate = payload as { text?: string; clear?: boolean };
            const currentState = currentModule.state as ConsoleState;
            let updatedLines = currentState.lines;
            if (consoleUpdate.clear === true) { // Handle clear operation
              updatedLines = [];
            } else if (consoleUpdate.text !== undefined) { // Handle append operation
              // Create a new lines array for immutability
              updatedLines = [...currentState.lines, consoleUpdate.text];
            }
            // Update the module state with the new lines array
            newModules.set(target, { ...currentModule, state: { lines: updatedLines } });

          } else if (currentModule.type === 'canvas') {
            const canvasUpdate = payload as CanvasUpdatePayload; // Use the base command type
            if (!canvasUpdate || !canvasUpdate.command || !canvasUpdate.options) {
              console.warn(`Invalid canvas update payload for target "${target}":`, payload);
              return state;
            }
            const currentState = currentModule.state as CanvasState;

            // Create a unique ID for the command (important for queue processing)
            const newCommand: CanvasDrawCommand = {
              ...canvasUpdate,
              commandId: canvasUpdate.commandId || `${Date.now()}-${Math.random()}` // Generate ID if missing
            };

            // --- CHANGE: Append command to the queue ---
            // Create a new queue array with the appended command for immutability
            const updatedQueue = [...currentState.commandQueue, newCommand];
            // Update the module state with the new command queue
            newModules.set(target, {
              ...currentModule,
              state: { ...currentState, commandQueue: updatedQueue }
            });
            // -------------------------------------------

          } else if (currentModule.type === 'viz') {
            const vizPayload = payload as VizUpdatePayload;
            if (!vizPayload || !vizPayload.variable_name || !vizPayload.change_type || !vizPayload.path) {
              console.warn("Invalid viz update payload:", payload); return state;
            }
            const currentState = currentModule.state as VizState;
            const { variable_name, change_type, path } = vizPayload;
            // Create new state objects for immutability
            let newVariablesState = { ...currentState.variables };
            let variableRemoved = false;

            // Handle removing the entire variable
            if (change_type === 'remove_variable') {
              if (newVariablesState[variable_name]) {
                delete newVariablesState[variable_name]; // Remove from variables map
                variableRemoved = true;
                console.log(`Viz removed variable: ${target}/${variable_name}`);
              } else { return state; } // Variable already removed, no change
            }
            // Handle updates to existing variables
            else if (newVariablesState[variable_name]) {
              try {
                // Use the immutable update helper function
                newVariablesState[variable_name] = updateRepresentationAtPath(
                    currentState.variables[variable_name], // Current representation
                    vizPayload // Full details of the change
                );
              } catch (e) {
                console.error(`Error applying viz update for ${variable_name} path ${path}:`, e);
                return state; // Revert to old state on error
              }
            } else {
              // Handle adding a *new* variable (only via 'set' type)
              if (change_type === 'set' && path.length === 0 && vizPayload.value_representation) {
                newVariablesState[variable_name] = vizPayload.value_representation; // Assume it's already cloned if needed
                console.log(`Viz created variable via 'set' update: ${target}/${variable_name}`);
              } else {
                // Ignore updates to non-existent variables unless it's the initial 'set'
                console.warn(`Viz update failed: Variable ${variable_name} not found for change type ${change_type}.`);
                return state;
              }
            }

            // --- Update lastChanges state for highlighting ---
            // Create a new lastChanges object for immutability
            const newLastChanges = { ...currentState.lastChanges };
            if (variableRemoved) {
              // If variable removed, delete its entry from lastChanges
              delete newLastChanges[variable_name];
            } else {
              // Otherwise, update/add the entry with new change info
              newLastChanges[variable_name] = {
                change_type: change_type,
                path: path, // Store the path that was changed
                timestamp: Date.now() // Record when the change was processed
              };
            }
            // --------------------------------------------------

            // Update the module state with new variables and lastChanges
            newModules.set(target, { ...currentModule, state: { variables: newVariablesState, lastChanges: newLastChanges } });

          } else {
            // Should not happen if types are correct
            console.warn(`Update failed: Unknown module type encountered for target "${target}":`, currentModule);
            return state;
          }
          break; // End 'update' case
        }

          // --- Handle 'remove': Delete a module instance ---
        case 'remove': {
          if (!newModules.has(target)) { return state; } // Ignore if already removed
          newModules.delete(target); // Remove the module from the map
          console.log(`Removed module: ${target}`);
          break; // End 'remove' case
        }

        default:
          // Handle any unknown methods received from the Hero
          console.warn('Received unknown method:', method);
          return state;
      } // end inner switch (method)
      // Return the potentially modified map
      return newModules;
    } // end case 'PROCESS_MESSAGE'

      // --- Handle 'CLEAR_ALL': Remove all modules ---
    case 'CLEAR_ALL': {
      console.log("Clearing all modules");
      return new Map<string, ModuleInstance>(); // Return a new, empty map
    }

    default:
      // If the action type is unknown, return the current state unmodified
      return state;
  } // end outer switch (action.type)
}


/**
 * Main Application Component.
 * Manages WebSocket connection, module state via reducer, and renders modules.
 */
function App() {
  // Initialize module state with an empty Map using useReducer
  const [modules, dispatchModules] = useReducer(moduleReducer, new Map<string, ModuleInstance>());

  // Callback function passed to useWebSocket hook to handle incoming messages
  const handleWebSocketMessage = useCallback((messageData: any) => {
    // Basic check to ensure the received data is a valid object
    if (typeof messageData === 'object' && messageData !== null) {
      // Dispatch the message to the reducer for processing
      dispatchModules({ type: 'PROCESS_MESSAGE', message: messageData as HeroMessage });
    } else {
      console.error("Received non-object message from WebSocket:", messageData);
    }
    // dispatchModules is stable, so dependency array is empty
  }, []);

  // Setup WebSocket connection using the custom hook
  const { isConnected, sendMessage } = useWebSocket(handleWebSocketMessage);

  // Callback function passed down to interactive modules (Grid, Console)
  // Allows them to send 'notify' messages back to the Hero via the WebSocket
  const handleModuleInteraction = useCallback((interactionMessage: SidekickMessage) => {
    console.log("Sending interaction to Hero:", interactionMessage);
    sendMessage(interactionMessage); // Use the function provided by useWebSocket
  }, [sendMessage]); // Depend on sendMessage function

  // Callback function for the "Clear All" button
  const clearAllModules = useCallback(() => {
    dispatchModules({ type: 'CLEAR_ALL' });
    // dispatchModules is stable
  }, []);

  // Function to render the different module components based on state
  const renderModules = () => {
    // Convert the Map values (module instances) to an array and map over them
    return Array.from(modules.values()).map(module => {
      // Use a switch statement to render the correct component based on module type
      switch (module.type) {
        case 'grid':
          return <GridModule key={module.id} id={module.id} state={module.state as GridState} onInteraction={handleModuleInteraction} />;
        case 'console':
          return <ConsoleModule key={module.id} id={module.id} state={module.state as ConsoleState} onInteraction={handleModuleInteraction} />;
        case 'viz':
          // Viz module doesn't send interactions back currently
          return <VizModule key={module.id} id={module.id} state={module.state as VizState} />;
        case 'canvas':
          // Canvas module doesn't send interactions back currently
          return <CanvasModule key={module.id} id={module.id} state={module.state as CanvasState} />;
        default:
          // Log error if an unknown module type is encountered in state
          console.error("Attempting to render unknown module type:", module);
          return null; // Don't render anything for unknown types
      }
    });
  };

  // Render the main application structure
  return (
      <div className="App">
        <header className="App-header">
          <h1>Sidekick</h1>
          <p>WebSocket: {isConnected ? 'Connected' : 'Disconnected'}</p>
          <button onClick={clearAllModules}>Clear All</button>
        </header>
        <main className="App-main">
          {/* Render all active modules */}
          {renderModules()}
        </main>
      </div>
  );
}

export default App;