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

// Helper function to manage cell updates/removals immutably
function updateCellsMap(
    currentCells: GridState['cells'],
    key: string,
    newCellData: GridState['cells'][string] | null // Pass null to remove
): GridState['cells'] {
    const updatedCells = { ...currentCells }; // Clone the map

    if (newCellData && Object.keys(newCellData).length > 0) {
        // Only update if the new data is different from the old
        if (JSON.stringify(updatedCells[key]) !== JSON.stringify(newCellData)) {
            updatedCells[key] = newCellData;
            return updatedCells;
        }
    } else {
        // Remove the key if newCellData is null or empty
        if (updatedCells[key]) {
            delete updatedCells[key];
            return updatedCells;
        }
    }
    // If no effective change, return the original map reference
    return currentCells;
}


/**
 * Updates the state of a Grid module based on an update payload.
 * Returns a new state object if changes were made, otherwise the original state.
 * @param currentState - The current state of the grid.
 * @param payload - The update payload containing action and options.
 * @returns The updated GridState or the original state if no changes occurred.
 */
export function updateState(currentState: GridState, payload: GridUpdatePayload): GridState {
    const { action } = payload;

    switch (action) {
        case 'setColor': {
            const { options } = payload;
            if (!options || typeof options.x !== 'number' || typeof options.y !== 'number') {
                console.warn(`GridLogic: Invalid 'setColor' options (missing x or y).`, options);
                return currentState;
            }
            if (options.x < 0 || options.x >= currentState.numColumns || options.y < 0 || options.y >= currentState.numRows) {
                console.warn(`GridLogic: 'setColor' coordinates (${options.x}, ${options.y}) out of bounds (${currentState.numColumns}x${currentState.numRows}). Ignoring.`);
                return currentState;
            }

            const key = `${options.x},${options.y}`;
            const currentCell = currentState.cells[key];
            const newColor = options.color; // Can be null

            // Preserve existing text
            const newText = currentCell?.text;

            // Construct potential new cell state
            const newCellState: GridState['cells'][string] = {};
            if (newColor !== null) {
                newCellState.color = newColor;
            }
            // Keep existing text if it exists
            if (newText !== undefined && newText !== null) {
                newCellState.text = newText;
            }

            const updatedCells = updateCellsMap(currentState.cells, key, newCellState);

            // Return new state object only if the cells map reference changed
            if (updatedCells !== currentState.cells) {
                return { ...currentState, cells: updatedCells };
            }
            return currentState;
        }

        case 'setText': {
            const { options } = payload;
            if (!options || typeof options.x !== 'number' || typeof options.y !== 'number') {
                console.warn(`GridLogic: Invalid 'setText' options (missing x or y).`, options);
                return currentState;
            }
            if (options.x < 0 || options.x >= currentState.numColumns || options.y < 0 || options.y >= currentState.numRows) {
                console.warn(`GridLogic: 'setText' coordinates (${options.x}, ${options.y}) out of bounds (${currentState.numColumns}x${currentState.numRows}). Ignoring.`);
                return currentState;
            }

            const key = `${options.x},${options.y}`;
            const currentCell = currentState.cells[key];
            const newText = options.text; // Can be null or ""

            // Preserve existing color
            const newColor = currentCell?.color;

            // Construct potential new cell state
            const newCellState: GridState['cells'][string] = {};
            // Keep existing color if it exists
            if (newColor !== undefined && newColor !== null) {
                newCellState.color = newColor;
            }
            // Add text only if it's not null or empty (clearing)
            if (newText !== null && newText !== "") {
                newCellState.text = newText;
            }

            const updatedCells = updateCellsMap(currentState.cells, key, newCellState);

            // Return new state object only if the cells map reference changed
            if (updatedCells !== currentState.cells) {
                return { ...currentState, cells: updatedCells };
            }
            return currentState;
        }

        case 'clearCell': {
            const { options } = payload;
            if (!options || typeof options.x !== 'number' || typeof options.y !== 'number') {
                console.warn(`GridLogic: Invalid 'clearCell' options (missing x or y).`, options);
                return currentState;
            }
            if (options.x < 0 || options.x >= currentState.numColumns || options.y < 0 || options.y >= currentState.numRows) {
                console.warn(`GridLogic: 'clearCell' coordinates (${options.x}, ${options.y}) out of bounds (${currentState.numColumns}x${currentState.numRows}). Ignoring.`);
                return currentState;
            }

            const key = `${options.x},${options.y}`;

            // Use helper to remove the cell (passing null as new state)
            const updatedCells = updateCellsMap(currentState.cells, key, null);

            // Return new state object only if the cells map reference changed
            if (updatedCells !== currentState.cells) {
                return { ...currentState, cells: updatedCells };
            }
            return currentState;
        }

        case 'clear': {
            // Only clear if there are cells currently set
            if (Object.keys(currentState.cells).length > 0) {
                console.log(`GridLogic: Clearing entire grid.`);
                // Return new state with empty cells (keeping existing numColumns/numRows)
                return { ...currentState, cells: {} };
            } else {
                return currentState; // Already empty, no change
            }
        }

        default: {
            // Use exhaustive check with 'never' type for unhandled actions
            const exhaustiveCheck: never = action;
            console.warn(`GridLogic: Unknown action "${exhaustiveCheck}" received.`);
            return currentState; // Return unchanged state for unknown actions
        }
    }
}