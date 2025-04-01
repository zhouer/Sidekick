// Sidekick/webapp/src/components/GridModule.tsx
import React from 'react';
import { GridState } from './types';
import { SidekickMessage } from '../../types';
import './GridModule.css'; // 建立對應的 CSS

interface GridModuleProps {
    id: string; // Instance ID
    state: GridState;
    onInteraction: (message: SidekickMessage) => void; // Callback to send message back
}

const GridModule: React.FC<GridModuleProps> = ({ id, state, onInteraction }) => {
    const { size, cells } = state;
    const [width, height] = size;

    const handleCellClick = (x: number, y: number) => {
        const message: SidekickMessage = {
            id: 0, // or generate unique id if needed
            module: 'grid',
            method: 'notify',
            src: id, // The ID of this grid instance
            payload: {
                x,
                y,
                event: 'click',
            },
        };
        onInteraction(message);
    };

    const renderGrid = () => {
        const rows = [];
        for (let y = 0; y < height; y++) {
            const rowCells = [];
            for (let x = 0; x < width; x++) {
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
                    >
                        {cellData?.text || ''} {/* Display text if available */}
                    </div>
                );
            }
            rows.push(<div key={`row-${y}`} className="grid-row">{rowCells}</div>);
        }
        return rows;
    };

    return (
        <div className="grid-module-container">
            <h3>Grid: {id} ({width}x{height})</h3>
            <div className="grid-canvas">
                {renderGrid()}
            </div>
        </div>
    );
};

export default GridModule;