"""Provides the Button class for creating clickable buttons in Sidekick.

Use the `sidekick.Button` class to add a standard clickable button to your
Sidekick UI panel. Clicking the button in the UI triggers a callback function
in your Python script.

Buttons can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization.
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Callable, Dict, Any, Union

class Button(BaseComponent):
    """Represents a clickable Button component instance in the Sidekick UI.

    Creates a button with a text label. Use the `on_click` method or the
    `@button.click` decorator to define what happens in Python when the
    button is clicked in the UI.

    Attributes:
        target_id (str): The unique identifier for this button instance.
        text (str): The text label currently displayed on the button.
    """
    def __init__(
        self,
        text: str = "Button",
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes the Button object and creates the UI element.

        Args:
            text (str): The initial text label displayed on the button.
                Defaults to "Button".
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, added to the root container.

        Raises:
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        self._text = str(text)
        # Callback function provided by the user via on_click or decorator.
        # Note: Button click callbacks don't receive arguments.
        self._click_callback: Optional[Callable[[], None]] = None

        # Prepare the payload for the 'spawn' command.
        # Keys must be camelCase per the protocol.
        spawn_payload: Dict[str, Any] = {
            "text": self._text
        }

        super().__init__(
            component_type="button",
            payload=spawn_payload,
            parent=parent # Pass parent to BaseComponent
        )
        logger.info(f"Button '{self.target_id}' initialized with text '{self._text}'.")

    @property
    def text(self) -> str:
        """str: The text label currently displayed on the button.

        Setting this property updates the button's text in the Sidekick UI.
        """
        return self._text

    @text.setter
    def text(self, new_text: str):
        """Sets the text label displayed on the button."""
        new_text_str = str(new_text)
        # Update local state first
        self._text = new_text_str
        # Prepare payload for the 'setText' update action.
        # Keys must be camelCase per the protocol.
        payload = {
            "action": "setText",
            "options": {"text": new_text_str}
        }
        # Send the update command to the UI.
        self._send_update(payload)
        logger.debug(f"Button '{self.target_id}' text set to '{new_text_str}'.")

    def on_click(self, callback: Optional[Callable[[], None]]):
        """Registers a function to be called when this button is clicked.

        The provided callback function will be executed in your Python script
        when the user clicks this specific button in the Sidekick UI. The callback
        function should not accept any arguments.

        Args:
            callback (Optional[Callable[[], None]]): The function to call on click.
                Pass `None` to remove the current callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for button '{self.target_id}'.")
        self._click_callback = callback

    def click(self, func: Callable[[], None]) -> Callable[[], None]:
        """Decorator to register a function to be called when this button is clicked.

        This provides an alternative, more Pythonic way to set the click handler.

        Args:
            func (Callable[[], None]): The function to register as the click handler.
                It should not accept any arguments.

        Returns:
            Callable[[], None]: The original function, allowing the decorator to be used directly.

        Raises:
            TypeError: If `func` is not a callable function.

        Example:
            >>> my_button = sidekick.Button("Run Me")
            >>>
            >>> @my_button.click
            ... def handle_button_press():
            ...     print("Button was clicked!")
            ...     # Perform some action...
        """
        self.on_click(func) # Register the function using the standard method
        return func # Return the original function

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' messages for this button. (Internal)."""
        msg_type = message.get("type")
        payload = message.get("payload")

        # Check if it's a click event targeted at this button instance.
        if msg_type == "event" and payload and payload.get("event") == "click":
            logger.debug(f"Button '{self.target_id}' received click event.")
            # If a user callback is registered, execute it.
            if self._click_callback:
                try:
                    self._click_callback() # Call the user's function
                except Exception as e:
                    # Prevent errors in user callback from crashing the listener.
                    logger.exception(
                        f"Error occurred inside Button '{self.target_id}' on_click callback: {e}"
                    )
            # No specific data needs extraction from a simple button click payload.

        # Always call the base handler for potential 'error' messages.
        super()._internal_message_handler(message)

    def _reset_specific_callbacks(self):
        """Internal: Resets button-specific callbacks."""
        super()._reset_specific_callbacks()
        self._click_callback = None