# Sidekick/libs/python/src/sidekick/control.py
from typing import Optional, Dict, Any, Callable
from .base_module import BaseModule
from . import connection

class Control(BaseModule):
    """
    Represents a Control module instance in the Sidekick UI.

    This module allows you to dynamically add interactive UI elements, such as
    buttons and text input fields, to the Sidekick panel. You can then receive
    notifications (via a callback) when the user interacts with these elements
    (e.g., clicks a button, submits text).

    It supports two modes of initialization:
    1. Creating a new control panel instance in Sidekick (`spawn=True`).
    2. Attaching to a pre-existing panel instance in Sidekick (`spawn=False`).
    """

    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Initializes the Control object, optionally creating a new control panel in Sidekick.

        Args:
            instance_id: A unique identifier for this control panel instance.
                         - If `spawn=True`: Optional. If None, an ID will be generated.
                         - If `spawn=False`: **Required**. Specifies the ID of the existing
                           control panel instance in Sidekick to attach to.
            spawn: If True (default), sends a command to Sidekick to create a new,
                   empty control module instance.
                   If False, assumes a control panel with `instance_id` already exists.
            on_message: An optional callback function invoked when a user interacts
                        with a control element within this panel in Sidekick.
                        The callback receives the full message dictionary
                        (e.g., {'event': 'click', 'controlId': 'my_button'}).
                        Payload keys are camelCase.
        """
        # Control spawn payload is currently empty.
        spawn_payload = {} if spawn else None

        super().__init__(
            module_type="control",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload,
            on_message=on_message
        )
        connection.logger.info(f"Control panel '{self.target_id}' initialized (spawn={spawn}).")

    def add_button(self, control_id: str, text: str):
        """
        Adds a clickable button to this control panel in the Sidekick UI.

        Args:
            control_id: A unique identifier string for this button within this panel.
                        This ID will be included in the notification payload when
                        the button is clicked. Must be a non-empty string.
            text: The text label to display on the button.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID for add_button must be a non-empty string. Ignoring command.")
            return
        if not isinstance(text, str):
            connection.logger.warning(f"Button text for '{control_id}' is not a string, converting.")
            text = str(text)

        # Construct the payload for adding a button. Keys must be camelCase.
        payload = {
            "action": "add",
            "controlId": control_id,
            "options": {
                "controlType": "button",
                "config": {"text": text} # config keys are also camelCase
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
        Adds a text input field along with an associated submit button to this
        control panel in the Sidekick UI.

        Args:
            control_id: A unique identifier string for this text input group.
                        This ID will be included in the notification payload when
                        the associated button is clicked. Must be a non-empty string.
            placeholder: Placeholder text displayed in the input field when empty.
            initial_value: The initial text value pre-filled in the input field.
            button_text: The text label for the submit button next to the input field.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID for add_text_input must be a non-empty string. Ignoring command.")
            return
        # Ensure all config values are strings
        placeholder = str(placeholder)
        initial_value = str(initial_value)
        button_text = str(button_text)

        # Construct the payload for adding a text input. Keys must be camelCase.
        payload = {
            "action": "add",
            "controlId": control_id,
            "options": {
                "controlType": "textInput",
                "config": {
                    "placeholder": placeholder,
                    "initialValue": initial_value,
                    "buttonText": button_text
                } # config keys are camelCase
            }
        }
        self._send_update(payload)
        connection.logger.debug(f"Control '{self.target_id}': Sent add command for text input '{control_id}'.")

    def remove_control(self, control_id: str):
        """
        Removes a specific control (button or text input group) from this panel
        in the Sidekick UI.

        Args:
            control_id: The unique identifier of the control to remove (as provided
                        when it was added). Must be a non-empty string.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID for remove_control must be a non-empty string. Ignoring command.")
            return

        # Construct the payload for removing a control.
        payload = {
            "action": "remove",
            "controlId": control_id
            # No 'options' needed for removal.
        }
        self._send_update(payload)
        connection.logger.debug(f"Control '{self.target_id}': Sent remove command for control '{control_id}'.")

    # The remove() method is inherited from BaseModule.
    # Calling control_instance.remove() will send a 'remove' command to Sidekick
    # for this control panel instance and unregister the local message handler.