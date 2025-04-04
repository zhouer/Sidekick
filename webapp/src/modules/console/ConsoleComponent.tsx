// Sidekick/webapp/src/modules/console/ConsoleComponent.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ConsoleState, ConsoleNotifyPayload } from './types';
import { SentMessage, ModuleNotifyMessage } from '../../types';
import './ConsoleComponent.css';

interface ConsoleComponentProps {
    id: string;
    state: ConsoleState;
    onInteraction: (message: SentMessage) => void;
}

const ConsoleComponent: React.FC<ConsoleComponentProps> = ({ id, state, onInteraction }) => {
    const { lines } = state;
    const outputRef = useRef<HTMLDivElement>(null);
    const [inputValue, setInputValue] = useState('');

    useEffect(() => {
        const outputDiv = outputRef.current;
        if (outputDiv) {
            // Set scrollTop to the total scrollable height to scroll to bottom
            outputDiv.scrollTop = outputDiv.scrollHeight;
        }
    }, [lines]); // Trigger only when lines change

    const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        setInputValue(event.target.value);
    };

    const sendInput = useCallback(() => {
        if (!inputValue.trim()) return;
        const payload: ConsoleNotifyPayload = { event: 'submit', value: inputValue };
        const message: ModuleNotifyMessage = { id: 0, module: 'console', method: 'notify', src: id, payload: payload };
        onInteraction(message);
        setInputValue('');
    }, [inputValue, id, onInteraction]);

    const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
        if (event.key === 'Enter') {
            sendInput();
        }
    };

    return (
        <div>
            {/* Output Area - Add the ref here */}
            <div className="console-output" ref={outputRef}> {/* <-- Assign ref */}
                {lines.map((line, index) => (
                    <div key={index} className="console-line">
                        {line.split('\n').map((part, partIndex) => (
                            <React.Fragment key={partIndex}>
                                {partIndex > 0 && <br />}
                                {part}
                            </React.Fragment>
                        ))}
                    </div>
                ))}
            </div>
            {/* Input Area (no changes needed here) */}
            <div className="console-input-area">
                <input
                    type="text"
                    value={inputValue}
                    onChange={handleInputChange}
                    onKeyDown={handleKeyDown}
                    placeholder="Enter command or text..."
                    className="console-input"
                />
                <button onClick={sendInput} className="console-send-button">
                    Send
                </button>
            </div>
        </div>
    );
};

export default ConsoleComponent;