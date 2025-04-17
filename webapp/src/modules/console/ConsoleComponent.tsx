// Sidekick/webapp/src/modules/console/ConsoleComponent.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ConsoleState, ConsoleEventPayload } from './types';
import { SentMessage, ModuleEventMessage } from '../../types';
import './ConsoleComponent.css';

interface ConsoleComponentProps {
    id: string;
    state: ConsoleState;
    onInteraction?: (message: SentMessage) => void;
}

const ConsoleComponent: React.FC<ConsoleComponentProps> = ({ id, state, onInteraction }) => {
    const { lines, showInput } = state;
    const outputRef = useRef<HTMLDivElement>(null);
    const [inputValue, setInputValue] = useState('');

    useEffect(() => {
        const outputDiv = outputRef.current;
        if (outputDiv) {
            outputDiv.scrollTop = outputDiv.scrollHeight;
        }
    }, [lines]);

    const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        setInputValue(event.target.value);
    };

    const sendInput = useCallback(() => {
        if (!onInteraction) {
            console.warn(`ConsoleComponent ${id}: onInteraction not provided, cannot send input.`);
            return;
        }
        if (!inputValue.trim()) return;

        const payload: ConsoleEventPayload = { event: 'inputText', value: inputValue };
        const message: ModuleEventMessage = {
            id: 0,
            module: 'console',
            type: 'event',
            src: id,
            payload: payload
        };
        onInteraction(message);
        setInputValue('');
    }, [inputValue, id, onInteraction]);

    const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
        if (event.key === 'Enter') {
            sendInput();
        }
    };

    return (
        <div className="console-container">
            <div className="console-output" ref={outputRef}>
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

            {showInput && (
                <div className="console-input-area">
                    <input
                        type="text"
                        value={inputValue}
                        onChange={handleInputChange}
                        onKeyDown={handleKeyDown}
                        placeholder="Enter command or text..."
                        className="console-input"
                        aria-label="Console Input"
                    />
                    <button onClick={sendInput} className="console-send-button">
                        Send
                    </button>
                </div>
            )}
        </div>
    );
};

export default ConsoleComponent;