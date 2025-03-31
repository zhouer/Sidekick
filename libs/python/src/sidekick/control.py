# Sidekick/libs/python/src/sidekick/control.py
from typing import Optional, Dict, Any, Callable
from .base_module import BaseModule
from . import connection

class Control(BaseModule):
    """
    Represents a Control module instance in Sidekick.
    Allows adding interactive elements like buttons and text inputs dynamically.
    """

    def __init__(
        self,
        instance_id: Optional[str] = None,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Creates a new Control module instance.

        Args:
            instance_id: A unique ID for this control module. Auto-generated if None.
            on_message: Callback function to handle notifications from controls
                        (button clicks, text input submissions). The callback receives
                        a dictionary matching the SidekickMessage format.
        """
        super().__init__("control", instance_id, payload={}, on_message=on_message)
        if on_message:
            connection.register_message_handler(self.target_id, on_message)
        connection.logger.info(f"Control module '{self.target_id}' created.")

    def add_button(self, control_id: str, text: str):
        """
        Adds a button to the Control module.

        Args:
            control_id: A unique identifier for this button within the module.
            text: The text label displayed on the button.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID must be a non-empty string.")
            return
        payload = {
            "operation": "add",
            "control_id": control_id,
            "control_type": "button",
            "config": {"text": text}
        }
        self._send_command("update", payload)
        connection.logger.debug(f"Control '{self.target_id}': Added button '{control_id}'.")

    def add_text_input(
        self,
        control_id: str,
        placeholder: str = "",
        initial_value: str = "",
        button_text: str = "Submit"
    ):
        """
        Adds a text input field with an associated submit button to the Control module.

        Args:
            control_id: A unique identifier for this text input within the module.
            placeholder: Placeholder text shown in the input field.
            initial_value: The initial value displayed in the input field.
            button_text: The text for the submit button next to the input.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID must be a non-empty string.")
            return
        payload = {
            "operation": "add",
            "control_id": control_id,
            "control_type": "text_input",
            "config": {
                "placeholder": placeholder,
                "initial_value": initial_value,
                "button_text": button_text
            }
        }
        self._send_command("update", payload)
        connection.logger.debug(f"Control '{self.target_id}': Added text input '{control_id}'.")

    def remove_control(self, control_id: str):
        """
        Removes a specific control (button or text input) from the module.

        Args:
            control_id: The unique identifier of the control to remove.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID must be a non-empty string.")
            return
        payload = {
            "operation": "remove",
            "control_id": control_id
            # No type/config needed for removal
        }
        self._send_command("update", payload)
        connection.logger.debug(f"Control '{self.target_id}': Removed control '{control_id}'.")

    def remove(self):
        """Removes the entire Control module instance and unregisters handlers."""
        connection.logger.info(f"Removing Control module '{self.target_id}'.")
        # Unregister the message handler associated with this specific module instance
        connection.unregister_message_handler(self.target_id)
        # Send the base 'remove' command to the frontend
        super().remove()