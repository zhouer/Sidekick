# Sidekick 模組: Canvas (畫布)

## 1. 概觀 (Overview)

`Canvas` 模組是 Sidekick 提供的一個視覺化元件，它允許使用者透過 Python 程式碼在 Sidekick UI 中繪製基本的 2D 圖形。它提供了一個簡單的畫布介面，可以在指定的區域內繪製線條、矩形、圓形等，並可設定顏色和線條樣式。

這對於視覺化演算法（例如路徑尋找、幾何圖形生成）、簡單的圖表繪製或任何需要基本圖形輸出的場景非常有用。

## 2. 功能特性 (Features)

*   **可自訂尺寸與背景:** 在建立時可以指定畫布的寬度、高度和背景顏色。
*   **基本圖形繪製:**
    *   直線 (`draw_line`)
    *   矩形 (`draw_rect` - 可填色或僅線框)
    *   圓形 (`draw_circle` - 可填色或僅線框)
*   **樣式設定:** 可以設定後續繪圖操作使用的描邊顏色 (`strokeStyle`)、填充顏色 (`fillStyle`) 和線條寬度 (`lineWidth`)。
*   **清除畫布:** 可以將畫布清除為指定的顏色（或預設背景色）。
*   **指令佇列:** 前端實作了指令佇列，確保即使 Python 端快速連續發送多個繪圖指令，也能按照順序正確繪製，避免指令丟失。

## 3. Python API (`sidekick.Canvas`)

使用者透過 `sidekick` 函式庫中的 `Canvas` 類別與畫布模組互動。

### 3.1 建立畫布 (`__init__`)

```python
from sidekick import Canvas

# 建立一個 400x300 像素，淺灰色背景的畫布
my_canvas = Canvas(width=400, height=300, bg_color='lightgrey', instance_id='drawing-area')

# 建立一個預設尺寸 (未指定則由前端決定或報錯)，白色背景的畫布
default_canvas = Canvas()
```

*   **參數:**
    *   `width` (int): 畫布寬度（像素）。
    *   `height` (int): 畫布高度（像素）。
    *   `bg_color` (Optional[str], default=None): 背景顏色字串（CSS 顏色值，如 "white", "#FF0000", "rgba(0,0,255,0.5)"）。如果為 `None`，前端通常會使用預設值（可能是白色）。
    *   `instance_id` (Optional[str], default=None): 為此畫布實例指定一個唯一的 ID。如果為 `None`，會自動產生一個。
*   **動作:** 呼叫建構子會向 Sidekick 前端發送一個 `spawn` 訊息，要求建立對應的 Canvas 元件。

### 3.2 清除畫布 (`clear`)

清除整個畫布，使用指定的顏色或預設背景色填充。

```python
# 清除為紅色
my_canvas.clear(color='red')

# 清除為預設背景色 (通常是建立時指定的 bg_color 或白色)
my_canvas.clear()
```

*   **參數:**
    *   `color` (Optional[str], default=None): 清除時使用的填充顏色。如果為 `None`，則使用畫布的預設背景色。
*   **動作:** 向前端發送 `update` 訊息，`command` 為 `"clear"`，`options` 包含可選的 `color`。

### 3.3 設定繪圖樣式 (`config`)

設定後續繪圖操作（如 `draw_line`, `draw_rect`, `draw_circle`）使用的樣式屬性。未設定的屬性保持不變。

```python
# 設定後續線條為藍色，寬度 3px
my_canvas.config(stroke_style='blue', line_width=3)

# 設定後續填充為半透明綠色
my_canvas.config(fill_style='rgba(0, 255, 0, 0.5)')

# 同時設定多個
my_canvas.config(stroke_style='black', fill_style='yellow', line_width=1)
```

*   **參數:**
    *   `stroke_style` (Optional[str]): 描邊顏色（CSS 顏色值）。
    *   `fill_style` (Optional[str]): 填充顏色（CSS 顏色值）。
    *   `line_width` (Optional[int]): 線條寬度（像素）。
*   **動作:** 向前端發送 `update` 訊息，`command` 為 `"config"`，`options` 包含傳入的樣式屬性。

### 3.4 繪製直線 (`draw_line`)

在指定的兩個點之間繪製一條直線，使用當前的 `strokeStyle` 和 `lineWidth`。

```python
# 從 (10, 10) 畫到 (100, 150)
my_canvas.draw_line(10, 10, 100, 150)
```

*   **參數:**
    *   `x1`, `y1` (int): 起點座標。
    *   `x2`, `y2` (int): 終點座標。
*   **動作:** 向前端發送 `update` 訊息，`command` 為 `"line"`，`options` 包含 `x1`, `y1`, `x2`, `y2`。

### 3.5 繪製矩形 (`draw_rect`)

在指定位置繪製一個指定尺寸的矩形。

```python
# 繪製一個左上角在 (50, 50)，寬 80，高 60 的線框矩形
my_canvas.draw_rect(50, 50, 80, 60, filled=False)

# 繪製一個左上角在 (150, 80)，寬 100，高 40 的實心填充矩形
my_canvas.config(fill_style='purple') # 先設定填充色
my_canvas.draw_rect(150, 80, 100, 40, filled=True)
```

*   **參數:**
    *   `x`, `y` (int): 矩形左上角座標。
    *   `width`, `height` (int): 矩形的寬度和高度。
    *   `filled` (bool, default=False): 如果為 `True`，則使用當前的 `fillStyle` 填充矩形；否則，使用當前的 `strokeStyle` 和 `lineWidth` 繪製線框。
*   **動作:** 向前端發送 `update` 訊息，`command` 為 `"rect"`，`options` 包含 `x`, `y`, `width`, `height`, `filled`。

### 3.6 繪製圓形 (`draw_circle`)

以指定圓心和半徑繪製一個圓形。

```python
# 繪製一個圓心在 (200, 200)，半徑 50 的線框圓
my_canvas.draw_circle(200, 200, 50, filled=False)

# 繪製一個圓心在 (300, 100)，半徑 30 的實心填充圓
my_canvas.config(fill_style='orange') # 先設定填充色
my_canvas.draw_circle(300, 100, 30, filled=True)
```

*   **參數:**
    *   `cx`, `cy` (int): 圓心座標。
    *   `radius` (int): 圓的半徑。
    *   `filled` (bool, default=False): 如果為 `True`，則使用當前的 `fillStyle` 填充圓形；否則，使用當前的 `strokeStyle` 和 `lineWidth` 繪製圓周。
*   **動作:** 向前端發送 `update` 訊息，`command` 為 `"circle"`，`options` 包含 `cx`, `cy`, `radius`, `filled`。

### 3.7 移除畫布 (`remove`)

從 Sidekick UI 中移除此畫布實例。

```python
my_canvas.remove()
```

*   **動作:** 向前端發送 `remove` 訊息，`target` 為此畫布實例的 ID。

## 4. 前端實作 (`CanvasModule.tsx`)

前端的 `CanvasModule` React 元件負責接收指令並在 HTML `<canvas>` 元素上執行繪圖。

*   **狀態 (`CanvasState`):** 儲存 `width`, `height`, `bgColor` 以及一個 `commandQueue: CanvasDrawCommand[]`。這個佇列是關鍵，用於緩存來自 Hero 端的繪圖指令。
*   **Refs:**
    *   `canvasRef`: 用於獲取實際的 `<canvas>` DOM 元素。
    *   `isProcessing`: 一個 flag ref，用於防止多個繪圖處理迴圈同時運行。
*   **`useState`:** 使用 `useState` 來儲存從 `<canvas>` 元素獲取的 `CanvasRenderingContext2D` (`ctx`)。繪圖操作必須在這個 `ctx` 上執行。
*   **`useEffect` 鉤子:**
    1.  **獲取 Context:** 在元件掛載或尺寸/背景變化時執行。它嘗試獲取 `ctx`，如果成功，將 `ctx` 存入 state，並用背景色填充一次畫布。如果畫布尺寸等發生變化，它還會清空本地的指令佇列。
    2.  **指令入隊:** 監聽來自 props 的 `state.commandQueue`。當 props 中的佇列有新指令時，它會將這些新指令（過濾掉可能已存在的）添加到元件本地的 `commandsToProcess` state 佇列中。
    3.  **處理佇列:** 監聽 `ctx` 的可用性和本地 `commandsToProcess` 佇列的變化。
        *   如果 `ctx` 可用、佇列不為空且 `isProcessing` 為 false，則開始處理。
        *   使用 `requestAnimationFrame` 以非阻塞的方式，異步地、**逐一**處理 `commandsToProcess` 佇列中的指令。
        *   在每個動畫幀中，執行一個繪圖指令（`clear`, `config`, `line` 等）。
        *   處理完畢（或出錯）後，更新 `commandsToProcess` state，移除已處理的指令，並重設 `isProcessing` flag。
*   **渲染:** 元件渲染出一個具有指定寬高和背景色的 `<canvas>` HTML 元素，並將 `canvasRef` 綁定到它上面。

## 5. 通訊協定 (Communication Protocol)

`Canvas` 模組使用標準的 `spawn` 和 `update` 方法。

### 5.1 `spawn` (Hero -> Sidekick)

*   `module`: `"canvas"`
*   `method`: `"spawn"`
*   `target`: (畫布實例 ID)
*   `payload`:
    ```json
    {
    "width": number,  // 畫布寬度
    "height": number, // 畫布高度
    "bgColor": Optional[string] // 背景顏色 (CSS 格式)
    }
    ```

### 5.2 `update` (Hero -> Sidekick)

*   `module`: `"canvas"`
*   `method`: `"update"`
*   `target`: (畫布實例 ID)
*   `payload`:
    ```json
    {
    "command": string, // "clear", "config", "line", "rect", "circle"
    "options": object, // 對應指令的參數
    "commandId": string | number // (由前端或後端確保的)唯一指令 ID
    }
    ```
    *   **`command: "clear"` Options:** `{ "color"?: string }`
    *   **`command: "config"` Options:** `{ "strokeStyle"?: string, "fillStyle"?: string, "lineWidth"?: number }`
    *   **`command: "line"` Options:** `{ "x1": number, "y1": number, "x2": number, "y2": number }`
    *   **`command: "rect"` Options:** `{ "x": number, "y": number, "width": number, "height": number, "filled"?: boolean }`
    *   **`command: "circle"` Options:** `{ "cx": number, "cy": number, "radius": number, "filled"?: boolean }`

## 6. 範例程式 (Python Example)

```python
import time
from sidekick import Canvas

try:
# 建立畫布
canvas = Canvas(width=300, height=200, bg_color="#f0f0f0", instance_id="main_canvas")
print("Canvas created.")

    # 設定樣式並繪製線條
    canvas.config(stroke_style="blue", line_width=2)
    canvas.draw_line(10, 10, 100, 80)
    canvas.draw_line(100, 80, 190, 10)
    print("Lines drawn.")
    time.sleep(0.1) # 短暫停頓讓指令有機會處理

    # 繪製矩形
    canvas.config(stroke_style="green", fill_style="lightgreen")
    canvas.draw_rect(30, 100, 80, 50, filled=True) # 實心
    canvas.draw_rect(150, 100, 60, 60, filled=False) # 線框
    print("Rectangles drawn.")
    time.sleep(0.1)

    # 繪製圓形
    canvas.config(stroke_style="red", fill_style="pink", line_width=3)
    canvas.draw_circle(250, 50, 30, filled=True) # 實心
    canvas.draw_circle(250, 150, 40, filled=False) # 線框
    print("Circles drawn.")

    # 等待一段時間看效果
    time.sleep(2)

    # 清除畫布
    canvas.clear(color='white')
    print("Canvas cleared.")

    # 讓腳本保持運行一小會兒
    time.sleep(1)

except Exception as e:
print(f"An error occurred: {e}")
finally:
# 移除畫布 (可選)
if 'canvas' in locals():
canvas.remove()
print("Canvas removed.")
print("Script finished.")
```

## 7. 潛在問題與限制 (Potential Issues/Limitations)

*   **效能:** 雖然使用了 `requestAnimationFrame`，但如果在極短時間內發送海量的繪圖指令，仍可能對瀏覽器效能造成影響。
*   **複雜圖形:** 目前只支援基本的圖元。複雜的圖形（如貝茲曲線、文字、圖片繪製）需要擴充指令集和前端繪圖邏輯。
*   **無互動:** 預設情況下，使用者無法直接在前端的 Canvas 上進行點擊等互動操作並將事件傳回 Hero 端（需要額外實作 `notify` 訊息）。
*   **狀態同步:** 前端的畫布狀態是透過執行指令序列來達成的。如果 Hero 端重新連線或前端刷新，除非 Hero 端重新發送所有繪圖指令，否則畫布狀態會丟失。它不像 Grid 或 Viz 那樣儲存完整的最終狀態表示。