# Sidekick/libs/python/src/sidekick/control.py
from typing import Optional, Dict, Any, Callable
from .base_module import BaseModule
from . import connection

class Control(BaseModule):
    """
    Represents a Control module instance in the Sidekick UI.

    This module allows you to dynamically add interactive UI elements, such as
    buttons and text input fields, to the Sidekick panel. You can then receive
    notifications (via a callback function) when the user interacts with these
    elements (e.g., clicks a button, submits text).

    Use the `on_message` callback during initialization to handle these interactions.

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
            instance_id (Optional[str]): A unique identifier for this control panel instance.
                - If `spawn=True`: Optional. If None, an ID will be generated automatically.
                - If `spawn=False`: **Required**. Specifies the ID of the existing
                  control panel instance in Sidekick to attach to.
            spawn (bool): If True (default), sends a command to Sidekick to create a new,
                empty control module instance.
                If False, assumes a control panel with `instance_id` already exists.
            on_message (Optional[Callable]): A function to call when a user interacts
                with a control element within this panel in Sidekick (e.g., clicks a
                button or submits text input). The callback receives the full message
                dictionary from Sidekick.
                Example payloads received by the callback:
                - Button click: `{'event': 'click', 'controlId': 'your_button_id'}`
                - Text input submission: `{'event': 'inputText', 'controlId': 'your_input_id', 'value': 'user text'}`
                Ensure the provided function accepts one dictionary argument.
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

        When the user clicks this button in Sidekick, the `on_message` callback
        (provided during initialization) will be called with a message containing
        `{'event': 'click', 'controlId': control_id}` in its payload.

        Args:
            control_id (str): A unique identifier string for this button within this panel.
                This ID **must** be unique among all controls added to this panel.
                It will be included in the notification payload when the button is clicked.
                Must be a non-empty string.
            text (str): The text label to display on the button.
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
                "controlType": "button", # Specify the type of control
                "config": {
                    "text": text # Configuration specific to buttons
                } # config keys are also camelCase
            }
        }
        # Send the update command (will be buffered if Sidekick not ready)
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

        When the user clicks the submit button next to the input field, the
        `on_message` callback (provided during initialization) will be called
        with a message containing
        `{'event': 'inputText', 'controlId': control_id, 'value': current_input_text}`
        in its payload.

        Args:
            control_id (str): A unique identifier string for this text input group.
                This ID **must** be unique among all controls added to this panel.
                It will be included in the notification payload when the associated
                button is clicked. Must be a non-empty string.
            placeholder (str): Placeholder text displayed in the input field when empty
                (e.g., "Enter your name..."). Defaults to "".
            initial_value (str): The initial text value pre-filled in the input field.
                Defaults to "".
            button_text (str): The text label for the submit button next to the input field.
                Defaults to "Submit".
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
                "controlType": "textInput", # Specify the type of control
                "config": {
                    # Configuration specific to text inputs (all camelCase)
                    "placeholder": placeholder,
                    "initialValue": initial_value,
                    "buttonText": button_text
                }
            }
        }
        # Send the update command (will be buffered if Sidekick not ready)
        self._send_update(payload)
        connection.logger.debug(f"Control '{self.target_id}': Sent add command for text input '{control_id}'.")

    def remove_control(self, control_id: str):
        """
        Removes a specific control (button or text input group) from this panel
        in the Sidekick UI.

        Args:
            control_id (str): The unique identifier of the control to remove (the same
                ID used when adding it with `add_button` or `add_text_input`).
                Must be a non-empty string.
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
        # Send the update command (will be buffered if Sidekick not ready)
        self._send_update(payload)
        connection.logger.debug(f"Control '{self.target_id}': Sent remove command for control '{control_id}'.")

    # The remove() method is inherited from BaseModule.
    # Calling control_instance.remove() will send a 'remove' command to Sidekick
    # for this control panel instance and unregister the local message handler.