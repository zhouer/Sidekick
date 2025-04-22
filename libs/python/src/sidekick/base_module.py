"""Provides the foundational `BaseModule` class for all Sidekick visual modules.

This module defines the common blueprint and core functionalities shared by all
the visual elements you create with Sidekick (like `Grid`, `Console`, `Canvas`, etc.).
Think of it as the engine under the hood that handles essential tasks necessary
for any Python object representing a component in the Sidekick UI.

Key responsibilities managed by `BaseModule`:

*   **Unique Identification:** Assigning a unique ID (`target_id`) to each module
    instance, allowing Sidekick to distinguish between different elements (e.g.,
    multiple Grids).
*   **Connection Activation:** Automatically ensuring the connection to the
    Sidekick panel is active (`activate_connection()`) before sending any commands.
    This happens when you first create a module instance.
*   **Command Sending:** Providing internal helper methods (`_send_command`,
    `_send_update`) for constructing and sending standardized instruction messages
    (like "create this grid", "update that cell", "remove this console") over the
    WebSocket connection according to the Sidekick protocol.
*   **Removal:** Offering a standard `remove()` method to destroy the visual element
    in the Sidekick UI and clean up associated resources in the Python library.
*   **Error Handling:** Providing a way (`on_error()`) for users to register a
    callback function to handle potential error messages sent back *from* the
    Sidekick UI related to a specific module instance.
*   **Message Routing:** Registering each instance with the connection manager so
    that incoming events (like clicks) or errors from the UI can be routed back
    to the correct Python object's internal handler (`_internal_message_handler`).

Note:
    You will typically **not** use `BaseModule` directly in your scripts. Instead,
    you'll instantiate its subclasses like `sidekick.Grid`, `sidekick.Console`, etc.
    This base class transparently handles the common low-level details for you.
"""

from . import logger
from . import connection # Import the connection management module
from .utils import generate_unique_id # For generating default instance IDs
from typing import Optional, Dict, Any, Callable

class BaseModule:
    """Base class for all Sidekick module interface classes (e.g., Grid, Console).

    This abstract class manages the fundamental setup, unique identification,
    and communication logic required for any Python object that represents and
    controls a visual component within the Sidekick UI panel.

    It ensures that when a module instance is created, the connection to Sidekick
    is established, a unique ID is assigned, and the instance is registered to
    receive relevant messages (events, errors) from the UI. It provides standardized
    methods for sending commands (`spawn`, `update`, `remove`) and handling cleanup.

    Note:
        This class is designed for internal use by the library developers when
        creating new Sidekick module types. Users of the library should interact
        with the concrete subclasses (`sidekick.Grid`, `sidekick.Console`, etc.).

    Attributes:
        module_type (str): A string identifying the type of Sidekick module this
            class represents (e.g., "grid", "console"). This must match the type
            expected by the Sidekick UI component and defined in the communication
            protocol.
        target_id (str): The unique identifier assigned to this specific module
            instance. This ID is crucial for routing commands from Python to the
            correct UI element and for routing events/errors back from that UI
            element to this Python object.
    """
    def __init__(
        self,
        module_type: str,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        payload: Optional[Dict[str, Any]] = None,
    ):
        """Initializes the base module, setting up ID, connection, and registration.

        This constructor is called automatically by the `__init__` method of
        subclasses (like `Grid`, `Console`). It performs the essential setup steps:

        1.  **Activates Connection:** Calls `connection.activate_connection()`. This is
            a **blocking call** the *first* time any module is created in a script.
            It ensures the WebSocket connection is established and the Sidekick UI
            is ready before proceeding. Raises `SidekickConnectionError` on failure.
        2.  **Assigns ID:** Determines the unique `target_id` for this instance, either
            using the provided `instance_id` or generating one automatically if `spawn`
            is True and `instance_id` is None.
        3.  **Registers Handler:** Registers this instance's `_internal_message_handler`
            method with the `connection` module, allowing it to receive messages
            specifically targeted at this instance's `target_id`.
        4.  **Spawns UI Element (Optional):** If `spawn` is True, sends the initial
            'spawn' command to the Sidekick UI via the WebSocket, instructing it
            to create the corresponding visual element (using the provided `payload`
            for initial configuration).

        Args:
            module_type (str): The internal type name of the module (e.g., "grid",
                "console", "viz"). This must match the type expected by the
                Sidekick UI and defined in the communication protocol.
            instance_id (Optional[str]): A specific ID for this module instance.
                If `spawn` is True (default), this is optional; if None, a unique ID
                (e.g., "grid-1") is generated automatically. Providing an ID when
                spawning allows deterministic referencing but requires user management
                of uniqueness. If `spawn` is False (attaching to an existing UI
                element), this ID is **required** and must exactly match the ID of
                the pre-existing element in the Sidekick UI panel.
            spawn (bool): If True (the default), a "spawn" command is sent to
                Sidekick immediately after connection readiness to create the
                corresponding UI element using the `payload`. If False, the library
                assumes the UI element with the given `instance_id` already exists,
                and this Python object will simply "attach" to it to send subsequent
                commands (`update`, `remove`) or receive events/errors. The `payload`
                is ignored when `spawn` is False.
            payload (Optional[Dict[str, Any]]): A dictionary containing the initial
                configuration data needed by the Sidekick UI to correctly create
                (spawn) the visual element (e.g., grid dimensions, console settings,
                canvas size). This is **only** used if `spawn` is True. Keys within
                this dictionary should generally conform to the `camelCase` convention
                required by the Sidekick communication protocol. Defaults to None.

        Raises:
            ValueError: If `spawn` is False but no `instance_id` was provided, or
                        if the determined `target_id` ends up being empty.
            SidekickConnectionError (or subclass): If `connection.activate_connection()`
                fails (e.g., cannot connect, timeout waiting for UI).
        """
        # CRITICAL: Ensure the connection is active and ready before doing anything else.
        # This blocks execution the first time it's called in a script until the
        # connection is fully established or raises an error if it fails.
        # Subsequent calls usually return quickly if already connected.
        connection.activate_connection() # Raises on failure.

        self.module_type = module_type
        # Placeholder for the user-defined error callback function.
        self._error_callback: Optional[Callable[[str], None]] = None

        # --- Determine the Target ID ---
        # Validate instance_id requirement when attaching to an existing element.
        if not spawn and instance_id is None:
            raise ValueError(f"instance_id is required when spawn=False for module type '{module_type}'")

        # Assign target_id: Use provided ID if given, otherwise generate one ONLY if spawning.
        # If not spawning, instance_id is guaranteed to be non-None due to the check above.
        self.target_id = instance_id if instance_id is not None else \
                         (generate_unique_id(module_type) if spawn else '') # Fallback to empty if logic fails

        # Final check to ensure target_id is valid. Should ideally not be triggered.
        if not self.target_id:
             raise ValueError(f"Could not determine a valid target_id for module '{module_type}' "
                              f"(spawn={spawn}, instance_id={instance_id})")

        logger.debug(f"Initializing BaseModule: type='{module_type}', id='{self.target_id}', spawn={spawn}")

        # --- Register with Connection Manager ---
        # Tell the connection module that messages from the UI with 'src' == self.target_id
        # should be delivered to this instance's _internal_message_handler method.
        connection.register_message_handler(self.target_id, self._internal_message_handler)

        # --- Send Spawn Command (if requested) ---
        if spawn:
            # Use the provided payload, defaulting to an empty dictionary if None.
            # Subclass __init__ methods are responsible for constructing the correct payload
            # with camelCase keys as required by the protocol.
            final_payload = payload or {}
            self._send_command("spawn", final_payload)
        # else: If not spawning, we assume the UI element already exists and do nothing here.

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages (events/errors) targeted at this module instance. (Internal).

        This method is called automatically by the `connection` module's background
        listener thread whenever a message arrives from the Sidekick UI where the
        message's `src` field matches this instance's `target_id`.

        The base implementation specifically checks for messages with `type: "error"`.
        If found, it extracts the error message string from the payload and calls the
        user's registered `on_error` callback (if one exists).

        **Subclasses (like Grid, Console) MUST override this method** to add
        handling for their specific `type: "event"` messages (like clicks or text
        input). Overriding methods should typically call `super()._internal_message_handler(message)`
        at the end to ensure that the base error handling still occurs.

        Args:
            message (Dict[str, Any]): The raw message dictionary received from
                the Sidekick connection manager. Expected to follow the protocol
                structure (keys: 'type', 'module', 'src', 'payload'). Payload keys
                are expected to be `camelCase`.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload should contain camelCase keys.

        # Handle generic 'error' messages sent from the UI for this module.
        if msg_type == "error":
            # Attempt to extract a meaningful error message from the payload.
            error_message = "Unknown error message received from Sidekick UI." # Default message
            if payload and isinstance(payload.get("message"), str):
                error_message = payload["message"] # Extract 'message' field if present and string.
            logger.error(f"Module '{self.target_id}' received error from Sidekick UI: {error_message}")
            # If the user has registered an error handler via on_error(), call it.
            if self._error_callback:
                try:
                    self._error_callback(error_message)
                except Exception as e:
                    # Catch and log errors *within* the user's callback function
                    # to prevent crashing the library's listener thread.
                    logger.exception(f"Error occurred inside {self.module_type} '{self.target_id}' on_error callback: {e}")
        elif msg_type == "event":
            # Base class doesn't handle specific events. Subclasses override this
            # method, check the `payload['event']` value (e.g., 'click', 'inputText'),
            # parse relevant data from the payload, and call their specific callbacks.
            logger.debug(f"BaseModule received unhandled event for '{self.target_id}': {payload}")
            # Subclass override should handle specific events before potentially calling super().
            pass
        else:
            # Log if we receive an unexpected message type targeted at this instance.
            logger.warning(f"Module '{self.target_id}' received unexpected message type '{msg_type}': {message}")

    def on_error(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to handle error messages from the Sidekick UI for this module.

        Occasionally, the Sidekick UI panel might encounter an issue while trying
        to process a command related to *this specific module instance* (e.g.,
        you sent invalid coordinates to `grid.set_color`, or tried to draw on a
        non-existent canvas buffer). In such cases, the UI might send an 'error'
        message back to your script.

        This method allows you to define a Python function (`callback`) that will
        be executed automatically when such an error message arrives for this module.

        Args:
            callback (Optional[Callable[[str], None]]): The function to call
                when an error message arrives for this module instance. The function
                should accept one argument: a string containing the error message
                sent from the Sidekick UI. Pass `None` to remove any previously
                registered error handler for this instance.

        Raises:
            TypeError: If the provided `callback` is not a callable function (or None).

        Example:
            >>> def my_grid_error_reporter(error_msg):
            ...     print(f"WARN: The grid '{my_grid.target_id}' reported an error: {error_msg}")
            ...
            >>> my_grid = sidekick.Grid(5, 5)
            >>> my_grid.on_error(my_grid_error_reporter)
            >>>
            >>> try:
            ...     my_grid.set_color(10, 10, 'red') # This might trigger an error if grid is 5x5
            ... except IndexError:
            ...     print("Caught local index error.") # Local check catches this first
            ... # If an error occurred *in the UI* processing a valid-looking command,
            ... # the callback would be triggered.
            >>>
            >>> # To stop handling errors this way:
            >>> my_grid.on_error(None)
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_error callback must be a callable function or None.")
        logger.info(f"Setting on_error callback for module '{self.target_id}'.")
        # Store the user's callback function.
        self._error_callback = callback

    def _send_command(self, msg_type: str, payload: Optional[Dict[str, Any]] = None):
        """Internal helper to construct and send a standard command message to Sidekick.

        This method builds the message dictionary according to the Sidekick
        communication protocol structure (including module type, message type,
        and this instance's target ID) and then uses the `connection.send_message`
        function to transmit it over the WebSocket.

        `connection.send_message` handles ensuring the connection is active and
        deals with potential low-level sending errors.

        Note:
            Payload keys within the passed `payload` dictionary should generally
            be `camelCase` as expected by the Sidekick UI and protocol. This method
            does not perform case conversion itself; that responsibility lies with
            the calling methods in the subclasses (e.g., `Grid.set_color`).

        Args:
            msg_type (str): The type of command being sent (e.g., "spawn", "update", "remove").
            payload (Optional[Dict[str, Any]]): The data payload associated with
                the command. Keys within this dictionary should already be in the
                correct `camelCase` format for the protocol. Defaults to None if
                no payload is needed for the command type.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or if `connection.send_message` fails during transmission.
        """
        # Construct the base message structure common to all commands sent to the UI.
        message: Dict[str, Any] = {
            "id": 0, # Reserved for future use, currently always 0.
            "module": self.module_type, # The type of module (e.g., "grid", "console").
            "type": msg_type,           # The command action (e.g., "spawn", "update").
            "target": self.target_id,   # Identifies *which* UI element this command applies to.
            # "src" field is omitted, as it's used for messages *from* the UI.
        }
        # Only include the 'payload' field in the final JSON message if it's provided.
        if payload is not None:
            message["payload"] = payload

        # Delegate the actual sending (including connection readiness checks and error handling)
        # to the connection module's public send function.
        connection.send_message(message)

    def _send_update(self, payload: Dict[str, Any]):
        """Convenience method for sending an 'update' command with a specific payload. (Internal).

        This is a shortcut frequently used by module methods that modify the state
        of an existing UI element (e.g., `grid.set_color`, `console.print`, `canvas.draw_line`).
        It simply calls `_send_command("update", payload)`.

        Note:
            The provided `payload` dictionary *must* already contain the module-specific
            `action` key (e.g., "setColor", "append", "drawLine") and any required
            `options` sub-dictionary with `camelCase` keys, as defined by the protocol
            for that module's update actions.

        Args:
            payload (Dict[str, Any]): The complete payload for the 'update' command,
                including the specific action and its options (with camelCase keys).

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or if sending the message fails.
        """
        # Although the protocol allows optional payload, updates usually require one.
        # Log a warning if called with None, though maybe allow empty dict?
        if payload is None:
            logger.warning(f"Module '{self.target_id}' _send_update called with None payload. Sending empty payload.")
            payload = {} # Send empty payload instead of failing? Needs decision.

        # Call the generic command sender with type="update".
        self._send_command("update", payload)

    def remove(self):
        """Removes this module instance from the Sidekick UI and cleans up resources.

        This method performs the necessary actions to gracefully remove the visual
        element associated with this Python object from the Sidekick panel and
        tidy up related resources within the library.

        Specifically, it:

        1.  **Unregisters Handlers:** Stops listening for messages (events/errors)
            specifically targeted at this module instance.
        2.  **Resets Callbacks:** Clears any user-defined callback functions
            (like `on_click` or `on_error`) associated with this instance, both
            in the base class and any specific ones defined in subclasses via
            `_reset_specific_callbacks()`.
        3.  **Sends Remove Command:** Sends a 'remove' command to the Sidekick UI,
            instructing it to destroy the visual element corresponding to this
            instance's `target_id`.

        Important:
            After calling `remove()`, you should generally consider this module object
            inactive and avoid calling further methods on it, as it no longer
            corresponds to an element in the UI and cannot send commands effectively.

        Raises:
            SidekickConnectionError (or subclass): Can potentially be raised by the
                underlying `_send_command` if sending the 'remove' command fails,
                though the local cleanup (steps 1 & 2) will still be attempted.

        Example:
            >>> my_grid = sidekick.Grid(5, 5)
            >>> my_console = sidekick.Console()
            >>> # ... use the grid and console ...
            >>>
            >>> # Remove them when done
            >>> my_grid.remove()
            >>> my_console.remove()
        """
        logger.info(f"Requesting removal of module '{self.module_type}' with id '{self.target_id}'.")

        # 1. Unregister the internal message handler for this instance ID.
        #    This prevents processing messages for an element that's being removed.
        connection.unregister_message_handler(self.target_id)

        # 2. Reset local callback references defined in this base class.
        self._error_callback = None

        # 3. Call the hook for subclasses to reset their specific callbacks.
        self._reset_specific_callbacks()

        # 4. Send the 'remove' command to the Sidekick UI.
        #    This happens last, after internal cleanup. _send_command handles
        #    connection checks and potential errors during sending.
        #    The payload for 'remove' is typically None/omitted according to protocol.
        try:
             self._send_command("remove", payload=None)
        except connection.SidekickConnectionError as e:
             # Log a warning if sending the remove command fails, but don't stop
             # the Python-side cleanup that has already happened.
             logger.warning(f"Failed to send 'remove' command for module '{self.target_id}' "
                            f"(it might remain visible in the UI): {e}. "
                            f"Internal Python-side cleanup still performed.")
        # No return value.


    def _reset_specific_callbacks(self):
        """Internal hook for subclasses to reset their unique callback attributes. (Internal).

        This method is called by the public `remove()` method *before* the final
        'remove' command is sent to the UI. Subclasses (like `Grid`, `Console`,
        `Control`, `Canvas`, `Viz`) **must** override this method if they store
        references to user-provided callback functions (e.g., `_click_callback`,
        `_input_text_callback`). The override should simply set these specific
        callback attributes back to `None` to break potential reference cycles and
        ensure they are not called after removal.

        Example override in a hypothetical `Button` subclass:
            ```python
            def _reset_specific_callbacks(self):
                self._click_callback = None
                self._hover_callback = None # If it had a hover callback too
            ```
        """
        # Base implementation does nothing. Subclasses provide the actual logic.
        pass

    def __del__(self):
        """Attempt to unregister the message handler upon garbage collection. (Fallback).

        This special method is called by Python's garbage collector when the
        `BaseModule` instance is about to be destroyed if its reference count
        reaches zero. It attempts to unregister the instance's message handler
        from the `connection` module as a fallback safety measure in case the
        `remove()` method was not called explicitly.

        Warning:
            Relying on `__del__` for crucial cleanup like this is **strongly
            discouraged** in Python. The timing of garbage collection and `__del__`
            execution is unpredictable and not guaranteed, especially during
            interpreter shutdown. **You should always explicitly call the `remove()`
            method** on your Sidekick module instances when you are finished with
            them to ensure proper cleanup in both the Python library and the
            Sidekick UI panel. This `__del__` method is only a best-effort fallback.
        """
        try:
            # Check if the connection module and its function still exist,
            # as they might be garbage collected themselves during interpreter shutdown.
            if hasattr(connection, 'unregister_message_handler'):
                 connection.unregister_message_handler(self.target_id)
                 # Log only at debug level as this is fallback behavior.
                 logger.debug(f"BaseModule __del__ attempting fallback unregistration for {self.target_id}")
        except Exception:
            # Suppress any errors during __del__ execution, as recommended practice.
            # We don't want __del__ to cause noisy errors, especially during shutdown.
            pass