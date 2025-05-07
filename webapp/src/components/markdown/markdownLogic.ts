// webapp/src/components/markdown/markdownLogic.ts
import { MarkdownState, MarkdownSpawnPayload, MarkdownUpdatePayload } from './types';
import { ChangeParentUpdate } from '../../types';

export function getInitialState(instanceId: string, payload: MarkdownSpawnPayload): MarkdownState {
    if (typeof payload.initialSource !== 'string') {
        console.error(`MarkdownLogic ${instanceId}: Spawn failed - 'initialSource' must be a string.`);
        throw new Error(`Markdown spawn failed for ${instanceId}: 'initialSource' is required and must be a string.`);
    }
    return {
        source: payload.initialSource,
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
        case 'setSource':
            if (typeof specificPayload.options?.source === 'string' && specificPayload.options.source !== currentState.source) {
                return { ...currentState, source: specificPayload.options.source };
            }
            return currentState; // No change if source is same or invalid
        default:
            console.warn(`MarkdownLogic ${instanceId}: Unknown action "${(specificPayload as any).action}"`);
            return currentState;
    }
}