import unittest
import asyncio
import sys
from unittest.mock import patch, MagicMock

# We need to test the PyodideTaskManager, so we import it directly.
from sidekick.core.pyodide_task_manager import PyodideTaskManager
from sidekick.core.exceptions import CoreLoopNotRunningError


# --- Separate Test Case for Synchronous Tests ---
class TestPyodideTaskManagerSync(unittest.TestCase):
    """Contains synchronous tests for PyodideTaskManager that must run outside an event loop."""

    @patch('sidekick.core.utils.is_pyodide', return_value=True)
    @patch.dict('sys.modules', {'pyodide': MagicMock(), 'pyodide.ffi': MagicMock(), 'js': MagicMock()})
    def test_initialization_without_loop_raises_error(self, *mocks):
        """Test that initializing outside a loop raises an error."""
        print(f"\n--- Running sync test: {self._testMethodName} ---")
        # Since this test method is synchronous, there's no running loop.
        tm = PyodideTaskManager()
        with self.assertRaises(CoreLoopNotRunningError):
            tm.ensure_loop_running()
        print(f"--- Finished sync test: {self._testMethodName} ---")


# --- Main Test Case for Asynchronous Tests ---
class TestPyodideTaskManagerAsync(unittest.IsolatedAsyncioTestCase):
    """
    Unit tests for the PyodideTaskManager.
    These tests are run within an asyncio event loop to simulate the Pyodide environment.
    """

    async def asyncSetUp(self):
        """Set up a new PyodideTaskManager instance for each async test."""
        # Patch the source of truth for is_pyodide
        self.is_pyodide_patcher = patch('sidekick.core.utils.is_pyodide', return_value=True)
        self.is_pyodide_patcher.start()

        # Patch the 'js' and 'pyodide' modules to avoid ImportError
        self.pyodide_modules_patcher = patch.dict('sys.modules', {
            'pyodide': MagicMock(),
            'pyodide.ffi': MagicMock(),
            'js': MagicMock(),
        })
        self.pyodide_modules_patcher.start()

        self.task_manager = PyodideTaskManager()
        self.results = []
        print(f"\n--- Running async test: {self._testMethodName} ---")

    async def asyncTearDown(self):
        """Clean up patches after each test."""
        self.is_pyodide_patcher.stop()
        self.pyodide_modules_patcher.stop()
        print(f"--- Finished async test: {self._testMethodName} ---")

    async def test_initialization_and_state(self):
        """Test that the manager initializes correctly within a running loop."""
        self.assertIsInstance(self.task_manager, PyodideTaskManager)

        self.task_manager.ensure_loop_running()

        self.assertTrue(self.task_manager.is_loop_running())
        self.assertIsNotNone(self.task_manager.get_loop())
        self.assertIs(self.task_manager.get_loop(), asyncio.get_running_loop())

    async def test_submit_simple_task(self):
        """Test submitting a task that has a side effect."""

        async def simple_coro():
            self.results.append(123)

        task = self.task_manager.submit_task(simple_coro())
        self.assertIsInstance(task, asyncio.Task)
        await task
        self.assertEqual(self.results, [123])

    async def test_submit_task_with_return_value(self):
        """Test submitting a task that returns a value."""

        async def coro_with_return():
            await asyncio.sleep(0.01)
            return "success"

        task = self.task_manager.submit_task(coro_with_return())
        result = await task
        self.assertEqual(result, "success")

    async def test_submit_task_that_raises_exception(self):
        """Test that exceptions from tasks are propagated correctly."""

        class CustomPyodideTestException(Exception):
            pass

        async def coro_that_fails():
            await asyncio.sleep(0.01)
            raise CustomPyodideTestException("Pyodide task failed")

        task = self.task_manager.submit_task(coro_that_fails())
        with self.assertRaises(CustomPyodideTestException):
            await task

    async def test_create_event(self):
        """Test creating an asyncio.Event."""
        event = self.task_manager.create_event()
        self.assertIsInstance(event, asyncio.Event)
        event.set()
        await event.wait()
        self.assertTrue(event.is_set())

    async def test_lifecycle_methods_are_noop(self):
        """Test that stop_loop and wait_for_stop do nothing and don't raise errors."""
        try:
            self.task_manager.stop_loop()
            self.task_manager.wait_for_stop()
        except Exception as e:
            self.fail(f"stop_loop or wait_for_stop raised an unexpected exception: {e}")

    async def test_multiple_tasks_concurrently(self):
        """Test that multiple submitted tasks run concurrently."""
        event1 = self.task_manager.create_event()
        event2 = self.task_manager.create_event()

        async def coro1():
            self.results.append("coro1_start")
            await event2.wait()
            self.results.append("coro1_end")

        async def coro2():
            self.results.append("coro2_start")
            event1.set()
            await asyncio.sleep(0.05)
            self.results.append("coro2_work_done")
            event2.set()

        task1 = self.task_manager.submit_task(coro1())
        task2 = self.task_manager.submit_task(coro2())

        await event1.wait()

        self.assertIn("coro1_start", self.results)
        self.assertIn("coro2_start", self.results)

        await asyncio.gather(task1, task2)
        self.assertEqual(self.results, ["coro1_start", "coro2_start", "coro2_work_done", "coro1_end"])


if __name__ == '__main__':
    unittest.main()