"""Factory functions for creating core infrastructure components.

This module provides centralized functions for instantiating core components
like the TaskManager and CommunicationManager. These factories determine the
appropriate concrete implementation based on the execution environment
(e.g., CPython or Pyodide).
"""

import logging
import threading
from typing import Optional, Dict, Any

from .task_manager import TaskManager
from .cpython_task_manager import CPythonTaskManager
from .pyodide_task_manager import PyodideTaskManager
from .communication_manager import CommunicationManager
from .websocket_communication_manager import WebSocketCommunicationManager, _DEFAULT_PING_INTERVAL_SECONDS, _DEFAULT_PING_TIMEOUT_SECONDS
from .pyodide_communication_manager import PyodideCommunicationManager
from .utils import is_pyodide
from .status import CoreConnectionStatus # Though not directly used, good to have related imports visible

logger = logging.getLogger(__name__)

# --- TaskManager Factory ---
_task_manager_instance: Optional[TaskManager] = None
_task_manager_lock = threading.Lock() # Ensures thread-safe singleton creation

def get_task_manager() -> TaskManager:
    """Gets the singleton instance of the appropriate TaskManager.

    This function determines whether the code is running in a CPython or
    Pyodide environment and returns a corresponding TaskManager implementation.
    The TaskManager instance is created only once (singleton pattern).

    Subsequent calls to this function will return the same instance.

    Returns:
        TaskManager: The singleton TaskManager instance for the current environment.

    Raises:
        RuntimeError: If a TaskManager instance cannot be created for some unexpected reason.
    """
    global _task_manager_instance
    if _task_manager_instance is None:
        with _task_manager_lock:
            if _task_manager_instance is None:
                if is_pyodide():
                    logger.info("Creating PyodideTaskManager instance.")
                    _task_manager_instance = PyodideTaskManager()
                else:
                    logger.info("Creating CPythonTaskManager instance.")
                    _task_manager_instance = CPythonTaskManager()

                if _task_manager_instance is None: # Should not happen
                     err_msg = "Failed to create a TaskManager instance."
                     logger.error(err_msg)
                     raise RuntimeError(err_msg) # pragma: no cover
    return _task_manager_instance


# --- CommunicationManager Factory ---
_communication_manager_instance: Optional[CommunicationManager] = None
_communication_manager_lock = threading.Lock() # Ensures thread-safe singleton creation

# Default WebSocket URL, can be overridden by ConnectionService later via sidekick.set_url
_DEFAULT_WEBSOCKET_URL = "ws://localhost:5163"


def get_communication_manager(
    ws_url: Optional[str] = None,
    ws_config: Optional[Dict[str, Any]] = None
) -> CommunicationManager:
    """Gets the singleton instance of the appropriate CommunicationManager.

    This function determines the execution environment (CPython or Pyodide)
    and returns a corresponding CommunicationManager implementation.
    The instance is created only once (singleton pattern).

    For CPython (WebSocket based):
        - It requires a `TaskManager` instance (obtained internally).
        - It uses the provided `ws_url` or a default if None.
        - `ws_config` can provide additional parameters like `ping_interval`, `ping_timeout`.

    For Pyodide:
        - It requires a `TaskManager` instance.
        - `ws_url` and `ws_config` are ignored.

    Args:
        ws_url (Optional[str]): The WebSocket URL to use if running in a CPython
            environment. If None, a default URL ("ws://localhost:5163") is used.
            This argument is ignored in Pyodide environments.
        ws_config (Optional[Dict[str, Any]]): A dictionary for WebSocket specific
            configurations like 'ping_interval' and 'ping_timeout'.
            Ignored in Pyodide.

    Returns:
        CommunicationManager: The singleton CommunicationManager instance.

    Raises:
        RuntimeError: If a CommunicationManager instance cannot be created.
    """
    global _communication_manager_instance
    if _communication_manager_instance is None:
        with _communication_manager_lock:
            if _communication_manager_instance is None:
                task_manager = get_task_manager() # Get the singleton TaskManager

                if is_pyodide():
                    logger.info("Creating PyodideCommunicationManager instance.")
                    _communication_manager_instance = PyodideCommunicationManager(task_manager)
                else:
                    effective_url = ws_url if ws_url is not None else _DEFAULT_WEBSOCKET_URL
                    config = ws_config if ws_config is not None else {}
                    ping_interval = config.get('ping_interval', _DEFAULT_PING_INTERVAL_SECONDS)
                    ping_timeout = config.get('ping_timeout', _DEFAULT_PING_TIMEOUT_SECONDS)

                    logger.info(f"Creating WebSocketCommunicationManager instance for URL: {effective_url}")
                    _communication_manager_instance = WebSocketCommunicationManager(
                        url=effective_url,
                        task_manager=task_manager,
                        ping_interval=ping_interval,
                        ping_timeout=ping_timeout
                    )

                if _communication_manager_instance is None: # Should not happen
                    err_msg = "Failed to create a CommunicationManager instance."
                    logger.error(err_msg)
                    raise RuntimeError(err_msg) # pragma: no cover
    return _communication_manager_instance