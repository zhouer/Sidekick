# Sidekick Python Library: `ObservableValue`

## 1. 概觀 (Overview)

`sidekick.ObservableValue` 是 Sidekick Python 函式庫中的一個核心類別。它扮演著一個「可觀察的」容器角色，可以包裝任何 Python 值（無論是基本型別如整數、字串，還是容器型別如列表、字典、集合）。

其主要目的是**偵測被包裝數值的變化**，並在變化發生時，**通知所有對此數值感興趣的訂閱者（Subscribers）**，同時提供關於這次變化的**詳細資訊**。

這使得 Sidekick 的其他部分（特別是 `sidekick.Viz` 視覺化模組）能夠響應資料的動態變化，並將這些變化即時反映到前端 UI 上。

## 2. 設計理念 (Design Philosophy)

`ObservableValue` 的設計遵循以下原則：

*   **通用性:** 可以包裝任何 Python 物件。
*   **反應式 (Reactive):** 當內部值改變時，能自動觸發通知。
*   **透明性 (部分):** 對於常見的容器操作（如列表的 `append`, `[]=`，字典的 `[]=`, `update` 等），使用者可以像操作原始物件一樣操作 `ObservableValue` 物件，變化會被自動偵測。但對於內部物件的屬性修改（如 `obs_obj.some_attribute = value`），則**不會**自動觸發通知。
*   **詳細通知:** 不僅僅通知「值變了」，而是提供變化的具體細節，如操作類型 (`type`)、變化的路徑 (`path`)、新值 (`value`)、涉及的鍵 (`key`)、新長度 (`length`) 等。
*   **訂閱機制:** 提供標準的發布/訂閱模式，允許任意數量的回呼函式 (Callback) 訂閱變化通知。
*   **與 `Viz` 模組整合:** `Viz` 模組可以自動識別並訂閱 `ObservableValue`，以實現資料的即時視覺化更新。

## 3. 使用方法 (Usage)

### 3.1 建立 `ObservableValue`

直接使用要包裝的初始值來實例化類別：

```python
from sidekick import ObservableValue

# 包裝基本型別
counter = ObservableValue(0)
is_active = ObservableValue(False)
message = ObservableValue("Hello")

# 包裝容器型別
my_list = ObservableValue([10, 20, 30])
my_dict = ObservableValue({"a": 1, "b": 2})
my_set = ObservableValue({1, 2, 3})

# 包裝自訂物件
class MyObject:
def __init__(self, x):
self.x = x
my_obj_instance = MyObject(100)
observed_obj = ObservableValue(my_obj_instance)
```

### 3.2 取得內部值

使用 `.get()` 方法：

```python
current_count = counter.get() # -> 0
current_list = my_list.get()   # -> [10, 20, 30]
```

### 3.3 修改內部值並觸發通知

根據值的類型，有不同的修改方式：

*   **`.set(new_value)`:** 適用於所有類型，特別是不可變類型或需要完全替換內部值的情況。這會觸發 `type="set"` 的通知。
    ```python
    counter.set(1)             # counter 現在內部是 1
    message.set("World")       # message 現在內部是 "World"
    my_list.set([1, 2])        # my_list 被完全替換成 [1, 2]
    ```

*   **攔截的容器方法:** 對於列表、字典、集合，可以直接使用它們的標準方法。`ObservableValue` 會攔截這些呼叫，執行操作，然後觸發帶有詳細資訊的通知。

    *   **列表 (`list`)**
        ```python
        my_list = ObservableValue([10, 20])

        my_list.append(30)        # 觸發 type="append", path=[2], value=30, length=3
        my_list[0] = 15           # 觸發 type="setitem", path=[0], value=15
        popped_value = my_list.pop() # 觸發 type="pop", path=[2], old_value=30, length=2
        # popped_value is 30
        del my_list[0]            # 觸發 type="delitem", path=[0], old_value=15, length=1
        my_list.clear()           # 觸發 type="clear", path=[], value=[], length=0
        my_list.insert(0, 5)      # 觸發 type="insert", path=[0], value=5, length=1
        ```
    *   **字典 (`dict`)**
        ```python
        my_dict = ObservableValue({"a": 1})

        my_dict["b"] = 2          # 觸發 type="setitem", path=['b'], value=2, key='b'
        my_dict["a"] = 5          # 觸發 type="setitem", path=['a'], value=5, key='a', old_value=1
        my_dict.update({"c": 3})  # 會觸發一次或多次 "setitem" (取決於內部實作，目前是一次)
        # 例如：觸發 type="setitem", path=['c'], value=3, key='c'
        del my_dict["a"]          # 觸發 type="delitem", path=['a'], old_value=5, key='a'
        my_dict.clear()           # 觸發 type="clear", path=[], value={}, length=0
        ```
    *   **集合 (`set`)**
        ```python
        my_set = ObservableValue({1, 2})

        my_set.add(3)             # 觸發 type="add_set", path=[], value=3, length=3
        my_set.add(1)             # 不觸發通知，因為集合內容未改變
        my_set.discard(2)         # 觸發 type="discard_set", path=[], old_value=2, length=2
        my_set.discard(5)         # 不觸發通知，因為 5 不在集合中
        my_set.clear()            # 觸發 type="clear", path=[], value=set(), length=0
        ```

*   **注意：直接修改內部物件屬性**
    如果 `ObservableValue` 包裝的是一個自訂物件，直接修改該物件的屬性**不會**觸發 `ObservableValue` 的通知：
    ```python
    observed_obj.get().x = 200 # observed_obj 本身不會發出通知
    # 或者 (效果相同)
    observed_obj.x = 200         # 透過 __getattr__ / __setattr__ 代理，但預設不通知
    ```
    如果希望這種修改被偵測到，你需要：
    1.  再次呼叫 `.set()` 把修改後的物件重新設定回去：`observed_obj.set(observed_obj.get())` （如果物件 ID 沒變，可能不會觸發通知）或 `observed_obj.set(new_obj_instance)`。
    2.  或者，如果這個物件在 `Viz` 中顯示，你需要再次呼叫 `viz.show("observed_obj", observed_obj)` 來強制更新前端。
    3.  更進階的方式是讓 `MyObject` 本身也實現類似的觀察者模式，並在 `ObservableValue` 的回呼中觸發。

### 3.4 訂閱變化

使用 `.subscribe(callback)` 方法註冊一個回呼函式。這個函式會在每次內部值發生變化（且觸發通知）時被呼叫。

回呼函式會接收一個字典參數，包含變化的詳細資訊。

`.subscribe()` 方法會返回一個「取消訂閱」函式，呼叫它可以移除這個特定的回呼。

```python
def my_callback(change_details):
print(f"Value changed! Details: {change_details}")

# 訂閱
unsubscribe_func = counter.subscribe(my_callback)

counter.set(5)
# 輸出: Value changed! Details: {'type': 'set', 'path': [], 'value': 5, 'old_value': 1, 'key': None, 'length': None}

my_list.append(40)
# (如果 my_list 也訂閱了 my_callback)
# 輸出: Value changed! Details: {'type': 'append', 'path': [1], 'value': 40, 'length': 2, 'key': None, 'old_value': None}


# 取消訂閱
unsubscribe_func()

counter.set(10) # my_callback 不再被呼叫
```

### 3.5 取消訂閱

有兩種方式取消訂閱：

1.  呼叫 `.subscribe()` 返回的取消訂閱函式。
2.  使用 `.unsubscribe(callback)` 方法，傳入原始的回呼函式。

```python
# 方法 1
unsubscribe = counter.subscribe(my_callback)
# ...
unsubscribe()

# 方法 2
counter.subscribe(my_callback)
# ...
counter.unsubscribe(my_callback)
```

## 4. 內部運作細節 (Internal Mechanics)

1.  **儲存:** 內部值存於 `self._value`。訂閱者回呼函式存於 `self._subscribers` (一個 Set)。每個 `ObservableValue` 實例還有一個內部 ID `self._obs_value_id`，用於 `Viz` 模組產生穩定的視覺化節點 ID。
2.  **方法攔截 (Method Interception):**
    *   對於 `.set()`，直接更新 `self._value` 並呼叫 `_notify({"type": "set", ...})`。
    *   對於容器的特殊方法 (如 `append`, `__setitem__` 等)，`ObservableValue` 提供了同名的方法。這些方法：
        *   首先，呼叫 `self._value` 上**真正**的同名方法來修改內部值（例如 `self._value.append(item)`）。
        *   然後，**收集**這次操作的詳細資訊（操作類型、路徑、新值、舊值、鍵、長度等）。
        *   最後，呼叫 `self._notify(change_details)`。
3.  **`_notify(change_details)`:**
    *   檢查是否有訂閱者，如果沒有則直接返回。
    *   確保 `change_details` 字典包含所有必要欄位（即使是 `None`）。
    *   為了防止在通知過程中訂閱者列表被修改（例如某個回呼函式取消了自己的訂閱），它會先複製一份當前的訂閱者列表。
    *   遍歷複製的列表，逐一呼叫每個回呼函式，並將 `change_details` 字典傳遞給它們。
    *   包含基本的錯誤處理，如果某個回呼函式拋出異常，會印出錯誤訊息但繼續通知其他訂閱者。
4.  **屬性/方法代理 (`__getattr__`, `__setattr__`):**
    *   `__getattr__(name)`: 當你試圖存取 `ObservableValue` 物件上不存在的屬性或方法時（例如 `observed_obj.x` 或 `my_list.sort()`），這個方法會被呼叫。它會嘗試從內部 `self._value` 上取得同名屬性或方法並返回。**預設情況下，這不會觸發通知**。
    *   `__setattr__(name, value)`: 當你試圖設定 `ObservableValue` 物件上的屬性時（例如 `observed_obj.x = 100`），如果該屬性不是 `ObservableValue` 的內部屬性（如 `_value`, `_subscribers`），它會嘗試在內部 `self._value` 上設定同名屬性。**預設情況下，這也不會觸發通知**。
5.  **其他 Dunder 方法:** `__len__`, `__getitem__`, `__iter__`, `__contains__`, `__repr__`, `__str__`, `__eq__` 等方法也通常被實作，將操作代理到內部的 `self._value` 上，使得 `ObservableValue` 在很多情況下可以像原始物件一樣使用（例如 `len(my_list)` 會返回內部列表的長度）。

## 5. 與 `Viz` 模組的整合

`Viz` 模組是 `ObservableValue` 的主要「客戶」之一。

*   `viz.show()` 會自動呼叫 `observable_value.subscribe()`，將 `Viz` 內部的一個處理函式 (`_handle_observable_update`) 註冊為訂閱者。
*   當 `ObservableValue` 觸發 `_notify(change_details)` 時，`Viz` 的 `_handle_observable_update` 會收到這個包含詳細資訊的 `change_details` 字典。
*   `Viz` 會解析 `change_details`，產生必要的視覺化表示（只針對變化涉及的值），並構建一個符合 Sidekick 通訊協定的 `update` WebSocket 訊息，將 `change_type`, `path`, `value_representation`, `key_representation`, `length` 等資訊發送給前端。
*   `viz.remove_variable()` 會負責呼叫儲存的取消訂閱函式，斷開 `Viz` 與 `ObservableValue` 的連結。

## 6. 總結

`ObservableValue` 提供了一個強大而靈活的方式來追蹤 Python 值的變化。透過攔截關鍵的修改操作並提供詳細的變化通知，它使得 `Viz` 模組能夠高效地將 Python 端的資料動態同步到前端視覺化介面，為 Sidekick 提供了核心的反應式更新能力。理解其攔截機制和通知細節對於有效地使用 Sidekick 進行視覺化偵錯和互動式程式設計至關重要。