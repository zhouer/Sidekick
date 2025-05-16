"""WebSocket-based implementation of the CommunicationManager.

This module provides `WebSocketCommunicationManager`, which uses the `websockets`
library to manage a WebSocket connection to a remote server. It handles
sending and receiving messages, managing connection state, and invoking
registered handlers for messages, status changes, and errors.
"""

import asyncio
import logging
import websockets # type: ignore[import-untyped] # websockets is not fully typed yet or recognized by all linters
from typing import Awaitable, Callable, Union, Optional, Any

from .communication_manager import (
    CommunicationManager,
    MessageHandlerType,
    StatusChangeHandlerType,
    ErrorHandlerType
)
from .status import CoreConnectionStatus
from .task_manager import TaskManager
from .exceptions import (
    CoreConnectionError,
    CoreConnectionRefusedError,
    CoreConnectionTimeoutError,
    CoreDisconnectedError
)

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT_SECONDS = 10.0
_CLOSE_TIMEOUT_SECONDS = 5.0
_DEFAULT_PING_INTERVAL_SECONDS = 20.0
_DEFAULT_PING_TIMEOUT_SECONDS = 10.0
_LISTENER_TASK_CANCEL_WAIT_SECONDS = 2.0


class WebSocketCommunicationManager(CommunicationManager):
    """Manages a WebSocket connection using the `websockets` library.

    This class implements the `CommunicationManager` interface for CPython
    environments, providing asynchronous WebSocket communication capabilities.
    """

    def __init__(self, url: str, task_manager: TaskManager,
                 ping_interval: Optional[float] = _DEFAULT_PING_INTERVAL_SECONDS,
                 ping_timeout: Optional[float] = _DEFAULT_PING_TIMEOUT_SECONDS):
        """Initializes the WebSocketCommunicationManager.

        Args:
            url: The WebSocket URL to connect to (e.g., "ws://localhost:5163").
            task_manager: The TaskManager instance for scheduling async operations
                          like the message listener and handler invocations.
            ping_interval: Interval in seconds for sending WebSocket keep-alive pings.
                           Set to `None` to disable automatic pings from this client.
            ping_timeout: Timeout in seconds for waiting for a pong response.
        """
        self._url = url
        self._task_manager = task_manager
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout

        self._ws_connection: Optional[websockets.client.WebSocketClientProtocol] = None
        self._status: CoreConnectionStatus = CoreConnectionStatus.DISCONNECTED
        self._connection_lock = asyncio.Lock() # For protecting connect/close ops

        self._message_handler: Optional[MessageHandlerType] = None
        self._status_change_handler: Optional[StatusChangeHandlerType] = None
        self._error_handler: Optional[ErrorHandlerType] = None

        self._listener_task: Optional[asyncio.Task] = None

    async def _invoke_handler_async(self, handler: Optional[Callable[..., Any]], *args: Any) -> None:
        """Safely invokes a handler, whether it's sync or async."""
        if not handler:
            return
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(*args)
            else:
                # For synchronous handlers, we run them in the current context
                # (which should be the loop thread if called from listener or task_manager task)
                # If this needs to be offloaded for long-running sync handlers,
                # task_manager.submit_task(loop.run_in_executor(...)) would be needed.
                # For now, assume sync handlers are quick or okay to run in loop.
                handler(*args)
        except Exception as e: # pragma: no cover
            logger.exception(f"Error invoking handler {handler.__name__}: {e}")
            # Optionally, report this to the main error handler as well
            if self._error_handler and handler is not self._error_handler: # Avoid recursive error reporting
                await self._invoke_handler_async(self._error_handler, e)


    async def _update_status_async(self, new_status: CoreConnectionStatus) -> None:
        """Internal helper to update status and notify handler."""
        if self._status == new_status:
            return
        logger.debug(f"WebSocket status changing from {self._status.name} to {new_status.name} for {self._url}")
        self._status = new_status
        if self._status_change_handler:
            # Schedule the handler invocation through the task manager to ensure
            # it runs on the loop and doesn't block critical paths if it's complex.
            # We wrap it in a simple coroutine.
            async def do_notify():
                await self._invoke_handler_async(self._status_change_handler, new_status)
            self._task_manager.submit_task(do_notify())


    async def connect_async(self) -> None:
        """Establishes the WebSocket connection asynchronously."""
        async with self._connection_lock:
            if self._status == CoreConnectionStatus.CONNECTED or self._status == CoreConnectionStatus.CONNECTING:
                logger.debug(f"Connection attempt skipped, already {self._status.name}.")
                return

            await self._update_status_async(CoreConnectionStatus.CONNECTING)
            logger.info(f"Attempting to connect to WebSocket: {self._url}")

            try:
                # The websockets.connect context manager handles opening and closing.
                # We need to manage the connection object more directly for a persistent connection.
                self._ws_connection = await websockets.connect(
                    self._url,
                    open_timeout=_CONNECT_TIMEOUT_SECONDS,
                    ping_interval=self._ping_interval,
                    ping_timeout=self._ping_timeout,
                    # close_timeout can be set if needed for graceful close handshake
                )
                logger.info(f"Successfully connected to WebSocket: {self._url}")
                await self._update_status_async(CoreConnectionStatus.CONNECTED)

                # Start the listener task if not already running from a previous attempt
                if self._listener_task and not self._listener_task.done(): # pragma: no cover
                    logger.warning("Listener task already exists and is not done. This should not happen.")
                    self._listener_task.cancel() # Attempt to cancel previous
                    try:
                        await asyncio.wait_for(self._listener_task, timeout=_LISTENER_TASK_CANCEL_WAIT_SECONDS)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass # Expected

                self._listener_task = self._task_manager.submit_task(self._listen_for_messages_async())
                logger.debug("WebSocket message listener task started.")

            except websockets.exceptions.InvalidURI as e: # pragma: no cover
                await self._handle_connection_failure_async(e, CoreConnectionRefusedError(self._url, e))
            except websockets.exceptions.WebSocketException as e: # Broad category for ws errors
                # More specific exceptions like ConnectionRefusedError, TimeoutError might be caught by websockets
                # and re-raised as WebSocketException or a subclass.
                # Check for common underlying OS errors.
                if isinstance(e.__cause__, ConnectionRefusedError) or "Connection refused" in str(e):
                    await self._handle_connection_failure_async(e, CoreConnectionRefusedError(self._url, e))
                elif isinstance(e.__cause__, TimeoutError) or "timed out" in str(e).lower(): # Timeout from OS or websockets
                    await self._handle_connection_failure_async(e, CoreConnectionTimeoutError(self._url, _CONNECT_TIMEOUT_SECONDS, e))
                else: # pragma: no cover
                    await self._handle_connection_failure_async(e, CoreConnectionError(f"WebSocket connection failed: {e}", url=self._url, original_exception=e))
            except OSError as e: # e.g., Host Down, Network Unreachable
                if e.errno == 111: # Connection refused
                    await self._handle_connection_failure_async(e, CoreConnectionRefusedError(self._url, e))
                else: # pragma: no cover
                    await self._handle_connection_failure_async(e, CoreConnectionError(f"OS error during WebSocket connection: {e}", url=self._url, original_exception=e))
            except asyncio.TimeoutError as e: # If websockets.connect itself times out due to open_timeout
                await self._handle_connection_failure_async(e, CoreConnectionTimeoutError(self._url, _CONNECT_TIMEOUT_SECONDS, e))
            except Exception as e: # Catch-all for unexpected errors
                await self._handle_connection_failure_async(e, CoreConnectionError(f"Unexpected error during WebSocket connection: {e}", url=self._url, original_exception=e))


    async def _handle_connection_failure_async(self, error: Exception, core_error_to_raise: CoreConnectionError) -> None:
        """Handles failures during the connection process."""
        logger.error(f"WebSocket connection to {self._url} failed: {error}")
        self._ws_connection = None # Ensure connection is None
        await self._update_status_async(CoreConnectionStatus.ERROR) # Or DISCONNECTED
        if self._error_handler:
            await self._invoke_handler_async(self._error_handler, error)
        raise core_error_to_raise


    async def _listen_for_messages_async(self) -> None:
        """Listens for incoming messages on the WebSocket connection."""
        logger.debug(f"WebSocket listener starting for {self._url}")
        try:
            while self._status == CoreConnectionStatus.CONNECTED and self._ws_connection:
                if self._ws_connection.closed: # Check before recv
                    logger.info("WebSocket connection found closed at start of listener iteration.")
                    if self._status == CoreConnectionStatus.CONNECTED: # If status wasn't updated yet
                        await self._update_status_async(CoreConnectionStatus.DISCONNECTED)
                    break
                try:
                    message_str = await self._ws_connection.recv()
                    if not isinstance(message_str, str): # pragma: no cover
                        # websockets typically returns str for text frames, bytes for binary
                        logger.warning(f"Received non-string message: {type(message_str)}. Assuming binary, ignoring.")
                        continue

                    logger.debug(f"WebSocket received: {message_str[:200]}{'...' if len(message_str) > 200 else ''}")
                    if self._message_handler:
                        await self._invoke_handler_async(self._message_handler, message_str)

                except websockets.exceptions.ConnectionClosedOK:
                    logger.info(f"WebSocket connection to {self._url} closed gracefully by server (OK).")
                    await self._update_status_async(CoreConnectionStatus.DISCONNECTED)
                    break
                except websockets.exceptions.ConnectionClosedError as e:
                    logger.warning(f"WebSocket connection to {self._url} closed with error: {e.code} {e.reason}")
                    await self._update_status_async(CoreConnectionStatus.ERROR) # Or DISCONNECTED
                    if self._error_handler:
                        await self._invoke_handler_async(self._error_handler, e)
                    break
                except websockets.exceptions.WebSocketException as e: # pragma: no cover
                    # Broader catch for other WebSocket issues during recv
                    logger.error(f"WebSocket listener error for {self._url}: {e}")
                    await self._update_status_async(CoreConnectionStatus.ERROR)
                    if self._error_handler:
                        await self._invoke_handler_async(self._error_handler, e)
                    # Depending on severity, might break or attempt to continue if recoverable
                    break # Usually safer to break on unexpected WebSocket errors
                except Exception as e: # pragma: no cover
                    # Catchall for unexpected errors in the listener loop
                    logger.exception(f"Unexpected error in WebSocket listener for {self._url}: {e}")
                    await self._update_status_async(CoreConnectionStatus.ERROR)
                    if self._error_handler:
                        await self._invoke_handler_async(self._error_handler, e)
                    break # Break on unknown errors
        except asyncio.CancelledError:
            logger.info(f"WebSocket listener task for {self._url} cancelled.")
        finally:
            logger.debug(f"WebSocket listener for {self._url} stopping.")
            # Ensure status reflects reality if loop exits due to connection issues
            if self._status == CoreConnectionStatus.CONNECTED: # pragma: no cover
                 # If we exit the loop but status is still CONNECTED, it implies an issue
                 logger.warning("Listener exited while status was CONNECTED. Setting to DISCONNECTED.")
                 await self._update_status_async(CoreConnectionStatus.DISCONNECTED)
            # Do not nullify self._listener_task here; close_async handles it.


    async def send_message_async(self, message_str: str) -> None:
        """Sends a string message over the WebSocket."""
        if self._status != CoreConnectionStatus.CONNECTED or not self._ws_connection or self._ws_connection.closed:
            err_msg = f"Cannot send message, WebSocket is not connected (status: {self._status.name})."
            logger.error(err_msg)
            raise CoreDisconnectedError(err_msg, reason=f"Current status: {self._status.name}")

        try:
            logger.debug(f"WebSocket sending: {message_str[:200]}{'...' if len(message_str) > 200 else ''}")
            await self._ws_connection.send(message_str)
        except websockets.exceptions.ConnectionClosed as e: # Covers ClosedOK and ClosedError
            err_msg = f"Failed to send message, WebSocket connection closed: {e}"
            logger.error(err_msg)
            await self._update_status_async(CoreConnectionStatus.DISCONNECTED if isinstance(e, websockets.exceptions.ConnectionClosedOK) else CoreConnectionStatus.ERROR)
            if self._error_handler and not isinstance(e, websockets.exceptions.ConnectionClosedOK):
                await self._invoke_handler_async(self._error_handler, e)
            raise CoreDisconnectedError(err_msg, reason=str(e), original_exception=e)
        except Exception as e: # pragma: no cover
            # For other unexpected send errors
            err_msg = f"Unexpected error sending WebSocket message: {e}"
            logger.exception(err_msg)
            # Assume connection is compromised
            await self._update_status_async(CoreConnectionStatus.ERROR)
            if self._error_handler:
                await self._invoke_handler_async(self._error_handler, e)
            raise CoreDisconnectedError(err_msg, reason=str(e), original_exception=e)


    async def close_async(self) -> None:
        """Closes the WebSocket connection asynchronously."""
        async with self._connection_lock:
            if self._status == CoreConnectionStatus.DISCONNECTED or self._status == CoreConnectionStatus.CLOSING:
                logger.debug(f"Close attempt skipped, already {self._status.name}.")
                return

            logger.info(f"Closing WebSocket connection to {self._url}")
            await self._update_status_async(CoreConnectionStatus.CLOSING)

            listener_task_to_cancel = self._listener_task
            self._listener_task = None # Prevent new listener from starting if connect is called again quickly

            if listener_task_to_cancel and not listener_task_to_cancel.done():
                logger.debug("Cancelling WebSocket listener task.")
                listener_task_to_cancel.cancel()
                try:
                    await asyncio.wait_for(listener_task_to_cancel, timeout=_LISTENER_TASK_CANCEL_WAIT_SECONDS)
                    logger.debug("Listener task successfully awaited after cancellation.")
                except asyncio.CancelledError:
                    logger.debug("Listener task was cancelled as expected.")
                except asyncio.TimeoutError: # pragma: no cover
                    logger.warning("Timeout waiting for listener task to finish after cancellation.")
                except Exception as e: # pragma: no cover
                    logger.exception(f"Error while awaiting cancelled listener task: {e}")


            if self._ws_connection and not self._ws_connection.closed:
                try:
                    logger.debug("Attempting to close WebSocket connection object.")
                    await asyncio.wait_for(self._ws_connection.close(), timeout=_CLOSE_TIMEOUT_SECONDS)
                    logger.info(f"WebSocket connection to {self._url} closed.")
                except asyncio.TimeoutError: # pragma: no cover
                    logger.warning(f"Timeout closing WebSocket connection to {self._url}.")
                except websockets.exceptions.WebSocketException as e: # pragma: no cover
                    logger.warning(f"WebSocket error during close for {self._url}: {e}")
                except Exception as e: # pragma: no cover
                    logger.exception(f"Unexpected error during WebSocket close for {self._url}: {e}")

            self._ws_connection = None
            await self._update_status_async(CoreConnectionStatus.DISCONNECTED)


    def register_message_handler(self, handler: MessageHandlerType) -> None:
        """Registers a callback for incoming messages."""
        logger.debug(f"Registering message handler: {handler}")
        self._message_handler = handler

    def register_status_change_handler(self, handler: StatusChangeHandlerType) -> None:
        """Registers a callback for connection status changes."""
        logger.debug(f"Registering status change handler: {handler}")
        self._status_change_handler = handler

    def register_error_handler(self, handler: Optional[ErrorHandlerType]) -> None:
        """Registers a callback for low-level communication errors."""
        logger.debug(f"Registering error handler: {handler}")
        self._error_handler = handler

    def is_connected(self) -> bool:
        """Checks if the WebSocket is actively connected."""
        return self._status == CoreConnectionStatus.CONNECTED and \
               self._ws_connection is not None and \
               not self._ws_connection.closed

    def get_current_status(self) -> CoreConnectionStatus:
        """Returns the current connection status."""
        return self._status