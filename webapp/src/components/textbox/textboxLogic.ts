import { TextboxState, TextboxSpawnPayload, TextboxUpdatePayload } from './types';
import { ChangeParentUpdate } from '../../types';

export function getInitialState(instanceId: string, payload: TextboxSpawnPayload): TextboxState {
    return {
        currentValue: payload.initialValue || '',
        placeholder: payload.placeholder,
    };
}

export function updateState(
    currentState: TextboxState,
    payload: TextboxUpdatePayload | ChangeParentUpdate,
    instanceId: string
): TextboxState {
    if ('action' in payload && payload.action === "changeParent") {
        // For changeParent action, no state change is needed.
        return currentState;
    }

    const specificPayload = payload as TextboxUpdatePayload;

    switch (specificPayload.action) {
        case 'setValue':
            // Always return a new state object for 'setValue' to ensure component reactivity.
            // Update currentValue if the payload provides a valid string value.
            // If options.value is undefined or not a string, retain the existing currentValue.
            const newCurrentValue = (specificPayload.options && typeof specificPayload.options.value === 'string')
                ? specificPayload.options.value
                : currentState.currentValue;
            return { ...currentState, currentValue: newCurrentValue };

        case 'setPlaceholder':
            // Always return a new state object for 'setPlaceholder'.
            // Update placeholder if the payload provides a valid string value.
            // If options.placeholder is undefined or not a string, retain the existing placeholder.
            const newPlaceholder = (specificPayload.options && typeof specificPayload.options.placeholder === 'string')
                ? specificPayload.options.placeholder
                : currentState.placeholder;
            return { ...currentState, placeholder: newPlaceholder };

        default:
            console.warn(`TextboxLogic ${instanceId}: Unknown action "${(specificPayload as any).action}"`);
            // For unknown actions, return the original state.
            return currentState;
    }
}

