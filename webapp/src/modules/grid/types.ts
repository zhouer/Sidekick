// Sidekick/webapp/src/modules/grid/types.ts

// --- State ---
export interface GridState {
    size: [number, number]; // Width, Height tuple
    cells: {
        [key: string]: { // Key is "x,y"
            color?: string | null;
            text?: string | null;
        }
    };
}

// --- Payloads ---
export interface GridSpawnPayload {
    size?: [number, number]; // Optional: [[width, height]]
}

export interface GridUpdatePayload {
    action: "setCell" | "clear";
    options?: {
        x?: number;
        y?: number;
        color?: string | null;
        text?: string | null;
    };
}

export interface GridNotifyPayload {
    event: 'click';
    x: number;
    y: number;
}