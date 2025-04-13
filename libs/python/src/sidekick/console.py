"""
Sidekick Console Module Interface.

This module provides the `Console` class, which represents a text console
displayed in the Sidekick panel. It's similar to Python's built-in console
where you use `print()`, but it appears visually within Sidekick.

You can use it to:
  - Print messages and log information from your script.
  - Optionally display an input field for the user to type text back to your script.
"""

from . import logger
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Console(BaseModule):
    """Represents a Console module instance in the Sidekick UI.

    Use this class to print text output from your Python script to a dedicated
    scrolling area in the Sidekick panel. You can also optionally add an input
    field to allow the user to type text back to your script.

    Attributes:
        target_id (str): The unique identifier for this console instance.
    """
    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        initial_text: str = "",
        show_input: bool = False
    ):
        """Initializes or attaches to a Console module in the Sidekick UI.

        Sets up the console and configures whether it should display an input field.

        Args:
            instance_id (Optional[str]): A specific ID for this console instance.
                - If `spawn=True`: Optional. Auto-generated if None.
                - If `spawn=False`: **Required**. Identifies the existing console.
            spawn (bool): If True (default), creates a new console UI element.
                If False, attaches to an existing console. `initial_text` and
                `show_input` are ignored if `spawn=False`.
            initial_text (str): A line of text to display immediately when the
                console is created. Only used if `spawn=True`. Defaults to "".
            show_input (bool): If True, displays a text input field at the bottom
                of the console in Sidekick, allowing the user to send text back
                to your script via the `on_input_text` callback. Defaults to False.
                Only used if `spawn=True`.

        Raises:
            ValueError: If `spawn` is False and `instance_id` is None.

        Examples:
            >>> # Create a simple console for output only
            >>> output_console = sidekick.Console()
            >>> output_console.print("Script started.")
            >>>
            >>> # Create an interactive console with an input field
            >>> interactive_console = sidekick.Console(show_input=True, initial_text="Enter command:")

        """
        spawn_payload: Dict[str, Any] = {}
        if spawn:
            # Validate showInput during spawn
            if show_input is None or not isinstance(show_input, bool):
                 raise ValueError(f"Console spawn requires a boolean 'show_input', got {show_input}")
            spawn_payload["showInput"] = show_input # camelCase key
            if initial_text:
                 spawn_payload["text"] = initial_text

        # Initialize the base class
        super().__init__(
            module_type="console",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None
        )
        self._input_text_callback: Optional[Callable[[str], None]] = None
        logger.info(f"Console '{self.target_id}' initialized (spawn={spawn}, show_input={show_input if spawn else 'N/A'}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages for this console instance."""
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "inputText" and self._input_text_callback:
                try:
                    value = payload.get("value")
                    if isinstance(value, str):
                        self._input_text_callback(value)
                    else:
                         logger.warning(f"Console '{self.target_id}' received inputText event with non-string value: {payload}")
                except Exception as e:
                    logger.exception(f"Error in Console '{self.target_id}' on_input_text callback: {e}")
            else:
                 logger.debug(f"Console '{self.target_id}' received unhandled event type '{event_type}'.")

        # Call base handler for error messages
        super()._internal_message_handler(message)

    def on_input_text(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to handle text submitted from the Sidekick input field.

        If you created the console with `show_input=True`, the user can type text
        into the input field in Sidekick and press Enter (or click a submit button).
        When they do, the function you register here will be called with the text
        they entered.

        Args:
            callback (Optional[Callable[[str], None]]): A function that takes one
                argument (the submitted text string). Pass `None` to remove the
                current callback.

        Raises:
            TypeError: If the provided callback is not callable or None.

        Examples:
            >>> def process_command(command):
            ...     print(f"Processing command: {command}")
            ...     if command == "quit":
            ...         sidekick.shutdown()
            >>>
            >>> interactive_console = sidekick.Console(show_input=True)
            >>> interactive_console.on_input_text(process_command)
            >>> interactive_console.print("Enter 'quit' to exit.")
            >>> # sidekick.run_forever() # Needed to keep script alive for input

        Returns:
            None
        """
        if callback is not None and not callable(callback):
            raise TypeError("Input text callback must be callable or None")
        logger.info(f"Setting on_input_text callback for console '{self.target_id}'.")
        self._input_text_callback = callback

    # on_error is inherited from BaseModule

    def print(self, *args: Any, sep: str = ' ', end: str = ''):
        """Prints text to this console module instance in Sidekick.

        Works like the built-in Python `print` function, converting arguments
        to strings and joining them with the separator. Appends the `end` string.

        Args:
            *args (Any): One or more objects to print. They will be converted to strings.
            sep (str): Separator inserted between objects. Defaults to a space ' '.
            end (str): String appended after the last object. Defaults to ''.
                       Use `end='\\n'` to mimic the default newline behavior of
                       Python's `print`.

        Examples:
            >>> console = sidekick.Console()
            >>> name = "World"
            >>> count = 10
            >>> console.print("Hello,", name) # Prints "Hello, World"
            >>> console.print("Count:", count, "items", end="\\n") # Prints "Count: 10 items" and a newline
            >>> console.print("Processing...") # Prints "Processing..."

        Returns:
            None
        """
        text_to_print = sep.join(map(str, args)) + end
        payload = {
            "action": "append",
            "options": { "text": text_to_print } # camelCase key
        }
        self._send_update(payload)

    def log(self, message: Any):
        """A convenient shortcut for printing a single message.

        Equivalent to calling `console.print(message, end='')`.

        Args:
            message (Any): The object to print (will be converted to string).

        Examples:
            >>> console.log("Debug message 1")
            >>> console.log(f"Current value: {some_variable}")

        Returns:
            None
        """
        self.print(message, end='') # Changed default end to '' to match docstring

    def clear(self):
        """Removes all text currently displayed in this console instance in Sidekick.

        Examples:
            >>> console.print("Line 1")
            >>> console.print("Line 2")
            >>> time.sleep(1)
            >>> console.clear() # Clears "Line 1" and "Line 2"

        Returns:
            None
        """
        logger.info(f"Requesting clear for console '{self.target_id}'.")
        payload = { "action": "clear" }
        self._send_update(payload)

    def _reset_specific_callbacks(self):
        """Resets console-specific callbacks on removal."""
        self._input_text_callback = None

    # remove() is inherited from BaseModule