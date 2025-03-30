# Sidekick 模組: Canvas (畫布)

## 1. 概觀 (Overview)

`Canvas` 模組是 Sidekick 提供的一個視覺化元件，它允許使用者透過 Python 程式碼在 Sidekick UI 中繪製基本的 2D 圖形。它提供了一個可自訂尺寸和背景色的畫布介面，可以在指定的區域內繪製線條、矩形、圓形等，並可設定顏色和線條樣式。

這對於視覺化演算法（例如路徑尋找、幾何圖形生成）、簡單的圖表繪製或任何需要基本圖形輸出的場景非常有用。

## 2. 功能特性 (Features)

*   **可自訂尺寸與背景:** 在建立時可以指定畫布的寬度、高度和背景顏色。
*   **基本圖形繪製:**
    *   直線 (`draw_line`)
    *   矩形 (`draw_rect` - 可填色或僅線框)
    *   圓形 (`draw_circle` - 可填色或僅線框)
*   **樣式設定:** 可以設定後續繪圖操作使用的描邊顏色 (`strokeStyle`)、填充顏色 (`fillStyle`) 和線條寬度 (`lineWidth`)。
*   **清除畫布:** 可以將畫布清除為指定的顏色（或預設背景色）。
*   **指令佇列處理:** 前端能可靠地處理來自 Python 端快速連續發送的多個繪圖指令，確保按順序繪製，避免指令丟失或重複繪製。

## 3. Python API (`sidekick.Canvas`)

使用者透過 `sidekick` 函式庫中的 `Canvas` 類別與畫布模組互動。

### 3.1 建立畫布 (`__init__`)

```python
from sidekick import Canvas

# 建立一個 400x300 像素，淺灰色背景的畫布
my_canvas = Canvas(width=400, height=300, bg_color='lightgrey', instance_id='drawing-area')

# 建立一個預設尺寸 (依賴前端實現)，白色背景的畫布
default_canvas = Canvas()
```

*   **參數:** `width`(int), `height`(int), `bg_color`(Optional[str]), `instance_id`(Optional[str])。
*   **動作:** 向 Sidekick 前端發送 `spawn` 訊息，要求建立對應的 Canvas 元件。

### 3.2 清除畫布 (`clear`)

清除整個畫布，使用指定的顏色或預設背景色填充。

```python
my_canvas.clear(color='red') # 清除為紅色
my_canvas.clear()          # 清除為預設背景色
```

*   **參數:** `color`(Optional[str])。
*   **動作:** 向前端發送 `update` 訊息 (`command="clear"`)。

### 3.3 設定繪圖樣式 (`config`)

設定後續繪圖操作使用的樣式屬性。

```python
my_canvas.config(stroke_style='blue', line_width=3)
my_canvas.config(fill_style='rgba(0, 255, 0, 0.5)')
```

*   **參數:** `stroke_style`(Optional[str]), `fill_style`(Optional[str]), `line_width`(Optional[int])。
*   **動作:** 向前端發送 `update` 訊息 (`command="config"`)。

### 3.4 繪製直線 (`draw_line`)

在指定的兩個點之間繪製一條直線。

```python
my_canvas.draw_line(10, 10, 100, 150)
```

*   **參數:** `x1`(int), `y1`(int), `x2`(int), `y2`(int)。
*   **動作:** 向前端發送 `update` 訊息 (`command="line"`)。

### 3.5 繪製矩形 (`draw_rect`)

在指定位置繪製一個指定尺寸的矩形（可選填充）。

```python
my_canvas.draw_rect(50, 50, 80, 60, filled=False) # 線框
my_canvas.draw_rect(150, 80, 100, 40, filled=True) # 實心
```

*   **參數:** `x`(int), `y`(int), `width`(int), `height`(int), `filled`(bool, default=False)。
*   **動作:** 向前端發送 `update` 訊息 (`command="rect"`)。

### 3.6 繪製圓形 (`draw_circle`)

以指定圓心和半徑繪製一個圓形（可選填充）。

```python
my_canvas.draw_circle(200, 200, 50, filled=False) # 線框
my_canvas.draw_circle(300, 100, 30, filled=True)  # 實心
```

*   **參數:** `cx`(int), `cy`(int), `radius`(int), `filled`(bool, default=False)。
*   **動作:** 向前端發送 `update` 訊息 (`command="circle"`)。

### 3.7 移除畫布 (`remove`)

從 Sidekick UI 中移除此畫布實例。

```python
my_canvas.remove()
```

*   **動作:** 向前端發送 `remove` 訊息。

## 4. 前端實作 (`CanvasModule.tsx`)

前端的 `CanvasModule` React 元件負責接收指令並在 HTML `<canvas>` 元素上執行繪圖。其核心機制如下：

*   **狀態 (`CanvasState`):** 儲存 `width`, `height`, `bgColor` 以及一個**指令佇列 `commandQueue: CanvasDrawCommand[]`**。這個佇列包含了所有從 Hero 端接收到但尚未被處理的繪圖指令。
*   **Refs:**
    *   `canvasRef`: 用於獲取實際的 `<canvas>` DOM 元素。
    *   `lastProcessedCommandId`: 儲存最後一個**成功處理完畢**的指令的 `commandId`。這是一個關鍵的 Ref，用於追蹤處理進度，防止指令被重複執行。
*   **`useState`:** 使用 `useState` 來儲存從 `<canvas>` 元素獲取的 2D 渲染上下文 `CanvasRenderingContext2D` (`ctx`)。所有繪圖操作都在此 `ctx` 上執行。
*   **`useEffect` 鉤子:**
    1.  **獲取 Context 與初始化:**
        *   在元件掛載或 `width`, `height`, `bgColor` 變化時執行。
        *   嘗試獲取 `ctx`，成功後存入 `ctx` state。
        *   使用 `bgColor` 對畫布進行初始填充。
        *   重設 `lastProcessedCommandId` 為 `null`，表示需要從頭處理指令佇列。
    2.  **處理指令佇列:**
        *   在 `ctx` 可用**且**來自 props 的 `commandQueue` 發生變化時執行。
        *   檢查 `commandQueue` 是否為空。
        *   **查找起點:** 使用 `lastProcessedCommandId.current` 在 `commandQueue` 中查找上一次處理到的位置，確定本次需要處理的**新指令**的起始索引 `startIndex`。
        *   **同步批次處理:** 如果 `startIndex` 指向有效的指令（即有新指令需要處理），則**同步地**遍歷從 `startIndex` 開始到 `commandQueue` 末尾的所有指令：
            *   對於每個指令，執行對應的 Canvas 繪圖操作（`fillRect`, `stroke`, `arc` 等）。
            *   使用 `try...catch` 包裹繪圖操作，如果某個指令出錯，則停止處理當前批次的剩餘指令，並記錄錯誤。
            *   記錄下當前批次中最後一個**成功執行**的指令的 `commandId`。
        *   **更新進度:** 在處理完（或因錯誤停止）當前批次的所有新指令後，將最後成功執行的指令 ID 更新到 `lastProcessedCommandId.current` Ref 中。

*   **渲染:** 元件渲染出一個具有指定寬高和背景色的 `<canvas>` HTML 元素，並將 `canvasRef` 綁定到它上面。

*   **處理邏輯說明:** 這種設計確保了：
    *   指令按接收順序處理。
    *   透過追蹤 `lastProcessedCommandId`，避免了因 React 重新渲染而導致的指令重複執行。
    *   在單次渲染週期內到達的一批新指令會被同步處理，保證了狀態的一致性。

## 5. 通訊協定 (Communication Protocol) - `canvas` 模組

`Canvas` 模組使用標準的 `spawn` 和 `update` 方法。

### 5.1 `spawn` (Hero -> Sidekick)

*   `module`: `"canvas"`
*   `method`: `"spawn"`
*   `target`: (畫布實例 ID)
*   `payload`:
    ```json
    {
    "width": number,
    "height": number,
    "bgColor"?: string
    }
    ```

### 5.2 `update` (Hero -> Sidekick)

*   `module`: `"canvas"`
*   `method`: `"update"`
*   `target`: (畫布實例 ID)
*   `payload` (代表一個繪圖或設定指令):
    ```json
    {
    "command": string, // "clear", "config", "line", "rect", "circle"
    "options": object, // 指令參數
    "commandId": string | number // 唯一指令 ID
    }
    ```
    *   **Options 詳見 Python API 部分的說明。**

## 6. 範例程式 (Python Example)

```python
import time
import math
from sidekick import Canvas

try:
canvas = Canvas(width=300, height=200, bg_color="#f0f0f0")
print("Canvas created.")
time.sleep(0.1) # 短暫等待確保 spawn 完成

    # 快速連續發送指令
    canvas.config(stroke_style="red", line_width=1)
    for i in range(0, 300, 10):
        canvas.draw_line(0, 0, i, 199)

    canvas.config(stroke_style="blue")
    for i in range(0, 200, 10):
        canvas.draw_line(299, 0, 0, i)

    print("Multiple draw commands sent quickly.")
    time.sleep(2) # 等待繪製完成

    canvas.clear()
    print("Canvas cleared.")
    time.sleep(1)

except Exception as e:
print(f"An error occurred: {e}")
finally:
if 'canvas' in locals():
canvas.remove()
print("Canvas removed.")
print("Script finished.")
```

## 7. 潛在問題與限制 (Potential Issues/Limitations)

*   **效能:** 雖然當前是同步處理批次指令，但如果 Hero 端在極短時間（單次 React 更新週期內）內發送了**超級大量**的指令，同步迴圈仍然可能導致短暫的 UI 卡頓。若遇到此情況，可能需要重新評估是否改回 `requestAnimationFrame` 配合更複雜的狀態管理。
*   **複雜圖形:** 目前僅支援基本圖元。
*   **無互動:** 預設不處理前端 Canvas 上的使用者互動。
*   **狀態易失:** Canvas 的視覺狀態是執行繪圖指令序列的結果。重新整理頁面或重新連線會導致畫布變為空白，除非 Hero 端重新發送所有指令。