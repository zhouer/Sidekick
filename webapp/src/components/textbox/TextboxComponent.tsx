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
    ({ id, state, onInteraction }, _ref) => { // Mark ref as unused
        // Local state for the input's current visual value
        // This allows immediate user feedback while typing.
        // It's synchronized with `state.currentValue` from Python.
        const [inputValue, setInputValue] = useState(state.currentValue);
        // Stores the value that was last successfully submitted via onInteraction
        const [lastSubmittedValue, setLastSubmittedValue] = useState(state.currentValue);

        // Effect to update local inputValue and lastSubmittedValue when state.currentValue (from Python) changes
        useEffect(() => {
            setInputValue(state.currentValue);
            setLastSubmittedValue(state.currentValue); // Sync lastSubmittedValue with external changes
        }, [state]);

        const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
            setInputValue(event.target.value);
        };

        const handleSubmit = useCallback(() => {
            // Only send an event if the inputValue is different from the lastSubmittedValue
            if (onInteraction && inputValue !== lastSubmittedValue) {
                const eventMessage: TextboxSubmitEvent = {
                    id: 0,
                    component: 'textbox',
                    type: 'event',
                    src: id,
                    payload: { event: 'submit', value: inputValue },
                };
                onInteraction(eventMessage);
                setLastSubmittedValue(inputValue); // Update lastSubmittedValue after successful submission
            }
        }, [id, inputValue, onInteraction, lastSubmittedValue]);

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
