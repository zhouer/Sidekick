// Sidekick/webapp/src/modules/canvas/canvasLogic.ts
import { CanvasState, CanvasSpawnPayload, CanvasUpdatePayload } from './types';

/**
 * Creates the initial state for a Canvas module.
 * @param instanceId - The ID of the canvas instance.
 * @param payload - The spawn payload containing width and height.
 * @returns The initial CanvasState.
 * @throws If width or height are missing or invalid in the payload.
 */
export function getInitialState(instanceId: string, payload: CanvasSpawnPayload): CanvasState {
    console.log(`CanvasLogic ${instanceId}: Initializing state with payload:`, payload);
    // Validate essential parameters
    if (!payload || typeof payload.width !== 'number' || payload.width <= 0 ||
        typeof payload.height !== 'number' || payload.height <= 0) {
        console.error(`CanvasLogic ${instanceId}: Spawn failed - Missing or invalid width/height in payload:`, payload);
        throw new Error(`Canvas spawn failed for ${instanceId}: Missing or invalid width/height.`);
    }
    // Initial state no longer includes commandQueue
    return {
        width: payload.width,
        height: payload.height,
    };
}

/**
 * Updates the state of a Canvas module.
 * **Note:** For Canvas (with imperativeUpdate: true), this function should
 * generally NOT be called for 'update' actions. It's kept for potential
 * future non-imperative updates or consistency. It currently does nothing.
 *
 * @param currentState - The current state of the canvas.
 * @param payload - The update payload (unused for imperative updates).
 * @returns The original currentState.
 */
export function updateState(currentState: CanvasState, payload: CanvasUpdatePayload): CanvasState {
    // Since Canvas updates are handled imperatively, this reducer function
    // for 'update' actions should ideally not be reached. If it is, we
    // return the current state without modification.
    console.warn(`CanvasLogic (${currentState.width}x${currentState.height}): updateState called unexpectedly for imperative module. Payload:`, payload);
    return currentState;
}