import { BaseSpawnPayload, ComponentEventMessage } from "../../types";

// --- State ---
export interface ButtonState {
    text: string;
}

// --- Payloads ---
export interface ButtonSpawnPayload extends BaseSpawnPayload {
    text: string; // Required: Button text
}

export type ButtonUpdatePayload =
    | {
    action: "setText";
    options: {
        text: string; // Required: New button text
    };
};

// --- Event ---
export interface ButtonClickEventPayload {
    event: "click";
}

export interface ButtonClickEvent extends ComponentEventMessage {
    component: 'button';
    payload: ButtonClickEventPayload;
}