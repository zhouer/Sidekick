import { BaseSpawnPayload, ComponentEventMessage } from "../../types";

// --- State ---
export interface TextboxState {
    currentValue: string; // Value managed by Python, updated via 'setValue'
    placeholder?: string;
}

// --- Payloads ---
export interface TextboxSpawnPayload extends BaseSpawnPayload {
    initialValue?: string;
    placeholder?: string;
}

export type TextboxUpdatePayload =
    | {
    action: "setValue";
    options: {
        value: string; // Required: New value from Python
    };
}
    | {
    action: "setPlaceholder";
    options: {
        placeholder: string; // Required: New placeholder
    };
};


// --- Event ---
export interface TextboxSubmitEventPayload {
    event: "submit";
    value: string; // Current value of the textbox upon submission
}

export interface TextboxSubmitEvent extends ComponentEventMessage {
    component: 'textbox';
    payload: TextboxSubmitEventPayload;
}