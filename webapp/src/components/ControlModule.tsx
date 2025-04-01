// Sidekick/webapp/src/components/ControlModule.tsx
import React, { useState, useCallback, useEffect } from 'react'; // Import useEffect
import { ControlState, SidekickMessage, ControlNotifyPayload } from '../types';
import './ControlModule.css';

interface ControlModuleProps {
    id: string;
    state: ControlState;
    onInteraction: (message: SidekickMessage) => void;
}

const ControlModule: React.FC<ControlModuleProps> = ({ id, state, onInteraction }) => {
    const { controls } = state;

    // Local state to manage the current value of each text input
    const [inputValues, setInputValues] = useState<Record<string, string>>(() => {
        const initial: Record<string, string> = {};
        controls.forEach(control => {
            if (control.type === 'text_input') {
                // FIX: Use camelCase 'initialValue'
                initial[control.id] = control.config?.initialValue || '';
            }
        });
        return initial;
    });

    // Update local input state if initialValue changes via props
    useEffect(() => { // Changed React.useEffect to useEffect
        const updatedInitial: Record<string, string> = {};
        let changed = false;
        controls.forEach(control => {
            if (control.type === 'text_input') {
                // FIX: Use camelCase 'initialValue'
                const initialValueProp = control.config?.initialValue || '';
                // Update only if prop differs from current state
                if (inputValues[control.id] !== initialValueProp) {
                    updatedInitial[control.id] = initialValueProp;
                    changed = true;
                } else {
                    // Keep existing value if prop hasn't changed relative to it
                    updatedInitial[control.id] = inputValues[control.id];
                }
            }
        });
        if (changed) {
            // Merge updates carefully to not lose other input states
            setInputValues(prev => ({ ...prev, ...updatedInitial }));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [controls]); // Dependency: Re-evaluate when the set of controls changes


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
            // FIX: Use camelCase 'controlId'
            controlId: controlId,
        };
        const message: SidekickMessage = { id: 0, module: 'control', method: 'notify', src: id, payload };
        onInteraction(message);
    }, [id, onInteraction]);

    // Handler for submitting text input value
    const handleTextSubmit = useCallback((controlId: string) => {
        const value = inputValues[controlId] || '';
        console.log(`Control ${id}: Input ${controlId} submitted with value: "${value}"`);
        const payload: ControlNotifyPayload = {
            event: 'submit',
            // FIX: Use camelCase 'controlId'
            controlId: controlId,
            value: value,
        };
        const message: SidekickMessage = { id: 0, module: 'control', method: 'notify', src: id, payload };
        onInteraction(message);
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
                {controls.size === 0 ? (
                    <p className="no-controls-message">No controls added yet.</p>
                ) : (
                    Array.from(controls.values()).map((control) => (
                        <div key={control.id} className={`control-item control-type-${control.type}`}>
                            {control.type === 'button' && (
                                <button
                                    onClick={() => handleButtonClick(control.id)}
                                    className="control-button"
                                >
                                    {control.config?.text || control.id}
                                </button>
                            )}
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
                                        {/* FIX: Use camelCase 'buttonText' */}
                                        {control.config?.buttonText || 'Submit'}
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