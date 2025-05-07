import { BaseSpawnPayload } from "../../types";

// --- State ---
export interface RowState {
    // Row-specific state, e.g., layout properties like gap, alignment.
    // For now, it might be empty if defaults are handled by CSS.
    // Children are managed globally or passed as props.
    childrenOrder: string[]; // Order of children IDs
}

// --- Payloads ---
export interface RowSpawnPayload extends BaseSpawnPayload {
    // Optional layout config in future
    // gap?: number;
    // justifyContent?: string;
    // alignItems?: string;
}

// Row typically won't have its own specific update actions other than changeParent
export type RowUpdatePayload = {
    // action: "setGap"; options: { gap: number }; // Example future update
};