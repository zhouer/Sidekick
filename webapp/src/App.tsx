// Sidekick/webapp/src/App.tsx
import React, { useCallback, useReducer, Reducer } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { moduleRegistry } from './modules/moduleRegistry'; // Import the central module registry
import {
  HeroMessage,
  SidekickMessage,
  ModuleInstance, // Generic ModuleInstance type
  ModuleDefinition // Generic ModuleDefinition type
} from './types'; // Import shared, generic types
import './App.css';

// --- Application State Definition ---
interface AppState {
  modulesById: Map<string, ModuleInstance>; // Map instance ID -> ModuleInstance
  moduleOrder: string[];                  // Array of instance IDs in creation order
}
// Initial state when the application loads
const initialState: AppState = {
  modulesById: new Map<string, ModuleInstance>(),
  moduleOrder: [],
};

// --- Reducer Actions Definition ---
// Defines the types of actions the reducer can handle
type ModuleAction =
    | { type: 'PROCESS_MESSAGE'; message: HeroMessage } // Action to process incoming message from Hero
    | { type: 'CLEAR_ALL' }; // Action to remove all modules

// =============================================================================
// == Main Application Reducer ==
// Manages the central state (modulesById, moduleOrder) based on dispatched actions.
// Delegates module-specific logic (initialization, updates) to the module registry.
// =============================================================================
const rootReducer: Reducer<AppState, ModuleAction> = (state, action): AppState => {
  switch (action.type) {
      // Handle processing of messages received from the Hero backend
    case 'PROCESS_MESSAGE': {
      const message = action.message;
      // Extract message details
      const { module: moduleType, method, target, payload } = message;

      // Find the corresponding module definition in the registry
      const moduleDefinition = moduleRegistry.get(moduleType);

      // Handle different message methods ('spawn', 'update', 'remove')
      switch (method) {
        case 'spawn': {
          // Prevent spawning if instance ID already exists
          if (state.modulesById.has(target)) {
            console.warn(`Reducer: Spawn failed - Duplicate instance ID "${target}".`);
            return state;
          }
          // Ensure the module type is known/registered
          if (!moduleDefinition) {
            console.warn(`Reducer: Spawn failed - Unknown module type "${moduleType}".`);
            return state;
          }

          try {
            // Delegate initial state creation to the registered module's logic
            const initialModuleState = moduleDefinition.getInitialState(target, payload);

            // Create the new module instance object
            const newModuleInstance: ModuleInstance = {
              id: target,
              type: moduleType, // Store the type string
              state: initialModuleState,
            };

            // Update application state immutably
            const newModulesById = new Map(state.modulesById);
            newModulesById.set(target, newModuleInstance);
            const newModuleOrder = [...state.moduleOrder, target]; // Append ID to order

            console.log(`Reducer: Spawned "${target}" (${moduleType}). Order:`, newModuleOrder);
            return { modulesById: newModulesById, moduleOrder: newModuleOrder };

          } catch (error: any) {
            // Handle errors during initial state creation (e.g., invalid payload)
            console.error(`Reducer: Error spawning module "${target}" (${moduleType}):`, error.message || error);
            return state; // Return unchanged state on error
          }
        }

        case 'update': {
          // Find the module instance to update
          const currentModule = state.modulesById.get(target);
          if (!currentModule) {
            console.warn(`Reducer: Update failed - Module instance "${target}" not found.`);
            return state;
          }
          // Verify the registered definition matches the instance type and incoming message type
          if (!moduleDefinition || currentModule.type !== moduleDefinition.type || currentModule.type !== moduleType) {
            console.error(`Reducer: Update failed - Module type mismatch or not registered for "${target}" (Instance: ${currentModule.type}, Message: ${moduleType}).`);
            return state;
          }
          // Basic payload check (specific checks happen in module logic)
          if (!payload) {
            console.warn(`Reducer: Update failed - Missing payload for "${target}".`);
            return state;
          }

          try {
            // Delegate state update to the registered module's logic
            const updatedModuleState = moduleDefinition.updateState(currentModule.state, payload);

            // If the update function returned the exact same state object, no update needed
            if (updatedModuleState === currentModule.state) {
              return state;
            }

            // Create the updated module instance with the new state
            const updatedModuleInstance = {
              ...currentModule,
              state: updatedModuleState,
            };

            // Update application state immutably
            const newModulesById = new Map(state.modulesById);
            newModulesById.set(target, updatedModuleInstance);

            // Module order remains the same on update
            return { ...state, modulesById: newModulesById };

          } catch (error: any) {
            // Handle errors during state update (e.g., invalid payload for the module)
            console.error(`Reducer: Error updating module "${target}" (${moduleType}):`, error.message || error);
            return state; // Return unchanged state on error
          }
        }

        case 'remove': {
          // Only proceed if the module instance actually exists
          if (!state.modulesById.has(target)) {
            return state; // Already removed or never existed
          }

          // Update application state immutably
          const newModulesById = new Map(state.modulesById);
          newModulesById.delete(target); // Remove instance from map
          const newModuleOrder = state.moduleOrder.filter(id => id !== target); // Filter ID out of order array

          console.log(`Reducer: Removed module "${target}". Order:`, newModuleOrder);
          return { modulesById: newModulesById, moduleOrder: newModuleOrder };
        }

          // Handle unknown message methods
        default:
          console.warn('Reducer: Unknown message method:', method);
          return state;
      }
    }
      // Handle the action to clear all modules
    case 'CLEAR_ALL':
      console.log("Reducer: Clearing all modules.");
      return initialState; // Reset state to the initial empty configuration
      // Handle unknown action types
    default:
      console.warn("Reducer: Unknown action type:", (action as any)?.type);
      return state;
  }
};

// =============================================================================
// == Main Application Component ==
// Renders the UI including header and dynamically rendered modules.
// =============================================================================
function App() {
  // Central application state managed by the reducer
  const [appState, dispatchModules] = useReducer(rootReducer, initialState);
  const { modulesById, moduleOrder } = appState;

  // Callback function passed to useWebSocket hook to handle incoming messages
  const handleWebSocketMessage = useCallback((messageData: any) => {
    // Basic validation of received data
    if (typeof messageData === 'object' && messageData !== null) {
      // Dispatch the message to the reducer if it's a valid object
      dispatchModules({ type: 'PROCESS_MESSAGE', message: messageData as HeroMessage });
    } else {
      console.error("App: Received non-object message from WebSocket:", messageData);
    }
  }, []); // dispatchModules is stable, no dependency needed

  // Custom hook to manage WebSocket connection
  const { isConnected, sendMessage } = useWebSocket(handleWebSocketMessage);

  // Callback function passed down to interactive module components
  // Used by modules to send notifications back to the Hero backend
  const handleModuleInteraction = useCallback((interactionMessage: SidekickMessage) => {
    // Basic validation of the message structure from the module component
    if (interactionMessage && interactionMessage.module && interactionMessage.method && interactionMessage.src) {
      sendMessage(interactionMessage); // Send the message via WebSocket
    } else {
      console.error("App: Invalid interaction message structure from component:", interactionMessage);
    }
  }, [sendMessage]); // Dependency on the stable sendMessage function

  // Callback for the "Clear All" button click
  const clearAllModules = useCallback(() => {
    dispatchModules({ type: 'CLEAR_ALL' });
  }, []); // No dependencies

  // --- Render Logic for Modules ---
  const renderModules = () => {
    // Map over the moduleOrder array to render components in the correct sequence
    return moduleOrder.map(moduleId => {
      // Get the module instance data from the state map
      const moduleInstance = modulesById.get(moduleId);

      // Safety check: Handle case where module ID exists in order but not in map (shouldn't happen ideally)
      if (!moduleInstance) {
        console.error(`App Render: Module "${moduleId}" found in order but not in map!`);
        return <div key={moduleId}>Error: Module data missing for {moduleId}</div>;
      }

      // Find the module's definition (component, logic functions) in the registry
      const moduleDefinition = moduleRegistry.get(moduleInstance.type);

      // Safety check: Handle case where the module type isn't registered
      if (!moduleDefinition) {
        console.error(`App Render: Module type "${moduleInstance.type}" for instance "${moduleId}" is not registered!`);
        return <div key={moduleId}>Error: Unknown Module Type '{moduleInstance.type}'</div>;
      }

      // Get the specific React component to render from the definition
      const ModuleComponent = moduleDefinition.component;

      // Prepare the props required by the module component
      // Note: state is passed as 'any' here, component internally expects specific type
      const componentProps: any = {
        id: moduleInstance.id,
        state: moduleInstance.state,
        // Conditionally pass the interaction handler only to modules that need it
        ...( moduleDefinition.isInteractive && { onInteraction: handleModuleInteraction } )
      };

      // Render the component with its props
      return <ModuleComponent key={moduleInstance.id} {...componentProps} />;
    });
  };

  // --- Main JSX Structure ---
  return (
      <div className="App">
        {/* Header section */}
        <header className="App-header">
          <h1>Sidekick</h1>
          {/* Display WebSocket connection status with appropriate class */}
          <p className={`status-${isConnected ? 'connected' : 'disconnected'}`}>
            WebSocket: {isConnected ? 'Connected' : 'Disconnected'}
          </p>
          {/* Button to clear all modules, disabled if none exist */}
          <button onClick={clearAllModules} disabled={moduleOrder.length === 0}>Clear All</button>
        </header>

        {/* Main content area */}
        <main className="App-main">
          {/* Show a placeholder message if no modules are active, otherwise render them */}
          {moduleOrder.length === 0
              ? <p>No modules active. Run a script using the Sidekick library!</p>
              : renderModules()}
        </main>
      </div>
  );
}

export default App;