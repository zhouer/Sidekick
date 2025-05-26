"""Provides the foundational `Component` class for all Sidekick visual components.

This module defines the `Component` class, which serves as the base for all
visual elements in the Sidekick library (e.g., `Grid`, `Button`, `Canvas`).
It encapsulates common functionalities required for any Python object that
represents and interacts with a corresponding UI element in the Sidekick panel.

Key responsibilities managed by `Component`:

*   **Unique Identification:** Each component instance is assigned a unique
    `instance_id`. This ID is crucial for the Sidekick system to distinguish
    between different UI elements, especially when multiple components of the
    same type exist.
*   **Command Sending:** Components send commands (like "spawn" to create the UI
    element, or "update" to modify its state) to the Sidekick UI. This is done
    through internal helper methods that format messages according to the Sidekick
    protocol and delegate the sending to the central `ConnectionService`.
*   **Parenting and Layout:** Components can be nested within layout containers
    (like `Row` or `Column`). The `parent` attribute, specified during
    initialization, determines where the component appears in the UI hierarchy.
*   **Lifecycle Management:** Components have a `remove()` method to instruct the
    Sidekick UI to destroy the visual element and to clean up associated
    resources on the Python side.
*   **Error Handling:** Users can register an `on_error` callback to be notified if
    the Sidekick UI reports an error related to a specific component instance.
    These errors are delivered as structured `ErrorEvent` objects.
*   **Event Message Routing:** Each component instance registers itself with the
    `ConnectionService`. When the UI sends back events (e.g., a button click)
    or error messages, the `ConnectionService` routes these messages to the
    `_internal_message_handler` of the correct Python `Component` object.

Note:
    While `Component` is fundamental, users of the Sidekick library will typically
    not instantiate `Component` directly. Instead, they will create instances of
    its more specialized subclasses like `sidekick.Grid`, `sidekick.Console`, etc.
"""

import asyncio
from typing import Optional, Dict, Any, Callable, Union, Coroutine

from . import logger
from . import connection as sidekick_connection_module # Alias for clarity
from .exceptions import SidekickConnectionError
from .utils import generate_unique_id
from .events import ErrorEvent, BaseSidekickEvent


class Component:
    """Base class for all Sidekick component interface classes.

    This class manages the fundamental aspects of a Sidekick component, including
    its unique identification, its relationship with parent containers, sending
    commands to the UI (via the central `ConnectionService`), and routing
    incoming messages (events or errors) from the UI back to the component.

    Attributes:
        component_type (str): A string identifying the type of Sidekick component
            (e.g., "grid", "button"), as defined in the communication protocol.
        instance_id (str): The unique identifier for this component instance.
            This ID is used in protocol messages to target this specific component
            in the Sidekick UI.
    """
    def __init__(
        self,
        component_type: str,
        payload: Optional[Dict[str, Any]] = None,
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_error: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
    ):
        """Initializes the base component and sends a "spawn" command to the UI.

        This constructor is called by subclasses (e.g., `Grid()`, `Button()`).
        It performs several critical setup steps:

        1.  **ID Assignment:** A unique `instance_id` is determined. If the user
            provides one, it's used; otherwise, a new ID is auto-generated.
        2.  **Handler Registration:** The component registers an internal message
            handler (`_internal_message_handler`) with the `ConnectionService`.
            This registration allows the `ConnectionService` to route incoming
            UI messages (events or errors specific to this component) back to this
            Python object. This step also serves as a check for duplicate `instance_id`s.
        3.  **Payload Preparation:** The initial configuration data (`payload`) and
            any parent information are assembled into a "spawn" message payload.
        4.  **Spawn Command:** A "spawn" command is sent to the Sidekick UI via the
            `ConnectionService`. This instructs the UI to create and display the
            new visual element.
            *Important:* The first time any component sends such a command, it
            implicitly triggers the `ConnectionService` to activate its connection
            to a Sidekick server (local or remote, as determined by `ServerConnector`).
        5.  **Error Callback:** If an `on_error` callback function is provided, it's
            registered to handle UI-reported errors for this component.

        Args:
            component_type (str): The internal type name of the component,
                matching the `component` field in the Sidekick protocol
                (e.g., "grid", "button").
            payload (Optional[Dict[str, Any]]): A dictionary containing initial
                configuration data specific to the component type. This data is
                sent to the UI as part of the "spawn" command.
            instance_id (Optional[str]): An optional, user-defined unique
                identifier for this component. If `None`, an ID will be
                auto-generated. If provided, it must be unique across all
                Sidekick components in the current session.
            parent (Optional[Union['Component', str]]): The parent container
                component (e.g., a `sidekick.Row` or `sidekick.Column` instance)
                or its string `instance_id`. This determines where the new
                component is placed in the UI layout. If `None`, the component
                is added to the default top-level area of the Sidekick panel.
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): An optional callback
                function. If the Sidekick UI sends an error message related to
                this component, this function will be called with an `ErrorEvent`
                object. The callback can be a regular function or a coroutine function (async def).

        Raises:
            SidekickConnectionError: If the `ConnectionService` fails to establish
                a connection to any Sidekick server during the implicit activation
                triggered by the initial "spawn" command.
            ValueError: If the provided `instance_id` is invalid (e.g., empty)
                        or if the `ConnectionService` detects a duplicate `instance_id`.
            TypeError: If `parent` is not a `Component` instance, a string ID,
                       or `None`, or if `on_error` is provided but is not a
                       callable function.
        """
        self.component_type = component_type
        self._error_callback: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None # Init before potential use

        # --- Instance ID Assignment ---
        final_instance_id: str
        if instance_id is not None and isinstance(instance_id, str):
            processed_id = instance_id.strip()
            if not processed_id:
                # Providing an empty or whitespace-only ID is invalid.
                msg = (f"User-provided instance_id for component type '{component_type}' "
                       f"cannot be empty or consist only of whitespace.")
                logger.error(msg)
                raise ValueError(msg)
            final_instance_id = processed_id
        else:
            # Auto-generate a unique ID if none is provided.
            final_instance_id = generate_unique_id(component_type)
        self.instance_id = final_instance_id # Assign to self attribute for public access

        # --- Register with ConnectionService ---
        # The `ConnectionService` (via `sidekick_connection_module`) handles mapping
        # this `instance_id` to this component's `_internal_message_handler`.
        # It will raise a ValueError if the `instance_id` is already in use.
        try:
            sidekick_connection_module.register_message_handler(
                self.instance_id, self._internal_message_handler
            )
        except ValueError as e_id_dup: # Typically indicates a duplicate instance_id
            logger.error(
                f"Failed to initialize component (type: {component_type}, "
                f"intended ID: '{self.instance_id}'): {e_id_dup}. "
                "Instance ID might be a duplicate."
            )
            raise # Re-raise the ValueError to inform the user

        # --- Prepare Spawn Payload ---
        # Start with a copy of the provided payload or an empty dict.
        final_spawn_payload = payload.copy() if payload else {}
        parent_id_to_send: Optional[str] = None

        if parent is not None:
            if isinstance(parent, Component):
                parent_id_to_send = parent.instance_id
            elif isinstance(parent, str):
                parent_id_to_send = parent.strip() # Allow string ID for parent, remove whitespace
            else:
                # Invalid parent type. Attempt to unregister the handler before raising.
                try: sidekick_connection_module.unregister_message_handler(self.instance_id)
                except Exception: pass # Ignore errors during this cleanup attempt
                msg = (f"The 'parent' argument for component '{self.component_type}' "
                       f"(ID: '{self.instance_id}') must be another Sidekick Component instance, "
                       f"its string instance_id, or None. Got type: {type(parent).__name__}.")
                logger.error(msg)
                raise TypeError(msg)

            if not parent_id_to_send: # Check if string ID was empty after strip
                try: sidekick_connection_module.unregister_message_handler(self.instance_id)
                except Exception: pass
                msg = (f"Parent ID string for component '{self.component_type}' "
                       f"(ID: '{self.instance_id}') cannot be empty.")
                logger.error(msg)
                raise ValueError(msg)
            # Add parent ID to the payload if a valid parent is specified.
            final_spawn_payload["parent"] = parent_id_to_send

        parent_display = parent_id_to_send if parent_id_to_send else "root (default)"
        logger.debug(
            f"Prepared 'spawn' command for component '{self.component_type}' "
            f"(ID: '{self.instance_id}') with parent '{parent_display}'. "
            f"Payload keys: {list(final_spawn_payload.keys())}"
        )

        # --- Send Spawn Command ---
        # This call to _send_command (which uses sidekick_connection_module.send_message)
        # will implicitly trigger ConnectionService.activate_connection_internally()
        # if this is the first message being sent. That activation now involves ServerConnector.
        try:
            self._send_command("spawn", final_spawn_payload)
        except SidekickConnectionError as e_conn:
            # If connection fails during the very first component's spawn.
            logger.error(
                f"A connection error occurred during the 'spawn' of component "
                f"'{self.component_type}' (ID: '{self.instance_id}'): {e_conn}. "
                "This often means Sidekick couldn't connect to any server. "
                "Unregistering handler as spawn failed."
            )
            # Attempt to clean up the handler registration.
            try:
                sidekick_connection_module.unregister_message_handler(self.instance_id)
            except Exception as e_unreg: # pragma: no cover
                logger.warning(
                    f"An error occurred while trying to unregister the message handler for "
                    f"'{self.instance_id}' after its spawn failed: {e_unreg}"
                )
            raise # Re-raise the original connection error to the user.
        except Exception as e_other_spawn: # pragma: no cover
            # Catch other unexpected errors during spawn (e.g., programming error in payload prep).
            logger.exception(
                f"An unexpected error occurred during the 'spawn' of component "
                f"'{self.component_type}' (ID: '{self.instance_id}'): {e_other_spawn}. "
                "Attempting to unregister handler."
            )
            try:
                sidekick_connection_module.unregister_message_handler(self.instance_id)
            except Exception: pass # Best effort cleanup for unexpected errors.
            raise # Re-raise the unexpected error.


        # --- Register Error Callback (if provided by user) ---
        if on_error is not None:
            self.on_error(on_error) # Use the public method for type checking and logging

        logger.info(
            f"Successfully initialized component: type='{self.component_type}', "
            f"ID='{self.instance_id}', parent='{parent_display}'."
        )

    def _invoke_callback(
        self,
        callback: Optional[Callable[[BaseSidekickEvent], Union[Any, Coroutine[Any, Any, Any]]]],
        event_object: BaseSidekickEvent
    ) -> None:
        """Internal helper to invoke a user-provided callback (sync or async).

        This method safely executes callbacks registered by users for various events
        (e.g., clicks, submissions, errors). It handles both synchronous functions and
        asynchronous coroutines appropriately:

        - For regular synchronous functions: Calls the function directly and returns
          after completion.
        - For asynchronous coroutine functions: Submits the coroutine to the Sidekick
          connection module's task system for execution without blocking. This allows
          async callbacks to perform I/O operations or other async tasks.

        All exceptions that might occur during callback invocation are caught and logged,
        preventing user-provided callback errors from disrupting the component's operation.

        Args:
            callback (Optional[Callable[[BaseSidekickEvent], Union[Any, Coroutine[Any, Any, Any]]]]): 
                The callback function to invoke. Can be a regular function, a coroutine function,
                or None. If None, this method returns immediately.
            event_object (BaseSidekickEvent): The event object to pass to the callback.
                This contains information about the event that triggered the callback,
                such as the component's instance_id, the event type, and any event-specific
                data.
        """
        if not callback:
            return

        try:
            if asyncio.iscoroutinefunction(callback):
                coro_obj = callback(event_object)
                sidekick_connection_module.submit_task(coro_obj)
                logger.debug(f"Component '{self.instance_id}': Submitted async callback for event '{event_object.type}'.")
            else:
                callback(event_object)
                logger.debug(f"Component '{self.instance_id}': Invoked sync callback for event '{event_object.type}'.")
        except Exception as e:
            logger.exception(
                f"Error occurred preparing or invoking callback for component '{self.instance_id}' "
                f"for event type '{event_object.type}': {e}"
            )

    def _internal_message_handler(self, message: Dict[str, Any]) -> None:
        """Handles incoming messages (events/errors) for this component instance.

        This method is registered with the `ConnectionService` during component
        initialization. The `ConnectionService` calls this method when it receives
        a message from the Sidekick UI that is specifically targeted at this
        component instance (identified by `message['src'] == self.instance_id`).

        The base implementation here processes "error" messages by constructing
        an `ErrorEvent` and invoking the user-registered `on_error` callback (if any).
        For "event" messages (like clicks or submits), this base method simply
        logs them. Component subclasses (e.g., `Button`, `Grid`, `Textbox`)
        override this method to parse their specific event payloads and invoke
        their respective user-defined event callbacks (e.g., `on_click`, `on_submit`).

        Args:
            message (Dict[str, Any]): The raw message dictionary received from
                the Sidekick UI. This dictionary adheres to the structure defined
                in the Sidekick communication protocol.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload can be None or absent

        if msg_type == "error":
            # Extract error message from payload; provide a default if missing.
            error_message_str = "An unknown error occurred in the Sidekick UI."
            if payload and isinstance(payload.get("message"), str):
                error_message_str = payload["message"]
            else:
                logger.warning(
                    f"Component '{self.component_type}' (ID: '{self.instance_id}') "
                    f"received an 'error' message with missing or invalid payload: {payload}"
                )

            logger.error(
                f"Component '{self.component_type}' (ID: '{self.instance_id}') "
                f"received an error from the UI: \"{error_message_str}\""
            )

            error_event = ErrorEvent(
                instance_id=self.instance_id,
                type="error",  # Standardized event type for errors
                message=error_message_str,
            )
            self._invoke_callback(self._error_callback, error_event)
        elif msg_type == "event":
            # Base Component class does not handle specific UI interaction events by default.
            # Subclasses (like Button, Grid) override this method to process their events.
            logger.debug(
                f"Component '{self.component_type}' (ID: '{self.instance_id}') "
                f"received an 'event' message. Payload: {payload}. "
                "This event type is not handled by the base Component class; "
                "subclasses should override _internal_message_handler if they expect specific events."
            )
        else: # pragma: no cover
            # This case should ideally not be reached if the UI adheres to the protocol.
            logger.warning(
                f"Component '{self.component_type}' (ID: '{self.instance_id}') "
                f"received a message with an unexpected type: '{msg_type}'. Full message: {message}"
            )

    def on_error(self, callback: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]) -> None:
        """Registers a function to handle UI error messages for this component.

        If the Sidekick UI encounters an error specifically related to this
        component instance (e.g., while trying to render it or process an update
        for it), it may send an "error" message back to the Python script.
        This method allows you to define a Python function that will be called
        when such an error is received.

        The callback function will receive an `ErrorEvent` object, which contains
        the `instance_id` of this component, the event `type` (always "error"),
        and a `message` string describing the error.

        Args:
            callback (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): The function to call
                when an error message for this component is received from the UI.
                It must accept one `ErrorEvent` argument. The callback can be a regular
                function or a coroutine function (async def). Pass `None` to remove
                any previously registered error callback.

        Raises:
            TypeError: If `callback` is provided but is not a callable function or `None`.
        """
        if callback is not None and not callable(callback):
            raise TypeError(
                "The on_error callback must be a callable function that accepts "
                "one ErrorEvent argument, or None to clear the callback."
            )
        logger.info(
            f"Setting on_error callback for component '{self.component_type}' (ID: '{self.instance_id}')."
        )
        self._error_callback = callback

    def _send_command(self, msg_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Internal helper to construct and send a command message.

        This method formats a message according to the Sidekick protocol (including
        this component's type and instance ID) and uses the `sidekick.connection.send_message()`
        function to transmit it. The `connection.send_message()` function, in turn,
        delegates to the active `ConnectionService`.

        Args:
            msg_type (str): The type of command, as defined in the protocol
                (e.g., "spawn", "update", "remove").
            payload (Optional[Dict[str, Any]]): The data associated with the command.
                For "spawn", this is initial configuration. For "update", it typically
                contains an "action" and "options". For "remove", it's usually `None`.

        Raises:
            SidekickConnectionError: If `sidekick.connection.send_message()` fails
                (e.g., if the `ConnectionService` is not active or encounters
                an error during sending).
        """
        message: Dict[str, Any] = {
            "id": 0, # Protocol field, reserved for future use (currently 0).
            "component": self.component_type,
            "type": msg_type,
            "target": self.instance_id, # Target this specific component instance in the UI.
        }
        if payload is not None:
            message["payload"] = payload

        logger.debug(
            f"Component '{self.component_type}' (ID: '{self.instance_id}') sending command: "
            f"type='{msg_type}', payload_keys={list(payload.keys()) if payload else 'None'}"
        )
        # Delegates to the module-level send_message in connection.py, which
        # then calls ConnectionService.send_message_internally().
        sidekick_connection_module.send_message(message)

    def _send_update(self, payload: Dict[str, Any]) -> None:
        """Convenience method for sending an 'update' command for this component.

        Update commands instruct the UI to modify an existing component instance.
        The structure of the `payload` is critical and defined by the Sidekick protocol
        for each component type and action.

        Args:
            payload (Dict[str, Any]): The payload for the "update" command.
                According to the protocol, this dictionary **must** contain an "action"
                key (e.g., "setText", "setColor") and an "options" key whose value
                is a dictionary of action-specific parameters.

        Raises:
            SidekickConnectionError: If sending the command fails.
            ValueError: If the provided `payload` is not a dictionary or is missing
                        the required "action" key (this is a basic validation;
                        the UI will perform more specific payload validation).
        """
        if not isinstance(payload, dict):
            # This indicates a programming error in the component's subclass.
            err_msg = (f"Component '{self.component_type}' (ID: '{self.instance_id}') "
                       f"_send_update was called with an invalid payload type "
                       f"'{type(payload).__name__}'. Expected a dictionary.")
            logger.error(err_msg)
            raise ValueError(err_msg)
        if "action" not in payload:
            # Also a programming error in the component's subclass.
            err_msg = (f"Component '{self.component_type}' (ID: '{self.instance_id}') "
                       f"_send_update payload is missing the required 'action' key. "
                       f"Payload received: {payload}")
            logger.error(err_msg)
            raise ValueError(err_msg)
        self._send_command("update", payload)

    def remove(self) -> None:
        """Removes this component from the Sidekick UI and cleans up local resources.

        This method performs two main actions:
        1.  Sends a "remove" command to the Sidekick UI, instructing it to delete
            the visual element associated with this component instance.
        2.  On the Python side, it unregisters the component's message handler
            from the `ConnectionService` and clears any registered callbacks
            (like `on_error` and any subclass-specific callbacks via
            `_reset_specific_callbacks`).

        After calling `remove()`, this component instance should generally not be
        used further, as it will no longer be synchronized with the UI and
        cannot receive events.
        """
        logger.info(
            f"Requesting removal of component '{self.component_type}' (ID: '{self.instance_id}')."
        )
        # Try to unregister the message handler first. This is important even if
        # sending the "remove" command to the UI fails (e.g., due to connection issues),
        # to prevent a disconnected UI from still trying to send messages to a
        # Python object that considers itself removed.
        try:
            sidekick_connection_module.unregister_message_handler(self.instance_id)
        except Exception as e_unreg: # pragma: no cover
             # Log but don't stop the removal process.
             logger.warning(
                f"An error occurred while unregistering the message handler for component "
                f"'{self.component_type}' (ID: '{self.instance_id}') during its removal: {e_unreg}"
            )

        # Reset callbacks to None. This helps with garbage collection by breaking
        # potential reference cycles and prevents callbacks from being invoked on a
        # component that is logically removed.
        self._error_callback = None
        self._reset_specific_callbacks() # Hook for subclasses to clear their specific callbacks.

        # Attempt to send the "remove" command to the UI.
        try:
             # According to the protocol, the "remove" command typically has no payload.
             self._send_command("remove", payload=None)
        except SidekickConnectionError as e_remove_conn: # pragma: no cover
             # If sending the command fails (e.g., connection is down), log a warning.
             # The component is already considered removed from the Python library's perspective.
             logger.warning(
                f"Failed to send the 'remove' command for component '{self.instance_id}' "
                f"to the Sidekick UI. The UI might not reflect this removal if the "
                f"connection is currently down. Error: {e_remove_conn}."
            )
        except Exception as e_remove_other: # pragma: no cover
             # Catch any other unexpected errors during the send.
             logger.exception(
                f"An unexpected error occurred while sending the 'remove' command "
                f"for component '{self.instance_id}': {e_remove_other}"
            )


    def _reset_specific_callbacks(self) -> None:
        """Internal hook for subclasses to reset their unique callback attributes.

        This method is called as part of the `component.remove()` process.
        Subclasses that define their own specific callbacks (e.g., a Button's
        `_click_callback` or a Grid's `_click_callback`) should override this
        method. In their override, they should set these callback attributes
        to `None`.

        This practice is important for:
        -   Preventing callbacks from being invoked on a component that has been removed.
        -   Helping Python's garbage collector by breaking potential reference cycles
            that might otherwise keep the component object (and its callbacks) alive
            unnecessarily.
        """
        # The base Component class itself only has `_error_callback`, which is
        # reset directly in the `remove()` method. So, this base implementation
        # does nothing. Subclasses add their specific logic here.
        pass

    def __del__(self) -> None:
        """Fallback attempt to unregister the message handler upon garbage collection.

        **Warning:** It is **strongly recommended** to explicitly call the
        `component.remove()` method when a Sidekick component is no longer needed.
        Relying on `__del__` for cleanup in Python has several caveats:
        -   The timing of `__del__` execution is not guaranteed and can be unpredictable.
        -   `__del__` might not be called at all if the object is part of a reference cycle
            that the garbage collector cannot break.
        -   Errors raised within `__del__` are often ignored and can be difficult to debug.
        -   During interpreter shutdown, the state of modules and global variables
            (like those in `sidekick_connection_module`) can be unreliable.

        This `__del__` method provides a **best-effort** attempt to unregister the
        component's message handler from the `ConnectionService` if `remove()`
        was not explicitly called. This is a defensive measure to reduce potential
        issues but should not be the primary cleanup mechanism.
        """
        try:
            # Perform checks to ensure critical attributes and modules are still accessible,
            # as __del__ can be called in various states of interpreter shutdown.
            if hasattr(sidekick_connection_module, 'unregister_message_handler') and \
               hasattr(self, 'instance_id') and self.instance_id:

                # Logging from __del__ can be problematic if the logging system
                # itself is being torn down. Keep it minimal or conditional.
                # logger.debug(
                #     f"Component __del__ attempting fallback unregistration for "
                #     f"{getattr(self, 'component_type', 'UnknownComponentType')} "
                #     f"(ID: {self.instance_id}). Explicit .remove() is strongly preferred."
                # )
                sidekick_connection_module.unregister_message_handler(self.instance_id)
        except Exception: # pragma: no cover
            # PEP 442 recommends that __del__ methods suppress all exceptions,
            # as errors here are printed to stderr and can be confusing.
            pass
