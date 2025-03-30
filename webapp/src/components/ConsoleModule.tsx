// Sidekick/webapp/src/components/ConsoleModule.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ConsoleState, SidekickMessage, ConsoleNotifyPayload } from '../types'; // Import necessary types
import './ConsoleModule.css';

interface ConsoleModuleProps {
    id: string; // Instance ID
    state: ConsoleState;
    // Add callback for sending messages back to Hero
    onInteraction: (message: SidekickMessage) => void;
}

const ConsoleModule: React.FC<ConsoleModuleProps> = ({ id, state, onInteraction }) => {
    const { lines } = state;
    const consoleEndRef = useRef<HTMLDivElement>(null); // Ref for scrolling output
    const [inputValue, setInputValue] = useState(''); // State for the input field

    // Auto-scroll output to bottom when lines change
    useEffect(() => {
        consoleEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [lines]);

    // Handle input change
    const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        setInputValue(event.target.value);
    };

    // Handle sending the input value
    const sendInput = useCallback(() => {
        if (!inputValue.trim()) return; // Don't send empty input

        const payload: ConsoleNotifyPayload = {
            event: 'submit',
            value: inputValue
        };

        const message: SidekickMessage = {
            id: 0, // Or generate unique id if needed
            module: 'console',
            method: 'notify',
            src: id, // The ID of this console instance
            payload: payload,
        };
        onInteraction(message); // Send message via the callback prop
        setInputValue(''); // Clear the input field
    }, [inputValue, id, onInteraction]);

    // Handle Enter key press in input field
    const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
        if (event.key === 'Enter') {
            sendInput();
        }
    };

    return (
        <div className="console-module-container">
            <h3>Console: {id}</h3>
            {/* Output Area */}
            <div className="console-output">
                {lines.map((line, index) => (
                    <div key={index} className="console-line">
                        {/* Render line breaks correctly */}
                        {line.split('\n').map((part, partIndex) => (
                            <React.Fragment key={partIndex}>
                                {partIndex > 0 && <br />}
                                {part}
                            </React.Fragment>
                        ))}
                    </div>
                ))}
                {/* Empty div to mark the end for scrolling */}
                <div ref={consoleEndRef} />
            </div>
            {/* Input Area */}
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

export default ConsoleModule;