import React, { useState, useEffect, useCallback, forwardRef } from 'react';
import { TextboxState, TextboxSubmitEvent } from './types';
import { SentMessage, ComponentHandle } from '../../types';
import './TextboxComponent.css';

interface TextboxComponentProps {
    id: string;
    state: TextboxState;
    onInteraction?: (message: SentMessage) => void;
}

const TextboxComponent = forwardRef<ComponentHandle | null, TextboxComponentProps>(
    ({ id, state, onInteraction }, ref) => {
        // Local state for the input's current visual value
        // This allows immediate user feedback while typing.
        // It's synchronized with `state.currentValue` from Python.
        const [inputValue, setInputValue] = useState(state.currentValue);

        // Effect to update local inputValue when state.currentValue (from Python) changes
        useEffect(() => {
            setInputValue(state.currentValue);
        }, [state.currentValue]);

        const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
            setInputValue(event.target.value);
            // 'on_change' is not supported yet, so no message sent here
        };

        const handleSubmit = useCallback(() => {
            if (onInteraction) {
                const eventMessage: TextboxSubmitEvent = {
                    id: 0,
                    component: 'textbox',
                    type: 'event',
                    src: id,
                    payload: { event: 'submit', value: inputValue },
                };
                onInteraction(eventMessage);
                // The Python side will receive this event and update its record.
                // If Python then sends a 'setValue' update, the useEffect above will sync.
            }
        }, [id, inputValue, onInteraction]);

        const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
            if (event.key === 'Enter') {
                handleSubmit();
            }
        };

        const handleBlur = () => {
            // Submit on blur as per common Textbox behavior for single-line inputs
            handleSubmit();
        };

        return (
            <input
                type="text"
                className="textbox-component"
                value={inputValue}
                placeholder={state.placeholder || ''}
                onChange={handleChange}
                onKeyDown={handleKeyDown}
                onBlur={handleBlur}
                aria-label={`Textbox input for ${id}`}
            />
        );
    }
);
TextboxComponent.displayName = 'TextboxComponent';
export default TextboxComponent;