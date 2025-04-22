"""
Provides the foundational `BaseModule` class for all Sidekick visual modules.

This module defines the common blueprint used by other specific module classes
like `Grid`, `Console`, `Canvas`, etc. Think of it as the underlying engine
that handles tasks shared by all visual elements you create with Sidekick.

You typically won't use `BaseModule` directly in your scripts. Instead, you'll
work with the more specific classes (like `sidekick.Grid`). This base class
takes care of essential background tasks:

- Giving each module instance a unique ID (`target_id`).
- Making sure the connection to the Sidekick panel is active before sending commands.
- Providing helper methods (`_send_command`, `_send_update`) for sending
  instructions (like "create", "update", "remove") to the Sidekick UI.
- Offering a standard way to remove the visual element (`remove()` method).
- Providing a way to handle errors reported by Sidekick for a specific module
  instance (`on_error` callback).
"""

from . import logger
from . import connection
from .utils import generate_unique_id
from typing import Optional, Dict, Any, Callable

class BaseModule:
    """Base class for all Sidekick module interface classes (like Grid, Console).

    This class manages the fundamental setup and communication logic needed
    for any Python object that represents a visual element in the Sidekick UI.
    It handles the creation of a unique ID, ensures the WebSocket connection
    is ready, sends commands, and provides common methods like `remove()` and
    `on_error()`.

    Note:
        This class is primarily for internal use by the library. You should use
        the specific subclasses like `sidekick.Grid`, `sidekick.Console`, etc.,
        in your code.

    Attributes:
        module_type (str): A string identifying the type of Sidekick module this
            class represents (e.g., "grid", "console"). Used in communication.
        target_id (str): The unique identifier assigned to this specific module
            instance. This ID is used to route commands and events between
            the Python script and the correct UI element in Sidekick.
    """
    def __init__(
        self,
        module_type: str,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        payload: Optional[Dict[str, Any]] = None,
    ):
        """Initializes the base module, preparing it for interaction.

        This constructor is called automatically when you create an instance
        of a specific module class (e.g., `my_grid = sidekick.Grid(5, 5)`).
        It sets up the unique ID, registers the instance with the connection
        manager so it can receive messages, and optionally sends the initial
        'spawn' command to create the visual element in the Sidekick UI.

        Args:
            module_type (str): The internal type name of the module (e.g., "grid").
                This must match the type expected by the Sidekick UI.
            instance_id (Optional[str]): A user-provided ID for this module instance.
                - If `spawn` is True (creating a new element), this is optional.
                  If not provided, a unique ID will be generated automatically
                  (e.g., "grid-1"). Providing one allows you to reference this
                  specific instance later, perhaps from another script or context
                  (requires careful coordination).
                - If `spawn` is False (attaching to an existing element), this ID
                  is **required** and must match the ID of the element already
                  present in the Sidekick UI.
            spawn (bool): If True (the default), a "spawn" command is sent to
                Sidekick immediately to create the corresponding UI element.
                If False, the library assumes the UI element with the given
                `instance_id` already exists, and this Python object will simply
                "attach" to it to send commands or receive events.
            payload (Optional[Dict[str, Any]]): A dictionary containing the
                initial configuration data needed by the Sidekick UI to create
                the element (e.g., grid dimensions, console settings). This is
                only used if `spawn` is True. Keys in this dictionary should
                generally be `camelCase` to match the communication protocol.

        Raises:
            ValueError: If `spawn` is False but no `instance_id` was provided.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established when `activate_connection()` is called.
        """
        # Ensure the connection is activated (blocks until ready or raises error).
        # This is crucial before registering handlers or sending commands.
        connection.activate_connection()

        self.module_type = module_type
        # Initialize the placeholder for the user's error callback.
        self._error_callback: Optional[Callable[[str], None]] = None

        # Validate instance_id requirement when not spawning.
        if not spawn and instance_id is None:
            raise ValueError(f"instance_id is required when spawn=False for module type '{module_type}'")

        # Determine the final ID: use provided one or generate a new one.
        # Use generate_unique_id ONLY if spawning and no ID is given.
        # If not spawning, instance_id is guaranteed to be non-None here due to the check above.
        self.target_id = instance_id if instance_id is not None else (generate_unique_id(module_type) if spawn else '')
        if not self.target_id: # Should not happen if logic above is correct
             raise ValueError(f"Could not determine target_id for {module_type} (spawn={spawn}, instance_id={instance_id})")


        logger.debug(f"Initializing BaseModule: type='{module_type}', id='{self.target_id}', spawn={spawn}")

        # Register this instance's internal message handler with the connection manager.
        # This tells the connection manager to call self._internal_message_handler
        # whenever a message arrives from Sidekick with this instance's target_id
        # in the 'src' field.
        connection.register_message_handler(self.target_id, self._internal_message_handler)

        # If requested, send the initial command to create the UI element.
        if spawn:
            # Use the provided payload, or an empty dict if None.
            # Keys in the payload dictionary *must* be camelCase for the protocol.
            self._send_command("spawn", payload or {})
        # else: If not spawning, we just assume the UI element exists.

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages specifically targeted at this module instance.

        This method is called automatically by the `connection` module's listener
        thread when a message arrives from the Sidekick UI where the message's
        `src` field matches this instance's `target_id`.

        It checks if the message is an 'error' type and calls the registered
        `on_error` callback if available. Subclasses (like Grid, Console)
        override this method to add handling for 'event' type messages (like
        clicks or text input) specific to their functionality.

        Args:
            message (Dict[str, Any]): The raw message dictionary received from
                the Sidekick connection manager.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload should contain camelCase keys.

        if msg_type == "error":
            # Attempt to extract the error message string from the payload.
            error_message = "Unknown error received from Sidekick UI."
            if payload and isinstance(payload.get("message"), str):
                error_message = payload["message"]
            logger.error(f"Module '{self.target_id}' received error from Sidekick UI: {error_message}")
            # If the user registered an error handler, call it.
            if self._error_callback:
                try:
                    self._error_callback(error_message)
                except Exception as e:
                    # Catch errors within the user's callback to prevent crashing the listener.
                    logger.exception(f"Error in {self.module_type} '{self.target_id}' on_error callback: {e}")
        elif msg_type == "event":
            # Base class doesn't handle specific events. Subclasses override this
            # method, check `payload['event']`, and call their specific callbacks.
            logger.debug(f"BaseModule received unhandled event for '{self.target_id}': {payload}")
            pass
        else:
            # Log if we receive an unexpected message type targeted at this instance.
            logger.warning(f"Module '{self.target_id}' received unhandled message type '{msg_type}': {message}")

    def on_error(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to call when Sidekick reports an error for this specific module.

        Sometimes, the Sidekick UI might encounter a problem related to this
        specific module (e.g., you tried to update a grid cell that doesn't
        exist). In such cases, the UI might send an 'error' message back.
        This method lets you define a Python function (`callback`) that will
        be executed when such an error message is received.

        Args:
            callback (Optional[Callable[[str], None]]): The function to call
                when an error message arrives. This function should accept one
                argument: a string containing the error message from Sidekick.
                Pass `None` to remove any previously registered error handler.

        Raises:
            TypeError: If the provided `callback` is not a function (or None).

        Returns:
            None: This method sets up the callback but doesn't return anything.

        Examples:
            >>> def my_grid_error_handler(message):
            ...     print(f"Oh no, the grid reported an error: {message}")
            ...
            >>> my_grid = sidekick.Grid(5, 5)
            >>> my_grid.on_error(my_grid_error_handler)
            >>>
            >>> # Later, to remove the handler:
            >>> my_grid.on_error(None)
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_error callback must be a callable function or None.")
        logger.info(f"Setting on_error callback for module '{self.target_id}'.")
        self._error_callback = callback

    def _send_command(self, msg_type: str, payload: Optional[Dict[str, Any]] = None):
        """Internal helper to build and send a command message to Sidekick.

        This method constructs the standard message dictionary structure required
        by the communication protocol and then uses the `connection.send_message`
        function to actually send it over the WebSocket. `connection.send_message`
        handles ensuring the connection is ready and potential errors.

        Args:
            msg_type (str): The type of command (e.g., "spawn", "update", "remove").
            payload (Optional[Dict[str, Any]]): The data payload associated with
                the command. **Keys within this payload dictionary should be
                `camelCase`** to match the protocol expected by the Sidekick UI.
                Defaults to None if no payload is needed.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or if sending the message fails.
        """
        message: Dict[str, Any] = {
            "id": 0, # Reserved for future use, currently 0.
            "module": self.module_type, # e.g., "grid", "console"
            "type": msg_type,           # e.g., "spawn", "update"
            "target": self.target_id,   # Identifies which UI element this command is for.
            # "src" is not needed when sending commands from Python to UI.
        }
        # Only include the payload field in the JSON if it's provided.
        if payload is not None:
            message["payload"] = payload

        # Delegate the actual sending (and connection readiness check)
        # to the connection module.
        connection.send_message(message)

    def _send_update(self, payload: Dict[str, Any]):
        """Convenience method for sending an 'update' command with the given payload.

        This is simply a shortcut for `_send_command("update", payload)`.

        Args:
            payload (Dict[str, Any]): The payload for the update command. Keys
                within this dictionary should be `camelCase`.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or if sending the message fails.
        """
        # Assume payload always exists for updates
        if payload is None:
            logger.warning(f"Module '{self.target_id}' _send_update called with None payload.")
            payload = {} # Send empty payload instead? Or raise? Sending empty for now.

        self._send_command("update", payload)

    def remove(self):
        """Removes this module instance from the Sidekick UI and cleans up resources.

        This performs two main actions:
        1. Sends a 'remove' command to the Sidekick UI, telling it to delete
           the visual element associated with this Python object.
        2. Cleans up internal resources in the Python library associated with
           this instance, such as unregistering message handlers and resetting
           any user-defined callbacks (like `on_click` or `on_error`).

        After calling `remove()`, you should generally not interact with this
        module object anymore.

        Returns:
            None: This method initiates removal but doesn't return anything.

        Examples:
            >>> my_grid = sidekick.Grid(5, 5)
            >>> # ... use the grid ...
            >>> my_grid.remove() # Remove the grid from the UI
            >>>
            >>> my_console = sidekick.Console()
            >>> # ... use the console ...
            >>> my_console.remove() # Remove the console
        """
        logger.info(f"Requesting removal of module '{self.target_id}'.")

        # 1. Unregister the handler so we don't process messages for a removed module.
        connection.unregister_message_handler(self.target_id)

        # 2. Reset local callbacks defined in this base class.
        self._error_callback = None

        # 3. Give subclasses a chance to reset their specific callbacks.
        self._reset_specific_callbacks()

        # 4. Send the 'remove' command to the Sidekick UI.
        #    This happens last, after internal cleanup. connection.send_message
        #    handles connection checks/errors.
        try:
             self._send_command("remove") # Payload is typically None/omitted for remove
        except connection.SidekickConnectionError as e:
             # Log if sending remove command fails, but don't crash the removal process.
             logger.warning(f"Failed to send remove command for '{self.target_id}': {e}. "
                            f"Internal cleanup still performed.")


    def _reset_specific_callbacks(self):
        """Internal placeholder for subclasses to reset their unique callbacks.

        This method is called by the public `remove()` method. Subclasses
        (like `Grid`, `Console`, `Control`) should override this method to
        set their specific callback attributes (e.g., `_click_callback`,
        `_input_text_callback`) back to `None` during the removal process.
        """
        # Base implementation does nothing, subclasses should override.
        pass

    def __del__(self):
        """Attempt to unregister the message handler when the object is garbage collected.

        This is intended as a fallback safety measure. It tries to clean up the
        message handler registration if the object is deleted without `remove()`
        being called explicitly.

        Warning:
            Relying on `__del__` for cleanup is generally discouraged in Python
            as its execution timing is not guaranteed. You should **always try
            to call the `remove()` method explicitly** when you are finished
            with a Sidekick module instance.
        """
        try:
            # Check if the connection module and its function still exist,
            # as they might be gone during interpreter shutdown.
            if hasattr(connection, 'unregister_message_handler'):
                 connection.unregister_message_handler(self.target_id)
                 logger.debug(f"BaseModule __del__ unregistering handler for {self.target_id}")
        except Exception:
            # Suppress errors during __del__ as per standard practice.
            pass