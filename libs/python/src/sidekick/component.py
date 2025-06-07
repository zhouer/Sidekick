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
    The sending of the initial "spawn" command is non-blocking; the command is
    queued if the connection to the Sidekick service is not yet active.
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
from .exceptions import SidekickConnectionError, SidekickDisconnectedError
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

        1.  **ID Assignment:** A unique `instance_id` is determined.
        2.  **Handler Registration:** Registers an internal message handler with the
            `ConnectionService` for this component's `instance_id`.
        3.  **Payload Preparation:** Assembles initial configuration and parent
            information into a "spawn" message payload.
        4.  **Spawn Command Scheduling:** Sends a "spawn" command to the Sidekick UI
            via the `ConnectionService`. This operation is **non-blocking**.
            The command is queued if the Sidekick service is not yet active.
            The implicit activation of the `ConnectionService` (if this is the
            first component) is also non-blocking.
        5.  **Error Callback Registration:** Registers the `on_error` callback if provided.

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
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]):
                An optional callback function. If the Sidekick UI sends an error
                message related to this component, this function will be called
                with an `ErrorEvent` object. The callback can be a regular
                function or a coroutine function (`async def`).

        Raises:
            ValueError: If the provided `instance_id` is invalid (e.g., empty)
                        or if the `ConnectionService` detects a duplicate `instance_id`.
            TypeError: If `parent` is not a `Component` instance, a string ID,
                       or `None`, or if `on_error` is provided but is not a
                       callable function.
            SidekickDisconnectedError: If `send_message` is called (internally by `_send_command`)
                                       when the service is in a state where messages cannot be
                                       queued or sent (e.g., FAILED, SHUTTING_DOWN).
            SidekickConnectionError: While direct connection errors are less likely to
                                     be raised by `__init__` itself due to its non-blocking
                                     nature, subsequent operations or synchronous wait points
                                     like `sidekick.wait_for_connection()` may raise this if
                                     the underlying asynchronous activation fails.
        """
        self.component_type = component_type
        self._error_callback: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None

        # --- Instance ID Assignment ---
        final_instance_id: str
        if instance_id is not None and isinstance(instance_id, str):
            processed_id = instance_id.strip()
            if not processed_id:
                msg = (f"User-provided instance_id for component type '{component_type}' "
                       f"cannot be empty or consist only of whitespace.")
                logger.error(msg)
                raise ValueError(msg)
            final_instance_id = processed_id
        else:
            final_instance_id = generate_unique_id(component_type)
        self.instance_id = final_instance_id

        # --- Register with ConnectionService ---
        try:
            sidekick_connection_module.register_message_handler(
                self.instance_id, self._internal_message_handler
            )
        except ValueError as e_id_dup:
            logger.error(
                f"Failed to initialize component (type: {component_type}, "
                f"intended ID: '{self.instance_id}'): {e_id_dup}. "
                "Instance ID might be a duplicate."
            )
            raise

        # --- Prepare Spawn Payload ---
        final_spawn_payload = payload.copy() if payload else {}
        parent_id_to_send: Optional[str] = None

        if parent is not None:
            if isinstance(parent, Component):
                parent_id_to_send = parent.instance_id
            elif isinstance(parent, str):
                parent_id_to_send = parent.strip()
            else:
                # Attempt to unregister the handler before raising TypeError, as registration happened.
                try: sidekick_connection_module.unregister_message_handler(self.instance_id)
                except Exception: pass # Best effort cleanup
                msg = (f"The 'parent' argument for component '{self.component_type}' "
                       f"(ID: '{self.instance_id}') must be another Sidekick Component instance, "
                       f"its string instance_id, or None. Got type: {type(parent).__name__}.")
                logger.error(msg)
                raise TypeError(msg)

            if not parent_id_to_send: # Check if string ID was empty after strip
                try: sidekick_connection_module.unregister_message_handler(self.instance_id)
                except Exception: pass # Best effort cleanup
                msg = (f"Parent ID string for component '{self.component_type}' "
                       f"(ID: '{self.instance_id}') cannot be empty.")
                logger.error(msg)
                raise ValueError(msg)
            final_spawn_payload["parent"] = parent_id_to_send

        parent_display = parent_id_to_send if parent_id_to_send else "root (default)"
        logger.debug(
            f"Prepared 'spawn' command for component '{self.component_type}' "
            f"(ID: '{self.instance_id}') with parent '{parent_display}'. "
            f"Payload keys: {list(final_spawn_payload.keys())}"
        )

        # --- Send Spawn Command (Non-Blocking) ---
        try:
            self._send_command("spawn", final_spawn_payload)
        except (SidekickDisconnectedError, SidekickConnectionError) as e_send:
            logger.error(
                f"Failed to send 'spawn' command for component "
                f"'{self.component_type}' (ID: '{self.instance_id}'): {e_send}. "
                "Unregistering handler."
            )
            try:
                sidekick_connection_module.unregister_message_handler(self.instance_id)
            except Exception as e_unreg: # pragma: no cover
                logger.warning(
                    f"Error unregistering message handler for '{self.instance_id}' "
                    f"after its spawn command failed: {e_unreg}"
                )
            raise
        except Exception as e_other_spawn: # pragma: no cover
            logger.exception(
                f"An unexpected error occurred during the 'spawn' of component "
                f"'{self.component_type}' (ID: '{self.instance_id}'): {e_other_spawn}. "
                "Attempting to unregister handler."
            )
            try:
                sidekick_connection_module.unregister_message_handler(self.instance_id)
            except Exception: pass
            raise

        # --- Register Error Callback (if provided by user) ---
        if on_error is not None:
            self.on_error(on_error) # Use public method for type checking and logging

        logger.info(
            f"Successfully scheduled initialization for component: type='{self.component_type}', "
            f"ID='{self.instance_id}', parent='{parent_display}'."
        )

    def _invoke_callback(
        self,
        callback: Optional[Callable[[BaseSidekickEvent], Union[Any, Coroutine[Any, Any, Any]]]],
        event_object: BaseSidekickEvent
    ) -> None:
        """Internal helper to invoke a user-provided callback (sync or async).

        Safely executes callbacks, handling both synchronous functions and
        asynchronous coroutines. Coroutines are submitted to Sidekick's
        managed task system. Exceptions during callback invocation are caught
        and logged.

        Args:
            callback (Optional[Callable[[BaseSidekickEvent], Union[Any, Coroutine[Any, Any, Any]]]]):
                The callback function to invoke. Can be a regular
                function, a coroutine function, or None.
            event_object (BaseSidekickEvent): The event object to pass to the callback, containing
                details about the event.
        """
        if not callback:
            return

        try:
            if asyncio.iscoroutinefunction(callback):
                coro_obj = callback(event_object) # type: ignore [operator] # Known to be coroutine if check passes
                sidekick_connection_module.submit_task(coro_obj)
                logger.debug(
                    f"Component '{self.instance_id}': Submitted async callback "
                    f"for event '{event_object.type}' to TaskManager."
                )
            else:
                callback(event_object)
                logger.debug(
                    f"Component '{self.instance_id}': Invoked sync callback "
                    f"for event '{event_object.type}'."
                )
        except Exception as e: # pragma: no cover
            logger.exception(
                f"Error occurred while preparing or invoking callback for component '{self.instance_id}' "
                f"for event type '{event_object.type}': {e}"
            )

    def _internal_message_handler(self, message: Dict[str, Any]) -> None:
        """Handles incoming messages (events/errors) for this component instance.

        This method is registered with the `ConnectionService` and is called
        when a UI message targeted at this component's `instance_id` is received.
        The base implementation processes "error" messages by invoking the
        `on_error` callback. Subclasses override this to handle specific UI
        interaction events (e.g., "click", "submit").

        Args:
            message (Dict[str, Any]): The raw message dictionary from the
                Sidekick UI, structured according to the protocol.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "error":
            error_message_str = "An unknown error occurred in the Sidekick UI for this component."
            if payload and isinstance(payload.get("message"), str):
                error_message_str = payload["message"]
            else: # pragma: no cover
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
                type="error", # Standardized event type for errors
                message=error_message_str,
            )
            self._invoke_callback(self._error_callback, error_event)
        elif msg_type == "event":
            # Base Component class does not handle specific UI interaction events by default.
            # Subclasses (like Button, Grid) override this method to process their events.
            logger.debug(
                f"Component '{self.component_type}' (ID: '{self.instance_id}') "
                f"received an 'event' message. Payload: {payload}. "
                "Base Component class does not handle specific events; "
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

        If the Sidekick UI encounters an error related to this component instance,
        it may send an "error" message back. This method defines a Python
        function to be called when such an error is received.

        The callback receives an `ErrorEvent` object with `instance_id`,
        `type` ("error"), and a `message` string.

        Args:
            callback (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]):
                The function to call upon receiving an error.
                It must accept one `ErrorEvent` argument. Can be a regular
                function or a coroutine function (`async def`). Pass `None`
                to clear a previously registered callback.

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
        """Internal helper to construct and schedule a command message for sending.

        Formats a message (including component type and instance ID) and uses
        `sidekick.connection.send_message()` to transmit it. This function
        handles queuing if the `ConnectionService` is not yet active.

        Args:
            msg_type (str): The command type (e.g., "spawn", "update", "remove").
            payload (Optional[Dict[str, Any]]): Data for the command. For "spawn", initial config;
                for "update", an "action" and "options"; for "remove", usually `None`.

        Raises:
            SidekickDisconnectedError: If `connection.send_message()` determines
                                       the service cannot accept messages
                                       (e.g., FAILED or SHUTTING_DOWN).
            TypeError: If `payload` causes issues during JSON serialization (rare,
                       as `send_message` handles serialization).
        """
        message: Dict[str, Any] = {
            "id": 0, # Protocol field, reserved for future use.
            "component": self.component_type,
            "type": msg_type,
            "target": self.instance_id, # Target this specific component instance in the UI.
        }
        if payload is not None:
            message["payload"] = payload

        logger.debug(
            f"Component '{self.component_type}' (ID: '{self.instance_id}') scheduling command: "
            f"type='{msg_type}', payload_keys={list(payload.keys()) if payload else 'None'}"
        )
        # Delegates to the module-level send_message in connection.py,
        # which calls ConnectionService.send_message_internally().
        # This function may raise SidekickDisconnectedError.
        sidekick_connection_module.send_message(message)

    def _send_update(self, payload: Dict[str, Any]) -> None:
        """Convenience method for sending an 'update' command for this component.

        Update commands instruct the UI to modify an existing component instance.
        The `payload` structure is defined by the Sidekick protocol.

        Args:
            payload (Dict[str, Any]): The payload for the "update" command.
                According to the protocol, this dictionary **must** contain an "action"
                key (e.g., "setText", "setColor") and an "options" key whose value
                is a dictionary of action-specific parameters.

        Raises:
            SidekickDisconnectedError: If sending the command fails because the
                                       service cannot accept messages.
            ValueError: If `payload` is not a dict or missing "action" key
                        (internal programming error check).
        """
        if not isinstance(payload, dict): # pragma: no cover
            # This indicates a programming error in the component's subclass.
            err_msg = (f"Component '{self.component_type}' (ID: '{self.instance_id}') "
                       f"_send_update was called with an invalid payload type "
                       f"'{type(payload).__name__}'. Expected a dictionary.")
            logger.error(err_msg)
            raise ValueError(err_msg)
        if "action" not in payload: # pragma: no cover
            # Also a programming error in the component's subclass.
            err_msg = (f"Component '{self.component_type}' (ID: '{self.instance_id}') "
                       f"_send_update payload is missing the required 'action' key. "
                       f"Payload received: {payload}")
            logger.error(err_msg)
            raise ValueError(err_msg)
        self._send_command("update", payload)

    def remove(self) -> None:
        """Removes this component from the Sidekick UI and cleans up local resources.

        Sends a "remove" command to the UI and unregisters the component's
        message handler and callbacks on the Python side.
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
                f"An error occurred while unregistering message handler for component "
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
        except SidekickDisconnectedError as e_remove_conn: # pragma: no cover
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

        Warning:
            It is **strongly recommended** to explicitly call the
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
               hasattr(self, 'instance_id') and self.instance_id: # Ensure instance_id is valid

                # Minimal logging or conditional logging from __del__ is advised.
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
