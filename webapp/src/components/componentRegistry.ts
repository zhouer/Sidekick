// webapp/src/components/componentRegistry.ts
import { ComponentDefinition } from '../types';

// Import Existing Components & Logic
import GridComponent from './grid/GridComponent.tsx';
import * as gridLogic from './grid/gridLogic';
import ConsoleComponent from './console/ConsoleComponent.tsx';
import * as consoleLogic from './console/consoleLogic';
import VizComponent from './viz/VizComponent.tsx';
import * as vizLogic from './viz/vizLogic';
import CanvasComponent from './canvas/CanvasComponent.tsx';
import * as canvasLogic from './canvas/canvasLogic';

// Import New Components & Logic
import LabelComponent from './label/LabelComponent.tsx';
import * as labelLogic from './label/labelLogic.ts';
import ButtonComponent from './button/ButtonComponent.tsx';
import * as buttonLogic from './button/buttonLogic.ts';
import TextboxComponent from './textbox/TextboxComponent.tsx';
import * as textboxLogic from './textbox/textboxLogic.ts';
import RowComponent from './row/RowComponent.tsx';
import * as rowLogic from './row/rowLogic.ts';
import ColumnComponent from './column/ColumnComponent.tsx';
import * as columnLogic from './column/columnLogic.ts';
import MarkdownComponent from './markdown/MarkdownComponent.tsx';
import * as markdownLogic from './markdown/markdownLogic.ts';

const registry = new Map<string, ComponentDefinition<any, any, any>>();

// Register existing components
registry.set('grid', {
    type: 'grid',
    displayName: 'Grid',
    component: GridComponent,
    getInitialState: gridLogic.getInitialState,
    updateState: gridLogic.updateState,
    imperativeUpdate: false,
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
    imperativeUpdate: false,
});

registry.set('canvas', {
    type: 'canvas',
    displayName: 'Canvas',
    component: CanvasComponent,
    getInitialState: canvasLogic.getInitialState,
    updateState: canvasLogic.updateState, // Still needed for ChangeParentUpdate
    imperativeUpdate: true,
});

// Register new components
registry.set('label', {
    type: 'label',
    displayName: 'Label',
    component: LabelComponent,
    getInitialState: labelLogic.getInitialState,
    updateState: labelLogic.updateState,
    imperativeUpdate: false,
    isContainer: false,
});

registry.set('button', {
    type: 'button',
    displayName: 'Button',
    component: ButtonComponent,
    getInitialState: buttonLogic.getInitialState,
    updateState: buttonLogic.updateState,
    imperativeUpdate: false,
    isContainer: false,
});

registry.set('textbox', {
    type: 'textbox',
    displayName: 'Textbox',
    component: TextboxComponent,
    getInitialState: textboxLogic.getInitialState,
    updateState: textboxLogic.updateState,
    imperativeUpdate: false,
    isContainer: false,
});

registry.set('markdown', {
    type: 'markdown',
    displayName: 'Markdown Content',
    component: MarkdownComponent,
    getInitialState: markdownLogic.getInitialState,
    updateState: markdownLogic.updateState,
    imperativeUpdate: false,
    isContainer: false,
});

registry.set('row', {
    type: 'row',
    displayName: 'Row Container',
    component: RowComponent,
    getInitialState: rowLogic.getInitialState,
    updateState: rowLogic.updateState,
    imperativeUpdate: false,
    isContainer: true, // Mark as container
});

registry.set('column', {
    type: 'column',
    displayName: 'Column Container',
    component: ColumnComponent,
    getInitialState: columnLogic.getInitialState,
    updateState: columnLogic.updateState,
    imperativeUpdate: false,
    isContainer: true, // Mark as container
});

export const componentRegistry = registry;

console.log('Component Registry initialized with types:', Array.from(componentRegistry.entries()).map(([key, value]) => ({ type: key, imperative: !!value.imperativeUpdate, isContainer: !!value.isContainer })));