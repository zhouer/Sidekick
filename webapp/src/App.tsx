import React, {
    useCallback,
    useReducer,
    Reducer,
    useState,
    useRef,
    useEffect,
    createRef // Used for creating refs for imperative components
} from 'react';
import { useCommunication, CommunicationMode } from './hooks/useCommunication'; // Communication management hook
import { componentRegistry } from './components/componentRegistry'; // Maps component type to definition
import {
    // Message Types
    ReceivedMessage,
    SentMessage,
    SystemAnnounceMessage,
    GlobalClearMessage,
    ComponentControlMessage,
    ComponentEventMessage,
    ComponentErrorMessage,
    // State & Definition Types
    ComponentInstance,
    HeroPeerInfo,
    ComponentHandle // Handle for imperative calls
} from './types'; // Shared application types
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faInfoCircle } from '@fortawesome/free-solid-svg-icons'; // Info icon
import './App.css'; // Application styles

// --- Application State Definition ---
interface AppState {
    componentsById: Map<string, ComponentInstance>; // Map: Instance ID -> Component Data & State
    componentOrder: string[];                       // Array of instance IDs, preserves creation order
    heroStatus: HeroPeerInfo | null;                // Info about the connected Python 'Hero' script
}

// Initial state when the application loads
const initialState: AppState = {
    componentsById: new Map<string, ComponentInstance>(),
    componentOrder: [],
    heroStatus: null,
};

// --- Reducer Actions Definition ---
// Actions describe how the state can be changed
type AppAction =
    | { type: 'PROCESS_STATE_UPDATE'; message: ComponentControlMessage }  // Update state for non-imperative components
    | { type: 'PROCESS_SPAWN'; message: ComponentControlMessage }         // Add a new component
    | { type: 'PROCESS_REMOVE'; message: ComponentControlMessage }        // Remove an existing component
    | { type: 'PROCESS_SYSTEM_ANNOUNCE'; message: SystemAnnounceMessage } // Handle Hero online/offline status
    | { type: 'PROCESS_GLOBAL_CLEAR'; message: GlobalClearMessage };      // Clear all components (from backend command)

// =============================================================================
// == Main Application Reducer ==
// Handles state updates based on dispatched actions.
// Primarily deals with component lifecycle (spawn/remove) and non-imperative state updates.
// =============================================================================
const rootReducer: Reducer<AppState, AppAction> = (state, action): AppState => {
    switch (action.type) {
        // --- Handle Spawn ---
        // Adds a new component instance to the state
        case 'PROCESS_SPAWN': {
            const { component: componentType, target, payload } = action.message;

            // Prevent duplicate IDs
            if (state.componentsById.has(target)) {
                console.warn(`Reducer: Spawn failed - Duplicate ID "${target}".`);
                return state; // No change
            }

            // Find the component definition in the registry
            const componentDefinition = componentRegistry.get(componentType);
            if (!componentDefinition) {
                console.warn(`Reducer: Spawn failed - Unknown component type "${componentType}".`);
                return state; // No change
            }

            try {
                // Get the initial state from the component's logic function
                const initialComponentState = componentDefinition.getInitialState(target, payload);
                const newComponentInstance: ComponentInstance = {
                    id: target,
                    type: componentType,
                    state: initialComponentState
                };

                // Create new state maps/arrays (immutability)
                const newComponentById = new Map(state.componentsById).set(target, newComponentInstance);
                const newComponentOrder = [...state.componentOrder, target]; // Add ID to the end

                console.log(`Reducer: Spawned component "${target}" (Type: ${componentType}). Current order:`, newComponentOrder);
                return { ...state, componentsById: newComponentById, componentOrder: newComponentOrder };

            } catch (error: any) {
                console.error(`Reducer: Error during getInitialState for component "${target}" (${componentType}):`, error.message || error);
                return state; // Return original state on error
            }
        }

        // --- Handle Non-Imperative State Updates ---
        // Updates the state for components that *don't* use the imperative handle
        case 'PROCESS_STATE_UPDATE': {
            const { component: componentType, target, payload } = action.message;

            const currentComponent = state.componentsById.get(target);
            if (!currentComponent) {
                console.warn(`Reducer: State Update failed - Component "${target}" not found.`);
                return state; // No change
            }

            const componentDefinition = componentRegistry.get(componentType);
            // This action should only be dispatched for non-imperative components
            if (!componentDefinition || componentDefinition.imperativeUpdate) {
                console.error(`Reducer: State Update failed - Component type mismatch or unexpected imperative component "${target}" (${componentType})`);
                return state; // No change
            }
            if (payload === undefined) {
                console.warn(`Reducer: State Update failed - Missing payload for "${target}".`);
                return state; // No change
            }

            try {
                // Call the component's specific updateState function
                const updatedComponentState = componentDefinition.updateState(currentComponent.state, payload as any);

                // If updateState returned the exact same state object, no actual change occurred
                if (updatedComponentState === currentComponent.state) {
                    return state;
                }

                // Create new state map with the updated instance
                const updatedComponentInstance = { ...currentComponent, state: updatedComponentState };
                const newComponentsById = new Map(state.componentsById).set(target, updatedComponentInstance);

                // console.debug(`Reducer: Updated state for component "${target}" (${componentType})`);
                return { ...state, componentsById: newComponentsById };

            } catch (error: any) {
                console.error(`Reducer: Error during updateState for component "${target}" (${componentType}):`, error.message || error);
                return state; // Return original state on error
            }
        }

        // --- Handle Remove ---
        // Removes a component instance from the state
        case 'PROCESS_REMOVE': {
            const { target } = action.message;

            // Check if the component actually exists
            if (!state.componentsById.has(target)) {
                return state; // Already removed, no change needed
            }

            // Create new map and array without the removed component
            const newComponentsById = new Map(state.componentsById);
            newComponentsById.delete(target);
            const newComponentOrder = state.componentOrder.filter(id => id !== target);

            console.log(`Reducer: Removed component "${target}". Current order:`, newComponentOrder);
            return { ...state, componentsById: newComponentsById, componentOrder: newComponentOrder };
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
            // Only update if there are components to clear
            if (state.componentsById.size > 0 || state.componentOrder.length > 0) {
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
// Orchestrates WebSocket connection, state management, and rendering of components.
// =============================================================================
function App() {
    const [appState, dispatch] = useReducer(rootReducer, initialState);
    const { componentsById, componentOrder, heroStatus } = appState;
    const [hoveredInfoId, setHoveredInfoId] = useState<string | null>(null); // Tracks hovered info icon for tooltips

    // --- Refs ---
    // Stores refs to component instances that handle updates imperatively
    const imperativeComponentRefs = useRef<Map<string, React.RefObject<ComponentHandle | null>>>(new Map());
    // Stores payloads for imperative updates that arrived before the component was ready
    const pendingImperativeUpdates = useRef<Map<string, any[]>>(new Map()); // Key: componentId, Value: array of payloads

    // --- Callback: Process Pending Updates when a Component Signals Ready ---
    // Passed as `onReady` prop to imperative components.
    const onComponentReady = useCallback((componentId: string) => {
        console.log(`App: Received ready signal from component "${componentId}".`);

        // Check if there are pending updates queued for this component
        const pendingUpdates = pendingImperativeUpdates.current.get(componentId);
        const componentRef = imperativeComponentRefs.current.get(componentId);

        // Ensure pending updates exist AND the component's handle/method is now available
        if (pendingUpdates && pendingUpdates.length > 0 && componentRef?.current?.processUpdate) {
            console.log(`App: Processing ${pendingUpdates.length} queued update(s) for ready component "${componentId}".`);

            // Get a stable reference to the processing function
            const processUpdateFunc = componentRef.current.processUpdate;
            try {
                // Process each queued payload using the component's imperative function
                pendingUpdates.forEach(payload => {
                    processUpdateFunc(payload);
                });
            } catch (error) {
                console.error(`App: Error processing queued updates for component "${componentId}":`, error);
                // Consider sending an error back to the backend/Python side here
            } finally {
                // CRITICAL: Clear the queue for this component after attempting to process
                pendingImperativeUpdates.current.delete(componentId);
                console.log(`App: Cleared pending update queue for "${componentId}".`);
            }
        } else if (pendingUpdates && pendingUpdates.length > 0) {
            // This case might happen in rare edge cases or if the handle setup is slow
            console.warn(`App: Component "${componentId}" signaled ready, but its imperative handle/processUpdate is still not available. ${pendingUpdates.length} update(s) remain queued.`);
        } else {
            console.debug(`App: Component "${componentId}" is ready, no pending updates found.`);
        }
    }, []); // This callback has no dependencies as it only interacts with refs

    // --- Callback: Handle Incoming Sidekick Messages ---
    // This function decides whether to dispatch to the reducer or call an imperative handle
    const handleSidekickMessage = useCallback((messageData: any) => {
        // Basic message structure validation
        if (typeof messageData !== 'object' || messageData === null || !messageData.component || !messageData.type) {
            console.error("App: Received invalid message structure from Sidekick:", messageData);
            return;
        }

        const message = messageData as ReceivedMessage; // Type assertion

        // --- Route 'update' messages based on component type ---
        if (message.type === 'update' && 'target' in message) {
            const componentMessage = message as ComponentControlMessage;
            const componentDefinition = componentRegistry.get(componentMessage.component);

            // Check if this component type uses imperative updates
            if (componentDefinition?.imperativeUpdate) {
                const componentRef = imperativeComponentRefs.current.get(componentMessage.target);

                // Check if the component's handle and processUpdate method are ready
                if (componentRef?.current?.processUpdate) {
                    // Handle is ready: Call the component's method directly
                    // console.debug(`App: Routing update for "${componentMessage.target}" imperatively.`);
                    try {
                        componentRef.current.processUpdate(componentMessage.payload);
                    } catch (error) {
                        console.error(`App: Error calling imperative processUpdate for "${componentMessage.target}":`, error);
                        // Future: Consider sending error back via sendMessage
                    }
                } else {
                    // Handle is not ready: Queue the payload
                    console.debug(`App: Queuing update for imperative component "${componentMessage.target}" (handle not ready). Payload:`, componentMessage.payload);
                    const queue = pendingImperativeUpdates.current.get(componentMessage.target) || [];
                    queue.push(componentMessage.payload);
                    pendingImperativeUpdates.current.set(componentMessage.target, queue);
                }
                // ** Stop further processing for this message **
                return;
            } else {
                // Not an imperative component: Dispatch to reducer for normal state update
                dispatch({ type: 'PROCESS_STATE_UPDATE', message: componentMessage });
                return; // Message processed
            }
        }

        // --- Route other message types to the reducer ---
        if (message.type === 'spawn' && 'target' in message) {
            dispatch({ type: 'PROCESS_SPAWN', message: message as ComponentControlMessage });
        } else if (message.type === 'remove' && 'target' in message) {
            dispatch({ type: 'PROCESS_REMOVE', message: message as ComponentControlMessage });
        } else if (message.component === 'system' && message.type === 'announce') {
            dispatch({ type: 'PROCESS_SYSTEM_ANNOUNCE', message: message as SystemAnnounceMessage });
        } else if (message.component === 'global' && message.type === 'clearAll') {
            dispatch({ type: 'PROCESS_GLOBAL_CLEAR', message: message as GlobalClearMessage });
        } else {
            // Log unhandled message types
            console.warn("App: Received unhandled message type:", message);
        }

    }, [/* No dependencies: uses refs and dispatch (stable) */]);

    // --- Communication Setup (WebSocket or Pyodide) ---
    const { 
        mode, 
        isConnected, 
        status, 
        sendMessage, 
        runScript, 
        stopScript
    } = useCommunication(handleSidekickMessage);

    // --- Effect: Clean Up Refs and Pending Queues for Removed Components ---
    useEffect(() => {
        const currentComponentIds = new Set(componentOrder);
        const refsAndQueuesToRemove: string[] = [];

        // Find refs/queues corresponding to components that are no longer in componentOrder
        imperativeComponentRefs.current.forEach((_, componentId) => {
            if (!currentComponentIds.has(componentId)) {
                refsAndQueuesToRemove.push(componentId);
            }
        });
        pendingImperativeUpdates.current.forEach((_, componentId) => {
            if (!currentComponentIds.has(componentId) && !refsAndQueuesToRemove.includes(componentId)) {
                refsAndQueuesToRemove.push(componentId); // Catch queues for components removed before ready
            }
        });


        // Perform cleanup if any stale entries were found
        if (refsAndQueuesToRemove.length > 0) {
            console.log(`App: Cleaning up refs and pending queues for removed components: ${refsAndQueuesToRemove.join(', ')}`);
            refsAndQueuesToRemove.forEach(componentId => {
                imperativeComponentRefs.current.delete(componentId);
                pendingImperativeUpdates.current.delete(componentId);
            });
        }
    }, [componentOrder]); // Rerun whenever the list of active components changes

    // --- Callback: Handle Interactions from Child Components (e.g., clicks, input) ---
    // Sends event/error messages back to the backend via WebSocket
    const handleComponentInteraction = useCallback((interactionMessage: SentMessage) => {
        // Validate structure before sending
        if (!interactionMessage || !interactionMessage.component || !interactionMessage.type) {
            console.error("App: Invalid interaction message structure from component:", interactionMessage);
            return;
        }

        // Only send event/error types initiated by the UI component interaction
        if (interactionMessage.type === 'event' || interactionMessage.type === 'error') {
            // Ensure the source ID ('src') is present for event/error messages
            const eventOrErrorMsg = interactionMessage as ComponentEventMessage | ComponentErrorMessage;
            if (eventOrErrorMsg.src) {
                sendMessage(eventOrErrorMsg); // Send validated message
            } else {
                console.error("App: Invalid event/error message missing 'src' field:", interactionMessage);
            }
        } else if (interactionMessage.component === 'system' && interactionMessage.type === 'announce') {
            // Allow sending system messages if needed (though usually handled by useWebSocket)
            sendMessage(interactionMessage);
        }
        else {
            console.error("App: Attempted to send message of unexpected type via interaction:", interactionMessage);
        }
    }, [sendMessage]); // Dependency: sendMessage ensures stability

    // --- Render Helper: Render Status Indicators in Header ---
    const renderStatus = () => {
        // Get Sidekick (this webapp) version from injected variable
        const sidekickStatusText = `Sidekick (v${__APP_VERSION__})`;

        // Determine Hero status text and class
        let heroStatusText = 'Hero: Offline';
        let heroStatusClass = 'hero-status-offline'; // Default class
        if (heroStatus?.status === 'online') {
            // Include version if available
            // heroStatusText = `Hero: Online (v${heroStatus.version || '?'})`;
            heroStatusText = `Hero: Online`;
            heroStatusClass = 'hero-status-online'; // Apply online style class
        }

        if (mode === 'websocket') {
            // Determine WebSocket status text based on the 'status' state variable
            let wsStatusText = 'Unknown';
            switch (status) {
                case 'connecting': wsStatusText = 'Connecting'; break;
                case 'connected': wsStatusText = 'Connected'; break;
                case 'disconnected': wsStatusText = 'Disconnected'; break;
                case 'reconnecting': wsStatusText = 'Reconnecting'; break;
            }
            const wsStatusClass = isConnected ? 'status-connected' : 'status-disconnected';

            return (
                <>
                    <p className={wsStatusClass}>WebSocket: {wsStatusText}</p>
                    <p className={heroStatusClass}>{heroStatusText}</p>
                    {/*<p className="app-version">{sidekickStatusText}</p>*/}
                </>
            );
        } else {
            // Script mode status
            let scriptStatusText = 'Script: Unknown';
            let scriptStatusClass = 'status-neutral';

            switch (status) {
                case 'initializing': scriptStatusText = 'Script: Initializing'; scriptStatusClass = 'status-neutral'; break;
                case 'ready': scriptStatusText = 'Script: Ready'; scriptStatusClass = 'status-connected'; break;
                case 'running': scriptStatusText = 'Script: Running'; scriptStatusClass = 'status-connected'; break;
                case 'stopping': scriptStatusText = 'Script: Stopping'; scriptStatusClass = 'status-neutral'; break;
                case 'stopped': scriptStatusText = 'Script: Stopped'; scriptStatusClass = 'status-neutral'; break;
                case 'error': scriptStatusText = 'Script: Error'; scriptStatusClass = 'status-disconnected'; break;
                case 'terminated': scriptStatusText = 'Script: Terminated'; scriptStatusClass = 'status-neutral'; break;
            }

            return (
                <>
                    <p className={scriptStatusClass}>{scriptStatusText}</p>
                    <p className={heroStatusClass}>{heroStatusText}</p>
                    {/*<p className="app-version">{sidekickStatusText}</p>*/}
                </>
            );
        }
    };

    // --- Render Helper: Render Active Components ---
    const renderComponents = () => {
        // Iterate over the componentOrder array to render components in the correct sequence
        return componentOrder.map(componentId => {
            const componentInstance = componentsById.get(componentId);

            // Safety check: Ensure component data exists
            if (!componentInstance) {
                console.error(`App Render: Component data for ID "${componentId}" not found in state map!`);
                return <div key={componentId} className="component-card error">Error: Component data missing for {componentId}</div>;
            }

            // Find the corresponding component definition from the registry
            const componentDefinition = componentRegistry.get(componentInstance.type);
            if (!componentDefinition) {
                console.error(`App Render: Component definition for type "${componentInstance.type}" (ID: "${componentId}") not registered!`);
                return <div key={componentId} className="component-card error">Error: Unknown Component Type '{componentInstance.type}'</div>;
            }

            const Component = componentDefinition.component; // Get the React component constructor
            let componentRef: React.RefObject<ComponentHandle | null > | undefined = undefined; // Ref for imperative components

            // --- Ref Management: Get or Create Ref for Imperative Components ---
            if (componentDefinition.imperativeUpdate) {
                // If a ref for this ID doesn't exist in our map yet, create it
                if (!imperativeComponentRefs.current.has(componentId)) {
                    console.debug(`App Render: Creating ref for imperative component "${componentId}"`);
                    imperativeComponentRefs.current.set(componentId, createRef<ComponentHandle | null>());
                }
                // Retrieve the ref (guaranteed to exist now)
                componentRef = imperativeComponentRefs.current.get(componentId);
            }

            // --- Prepare Props for the Component ---
            // Use 'any' for props temporarily for easier prop spreading, consider stricter typing if needed
            const componentProps: any = {
                id: componentInstance.id,
                state: componentInstance.state, // Pass component-specific state
                onInteraction: handleComponentInteraction, // Pass interaction callback
            };
            // Conditionally add the onReady prop only for imperative components
            if (componentDefinition.imperativeUpdate) {
                componentProps.onReady = onComponentReady;
            }

            // --- Tooltip Logic (for displaying component type/ID on hover) ---
            const handleMouseEnterInfo = () => setHoveredInfoId(componentId);
            const handleMouseLeaveInfo = () => setHoveredInfoId(null);
            const isInfoHovered = hoveredInfoId === componentId;
            const componentDisplayName = componentDefinition.displayName || componentInstance.type; // Use display name or type string

            // Render the component within a styled card container
            return (
                <div key={componentInstance.id} className="component-card">
                    {/* Info Icon & Tooltip */}
                    <div
                        className="component-info-icon"
                        onMouseEnter={handleMouseEnterInfo}
                        onMouseLeave={handleMouseLeaveInfo}
                        aria-label={`Info for ${componentDisplayName}: ${componentInstance.id}`}
                    >
                        <FontAwesomeIcon icon={faInfoCircle} />
                    </div>
                    {isInfoHovered && (
                        <div className="component-tooltip">
                            Type: {componentDisplayName}
                            <br />
                            ID: {componentInstance.id}
                        </div>
                    )}
                    {/* Render the actual component, passing ref and props */}
                    <Component ref={componentRef} {...componentProps} />
                </div>
            );
        }); // End map over componentOrder
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
                {mode === 'script' && (
                    <div className="script-controls">
                        <button
                            onClick={runScript}
                            disabled={status !== 'ready' && status !== 'stopped' && status !== 'terminated' && status !== 'error'}
                            title="Run the Python script"
                        >
                            Run
                        </button>
                        <button
                            onClick={stopScript}
                            disabled={status !== 'running'} // Only enable when running
                            title="Stop the Python script"
                        >
                            Stop
                        </button>
                    </div>
                )}
            </header>

            {/* Main Content Area */}
            <main className="App-main">
                {componentOrder.length === 0
                    // Display message when no components are active
                    ? <p>No components active. Waiting for Hero script...</p>
                    // Otherwise, render the active components
                    : renderComponents()
                }
            </main>
        </div>
    );
}

export default App;
