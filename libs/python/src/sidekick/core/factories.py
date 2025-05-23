"""Factory functions for creating core infrastructure components.

This module provides centralized functions for instantiating core components
like the TaskManager and specific types of CommunicationManagers.
The TaskManager is provided as a singleton, while CommunicationManagers
are created on demand.
"""

import logging
import threading # For _task_manager_lock
from typing import Optional, Dict, Any

from .task_manager import TaskManager
from .cpython_task_manager import CPythonTaskManager
from .pyodide_task_manager import PyodideTaskManager
from .websocket_communication_manager import WebSocketCommunicationManager
from .pyodide_communication_manager import PyodideCommunicationManager
from .utils import is_pyodide # Import is_pyodide for get_task_manager

logger = logging.getLogger(__name__)

# --- TaskManager Factory (Singleton) ---
_task_manager_instance: Optional[TaskManager] = None
_task_manager_lock = threading.Lock() # Ensures thread-safe singleton creation for TaskManager

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
                    logger.info("Creating PyodideTaskManager singleton instance.")
                    _task_manager_instance = PyodideTaskManager()
                else:
                    logger.info("Creating CPythonTaskManager singleton instance.")
                    _task_manager_instance = CPythonTaskManager()

                if _task_manager_instance is None: # Should not be reached if logic is correct
                     err_msg = "Failed to create a TaskManager instance."
                     logger.critical(err_msg) # More severe if this happens
                     raise RuntimeError(err_msg) # pragma: no cover
    return _task_manager_instance


# --- CommunicationManager Creation Functions ---

def create_websocket_communication_manager(
    url: str,
    task_manager: TaskManager
) -> WebSocketCommunicationManager:
    """Creates and returns a new instance of WebSocketCommunicationManager.

    This manager is responsible for handling WebSocket communication, typically
    used in CPython environments.

    Args:
        url (str): The WebSocket URL to connect to (e.g., "ws://localhost:5163").
        task_manager (TaskManager): The TaskManager instance that this
            CommunicationManager will use for scheduling its asynchronous operations.

    Returns:
        WebSocketCommunicationManager: A new instance configured for the given URL.
    """

    logger.info(f"Creating new WebSocketCommunicationManager instance for URL: {url}")
    return WebSocketCommunicationManager(url=url, task_manager=task_manager)

def create_pyodide_communication_manager(
    task_manager: TaskManager
) -> PyodideCommunicationManager:
    """Creates and returns a new instance of PyodideCommunicationManager.

    This manager handles communication within a Pyodide environment, typically
    by bridging messages between a Web Worker (where Python runs) and the main
    browser thread (where the UI runs).

    Args:
        task_manager (TaskManager): The TaskManager instance (usually PyodideTaskManager)
            that this CommunicationManager will use.

    Returns:
        PyodideCommunicationManager: A new instance.
    """
    logger.info("Creating new PyodideCommunicationManager instance.")
    return PyodideCommunicationManager(task_manager=task_manager)
