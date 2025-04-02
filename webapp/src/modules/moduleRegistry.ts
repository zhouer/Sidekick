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
    component: GridComponent,
    getInitialState: gridLogic.getInitialState,
    updateState: gridLogic.updateState,
    isInteractive: true,
});

registry.set('console', {
    type: 'console',
    component: ConsoleComponent,
    getInitialState: consoleLogic.getInitialState,
    updateState: consoleLogic.updateState,
    isInteractive: true,
});

registry.set('viz', {
    type: 'viz',
    component: VizComponent,
    getInitialState: vizLogic.getInitialState,
    updateState: vizLogic.updateState,
    isInteractive: false,
});

registry.set('canvas', {
    type: 'canvas',
    component: CanvasComponent,
    getInitialState: canvasLogic.getInitialState,
    updateState: canvasLogic.updateState,
    isInteractive: false,
});

registry.set('control', {
    type: 'control',
    component: ControlComponent,
    getInitialState: controlLogic.getInitialState,
    updateState: controlLogic.updateState,
    isInteractive: true,
});

// Export the registry for use in the main application
export const moduleRegistry = registry;

// Log registered modules on initialization (useful for debugging)
console.log('Module Registry initialized with types:', Array.from(moduleRegistry.keys()));