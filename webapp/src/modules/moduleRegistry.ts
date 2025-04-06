// Sidekick/webapp/src/modules/moduleRegistry.ts
import { ModuleDefinition } from '../types'; // Import shared types

// Import Module Components
import GridComponent from './grid/GridComponent.tsx';
import ConsoleComponent from './console/ConsoleComponent.tsx';
import VizComponent from './viz/VizComponent.tsx';
import CanvasComponent from './canvas/CanvasComponent.tsx';
import ControlComponent from './control/ControlComponent.tsx';

// Import Module Logic functions
import * as gridLogic from './grid/gridLogic';
import * as consoleLogic from './console/consoleLogic';
import * as vizLogic from './viz/vizLogic';
import * as canvasLogic from './canvas/canvasLogic';
import * as controlLogic from './control/controlLogic';

// Define the registry map, mapping module type strings to their definitions
const registry = new Map<string, ModuleDefinition>();

// Register each built-in module
registry.set('grid', {
    type: 'grid', // Module identifier string
    displayName: 'Grid',
    component: GridComponent,
    getInitialState: gridLogic.getInitialState,
    updateState: gridLogic.updateState,
});

registry.set('console', {
    type: 'console',
    displayName: 'Console',
    component: ConsoleComponent,
    getInitialState: consoleLogic.getInitialState,
    updateState: consoleLogic.updateState,
});

registry.set('viz', {
    type: 'viz',
    displayName: 'Viz',
    component: VizComponent,
    getInitialState: vizLogic.getInitialState,
    updateState: vizLogic.updateState,
});

registry.set('canvas', {
    type: 'canvas',
    displayName: 'Canvas',
    component: CanvasComponent,
    getInitialState: canvasLogic.getInitialState,
    updateState: canvasLogic.updateState,
});

registry.set('control', {
    type: 'control',
    displayName: 'Control',
    component: ControlComponent,
    getInitialState: controlLogic.getInitialState,
    updateState: controlLogic.updateState,
});

// Export the registry for use in the main application
export const moduleRegistry = registry;

// Log registered modules on initialization (useful for debugging)
console.log('Module Registry initialized with types:', Array.from(moduleRegistry.keys()));