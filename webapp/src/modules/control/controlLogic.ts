// Sidekick/webapp/src/modules/control/controlLogic.ts
import { ControlState, ControlSpawnPayload, ControlUpdatePayload, ControlDefinition } from './types';

/**
 * Creates the initial state for a Control module.
 * @param instanceId - The ID of the control panel instance.
 * @param payload - The spawn payload (currently unused).
 * @returns The initial ControlState.
 */
export function getInitialState(instanceId: string, payload: ControlSpawnPayload): ControlState {
    console.log(`ControlLogic ${instanceId}: Initializing state.`);
    // Control module starts with an empty map of controls
    return {
        controls: new Map<string, ControlDefinition>(),
    };
}

/**
 * Updates the state of a Control module based on an update payload (add or remove).
 * Returns a new state object if changes were made.
 * @param currentState - The current state of the control panel.
 * @param payload - The update payload containing action, controlId, and options (for add).
 * @returns The updated ControlState.
 */
export function updateState(currentState: ControlState, payload: ControlUpdatePayload): ControlState {
    const { action: controlAction, controlId, options } = payload;

    // Validate the payload structure
    if (!controlAction || !controlId) {
        console.warn(`ControlLogic: Invalid control update structure. Missing action or controlId.`, payload);
        return currentState; // Return unchanged state
    }

    // Create a mutable copy of the controls map to potentially modify
    const updatedControls = new Map(currentState.controls);
    let changed = false; // Flag to track if the state actually changed

    if (controlAction === 'add') {
        // Validate options for adding a control
        if (!options || !options.controlType || !options.config) {
            console.warn(`ControlLogic: Invalid 'add' control options. Missing controlType or config.`, options);
            return currentState; // Return unchanged state
        }
        // Create the definition for the new control
        const newControlDef: ControlDefinition = {
            id: controlId,
            type: options.controlType,
            config: options.config,
        };
        // Add or overwrite the control in the map
        updatedControls.set(controlId, newControlDef);
        console.log(`ControlLogic: Added/Updated control "${controlId}".`);
        changed = true; // Mark state as changed

    } else if (controlAction === 'remove') {
        // Check if the control exists before attempting to delete
        if (updatedControls.has(controlId)) {
            updatedControls.delete(controlId);
            console.log(`ControlLogic: Removed control "${controlId}".`);
            changed = true; // Mark state as changed
        } else {
            // Log a warning if trying to remove a non-existent control
            console.warn(`ControlLogic: Control ID "${controlId}" not found for removal.`);
            // No state change occurred
        }
    } else {
        // Log a warning for unknown actions
        console.warn(`ControlLogic: Unknown action "${controlAction}" received.`);
        return currentState;
    }

    // If the state changed, return a new state object with the updated controls map
    if (changed) {
        return { controls: updatedControls };
    } else {
        // Otherwise, return the original state object
        return currentState;
    }
}