// Sidekick/webapp/src/modules/grid/GridComponent.tsx
import React from 'react';
import { GridState, GridNotifyPayload } from './types'; // Import GridNotifyPayload
import { SentMessage, ModuleNotifyMessage } from '../../types';
import './GridComponent.css';

interface GridComponentProps {
    id: string; // Instance ID
    state: GridState;
    onInteraction: (message: SentMessage) => void; // Callback to send message back
}

const GridComponent: React.FC<GridComponentProps> = ({ id, state, onInteraction }) => {
    // Read numColumns and numRows directly from state
    const { numColumns, numRows, cells } = state;

    const handleCellClick = (x: number, y: number) => {
        // Define the payload according to GridNotifyPayload
        const payload: GridNotifyPayload = {
            event: 'click',
            x,
            y,
        };
        // Create the message structure
        const message: ModuleNotifyMessage = {
            id: 0, // or generate unique id if needed
            module: 'grid',
            method: 'notify',
            src: id, // The ID of this grid instance
            payload: payload, // Use the typed payload
        };
        onInteraction(message);
    };

    const renderGrid = () => {
        const rows = [];
        // Use numRows for the outer loop
        for (let y = 0; y < numRows; y++) {
            const rowCells = [];
            // Use numColumns for the inner loop
            for (let x = 0; x < numColumns; x++) {
                const key = `${x},${y}`;
                const cellData = cells[key];
                const style: React.CSSProperties = {
                    backgroundColor: cellData?.color || 'white', // Default background
                };
                rowCells.push(
                    <div
                        key={key}
                        className="grid-cell"
                        style={style}
                        onClick={() => handleCellClick(x, y)} // Add click handler
                        role="gridcell" // Add ARIA role
                        aria-label={`Cell (${x}, ${y})`} // Add ARIA label
                    >
                        {cellData?.text || ''} {/* Display text if available */}
                    </div>
                );
            }
            rows.push(<div key={`row-${y}`} className="grid-row">{rowCells}</div>);
        }
        return rows;
    };

    // Add ARIA roles for accessibility
    return (
        <div className="grid-canvas" role="grid" aria-colcount={numColumns} aria-rowcount={numRows}>
            {renderGrid()}
        </div>
    );
};

export default GridComponent;