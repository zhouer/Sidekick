# Sidekick/libs/python/src/sidekick/base_module.py
from . import connection
from .utils import generate_unique_id
from typing import Optional, Dict, Any, Callable

class BaseModule:
    """Base class for Sidekick modules."""
    def __init__(self, module_type: str, instance_id: Optional[str] = None,
                 payload: Optional[Dict[str, Any]] = None,
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initializes the base module, registers message handler, and sends spawn command.
        """
        connection.activate_connection() # Ensure connection is allowed and potentially initiated
        self.module_type = module_type
        self.target_id = instance_id or generate_unique_id(module_type)
        self._on_message_callback = on_message # Store callback reference

        # Register handler *before* sending spawn, in case Sidekick replies immediately
        if self._on_message_callback:
            connection.register_message_handler(self.target_id, self._on_message_callback)

        self._send_command("spawn", payload or {})

    def _send_command(self, method: str, payload: Optional[Dict[str, Any]] = None):
        """Helper method to send a command to the Sidekick frontend."""
        message: Dict[str, Any] = {
            "id": 0, # id field from spec, might be used later
            "module": self.module_type,
            "method": method,
            "target": self.target_id,
        }
        if payload is not None:
            message["payload"] = payload
        connection.send_message(message)

    def remove(self):
        """Removes the module instance from the Sidekick UI and unregisters message handler."""
        connection.logger.info(f"Removing module '{self.target_id}' and unregistering handler.")
        # Unregister handler first
        connection.unregister_message_handler(self.target_id)
        # Then send remove command
        self._send_command("remove")

    def __del__(self):
        """Attempts to remove the instance and handler upon garbage collection."""
        # Note: This is not guaranteed to run reliably. Explicit .remove() is safer.
        try:
            # Check if connection/handler might still be valid (basic check)
            if hasattr(connection, 'unregister_message_handler'):
                 connection.unregister_message_handler(self.target_id)
        except Exception:
            # Suppress errors during garbage collection
            pass