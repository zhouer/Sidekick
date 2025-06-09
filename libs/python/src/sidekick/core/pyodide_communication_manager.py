"""Pyodide-specific implementation of the CommunicationManager.

This module provides `PyodideCommunicationManager`, which facilitates communication
when the Sidekick Python library is running within a Pyodide environment (typically
inside a Web Worker). Instead of using WebSockets, it relies on direct JavaScript
function calls, brokered by the Pyodide runtime, to exchange messages with the
Sidekick UI running on the main browser thread.

The manager assumes that specific JavaScript functions are globally available in the
JavaScript context where Pyodide is operating. These functions are responsible for
relaying messages to/from the main thread UI.
"""

import asyncio
import logging
from typing import Awaitable, Callable, Union, Optional, Any

# Attempt to import Pyodide-specific modules for type checking and functionality.
# These imports are made optional to allow the codebase to be parsed in
# standard CPython environments where Pyodide is not installed.
try:
    from pyodide.ffi import JsProxy, create_proxy  # type: ignore[import-not-found]
    import js  # type: ignore[import-not-found] # Global object providing access to JS context

    _PYODIDE_AVAILABLE = True
    # Check for expected JS functions during class initialization or connection
    # to provide more specific errors if they are missing.
except ImportError:  # pragma: no cover
    _PYODIDE_AVAILABLE = False
    # Define placeholders for type hints if Pyodide is not available.
    # This helps linters and type checkers in non-Pyodide development environments.
    JsProxy = Any  # type: ignore[misc]
    # `js` object won't exist, leading to NameError if accessed,
    # which is caught by `PyodideCommunicationManager` if instantiated wrongly.

from .communication_manager import (
    CommunicationManager,
    MessageHandlerType,
    StatusChangeHandlerType,
    ErrorHandlerType
)
from .status import CoreConnectionStatus
from .task_manager import TaskManager # PyodideTaskManager will be used
from .exceptions import CoreConnectionError, CoreDisconnectedError
from .utils import is_pyodide # To confirm environment if needed, though factory should handle.

logger = logging.getLogger(__name__)


class PyodideCommunicationManager(CommunicationManager):
    """Manages communication using Pyodide's JavaScript bridge.

    This class implements the `CommunicationManager` interface for Pyodide
    environments. It assumes it's running within a Pyodide Web Worker and
    that the main browser thread (hosting the UI) has exposed JavaScript
    functions:
    - `js.registerSidekickMessageHandler(proxy_to_python_callback)`:
      Called by Python to give JavaScript a way to send messages to Python.
    - `js.sendHeroMessage(message_string)`:
      Called by Python to send a message string to the JavaScript side (UI).

    The "connection" is considered established once the Python message handler
    is successfully registered with the JavaScript side.
    """

    def __init__(self, task_manager: TaskManager):
        """Initializes the PyodideCommunicationManager.

        Args:
            task_manager (TaskManager): The TaskManager instance (typically
                `PyodideTaskManager`) for scheduling asynchronous operations
                like handler invocations.
        """
        if not _PYODIDE_AVAILABLE:  # pragma: no cover
            # This check is critical. The factory (get_communication_manager)
            # should prevent this class from being instantiated if Pyodide isn't available.
            # If it still happens, it's a fundamental setup error.
            error_msg = (
                "PyodideCommunicationManager cannot be instantiated because "
                "Pyodide-specific modules ('pyodide', 'js') were not found. "
                "This indicates either the environment is not Pyodide or there's an "
                "issue with the Pyodide setup."
            )
            logger.critical(error_msg)
            raise RuntimeError(error_msg)

        # Secondary check using the utility, mostly for sanity/logging.
        if not is_pyodide():  # pragma: no cover
            logger.warning(
                "PyodideCommunicationManager is being instantiated, but the "
                "is_pyodide() utility returned False. This might indicate an "
                "environment detection inconsistency or an incorrect usage of the factory."
            )

        self._task_manager = task_manager
        self._status: CoreConnectionStatus = CoreConnectionStatus.DISCONNECTED
        # An asyncio.Lock to protect state transitions, especially around connect/close.
        # Even in Pyodide's single-threaded worker, this helps manage async state changes.
        self._connection_lock = asyncio.Lock()

        self._message_handler: Optional[MessageHandlerType] = None
        self._status_change_handler: Optional[StatusChangeHandlerType] = None
        self._error_handler: Optional[ErrorHandlerType] = None

        # Store the JsProxy for the message handler to allow for its destruction on close.
        self._js_message_handler_proxy: Optional[JsProxy] = None
        logger.debug("PyodideCommunicationManager instance created.")

    async def _invoke_handler_async(self, handler: Optional[Callable[..., Any]], *args: Any) -> None:
        """Safely invokes a registered handler (message, status, or error).

        Checks if the handler is callable and handles both sync and async handlers.
        Exceptions from handlers are caught and logged.

        Args:
            handler (Optional[Callable[..., Any]]): The handler function.
            *args (Any): Arguments for the handler.
        """
        if not handler: # If no handler is registered, do nothing.
            return
        try:
            if asyncio.iscoroutinefunction(handler):
                # If the handler is an async function, await it.
                await handler(*args)
            else:
                # If it's a synchronous function, call it directly.
                # This runs in the Pyodide worker's single event loop.
                handler(*args)
        except Exception as e:  # pragma: no cover
            # Log any exception that occurs within the user's handler.
            handler_name = getattr(handler, '__name__', 'unknown_handler')
            logger.exception(f"An error occurred inside the registered handler '{handler_name}': {e}")
            # Avoid recursive error reporting: if this is the error_handler itself failing, don't call it again.
            if self._error_handler and handler is not self._error_handler:
                # Report the handler's exception to the main _error_handler.
                await self._invoke_handler_async(self._error_handler, e)

    async def _update_status_async(self, new_status: CoreConnectionStatus) -> None:
        """Internal helper to update the connection status and notify the status change handler.

        Args:
            new_status (CoreConnectionStatus): The new status to set.
        """
        if self._status == new_status: # No change needed.
            return
        logger.debug(f"PyodideCommunicationManager: Status changing from {self._status.name} to {new_status.name}")
        self._status = new_status

        if self._status_change_handler:
            # Schedule the handler invocation to run on the TaskManager's event loop.
            async def do_notify_status_change_pyodide():
                await self._invoke_handler_async(self._status_change_handler, new_status)
            try:
                self._task_manager.submit_task(do_notify_status_change_pyodide())
            except Exception as e_submit: # pragma: no cover
                 logger.error(f"PyodideCM: Failed to submit status change notification task: {e_submit}")


    def _on_message_from_js(self, message_str: str) -> None:
        """Callback executed by JavaScript when a message is received from the Sidekick UI.

        This method itself **must be synchronous** as it's called directly from
        the JavaScript environment via the Pyodide FFI (Foreign Function Interface).
        It then schedules the actual (potentially asynchronous) message handling
        via the TaskManager to ensure it runs within Pyodide's asyncio event loop.

        Args:
            message_str (str): The raw message string received from the JavaScript side.
        """
        logger.debug(
            f"PyodideCM _on_message_from_js: Received raw message from JS. Length: {len(message_str)}. "
            f"Preview: {message_str[:150]}{'...' if len(message_str) > 150 else ''}"
        )
        if self._message_handler:
            # Define an async wrapper to call the registered message handler.
            async def do_handle_message_pyodide():
                await self._invoke_handler_async(self._message_handler, message_str)
            # Submit this wrapper to the TaskManager to run on Pyodide's asyncio loop.
            try:
                self._task_manager.submit_task(do_handle_message_pyodide())
            except Exception as e_submit: # pragma: no cover
                 logger.error(f"PyodideCM: Failed to submit JS message handling task: {e_submit}")
        else:  # pragma: no cover
            logger.warning(
                "PyodideCommunicationManager received a message from JavaScript, "
                "but no message handler is currently registered. Message ignored."
            )

    async def connect_async(
        self,
        message_handler: Optional[MessageHandlerType] = None,
        status_change_handler: Optional[StatusChangeHandlerType] = None,
        error_handler: Optional[ErrorHandlerType] = None
    ) -> None:
        """Establishes the communication bridge to JavaScript.

        For Pyodide, "connecting" means registering a Python callback function
        (via a Pyodide proxy) with the JavaScript environment, allowing JavaScript
        to send messages to this Python instance.
        """
        async with self._connection_lock: # Ensure atomic connect operation.
            if self._status == CoreConnectionStatus.CONNECTED or self._status == CoreConnectionStatus.CONNECTING:
                logger.debug(
                    f"PyodideCM connect_async attempt skipped: already {self._status.name}."
                )
                return

            await self._update_status_async(CoreConnectionStatus.CONNECTING)
            logger.info("PyodideCommunicationManager: Attempting to establish JavaScript communication bridge.")

            # Store provided handlers internally
            self._message_handler = message_handler
            self._status_change_handler = status_change_handler
            self._error_handler = error_handler

            try:
                # Check if essential JavaScript functions are available on the global `js` object.
                if not hasattr(js, 'registerSidekickMessageHandler'):  # pragma: no cover
                    raise AttributeError(
                        "The required JavaScript function 'registerSidekickMessageHandler' was not found "
                        "on the global 'js' object. Ensure the Sidekick UI environment is correctly set up."
                    )

                # If a proxy already exists (e.g., from a previous failed connection attempt
                # that didn't clean up fully), try to destroy it first.
                if self._js_message_handler_proxy:  # pragma: no cover
                    logger.warning("PyodideCM: Found an existing JS message handler proxy. Attempting to destroy it before creating a new one.")
                    try:
                        self._js_message_handler_proxy.destroy()
                    except Exception as e_destroy_old:
                        logger.warning(f"PyodideCM: Error destroying old JS proxy: {e_destroy_old}")
                    self._js_message_handler_proxy = None

                # Create a Pyodide proxy for the Python method `_on_message_from_js`.
                # This proxy makes the Python method callable from JavaScript.
                # _on_message_from_js will use the self._message_handler set above.
                self._js_message_handler_proxy = create_proxy(self._on_message_from_js)

                # Register this proxied Python callback with the JavaScript side.
                js.registerSidekickMessageHandler(self._js_message_handler_proxy)  # type: ignore[attr-defined]

                logger.info("PyodideCommunicationManager: JavaScript communication bridge established (JS message handler registered).")
                await self._update_status_async(CoreConnectionStatus.CONNECTED)

            except (AttributeError, NameError, RuntimeError) as e_bridge_setup:
                # AttributeError: If `js.registerSidekickMessageHandler` is missing.
                # NameError: If `js` or `create_proxy` itself is not found (should be caught by __init__ if _PYODIDE_AVAILABLE is false).
                # RuntimeError: Can be raised by FFI operations.
                err_msg = f"PyodideCM: Failed to set up JavaScript bridge: {e_bridge_setup}"
                logger.exception(err_msg) # Log with stack trace
                await self._update_status_async(CoreConnectionStatus.ERROR)
                if self._error_handler:
                    await self._invoke_handler_async(self._error_handler, e_bridge_setup)
                # Raise a specific CoreConnectionError to indicate failure.
                raise CoreConnectionError(err_msg, original_exception=e_bridge_setup)
            except Exception as e_unexpected_connect:  # pragma: no cover
                # Catch-all for any other unexpected errors during the connect process.
                err_msg = f"PyodideCM: An unexpected error occurred during connect_async: {e_unexpected_connect}"
                logger.exception(err_msg)
                await self._update_status_async(CoreConnectionStatus.ERROR)
                if self._error_handler:
                    await self._invoke_handler_async(self._error_handler, e_unexpected_connect)
                raise CoreConnectionError(err_msg, original_exception=e_unexpected_connect)

    async def send_message_async(self, message_str: str) -> None:
        """Sends a string message to the Sidekick UI via the JavaScript bridge.

        Args:
            message_str (str): The message string to send (expected to be JSON).

        Raises:
            CoreDisconnectedError: If the manager is not connected.
        """
        if self._status != CoreConnectionStatus.CONNECTED:
            err_msg = (
                f"PyodideCommunicationManager: Cannot send message, not connected. "
                f"Current status: {self._status.name}."
            )
            logger.error(err_msg)
            raise CoreDisconnectedError(err_msg, reason=f"Current status: {self._status.name}")

        try:
            # Ensure the `js.sendHeroMessage` function exists.
            if not hasattr(js, 'sendHeroMessage'):  # pragma: no cover
                raise AttributeError(
                    "The required JavaScript function 'sendHeroMessage' was not found on the global 'js' object. "
                    "Ensure the Sidekick UI environment is correctly set up."
                )

            logger.debug(f"PyodideCM sending message to JS: {message_str[:200]}{'...' if len(message_str) > 200 else ''}")
            # Call the globally available JavaScript function to send the message.
            js.sendHeroMessage(message_str)  # type: ignore[attr-defined]

        except (AttributeError, NameError, RuntimeError) as e_send_bridge:
            # Handle errors if the JS bridge function is missing or fails.
            err_msg = f"PyodideCM: Failed to send message via JavaScript bridge: {e_send_bridge}"
            logger.exception(err_msg)
            await self._update_status_async(CoreConnectionStatus.ERROR) # Assume connection is compromised
            if self._error_handler:
                await self._invoke_handler_async(self._error_handler, e_send_bridge)
            raise CoreDisconnectedError(err_msg, reason=str(e_send_bridge), original_exception=e_send_bridge)
        except Exception as e_send_unexpected:  # pragma: no cover
            # Catch-all for other unexpected errors during send.
            err_msg = f"PyodideCM: An unexpected error occurred while sending message: {e_send_unexpected}"
            logger.exception(err_msg)
            await self._update_status_async(CoreConnectionStatus.ERROR)
            if self._error_handler:
                await self._invoke_handler_async(self._error_handler, e_send_unexpected)
            raise CoreDisconnectedError(err_msg, reason=str(e_send_unexpected), original_exception=e_send_unexpected)

    async def close_async(self) -> None:
        """Closes the communication bridge by destroying the JavaScript proxy.

        This effectively unregisters the Python message handler from the JavaScript side,
        stopping further messages from being received.
        """
        async with self._connection_lock: # Ensure atomic close operation.
            if self._status == CoreConnectionStatus.DISCONNECTED or self._status == CoreConnectionStatus.CLOSING:
                logger.debug(
                    f"PyodideCM close_async attempt skipped: already {self._status.name}."
                )
                return

            logger.info("PyodideCommunicationManager: Closing JavaScript communication bridge.")
            await self._update_status_async(CoreConnectionStatus.CLOSING)

            if self._js_message_handler_proxy:
                try:
                    # Destroy the Pyodide FFI proxy to release resources and break the link.
                    self._js_message_handler_proxy.destroy()
                    logger.debug("PyodideCM: JavaScript message handler proxy successfully destroyed.")
                except Exception as e_destroy_proxy:  # pragma: no cover
                    # Log if destroying the proxy fails, but proceed with status update.
                    logger.warning(f"PyodideCM: Error encountered while destroying JS proxy: {e_destroy_proxy}")
                finally:
                    self._js_message_handler_proxy = None # Clear the reference.

            # Note: There isn't an explicit "unregister" call to JavaScript in this model.
            # The destruction of the proxy on the Python side is the primary cleanup.
            # If JavaScript maintained a direct reference to the proxy object (beyond what
            # Pyodide manages), that side might also need explicit cleanup if this proxy
            # were to be replaced by a new one later without a full page reload.

            # Clear handlers after connection is confirmed closed
            self._message_handler = None
            self._status_change_handler = None
            self._error_handler = None
            await self._update_status_async(CoreConnectionStatus.DISCONNECTED)
            logger.info("PyodideCommunicationManager: JavaScript communication bridge closed.")

    def is_connected(self) -> bool:
        """Checks if the communication bridge to JavaScript is considered active."""
        return self._status == CoreConnectionStatus.CONNECTED

    def get_current_status(self) -> CoreConnectionStatus:
        """Returns the current `CoreConnectionStatus` of the Pyodide bridge."""
        return self._status
