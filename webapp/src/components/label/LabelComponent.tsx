import React, { forwardRef } from 'react';
import { LabelState } from './types';
import { ComponentHandle } from '../../types'; // No onInteraction needed for Label
import './LabelComponent.css';

interface LabelComponentProps {
    id: string;
    state: LabelState;
    // No onInteraction or onReady for simple Label
}

const LabelComponent = forwardRef<ComponentHandle | null, LabelComponentProps>(
    ({ id, state }, ref) => {
        const { text } = state;

        // Label is purely display, no imperative handles needed for now
        // useImperativeHandle(ref, () => ({}), []);

        return (
            <span className="label-component" title={text} aria-label={`Label: ${text}`}>
                {text}
            </span>
        );
    }
);
LabelComponent.displayName = 'LabelComponent';
export default LabelComponent;