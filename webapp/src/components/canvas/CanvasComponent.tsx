import React, {
    useRef,
    useEffect,
    useState,
    useCallback,
    forwardRef,
    useImperativeHandle
} from 'react';
import {
    CanvasState,
    CanvasUpdatePayload,
    CanvasClickEventMessage,
    // Import specific options types for type safety
    ClearOptions,
    DrawLineOptions,
    DrawRectOptions,
    DrawCircleOptions,
    DrawPolylineOptions,
    DrawPolygonOptions,
    DrawEllipseOptions,
    DrawTextOptions,
    CreateBufferOptions,
    DrawBufferOptions,
    DestroyBufferOptions
} from './types';
import { SentMessage, ComponentHandle } from '../../types'; // Import shared types
import './CanvasComponent.css';

// --- Constants ---
const ONSCREEN_BUFFER_ID = 0; // Constant for the visible canvas buffer ID

// --- Component Props ---
interface CanvasComponentProps {
    id: string;
    state: CanvasState; // Contains width, height
    onInteraction?: (message: SentMessage) => void;
    onReady?: (id: string) => void; // Callback when component is mounted and handle is ready
}

// Type alias for possible rendering contexts
type RenderingContext = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

// --- Main Component (Wrapped with forwardRef) ---
const CanvasComponent = forwardRef<ComponentHandle, CanvasComponentProps>(
    ({ id, state, onInteraction, onReady }, ref) => {

        // --- Refs ---
        const canvasRef = useRef<HTMLCanvasElement>(null); // Ref for the visible canvas element
        const offscreenCanvases = useRef<Map<number, OffscreenCanvas | HTMLCanvasElement>>(new Map()); // Stores offscreen canvas elements (ID -> Canvas)
        const offscreenContexts = useRef<Map<number, RenderingContext>>(new Map()); // Stores offscreen rendering contexts (ID -> Context)
        const onscreenCtxRef = useRef<CanvasRenderingContext2D | null>(null); // Ref for the visible canvas's context
        const isReadySignaled = useRef(false); // Track if onReady has been called (handles StrictMode)

        // --- State ---
        const [initError, setInitError] = useState<string | null>(null); // Stores any initialization error message

        const { width, height } = state; // Extract dimensions from state

        // --- Effect 1: Initialize Onscreen Context & Signal Readiness ---
        useEffect(() => {
            console.log(`Canvas ${id}: Initializing Effect (Size: ${width}x${height})`);
            setInitError(null); // Clear previous errors
            isReadySignaled.current = false; // Reset ready signal on re-initialization

            const canvas = canvasRef.current;
            if (!canvas) {
                console.error(`Canvas ${id}: Onscreen canvas ref is null during init.`);
                setInitError("Canvas element not found.");
                return;
            }

            let context: CanvasRenderingContext2D | null = null;
            try {
                context = canvas.getContext('2d');
            } catch (e) {
                console.error(`Canvas ${id}: Error getting 2D context:`, e);
                setInitError("Error getting 2D context.");
                onscreenCtxRef.current = null;
                return;
            }

            if (!context) {
                console.error(`Canvas ${id}: Failed to get 2D context for onscreen canvas (returned null).`);
                setInitError("Failed to get 2D context.");
                onscreenCtxRef.current = null;
                return;
            }

            // Store the context and perform initial clear
            console.log(`Canvas ${id}: Onscreen context obtained.`);
            onscreenCtxRef.current = context;
            // Perform a clear using the current (default or previous) canvas state
            context.clearRect(0, 0, width, height);

            // Signal that the component is ready for imperative calls
            // Check ref flag to prevent double signaling in StrictMode
            if (onReady && !isReadySignaled.current) {
                console.log(`Canvas ${id}: Signaling ready.`);
                onReady(id);
                isReadySignaled.current = true; // Mark as signaled for this mount
            }

            // Cleanup function: Runs on unmount or before re-running the effect (due to StrictMode or deps change)
            return () => {
                console.log(`Canvas ${id}: Cleanup Effect - Clearing refs and context.`);
                onscreenCtxRef.current = null;
                // Clear maps holding offscreen resources
                offscreenCanvases.current.clear();
                offscreenContexts.current.clear();
                isReadySignaled.current = false; // Reset flag on unmount/cleanup
            };
        }, [id, width, height, onReady]); // Dependencies: Re-run if ID, dimensions, or the onReady callback changes


        /**
         * Helper function to apply optional drawing styles to the context.
         * If any style options are provided, it saves the context state first.
         * @param ctx The rendering context to apply styles to.
         * @param opts The options object potentially containing style properties.
         * @returns `true` if styles were applied (and context was saved), `false` otherwise.
         */
        const applyStyles = (ctx: RenderingContext, opts: any): boolean => {
            // Check if any specific style option is present (not undefined)
            const styleOptionsProvided = opts.lineColor !== undefined ||
                opts.lineWidth !== undefined ||
                opts.fillColor !== undefined || // Check presence, handle null in drawing logic
                opts.textColor !== undefined ||
                opts.textSize !== undefined;

            if (styleOptionsProvided) {
                ctx.save(); // Save state BEFORE applying any custom styles

                // Apply styles ONLY if they are explicitly provided
                if (opts.lineColor !== undefined) {
                    ctx.strokeStyle = opts.lineColor;
                }
                if (opts.lineWidth !== undefined) {
                    ctx.lineWidth = opts.lineWidth;
                }
                // Set fillStyle for shapes if it's a non-null string.
                // This might be overwritten by textColor for text drawing later.
                if (opts.fillColor !== undefined && opts.fillColor !== null) {
                    ctx.fillStyle = opts.fillColor;
                }
                // Handle font: Use a generic family if size IS specified.
                // Otherwise, let the canvas default font apply.
                if (opts.textSize !== undefined) {
                    ctx.font = `${opts.textSize}px sans-serif`;
                }
                // Handle textColor (primarily for fillText): Set fillStyle if provided.
                // This takes precedence over fillColor for text.
                if (opts.textColor !== undefined) {
                    ctx.fillStyle = opts.textColor;
                }

                return true; // Indicate that save() was called
            }
            return false; // No custom styles applied, no save() called
        };


        // --- Imperative Update Processing Function ---
        // This function is exposed via useImperativeHandle and called directly by App.tsx
        const processUpdate = useCallback((payload: CanvasUpdatePayload) => {
            const onscreenCtx = onscreenCtxRef.current;

            // Check if the component is in an error state
            if (initError) {
                console.error(`Canvas ${id}: Cannot process update due to initialization error: ${initError}`);
                return;
            }

            // Basic validation of the incoming payload structure
            if (!payload || !payload.action || !payload.options) {
                console.warn(`Canvas ${id}: Skipping invalid imperative update payload:`, payload);
                return;
            }

            const { action, options } = payload;

            // Determine the target rendering context and buffer ID
            let targetCtx: RenderingContext | null = null;
            let targetBufferId: number = ONSCREEN_BUFFER_ID; // Default to onscreen (0)
            let needsContextLookup = true; // Flag to check if we need to find a context

            // Buffer management actions have specific ID requirements
            if (action === 'createBuffer' || action === 'destroyBuffer') {
                needsContextLookup = false; // Context not needed directly for these actions
                const requiredBufferId = (options as CreateBufferOptions | DestroyBufferOptions).bufferId;
                if (requiredBufferId === undefined || requiredBufferId === null || requiredBufferId <= 0) {
                    console.error(`Canvas ${id}: Action "${action}" requires a positive 'bufferId'. Skipping. Options:`, options);
                    return;
                }
                targetBufferId = requiredBufferId; // Store the ID for use in the switch
            } else if (action === 'drawBuffer') {
                needsContextLookup = false; // Context looked up within the specific case
                const drawOpts = options as DrawBufferOptions;
                if (drawOpts.sourceBufferId === undefined || drawOpts.sourceBufferId === null ||
                    drawOpts.targetBufferId === undefined || drawOpts.targetBufferId === null) {
                    console.error(`Canvas ${id}: Action "${action}" requires 'sourceBufferId' and 'targetBufferId'. Skipping. Options:`, options);
                    return;
                }
            } else {
                // For drawing/clearing actions, determine target buffer from options
                targetBufferId = (options as any).bufferId ?? ONSCREEN_BUFFER_ID;
            }

            // Look up the context if needed (not for create/destroy/drawBuffer initially)
            if (needsContextLookup) {
                if (targetBufferId === ONSCREEN_BUFFER_ID) {
                    targetCtx = onscreenCtx;
                } else {
                    targetCtx = offscreenContexts.current.get(targetBufferId) ?? null;
                }
                // Validate context availability for drawing actions
                if (!targetCtx) {
                    console.error(`Canvas ${id}: Target context for buffer ${targetBufferId} not found for action "${action}". Skipping.`);
                    return;
                }
            }

            // --- Execute the requested action ---
            let contextWasSaved = false; // Track if applyStyles saved the context
            try {
                // Switch based on the action type
                switch (action) {
                    // --- Clearing Actions ---
                    case 'clear':
                        if (!targetCtx) throw new Error(`Target context unavailable for clear on buffer ${targetBufferId}`);
                        targetCtx.clearRect(0, 0, targetCtx.canvas.width, targetCtx.canvas.height);
                        break;

                    // --- Drawing Actions ---
                    case 'drawLine': {
                        if (!targetCtx) throw new Error(`Target context unavailable for drawLine on buffer ${targetBufferId}`);
                        const opts = options as DrawLineOptions;
                        contextWasSaved = applyStyles(targetCtx, opts); // Apply optional styles
                        // --- Drawing logic ---
                        targetCtx.beginPath();
                        targetCtx.moveTo(opts.x1, opts.y1);
                        targetCtx.lineTo(opts.x2, opts.y2);
                        targetCtx.stroke(); // Use current/applied stroke style
                        // --- End drawing logic ---
                        break;
                    }
                    case 'drawRect': {
                        if (!targetCtx) throw new Error(`Target context unavailable for drawRect on buffer ${targetBufferId}`);
                        const opts = options as DrawRectOptions;
                        contextWasSaved = applyStyles(targetCtx, opts);
                        // --- Drawing logic ---
                        // Fill ONLY if fillColor is provided and not null
                        if (opts.fillColor !== undefined && opts.fillColor !== null) {
                            targetCtx.fillRect(opts.x, opts.y, opts.width, opts.height);
                        }
                        // Always draw the outline stroke
                        targetCtx.strokeRect(opts.x, opts.y, opts.width, opts.height);
                        // --- End drawing logic ---
                        break;
                    }
                    case 'drawCircle': {
                        if (!targetCtx) throw new Error(`Target context unavailable for drawCircle on buffer ${targetBufferId}`);
                        const opts = options as DrawCircleOptions;
                        contextWasSaved = applyStyles(targetCtx, opts);
                        // --- Drawing logic ---
                        targetCtx.beginPath();
                        targetCtx.arc(opts.cx, opts.cy, opts.radius, 0, Math.PI * 2);
                        // Fill ONLY if fillColor is provided and not null
                        if (opts.fillColor !== undefined && opts.fillColor !== null) {
                            targetCtx.fill();
                        }
                        // Always draw the outline stroke
                        targetCtx.stroke();
                        // --- End drawing logic ---
                        break;
                    }
                    case 'drawPolyline': {
                        if (!targetCtx) throw new Error(`Target context unavailable for drawPolyline on buffer ${targetBufferId}`);
                        const opts = options as DrawPolylineOptions;
                        if (!opts.points || opts.points.length < 2) throw new Error("Polyline requires at least 2 points");
                        contextWasSaved = applyStyles(targetCtx, opts);
                        // --- Drawing logic ---
                        targetCtx.beginPath();
                        targetCtx.moveTo(opts.points[0].x, opts.points[0].y);
                        for (let k = 1; k < opts.points.length; k++) {
                            targetCtx.lineTo(opts.points[k].x, opts.points[k].y);
                        }
                        targetCtx.stroke(); // Draw the open path
                        // --- End drawing logic ---
                        break;
                    }
                    case 'drawPolygon': {
                        if (!targetCtx) throw new Error(`Target context unavailable for drawPolygon on buffer ${targetBufferId}`);
                        const opts = options as DrawPolygonOptions;
                        if (!opts.points || opts.points.length < 3) throw new Error("Polygon requires at least 3 points");
                        contextWasSaved = applyStyles(targetCtx, opts);
                        // --- Drawing logic ---
                        targetCtx.beginPath();
                        targetCtx.moveTo(opts.points[0].x, opts.points[0].y);
                        for (let k = 1; k < opts.points.length; k++) {
                            targetCtx.lineTo(opts.points[k].x, opts.points[k].y);
                        }
                        targetCtx.closePath(); // Close the path
                        // Fill ONLY if fillColor is provided and not null
                        if (opts.fillColor !== undefined && opts.fillColor !== null) {
                            targetCtx.fill();
                        }
                        // Always draw the outline stroke
                        targetCtx.stroke();
                        // --- End drawing logic ---
                        break;
                    }
                    case 'drawEllipse': {
                        if (!targetCtx) throw new Error(`Target context unavailable for drawEllipse on buffer ${targetBufferId}`);
                        const opts = options as DrawEllipseOptions;
                        contextWasSaved = applyStyles(targetCtx, opts);
                        // --- Drawing logic ---
                        targetCtx.beginPath();
                        targetCtx.ellipse(opts.cx, opts.cy, opts.radiusX, opts.radiusY, 0, 0, Math.PI * 2);
                        // Fill ONLY if fillColor is provided and not null
                        if (opts.fillColor !== undefined && opts.fillColor !== null) {
                            targetCtx.fill();
                        }
                        // Always draw the outline stroke
                        targetCtx.stroke();
                        // --- End drawing logic ---
                        break;
                    }
                    case 'drawText': {
                        if (!targetCtx) throw new Error(`Target context unavailable for drawText on buffer ${targetBufferId}`);
                        const opts = options as DrawTextOptions;
                        contextWasSaved = applyStyles(targetCtx, opts); // Applies font and potentially fillStyle via textColor
                        // --- Drawing logic ---
                        // fillText uses the current fillStyle (set by textColor or fillColor in applyStyles)
                        targetCtx.fillText(opts.text, opts.x, opts.y);
                        // --- End drawing logic ---
                        break;
                    }

                    // --- Buffer Management Actions ---
                    case 'createBuffer': {
                        const opts = options as CreateBufferOptions;
                        const newBufferId = opts.bufferId; // Already validated > 0
                        if (offscreenCanvases.current.has(newBufferId)) {
                            console.warn(`Canvas ${id}: Buffer ${newBufferId} already exists. Recreating.`);
                            // Optionally destroy existing before recreating?
                        }

                        console.log(`Canvas ${id}: Creating offscreen buffer ${newBufferId} (${width}x${height})`);
                        let newCanvas: OffscreenCanvas | HTMLCanvasElement;
                        let newCtx: RenderingContext | null = null;
                        try {
                            if (typeof OffscreenCanvas !== 'undefined') {
                                newCanvas = new OffscreenCanvas(width, height);
                                newCtx = newCanvas.getContext('2d') as RenderingContext | null;
                            } else {
                                console.warn(`Canvas ${id}: OffscreenCanvas not supported, falling back to hidden <canvas>.`);
                                const hiddenCanvas = document.createElement('canvas');
                                hiddenCanvas.width = width;
                                hiddenCanvas.height = height;
                                newCanvas = hiddenCanvas;
                                newCtx = newCanvas.getContext('2d');
                            }

                            if (!newCtx) throw new Error("Failed to get rendering context for the new buffer.");

                            offscreenCanvases.current.set(newBufferId, newCanvas);
                            offscreenContexts.current.set(newBufferId, newCtx);
                            console.log(`Canvas ${id}: Successfully created buffer ${newBufferId}.`);

                        } catch (err) {
                            console.error(`Canvas ${id}: Error creating buffer ${newBufferId}:`, err);
                            offscreenCanvases.current.delete(newBufferId);
                            offscreenContexts.current.delete(newBufferId);
                            throw err; // Re-throw
                        }
                        break;
                    }
                    case 'drawBuffer': {
                        const opts = options as DrawBufferOptions;
                        const sourceCanvas = offscreenCanvases.current.get(opts.sourceBufferId);
                        let destinationCtx: RenderingContext | null = null;

                        // Determine destination context
                        if (opts.targetBufferId === ONSCREEN_BUFFER_ID) {
                            destinationCtx = onscreenCtx;
                        } else {
                            destinationCtx = offscreenContexts.current.get(opts.targetBufferId) ?? null;
                        }

                        // Validate source and destination
                        if (!sourceCanvas) throw new Error(`Source buffer ${opts.sourceBufferId} not found for drawBuffer.`);
                        if (!destinationCtx) throw new Error(`Target context for buffer ${opts.targetBufferId} not found for drawBuffer.`);

                        if (sourceCanvas instanceof HTMLCanvasElement ||
                            (typeof OffscreenCanvas !== 'undefined' && sourceCanvas instanceof OffscreenCanvas))
                        {
                            // Perform the draw operation. No save/restore needed here as drawImage doesn't
                            // permanently change context state like strokeStyle etc.
                            destinationCtx.drawImage(sourceCanvas, 0, 0);
                        } else {
                            throw new Error(`Source buffer ${opts.sourceBufferId} is not a valid drawable type.`);
                        }
                        break;
                    }
                    case 'destroyBuffer': {
                        const opts = options as DestroyBufferOptions;
                        const bufferIdToDestroy = opts.bufferId; // Already validated > 0
                        console.log(`Canvas ${id}: Destroying buffer ${bufferIdToDestroy}`);
                        const deletedCanvas = offscreenCanvases.current.delete(bufferIdToDestroy);
                        const deletedCtx = offscreenContexts.current.delete(bufferIdToDestroy);
                        if (!deletedCanvas && !deletedCtx) {
                            console.warn(`Canvas ${id}: Attempted to destroy buffer ${bufferIdToDestroy}, but it was not found.`);
                        }
                        break;
                    }
                    default:
                        console.warn(`Canvas ${id}: Received unknown imperative action "${(action as any)}"`);
                }

            } catch (error: any) {
                // Catch errors during action execution
                console.error(`Canvas ${id}: Error processing imperative action "${action}" for buffer ${targetBufferId}:`, options, error.message || error);
                // Optionally send an error message back to the Hero script
                if (onInteraction) {
                    const errorMsg: SentMessage = {
                        id: 0, component: 'canvas', type: 'error', src: id,
                        payload: { message: `Error processing action "${action}" for buffer ${targetBufferId}: ${error.message}` }
                    };
                    onInteraction(errorMsg);
                }
            } finally {
                // CRITICAL: Restore context state IF it was saved by applyStyles
                if (contextWasSaved && targetCtx) {
                    targetCtx.restore();
                }
            }
            // End of action execution
        }, [id, onInteraction, width, height, initError /* Refs like onscreenCtxRef are stable */]);


        // --- Expose Imperative Handle ---
        // This makes the `processUpdate` function callable via the ref passed from App.tsx
        useImperativeHandle(ref, () => ({
            processUpdate
        }), [processUpdate]); // Update the handle if processUpdate changes


        // --- Click Handler ---
        // Handles clicks on the visible canvas and sends event messages back
        const handleCanvasClick = useCallback((event: React.MouseEvent<HTMLCanvasElement>) => {
            if (!onInteraction) return; // Only handle clicks if interaction callback is provided

            const canvas = event.currentTarget;
            const rect = canvas.getBoundingClientRect();
            const x = Math.round(event.clientX - rect.left);
            const y = Math.round(event.clientY - rect.top);

            console.log(`Canvas ${id}: Click detected at (${x}, ${y})`);

            const clickMessage: CanvasClickEventMessage = {
                id: 0, component: 'canvas', type: 'event', src: id,
                payload: { event: 'click', x: x, y: y }
            };
            onInteraction(clickMessage);
        }, [id, onInteraction]);


        // --- Render ---
        if (initError) {
            return (
                <div style={{
                    color: 'var(--sk-status-error-fg)', padding: '10px',
                    border: '1px solid var(--sk-status-error-border)',
                    backgroundColor: 'var(--sk-status-error-bg)'
                }}>
                    Canvas Error: {initError}
                </div>
            );
        }

        // Render the main canvas element
        return (
            <canvas
                ref={canvasRef}
                width={width}
                height={height}
                className="canvas-element"
                onClick={handleCanvasClick} // Attach click handler
                style={{
                    maxWidth: '100%', // Ensure responsiveness
                    display: 'block', // Prevents extra space below
                    margin: 'auto', // Center if container allows
                }}
                aria-label={`Drawing canvas ${id}`} // Accessibility
            >
                {/* Fallback text for browsers that don't support canvas */}
                Your browser does not support the canvas element.
            </canvas>
        );
    } // End of component function body
); // End of forwardRef

export default CanvasComponent;