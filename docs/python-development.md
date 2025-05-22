# Sidekick Python Library (`sidekick-py`) Development Guide

## 1. Overview

This document provides a technical deep dive into the `sidekick-py` library, intended for developers contributing to the library or seeking to understand its internal mechanics. It details the Python "Hero" interface for interacting with the Sidekick UI.

The library's primary goal is to offer an intuitive Python API that abstracts the complexities of communication, message formatting, connection lifecycle, event handling, and component management. It is designed to be **async first** at its core but provides a **convenient synchronous facade** for typical CPython usage.

To set up for development, clone the main Sidekick repository. For the Python library specifically, navigate to the `Sidekick/libs/python` directory. You can then install it in editable mode using pip: `pip install -e .`. This allows you to make changes to the library source code and have them immediately reflected when you run your test scripts.

**Key Architectural Components (within `sidekick-py`):**

*   **`sidekick.config.ServerConfig` & `DEFAULT_SERVERS`**: Defines server connection configurations and a default list of servers (local, remote) to try.
*   **`sidekick.utils.generate_session_id()`**: Generates session IDs for connecting to remote servers.
*   **`sidekick.core.TaskManager`**: Manages an asyncio event loop.
    *   **CPython (`CPythonTaskManager`):** Runs the loop in a dedicated background thread.
    *   **Pyodide (`PyodideTaskManager`):** Uses the browser-provided event loop (in the Web Worker).
    *   Accessed via the singleton factory `sidekick.core.factories.get_task_manager()`.
*   **`sidekick.core.CommunicationManager` (ABC)**: Abstracts the raw transport layer.
    *   Concrete implementations: `WebSocketCommunicationManager` (CPython) and `PyodideCommunicationManager` (Pyodide).
    *   Instances are now created by specific factory functions (`create_websocket_communication_manager`, `create_pyodide_communication_manager`) primarily invoked by the `ServerConnector`.
*   **`sidekick.server_connector.ServerConnector`**: A new component responsible for the **connection establishment strategy**. It attempts to connect to a Sidekick server by trying different approaches in a prioritized order:
    1.  Pyodide environment (direct JS bridge).
    2.  User-defined URL (if `sidekick.set_url()` was called).
    3.  A default list of servers (`DEFAULT_SERVERS` from `config.py`), typically trying local VS Code extension first, then remote cloud servers.
    It handles session ID generation and URL construction for remote servers.
*   **`sidekick.connection.ConnectionService`**: The central orchestrator *after* a connection is successfully established by the `ServerConnector`. It uses the `TaskManager` and the `CommunicationManager` instance provided by the `ServerConnector`. It handles:
    *   The Sidekick-specific post-connection activation sequence (hero announce, waiting for sidekick UI announce, global clearAll).
    *   Printing UI URLs and VS Code extension hints for remote connections.
    *   Message queuing for operations attempted before full activation.
    *   Serialization/deserialization of messages.
    *   Dispatching incoming UI events (`event`, `error` messages) to the correct `Component` instance handlers.
    *   Managing the overall service status post-connection.
*   **`sidekick.Component` (and subclasses like `Grid`, `Button`)**: User-facing classes representing UI elements. They delegate communication tasks to the `ConnectionService` (via module-level functions in `sidekick.connection`).

**Key Design Philosophy & Connection Model:**

1.  **Connection Priority & Fallback:**
    *   The library first checks if it's running in **Pyodide**. If so, it attempts to use `PyodideCommunicationManager`.
    *   If not in Pyodide, it checks if the user has specified a URL via **`sidekick.set_url()`**. If yes, it attempts to connect only to this URL.
    *   Otherwise, it iterates through the **`DEFAULT_SERVERS`** list in `sidekick.config`. This list typically prioritizes a local WebSocket server (e.g., `ws://localhost:5163` for the VS Code extension) and then falls back to remote cloud-based servers.
2.  **Session IDs for Remote Servers:**
    *   When attempting to connect to a remote server marked as `requires_session_id: True` in its `ServerConfig`, a unique session ID is generated.
    *   This session ID is appended to the WebSocket URL (e.g., `wss://ws.remote/?session=12345678`) and used to construct the UI URL (e.g., `https://ui.remote/12345678`).
3.  **UI URL Prompt:**
    *   If a connection to a remote server (marked with `show_ui_url: True`) is successful, the `ConnectionService` will print the session-specific UI URL to the console, prompting the user to open it in a browser. It will also suggest installing the VS Code extension for a better experience.
    *   For local connections (VS Code extension) or user-set URLs, this prompt is typically suppressed.
4.  **Activation Process (Triggered by First Component):**
    *   The *first* operation requiring communication (e.g., creating the first `sidekick.Grid()`, or an explicit `sidekick.activate_connection()`) triggers the `ConnectionService`'s activation sequence.
    *   `ConnectionService` now invokes `ServerConnector.connect_async()` to obtain a connected `CommunicationManager`.
    *   The `ServerConnector` executes the prioritized connection strategy described above.
    *   Once `ServerConnector` returns a successfully connected `CommunicationManager`, `ConnectionService` proceeds with its post-connection sequence: sending "hero online" `system/announce`, waiting for the Sidekick UI's "online" `system/announce` (from the connected endpoint), sending `global/clearAll`, and then processing any queued messages.
    *   **CPython:** The `activate_connection()` call (and thus the first component creation) **blocks** the calling (main) thread until this entire sequence (including `ServerConnector` finding a connection and `ConnectionService` completing its protocol handshake) completes or fails.
    *   **Pyodide:** The `activate_connection()` call is **non-blocking**. It initiates the asynchronous activation sequence. Messages sent by components during this pending activation are queued by `ConnectionService`.
5.  **Message Sending:**
    *   Component methods (e.g., `grid.set_color()`) call internal `_send_update` or `_send_command` methods, which then use `sidekick.connection.send_message()`. This module-level function delegates to `ConnectionService.send_message_internally()`.
    *   `ConnectionService` queues messages if not fully active or sends them via the established `CommunicationManager`.
6.  **Error Handling:**
    *   If `ServerConnector` fails to connect to any server (after trying all applicable strategies), it raises a `SidekickConnectionError`.
    *   If `sidekick.set_url()` was used and that specific connection fails, `ServerConnector` raises `SidekickConnectionRefusedError`.
    *   `ConnectionService` catches these and other errors (like timeouts waiting for UI announce) during activation. In CPython's blocking `activate_connection()`, these errors are propagated to the user.
    *   Once active, transport errors from `CommunicationManager` are handled by `ConnectionService`, potentially leading to a `FAILED` state and `SidekickDisconnectedError` on subsequent operations.
7.  **No Automatic Reconnection (at `sidekick-py` level):** The library does **not** currently attempt automatic reconnection if a connection is lost after being established.

## 2. Core Implementation Details (`sidekick-py`)

### 2.1. `sidekick.config`
*   Defines the `ServerConfig` dataclass for server connection parameters (`name`, `ws_url`, `ui_url`, `requires_session_id`, `show_ui_url`).
*   Contains the `DEFAULT_SERVERS` list, which `ServerConnector` uses as a fallback.
*   Manages the user-set URL via `get_user_set_url()` and `set_user_url_globally()`.

### 2.2. `sidekick.utils`
*   `generate_unique_id()`: For component instance IDs.
*   `generate_session_id()`: For creating session IDs for remote server connections.

### 2.3. `sidekick.core` Sub-package
This sub-package contains foundational, environment-agnostic abstractions and their concrete CPython/Pyodide implementations:

*   **`core.status.CoreConnectionStatus`**: Enum for low-level transport connection states.
*   **`core.exceptions`**: Defines `CoreConnectionError` and related low-level exceptions.
*   **`core.utils.is_pyodide()`**: Detects the execution environment.
*   **`core.TaskManager` (ABC)**:
    *   `CPythonTaskManager`: Manages an asyncio loop in a background thread.
    *   `PyodideTaskManager`: Uses Pyodide's existing asyncio loop.
    *   A singleton instance is provided by `core.factories.get_task_manager()`.
*   **`core.CommunicationManager` (ABC)**:
    *   `WebSocketCommunicationManager` (CPython): Uses `websockets` library.
    *   `PyodideCommunicationManager` (Pyodide): Uses `js` module and `pyodide.ffi`.
    *   Instances are now created by `core.factories.create_websocket_communication_manager()` or `create_pyodide_communication_manager()`.
*   **`core.factories`**:
    *   `get_task_manager()`: Singleton factory for `TaskManager`.
    *   `create_websocket_communication_manager()`: Creates new `WebSocketCommunicationManager` instances.
    *   `create_pyodide_communication_manager()`: Creates new `PyodideCommunicationManager` instances.

### 2.4. `sidekick.server_connector.ServerConnector`
*   **Responsibilities**: Encapsulates the logic for attempting connections to Sidekick servers.
*   **`connect_async()` method**:
    1.  Checks if running in Pyodide. If so, attempts to use `PyodideCommunicationManager`. Returns on success.
    2.  Checks if a user URL is set via `config.get_user_set_url()`. If so, attempts connection only to this URL using `WebSocketCommunicationManager`. Returns on success or raises `SidekickConnectionRefusedError` on failure.
    3.  Iterates through `config.DEFAULT_SERVERS`. For each server:
        *   Calls `_attempt_single_ws_connection()` with the server's config.
        *   If successful, returns the `ConnectionResult` (containing the CM, UI URL info, etc.).
    4.  If all attempts fail, raises a comprehensive `SidekickConnectionError`.
*   **`_attempt_single_ws_connection()` method**:
    *   Takes a `ServerConfig`.
    *   If `requires_session_id` is true, calls `utils.generate_session_id()` and constructs the final WebSocket URL (e.g., `wss://.../?session=ID`) and UI URL (e.g., `https://.../ID`).
    *   Creates a new `WebSocketCommunicationManager` instance.
    *   Calls `cm.connect_async()`.
    *   Returns a `ConnectionAttemptResult` with success status, the CM, and any UI/hint info.
*   URL helper methods: `_build_ws_url_with_session`, `_build_ui_url_with_session_path`.

### 2.5. `sidekick.connection.ConnectionService`
The `ConnectionService` remains the central orchestrator for post-connection logic but now delegates the initial connection establishment to `ServerConnector`.

*   **Singleton:** Accessed via a module-level `_get_service_instance()`.
*   **State Machine (`_ServiceStatus` Enum):** Tracks detailed lifecycle (IDLE, ACTIVATING_SCHEDULED, CORE_CONNECTED, WAITING_SIDEKICK_ANNOUNCE, ACTIVE, FAILED, etc.).
*   **Async Activation (`_async_activate_and_run_message_queue`):**
    *   Launched as an `asyncio.Task` by the `TaskManager`.
    *   **Step 1: Obtain Connection:** Calls `await self._server_connector.connect_async()`.
        *   If successful, receives a `ConnectionResult` containing a connected `CommunicationManager`, the name of the connected server, and UI URL/hint information.
        *   Stores the received `CommunicationManager` as `self._communication_manager`.
        *   Registers its internal `_handle_core_message`, `_handle_core_status_change`, and `_handle_core_error` callbacks with this `CommunicationManager`.
        *   Sets `self._service_status` to `CORE_CONNECTED`.
        *   If `connection_outcome.show_ui_url_hint` is true, prints the `connection_outcome.ui_url_to_show` and VS Code extension hint to the console.
        *   If `ServerConnector.connect_async()` raises an error, this error is propagated, caught by the outer try-except of `_async_activate_and_run_message_queue`, and the service status is set to `FAILED`.
    *   **Step 2: Post-Connection Protocol:** (This part is largely as before)
        *   Sends "hero online" `system/announce` message via `self._communication_manager`.
        *   Waits for `_sidekick_ui_online_event` (set by `_handle_core_message` on "sidekick online" announce, with timeout).
        *   Sends `global/clearAll` message.
        *   Processes any messages in `_message_queue`.
        *   Sets service status to `ACTIVE` and sets `_clearall_sent_and_queue_processed_event`.
    *   Exceptions during this entire process are caught, set the service to `FAILED`, and are propagated to CPython's blocking `activate_connection_internally()` call.
*   **Blocking `activate_connection_internally()` (CPython):**
    *   Launches `_async_activate_and_run_message_queue`.
    *   Uses `_activation_cv` (a `threading.Condition`) to block the calling thread until the async activation task completes.
*   **Non-blocking `activate_connection_internally()` (Pyodide):**
    *   Launches `_async_activate_and_run_message_queue` and returns.
*   **Message Queuing (`_message_queue`):** Still used for messages sent before `ACTIVE` state.
*   **Message Sending (`send_message_internally()` via module function `send_message`):**
    *   If active, serializes and sends via `self._communication_manager`. Otherwise, queues.
*   **Incoming Message Handling (`_handle_core_message`):** Deserializes and routes messages to component handlers or global handler.
*   **Core Status/Error Handling (`_handle_core_status_change`, `_handle_core_error`):** Updates service status based on feedback from the `CommunicationManager`.
*   **Shutdown (`shutdown_service()` via module `shutdown()`):**
    *   Sends "hero offline" (best effort).
    *   Schedules `self._communication_manager.close_async()` (if CM exists).
    *   Signals `TaskManager.signal_shutdown()`.

### 2.6. `sidekick.Component`
*   `__init__` still calls `sidekick_connection_module.register_message_handler()` and then `_send_command("spawn", ...)`. The `_send_command` (which uses `sidekick_connection_module.send_message()`) will implicitly trigger `ConnectionService.activate_connection_internally()` if it's the first such call.
*   Its core interaction pattern with the `ConnectionService` (via `sidekick_connection_module`) remains largely unchanged from its perspective.

### 2.7. Lifecycle & Synchronization Functions (`sidekick/__init__.py` wrappers)
*   **`sidekick.set_url(url)`:** Now calls `config.set_user_url_globally(url)`. `ServerConnector` will pick this up.
*   **`sidekick.activate_connection()`:** Calls `ConnectionService.activate_connection_internally()`.
*   **`sidekick.run_forever()` (CPython):** Calls `ConnectionService.run_service_forever()`.
*   **`sidekick.run_forever_async()` (Pyodide/Async):** Calls `ConnectionService.run_service_forever_async()`.
*   **`sidekick.shutdown()`:** Calls `ConnectionService.shutdown_service()`.
*   **`sidekick.submit_task(coro)`:** Delegates to `TaskManager.submit_task(coro)`.

## 3. API Design Notes (Recap)

*   **Public API remains mostly synchronous for CPython ease of use.** The complexities of tiered connection attempts and async operations are hidden.
*   `sidekick.set_url()` provides user override for connection.
*   If no user URL and not Pyodide, library tries local VS Code, then remote cloud servers.
*   UI URL and VS Code extension hints are printed for successful remote connections.
*   Pyodide users and advanced CPython users can leverage `run_forever_async` and `submit_task`.

## 4. Logging Strategy

*   Root logger "sidekick". Submodule loggers like "sidekick.connection", "sidekick.server_connector", "sidekick.core.cpython_task_manager".
*   Detailed logging in `ServerConnector` for each connection attempt.
*   Logging in `ConnectionService` for its lifecycle and UI URL printing.
*   Default `NullHandler` for the "sidekick" logger; applications can configure it.

This revised architecture makes the connection process more robust and user-friendly by trying multiple endpoints and guiding users towards the optimal setup (VS Code extension) when using remote fallbacks.