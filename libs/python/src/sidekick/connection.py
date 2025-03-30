# Sidekick/libs/python/src/sidekick/connection.py
import websocket # Using websocket-client library
import json
import threading
import atexit
import time
import logging
from typing import Optional, Dict, Any, Callable, cast

# --- Logging Setup ---
# Ensure logging is configured only once, check if handlers already exist
logger = logging.getLogger("SidekickConn")
if not logger.hasHandlers():
    logger.setLevel(logging.INFO) # Default level, can be changed by application
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    # Use StreamHandler by default, or configure as needed elsewhere
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)


# --- Configuration and State ---
_ws_url = "ws://localhost:5163"
_ws_connection: Optional[websocket.WebSocket] = None
_connection_lock = threading.Lock()
_connection_active = False # Flag to indicate if connection is intentionally active
_listener_thread: Optional[threading.Thread] = None
_listener_started = False
# Registry for message handlers: key = instance_id, value = callback function
_message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}

# WebSocket Keep-Alive settings (in seconds)
_PING_INTERVAL = 20 # Send a ping every 20 seconds
_PING_TIMEOUT = 10  # Wait up to 10 seconds for a pong response
_INITIAL_CONNECT_TIMEOUT = 5 # Timeout ONLY for the initial connection attempt

# --- Public Functions ---

def set_url(url: str):
    """Sets the WebSocket server URL. Must be called before the first connection attempt."""
    global _ws_url
    with _connection_lock:
        if _ws_connection:
            logger.warning("Cannot change URL after connection is established. Close connection first.")
            return
        if not url.startswith(("ws://", "wss://")):
             logger.warning(f"Invalid WebSocket URL scheme: {url}. Using default: {_ws_url}")
             return
        _ws_url = url
        logger.info(f"Sidekick WebSocket URL set to: {_ws_url}")

def activate_connection():
    """Marks the connection as intentionally active, allowing connection attempts."""
    global _connection_active
    with _connection_lock:
        if not _connection_active:
             _connection_active = True
             logger.debug("Sidekick connection marked as active.")

def get_connection() -> Optional[websocket.WebSocket]:
    """
    Gets the singleton WebSocket connection, establishing it if necessary.
    Uses a timeout for initial connection, then disables socket timeout,
    relying on WebSocket PING/PONG for keep-alive.
    """
    global _ws_connection, _connection_active, _listener_thread, _listener_started
    # Quick check without lock first for performance
    if _ws_connection and _ws_connection.connected:
        return _ws_connection

    with _connection_lock:
        # Double-check connection status after acquiring lock
        if _ws_connection and _ws_connection.connected:
            return _ws_connection

        if not _connection_active:
             logger.debug("Connection is not active. Not attempting to connect.")
             return None

        logger.info(f"Attempting to connect to Sidekick server at {_ws_url}...")
        try:
            _ws_connection = websocket.create_connection(
                _ws_url,
                timeout=_INITIAL_CONNECT_TIMEOUT, # Use INITIAL timeout here
                ping_interval=_PING_INTERVAL,     # Enable automatic pings
                ping_timeout=_PING_TIMEOUT        # Timeout for pong response
            )
            logger.info("Successfully connected to Sidekick server.")

            # --- CRITICAL CHANGE: Disable socket timeout after connection ---
            logger.debug("Disabling socket read timeout, relying on WebSocket Ping/Pong.")
            _ws_connection.settimeout(None)
            # -------------------------------------------------------------

            # Start the listener thread only once per connection period
            if not _listener_started:
                logger.info("Starting WebSocket listener thread.")
                _listener_thread = threading.Thread(target=_listen_for_messages, daemon=True)
                _listener_thread.start()
                _listener_started = True

            return _ws_connection
        # Catch specific websocket timeout error related to pings
        except websocket.WebSocketTimeoutException as e:
            # This error is specifically for PINGs not getting PONGs back in time
            logger.error(f"WebSocket ping timeout: Server did not respond to ping. {e}")
            _ws_connection = None
            _connection_active = False
            _listener_started = False
            return None
        # Catch general timeout error (should primarily happen during initial connect now)
        except TimeoutError as e:
             logger.error(f"Connection attempt timed out after {_INITIAL_CONNECT_TIMEOUT} seconds. {e}")
             _ws_connection = None
             _connection_active = False
             _listener_started = False
             return None
        # Catch other potential connection errors
        except (websocket.WebSocketException, ConnectionRefusedError, OSError) as e:
            logger.error(f"Failed to connect to Sidekick server at {_ws_url}: {e}")
            _ws_connection = None
            _connection_active = False # Mark as inactive on failure
            _listener_started = False # Allow restarting listener on next successful connect
            return None
        except Exception as e: # Catch any other unexpected error during connection
            logger.exception(f"Unexpected error during connection: {e}")
            _ws_connection = None
            _connection_active = False
            _listener_started = False
            return None


def send_message(message_dict: Dict[str, Any]):
    """Sends a JSON message over the WebSocket connection."""
    ws = get_connection()
    if ws:
        # Acquire lock for sending to prevent potential race conditions from multiple threads
        with _connection_lock:
            # Check connection again after acquiring lock
            if not (ws and ws.connected):
                 logger.warning(f"Cannot send message, WebSocket disconnected before sending. Message: {message_dict}")
                 return

            try:
                message_json = json.dumps(message_dict)
                logger.debug(f"Sending message: {message_json}")
                ws.send(message_json)
            except (websocket.WebSocketException, BrokenPipeError, OSError) as e:
                logger.error(f"Error sending message: {e}. Closing connection.")
                # Attempt to close the broken connection from the sending side
                close_connection(log_info=False) # Don't log standard closure message
            except Exception as e:
                logger.exception(f"Unexpected error sending message: {e}") # Log full traceback
    else:
        # Reduce log noise if connection is intentionally inactive
        if _connection_active:
             logger.warning(f"Cannot send message, WebSocket not connected. Message: {message_dict}")
        else:
             logger.debug(f"WebSocket not active, message suppressed: {message_dict}")

def close_connection(log_info=True):
    """Closes the WebSocket connection if it's open."""
    global _ws_connection, _connection_active, _listener_thread, _listener_started, _message_handlers
    with _connection_lock:
        was_active = _connection_active
        _connection_active = False # Mark as inactive FIRST to signal listener thread
        _listener_started = False # Reset listener flag

        ws_temp = _ws_connection # Use a temporary variable inside the lock
        _ws_connection = None # Set global var to None immediately

        if ws_temp:
            if log_info and was_active: # Only log closure info if it was meant to be active
                logger.info("Closing WebSocket connection.")
            try:
                ws_temp.close()
            except (websocket.WebSocketException, OSError, Exception) as e: # Catch broader errors during close
                 logger.error(f"Error during WebSocket close(): {e}")

        # Clear handlers when connection is closed
        if _message_handlers:
            logger.debug("Clearing message handlers.")
            _message_handlers.clear()

def register_message_handler(instance_id: str, handler: Callable[[Dict[str, Any]], None]):
    """Registers a callback function to handle messages from a specific module instance."""
    if not callable(handler):
        logger.error(f"Handler for instance '{instance_id}' is not callable.")
        return
    with _connection_lock: # Protect access to shared handler dict
        logger.info(f"Registering message handler for instance '{instance_id}'.")
        _message_handlers[instance_id] = handler

def unregister_message_handler(instance_id: str):
    """Unregisters the callback function for a specific module instance."""
    with _connection_lock: # Protect access to shared handler dict
        if instance_id in _message_handlers:
            logger.info(f"Unregistering message handler for instance '{instance_id}'.")
            del _message_handlers[instance_id]
        else:
            logger.debug(f"No message handler found for instance '{instance_id}' to unregister.")

# --- Private Helper Functions ---

def _listen_for_messages():
    """Function run in a separate thread to listen for incoming WebSocket messages."""
    global _connection_active, _message_handlers, _listener_started
    logger.info("Listener thread started.")

    # Loop as long as the connection is intended to be active
    while _connection_active:
        ws = None
        # Get current connection reference safely under lock
        with _connection_lock:
             if _ws_connection and _ws_connection.connected:
                 ws = _ws_connection
             elif not _connection_active: # Check active flag inside lock too
                  break # Exit loop if intentionally deactivated

        if ws: # If we got a valid, connected ws instance
            try:
                # ws.recv() will now block indefinitely until data or error/close
                message_str = ws.recv()

                if not message_str: # Handle server closing connection gracefully
                    if _connection_active: # Only log if we didn't expect it
                        logger.info("Listener: Server closed connection (received empty message).")
                    break # Exit loop

                logger.debug(f"Listener: Received raw message: {message_str}")

                # Safely parse JSON
                try:
                    message_data = json.loads(message_str)
                    if not isinstance(message_data, dict):
                        logger.warning(f"Listener: Received non-dict JSON: {message_data}")
                        continue
                except json.JSONDecodeError:
                    logger.error(f"Listener: Failed to parse JSON message: {message_str}")
                    continue

                # Process the message
                instance_id = message_data.get('src') # 'src' indicates the originating instance in Sidekick
                if instance_id:
                     # Get handler within lock, but call it outside lock to prevent deadlocks
                     handler = None
                     with _connection_lock:
                         # Check active flag again before getting handler
                         if not _connection_active: break
                         handler = _message_handlers.get(instance_id)

                     if handler:
                         logger.debug(f"Listener: Invoking handler for instance '{instance_id}'.")
                         try:
                             handler(message_data) # Call the registered handler
                         except Exception as e:
                             logger.exception(f"Listener: Error executing handler for instance '{instance_id}': {e}")
                     else:
                          logger.debug(f"Listener: No handler registered for instance '{instance_id}'.")
                else:
                    logger.debug(f"Listener: Received message without 'src' field: {message_data}")

            except websocket.WebSocketConnectionClosedException:
                if _connection_active: # Log only if unexpected
                     logger.info("Listener: WebSocket connection closed.")
                break # Exit loop gracefully
            except websocket.WebSocketTimeoutException:
                 # This indicates the PING mechanism failed (no PONG received)
                 if _connection_active:
                      logger.error("Listener: WebSocket ping timeout. Connection lost.")
                 break # Exit loop, connection is dead
            except OSError as e: # Catch network errors
                if _connection_active:
                    logger.warning(f"Listener: OS error occurred ({e}), likely connection closed.")
                break
            except Exception as e:
                if _connection_active: # Only log if error occurred during active phase
                     logger.exception(f"Listener: Unexpected error receiving/processing message: {e}")
                with _connection_lock:
                    if not (_ws_connection and _ws_connection.connected and _connection_active):
                        if _connection_active:
                             logger.warning("Listener: Connection lost or inactive after error, exiting.")
                        break
                    else:
                         if _connection_active:
                              logger.error("Listener: Exiting due to unexpected error.")
                         break
        else:
            # If ws is None or not connected, wait before checking again
            if _connection_active: # Only log sleep message if we are trying to be active
                logger.debug("Listener: Connection not available, sleeping...")
            # Check active flag frequently even while sleeping
            slept = 0
            while slept < 1.0 and _connection_active:
                 time.sleep(0.1)
                 slept += 0.1
            if not _connection_active: # Exit outer loop if deactivated during sleep
                 break

    # Cleanup after loop exits
    logger.info("Listener thread finished.")
    with _connection_lock: # Ensure flag is reset under lock
        _listener_started = False # Allow restarting if connect is called again
        if _connection_active and _ws_connection:
             logger.warning("Listener thread exited unexpectedly while connection was marked active. Attempting cleanup.")
             _connection_active = False


# --- Automatic Cleanup ---
# Register the close function to be called upon script exit
atexit.register(close_connection)