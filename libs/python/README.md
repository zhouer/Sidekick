# Sidekick Python Library (`sidekick-py`)

## 1. Overview

This library provides the Python interface ("Hero") for interacting with the Sidekick Visual Coding Buddy frontend UI. It allows Python scripts to easily create, update, interact with, and remove visual modules like grids, consoles, variable visualizers, drawing canvases, and UI controls within the Sidekick UI, typically via a mediating WebSocket Server.

The library abstracts the underlying WebSocket communication and JSON message formatting, offering an intuitive object-oriented API. It handles connection management, peer discovery, message buffering, event handling, and provides mechanisms for controlling the script's lifecycle and synchronizing with the Sidekick frontend state.

## 2. Key Features

*   **Object-Oriented API:** Control visual modules (`Grid`, `Console`, `Viz`, `Canvas`, `Control`) via Python classes and methods (using standard Python `snake_case`).
*   **Simplified Event Handling:**
    *   Register specific callbacks (e.g., `on_click`, `on_input_text`) directly on module instances.
    *   All modules provide an `on_error(callback)` method.
*   **Automatic Connection Management:**
    *   Lazy connection establishment (connects on first use).
    *   Manages WebSocket connection state (`DISCONNECTED`, `CONNECTING`, `CONNECTED_WAITING_SIDEKICK`, `CONNECTED_READY`).
    *   Handles keep-alive (Ping/Pong) via `websocket-client`.
    *   Runs a background listener thread (daemon) for incoming messages with timeouts for clean shutdown.
    *   Attempts graceful shutdown on normal script exit via `atexit`.
*   **Peer Discovery & Status:** Automatically announces itself (`system/announce` with `role: "hero"`) and listens for Sidekick (`role: "sidekick"`) announcements to determine readiness (`CONNECTED_READY` state).
*   **Message Buffering:** Automatically queues outgoing commands if Sidekick is not yet `CONNECTED_READY`. The buffer is flushed when Sidekick becomes ready.
*   **Configuration:** Set WebSocket URL and automatic clearing behavior (`clear_on_connect`, `clear_on_disconnect`).
*   **Re-attachment Support:** Module constructors support `spawn=False` to attach to existing UI elements.
*   **Reactive Visualization (`ObservableValue`):** A wrapper class to track changes in Python objects, enabling automatic, granular updates in the `Viz` module.
*   **Lifecycle Control:**
    *   `run_forever()`: Keeps the script running to process events indefinitely.
    *   `shutdown()`: Signals `run_forever` to exit and cleans up the connection.
*   **Synchronization Primitives:**
    *   `ensure_ready()`: Blocks until Sidekick connection is established and ready.
    *   `flush_messages()`: Blocks until Sidekick is ready and all buffered messages have been sent.
*   **Global Message Handling:** Option to register a handler to inspect all incoming messages.

## 3. Installation

**Standard Installation (from PyPI):**

```bash
pip install sidekick-py
```

**Development Installation (from project root):**

Install editable mode to link the installed package to your source code:

```bash
pip install -e libs/python
```

## 4. Core Concepts

### 4.1. Connection Management (`connection.py`)

*   **Singleton & State Machine:** Manages a single, shared WebSocket connection using a state machine (`ConnectionStatus`: `DISCONNECTED`, `CONNECTING`, `CONNECTED_WAITING_SIDEKICK`, `CONNECTED_READY`). Thread-safety is managed using an `RLock`.
*   **Lazy Connection:** The connection attempt is automatically triggered only when the first module is instantiated or when `sidekick.activate_connection()` is explicitly called.
*   **Configuration (`set_url`, `set_config`):** These global functions **must** be called *before* the first connection attempt is made.
    *   `set_url(url: str)`: Sets the WebSocket server URL (defaults to `ws://localhost:5163`).
    *   `set_config(clear_on_connect: bool = True, clear_on_disconnect: bool = False)`:
        *   `clear_on_connect`: If True, sends `global/clearAll` *after* the connection becomes `CONNECTED_READY`.
        *   `clear_on_disconnect`: If True, attempts (best-effort) to send `global/clearAll` during the `close_connection` process.
*   **Listener Thread (`_listen_for_messages`):**
    *   Runs as a background daemon thread to receive messages.
    *   Uses a timeout on `websocket.recv()` to ensure it can periodically check for stop signals, allowing for clean shutdowns.
    *   Handles `system/announce` messages to update peer status.
    *   Dispatches incoming `event` and `error` messages to the appropriate module instance handler.
    *   Calls the optional global message handler.
*   **Threading Events & Conditions:** Uses `threading.Event` (`_stop_event`, `_ready_event`, `_shutdown_event`) and `threading.Condition` (`_buffer_flushed_and_ready_condition`) internally to coordinate thread startup, shutdown, readiness checks, and message flushing.
*   **Shutdown Process (`close_connection`, `shutdown`, `atexit`):**
    *   `close_connection` is the core cleanup function. It signals the listener thread to stop (`_stop_event.set()`), closes the WebSocket, and cleans up resources.
    *   `shutdown` signals `run_forever` to exit (`_shutdown_event.set()`) and then calls `close_connection`.
    *   `atexit.register(shutdown)` ensures that on normal Python interpreter exit, the `shutdown` process is attempted, allowing the listener thread to terminate gracefully and the program to exit cleanly.

### 4.2. Peer Discovery & Message Buffering

*   **Announcements:** On connection, Hero sends `system/announce` (`role: "hero", status: "online"`). It listens for `system/announce` from Sidekick peers (`role: "sidekick"`).
*   **Ready State:** When the first Sidekick peer announces `online`, the connection status transitions to `CONNECTED_READY`. The `_ready_event` is set.
*   **Buffering:** Messages sent via module methods (e.g., `grid.set_cell`) before the status is `CONNECTED_READY` are queued in an internal buffer (`_message_buffer`).
*   **Flushing:** When the status becomes `CONNECTED_READY`, the buffer is automatically flushed, sending queued messages. The `_buffer_flushed_and_ready_condition` is notified when the buffer becomes empty while in the ready state.

### 4.3. Message Handling & Callbacks

*   **Dispatch:** Incoming messages are first passed to the optional global handler. Messages with a `src` field (indicating the source module instance) are then routed to the `_internal_message_handler` method of the corresponding Python module object (e.g., a specific `Grid` instance).
*   **Internal Handler:** `BaseModule._internal_message_handler` handles `error` messages by calling the `on_error` callback. Module subclasses override this method to handle specific `event` messages (e.g., `type: "event", payload: {"event": "click", ...}`) and invoke the relevant user callback (e.g., `on_click`).
*   **Specific Callbacks:** Users interact with events primarily through methods like `grid.on_click(my_handler)`, `console.on_input_text(my_handler)`, etc., abstracting the message parsing.

### 4.4. Module Interaction (`BaseModule`, `spawn`)

*   **Base Class:** `BaseModule` provides common functionality: ID management, connection activation, sending commands (`_send_command`, `_send_update`), `remove()` method, and `on_error` registration.
*   **Instance ID (`instance_id`):** Uniquely identifies a module instance between Hero and Sidekick. Can be auto-generated or specified.
*   **`spawn=True` (Default):** Creates a *new* visual instance in Sidekick by sending a `spawn` command.
*   **`spawn=False`:** Attaches the Python object to an *existing* visual instance in Sidekick (requires `instance_id`). No `spawn` command is sent.
*   **Payloads:** Internal methods ensure outgoing message payloads use `camelCase` keys as required by the protocol.

### 4.5. Reactivity (`ObservableValue`, `Viz`)

*   **`ObservableValue`:** A wrapper class for Python values. It intercepts common mutation methods (e.g., `append`, `__setitem__`, `add`, `set`) and notifies subscribed callbacks with detailed change information.
*   **`Viz` Integration:**
    *   `viz.show(name, value)`: Displays a variable. If `value` is an `ObservableValue`, `Viz` subscribes to it.
    *   `_handle_observable_update`: Internal callback in `Viz` triggered by `ObservableValue` changes. It translates the change details into granular `update` messages (e.g., `action: "setitem"`) for Sidekick, enabling efficient UI updates.

### 4.6. Lifecycle Control (`run_forever`, `shutdown`)

*   **`run_forever()`:** Call this if your script needs to stay alive to react to events (like button clicks or console input) after the main setup code has finished. It blocks the main thread until `shutdown()` is called or Ctrl+C is pressed.
*   **`shutdown()`:** Explicitly stops the `run_forever` loop (if running) and initiates the connection closing process. Safe to call multiple times or even if `run_forever` wasn't used. Automatically called on normal program exit via `atexit`.

### 4.7. Synchronization (`ensure_ready`, `flush_messages`)

*   **`ensure_ready(timeout=None)`:** Blocks execution until the connection has reached the `CONNECTED_READY` state (meaning at least one Sidekick frontend is connected and has announced itself). Useful at the start of a script to wait for Sidekick before sending commands.
*   **`flush_messages(timeout=None)`:** Blocks execution until the connection is `CONNECTED_READY` *and* the internal outgoing message buffer is empty. Useful at the end of a short-lived script to increase the likelihood that Sidekick received all sent commands before the script exits (without needing `time.sleep` or `run_forever`).

## 5. API Reference

*(Note: All methods sending messages construct payloads with `camelCase` keys as required by the protocol. Non-system messages are buffered until the connection is `CONNECTED_READY`.)*

### 5.1. Top-Level Functions (`sidekick` namespace)

*   `sidekick.set_url(url: str)`
    *   Sets the WebSocket Server URL (e.g., `"ws://localhost:5163"`).
    *   **Must be called before the first connection attempt.**
*   `sidekick.set_config(clear_on_connect: bool = True, clear_on_disconnect: bool = False)`
    *   Configures automatic clearing behavior.
    *   `clear_on_connect`: Sends `global/clearAll` when Sidekick becomes ready.
    *   `clear_on_disconnect`: Attempts to send `global/clearAll` on disconnect.
    *   **Must be called before the first connection attempt.**
*   `sidekick.activate_connection()`
    *   Ensures the connection attempt is initiated if currently disconnected.
    *   Called automatically by module constructors. Safe to call multiple times.
*   `sidekick.clear_all()`
    *   Sends a `global/clearAll` message to Sidekick (buffered if connection not ready).
*   `sidekick.close_connection(log_info=True)`
    *   Manually initiates the closing of the WebSocket connection and cleanup. Consider using `shutdown()` instead for consistency with `atexit` and `run_forever`.
*   `sidekick.shutdown()`
    *   Initiates the clean shutdown process: signals `run_forever` to exit (if running), stops the listener thread, and closes the WebSocket connection.
    *   This is the recommended way to programmatically stop the connection. Automatically called by `atexit`.
*   `sidekick.run_forever()`
    *   Blocks the main thread, keeping the script alive to process incoming events.
    *   Exits when `shutdown()` is called or Ctrl+C is pressed.
*   `sidekick.ensure_ready(timeout: Optional[float] = None) -> bool`
    *   Blocks until the connection status is `CONNECTED_READY` or the timeout (in seconds) expires.
    *   Returns `True` if ready, `False` on timeout or disconnection.
*   `sidekick.flush_messages(timeout: Optional[float] = None) -> bool`
    *   Blocks until the connection is `CONNECTED_READY` and the outgoing message buffer is empty, or the timeout (in seconds) expires.
    *   Returns `True` if flushed while ready, `False` on timeout or disconnection.
*   `sidekick.register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]])`
    *   Registers or unregisters a single handler function that will be called with *every* message dictionary received from Sidekick. Use `None` to unregister.

### 5.2. `sidekick.ObservableValue`

*   `ObservableValue(initial_value: Any)`
    *   Wraps a Python value to enable change tracking.
*   **Methods:**
    *   `.get() -> Any`: Returns the current wrapped value.
    *   `.set(new_value: Any)`: Sets a new value, triggering a "set" notification.
    *   `.subscribe(callback: Callable[[Dict[str, Any]], None]) -> Callable[[], None]`: Registers a callback for change notifications. Returns an unsubscribe function.
    *   `.unsubscribe(callback: Callable[[Dict[str, Any]], None])`: Removes a specific callback.
*   **Intercepted Methods (trigger notifications):** `.append()`, `.insert()`, `.pop()`, `.remove()`, `.clear()`, `.__setitem__()`, `.__delitem__()`, `.update()` (for dicts), `.add()`, `.discard()` (for sets).
*   **Other Dunder Methods:** Delegates common methods like `__getattr__`, `__repr__`, `__str__`, `__eq__`, `__len__`, `__getitem__`, `__iter__`, `__contains__` to the wrapped value.

### 5.3. `sidekick.Grid`

*   `Grid(num_columns: int = 16, num_rows: int = 16, instance_id: Optional[str] = None, spawn: bool = True)`
    *   Represents a grid module.
    *   `spawn=False` requires `instance_id`.
*   **Methods:**
    *   `.set_cell(x: int, y: int, color: Optional[str] = None, text: Optional[str] = None)`: Sets cell state (column `x`, row `y`).
    *   `.set_color(x: int, y: int, color: Optional[str])`: Sets only the cell color.
    *   `.set_text(x: int, y: int, text: Optional[str])`: Sets only the cell text.
    *   `.clear()`: Clears the entire grid.
    *   `.remove()`: Removes this grid instance from Sidekick.
*   **Event Handlers:**
    *   `.on_click(callback: Optional[Callable[[int, int], None]])`: Registers a function called with `x`, `y` when a cell is clicked. Pass `None` to unregister.
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function called with an error message string specific to this instance. Pass `None` to unregister.

### 5.4. `sidekick.Console`

*   `Console(instance_id: Optional[str] = None, spawn: bool = True, initial_text: str = "", show_input: bool = False)`
    *   Represents a console module.
    *   `spawn=False` requires `instance_id`; `initial_text` and `show_input` are ignored.
*   **Methods:**
    *   `.print(*args: Any, sep: str = ' ', end: str = '')`: Prints text to the console.
    *   `.log(message: Any)`: Shortcut for `.print(message)`.
    *   `.clear()`: Clears the console text.
    *   `.remove()`: Removes this console instance from Sidekick.
*   **Event Handlers:**
    *   `.on_input_text(callback: Optional[Callable[[str], None]])`: Registers a function called with the submitted text (requires `show_input=True`). Pass `None` to unregister.
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function for instance-specific errors. Pass `None` to unregister.

### 5.5. `sidekick.Viz`

*   `Viz(instance_id: Optional[str] = None, spawn: bool = True)`
    *   Represents a variable visualizer module.
    *   `spawn=False` requires `instance_id`.
*   **Methods:**
    *   `.show(name: str, value: Any)`: Displays/updates a variable. Subscribes automatically if `value` is an `ObservableValue`.
    *   `.remove_variable(name: str)`: Removes a variable display. Unsubscribes if applicable.
    *   `.remove()`: Removes this viz instance from Sidekick. Unsubscribes all tracked observables.
*   **Event Handlers:**
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function for instance-specific errors. Pass `None` to unregister. *(Note: Viz currently doesn't emit user interaction events like 'click'.)*

### 5.6. `sidekick.Canvas`

*   `Canvas(width: int, height: int, instance_id: Optional[str] = None, spawn: bool = True, bg_color: Optional[str] = None)`
    *   Represents a 2D drawing canvas module.
    *   `spawn=False` requires `instance_id`; `width`, `height`, `bg_color` are ignored.
*   **Methods:**
    *   `.clear(color: Optional[str] = None)`: Clears the canvas, optionally filling with a color.
    *   `.config(stroke_style: Optional[str] = None, fill_style: Optional[str] = None, line_width: Optional[int] = None)`: Configures drawing styles.
    *   `.draw_line(x1: int, y1: int, x2: int, y2: int)`: Draws a line.
    *   `.draw_rect(x: int, y: int, width: int, height: int, filled: bool = False)`: Draws a rectangle (outline or filled).
    *   `.draw_circle(cx: int, cy: int, radius: int, filled: bool = False)`: Draws a circle (outline or filled).
    *   `.remove()`: Removes this canvas instance from Sidekick.
*   **Event Handlers:**
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function for instance-specific errors. Pass `None` to unregister. *(Note: Canvas currently doesn't emit user interaction events.)*

### 5.7. `sidekick.Control`

*   `Control(instance_id: Optional[str] = None, spawn: bool = True)`
    *   Represents a UI control panel module.
    *   `spawn=False` requires `instance_id`.
*   **Methods:**
    *   `.add_button(control_id: str, text: str)`: Adds a button.
    *   `.add_text_input(control_id: str, placeholder: str = "", initial_value: str = "", button_text: str = "Submit")`: Adds a text input field with a submit button.
    *   `.remove_control(control_id: str)`: Removes a specific button or text input by its ID.
    *   `.remove()`: Removes this control panel instance from Sidekick.
*   **Event Handlers:**
    *   `.on_click(callback: Optional[Callable[[str], None]])`: Registers a function called with the `controlId` when a button is clicked. Pass `None` to unregister.
    *   `.on_input_text(callback: Optional[Callable[[str, str], None]])`: Registers a function called with `controlId` and `value` when a text input is submitted. Pass `None` to unregister.
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function for instance-specific errors. Pass `None` to unregister.

## 6. Development Notes

*   **Payload Keys:** Remember that all keys in the `payload` dictionary sent to Sidekick **MUST use `camelCase`**. This is handled internally by the library's methods.
*   **Dependencies:** Requires the `websocket-client` library (`pip install websocket-client`).
*   **Threading:** The library uses a background daemon thread for receiving messages. Be mindful of thread safety if accessing shared state from module callbacks.
*   **Shutdown:** Use `sidekick.shutdown()` for explicit cleanup or rely on `atexit` for normal program termination. Ensure long-running scripts use `sidekick.run_forever()` or manage their own main loop.

## 7. Troubleshooting

*   **Connection Errors:**
    *   Check if the Sidekick WebSocket server is running (often part of the VS Code extension or run via `npm run dev` in `webapp`).
    *   Verify the URL (`ws://localhost:5163` by default) using `sidekick.set_url()` *before* creating modules.
    *   Check firewalls.
    *   Enable DEBUG logging (`logging.getLogger("SidekickConn").setLevel(logging.DEBUG)`) for detailed connection logs.
*   **Module Commands Not Appearing:**
    *   Check DEBUG logs. Are messages buffered? Did Sidekick become `CONNECTED_READY`? Was the buffer flushed?
    *   Inspect WebSocket messages in the Sidekick frontend (Browser DevTools > Network > WS). Verify message structure (`module`, `type`, `target`) and **ensure `payload` keys are `camelCase`**.
    *   Check the Sidekick browser console for errors processing the message.
*   **Callbacks Not Firing:**
    *   Ensure the correct registration method was called on the module instance.
    *   Check DEBUG logs: Is the `event` or `error` message being received from Sidekick? Does the `src` match the `instance_id`? Does the `payload['event']` match expectations?
    *   Add logging inside your callback function. Check for exceptions within your callback (these are caught and logged by `SidekickConn`).
*   **Script Doesn't Exit:** Ensure you are not calling `sidekick.run_forever()` unless intended. If using event callbacks that should keep the script alive, use `run_forever()` and `shutdown()`. Check for other non-daemon threads or blocking operations in your code.
*   **`ensure_ready` / `flush_messages` Timeout:** This usually means Sidekick did not connect or announce itself online within the timeout period. Check Sidekick server status and network connectivity. Increase the timeout if necessary for slow startups.
*   **`Viz` Not Updating Reactively:**
    *   Ensure the value passed to `viz.show()` is an `sidekick.ObservableValue`.
    *   Mutations must happen *through* the `ObservableValue` wrapper methods (e.g., `obs_list.append(item)`, `obs_dict[key] = value`, `obs_value.set(new_val)`).
