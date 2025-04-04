// Sidekick/webapp/src/App.tsx
import React, { useCallback, useReducer, Reducer, useState } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { moduleRegistry } from './modules/moduleRegistry';
import {
    ReceivedMessage, // Use the specific union type
    SentMessage,     // Use the specific union type
    ModuleInstance,
    ModuleDefinition,
    SystemAnnounceMessage,
    GlobalClearMessage,
    ModuleControlMessage,
    HeroPeerInfo,
    ModuleNotifyMessage,
    ModuleErrorMessage
} from './types';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faInfoCircle } from '@fortawesome/free-solid-svg-icons';
import './App.css';

// --- Application State Definition ---
interface AppState {
    modulesById: Map<string, ModuleInstance>; // Map instance ID -> ModuleInstance
    moduleOrder: string[];                  // Array of instance IDs in creation order
    heroStatus: HeroPeerInfo | null;        // Status of the connected Hero (if any)
}

// Initial state
const initialState: AppState = {
    modulesById: new Map<string, ModuleInstance>(),
    moduleOrder: [],
    heroStatus: null,
};

// --- Reducer Actions Definition ---
type AppAction =
    | { type: 'PROCESS_MESSAGE'; message: ReceivedMessage } // Use the specific union type
    | { type: 'CLEAR_ALL_MODULES' }; // Renamed for clarity

// =============================================================================
// == Main Application Reducer ==
// =============================================================================
const rootReducer: Reducer<AppState, AppAction> = (state, action): AppState => {
    switch (action.type) {
        case 'PROCESS_MESSAGE': {
            const message = action.message;

            // --- Handle System Announce ---
            if (message.module === 'system' && message.method === 'announce') {
                const payload = (message as SystemAnnounceMessage).payload;
                if (payload && payload.role === 'hero') {
                    // Update hero status (overwrite previous hero info for simplicity)
                    console.log(`Reducer: Received Hero announce (${payload.peerId}, Status: ${payload.status})`);
                    const newHeroStatus: HeroPeerInfo | null = payload.status === 'online' ? {
                        peerId: payload.peerId,
                        version: payload.version,
                        status: payload.status,
                        timestamp: payload.timestamp,
                    } : null; // Set to null if hero goes offline

                    // Only return new state if status actually changed
                    if (state.heroStatus?.peerId !== newHeroStatus?.peerId || state.heroStatus?.status !== newHeroStatus?.status) {
                        return { ...state, heroStatus: newHeroStatus };
                    }
                }
                // Ignore sidekick announcements or other roles for now
                return state; // No state change needed for this message
            }

            // --- Handle Global Clear ---
            if (message.module === 'global' && message.method === 'clearAll') {
                console.log("Reducer: Received global/clearAll command.");
                // Only update if modules actually exist
                if (state.modulesById.size > 0 || state.moduleOrder.length > 0) {
                    return { ...state, modulesById: new Map(), moduleOrder: [] };
                }
                return state; // Already cleared
            }

            // --- Handle Module Control Messages ---
            // Type guard to ensure it's a ModuleControlMessage before proceeding
            if (message.method === 'spawn' || message.method === 'update' || message.method === 'remove') {
                const moduleMessage = message as ModuleControlMessage;
                const { module: moduleType, method, target, payload } = moduleMessage;

                const moduleDefinition = moduleRegistry.get(moduleType);

                switch (method) {
                    case 'spawn': {
                        if (state.modulesById.has(target)) { console.warn(`Reducer: Spawn failed - Duplicate ID "${target}".`); return state; }
                        if (!moduleDefinition) { console.warn(`Reducer: Spawn failed - Unknown module type "${moduleType}".`); return state; }

                        try {
                            const initialModuleState = moduleDefinition.getInitialState(target, payload);
                            const newModuleInstance: ModuleInstance = { id: target, type: moduleType, state: initialModuleState };
                            const newModulesById = new Map(state.modulesById).set(target, newModuleInstance);
                            const newModuleOrder = [...state.moduleOrder, target];
                            console.log(`Reducer: Spawned "${target}" (${moduleType}). Order:`, newModuleOrder);
                            return { ...state, modulesById: newModulesById, moduleOrder: newModuleOrder };
                        } catch (error: any) { console.error(`Reducer: Error spawning module "${target}" (${moduleType}):`, error.message || error); return state; }
                    }

                    case 'update': {
                        const currentModule = state.modulesById.get(target);
                        if (!currentModule) { console.warn(`Reducer: Update failed - Module "${target}" not found.`); return state; }
                        if (!moduleDefinition || currentModule.type !== moduleDefinition.type || currentModule.type !== moduleType) { console.error(`Reducer: Update failed - Module type mismatch for "${target}"`); return state; }
                        if (payload === undefined) { console.warn(`Reducer: Update failed - Missing payload for "${target}".`); return state; } // Check payload exists

                        try {
                            // Ensure payload is treated as 'any' for the generic updateState function
                            const updatedModuleState = moduleDefinition.updateState(currentModule.state, payload as any);
                            if (updatedModuleState === currentModule.state) { return state; } // No change

                            const updatedModuleInstance = { ...currentModule, state: updatedModuleState };
                            const newModulesById = new Map(state.modulesById).set(target, updatedModuleInstance);
                            return { ...state, modulesById: newModulesById };
                        } catch (error: any) { console.error(`Reducer: Error updating module "${target}" (${moduleType}):`, error.message || error); return state; }
                    }

                    case 'remove': {
                        if (!state.modulesById.has(target)) { return state; } // Already removed
                        const newModulesById = new Map(state.modulesById);
                        newModulesById.delete(target);
                        const newModuleOrder = state.moduleOrder.filter(id => id !== target);
                        console.log(`Reducer: Removed module "${target}". Order:`, newModuleOrder);
                        return { ...state, modulesById: newModulesById, moduleOrder: newModuleOrder };
                    }
                    // No default needed as method is constrained by type guard
                }
            }

            // Fallback for unhandled message types (should ideally not happen with strict typing)
            console.warn('Reducer: Unhandled message type received:', message);
            return state;
        }

        // Handle explicit CLEAR_ALL_MODULES action (e.g., from a UI button)
        case 'CLEAR_ALL_MODULES':
            console.log("Reducer: Clearing all modules via UI action.");
            // Only update if modules actually exist
            if (state.modulesById.size > 0 || state.moduleOrder.length > 0) {
                return { ...state, modulesById: new Map(), moduleOrder: [], heroStatus: state.heroStatus }; // Keep hero status
            }
            return state; // Already cleared

        default:
            console.warn("Reducer: Unknown action type:", (action as any)?.type);
            return state;
    }
};

// =============================================================================
// == Main Application Component ==
// =============================================================================
function App() {
    const [appState, dispatch] = useReducer(rootReducer, initialState);
    const { modulesById, moduleOrder, heroStatus } = appState;
    const [hoveredInfoId, setHoveredInfoId] = useState<string | null>(null);

    // Callback for useWebSocket hook
    const handleWebSocketMessage = useCallback((messageData: any) => {
        // Basic validation
        if (typeof messageData === 'object' && messageData !== null && messageData.module && messageData.method) {
            dispatch({ type: 'PROCESS_MESSAGE', message: messageData as ReceivedMessage });
        } else {
            console.error("App: Received invalid message structure from WebSocket:", messageData);
        }
    }, []); // dispatch is stable

    // WebSocket connection hook
    const { isConnected, sendMessage } = useWebSocket(handleWebSocketMessage);

    // Callback passed to interactive modules
    const handleModuleInteraction = useCallback((interactionMessage: SentMessage) => {
        // Check for properties common to messages that should be sent
        if (interactionMessage && interactionMessage.module && interactionMessage.method) {
            // Check if it's a type that *should* have 'src' before validating 'src'
            if ((interactionMessage.method === 'notify' || interactionMessage.method === 'error')) {
                // Now it's safe to check for src on ModuleNotifyMessage or ModuleErrorMessage
                const notifyOrErrorMsg = interactionMessage as ModuleNotifyMessage | ModuleErrorMessage;
                if (notifyOrErrorMsg.src) {
                    sendMessage(notifyOrErrorMsg);
                } else {
                    console.error("App: Invalid notify/error message missing 'src':", interactionMessage);
                }
            } else if (interactionMessage.module === 'system') {
                // Allow sending system messages (though usually only done by useWebSocket hook)
                sendMessage(interactionMessage);
            } else {
                console.error("App: Attempted to send message of unexpected type via interaction:", interactionMessage);
            }
        } else {
            console.error("App: Invalid interaction message structure from component:", interactionMessage);
        }
    }, [sendMessage]);

    // Callback for the UI "Clear All" button
    const clearAllModulesUI = useCallback(() => {
        // Dispatch local clear action, Python side handles global/clearAll via config or manual call
        dispatch({ type: 'CLEAR_ALL_MODULES' });
    }, []);

    // --- Render Logic for Modules ---
    const renderModules = () => {
        return moduleOrder.map(moduleId => {
            const moduleInstance = modulesById.get(moduleId);
            if (!moduleInstance) { console.error(`App Render: Module "${moduleId}" in order but not in map!`); return <div key={moduleId}>Error: Module data missing</div>; }

            const moduleDefinition = moduleRegistry.get(moduleInstance.type);
            if (!moduleDefinition) { console.error(`App Render: Module type "${moduleInstance.type}" (${moduleId}) not registered!`); return <div key={moduleId}>Error: Unknown Module Type '{moduleInstance.type}'</div>; }

            const ModuleComponent = moduleDefinition.component;
            // Define props, casting state to any for flexibility, component expects specific type
            const componentProps: { id: string; state: any; onInteraction?: (msg: SentMessage) => void } = {
                id: moduleInstance.id,
                state: moduleInstance.state,
            };
            // Conditionally add onInteraction if the module needs it
            if (moduleDefinition.isInteractive) {
                componentProps.onInteraction = handleModuleInteraction;
            }

            // --- Tooltip/Info Logic (remains the same) ---
            const handleMouseEnter = () => setHoveredInfoId(moduleId);
            const handleMouseLeave = () => setHoveredInfoId(null);
            const isHovered = hoveredInfoId === moduleId;
            const moduleDisplayName = moduleDefinition.displayName || moduleInstance.type;

            return (
                <div key={moduleInstance.id} className="module-card">
                    <div className="module-info-icon" onMouseEnter={handleMouseEnter} onMouseLeave={handleMouseLeave} aria-label={`Info for ${moduleDisplayName}: ${moduleInstance.id}`}>
                        <FontAwesomeIcon icon={faInfoCircle} />
                    </div>
                    {isHovered && (
                        <div className="module-tooltip">Type: {moduleDisplayName}<br />ID: {moduleInstance.id}</div>
                    )}
                    <ModuleComponent {...componentProps} />
                </div>
            );
        });
    };

    // --- Render Status Indicators ---
    const renderStatus = () => {
        const wsStatusText = isConnected ? 'Connected' : 'Disconnected';
        const wsStatusClass = isConnected ? 'status-connected' : 'status-disconnected';
        let heroStatusText = 'Hero: Offline';
        if (heroStatus?.status === 'online') {
            heroStatusText = `Hero: Online (v${heroStatus.version})`;
        }
        const sidekickStatusText = 'Sidekick (v' + __APP_VERSION__ + ')';

        return (
            <>
                <p className={wsStatusClass}>WebSocket: {wsStatusText}</p>
                <p className="app-version">{heroStatusText}</p>
                <p className="app-version">{sidekickStatusText}</p>
            </>
        );
    };


    // --- Main JSX Structure ---
    return (
        <div className="App">
            <header className="App-header">
                <h1>Sidekick</h1>
                <div className="status-indicators"> {/* Group status indicators */}
                    {renderStatus()}
                </div>
                <button onClick={clearAllModulesUI} disabled={moduleOrder.length === 0}>Clear UI</button>
            </header>

            <main className="App-main">
                {moduleOrder.length === 0
                    ? <p>No modules active. Waiting for Hero...</p>
                    : renderModules()}
            </main>
        </div>
    );
}

export default App;