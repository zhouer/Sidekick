"""Provides the foundational `BaseComponent` class for all Sidekick visual components.

This component defines the common blueprint and core functionalities shared by all
the visual elements you create with Sidekick (like `Grid`, `Console`, `Canvas`,
`Label`, `Button`, `Textbox`, `Markdown`, `Row`, `Column`). Think of it as the
engine under the hood that handles essential tasks necessary for any Python object
representing a component in the Sidekick UI.

Key responsibilities managed by `BaseComponent`:

*   **Unique Identification:** Assigning a unique ID (`target_id`) to each component
    instance, allowing Sidekick to distinguish between different elements (e.g.,
    multiple Grids).
*   **Connection Activation:** Automatically ensuring the connection to the
    Sidekick panel is active (`activate_connection()`) before sending any commands.
    This happens when you first create a component instance.
*   **Command Sending:** Providing internal helper methods (`_send_command`,
    `_send_update`) for constructing and sending standardized instruction messages
    (like "create this grid", "update that cell", "remove this console") over the
    communication channel according to the Sidekick protocol.
*   **Parenting:** Allowing components to be nested within container components
    (like `Row` or `Column`) by specifying a `parent` during initialization.
    The `parent` information is sent in the 'spawn' command.
*   **Removal:** Offering a standard `remove()` method to destroy the visual element
    in the Sidekick UI and clean up associated resources in the Python library.
    When a container is removed, its children should be recursively removed by the UI.
*   **Error Handling:** Providing a way (`on_error()`) for users to register a
    callback function to handle potential error messages sent back *from* the
    Sidekick UI related to a specific component instance.
*   **Message Routing:** Registering each instance with the connection manager so
    that incoming events (like clicks) or errors from the UI can be routed back
    to the correct Python object's internal handler (`_internal_message_handler`).

Note:
    You will typically **not** use `BaseComponent` directly in your scripts. Instead,
    you'll instantiate its subclasses like `sidekick.Grid`, `sidekick.Console`, etc.
    This base class transparently handles the common low-level details for you.
"""

from . import logger
from . import connection # Import the connection management component
from .errors import SidekickConnectionError
from .utils import generate_unique_id # For generating default instance IDs
from typing import Optional, Dict, Any, Callable, Union # Added Union

class BaseComponent:
    """Base class for all Sidekick component interface classes.

    This abstract class manages the fundamental setup, unique identification,
    parenting, and communication logic required for any Python object that
    represents and controls a visual component within the Sidekick UI panel.

    It ensures that when a component instance is created, the connection to Sidekick
    is established, a unique ID is assigned, parent information is processed,
    and the instance is registered to receive relevant messages (events, errors)
    from the UI. It provides standardized methods for sending commands (`spawn`,
    `update`, `remove`) and handling cleanup.

    Note:
        This class is designed for internal use by the library developers when
        creating new Sidekick component types. Users of the library should interact
        with the concrete subclasses (`sidekick.Grid`, `sidekick.Label`, etc.).

    Attributes:
        component_type (str): A string identifying the type of Sidekick component this
            class represents (e.g., "grid", "label"). This must match the type
            expected by the Sidekick UI component and defined in the communication
            protocol.
        target_id (str): The unique identifier assigned to this specific component
            instance. This ID is crucial for routing commands and events.
    """
    def __init__(
        self,
        component_type: str,
        payload: Optional[Dict[str, Any]] = None,
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes the base component, setting up ID, parent, connection, and registration.

        This constructor is called automatically by the `__init__` method of
        subclasses. It performs the essential setup steps:

        1.  **Activates Connection:** Calls `connection.activate_connection()`. This is
            a **blocking call** the *first* time any component is created in a script.
            It ensures the communication channel is established and the Sidekick UI
            is ready before proceeding. Raises `SidekickConnectionError` on failure.
        2.  **Assigns ID:** Generates a unique `target_id` for this instance.
        3.  **Registers Handler:** Registers this instance's `_internal_message_handler`
            method with the `connection` component.
        4.  **Processes Parent:** Determines the parent ID string from the `parent`
            argument. If a parent is specified, its ID is added to the `spawn` payload.
            If `parent` is `None`, the component is added to the default top-level
            container (ID: "root") by the UI.
        5.  **Spawns UI Element:** Sends the initial 'spawn' command to the Sidekick UI
            instructing it to create the corresponding visual element, using the
            provided `payload` (potentially augmented with parent info) for initial
            configuration.

        Args:
            component_type (str): The internal type name of the component (e.g., "grid",
                "label", "button"). This must match the type expected by the
                Sidekick UI and defined in the communication protocol.
            payload (Optional[Dict[str, Any]]): A dictionary containing the initial
                configuration data needed by the Sidekick UI to correctly create
                (spawn) the visual element (e.g., grid dimensions, initial text).
                Keys within this dictionary should generally conform to the `camelCase`
                convention required by the Sidekick communication protocol.
                Defaults to None or an empty dictionary.
            parent (Optional[Union['BaseComponent', str]]): The parent container for
                this component. Can be:
                - A `BaseComponent` instance (e.g., a `Row` or `Column` object).
                - A `str` representing the `target_id` of an existing parent component.
                - `None` (default): The component will be added to the top-level
                  "root" container in the Sidekick UI.

        Raises:
            SidekickConnectionError (or subclass): If `connection.activate_connection()`
                fails (e.g., cannot connect, timeout waiting for UI).
            TypeError: If the `parent` argument is provided but is not a `BaseComponent`
                       instance, a string, or `None`.
        """
        # CRITICAL: Ensure the connection is active and ready before doing anything else.
        connection.activate_connection() # Raises on failure.

        self.component_type = component_type
        self._error_callback: Optional[Callable[[str], None]] = None

        # Generate a unique Target ID for this component instance.
        self.target_id = generate_unique_id(component_type)

        # Register this instance's message handler with the connection manager.
        connection.register_message_handler(self.target_id, self._internal_message_handler)

        # Prepare the final payload for the 'spawn' command.
        # Start with a copy of the provided component-specific payload (if any).
        final_spawn_payload = payload.copy() if payload else {}

        # Process the parent argument and add it to the spawn payload if specified.
        parent_id_to_send: Optional[str] = None
        if parent is not None:
            if isinstance(parent, BaseComponent):
                parent_id_to_send = parent.target_id
            elif isinstance(parent, str):
                parent_id_to_send = parent
            else:
                # Invalid parent type provided.
                msg = (f"Parent for component '{self.target_id}' (type: {component_type}) "
                       f"must be a Sidekick component instance, a string ID, or None. "
                       f"Received type: {type(parent).__name__}.")
                logger.error(msg)
                raise TypeError(msg)

            # If a parent was specified, its ID must be a non-empty string.
            if not parent_id_to_send: # Checks for empty string too
                msg = (f"Parent ID for component '{self.target_id}' cannot be an empty string. "
                       f"If specifying a parent by ID, it must be a valid, non-empty target_id. "
                       f"If parent was a BaseComponent, its target_id was empty.")
                logger.error(msg)
                # This situation is likely a programming error, either in user code
                # (passing empty string) or if a component's target_id was somehow empty.
                raise ValueError(msg)

            # Add the 'parent' key to the payload only if a valid parent ID was determined.
            # The protocol specifies that if 'parent' is omitted, it defaults to "root".
            final_spawn_payload["parent"] = parent_id_to_send

        # Send the 'spawn' command to the UI.
        self._send_command("spawn", final_spawn_payload)

        # Log initialization details, including the resolved parent.
        parent_display = parent_id_to_send if parent_id_to_send else "root (default)"
        logger.debug(
            f"Initialized BaseComponent: type='{component_type}', id='{self.target_id}', "
            f"parent='{parent_display}'"
        )

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages (events/errors) targeted at this component instance. (Internal).

        This method is called automatically by the `connection` component's background
        listener thread whenever a message arrives from the Sidekick UI where the
        message's `src` field matches this instance's `target_id`.

        The base implementation specifically checks for messages with `type: "error"`.
        If found, it extracts the error message string from the payload and calls the
        user's registered `on_error` callback (if one exists).

        **Subclasses (like Grid, Button) MUST override this method** to add
        handling for their specific `type: "event"` messages (like clicks or text
        input). Overriding methods should typically call `super()._internal_message_handler(message)`
        at the end to ensure that the base error handling still occurs.

        Args:
            message (Dict[str, Any]): The raw message dictionary received from
                the Sidekick connection manager. Expected to follow the protocol
                structure (keys: 'type', 'component', 'src', 'payload'). Payload keys
                are expected to be `camelCase`.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload should contain camelCase keys.

        if msg_type == "error":
            error_message = "Unknown error message received from Sidekick UI."
            if payload and isinstance(payload.get("message"), str):
                error_message = payload["message"]
            logger.error(f"Component '{self.target_id}' received error from Sidekick UI: {error_message}")
            if self._error_callback:
                try:
                    self._error_callback(error_message)
                except Exception as e:
                    logger.exception(
                        f"Error occurred inside {self.component_type} "
                        f"'{self.target_id}' on_error callback: {e}"
                    )
        elif msg_type == "event":
            logger.debug(f"BaseComponent received unhandled event for '{self.target_id}': {payload}")
            pass # Subclasses handle specific events.
        else:
            logger.warning(
                f"Component '{self.target_id}' received unexpected message type "
                f"'{msg_type}': {message}"
            )

    def on_error(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to handle error messages from the Sidekick UI for this component.

        Occasionally, the Sidekick UI panel might encounter an issue while trying
        to process a command related to *this specific component instance*. In such
        cases, the UI might send an 'error' message back to your script.

        This method allows you to define a Python function (`callback`) that will
        be executed automatically when such an error message arrives for this component.

        Args:
            callback (Optional[Callable[[str], None]]): The function to call
                when an error message arrives. It should accept one argument:
                a string containing the error message from the Sidekick UI.
                Pass `None` to remove a previously registered error handler.

        Raises:
            TypeError: If `callback` is not a callable function (or None).

        Example:
            >>> def my_grid_error_reporter(error_msg):
            ...     print(f"Grid error: {error_msg}")
            ...
            >>> my_grid = sidekick.Grid(5, 5)
            >>> my_grid.on_error(my_grid_error_reporter)
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_error callback must be a callable function or None.")
        logger.info(f"Setting on_error callback for component '{self.target_id}'.")
        self._error_callback = callback

    def _send_command(self, msg_type: str, payload: Optional[Dict[str, Any]] = None):
        """Internal helper to construct and send a standard command message to Sidekick.

        This method builds the message dictionary according to the Sidekick
        communication protocol and uses `connection.send_message` to transmit it.

        Note:
            Payload keys within `payload` should generally be `camelCase`. This method
            does not perform case conversion; that responsibility lies with callers.

        Args:
            msg_type (str): The type of command (e.g., "spawn", "update", "remove").
            payload (Optional[Dict[str, Any]]): The data payload for the command.
                Keys should already be in `camelCase`. Defaults to None.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or if `connection.send_message` fails.
        """
        message: Dict[str, Any] = {
            "id": 0,
            "component": self.component_type,
            "type": msg_type,
            "target": self.target_id,
        }
        if payload is not None:
            message["payload"] = payload

        connection.send_message(message)

    def _send_update(self, payload: Dict[str, Any]):
        """Convenience method for sending an 'update' command. (Internal).

        A shortcut for `_send_command("update", payload)`. Used by component methods
        that modify an existing UI element.

        Note:
            The `payload` *must* include the component-specific `action` key
            (e.g., "setColor", "setText") and any `options` sub-dictionary
            with `camelCase` keys, as defined by the protocol.

        Args:
            payload (Dict[str, Any]): The complete payload for the 'update' command,
                including the `action` and its `options` (with camelCase keys).

        Raises:
            SidekickConnectionError (or subclass): If connection or send fails.
        """
        if payload is None: # Should generally not be None for updates
            logger.warning(
                f"Component '{self.target_id}' _send_update called with None payload. "
                f"Sending empty payload, which might be invalid for most updates."
            )
            payload = {}
        self._send_command("update", payload)

    def remove(self):
        """Removes this component instance from the Sidekick UI and cleans up resources.

        Performs:
        1.  Unregisters message handlers for this instance.
        2.  Resets its specific user-defined callbacks (via `_reset_specific_callbacks()`).
        3.  Sends a 'remove' command to the Sidekick UI to delete the visual element.

        Important:
            After calling `remove()`, this component object should be considered
            inactive. Further method calls may fail or have no effect.
            If this component is a container (like `Row` or `Column`), the Sidekick UI
            is responsible for recursively removing its child components.

        Raises:
            SidekickConnectionError (or subclass): Can be raised by the
                underlying `_send_command` if sending the 'remove' command fails.
                Local cleanup will still be attempted.

        Example:
            >>> my_label = sidekick.Label("Temporary Message")
            >>> # ... use the label ...
            >>> my_label.remove() # Removes the label from the Sidekick panel
        """
        logger.info(
            f"Requesting removal of component '{self.component_type}' with id '{self.target_id}'."
        )

        connection.unregister_message_handler(self.target_id)
        self._error_callback = None
        self._reset_specific_callbacks()

        try:
             self._send_command("remove", payload=None)
        except SidekickConnectionError as e:
             logger.warning(
                f"Failed to send 'remove' command for component '{self.target_id}' "
                f"(it might remain visible in the UI): {e}. "
                f"Internal Python-side cleanup still performed."
            )

    def _reset_specific_callbacks(self):
        """Internal hook for subclasses to reset their unique callback attributes. (Internal).

        Called by `remove()`. Subclasses (like `Button`, `Textbox`) **must** override
        this if they store references to user-provided callbacks (e.g., `_click_callback`).
        The override should set these attributes to `None`.

        Example override in a `Button` subclass:
            ```python
            def _reset_specific_callbacks(self):
                super()._reset_specific_callbacks() # Good practice if base had its own
                self._click_callback = None
            ```
        """
        # Base implementation does nothing. Subclasses provide the actual logic.
        pass

    def __del__(self):
        """Attempt to unregister message handler upon garbage collection. (Fallback).

        Warning:
            Relying on `__del__` for cleanup is **strongly discouraged**. Python's
            garbage collection timing is unpredictable. **Always explicitly call
            `remove()`** on Sidekick components when finished to ensure proper
            cleanup in both Python and the Sidekick UI. This is a best-effort fallback.
        """
        try:
            if hasattr(connection, 'unregister_message_handler') and self.target_id:
                 connection.unregister_message_handler(self.target_id)
                 logger.debug(
                    f"BaseComponent __del__ attempting fallback unregistration "
                    f"for {self.component_type} id {self.target_id}"
                 )
        except Exception:
            pass # Suppress errors during __del__.