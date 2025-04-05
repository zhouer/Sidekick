// Sidekick/webapp/src/modules/grid/gridLogic.ts
import { GridState, GridSpawnPayload, GridUpdatePayload } from './types';

/**
 * Creates the initial state for a Grid module.
 * @param instanceId - The ID of the grid instance.
 * @param payload - The spawn payload containing the grid dimensions (numColumns, numRows).
 * @returns The initial GridState.
 * @throws If numColumns or numRows in payload are invalid or missing.
 */
export function getInitialState(instanceId: string, payload: GridSpawnPayload): GridState {
    console.log(`GridLogic ${instanceId}: Initializing state with payload:`, payload);

    // Validate essential parameters: numColumns and numRows
    if (!payload || typeof payload.numColumns !== 'number' || typeof payload.numRows !== 'number' || payload.numColumns <= 0 || payload.numRows <= 0) {
        console.error(`GridLogic ${instanceId}: Spawn failed - Invalid or missing numColumns/numRows in payload:`, payload);
        throw new Error(`Grid spawn failed for ${instanceId}: Invalid or missing numColumns/numRows.`);
    }

    const { numColumns, numRows } = payload;

    // Create the initial state using validated dimensions
    return {
        numColumns: numColumns,
        numRows: numRows,
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

        // Also validate coordinates against state dimensions
        if (options.x < 0 || options.x >= currentState.numColumns || options.y < 0 || options.y >= currentState.numRows) {
            console.warn(`GridLogic: 'setCell' coordinates (${options.x}, ${options.y}) out of bounds (${currentState.numColumns}x${currentState.numRows}). Ignoring.`);
            return currentState;
        }

        const key = `${options.x},${options.y}`;
        const currentCell = currentState.cells[key];

        // Determine the potential new state for the cell
        const potentialNewColor = options.color !== undefined ? options.color : currentCell?.color;
        const potentialNewText = options.text !== undefined ? options.text : currentCell?.text;

        // Check if the cell needs to be updated (either new or content changed)
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
            if (currentState.cells[key] !== updatedCells[key]) {
                // Return new state object (keeping existing numColumns/numRows)
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
            // Return new state with empty cells (keeping existing numColumns/numRows)
            return { ...currentState, cells: {} };
        } else {
            return currentState; // Already empty, no change
        }
    } else {
        console.warn(`GridLogic: Unknown action "${action}" received.`);
        return currentState; // Return unchanged state for unknown actions
    }
}