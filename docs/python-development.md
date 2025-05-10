# Sidekick Python Library (`sidekick-py`) Development Guide

## 1. Overview

This document provides a technical deep dive into the `sidekick-py` library, intended for developers contributing to the library or seeking to understand its internal mechanics. It details the implementation of the Python "Hero" interface for interacting with the Sidekick visualization panel or web UI.

The library's primary goal is to offer a high-level, intuitive Python API that abstracts the complexities of communication (WebSocket or direct JS calls), message formatting (including payload key casing conversion), connection management, peer discovery, event handling, and component lifecycle management based on the [Sidekick Communication Protocol](./protocol.md). It enables the creation and control of visual components like `Grid`, `Console`, `Canvas`, `Viz`, `Label`, `Button`, `Textbox`, `Markdown`, and layout containers like `Row` and `Column`.

**Key Design Philosophy:**

The library operates under a specific connection model:

1.  **Mandatory Sidekick Presence:** The Sidekick UI (VS Code panel or WebApp) and its communication layer (server or JS functions) **must** be running *before* the Python script attempts to establish a connection.
2.  **Blocking Connection Establishment:** The *first* operation requiring communication (e.g., creating the first `sidekick.Grid()` or `sidekick.Label()`) will **block** the Python script's execution until:
    *   A connection is successfully established (via WebSocket or direct JavaScript functions in Pyodide).
    *   The Sidekick UI panel signals back that it's online and ready via a `system/announce` message.
    *   Upon readiness, the library sends a `global/clearAll` message to the UI.
3.  **Synchronous Sends:** Once the connection is ready, messages sent via component methods (like `grid.set_color()` or `button.text = "New"`) are attempted immediately. There is no internal queue or buffering if the connection is not ready; connection establishment blocks instead.
4.  **Exception-Based Error Handling:** Connection failures (initial refusal, timeout waiting for UI, disconnection during operation) will immediately **raise specific `SidekickConnectionError` exceptions**, halting the operation. The library does **not** attempt automatic reconnection. The user's script must handle these exceptions if recovery is desired (though typically the script would exit).
5.  **Component Instance Identification:**
    *   Each component instance is assigned a unique **`instance_id`**.
    *   Users can optionally provide a custom `instance_id` (string) during component creation (e.g., `Button(..., instance_id="my-unique-button")`). If provided, this ID must be unique across all components in the script.
    *   If no `instance_id` is provided, the library automatically generates one (e.g., "button-1").
    *   Duplicate `instance_id`s (either user-provided or due to an unlikely collision with auto-generated ones if mixed) will cause a `ValueError` during component creation, preventing runtime ambiguity.
6.  **Component Parenting:** Components can be nested using several methods:
    *   The `parent` argument in a component's constructor (`Button(..., parent=my_row)`).
    *   The `container.add_child(component)` method on `Row` or `Column` instances after creation.
    *   Passing existing child components as positional arguments to the `Row` or `Column` constructor (`Row(button1, label1)`). Internally, this uses `add_child`.
7.  **UI Event Handling (Structured Events):** User interactions (clicks, text submissions) in the UI trigger event messages back to Python. These are dispatched to specific callback functions registered via:
    *   Constructor parameters (e.g., `Button(..., on_click=my_handler)`).
    *   Dedicated methods (e.g., `button.on_click(my_handler)`).
    *   Decorators (e.g., `@button.click`).
    *   All event callbacks now receive a single, **structured event object** (e.g., `ButtonClickEvent`, `GridClickEvent`) as their argument. This object contains event-specific data (like coordinates for a grid click, or the submitted value for a textbox) as well as common contextual information like the `instance_id` of the component that triggered the event and the event `type`. See `sidekick.events` for defined event classes.

## 2. Development Setup

To work on the library code:

1.  Clone the main Sidekick repository.
2.  Navigate to the **project root directory** (`Sidekick/`).
3.  Install `sidekick-py` in editable mode using pip:
    ```bash
    # Make sure you are in the Sidekick/ project root
    pip install -e libs/python
    ```
4.  Ensure development dependencies are installed (if using WebSocket):
    ```bash
    # Install if you don't have it already
    pip install websocket-client
    ```
5.  For testing Pyodide support, you'll need to set up a Pyodide environment (e.g., running the `webapp` locally, which includes Pyodide).

Editable mode (`-e`) links the installed package directly to your source code in `libs/python/src/sidekick`, so any changes you make are immediately reflected when you run Python scripts that import `sidekick`.

## 3. Core Implementation Details

### 3.0. Communication Channel Abstraction

The library uses an abstract communication channel interface (`CommunicationChannel` in `channel.py`) to support different communication methods:

*   **`WebSocketChannel`:** (`websocket_channel.py`) Uses WebSockets via `websocket-client` for standard Python environments, connecting to the Sidekick server (default `ws://localhost:5163`).
*   **`PyodideChannel`:** (`pyodide_channel.py`) Uses direct JavaScript function calls (`sendHeroMessage`, `registerSidekickMessageHandler`) for communication within a Pyodide (browser) environment.
*   **Factory Function (`create_communication_channel`):** (`channel.py`) Detects the environment (Pyodide vs. standard Python) and instantiates the appropriate channel.

### 3.1. Connection Management & Lifecycle (`connection.py`)

This module orchestrates the communication channel and connection lifecycle.

*   **Shared State:** Manages a single, shared communication channel (`_channel`) and associated state (`_connection_status`, `_message_handlers`, etc.) using module-level variables.
*   **Thread Safety:** Uses `threading.RLock` (`_connection_lock`) to protect shared state.
*   **State Machine (`ConnectionStatus` Enum):** Tracks connection state (`DISCONNECTED`, `CONNECTING`, `CONNECTED_WAITING_SIDEKICK`, `CONNECTED_READY`).
*   **Blocking Activation (`activate_connection()`):**
    *   Central function ensuring readiness before communication. Called implicitly by component methods and `run_forever`.
    *   If `DISCONNECTED`, calls `_ensure_connection()` to create/connect the channel.
    *   If connection succeeds (status becomes `CONNECTED_WAITING_SIDEKICK`), **blocks** the calling thread by waiting on `_ready_event` (a `threading.Event`).
    *   `_ready_event` is set by `_handle_incoming_message` upon receiving the first `system/announce` (`role: "sidekick", status: "online"`) from the UI.
    *   Raises `SidekickConnectionRefusedError` on initial connect failure or `SidekickTimeoutError` if waiting for the UI's `_ready_event` exceeds `_SIDEKICK_WAIT_TIMEOUT`.
    *   Once `CONNECTED_READY` is reached, it sends a `global/clearAll` command to the UI.
*   **Instance ID Uniqueness Check:** The `register_message_handler(instance_id, handler)` function in `connection.py` now checks if the provided `instance_id` is already present in its `_message_handlers` dictionary. If a duplicate ID is detected, it raises a `ValueError`, which typically causes the offending component's `__init__` to fail, thus preventing runtime issues from ID collisions.
*   **Message Handling (`_handle_incoming_message`):**
    *   Called by the channel implementation when a message arrives.
    *   Handles `system/announce` to track UI readiness and set `_ready_event`.
    *   Handles `event` messages: Looks up the handler function registered for the message's `src` instance ID in `_message_handlers` and calls it (typically the `_internal_message_handler` of the corresponding `Component` instance). The `src` field from the UI message corresponds to the component's `instance_id`.
    *   Handles `error` messages: Also routes to the specific component's `_internal_message_handler`.
*   **Error Handling & Exceptions:** Raises specific `SidekickConnectionError` subclasses for different failure modes (Refused, Timeout, Disconnected).
*   **Threading Primitives:** Uses `threading.Event` and `threading.RLock` for synchronization and state protection.
*   **Shutdown Process (`close_connection()`, `shutdown()`, `atexit`):** Manages clean disconnection, attempting to send an `offline` announce (best-effort) and cleaning up resources. **Does not clear the UI on shutdown.**

### 3.2. Peer Discovery (`system/announce`)

*   On successful connection, the library sends `system/announce` (`role: "hero", status: "online"`).
*   `_handle_incoming_message` listens for `system/announce` (`role: "sidekick", status: "online"`).
*   Receiving the first such message from a Sidekick UI triggers the state transition to `CONNECTED_READY` and sets `_ready_event`.

### 3.3. Message Sending (`send_message()`)

*   Gatekeeper function called internally by components.
*   Calls `activate_connection()` (blocking if needed).
*   If ready, acquires lock and sends the message via the channel's `send_message` method. The message's `"target"` field (for commands to UI) will contain the component's `instance_id`.
*   Handles send errors by triggering `close_connection(is_exception=True)` and raising `SidekickDisconnectedError`.
*   No internal buffering; `activate_connection` handles waiting for readiness.

### 3.4. Structured Event Model (`sidekick.events`) and Callback Handling

*   A new module `sidekick.events` defines structured event classes (e.g., `ButtonClickEvent`, `GridClickEvent`, `ErrorEvent`) using `dataclasses`. These inherit from a `BaseSidekickEvent` which includes `instance_id` and `type`.
*   **Dispatch:** `connection._handle_incoming_message` routes incoming `event` and `error` messages (raw dictionaries) based on the `src` field (the `instance_id` of the UI component that sent the message) to the appropriate handler in `_message_handlers`.
*   **Handler Registration:** `Component.__init__` registers its `_internal_message_handler` method using its unique `instance_id`.
*   **`Component._internal_message_handler`:**
    *   Base implementation handles `type: "error"` messages by:
        1.  Extracting the error message string from the UI payload.
        2.  Constructing an `ErrorEvent` object (from `sidekick.events`), populating its `instance_id` (with `self.instance_id`) and `message`.
        3.  Calling the user's registered error callback (`_error_callback`) with this `ErrorEvent` object, if the callback is set.
    *   **Subclasses override** this to handle their specific `type: "event"` messages. For example:
        *   `Grid`: Checks `payload['event'] == 'click'`, extracts `x`, `y`, constructs a `GridClickEvent(instance_id=self.instance_id, x=x, y=y)`, and calls `_click_callback` with this event object.
        *   `Button`: Checks `payload['event'] == 'click'`, constructs a `ButtonClickEvent(instance_id=self.instance_id)`, and calls `_click_callback` with this event object.
        *   `Textbox`: Checks `payload['event'] == 'submit'`, extracts `value`, updates its internal `_value`, constructs a `TextboxSubmitEvent(instance_id=self.instance_id, value=value)`, and calls `_submit_callback` with this event object.
*   **User Callbacks:** Functions provided by the user (e.g., via constructor params like `on_click=`, methods like `button.on_click()`, or decorators like `@textbox.submit`) are stored on the component instance (e.g., `_click_callback`) and called by the `_internal_message_handler` with the appropriate structured event object.
*   **Callback Exception Handling:** Exceptions *inside* user callbacks are caught by the `_internal_message_handler` and logged via `logger.exception`. They do **not** crash the listener thread or `run_forever`.

### 3.5. Component Interaction (`Component`, `_send_command`, `_send_update`)

*   **`Component`:** Foundation for all visual/UI components.
    *   **`__init__`:**
        *   Implicitly calls `connection.activate_connection()` (blocking on first component creation).
        *   Handles `instance_id`:
            *   Accepts an optional `instance_id: str` argument.
            *   If provided, it's stripped and validated (non-empty).
            *   If not provided or invalid, `generate_unique_id(component_type)` is used.
            *   The final `instance_id` is stored as `self.instance_id`.
        *   Registers `_internal_message_handler` with `connection.register_message_handler(self.instance_id, ...)`, which also performs uniqueness validation for the `instance_id`.
        *   Accepts optional `parent` (instance or ID string). If provided, adds `{"parent": parent_id}` to the `spawn` payload. If `parent` is `None`, the key is omitted, defaulting to `"root"` in the UI.
        *   Accepts optional `on_error: Callable[[ErrorEvent], None]` callback and registers it using `self.on_error()`.
        *   Sends the `spawn` command via `_send_command()`. The `"target"` field in the message will be `self.instance_id`.
    *   **Subclass `__init__`:**
        *   Accept component-specific arguments (e.g., `text` for `Button`).
        *   Accept relevant event callbacks (e.g., `on_click`, `on_submit` with updated signatures taking event objects) and register them using the component's specific methods (`self.on_click`, `self.on_submit`).
        *   Call `super().__init__(..., instance_id=instance_id, on_error=on_error)` to handle base initialization, `instance_id` processing, and error callback registration.
    *   **`_send_command(type, payload)`:** Internal helper for `spawn` and `remove`. Constructs message with `component_type`, `msg_type`, `target: self.instance_id`, and `payload`, then calls `connection.send_message()`.
    *   **`_send_update(payload)`:** Internal helper for methods modifying state (e.g., `grid.set_color`, `label.text = ...`). Constructs `update` message (`type: "update"`, `target: self.instance_id`, `payload: {action: ..., options: ...}`). The `payload` passed *to* `_send_update` must contain the specific `action` and `options`.
    *   **`remove()`:** Unregisters handler, resets callbacks (`_reset_specific_callbacks`), sends `remove` command targeting `self.instance_id`.
    *   **`on_error(callback: Callable[[ErrorEvent], None])` / `on_click(callback: Callable[[SpecificEvent], None])` etc.:** Public methods to register/unregister user callbacks after initialization, now with updated signatures for structured event objects.
*   **`_reset_specific_callbacks()`:** Virtual method overridden by subclasses to clear their specific callback attributes during `remove()`.
*   **Layout (`Row`, `Column`):**
    *   `__init__` accepts `*children` arguments. It iterates through them and calls `self.add_child()` for each.
    *   `add_child(child_component)` method calls `child_component._send_update(...)` with an action `changeParent` and options `{"parent": self.instance_id}`. The child component sends the message about itself being moved.

### 3.6. Reactivity (`ObservableValue`, `Viz`)

*   **`ObservableValue`:** Wrapper for lists, dicts, sets. Intercepts mutation methods and calls `_notify()`.
*   **`Viz.show()`:** If passed an `ObservableValue`, subscribes its `_handle_observable_update` method.
*   **`Viz._handle_observable_update`:** Triggered by `ObservableValue._notify()`. Constructs granular `update` message payload and sends via `_send_update()`.
*   **`_get_representation()`:** Internal recursive helper converting Python data to the JSON structure required by Viz UI.

### 3.7. Canvas Double Buffering (`canvas.py`)

*   `Canvas.buffer()` returns a context manager (`_CanvasBufferContextManager`).
*   Proxy methods (`buf.draw_*()`) automatically target an acquired offscreen buffer ID.
*   `_CanvasBufferContextManager.__enter__` acquires buffer ID, clears the offscreen buffer.
*   `_CanvasBufferContextManager.__exit__` sends `drawBuffer` (offscreen -> onscreen) command.

### 3.8. Lifecycle & Synchronization Functions

*   **`run_forever()`:** Blocks main script thread after ensuring connection is ready (`activate_connection`). Waits on `_shutdown_event`.
*   **`shutdown()`:** Initiates clean shutdown. Sets `_shutdown_event`, calls `close_connection(is_exception=False)`.
*   **`activate_connection()`:** Handles blocking connection establishment and readiness check.

## 4. API Design Notes

*   **Public API:** Uses standard Python `snake_case` for functions/methods, `CapWords` for classes. Component configuration via `__init__` arguments (including optional `instance_id`), state modification/retrieval via properties or methods.
*   **Event Handling:**
    *   Now uses a **structured event model**. All interactive event callbacks (`on_click`, `on_submit`, etc.) and error callbacks (`on_error`) receive a single event object (e.g., `ButtonClickEvent`, `GridClickEvent`, `ErrorEvent` from `sidekick.events`) as their argument.
    *   This event object contains event-specific data (e.g., coordinates, submitted value) as well as common context like the `instance_id` of the source component and the event `type`.
    *   Callbacks are registered via constructor parameters (e.g., `on_click=...`), dedicated methods (e.g., `component.on_click()`), or decorators (e.g., `@component.click`).
*   **Error Handling Strategy:**
    *   **Argument Errors:** Standard Python exceptions (`ValueError`, `TypeError`, `IndexError`) for invalid user input to methods/constructors. This includes `ValueError` for duplicate `instance_id`s.
    *   **Connection Errors:** Specific `SidekickConnectionError` subclasses raised for connection issues (Refused, Timeout, Disconnected). Generally unrecoverable by the library.
    *   **Errors from Sidekick UI:** Messages with `type: "error"` received from the UI are routed to the component's error callback (`_error_callback`, set via constructor `on_error=` or `component.on_error()`). The callback receives an `ErrorEvent` object. These do not typically raise Python exceptions in the main flow.
    *   **User Callback Errors:** Exceptions *inside* user callbacks (`on_click`, `on_error`, etc.) are caught by the internal message handler, logged via `logger.exception`, but do not stop the listener or `run_forever`.

## 5. Logging Strategy

*   Uses Python's standard `logging` module. Root logger `"sidekick"`.
*   Default `logging.NullHandler` prevents logs unless user configures logging (e.g., `logging.basicConfig(level=logging.DEBUG)`).
