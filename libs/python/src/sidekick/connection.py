# Sidekick/libs/python/src/sidekick/connection.py
import websocket # Using websocket-client library
import json
import threading
import atexit
import time
import logging
from typing import Optional, Dict, Any, Callable, cast

# --- Logging Setup ---
logger = logging.getLogger("SidekickConn")
if not logger.hasHandlers():
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.propagate = False


# --- Configuration and State ---
_ws_url = "ws://localhost:5163"
_ws_connection: Optional[websocket.WebSocket] = None
_connection_lock = threading.Lock()
_connection_active = False
_listener_thread: Optional[threading.Thread] = None
_listener_started = False
_message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
_command_counter = 0 # Counter for generating unique command IDs

# WebSocket Keep-Alive settings (in seconds)
_PING_INTERVAL = 20
_PING_TIMEOUT = 10
_INITIAL_CONNECT_TIMEOUT = 5

# --- Public Functions ---

def set_url(url: str):
    """
    Sets the WebSocket server URL for Sidekick.

    This must be called *before* the first attempt to connect (e.g., before
    creating the first Sidekick module instance). Once a connection is established,
    the URL cannot be changed without closing the connection first.

    Args:
        url: The WebSocket URL (e.g., "ws://localhost:5163", "wss://example.com/sidekick").
             Must start with "ws://" or "wss://".
    """
    global _ws_url
    with _connection_lock:
        if _ws_connection and _ws_connection.connected:
            logger.warning("Cannot change URL after connection is established. Close connection first.")
            return
        if not url.startswith(("ws://", "wss://")):
             logger.warning(f"Invalid WebSocket URL scheme: {url}. Using default: {_ws_url}")
             return
        _ws_url = url
        logger.info(f"Sidekick WebSocket URL set to: {_ws_url}")

def activate_connection():
    """
    Signals the intention to use the Sidekick connection.

    This function is typically called internally by module constructors.
    It allows the connection attempt in `get_connection()` to proceed.
    """
    global _connection_active
    with _connection_lock:
        if not _connection_active:
             _connection_active = True
             logger.debug("Sidekick connection marked as active.")

def get_connection() -> Optional[websocket.WebSocket]:
    """
    Retrieves the singleton WebSocket connection instance.

    If the connection doesn't exist or is disconnected, and the connection
    is marked as active (`activate_connection()` was called), this function
    will attempt to establish a new connection.

    It uses a specific timeout for the initial connection attempt and then
    relies solely on WebSocket Ping/Pong frames for keep-alive by disabling
    the underlying socket's read timeout.

    Returns:
        The active websocket.WebSocket instance, or None if connection failed
        or is not marked as active.
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
                timeout=_INITIAL_CONNECT_TIMEOUT, # Timeout for initial connect ONLY
                ping_interval=_PING_INTERVAL,     # Enable automatic pings for keep-alive
                ping_timeout=_PING_TIMEOUT        # Timeout for server's pong response
            )
            logger.info("Successfully connected to Sidekick server.")

            # Disable socket read timeout after successful connection, rely on Ping/Pong
            logger.debug("Disabling socket read timeout, relying on WebSocket Ping/Pong.")
            _ws_connection.settimeout(None)

            # Start the listener thread only once per connection period
            if not _listener_started:
                logger.info("Starting WebSocket listener thread.")
                _listener_thread = threading.Thread(target=_listen_for_messages, daemon=True)
                _listener_thread.start()
                _listener_started = True

            return _ws_connection
        # Catch specific websocket timeout error related to pings
        except websocket.WebSocketTimeoutException as e:
            logger.error(f"WebSocket ping timeout: Server did not respond to ping. {e}")
            _ws_connection = None; _connection_active = False; _listener_started = False
            return None
        # Catch general timeout error (primarily during initial connect)
        except TimeoutError as e:
             logger.error(f"Connection attempt timed out after {_INITIAL_CONNECT_TIMEOUT} seconds. {e}")
             _ws_connection = None; _connection_active = False; _listener_started = False
             return None
        # Catch other potential connection errors
        except (websocket.WebSocketException, ConnectionRefusedError, OSError) as e:
            logger.error(f"Failed to connect to Sidekick server at {_ws_url}: {e}")
            _ws_connection = None; _connection_active = False; _listener_started = False
            return None
        except Exception as e: # Catch any other unexpected error during connection
            logger.exception(f"Unexpected error during connection: {e}")
            _ws_connection = None; _connection_active = False; _listener_started = False
            return None


def send_message(message_dict: Dict[str, Any]):
    """
    Sends a Python dictionary as a JSON message over the WebSocket connection.

    Internal function, typically called by module helper methods like `_send_command`.

    Args:
        message_dict: The dictionary to send. Keys within the 'payload' sub-dictionary
                      should ideally be camelCase to match frontend expectations.
    """
    ws = get_connection()
    if ws:
        with _connection_lock: # Acquire lock for sending
            if not (ws and ws.connected):
                 logger.warning(f"Cannot send message, WebSocket disconnected before sending. Message: {message_dict}")
                 return

            try:
                message_json = json.dumps(message_dict)
                logger.debug(f"Sending message: {message_json}")
                ws.send(message_json)
            except (websocket.WebSocketException, BrokenPipeError, OSError) as e:
                logger.error(f"Error sending message: {e}. Closing connection.")
                close_connection(log_info=False) # Attempt to close broken connection
            except Exception as e:
                logger.exception(f"Unexpected error sending message: {e}")
    else:
        if _connection_active:
             logger.warning(f"Cannot send message, WebSocket not connected. Message: {message_dict}")
        else:
             logger.debug(f"WebSocket not active, message suppressed: {message_dict}")

def close_connection(log_info=True):
    """
    Closes the WebSocket connection and cleans up resources.

    This is automatically called on script exit via `atexit`, but can be
    called manually if needed.

    Args:
        log_info: Whether to log the "Closing connection" message.
    """
    global _ws_connection, _connection_active, _listener_thread, _listener_started, _message_handlers
    with _connection_lock:
        was_active = _connection_active
        _connection_active = False # Mark as inactive FIRST to signal listener thread
        _listener_started = False # Reset listener flag

        ws_temp = _ws_connection
        _ws_connection = None # Set global var to None immediately

        if ws_temp:
            if log_info and was_active:
                logger.info("Closing WebSocket connection.")
            try:
                ws_temp.close()
            except (websocket.WebSocketException, OSError, Exception) as e:
                 logger.error(f"Error during WebSocket close(): {e}")

        # Clear handlers when connection is closed
        if _message_handlers:
            logger.debug("Clearing message handlers.")
            _message_handlers.clear()

def register_message_handler(instance_id: str, handler: Callable[[Dict[str, Any]], None]):
    """
    Registers a callback function to handle messages received from a specific module instance.

    Args:
        instance_id: The unique ID (`target_id`) of the module instance.
        handler: The function to call when a message with `src` matching `instance_id` arrives.
                 The handler receives the full message dictionary.
    """
    if not callable(handler):
        logger.error(f"Handler for instance '{instance_id}' is not callable.")
        return
    with _connection_lock: # Protect access to shared handler dict
        logger.info(f"Registering message handler for instance '{instance_id}'.")
        _message_handlers[instance_id] = handler

def unregister_message_handler(instance_id: str):
    """
    Unregisters the callback function for a specific module instance.

    Args:
        instance_id: The unique ID (`target_id`) of the module instance whose handler should be removed.
    """
    with _connection_lock: # Protect access to shared handler dict
        if instance_id in _message_handlers:
            logger.info(f"Unregistering message handler for instance '{instance_id}'.")
            del _message_handlers[instance_id]
        else:
            logger.debug(f"No message handler found for instance '{instance_id}' to unregister.")

def get_next_command_id() -> int:
    """
    Generates a sequential ID for commands (like Canvas drawing ops).

    Returns:
        A unique integer ID for the current session.
    """
    global _command_counter
    with _connection_lock: # Protect counter access
        _command_counter += 1
        return _command_counter

# --- Private Helper Functions ---

def _listen_for_messages():
    """
    Background thread function to continuously listen for incoming WebSocket messages.

    Parses messages, identifies the source module (`src`), and dispatches
    the message to the registered handler (if any) for that `src` ID.
    Handles connection closures and errors.
    """
    global _connection_active, _message_handlers, _listener_started
    logger.info("Listener thread started.")

    while _connection_active:
        ws = None
        with _connection_lock: # Get current connection reference safely
             if _ws_connection and _ws_connection.connected:
                 ws = _ws_connection
             elif not _connection_active: break

        if ws:
            try:
                message_str = ws.recv() # Blocks until data or error/close

                if not message_str: # Handle server closing connection
                    if _connection_active: logger.info("Listener: Server closed connection (received empty message).")
                    break

                logger.debug(f"Listener: Received raw message: {message_str}")

                try:
                    message_data = json.loads(message_str)
                    if not isinstance(message_data, dict):
                        logger.warning(f"Listener: Received non-dict JSON: {message_data}")
                        continue
                except json.JSONDecodeError:
                    logger.error(f"Listener: Failed to parse JSON message: {message_str}")
                    continue

                # Process the message - Dispatch based on 'src' field
                instance_id = message_data.get('src') # 'src' identifies the Sidekick module instance
                if instance_id:
                     handler = None
                     with _connection_lock: # Get handler safely
                         if not _connection_active: break
                         handler = _message_handlers.get(instance_id)

                     if handler: # Call handler outside the lock
                         logger.debug(f"Listener: Invoking handler for instance '{instance_id}'.")
                         try: handler(message_data)
                         except Exception as e: logger.exception(f"Listener: Error executing handler for instance '{instance_id}': {e}")
                     else: logger.debug(f"Listener: No handler registered for instance '{instance_id}'.")
                else:
                     # Log messages without 'src' (could be errors from Sidekick, etc.)
                     logger.debug(f"Listener: Received message without 'src' field: {message_data}")

            except websocket.WebSocketConnectionClosedException:
                if _connection_active: logger.info("Listener: WebSocket connection closed.")
                break
            except websocket.WebSocketTimeoutException:
                 # This indicates the PING mechanism failed (no PONG received)
                 if _connection_active: logger.error("Listener: WebSocket ping timeout. Connection lost.")
                 break
            except OSError as e: # Catch network errors during recv
                if _connection_active: logger.warning(f"Listener: OS error occurred ({e}), likely connection closed.")
                break
            except Exception as e:
                if _connection_active: logger.exception(f"Listener: Unexpected error receiving/processing message: {e}")
                break # Exit on unexpected errors
        else:
            # If connection is temporarily unavailable but still active, wait briefly
            if _connection_active:
                 logger.debug("Listener: Connection not available, sleeping...")
                 time.sleep(0.5) # Wait a bit before retrying get_connection implicitly

    # Cleanup after loop exits
    logger.info("Listener thread finished.")
    with _connection_lock:
        _listener_started = False # Allow restarting if connect is called again

# --- Automatic Cleanup ---
atexit.register(close_connection)