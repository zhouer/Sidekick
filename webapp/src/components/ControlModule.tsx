// Sidekick/webapp/src/components/ControlModule.tsx
import React, { useState, useCallback } from 'react';
import { ControlState, SidekickMessage, ControlNotifyPayload } from '../types';
import './ControlModule.css'; // Create this CSS file

interface ControlModuleProps {
    id: string; // Instance ID of the Control module
    state: ControlState;
    onInteraction: (message: SidekickMessage) => void; // Callback to send notifications
}

const ControlModule: React.FC<ControlModuleProps> = ({ id, state, onInteraction }) => {
    const { controls } = state;

    // Local state to manage the current value of each text input
    // Keyed by the control_id of the text input
    const [inputValues, setInputValues] = useState<Record<string, string>>(() => {
        // Initialize input values from control definitions if provided
        const initial: Record<string, string> = {};
        controls.forEach(control => {
            if (control.type === 'text_input') {
                initial[control.id] = control.config?.initial_value || '';
            }
        });
        return initial;
    });

    // Update local input state if initial_value changes via props (less common)
    React.useEffect(() => {
        const updatedInitial: Record<string, string> = {};
        let changed = false;
        controls.forEach(control => {
            if (control.type === 'text_input') {
                const initialValue = control.config?.initial_value || '';
                // Only update if the prop value differs from current local state
                if (inputValues[control.id] !== initialValue) {
                    updatedInitial[control.id] = initialValue;
                    changed = true;
                } else {
                    updatedInitial[control.id] = inputValues[control.id]; // Keep current if same
                }
            }
        });
        // Only set state if there was actually a change from props
        if (changed) {
            setInputValues(prev => ({ ...prev, ...updatedInitial }));
        }
        // Note: This effect might overwrite user input if initial_value changes frequently from Hero.
        // Consider if this behavior is desired. Usually, initial_value is set once.
    }, [controls]); // Rerun when controls definition changes

    // Handler for text input changes
    const handleInputChange = (controlId: string, value: string) => {
        setInputValues(prev => ({
            ...prev,
            [controlId]: value,
        }));
    };

    // Handler for button clicks
    const handleButtonClick = useCallback((controlId: string) => {
        console.log(`Control ${id}: Button ${controlId} clicked.`);
        const payload: ControlNotifyPayload = {
            event: 'click',
            control_id: controlId,
        };
        const message: SidekickMessage = { id: 0, module: 'control', method: 'notify', src: id, payload };
        onInteraction(message);
    }, [id, onInteraction]);

    // Handler for submitting text input value
    const handleTextSubmit = useCallback((controlId: string) => {
        const value = inputValues[controlId] || ''; // Get current value from local state
        console.log(`Control ${id}: Input ${controlId} submitted with value: "${value}"`);
        const payload: ControlNotifyPayload = {
            event: 'submit',
            control_id: controlId,
            value: value,
        };
        const message: SidekickMessage = { id: 0, module: 'control', method: 'notify', src: id, payload };
        onInteraction(message);
        // Optionally clear the input after submission:
        // setInputValues(prev => ({ ...prev, [controlId]: '' }));
    }, [id, onInteraction, inputValues]);

    // Handle Enter key press for text inputs
    const handleInputKeyDown = (event: React.KeyboardEvent<HTMLInputElement>, controlId: string) => {
        if (event.key === 'Enter') {
            handleTextSubmit(controlId);
        }
    };

    return (
        <div className="control-module-container">
            <h3>Controls: {id}</h3>
            <div className="controls-wrapper">
                {/* Check if there are any controls */}
                {controls.size === 0 ? (
                    <p className="no-controls-message">No controls added yet.</p>
                ) : (
                    // Convert Map values to array and render each control
                    Array.from(controls.values()).map((control) => (
                        <div key={control.id} className={`control-item control-type-${control.type}`}>
                            {/* Render button */}
                            {control.type === 'button' && (
                                <button
                                    onClick={() => handleButtonClick(control.id)}
                                    className="control-button"
                                >
                                    {control.config?.text || control.id} {/* Fallback to ID if text missing */}
                                </button>
                            )}
                            {/* Render text input with its submit button */}
                            {control.type === 'text_input' && (
                                <div className="control-text-input-group">
                                    <input
                                        type="text"
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
                                        {control.config?.button_text || 'Submit'}
                                    </button>
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};

export default ControlModule;