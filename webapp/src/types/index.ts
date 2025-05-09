// Sidekick/webapp/src/types/index.ts

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
    module: string; // Target/Source module type (e.g., "grid", "system", "global")
    payload?: any; // Type-specific payload, MUST use camelCase keys
}

// --- Messages Sent FROM Hero TO Sidekick ---
// (via Server)

// Base type for messages sent from Hero
interface BaseHeroMessage extends BaseMessage {
    target?: string; // Target instance ID (required for module control)
    src?: never;
}

// System Announce message (sent by Hero or Sidekick, received by Sidekick/Hero)
export interface SystemAnnounceMessage extends BaseMessage {
    module: "system";
    type: "announce"; // Changed from method
    payload: AnnouncePayload;
    target?: never; // System messages don't target specific instances
    src?: never;
}

// Global Clear All message (Hero -> Sidekick)
export interface GlobalClearMessage extends BaseHeroMessage {
    module: "global";
    type: "clearAll"; // Changed from method
    payload?: null; // Payload is null or omitted
    target?: never; // Global ops don't target specific instances
    src?: never;
}

// Module Control messages (Hero -> Sidekick)
export interface ModuleControlMessage extends BaseHeroMessage {
    module: "grid" | "console" | "viz" | "canvas" | "control"; // Add other modules here
    type: "spawn" | "update" | "remove"; // Changed from method
    target: string; // Target instance ID is required
    payload: any; // Module-specific payload structure (defined in module types/*)
}

// Union type for all messages received BY Sidekick FROM Hero
export type ReceivedMessage =
    | SystemAnnounceMessage // Can also receive announce from other Sidekick instances (via server)
    | GlobalClearMessage
    | ModuleControlMessage;

// --- Messages Sent FROM Sidekick TO Hero ---
// (via Server)

// Base type for messages sent from Sidekick
interface BaseSidekickMessage extends BaseMessage {
    src?: string; // Source instance ID (required for event/error)
    target?: never; // Sidekick never targets specific Hero instances
}

// Module Event message (Sidekick -> Hero)
export interface ModuleEventMessage extends BaseSidekickMessage {
    module: string;
    type: "event";
    src: string; // Source instance ID is required
    payload: any; // Module-specific event payload (defined in module types/*, e.g., { event: 'click', x: number, y: number })
}

// Module Error message (Sidekick -> Hero)
export interface ModuleErrorMessage extends BaseSidekickMessage {
    module: string; // Any module type can potentially send an error
    type: "error";
    src: string; // Source instance ID is required (or potentially module type if instance not found)
    payload: {
        message: string; // Error description
    };
}

// Union type for all messages sent BY Sidekick TO Hero
export type SentMessage =
    | SystemAnnounceMessage // Sidekick also announces itself
    | ModuleEventMessage
    | ModuleErrorMessage;

// --- Internal Sidekick Application Types ---

// Represents a single module instance within the Sidekick UI state
export interface ModuleInstance<TState = any> { // TState is the module-specific state type
    id: string;
    type: string; // e.g., "grid", "console"
    state: TState;
}

/**
 * Defines the contract for a Sidekick module.
 * Each module provides functions for state management and a React component for rendering.
 */
export interface ModuleDefinition<
    TState = any, // Generic type for module-specific state
    TSpawnPayload = any, // Generic type for spawn payload
    TUpdatePayload = any, // Generic type for update payload
> {
    /** Unique string identifier for the module type (e.g., "grid", "console"). */
    type: string;
    /** React functional component responsible for rendering the module's UI. */
    component: React.ForwardRefExoticComponent<
        React.PropsWithoutRef<{
            id: string;
            state: TState;
            onInteraction?: (message: SentMessage) => void;
        }> & React.RefAttributes<ModuleHandle> // Supports forwarding ref of type ModuleHandle
    >;
    /**
     * Pure function to calculate the initial state for a new module instance.
     * Should validate the payload and throw an error if invalid.
     * @param instanceId The unique ID for the new instance.
     * @param payload The payload received from the 'spawn' command.
     * @returns The initial state object for the module instance.
     */
    getInitialState: (instanceId: string, payload: TSpawnPayload) => TState;
    /**
     * Pure function to calculate the next state based on the current state and an update payload.
     * Should validate the payload and return the current state if the update is invalid or causes no change.
     * MUST return a new object reference if the state changes, otherwise return the original currentState object.
     * **Note:** This is NOT called for modules where `imperativeUpdate` is true.
     * @param currentState The current state of the module instance.
     * @param payload The payload received from the 'update' command.
     * @returns The new state object if changes occurred, otherwise the original currentState.
     */
    updateState: (currentState: TState, payload: TUpdatePayload) => TState;
    /** Optional user-friendly display name for the module type (e.g., in tooltips). */
    displayName?: string;
    /**
     * If true, 'update' messages for this module type will be sent directly
     * to the component instance via an imperative handle, bypassing the reducer.
     * Defaults to false.
     */
    imperativeUpdate?: boolean;
}

/**
 * Interface for the imperative handle exposed by modules supporting direct updates.
 */
export interface ModuleHandle {
    /**
     * Processes an 'update' payload directly.
     * Called by the App component for modules with `imperativeUpdate: true`.
     * @param payload The payload from the 'update' message.
     */
    processUpdate: (payload: any) => void;
}