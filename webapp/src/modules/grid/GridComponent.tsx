// Sidekick/webapp/src/modules/grid/GridComponent.tsx
import React from 'react';
import { GridState, GridEventPayload } from './types';
import { SentMessage, ModuleEventMessage } from '../../types';
import './GridComponent.css';

interface GridComponentProps {
    id: string; // Instance ID
    state: GridState;
    onInteraction?: (message: SentMessage) => void;
}

const GridComponent: React.FC<GridComponentProps> = ({ id, state, onInteraction }) => {
    // Read numColumns and numRows directly from state
    const { numColumns, numRows, cells } = state;

    const handleCellClick = (x: number, y: number) => {
        if (onInteraction) {
            const payload: GridEventPayload = {
                event: 'click',
                x,
                y,
            };
            const message: ModuleEventMessage = {
                id: 0,
                module: 'grid',
                type: 'event',
                src: id,
                payload: payload,
            };
            onInteraction(message);
        } else {
            console.warn(`GridComponent ${id}: onInteraction not provided, cannot send click event.`);
        }
    };

    const renderGrid = () => {
        const rows = [];
        for (let y = 0; y < numRows; y++) {
            const rowCells = [];
            for (let x = 0; x < numColumns; x++) {
                const key = `${x},${y}`;
                const cellData = cells[key];
                const style: React.CSSProperties = {
                    backgroundColor: cellData?.color || 'white',
                };
                rowCells.push(
                    <div
                        key={key}
                        className="grid-cell"
                        style={style}
                        onClick={() => handleCellClick(x, y)}
                        role="gridcell"
                        aria-label={`Cell (${x}, ${y})`}
                    >
                        {cellData?.text || ''}
                    </div>
                );
            }
            rows.push(<div key={`row-${y}`} className="grid-row">{rowCells}</div>);
        }
        return rows;
    };

    return (
        <div className="grid-canvas" role="grid" aria-colcount={numColumns} aria-rowcount={numRows}>
            {renderGrid()}
        </div>
    );
};

export default GridComponent;