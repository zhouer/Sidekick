"""Provides the Control class for adding interactive UI elements to Sidekick.

Use the `sidekick.Control` class to create a dedicated panel within the Sidekick
UI where you can programmatically add simple user interface controls like buttons
and labeled text input fields.

This allows your Python script to present interactive options to the user directly
within the Sidekick panel, enabling you to:

*   Create buttons (`add_button`) that trigger specific Python functions when
    clicked in the Sidekick UI.
*   Add text input fields (`add_text_input`) where users can type information,
    which is then sent back to your Python script for processing when they click
    the associated submit button.

Use the `on_click()` and `on_input_text()` methods to register callback functions
that define how your Python script should react to these user interactions.

Example Scenario:
Imagine building a simple simulation. You could use a `Control` panel to add:

*   A "Start Simulation" button.
*   A "Reset Simulation" button.
*   A text input field labeled "Enter Speed:" with a "Set Speed" button.

Your Python script would then use `on_click` and `on_input_text` to run the
appropriate simulation logic or update speed variables when the user interacts
with these controls in Sidekick.
"""

from typing import Optional, Dict, Any, Callable
from . import logger
from .base_module import BaseModule

class Control(BaseModule):
    """Represents a Control panel module instance in the Sidekick UI.

    This class creates a container in the Sidekick panel specifically designed
    to hold simple interactive controls added dynamically from your Python script.
    Use its methods (`add_button`, `add_text_input`) to populate the panel, and
    `on_click` / `on_input_text` to define the Python functions that respond to
    user interactions with those controls.

    Attributes:
        target_id (str): The unique identifier for this control panel instance.
    """

    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True
    ):
        """Initializes the Control panel object and optionally creates the UI element.

        Sets up an empty panel ready to receive controls via methods like `add_button`.
        Establishes the connection to Sidekick if not already done.

        Args:
            instance_id (Optional[str]): A specific ID for this control panel instance.
                - If `spawn=True` (default): Optional. If None, a unique ID (e.g.,
                  "control-1") is generated automatically.
                - If `spawn=False`: **Required**. Must match the ID of an existing
                  control panel element in the Sidekick UI to attach to.
            spawn (bool): If True (the default), a command is sent to Sidekick
                to create a new, empty control panel UI element. If False, the
                library assumes a panel with the given `instance_id` already exists,
                and this Python object simply connects to it.

        Raises:
            ValueError: If `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established during initialization.

        Examples:
            >>> # Create a new panel to hold buttons and inputs
            >>> sim_controls = sidekick.Control(instance_id="simulation-controls")
            >>> sim_controls.add_button("start_btn", "Run Simulation")
            >>>
            >>> # Attach to an existing panel (e.g., created by another script)
            >>> existing_panel = sidekick.Control(instance_id="shared-controls", spawn=False)
        """
        # The initial spawn command for a Control panel currently doesn't require
        # any specific payload data, as it just creates an empty container.
        spawn_payload = {} if spawn else None

        # Initialize the base class (handles connection, ID, registration, spawn).
        super().__init__(
            module_type="control",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload, # Send empty payload if spawning
        )
        # --- Initialize Callbacks ---
        # Placeholders for the user-defined callback functions.
        self._click_callback: Optional[Callable[[str], None]] = None
        self._input_text_callback: Optional[Callable[[str, str], None]] = None
        # Log initialization.
        spawn_info = "new panel" if spawn else "attaching to existing"
        logger.info(f"Control panel '{self.target_id}' initialized ({spawn_info}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this control panel. (Internal).

        Overrides the base class method to specifically process 'click' and
        'inputText' events originating from controls (buttons, inputs) added
        to this panel. It uses the `controlId` field within the message payload
        to identify which specific control triggered the event. Based on the
        event type ('click' or 'inputText'), it calls the corresponding registered
        user callback (`on_click` or `on_input_text`), passing the `controlId`
        (and the submitted text value for `inputText`) as arguments.

        It delegates to the base class's handler (`super()._internal_message_handler`)
        at the end to ensure standard 'error' message processing still occurs.

        Args:
            message (Dict[str, Any]): The raw message dictionary received. Expected
                payload keys are camelCase.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload keys expected to be camelCase.

        # Handle 'event' messages specifically
        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            # CRITICAL: Get the ID of the specific button or input that triggered the event.
            control_id = payload.get("controlId") if payload else None

            # We *must* have a controlId to know which element was interacted with.
            if not control_id:
                 logger.warning(f"Control panel '{self.target_id}' received event message without required 'controlId': {payload}")
                 # Cannot dispatch without knowing the source control, but still process potential errors.
                 super()._internal_message_handler(message)
                 return # Stop further processing of this event.

            # --- Dispatch based on event type and registered callback ---
            if event_type == "click" and self._click_callback:
                # Handle button clicks
                try:
                    # Call the user's click handler, passing the ID of the clicked button.
                    self._click_callback(control_id)
                except Exception as e:
                    # Catch errors within the user's callback.
                    logger.exception(f"Error occurred inside Control '{self.target_id}' on_click callback for control '{control_id}': {e}")

            elif event_type == "inputText" and self._input_text_callback:
                # Handle text input submissions
                try:
                    # Extract the submitted text value.
                    submitted_text = payload.get("value")
                    # Ensure the value is a string before calling the callback.
                    if isinstance(submitted_text, str):
                        # Call the user's input handler, passing the control ID and the text.
                        self._input_text_callback(control_id, submitted_text)
                    else:
                        logger.warning(f"Control '{self.target_id}' received 'inputText' for '{control_id}' with non-string value: {payload}")
                except Exception as e:
                    # Catch errors within the user's callback.
                    logger.exception(f"Error occurred inside Control '{self.target_id}' on_input_text callback for control '{control_id}': {e}")
            else:
                # Log if we receive an event type we don't handle for this control ID,
                # or if the corresponding callback wasn't registered.
                logger.debug(f"Control '{self.target_id}': Received unhandled event '{event_type}' for control '{control_id}' or no callback registered.")

        # ALWAYS call the base class handler. This is crucial for processing
        # 'error' messages sent from the UI related to this specific control panel.
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to call when any button within this panel is clicked.

        When a user clicks a button (previously added using `add_button()`) in
        the Sidekick UI panel that belongs to this `Control` instance, the `callback`
        function you provide here will be executed within your running Python script.

        Args:
            callback (Optional[Callable[[str], None]]): The function to call
                when any button in this panel is clicked. This function must
                accept one argument:
                `control_id` (str): The unique identifier (the same ID you
                provided when calling `add_button`) of the specific button
                that was clicked.
                Pass `None` to remove any previously registered click callback.

        Raises:
            TypeError: If the provided `callback` is not a callable function (or `None`).

        Example:
            >>> controls = sidekick.Control()
            >>> controls.add_button("action_one", "Perform Action 1")
            >>> controls.add_button("action_two", "Do Something Else")
            >>>
            >>> def button_handler(button_that_was_clicked):
            ...     print(f"Button clicked: {button_that_was_clicked}")
            ...     if button_that_was_clicked == "action_one":
            ...         # Run action 1 logic...
            ...         print("Running action 1...")
            ...     elif button_that_was_clicked == "action_two":
            ...         # Run action 2 logic...
            ...         print("Doing something else...")
            ...
            >>> controls.on_click(button_handler)
            >>> sidekick.run_forever() # Keep script running
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for control panel '{self.target_id}'.")
        self._click_callback = callback

    def on_input_text(self, callback: Optional[Callable[[str, str], None]]):
        """Registers a function to call when text is submitted from any text input field within this panel.

        When a user types text into an input field (previously added using
        `add_text_input()`) within this `Control` instance's panel and clicks
        its associated "Submit" button in the Sidekick UI, the `callback` function
        you provide here will be executed in your running Python script.

        Args:
            callback (Optional[Callable[[str, str], None]]): The function to call
                when text is submitted from any input field in this panel. This
                function must accept two arguments:
                1. `control_id` (str): The unique identifier (the same ID you
                   provided when calling `add_text_input`) of the specific text
                   input group whose submit button was clicked.
                2. `value` (str): The text string that the user had entered into
                   the input field when they submitted it.
                Pass `None` to remove any previously registered input text callback.

        Raises:
            TypeError: If the provided `callback` is not a callable function (or `None`).

        Example:
            >>> controls = sidekick.Control()
            >>> controls.add_text_input("param_a", placeholder="Parameter A")
            >>> controls.add_text_input("param_b", placeholder="Parameter B", button_text="Set B")
            >>>
            >>> def input_handler(input_field_id, submitted_value):
            ...     print(f"Input received from '{input_field_id}': '{submitted_value}'")
            ...     if input_field_id == "param_a":
            ...         # Process parameter A...
            ...         print(f"Setting A to {submitted_value}")
            ...     elif input_field_id == "param_b":
            ...         # Process parameter B...
            ...         print(f"Setting B to {submitted_value}")
            ...
            >>> controls.input_text_handler(input_handler)
            >>> sidekick.run_forever() # Keep script running
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_input_text callback must be a callable function or None.")
        logger.info(f"Setting on_input_text callback for control panel '{self.target_id}'.")
        self._input_text_callback = callback

    # --- Error Callback ---
    # Inherits the on_error(callback) method directly from BaseModule.
    # Use `controls.on_error(my_handler)` to register a function that will be
    # called if the Control panel UI element itself reports an error back to Python
    # (e.g., if it failed to process an 'add' or 'remove' command internally).

    def add_button(self, control_id: str, button_text: str):
        """Adds a clickable button to this control panel in the Sidekick UI.

        Creates a button element within this `Control` instance's panel area.
        Clicking this button in the Sidekick UI will trigger the function
        registered using `on_click()`, passing this button's unique `control_id`
        to the callback function.

        Args:
            control_id (str): A unique identifier string for this specific button
                within this control panel. This ID is chosen by you and is crucial
                for identifying which button was pressed in the `on_click` callback.
                It must be a non-empty string.
            button_text (str): The text label that will appear visibly on the button in the UI.

        Raises:
            ValueError: If `control_id` is empty or not a string.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> controls = sidekick.Control()
            >>> controls.add_button("start_sim", "Start Simulation")
            >>> controls.add_button("reset_sim", "Reset")
            >>> # Add an on_click handler to react to these buttons...
        """
        # Validate the control_id provided by the user.
        if not isinstance(control_id, str) or not control_id:
            msg = "Control ID for add_button must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)
        # Ensure text is explicitly a string for the payload.
        button_label = str(button_text)

        # Prepare the payload for the 'update' command to add the control.
        # Keys must be camelCase for the communication protocol.
        payload = {
            "action": "add",          # Command type: add a new control
            "controlId": control_id,  # The unique ID for this new button
            "options": {
                "controlType": "button",       # Specify the type of control being added
                "config": {                    # Configuration settings specific to this control type
                    "buttonText": button_label # The text label for the button
                }
            }
        }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(payload)
        logger.debug(f"Control '{self.target_id}': Sent 'add' command for button '{control_id}'.")

    def add_text_input(
        self,
        control_id: str,
        placeholder: str = "",
        initial_value: str = "",
        button_text: str = ""
    ):
        """Adds a text input field paired with a submit button to the control panel.

        Creates a combined UI element in the Sidekick panel consisting of a text entry
        box and an adjacent button (labeled with `button_text`). When the user types
        text into the field and clicks the associated submit button, the function
        registered using `on_input_text()` is triggered. That callback function
        receives both this control's `control_id` and the text the user entered.

        Args:
            control_id (str): A unique identifier string for this specific text input
                group (the field + button combination) within this control panel.
                This ID is passed to the `on_input_text` callback. Must be a
                non-empty string.
            placeholder (str): Optional text displayed faintly inside the input field
                when it's empty, providing a hint to the user (e.g., "Enter name").
                Defaults to "".
            initial_value (str): Optional text pre-filled in the input field when it
                first appears in the UI. Defaults to "".
            button_text (str): Optional text label displayed on the submit button that's
                associated with this input field.

        Raises:
            ValueError: If `control_id` is empty or not a string.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> controls = sidekick.Control()
            >>> # Add a simple text input with a placeholder
            >>> controls.add_text_input("search_term", placeholder="Enter search query...")
            >>>
            >>> # Add an input with an initial value and a custom button label
            >>> controls.add_text_input("server_ip", initial_value="192.168.1.1", button_text="Set IP")
            >>> # Add an on_input_text handler to react to these inputs...
        """
        # Validate the control_id provided by the user.
        if not isinstance(control_id, str) or not control_id:
            msg = "Control ID for add_text_input must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)
        # Ensure other text parameters are explicitly strings for the payload.
        input_placeholder = str(placeholder)
        input_initial_value = str(initial_value)
        submit_button_label = str(button_text)

        # Prepare the payload for adding the text input control.
        # Keys must be camelCase for the protocol.
        payload = {
            "action": "add",          # Command type: add a new control
            "controlId": control_id,  # The unique ID for this new input group
            "options": {
                "controlType": "textInput", # Specify the type of control being added
                "config": {                 # Configuration settings specific to text inputs
                    "placeholder": input_placeholder,
                    "initialValue": input_initial_value,
                    "buttonText": submit_button_label,
                }
            }
        }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(payload)
        logger.debug(f"Control '{self.target_id}': Sent 'add' command for text input '{control_id}'.")

    def remove_control(self, control_id: str):
        """Removes a specific control (button or text input) from this panel in the UI.

        Use this method to dynamically remove a button or text input field that
        was previously added using `add_button()` or `add_text_input()`. You must
        provide the same unique `control_id` that you used when adding the control.

        Args:
            control_id (str): The unique identifier string of the control element
                (button or text input group) that you want to remove from the
                Sidekick UI panel. Must be a non-empty string matching the ID used
                during creation.

        Raises:
            ValueError: If `control_id` is empty or not a string.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> controls = sidekick.Control()
            >>> controls.add_button("temporary_task", "Run Once")
            >>> # ... some logic runs ...
            >>> # Now remove the button as it's no longer needed
            >>> controls.remove_control("temporary_task")
            >>>
            >>> controls.add_text_input("user_pin", "PIN")
            >>> # ... user enters PIN and it's processed ...
            >>> controls.remove_control("user_pin") # Remove the input field
        """
        # Validate the control_id provided by the user.
        if not isinstance(control_id, str) or not control_id:
            msg = "Control ID for remove_control must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)

        # Prepare the payload for the 'remove' action targeting a specific control.
        # Keys must be camelCase.
        payload = {
            "action": "remove",       # Command type: remove an existing control
            "controlId": control_id   # Specify which control ID to remove
            # No further 'options' are typically needed for the 'remove' action targeting a specific control.
        }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(payload)
        logger.debug(f"Control '{self.target_id}': Sent 'remove' command for control '{control_id}'.")

    def _reset_specific_callbacks(self):
        """Internal: Resets control-panel-specific callbacks when the module is removed.

        Called automatically by the base class's `remove()` method.
        """
        # Reset the callback references for this control panel.
        self._click_callback = None
        self._input_text_callback = None

    # --- Removal ---
    # Inherits the standard remove() method from BaseModule. Calling `controls.remove()`
    # will send a command to the Sidekick UI to remove this entire control panel instance
    # (including any controls currently inside it) and will perform local cleanup
    # (unregistering handlers, resetting callbacks).