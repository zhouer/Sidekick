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
    // --- CHANGE: Track the ID of the last successfully processed command ---
    const lastProcessedCommandId = useRef<string | number | null>(null);
    // Ref to track if the initial clear based on background has happened
    const initialBgApplied = useRef(false);

    // Destructure state for dependencies
    const { width, height, bgColor, commandQueue } = state;

    // --- Effect 1: Get context and perform initial clear/setup ---
    useEffect(() => {
        // Reset initial background flag when fundamental props change
        initialBgApplied.current = false;
        lastProcessedCommandId.current = null; // Reset processed commands on resize/remount

        if (canvasRef.current) {
            console.log(`Canvas ${id}: Getting context (Size: ${width}x${height}, BG: ${bgColor})`);
            const context = canvasRef.current.getContext('2d');
            if (context) {
                setCtx(context); // Store context in state
                console.log(`Canvas ${id}: Context obtained.`);
                // Initial clear with background color - only if not done before
                if (!initialBgApplied.current) {
                    context.fillStyle = bgColor || '#FFFFFF';
                    context.fillRect(0, 0, width, height);
                    initialBgApplied.current = true;
                    console.log(`Canvas ${id}: Initial background applied.`);
                }
            } else {
                console.error(`Canvas ${id}: Failed to get 2D context.`);
                setCtx(null);
            }
        } else {
            setCtx(null); // Ensure context is null if canvas ref is not available
        }
        // This effect handles the fundamental setup based on these props
    }, [id, width, height, bgColor]); // Depend on props that require re-initialization

    // --- Effect 2: Process Drawing Commands from Props Queue ---
    useEffect(() => {
        // --- Guard Clauses ---
        // 1. Ensure context is available
        if (!ctx) {
            // console.log(`Canvas ${id}: Skipping draw - no context`);
            return;
        }
        // 2. Ensure there are commands in the queue from props
        if (!commandQueue || commandQueue.length === 0) {
            // console.log(`Canvas ${id}: Skipping draw - empty command queue`);
            return;
        }

        // --- Find the starting point for processing ---
        let startIndex = 0;
        // If we have processed commands before, find the index *after* the last processed one
        if (lastProcessedCommandId.current !== null) {
            startIndex = commandQueue.findIndex(cmd => cmd.commandId === lastProcessedCommandId.current);
            if (startIndex !== -1) {
                startIndex += 1; // Start processing from the *next* command
            } else {
                // Last processed ID not found (maybe queue was cleared/reset?), process from beginning
                console.warn(`Canvas ${id}: Last processed command ID ${lastProcessedCommandId.current} not found in queue. Processing all.`);
                startIndex = 0;
            }
        }

        // --- Check if there are actually new commands to process ---
        if (startIndex >= commandQueue.length) {
            // console.log(`Canvas ${id}: No new commands to process after index ${startIndex - 1}`);
            return;
        }

        console.log(`Canvas ${id}: Processing commands from index ${startIndex} (${commandQueue.length - startIndex} new)`);

        // --- Synchronous Processing Loop (for commands in this update batch) ---
        // We iterate directly over the relevant slice of the props queue.
        // This avoids issues with local state synchronization lag.
        let currentCommandId: string | number | null = lastProcessedCommandId.current;
        for (let i = startIndex; i < commandQueue.length; i++) {
            const command = commandQueue[i];
            if (!command || !command.commandId) {
                console.warn(`Canvas ${id}: Skipping invalid command at index ${i}:`, command);
                continue; // Skip invalid commands
            }

            // Double-check (though unlikely with findIndex logic) to prevent reprocessing
            if (command.commandId === lastProcessedCommandId.current) {
                console.warn(`Canvas ${id}: Attempted to reprocess command ID ${command.commandId}. Skipping.`);
                continue;
            }

            console.log(`Canvas ${id}: Executing command ${command.commandId}`, command);
            const { command: commandName, options } = command;

            try {
                // --- Drawing Logic (same as before) ---
                switch (commandName) {
                    case 'clear': ctx.fillStyle = options.color || bgColor || '#FFFFFF'; ctx.fillRect(0, 0, width, height); break;
                    case 'config': if (options.strokeStyle !== undefined) ctx.strokeStyle = options.strokeStyle; if (options.fillStyle !== undefined) ctx.fillStyle = options.fillStyle; if (options.lineWidth !== undefined) ctx.lineWidth = options.lineWidth; break;
                    case 'line': ctx.beginPath(); ctx.moveTo(options.x1, options.y1); ctx.lineTo(options.x2, options.y2); ctx.stroke(); break;
                    case 'rect': if (options.filled) { ctx.fillRect(options.x, options.y, options.width, options.height); } else { ctx.strokeRect(options.x, options.y, options.width, options.height); } break;
                    case 'circle': ctx.beginPath(); ctx.arc(options.cx, options.cy, options.radius, 0, Math.PI * 2); if (options.filled) { ctx.fill(); } else { ctx.stroke(); } break;
                    default: console.warn(`Canvas ${id}: Unknown draw command "${commandName}"`);
                }
                // --- Update last processed ID *after successful execution* ---
                currentCommandId = command.commandId;

            } catch (error) {
                console.error(`Canvas ${id}: Error executing command ${command.commandId}:`, commandName, options, error);
                // --- Error Handling: Stop processing this batch on error ---
                console.log(`Canvas ${id}: Stopping processing this batch due to error.`);
                // Update ref to the last *successfully* processed command before the error
                lastProcessedCommandId.current = currentCommandId;
                // Exit the loop for this render cycle
                return;
            }
        } // End of loop

        // --- Update the ref *after* the loop completes successfully ---
        lastProcessedCommandId.current = currentCommandId;
        console.log(`Canvas ${id}: Finished processing batch. Last processed ID: ${lastProcessedCommandId.current}`);

        // Dependencies: Re-run this effect if context changes OR the command queue prop changes.
    }, [ctx, commandQueue, id, width, height, bgColor]); // Include all variables used inside

    // Render the canvas element
    return (
        <div className="canvas-module-container">
            <h3>Canvas: {id}</h3>
            <canvas
                ref={canvasRef}
                width={width}
                height={height}
                className="canvas-element"
                style={{ backgroundColor: bgColor }}
            >
                Your browser does not support the canvas element.
            </canvas>
        </div>
    );
};

export default CanvasModule;