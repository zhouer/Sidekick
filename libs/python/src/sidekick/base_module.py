# Sidekick/libs/python/src/sidekick/base_module.py
from . import connection
from .utils import generate_unique_id
from typing import Optional, Dict, Any, Callable

class BaseModule:
    """
    Base class for Sidekick Python module interfaces (Grid, Console, Viz, etc.).

    Handles common functionality like activating the connection, managing instance IDs,
    registering message handlers, and sending commands ('spawn', 'remove', 'update').

    Provides the `spawn` parameter to control whether a new instance is created
    in Sidekick or if the Python object should attach to an existing instance.
    """
    def __init__(
        self,
        module_type: str,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        payload: Optional[Dict[str, Any]] = None,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None
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
            on_message: Optional callback for 'event' or 'error' messages from the frontend module.
                        Receives the full message dictionary.
        """
        connection.activate_connection() # Ensure connection attempt is triggered
        self.module_type = module_type

        if not spawn and instance_id is None:
            raise ValueError(f"instance_id is required when spawn=False for module type '{module_type}'")

        # Determine the target_id based on spawn and provided instance_id
        self.target_id = instance_id or generate_unique_id(module_type)
        connection.logger.debug(f"Initializing BaseModule: type='{module_type}', id='{self.target_id}', spawn={spawn}")

        self._on_message_callback = on_message
        if self._on_message_callback:
            connection.register_message_handler(self.target_id, self._on_message_callback)

        # Only send spawn command if requested
        if spawn:
            self._send_command("spawn", payload or {})
        # else: Assuming instance exists, just track it locally

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
        self._send_command("remove") # Send remove command (might be buffered)

    # __del__ remains the same (best-effort cleanup)
    def __del__(self):
        """Attempts to unregister the message handler upon garbage collection."""
        try:
            # Check if connection module still exists (might be cleaned up during exit)
            if hasattr(connection, 'unregister_message_handler'):
                 connection.unregister_message_handler(self.target_id)
        except Exception:
            # Suppress errors during cleanup
            pass