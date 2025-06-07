"""Defines the abstract base class for managing asyncio event loops and tasks.

This module provides the `TaskManager` Abstract Base Class (ABC), which outlines
the contract for concrete implementations that manage an asyncio event loop.
Different implementations exist for standard CPython environments (managing a
loop in a separate thread) and for Pyodide environments (using the
browser's event loop provided by Pyodide).

The TaskManager is responsible for:

- Ensuring an event loop is running and providing access to it.
- Submitting asynchronous tasks (coroutines) to be executed on the loop.
- Providing mechanisms to request the loop to stop and to wait for its completion.
- Creating event loop-specific synchronization primitives like asyncio.Event.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Coroutine


class TaskManager(ABC):
    """Abstract Base Class for managing an asyncio event loop and tasks.

    This class defines the interface for an environment-aware asyncio loop
    manager. Concrete subclasses will provide environment-specific implementations
    for CPython and Pyodide. Its primary role is to provide a stable asynchronous
    execution context for other services, like the ConnectionService.
    """

    @abstractmethod
    def ensure_loop_running(self) -> None:
        """Ensures that the managed asyncio event loop is running.

        If the loop is not already running (e.g., in CPython where it might run
        in a separate thread), this method should start it and confirm its readiness.
        If the loop is already running, this method should do nothing.

        Raises:
            CoreTaskManagerError: If the loop cannot be started or confirmed as running.
        """
        pass

    @abstractmethod
    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Returns the asyncio event loop instance managed by this TaskManager.

        This method should typically call `ensure_loop_running()` implicitly to
        guarantee that a running loop is returned.

        Returns:
            asyncio.AbstractEventLoop: The event loop instance.

        Raises:
            CoreLoopNotRunningError: If the loop has not been initialized or is not accessible.
        """
        pass

    @abstractmethod
    def is_loop_running(self) -> bool:
        """Checks if the managed asyncio event loop is currently running.

        Returns:
            bool: True if the loop is active and responsive, False otherwise.
        """
        pass

    @abstractmethod
    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Submits a coroutine to be executed on the managed event loop.

        This method is non-blocking. It schedules the coroutine and should
        immediately return an `asyncio.Task` object. For CPython, this method
        must be thread-safe.

        Args:
            coro (Coroutine[Any, Any, Any]): The coroutine to execute.

        Returns:
            asyncio.Task: The task object representing the execution of the coroutine.
                          Callers can use this to await the task's completion or
                          to cancel it.
        """
        pass

    @abstractmethod
    def create_event(self) -> asyncio.Event:
        """Creates an `asyncio.Event` object associated with the managed event loop.

        This is a factory method to ensure that synchronization primitives are
        created in the correct loop context, which is especially important in
        multi-threaded CPython environments. For CPython, this method must be
        thread-safe.

        Returns:
            asyncio.Event: A new event object tied to the managed loop.
        """
        pass

    @abstractmethod
    def stop_loop(self) -> None:
        """Requests the managed event loop to begin its shutdown process.

        This method is non-blocking and thread-safe. It signals the loop to stop
        processing new tasks and to eventually terminate. For implementations that
        manage the loop's lifecycle (like CPythonTaskManager), this will lead to the
        loop stopping. For implementations that don't own the loop (like
        PyodideTaskManager), this may be a no-op.
        """
        pass

    @abstractmethod
    def wait_for_stop(self) -> None:
        """Blocks the calling thread until the managed event loop has fully stopped.

        This method is synchronous and blocking. It's primarily intended for the
        main thread of a CPython application to wait for the background event
        loop thread to terminate cleanly.

        Note:
            This method may not be applicable or may be a no-op in environments
            where the loop's lifecycle is not managed by the TaskManager (e.g., Pyodide).
        """
        pass
