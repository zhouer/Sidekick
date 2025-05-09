// webapp/src/types/index.ts

// Represents a peer role
export type PeerRole = "hero" | "sidekick";
export type PeerStatus = "online" | "offline";

// Payload for system/announce message
export interface AnnouncePayload {
    peerId: string;
    role: PeerRole;
    status: PeerStatus;
    version: string;
    timestamp: number; // Unix epoch milliseconds
}

// Information about a connected Hero peer
export interface HeroPeerInfo extends AnnouncePayload {
    role: "hero"; // Ensure role is specifically 'hero'
}

// --- Base Message Structure ---
interface BaseMessage {
    id: number; // Reserved
    component: string; // Target/Source component type
    payload?: any; // Type-specific payload, MUST use camelCase keys
}

// --- Messages Sent FROM Hero TO Sidekick ---

interface BaseHeroMessage extends BaseMessage {
    target?: string; // Target instance ID (required for component control)
    src?: never;
}

export interface SystemAnnounceMessage extends BaseMessage {
    component: "system";
    type: "announce";
    payload: AnnouncePayload;
    target?: never;
    src?: never;
}

export interface GlobalClearMessage extends BaseHeroMessage {
    component: "global";
    type: "clearAll";
    payload?: never;
    target?: never;
    src?: never;
}

// Base Spawn Payload including optional parent
export interface BaseSpawnPayload {
    parent?: string; // Optional: ID of the parent container. "root" for top-level.
}

// Component Control messages (Hero -> Sidekick)
export interface ComponentControlMessage extends BaseHeroMessage {
    component: "grid" | "console" | "viz" | "canvas" | "label" | "markdown" | "button" | "textbox" | "row" | "column";
    type: "spawn" | "update" | "remove";
    target: string; // Target instance ID is required
    payload: any; // Component-specific payload structure
}

// Payload for the 'changeParent' update action
export interface ChangeParentUpdatePayloadOptions {
    parent: string; // Required: New parent ID ("root" for top-level)
    insertBefore?: string | null; // Optional: for ordering (future use)
}
export interface ChangeParentUpdate {
    action: "changeParent";
    options: ChangeParentUpdatePayloadOptions;
}


// Union type for all messages received BY Sidekick FROM Hero
export type ReceivedMessage =
    | SystemAnnounceMessage
    | GlobalClearMessage
    | ComponentControlMessage; // ComponentControlMessage's payload can be a component-specific update OR ChangeParentUpdate

// --- Messages Sent FROM Sidekick TO Hero ---

interface BaseSidekickMessage extends BaseMessage {
    src?: string; // Source instance ID (required for event/error)
    target?: never;
}

export interface ComponentEventMessage extends BaseSidekickMessage {
    component: string;
    type: "event";
    src: string; // Source instance ID is required
    payload: any; // Component-specific event payload
}

export interface ComponentErrorMessage extends BaseSidekickMessage {
    component: string;
    type: "error";
    src: string;
    payload: {
        message: string;
    };
}

export type SentMessage =
    | SystemAnnounceMessage
    | ComponentEventMessage
    | ComponentErrorMessage;

// --- Internal Sidekick Application Types ---

export interface ComponentInstance<TState = any> {
    id: string;
    type: string;
    parentId?: string | null; // ID of the parent, null or "root" if top-level
    state: TState;
    // For containers, we might store children order here, or manage globally in AppState
    // childrenOrder?: string[];
}

export interface ComponentDefinition<
    TState = any,
    TSpawnPayload extends BaseSpawnPayload = BaseSpawnPayload, // Ensure BaseSpawnPayload is included
    TUpdatePayload = any, // Can be specific update or ChangeParentUpdate
> {
    type: string;
    component: React.ForwardRefExoticComponent<
        React.PropsWithoutRef<{
            id: string;
            state: TState;
            onInteraction?: (message: SentMessage) => void;
            onReady?: (id: string) => void; // For imperative components
            // Props for container components to render children
            childrenIds?: string[];
            renderChild?: (childId: string) => React.ReactNode;
        }> & React.RefAttributes<ComponentHandle | null>
    >;
    getInitialState: (instanceId: string, payload: TSpawnPayload, parentId?: string) => TState;
    updateState: (currentState: TState, payload: TUpdatePayload | ChangeParentUpdate, instanceId: string) => TState;
    displayName?: string;
    imperativeUpdate?: boolean;
    isContainer?: boolean; // Flag to identify container components
}

export interface ComponentHandle {
    processUpdate: (payload: any) => void;
}

// Specific types for new components will be in their respective types.ts files
// e.g., LabelState, LabelSpawnPayload, LabelUpdatePayload in ./label/types.ts

// Top-level container ID
export const ROOT_CONTAINER_ID = "root";