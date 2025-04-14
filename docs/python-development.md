# Sidekick Python Library (`sidekick-py`) Development Guide

## 1. Overview

This document provides a technical deep dive into the `sidekick-py` library, intended for developers contributing to the library or seeking to understand its internal mechanics. It details the implementation of the Python "Hero" interface for interacting with the Sidekick visualization panel.

The library's primary goal is to offer a high-level, intuitive Python API (`snake_case` methods) that abstracts the complexities of WebSocket communication, message formatting (including payload key casing conversion), connection management, peer discovery, message buffering, and event handling based on the [Sidekick Communication Protocol](../protocol.md).

## 2. Development Setup

To work on the library code, clone the main Sidekick repository and install `sidekick-py` in editable mode from the **project root directory (`Sidekick/`)**:

```bash
# Ensure you are in the Sidekick/ directory
pip install -e libs/python
# Install dependencies (if not already installed)
pip install websocket-client
```
This links the installed package to your source code in `libs/python/src/sidekick`, allowing changes to be immediately reflected.

## 3. Core Implementation Details

### 3.1. Connection Management (`connection.py`)

*   **Singleton & State Machine:** Manages a single, shared WebSocket connection (`_ws_connection`) using a state machine (`ConnectionStatus`) and an `RLock` (`_connection_lock`) for thread safety.
*   **Lazy Connection:** `activate_connection()` (called by module `__init__`) triggers `_ensure_connection()` only if status is `DISCONNECTED`.
*   **Configuration:** `set_url()` and `set_config()` modify global state variables (`_ws_url`, `_clear_on_connect`, etc.) **before** the first connection attempt.
*   **Listener Thread:**
    *   `_listen_for_messages` runs as a background daemon thread (`daemon=True` is crucial).
    *   Uses `websocket.recv()` with a short timeout (`_LISTENER_RECV_TIMEOUT`) to allow periodic checks of the `_stop_event`.
    *   Parses incoming JSON messages.
    *   Handles `system/announce` messages to track Sidekick peer status (`_sidekick_peers_online`) and update connection state (`_connection_status`, `_ready_event`).
    *   Dispatches `event` and `error` messages to the correct handler registered in `_message_handlers` based on the message's `src` field.
    *   Calls the optional `_global_message_handler`.
*   **Threading Primitives:** Uses `threading.Event` (`_stop_event`, `_ready_event`, `_shutdown_event`) and `threading.Condition` (`_buffer_flushed_and_ready_condition`) for inter-thread coordination (shutdown, readiness, flushing).
*   **Shutdown Process:**
    *   `close_connection` is the core cleanup: sets `_stop_event`, notifies conditions, attempts best-effort `clearAll`/`offline` announce, closes WebSocket, joins listener thread.
    *   `shutdown` signals `run_forever` via `_shutdown_event` and calls `close_connection`.
    *   `atexit.register(shutdown)` ensures cleanup on normal interpreter exit.

### 3.2. Peer Discovery & Message Buffering

*   **Announcements:** Hero sends `system/announce` (`role: "hero", status: "online"`) upon connection. Listens for Sidekick (`role: "sidekick"`) announces in `_listen_for_messages`.
*   **Ready State (`CONNECTED_READY`):** Set when the first Sidekick peer announces `online`. `_ready_event` is set, `_handle_sidekick_online` is called.
*   **Buffering (`_message_buffer`):** Non-`system` messages sent via `send_message()` before status is `CONNECTED_READY` are queued in `_message_buffer` (`collections.deque`).
*   **Flushing (`_flush_message_buffer`):** Called by `_handle_sidekick_online` when status becomes `READY`. Also implicitly handled by `send_message` if sending while `READY`. Notifies `_buffer_flushed_and_ready_condition`.

### 3.3. Message Handling & Callbacks

*   **Dispatch:** `_listen_for_messages` routes messages with a `src` field to the handler stored in `_message_handlers` (keyed by `instance_id`).
*   **Internal Handler (`BaseModule._internal_message_handler`):** Registered by each module instance. Receives the raw message dictionary. Handles `type: "error"` by calling `_error_callback`. Subclasses override it to parse specific `type: "event"` messages (based on `payload.event`) and invoke user callbacks (e.g., `_click_callback`, `_input_text_callback`).
*   **User Callbacks:** Registered via public methods like `grid.on_click()`, stored in instance variables.

### 3.4. Module Interaction (`BaseModule`, `_send_command`)

*   **`BaseModule`:** Provides common functionality: `target_id` management (using `utils.generate_unique_id`), connection activation, handler registration/unregistration, `_send_command`/`_send_update` helpers, `remove()`, `on_error()`.
*   **`instance_id` / `target_id`:** Unique identifier linking the Python object to the UI element. `target_id` is used as the `target` field in outgoing commands.
*   **`spawn=True/False`:** Controls whether a `spawn` command is sent on init or if the object attaches to an existing UI element.
*   **`_send_command`/`_send_update`:** Internal helpers that construct the message dictionary (including `module`, `type`, `target`) and pass it to `connection.send_message()`.

### 3.5. Protocol Compliance: `snake_case` to `camelCase` Conversion

*   **Responsibility:** Public API methods in module classes (e.g., `Grid.set_color`, `Console.__init__`) are responsible for constructing the `payload` dictionary.
*   **Implementation:** When constructing the `payload` (and its nested `options`, `config` etc.), these methods **must use `camelCase` keys** as defined in the [protocol specification](./protocol.md).
    *   Example (`grid.py`): `options: Dict[str, Any] = {"x": x, "y": y, "text": text}` -> `update_payload = { "action": "setText", "options": options }` -> `self._send_update(update_payload)`
    *   Example (`console.py`): `spawn_payload["showInput"] = show_input` -> `super().__init__(..., payload=spawn_payload)` -> BaseModule calls `self._send_command("spawn", payload)`
*   The `connection.py` module sends the message dictionary as-is, assuming the `payload` already has the correct `camelCase` keys.

### 3.6. Reactivity (`ObservableValue`, `Viz`)

*   **`ObservableValue`:** Wraps data, intercepts mutation methods (`append`, `__setitem__`, `add`, `set`, etc.), calls `_notify` with detailed `change_details`.
*   **Subscription:** `Viz.show()` subscribes `_handle_observable_update` to the `ObservableValue` if applicable. `remove_variable()` and `remove()` unsubscribe.
*   **`Viz._handle_observable_update`:** Translates `change_details` into a granular `update` message for Sidekick (using `change_details.type` as `action`), generating `valueRepresentation` / `keyRepresentation` via `_get_representation`.
*   **`_get_representation`:** Recursive function converting Python data to the JSON `VizRepresentation` format (handling depth, items, recursion). Defined in `viz.py`.

### 3.7. Lifecycle & Synchronization Functions

*   **`run_forever()`:** Blocks main thread by waiting on `_shutdown_event`. Includes logic to attempt reconnection if listener dies unexpectedly.
*   **`shutdown()`:** Sets `_shutdown_event`, calls `close_connection`. Called by `atexit`.
*   **`ensure_ready()`:** Blocks by waiting on `_ready_event`.
*   **`flush_messages()`:** Blocks using `_buffer_flushed_and_ready_condition` until status is `READY` and `_message_buffer` is empty.

## 4. API Design Notes

*   **Public API:** Uses standard Python `snake_case`.
*   **Error Handling:** Module methods raise standard Python exceptions for invalid arguments. Communication errors are handled in `connection.py` (logged). Errors *from* Sidekick (`type: "error"`) are routed to `on_error` callbacks. User callback exceptions are caught and logged.

## 5. Logging Strategy

*   Uses Python's standard `logging` module with the logger name `"sidekick"`.
*   A `NullHandler` is added by default to prevent warnings if the user application doesn't configure logging.
*   Users can configure handlers (e.g., `logging.basicConfig`) to see library logs (DEBUG level is useful for diagnosing issues).

## 6. Troubleshooting

*   **Connection Errors:** Check server status, URL (`sidekick.set_url()`), firewalls. Enable DEBUG logging for `"sidekick"`.
*   **Commands Not Appearing:** Check DEBUG logs (sending/buffering/flushing). Inspect WebSocket messages in browser DevTools (check `module`, `type`, `target`, and **payload key casing**). Check Sidekick browser console.
*   **Callbacks Not Firing:** Check registration. Check DEBUG logs (message received? `src` matches `target_id`? dispatch happening?). Log inside callback. Check for exceptions in callback (logged at DEBUG level).
*   **Script Doesn't Exit:** Using `run_forever()`? Use Ctrl+C or `sidekick.shutdown()`. Check for other non-daemon threads.
*   **`ensure_ready`/`flush_messages` Timeout:** Sidekick UI didn't connect/announce? Check Sidekick server/UI status, network. Check library DEBUG logs for connection state transitions and `system/announce` reception.
*   **`Viz` Not Updating:** Using `ObservableValue`? Mutating *through* wrapper methods? Check DEBUG logs for `"Received update..."`. Check browser DevTools for granular `update` messages. Check `_get_representation` logic if needed.