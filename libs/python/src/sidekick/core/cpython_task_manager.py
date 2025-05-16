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

Key features and responsibilities:
-   Manages the lifecycle of an asyncio event loop running in a background thread.
-   Provides thread-safe methods to submit coroutines to this loop from any thread
    (`submit_task`, `submit_and_wait`).
-   Handles graceful shutdown of the event loop and its tasks when signaled.
-   Offers mechanisms for a synchronous thread (typically the main thread) to
    block until the TaskManager is shut down (`wait_for_shutdown`).
"""

import asyncio
import threading
import concurrent.futures # For Future objects used in cross-thread communication
import logging
from typing import Awaitable, Any, Coroutine, Optional

from .task_manager import TaskManager
from .exceptions import CoreLoopNotRunningError, CoreTaskSubmissionError, CoreTaskManagerError

logger = logging.getLogger(__name__)

# --- Constants for Timeouts ---
_LOOP_START_TIMEOUT = 5.0  # Max seconds to wait for the loop thread to confirm startup.
_LOOP_JOIN_TIMEOUT = 5.0   # Max seconds to wait for the loop thread to join during shutdown.
_GET_TASK_REF_TIMEOUT = 2.0 # Max seconds for submit_task to wait for the asyncio.Task reference.
_FUTURE_WAIT_POLL_INTERVAL = 0.05 # Short polling interval in submit_and_wait for KeyboardInterrupt responsiveness.
_TASK_CANCELLATION_GATHER_TIMEOUT = 3.0 # Max time for tasks to finish after being cancelled during shutdown.
_ASYNCGEN_SHUTDOWN_TIMEOUT = 2.0    # Max time for asynchronous generators to shut down.


class CPythonTaskManager(TaskManager):
    """Manages an asyncio event loop in a separate thread for CPython environments.

    This implementation starts an asyncio event loop in a dedicated daemon thread,
    allowing the main synchronous Python program to schedule and interact with
    asynchronous tasks. It handles thread-safe submission of coroutines and
    graceful shutdown of the loop and its tasks.
    """

    def __init__(self):
        """Initializes the CPythonTaskManager.

        The event loop and its thread are not started automatically upon
        initialization. They are started by the first call to a method
        that requires the loop, such as `ensure_loop_running()` or
        `submit_task()`.
        """
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        # Reentrant lock to protect access to shared attributes like _loop,
        # _loop_thread, and during startup/shutdown sequences.
        self._lock = threading.RLock()

        # asyncio.Event, lives in self._loop. Used by the loop thread to wait for a shutdown signal.
        self._shutdown_requested_event_for_loop: Optional[asyncio.Event] = None
        # threading.Event, used by a synchronous thread (e.g., main thread) to block
        # in wait_for_shutdown() until shutdown is signaled.
        self._sync_shutdown_wait_event = threading.Event()

        # Flag to indicate if ensure_loop_running() has been called at least once
        # to attempt loop creation and thread start.
        self._loop_creation_attempted = False
        # asyncio.Event, lives in self._loop. Set by the loop thread once it has
        # successfully started and set its event loop. ensure_loop_running() waits on this.
        self._loop_is_actually_running_event: Optional[asyncio.Event] = None

    def _ensure_and_get_loop(self) -> asyncio.AbstractEventLoop:
        """Ensures the loop is initialized and running, then returns it.

        Internal helper. `ensure_loop_running()` must be called first by public methods.

        Raises:
            CoreLoopNotRunningError: If the loop is not running or not initialized
                                     after `ensure_loop_running` should have set it up.
        """
        # This method assumes ensure_loop_running() has done its job.
        # The check here is a safeguard.
        if not self._loop or not self.is_loop_running(): # pragma: no cover
            logger.error("_ensure_and_get_loop: Loop is unexpectedly not running or not initialized.")
            raise CoreLoopNotRunningError("Event loop is not available or not running.")
        return self._loop

    def _run_loop_in_thread(self) -> None:
        """The target function executed by the dedicated event loop thread.

        This method sets up the asyncio event loop for the current thread,
        signals that it's running, and then runs the loop until a shutdown
        is requested. It also handles graceful cleanup of tasks and async
        resources before closing the loop.
        """
        # Capture these from self at the start, as self attributes might be changed
        # by other threads (e.g., during shutdown).
        loop_object_for_this_thread = self._loop
        shutdown_event_for_this_loop = self._shutdown_requested_event_for_loop
        running_event_for_this_loop = self._loop_is_actually_running_event

        if not loop_object_for_this_thread or \
           not shutdown_event_for_this_loop or \
           not running_event_for_this_loop:
            # This indicates a programming error in how the thread was started.
            logger.error("Loop thread started with uninitialized loop or critical asyncio events.") # pragma: no cover
            return

        current_thread_id = threading.get_ident()
        logger.info(f"Event loop thread (TID: {current_thread_id}) starting.")
        asyncio.set_event_loop(loop_object_for_this_thread)

        # Define a synchronous function to set the asyncio.Event.
        # This is scheduled with call_soon to run on the loop once it starts.
        def _sync_set_running_event_on_loop():
            if running_event_for_this_loop: # Check if event still exists
                logger.debug(
                    f"Event loop thread (TID: {current_thread_id}) is now setting "
                    "_loop_is_actually_running_event via call_soon."
                )
                running_event_for_this_loop.set()

        loop_object_for_this_thread.call_soon(_sync_set_running_event_on_loop)

        try:
            logger.debug(f"Event loop thread (TID: {current_thread_id}) entering main run_until_complete phase (waiting for shutdown signal).")
            # The loop runs here, processing tasks, until _shutdown_requested_event_for_loop is set.
            loop_object_for_this_thread.run_until_complete(shutdown_event_for_this_loop.wait())
        except Exception as e: # pragma: no cover
            # Catch any unexpected error during the loop's main execution phase.
            logger.exception(f"Event loop in thread {current_thread_id} encountered an error during its main wait: {e}")
        finally:
            logger.info(f"Event loop thread (TID: {current_thread_id}) shutting down (exited main wait phase).")
            try:
                # Attempt cleanup of tasks and async generators, provided the loop isn't already closed.
                if loop_object_for_this_thread and not loop_object_for_this_thread.is_closed():
                    logger.debug(
                        f"Loop (TID: {current_thread_id}) not closed yet. "
                        "Proceeding with task cancellation and async generator shutdown."
                    )

                    all_tasks_in_loop = asyncio.all_tasks(loop=loop_object_for_this_thread)
                    # The current_task is the one that was waiting on shutdown_event_for_this_loop.
                    # It completes normally when the event is set.
                    current_task_in_loop = asyncio.current_task(loop=loop_object_for_this_thread)

                    tasks_to_cancel = [
                        t for t in all_tasks_in_loop
                        if t is not current_task_in_loop and not t.done() # Don't cancel self or already done tasks
                    ]

                    if tasks_to_cancel:
                        logger.debug(f"Cancelling {len(tasks_to_cancel)} outstanding tasks in loop (TID: {current_thread_id})...")
                        for task in tasks_to_cancel:
                            task.cancel()

                        logger.debug(f"Gathering {len(tasks_to_cancel)} cancelled tasks in loop (TID: {current_thread_id}) to allow their cleanup...")
                        try:
                            # This run_until_complete allows cancelled tasks to handle CancelledError
                            # (e.g., run their 'finally' blocks).
                            loop_object_for_this_thread.run_until_complete(
                                asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                            )
                            logger.debug(f"Gather for cancelled tasks processed in loop (TID: {current_thread_id}).")
                        except Exception as e_gather: # pragma: no cover
                             logger.exception(f"Error during asyncio.gather of cancelled tasks in loop (TID: {current_thread_id}): {e_gather}")
                    else:
                        logger.debug(f"No outstanding tasks to cancel in loop (TID: {current_thread_id}).")

                    logger.debug(f"Shutting down async generators for loop (TID: {current_thread_id}).")
                    try:
                        # This also needs to run to completion on the loop.
                        loop_object_for_this_thread.run_until_complete(
                           loop_object_for_this_thread.shutdown_asyncgens()
                        )
                    except RuntimeError as e_ru_ash: # pragma: no cover
                        # Handle cases where loop might be closing/closed concurrently by another path.
                        if "cannot schedule new futures after shutdown" in str(e_ru_ash).lower() or \
                           "Event loop is closed" in str(e_ru_ash):
                            logger.warning(f"Could not run shutdown_asyncgens for loop (TID: {current_thread_id}), loop may have been closed: {e_ru_ash}")
                        else: # Other RuntimeErrors
                            logger.exception(f"RuntimeError during shutdown_asyncgens for loop (TID: {current_thread_id}): {e_ru_ash}")
                    except Exception as e_asyncgen: # pragma: no cover
                        logger.exception(f"Unexpected error during shutdown_asyncgens for loop (TID: {current_thread_id}): {e_asyncgen}")
                else:
                    logger.warning( # pragma: no cover
                        f"Loop (TID: {current_thread_id}) was already closed or is None "
                        "before explicit task/asyncgen cleanup in _run_loop_in_thread's finally."
                    )
            except Exception as e_shutdown_outer: # pragma: no cover
                # Catch errors from the cleanup logic itself.
                logger.exception(f"Outer error during loop's (TID: {current_thread_id}) async resource shutdown process: {e_shutdown_outer}")
            finally:
                # Ensure the loop is closed.
                if loop_object_for_this_thread and not loop_object_for_this_thread.is_closed():
                    loop_object_for_this_thread.close()

                closed_state = loop_object_for_this_thread.is_closed() if loop_object_for_this_thread else 'N/A (loop was None)'
                logger.info(f"Event loop thread (TID: {current_thread_id}) loop final closed state: {closed_state}.")

                # Clear the asyncio.Event used for startup confirmation.
                if running_event_for_this_loop:
                    running_event_for_this_loop.clear()


    def ensure_loop_running(self) -> None:
        """Ensures the asyncio event loop is created and running in its dedicated thread."""
        with self._lock: # Protect the entire startup sequence
            if self.is_loop_running():
                return # Already running

            # Handle case where thread might be alive from a previous failed startup
            # but is_loop_running() returned false (e.g. _loop_is_actually_running_event not set)
            if self._loop_thread and self._loop_thread.is_alive(): # pragma: no cover
                logger.warning(
                    "ensure_loop_running: Loop thread found alive but service not marked as running. "
                    "Attempting to wait for running confirmation event."
                )
                if self._loop_is_actually_running_event and self._loop: # Must exist if thread was started
                    temp_wait_confirm = threading.Event()
                    async def _check_running_event_and_signal_sync():
                        if self._loop_is_actually_running_event:
                           await self._loop_is_actually_running_event.wait()
                        temp_wait_confirm.set()

                    if not self._loop.is_closed():
                        asyncio.run_coroutine_threadsafe(_check_running_event_and_signal_sync(), self._loop)
                        if temp_wait_confirm.wait(timeout=_LOOP_START_TIMEOUT):
                            # If event was set, is_loop_running() should now be true
                            if self.is_loop_running(): return
                        else: # Timeout waiting for confirmation
                            raise CoreTaskManagerError(
                               f"Loop thread was alive but failed to confirm active running state within {_LOOP_START_TIMEOUT}s."
                           )
                    else: # Loop was found closed
                        logger.warning("ensure_loop_running: Found alive thread but its loop was closed. Proceeding to recreate.")
                        # Fall through to recreate logic
                else: # Should not happen if thread is alive from our start
                     raise CoreTaskManagerError(
                        "ensure_loop_running: Loop thread alive but critical event objects are missing."
                    )


            logger.info("Initializing and starting asyncio event loop in a new thread.")
            # Create new loop and associated asyncio events for this run
            self._loop = asyncio.new_event_loop()
            self._shutdown_requested_event_for_loop = asyncio.Event()
            self._loop_is_actually_running_event = asyncio.Event()
            self._sync_shutdown_wait_event.clear() # Clear sync event for this new session

            self._loop_thread = threading.Thread(
                target=self._run_loop_in_thread,
                daemon=True, # Daemon thread allows main program to exit even if loop thread is stuck
                name="SidekickCoreAsyncLoop"
            )
            self._loop_thread.start()
            self._loop_creation_attempted = True # Mark that we've tried

            # Wait for the loop thread to signal that it has started and set its loop.
            # This uses a temporary threading.Event bridged from the asyncio.Event.
            temp_startup_sync_event = threading.Event()
            async def _wait_for_async_running_event_and_signal_sync():
                if self._loop_is_actually_running_event: # Should have been created
                    await self._loop_is_actually_running_event.wait()
                temp_startup_sync_event.set() # Signal the synchronous waiter

            if self._loop: # Loop must exist to schedule on it
                asyncio.run_coroutine_threadsafe(_wait_for_async_running_event_and_signal_sync(), self._loop)
            else: # pragma: no cover
                # Should not happen if logic above is correct
                raise CoreTaskManagerError("ensure_loop_running: self._loop is None before scheduling startup confirmation.")

            if not temp_startup_sync_event.wait(timeout=_LOOP_START_TIMEOUT): # pragma: no cover
                # Loop thread failed to start and signal within timeout
                err_msg = f"Failed to confirm event loop start in thread within {_LOOP_START_TIMEOUT} seconds."
                logger.error(err_msg)
                # Attempt to clean up the potentially stuck thread
                if self._loop and self._shutdown_requested_event_for_loop and not self._loop.is_closed():
                    try:
                        self._loop.call_soon_threadsafe(self._shutdown_requested_event_for_loop.set)
                    except RuntimeError: pass # Loop might be closing/closed
                if self._loop_thread and self._loop_thread.is_alive():
                    self._loop_thread.join(timeout=1.0) # Attempt to join
                raise CoreTaskManagerError(err_msg)

            logger.info("Asyncio event loop successfully started and confirmed running.")


    def is_loop_running(self) -> bool:
        """Checks if the managed asyncio event loop is currently active and confirmed running."""
        with self._lock: # Protect access to shared attributes
            # Check if the asyncio.Event (set by the loop thread) is set
            loop_event_confirmed_running = False
            if self._loop_is_actually_running_event:
                # asyncio.Event.is_set() is thread-safe
                loop_event_confirmed_running = self._loop_is_actually_running_event.is_set()

            return (
                self._loop is not None and       # Loop object exists
                self._loop_thread is not None and # Thread object exists
                self._loop_thread.is_alive() and  # Thread is running
                loop_event_confirmed_running     # Loop has signaled it's up
            )

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Returns the managed asyncio event loop, ensuring it's running first."""
        self.ensure_loop_running() # Guarantees loop is started or raises error
        if not self._loop: # Should be set by ensure_loop_running or error raised
            raise CoreLoopNotRunningError("Loop has not been initialized despite ensure_loop_running.") # pragma: no cover
        return self._loop


    def _schedule_task_creation_in_loop(
        self,
        coro: Coroutine[Any, Any, Any],
        task_ref_future: concurrent.futures.Future # Future to return the asyncio.Task
    ) -> None:
        """Internal helper: schedules `loop.create_task(coro)` from loop thread."""
        # This method is called via loop.call_soon_threadsafe, so it runs in the loop thread.
        loop_for_task = self._loop # Capture current loop reference
        if not loop_for_task or loop_for_task.is_closed(): # pragma: no cover
            task_ref_future.set_exception(
                CoreLoopNotRunningError("Loop not available or closed when trying to create task.")
            )
            return
        try:
            # Ensure we are actually running on the loop we think we are (defensive)
            if asyncio.get_running_loop() is not loop_for_task: # pragma: no cover
                 logger.warning(
                    "_schedule_task_creation_in_loop called from an unexpected loop context. "
                    "This could indicate an issue."
                )
            task = loop_for_task.create_task(coro)
            task_ref_future.set_result(task)
        except Exception as e: # pragma: no cover
            logger.exception(f"Failed to create task for coroutine {coro} in loop thread: {e}")
            task_ref_future.set_exception(
                CoreTaskSubmissionError(f"Task creation failed in loop: {e}", original_exception=e)
            )

    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Submits a coroutine to the managed loop and returns an asyncio.Task.

        If called from the loop thread itself, creates the task directly.
        Otherwise, schedules the task creation thread-safely and waits briefly
        for the `asyncio.Task` object reference.
        """
        self.ensure_loop_running() # Make sure loop and thread are up
        loop = self._ensure_and_get_loop() # Get the loop, re-validates it's running

        try:
            # If this call is already executing on the TaskManager's loop thread
            if asyncio.get_running_loop() is loop:
                return loop.create_task(coro)
        except RuntimeError:
            # No loop running in *this* thread (e.g. main thread), so proceed to threadsafe submission.
            pass

        # Called from a different thread, so use call_soon_threadsafe
        task_ref_future = concurrent.futures.Future() # Used to get asyncio.Task back
        loop.call_soon_threadsafe(
            self._schedule_task_creation_in_loop, # Schedules create_task on loop
            coro,
            task_ref_future
        )
        try:
            # Block synchronously to get the asyncio.Task object.
            # This makes submit_task's signature (returning asyncio.Task) fulfillable
            # even when called from a non-loop thread.
            task: asyncio.Task = task_ref_future.result(timeout=_GET_TASK_REF_TIMEOUT)
            return task
        except concurrent.futures.TimeoutError: # pragma: no cover
            err_msg = (
                f"Timeout ({_GET_TASK_REF_TIMEOUT}s) waiting for asyncio.Task reference "
                "from loop thread. Task may be scheduled but reference not retrieved."
            )
            logger.error(err_msg)
            # It's hard to cancel the task if we don't have its reference yet.
            # The coroutine might still run.
            raise CoreTaskSubmissionError(err_msg)
        except Exception as e: # pragma: no cover
            # This could be an exception set on task_ref_future by _schedule_task_creation_in_loop
            logger.exception(f"Error obtaining asyncio.Task reference via future: {e}")
            if isinstance(e, CoreTaskSubmissionError): raise e # Re-raise if already correct type
            raise CoreTaskSubmissionError(f"Failed to obtain task reference: {e}", original_exception=e)

    def submit_and_wait(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Submits a coroutine to the managed event loop and blocks the current
        (non-loop) thread until the coroutine completes. It then returns the
        coroutine's result or raises its exception.

        This method provides a synchronous bridge to run and await an asynchronous
        task from a synchronous context. It polls for the result periodically
        to remain responsive to `KeyboardInterrupt` in the calling thread.

        Warning:
            This method **MUST NOT** be called from within the TaskManager's own
            event loop thread (i.e., a coroutine submitted via `submit_task` or
            `submit_and_wait` should not call this method again). Doing so would
            lead to a deadlock and will raise a `RuntimeError`.

        Args:
            coro: The coroutine to execute on the TaskManager's event loop.

        Returns:
            Any: The result returned by the successfully completed coroutine.

        Raises:
            RuntimeError: If called from within the TaskManager's own event loop thread.
            CoreLoopNotRunningError: If the TaskManager's event loop is not
                                     initialized or running when attempting to get it.
            CoreTaskSubmissionError: If `asyncio.run_coroutine_threadsafe` fails for
                                     reasons other than the loop not being ready.
            KeyboardInterrupt: If a `KeyboardInterrupt` (e.g., Ctrl+C) occurs in
                               the calling thread while waiting for the coroutine.
                               In this case, a shutdown of the TaskManager is signaled.
            asyncio.CancelledError: If the submitted coroutine is cancelled during
                                    its execution (often as part of the TaskManager's
                                    shutdown process).
            Exception: Any other exception raised by the `coro` during its execution
                       will be propagated to the caller of `submit_and_wait`.
        """
        # Step 1: Ensure the loop is available and get a reference to it.
        # get_loop() internally calls ensure_loop_running().
        try:
            loop = self.get_loop()
        except CoreLoopNotRunningError as e:  # pragma: no cover
            # This path indicates a fundamental issue with TM initialization if get_loop fails.
            logger.critical(
                f"submit_and_wait: Failed to get an active event loop. "
                f"TaskManager may not be properly initialized. Error: {e}"
            )
            # Re-raise as a more generic RuntimeError indicating a precondition failure for this method.
            raise RuntimeError(f"TaskManager loop not available for submit_and_wait: {e}") from e

        # Step 2: Prevent recursive calls from the loop thread itself (deadlock avoidance).
        try:
            if asyncio.get_running_loop() is loop:
                # This means submit_and_wait is being called from a coroutine
                # already running on this TaskManager's loop.
                err_msg = (
                    "submit_and_wait cannot be called from within the TaskManager's own event loop thread "
                    "as it would cause a deadlock by blocking the loop it needs to complete the task."
                )
                logger.error(err_msg)
                raise RuntimeError(err_msg)
        except RuntimeError as e_get_loop_check:
            # This 'except' block handles two scenarios from `asyncio.get_running_loop()`:
            # 1. If it's our specific RuntimeError from the 'if' block above: re-raise it.
            if "submit_and_wait cannot be called from within" in str(e_get_loop_check):
                raise e_get_loop_check
            # 2. If `asyncio.get_running_loop()` itself raises "no running event loop":
            #    This is the expected scenario if submit_and_wait is called from a
            #    non-asyncio thread (e.g., the main application thread). We can proceed.
            elif "no running event loop" in str(e_get_loop_check).lower():
                logger.debug("submit_and_wait: Called from a non-loop thread (e.g., main thread), which is correct.")
            else:  # pragma: no cover
                # Any other RuntimeError from get_running_loop() is unexpected here.
                logger.error(f"submit_and_wait: Unexpected RuntimeError during running loop check: {e_get_loop_check}")
                raise  # Re-raise other unexpected RuntimeErrors

        # Step 3: Schedule the coroutine on the event loop thread-safely.
        # `asyncio.run_coroutine_threadsafe` returns a `concurrent.futures.Future`.
        logger.debug(
            f"submit_and_wait: Submitting coroutine '{getattr(coro, '__name__', 'unknown_coro')}' to loop thread.")
        try:
            cf_future = asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e_run_threadsafe:  # pragma: no cover
            # This could happen if, for example, the loop was closed between get_loop() and here,
            # or other low-level asyncio errors.
            logger.exception(f"submit_and_wait: asyncio.run_coroutine_threadsafe failed: {e_run_threadsafe}")
            raise CoreTaskSubmissionError(
                f"Failed to schedule coroutine on loop thread: {e_run_threadsafe}",
                original_exception=e_run_threadsafe
            ) from e_run_threadsafe

        # Step 4: Wait for the concurrent.futures.Future to complete, with polling.
        # The polling allows the main thread to be responsive to KeyboardInterrupt.
        logger.debug(
            f"submit_and_wait: Main thread (TID: {threading.get_ident()}) now polling for coroutine completion.")
        try:
            while not cf_future.done():
                try:
                    # Attempt to get the result with a short timeout.
                    # If the future is done, this returns/raises immediately.
                    # If not done, it raises concurrent.futures.TimeoutError after the interval.
                    return cf_future.result(timeout=_FUTURE_WAIT_POLL_INTERVAL)
                except concurrent.futures.TimeoutError:
                    # This is the expected timeout for polling, just continue the loop.
                    pass
                # If KeyboardInterrupt occurs during cf_future.result(), it will propagate
                # out of this inner try and be caught by the outer KeyboardInterrupt handler below.

            # If the loop finishes because cf_future.done() is true, retrieve the final result/exception.
            # This call will not block if cf_future is truly done.
            return cf_future.result()

        except KeyboardInterrupt:  # pragma: no cover
            # This handles Ctrl+C pressed in the main thread while it's polling.
            logger.info(
                "submit_and_wait: KeyboardInterrupt received during polling for coroutine result. Signaling TM shutdown.")
            self.signal_shutdown()  # Initiate shutdown of the TaskManager and its loop.

            # Attempt to cancel the concurrent.futures.Future. This, in turn,
            # should lead to the asyncio.Task in the loop thread being cancelled
            # if it's at an 'await' point.
            if not cf_future.done():
                if cf_future.cancel():
                    logger.debug("submit_and_wait: concurrent.futures.Future was cancelled due to KeyboardInterrupt.")
                else:
                    logger.debug(
                        "submit_and_wait: concurrent.futures.Future could not be cancelled "
                        "(it may have already started running or completed)."
                    )
            raise  # Re-raise KeyboardInterrupt to allow the calling application to terminate.

        except concurrent.futures.CancelledError:  # pragma: no cover
            # This occurs if cf_future.result() is called on a future that was successfully
            # cancelled (e.g., by the KeyboardInterrupt block above, or if the asyncio.Task
            # itself was cancelled by the loop's shutdown process).
            logger.info("submit_and_wait: Coroutine's future was cancelled (likely due to shutdown signal).")
            # Propagate as asyncio.CancelledError for consistency if this is bubbled up
            # from an asyncio context, though submit_and_wait is usually called from sync.
            raise asyncio.CancelledError("Coroutine execution was cancelled by shutdown or interruption.") from None
        except Exception as e_coro:
            # This 'except' block catches exceptions *raised by the coroutine itself*
            # and set on the cf_future by the event loop.
            logger.debug(f"submit_and_wait: Coroutine raised an exception: {type(e_coro).__name__}: {e_coro}")
            raise  # Re-raise the original exception from the coroutine.

    def signal_shutdown(self) -> None:
        """Signals the event loop (and synchronous waiters) to shut down."""
        with self._lock: # Protect access to loop and event attributes
            loop_ref = self._loop
            async_shutdown_event_ref = self._shutdown_requested_event_for_loop
            sync_shutdown_event_is_set = self._sync_shutdown_wait_event.is_set() # Check before trying to set

            # Signal the asyncio event for the loop thread
            if loop_ref and not loop_ref.is_closed() and \
               async_shutdown_event_ref and not async_shutdown_event_ref.is_set():
                logger.info("Signaling event loop to shutdown via asyncio.Event.set().")
                try:
                    # Schedules .set() to be called in the loop thread.
                    loop_ref.call_soon_threadsafe(async_shutdown_event_ref.set)
                except RuntimeError as e: # pragma: no cover
                    # This can happen if the loop is closing/closed just as we try to schedule.
                    logger.warning(f"Could not schedule signal_shutdown on loop (already closing/closed?): {e}")
            elif not (loop_ref and not loop_ref.is_closed()): # pragma: no cover
                 logger.debug("Loop not active/initialized for signaling asyncio shutdown event.")
            else: # Event already set or loop_ref is None
                 logger.debug("Asyncio shutdown event already set, or loop not ready for signaling.")

            # Signal the threading.Event for synchronous waiters (like wait_for_shutdown)
            if not sync_shutdown_event_is_set:
                logger.info("Signaling synchronous shutdown event (threading.Event).")
                self._sync_shutdown_wait_event.set()
            else:
                logger.debug("Synchronous shutdown event (threading.Event) was already set.")


    def wait_for_shutdown(self) -> None:
        """Blocks the current (non-loop) thread until shutdown is completed."""
        if not self._loop_creation_attempted:
            logger.debug("wait_for_shutdown called but loop was never started. Returning immediately.")
            return

        # Check if loop is running; if not, but creation was attempted, means it might have failed
        # or shut down prematurely.
        try:
            if not self.is_loop_running() and self._loop_creation_attempted:
                 logger.warning(
                    "wait_for_shutdown: Loop not actively running (or startup failed), "
                    "but proceeding to wait for synchronous shutdown signal."
                )
        except CoreTaskManagerError as e: # pragma: no cover
            # This might happen if is_loop_running itself encounters an issue
            logger.warning(f"TaskManager error during pre-wait check in wait_for_shutdown: {e}. May exit prematurely.")

        logger.info("Main thread entering wait_for_shutdown, blocking on synchronous event...")
        self._sync_shutdown_wait_event.wait() # Blocks until signal_shutdown sets this
        logger.info("Main thread unblocked from wait_for_shutdown (synchronous event was set).")

        # After sync event is set, ensure the loop thread itself has terminated.
        thread_to_join = None
        with self._lock: # Get thread reference under lock
            thread_to_join = self._loop_thread

        if thread_to_join and thread_to_join.is_alive():
            logger.debug(f"Waiting for event loop thread (TID: {thread_to_join.ident}) to join...")
            thread_to_join.join(timeout=_LOOP_JOIN_TIMEOUT)
            if thread_to_join.is_alive(): # pragma: no cover
                logger.warning(
                    f"Event loop thread (TID: {thread_to_join.ident}) did not join within "
                    f"{_LOOP_JOIN_TIMEOUT}s timeout. It might be stuck."
                )
            else:
                logger.debug(f"Event loop thread (TID: {thread_to_join.ident}) joined successfully.")
        elif thread_to_join: # pragma: no cover
             logger.debug(f"Event loop thread (TID: {thread_to_join.ident}) was already finished.")
        else: # pragma: no cover
             logger.debug("No event loop thread reference to join (was it started?).")

        # Final cleanup of attributes related to the now-stopped loop/thread
        with self._lock:
            self._loop_thread = None # Clear thread reference
            # Only set _loop to None if thread is confirmed not alive,
            # otherwise _run_loop_in_thread's finally block is responsible for closing it.
            if not (thread_to_join and thread_to_join.is_alive()):
                self._loop = None # Loop is closed and thread joined
            self._loop_creation_attempted = False # Reset for potential re-initiation (though unlikely for singleton)
            self._shutdown_requested_event_for_loop = None
            self._loop_is_actually_running_event = None
        logger.info("CPythonTaskManager wait_for_shutdown complete.")


    async def wait_for_shutdown_async(self) -> None:
        """Asynchronously waits for the shutdown signal (asyncio.Event)."""
        # ensure_loop_running should have been called by the context that wants to use this
        # to make sure _shutdown_requested_event_for_loop is initialized.
        if not self._shutdown_requested_event_for_loop: # pragma: no cover
            # Try to initialize it if called out of order, though this is not ideal.
            self.ensure_loop_running()
            if not self._shutdown_requested_event_for_loop:
                 raise CoreLoopNotRunningError(
                    "Shutdown event (asyncio.Event) not initialized for async wait. "
                    "Ensure loop is running."
                )

        logger.info("Asynchronously waiting for shutdown signal (asyncio.Event)...")
        await self._shutdown_requested_event_for_loop.wait()
        logger.info("Asyncio shutdown event received by wait_for_shutdown_async.")
        # Note: This async wait only waits for the signal. The actual loop thread
        # joining and full cleanup is primarily managed by the synchronous
        # wait_for_shutdown() if this TM is used in a CPython app that blocks its main thread.
        # If used in a fully async app, the caller of this might need to ensure
        # the loop thread (if any) terminates if it was started by this TM.
        # For CPythonTaskManager, this async version is less common for primary shutdown blocking.
