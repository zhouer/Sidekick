// --- State ---
export interface ConsoleState {
    lines: string[];
    showInput: boolean;
}

// --- Payloads ---
export interface ConsoleSpawnPayload {
    showInput: boolean;
    text?: string;      // Optional initial text line
}

export interface ConsoleUpdatePayload {
    action: "append" | "clear";
    options?: {
        text?: string; // Text to append for 'append' action
    };
}

export interface ConsoleEventPayload {
    event: 'inputText';
    value: string; // The text submitted by the user
}