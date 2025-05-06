// --- State ---
// The structure of the state itself remains the same.
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
// Spawn payload remains the same.
export interface GridSpawnPayload {
    numColumns: number;
    numRows: number;
}

// Define specific options for each new action
interface SetColorOptions {
    x: number;
    y: number;
    color: string | null; // null clears the color
}

interface SetTextOptions {
    x: number;
    y: number;
    text: string | null; // null or "" clears the text
}

interface ClearCellOptions {
    x: number;
    y: number;
}

// Update the GridUpdatePayload to use the new actions and their options
export type GridUpdatePayload =
    | { action: "setColor"; options: SetColorOptions }
    | { action: "setText"; options: SetTextOptions }
    | { action: "clearCell"; options: ClearCellOptions }
    | { action: "clear" }; // No options needed for clear

// Event payload remains the same.
export interface GridEventPayload {
    event: 'click';
    x: number;
    y: number;
}