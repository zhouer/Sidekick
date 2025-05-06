import { produce } from "immer";
import {
    Path,
    VizChangeInfo,
    VizDictKeyValuePair,
    VizRepresentation,
    VizSpawnPayload,
    VizState,
    VizUpdatePayload
} from './types';

// --- Helper function to find a node within the Immer draft state ---
/**
 * Navigates through the draft state to find the node at the specified path.
 * @param draftState The Immer draft state.
 * @param variableName The name of the variable to start navigation from.
 * @param path The path segments to navigate.
 * @returns The node found at the path, or undefined if navigation fails.
 */
function findNodeInDraft(draftState: VizState, variableName: string, path: Path): any {
    // If path is empty, return the root representation of the variable
    if (!path || path.length === 0) {
        return draftState.variables[variableName];
    }

    // Start navigation from the variable's root representation
    let currentNode: any = draftState.variables[variableName];
    if (!currentNode) {
        console.warn(`VizLogic: Variable "${variableName}" not found during navigation.`);
        return undefined; // Variable doesn't exist
    }

    // Iterate through each segment in the path
    for (let i = 0; i < path.length; i++) {
        const segment = path[i];

        // Check if the current node is navigable (must be an object/representation)
        if (currentNode === null || typeof currentNode !== 'object' || !('type' in currentNode)) {
            console.error(`VizLogic: Path navigation failed at segment ${i} ('${segment}'). Current node is not a valid representation:`, currentNode);
            return undefined; // Cannot navigate further
        }

        // Navigate based on the current node's type
        switch (currentNode.type) {
            case 'list':
            case 'set': // Sets are represented as arrays internally
                // Navigate list/set by numeric index
                if (typeof segment !== 'number' || !Array.isArray(currentNode.value) || segment < 0 || segment >= currentNode.value.length) {
                    // Allow path to point just past the end for potential 'insert'/'setitem' append
                    if (i === path.length - 1 && segment === currentNode.value.length) {
                        break; // Let applyModification handle potential append/insert
                    }
                    console.error(`VizLogic: Path navigation failed at segment ${i}. Invalid list/set index '${segment}' for node:`, currentNode);
                    return undefined;
                }
                currentNode = currentNode.value[segment];
                break;
            case 'dict':
                // Navigate dictionary by key (matching value or ID)
                if (!Array.isArray(currentNode.value)) {
                    console.error(`VizLogic: Path navigation failed at segment ${i}. Invalid dict value (expected array of pairs) for node:`, currentNode);
                    return undefined;
                }
                // Find the key-value pair
                const pair: VizDictKeyValuePair | undefined = currentNode.value.find(
                    (p: VizDictKeyValuePair) => p?.key?.value === segment || p?.key?.id === String(segment)
                );

                // Special check: Is the path targeting the key itself? (e.g., for highlighting the key)
                if (!pair && path[i+1] === '(key)') {
                    const keyNode = currentNode.value.find((p: VizDictKeyValuePair) => (p?.key?.value === segment || p?.key?.id === String(segment)));
                    if (keyNode) {
                        currentNode = keyNode.key;
                        i++; // Important: Skip the next '(key)' segment in the path
                        break; // Continue to next segment after the key
                    }
                }

                if (!pair) {
                    // Allow path to point to a non-existent key if it's the last segment (for adding items)
                    if (i === path.length - 1) {
                        break; // Let applyModification handle adding the new key-value pair
                    }
                    console.error(`VizLogic: Path navigation failed at segment ${i}. Dict key "${segment}" not found in node:`, currentNode);
                    return undefined;
                }
                // Navigate into the value part of the pair
                currentNode = pair.value;
                break;
            case 'object':
            case 'repr': // Assume repr might contain navigable attributes
                // Navigate object by attribute name (string segment)
                if (typeof segment !== 'string' || typeof currentNode.value !== 'object' || currentNode.value === null) {
                    console.error(`VizLogic: Path navigation failed at segment ${i}. Invalid object/repr navigation for segment '${segment}' in node:`, currentNode);
                    return undefined;
                }
                if (!(segment in currentNode.value)) {
                    // Allow path to point to a non-existent attribute if it's the last segment (for adding)
                    if (i === path.length - 1) {
                        break; // Let applyModification handle adding the new attribute
                    }
                    console.error(`VizLogic: Path navigation failed at segment ${i}. Object/repr attribute "${segment}" not found in node:`, currentNode);
                    return undefined;
                }
                currentNode = currentNode.value[segment];
                break;
            default:
                // Handle navigation attempt on unsupported types
                console.error(`VizLogic: Path navigation failed at segment ${i}. Segment '${segment}' incompatible with node type '${currentNode.type}' in node:`, currentNode);
                return undefined;
        }

        // Check if navigation resulted in undefined unexpectedly (unless it's the last step)
        if (currentNode === undefined && i < path.length - 1) {
            console.error(`VizLogic: Path navigation yielded undefined before reaching the end of the path at segment ${i} ('${segment}').`);
            return undefined;
        }
    }
    // Return the node found at the end of the path (or potentially undefined if path points to a non-existent final element)
    return currentNode;
}


// --- Helper function to apply modifications directly to the Immer draft ---
/**
 * Applies the specified modification (action) to the draft state at the given path.
 * Modifies the draft state directly.
 * @param draftState The Immer draft state.
 * @param variableName The name of the variable being modified.
 * @param action The update action (e.g., 'setitem', 'append').
 * @param path The path to the node *relative to the variable root*.
 * @param options The payload options containing value/key representations and length.
 * @returns True if the modification was applied successfully, false otherwise.
 */
function applyModification(
    draftState: VizState,
    variableName: string,
    action: string,
    path: Path,
    options: VizUpdatePayload['options']
): boolean {
    // Destructure necessary data from options
    const { valueRepresentation, keyRepresentation, length } = options;
    // Standardize handling of the new length value
    const newLength = (length !== undefined && length !== null) ? length : undefined;

    // Find the parent node within the draft. If path is empty, the variable root is the parent.
    let parentNode: any = draftState.variables[variableName];
    let targetSegment: string | number | undefined = undefined;

    if (path.length > 0) {
        const parentPath = path.slice(0, -1);
        parentNode = findNodeInDraft(draftState, variableName, parentPath); // Find parent in draft
        targetSegment = path[path.length - 1]; // Get the final key/index
    } // If path is empty, parentNode remains the root, targetSegment is undefined

    // Check if the parent node was successfully found
    if (parentNode === undefined) {
        console.error(`VizLogic Apply: Failed to find parent node for path [${path.join(', ')}]`);
        return false; // Cannot apply modification if parent doesn't exist
    }

    try {
        // Apply modification based on the action type
        switch (action) {
            case 'set':
                // Handle setting the value at a specific path (root or nested)
                if (path.length === 0) {
                    // Setting the root variable's representation
                    if (!valueRepresentation) throw new Error("Missing valueRepresentation for root 'set'");
                    draftState.variables[variableName] = valueRepresentation; // Replace entire root
                } else {
                    // Setting a value at a nested path (behaves like setitem)
                    if (targetSegment === undefined || !valueRepresentation) throw new Error("Invalid targetSegment or missing valueRepresentation for nested 'set'");
                    if (parentNode.type === 'list' && typeof targetSegment === 'number') {
                        parentNode.value[targetSegment] = valueRepresentation; // Update list item
                    } else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) {
                        // Update or add dictionary item
                        const pairIndex = parentNode.value.findIndex((p: any) => p?.key?.value === targetSegment || p?.key?.id === String(targetSegment));
                        if (pairIndex !== -1) {
                            parentNode.value[pairIndex].value = valueRepresentation; // Update existing
                        } else if (keyRepresentation) {
                            parentNode.value.push({ key: keyRepresentation, value: valueRepresentation }); // Add new
                            parentNode.length = newLength ?? (parentNode.length || 0) + 1; // Update length if new
                        } else {
                            throw new Error("Cannot add dict item without keyRepresentation");
                        }
                    } else if (parentNode.type?.startsWith('object') && typeof targetSegment === 'string' && parentNode.value) {
                        parentNode.value[targetSegment] = valueRepresentation; // Update object attribute
                    } else {
                        throw new Error(`Nested 'set'/'setitem' failed for parent type ${parentNode.type} at segment ${targetSegment}`);
                    }
                    // Update length if provided by the backend
                    if (newLength !== undefined) parentNode.length = newLength;
                }
                break;

            case 'setitem':
                // Handle setting an item in a list, dict, or object
                if (targetSegment === undefined || !valueRepresentation) throw new Error("Invalid targetSegment or missing valueRepresentation for 'setitem'");
                if (parentNode.type === 'list' && typeof targetSegment === 'number') {
                    // List setitem
                    if (targetSegment < 0) throw new Error(`Negative index ${targetSegment} invalid.`);
                    // Allow setting at index equal to length (acts like append)
                    if (targetSegment >= parentNode.value.length) {
                        if(targetSegment === parentNode.value.length) {
                            parentNode.value.push(valueRepresentation); // Append
                            console.log(`VizLogic Apply: 'setitem' at index ${targetSegment} treated as append.`);
                        } else {
                            throw new Error(`Index ${targetSegment} out of bounds for list length ${parentNode.value.length}.`);
                        }
                    } else {
                        parentNode.value[targetSegment] = valueRepresentation; // Overwrite existing
                    }
                    if (newLength !== undefined) parentNode.length = newLength; // Update length if provided
                }
                else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) {
                    // Dict setitem (update or add)
                    const pairIndex = parentNode.value.findIndex((p: any) => p?.key?.value === targetSegment || p?.key?.id === String(targetSegment));
                    if (pairIndex !== -1) {
                        parentNode.value[pairIndex].value = valueRepresentation; // Update existing value
                    } else {
                        if (!keyRepresentation) throw new Error("Missing keyRepresentation for adding new dict item via setitem");
                        parentNode.value.push({ key: keyRepresentation, value: valueRepresentation }); // Add new pair
                        parentNode.length = newLength ?? (parentNode.length || 0) + 1; // Update length
                    }
                }
                else if (parentNode.type?.startsWith('object') && typeof targetSegment === 'string' && parentNode.value) {
                    // Object attribute set (add or update)
                    parentNode.value[targetSegment] = valueRepresentation;
                    if (newLength !== undefined) parentNode.length = newLength; // Update length if provided
                } else {
                    throw new Error(`'setitem' cannot be applied to parent type ${parentNode.type} with segment ${targetSegment}`);
                }
                break;

            case 'append':
                // Append item to a list
                if (parentNode.type !== 'list' || !Array.isArray(parentNode.value)) throw new Error("'append' target must be a list representation");
                if (!valueRepresentation) throw new Error("Missing valueRepresentation for 'append'");
                parentNode.value.push(valueRepresentation); // Append to the list's value array
                parentNode.length = newLength ?? (parentNode.length || 0) + 1; // Update length
                break;

            case 'insert':
                // Insert item into a list at a specific index
                if (parentNode.type !== 'list' || !Array.isArray(parentNode.value)) throw new Error("'insert' target must be a list representation");
                if (typeof targetSegment !== 'number') throw new Error("'insert' path segment must be a numeric index");
                if (!valueRepresentation) throw new Error("Missing valueRepresentation for 'insert'");
                parentNode.value.splice(targetSegment, 0, valueRepresentation); // Insert into array
                parentNode.length = newLength ?? (parentNode.length || 0) + 1; // Update length
                break;

            case 'pop':
            case 'remove': // Treat remove like delitem
            case 'delitem':
                // Remove item from list, dict, or object
                if (targetSegment === undefined) throw new Error("Missing targetSegment for removal action");
                if (parentNode.type === 'list' && typeof targetSegment === 'number') {
                    // Remove list item by index
                    if (targetSegment < 0 || targetSegment >= parentNode.value.length) throw new Error(`Removal index ${targetSegment} out of bounds`);
                    parentNode.value.splice(targetSegment, 1); // Remove from array
                    parentNode.length = newLength ?? (parentNode.length || 1) - 1; // Update length
                }
                else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) {
                    // Remove dict item by key
                    const initialLength = parentNode.value.length;
                    parentNode.value = parentNode.value.filter(
                        (p: any) => !(p?.key?.value === targetSegment || p?.key?.id === String(targetSegment))
                    ); // Filter out the item
                    // Update length only if an item was actually removed
                    if (parentNode.value.length < initialLength) {
                        parentNode.length = newLength ?? (parentNode.length || 1) - 1;
                    }
                }
                else if (parentNode.type?.startsWith('object') && typeof targetSegment === 'string' && parentNode.value) {
                    // Delete object attribute
                    if (targetSegment in parentNode.value) {
                        delete parentNode.value[targetSegment];
                        if (newLength !== undefined) parentNode.length = newLength;
                    } else {
                        console.warn(`VizLogic Apply: Attribute "${targetSegment}" not found for deletion.`);
                    }
                } else {
                    throw new Error(`Removal action cannot be applied to parent type ${parentNode.type} with segment ${targetSegment}`);
                }
                break;

            case 'add_set':
                // Add element to a set (represented as an array)
                if (!parentNode.type?.endsWith('set') || !Array.isArray(parentNode.value)) throw new Error("'add_set' target must be a set representation");
                if (!valueRepresentation) throw new Error("Missing valueRepresentation for 'add_set'");
                // Check if item (by ID) already exists to maintain set uniqueness
                const exists = parentNode.value.some((item: any) => item?.id === valueRepresentation?.id);
                if (!exists) {
                    parentNode.value.push(valueRepresentation); // Add if not present
                    parentNode.length = newLength ?? (parentNode.length || 0) + 1; // Update length
                }
                break;

            case 'discard_set':
                // Remove element from a set
                if (!parentNode.type?.endsWith('set') || !Array.isArray(parentNode.value)) throw new Error("'discard_set' target must be a set representation");
                // Requires valueRepresentation (usually for its ID) to identify the element
                if (!valueRepresentation?.id) throw new Error("Missing valueRepresentation.id for 'discard_set'");
                const initialSetLength = parentNode.value.length;
                // Filter out the item matching the ID
                parentNode.value = parentNode.value.filter((item: any) => item?.id !== valueRepresentation?.id);
                // Update length only if an item was removed
                if (parentNode.value.length < initialSetLength) {
                    parentNode.length = newLength ?? (parentNode.length || 1) - 1;
                }
                break;

            case 'clear':
                // Clear contents of a container (list, dict, set, object)
                if (parentNode.type === 'list' || parentNode.type === 'dict' || parentNode.type === 'set') {
                    parentNode.value = []; // Reset value to empty array
                    parentNode.length = 0; // Reset length
                } else if (parentNode.type?.startsWith('object') && parentNode.value) {
                    parentNode.value = {}; // Reset value to empty object
                    parentNode.length = 0; // Reset length
                } else {
                    console.warn(`VizLogic Apply: 'clear' action not applicable to type '${parentNode.type}'.`);
                }
                break;

            default:
                // Handle unknown actions
                throw new Error(`Unhandled action type "${action}"`);
        }
        // If no error was thrown, modification is considered successful
        return true;
    } catch (e: any) {
        // Log errors occurring during the modification attempt
        console.error(`VizLogic Apply: Error applying action "${action}" at path [${path.join(', ')}]:`, e.message || e);
        return false; // Modification failed
    }
}

// --- Viz Component Logic ---

/**
 * Creates the initial state for a Viz component.
 */
export function getInitialState(instanceId: string, payload: VizSpawnPayload): VizState {
    console.log(`VizLogic ${instanceId}: Initializing state.`);
    // Return the initial state structure
    return {
        variables: {},   // Start with no variables
        lastChanges: {}, // Start with no recorded changes
    };
}

/**
 * Updates the state of a Viz component based on variable changes using Immer.
 * Handles adding, updating (granularly), or removing variables.
 * Returns a new state object if changes were made.
 */
export function updateState(currentState: VizState, payload: VizUpdatePayload): VizState {
    // Use Immer's produce function for safe and easy immutable updates
    return produce(currentState, draftState => {
        const { action, variableName, options } = payload;
        // Default path to empty array if not provided in options
        const path = options?.path || [];

        // Basic validation of the incoming payload
        if (!action || !variableName) {
            console.warn(`VizLogic: Invalid viz update structure. Missing action or variableName.`, payload);
            return; // Exit the produce recipe; Immer returns the original state
        }

        // --- Action: Remove a variable ---
        if (action === 'removeVariable') {
            if (draftState.variables[variableName]) {
                // Directly delete the variable and its change info from the draft state
                delete draftState.variables[variableName];
                delete draftState.lastChanges[variableName];
                console.log(`VizLogic: Removed variable "${variableName}".`);
            } else {
                // Log if trying to remove a non-existent variable
                console.warn(`VizLogic: Variable "${variableName}" not found for removal.`);
            }
            return; // End the recipe for removeVariable
        }

        // --- Action: Add a new variable (via 'set' on root path) ---
        if (!draftState.variables[variableName]) {
            // Only allow creation via a 'set' action at the root path with a value representation
            if (action === 'set' && path.length === 0 && options?.valueRepresentation) {
                console.log(`VizLogic: Creating variable "${variableName}".`);
                // Directly assign the representation to the draft state
                draftState.variables[variableName] = options.valueRepresentation;
                // Record this initial 'set' action
                draftState.lastChanges[variableName] = { action, path, timestamp: Date.now() };
            } else {
                // Log error if trying to modify a non-existent variable without a valid root 'set'
                console.error(`VizLogic: Cannot apply action "${action}" to non-existent variable "${variableName}" without root 'set' payload.`);
            }
            return; // End the recipe after creation attempt or error
        }

        // --- Action: Update an existing variable ---
        // Attempt to apply the modification directly to the draft state
        const modificationSuccessful = applyModification(
            draftState,
            variableName,
            action,
            path,
            options || {} // Pass options or empty object
        );

        // If the modification was applied successfully, update the last change info
        if (modificationSuccessful) {
            draftState.lastChanges[variableName] = { action, path, timestamp: Date.now() };
        } else {
            // If applyModification returned false, an error occurred (already logged).
            // Immer will automatically discard the changes made to the draft in this recipe execution.
            console.warn(`VizLogic: Update failed for variable "${variableName}" (action: ${action}), state remains unchanged for this update.`);
        }

    }); // End of Immer's produce function
}