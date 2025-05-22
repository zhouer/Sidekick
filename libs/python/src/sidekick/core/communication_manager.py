"""Defines the abstract base class for managing low-level communication channels.

This module provides the `CommunicationManager` Abstract Base Class (ABC).
Concrete implementations of this class will handle the specifics of different
communication transports, such as WebSockets (for CPython environments) or
JavaScript `postMessage` (for Pyodide environments).

The `CommunicationManager` is responsible for:
- Establishing and tearing down the raw communication link (e.g., WebSocket connection).
- Sending raw string-based messages over the established link.
- Receiving raw string-based messages from the link.
- Reporting changes in the connection status (using `CoreConnectionStatus`).
- Notifying about underlying communication errors that might occur.
- Allowing higher-level services (like `ConnectionService`) to register callback
  functions to handle incoming messages, status changes, and errors.

This abstraction allows the rest of the Sidekick system to interact with different
communication methods through a consistent interface.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Union, Any, Optional # Ensure Optional is imported

from .status import CoreConnectionStatus


# Define type aliases for handler functions to improve readability and maintainability.
# These handlers can be either synchronous functions or asynchronous coroutine functions.

MessageHandlerType = Callable[[str], Union[None, Awaitable[None]]]
"""Type alias for a function that handles incoming raw string messages.
It accepts the message string and returns None or an Awaitable.
"""

StatusChangeHandlerType = Callable[[CoreConnectionStatus], Union[None, Awaitable[None]]]
"""Type alias for a function that handles connection status changes.
It accepts a CoreConnectionStatus enum member and returns None or an Awaitable.
"""

ErrorHandlerType = Callable[[Exception], Union[None, Awaitable[None]]]
"""Type alias for a function that handles low-level communication errors.
It accepts an Exception object and returns None or an Awaitable.
"""


class CommunicationManager(ABC):
    """Abstract Base Class for managing a raw communication channel.

    Implementations of this class will abstract the specifics of the underlying
    transport mechanism (e.g., WebSockets, Pyodide's JavaScript message passing)
    and provide a standardized interface for:
    - Connecting to and disconnecting from a remote endpoint.
    - Sending and receiving string-based messages.
    - Monitoring the connection status.
    - Registering callbacks for messages, status changes, and errors.
    """

    @abstractmethod
    async def connect_async(self) -> None:
        """Establishes the connection to the remote endpoint asynchronously.

        Implementations should handle the complete process of setting up the
        communication link according to the chosen transport protocol (e.g.,
        performing a WebSocket handshake).

        Upon successful connection, the manager's status should transition to
        `CoreConnectionStatus.CONNECTED`. If the connection attempt fails, an
        appropriate `CoreConnectionError` (such as `CoreConnectionRefusedError`
        or `CoreConnectionTimeoutError`) should be raised to indicate the failure.

        Raises:
            CoreConnectionError: If the connection cannot be established due to
                refusal, timeout, or other transport-level issues.
        """
        pass

    @abstractmethod
    async def close_async(self) -> None:
        """Closes the communication channel asynchronously.

        Implementations should gracefully terminate the connection. This might
        involve sending close frames (for WebSockets) or releasing resources.
        The status should typically transition through `CoreConnectionStatus.CLOSING`
        and eventually to `CoreConnectionStatus.DISCONNECTED`.
        This method should be idempotent; calling it multiple times on an already
        closed or closing connection should not cause errors.
        """
        pass

    @abstractmethod
    async def send_message_async(self, message_str: str) -> None:
        """Sends a string message over the communication channel asynchronously.

        The caller is responsible for ensuring the `message_str` is formatted
        according to the expected protocol (e.g., as a JSON string).

        Args:
            message_str (str): The raw string message to send.

        Raises:
            CoreDisconnectedError: If the channel is not currently connected or if
                the send operation fails due to a broken or closed connection.
            Exception: Other transport-specific exceptions might be raised if the
                send fails for reasons other than disconnection (e.g., message
                too large for buffer, underlying socket errors).
        """
        pass

    @abstractmethod
    def register_message_handler(self, handler: MessageHandlerType) -> None:
        """Registers a callback function to handle incoming raw string messages.

        The provided `handler` will be invoked by the CommunicationManager
        whenever a new message string is received from the remote endpoint.
        The manager is responsible for correctly calling the handler, whether
        it's a synchronous function or an awaitable coroutine.

        If a handler was previously registered, calling this method again with a
        new handler will replace the old one. To remove a handler, one might
        pass `None` or a dedicated `unregister_message_handler` could be added
        if more complex handler management is needed.

        Args:
            handler (MessageHandlerType): A callable that accepts a single string
                argument (the received message) and returns `None` or an
                `Awaitable[None]`.
        """
        pass

    @abstractmethod
    def register_status_change_handler(self, handler: StatusChangeHandlerType) -> None:
        """Registers a callback function to be notified of connection status changes.

        The `handler` will be invoked whenever the `CoreConnectionStatus` of the
        communication channel changes (e.g., from `CONNECTING` to `CONNECTED`, or
        from `CONNECTED` to `DISCONNECTED`). This allows higher-level services
        to react to the state of the underlying connection.

        Args:
            handler (StatusChangeHandlerType): A callable that accepts a
                `CoreConnectionStatus` enum member as its argument and returns
                `None` or an `Awaitable[None]`.
        """
        pass

    @abstractmethod
    def register_error_handler(self, handler: Optional[ErrorHandlerType]) -> None:
        """Registers a callback function to handle low-level communication errors.

        This handler is intended for errors that originate from the communication
        transport layer itself. These are typically errors that might lead to
        disconnection or indicate a significant problem with the channel's health
        (e.g., a WebSocket error event, an unhandled exception in the message
        listening loop if not caught and translated into a status change).

        Args:
            handler (Optional[ErrorHandlerType]): A callable that accepts a single
                `Exception` object as its argument and returns `None` or an
                `Awaitable[None]`. Pass `None` to unregister a previously set
                error handler.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Checks if the communication channel is currently in an active, connected state.

        A "connected" state typically means the status is `CoreConnectionStatus.CONNECTED`
        and the underlying transport link is open and usable for sending/receiving data.

        Returns:
            bool: True if the channel is actively connected, False otherwise.
        """
        pass

    @abstractmethod
    def get_current_status(self) -> CoreConnectionStatus:
        """Returns the current `CoreConnectionStatus` of the communication channel.

        This provides the most up-to-date known state of the connection according
        to the manager.

        Returns:
            CoreConnectionStatus: The current connection status.
        """
        pass