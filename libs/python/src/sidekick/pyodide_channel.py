"""Pyodide direct communication for Sidekick.

This module implements the PyodideChannel class, which uses the JavaScript
functions sendHeroMessage and registerSidekickMessageHandler for direct communication
between Python code running in Pyodide and the Sidekick UI.
"""

import json
from typing import Dict, Any, Callable, Optional

from pyodide.ffi import create_proxy

from .channel import CommunicationChannel
from .errors import SidekickDisconnectedError
from . import logger

class PyodideChannel(CommunicationChannel):
    """Direct communication implementation for Pyodide environments.

    This class uses the JavaScript functions sendHeroMessage and registerSidekickMessageHandler
    to communicate between Python code running in Pyodide and the Sidekick UI.
    """

    def __init__(self):
        """Initialize the PyodideChannel."""
        self._handler = None
        self._handler_proxy = None
        self._connected = False

    def connect(self):
        """Establish the communication connection.

        This method sets up the communication by registering a message handler with
        the JavaScript side.

        Raises:
            SidekickDisconnectedError: If the connection cannot be established.
        """
        try:
            # Import JavaScript functions
            from js import registerSidekickMessageHandler

            logger.info("PyodideChannel: Setting up direct communication")

            # Define the message handler function
            def on_message(message):
                if self._handler:
                    try:
                        # Parse the JSON message
                        message_data = json.loads(message)
                        logger.debug(f"PyodideChannel: Received message: {message_data}")
                        self._handler(message_data)
                    except json.JSONDecodeError as e:
                        logger.error(f"PyodideChannel: Failed to parse JSON: {e}")
                    except Exception as e:
                        logger.exception(f"PyodideChannel: Error in message handler: {e}")

            # Create a persistent proxy for the function
            self._handler_proxy = create_proxy(on_message)

            # Register the proxied message handler
            registerSidekickMessageHandler(self._handler_proxy)
            self._connected = True

            logger.info("PyodideChannel: Communication established")

        except Exception as e:
            logger.exception(f"PyodideChannel: Failed to establish connection: {e}")
            self._connected = False
            raise SidekickDisconnectedError(f"Failed to establish connection: {e}")

    def send_message(self, message_dict: Dict[str, Any]):
        """Send a message to the JavaScript side.

        Args:
            message_dict (Dict[str, Any]): The message to send.

        Raises:
            SidekickDisconnectedError: If the connection is not established.
        """
        if not self._connected:
            raise SidekickDisconnectedError("PyodideChannel: Not connected")

        try:
            # Import JavaScript function
            from js import sendHeroMessage

            # Convert the message to JSON
            message_json = json.dumps(message_dict)
            logger.debug(f"PyodideChannel: Sending message: {message_json}")

            # Send the message
            sendHeroMessage(message_json)
        except Exception as e:
            logger.exception(f"PyodideChannel: Error sending message: {e}")
            raise SidekickDisconnectedError(f"Error sending message: {e}")

    def close(self):
        """Close the communication connection."""
        logger.info("PyodideChannel: Closing connection")

        try:
            # Release the proxy
            if self._handler_proxy:
                self._handler_proxy.destroy()
        except Exception as e:
            logger.warning(f"PyodideChannel: Error closing connection: {e}")
        finally:
            self._handler_proxy = None
            self._connected = False

    def is_connected(self) -> bool:
        """Check if the communication connection is established.

        Returns:
            bool: True if connected, False otherwise.
        """
        return self._connected

    def register_message_handler(self, handler: Callable[[Dict[str, Any]], None]):
        """Register a handler for incoming messages.

        Args:
            handler (Callable[[Dict[str, Any]], None]): The handler function to call
                when a message is received.
        """
        self._handler = handler
