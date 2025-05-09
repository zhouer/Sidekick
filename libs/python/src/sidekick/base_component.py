"""Provides the foundational `BaseComponent` class for all Sidekick visual components.

This component defines the common blueprint and core functionalities shared by all
the visual elements you create with Sidekick (like `Grid`, `Console`, `Canvas`,
`Label`, `Button`, `Textbox`, `Markdown`, `Row`, `Column`). Think of it as the
engine under the hood that handles essential tasks necessary for any Python object
representing a component in the Sidekick UI.

Key responsibilities managed by `BaseComponent`:

*   **Unique Identification:** Assigning or using a user-provided unique `instance_id`
    to each component instance, allowing Sidekick to distinguish between different
    elements.
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
*   **Error Handling:** Providing a way (`on_error()`, or via constructor) for
    users to register a callback function to handle potential error messages sent
    back *from* the Sidekick UI related to a specific component instance, via a
    structured `ErrorEvent` object.
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
from .events import ErrorEvent # Import the structured ErrorEvent
from typing import Optional, Dict, Any, Callable, Union

class BaseComponent:
    """Base class for all Sidekick component interface classes.

    This abstract class manages the fundamental setup, unique identification,
    parenting, and communication logic required for any Python object that
    represents and controls a visual component within the Sidekick UI panel.

    It ensures that when a component instance is created, the connection to Sidekick
    is established, a unique ID (either user-provided or auto-generated) is assigned
    and validated for uniqueness, parent information is processed, and the instance
    is registered to receive relevant messages (events, errors) from the UI.
    It provides standardized methods for sending commands (`spawn`, `update`, `remove`)
    and handling cleanup.

    Note:
        This class is designed for internal use by the library developers when
        creating new Sidekick component types. Users of the library should interact
        with the concrete subclasses (`sidekick.Grid`, `sidekick.Label`, etc.).

    Attributes:
        component_type (str): A string identifying the type of Sidekick component this
            class represents (e.g., "grid", "label"). This must match the type
            expected by the Sidekick UI component and defined in the communication
            protocol.
        instance_id (str): The unique identifier assigned to or provided for this
            specific component instance. This ID is crucial for routing commands
            and events, and for uniquely identifying the component within the
            Sidekick ecosystem for the current script run.
    """
    def __init__(
        self,
        component_type: str,
        payload: Optional[Dict[str, Any]] = None,
        instance_id: Optional[str] = None, # New: User-provided instance ID
        parent: Optional[Union['BaseComponent', str]] = None,
        on_error: Optional[Callable[[ErrorEvent], None]] = None, # Updated signature
    ):
        """Initializes the base component, setting up ID, parent, connection, and registration.

        This constructor is called automatically by the `__init__` method of
        subclasses (like `Button`, `Grid`, etc.) when you create a new component,
        for example: `my_label = sidekick.Label("Hello", instance_id="greeting")`.

        It performs several essential setup steps:

        1.  **Activates Connection:** Ensures the connection to the Sidekick UI panel
            is active. This is a **blocking call** the *first* time any Sidekick
            component is created in your script. It waits until the communication
            channel is established and the Sidekick UI is ready before proceeding.
        2.  **Assigns & Validates ID:**
            *   If an `instance_id` is provided by the user, it's used (after basic
                validation like stripping whitespace and checking for non-emptiness).
            *   If no `instance_id` is provided, a unique ID is automatically generated
                (e.g., "label-1").
            *   The chosen `instance_id` is then registered with the connection
                manager, which will **validate its uniqueness** across all active
                Sidekick components in the current script. If the ID is a duplicate,
                a `ValueError` will be raised, and component creation will fail.
        3.  **Registers Handler:** Sets up this component instance to receive messages
            (like error reports or specific events) from the Sidekick UI that are
            specifically meant for it, using its unique `instance_id`.
        4.  **Processes Parent:** If you specify a `parent` (like a `Row` or `Column`),
            this component will be visually placed inside that parent in the UI.
            Otherwise, it's added to the main Sidekick panel area (the "root" container).
        5.  **Spawns UI Element:** Sends a "spawn" command to the Sidekick UI,
            instructing it to create and display the corresponding visual element
            (e.g., a label, a button). The `payload` argument carries any initial
            configuration data needed by the UI (like the label's text). The component's
            `instance_id` is sent as the `"target"` in this command.
        6.  **Sets Error Handler:** If you provide an `on_error` function, it's
            registered so that your function will be called with an `ErrorEvent`
            object if an error related to this component occurs in the Sidekick UI.

        Args:
            component_type (str): The internal type name of the component (e.g., "grid",
                "label", "button"). This is used by the library and must match the
                type expected by the Sidekick UI.
            payload (Optional[Dict[str, Any]]): A dictionary containing initial
                configuration data for the UI component (e.g., grid dimensions,
                initial text for a label). Keys within this dictionary should
                generally conform to the `camelCase` convention required by the
                Sidekick communication protocol. Defaults to None or an empty dictionary.
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this component instance. If provided, it must be a non-empty string
                and must be unique among all Sidekick components created in the current
                script run. If `None` (default), a unique ID will be auto-generated.
            parent (Optional[Union['BaseComponent', str]]): The parent container for
                this component. Can be:
                - A Sidekick component instance (e.g., a `Row` or `Column` object).
                - A `str` representing the `instance_id` of an existing parent component.
                - `None` (default): The component will be added to the top-level
                  "root" container in the Sidekick UI.
            on_error (Optional[Callable[[ErrorEvent], None]]): A function to call if
                an error message related to this specific component is sent back
                from the Sidekick UI. The function should accept one `ErrorEvent`
                object as an argument. This is an alternative to calling
                `my_component.on_error(callback)` after creation. Defaults to `None`.

        Raises:
            SidekickConnectionError (or subclass): If `connection.activate_connection()`
                fails (e.g., cannot connect to the Sidekick server, or the UI
                panel doesn't respond in time).
            ValueError: If a user-provided `instance_id` is invalid (e.g., empty after
                        stripping whitespace) or if the final `instance_id` (user-provided
                        or auto-generated) is found to be a duplicate of an already
                        registered component ID.
            TypeError: If the `parent` argument is provided but is not a `BaseComponent`
                       instance, a string, or `None`. Also raised if `on_error` is
                       provided but is not a callable function.
        """
        # CRITICAL: Ensure the connection is active and ready before doing anything else.
        # This is a blocking call the first time any component is created.
        connection.activate_connection() # Raises SidekickConnectionError on failure.

        self.component_type = component_type
        self._error_callback: Optional[Callable[[ErrorEvent], None]] = None # Initialize before use

        # --- Instance ID Assignment and Validation ---
        final_instance_id: str
        if instance_id is not None and isinstance(instance_id, str):
            processed_id = instance_id.strip()
            if not processed_id:
                msg = (f"User-provided instance_id for component type '{component_type}' "
                       f"cannot be an empty string or only whitespace.")
                logger.error(msg)
                raise ValueError(msg)
            final_instance_id = processed_id
            logger.debug(f"Using user-provided instance_id: '{final_instance_id}' for {component_type}.")
        else:
            final_instance_id = generate_unique_id(component_type)
            logger.debug(f"Auto-generated instance_id: '{final_instance_id}' for {component_type}.")

        self.instance_id = final_instance_id # Store the chosen ID internally.

        # Register this instance's message handler with the connection manager.
        # This also performs uniqueness validation for self.instance_id.
        # If self.instance_id is a duplicate, connection.register_message_handler
        # will raise a ValueError.
        try:
            connection.register_message_handler(self.instance_id, self._internal_message_handler)
        except ValueError as e_id_dup:
            # Log the error specifically related to ID duplication.
            logger.error(
                f"Failed to initialize component (type: {component_type}, "
                f"attempted ID: '{self.instance_id}'): {e_id_dup}"
            )
            raise e_id_dup # Re-raise the ValueError for ID duplication.

        # Prepare the final payload for the 'spawn' command.
        # Start with a copy of the provided component-specific payload (if any).
        final_spawn_payload = payload.copy() if payload else {}

        # Process the parent argument and add it to the spawn payload if specified.
        parent_id_to_send: Optional[str] = None
        if parent is not None:
            if isinstance(parent, BaseComponent):
                parent_id_to_send = parent.instance_id # Use the parent's instance_id
            elif isinstance(parent, str):
                parent_id_to_send = parent # Assume it's a valid instance_id string
            else:
                # Invalid parent type provided.
                msg = (f"Parent for component '{self.instance_id}' (type: {component_type}) "
                       f"must be a Sidekick component instance, a string ID, or None. "
                       f"Received type: {type(parent).__name__}.")
                logger.error(msg)
                raise TypeError(msg)

            # If a parent was specified, its ID must be a non-empty string.
            if not parent_id_to_send: # Checks for empty string too
                msg = (f"Parent ID for component '{self.instance_id}' cannot be an empty string. "
                       f"If specifying a parent by ID, it must be a valid, non-empty instance_id. "
                       f"If parent was a BaseComponent, its instance_id was empty.")
                logger.error(msg)
                # This situation is likely a programming error.
                raise ValueError(msg)

            # Add the 'parent' key to the payload only if a valid parent ID was determined.
            # The protocol specifies that if 'parent' is omitted, it defaults to "root".
            final_spawn_payload["parent"] = parent_id_to_send

        # Send the 'spawn' command to the UI to create the visual element.
        # The command will use self.instance_id as the "target" in the message.
        self._send_command("spawn", final_spawn_payload)

        # Register the on_error callback if it was provided in the constructor.
        # This uses the public self.on_error() method which includes type checking.
        if on_error is not None:
            self.on_error(on_error)

        # Log initialization details, including the resolved parent.
        parent_display = parent_id_to_send if parent_id_to_send else "root (default)"
        logger.info(
            f"Initialized {self.component_type} component: id='{self.instance_id}', "
            f"parent='{parent_display}'."
        )

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages (events/errors) targeted at this component instance. (Internal).

        This method is called automatically by the `connection` component's background
        listener thread whenever a message arrives from the Sidekick UI where the
        message's `src` field matches this instance's `instance_id`.

        The base implementation specifically checks for messages with `type: "error"`.
        If found, it extracts the error message string from the payload, constructs
        an `ErrorEvent` object, and calls the user's registered `on_error` callback
        (if one exists).

        **Subclasses (like Grid, Button) MUST override this method** to add
        handling for their specific `type: "event"` messages (like clicks or text
        input). Overriding methods should typically call `super()._internal_message_handler(message)`
        at the end to ensure that the base error handling still occurs, or directly handle
        "error" type messages if they need custom error processing.

        Args:
            message (Dict[str, Any]): The raw message dictionary received from
                the Sidekick connection manager. Expected to follow the protocol
                structure (keys: 'type', 'component', 'src', 'payload'). Payload keys
                are expected to be `camelCase`.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload should contain camelCase keys.

        if msg_type == "error":
            error_message_str = "Unknown error message received from Sidekick UI."
            if payload and isinstance(payload.get("message"), str):
                error_message_str = payload["message"]
            logger.error(f"Component '{self.instance_id}' received error from Sidekick UI: {error_message_str}")

            if self._error_callback:
                try:
                    # Construct and pass the ErrorEvent object
                    error_event = ErrorEvent(
                        instance_id=self.instance_id,
                        type="error",
                        message=error_message_str,
                    )
                    self._error_callback(error_event)
                except Exception as e:
                    logger.exception(
                        f"Error occurred inside {self.component_type} "
                        f"'{self.instance_id}' on_error callback: {e}"
                    )
        elif msg_type == "event":
            # This base implementation doesn't handle specific events itself.
            # Subclasses should override this method to process their unique events
            # (e.g., a "click" event for a Button, or a "submit" event for a Textbox).
            # If a subclass doesn't handle an event, it will be logged here.
            logger.debug(
                f"BaseComponent received an 'event' for '{self.instance_id}' "
                f"that was not handled by a subclass: {payload}"
            )
            pass # Subclasses are responsible for handling specific events.
        else:
            logger.warning(
                f"Component '{self.instance_id}' received unexpected message type "
                f"'{msg_type}': {message}"
            )

    def on_error(self, callback: Optional[Callable[[ErrorEvent], None]]):
        """Registers a function to handle error messages from the Sidekick UI for this component.

        Occasionally, the Sidekick UI panel might encounter an issue while trying
        to process a command related to *this specific component instance*. In such
        cases, the UI might send an 'error' message back to your script.

        This method allows you to define a Python function (`callback`) that will
        be executed automatically when such an error message arrives for this component.
        The callback will receive an `ErrorEvent` object containing details about the
        error. You can also set this callback directly when creating the component using
        the `on_error` parameter in its constructor.

        Args:
            callback (Optional[Callable[[ErrorEvent], None]]): The function to call
                when an error message arrives. It should accept one argument:
                an `ErrorEvent` object, which has `instance_id`, `type` ("error"),
                and `message` (string) attributes.
                Pass `None` to remove a previously registered error handler.

        Raises:
            TypeError: If `callback` is not a callable function (or `None`).

        Example:
            >>> from sidekick.events import ErrorEvent
            >>>
            >>> def my_grid_error_reporter(event: ErrorEvent):
            ...     print(f"Oops! The grid '{event.instance_id}' reported an error: {event.message}")
            ...
            >>> # Option 1: Using the method
            >>> my_grid = sidekick.Grid(5, 5, instance_id="my-grid")
            >>> my_grid.on_error(my_grid_error_reporter)
            >>>
            >>> # Option 2: Using the constructor parameter
            >>> # my_other_grid = sidekick.Grid(3, 3, on_error=my_grid_error_reporter)
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_error callback must be a callable function or None.")
        logger.info(f"Setting on_error callback for component '{self.instance_id}'.")
        self._error_callback = callback

    def _send_command(self, msg_type: str, payload: Optional[Dict[str, Any]] = None):
        """Internal helper to construct and send a standard command message to Sidekick.

        This method builds the message dictionary according to the Sidekick
        communication protocol and uses `connection.send_message` to transmit it.
        It's used internally for "spawn" and "remove" commands. The component's
        `self.instance_id` is automatically used as the `"target"` field in the message.

        Note:
            Payload keys within `payload` should generally be `camelCase`. This method
            does not perform case conversion; that responsibility lies with callers
            (typically the `__init__` methods of component subclasses).

        Args:
            msg_type (str): The type of command (e.g., "spawn", "update", "remove").
            payload (Optional[Dict[str, Any]]): The data payload for the command.
                Keys should already be in `camelCase`. Defaults to None.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or if `connection.send_message` fails.
        """
        message: Dict[str, Any] = {
            "id": 0, # Reserved, currently always 0.
            "component": self.component_type,
            "type": msg_type,
            "target": self.instance_id, # Use self.instance_id as the target for the UI.
        }
        if payload is not None:
            message["payload"] = payload

        connection.send_message(message) # This can raise SidekickConnectionError

    def _send_update(self, payload: Dict[str, Any]):
        """Convenience method for sending an 'update' command. (Internal).

        A shortcut for `_send_command("update", payload)`. Used by component methods
        that modify an existing UI element (e.g., `label.text = "New"`,
        `grid.set_color(...)`). The component's `instance_id` is automatically included
        as the target.

        Note:
            The `payload` *must* include the component-specific `action` key
            (e.g., "setColor", "setText") and any `options` sub-dictionary
            with `camelCase` keys, as defined by the protocol for that action.
            The responsibility for correct `camelCase` formatting of `action` and
            `options` keys lies with the calling component method.

        Args:
            payload (Dict[str, Any]): The complete payload for the 'update' command,
                including the `action` and its `options` (with camelCase keys).

        Raises:
            SidekickConnectionError (or subclass): If connection or send fails.
        """
        if payload is None: # Should generally not be None for updates
            logger.warning(
                f"Component '{self.instance_id}' _send_update called with None payload. "
                f"Sending empty payload, which might be invalid for most updates."
            )
            payload = {} # Ensure payload is a dict, even if empty
        self._send_command("update", payload)

    def remove(self):
        """Removes this component instance from the Sidekick UI and cleans up resources.

        When you call `my_component.remove()`, this function performs several actions:
        1.  It stops listening for messages specifically for this component by unregistering
            its `instance_id` from the connection manager.
        2.  It clears any custom callback functions you might have set (like `on_error`,
            or `on_click` for a button).
        3.  It sends a 'remove' command to the Sidekick UI, instructing it to delete
            the visual element from the panel. The component's `instance_id` is used
            to target the correct element in the UI.

        Important:
            After calling `remove()`, this component object should be considered
            inactive. Further method calls on it may fail or have no effect.
            If this component is a container (like `Row` or `Column`), the Sidekick UI
            is responsible for recursively removing its child components as well.

        Raises:
            SidekickConnectionError (or subclass): Can be raised by the
                underlying `_send_command` if sending the 'remove' command fails.
                However, the Python-side cleanup (unregistering handlers, clearing
                callbacks) will still be attempted.

        Example:
            >>> my_label = sidekick.Label("Temporary Message", instance_id="temp-msg")
            >>> # ... (your script uses the label for a while) ...
            >>> my_label.remove() # This makes the label disappear from the Sidekick panel
        """
        logger.info(
            f"Requesting removal of component '{self.component_type}' with id '{self.instance_id}'."
        )

        # Stop listening for messages for this specific component instance.
        connection.unregister_message_handler(self.instance_id)

        # Clear any registered error callback for this component.
        self._error_callback = None

        # Call a hook for subclasses to clear their own specific callbacks (e.g., _click_callback).
        self._reset_specific_callbacks()

        try:
             # Send the 'remove' command to the UI. No payload is needed for removal.
             # self.instance_id will be used as the "target" in _send_command.
             self._send_command("remove", payload=None)
        except SidekickConnectionError as e:
             # Log a warning if the command fails, but Python-side cleanup is done.
             logger.warning(
                f"Failed to send 'remove' command for component '{self.instance_id}' "
                f"(it might remain visible in the UI): {e}. "
                f"Internal Python-side cleanup still performed."
            )
             # Depending on desired behavior, you might choose to re-raise 'e' here
             # or allow the script to continue if only the UI removal failed.
             # For now, we log and continue, as local cleanup is done.

    def _reset_specific_callbacks(self):
        """Internal hook for subclasses to reset their unique callback attributes. (Internal).

        This method is called by `remove()` before the component is fully removed.
        Subclasses (like `Button`, `Textbox`, `Grid`) that store references to
        user-provided callback functions (e.g., `_click_callback`, `_submit_callback`)
        **must** override this method. The override should set these specific
        callback attributes to `None` to help with garbage collection and prevent
        potential issues with stale references.

        Example override in a `Button` subclass:
            ```python
            def _reset_specific_callbacks(self):
                super()._reset_specific_callbacks() # Good practice if base also had its own
                self._click_callback = None
            ```
        The base implementation here does nothing, as `BaseComponent` itself only
        manages `_error_callback`, which is handled directly in `remove()`.
        """
        # Base implementation does nothing. Subclasses provide the actual logic
        # for their own event-specific callbacks.
        pass

    def __del__(self):
        """Attempt to unregister message handler upon garbage collection. (Fallback).

        Warning:
            Relying on `__del__` for cleanup is **strongly discouraged** in Python,
            as its execution is not guaranteed and can be unpredictable.
            **Always explicitly call `remove()`** on Sidekick components when you are
            finished with them. This ensures proper and timely cleanup in both your
            Python script and the Sidekick UI.

            This `__del__` method is provided as a last-resort, best-effort attempt
            to unregister the component's message handler if `remove()` was not called
            and the object is being garbage collected. It might help reduce resource
            leakage in some edge cases but should not be depended upon.
        """
        try:
            # Check if 'connection' module and 'unregister_message_handler' still exist
            # and if this instance has an 'instance_id'. This is to prevent errors
            # during interpreter shutdown when modules might be partially torn down.
            if hasattr(connection, 'unregister_message_handler') and hasattr(self, 'instance_id') and self.instance_id:
                 connection.unregister_message_handler(self.instance_id)
                 logger.debug(
                    f"BaseComponent __del__ attempting fallback unregistration "
                    f"for {getattr(self, 'component_type', 'UnknownComponentType')} "
                    f"id {self.instance_id}"
                 )
        except Exception:
            # Suppress any errors during __del__, as recommended by Python guidelines.
            # Errors in __del__ are often ignored or cause confusing warnings.
            pass