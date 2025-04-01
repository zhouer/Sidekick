// Sidekick/webapp/src/utils/stateUtils.ts
import {
    VizRepresentation,
    Path,
    VizUpdatePayload,
    VizDictKeyValuePair
} from '../types';

/**
 * Deeply clones a value, intended primarily for VizRepresentation structures.
 */
function cloneRepresentation<T>(value: T): T {
    if (value === null || typeof value !== 'object') { return value; }
    if (Array.isArray(value)) { return value.map(item => cloneRepresentation(item)) as any; }
    if (typeof value === 'object') {
        const clonedObj: { [key: string]: any } = {};
        for (const key in value) { if (Object.prototype.hasOwnProperty.call(value, key)) { clonedObj[key] = cloneRepresentation((value as any)[key]); } }
        return clonedObj as T;
    }
    return value;
}

/**
 * Navigates through a cloned VizRepresentation structure to find the parent node.
 */
function findParentNode(clonedRootRep: VizRepresentation, path: Path): any {
    if (!path || path.length === 0) { throw new Error("Cannot find parent for empty path."); }
    if (path.length === 1) { return clonedRootRep; } // Root is parent

    const parentPath = path.slice(0, -1);
    let currentNode: any = clonedRootRep;

    for (let i = 0; i < parentPath.length; i++) {
        const segment = parentPath[i];
        if (currentNode === null || typeof currentNode !== 'object') { throw new Error(`Path fail seg ${i}: Node not object.`); }

        switch (currentNode.type) {
            case 'list':
                if (typeof segment !== 'number' || !Array.isArray(currentNode.value) || segment < 0 || segment >= currentNode.value.length) { throw new Error(`Invalid list index '${segment}'`); }
                currentNode = currentNode.value[segment];
                break;
            case 'dict':
                if (!Array.isArray(currentNode.value)) { throw new Error(`Invalid dict value (not array)`); }
                const pair: VizDictKeyValuePair | undefined = currentNode.value.find((p: VizDictKeyValuePair) => p?.key?.value === segment || p?.key?.id === segment);
                if (!pair) { throw new Error(`Dict key "${segment}" not found`); }
                currentNode = pair.value;
                break;
            case 'object': // Handles object attributes
                if (typeof segment !== 'string' || typeof currentNode.value !== 'object' || currentNode.value === null) { throw new Error(`Invalid object navigation for segment '${segment}'`); }
                if (!(segment in currentNode.value)) { throw new Error(`Object attr "${segment}" not found`); }
                currentNode = currentNode.value[segment];
                break; // FIX: Add break here to prevent fallthrough
            case 'repr': // Let repr fall through to default if not handled like object
                // If repr value *could* be structured like an object, handle it here, otherwise fallthrough
                console.warn(`Navigating potentially unstructured 'repr' type at path segment ${i}. Assuming object-like structure for segment '${segment}'.`);
                if (typeof segment !== 'string' || typeof currentNode.value !== 'object' || currentNode.value === null) {
                    // If repr value isn't an object or segment isn't string, path is invalid here
                    throw new Error(`Path segment '${segment}' incompatible with 'repr' node value`);
                }
                if (!(segment in currentNode.value)) { throw new Error(`Attribute "${segment}" not found in 'repr' value`); }
                currentNode = currentNode.value[segment];
                break; // Added break if repr was handled like object
            default:
                throw new Error(`Segment '${segment}' incompatible with node type '${currentNode.type}'`);
        }
    }
    return currentNode;
}


/**
 * Applies the specific update operation directly onto the (cloned) parent node representation.
 */
function applyUpdateToParent(
    parentNode: any,
    changeType: string,
    targetSegment: string | number,
    options: VizUpdatePayload['options']
) {
    const { valueRepresentation, keyRepresentation, length } = options; // Destructure from options

    switch (changeType) {
        case 'setitem':
            // ... (setitem logic remains the same, using valueRepresentation/keyRepresentation from options) ...
            if (valueRepresentation === null || valueRepresentation === undefined) { throw new Error("Missing 'valueRepresentation' for 'setitem'"); }
            const clonedValueRep = cloneRepresentation(valueRepresentation);
            if (parentNode.type === 'list' && typeof targetSegment === 'number' && Array.isArray(parentNode.value)) { if (targetSegment < 0 || targetSegment >= parentNode.value.length) throw new Error(`setitem index ${targetSegment} out of bounds`); parentNode.value[targetSegment] = clonedValueRep; }
            else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) { const keyToUpdate = targetSegment; const pairIndex = parentNode.value.findIndex((p: VizDictKeyValuePair) => p?.key?.value === keyToUpdate || p?.key?.id === keyToUpdate); if (pairIndex !== -1) { parentNode.value[pairIndex].value = clonedValueRep; } else { if (!keyRepresentation) throw new Error("Missing 'keyRepresentation' for new dict item"); parentNode.value.push({ key: cloneRepresentation(keyRepresentation), value: clonedValueRep }); parentNode.length = (length !== undefined && length !== null) ? length : (parentNode.length || 0) + 1; } }
            else if (parentNode.type?.startsWith('object') && typeof targetSegment === 'string' && typeof parentNode.value === 'object') { parentNode.value[targetSegment] = clonedValueRep; if (length !== undefined && length !== null) parentNode.length = length; }
            else { throw new Error(`'setitem' target type mismatch`); }
            break;
        case 'append':
            // ... (append logic remains the same, using valueRepresentation from options) ...
            if (parentNode.type !== 'list' || !Array.isArray(parentNode.value)) { throw new Error("'append' target must be list"); }
            if (valueRepresentation === null || valueRepresentation === undefined) { throw new Error("Missing 'valueRepresentation' for 'append'"); }
            parentNode.value.push(cloneRepresentation(valueRepresentation));
            parentNode.length = (length !== undefined && length !== null) ? length : (parentNode.length || 0) + 1;
            break;
        case 'insert':
            // ... (insert logic remains the same, using valueRepresentation from options) ...
            if (parentNode.type !== 'list' || !Array.isArray(parentNode.value)) { throw new Error("'insert' target must be list"); }
            if (typeof targetSegment !== 'number') { throw new Error("'insert' path segment must be index"); }
            if (valueRepresentation === null || valueRepresentation === undefined) { throw new Error("Missing 'valueRepresentation' for 'insert'"); }
            parentNode.value.splice(targetSegment, 0, cloneRepresentation(valueRepresentation));
            parentNode.length = (length !== undefined && length !== null) ? length : (parentNode.length || 0) + 1;
            break;
        case 'pop': case 'remove': case 'delitem':
            // ... (delete logic remains the same, using length from options) ...
            const newLength = (length !== undefined && length !== null) ? length : undefined;
            if (parentNode.type === 'list' && typeof targetSegment === 'number' && Array.isArray(parentNode.value)) { if (targetSegment < 0 || targetSegment >= parentNode.value.length) { throw new Error(`del/pop index ${targetSegment} out of bounds`); } parentNode.value.splice(targetSegment, 1); parentNode.length = newLength ?? (parentNode.length || 1) - 1; }
            else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) { const keyToRemove = targetSegment; const initialLength = parentNode.value.length; parentNode.value = parentNode.value.filter((p: VizDictKeyValuePair) => !(p?.key?.value === keyToRemove || p?.key?.id === keyToRemove)); if (parentNode.value.length < initialLength) { parentNode.length = newLength ?? (parentNode.length || 1) - 1; } }
            else if (parentNode.type?.startsWith('object') && typeof targetSegment === 'string' && typeof parentNode.value === 'object') { if (targetSegment in parentNode.value) { delete parentNode.value[targetSegment]; if (newLength !== undefined) parentNode.length = newLength; } }
            else { throw new Error(`'del/pop' target type mismatch`); }
            break;
        case 'add_set':
            // ... (add_set logic remains the same, using valueRepresentation/length from options) ...
            if (!parentNode.type?.endsWith('set') || !Array.isArray(parentNode.value)) { throw new Error("'add_set' target not set"); }
            if (valueRepresentation === null || valueRepresentation === undefined) { throw new Error("Missing 'valueRepresentation' for 'add_set'"); }
            const valRepAdd = valueRepresentation; const lenAdd = length;
            const exists = parentNode.value.some((item: any) => item?.id === valRepAdd?.id);
            if (!exists) { parentNode.value.push(cloneRepresentation(valRepAdd)); parentNode.length = (lenAdd !== undefined && lenAdd !== null) ? lenAdd : (parentNode.length || 0) + 1; }
            break;
        case 'discard_set':
            // ... (discard_set logic remains the same, using valueRepresentation/length from options) ...
            if (!parentNode.type?.endsWith('set') || !Array.isArray(parentNode.value)) { throw new Error("'discard_set' target not set"); }
            if (valueRepresentation === null || valueRepresentation === undefined) { throw new Error("Missing 'valueRepresentation' for 'discard_set'"); }
            const valRepDiscard = valueRepresentation; const lenDiscard = length;
            const initialSetLength = parentNode.value.length;
            parentNode.value = parentNode.value.filter((item: any) => item?.id !== valRepDiscard?.id);
            if (parentNode.value.length < initialSetLength) { parentNode.length = (lenDiscard !== undefined && lenDiscard !== null) ? lenDiscard : (parentNode.length || 1) - 1; }
            break;
        default:
            throw new Error(`Unhandled change type "${changeType}" during update application.`);
    }
}

/**
 * Immutably updates a VizRepresentation structure at a given path based on a change payload.
 */
export function updateRepresentationAtPath(
    currentRootRep: VizRepresentation | undefined,
    payload: VizUpdatePayload
): VizRepresentation {

    const { action: changeType, options } = payload;
    const { path = [] } = options || {}; // Default path

    if (!currentRootRep) {
        if (changeType === 'set' && options?.valueRepresentation) { return cloneRepresentation(options.valueRepresentation); }
        else { throw new Error(`Cannot apply action "${changeType}" to non-existent variable.`); }
    }

    const newRootRep = cloneRepresentation(currentRootRep) as VizRepresentation;

    if (!path || path.length === 0) {
        // Apply root-level changes directly to newRootRep
        applyUpdateToParent(newRootRep, changeType, '', options || {}); // Pass empty options if null
        return newRootRep; // Return potentially modified root
    }

    try {
        const parentNode = findParentNode(newRootRep, path);
        if (parentNode === null || typeof parentNode !== 'object') { throw new Error("Target parent node not found or invalid."); }
        const targetSegment = path[path.length - 1];
        applyUpdateToParent(parentNode, changeType, targetSegment, options || {}); // Pass empty options if null
    } catch (e) {
        console.error(`Reducer/VizUtil: Failed update at path [${path?.join(', ')}]:`, e, "\nPayload:", payload, "\nCurrent RootRep:", currentRootRep);
        return newRootRep; // Return unmodified clone on error
    }

    return newRootRep;
}