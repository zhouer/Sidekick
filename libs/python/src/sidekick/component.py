"""Provides the foundational `Component` class for all Sidekick visual components.

This component defines the common blueprint and core functionalities shared by all
the visual elements you create with Sidekick (like `Grid`, `Console`, `Canvas`,
`Label`, `Button`, `Textbox`, `Markdown`, `Row`, `Column`). Think of it as the
engine under the hood that handles essential tasks necessary for any Python object
representing a component in the Sidekick UI.

Key responsibilities managed by `Component`:

*   **Unique Identification:** Assigning or using a user-provided unique `instance_id`
    to each component instance, allowing Sidekick to distinguish between different
    elements.
*   **Command Sending:** Providing internal helper methods (`_send_command`,
    `_send_update`) for constructing and sending standardized instruction messages
    (like "create this grid", "update that cell", "remove this console") over the
    communication channel according to the Sidekick protocol. This now uses the
    central `ConnectionService`.
*   **Parenting:** Allowing components to be nested within container components
    (like `Row` or `Column`) by specifying a `parent` during initialization.
*   **Removal:** Offering a standard `remove()` method to destroy the visual element
    in the Sidekick UI and clean up associated resources.
*   **Error Handling:** Providing a way (`on_error()`, or via constructor) for
    users to register a callback function to handle potential error messages sent
    back *from* the Sidekick UI related to a specific component instance, via a
    structured `ErrorEvent` object.
*   **Message Routing:** Registering each instance with the `ConnectionService` so
    that incoming events (like clicks) or errors from the UI can be routed back
    to the correct Python object's internal handler (`_internal_message_handler`).

Note:
    You will typically **not** use `Component` directly in your scripts. Instead,
    you'll instantiate its subclasses like `sidekick.Grid`, `sidekick.Console`, etc.
"""

import logging # Changed from "from . import logger" to direct import
from typing import Optional, Dict, Any, Callable, Union

# Import ConnectionService's public API functions (which use the singleton)
from . import logger
from . import connection as sidekick_connection_module
from .errors import SidekickConnectionError # Still relevant if send_message fails
from .utils import generate_unique_id
from .events import ErrorEvent


class Component:
    """Base class for all Sidekick component interface classes.

    Manages unique identification, parenting, command sending (via ConnectionService),
    and message routing for Sidekick UI components.

    Attributes:
        component_type (str): A string identifying the type of Sidekick component.
        instance_id (str): The unique identifier for this component instance.
    """
    def __init__(
        self,
        component_type: str,
        payload: Optional[Dict[str, Any]] = None,
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_error: Optional[Callable[[ErrorEvent], None]] = None,
    ):
        """Initializes the base component.

        This is called by subclasses. It handles ID generation/validation,
        registers with ConnectionService, processes parent info, and sends the
        'spawn' command. The first component creation (triggering the first
        `send_message` to ConnectionService) will implicitly activate the
        connection.

        Args:
            component_type: The internal type name of the component.
            payload: Initial configuration data for the UI component.
            instance_id: Optional user-defined unique ID. Must be unique.
            parent: Optional parent Component instance or its string ID.
            on_error: Optional callback for UI errors related to this component.

        Raises:
            SidekickConnectionError: If the implicit connection activation fails
                                     (e.g., during the first 'spawn' command).
            ValueError: If `instance_id` is invalid or a duplicate.
            TypeError: If `parent` or `on_error` types are invalid.
        """
        self.component_type = component_type
        self._error_callback: Optional[Callable[[ErrorEvent], None]] = None # Init before use

        # --- Instance ID Assignment ---
        final_instance_id: str
        if instance_id is not None and isinstance(instance_id, str):
            processed_id = instance_id.strip()
            if not processed_id:
                msg = (f"User-provided instance_id for {component_type} "
                       f"cannot be empty or only whitespace.")
                logger.error(msg)
                raise ValueError(msg)
            final_instance_id = processed_id
        else:
            final_instance_id = generate_unique_id(component_type)
        self.instance_id = final_instance_id

        # --- Register with ConnectionService ---
        # This also validates instance_id uniqueness via ConnectionService
        try:
            sidekick_connection_module.register_message_handler(
                self.instance_id, self._internal_message_handler
            )
        except ValueError as e_id_dup:
            logger.error(
                f"Failed to initialize {component_type} (ID: '{self.instance_id}'): {e_id_dup}"
            )
            raise # Re-raise ValueError for duplicate ID

        # --- Prepare Spawn Payload ---
        final_spawn_payload = payload.copy() if payload else {}
        parent_id_to_send: Optional[str] = None
        if parent is not None:
            if isinstance(parent, Component):
                parent_id_to_send = parent.instance_id
            elif isinstance(parent, str):
                parent_id_to_send = parent
            else:
                msg = (f"Parent for {self.component_type} '{self.instance_id}' "
                       f"must be Component, str ID, or None. Got: {type(parent).__name__}.")
                logger.error(msg)
                raise TypeError(msg)
            if not parent_id_to_send:
                msg = (f"Parent ID for {self.component_type} '{self.instance_id}' cannot be empty.")
                logger.error(msg)
                raise ValueError(msg)
            final_spawn_payload["parent"] = parent_id_to_send

        parent_display = parent_id_to_send if parent_id_to_send else "root (default)"
        logger.debug(
            f"Prepared spawn for {self.component_type} '{self.instance_id}' "
            f"with parent '{parent_display}' and payload keys: {list(final_spawn_payload.keys())}"
        )

        # --- Send Spawn Command (this will trigger activate_connection if first call) ---
        try:
            self._send_command("spawn", final_spawn_payload)
        except SidekickConnectionError as e_conn: # Catch connection errors during initial spawn
            logger.error(
                f"Connection error during spawn of {self.component_type} "
                f"'{self.instance_id}': {e_conn}. Unregistering handler."
            )
            # If spawn fails due to connection, unregister the handler that was just added.
            try:
                sidekick_connection_module.unregister_message_handler(self.instance_id)
            except Exception as e_unreg: # pragma: no cover
                logger.warning(f"Error unregistering handler for '{self.instance_id}' after spawn failure: {e_unreg}")
            raise # Re-raise the original connection error
        except Exception as e_other_spawn: # pragma: no cover
            logger.exception(
                f"Unexpected error during spawn of {self.component_type} "
                f"'{self.instance_id}': {e_other_spawn}. Unregistering handler."
            )
            try:
                sidekick_connection_module.unregister_message_handler(self.instance_id)
            except Exception: pass
            raise


        # --- Register Error Callback ---
        if on_error is not None:
            self.on_error(on_error)

        logger.info(
            f"Initialized {self.component_type} component: id='{self.instance_id}', "
            f"parent='{parent_display}'."
        )

    def _internal_message_handler(self, message: Dict[str, Any]) -> None:
        """Handles incoming messages (events/errors) for this component instance."""
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "error":
            error_message_str = "Unknown error from Sidekick UI."
            if payload and isinstance(payload.get("message"), str):
                error_message_str = payload["message"]
            logger.error(f"Component '{self.instance_id}' received UI error: {error_message_str}")

            if self._error_callback:
                try:
                    error_event = ErrorEvent(
                        instance_id=self.instance_id,
                        type="error",
                        message=error_message_str,
                    )
                    self._error_callback(error_event)
                except Exception as e: # pragma: no cover
                    logger.exception(
                        f"Error in {self.component_type} '{self.instance_id}' "
                        f"on_error callback: {e}"
                    )
        elif msg_type == "event":
            # Base Component doesn't handle specific events. Subclasses override.
            logger.debug(
                f"Component '{self.instance_id}' received unhandled 'event': {payload}"
            )
        else: # pragma: no cover
            logger.warning(
                f"Component '{self.instance_id}' received unexpected message type "
                f"'{msg_type}': {message}"
            )

    def on_error(self, callback: Optional[Callable[[ErrorEvent], None]]) -> None:
        """Registers a function to handle UI error messages for this component."""
        if callback is not None and not callable(callback):
            raise TypeError("on_error callback must be a callable function or None.")
        logger.info(f"Setting on_error callback for component '{self.instance_id}'.")
        self._error_callback = callback

    def _send_command(self, msg_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Internal helper to construct and send a command message via ConnectionService."""
        message: Dict[str, Any] = {
            "id": 0,
            "component": self.component_type,
            "type": msg_type,
            "target": self.instance_id,
        }
        if payload is not None:
            message["payload"] = payload

        logger.debug(f"Component '{self.instance_id}' sending command: type='{msg_type}', target='{self.instance_id}', payload_keys={list(payload.keys()) if payload else 'None'}")
        sidekick_connection_module.send_message(message) # Uses the new service

    def _send_update(self, payload: Dict[str, Any]) -> None:
        """Convenience method for sending an 'update' command."""
        if not isinstance(payload, dict) or "action" not in payload: # Basic validation
            logger.error(f"Component '{self.instance_id}' _send_update called with invalid payload (missing 'action'): {payload}")
            # Consider raising an error here for internal consistency.
            # For now, it will likely fail in ConnectionService or UI.
            # raise ValueError("Update payload must be a dict and include an 'action'.")
        self._send_command("update", payload)

    def remove(self) -> None:
        """Removes this component from the Sidekick UI and cleans up resources."""
        logger.info(
            f"Requesting removal of {self.component_type} id '{self.instance_id}'."
        )
        try:
            sidekick_connection_module.unregister_message_handler(self.instance_id)
        except Exception as e_unreg: # pragma: no cover
             logger.warning(f"Error unregistering handler for '{self.instance_id}' during remove: {e_unreg}")

        self._error_callback = None
        self._reset_specific_callbacks()

        try:
             self._send_command("remove", payload=None)
        except SidekickConnectionError as e_remove_conn: # pragma: no cover
             logger.warning(
                f"Failed to send 'remove' command for component '{self.instance_id}' "
                f"(UI might not reflect removal): {e_remove_conn}."
            )
        except Exception as e_remove_other: # pragma: no cover
             logger.exception(
                f"Unexpected error sending 'remove' command for '{self.instance_id}': {e_remove_other}"
            )


    def _reset_specific_callbacks(self) -> None:
        """Internal hook for subclasses to reset their unique callback attributes."""
        # Base implementation does nothing for now.
        pass

    def __del__(self) -> None:
        """Attempt to unregister message handler upon garbage collection. (Fallback)."""
        # This is a best-effort cleanup. Explicit .remove() is preferred.
        try:
            # Check if module and function still exist (interpreter shutdown)
            if hasattr(sidekick_connection_module, 'unregister_message_handler') and hasattr(self, 'instance_id') and self.instance_id:
                 # Check if ConnectionService might still be active enough to process this
                 # This is risky in __del__; ConnectionService might be None or shutting down.
                 # A more robust check might be needed if this causes issues during shutdown.
                 # For now, attempt it.
                 sidekick_connection_module.unregister_message_handler(self.instance_id)
                 logger.debug(
                    f"Component __del__ attempting fallback unregistration for {getattr(self, 'component_type', '?')} id {self.instance_id}"
                 )
        except Exception: # pragma: no cover
            # Suppress all errors in __del__
            pass