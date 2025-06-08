import unittest
import asyncio
import time
from concurrent.futures import Future
from typing import List, Any

from sidekick.core.cpython_task_manager import CPythonTaskManager
from sidekick.core.exceptions import CoreLoopNotRunningError, CoreTaskSubmissionError, CoreTaskManagerError


class TestCPythonTaskManager(unittest.TestCase):
    """Unit tests for the CPythonTaskManager."""

    def setUp(self):
        """Set up a new CPythonTaskManager instance for each test."""
        self.task_manager = CPythonTaskManager()
        self.results: List[Any] = []
        print(f"\n--- Running test: {self._testMethodName} ---")

    def tearDown(self):
        """Ensure the event loop is stopped after each test."""
        if hasattr(self, 'task_manager') and self.task_manager is not None:
            if self.task_manager.is_loop_running():
                print("Tearing down: stopping loop...")
                self.task_manager.stop_loop()
                self.task_manager.wait_for_stop()
                print("Tearing down: loop stopped.")
            else:
                print("Tearing down: loop was not running.")
        else:
            print("Tearing down: no task_manager instance found.")

    def _wait_for_task(self, task: asyncio.Task, timeout: float = 1.0) -> Any:
        """Helper to wait for an asyncio.Task from the main thread and get its result."""
        # Create a concurrent.futures.Future to bridge the result/exception
        future: Future = Future()

        def on_done(asyncio_task: asyncio.Task):
            """Callback for when the asyncio.Task completes."""
            try:
                # Set the result or exception of the concurrent.futures.Future
                # based on the outcome of the asyncio.Task.
                if exc := asyncio_task.exception():
                    future.set_exception(exc)
                else:
                    future.set_result(asyncio_task.result())
            except asyncio.CancelledError:
                future.cancel()
            except Exception as e:
                future.set_exception(e)

        # Add the callback to the task, ensuring it's called from within the loop.
        task.add_done_callback(on_done)

        # Block the main thread and wait for the concurrent.futures.Future to complete.
        return future.result(timeout=timeout)

    def test_initial_state(self):
        """Test that the task manager starts in a non-running state."""
        self.assertFalse(self.task_manager.is_loop_running())
        self.assertIsNone(self.task_manager._loop)
        self.assertIsNone(self.task_manager._loop_thread)

    def test_ensure_loop_running_and_is_running(self):
        """Test starting the loop and checking its running state."""
        self.assertFalse(self.task_manager.is_loop_running())

        # First call should start the loop
        self.task_manager.ensure_loop_running()
        self.assertTrue(self.task_manager.is_loop_running())

        # Second call should be idempotent and not cause issues
        self.task_manager.ensure_loop_running()
        self.assertTrue(self.task_manager.is_loop_running())

    def test_get_loop(self):
        """Test getting the event loop instance."""
        loop = self.task_manager.get_loop()
        self.assertIsInstance(loop, asyncio.AbstractEventLoop)
        self.assertTrue(loop.is_running())
        self.assertTrue(self.task_manager.is_loop_running())

    def test_stop_and_wait_for_stop(self):
        """Test the full lifecycle: start, stop, and wait."""
        self.task_manager.ensure_loop_running()
        self.assertTrue(self.task_manager.is_loop_running())

        # Get the thread for verification later
        thread_before_stop = self.task_manager._loop_thread
        self.assertIsNotNone(thread_before_stop)
        self.assertTrue(thread_before_stop.is_alive())

        self.task_manager.stop_loop()
        self.task_manager.wait_for_stop()

        self.assertFalse(self.task_manager.is_loop_running())
        # After wait_for_stop, the thread should no longer be alive
        self.assertFalse(thread_before_stop.is_alive())

    def test_submit_simple_task_from_main_thread(self):
        """Test submitting a simple task that has a side effect."""

        async def simple_coro():
            self.results.append(42)

        task = self.task_manager.submit_task(simple_coro())
        self.assertIsInstance(task, asyncio.Task)

        # Wait for the task to complete using the helper
        self._wait_for_task(task)

        self.assertEqual(self.results, [42])

    def test_submit_task_with_return_value(self):
        """Test submitting a task that returns a value."""

        async def coro_with_return():
            await asyncio.sleep(0.05)
            return "done"

        task = self.task_manager.submit_task(coro_with_return())

        result = self._wait_for_task(task)
        self.assertEqual(result, "done")

    def test_submit_task_that_raises_exception(self):
        """Test that exceptions from tasks are propagated correctly."""

        class CustomTestException(Exception):
            pass

        async def coro_that_fails():
            await asyncio.sleep(0.01)  # Give loop time to process
            raise CustomTestException("Task failed as expected")

        task = self.task_manager.submit_task(coro_that_fails())

        with self.assertRaises(CustomTestException):
            self._wait_for_task(task)

    def test_create_event_and_use_it_for_sync(self):
        """Test creating an event and using it to synchronize with the main thread."""
        event = self.task_manager.create_event()
        self.assertIsInstance(event, asyncio.Event)

        # We no longer test the internal `_loop` attribute as it's an implementation detail.
        # self.assertIs(event._loop, self.task_manager.get_loop())

        async def coro_that_sets_event():
            await asyncio.sleep(0.1)
            self.results.append("setting event")
            event.set()

        self.task_manager.submit_task(coro_that_sets_event())

        # Poll the event from the main thread to wait for it.
        # This is a common pattern for testing cross-thread async communication.
        start_time = time.time()
        while not event.is_set():
            time.sleep(0.01)
            if time.time() - start_time > 2:
                self.fail("Test timed out waiting for asyncio.Event to be set.")

        self.assertEqual(self.results, ["setting event"])

    def test_submit_task_from_within_loop(self):
        """Test submitting a task from another task already running in the loop."""
        completion_event = self.task_manager.create_event()

        async def inner_coro():
            self.results.append("inner_done")

        async def outer_coro():
            # This task is already running in the loop. Now, submit another one.
            inner_task = self.task_manager.submit_task(inner_coro())
            await inner_task  # Wait for the inner task to complete
            self.results.append("outer_done")
            completion_event.set()

        self.task_manager.submit_task(outer_coro())

        # Wait for the outer coroutine to signal completion.
        start_time = time.time()
        while not completion_event.is_set():
            time.sleep(0.01)
            if time.time() - start_time > 2:
                self.fail("Test timed out waiting for outer coroutine to complete.")

        self.assertEqual(self.results, ["inner_done", "outer_done"])

    def test_multiple_tasks_concurrently(self):
        """Test that multiple submitted tasks run concurrently."""
        event1 = self.task_manager.create_event()
        event2 = self.task_manager.create_event()

        async def coro1():
            self.results.append("coro1_start")
            await event2.wait()  # Wait for coro2 to signal
            self.results.append("coro1_end")

        async def coro2():
            self.results.append("coro2_start")
            event1.set()  # Signal that coro2 has started
            await asyncio.sleep(0.1)  # Simulate work
            self.results.append("coro2_work_done")
            event2.set()  # Signal for coro1 to continue

        async def main_test_coro():
            # Create tasks within the event loop
            task1 = asyncio.create_task(coro1())
            task2 = asyncio.create_task(coro2())
            # Wait for both tasks to complete
            await asyncio.gather(task1, task2)

        # Submit the main wrapper coroutine as a single task
        main_task = self.task_manager.submit_task(main_test_coro())

        # Wait until event1 is set, which confirms coro2 started while coro1 was waiting.
        start_time = time.time()
        while not event1.is_set():
            time.sleep(0.01)
            if time.time() - start_time > 2:
                self.fail("Timed out waiting for coro2 to start.")

        # At this point, coro1 is waiting, and coro2 has started.
        # Allow a small moment for thread context switching to be safe.
        time.sleep(0.01)
        self.assertIn("coro1_start", self.results)
        self.assertIn("coro2_start", self.results)

        # Now, wait for the main task (which gathers the sub-tasks) to complete.
        self._wait_for_task(main_task, timeout=2)

        # Check the final order of operations
        self.assertEqual(self.results, ["coro1_start", "coro2_start", "coro2_work_done", "coro1_end"])

if __name__ == '__main__':
    unittest.main()