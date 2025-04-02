// Sidekick/webapp/src/types/index.ts
import React from 'react';

// --- Shared Communication Message Types ---

interface BaseMessage {
    id: number; // Reserved, often 0
    module: string; // Module type identifier string
    method: string; // Action/Notification type
}

/** Message from Hero (Python backend) to Sidekick (Frontend) */
export interface HeroMessage extends BaseMessage {
    method: 'spawn' | 'update' | 'remove'; // Actions Hero can perform
    target: string; // The unique ID of the target module instance
    payload?: any; // Data specific to the method and module type (defined per module)
}

/** Message from Sidekick (Frontend) to Hero (Python backend) */
export interface SidekickMessage extends BaseMessage {
    method: 'notify' | 'error'; // Types of messages Sidekick can send
    src: string;    // The unique ID of the source module instance
    payload?: any; // Data specific to the notification/error (defined per module)
}


// --- Generic Module Types ---

/**
 * Represents a generic module instance stored in the application state.
 * Specific state details are handled by module-specific logic.
 */
export interface ModuleInstance {
    id: string;     // Unique instance identifier
    type: string;   // Module type identifier string
    state: any;     // The state specific to this module instance (kept generic here)
}

// --- Module Definition for Registry ---
/**
 * Defines the structure for registering a module type.
 * Uses generics to allow specific module logic/components to be strongly typed internally,
 * while the definition itself remains generic here.
 * @template S The type of the module's state (defaults to any).
 * @template P_Spawn The type of the payload for the 'spawn' message (defaults to any).
 * @template P_Update The type of the payload for the 'update' message (defaults to any).
 */
export interface ModuleDefinition<S = any, P_Spawn = any, P_Update = any> {
    /** The unique identifier string for the module type. */
    type: string;

    /** The display name for the module type, used in the UI. */
    displayName: string;

    /** The React component responsible for rendering this module type. */
    component: React.FC<any>; // Component props are expected to handle specific state type internally

    /**
     * Creates the initial state for a new module instance.
     * @param instanceId The unique ID assigned to this instance.
     * @param payload The payload received from the 'spawn' message.
     * @returns The initial state object for this module type.
     */
    getInitialState: (instanceId: string, payload: P_Spawn) => S;

    /**
     * Updates the state of a module instance based on an 'update' message payload.
     * This function MUST be pure and return a new state object if changes occurred.
     * @param currentState The current state of the module instance.
     * @param payload The payload received from the 'update' message.
     * @returns The updated state object. If no change occurred, it should return the original state object reference.
     */
    updateState: (currentState: S, payload: P_Update) => S;

    /**
     * Optional flag indicating if this module type requires the 'onInteraction'
     * callback prop to send messages back to the Hero backend.
     * Defaults to false if omitted.
     */
    isInteractive?: boolean;
}