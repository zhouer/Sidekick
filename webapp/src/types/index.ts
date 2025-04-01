// Sidekick/webapp/src/types/index.ts

// --- Communication Message Types ---
interface BaseMessage { id: number; module: string; method: string; }
export interface HeroMessage extends BaseMessage { method: 'spawn' | 'update' | 'remove'; target: string; payload?: any; }
export interface SidekickMessage extends BaseMessage { method: 'notify' | 'error'; src: string; payload?: any; }

// --- Module State Types ---
export interface VizRepresentation { type: string; value: any; length?: number; observableTracked?: boolean; id: string; }
export interface VizDictKeyValuePair { key: VizRepresentation; value: VizRepresentation; }
export type Path = (string | number)[];

// FIX: Remove changeType, keep only action to align with VizUpdatePayload
export interface VizChangeInfo {
    action: string; // Type of change action (e.g., "setitem", "append")
    path: Path;
    timestamp: number;
}
export interface VizState { variables: { [name: string]: VizRepresentation }; lastChanges: { [name: string]: VizChangeInfo }; }
export interface GridState { size: [number, number]; cells: { [key: string]: { color?: string | null; text?: string | null } }; }
export interface ConsoleState { lines: string[]; }
// CanvasUpdatePayload definition moved below
export interface CanvasState { width: number; height: number; bgColor: string; commandQueue: CanvasUpdatePayload[]; } // Queue holds full update payloads
export type ControlType = "button" | "text_input";
export interface ControlDefinition { id: string; type: ControlType; config: { text?: string; placeholder?: string; initialValue?: string; buttonText?: string; }; }
export interface ControlState { controls: Map<string, ControlDefinition>; }

// --- Module Instance Type ---
// ... (ModuleType, BaseModuleInstance, specific instances remain the same) ...
type ModuleType = 'grid' | 'console' | 'viz' | 'canvas' | 'control';
interface BaseModuleInstance { id: string; type: ModuleType; }
export interface GridModuleInstance extends BaseModuleInstance { type: 'grid'; state: GridState; }
export interface ConsoleModuleInstance extends BaseModuleInstance { type: 'console'; state: ConsoleState; }
export interface VizModuleInstance extends BaseModuleInstance { type: 'viz'; state: VizState; }
export interface CanvasModuleInstance extends BaseModuleInstance { type: 'canvas'; state: CanvasState; }
export interface ControlModuleInstance extends BaseModuleInstance { type: 'control'; state: ControlState; }
export type ModuleInstance = GridModuleInstance | ConsoleModuleInstance | VizModuleInstance | CanvasModuleInstance | ControlModuleInstance;


// --- Specific Message Payloads (REVISED based on new protocol) ---

// == Grid ==
export interface GridSpawnPayload { size: [number, number]; }
export interface GridUpdatePayload { action: "setCell" | "clear"; options?: { x?: number; y?: number; color?: string | null; text?: string | null; }; }
export interface GridNotifyPayload { event: 'click'; x: number; y: number; }

// == Console ==
export interface ConsoleSpawnPayload { text?: string; }
export interface ConsoleUpdatePayload { action: "append" | "clear"; options?: { text?: string; }; }
export interface ConsoleNotifyPayload { event: 'submit'; value: string; }

// == Viz ==
export interface VizSpawnPayload {}
export interface VizUpdatePayload {
    action: string;
    variableName: string;
    options: { // Parameters grouped under options
        path?: Path;
        valueRepresentation?: VizRepresentation | null;
        keyRepresentation?: VizRepresentation | null;
        length?: number | null;
    };
}

// == Canvas ==
export interface CanvasSpawnPayload { width: number; height: number; bgColor?: string; }
export interface CanvasUpdatePayload { // This IS the item in the queue now
    action: string;
    options: any;
    commandId: string | number; // REQUIRED unique ID
}

// == Control ==
export interface ControlSpawnPayload {}
export interface ControlUpdatePayload { action: "add" | "remove"; controlId: string; options?: { controlType?: ControlType; config?: ControlDefinition['config']; }; }
export interface ControlNotifyPayload { event: "click" | "submit"; controlId: string; value?: string; }
// --- End Specific Message Payloads ---