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
_LOOP_START_TIMEOUT = 5.0  # Max seconds to wait for loop thread to confirm asyncio.set_event_loop()
_PROBE_CORO_TIMEOUT = 3.0  # Max seconds to wait for the initial probe coroutine to confirm loop responsiveness
_LOOP_JOIN_TIMEOUT = 5.0   # Max seconds to wait for the loop thread to join during shutdown.
_GET_TASK_REF_TIMEOUT = 5.0 # Max seconds for submit_task to wait for the asyncio.Task reference from loop thread.
_FUTURE_WAIT_POLL_INTERVAL = 0.05 # Short polling interval in submit_and_wait for KeyboardInterrupt responsiveness.
_TASK_CANCELLATION_GATHER_TIMEOUT = 3.0 # Max time for tasks to finish after being cancelled during shutdown.
_ASYNCGEN_SHUTDOWN_TIMEOUT = 2.0    # Max time for asynchronous generators to shut down.


class CPythonTaskManager(TaskManager):
    """Manages an asyncio event loop in a separate thread for CPython environments.

    This implementation starts an asyncio event loop in a dedicated daemon thread,
    allowing the main synchronous Python program to schedule and interact with
    asynchronous tasks. It handles thread-safe submission of coroutines and
    graceful shutdown of the loop and its tasks.
    The startup sequence (`ensure_loop_running`) involves a two-stage confirmation:
    1. The event loop thread confirms it has successfully called `asyncio.set_event_loop()`.
    2. The calling thread submits a "probe" coroutine and waits for its completion
       to confirm the event loop is truly responsive to new tasks.
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
        # _loop_thread, _loop_creation_attempted and during startup/shutdown sequences.
        self._lock = threading.RLock()

        # asyncio.Event, set by the loop thread once asyncio.set_event_loop() is done
        # and the loop is about to enter its main processing cycle (_loop_runner_task).
        self._loop_set_and_ready_to_run_event: Optional[asyncio.Event] = None
        # threading.Event, used by ensure_loop_running (typically from main thread)
        # to wait for _loop_set_and_ready_to_run_event to be set by the loop thread.
        # This forms the first stage of startup confirmation.
        self._sync_loop_set_confirm_event = threading.Event()

        # asyncio.Event, lives in self._loop. Set by signal_shutdown() to tell
        # _loop_runner_task to exit its processing cycle.
        self._shutdown_requested_event_for_loop: Optional[asyncio.Event] = None
        # threading.Event, used by a synchronous thread (e.g., main thread in wait_for_shutdown())
        # to block until shutdown is signaled by signal_shutdown().
        self._sync_shutdown_wait_event = threading.Event()

        # Flag to indicate if ensure_loop_running() has been called at least once
        # to attempt loop creation and thread start.
        self._loop_creation_attempted = False


    def _ensure_and_get_loop(self) -> asyncio.AbstractEventLoop:
        """Ensures the loop is initialized and the loop thread is alive, then returns the loop.

        This is an internal helper primarily called after `ensure_loop_running` has
        completed its more thorough checks (including the probe). Its main purpose
        here is to re-verify basic conditions and return `self._loop`.

        Raises:
            CoreLoopNotRunningError: If `self._loop` is not set or the loop thread
                                     is not alive, indicating a problem with prior
                                     initialization.
        """
        with self._lock: # Ensure consistent access to self._loop and self._loop_thread
            if not self._loop or not self._loop_thread or not self._loop_thread.is_alive():
                # This state should ideally not be reached if ensure_loop_running() was successful.
                # It implies a more fundamental issue or incorrect calling sequence.
                logger.error(
                    "_ensure_and_get_loop: Loop or loop thread is not available/alive. "
                    "This indicates a failure in the TM startup sequence."
                )
                raise CoreLoopNotRunningError(
                    "Event loop is not properly initialized or its managing thread is not running."
                )
            # At this point, ensure_loop_running() should have confirmed responsiveness.
            # We return the loop instance.
            return self._loop

    async def _loop_runner_task(self):
        """
        The main coroutine that drives the event loop's processing cycle in the dedicated thread.

        It runs in a loop, periodically yielding control via `asyncio.sleep(0)`.
        This yielding allows the event loop to process other scheduled tasks,
        particularly those submitted from different threads via `call_soon_threadsafe`
        (e.g., by `submit_task`). The loop continues until the
        `_shutdown_requested_event_for_loop` is set.
        """
        current_thread_id = threading.get_ident()
        logger.debug(f"Event loop thread (TID: {current_thread_id}) _loop_runner_task starting its processing cycle.")

        # This assertion ensures that _shutdown_requested_event_for_loop was correctly initialized
        # by _run_loop_in_thread before this coroutine starts.
        assert self._shutdown_requested_event_for_loop is not None, \
               "_shutdown_requested_event_for_loop was not initialized before _loop_runner_task started."

        while not self._shutdown_requested_event_for_loop.is_set():
            try:
                # asyncio.sleep(0) yields control to the event loop immediately,
                # allowing it to process any other ready tasks (like those scheduled
                # by call_soon_threadsafe). This is crucial for responsiveness.
                await asyncio.sleep(0)

                # After yielding, re-check the shutdown event.
                if self._shutdown_requested_event_for_loop.is_set():
                    logger.debug(f"_loop_runner_task (TID: {current_thread_id}): Shutdown event detected after sleep(0). Exiting cycle.")
                    break
            except asyncio.CancelledError: # pragma: no cover
                # This occurs if _loop_runner_task itself is cancelled (e.g., during TM shutdown).
                logger.info(f"_loop_runner_task (TID: {current_thread_id}) was cancelled.")
                break
            except Exception as e_tick: # pragma: no cover
                # Catch unexpected errors within the processing cycle.
                logger.exception(f"Unexpected error in _loop_runner_task (TID: {current_thread_id}) processing cycle: {e_tick}")
                # Pause briefly before continuing to prevent tight error loops.
                await asyncio.sleep(0.01)
        logger.debug(f"Event loop thread (TID: {current_thread_id}) _loop_runner_task finished its processing cycle.")


    def _run_loop_in_thread(self) -> None:
        """The target function executed by the dedicated event loop thread.

        This method performs the following critical steps:
        1. Sets the current thread's asyncio event loop to `self._loop` (which was
           created by `ensure_loop_running` in the main thread).
        2. Creates `self._shutdown_requested_event_for_loop` (an `asyncio.Event`)
           on this newly set event loop. This event will be used by `_loop_runner_task`
           to detect shutdown requests.
        3. Signals `self._loop_set_and_ready_to_run_event` (another `asyncio.Event`)
           to notify `ensure_loop_running` (waiting in the main thread) that
           `set_event_loop` is done and the loop is about to run its main task.
        4. Runs `self._loop_runner_task()` using `loop.run_until_complete()`. This
           starts the event loop's main processing cycle.
        5. Upon completion of `_loop_runner_task()` (typically due to shutdown),
           it performs cleanup: cancels outstanding tasks, shuts down async
           generators, and finally closes the event loop.
        """
        # Capture references to attributes that will be used by this thread.
        loop_object_for_this_thread = self._loop
        # This event is set by this thread to signal the main thread.
        loop_set_event_for_this_thread = self._loop_set_and_ready_to_run_event

        if not loop_object_for_this_thread or \
           not loop_set_event_for_this_thread: # pragma: no cover
            # This indicates a programming error: thread started before essential attributes were set.
            logger.critical(
                "_run_loop_in_thread: Thread started with uninitialized loop object "
                "or its confirmation asyncio.Event. Aborting thread."
            )
            # Attempt to signal synchronous waiters about this failure.
            if not self._sync_loop_set_confirm_event.is_set():
                 self._sync_loop_set_confirm_event.set() # Unblock, they will see startup failure
            return

        current_thread_id = threading.get_ident()
        logger.info(f"Event loop thread (TID: {current_thread_id}) starting execution.")

        # Set the asyncio event loop for this thread.
        asyncio.set_event_loop(loop_object_for_this_thread)

        # CRITICAL: Create the _shutdown_requested_event_for_loop *on this thread's loop*.
        # This ensures it's bound to the correct loop instance.
        if self._shutdown_requested_event_for_loop is None or \
           self._shutdown_requested_event_for_loop._loop is not loop_object_for_this_thread: # type: ignore
            self._shutdown_requested_event_for_loop = asyncio.Event() # Created on current (loop_object_for_this_thread)
            logger.debug(
                f"Event loop thread (TID: {current_thread_id}) "
                "created/re-created its _shutdown_requested_event_for_loop on its own event loop."
            )

        # Signal the main thread (via ensure_loop_running) that set_event_loop is done
        # and the loop is about to run its main task (_loop_runner_task).
        if loop_set_event_for_this_thread:
            logger.debug(
                f"Event loop thread (TID: {current_thread_id}) is now setting "
                "_loop_set_and_ready_to_run_event (asyncio.Event)."
            )
            loop_set_event_for_this_thread.set()

        try:
            logger.debug(
                f"Event loop thread (TID: {current_thread_id}) entering main run_until_complete phase "
                "(will execute _loop_runner_task)."
            )
            # This runs the _loop_runner_task, which contains the while loop with asyncio.sleep(0).
            # This is the main "engine" of the event loop thread.
            loop_object_for_this_thread.run_until_complete(self._loop_runner_task())
        except Exception as e_run_main_task: # pragma: no cover
            # Catch unexpected errors from run_until_complete or _loop_runner_task itself.
            logger.exception(
                f"Event loop in thread {current_thread_id} encountered an unhandled error "
                f"during its main _loop_runner_task execution: {e_run_main_task}"
            )
        finally:
            logger.info(
                f"Event loop thread (TID: {current_thread_id}) is shutting down "
                "(exited run_until_complete for _loop_runner_task)."
            )
            # Standard asyncio cleanup sequence for an event loop before closing.
            try:
                if loop_object_for_this_thread and not loop_object_for_this_thread.is_closed():
                    logger.debug(
                        f"Loop (TID: {current_thread_id}) is not yet closed. "
                        "Proceeding with task cancellation and async generator shutdown."
                    )

                    # Get all tasks except the current one (_loop_runner_task, which is now finishing).
                    all_tasks_in_loop = asyncio.all_tasks(loop=loop_object_for_this_thread)
                    current_task_in_loop = asyncio.current_task(loop=loop_object_for_this_thread)
                    tasks_to_cancel = [
                        t for t in all_tasks_in_loop
                        if t is not current_task_in_loop and not t.done()
                    ]

                    if tasks_to_cancel:
                        logger.debug(f"Cancelling {len(tasks_to_cancel)} outstanding tasks in loop (TID: {current_thread_id})...")
                        for task in tasks_to_cancel:
                            task.cancel() # Request cancellation for each task.

                        logger.debug(
                            f"Gathering {len(tasks_to_cancel)} cancelled tasks in loop (TID: {current_thread_id}) "
                            "to allow them to process CancelledError and perform cleanup..."
                        )
                        try:
                            # Run gather to allow tasks to handle CancelledError.
                            loop_object_for_this_thread.run_until_complete(
                                asyncio.gather(*tasks_to_cancel, return_exceptions=True)
                            )
                            logger.debug(f"Gather for cancelled tasks processed in loop (TID: {current_thread_id}).")
                        except Exception as e_gather_cancelled: # pragma: no cover
                             logger.exception(
                                f"Error during asyncio.gather of cancelled tasks in loop (TID: {current_thread_id}): {e_gather_cancelled}"
                            )
                    else:
                        logger.debug(f"No outstanding tasks to cancel in loop (TID: {current_thread_id}).")

                    # Shut down asynchronous generators.
                    logger.debug(f"Shutting down async generators for loop (TID: {current_thread_id}).")
                    try:
                        loop_object_for_this_thread.run_until_complete(
                           loop_object_for_this_thread.shutdown_asyncgens()
                        )
                    except RuntimeError as e_runtime_ashutdown: # pragma: no cover
                        # This can happen if loop is closing/closed concurrently.
                        if "cannot schedule new futures after shutdown" in str(e_runtime_ashutdown).lower() or \
                           "Event loop is closed" in str(e_runtime_ashutdown).lower():
                            logger.warning(
                                f"Could not run shutdown_asyncgens for loop (TID: {current_thread_id}), "
                                f"loop may have been closed already: {e_runtime_ashutdown}"
                            )
                        else: # Other RuntimeErrors from shutdown_asyncgens
                            logger.exception(
                                f"RuntimeError during shutdown_asyncgens for loop (TID: {current_thread_id}): {e_runtime_ashutdown}"
                            )
                    except Exception as e_asyncgen_shutdown: # pragma: no cover
                        logger.exception(
                            f"Unexpected error during shutdown_asyncgens for loop (TID: {current_thread_id}): {e_asyncgen_shutdown}"
                        )
                else: # loop_object_for_this_thread is None or already closed
                    logger.warning( # pragma: no cover
                        f"Loop (TID: {current_thread_id}) was already closed or is None "
                        "before explicit task/asyncgen cleanup in _run_loop_in_thread's finally block. Skipping."
                    )
            except Exception as e_outer_shutdown_logic: # pragma: no cover
                # Catch errors from the cleanup logic itself.
                logger.exception(
                    f"Outer error during loop's (TID: {current_thread_id}) "
                    f"asynchronous resource shutdown process: {e_outer_shutdown_logic}"
                )
            finally:
                # Ensure the loop is always closed.
                if loop_object_for_this_thread and not loop_object_for_this_thread.is_closed():
                    loop_object_for_this_thread.close()

                closed_state_msg = 'N/A (loop object was None)'
                if loop_object_for_this_thread:
                    closed_state_msg = 'closed' if loop_object_for_this_thread.is_closed() else 'NOT closed (error in close?)'
                logger.info(f"Event loop thread (TID: {current_thread_id}) loop final state: {closed_state_msg}.")

                # Clear the asyncio.Event used for startup confirmation, as the loop is no longer "set and ready".
                if loop_set_event_for_this_thread and loop_set_event_for_this_thread.is_set():
                    loop_set_event_for_this_thread.clear()


    async def _probe_coroutine(self):
        """A simple coroutine used by ensure_loop_running to confirm the event loop is responsive.
        Its successful completion signals that the loop can execute submitted tasks.
        """
        logger.debug("Probe coroutine executing on event loop to confirm responsiveness.")
        # Simply returning (or doing a trivial await asyncio.sleep(0) if more safety needed) is enough.
        await asyncio.sleep(0) # Ensures it yields at least once, confirming task execution.
        logger.debug("Probe coroutine completed successfully.")
        pass


    def ensure_loop_running(self) -> None:
        """Ensures the asyncio event loop is created, running in its dedicated thread,
        and is responsive to new tasks.

        This method implements a two-stage confirmation:
        1.  Starts the event loop thread and waits for it to signal (via
            `_sync_loop_set_confirm_event`) that `asyncio.set_event_loop()` has
            been successfully called within that thread.
        2.  After the first confirmation, it submits a "probe" coroutine
            (`_probe_coroutine`) to the event loop and waits for its completion.
            This second stage verifies that the loop is not just set up but is
            actively processing tasks submitted from other threads.

        Raises:
            CoreTaskManagerError: If any stage of the startup or probing fails or times out.
        """
        with self._lock: # Protect the entire startup sequence
            if self.is_loop_running(): # is_loop_running checks thread aliveness and _sync_loop_set_confirm_event
                logger.debug("ensure_loop_running: Loop already considered running and confirmed. Skipping full startup.")
                return

            # If a previous attempt to create the loop was made but is_loop_running is false,
            # it implies a potential partial/failed startup. We might need to be more robust here
            # e.g. try to join the old thread if it's still alive before creating a new one.
            # For simplicity now, if is_loop_running() is false, we proceed with a full new setup.
            if self._loop_thread and self._loop_thread.is_alive(): # pragma: no cover
                logger.warning(
                    "ensure_loop_running: Found an existing live loop thread, but is_loop_running() returned False. "
                    "This indicates a potential issue from a previous startup. Proceeding with re-initialization. "
                    "Consider more robust cleanup of old thread if this occurs frequently."
                )
                # Attempt a quick join on old thread, but don't block indefinitely.
                self._loop_thread.join(timeout=0.1)
                if self._loop_thread.is_alive():
                    logger.error("ensure_loop_running: Old loop thread is still alive after join attempt. This could lead to resource issues.")
                self._loop_thread = None # Discard reference to potentially problematic old thread.
                self._loop = None # Clear old loop instance


            logger.info("ensure_loop_running: Initializing and starting asyncio event loop in a new thread.")
            # Create a new event loop instance. This will be passed to the new thread.
            self._loop = asyncio.new_event_loop()
            # Create the asyncio.Event that the new loop thread will set.
            # This event *must* be created by the main thread *before* the loop thread starts,
            # so the loop thread has the correct Event object instance to set.
            # However, its _loop attribute will be set implicitly when it's first awaited or manipulated
            # on the loop it's intended for.
            self._loop_set_and_ready_to_run_event = asyncio.Event()

            # Clear threading.Events for this new startup attempt
            self._sync_loop_set_confirm_event.clear()
            self._sync_shutdown_wait_event.clear() # Ensure shutdown event is also reset

            # Create and start the new thread.
            self._loop_thread = threading.Thread(
                target=self._run_loop_in_thread,
                daemon=True, # Daemon thread allows main program to exit even if this thread is stuck.
                name="SidekickCoreAsyncLoop"
            )
            self._loop_thread.start()
            self._loop_creation_attempted = True # Mark that we've initiated the startup.

            # ---- Stage 1: Wait for loop thread to confirm `set_event_loop()` ----
            # The loop thread will call self._loop_set_and_ready_to_run_event.set().
            # We need to bridge this asyncio.Event signal to our current (main) thread
            # using a threading.Event.

            # Define a bridge coroutine that will run on the new loop.
            async def _wait_for_async_loop_set_event_and_signal_sync_thread():
                if self._loop_set_and_ready_to_run_event:
                    try:
                        # Wait for the loop thread to signal that set_event_loop is done.
                        await asyncio.wait_for(self._loop_set_and_ready_to_run_event.wait(), timeout=_LOOP_START_TIMEOUT)
                        # If successful, set the threading.Event to unblock the main thread.
                        self._sync_loop_set_confirm_event.set()
                        logger.debug("_wait_for_async_loop_set_event: Successfully set _sync_loop_set_confirm_event.")
                    except asyncio.TimeoutError: # pragma: no cover
                        logger.error(
                            "_wait_for_async_loop_set_event: Timed out waiting for loop thread "
                            "to set _loop_set_and_ready_to_run_event. Startup failed."
                        )
                        # _sync_loop_set_confirm_event will not be set, outer wait will timeout.
                    except Exception as e_wait_ev_bridge: # pragma: no cover
                        logger.error(f"Error in _wait_for_async_loop_set_event_and_signal_sync_thread bridge: {e_wait_ev_bridge}")
                else: # pragma: no cover
                    logger.error("_wait_for_async_loop_set_event: _loop_set_and_ready_to_run_event is None. Cannot proceed.")


            if self._loop: # self._loop is the new loop created for the thread
                # Schedule the bridge coroutine on the *new* loop from this (main) thread.
                asyncio.run_coroutine_threadsafe(_wait_for_async_loop_set_event_and_signal_sync_thread(), self._loop)
            else: # pragma: no cover
                # This should not happen if the above logic is correct.
                self._attempt_thread_shutdown_on_startup_failure()
                raise CoreTaskManagerError("ensure_loop_running: self._loop is None before scheduling loop set confirmation bridge.")

            # Main thread waits for the threading.Event to be set by the bridge.
            logger.debug("ensure_loop_running: Main thread waiting for _sync_loop_set_confirm_event (Stage 1 confirmation).")
            if not self._sync_loop_set_confirm_event.wait(timeout=_LOOP_START_TIMEOUT + 0.5): # Slightly longer timeout
                 # Timeout waiting for the loop thread to confirm it has set its loop.
                err_msg = (
                    f"Timeout ({_LOOP_START_TIMEOUT + 0.5}s) waiting for event loop thread to confirm "
                    "it has called asyncio.set_event_loop(). Loop startup failed."
                )
                logger.error(err_msg)
                self._attempt_thread_shutdown_on_startup_failure() # Try to clean up the thread
                raise CoreTaskManagerError(err_msg)

            logger.debug("ensure_loop_running: Stage 1 (_sync_loop_set_confirm_event) confirmed. Loop thread has set its event loop.")

            # ---- Stage 2: Probe the loop's responsiveness ----
            # Now that we know the loop thread has set its loop, we submit a simple
            # coroutine to it and wait for completion to ensure it's actually processing tasks.
            if not self._loop: # Should be set if Stage 1 passed
                 # This is a safeguard; if _loop is None here, something is very wrong.
                 self._attempt_thread_shutdown_on_startup_failure()
                 raise CoreTaskManagerError("Loop instance is None after Stage 1 confirmation. Cannot probe responsiveness.") # pragma: no cover

            logger.debug("ensure_loop_running: Submitting probe coroutine to event loop (Stage 2 confirmation).")
            probe_cf_future = asyncio.run_coroutine_threadsafe(self._probe_coroutine(), self._loop)
            try:
                # Block the main thread, waiting for the probe coroutine to complete on the loop thread.
                probe_cf_future.result(timeout=_PROBE_CORO_TIMEOUT)
                logger.info("Asyncio event loop successfully started, confirmed running, and responsive to tasks.")
            except concurrent.futures.TimeoutError: # pragma: no cover
                # Probe coroutine did not complete within its timeout.
                err_msg = (
                    f"Timeout ({_PROBE_CORO_TIMEOUT}s) waiting for probe coroutine to complete. "
                    "Event loop may have started but is not responsive to new tasks."
                )
                logger.error(err_msg)
                if not probe_cf_future.done(): probe_cf_future.cancel() # Attempt to cancel the probe task
                self._attempt_thread_shutdown_on_startup_failure() # Try to clean up
                raise CoreTaskManagerError(err_msg)
            except Exception as e_probe_exec: # pragma: no cover
                # Probe coroutine raised an unexpected exception during its execution.
                err_msg = f"Probe coroutine failed with exception: {e_probe_exec}. Event loop may have issues."
                logger.exception(err_msg) # Log with stack trace
                self._attempt_thread_shutdown_on_startup_failure() # Try to clean up
                raise CoreTaskManagerError(err_msg, original_exception=e_probe_exec)
            # If we reach here, ensure_loop_running is successful.

    def _attempt_thread_shutdown_on_startup_failure(self): # pragma: no cover
        """Internal helper: Tries to signal the loop thread to shut down if startup fails."""
        logger.warning("Attempting to signal loop thread for shutdown due to startup failure.")
        # Use the lock to prevent concurrent modification of these attributes
        # while signal_shutdown (which also uses the lock) might be called.
        with self._lock:
            loop_ref = self._loop
            async_shutdown_event = self._shutdown_requested_event_for_loop
            loop_thread_ref = self._loop_thread

        if loop_ref and async_shutdown_event and not loop_ref.is_closed():
            try:
                logger.debug("Startup failure: Signaling _shutdown_requested_event_for_loop.")
                loop_ref.call_soon_threadsafe(async_shutdown_event.set)
            except RuntimeError:
                logger.warning("Startup failure: RuntimeErorr while trying to set shutdown event (loop might be closing).")
        else:
            logger.debug("Startup failure: Loop or shutdown event not available for signaling.")

        if loop_thread_ref and loop_thread_ref.is_alive():
            logger.debug(f"Startup failure: Attempting to join loop thread (TID: {loop_thread_ref.ident}) with short timeout.")
            loop_thread_ref.join(timeout=1.0) # Short timeout, best effort.
            if loop_thread_ref.is_alive():
                logger.error("Startup failure: Loop thread did not stop after join attempt. It may be stuck.")
            else:
                logger.info("Startup failure: Loop thread successfully joined.")
        else:
            logger.debug("Startup failure: No live loop thread to join.")


    def is_loop_running(self) -> bool:
        """Checks if the managed asyncio event loop is considered active.

        "Active" means the loop thread is alive and has confirmed (via
        _sync_loop_set_confirm_event) that it has set its event loop.
        Full responsiveness is further verified by the probe in `ensure_loop_running`.
        """
        with self._lock:
            return (
                self._loop is not None and
                self._loop_thread is not None and
                self._loop_thread.is_alive() and
                self._sync_loop_set_confirm_event.is_set() # Key indicator from main thread's perspective
            )

    def get_loop(self) -> asyncio.AbstractEventLoop:
        """Returns the managed asyncio event loop, ensuring it's running and responsive first."""
        self.ensure_loop_running() # This call now includes the responsiveness probe.
        # _ensure_and_get_loop performs basic checks and returns self._loop.
        return self._ensure_and_get_loop()


    def _schedule_task_creation_in_loop(
        self,
        coro: Coroutine[Any, Any, Any],
        task_ref_future: concurrent.futures.Future
    ) -> None:
        """Internal helper: schedules `loop.create_task(coro)` to run in the loop thread.

        This method is intended to be called via `loop.call_soon_threadsafe`
        from a non-loop thread. It creates an asyncio.Task for the given
        coroutine on the TaskManager's event loop and sets the `task_ref_future`
        with either the Task object or an exception if creation fails.
        """
        loop_for_task = self._loop # Capture self._loop at call time
        coro_name = getattr(coro, '__name__', 'unknown_coro') # For logging

        if not loop_for_task or loop_for_task.is_closed(): # pragma: no cover
            logger.warning(
                f"_schedule_task_creation_in_loop: Event loop not available or closed "
                f"when trying to create task for coroutine '{coro_name}'."
            )
            task_ref_future.set_exception(
                CoreLoopNotRunningError(
                    f"Loop not available or closed when trying to create task for '{coro_name}'."
                )
            )
            return

        try:
            # Create the asyncio.Task on the loop this method is running on.
            task = loop_for_task.create_task(coro)
            # Set the result of the concurrent.futures.Future to be the asyncio.Task.
            # This unblocks the thread that called submit_task and is waiting on this future.
            task_ref_future.set_result(task)
            logger.debug(f"_schedule_task_creation_in_loop: Successfully created task for '{coro_name}'.")
        except Exception as e_create_task: # pragma: no cover
            # Handle any errors during task creation itself.
            logger.exception(
                f"Failed to create task for coroutine '{coro_name}' within the event loop thread: {e_create_task}"
            )
            task_ref_future.set_exception(
                CoreTaskSubmissionError(
                    f"Task creation failed in event loop for '{coro_name}': {e_create_task}",
                    original_exception=e_create_task
                )
            )

    def submit_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
        """Submits a coroutine to the managed event loop and returns an asyncio.Task.

        Ensures the loop is running and responsive before submission.
        If called from the loop thread itself, creates the task directly.
        Otherwise, schedules the task creation thread-safely using
        `loop.call_soon_threadsafe` and waits (with timeout) for the
        `asyncio.Task` object reference to be returned.
        """
        self.ensure_loop_running() # Ensures loop is started, set, and responsive (via probe).
        loop = self._ensure_and_get_loop() # Gets the loop after full checks.
        coro_name = getattr(coro, '__name__', 'unknown_coro') # For better logging.

        try:
            # Check if the current thread is the one running our managed event loop.
            if asyncio.get_running_loop() is loop:
                logger.debug(f"submit_task: Called from within the event loop thread. Creating task '{coro_name}' directly.")
                return loop.create_task(coro)
        except RuntimeError:
            # asyncio.get_running_loop() raises RuntimeError if no loop is set for the current OS thread.
            # This is the expected case when submit_task is called from a non-loop thread (e.g., main thread).
            logger.debug(f"submit_task: Called from a non-loop thread (current thread has no running loop).")
            pass # Proceed to thread-safe submission.

        # If called from a different thread, schedule task creation on the loop thread.
        logger.debug(f"submit_task: Submitting task '{coro_name}' to event loop thread via call_soon_threadsafe.")

        # This concurrent.futures.Future is used by the main thread to wait for the
        # asyncio.Task object to be created by the _schedule_task_creation_in_loop callback.
        task_ref_cf_future = concurrent.futures.Future()

        loop.call_soon_threadsafe(
            self._schedule_task_creation_in_loop, # The callback to run on the loop
            coro,                                 # Argument for the callback
            task_ref_cf_future                    # Argument for the callback
        )

        try:
            # Main thread blocks here, waiting for _schedule_task_creation_in_loop
            # to run on the event loop thread and set the result of task_ref_cf_future.
            # The timeout protects against the loop thread being unresponsive.
            asyncio_task_ref: asyncio.Task = task_ref_cf_future.result(timeout=_GET_TASK_REF_TIMEOUT)
            logger.debug(f"submit_task: Successfully obtained asyncio.Task reference for '{coro_name}' from event loop thread.")
            return asyncio_task_ref
        except concurrent.futures.TimeoutError: # pragma: no cover
            # This timeout means _schedule_task_creation_in_loop did not complete
            # and set the future's result within _GET_TASK_REF_TIMEOUT.
            # This indicates the event loop, despite passing earlier checks, became unresponsive.
            err_msg = (
                f"Timeout ({_GET_TASK_REF_TIMEOUT}s) waiting for asyncio.Task reference from event loop thread "
                f"for coroutine '{coro_name}'. The event loop might be too busy or stuck. "
                f"Loop state from main thread's perspective: loop_obj_exists={self._loop is not None}, "
                f"thread_alive={self._loop_thread.is_alive() if self._loop_thread else 'N/A'}."
            )
            logger.error(err_msg)
            # It's hard to safely cancel the task if we don't have its reference.
            # The coroutine might still run eventually if the loop unblocks.
            raise CoreTaskSubmissionError(err_msg)
        except Exception as e_get_ref: # pragma: no cover
            # This catches exceptions set on task_ref_cf_future by _schedule_task_creation_in_loop
            # (e.g., if loop was closed when _schedule_task_creation_in_loop tried to run).
            logger.exception(f"Error obtaining asyncio.Task reference via concurrent.futures.Future for '{coro_name}': {e_get_ref}")
            if isinstance(e_get_ref, (CoreTaskSubmissionError, CoreLoopNotRunningError)):
                raise # Re-raise if it's already one of our specific core errors.
            # Wrap other exceptions.
            raise CoreTaskSubmissionError(
                f"Failed to obtain asyncio.Task reference for '{coro_name}': {e_get_ref}",
                original_exception=e_get_ref
            )

    def submit_and_wait(self, coro: Coroutine[Any, Any, Any]) -> Any:
        """Submits a coroutine to the managed event loop and blocks the current
        (non-loop) thread until the coroutine completes. It then returns the
        coroutine's result or raises its exception.

        Warning:
            This method **MUST NOT** be called from within the TaskManager's own
            event loop thread, as it would cause a deadlock.
        """
        coro_name = getattr(coro, '__name__', 'unknown_coro')
        try:
            # ensure_loop_running() (called by get_loop()) now includes the probe,
            # so the loop should be responsive if get_loop() succeeds.
            loop = self.get_loop()
        except CoreLoopNotRunningError as e_get_loop_fail:  # pragma: no cover
            # This means ensure_loop_running() itself failed.
            raise RuntimeError(
                f"TaskManager event loop not available or not responsive for submit_and_wait "
                f"(coroutine: '{coro_name}'). Startup failure: {e_get_loop_fail}"
            ) from e_get_loop_fail

        # Check if called from the loop thread itself.
        try:
            if asyncio.get_running_loop() is loop:
                err_msg = (
                    f"submit_and_wait cannot be called from within the TaskManager's own event loop thread "
                    f"(coroutine: '{coro_name}') as it would cause a deadlock by blocking the loop "
                    "it needs to complete the task."
                )
                logger.error(err_msg)
                raise RuntimeError(err_msg)
        except RuntimeError as e_check_loop_thread:
            # This 'except' handles two cases from asyncio.get_running_loop():
            # 1. If it's our specific RuntimeError from the 'if' block above: re-raise it.
            if "submit_and_wait cannot be called from within" in str(e_check_loop_thread):
                raise e_check_loop_thread
            # 2. If `asyncio.get_running_loop()` raises "no running event loop":
            #    This is expected if submit_and_wait is called from a non-asyncio thread.
            elif "no running event loop" in str(e_check_loop_thread).lower():
                logger.debug(f"submit_and_wait: Called from a non-loop thread for '{coro_name}', which is correct. Proceeding.")
            else: # pragma: no cover
                # Any other RuntimeError from get_running_loop() is unexpected.
                logger.error(f"submit_and_wait: Unexpected RuntimeError during running loop check for '{coro_name}': {e_check_loop_thread}")
                raise # Re-raise other unexpected RuntimeErrors

        logger.debug(f"submit_and_wait: Submitting coroutine '{coro_name}' to event loop thread via run_coroutine_threadsafe.")
        try:
            # asyncio.run_coroutine_threadsafe schedules the coroutine on the loop
            # and returns a concurrent.futures.Future that the current thread can wait on.
            cf_future = asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e_run_cts_fail:  # pragma: no cover
            # This could happen if the loop was closed between get_loop() and here,
            # or other low-level asyncio errors during scheduling.
            logger.exception(f"submit_and_wait: asyncio.run_coroutine_threadsafe failed for '{coro_name}': {e_run_cts_fail}")
            raise CoreTaskSubmissionError(
                f"Failed to schedule coroutine '{coro_name}' on loop thread via run_coroutine_threadsafe: {e_run_cts_fail}",
                original_exception=e_run_cts_fail
            ) from e_run_cts_fail

        # Main thread polls the concurrent.futures.Future for completion.
        # The polling allows responsiveness to KeyboardInterrupt in the main thread.
        logger.debug(
            f"submit_and_wait: Main thread (TID: {threading.get_ident()}) now polling "
            f"concurrent.futures.Future for '{coro_name}' completion."
        )
        try:
            while not cf_future.done():
                try:
                    # Attempt to get the result with a short timeout.
                    # If future is done, this returns/raises immediately.
                    # If not done, it raises concurrent.futures.TimeoutError.
                    return cf_future.result(timeout=_FUTURE_WAIT_POLL_INTERVAL)
                except concurrent.futures.TimeoutError:
                    # This is the expected timeout for polling, just continue the loop.
                    pass
                # KeyboardInterrupt during cf_future.result() propagates to outer try.

            # If the loop finishes because cf_future.done() is true, get final result/exception.
            return cf_future.result() # This won't block if future is truly done.

        except KeyboardInterrupt:  # pragma: no cover
            logger.info(
                f"submit_and_wait: KeyboardInterrupt received during polling for '{coro_name}' result. "
                "Signaling TaskManager shutdown."
            )
            self.signal_shutdown() # Initiate shutdown of the TaskManager and its loop.

            # Attempt to cancel the concurrent.futures.Future.
            if not cf_future.done():
                if cf_future.cancel():
                    logger.debug(f"submit_and_wait: concurrent.futures.Future for '{coro_name}' was cancelled due to KeyboardInterrupt.")
                else:
                    logger.debug(
                        f"submit_and_wait: concurrent.futures.Future for '{coro_name}' could not be cancelled "
                        "(it may have already started running or completed)."
                    )
            raise # Re-raise KeyboardInterrupt.
        except concurrent.futures.CancelledError:  # pragma: no cover
            # Occurs if cf_future.result() is called on a successfully cancelled future.
            logger.info(f"submit_and_wait: Coroutine '{coro_name}''s future was cancelled (likely due to shutdown signal or KeyboardInterrupt).")
            # Propagate as asyncio.CancelledError for consistency if this is part of an async chain.
            raise asyncio.CancelledError(f"Coroutine '{coro_name}' execution was cancelled.") from None
        except Exception as e_coro_exception:
            # Catches exceptions *raised by the coroutine itself* and set on cf_future.
            logger.debug(f"submit_and_wait: Coroutine '{coro_name}' raised an exception: {type(e_coro_exception).__name__}: {e_coro_exception}")
            raise # Re-raise the original exception from the coroutine.


    def signal_shutdown(self) -> None:
        """Signals the event loop (and synchronous waiters) to shut down."""
        with self._lock: # Protect access to loop and event attributes
            loop_ref = self._loop
            async_shutdown_event_ref = self._shutdown_requested_event_for_loop
            sync_shutdown_event_is_set = self._sync_shutdown_wait_event.is_set() # Check before trying to set

            # Signal the asyncio event for the loop thread
            if loop_ref and not loop_ref.is_closed() and \
               async_shutdown_event_ref and not async_shutdown_event_ref.is_set():
                logger.info("signal_shutdown: Signaling event loop to shutdown via _shutdown_requested_event_for_loop.set().")
                try:
                    # Schedules .set() to be called in the loop thread.
                    loop_ref.call_soon_threadsafe(async_shutdown_event_ref.set)
                except RuntimeError as e_schedule_set: # pragma: no cover
                    # This can happen if the loop is closing/closed just as we try to schedule.
                    logger.warning(f"signal_shutdown: Could not schedule shutdown event set on loop (already closing/closed?): {e_schedule_set}")
            elif not (loop_ref and not loop_ref.is_closed()): # pragma: no cover
                 logger.debug("signal_shutdown: Loop not active/initialized for signaling asyncio shutdown event.")
            else: # Event already set or loop_ref/event_ref is None
                 logger.debug("signal_shutdown: Asyncio shutdown event already set, or loop/event not ready for signaling.")

            # Signal the threading.Event for synchronous waiters (like wait_for_shutdown)
            if not sync_shutdown_event_is_set:
                logger.info("signal_shutdown: Signaling synchronous shutdown event (_sync_shutdown_wait_event).")
                self._sync_shutdown_wait_event.set()
            else:
                logger.debug("signal_shutdown: Synchronous shutdown event (_sync_shutdown_wait_event) was already set.")


    def wait_for_shutdown(self) -> None:
        """Blocks the current (non-loop) thread until shutdown is completed.

        This involves waiting for the shutdown signal and then ensuring the
        event loop thread has fully terminated.
        """
        if not self._loop_creation_attempted: # Check if ensure_loop_running was ever called
            logger.debug("wait_for_shutdown called but loop creation was never attempted. Returning immediately.")
            return

        # Check current running state. If not running but creation was attempted,
        # it might have failed startup or shut down prematurely.
        try:
            # is_loop_running checks thread aliveness and _sync_loop_set_confirm_event
            if not self.is_loop_running() and self._loop_creation_attempted:
                 logger.warning(
                    "wait_for_shutdown: Loop not actively running (or startup failed), "
                    "but proceeding to wait for synchronous shutdown signal as creation was attempted."
                )
        except CoreTaskManagerError as e_check_running: # pragma: no cover
            # This might happen if is_loop_running itself encounters an issue (e.g., _lock issues).
            logger.warning(
                f"TaskManager error during pre-wait check in wait_for_shutdown: {e_check_running}. "
                "Shutdown may not proceed as expected if loop was not properly started."
            )

        logger.info("wait_for_shutdown: Main thread blocking on _sync_shutdown_wait_event...")
        self._sync_shutdown_wait_event.wait() # Blocks until signal_shutdown sets this
        logger.info("wait_for_shutdown: Main thread unblocked from _sync_shutdown_wait_event (signal received).")

        # After sync event is set, ensure the loop thread itself has terminated.
        thread_to_join_ref = None
        with self._lock: # Get thread reference under lock
            thread_to_join_ref = self._loop_thread

        if thread_to_join_ref and thread_to_join_ref.is_alive():
            logger.debug(f"wait_for_shutdown: Waiting for event loop thread (TID: {thread_to_join_ref.ident}) to join...")
            thread_to_join_ref.join(timeout=_LOOP_JOIN_TIMEOUT)
            if thread_to_join_ref.is_alive(): # pragma: no cover
                logger.warning(
                    f"Event loop thread (TID: {thread_to_join_ref.ident}) did not join within "
                    f"{_LOOP_JOIN_TIMEOUT}s timeout. It might be stuck."
                )
            else:
                logger.debug(f"Event loop thread (TID: {thread_to_join_ref.ident}) joined successfully.")
        elif thread_to_join_ref: # Thread object exists but is_alive() is false
             logger.debug(f"Event loop thread (TID: {thread_to_join_ref.ident}) was already finished before join attempt.") # pragma: no cover
        else: # thread_to_join_ref is None
             logger.debug("No event loop thread reference found to join (was it ever started or already cleaned up?).") # pragma: no cover

        # Final cleanup of attributes related to the now-stopped loop/thread
        with self._lock:
            self._loop_thread = None # Clear thread reference
            # Only set _loop to None if thread is confirmed not alive (or no thread ref),
            # otherwise _run_loop_in_thread's finally block is responsible for closing it.
            if not (thread_to_join_ref and thread_to_join_ref.is_alive()):
                if self._loop and not self._loop.is_closed(): # pragma: no cover
                    logger.warning("wait_for_shutdown: Loop object exists but thread is gone/unjoinable. Explicitly closing loop from main thread (best effort).")
                    try: self._loop.close()
                    except Exception as e_close_fallback: logger.error(f"Error during fallback loop close: {e_close_fallback}")
                self._loop = None # Loop is closed and thread joined/gone
            self._loop_creation_attempted = False # Reset for potential re-initiation (unlikely for singleton)
            self._shutdown_requested_event_for_loop = None
            self._loop_set_and_ready_to_run_event = None # Loop thread clears its own instance of this on exit
            # _sync_loop_set_confirm_event is cleared by ensure_loop_running on new attempt
        logger.info("CPythonTaskManager wait_for_shutdown complete.")


    async def wait_for_shutdown_async(self) -> None:
        """Asynchronously waits for the shutdown signal (asyncio.Event).

        This is typically used in Pyodide or fully asyncio CPython applications.
        It waits for `_shutdown_requested_event_for_loop` which is set by
        `signal_shutdown`.
        """
        # Ensure loop and its associated shutdown event are initialized.
        # ensure_loop_running() sets up self._loop and _run_loop_in_thread sets up
        # self._shutdown_requested_event_for_loop on that loop.
        if not self._shutdown_requested_event_for_loop: # pragma: no cover
            try:
                self.ensure_loop_running() # Attempt to initialize if called prematurely.
            except CoreTaskManagerError as e_init_fail:
                 raise CoreLoopNotRunningError(
                    "Cannot wait_for_shutdown_async: TaskManager loop/shutdown event not initialized "
                    f"and failed to initialize. Original error: {e_init_fail}"
                ) from e_init_fail

            if not self._shutdown_requested_event_for_loop: # Still None after ensure_loop_running
                 raise CoreLoopNotRunningError( # Should be caught by ensure_loop_running failing
                    "Shutdown event (asyncio.Event) not initialized for async wait even after ensure_loop_running."
                )

        logger.info("wait_for_shutdown_async: Asynchronously waiting for shutdown signal (asyncio.Event)...")
        await self._shutdown_requested_event_for_loop.wait()
        logger.info("wait_for_shutdown_async: Asyncio shutdown event received.")
        # Note: This async wait only waits for the signal.
        # The actual loop thread termination and resource cleanup (for CPythonTaskManager)
        # are primarily managed by the synchronous wait_for_shutdown() if it's called,
        # or by the _run_loop_in_thread's finally block.
        # For a fully async app, the entity calling this might also be responsible for
        # ensuring the TaskManager's resources are released if it started the loop.