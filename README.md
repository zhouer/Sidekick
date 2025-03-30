# Sidekick – Your Visual Coding Buddy

created: 2025-03-25
updated: 2025-03-26
tags: #Programming 

## 開發動機與需求背景

### 簡介

Sidekick 是一款模組化的視覺化編程輔助工具，讓初學者與進階使用者能在完整的開發環境中結合程式設計與視覺輸出。使用者透過程式碼控制畫面中的各種視覺模組（如格子畫布、文字輸出區、圖表、圖像等），即時呈現程式邏輯與執行結果。Sidekick 強調互動性與可擴充性，特別適合用於教學、親子共學、演算法視覺化等場景。

### 開發動機

- **從 Console 到視覺互動：讓程式看得見**  
    傳統程式教學多依賴純文字的 Console 輸出，缺乏視覺化呈現與即時反饋，對現代學習者（尤其是年幼的初學者）來說吸引力有限。Sidekick 在 VS Code 的 side panel 中提供視覺化界面，將程式行為轉化為動態的視覺輸出，讓抽象的邏輯變得直觀可見，從而提升學習者的理解力與學習興趣。

- **真實開發環境中的視覺化學習**  
    Sidekick 整合於完整的 IDE 環境中，VS Code 提供 debug、version control 等進階功能，讓學習者能在視覺化的輔助下逐步適應真實開發流程，為未來的進階程式設計奠定基礎。

### 需求概述

- **跨語言與跨平台的擴充潛力**  
    Sidekick 的架構設計具高度靈活性，搭配用戶端函式庫達成支援多種程式語言（如 Python、JavaScript），透過自定義的通訊協定，達成程式邏輯與顯示分離，實現跨語言跨平台互通。

- **即時雙向通訊**  
    採用 WebSocket 進行 Hero 與 Sidekick 間的即時雙向訊息交換，除了可接收來自程式的控制指令，也支援使用者操作（如點擊畫面或鍵盤輸入）回傳通知至 Hero。

- **模組化、可擴充的元件系統**  
    Sidekick 採用模組化設計，初期提供 grid 與 console 模組，未來可透過 plugin 模式擴充 image、chart、html 等更多呈現方式，甚至允許使用者註冊自定模組。

- **模組狀態維持、明確清除機制**  
    考慮到 Hero 端程式可能頻繁重啟，Sidekick 必須獨立維持狀態，直到明確接收到 `clear` 或 `reset` 指令。

- **模組自主邏輯**
    每個 module 可以有自己的邏輯與狀態，例如可以自主決定哪些訊息需要送回給 Hero，哪些不需要。較複雜的 module 例如走迷宮、生命遊戲，狀態不需要頻繁在 Hero、Sidekick 之間交流，可由 Sidekick 自主完成。

## 系統架構

### 系統分層與角色

系統整體分為兩大區塊：Hero 與 Sidekick

- **Hero**
    使用者撰寫並執行的程式（例如 Python script），負責產生視覺化訊息，透過 Sidekick library 操作 UI。Sidekick library 為封裝底層細節的高階 API，讓使用者透過直觀的物件接口操作視覺化功能，無需接觸底層通訊與模組生成邏輯。
- **Sidekick**  
    由 VS Code extension 與內嵌的 React App 組成，接收來自 Hero 的訊息，並根據訊息更新視覺化 UI。

### 架構圖

```plaintext
 +---------------------------------------+
 |                 Hero                  |
 |            (User Program)             |
 |  +-------------------------------+    |
 |  |        Sidekick Library       |    |
 |  +-------------------------------+    |
 +---------------------------------------+
                    ^
                    |  WebSocket + JSON
                    v
 +---------------------------------------+
 |               Sidekick                |
 |         (VS Code Extension)           |
 |  +-------------------------------+    |
 |  |       WebSocket Server        |    |
 |  +-------------------------------+    |
 |  +-------------------------------+    |
 |  |           React App           |    |
 |  |    (UI + Module Dispatcher)   |    |
 |  +-------------------------------+    |
 +---------------------------------------+
```

### Hero 端 – Sidekick Library

將所有底層訊息格式、WebSocket 通訊與模組生成細節封裝在 library 中，提供直觀且易用的物件導向接口。

```python
from sidekick import Grid

grid = Grid(20, 20)
grid.set_color(3, 5, 'red')
```

### Sidekick – VS Code Extension

- 內建 WebSocket Server 並轉傳 Hero 與 React App 之間的訊息
- 預設監聽 localhost:5163
- 提供 vscode command 查詢連線用的  URL

### Sidekick – React App

- 採用 React 實作，用於組件化的 UI 建構與狀態管理。
- 實現模組化的 Module Dispatcher，根據收到的訊息發送給相關的 module 處理。
- 內建兩個預設模組：
    - **grid 模組**：呈現 m x n 格子畫布，支援更新各格狀態。
    - **console 模組**：提供即時文字訊息顯示，模擬傳統 console 輸出。

## 通訊機制與訊息格式

### 通訊機制 – WebSocket

- **即時雙向通訊** 
    Hero 與 Sidekick 之間採用 WebSocket 進行雙向、即時訊息傳遞，確保程式運行狀態能夠即時反映在視覺化介面上，使用者的動作也能即時回傳給程式。
- **統一訊息格式**  
    - Hero 發送訊息至 Sidekick，包含 `id`、`module`、`method`、 `target`、`payload`
    - Sidekick 發送訊息至 Hero，包含 `id`、`module`、`method`、 `src`、`payload`

### 訊息格式 - JSON

- **Hero 建立新 instance (spawn)**  

    ```json
    {
      "id": 0,
      "module": "grid",
      "method": "spawn",
      "target": "grid-1",
      "payload": {
        "size": [20, 20]
      }
    }
    ```

- **Hero 更新 instance**  

    ```json
    {
      "id": 0,
      "module": "grid",
      "method": "update",
      "target": "grid-1",
      "payload": {
        "x": 3,
        "y": 5,
        "color": "red"
      }
    }
    ```

- **Hero 移除 instance**  

    ```json
    {
      "id": 0,
      "module": "console",
      "method": "remove",
      "target": "console-1"
    }
    ```

- **Sidekick 使用者互動訊息**  

    ```json
    {
      "id": 0,
      "module": "grid",
      "method": "notify",
      "src": "grid-1",
      "payload": {
        "x": 3,
        "y": 5,
        "event": "click"
      }
    }
    ```

- **Sidekick 回傳錯誤**  

    ```json
    {
      "id": 0,
      "module": "grid",
      "method": "error",
      "src": "grid-1",
      "payload": {
        "message": "no such instance id"
      }
    }
    ```

## 內建模組

### grid 模組

- **功能概述**  
    提供一個 m x n 的格子畫布，使用者可透過更新操作改變特定格子的顏色或其他屬性。
    
- **基本範例**
    
    1. **建立畫布**  
        當使用者調用高階 API（例如 `Grid(20, 20)`）時，library 自動將操作轉換成一筆 `spawn` 訊息：
        
        ```json
        {
          "id": 0,
          "module": "grid",
          "method": "spawn",
          "target": "grid-1",
          "payload": {
            "size": [20, 20],
          }
        }
        ```
        
    2. **更新格子狀態**  
        使用者調用 `set_color(3, 5, "red")`，library 轉換為 `update` 訊息：
        
        ```json
        {
          "id": 0,
          "module": "grid",
          "method": "update",
          "target": "grid-1",
          "payload": {
            "x": 3,
            "y": 5,
            "color": "red"
          }
        }
        ```
        

### console 模組

- **功能概述**  
    提供一個即時文字訊息顯示區域，用於展示程式運行時的資訊與輸出。
    
- **基本範例**
    
    1. **建立 console**  
        當使用者初始化 console 模組時，會產生一筆 `spawn` 訊息：
        
        ```json
        {
          "id": 0,
          "module": "console",
          "method": "spawn",
          "target": "console-1",
          "payload": {
            "text": ""
          }
        }
        ```
        
    2. **輸出訊息**  
        當程式需要輸出文字（例如 debug 訊息）時，Library 將操作轉換成 `update` 訊息：
        
        ```json
        {
          "id": 0,
          "module": "console",
          "method": "update",
          "target": "console-1",
          "payload": {
            "text": "Hello world!"
          }
        }
        ```


## 未來擴充性規劃

### 多 instance 彈性排版

多個 instances 可同時呈現在 Sidekick 的 UI 上，並提供彈性排版設定，MVP 階段採垂直放置。
