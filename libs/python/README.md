# Sidekick Python Library

## 1. Overview

This library provides the Python interface ("Hero") for interacting with the Sidekick Visual Coding Buddy frontend UI. It allows Python scripts to easily create, update, interact with, and remove visual modules like grids, consoles, variable visualizers, and drawing canvases within the Sidekick UI, typically via a mediating Server.

It abstracts the underlying WebSocket communication and message formatting, offering an intuitive object-oriented API. The library includes features for peer discovery (`system/announce`), automatic state clearing on connect (`global/clearAll`), message buffering for enhanced reliability, and the ability to re-attach to existing UI elements.

## 2. Features

*   **Object-Oriented API:** Control visual modules (`Grid`, `Console`, `Viz`, `Canvas`, `Control`) via Python classes and methods (using `snake_case`).
*   **Peer Discovery & Status:** Automatically announces itself (`system/announce` with `role: "hero"`) upon connection and listens for Sidekick (`role: "sidekick"`) announcements to manage interaction readiness.
*   **Message Buffering:** Automatically buffers module-specific commands (`spawn`, `update`, `remove`) and global commands (`clearAll`) until at least one Sidekick peer announces itself as online, preventing message loss during Sidekick startup or reconnection. `system/announce` messages are sent immediately upon connection.
*   **Automatic State Clearing:** Configurable option (`clear_on_connect`, default True) to automatically send a `global/clearAll` message when the connection becomes ready (i.e., Sidekick is online), ensuring a clean state. Optional best-effort clearing on disconnect.
*   **Re-attachment Support:** Module constructors include a `spawn: bool` parameter (default `True`). Setting `spawn=False` allows the Python object to represent and interact with an existing module instance in Sidekick (identified by `instance_id`) without sending a `spawn` command.
*   **`ObservableValue`:** A general-purpose wrapper to track changes in Python values (primitives or containers). Notifies subscribers with detailed change information.
*   **Automatic WebSocket Management:** Handles connection (`ws://localhost:5163` default), peer announcements, keep-alive (Ping/Pong), listener thread, connection status tracking, and `atexit` cleanup.
*   **Callback Handling:** Supports receiving notifications (`notify`) from interactive modules (`Grid`, `Console`, `Control`) via user-provided `on_message` callbacks.
*   **Structured Data Visualization (`Viz`):** Provides detailed, expandable views of Python data structures, reacting to granular changes from `ObservableValue`.
*   **Basic 2D Drawing (`Canvas`):** Allows drawing lines, rectangles, and circles.
*   **Dynamic UI Controls (`Control`):** Add buttons and text inputs dynamically, receiving interaction events.

## 3. Installation

**Development (Recommended):**

Install in editable mode from the project root (`Sidekick/`) directory:

```bash
pip install -e libs/python
```

This links the installed package to your source code, so changes are immediately reflected.

**Distribution (PyPI):**

```bash
pip install sidekick-py
```

## 4. Core Concepts

### 4.1. Connection Management (`connection.py`)

*   **Singleton & State Machine:** Manages a single WebSocket connection using a state machine (`ConnectionStatus`: `DISCONNECTED`, `CONNECTING`, `CONNECTED_WAITING_SIDEKICK`, `CONNECTED_READY`). An `RLock` is used for thread safety.
*   **Lazy Connection & Activation:** Connects automatically when needed (e.g., first module instantiation) or when `activate_connection()` is called.
*   **Configuration (`set_url`, `set_config`):** These functions **must** be called *before* the first connection attempt (before `activate_connection` or module creation).
    *   `set_url(url)`: Sets the WebSocket server URL.
    *   `set_config(clear_on_connect=True, clear_on_disconnect=False)`:
        *   `clear_on_connect` (bool, default `True`): If True, the library automatically sends a `global/clearAll` message immediately after the connection status transitions to `CONNECTED_READY` (i.e., when the first Sidekick peer announces `online`).
        *   `clear_on_disconnect` (bool, default `False`): If True, the library attempts (best-effort) to send `global/clearAll` followed by a `system/announce offline` message during the `close_connection` process. This is not guaranteed if the connection is already lost or the script terminates abruptly.
*   **Peer Announcement (`system/announce`):**
    *   **Sending:** Upon successful WebSocket connection, generates a unique `peerId` (`hero-<uuid>`) and immediately sends a `system/announce` message with `role: "hero"`, `status: "online"`, and the library `version`. Attempts to send an `offline` announcement on graceful disconnect (`close_connection`).
    *   **Receiving:** The listener thread parses incoming `system/announce` messages. It maintains a set of online Sidekick `peerId`s (`_sidekick_peers_online`).
*   **Connection Status & Readiness:**
    *   Starts as `DISCONNECTED`.
    *   Moves to `CONNECTING` during the connection attempt.
    *   On successful WebSocket connection and sending the initial `online` announce, moves to `CONNECTED_WAITING_SIDEKICK`.
    *   When the *first* `announce online` message from a `role: "sidekick"` peer is received, the status transitions to `CONNECTED_READY`.
*   **Message Buffering (`_message_buffer`):**
    *   A `deque` is used to store outgoing messages.
    *   When `send_message()` is called:
        *   If the message `module` is `system`, it attempts to send immediately if the WebSocket is connected (status `CONNECTED_WAITING_SIDEKICK` or `CONNECTED_READY`).
        *   If the message `module` is *not* `system` (e.g., `grid`, `console`, `global`), it checks the connection status. If *not* `CONNECTED_READY`, the message is appended to the buffer (`_message_buffer`).
        *   If `CONNECTED_READY`, the message is sent directly.
    *   **Buffer Flushing:** When the status transitions to `CONNECTED_READY` (first Sidekick online), the `_flush_message_buffer()` function is called automatically (after potential `clear_on_connect`), sending all buffered messages in FIFO order.
*   **Keep-Alive:** Uses WebSocket Ping/Pong frames for reliable connection maintenance.
*   **Listener Thread (`_listen_for_messages`):** Runs in the background, receiving messages, parsing JSON, handling `system/announce` to update Sidekick status and trigger readiness, and dispatching `notify`/`error` messages to registered module handlers.
*   **Message Dispatch:** Uses a dictionary (`_message_handlers`) mapping `instance_id` (`src` field in message) to user-provided `on_message` callbacks.
*   **Cleanup (`atexit`):** Registers `close_connection` to run on script exit for graceful shutdown attempts.

### 4.2. Base Module (`base_module.py`)

*   Provides common functionality: activates connection, manages `instance_id`, registers callbacks.
*   **Constructor `__init__(..., instance_id=None, spawn=True, ...)`:**
    *   Takes `spawn: bool` parameter.
    *   **`spawn=True` (Default):** Normal behavior. Creates a *new* visual instance in Sidekick. `instance_id` is optional (auto-generated using `utils.generate_unique_id` if `None`). Sends a `spawn` command message (which will be buffered if Sidekick isn't ready yet). The provided `payload` is used for the spawn command.
    *   **`spawn=False`:** Re-attachment mode. Assumes the visual instance *already exists* in Sidekick. **`instance_id` becomes mandatory** and must match the existing Sidekick instance ID. **No** `spawn` command is sent. The `payload` argument is ignored. This allows the Python script to control pre-existing UI elements (e.g., after a script restart if Sidekick state persisted).
*   **Sending Commands:** Methods like `_send_command`, `_send_update`, `remove` now use `connection.send_message`, automatically handling buffering based on connection readiness.
*   **Payloads:** Emphasizes that payloads sent via helpers **MUST use `camelCase` keys**.

### 4.3. Communication Protocol & Payloads

*   Communication uses JSON messages over WebSocket, relayed by a Server.
*   Messages follow the structure: `{ id, module, method, target?, src?, payload? }`.
*   **Payload Keys:** The `payload` object **MUST use `camelCase` keys**.
*   **Key Methods & Modules:**
    *   `system/announce`: Used for peer discovery and status (see 4.1). `target`/`src` omitted.
    *   `global/clearAll`: Used to clear all Sidekick modules. Sent via `sidekick.clear_all()` or automatically via `clear_on_connect`. `target`/`src`/`payload` omitted.
    *   Module methods (`spawn`, `update`, `remove`, `notify`, `error`) operate on specific module instances (`target` or `src` provided). Payloads typically use `action`/`options` structure.
*   Refer to `protocol.md` for detailed payload structures for each module.

### 4.4. `ObservableValue` (`observable_value.py`)

*   (No fundamental change) Wraps Python values, intercepts container mutations (`append`, `__setitem__`, `add`, etc.) or `.set()` calls, notifies subscribers with detailed `change_details` dict. Crucial for `Viz` module reactivity.

### 4.5. `Viz` Module Integration (`viz.py`)

*   (No fundamental change) `viz.show(name, value)` sends `update` (`action: "set"`) message. Subscribes to `ObservableValue`s passed to it. Translates `change_details` from `ObservableValue` into granular `update` messages (`action: "setitem"`, etc.) with appropriate `variableName`, `path`, `valueRepresentation`, `keyRepresentation`, `length` in the `options` field (all `camelCase`).

## 5. API Reference

*(Note: All methods sending messages construct payloads with **`camelCase` keys**. Non-`system` messages are buffered until Sidekick is online.)*

### 5.1. Top-Level Functions (`connection.py`, `__init__.py`)

*   `sidekick.set_url(url: str)`: Sets WebSocket Server URL. **Call before connecting.**
*   `sidekick.set_config(clear_on_connect: bool = True, clear_on_disconnect: bool = False)`: Configures automatic clearing. **Call before connecting.**
*   `sidekick.clear_all()`: Sends `global/clearAll` message (buffered if needed).
*   `sidekick.close_connection()`: Manually closes connection, attempts cleanup messages.
*   `sidekick.activate_connection()`: Ensures connection attempt is initiated. Safe to call multiple times.
*   `(Internal/Advanced)`: `get_connection()`, `register_message_handler()`, `unregister_message_handler()`, `get_next_command_id()`.

### 5.2. `sidekick.ObservableValue`

*   `ObservableValue(initial_value: Any)`
*   Methods: `.get()`, `.set()`, `.subscribe()`, `.unsubscribe()`, container methods (`.append`, `.__setitem__`, etc.).

### 5.3. `sidekick.Grid`

*   `Grid(width: int, height: int, instance_id: Optional[str] = None, spawn: bool = True, on_message: Optional[Callable] = None)`
    *   `spawn=False` requires `instance_id`.
*   Methods: `.set_color()`, `.set_text()`, `.clear()`, `.remove()`.

### 5.4. `sidekick.Console`

*   `Console(instance_id: Optional[str] = None, spawn: bool = True, initial_text: str = "", on_message: Optional[Callable] = None)`
    *   `spawn=False` requires `instance_id`. `initial_text` ignored if `spawn=False`.
*   Methods: `.print()`, `.log()`, `.clear()`, `.remove()`.

### 5.5. `sidekick.Viz`

*   `Viz(instance_id: Optional[str] = None, spawn: bool = True)`
    *   `spawn=False` requires `instance_id`.
*   Methods: `.show()`, `.remove_variable()`, `.remove()`.

### 5.6. `sidekick.Canvas`

*   `Canvas(width: int, height: int, instance_id: Optional[str] = None, spawn: bool = True, bg_color: Optional[str] = None)`
    *   `spawn=False` requires `instance_id`. `width/height/bg_color` ignored if `spawn=False`.
*   Methods: `.clear()`, `.config()`, `.draw_line()`, `.draw_rect()`, `.draw_circle()`, `.remove()`.

### 5.7. `sidekick.Control`

*   `Control(instance_id: Optional[str] = None, spawn: bool = True, on_message: Optional[Callable] = None)`
    *   `spawn=False` requires `instance_id`.
*   Methods: `.add_button()`, `.add_text_input()`, `.remove_control()`, `.remove()`.

## 6. Development Notes

*   **Structure:** See previous version. `_version.py` added. `connection.py` and `base_module.py` have significant logic changes.
*   **Dependencies:** `websocket-client`.
*   **Payload Keys:** **MUST use `camelCase`**.
*   **Buffering:** Module/global commands are delayed until Sidekick announces `online`. Check DEBUG logs to see buffering and flushing.
*   **Re-attachment:** Use `spawn=False` and provide the correct `instance_id` to control existing Sidekick elements without re-creating them. Ensure Sidekick state persistence aligns with this usage.

## 7. Troubleshooting

*   **Connection Errors:** Check server, URL, firewall. Ensure `set_url`/`set_config` called *before* module creation. Check DEBUG logs (`SidekickConn`).
*   **Messages Not Appearing (Module Commands):**
    *   Check DEBUG logs. Are messages being buffered? `Buffering message (...)`
    *   Did Sidekick announce `online`? `Sidekick peer online: ...`, `System is READY.`
    *   Was the buffer flushed? `Flushing message buffer...`
*   **`clear_on_connect` Not Working:** Ensure `set_config` called early. Check logs for `global/clearAll` being sent *after* `System is READY`. Note: `clearAll` itself is buffered if Sidekick isn't ready when `set_config` triggers it.
*   **`clear_on_disconnect` Not Working:** This is best-effort only. May fail if connection already dropped.
*   **Module Not Appearing (Using `spawn=True`):** Check buffering issues above. Check Sidekick console for errors receiving `spawn`. Verify `target_id`. **Ensure payload keys are `camelCase`**.
*   **Errors Using `spawn=False`:**
    *   Did you provide a valid `instance_id`? Error `instance_id is required...`
    *   Does the instance actually exist in Sidekick with that ID? Sidekick might have cleared it.
    *   Was Sidekick cleared unexpectedly (e.g., via `clear_on_connect` or manual `clear_all`)?
*   **Callbacks Not Firing:** Check `on_message` registration. Check DEBUG logs for incoming `notify` messages.
*   **Viz/Canvas/Control Issues:** Remember potential buffering delays. Refer to previous notes on `commandId`, `ObservableValue` etc.