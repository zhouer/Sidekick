"""WebSocket communication channel for Sidekick.

This module implements the WebSocketChannel class, which uses WebSockets
for communication between the Python script and the Sidekick UI.
"""

import websocket
import json
import threading
import time
from typing import Dict, Any, Callable, Optional

from .channel import CommunicationChannel
from .errors import (
    SidekickConnectionError,
    SidekickConnectionRefusedError,
    SidekickTimeoutError,
    SidekickDisconnectedError
)
from . import logger

class WebSocketChannel(CommunicationChannel):
    """WebSocket implementation of the CommunicationChannel interface.
    
    This class uses the websocket-client library to establish a WebSocket connection
    to the Sidekick server.
    """
    
    def __init__(self, url: str = "ws://localhost:5163"):
        """Initialize the WebSocketChannel.
        
        Args:
            url (str): The WebSocket URL to connect to.
                Default is "ws://localhost:5163".
        """
        self._ws_url = url
        self._ws_connection = None
        self._connection_lock = threading.RLock()
        self._listener_thread = None
        self._listener_started = False
        self._message_handler = None
        self._stop_event = threading.Event()
        
        # WebSocket Ping settings
        self._PING_INTERVAL = 20  # Send a WebSocket PING frame every 20 seconds
        self._PING_TIMEOUT = 10   # Wait a maximum of 10 seconds for a PONG reply
        self._INITIAL_CONNECT_TIMEOUT = 5.0  # Max seconds to wait for connection
        self._LISTENER_RECV_TIMEOUT = 1.0    # Timeout for ws.recv() in listener loop
    
    def connect(self):
        """Establish the WebSocket connection.
        
        Raises:
            SidekickConnectionRefusedError: If the connection cannot be established.
        """
        with self._connection_lock:
            if self._ws_connection and self._ws_connection.connected:
                logger.debug("WebSocketChannel: Already connected.")
                return
            
            logger.info(f"WebSocketChannel: Attempting to connect to {self._ws_url}...")
            self._stop_event.clear()
            
            try:
                self._ws_connection = websocket.create_connection(
                    self._ws_url,
                    timeout=self._INITIAL_CONNECT_TIMEOUT,
                    ping_interval=self._PING_INTERVAL,
                    ping_timeout=self._PING_TIMEOUT
                )
                logger.info("WebSocketChannel: Successfully connected to Sidekick server.")
                
                # Start the listener thread if not already running
                if not self._listener_started and not (self._listener_thread and self._listener_thread.is_alive()):
                    logger.info("WebSocketChannel: Starting listener thread.")
                    self._listener_thread = threading.Thread(target=self._listen_for_messages, daemon=True)
                    self._listener_thread.start()
                    self._listener_started = True
                
            except (websocket.WebSocketException, ConnectionRefusedError, OSError, TimeoutError) as e:
                logger.error(f"WebSocketChannel: Failed to connect to {self._ws_url}: {e}")
                self._ws_connection = None
                self._stop_event.set()
                self._listener_started = False
                raise SidekickConnectionRefusedError(self._ws_url, e)
            except Exception as e:
                logger.exception(f"WebSocketChannel: Unexpected error during connection: {e}")
                self._ws_connection = None
                self._stop_event.set()
                self._listener_started = False
                raise SidekickConnectionRefusedError(self._ws_url, e)
    
    def send_message(self, message_dict: Dict[str, Any]):
        """Send a message through the WebSocket connection.
        
        Args:
            message_dict (Dict[str, Any]): The message to send.
            
        Raises:
            SidekickDisconnectedError: If the connection is lost or not established.
        """
        with self._connection_lock:
            if not self._ws_connection or not self._ws_connection.connected:
                raise SidekickDisconnectedError("WebSocketChannel: Not connected")
            
            try:
                message_json = json.dumps(message_dict)
                logger.debug(f"WebSocketChannel: Sending: {message_json}")
                self._ws_connection.send(message_json)
            except (websocket.WebSocketException, BrokenPipeError, OSError) as e:
                logger.error(f"WebSocketChannel: Send error: {e}")
                raise SidekickDisconnectedError(f"WebSocketChannel: Send failed: {e}")
            except Exception as e:
                logger.exception(f"WebSocketChannel: Unexpected send error: {e}")
                raise SidekickDisconnectedError(f"WebSocketChannel: Unexpected send error: {e}")
    
    def close(self):
        """Close the WebSocket connection."""
        with self._connection_lock:
            logger.info("WebSocketChannel: Closing connection.")
            self._stop_event.set()
            
            if self._ws_connection:
                try:
                    self._ws_connection.close()
                except Exception as e:
                    logger.warning(f"WebSocketChannel: Error closing connection: {e}")
                finally:
                    self._ws_connection = None
            
            self._listener_started = False
    
    def is_connected(self) -> bool:
        """Check if the WebSocket connection is established.
        
        Returns:
            bool: True if connected, False otherwise.
        """
        with self._connection_lock:
            return self._ws_connection is not None and self._ws_connection.connected
    
    def register_message_handler(self, handler: Callable[[Dict[str, Any]], None]):
        """Register a handler for incoming messages.
        
        Args:
            handler (Callable[[Dict[str, Any]], None]): The handler function to call
                when a message is received.
        """
        with self._connection_lock:
            self._message_handler = handler
    
    def _listen_for_messages(self):
        """Background thread that listens for incoming WebSocket messages."""
        logger.info("WebSocketChannel: Listener thread started.")
        
        while not self._stop_event.is_set():
            # Check if we still have a valid connection
            with self._connection_lock:
                if not self._ws_connection or not self._ws_connection.connected:
                    logger.warning("WebSocketChannel: Connection lost or unavailable.")
                    break
                ws = self._ws_connection
            
            try:
                # Wait for a message with timeout to allow checking _stop_event
                ws.settimeout(self._LISTENER_RECV_TIMEOUT)
                message_str = ws.recv()
                
                # Check if stop was signaled during recv()
                if self._stop_event.is_set():
                    break
                
                # Empty message means server closed connection
                if not message_str:
                    logger.info("WebSocketChannel: Server closed the connection.")
                    break
                
                logger.debug(f"WebSocketChannel: Received: {message_str}")
                message_data = json.loads(message_str)
                
                # Process the message
                with self._connection_lock:
                    if self._stop_event.is_set():
                        break
                    
                    if self._message_handler:
                        try:
                            self._message_handler(message_data)
                        except Exception as e:
                            logger.exception(f"WebSocketChannel: Error in message handler: {e}")
                
            except websocket.WebSocketTimeoutException:
                # Expected due to timeout, just continue
                continue
            except websocket.WebSocketConnectionClosedException:
                logger.info("WebSocketChannel: Connection closed by server.")
                break
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"WebSocketChannel: Failed to parse JSON: {e}")
                continue
            except OSError as e:
                # Ignore "Bad file descriptor" if stopping
                if not (self._stop_event.is_set() and e.errno == 9):
                    logger.warning(f"WebSocketChannel: OS error: {e}")
                    break
            except Exception as e:
                logger.exception(f"WebSocketChannel: Unexpected error: {e}")
                break
        
        logger.info("WebSocketChannel: Listener thread finished.")
        
        with self._connection_lock:
            self._listener_started = False
            
            # If stopped unexpectedly, clean up
            if not self._stop_event.is_set():
                logger.warning("WebSocketChannel: Listener thread stopped unexpectedly.")
                # Create a separate thread for cleanup to avoid deadlocks
                cleanup_thread = threading.Thread(
                    target=self.close,
                    daemon=False
                )
                cleanup_thread.start()