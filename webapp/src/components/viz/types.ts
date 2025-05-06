// --- Core Data Structures ---
export interface VizRepresentation {
    type: string;       // e.g., "list", "int", "str", "dict", "MyClass object"
    value: any;         // The actual value or representation (primitive, array of reps, object of reps)
    length?: number;    // Length if applicable (list, dict, set, etc.)
    observableTracked?: boolean; // True if this node came directly from an ObservableValue
    id: string;         // Unique ID for this representation node (for React keys, etc.)
}

// Specific structure for dictionary key-value pairs within VizRepresentation.value
export interface VizDictKeyValuePair {
    key: VizRepresentation;
    value: VizRepresentation;
}

// Type for representing the path to a nested element within a variable
export type Path = (string | number)[];

// --- State ---
export interface VizChangeInfo {
    action: string; // Type of change action (e.g., "setitem", "append")
    path: Path;     // Path to the changed element
    timestamp: number; // Timestamp of the change for highlighting
}

export interface VizState {
    variables: {
        // Maps variable name (string) to its root VizRepresentation
        [name: string]: VizRepresentation;
    };
    lastChanges: {
        // Maps variable name (string) to info about the last change for highlighting
        [name: string]: VizChangeInfo;
    };
}

// --- Payloads ---
export interface VizSpawnPayload {
    // Viz component typically doesn't need specific spawn payload options
}

export interface VizUpdatePayload {
    action: string;        // e.g., "set", "setitem", "append", "removeVariable"
    variableName: string;  // The name of the variable being affected
    options: {             // Options specific to the action
        path?: Path;                            // Path within the variable structure
        valueRepresentation?: VizRepresentation | null; // New value representation
        keyRepresentation?: VizRepresentation | null;   // Key representation (for dict setitem)
        length?: number | null;                 // New length (for container operations)
    };
}

// Viz component typically doesn't send notifications back based on direct interaction
// export interface VizNotifyPayload { ... }