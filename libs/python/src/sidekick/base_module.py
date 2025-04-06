# Sidekick/libs/python/src/sidekick/base_module.py
from . import connection
from .utils import generate_unique_id
from typing import Optional, Dict, Any, Callable

class BaseModule:
    """
    Base class for Sidekick Python module interfaces (Grid, Console, Viz, etc.).

    Handles common functionality like activating the connection, managing instance IDs,
    registering an internal message handler for errors, and sending commands.

    Provides the `spawn` parameter to control whether a new instance is created
    in Sidekick or if the Python object should attach to an existing instance.

    Subclasses should override `_internal_message_handler` to handle specific
    'event' messages and call specific callbacks (e.g., `_click_callback`).
    """
    def __init__(
        self,
        module_type: str,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        payload: Optional[Dict[str, Any]] = None,
    ):
        """
        Initializes the base module.

        Args:
            module_type: The type string of the module (e.g., "grid", "console").
            instance_id: A unique ID for this instance.
                         - If `spawn=True`, optional (auto-generated if None).
                         - If `spawn=False`, required.
            spawn: If True (default), attempts to create a new instance in Sidekick
                   by sending a 'spawn' command. If False, assumes the instance
                   already exists in Sidekick and attaches to it without sending 'spawn'.
            payload: The initial payload for the 'spawn' command (only used if spawn=True).
                     Keys should generally be camelCase.
        """
        connection.activate_connection() # Ensure connection attempt is triggered
        self.module_type = module_type
        self._error_callback: Optional[Callable[[str], None]] = None

        if not spawn and instance_id is None:
            raise ValueError(f"instance_id is required when spawn=False for module type '{module_type}'")

        # Determine the target_id based on spawn and provided instance_id
        self.target_id = instance_id or generate_unique_id(module_type)
        connection.logger.debug(f"Initializing BaseModule: type='{module_type}', id='{self.target_id}', spawn={spawn}")

        # Register the internal handler for this instance
        connection.register_message_handler(self.target_id, self._internal_message_handler)

        # Only send spawn command if requested
        if spawn:
            self._send_command("spawn", payload or {})
        # else: Assuming instance exists, just track it locally

    def _internal_message_handler(self, message: Dict[str, Any]):
        """
        Internal handler for messages received for this specific instance.
        Registered with the connection manager. Parses message type and payload.
        Base implementation handles 'error' messages. Subclasses should override
        this to handle 'event' messages and call super() for error handling.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "error":
            error_message = "Unknown error"
            if payload and isinstance(payload.get("message"), str):
                error_message = payload["message"]
            connection.logger.error(f"Module '{self.target_id}' received error from Sidekick: {error_message}")
            if self._error_callback:
                try:
                    self._error_callback(error_message)
                except Exception as e:
                    connection.logger.exception(f"Error in {self.module_type} '{self.target_id}' on_error callback: {e}")
        elif msg_type == "event":
            # Base implementation doesn't handle specific events, subclasses should.
            pass
        else:
            connection.logger.warning(f"Module '{self.target_id}' received unhandled message type '{msg_type}': {message}")

    def on_error(self, callback: Optional[Callable[[str], None]]):
        """
        Registers a function to be called when an error message related to this
        module instance is received from Sidekick.

        Args:
            callback: A function that accepts a single string argument (the error message),
                      or None to unregister.
        """
        if callback is not None and not callable(callback):
            raise TypeError("Error callback must be callable or None")
        connection.logger.info(f"Setting on_error callback for module '{self.target_id}'.")
        self._error_callback = callback

    def _send_command(self, msg_type: str, payload: Optional[Dict[str, Any]] = None):
        """
        Constructs and sends a command message to the Sidekick frontend for this instance.
        Uses connection.send_message which handles buffering.

        Args:
            msg_type: The message type ("spawn", "update", "remove").
            payload: The data payload (keys should be camelCase). None if no payload.
        """
        message: Dict[str, Any] = {
            "id": 0, # Reserved
            "module": self.module_type,
            "type": msg_type,
            "target": self.target_id,
        }
        # Include payload only if it's not None
        if payload is not None:
            message["payload"] = payload

        # Delegate sending (and potential buffering) to the connection module
        connection.send_message(message)

    def _send_update(self, payload: Dict[str, Any]):
        """Sends an 'update' command with the given payload."""
        self._send_command("update", payload)

    def remove(self):
        """
        Sends a 'remove' command to Sidekick for this instance and unregisters
        the local message handler.
        """
        connection.logger.info(f"Requesting removal of module '{self.target_id}'.")
        # Always try to unregister handler first
        connection.unregister_message_handler(self.target_id)
        # Reset local callbacks
        self._error_callback = None
        # Let subclasses reset their specific callbacks if needed
        self._reset_specific_callbacks()
        # Send remove command (might be buffered)
        self._send_command("remove")

    def _reset_specific_callbacks(self):
        """Placeholder for subclasses to reset their specific event callbacks on remove."""
        pass

    def __del__(self):
        """Attempts to unregister the message handler upon garbage collection."""
        try:
            # Check if connection module still exists (might be cleaned up during exit)
            if hasattr(connection, 'unregister_message_handler'):
                 connection.unregister_message_handler(self.target_id)
        except Exception:
            # Suppress errors during cleanup
            pass