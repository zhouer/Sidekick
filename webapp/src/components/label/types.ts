import { BaseSpawnPayload } from "../../types";

// --- State ---
export interface LabelState {
    text: string;
}

// --- Payloads ---
export interface LabelSpawnPayload extends BaseSpawnPayload {
    text: string; // Required: Initial text
}

export type LabelUpdatePayload =
    | {
    action: "setText";
    options: {
        text: string; // Required: New text
    };
};
// Label does not send events