# Sidekick/libs/python/src/sidekick/control.py
from typing import Optional, Dict, Any, Callable
from .base_module import BaseModule
from . import connection

class Control(BaseModule):
    """
    Represents a Control module instance in Sidekick.

    Allows dynamically adding interactive elements (buttons, text inputs)
    and receiving user interaction events via a callback.
    Uses a consistent action/options payload structure for updates.
    """

    def __init__(
        self,
        instance_id: Optional[str] = None,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """Creates a new, initially empty, Control module instance."""
        super().__init__("control", instance_id, payload={}, on_message=on_message)
        connection.logger.info(f"Control module '{self.target_id}' created.")

    def add_button(self, control_id: str, text: str):
        """
        Adds a clickable button to the Control module UI.

        Args:
            control_id: A unique identifier for this button within this module.
            text: The text label displayed on the button.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID for add_button must be a non-empty string.")
            return
        # Construct payload using the revised action/options structure
        payload = {
            "action": "add",
            "controlId": control_id,
            "options": {
                "controlType": "button",
                "config": {"text": text}
            }
        }
        self._send_update(payload)
        connection.logger.debug(f"Control '{self.target_id}': Sent add command for button '{control_id}'.")

    def add_text_input(
        self,
        control_id: str,
        placeholder: str = "",
        initial_value: str = "",
        button_text: str = "Submit"
    ):
        """
        Adds a text input field with an associated submit button.

        Args:
            control_id: A unique identifier for this text input group.
            placeholder: Placeholder text for the input field. Defaults to "".
            initial_value: Initial text in the input field. Defaults to "".
            button_text: Text for the submit button. Defaults to "Submit".
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID for add_text_input must be a non-empty string.")
            return
        # Construct payload using the revised action/options structure
        payload = {
            "action": "add",
            "controlId": control_id,
            "options": {
                "controlType": "text_input",
                "config": {
                    "placeholder": placeholder,
                    "initialValue": initial_value,
                    "buttonText": button_text
                }
            }
        }
        self._send_update(payload)
        connection.logger.debug(f"Control '{self.target_id}': Sent add command for text input '{control_id}'.")

    def remove_control(self, control_id: str):
        """
        Removes a specific control (button or text input) from this module.

        Args:
            control_id: The unique identifier of the control to remove.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID for remove_control must be a non-empty string.")
            return
        # Construct payload using the revised action/options structure
        # No options are needed for remove
        payload = {
            "action": "remove",
            "controlId": control_id
        }
        self._send_update(payload)
        connection.logger.debug(f"Control '{self.target_id}': Sent remove command for control '{control_id}'.")

    # remove() method is inherited from BaseModule