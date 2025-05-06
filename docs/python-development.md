# Sidekick Python Library (`sidekick-py`) Development Guide

## 1. Overview

This document provides a technical deep dive into the `sidekick-py` library, intended for developers contributing to the library or seeking to understand its internal mechanics. It details the implementation of the Python "Hero" interface for interacting with the Sidekick visualization panel.

The library's primary goal is to offer a high-level, intuitive Python API that abstracts the complexities of WebSocket communication, message formatting (including payload key casing conversion), connection management, peer discovery, and event handling based on the [Sidekick Communication Protocol](./protocol.md).

**Key Design Philosophy:**

The library operates under a specific connection model:

1.  **Mandatory Sidekick Presence:** The Sidekick VS Code panel and its communication server **must** be running *before* the Python script attempts to establish a connection.
2.  **Blocking Connection Establishment:** The *first* operation requiring communication (e.g., creating a `sidekick.Grid()` or sending the first message) will **block** the Python script's execution until:
    *   A connection to the Sidekick server is successfully established (via WebSocket or MessageChannel).
    *   The Sidekick UI panel signals back that it's online and ready.
3.  **Synchronous Sends:** Once the connection is ready, messages sent via component methods (like `grid.set_color()` or `canvas.draw_line()`) are attempted immediately. There is no internal queue or buffering if the connection is not ready; connection establishment blocks instead.
4.  **Exception-Based Error Handling:** Connection failures (initial refusal, timeout waiting for UI, disconnection during operation) will immediately **raise specific `SidekickConnectionError` exceptions**, halting the operation. The library does **not** attempt automatic reconnection. The user's script must handle these exceptions if recovery is desired (though typically the script would exit).
5.  **Canvas Double Buffering:** The `Canvas` component provides an optional double buffering mechanism via a context manager (`with canvas.buffer() as buf:`) for smoother animations.

## 2. Development Setup

To work on the library code:

1.  Clone the main Sidekick repository.
2.  Navigate to the **project root directory** (`Sidekick/`).
3.  Install `sidekick-py` in editable mode using pip:
    ```bash
    # Make sure you are in the Sidekick/ project root
    pip install -e libs/python
    ```
4.  Ensure development dependencies are installed:
    ```bash
    # Install if you don't have it already
    pip install websocket-client

    # For testing Pyodide support, you'll need to set up a Pyodide environment
    # This typically involves using a tool like pyodide-build or running in a browser context
    ```

Editable mode (`-e`) links the installed package directly to your source code in `libs/python/src/sidekick`, so any changes you make are immediately reflected when you run Python scripts that import `sidekick`.

## 3. Core Implementation Details

### 3.0. Communication Channel Abstraction

The library now uses an abstract communication channel interface to support different communication methods:

*   **`CommunicationChannel` (Abstract Base Class):** Defined in `channel.py`, this abstract class provides the interface that all communication channel implementations must follow. It includes methods for connecting, sending messages, closing the connection, and handling incoming messages.

*   **`WebSocketChannel` Implementation:** Defined in `websocket_channel.py`, this class implements the `CommunicationChannel` interface using WebSockets. It's used in standard Python environments and communicates with the Sidekick server via WebSocket.

*   **`PyodideMessageChannel` Implementation:** Defined in `pyodide_channel.py`, this class implements the `CommunicationChannel` interface using the JavaScript MessageChannel API. It's used when the library is running in a Pyodide environment (Python in the browser).

*   **Factory Function (`create_communication_channel`):** This function in `channel.py` detects the environment and creates the appropriate communication channel implementation. It checks if the code is running in Pyodide and returns either a `PyodideMessageChannel` or a `WebSocketChannel` accordingly.

### 3.1. Connection Management & Lifecycle (`connection.py`)

The `connection.py` module orchestrates the communication channel and connection lifecycle.

*   **Shared State:** Manages a single, shared communication channel (`_channel`) and associated state using module-level variables.
*   **Thread Safety:** Uses a `threading.RLock` (`_connection_lock`) to protect access to shared state variables (like `_connection_status`, `_channel`, `_message_handlers`) from race conditions between the main thread and the background listener thread.
*   **State Machine (`ConnectionStatus` Enum):** Tracks the connection's current state:
    *   `DISCONNECTED`: Initial state, or after `shutdown()` / error.
    *   `CONNECTING`: Actively trying to establish the connection.
    *   `CONNECTED_WAITING_SIDEKICK`: Connected to the server, but waiting for the UI panel's 'online' signal.
    *   `CONNECTED_READY`: Fully connected and confirmed that a Sidekick UI is ready to receive commands.
*   **Blocking Activation (`activate_connection()`):**
    *   This is the **central function** ensuring the connection is ready before any communication attempt. It's called automatically by methods like `send_message` (used by module methods) and `run_forever`.
    *   If the status is `DISCONNECTED`, it calls the internal `_ensure_connection()` to create the appropriate communication channel, establish the connection, and set up message handling.
    *   If `_ensure_connection()` succeeds (status becomes `CONNECTED_WAITING_SIDEKICK`), `activate_connection()` then **blocks** the calling thread by waiting on a `threading.Event` called `_ready_event`.
    *   The `_ready_event` is set **only** by the message handler when it receives the first `system/announce` message with `role: "sidekick"` and `status: "online"`.
    *   If the initial connection via `_ensure_connection()` fails, it raises `SidekickConnectionRefusedError`.
    *   If the wait for the `_ready_event` exceeds `_SIDEKICK_WAIT_TIMEOUT` (default 2 seconds), it triggers cleanup and raises `SidekickTimeoutError`.
*   **Message Handling:**
    *   Each communication channel implementation handles receiving messages differently:
        *   **WebSocketChannel:** Uses a background **daemon thread** that enters a loop, using `websocket.recv()` with a short timeout to periodically check if the stop event has been set.
        *   **PyodideMessageChannel:** Uses JavaScript event listeners to handle incoming messages asynchronously.
    *   Both implementations:
        *   Receive incoming JSON messages from the server or UI.
        *   Parse the JSON.
        *   Call the registered message handler function with the parsed message data.
    *   The message handler function (`_handle_incoming_message`):
        *   **Handles `system/announce` messages:** Tracks which Sidekick UI peers (`role: "sidekick"`) are online. When the *first* Sidekick UI announces itself as `online` *and* the connection status is `CONNECTED_WAITING_SIDEKICK`, it performs the crucial step of transitioning the status to `CONNECTED_READY` and **setting the `_ready_event`**, which unblocks the main thread waiting in `activate_connection()`.
        *   **Handles `event` and `error` messages:** Looks up the handler function registered for the message's `src` instance ID in the `_message_handlers` dictionary and calls it (typically the `_internal_message_handler` of the corresponding `BaseComponent` subclass instance).
        *   Calls the optional `_global_message_handler` if registered.
    *   **Handles Unexpected Disconnection/Errors:** If receiving messages fails (e.g., server closes connection, network error) or an unexpected exception occurs, and if it wasn't a planned shutdown, it triggers `close_connection(is_exception=True, ...)` in a *separate thread* to initiate cleanup and ensure a `SidekickDisconnectedError` is likely raised eventually.
*   **Error Handling & Exceptions:**
    *   `SidekickConnectionRefusedError`: Raised by `_ensure_connection` (via `activate_connection`) if the initial WebSocket `create_connection` fails. Indicates the server is likely not running or unreachable.
    *   `SidekickTimeoutError`: Raised by `activate_connection` if the connection to the server succeeds, but the `_ready_event` isn't set by the listener (because no Sidekick UI announced itself) within `_SIDEKICK_WAIT_TIMEOUT`.
    *   `SidekickDisconnectedError`: Raised by `send_message` if sending fails, or potentially by `close_connection` after cleanup if the closure was triggered by an unexpected listener termination or WebSocket error. Indicates the connection was lost *after* being established.
*   **Threading Primitives:** Uses `threading.Event` (`_stop_event`, `_ready_event`, `_shutdown_event`) for signaling between the main thread, listener thread, and shutdown logic. Uses `threading.RLock` (`_connection_lock`) for safe access to shared state.
*   **Shutdown Process (`close_connection()`, `shutdown()`, `atexit`):**
    *   `close_connection(is_exception, reason)`: The core cleanup function. Sets `_stop_event` to signal the listener thread, clears internal state (`_ws_connection`, status, handlers), attempts to send 'offline' announce and 'clearAll' (only on clean shutdown), closes the actual WebSocket socket, and joins the listener thread (waits for it to exit). Crucially, if called with `is_exception=True` (due to an error), it prepares a `SidekickDisconnectedError` to be raised *after* cleanup, unless `_shutdown_event` indicates a clean shutdown was requested concurrently.
    *   `shutdown()`: The public function for clean shutdown. Sets the `_shutdown_event` (to stop `run_forever`) and calls `close_connection(is_exception=False)`.
    *   `atexit.register(shutdown)`: Ensures `shutdown()` is called automatically when the Python script exits normally.
*   **Command ID Generation (`get_next_command_id()`):** Provides a simple sequential counter (module-level, not thread-safe but usually sufficient for typical single-threaded use) to generate unique IDs for commands that require strict ordering, primarily used by the `Canvas` module.

### 3.2. Peer Discovery (`system/announce`)

*   Immediately after a successful WebSocket connection in `_ensure_connection()`, the library sends a `system/announce` message with `role: "hero"` and `status: "online"`.
*   The background listener thread (`_listen_for_messages`) specifically waits for incoming `system/announce` messages where `role: "sidekick"` and `status: "online"`.
*   Receiving the *first* such message from a Sidekick UI triggers the state transition to `CONNECTED_READY` and the setting of the `_ready_event`, unblocking `activate_connection()`.

### 3.3. Message Sending (`send_message()`)

*   This function is the gatekeeper for sending messages.
*   **Step 1: Ensure Readiness:** It first calls `activate_connection()`. This **blocks** execution if the connection isn't `CONNECTED_READY` or raises a `SidekickConnectionError` subclass if establishment fails or times out.
*   **Step 2: Send Immediately:** If `activate_connection()` returns successfully, `send_message` acquires the lock and immediately attempts to send the provided `message_dict` using the internal `_send_raw` helper.
*   **Step 3: Handle Send Errors:** If `_send_raw` encounters a WebSocket error during the send attempt (e.g., connection dropped), it raises a `SidekickDisconnectedError`. `send_message` catches this, triggers the `close_connection(is_exception=True)` cleanup process, and then re-raises the `SidekickDisconnectedError` to the original caller (e.g., the `grid.set_color` method).
*   **No Buffering:** Messages are *not* buffered if the connection isn't ready. `activate_connection` handles the waiting.

### 3.4. Message Handling & Callbacks (`_listen_for_messages`, `BaseComponent`)

*   **Dispatch:** The `_listen_for_messages` thread receives messages. If a message has `type: "event"` or `type: "error"` and a `src` field (indicating the source UI component instance ID), it looks up the corresponding handler function in the `_message_handlers` dictionary using the `src` ID as the key.
*   **Handler Registration:** Each instance of a `BaseComponent` subclass (like `Grid`, `Console`, `Canvas`) registers its own `_internal_message_handler` method with the `connection` module during its `__init__`, using its unique `target_id`.
*   **`BaseComponent._internal_message_handler`:** This method receives the raw message dictionary from the dispatcher.
    *   It checks for `type: "error"` and calls the user's `_error_callback` (registered via `component.on_error()`) if it exists.
    *   Subclasses override this method to add logic for handling specific `type: "event"` messages (e.g., checking `payload['event'] == 'click'` in `Grid` or `Canvas`, or `payload['event'] == 'inputText'` in `Console` or `Control`), parsing relevant data from the `payload`, and calling the appropriate user callback (e.g., `self._click_callback`, `self._input_text_callback`).
*   **User Callbacks:** These are the functions provided by the user to methods like `grid.on_click()`, `console.on_input_text()`, `control.on_click()`, `canvas.on_click()`, etc. They are stored as instance attributes (e.g., `self._click_callback`) on the component object.
*   **Callback Exception Handling:** If an exception occurs *inside* a user's callback function when it's invoked by the listener thread, the library catches the exception, logs it using `logger.exception`, but **does not** crash the listener thread. This prevents one faulty callback from stopping the entire event processing system.

### 3.5. Component Interaction (`BaseComponent`, `_send_command`, `_send_update`)

*   **`BaseComponent`:** Provides the common foundation for all visual component classes.
    *   **`__init__`:** The constructor of any `BaseComponent` subclass (like `Grid()`, `Console()`) **implicitly triggers `connection.activate_connection()`**. This means simply creating the first component instance in your script is enough to initiate the blocking connection establishment process. It automatically generates a unique `target_id` for the instance and registers the instance's message handler.
    *   **`_send_command(type, payload)`:** Internal helper used only for `spawn` and `remove`. Constructs the message and calls `connection.send_message()`.
    *   **`_send_update(payload)`:** Internal helper used by most component methods that modify state (e.g., `grid.set_color`, `console.print`, `canvas.draw_line`). It constructs the full `update` message (including `type: "update"` and the provided `payload` which *must* already contain the component-specific `action` and `options`) and calls `connection.send_message()`.
    *   **`remove()`:** Unregisters the message handler, calls `_reset_specific_callbacks()` for subclass cleanup, and sends a `remove` command via `_send_command()`. May also trigger component-specific cleanup (like destroying canvas buffers).
    *   **`on_error(callback)`:** Registers the user's error handler.
*   **`_reset_specific_callbacks()`:** A virtual method in `BaseComponent` that subclasses override to clear their specific callback attributes (like `_click_callback`) during `remove()`.

### 3.6. Protocol Compliance: `snake_case` to `camelCase` Conversion

*   **Responsibility:** The conversion from Pythonic `snake_case` (used in public API arguments like `num_columns`, `line_color`) to the protocol-required `camelCase` (like `numColumns`, `lineColor`) for keys within the JSON `payload` (specifically within the `options` or `config` sub-dictionaries) happens **within the public API methods of the specific component classes** (e.g., `Grid.__init__`, `Grid.set_color`, `Canvas.draw_line`, `Viz.show`).
*   **Implementation:** These methods construct the `payload` dictionary (usually containing `action` and `options`) ensuring that all keys *within `options`* intended for the JSON message adhere to the `camelCase` convention defined in the [protocol specification](./protocol.md).
*   **`connection.send_message` Role:** The `connection` module **does not perform any case conversion**. It receives the fully constructed message dictionary (with `camelCase` keys already in the `payload.options`) from the component method and sends it as JSON.
*   **Canvas Specifics:** The `Canvas` component methods now also handle constructing the correct `action` name (e.g., `drawLine`) and ensuring the required `bufferId` and optional style parameters (as `camelCase`) are included in the `options` dictionary within the payload sent via `_send_update`. They also add the `commandId` to the payload before sending.

### 3.7. Reactivity (`ObservableValue`, `Viz`)

*   **`ObservableValue`:** A wrapper class for lists, dicts, and sets. It intercepts common mutation methods (e.g., `append`, `__setitem__`, `add`, `update`, `clear`). When a mutation occurs *through the wrapper*, it calls its internal `_notify()` method, passing along detailed `change_details` (type of change, path, values).
*   **Subscription:** When `Viz.show(name, obs_value)` is called with an `ObservableValue`, the `Viz` instance subscribes its internal `_handle_observable_update` method to the `obs_value`. It stores the returned `unsubscribe` function.
*   **`Viz._handle_observable_update(variable_name, change_details)`:** This method is the callback triggered by `_notify()`. It receives the `change_details`, uses the internal `_get_representation()` helper to convert involved Python values into the JSON representation format (handling depth, recursion, etc.), and constructs a granular `update` message payload (e.g., type 'setitem', variable name, path, valueRepresentation). This `update` message is then sent via `_send_update()`.
*   **Unsubscription:** When `Viz.remove_variable(name)` or `Viz.remove()` is called, the stored `unsubscribe` function for the corresponding `ObservableValue` is called to stop listening for changes.
*   **`_get_representation()`:** This crucial recursive helper function handles the conversion of arbitrary Python data into the specific nested JSON structure (`VizRepresentation`) required by the Viz UI component, applying depth/item limits and detecting recursion.

### 3.8. Canvas Double Buffering (`canvas.py`)

*   **Context Manager:** The `Canvas` class provides a `buffer()` method returning a context manager (`_CanvasBufferContextManager`). Using `with canvas.buffer() as buf:` provides a `_CanvasBufferProxy` object (`buf`).
*   **Proxy Object:** The `_CanvasBufferProxy` mirrors the Canvas drawing methods but automatically targets an acquired offscreen buffer ID.
*   **Buffer Pool:** `Canvas` maintains an internal pool (`_buffer_pool`) of offscreen buffer IDs managed via `_acquire_buffer_id` and `_release_buffer_id`.
*   **Protocol Commands:**
    *   `__enter__`: Acquires a buffer ID, sends `createBuffer` if needed, sends `clear` to the *offscreen* buffer.
    *   `buf.draw_*()`: Sends drawing commands with the acquired *offscreen* `bufferId`.
    *   `__exit__`: Sends `drawBuffer` (to draw the offscreen buffer onto the onscreen one) and releases the buffer ID back to the pool.
*   **Cleanup:** The `Canvas.remove()` method now attempts to send `destroyBuffer` commands for all known offscreen buffers.

### 3.9. Lifecycle & Synchronization Functions

*   **`run_forever()`:**
    *   Its primary role is to **block the main script thread** after ensuring the connection is ready.
    *   **Step 1:** Calls `activate_connection()` to ensure the connection is `CONNECTED_READY`. This initial call blocks or raises exceptions if connection fails.
    *   **Step 2:** Enters a loop that waits indefinitely on the `_shutdown_event`. This allows the background listener thread to continue processing UI events.
    *   **Step 3:** The loop terminates if `_shutdown_event` is set (by `shutdown()` or Ctrl+C) or if the connection status changes from `CONNECTED_READY` (indicating a potential disconnect detected by the listener).
    *   **Does NOT handle reconnection.** If a `SidekickDisconnectedError` occurs (typically raised via `close_connection` after the listener detects an issue), the `run_forever` loop will likely terminate as the exception propagates or the status check fails.
*   **`shutdown()`:** The public function to initiate a *clean* shutdown. Sets the `_shutdown_event` (to signal `run_forever` to exit) and calls `close_connection(is_exception=False)` to perform the actual cleanup and disconnection.
*   **`activate_connection()`:** As described in 3.1, this is the function that handles the **blocking connection establishment and readiness check**. Called implicitly before sends and by `run_forever`.

## 4. API Design Notes

*   **Public API:** Uses standard Python `snake_case` for function and method names (e.g., `set_color`, `run_forever`, `draw_line`).
*   **Error Handling Strategy:**
    *   **Argument Errors:** Methods generally raise standard Python exceptions like `ValueError`, `TypeError`, or `IndexError` for invalid user input (e.g., non-positive grid dimensions, out-of-bounds indices, invalid Canvas parameters like negative radius).
    *   **Connection Errors:** Failures related to establishing or maintaining the WebSocket connection (refused, timeout, disconnect) now primarily raise specific `SidekickConnectionError` subclasses. **These are generally unrecoverable by the library and require script-level handling if the script shouldn't terminate.**
    *   **Errors from Sidekick UI:** Messages with `type: "error"` received *from* the Sidekick UI (indicating a problem processing a command on the frontend) are routed to the `on_error` callback registered on the specific component instance. They do *not* typically raise Python exceptions.
    *   **User Callback Errors:** Exceptions occurring *inside* user-provided callback functions (`on_click`, `on_input_text`, etc.) are caught by the library's listener thread, logged using `logger.exception`, but **do not** stop the listener or raise exceptions that would halt `run_forever`.

## 5. Logging Strategy

*   Uses Python's standard `logging` module.
*   The root logger for the library is named `"sidekick"`.
*   A `logging.NullHandler` is added by default. This means library logs won't appear anywhere unless the user explicitly configures logging in their script (e.g., using `logging.basicConfig(level=logging.DEBUG)` or adding specific handlers to the `"sidekick"` logger).
*   Using `level=logging.DEBUG` is highly recommended when troubleshooting library issues.
