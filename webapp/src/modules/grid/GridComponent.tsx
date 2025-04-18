// Sidekick/webapp/src/modules/grid/GridComponent.tsx
import React, { useState, useRef, useLayoutEffect, useEffect, useCallback } from 'react';
import { GridState, GridEventPayload } from './types';
import { SentMessage, ModuleEventMessage } from '../../types';
import './GridComponent.css';

// --- Constants ---
const DESIRED_CELL_SIZE = 50; // px
const MIN_CELL_SIZE = 10; // px (prevent extremely small cells)
const GRID_GAP = 1; // px (must match CSS gap value)
const CANVAS_PADDING = 1; // px (must match CSS padding for canvas)
const MIN_FONT_SIZE = 10; // px

// --- Helper Component for Cell Content & Font Sizing ---
interface GridCellContentProps {
    text: string | null | undefined;
    cellSize: number;
}

const GridCellContent: React.FC<GridCellContentProps> = React.memo(({ text, cellSize }) => {
    const textRef = useRef<HTMLSpanElement>(null);
    const [fontSize, setFontSize] = useState(MIN_FONT_SIZE);

    useLayoutEffect(() => {
        if (!text || !textRef.current || cellSize <= 0) {
            setFontSize(MIN_FONT_SIZE); // Reset if no text or invalid cell size
            return;
        }

        const span = textRef.current;
        let currentFontSize = Math.min(MIN_FONT_SIZE * 2.5, Math.max(MIN_FONT_SIZE, Math.floor(cellSize * 0.7))); // Start reasonably large
        let fits = false;

        // Max iterations to prevent infinite loops in weird edge cases
        let iterations = 0;
        const maxIterations = 30;

        // Binary search or iterative approach to find the best font size
        // Iterative is simpler here:
        while (currentFontSize >= MIN_FONT_SIZE && iterations < maxIterations) {
            iterations++;
            span.style.fontSize = `${currentFontSize}px`;
            // Check if text overflows the available space (consider cell padding)
            const availableWidth = cellSize - 4; // Account for padding (2px left + 2px right)
            const availableHeight = cellSize - 4; // Account for padding (2px top + 2px bottom)

            // Check scrollWidth/scrollHeight against clientWidth/clientHeight or available space
            if (span.scrollWidth <= availableWidth && span.scrollHeight <= availableHeight) {
                fits = true;
                break; // Found a size that fits
            }
            currentFontSize -= 1; // Decrease font size and try again
        }

        // If even min size doesn't fit, use min size (text will be clipped by overflow:hidden)
        setFontSize(Math.max(MIN_FONT_SIZE, currentFontSize));

    }, [text, cellSize]); // Rerun when text or cell size changes

    return (
        <span ref={textRef} className="grid-cell-text" style={{ fontSize: `${fontSize}px` }}>
            {text}
        </span>
    );
});
GridCellContent.displayName = 'GridCellContent'; // For React DevTools

// --- Main Grid Component ---
interface GridComponentProps {
    id: string; // Instance ID
    state: GridState;
    onInteraction?: (message: SentMessage) => void;
}

const GridComponent: React.FC<GridComponentProps> = ({ id, state, onInteraction }) => {
    const { numColumns, numRows, cells } = state;
    const containerRef = useRef<HTMLDivElement>(null);
    const [cellSize, setCellSize] = useState(DESIRED_CELL_SIZE);
    const [containerWidth, setContainerWidth] = useState(0);

    // --- Calculate Cell Size based on Container Width ---
    const calculateCellSize = useCallback((width: number) => {
        if (!width || numColumns <= 0) {
            return DESIRED_CELL_SIZE; // Default if no width or columns
        }
        const totalGapWidth = (numColumns - 1) * GRID_GAP;
        const widthWithoutGaps = width - 2 * CANVAS_PADDING - totalGapWidth;
        // Calculate max size based on width, ensure it's at least MIN_CELL_SIZE
        const maxPossibleWidth = Math.max(MIN_CELL_SIZE, Math.floor(widthWithoutGaps / numColumns));
        // Choose the smaller of desired size and max possible size
        return Math.min(DESIRED_CELL_SIZE, maxPossibleWidth);
    }, [numColumns]);

    // --- Resize Observer ---
    useEffect(() => {
        const element = containerRef.current;
        if (!element) return;

        const observer = new ResizeObserver(entries => {
            // We only observe one element
            if (entries[0]) {
                const newWidth = entries[0].contentRect.width;
                // Update containerWidth state only if it actually changed
                // to prevent potential unnecessary recalculations
                setContainerWidth(prevWidth => {
                    if (Math.abs(prevWidth - newWidth) > 0.5) { // Add tolerance
                        // console.log(`Grid ${id}: Resize detected. New width: ${newWidth}`);
                        return newWidth;
                    }
                    return prevWidth;
                });
            }
        });

        observer.observe(element);

        // Initial measurement
        setContainerWidth(element.clientWidth);
        // console.log(`Grid ${id}: Initial container width: ${element.clientWidth}`);


        return () => {
            observer.unobserve(element);
            // console.log(`Grid ${id}: ResizeObserver disconnected.`);
        };
    }, [id]); // Only needs to run once on mount to set up observer

    // --- Update Cell Size State when Container Width or Columns Change ---
    useEffect(() => {
        const newSize = calculateCellSize(containerWidth);
        if (newSize !== cellSize) {
            // console.log(`Grid ${id}: Calculated new cell size: ${newSize}px (Container: ${containerWidth}px, Cols: ${numColumns})`);
            setCellSize(newSize);
        }
    }, [containerWidth, numColumns, calculateCellSize, cellSize]);


    // --- Handle Cell Click ---
    const handleCellClick = useCallback((x: number, y: number) => {
        if (onInteraction) {
            const payload: GridEventPayload = { event: 'click', x, y };
            const message: ModuleEventMessage = {
                id: 0, module: 'grid', type: 'event', src: id, payload: payload
            };
            onInteraction(message);
        } else {
            console.warn(`GridComponent ${id}: onInteraction not provided, cannot send click event.`);
        }
    }, [id, onInteraction]);

    // --- Render Grid Cells ---
    const renderGridCells = () => {
        const gridCells = [];
        for (let y = 0; y < numRows; y++) {
            for (let x = 0; x < numColumns; x++) {
                const key = `${x},${y}`;
                const cellData = cells[key];
                const cellStyle: React.CSSProperties = {
                    width: `${cellSize}px`,
                    height: `${cellSize}px`,
                    ...(cellData?.color && { backgroundColor: cellData.color }),
                };

                gridCells.push(
                    <div
                        key={key}
                        className="grid-cell"
                        style={cellStyle}
                        onClick={() => handleCellClick(x, y)}
                        role="gridcell"
                        aria-label={`Cell (${x}, ${y})`}
                        title={`Cell (${x}, ${y})${cellData?.text ? ': ' + cellData.text : ''}${cellData?.color ? ' Color: ' + cellData.color : ''}`} // Tooltip
                    >
                        <GridCellContent text={cellData?.text} cellSize={cellSize} />
                    </div>
                );
            }
        }
        return gridCells;
    };

    // --- Grid Container Styles ---
    const gridCanvasStyle: React.CSSProperties = {
        gridTemplateColumns: `repeat(${numColumns}, ${cellSize}px)`,
        // gridTemplateRows is implicit due to square cells + gap
    };

    return (
        <div className="grid-container" ref={containerRef}>
            <div
                className="grid-canvas"
                style={gridCanvasStyle}
                role="grid"
                aria-colcount={numColumns}
                aria-rowcount={numRows}
            >
                {renderGridCells()}
            </div>
        </div>
    );
};

export default GridComponent;