"""Pyodide-specific implementation of the TaskManager.

This TaskManager leverages the existing asyncio event loop provided by the
Pyodide environment (typically running in a Web Worker). It does not create
a new thread or manage the loop's lifecycle directly, as that is handled
by the browser and Pyodide runtime.

This class acts as a lightweight adapter to the externally-managed event loop,
conforming to the `TaskManager` interface.
"""

import asyncio
import logging
from typing import Any, Coroutine, Optional

from .task_manager import TaskManager
from .exceptions import CoreLoopNotRunningError, CoreTaskSubmissionError

logger = logging.getLogger(__name__)

class PyodideTaskManager(TaskManager):
    """Manages tasks using Pyodide's existing asyncio event loop.

    This implementation assumes that an asyncio event loop is already running
    or will be run by the Pyodide environment (e.g., when Python code is
    executed via `pyodide.runPythonAsync`). It acts as an interface to this
    externally managed loop.
    """

    def __init__(self):
        """Initializes the PyodideTaskManager."""
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # A flag to ensure one-time initialization of the loop reference.
        self._initialized: bool = False

    def _ensure_initialized(self) -> None:
        """Initializes the loop reference if not already done.

        This method attempts to get the current running event loop provided by
        the Pyodide environment. Since this manager does not create the loop,
        this method's primary role is to obtain and store a reference to it.

        Raises:
            CoreLoopNotRunningError: If no event loop can be obtained from the
                                     Pyodide/browser environment.
        """
        # This method is not thread-safe, but it's not expected to be called
        # from multiple threads in a Pyodide (single-threaded) context.
        if self._initialized:
            return

        current_loop: Optional[asyncio.AbstractEventLoop] = None
        try:
            # This is the standard way to get the loop in an async context.
            current_loop = asyncio.get_running_loop()
            logger.debug("PyodideTaskManager: Acquired running loop via get_running_loop().")
        except RuntimeError:
            # Fallback for contexts where get_running_loop might not work but a loop is set.
            logger.warning("PyodideTaskManager: No running loop from get_running_loop(), attempting get_event_loop().")
            try:
                current_loop = asyncio.get_event_loop()
                logger.debug("PyodideTaskManager: Acquired loop via get_event_loop().")
            except RuntimeError as e_get_loop:
                 # If both methods fail, we cannot proceed.
                 err_msg = f"Failed to obtain an event loop in Pyodide environment: {e_get_loop}"
                 logger.error(f"PyodideTaskManager: Could not get or set an event loop: {e_get_loop}")
                 raise CoreLoopNotRunningError(err_msg) from e_get_loop

        if not current_loop: # pragma: no cover
             # This state should ideally be unreachable due to the exceptions above.
             err_msg_unreachable = "Event loop could not be initialized in Pyodide (current_loop is None)."
             logger.error(f"PyodideTaskManager: {err_msg_unreachable}")
             raise CoreLoopNotRunningError(err_msg_unreachable)

        self._loop = current_loop
        self._initialized = True
        logger.info(f"PyodideTaskManager initialized with event loop: {self._loop}")

    def ensure_loop_running(self) -> None:
        """Ensures the loop reference is initialized. The loop itself is managed by Pyodide."""
        self._ensure_initialized()
        if not self._loop: # pragma: no cover
            raise CoreLoopNotRunningError("Pyodide's event loop reference is not available after initialization attempt.")

    def is_loop_running(self) -> bool:
        """Checks if the Pyodide-managed asyncio event loop is currently running."""
        try:
            self._ensure_initialized()
            if self._loop:
                return self._loop.is_running()
        except CoreLoopNotRunningError:
            # If we can't even get a loop, it's not running from our perspective.
            return False
        return False # Default if _loop is somehow None after ensure_initialized

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Returns the Pyodide-managed asyncio event loop."""
        self.ensure_loop_running()
        if not self._loop: # pragma: no cover
            raise CoreLoopNotRunningError("Pyodide's event loop reference is not available.")
        return self._loop

    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Submits a coroutine to Pyodide's event loop.

        Args:
            coro (Coroutine[Any, Any, Any]): The coroutine to execute.

        Returns:
            asyncio.Task: The task object representing the coroutine's execution.

        Raises:
            CoreTaskSubmissionError: If creating the task fails.
        """
        loop = self.get_loop()
        try:
            task = loop.create_task(coro)
            return task
        except RuntimeError as e: # pragma: no cover
            logger.exception(f"PyodideTaskManager: Error submitting task: {e}")
            raise CoreTaskSubmissionError(f"Failed to submit task in Pyodide: {e}", original_exception=e) from e

    def create_event(self) -> asyncio.Event:
        """Creates an `asyncio.Event` object associated with the managed event loop."""
        self.ensure_loop_running()
        # In Pyodide, we are always in the context of the single event loop,
        # so direct instantiation is safe and correct.
        return asyncio.Event()

    def stop_loop(self) -> None:
        """Does nothing in the Pyodide environment.

        The Pyodide/browser event loop lifecycle is not managed by this TaskManager
        and should not be stopped from Python code, as it would terminate the
        entire Web Worker's execution context. This method is a no-op to fulfill
        the `TaskManager` interface contract.
        """
        logger.debug("PyodideTaskManager.stop_loop() called. This is a no-op in the Pyodide environment.")
        pass

    def wait_for_stop(self) -> None:
        """Immediately returns in the Pyodide environment.

        Since the event loop cannot be stopped by this manager, there is no
        'stopped' state to wait for. This method is a no-op to maintain
        interface compatibility.

        For synchronous applications that need to wait, this pattern is not
        suitable for Pyodide. Asynchronous waiting should be used instead.
        """
        logger.debug("PyodideTaskManager.wait_for_stop() called. This is a no-op in the Pyodide environment.")
        pass
