"""Defines the core connection status for communication channels.

This module provides the `CoreConnectionStatus` enumeration, which represents
the various states an underlying communication channel (like a WebSocket or
a Pyodide message bridge) can be in. This is a low-level status, distinct
from higher-level application-specific connection states.
"""

from enum import Enum, auto


class CoreConnectionStatus(Enum):
    """Represents the fundamental states of a communication channel.

    This enum is used by the `CommunicationManager` to track the health and
    status of the connection it manages.
    """
    DISCONNECTED = auto()
    """The channel is not connected.
    This is the initial state, or the state after a connection has been
    explicitly closed or has definitively failed and will not attempt
    automatic reconnection at this level.
    """

    CONNECTING = auto()
    """The channel is actively attempting to establish a connection.
    For example, a WebSocket client might be in the process of its handshake.
    """

    CONNECTED = auto()
    """The channel has successfully established an active connection.
    Data can (in principle) be sent and received over the transport layer.
    For example, a WebSocket connection is open.
    """

    CLOSING = auto()
    """The channel is in the process of gracefully closing the connection.
    This state might be entered before transitioning to DISCONNECTED
    during a clean shutdown.
    """

    ERROR = auto()
    """The channel has encountered an unrecoverable error.
    The connection is not usable and likely needs to be re-initialized
    (e.g., by creating a new channel instance) if communication is to
    be re-attempted.
    """

    def __str__(self) -> str:
        """Return a user-friendly string representation of the status."""
        return self.name
