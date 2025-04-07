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