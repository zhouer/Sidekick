import { ComponentEventMessage } from "../../types"; // Import base type if needed

// --- State ---
export interface CanvasState {
    width: number;
    height: number;
    // commandQueue removed
}

// --- Protocol Payloads ---

// --- Spawn ---
export interface CanvasSpawnPayload {
    width: number;
    height: number;
}

// --- Update Actions & Options (commandId removed from all) ---

// Base interface for options that target a buffer
interface BaseBufferOptions {
    /** Optional: The ID of the target buffer. If omitted or null/undefined, defaults to 0 (the onscreen canvas). */
    bufferId?: number;
}

// Options for drawing actions with common styles
interface CommonStyleOptions {
    lineColor?: string;
    lineWidth?: number;
}

interface FillableStyleOptions extends CommonStyleOptions {
    fillColor?: string;
}

// Specific Options for each action
export interface ClearOptions extends BaseBufferOptions {}
export interface DrawLineOptions extends BaseBufferOptions, CommonStyleOptions { x1: number; y1: number; x2: number; y2: number; }
export interface DrawRectOptions extends BaseBufferOptions, FillableStyleOptions { x: number; y: number; width: number; height: number; }
export interface DrawCircleOptions extends BaseBufferOptions, FillableStyleOptions { cx: number; cy: number; radius: number; }
export interface DrawPolylineOptions extends BaseBufferOptions, CommonStyleOptions { points: Array<{ x: number; y: number }>; }
export interface DrawPolygonOptions extends BaseBufferOptions, FillableStyleOptions { points: Array<{ x: number; y: number }>; }
export interface DrawEllipseOptions extends BaseBufferOptions, FillableStyleOptions { cx: number; cy: number; radiusX: number; radiusY: number; }
export interface DrawTextOptions extends BaseBufferOptions { x: number; y: number; text: string; textColor?: string; textSize?: number; }
export interface CreateBufferOptions { bufferId: number; }
export interface DrawBufferOptions { sourceBufferId: number; targetBufferId: number; }
export interface DestroyBufferOptions { bufferId: number; }

// --- Update Payload (Discriminated Union - commandId removed) ---
export type CanvasUpdatePayload =
    | { action: "clear";       options: ClearOptions; }
    | { action: "drawLine";    options: DrawLineOptions; }
    | { action: "drawRect";    options: DrawRectOptions; }
    | { action: "drawCircle";  options: DrawCircleOptions; }
    | { action: "drawPolyline";options: DrawPolylineOptions; }
    | { action: "drawPolygon"; options: DrawPolygonOptions; }
    | { action: "drawEllipse"; options: DrawEllipseOptions; }
    | { action: "drawText";    options: DrawTextOptions; }
    | { action: "createBuffer";options: CreateBufferOptions; }
    | { action: "drawBuffer";  options: DrawBufferOptions; }
    | { action: "destroyBuffer";options: DestroyBufferOptions; };

// --- Event Payload (Sidekick -> Hero) ---
export interface CanvasClickPayload {
    event: "click";
    x: number;
    y: number;
}

// Define the specific ComponentEventMessage for Canvas clicks
export interface CanvasClickEventMessage extends ComponentEventMessage {
    component: 'canvas';
    payload: CanvasClickPayload;
}