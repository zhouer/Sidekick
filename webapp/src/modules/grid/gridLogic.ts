// Sidekick/webapp/src/modules/grid/gridLogic.ts
import { GridState, GridSpawnPayload, GridUpdatePayload } from './types';

/**
 * Creates the initial state for a Grid module.
 * @param instanceId - The ID of the grid instance.
 * @param payload - The spawn payload containing the grid size.
 * @returns The initial GridState.
 */
export function getInitialState(instanceId: string, payload: GridSpawnPayload): GridState {
    console.log(`GridLogic ${instanceId}: Initializing state with payload:`, payload);

    // Default grid dimensions
    let finalWidth = 10;
    let finalHeight = 10;

    // Check payload for valid size and update defaults if necessary
    if (payload?.size && payload.size.length === 2) {
        finalWidth = payload.size[0];
        finalHeight = payload.size[1];
    }

    // Create the initial state ensuring 'size' is a [number, number] tuple
    return {
        size: [finalWidth, finalHeight],
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
        if (!options || options.x === undefined || options.y === undefined) {
            console.warn(`GridLogic: Invalid 'setCell' options for state update.`, options);
            return currentState;
        }
        const key = `${options.x},${options.y}`;
        const currentCell = currentState.cells[key];
        // Determine new cell state, preserving existing properties if not provided
        const newCellState = {
            color: options.color !== undefined ? options.color : currentCell?.color,
            text: options.text !== undefined ? options.text : currentCell?.text,
        };
        // Only create new state if the cell content actually changed or cell is new
        if (!currentCell || currentCell.color !== newCellState.color || currentCell.text !== newCellState.text) {
            const updatedCells = { ...currentState.cells, [key]: newCellState, };
            return { ...currentState, cells: updatedCells };
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