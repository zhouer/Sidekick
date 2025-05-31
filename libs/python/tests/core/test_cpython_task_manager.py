"""Unit tests for CPythonTaskManager in sidekick.core."""

import unittest
import asyncio
import threading
import time
import logging
import concurrent.futures
from unittest.mock import patch, MagicMock

from sidekick.core.cpython_task_manager import (
    CPythonTaskManager,
    _LOOP_START_TIMEOUT,
    _PROBE_CORO_TIMEOUT,
    _LOOP_JOIN_TIMEOUT
)
from sidekick.core.exceptions import CoreLoopNotRunningError, CoreTaskManagerError, CoreTaskSubmissionError

logger = logging.getLogger("test_cpython_task_manager")
# (Keep existing logging setup)


# A simple coroutine for testing
async def simple_coro(duration=0.01, value_to_return=42):
    """A test coroutine that sleeps and returns a value or raises an exception."""
    logger.debug(f"simple_coro: Sleeping for {duration}s, will return/raise: {value_to_return}")
    try:
        await asyncio.sleep(duration)
        if isinstance(value_to_return, Exception):
            logger.debug(f"simple_coro: Raising exception {type(value_to_return).__name__}")
            raise value_to_return
        logger.debug(f"simple_coro: Returning value {value_to_return}")
        return value_to_return
    except asyncio.CancelledError:
        logger.debug("simple_coro: Was cancelled during sleep or operation.")
        raise


class TestCPythonTaskManager(unittest.TestCase):

    def setUp(self):
        """Set up for each test case."""
        logger.debug(f"--- Starting test: {self.id()} ---")
        self.tm = CPythonTaskManager()

    def tearDown(self):
        """Clean up after each test case."""
        logger.debug(f"--- Tearing down test: {self.id()} ---")
        if self.tm._loop_creation_attempted and self.tm.is_loop_running():
            logger.debug(f"tearDown: Loop for TM {id(self.tm)} still running. Signaling shutdown.")
            self.tm.signal_shutdown()
            try:
                with patch('sidekick.core.cpython_task_manager._LOOP_JOIN_TIMEOUT', 1.0): # Use a shorter timeout for test teardown
                     self.tm.wait_for_shutdown()
                logger.debug(f"tearDown: TM {id(self.tm)} shutdown complete.")
            except Exception as e:  # pragma: no cover
                logger.error(f"tearDown: Error during TM shutdown: {e}")

        if self.tm._loop_thread and self.tm._loop_thread.is_alive():  # pragma: no cover
            logger.warning(
                f"tearDown: TM {id(self.tm)} loop thread (TID: {self.tm._loop_thread.ident}) "
                "still alive after wait_for_shutdown. This might indicate a stuck thread."
            )
        else:
            logger.debug(f"tearDown: Loop thread for TM {id(self.tm)} is confirmed not alive or was not created.")
        logger.debug(f"--- Finished test: {self.id()} ---")

    # ... (test_initial_state, test_ensure_loop_running_starts_loop_and_thread_and_probes,
    #      test_ensure_loop_running_idempotent, test_get_loop_returns_running_loop,
    #      test_get_loop_raises_if_ensure_loop_fails remain the same) ...
    # Start of pasted unchanged tests
    def test_initial_state(self):
        """Test the initial state of the TaskManager."""
        logger.info("test_initial_state: Verifying initial TM attributes.")
        self.assertIsNone(self.tm._loop, "Initial self._loop should be None.")
        self.assertIsNone(self.tm._loop_thread, "Initial self._loop_thread should be None.")
        self.assertFalse(self.tm._loop_creation_attempted, "Initial self._loop_creation_attempted should be False.")
        self.assertFalse(self.tm.is_loop_running(), "is_loop_running should be False initially.")
        self.assertFalse(self.tm._sync_loop_set_confirm_event.is_set(), "_sync_loop_set_confirm_event should be clear.")

    def test_ensure_loop_running_starts_loop_and_thread_and_probes(self):
        """Test that ensure_loop_running starts the loop, thread, and completes probe."""
        logger.info("test_ensure_loop_running: Starting test.")
        self.assertFalse(self.tm.is_loop_running())

        self.tm.ensure_loop_running()

        logger.info("test_ensure_loop_running: ensure_loop_running completed. Verifying state.")
        self.assertTrue(self.tm.is_loop_running(), "Loop should be considered running after successful ensure_loop_running.")
        self.assertIsNotNone(self.tm._loop, "self._loop object should be created.")

        self.assertIsNotNone(self.tm._loop_thread, "Loop thread object should be created.")
        self.assertTrue(self.tm._loop_thread.is_alive(), "Loop thread should be alive.")
        self.assertTrue(self.tm._loop_creation_attempted, "self._loop_creation_attempted should be True.")

        self.assertTrue(self.tm._sync_loop_set_confirm_event.is_set(),
                        "_sync_loop_set_confirm_event should be set after ensure_loop_running.")
        logger.info("test_ensure_loop_running: Completed successfully.")

    def test_ensure_loop_running_idempotent(self):
        """Test that multiple calls to ensure_loop_running are idempotent."""
        logger.info("test_ensure_loop_running_idempotent: Starting.")
        self.tm.ensure_loop_running() # First call
        loop_id_first = id(self.tm._loop)
        thread_id_first = self.tm._loop_thread.ident if self.tm._loop_thread else None
        logger.info(f"test_ensure_loop_running_idempotent: First call done. Loop ID: {loop_id_first}, Thread ID: {thread_id_first}")

        self.tm.ensure_loop_running()  # Second call
        logger.info("test_ensure_loop_running_idempotent: Second call done. Verifying state.")
        self.assertTrue(self.tm.is_loop_running())
        self.assertEqual(id(self.tm._loop), loop_id_first, "Loop object should not be recreated on idempotent call.")
        self.assertIsNotNone(self.tm._loop_thread, "Loop thread should still exist.")
        self.assertEqual(self.tm._loop_thread.ident, thread_id_first, "Loop thread should not be recreated on idempotent call.")
        logger.info("test_ensure_loop_running_idempotent: Completed successfully.")


    def test_get_loop_returns_running_loop(self):
        """Test get_loop() returns the correct loop after ensure_loop_running."""
        logger.info("test_get_loop_returns_running_loop: Starting.")
        self.tm.ensure_loop_running()
        loop = self.tm.get_loop()

        self.assertIsNotNone(loop, "get_loop() should return a loop object.")
        self.assertIs(loop, self.tm._loop, "get_loop() should return the internally managed loop instance.")
        logger.info("test_get_loop_returns_running_loop: Completed successfully.")

    def test_get_loop_raises_if_ensure_loop_fails(self):
        """Test get_loop() raises error if ensure_loop_running (called internally) fails."""
        logger.info("test_get_loop_raises_if_ensure_loop_fails: Starting.")
        simulated_startup_error = CoreTaskManagerError("Simulated critical failure in ensure_loop_running")
        with patch.object(self.tm, 'ensure_loop_running', side_effect=simulated_startup_error):
            with self.assertRaises(CoreTaskManagerError) as cm:
                self.tm.get_loop()
            self.assertIs(cm.exception, simulated_startup_error, "The specific error from ensure_loop_running should propagate.")
        logger.info("test_get_loop_raises_if_ensure_loop_fails: Completed successfully.")
    # End of pasted unchanged tests

    def test_submit_task_executes_coroutine_and_waits_for_result_correctly(self):
        """Test submitting a task from the main thread and correctly waiting for its completion."""
        self.tm.ensure_loop_running()
        logger.info("test_submit_task_executes_coroutine: Starting test.")

        expected_result = 123
        async_result_container = []

        async def coro_to_run_for_submit():
            logger.debug("coro_to_run_for_submit: Starting execution in loop thread.")
            res = await simple_coro(duration=0.05, value_to_return=expected_result)
            async_result_container.append(res)
            logger.debug(f"coro_to_run_for_submit: Finished execution, result: {res}")
            return res

        logger.info("test_submit_task_executes_coroutine: Submitting coro_to_run_for_submit via tm.submit_task.")
        task = self.tm.submit_task(coro_to_run_for_submit())
        self.assertIsInstance(task, asyncio.Task, "submit_task should return an asyncio.Task instance.")
        logger.info(f"test_submit_task_executes_coroutine: asyncio.Task reference obtained: {task.get_name()}")

        async def _waiter_for_task(task_to_await: asyncio.Task):
            logger.debug(f"_waiter_for_task: Now awaiting the submitted task {task_to_await.get_name()}.")
            return await task_to_await

        logger.info("test_submit_task_executes_coroutine: Using submit_and_wait to await the submitted task's completion.")
        try:
            final_result = self.tm.submit_and_wait(_waiter_for_task(task))
            logger.info(f"test_submit_task_executes_coroutine: submit_and_wait for waiter completed. Final result: {final_result}")
        except Exception as e_wait: # pragma: no cover
            self.fail(f"Waiting for submitted task via submit_and_wait failed unexpectedly: {e_wait}")
            return

        self.assertTrue(task.done(), "The original submitted task (coro_to_run_for_submit) should be done.")
        self.assertFalse(task.cancelled(), "Task should not be cancelled.")
        if task.exception():  # pragma: no cover
            logger.error(f"Task (coro_to_run_for_submit) had an exception: {task.exception()}")
        self.assertIsNone(task.exception(), f"Task should not have an exception: {task.exception()}")

        self.assertEqual(len(async_result_container), 1, "Coroutine side effect (container append) failed.")
        self.assertEqual(async_result_container[0], expected_result, "Coroutine side effect result mismatch.")
        self.assertEqual(task.result(), expected_result, "asyncio.Task.result() mismatch.")
        self.assertEqual(final_result, expected_result, "Result from submit_and_wait (via waiter) mismatch.")
        logger.info("test_submit_task_executes_coroutine: Completed successfully.")


    def test_submit_task_from_loop_thread_itself(self):
        """Test submitting a task when submit_task is called from within the loop thread."""
        self.tm.ensure_loop_running()
        logger.info("test_submit_task_from_loop_thread_itself: Starting.")

        async_result_container = []
        task_ref_holder = {}

        async def coro_inner_task():
            logger.debug("coro_inner_task: Executing.")
            res = await simple_coro(value_to_return="result_from_inner_task_in_loop_thread")
            async_result_container.append(res)
            logger.debug("coro_inner_task: Finished.")
            return res

        async def coro_submitter_in_loop():
            logger.debug("coro_submitter_in_loop: Entered. Will call tm.submit_task for coro_inner_task.")
            inner_task = self.tm.submit_task(coro_inner_task())
            task_ref_holder['task'] = inner_task
            logger.debug(f"coro_submitter_in_loop: Submitted coro_inner_task, got task ref: {inner_task.get_name()}. Now awaiting it.")
            await inner_task
            logger.debug("coro_submitter_in_loop: Awaited inner_task successfully.")
            return "coro_submitter_done"

        logger.info("test_submit_task_from_loop_thread_itself: Using submit_and_wait to run coro_submitter_in_loop.")
        outer_result = self.tm.submit_and_wait(coro_submitter_in_loop())

        self.assertEqual(outer_result, "coro_submitter_done", "Outer submitter coroutine did not return expected value.")
        self.assertIn('task', task_ref_holder, "Task reference for inner task was not captured.")
        self.assertIsInstance(task_ref_holder['task'], asyncio.Task, "Inner task reference is not an asyncio.Task.")
        self.assertTrue(task_ref_holder['task'].done(), "Inner task should be done.")
        self.assertEqual(len(async_result_container), 1, "Inner task did not append to result container.")
        self.assertEqual(async_result_container[0], "result_from_inner_task_in_loop_thread", "Inner task result mismatch.")
        logger.info("test_submit_task_from_loop_thread_itself: Completed successfully.")


    def test_submit_and_wait_returns_value(self):
        """Test submit_and_wait successfully returns a value from a coroutine."""
        self.tm.ensure_loop_running()
        expected_value = "value_from_submit_and_wait"
        logger.info(f"test_submit_and_wait_returns_value: Calling submit_and_wait for simple_coro returning '{expected_value}'.")
        result = self.tm.submit_and_wait(simple_coro(value_to_return=expected_value))
        self.assertEqual(result, expected_value, "submit_and_wait did not return the correct value.")
        logger.info("test_submit_and_wait_returns_value: Completed successfully.")

    def test_submit_and_wait_propagates_exception(self):
        """Test submit_and_wait correctly propagates exceptions from the coroutine."""
        self.tm.ensure_loop_running()
        custom_exception = ValueError("Test Exception from Coroutine for submit_and_wait")
        logger.info(f"test_submit_and_wait_propagates_exception: Calling submit_and_wait for simple_coro raising '{custom_exception}'.")
        with self.assertRaises(ValueError) as context_manager:
            self.tm.submit_and_wait(simple_coro(value_to_return=custom_exception))

        self.assertIs(context_manager.exception, custom_exception,
                      "The specific exception instance from the coroutine should be propagated by submit_and_wait.")
        logger.info("test_submit_and_wait_propagates_exception: Completed successfully (exception propagated as expected).")

    def test_submit_and_wait_from_loop_thread_raises_runtime_error(self):
        """Test submit_and_wait raises RuntimeError if called from the loop thread itself."""
        self.tm.ensure_loop_running()
        logger.info("test_saw_from_loop_raises: Starting.")

        exception_details_holder = {}

        async def coro_attempting_recursive_submit_and_wait():
            logger.debug("coro_attempting_recursive_submit_and_wait: Entered. Will attempt illegal submit_and_wait.")
            try:
                # The simple_coro object is created but never awaited if RuntimeError is raised by submit_and_wait.
                # This is expected and may cause a RuntimeWarning, which is acceptable for this test.
                self.tm.submit_and_wait(simple_coro(duration=0.001, value_to_return="should_not_happen"))
                logger.error("coro_attempting_recursive_submit_and_wait: Inner submit_and_wait DID NOT RAISE RuntimeError!") # pragma: no cover
                exception_details_holder['raised'] = False
            except RuntimeError as e_runtime:
                logger.info(f"coro_attempting_recursive_submit_and_wait: Caught RuntimeError as expected: {e_runtime}")
                if "cannot be called from within the TaskManager's own event loop thread" in str(e_runtime):
                    exception_details_holder['raised'] = True
                    exception_details_holder['message_correct'] = True
                else: # pragma: no cover
                    exception_details_holder['raised'] = True
                    exception_details_holder['message_correct'] = False
                    logger.error(f"coro_attempting_recursive_submit_and_wait: Caught RuntimeError, but message was unexpected: {e_runtime}")
            except Exception as e_other: # pragma: no cover
                logger.error(f"coro_attempting_recursive_submit_and_wait: Caught unexpected exception type: {type(e_other).__name__}: {e_other}")
                exception_details_holder['raised'] = True
                exception_details_holder['message_correct'] = False
                exception_details_holder['other_exception'] = e_other

            logger.debug("coro_attempting_recursive_submit_and_wait: Exiting.")
            return "coro_attempting_recursive_done"

        logger.info("test_saw_from_loop_raises: Calling outer submit_and_wait for coro_attempting_recursive_submit_and_wait.")
        try:
            outer_result = self.tm.submit_and_wait(coro_attempting_recursive_submit_and_wait())
            self.assertEqual(outer_result, "coro_attempting_recursive_done", "Outer coroutine did not complete as expected.")
        except Exception as e_outer_saw_call: # pragma: no cover
            self.fail(f"The outer submit_and_wait call failed unexpectedly: {e_outer_saw_call}")

        self.assertTrue(exception_details_holder.get('raised'),
                        "Inner call to submit_and_wait from loop thread did not raise any exception.")
        self.assertTrue(exception_details_holder.get('message_correct'),
                        "Inner call to submit_and_wait raised a RuntimeError, but with an unexpected message.")
        self.assertNotIn('other_exception', exception_details_holder,
                         f"Inner call raised an unexpected exception type: {exception_details_holder.get('other_exception')}")
        logger.info("test_saw_from_loop_raises: Completed successfully (RuntimeError correctly handled).")


    def test_shutdown_sequence_cancels_pending_tasks(self):
        """Test that the shutdown sequence signals effectively and cancels pending tasks."""
        self.tm.ensure_loop_running()
        self.assertTrue(self.tm.is_loop_running(), "Loop should be running before shutdown test.")
        logger.info("test_shutdown_sequence: Loop running. Submitting a long task.")

        long_task_was_cancelled_event = threading.Event()

        async def long_running_coro_for_shutdown_test():
            logger.debug("long_running_coro_for_shutdown_test: Started, entering long sleep.")
            try:
                await asyncio.sleep(10)
                logger.error("long_running_coro_for_shutdown_test: Sleep completed unexpectedly (should have been cancelled).") # pragma: no cover
            except asyncio.CancelledError:
                logger.info("long_running_coro_for_shutdown_test: Correctly received CancelledError.")
                long_task_was_cancelled_event.set()
                raise
            except Exception as e_in_long_task: # pragma: no cover
                logger.error(f"long_running_coro_for_shutdown_test: Received unexpected error: {e_in_long_task}")


        submitted_long_task = self.tm.submit_task(long_running_coro_for_shutdown_test())
        logger.info(f"test_shutdown_sequence: Long task {submitted_long_task.get_name()} submitted. Now signaling shutdown.")

        time.sleep(0.1)

        self.tm.signal_shutdown()
        logger.info("test_shutdown_sequence: signal_shutdown() called.")

        self.assertTrue(self.tm._sync_shutdown_wait_event.is_set(),
                        "_sync_shutdown_wait_event should be set immediately by signal_shutdown.")

        logger.info("test_shutdown_sequence: Calling wait_for_shutdown() to block until TM fully stops.")
        self.tm.wait_for_shutdown()
        logger.info("test_shutdown_sequence: wait_for_shutdown() completed.")

        self.assertFalse(self.tm.is_loop_running(), "Loop should not be running after wait_for_shutdown.")
        self.assertIsNone(self.tm._loop_thread, "_loop_thread should be None after full shutdown.")
        self.assertIsNone(self.tm._loop, "_loop should be None after full shutdown.")

        self.assertTrue(long_task_was_cancelled_event.wait(timeout=1.0),
                        "Long-running task did not signal that it was cancelled via its event.")

        # Check the task's state
        self.assertTrue(submitted_long_task.done(), "Cancelled task should be 'done'.")
        self.assertTrue(submitted_long_task.cancelled(), "Task should be marked as 'cancelled'.")

        # Accessing .exception() on a cancelled task raises CancelledError.
        # So, we assert that this specific error is raised.
        with self.assertRaises(asyncio.CancelledError):
            submitted_long_task.exception()
        logger.info("test_shutdown_sequence: Completed successfully.")


    def test_wait_for_shutdown_async_unblocks_after_signal(self):
        """Test that wait_for_shutdown_async (called from loop thread) unblocks after signal_shutdown."""
        self.tm.ensure_loop_running()
        logger.info("test_wait_for_shutdown_async: Starting.")

        async def coroutine_that_waits_and_signals():
            logger.debug("coroutine_that_waits_and_signals: Creating wait_for_shutdown_async task.")
            waiter_task = asyncio.create_task(self.tm.wait_for_shutdown_async())

            await asyncio.sleep(0.01)
            self.assertFalse(waiter_task.done(),
                             "wait_for_shutdown_async task should be waiting (not done yet).")

            logger.debug("coroutine_that_waits_and_signals: Calling tm.signal_shutdown() from loop thread.")
            self.tm.signal_shutdown()
            logger.debug("coroutine_that_waits_and_signals: tm.signal_shutdown() called.")

            try:
                logger.debug("coroutine_that_waits_and_signals: Awaiting waiter_task.")
                await asyncio.wait_for(waiter_task, timeout=1.0)
                logger.debug("coroutine_that_waits_and_signals: waiter_task completed.")
            except asyncio.TimeoutError: # pragma: no cover
                self.fail("wait_for_shutdown_async task did not complete within timeout after being signaled.")

            self.assertTrue(waiter_task.done(), "wait_for_shutdown_async task should be done after signal and await.")
            if waiter_task.exception(): # pragma: no cover
                 self.fail(f"wait_for_shutdown_async task raised an unexpected exception: {waiter_task.exception()}")
            return "wait_and_signal_done"

        logger.info("test_wait_for_shutdown_async: Using submit_and_wait to run coroutine_that_waits_and_signals.")
        result = self.tm.submit_and_wait(coroutine_that_waits_and_signals())
        self.assertEqual(result, "wait_and_signal_done")

        logger.info("test_wait_for_shutdown_async: Performing full TM shutdown for test cleanup.")
        self.tm.wait_for_shutdown()
        logger.info("test_wait_for_shutdown_async: Completed successfully.")

    # test_VERY_SIMPLE_submit_and_wait_from_loop_thread_raises_error and
    # test_submit_and_wait_from_loop_thread_raises_runtime_error both test similar things.
    # The "VERY_SIMPLE" one can be kept as a more focused version if desired, or merged.
    # For now, I'll keep both, but the RuntimeWarning about unawaited coroutine applies.
    # We accept this warning as it's a side effect of testing the error path of submit_and_wait.

    # test_submit_and_wait_with_simple_async_inner_work seems like a good general test, keeping it.
    def test_submit_and_wait_with_simple_async_inner_work(self):
        """Test submit_and_wait with a coro that does simple async work and returns."""
        self.tm.ensure_loop_running()
        logger.debug("test_saw_simple_async: Starting")

        async_result_container = []

        async def simple_worker_coro():
            logger.debug("simple_worker_coro: Starting sleep")
            await asyncio.sleep(0.05)
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
        """Extremely simplified test for the problematic scenario, checking RuntimeError."""
        self.tm.ensure_loop_running()
        logger.info("test_VERY_SIMPLE_saw_from_loop: Starting")

        exception_caught_in_coro = None

        async def coro_caller_simplified():
            nonlocal exception_caught_in_coro
            logger.info("coro_caller_simplified: Entered")
            try:
                # This simple_coro() object will not be awaited if submit_and_wait raises,
                # leading to a RuntimeWarning. This is an expected side effect of this test.
                self.tm.submit_and_wait(simple_coro(duration=0.001)) # Intentionally call from loop thread
                logger.error("coro_caller_simplified: Inner submit_and_wait DID NOT RAISE!")  # pragma: no cover
            except RuntimeError as e:
                logger.info(f"coro_caller_simplified: Caught expected RuntimeError: {e}")
                exception_caught_in_coro = e
            except Exception as e_other:  # pragma: no cover
                logger.error(f"coro_caller_simplified: Caught unexpected error: {e_other}")
                exception_caught_in_coro = e_other # Store to fail the test
            logger.info("coro_caller_simplified: Exiting")
            return "coro_caller_simplified_done"

        logger.info("test_VERY_SIMPLE_saw_from_loop: Calling outer submit_and_wait")
        try:
            result = self.tm.submit_and_wait(coro_caller_simplified())
            logger.info(f"test_VERY_SIMPLE_saw_from_loop: Outer submit_and_wait completed with result: {result}")
            self.assertEqual(result, "coro_caller_simplified_done")
            self.assertIsNotNone(exception_caught_in_coro, "No exception was caught in the coroutine.")
            self.assertIsInstance(exception_caught_in_coro, RuntimeError, "Caught exception was not a RuntimeError.")
            self.assertIn("cannot be called from within", str(exception_caught_in_coro), "RuntimeError message mismatch.")
        except Exception as e_outer:  # pragma: no cover
            logger.error(f"test_VERY_SIMPLE_saw_from_loop: Outer submit_and_wait failed: {e_outer}")
            self.fail(f"Outer submit_and_wait failed: {e_outer}")

        logger.info("test_VERY_SIMPLE_saw_from_loop: Finished")


if __name__ == '__main__':  # pragma: no cover
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s.%(msecs)03d - %(name)-30s - %(levelname)-8s - [%(threadName)s (TID:%(thread)d)] - %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    test_runner_logger = logging.getLogger("unittest_main")
    test_runner_logger.info("Starting CPythonTaskManager unit tests...")

    unittest.main()
    test_runner_logger.info("CPythonTaskManager unit tests finished.")