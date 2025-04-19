// Sidekick/webapp/src/App.tsx
import React, {
    useCallback,
    useReducer,
    Reducer,
    useState,
    useRef,
    useEffect,
    createRef // Used for creating refs for imperative modules
} from 'react';
import { useWebSocket } from './hooks/useWebSocket'; // WebSocket management hook
import { moduleRegistry } from './modules/moduleRegistry'; // Maps module type to definition
import {
    // Message Types
    ReceivedMessage,
    SentMessage,
    SystemAnnounceMessage,
    GlobalClearMessage,
    ModuleControlMessage,
    ModuleEventMessage,
    ModuleErrorMessage,
    // State & Definition Types
    ModuleInstance,
    ModuleDefinition, // Removed explicit import, used via moduleRegistry
    HeroPeerInfo,
    ModuleHandle // Handle for imperative calls
} from './types'; // Shared application types
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faInfoCircle } from '@fortawesome/free-solid-svg-icons'; // Info icon
import './App.css'; // Application styles

// --- Application State Definition ---
interface AppState {
    modulesById: Map<string, ModuleInstance>; // Map: Instance ID -> Module Data & State
    moduleOrder: string[];                  // Array of instance IDs, preserves creation order
    heroStatus: HeroPeerInfo | null;        // Info about the connected Python 'Hero' script
}

// Initial state when the application loads
const initialState: AppState = {
    modulesById: new Map<string, ModuleInstance>(),
    moduleOrder: [],
    heroStatus: null,
};

// --- Reducer Actions Definition ---
// Actions describe how the state can be changed
type AppAction =
    | { type: 'PROCESS_STATE_UPDATE'; message: ModuleControlMessage } // Update state for non-imperative modules
    | { type: 'PROCESS_SPAWN'; message: ModuleControlMessage }        // Add a new module
    | { type: 'PROCESS_REMOVE'; message: ModuleControlMessage }       // Remove an existing module
    | { type: 'PROCESS_SYSTEM_ANNOUNCE'; message: SystemAnnounceMessage } // Handle Hero online/offline status
    | { type: 'PROCESS_GLOBAL_CLEAR'; message: GlobalClearMessage }   // Clear all modules (from backend command)
    | { type: 'CLEAR_ALL_MODULES_UI' }; // Clear all modules (from UI button)

// =============================================================================
// == Main Application Reducer ==
// Handles state updates based on dispatched actions.
// Primarily deals with module lifecycle (spawn/remove) and non-imperative state updates.
// =============================================================================
const rootReducer: Reducer<AppState, AppAction> = (state, action): AppState => {
    switch (action.type) {
        // --- Handle Spawn ---
        // Adds a new module instance to the state
        case 'PROCESS_SPAWN': {
            const { module: moduleType, target, payload } = action.message;

            // Prevent duplicate IDs
            if (state.modulesById.has(target)) {
                console.warn(`Reducer: Spawn failed - Duplicate ID "${target}".`);
                return state; // No change
            }

            // Find the module definition in the registry
            const moduleDefinition = moduleRegistry.get(moduleType);
            if (!moduleDefinition) {
                console.warn(`Reducer: Spawn failed - Unknown module type "${moduleType}".`);
                return state; // No change
            }

            try {
                // Get the initial state from the module's logic function
                const initialModuleState = moduleDefinition.getInitialState(target, payload);
                const newModuleInstance: ModuleInstance = {
                    id: target,
                    type: moduleType,
                    state: initialModuleState
                };

                // Create new state maps/arrays (immutability)
                const newModulesById = new Map(state.modulesById).set(target, newModuleInstance);
                const newModuleOrder = [...state.moduleOrder, target]; // Add ID to the end

                console.log(`Reducer: Spawned module "${target}" (Type: ${moduleType}). Current order:`, newModuleOrder);
                return { ...state, modulesById: newModulesById, moduleOrder: newModuleOrder };

            } catch (error: any) {
                console.error(`Reducer: Error during getInitialState for module "${target}" (${moduleType}):`, error.message || error);
                return state; // Return original state on error
            }
        }

        // --- Handle Non-Imperative State Updates ---
        // Updates the state for modules that *don't* use the imperative handle
        case 'PROCESS_STATE_UPDATE': {
            const { module: moduleType, target, payload } = action.message;

            const currentModule = state.modulesById.get(target);
            if (!currentModule) {
                console.warn(`Reducer: State Update failed - Module "${target}" not found.`);
                return state; // No change
            }

            const moduleDefinition = moduleRegistry.get(moduleType);
            // This action should only be dispatched for non-imperative modules
            if (!moduleDefinition || moduleDefinition.imperativeUpdate) {
                console.error(`Reducer: State Update failed - Module type mismatch or unexpected imperative module "${target}" (${moduleType})`);
                return state; // No change
            }
            if (payload === undefined) {
                console.warn(`Reducer: State Update failed - Missing payload for "${target}".`);
                return state; // No change
            }

            try {
                // Call the module's specific updateState function
                const updatedModuleState = moduleDefinition.updateState(currentModule.state, payload as any);

                // If updateState returned the exact same state object, no actual change occurred
                if (updatedModuleState === currentModule.state) {
                    return state;
                }

                // Create new state map with the updated instance
                const updatedModuleInstance = { ...currentModule, state: updatedModuleState };
                const newModulesById = new Map(state.modulesById).set(target, updatedModuleInstance);

                // console.debug(`Reducer: Updated state for module "${target}" (${moduleType})`);
                return { ...state, modulesById: newModulesById };

            } catch (error: any) {
                console.error(`Reducer: Error during updateState for module "${target}" (${moduleType}):`, error.message || error);
                return state; // Return original state on error
            }
        }

        // --- Handle Remove ---
        // Removes a module instance from the state
        case 'PROCESS_REMOVE': {
            const { target } = action.message;

            // Check if the module actually exists
            if (!state.modulesById.has(target)) {
                return state; // Already removed, no change needed
            }

            // Create new map and array without the removed module
            const newModulesById = new Map(state.modulesById);
            newModulesById.delete(target);
            const newModuleOrder = state.moduleOrder.filter(id => id !== target);

            console.log(`Reducer: Removed module "${target}". Current order:`, newModuleOrder);
            return { ...state, modulesById: newModulesById, moduleOrder: newModuleOrder };
        }

        // --- Handle System Announce (Hero Status) ---
        case 'PROCESS_SYSTEM_ANNOUNCE': {
            const { payload } = action.message;

            // Only process announcements from the 'hero' role
            if (payload && payload.role === 'hero') {
                console.log(`Reducer: Processing Hero announce (PeerID: ${payload.peerId}, Status: ${payload.status})`);
                // Determine the new status object (null if offline)
                const newHeroStatus: HeroPeerInfo | null = payload.status === 'online' ? { ...payload, role: 'hero' } : null;

                // Only update state if the status or peer ID actually changed
                if (state.heroStatus?.peerId !== newHeroStatus?.peerId || state.heroStatus?.status !== newHeroStatus?.status) {
                    return { ...state, heroStatus: newHeroStatus };
                }
            }
            // Ignore announcements from 'sidekick' or other roles
            return state; // No relevant change
        }

        // --- Handle Global Clear (from backend) ---
        case 'PROCESS_GLOBAL_CLEAR': {
            console.log("Reducer: Processing global/clearAll command from backend.");
            // Only update if there are modules to clear
            if (state.modulesById.size > 0 || state.moduleOrder.length > 0) {
                // Reset maps and order, keep hero status
                return { ...initialState, heroStatus: state.heroStatus };
            }
            return state; // Already cleared
        }

        // --- Handle Clear All (from UI button) ---
        case 'CLEAR_ALL_MODULES_UI': {
            console.log("Reducer: Clearing all modules via UI action.");
            if (state.modulesById.size > 0 || state.moduleOrder.length > 0) {
                // Reset maps and order, keep hero status
                return { ...initialState, heroStatus: state.heroStatus };
            }
            return state; // Already cleared
        }

        // Default case for unknown actions
        default:
            console.warn("Reducer: Received unknown action type:", (action as any)?.type);
            return state;
    }
};

// =============================================================================
// == Main Application Component ==
// Orchestrates WebSocket connection, state management, and rendering of modules.
// =============================================================================
function App() {
    const [appState, dispatch] = useReducer(rootReducer, initialState);
    const { modulesById, moduleOrder, heroStatus } = appState;
    const [hoveredInfoId, setHoveredInfoId] = useState<string | null>(null); // Tracks hovered info icon for tooltips

    // --- Refs ---
    // Stores refs to component instances that handle updates imperatively
    const imperativeModuleRefs = useRef<Map<string, React.RefObject<ModuleHandle | null>>>(new Map());
    // Stores payloads for imperative updates that arrived before the component was ready
    const pendingImperativeUpdates = useRef<Map<string, any[]>>(new Map()); // Key: moduleId, Value: array of payloads

    // --- Callback: Process Pending Updates when a Module Signals Ready ---
    // Passed as `onReady` prop to imperative modules.
    const onModuleReady = useCallback((moduleId: string) => {
        console.log(`App: Received ready signal from module "${moduleId}".`);

        // Check if there are pending updates queued for this module
        const pendingUpdates = pendingImperativeUpdates.current.get(moduleId);
        const moduleRef = imperativeModuleRefs.current.get(moduleId);

        // Ensure pending updates exist AND the module's handle/method is now available
        if (pendingUpdates && pendingUpdates.length > 0 && moduleRef?.current?.processUpdate) {
            console.log(`App: Processing ${pendingUpdates.length} queued update(s) for ready module "${moduleId}".`);

            // Get a stable reference to the processing function
            const processUpdateFunc = moduleRef.current.processUpdate;
            try {
                // Process each queued payload using the module's imperative function
                pendingUpdates.forEach(payload => {
                    processUpdateFunc(payload);
                });
            } catch (error) {
                console.error(`App: Error processing queued updates for module "${moduleId}":`, error);
                // Consider sending an error back to the backend/Python side here
            } finally {
                // CRITICAL: Clear the queue for this module after attempting to process
                pendingImperativeUpdates.current.delete(moduleId);
                console.log(`App: Cleared pending update queue for "${moduleId}".`);
            }
        } else if (pendingUpdates && pendingUpdates.length > 0) {
            // This case might happen in rare edge cases or if the handle setup is slow
            console.warn(`App: Module "${moduleId}" signaled ready, but its imperative handle/processUpdate is still not available. ${pendingUpdates.length} update(s) remain queued.`);
        } else {
            console.debug(`App: Module "${moduleId}" is ready, no pending updates found.`);
        }
    }, []); // This callback has no dependencies as it only interacts with refs

    // --- Callback: Handle Incoming WebSocket Messages ---
    // This function decides whether to dispatch to the reducer or call an imperative handle
    const handleWebSocketMessage = useCallback((messageData: any) => {
        // Basic message structure validation
        if (typeof messageData !== 'object' || messageData === null || !messageData.module || !messageData.type) {
            console.error("App: Received invalid message structure from WebSocket:", messageData);
            return;
        }

        const message = messageData as ReceivedMessage; // Type assertion

        // --- Route 'update' messages based on module type ---
        if (message.type === 'update' && 'target' in message) {
            const moduleMessage = message as ModuleControlMessage;
            const moduleDefinition = moduleRegistry.get(moduleMessage.module);

            // Check if this module type uses imperative updates
            if (moduleDefinition?.imperativeUpdate) {
                const moduleRef = imperativeModuleRefs.current.get(moduleMessage.target);

                // Check if the component's handle and processUpdate method are ready
                if (moduleRef?.current?.processUpdate) {
                    // Handle is ready: Call the component's method directly
                    // console.debug(`App: Routing update for "${moduleMessage.target}" imperatively.`);
                    try {
                        moduleRef.current.processUpdate(moduleMessage.payload);
                    } catch (error) {
                        console.error(`App: Error calling imperative processUpdate for "${moduleMessage.target}":`, error);
                        // Future: Consider sending error back via sendMessage
                    }
                } else {
                    // Handle is not ready: Queue the payload
                    console.debug(`App: Queuing update for imperative module "${moduleMessage.target}" (handle not ready). Payload:`, moduleMessage.payload);
                    const queue = pendingImperativeUpdates.current.get(moduleMessage.target) || [];
                    queue.push(moduleMessage.payload);
                    pendingImperativeUpdates.current.set(moduleMessage.target, queue);
                }
                // ** Stop further processing for this message **
                return;
            } else {
                // Not an imperative module: Dispatch to reducer for normal state update
                dispatch({ type: 'PROCESS_STATE_UPDATE', message: moduleMessage });
                return; // Message processed
            }
        }

        // --- Route other message types to the reducer ---
        if (message.type === 'spawn' && 'target' in message) {
            dispatch({ type: 'PROCESS_SPAWN', message: message as ModuleControlMessage });
        } else if (message.type === 'remove' && 'target' in message) {
            dispatch({ type: 'PROCESS_REMOVE', message: message as ModuleControlMessage });
        } else if (message.module === 'system' && message.type === 'announce') {
            dispatch({ type: 'PROCESS_SYSTEM_ANNOUNCE', message: message as SystemAnnounceMessage });
        } else if (message.module === 'global' && message.type === 'clearAll') {
            dispatch({ type: 'PROCESS_GLOBAL_CLEAR', message: message as GlobalClearMessage });
        } else {
            // Log unhandled message types
            console.warn("App: Received unhandled message type:", message);
        }

    }, [/* No dependencies: uses refs and dispatch (stable) */]);

    // --- WebSocket Connection Setup ---
    const { isConnected, status, sendMessage } = useWebSocket(handleWebSocketMessage);

    // --- Effect: Clean Up Refs and Pending Queues for Removed Modules ---
    useEffect(() => {
        const currentModuleIds = new Set(moduleOrder);
        const refsAndQueuesToRemove: string[] = [];

        // Find refs/queues corresponding to modules that are no longer in moduleOrder
        imperativeModuleRefs.current.forEach((_, moduleId) => {
            if (!currentModuleIds.has(moduleId)) {
                refsAndQueuesToRemove.push(moduleId);
            }
        });
        pendingImperativeUpdates.current.forEach((_, moduleId) => {
            if (!currentModuleIds.has(moduleId) && !refsAndQueuesToRemove.includes(moduleId)) {
                refsAndQueuesToRemove.push(moduleId); // Catch queues for modules removed before ready
            }
        });


        // Perform cleanup if any stale entries were found
        if (refsAndQueuesToRemove.length > 0) {
            console.log(`App: Cleaning up refs and pending queues for removed modules: ${refsAndQueuesToRemove.join(', ')}`);
            refsAndQueuesToRemove.forEach(moduleId => {
                imperativeModuleRefs.current.delete(moduleId);
                pendingImperativeUpdates.current.delete(moduleId);
            });
        }
    }, [moduleOrder]); // Rerun whenever the list of active modules changes

    // --- Callback: Handle Interactions from Child Modules (e.g., clicks, input) ---
    // Sends event/error messages back to the backend via WebSocket
    const handleModuleInteraction = useCallback((interactionMessage: SentMessage) => {
        // Validate structure before sending
        if (!interactionMessage || !interactionMessage.module || !interactionMessage.type) {
            console.error("App: Invalid interaction message structure from component:", interactionMessage);
            return;
        }

        // Only send event/error types initiated by the UI component interaction
        if (interactionMessage.type === 'event' || interactionMessage.type === 'error') {
            // Ensure the source ID ('src') is present for event/error messages
            const eventOrErrorMsg = interactionMessage as ModuleEventMessage | ModuleErrorMessage;
            if (eventOrErrorMsg.src) {
                sendMessage(eventOrErrorMsg); // Send validated message
            } else {
                console.error("App: Invalid event/error message missing 'src' field:", interactionMessage);
            }
        } else if (interactionMessage.module === 'system' && interactionMessage.type === 'announce') {
            // Allow sending system messages if needed (though usually handled by useWebSocket)
            sendMessage(interactionMessage);
        }
        else {
            console.error("App: Attempted to send message of unexpected type via interaction:", interactionMessage);
        }
    }, [sendMessage]); // Dependency: sendMessage ensures stability

    // --- Callback: Handle UI "Clear All" Button Click ---
    const clearAllModulesUI = useCallback(() => {
        // Dispatch action to clear local UI state
        dispatch({ type: 'CLEAR_ALL_MODULES_UI' });
        // Note: This only clears the UI state. It does not send a global/clearAll
        // command to the backend by default. That's typically handled by the
        // Python side's connection logic (clear_on_connect/disconnect) or explicit calls.
    }, []);

    // --- Render Helper: Render Status Indicators in Header ---
    const renderStatus = () => {
        // Determine WebSocket status text based on the 'status' state variable
        let wsStatusText = 'Unknown';
        switch (status) {
            case 'connecting': wsStatusText = 'Connecting...'; break;
            case 'connected': wsStatusText = 'Connected'; break;
            case 'disconnected': wsStatusText = 'Disconnected'; break;
            case 'reconnecting': wsStatusText = 'Reconnecting...'; break;
        }
        const wsStatusClass = isConnected ? 'status-connected' : 'status-disconnected';

        // Determine Hero status text and class
        let heroStatusText = 'Hero: Offline';
        let heroStatusClass = 'hero-status-offline'; // Default class
        if (heroStatus?.status === 'online') {
            // Include version if available
            heroStatusText = `Hero: Online (v${heroStatus.version || '?'})`;
            heroStatusClass = 'hero-status-online'; // Apply online style class
        }

        // Get Sidekick (this webapp) version from injected variable
        const sidekickStatusText = `Sidekick (v${__APP_VERSION__})`;

        return (
            <>
                <p className={wsStatusClass}>WebSocket: {wsStatusText}</p>
                <p className={heroStatusClass}>{heroStatusText}</p>
                <p className="app-version">{sidekickStatusText}</p>
            </>
        );
    };

    // --- Render Helper: Render Active Modules ---
    const renderModules = () => {
        // Iterate over the moduleOrder array to render modules in the correct sequence
        return moduleOrder.map(moduleId => {
            const moduleInstance = modulesById.get(moduleId);

            // Safety check: Ensure module data exists
            if (!moduleInstance) {
                console.error(`App Render: Module data for ID "${moduleId}" not found in state map!`);
                return <div key={moduleId} className="module-card error">Error: Module data missing for {moduleId}</div>;
            }

            // Find the corresponding module definition from the registry
            const moduleDefinition = moduleRegistry.get(moduleInstance.type);
            if (!moduleDefinition) {
                console.error(`App Render: Module definition for type "${moduleInstance.type}" (ID: "${moduleId}") not registered!`);
                return <div key={moduleId} className="module-card error">Error: Unknown Module Type '{moduleInstance.type}'</div>;
            }

            const ModuleComponent = moduleDefinition.component; // Get the React component constructor
            let moduleRef: React.RefObject<ModuleHandle | null > | undefined = undefined; // Ref for imperative modules

            // --- Ref Management: Get or Create Ref for Imperative Modules ---
            if (moduleDefinition.imperativeUpdate) {
                // If a ref for this ID doesn't exist in our map yet, create it
                if (!imperativeModuleRefs.current.has(moduleId)) {
                    console.debug(`App Render: Creating ref for imperative module "${moduleId}"`);
                    imperativeModuleRefs.current.set(moduleId, createRef<ModuleHandle | null>());
                }
                // Retrieve the ref (guaranteed to exist now)
                moduleRef = imperativeModuleRefs.current.get(moduleId);
            }

            // --- Prepare Props for the Module Component ---
            // Use 'any' for props temporarily for easier prop spreading, consider stricter typing if needed
            const componentProps: any = {
                id: moduleInstance.id,
                state: moduleInstance.state, // Pass module-specific state
                onInteraction: handleModuleInteraction, // Pass interaction callback
            };
            // Conditionally add the onReady prop only for imperative modules
            if (moduleDefinition.imperativeUpdate) {
                componentProps.onReady = onModuleReady;
            }

            // --- Tooltip Logic (for displaying module type/ID on hover) ---
            const handleMouseEnterInfo = () => setHoveredInfoId(moduleId);
            const handleMouseLeaveInfo = () => setHoveredInfoId(null);
            const isInfoHovered = hoveredInfoId === moduleId;
            const moduleDisplayName = moduleDefinition.displayName || moduleInstance.type; // Use display name or type string

            // Render the module within a styled card container
            return (
                <div key={moduleInstance.id} className="module-card">
                    {/* Info Icon & Tooltip */}
                    <div
                        className="module-info-icon"
                        onMouseEnter={handleMouseEnterInfo}
                        onMouseLeave={handleMouseLeaveInfo}
                        aria-label={`Info for ${moduleDisplayName}: ${moduleInstance.id}`}
                    >
                        <FontAwesomeIcon icon={faInfoCircle} />
                    </div>
                    {isInfoHovered && (
                        <div className="module-tooltip">
                            Type: {moduleDisplayName}
                            <br />
                            ID: {moduleInstance.id}
                        </div>
                    )}
                    {/* Render the actual module component, passing ref and props */}
                    <ModuleComponent ref={moduleRef} {...componentProps} />
                </div>
            );
        }); // End map over moduleOrder
    };

    // --- Main Application JSX Structure ---
    return (
        <div className="App">
            {/* Application Header */}
            <header className="App-header">
                <h1>Sidekick</h1>
                <div className="status-indicators">
                    {renderStatus()} {/* Render dynamic status indicators */}
                </div>
                <button
                    onClick={clearAllModulesUI}
                    disabled={moduleOrder.length === 0} // Disable button if no modules are present
                    title="Clear all modules from the UI"
                >
                    Clear UI
                </button>
            </header>

            {/* Main Content Area */}
            <main className="App-main">
                {moduleOrder.length === 0
                    // Display message when no modules are active
                    ? <p>No modules active. Waiting for Hero script...</p>
                    // Otherwise, render the active modules
                    : renderModules()
                }
            </main>
        </div>
    );
}

export default App;