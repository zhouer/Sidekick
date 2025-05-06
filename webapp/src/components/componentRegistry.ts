import { ComponentDefinition } from '../types'; // Import shared types

// Import Components
import GridComponent from './grid/GridComponent.tsx';
import ConsoleComponent from './console/ConsoleComponent.tsx';
import VizComponent from './viz/VizComponent.tsx';
import CanvasComponent from './canvas/CanvasComponent.tsx';
import ControlComponent from './control/ControlComponent.tsx';

// Import Component Logic functions
import * as gridLogic from './grid/gridLogic';
import * as consoleLogic from './console/consoleLogic';
import * as vizLogic from './viz/vizLogic';
import * as canvasLogic from './canvas/canvasLogic';
import * as controlLogic from './control/controlLogic';

// Define the registry map, mapping component type strings to their definitions
const registry = new Map<string, ComponentDefinition>();

// Register each built-in component
registry.set('grid', {
    type: 'grid', // Component identifier string
    displayName: 'Grid',
    component: GridComponent,
    getInitialState: gridLogic.getInitialState,
    updateState: gridLogic.updateState,
    imperativeUpdate: false, // Default or explicitly false
});

registry.set('console', {
    type: 'console',
    displayName: 'Console',
    component: ConsoleComponent,
    getInitialState: consoleLogic.getInitialState,
    updateState: consoleLogic.updateState,
    imperativeUpdate: false,
});

registry.set('viz', {
    type: 'viz',
    displayName: 'Viz',
    component: VizComponent,
    getInitialState: vizLogic.getInitialState,
    updateState: vizLogic.updateState,
    imperativeUpdate: false, // Viz uses state updates for reactivity
});

registry.set('canvas', {
    type: 'canvas',
    displayName: 'Canvas',
    component: CanvasComponent,
    getInitialState: canvasLogic.getInitialState,
    updateState: canvasLogic.updateState, // Keep for consistency, but it won't be used for updates
    imperativeUpdate: true, // <-- Enable imperative updates for Canvas
});

registry.set('control', {
    type: 'control',
    displayName: 'Control',
    component: ControlComponent,
    getInitialState: controlLogic.getInitialState,
    updateState: controlLogic.updateState,
    imperativeUpdate: false,
});

// Export the registry for use in the main application
export const componentRegistry = registry;

// Log registered components on initialization (useful for debugging)
console.log('Component Registry initialized with types:', Array.from(componentRegistry.entries()).map(([key, value]) => ({ type: key, imperative: !!value.imperativeUpdate })));