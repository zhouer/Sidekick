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
        return currentState;
    }

    const specificPayload = payload as TextboxUpdatePayload;
    let changed = false;
    const newState = { ...currentState };

    switch (specificPayload.action) {
        case 'setValue':
            if (typeof specificPayload.options?.value === 'string' && specificPayload.options.value !== currentState.currentValue) {
                newState.currentValue = specificPayload.options.value;
                changed = true;
            }
            break;
        case 'setPlaceholder':
            if (typeof specificPayload.options?.placeholder === 'string' && specificPayload.options.placeholder !== currentState.placeholder) {
                newState.placeholder = specificPayload.options.placeholder;
                changed = true;
            }
            break;
        default:
            console.warn(`TextboxLogic ${instanceId}: Unknown action "${(specificPayload as any).action}"`);
            return currentState;
    }
    return changed ? newState : currentState;
}