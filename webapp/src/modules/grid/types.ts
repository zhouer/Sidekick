// Sidekick/webapp/src/modules/grid/types.ts

// --- State ---
export interface GridState {
    numColumns: number;
    numRows: number;
    cells: {
        [key: string]: { // Key is "x,y"
            color?: string | null;
            text?: string | null;
        }
    };
}

// --- Payloads ---
export interface GridSpawnPayload {
    numColumns: number;
    numRows: number;
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