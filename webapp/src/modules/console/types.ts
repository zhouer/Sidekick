// Sidekick/webapp/src/modules/console/types.ts

// --- State ---
export interface ConsoleState {
    lines: string[];
}

// --- Payloads ---
export interface ConsoleSpawnPayload {
    text?: string; // Optional initial text line
}

export interface ConsoleUpdatePayload {
    action: "append" | "clear";
    options?: {
        text?: string; // Text to append for 'append' action
    };
}

export interface ConsoleNotifyPayload {
    event: 'submit';
    value: string; // The text submitted by the user
}