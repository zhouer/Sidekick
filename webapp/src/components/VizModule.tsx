// Sidekick/webapp/src/components/VizModule.tsx
import React, { useState } from 'react';
import './VizModule.css';
import { VizRepresentation, VizState, VizDictKeyValuePair } from '../types';

// --- Define Props Interface ---
interface VizModuleProps {
    id: string; // Instance ID
    state: VizState;
}

// --- Change Highlighting Logic ---
const HIGHLIGHT_DURATION = 1500; // ms

function isVizDictKeyValuePair(item: any): item is VizDictKeyValuePair {
    return typeof item === 'object' && item !== null && 'key' in item && 'value' in item;
}

// --- Helper Rendering Components ---
interface RenderValueProps {
    data: VizRepresentation | any;
    depth: number;
    changeInfo?: { // Pass down entire changeInfo for more flexible highlighting
        change_type: string;
        change_details?: any;
        timestamp: number;
    };
    parentRepId?: string;
}

const RenderValue: React.FC<RenderValueProps> = React.memo(({ data, depth, changeInfo, parentRepId }) => {
    // --- Primitive Check ---
    if (data === null || typeof data !== 'object' || Array.isArray(data)) {
        let displayValue = String(data);
        let className = 'viz-value-primitive';
        if (typeof data === 'string') { displayValue = `"${displayValue}"`; className += ' viz-value-string'; }
        else if (typeof data === 'number') { className += ' viz-value-number'; }
        else if (typeof data === 'boolean') { className += ' viz-value-boolean'; }
        else if (data === null) { displayValue = 'None'; className += ' viz-value-none'; }
        else { className += ' viz-value-unknown-primitive'; }
        return <span className={className}>{displayValue}</span>;
    }

    // --- Assume VizRepresentation ---
    const rep = data as VizRepresentation;
    const repId = rep.id || `${parentRepId}_val_${depth}`;
    const [isExpanded, setIsExpanded] = useState(depth < 1);

    const isRecent = changeInfo && (Date.now() - changeInfo.timestamp < HIGHLIGHT_DURATION);
    // Highlight the whole node if change type is 'observable_update' or 'replace'
    let nodeHighlightClass = isRecent && ['observable_update', 'replace'].includes(changeInfo?.change_type ?? '') ? ' viz-highlight-node' : '';

    // Safely calculate typeClassName
    let typeClassName = 'viz-type-unknown';
    if (typeof rep.type === 'string') {
        typeClassName = `viz-type-${rep.type.split(' ')[0].toLowerCase()}`;
    } else { console.warn("VizModule: Rep type is not string:", rep); }

    const toggleExpand = (e: React.MouseEvent) => { e.stopPropagation(); setIsExpanded(!isExpanded); };

    const isExpandable = typeof rep.type === 'string' &&
        (rep.type === 'list' || rep.type === 'dict' || rep.type === 'set' || rep.type.startsWith('object')) &&
        rep.length !== undefined && rep.length > 0;

    return (
        // Use observable_tracked class
        <div className={`viz-value-container ${typeClassName}${rep.observable_tracked ? ' observable-tracked' : ''}${nodeHighlightClass}`} id={repId}>
            {isExpandable && (
                <button onClick={toggleExpand} className="viz-expand-button" aria-expanded={isExpanded}>
                    {isExpanded ? '▼' : '▶'}
                </button>
            )}
            <span className="viz-type-indicator">
            {typeof rep.type === 'string' ? rep.type : 'unknown'}
                {rep.length !== undefined ? `[${rep.length}]` : ''}:
        </span>

            {/* --- Render List --- */}
            {isExpanded && typeof rep.type === 'string' && rep.type === 'list' && Array.isArray(rep.value) && (
                <div className="viz-list">
                    {rep.value.map((item: VizRepresentation | any, index: number) => {
                        // Highlight based on original change type stored potentially in details (if backend sent it)
                        // For now, just highlight if parent node was recently updated by observable
                        const itemHighlightClass = nodeHighlightClass ? ' viz-highlight-item' : ''; // Simple highlight propagation
                        const itemId = (item as VizRepresentation)?.id || `${repId}_item_${index}`;
                        return (
                            <div key={itemId} className={`viz-list-item ${itemHighlightClass}`}>
                                <span className="viz-list-index">{index}:</span>
                                <RenderValue data={item} depth={depth + 1} changeInfo={changeInfo} parentRepId={repId} />
                            </div>
                        );
                    })}
                </div>
            )}
            {/* --- Render Set --- */}
            {isExpanded && typeof rep.type === 'string' && rep.type === 'set' && Array.isArray(rep.value) && (
                <div className="viz-list viz-set">
                    {rep.value.map((item: VizRepresentation | any, index: number) => {
                        const itemHighlightClass = nodeHighlightClass ? ' viz-highlight-item' : ''; // Simple propagation
                        const itemId = (item as VizRepresentation)?.id || `${repId}_setitem_${index}`;
                        return (
                            <div key={itemId} className={`viz-list-item viz-set-item ${itemHighlightClass}`}>
                                <RenderValue data={item} depth={depth + 1} changeInfo={changeInfo} parentRepId={repId} />
                            </div>
                        );
                    })}
                </div>
            )}
            {/* --- Render Dict --- */}
            {isExpanded && typeof rep.type === 'string' && rep.type === 'dict' && Array.isArray(rep.value) && (
                <div className="viz-dict">
                    {rep.value.map((pair: any, index: number) => {
                        if (!isVizDictKeyValuePair(pair)) { return <div key={index} className="viz-dict-item viz-error">Invalid dict pair data</div>; }
                        const keyRep = pair.key;
                        const valueRep = pair.value;
                        const keyId = keyRep.id || `${repId}_key_${index}`;
                        const itemHighlightClass = nodeHighlightClass ? ' viz-highlight-item' : ''; // Simple propagation

                        return (
                            <div key={keyId} className={`viz-dict-item ${itemHighlightClass}`}>
                    <span className="viz-dict-key">
                        <RenderValue data={keyRep} depth={depth + 1} changeInfo={changeInfo} parentRepId={repId} />:
                    </span>
                                <RenderValue data={valueRep} depth={depth + 1} changeInfo={changeInfo} parentRepId={repId} />
                            </div>
                        );
                    })}
                </div>
            )}
            {/* --- Render Object --- */}
            {isExpanded && typeof rep.type === 'string' && rep.type.startsWith('object') && typeof rep.value === 'object' && rep.value !== null && (
                <div className="viz-dict viz-object">
                    {Object.entries(rep.value).map(([attrName, attrValueRep]) => {
                        const attrId = (attrValueRep as VizRepresentation)?.id || `${repId}_attr_${attrName}`;
                        const itemHighlightClass = nodeHighlightClass ? ' viz-highlight-item' : ''; // Simple propagation

                        return (
                            <div key={attrId} className={`viz-dict-item viz-object-item ${itemHighlightClass}`}>
                                <span className="viz-dict-key viz-attr-name">.{attrName}:</span>
                                <RenderValue data={attrValueRep as VizRepresentation} depth={depth + 1} changeInfo={changeInfo} parentRepId={repId} />
                            </div>
                        );
                    })}
                </div>
            )}

            {/* Render primitive value inside 'rep' or collapsed view */}
            {(!isExpanded || !isExpandable) && (
                <RenderValue data={rep.value} depth={depth + 1} changeInfo={changeInfo} parentRepId={repId} />
            )}
        </div>
    );
});

// --- Main Viz Module Component ---
const VizModule: React.FC<VizModuleProps> = ({ id, state }) => {
    const { variables, lastChanges } = state || { variables: {}, lastChanges: {} };
    const sortedVarNames = Object.keys(variables).sort();

    return (
        <div className="viz-module-container">
            <h3>Variable Visualizer: {id}</h3>
            <div className="viz-variable-list">
                {sortedVarNames.length === 0 && (
                    <p className="viz-empty-message">No variables shown yet. Use `viz.show('var_name', var_value)` in Python.</p>
                )}
                {sortedVarNames.map(varName => {
                    const representation = variables[varName];
                    if (!representation || typeof representation !== 'object' || representation === null || !representation.id) {
                        console.warn(`Invalid representation for var: ${varName}`, representation);
                        return (<div key={varName} className="viz-variable-item viz-error">Error</div>);
                    }
                    const changeInfo = lastChanges[varName];
                    return (
                        <div key={varName} className={`viz-variable-item`}>
                            <span className="viz-variable-name">{varName} =</span>
                            <RenderValue data={representation} depth={0} changeInfo={changeInfo} parentRepId={id} />
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default VizModule;