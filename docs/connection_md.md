# Sidekick Python Library: 連線管理 (`connection.py`)

## 1. 概觀 (Overview)

`connection.py` 模組是 Sidekick Python 函式庫的基石，負責建立、維護和管理與 Sidekick 前端 UI（通常透過一個 WebSocket 伺服器）之間的 **WebSocket 連線**。所有模組（如 `Grid`, `Console`, `Viz`, `Canvas`）的通訊都依賴這個共享的連線。

這個模組被設計為一個**單例 (Singleton)** 管理器，確保在整個 Python 腳本的生命週期中只有一個活躍的 WebSocket 連線。它處理了連線的建立、底層的訊息收發、連線維持 (Keep-Alive)、錯誤處理以及在腳本結束時的自動清理。

## 2. 設計目標與特性 (Goals & Features)

*   **單一連線 (Singleton):** 避免多個模組建立重複的連線，節省資源並簡化管理。
*   **延遲建立 (Lazy Connection):** 直到第一個需要通訊的操作（通常是建立第一個模組實例）發生時，才實際嘗試建立連線。
*   **背景監聽:** 使用獨立的背景執行緒（Listener Thread）來接收來自 Sidekick 前端的訊息（如 `notify` 或 `error`），避免阻塞主執行緒。
*   **可靠的連線維持 (Keep-Alive):**
    *   利用 `websocket-client` 函式庫內建的 **WebSocket Ping/Pong** 機制。設定固定的時間間隔 (`_PING_INTERVAL`) 自動發送 Ping 訊框。
    *   設定 Ping 的超時時間 (`_PING_TIMEOUT`)，如果在指定時間內未收到對應的 Pong 回應，則認為連線已斷開。
    *   **關鍵:** 成功建立連線後，**禁用**了底層 socket 的讀取超時 (`settimeout(None)`)，完全依賴 Ping/Pong 來判斷連線活性，適用於可能長時間無應用層數據傳輸的場景。
*   **明確的連線狀態管理:** 使用內部旗標 (`_connection_active`, `_listener_started`) 和執行緒鎖 (`_connection_lock`) 來安全地管理連線的意圖狀態（是否應該連線）、實際狀態以及監聽執行緒的生命週期。
*   **訊息處理分發:** 提供註冊機制 (`register_message_handler`, `unregister_message_handler`)，允許特定的模組實例（由 `instance_id` 標識）註冊回呼函式，以便在收到來自前端對應元件的訊息時進行處理。監聽執行緒負責將收到的訊息分派給正確的處理常式。
*   **線程安全:** 使用 `threading.Lock` 來保護對共享資源（如 WebSocket 連線物件、狀態旗標、處理常式註冊表）的存取，確保在多執行緒環境下的安全。
*   **健壯的錯誤處理:** 捕捉連線建立、訊息發送/接收、連線關閉過程中可能出現的各種網路錯誤、WebSocket 協議錯誤、JSON 解析錯誤等，並進行適當的日誌記錄和狀態清理。
*   **自動清理 (`atexit`):** 在 Python 腳本結束時，自動註冊 `close_connection` 函式被呼叫，確保 WebSocket 連線被優雅關閉。
*   **可設定的 URL:** 允許使用者在建立連線前透過 `set_url()` 函數指定不同的 WebSocket 伺服器地址。
*   **日誌記錄:** 使用標準 `logging` 模組提供詳細的連線過程和錯誤資訊。

## 3. 主要函式與用法 (Key Functions & Usage)

開發者通常不需要直接與 `connection.py` 中的大部分函式互動，因為模組類別（如 `Viz`, `Grid`）會在內部呼叫它們。但了解其提供的公共接口有助於理解整體機制或進行進階設定。

*   **`set_url(url: str)`:**
    *   **用途:** 設定要連接的 WebSocket 伺服器 URL。
    *   **限制:** **必須**在第一次嘗試建立連線（例如，建立第一個 Sidekick 模組物件）**之前**呼叫。一旦連線建立，則無法更改 URL，除非先呼叫 `close_connection()`。
    *   **範例:** `sidekick.connection.set_url("ws://192.168.1.100:5163")`

*   **`activate_connection()`:**
    *   **用途:** (主要供內部模組呼叫) 明確標識應用程式**意圖**使用 Sidekick 連線。`get_connection()` 只會在 `_connection_active` 為 `True` 時才嘗試連線。模組的 `__init__` 通常會呼叫它。
    *   **注意:** 開發者一般不需要直接呼叫。

*   **`get_connection() -> Optional[websocket.WebSocket]`:**
    *   **用途:** (主要供內部模組呼叫) 取得共享的 `websocket-client` 的 `WebSocket` 連線物件。
    *   **行為:**
        1.  如果連線已存在且處於連接狀態，直接返回該物件。
        2.  如果連線不存在或已斷開，**且** `_connection_active` 為 `True`，則嘗試建立新連線。
        3.  建立連線時，使用 `_INITIAL_CONNECT_TIMEOUT` 作為初始連線超時。
        4.  成功連線後，設定 `ping_interval` 和 `ping_timeout`，並呼叫 `settimeout(None)` 禁用 socket 讀取超時。
        5.  如果監聽執行緒尚未啟動，則啟動它。
        6.  如果連線失敗或 `_connection_active` 為 `False`，則返回 `None`。
    *   **注意:** 開發者一般不需要直接呼叫。

*   **`send_message(message_dict: Dict[str, Any])`:**
    *   **用途:** (主要供內部模組呼叫) 將一個 Python 字典轉換為 JSON 字串，並透過 WebSocket 發送出去。
    *   **行為:**
        1.  呼叫 `get_connection()` 確保連線存在。
        2.  如果連線成功，獲取執行緒鎖，再次檢查連線狀態。
        3.  序列化字典為 JSON。
        4.  呼叫 `ws.send()` 發送訊息。
        5.  處理可能的發送錯誤（如 `BrokenPipeError`, `WebSocketException`），並在出錯時嘗試關閉連線。
    *   **注意:** 開發者一般不需要直接呼叫。模組的 `_send_command` 等方法會封裝此函式。

*   **`close_connection(log_info=True)`:**
    *   **用途:** 手動關閉當前的 WebSocket 連線，並清理相關狀態。也會由 `atexit` 自動呼叫。
    *   **行為:**
        1.  獲取執行緒鎖。
        2.  將 `_connection_active` 設為 `False`，通知監聽執行緒停止。
        3.  將 `_listener_started` 設為 `False`。
        4.  如果存在連線物件 (`_ws_connection`)，則呼叫其 `close()` 方法。
        5.  清空 `_message_handlers` 註冊表。
        6.  將 `_ws_connection` 設為 `None`。
    *   **範例:** `sidekick.connection.close_connection()` (不常需要手動呼叫)。

*   **`register_message_handler(instance_id: str, handler: Callable)`:**
    *   **用途:** (主要供內部模組呼叫) 為來自前端特定模組實例 (`instance_id`) 的訊息註冊一個處理函式 (`handler`)。
    *   **注意:** `Console` 和 `Grid` 的 `__init__` 方法會使用它來註冊傳入的 `on_message` 回呼。

*   **`unregister_message_handler(instance_id: str)`:**
    *   **用途:** (主要供內部模組呼叫) 移除之前為特定 `instance_id` 註冊的訊息處理函式。
    *   **注意:** 模組的 `remove()` 方法通常會呼叫它來清理。

## 4. 內部運作細節 (Internal Mechanics)

### 4.1 監聽執行緒 (`_listen_for_messages`)

*   這是 `connection.py` 的核心執行緒，負責持續監聽 WebSocket 上的傳入訊息。
*   **循環:** 在 `_connection_active` 為 `True` 且連線有效時，它會阻塞在 `ws.recv()` 上等待訊息。
*   **訊息處理:**
    1.  收到訊息字串後，嘗試將其解析為 JSON 字典。
    2.  檢查 JSON 字典中是否存在 `src` 欄位（表示來源模組 ID）。
    3.  如果存在 `src`，則在鎖的保護下查找 `_message_handlers` 字典中對應的回呼函式。
    4.  如果找到處理常式，則**在鎖之外**呼叫該處理常式，並將完整的訊息字典傳遞給它（避免在執行處理常式時持有鎖導致死鎖）。
    5.  處理 JSON 解析錯誤、處理常式執行錯誤等。
*   **錯誤與退出:**
    *   當 `ws.recv()` 因連線關閉 (`WebSocketConnectionClosedException`) 或 Ping 超時 (`WebSocketTimeoutException`) 或其他網路錯誤 (`OSError`) 而拋出異常時，執行緒會記錄訊息並退出循環。
    *   當 `_connection_active` 變為 `False`（例如呼叫了 `close_connection`）時，執行緒也會在下一次檢查或等待超時後退出循環。
    *   執行緒結束時，會重設 `_listener_started` 旗標。

### 4.2 線程安全 (Thread Safety)

*   使用 `_connection_lock = threading.Lock()` 來保護所有對共享狀態的訪問，包括：
    *   讀寫 `_ws_connection` 連線物件。
    *   讀寫 `_connection_active`, `_listener_started` 旗標。
    *   讀寫 `_message_handlers` 字典。
    *   在 `send_message` 中包裹 `ws.send()` 操作，防止多個執行緒同時寫入 WebSocket。
*   **注意:** 訊息處理常式 (`handler`) 是在獲取到處理常式參考後，**在鎖之外**執行的，這是為了避免處理常式內部如果需要呼叫 `send_message`（或其他需要鎖的操作）時發生死鎖。

### 4.3 Keep-Alive 詳細說明

*   `websocket-client` 函式庫在設定 `ping_interval` 和 `ping_timeout` 後，會在內部維護一個計時器。
*   每隔 `ping_interval` 秒，如果期間沒有發送任何其他數據，它會自動發送一個 WebSocket Ping 訊框。
*   同時，它會監聽 Pong 訊框。如果在發送 Ping 後的 `ping_timeout` 秒內沒有收到對應的 Pong，函式庫會認為連線超時，並在下一次呼叫 `recv()` 或 `send()` 時拋出 `WebSocketTimeoutException`。
*   由於 `_listen_for_messages` 中的 `ws.recv()` 在禁用 socket timeout 後會一直阻塞，`WebSocketTimeoutException` 會在這裡被捕捉到，從而使監聽執行緒知道連線因 Ping 超時而斷開。

## 5. 日誌記錄 (Logging)

*   模組使用標準 `logging` 模組，記錄器名稱為 `"SidekickConn"`。
*   預設日誌級別為 `INFO`，輸出到控制台 (`StreamHandler`)。
*   可以透過 Python 的標準 `logging` 配置來修改日誌級別、格式和輸出目標。例如，設定為 `DEBUG` 級別會看到更詳細的訊息（如發送/接收的原始訊息）。
    ```python
    import logging
    logging.getLogger("SidekickConn").setLevel(logging.DEBUG)
    ```

## 6. 總結

`connection.py` 提供了一個穩定、可靠且易於內部使用的 WebSocket 連線管理層。它透過背景執行緒、內建 Keep-Alive、線程安全機制和自動清理，簡化了 Sidekick 其他模組與前端進行雙向通訊的複雜性，是整個 Sidekick Python 函式庫正常運作的基礎。開發者主要透過配置 URL 和理解其 Keep-Alive 機制來與之互動。