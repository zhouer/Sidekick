// Sidekick/webapp/src/components/CanvasModule.tsx
import React, { useRef, useEffect } from 'react';
import { CanvasState, CanvasDrawCommand } from '../types'; // Import relevant types
import './CanvasModule.css'; // Create this CSS file

interface CanvasModuleProps {
    id: string; // Instance ID
    state: CanvasState;
    // No interaction back to Hero needed for basic drawing MVP
}

// Helper to draw based on command
const executeDrawCommand = (
    ctx: CanvasRenderingContext2D | null,
    command: CanvasDrawCommand | null,
    initialBgColor: string
) => {
    if (!ctx || !command) return;

    const { command: cmd, options } = command;

    try { // Wrap drawing in try/catch
        switch (cmd) {
            case 'clear':
                ctx.fillStyle = options?.color || initialBgColor || '#FFFFFF'; // Use specified, initial, or white
                ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
                break;

            case 'config':
                if (options?.strokeStyle !== undefined) ctx.strokeStyle = options.strokeStyle;
                if (options?.fillStyle !== undefined) ctx.fillStyle = options.fillStyle;
                if (options?.lineWidth !== undefined) ctx.lineWidth = options.lineWidth;
                break;

            case 'line':
                if (options.x1 === undefined || options.y1 === undefined || options.x2 === undefined || options.y2 === undefined) break;
                ctx.beginPath();
                ctx.moveTo(options.x1, options.y1);
                ctx.lineTo(options.x2, options.y2);
                ctx.stroke();
                break;

            case 'rect':
                if (options.x === undefined || options.y === undefined || options.width === undefined || options.height === undefined) break;
                if (options.filled) {
                    ctx.fillRect(options.x, options.y, options.width, options.height);
                } else {
                    ctx.strokeRect(options.x, options.y, options.width, options.height);
                }
                break;

            case 'circle':
                if (options.cx === undefined || options.cy === undefined || options.radius === undefined) break;
                ctx.beginPath();
                ctx.arc(options.cx, options.cy, options.radius, 0, Math.PI * 2);
                if (options.filled) {
                    ctx.fill();
                } else {
                    ctx.stroke();
                }
                break;

            default:
                console.warn(`CanvasModule: Unknown draw command "${cmd}"`);
        }
    } catch (error) {
        console.error(`CanvasModule: Error executing command "${cmd}":`, error, options);
    }
};

const CanvasModule: React.FC<CanvasModuleProps> = ({ id, state }) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const contextRef = useRef<CanvasRenderingContext2D | null>(null); // Store context
    const { width, height, bgColor, lastCommand } = state || { width: 100, height: 100, bgColor: '#FFFFFF', lastCommand: null };

    // Initialize canvas and context, clear on size/bgColor change
    useEffect(() => {
        if (canvasRef.current) {
            contextRef.current = canvasRef.current.getContext('2d');
            if (contextRef.current) {
                // Clear to background color when dimensions or initial bg change
                contextRef.current.fillStyle = bgColor || '#FFFFFF';
                contextRef.current.fillRect(0, 0, width, height);
                console.log(`Canvas ${id} initialized/reset to ${width}x${height}`);
            } else {
                console.error(`CanvasModule ${id}: Failed to get 2D context.`);
            }
        }
    }, [width, height, bgColor, id]); // Rerun if size or bg changes

    // Execute drawing command when lastCommand changes
    useEffect(() => {
        if (contextRef.current && lastCommand) {
            // console.log(`Canvas ${id} executing:`, lastCommand.command, lastCommand.options);
            executeDrawCommand(contextRef.current, lastCommand, bgColor);
        }
        // Only re-run when lastCommand changes identity
    }, [lastCommand, bgColor, id]); // Include bgColor for clear command fallback

    return (
        <div className="canvas-module-container">
            <h3>Canvas: {id}</h3>
            <canvas
                ref={canvasRef}
                width={width}
                height={height}
                className="canvas-element"
            />
        </div>
    );
};

export default CanvasModule;