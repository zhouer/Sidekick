# libs/python/src/sidekick/core/cpython_task_manager.py

"""CPython-specific implementation of the TaskManager.

This module provides `CPythonTaskManager`, a concrete implementation of the
`TaskManager` abstract base class. It is designed for standard CPython
environments where asyncio operations need to be managed alongside potentially
synchronous application code.

The `CPythonTaskManager` achieves this by running an asyncio event loop in a
separate daemon thread. This allows the main application thread to remain
synchronous (e.g., blocking on user input or `sidekick.run_forever()`) while
asynchronous tasks (like network communication or timed events) are handled
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
_LOOP_STARTUP_TIMEOUT_SECONDS = 10.0 # Time for loop thread to set its loop and signal readiness.
_TASK_REF_TIMEOUT_SECONDS = 5.0 # Time for submit_task to get asyncio.Task ref from loop thread.
_LOOP_JOIN_TIMEOUT_SECONDS = 5.0 # Time to wait for loop thread to join during shutdown.
_SHUTDOWN_TASK_CLEANUP_TIMEOUT_SECONDS = 3.0 # Time for tasks to finish after cancellation.

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
        started by the first call to a method requiring the loop, typically
        `ensure_loop_running()`.
        """
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock() # Protects shared attributes

        # For loop startup synchronization
        self._loop_startup_event = threading.Event()
        self._loop_startup_exception: Optional[BaseException] = None

        # For shutdown synchronization
        self._shutdown_event_async: Optional[asyncio.Event] = None # Used by the loop's main coroutine
        self._shutdown_event_sync = threading.Event()    # Used by wait_for_shutdown

        self._active_tasks: Set[asyncio.Task] = set() # Track tasks for cleanup

    def _run_loop_thread_target(self) -> None:
        """The target function executed by the dedicated event loop thread.

        Initializes the asyncio event loop for this thread, runs a main coroutine
        that waits for a shutdown signal, and handles cleanup upon exit.
        """
        loop_for_this_thread: Optional[asyncio.AbstractEventLoop] = None
        try:
            loop_for_this_thread = asyncio.new_event_loop()
            asyncio.set_event_loop(loop_for_this_thread)
            # Assign to self._loop only after asyncio.set_event_loop is successful
            # This is read by other threads, so access should be careful (though RLock helps).
            with self._lock:
                self._loop = loop_for_this_thread
                # This asyncio.Event must be created on this thread's loop
                self._shutdown_event_async = asyncio.Event()

            logger.info(
                f"Event loop thread (TID: {threading.get_ident()}) initialized its event loop: {self._loop}."
            )
            # Signal that loop setup (asyncio.set_event_loop) is complete.
            self._loop_startup_event.set()

            # Run the main coroutine that keeps the loop alive until shutdown.
            loop_for_this_thread.run_until_complete(self._main_loop_coro())

        except Exception as e:
            logger.exception(
                f"Event loop thread (TID: {threading.get_ident()}) encountered a fatal error during "
                f"initialization or main execution: {e}"
            )
            # Store exception for ensure_loop_running to pick up if startup failed.
            if not self._loop_startup_event.is_set(): # If startup event wasn't set due to early error
                self._loop_startup_exception = e
                self._loop_startup_event.set() # Unblock ensure_loop_running
        finally:
            logger.info(
                f"Event loop thread (TID: {threading.get_ident()}) is shutting down its loop."
            )
            if loop_for_this_thread and not loop_for_this_thread.is_closed():
                try:
                    # Perform cleanup of tasks and async generators before closing loop.
                    loop_for_this_thread.run_until_complete(self._perform_loop_cleanup(loop_for_this_thread))
                except Exception as e_cleanup: # pragma: no cover
                    logger.error(f"Error during event loop cleanup: {e_cleanup}")
                finally:
                    loop_for_this_thread.close()
                    logger.info("Event loop closed.")
            else: # pragma: no cover
                logger.debug("Event loop was already closed or not initialized in finally block.")

            # Clear self._loop under lock if this thread was the one managing it.
            with self._lock:
                if self._loop is loop_for_this_thread: # Ensure it's the same loop instance
                    self._loop = None
                    self._shutdown_event_async = None # Also clear this
                    logger.debug("Cleared self._loop and self._shutdown_event_async references.")


    async def _main_loop_coro(self) -> None:
        """The main coroutine that runs in the event loop thread.

        It waits for the `_shutdown_event_async` to be set, keeping the
        event loop alive and processing tasks until then.
        """
        if not self._shutdown_event_async: # Should have been set by _run_loop_thread_target
            logger.error("_main_loop_coro: _shutdown_event_async is None. Cannot wait for shutdown.") # pragma: no cover
            return
        logger.debug("Event loop's main coroutine started, waiting for shutdown signal.")
        await self._shutdown_event_async.wait()
        logger.debug("Event loop's main coroutine received shutdown signal. Exiting.")

    async def _perform_loop_cleanup(self, loop_to_clean: asyncio.AbstractEventLoop) -> None:
        """Cancels outstanding tasks and shuts down async generators for the given loop.

        Args:
            loop_to_clean (asyncio.AbstractEventLoop): The event loop to clean up.
        """
        logger.debug("Performing event loop cleanup: cancelling tasks and shutting down async generators.")
        # Cancel all tasks associated with this TaskManager instance
        tasks_to_cancel_locally = list(self._active_tasks) # Operate on a copy
        self._active_tasks.clear() # Clear the set immediately

        if tasks_to_cancel_locally:
            logger.debug(f"Cancelling {len(tasks_to_cancel_locally)} active tasks managed by this TaskManager.")
            for task in tasks_to_cancel_locally:
                if not task.done():
                    task.cancel()
            try:
                await asyncio.gather(*tasks_to_cancel_locally, return_exceptions=True)
                logger.debug("Gathered cancelled tasks.")
            except Exception as e_gather: # pragma: no cover
                logger.error(f"Error during asyncio.gather of cancelled tasks: {e_gather}")
        else:
            logger.debug("No active tasks tracked by this TaskManager to cancel.")

        # Standard asyncio cleanup: Shut down asynchronous generators.
        if hasattr(loop_to_clean, 'shutdown_asyncgens'):
            try:
                logger.debug("Shutting down asynchronous generators for the loop.")
                await loop_to_clean.shutdown_asyncgens()
            except RuntimeError as e_gens_shutdown: # pragma: no cover
                if "cannot schedule new futures after shutdown" in str(e_gens_shutdown).lower() or \
                   "Event loop is closed" in str(e_gens_shutdown).lower():
                    logger.warning(f"Could not run shutdown_asyncgens, loop may be closing/closed: {e_gens_shutdown}")
                else:
                    logger.exception(f"RuntimeError during shutdown_asyncgens: {e_gens_shutdown}")
            except Exception as e_gens_other: # pragma: no cover
                logger.exception(f"Unexpected error during shutdown_asyncgens: {e_gens_other}")


    def ensure_loop_running(self) -> None:
        """Ensures the asyncio event loop is created and running in its dedicated thread.

        If the loop is already running, this method does nothing. Otherwise, it
        starts the loop thread and waits for it to confirm successful initialization.

        Raises:
            CoreTaskManagerError: If the loop thread fails to start or initialize
                                  the event loop within the timeout.
        """
        with self._lock: # Protect the entire startup sequence
            # Check if loop is already running and initialized correctly
            if self._loop_thread and self._loop_thread.is_alive() and \
               self._loop_startup_event.is_set() and not self._loop_startup_exception:
                # Additionally, ensure self._loop is set and running, as loop_startup_event
                # only signals loop_thread has finished its set_event_loop part.
                if self._loop and self._loop.is_running():
                    logger.debug("ensure_loop_running: Loop already running and confirmed.")
                    return
                else: # pragma: no cover
                    # This state might indicate a problem if startup_event is set but loop isn't.
                    # Forcing re-initialization might be safer.
                    logger.warning(
                        "ensure_loop_running: Loop startup event was set, but loop object or its "
                        "running state is invalid. Attempting re-initialization."
                    )
                    # Fall through to re-initialize

            if self._loop_thread and self._loop_thread.is_alive(): # pragma: no cover
                # If thread is alive but previous checks failed, it's an inconsistent state.
                logger.warning(
                    "ensure_loop_running: Loop thread is alive but startup confirmation is "
                    "incomplete or indicates failure. Attempting to join old thread before restart."
                )
                self._loop_thread.join(timeout=0.1) # Best effort join
                if self._loop_thread.is_alive():
                    logger.error("Old loop thread still alive. This could lead to issues.")
                self._loop_thread = None # Discard old thread ref

            # Reset startup state for a new attempt
            self._loop_startup_event.clear()
            self._loop_startup_exception = None
            self._loop = None # Clear any old loop reference
            self._shutdown_event_async = None # This will be created by the loop thread

            logger.info("ensure_loop_running: Initializing and starting event loop thread.")
            self._loop_thread = threading.Thread(
                target=self._run_loop_thread_target,
                daemon=True,
                name="SidekickCPythonAsyncLoop"
            )
            self._loop_thread.start()
            # End of critical section protected by self._lock for thread creation.
            # Now, wait for the event outside the lock to prevent deadlock if the
            # loop thread needs to acquire this lock (though it shouldn't here).

        # Wait for the loop thread to signal that it has initialized the loop.
        logger.debug(
            "ensure_loop_running: Main thread waiting for _loop_startup_event "
            f"(timeout: {_LOOP_STARTUP_TIMEOUT_SECONDS}s)."
        )
        if not self._loop_startup_event.wait(timeout=_LOOP_STARTUP_TIMEOUT_SECONDS):
            err_msg = (
                f"Timeout ({_LOOP_STARTUP_TIMEOUT_SECONDS}s) waiting for event loop thread to initialize. "
                "Loop startup failed."
            )
            logger.error(err_msg)
            # Attempt to join the thread if it's stuck
            if self._loop_thread and self._loop_thread.is_alive(): # pragma: no cover
                self._loop_thread.join(timeout=0.5)
            raise CoreTaskManagerError(err_msg)

        # Check if an exception occurred during loop thread startup
        with self._lock: # Re-acquire lock to safely access _loop_startup_exception
            if self._loop_startup_exception:
                err_msg = "Event loop thread failed during startup."
                logger.error(f"{err_msg} Exception: {self._loop_startup_exception}")
                raise CoreTaskManagerError(err_msg, original_exception=self._loop_startup_exception)

            # Final check: ensure self._loop is set and running after startup_event is set.
            if not self._loop or not self._loop.is_running(): # pragma: no cover
                 # This implies _run_loop_thread_target set startup_event but loop died or wasn't set properly.
                 err_msg_final_check = (
                    "Loop startup event was set, but the event loop object is "
                    "not available or not running. Startup deemed failed."
                )
                 logger.error(err_msg_final_check)
                 raise CoreTaskManagerError(err_msg_final_check)

        logger.info("Event loop thread started and asyncio loop initialized successfully.")

    def is_loop_running(self) -> bool:
        """Checks if the managed asyncio event loop is active and responsive.

        Returns:
            bool: True if the loop thread is alive, the loop object exists,
                  and the loop reports itself as running. False otherwise.
        """
        with self._lock:
            return bool(
                self._loop_thread and
                self._loop_thread.is_alive() and
                self._loop and
                self._loop.is_running() and
                self._loop_startup_event.is_set() and # Ensures _run_loop_thread_target reached initialization
                not self._loop_startup_exception   # Ensures no error during that initialization
            )

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Returns the managed asyncio event loop, ensuring it's running first.

        Returns:
            asyncio.AbstractEventLoop: The event loop instance.

        Raises:
            CoreLoopNotRunningError: If the loop is not running or fails to start.
        """
        self.ensure_loop_running() # This will raise if loop cannot be started/confirmed.
        with self._lock: # Acquire lock to safely return self._loop
            if not self._loop: # Should be caught by ensure_loop_running
                raise CoreLoopNotRunningError("Event loop is None after ensure_loop_running succeeded.") # pragma: no cover
            return self._loop

    def _track_task(self, task: asyncio.Task) -> None:
        """Adds a task to the set of active tasks and sets a callback to remove it upon completion.

        Args:
            task (asyncio.Task): The task to track.
        """
        self._active_tasks.add(task)
        task.add_done_callback(self._active_tasks.discard)

    def _schedule_task_in_loop(
        self,
        coro: Coroutine[Any, Any, Any],
        task_ref_future: concurrent.futures.Future
    ) -> None:
        """Internal: Schedules task creation in the loop and resolves a future with the Task ref.

        This method is called via `loop.call_soon_threadsafe`.

        Args:
            coro (Coroutine[Any, Any, Any]): The coroutine to schedule.
            task_ref_future (concurrent.futures.Future): The future to resolve with the asyncio.Task.
        """
        loop_for_task: Optional[asyncio.AbstractEventLoop] = None
        # Get loop under lock, but don't hold lock during create_task.
        with self._lock:
            loop_for_task = self._loop

        if not loop_for_task or loop_for_task.is_closed(): # pragma: no cover
            task_ref_future.set_exception(
                CoreLoopNotRunningError("Event loop not available or closed for task creation.")
            )
            return
        try:
            task = loop_for_task.create_task(coro)
            self._track_task(task) # Track for cleanup
            task_ref_future.set_result(task)
        except Exception as e: # pragma: no cover
            task_ref_future.set_exception(
                CoreTaskSubmissionError(f"Failed to create task in event loop: {e}", original_exception=e)
            )

    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Submits a coroutine to the managed event loop.

        If called from the loop thread, creates the task directly. Otherwise,
        schedules creation thread-safely and waits for the `asyncio.Task` reference.

        Args:
            coro (Coroutine[Any, Any, Any]): The coroutine to execute.

        Returns:
            asyncio.Task: The task object representing the coroutine's execution.

        Raises:
            CoreLoopNotRunningError: If the event loop is not running.
            CoreTaskSubmissionError: If task submission fails (e.g., timeout
                                     getting task reference from loop thread).
        """
        loop = self.get_loop() # Ensures loop is running and gets it.
        coro_name = getattr(coro, '__name__', 'unknown_coro')

        # Check if called from the event loop thread itself
        try:
            if asyncio.get_running_loop() is loop:
                logger.debug(f"submit_task: Called from event loop thread. Creating task '{coro_name}' directly.")
                task = loop.create_task(coro)
                self._track_task(task)
                return task
        except RuntimeError: # No running loop in current thread, so it's not the loop thread
            pass

        # Called from a different thread
        logger.debug(f"submit_task: Submitting task '{coro_name}' to event loop thread.")
        cf_future_for_task_ref = concurrent.futures.Future()
        loop.call_soon_threadsafe(
            self._schedule_task_in_loop,
            coro,
            cf_future_for_task_ref
        )
        try:
            # Wait for the asyncio.Task object reference from the loop thread
            task_ref: asyncio.Task = cf_future_for_task_ref.result(timeout=_TASK_REF_TIMEOUT_SECONDS)
            logger.debug(f"submit_task: Successfully obtained asyncio.Task ref for '{coro_name}'.")
            return task_ref
        except concurrent.futures.TimeoutError:
            err_msg = (
                f"Timeout ({_TASK_REF_TIMEOUT_SECONDS}s) waiting for asyncio.Task reference from "
                f"event loop thread for coroutine '{coro_name}'. The event loop might be busy or stuck."
            )
            logger.error(err_msg)
            raise CoreTaskSubmissionError(err_msg)
        except Exception as e_get_ref: # Exception set by _schedule_task_in_loop
            logger.error(f"Error obtaining asyncio.Task ref for '{coro_name}': {e_get_ref}")
            if isinstance(e_get_ref, (CoreLoopNotRunningError, CoreTaskSubmissionError)):
                raise e_get_ref
            raise CoreTaskSubmissionError(
                f"Failed to obtain asyncio.Task reference for '{coro_name}': {e_get_ref}",
                original_exception=e_get_ref
            )

    def submit_and_wait(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Submits a coroutine and blocks current thread until it completes.

        Args:
            coro (Coroutine[Any, Any, Any]): The coroutine to execute.

        Returns:
            Any: The result of the coroutine.

        Raises:
            RuntimeError: If called from the TaskManager's own event loop thread.
            CoreLoopNotRunningError: If the event loop is not running.
            Exception: Any exception raised by the coroutine.
        """
        loop = self.get_loop() # Ensures loop is running
        coro_name = getattr(coro, '__name__', 'unknown_coro')

        try:
            if asyncio.get_running_loop() is loop:
                # This is the critical check. If true, we are in the loop thread.
                raise RuntimeError(
                    "submit_and_wait cannot be called from the TaskManager's event loop thread."
                )
        except RuntimeError as e:
            # We need to distinguish between the RuntimeError we just raised
            # and the one raised by asyncio.get_running_loop() if no loop is running
            # (which means we are in a non-loop, non-asyncio-managed thread).
            if "submit_and_wait cannot be called from" in str(e):
                logger.error(f"submit_and_wait for '{coro_name}' aborted: called from loop thread.")
                raise e # Re-raise the specific RuntimeError we threw.
            elif "no running event loop" in str(e).lower():
                # This is the expected case if called from a non-loop, non-asyncio thread.
                # It's safe to proceed with run_coroutine_threadsafe.
                logger.debug(f"submit_and_wait: Called for '{coro_name}' from a non-loop thread, as expected.")
            else: # pragma: no cover
                # Any other RuntimeError from get_running_loop is unexpected here.
                logger.error(f"submit_and_wait: Unexpected RuntimeError during running loop check for '{coro_name}': {e}")
                raise CoreTaskManagerError(f"Unexpected error checking running loop for '{coro_name}'", original_exception=e) from e


        # If we reached here, it means we are in a non-loop thread.
        logger.debug(f"submit_and_wait: Submitting '{coro_name}' to loop thread and waiting for completion.")
        cf_future = asyncio.run_coroutine_threadsafe(coro, loop)
        # Add task to tracking if possible - run_coroutine_threadsafe doesn't directly return asyncio.Task
        # For robust tracking with submit_and_wait, one might need to wrap `coro`
        # to get its task and add it to _active_tasks from within the loop.
        # For simplicity, submit_and_wait doesn't directly track via _active_tasks here.
        # The _perform_loop_cleanup will still attempt to cancel tasks it finds via asyncio.all_tasks.

        try:
            # Poll with timeout for KeyboardInterrupt responsiveness
            while not cf_future.done():
                try:
                    return cf_future.result(timeout=0.1) # Short poll
                except concurrent.futures.TimeoutError:
                    pass # Continue polling
            return cf_future.result() # Get final result or exception
        except KeyboardInterrupt: # pragma: no cover
            logger.info(f"submit_and_wait: KeyboardInterrupt for '{coro_name}'. Signaling shutdown.")
            self.signal_shutdown()
            if not cf_future.done(): cf_future.cancel()
            raise
        except concurrent.futures.CancelledError: # pragma: no cover
            logger.info(f"submit_and_wait: Coroutine '{coro_name}' future was cancelled.")
            raise asyncio.CancelledError(f"Coroutine '{coro_name}' was cancelled.") from None
        except Exception as e_coro: # Exception from the coroutine itself
            logger.debug(f"submit_and_wait: Coroutine '{coro_name}' raised: {type(e_coro).__name__}")
            raise


    def signal_shutdown(self) -> None:
        """Signals the event loop and synchronous waiters to shut down."""
        with self._lock:
            loop_ref = self._loop
            async_shutdown_event_ref = self._shutdown_event_async

            if loop_ref and not loop_ref.is_closed() and \
               async_shutdown_event_ref and not async_shutdown_event_ref.is_set():
                logger.info("signal_shutdown: Signaling event loop's async shutdown event.")
                try:
                    loop_ref.call_soon_threadsafe(async_shutdown_event_ref.set)
                except RuntimeError as e_set_event: # pragma: no cover
                    logger.warning(f"Could not schedule async shutdown event set (loop closing?): {e_set_event}")
            elif not (loop_ref and not loop_ref.is_closed()): # pragma: no cover
                 logger.debug("signal_shutdown: Loop not active for signaling async shutdown event.")

            if not self._shutdown_event_sync.is_set():
                logger.info("signal_shutdown: Signaling synchronous shutdown event.")
                self._shutdown_event_sync.set()
            else: # pragma: no cover
                logger.debug("signal_shutdown: Synchronous shutdown event already set.")


    def wait_for_shutdown(self) -> None:
        """Blocks current thread until shutdown is completed and loop thread exits."""
        logger.info("wait_for_shutdown: Blocking until shutdown signal received.")
        self._shutdown_event_sync.wait() # Wait for signal_shutdown to set this
        logger.info("wait_for_shutdown: Shutdown signal received. Waiting for loop thread to join.")

        thread_to_join: Optional[threading.Thread] = None
        with self._lock: # Get thread reference safely
            thread_to_join = self._loop_thread

        if thread_to_join and thread_to_join.is_alive():
            thread_to_join.join(timeout=_LOOP_JOIN_TIMEOUT_SECONDS)
            if thread_to_join.is_alive(): # pragma: no cover
                logger.warning(
                    f"Event loop thread did not join within {_LOOP_JOIN_TIMEOUT_SECONDS}s. It might be stuck."
                )
            else:
                logger.info("Event loop thread joined successfully.")
        elif thread_to_join: # pragma: no cover
             logger.debug("Event loop thread was already finished.")
        else: # pragma: no cover
             logger.debug("No event loop thread reference to join (was it started?).")

        # Final cleanup of state associated with the now-stopped thread/loop.
        with self._lock:
            self._loop_thread = None
            # self._loop should be None by now (cleared in _run_loop_thread_target's finally)
            # but clear it again just in case, if loop thread died abnormally.
            if self._loop and not self._loop.is_closed(): # pragma: no cover
                 logger.warning("Loop object still exists and not closed after thread join. Attempting force close.")
                 try: self._loop.close()
                 except Exception: pass
            self._loop = None
            self._shutdown_event_async = None
            self._loop_startup_event.clear() # Reset for any potential (unlikely for singleton) next use
            self._loop_startup_exception = None
            self._active_tasks.clear() # Should be empty if _perform_loop_cleanup worked.

        logger.info("CPythonTaskManager wait_for_shutdown complete.")

    async def wait_for_shutdown_async(self) -> None:
        """Asynchronously waits for the shutdown signal.

        Raises:
            CoreLoopNotRunningError: If the async shutdown event is not initialized.
        """
        loop = self.get_loop() # Ensures loop and _shutdown_event_async are initialized
        if not self._shutdown_event_async: # Should be set by get_loop()->ensure_loop_running()->_run_loop_thread_target
            raise CoreLoopNotRunningError("Async shutdown event not initialized for async wait.") # pragma: no cover

        logger.info("wait_for_shutdown_async: Waiting for async shutdown signal.")
        await self._shutdown_event_async.wait()
        logger.info("wait_for_shutdown_async: Async shutdown signal received.")
        # Note: This only waits for the signal. Actual loop thread cleanup
        # (joining, closing loop) is managed by synchronous `wait_for_shutdown`
        # or the loop thread's `finally` block.
        # If a fully async application uses this, it might need to ensure
        # the TaskManager instance itself is 'closed' or resources released
        # if it started the loop and thread.

