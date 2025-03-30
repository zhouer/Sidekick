# Sidekick 模組: Viz (變數視覺化器)

## 1. 概觀 (Overview)

`Viz` 模組是 Sidekick 的核心功能之一，它提供了一個強大的視覺化界面，用於在 Sidekick UI 中**檢查和追蹤 Python 腳本 (Hero 端) 中的變數狀態**。

使用者可以透過 `viz.show()` 方法將任意 Python 變數（包括基本型別、複雜的巢狀容器，甚至是自訂物件）傳送到前端進行展示。`Viz` 模組最顯著的特性是它與 `sidekick.ObservableValue` 的深度整合，能夠**自動監聽**被 `ObservableValue` 包裝的變數，並在這些變數發生變化時，**即時、細粒度地更新**前端顯示，甚至可以 highlight 發生變化的具體部分。

這使得 `Viz` 成為一個極佳的偵錯 (Debug) 和理解程式執行流程中資料變化的工具。

## 2. 功能特性 (Features)

*   **任意變數顯示:** 可以顯示 Python 中的各種資料類型。
*   **結構化呈現:** 對於列表、字典、集合、物件等容器類型，提供可展開/摺疊的樹狀結構視圖，方便查看內部元素或屬性。
*   **類型標識:** 清晰地標示每個值的 Python 類型。
*   **自動更新 (基於 `ObservableValue`):** 當使用 `viz.show()` 顯示一個 `ObservableValue` 時，`Viz` 會自動訂閱其變化。之後對該 `ObservableValue` 的任何修改（透過 `.set()` 或攔截的方法如 `append`, `[]=`) 都會觸發前端 UI 的自動更新。
*   **細粒度變化追蹤:** 利用 `ObservableValue` 提供的詳細變化資訊（類型、路徑、新值等），`Viz` 能夠將這些細節傳遞給前端。
*   **變化高亮 (Highlighting):** 前端 UI 會根據接收到的變化路徑 (`path`) 和時間戳，暫時高亮顯示剛剛發生變化的資料節點，幫助使用者快速定位變更。
*   **Observable 標識:** 被 `ObservableValue` 包裝的數值在 UI 上會有特殊的視覺標識（例如，淺藍色背景），以區分它們和普通靜態變數。

## 3. Python API (`sidekick.Viz`)

使用者透過 `sidekick` 函式庫中的 `Viz` 類別與視覺化模組互動。

### 3.1 建立視覺化器 (`__init__`)

```python
from sidekick import Viz

# 建立一個 Viz 模組實例
viz = Viz(instance_id='my-variable-watcher')

# 使用自動產生的 ID
default_viz = Viz()
```

*   **參數:**
    *   `instance_id` (Optional[str], default=None): 為此 `Viz` 實例指定一個唯一的 ID。如果為 `None`，會自動產生一個。
*   **動作:** 呼叫建構子會向 Sidekick 前端發送一個 `spawn` 訊息，要求建立對應的 Viz 元件。

### 3.2 顯示或更新變數 (`show`)

將一個 Python 變數顯示在 `Viz` 模組中，或者更新已顯示變數的值。

```python
from sidekick import Viz, ObservableValue

viz = Viz()

# 顯示靜態變數
name = "Sidekick"
version = 1.0
viz.show("app_name", name)
viz.show("app_version", version)

# 顯示並追蹤 ObservableValue
counter = ObservableValue(0)
data_list = ObservableValue(['a', 'b'])
viz.show("counter", counter)        # Viz 會訂閱 counter 的變化
viz.show("my_data", data_list)      # Viz 會訂閱 data_list 的變化

# 更新已顯示的變數 (即使不是 ObservableValue)
version = 1.1
viz.show("app_version", version) # 前端會更新 app_version 的顯示

# 更新 ObservableValue (通常不需要再呼叫 show，除非要替換整個 Observable 物件)
counter.set(1) # Viz 會自動收到通知並更新前端
data_list.append('c') # Viz 會自動收到通知並更新前端
```

*   **參數:**
    *   `name` (str): 要在 UI 中顯示的變數名稱。
    *   `value` (Any): 要顯示的 Python 值，可以是任何類型，包括 `ObservableValue`。
*   **動作:**
    1.  **產生視覺化表示 (`VizRepresentation`):** 呼叫內部的 `_get_representation` 函數，將 `value` 轉換為前端可以理解的 JSON 格式。如果 `value` 是 `ObservableValue`，產生的表示會包含 `observable_tracked: true` 標記，且其根節點 ID 會使用 `ObservableValue` 的內部 ID。
    2.  **(如果 value 是 `ObservableValue`) 訂閱:** `Viz` 實例會將自己的 `_handle_observable_update` 方法註冊為 `value` 的訂閱者。如果之前已經為同名 `name` 顯示過另一個 `ObservableValue`，會先取消之前的訂閱。
    3.  **發送 `set` 更新:** 向前端發送一個 `update` 訊息，其 `payload` 包含：
        *   `variable_name`: `name` 參數的值。
        *   `change_type`: `"set"` (表示這是一次完整的設定或替換)。
        *   `path`: `[]` (表示作用於根變數)。
        *   `value_representation`: 第 1 步產生的 JSON 表示。
        *   `length`: 如果 `value` 或其內部值有長度，則包含該長度。

### 3.3 移除變數顯示 (`remove_variable`)

從 `Viz` 模組的 UI 中移除指定名稱的變數顯示。

```python
# 假設之前顯示了 "counter"
viz.remove_variable("counter")
```

*   **參數:**
    *   `name` (str): 要移除的變數名稱。
*   **動作:**
    1.  **取消訂閱:** 如果名為 `name` 的變數當初是一個 `ObservableValue`，則呼叫取消訂閱函式，解除 `Viz` 與該 `ObservableValue` 的關聯。
    2.  **從內部記錄中移除:** 從 `Viz` 實例內部維護的 `_shown_variables` 字典中移除該變數的記錄。
    3.  **發送 `remove_variable` 更新:** 向前端發送一個 `update` 訊息，其 `payload` 包含：
        *   `variable_name`: `name` 參數的值。
        *   `change_type`: `"remove_variable"`。
        *   `path`: `[]`。
        *   其他欄位（如 `value_representation`）為 `None`。

### 3.4 移除 Viz 模組 (`remove`)

從 Sidekick UI 中移除整個 `Viz` 模組實例，並清理所有相關資源。

```python
viz.remove()
```

*   **動作:**
    1.  遍歷內部記錄的所有已顯示變數。
    2.  對每個變數呼叫 `remove_variable(variable_name)`，以確保所有訂閱都被取消，並向前端發送移除各個變數的 `update` 訊息。
    3.  向前端發送一個基礎的 `remove` 訊息（來自 `BaseModule`），要求移除整個 `Viz` 模組元件。

## 4. 內部運作與資料流 (Internal Mechanics & Data Flow)

### 4.1 序列化 (`_get_representation`)

*   這是 `viz.py` 中的一個關鍵輔助函式，負責將任意 Python 資料遞迴地轉換為標準的 `VizRepresentation` JSON 物件結構。
*   它處理基本型別、容器（限制最大深度 `_MAX_DEPTH` 和最大項目數 `_MAX_ITEMS` 以避免效能問題和無限遞迴）、物件屬性（只讀取非 callable 且非底線開頭的屬性）。
*   **核心:** 當遇到 `ObservableValue` 時，它會取得其內部值，遞迴處理內部值，然後在結果上附加 `observable_tracked: true` 標記，並使用 `ObservableValue` 的 `_obs_value_id` 作為最終表示的 `id`。

### 4.2 處理 Observable 更新 (`_handle_observable_update`)

*   這是 `Viz` 實例內部的方法，被註冊為 `ObservableValue` 的回呼函式。
*   當 `ObservableValue` 呼叫它時，會傳入一個包含變化細節的字典 (`change_details`)，內容由 `ObservableValue` 的攔截方法產生（包含 `type`, `path`, `value`, `key`, `length` 等）。
*   `_handle_observable_update` 的工作是：
    1.  解析 `change_details`。
    2.  如果 `change_details` 中包含需要序列化的新 `value` 或 `key`，則呼叫 `_get_representation` 產生它們的 `VizRepresentation`。
    3.  構建一個符合通訊協定的 `update` WebSocket 訊息，將 `variable_name`, `change_type`, `path`, `value_representation`, `key_representation`, `length` 等欄位填入 `payload`。
    4.  透過 `connection` 模組將此訊息發送給前端。

### 4.3 資料流總結

1.  **`viz.show(name, value)`:**
    *   Python (`Viz`) -> `_get_representation(value)` -> JSON (`VizRepresentation`)
    *   Python (`Viz`) -> WebSocket -> 前端: `update` msg (`type="set"`, `path=[]`, `value_rep=完整表示`)
    *   (If `value` is Observable) Python (`Viz`) -> `value.subscribe(_handle_observable_update)`
2.  **`observable_value.append(item)` (或其他修改):**
    *   Python (`ObservableValue`) -> 執行 `append` -> 產生 `change_details` (`type="append"`, `path=[idx]`, `value=item`, ...)
    *   Python (`ObservableValue`) -> `_notify(change_details)` -> Python (`Viz._handle_observable_update`)
    *   Python (`Viz`) -> `_get_representation(item)` -> JSON (item 的 `VizRepresentation`)
    *   Python (`Viz`) -> WebSocket -> 前端: `update` msg (`type="append"`, `path=[idx]`, `value_rep=item表示`, ...)
3.  **`viz.remove_variable(name)`:**
    *   (If observable) Python (`Viz`) -> `observable_value.unsubscribe()`
    *   Python (`Viz`) -> WebSocket -> 前端: `update` msg (`type="remove_variable"`, `path=[]`, ...)

## 5. 前端實作 (`VizModule.tsx` & `RenderValue`)

*   **`VizModule.tsx`:**
    *   接收 `state: VizState` 作為 prop。
    *   從 `state.variables` 中讀取所有要顯示的變數名稱並排序。
    *   遍歷變數，為每個變數渲染其名稱 (`<span class="viz-variable-name">`)。
    *   為每個變數渲染一個頂層的 `RenderValue` 元件，將變數的完整 `VizRepresentation` (`state.variables[varName]`)、初始空路徑 `[]`、以及對應的 `state.lastChanges[varName]` 資訊傳遞下去。
*   **`RenderValue.tsx` (遞迴元件):**
    *   接收 `data` (當前的 `VizRepresentation` 節點)、`currentPath` (到達此節點的路徑)、`lastChangeInfo` (整個變數的最後變化資訊) 作為 props。
    *   **核心邏輯:**
        *   **Highlight 判斷:** 比較 `currentPath` 和 `lastChangeInfo.path`。如果路徑匹配且 `lastChangeInfo.timestamp` 是最近的，則設定 `shouldHighlight = true`。
        *   **動態 Key:** 如果 `shouldHighlight` 為 true，則為當前元件的根 `div` 計算一個包含時間戳的動態 `key` (`dynamicKey`)；否則使用基於 `rep.id` 的靜態 `key`。這確保了高亮時元件會重新掛載以觸發動畫。
        *   **渲染:**
            *   渲染節點的類型標識 (`.viz-type-indicator`)。
            *   如果節點是 `observable_tracked: true`，則為其容器 `div` 添加 `.observable-tracked` class (提供淺藍色背景)。
            *   如果 `shouldHighlight` 為 true，則為其容器 `div` 添加 `.viz-highlight-node` class (觸發短暫的紫色背景動畫)。
            *   如果節點是可展開的容器 (list, dict, set, object) 且目前是展開狀態，則遞迴地渲染其子元素 (value 陣列或 value 物件的屬性)：
                *   為每個子元素計算**新的 `currentPath`**（在當前路徑後附加索引或鍵/屬性名）。
                *   遞迴呼叫 `RenderValue`，傳遞子元素的 `VizRepresentation`、新的 `currentPath` 和**原始的 `lastChangeInfo`**。
            *   如果節點不可展開或處於摺疊狀態，則渲染其基本值。

## 6. 通訊協定 (Communication Protocol) - `viz` 模組

### 6.1 `spawn` (Hero -> Sidekick)

*   `module`: `"viz"`
*   `method`: `"spawn"`
*   `target`: (Viz 實例 ID)
*   `payload`: `{}` (無特定 payload)

### 6.2 `update` (Hero -> Sidekick)

*   `module`: `"viz"`
*   `method`: `"update"`
*   `target`: (Viz 實例 ID)
*   `payload`:
    ```json
    {
    "variable_name": string, // 變數名稱
    "change_type": string,   // "set", "setitem", "append", ..., "remove_variable"
    "path": Array<string | number>, // 變化路徑, [] 表示根
    "value_representation": VizRepresentation | null, // 新值的表示 (適用於 set, setitem, append 等)
    "key_representation": VizRepresentation | null,   // 鍵的表示 (適用於 dict 操作)
    "length": number | null                          // 容器的新長度 (適用於容器操作)
    }
    ```

## 7. 範例程式 (Python Example)

```python
import time
from sidekick import Viz, ObservableValue

viz = Viz()

# 顯示靜態和可觀察的值
static_list = [1, 2, 3]
obs_list = ObservableValue(['a', 'b'])
obs_dict = ObservableValue({'x': 10, 'y': {'z': 20}})
counter = ObservableValue(0)

viz.show("Static List", static_list)
viz.show("Observable List", obs_list)
viz.show("Observable Dict", obs_dict)
viz.show("Counter", counter)

print("Initial state shown. Modifying observables...")
time.sleep(2)

# 修改 ObservableValue, Viz 會自動更新前端
counter.set(counter.get() + 1) # type="set", path=[]
print("Counter incremented")
time.sleep(1)

obs_list.append('c')         # type="append", path=[2]
print("List appended")
time.sleep(1)

obs_list[0] = 'A'            # type="setitem", path=[0]
print("List item changed")
time.sleep(1)

obs_dict['y']['z'] = 25      # type="setitem", path=['y', 'z'] - 注意：這假設內部字典也是 ObservableValue 或重新 show
# 如果 {'z': 20} 不是 ObservableValue，需要 obs_dict.set({...}) 或 viz.show() 才能看到更新
# --- 更好的方式: ---
new_inner_dict = obs_dict['y'].copy() # 取得內部字典副本
new_inner_dict['z'] = 25
obs_dict['y'] = new_inner_dict # type="setitem", path=['y'] -> 會更新 y 對應的值
print("Dict inner value changed (via replacing parent key)")
time.sleep(1)

obs_dict['new_key'] = 100     # type="setitem", path=['new_key']
print("Dict key added")
time.sleep(1)

# 移除變數
viz.remove_variable("Static List")
print("Static List removed")
time.sleep(1)

# 保持運行
print("Keeping script alive...")
try:
while True:
time.sleep(5)
counter.set(counter.get() + 1) # 持續更新 counter
except KeyboardInterrupt:
print("\nExiting...")
finally:
viz.remove() # 清理 Viz 模組
print("Viz removed. Script finished.")

```

## 8. 潛在問題與限制 (Potential Issues/Limitations)

*   **效能:** 對於包含極大量項目或深度嵌套的資料結構，序列化 (`_get_representation`) 和前端渲染 (`RenderValue` 遞迴) 可能會有效能瓶頸。`_MAX_DEPTH` 和 `_MAX_ITEMS` 是為了緩解這個問題。
*   **Highlight 精確度:**
    *   對於集合 (`set`) 內部元素的變化，由於集合無序，`path` 的表示比較困難，highlight 可能無法精確對應到單個元素，通常會 highlight 整個集合容器。
    *   對於字典，如果鍵是複雜物件，前端 `RenderValue` 中比較 `path` segment 可能不夠精確（目前主要基於值的比較或 ID）。
*   **非 Observable 的內部變化:** 如前所述，如果 `ObservableValue` 包裝了一個容器，而你直接修改了容器內部的**非 `ObservableValue`** 物件的屬性，`Viz` 無法自動偵測到。你需要手動觸發更新（例如再次 `viz.show()` 或修改 `ObservableValue` 的結構）。
*   **前端狀態更新複雜度:** 前端需要使用 `updateRepresentationAtPath` 這樣的輔助函式來處理來自後端的細粒度更新指令，並確保狀態的不可變性，這增加了前端邏輯的複雜度。