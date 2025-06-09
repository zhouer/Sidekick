// webapp/src/components/markdown/markdownLogic.ts
import { MarkdownState, MarkdownSpawnPayload, MarkdownUpdatePayload } from './types';
import { ChangeParentUpdate } from '../../types';

export function getInitialState(instanceId: string, payload: MarkdownSpawnPayload): MarkdownState {
    if (typeof payload.text !== 'string') {
        console.error(`MarkdownLogic ${instanceId}: Spawn failed - 'text' must be a string.`);
        throw new Error(`Markdown spawn failed for ${instanceId}: 'text' is required and must be a string.`);
    }
    return {
        text: payload.text,
    };
}

export function updateState(
    currentState: MarkdownState,
    payload: MarkdownUpdatePayload | ChangeParentUpdate,
    instanceId: string
): MarkdownState {
    if ('action' in payload && payload.action === "changeParent") {
        return currentState;
    }

    const specificPayload = payload as MarkdownUpdatePayload;
    switch (specificPayload.action) {
        case 'setText':
            if (typeof specificPayload.options?.text === 'string' && specificPayload.options.text !== currentState.text) {
                return { ...currentState, text: specificPayload.options.text };
            }
            return currentState; // No change if source is same or invalid
        default:
            console.warn(`MarkdownLogic ${instanceId}: Unknown action "${(specificPayload as any).action}"`);
            return currentState;
    }
}