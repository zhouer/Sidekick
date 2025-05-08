"""Provides the Console class for displaying text output in Sidekick.

Use the `sidekick.Console` class to create a dedicated text area within the
Sidekick panel. This acts like a separate terminal or output window specifically
for your script, allowing you to display status messages, log information, or
show results without cluttering the main VS Code terminal.

The console can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization.

Key Features:

*   **Text Output:** Use the `print()` method (similar to Python's built-in `print`)
    to append text messages to the console area.
*   **Optional Text Input:** Configure the console (`show_input=True`) to include
    a text input field at the bottom. Users can type text into this field and
    submit it back to your running Python script.
*   **Input Handling:** Use the `on_input_text()` method to register a callback
    function that gets executed whenever the user submits text from the input field.
*   **Clearing:** Use the `clear()` method to remove all previously displayed text.

Basic Usage:
    >>> import sidekick
    >>> console = sidekick.Console() # Created in the root container
    >>> console.print("Script starting...")

Interactive Usage with a Parent Container:
    >>> import sidekick
    >>> my_column = sidekick.Column()
    >>> console = sidekick.Console(show_input=True, parent=my_column)
    >>>
    >>> def handle_command(user_text):
    ...     console.print(f"Received: '{user_text}'")
    ...
    >>> console.on_input_text(handle_command) # Renamed from input_text_handler
    >>> # sidekick.run_forever() # Keep script running
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Callable, Dict, Any, Union # Added Union

class Console(BaseComponent):
    """Represents a Console component instance in the Sidekick UI panel.

    Creates a scrollable text area for displaying output and optionally an input field.
    Can be nested within layout containers.

    Attributes:
        target_id (str): The unique identifier for this console instance.
    """
    def __init__(
        self,
        initial_text: str = "",
        show_input: bool = False,
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes the Console object and creates the UI element.

        Args:
            initial_text (str): Text to display immediately. Defaults to "".
            show_input (bool): If True, show an input field. Defaults to False.
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, added to the root container.

        Raises:
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        spawn_payload: Dict[str, Any] = {
            "showInput": bool(show_input)
        }
        if initial_text: # Only include if not empty, to match protocol example
             spawn_payload["text"] = str(initial_text)

        super().__init__(
            component_type="console",
            payload=spawn_payload,
            parent=parent # Pass the parent argument to BaseComponent
        )
        self._input_text_callback: Optional[Callable[[str], None]] = None
        logger.info(f"Console '{self.target_id}' initialized (show_input={show_input}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this console. (Internal)."""
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "inputText" and self._input_text_callback:
                try:
                    submitted_text = payload.get("value")
                    if isinstance(submitted_text, str):
                        self._input_text_callback(submitted_text)
                    else:
                         logger.warning(
                            f"Console '{self.target_id}' received 'inputText' event "
                            f"with non-string value: {payload}"
                         )
                except Exception as e:
                    logger.exception(
                        f"Error occurred inside Console '{self.target_id}' "
                        f"on_input_text callback: {e}"
                    )
            else:
                 logger.debug(
                    f"Console '{self.target_id}' received unhandled event type '{event_type}' "
                    f"or no input callback registered."
                 )
        super()._internal_message_handler(message)

    def on_input_text(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to call when the user submits text.

        Relevant only if `show_input=True` during initialization.

        Args:
            callback (Optional[Callable[[str], None]]): Function to call.
                It must accept one string argument (the submitted text).
                Pass `None` to remove a callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_input_text callback must be a callable function or None.")
        logger.info(f"Setting on_input_text callback for console '{self.target_id}'.")
        self._input_text_callback = callback

    # `input_text_handler` was renamed to `on_input_text` in the prompt.
    # If you need to keep `input_text_handler` for backward compatibility,
    # you can add it as an alias:
    # def input_text_handler(self, callback: Optional[Callable[[str], None]]):
    #     """Alias for on_input_text."""
    #     self.on_input_text(callback)

    def print(self, *args: Any, sep: str = ' ', end: str = '\n'):
        """Prints messages to this console instance in the Sidekick UI.

        Args:
            *args (Any): Objects to print, converted to strings.
            sep (str): Separator between arguments. Defaults to ' '.
            end (str): String appended at the end. Defaults to '\\n'.

        Raises:
            SidekickConnectionError: If sending command fails.
        """
        text_to_print = sep.join(map(str, args)) + end
        payload = {
            "action": "append",
            "options": { "text": text_to_print }
        }
        self._send_update(payload)

    def clear(self):
        """Removes all previously printed text from this console instance.

        Raises:
            SidekickConnectionError: If sending command fails.
        """
        logger.info(f"Requesting clear for console '{self.target_id}'.")
        payload = { "action": "clear" }
        self._send_update(payload)

    def _reset_specific_callbacks(self):
        """Internal: Resets console-specific callbacks."""
        super()._reset_specific_callbacks()
        self._input_text_callback = None