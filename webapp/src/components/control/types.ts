// --- Helper Types ---
export type ControlType = "button" | "textInput";

export interface ControlDefinition {
    id: string;         // Unique ID for this specific control instance
    type: ControlType;  // Type of control (button or textInput)
    config: {           // Configuration specific to the control type
        placeholder?: string; // Placeholder for text input
        initialValue?: string;// Initial value for text input
        buttonText?: string;  // Text for the button control or the button next to text input
    };
}

// --- State ---
export interface ControlState {
    // Maps control ID (string) to its definition
    controls: Map<string, ControlDefinition>;
}

// --- Payloads ---
export interface ControlSpawnPayload {
    // Control component typically doesn't need specific spawn payload options
}

export interface ControlUpdatePayload {
    action: "add" | "remove";
    controlId: string;      // ID of the control to add or remove
    options?: {             // Options required only for 'add' action
        controlType?: ControlType;
        config?: ControlDefinition['config']; // Use the config type from ControlDefinition
    };
}

export interface ControlEventPayload {
    event: "click" | "inputText"; // Type of interaction event
    controlId: string;            // ID of the control that triggered the event
    value?: string;               // Submitted value (only for "inputText" event from textInput)
}