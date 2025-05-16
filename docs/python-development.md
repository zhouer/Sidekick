# Sidekick Python Library (`sidekick-py`) Development Guide

## 1. Overview

This document provides a technical deep dive into the `sidekick-py` library, intended for developers contributing to the library or seeking to understand its internal mechanics. It details the Python "Hero" interface for interacting with the Sidekick UI.

The library's primary goal is to offer an intuitive Python API that abstracts the complexities of communication, message formatting, connection lifecycle, event handling, and component management. It is designed to be **async first** at its core but provides a **convenient synchronous facade** for typical CPython usage.

**Key Architectural Components (within `sidekick-py`):**

*   **`sidekick.core.TaskManager`:** Manages an asyncio event loop.
    *   **CPython:** Runs the loop in a dedicated background thread.
    *   **Pyodide:** Uses the browser-provided event loop (in the Web Worker).
*   **`sidekick.core.CommunicationManager`:** Abstracts the raw transport layer.
    *   **CPython:** `WebSocketCommunicationManager` using the `websockets` library.
    *   **Pyodide:** `PyodideCommunicationManager` using JavaScript bridge functions (`js` module, `pyodide.ffi`).
*   **`sidekick.connection.ConnectionService`:** The central orchestrator. It uses the `TaskManager` and `CommunicationManager`. It handles:
    *   The Sidekick-specific activation sequence (hero announce, waiting for sidekick UI announce, global clearAll).
    *   Message queuing for operations attempted before full activation (especially relevant in Pyodide's non-blocking activation).
    *   Serialization/deserialization of messages between Python dicts and JSON strings.
    *   Dispatching incoming UI events (`event`, `error` messages) to the correct `Component` instance handlers.
    *   Managing the overall service status.
*   **`sidekick.Component` (and subclasses like `Grid`, `Button`):** User-facing classes that represent UI elements. They delegate communication tasks to the `ConnectionService`.

**Key Design Philosophy & Connection Model:**

1.  **Sidekick Infrastructure Prerequisite:** The Sidekick UI (VS Code panel or WebApp) and its communication layer (WebSocket server or JS bridge) **must** be active *before* `sidekick-py` attempts a full connection.
2.  **Activation Process:**
    *   The *first* operation requiring communication (e.g., creating the first `sidekick.Grid()`, or an explicit `sidekick.activate_connection()`) triggers the `ConnectionService`'s activation sequence. This sequence is asynchronous internally.
    *   **CPython:** The `activate_connection()` call (and thus the first component creation) **blocks** the calling (main) thread until the full activation sequence (core transport connected -> hero online sent -> sidekick UI online received -> global clearAll sent -> message queue flushed) completes or fails.
    *   **Pyodide:** The `activate_connection()` call is **non-blocking**. It initiates the asynchronous activation sequence. Messages sent by components during this pending activation are queued by the `ConnectionService` and dispatched after successful activation.
3.  **Message Sending:**
    *   Component methods (e.g., `grid.set_color()`) call internal `_send_update` or `_send_command` methods, which then use `ConnectionService.send_message()`.
    *   `ConnectionService.send_message()`:
        *   If the service is not yet fully active (i.e., `global/clearAll` not yet sent and queue not flushed), messages are queued.
        *   If active, messages are serialized to JSON and scheduled for asynchronous sending via the `CommunicationManager` and `TaskManager`. The `send_message()` call itself is non-blocking from the `Component`'s perspective (it submits the send task).
4.  **Error Handling:**
    *   Failures during CPython's blocking `activate_connection()` will raise `SidekickConnectionRefusedError`, `SidekickTimeoutError` (for UI readiness timeout), or `SidekickConnectionError`.
    *   Failures during Pyodide's non-blocking activation might be reported via logs or by subsequent operations failing if the activation doesn't eventually succeed. A failed `_async_activate_task` will set the service status to `FAILED`.
    *   Once active, transport errors caught by `CommunicationManager` are reported to `ConnectionService`, which may transition the service to a `FAILED` state and raise `SidekickDisconnectedError` on subsequent operations.
5.  **No Automatic Reconnection:** The library does **not** currently attempt automatic reconnection if a connection is lost after being established.
6.  **Component Instance ID & Parenting:** Handled as before by `Component` and its subclasses, with `ConnectionService` now managing the `instance_id` uniqueness check during handler registration.
7.  **UI Event Handling (Structured Events):** Works as before. `ConnectionService` receives raw messages from `CommunicationManager`, deserializes, and routes them to the `_internal_message_handler` of the target `Component` instance.

## 2. Development Setup

(Setup instructions remain largely the same: clone, editable install `pip install -e libs/python`)

## 3. Core Implementation Details (`sidekick-py`)

### 3.0. `sidekick.core` Sub-package
This new sub-package contains the foundational, environment-agnostic abstractions and their concrete CPython/Pyodide implementations:

*   **`core.status.CoreConnectionStatus`**: Enum for low-level transport connection states.
*   **`core.exceptions`**: Defines `CoreConnectionError` and related low-level exceptions.
*   **`core.utils.is_pyodide()`**: Detects the execution environment.
*   **`core.TaskManager` (ABC)**:
    *   `CPythonTaskManager`: Manages an asyncio loop in a background thread. Uses `threading` and `concurrent.futures` for sync/async bridging.
    *   `PyodideTaskManager`: Uses Pyodide's existing asyncio loop. Avoids blocking calls.
*   **`core.CommunicationManager` (ABC)**:
    *   `WebSocketCommunicationManager` (CPython): Uses `websockets` library for async WebSocket comms. Needs `TaskManager`.
    *   `PyodideCommunicationManager` (Pyodide): Uses `js` module and `pyodide.ffi` for JS bridge. Needs `TaskManager`.
*   **`core.factories.get_task_manager()`, `get_communication_manager()`**: Singleton factories providing the correct manager instances based on `is_pyodide()`.

### 3.1. `sidekick.connection.ConnectionService`
The new central service orchestrating all communication logic:

*   **Singleton:** Accessed via `ConnectionService.get_instance()` (used by module-level functions).
*   **State Machine (`_ServiceStatus` Enum):** Tracks detailed lifecycle: `IDLE`, `ACTIVATING_SCHEDULED`, `CORE_CONNECTING`, `CORE_CONNECTED`, `WAITING_SIDEKICK_ANNOUNCE`, `ACTIVE`, `FAILED`, `SHUTTING_DOWN`, `SHUTDOWN_COMPLETE`.
*   **Async Activation (`_async_activate_and_run_message_queue`):**
    *   Launched as an `asyncio.Task` by the `TaskManager`.
    *   Sequence:
        1.  Gets/Creates and connects `CommunicationManager` (`await cm.connect_async()`).
        2.  Waits for `_core_transport_connected_event` (set by `_handle_core_status_change`).
        3.  Sends "hero online" `system/announce` (`await cm.send_message_async()`).
        4.  Waits for `_sidekick_ui_online_event` (set by `_handle_core_message` on "sidekick online" announce, with timeout).
        5.  Sends `global/clearAll` (`await cm.send_message_async()`).
        6.  Processes any messages in `_message_queue`.
        7.  Sets service status to `ACTIVE` and sets `_clearall_sent_and_queue_processed_event`.
    *   Exceptions during this process are caught, set the service to `FAILED`, and are propagated to CPython's blocking `activate_connection()` call via its `_activation_done_callback` and `_re_raise_activation_failure_if_any()`.
*   **Blocking `activate_connection()` (CPython):**
    *   Launches `_async_activate_and_run_message_queue`.
    *   Uses a `threading.Condition` (`_activation_cv`) to block the calling thread until the async activation task completes (success or failure), signaled by `_activation_done_callback`.
*   **Non-blocking `activate_connection()` (Pyodide):**
    *   Launches `_async_activate_and_run_message_queue` and returns, allowing the caller to continue.
*   **Message Queuing (`_message_queue`):**
    *   `send_message()` adds messages to this `deque` if `_clearall_sent_and_queue_processed_event` is not yet set.
    *   The queue is processed at the end of successful activation.
*   **Message Sending (`send_message()` via module function):**
    *   If service is `ACTIVE` and ready, serializes to JSON and uses `TaskManager.submit_task(cm.send_message_async(json_str))` for fire-and-forget sending.
    *   Otherwise, queues the message (and implicitly triggers activation if needed).
*   **Incoming Message Handling (`_handle_core_message`):**
    *   Callback registered with `CommunicationManager`. Receives raw JSON strings.
    *   Deserializes JSON.
    *   Calls user's global handler (if any).
    *   Processes `system/announce` from "sidekick" role to set `_sidekick_ui_online_event`.
    *   Dispatches `event` and `error` messages to the appropriate `Component._internal_message_handler` based on `src` (instance_id). Component handlers are called **synchronously** from this callback as per design.
*   **Core Status/Error Handling (`_handle_core_status_change`, `_handle_core_error`):**
    *   Callbacks registered with `CommunicationManager`.
    *   Update `_service_status` (e.g., to `FAILED` if core transport disconnects).
    *   Signal CPython's blocking `activate_connection` via `_activation_cv` if an error occurs during its wait.
*   **Shutdown (`shutdown_service()` via module `shutdown()`):**
    *   Cancels `_async_activate_task` if running.
    *   Clears queue and internal events.
    *   Sends "hero offline" `system/announce` (best effort, async).
    *   Schedules `CommunicationManager.close_async()` (async).
    *   Signals `TaskManager.signal_shutdown()`.
    *   Clears component handlers and sets status to `SHUTDOWN_COMPLETE`.

### 3.2. `sidekick.Component`
*   `__init__` now relies on `ConnectionService.send_message()` (for the "spawn" command) to implicitly trigger service activation. It no longer calls an explicit `activate_connection` function itself.
*   Registers/unregisters its `_internal_message_handler` with `ConnectionService`.
*   `_send_command` and `_send_update` use `ConnectionService.send_message()`.
*   Otherwise, its public API and internal logic for subclasses remain largely unchanged.

### 3.3. Lifecycle & Synchronization Functions
*   **`sidekick.run_forever()` (CPython):** Calls `ConnectionService.activate_connection()` (blocking), then `TaskManager.wait_for_shutdown()` (blocking).
*   **`sidekick.run_forever_async()` (Pyodide/Async):** Calls `ConnectionService.activate_connection()` (non-blocking initiator), then `await async_activation_task` (internal to `ConnectionService.run_service_forever_async`), then `await TaskManager.wait_for_shutdown_async()`.
*   **`sidekick.shutdown()`:** Calls `ConnectionService.shutdown_service()`.
*   **`sidekick.submit_task(coro)`:** New API. Delegates to `TaskManager.submit_task(coro)`.

## 4. API Design Notes (Recap)

*   **Public API remains mostly synchronous for CPython ease of use.**
*   Pyodide users and advanced CPython users can leverage `run_forever_async` and `submit_task`.
*   Structured event objects (`ButtonClickEvent`, etc.) are still used for component callbacks.
*   Error handling strategy: `ConnectionService` catches `Core...Error`s and may raise corresponding `Sidekick...Error`s. Component methods might raise `SidekickDisconnectedError` if `send_message` fails due to service not being active.

## 5. Logging Strategy

*   Root logger "sidekick". Submodule loggers like "sidekick.connection", "sidekick.core.cpython_task_manager".
*   Default `NullHandler`.