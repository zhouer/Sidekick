// Sidekick/webapp/src/components/VizModule.tsx
import React, { useState, useMemo } from 'react';
import './VizModule.css';
// Removed VizState import, added VizModuleProps definition
import { VizRepresentation, /* Removed VizState here */ VizDictKeyValuePair, Path, VizChangeInfo, VizState } from '../types';

// --- Constants ---
const HIGHLIGHT_DURATION = 1500; // ms

// --- Define Props Interface (THIS WAS MISSING) ---
interface VizModuleProps {
    id: string; // Instance ID
    state: VizState; // Use VizState here
}


// --- Type Guards & Helpers ---
function isVizDictKeyValuePair(item: any): item is VizDictKeyValuePair {
    return typeof item === 'object' && item !== null && 'key' in item && 'value' in item;
}
function pathsAreEqual(path1: Path, path2: Path): boolean {
    if (path1.length !== path2.length) return false;
    for (let i = 0; i < path1.length; i++) { if (path1[i] !== path2[i]) return false; }
    return true;
}

// --- Helper Rendering Components (no changes) ---
interface RenderValueProps {
    data: VizRepresentation | any;
    currentPath: Path;
    lastChangeInfo?: VizChangeInfo;
    depth: number;
    parentRepId?: string;
}

const RenderValue: React.FC<RenderValueProps> = React.memo(({ data, currentPath, lastChangeInfo, depth, parentRepId }) => {
    // Primitive Check
    if (data === null || typeof data !== 'object' || !('id' in data && 'type' in data && 'value' in data)) {
        let displayValue = String(data); let className = 'viz-value-primitive';
        if (typeof data === 'string') { displayValue = `"${displayValue}"`; className += ' viz-value-string'; }
        else if (typeof data === 'number') { className += ' viz-value-number'; }
        else if (typeof data === 'boolean') { className += ' viz-value-boolean'; }
        else if (data === null) { displayValue = 'None'; className += ' viz-value-none'; }
        else { displayValue = `?? ${displayValue}`; className += ' viz-value-unknown-primitive'; }
        return <span className={className}>{displayValue}</span>;
    }

    // Assume VizRepresentation
    const rep = data as VizRepresentation; const repId = rep.id || `${parentRepId}_val_${depth}_${Math.random()}`;
    const [isExpanded, setIsExpanded] = useState(depth < 1);

    // Determine highlight and key
    const isRecent = lastChangeInfo && (Date.now() - lastChangeInfo.timestamp < HIGHLIGHT_DURATION);
    const shouldHighlight = isRecent && lastChangeInfo && pathsAreEqual(lastChangeInfo.path, currentPath);
    const highlightClass = shouldHighlight ? ' viz-highlight-node' : '';
    const dynamicKey = shouldHighlight && lastChangeInfo ? `${repId}-${lastChangeInfo.timestamp}` : repId;

    let typeClassName = 'viz-type-unknown'; if (typeof rep.type === 'string') { typeClassName = `viz-type-${rep.type.split(' ')[0].toLowerCase().replace(/[^a-z0-9]/g, '-')}`; } else { console.warn("VizModule: Rep type is not string:", rep); }
    const toggleExpand = (e: React.MouseEvent) => { e.stopPropagation(); setIsExpanded(!isExpanded); };
    const isValueExpandable = Array.isArray(rep.value) || (typeof rep.value === 'object' && rep.value !== null);
    const hasLength = rep.length !== undefined && rep.length > 0;
    const canExpand = (rep.type === 'list' || rep.type === 'dict' || rep.type === 'set' || rep.type.startsWith('object')) && isValueExpandable && hasLength;

    return (
        <div key={dynamicKey} className={`viz-value-container ${typeClassName}${rep.observable_tracked ? ' observable-tracked' : ''}${highlightClass}`} id={repId}>
            {canExpand && (<button onClick={toggleExpand} className="viz-expand-button" aria-expanded={isExpanded}>{isExpanded ? '▼' : '▶'}</button>)}
            <span className="viz-type-indicator">{typeof rep.type === 'string' ? rep.type : 'unknown'}{rep.length !== undefined ? `[${rep.length}]` : ''}{!canExpand && rep.type !== 'NoneType' && typeof rep.value !== 'object' ? ':' : ''}</span>
            {(!canExpand || !isExpanded) && rep.type !== 'NoneType' && typeof rep.value !== 'object' && (<span className="viz-value-inline"><RenderValue data={rep.value} currentPath={[...currentPath, '(primitive_value)']} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} /></span>)}
            {isExpanded && canExpand && rep.type === 'list' && Array.isArray(rep.value) && (<div className="viz-list">{rep.value.map((item, index) => (<div key={index} className={`viz-list-item`}><span className="viz-list-index">{index}:</span><RenderValue data={item} currentPath={[...currentPath, index]} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} /></div>))}</div>)}
            {isExpanded && canExpand && rep.type === 'set' && Array.isArray(rep.value) && (<div className="viz-list viz-set">{rep.value.map((item, index) => { const itemPathSegment = (item as VizRepresentation)?.id || `set_item_${index}`; return (<div key={index} className={`viz-list-item viz-set-item`}><RenderValue data={item} currentPath={[...currentPath, itemPathSegment]} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} /></div>); })}</div>)}
            {isExpanded && canExpand && rep.type === 'dict' && Array.isArray(rep.value) && (<div className="viz-dict">{rep.value.map((pair: any, index: number) => { if (!isVizDictKeyValuePair(pair)) { return <div key={`error_${index}`} className="viz-dict-item viz-error">Invalid dict pair</div>; } const keyRep = pair.key; const valueRep = pair.value; const keySegment = keyRep?.value !== undefined ? keyRep.value : keyRep?.id || `dict_key_${index}`; const itemKey = keyRep?.id || `dict_item_${index}`; return (<div key={itemKey} className={`viz-dict-item`}><span className="viz-dict-key"><RenderValue data={keyRep} currentPath={[...currentPath, keySegment, '(key)']} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} />:</span><RenderValue data={valueRep} currentPath={[...currentPath, keySegment]} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} /></div>); })}</div>)}
            {isExpanded && canExpand && rep.type.startsWith('object') && typeof rep.value === 'object' && rep.value !== null && !Array.isArray(rep.value) && (<div className="viz-dict viz-object">{Object.entries(rep.value).map(([attrName, attrValueRep]) => (<div key={attrName} className={`viz-dict-item viz-object-item`}><span className="viz-dict-key viz-attr-name">.{attrName}:</span><RenderValue data={attrValueRep as VizRepresentation} currentPath={[...currentPath, attrName]} lastChangeInfo={lastChangeInfo} depth={depth + 1} parentRepId={repId} /></div>))}</div>)}
        </div>
    );
});

// --- Main Viz Module Component (no changes) ---
// Use the defined VizModuleProps interface
const VizModule: React.FC<VizModuleProps> = ({ id, state }) => {
    const { variables, lastChanges } = state || { variables: {}, lastChanges: {} };
    const sortedVarNames = useMemo(() => Object.keys(variables).sort(), [variables]);

    return (
        <div className="viz-module-container">
            <h3>Variable Visualizer: {id}</h3>
            <div className="viz-variable-list">
                {sortedVarNames.length === 0 && (<p className="viz-empty-message">No variables shown yet.</p>)}
                {sortedVarNames.map(varName => {
                    const representation = variables[varName];
                    if (!representation || typeof representation !== 'object' || representation === null || !('id' in representation)) { return (<div key={varName} className="viz-variable-item viz-error">Error display '{varName}'</div>); }
                    const changeInfo = lastChanges[varName];
                    return (
                        <div key={varName} className={`viz-variable-item`}>
                            <span className="viz-variable-name">{varName} =</span>
                            <RenderValue data={representation} currentPath={[]} lastChangeInfo={changeInfo} depth={0} parentRepId={id} />
                        </div>
                    );
                })}
            </div>
        </div>
    );
};
export default VizModule;