import websocket # Using websocket-client library
import json
import threading
import atexit
import time
import uuid
from collections import deque
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable, Deque, List, Set

# --- Import logger from package __init__ ---
from . import logger

# --- Version Import ---
try:
    from ._version import __version__
except ImportError:
    __version__ = 'unknown' # Fallback version

# --- Connection Status Enum ---
class ConnectionStatus(Enum):
    """Represents the different states of the WebSocket connection."""
    DISCONNECTED = auto()               # Not connected or connection closed.
    CONNECTING = auto()                 # Attempting to establish connection.
    CONNECTED_WAITING_SIDEKICK = auto() # Connected to server, waiting for Sidekick UI to announce itself.
    CONNECTED_READY = auto()            # Connected and Sidekick UI is online and ready.

# --- Configuration and State (Internal) ---
_ws_url: str = "ws://localhost:5163"
_ws_connection: Optional[websocket.WebSocket] = None
_connection_lock = threading.RLock() # Lock for thread safety
_listener_thread: Optional[threading.Thread] = None
_listener_started: bool = False
_message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {} # Maps instance_id to handler
_command_counter: int = 0 # Counter for Canvas command IDs

_peer_id: Optional[str] = None # Unique ID for this Python script instance
_connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
_sidekick_peers_online: Set[str] = set() # Stores IDs of online Sidekick UIs
_message_buffer: Deque[Dict[str, Any]] = deque() # Buffer for messages sent before READY
_clear_on_connect: bool = True
_clear_on_disconnect: bool = False
_global_message_handler: Optional[Callable[[Dict[str, Any]], None]] = None # Global handler

_stop_event = threading.Event() # Signals listener thread to stop
_ready_event = threading.Event() # Signals when connection becomes READY
_shutdown_event = threading.Event() # Signals shutdown for run_forever
_buffer_flushed_and_ready_condition = threading.Condition(_connection_lock) # For flush_messages

_PING_INTERVAL = 20
_PING_TIMEOUT = 10
_INITIAL_CONNECT_TIMEOUT = 5
_LISTENER_RECV_TIMEOUT = 1.0 # Timeout for ws.recv()

# --- Private Helper Functions (Internal Use Only) ---

def _generate_peer_id() -> str:
    """Generates the unique peer ID for this Hero instance."""
    global _peer_id
    if _peer_id is None:
        _peer_id = f"hero-{uuid.uuid4().hex}"
        logger.info(f"Generated Hero Peer ID: {_peer_id}")
    return _peer_id

def _send_raw(ws: websocket.WebSocket, message_dict: Dict[str, Any]):
    """Internal: Sends the message directly, handles basic errors."""
    try:
        message_json = json.dumps(message_dict)
        logger.debug(f"Sending raw: {message_json}")
        ws.send(message_json)
    except (websocket.WebSocketException, BrokenPipeError, OSError) as e:
        # Check if we are already stopping/disconnected to avoid redundant close calls
        if not _stop_event.is_set() and _connection_status != ConnectionStatus.DISCONNECTED:
            logger.error(f"WebSocket send error: {e}. Triggering close.")
            # Use a separate thread or schedule cleanup to avoid deadlock if called from listener
            threading.Thread(target=close_connection, args=(False,), daemon=True).start()
    except Exception as e:
        logger.exception(f"Unexpected error sending message: {e}")

def _send_system_announce(status: str):
    """Sends the system announce message (online/offline)."""
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
             logger.debug("Cannot send offline announce, connection already closed or closing.")
        else:
             logger.warning(f"Cannot send system announce '{status}', WebSocket not connected.")

def _flush_message_buffer() -> bool:
    """Sends all buffered messages. Assumes lock is held. Returns True if READY and empty."""
    notify_condition = False
    if not _message_buffer:
        # Buffer is already empty, potentially need notification if status just became READY
        if _connection_status == ConnectionStatus.CONNECTED_READY:
             notify_condition = True
        return notify_condition # Return whether notification is needed

    ws = _ws_connection
    if not (ws and ws.connected and _connection_status == ConnectionStatus.CONNECTED_READY):
        # Cannot flush yet, state not met
        return False

    logger.info(f"Flushing {len(_message_buffer)} buffered messages...")
    while _message_buffer:
        message_to_send = _message_buffer.popleft()
        _send_raw(ws, message_to_send) # Assumes _send_raw handles potential errors
        # Check stop event during flushing in case close is called concurrently
        if _stop_event.is_set():
             logger.warning("Stop event set during buffer flush, aborting.")
             return False # State not met as we are stopping

    logger.info("Message buffer flushed.")
    # Buffer is now empty and status is READY
    return True

def _handle_sidekick_online(sidekick_peer_id: str):
    """Handles logic when the first Sidekick UI announces online."""
    # Assumes lock is held by the caller (_listen_for_messages)
    global _connection_status
    notify_flush_cond = False
    if _connection_status == ConnectionStatus.CONNECTED_WAITING_SIDEKICK:
        logger.info(f"Sidekick '{sidekick_peer_id}' announced online. System is READY.")
        _connection_status = ConnectionStatus.CONNECTED_READY
        _ready_event.set() # Signal that connection is ready

        if _clear_on_connect:
            logger.info("clear_on_connect is True, sending global/clearAll.")
            clear_all() # This will now succeed as status is READY

        # Flush buffer and check if the condition (READY + empty) is now met
        notify_flush_cond = _flush_message_buffer()

    # If the condition (READY + empty buffer) is met, notify waiters
    if notify_flush_cond:
         logger.debug("_handle_sidekick_online: Notifying flush condition.")
         _buffer_flushed_and_ready_condition.notify_all()

def _listen_for_messages():
    """Background thread function to listen for incoming messages."""
    global _connection_status, _message_handlers, _sidekick_peers_online, _listener_started, _global_message_handler
    logger.info("Listener thread started.")
    ws = None

    # Main loop controlled by the stop event
    while not _stop_event.is_set():
        with _connection_lock:
             # Check status/connection integrity at the start of each loop iteration
             if _connection_status == ConnectionStatus.DISCONNECTED:
                 logger.debug("Listener: Status is DISCONNECTED, stopping loop.")
                 break # Exit loop if disconnected externally
             if _ws_connection and _ws_connection.connected:
                 ws = _ws_connection
             else:
                 # Connection lost unexpectedly? Trigger close only if not already stopping.
                 if not _stop_event.is_set():
                    logger.warning("Listener: WebSocket connection lost.")
                    threading.Thread(target=close_connection, args=(False,), daemon=True).start()
                 break

        if not ws:
            # Should have been caught above, but as a safeguard
            if not _stop_event.is_set():
                 logger.warning("Listener: WebSocket object is None, stopping loop.")
                 threading.Thread(target=close_connection, args=(False,), daemon=True).start()
            break

        try:
            # Set timeout for recv() to allow periodic check of _stop_event
            # This is the crucial change for reliable shutdown
            ws.settimeout(_LISTENER_RECV_TIMEOUT)
            message_str = ws.recv()

            # Check stop event again immediately after potentially blocking recv
            if _stop_event.is_set(): break

            if not message_str: # Empty message often means server closed connection
                if not _stop_event.is_set():
                     logger.info("Listener: Server closed connection (received empty message).")
                     threading.Thread(target=close_connection, args=(False,), daemon=True).start()
                break

            logger.debug(f"Listener: Received raw message: {message_str}")
            message_data = json.loads(message_str) # Assume valid JSON

            with _connection_lock: # Acquire lock to process message and update state
                 # Check stop/disconnect again inside lock
                 if _stop_event.is_set() or _connection_status == ConnectionStatus.DISCONNECTED: break

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
                                     # Optional: If needed, could transition back to WAITING
                                     # and clear _ready_event if _sidekick_peers_online is now empty.
                                     # if not _sidekick_peers_online and _connection_status == ConnectionStatus.CONNECTED_READY:
                                     #    _connection_status = ConnectionStatus.CONNECTED_WAITING_SIDEKICK
                                     #    _ready_event.clear()
                                     #    logger.info("Last Sidekick peer disconnected, returning to WAITING state.")

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
                      logger.debug(f"Listener: Received unhandled message type: module='{module}', type='{msg_type}'")

        except websocket.WebSocketTimeoutException:
            # This is expected due to ws.settimeout(). Just continue the loop.
            # logger.debug("Listener: recv() timeout, checking stop event.")
            continue
        except websocket.WebSocketConnectionClosedException:
            # Connection closed gracefully
            if not _stop_event.is_set():
                 logger.info("Listener: WebSocket connection closed.")
                 # Trigger close_connection if it wasn't initiated by us
                 threading.Thread(target=close_connection, args=(False,), daemon=True).start()
            break # Exit loop
        except websocket.WebSocketPayloadException as e:
             # Error processing the WebSocket frame/payload itself
             logger.error(f"Listener: Invalid WebSocket payload received: {e}")
             continue # Try to continue receiving other messages
        except (json.JSONDecodeError, TypeError) as e:
             logger.error(f"Listener: Failed to parse JSON message or invalid data: {message_str}, Error: {e}")
             continue # Skip this message
        except OSError as e:
            # Ignore "[Errno 9] Bad file descriptor" if stop_event is set, as it's expected during shutdown
            if not (_stop_event.is_set() and isinstance(e, OSError) and e.errno == 9):
                if not _stop_event.is_set():
                    logger.warning(f"Listener: OS error ({e}), likely connection closed.")
                    threading.Thread(target=close_connection, args=(False,), daemon=True).start()
            break # Exit loop on OS errors (unless expected during shutdown)
        except Exception as e:
            # Catchall for other unexpected errors
            if not _stop_event.is_set():
                 logger.exception(f"Listener: Unexpected error: {e}")
                 threading.Thread(target=close_connection, args=(False,), daemon=True).start()
            break # Exit loop

    # --- Listener Loop Exit ---
    logger.info("Listener thread finished.")
    with _connection_lock:
        # Ensure listener status is updated after loop exit
        _listener_started = False


def _ensure_connection():
    """Internal: Attempts WebSocket connection if disconnected."""
    global _ws_connection, _listener_thread, _listener_started, _connection_status

    with _connection_lock:
        if _connection_status != ConnectionStatus.DISCONNECTED:
            return # Already connected or connecting

        logger.info(f"Attempting to connect to Sidekick server at {_ws_url}...")
        _connection_status = ConnectionStatus.CONNECTING
        _sidekick_peers_online.clear()
        _message_buffer.clear()
        # --- Reset Events for the new connection attempt ---
        _stop_event.clear()
        _ready_event.clear()
        _shutdown_event.clear()

        try:
            _ws_connection = websocket.create_connection(
                _ws_url,
                timeout=_INITIAL_CONNECT_TIMEOUT,
                ping_interval=_PING_INTERVAL,
                ping_timeout=_PING_TIMEOUT
            )
            logger.info("Successfully connected to Sidekick server.")
            # Timeout will be set dynamically in the listener loop

            # Send online announcement immediately
            _send_system_announce("online")

            _connection_status = ConnectionStatus.CONNECTED_WAITING_SIDEKICK

            # Start listener thread if not already running
            # Check both the flag and the thread object's status
            if not _listener_started and not (_listener_thread and _listener_thread.is_alive()):
                logger.info("Starting WebSocket listener thread.")
                _listener_thread = threading.Thread(target=_listen_for_messages, daemon=True) # CRITICAL: Use daemon=True
                _listener_thread.start()
                _listener_started = True
            elif (_listener_thread and _listener_thread.is_alive()):
                 logger.warning("Listener thread already running during connect sequence (unexpected).")
                 _listener_started = True # Assume it's active


        except (websocket.WebSocketException, ConnectionRefusedError, OSError, TimeoutError) as e:
            logger.error(f"Failed to connect to Sidekick server at {_ws_url}: {e}")
            _ws_connection = None
            _connection_status = ConnectionStatus.DISCONNECTED
            _stop_event.set() # Ensure stop is set if connection fails, prevents zombie listener start attempts
            _listener_started = False
        except Exception as e:
            logger.exception(f"Unexpected error during connection: {e}")
            _ws_connection = None
            _connection_status = ConnectionStatus.DISCONNECTED
            _stop_event.set()
            _listener_started = False


# --- Public API ---

def set_url(url: str):
    """Sets the WebSocket server URL where Sidekick is listening.

    You **must** call this function *before* creating any Sidekick modules
    (like `Grid`, `Console`) if the Sidekick server is not running on the
    default URL (`ws://localhost:5163`).

    Args:
        url (str): The WebSocket URL (must start with "ws://" or "wss://").

    Examples:
        >>> # If Sidekick server is running on a different port
        >>> sidekick.set_url("ws://localhost:8080")
        >>>
        >>> # If Sidekick server is on a different machine
        >>> sidekick.set_url("ws://192.168.1.100:5163")

    Returns:
        None
    """
    global _ws_url
    with _connection_lock:
        if _connection_status != ConnectionStatus.DISCONNECTED:
            logger.warning("Cannot change URL after connection attempt. Call sidekick.close_connection() first if needed.")
            return
        if not url.startswith(("ws://", "wss://")):
             logger.warning(f"Invalid WebSocket URL scheme: {url}. Please use 'ws://' or 'wss://'.")
             return
        _ws_url = url
        logger.info(f"Sidekick WebSocket URL set to: {_ws_url}")

def set_config(clear_on_connect: bool = True, clear_on_disconnect: bool = False):
    """Configures automatic clearing behavior of the Sidekick UI.

    Call this *before* creating any Sidekick modules to change the default behavior.

    Args:
        clear_on_connect (bool): If True (default), sends a command to clear all
            existing UI elements in Sidekick as soon as the connection becomes ready.
            Set to False if you want your script to potentially interact with UI
            elements left over from a previous script run.
        clear_on_disconnect (bool): If True (default is False), attempts to send
            a command to clear all UI elements when the Python script disconnects
            (e.g., at the end of the script or when `shutdown()` is called). This
            is a "best-effort" attempt and might not always succeed.

    Examples:
        >>> # Prevent clearing the UI when the script connects
        >>> sidekick.set_config(clear_on_connect=False)
        >>>
        >>> # Try to clear the UI when the script exits
        >>> sidekick.set_config(clear_on_disconnect=True)

    Returns:
        None
    """
    global _clear_on_connect, _clear_on_disconnect
    with _connection_lock:
        if _connection_status != ConnectionStatus.DISCONNECTED:
            logger.warning("Cannot change config after connection attempt. Call sidekick.close_connection() first if needed.")
            return
        _clear_on_connect = clear_on_connect
        _clear_on_disconnect = clear_on_disconnect
        logger.info(f"Set config: clear_on_connect={_clear_on_connect}, clear_on_disconnect={_clear_on_disconnect}")

def activate_connection():
    """Ensures the connection attempt to the Sidekick server is initiated.

    This function is usually called automatically when you create the first
    Sidekick module (like `Grid` or `Console`). You typically don't need to
    call it directly, but it's safe to do so. It won't do anything if the
    connection is already active or connecting.

    Returns:
        None
    """
    with _connection_lock:
        if _connection_status == ConnectionStatus.DISCONNECTED:
             _ensure_connection()

def send_message(message_dict: Dict[str, Any]):
    """Sends a message dictionary to the Sidekick system. (Internal Use)

    Handles buffering if Sidekick is not yet ready and ensures the connection
    attempt is triggered.

    Args:
        message_dict (Dict[str, Any]): The message payload conforming to the protocol.

    Returns:
        None
    """
    module = message_dict.get("module")
    msg_type = message_dict.get("type")
    notify_flush_cond = False

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
            # Cannot notify condition yet
        else:
            # Sending Logic (System messages or when Ready)
            if current_status in [ConnectionStatus.CONNECTED_WAITING_SIDEKICK, ConnectionStatus.CONNECTED_READY]:
                if ws and ws.connected:
                    _send_raw(ws, message_dict)
                    # If we just sent the last message in the buffer while ready, notify
                    if current_status == ConnectionStatus.CONNECTED_READY and not _message_buffer:
                         notify_flush_cond = True
                else:
                    # Should not happen if status is correct, but handle defensively
                    logger.warning(f"Cannot send message, status is {current_status} but WebSocket is not connected. Buffering.")
                    _message_buffer.append(message_dict) # Buffer it anyway
                    if current_status == ConnectionStatus.DISCONNECTED:
                         _ensure_connection() # Trigger connection if disconnected
            elif current_status in [ConnectionStatus.DISCONNECTED, ConnectionStatus.CONNECTING]:
                 if module == "system": logger.warning(f"Cannot send system message, connection status is {current_status}.")
                 else: logger.warning(f"Message ({module}/{msg_type}) dropped, connection status is {current_status}.")

        # Notify condition outside the main sending logic, but still under lock
        if notify_flush_cond:
             logger.debug("send_message: Buffer became empty while ready, notifying condition.")
             _buffer_flushed_and_ready_condition.notify_all()

def clear_all():
    """Sends a command to Sidekick to remove all currently displayed UI elements.

    This affects all modules (Grids, Consoles, etc.) shown in the Sidekick panel.

    Examples:
        >>> # Clear everything currently shown in Sidekick
        >>> sidekick.clear_all()

    Returns:
        None
    """
    logger.info("Requesting global clearAll.")
    message = {
        "id": 0,
        "module": "global",
        "type": "clearAll",
    }
    # Use the public send_message to handle buffering if needed
    send_message(message)

def close_connection(log_info=True):
    """Closes the WebSocket connection, stops the listener, and cleans up resources.

    You generally don't need to call this directly. Use `sidekick.shutdown()`
    instead, especially if using `sidekick.run_forever()`, as `shutdown()` handles
    more context. `shutdown()` is also called automatically when your script exits normally.

    Args:
        log_info (bool): Whether to log info messages during closing. Defaults to True.

    Returns:
        None
    """
    global _ws_connection, _listener_thread, _listener_started, _connection_status, _message_handlers, _sidekick_peers_online, _message_buffer

    with _connection_lock:
        # Check if already disconnected or stopping process initiated
        if _connection_status == ConnectionStatus.DISCONNECTED and _stop_event.is_set():
            if log_info: logger.debug("Connection already closed or closing process initiated.")
            return

        if log_info: logger.info("Closing WebSocket connection...")
        initial_status = _connection_status

        # --- Signal listener thread to stop FIRST ---
        _stop_event.set()
        # Signal any waiting threads (like flush_messages) that we are disconnecting
        _buffer_flushed_and_ready_condition.notify_all()
        _ready_event.clear() # Ensure ready state is false

        # --- Mark as disconnected ---
        _connection_status = ConnectionStatus.DISCONNECTED
        _sidekick_peers_online.clear()

        # Check *before* clearing the buffer or closing the socket
        buffered_count = len(_message_buffer)
        if buffered_count > 0:
            warning_message = f"[Sidekick Warning] Script finished, but {buffered_count} message(s) were still buffered."
            warning_message += "\n                 Visual updates in Sidekick might be incomplete or missing."
            warning_message += "\n                 For short scripts, add 'sidekick.flush_messages(timeout=5.0)' at the end."
            warning_message += "\n                 For interactive scripts, use 'sidekick.run_forever()' to keep the script alive."
            logger.warning(warning_message)

        _message_buffer.clear() # Clear buffer after checking

        # --- Best-effort cleanup messages ---
        ws_temp = _ws_connection
        if ws_temp and ws_temp.connected and initial_status != ConnectionStatus.CONNECTING:
             if _clear_on_disconnect:
                  logger.debug("Attempting to send global/clearAll on disconnect (best-effort).")
                  clear_all_msg = {"id": 0, "module": "global", "type": "clearAll"}
                  try: _send_raw(ws_temp, clear_all_msg)
                  except Exception: logger.warning("Failed to send clearAll during disconnect.")

             logger.debug("Attempting to send offline announce (best-effort).")
             try: _send_system_announce("offline") # Use helper which calls _send_raw
             except Exception: logger.warning("Failed to send offline announce during disconnect.")

        # --- Close WebSocket (no shutdown needed) ---
        if ws_temp:
            try:
                # logger.debug("Attempting ws.close()...")
                # Set a short timeout for close itself, just in case
                ws_temp.settimeout(0.5)
                ws_temp.close()
            except Exception as e:
                 logger.error(f"Error during WebSocket close(): {e}")
        _ws_connection = None # Set global var to None after trying to close

        # --- Get listener thread reference before clearing ---
        listener_thread_temp = _listener_thread
        _listener_thread = None # Clear global reference
        _listener_started = False # Allow listener restart on next connect

    # --- Join Listener Thread (Outside main lock) ---
    if listener_thread_temp and listener_thread_temp.is_alive():
        if log_info: logger.debug("Waiting for listener thread to stop...")
        try:
            # Timeout slightly longer than recv timeout allows it to naturally exit
            listener_thread_temp.join(timeout=_LISTENER_RECV_TIMEOUT + 0.5)
            if listener_thread_temp.is_alive():
                 logger.warning(f"Listener thread did not stop gracefully after join timeout.")
            else:
                 if log_info: logger.debug("Listener thread stopped.")
        except Exception as e:
             logger.warning(f"Error joining listener thread: {e}")
    elif log_info:
        logger.debug("Listener thread was not running or already finished.")

    # --- Clear Handlers (outside lock is fine) ---
    if _message_handlers:
        logger.debug("Clearing instance message handlers.")
        _message_handlers.clear()

    if log_info: logger.info("WebSocket connection closed.")

def run_forever():
    """Keeps the Python script running indefinitely to listen for Sidekick events.

    If your script needs to react to user input from Sidekick (like button clicks
    via `Control.on_click` or text input via `Console.on_input_text`), you
    should call `sidekick.run_forever()` at the end of your script setup.

    This function will block the script from exiting, allowing the background
    thread to continue receiving messages and triggering your callback functions.

    To stop the script gracefully, either:
    1. Press Ctrl+C in the terminal.
    2. Call `sidekick.shutdown()` from within one of your event callback functions.

    Examples:
        .. code-block:: python

            import sidekick
            import time

            console = sidekick.Console(show_input=True)
            control = sidekick.Control()

            def handle_input(text):
                console.print(f"You entered: {text}")
                if text == "quit":
                    console.print("Shutting down...")
                    sidekick.shutdown() # Stop run_forever

            def handle_click(control_id):
                console.print(f"Button '{control_id}' clicked!")

            console.on_input_text(handle_input)
            control.on_click(handle_click)

            control.add_button("my_button", "Click Me")
            console.print("Enter text below or click the button.")
            console.print("Type 'quit' to exit.")

            # Keep the script running to handle events
            sidekick.run_forever()

            print("Script finished.") # This line will run after shutdown() is called

    Returns:
        None
    """
    activate_connection() # Make sure connection attempt happens if needed
    logger.info("Sidekick entering run_forever mode. Press Ctrl+C or call sidekick.shutdown() to exit.")
    _shutdown_event.clear() # Ensure clean state before waiting
    try:
        while not _shutdown_event.is_set():
            # Check if listener died unexpectedly (and not because we're shutting down)
            with _connection_lock:
                if _listener_thread and not _listener_thread.is_alive() and \
                   _listener_started and not _stop_event.is_set():
                    logger.warning("run_forever: Listener thread died unexpectedly. Attempting reconnect...")
                    # Mark as disconnected to trigger reconnect attempt
                    _connection_status = ConnectionStatus.DISCONNECTED
                    _listener_started = False # Allow restart
                    _stop_event.clear() # Clear stop event for the *new* listener
                    activate_connection() # Try to restart connection and listener

            # Wait efficiently using the shutdown event
            signaled = _shutdown_event.wait(timeout=1.0) # Check every second
            if signaled:
                logger.debug("run_forever: Shutdown event signaled.")
                break # Exit loop cleanly if shutdown() was called

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received, shutting down Sidekick.")
        # Let finally block handle shutdown
    except Exception as e:
        logger.exception(f"Unexpected error during run_forever: {e}")
        # Let finally block handle shutdown
    finally:
        # Ensure shutdown logic runs even if loop breaks unexpectedly
        if not _shutdown_event.is_set(): # Check if shutdown wasn't already called
            logger.debug("run_forever: Exiting loop, initiating shutdown.")
            shutdown() # Call full shutdown process
        else:
             logger.debug("run_forever: Loop exited, shutdown already initiated.")

    logger.info("Sidekick run_forever mode finished.")

def shutdown():
    """Initiates a clean shutdown of the Sidekick connection and listener.

    If you are using `sidekick.run_forever()`, you can call this function
    (e.g., from an event handler) to make `run_forever()` stop and allow your
    script to exit cleanly.

    This function is also registered to be called automatically when your Python
    script exits normally (using `atexit`). You usually don't need to call it
    manually unless you want to stop `run_forever()` programmatically.

    It's safe to call this function multiple times.

    Examples:
        >>> # Inside a button click handler
        >>> def on_quit_button_click(control_id):
        ...     print("Quit button pressed. Shutting down.")
        ...     sidekick.shutdown()

    Returns:
        None
    """
    with _connection_lock:
        if _shutdown_event.is_set() and _stop_event.is_set() and _connection_status == ConnectionStatus.DISCONNECTED:
            logger.debug("Shutdown already completed or in progress.")
            return

        logger.info("Sidekick shutdown requested.")
        _shutdown_event.set() # Signal run_forever to stop

    # Initiate close outside the lock to allow close_connection to manage its own locking
    close_connection() # Close the connection and stop listener

def ensure_ready(timeout: Optional[float] = None) -> bool:
    """Waits until the connection to Sidekick is established and ready.

    This function blocks your script's execution until the Sidekick library has
    successfully connected to the server AND has received confirmation that at
    least one Sidekick UI is online and ready to receive commands.

    This is useful at the beginning of a script to make sure Sidekick is
    ready before you start sending commands to create or update UI elements.

    Args:
        timeout (Optional[float]): Maximum time in seconds to wait. If None
            (default), it will wait indefinitely. If the timeout is reached
            before the connection is ready, the function will return False.

    Returns:
        bool: True if the connection became ready within the timeout, False otherwise.

    Examples:
        >>> # Wait up to 10 seconds for Sidekick to be ready
        >>> if sidekick.ensure_ready(timeout=10.0):
        ...     print("Sidekick is ready! Proceeding...")
        ...     grid = sidekick.Grid()
        ...     grid.set_color(0, 0, "green")
        ... else:
        ...     print("Sidekick didn't become ready in time.")

    """
    activate_connection() # Ensure connection process has started

    # Handle non-positive timeout immediately
    if timeout is not None and timeout <= 0:
        with _connection_lock:
            return _connection_status == ConnectionStatus.CONNECTED_READY

    logger.debug(f"Waiting for connection to be READY (timeout={timeout}s)...")
    # Wait for the ready event to be set
    ready = _ready_event.wait(timeout=timeout)

    if ready:
         # Event was set, double-check status under lock
         with _connection_lock:
             if _connection_status == ConnectionStatus.CONNECTED_READY:
                  logger.debug("Connection is READY.")
                  return True
             else:
                  # Race condition: Became ready then disconnected before we checked
                  logger.warning(f"ensure_ready: Event set, but status is now {_connection_status}. Returning False.")
                  # _ready_event should have been cleared by close_connection
                  return False
    else:
        # Timed out
        with _connection_lock: # Get status for logging
             current_status = _connection_status
        logger.warning(f"ensure_ready: Timed out after {timeout}s waiting for READY state. Current status: {current_status}")
        return False

def flush_messages(timeout: Optional[float] = None) -> bool:
    """Waits until the connection is READY and all buffered messages have been sent.

    When you send commands (like `grid.set_color()`) before Sidekick is fully
    connected and ready, the library temporarily stores these messages in a buffer.
    This function waits until the connection is established (`CONNECTED_READY`)
    AND all messages in that buffer have been sent to Sidekick.

    This is particularly useful at the very end of short scripts that don't use
    `run_forever()`. Calling `flush_messages()` increases the chance that Sidekick
    receives and displays all your updates before the script exits.

    Args:
        timeout (Optional[float]): Maximum time in seconds to wait. If None
            (default), waits indefinitely. If the timeout is reached before
            the buffer is flushed while ready, returns False.

    Returns:
        bool: True if the connection was ready and the buffer was flushed within
              the timeout, False otherwise (e.g., timeout, disconnection).

    Examples:
        .. code-block:: python

            import sidekick
            import time

            # Create a grid and update cells quickly
            grid = sidekick.Grid(4, 4)
            for i in range(4):
                grid.set_color(i, i, color="blue")
                time.sleep(0.01) # Simulate some work

            print("Script finished sending commands.")

            # Wait up to 5 seconds for messages to be sent before exiting
            if sidekick.flush_messages(timeout=5.0):
                print("Messages flushed successfully.")
            else:
                print("Warning: Messages might not have been fully sent.")

            # No run_forever(), so script exits here. flush_messages helps ensure
            # the blue cells appear in Sidekick.
    """
    activate_connection() # Ensure connection attempt is happening

    with _buffer_flushed_and_ready_condition: # Use the condition variable's lock
        start_time = time.monotonic()
        remaining_timeout = timeout

        while not (_connection_status == ConnectionStatus.CONNECTED_READY and not _message_buffer):
            # Check for immediate exit conditions
            if _connection_status == ConnectionStatus.DISCONNECTED:
                 logger.warning("flush_messages: Connection disconnected. Cannot flush.")
                 return False # Cannot possibly succeed if disconnected
            if _stop_event.is_set(): # Check if closing process started
                 logger.warning("flush_messages: Connection closing. Cannot flush.")
                 return False

            # Calculate remaining time for wait()
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    # Check condition one last time before declaring timeout
                    if not (_connection_status == ConnectionStatus.CONNECTED_READY and not _message_buffer):
                        logger.warning(f"flush_messages: Timed out after {timeout:.2f}s. Status={_connection_status.name}, Buffer size={len(_message_buffer)}")
                        return False
                    else:
                        break # Condition met just as timeout hit

                # Ensure remaining_timeout isn't negative for wait()
                remaining_timeout = max(0., timeout - elapsed)

            # Wait for notification or timeout
            signaled = _buffer_flushed_and_ready_condition.wait(timeout=remaining_timeout)

            # If wait timed out specifically (signaled is False), check condition again
            # This handles the case where the condition became true *just* as wait timed out
            if not signaled and timeout is not None:
                 if not (_connection_status == ConnectionStatus.CONNECTED_READY and not _message_buffer):
                      logger.warning(f"flush_messages: Timed out (wait returned False) after {timeout:.2f}s. Status={_connection_status.name}, Buffer size={len(_message_buffer)}")
                      return False
                 # else: Condition became true just as wait timed out, loop will exit

        # Loop finished because condition is met
        logger.info("flush_messages: Connection is READY and message buffer is flushed.")
        return True

# --- Registration/Utility Functions (Mostly Internal) ---

def register_message_handler(instance_id: str, handler: Callable[[Dict[str, Any]], None]):
    """Registers the internal message handler for a specific module instance."""
    if not callable(handler):
        logger.error(f"Handler for instance '{instance_id}' is not callable.")
        return
    with _connection_lock:
        # Only register if not shutting down
        if _connection_status != ConnectionStatus.DISCONNECTED or not _stop_event.is_set():
            logger.info(f"Registering internal message handler for instance '{instance_id}'.")
            _message_handlers[instance_id] = handler
        else:
            logger.warning(f"Connection closed or closing, handler for '{instance_id}' not registered.")

def unregister_message_handler(instance_id: str):
    """Unregisters the internal message handler for a specific module instance."""
    with _connection_lock:
        if instance_id in _message_handlers:
            logger.info(f"Unregistering internal message handler for instance '{instance_id}'.")
            del _message_handlers[instance_id]
        else:
            # This can happen normally during shutdown cleanup
            logger.debug(f"No internal message handler found for instance '{instance_id}' to unregister.")

def register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]]):
    """Registers a function to receive ALL incoming messages from Sidekick.

    This is an advanced feature primarily for debugging or specific low-level
    integrations. The handler function will be called with the raw message
    dictionary received over the WebSocket *before* it's dispatched to specific
    module handlers.

    Args:
        handler (Optional[Callable[[Dict[str, Any]], None]]): A function that
            accepts a single argument (the message dictionary), or `None` to
            remove the current handler.

    Examples:
        >>> def my_raw_message_spy(message):
        ...     print(f"Received from Sidekick: {message}")
        >>>
        >>> sidekick.register_global_message_handler(my_raw_message_spy)
        >>> # ... run your sidekick code ...
        >>> sidekick.register_global_message_handler(None) # Stop spying

    Returns:
        None
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
    """Generates a sequential ID for commands (like Canvas drawing ops). Internal use."""
    global _command_counter
    with _connection_lock:
        _command_counter += 1
        return _command_counter

# --- Automatic Cleanup ---
# Ensure shutdown is called on normal exit. This correctly handles stopping
# run_forever if used, and cleans up the connection and listener thread.
atexit.register(shutdown)