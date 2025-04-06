# Sidekick/libs/python/src/sidekick/control.py
from typing import Optional, Dict, Any, Callable
from .base_module import BaseModule
from . import connection

class Control(BaseModule):
    """
    Represents a Control module instance in the Sidekick UI.

    Allows dynamic addition of interactive UI elements (buttons, text inputs)
    and receiving user interaction events via callbacks (on_click, on_input_text).
    Also supports error callbacks via on_error.

    It supports two modes of initialization:
    1. Creating a new control panel instance in Sidekick (`spawn=True`).
    2. Attaching to a pre-existing panel instance in Sidekick (`spawn=False`).
    """

    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True
    ):
        """
        Initializes the Control object, optionally creating a new control panel.

        Args:
            instance_id (Optional[str]): A unique identifier for this panel.
                - If `spawn=True`: Optional. Auto-generated if None.
                - If `spawn=False`: **Required**.
            spawn (bool): If True (default), creates a new control panel instance.
                If False, assumes a panel with `instance_id` already exists.
        """
        # Control spawn payload is currently empty.
        spawn_payload = {} if spawn else None

        super().__init__(
            module_type="control",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload,
        )
        # Initialize specific callbacks
        self._click_callback: Optional[Callable[[str], None]] = None
        self._input_text_callback: Optional[Callable[[str, str], None]] = None
        connection.logger.info(f"Control panel '{self.target_id}' initialized (spawn={spawn}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages for this control panel instance."""
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            control_id = payload.get("controlId") if payload else None

            if not control_id:
                 connection.logger.warning(f"Control '{self.target_id}' received event without 'controlId': {payload}")
                 return # Cannot process event without controlId

            if event_type == "click" and self._click_callback:
                try:
                    self._click_callback(control_id)
                except Exception as e:
                    connection.logger.exception(f"Error in Control '{self.target_id}' on_click callback for '{control_id}': {e}")

            elif event_type == "inputText" and self._input_text_callback:
                try:
                    value = payload.get("value")
                    if isinstance(value, str):
                        self._input_text_callback(control_id, value)
                    else:
                         connection.logger.warning(f"Control '{self.target_id}' received inputText event for '{control_id}' with non-string value: {payload}")
                except Exception as e:
                    connection.logger.exception(f"Error in Control '{self.target_id}' on_input_text callback for '{control_id}': {e}")
            else:
                 connection.logger.debug(f"Control '{self.target_id}' received unhandled event type '{event_type}' for control '{control_id}'.")

        # Call base handler for error messages
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[str], None]]):
        """
        Registers a function to be called when a button control within this panel is clicked.

        The callback function will receive one string argument: the `controlId` of the clicked button.

        Args:
            callback: A function accepting the control ID string, or None to unregister.
        """
        if callback is not None and not callable(callback):
            raise TypeError("Click callback must be callable or None")
        connection.logger.info(f"Setting on_click callback for control panel '{self.target_id}'.")
        self._click_callback = callback

    def on_input_text(self, callback: Optional[Callable[[str, str], None]]):
        """
        Registers a function to be called when a text input control within this panel
        is submitted (usually by clicking its associated button).

        The callback function will receive two string arguments:
        the `controlId` of the text input group, and the `value` entered by the user.

        Args:
            callback: A function accepting control ID and value strings, or None to unregister.
        """
        if callback is not None and not callable(callback):
            raise TypeError("Input text callback must be callable or None")
        connection.logger.info(f"Setting on_input_text callback for control panel '{self.target_id}'.")
        self._input_text_callback = callback

    # on_error is inherited from BaseModule

    def add_button(self, control_id: str, text: str):
        """
        Adds a clickable button to this control panel in the Sidekick UI.

        Args:
            control_id (str): A unique identifier for this button within this panel.
            text (str): The text label to display on the button.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID for add_button must be a non-empty string. Ignoring command.")
            return
        if not isinstance(text, str):
            connection.logger.warning(f"Button text for '{control_id}' is not a string, converting.")
            text = str(text)

        payload = {
            "action": "add",
            "controlId": control_id,
            "options": {
                "controlType": "button",
                "config": { "text": text } # camelCase key
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
        Adds a text input field and a submit button to this control panel.

        Args:
            control_id (str): A unique identifier for this text input group.
            placeholder (str): Placeholder text for the input field. Defaults to "".
            initial_value (str): Initial value for the input field. Defaults to "".
            button_text (str): Text for the submit button. Defaults to "Submit".
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID for add_text_input must be a non-empty string. Ignoring command.")
            return
        placeholder = str(placeholder)
        initial_value = str(initial_value)
        button_text = str(button_text)

        payload = {
            "action": "add",
            "controlId": control_id,
            "options": {
                "controlType": "textInput",
                "config": { # camelCase keys
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
        Removes a specific control (button or text input) from this panel.

        Args:
            control_id (str): The unique identifier of the control to remove.
        """
        if not isinstance(control_id, str) or not control_id:
            connection.logger.error("Control ID for remove_control must be a non-empty string. Ignoring command.")
            return

        payload = { "action": "remove", "controlId": control_id }
        self._send_update(payload)
        connection.logger.debug(f"Control '{self.target_id}': Sent remove command for control '{control_id}'.")

    def _reset_specific_callbacks(self):
        """Resets control-specific callbacks on removal."""
        self._click_callback = None
        self._input_text_callback = None

    # remove() is inherited from BaseModule