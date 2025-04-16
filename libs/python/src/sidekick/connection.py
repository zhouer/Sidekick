"""
Manages the WebSocket connection between your Python script and the Sidekick UI.

This module is the heart of the communication layer. It handles the tricky bits
of talking to the Sidekick panel running in VS Code, letting your Python script
send commands (like "create a grid" or "set a color") and receive events
(like "button clicked" or "text entered").

How it Works (The Short Version):
- It uses WebSockets to talk to a server running inside the Sidekick VS Code extension.
- The *first* time your script tries to interact with Sidekick (e.g., creating
  a `sidekick.Grid()`), this module tries to connect.
- **Important:** It will PAUSE (block) your script until the connection is fully
  ready (connected to the server AND the Sidekick UI panel confirms it's ready).
- If it can't connect or the UI doesn't respond in time, it raises an error.
- Once connected, sending commands happens immediately.
- A background "listener" thread waits for messages (like clicks) from the UI.
- If the connection breaks, it raises an error; it won't try to reconnect automatically.

You usually interact with this module indirectly through functions like
`sidekick.run_forever()` or `sidekick.shutdown()`, or just by creating and
using the visual module classes (`Grid`, `Console`, etc.).
"""

import websocket # The library used for WebSocket communication (websocket-client)
import json
import threading
import atexit # Used to automatically call shutdown() when the script exits
import time
import uuid
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable, Set

# --- Import logger and Version ---
from . import logger # Use the central logger defined in __init__.py
try:
    # Try to get the version number from the _version.py file
    from ._version import __version__
except ImportError:
    # If _version.py isn't found (e.g., during development setup), use a fallback.
    __version__ = 'unknown'

# --- Custom Exceptions ---
# Define specific error types for connection problems, making it easier
# for users to catch and potentially handle different failure scenarios.

class SidekickConnectionError(Exception):
    """Base error for all Sidekick connection-related problems.

    You can use `except sidekick.SidekickConnectionError:` to catch any
    connection issue raised by the library.
    """
    pass

class SidekickConnectionRefusedError(SidekickConnectionError):
    """Raised when the library fails to connect to the Sidekick server initially.

    This usually means:
    1. The Sidekick panel isn't open in VS Code.
    2. The Sidekick VS Code extension isn't running correctly.
    3. The WebSocket server couldn't start (maybe the port is already in use,
       check VS Code's "Sidekick Server" output channel).
    4. A firewall is blocking the connection.
    5. The URL configured via `sidekick.set_url()` is incorrect.

    Attributes:
        url (str): The WebSocket URL that the connection attempt was made to.
        original_exception (Exception): The lower-level error that caused the failure
            (e.g., `ConnectionRefusedError`, `TimeoutError`).
    """
    def __init__(self, url: str, original_exception: Exception):
        self.url = url
        self.original_exception = original_exception
        super().__init__(
            f"Failed to connect to Sidekick server at {url}. "
            f"Reason: {original_exception}. "
            f"Is the Sidekick panel open in VS Code? "
            f"Check the URL, port conflicts, and firewall."
        )

class SidekickTimeoutError(SidekickConnectionError):
    """Raised when the connection to the server succeeded, but the Sidekick UI didn't respond in time.

    After connecting to the WebSocket server (run by the VS Code extension),
    the library waits for the Sidekick UI panel (the React app in the webview)
    to send a message saying it's ready (`system/announce`). If this message
    doesn't arrive within a few seconds, this error occurs.

    This might happen if:
    1. The Sidekick panel is open but hasn't finished loading its content yet.
    2. There's an error within the Sidekick UI panel itself (check the
       Webview Developer Tools in VS Code for errors).

    Attributes:
        timeout (float): The number of seconds the library waited for the UI response.
    """
    def __init__(self, timeout: float):
        self.timeout = timeout
        super().__init__(
            f"Connected to server, but timed out after {timeout:.1f} seconds waiting "
            f"for the Sidekick UI panel to signal it's ready. "
            f"Is the panel visible and fully loaded in VS Code?"
        )

class SidekickDisconnectedError(SidekickConnectionError):
    """Raised when the connection is lost *after* it was successfully established.

    This indicates that communication was working, but something interrupted it.
    Possible causes include:
    1. The Sidekick panel was closed in VS Code.
    2. The Sidekick VS Code extension crashed or was stopped.
    3. A network interruption occurred between the Python script and VS Code.
    4. An error occurred while trying to send or receive a message.

    **Important:** The library will **not** automatically try to reconnect.
    Subsequent attempts to send messages will also fail unless the connection
    is manually re-established (which typically involves restarting the script).

    Attributes:
        reason (str): A short description of why the disconnection occurred.
    """
    def __init__(self, reason: str = "Connection lost"):
        self.reason = reason
        super().__init__(
            f"Sidekick connection lost: {reason}. "
            f"The connection was active but is now broken. "
            f"The library will not automatically reconnect."
        )

# --- Connection Status Enum ---
class ConnectionStatus(Enum):
    """Represents the different states of the WebSocket connection."""
    DISCONNECTED = auto()               # Default state, or after closing/error.
    CONNECTING = auto()                 # Trying to establish the WebSocket link.
    CONNECTED_WAITING_SIDEKICK = auto() # Link established, waiting for UI 'ready' signal.
    CONNECTED_READY = auto()            # Everything is connected and ready for messages.

# --- Configuration and State (Internal Variables) ---
# These variables store the connection details and current state.
# They are considered internal and might change in future versions.

# The URL to connect to. Can be changed using sidekick.set_url() *before* connecting.
_ws_url: str = "ws://localhost:5163"
# Holds the active WebSocket connection object once established.
_ws_connection: Optional[websocket.WebSocket] = None
# A lock to prevent race conditions when multiple threads access connection state.
_connection_lock = threading.RLock()
# The background thread that listens for incoming messages from Sidekick.
_listener_thread: Optional[threading.Thread] = None
# Flag to track if the listener thread has been started for the current connection attempt.
_listener_started: bool = False
# A dictionary mapping module instance IDs (e.g., "grid-1") to the function
# that should handle messages for that specific instance.
_message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
# A simple counter used by sidekick.Canvas to generate unique command IDs.
_command_counter: int = 0

# A unique ID generated for this specific run of the Python script ("Hero").
_peer_id: Optional[str] = None
# Tracks the current status of the connection using the ConnectionStatus enum.
_connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
# Stores the peer IDs of Sidekick UI instances that have announced they are online.
_sidekick_peers_online: Set[str] = set()
# Configuration flags (set via sidekick.set_config).
_clear_on_connect: bool = True
_clear_on_disconnect: bool = False
# An optional global handler (for debugging) that receives *all* messages.
_global_message_handler: Optional[Callable[[Dict[str, Any]], None]] = None

# --- Threading Events for Synchronization ---
# These events are used to coordinate between the main script thread,
# the listener thread, and shutdown procedures.
# Signals the listener thread that it should stop running.
_stop_event = threading.Event()
# Set by the listener thread when the connection becomes CONNECTED_READY.
# activate_connection() waits on this event.
_ready_event = threading.Event()
# Set by shutdown() or Ctrl+C to signal run_forever() to exit cleanly.
_shutdown_event = threading.Event()

# --- Constants ---
# Timeouts and intervals used for connection and communication.
_INITIAL_CONNECT_TIMEOUT = 5.0 # Max seconds to wait for the initial WebSocket connection.
_SIDEKICK_WAIT_TIMEOUT = 2.0   # Max seconds to wait for the Sidekick UI 'online' message.
_LISTENER_RECV_TIMEOUT = 1.0   # How long ws.recv() waits before timing out in the listener loop.
                               # This allows the loop to check _stop_event periodically.
# WebSocket Ping settings (helps detect dead connections)
_PING_INTERVAL = 20            # Send a ping every 20 seconds.
_PING_TIMEOUT = 10             # Wait max 10 seconds for pong reply.

# --- Private Helper Functions (Used only within this module) ---

def _generate_peer_id() -> str:
    """Generates or returns the unique ID for this Python script instance."""
    global _peer_id
    # Generate it only once per script run.
    if _peer_id is None:
        _peer_id = f"hero-{uuid.uuid4().hex}"
        logger.info(f"Generated Hero Peer ID: {_peer_id}")
    return _peer_id

def _send_raw(ws: websocket.WebSocket, message_dict: Dict[str, Any]):
    """Safely sends a dictionary as a JSON string over the WebSocket.

    Handles JSON conversion and basic WebSocket send errors.

    Args:
        ws: The active WebSocket connection object.
        message_dict: The Python dictionary to send.

    Raises:
        SidekickDisconnectedError: If sending fails due to WebSocket issues
            (e.g., connection closed, broken pipe).
        Exception: For unexpected errors like JSON serialization problems.
    """
    try:
        # Convert the Python dictionary to a JSON string.
        message_json = json.dumps(message_dict)
        logger.debug(f"Sending raw: {message_json}")
        # Send the JSON string over the WebSocket.
        ws.send(message_json)
    except (websocket.WebSocketException, BrokenPipeError, OSError) as e:
        # These errors usually mean the connection is no longer valid.
        logger.error(f"WebSocket send error: {e}. Connection lost.")
        # Raise our specific error to indicate disconnection.
        # The calling function (send_message) will handle cleanup.
        raise SidekickDisconnectedError(f"Send failed: {e}")
    except Exception as e:
        # Catch other potential errors (e.g., json.dumps failure).
        logger.exception(f"Unexpected error sending message: {e}")
        # Wrap unexpected errors too, treating them as a disconnect.
        raise SidekickDisconnectedError(f"Unexpected send error: {e}")

def _send_system_announce(status: str):
    """Sends a special 'system/announce' message to the server.

    This tells the server (and other connected clients like the UI) that this
    Python script ('hero') is now 'online' or going 'offline'.

    Args:
        status (str): Either "online" or "offline".
    """
    # Use the lock to safely access the shared connection object.
    with _connection_lock:
        ws = _ws_connection # Get the current WebSocket object.
        peer_id = _generate_peer_id() # Make sure we have our ID.

        # Check if we actually have a valid, connected WebSocket.
        if ws and ws.connected and peer_id:
            announce_payload = {
                "peerId": peer_id,          # Our unique ID.
                "role": "hero",             # We are the Python script.
                "status": status,           # 'online' or 'offline'.
                "version": __version__,     # Library version.
                "timestamp": int(time.time() * 1000) # Current time in ms.
            }
            message = {
                "id": 0, # Reserved, usually 0.
                "module": "system",
                "type": "announce",
                "payload": announce_payload
            }
            try:
                # Use the safe sending function.
                _send_raw(ws, message)
                logger.info(f"Sent system announce: {status}")
            except SidekickDisconnectedError as e:
                # If sending the announce fails (e.g., during shutdown), log a
                # warning but don't crash the shutdown process itself.
                logger.warning(f"Could not send system announce '{status}': {e}")
            except Exception as e:
                 logger.warning(f"Unexpected error sending system announce '{status}': {e}")
        elif status == "offline":
             # It's okay if we can't send 'offline' if we're already disconnected.
             logger.debug("Cannot send offline announce, connection already closed or closing.")
        else:
             # It's a problem if we try to send 'online' but aren't connected.
             logger.warning(f"Cannot send system announce '{status}', WebSocket not connected.")

def _listen_for_messages():
    """The main function run by the background listener thread.

    It continuously waits for messages from the WebSocket server, parses them,
    and dispatches them to the appropriate handlers (either the global handler
    or a specific module instance's handler). It also updates connection state
    based on 'system/announce' messages from the Sidekick UI.

    This function runs until `_stop_event` is set or the connection breaks.
    If the connection breaks unexpectedly, it triggers `close_connection` to
    clean up and potentially raise `SidekickDisconnectedError`.
    """
    global _connection_status, _message_handlers, _sidekick_peers_online, _listener_started, _global_message_handler
    logger.info("Listener thread started.")
    ws = None
    disconnect_reason = "Listener thread terminated normally" # Default exit reason

    # Keep looping as long as the stop signal hasn't been received.
    while not _stop_event.is_set():
        # --- Check Connection State Safely ---
        with _connection_lock:
            # If connection was closed externally, stop listening.
            if _connection_status == ConnectionStatus.DISCONNECTED:
                disconnect_reason = "Status became DISCONNECTED"
                break
            # Ensure we still have a valid WebSocket object.
            if _ws_connection and _ws_connection.connected:
                ws = _ws_connection
            else:
                # Connection object is gone or disconnected.
                disconnect_reason = "WebSocket connection lost unexpectedly"
                # Only log a warning if this wasn't a planned stop.
                if not _stop_event.is_set():
                    logger.warning("Listener: WebSocket connection lost.")
                break

        if not ws:
            # Should be redundant due to above check, but added safety.
            disconnect_reason = "WebSocket object is None"
            if not _stop_event.is_set():
                logger.warning("Listener: WebSocket object is None, stopping loop.")
            break

        # --- Receive Message ---
        try:
            # Wait for a message, but time out after _LISTENER_RECV_TIMEOUT seconds.
            # This timeout allows the loop to check the _stop_event regularly.
            ws.settimeout(_LISTENER_RECV_TIMEOUT)
            message_str = ws.recv()

            # Check again if stop was signaled *while* waiting for recv().
            if _stop_event.is_set():
                disconnect_reason = "Stop event set during receive"
                break

            # An empty message usually means the server closed the connection cleanly.
            if not message_str:
                disconnect_reason = "Server closed connection (received empty message)"
                if not _stop_event.is_set():
                    logger.info("Listener: Server closed connection.")
                break

            logger.debug(f"Listener: Received raw message: {message_str}")
            # Parse the incoming JSON string into a Python dictionary.
            message_data = json.loads(message_str)

            # --- Process Message Safely ---
            # Acquire the lock to prevent conflicts while handling the message
            # and potentially updating shared state (_connection_status, handlers).
            with _connection_lock:
                # Check status again inside the lock.
                if _stop_event.is_set() or _connection_status == ConnectionStatus.DISCONNECTED:
                    break # Stop processing if we are stopping/disconnected.

                # --- 1. Global Handler ---
                # If a global handler is registered, call it first with the raw message.
                if _global_message_handler:
                     try:
                         _global_message_handler(message_data)
                     except Exception as e:
                         logger.exception(f"Listener: Error in global message handler: {e}")

                # --- 2. Message Dispatch ---
                module = message_data.get('module')
                msg_type = message_data.get('type')
                payload = message_data.get('payload')

                # --- Handle System Announce (Sidekick UI Ready?) ---
                if module == 'system' and msg_type == 'announce' and payload:
                    peer_id = payload.get('peerId')
                    role = payload.get('role')
                    status = payload.get('status')

                    # Is this announcement from a Sidekick UI panel?
                    if peer_id and role == 'sidekick':
                        if status == 'online':
                            # A Sidekick UI just connected.
                            was_empty = not _sidekick_peers_online # Was this the *first* UI?
                            _sidekick_peers_online.add(peer_id)
                            logger.info(f"Sidekick peer online: {peer_id}")

                            # If this IS the first UI and we were waiting...
                            if was_empty and _connection_status == ConnectionStatus.CONNECTED_WAITING_SIDEKICK:
                                logger.info(f"First Sidekick UI '{peer_id}' announced online. System is READY.")
                                # Update the status to READY!
                                _connection_status = ConnectionStatus.CONNECTED_READY
                                # If configured, send a 'clearAll' command now.
                                if _clear_on_connect:
                                    logger.info("clear_on_connect is True, sending global/clearAll.")
                                    try:
                                        # Can call directly now, connection assumed ready
                                        clear_all()
                                    except SidekickConnectionError as e_clr:
                                        logger.error(f"Failed to clearAll on connect: {e_clr}")
                                # IMPORTANT: Signal the main thread (waiting in activate_connection)
                                # that the connection is finally ready!
                                _ready_event.set()

                        elif status == 'offline':
                            # A Sidekick UI disconnected.
                            if peer_id in _sidekick_peers_online:
                                _sidekick_peers_online.discard(peer_id)
                                logger.info(f"Sidekick peer offline: {peer_id}")
                                # Note: The connection remains READY even if all UIs leave.
                                # A disconnect error will only occur on the next send/receive
                                # attempt if the underlying WebSocket is actually closed.

                # --- Handle Module Event/Error (Dispatch to Instance) ---
                elif msg_type in ['event', 'error']:
                    # These messages come FROM a specific UI module instance.
                    # The 'src' field tells us which one.
                    instance_id = message_data.get('src')
                    if instance_id and instance_id in _message_handlers:
                        # Find the handler function registered for this instance ID.
                        handler = _message_handlers[instance_id]
                        try:
                             logger.debug(f"Listener: Invoking handler for instance '{instance_id}' (type: {msg_type}).")
                             # Call the instance's specific handler (e.g., Grid._internal_message_handler).
                             handler(message_data)
                        except Exception as e:
                             # Catch errors within the user's callback or the internal handler.
                             logger.exception(f"Listener: Error executing handler for '{instance_id}': {e}")
                    elif instance_id:
                        # We received a message for an instance we don't know about
                        # (maybe it was already removed). Just log it.
                         logger.debug(f"Listener: No specific handler registered for instance '{instance_id}' for message type {msg_type}.")
                    else:
                        # The message is missing the 'src' ID, can't dispatch.
                         logger.debug(f"Listener: Received {msg_type} message without 'src': {message_data}")
                else:
                    # We received a message type we don't handle (e.g., 'spawn' from UI).
                    logger.debug(f"Listener: Received unhandled message type: module='{module}', type='{msg_type}'")

        except websocket.WebSocketTimeoutException:
            # This is expected because of ws.settimeout(). Just continue the loop.
            continue
        except websocket.WebSocketConnectionClosedException:
            # The server explicitly closed the connection.
            disconnect_reason = "WebSocketConnectionClosedException"
            if not _stop_event.is_set():
                logger.info("Listener: WebSocket connection closed by server.")
            break # Exit the loop.
        except (json.JSONDecodeError, TypeError) as e:
            # Received invalid JSON or unexpected data type.
            logger.error(f"Listener: Failed to parse JSON or invalid data: {message_str}, Error: {e}")
            continue # Try to continue listening.
        except OSError as e:
            # Handle lower-level OS errors (network issues, etc.).
            # Ignore "Bad file descriptor" if we are already stopping (expected).
            if not (_stop_event.is_set() and e.errno == 9):
                disconnect_reason = f"OS error ({e})"
                if not _stop_event.is_set():
                     logger.warning(f"Listener: OS error ({e}), likely connection closed.")
                break # Exit the loop on OS errors.
        except Exception as e:
            # Catch any other unexpected error during the loop.
            disconnect_reason = f"Unexpected error: {e}"
            if not _stop_event.is_set():
                 logger.exception(f"Listener: Unexpected error: {e}")
            break # Exit the loop.

    # --- Listener Loop Exit ---
    logger.info(f"Listener thread finished. Reason: {disconnect_reason}")
    with _connection_lock:
        # Ensure the flag reflects that the listener is no longer running.
        _listener_started = False

    # If the loop exited *unexpectedly* (not via _stop_event)...
    if not _stop_event.is_set():
        logger.warning("Listener thread terminated unexpectedly. Initiating disconnect process.")
        # Trigger the cleanup process. This will likely lead to a
        # SidekickDisconnectedError being raised for the main thread.
        # Run close_connection in a new thread to avoid potential deadlocks.
        threading.Thread(
            target=close_connection,
            # Mark as an exception, pass the reason.
            args=(False, True, disconnect_reason),
            daemon=True # Don't let this cleanup thread block script exit.
        ).start()


def _ensure_connection():
    """Internal function to establish the initial WebSocket connection.

    Called by `activate_connection`. It attempts to connect to the server
    and starts the listener thread if successful.

    Raises:
        SidekickConnectionRefusedError: If the WebSocket connection fails.
    """
    global _ws_connection, _listener_thread, _listener_started, _connection_status

    # --- This function assumes _connection_lock is already held by the caller ---

    # Safety check: should only be called when DISCONNECTED.
    if _connection_status != ConnectionStatus.DISCONNECTED:
        logger.warning(f"_ensure_connection called when status is {_connection_status.name}")
        return

    logger.info(f"Attempting to connect to Sidekick server at {_ws_url}...")
    # --- Prepare for New Connection ---
    _connection_status = ConnectionStatus.CONNECTING
    _sidekick_peers_online.clear() # Reset known UI peers.
    # Reset threading events for this new attempt.
    _stop_event.clear()
    _ready_event.clear()
    _shutdown_event.clear()

    # --- Attempt Connection ---
    try:
        # Create the WebSocket connection. This might block for up to
        # _INITIAL_CONNECT_TIMEOUT seconds.
        _ws_connection = websocket.create_connection(
            _ws_url,
            timeout=_INITIAL_CONNECT_TIMEOUT,
            ping_interval=_PING_INTERVAL, # Enable automatic pings
            ping_timeout=_PING_TIMEOUT
        )
        logger.info("Successfully connected to Sidekick server.")

        # --- Connection Successful ---
        # Send our 'online' announcement immediately.
        _send_system_announce("online")
        # Update status: We are connected, but waiting for the UI panel.
        _connection_status = ConnectionStatus.CONNECTED_WAITING_SIDEKICK

        # Start the listener thread if it's not already running.
        if not _listener_started and not (_listener_thread and _listener_thread.is_alive()):
            logger.info("Starting WebSocket listener thread.")
            # Create and start the thread. It's crucial to set daemon=True so
            # this background thread doesn't prevent the main script from exiting
            # if the main script finishes before sidekick.shutdown() is called.
            _listener_thread = threading.Thread(target=_listen_for_messages, daemon=True)
            _listener_thread.start()
            _listener_started = True
        elif _listener_started:
             # Should not happen with correct state management.
             logger.warning("Listener thread already marked as started during connect sequence (unexpected).")

    # --- Handle Connection Errors ---
    except (websocket.WebSocketException, ConnectionRefusedError, OSError, TimeoutError) as e:
        logger.error(f"Failed to connect to Sidekick server at {_ws_url}: {e}")
        # Clean up state on failure.
        _ws_connection = None
        _connection_status = ConnectionStatus.DISCONNECTED
        _stop_event.set() # Signal potential (failed) listener to stop.
        _listener_started = False
        # Raise the specific error for activate_connection to handle.
        raise SidekickConnectionRefusedError(_ws_url, e)
    except Exception as e:
        # Catch any other unexpected errors during setup.
        logger.exception(f"Unexpected error during connection: {e}")
        _ws_connection = None
        _connection_status = ConnectionStatus.DISCONNECTED
        _stop_event.set()
        _listener_started = False
        # Wrap the error.
        raise SidekickConnectionRefusedError(_ws_url, e)


# --- Public API Functions ---
# These functions are intended to be used directly by users of the library.

def set_url(url: str):
    """Sets the WebSocket URL where the Sidekick server is expected to be listening.

    **Important:** You **must** call this *before* creating any Sidekick modules
    (like `Grid`, `Console`) or trying to send any messages, as the first action
    will trigger the connection attempt using the currently set URL.

    If you call this after a connection attempt has already been made (even
    if it failed), it will log a warning and have no effect unless you call
    `sidekick.shutdown()` first to completely reset the connection state.

    Args:
        url (str): The full WebSocket URL, starting with "ws://" or "wss://".
                   The default is "ws://localhost:5163".

    Examples:
        >>> import sidekick
        >>> # If your Sidekick server is running on a different port
        >>> sidekick.set_url("ws://127.0.0.1:8000")
        >>>
        >>> # Now it's safe to create Sidekick modules
        >>> console = sidekick.Console()
    """
    global _ws_url
    with _connection_lock:
        # Only allow changing the URL if we haven't even started connecting yet.
        if _connection_status != ConnectionStatus.DISCONNECTED:
            logger.warning("Cannot change Sidekick URL after a connection attempt "
                           "has been made. Call sidekick.shutdown() first if needed.")
            return
        # Simple validation.
        if not url.startswith(("ws://", "wss://")):
             logger.error(f"Invalid WebSocket URL provided: '{url}'. "
                          f"It must start with 'ws://' or 'wss://'. Using default '{_ws_url}'.")
             return # Keep the existing default if invalid format provided
        _ws_url = url
        logger.info(f"Sidekick WebSocket URL set to: {_ws_url}")

def set_config(clear_on_connect: bool = True, clear_on_disconnect: bool = False):
    """Configures automatic clearing of the Sidekick UI.

    **Important:** You **must** call this *before* creating any Sidekick modules
    or trying to send any messages. Like `set_url`, calling it after a connection
    attempt will have no effect unless `shutdown()` is called first.

    Args:
        clear_on_connect (bool): If True (the default), the library will send
            a command to clear *all* existing elements from the Sidekick UI
            as soon as the connection becomes fully ready (when the UI panel
            signals it's online). Set this to False if you want your script
            to potentially interact with UI elements left over from a previous
            script run (less common).
        clear_on_disconnect (bool): If True (default is False), the library
            will *attempt* to send a command to clear the Sidekick UI when
            your script disconnects cleanly (e.g., when `shutdown()` is called
            or the script ends normally). This is a "best-effort" attempt and
            might not succeed if the disconnection is abrupt or caused by an error.
    """
    global _clear_on_connect, _clear_on_disconnect
    with _connection_lock:
        # Only allow changing config if we haven't started connecting.
        if _connection_status != ConnectionStatus.DISCONNECTED:
            logger.warning("Cannot change Sidekick config after a connection attempt "
                           "has been made. Call sidekick.shutdown() first if needed.")
            return
        _clear_on_connect = clear_on_connect
        _clear_on_disconnect = clear_on_disconnect
        logger.info(f"Sidekick config set: clear_on_connect={_clear_on_connect}, "
                    f"clear_on_disconnect={_clear_on_disconnect}")

def activate_connection():
    """Ensures the connection to Sidekick is established and fully ready.

    This is the **key function** that guarantees the library is prepared for
    sending messages. It performs these steps:

    1. Checks the current connection status. If already `CONNECTED_READY`, it returns immediately.
    2. If `DISCONNECTED`, it calls the internal `_ensure_connection()` to:
       - Attempt the WebSocket connection to the server.
       - Start the background listener thread.
       - Send the initial 'online' announcement.
    3. If the connection to the server succeeds (status becomes
       `CONNECTED_WAITING_SIDEKICK`), it then **pauses (blocks)** execution.
    4. It waits for the background listener thread to receive the 'online'
       announcement from the Sidekick UI panel (which sets the `_ready_event`).
    5. Once the `_ready_event` is set and the status is `CONNECTED_READY`, this
       function returns, and the script can proceed.

    **When is it called?** This function is called automatically *before* any
    message is sent (e.g., by `grid.set_color`, `console.print`, `viz.show`, etc.)
    and also at the beginning of `sidekick.run_forever()`. You generally don't
    need to call it yourself unless you want to explicitly establish the
    connection at a specific point without immediately sending a command.

    Raises:
        SidekickConnectionRefusedError: If the initial WebSocket connection attempt fails.
        SidekickTimeoutError: If the Sidekick UI panel doesn't signal readiness within
                              the `_SIDEKICK_WAIT_TIMEOUT`.
        SidekickDisconnectedError: If the connection is lost while waiting for the
                                   UI panel or if the state is inconsistent.
    """
    # Acquire lock to check status and potentially start connection.
    with _connection_lock:
        current_status = _connection_status
        logger.debug(f"activate_connection called. Current status: {current_status.name}")

        # If already ready, we're good to go!
        if current_status == ConnectionStatus.CONNECTED_READY:
            logger.debug("Connection already READY.")
            return

        # If disconnected, need to start the connection process.
        if current_status == ConnectionStatus.DISCONNECTED:
            try:
                # This internal function attempts connection and starts the listener.
                # It raises SidekickConnectionRefusedError on failure.
                _ensure_connection()
                # If _ensure_connection succeeded, status is now CONNECTING or
                # CONNECTED_WAITING_SIDEKICK. Proceed to wait for the UI.
                logger.debug("Initial connection attempt successful, now waiting for UI readiness.")
            except SidekickConnectionError as e:
                # If _ensure_connection failed, re-raise the error immediately.
                logger.error(f"Initial connection failed in activate_connection: {e}")
                raise e

        # If we are CONNECTING or CONNECTED_WAITING_SIDEKICK, fall through to wait.

    # --- Wait for READY state ---
    # **IMPORTANT**: Release the lock *before* waiting on the event.
    # This allows the listener thread (which needs the lock to update the state
    # and set the event) to proceed.
    logger.debug(f"Waiting up to {_SIDEKICK_WAIT_TIMEOUT}s for Sidekick UI (_ready_event)...")

    # Block until the listener thread calls _ready_event.set() OR the timeout occurs.
    ready_signal_received = _ready_event.wait(timeout=_SIDEKICK_WAIT_TIMEOUT)

    # --- Check Status *After* Waiting ---
    # Re-acquire the lock to safely check the final status.
    with _connection_lock:
        # Case 1: Success! Event was set and status is READY.
        if ready_signal_received and _connection_status == ConnectionStatus.CONNECTED_READY:
            logger.debug("Sidekick connection is now READY.")
            return

        # Case 2: Timeout! Event was *not* set within the time limit.
        elif not ready_signal_received:
            timeout_reason = f"Timed out waiting for Sidekick UI after {_SIDEKICK_WAIT_TIMEOUT}s"
            logger.error(timeout_reason)
            # Clean up the partially established connection since the UI never showed up.
            # Run cleanup in a thread to avoid potential deadlocks.
            threading.Thread(target=close_connection, args=(False, True, timeout_reason), daemon=True).start()
            raise SidekickTimeoutError(_SIDEKICK_WAIT_TIMEOUT)

        # Case 3: Inconsistency. Event *was* set, but status is *not* READY.
        # This could happen if the connection dropped immediately after becoming ready,
        # before this thread could re-acquire the lock.
        else:
            disconnect_reason = f"Ready event was set, but status is now inconsistent: {_connection_status.name}"
            logger.error(f"Connection state error: {disconnect_reason}")
            # Trigger cleanup if not already disconnected.
            if _connection_status != ConnectionStatus.DISCONNECTED:
                 threading.Thread(target=close_connection, args=(False, True, disconnect_reason), daemon=True).start()
            raise SidekickDisconnectedError(disconnect_reason)

def send_message(message_dict: Dict[str, Any]):
    """Sends a command message (as a dictionary) to the Sidekick UI.

    This is the primary way the library sends instructions like "update grid cell"
    or "append text to console" to the UI.

    How it works:
    1. It first calls `activate_connection()` to ensure the connection is fully
       ready. This might block your script initially or raise connection errors.
    2. If the connection is ready, it converts the `message_dict` to JSON and
       sends it over the WebSocket immediately.

    Args:
        message_dict (Dict[str, Any]): A Python dictionary representing the
            message to send. It must conform to the Sidekick communication
            protocol structure (including `module`, `type`, `target`/`src`,
            and a `payload` with **camelCase keys**). Module classes like
            `Grid`, `Console`, etc., construct these dictionaries internally.

    Raises:
        SidekickConnectionRefusedError: If the initial connection fails when
                                         `activate_connection` is called.
        SidekickTimeoutError: If waiting for the Sidekick UI times out during
                               `activate_connection`.
        SidekickDisconnectedError: If the connection is lost *before* or *during*
                                   the attempt to send this message.
        TypeError: If `message_dict` is not actually a dictionary.
        Exception: For other unexpected errors (e.g., JSON serialization failure).
    """
    if not isinstance(message_dict, dict):
        raise TypeError("message_dict must be a dictionary")

    # 1. Ensure connection is ready. This blocks or raises if not ready.
    activate_connection()

    # 2. Acquire lock to safely access the WebSocket object and send.
    with _connection_lock:
        ws = _ws_connection
        # Double-check the status and connection object *after* getting the lock.
        # activate_connection() should guarantee readiness, but this is a safety
        # measure against rare race conditions.
        if _connection_status != ConnectionStatus.CONNECTED_READY or not ws or not ws.connected:
            disconnect_reason = f"Connection state invalid ({_connection_status.name}) just before sending"
            logger.error(disconnect_reason)
            # Trigger cleanup if not already disconnected.
            if _connection_status != ConnectionStatus.DISCONNECTED:
                 threading.Thread(target=close_connection, args=(False, True, disconnect_reason), daemon=True).start()
            raise SidekickDisconnectedError(disconnect_reason)

        # 3. Attempt the send using the internal helper.
        try:
            # _send_raw handles JSON conversion and raises SidekickDisconnectedError on failure.
            _send_raw(ws, message_dict)
        except SidekickDisconnectedError as e:
             # If _send_raw failed, log and initiate cleanup.
             logger.error(f"Send message failed: {e.reason}")
             if _connection_status != ConnectionStatus.DISCONNECTED:
                  threading.Thread(target=close_connection, args=(False, True, f"Send failed: {e.reason}"), daemon=True).start()
             # Re-raise the error to notify the caller.
             raise e
        except Exception as e:
             # Catch other unexpected errors during send (e.g., JSON issues).
             disconnect_reason = f"Unexpected error during send: {e}"
             logger.exception(disconnect_reason)
             if _connection_status != ConnectionStatus.DISCONNECTED:
                  threading.Thread(target=close_connection, args=(False, True, disconnect_reason), daemon=True).start()
             # Wrap the error.
             raise SidekickDisconnectedError(disconnect_reason)

def clear_all():
    """Sends a command to remove *all* visual elements from the Sidekick panel.

    This clears any Grids, Consoles, Viz panels, etc., that were created by
    *this* Python script instance. It's useful for resetting the UI state.

    Raises:
        SidekickConnectionError (or subclass): If the connection is not ready or
                                              if sending the command fails.
    """
    logger.info("Requesting global clearAll of Sidekick UI elements.")
    message = {
        "id": 0,
        "module": "global", # Special module target for global actions
        "type": "clearAll",
        "payload": None # No extra data needed
    }
    # Use the public send_message, which handles readiness checks and errors.
    send_message(message)

def close_connection(log_info=True, is_exception=False, reason=""):
    """Closes the WebSocket connection and cleans up resources. (Mostly internal).

    This function stops the listener thread, closes the WebSocket, and resets
    internal state. It's called automatically by `shutdown()` and `atexit`,
    and also internally if the listener thread detects an unrecoverable error.

    **You should generally use `sidekick.shutdown()` instead of calling this directly.**

    Args:
        log_info (bool): If True, logs status messages during closure.
        is_exception (bool): If True, indicates this closure is due to an error.
                             This might cause `SidekickDisconnectedError` to be
                             raised *after* cleanup, unless a clean shutdown via
                             `_shutdown_event` was already signaled.
        reason (str): Optional description of why the connection is closing,
                      used for logging and potentially in errors.
    """
    global _ws_connection, _listener_thread, _listener_started, _connection_status, _message_handlers, _sidekick_peers_online

    disconnect_exception_to_raise = None # Store potential exception

    # Use lock to safely modify shared state during cleanup.
    with _connection_lock:
        # Avoid closing multiple times.
        if _connection_status == ConnectionStatus.DISCONNECTED:
            if log_info: logger.debug("Connection already closed or closing.")
            return

        if log_info: logger.info(f"Closing Sidekick WebSocket connection... (Exception: {is_exception}, Reason: '{reason}')")
        initial_status = _connection_status # Remember status before changing it

        # --- 1. Signal Listener to Stop ---
        # Tell the background thread to exit its loop.
        _stop_event.set()
        # Connection is no longer ready.
        _ready_event.clear()

        # --- 2. Update Internal State ---
        _connection_status = ConnectionStatus.DISCONNECTED
        _sidekick_peers_online.clear() # No longer tracking UI peers.

        # --- 3. Best-Effort Cleanup Messages ---
        # Try to send 'clearAll' (if configured) and 'offline' announce,
        # but only if this is a clean shutdown (not an error) and we
        # were actually connected. Don't worry too much if these fail.
        ws_temp = _ws_connection # Grab reference under lock
        if not is_exception and ws_temp and ws_temp.connected and initial_status != ConnectionStatus.CONNECTING:
             # Send clearAll if configured for disconnect.
             if _clear_on_disconnect:
                  logger.debug("Attempting to send global/clearAll on disconnect (best-effort).")
                  clear_all_msg = {"id": 0, "module": "global", "type": "clearAll", "payload": None}
                  try: _send_raw(ws_temp, clear_all_msg)
                  except Exception: logger.warning("Failed to send clearAll during disconnect (ignored).")

             # Send offline announce.
             logger.debug("Attempting to send offline announce (best-effort).")
             try: _send_system_announce("offline")
             except Exception: logger.warning("Failed to send offline announce during disconnect (ignored).")

        # --- 4. Close the WebSocket ---
        if ws_temp:
            try:
                # Set a short timeout for the close operation itself.
                ws_temp.settimeout(0.5)
                ws_temp.close()
            except Exception as e:
                 logger.warning(f"Error during WebSocket close(): {e}")
        # Clear the global reference.
        _ws_connection = None

        # --- 5. Prepare Exception (if needed) ---
        # If this close was triggered by an error, prepare the exception object now.
        # We will raise it *after* releasing the lock and joining the thread.
        if is_exception:
            disconnect_exception_to_raise = SidekickDisconnectedError(reason or "Connection closed due to an error")

        # --- 6. Clear Listener Thread References ---
        listener_thread_temp = _listener_thread # Grab reference under lock
        _listener_thread = None
        _listener_started = False # Allow listener to potentially restart later

    # --- 7. Join Listener Thread (Outside the main lock) ---
    # Wait for the listener thread to actually finish executing.
    if listener_thread_temp and listener_thread_temp.is_alive():
        if log_info: logger.debug("Waiting for listener thread to stop...")
        try:
            # Wait max ~1.5s for the listener to exit.
            listener_thread_temp.join(timeout=_LISTENER_RECV_TIMEOUT + 0.5)
            if listener_thread_temp.is_alive():
                 logger.warning(f"Listener thread did not stop gracefully after join timeout.")
            elif log_info:
                 logger.debug("Listener thread stopped.")
        except Exception as e:
             logger.warning(f"Error joining listener thread: {e}")
    elif log_info:
        logger.debug("Listener thread was not running or already finished.")

    # --- 8. Clear Instance Message Handlers ---
    # Can do this outside the lock after listener is stopped.
    if _message_handlers:
        logger.debug(f"Clearing {len(_message_handlers)} instance message handlers.")
        _message_handlers.clear()

    if log_info: logger.info("Sidekick WebSocket connection closed.")

    # --- 9. Raise Exception (if needed) ---
    # If this cleanup was triggered by an error (`is_exception` was True),
    # and if a clean shutdown wasn't *also* requested concurrently via the
    # _shutdown_event, then raise the disconnect error now to signal the problem.
    if disconnect_exception_to_raise:
        # Check if a clean shutdown (e.g., via Ctrl+C or shutdown()) occurred
        # around the same time as the error.
        if not _shutdown_event.is_set():
            logger.error(f"Raising disconnect exception after cleanup: {disconnect_exception_to_raise}")
            # Raise the exception for the calling code to handle.
            raise disconnect_exception_to_raise
        else:
            # If a clean shutdown was requested, don't raise the error,
            # just log the original problem.
            logger.warning(f"Suppressed disconnect exception because clean shutdown was also requested: {disconnect_exception_to_raise}")

def run_forever():
    """Keeps your Python script running indefinitely to handle Sidekick UI events.

    Why use this? If your script needs to react to things happening in the
    Sidekick panel (like button clicks, grid cell clicks, or text input),
    your script needs to stay alive to listen for those events. Calling
    `run_forever()` at the end of your setup code does exactly that: it pauses
    the main part of your script, while allowing the background listener thread
    (managed by this module) to keep receiving and processing events from Sidekick,
    triggering your callback functions (`on_click`, `on_input_text`, etc.).

    How to stop it:
    1. Press `Ctrl+C` in the terminal where your script is running.
    2. Call `sidekick.shutdown()` from within one of your callback functions
       (e.g., have a "Quit" button that calls `shutdown`).
    3. If the connection to Sidekick breaks unexpectedly, `run_forever()` will
       also stop (after a `SidekickDisconnectedError` is raised).

    Raises:
        SidekickConnectionError (or subclass): If the connection to Sidekick cannot
                                              be established *before* entering the
                                              waiting loop.
    """
    # 1. Ensure connection is ready before starting. Blocks or raises if fails.
    try:
        activate_connection()
    except SidekickConnectionError as e:
        logger.error(f"Cannot start run_forever: Initial connection failed: {e}")
        # Don't proceed if we can't even connect.
        raise e

    logger.info("Sidekick entering run_forever mode. Press Ctrl+C or call sidekick.shutdown() to exit.")
    _shutdown_event.clear() # Make sure the shutdown signal is clear initially.

    try:
        # --- Main Waiting Loop ---
        # Keep looping as long as the shutdown signal hasn't been set.
        while not _shutdown_event.is_set():
            # Wait efficiently for the shutdown signal.
            # The `wait()` method will return True if the event was set,
            # or False if the timeout expired. Check status every second.
            signaled = _shutdown_event.wait(timeout=1.0)
            if signaled:
                logger.debug("run_forever: Shutdown event signaled.")
                break # Exit loop cleanly.

            # Optional check: If the listener detected a disconnect, exit early.
            with _connection_lock:
                 if _connection_status != ConnectionStatus.CONNECTED_READY:
                      logger.warning(f"run_forever: Connection status changed to {_connection_status.name}. Exiting loop.")
                      # Note: The actual SidekickDisconnectedError is likely raised by
                      # the listener triggering close_connection(is_exception=True).
                      # This check just helps exit the wait loop sooner.
                      break

    except KeyboardInterrupt:
        # User pressed Ctrl+C.
        logger.info("KeyboardInterrupt received, shutting down Sidekick.")
        # The `finally` block below will handle calling shutdown().
    except Exception as e:
        # Catch any other unexpected errors during the wait.
        logger.exception(f"Unexpected error during run_forever wait loop: {e}")
        # Let `finally` handle shutdown.
    finally:
        # --- Cleanup ---
        # This block always runs, whether the loop exited normally,
        # via Ctrl+C, or an unexpected error.
        # Check if a clean shutdown was *already* signaled.
        if not _shutdown_event.is_set():
            # If not, it means we exited for another reason (Ctrl+C, error, disconnect).
            # Initiate a clean shutdown now.
            logger.debug("run_forever: Loop exited unexpectedly or via Ctrl+C, initiating shutdown.")
            shutdown() # Call the standard shutdown procedure.
        else:
             logger.debug("run_forever: Loop exited cleanly via shutdown signal.")

    logger.info("Sidekick run_forever mode finished.")

def shutdown():
    """Initiates a clean shutdown of the Sidekick connection.

    This function:
    - Signals `run_forever()` (if it's running) to stop waiting.
    - Attempts to send an 'offline' announcement to the Sidekick server.
    - Attempts to send a 'clearAll' command (if configured via `set_config`).
    - Closes the WebSocket connection.
    - Stops the background listener thread.
    - Clears internal state.

    It's safe to call this function multiple times; subsequent calls will have no effect.
    This function is also registered automatically via `atexit` to be called when
    your Python script exits normally.

    You might call this manually from an event handler (e.g., a "Quit" button's
    `on_click` callback) to programmatically stop `run_forever()`.
    """
    with _connection_lock:
        # Check if shutdown is already done or in progress.
        if _shutdown_event.is_set() and _connection_status == ConnectionStatus.DISCONNECTED:
            logger.debug("Shutdown already completed or in progress.")
            return

        logger.info("Sidekick shutdown requested.")
        # Signal that a clean shutdown is intended. This prevents disconnect
        # errors from being raised unnecessarily if cleanup happens concurrently
        # with an error, and tells run_forever() to stop.
        _shutdown_event.set()

    # Initiate the closing process. Run it outside the main lock.
    # This is a clean shutdown request, so set is_exception=False.
    close_connection(log_info=True, is_exception=False, reason="Shutdown requested")

# --- Registration/Utility Functions (Mostly Internal/Advanced) ---

def register_message_handler(instance_id: str, handler: Callable[[Dict[str, Any]], None]):
    """Registers a function to handle messages for a specific module instance. (Internal use).

    This is automatically called by the base class (`BaseModule`) when you
    create a Sidekick module instance (like `Grid`, `Console`). The provided
    `handler` function (usually the `_internal_message_handler` method of the
    instance) will be called by the listener thread whenever an 'event' or
    'error' message arrives from the Sidekick UI with a `src` field matching
    the `instance_id`.

    Args:
        instance_id (str): The unique ID of the module instance (e.g., "grid-1").
        handler (Callable): The function to call for incoming messages for this ID.
                            It must accept one argument: the message dictionary.

    Raises:
        TypeError: If the provided handler is not a callable function.
    """
    if not callable(handler):
        raise TypeError(f"Handler for instance '{instance_id}' must be callable.")
    with _connection_lock:
        # Only register if the connection isn't already fully shut down.
        # Allows registration even before connection is fully READY.
        if _connection_status != ConnectionStatus.DISCONNECTED or not _stop_event.is_set():
            logger.info(f"Registering internal message handler for instance '{instance_id}'.")
            _message_handlers[instance_id] = handler
        else:
            logger.warning(f"Connection closed or closing, handler for '{instance_id}' not registered.")

def unregister_message_handler(instance_id: str):
    """Removes the message handler for a specific module instance. (Internal use).

    This is called automatically when a module's `remove()` method is used,
    or during the final `close_connection` cleanup.

    Args:
        instance_id (str): The ID of the module instance whose handler should be removed.
    """
    with _connection_lock:
        # Remove the handler from the dictionary if it exists.
        if instance_id in _message_handlers:
            logger.info(f"Unregistering internal message handler for instance '{instance_id}'.")
            del _message_handlers[instance_id]
        else:
            # It's normal for this to happen during cleanup if already removed.
            logger.debug(f"No internal message handler found for instance '{instance_id}' to unregister.")

def register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]]):
    """Registers a single function to receive *all* incoming messages from Sidekick.

    **Advanced Usage:** This is mostly intended for debugging or building very
    custom low-level integrations. The function you provide here will be called
    by the listener thread for *every* message received from the Sidekick server,
    *before* the message is dispatched to any specific module instance handlers.

    Args:
        handler (Optional[Callable]): The function to call with each raw message
            dictionary received. It should accept one argument (the message dict).
            Pass `None` to remove any existing global handler.

    Raises:
        TypeError: If the provided handler is not callable and not `None`.
    """
    global _global_message_handler
    with _connection_lock:
        if handler is None:
            # Remove the global handler.
            if _global_message_handler is not None:
                logger.info("Unregistering global message handler.")
                _global_message_handler = None
        elif callable(handler):
            # Set the new global handler.
            logger.info(f"Registering global message handler: {handler}")
            _global_message_handler = handler
        else:
            raise TypeError("Global message handler must be callable or None.")

def get_next_command_id() -> int:
    """Generates the next sequential ID for Canvas drawing commands. (Internal use).

    The Sidekick Canvas protocol requires each drawing command (`line`, `rect`, etc.)
    to have a unique, sequential ID within the connection session. This function
    provides those IDs.

    Returns:
        int: The next unique command ID.
    """
    global _command_counter
    # Use lock for thread safety, although typically only called from main thread.
    with _connection_lock:
        _command_counter += 1
        return _command_counter

# --- Automatic Cleanup on Exit ---
# Register the main shutdown() function to be called automatically when the
# Python interpreter exits normally. This ensures we attempt to close the
# WebSocket, stop the listener, and send cleanup messages if possible.
atexit.register(shutdown)