# Sidekick/libs/python/src/sidekick/base_module.py
from . import connection
from .utils import generate_unique_id
from typing import Optional, Dict, Any, Callable

class BaseModule:
    """
    Base class for all Sidekick Python module interfaces (Grid, Console, Viz, etc.).

    Handles common functionality like activating the connection, generating a unique
    instance ID, registering message handlers, and sending basic commands ('spawn', 'remove').
    """
    def __init__(self, module_type: str, instance_id: Optional[str] = None,
                 payload: Optional[Dict[str, Any]] = None,
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initializes the base module.

        Args:
            module_type: The type string of the module (e.g., "grid", "console").
            instance_id: A user-provided unique ID for this instance. If None,
                         an ID will be generated automatically.
            payload: The initial payload to send with the 'spawn' command. Keys
                     should generally be camelCase.
            on_message: An optional callback function to handle 'notify' messages
                        received from the corresponding frontend module instance.
                        The callback receives the full message dictionary.
        """
        connection.activate_connection()
        self.module_type = module_type
        self.target_id = instance_id or generate_unique_id(module_type)
        self._on_message_callback = on_message

        if self._on_message_callback:
            connection.register_message_handler(self.target_id, self._on_message_callback)

        self._send_command("spawn", payload or {})

    def _send_command(self, method: str, payload: Optional[Dict[str, Any]] = None):
        """
        Sends a command message to the Sidekick frontend for this module instance.

        Args:
            method: The command method ("spawn", "update", "remove").
            payload: The data payload for the command. Keys should be camelCase.
                     Can be None if the command requires no payload.
        """
        message: Dict[str, Any] = {
            "id": 0,
            "module": self.module_type,
            "method": method,
            "target": self.target_id,
        }
        if payload is not None:
            message["payload"] = payload
        connection.send_message(message)

    def _send_update(self, payload: Dict[str, Any]):
        """
        Sends an 'update' command with the given payload.

        Args:
            payload: The payload for the update command. Keys should be camelCase.
        """
        self._send_command("update", payload)

    def remove(self):
        """
        Removes the module instance from the Sidekick UI.
        """
        connection.logger.info(f"Removing module '{self.target_id}' and unregistering handler.")
        connection.unregister_message_handler(self.target_id)
        self._send_command("remove")

    def __del__(self):
        """
        Attempts to unregister the message handler upon garbage collection. (Not reliable)
        """
        try:
            if hasattr(connection, 'unregister_message_handler'):
                 connection.unregister_message_handler(self.target_id)
        except Exception:
            pass