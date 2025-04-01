// Sidekick/webapp/src/components/CanvasModule.tsx
import React, { useRef, useEffect, useState } from 'react';
import { CanvasState } from '../types';
import './CanvasModule.css';

interface CanvasModuleProps {
    id: string;
    state: CanvasState;
}

const CanvasModule: React.FC<CanvasModuleProps> = ({ id, state }) => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const [ctx, setCtx] = useState<CanvasRenderingContext2D | null>(null);
    const lastProcessedCommandId = useRef<string | number | null>(null);
    const initialBgApplied = useRef(false);

    const { width, height, bgColor, commandQueue } = state;

    // Effect 1: Get context and perform initial clear/setup
    useEffect(() => {
        initialBgApplied.current = false;
        lastProcessedCommandId.current = null;
        if (canvasRef.current) {
            console.log(`Canvas ${id}: Getting context (Size: ${width}x${height}, BG: ${bgColor})`);
            const context = canvasRef.current.getContext('2d');
            if (context) {
                setCtx(context);
                console.log(`Canvas ${id}: Context obtained.`);
                context.fillStyle = bgColor || '#FFFFFF';
                context.fillRect(0, 0, width, height);
                initialBgApplied.current = true;
                console.log(`Canvas ${id}: Initial background applied.`);
            } else {
                console.error(`Canvas ${id}: Failed to get 2D context.`); setCtx(null);
            }
        } else { setCtx(null); }
    }, [id, width, height, bgColor]);

    // Effect 2: Process Drawing Commands from Props Queue
    useEffect(() => {
        if (!ctx) return;
        if (!commandQueue || commandQueue.length === 0) return;

        let startIndex = 0;
        if (lastProcessedCommandId.current !== null) {
            startIndex = commandQueue.findIndex(cmd => cmd.commandId === lastProcessedCommandId.current);
            if (startIndex !== -1) { startIndex += 1; }
            else { console.warn(`Canvas ${id}: Last processed ID ${lastProcessedCommandId.current} not found. Processing all.`); startIndex = 0; }
        }
        if (startIndex >= commandQueue.length) return;

        console.log(`Canvas ${id}: Processing commands from index ${startIndex} (${commandQueue.length - startIndex} new)`);
        let currentCommandId: string | number | null = lastProcessedCommandId.current;

        for (let i = startIndex; i < commandQueue.length; i++) {
            const commandPayload = commandQueue[i]; // Item in queue IS the payload
            if (!commandPayload || !commandPayload.commandId || !commandPayload.action) { console.warn(`Canvas ${id}: Skipping invalid command payload at index ${i}:`, commandPayload); continue; }
            const { action, options, commandId } = commandPayload;
            if (commandId === lastProcessedCommandId.current) { continue; }

            console.log(`Canvas ${id}: Executing ${action} (ID: ${commandId})`, options);
            try {
                switch (action) {
                    case 'clear': ctx.fillStyle = options.color || bgColor || '#FFFFFF'; ctx.fillRect(0, 0, width, height); break;
                    case 'config': if (options.strokeStyle !== undefined) ctx.strokeStyle = options.strokeStyle; if (options.fillStyle !== undefined) ctx.fillStyle = options.fillStyle; if (options.lineWidth !== undefined) ctx.lineWidth = options.lineWidth; break;
                    case 'line': if (options.x1 === undefined || options.y1 === undefined || options.x2 === undefined || options.y2 === undefined) throw new Error("Missing coords for line"); ctx.beginPath(); ctx.moveTo(options.x1, options.y1); ctx.lineTo(options.x2, options.y2); ctx.stroke(); break;
                    case 'rect': if (options.x === undefined || options.y === undefined || options.width === undefined || options.height === undefined) throw new Error("Missing params for rect"); if (options.filled) { ctx.fillRect(options.x, options.y, options.width, options.height); } else { ctx.strokeRect(options.x, options.y, options.width, options.height); } break;
                    case 'circle': if (options.cx === undefined || options.cy === undefined || options.radius === undefined) throw new Error("Missing params for circle"); ctx.beginPath(); ctx.arc(options.cx, options.cy, options.radius, 0, Math.PI * 2); if (options.filled) { ctx.fill(); } else { ctx.stroke(); } break;
                    default: console.warn(`Canvas ${id}: Unknown draw action "${action}"`);
                }
                currentCommandId = commandId; // Success
            } catch (error) {
                console.error(`Canvas ${id}: Error executing command ${commandId} (${action}):`, options, error);
                console.log(`Canvas ${id}: Stopping processing batch due to error.`);
                lastProcessedCommandId.current = currentCommandId;
                return;
            }
        }
        lastProcessedCommandId.current = currentCommandId;
        console.log(`Canvas ${id}: Finished processing batch. Last processed ID: ${lastProcessedCommandId.current}`);
    }, [ctx, commandQueue, id, width, height, bgColor]);

    return (
        <div className="canvas-module-container">
            <h3>Canvas: {id}</h3>
            <canvas ref={canvasRef} width={width} height={height} className="canvas-element" style={{ backgroundColor: bgColor || '#FFFFFF' }}>
                Your browser does not support the canvas element.
            </canvas>
        </div>
    );
};

export default CanvasModule;