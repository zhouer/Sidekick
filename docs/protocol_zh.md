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
  "module": string,   // 目標模組的類型 ("grid", "console", "viz", "canvas", "control")。
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
  "module": string,   // 產生此訊息的來源模組類型 ("grid", "console", "control")。
  "method": string,   // 訊息的類型 ("notify", "error")。
  "src": string,      // 來源模組實例的唯一識別碼。
  "payload": object | null // 根據通知或錯誤而定的特定資料。
}
```

### 3.3 欄位說明 (Field Descriptions)

*   `id` (整數 Integer): 保留欄位。預設為 `0`。未來版本可能用於請求/回應的配對。
*   `module` (字串 String): 指明涉及的模組類型（例如 `"grid"`, `"console"`, `"viz"`, `"canvas"`, `"control"`）。
*   `method` (字串 String): 指定要執行的動作（用於 Hero->Sidekick）或訊息的類型（用於 Sidekick->Hero）。
*   `target` (字串 String): **僅用於 Hero -> Sidekick。** 應處理此指令的模組實例的唯一 ID。
*   `src` (字串 String): **僅用於 Sidekick -> Hero。** 產生此訊息的模組實例的唯一 ID。
*   `payload` (物件 Object | Null): 包含特定於方法的資料結構，詳見第 5 節。

## 4. 核心方法 (Core Methods)

這些定義了透過 `method` 欄位進行的主要互動。

### 4.1 Hero -> Sidekick 方法

*   **`spawn`**: 指示 Sidekick 建立並顯示一個指定模組類型的新實例。`payload` 包含該模組的初始設定。
*   **`update`**: 指示 Sidekick 修改一個現有模組實例（由 `target` 指定）的狀態。`payload` 包含要套用的具體變更。對於 `viz` 模組，此方法處理所有變數的新增、更新和移除。對於 `control` 模組，它處理新增/移除個別控制項。
*   **`remove`**: 指示 Sidekick 銷毀並從 UI 中移除一個特定的模組實例（由 `target` 指定）。

### 4.2 Sidekick -> Hero 方法

*   **`notify`**: 由互動式模組（如 `grid`, `console` 或 `control`）發送，用於告知 Hero 使用者的操作（例如，點擊儲存格、提交文字輸入、點擊按鈕）。`payload` 包含事件的詳細資訊。
*   **`error`**: 如果 Sidekick 在處理指令或管理模組時遇到錯誤（例如，無效的 payload、找不到模組），則會發送此訊息。`payload` 通常包含錯誤訊息。

## 5. 特定模組的 Payload (`payload` 結構)

本節詳細說明了不同 `module` 和 `method` 組合下，`payload` 物件預期的結構。

### 5.1 模組: `grid`

*   **`spawn` Payload:** ` { "size": [width: number, height: number] } `
*   **`update` Payload (擇一):**
    *   更新儲存格: ` { "x": number, "y": number, "color"?: string | null, "text"?: string | null } `
    *   填滿網格: ` { "fill_color": string } `
*   **`notify` Payload (Sidekick -> Hero):** ` { "event": "click", "x": number, "y": number } `

### 5.2 模組: `console`

*   **`spawn` Payload:** ` { "text"?: string } `
*   **`update` Payload (擇一):**
    *   附加文字: ` { "text": string } `
    *   清除主控台: ` { "clear": true } `
*   **`notify` Payload (Sidekick -> Hero):** ` { "event": "submit", "value": string } `

### 5.3 模組: `viz`

*   **`spawn` Payload:** `{}`
*   **`update` Payload:** 處理變數新增/更新/移除。
    ```json
    {
      "variable_name": string,
      "change_type": string, // "set", "setitem", "append", ..., "remove_variable"
      "path": Array<string | number>, // `[]` 表示根
      "value_representation": VizRepresentation | null, // 見第 6 節。若不適用則為 null
      "key_representation"?: VizRepresentation | null,   // 可選: 用於字典操作
      "length"?: number | null                   // 可選: 新容器長度
    }
    ```

### 5.4 模組: `canvas`

*   **`spawn` Payload:** ` { "width": number, "height": number, "bgColor"?: string } `
*   **`update` Payload:** 代表一個繪圖或設定指令。
    ```json
    {
      "command": string, // "clear", "config", "line", "rect", "circle"
      "options": object, // 指令參數
      "commandId": string | number // 指令的唯一 ID
    }
    ```
    *   *(具體 options 結構請參考之前的說明文件)*

### 5.5 模組: `control`

*   **`spawn` Payload:**
    ```json
    {} // Spawn 時不需要特定 payload，僅建立空容器
    ```
*   **`update` Payload:** 用於新增或移除個別控制項。
    ```json
    {
      "operation": "add" | "remove", // 要執行的操作
      "control_id": string,         // 此模組內控制項的唯一 ID
      // "add" 操作所需欄位:
      "control_type"?: "button" | "text_input", // 控制項類型
      "config"?: {                             // 控制項設定
        // 用於 "button":
        "text"?: string,         // 按鈕上顯示的文字
        // 用於 "text_input":
        "placeholder"?: string, // 輸入框的提示文字
        "initial_value"?: string,// 輸入框的初始值
        "button_text"?: string  // 關聯提交按鈕的文字 (可選)
      }
    }
    ```
*   **`notify` Payload (Sidekick -> Hero):** 使用者互動時發送。
    ```json
    {
      "event": "click" | "submit", // 互動類型 ("click" 為按鈕, "submit" 為文字輸入)
      "control_id": string,         // 觸發互動的控制項 ID
      // 僅在 text_input 的 "submit" 事件時存在:
      "value"?: string              // 使用者提交的文字值
    }
    ```

## 6. 資料表示 (`VizRepresentation`)

這個標準的 JSON 結構用於 `viz` 模組 `update` 訊息的 `payload` 中（`value_representation`, `key_representation` 欄位），目的是將 Python 資料序列化以供前端顯示。

一個 `VizRepresentation` 是包含以下欄位的 JSON 物件：

*   `type` (字串 String): Python 類型名稱或特殊類型識別符 (例如 `"int"`, `"list"`, `"dict"`, `"set"`, `"NoneType"`, `"object (ClassName)"`, `"repr (ClassName)"`, `"truncated"`)。
*   `id` (字串 String): 此資料節點表示的唯一識別碼 (例如 `"int_1401..."`, `"obs_1401..."`)。
*   `value` (任意型別 Any): 序列化後的值（基本型別、表示陣列、表示物件、或描述性字串）。
*   `length` (整數 Integer | undefined): 容器類型的項目/屬性數量。
*   `observable_tracked` (布林 Boolean | undefined): 若資料源自 `ObservableValue`，則為 `true`。

*(list, dict, object 的詳細 value 結構省略，請參考先前的 Viz 文件)*

## 7. 錯誤處理 (Error Handling)

Sidekick -> Hero 的 `error` 訊息使用標準結構，其中 `method: "error"`。`payload` 通常包含：

```json
{ "message": string } // Sidekick 遇到的錯誤描述
```

## 8. 版本與擴充性 (Versioning and Extensibility)

本協定文件代表當前版本。未來可能會進行更改。
*   實作應能穩健地處理收到包含額外、非預期欄位的訊息。
*   實作應嚴格要求本規格書中定義的必要欄位必須存在。
*   目前協定本身沒有正式的版本協商機制。相容性依賴於對本規格書的遵守。