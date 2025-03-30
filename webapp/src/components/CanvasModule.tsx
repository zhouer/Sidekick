// Sidekick/webapp/src/components/CanvasModule.tsx
import React, { useRef, useEffect, useState } from 'react';
import { CanvasState, CanvasDrawCommand } from '../types'; // Import necessary types
import './CanvasModule.css'; // Assuming styles exist

// Define props expected by the CanvasModule component
interface CanvasModuleProps {
    id: string; // Unique identifier for this canvas instance
    state: CanvasState; // The current state object for this canvas from the reducer
}

/**
 * React component responsible for rendering an HTML5 canvas and executing
 * drawing commands received via its state props. Handles command queueing
 * to ensure proper order of execution even if commands arrive rapidly.
 */
const CanvasModule: React.FC<CanvasModuleProps> = ({ id, state }) => {
    // Ref to access the underlying HTML <canvas> element
    const canvasRef = useRef<HTMLCanvasElement>(null);
    // State to hold the 2D rendering context once it's obtained
    const [ctx, setCtx] = useState<CanvasRenderingContext2D | null>(null);
    // State to manage the queue of commands that this component instance needs to process
    // We copy commands from props (`state.commandQueue`) into this local queue.
    const [commandsToProcess, setCommandsToProcess] = useState<CanvasDrawCommand[]>([]);
    // Ref to act as a flag, preventing multiple asynchronous processing loops from running simultaneously
    const isProcessing = useRef(false);

    // Destructure state properties for easier access
    const { width, height, bgColor, commandQueue } = state;

    // --- Effect 1: Obtain and initialize the 2D rendering context ---
    // Runs when the component mounts or when fundamental properties (size, bg) change.
    useEffect(() => {
        // Ensure the canvas DOM element is available
        if (canvasRef.current) {
            console.log(`Canvas ${id}: Attempting to get context (Width: ${width}, Height: ${height})`);
            const context = canvasRef.current.getContext('2d');
            if (context) {
                // Store the context in state, making it available for drawing
                setCtx(context);
                console.log(`Canvas ${id}: Context obtained successfully.`);
                // Apply the initial background color when context is ready or bg/size changes
                context.fillStyle = bgColor || '#FFFFFF';
                context.fillRect(0, 0, width, height);
                // Reset local processing state if canvas dimensions/background change
                setCommandsToProcess([]); // Clear any potentially old commands
                isProcessing.current = false; // Reset processing flag
            } else {
                // Log error if context creation fails (e.g., unsupported browser)
                console.error(`Canvas ${id}: Failed to get 2D context.`);
                setCtx(null); // Ensure context state is null if failed
            }
        }
        // Dependencies: Re-run if the canvas needs fundamental re-setup
    }, [id, width, height, bgColor]);

    // --- Effect 2: Transfer new commands from props to the local processing queue ---
    // Runs whenever the `commandQueue` prop from the parent state changes.
    useEffect(() => {
        // Check if there are new commands in the props queue
        if (commandQueue && commandQueue.length > 0) {
            // Filter out commands that might already be in the local `commandsToProcess` queue
            // or commands that seem older than the latest command we have (using ID as rough proxy).
            // This prevents duplicates and potential out-of-order issues if props update strangely.
            const newCommands = commandQueue.filter(cmdFromProp =>
                // Check if command ID is NOT present in the current local processing queue
                !commandsToProcess.some(cmdInQueue => cmdInQueue.commandId === cmdFromProp.commandId) &&
                // Additionally, only add commands "newer" than the last one we know about locally.
                // This assumes command IDs are roughly sequential (like timestamps).
                (commandsToProcess.length === 0 || cmdFromProp.commandId > commandsToProcess[commandsToProcess.length - 1].commandId)
            );

            // If there are genuinely new commands to add
            if (newCommands.length > 0) {
                console.log(`Canvas ${id}: Adding ${newCommands.length} new command(s) to local queue.`);
                // Append the new commands to the existing local queue
                setCommandsToProcess(prevQueue => [...prevQueue, ...newCommands]);
            }
        }
        // Dependency: Run only when the command queue from props changes.
        // Also depend on `commandsToProcess` state itself to help with the filtering logic.
    }, [commandQueue, commandsToProcess, id]);

    // --- Effect 3: Process commands from the local queue asynchronously ---
    // Runs whenever the context (`ctx`) is ready or the local `commandsToProcess` queue changes.
    useEffect(() => {
        // Guard clauses: Don't proceed if
        // - Context is not yet available (`ctx` is null)
        // - There are no commands in the local queue to process
        // - Another processing loop is already running (`isProcessing.current` is true)
        if (!ctx || commandsToProcess.length === 0 || isProcessing.current) {
            return;
        }

        // Set the flag to indicate processing has started
        isProcessing.current = true;
        console.log(`Canvas ${id}: Start processing command queue (${commandsToProcess.length} items)`);

        // Counter for commands processed in this batch
        let processedCountInBatch = 0;

        // Asynchronous function to process one command and schedule the next
        const processNextCommand = () => {
            // Get the context again (needed inside this scope)
            const currentCtx = ctx;

            // Stop conditions for the processing loop:
            // - No context (shouldn't happen if initial check passed, but safety first)
            // - No more commands left in the *original* batch we started processing
            if (!currentCtx || processedCountInBatch >= commandsToProcess.length) {
                console.log(`Canvas ${id}: Finished processing batch (${processedCountInBatch} items).`);
                // Mark processing as finished
                isProcessing.current = false;
                // Update the component's state *after* the loop finishes to remove processed commands
                if (processedCountInBatch > 0) {
                    setCommandsToProcess(prevQueue => prevQueue.slice(processedCountInBatch));
                }
                return; // Exit the loop
            }

            // Get the next command from the state *at the start of this batch*
            const command = commandsToProcess[processedCountInBatch];
            console.log(`Canvas ${id}: Executing command ${command.commandId} (${processedCountInBatch + 1}/${commandsToProcess.length})`, command);
            const { command: commandName, options } = command;

            try {
                // --- Execute the drawing command based on its type ---
                switch (commandName) {
                    case 'clear':
                        currentCtx.fillStyle = options.color || bgColor || '#FFFFFF';
                        currentCtx.fillRect(0, 0, width, height);
                        break;
                    case 'config':
                        // Apply canvas context configurations
                        if (options.strokeStyle !== undefined) currentCtx.strokeStyle = options.strokeStyle;
                        if (options.fillStyle !== undefined) currentCtx.fillStyle = options.fillStyle;
                        if (options.lineWidth !== undefined) currentCtx.lineWidth = options.lineWidth;
                        break;
                    case 'line':
                        currentCtx.beginPath();
                        currentCtx.moveTo(options.x1, options.y1);
                        currentCtx.lineTo(options.x2, options.y2);
                        currentCtx.stroke();
                        break;
                    case 'rect':
                        if (options.filled) {
                            currentCtx.fillRect(options.x, options.y, options.width, options.height);
                        } else {
                            currentCtx.strokeRect(options.x, options.y, options.width, options.height);
                        }
                        break;
                    case 'circle':
                        currentCtx.beginPath();
                        currentCtx.arc(options.cx, options.cy, options.radius, 0, Math.PI * 2);
                        if (options.filled) {
                            currentCtx.fill();
                        } else {
                            currentCtx.stroke();
                        }
                        break;
                    default:
                        console.warn(`Canvas ${id}: Unknown draw command "${commandName}"`);
                }
                // Increment the counter for successfully processed commands in this batch
                processedCountInBatch++;
            } catch (error) {
                console.error(`Canvas ${id}: Error executing command ${command.commandId}:`, commandName, options, error);
                // --- Error Handling ---
                // Decide whether to stop the entire queue or just skip the failed command.
                // Option A: Stop processing the rest of this batch on error.
                console.log(`Canvas ${id}: Stopping processing queue due to error.`);
                isProcessing.current = false; // Mark processing as finished (due to error)
                // Remove the commands processed *before* the error occurred
                if (processedCountInBatch > 0) {
                    setCommandsToProcess(prevQueue => prevQueue.slice(processedCountInBatch));
                }
                return; // Stop the animation frame loop

                // Option B: Skip the failed command and continue (might lead to weird visual state)
                // processedCountInBatch++; // Increment even on error to move past it
            }

            // --- Schedule the next iteration ---
            // Use requestAnimationFrame to process the next command in the batch.
            // This yields control back to the browser briefly, preventing the UI
            // from freezing if there are many commands to process quickly.
            requestAnimationFrame(processNextCommand);
        };

        // --- Start the processing loop ---
        requestAnimationFrame(processNextCommand);

        // No cleanup needed typically, state updates handle queue management
        // and isProcessing ref prevents overlap.

        // Dependencies: Re-run this effect if the context becomes available/unavailable,
        // or if the local command queue state changes. Also include dimensions/bg
        // as they might be used within the drawing commands (e.g., clear).
    }, [ctx, commandsToProcess, width, height, bgColor, id]);

    // Render the canvas element
    return (
        <div className="canvas-module-container">
            <h3>Canvas: {id}</h3>
            <canvas
                ref={canvasRef}
                width={width}
                height={height}
                className="canvas-element"
                // Style is less critical now as background is filled via JS, but can be fallback
                style={{ backgroundColor: bgColor }}
            >
                Your browser does not support the canvas element.
            </canvas>
        </div>
    );
};

export default CanvasModule;