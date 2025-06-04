"""Unit tests for PyodideTaskManager in sidekick.core."""

import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
import logging # Import logging for assertLogs

from sidekick.core.pyodide_task_manager import PyodideTaskManager
from sidekick.core.exceptions import CoreLoopNotRunningError, CoreTaskSubmissionError

# A simple coroutine for testing task submission
async def dummy_coro():
    await asyncio.sleep(0)
    return "dummy_coro_result"

logger = logging.getLogger(__name__)


class TestPyodideTaskManager(unittest.TestCase):

    def setUp(self):
        self.tm = PyodideTaskManager()

    @patch('sidekick.core.pyodide_task_manager.asyncio.get_event_loop') # Patch where get_event_loop is called
    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop') # Patch where get_running_loop is called
    def test_initial_state_and_first_initialization_with_running_loop(self, mock_get_running_loop, mock_get_event_loop):
        """Test initialization when get_running_loop returns a loop."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.is_running.return_value = True
        mock_get_running_loop.return_value = mock_loop

        self.assertFalse(self.tm._initialized)
        self.tm.ensure_loop_running()

        self.assertTrue(self.tm._initialized)
        self.assertIs(self.tm._loop, mock_loop)
        self.assertIsInstance(self.tm._shutdown_requested_event, asyncio.Event)
        mock_get_running_loop.assert_called_once()
        mock_get_event_loop.assert_not_called()

    @patch('sidekick.core.pyodide_task_manager.asyncio.get_event_loop')
    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop')
    def test_initialization_fallback_to_get_event_loop(self, mock_get_running_loop, mock_get_event_loop):
        """Test initialization falls back to get_event_loop if get_running_loop fails."""
        mock_get_running_loop.side_effect = RuntimeError("No running loop")

        mock_fallback_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_fallback_loop.is_running.return_value = True
        mock_get_event_loop.return_value = mock_fallback_loop

        self.tm.ensure_loop_running()

        self.assertTrue(self.tm._initialized)
        self.assertIs(self.tm._loop, mock_fallback_loop)
        mock_get_running_loop.assert_called_once()
        mock_get_event_loop.assert_called_once()

    @patch('sidekick.core.pyodide_task_manager.asyncio.get_event_loop', side_effect=RuntimeError("get_event_loop also fails"))
    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop', side_effect=RuntimeError("No running loop from mock"))
    def test_initialization_raises_if_no_loop_available(self, mock_get_running_loop, mock_get_event_loop):
        """Test ensure_loop_running raises CoreLoopNotRunningError if no loop can be obtained."""
        with self.assertRaisesRegex(CoreLoopNotRunningError, "Failed to obtain an event loop in Pyodide environment"):
            self.tm.ensure_loop_running()
        self.assertFalse(self.tm._initialized)

    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop')
    def test_is_loop_running(self, mock_get_running_loop):
        mock_loop_active = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop_active.is_running.return_value = True

        mock_loop_inactive = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop_inactive.is_running.return_value = False

        mock_get_running_loop.return_value = mock_loop_active
        tm1 = PyodideTaskManager()
        tm1.ensure_loop_running()
        self.assertTrue(tm1.is_loop_running())

        mock_get_running_loop.return_value = mock_loop_inactive
        tm2 = PyodideTaskManager()
        tm2.ensure_loop_running()
        self.assertFalse(tm2.is_loop_running())

        mock_get_running_loop.side_effect = RuntimeError("No loop at all")
        tm3 = PyodideTaskManager()
        self.assertFalse(tm3.is_loop_running())

    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop')
    def test_get_loop_success(self, mock_get_running_loop):
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.is_running.return_value = True
        mock_get_running_loop.return_value = mock_loop
        self.tm.ensure_loop_running()
        returned_loop = self.tm.get_loop()
        self.assertIs(returned_loop, mock_loop)

    # Corrected version for test_get_loop_raises_if_initialization_fails intent
    @patch('sidekick.core.pyodide_task_manager.asyncio.get_event_loop', side_effect=RuntimeError("get_event_loop also fails for test"))
    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop', side_effect=RuntimeError("No running loop from mock for test"))
    def test_get_loop_raises_if_both_loop_sources_fail(self, mock_get_running_loop, mock_get_event_loop):
        """Test get_loop() raises CoreLoopNotRunningError if both get_running_loop and get_event_loop fail."""
        with self.assertRaisesRegex(CoreLoopNotRunningError, "Failed to obtain an event loop"):
            self.tm.get_loop()

    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop')
    def test_submit_task_success(self, mock_get_running_loop):
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.is_running.return_value = True
        mock_get_running_loop.return_value = mock_loop

        mock_task_obj = MagicMock(spec=asyncio.Task)
        mock_loop.create_task.return_value = mock_task_obj

        self.tm.ensure_loop_running()
        coro_instance = dummy_coro()
        returned_task = self.tm.submit_task(coro_instance)

        mock_loop.create_task.assert_called_once_with(coro_instance)
        self.assertIs(returned_task, mock_task_obj)

    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop')
    def test_submit_task_propagates_create_task_runtime_error(self, mock_get_running_loop):
        """Test submit_task() raises CoreTaskSubmissionError if loop.create_task fails."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.is_running.return_value = True
        mock_get_running_loop.return_value = mock_loop

        test_exception = RuntimeError("Simulated loop.create_task failure")
        mock_loop.create_task.side_effect = test_exception

        self.tm.ensure_loop_running()

        with self.assertRaises(CoreTaskSubmissionError) as cm:
            self.tm.submit_task(dummy_coro())

        # __cause__ should be set if 'from e' was used when raising CoreTaskSubmissionError
        self.assertIs(cm.exception.__cause__, test_exception,
                      "The original RuntimeError should be the cause of CoreTaskSubmissionError.")
        self.assertIn("Failed to submit task in Pyodide: Simulated loop.create_task failure", str(cm.exception))



    def test_wait_for_shutdown_raises_not_implemented_error(self):
        with patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop', return_value=MagicMock(is_running=True)):
            self.tm.ensure_loop_running()
        with self.assertRaisesRegex(NotImplementedError, r"wait_for_shutdown \(synchronous\) is not implemented for PyodideTaskManager"): # Corrected regex
            self.tm.wait_for_shutdown()

    async def _run_signal_and_wait_async_test_logic(self):
        """Async helper containing the logic for testing signal/wait_async."""
        # ensure_loop_running will be called by PTM methods, using the patched get_running_loop
        self.tm.ensure_loop_running()
        self.assertIsNotNone(self.tm._shutdown_requested_event)

        actual_shutdown_event = self.tm._shutdown_requested_event # Already an asyncio.Event

        wait_task = asyncio.create_task(self.tm.wait_for_shutdown_async())

        # Check *before* signaling and before any significant await that might complete the task
        self.assertFalse(wait_task.done(), "wait_for_shutdown_async should be waiting immediately after creation.")

        # Give other tasks (like wait_task starting its await) a chance to run
        await asyncio.sleep(0.001)
        self.assertFalse(wait_task.done(), "wait_for_shutdown_async should still be waiting before signal.")

        self.tm.signal_shutdown()

        self.assertTrue(actual_shutdown_event.is_set(), "Shutdown event should be set after signal_shutdown.")

        try:
            await asyncio.wait_for(wait_task, timeout=0.1)
        except asyncio.TimeoutError: # pragma: no cover
            self.fail("wait_for_shutdown_async did not complete after signal_shutdown within timeout.")

        self.assertTrue(wait_task.done(), "wait_for_shutdown_async task should be done.")
        self.assertIsNone(wait_task.exception(), f"wait_for_shutdown_async task failed with {wait_task.exception()}")


    @patch('sidekick.core.pyodide_task_manager.asyncio.get_event_loop') # Patch the fallback too
    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop')
    def test_signal_shutdown_and_wait_for_shutdown_async(self, mock_get_running_loop, mock_get_event_loop):
        """Test signal_shutdown() and wait_for_shutdown_async() interaction."""
        mock_loop_for_ptm = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop_for_ptm.is_running.return_value = True
        # PTM will use this mock_loop_for_ptm via its _ensure_initialized
        mock_get_running_loop.return_value = mock_loop_for_ptm
        mock_get_event_loop.return_value = mock_loop_for_ptm # Ensure fallback also gets it

        # The test runner (unittest) might not have a current event loop in this thread.
        # asyncio.run will create one for _run_signal_and_wait_async_test_logic.
        try:
            asyncio.run(self._run_signal_and_wait_async_test_logic())
        except Exception as e: # pragma: no cover
            self.fail(f"Async test logic failed: {e}")

    @patch('sidekick.core.pyodide_task_manager.asyncio.get_event_loop',
           side_effect=RuntimeError("get_event_loop fails for signal test"))
    @patch('sidekick.core.pyodide_task_manager.asyncio.get_running_loop',
           side_effect=RuntimeError("get_running_loop fails for signal test"))
    def test_signal_shutdown_when_not_initialized_logs_warning(self, mock_get_running, mock_get_event):
        """Test signal_shutdown() logs warning if _ensure_initialized fails."""
        with self.assertLogs(logger='sidekick.core.pyodide_task_manager', level='WARNING') as log_cm:
            self.tm.signal_shutdown()

            # We expect the warning from signal_shutdown's except block
        self.assertTrue(
            any("Cannot signal shutdown, loop not initialized properly." in record.getMessage() for record in
                log_cm.records),
            f"Expected warning log not found. Logs: {log_cm.output}"
        )

if __name__ == '__main__': # pragma: no cover
    logging.basicConfig(
        level=logging.INFO, # Changed to INFO to reduce noise from DEBUG
        format="%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s"
    )
    unittest.main()
