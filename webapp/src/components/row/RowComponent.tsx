import React, { forwardRef } from 'react';
import { RowState } from './types';
import { ComponentHandle } from '../../types';
import './RowComponent.css';

interface RowComponentProps {
    id: string;
    state: RowState; // Contains childrenOrder
    // Props for rendering children, passed by App.tsx
    childrenIds?: string[]; // Ordered list of child component IDs
    renderChild?: (childId: string) => React.ReactNode; // Function to render a child
}

const RowComponent = forwardRef<ComponentHandle | null, RowComponentProps>(
    ({ id, state, childrenIds, renderChild }, ref) => {
        // const { childrenOrder } = state; // Or use childrenIds directly if passed from App

        return (
            <div className="row-component" data-testid={`row-${id}`}>
                {childrenIds && renderChild
                    ? childrenIds.map(childId => renderChild(childId))
                    : null}
            </div>
        );
    }
);
RowComponent.displayName = 'RowComponent';
export default RowComponent;