// Sidekick/webapp/src/types/index.ts

// --- Peer Information ---
export type PeerRole = "hero" | "sidekick";
export type PeerStatus = "online" | "offline";

export interface AnnouncePayload {
    peerId: string;
    role: PeerRole;
    status: PeerStatus;
    version: string;
    timestamp: number;
}

// --- Base Message Structure ---
interface BaseMessage {
    id: number; // Reserved
    module: string;
    method: string;
    payload?: object | null;
}

// --- Specific Message Types ---

// Messages received FROM Hero (or Server)
export interface SystemAnnounceMessage extends BaseMessage {
    module: "system";
    method: "announce";
    payload: AnnouncePayload;
    // target/src are omitted
}

export interface GlobalClearMessage extends BaseMessage {
    module: "global";
    method: "clearAll";
    // target/src/payload are omitted
}

export interface ModuleControlMessage extends BaseMessage {
    module: string; // e.g., "grid", "console", "viz", etc. (NOT "system" or "global")
    method: "spawn" | "update" | "remove";
    target: string; // Target instance ID is required
    payload?: object | null; // Payload structure depends on module/method
    // src is omitted
}

// Union type for all messages potentially received by Sidekick
export type ReceivedMessage = SystemAnnounceMessage | GlobalClearMessage | ModuleControlMessage;

// Messages sent FROM Sidekick
export interface SystemAnnounceMessageToSend extends BaseMessage {
    module: "system";
    method: "announce";
    payload: AnnouncePayload;
    // target/src are omitted
}
export interface ModuleNotifyMessage extends BaseMessage {
    module: string; // e.g., "grid", "console", "control"
    method: "notify";
    src: string; // Source instance ID is required
    payload: object; // Payload structure depends on module/event
    // target is omitted
}

export interface ModuleErrorMessage extends BaseMessage {
    module: string; // e.g., "grid"
    method: "error";
    src: string; // Source instance ID is required
    payload: { message: string };
    // target is omitted
}

// Union type for all messages potentially sent by Sidekick
export type SentMessage = SystemAnnounceMessageToSend | ModuleNotifyMessage | ModuleErrorMessage;

// --- Module Instance State ---
// Represents a single active module instance in the UI
export interface ModuleInstance<TState = any> {
    id: string;
    type: string; // Module type string (e.g., "grid")
    state: TState; // Module-specific state object
}

// --- Module Definition (for Registry) ---
// Defines the contract for registering a module type
export interface ModuleDefinition<TState = any, TPayload = any> {
    type: string; // Unique module type identifier
    component: React.FC<any>; // The React component to render the module
    // Pure function to create the initial state for a new instance
    getInitialState: (instanceId: string, payload: TPayload | null) => TState;
    // Pure function to calculate the next state based on an update payload
    // Must return a new object reference if the state changes.
    updateState: (currentState: TState, payload: TPayload) => TState;
    // Does this module component require the 'onInteraction' prop?
    isInteractive?: boolean;
    // Optional display name for UI purposes
    displayName?: string;
}

// --- Hero Peer Status (for AppState) ---
export interface HeroPeerInfo {
    peerId: string;
    version: string;
    status: PeerStatus;
    timestamp: number;
}