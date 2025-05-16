"""Defines the abstract base class for managing low-level communication channels.

This module provides the `CommunicationManager` Abstract Base Class (ABC).
Concrete implementations of this class will handle the specifics of different
communication transports, such as WebSockets (for CPython environments) or
JavaScript `postMessage` (for Pyodide environments).

The `CommunicationManager` is responsible for:
- Establishing and tearing down the raw communication link.
- Sending and receiving raw string-based messages.
- Reporting connection status changes (using `CoreConnectionStatus`).
- Reporting underlying communication errors.
- Allowing higher-level services (like `ConnectionService`) to register
  handlers for incoming messages, status changes, and errors.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Union, Any, Optional # Added Optional for error_handler

from .status import CoreConnectionStatus


# Define a type alias for handler functions for clarity.
# Handlers can be synchronous or asynchronous.
MessageHandlerType = Callable[[str], Union[None, Awaitable[None]]]
StatusChangeHandlerType = Callable[[CoreConnectionStatus], Union[None, Awaitable[None]]]
ErrorHandlerType = Callable[[Exception], Union[None, Awaitable[None]]]


class CommunicationManager(ABC):
    """Abstract Base Class for managing a raw communication channel.

    Implementations will abstract the underlying transport (e.g., WebSocket,
    Pyodide message passing) and provide a consistent interface for sending
    and receiving string-based messages, and for monitoring connection status.
    """

    @abstractmethod
    async def connect_async(self) -> None:
        """Establishes the connection to the remote endpoint asynchronously.

        Implementations should handle the specifics of the chosen transport protocol
        (e.g., WebSocket handshake).

        After a successful connection, the status should typically transition to
        `CoreConnectionStatus.CONNECTED`. If connection fails, an appropriate
        `CoreConnectionError` (e.g., `CoreConnectionRefusedError`,
        `CoreConnectionTimeoutError`) should be raised.

        Raises:
            CoreConnectionError: If the connection cannot be established.
        """
        pass

    @abstractmethod
    async def close_async(self) -> None:
        """Closes the communication channel asynchronously.

        Implementations should gracefully terminate the connection.
        The status should typically transition to `CoreConnectionStatus.CLOSING`
        and then `CoreConnectionStatus.DISCONNECTED`.
        """
        pass

    @abstractmethod
    async def send_message_async(self, message_str: str) -> None:
        """Sends a string message over the communication channel asynchronously.

        Args:
            message_str: The raw string message to send. Serialization (e.g., to JSON)
                         is expected to be handled by the caller.

        Raises:
            CoreDisconnectedError: If the channel is not connected or if the send fails
                                   due to a broken connection.
            Exception: Other transport-specific exceptions might be raised if the send fails
                       for reasons other than disconnection.
        """
        pass

    @abstractmethod
    def register_message_handler(self, handler: MessageHandlerType) -> None:
        """Registers a callback function to handle incoming raw string messages.

        The provided `handler` will be called whenever a new message string is
        received on the communication channel. The manager should handle calling
        the handler appropriately, whether it's synchronous or an awaitable coroutine.

        If a handler was previously registered, this new handler should replace it.
        To unregister, one might pass `None`, or a dedicated unregister method
        could be added if needed.

        Args:
            handler: A callable that accepts a single string argument (the message)
                     and returns `None` or an `Awaitable[None]`.
        """
        pass

    @abstractmethod
    def register_status_change_handler(self, handler: StatusChangeHandlerType) -> None:
        """Registers a callback function to be notified of connection status changes.

        The `handler` will be invoked whenever the `CoreConnectionStatus` of the
        communication channel changes (e.g., from `CONNECTING` to `CONNECTED`, or
        `CONNECTED` to `DISCONNECTED`).

        Args:
            handler: A callable that accepts a `CoreConnectionStatus` enum member
                     and returns `None` or an `Awaitable[None]`.
        """
        pass

    @abstractmethod
    def register_error_handler(self, handler: Optional[ErrorHandlerType]) -> None:
        """Registers a callback function to handle low-level communication errors.

        This handler is for errors originating from the communication transport
        itself (e.g., a WebSocket error event, an unhandled exception in the
        message listening loop). These are typically errors that might lead to
        disconnection or indicate a problem with the channel.

        Args:
            handler: A callable that accepts a single `Exception` argument
                     and returns `None` or an `Awaitable[None]`. Pass `None`
                     to unregister a previously set handler.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Checks if the communication channel is currently in a connected state.

        This typically means the status is `CoreConnectionStatus.CONNECTED`.

        Returns:
            bool: True if the channel is actively connected, False otherwise.
        """
        pass

    @abstractmethod
    def get_current_status(self) -> CoreConnectionStatus:
        """Returns the current `CoreConnectionStatus` of the channel.

        Returns:
            CoreConnectionStatus: The current connection status.
        """
        pass