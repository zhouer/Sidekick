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
    payload?: any; // Type-specific payload, MUST use camelCase keys
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