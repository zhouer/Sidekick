import React, { forwardRef } from 'react';
import { ColumnState } from './types';
import { ComponentHandle } from '../../types';
import './ColumnComponent.css';

interface ColumnComponentProps {
    id: string;
    state: ColumnState; // Contains childrenOrder
    childrenIds?: string[];
    renderChild?: (childId: string) => React.ReactNode;
}

const ColumnComponent = forwardRef<ComponentHandle | null, ColumnComponentProps>(
    ({ id, state, childrenIds, renderChild }, ref) => {
        // const { childrenOrder } = state;

        return (
            <div className="column-component" data-testid={`column-${id}`}>
                {childrenIds && renderChild
                    ? childrenIds.map(childId => renderChild(childId))
                    : null}
            </div>
        );
    }
);
ColumnComponent.displayName = 'ColumnComponent';
export default ColumnComponent;