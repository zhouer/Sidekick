"""Abstract communication channel interface for Sidekick.

This module defines the abstract base class for communication channels used by Sidekick.
Different implementations of this interface can be used for different environments,
such as WebSocket for standard Python and direct JavaScript functions for Pyodide.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Optional

class CommunicationChannel(ABC):
    """Abstract base class for communication channels.

    This class defines the interface that all communication channel implementations
    must follow. It provides methods for connecting, sending messages, and handling
    incoming messages.
    """

    @abstractmethod
    def connect(self):
        """Establish the connection.

        This method should establish the connection to the Sidekick server or UI.
        It may return different values depending on the implementation.

        Raises:
            SidekickConnectionError: If the connection cannot be established.
        """
        pass

    @abstractmethod
    def send_message(self, message_dict: Dict[str, Any]):
        """Send a message.

        Args:
            message_dict (Dict[str, Any]): The message to send.

        Raises:
            SidekickDisconnectedError: If the connection is lost or not established.
        """
        pass

    @abstractmethod
    def close(self):
        """Close the connection.

        This method should close the connection and clean up any resources.
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Check if connected.

        Returns:
            bool: True if the connection is established, False otherwise.
        """
        pass

    @abstractmethod
    def register_message_handler(self, handler: Callable[[Dict[str, Any]], None]):
        """Register a handler for incoming messages.

        Args:
            handler (Callable[[Dict[str, Any]], None]): The handler function to call
                when a message is received.
        """
        pass

def create_communication_channel(url: str = "ws://localhost:5163") -> CommunicationChannel:
    """Create the appropriate communication channel based on environment.

    This factory function detects the environment and creates the appropriate
    communication channel implementation.

    Args:
        url (str): The WebSocket URL to connect to if using WebSocketChannel.
            Default is "ws://localhost:5163".

    Returns:
        CommunicationChannel: An instance of a concrete CommunicationChannel implementation.
    """
    # Check if running in Pyodide
    try:
        import pyodide
        # We're in Pyodide environment
        from .pyodide_channel import PyodideChannel
        return PyodideChannel()
    except ImportError:
        # Not in Pyodide, use WebSocket
        from .websocket_channel import WebSocketChannel
        return WebSocketChannel(url)
