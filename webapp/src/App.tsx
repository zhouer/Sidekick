// Sidekick/webapp/src/App.tsx
import { useCallback, useReducer } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import {
  HeroMessage, ModuleInstance, GridState, ConsoleState, VizState, CanvasState, SidekickMessage,
  CanvasSpawnPayload, CanvasUpdatePayload, /* Removed VizRepresentation here */ CanvasDrawCommand,
  VizUpdatePayload
} from './types'; // Removed VizRepresentation import
import { updateRepresentationAtPath } from './utils/stateUtils';
import GridModule from './components/GridModule';
import ConsoleModule from './components/ConsoleModule';
import VizModule from './components/VizModule';
import CanvasModule from './components/CanvasModule';
import './App.css';

type ModuleAction =
    | { type: 'PROCESS_MESSAGE'; message: HeroMessage }
    | { type: 'CLEAR_ALL' };

// --- Reducer (no changes from previous version) ---
function moduleReducer(state: Map<string, ModuleInstance>, action: ModuleAction): Map<string, ModuleInstance> {
  const newModules = new Map(state);

  switch (action.type) {
    case 'PROCESS_MESSAGE': {
      const message = action.message;
      if (!message || !message.method || !message.target || !message.module) {
        console.warn("Received incomplete message:", message); return state;
      }
      const { module: moduleType, method, target, payload } = message;

      switch (method) {
        case 'spawn': {
          if (newModules.has(target)) { console.warn(`${moduleType} Spawn failed: Duplicate ID "${target}"`); return state; }
          if (moduleType === 'grid') { const p = payload as { size?: [number, number] }; newModules.set(target, { id: target, type: 'grid', state: { size: p?.size || [10, 10], cells: {} } }); }
          else if (moduleType === 'console') { const p = payload as { text?: string }; newModules.set(target, { id: target, type: 'console', state: { lines: p?.text ? [p.text] : [] } }); }
          else if (moduleType === 'viz') { newModules.set(target, { id: target, type: 'viz', state: { variables: {}, lastChanges: {} } }); }
          else if (moduleType === 'canvas') { const p = payload as CanvasSpawnPayload; if (!p || !p.width || !p.height) { console.error(`Canvas Spawn failed: Invalid payload for "${target}"`, payload); return state; } newModules.set(target, { id: target, type: 'canvas', state: { width: p.width, height: p.height, bgColor: p.bgColor || '#FFFFFF', lastCommand: null } }); }
          else { console.warn(`Spawn failed: Unknown type "${moduleType}"`); return state; }
          console.log(`Spawned module: ${target} (${moduleType})`);
          break;
        }
        case 'update': {
          const currentModule = newModules.get(target);
          if (!currentModule) { console.warn(`Update failed: Module "${target}" not found.`); return state; }

          if (currentModule.type === 'grid') {
            const gridUpdate = payload as { x?: number; y?: number; color?: string | null; text?: string | null; fill_color?: string };
            const currentState = currentModule.state as GridState; const updatedCells = { ...currentState.cells };
            if (gridUpdate.fill_color !== undefined) { for (let y = 0; y < currentState.size[1]; y++) for (let x = 0; x < currentState.size[0]; x++) updatedCells[`${x},${y}`] = { ...(updatedCells[`${x},${y}`] || {}), color: gridUpdate.fill_color }; }
            else if (gridUpdate.x !== undefined && gridUpdate.y !== undefined) { const key = `${gridUpdate.x},${gridUpdate.y}`; updatedCells[key] = { color: gridUpdate.color !== undefined ? gridUpdate.color : currentState.cells[key]?.color, text: gridUpdate.text !== undefined ? gridUpdate.text : currentState.cells[key]?.text }; }
            else { return state; } newModules.set(target, { ...currentModule, state: { ...currentState, cells: updatedCells } });
          }
          else if (currentModule.type === 'console') {
            const consoleUpdate = payload as { text?: string; clear?: boolean }; const currentState = currentModule.state as ConsoleState; let updatedLines = currentState.lines;
            if (consoleUpdate.clear === true) { updatedLines = []; } else if (consoleUpdate.text !== undefined) { updatedLines = [...currentState.lines, consoleUpdate.text]; } newModules.set(target, { ...currentModule, state: { lines: updatedLines } });
          }
          else if (currentModule.type === 'canvas') {
            const canvasUpdate = payload as CanvasUpdatePayload; if (!canvasUpdate || !canvasUpdate.command || !canvasUpdate.options) { console.warn(`Invalid canvas update payload for "${target}":`, payload); return state; } const currentState = currentModule.state as CanvasState; const newCommand: CanvasDrawCommand = { ...canvasUpdate, commandId: `${Date.now()}-${Math.random()}` }; newModules.set(target, { ...currentModule, state: { ...currentState, lastCommand: newCommand } });
          }
          else if (currentModule.type === 'viz') {
            const vizPayload = payload as VizUpdatePayload;
            if (!vizPayload || !vizPayload.variable_name || !vizPayload.change_type || !vizPayload.path) { console.warn("Invalid viz update payload:", payload); return state; }
            const currentState = currentModule.state as VizState;
            const { variable_name, change_type, path } = vizPayload;
            let newVariablesState = { ...currentState.variables };
            let variableRemoved = false;
            if (change_type === 'remove_variable') { if (newVariablesState[variable_name]) { delete newVariablesState[variable_name]; variableRemoved = true; console.log(`Viz removed variable: ${target}/${variable_name}`); } else { return state; } }
            else if (newVariablesState[variable_name]) { try { newVariablesState[variable_name] = updateRepresentationAtPath( currentState.variables[variable_name], vizPayload ); } catch (e) { console.error(`Error applying viz update for ${variable_name}:`, e); return state; } }
            else { if (change_type === 'set' && path.length === 0 && vizPayload.value_representation) { newVariablesState[variable_name] = vizPayload.value_representation; console.log(`Viz created variable via 'set' update: ${target}/${variable_name}`); } else { console.warn(`Viz update failed: Variable ${variable_name} not found.`); return state; } }
            const newLastChanges = { ...currentState.lastChanges, [variable_name]: { change_type: change_type, path: path, timestamp: Date.now() } };
            if (variableRemoved) { delete newLastChanges[variable_name]; }
            newModules.set(target, { ...currentModule, state: { variables: newVariablesState, lastChanges: newLastChanges } });
          } else { console.warn(`Update failed: Unknown type for "${target}":`, currentModule); return state; }
          break;
        }
        case 'remove': {
          if (!newModules.has(target)) { return state; } newModules.delete(target); console.log(`Removed module: ${target}`); break;
        }
        default: console.warn('Received unknown method:', method); return state;
      }
      return newModules;
    }
    case 'CLEAR_ALL': { return new Map<string, ModuleInstance>(); }
    default: return state;
  }
}


// --- App Component (no changes) ---
function App() {
  const [modules, dispatchModules] = useReducer(moduleReducer, new Map<string, ModuleInstance>());
  const handleWebSocketMessage = useCallback((messageData: any) => { if (typeof messageData === 'object' && messageData !== null) { dispatchModules({ type: 'PROCESS_MESSAGE', message: messageData as HeroMessage }); } else { console.error("Received non-object message:", messageData); } }, []);
  const { isConnected, sendMessage } = useWebSocket(handleWebSocketMessage);
  const handleModuleInteraction = useCallback((interactionMessage: SidekickMessage) => { console.log("Sending interaction to Hero:", interactionMessage); sendMessage(interactionMessage); }, [sendMessage]);
  const clearAllModules = useCallback(() => { dispatchModules({ type: 'CLEAR_ALL' }); }, []);
  const renderModules = () => { return Array.from(modules.values()).map(module => { switch (module.type) { case 'grid': return <GridModule key={module.id} id={module.id} state={module.state as GridState} onInteraction={handleModuleInteraction} />; case 'console': return <ConsoleModule key={module.id} id={module.id} state={module.state as ConsoleState} onInteraction={handleModuleInteraction} />; case 'viz': return <VizModule key={module.id} id={module.id} state={module.state as VizState} />; case 'canvas': return <CanvasModule key={module.id} id={module.id} state={module.state as CanvasState} />; default: console.error("Unknown module type:", module); return null; } }); };
  return ( <div className="App"> <header className="App-header"> <h1>Sidekick</h1> <p>WebSocket: {isConnected ? 'Connected' : 'Disconnected'}</p> <button onClick={clearAllModules}>Clear All</button> </header> <main className="App-main"> {renderModules()} </main> </div> );
}
export default App;