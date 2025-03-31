// Sidekick/webapp/src/types/index.ts

// --- Communication Message Types ---
// Base structure for messages between Hero and Sidekick
interface BaseMessage {
    id: number; // Reserved, currently defaults to 0
    module: string; // Module type (e.g., "grid", "console", "viz", "canvas", "control")
    method: string; // Action/Notification type (e.g., "spawn", "update", "notify")
}

// Message sent FROM Hero TO Sidekick (Commands)
export interface HeroMessage extends BaseMessage {
    method: 'spawn' | 'update' | 'remove'; // Allowed command methods
    target: string; // ID of the target module instance
    payload?: any; // Data specific to the command and module
}

// Message sent FROM Sidekick TO Hero (Notifications, Errors)
export interface SidekickMessage extends BaseMessage {
    method: 'notify' | 'error'; // Allowed notification/error methods
    src: string; // ID of the source module instance sending the message
    payload?: any; // Data specific to the notification/error
}


// --- Module State Types ---

// Represents a Python value serialized for visualization
export interface VizRepresentation {
    type: string; // Python type name (e.g., "int", "list", "object (MyClass)")
    value: any; // The primitive value or nested structure
    length?: number; // Number of items/attributes for containers
    observable_tracked?: boolean; // True if the value originated from an ObservableValue
    id: string; // Unique ID for this representation node
}
// Helper for dictionary key-value pairs within VizRepresentation
export interface VizDictKeyValuePair { key: VizRepresentation; value: VizRepresentation; }

// Represents the path to an element within a variable's structure
export type Path = (string | number)[];

// Structure holding information about the last change event for a variable
export interface VizChangeInfo {
    change_type: string; // Type of change (e.g., "setitem", "append")
    path: Path; // Path to the element that changed
    timestamp: number; // Timestamp of when the change was processed
}
// State specific to the Variable Visualizer (Viz) module
export interface VizState {
    variables: { [name: string]: VizRepresentation }; // Map of variable names to their representation
    lastChanges: { [name: string]: VizChangeInfo }; // Map tracking the last change event per variable
}

// State specific to the Grid module
export interface GridState {
    size: [number, number]; // [width, height]
    cells: { [key: string]: { color?: string | null; text?: string | null } }; // Map of "x,y" to cell state
}

// State specific to the Console module
export interface ConsoleState {
    lines: string[]; // Array of output lines
}

// Represents a single drawing command for the Canvas module
export interface CanvasDrawCommand {
    command: string; // Drawing operation (e.g., "line", "rect")
    options: any; // Parameters for the command
    commandId: string | number; // Unique identifier for this command instance
}
// State specific to the Canvas module
export interface CanvasState {
    width: number; // Canvas width
    height: number; // Canvas height
    bgColor: string; // Background color
    commandQueue: CanvasDrawCommand[]; // Queue of drawing commands
}

// --- NEW: Control Module Types ---
// Defines the type of a control element
export type ControlType = "button" | "text_input";

// Defines a single control element within the Control module
export interface ControlDefinition {
    id: string;         // Unique ID for this control within its module instance
    type: ControlType;  // Type of control
    config: {           // Configuration specific to the control type
        text?: string;          // For button: Button label
        placeholder?: string;   // For text_input: Input placeholder
        initial_value?: string; // For text_input: Initial input value
        button_text?: string;   // For text_input: Text for its submit button
    };
}
// State for the Control module instance
export interface ControlState {
    // Use a Map to store control definitions, keyed by their unique ID for efficient access
    controls: Map<string, ControlDefinition>;
}
// --------------------------------


// --- Module Instance Type ---
// Define all possible module types as a string literal union
type ModuleType = 'grid' | 'console' | 'viz' | 'canvas' | 'control'; // Added 'control'

// Base interface common to all module instances
interface BaseModuleInstance {
    id: string; // Unique identifier for this specific module instance
    type: ModuleType; // The type of the module
}

// Specific instance types inheriting from BaseModuleInstance, defining their state shape
export interface GridModuleInstance extends BaseModuleInstance { type: 'grid'; state: GridState; }
export interface ConsoleModuleInstance extends BaseModuleInstance { type: 'console'; state: ConsoleState; }
export interface VizModuleInstance extends BaseModuleInstance { type: 'viz'; state: VizState; }
export interface CanvasModuleInstance extends BaseModuleInstance { type: 'canvas'; state: CanvasState; }
export interface ControlModuleInstance extends BaseModuleInstance { type: 'control'; state: ControlState; } // Added Control instance

// Create the final discriminated union type for any module instance
export type ModuleInstance =
    | GridModuleInstance
    | ConsoleModuleInstance
    | VizModuleInstance
    | CanvasModuleInstance
    | ControlModuleInstance; // Added Control instance


// --- Specific Message Payloads ---
// Define types for the `payload` field of specific messages for better type safety

// Payload for Console -> Hero notification (user submitted text)
export interface ConsoleNotifyPayload { event: 'submit'; value: string; }

// Payload for Hero -> Sidekick to spawn a Canvas
export interface CanvasSpawnPayload { width: number; height: number; bgColor?: string; }
// Payload for Hero -> Sidekick to update a Canvas (a single draw command)
export interface CanvasUpdatePayload extends CanvasDrawCommand {}

// Payload for Hero -> Sidekick to update a Viz variable
export interface VizUpdatePayload {
    variable_name: string;
    change_type: string;
    path: Path;
    value_representation: VizRepresentation | null;
    key_representation?: VizRepresentation | null;
    length?: number | null;
}

// Example payload for Hero -> Sidekick to update a Grid
export interface GridUpdatePayload {
    x?: number; y?: number;
    color?: string | null; text?: string | null;
    fill_color?: string;
}

// --- NEW: Control Module Payloads ---
// Payload for Hero -> Sidekick to update controls (add/remove) within a Control module
export interface ControlUpdatePayload {
    operation: "add" | "remove"; // Action to perform
    control_id: string;         // ID of the control to add/remove
    control_type?: ControlType; // Required for "add"
    config?: ControlDefinition['config']; // Required for "add"
}
// Payload for Sidekick -> Hero notification when a control is interacted with
export interface ControlNotifyPayload {
    event: "click" | "submit"; // Type of interaction ("click" for button, "submit" for text input)
    control_id: string;         // ID of the control that triggered the event
    value?: string;              // The submitted value (only for "submit" event from text_input)
}
// -----------------------------------