import { LabelState, LabelSpawnPayload, LabelUpdatePayload } from './types';
import { ChangeParentUpdate } from '../../types'; // Import for updateState

export function getInitialState(instanceId: string, payload: LabelSpawnPayload): LabelState {
    if (typeof payload.text !== 'string') {
        console.error(`LabelLogic ${instanceId}: Spawn failed - 'text' must be a string.`);
        throw new Error(`Label spawn failed for ${instanceId}: 'text' is required and must be a string.`);
    }
    return {
        text: payload.text,
    };
}

export function updateState(
    currentState: LabelState,
    payload: LabelUpdatePayload | ChangeParentUpdate, // Handles specific updates or generic parent change
    instanceId: string
): LabelState {
    // Check if it's a ChangeParentUpdate action (handled globally, not by component logic)
    if ('action' in payload && payload.action === "changeParent") {
        // console.debug(`LabelLogic ${instanceId}: changeParent action received, state unchanged by component logic.`);
        return currentState; // No state change for the component itself
    }

    // Handle Label-specific updates
    const specificPayload = payload as LabelUpdatePayload;
    switch (specificPayload.action) {
        case 'setText':
            if (typeof specificPayload.options?.text === 'string' && specificPayload.options.text !== currentState.text) {
                return { ...currentState, text: specificPayload.options.text };
            }
            return currentState; // No change if text is same or invalid
        default:
            console.warn(`LabelLogic ${instanceId}: Unknown action "${(specificPayload as any).action}"`);
            return currentState;
    }
}