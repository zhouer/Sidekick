import { ColumnState, ColumnSpawnPayload, ColumnUpdatePayload } from './types';
import { ChangeParentUpdate } from '../../types';

export function getInitialState(instanceId: string, payload: ColumnSpawnPayload): ColumnState {
    return {
        childrenOrder: [],
    };
}

export function updateState(
    currentState: ColumnState,
    payload: ColumnUpdatePayload | ChangeParentUpdate, // ColumnUpdatePayload is currently empty
    instanceId: string
): ColumnState {
    if ('action' in payload && payload.action === "changeParent") {
        return currentState;
    }
    const specificPayload = payload as ColumnUpdatePayload;
    // Handle future Column-specific updates here
    console.warn(`ColumnLogic ${instanceId}: Unknown or unhandled action "${(specificPayload as any).action}"`);
    return currentState;
}