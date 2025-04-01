// Sidekick/webapp/src/App.tsx
import { useCallback, useReducer, Reducer } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import {
  HeroMessage,
  SidekickMessage,
  ModuleInstance,
  GridState,
  ConsoleState,
  VizState,
  CanvasState,
  ControlState,
  CanvasSpawnPayload,
  CanvasUpdatePayload,
  VizUpdatePayload,
  ControlUpdatePayload,
  GridUpdatePayload,
  ControlDefinition,
  ConsoleUpdatePayload,
} from './types';
import { updateRepresentationAtPath } from './utils/stateUtils';
import GridModule from './components/GridModule';
import ConsoleModule from './components/ConsoleModule';
import VizModule from './components/VizModule';
import CanvasModule from './components/CanvasModule';
import ControlModule from './components/ControlModule';
import './App.css';

// --- Application State Definition ---
interface AppState {
  modulesById: Map<string, ModuleInstance>;
  moduleOrder: string[];
}
const initialState: AppState = {
  modulesById: new Map<string, ModuleInstance>(),
  moduleOrder: [],
};

// --- Reducer Actions Definition ---
type ModuleAction =
    | { type: 'PROCESS_MESSAGE'; message: HeroMessage }
    | { type: 'CLEAR_ALL' };

// =============================================================================
// == Reducer Helper Functions for Module Logic ==
// =============================================================================

/** Handles the 'spawn' logic */
function handleSpawn(state: AppState, message: HeroMessage): AppState {
  const { module: moduleType, target, payload } = message;
  if (state.modulesById.has(target)) { console.warn(`Spawn failed: Dup ID "${target}"`); return state; }
  let newModuleInstance: ModuleInstance | null = null;
  switch (moduleType) {
    case 'grid': { const p = payload as { size?: [number, number] }; newModuleInstance = { id: target, type: 'grid', state: { size: p?.size || [10, 10], cells: {} } }; break; }
    case 'console': { const p = payload as { text?: string }; newModuleInstance = { id: target, type: 'console', state: { lines: p?.text ? [p.text] : [] } }; break; }
    case 'viz': { newModuleInstance = { id: target, type: 'viz', state: { variables: {}, lastChanges: {} } }; break; }
    case 'canvas': { const p = payload as CanvasSpawnPayload; if (!p || !p.width || !p.height) { console.error(`Canvas Spawn failed`, p); return state; } newModuleInstance = { id: target, type: 'canvas', state: { width: p.width, height: p.height, bgColor: p.bgColor || '#FFFFFF', commandQueue: [] } }; break; }
    case 'control': { newModuleInstance = { id: target, type: 'control', state: { controls: new Map() } }; break; }
    default: console.warn(`Spawn failed: Unknown type "${moduleType}"`); return state;
  }
  if (newModuleInstance) {
    const newModulesById = new Map(state.modulesById);
    const newModuleOrder = [...state.moduleOrder, target];
    newModulesById.set(target, newModuleInstance);
    console.log(`Spawned: ${target} (${moduleType}), Order:`, newModuleOrder);
    return { modulesById: newModulesById, moduleOrder: newModuleOrder };
  }
  return state;
}

/** Handles the 'update' logic */
function handleUpdate(state: AppState, message: HeroMessage): AppState {
  const { target, payload } = message;
  const currentModule = state.modulesById.get(target);
  if (!currentModule) { console.warn(`Update failed: Mod "${target}" not found.`); return state; }
  if (!payload || typeof payload !== 'object' || !payload.action) { console.warn(`Update failed: Invalid payload/action for "${target}"`, payload); return state; }

  let updatedModule = { ...currentModule };
  let stateChanged = false;

  switch (updatedModule.type) {
    case 'grid': stateChanged = updateGridState(updatedModule, payload); break;
    case 'console': stateChanged = updateConsoleState(updatedModule, payload); break;
    case 'canvas': stateChanged = updateCanvasState(updatedModule, payload); break;
    case 'viz': stateChanged = updateVizState(updatedModule, payload); break;
    case 'control': stateChanged = updateControlState(updatedModule, payload); break;
    default: { const _exhaustiveCheck: never = updatedModule; console.error(`Update failed: Unhandled type: ${(_exhaustiveCheck as any)?.type}`); return state; }
  }

  if (stateChanged) {
    const newModulesById = new Map(state.modulesById);
    newModulesById.set(target, updatedModule);
    return { ...state, modulesById: newModulesById };
  }
  return state;
}

/** Helper to update Grid state */
function updateGridState(module: ModuleInstance, payload: GridUpdatePayload): boolean {
  if (module.type !== 'grid') return false;
  const currentState = module.state as GridState;
  const { action, options } = payload;
  if (action === 'setCell') {
    if (!options || options.x === undefined || options.y === undefined) { console.warn(`Invalid 'setCell' options`); return false; }
    const updatedCells = { ...currentState.cells }; const key = `${options.x},${options.y}`; const currentCell = currentState.cells[key];
    const newCellState = { color: options.color !== undefined ? options.color : currentCell?.color, text: options.text !== undefined ? options.text : currentCell?.text, };
    updatedCells[key] = newCellState; module.state = { ...currentState, cells: updatedCells }; return true;
  } else if (action === 'clear') { if (Object.keys(currentState.cells).length > 0) { module.state = { ...currentState, cells: {} }; console.log(`Grid ${module.id} cleared.`); return true; } return false; }
  else { console.warn(`Unknown action "${action}" for grid`); return false; }
}

/** Helper to update Console state */
function updateConsoleState(module: ModuleInstance, payload: ConsoleUpdatePayload): boolean {
  if (module.type !== 'console') return false;
  const currentState = module.state as ConsoleState;
  const { action, options } = payload;
  if (action === 'append') { if (!options || options.text === undefined) { console.warn(`Invalid 'append' options`); return false; } const updatedLines = [...currentState.lines, options.text]; module.state = { lines: updatedLines }; return true; }
  else if (action === 'clear') { if (currentState.lines.length > 0) { module.state = { lines: [] }; console.log(`Console ${module.id} cleared.`); return true; } return false; }
  else { console.warn(`Unknown action "${action}" for console`); return false; }
}

/** Helper to update Canvas state */
function updateCanvasState(module: ModuleInstance, payload: CanvasUpdatePayload): boolean {
  if (module.type !== 'canvas') return false;
  const currentState = module.state as CanvasState;
  const { action, options, commandId } = payload;
  if (!action || !options || !commandId) { console.warn(`Invalid canvas update payload`); return false; }
  const existingIndex = currentState.commandQueue.findIndex(cmd => cmd.commandId === commandId);
  if (existingIndex !== -1) { console.warn(`Canvas ${module.id}: Dup commandId ${commandId}.`); return false; }
  const updatedQueue = [...currentState.commandQueue, payload]; module.state = { ...currentState, commandQueue: updatedQueue }; return true;
}

/** Helper to update Viz state */
function updateVizState(module: ModuleInstance, payload: VizUpdatePayload): boolean {
  if (module.type !== 'viz') return false;
  const currentState = module.state as VizState;
  const { action: vizAction, variableName, options } = payload;
  if (!vizAction || !variableName || !options) { console.warn(`Invalid viz update structure`); return false; }
  const { path = [] } = options;

  let newVariablesState = { ...currentState.variables };
  let newLastChanges = { ...currentState.lastChanges };
  let variableChanged = false;
  // REMOVED unused variable: let variableRemoved = false;

  if (vizAction === 'removeVariable') {
    if (newVariablesState[variableName]) { delete newVariablesState[variableName]; delete newLastChanges[variableName]; /* variableRemoved = true; */ variableChanged = true; console.log(`Viz removed: ${module.id}/${variableName}`); }
    else { return false; }
  } else {
    const currentRepresentation = currentState.variables[variableName];
    if (currentRepresentation || (vizAction === 'set' && path.length === 0 && options.valueRepresentation)) {
      try { newVariablesState[variableName] = updateRepresentationAtPath( currentRepresentation, payload ); newLastChanges[variableName] = { action: vizAction, path: path, timestamp: Date.now() }; variableChanged = true; if (!currentRepresentation && vizAction === 'set') { console.log(`Viz created: ${module.id}/${variableName}`); } }
      catch (e) { console.error(`Error applying viz update ${variableName} path ${path}:`, e); return false; }
    } else { console.warn(`Viz update failed: Var ${variableName} not found for action ${vizAction}.`); return false; }
  }

  if (variableChanged) { module.state = { variables: newVariablesState, lastChanges: newLastChanges }; return true; }
  return false;
}

/** Helper to update Control state */
function updateControlState(module: ModuleInstance, payload: ControlUpdatePayload): boolean {
  if (module.type !== 'control') return false;
  const currentState = module.state as ControlState;
  const { action: controlAction, controlId, options } = payload;
  if (!controlAction || !controlId) { console.warn(`Invalid control update structure`); return false; }

  const updatedControls = new Map(currentState.controls);
  let changed = false;
  if (controlAction === 'add') { if (!options || !options.controlType || !options.config) { console.warn(`Invalid 'add' control options`); return false; } const newControlDef: ControlDefinition = { id: controlId, type: options.controlType, config: options.config }; updatedControls.set(controlId, newControlDef); console.log(`Control ${module.id}: Added/Updated ${controlId}`); changed = true; }
  else if (controlAction === 'remove') { if (updatedControls.has(controlId)) { updatedControls.delete(controlId); console.log(`Control ${module.id}: Removed ${controlId}`); changed = true; } else { console.warn(`Control ${module.id}: ID ${controlId} not found for removal.`); } }
  else { console.warn(`Unknown action "${controlAction}" for control`); return false; }
  if (changed) { module.state = { controls: updatedControls }; return true; }
  return false;
}

// =============================================================================
// == Main Reducer ==
// =============================================================================
const rootReducer: Reducer<AppState, ModuleAction> = (state, action): AppState => {
  switch (action.type) {
    case 'PROCESS_MESSAGE': {
      const { method } = action.message;
      switch (method) {
        case 'spawn': return handleSpawn(state, action.message);
        case 'update': return handleUpdate(state, action.message);
        case 'remove': {
          const { target } = action.message;
          if (!state.modulesById.has(target)) return state;
          const newModulesById = new Map(state.modulesById); newModulesById.delete(target);
          const newModuleOrder = state.moduleOrder.filter(id => id !== target);
          console.log(`Reducer: Removed module: ${target}, Order:`, newModuleOrder);
          return { modulesById: newModulesById, moduleOrder: newModuleOrder };
        }
        default: console.warn('Reducer: Unknown method:', method); return state;
      }
    }
    case 'CLEAR_ALL': console.log("Reducer: Clearing all modules"); return initialState;
    default: console.warn("Reducer: Unknown action type:", (action as any)?.type); return state;
  }
};

// =============================================================================
// == Main Application Component ==
// =============================================================================
function App() {
  const [appState, dispatchModules] = useReducer(rootReducer, initialState);
  const { modulesById, moduleOrder } = appState;

  const handleWebSocketMessage = useCallback((messageData: any) => {
    if (typeof messageData === 'object' && messageData !== null) { dispatchModules({ type: 'PROCESS_MESSAGE', message: messageData as HeroMessage }); }
    else { console.error("App: Received non-object message:", messageData); }
  }, []);

  const { isConnected, sendMessage } = useWebSocket(handleWebSocketMessage);

  const handleModuleInteraction = useCallback((interactionMessage: SidekickMessage) => {
    if (interactionMessage && interactionMessage.module && interactionMessage.method && interactionMessage.src) { sendMessage(interactionMessage); }
    else { console.error("App: Invalid interaction message:", interactionMessage); }
  }, [sendMessage]);

  const clearAllModules = useCallback(() => { dispatchModules({ type: 'CLEAR_ALL' }); }, []);

  const renderModules = () => {
    return moduleOrder.map(moduleId => {
      const module = modulesById.get(moduleId);
      if (!module) { console.error(`App: Module ${moduleId} in order but not map!`); return null; }
      switch (module.type) {
        case 'grid': return <GridModule key={module.id} id={module.id} state={module.state as GridState} onInteraction={handleModuleInteraction} />;
        case 'console': return <ConsoleModule key={module.id} id={module.id} state={module.state as ConsoleState} onInteraction={handleModuleInteraction} />;
        case 'viz': return <VizModule key={module.id} id={module.id} state={module.state as VizState} />;
        case 'canvas': return <CanvasModule key={module.id} id={module.id} state={module.state as CanvasState} />;
        case 'control': return <ControlModule key={module.id} id={module.id} state={module.state as ControlState} onInteraction={handleModuleInteraction} />;
        default: {
          // FIX: Safely render default case using type assertion for key
          const unknownModule = module as any; // Assert to access id safely
          console.error("App: Rendering unknown module type:", unknownModule?.type);
          return <div key={unknownModule?.id || `unknown_${Date.now()}`}>Error: Unknown Module Type '{unknownModule?.type}'</div>;
        }
      }
    });
  };

  return (
      <div className="App">
        <header className="App-header">
          <h1>Sidekick</h1>
          <p>WebSocket: {isConnected ? 'Connected' : 'Disconnected'}</p>
          <button onClick={clearAllModules}>Clear All</button>
        </header>
        <main className="App-main">
          {moduleOrder.length === 0 ? <p>No modules active.</p> : renderModules()}
        </main>
      </div>
  );
}

export default App;