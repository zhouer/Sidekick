# Issues

1. 加強錯誤處理機制
    1. spawn 的錯誤無法用 on_error 捕捉
2. 從 sidekick 清除元件/重整頁面 應該通知 hero
3. canvas 使用 requestAnimationFrame
4. 網頁版的 playground，使用 Pyodide 執行 Python 程式，透過 postMessage 與 webapp 直接通信，不經過 WebSocket
5. 提供一個機制讓 sidekick 通知 Python 程式來不及處理訊息 
