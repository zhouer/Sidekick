# Issues

1. 先執行程式再打開 sidekick，python library 要一直重連 
2. 加強錯誤處理機制
    1. spawn 的錯誤無法用 on_error 捕捉
3. 從 sidekick 清除元件/重整頁面 應該通知 hero
4. canvas 使用 requestAnimationFrame
5. 網頁版的 playground，使用 Pyodide 執行 Python 程式，透過 postMessage 與 webapp 直接通信，不經過 WebSocket
6. 提供一個機制讓 sidekick 通知 Python 程式來不及處理訊息 
