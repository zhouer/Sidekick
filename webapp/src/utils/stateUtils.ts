// Sidekick/webapp/src/utils/stateUtils.ts
import { VizRepresentation, Path } from '../types';

/**
 * Deeply clones a VizRepresentation structure.
 */
function cloneRepresentation(rep: VizRepresentation | any): VizRepresentation | any {
    if (rep === null || typeof rep !== 'object') { return rep; }
    if (Array.isArray(rep)) { return rep.map(cloneRepresentation); }
    if (typeof rep === 'object') {
        const cloned: { [key: string]: any } = {};
        for (const key in rep) {
            if (Object.prototype.hasOwnProperty.call(rep, key)) {
                cloned[key] = cloneRepresentation(rep[key]);
            }
        }
        return cloned as VizRepresentation;
    }
    return rep;
}


// REMOVED the unused navigateRepresentation function


/**
 * Immutably updates a VizRepresentation structure at a given path.
 */
export function updateRepresentationAtPath(
    rootRep: VizRepresentation,
    payload: { change_type: string; path: Path; value_representation: VizRepresentation | null; key_representation?: VizRepresentation | null; length?: number | null; }
): VizRepresentation {

    const { change_type, path, value_representation, key_representation, length } = payload;
    const newRootRep = cloneRepresentation(rootRep) as VizRepresentation;

    // Handle root-level changes
    if (path.length === 0) {
        switch (change_type) {
            case 'set': if (!value_representation) throw new Error("Missing value_rep for 'set'"); return cloneRepresentation(value_representation);
            case 'clear': if (Array.isArray(newRootRep.value)) newRootRep.value = []; else if (typeof newRootRep.value === 'object') newRootRep.value = newRootRep.type === 'dict' ? [] : {}; else newRootRep.value = null; newRootRep.length = 0; return newRootRep;
            default: console.warn("Unexpected change type for root path:", change_type); return newRootRep;
        }
    }

    // Navigate to the parent of the target node
    const parentPath = path.slice(0, -1); const targetSegment = path[path.length - 1];
    let parentNode: any = newRootRep;

    try {
        for (let i = 0; i < parentPath.length; i++) {
            const segment = parentPath[i]; if (parentNode === null || typeof parentNode !== 'object') throw new Error("Parent path invalid");
            if (parentNode.type === 'list' && typeof segment === 'number' && Array.isArray(parentNode.value)) { parentNode = parentNode.value[segment]; }
            else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) { const pair = parentNode.value.find((p: any) => p.key?.value === segment || p.key?.id === segment); if (!pair) throw new Error(`Dict key "${segment}" not found in parent path`); parentNode = pair.value; }
            else if (parentNode.type?.startsWith('object') && typeof segment === 'string' && typeof parentNode.value === 'object') { if (!(segment in parentNode.value)) throw new Error(`Object attr "${segment}" not found in parent path`); parentNode = parentNode.value[segment]; }
            else { throw new Error("Parent path structure mismatch"); }
        }

        // Apply change within the parentNode
        switch (change_type) {
            case 'setitem': {
                if (!value_representation) throw new Error("Missing value_rep for 'setitem'"); const clonedValueRep = cloneRepresentation(value_representation);
                if (parentNode.type === 'list' && typeof targetSegment === 'number' && Array.isArray(parentNode.value)) { if (targetSegment < 0 || targetSegment >= parentNode.value.length) throw new Error("setitem index out of bounds"); parentNode.value[targetSegment] = clonedValueRep; }
                else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) { const keyToUpdate = targetSegment; const pairIndex = parentNode.value.findIndex((p: any) => p.key?.value === keyToUpdate || p.key?.id === keyToUpdate); if (pairIndex !== -1) { parentNode.value[pairIndex].value = clonedValueRep; } else { if (!key_representation) throw new Error("Missing key_rep for new dict item"); parentNode.value.push({ key: cloneRepresentation(key_representation), value: clonedValueRep }); if (length !== undefined && length !== null) parentNode.length = length; else parentNode.length++; } }
                else if (parentNode.type?.startsWith('object') && typeof targetSegment === 'string' && typeof parentNode.value === 'object') { parentNode.value[targetSegment] = clonedValueRep; if (length !== undefined && length !== null) parentNode.length = length; }
                else { throw new Error("setitem target type mismatch"); } break;
            }
            case 'append': { if (parentNode.type !== 'list' || !Array.isArray(parentNode.value)) throw new Error("append target must be list"); if (!value_representation) throw new Error("Missing value_rep for 'append'"); parentNode.value.push(cloneRepresentation(value_representation)); if (length !== undefined && length !== null) parentNode.length = length; else parentNode.length++; break; }
            case 'insert': { if (parentNode.type !== 'list' || !Array.isArray(parentNode.value)) throw new Error("insert target must be list"); if (typeof targetSegment !== 'number') throw new Error("insert path segment must be index"); if (!value_representation) throw new Error("Missing value_rep for 'insert'"); parentNode.value.splice(targetSegment, 0, cloneRepresentation(value_representation)); if (length !== undefined && length !== null) parentNode.length = length; else parentNode.length++; break; }
            case 'pop': case 'remove': case 'delitem': {
                if (parentNode.type === 'list' && typeof targetSegment === 'number' && Array.isArray(parentNode.value)) { if (targetSegment < 0 || targetSegment >= parentNode.value.length) throw new Error("delitem/pop index out of bounds"); parentNode.value.splice(targetSegment, 1); if (length !== undefined && length !== null) parentNode.length = length; else parentNode.length--; }
                else if (parentNode.type === 'dict' && Array.isArray(parentNode.value)) { const keyToRemove = targetSegment; const initialLength = parentNode.value.length; parentNode.value = parentNode.value.filter((p: any) => !(p.key?.value === keyToRemove || p.key?.id === keyToRemove)); if (parentNode.value.length < initialLength) { if (length !== undefined && length !== null) parentNode.length = length; else parentNode.length--; } }
                else if (parentNode.type?.startsWith('object') && typeof targetSegment === 'string' && typeof parentNode.value === 'object') { if (targetSegment in parentNode.value) { delete parentNode.value[targetSegment]; if (length !== undefined && length !== null) parentNode.length = length; } }
                else { throw new Error("delitem target type mismatch"); } break;
            }
            default: console.warn("Unhandled change type in updateRepresentationAtPath:", change_type);
        }
    } catch (e) { console.error("Error updating representation at path:", path, e); return newRootRep; } // Return unmodified clone on error
    return newRootRep;
}