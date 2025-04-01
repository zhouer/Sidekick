// Sidekick/webapp/src/modules/viz/vizLogic.ts

import {
    VizState,
    VizSpawnPayload,
    VizUpdatePayload,
    VizRepresentation,
    Path,
    VizDictKeyValuePair
} from './types';

// --- Helper Functions ---

/**
 * Deeply clones a value, intended primarily for VizRepresentation structures.
 * Ensures immutability when updating nested state.
 */
function cloneRepresentation<T>(value: T): T {
    // Handle primitives and null
    if (value === null || typeof value !== 'object') {
        return value;
    }

    // Handle arrays by recursively cloning each item
    if (Array.isArray(value)) {
        // Use 'as any' temporarily as TS struggles with mapping complex types here
        return value.map(item => cloneRepresentation(item)) as any;
    }

    // Handle generic objects (plain objects, likely part of VizRepresentation structure)
    if (typeof value === 'object') {
        const clonedObj: { [key: string]: any } = {};
        for (const key in value) {
            // Ensure we only copy own properties
            if (Object.prototype.hasOwnProperty.call(value, key)) {
                clonedObj[key] = cloneRepresentation((value as any)[key]);
            }
        }
        return clonedObj as T;
    }

    // Fallback for unexpected types (should ideally not be reached with VizRepresentations)
    return value;
}

/**
 * Navigates through a cloned VizRepresentation structure based on a path
 * to find the *parent* node of the target segment.
 * Used to apply updates immutably within the nested structure.
 * @param clonedRootRep The root of the cloned representation to navigate.
 * @param path The path segments leading to the target node.
 * @returns The parent node representation.
 * @throws If the path is invalid or navigation fails.
 */
function findParentNode(clonedRootRep: VizRepresentation, path: Path): any {
    // Cannot find parent for root level changes or empty path
    if (!path || path.length === 0) {
        throw new Error("Cannot find parent for empty or root path. Use applyUpdateToParent directly on root.");
    }
    // If path has only one segment, the root is the parent
    if (path.length === 1) {
        return clonedRootRep;
    }

    // Get the path excluding the final target segment
    const parentPath = path.slice(0, -1);
    let currentNode: any = clonedRootRep; // Start navigation from the root

    // Iterate through the parent path segments
    for (let i = 0; i < parentPath.length; i++) {
        const segment = parentPath[i];

        // Ensure the current node is navigable (an object or potentially array)
        if (currentNode === null || typeof currentNode !== 'object') {
            throw new Error(`Path navigation failed at segment ${i} ('${segment}'): Current node is not an object or array.`);
        }

        // Navigate based on the current node's type
        switch (currentNode.type) {
            case 'list':
                // Ensure segment is a valid index for the list's value array
                if (typeof segment !== 'number' || !Array.isArray(currentNode.value) || segment < 0 || segment >= currentNode.value.length) {
                    throw new Error(`Path navigation failed at segment ${i}: Invalid list index '${segment}'.`);
                }
                currentNode = currentNode.value[segment]; // Move to the list item
                break;
            case 'dict':
                // Ensure the dictionary value is the expected array of pairs
                if (!Array.isArray(currentNode.value)) {
                    throw new Error(`Path navigation failed at segment ${i}: Invalid dict value (expected array of pairs).`);
                }
                // Find the key-value pair matching the segment (either by primitive value or ID)
                const pair: VizDictKeyValuePair | undefined = currentNode.value.find(
                    (p: VizDictKeyValuePair) => p?.key?.value === segment || p?.key?.id === segment
                );
                if (!pair) {
                    throw new Error(`Path navigation failed at segment ${i}: Dict key "${segment}" not found.`);
                }
                currentNode = pair.value; // Move to the value part of the pair
                break;
            case 'object': // Handle standard object attribute access
            case 'repr':   // Assume 'repr' might be object-like if navigating with string key
                // Ensure segment is a string and value is a non-null object
                if (typeof segment !== 'string' || typeof currentNode.value !== 'object' || currentNode.value === null) {
                    throw new Error(`Path navigation failed at segment ${i}: Invalid object/repr navigation for segment '${segment}'.`);
                }
                // Check if the attribute exists on the object's value
                if (!(segment in currentNode.value)) {
                    throw new Error(`Path navigation failed at segment ${i}: Object/repr attribute "${segment}" not found.`);
                }
                currentNode = currentNode.value[segment]; // Move to the attribute value
                break;
            default:
                // Handle cases where navigation is attempted on an unsupported type
                throw new Error(`Path navigation failed at segment ${i}: Segment '${segment}' incompatible with node type '${currentNode.type}'.`);
        }
    }
    // After iterating through the parent path, currentNode is the direct parent
    return currentNode;
}


/**
 * Applies a specific update operation (like setitem, append, pop)
 * directly onto the provided parent node representation (which should be a clone).
 * This function mutates the *cloned* parent node.
 * @param parentNode The cloned parent node representation to modify.
 * @param changeAction The specific action ('setitem', 'append', etc.).
 * @param targetSegment The final segment of the path (e.g., index for list, key for dict).
 * @param options The options payload from the VizUpdatePayload, containing necessary data like value/key representations and length.
 * @throws If the operation is invalid for the parent node type or options are missing.
 */
function applyUpdateToParent(
    parentNode: any, // Should be a mutable clone
    changeAction: string,
    targetSegment: string | number,
    options: VizUpdatePayload['options']
) {
    // Destructure required data from the options payload
    const { valueRepresentation, keyRepresentation, length } = options;
    const newLength = (length !== undefined && length !== null) ? length : undefined; // Standardize new length handling

    switch (changeAction) {
        case 'set': // Assuming 'set' applies directly to the parent node's value when path is root
            if (valueRepresentation === null || valueRepresentation === undefined) {
                throw new Error("Missing 'valueRepresentation' in options for 'set'");
            }
            // Directly update the value property of the parentNode (which is the rootRep clone in this case)
            parentNode.value = cloneRepresentation(valueRepresentation.value); // <-- Key change: Apply primitive value?
            parentNode.type = valueRepresentation.type; // <-- Also update type?
            parentNode.observableTracked = valueRepresentation.observableTracked; // <-- Update tracked status?
            if (newLength !== undefined) parentNode.length = newLength;
            break;

        case 'setitem':
            // Need value representation for setting an item
            if (valueRepresentation === null || valueRepresentation === undefined) {
                throw new Error("Missing 'valueRepresentation' in options for 'setitem'");
            }
            const clonedValueRep = cloneRepresentation(valueRepresentation); // Clone value before assigning

            if (parentNode.type === 'list' && typeof targetSegment === 'number' && Array.isArray(parentNode.value)) {
                // List item update by index
                if (targetSegment < 0 || targetSegment >= parentNode.value.length) {
                    throw new Error(`'setitem' index ${targetSegment} out of bounds for list of length ${parentNode.value.length}`);
                }
                parentNode.value[targetSegment] = clonedValueRep;
                // Length typically doesn't change on list setitem unless explicitly provided
                if (newLength !== undefined) parentNode.length = newLength;

            } else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) {
                // Dictionary item update/add by key
                const keyToUpdate = targetSegment;
                const pairIndex = parentNode.value.findIndex(
                    (p: VizDictKeyValuePair) => p?.key?.value === keyToUpdate || p?.key?.id === keyToUpdate
                );
                if (pairIndex !== -1) {
                    // Update existing value
                    parentNode.value[pairIndex].value = clonedValueRep;
                } else {
                    // Add new key-value pair
                    if (!keyRepresentation) {
                        throw new Error("Missing 'keyRepresentation' in options for adding new dict item");
                    }
                    parentNode.value.push({ key: cloneRepresentation(keyRepresentation), value: clonedValueRep });
                    // Update length if adding new item
                    parentNode.length = newLength ?? (parentNode.length || 0) + 1;
                }

            } else if (parentNode.type?.startsWith('object') && typeof targetSegment === 'string' && typeof parentNode.value === 'object') {
                // Object attribute update/add
                parentNode.value[targetSegment] = clonedValueRep;
                // Length might change if explicitly provided (e.g., for custom object representations)
                if (newLength !== undefined) parentNode.length = newLength;

            } else {
                throw new Error(`'setitem' target type '${parentNode.type}' or segment type mismatch.`);
            }
            break;

        case 'append':
            // Requires a list and a value representation
            if (parentNode.type !== 'list' || !Array.isArray(parentNode.value)) {
                throw new Error("'append' target must be a list representation");
            }
            if (valueRepresentation === null || valueRepresentation === undefined) {
                throw new Error("Missing 'valueRepresentation' in options for 'append'");
            }
            parentNode.value.push(cloneRepresentation(valueRepresentation));
            // Update length after append
            parentNode.length = newLength ?? (parentNode.length || 0) + 1;
            break;

        case 'insert':
            // Requires a list, index (targetSegment), and value representation
            if (parentNode.type !== 'list' || !Array.isArray(parentNode.value)) {
                throw new Error("'insert' target must be a list representation");
            }
            if (typeof targetSegment !== 'number') {
                throw new Error("'insert' path segment must be a numeric index");
            }
            if (valueRepresentation === null || valueRepresentation === undefined) {
                throw new Error("Missing 'valueRepresentation' in options for 'insert'");
            }
            // Insert at the specified index
            parentNode.value.splice(targetSegment, 0, cloneRepresentation(valueRepresentation));
            // Update length after insert
            parentNode.length = newLength ?? (parentNode.length || 0) + 1;
            break;

        case 'pop':
        case 'remove': // Treat 'remove' similarly to 'delitem' or 'pop'
        case 'delitem':
            // Handle deletion from list, dict, or object attribute
            if (parentNode.type === 'list' && typeof targetSegment === 'number' && Array.isArray(parentNode.value)) {
                // List item removal by index
                if (targetSegment < 0 || targetSegment >= parentNode.value.length) {
                    throw new Error(`'del/pop' index ${targetSegment} out of bounds for list of length ${parentNode.value.length}`);
                }
                parentNode.value.splice(targetSegment, 1);
                // Update length after removal
                parentNode.length = newLength ?? (parentNode.length || 1) - 1;

            } else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) {
                // Dictionary item removal by key
                const keyToRemove = targetSegment;
                const initialLength = parentNode.value.length;
                // Filter out the pair matching the key
                parentNode.value = parentNode.value.filter(
                    (p: VizDictKeyValuePair) => !(p?.key?.value === keyToRemove || p?.key?.id === keyToRemove)
                );
                // Update length only if an item was actually removed
                if (parentNode.value.length < initialLength) {
                    parentNode.length = newLength ?? (parentNode.length || 1) - 1;
                }

            } else if (parentNode.type?.startsWith('object') && typeof targetSegment === 'string' && typeof parentNode.value === 'object') {
                // Object attribute deletion
                if (targetSegment in parentNode.value) {
                    delete parentNode.value[targetSegment];
                    // Update length if explicitly provided
                    if (newLength !== undefined) parentNode.length = newLength;
                }

            } else {
                throw new Error(`'del/pop/remove' target type '${parentNode.type}' or segment type mismatch.`);
            }
            break;

        case 'add_set':
            // Requires a set and a value representation
            if (!parentNode.type?.endsWith('set') || !Array.isArray(parentNode.value)) {
                throw new Error("'add_set' target must be a set representation (array value)");
            }
            if (valueRepresentation === null || valueRepresentation === undefined) {
                throw new Error("Missing 'valueRepresentation' in options for 'add_set'");
            }
            const valRepAdd = valueRepresentation;
            // Check if item (identified by ID) already exists
            const exists = parentNode.value.some((item: any) => item?.id === valRepAdd?.id);
            if (!exists) {
                parentNode.value.push(cloneRepresentation(valRepAdd));
                // Update length if item was added
                parentNode.length = newLength ?? (parentNode.length || 0) + 1;
            }
            break;

        case 'discard_set':
            // Requires a set and a value representation (to identify the item to discard)
            if (!parentNode.type?.endsWith('set') || !Array.isArray(parentNode.value)) {
                throw new Error("'discard_set' target must be a set representation (array value)");
            }
            // Use valueRepresentation to identify the element to discard (typically by ID)
            if (valueRepresentation === null || valueRepresentation === undefined) {
                throw new Error("Missing 'valueRepresentation' (for ID) in options for 'discard_set'");
            }
            const valRepDiscard = valueRepresentation;
            const initialSetLength = parentNode.value.length;
            // Filter out the item matching the ID
            parentNode.value = parentNode.value.filter((item: any) => item?.id !== valRepDiscard?.id);
            // Update length only if an item was actually removed
            if (parentNode.value.length < initialSetLength) {
                parentNode.length = newLength ?? (parentNode.length || 1) - 1;
            }
            break;

        default:
            // Handle unknown change types
            throw new Error(`Unhandled change action type "${changeAction}" during update application.`);
    }
}


/**
 * Immutably updates a VizRepresentation structure at a given path based on a change payload.
 * This is the core function used by the Viz module's updateState logic.
 * @param currentRootRep The current root VizRepresentation for the variable (can be undefined if just created).
 * @param payload The VizUpdatePayload containing the action, variableName, and options (path, values, etc.).
 * @returns The new root VizRepresentation after applying the update.
 * @throws If the update cannot be applied (e.g., invalid path, missing data).
 */
export function updateRepresentationAtPath(
    currentRootRep: VizRepresentation | undefined,
    payload: VizUpdatePayload
): VizRepresentation {

    const { action: changeAction, options } = payload;
    const { path = [], valueRepresentation } = options || {}; // Default path to empty array

    // Handle initial creation (action 'set' on root path with value)
    if (!currentRootRep) {
        if (changeAction === 'set' && path.length === 0 && valueRepresentation) {
            // Create the initial representation by cloning the provided value
            return cloneRepresentation(valueRepresentation);
        } else {
            // Cannot apply other actions or non-root set to a non-existent variable
            throw new Error(`VizLogic: Cannot apply action "${changeAction}" to non-existent variable without root 'set' payload.`);
        }
    }

    // Start by cloning the current root representation to ensure immutability
    const newRootRep = cloneRepresentation(currentRootRep);

    try {
        // Handle updates at the root level (empty path)
        if (path.length === 0) {
            // Apply update directly to the cloned root
            applyUpdateToParent(newRootRep, changeAction, '', options || {}); // Pass empty segment and options
        } else {
            // For nested updates, find the parent node within the cloned structure
            const parentNode = findParentNode(newRootRep, path);
            // Ensure the parent node was found and is valid
            if (parentNode === null || typeof parentNode !== 'object') {
                throw new Error("Target parent node not found or invalid during path navigation.");
            }
            // Get the final segment of the path (the key/index within the parent)
            const targetSegment = path[path.length - 1];
            // Apply the update to the found parent node
            applyUpdateToParent(parentNode, changeAction, targetSegment, options || {});
        }
    } catch (e: any) {
        // Log detailed error information if the update fails
        console.error(`VizLogic: Failed to apply update at path [${path?.join(', ')}] with action "${changeAction}":`, e.message || e, "\nPayload:", payload, "\nCurrent RootRep:", currentRootRep);
        // Return the unmodified clone to prevent corrupted state
        return newRootRep;
    }

    // Return the potentially modified new root representation
    return newRootRep;
}

// --- Viz Module Logic ---

/**
 * Creates the initial state for a Viz module.
 * @param instanceId - The ID of the viz instance.
 * @param payload - Spawn payload (unused for Viz).
 * @returns Initial VizState with empty variables and changes.
 */
export function getInitialState(instanceId: string, payload: VizSpawnPayload): VizState {
    console.log(`VizLogic ${instanceId}: Initializing state.`);
    return {
        variables: {},   // No variables initially shown
        lastChanges: {}, // No changes recorded yet
    };
}

/**
 * Updates the state of a Viz module based on variable changes.
 * Handles adding, updating (granularly), or removing variables.
 * Returns a new state object if changes were made.
 * @param currentState - The current state of the Viz module.
 * @param payload - The update payload detailing the variable change.
 * @returns The updated VizState.
 */
export function updateState(currentState: VizState, payload: VizUpdatePayload): VizState {
    const { action: vizAction, variableName, options } = payload;

    // Validate essential parts of the payload
    if (!vizAction || !variableName) { // Options might be empty for removeVariable
        console.warn(`VizLogic: Invalid viz update structure. Missing action or variableName.`, payload);
        return currentState;
    }

    // Use path from options, default to empty array if not present
    const path = options?.path || [];

    // Create copies of current state parts for potential modification
    let newVariablesState = { ...currentState.variables };
    let newLastChanges = { ...currentState.lastChanges };
    let stateChanged = false; // Flag to track actual changes

    if (vizAction === 'removeVariable') {
        // Check if the variable exists before trying to remove
        if (newVariablesState[variableName]) {
            delete newVariablesState[variableName]; // Remove from variables map
            delete newLastChanges[variableName];  // Remove associated change info
            console.log(`VizLogic: Removed variable "${variableName}".`);
            stateChanged = true;
        } else {
            // Variable not found, no change needed
            return currentState;
        }
    } else {
        // Handle 'set' or granular updates using updateRepresentationAtPath
        const currentRepresentation = currentState.variables[variableName];

        try {
            // Calculate the new representation based on the current one and the update payload
            const updatedRepresentation = updateRepresentationAtPath(currentRepresentation, payload);

            // Check if the representation actually changed to avoid unnecessary state updates
            // (updateRepresentationAtPath returns original clone on error or no-op)
            if (updatedRepresentation !== currentRepresentation || !currentRepresentation) { // Also true if it was newly created
                // Update the variables map with the new representation
                newVariablesState[variableName] = updatedRepresentation;
                // Record the change details (action, path, timestamp) for highlighting
                newLastChanges[variableName] = {
                    action: vizAction, // Store the action type
                    path: path,        // Store the path of the change
                    timestamp: Date.now(), // Record when the change occurred
                };
                stateChanged = true; // Mark state as changed
                // Log if a variable was newly created
                if (!currentRepresentation && vizAction === 'set') {
                    console.log(`VizLogic: Created variable "${variableName}".`);
                }
            } else {
                // Representation didn't change (e.g., setitem with same value, or update error)
                return currentState;
            }
        } catch (e) {
            // Error during updateRepresentationAtPath (already logged there)
            // Return current state to prevent potential corruption
            return currentState;
        }
    }

    // If the state was changed (variable added, updated, or removed), return the new state object
    if (stateChanged) {
        return { variables: newVariablesState, lastChanges: newLastChanges };
    } else {
        // Otherwise, return the original state object
        return currentState;
    }
}