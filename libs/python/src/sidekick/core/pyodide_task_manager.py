"""Pyodide-specific implementation of the TaskManager.

This TaskManager leverages the existing asyncio event loop provided by the
Pyodide environment (typically running in a Web Worker). It does not create
a new thread or manage the loop's lifecycle directly, as that is handled
by the browser and Pyodide runtime.
"""

import asyncio
import logging
import threading # For RLock, though less critical for thread-safety here
from typing import Awaitable, Any, Coroutine, Optional

# Attempt to import Pyodide-specific types for type checking if possible,
# but make them optional for environments where Pyodide isn't installed (e.g., CPython dev).
try:
    from pyodide.ffi import JsProxy, create_proxy # type: ignore[import-not-found]
    import js # type: ignore[import-not-found]
    _PYODIDE_AVAILABLE = True
except ImportError: # pragma: no cover
    _PYODIDE_AVAILABLE = False
    JsProxy = Any # type: ignore[misc]


from .task_manager import TaskManager
from .exceptions import CoreLoopNotRunningError, CoreTaskSubmissionError
# from .utils import is_pyodide # Not strictly needed by this class itself if factory handles choice

logger = logging.getLogger(__name__)

class PyodideTaskManager(TaskManager):
    """Manages tasks using Pyodide's existing asyncio event loop.

    This implementation assumes that an asyncio event loop is already running
    or will be run by the Pyodide environment (e.g., when Python code is
    executed via `pyodide.runPythonAsync`).
    """

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._shutdown_requested_event: Optional[asyncio.Event] = None
        self._initialization_lock = threading.RLock() # Protects one-time init of loop/event
        self._initialized = False

    def _ensure_initialized(self) -> None:
        """Initializes the loop and shutdown event references if not already done.
        Must set self._loop and self._shutdown_requested_event, or raise CoreLoopNotRunningError.
        """
        with self._initialization_lock:
            if self._initialized:
                return

            current_loop: Optional[asyncio.AbstractEventLoop] = None
            try:
                current_loop = asyncio.get_running_loop()
                logger.debug("PyodideTaskManager: Acquired running loop via get_running_loop().")
            except RuntimeError:
                logger.debug("PyodideTaskManager: No running loop from get_running_loop(), attempting get_event_loop().")
                try:
                    current_loop = asyncio.get_event_loop()
                    logger.debug("PyodideTaskManager: Acquired loop via get_event_loop().")
                except RuntimeError as e_get_loop:
                     err_msg = f"Failed to obtain an event loop in Pyodide environment: {e_get_loop}"
                     logger.error(f"PyodideTaskManager: Could not get or set an event loop: {e_get_loop}")
                     raise CoreLoopNotRunningError(err_msg) from e_get_loop # CRITICAL: Raise if both fail

            if not current_loop: # Should be caught by the exception above # pragma: no cover
                 err_msg_unreachable = "Event loop could not be initialized in Pyodide (current_loop is None)."
                 logger.error(f"PyodideTaskManager: {err_msg_unreachable}")
                 raise CoreLoopNotRunningError(err_msg_unreachable)

            self._loop = current_loop
            # Create event associated with the found/created loop
            self._shutdown_requested_event = asyncio.Event()
            self._initialized = True
            logger.info(f"PyodideTaskManager initialized with event loop: {self._loop}")


    def ensure_loop_running(self) -> None:
        """Ensures loop and event references are initialized. Loop is managed by Pyodide."""
        self._ensure_initialized() # This will raise if loop cannot be obtained
        if not self._loop: # Defensive, should be caught by _ensure_initialized # pragma: no cover
            raise CoreLoopNotRunningError("Pyodide's event loop reference is not available after initialization attempt.")

    def is_loop_running(self) -> bool:
        """Checks if the Pyodide-managed asyncio event loop is currently running."""
        try:
            # ensure_initialized might fail if called very early before any loop is set by Pyodide/browser.
            # In such a case, the loop is not "running" from our perspective yet.
            self._ensure_initialized()
            if self._loop:
                return self._loop.is_running()
        except CoreLoopNotRunningError:
            return False # If loop couldn't be obtained, it's not running for us
        return False # Default if _loop is somehow None after ensure_initialized

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Returns the Pyodide-managed asyncio event loop."""
        self._ensure_initialized() # Will raise CoreLoopNotRunningError if fails
        if not self._loop: # Defensive # pragma: no cover
            raise CoreLoopNotRunningError("Pyodide's event loop reference is not available (should have been caught by _ensure_initialized).")
        return self._loop

    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Submits a coroutine to Pyodide's event loop."""
        self._ensure_initialized() # Ensures self._loop is set or raises
        if not self._loop: # Defensive # pragma: no cover
            raise CoreLoopNotRunningError("Loop not available for task submission (should have been caught by _ensure_initialized).")

        try:
            task = self._loop.create_task(coro)
            return task
        except RuntimeError as e: # pragma: no cover
            logger.exception(f"PyodideTaskManager: Error submitting task: {e}")
            raise CoreTaskSubmissionError(f"Failed to submit task in Pyodide: {e}", original_exception=e) from e

    def submit_and_wait(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Synchronous waiting is not supported in Pyodide's TaskManager.

        Blocking the Pyodide worker thread to wait for an async task would
        freeze all execution in that worker, including the event loop itself.
        Use `await submit_task(coro)` or handle the task asynchronously.

        Raises:
            NotImplementedError: Always, as this pattern is unsuitable for Pyodide.
        """
        err_msg = ("submit_and_wait is not implemented for PyodideTaskManager "
                   "as it would block the single worker thread. "
                   "Use an asynchronous approach (e.g., await task).")
        logger.error(err_msg)
        raise NotImplementedError(err_msg)

    def signal_shutdown(self) -> None:
        """Signals that a shutdown has been requested."""
        try:
            self._ensure_initialized()
        except CoreLoopNotRunningError: # pragma: no cover
            logger.warning("PyodideTaskManager: Cannot signal shutdown, loop not initialized properly.")
            return

        if self._shutdown_requested_event and not self._shutdown_requested_event.is_set():
            logger.info("PyodideTaskManager: Signaling shutdown via asyncio.Event.")
            self._shutdown_requested_event.set()
        else:
            logger.debug("PyodideTaskManager: Shutdown already signaled or event not initialized.")

    def wait_for_shutdown(self) -> None:
        """Synchronous waiting for shutdown is not supported in Pyodide.

        Use `await wait_for_shutdown_async()` instead from an async context.

        Raises:
            NotImplementedError: Always, as this pattern is unsuitable for Pyodide.
        """
        err_msg = ("wait_for_shutdown (synchronous) is not implemented for PyodideTaskManager. "
                   "Use 'await wait_for_shutdown_async()' from an async function.")
        logger.error(err_msg)
        raise NotImplementedError(err_msg)

    async def wait_for_shutdown_async(self) -> None:
        """Asynchronously waits until shutdown is signaled."""
        self._ensure_initialized() # Ensures _shutdown_requested_event is created
        if not self._shutdown_requested_event: # Defensive # pragma: no cover
             raise CoreLoopNotRunningError("Shutdown event not initialized for async wait in Pyodide (should have been caught).")

        logger.info("PyodideTaskManager: Asynchronously waiting for shutdown signal...")
        await self._shutdown_requested_event.wait()
        logger.info("PyodideTaskManager: Shutdown signal received.")

        # Perform a basic cleanup of tasks.
        loop = self._loop # Loop should be valid here
        if loop and not loop.is_closed(): # Check if loop still usable for cleanup # pragma: no cover
            try:
                all_tasks_in_loop = asyncio.all_tasks(loop=loop)
                current_task_in_loop = asyncio.current_task(loop=loop)
                tasks_to_cancel = [
                    t for t in all_tasks_in_loop
                    if t is not current_task_in_loop and not t.done()
                ]
                if tasks_to_cancel:
                    logger.debug(f"PyodideTaskManager: Cancelling {len(tasks_to_cancel)} outstanding tasks on shutdown.")
                    for task in tasks_to_cancel:
                        task.cancel()
                    await asyncio.gather(*tasks_to_cancel, return_exceptions=True)

                if hasattr(loop, 'shutdown_asyncgens'):
                     logger.debug("PyodideTaskManager: Shutting down async generators.")
                     await loop.shutdown_asyncgens()
            except Exception as e_cleanup:
                logger.warning(f"PyodideTaskManager: Error during async cleanup on shutdown: {e_cleanup}")
        logger.info("PyodideTaskManager: Async shutdown sequence complete.")
