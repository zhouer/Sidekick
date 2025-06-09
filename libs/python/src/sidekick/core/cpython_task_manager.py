"""CPython-specific implementation of the TaskManager.

This module provides `CPythonTaskManager`, a concrete implementation of the
`TaskManager` abstract base class. It is designed for standard CPython
environments where asyncio operations need to be managed alongside potentially
synchronous application code.

The `CPythonTaskManager` achieves this by running an asyncio event loop in a
separate daemon thread. This allows the main application thread to remain
synchronous (e.g., blocking on user input or waiting for the service to stop)
while asynchronous tasks (like network communication or timed events) are handled
concurrently by the event loop in its dedicated thread.
"""

import asyncio
import threading
import concurrent.futures
import logging
from typing import Any, Coroutine, Optional, Set

from .task_manager import TaskManager
from .exceptions import CoreLoopNotRunningError, CoreTaskSubmissionError, CoreTaskManagerError

logger = logging.getLogger(__name__)

# --- Constants for Timeouts ---
_LOOP_STARTUP_TIMEOUT_SECONDS = 10.0
_TASK_REF_TIMEOUT_SECONDS = 5.0
_EVENT_CREATION_TIMEOUT_SECONDS = 5.0

class CPythonTaskManager(TaskManager):
    """Manages an asyncio event loop in a separate thread for CPython environments.

    This implementation starts an asyncio event loop in a dedicated daemon thread,
    allowing the main synchronous Python program to schedule and interact with
    asynchronous tasks. It handles thread-safe submission of coroutines and
    graceful shutdown of the loop and its tasks.
    """

    def __init__(self):
        """Initializes the CPythonTaskManager.

        The event loop and its thread are not started automatically. They are
        started on-demand by the first call to a method requiring the loop,
        typically `ensure_loop_running()`.
        """
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        # A re-entrant lock is used to protect access to shared state attributes
        # like _loop, _loop_thread, etc., from both the main thread and the loop thread.
        self._lock = threading.RLock()

        # For synchronizing loop startup between the main thread and the loop thread.
        self._loop_startup_event = threading.Event()
        self._loop_startup_exception: Optional[BaseException] = None

        # For synchronizing loop shutdown.
        self._loop_stopped_event = threading.Event()

        # The asyncio.Event used within the loop thread to signal shutdown.
        self._shutdown_event_async: Optional[asyncio.Event] = None

        # A set to keep track of tasks submitted by this manager for graceful cleanup.
        self._active_tasks: Set[asyncio.Task] = set()

    def _run_loop_thread_target(self) -> None:
        """The target function executed by the dedicated event loop thread.

        This function's lifecycle is the lifecycle of the background thread. It
        initializes a new asyncio event loop for this thread, runs a main coroutine
        that waits for a shutdown signal, and handles the complete cleanup of the
        loop and its associated resources upon exit.
        """
        loop_for_this_thread: Optional[asyncio.AbstractEventLoop] = None
        try:
            # 1. Create and set a new event loop for this thread.
            loop_for_this_thread = asyncio.new_event_loop()
            asyncio.set_event_loop(loop_for_this_thread)

            # 2. Store references and signal readiness.
            with self._lock:
                self._loop = loop_for_this_thread
                # This asyncio.Event must be created on this thread's loop.
                self._shutdown_event_async = asyncio.Event()

            logger.info(f"Event loop thread (TID: {threading.get_ident()}) initialized its event loop: {self._loop}.")
            # Signal to the main thread that the loop is set up and ready.
            self._loop_startup_event.set()

            # 3. Run the main coroutine that keeps the loop alive.
            loop_for_this_thread.run_until_complete(self._main_loop_coro())

        except Exception as e:
            logger.exception(f"Event loop thread (TID: {threading.get_ident()}) encountered a fatal error: {e}")
            # If startup fails, store the exception and signal the event to unblock the main thread.
            if not self._loop_startup_event.is_set():
                self._loop_startup_exception = e
                self._loop_startup_event.set()
        finally:
            # 4. Perform final cleanup when the loop is stopping.
            logger.info(f"Event loop thread (TID: {threading.get_ident()}) is shutting down its loop.")
            if loop_for_this_thread and not loop_for_this_thread.is_closed():
                try:
                    # Cancel tasks and shutdown async generators.
                    loop_for_this_thread.run_until_complete(self._perform_loop_cleanup())
                except Exception as e_cleanup: # pragma: no cover
                    logger.error(f"Error during event loop cleanup: {e_cleanup}")
                finally:
                    # Close the loop itself.
                    loop_for_this_thread.close()
                    logger.info("Event loop closed.")

            # Clear internal references.
            with self._lock:
                if self._loop is loop_for_this_thread:
                    self._loop = None
                    self._shutdown_event_async = None

            # 5. Signal that the thread and loop have fully stopped.
            self._loop_stopped_event.set()
            logger.debug("Loop stopped event has been set.")

    async def _main_loop_coro(self) -> None:
        """The main coroutine that runs in the event loop thread.

        It simply waits for the internal `_shutdown_event_async` to be set. This
        is what keeps the event loop running and processing other tasks until
        `stop_loop()` is called.
        """
        if not self._shutdown_event_async: # pragma: no cover
            logger.error("_main_loop_coro: _shutdown_event_async is None. Cannot wait for shutdown.")
            return
        logger.debug("Event loop's main coroutine started, waiting for shutdown signal.")
        await self._shutdown_event_async.wait()
        logger.debug("Event loop's main coroutine received shutdown signal. Exiting.")

    async def _perform_loop_cleanup(self) -> None:
        """Cancels outstanding tasks and shuts down async generators."""
        logger.debug("Performing event loop cleanup: cancelling tasks and shutting down async generators.")
        # Operate on a copy of the tasks set for safe iteration.
        tasks_to_cancel_locally = list(self._active_tasks)
        self._active_tasks.clear()

        if tasks_to_cancel_locally:
            logger.debug(f"Cancelling {len(tasks_to_cancel_locally)} active tasks managed by this TaskManager.")
            for task in tasks_to_cancel_locally:
                if not task.done():
                    task.cancel()
            try:
                # Wait for all cancellations to be processed.
                await asyncio.gather(*tasks_to_cancel_locally, return_exceptions=True)
                logger.debug("Gathered cancelled tasks.")
            except Exception as e_gather: # pragma: no cover
                logger.error(f"Error during asyncio.gather of cancelled tasks: {e_gather}")
        else:
            logger.debug("No active tasks tracked by this TaskManager to cancel.")

        current_loop = asyncio.get_running_loop()
        if hasattr(current_loop, 'shutdown_asyncgens'):
            try:
                logger.debug("Shutting down asynchronous generators for the loop.")
                await current_loop.shutdown_asyncgens()
            except Exception as e_gens_other: # pragma: no cover
                logger.exception(f"Unexpected error during shutdown_asyncgens: {e_gens_other}")

    def ensure_loop_running(self) -> None:
        """Ensures the asyncio event loop is created and running in its dedicated thread."""
        with self._lock:
            # If already running, do nothing.
            if self.is_loop_running():
                return

            if self._loop_thread and self._loop_thread.is_alive(): # pragma: no cover
                logger.warning("ensure_loop_running: Loop thread is alive but state is inconsistent. Attempting to join old thread.")
                self._loop_thread.join(timeout=0.1)

            # Reset state for a new run.
            self._loop_startup_event.clear()
            self._loop_stopped_event.clear()
            self._loop_startup_exception = None
            self._loop = None
            self._shutdown_event_async = None

            logger.info("ensure_loop_running: Initializing and starting event loop thread.")
            self._loop_thread = threading.Thread(
                target=self._run_loop_thread_target,
                daemon=True,
                name="SidekickCPythonAsyncLoop"
            )
            self._loop_thread.start()

        logger.debug(f"ensure_loop_running: Main thread waiting for _loop_startup_event (timeout: {_LOOP_STARTUP_TIMEOUT_SECONDS}s).")
        if not self._loop_startup_event.wait(timeout=_LOOP_STARTUP_TIMEOUT_SECONDS):
            raise CoreTaskManagerError(f"Timeout ({_LOOP_STARTUP_TIMEOUT_SECONDS}s) waiting for event loop thread to initialize.")

        with self._lock:
            if self._loop_startup_exception:
                raise CoreTaskManagerError("Event loop thread failed during startup.", original_exception=self._loop_startup_exception)
            if not self._loop or not self._loop.is_running(): # pragma: no cover
                 raise CoreTaskManagerError("Loop startup event was set, but the event loop object is not available or not running.")
        logger.info("Event loop thread started and asyncio loop initialized successfully.")

    def is_loop_running(self) -> bool:
        """Checks if the managed asyncio event loop is active and responsive."""
        with self._lock:
            return bool(self._loop_thread and self._loop_thread.is_alive() and self._loop and self._loop.is_running())

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Returns the managed asyncio event loop, ensuring it's running first."""
        self.ensure_loop_running()
        with self._lock:
            if not self._loop: # pragma: no cover
                raise CoreLoopNotRunningError("Event loop is None after ensure_loop_running succeeded.")
            return self._loop

    def _track_task(self, task: asyncio.Task) -> None:
        """Adds a task to the set of active tasks and sets a callback to remove it upon completion."""
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    def _schedule_task_in_loop(self, coro: Coroutine[Any, Any, Any], task_ref_future: concurrent.futures.Future) -> None:
        """Internal helper called via `call_soon_threadsafe` to create a task."""
        if not (loop_for_task := self._loop) or loop_for_task.is_closed(): # pragma: no cover
            task_ref_future.set_exception(CoreLoopNotRunningError("Event loop not available or closed for task creation."))
            return
        try:
            task = loop_for_task.create_task(coro)
            self._track_task(task)
            task_ref_future.set_result(task)
        except Exception as e: # pragma: no cover
            task_ref_future.set_exception(CoreTaskSubmissionError(f"Failed to create task in event loop: {e}", original_exception=e))

    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Submits a coroutine to the managed event loop thread-safely."""
        loop = self.get_loop()
        # If called from the loop thread itself, create the task directly for efficiency.
        try:
            if asyncio.get_running_loop() is loop:
                task = loop.create_task(coro)
                self._track_task(task)
                return task
        except RuntimeError:
            # This is expected if called from another thread.
            pass

        # If called from another thread, schedule task creation thread-safely.
        cf_future_for_task_ref = concurrent.futures.Future()
        loop.call_soon_threadsafe(self._schedule_task_in_loop, coro, cf_future_for_task_ref)
        try:
            # Block and wait for the asyncio.Task object to be created and returned.
            return cf_future_for_task_ref.result(timeout=_TASK_REF_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError as e:
            raise CoreTaskSubmissionError(f"Timeout ({_TASK_REF_TIMEOUT_SECONDS}s) waiting for asyncio.Task reference.", original_exception=e) from e
        except Exception as e_get_ref:
            raise CoreTaskSubmissionError("Failed to obtain asyncio.Task reference.", original_exception=e_get_ref) from e_get_ref

    async def _create_event_coro(self) -> asyncio.Event:
        """A simple coroutine that creates and returns an asyncio.Event."""
        return asyncio.Event()

    def create_event(self) -> asyncio.Event:
        """Creates an `asyncio.Event` object associated with the managed event loop."""
        loop = self.get_loop()
        # If called from within the loop, create it directly.
        try:
            if asyncio.get_running_loop() is loop:
                return asyncio.Event()
        except RuntimeError:
            pass # Not in the loop thread, proceed with thread-safe method.

        # Use run_coroutine_threadsafe to create the event in the loop thread and get it back.
        future = asyncio.run_coroutine_threadsafe(self._create_event_coro(), loop)
        try:
            return future.result(timeout=_EVENT_CREATION_TIMEOUT_SECONDS)
        except concurrent.futures.TimeoutError as e:
            raise CoreTaskManagerError(f"Timeout ({_EVENT_CREATION_TIMEOUT_SECONDS}s) waiting for asyncio.Event creation.", original_exception=e) from e
        except Exception as e_create: # pragma: no cover
            raise CoreTaskManagerError(f"Failed to create asyncio.Event in loop thread: {e_create}", original_exception=e_create) from e_create

    def stop_loop(self) -> None:
        """Requests the managed event loop to begin its shutdown process."""
        with self._lock:
            # Check if there's a running loop and an event to signal.
            if (loop_ref := self._loop) and not loop_ref.is_closed() and \
               (async_shutdown_event_ref := self._shutdown_event_async) and \
               not async_shutdown_event_ref.is_set():
                logger.info("stop_loop: Signaling event loop's async shutdown event.")
                try:
                    # Thread-safely schedule the setting of the event.
                    loop_ref.call_soon_threadsafe(async_shutdown_event_ref.set)
                except RuntimeError as e: # Loop might be closing.
                    logger.warning(f"Could not schedule async shutdown event set (loop closing?): {e}")
            else:
                logger.debug("stop_loop: Loop not active or already signaled for shutdown.")

    def wait_for_stop(self) -> None:
        """Blocks the calling thread until the managed event loop has fully stopped."""
        # Get a reference to the thread outside the lock to avoid holding lock while waiting.
        thread_to_join: Optional[threading.Thread] = self._loop_thread

        if thread_to_join and thread_to_join.is_alive():
            logger.info(f"wait_for_stop: Waiting for event loop thread (TID: {thread_to_join.ident}) to stop.")
            # Wait on the threading.Event that is set at the end of the thread's lifecycle.
            self._loop_stopped_event.wait()
            logger.info("wait_for_stop: Loop stopped event received.")
        else:
            logger.debug("wait_for_stop: No active event loop thread to wait for.")

        # Final cleanup of the thread reference.
        if thread_to_join and not thread_to_join.is_alive():
            with self._lock:
                if self._loop_thread is thread_to_join:
                    self._loop_thread = None
        logger.info("CPythonTaskManager wait_for_stop complete.")
