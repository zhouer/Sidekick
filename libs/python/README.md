# Sidekick Python Library (`sidekick-py`)

## 1. Overview

This library provides the Python interface ("Hero") for interacting with the Sidekick Visual Coding Buddy frontend UI. It allows Python scripts to easily create, update, interact with, and remove visual modules like grids, consoles, variable visualizers, drawing canvases, and UI controls within the Sidekick UI, typically via a mediating WebSocket Server.

The library abstracts the underlying WebSocket communication and JSON message formatting, offering an intuitive object-oriented API. Key features include:

*   **Simplified Event Handling:** Register specific callbacks (e.g., `on_click`, `on_input_text`) directly on module instances.
*   **Reliable Communication:** Automatic connection management, peer discovery, message buffering, and keep-alive mechanisms.
*   **Flexible Instantiation:** Create new UI modules or attach to existing ones (`spawn=False`).
*   **Reactive Visualization:** Integration with `ObservableValue` for automatic UI updates in the `Viz` module.
*   **Global Message Observation:** Optional handler to inspect all incoming messages.

## 2. Features

*   **Object-Oriented API:** Control visual modules (`Grid`, `Console`, `Viz`, `Canvas`, `Control`) via Python classes and methods (using standard Python `snake_case`).
*   **Simplified Event Handling:**
    *   Interactive modules (`Grid`, `Console`, `Control`) offer specific event registration methods (e.g., `module_instance.on_click(...)`, `module_instance.on_input_text(...)`).
    *   All modules provide an `on_error(callback)` method to handle errors reported by the frontend for that specific instance.
    *   Removes the need for users to manually parse raw `event` or `error` messages in most cases.
*   **Global Message Handling:** Provides `sidekick.register_global_message_handler(handler)` for observing *all* incoming messages for advanced logging, debugging, or handling custom message types.
*   **Peer Discovery & Status:** Automatically announces itself (`system/announce` with `role: "hero"`) upon connection and listens for Sidekick (`role: "sidekick"`) announcements to manage interaction readiness (`CONNECTED_READY` state).
*   **Message Buffering:** Automatically queues module-specific commands (`spawn`, `update`, `remove`) and global commands (`clearAll`) if the connection is not yet `CONNECTED_READY` (i.e., Sidekick hasn't announced itself online). The buffer is flushed automatically when the connection becomes ready.
*   **Automatic State Clearing:** Configurable options (`clear_on_connect`, `clear_on_disconnect`) via `sidekick.set_config()` to manage the Sidekick UI state automatically upon connection or disconnection.
*   **Re-attachment Support:** Module constructors include `spawn: bool` (default `True`). Setting `spawn=False` allows the Python object to represent and interact with an existing module instance in Sidekick (identified by `instance_id`) without sending a `spawn` command.
*   **`ObservableValue`:** A general-purpose wrapper (`sidekick.ObservableValue`) to track changes in Python values (primitives or containers like lists, dicts, sets). It automatically notifies subscribers (like the `Viz` module) with detailed change information upon mutation or `.set()` calls.
*   **Automatic WebSocket Management:** Handles connection establishment (default `ws://localhost:5163`), peer announcements, keep-alive (Ping/Pong), background listener thread, connection state tracking (`ConnectionStatus`), and attempts graceful cleanup on script exit (`atexit`).
*   **Structured Data Visualization (`Viz`):** Provides detailed, expandable views of Python data structures, reacting automatically to granular changes in `ObservableValue` instances shown via `viz.show()`.
*   **Basic 2D Drawing (`Canvas`):** Allows programmatic drawing of lines, rectangles, and circles with basic configuration options. Uses command IDs for reliable processing.
*   **Dynamic UI Controls (`Control`):** Dynamically add buttons and text inputs to the UI and receive interaction events via specific callbacks (`on_click`, `on_input_text`).

## 3. Installation

**Development:**

Install from the project root (`Sidekick/`) directory:

```bash
pip install -e libs/python
```

This links the installed package to your source code, so changes are immediately reflected.

**Standard Installation (from PyPI):**

```bash
pip install sidekick-py
```

## 4. Core Concepts

### 4.1. Connection Management (`connection.py`)

*   **Singleton & State Machine:** Manages a single, shared WebSocket connection using a state machine (`ConnectionStatus`: `DISCONNECTED`, `CONNECTING`, `CONNECTED_WAITING_SIDEKICK`, `CONNECTED_READY`). Thread-safety is managed using an `RLock`.
*   **Lazy Connection:** The connection attempt is automatically triggered when the first module is instantiated or when `sidekick.activate_connection()` is explicitly called.
*   **Configuration (`set_url`, `set_config`):** These global functions **must** be called *before* the first connection attempt is made (i.e., before the first module is created or `activate_connection` is called).
    *   `set_url(url: str)`: Sets the WebSocket server URL (defaults to `ws://localhost:5163`).
    *   `set_config(clear_on_connect: bool = True, clear_on_disconnect: bool = False)`:
        *   `clear_on_connect`: If True, automatically sends a `global/clearAll` message *after* the connection status becomes `CONNECTED_READY` (first Sidekick peer announces online).
        *   `clear_on_disconnect`: If True, attempts (best-effort) to send `global/clearAll` followed by a `system/announce offline` message during the `close_connection` process. Not guaranteed if the connection is already lost or the script terminates abruptly.
*   **Peer Announcement (`system/announce`):**
    *   **Sending:** Upon successful WebSocket connection, generates a unique `peerId` (`hero-<uuid>`) and immediately sends a `system/announce` message with `role: "hero"`, `status: "online"`, and the library `version`. Attempts to send an `offline` announcement on graceful disconnect (`close_connection`).
    *   **Receiving:** The listener thread parses incoming `system/announce` messages. It maintains a set of online Sidekick `peerId`s (`_sidekick_peers_online`). When the first Sidekick announces `online`, the connection status transitions to `CONNECTED_READY`.
*   **Message Buffering (`_message_buffer`):**
    *   A `deque` stores outgoing messages (except `system/announce`).
    *   When `send_message()` is called for non-system messages:
        *   If status is not `CONNECTED_READY`, the message is added to the buffer.
        *   If status is `CONNECTED_READY`, the message is sent immediately.
    *   **Buffer Flushing:** When the status transitions to `CONNECTED_READY`, `_flush_message_buffer()` sends all buffered messages in FIFO order (after potentially sending `clear_on_connect`).
*   **Keep-Alive:** Uses WebSocket Ping/Pong frames (configured via internal constants `_PING_INTERVAL`, `_PING_TIMEOUT`) for reliable connection maintenance and failure detection.
*   **Listener Thread (`_listen_for_messages`):** Runs in the background to receive messages.
    *   Parses incoming JSON messages.
    *   Handles `system/announce` to update Sidekick status and trigger readiness/buffer flushing.
    *   **Message Dispatching:**
        1.  If a `_global_message_handler` is registered (via `register_global_message_handler`), it's called first with the raw incoming message dictionary.
        2.  If the message has a `src` field (identifying the source module instance, typically for `event` or `error` messages), it looks up the *internal* handler function registered for that `instance_id` (via `_message_handlers`).
        3.  It calls the found internal handler (which belongs to the specific `BaseModule` subclass instance).
*   **Handler Registration:**
    *   `register_message_handler(instance_id, handler)`: **Internal use.** Called by `BaseModule.__init__` to register the module instance's `_internal_message_handler`.
    *   `unregister_message_handler(instance_id)`: **Internal use.** Called by `BaseModule.remove` and `__del__`.
    *   `register_global_message_handler(handler)`: **Public API.** Registers or unregisters a single global function to receive all messages.
*   **Cleanup (`atexit`):** Registers `close_connection` to run on normal script exit for graceful shutdown attempts.

### 4.2. Base Module (`base_module.py`)

*   Provides common functionality for all module classes (`Grid`, `Console`, `Viz`, etc.).
*   **Constructor `__init__(module_type, instance_id=None, spawn=True, payload=None)`:**
    *   Takes `spawn: bool` parameter:
        *   `spawn=True` (Default): Creates a *new* visual instance in Sidekick. `instance_id` is optional (auto-generated if `None`). Sends a `spawn` command message (buffered if needed) with the `payload`.
        *   `spawn=False`: Re-attachment mode. Assumes the visual instance *already exists* in Sidekick. **`instance_id` becomes mandatory**. No `spawn` command is sent. `payload` is ignored.
    *   Activates the connection (`connection.activate_connection()`).
    *   Generates or validates `target_id`.
    *   Registers its own `self._internal_message_handler` with the connection manager using its `target_id`.
    *   **Does NOT take an `on_message` argument anymore.**
*   **Internal Message Handler (`_internal_message_handler(self, message)`)**
    *   This method is called by `connection.py` when a message for this specific instance (`src` matches `target_id`) is received.
    *   The base implementation in `BaseModule` specifically handles messages with `type: "error"`. It extracts the error message from the payload and calls the user-registered `_error_callback` (if any).
    *   **Subclasses (like `Grid`, `Console`, `Control`) MUST override this method.** Their overridden method should:
        1.  Check if the message `type` is `"event"`.
        2.  Parse the `payload` to determine the specific event (e.g., `payload['event'] == 'click'`).
        3.  Extract relevant data from the payload (e.g., `payload['x']`, `payload['y']`, `payload['value']`, `payload['controlId']`).
        4.  Call the corresponding specific user callback (e.g., `self._click_callback(x, y)`).
        5.  **Crucially, call `super()._internal_message_handler(message)`** to allow the base class to handle potential `error` messages or other common types in the future.
*   **Error Callback (`on_error(self, callback)`)**
    *   Public method available on all module instances.
    *   Allows users to register a function (`Callable[[str], None]`) that will be called if an `error` message is received from the frontend specifically for this module instance. The callback receives the error message string.
*   **Sending Commands (`_send_command`, `_send_update`)**
    *   Internal helper methods to construct messages (`spawn`, `update`, `remove`) with the correct `module`, `type`, and `target` ID.
    *   They use `connection.send_message`, which handles buffering automatically.
    *   **Payloads constructed here MUST use `camelCase` keys.**
*   **Removal (`remove()`)**
    *   Sends the `remove` command to Sidekick.
    *   Unregisters the instance's internal message handler from the connection manager.
    *   Resets any local callbacks (`_error_callback`, and calls `_reset_specific_callbacks` for subclasses).

### 4.3. Communication Protocol & Payloads

*   Communication uses JSON messages over WebSocket, typically relayed by a Server.
*   Messages follow the structure: `{ id: int, module: str, type: str, target?: str, src?: str, payload?: object | null }`. (See `protocol.md` for full details).
*   **Payload Keys:** All keys within the `payload` object and any nested objects within it **MUST use `camelCase`**. This is enforced by the protocol and expected by the Sidekick frontend. The Python library is responsible for ensuring outgoing messages adhere to this.
*   **Key Message Types & Modules:**
    *   `system/announce`: Used for peer discovery and status (handled internally by `connection.py`). `target`/`src` omitted.
    *   `global/clearAll`: Used to clear all Sidekick modules. Sent via `sidekick.clear_all()` or automatically via `clear_on_connect`. `target`/`src`/`payload` omitted.
    *   Module interaction types (`spawn`, `update`, `remove`) sent from Hero to Sidekick. Require `target` field identifying the module instance. `payload` structure depends on `module` and `type`.
    *   Module feedback types (`event`, `error`) sent from Sidekick to Hero. Require `src` field identifying the module instance. `payload` structure depends on `module` and `type`.
*   Refer to `protocol.md` for detailed payload structures for each module/type combination.

### 4.4. `ObservableValue` (`observable_value.py`)

*   A wrapper class for Python values (primitives, lists, dicts, sets).
*   Intercepts common mutable operations (`append`, `__setitem__`, `add`, `update`, `clear`, etc.) or explicit `.set()` calls.
*   Notifies subscribed callbacks with detailed `change_details` dictionary upon changes.
*   Essential for the reactive updates in the `Viz` module. When an `ObservableValue` instance is passed to `viz.show()`, the `Viz` module subscribes to it and sends granular updates to the frontend upon notification.

### 4.5. `Viz` Module Integration (`viz.py`)

*   `viz.show(name, value)` sends an initial `update` (`action: "set"`) message with the full representation of the `value`.
*   If `value` is an `ObservableValue`, `viz.show` subscribes to it.
*   When the `ObservableValue` notifies `Viz` of a change (via internal callback `_handle_observable_update`), `Viz` translates the `change_details` into a granular `update` message (`action: "setitem"`, `action: "append"`, etc.) for Sidekick. This message includes the `variableName`, `path` to the change, and `camelCase` representations (`valueRepresentation`, `keyRepresentation`, `length`).

## 5. API Reference

*(Note: All methods sending messages construct payloads with **`camelCase` keys**. Non-`system` messages are buffered until Sidekick is online.)*

### 5.1. Top-Level Functions (`sidekick` namespace)

*   `sidekick.set_url(url: str)`: Sets the WebSocket Server URL. **Call before connecting.**
*   `sidekick.set_config(clear_on_connect: bool = True, clear_on_disconnect: bool = False)`: Configures automatic clearing behavior. **Call before connecting.**
*   `sidekick.clear_all()`: Sends `global/clearAll` message to Sidekick (buffered if connection not ready).
*   `sidekick.close_connection()`: Manually closes the WebSocket connection and attempts cleanup.
*   `sidekick.activate_connection()`: Ensures the connection attempt is initiated. Called automatically by module constructors but can be called manually. Safe to call multiple times.
*   `sidekick.register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]])`:
    Registers or unregisters a single handler function that will be called with *every* message received from Sidekick. The handler receives the raw message dictionary. Use `None` to unregister.

### 5.2. `sidekick.ObservableValue`

*   `ObservableValue(initial_value: Any)`
*   Methods: `.get()`, `.set(new_value)`, `.subscribe(callback)`, `.unsubscribe(callback)`.
*   Also intercepts and notifies on standard mutable container methods like `.append()`, `.__setitem__()`, `.add()`, `.update()`, `.pop()`, `.remove()`, `.clear()`, `.__delitem__()`, `.insert()`, `.discard()`.

### 5.3. `sidekick.Grid`

*   `Grid(num_columns: int = 16, num_rows: int = 16, instance_id: Optional[str] = None, spawn: bool = True)`
    *   `spawn=False` requires `instance_id`.
*   **Methods:**
    *   `.set_cell(x: int, y: int, color: Optional[str] = None, text: Optional[str] = None)`
    *   `.set_color(x: int, y: int, color: Optional[str])`
    *   `.set_text(x: int, y: int, text: Optional[str])`
    *   `.clear()`
    *   `.remove()`
*   **Event Handlers:**
    *   `.on_click(callback: Optional[Callable[[int, int], None]])`: Registers a function called when a cell is clicked. Callback receives `x` (column index) and `y` (row index). Pass `None` to unregister.
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function called when an error related to this grid instance is received from Sidekick. Callback receives the error message string. Pass `None` to unregister.

### 5.4. `sidekick.Console`

*   `Console(instance_id: Optional[str] = None, spawn: bool = True, initial_text: str = "", show_input: bool = False)`
    *   `spawn=False` requires `instance_id`; `initial_text` and `show_input` are ignored.
*   **Methods:**
    *   `.print(*args: Any, sep: str = ' ', end: str = '')`
    *   `.log(message: Any)`
    *   `.clear()`
    *   `.remove()`
*   **Event Handlers:**
    *   `.on_input_text(callback: Optional[Callable[[str], None]])`: Registers a function called when text is submitted via the input field (requires `show_input=True`). Callback receives the submitted text string. Pass `None` to unregister.
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function called when an error related to this console instance is received. Callback receives the error message string. Pass `None` to unregister.

### 5.5. `sidekick.Viz`

*   `Viz(instance_id: Optional[str] = None, spawn: bool = True)`
    *   `spawn=False` requires `instance_id`.
*   **Methods:**
    *   `.show(name: str, value: Any)`: Displays a variable. Automatically subscribes if `value` is an `ObservableValue`.
    *   `.remove_variable(name: str)`: Removes a variable from the display.
    *   `.remove()`: Removes the entire Viz panel instance.
*   **Event Handlers:**
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function called when an error related to this Viz instance is received. Callback receives the error message string. Pass `None` to unregister. *(Note: Viz currently doesn't emit user interaction events like 'click'.)*

### 5.6. `sidekick.Canvas`

*   `Canvas(width: int, height: int, instance_id: Optional[str] = None, spawn: bool = True, bg_color: Optional[str] = None)`
    *   `spawn=False` requires `instance_id`; `width`, `height`, `bg_color` are ignored.
*   **Methods:**
    *   `.clear(color: Optional[str] = None)`
    *   `.config(stroke_style: Optional[str] = None, fill_style: Optional[str] = None, line_width: Optional[int] = None)`
    *   `.draw_line(x1: int, y1: int, x2: int, y2: int)`
    *   `.draw_rect(x: int, y: int, width: int, height: int, filled: bool = False)`
    *   `.draw_circle(cx: int, cy: int, radius: int, filled: bool = False)`
    *   `.remove()`
*   **Event Handlers:**
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function called when an error related to this Canvas instance is received. Callback receives the error message string. Pass `None` to unregister. *(Note: Canvas currently doesn't emit user interaction events.)*

### 5.7. `sidekick.Control`

*   `Control(instance_id: Optional[str] = None, spawn: bool = True)`
    *   `spawn=False` requires `instance_id`.
*   **Methods:**
    *   `.add_button(control_id: str, text: str)`
    *   `.add_text_input(control_id: str, placeholder: str = "", initial_value: str = "", button_text: str = "Submit")`
    *   `.remove_control(control_id: str)`
    *   `.remove()`
*   **Event Handlers:**
    *   `.on_click(callback: Optional[Callable[[str], None]])`: Registers a function called when a button control created by this instance is clicked. Callback receives the `controlId` of the clicked button. Pass `None` to unregister.
    *   `.on_input_text(callback: Optional[Callable[[str, str], None]])`: Registers a function called when a text input control created by this instance is submitted. Callback receives the `controlId` and the submitted `value` string. Pass `None` to unregister.
    *   `.on_error(callback: Optional[Callable[[str], None]])`: Registers a function called when an error related to this Control panel instance is received. Callback receives the error message string. Pass `None` to unregister.

## 6. Development Notes

*   **Structure:** The core connection and dispatch logic resides in `connection.py` and `base_module.py`. Individual module classes (`grid.py`, `console.py`, etc.) inherit from `BaseModule` and implement specific methods and event handling.
*   **Dependencies:** Requires the `websocket-client` library (`pip install websocket-client`).
*   **Payload Keys:** Remember that all keys in the `payload` dictionary sent to Sidekick **MUST use `camelCase`**. This is handled internally by the library's methods, but be aware if constructing messages manually.
*   **Buffering:** Module/global commands are automatically buffered if Sidekick is not yet online. Check DEBUG logs (`SidekickConn` logger) to observe buffering and flushing.
*   **Re-attachment:** Use `spawn=False` with the correct `instance_id` to control existing Sidekick elements. Ensure Sidekick's state persistence aligns with this usage and consider the effect of `clear_on_connect`.
*   **Event Handling:** Use the specific `on_click`, `on_input_text`, `on_error` methods provided by module instances for clear and simple event handling. Use `register_global_message_handler` primarily for debugging or advanced scenarios.

## 7. Troubleshooting

*   **Connection Errors:**
    *   Check if the Sidekick WebSocket server (often part of the VS Code extension or run via `npm run dev` in `webapp`) is running.
    *   Verify the URL (`ws://localhost:5163` by default) is correct using `sidekick.set_url()` *before* creating modules.
    *   Check firewalls.
    *   Inspect the `SidekickConn` DEBUG logs for detailed connection attempts and errors.
*   **Messages Not Appearing in Sidekick (Module Commands):**
    *   Check `SidekickConn` logs. Are messages being buffered (`Buffering message...`)?
    *   Did Sidekick announce itself online (`Sidekick peer online...`, `System is READY.`)?
    *   Was the buffer flushed (`Flushing message buffer...`)?
    *   Inspect the WebSocket messages in your browser's Developer Tools (Network -> WS tab) within Sidekick. Verify the message structure (`module`, `type`, `target`) and **ensure the `payload` keys are `camelCase`**.
    *   Check the Sidekick browser console for errors when processing the message (e.g., payload validation errors in `*Logic.ts`).
*   **Callbacks Not Firing (`on_click`, `on_input_text`, `on_error`):**
    *   **Registration:** Ensure you called the correct registration method (e.g., `my_grid.on_click(my_handler)`) on the specific module instance.
    *   **Message Reception:** Check `SidekickConn` DEBUG logs. Is the corresponding `event` or `error` message being received from Sidekick? Verify the `src` field matches your `instance_id`.
    *   **Event Type:** For `event` messages, check the `payload['event']` field in the log matches the expected type (e.g., `"click"`, `"inputText"`).
    *   **Callback Execution:** Add logging *inside* your callback function to confirm it's being entered. Check for exceptions occurring within your callback function (these will be logged by SidekickConn).
*   **`clear_on_connect` / `clear_on_disconnect` Issues:** Ensure `set_config` is called *before* connection. Note that `clear_on_disconnect` is best-effort.
*   **Errors Using `spawn=False`:**
    *   Did you provide the correct, non-None `instance_id`?
    *   Does the instance actually exist in Sidekick with that ID? It might have been cleared (manually or via `clear_on_connect`).
*   **Viz Module Not Updating Reactively:**
    *   Ensure the value passed to `viz.show()` is an `sidekick.ObservableValue` instance.
    *   Ensure mutations are happening *through* the `ObservableValue` wrapper methods (e.g., `obs_list.append(item)`, `obs_dict[key] = value`, `obs_value.set(new_val)`), not by modifying internal data directly.
    *   Check logs for subscription messages and update processing in `Viz` and `connection`.
