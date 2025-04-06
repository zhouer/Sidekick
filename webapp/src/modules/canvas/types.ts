// Sidekick/webapp/src/modules/canvas/types.ts

// --- State ---
export interface CanvasState {
    width: number;
    height: number;
    bgColor: string; // Background color (hex, rgba, etc.)
    // The command queue now stores the full update payloads
    commandQueue: CanvasUpdatePayload[];
}

// --- Payloads ---
export interface CanvasSpawnPayload {
    width: number;
    height: number;
    bgColor?: string; // Optional background color on spawn
}

export interface CanvasUpdatePayload {
    action: string;               // e.g., "clear", "config", "line", "rect", "circle"
    options: any;                 // Action-specific parameters (e.g., coordinates, colors)
    commandId: string | number;   // REQUIRED unique identifier for this command instance
}
