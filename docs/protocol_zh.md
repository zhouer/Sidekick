# Sidekick 通訊協定規格書

## 1. 簡介

本文件詳細說明了 **Hero 端**（使用者執行、使用 `sidekick` 函式庫的腳本）與 **Sidekick 前端**（React 應用程式）之間的通訊協定。此協定讓 Hero 端能夠控制 Sidekick UI 中的視覺化模組，並允許 Sidekick 將通知傳回 Hero 端。

## 2. 傳輸層 (Transport Layer)

*   **機制:** WebSocket
*   **預設端點:** `ws://localhost:5163` (可透過 Python 中的 `sidekick.set_url()` 進行設定)。
*   **編碼:** JSON 字串 (使用 UTF-8 編碼)。
*   **連線維持 (Keep-Alive):** Python 客戶端使用 WebSocket 的 Ping/Pong 訊框來維護連線並偵測連線失敗（在禁用底層 socket 超時後）。伺服器應回應 Ping 訊框以 Pong 訊框。

## 3. 訊息格式 (Message Format)

所有在 Hero 和 Sidekick 之間交換的訊息都共用一個基礎的 JSON 結構。

### 3.1 Hero -> Sidekick 訊息結構

這些是從 Hero 腳本發送，用來控制 Sidekick UI 模組的指令。

```json
{
  "id": number,       // 保留。預設為 0。
  "module": string,   // 目標模組類型 (例如 "grid", "console", "viz", "canvas", "control")。
  "method": string,   // 要執行的動作 ("spawn", "update", "remove")。
  "target": string,   // 目標模組實例的唯一識別碼。
  "payload": object | null // 特定資料。若無則為 null。
}
```

### 3.2 Sidekick -> Hero 訊息結構

這些是從 Sidekick UI 發送回 Hero 腳本的通知或錯誤報告。

```json
{
  "id": number,       // 保留。預設為 0。
  "module": string,   // 來源模組類型 (例如 "grid", "console", "control")。
  "method": string,   // 訊息類型 ("notify", "error")。
  "src": string,      // 來源模組實例的唯一識別碼。
  "payload": object | null // 特定資料。若無則為 null。
}
```

### 3.3 欄位說明 (Field Descriptions)

*   `id` (整數 Integer): 保留欄位。預設為 `0`。
*   `module` (字串 String): 指明涉及的模組類型。
*   `method` (字串 String): 指定要執行的動作（Hero->Sidekick）或訊息的類型（Sidekick->Hero）。
*   `target` (字串 String): **僅用於 Hero -> Sidekick。** 應處理此指令的模組實例的唯一 ID。
*   `src` (字串 String): **僅用於 Sidekick -> Hero。** 產生此訊息的模組實例的唯一 ID。
*   `payload` (物件 Object | Null): 包含特定於方法的資料結構，詳見第 5 節。

## 4. 核心方法 (Core Methods)

這些定義了透過 `method` 欄位進行的主要互動。

### 4.1 Hero -> Sidekick 方法

*   **`spawn`**: 建立新模組實例。Payload 包含初始設定。
*   **`update`**: 修改現有模組實例。Payload 包含具體變更。
*   **`remove`**: 銷毀模組實例。

### 4.2 Sidekick -> Hero 方法

*   **`notify`**: 告知 Hero 使用者操作。Payload 包含事件詳情。
*   **`error`**: 報告 Sidekick 端錯誤。Payload 包含錯誤訊息。

## 5. 特定模組的 Payload (`payload` 結構)

本節詳細說明了不同 `module` 和 `method` 組合下，`payload` 物件預期的結構。

### 5.1 模組: `grid`

*   **`spawn` Payload:**
    ```json
    {
      "size": [width: number, height: number]
    }
    ```
*   **`update` Payload:**
    *   設定儲存格狀態:
        ```json
        {
          "action": "setCell",
          "options": {
            "x": number,
            "y": number,
            "color"?: string | null,
            "text"?: string | null
          }
        }
        ```
    *   清除整個網格:
        ```json
        {
          "action": "clear"
          // 無需 options
        }
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    {
      "event": "click",
      "x": number,
      "y": number
    }
    ```

### 5.2 模組: `console`

*   **`spawn` Payload:**
    ```json
    {
      "text"?: string // 可選初始文字
    }
    ```
*   **`update` Payload:**
    *   附加文字:
        ```json
        {
          "action": "append",
          "options": {
            "text": string
          }
        }
        ```
    *   清除主控台:
        ```json
        {
          "action": "clear"
          // 無需 options
        }
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    {
      "event": "submit",
      "value": string
    }
    ```

### 5.3 模組: `viz`

*   **`spawn` Payload:** `{}`
*   **`update` Payload:** 處理變數新增/更新/移除。
    ```json
    {
      "action": string,       // 例如 "set", "setitem", "append", "removeVariable"
      "variableName": string, // 要更新的變數名稱
      "options": {            // 與操作相關的參數
        "path"?: Array<string | number>, // 變更路徑 (對非根操作為必需)
        "valueRepresentation"?: VizRepresentation | null, // 新值的表示 (若適用)
        "keyRepresentation"?: VizRepresentation | null,   // 鍵的表示 (用於字典 setitem)
        "length"?: number | null                   // 新容器長度 (若適用)
        // 註: 對於 action="removeVariable", options 可能為空或省略
      }
    }
    ```

### 5.4 模組: `canvas`

*   **`spawn` Payload:**
    ```json
    {
      "width": number,
      "height": number,
      "bgColor"?: string
    }
    ```
*   **`update` Payload:**
    ```json
    {
      "action": string, // 例如 "clear", "config", "line", "rect", "circle"
      "options": object, // 指令參數
      "commandId": string | number // 【必需】指令唯一 ID
    }
    ```
    *   *(範例 options: `clear: { color? }`, `config: { strokeStyle?, fillStyle?, lineWidth? }`, `line: { x1, y1, x2, y2 }` 等)*

### 5.5 模組: `control`

*   **`spawn` Payload:** `{}`
*   **`update` Payload:** 用於新增或移除個別控制項。
    *   新增控制項:
        ```json
        {
          "action": "add",
          "controlId": string, // 要新增的控制項 ID
          "options": {        // 新控制項的參數
            "controlType": "button" | "text_input",
            "config": {
              "text"?: string,
              "placeholder"?: string,
              "initialValue"?: string,
              "buttonText"?: string
            }
          }
        }
        ```
    *   移除控制項:
        ```json
        {
          "action": "remove",
          "controlId": string // 要移除的控制項 ID
          // 移除時無需 options
        }
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    {
      "event": "click" | "submit",
      "controlId": string,
      "value"?: string // 僅用於 "submit" 事件
    }
    ```

## 6. 資料表示 (`VizRepresentation`)

(無變更，鍵名已是 camelCase)

*   `type` (字串 String)
*   `id` (字串 String)
*   `value` (任意型別 Any)
*   `length` (整數 Integer | undefined)
*   `observableTracked` (布林 Boolean | undefined)

## 7. 錯誤處理 (Error Handling)

Sidekick -> Hero 的 `error` 訊息使用標準結構，其中 `method: "error"`。`payload` 通常包含：

```json
{ "message": string }
```

## 8. 版本與擴充性 (Versioning and Extensibility)

本協定文件代表當前版本。未來可能會進行更改。
*   實作應能穩健地處理收到包含額外、非預期欄位的訊息。
*   實作應嚴格要求本規格書中定義的必要欄位必須存在。
*   `payload` 物件內的鍵名**必須**使用 `camelCase`。
*   盡可能採用 `action`/`options` 的模式來組織 `update` 的 payload。
*   目前協定本身沒有正式的版本協商機制。