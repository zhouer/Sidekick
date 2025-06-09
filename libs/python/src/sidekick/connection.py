"""Handles the Sidekick service connection and provides module-level API functions.

This module acts as the primary public-facing API for Python scripts to interact with
the Sidekick service. It manages a singleton instance of the `ConnectionService`
(from `sidekick.connection_service`) which orchestrates the actual communication
and lifecycle management.

The public functions exposed here (`set_url`, `activate_connection`, `shutdown`,
`run_forever`, etc.) are wrappers that delegate their operations to the
singleton `ConnectionService` instance. This design pattern simplifies the
user-facing API while centralizing complex connection logic, making the library
easier to use.
"""

import asyncio
import threading
from typing import Dict, Any, Callable, Optional, Coroutine

from . import logger
from .config import set_user_url_globally
from .connection_service import ConnectionService, _ACTIVATION_SYNC_WAIT_TIMEOUT_SECONDS
from .core import TaskManager

# --- Singleton Management for ConnectionService ---
# A lock to ensure thread-safe initialization of the singleton.
_connection_service_singleton_init_lock = threading.Lock()
_connection_service_singleton_instance: Optional[ConnectionService] = None

def _get_service_instance() -> ConnectionService:
    """Internal helper to get or create the singleton ConnectionService instance.

    This function uses a double-checked locking pattern to ensure that only one
    instance of `ConnectionService` exists throughout the lifetime of the
    Sidekick library's use in a Python script.

    Returns:
        ConnectionService: The singleton instance.
    """
    global _connection_service_singleton_instance
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
    It must be called before any components are created or before `activate_connection()`
    or other connection-dependent functions are called.

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
    # This function is part of the public API. It calls the internal config setter.
    set_user_url_globally(url)
    service = _get_service_instance()
    log_msg = f"Sidekick target URL explicitly set to: {url}" if url else "Sidekick target URL cleared."
    logger.info(f"{log_msg} This will be used on next activation (Hero: {service._hero_peer_id}).")


def activate_connection() -> None:
    """Ensures the Sidekick connection activation process is initiated.

    This function is non-blocking. It schedules the asynchronous activation
    sequence if the service is not already active or in the process of activating.
    Component creation will also implicitly call this.

    To synchronously wait for the connection to become fully active, use
    `sidekick.wait_for_connection()`.
    """
    _get_service_instance().activate_connection_internally()

def wait_for_connection(timeout: Optional[float] = None) -> None:
    """Blocks the calling thread until the Sidekick connection is fully active.

    This function is primarily intended for CPython environments. It ensures that
    the connection to the Sidekick UI is established and ready before proceeding
    with operations that require an active connection.

    Args:
        timeout (Optional[float]): The maximum time in seconds to wait.
            If `None`, a default timeout (`_ACTIVATION_SYNC_WAIT_TIMEOUT_SECONDS`)
            will be used.

    Raises:
        RuntimeError: If called from within the Sidekick event loop thread or in Pyodide.
        SidekickConnectionError: If the connection activation process fails.
        SidekickTimeoutError: If the timeout is reached before the connection becomes active.
    """
    effective_timeout = timeout if timeout is not None else _ACTIVATION_SYNC_WAIT_TIMEOUT_SECONDS
    _get_service_instance().wait_for_active_connection_sync(timeout=effective_timeout)


def send_message(message_dict: Dict[str, Any]) -> None:
    """Sends a message dictionary (Sidekick protocol) to the Sidekick UI.

    This is an internal-facing function primarily used by `Component` methods.
    It schedules the message to be sent by the `ConnectionService`.

    Args:
        message_dict (Dict[str, Any]): The Sidekick protocol message to send.
    """
    _get_service_instance().send_message_internally(message_dict)

def register_message_handler(instance_id: str, handler: Callable[[Dict[str, Any]], None]) -> None:
    """Registers a message handler for a specific component instance ID.

    Used internally by `Component` subclasses to route incoming UI events.

    Args:
        instance_id (str): The unique ID of the component instance.
        handler (Callable[[Dict[str, Any]], None]): The function to call when a
            message for this instance_id is received.
    """
    _get_service_instance().register_component_message_handler(instance_id, handler)

def unregister_message_handler(instance_id: str) -> None:
    """Unregisters a message handler for a specific component instance ID.

    Called internally when a component is removed.

    Args:
        instance_id (str): The unique ID of the component instance.
    """
    _get_service_instance().unregister_component_message_handler(instance_id)

def clear_all() -> None:
    """Sends a command to remove all components from the Sidekick UI."""
    _get_service_instance().clear_all_ui_components()

def shutdown(wait: bool = False) -> None:
    """Initiates a clean shutdown of the Sidekick connection service.

    This schedules the shutdown sequence in the event loop.

    Args:
        wait (bool): If `True` (and in a CPython environment), this function
            will block until the service has fully shut down. Defaults to `False`.
    """
    _get_service_instance().shutdown_service(wait=wait)

def run_forever() -> None:
    """Keeps the Python script running to handle UI events (for CPython).

    This function first waits for the Sidekick connection to be established and
    then blocks the main thread, allowing Sidekick's background event loop to
    run until a shutdown is requested (e.g., via `sidekick.shutdown()` in a
    callback or by pressing Ctrl+C).
    """
    _get_service_instance().run_service_forever()

async def run_forever_async() -> None:
    """Keeps the script running asynchronously to handle UI events.

    This function is intended for Pyodide or asyncio-based applications. It
    asynchronously waits for the connection to be established and then for a
    shutdown signal.
    """
    await _get_service_instance().run_service_forever_async()

async def _interval_runner(callback: Callable[[], Any], interval: float) -> None:
    """Internal coroutine that repeatedly calls a callback at a given interval."""
    is_async_callback = asyncio.iscoroutinefunction(callback)
    while True:
        try:
            await asyncio.sleep(interval)
            if is_async_callback:
                await callback()
            else:
                callback()
        except asyncio.CancelledError:
            logger.debug(f"Interval task for callback '{getattr(callback, '__name__', 'unknown')}' was cancelled.")
            break
        except Exception as e:
            logger.exception(f"Error in interval callback '{getattr(callback, '__name__', 'unknown')}': {e}")
            # Decide whether to break the loop or continue
            # For now, we continue, to make it robust against single-frame errors.

def submit_interval(
    callback: Callable[[], Any],
    interval: float
) -> asyncio.Task:
    """Submits a function to be called repeatedly at a specified interval.

    This is a convenient way to create animations or run periodic tasks without
    managing your own `while True` and `time.sleep()` loop. The task is
    automatically managed by Sidekick's event loop and will be cleaned up
    when `sidekick.shutdown()` is called.

    Args:
        callback (Callable[[], Any]): The function or coroutine to be
            executed at each interval. It should take no arguments.
        interval (float): The time in seconds to wait between each call.
            For example, `1/60` for 60 frames per second.

    Returns:
        asyncio.Task: The task object representing the interval execution. You
            can use this to manually cancel the interval if needed.

    Raises:
        ValueError: If `interval` is not a positive number.
        TypeError: If `callback_or_coro` is not a callable function.
    """
    if not callable(callback):
        raise TypeError("The first argument to submit_interval must be a callable function or coroutine.")
    if not isinstance(interval, (int, float)) or interval <= 0:
        raise ValueError("The interval must be a positive number.")

    logger.info(f"Submitting interval task with interval {interval:.4f}s.")
    return submit_task(_interval_runner(callback, interval))

def submit_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Submits a user-defined coroutine to Sidekick's managed event loop.

    This function delegates directly to the `TaskManager`, allowing users to run
    their own asynchronous code concurrently with Sidekick's operations.

    Args:
        coro (Coroutine[Any, Any, Any]): The coroutine to execute.

    Returns:
        asyncio.Task: An `asyncio.Task` object representing the execution of the coroutine.
    """
    task_manager: TaskManager = _get_service_instance()._task_manager
    return task_manager.submit_task(coro)

def register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    """Registers a global handler for *all* incoming messages from the UI.

    This is primarily for debugging or advanced use cases where you need to
    inspect every raw message received from the Sidekick UI.

    Args:
        handler (Optional[Callable[[Dict[str, Any]], None]]): A function that
            accepts a single argument (the message dictionary). Pass `None` to
            remove a previously registered handler.
    """
    _get_service_instance().register_user_global_message_handler(handler)
