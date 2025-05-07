import React, {
    useCallback,
    useReducer,
    Reducer,
    useState,
    useRef,
    useEffect,
    createRef
} from 'react';
import { useCommunication, CommunicationMode } from './hooks/useCommunication';
import { componentRegistry } from './components/componentRegistry';
import {
    ReceivedMessage,
    SentMessage,
    SystemAnnounceMessage,
    GlobalClearMessage,
    ComponentControlMessage,
    ComponentEventMessage,
    ComponentErrorMessage,
    ComponentInstance,
    HeroPeerInfo,
    ComponentHandle,
    BaseSpawnPayload, // For typing spawn payload
    ChangeParentUpdate, // For typing changeParent update
    ROOT_CONTAINER_ID
} from './types';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faInfoCircle } from '@fortawesome/free-solid-svg-icons';
import './App.css';

// --- Application State Definition ---
interface AppState {
    componentsById: Map<string, ComponentInstance>;
    // componentOrder: string[]; // May still be useful for top-level ordering or fallbacks
    childrenByParentId: Map<string, string[]>; // ParentID -> Array of ChildIDs
    heroStatus: HeroPeerInfo | null;
}

const initialState: AppState = {
    componentsById: new Map<string, ComponentInstance>(),
    // componentOrder: [],
    childrenByParentId: new Map([[ROOT_CONTAINER_ID, []]]), // Initialize root container
    heroStatus: null,
};

// --- Reducer Actions Definition ---
type AppAction =
    | { type: 'PROCESS_STATE_UPDATE'; message: ComponentControlMessage }
    | { type: 'PROCESS_SPAWN'; message: ComponentControlMessage }
    | { type: 'PROCESS_REMOVE'; message: ComponentControlMessage }
    | { type: 'PROCESS_SYSTEM_ANNOUNCE'; message: SystemAnnounceMessage }
    | { type: 'PROCESS_GLOBAL_CLEAR'; message: GlobalClearMessage }
    | { type: 'PROCESS_CHANGE_PARENT'; message: ComponentControlMessage & { payload: ChangeParentUpdate } }; // Specific type for changeParent

// =============================================================================
// == Main Application Reducer ==
// =============================================================================
const rootReducer: Reducer<AppState, AppAction> = (state, action): AppState => {
    switch (action.type) {
        case 'PROCESS_SPAWN': {
            const { component: componentType, target: instanceId, payload } = action.message;
            const spawnPayload = payload as BaseSpawnPayload; // Cast to access 'parent'
            const parentId = spawnPayload.parent || ROOT_CONTAINER_ID;

            if (state.componentsById.has(instanceId)) {
                console.warn(`Reducer: Spawn failed - Duplicate ID "${instanceId}".`);
                return state;
            }

            const componentDefinition = componentRegistry.get(componentType);
            if (!componentDefinition) {
                console.warn(`Reducer: Spawn failed - Unknown component type "${componentType}".`);
                return state;
            }

            try {
                const initialComponentState = componentDefinition.getInitialState(instanceId, spawnPayload, parentId);
                const newComponentInstance: ComponentInstance = {
                    id: instanceId,
                    type: componentType,
                    parentId: parentId,
                    state: initialComponentState,
                };

                const newComponentsById = new Map(state.componentsById).set(instanceId, newComponentInstance);
                const newChildrenByParentId = new Map(state.childrenByParentId);

                // Add to parent's children list
                const parentChildren = newChildrenByParentId.get(parentId) || [];
                newChildrenByParentId.set(parentId, [...parentChildren, instanceId]);

                // If it's a container, initialize its own children list
                if (componentDefinition.isContainer) {
                    newChildrenByParentId.set(instanceId, []);
                }

                console.log(`Reducer: Spawned component "${instanceId}" (Type: ${componentType}, Parent: ${parentId}).`);
                return { ...state, componentsById: newComponentsById, childrenByParentId: newChildrenByParentId };

            } catch (error: any) {
                console.error(`Reducer: Error during getInitialState for "${instanceId}" (${componentType}):`, error.message || error);
                // Send error back to Hero?
                return state;
            }
        }

        case 'PROCESS_STATE_UPDATE': { // Handles non-imperative state updates
            const { component: componentType, target, payload } = action.message;

            const currentComponent = state.componentsById.get(target);
            if (!currentComponent) {
                console.warn(`Reducer: State Update failed - Component "${target}" not found.`);
                return state;
            }

            const componentDefinition = componentRegistry.get(componentType);
            if (!componentDefinition || componentDefinition.imperativeUpdate) {
                console.error(`Reducer: State Update failed for "${target}" - Not a non-imperative component or definition missing.`);
                return state;
            }
            if (payload === undefined || payload === null) {
                console.warn(`Reducer: State Update failed - Missing payload for "${target}".`);
                return state;
            }
            // Exclude ChangeParentUpdate from here, it's handled by PROCESS_CHANGE_PARENT
            if ((payload as any).action === "changeParent") {
                console.warn(`Reducer: 'changeParent' action should be handled by PROCESS_CHANGE_PARENT. Ignoring in PROCESS_STATE_UPDATE for "${target}".`);
                return state;
            }


            try {
                const updatedComponentState = componentDefinition.updateState(currentComponent.state, payload as any, target);
                if (updatedComponentState === currentComponent.state) return state;

                const updatedComponentInstance = { ...currentComponent, state: updatedComponentState };
                const newComponentsById = new Map(state.componentsById).set(target, updatedComponentInstance);
                return { ...state, componentsById: newComponentsById };

            } catch (error: any) {
                console.error(`Reducer: Error during updateState for "${target}" (${componentType}):`, error.message || error);
                return state;
            }
        }

        case 'PROCESS_CHANGE_PARENT': {
            const { target: instanceId, payload } = action.message; // payload is ChangeParentUpdate
            const { parent: newParentId /*, insertBefore */ } = payload.options;

            const componentToMove = state.componentsById.get(instanceId);
            if (!componentToMove) {
                console.warn(`Reducer: ChangeParent failed - Component "${instanceId}" not found.`);
                return state;
            }
            if (!state.childrenByParentId.has(newParentId) && newParentId !== ROOT_CONTAINER_ID) {
                const newParentDef = state.componentsById.get(newParentId);
                if (!newParentDef || !componentRegistry.get(newParentDef.type)?.isContainer) {
                    console.warn(`Reducer: ChangeParent failed - New parent "${newParentId}" is not a valid container or does not exist.`);
                    return state;
                }
            }


            const oldParentId = componentToMove.parentId || ROOT_CONTAINER_ID;

            if (oldParentId === newParentId) {
                // TODO: Handle reordering within the same parent if `insertBefore` is provided
                console.log(`Reducer: ChangeParent - Component "${instanceId}" already child of "${newParentId}". Reordering not yet implemented.`);
                return state;
            }

            const newComponentsById = new Map(state.componentsById);
            const newChildrenByParentId = new Map(state.childrenByParentId);

            // 1. Remove from old parent's children list
            const oldParentChildren = newChildrenByParentId.get(oldParentId) || [];
            newChildrenByParentId.set(oldParentId, oldParentChildren.filter(id => id !== instanceId));

            // 2. Add to new parent's children list (append for now)
            const newParentChildren = newChildrenByParentId.get(newParentId) || [];
            // Ensure new parent has a children array if it's the first child
            if (!newChildrenByParentId.has(newParentId)) {
                newChildrenByParentId.set(newParentId, []);
            }
            newChildrenByParentId.set(newParentId, [...newParentChildren, instanceId]);


            // 3. Update component's parentId
            newComponentsById.set(instanceId, { ...componentToMove, parentId: newParentId });

            console.log(`Reducer: Moved component "${instanceId}" from parent "${oldParentId}" to "${newParentId}".`);
            return { ...state, componentsById: newComponentsById, childrenByParentId: newChildrenByParentId };
        }

        case 'PROCESS_REMOVE': {
            const { target: instanceIdToRemove } = action.message;
            if (!state.componentsById.has(instanceIdToRemove)) return state;

            let newComponentsById = new Map(state.componentsById);
            let newChildrenByParentId = new Map(state.childrenByParentId);

            const
                q: string[] = [instanceIdToRemove]; // Queue for BFS/DFS removal
            const removedIds = new Set<string>();

            while (q.length > 0) {
                const currentId = q.shift()!;
                if (removedIds.has(currentId)) continue;

                const componentToRemove = newComponentsById.get(currentId);
                if (!componentToRemove) continue;

                // 1. Remove from its parent's children list
                const parentId = componentToRemove.parentId || ROOT_CONTAINER_ID;
                const parentChildren = newChildrenByParentId.get(parentId) || [];
                newChildrenByParentId.set(parentId, parentChildren.filter(id => id !== currentId));

                // 2. If it's a container, enqueue its children for removal
                const componentDef = componentRegistry.get(componentToRemove.type);
                if (componentDef?.isContainer) {
                    const childrenOfCurrent = newChildrenByParentId.get(currentId) || [];
                    childrenOfCurrent.forEach(childId => q.push(childId));
                    newChildrenByParentId.delete(currentId); // Remove its own entry from childrenByParentId
                }

                // 3. Remove from componentsById
                newComponentsById.delete(currentId);
                removedIds.add(currentId);
                console.log(`Reducer: Removed component "${currentId}".`);
            }

            return { ...state, componentsById: newComponentsById, childrenByParentId: newChildrenByParentId, heroStatus: state.heroStatus };
        }

        case 'PROCESS_SYSTEM_ANNOUNCE': {
            const { payload } = action.message;
            if (payload && payload.role === 'hero') {
                const newHeroStatus: HeroPeerInfo | null = payload.status === 'online' ? { ...payload, role: 'hero' } : null;
                if (state.heroStatus?.peerId !== newHeroStatus?.peerId || state.heroStatus?.status !== newHeroStatus?.status) {
                    return { ...state, heroStatus: newHeroStatus };
                }
            }
            return state;
        }

        case 'PROCESS_GLOBAL_CLEAR': {
            console.log("Reducer: Processing global/clearAll command.");
            return {
                ...initialState, // Resets componentsById, childrenByParentId (with root)
                heroStatus: state.heroStatus // Preserve hero status
            };
        }

        default:
            console.warn("Reducer: Received unknown action type:", (action as any)?.type);
            return state;
    }
};

// =============================================================================
// == Main Application Component ==
// =============================================================================
function App() {
    const [appState, dispatch] = useReducer(rootReducer, initialState);
    const { componentsById, childrenByParentId, heroStatus } = appState;
    const [hoveredInfoId, setHoveredInfoId] = useState<string | null>(null);

    const imperativeComponentRefs = useRef<Map<string, React.RefObject<ComponentHandle | null>>>(new Map());
    const pendingImperativeUpdates = useRef<Map<string, any[]>>(new Map());

    const onComponentReady = useCallback((componentId: string) => {
        console.log(`App: Received ready signal from component "${componentId}".`);
        const pendingUpdates = pendingImperativeUpdates.current.get(componentId);
        const componentRef = imperativeComponentRefs.current.get(componentId);

        if (pendingUpdates && pendingUpdates.length > 0 && componentRef?.current?.processUpdate) {
            console.log(`App: Processing ${pendingUpdates.length} queued update(s) for "${componentId}".`);
            const processUpdateFunc = componentRef.current.processUpdate;
            try {
                pendingUpdates.forEach(payload => processUpdateFunc(payload));
            } catch (error) {
                console.error(`App: Error processing queued updates for "${componentId}":`, error);
            } finally {
                pendingImperativeUpdates.current.delete(componentId);
            }
        } else if (pendingUpdates && pendingUpdates.length > 0) {
            console.warn(`App: "${componentId}" ready, but handle/processUpdate not available. ${pendingUpdates.length} updates remain.`);
        }
    }, []);

    const handleSidekickMessage = useCallback((messageData: any) => {
        if (typeof messageData !== 'object' || messageData === null || !messageData.component || !messageData.type) {
            console.error("App: Received invalid message from Sidekick:", messageData);
            return;
        }
        const message = messageData as ReceivedMessage;

        if (message.type === 'update' && 'target' in message && (message.payload as any)?.action === 'changeParent') {
            dispatch({ type: 'PROCESS_CHANGE_PARENT', message: message as ComponentControlMessage & { payload: ChangeParentUpdate } });
            return;
        }

        if (message.type === 'update' && 'target' in message) {
            const componentMessage = message as ComponentControlMessage;
            const componentDefinition = componentRegistry.get(componentMessage.component);

            if (componentDefinition?.imperativeUpdate) {
                const componentRef = imperativeComponentRefs.current.get(componentMessage.target);
                if (componentRef?.current?.processUpdate) {
                    try {
                        componentRef.current.processUpdate(componentMessage.payload);
                    } catch (error) {
                        console.error(`App: Error calling imperative processUpdate for "${componentMessage.target}":`, error);
                    }
                } else {
                    console.debug(`App: Queuing update for imperative "${componentMessage.target}" (handle not ready).`);
                    const queue = pendingImperativeUpdates.current.get(componentMessage.target) || [];
                    queue.push(componentMessage.payload);
                    pendingImperativeUpdates.current.set(componentMessage.target, queue);
                }
                return;
            } else {
                dispatch({ type: 'PROCESS_STATE_UPDATE', message: componentMessage });
                return;
            }
        }

        if (message.type === 'spawn' && 'target' in message) {
            dispatch({ type: 'PROCESS_SPAWN', message: message as ComponentControlMessage });
        } else if (message.type === 'remove' && 'target' in message) {
            dispatch({ type: 'PROCESS_REMOVE', message: message as ComponentControlMessage });
        } else if (message.component === 'system' && message.type === 'announce') {
            dispatch({ type: 'PROCESS_SYSTEM_ANNOUNCE', message: message as SystemAnnounceMessage });
        } else if (message.component === 'global' && message.type === 'clearAll') {
            dispatch({ type: 'PROCESS_GLOBAL_CLEAR', message: message as GlobalClearMessage });
        } else {
            console.warn("App: Received unhandled message type:", message);
        }
    }, [/* dispatch is stable */]);

    const { mode, isConnected, status, sendMessage, runScript, stopScript } = useCommunication(handleSidekickMessage);

    useEffect(() => { // Cleanup refs for removed components
        const currentComponentIds = new Set(componentsById.keys());
        imperativeComponentRefs.current.forEach((_, componentId) => {
            if (!currentComponentIds.has(componentId)) imperativeComponentRefs.current.delete(componentId);
        });
        pendingImperativeUpdates.current.forEach((_, componentId) => {
            if (!currentComponentIds.has(componentId)) pendingImperativeUpdates.current.delete(componentId);
        });
    }, [componentsById]);

    const handleComponentInteraction = useCallback((interactionMessage: SentMessage) => {
        if (!interactionMessage || !interactionMessage.component || !interactionMessage.type) {
            console.error("App: Invalid interaction message from component:", interactionMessage);
            return;
        }
        if ((interactionMessage.type === 'event' || interactionMessage.type === 'error') && (interactionMessage as ComponentEventMessage | ComponentErrorMessage).src) {
            sendMessage(interactionMessage);
        } else if (interactionMessage.component === 'system' && interactionMessage.type === 'announce') {
            sendMessage(interactionMessage);
        } else {
            console.error("App: Attempted to send message of unexpected type via interaction:", interactionMessage);
        }
    }, [sendMessage]);

    const renderStatus = () => { /* ... (same as before) ... */
        const sidekickStatusText = `Sidekick (v${__APP_VERSION__})`;
        let heroStatusText = 'Hero: Offline';
        let heroStatusClass = 'hero-status-offline';
        if (heroStatus?.status === 'online') {
            heroStatusText = `Hero: Online`;
            heroStatusClass = 'hero-status-online';
        }

        if (mode === 'websocket') {
            let wsStatusText = 'Unknown';
            switch (status) {
                case 'connecting': wsStatusText = 'Connecting'; break;
                case 'connected': wsStatusText = 'Connected'; break;
                case 'disconnected': wsStatusText = 'Disconnected'; break;
                case 'reconnecting': wsStatusText = 'Reconnecting'; break;
            }
            const wsStatusClass = isConnected ? 'status-connected' : 'status-disconnected';
            return (<><p className={wsStatusClass}>WebSocket: {wsStatusText}</p><p className={heroStatusClass}>{heroStatusText}</p></>);
        } else {
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
            return (<><p className={scriptStatusClass}>{scriptStatusText}</p><p className={heroStatusClass}>{heroStatusText}</p></>);
        }
    };

    // --- Recursive Rendering Function ---
    const renderComponentTree = useCallback((componentId: string): React.ReactNode => {
        const componentInstance = componentsById.get(componentId);
        if (!componentInstance) {
            console.error(`App Render: Component data for ID "${componentId}" not found!`);
            return <div key={componentId} className="component-card error">Error: Component data missing for {componentId}</div>;
        }

        const componentDefinition = componentRegistry.get(componentInstance.type);
        if (!componentDefinition) {
            console.error(`App Render: Def for type "${componentInstance.type}" (ID: "${componentId}") not registered!`);
            return <div key={componentId} className="component-card error">Error: Unknown Type '{componentInstance.type}'</div>;
        }

        const ComponentToRender = componentDefinition.component;
        let componentRef: React.RefObject<ComponentHandle | null> | undefined = undefined;

        if (componentDefinition.imperativeUpdate) {
            if (!imperativeComponentRefs.current.has(componentId)) {
                imperativeComponentRefs.current.set(componentId, createRef<ComponentHandle | null>());
            }
            componentRef = imperativeComponentRefs.current.get(componentId);
        }

        const componentProps: any = {
            id: componentInstance.id,
            state: componentInstance.state,
            onInteraction: handleComponentInteraction,
        };
        if (componentDefinition.imperativeUpdate) componentProps.onReady = onComponentReady;

        // For container components, pass childrenIds and the render function itself
        if (componentDefinition.isContainer) {
            componentProps.childrenIds = childrenByParentId.get(componentId) || [];
            componentProps.renderChild = renderComponentTree; // Pass the recursive render function
        }

        const handleMouseEnterInfo = () => setHoveredInfoId(componentId);
        const handleMouseLeaveInfo = () => setHoveredInfoId(null);
        const isInfoHovered = hoveredInfoId === componentId;
        const displayName = componentDefinition.displayName || componentInstance.type;

        // Wrap non-container components in a card, containers might style themselves
        const Wrapper = componentDefinition.isContainer ? React.Fragment : 'div';
        const wrapperProps = componentDefinition.isContainer ? {} : { className: "component-card" };


        return (
            <Wrapper {...wrapperProps} key={componentInstance.id}>
                {!componentDefinition.isContainer && ( // Only show info icon for non-container items in cards
                    <>
                        <div className="component-info-icon" onMouseEnter={handleMouseEnterInfo} onMouseLeave={handleMouseLeaveInfo} aria-label={`Info for ${displayName}: ${componentInstance.id}`}>
                            <FontAwesomeIcon icon={faInfoCircle} />
                        </div>
                        {isInfoHovered && (<div className="component-tooltip">Type: {displayName}<br />ID: {componentInstance.id}</div>)}
                    </>
                )}
                <ComponentToRender ref={componentRef} {...componentProps} />
            </Wrapper>
        );
    }, [componentsById, childrenByParentId, handleComponentInteraction, onComponentReady, hoveredInfoId]);


    const rootChildren = childrenByParentId.get(ROOT_CONTAINER_ID) || [];

    return (
        <div className="App">
            <header className="App-header">
                <h1>Sidekick</h1>
                <div className="status-indicators">{renderStatus()}</div>
                {mode === 'script' && (
                    <div className="script-controls">
                        <button onClick={runScript} disabled={!(status === 'ready' || status === 'stopped' || status === 'terminated' || status === 'error')} title="Run Script">Run</button>
                        <button onClick={stopScript} disabled={status !== 'running'} title="Stop Script">Stop</button>
                    </div>
                )}
            </header>
            <main className="App-main">
                {componentsById.size === 0 && rootChildren.length === 0
                    ? <p>No components active. Waiting for Hero script...</p>
                    : rootChildren.map(childId => renderComponentTree(childId))
                }
            </main>
        </div>
    );
}

export default App;