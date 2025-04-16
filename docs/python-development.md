# Sidekick Python Library (`sidekick-py`) Development Guide

## 1. Overview

This document provides a technical deep dive into the `sidekick-py` library, intended for developers contributing to the library or seeking to understand its internal mechanics. It details the implementation of the Python "Hero" interface for interacting with the Sidekick visualization panel.

The library's primary goal is to offer a high-level, intuitive Python API that abstracts the complexities of WebSocket communication, message formatting (including payload key casing conversion), connection management, peer discovery, and event handling based on the [Sidekick Communication Protocol](./protocol.md).

**Key Design Philosophy:**

The library operates under a specific connection model:

1.  **Mandatory Sidekick Presence:** The Sidekick VS Code panel and its internal WebSocket server **must** be running *before* the Python script attempts to establish a connection.
2.  **Blocking Connection Establishment:** The *first* operation requiring communication (e.g., creating a `sidekick.Grid()` or sending the first message) will **block** the Python script's execution until:
    *   A WebSocket connection to the Sidekick server is successfully established.
    *   The Sidekick UI panel signals back that it's online and ready.
3.  **Synchronous Sends:** Once the connection is ready, messages sent via module methods (like `grid.set_color()`) are attempted immediately. There is no internal queue or buffering if the connection is not ready; connection establishment blocks instead.
4.  **Exception-Based Error Handling:** Connection failures (initial refusal, timeout waiting for UI, disconnection during operation) will immediately **raise specific `SidekickConnectionError` exceptions**, halting the operation. The library does **not** attempt automatic reconnection. The user's script must handle these exceptions if recovery is desired (though typically the script would exit).

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
    ```

Editable mode (`-e`) links the installed package directly to your source code in `libs/python/src/sidekick`, so any changes you make are immediately reflected when you run Python scripts that import `sidekick`.

## 3. Core Implementation Details (`connection.py`)

The `connection.py` module orchestrates the WebSocket communication and connection lifecycle.

### 3.1. Connection Management & Lifecycle

*   **Shared State:** Manages a single, shared WebSocket connection (`_ws_connection`) and associated state using module-level variables.
*   **Thread Safety:** Uses a `threading.RLock` (`_connection_lock`) to protect access to shared state variables (like `_connection_status`, `_ws_connection`, `_message_handlers`) from race conditions between the main thread and the background listener thread.
*   **State Machine (`ConnectionStatus` Enum):** Tracks the connection's current state:
    *   `DISCONNECTED`: Initial state, or after `shutdown()` / error.
    *   `CONNECTING`: Actively trying to establish the WebSocket connection.
    *   `CONNECTED_WAITING_SIDEKICK`: Connected to the server, but waiting for the UI panel's 'online' signal.
    *   `CONNECTED_READY`: Fully connected and confirmed that a Sidekick UI is ready to receive commands.
*   **Blocking Activation (`activate_connection()`):**
    *   This is the **central function** ensuring the connection is ready before any communication attempt. It's called automatically by methods like `send_message` (used by module methods) and `run_forever`.
    *   If the status is `DISCONNECTED`, it calls the internal `_ensure_connection()` to attempt the WebSocket connection and start the listener thread.
    *   If `_ensure_connection()` succeeds (status becomes `CONNECTED_WAITING_SIDEKICK`), `activate_connection()` then **blocks** the calling thread by waiting on a `threading.Event` called `_ready_event`.
    *   The `_ready_event` is set **only** by the listener thread when it receives the first `system/announce` message with `role: "sidekick"` and `status: "online"`.
    *   If the initial connection via `_ensure_connection()` fails, it raises `SidekickConnectionRefusedError`.
    *   If the wait for the `_ready_event` exceeds `_SIDEKICK_WAIT_TIMEOUT` (default 2 seconds), it triggers cleanup and raises `SidekickTimeoutError`.
*   **Listener Thread (`_listen_for_messages()`):**
    *   Runs as a background **daemon thread** (`daemon=True`), meaning it won't prevent the main script from exiting if the main thread finishes.
    *   Enters a loop, using `websocket.recv()` with a short timeout (`_LISTENER_RECV_TIMEOUT`) to periodically check if the `_stop_event` has been set.
    *   Receives incoming JSON messages from the server.
    *   Parses the JSON.
    *   **Handles `system/announce` messages:** Tracks which Sidekick UI peers (`role: "sidekick"`) are online. When the *first* Sidekick UI announces itself as `online` *and* the connection status is `CONNECTED_WAITING_SIDEKICK`, it performs the crucial step of transitioning the status to `CONNECTED_READY` and **setting the `_ready_event`**, which unblocks the main thread waiting in `activate_connection()`.
    *   **Handles `event` and `error` messages:** Looks up the handler function registered for the message's `src` instance ID in the `_message_handlers` dictionary and calls it (typically the `_internal_message_handler` of the corresponding `BaseModule` subclass instance).
    *   Calls the optional `_global_message_handler` if registered.
    *   **Handles Unexpected Disconnection/Errors:** If the `recv()` call fails (e.g., server closes connection, network error) or an unexpected exception occurs within the listener loop, and if the `_stop_event` wasn't set (meaning it wasn't a planned shutdown), it triggers `close_connection(is_exception=True, ...)` in a *separate thread* to initiate cleanup and ensure a `SidekickDisconnectedError` is likely raised eventually.
*   **Error Handling & Exceptions:**
    *   `SidekickConnectionRefusedError`: Raised by `_ensure_connection` (via `activate_connection`) if the initial WebSocket `create_connection` fails. Indicates the server is likely not running or unreachable.
    *   `SidekickTimeoutError`: Raised by `activate_connection` if the connection to the server succeeds, but the `_ready_event` isn't set by the listener (because no Sidekick UI announced itself) within `_SIDEKICK_WAIT_TIMEOUT`.
    *   `SidekickDisconnectedError`: Raised by `send_message` if sending fails, or potentially by `close_connection` after cleanup if the closure was triggered by an unexpected listener termination or WebSocket error. Indicates the connection was lost *after* being established.
*   **Threading Primitives:** Uses `threading.Event` (`_stop_event`, `_ready_event`, `_shutdown_event`) for signaling between the main thread, listener thread, and shutdown logic. Uses `threading.RLock` (`_connection_lock`) for safe access to shared state.
*   **Shutdown Process (`close_connection()`, `shutdown()`, `atexit`):**
    *   `close_connection(is_exception, reason)`: The core cleanup function. Sets `_stop_event` to signal the listener thread, clears internal state (`_ws_connection`, status, handlers), attempts to send 'offline' announce and 'clearAll' (only on clean shutdown), closes the actual WebSocket socket, and joins the listener thread (waits for it to exit). Crucially, if called with `is_exception=True` (due to an error), it prepares a `SidekickDisconnectedError` to be raised *after* cleanup, unless `_shutdown_event` indicates a clean shutdown was requested concurrently.
    *   `shutdown()`: The public function for clean shutdown. Sets the `_shutdown_event` (to stop `run_forever`) and calls `close_connection(is_exception=False)`.
    *   `atexit.register(shutdown)`: Ensures `shutdown()` is called automatically when the Python script exits normally.

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

### 3.4. Message Handling & Callbacks (`_listen_for_messages`, `BaseModule`)

*   **Dispatch:** The `_listen_for_messages` thread receives messages. If a message has `type: "event"` or `type: "error"` and a `src` field (indicating the source UI module instance ID), it looks up the corresponding handler function in the `_message_handlers` dictionary using the `src` ID as the key.
*   **Handler Registration:** Each instance of a `BaseModule` subclass (like `Grid`, `Console`) registers its own `_internal_message_handler` method with the `connection` module during its `__init__`, using its unique `target_id`.
*   **`BaseModule._internal_message_handler`:** This method receives the raw message dictionary from the dispatcher.
    *   It checks for `type: "error"` and calls the user's `_error_callback` (registered via `module.on_error()`) if it exists.
    *   Subclasses override this method to add logic for handling specific `type: "event"` messages (e.g., checking `payload['event'] == 'click'`), parsing relevant data from the `payload`, and calling the appropriate user callback (e.g., `self._click_callback`, `self._input_text_callback`).
*   **User Callbacks:** These are the functions provided by the user to methods like `grid.on_click()`, `console.on_input_text()`, `control.on_click()`, etc. They are stored as instance attributes (e.g., `self._click_callback`) on the module object.
*   **Callback Exception Handling:** If an exception occurs *inside* a user's callback function when it's invoked by the listener thread, the library catches the exception, logs it using `logger.exception`, but **does not** crash the listener thread. This prevents one faulty callback from stopping the entire event processing system.

### 3.5. Module Interaction (`BaseModule`, `_send_command`)

*   **`BaseModule`:** Provides the common foundation for all visual module classes.
    *   **`__init__`:** The constructor of any `BaseModule` subclass (like `Grid()`, `Console()`) **implicitly triggers `connection.activate_connection()`**. This means simply creating the first module instance in your script is enough to initiate the blocking connection establishment process. It also generates the `target_id` and registers the instance's message handler.
    *   **`_send_command(type, payload)` / `_send_update(payload)`:** Internal helper methods used by public methods (like `set_color`, `print`, `add_button`). They construct the message dictionary (expecting the `payload` to already have `camelCase` keys where needed) and then call `connection.send_message()` to send it. They rely entirely on `send_message` for connection readiness checks and error handling.
    *   **`remove()`:** Unregisters the message handler, calls `_reset_specific_callbacks()` for subclass cleanup, and sends a `remove` command via `_send_command()`.
    *   **`on_error(callback)`:** Registers the user's error handler.
*   **`_reset_specific_callbacks()`:** A virtual method in `BaseModule` that subclasses override to clear their specific callback attributes (like `_click_callback`) during `remove()`.

### 3.6. Protocol Compliance: `snake_case` to `camelCase` Conversion

*   **Responsibility:** The conversion from Pythonic `snake_case` (used in public API arguments like `num_columns`) to the protocol-required `camelCase` (like `numColumns`) for keys within the JSON `payload` happens **within the public API methods of the specific module classes** (e.g., `Grid.__init__`, `Grid.set_color`, `Console.print`, `Control.add_button`, `Canvas._send_canvas_command`, `Viz.show`).
*   **Implementation:** These methods construct the `payload` dictionary (and any nested dictionaries like `options` or `config`) ensuring that all keys intended for the JSON message adhere to the `camelCase` convention defined in the [protocol specification](./protocol.md).
*   **`connection.send_message` Role:** The `connection` module **does not perform any case conversion**. It receives the fully constructed dictionary (with `camelCase` keys already in the `payload`) from the module method and sends it as JSON.

### 3.7. Reactivity (`ObservableValue`, `Viz`)

*   **`ObservableValue`:** A wrapper class for lists, dicts, and sets. It intercepts common mutation methods (e.g., `append`, `__setitem__`, `add`, `update`, `clear`). When a mutation occurs *through the wrapper*, it calls its internal `_notify()` method, passing along detailed `change_details` (type of change, path, values).
*   **Subscription:** When `Viz.show(name, obs_value)` is called with an `ObservableValue`, the `Viz` instance subscribes its internal `_handle_observable_update` method to the `obs_value`. It stores the returned `unsubscribe` function.
*   **`Viz._handle_observable_update(variable_name, change_details)`:** This method is the callback triggered by `_notify()`. It receives the `change_details`, uses the internal `_get_representation()` helper to convert involved Python values into the JSON representation format (handling depth, recursion, etc.), and constructs a granular `update` message payload (e.g., type 'setitem', variable name, path, valueRepresentation). This `update` message is then sent via `_send_update()`.
*   **Unsubscription:** When `Viz.remove_variable(name)` or `Viz.remove()` is called, the stored `unsubscribe` function for the corresponding `ObservableValue` is called to stop listening for changes.
*   **`_get_representation()`:** This crucial recursive helper function handles the conversion of arbitrary Python data into the specific nested JSON structure (`VizRepresentation`) required by the Viz UI component, applying depth/item limits and detecting recursion.

### 3.8. Lifecycle & Synchronization Functions

*   **`run_forever()`:**
    *   Its primary role is to **block the main script thread** after ensuring the connection is ready.
    *   **Step 1:** Calls `activate_connection()` to ensure the connection is `CONNECTED_READY`. This initial call blocks or raises exceptions if connection fails.
    *   **Step 2:** Enters a loop that waits indefinitely on the `_shutdown_event`. This allows the background listener thread to continue processing UI events.
    *   **Step 3:** The loop terminates if `_shutdown_event` is set (by `shutdown()` or Ctrl+C) or if the connection status changes from `CONNECTED_READY` (indicating a potential disconnect detected by the listener).
    *   **Does NOT handle reconnection.** If a `SidekickDisconnectedError` occurs (typically raised via `close_connection` after the listener detects an issue), the `run_forever` loop will likely terminate as the exception propagates or the status check fails.
*   **`shutdown()`:** The public function to initiate a *clean* shutdown. Sets the `_shutdown_event` (to signal `run_forever` to exit) and calls `close_connection(is_exception=False)` to perform the actual cleanup and disconnection.
*   **`activate_connection()`:** As described in 3.1, this is the function that handles the **blocking connection establishment and readiness check**. Called implicitly before sends and by `run_forever`.

## 4. API Design Notes

*   **Public API:** Uses standard Python `snake_case` for function and method names (e.g., `set_color`, `run_forever`).
*   **Error Handling Strategy:**
    *   **Argument Errors:** Methods generally raise standard Python exceptions like `ValueError`, `TypeError`, or `IndexError` for invalid user input (e.g., non-positive grid dimensions, out-of-bounds indices).
    *   **Connection Errors:** Failures related to establishing or maintaining the WebSocket connection (refused, timeout, disconnect) now primarily raise specific `SidekickConnectionError` subclasses. **These are generally unrecoverable by the library and require script-level handling if the script shouldn't terminate.**
    *   **Errors from Sidekick UI:** Messages with `type: "error"` received *from* the Sidekick UI (indicating a problem processing a command on the frontend) are routed to the `on_error` callback registered on the specific module instance. They do *not* typically raise Python exceptions.
    *   **User Callback Errors:** Exceptions occurring *inside* user-provided callback functions (`on_click`, `on_input_text`, etc.) are caught by the library's listener thread, logged using `logger.exception`, but **do not** stop the listener or raise exceptions that would halt `run_forever`.

## 5. Logging Strategy

*   Uses Python's standard `logging` module.
*   The root logger for the library is named `"sidekick"`.
*   A `logging.NullHandler` is added by default. This means library logs won't appear anywhere unless the user explicitly configures logging in their script (e.g., using `logging.basicConfig(level=logging.DEBUG)` or adding specific handlers to the `"sidekick"` logger).
*   Using `level=logging.DEBUG` is highly recommended when troubleshooting library issues.

## 6. Troubleshooting

*   **`SidekickConnectionRefusedError` on startup:**
    *   **Cause:** Cannot make initial WebSocket connection.
    *   **Check:** Is the Sidekick panel **open** in VS Code *before* running the script? Is the VS Code extension enabled and running? Is the configured URL (`sidekick.set_url()` or default `ws://localhost:5163`) correct? Is another process using that port (check VS Code "Sidekick Server" Output Channel for `EADDRINUSE`)? Check firewall settings.
*   **`SidekickTimeoutError` on startup:**
    *   **Cause:** Connected to the server, but the Sidekick UI panel didn't send its "online" announce message within the timeout (~2s).
    *   **Check:** Is the Sidekick panel **visible** and fully loaded in VS Code? Check the VS Code Developer Tools (Help -> Toggle Developer Tools) and the Webview Developer Tools (Open Sidekick Panel -> Command Palette -> "Developer: Open Webview Developer Tools") for errors related to the webapp loading or executing.
*   **`SidekickDisconnectedError` during script run:**
    *   **Cause:** Connection lost *after* being established.
    *   **Check:** Did the Sidekick panel remain open? Was VS Code closed or the extension disabled? Check the network connection. Check library DEBUG logs (`logging.basicConfig(level=logging.DEBUG)`) and the "Sidekick Server" Output Channel in VS Code for preceding errors (e.g., send/receive failures, ping timeouts).
*   **Commands Sent but No Effect in UI:**
    *   **Check for Exceptions:** Did a `SidekickConnectionError` get raised earlier, stopping execution before the command was fully processed? Wrap potentially failing Sidekick calls in `try...except SidekickConnectionError`.
    *   **Inspect Messages:** Use the Webview Developer Tools (Network -> WS tab) to inspect the actual JSON messages being sent. Verify `module`, `type`, `target`. **Critically, verify that all keys within the `payload` object are `camelCase` as required by the protocol.**
    *   **Check UI Console:** Look for errors in the Webview Developer Tools Console tab - the React app might be logging errors if it receives invalid commands.
    *   **Check Library Logs:** Enable DEBUG logging (`logging.basicConfig(level=logging.DEBUG)`) to see if `send_message` logs the attempt.
*   **Callbacks Not Firing (`on_click`, `on_input_text`, etc.):**
    *   **Is `run_forever()` called?** The script must be kept alive via `run_forever()` (or a similar blocking mechanism) for the listener thread to process incoming events and trigger callbacks.
    *   **Callback Correctly Registered?** Double-check the `module.on_click(my_handler)` call.
    *   **Check Library Logs:** Enable DEBUG logging. Look for logs indicating a message was received and dispatched to the correct handler (`Invoking handler for instance...`).
    *   **Add Logging in Callback:** Put a simple `print()` or `logger.info()` statement inside your callback function itself to confirm it's being entered.
    *   **Check for Callback Exceptions:** Look in the script's output/logs for logged exceptions originating *from within* your callback function (the library logs these but doesn't crash).
*   **Script Doesn't Exit After `run_forever()`:**
    *   Normal exit requires pressing Ctrl+C or calling `sidekick.shutdown()` from a callback.
    *   Check if any other non-daemon threads created by your script are preventing the main process from exiting.
*   **`Viz` Not Updating Automatically:**
    *   Are you using `sidekick.ObservableValue` to wrap the list/dict/set?
    *   Are you modifying the data *through the ObservableValue wrapper* methods (`.append()`, `[key]=`, `.add()`, `.update()`)? Modifying the *original* object after wrapping it won't trigger updates. Modifying attributes of objects *inside* the wrapped collection also won't trigger automatically unless those nested objects are *also* ObservableValues or you call `.set()` on the parent.
    *   Check DEBUG logs for messages like `"Received observable update..."` from `_handle_observable_update`.
    *   Check Webview DevTools (Network -> WS) to see if the granular `update` messages (with `action` like 'setitem', 'append') are being sent from Python to the UI.
    *   If complex objects aren't displaying correctly, review the `_get_representation` logic and its limitations (depth, item count, attribute skipping).