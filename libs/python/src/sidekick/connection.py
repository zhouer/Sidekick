# Sidekick/libs/python/src/sidekick/connection.py
import websocket # Using websocket-client library
import json
import threading
import atexit
import time
import logging
import uuid
from collections import deque
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable, Deque, List, Set

# --- Version Import ---
try:
    from ._version import __version__
except ImportError:
    __version__ = 'unknown' # Fallback version

# --- Logging Setup ---
logger = logging.getLogger("SidekickConn")
# (Logging setup remains the same as before - ensuring it exists)
if not logger.hasHandlers():
    logger.setLevel(logging.INFO) # Default INFO, can be changed by user
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.propagate = False

# --- Connection Status Enum ---
class ConnectionStatus(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED_WAITING_SIDEKICK = auto() # Connected to server, waiting for Sidekick announce
    CONNECTED_READY = auto()            # Connected and Sidekick is online

# --- Configuration and State ---
_ws_url: str = "ws://localhost:5163"
_ws_connection: Optional[websocket.WebSocket] = None
_connection_lock = threading.RLock() # Use RLock for potential re-entrant calls
_listener_thread: Optional[threading.Thread] = None
_listener_started: bool = False
# Maps instance_id to the internal handler of the module instance
_message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
_command_counter: int = 0 # Counter for Canvas command IDs

# -- New State Variables --
_peer_id: Optional[str] = None # Unique ID for this Hero instance
_connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
_sidekick_peers_online: Set[str] = set() # Store peerIds of online sidekicks
_message_buffer: Deque[Dict[str, Any]] = deque() # Buffer for non-system messages
_clear_on_connect: bool = True
_clear_on_disconnect: bool = False
# Global handler for all incoming messages
_global_message_handler: Optional[Callable[[Dict[str, Any]], None]] = None

# WebSocket Keep-Alive settings (remains the same)
_PING_INTERVAL = 20
_PING_TIMEOUT = 10
_INITIAL_CONNECT_TIMEOUT = 5

# --- Private Helper Functions ---

def _generate_peer_id() -> str:
    """Generates and returns the unique peer ID for this Hero instance."""
    global _peer_id
    if _peer_id is None:
        _peer_id = f"hero-{uuid.uuid4().hex}"
        logger.info(f"Generated Hero Peer ID: {_peer_id}")
    return _peer_id

def _send_raw(ws: websocket.WebSocket, message_dict: Dict[str, Any]):
    """Internal: Sends the message dictionary directly over the WebSocket."""
    # Assumes lock is held by caller if necessary
    try:
        message_json = json.dumps(message_dict)
        logger.debug(f"Sending raw: {message_json}")
        ws.send(message_json)
    except (websocket.WebSocketException, BrokenPipeError, OSError) as e:
        logger.error(f"WebSocket send error: {e}. Closing connection.")
        # Use a separate thread or schedule cleanup to avoid deadlock if called from listener
        threading.Thread(target=close_connection, args=(False,), daemon=True).start()
    except Exception as e:
        logger.exception(f"Unexpected error sending message: {e}")

def _send_system_announce(status: str):
    """Sends the system announce message."""
    # This function might be called before connection is fully 'READY'
    # It needs to acquire the connection directly if available
    with _connection_lock:
        ws = _ws_connection # Get current connection object safely
        peer_id = _generate_peer_id() # Ensure peer ID exists
        if ws and ws.connected and peer_id:
            announce_payload = {
                "peerId": peer_id,
                "role": "hero",
                "status": status,
                "version": __version__,
                "timestamp": int(time.time() * 1000)
            }
            message = {
                "id": 0,
                "module": "system",
                "type": "announce",
                "payload": announce_payload
            }
            _send_raw(ws, message)
            logger.info(f"Sent system announce: {status}")
        elif status == "offline":
             logger.debug("Cannot send offline announce, connection already closed.")
        else:
             logger.warning(f"Cannot send system announce '{status}', WebSocket not connected.")


def _flush_message_buffer():
    """Sends all messages currently in the buffer."""
    # Assumes lock is held by the caller (_handle_sidekick_online)
    if not _message_buffer:
        return

    ws = _ws_connection
    if not (ws and ws.connected and _connection_status == ConnectionStatus.CONNECTED_READY):
        logger.warning("Cannot flush buffer, connection not ready.")
        return

    logger.info(f"Flushing {len(_message_buffer)} buffered messages...")
    while _message_buffer:
        message_to_send = _message_buffer.popleft()
        _send_raw(ws, message_to_send)
    logger.info("Message buffer flushed.")

def _handle_sidekick_online(sidekick_peer_id: str):
    """Handles logic when the first Sidekick announces online."""
    # Assumes lock is held by the caller (_listen_for_messages)
    global _connection_status
    if _connection_status == ConnectionStatus.CONNECTED_WAITING_SIDEKICK:
        logger.info(f"Sidekick '{sidekick_peer_id}' announced online. System is READY.")
        _connection_status = ConnectionStatus.CONNECTED_READY
        if _clear_on_connect:
            logger.info("clear_on_connect is True, sending global/clearAll.")
            # Need to release and re-acquire lock? No, RLock allows re-entrancy.
            # Call the public clear_all which calls send_message
            clear_all() # This will now succeed as status is READY
        _flush_message_buffer()

def _listen_for_messages():
    """Background thread function to listen for incoming messages."""
    global _connection_status, _message_handlers, _sidekick_peers_online, _listener_started, _global_message_handler
    logger.info("Listener thread started.")

    while _connection_status != ConnectionStatus.DISCONNECTED:
        ws = None
        with _connection_lock:
             if _ws_connection and _ws_connection.connected:
                 ws = _ws_connection
             elif _connection_status == ConnectionStatus.DISCONNECTED:
                 break # Exit loop if disconnected

        if not ws:
             # If connection is lost unexpectedly, attempt cleanup
             if _connection_status != ConnectionStatus.DISCONNECTED:
                  logger.warning("Listener: WebSocket connection lost unexpectedly.")
                  # Use a separate thread for cleanup to avoid deadlocking the listener
                  threading.Thread(target=close_connection, args=(False,), daemon=True).start()
             break

        try:
            message_str = ws.recv()
            if not message_str:
                if _connection_status != ConnectionStatus.DISCONNECTED:
                     logger.info("Listener: Server closed connection (received empty message).")
                     threading.Thread(target=close_connection, args=(False,), daemon=True).start()
                break

            logger.debug(f"Listener: Received raw message: {message_str}")
            message_data = json.loads(message_str) # Assume valid JSON

            with _connection_lock: # Acquire lock to process message and update state
                 if _connection_status == ConnectionStatus.DISCONNECTED: break # Check again after potential delay

                 # --- 1. Call Global Handler (if registered) ---
                 if _global_message_handler:
                     try:
                         _global_message_handler(message_data)
                     except Exception as e:
                         logger.exception(f"Listener: Error in global message handler: {e}")

                 # --- 2. Handle Message Dispatch ---
                 module = message_data.get('module')
                 msg_type = message_data.get('type')
                 payload = message_data.get('payload')

                 # --- Handle System Announce ---
                 if module == 'system' and msg_type == 'announce' and payload:
                      peer_id = payload.get('peerId')
                      role = payload.get('role')
                      status = payload.get('status')
                      if peer_id and role == 'sidekick':
                           if status == 'online':
                                was_empty = not _sidekick_peers_online
                                _sidekick_peers_online.add(peer_id)
                                logger.info(f"Sidekick peer online: {peer_id}")
                                if was_empty: # If this is the *first* sidekick online
                                     _handle_sidekick_online(peer_id)
                           elif status == 'offline':
                                if peer_id in _sidekick_peers_online:
                                     _sidekick_peers_online.discard(peer_id)
                                     logger.info(f"Sidekick peer offline: {peer_id}")
                                     if not _sidekick_peers_online and _connection_status == ConnectionStatus.CONNECTED_READY:
                                          # Keep READY state for simplicity for now
                                          pass

                 # --- Handle Module Event/Error (Dispatch to specific handler) ---
                 elif msg_type in ['event', 'error']:
                      instance_id = message_data.get('src')
                      if instance_id and instance_id in _message_handlers:
                           handler = _message_handlers[instance_id]
                           try:
                                logger.debug(f"Listener: Invoking handler for instance '{instance_id}' (type: {msg_type}).")
                                handler(message_data) # Call the module's internal handler
                           except Exception as e:
                                logger.exception(f"Listener: Error executing handler for instance '{instance_id}': {e}")
                      elif instance_id:
                           logger.debug(f"Listener: No specific handler registered for instance '{instance_id}' for message type {msg_type}.")
                      else:
                           logger.debug(f"Listener: Received {msg_type} message without 'src': {message_data}")

                 else:
                      # Other message types (e.g., spawn/update coming from Sidekick?) are not expected here yet.
                      logger.debug(f"Listener: Received message not dispatched to specific handler: type='{msg_type}', module='{module}'")

        except websocket.WebSocketConnectionClosedException:
            if _connection_status != ConnectionStatus.DISCONNECTED:
                 logger.info("Listener: WebSocket connection closed gracefully by server or self.")
                 threading.Thread(target=close_connection, args=(False,), daemon=True).start()
            break
        except websocket.WebSocketTimeoutException:
             if _connection_status != ConnectionStatus.DISCONNECTED:
                 logger.error("Listener: WebSocket ping timeout. Connection lost.")
                 threading.Thread(target=close_connection, args=(False,), daemon=True).start()
             break
        except (json.JSONDecodeError, TypeError) as e:
             logger.error(f"Listener: Failed to parse JSON message or invalid data: {message_str}, Error: {e}")
             continue # Skip this message
        except OSError as e:
            if _connection_status != ConnectionStatus.DISCONNECTED:
                 logger.warning(f"Listener: OS error occurred ({e}), likely connection closed.")
                 threading.Thread(target=close_connection, args=(False,), daemon=True).start()
            break
        except Exception as e:
            if _connection_status != ConnectionStatus.DISCONNECTED:
                 logger.exception(f"Listener: Unexpected error receiving/processing message: {e}")
                 threading.Thread(target=close_connection, args=(False,), daemon=True).start() # Close on unexpected errors
            break

    logger.info("Listener thread finished.")
    with _connection_lock:
        _listener_started = False # Allow restarting if connect is called again

def _ensure_connection():
    """Internal: Attempts to establish WebSocket connection if disconnected."""
    global _ws_connection, _listener_thread, _listener_started, _connection_status

    with _connection_lock:
        if _connection_status != ConnectionStatus.DISCONNECTED:
            return # Already connected or connecting

        logger.info(f"Attempting to connect to Sidekick server at {_ws_url}...")
        _connection_status = ConnectionStatus.CONNECTING
        _sidekick_peers_online.clear() # Clear sidekick status on new connection attempt
        _message_buffer.clear() # Clear buffer on new connection attempt

        try:
            _ws_connection = websocket.create_connection(
                _ws_url,
                timeout=_INITIAL_CONNECT_TIMEOUT,
                ping_interval=_PING_INTERVAL,
                ping_timeout=_PING_TIMEOUT
            )
            logger.info("Successfully connected to Sidekick server.")
            _ws_connection.settimeout(None) # Rely on Ping/Pong

            # Send online announcement immediately
            _send_system_announce("online")

            _connection_status = ConnectionStatus.CONNECTED_WAITING_SIDEKICK

            # Start listener thread if not already running from a previous failed attempt
            if not _listener_started:
                logger.info("Starting WebSocket listener thread.")
                _listener_thread = threading.Thread(target=_listen_for_messages, daemon=True)
                _listener_thread.start()
                _listener_started = True

        except (websocket.WebSocketException, ConnectionRefusedError, OSError, TimeoutError) as e:
            logger.error(f"Failed to connect to Sidekick server at {_ws_url}: {e}")
            _ws_connection = None
            _connection_status = ConnectionStatus.DISCONNECTED
        except Exception as e:
            logger.exception(f"Unexpected error during connection: {e}")
            _ws_connection = None
            _connection_status = ConnectionStatus.DISCONNECTED


# --- Public API ---

def set_url(url: str):
    """Sets the WebSocket server URL. Must be called before connecting."""
    global _ws_url
    with _connection_lock:
        if _connection_status != ConnectionStatus.DISCONNECTED:
            logger.warning("Cannot change URL after connection attempt. Call close_connection() first.")
            return
        if not url.startswith(("ws://", "wss://")):
             logger.warning(f"Invalid WebSocket URL scheme: {url}. Using default: {_ws_url}")
             return
        _ws_url = url
        logger.info(f"Sidekick WebSocket URL set to: {_ws_url}")

def set_config(clear_on_connect: bool = True, clear_on_disconnect: bool = False):
    """
    Configures automatic clearing behavior. Must be called before connecting.

    Args:
        clear_on_connect: If True (default), sends 'global/clearAll' when the first
                          Sidekick peer announces itself online.
        clear_on_disconnect: If True (default False), attempts (best-effort) to send
                             'global/clearAll' just before disconnecting.
    """
    global _clear_on_connect, _clear_on_disconnect
    with _connection_lock:
        if _connection_status != ConnectionStatus.DISCONNECTED:
            logger.warning("Cannot change config after connection attempt. Call close_connection() first.")
            return
        _clear_on_connect = clear_on_connect
        _clear_on_disconnect = clear_on_disconnect
        logger.info(f"Set config: clear_on_connect={_clear_on_connect}, clear_on_disconnect={_clear_on_disconnect}")

def activate_connection():
    """
    Ensures the WebSocket connection is established or being established.
    Safe to call multiple times. Typically called by module constructors.
    """
    with _connection_lock:
        if _connection_status == ConnectionStatus.DISCONNECTED:
             _ensure_connection()

def send_message(message_dict: Dict[str, Any]):
    """
    Sends a message dictionary to the Sidekick system.

    Handles buffering for non-system messages if Sidekick is not yet online.
    """
    module = message_dict.get("module")
    msg_type = message_dict.get("type")

    with _connection_lock:
        current_status = _connection_status
        ws = _ws_connection

        # Buffering Logic
        should_buffer = (module not in ["system"]) and \
                        (current_status != ConnectionStatus.CONNECTED_READY)

        if should_buffer:
            _message_buffer.append(message_dict)
            logger.debug(f"Buffering message ({module}/{msg_type}): {len(_message_buffer)} in buffer.")
            # If disconnected/connecting, ensure connection attempt is triggered
            if current_status == ConnectionStatus.DISCONNECTED:
                 _ensure_connection()
            return # Don't send yet

        # Sending Logic (System messages or when Ready)
        if current_status in [ConnectionStatus.CONNECTED_WAITING_SIDEKICK, ConnectionStatus.CONNECTED_READY]:
            if ws and ws.connected:
                _send_raw(ws, message_dict)
            else:
                # Should not happen if status is correct, but handle defensively
                logger.warning(f"Cannot send message, status is {current_status} but WebSocket is not connected. Buffering.")
                _message_buffer.append(message_dict) # Buffer it anyway
        elif current_status in [ConnectionStatus.DISCONNECTED, ConnectionStatus.CONNECTING]:
             # Should only reach here for system messages if buffering isn't applied to them
             if module == "system": logger.warning(f"Cannot send system message, connection status is {current_status}.")
             # If it's not a system message, it should have been buffered above. This is a fallback log.
             else: logger.warning(f"Message ({module}/{msg_type}) dropped, connection status is {current_status}.")
        # else: # Should cover all states

def clear_all():
    """Sends a 'global/clearAll' message to instruct Sidekick to clear all modules."""
    logger.info("Requesting global clearAll.")
    message = {
        "id": 0,
        "module": "global",
        "type": "clearAll",
    }
    # Use the public send_message to handle buffering if needed
    send_message(message)

def close_connection(log_info=True):
    """Closes the WebSocket connection and cleans up resources."""
    global _ws_connection, _listener_thread, _listener_started, _connection_status, _message_handlers, _sidekick_peers_online, _message_buffer

    with _connection_lock:
        if _connection_status == ConnectionStatus.DISCONNECTED:
            if log_info: logger.debug("Connection already closed.")
            return

        if log_info: logger.info("Closing WebSocket connection...")
        initial_status = _connection_status # Store status before changing

        # --- Mark as disconnected FIRST ---
        _connection_status = ConnectionStatus.DISCONNECTED
        _listener_started = False # Allow listener restart on next connect
        _sidekick_peers_online.clear()
        _message_buffer.clear() # Clear buffer on disconnect

        # --- Best-effort cleanup messages ---
        ws_temp = _ws_connection # Get a local ref before setting global to None
        if ws_temp and ws_temp.connected:
             if _clear_on_disconnect:
                  logger.debug("Attempting to send global/clearAll on disconnect (best-effort).")
                  clear_all_msg = {"id": 0, "module": "global", "type": "clearAll"}
                  try: _send_raw(ws_temp, clear_all_msg)
                  except Exception: logger.warning("Failed to send clearAll during disconnect.")

             logger.debug("Attempting to send offline announce (best-effort).")
             try: _send_system_announce("offline") # Use helper which calls _send_raw
             except Exception: logger.warning("Failed to send offline announce during disconnect.")

        # --- Close WebSocket ---
        _ws_connection = None # Set global var to None
        if ws_temp:
            try:
                ws_temp.close()
            except Exception as e:
                 logger.error(f"Error during WebSocket close(): {e}")

        # --- Clear Handlers ---
        # Keep global handler, but clear instance handlers
        if _message_handlers:
            logger.debug("Clearing instance message handlers.")
            _message_handlers.clear()

        if log_info: logger.info("WebSocket connection closed.")

# --- Registration/Utility Functions ---

def register_message_handler(instance_id: str, handler: Callable[[Dict[str, Any]], None]):
    """Registers the internal message handler for a specific module instance."""
    if not callable(handler):
        logger.error(f"Handler for instance '{instance_id}' is not callable.")
        return
    with _connection_lock:
        logger.info(f"Registering internal message handler for instance '{instance_id}'.")
        _message_handlers[instance_id] = handler

def unregister_message_handler(instance_id: str):
    """Unregisters the internal message handler for a specific module instance."""
    with _connection_lock:
        if instance_id in _message_handlers:
            logger.info(f"Unregistering internal message handler for instance '{instance_id}'.")
            del _message_handlers[instance_id]
        else:
            logger.debug(f"No internal message handler found for instance '{instance_id}' to unregister.")

def register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]]):
    """
    Registers a single handler function to receive ALL incoming messages from Sidekick.
    Set to None to unregister.

    Args:
        handler: A function that accepts the raw message dictionary, or None.
    """
    global _global_message_handler
    with _connection_lock:
        if handler is None:
            logger.info("Unregistering global message handler.")
            _global_message_handler = None
        elif callable(handler):
            logger.info(f"Registering global message handler: {handler}")
            _global_message_handler = handler
        else:
            logger.error("Global message handler must be callable or None.")

def get_next_command_id() -> int:
    """Generates a sequential ID for commands (like Canvas drawing ops)."""
    global _command_counter
    with _connection_lock:
        _command_counter += 1
        return _command_counter

# --- Automatic Cleanup ---
atexit.register(close_connection)