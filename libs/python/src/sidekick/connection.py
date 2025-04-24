"""Manages the WebSocket connection between your Python script and the Sidekick UI.

This module acts as the central communication hub for the Sidekick library. It
handles the technical details of establishing and maintaining a real-time
connection with the Sidekick panel running in Visual Studio Code.

Key Responsibilities:

*   **Connecting:** Automatically attempts to connect to the Sidekick server
    (usually running within the VS Code extension) the first time your script
    tries to interact with a Sidekick module (e.g., when you create `sidekick.Grid()`).
*   **Blocking Connection:** It **pauses** (blocks) your script during the initial
    connection phase until it confirms that both the server is reached and the
    Sidekick UI panel is loaded and ready to receive commands. This ensures your
    commands don't get lost.
*   **Sending Commands:** Provides the mechanism (`send_message`, used internally
    by modules like Grid, Console) to send instructions (like "set color", "print text")
    to the Sidekick UI.
*   **Receiving Events:** Runs a background thread (`_listen_for_messages`) to listen
    for messages coming *from* the Sidekick UI (like button clicks or text input)
    and routes them to the correct handler function in your script (e.g., the
    function you provided to `grid.on_click`).
*   **Error Handling:** Raises specific `SidekickConnectionError` exceptions if it
    cannot connect, if the UI doesn't respond, or if the connection is lost later.
*   **Lifecycle Management:** Handles clean shutdown procedures, ensuring resources
    are released when your script finishes or when `sidekick.shutdown()` is called.

Note:
    You typically interact with this module indirectly through functions like
    `sidekick.run_forever()` or `sidekick.shutdown()`, or simply by using the
    visual module classes (`Grid`, `Console`, etc.). However, understanding its
    role helps explain the library's behavior, especially regarding connection
    and event handling. The library does **not** automatically attempt to reconnect
    if the connection is lost after being established.
"""

import websocket # The library used for WebSocket communication (websocket-client)
import json
import threading
import atexit # Used to automatically call shutdown() when the script exits normally
import time
import uuid
from enum import Enum, auto
from typing import Optional, Dict, Any, Callable, Set

# --- Import logger and Version ---
from . import logger
from ._version import __version__

# --- Custom Exceptions ---
# Define specific error types for connection problems, making it easier
# for users to catch and potentially handle different failure scenarios.

class SidekickConnectionError(Exception):
    """Base error for all Sidekick connection-related problems.

    Catch this exception type if you want to handle any issue related to
    establishing or maintaining the connection to the Sidekick panel.

    Example:
        >>> try:
        ...     console = sidekick.Console() # Connection happens here
        ...     console.print("Connected!")
        ... except sidekick.SidekickConnectionError as e:
        ...     print(f"Could not connect to Sidekick: {e}")
    """
    pass

class SidekickConnectionRefusedError(SidekickConnectionError):
    """Raised when the library fails to connect to the Sidekick server initially.

    This usually means the Sidekick WebSocket server wasn't running or couldn't
    be reached at the configured URL (`ws://localhost:5163` by default).

    Common Causes:

    1. The Sidekick panel isn't open and active in VS Code.
    2. The Sidekick VS Code extension isn't running correctly or has encountered an error.
    3. The WebSocket server couldn't start (e.g., the port is already in use by another
       application). Check VS Code's "Sidekick Server" output channel for details.
    4. A firewall is blocking the connection between your script and VS Code.
    5. The URL was changed via `sidekick.set_url()` to an incorrect address.

    Attributes:
        url (str): The WebSocket URL that the connection attempt was made to.
        original_exception (Exception): The lower-level error that caused the failure
            (e.g., `ConnectionRefusedError` from the OS, `TimeoutError` from the
            `websocket` library).
    """
    def __init__(self, url: str, original_exception: Exception):
        self.url = url
        self.original_exception = original_exception
        # User-friendly error message suggesting common fixes.
        super().__init__(
            f"Failed to connect to Sidekick server at {url}. "
            f"Reason: {original_exception}. "
            f"Is the Sidekick panel open in VS Code? "
            f"Check the URL, potential port conflicts (default 5163), and firewall settings."
        )

class SidekickTimeoutError(SidekickConnectionError):
    """Raised when connection to the server succeeds, but the Sidekick UI panel doesn't respond.

    After successfully connecting to the WebSocket server (run by the VS Code extension),
    the library waits a short time (a few seconds) for the Sidekick UI panel itself
    (the web content inside the panel) to finish loading and send back a signal
    confirming it's ready to receive commands. If this signal doesn't arrive
    within the timeout period, this error is raised.

    Common Causes:

    1. The Sidekick panel is open in VS Code, but it hasn't finished loading its
       HTML/JavaScript content yet (e.g., due to slow system performance or
       network issues if loading remote resources, though usually local).
    2. There's an error within the Sidekick UI panel's JavaScript code preventing
       it from initializing correctly. Check the Webview Developer Tools in VS Code
       (Command Palette -> "Developer: Open Webview Developer Tools") for errors.

    Attributes:
        timeout (float): The number of seconds the library waited for the UI response.
    """
    def __init__(self, timeout: float):
        self.timeout = timeout
        # User-friendly message explaining the timeout.
        super().__init__(
            f"Connected to the Sidekick server, but timed out after {timeout:.1f} seconds "
            f"waiting for the Sidekick UI panel itself to signal it's ready. "
            f"Is the panel visible and fully loaded in VS Code? Check Webview Developer Tools for errors."
        )

class SidekickDisconnectedError(SidekickConnectionError):
    """Raised when the connection is lost *after* it was successfully established.

    This indicates that communication was working previously, but the connection
    broke unexpectedly. This can happen if you try to send a command or if the
    background listener thread detects the disconnection.

    Common Causes:

    1. The Sidekick panel was closed in VS Code while your script was still running.
    2. The Sidekick VS Code extension crashed, was disabled, or VS Code was closed.
    3. A network interruption occurred between the Python script and VS Code (less
       common for local connections but possible).
    4. An internal error occurred while trying to send or receive a message over
       the established connection.

    **Important:** The library will **not** automatically try to reconnect if this
    error occurs. Any further attempts to use Sidekick modules (like `grid.set_color()`)
    will also fail until the script is potentially restarted and a new connection
    is established.

    Attributes:
        reason (str): A short description of why the disconnection occurred or was detected.
    """
    def __init__(self, reason: str = "Connection lost"):
        self.reason = reason
        # User-friendly message explaining the disconnection.
        super().__init__(
            f"Sidekick connection lost: {reason}. "
            f"The connection was active but is now broken. "
            f"The library will not automatically reconnect."
        )

# --- Connection Status Enum ---
class ConnectionStatus(Enum):
    """Represents the different states of the WebSocket connection internally."""
    DISCONNECTED = auto()               # Not connected. Initial state, or after closing/error.
    CONNECTING = auto()                 # Actively trying to establish the WebSocket link.
    CONNECTED_WAITING_SIDEKICK = auto() # WebSocket link established, waiting for UI panel 'ready' signal.
    CONNECTED_READY = auto()            # Fully connected and confirmed UI panel is ready. Safe to send messages.

# --- Configuration and State (Internal Variables) ---
# These variables manage the connection details and current state.
# They are considered internal implementation details.

# Default WebSocket URL. Can be changed via sidekick.set_url().
_ws_url: str = "ws://localhost:5163"
# Holds the active websocket.WebSocket object once connected.
_ws_connection: Optional[websocket.WebSocket] = None
# A reentrant lock to protect access to shared state variables (status, connection object, handlers, etc.)
# from race conditions between the main thread and the listener thread. RLock allows the same thread
# to acquire the lock multiple times.
_connection_lock = threading.RLock()
# The background thread object responsible for listening for incoming messages.
_listener_thread: Optional[threading.Thread] = None
# Internal flag to track if the listener thread has been started for the current connection cycle.
_listener_started: bool = False
# Maps module instance IDs (e.g., "grid-1") to their specific message handler function
# (usually the _internal_message_handler method of the module instance).
_message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}

# A unique ID generated for this specific Python script ("Hero") instance run.
_peer_id: Optional[str] = None
# Tracks the current status using the ConnectionStatus enum. Crucial for state management.
_connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
# Stores the peer IDs of Sidekick UI instances that have announced they are online via system/announce.
_sidekick_peers_online: Set[str] = set()
# Configuration flags set via sidekick.set_config.
_clear_on_connect: bool = True   # Should the UI be cleared when connection becomes ready?
_clear_on_disconnect: bool = False # Should we *try* to clear the UI on clean shutdown?
# An optional global handler (for debugging/advanced use) that receives *all* messages.
_global_message_handler: Optional[Callable[[Dict[str, Any]], None]] = None

# --- Threading Events for Synchronization ---
# These events are used to coordinate actions between the main script thread,
# the background listener thread, and shutdown procedures.
_stop_event = threading.Event()      # Signals the listener thread that it should stop running cleanly.
_ready_event = threading.Event()     # Set by the listener when the full connection (including UI ready) is established.
                                     # activate_connection() waits on this.
_shutdown_event = threading.Event()  # Set by shutdown() or Ctrl+C to signal run_forever() to exit its wait loop.

# --- Constants ---
# Timeouts and intervals used for connection and communication reliability.
_INITIAL_CONNECT_TIMEOUT = 5.0 # Max seconds to wait for websocket.create_connection() to succeed.
_SIDEKICK_WAIT_TIMEOUT = 2.0   # Max seconds activate_connection() waits for the _ready_event after server connect.
_LISTENER_RECV_TIMEOUT = 1.0   # How long ws.recv() waits in the listener loop before timing out.
                               # Allows the loop to check _stop_event periodically without blocking indefinitely.
# WebSocket Ping settings (using websocket-client's built-in ping):
_PING_INTERVAL = 20            # Send a WebSocket PING frame every 20 seconds if no other messages are sent.
_PING_TIMEOUT = 10             # Wait a maximum of 10 seconds for a PONG reply after sending a PING.
                               # Helps detect unresponsive/dead connections sooner than TCP timeouts.

# --- Private Helper Functions (Internal Use Only) ---

def _generate_peer_id() -> str:
    """Generates or returns the unique ID for this Python script instance ('Hero'). Internal use."""
    global _peer_id
    # Generate only once per script execution.
    if _peer_id is None:
        # Create a unique ID using UUIDv4 for randomness.
        _peer_id = f"hero-{uuid.uuid4().hex}"
        logger.info(f"Generated Hero Peer ID: {_peer_id}")
    return _peer_id

def _send_raw(ws: websocket.WebSocket, message_dict: Dict[str, Any]):
    """Safely serializes a dictionary to JSON and sends it over the WebSocket. Internal use.

    Handles JSON encoding and raises SidekickDisconnectedError if the send fails.

    Args:
        ws: The active WebSocket connection object.
        message_dict: The Python dictionary payload to send.

    Raises:
        SidekickDisconnectedError: If sending fails due to WebSocket-level issues
            (e.g., connection closed, broken pipe, OS errors during send).
        Exception: For other unexpected errors like JSON serialization problems.
    """
    try:
        # Convert the dictionary to a JSON string (UTF-8 encoded by default).
        message_json = json.dumps(message_dict)
        logger.debug(f"Sending raw: {message_json}")
        # Send the JSON string via the WebSocket connection.
        ws.send(message_json)
    except (websocket.WebSocketException, BrokenPipeError, OSError) as e:
        # These errors typically indicate the connection is no longer viable.
        logger.error(f"WebSocket send error: {e}. Connection likely lost.")
        # Raise our specific error to signal disconnection to the caller (send_message).
        raise SidekickDisconnectedError(f"Send failed: {e}")
    except Exception as e:
        # Catch other potential errors (e.g., json.dumps failure if data is not serializable).
        logger.exception(f"Unexpected error sending message: {e}")
        # Treat unexpected send errors as a disconnection as well.
        raise SidekickDisconnectedError(f"Unexpected send error: {e}")

def _send_system_announce(status: str):
    """Sends a 'system/announce' message to the server. Internal use.

    Used to inform the server and other peers (like the UI) about this script's
    online/offline status, role ('hero'), and version, following the protocol spec.

    Args:
        status (str): Either "online" or "offline".
    """
    # Acquire lock for safe access to shared connection object.
    with _connection_lock:
        ws = _ws_connection # Get the current WebSocket object reference.
        peer_id = _generate_peer_id() # Ensure we have our unique ID.

        # Only proceed if we have a seemingly valid, connected WebSocket.
        if ws and ws.connected and peer_id:
            # Construct the payload according to the protocol specification.
            announce_payload = {
                "peerId": peer_id,          # Our unique identifier.
                "role": "hero",             # Identify as the Python script.
                "status": status,           # 'online' or 'offline'.
                "version": __version__,     # Report the library version.
                "timestamp": int(time.time() * 1000) # Current Unix time in milliseconds.
            }
            # Construct the full message structure.
            message = {
                "id": 0, # Reserved, usually 0.
                "module": "system",
                "type": "announce",
                "payload": announce_payload
            }
            try:
                # Use the safe sending helper.
                _send_raw(ws, message)
                logger.info(f"Sent system announce: {status}")
            except SidekickDisconnectedError as e:
                # It's possible sending announce fails (e.g., during shutdown if connection
                # drops simultaneously). Log a warning but don't crash the process.
                logger.warning(f"Could not send system announce '{status}' (connection likely closing): {e}")
            except Exception as e:
                 logger.warning(f"Unexpected error sending system announce '{status}': {e}")
        elif status == "offline":
             # If we're trying to send 'offline' but are already disconnected, that's expected.
             logger.debug("Cannot send offline announce, connection already closed or closing.")
        else:
             # If trying to send 'online' but not connected, that's an issue.
             logger.warning(f"Cannot send system announce '{status}', WebSocket is not connected.")

def _listen_for_messages():
    """The main function executed by the background listener thread. Internal use.

    Continuously waits for incoming messages from the WebSocket server, parses
    the JSON, and dispatches them to the appropriate handlers (_global_message_handler
    or specific module instance handlers registered in _message_handlers).

    It also specifically handles `system/announce` messages from the Sidekick UI
    to track its readiness and update the `_connection_status` and `_ready_event`.

    This function runs until `_stop_event` is set or an unrecoverable connection
    error occurs. If an unexpected error happens, it initiates the `close_connection`
    process.
    """
    global _connection_status, _message_handlers, _sidekick_peers_online, _listener_started, _global_message_handler
    logger.info("Listener thread started.")
    ws = None # Holds the reference to the WebSocket connection for this loop iteration.
    disconnect_reason = "Listener thread terminated normally" # Default exit reason.

    # Loop indefinitely until the stop signal is received.
    while not _stop_event.is_set():
        # --- Check Connection State Safely (Under Lock) ---
        with _connection_lock:
            # If the connection status was changed externally (e.g., by shutdown()), exit the loop.
            if _connection_status == ConnectionStatus.DISCONNECTED:
                disconnect_reason = "Status became DISCONNECTED"
                break
            # Ensure we still have a valid WebSocket object and it thinks it's connected.
            if _ws_connection and _ws_connection.connected:
                ws = _ws_connection # Use the current connection object.
            else:
                # If the connection object is gone or disconnected, exit the loop.
                disconnect_reason = "WebSocket connection lost or object is None"
                # Only log a warning if this wasn't a planned stop.
                if not _stop_event.is_set():
                    logger.warning("Listener: WebSocket connection lost or unavailable.")
                break

        # Check ws again outside the lock (mostly redundant, but safe).
        if not ws:
            disconnect_reason = "WebSocket object is None (checked outside lock)"
            if not _stop_event.is_set():
                logger.warning("Listener: WebSocket object is None, stopping loop.")
            break

        # --- Receive Message ---
        try:
            # Wait for an incoming message, with a timeout.
            # The timeout (_LISTENER_RECV_TIMEOUT) is crucial: it prevents recv()
            # from blocking forever, allowing the loop to periodically check _stop_event.
            ws.settimeout(_LISTENER_RECV_TIMEOUT)
            message_str = ws.recv()

            # Check if stop was signaled *while* we were blocked waiting for recv().
            if _stop_event.is_set():
                disconnect_reason = "Stop event set during receive wait"
                break

            # An empty message usually signifies the server closed the connection gracefully.
            if not message_str:
                disconnect_reason = "Server closed connection (received empty message)"
                if not _stop_event.is_set():
                    logger.info("Listener: Server closed the WebSocket connection.")
                break

            logger.debug(f"Listener: Received raw message: {message_str}")
            # Parse the incoming JSON string into a Python dictionary.
            message_data = json.loads(message_str)

            # --- Process Message Safely (Under Lock) ---
            # Re-acquire the lock to safely access/modify shared state (status, handlers)
            # while processing the received message.
            with _connection_lock:
                # Final check: if status changed or stop signaled while parsing, exit.
                if _stop_event.is_set() or _connection_status == ConnectionStatus.DISCONNECTED:
                    break

                # --- 1. Call Global Handler (if registered) ---
                # Used for debugging/advanced scenarios.
                if _global_message_handler:
                     try:
                         # Pass the raw parsed message dictionary.
                         _global_message_handler(message_data)
                     except Exception as e:
                         # Log errors in the global handler but don't crash the listener.
                         logger.exception(f"Listener: Error in global message handler: {e}")

                # --- 2. Message Dispatch Logic ---
                module = message_data.get('module')
                msg_type = message_data.get('type')
                payload = message_data.get('payload') # Note: Payload keys should be camelCase per protocol.

                # --- Handle System Announce (Sidekick UI Ready?) ---
                if module == 'system' and msg_type == 'announce' and payload:
                    peer_id = payload.get('peerId')
                    role = payload.get('role')
                    status = payload.get('status')

                    # Only process announcements from 'sidekick' peers (the UI).
                    if peer_id and role == 'sidekick':
                        if status == 'online':
                            # A Sidekick UI panel just connected or announced readiness.
                            # Check if this is the *first* Sidekick UI we've seen.
                            was_empty = not _sidekick_peers_online
                            # Add it to our set of known online UIs.
                            _sidekick_peers_online.add(peer_id)
                            logger.info(f"Sidekick peer online: {peer_id}")

                            # CRITICAL: If this is the first UI and we were waiting...
                            if was_empty and _connection_status == ConnectionStatus.CONNECTED_WAITING_SIDEKICK:
                                logger.info(f"First Sidekick UI '{peer_id}' announced online. Connection is now READY.")
                                # Transition the state to fully ready.
                                _connection_status = ConnectionStatus.CONNECTED_READY
                                # If configured, send a 'clearAll' command now that the UI is ready.
                                if _clear_on_connect:
                                    logger.info("clear_on_connect is True, sending global/clearAll.")
                                    try:
                                        # Can call clear_all directly now, connection assumed ready.
                                        clear_all()
                                    except SidekickConnectionError as e_clr:
                                        # Log if the clear fails, but don't stop the listener.
                                        logger.error(f"Failed to send clearAll on connect: {e_clr}")
                                # IMPORTANT: Signal the main thread (waiting in activate_connection)
                                # by setting the _ready_event. This unblocks the script.
                                _ready_event.set()

                        elif status == 'offline':
                            # A Sidekick UI panel disconnected or went offline.
                            if peer_id in _sidekick_peers_online:
                                _sidekick_peers_online.discard(peer_id)
                                logger.info(f"Sidekick peer offline: {peer_id}")
                                # Note: The connection status remains CONNECTED_READY even if all UIs leave.
                                # A disconnect error will only occur if the underlying WebSocket connection
                                # breaks or if a subsequent send/receive operation fails.

                # --- Handle Module Event/Error (Dispatch to Specific Instance) ---
                elif msg_type in ['event', 'error']:
                    # These messages originate *from* a specific module instance in the UI.
                    # The 'src' field in the message identifies which instance.
                    instance_id = message_data.get('src')
                    # Check if we have a handler registered for this specific instance ID.
                    if instance_id and instance_id in _message_handlers:
                        handler = _message_handlers[instance_id]
                        try:
                             logger.debug(f"Listener: Invoking handler for instance '{instance_id}' (type: {msg_type}).")
                             # Call the instance's registered handler (e.g., Grid._internal_message_handler).
                             handler(message_data)
                        except Exception as e:
                             # Catch errors within the user's callback or the internal handler logic.
                             # Log the error but continue the listener loop.
                             logger.exception(f"Listener: Error executing handler for instance '{instance_id}': {e}")
                    elif instance_id:
                        # Received a message for an instance we don't know (e.g., removed).
                         logger.debug(f"Listener: No handler registered for instance '{instance_id}' for message type '{msg_type}'. Ignoring.")
                    else:
                        # Malformed message missing the 'src' identifier.
                         logger.warning(f"Listener: Received '{msg_type}' message without required 'src' field: {message_data}")
                else:
                    # Received a message type the listener doesn't handle directly (e.g., 'spawn' from UI).
                    logger.debug(f"Listener: Received unhandled message type: module='{module}', type='{msg_type}'")

        except websocket.WebSocketTimeoutException:
            # This is expected due to ws.settimeout(). It's not an error.
            # Simply continue the loop to check _stop_event and wait again.
            continue
        except websocket.WebSocketConnectionClosedException:
            # The server actively closed the connection while we were listening.
            disconnect_reason = "WebSocketConnectionClosedException"
            if not _stop_event.is_set(): # Log only if it wasn't expected.
                logger.info("Listener: WebSocket connection closed by server.")
            break # Exit the loop.
        except (json.JSONDecodeError, TypeError) as e:
            # Received data that wasn't valid JSON or had unexpected types.
            logger.error(f"Listener: Failed to parse incoming JSON or invalid data type: {message_str}. Error: {e}")
            continue # Try to recover and continue listening.
        except OSError as e:
            # Catch lower-level OS errors (e.g., network issues, bad file descriptor).
            # Ignore "Bad file descriptor" (errno 9) if we are stopping, as it's expected.
            if not (_stop_event.is_set() and e.errno == 9):
                disconnect_reason = f"OS error ({e})"
                if not _stop_event.is_set():
                     logger.warning(f"Listener: OS error occurred ({e}), likely connection lost.")
                break # Exit the loop on significant OS errors.
        except Exception as e:
            # Catch any other unexpected error during the loop.
            disconnect_reason = f"Unexpected error: {e}"
            if not _stop_event.is_set(): # Log only if unexpected.
                 logger.exception(f"Listener: Unexpected error occurred: {e}")
            break # Exit the loop.

    # --- Listener Loop Exit ---
    logger.info(f"Listener thread finished. Reason: {disconnect_reason}")
    # Ensure the flag reflects that the listener is no longer running.
    with _connection_lock:
        _listener_started = False # Allow listener to potentially restart on next connection attempt.

    # If the loop exited *unexpectedly* (i.e., not because _stop_event was set)...
    if not _stop_event.is_set():
        logger.warning("Listener thread terminated unexpectedly. Initiating disconnect cleanup.")
        # Trigger the full cleanup process. This will likely lead to a
        # SidekickDisconnectedError being raised for the main thread eventually.
        # Crucially, run close_connection in a *separate non-daemon thread*
        # This avoids potential deadlocks if close_connection needs to acquire locks held
        # elsewhere, and ensures cleanup completes even if the main script exits.
        # Marking as an exception scenario.
        cleanup_thread = threading.Thread(
            target=close_connection,
            args=(False, True, disconnect_reason), # log_info=False, is_exception=True
            daemon=False # Make sure cleanup finishes
        )
        cleanup_thread.start()


def _ensure_connection():
    """Establishes the initial WebSocket connection and starts the listener. Internal use.

    Called only by `activate_connection` when the status is `DISCONNECTED`.
    It handles the `websocket.create_connection` call and starts the `_listen_for_messages`
    thread if the connection is successful.

    Note:
        This function assumes the caller (`activate_connection`) holds the `_connection_lock`.

    Raises:
        SidekickConnectionRefusedError: If the initial WebSocket `create_connection` fails.
    """
    global _ws_connection, _listener_thread, _listener_started, _connection_status

    # Safety check: Should only be called when DISCONNECTED.
    if _connection_status != ConnectionStatus.DISCONNECTED:
        # This indicates a potential logic error elsewhere.
        logger.warning(f"_ensure_connection called unexpectedly while status is {_connection_status.name}")
        return

    logger.info(f"Attempting to connect to Sidekick server at {_ws_url}...")
    # --- Prepare for New Connection Attempt ---
    _connection_status = ConnectionStatus.CONNECTING # Update state
    _sidekick_peers_online.clear() # Reset known UI peers for this new connection.
    # Reset threading events to their initial (cleared) state.
    _stop_event.clear()
    _ready_event.clear()
    _shutdown_event.clear()

    # --- Attempt WebSocket Connection ---
    try:
        # This is the blocking call that tries to establish the WebSocket connection.
        # It uses the configured URL and initial connection timeout.
        # It also configures automatic background ping/pong handling.
        _ws_connection = websocket.create_connection(
            _ws_url,
            timeout=_INITIAL_CONNECT_TIMEOUT,
            ping_interval=_PING_INTERVAL, # Send pings if connection idle
            ping_timeout=_PING_TIMEOUT    # Timeout if pong not received
        )
        logger.info("Successfully connected to Sidekick server (WebSocket established).")

        # --- Connection Succeeded ---
        # Immediately send our 'online' announcement to identify ourselves.
        _send_system_announce("online")
        # Update status: WebSocket connected, but waiting for UI panel confirmation.
        _connection_status = ConnectionStatus.CONNECTED_WAITING_SIDEKICK

        # Start the listener thread if it's not already running (e.g., from a previous failed attempt).
        # Check both the flag and the thread's alive status for robustness.
        if not _listener_started and not (_listener_thread and _listener_thread.is_alive()):
            logger.info("Starting WebSocket listener thread.")
            # Create the thread. Set daemon=True so it doesn't prevent script exit
            # if the main thread finishes without calling shutdown().
            _listener_thread = threading.Thread(target=_listen_for_messages, daemon=True)
            _listener_thread.start()
            _listener_started = True # Mark that the listener is running for this cycle.
        elif _listener_started:
             # This state should ideally not be reached if status management is correct.
             logger.warning("_ensure_connection: Listener thread already marked as started (unexpected).")

    # --- Handle Connection Errors ---
    except (websocket.WebSocketException, ConnectionRefusedError, OSError, TimeoutError) as e:
        # Catch specific errors indicating failure to connect.
        logger.error(f"Failed to connect to Sidekick server at {_ws_url}: {e}")
        # Clean up state: Mark as disconnected, clear connection object.
        _ws_connection = None
        _connection_status = ConnectionStatus.DISCONNECTED
        # Signal the listener thread (if it somehow started before failing) to stop.
        _stop_event.set()
        _listener_started = False
        # Raise the specific error for activate_connection to catch and report to the user.
        raise SidekickConnectionRefusedError(_ws_url, e)
    except Exception as e:
        # Catch any other unexpected errors during the connection process.
        logger.exception(f"Unexpected error during Sidekick connection setup: {e}")
        # Perform similar cleanup.
        _ws_connection = None
        _connection_status = ConnectionStatus.DISCONNECTED
        _stop_event.set()
        _listener_started = False
        # Wrap the unexpected error in our specific connection error type.
        raise SidekickConnectionRefusedError(_ws_url, e)


# --- Public API Functions ---

def set_url(url: str):
    """Sets the WebSocket URL where the Sidekick server is expected to be listening.

    You **must** call this function *before* creating any Sidekick modules
    (like `sidekick.Grid()`) or calling any other Sidekick function that might
    trigger a connection attempt (like `sidekick.clear_all()`). The library uses
    the URL set here when it makes its first connection attempt.

    Calling this after a connection attempt has already started (even if it failed)
    will log a warning and have no effect, unless you explicitly call
    `sidekick.shutdown()` first to completely reset the connection state.

    Args:
        url (str): The full WebSocket URL, which must start with "ws://" or "wss://".
            The default value is "ws://localhost:5163".

    Raises:
        ValueError: If the provided URL does not start with "ws://" or "wss://".

    Example:
        >>> import sidekick
        >>> # If the Sidekick server is running on a different machine or port
        >>> try:
        ...     sidekick.set_url("ws://192.168.1.100:5163")
        ... except ValueError as e:
        ...     print(e)
        >>>
        >>> # Now it's safe to create Sidekick modules
        >>> console = sidekick.Console()
    """
    global _ws_url
    # Acquire lock for safe state checking and modification.
    with _connection_lock:
        # Only allow changing the URL if we are fully disconnected.
        if _connection_status != ConnectionStatus.DISCONNECTED:
            logger.warning("Cannot change Sidekick URL after a connection attempt "
                           "has been made. Call sidekick.shutdown() first if you need to change the URL.")
            return
        # Basic validation for the URL format.
        if not isinstance(url, str) or not url.startswith(("ws://", "wss://")):
             msg = (f"Invalid WebSocket URL provided: '{url}'. It must be a string "
                    f"starting with 'ws://' or 'wss://'. Keeping previous URL ('{_ws_url}').")
             logger.error(msg)
             raise ValueError(msg) # Raise error for invalid URL format
        _ws_url = url
        logger.info(f"Sidekick WebSocket URL set to: {_ws_url}")

def set_config(clear_on_connect: bool = True, clear_on_disconnect: bool = False):
    """Configures automatic clearing behavior for the Sidekick UI panel.

    Like `set_url`, you **must** call this function *before* the first connection
    attempt is made (i.e., before creating any Sidekick modules). Calling it later
    will have no effect unless `shutdown()` is called first.

    Args:
        clear_on_connect (bool): If True (the default), the library will automatically
            send a command to clear *all* existing elements from the Sidekick UI panel
            as soon as the connection becomes fully ready (i.e., when the UI panel
            signals it's online and ready). This provides a clean slate for your
            script. Set this to False if you want your script to potentially add to
            or interact with UI elements left over from a previous script run (less common).
        clear_on_disconnect (bool): If True (default is False), the library will
            *attempt* (on a best-effort basis) to send a command to clear the Sidekick
            UI when your script disconnects cleanly. This happens when `shutdown()`
            is called explicitly or when the script exits normally (due to the `atexit`
            handler). This cleanup might *not* happen if the connection is lost
            abruptly or due to an error.
    """
    global _clear_on_connect, _clear_on_disconnect
    # Acquire lock for safe state checking and modification.
    with _connection_lock:
        # Only allow changing config if we are fully disconnected.
        if _connection_status != ConnectionStatus.DISCONNECTED:
            logger.warning("Cannot change Sidekick config after a connection attempt "
                           "has been made. Call sidekick.shutdown() first if needed.")
            return
        _clear_on_connect = bool(clear_on_connect) # Ensure boolean type
        _clear_on_disconnect = bool(clear_on_disconnect) # Ensure boolean type
        logger.info(f"Sidekick config set: clear_on_connect={_clear_on_connect}, "
                    f"clear_on_disconnect={_clear_on_disconnect}")

def activate_connection():
    """Ensures the connection to Sidekick is established and fully ready. (Internal use).

    This function is the gateway for all communication. It's called implicitly by
    `send_message` (which is used by all module methods like `grid.set_color`) and
    at the start of `run_forever`. You generally don't need to call it directly.

    It performs the crucial steps of:

    1. Checking the current connection status.
    2. If disconnected, initiating the connection attempt (`_ensure_connection`).
    3. **Blocking** execution if the WebSocket is connected but the UI panel hasn't
       signaled readiness yet (waiting on `_ready_event`).
    4. Returning only when the status is `CONNECTED_READY`.

    Raises:
        SidekickConnectionRefusedError: If the initial WebSocket connection attempt fails.
        SidekickTimeoutError: If the connection to the server succeeds, but the Sidekick
                              UI panel doesn't signal readiness within the timeout period.
        SidekickDisconnectedError: If the connection state becomes invalid or disconnected
                                   during the activation process.
    """
    # Acquire lock to safely check status and potentially initiate connection.
    with _connection_lock:
        current_status = _connection_status
        logger.debug(f"activate_connection called. Current status: {current_status.name}")

        # If already fully ready, nothing more to do.
        if current_status == ConnectionStatus.CONNECTED_READY:
            logger.debug("Connection already READY.")
            return

        # If disconnected, need to start the connection process.
        if current_status == ConnectionStatus.DISCONNECTED:
            try:
                # _ensure_connection attempts connection, starts listener, sends announce.
                # Raises SidekickConnectionRefusedError on immediate failure.
                _ensure_connection()
                # If successful, status becomes CONNECTED_WAITING_SIDEKICK.
                # We now need to wait for the UI's signal outside the lock.
                logger.debug("Initial connection attempt successful, proceed to wait for UI readiness.")
            except SidekickConnectionError as e:
                # If _ensure_connection failed, log and re-raise the specific error.
                logger.error(f"Initial connection failed during activate_connection: {e}")
                raise e

        # If status is CONNECTING or CONNECTED_WAITING_SIDEKICK, fall through to the wait phase.

    # --- Wait for READY state (Outside the main lock) ---
    # Release the lock *before* waiting on the event. This is essential to allow
    # the listener thread (which needs the lock to update the status and set the event)
    # to make progress.
    logger.debug(f"Waiting up to {_SIDEKICK_WAIT_TIMEOUT}s for Sidekick UI readiness signal (_ready_event)...")

    # Block the current (main) thread until the listener thread calls _ready_event.set()
    # OR the timeout (_SIDEKICK_WAIT_TIMEOUT) expires.
    ready_signal_received = _ready_event.wait(timeout=_SIDEKICK_WAIT_TIMEOUT)

    # --- Check Status *After* Waiting (Re-acquire lock) ---
    # Re-acquire the lock to safely check the final connection status after the wait.
    with _connection_lock:
        # Case 1: Success! The event was set, and the status confirms we are ready.
        if ready_signal_received and _connection_status == ConnectionStatus.CONNECTED_READY:
            logger.debug("Sidekick connection is now confirmed READY.")
            return # Connection activated successfully.

        # Case 2: Timeout! The event was *not* set within the time limit.
        elif not ready_signal_received:
            timeout_reason = f"Timed out waiting for Sidekick UI readiness signal after {_SIDEKICK_WAIT_TIMEOUT}s"
            logger.error(timeout_reason)
            # Since the UI never responded, clean up the partially established connection.
            # Trigger cleanup in a separate thread to avoid potential deadlocks.
            threading.Thread(target=close_connection, args=(False, True, timeout_reason), daemon=True).start()
            # Raise the specific timeout error for the user.
            raise SidekickTimeoutError(_SIDEKICK_WAIT_TIMEOUT)

        # Case 3: Inconsistency. The event *was* set, but the status is *not* READY.
        # This is rare but could happen if the connection dropped immediately after the
        # listener set the event but before this thread could re-acquire the lock and check.
        else:
            # ready_signal_received is True, but _connection_status is not CONNECTED_READY
            disconnect_reason = f"Connection state inconsistent after wait: Ready event was set, but status is now {_connection_status.name}"
            logger.error(f"Connection activation failed: {disconnect_reason}")
            # If not already disconnected, trigger cleanup.
            if _connection_status != ConnectionStatus.DISCONNECTED:
                 threading.Thread(target=close_connection, args=(False, True, disconnect_reason), daemon=True).start()
            # Raise a generic disconnected error.
            raise SidekickDisconnectedError(disconnect_reason)

def send_message(message_dict: Dict[str, Any]):
    """Sends a command message (as a dictionary) to the Sidekick UI. (Internal use).

    This is the core function used by all Sidekick modules (`Grid`, `Console`, etc.)
    to send their specific commands (like 'setColor', 'append', 'add') to the UI panel.
    You typically don't call this directly.

    It ensures the connection is ready via `activate_connection()` before attempting
    to serialize the message to JSON and send it over the WebSocket.

    Args:
        message_dict (Dict[str, Any]): A Python dictionary representing the message.
            It must conform to the Sidekick communication protocol structure, including
            `module`, `type`, `target`/`src`, and a `payload` whose keys should generally
            be `camelCase`.

    Raises:
        SidekickConnectionRefusedError: If the connection isn't ready and fails during activation.
        SidekickTimeoutError: If waiting for the UI times out during activation.
        SidekickDisconnectedError: If the connection is lost *before* or *during* the send attempt.
        TypeError: If `message_dict` is not a dictionary.
        Exception: For other unexpected errors (e.g., JSON serialization failure).
    """
    if not isinstance(message_dict, dict):
        raise TypeError("message_dict must be a dictionary")

    # 1. Ensure connection is fully ready. This blocks or raises errors if necessary.
    activate_connection() # Raises SidekickConnectionError subclasses on failure.

    # 2. Acquire lock for safe access to the WebSocket object for sending.
    with _connection_lock:
        ws = _ws_connection
        # Double-check status *after* acquiring the lock, as a safety measure against
        # rare race conditions where the connection might drop between activate_connection returning
        # and this lock being acquired.
        if _connection_status != ConnectionStatus.CONNECTED_READY or not ws or not ws.connected:
            disconnect_reason = f"Connection became invalid ({_connection_status.name}) immediately before sending"
            logger.error(disconnect_reason)
            # If not already disconnected, trigger cleanup.
            if _connection_status != ConnectionStatus.DISCONNECTED:
                 threading.Thread(target=close_connection, args=(False, True, disconnect_reason), daemon=True).start()
            raise SidekickDisconnectedError(disconnect_reason)

        # 3. Attempt the send using the internal raw helper.
        try:
            # _send_raw handles JSON conversion and raises SidekickDisconnectedError on WebSocket errors.
            _send_raw(ws, message_dict)
        except SidekickDisconnectedError as e:
             # If _send_raw indicated a disconnection, log it and initiate cleanup.
             logger.error(f"Send message failed due to disconnection: {e.reason}")
             # Trigger cleanup if not already disconnected.
             if _connection_status != ConnectionStatus.DISCONNECTED:
                  # Use a thread for cleanup to avoid potential deadlocks.
                  threading.Thread(target=close_connection, args=(False, True, f"Send failed: {e.reason}"), daemon=True).start()
             # Re-raise the error to inform the caller (e.g., the Grid method).
             raise e
        except Exception as e:
             # Catch other unexpected errors during send (e.g., JSON serialization).
             disconnect_reason = f"Unexpected error during send: {e}"
             logger.exception(disconnect_reason)
             # Assume connection is compromised, trigger cleanup.
             if _connection_status != ConnectionStatus.DISCONNECTED:
                  threading.Thread(target=close_connection, args=(False, True, disconnect_reason), daemon=True).start()
             # Wrap the error.
             raise SidekickDisconnectedError(disconnect_reason)

def clear_all():
    """Sends a command to remove *all* visual elements from the Sidekick panel.

    This effectively resets the Sidekick UI, removing any Grids, Consoles, Viz panels,
    Canvases, or Controls that were created by *this* running Python script instance.

    Raises:
        SidekickConnectionError (or subclass): If the connection is not ready or
                                              if sending the command fails.
    """
    logger.info("Requesting global clearAll of Sidekick UI elements.")
    # Construct the specific 'global/clearAll' message according to the protocol.
    message = {
        "id": 0,
        "module": "global", # Target the global scope, not a specific module instance.
        "type": "clearAll",
        "payload": None     # No additional data needed for this command.
    }
    # Use the public send_message function, which handles readiness checks and errors.
    send_message(message)

def close_connection(log_info=True, is_exception=False, reason=""):
    """Closes the WebSocket connection and cleans up resources. (Internal use).

    This is the core cleanup function. It stops the listener thread, closes the
    WebSocket socket, sends final 'offline'/'clearAll' messages (best-effort),
    and resets internal state variables.

    It's called automatically by `shutdown()` and the `atexit` handler for clean
    exits, and also triggered internally by the listener thread or `send_message`
    if an unrecoverable error (`is_exception=True`) is detected.

    **Users should typically call `sidekick.shutdown()` instead of this directly.**

    Args:
        log_info (bool): If True, logs status messages during the closure process.
        is_exception (bool): If True, indicates this closure was triggered by an
                             error condition (e.g., listener crash, send failure).
                             This may influence whether a final `SidekickDisconnectedError`
                             is raised after cleanup, depending on whether a clean
                             `shutdown()` was also requested concurrently.
        reason (str): Optional description of why the connection is closing, used
                      for logging and potentially included in error messages.
    """
    global _ws_connection, _listener_thread, _listener_started, _connection_status, _message_handlers, _sidekick_peers_online

    disconnect_exception_to_raise: Optional[SidekickDisconnectedError] = None # Prepare potential exception

    # Acquire lock for safe modification of shared state during cleanup.
    with _connection_lock:
        # Prevent redundant close operations if already disconnected.
        if _connection_status == ConnectionStatus.DISCONNECTED:
            if log_info: logger.debug("Connection already closed or closing.")
            return

        if log_info: logger.info(f"Closing Sidekick WebSocket connection... (Exception: {is_exception}, Reason: '{reason}')")
        initial_status = _connection_status # Remember status before changing it for logic below.

        # --- 1. Signal Listener Thread to Stop ---
        _stop_event.set() # Tell the _listen_for_messages loop to exit.
        _ready_event.clear() # Connection is no longer ready.

        # --- 2. Update Internal State Immediately ---
        _connection_status = ConnectionStatus.DISCONNECTED
        _sidekick_peers_online.clear() # Stop tracking UI peers.

        # --- 3. Best-Effort Cleanup Messages ---
        # Attempt to send final messages ('clearAll' if configured, 'offline' announce)
        # ONLY if this is a clean shutdown (not an error) AND we were actually connected.
        # These are best-effort and might fail if the connection is already broken.
        ws_temp = _ws_connection # Get reference under lock
        if not is_exception and ws_temp and ws_temp.connected and initial_status != ConnectionStatus.CONNECTING:
             # Send clearAll if configured for disconnect.
             if _clear_on_disconnect:
                  logger.debug("Attempting to send global/clearAll on disconnect (best-effort).")
                  clear_all_msg = {"id": 0, "module": "global", "type": "clearAll", "payload": None}
                  try: _send_raw(ws_temp, clear_all_msg)
                  # Ignore failures here, as connection might be closing.
                  except Exception: logger.warning("Failed to send clearAll during disconnect (ignored).")

             # Send offline announce.
             logger.debug("Attempting to send offline system announce (best-effort).")
             try: _send_system_announce("offline")
             # Ignore failures here as well.
             except Exception: logger.warning("Failed to send offline announce during disconnect (ignored).")

        # --- 4. Close the WebSocket Socket ---
        if ws_temp:
            try:
                # Give the close operation a short timeout.
                ws_temp.settimeout(0.5)
                ws_temp.close()
            except Exception as e:
                 # Log errors during close but continue cleanup.
                 logger.warning(f"Error occurred during WebSocket close(): {e}")
        # Clear the global reference to the connection object.
        _ws_connection = None

        # --- 5. Prepare Exception (if closure was due to an error) ---
        # If this close was triggered by an error (is_exception=True), create the
        # exception object now. We will raise it *after* releasing the lock and
        # joining the listener thread, but only if a clean shutdown wasn't also requested.
        if is_exception:
            disconnect_exception_to_raise = SidekickDisconnectedError(reason or "Connection closed due to an error")

        # --- 6. Clear Listener Thread References ---
        # Store reference to potentially running thread for joining outside the lock.
        listener_thread_temp = _listener_thread
        _listener_thread = None # Clear global reference.
        _listener_started = False # Allow listener to restart if connect is called again.

    # --- 7. Join Listener Thread (Outside the main lock) ---
    # Wait for the listener thread to finish its execution cleanly.
    # This is done outside the lock to avoid deadlocks if the listener needs the lock to exit.
    if listener_thread_temp and listener_thread_temp.is_alive():
        if log_info: logger.debug("Waiting for listener thread to stop...")
        try:
            # Wait a bit longer than the listener's receive timeout.
            join_timeout = _LISTENER_RECV_TIMEOUT + 0.5
            listener_thread_temp.join(timeout=join_timeout)
            # Check if it actually stopped.
            if listener_thread_temp.is_alive():
                 logger.warning(f"Listener thread did not stop gracefully after join timeout ({join_timeout}s).")
            elif log_info:
                 logger.debug("Listener thread stopped.")
        except Exception as e:
             logger.warning(f"Error joining listener thread: {e}")
    elif log_info:
        logger.debug("Listener thread was not running or already finished.")

    # --- 8. Clear Instance Message Handlers ---
    # Do this after the listener is stopped, outside the main lock.
    if _message_handlers:
        logger.debug(f"Clearing {len(_message_handlers)} instance message handlers.")
        _message_handlers.clear()

    if log_info: logger.info("Sidekick WebSocket connection closed and resources cleaned up.")

    # --- 9. Raise Exception (if applicable) ---
    # If this cleanup was triggered by an error (`is_exception` was True),
    # check if a clean shutdown was *also* requested concurrently (e.g., via Ctrl+C
    # setting _shutdown_event). If NOT requested, raise the disconnect error now
    # to signal the problem to the main thread.
    if disconnect_exception_to_raise:
        if not _shutdown_event.is_set():
            logger.error(f"Raising disconnect exception after cleanup: {disconnect_exception_to_raise}")
            raise disconnect_exception_to_raise
        else:
            # If a clean shutdown was requested, don't raise the error, just log it.
            logger.warning(f"Suppressed disconnect exception because clean shutdown was also requested: {disconnect_exception_to_raise}")


def run_forever():
    """Keeps your Python script running indefinitely to handle Sidekick UI events.

    If your script needs to react to interactions in the Sidekick panel (like
    button clicks, grid cell clicks, console input, etc.), it needs to stay
    alive to listen for those events. Calling `sidekick.run_forever()` at the
    end of your script achieves this.

    It essentially pauses the main thread of your script in a loop, while the
    background listener thread (managed internally) continues to receive messages
    from Sidekick and trigger your registered callback functions (e.g., the
    functions passed to `grid.on_click()` or `console.on_input_text()`).

    How to Stop `run_forever()`:

    1. Press `Ctrl+C` in the terminal where your script is running.
    2. Call `sidekick.shutdown()` from within one of your callback functions
       (e.g., have a "Quit" button call `sidekick.shutdown` in its `on_click` handler).
    3. If the connection to Sidekick breaks unexpectedly, `run_forever()` will
       also stop (typically after a `SidekickDisconnectedError` is raised).

    Raises:
        SidekickConnectionError (or subclass): If the initial connection to Sidekick
            cannot be established when `run_forever` starts. The script won't enter
            the waiting loop if it can't connect first.

    Example:
        >>> import sidekick
        >>> console = sidekick.Console(show_input=True)
        >>> def handle_input(text):
        ...     if text.lower() == 'quit':
        ...         console.print("Exiting...")
        ...         sidekick.shutdown() # Stop run_forever from callback
        ...     else:
        ...         console.print(f"You typed: {text}")
        >>> console.input_text_handler(handle_input)
        >>> console.print("Enter text or type 'quit' to exit.")
        >>>
        >>> # Keep script running to listen for input
        >>> sidekick.run_forever()
        >>> print("Script has finished.") # This line runs after run_forever exits
    """
    # 1. Ensure connection is established and ready before entering the loop.
    #    This will block or raise connection errors if it fails.
    try:
        activate_connection()
    except SidekickConnectionError as e:
        logger.error(f"Cannot start run_forever: Initial connection failed: {e}")
        # Re-raise the error; don't proceed if we can't connect.
        raise e

    logger.info("Sidekick entering run_forever mode. Press Ctrl+C or call sidekick.shutdown() to exit.")
    _shutdown_event.clear() # Ensure the shutdown signal is clear before starting the loop.

    try:
        # --- Main Waiting Loop ---
        # Loop indefinitely as long as the shutdown event hasn't been signaled.
        while not _shutdown_event.is_set():
            # Wait for the shutdown signal. The `wait()` method blocks until the
            # event is set or the timeout expires. Using a timeout allows the loop
            # to periodically check other conditions (like connection status) if needed.
            # A timeout of 1 second is reasonable.
            shutdown_signaled = _shutdown_event.wait(timeout=1.0)
            if shutdown_signaled:
                logger.debug("run_forever: Shutdown event detected.")
                break # Exit the loop cleanly.

            # Optional check: If the connection status changed (e.g., listener detected
            # a disconnect), exit the loop early. The actual SidekickDisconnectedError
            # is typically raised by the listener thread initiating close_connection,
            # but this check helps exit the wait loop sooner.
            with _connection_lock:
                 if _connection_status != ConnectionStatus.CONNECTED_READY:
                      logger.warning(f"run_forever: Connection status changed unexpectedly to {_connection_status.name}. Exiting loop.")
                      break

    except KeyboardInterrupt:
        # User pressed Ctrl+C in the terminal.
        logger.info("KeyboardInterrupt received, initiating Sidekick shutdown.")
        # The `finally` block will handle calling shutdown().
        pass # Absorb the KeyboardInterrupt here
    except Exception as e:
        # Catch any other unexpected error during the wait loop itself.
        logger.exception(f"Unexpected error during run_forever wait loop: {e}")
        # Let the `finally` block handle shutdown.
        pass
    finally:
        # --- Cleanup ---
        # This block executes regardless of how the loop was exited
        # (shutdown signal, Ctrl+C, error, or connection status change).
        # Check if a clean shutdown was *already* signaled (e.g., by a callback).
        if not _shutdown_event.is_set():
            # If not, it means we exited for another reason (Ctrl+C, error, disconnect).
            # Initiate a clean shutdown now.
            logger.debug("run_forever: Loop exited without explicit shutdown signal, initiating shutdown now.")
            shutdown() # Call the standard shutdown procedure.
        else:
             # If shutdown was already signaled, just log that we're exiting cleanly.
             logger.debug("run_forever: Exiting cleanly due to prior shutdown signal.")

    logger.info("Sidekick run_forever mode finished.")


def shutdown():
    """Initiates a clean shutdown of the Sidekick connection and resources.

    Call this function to gracefully disconnect from the Sidekick panel. It performs
    the following actions:
    - Signals `run_forever()` (if it's currently running) to stop its waiting loop.
    - Attempts to send a final 'offline' announcement to the Sidekick server.
    - Attempts to send a 'clearAll' command to the UI (if configured via `set_config`).
    - Closes the underlying WebSocket connection.
    - Stops the background listener thread.
    - Clears internal state and message handlers.

    It's safe to call this function multiple times; subsequent calls after the
    first successful shutdown will have no effect.

    This function is also registered automatically via `atexit` to be called when
    your Python script exits normally, ensuring cleanup happens if possible.

    You might call this manually from an event handler (e.g., a "Quit" button's
    `on_click` callback) to programmatically stop `run_forever()` and end the script.

    Example:
        >>> def on_quit_button_click(control_id):
        ...    print("Quit button clicked. Shutting down.")
        ...    sidekick.shutdown()
        >>> controls.add_button("quit", "Quit")
        >>> controls.on_click(on_quit_button_click)
        >>> sidekick.run_forever()
    """
    # Acquire lock briefly to check status and set the shutdown event.
    with _connection_lock:
        # Check if already disconnected or if shutdown is already in progress.
        if _connection_status == ConnectionStatus.DISCONNECTED and _shutdown_event.is_set():
            logger.debug("Shutdown already completed or in progress.")
            return

        logger.info("Sidekick shutdown requested.")
        # Signal that a clean shutdown is intended.
        # This tells run_forever() to exit and prevents close_connection from
        # raising a disconnect error if called concurrently due to an error.
        _shutdown_event.set()

    # Initiate the closing process by calling the internal cleanup function.
    # Do this *outside* the main lock to avoid potential deadlocks.
    # Mark this as NOT being triggered by an exception (is_exception=False).
    close_connection(log_info=True, is_exception=False, reason="Shutdown requested by user/script")


# --- Registration/Utility Functions (Mostly Internal/Advanced) ---

def register_message_handler(instance_id: str, handler: Callable[[Dict[str, Any]], None]):
    """Registers a handler function for messages targeted at a specific module instance. (Internal).

    This is called automatically by `BaseModule.__init__` when a Sidekick module
    (like `Grid`, `Console`) is created. It maps the module's unique `instance_id`
    to its `_internal_message_handler` method.

    The listener thread uses this mapping to dispatch incoming 'event' and 'error'
    messages from the UI to the correct Python object.

    Args:
        instance_id (str): The unique ID of the module instance (e.g., "grid-1").
        handler (Callable): The function (usually an instance method) to call.
                            It must accept one argument: the message dictionary.

    Raises:
        TypeError: If the provided handler is not a callable function.
    """
    if not callable(handler):
        raise TypeError(f"Handler for instance '{instance_id}' must be callable.")
    # Acquire lock for safe modification of the shared handler dictionary.
    with _connection_lock:
        # Only register if the connection isn't already fully shut down.
        # Allows registration even before the connection becomes CONNECTED_READY.
        if _connection_status != ConnectionStatus.DISCONNECTED or not _stop_event.is_set():
            logger.debug(f"Registering internal message handler for instance '{instance_id}'.")
            _message_handlers[instance_id] = handler
        else:
            # Avoid registration if shutdown is complete or in progress.
            logger.warning(f"Connection closed or closing, handler for '{instance_id}' not registered.")


def unregister_message_handler(instance_id: str):
    """Removes the message handler for a specific module instance. (Internal).

    Called automatically by `BaseModule.remove()` when a module is explicitly
    removed, and also during the final `close_connection` cleanup to clear all handlers.

    Args:
        instance_id (str): The ID of the module instance whose handler should be removed.
    """
    # Acquire lock for safe modification of the shared handler dictionary.
    with _connection_lock:
        # Use dict.pop() which safely removes the key if it exists, and does nothing otherwise.
        # Store the popped value (the handler function) temporarily.
        removed_handler = _message_handlers.pop(instance_id, None)
        if removed_handler:
            logger.debug(f"Unregistered internal message handler for instance '{instance_id}'.")
        # else:
            # No need to log if not found, as this is expected during cleanup or if remove() is called twice.
            # logger.debug(f"No internal message handler found for instance '{instance_id}' to unregister.")


def register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]]):
    """Registers a single function to receive *all* incoming messages from Sidekick.

    **Advanced Usage / Debugging:** This function is primarily intended for debugging
    the communication protocol or building very custom, low-level integrations.
    The function you provide (`handler`) will be called by the listener thread for
    *every* message received from the Sidekick server, *before* the message is
    dispatched to any specific module instance handlers.

    Warning:
        The structure and content of messages received here are subject to the
        internal Sidekick communication protocol and may change between versions.
        Relying on this for core application logic is generally discouraged.

    Args:
        handler (Optional[Callable[[Dict[str, Any]], None]]): The function to call
            with each raw message dictionary received from the WebSocket. It should
            accept one argument (the message dict). Pass `None` to remove any
            currently registered global handler.

    Raises:
        TypeError: If the provided handler is not a callable function and not `None`.
    """
    global _global_message_handler
    # Acquire lock for safe modification of the global handler reference.
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
            # Raise error if the provided handler is invalid.
            raise TypeError("Global message handler must be a callable function or None.")

# --- Automatic Cleanup on Exit ---
# Register the public shutdown() function to be called automatically when the
# Python interpreter exits normally (e.g., script finishes, sys.exit()).
# This ensures a best-effort attempt to close the WebSocket, stop the listener,
# and send cleanup messages like 'offline' or 'clearAll'.
atexit.register(shutdown)
