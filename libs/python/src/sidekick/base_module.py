"""
Base Class for Sidekick Visual Modules.

This module provides the foundational `BaseModule` class, which acts as a
blueprint for all specific visual modules in the Sidekick library (like Grid,
Console, etc.).

You typically won't use `BaseModule` directly in your scripts. Instead, you'll
use the specific module classes (e.g., `sidekick.Grid`). This base class handles
the common tasks needed for any visual module:

- Assigning a unique ID to each module instance.
- Ensuring the connection to the Sidekick panel is established.
- Sending commands (like 'create', 'update', 'remove') to Sidekick.
- Providing a way to remove the visual element (`remove()` method).
- Handling errors reported by Sidekick for a specific module (`on_error` callback).
"""

from . import logger
from . import connection
from .utils import generate_unique_id
from typing import Optional, Dict, Any, Callable

class BaseModule:
    """Base class for all Sidekick module interface classes (like Grid, Console).

    This class handles the basic setup needed for any module that interacts
    with the Sidekick UI. It manages the unique ID for the module instance,
    ensures the connection to Sidekick is active, and provides common methods
    like `remove()` and `on_error()`.

    You typically won't use `BaseModule` directly. Instead, you'll use specific
    module classes like `sidekick.Grid` or `sidekick.Console`.

    Attributes:
        module_type (str): The type name of the module (e.g., "grid", "console").
        target_id (str): The unique identifier for this specific module instance.
    """
    def __init__(
        self,
        module_type: str,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        payload: Optional[Dict[str, Any]] = None,
    ):
        """Initializes the base module properties and connection.

        This constructor is called by the subclasses (like Grid, Console).
        It sets up the unique ID and registers the module instance with the
        connection manager. If `spawn` is True, it sends a command to create
        the corresponding UI element in Sidekick.

        Args:
            module_type (str): The type string of the module (e.g., "grid").
            instance_id (Optional[str]): A specific ID for this instance.
                - If `spawn=True`: Optional. A unique ID will be auto-generated if None.
                - If `spawn=False`: **Required**. Identifies the existing UI element.
            spawn (bool): If True (default), sends a command to Sidekick to create
                a new UI element. If False, assumes the UI element already exists
                and this Python object should connect to it.
            payload (Optional[Dict[str, Any]]): Data needed to create the UI element
                (only used if `spawn=True`). Keys should generally be camelCase.

        Raises:
            ValueError: If `spawn` is False but `instance_id` is not provided.
        """
        connection.activate_connection() # Ensure connection attempt is triggered
        self.module_type = module_type
        self._error_callback: Optional[Callable[[str], None]] = None

        if not spawn and instance_id is None:
            raise ValueError(f"instance_id is required when spawn=False for module type '{module_type}'")

        # Determine the target_id based on spawn and provided instance_id
        self.target_id = instance_id or generate_unique_id(module_type)
        logger.debug(f"Initializing BaseModule: type='{module_type}', id='{self.target_id}', spawn={spawn}")

        # Register the internal handler for this instance
        connection.register_message_handler(self.target_id, self._internal_message_handler)

        # Only send spawn command if requested
        if spawn:
            self._send_command("spawn", payload or {})
        # else: Assuming instance exists, just track it locally

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Internal handler for messages received for this specific instance.

        This method is automatically called by the connection manager when a
        message arrives from Sidekick intended for this module instance.
        It checks if the message is an error or an event. Subclasses override
        this to handle specific events (like clicks).

        Args:
            message (Dict[str, Any]): The message dictionary received from Sidekick.

        Returns:
            None
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "error":
            error_message = "Unknown error"
            if payload and isinstance(payload.get("message"), str):
                error_message = payload["message"]
            logger.error(f"Module '{self.target_id}' received error from Sidekick: {error_message}")
            if self._error_callback:
                try:
                    self._error_callback(error_message)
                except Exception as e:
                    logger.exception(f"Error in {self.module_type} '{self.target_id}' on_error callback: {e}")
        elif msg_type == "event":
            # Base implementation doesn't handle specific events, subclasses should.
            pass
        else:
            logger.warning(f"Module '{self.target_id}' received unhandled message type '{msg_type}': {message}")

    def on_error(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to handle errors specific to this module instance.

        If Sidekick encounters an error related to this specific module instance
        (e.g., trying to update a cell that doesn't exist), it might send back
        an error message. This function allows you to define what happens when
        such an error is received.

        Args:
            callback (Optional[Callable[[str], None]]): A function that takes one
                argument (the error message string). Pass `None` to remove any
                existing callback.

        Raises:
            TypeError: If the provided callback is not callable or None.

        Examples:
            >>> def handle_grid_error(error_msg):
            ...     print(f"Oops, grid error: {error_msg}")
            >>> my_grid.on_error(handle_grid_error)
            >>> # To remove the handler:
            >>> my_grid.on_error(None)

        Returns:
            None
        """
        if callback is not None and not callable(callback):
            raise TypeError("Error callback must be callable or None")
        logger.info(f"Setting on_error callback for module '{self.target_id}'.")
        self._error_callback = callback

    def _send_command(self, msg_type: str, payload: Optional[Dict[str, Any]] = None):
        """Constructs and sends a command message to Sidekick for this instance.

        This is an internal helper method used by methods like `set_color` or `clear`.
        It formats the message according to the Sidekick protocol and uses the
        connection manager to send it (handling buffering if needed).

        Args:
            msg_type (str): The message type (e.g., "spawn", "update", "remove").
            payload (Optional[Dict[str, Any]]): The data payload for the command.
                Keys should be camelCase. Defaults to None.

        Returns:
            None
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
        """Sends an 'update' command with the given payload.

        Shortcut for `_send_command("update", payload)`.

        Args:
            payload (Dict[str, Any]): The payload for the update command.

        Returns:
            None
        """
        self._send_command("update", payload)

    def remove(self):
        """Removes this module instance from the Sidekick UI.

        Sends a 'remove' command to Sidekick to delete the corresponding UI
        element and cleans up internal references and callbacks associated
        with this Python object.

        Examples:
            >>> my_grid.remove()
            >>> my_console.remove()

        Returns:
            None
        """
        logger.info(f"Requesting removal of module '{self.target_id}'.")
        # Always try to unregister handler first
        connection.unregister_message_handler(self.target_id)
        # Reset local callbacks
        self._error_callback = None
        # Let subclasses reset their specific callbacks if needed
        self._reset_specific_callbacks()
        # Send remove command (might be buffered)
        self._send_command("remove")

    def _reset_specific_callbacks(self):
        """Internal placeholder for subclasses to reset their specific callbacks.

        Called during the `remove()` process. Subclasses (like Grid, Console)
        override this to set their specific event callbacks (like `_click_callback`
        or `_input_text_callback`) back to None.

        Returns:
            None
        """
        pass

    def __del__(self):
        """Attempts to unregister the message handler upon garbage collection.

        This is a cleanup measure, but relying on `remove()` explicitly is safer.
        """
        try:
            # Check if connection module still exists (might be cleaned up during exit)
            if hasattr(connection, 'unregister_message_handler'):
                 connection.unregister_message_handler(self.target_id)
        except Exception:
            # Suppress errors during cleanup
            pass