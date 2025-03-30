// Sidekick/webapp/src/types/index.ts

// --- Communication Message Types ---
// Base structure for messages between Hero and Sidekick
interface BaseMessage {
    id: number; // Reserved, currently defaults to 0
    module: string; // Module type (e.g., "grid", "console", "viz", "canvas")
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
    value: any; // The primitive value or nested structure (array for list/set/dict, object for obj attrs)
    length?: number; // Number of items/attributes for containers
    observable_tracked?: boolean; // True if the value originated from an ObservableValue
    id: string; // Unique ID for this representation node (often based on Python id() or observable id)
}
// Helper for dictionary key-value pairs within VizRepresentation
export interface VizDictKeyValuePair { key: VizRepresentation; value: VizRepresentation; }

// Represents the path to an element within a variable's structure (for granular updates)
export type Path = (string | number)[];

// Structure holding information about the last change event for a variable (used for highlighting)
export interface VizChangeInfo {
    change_type: string; // Type of change (e.g., "setitem", "append", "remove_variable")
    path: Path; // Path to the element that changed within the variable
    timestamp: number; // Timestamp of when the change was processed by the frontend
}
// State specific to the Variable Visualizer (Viz) module
export interface VizState {
    variables: { [name: string]: VizRepresentation }; // Map of variable names to their current representation
    lastChanges: { [name: string]: VizChangeInfo }; // Map tracking the last change event for each variable
}

// State specific to the Grid module
export interface GridState {
    size: [number, number]; // [width, height]
    cells: { [key: string]: { color?: string | null; text?: string | null } }; // Map of "x,y" to cell state
}

// State specific to the Console module
export interface ConsoleState {
    lines: string[]; // Array of strings representing output lines
}

// Represents a single drawing command for the Canvas module
export interface CanvasDrawCommand {
    command: string; // The drawing operation (e.g., "line", "rect", "config")
    options: any; // Parameters for the command (e.g., coordinates, colors, styles)
    commandId: string | number; // Unique identifier for this command instance
}
// State specific to the Canvas module
export interface CanvasState {
    width: number; // Canvas width in pixels
    height: number; // Canvas height in pixels
    bgColor: string; // Background color string (e.g., "#FFFFFF", "lightgrey")
    // --- CHANGE: Store a queue of commands instead of just the last one ---
    commandQueue: CanvasDrawCommand[]; // Array holding commands waiting to be drawn
}


// --- Module Instance Type ---
// Discriminated union representing any possible module instance in the Sidekick UI

type ModuleType = 'grid' | 'console' | 'viz' | 'canvas';

// Base properties common to all module instances
interface BaseModuleInstance {
    id: string; // Unique identifier for this specific module instance
    type: ModuleType; // The type of the module
}

// Specific instance types inheriting from BaseModuleInstance
export interface GridModuleInstance extends BaseModuleInstance { type: 'grid'; state: GridState; }
export interface ConsoleModuleInstance extends BaseModuleInstance { type: 'console'; state: ConsoleState; }
export interface VizModuleInstance extends BaseModuleInstance { type: 'viz'; state: VizState; }
export interface CanvasModuleInstance extends BaseModuleInstance { type: 'canvas'; state: CanvasState; }

// The union type representing any module instance
export type ModuleInstance = GridModuleInstance | ConsoleModuleInstance | VizModuleInstance | CanvasModuleInstance;


// --- Specific Message Payloads ---
// These provide type safety for the `payload` field of messages involving specific modules

// Payload for Console -> Hero notification when user submits input
export interface ConsoleNotifyPayload { event: 'submit'; value: string; }

// Payload for Hero -> Sidekick to spawn a Canvas module
export interface CanvasSpawnPayload { width: number; height: number; bgColor?: string; }
// Payload for Hero -> Sidekick to update a Canvas module (is essentially a draw command)
export interface CanvasUpdatePayload extends CanvasDrawCommand {}

// Payload for Hero -> Sidekick to update a Viz module variable
export interface VizUpdatePayload {
    variable_name: string; // Name of the variable being updated
    change_type: string;   // Type of change (e.g., "set", "setitem", "append", "remove_variable")
    path: Path;            // Path within the variable where the change occurred
    value_representation: VizRepresentation | null; // Representation of the new value (or null if not applicable)
    key_representation?: VizRepresentation | null; // Representation of the key involved (for dict operations)
    length?: number | null; // New length of the container, if applicable
}

// Example payload for Hero -> Sidekick to update a Grid module
export interface GridUpdatePayload {
    x?: number; y?: number; // Coordinates for cell update
    color?: string | null; text?: string | null; // New cell properties
    fill_color?: string; // Color for filling the entire grid
}