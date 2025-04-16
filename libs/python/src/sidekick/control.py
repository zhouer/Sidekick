"""
Provides the Control class for adding interactive UI elements to Sidekick.

Use the `sidekick.Control` class to create a dedicated panel in Sidekick
where you can add simple user interface elements like buttons and text input
fields.

This allows you to:
- Create buttons that, when clicked in Sidekick, trigger specific actions
  (functions) in your Python script.
- Add text input fields where users can type information, which is then sent
  back to your Python script for processing when a submit button is clicked.
"""

from typing import Optional, Dict, Any, Callable
from . import logger
from .base_module import BaseModule

class Control(BaseModule):
    """Represents a Control panel module instance in the Sidekick UI.

    Use this class to create a container in the Sidekick panel where you can
    programmatically add simple UI controls:
    - `add_button()`: Creates a clickable button.
    - `add_text_input()`: Creates a text field with a submit button.

    You can then define callback functions using `on_click()` and `on_input_text()`
    to make your Python script react when the user interacts with these controls.

    Attributes:
        target_id (str): The unique identifier for this control panel instance.
    """

    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True
    ):
        """Initializes the Control panel object and optionally creates the UI element.

        Args:
            instance_id (Optional[str]): A specific ID for this control panel.
                - If `spawn=True` (default): Optional. Auto-generated if None.
                - If `spawn=False`: **Required**. Must match the ID of an existing panel.
            spawn (bool): If True (default), creates a new, empty control panel
                UI element in Sidekick. If False, attaches to an existing panel.

        Raises:
            ValueError: If `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established.

        Examples:
            >>> # Create a new panel to hold controls
            >>> controls = sidekick.Control()
            >>> controls.add_button("btn_1", "Click Me")
            >>>
            >>> # Attach to an existing panel named "main-controls"
            >>> existing_controls = sidekick.Control(instance_id="main-controls", spawn=False)
        """
        # The initial spawn command for Control currently doesn't require any payload data.
        spawn_payload = {} if spawn else None

        # Initialize the base class.
        super().__init__(
            module_type="control",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload,
        )
        # Initialize placeholders for user callback functions.
        self._click_callback: Optional[Callable[[str], None]] = None
        self._input_text_callback: Optional[Callable[[str, str], None]] = None
        logger.info(f"Control panel '{self.target_id}' initialized (spawn={spawn}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages specifically for this control panel instance.

        This overrides the base class method to add handling for 'click' and
        'inputText' events originating from controls within this panel. It extracts
        the `controlId` from the payload to identify which specific button or
        input was interacted with, and then calls the corresponding registered
        user callback (`on_click` or `on_input_text`).

        It calls the base class's handler at the end for 'error' message processing.

        Args:
            message (Dict[str, Any]): The raw message dictionary received.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload keys expected to be camelCase.

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            # Crucially, get the ID of the specific control that triggered the event.
            control_id = payload.get("controlId") if payload else None

            # We need the controlId to know which button/input was used.
            if not control_id:
                 logger.warning(f"Control '{self.target_id}' received event without 'controlId': {payload}")
                 # Can't process further without knowing which control it was.
                 super()._internal_message_handler(message) # Still process errors
                 return

            # --- Dispatch based on event type ---
            if event_type == "click" and self._click_callback:
                try:
                    # Call the user's click handler, passing the ID of the clicked button.
                    self._click_callback(control_id)
                except Exception as e:
                    # Catch errors in the user's callback.
                    logger.exception(f"Error in Control '{self.target_id}' on_click callback for '{control_id}': {e}")

            elif event_type == "inputText" and self._input_text_callback:
                try:
                    # Extract the submitted text value.
                    value = payload.get("value")
                    if isinstance(value, str):
                        # Call the user's input handler, passing the control ID and the text.
                        self._input_text_callback(control_id, value)
                    else:
                        logger.warning(f"Control '{self.target_id}' received inputText for '{control_id}' with non-string value: {payload}")
                except Exception as e:
                    # Catch errors in the user's callback.
                    logger.exception(f"Error in Control '{self.target_id}' on_input_text callback for '{control_id}': {e}")
            else:
                # Log if we receive an event type we don't handle or if no callback is set.
                logger.debug(f"Control '{self.target_id}' received unhandled event '{event_type}' for control '{control_id}'.")

        # Call the base class handler to process potential 'error' messages.
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to call when any button in this panel is clicked.

        When a user clicks a button (created with `add_button()`) in the
        Sidekick UI, the `callback` function you provide here will be executed
        in your Python script.

        Args:
            callback (Optional[Callable[[str], None]]): The function to call
                when a button is clicked. This function should accept one
                argument: the `control_id` (string) of the specific button
                that was clicked (this is the ID you provided when calling
                `add_button`). Pass `None` to remove any previously registered
                callback.

        Raises:
            TypeError: If the provided `callback` is not a function (or None).

        Returns:
            None

        Examples:
            >>> def handle_button_press(button_id):
            ...     print(f"Button '{button_id}' was pressed!")
            ...     if button_id == "run_simulation":
            ...         print("Starting simulation...")
            ...         # (Add simulation logic here)
            ...     elif button_id == "quit_app":
            ...         print("Quitting...")
            ...         sidekick.shutdown()
            ...
            >>> controls = sidekick.Control()
            >>> controls.add_button("run_simulation", "Start Simulation")
            >>> controls.add_button("quit_app", "Quit")
            >>> controls.on_click(handle_button_press)
            >>>
            >>> # Important: Keep the script running to listen for clicks!
            >>> sidekick.run_forever()
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for control panel '{self.target_id}'.")
        self._click_callback = callback

    def on_input_text(self, callback: Optional[Callable[[str, str], None]]):
        """Registers a function to call when text is submitted from an input field.

        When a user types text into an input field (created with `add_text_input()`)
        and clicks its associated "Submit" button in the Sidekick UI, the `callback`
        function you provide here will be executed in your Python script.

        Args:
            callback (Optional[Callable[[str, str], None]]): The function to call
                when text is submitted. This function should accept two arguments:
                1. `control_id` (str): The ID of the text input control group
                   (the ID you provided when calling `add_text_input`).
                2. `value` (str): The text string that the user entered and submitted.
                Pass `None` to remove any previously registered callback.

        Raises:
            TypeError: If the provided `callback` is not a function (or None).

        Returns:
            None

        Examples:
            >>> def handle_user_input(input_field_id, text_value):
            ...     print(f"Received input from '{input_field_id}': '{text_value}'")
            ...     if input_field_id == "user_name":
            ...         print(f"Hello, {text_value}!")
            ...
            >>> controls = sidekick.Control()
            >>> controls.add_text_input("user_name", placeholder="Enter your name", button_text="Greet")
            >>> controls.add_text_input("search_query", placeholder="Search term...")
            >>> controls.on_input_text(handle_user_input)
            >>>
            >>> # Important: Keep the script running to listen for input!
            >>> sidekick.run_forever()
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_input_text callback must be a callable function or None.")
        logger.info(f"Setting on_input_text callback for control panel '{self.target_id}'.")
        self._input_text_callback = callback

    # --- Error Callback ---
    # Inherits on_error(callback) method from BaseModule. Use this to handle
    # potential errors reported by the Control panel UI element itself.

    def add_button(self, control_id: str, text: str):
        """Adds a clickable button to this control panel in the Sidekick UI.

        Clicking this button in the UI will trigger the `on_click` callback
        (if one is registered), passing the `control_id`.

        Args:
            control_id (str): A unique identifier for this specific button within
                this control panel. This ID will be passed to the `on_click`
                callback. Must be a non-empty string.
            text (str): The text label that will appear on the button in the UI.

        Raises:
            ValueError: If `control_id` is empty or not a string.

        Returns:
            None

        Examples:
            >>> controls = sidekick.Control()
            >>> controls.add_button("start_button", "Start Process")
            >>> controls.add_button("cancel_button", "Cancel")
        """
        # Validate control_id
        if not isinstance(control_id, str) or not control_id:
            msg = "Control ID for add_button must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)
        # Ensure text is a string
        if not isinstance(text, str):
            logger.warning(f"Button text for '{control_id}' is not a string, converting using str().")
            text = str(text)

        # Prepare the payload for the 'update' command to add the control.
        # Keys must be camelCase.
        payload = {
            "action": "add",          # Tell the UI to add a control
            "controlId": control_id,  # The ID for this new control
            "options": {
                "controlType": "button", # Specify the type of control
                "config": {              # Configuration specific to buttons
                    "text": text
                }
            }
        }
        # Send the command.
        self._send_update(payload)
        logger.debug(f"Control '{self.target_id}': Sent add command for button '{control_id}'.")

    def add_text_input(
        self,
        control_id: str,
        placeholder: str = "",
        initial_value: str = "",
        button_text: str = "Submit"
    ):
        """Adds a text input field along with a submit button to the control panel.

        This creates a combined UI element in Sidekick. When the user types text
        and clicks the associated submit button, the `on_input_text` callback
        is triggered, passing this control's `control_id` and the entered text.

        Args:
            control_id (str): A unique identifier for this text input group
                (field + button). This ID will be passed to the `on_input_text`
                callback. Must be a non-empty string.
            placeholder (str): Text displayed faintly in the input field when it's
                empty, guiding the user. Defaults to "".
            initial_value (str): Text pre-filled in the input field when it first
                appears. Defaults to "".
            button_text (str): The text label displayed on the submit button
                next to the input field. Defaults to "Submit".

        Raises:
            ValueError: If `control_id` is empty or not a string.

        Returns:
            None

        Examples:
            >>> controls = sidekick.Control()
            >>> # Add a simple text input with a placeholder
            >>> controls.add_text_input("user_query", placeholder="Enter search term...")
            >>>
            >>> # Add an input with initial value and custom button text
            >>> controls.add_text_input("config_setting", initial_value="127.0.0.1", button_text="Update IP")
        """
        # Validate control_id
        if not isinstance(control_id, str) or not control_id:
            msg = "Control ID for add_text_input must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)
        # Ensure other text parameters are strings.
        placeholder = str(placeholder)
        initial_value = str(initial_value)
        button_text = str(button_text)

        # Prepare the payload. Keys must be camelCase.
        payload = {
            "action": "add",
            "controlId": control_id,
            "options": {
                "controlType": "textInput", # Specify the type
                "config": {                 # Configuration specific to text inputs
                    "placeholder": placeholder,
                    "initialValue": initial_value,
                    "buttonText": button_text
                }
            }
        }
        # Send the command.
        self._send_update(payload)
        logger.debug(f"Control '{self.target_id}': Sent add command for text input '{control_id}'.")

    def remove_control(self, control_id: str):
        """Removes a specific control (button or text input) from this panel.

        Use the same `control_id` that you used when adding the control with
        `add_button()` or `add_text_input()`.

        Args:
            control_id (str): The unique identifier of the control element
                (button or text input group) to remove from the UI. Must be
                a non-empty string.

        Raises:
            ValueError: If `control_id` is empty or not a string.

        Returns:
            None

        Examples:
            >>> controls = sidekick.Control()
            >>> controls.add_button("temp_action", "Temporary")
            >>> # ... later ...
            >>> controls.remove_control("temp_action") # Button disappears from UI
            >>>
            >>> controls.add_text_input("user_id", "User ID")
            >>> # ... later ...
            >>> controls.remove_control("user_id") # Text input + button disappear
        """
        # Validate control_id
        if not isinstance(control_id, str) or not control_id:
            msg = "Control ID for remove_control must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)

        # Prepare the payload for removing a specific control.
        # Keys must be camelCase.
        payload = {
            "action": "remove",       # Tell the UI to remove a control
            "controlId": control_id   # Specify which control to remove
            # No further options needed for removal
        }
        # Send the command.
        self._send_update(payload)
        logger.debug(f"Control '{self.target_id}': Sent remove command for control '{control_id}'.")

    def _reset_specific_callbacks(self):
        """Resets control-panel-specific callbacks when the module is removed."""
        # Called by BaseModule.remove()
        self._click_callback = None
        self._input_text_callback = None

    # --- Removal ---
    # Inherits the remove() method from BaseModule to remove the entire control panel.