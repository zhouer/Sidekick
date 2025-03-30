# Sidekick 通訊協定規格書

## 1. 簡介

本文件詳細說明了 **Hero 端**（使用者執行、使用了 `sidekick` Python 函式庫的腳本）與 **Sidekick 前端**（React 應用程式）之間的通訊協定。此協定讓 Hero 端能夠控制 Sidekick UI 中的視覺化模組，並允許 Sidekick 將通知傳回 Hero 端。

## 2. 傳輸層 (Transport Layer)

*   **機制:** WebSocket
*   **預設端點:** `ws://localhost:5163` (可透過 Python 中的 `sidekick.set_url()` 進行設定)。
*   **編碼:** JSON 字串 (使用 UTF-8 編碼)。
*   **連線維持 (Keep-Alive):** Python 客戶端使用 WebSocket 的 Ping/Pong 訊框來維護連線並偵測連線失敗。伺服器應回應 Ping 訊框以 Pong 訊框。

## 3. 訊息格式 (Message Format)

所有在 Hero 和 Sidekick 之間交換的訊息都共用一個基礎的 JSON 結構。

### 3.1 Hero -> Sidekick 訊息結構

這些是從 Hero 腳本發送，用來控制 Sidekick UI 模組的指令。

```json
{
"id": number,       // 保留供未來使用 (例如訊息追蹤)。目前預設為 0。
"module": string,   // 目標模組的類型 (例如 "grid", "console", "viz", "canvas")。
"method": string,   // 要執行的動作 ("spawn", "update", "remove")。
"target": string,   // 目標模組實例的唯一識別碼。
"payload": object | null // 根據方法和模組類型而定的特定資料。如果不需要則為 null。
}
```

### 3.2 Sidekick -> Hero 訊息結構

這些是從 Sidekick UI 發送回 Hero 腳本的通知或錯誤報告。

```json
{
"id": number,       // 保留供未來使用。目前預設為 0。
"module": string,   // 產生此訊息的來源模組類型 (例如 "grid", "console")。
"method": string,   // 訊息的類型 ("notify", "error")。
"src": string,      // 來源模組實例的唯一識別碼。
"payload": object | null // 根據通知或錯誤而定的特定資料。
}
```

### 3.3 欄位說明 (Field Descriptions)

*   `id` (整數 Integer): 保留欄位。預設為 `0`。未來版本可能用於請求/回應的配對。
*   `module` (字串 String): 指明涉及的模組類型（例如 `"grid"`, `"console"`, `"viz"`, `"canvas"`）。
*   `method` (字串 String): 指定要執行的動作（用於 Hero->Sidekick）或訊息的類型（用於 Sidekick->Hero）。
*   `target` (字串 String): **僅用於 Hero -> Sidekick。** 應處理此指令的模組實例的唯一 ID。
*   `src` (字串 String): **僅用於 Sidekick -> Hero。** 產生此訊息的模組實例的唯一 ID。
*   `payload` (物件 Object | Null): 包含特定於方法的資料結構，詳見第 5 節。

## 4. 核心方法 (Core Methods)

這些定義了透過 `method` 欄位進行的主要互動。

### 4.1 Hero -> Sidekick 方法

*   **`spawn`**: 指示 Sidekick 建立並顯示一個指定模組類型的新實例。`payload` 包含該模組的初始設定。
*   **`update`**: 指示 Sidekick 修改一個現有模組實例（由 `target` 指定）的狀態。`payload` 包含要套用的具體變更。對於 `viz` 模組，此方法處理所有變數的新增、更新和移除。
*   **`remove`**: 指示 Sidekick 銷毀並從 UI 中移除一個特定的模組實例（由 `target` 指定）。

### 4.2 Sidekick -> Hero 方法

*   **`notify`**: 由互動式模組（如 `grid` 或 `console`）發送，用於告知 Hero 使用者的操作（例如，點擊儲存格、提交文字輸入）。`payload` 包含事件的詳細資訊。
*   **`error`**: 如果 Sidekick 在處理指令或管理模組時遇到錯誤（例如，無效的 payload、找不到模組），則會發送此訊息。`payload` 通常包含錯誤訊息。

## 5. 特定模組的 Payload (`payload` 結構)

本節詳細說明了不同 `module` 和 `method` 組合下，`payload` 物件預期的結構。

### 5.1 模組: `grid`

*   **`spawn` Payload:**
    ```json
    { "size": [width: number, height: number] }
    ```
*   **`update` Payload (選擇一種格式):**
    *   更新單一儲存格:
        ```json
        {
        "x": number,
        "y": number,
        "color"?: string | null, // 可選: 新的背景顏色 (null 可能表示清除？)
        "text"?: string | null   // 可選: 新的文字內容 (null 表示清除？)
        }
        ```
    *   填滿整個網格:
        ```json
        { "fill_color": string } // 用於填滿所有儲存格的顏色
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    { "event": "click", "x": number, "y": number }
    ```

### 5.2 模組: `console`

*   **`spawn` Payload:**
    ```json
    { "text"?: string } // 可選的初始文字行
    ```
*   **`update` Payload (選擇一種格式):**
    *   附加文字:
        ```json
        { "text": string } // 要附加的文字 (可包含換行符)
        ```
    *   清除主控台:
        ```json
        { "clear": true }
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    { "event": "submit", "value": string } // 使用者提交的文字
    ```

### 5.3 模組: `viz`

*   **`spawn` Payload:**
    ```json
    {} // spawn 時不需要特定的 payload
    ```
*   **`update` Payload:** 這一個方法處理變數的新增、更新和移除。
    ```json
    {
    "variable_name": string,                 // 要操作的變數名稱
    "change_type": string,                   // 變更類型: "set", "setitem", "append", "pop", "insert", "delitem", "remove", "add_set", "discard_set", "clear", "remove_variable"
    "path": Array<string | number>,          // 變數結構內發生變更的路徑。`[]` 表示根變數本身。
    "value_representation": VizRepresentation | null, // 新值的表示 (或新增的元素、清除後的容器)。若不適用則為 null (例如 remove_variable, pop, delitem)。詳見第 6 節。
    "key_representation"?: VizRepresentation | null,   // 可選: 涉及字典操作 (setitem, delitem) 時的鍵的表示。
    "length"?: number | null                   // 可選: 操作後容器的新長度。
    }
    ```

### 5.4 模組: `canvas`

*   **`spawn` Payload:**
    ```json
    {
    "width": number,          // 畫布寬度 (像素)
    "height": number,         // 畫布高度 (像素)
    "bgColor"?: string        // 可選: 初始背景顏色 (CSS 格式)
    }
    ```
*   **`update` Payload:** 代表一個繪圖或設定指令。
    ```json
    {
    "command": string,        // 指令名稱: "clear", "config", "line", "rect", "circle"
    "options": object,        // 指令的特定參數 (見下文)
    "commandId": string | number // 此指令實例的唯一 ID (由 Hero 或 Sidekick 確保)
    }
    ```
    *   **`command: "clear"` Options:** `{ "color"?: string }` (可選顏色，預設為背景色)
    *   **`command: "config"` Options:** `{ "strokeStyle"?: string, "fillStyle"?: string, "lineWidth"?: number }`
    *   **`command: "line"` Options:** `{ "x1": number, "y1": number, "x2": number, "y2": number }`
    *   **`command: "rect"` Options:** `{ "x": number, "y": number, "width": number, "height": number, "filled"?: boolean }`
    *   **`command: "circle"` Options:** `{ "cx": number, "cy": number, "radius": number, "filled"?: boolean }`

## 6. 資料表示 (`VizRepresentation`)

這個標準的 JSON 結構用於 `viz` 模組 `update` 訊息的 `payload` 中（特別是 `value_representation` 和 `key_representation` 欄位），目的是將 Python 資料序列化以供前端顯示。

一個 `VizRepresentation` 是一個包含以下欄位的 JSON 物件：

*   `type` (字串 String): Python 的類型名稱 (例如 `"int"`, `"list"`, `"dict"`, `"set"`, `"NoneType"`) 或特殊的類型識別符 (例如 `"object (ClassName)"`, `"repr (ClassName)"`, `"truncated"`, `"error"`, `"recursive_ref"`)。
*   `id` (字串 String): 這個特定資料節點表示的唯一識別碼 (例如 `"int_1401..._0"`, `"obs_1401..."`)。幫助前端處理渲染 key 和潛在的變更追蹤。
*   `value` (任意型別 Any): 序列化後的值。
    *   對於**基本型別** (`int`, `float`, `bool`, `str`): 實際的基本值。
    *   對於 **`NoneType`**: 字串 `"None"`。
    *   對於 **`list`**, **`set`**: 一個陣列 (`[]`)，包含每個元素的巢狀 `VizRepresentation` 物件。
    *   對於 **`dict`**: 一個陣列 (`[]`)，包含多個物件，每個物件結構為 `{ "key": VizRepresentation, "value": VizRepresentation }`。
    *   對於 **`object`**: 一個物件 (`{}`)，將屬性名稱（字串）映射到它們對應的巢狀 `VizRepresentation` 物件。
    *   對於 **`repr`**: 一個字串，包含 Python `repr()` 函式的結果（作為備用方案）。
    *   對於**特殊類型** (`truncated`, `error`, `recursive_ref`): 描述性的字串。
*   `length` (整數 Integer | undefined): 對於容器類型 (`list`, `dict`, `set`, `object`)，表示包含的元素或屬性的數量。對於非容器類型則為 `undefined`。
*   `observable_tracked` (布林 Boolean | undefined): 如果這個表示對應的資料直接來自一個 `ObservableValue`，則設為 `true`。否則為 `undefined`。幫助前端應用特定的樣式或行為。

## 7. 錯誤處理 (Error Handling)

Sidekick -> Hero 的 `error` 訊息使用標準結構，其中 `method: "error"`。`payload` 通常包含：

```json
{ "message": string } // Sidekick 遇到的錯誤描述
```

## 8. 版本與擴充性 (Versioning and Extensibility)

本協定文件代表當前版本。未來可能會進行更改。
*   實作應能處理收到 `payload` 中包含額外、非預期欄位的訊息。
*   實作應嚴格要求本規格書中定義的必要欄位必須存在。
*   目前協定本身沒有正式的版本協商機制。相容性依賴於對本規格書的遵守。