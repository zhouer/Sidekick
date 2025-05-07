import { BaseSpawnPayload } from "../../types";

// --- State ---
export interface ColumnState {
    // Column-specific state, similar to Row.
    // Children are managed globally or passed as props.
    childrenOrder: string[]; // Order of children IDs
}

// --- Payloads ---
export interface ColumnSpawnPayload extends BaseSpawnPayload {
    // Optional layout config in future
}

// Column typically won't have its own specific update actions other than changeParent
export type ColumnUpdatePayload = {
    // action: "setAlignItems"; options: { alignItems: string }; // Example
};