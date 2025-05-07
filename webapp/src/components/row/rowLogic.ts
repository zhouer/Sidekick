import { RowState, RowSpawnPayload, RowUpdatePayload } from './types';
import { ChangeParentUpdate } from '../../types';

export function getInitialState(instanceId: string, payload: RowSpawnPayload): RowState {
    // Row's children order is managed by App.tsx for now,
    // but RowState could hold it if component definitions were more complex.
    return {
        childrenOrder: [], // Initially empty, will be populated by App.tsx
    };
}

export function updateState(
    currentState: RowState,
    payload: RowUpdatePayload | ChangeParentUpdate, // RowUpdatePayload is currently empty placeholder
    instanceId: string
): RowState {
    if ('action' in payload && payload.action === "changeParent") {
        // This is a generic action, the row component itself might not change its internal state based on this.
        // However, if RowState stored childrenOrder *from its own perspective*, it would update here.
        // For now, App.tsx handles the global component tree.
        return currentState;
    }

    const specificPayload = payload as RowUpdatePayload;
    // Handle future Row-specific updates here
    // e.g., if (specificPayload.action === "setGap") { ... }
    console.warn(`RowLogic ${instanceId}: Unknown or unhandled action "${(specificPayload as any).action}"`);
    return currentState;
}