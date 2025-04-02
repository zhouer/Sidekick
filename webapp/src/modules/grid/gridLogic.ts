// Sidekick/webapp/src/modules/grid/gridLogic.ts
import { GridState, GridSpawnPayload, GridUpdatePayload } from './types';

/**
 * Creates the initial state for a Grid module.
 * @param instanceId - The ID of the grid instance.
 * @param payload - The spawn payload containing the grid size.
 * @returns The initial GridState.
 * @throws If size in payload is invalid or missing.
 */
export function getInitialState(instanceId: string, payload: GridSpawnPayload): GridState {
    console.log(`GridLogic ${instanceId}: Initializing state with payload:`, payload);

    // Validate essential parameters
    if (!payload?.size || !Array.isArray(payload.size) || payload.size.length !== 2 || typeof payload.size[0] !== 'number' || typeof payload.size[1] !== 'number' || payload.size[0] <= 0 || payload.size[1] <= 0) {
        console.error(`GridLogic ${instanceId}: Spawn failed - Invalid or missing size in payload:`, payload);
        throw new Error(`Grid spawn failed for ${instanceId}: Invalid or missing size.`);
    }

    const [width, height] = payload.size;

    // Create the initial state ensuring 'size' is a [number, number] tuple
    return {
        size: [width, height], // Use validated size
        cells: {}, // Start with an empty cells object
    };
}

/**
 * Updates the state of a Grid module based on an update payload.
 * Returns a new state object if changes were made, otherwise the original state.
 * @param currentState - The current state of the grid.
 * @param payload - The update payload containing action and options.
 * @returns The updated GridState or the original state if no changes occurred.
 */
export function updateState(currentState: GridState, payload: GridUpdatePayload): GridState {
    const { action, options } = payload;

    if (action === 'setCell') {
        // Validate required options for setting a cell
        if (!options || typeof options.x !== 'number' || typeof options.y !== 'number') {
            console.warn(`GridLogic: Invalid 'setCell' options for state update (missing x or y).`, options);
            return currentState;
        }
        const key = `${options.x},${options.y}`;
        const currentCell = currentState.cells[key];

        // Determine the potential new state for the cell
        const potentialNewColor = options.color !== undefined ? options.color : currentCell?.color;
        const potentialNewText = options.text !== undefined ? options.text : currentCell?.text;

        // Check if the cell needs to be updated (either new or content changed)
        // Explicitly check for null/undefined vs empty string if that distinction matters
        const needsUpdate = !currentCell ||
            currentCell.color !== potentialNewColor ||
            currentCell.text !== potentialNewText;

        if (needsUpdate) {
            // Create the new cell state, removing keys if value is null/undefined
            const newCellState: { color?: string | null; text?: string | null } = {};
            if (potentialNewColor !== null && potentialNewColor !== undefined) {
                newCellState.color = potentialNewColor;
            }
            if (potentialNewText !== null && potentialNewText !== undefined && potentialNewText !== "") { // Also consider empty string as null for text
                newCellState.text = potentialNewText;
            }

            // Create new cells map immutably
            const updatedCells = { ...currentState.cells };

            // Add/update the cell only if it has content, otherwise remove the key
            if (Object.keys(newCellState).length > 0) {
                updatedCells[key] = newCellState;
            } else {
                // Only delete if the key actually exists
                if (updatedCells[key]) {
                    delete updatedCells[key]; // Remove cell if it becomes empty
                } else {
                    // Key didn't exist and new state is empty, no change needed to the map
                    return currentState;
                }
            }

            // Check if the map reference or content actually changed
            // This comparison is slightly simplified; a deep compare isn't strictly necessary
            // because Immer handles structural sharing, but checking if the specific key's
            // value changed or was removed is a good indicator.
            if (currentState.cells[key] !== updatedCells[key]) {
                return { ...currentState, cells: updatedCells };
            } else {
                return currentState; // No effective change to this cell
            }

        } else {
            return currentState; // No change needed
        }
    } else if (action === 'clear') {
        // Only clear if there are cells currently set
        if (Object.keys(currentState.cells).length > 0) {
            console.log(`GridLogic: Clearing grid.`);
            return { ...currentState, cells: {} }; // Return new state with empty cells
        } else {
            return currentState; // Already empty, no change
        }
    } else {
        console.warn(`GridLogic: Unknown action "${action}" received.`);
        return currentState; // Return unchanged state for unknown actions
    }
}