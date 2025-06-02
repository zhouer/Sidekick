# Sidekick Python Library (`sidekick-py`) Development Guide

## 1. Overview

This document provides a technical deep dive into the `sidekick-py` library, intended for developers contributing to the library or seeking to understand its internal mechanics. It details the Python "Hero" interface for interacting with the Sidekick UI.

The library's primary goal is to offer an intuitive Python API that abstracts the complexities of communication, message formatting, connection lifecycle, event handling, and component management. It is designed to be **async first** at its core but provides a **convenient synchronous facade** for typical CPython usage.

To set up for development, clone the main Sidekick repository. For the Python library specifically, navigate to the `Sidekick/libs/python` directory. You can then install it in editable mode using pip: `pip install -e .`. This allows you to make changes to the library source code and have them immediately reflected when you run your test scripts.

**Key Architectural Components (within `sidekick-py`):**

*   **`sidekick.config.ServerConfig` & `DEFAULT_SERVERS`**: Defines server connection configurations and a default list of servers (local, remote) to try.
*   **`sidekick.utils.generate_session_id()`**: Generates session IDs for connecting to remote servers.
*   **`sidekick.core.TaskManager`**: Manages an asyncio event loop.
    *   **CPython (`CPythonTaskManager`):** Runs the loop in a dedicated background thread. Startup includes a two-stage confirmation (loop set + responsiveness probe) to ensure reliability. The loop's main task (`_loop_runner_task`) uses `asyncio.sleep(0)` to remain responsive to tasks submitted from other threads.
    *   **Pyodide (`PyodideTaskManager`):** Uses the browser-provided event loop (in the Web Worker).
    *   Accessed via the singleton factory `sidekick.core.factories.get_task_manager()`.
*   **`sidekick.core.CommunicationManager` (ABC)**: Abstracts the raw transport layer.
    *   Concrete implementations: `WebSocketCommunicationManager` (CPython) and `PyodideCommunicationManager` (Pyodide).
    *   Its `connect_async` method now accepts message, status, and error handlers as arguments, ensuring they are set up before any messages can be processed from the transport layer.
    *   Instances are created by specific factory functions (`create_websocket_communication_manager`, `create_pyodide_communication_manager`) primarily invoked by the `ServerConnector`.
*   **`sidekick.server_connector.ServerConnector`**: Responsible for the **connection establishment strategy**. It attempts to connect to a Sidekick server by trying different approaches in a prioritized order:
    1.  Pyodide environment (direct JS bridge).
    2.  User-defined URL (if `sidekick.set_url()` was called).
    3.  A default list of servers (`DEFAULT_SERVERS` from `config.py`).
    It handles session ID generation and URL construction for remote servers. Its `connect_async` method accepts and relays the core handlers (message, status, error) to the underlying `CommunicationManager` it creates.
*   **`sidekick.connection.ConnectionService`**: The central orchestrator *after* a connection is successfully established by the `ServerConnector`. It uses the `TaskManager` and the `CommunicationManager` instance provided by the `ServerConnector`. It handles:
    *   The Sidekick-specific post-connection activation sequence (hero announce, waiting for sidekick UI announce, global clearAll). This activation sequence is managed by an internal asynchronous task (`_async_activate_and_run_message_queue`). During this sequence, it passes its internal handlers (`_handle_core_message`, etc.) to the `ServerConnector`'s `connect_async` method.
    *   Printing UI URLs and VS Code extension hints for remote connections.
    *   Message queuing for operations attempted before full activation.
    *   Serialization/deserialization of messages.
    *   Dispatching incoming UI events (`event`, `error` messages) to the correct `Component` instance handlers (via `_handle_core_message` which routes to component-specific handlers).
    *   Managing the overall service status post-connection.
    *   **Connection Activation:**
        *   `activate_connection_internally()`: This method is **non-blocking**. It ensures the asynchronous activation task (`_async_activate_and_run_message_queue`) is scheduled on the `TaskManager` if not already running or active. It does not wait for the activation to complete.
        *   `wait_for_active_connection_sync()`: (CPython specific) A method used internally by `sidekick.wait_for_connection()` and `sidekick.run_forever()` to **synchronously block** the calling (non-event-loop) thread until the asynchronous activation completes or fails. It uses a `threading.Event` for this synchronization.
*   **`sidekick.Component` (and subclasses like `Grid`, `Button`)**: User-facing classes representing UI elements.
    *   Their `__init__` methods are **non-blocking**. They send a "spawn" command via `ConnectionService.send_message_internally()`. If the service is not yet active, the command is queued, and `__init__` returns immediately.
    *   They delegate communication tasks to the `ConnectionService` (via module-level functions in `sidekick.connection`).

**Key Design Philosophy & Connection Model:**

1.  **Connection Priority & Fallback (via `ServerConnector`):**
    *   The library first checks if it's running in **Pyodide**. If so, it attempts to use `PyodideCommunicationManager`.
    *   If not in Pyodide, it checks if the user has specified a URL via **`sidekick.set_url()`**. If yes, it attempts to connect only to this URL.
    *   Otherwise, it iterates through the **`DEFAULT_SERVERS`** list.
2.  **Session IDs for Remote Servers:** Handled by `ServerConnector`.
3.  **UI URL Prompt:** Handled by `ConnectionService` after successful remote connection by `ServerConnector`.
4.  **Activation Process (Triggered by First Component or Explicit Call):**
    *   The *first* operation requiring communication (e.g., creating the first `sidekick.Grid()`, or an explicit `sidekick.activate_connection()`) triggers `ConnectionService.activate_connection_internally()`.
    *   `ConnectionService.activate_connection_internally()` is **non-blocking**. It schedules `_async_activate_and_run_message_queue` on the `TaskManager`.
    *   The `_async_activate_and_run_message_queue` coroutine then:
        1.  Invokes `ServerConnector.connect_async()`, passing its internal handlers (`_handle_core_message`, `_handle_core_status_change`, `_handle_core_error`). `ServerConnector` relays these to the chosen `CommunicationManager`'s `connect_async` method. This ensures handlers are set *before* the `CommunicationManager` starts processing incoming messages, preventing race conditions.
        2.  `ServerConnector.connect_async()` returns a connected `CommunicationManager` (or raises an error).
        3.  `ConnectionService` proceeds with its post-connection sequence: sending "hero online" `system/announce`, waiting for the Sidekick UI's "online" `system/announce`, sending `global/clearAll`, and then processing any queued messages.
    *   **CPython - Synchronous Waiting:**
        *   If a CPython user needs to wait for the connection to be active (e.g., before proceeding with critical UI interactions or when `run_forever()` starts), they can call `sidekick.wait_for_connection()`. This function internally calls `ConnectionService.wait_for_active_connection_sync()`, which blocks the calling thread (e.g., the main thread) until the `_async_activate_and_run_message_queue` completes or fails.
    *   **Pyodide:** Activation is entirely non-blocking. Messages are queued by `ConnectionService`. `await sidekick.run_forever_async()` will internally await the completion of the activation sequence.
5.  **Message Sending (`Component` -> `ConnectionService`):**
    *   Component methods call `sidekick.connection.send_message()`.
    *   `connection.send_message()` calls `ConnectionService.send_message_internally()`.
    *   `send_message_internally()` first calls `activate_connection_internally()` (non-blocking) to ensure the activation process is running or scheduled.
    *   If the service is not yet `ACTIVE`, the message is queued. Otherwise, it's sent via the established `CommunicationManager`.
6.  **Error Handling:**
    *   `ServerConnector` raises `SidekickConnectionError` or `SidekickConnectionRefusedError` if it cannot establish an initial connection. These are caught by `_async_activate_and_run_message_queue`.
    *   If `_async_activate_and_run_message_queue` fails (due to connection errors, timeouts waiting for UI announce, etc.), it stores the exception and signals completion.
    *   `ConnectionService.wait_for_active_connection_sync()` (CPython) will then re-raise this stored exception to the synchronously waiting thread.
    *   Once active, transport errors from `CommunicationManager` (reported via its error handler, which is `ConnectionService._handle_core_error`) are handled by `ConnectionService`, potentially leading to a `FAILED` state and `SidekickDisconnectedError` on subsequent operations.
7.  **No Automatic Reconnection (at `sidekick-py` level):** The library does **not** currently attempt automatic reconnection if a connection is lost after being established.

## 2. Core Implementation Details (`sidekick-py`)

### 2.1. `sidekick.config`
*   Defines `ServerConfig` and `DEFAULT_SERVERS`. Manages user-set URL.

### 2.2. `sidekick.utils`
*   Provides `generate_unique_id()`, `generate_session_id()`.

### 2.3. `sidekick.core` Sub-package
This sub-package contains foundational abstractions and their implementations:

*   **`core.status.CoreConnectionStatus`**: Enum for low-level transport states.
*   **`core.exceptions`**: Defines `CoreConnectionError` and related low-level exceptions.
*   **`core.utils.is_pyodide()`**: Detects execution environment.
*   **`core.TaskManager` (ABC)**:
    *   `CPythonTaskManager`: Manages an asyncio loop in a background thread.
        *   `ensure_loop_running()`: Now implements a two-stage confirmation. First, it waits for the loop thread to signal it has set its event loop. Second, it submits a "probe" coroutine and waits for its completion to ensure the loop is responsive to tasks submitted from other threads.
        *   `_loop_runner_task()`: The main coroutine for the event loop thread. It uses `asyncio.sleep(0)` in a `while` loop to continuously process tasks and check for shutdown, ensuring the loop remains responsive to `call_soon_threadsafe` calls.
        *   `_shutdown_requested_event_for_loop`: This `asyncio.Event` is now created within `_run_loop_in_thread` to ensure it's bound to the correct event loop.
    *   `PyodideTaskManager`: Uses Pyodide's existing asyncio loop.
    *   A singleton instance is provided by `core.factories.get_task_manager()`.
*   **`core.CommunicationManager` (ABC)**:
    *   `connect_async` method now accepts handlers (`message_handler`, `status_change_handler`, `error_handler`) to ensure they are set before message processing begins.
    *   Separate `register_xxx_handler` methods have been removed from the `CommunicationManager` public API for initial setup.
    *   `WebSocketCommunicationManager` (CPython) and `PyodideCommunicationManager` (Pyodide) are concrete implementations.
    *   Created by factory functions in `core.factories`.
*   **`core.factories`**: Provides `get_task_manager()` and creation functions for `CommunicationManager` implementations.

### 2.4. `sidekick.server_connector.ServerConnector`
*   Encapsulates connection attempt logic (Pyodide, user URL, default servers).
*   Its `connect_async(message_handler, status_change_handler, error_handler)` method now accepts the core handlers and passes them to the chosen `CommunicationManager`'s `connect_async` method. It returns a `ConnectionResult` with a connected `CommunicationManager` or raises an error.

### 2.5. `sidekick.connection.ConnectionService`
The `ConnectionService` is the central orchestrator.

*   **Singleton:** Accessed via `_get_service_instance()`.
*   **State Machine (`_ServiceStatus` Enum):** Tracks detailed lifecycle.
*   **`activate_connection_internally()`:**
    *   This method is now **non-blocking**.
    *   It checks the current service status. If activation is needed and not already in progress, it schedules the `_async_activate_and_run_message_queue` coroutine on the `TaskManager`.
    *   It uses `_sync_activation_complete_event` (`threading.Event`) and `_activation_exception` to communicate the result of the asynchronous activation back to any synchronous waiters (CPython).
*   **`_async_activate_and_run_message_queue()`:**
    *   This is the core asynchronous activation task. It:
        1.  Calls `self._server_connector.connect_async()`, passing its internal handlers (`_handle_core_message`, `_handle_core_status_change`, `_handle_core_error`) to it. This ensures the `CommunicationManager` instance created by `ServerConnector` has these handlers set *before* it starts processing any messages.
        2.  `_handle_core_message` (internal to `ConnectionService`) is responsible for receiving all messages from the `CommunicationManager` and then routing them to `_user_global_message_handler` (if set) and to the appropriate `_component_message_handlers` based on `instance_id`.
        3.  Performs the Sidekick protocol handshake: sends "hero online" `system/announce`, waits for Sidekick UI's "online" `system/announce` (with timeout), sends `global/clearAll`.
        4.  Processes any messages in `_message_queue`.
        5.  Sets service status to `ACTIVE`.
    *   Its completion (or failure) is signaled by `_activation_done_callback`.
*   **`_activation_done_callback()`:**
    *   Called when `_async_activate_and_run_message_queue` finishes.
    *   Stores any exception from the activation task into `self._activation_exception`.
    *   Sets `self._sync_activation_complete_event` to unblock synchronous waiters.
    *   Updates the final service status based on the outcome.
*   **`wait_for_active_connection_sync()`:**
    *   (CPython specific) Called by `sidekick.wait_for_connection()`.
    *   First, calls `activate_connection_internally()` (non-blocking) to ensure activation is scheduled.
    *   Then, blocks on `self._sync_activation_complete_event.wait(timeout)`.
    *   After unblocking, checks `self._activation_exception` and `self._service_status` to determine success or raise appropriate errors.
*   **Message Queuing (`_message_queue`):** Used for messages sent before `ACTIVE` state.
*   **Message Sending (`send_message_internally()` via module function `send_message`):**
    *   Calls `activate_connection_internally()` (non-blocking).
    *   If service is `ACTIVE`, serializes and sends via `self._communication_manager`. Otherwise, queues.
*   **Incoming Message Handling (`_handle_core_message`):** Deserializes JSON, calls global handler (if any), and routes messages to specific component handlers (`self._component_message_handlers`) or processes system messages (like "sidekick online" announce which sets `_sidekick_ui_online_event`).
*   **Core Status/Error Handling (`_handle_core_status_change`, `_handle_core_error`):** Updates service status based on feedback from `CommunicationManager`.
*   **Shutdown (`shutdown_service()` via module `shutdown()`):**
    *   Sends "hero offline" (best effort).
    *   Cancels ongoing `_async_activate_task` if any.
    *   Sets `_sync_activation_complete_event` with an error if waiters might be stuck.
    *   Schedules `self._communication_manager.close_async()`.
    *   Signals `TaskManager.signal_shutdown()`.

### 2.6. `sidekick.Component`
*   `__init__` is **non-blocking**. It calls `sidekick_connection_module.send_message()` which uses `ConnectionService.send_message_internally()`. The "spawn" command will be queued if the service isn't active yet.
*   Component instances register their `_internal_message_handler` with `ConnectionService`'s `_component_message_handlers` dictionary, keyed by `instance_id`.

### 2.7. Lifecycle & Synchronization Functions (`sidekick/__init__.py` wrappers)
*   **`sidekick.set_url(url)`:** Calls `config.set_user_url_globally(url)`.
*   **`sidekick.activate_connection()`:** Now non-blocking. Calls `ConnectionService.activate_connection_internally()`.
*   **`sidekick.wait_for_connection(timeout)` (CPython):** Blocks the calling thread until the connection is active or fails/times out. Internally calls `ConnectionService.wait_for_active_connection_sync()`.
*   **`sidekick.run_forever()` (CPython):**
    *   First, calls `sidekick.wait_for_connection()` to ensure the connection is active before proceeding. Handles exceptions from this wait.
    *   Then, calls `ConnectionService._task_manager.wait_for_shutdown()`.
*   **`sidekick.run_forever_async()` (Pyodide/Async):**
    *   Calls `ConnectionService.activate_connection_internally()` (which is non-blocking for Pyodide).
    *   Awaits the completion of the internal `_async_activate_task` (or checks `is_active()`) before proceeding to `ConnectionService._task_manager.wait_for_shutdown_async()`.
*   **`sidekick.shutdown()`:** Calls `ConnectionService.shutdown_service()`.
*   **`sidekick.submit_task(coro)`:** Delegates to `TaskManager.submit_task(coro)`. The `CPythonTaskManager`'s `submit_task` is now more robust due to improvements in `ensure_loop_running`.

## 3. API Design Notes

*   **Public API remains mostly synchronous for CPython ease of use,** but component initialization is now non-blocking.
*   `sidekick.wait_for_connection()` provides an explicit synchronous waiting point for CPython users.
*   `run_forever()` now robustly waits for connection before blocking for task manager shutdown.
*   Connection activation is an asynchronous process internally. Handlers for the core `CommunicationManager` are now passed during its `connect_async` call to prevent race conditions.
*   Pyodide users continue to use an async-first approach.