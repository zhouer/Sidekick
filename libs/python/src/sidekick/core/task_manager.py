"""Defines the abstract base class for managing asyncio event loops and tasks.

This module provides the `TaskManager` Abstract Base Class (ABC), which outlines
the contract for concrete implementations that manage an asyncio event loop.
Different implementations will exist for standard CPython environments (typically
managing a loop in a separate thread) and for Pyodide environments (using the
browser's event loop provided by Pyodide).

The TaskManager is responsible for:
- Ensuring an event loop is running.
- Submitting asynchronous tasks (coroutines) to the loop.
- Providing mechanisms to wait for tasks to complete (synchronously or asynchronously).
- Managing a shutdown signal for the loop.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Awaitable, Any, Coroutine


class TaskManager(ABC):
    """Abstract Base Class for managing an asyncio event loop and tasks.

    Concrete subclasses will provide environment-specific implementations for
    CPython and Pyodide.
    """

    @abstractmethod
    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Submits a coroutine to be executed on the managed event loop.

        This method is non-blocking. It schedules the coroutine and returns
        an `asyncio.Task` object immediately.

        Args:
            coro: The coroutine to execute.

        Returns:
            asyncio.Task: The task object representing the execution of the coroutine.
                          Callers can use this to await the task's completion or
                          to cancel it.
        """
        pass

    @abstractmethod
    def submit_and_wait(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Submits a coroutine to the loop and blocks until it completes, returning its result.

        This method provides a synchronous way to execute an asynchronous task and
        get its result.

        Warning:
            This method **SHOULD NOT** be used in environments where blocking the
            current thread is problematic (e.g., in the main browser thread or
            a Pyodide worker if it's the only thread handling events).
            Implementations for such environments (like Pyodide) **MUST** raise
            a `NotImplementedError` or a specific `RuntimeError`.

        Args:
            coro: The coroutine to execute.

        Returns:
            Any: The result of the coroutine.

        Raises:
            NotImplementedError: If called in an environment that does not support
                                 synchronous blocking for async tasks (e.g., Pyodide).
            Exception: Any exception raised by the coroutine during its execution
                       will be propagated to the caller of `submit_and_wait`.
        """
        pass

    @abstractmethod
    def wait_for_shutdown(self) -> None:
        """Blocks the calling thread until a shutdown is signaled via `signal_shutdown()`.

        This method is typically used in the main thread of a CPython application
        (like `sidekick.run_forever()`) to keep the application alive while the
        asyncio loop in a background thread processes events.

        Note:
            This method is synchronous and blocking. In an asyncio-native
            application or Pyodide, `wait_for_shutdown_async()` should be used instead.
        """
        pass

    @abstractmethod
    async def wait_for_shutdown_async(self) -> None:
        """Asynchronously waits until a shutdown is signaled via `signal_shutdown()`.

        This method is suitable for use in an `async def` function, particularly
        in Pyodide environments (e.g., `await sidekick.run_forever_async()`) or
        asyncio-native CPython applications.

        It allows other asyncio tasks to run while waiting for the shutdown signal.
        """
        pass

    @abstractmethod
    def signal_shutdown(self) -> None:
        """Signals the TaskManager that a shutdown has been requested.

        This will cause `wait_for_shutdown()` or `wait_for_shutdown_async()`
        to unblock and return. It should also trigger the cleanup and stopping
        of the managed event loop if the TaskManager is responsible for its lifecycle.
        """
        pass

    @abstractmethod
    def ensure_loop_running(self) -> None:
        """Ensures that the managed asyncio event loop is running.

        If the loop is not already running (e.g., in CPython where it might run
        in a separate thread), this method should start it. If the loop is already
        running, this method might do nothing.

        This should be called before submitting any tasks if there's a chance
        the loop isn't active.
        """
        pass

    @abstractmethod
    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Returns the asyncio event loop instance managed by this TaskManager.

        Returns:
            asyncio.AbstractEventLoop: The event loop.

        Raises:
            RuntimeError: If the loop has not been initialized or is not accessible.
        """
        pass

    @abstractmethod
    def is_loop_running(self) -> bool:
        """Checks if the managed asyncio event loop is currently running.

        Returns:
            bool: True if the loop is active, False otherwise.
        """
        pass