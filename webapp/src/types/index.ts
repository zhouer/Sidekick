// Sidekick/webapp/src/types/index.ts

// --- Communication Message Types ---
interface BaseMessage { id: number; module: string; method: string; }
export interface HeroMessage extends BaseMessage {
    method: 'spawn' | 'update' | 'remove'; // Note: remove_var is gone
    target: string;
    payload?: any;
}
export interface SidekickMessage extends BaseMessage {
    method: 'notify' | 'error';
    src: string;
    payload?: any;
}

// --- Module State Types ---
export interface VizRepresentation {
    type: string;
    value: any;
    length?: number;
    observable_tracked?: boolean;
    id: string;
}
export interface VizDictKeyValuePair { key: VizRepresentation; value: VizRepresentation; }

// Structure to hold info about the last change *per variable*
// This is used for highlighting triggering, the path identifies the target
export interface VizChangeInfo {
    change_type: string;
    path: (string | number)[]; // Path within the variable where change occurred
    // value_representation?: VizRepresentation | null; // We don't store this here, it's applied to main state
    timestamp: number;
}
export interface VizState {
    variables: { [name: string]: VizRepresentation }; // The current state representation
    lastChanges: { [name: string]: VizChangeInfo }; // Info about the LAST change event *for triggering highlight*
}

// Grid Module
export interface GridState { /* ... */ size: [number, number]; cells: { [key: string]: { color?: string | null; text?: string | null } }; }
// Console Module
export interface ConsoleState { /* ... */ lines: string[]; }
// Canvas Module State
export interface CanvasDrawCommand { /* ... */ command: string; options: any; commandId: string | number; }
export interface CanvasState { /* ... */ width: number; height: number; bgColor: string; lastCommand: CanvasDrawCommand | null; }

// --- Module Instance Type ---
type ModuleType = 'grid' | 'console' | 'viz' | 'canvas';
interface BaseModuleInstance { id: string; type: ModuleType; }
export interface GridModuleInstance extends BaseModuleInstance { type: 'grid'; state: GridState; }
export interface ConsoleModuleInstance extends BaseModuleInstance { type: 'console'; state: ConsoleState; }
export interface VizModuleInstance extends BaseModuleInstance { type: 'viz'; state: VizState; }
export interface CanvasModuleInstance extends BaseModuleInstance { type: 'canvas'; state: CanvasState; }
export type ModuleInstance = GridModuleInstance | ConsoleModuleInstance | VizModuleInstance | CanvasModuleInstance;

// --- Specific Message Payloads ---
export interface ConsoleNotifyPayload { event: 'submit'; value: string; }
export interface CanvasSpawnPayload { width: number; height: number; bgColor?: string; }
export interface CanvasUpdatePayload extends CanvasDrawCommand {}
// Updated Viz update payload type according to protocol.md
export interface VizUpdatePayload {
    variable_name: string;
    change_type: string; // "set" | "setitem" | "append" | "pop" | "update_dict" | "delitem" | "add_set" | "discard_set" | "clear" | "remove_variable"
    path: (string | number)[];
    value_representation: VizRepresentation | null;
    key_representation?: VizRepresentation | null; // Optional in protocol, make optional here
    length?: number | null; // Optional in protocol
}
export interface GridUpdatePayload { x?: number; y?: number; color?: string | null; text?: string | null; fill_color?: string; }

// Helper type for deep immutable updates
export type Path = (string | number)[];