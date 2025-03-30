// Sidekick/webapp/src/App.tsx
import { useCallback, useReducer } from 'react'; // Removed React import
import { useWebSocket } from './hooks/useWebSocket';
import {
  HeroMessage,
  ModuleInstance, // Union type
  GridState,
  ConsoleState,
  VizState,
  CanvasState,
  SidekickMessage,
  CanvasSpawnPayload,
  CanvasUpdatePayload,
  VizRepresentation,
  CanvasDrawCommand,
} from './types';
import GridModule from './components/GridModule';
import ConsoleModule from './components/ConsoleModule';
import VizModule from './components/VizModule';
import CanvasModule from './components/CanvasModule';
import './App.css';

// --- Reducer Action Type ---
type ModuleAction =
    | { type: 'PROCESS_MESSAGE'; message: HeroMessage }
    | { type: 'CLEAR_ALL' };

// --- Reducer Logic ---
function moduleReducer(state: Map<string, ModuleInstance>, action: ModuleAction): Map<string, ModuleInstance> {
  const newModules = new Map(state); // Create a mutable copy

  switch (action.type) {
    case 'PROCESS_MESSAGE': {
      const message = action.message;
      if (!message || !message.method || !message.target || !message.module) {
        console.warn("Received incomplete message:", message);
        return state;
      }
      const { module: moduleType, method, target, payload } = message;

      switch (method) {
        case 'spawn': {
          if (newModules.has(target)) {
            console.warn(`${moduleType} Spawn failed: Duplicate target ID "${target}"`);
            return state;
          }
          // --- Spawn Logic ---
          if (moduleType === 'grid') {
            const gridPayload = payload as { size?: [number, number] };
            const initialState: GridState = { size: gridPayload?.size || [10, 10], cells: {} };
            newModules.set(target, { id: target, type: 'grid', state: initialState });
          } else if (moduleType === 'console') {
            const consolePayload = payload as { text?: string };
            const initialState: ConsoleState = { lines: consolePayload?.text ? [consolePayload.text] : [] };
            newModules.set(target, { id: target, type: 'console', state: initialState });
          } else if (moduleType === 'viz') {
            const initialState: VizState = { variables: {}, lastChanges: {} };
            newModules.set(target, { id: target, type: 'viz', state: initialState });
          } else if (moduleType === 'canvas') {
            const canvasPayload = payload as CanvasSpawnPayload;
            if (!canvasPayload || !canvasPayload.width || !canvasPayload.height) {
              console.error(`Canvas Spawn failed: Invalid payload for target "${target}"`, payload);
              return state;
            }
            const initialState: CanvasState = {
              width: canvasPayload.width,
              height: canvasPayload.height,
              bgColor: canvasPayload.bgColor || '#FFFFFF',
              lastCommand: null
            };
            newModules.set(target, { id: target, type: 'canvas', state: initialState });
          } else {
            console.warn(`Spawn failed: Unknown module type "${moduleType}"`);
            return state;
          }
          console.log(`Spawned module: ${target} (${moduleType})`);
          break;
        } // end case 'spawn'

        case 'update': {
          const currentModule = newModules.get(target);
          if (!currentModule) {
            console.warn(`Update failed: Module with ID "${target}" not found.`);
            return state;
          }
          // --- Update Logic ---
          if (currentModule.type === 'grid') {
            const gridUpdate = payload as { x?: number; y?: number; color?: string | null; text?: string | null; fill_color?: string };
            const currentState = currentModule.state as GridState;
            const updatedCells = { ...currentState.cells };
            if (gridUpdate.fill_color !== undefined) {
              for (let y = 0; y < currentState.size[1]; y++) {
                for (let x = 0; x < currentState.size[0]; x++) {
                  updatedCells[`${x},${y}`] = { ...(updatedCells[`${x},${y}`] || {}), color: gridUpdate.fill_color };
                }
              }
            } else if (gridUpdate.x !== undefined && gridUpdate.y !== undefined) {
              const key = `${gridUpdate.x},${gridUpdate.y}`;
              updatedCells[key] = {
                color: gridUpdate.color !== undefined ? gridUpdate.color : currentState.cells[key]?.color,
                text: gridUpdate.text !== undefined ? gridUpdate.text : currentState.cells[key]?.text,
              };
            } else { return state; } // Invalid payload
            newModules.set(target, { ...currentModule, state: { ...currentState, cells: updatedCells } });

          } else if (currentModule.type === 'console') {
            const consoleUpdate = payload as { text?: string; clear?: boolean };
            const currentState = currentModule.state as ConsoleState;
            let updatedLines = currentState.lines;
            if (consoleUpdate.clear === true) { updatedLines = []; }
            else if (consoleUpdate.text !== undefined) { updatedLines = [...currentState.lines, consoleUpdate.text]; }
            newModules.set(target, { ...currentModule, state: { lines: updatedLines } });

          } else if (currentModule.type === 'viz') {
            const vizPayload = payload as { variable_name?: string; representation?: VizRepresentation; change_type?: string; change_details?: any; };
            if (!vizPayload || !vizPayload.variable_name || vizPayload.representation === undefined) { return state; } // Invalid payload
            const currentState = currentModule.state as VizState;
            const updatedVariables = { ...currentState.variables, [vizPayload.variable_name]: vizPayload.representation };
            const updatedLastChanges = { ...currentState.lastChanges, [vizPayload.variable_name]: { change_type: vizPayload.change_type || 'replace', change_details: vizPayload.change_details, timestamp: Date.now() } };
            newModules.set(target, { ...currentModule, state: { variables: updatedVariables, lastChanges: updatedLastChanges } });

          } else if (currentModule.type === 'canvas') {
            const canvasUpdate = payload as CanvasUpdatePayload;
            if (!canvasUpdate || !canvasUpdate.command || !canvasUpdate.options) {
              console.warn(`Invalid canvas update payload for target "${target}":`, payload);
              return state;
            }
            const currentState = currentModule.state as CanvasState;
            const newCommand: CanvasDrawCommand = {
              ...canvasUpdate,
              commandId: `${Date.now()}-${Math.random()}`
            };
            newModules.set(target, { ...currentModule, state: { ...currentState, lastCommand: newCommand } });

          } else {
            console.warn(`Update failed: Unknown module type encountered for target "${target}":`, currentModule);
            return state;
          }
          break;
        } // end case 'update'

        case 'remove': {
          if (!newModules.has(target)) { return state; }
          newModules.delete(target);
          console.log(`Removed module: ${target}`);
          break;
        } // end case 'remove'

        case 'remove_var': { // Specific method for Viz
          const currentModule = newModules.get(target);
          if (!currentModule || currentModule.type !== 'viz') { return state; }
          const varName = payload?.variable_name;
          if (!varName) { return state; }
          const currentState = currentModule.state as VizState;
          const newVars = { ...currentState.variables };
          const newChanges = { ...currentState.lastChanges };
          if (newVars[varName]) {
            delete newVars[varName];
            delete newChanges[varName];
            console.log(`Viz removing variable: ${target}/${varName}`);
            newModules.set(target, { ...currentModule, state: { variables: newVars, lastChanges: newChanges } });
          } else { return state; }
          break;
        } // end case 'remove_var'

        default:
          console.warn('Received unknown method:', method);
          return state;
      } // end inner switch (method)
      return newModules; // Return the updated map from the reducer
    } // end case 'PROCESS_MESSAGE'

    case 'CLEAR_ALL': {
      console.log("Clearing all modules");
      return new Map<string, ModuleInstance>(); // Return a new empty map
    } // end case 'CLEAR_ALL'

    default:
      return state; // Return current state if action is unknown
  } // end outer switch (action.type)
}


function App() {
  const [modules, dispatchModules] = useReducer(moduleReducer, new Map<string, ModuleInstance>());

  const handleWebSocketMessage = useCallback((messageData: any) => {
    if (typeof messageData === 'object' && messageData !== null) {
      dispatchModules({ type: 'PROCESS_MESSAGE', message: messageData as HeroMessage });
    } else { console.error("Received non-object message:", messageData); }
  }, []); // dispatchModules is stable

  const { isConnected, sendMessage } = useWebSocket(handleWebSocketMessage);

  // Memoize the interaction handler for Grid and Console
  const handleModuleInteraction = useCallback((interactionMessage: SidekickMessage) => {
    console.log("Sending interaction to Hero:", interactionMessage);
    sendMessage(interactionMessage);
  }, [sendMessage]);

  const clearAllModules = useCallback(() => {
    dispatchModules({ type: 'CLEAR_ALL' });
  }, []);

  // --- Render modules ---
  const renderModules = () => {
    return Array.from(modules.values()).map(module => {
      switch (module.type) {
        case 'grid':
          return <GridModule key={module.id} id={module.id} state={module.state as GridState} onInteraction={handleModuleInteraction} />;
        case 'console':
          return <ConsoleModule key={module.id} id={module.id} state={module.state as ConsoleState} onInteraction={handleModuleInteraction} />;
        case 'viz':
          return <VizModule key={module.id} id={module.id} state={module.state as VizState} />;
        case 'canvas':
          return <CanvasModule key={module.id} id={module.id} state={module.state as CanvasState} />;
        default:
          console.error("Attempting to render unknown module type:", module);
          return null;
      }
    });
  };

  return (
      <div className="App">
        <header className="App-header">
          <h1>Sidekick MVP</h1>
          <p>WebSocket Status: {isConnected ? 'Connected' : 'Disconnected'}</p>
          <button onClick={clearAllModules}>Clear All Modules</button>
        </header>
        <main className="App-main">
          {renderModules()}
        </main>
      </div>
  );
}

export default App;