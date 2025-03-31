# Sidekick Python Library: `Control` 模組

## 1. 概觀 (Overview)

`sidekick.Control` 類別提供了一個介面，讓 Python (Hero) 腳本能夠動態地在 Sidekick 前端 UI 中建立包含互動式控制項（如按鈕、文字輸入框）的區域。

使用者可以透過這個模組向 UI 添加控制項，並註冊一個回呼函式來處理來自這些控制項的使用者互動事件（例如按鈕點擊、文字提交）。這使得 Hero 腳本可以接收來自使用者的直接輸入或觸發指令。

## 2. 設計理念 (Design Philosophy)

*   **動態性:** 允許在腳本運行過程中隨時添加或移除控制項。
*   **互動性:** 提供一種將 UI 事件（點擊、提交）傳回 Python 腳本的標準方式。
*   **簡單性:** 提供簡潔的方法來添加常用控制項。
*   **唯一標識:** 每個添加到模組中的控制項都需要一個在該模組實例內唯一的 `control_id`，以便區分事件來源。
*   **事件驅動:** 透過 `on_message` 回呼函式處理來自前端的 `notify` 訊息。

## 3. 使用方法 (Usage)

### 3.1 建立 Control 模組 (`__init__`)

```python
from sidekick import Control
import logging # 假設已設定日誌

# 定義處理來自控制項事件的回呼函式
def handle_my_controls(message):
    payload = message.get('payload', {})
    event = payload.get('event')
    control_id = payload.get('control_id')
    value = payload.get('value') # 只有 submit 事件有值

    logging.info(f"Control Event: ID='{control_id}', Event='{event}', Value='{value}'")

    if control_id == 'action_button' and event == 'click':
        print("Action Button was clicked!")
        # 在此處執行按鈕點擊後的操作...
    elif control_id == 'user_input' and event == 'submit':
        print(f"User submitted: {value}")
        # 在此處處理使用者輸入...

# 建立 Control 模組實例，並傳入回呼函式
my_controls = Control(instance_id='interactive-panel', on_message=handle_my_controls)
```

*   **參數:**
    *   `instance_id` (Optional[str], default=None): 此 Control 模組實例的唯一 ID。
    *   `on_message` (Optional[Callable[[Dict[str, Any]], None]], default=None): 一個回呼函式，用於處理從前端此模組發送回來的 `notify` 訊息。該函式會接收一個符合 `SidekickMessage` 格式的字典。
*   **動作:**
    1.  向前端發送 `spawn` 訊息，建立 Control 模組容器。
    2.  如果提供了 `on_message` 回呼，則呼叫 `connection.register_message_handler` 將回呼與此模組的 `instance_id` 關聯起來。

### 3.2 添加按鈕 (`add_button`)

在模組中添加一個可點擊的按鈕。

```python
# 添加一個 ID 為 "action_button"，顯示文字為 "Perform Action" 的按鈕
my_controls.add_button(control_id='action_button', text='Perform Action')

# 添加另一個按鈕
my_controls.add_button(control_id='cancel_op', text='Cancel')
```

*   **參數:**
    *   `control_id` (str): 此按鈕在此模組內的唯一識別碼。用於在 `on_message` 回呼中區分是哪個按鈕被點擊。
    *   `text` (str): 顯示在按鈕上的文字。
*   **動作:** 向前端發送 `update` 訊息，`operation` 為 `"add"`，`control_type` 為 `"button"`，並包含 `control_id` 和 `config`（內含 `text`）。

### 3.3 添加文字輸入框 (`add_text_input`)

在模組中添加一個文字輸入欄位和一個關聯的提交按鈕。

```python
# 添加一個文字輸入框，用於輸入名稱
my_controls.add_text_input(
    control_id='name_field',
    placeholder='Enter your name...',
    initial_value='Default User',
    button_text='Submit Name'
)

# 添加另一個只有基本提示的輸入框
my_controls.add_text_input(control_id='search_query', placeholder='Search...')
```

*   **參數:**
    *   `control_id` (str): 此文字輸入框在此模組內的唯一識別碼。提交事件會使用此 ID。
    *   `placeholder` (str, default=""): 顯示在輸入框中的提示文字。
    *   `initial_value` (str, default=""): 輸入框的初始內容。
    *   `button_text` (str, default="Submit"): 提交按鈕上顯示的文字。
*   **動作:** 向前端發送 `update` 訊息，`operation` 為 `"add"`，`control_type` 為 `"text_input"`，並包含 `control_id` 和 `config`（內含 `placeholder`, `initial_value`, `button_text`）。

### 3.4 移除控制項 (`remove_control`)

從模組中移除指定 ID 的控制項（按鈕或文字輸入框）。

```python
# 移除之前添加的取消按鈕
my_controls.remove_control('cancel_op')

# 移除搜尋輸入框
my_controls.remove_control('search_query')
```

*   **參數:**
    *   `control_id` (str): 要移除的控制項的唯一識別碼。
*   **動作:** 向前端發送 `update` 訊息，`operation` 為 `"remove"`，並包含 `control_id`。

### 3.5 移除 Control 模組 (`remove`)

從 Sidekick UI 中移除整個 Control 模組實例，並取消註冊其訊息處理常式。

```python
my_controls.remove()
```

*   **動作:**
    1.  呼叫 `connection.unregister_message_handler` 取消註冊與此模組 ID 關聯的 `on_message` 回呼。
    2.  向前端發送基礎的 `remove` 訊息，要求移除整個模組元件。

## 4. 前端互動與回呼 (Frontend Interaction & Callback)

*   當使用者在前端 UI 中與 `ControlModule` 內的控制項互動時（點擊按鈕或提交文字輸入），`ControlModule.tsx` 元件會觸發其 `onInteraction` prop。
*   `onInteraction`（最終會呼叫 `connection.send_message`）會向 Hero 端發送一個 `notify` 訊息。
*   這個 `notify` 訊息的 `src` 欄位會是觸發事件的 Control 模組的 `instance_id`。
*   `payload` 結構如 `protocol.md` 中定義：
    *   對於按鈕點擊：`{ "event": "click", "control_id": "..." }`
    *   對於文字提交：`{ "event": "submit", "control_id": "...", "value": "..." }`
*   Python 端的 `connection` 模組的監聽執行緒接收到此訊息後，會根據訊息中的 `src` 欄位查找對應的已註冊 `on_message` 回呼函式。
*   如果找到了回呼函式（即建立 `Control` 物件時傳入的那個函式），則執行該函式，並將完整的 `notify` 訊息字典作為參數傳入。
*   開發者在回呼函式中解析 `payload` 中的 `event`, `control_id`, 和 `value` (如果有的話)，來執行相應的 Python 邏輯。

## 5. 範例場景 (Example Scenario)

```python
from sidekick import Control, Console, connection
import time
import logging

logging.basicConfig(level=logging.INFO)

console = Console()
counter = 0

def control_handler(msg):
    global counter
    payload = msg.get('payload', {})
    ctrl_id = payload.get('control_id')
    event = payload.get('event')

    if event == 'click':
        if ctrl_id == 'inc_btn':
            counter += 1
            console.print(f"Counter incremented to: {counter}")
        elif ctrl_id == 'dec_btn':
            counter -= 1
            console.print(f"Counter decremented to: {counter}")
    elif event == 'submit' and ctrl_id == 'set_val_input':
        try:
            new_val = int(payload.get('value', 0))
            counter = new_val
            console.print(f"Counter set to: {counter}")
        except ValueError:
            console.print(f"Invalid input: '{payload.get('value')}' is not an integer.")

connection.activate_connection()
controls = Control(on_message=control_handler)

controls.add_button(control_id='inc_btn', text='Increment')
controls.add_button(control_id='dec_btn', text='Decrement')
controls.add_text_input(control_id='set_val_input', placeholder='Set counter value', button_text='Set')

console.log("Controls added. Interact with them in Sidekick.")

try:
    while True:
        time.sleep(10) # Keep script running
except KeyboardInterrupt:
    pass
finally:
    connection.close_connection()
```
