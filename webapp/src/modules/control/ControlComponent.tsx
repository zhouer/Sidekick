// Sidekick/webapp/src/modules/control/ControlComponent.tsx
import React, { useState, useCallback, useEffect } from 'react';
import { ControlState, ControlNotifyPayload } from './types';
import { SentMessage, ModuleNotifyMessage } from '../../types';
import './ControlComponent.css';

interface ControlComponentProps {
    id: string;
    state: ControlState;
    onInteraction: (message: SentMessage) => void;
}

const ControlComponent: React.FC<ControlComponentProps> = ({ id, state, onInteraction }) => {
    const { controls } = state;

    // Local state to manage the current value of each text input
    const [inputValues, setInputValues] = useState<Record<string, string>>(() => {
        const initial: Record<string, string> = {};
        controls.forEach(control => {
            if (control.type === 'textInput') {
                initial[control.id] = control.config?.initialValue || '';
            }
        });
        return initial;
    });

    // Effect to synchronize local state with potentially updated initialValue from props
    useEffect(() => {
        setInputValues(prevInputValues => {
            const nextInputValues: Record<string, string> = { ...prevInputValues };
            let changed = false;
            controls.forEach(control => {
                if (control.type === 'textInput') {
                    const initialValueProp = control.config?.initialValue || '';
                    if (nextInputValues[control.id] === undefined || nextInputValues[control.id] !== initialValueProp) {
                        nextInputValues[control.id] = initialValueProp;
                        changed = true;
                    }
                }
            });
            Object.keys(nextInputValues).forEach(controlId => {
                if (!controls.has(controlId)) {
                    delete nextInputValues[controlId];
                    changed = true;
                }
            });
            return changed ? nextInputValues : prevInputValues;
        });
    }, [controls]);


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
            controlId: controlId,
        };
        const message: ModuleNotifyMessage = { id: 0, module: 'control', method: 'notify', src: id, payload };
        onInteraction(message);
    }, [id, onInteraction]);

    // Handler for submitting text input value
    const handleTextSubmit = useCallback((controlId: string) => {
        const value = inputValues[controlId] || '';
        console.log(`Control ${id}: Input ${controlId} submitted with value: "${value}"`);
        const payload: ControlNotifyPayload = {
            event: 'submit',
            controlId: controlId,
            value: value,
        };
        const message: ModuleNotifyMessage = { id: 0, module: 'control', method: 'notify', src: id, payload };
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
        // Convert type ("button", "textInput") to CSS-friendly class ("button", "text-input")
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