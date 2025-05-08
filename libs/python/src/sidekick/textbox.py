"""Provides the Textbox class for creating text input fields in Sidekick.

Use the `sidekick.Textbox` class to add a single-line text input field to your
Sidekick UI panel. Users can type text into this field. When they press Enter
or the field loses focus (on-blur), the entered text is sent back to your Python
script, triggering a callback function you define.

Textboxes can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization.
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Callable, Dict, Any, Union

class Textbox(BaseComponent):
    """Represents a single-line Textbox component instance in the Sidekick UI.

    Creates an input field where users can type text. Use the `on_submit`
    method or the `@textbox.submit` decorator to define a Python function that
    receives the text when the user submits it (e.g., by pressing Enter or on blur).

    The `value` property allows you to programmatically get or set the text
    currently displayed in the textbox.

    Attributes:
        target_id (str): The unique identifier for this textbox instance.
        value (str): The current text content of the textbox.
        placeholder (str): The placeholder text displayed when the box is empty.
    """
    def __init__(
        self,
        initial_value: str = "",
        placeholder: str = "",
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes the Textbox object and creates the UI element.

        Args:
            initial_value (str): The text initially displayed in the input field.
                Defaults to "".
            placeholder (str): Hint text shown when the input field is empty.
                Defaults to "".
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, added to the root container.

        Raises:
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        self._value = str(initial_value)
        self._placeholder = str(placeholder)
        # Callback function provided by the user via on_submit or decorator.
        # It receives the submitted text value as an argument.
        self._submit_callback: Optional[Callable[[str], None]] = None

        # Prepare the payload for the 'spawn' command.
        # Keys must be camelCase per the protocol.
        spawn_payload: Dict[str, Any] = {}
        # Only include keys if they have non-default values, as per protocol examples.
        if self._value:
            spawn_payload["initialValue"] = self._value
        if self._placeholder:
            spawn_payload["placeholder"] = self._placeholder

        super().__init__(
            component_type="textbox",
            payload=spawn_payload,
            parent=parent # Pass parent to BaseComponent
        )
        logger.info(f"Textbox '{self.target_id}' initialized.")

    @property
    def value(self) -> str:
        """str: The current text content of the textbox.

        Reading this property returns the value stored locally in the Python object,
        which is updated when the user submits text from the UI.

        Setting this property updates the local value and sends a command to update
        the text displayed in the Sidekick UI's input field.
        """
        return self._value

    @value.setter
    def value(self, new_text_value: str):
        """Sets the text content displayed in the textbox."""
        new_val_str = str(new_text_value)
        # Update local state first
        self._value = new_val_str
        # Prepare payload for the 'setValue' update action.
        # Keys must be camelCase per the protocol.
        payload = {
            "action": "setValue",
            "options": {"value": new_val_str}
        }
        # Send the update command to the UI.
        self._send_update(payload)
        logger.debug(f"Textbox '{self.target_id}' value set to '{new_val_str}'.")

    @property
    def placeholder(self) -> str:
        """str: The placeholder text displayed when the textbox is empty.

        Setting this property updates the placeholder in the Sidekick UI.
        """
        return self._placeholder

    @placeholder.setter
    def placeholder(self, new_placeholder: str):
        """Sets the placeholder text displayed when the textbox is empty."""
        new_ph_str = str(new_placeholder)
        # Update local state
        self._placeholder = new_ph_str
        # Prepare payload for the 'setPlaceholder' update action.
        payload = {
            "action": "setPlaceholder",
            "options": {"placeholder": new_ph_str}
        }
        # Send the update command to the UI.
        self._send_update(payload)
        logger.debug(f"Textbox '{self.target_id}' placeholder set to '{new_ph_str}'.")

    def on_submit(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to call when the user submits text from this textbox.

        The submission typically happens when the user presses Enter while the
        textbox has focus, or when the input field loses focus (on-blur event).
        The provided callback function receives the submitted text.

        Args:
            callback (Optional[Callable[[str], None]]): The function to call on submit.
                It must accept one argument: the string value submitted by the user.
                Pass `None` to remove the current callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_submit callback must be a callable function or None.")
        logger.info(f"Setting on_submit callback for textbox '{self.target_id}'.")
        self._submit_callback = callback

    def submit(self, func: Callable[[str], None]) -> Callable[[str], None]:
        """Decorator to register a function to call when the user submits text.

        Provides an alternative syntax to `on_submit()`.

        Args:
            func (Callable[[str], None]): The function to register. Must accept one
                string argument (the submitted value).

        Returns:
            Callable[[str], None]: The original function.

        Raises:
            TypeError: If `func` is not a callable function.

        Example:
            >>> name_input = sidekick.Textbox(placeholder="Enter name")
            >>>
            >>> @name_input.submit
            ... def handle_name(submitted_name):
            ...     print(f"Hello, {submitted_name}!")
        """
        self.on_submit(func)
        return func

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' messages for this textbox. (Internal)."""
        msg_type = message.get("type")
        payload = message.get("payload")

        # Check if it's a submit event targeted at this textbox instance.
        if msg_type == "event" and payload and payload.get("event") == "submit":
            submitted_value = payload.get("value", "") # Default to empty string if missing
            logger.debug(f"Textbox '{self.target_id}' received submit event with value: '{submitted_value}'")

            # Ensure local value matches submitted value (maintaining consistency)
            # Ensure it's stored as a string.
            self._value = str(submitted_value)

            # If a user callback is registered, execute it with the submitted value.
            if self._submit_callback:
                try:
                    # Pass the locally updated (and validated as string) value.
                    self._submit_callback(self._value)
                except Exception as e:
                    # Prevent errors in user callback from crashing the listener.
                    logger.exception(
                        f"Error occurred inside Textbox '{self.target_id}' on_submit callback: {e}"
                    )

        # Always call the base handler for potential 'error' messages.
        super()._internal_message_handler(message)

    def _reset_specific_callbacks(self):
        """Internal: Resets textbox-specific callbacks."""
        super()._reset_specific_callbacks()
        self._submit_callback = None