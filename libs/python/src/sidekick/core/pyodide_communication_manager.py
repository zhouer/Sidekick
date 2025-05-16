"""Pyodide-specific implementation of the CommunicationManager.

This module provides `PyodideCommunicationManager`, which uses direct JavaScript
function calls (brokered by the Pyodide environment) for communication between
the Python script running in a Web Worker and the Sidekick UI running on the
main browser thread.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Union, Optional, Any

# Attempt to import Pyodide-specific types for type checking if possible,
# but make them optional for environments where Pyodide isn't installed (e.g., CPython dev).
try:
    from pyodide.ffi import JsProxy, create_proxy  # type: ignore[import-not-found]
    import js  # type: ignore[import-not-found]

    _PYODIDE_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYODIDE_AVAILABLE = False
    # Define placeholders for type hints if Pyodide is not available
    JsProxy = Any  # type: ignore[misc]

from .communication_manager import (
    CommunicationManager,
    MessageHandlerType,
    StatusChangeHandlerType,
    ErrorHandlerType
)
from .status import CoreConnectionStatus
from .task_manager import TaskManager
from .exceptions import CoreConnectionError, CoreDisconnectedError
from .utils import is_pyodide  # To double-check environment

logger = logging.getLogger(__name__)


class PyodideCommunicationManager(CommunicationManager):
    """Manages communication using Pyodide's JS bridge.

    This class assumes it's running within a Pyodide environment where
    specific JavaScript functions (`registerSidekickMessageHandler` and
    `sendHeroMessage`) are globally available for inter-thread (Worker to Main)
    communication.
    """

    def __init__(self, task_manager: TaskManager):
        """Initializes the PyodideCommunicationManager.

        Args:
            task_manager: The TaskManager instance for scheduling async operations
                          like handler invocations.
        """
        if not _PYODIDE_AVAILABLE:  # pragma: no cover
            # This manager should only be instantiated if Pyodide is available.
            # The factory should prevent this.
            raise RuntimeError(
                "PyodideCommunicationManager cannot be used: "
                "Pyodide-specific modules ('pyodide', 'js') are not available."
            )
        if not is_pyodide():  # pragma: no cover
            logger.warning(
                "PyodideCommunicationManager instantiated, but is_pyodide() is False. "
                "This might indicate an environment detection issue or incorrect factory usage."
            )

        self._task_manager = task_manager
        self._status: CoreConnectionStatus = CoreConnectionStatus.DISCONNECTED
        # asyncio.Lock is okay even in single-threaded Pyodide for managing state transitions.
        self._connection_lock = asyncio.Lock()

        self._message_handler: Optional[MessageHandlerType] = None
        self._status_change_handler: Optional[StatusChangeHandlerType] = None
        self._error_handler: Optional[ErrorHandlerType] = None

        self._js_message_handler_proxy: Optional[JsProxy] = None

    async def _invoke_handler_async(self, handler: Optional[Callable[..., Any]], *args: Any) -> None:
        """Safely invokes a handler, whether it's sync or async."""
        if not handler:
            return
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(*args)
            else:
                handler(*args)  # Run sync handler directly
        except Exception as e:  # pragma: no cover
            logger.exception(f"Error invoking handler {handler.__name__}: {e}")
            if self._error_handler and handler is not self._error_handler:
                await self._invoke_handler_async(self._error_handler, e)

    async def _update_status_async(self, new_status: CoreConnectionStatus) -> None:
        """Internal helper to update status and notify handler."""
        if self._status == new_status:
            return
        logger.debug(f"Pyodide CM status changing from {self._status.name} to {new_status.name}")
        self._status = new_status
        if self._status_change_handler:
            async def do_notify():  # Simple wrapper for task submission
                await self._invoke_handler_async(self._status_change_handler, new_status)

            self._task_manager.submit_task(do_notify())

    def _on_message_from_js(self, message_str: str) -> None:
        """Callback executed by JavaScript when a message is received from the Sidekick UI.
        This method itself must be synchronous as it's called directly from JS.
        It then schedules the actual message handling.
        """
        logger.debug(
            f"Pyodide CM received raw message from JS: {message_str[:200]}{'...' if len(message_str) > 200 else ''}")
        if self._message_handler:
            # Schedule the potentially async message handler via the task manager
            # to run on Pyodide's asyncio loop.
            async def do_handle():
                await self._invoke_handler_async(self._message_handler, message_str)

            self._task_manager.submit_task(do_handle())
        else:  # pragma: no cover
            logger.warning("Pyodide CM received a message from JS, but no message handler is registered.")

    async def connect_async(self) -> None:
        """Establishes communication by registering a JS message handler."""
        async with self._connection_lock:
            if self._status == CoreConnectionStatus.CONNECTED or self._status == CoreConnectionStatus.CONNECTING:
                logger.debug(f"Pyodide CM connect attempt skipped, already {self._status.name}.")
                return

            await self._update_status_async(CoreConnectionStatus.CONNECTING)
            logger.info("Pyodide CM: Attempting to establish communication bridge.")

            try:
                # Ensure Pyodide FFI and JS context are available (already checked in __init__)
                # from pyodide.ffi import create_proxy
                # import js

                if not hasattr(js, 'registerSidekickMessageHandler'):  # pragma: no cover
                    raise AttributeError("JavaScript function 'registerSidekickMessageHandler' not found.")

                # Create a proxy for the Python callback.
                # This proxy needs to be stored to be destroyed later.
                if self._js_message_handler_proxy:  # pragma: no cover
                    try:
                        self._js_message_handler_proxy.destroy()
                    except Exception:
                        pass  # Ignore if already destroyed
                self._js_message_handler_proxy = create_proxy(self._on_message_from_js)

                # Register the Python callback with the JavaScript side.
                js.registerSidekickMessageHandler(self._js_message_handler_proxy)  # type: ignore[attr-defined]

                logger.info("Pyodide CM: Communication bridge established (JS handler registered).")
                await self._update_status_async(CoreConnectionStatus.CONNECTED)

            except (AttributeError, NameError, RuntimeError) as e:  # NameError if 'js' or 'create_proxy' not found
                err_msg = f"Pyodide CM: Failed to set up JS bridge: {e}"
                logger.exception(err_msg)
                await self._update_status_async(CoreConnectionStatus.ERROR)
                if self._error_handler:
                    await self._invoke_handler_async(self._error_handler, e)
                raise CoreConnectionError(err_msg, original_exception=e)
            except Exception as e:  # pragma: no cover
                # Catch-all for unexpected errors
                err_msg = f"Pyodide CM: Unexpected error during connect_async: {e}"
                logger.exception(err_msg)
                await self._update_status_async(CoreConnectionStatus.ERROR)
                if self._error_handler:
                    await self._invoke_handler_async(self._error_handler, e)
                raise CoreConnectionError(err_msg, original_exception=e)

    async def send_message_async(self, message_str: str) -> None:
        """Sends a string message to the Sidekick UI via JavaScript."""
        if self._status != CoreConnectionStatus.CONNECTED:
            err_msg = f"Pyodide CM: Cannot send message, not connected (status: {self._status.name})."
            logger.error(err_msg)
            raise CoreDisconnectedError(err_msg, reason=f"Current status: {self._status.name}")

        try:
            # import js # Should be available if connect_async succeeded.
            if not hasattr(js, 'sendHeroMessage'):  # pragma: no cover
                raise AttributeError("JavaScript function 'sendHeroMessage' not found.")

            logger.debug(f"Pyodide CM sending: {message_str[:200]}{'...' if len(message_str) > 200 else ''}")
            js.sendHeroMessage(message_str)  # type: ignore[attr-defined]

        except (AttributeError, NameError, RuntimeError) as e:  # NameError if 'js' not found
            err_msg = f"Pyodide CM: Failed to send message via JS bridge: {e}"
            logger.exception(err_msg)
            await self._update_status_async(CoreConnectionStatus.ERROR)
            if self._error_handler:
                await self._invoke_handler_async(self._error_handler, e)
            raise CoreDisconnectedError(err_msg, reason=str(e), original_exception=e)
        except Exception as e:  # pragma: no cover
            err_msg = f"Pyodide CM: Unexpected error sending message: {e}"
            logger.exception(err_msg)
            await self._update_status_async(CoreConnectionStatus.ERROR)
            if self._error_handler:
                await self._invoke_handler_async(self._error_handler, e)
            raise CoreDisconnectedError(err_msg, reason=str(e), original_exception=e)

    async def close_async(self) -> None:
        """Closes the communication bridge by destroying the JS proxy."""
        async with self._connection_lock:
            if self._status == CoreConnectionStatus.DISCONNECTED or self._status == CoreConnectionStatus.CLOSING:
                logger.debug(f"Pyodide CM close attempt skipped, already {self._status.name}.")
                return

            logger.info("Pyodide CM: Closing communication bridge.")
            await self._update_status_async(CoreConnectionStatus.CLOSING)

            if self._js_message_handler_proxy:
                try:
                    self._js_message_handler_proxy.destroy()
                    logger.debug("Pyodide CM: JS message handler proxy destroyed.")
                except Exception as e:  # pragma: no cover
                    logger.warning(f"Pyodide CM: Error destroying JS proxy: {e}")
                self._js_message_handler_proxy = None

            # There isn't an explicit "unregister" in the provided JS,
            # destroying the proxy is the main cleanup on Python side.
            # If JS side kept a direct reference, it might also need cleanup there.

            await self._update_status_async(CoreConnectionStatus.DISCONNECTED)
            logger.info("Pyodide CM: Communication bridge closed.")

    def register_message_handler(self, handler: MessageHandlerType) -> None:
        """Registers a callback for incoming messages from JS."""
        logger.debug(f"Pyodide CM: Registering message handler: {handler}")
        self._message_handler = handler

    def register_status_change_handler(self, handler: StatusChangeHandlerType) -> None:
        """Registers a callback for connection status changes."""
        logger.debug(f"Pyodide CM: Registering status change handler: {handler}")
        self._status_change_handler = handler

    def register_error_handler(self, handler: Optional[ErrorHandlerType]) -> None:
        """Registers a callback for low-level communication errors."""
        logger.debug(f"Pyodide CM: Registering error handler: {handler}")
        self._error_handler = handler

    def is_connected(self) -> bool:
        """Checks if the communication bridge is active."""
        return self._status == CoreConnectionStatus.CONNECTED

    def get_current_status(self) -> CoreConnectionStatus:
        """Returns the current connection status."""
        return self._status