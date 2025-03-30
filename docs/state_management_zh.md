# Sidekick Web 應用程式: 狀態管理

## 1. 概觀 (Overview)

Sidekick Web 應用程式（`webapp/` 目錄下的 React 應用）的核心職責之一是管理所有視覺化模組（如 Grid, Console, Viz, Canvas）的當前狀態。這個狀態決定了使用者介面上顯示的內容。

狀態管理的主要機制是使用 React 的 **`useReducer` Hook**，配合一個中央的 **`moduleReducer` 函數** 來處理來自 Hero 端（Python 腳本）的指令，並以**不可變 (Immutable)** 的方式更新狀態。

## 2. 核心概念 (Core Concepts)

*   **React `useReducer` Hook:**
    *   這是 React 提供的狀態管理方案，適用於比 `useState` 更複雜的狀態邏輯。
    *   它包含三個主要部分：
        1.  **State:** 當前的狀態資料。在 Sidekick 中，這是一個 `Map`，儲存所有模組的狀態。
        2.  **Reducer Function (`moduleReducer`):** 一個純函數 (Pure Function)，接收當前的 `state` 和一個描述變化的 `action` 物件，並**返回一個全新的 state**。它定義了所有可能的狀態轉換邏輯。
        3.  **Dispatch Function (`dispatchModules`):** 一個函式，用於觸發狀態更新。我們呼叫 `dispatch` 並傳入一個 `action` 物件，React 會將當前 state 和這個 action 傳遞給 reducer 函數。
*   **不可變性 (Immutability):**
    *   這是 React 狀態管理的**黃金法則**。Reducer 函數**絕不能**直接修改 (Mutate) 傳入的 `state` 物件。它必須創建新的物件或陣列來反映變化。
    *   **原因:** React 依賴物件參考 (Reference) 的變化來偵測狀態是否更新，從而決定是否重新渲染元件。如果直接修改舊 state，參考不變，React 可能無法偵測到更新。
    *   **實現方式:** 在 reducer 中，通常使用展開運算子 (`...`) 或 `Map` 的方法（如 `new Map(state)`) 來創建副本，然後在副本上進行修改。對於深層嵌套的物件（如 `VizState` 中的 `variables`），需要遞迴地確保每一層都是新的物件/陣列（通常藉助輔助函式如 `updateRepresentationAtPath`）。
*   **單向資料流 (One-Way Data Flow):**
    *   狀態由頂層的 `App` 元件持有。
    *   狀態更新由來自 WebSocket 的訊息觸發，通過 `dispatch` 和 `reducer` 集中處理。
    *   更新後的狀態作為 `props` 向下傳遞給各個模組元件（`GridModule`, `VizModule` 等）。
    *   子元件不能直接修改狀態，只能透過呼叫傳遞下來的回呼函式（如 `onInteraction`）來觸發向 Hero 發送訊息，進而可能引起 Hero 發送新的更新指令。

## 3. 狀態結構 (State Structure)

應用的核心狀態定義在 `src/types/index.ts` 中，並由 `App.tsx` 中的 `useReducer` 管理。

*   **根狀態 (Root State):** `Map<string, ModuleInstance>`
    *   這是一個 JavaScript `Map` 物件。
    *   **鍵 (Key):** 模組實例的唯一 ID (`target` ID)，由 Hero 端產生並在 `spawn` 指令中指定。
    *   **值 (Value):** 一個 `ModuleInstance` 物件，代表該模組的完整狀態。

*   **`ModuleInstance` (定義於 `src/types/index.ts`):**
    *   這是一個**可辨識聯合類型 (Discriminated Union)**，用 `type` 欄位來區分不同的模組。
    *   所有 `ModuleInstance` 都包含 `id: string` 和 `type: ModuleType`。
    *   根據 `type` 的不同，它會包含一個特定的 `state` 物件：
        *   `GridModuleInstance`: `{ id: string; type: 'grid'; state: GridState; }`
        *   `ConsoleModuleInstance`: `{ id: string; type: 'console'; state: ConsoleState; }`
        *   `VizModuleInstance`: `{ id: string; type: 'viz'; state: VizState; }`
        *   `CanvasModuleInstance`: `{ id: string; type: 'canvas'; state: CanvasState; }`

*   **特定模組狀態 (`GridState`, `ConsoleState`, `VizState`, `CanvasState`):**
    *   **`GridState`:** 包含 `size: [number, number]` 和 `cells: { [key: string]: { ... } }` (儲存格狀態)。
    *   **`ConsoleState`:** 包含 `lines: string[]` (顯示的文字行)。
    *   **`VizState`:** 包含：
        *   `variables: { [name: string]: VizRepresentation }`：一個物件，映射變數名稱到其當前的視覺化表示 (`VizRepresentation`)。
        *   `lastChanges: { [name: string]: VizChangeInfo }`：一個物件，追蹤每個變數**最後一次更新**的詳細資訊（包括 `change_type`, `path`, `timestamp`），主要用於觸發前端的 highlight 動畫。
    *   **`CanvasState`:** 包含 `width`, `height`, `bgColor` 以及 `commandQueue: CanvasDrawCommand[]`（儲存待處理的繪圖指令佇列）。

## 4. 狀態更新流程 (State Update Flow)

狀態的更新總是從接收到來自 Hero 的 WebSocket 訊息開始：

1.  **訊息到達:** `useWebSocket` Hook 接收到一個 JSON 字串訊息，並將其解析為 JavaScript 物件。
2.  **呼叫回呼:** `useWebSocket` 呼叫傳遞給它的 `handleWebSocketMessage` 回呼函式（在 `App.tsx` 中定義）。
3.  **分發動作 (Dispatch Action):** `handleWebSocketMessage` 將收到的訊息包裝成一個 `action` 物件（例如 `{ type: 'PROCESS_MESSAGE', message: receivedMessage }`），並呼叫 `dispatchModules(action)`。
4.  **Reducer 執行 (`moduleReducer`):** React 將當前的 `state` (Map) 和剛剛 dispatch 的 `action` 傳遞給 `moduleReducer` 函數。
5.  **創建新狀態副本:** Reducer 首先創建一個當前 state Map 的副本：`const newModules = new Map(state);`。**之後的所有修改都在 `newModules` 上進行。**
6.  **處理動作類型:** Reducer 檢查 `action.type`。
    *   如果是 `CLEAR_ALL`，直接返回一個新的空 Map：`new Map()`.
    *   如果是 `PROCESS_MESSAGE`，則進一步處理訊息內容 (`action.message`)。
7.  **處理訊息方法 (`method`):** Reducer 根據訊息的 `method` ("spawn", "update", "remove") 執行不同邏輯：
    *   **`spawn`:**
        *   檢查 `target` ID 是否已存在，如果存在則忽略。
        *   根據 `moduleType` 和 `payload` 創建對應模組的**初始 state** 物件（如 `initialGridState`）。
        *   將新的 `ModuleInstance`（包含 ID, type, 和初始 state）添加到 `newModules` Map 中：`newModules.set(target, newModuleInstance);`。
    *   **`remove`:**
        *   檢查 `target` ID 是否存在於 `newModules` 中。
        *   如果存在，則從 `newModules` 中刪除該條目：`newModules.delete(target);`。
    *   **`update`:**
        *   根據 `target` ID 從 `newModules` 中找到對應的 `currentModule`。如果找不到則忽略。
        *   根據 `currentModule.type` 執行特定模組的更新邏輯：
            *   **Grid/Console/Canvas:** 讀取 `payload`，創建**新的** state 物件（例如，對於 Grid，創建新的 `cells` 物件；對於 Console，創建新的 `lines` 陣列；對於 Canvas，創建新的 `commandQueue` 陣列），然後用新的 state 更新 `newModules` 中的條目：`newModules.set(target, { ...currentModule, state: newSpecificState });`。
            *   **Viz:** 這是最複雜的。
                *   讀取 `payload` 中的 `variable_name`, `change_type`, `path` 等詳細資訊。
                *   如果 `change_type` 是 `"remove_variable"`，則從 `variables` Map 中移除對應變數。
                *   否則，呼叫 `updateRepresentationAtPath` 輔助函式。這個函式會接收**當前**變數的 `VizRepresentation` 和更新的詳細資訊 (`payload`)，並**遞迴地**創建一個**全新**的、已更新的 `VizRepresentation` 物件返回（保證了深層不可變性）。
                *   將返回的新的 `VizRepresentation` 更新到 `variables` Map 中。
                *   同時，更新 `lastChanges` Map，記錄這次變化的 `change_type`, `path` 和 `timestamp`，用於觸發 highlight。
                *   最後，用包含**新的 `variables` 和 `lastChanges` 物件**的 `VizState` 來更新 `newModules` 中的條目。
8.  **返回新狀態:** `moduleReducer` 返回修改後的 `newModules` Map。
9.  **React 更新:** React 比較舊 state Map 和 reducer 返回的新 state Map。由於我們總是返回一個新的 Map (或者原始的 Map 如果沒有變化)，React 會偵測到狀態變化（如果有的話），並觸發 `App` 元件以及依賴相關 state 的子元件重新渲染。

## 5. 關鍵檔案 (Key Files)

*   **`src/App.tsx`:** 包含 `useReducer` Hook 的初始化、`moduleReducer` 函數的定義，以及將 state 傳遞給子元件的邏輯。
*   **`src/types/index.ts`:** 定義所有狀態結構（`ModuleInstance`, `GridState`, `VizState` 等）和訊息/Payload 的 TypeScript 類型。是理解狀態形狀的關鍵。
*   **`src/utils/stateUtils.ts`:** 包含 `updateRepresentationAtPath` 等輔助函式，用於處理複雜的、深層的不可變狀態更新（主要是為 `Viz` 模組服務）。

## 6. 狀態如何傳遞給元件 (Data Flow to Components)

1.  `App` 元件持有從 `useReducer` 獲取的最新 `modules` 狀態 Map。
2.  在 `App` 的 `renderModules` 函數中，它遍歷 `modules` Map。
3.  對於 Map 中的每一個 `module` 實例，它根據 `module.type` 選擇渲染對應的元件（`GridModule`, `ConsoleModule` 等）。
4.  它將該模組的 `id` 和**完整的 `state` 物件** (`module.state`) 作為 `props` 傳遞給子元件。
    ```jsx
    // In App.tsx's renderModules
    case 'viz':
    // Pass the specific VizState object down as 'state' prop
    return <VizModule key={module.id} id={module.id} state={module.state as VizState} />;
    ```
5.  子元件（如 `VizModule`）在其 `props` 中接收到自己的 `state` 物件，並根據其中的資料來渲染 UI。

## 7. 選擇 `useReducer` 的理由 (Rationale)

*   **集中式邏輯:** 將所有狀態轉換邏輯集中在 `moduleReducer` 中，使得狀態變化更可預測、易於理解和除錯。
*   **可測試性:** Reducer 是純函數，易於進行單元測試。只需提供輸入的 state 和 action，斷言輸出的 state 是否符合預期。
*   **清晰的動作:** 使用帶有 `type` 和 `payload` 的 action 物件，使得狀態更新的意圖更加明確。
*   **處理複雜狀態:** 對於像 Sidekick 這樣可能有多個模組、多種互動方式的應用，`useReducer` 比多個 `useState` 更容易管理。

## 8. 注意事項 (Considerations)

*   **嚴格遵守不可變性:** 這是最重要也是最容易出錯的地方。任何時候修改 state，都必須確保返回的是新的物件/陣列/Map，尤其是在深層嵌套的結構中。`updateRepresentationAtPath` 這樣的工具是必要的。
*   **Reducer 效能:** Reducer 應該是相對快速的純函數。避免在 reducer 中執行副作用（如 API 呼叫、計時器等）或進行非常耗時的計算。
*   **狀態結構設計:** 良好的狀態結構（如使用 Map 和 Discriminated Union）對於 reducer 的清晰度和效率至關重要。