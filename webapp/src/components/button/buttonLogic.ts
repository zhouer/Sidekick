import { ButtonState, ButtonSpawnPayload, ButtonUpdatePayload } from './types';
import { ChangeParentUpdate } from '../../types';

export function getInitialState(instanceId: string, payload: ButtonSpawnPayload): ButtonState {
    if (typeof payload.text !== 'string') {
        console.error(`ButtonLogic ${instanceId}: Spawn failed - 'text' must be a string.`);
        throw new Error(`Button spawn failed for ${instanceId}: 'text' is required and must be a string.`);
    }
    return {
        text: payload.text,
    };
}

export function updateState(
    currentState: ButtonState,
    payload: ButtonUpdatePayload | ChangeParentUpdate,
    instanceId: string
): ButtonState {
    if ('action' in payload && payload.action === "changeParent") {
        return currentState;
    }

    const specificPayload = payload as ButtonUpdatePayload;
    switch (specificPayload.action) {
        case 'setText':
            if (typeof specificPayload.options?.text === 'string' && specificPayload.options.text !== currentState.text) {
                return { ...currentState, text: specificPayload.options.text };
            }
            return currentState;
        default:
            console.warn(`ButtonLogic ${instanceId}: Unknown action "${(specificPayload as any).action}"`);
            return currentState;
    }
}