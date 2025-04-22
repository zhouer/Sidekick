"""
Provides the Console class for displaying text output in Sidekick.

Use the `sidekick.Console` class to create a text area in the Sidekick panel,
similar to the standard Python terminal or console window. You can print messages
to it from your script using the `print()` method.

Optionally, you can include a text input field at the bottom, allowing the user
to type commands or data back into your running Python script.
"""

from . import logger
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Console(BaseModule):
    """Represents a Console module instance in the Sidekick UI panel.

    This creates a scrollable text area where you can send output using the
    `print()` method. Think of it as a dedicated output window for
    your script within the Sidekick panel.

    You can also configure it to show an input box (`show_input=True`), allowing
    two-way communication: your script prints messages, and the user can send
    text back.

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
        """Initializes the Console object and optionally creates the UI element.

        Sets up the console and determines if it should include an input field.

        Args:
            instance_id (Optional[str]): A specific ID for this console instance.
                - If `spawn=True` (default): Optional. Auto-generated if None.
                - If `spawn=False`: **Required**. Must match the ID of an existing console.
            spawn (bool): If True (default), creates a new console element in Sidekick.
                If False, attaches to an existing console element. `initial_text`
                and `show_input` are ignored if `spawn=False`.
            initial_text (str): A line of text to display immediately when the
                console is first created. Only used if `spawn=True`. Defaults to "".
            show_input (bool): If True, includes a text input field at the bottom
                of the console UI, allowing the user to type and submit text back
                to the script (handled via `on_input_text`). Defaults to False.
                Only used if `spawn=True`.

        Raises:
            ValueError: If `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established.

        Examples:
            >>> # Create a simple console for output only
            >>> output_console = sidekick.Console()
            >>> output_console.print("Script starting...")
            >>>
            >>> # Create an interactive console with an input field
            >>> input_console = sidekick.Console(show_input=True, initial_text="Enter your command:")
            >>> # (Need to use input_console.on_input_text() to handle input)
        """
        # Prepare the payload for the 'spawn' command if needed.
        spawn_payload: Dict[str, Any] = {}
        if spawn:
            # Keys must be camelCase for the protocol.
            spawn_payload["showInput"] = bool(show_input) # Ensure it's a boolean
            if initial_text: # Only include text if it's not empty
                 spawn_payload["text"] = str(initial_text) # Ensure it's a string

        # Initialize the base class (handles connection, ID, registration, spawn).
        super().__init__(
            module_type="console",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None
        )
        # Initialize the callback placeholder for text input.
        self._input_text_callback: Optional[Callable[[str], None]] = None
        logger.info(f"Console '{self.target_id}' initialized (spawn={spawn}, show_input={show_input if spawn else 'N/A'}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages specifically for this console instance.

        This overrides the base class method to add handling for 'inputText' events.
        It checks if the incoming message is an 'event' and if the event type is
        'inputText'. If so, and if an `on_input_text` callback is registered,
        it calls the callback function with the submitted text value.

        It still calls the base class's handler at the end to ensure 'error'
        messages are processed correctly.

        Args:
            message (Dict[str, Any]): The raw message dictionary received.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload keys are expected to be camelCase.

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            # Check if it's the specific event type we care about ('inputText')
            # and if the user has registered a function to handle it.
            if event_type == "inputText" and self._input_text_callback:
                try:
                    # Extract the submitted text value.
                    value = payload.get("value")
                    if isinstance(value, str):
                        # Call the user's registered function!
                        self._input_text_callback(value)
                    else:
                         # Log a warning if the payload format is unexpected.
                         logger.warning(f"Console '{self.target_id}' received inputText event with non-string value: {payload}")
                except Exception as e:
                    # Catch errors within the user's callback to prevent crashing.
                    logger.exception(f"Error in Console '{self.target_id}' on_input_text callback: {e}")
            else:
                 # Log other event types if needed for debugging.
                 logger.debug(f"Console '{self.target_id}' received unhandled event type '{event_type}'.")

        # Important: Call the base class's handler AFTER checking for our specific
        # events. This ensures error messages are still handled.
        super()._internal_message_handler(message)

    def on_input_text(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to call when the user submits text from the input field.

        If you created this console using `show_input=True`, an input box appears
        in the Sidekick UI. When the user types text into that box and presses
        Enter (or clicks the associated submit button), the `callback` function
        you provide here will be executed in your Python script.

        Args:
            callback (Optional[Callable[[str], None]]): The function to call when
                text is submitted. This function should accept one argument:
                a string containing the text entered by the user.
                Pass `None` to remove any previously registered callback.

        Raises:
            TypeError: If the provided `callback` is not a function (or None).

        Returns:
            None

        Examples:
            >>> def process_user_command(command):
            ...     console.print(f"You entered: {command}")
            ...     if command.lower() == "quit":
            ...         console.print("Okay, shutting down.")
            ...         sidekick.shutdown()
            ...     else:
            ...         console.print(f"Running command: {command}...")
            ...
            >>> console = sidekick.Console(show_input=True)
            >>> console.on_input_text(process_user_command)
            >>> console.print("Enter a command (or 'quit' to exit):")
            >>>
            >>> # Important: Keep the script running to listen for input!
            >>> sidekick.run_forever()
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_input_text callback must be a callable function or None.")
        logger.info(f"Setting on_input_text callback for console '{self.target_id}'.")
        self._input_text_callback = callback

    # --- Error Callback ---
    # Inherits on_error(callback) method from BaseModule. Use this to handle
    # potential errors reported by the Console UI element itself.

    def print(self, *args: Any, sep: str = ' ', end: str = '\n'):
        """Prints messages to this console instance in the Sidekick UI, adding a newline by default.

        This works very similarly to Python's built-in `print()` function.
        It converts all arguments (`args`) to strings, joins them together
        using the `sep` separator, and appends the `end` string (which defaults
        to a newline character `\\n`). The resulting string is then displayed
        as appended text in the Sidekick console.

        Args:
            *args (Any): One or more objects to print. They will be automatically
                converted to their string representation (using `str()`).
            sep (str): The separator string inserted between arguments. Defaults
                to a single space (' ').
            end (str): The string appended after the last argument. Defaults to
                a newline character ('\\n'). To print without adding a newline,
                use `end=''`.

        Returns:
            None

        Examples:
            >>> console = sidekick.Console()
            >>> name = "Alice"
            >>> console.print("Hello, ", end="")
            >>> console.print(name, "!")
        """
        # Convert all arguments to strings and join them.
        text_to_print = sep.join(map(str, args)) + end
        # Prepare the payload for the 'update' command.
        # Action 'append' tells the UI to add this text.
        # Key 'text' must be camelCase.
        payload = {
            "action": "append",
            "options": { "text": text_to_print }
        }
        # Send the command.
        self._send_update(payload)

    def clear(self):
        """Removes all previously printed text from this console instance in Sidekick.

        This clears the entire text area of the console UI element.

        Returns:
            None

        Examples:
            >>> console.print("Line 1")
            >>> console.print("Line 2")
            >>> # Wait a bit
            >>> import time; time.sleep(1)
            >>> console.clear() # Console UI becomes empty
        """
        logger.info(f"Requesting clear for console '{self.target_id}'.")
        # Action 'clear' tells the UI to remove all content. No options needed.
        payload = { "action": "clear" }
        # Send the command.
        self._send_update(payload)

    def _reset_specific_callbacks(self):
        """Resets console-specific callbacks when the module is removed."""
        # Called by BaseModule.remove()
        self._input_text_callback = None

    # --- Removal ---
    # Inherits the remove() method from BaseModule to remove the console element.