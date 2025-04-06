// Sidekick/webapp/src/modules/control/ControlComponent.tsx
import React, { useState, useCallback, useEffect } from 'react';
import { ControlState, ControlEventPayload } from './types';
import { SentMessage, ModuleEventMessage } from '../../types';
import './ControlComponent.css';

interface ControlComponentProps {
    id: string;
    state: ControlState;
    onInteraction?: (message: SentMessage) => void;
}

const ControlComponent: React.FC<ControlComponentProps> = ({ id, state, onInteraction }) => {
    const { controls } = state;

    // Local state to manage the *current* value of each text input after user interaction
    const [inputValues, setInputValues] = useState<Record<string, string>>(() => {
        // Initialize state map based on initial controls props
        const initial: Record<string, string> = {};
        controls.forEach(control => {
            if (control.type === 'textInput') {
                initial[control.id] = control.config?.initialValue || '';
            }
        });
        return initial;
    });

    // Effect to synchronize the *keys* in the local state with the controls map
    // and ensure new inputs get their initial value reflected in the state map
    useEffect(() => {
        setInputValues(currentInputValues => {
            const nextState = { ...currentInputValues };
            let stateChanged = false;

            // Ensure state has keys for all current textInput controls
            controls.forEach(control => {
                if (control.type === 'textInput') {
                    // If a new control was added, add its key to our local state
                    if (!(control.id in nextState)) {
                        // Initialize with the value from config
                        nextState[control.id] = control.config?.initialValue || '';
                        stateChanged = true;
                        console.log(`ControlComponent useEffect: Initialized state for new control ${control.id} with value "${nextState[control.id]}"`);
                    }
                    // Optional: If initialValue itself could change dynamically after mount
                    // else if (nextState[control.id] !== (control.config?.initialValue || '') && control.config?.initialValue !== undefined) {
                    //     nextState[control.id] = control.config.initialValue || '';
                    //     stateChanged = true;
                    // }
                }
            });

            // Remove keys for controls that no longer exist
            Object.keys(nextState).forEach(inputId => {
                if (!controls.has(inputId)) {
                    delete nextState[inputId];
                    stateChanged = true;
                    console.log(`ControlComponent useEffect: Removed state for control ${inputId}`);
                }
            });

            return stateChanged ? nextState : currentInputValues;
        });
    }, [controls]); // Rerun only when the set of controls changes


    // Handler for text input changes - Updates the local state
    const handleInputChange = (controlId: string, value: string) => {
        setInputValues(prev => ({
            ...prev,
            [controlId]: value,
        }));
    };

    // Handler for button clicks (no change needed)
    const handleButtonClick = useCallback((controlId: string) => {
        if (!onInteraction) {
            console.warn(`ControlComponent ${id}: onInteraction not provided, cannot send button click.`);
            return;
        }
        console.log(`Control ${id}: Button ${controlId} clicked.`);
        const payload: ControlEventPayload = { event: 'click', controlId: controlId };
        const message: ModuleEventMessage = { id: 0, module: 'control', type: 'event', src: id, payload };
        onInteraction(message);
    }, [id, onInteraction]);

    const handleTextSubmit = useCallback((controlId: string) => {
        if (!onInteraction) {
            console.warn(`ControlComponent ${id}: onInteraction not provided, cannot send text input.`);
            return;
        }
        const value = inputValues[controlId] || '';
        console.log(`Control ${id}: Input ${controlId} submitted with value: "${value}"`);
        const payload: ControlEventPayload = {
            event: 'inputText',
            controlId: controlId,
            value: value,
        };
        const message: ModuleEventMessage = {
            id: 0,
            module: 'control',
            type: 'event',
            src: id,
            payload,
        };
        onInteraction(message);
    }, [id, onInteraction, inputValues]);

    // Handle Enter key press for text inputs
    const handleInputKeyDown = (event: React.KeyboardEvent<HTMLInputElement>, controlId: string) => {
        if (event.key === 'Enter') {
            handleTextSubmit(controlId);
        }
    };

    // Helper to generate CSS class based on control type
    const getControlTypeClass = (type: string): string => {
        return type.replace(/([A-Z])/g, '-$1').toLowerCase();
    }

    return (
        <div className="controls-wrapper">
            {controls.size === 0 ? (
                <p className="no-controls-message">No controls added yet.</p>
            ) : (
                Array.from(controls.values()).map((control) => (
                    <div key={control.id} className={`control-item control-type-${getControlTypeClass(control.type)}`}>
                        {control.type === 'button' && (
                            <button
                                onClick={() => handleButtonClick(control.id)}
                                className="control-button"
                            >
                                {control.config?.text || control.id}
                            </button>
                        )}
                        {control.type === 'textInput' && (
                            <div className="control-text-input-group">
                                <input
                                    key={control.id} // Ensure re-mount if ID changes
                                    type="text"
                                    // Use value to make it a controlled component
                                    value={inputValues[control.id] || ''}
                                    onChange={(e) => handleInputChange(control.id, e.target.value)}
                                    onKeyDown={(e) => handleInputKeyDown(e, control.id)}
                                    placeholder={control.config?.placeholder || ''}
                                    className="control-text-input"
                                    aria-label={`Input for ${control.id}`}
                                />
                                <button
                                    onClick={() => handleTextSubmit(control.id)}
                                    className="control-text-submit-button"
                                >
                                    {control.config?.buttonText || 'Submit'}
                                </button>
                            </div>
                        )}
                    </div>
                ))
            )}
        </div>
    );
};

export default ControlComponent;