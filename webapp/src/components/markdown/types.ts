// webapp/src/components/markdown/types.ts
import { BaseSpawnPayload } from "../../types";

// --- State ---
export interface MarkdownState {
    text: string; // The raw Markdown string
}

// --- Payloads ---
export interface MarkdownSpawnPayload extends BaseSpawnPayload {
    text: string;
}

export type MarkdownUpdatePayload =
    | {
    action: "setText";
    options: {
        text: string;
    };
};

// Markdown component does not typically send events