"""WebSocket-based implementation of the CommunicationManager.

This module provides `WebSocketCommunicationManager`, which uses the `websockets`
library to manage a WebSocket connection to a remote server. It handles
sending and receiving messages, managing connection state, and invoking
registered handlers for messages, status changes, and errors. This implementation
is typically used in standard CPython environments.
"""

import asyncio
import logging
import websockets # type: ignore[import-untyped]
from typing import Callable, Optional, Any

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

_DEFAULT_OPEN_TIMEOUT_SECONDS = 5.0
_DEFAULT_CLOSE_TIMEOUT_SECONDS = 1.0
_DEFAULT_PING_INTERVAL_SECONDS = 20.0
_DEFAULT_PING_TIMEOUT_SECONDS = 10.0
_LISTENER_TASK_CANCEL_WAIT_SECONDS = 2.0


class WebSocketCommunicationManager(CommunicationManager):
    """Manages a WebSocket connection using the `websockets` library.

    This class implements the `CommunicationManager` interface for CPython
    environments, providing asynchronous WebSocket communication capabilities.
    It handles the connection lifecycle, message transmission and reception,
    and keep-alive pings.
    """

    def __init__(self,
                 url: str,
                 task_manager: TaskManager,
                 open_timeout: Optional[float] = _DEFAULT_OPEN_TIMEOUT_SECONDS,
                 ping_interval: Optional[float] = _DEFAULT_PING_INTERVAL_SECONDS,
                 ping_timeout: Optional[float] = _DEFAULT_PING_TIMEOUT_SECONDS,
                 close_timeout: Optional[float] = _DEFAULT_CLOSE_TIMEOUT_SECONDS):
        """Initializes the WebSocketCommunicationManager.

        Args:
            url (str): The WebSocket URL to connect to (e.g., "ws://localhost:5163").
            task_manager (TaskManager): The TaskManager instance that this
                CommunicationManager will use for scheduling its asynchronous
                operations, such as the message listener loop.
            open_timeout (Optional[float]): Timeout for establishing the initial connection.
            ping_interval (Optional[float]): Interval for sending keep-alive pings.
                If `None`, client-side pings are disabled.
            ping_timeout (Optional[float]): Timeout for waiting for a pong response.
            close_timeout (Optional[float]): Timeout for the graceful close handshake.
        """
        self._url = url
        self._task_manager = task_manager
        self._open_timeout = open_timeout
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._close_timeout = close_timeout

        self._ws_connection: Optional[websockets.client.WebSocketClientProtocol] = None
        self._status: CoreConnectionStatus = CoreConnectionStatus.DISCONNECTED
        self._connection_lock = asyncio.Lock()

        self._message_handler: Optional[MessageHandlerType] = None
        self._status_change_handler: Optional[StatusChangeHandlerType] = None
        self._error_handler: Optional[ErrorHandlerType] = None

        self._listener_task: Optional[asyncio.Task] = None

    async def _invoke_handler_async(self, handler: Optional[Callable[..., Any]], *args: Any) -> None:
        """Safely invokes a registered handler (sync or async)."""
        if not handler: return
        try:
            if asyncio.iscoroutinefunction(handler): await handler(*args)
            else: handler(*args)
        except Exception as e: # pragma: no cover
            logger.exception(f"An error occurred inside a registered handler ('{getattr(handler, '__name__', 'unknown_handler')}'): {e}")
            if self._error_handler and handler is not self._error_handler:
                await self._invoke_handler_async(self._error_handler, e)

    async def _update_status_async(self, new_status: CoreConnectionStatus) -> None:
        """Internal helper to update status and notify the status change handler."""
        if self._status == new_status: return
        logger.debug(f"WebSocketCommunicationManager: Status changing from {self._status.name} to {new_status.name} for URL {self._url}")
        self._status = new_status
        if self._status_change_handler:
            async def do_notify_status_change():
                await self._invoke_handler_async(self._status_change_handler, new_status)
            try: self._task_manager.submit_task(do_notify_status_change())
            except Exception as e_submit: logger.error(f"Failed to submit status change notification task: {e_submit}")

    async def connect_async(
        self,
        message_handler: Optional[MessageHandlerType] = None,
        status_change_handler: Optional[StatusChangeHandlerType] = None,
        error_handler: Optional[ErrorHandlerType] = None
    ) -> None:
        """Establishes or configures the WebSocket connection.

        This method can be called in two phases:
        1.  Initial connection: Called with no handlers to simply establish the
            WebSocket link. If successful, the status becomes `CONNECTED`.
        2.  Handler attachment: Called on an already connected instance to
            attach or update the message/status/error handlers and start the
            message listener task if it's not already running.

        Args:
            message_handler (Optional[MessageHandlerType]): Callback for incoming messages.
            status_change_handler (Optional[StatusChangeHandlerType]): Callback for status changes.
            error_handler (Optional[ErrorHandlerType]): Callback for communication errors.

        Raises:
            CoreConnectionError: If the connection attempt fails.
        """
        async with self._connection_lock:
            # Store/update handlers first, regardless of connection state.
            self._message_handler = message_handler
            self._status_change_handler = status_change_handler
            self._error_handler = error_handler

            # If already connected, just ensure the listener is running and return.
            # This handles the second phase (attaching handlers).
            if self._status == CoreConnectionStatus.CONNECTED:
                logger.debug(f"connect_async called on an already connected CM for {self._url}. Attaching/updating handlers.")
                if not self._listener_task or self._listener_task.done():
                    logger.info("CM is connected but listener task is not running. Starting it now.")
                    self._listener_task = self._task_manager.submit_task(self._listen_for_messages_async())
                return

            if self._status == CoreConnectionStatus.CONNECTING:
                logger.debug(f"Connection attempt to {self._url} already in progress.")
                return

            # --- Begin initial connection phase ---
            await self._update_status_async(CoreConnectionStatus.CONNECTING)
            logger.info(f"Attempting to connect to WebSocket server at: {self._url}")

            try:
                self._ws_connection = await websockets.connect(
                    self._url, open_timeout=self._open_timeout, ping_interval=self._ping_interval,
                    ping_timeout=self._ping_timeout, close_timeout=self._close_timeout,
                )
                logger.info(f"Successfully connected to WebSocket server: {self._url}")
                await self._update_status_async(CoreConnectionStatus.CONNECTED)

                # If handlers were provided in this initial call, start the listener.
                if self._message_handler:
                    if self._listener_task and not self._listener_task.done(): self._listener_task.cancel()
                    self._listener_task = self._task_manager.submit_task(self._listen_for_messages_async())
                    logger.debug(f"WebSocket message listener task started for {self._url}.")

            except (websockets.exceptions.InvalidURI, asyncio.TimeoutError, websockets.exceptions.WebSocketException, OSError) as e:
                # Failure during connection attempt.
                await self._handle_connection_failure_async(e)
                # Re-raise a specific core exception for the ServerConnector to handle.
                if isinstance(e, ConnectionRefusedError) or (isinstance(e, OSError) and e.errno == 111):
                    raise CoreConnectionRefusedError(self._url, e) from e
                if isinstance(e, asyncio.TimeoutError):
                    raise CoreConnectionTimeoutError(self._url, self._open_timeout, e) from e
                raise CoreConnectionError(f"WebSocket connection failed: {e}", url=self._url, original_exception=e) from e
            except Exception as e_unexpected:
                await self._handle_connection_failure_async(e_unexpected)
                raise CoreConnectionError(f"Unexpected error during WebSocket connection: {e_unexpected}", url=self._url, original_exception=e_unexpected) from e_unexpected

    async def _handle_connection_failure_async(self, error: Exception) -> None:
        """Helper method to process connection failures."""
        logger.error(f"WebSocket connection to {self._url} failed: {error}")
        self._ws_connection = None
        await self._update_status_async(CoreConnectionStatus.ERROR)
        if self._error_handler:
            await self._invoke_handler_async(self._error_handler, error)

    async def _listen_for_messages_async(self) -> None:
        """Continuously listens for incoming messages on the active WebSocket connection."""
        logger.debug(f"WebSocket message listener task starting for URL: {self._url}")
        try:
            # The loop continues as long as the connection is considered active.
            while self.is_connected() and self._ws_connection:
                try:
                    message_data = await self._ws_connection.recv()
                    if isinstance(message_data, str):
                        if self._message_handler: await self._invoke_handler_async(self._message_handler, message_data)
                    else: logger.warning(f"Received unexpected binary message from {self._url}. Ignoring.")
                except websockets.exceptions.ConnectionClosedOK:
                    await self._update_status_async(CoreConnectionStatus.DISCONNECTED); break
                except websockets.exceptions.ConnectionClosedError as e_closed_err:
                    await self._update_status_async(CoreConnectionStatus.ERROR)
                    if self._error_handler: await self._invoke_handler_async(self._error_handler, e_closed_err)
                    break
                except websockets.exceptions.WebSocketException as e_ws_recv:
                    await self._update_status_async(CoreConnectionStatus.ERROR)
                    if self._error_handler: await self._invoke_handler_async(self._error_handler, e_ws_recv)
                    break
        except asyncio.CancelledError:
            logger.info(f"WebSocket message listener task for {self._url} was cancelled.")
        finally:
            logger.debug(f"WebSocket message listener task for {self._url} is stopping.")
            if self.is_connected(): await self._update_status_async(CoreConnectionStatus.DISCONNECTED)

    async def send_message_async(self, message_str: str) -> None:
        """Sends a string message over the active WebSocket connection."""
        if not self.is_connected() or not self._ws_connection:
            raise CoreDisconnectedError(f"Cannot send message, not connected. Status: {self._status.name}")
        try:
            await self._ws_connection.send(message_str)
        except websockets.exceptions.ConnectionClosed as e:
            new_status = CoreConnectionStatus.DISCONNECTED if isinstance(e, websockets.exceptions.ConnectionClosedOK) else CoreConnectionStatus.ERROR
            await self._update_status_async(new_status)
            if new_status == CoreConnectionStatus.ERROR and self._error_handler: await self._invoke_handler_async(self._error_handler, e)
            raise CoreDisconnectedError(f"Failed to send message: Connection closed.", reason=str(e), original_exception=e) from e

    async def close_async(self) -> None:
        """Closes the WebSocket connection asynchronously."""
        async with self._connection_lock:
            if self._status in [CoreConnectionStatus.DISCONNECTED, CoreConnectionStatus.CLOSING]: return
            await self._update_status_async(CoreConnectionStatus.CLOSING)
            if (task := self._listener_task) and not task.done():
                task.cancel()
                try: await asyncio.wait_for(task, timeout=_LISTENER_TASK_CANCEL_WAIT_SECONDS)
                except (asyncio.CancelledError, asyncio.TimeoutError): pass
            if (conn := self._ws_connection) and not conn.closed:
                try: await asyncio.wait_for(conn.close(), timeout=_DEFAULT_CLOSE_TIMEOUT_SECONDS)
                except (asyncio.TimeoutError, websockets.exceptions.WebSocketException): pass
            self._ws_connection = None
            self._message_handler = self._status_change_handler = self._error_handler = None
            await self._update_status_async(CoreConnectionStatus.DISCONNECTED)

    def is_connected(self) -> bool:
        """Checks if the WebSocket is actively connected."""
        return self._status == CoreConnectionStatus.CONNECTED and self._ws_connection is not None and not self._ws_connection.closed

    def get_current_status(self) -> CoreConnectionStatus:
        """Returns the current `CoreConnectionStatus`."""
        return self._status
