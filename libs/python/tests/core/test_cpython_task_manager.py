"""Unit tests for CPythonTaskManager in sidekick.core."""

import unittest
import asyncio
import threading
import time
import logging
import concurrent.futures
from unittest.mock import patch, MagicMock, ANY

from sidekick.core.cpython_task_manager import CPythonTaskManager, _LOOP_START_TIMEOUT, _LOOP_JOIN_TIMEOUT
from sidekick.core.exceptions import CoreLoopNotRunningError, CoreTaskManagerError, CoreTaskSubmissionError

logger = logging.getLogger(__name__)

# A simple coroutine for testing
async def simple_coro(duration=0.01, value_to_return=42):
    """A test coroutine that sleeps and returns a value or raises an exception."""
    await asyncio.sleep(duration)
    if isinstance(value_to_return, Exception):
        raise value_to_return
    return value_to_return


class TestCPythonTaskManager(unittest.TestCase):

    def setUp(self):
        """Set up for each test case."""
        self.tm = CPythonTaskManager()
        # Ensure any previous test's TM thread is fully shut down before starting a new one.
        # This is tricky as TM is a singleton in factories, but here we test direct instantiation.
        # If tests interfere, we might need a more robust global cleanup or factory reset.

    def tearDown(self):
        """Clean up after each test case."""
        # Ensure the task manager is shut down to release resources, especially the thread.
        if self.tm.is_loop_running():
            logger = logging.getLogger(__name__)  # Use a specific logger
            logger.debug(f"tearDown: Loop for TM {id(self.tm)} still running. Signaling shutdown.")
            self.tm.signal_shutdown()
            # In tests, we want to ensure the thread actually exits.
            # wait_for_shutdown() handles the join.
            try:
                # Use a shorter timeout for test teardown join to avoid hanging tests
                # if something went wrong in the test itself.
                original_join_timeout = self.tm._LOOP_JOIN_TIMEOUT  # Accessing internal for test
                self.tm._LOOP_JOIN_TIMEOUT = 1.0  # Temporarily shorten
                self.tm.wait_for_shutdown()
                self.tm._LOOP_JOIN_TIMEOUT = original_join_timeout  # Restore
                logger.debug(f"tearDown: TM {id(self.tm)} shutdown complete.")
            except Exception as e:  # pragma: no cover
                logger.error(f"tearDown: Error during TM shutdown: {e}")
        # Allow some time for thread to actually die if join timed out or wasn't perfect
        if self.tm._loop_thread and self.tm._loop_thread.is_alive():  # pragma: no cover
            time.sleep(0.1)
            if self.tm._loop_thread.is_alive():
                logger.warning(f"tearDown: TM {id(self.tm)} loop thread still alive after wait_for_shutdown.")

    def test_initial_state(self):
        """Test the initial state of the TaskManager."""
        self.assertIsNone(self.tm._loop, "Initial loop should be None.")
        self.assertIsNone(self.tm._loop_thread, "Initial loop_thread should be None.")
        self.assertFalse(self.tm._loop_creation_attempted, "Initial _loop_creation_attempted should be False.")
        self.assertFalse(self.tm.is_loop_running(), "is_loop_running should be False initially.")

    def test_ensure_loop_running_starts_loop_and_thread(self):
        """Test that ensure_loop_running starts the loop and thread correctly."""
        self.assertFalse(self.tm.is_loop_running())
        self.tm.ensure_loop_running()
        self.assertTrue(self.tm.is_loop_running(), "Loop should be running after ensure_loop_running.")
        self.assertIsNotNone(self.tm._loop, "Loop object should be created.")
        self.assertTrue(self.tm._loop.is_running(), "Asyncio loop internal state should be running.")
        self.assertIsNotNone(self.tm._loop_thread, "Loop thread object should be created.")
        self.assertTrue(self.tm._loop_thread.is_alive(), "Loop thread should be alive.")
        self.assertTrue(self.tm._loop_creation_attempted, "_loop_creation_attempted should be True.")
        self.assertTrue(self.tm._loop_is_actually_running_event.is_set(),
                        "_loop_is_actually_running_event should be set.")

    def test_ensure_loop_running_idempotent(self):
        """Test that multiple calls to ensure_loop_running are idempotent."""
        self.tm.ensure_loop_running()
        loop_id_first = id(self.tm._loop)
        thread_id_first = self.tm._loop_thread.ident if self.tm._loop_thread else None

        self.tm.ensure_loop_running()  # Second call
        self.assertTrue(self.tm.is_loop_running())
        self.assertEqual(id(self.tm._loop), loop_id_first, "Loop object should not be recreated.")
        self.assertEqual(self.tm._loop_thread.ident, thread_id_first, "Loop thread should not be recreated.")

    def test_get_loop_returns_running_loop(self):
        """Test get_loop() returns the correct loop when running."""
        self.tm.ensure_loop_running()
        loop = self.tm.get_loop()
        self.assertIsNotNone(loop)
        self.assertTrue(loop.is_running())
        self.assertIs(loop, self.tm._loop)

    def test_get_loop_raises_if_not_started_by_ensure(self):
        """Test get_loop() behavior if ensure_loop_running wasn't successful (hard to test directly)."""
        # This case is hard to test perfectly because get_loop() calls ensure_loop_running().
        # If ensure_loop_running() fails, it raises CoreTaskManagerError.
        # We can mock ensure_loop_running to simulate it not setting up the loop.
        with patch.object(self.tm, 'ensure_loop_running', side_effect=CoreTaskManagerError("Simulated ensure failure")):
            with self.assertRaises(CoreTaskManagerError):
                self.tm.get_loop()

        # Test if loop is None after a failed ensure_loop_running (more direct if possible)
        # For now, rely on ensure_loop_running's own error raising.

    def test_submit_task_executes_coroutine(self):
        """Test submitting a task from the main thread and waiting for its completion."""
        self.tm.ensure_loop_running()
        logger.debug("test_submit_task_executes_coroutine: Starting")
        async_result_container = []

        async def coro_to_run():
            logger.debug("coro_to_run: Starting execution")
            res = await simple_coro(duration=0.05, value_to_return=123)
            async_result_container.append(res)
            logger.debug("coro_to_run: Finished execution")
            return res  # Also return the result for task.result() check if needed

        logger.debug("test_submit_task_executes_coroutine: Submitting coro_to_run via submit_task")
        # 'task' is an asyncio.Task running in the TM's loop thread
        task = self.tm.submit_task(coro_to_run())
        self.assertIsInstance(task, asyncio.Task, "submit_task should return an asyncio.Task.")

        # --- CORRECTED WAITING MECHANISM ---
        # To wait for 'task' (an asyncio.Task in another thread's loop) from the main thread:
        # We submit another coroutine to the loop that will await 'task'.
        async def _wait_for_submitted_task(task_to_await: asyncio.Task):
            logger.debug(f"_wait_for_submitted_task: Awaiting task {task_to_await.get_name()}")
            try:
                result = await task_to_await
                logger.debug(
                    f"_wait_for_submitted_task: Task {task_to_await.get_name()} completed with result: {result}")
                return result
            except asyncio.CancelledError:  # pragma: no cover
                logger.info(f"_wait_for_submitted_task: Task {task_to_await.get_name()} was cancelled.")
                raise
            except Exception as e_inner:  # pragma: no cover
                logger.error(
                    f"_wait_for_submitted_task: Task {task_to_await.get_name()} raised an exception: {e_inner}")
                raise

        logger.debug(
            "test_submit_task_executes_coroutine: Submitting _wait_for_submitted_task via run_coroutine_threadsafe")
        # cf_waiter is a concurrent.futures.Future, its result is the result of _wait_for_submitted_task
        cf_waiter = asyncio.run_coroutine_threadsafe(_wait_for_submitted_task(task), self.tm.get_loop())

        returned_by_waiter = None
        try:
            # Wait for _wait_for_submitted_task (which waits for 'task') to complete
            logger.debug("test_submit_task_executes_coroutine: Main thread waiting on cf_waiter.result()")
            returned_by_waiter = cf_waiter.result(timeout=1.0)
            logger.debug(f"test_submit_task_executes_coroutine: cf_waiter.result() returned: {returned_by_waiter}")
        except concurrent.futures.TimeoutError:  # pragma: no cover
            self.fail("Coroutine submitted via submit_task (and its waiter) did not complete in time.")
        except asyncio.CancelledError:  # pragma: no cover
            self.fail("Waiting task was unexpectedly cancelled.")
        # --- END CORRECTION ---

        self.assertTrue(task.done(), "Task (coro_to_run) should be done.")
        self.assertFalse(task.cancelled(), "Task (coro_to_run) should not be cancelled.")
        if task.exception():  # pragma: no cover
            logger.error(f"Task (coro_to_run) had an exception: {task.exception()}")
        self.assertIsNone(task.exception(), f"Task (coro_to_run) should not have an exception: {task.exception()}")

        self.assertEqual(len(async_result_container), 1, "Coroutine should have appended one result.")
        self.assertEqual(async_result_container[0], 123, "Coroutine result mismatch (from container).")
        self.assertEqual(task.result(), 123, "Task result() mismatch.")  # asyncio.Task.result()
        self.assertEqual(returned_by_waiter, 123, "Result from waiter coroutine mismatch.")
        logger.debug("test_submit_task_executes_coroutine: Finished successfully")

    def test_submit_task_from_loop_thread_itself(self):
        """Test submitting a task when submit_task is called from the loop thread."""
        self.tm.ensure_loop_running()
        loop = self.tm.get_loop()

        async_result_container = []
        task_ref_from_submit = None

        async def coro_submitter():
            nonlocal task_ref_from_submit

            # This coro_to_run will be scheduled by submit_task called from *this* (coro_submitter) context
            async def coro_to_run_inner():
                res = await simple_coro(value_to_return="from_loop_thread")
                async_result_container.append(res)

            # Calling submit_task from within a coroutine running on the TM's loop
            task_ref_from_submit = self.tm.submit_task(coro_to_run_inner())
            await task_ref_from_submit  # Wait for the inner task to complete

        # Run coro_submitter using submit_and_wait to block main test thread
        self.tm.submit_and_wait(coro_submitter())

        self.assertIsNotNone(task_ref_from_submit, "Task reference should be captured.")
        self.assertTrue(task_ref_from_submit.done())  # type: ignore[union-attr]
        self.assertEqual(async_result_container, ["from_loop_thread"])

    def test_submit_and_wait_returns_value(self):
        """Test submit_and_wait successfully returns a value."""
        self.tm.ensure_loop_running()
        expected_value = "success_val"
        result = self.tm.submit_and_wait(simple_coro(value_to_return=expected_value))
        self.assertEqual(result, expected_value)

    def test_submit_and_wait_propagates_exception(self):
        """Test submit_and_wait propagates exceptions from the coroutine."""
        self.tm.ensure_loop_running()
        custom_exception = ValueError("Test Coro Error")
        with self.assertRaises(ValueError) as cm:
            self.tm.submit_and_wait(simple_coro(value_to_return=custom_exception))
        self.assertIs(cm.exception, custom_exception, "Specific exception instance should be propagated.")

    def test_submit_and_wait_from_loop_thread_raises_error(self):
        """Test submit_and_wait raises RuntimeError if called from loop thread,
        and that the outer calling task completes."""
        self.tm.ensure_loop_running()

        # Use an asyncio.Event to signal from the coro_caller
        # This event must be created by/for the TM's loop.
        # We'll create it inside an async function submitted to the TM.

        event_holder = {}  # To hold the event created in the loop

        async def setup_event_coro():
            event_holder['did_raise_correctly_event'] = asyncio.Event()

        self.tm.submit_and_wait(setup_event_coro())  # Create event on the loop
        did_raise_correctly_event = event_holder['did_raise_correctly_event']

        async def coro_caller():
            logger.info("coro_caller: Entered")  # Changed from debug to info
            raised_expected_error = False
            try:
                logger.info("coro_caller: About to call inner submit_and_wait")
                self.tm.submit_and_wait(simple_coro(duration=0.001))
                logger.error("coro_caller: Inner submit_and_wait DID NOT RAISE an error!")  # pragma: no cover
            except RuntimeError as e:
                logger.info(f"coro_caller: Caught RuntimeError: {e}")  # Changed to info
                if "cannot be called from within the TaskManager's own event loop thread" in str(e):
                    logger.info("coro_caller: Correct RuntimeError caught.")
                    raised_expected_error = True
                else:  # pragma: no cover
                    logger.error(f"coro_caller: Caught RuntimeError, but wrong message: {e}")
            except Exception as e_other:  # pragma: no cover
                logger.error(f"coro_caller: Caught unexpected error: {type(e_other).__name__}: {e_other}")

            if raised_expected_error:
                logger.info("coro_caller: Setting did_raise_correctly_event")  # Changed to info
                if did_raise_correctly_event:  # Check if event exists
                    did_raise_correctly_event.set()
                else:  # pragma: no cover
                    logger.error("coro_caller: did_raise_correctly_event is None!")
            else:  # pragma: no cover
                logger.error("coro_caller: Expected RuntimeError was NOT caught or signaled!")
            logger.info("coro_caller: Exiting")  # Changed to info

        logger.debug("Main test: Submitting coro_caller via outer submit_and_wait")
        # This outer submit_and_wait runs coro_caller in the TM's loop.
        # It should complete successfully because coro_caller handles its internal exception.
        try:
            self.tm.submit_and_wait(coro_caller())
            logger.debug("Main test: Outer submit_and_wait(coro_caller) completed.")
        except Exception as e_outer_saw:  # pragma: no cover
            # This should not happen if coro_caller handles its exceptions
            logger.error(
                f"Main test: Outer submit_and_wait(coro_caller) raised an unexpected error: {e_outer_saw}")
            self.fail(f"Outer submit_and_wait(coro_caller) failed: {e_outer_saw}")

        # Now, check if the event was set from within coro_caller using another submit_and_wait
        logger.debug("Main test: Submitting check_event to verify did_raise_correctly_event")

        async def check_event_status():
            logger.debug("check_event_status: Waiting for did_raise_correctly_event")
            try:
                await asyncio.wait_for(did_raise_correctly_event.wait(), timeout=1.0)
                logger.info("check_event_status: did_raise_correctly_event was set.")
                return True
            except asyncio.TimeoutError:  # pragma: no cover
                logger.error("check_event_status: Timeout waiting for did_raise_correctly_event.")
                return False

        try:
            event_was_set = self.tm.submit_and_wait(check_event_status())
            self.assertTrue(event_was_set, "The expected RuntimeError was not caught and signaled by coro_caller.")
        except Exception as e_check_event:  # pragma: no cover
            logger.error(
                f"Main test: submit_and_wait(check_event_status) raised an unexpected error: {e_check_event}")
            self.fail(f"Checking event status failed: {e_check_event}")

        logger.debug("Main test: test_submit_and_wait_from_loop_thread_raises_error finished.")

    def test_shutdown_sequence(self):
        """Test the shutdown sequence: signal, wait, loop/thread termination."""
        self.tm.ensure_loop_running()
        self.assertTrue(self.tm.is_loop_running())

        # Submit a long-running (but cancellable) task to see if it gets cancelled
        long_task_cancelled_event = threading.Event()

        async def long_running_coro():
            try:
                await asyncio.sleep(5)  # Make it long enough to be cancelled
            except asyncio.CancelledError:  # pragma: no cover
                # This is expected if cancellation works
                long_task_cancelled_event.set()
                raise

        long_task = self.tm.submit_task(long_running_coro())

        # Signal shutdown from main thread
        self.tm.signal_shutdown()

        # Check events were set
        self.assertTrue(self.tm._sync_shutdown_wait_event.is_set(), "_sync_shutdown_wait_event not set by signal.")
        # Checking _shutdown_requested_event_for_loop requires being on the loop or careful inter-thread comms.
        # We'll infer its state from wait_for_shutdown_async or behavior of the loop thread.

        # wait_for_shutdown should block and then return once loop thread is joined
        self.tm.wait_for_shutdown()

        self.assertFalse(self.tm.is_loop_running(), "Loop should not be running after wait_for_shutdown.")
        self.assertIsNone(self.tm._loop_thread,
                          "_loop_thread should be None after shutdown.")  # Check if _loop_thread is cleared
        self.assertIsNone(self.tm._loop, "_loop should be None after shutdown.")  # Check if _loop is cleared
        self.assertTrue(long_task_cancelled_event.is_set(), "Long running task was not cancelled during shutdown.")
        self.assertTrue(long_task.cancelled() or long_task.done(), "Long task should be cancelled or done.")

    def test_wait_for_shutdown_async(self):
        """Test the async version of waiting for shutdown."""
        self.tm.ensure_loop_running()

        async def run_waiter_and_signal():
            wait_task = asyncio.create_task(self.tm.wait_for_shutdown_async())
            await asyncio.sleep(0.05)  # Give waiter task a chance to start waiting
            self.assertFalse(wait_task.done(), "wait_for_shutdown_async should be waiting.")

            self.tm.signal_shutdown()  # Signal

            await asyncio.wait_for(wait_task, timeout=1.0)  # Wait for it to complete
            self.assertTrue(wait_task.done(), "wait_for_shutdown_async should be done after signal.")
            self.assertIsNone(wait_task.exception(), "wait_for_shutdown_async should not raise error.")

        self.tm.submit_and_wait(run_waiter_and_signal())
        # After this, the loop thread will also shut down due to the signal.
        self.tm.wait_for_shutdown()  # Clean up the TM fully for subsequent tests.

    def test_submit_and_wait_with_simple_async_inner_work(self):
        """Test submit_and_wait with a coro that does simple async work and returns."""
        self.tm.ensure_loop_running()
        logger.debug("test_saw_simple_async: Starting")

        async_result_container = []  # Using a list to pass result out of coro

        async def simple_worker_coro():
            logger.debug("simple_worker_coro: Starting sleep")
            await asyncio.sleep(0.05)  # Simulate some async work, slightly longer
            logger.debug("simple_worker_coro: Finished sleep, appending result")
            async_result_container.append("worker_done")
            return "worker_returned_value"

        logger.debug("test_saw_simple_async: Calling outer submit_and_wait")
        try:
            return_value = self.tm.submit_and_wait(simple_worker_coro())
            logger.debug(f"test_saw_simple_async: Outer submit_and_wait returned: {return_value}")

            self.assertEqual(return_value, "worker_returned_value")
            self.assertEqual(async_result_container, ["worker_done"])
        except Exception as e:  # pragma: no cover
            logger.error(f"test_saw_simple_async failed: {e}")
            self.fail(f"test_saw_simple_async failed unexpectedly: {e}")
        logger.debug("test_saw_simple_async: Finished")

    def test_VERY_SIMPLE_submit_and_wait_from_loop_thread_raises_error(self):
        """Extremely simplified test for the problematic scenario."""
        self.tm.ensure_loop_running()
        logger.info("test_VERY_SIMPLE_saw_from_loop: Starting")

        exception_caught_in_coro = None  # Use a simple list/dict to pass status out

        async def coro_caller_simplified():
            nonlocal exception_caught_in_coro
            logger.info("coro_caller_simplified: Entered")
            try:
                # This call is from the loop thread
                self.tm.submit_and_wait(simple_coro(duration=0.001))
                logger.error("coro_caller_simplified: Inner submit_and_wait DID NOT RAISE!")  # pragma: no cover
            except RuntimeError as e:
                logger.info(f"coro_caller_simplified: Caught expected RuntimeError: {e}")
                exception_caught_in_coro = e  # Store the exception
            except Exception as e_other:  # pragma: no cover
                logger.error(f"coro_caller_simplified: Caught unexpected error: {e_other}")
                exception_caught_in_coro = e_other
            logger.info("coro_caller_simplified: Exiting")
            return "coro_caller_simplified_done"  # Return a value

        # This outer submit_and_wait runs coro_caller_simplified in the TM's loop.
        # It should complete because coro_caller_simplified handles its internal exception.
        logger.info("test_VERY_SIMPLE_saw_from_loop: Calling outer submit_and_wait")
        try:
            result = self.tm.submit_and_wait(coro_caller_simplified())
            logger.info(f"test_VERY_SIMPLE_saw_from_loop: Outer submit_and_wait completed with result: {result}")
            self.assertEqual(result, "coro_caller_simplified_done")
            self.assertIsNotNone(exception_caught_in_coro)
            self.assertIn("cannot be called from within", str(exception_caught_in_coro))
        except Exception as e_outer:  # pragma: no cover
            logger.error(f"test_VERY_SIMPLE_saw_from_loop: Outer submit_and_wait failed: {e_outer}")
            self.fail(f"Outer submit_and_wait failed: {e_outer}")

        logger.info("test_VERY_SIMPLE_saw_from_loop: Finished")

    # More tests needed:
    # - Test _LOOP_START_TIMEOUT (e.g., if _run_loop_in_thread hangs before setting event) - Hard to mock.
    # - Test _GET_TASK_REF_TIMEOUT for submit_task (e.g., if _schedule_task_creation_in_loop hangs) - Hard.
    # - Test KeyboardInterrupt handling in submit_and_wait (requires more complex setup or focus in integration).


# It's good practice to set up logging for tests if the tested module uses logging.
if __name__ == '__main__':  # pragma: no cover
    logging.basicConfig(level=logging.DEBUG,
                        format="%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s")
    # Silence verbose websockets logger for these tests if it gets noisy from other parts
    # logging.getLogger("websockets").setLevel(logging.INFO)
    unittest.main()