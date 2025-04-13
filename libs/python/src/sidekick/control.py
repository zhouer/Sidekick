"""
Sidekick Control Module Interface.

This module provides the `Control` class, which allows you to add interactive
UI elements like buttons and text input fields to the Sidekick panel directly
from your Python script.

You can use this to:
  - Create buttons that trigger actions in your Python code when clicked.
  - Add text fields where users can enter information that your script can then process.
"""

from typing import Optional, Dict, Any, Callable
from . import logger
from .base_module import BaseModule

class Control(BaseModule):
    """Represents a Control module instance in the Sidekick UI.

    Use this class to add interactive UI elements like buttons and text input
    fields with submit buttons to the Sidekick panel. You can then define
    callback functions (`on_click`, `on_input_text`) to react when the user
    interacts with these controls.

    Attributes:
        target_id (str): The unique identifier for this control panel instance.
    """

    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True
    ):
        """Initializes the Control object, optionally creating a new control panel.

        Args:
            instance_id (Optional[str]): A specific ID for this control panel.
                - If `spawn=True`: Optional. Auto-generated if None.
                - If `spawn=False`: **Required**. Identifies the existing panel.
            spawn (bool): If True (default), creates a new, empty control panel
                UI element. If False, attaches to an existing panel.

        Examples:
            >>> # Create a new control panel
            >>> controls = sidekick.Control()
            >>>
            >>> # Attach to an existing panel named "main-controls"
            >>> existing_controls = sidekick.Control(instance_id="main-controls", spawn=False)

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
        logger.info(f"Control panel '{self.target_id}' initialized (spawn={spawn}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages for this control panel instance."""
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            control_id = payload.get("controlId") if payload else None

            if not control_id:
                 logger.warning(f"Control '{self.target_id}' received event without 'controlId': {payload}")
                 return # Cannot process event without controlId

            if event_type == "click" and self._click_callback:
                try:
                    self._click_callback(control_id)
                except Exception as e:
                    logger.exception(f"Error in Control '{self.target_id}' on_click callback for '{control_id}': {e}")

            elif event_type == "inputText" and self._input_text_callback:
                try:
                    value = payload.get("value")
                    if isinstance(value, str):
                        self._input_text_callback(control_id, value)
                    else:
                        logger.warning(f"Control '{self.target_id}' received inputText for '{control_id}' with non-string value: {payload}")
                except Exception as e:
                    logger.exception(f"Error in Control '{self.target_id}' on_input_text callback for '{control_id}': {e}")
            else:
                logger.debug(f"Control '{self.target_id}' received unhandled event '{event_type}' for control '{control_id}'.")

        # Call base handler for error messages
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to handle button clicks within this panel.

        When a button added via `add_button` is clicked in the Sidekick UI, the
        function registered here will be called.

        Args:
            callback (Optional[Callable[[str], None]]): A function that takes one
                argument: the `control_id` (string) of the button that was clicked.
                Pass `None` to remove the current callback.

        Raises:
            TypeError: If the provided callback is not callable or None.

        Examples:
            >>> def handle_button(button_id):
            ...     print(f"Button '{button_id}' was pressed!")
            ...     if button_id == "quit_button":
            ...         sidekick.shutdown()
            >>>
            >>> controls = sidekick.Control()
            >>> controls.add_button("start_button", "Start Process")
            >>> controls.add_button("quit_button", "Quit")
            >>> controls.on_click(handle_button)
            >>> # sidekick.run_forever() # Needed to keep script alive for clicks

        Returns:
            None
        """
        if callback is not None and not callable(callback):
            raise TypeError("Click callback must be callable or None")
        logger.info(f"Setting on_click callback for control panel '{self.target_id}'.")
        self._click_callback = callback

    def on_input_text(self, callback: Optional[Callable[[str, str], None]]):
        """Registers a function to handle text submitted from text input controls.

        When the user enters text into a field added by `add_text_input` and
        clicks its associated submit button in Sidekick, the function registered
        here will be called.

        Args:
            callback (Optional[Callable[[str, str], None]]): A function that takes
                two arguments:
                1. `control_id` (str): The ID of the text input group.
                2. `value` (str): The text entered by the user.
                Pass `None` to remove the current callback.

        Raises:
            TypeError: If the provided callback is not callable or None.

        Examples:
            >>> def handle_name_input(input_id, entered_name):
            ...     print(f"Input received from '{input_id}': Hello, {entered_name}!")
            >>>
            >>> controls = sidekick.Control()
            >>> controls.add_text_input("name_input", placeholder="Enter your name")
            >>> controls.on_input_text(handle_name_input)
            >>> # sidekick.run_forever() # Needed to keep script alive for input

        Returns:
            None
        """
        if callback is not None and not callable(callback):
            raise TypeError("Input text callback must be callable or None")
        logger.info(f"Setting on_input_text callback for control panel '{self.target_id}'.")
        self._input_text_callback = callback

    # on_error is inherited from BaseModule

    def add_button(self, control_id: str, text: str):
        """Adds a clickable button to this control panel in the Sidekick UI.

        Args:
            control_id (str): A unique identifier for this button within this panel.
                You'll receive this ID in the `on_click` callback when the button
                is pressed. Must be a non-empty string.
            text (str): The text label displayed on the button.

        Raises:
            ValueError: If `control_id` is empty or not a string (logs an error).

        Examples:
            >>> controls.add_button("action_button", "Perform Action")
            >>> controls.add_button("cancel_button", "Cancel")

        Returns:
            None
        """
        if not isinstance(control_id, str) or not control_id:
            # Log error and raise exception for invalid control_id
            logger.error("Control ID for add_button must be a non-empty string.")
            raise ValueError("Control ID for add_button must be a non-empty string.")
        if not isinstance(text, str):
            logger.warning(f"Button text for '{control_id}' is not a string, converting.")
            text = str(text)

        payload = {
            "action": "add",
            "controlId": control_id,
            "options": {
                "controlType": "button",
                "config": { "text": text }
            }
        }
        self._send_update(payload)
        logger.debug(f"Control '{self.target_id}': Sent add command for button '{control_id}'.")

    def add_text_input(
        self,
        control_id: str,
        placeholder: str = "",
        initial_value: str = "",
        button_text: str = "Submit"
    ):
        """Adds a text input field and an associated submit button to the panel.

        Args:
            control_id (str): A unique identifier for this text input group.
                You'll receive this ID and the entered text in the `on_input_text`
                callback when the submit button is clicked. Must be a non-empty string.
            placeholder (str): Placeholder text displayed in the input field when
                it's empty. Defaults to "".
            initial_value (str): Initial text value pre-filled in the input field.
                Defaults to "".
            button_text (str): Text label for the submit button associated with this
                input field. Defaults to "Submit".

        Raises:
            ValueError: If `control_id` is empty or not a string (logs an error).

        Examples:
            >>> # Add a simple text input
            >>> controls.add_text_input("user_query", placeholder="Ask something...")
            >>>
            >>> # Add an input with initial value and custom button
            >>> controls.add_text_input("config_value", initial_value="default", button_text="Update")

        Returns:
            None
        """
        if not isinstance(control_id, str) or not control_id:
            logger.error("Control ID for add_text_input must be a non-empty string.")
            raise ValueError("Control ID for add_text_input must be a non-empty string.")
        placeholder = str(placeholder)
        initial_value = str(initial_value)
        button_text = str(button_text)

        payload = {
            "action": "add",
            "controlId": control_id,
            "options": {
                "controlType": "textInput",
                "config": {
                    "placeholder": placeholder,
                    "initialValue": initial_value,
                    "buttonText": button_text
                }
            }
        }
        self._send_update(payload)
        logger.debug(f"Control '{self.target_id}': Sent add command for text input '{control_id}'.")

    def remove_control(self, control_id: str):
        """Removes a specific control (button or text input) from this panel.

        Args:
            control_id (str): The unique identifier (`control_id` used when adding)
                of the control to remove. Must be a non-empty string.

        Raises:
            ValueError: If `control_id` is empty or not a string (logs an error).

        Examples:
            >>> controls.remove_control("start_button")
            >>> controls.remove_control("user_query")

        Returns:
            None
        """
        if not isinstance(control_id, str) or not control_id:
            logger.error("Control ID for remove_control must be a non-empty string.")
            raise ValueError("Control ID for remove_control must be a non-empty string.")

        payload = { "action": "remove", "controlId": control_id }
        self._send_update(payload)
        logger.debug(f"Control '{self.target_id}': Sent remove command for control '{control_id}'.")

    def _reset_specific_callbacks(self):
        """Resets control-specific callbacks on removal."""
        self._click_callback = None
        self._input_text_callback = None

    # remove() is inherited from BaseModule