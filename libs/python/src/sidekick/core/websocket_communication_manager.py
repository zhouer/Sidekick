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
    ErrorHandlerType  # ErrorHandlerType is already Optional in some contexts
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

_DEFAULT_OPEN_TIMEOUT_SECONDS = 5.0  # Timeout for establishing the initial connection.
_DEFAULT_CLOSE_TIMEOUT_SECONDS = 1.0 # Timeout for the graceful close handshake.
_DEFAULT_PING_INTERVAL_SECONDS = 20.0
_DEFAULT_PING_TIMEOUT_SECONDS = 10.0
_LISTENER_TASK_CANCEL_WAIT_SECONDS = 2.0 # Time to wait for listener task to exit after cancellation.


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
                operations, such as the message listener loop and handler invocations.
            open_timeout (Optional[float]): The timeout in seconds for establishing
                the initial connection. Defaults to `_DEFAULT_OPEN_TIMEOUT_SECONDS`.
            ping_interval (Optional[float]): The interval in seconds for sending
                WebSocket keep-alive pings from this client to the server.
                If `None`, automatic pings initiated by this client are disabled.
                Defaults to `_DEFAULT_PING_INTERVAL_SECONDS`.
            ping_timeout (Optional[float]): The timeout in seconds for waiting for a
                pong response from the server after a ping is sent. If a pong is
                not received within this time, the connection may be considered dead.
                Defaults to `_DEFAULT_PING_TIMEOUT_SECONDS`.
            close_timeout (Optional[float]): The timeout in seconds for the
                graceful close handshake when establishing the connection.
                Defaults to `_DEFAULT_CLOSE_TIMEOUT_SECONDS`.
        """
        self._url = url
        self._task_manager = task_manager
        self._open_timeout = open_timeout
        self._ping_interval = ping_interval
        self._ping_timeout = ping_timeout
        self._close_timeout = close_timeout

        self._ws_connection: Optional[websockets.client.WebSocketClientProtocol] = None
        self._status: CoreConnectionStatus = CoreConnectionStatus.DISCONNECTED
        # asyncio.Lock is used to protect critical sections during connect and close
        # operations, preventing race conditions if these methods are called concurrently.
        self._connection_lock = asyncio.Lock()

        self._message_handler: Optional[MessageHandlerType] = None
        self._status_change_handler: Optional[StatusChangeHandlerType] = None
        self._error_handler: Optional[ErrorHandlerType] = None # Now explicitly Optional

        self._listener_task: Optional[asyncio.Task] = None # Task for _listen_for_messages_async

    async def _invoke_handler_async(self, handler: Optional[Callable[..., Any]], *args: Any) -> None:
        """Safely invokes a registered handler (message, status, or error).

        This helper method checks if the handler is callable and if it's an
        async function. It then calls it appropriately. Any exceptions raised
        by the handler are caught and logged.

        Args:
            handler (Optional[Callable[..., Any]]): The handler function to invoke.
                If `None`, the method does nothing.
            *args (Any): Arguments to pass to the handler.
        """
        if not handler:
            return
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(*args)
            else:
                # Synchronous handlers are run directly. If they are long-running,
                # they could block the event loop if called from within it.
                # For Sidekick, handlers are generally expected to be quick or offload work.
                handler(*args)
        except Exception as e: # pragma: no cover
            logger.exception(f"An error occurred inside a registered handler ('{getattr(handler, '__name__', 'unknown_handler')}'): {e}")
            # Avoid recursive error reporting: if this is the error_handler itself failing, don't call it again.
            if self._error_handler and handler is not self._error_handler:
                # Report the handler's exception to the main error_handler.
                await self._invoke_handler_async(self._error_handler, e)


    async def _update_status_async(self, new_status: CoreConnectionStatus) -> None:
        """Internal helper to update the connection status and notify the status change handler.

        If the new status is the same as the current status, no action is taken.
        The status change handler is invoked asynchronously via the TaskManager.

        Args:
            new_status (CoreConnectionStatus): The new connection status to set.
        """
        if self._status == new_status:
            return # No change, do nothing.

        logger.debug(f"WebSocketCommunicationManager: Status changing from {self._status.name} to {new_status.name} for URL {self._url}")
        self._status = new_status

        if self._status_change_handler:
            # Schedule the handler invocation to run on the TaskManager's event loop.
            # This ensures the handler doesn't block critical paths and runs in the correct async context.
            async def do_notify_status_change():
                await self._invoke_handler_async(self._status_change_handler, new_status)

            try:
                self._task_manager.submit_task(do_notify_status_change())
            except Exception as e_submit: # pragma: no cover
                 logger.error(f"Failed to submit status change notification task: {e_submit}")

    async def connect_async(self) -> None:
        """Establishes the WebSocket connection to the configured URL asynchronously."""
        async with self._connection_lock: # Ensure only one connect/close operation at a time
            if self._status == CoreConnectionStatus.CONNECTED or self._status == CoreConnectionStatus.CONNECTING:
                logger.debug(
                    f"Connection attempt to {self._url} skipped: already {self._status.name}."
                )
                return

            await self._update_status_async(CoreConnectionStatus.CONNECTING)
            logger.info(f"Attempting to connect to WebSocket server at: {self._url}")

            try:
                # `websockets.connect` establishes the connection.
                # It takes an open_timeout for the handshake.
                # ping_interval and ping_timeout configure automatic keep-alive.
                self._ws_connection = await websockets.connect(
                    self._url,
                    open_timeout=self._open_timeout,
                    ping_interval=self._ping_interval,
                    ping_timeout=self._ping_timeout,
                    close_timeout=self._close_timeout,
                )
                logger.info(f"Successfully connected to WebSocket server: {self._url}")
                await self._update_status_async(CoreConnectionStatus.CONNECTED)

                # If a listener task from a previous connection attempt still exists and isn't done,
                # (e.g., if connect_async was called rapidly after a failure), cancel it.
                if self._listener_task and not self._listener_task.done(): # pragma: no cover
                    logger.warning("Previous listener task found active during new connection. Cancelling it.")
                    self._listener_task.cancel()
                    try:
                        # Give it a moment to process cancellation.
                        await asyncio.wait_for(self._listener_task, timeout=_LISTENER_TASK_CANCEL_WAIT_SECONDS)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass # Expected outcomes if it was running.
                    except Exception as e_await_old_listener:
                        logger.error(f"Error awaiting old listener task cancellation: {e_await_old_listener}")


                # Start the message listener task for this new connection.
                self._listener_task = self._task_manager.submit_task(self._listen_for_messages_async())
                logger.debug(f"WebSocket message listener task started for {self._url}.")

            except websockets.exceptions.InvalidURI as e_uri: # pragma: no cover
                # Error if the URL format is incorrect.
                await self._handle_connection_failure_async(e_uri, CoreConnectionRefusedError(self._url, e_uri))
            except asyncio.TimeoutError as e_timeout: # If websockets.connect itself times out.
                await self._handle_connection_failure_async(e_timeout, CoreConnectionTimeoutError(self._url, self._open_timeout, e_timeout))
            except websockets.exceptions.WebSocketException as e_ws:
                # This is a broad category for `websockets` library errors.
                # We try to map common underlying OS errors to more specific Core...Errors.
                if isinstance(e_ws.__cause__, ConnectionRefusedError) or \
                   (e_ws.args and "Connection refused" in str(e_ws.args[0])):
                    await self._handle_connection_failure_async(e_ws, CoreConnectionRefusedError(self._url, e_ws))
                elif isinstance(e_ws.__cause__, TimeoutError) or \
                     (e_ws.args and "timed out" in str(e_ws.args[0]).lower()):
                    await self._handle_connection_failure_async(e_ws, CoreConnectionTimeoutError(self._url, self._open_timeout, e_ws))
                else: # pragma: no cover
                    # Other WebSocket specific errors.
                    await self._handle_connection_failure_async(
                        e_ws,
                        CoreConnectionError(f"WebSocket connection failed: {e_ws}", url=self._url, original_exception=e_ws)
                    )
            except OSError as e_os: # Catches OS-level errors like host down, network unreachable.
                if e_os.errno == 111: # Specific error code for "Connection refused" on Linux.
                    await self._handle_connection_failure_async(e_os, CoreConnectionRefusedError(self._url, e_os))
                else: # pragma: no cover
                    await self._handle_connection_failure_async(
                        e_os,
                        CoreConnectionError(f"OS error during WebSocket connection: {e_os}", url=self._url, original_exception=e_os)
                    )
            except Exception as e_unexpected: # Catch-all for any other unexpected errors.
                 # pragma: no cover
                await self._handle_connection_failure_async(
                    e_unexpected,
                    CoreConnectionError(f"Unexpected error during WebSocket connection: {e_unexpected}", url=self._url, original_exception=e_unexpected)
                )

    async def _handle_connection_failure_async(self,
                                             error: Exception,
                                             core_error_to_raise: CoreConnectionError) -> None:
        """Helper method to process connection failures.

        It logs the error, updates the status, invokes the error handler (if registered),
        and then raises the provided `core_error_to_raise`.

        Args:
            error (Exception): The original exception that caused the failure.
            core_error_to_raise (CoreConnectionError): The specific `CoreConnectionError`
                subtype to raise after handling.
        """
        logger.error(f"WebSocket connection to {self._url} failed: {error}")
        self._ws_connection = None # Ensure connection object is cleared.
        await self._update_status_async(CoreConnectionStatus.ERROR) # Or DISCONNECTED, ERROR is more indicative of failure.

        if self._error_handler:
            await self._invoke_handler_async(self._error_handler, error)
        raise core_error_to_raise


    async def _listen_for_messages_async(self) -> None:
        """Continuously listens for incoming messages on the active WebSocket connection.

        This method runs as an asyncio Task. It iterates, awaiting new messages.
        If a message is received, it's passed to the registered message handler.
        The loop terminates if the connection closes, an error occurs, or the
        task is cancelled (e.g., during shutdown).
        """
        logger.debug(f"WebSocket message listener task starting for URL: {self._url}")
        try:
            # Loop as long as the connection is supposed to be active and the ws object exists.
            while self._status == CoreConnectionStatus.CONNECTED and self._ws_connection:
                if self._ws_connection.closed: # Double-check before awaiting recv
                    logger.info(
                        f"WebSocket connection to {self._url} found closed at the start of a listener iteration."
                    )
                    if self._status == CoreConnectionStatus.CONNECTED: # If status wasn't updated by another path
                        await self._update_status_async(CoreConnectionStatus.DISCONNECTED)
                    break # Exit listener loop.

                try:
                    message_data = await self._ws_connection.recv()
                    # `websockets` library returns `str` for text frames and `bytes` for binary.
                    # Sidekick protocol uses JSON strings, so we expect text.
                    if isinstance(message_data, str):
                        message_str = message_data
                        logger.debug(f"WebSocket received text message: {message_str[:200]}{'...' if len(message_str) > 200 else ''}")
                        if self._message_handler:
                            await self._invoke_handler_async(self._message_handler, message_str)
                    elif isinstance(message_data, bytes): # pragma: no cover
                        logger.warning(
                            f"Received unexpected binary message from {self._url} "
                            f"(length: {len(message_data)} bytes). Sidekick protocol expects text. Ignoring."
                        )
                        # Handle or log binary data if necessary, otherwise ignore.
                    else: # pragma: no cover
                        # Should not happen with current websockets library versions.
                        logger.error(
                            f"Received message of unexpected type '{type(message_data).__name__}' from {self._url}. Ignoring."
                        )

                except websockets.exceptions.ConnectionClosedOK:
                    logger.info(f"WebSocket connection to {self._url} was closed gracefully by the server (Close code OK).")
                    await self._update_status_async(CoreConnectionStatus.DISCONNECTED)
                    break # Exit listener loop.
                except websockets.exceptions.ConnectionClosedError as e_closed_err:
                    logger.warning(
                        f"WebSocket connection to {self._url} closed with an error: "
                        f"Code={e_closed_err.code}, Reason='{e_closed_err.reason}'. "
                        "This may indicate an issue on the server side or network."
                    )
                    # Transition to ERROR if closed abnormally, or DISCONNECTED if it's a known "going away" code.
                    # For simplicity here, using ERROR for any non-OK close.
                    await self._update_status_async(CoreConnectionStatus.ERROR)
                    if self._error_handler:
                        await self._invoke_handler_async(self._error_handler, e_closed_err)
                    break # Exit listener loop.
                except websockets.exceptions.WebSocketException as e_ws_recv: # pragma: no cover
                    # Catch other specific WebSocket errors during receive.
                    logger.error(f"A WebSocket error occurred in the listener for {self._url}: {e_ws_recv}")
                    await self._update_status_async(CoreConnectionStatus.ERROR)
                    if self._error_handler:
                        await self._invoke_handler_async(self._error_handler, e_ws_recv)
                    break # Usually safer to exit listener on unexpected WebSocket errors.
                except Exception as e_listener_unexpected: # pragma: no cover
                    # Catch-all for any other unexpected errors within the listener loop.
                    logger.exception(f"An unexpected error occurred in the WebSocket listener for {self._url}: {e_listener_unexpected}")
                    await self._update_status_async(CoreConnectionStatus.ERROR)
                    if self._error_handler:
                        await self._invoke_handler_async(self._error_handler, e_listener_unexpected)
                    break # Exit listener loop on unknown errors.
        except asyncio.CancelledError:
            # This is expected when the listener task is cancelled (e.g., during shutdown).
            logger.info(f"WebSocket message listener task for {self._url} was cancelled.")
        finally:
            logger.debug(f"WebSocket message listener task for {self._url} is stopping.")
            # If the listener exits for any reason (error, cancellation, normal close)
            # and the status was still CONNECTED, it means the connection effectively dropped.
            if self._status == CoreConnectionStatus.CONNECTED: # pragma: no cover
                 logger.warning(
                    f"Listener for {self._url} exited while status was still CONNECTED. "
                    "Updating status to DISCONNECTED to reflect reality."
                )
                 await self._update_status_async(CoreConnectionStatus.DISCONNECTED)
            # Do not nullify self._listener_task here; close_async or a new connect_async handles it.

    async def send_message_async(self, message_str: str) -> None:
        """Sends a string message over the active WebSocket connection."""
        if not self.is_connected(): # is_connected() checks status and ws_connection object
            err_msg = (
                f"Cannot send message via WebSocket: Not connected or connection object is invalid. "
                f"Current status: {self._status.name}."
            )
            logger.error(err_msg)
            raise CoreDisconnectedError(err_msg, reason=f"Status: {self._status.name}")

        # self._ws_connection should be non-None if is_connected() is true.
        # Add type assertion for linters after the check.
        current_ws_connection = self._ws_connection
        assert current_ws_connection is not None, "WebSocket connection object is None despite is_connected() being true."

        try:
            logger.debug(f"WebSocket sending message: {message_str[:200]}{'...' if len(message_str) > 200 else ''}")
            await current_ws_connection.send(message_str)
        except websockets.exceptions.ConnectionClosed as e_closed_send:
            # This covers ConnectionClosedOK and ConnectionClosedError.
            err_msg = f"Failed to send WebSocket message: Connection was closed. Code={e_closed_send.code}, Reason='{e_closed_send.reason}'"
            logger.error(err_msg)
            # Update status based on whether the close was graceful or an error.
            new_status = CoreConnectionStatus.DISCONNECTED if isinstance(e_closed_send, websockets.exceptions.ConnectionClosedOK) else CoreConnectionStatus.ERROR
            await self._update_status_async(new_status)
            # Report error if it wasn't a graceful (OK) close.
            if not isinstance(e_closed_send, websockets.exceptions.ConnectionClosedOK) and self._error_handler:
                await self._invoke_handler_async(self._error_handler, e_closed_send)
            raise CoreDisconnectedError(err_msg, reason=str(e_closed_send), original_exception=e_closed_send)
        except Exception as e_send_unexpected: # pragma: no cover
            # For other unexpected errors during send (e.g., OS errors, library bugs).
            err_msg = f"An unexpected error occurred while sending WebSocket message: {e_send_unexpected}"
            logger.exception(err_msg)
            # Assume the connection is compromised after an unexpected send error.
            await self._update_status_async(CoreConnectionStatus.ERROR)
            if self._error_handler:
                await self._invoke_handler_async(self._error_handler, e_send_unexpected)
            raise CoreDisconnectedError(err_msg, reason=str(e_send_unexpected), original_exception=e_send_unexpected)

    async def close_async(self) -> None:
        """Closes the WebSocket connection asynchronously."""
        async with self._connection_lock: # Ensure only one connect/close op at a time
            if self._status == CoreConnectionStatus.DISCONNECTED or self._status == CoreConnectionStatus.CLOSING:
                logger.debug(f"Close attempt for {self._url} skipped: connection already {self._status.name}.")
                return

            logger.info(f"Initiating close for WebSocket connection to {self._url}")
            await self._update_status_async(CoreConnectionStatus.CLOSING)

            # Store reference to listener task before nullifying self._listener_task,
            # to prevent race condition if connect_async is called again quickly.
            listener_task_to_await = self._listener_task
            self._listener_task = None # Prevent a new listener from using an old task reference.

            if listener_task_to_await and not listener_task_to_await.done():
                logger.debug(f"Cancelling active WebSocket listener task for {self._url}.")
                listener_task_to_await.cancel()
                try:
                    # Wait for the listener task to finish its cleanup after cancellation.
                    await asyncio.wait_for(listener_task_to_await, timeout=_LISTENER_TASK_CANCEL_WAIT_SECONDS)
                    logger.debug(f"Listener task for {self._url} successfully processed cancellation.")
                except asyncio.CancelledError:
                    logger.debug(f"Listener task for {self._url} was cancelled as expected during close.")
                except asyncio.TimeoutError: # pragma: no cover
                    logger.warning(
                        f"Timeout waiting for listener task of {self._url} to finish after cancellation. "
                        "It might be stuck."
                    )
                except Exception as e_await_cancel: # pragma: no cover
                    logger.exception(f"An error occurred while awaiting cancelled listener task for {self._url}: {e_await_cancel}")

            # Close the actual WebSocket connection object.
            if self._ws_connection and not self._ws_connection.closed:
                try:
                    logger.debug(f"Attempting to gracefully close WebSocket object for {self._url}.")
                    # websockets.close() has its own timeout mechanism if not specified.
                    await asyncio.wait_for(self._ws_connection.close(), timeout=_DEFAULT_CLOSE_TIMEOUT_SECONDS)
                    logger.info(f"WebSocket connection to {self._url} has been closed.")
                except asyncio.TimeoutError: # pragma: no cover
                    logger.warning(f"Timeout occurred while closing WebSocket connection to {self._url}.")
                except websockets.exceptions.WebSocketException as e_ws_close: # pragma: no cover
                    logger.warning(f"A WebSocket error occurred during close operation for {self._url}: {e_ws_close}")
                except Exception as e_close_unexpected: # pragma: no cover
                    logger.exception(f"An unexpected error occurred during WebSocket close for {self._url}: {e_close_unexpected}")

            self._ws_connection = None # Clear the connection object reference.
            await self._update_status_async(CoreConnectionStatus.DISCONNECTED)
            logger.info(f"WebSocketCommunicationManager for {self._url} is now fully DISCONNECTED.")


    def register_message_handler(self, handler: MessageHandlerType) -> None:
        """Registers a callback function to handle incoming raw string messages."""
        logger.debug(f"Registering message handler for WebSocket CM ({self._url}): {handler}")
        self._message_handler = handler

    def register_status_change_handler(self, handler: StatusChangeHandlerType) -> None:
        """Registers a callback function for connection status changes."""
        logger.debug(f"Registering status change handler for WebSocket CM ({self._url}): {handler}")
        self._status_change_handler = handler

    def register_error_handler(self, handler: Optional[ErrorHandlerType]) -> None:
        """Registers a callback function to handle low-level communication errors.
        Pass `None` to unregister.
        """
        logger.debug(f"Registering error handler for WebSocket CM ({self._url}): {handler}")
        self._error_handler = handler # MODIFIED: Directly assign, can be None

    def is_connected(self) -> bool:
        """Checks if the WebSocket is actively connected and the connection object is valid."""
        return self._status == CoreConnectionStatus.CONNECTED and \
               self._ws_connection is not None and \
               not self._ws_connection.closed

    def get_current_status(self) -> CoreConnectionStatus:
        """Returns the current `CoreConnectionStatus` of the WebSocket connection."""
        return self._status