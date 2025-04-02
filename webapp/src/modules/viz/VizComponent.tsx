// Sidekick/webapp/src/modules/viz/VizComponent.tsx
import React, { useState, useMemo } from 'react';
import './VizComponent.css';
import { VizRepresentation, VizDictKeyValuePair, Path, VizChangeInfo, VizState } from './types';

// --- Constants ---
const HIGHLIGHT_DURATION = 1500; // ms, Duration for the highlight animation

// --- Define Props Interface ---
interface VizComponentProps {
    id: string; // Instance ID
    state: VizState; // State specific to the Viz module
}

// --- Type Guards & Helpers ---
// Check if an item is a dictionary key-value pair representation
function isVizDictKeyValuePair(item: any): item is VizDictKeyValuePair {
    return typeof item === 'object' && item !== null && 'key' in item && 'value' in item;
}
// Compare two path arrays for equality
function pathsAreEqual(path1: Path, path2: Path): boolean {
    if (!path1 || !path2 || path1.length !== path2.length) return false;
    for (let i = 0; i < path1.length; i++) { if (path1[i] !== path2[i]) return false; }
    return true;
}

// --- Recursive Helper Rendering Component ---
interface RenderValueProps {
    data: VizRepresentation | any; // The data node to render
    currentPath: Path;             // The path to reach this node from the root variable
    lastChangeInfo?: VizChangeInfo;// Information about the last change event for the root variable
    depth: number;                 // Current recursion depth
    parentRepId?: string;          // ID of the parent representation (for generating unique keys)
}

const RenderValue: React.FC<RenderValueProps> = React.memo(({ data, currentPath, lastChangeInfo, depth, parentRepId }) => {
    // --- Handle non-VizRepresentation data (e.g., primitive values used directly) ---
    if (data === null || typeof data !== 'object' || !('id' in data && 'type' in data && 'value' in data)) {
        let displayValue = String(data); let className = 'viz-value-primitive';
        if (typeof data === 'string') { displayValue = `"${displayValue}"`; className += ' viz-value-string'; }
        else if (typeof data === 'number') { className += ' viz-value-number'; }
        else if (typeof data === 'boolean') { className += ' viz-value-boolean'; }
        else if (data === null) { displayValue = 'None'; className += ' viz-value-none'; }
        else { displayValue = `?? ${displayValue}`; className += ' viz-value-unknown-primitive'; }
        return <span className={className}>{displayValue}</span>;
    }

    // --- Handle VizRepresentation objects ---
    const rep = data as VizRepresentation;
    // Ensure a unique ID for React keys, falling back if needed
    const repId = rep.id || `${parentRepId}_val_${depth}_${Math.random()}`;
    // Local state for expand/collapse functionality
    const [isExpanded, setIsExpanded] = useState(depth < 1); // Initially expand top levels

    // --- Highlighting Logic ---
    // Check if the last change occurred recently
    const isRecent = lastChangeInfo && (Date.now() - lastChangeInfo.timestamp < HIGHLIGHT_DURATION);
    // Check if the current node's path matches the path of the recent change
    const shouldHighlight = isRecent && lastChangeInfo && pathsAreEqual(lastChangeInfo.path, currentPath);
    // Class for CSS animation
    const highlightClass = shouldHighlight ? ' viz-highlight-node' : '';
    // Dynamic key to force re-mount and restart animation when highlighted
    const dynamicKey = shouldHighlight && lastChangeInfo ? `${repId}-${lastChangeInfo.timestamp}` : repId;

    // Determine CSS class based on representation type
    let typeClassName = 'viz-type-unknown';
    if (typeof rep.type === 'string') {
        // Generate a CSS-friendly class name from the type string
        typeClassName = `viz-type-${rep.type.split(' ')[0].toLowerCase().replace(/[^a-z0-9]/g, '-')}`;
    } else { console.warn("VizModule: Rep type is not string:", rep); }

    // Toggle expand/collapse state
    const toggleExpand = (e: React.MouseEvent) => { e.stopPropagation(); setIsExpanded(!isExpanded); };

    // Determine if the value itself can be expanded (is a container)
    const isValueExpandable = Array.isArray(rep.value) || (typeof rep.value === 'object' && rep.value !== null);
    // Check if the representation type suggests it's expandable and has content
    const hasLength = rep.length !== undefined && rep.length > 0;
    const canExpand = (rep.type === 'list' || rep.type === 'dict' || rep.type === 'set' || rep.type.startsWith('object')) && isValueExpandable && hasLength;

    return (
        // Use dynamicKey for potential re-mount on highlight
        <div key={dynamicKey} className={`viz-value-container ${typeClassName}${
            // FIX: Use camelCase 'observableTracked'
            rep.observableTracked ? ' observable-tracked' : ''
        }${highlightClass}`} id={repId}>

            {/* Expand/Collapse Button */}
            {canExpand && (<button onClick={toggleExpand} className="viz-expand-button" aria-expanded={isExpanded}>{isExpanded ? '▼' : '▶'}</button>)}

            {/* Type Indicator (e.g., list[3], dict[2], int) */}
            <span className="viz-type-indicator">
                {typeof rep.type === 'string' ? rep.type : 'unknown'}
                {/* Show length for containers */}
                {rep.length !== undefined ? `[${rep.length}]` : ''}
                {/* Add colon for non-expandable primitives (unless None) */}
                {!canExpand && rep.type !== 'NoneType' && typeof rep.value !== 'object' ? ':' : ''}
            </span>

            {/* Render primitive value inline if not expandable or collapsed */}
            {(!canExpand || !isExpanded) && rep.type !== 'NoneType' && typeof rep.value !== 'object' && (
                <span className="viz-value-inline">
                    {/* Recursively render the primitive value itself */}
                    <RenderValue data={rep.value} currentPath={[...currentPath, '(primitive_value)']} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} />
                </span>
            )}

            {/* --- Render Expanded Container Content --- */}
            {/* List */}
            {isExpanded && canExpand && rep.type === 'list' && Array.isArray(rep.value) && (
                <div className="viz-list">
                    {rep.value.map((item, index) => (
                        <div key={index} className={`viz-list-item`}>
                            <span className="viz-list-index">{index}:</span>
                            {/* Recurse for list item, appending index to path */}
                            <RenderValue data={item} currentPath={[...currentPath, index]} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} />
                        </div>
                    ))}
                </div>
            )}
            {/* Set */}
            {isExpanded && canExpand && rep.type === 'set' && Array.isArray(rep.value) && (
                // Sets are represented as sorted arrays, render similarly to lists but without index prefix
                <div className="viz-list viz-set">
                    {rep.value.map((item, index) => {
                        // Use item's ID or index as path segment for sets (less precise highlighting)
                        const itemPathSegment = (item as VizRepresentation)?.id || `set_item_${index}`;
                        return (
                            <div key={index} className={`viz-list-item viz-set-item`}>
                                {/* Recurse for set item */}
                                <RenderValue data={item} currentPath={[...currentPath, itemPathSegment]} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} />
                            </div>
                        );
                    })}
                </div>
            )}
            {/* Dictionary */}
            {isExpanded && canExpand && rep.type === 'dict' && Array.isArray(rep.value) && (
                <div className="viz-dict">
                    {rep.value.map((pair: any, index: number) => {
                        if (!isVizDictKeyValuePair(pair)) { return <div key={`error_${index}`} className="viz-dict-item viz-error">Invalid dict pair</div>; }
                        const keyRep = pair.key;
                        const valueRep = pair.value;
                        // Use key's primitive value or ID as path segment
                        const keySegment = keyRep?.value !== undefined ? keyRep.value : keyRep?.id || `dict_key_${index}`;
                        const itemKey = keyRep?.id || `dict_item_${index}`; // Unique key for React list
                        return (
                            <div key={itemKey} className={`viz-dict-item`}>
                                {/* Render key */}
                                <span className="viz-dict-key">
                                    {/* Recurse for key, adding '(key)' to path for distinction */}
                                    <RenderValue data={keyRep} currentPath={[...currentPath, keySegment, '(key)']} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} />
                                </span>
                                {/* Render value */}
                                {/* Recurse for value, using keySegment in path */}
                                <RenderValue data={valueRep} currentPath={[...currentPath, keySegment]} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} />
                            </div>
                        );
                    })}
                </div>
            )}
            {/* Object Attributes */}
            {isExpanded && canExpand && rep.type.startsWith('object') && typeof rep.value === 'object' && rep.value !== null && !Array.isArray(rep.value) && (
                <div className="viz-dict viz-object">
                    {/* Iterate over object attributes */}
                    {Object.entries(rep.value).map(([attrName, attrValueRep]) => (
                        <div key={attrName} className={`viz-dict-item viz-object-item`}>
                            {/* Render attribute name */}
                            <span className="viz-dict-key viz-attr-name">.{attrName}</span>
                            {/* Recurse for attribute value, using attrName in path */}
                            <RenderValue data={attrValueRep as VizRepresentation} currentPath={[...currentPath, attrName]} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} />
                        </div>
                    ))}
                </div>
            )}
        </div> // End viz-value-container
    );
});
RenderValue.displayName = 'RenderValue'; // Add display name for React DevTools

// --- Main Viz Module Component ---
const VizComponent: React.FC<VizComponentProps> = ({ id, state }) => {
    // Ensure state exists before destructuring
    const { variables, lastChanges } = state || { variables: {}, lastChanges: {} };
    // Memoize sorted variable names to prevent recalculation on every render
    const sortedVarNames = useMemo(() => Object.keys(variables).sort(), [variables]);

    return (
        <div className="module-card">
            <h3>Variable Visualizer: {id}</h3>
            <div className="viz-variable-list">
                {/* Handle empty state */}
                {sortedVarNames.length === 0 && (
                    <p className="viz-empty-message">No variables shown yet.</p>
                )}
                {/* Render each variable */}
                {sortedVarNames.map(varName => {
                    const representation = variables[varName];
                    // Basic validation for representation structure
                    if (!representation || typeof representation !== 'object' || representation === null || !('id' in representation)) {
                        return (<div key={varName} className="viz-variable-item viz-error">Error displaying variable '{varName}'</div>);
                    }
                    const changeInfo = lastChanges[varName];
                    return (
                        <div key={varName} className={`viz-variable-item`}>
                            <span className="viz-variable-name">{varName} =</span>
                            {/* Render the top-level value representation */}
                            <RenderValue data={representation} currentPath={[]} lastChangeInfo={changeInfo} depth={0} parentRepId={id} />
                        </div>
                    );
                })}
            </div>
        </div>
    );
};

export default VizComponent;