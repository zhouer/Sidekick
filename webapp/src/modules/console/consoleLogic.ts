// Sidekick/webapp/src/modules/console/consoleLogic.ts
import { ConsoleState, ConsoleSpawnPayload, ConsoleUpdatePayload } from './types';

/**
 * Creates the initial state for a Console module.
 * @param instanceId - The ID of the console instance.
 * @param payload - The spawn payload containing required showInput and optional initial text.
 * @returns The initial ConsoleState.
 * @throws If showInput is missing in the payload.
 */
export function getInitialState(instanceId: string, payload: ConsoleSpawnPayload): ConsoleState {
    console.log(`ConsoleLogic ${instanceId}: Initializing state with payload:`, payload);

    // Validate essential parameters
    // Check if showInput is explicitly provided and is a boolean
    if (payload?.showInput === undefined || typeof payload.showInput !== 'boolean') {
        console.error(`ConsoleLogic ${instanceId}: Spawn failed - Missing or invalid 'showInput' (boolean) in payload:`, payload);
        throw new Error(`Console spawn failed for ${instanceId}: Missing or invalid 'showInput'.`);
    }

    return {
        // Initialize lines as an array containing the initial text, or an empty array
        lines: payload.text ? [payload.text] : [],
        // Store the required showInput flag
        showInput: payload.showInput,
    };
}

/**
 * Updates the state of a Console module based on an update payload.
 * Returns a new state object if changes were made.
 * @param currentState - The current state of the console.
 * @param payload - The update payload containing action and options.
 * @returns The updated ConsoleState.
 */
export function updateState(currentState: ConsoleState, payload: ConsoleUpdatePayload): ConsoleState {
    const { action, options } = payload;

    if (action === 'append') {
        // Validate options for append
        if (!options || options.text === undefined) {
            console.warn(`ConsoleLogic: Invalid 'append' options for state update.`, options);
            return currentState; // Return unchanged state
        }
        // Create a new lines array with the appended text (immutability)
        const updatedLines = [...currentState.lines, options.text];
        // Return the new state object (keeping existing showInput)
        return { ...currentState, lines: updatedLines };
    } else if (action === 'clear') {
        // Only update if there are lines to clear
        if (currentState.lines.length > 0) {
            console.log(`ConsoleLogic: Clearing console.`);
            // Return a new state object with an empty lines array (keeping existing showInput)
            return { ...currentState, lines: [] };
        } else {
            // Console is already empty, no state change
            return currentState;
        }
    } else {
        console.warn(`ConsoleLogic: Unknown action "${action}" received.`);
        return currentState;
    }
}