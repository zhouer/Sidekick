// Sidekick/webapp/src/modules/canvas/types.ts

// --- Payloads ---
// Define Update Payload first as State depends on it
export interface CanvasUpdatePayload {
    action: string;               // e.g., "clear", "config", "line", "rect", "circle"
    options: any;                 // Action-specific parameters (e.g., coordinates, colors)
    commandId: string | number;   // REQUIRED unique identifier for this command instance
}

// --- State ---
export interface CanvasState {
    width: number;
    height: number;
    bgColor: string; // Background color (hex, rgba, etc.)
    // The command queue now stores the full update payloads
    commandQueue: CanvasUpdatePayload[];
}

export interface CanvasSpawnPayload {
    width: number;
    height: number;
    bgColor?: string; // Optional background color on spawn
}

// Canvas module typically doesn't send notifications back based on direct interaction
// export interface CanvasNotifyPayload { ... }