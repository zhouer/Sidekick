import asyncio
import threading
import time
import unittest
import logging
import warnings

from sidekick.core.cpython_task_manager import CPythonTaskManager, _TASK_REF_TIMEOUT_SECONDS
from sidekick.core.exceptions import CoreLoopNotRunningError, CoreTaskSubmissionError, CoreTaskManagerError


class TestCPythonTaskManager(unittest.TestCase):
    """
    Tests for the CPythonTaskManager implementation.
    """

    def setUp(self):
        self.tm = CPythonTaskManager()
        self.assertFalse(self.tm.is_loop_running(), "TaskManager loop should not be running at start of test.")

    def tearDown(self):
        if self.tm and self.tm.is_loop_running():
            self.tm.signal_shutdown()
            self.tm.wait_for_shutdown()
        if self.tm:
            self.assertFalse(self.tm.is_loop_running(), "TaskManager loop should be stopped after teardown.")

    def test_initial_state(self):
        self.assertFalse(self.tm.is_loop_running())
        self.assertIsNone(self.tm._loop)
        self.assertIsNone(self.tm._loop_thread)

    def test_ensure_loop_running_starts_loop(self):
        self.tm.ensure_loop_running()
        self.assertTrue(self.tm.is_loop_running())
        self.assertIsNotNone(self.tm._loop)
        self.assertTrue(self.tm._loop.is_running()) # type: ignore
        self.assertIsNotNone(self.tm._loop_thread)
        self.assertTrue(self.tm._loop_thread.is_alive()) # type: ignore

    def test_ensure_loop_running_idempotent(self):
        self.tm.ensure_loop_running()
        loop_id_first = id(self.tm.get_loop())
        thread_id_first = self.tm._loop_thread.ident if self.tm._loop_thread else None # type: ignore

        self.tm.ensure_loop_running()
        self.assertTrue(self.tm.is_loop_running())
        self.assertEqual(id(self.tm.get_loop()), loop_id_first)
        self.assertEqual(self.tm._loop_thread.ident if self.tm._loop_thread else None, thread_id_first) # type: ignore

    def test_get_loop_starts_loop_if_not_running(self):
        loop = self.tm.get_loop()
        self.assertTrue(self.tm.is_loop_running())
        self.assertIsInstance(loop, asyncio.AbstractEventLoop)
        self.assertTrue(loop.is_running())

    async def _simple_coro(self, delay=0.01, result="done"):
        await asyncio.sleep(delay)
        return result

    async def _coro_that_raises(self, exc_type=ValueError, msg="Test error"):
        await asyncio.sleep(0.01)
        raise exc_type(msg)

    def test_submit_task_from_main_thread(self):
        self.tm.ensure_loop_running()
        coro_to_run = self._simple_coro(result="task_submitted")
        task_ref = self.tm.submit_task(coro_to_run)
        self.assertIsInstance(task_ref, asyncio.Task)

        async def waiter(task_to_await):
            return await task_to_await
        result = self.tm.submit_and_wait(waiter(task_ref))
        self.assertEqual(result, "task_submitted")

    def test_submit_task_from_loop_thread(self):
        async def coro_submitter():
            inner_task = self.tm.submit_task(self._simple_coro(result="inner_done"))
            self.assertIsInstance(inner_task, asyncio.Task)
            return await inner_task
        result = self.tm.submit_and_wait(coro_submitter())
        self.assertEqual(result, "inner_done")

    def test_submit_and_wait_from_main_thread(self):
        result = self.tm.submit_and_wait(self._simple_coro(result="wait_success"))
        self.assertEqual(result, "wait_success")

    def test_submit_and_wait_propagates_exception(self):
        with self.assertRaisesRegex(ValueError, "Test error from wait"):
            self.tm.submit_and_wait(self._coro_that_raises(ValueError, "Test error from wait"))

    def test_submit_and_wait_raises_if_called_from_loop_thread(self):
        async def coro_caller():
            # Catch the RuntimeWarning about unawaited coroutine specifically for this test
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always", RuntimeWarning) # Make sure we see it
                with self.assertRaisesRegex(RuntimeError, "submit_and_wait cannot be called from the TaskManager's event loop thread"):
                    self.tm.submit_and_wait(self._simple_coro()) # This should raise
                # Check if the specific warning was issued
                unawaited_coro_warning_found = False
                for warning_msg in w:
                    if issubclass(warning_msg.category, RuntimeWarning) and \
                       "was never awaited" in str(warning_msg.message) and \
                       "_simple_coro" in str(warning_msg.message):
                        unawaited_coro_warning_found = True
                        break
                self.assertTrue(unawaited_coro_warning_found, "Expected RuntimeWarning for unawaited _simple_coro")
            return "checked_runtime_error_in_loop_call"

        result = self.tm.submit_and_wait(coro_caller())
        self.assertEqual(result, "checked_runtime_error_in_loop_call")

    def test_shutdown_sequence(self):
        self.tm.ensure_loop_running()
        self.assertTrue(self.tm.is_loop_running())
        long_task_finished_event = asyncio.Event()

        async def long_running_coro():
            nonlocal long_task_finished_event
            logging.debug("long_running_coro started")
            try:
                await asyncio.sleep(0.5)
                logging.debug("long_running_coro finished sleep")
                long_task_finished_event.set()
                return "long_task_done"
            except asyncio.CancelledError:
                logging.debug("long_running_coro was cancelled")
                raise # Re-raise CancelledError

        task = self.tm.submit_task(long_running_coro())
        time.sleep(0.05) # Give task a moment to start

        self.tm.signal_shutdown()
        self.assertTrue(self.tm._shutdown_event_sync.is_set()) # type: ignore

        self.tm.wait_for_shutdown()
        self.assertFalse(self.tm.is_loop_running())
        self.assertIsNone(self.tm._loop_thread)
        self.assertIsNone(self.tm._loop)

        self.assertTrue(task.done())
        if long_task_finished_event.is_set(): # type: ignore
            # If event is set, task should have completed normally before cancellation took full effect
            self.assertEqual(task.result(), "long_task_done")
            self.assertFalse(task.cancelled())
        else:
            # If event is not set, task was cancelled during its sleep
            self.assertTrue(task.cancelled(), "If task didn't set finished_event, it should have been cancelled.")
            with self.assertRaises(asyncio.CancelledError):
                task.result() # Accessing result of a cancelled task raises CancelledError

    def test_wait_for_shutdown_without_start(self):
        self.tm.signal_shutdown()
        self.tm.wait_for_shutdown()
        self.assertFalse(self.tm.is_loop_running())

    def test_multiple_shutdown_signals(self):
        self.tm.ensure_loop_running()
        self.tm.signal_shutdown()
        self.tm.signal_shutdown()
        self.assertTrue(self.tm._shutdown_event_sync.is_set()) # type: ignore
        self.tm.wait_for_shutdown()
        self.assertFalse(self.tm.is_loop_running())

    async def _wait_on_async_shutdown_event(self):
        if self.tm._shutdown_event_async: # type: ignore
            await self.tm._shutdown_event_async.wait() # type: ignore
            return "async_shutdown_received"
        return "async_event_not_ready"

    def test_wait_for_shutdown_async(self):
        self.tm.ensure_loop_running()
        waiter_coro = self._wait_on_async_shutdown_event()
        waiter_task_ref = self.tm.submit_task(waiter_coro)

        time.sleep(0.05)
        self.assertFalse(waiter_task_ref.done())

        self.tm.signal_shutdown()

        async def waiter(task_to_await):
            return await task_to_await
        result = self.tm.submit_and_wait(waiter(waiter_task_ref))
        self.assertEqual(result, "async_shutdown_received")

        self.tm.wait_for_shutdown()
        self.assertFalse(self.tm.is_loop_running())

    def test_task_submission_timeout(self):
        self.tm.ensure_loop_running()
        loop = self.tm.get_loop()

        block_duration = _TASK_REF_TIMEOUT_SECONDS + 0.2
        sync_block_done_event = threading.Event()
        sync_block_started_event = threading.Event()

        def long_sync_block_in_loop_thread(duration, started_event, done_event):
            logging.debug(f"Loop thread: long_sync_block_in_loop_thread starting for {duration}s.")
            started_event.set()
            time.sleep(duration)
            logging.debug("Loop thread: long_sync_block_in_loop_thread finished sleep.")
            done_event.set()

        loop.call_soon_threadsafe(
            long_sync_block_in_loop_thread,
            block_duration,
            sync_block_started_event,
            sync_block_done_event
        )

        if not sync_block_started_event.wait(timeout=1.0):
            self.fail("The blocking function did not signal start in the loop thread.")
        logging.debug("Main thread: Blocking function has started. Attempting submit_task.")

        with self.assertRaisesRegex(CoreTaskSubmissionError, "Timeout .* waiting for asyncio.Task reference"):
            self.tm.submit_task(self._simple_coro(delay=0.01))

        logging.debug("Main thread: Waiting for long_sync_block_in_loop_thread to complete for cleanup.")
        if not sync_block_done_event.wait(timeout=block_duration + 1.0):
            logging.warning("Main thread: Timeout waiting for the blocking function to complete after test.")
            if self.tm.is_loop_running(): self.tm.signal_shutdown() # Help teardown if stuck


    def test_loop_startup_failure_exception_propagation(self):
        original_new_event_loop = asyncio.new_event_loop
        def mock_new_event_loop_raiser():
            raise RuntimeError("Mocked new_event_loop failure")

        asyncio.new_event_loop = mock_new_event_loop_raiser
        try:
            with self.assertRaises(CoreTaskManagerError) as cm_outer: # Catch base CoreTaskManagerError
                self.tm.ensure_loop_running()

            # Now check the properties of the caught exception
            self.assertIsNotNone(cm_outer.exception.original_exception, "Original exception should be attached.")
            self.assertIsInstance(cm_outer.exception.original_exception, RuntimeError)
            self.assertIn("Mocked new_event_loop failure", str(cm_outer.exception.original_exception))
            self.assertIn("Event loop thread failed during startup.", str(cm_outer.exception))

        finally:
            asyncio.new_event_loop = original_new_event_loop
        self.assertFalse(self.tm.is_loop_running())


    def test_active_tasks_tracking_and_cancellation(self):
        self.tm.ensure_loop_running()
        task_cancelled_event = asyncio.Event()
        task_started_event = asyncio.Event()

        async def tracked_coro():
            nonlocal task_started_event, task_cancelled_event
            logging.debug("tracked_coro: Started.")
            task_started_event.set()
            try:
                await asyncio.sleep(5)
                logging.debug("tracked_coro: Finished sleep (should have been cancelled).")
            except asyncio.CancelledError:
                logging.debug("tracked_coro: Successfully cancelled.")
                task_cancelled_event.set()
                raise
            return "completed_unexpectedly"

        task1 = self.tm.submit_task(tracked_coro())
        self.assertIn(task1, self.tm._active_tasks) # type: ignore

        self.tm.submit_and_wait(task_started_event.wait())
        logging.debug("Main thread: tracked_coro has started.")

        self.tm.signal_shutdown()
        self.tm.wait_for_shutdown()

        self.assertTrue(task1.done())
        self.assertTrue(task1.cancelled())
        # To verify task_cancelled_event was set, it would need to be a threading.Event
        # or checked before the loop fully closes in _perform_loop_cleanup.
        # For this test, task1.cancelled() is the primary check.
        self.assertFalse(self.tm._active_tasks, "Active tasks set should be empty after shutdown.") # type: ignore

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO, # Changed to INFO to reduce noise from DEBUG
        format="%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s"
    )
    unittest.main()
