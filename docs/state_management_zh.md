# Sidekick Web 應用程式: 狀態管理

## 1. 概觀 (Overview)

Sidekick Web 應用程式（`webapp/` 目錄下的 React 應用）的核心職責之一是精確地管理所有視覺化模組（如 Grid, Console, Viz, Canvas）的當前狀態。這個狀態是使用者介面 (UI) 顯示內容的唯一來源 (Single Source of Truth)。

狀態管理採用了 React 的 **`useReducer` Hook** 作為核心機制，配合一個中央的 **`moduleReducer` 函數** 來處理來自 Hero 端（Python 腳本）透過 WebSocket 發送的指令。所有狀態的更新都遵循**不可變 (Immutable)** 原則，以確保 React 的高效渲染和狀態的可預測性。

## 2. 核心概念 (Core Concepts)

*   **React `useReducer` Hook:**
    *   適用於管理涉及多個子值或下一個 state 依賴於前一個 state 的複雜狀態邏輯。
    *   包含 **State** (當前的 `Map<string, ModuleInstance>`)、**Reducer Function** (`moduleReducer`) 和 **Dispatch Function** (`dispatchModules`)。
    *   工作流程：`Action` -> `dispatch(Action)` -> `Reducer(currentState, Action)` -> `newState`。
*   **不可變性 (Immutability):**
    *   Reducer **絕不**直接修改傳入的 `state`。它必須返回一個**全新的** state 物件或集合。
    *   這是 React 高效偵測變更並觸發渲染的基礎。
    *   透過展開運算子 (`...`)、`Map` 的建構子 (`new Map(state)`)、陣列方法 (`map`, `filter`, `concat`, `slice`) 或專門的輔助函式（如 `updateRepresentationAtPath`）來實現。
*   **單向資料流 (One-Way Data Flow):**
    *   狀態由頂層 `App` 元件集中管理。
    *   狀態更新由 WebSocket 訊息觸發 -> `dispatch` -> `Reducer`。
    *   更新後的狀態透過 `props` 向下流動到各個子模組元件。
    *   子元件透過回呼函式 (`onInteraction`) 觸發事件，請求 Hero 端進行操作（可能間接導致狀態更新）。

## 3. 狀態結構 (State Structure)

狀態的具體形狀定義在 `src/types/index.ts`，由 `App.tsx` 中的 `useReducer` 管理。

*   **根狀態 (Root State):** `Map<string, ModuleInstance>`
    *   鍵 (Key): 模組實例的唯一 ID (`target` ID)。
    *   值 (Value): `ModuleInstance` 物件，代表該模組的類型和具體狀態。

*   **`ModuleInstance` (Discriminated Union):**
    *   包含 `id: string` 和 `type: ModuleType`。
    *   根據 `type` 包含特定的 `state` 物件：
        *   `GridModuleInstance`: `{ ..., type: 'grid', state: GridState; }`
        *   `ConsoleModuleInstance`: `{ ..., type: 'console', state: ConsoleState; }`
        *   `VizModuleInstance`: `{ ..., type: 'viz', state: VizState; }`
        *   `CanvasModuleInstance`: `{ ..., type: 'canvas', state: CanvasState; }`

*   **特定模組狀態 (`GridState`, `ConsoleState`, `VizState`, `CanvasState`):**
    *   `GridState`: 包含 `size`, `cells`。
    *   `ConsoleState`: 包含 `lines`。
    *   **`VizState`:** (關鍵狀態)
        *   `variables: { [name: string]: VizRepresentation }`：儲存每個變數當前完整的視覺化表示。
        *   `lastChanges: { [name: string]: VizChangeInfo }`：儲存每個變數**最後一次更新事件**的資訊 (`change_type`, `path`, `timestamp`)，用於觸發 UI 高亮。**注意：** 這個欄位不儲存變數的實際值，只記錄變更事件本身。
    *   **`CanvasState`:** (關鍵狀態)
        *   包含 `width`, `height`, `bgColor`。
        *   `commandQueue: CanvasDrawCommand[]`：儲存從 Hero 端接收到的、**所有待處理**的繪圖指令物件的陣列。

## 4. 狀態更新流程 (State Update Flow) - `moduleReducer` 內部

當 `dispatchModules({ type: 'PROCESS_MESSAGE', message })` 被呼叫時，`moduleReducer` 執行以下步驟：

1.  **創建新狀態副本:** `const newModules = new Map(state);`
2.  **解析訊息:** 從 `message` 中獲取 `moduleType`, `method`, `target`, `payload`。
3.  **處理方法 (`method`):**
    *   **`spawn`:**
        *   檢查 ID 衝突。
        *   根據 `moduleType` 和 `payload` 創建模組的**初始 state** (例如 `CanvasState` 的 `commandQueue` 初始化為空陣列 `[]`)。
        *   `newModules.set(target, newModuleInstance);`
    *   **`remove`:**
        *   `newModules.delete(target);`
    *   **`update`:**
        *   找到 `currentModule = newModules.get(target)`。
        *   **根據 `currentModule.type` 處理:**
            *   **`grid` / `console`:** 創建**新的** `cells` 物件或 `lines` 陣列，更新 `newModules.set(target, { ..., state: newSpecificState });`。
            *   **`canvas`:**
                *   從 `payload` 中獲取繪圖指令 `canvasUpdate`。
                *   確保指令有唯一的 `commandId`。
                *   獲取當前的 `commandQueue`。
                *   **創建一個新的佇列陣列**，將新指令附加到末尾：`const updatedQueue = [...currentState.commandQueue, newCommand];`。
                *   更新 `newModules.set(target, { ..., state: { ..., commandQueue: updatedQueue } });`。
            *   **`viz`:**
                *   解析 `payload` 獲取 `variable_name`, `change_type`, `path` 等。
                *   創建 `variables` 和 `lastChanges` 的**新副本** (`newVariablesState`, `newLastChanges`)。
                *   **如果 `change_type === "remove_variable"`:** 從 `newVariablesState` 中 `delete` 對應的 `variable_name`。
                *   **否則 (如果是其他更新類型):**
                    *   確保 `variable_name` 存在於 `newVariablesState` 中 (或允許 `change_type === "set"` 創建它)。
                    *   呼叫 `updateRepresentationAtPath(currentState.variables[variable_name], vizPayload)`。此函式會**遞迴地複製並更新**變數的視覺化表示，返回一個**全新**的 `VizRepresentation` 物件。
                    *   將返回的新表示賦值給 `newVariablesState[variable_name]`。
                *   **更新 `lastChanges`:**
                    *   如果變數被移除，則從 `newLastChanges` 中 `delete` 對應條目。
                    *   否則，在 `newLastChanges` 中更新或新增 `variable_name` 對應的條目，儲存當前的 `change_type`, `path` 和 `Date.now()` 時間戳。
                *   更新 `newModules.set(target, { ..., state: { variables: newVariablesState, lastChanges: newLastChanges } });`。
4.  **返回新狀態:** `return newModules;`
5.  **React 渲染:** React 比較 state，觸發 `App` 和相關子元件的重新渲染。

## 5. 關鍵檔案 (Key Files)

*   **`src/App.tsx`:** 包含 `useReducer` Hook 和 `moduleReducer` 函數。
*   **`src/types/index.ts`:** 定義狀態結構 (`ModuleInstance`, `VizState`, `CanvasState` 等)。
*   **`src/utils/stateUtils.ts`:** 包含 `updateRepresentationAtPath` 等處理不可變更新的輔助函式（主要為 Viz）。

## 6. 狀態如何傳遞給元件 (Data Flow to Components)

`App` 元件將 `modules` Map 中的每個 `module.state` 物件作為 `prop` 傳遞給對應的子元件（`GridModule`, `ConsoleModule`, `VizModule`, `CanvasModule`）。子元件讀取這些 props 來渲染 UI。

## 7. 選擇 `useReducer` 的理由 (Rationale)

*   **集中式邏輯:** 使複雜的狀態轉換易於管理和除錯。
*   **可測試性:** Reducer 是純函數，便於測試。
*   **清晰的動作:** `Action` 物件明確表達了更新意圖。
*   **處理複雜性:** 比多個 `useState` 更適合管理多模組、多互動的狀態。

## 8. 注意事項 (Considerations)

*   **不可變性:** 必須始終返回新的狀態物件/陣列/Map。尤其注意 `Viz` 的深層更新。
*   **Reducer 效能:** 保持 Reducer 快速且無副作用。
*   **狀態設計:** 合理的狀態結構（如 Map, Discriminated Union, `VizState` 的拆分）對可維護性很重要。
*   **`lastChanges` 的目的:** `VizState.lastChanges` **不**儲存變數的歷史記錄，它只記錄**最後一次**更新事件的元數據，目的是為了**觸發 UI 高亮**。UI 高亮邏輯本身在 `VizModule.tsx` 中，它比較 `lastChanges` 中的路徑和時間戳。
*   **`commandQueue` 的處理:** `CanvasState.commandQueue` 由 Reducer 填充，但實際的繪圖處理和佇列消耗邏輯在 `CanvasModule.tsx` 元件內部完成。