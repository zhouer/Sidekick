// Sidekick/webapp/src/types/index.ts

// --- Communication Message Types ---

interface BaseMessage {
    id: number;
    module: string;
    method: string;
}

export interface HeroMessage extends BaseMessage {
    method: 'spawn' | 'update' | 'remove' | 'remove_var';
    target: string;
    payload?: any;
}

export interface SidekickMessage extends BaseMessage {
    method: 'notify' | 'error';
    src: string;
    payload?: any;
}


// --- Module State Types ---

/**
 * Represents the recursive structure received from Python's _get_representation.
 * Includes type info, value (primitive or nested), optional length, and node ID.
 */
export interface VizRepresentation {
    type: string;
    value: any;
    length?: number;
    observable_tracked?: boolean; // <-- Renamed from viz_wrapped
    id: string;
}

export interface VizDictKeyValuePair {
    key: VizRepresentation;
    value: VizRepresentation;
}
export interface VizState {
    variables: { [name: string]: VizRepresentation };
    lastChanges: {
        [name: string]: {
            change_type: string; // e.g., 'replace', 'observable_update'
            change_details?: any;
            timestamp: number;
        }
    }
}

// Grid Module
export interface GridState {
    size: [number, number];
    cells: { [key: string]: { color?: string | null; text?: string | null } };
}

// Console Module
export interface ConsoleState {
    lines: string[];
}

// Canvas Module State
export interface CanvasDrawCommand {
    command: string;
    options: any;
    commandId: string | number;
}
export interface CanvasState {
    width: number;
    height: number;
    bgColor: string;
    lastCommand: CanvasDrawCommand | null;
}


// --- Module Instance Type ---
type ModuleType = 'grid' | 'console' | 'viz' | 'canvas';

interface BaseModuleInstance {
    id: string;
    type: ModuleType;
}

export interface GridModuleInstance extends BaseModuleInstance { type: 'grid'; state: GridState; }
export interface ConsoleModuleInstance extends BaseModuleInstance { type: 'console'; state: ConsoleState; }
export interface VizModuleInstance extends BaseModuleInstance { type: 'viz'; state: VizState; }
export interface CanvasModuleInstance extends BaseModuleInstance { type: 'canvas'; state: CanvasState; }

export type ModuleInstance = GridModuleInstance | ConsoleModuleInstance | VizModuleInstance | CanvasModuleInstance;


// --- Specific Message Payloads ---

// Console Notify Payload (User Input)
export interface ConsoleNotifyPayload { event: 'submit'; value: string; }

// Canvas Payloads
export interface CanvasSpawnPayload { width: number; height: number; bgColor?: string; }
export interface CanvasUpdatePayload extends CanvasDrawCommand {}

// Viz Payloads
export interface VizUpdatePayload {
    variable_name: string;
    representation: VizRepresentation;
    change_type?: string;   // e.g., 'replace', 'observable_update'
    change_details?: any;   // Could contain original change type from Observable like 'append', 'setitem' if needed
}
export interface VizRemoveVarPayload { variable_name: string; }

// Grid Payloads (Example)
export interface GridUpdatePayload {
    x?: number; y?: number; color?: string | null; text?: string | null; fill_color?: string;
}