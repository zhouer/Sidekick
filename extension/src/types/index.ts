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
    component: string; // Target/Source component type (e.g., "grid", "system", "global")
    payload?: any; // Type-specific payload
}

// --- Messages Sent FROM Hero TO Sidekick ---
// (via Server)

// Base type for messages sent from Hero
interface BaseHeroMessage extends BaseMessage {
    target?: string; // Target instance ID (required for component control)
    src?: never;
}

// System Announce message (sent by Hero or Sidekick, received by Sidekick/Hero)
export interface SystemAnnounceMessage extends BaseMessage {
    component: "system";
    type: "announce"; // Changed from method
    payload: AnnouncePayload;
    target?: never; // System messages don't target specific instances
    src?: never;
}

// Global Clear All message (Hero -> Sidekick)
export interface GlobalClearMessage extends BaseHeroMessage {
    component: "global";
    type: "clearAll"; // Changed from method
    payload?: null; // Payload is null or omitted
    target?: never; // Global ops don't target specific instances
    src?: never;
}

// Component Control messages (Hero -> Sidekick)
export interface ComponentControlMessage extends BaseHeroMessage {
    component: "grid" | "console" | "viz" | "canvas" | "control"; // Add other components here
    type: "spawn" | "update" | "remove"; // Changed from method
    target: string; // Target instance ID is required
    payload: any; // Component-specific payload structure (defined in component types/*)
}

// Union type for all messages received BY Sidekick FROM Hero
export type ReceivedMessage =
    | SystemAnnounceMessage // Can also receive announce from other Sidekick instances (via server)
    | GlobalClearMessage
    | ComponentControlMessage;

// --- Messages Sent FROM Sidekick TO Hero ---
// (via Server)

// Base type for messages sent from Sidekick
interface BaseSidekickMessage extends BaseMessage {
    src?: string; // Source instance ID (required for event/error)
    target?: never; // Sidekick never targets specific Hero instances
}

// Component Event message (Sidekick -> Hero)
export interface ComponentEventMessage extends BaseSidekickMessage {
    component: string;
    type: "event";
    src: string; // Source instance ID is required
    payload: any; // Component-specific event payload (defined in component types/*, e.g., { event: 'click', x: number, y: number })
}

// Component Error message (Sidekick -> Hero)
export interface ComponentErrorMessage extends BaseSidekickMessage {
    component: string; // Any component type can potentially send an error
    type: "error";
    src: string; // Source instance ID is required (or potentially component type if instance not found)
    payload: {
        message: string; // Error description
    };
}

// Union type for all messages sent BY Sidekick TO Hero
export type SentMessage =
    | SystemAnnounceMessage // Sidekick also announces itself
    | ComponentEventMessage
    | ComponentErrorMessage;

// --- Internal Sidekick Application Types ---

// Represents a single component instance within the Sidekick UI state
export interface ComponentInstance<TState = any> { // TState is the component-specific state type
    id: string;
    type: string; // e.g., "grid", "console"
    state: TState;
}

/**
 * Defines the contract for a Sidekick component.
 * Each component provides functions for state management and a React component for rendering.
 */
export interface ComponentDefinition<
    TState = any, // Generic type for component-specific state
    TSpawnPayload = any, // Generic type for spawn payload
    TUpdatePayload = any, // Generic type for update payload
> {
    /** Unique string identifier for the component type (e.g., "grid", "console"). */
    type: string;
    /** React functional component responsible for rendering the component's UI. */
    component: React.ForwardRefExoticComponent<
        React.PropsWithoutRef<{
            id: string;
            state: TState;
            onInteraction?: (message: SentMessage) => void;
        }> & React.RefAttributes<ComponentHandle> // Supports forwarding ref of type ComponentHandle
    >;
    /**
     * Pure function to calculate the initial state for a new component instance.
     * Should validate the payload and throw an error if invalid.
     * @param instanceId The unique ID for the new instance.
     * @param payload The payload received from the 'spawn' command.
     * @returns The initial state object for the component instance.
     */
    getInitialState: (instanceId: string, payload: TSpawnPayload) => TState;
    /**
     * Pure function to calculate the next state based on the current state and an update payload.
     * Should validate the payload and return the current state if the update is invalid or causes no change.
     * MUST return a new object reference if the state changes, otherwise return the original currentState object.
     * **Note:** This is NOT called for components where `imperativeUpdate` is true.
     * @param currentState The current state of the component instance.
     * @param payload The payload received from the 'update' command.
     * @returns The new state object if changes occurred, otherwise the original currentState.
     */
    updateState: (currentState: TState, payload: TUpdatePayload) => TState;
    /** Optional user-friendly display name for the component type (e.g., in tooltips). */
    displayName?: string;
    /**
     * If true, 'update' messages for this component type will be sent directly
     * to the component instance via an imperative handle, bypassing the reducer.
     * Defaults to false.
     */
    imperativeUpdate?: boolean;
}

/**
 * Interface for the imperative handle exposed by components supporting direct updates.
 */
export interface ComponentHandle {
    /**
     * Processes an 'update' payload directly.
     * Called by the App component for components with `imperativeUpdate: true`.
     * @param payload The payload from the 'update' message.
     */
    processUpdate: (payload: any) => void;
}
