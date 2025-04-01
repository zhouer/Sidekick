// Sidekick/webapp/src/modules/canvas/canvasLogic.ts
import { CanvasState, CanvasSpawnPayload, CanvasUpdatePayload } from './types';

/**
 * Creates the initial state for a Canvas module.
 * @param instanceId - The ID of the canvas instance.
 * @param payload - The spawn payload containing width, height, and optional background color.
 * @returns The initial CanvasState.
 * @throws If width or height are missing in the payload.
 */
export function getInitialState(instanceId: string, payload: CanvasSpawnPayload): CanvasState {
    console.log(`CanvasLogic ${instanceId}: Initializing state with payload:`, payload);
    // Validate essential parameters
    if (!payload || !payload.width || !payload.height) {
        // Log error and throw to prevent invalid state creation
        console.error(`CanvasLogic ${instanceId}: Spawn failed - Missing width or height in payload:`, payload);
        throw new Error(`Canvas spawn failed for ${instanceId}: Missing width or height.`);
    }
    return {
        width: payload.width,
        height: payload.height,
        bgColor: payload.bgColor || '#FFFFFF', // Default background color if not provided
        commandQueue: [], // Start with an empty command queue
    };
}

/**
 * Updates the state of a Canvas module based on an update payload.
 * Adds the new command to the command queue if the commandId is unique.
 * Returns a new state object if the command was added.
 * @param currentState - The current state of the canvas.
 * @param payload - The update payload containing the drawing command.
 * @returns The updated CanvasState.
 */
export function updateState(currentState: CanvasState, payload: CanvasUpdatePayload): CanvasState {
    const { action, options, commandId } = payload;

    // Validate the structure of the canvas update payload
    if (!action || !options || commandId === undefined || commandId === null) {
        console.warn(`CanvasLogic: Invalid canvas update payload structure received.`, payload);
        return currentState; // Return unchanged state
    }

    // Check if a command with the same ID already exists in the queue
    const existingIndex = currentState.commandQueue.findIndex(cmd => cmd.commandId === commandId);
    if (existingIndex !== -1) {
        // Log a warning if a duplicate command ID is detected, but don't modify state
        console.warn(`CanvasLogic: Duplicate commandId ${commandId} received. Ignoring.`);
        return currentState;
    }

    // Add the new valid command payload to the queue (immutability)
    const updatedQueue = [...currentState.commandQueue, payload];

    // Return the new state object with the updated command queue
    return { ...currentState, commandQueue: updatedQueue };
}