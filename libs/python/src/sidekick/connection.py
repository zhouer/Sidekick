"""Handles the Sidekick service connection and provides module-level API functions.

This module acts as the primary interface for Python scripts to interact with
the Sidekick service. It manages a singleton instance of the `ConnectionService`
(from `sidekick.connection_service`) which orchestrates the actual communication
and lifecycle management.

The public functions exposed here (`set_url`, `activate_connection`, `shutdown`,
`run_forever`, etc.) are wrappers that delegate their operations to the
singleton `ConnectionService` instance. This design pattern simplifies the
user-facing API while centralizing complex connection logic.

Key responsibilities of this module (through the ConnectionService):
- Providing functions to explicitly control the Sidekick connection lifecycle.
- Offering a way to send messages to the UI (used internally by components).
- Managing the registration of message handlers for specific component instances.
- Keeping the Python script alive to process UI events via `run_forever` or
  `run_forever_async`.
"""

import asyncio
import threading
from typing import Dict, Any, Callable, Optional, Coroutine

from . import logger # Uses the package-level logger
from .config import set_user_url_globally # For sidekick.set_url()
from .connection_service import ConnectionService, _ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON # Import the class and constants
from .core.utils import is_pyodide # For environment-specific logic in wait_for_connection/run_forever

# --- Singleton Management for ConnectionService ---
_connection_service_singleton_init_lock = threading.Lock()
_connection_service_singleton_instance: Optional[ConnectionService] = None

def _get_service_instance() -> ConnectionService:
    """Internal helper to get or create the singleton ConnectionService instance.

    This ensures that only one instance of `ConnectionService` exists throughout
    the lifetime of the Sidekick library's use in a Python script.

    Returns:
        ConnectionService: The singleton instance.
    """
    global _connection_service_singleton_instance
    # Double-check locking pattern for thread-safe singleton initialization.
    if _connection_service_singleton_instance is None:
        with _connection_service_singleton_init_lock:
            if _connection_service_singleton_instance is None:
                logger.debug("Creating ConnectionService singleton instance.")
                _connection_service_singleton_instance = ConnectionService()
    return _connection_service_singleton_instance


# --- Module-level public API functions that delegate to ConnectionService ---

def set_url(url: Optional[str]) -> None:
    """Sets the target WebSocket URL for the Sidekick connection.

    This URL will be used when the Sidekick connection is next activated.
    It must be called before any components are created or before
    `activate_connection()` / `wait_for_connection()` / `run_forever()`
    is called if you want this URL to take effect for that activation.

    If `None` is passed, Sidekick will revert to using its default server list
    (typically trying a local VS Code extension server first, then cloud fallbacks).

    Args:
        url (Optional[str]): The WebSocket URL (e.g., "ws://custom.server/ws")
            to connect to, or `None` to use default servers.

    Raises:
        ValueError: If the provided `url` is not `None` and is not a valid
                    WebSocket URL string (i.e., does not start with "ws://"
                    or "wss://").
    """
    # `set_user_url_globally` is now in `sidekick.config` but called from here
    # as part of the public API for setting the URL.
    set_user_url_globally(url)
    # Log through the service instance for consistent hero peer ID if already initialized
    _service_instance = _get_service_instance()
    if url:
        logger.info(f"Sidekick target URL explicitly set to: {url}. This will be used on next activation (Hero: {_service_instance._hero_peer_id}).")
    else:
        logger.info(f"Sidekick target URL cleared. Default server list will be used on next activation (Hero: {_service_instance._hero_peer_id}).")


def activate_connection() -> None:
    """Ensures the Sidekick connection activation process is initiated.

    This function is **non-blocking**. It schedules the asynchronous activation
    sequence if the service is not already active or in the process of activating.
    Component creation will also implicitly call this.

    To synchronously wait for the connection to become fully active, especially
    in CPython environments before interacting with components, use
    `sidekick.wait_for_connection()`.

    Example:
        >>> import sidekick
        >>> sidekick.activate_connection() # Schedules activation
        >>> # ... other setup ...
        >>> # If needed, wait for it to complete:
        >>> # sidekick.wait_for_connection()
        >>> my_label = sidekick.Label("Hello") # Component creation also calls activate_connection
    """
    _get_service_instance().activate_connection_internally()

def wait_for_connection(timeout: Optional[float] = None) -> None:
    """Blocks the calling thread until the Sidekick connection is fully active.

    This function is primarily intended for **CPython environments** when you need
    to ensure that the connection to the Sidekick UI is established and ready
    before proceeding with operations that require an active link (e.g.,
    sending commands to components immediately after their creation if not
    relying on `run_forever()` to manage this).

    It first ensures that the activation process is initiated (if not already)
    and then waits for its completion.

    Args:
        timeout (Optional[float]): The maximum time in seconds to wait for the
            connection to become active. If `None`, a default timeout
            (defined in `connection_service.py`, e.g., 180 seconds) will be used.

    Raises:
        RuntimeError: If called from within the Sidekick event loop thread itself
                      (which would cause a deadlock) or if called in a Pyodide
                      environment (where synchronous blocking is not appropriate).
        SidekickConnectionError: If the connection activation process fails for
                                 any reason (e.g., server not reachable, protocol
                                 handshake error).
        SidekickTimeoutError: If the specified `timeout` is reached before the
                              connection becomes active.
        SidekickDisconnectedError: If the service reports a disconnected state
                                   during the wait.
    """
    if is_pyodide():
        raise RuntimeError(
            "sidekick.wait_for_connection() is synchronous and not suitable for Pyodide. "
            "Use asynchronous patterns and `await sidekick.run_forever_async()`."
        )
    # Use the default timeout from connection_service if None is provided
    effective_timeout = timeout if timeout is not None else _ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON
    _get_service_instance().wait_for_active_connection_sync(timeout=effective_timeout)


def send_message(message_dict: Dict[str, Any]) -> None:
    """Sends a message dictionary (Sidekick protocol) to the Sidekick UI.

    This is an internal-facing function primarily used by `Component` methods.
    It ensures the connection activation is initiated (if needed) and queues
    messages if the service is not yet fully active and ready to send.

    Args:
        message_dict (Dict[str, Any]): The Sidekick protocol message to send.

    Raises:
        SidekickDisconnectedError: If the service is in a state (e.g., FAILED,
                                   SHUTTING_DOWN) where messages cannot be
                                   queued or sent.
        TypeError: If the `message_dict` is not JSON serializable (this is
                   generally caught before actual network send by the underlying
                   `json.dumps` call).
    """
    _get_service_instance().send_message_internally(message_dict)

def register_message_handler(instance_id: str, handler: Callable[[Dict[str, Any]], None]) -> None:
    """Registers a message handler for a specific component instance ID.

    This is used internally by `Component` subclasses to route incoming UI events
    (like clicks or submissions) or error messages to the correct Python
    component instance.

    Args:
        instance_id (str): The unique ID of the component instance.
        handler (Callable[[Dict[str, Any]], None]): The function to call when a
            message for this instance_id is received.

    Raises:
        ValueError: If `instance_id` is empty or not a string, or if `ConnectionService`
                    detects a duplicate registration (though `ConnectionService` currently warns).
        TypeError: If `handler` is not a callable function.
    """
    _get_service_instance().register_component_message_handler(instance_id, handler)

def unregister_message_handler(instance_id: str) -> None:
    """Unregisters a message handler for a specific component instance ID.

    Called internally when a component is removed via `component.remove()`.

    Args:
        instance_id (str): The unique ID of the component instance whose
                           handler should be unregistered.
    """
    _get_service_instance().unregister_component_message_handler(instance_id)

def clear_all() -> None:
    """Sends a command to remove all components from the Sidekick UI.

    This effectively resets the Sidekick panel to an empty state (except for the
    implicit root container). The command is scheduled and will be sent when the
    connection is active.
    """
    _get_service_instance().clear_all_ui_components()

def shutdown() -> None:
    """Initiates a clean shutdown of the Sidekick connection service.

    This will attempt to send an "offline" announcement to the UI, close the
    underlying communication channel (e.g., WebSocket), and stop the internal
    event loop manager (`TaskManager`). If `run_forever()` or
    `run_forever_async()` is active, this call will also cause them to terminate.
    """
    _get_service_instance().shutdown_service()

def run_forever() -> None:
    """Keeps the Python script running to handle UI events (for CPython).

    This function is primarily intended for use in standard CPython environments.
    It performs two main actions:
    1.  It first calls `sidekick.wait_for_connection()` internally, which will
        block the main thread until the connection to the Sidekick service is
        fully established and active, or until it fails or times out. If
        connection fails, this function may log an error and exit.
    2.  If the connection is successful, it then blocks the main thread further,
        allowing Sidekick's background event loop (managed by `CPythonTaskManager`)
        to continue processing incoming UI events and submitted asynchronous tasks.

    The script will remain in this state until `sidekick.shutdown()` is called
    (e.g., from a UI event callback or another thread), a `KeyboardInterrupt`
    (Ctrl+C) is received, or an unrecoverable error occurs.

    Example:
        >>> import sidekick
        >>> button = sidekick.Button("Click Me")
        >>> @button.click
        ... def on_button_click(event):
        ...     print("Button was clicked!")
        ...     sidekick.shutdown() # Example of stopping from a callback
        ...
        >>> sidekick.run_forever()
        >>> print("Sidekick has shut down.")

    Raises:
        SidekickConnectionError: If the initial `wait_for_connection()` fails.
        SidekickTimeoutError: If `wait_for_connection()` times out.
    """
    _get_service_instance().run_service_forever()

async def run_forever_async() -> None:
    """Keeps the script running asynchronously to handle UI events.

    This function is intended for Pyodide environments or asyncio-based
    CPython applications.

    It performs two main actions:
    1.  It first ensures the Sidekick connection activation is initiated and then
        asynchronously waits for the service to become fully active. If connection
        fails, an appropriate `SidekickConnectionError` or `SidekickTimeoutError`
        will be raised.
    2.  If the connection is successful, it then `await`s an internal event
        signaling that a shutdown has been requested (via `sidekick.shutdown()`).

    This allows other asyncio tasks in your application to run concurrently
    while Sidekick processes UI events.

    Example (in an async context):
        >>> import sidekick
        >>> import asyncio
        >>>
        >>> async def my_app():
        ...     counter_label = sidekick.Label("Count: 0")
        ...     count = 0
        ...     async def increment():
        ...         nonlocal count
        ...         count += 1
        ...         counter_label.text = f"Count: {count}"
        ...         if count >= 5:
        ...             sidekick.shutdown()
        ...     # Periodically increment counter (example of another async task)
        ...     async def background_counter():
        ...         while True:
        ...             await asyncio.sleep(1)
        ...             await increment() # Assume increment could be async
        ...
        ...     asyncio.create_task(background_counter()) # Start background task
        ...     await sidekick.run_forever_async()
        ...     print("Sidekick async run has finished.")
        >>>
        >>> # To run this: asyncio.run(my_app())
    Raises:
        SidekickConnectionError: If the initial asynchronous connection activation fails.
        SidekickTimeoutError: If waiting for asynchronous connection activation times out.
    """
    await _get_service_instance().run_service_forever_async()

def submit_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Submits a user-defined coroutine to Sidekick's managed event loop.

    This is useful for running custom asynchronous code (e.g., background
    updates, animations, long-running calculations that shouldn't block the
    main Sidekick communication) concurrently with Sidekick components.

    The Sidekick `TaskManager` will be started if it's not already running (this
    is handled internally by the `ConnectionService` which owns the `TaskManager`).

    Args:
        coro (Coroutine[Any, Any, Any]): The coroutine to execute.

    Returns:
        asyncio.Task: An `asyncio.Task` object representing the execution of
            the coroutine. You can use this task object to await its
            completion or to cancel it if needed.

    Raises:
        CoreTaskSubmissionError: If the task cannot be submitted (e.g., if
                                 the TaskManager's loop has issues). This is
                                 a `sidekick.core` exception.
    """
    # _get_service_instance() ensures the ConnectionService (and thus TaskManager) exists.
    # The ConnectionService's _task_manager attribute then calls its submit_task.
    return _get_service_instance()._task_manager.submit_task(coro)

def register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    """Registers a global handler for *all* incoming messages from the UI.

    This is primarily intended for debugging or advanced use cases where you
    need to inspect every raw message received from the Sidekick UI before
    it's processed by specific component handlers.

    Warning:
        The provided handler will receive raw message dictionaries. Modifying
        these dictionaries within the handler could have unintended consequences.
        Errors in the global handler can also impact overall Sidekick functionality.

    Args:
        handler (Optional[Callable[[Dict[str, Any]], None]]): A function that
            accepts a single argument (the message dictionary). Pass `None` to
            remove a previously registered global handler.
    """
    _get_service_instance().register_user_global_message_handler(handler)