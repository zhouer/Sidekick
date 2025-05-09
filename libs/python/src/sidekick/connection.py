"""Manages the communication channel between your Python script and the Sidekick UI.

This component acts as the central communication hub for the Sidekick library. It
handles the technical details of establishing and maintaining a real-time
connection with the Sidekick panel running in Visual Studio Code.

Key Responsibilities:

*   **Connecting:** Automatically attempts to connect to the Sidekick server
    (usually running within the VS Code extension) the first time your script
    tries to interact with a Sidekick component (e.g., when you create `sidekick.Grid()`).
    Upon successful connection and UI readiness, the Sidekick UI panel is **automatically cleared**.
*   **Blocking Connection:** It **pauses** (blocks) your script during the initial
    connection phase until it confirms that both the server is reached and the
    Sidekick UI panel is loaded and ready to receive commands. This ensures your
    commands don't get lost.
*   **Sending Commands:** Provides the mechanism (`send_message`, used internally
    by components like Grid, Console) to send instructions (like "set color", "print text")
    to the Sidekick UI.
*   **Receiving Events:** Handles incoming messages from the Sidekick UI (like button
    clicks or text input) and routes them to the correct handler function in your
    script (e.g., the function you provided to `grid.on_click`).
*   **Error Handling:** Raises specific `SidekickConnectionError` exceptions if it
    cannot connect, if the UI doesn't respond, or if the connection is lost later.
*   **Lifecycle Management:** Handles clean shutdown procedures, ensuring resources
    are released when your script finishes or when `sidekick.shutdown()` is called.
    The Sidekick UI panel is **not cleared** on shutdown, preserving its state for
    potential inspection or re-connection by a subsequent script run.

Note:
    You typically interact with this component indirectly through functions like
    `sidekick.run_forever()` or `sidekick.shutdown()`, or simply by using the
    visual component classes (`Grid`, `Console`, etc.). However, understanding its
    role helps explain the library's behavior, especially regarding connection, UI clearing,
    and event handling. The library does **not** automatically attempt to reconnect
    if the connection is lost after being established.
"""

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

# --- Import Custom Exceptions ---
from .errors import (
    SidekickConnectionError,
    SidekickConnectionRefusedError,
    SidekickTimeoutError,
    SidekickDisconnectedError
)

# --- Import Channel Abstraction ---
from .channel import CommunicationChannel, create_communication_channel

# --- Import Event classes for docstring examples ---
# (Not strictly needed for connection.py logic, but good for example accuracy)
from .events import ConsoleSubmitEvent, ButtonClickEvent

# --- Connection Status Enum ---
class ConnectionStatus(Enum):
    """Represents the different states of the communication channel internally."""
    DISCONNECTED = auto()               # Not connected. Initial state, or after closing/error.
    CONNECTING = auto()                 # Actively trying to establish the connection.
    CONNECTED_WAITING_SIDEKICK = auto() # Connection established, waiting for UI panel 'ready' signal.
    CONNECTED_READY = auto()            # Fully connected and confirmed UI panel is ready. Safe to send messages.

# --- Configuration and State (Internal Variables) ---
# These variables manage the connection details and current state.
# They are considered internal implementation details.

# Default WebSocket URL. Can be changed via sidekick.set_url().
_ws_url: str = "ws://localhost:5163"
# Holds the active communication channel once connected.
_channel: Optional[CommunicationChannel] = None
# A reentrant lock to protect access to shared state variables (status, channel object, handlers, etc.)
# from race conditions between threads. RLock allows the same thread to acquire the lock multiple times.
_connection_lock = threading.RLock()
# Maps component instance IDs (e.g., "my-custom-grid-id" or "grid-1") to their specific
# message handler function (usually the _internal_message_handler method of the component instance).
_message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}

# A unique ID generated for this specific Python script ("Hero") instance run.
_peer_id: Optional[str] = None
# Tracks the current status using the ConnectionStatus enum. Crucial for state management.
_connection_status: ConnectionStatus = ConnectionStatus.DISCONNECTED
# Stores the peer IDs of Sidekick UI instances that have announced they are online via system/announce.
_sidekick_peers_online: Set[str] = set()
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

def _send_raw(channel: CommunicationChannel, message_dict: Dict[str, Any]):
    """Safely sends a dictionary message through the communication channel. Internal use.

    Args:
        channel: The active communication channel.
        message_dict: The Python dictionary payload to send.

    Raises:
        SidekickDisconnectedError: If sending fails due to connection issues.
        Exception: For other unexpected errors.
    """
    try:
        logger.debug(f"Sending raw: {message_dict}")
        # Send the message via the communication channel.
        channel.send_message(message_dict)
    except SidekickDisconnectedError as e:
        # These errors indicate the connection is no longer viable.
        logger.error(f"Channel send error: {e}. Connection likely lost.")
        # Re-raise the error to signal disconnection to the caller.
        raise
    except Exception as e:
        # Catch other potential errors.
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
    # Acquire lock for safe access to shared channel object.
    with _connection_lock:
        channel = _channel # Get the current channel object reference.
        peer_id = _generate_peer_id() # Ensure we have our unique ID.

        # Only proceed if we have a seemingly valid, connected channel.
        if channel and channel.is_connected() and peer_id:
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
                "component": "system",
                "type": "announce",
                "payload": announce_payload
            }
            try:
                # Use the safe sending helper.
                _send_raw(channel, message)
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
             logger.warning(f"Cannot send system announce '{status}', channel is not connected.")

def _handle_incoming_message(message_data: Dict[str, Any]):
    """Handles incoming messages from the communication channel.

    This function processes messages received from the channel and dispatches them
    to the appropriate handlers. It specifically handles system/announce messages
    to track UI readiness.

    Args:
        message_data (Dict[str, Any]): The parsed message data.
    """
    global _connection_status, _message_handlers, _sidekick_peers_online, _global_message_handler

    try:
        # --- 1. Call Global Handler (if registered) ---
        # Used for debugging/advanced scenarios.
        if _global_message_handler:
            try:
                # Pass the raw parsed message dictionary.
                _global_message_handler(message_data)
            except Exception as e:
                # Log errors in the global handler but don't crash the handler.
                logger.exception(f"Error in global message handler: {e}")

        # --- 2. Message Dispatch Logic ---
        component = message_data.get('component')
        msg_type = message_data.get('type')
        payload = message_data.get('payload') # Note: Payload keys should be camelCase per protocol.

        # --- Handle System Announce (Sidekick UI Ready?) ---
        if component == 'system' and msg_type == 'announce' and payload:
            peer_id = payload.get('peerId')
            role = payload.get('role')
            status = payload.get('status')

            # Only process announcements from 'sidekick' peers (the UI).
            if peer_id and role == 'sidekick':
                if status == 'online':
                    # A Sidekick UI panel just connected or announced readiness.
                    # Check if this is the *first* Sidekick UI we've seen.
                    with _connection_lock:
                        was_empty = not _sidekick_peers_online
                        # Add it to our set of known online UIs.
                        _sidekick_peers_online.add(peer_id)

                    logger.info(f"Sidekick peer online: {peer_id}")

                    # CRITICAL: If this is the first UI and we were waiting...
                    if was_empty and _connection_status == ConnectionStatus.CONNECTED_WAITING_SIDEKICK:
                        logger.info(f"First Sidekick UI '{peer_id}' announced online. Connection is now READY.")
                        # Transition the state to fully ready.
                        _connection_status = ConnectionStatus.CONNECTED_READY
                        # Always send a 'clearAll' command now that the UI is ready.
                        logger.info("Connection ready, sending global/clearAll to clear UI.")
                        try:
                            # Can call clear_all directly now, connection assumed ready.
                            clear_all()
                        except SidekickConnectionError as e_clr:
                            # Log if the clear fails, but don't stop the handler.
                            logger.error(f"Failed to send clearAll on connect: {e_clr}")
                        # IMPORTANT: Signal the main thread (waiting in activate_connection)
                        # by setting the _ready_event. This unblocks the script.
                        _ready_event.set()

                elif status == 'offline':
                    # A Sidekick UI panel disconnected or went offline.
                    with _connection_lock:
                        if peer_id in _sidekick_peers_online:
                            _sidekick_peers_online.discard(peer_id)
                            logger.info(f"Sidekick peer offline: {peer_id}")
                            # Note: The connection status remains CONNECTED_READY even if all UIs leave.
                            # A disconnect error will only occur if the underlying connection
                            # breaks or if a subsequent send/receive operation fails.

        # --- Handle Component Event/Error (Dispatch to Specific Instance) ---
        elif msg_type in ['event', 'error']:
            # These messages originate *from* a specific component instance in the UI.
            # The 'src' field in the message identifies which instance (its instance_id).
            instance_id_from_ui = message_data.get('src')
            # Check if we have a handler registered for this specific instance ID.
            with _connection_lock:
                handler = _message_handlers.get(instance_id_from_ui) if instance_id_from_ui else None

            if handler:
                try:
                    logger.debug(f"Invoking handler for instance '{instance_id_from_ui}' (type: {msg_type}).")
                    # Call the instance's registered handler (e.g., Grid._internal_message_handler).
                    # This handler is responsible for creating a structured Event object if needed.
                    handler(message_data)
                except Exception as e:
                    # Catch errors within the user's callback or the internal handler logic.
                    # Log the error but continue processing.
                    logger.exception(f"Error executing handler for instance '{instance_id_from_ui}': {e}")
            elif instance_id_from_ui:
                # Received a message for an instance we don't know (e.g., removed).
                logger.debug(f"No handler registered for instance '{instance_id_from_ui}' for message type '{msg_type}'. Ignoring.")
            else:
                # Malformed message missing the 'src' identifier.
                logger.warning(f"Received '{msg_type}' message without required 'src' field: {message_data}")
        else:
            # Received a message type the handler doesn't handle directly (e.g., 'spawn' from UI).
            logger.debug(f"Received unhandled message type: component='{component}', type='{msg_type}'")

    except Exception as e:
        # Catch any other unexpected error during message handling.
        logger.exception(f"Unexpected error handling message: {e}")
        # We don't want to crash the handler, so just log the error and continue.


def _ensure_connection():
    """Establishes the initial connection using the appropriate channel. Internal use.

    Called only by `activate_connection` when the status is `DISCONNECTED`.
    It creates the appropriate communication channel based on the environment
    and connects to the Sidekick server.

    Note:
        This function assumes the caller (`activate_connection`) holds the `_connection_lock`.

    Raises:
        SidekickConnectionRefusedError: If the initial connection fails.
    """
    global _channel, _connection_status

    # Safety check: Should only be called when DISCONNECTED.
    if _connection_status != ConnectionStatus.DISCONNECTED:
        # This indicates a potential logic error elsewhere.
        logger.warning(f"_ensure_connection called unexpectedly while status is {_connection_status.name}")
        return

    logger.info(f"Attempting to connect to Sidekick server...")
    # --- Prepare for New Connection Attempt ---
    _connection_status = ConnectionStatus.CONNECTING # Update state
    _sidekick_peers_online.clear() # Reset known UI peers for this new connection.
    # Reset threading events to their initial (cleared) state.
    _stop_event.clear()
    _ready_event.clear()
    _shutdown_event.clear()

    # --- Create and Connect Channel ---
    try:
        # Create the appropriate communication channel based on the environment
        _channel = create_communication_channel(_ws_url)

        # Register a message handler for the channel
        _channel.register_message_handler(_handle_incoming_message)

        # Connect the channel
        _channel.connect()
        logger.info("Successfully connected to Sidekick server.")

        # --- Connection Succeeded ---
        # Immediately send our 'online' announcement to identify ourselves.
        _send_system_announce("online")
        # Update status: Connected, but waiting for UI panel confirmation.
        _connection_status = ConnectionStatus.CONNECTED_WAITING_SIDEKICK

    # --- Handle Connection Errors ---
    except SidekickConnectionRefusedError as e:
        # Catch specific errors indicating failure to connect.
        logger.error(f"Failed to connect to Sidekick server: {e}")
        # Clean up state: Mark as disconnected, clear channel object.
        _channel = None
        _connection_status = ConnectionStatus.DISCONNECTED
        # Raise the error for activate_connection to catch and report to the user.
        raise
    except Exception as e:
        # Catch any other unexpected errors during the connection process.
        logger.exception(f"Unexpected error during Sidekick connection setup: {e}")
        # Perform similar cleanup.
        _channel = None
        _connection_status = ConnectionStatus.DISCONNECTED
        # Wrap the unexpected error in our specific connection error type.
        raise SidekickConnectionRefusedError(_ws_url, e)


# --- Public API Functions ---

def set_url(url: str):
    """Sets the URL where the Sidekick server is expected to be listening.

    You **must** call this function *before* creating any Sidekick components
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
        >>> # Now it's safe to create Sidekick components
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

def activate_connection():
    """Ensures the connection to Sidekick is established and fully ready. (Internal use).

    This function is the gateway for all communication. It's called implicitly by
    `send_message` (which is used by all component methods like `grid.set_color`) and
    at the start of `run_forever`. You generally don't need to call it directly.

    It performs the crucial steps of:

    1. Checking the current connection status.
    2. If disconnected, initiating the connection attempt (`_ensure_connection`).
    3. **Blocking** execution if the connection is established but the UI panel hasn't
       signaled readiness yet (waiting on `_ready_event`).
    4. Returning only when the status is `CONNECTED_READY`.

    Raises:
        SidekickConnectionRefusedError: If the initial connection attempt fails.
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

    This is the core function used by all Sidekick components (`Grid`, `Console`, etc.)
    to send their specific commands (like 'setColor', 'append', 'add') to the UI panel.
    You typically don't call this directly.

    It ensures the connection is ready via `activate_connection()` before attempting
    to send the message through the communication channel.

    Args:
        message_dict (Dict[str, Any]): A Python dictionary representing the message.
            It must conform to the Sidekick communication protocol structure, including
            `component`, `type`, `target`/`src`, and a `payload` whose keys should generally
            be `camelCase`. The `target` field should contain the component's `instance_id`.

    Raises:
        SidekickConnectionRefusedError: If the connection isn't ready and fails during activation.
        SidekickTimeoutError: If waiting for the UI times out during activation.
        SidekickDisconnectedError: If the connection is lost *before* or *during* the send attempt.
        TypeError: If `message_dict` is not a dictionary.
        Exception: For other unexpected errors.
    """
    if not isinstance(message_dict, dict):
        raise TypeError("message_dict must be a dictionary")

    # 1. Ensure connection is fully ready. This blocks or raises errors if necessary.
    activate_connection() # Raises SidekickConnectionError subclasses on failure.

    # 2. Acquire lock for safe access to the channel object for sending.
    with _connection_lock:
        channel = _channel
        # Double-check status *after* acquiring the lock, as a safety measure against
        # rare race conditions where the connection might drop between activate_connection returning
        # and this lock being acquired.
        if _connection_status != ConnectionStatus.CONNECTED_READY or not channel or not channel.is_connected():
            disconnect_reason = f"Connection became invalid ({_connection_status.name}) immediately before sending"
            logger.error(disconnect_reason)
            # If not already disconnected, trigger cleanup.
            if _connection_status != ConnectionStatus.DISCONNECTED:
                 threading.Thread(target=close_connection, args=(False, True, disconnect_reason), daemon=True).start()
            raise SidekickDisconnectedError(disconnect_reason)

        # 3. Attempt the send using the internal raw helper.
        try:
            # _send_raw handles sending and raises SidekickDisconnectedError on channel errors.
            _send_raw(channel, message_dict)
        except SidekickDisconnectedError as e:
             # If _send_raw indicated a disconnection, log it and initiate cleanup.
             logger.error(f"Send message failed due to disconnection: {e}")
             # Trigger cleanup if not already disconnected.
             if _connection_status != ConnectionStatus.DISCONNECTED:
                  # Use a thread for cleanup to avoid potential deadlocks.
                  threading.Thread(target=close_connection, args=(False, True, f"Send failed: {e}"), daemon=True).start()
             # Re-raise the error to inform the caller (e.g., the Grid method).
             raise
        except Exception as e:
             # Catch other unexpected errors during send.
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
        "component": "global", # Target the global scope, not a specific component instance.
        "type": "clearAll"
    }
    # Use the public send_message function, which handles readiness checks and errors.
    send_message(message)

def close_connection(log_info=True, is_exception=False, reason=""):
    """Closes the communication channel and cleans up resources. (Internal use).

    This is the core cleanup function. It closes the communication channel,
    sends a final 'offline' message (best-effort), and resets internal
    state variables. The UI is not cleared on close/shutdown.

    It's called automatically by `shutdown()` and the `atexit` handler for clean
    exits, and also triggered internally by error handlers in `send_message`
    if an unrecoverable error (`is_exception=True`) is detected.

    **Users should typically call `sidekick.shutdown()` instead of this directly.**

    Args:
        log_info (bool): If True, logs status messages during the closure process.
        is_exception (bool): If True, indicates this closure was triggered by an
                             error condition (e.g., channel error, send failure).
                             This may influence whether a final `SidekickDisconnectedError`
                             is raised after cleanup, depending on whether a clean
                             `shutdown()` was also requested concurrently.
        reason (str): Optional description of why the connection is closing, used
                      for logging and potentially included in error messages.
    """
    global _channel, _connection_status, _message_handlers, _sidekick_peers_online

    disconnect_exception_to_raise: Optional[SidekickDisconnectedError] = None # Prepare potential exception

    # Acquire lock for safe modification of shared state during cleanup.
    with _connection_lock:
        # Prevent redundant close operations if already disconnected.
        if _connection_status == ConnectionStatus.DISCONNECTED:
            if log_info: logger.debug("Connection already closed or closing.")
            return

        if log_info: logger.info(f"Closing Sidekick connection... (Exception: {is_exception}, Reason: '{reason}')")
        initial_status = _connection_status # Remember status before changing it for logic below.

        # --- 1. Signal to Stop ---
        _stop_event.set() # Signal any waiting threads to stop.
        _ready_event.clear() # Connection is no longer ready.

        # --- 2. Update Internal State Immediately ---
        _connection_status = ConnectionStatus.DISCONNECTED
        _sidekick_peers_online.clear() # Stop tracking UI peers.

        # --- 3. Best-Effort Cleanup Messages ---
        # Attempt to send final 'offline' announce message if this is a clean shutdown
        # and we were actually connected. This is best-effort. The UI is not cleared.
        channel_temp = _channel # Get reference under lock
        if not is_exception and channel_temp and channel_temp.is_connected() and initial_status != ConnectionStatus.CONNECTING:
             # Send offline announce.
             logger.debug("Attempting to send offline system announce (best-effort).")
             try: _send_system_announce("offline")
             # Ignore failures here as well.
             except Exception: logger.warning("Failed to send offline announce during disconnect (ignored).")

        # --- 4. Close the Channel ---
        if channel_temp:
            try:
                channel_temp.close()
            except Exception as e:
                 # Log errors during close but continue cleanup.
                 logger.warning(f"Error occurred during channel close(): {e}")
        # Clear the global reference to the channel object.
        _channel = None

        # --- 5. Prepare Exception (if closure was due to an error) ---
        # If this close was triggered by an error (is_exception=True), create the
        # exception object now. We will raise it *after* releasing the lock,
        # but only if a clean shutdown wasn't also requested.
        if is_exception:
            disconnect_exception_to_raise = SidekickDisconnectedError(reason or "Connection closed due to an error")

    # --- 6. Clear Instance Message Handlers ---
    # Do this outside the main lock.
    if _message_handlers:
        logger.debug(f"Clearing {len(_message_handlers)} instance message handlers.")
        _message_handlers.clear()

    if log_info: logger.info("Sidekick connection closed and resources cleaned up.")

    # --- 7. Raise Exception (if applicable) ---
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
    functions passed to `grid.on_click()` or `console.on_submit()`).

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
        >>> # Assuming ConsoleSubmitEvent is imported or defined
        >>> # from sidekick.events import ConsoleSubmitEvent
        >>>
        >>> console = sidekick.Console(show_input=True)
        >>> def handle_input(event: sidekick.ConsoleSubmitEvent): # Updated callback signature
        ...     if event.value.lower() == 'quit':
        ...         console.print("Exiting...")
        ...         sidekick.shutdown() # Stop run_forever from callback
        ...     else:
        ...         console.print(f"You typed: {event.value}")
        >>> console.on_submit(handle_input)
        >>> console.print("Enter text or type 'quit' to exit.")
        >>>
        >>> # Keep script running to listen for input
        >>> try:
        ...     sidekick.run_forever()
        ... except sidekick.SidekickConnectionError as e:
        ...     print(f"Connection error: {e}")
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
    - The UI is *not* cleared on shutdown, preserving its state.
    - Closes the underlying communication channel.
    - Clears internal state and message handlers.

    It's safe to call this function multiple times; subsequent calls after the
    first successful shutdown will have no effect.

    This function is also registered automatically via `atexit` to be called when
    your Python script exits normally, ensuring cleanup happens if possible.

    You might call this manually from an event handler (e.g., a "Quit" button's
    `on_click` callback) to programmatically stop `run_forever()` and end the script.

    Example:
        >>> import sidekick
        >>> # Assuming ButtonClickEvent is imported
        >>> # from sidekick.events import ButtonClickEvent
        >>>
        >>> quit_button = sidekick.Button("Quit", instance_id="my-quit-btn")
        >>> def on_quit_button_click(event: sidekick.ButtonClickEvent):
        ...    print(f"Button '{event.instance_id}' clicked. Shutting down.")
        ...    sidekick.shutdown()
        >>> quit_button.on_click(on_quit_button_click)
        >>>
        >>> # sidekick.run_forever() # To keep the script alive for the button click
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
    """Registers a handler function for messages targeted at a specific component instance. (Internal).

    This is called automatically by `Component.__init__` when a Sidekick component
    (like `Grid`, `Console`) is created. It maps the component's unique `instance_id`
    to its `_internal_message_handler` method.

    The message handler uses this mapping to dispatch incoming 'event' and 'error'
    messages from the UI to the correct Python object.

    If an `instance_id` is already registered, this function will raise a `ValueError`.

    Args:
        instance_id (str): The unique ID of the component instance (e.g., "my-grid" or "grid-1").
        handler (Callable): The function (usually an instance method) to call.
                            It must accept one argument: the message dictionary.

    Raises:
        TypeError: If the provided handler is not a callable function.
        ValueError: If the `instance_id` is already registered, indicating a duplicate ID.
    """
    if not callable(handler):
        raise TypeError(f"Handler for instance '{instance_id}' must be callable.")
    # Acquire lock for safe modification of the shared handler dictionary.
    with _connection_lock:
        # Check for duplicate instance_id before registration.
        if instance_id in _message_handlers:
            msg = (f"Cannot register handler: Instance ID '{instance_id}' is already in use. "
                   f"Component instance IDs must be unique within a script run.")
            logger.error(msg)
            raise ValueError(msg) # This will stop component creation if ID is duplicated.

        # Only register if the connection isn't already fully shut down.
        # Allows registration even before the connection becomes CONNECTED_READY.
        if _connection_status != ConnectionStatus.DISCONNECTED or not _stop_event.is_set():
            logger.debug(f"Registering internal message handler for instance '{instance_id}'.")
            _message_handlers[instance_id] = handler
        else:
            # Avoid registration if shutdown is complete or in progress.
            logger.warning(f"Connection closed or closing, handler for '{instance_id}' not registered.")


def unregister_message_handler(instance_id: str):
    """Removes the message handler for a specific component instance. (Internal).

    Called automatically by `Component.remove()` when a component is explicitly
    removed, and also during the final `close_connection` cleanup to clear all handlers.

    Args:
        instance_id (str): The ID of the component instance whose handler should be removed.
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
    dispatched to any specific component instance handlers.

    Warning:
        The structure and content of messages received here are subject to the
        internal Sidekick communication protocol and may change between versions.
        Relying on this for core application logic is generally discouraged.
        The raw message dictionary received here does not automatically get transformed
        into the structured event objects (like `ButtonClickEvent`) that component-specific
        callbacks receive.

    Args:
        handler (Optional[Callable[[Dict[str, Any]], None]]): The function to call
            with each raw message dictionary received from the communication channel.
            It should accept one argument (the message dict). Pass `None` to remove any
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
# and send an 'offline' announcement. The UI is not cleared.
atexit.register(shutdown)