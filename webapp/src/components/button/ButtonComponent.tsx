import React, { useCallback, forwardRef } from 'react';
import { ButtonState, ButtonClickEvent } from './types';
import { SentMessage, ComponentHandle } from '../../types';
import './ButtonComponent.css';

interface ButtonComponentProps {
    id: string;
    state: ButtonState;
    onInteraction?: (message: SentMessage) => void;
}

const ButtonComponent = forwardRef<ComponentHandle | null, ButtonComponentProps>(
    ({ id, state, onInteraction }, ref) => {
        const { text } = state;

        const handleClick = useCallback(() => {
            if (onInteraction) {
                const eventMessage: ButtonClickEvent = {
                    id: 0, // Message ID, can be 0 or managed if needed
                    component: 'button',
                    type: 'event',
                    src: id,
                    payload: { event: 'click' },
                };
                onInteraction(eventMessage);
            }
        }, [id, onInteraction]);

        return (
            <button className="button-component" onClick={handleClick} title={text}>
                {text}
            </button>
        );
    }
);
ButtonComponent.displayName = 'ButtonComponent';
export default ButtonComponent;