// webapp/src/components/markdown/types.ts
import { BaseSpawnPayload } from "../../types";

// --- State ---
export interface MarkdownState {
    source: string; // The raw Markdown string
}

// --- Payloads ---
export interface MarkdownSpawnPayload extends BaseSpawnPayload {
    initialSource: string;
}

export type MarkdownUpdatePayload =
    | {
    action: "setSource";
    options: {
        source: string;
    };
};

// Markdown component does not typically send events