"""Provides the Console class for displaying text output in Sidekick.

Use the `sidekick.Console` class to create a dedicated text area within the
Sidekick panel. This acts like a separate terminal or output window specifically
for your script, allowing you to display status messages, log information, or
show results without cluttering the main VS Code terminal.

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
    >>> # Create a simple console for output only
    >>> console = sidekick.Console()
    >>> console.print("Script starting...")
    >>> for i in range(3):
    ...     console.print(f"Processing item {i+1}...")
    >>> console.print("Script finished.")

Interactive Usage:
    >>> import sidekick
    >>> console = sidekick.Console(show_input=True, initial_text="Enter command:")
    >>>
    >>> def handle_command(user_text):
    ...     console.print(f"Received: '{user_text}'")
    ...     if user_text.lower() == 'quit':
    ...         sidekick.shutdown() # Example: stop the script
    ...
    >>> console.input_text_handler(handle_command)
    >>> sidekick.run_forever() # Keep script running to listen for input
"""

from . import logger
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Console(BaseModule):
    """Represents a Console module instance in the Sidekick UI panel.

    Creates a scrollable text area for displaying output from your script via
    its `print()` method. Optionally includes a text input field at the bottom
    to receive input from the user in the Sidekick panel.

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

        Sets up the console and configures its appearance (e.g., whether to show
        an input field). Establishes the connection to Sidekick if not already done.

        Args:
            instance_id (Optional[str]): A specific ID for this console instance.
                - If `spawn=True` (default): Optional. If None, a unique ID (e.g.,
                  "console-1") is generated automatically.
                - If `spawn=False`: **Required**. Must match the ID of an existing
                  console element in the Sidekick UI to attach to.
            spawn (bool): If True (the default), a command is sent to Sidekick
                to create a new console UI element. If False, the library assumes
                a console element with the given `instance_id` already exists, and
                this Python object simply connects to it. `initial_text` and
                `show_input` arguments are ignored if `spawn=False`.
            initial_text (str): A line of text to display immediately when the
                console UI element is first created. Only used if `spawn=True`.
                Defaults to an empty string "".
            show_input (bool): If True, an input field and submit button are included
                at the bottom of the console UI, allowing the user to type and send
                text back to the script (handled via `on_input_text()`). If False
                (default), only the text output area is shown. Only used if `spawn=True`.

        Raises:
            ValueError: If `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established during initialization.

        Examples:
            >>> # Simple output-only console
            >>> log_console = sidekick.Console()
            >>> log_console.print("Program log started.")
            >>>
            >>> # Interactive console waiting for user input
            >>> interactive_console = sidekick.Console(show_input=True, initial_text="Enter your name:")
            >>> # (Requires using interactive_console.on_input_text() and sidekick.run_forever())
        """
        # --- Prepare Spawn Payload ---
        # Payload is only needed if we are creating (spawning) a new console.
        spawn_payload: Dict[str, Any] = {}
        if spawn:
            # Keys must be camelCase for the protocol specification.
            spawn_payload["showInput"] = bool(show_input) # Ensure it's a boolean value
            # Only include initial text in payload if it's not empty.
            if initial_text:
                 spawn_payload["text"] = str(initial_text) # Ensure it's a string

        # --- Initialize Base Class ---
        # This handles connection activation, ID assignment, handler registration,
        # and sending the 'spawn' command with the payload if spawn=True.
        super().__init__(
            module_type="console",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None # Send payload only if spawning
        )
        # --- Initialize Callback ---
        # Placeholder for the user's input text callback function.
        self._input_text_callback: Optional[Callable[[str], None]] = None
        # Log initialization details.
        spawn_info = f"show_input={show_input}" if spawn else "attaching to existing"
        logger.info(f"Console '{self.target_id}' initialized ({spawn_info}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this console. (Internal).

        Overrides the base class method to specifically process 'inputText' events
        originating from the console's input field (if `show_input=True`). When
        an 'inputText' event arrives, it extracts the submitted text value from the
        payload and, if an `on_input_text` callback function is registered, calls
        that function with the text.

        It delegates to the base class's handler (`super()._internal_message_handler`)
        at the end to ensure standard 'error' message processing still occurs.

        Args:
            message (Dict[str, Any]): The raw message dictionary received. Expected
                payload keys are camelCase.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload keys are expected to be camelCase.

        # Handle 'event' messages specifically
        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            # Check if it's the specific event type we care about ('inputText')
            # AND if the user has registered a function via on_input_text().
            if event_type == "inputText" and self._input_text_callback:
                try:
                    # Extract the submitted text value from the payload's 'value' field.
                    submitted_text = payload.get("value")
                    # Ensure the value is actually a string before calling the callback.
                    if isinstance(submitted_text, str):
                        # Call the user's registered callback function with the text!
                        self._input_text_callback(submitted_text)
                    else:
                         # Log a warning if the payload format is unexpected.
                         logger.warning(f"Console '{self.target_id}' received 'inputText' event with non-string value: {payload}")
                except Exception as e:
                    # IMPORTANT: Catch errors *within* the user's callback function
                    # to prevent crashing the library's background listener thread.
                    logger.exception(f"Error occurred inside Console '{self.target_id}' on_input_text callback: {e}")
            else:
                 # Log other event types or if no callback was set.
                 logger.debug(f"Console '{self.target_id}' received unhandled event type '{event_type}' or no input callback registered.")

        # ALWAYS call the base class handler. This is crucial for processing
        # 'error' messages sent from the UI related to this specific console instance.
        super()._internal_message_handler(message)

    def on_input_text(self, callback: Optional[Callable[[str], None]]):
        """Registers a function to call when the user submits text via the input field.

        This method is only relevant if you created the console with `show_input=True`.
        When the user types text into the input box in the Sidekick UI panel and then
        presses Enter (or clicks the associated submit button), the `callback` function
        you provide here will be executed within your running Python script.

        Args:
            callback (Optional[Callable[[str], None]]): The function to call when
                text is submitted. This function must accept one argument:
                a string containing the exact text entered and submitted by the user.
                Pass `None` to remove any previously registered callback.

        Raises:
            TypeError: If the provided `callback` is not a callable function (or `None`).

        Example:
            >>> import sidekick
            >>> console = sidekick.Console(show_input=True)
            >>>
            >>> def process_user_input(text_from_user):
            ...     console.print(f"Processing command: {text_from_user}")
            ...     # Add logic here based on the input...
            ...     if text_from_user.lower() == "quit":
            ...         console.print("Exiting now.")
            ...         sidekick.shutdown() # Stop run_forever
            ...
            >>> console.input_text_handler(process_user_input)
            >>> console.print("Enter commands below (type 'quit' to exit):")
            >>>
            >>> # Keep the script running to listen for the user's input!
            >>> sidekick.run_forever()
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_input_text callback must be a callable function or None.")
        logger.info(f"Setting on_input_text callback for console '{self.target_id}'.")
        self._input_text_callback = callback

    # --- Error Callback ---
    # Inherits the on_error(callback) method directly from BaseModule.
    # Use `console.on_error(my_handler)` to register a function that will be
    # called if the Console UI element itself reports an error back to Python
    # (e.g., if it failed to process an 'append' or 'clear' command internally).

    def print(self, *args: Any, sep: str = ' ', end: str = '\n'):
        """Prints messages to this console instance in the Sidekick UI.

        Works very much like Python's built-in `print()` function. It converts
        all positional arguments (`args`) to their string representations, joins
        them together using the `sep` string as a separator, and finally appends
        the `end` string (which defaults to a newline character `\\n`, causing
        each call to typically start on a new line in the console).

        The resulting string is then sent to the Sidekick UI to be appended to the
        console's text area.

        Args:
            *args (Any): One or more objects to print. They will be automatically
                converted to strings using `str()`.
            sep (str): The separator string inserted between multiple arguments.
                Defaults to a single space (' ').
            end (str): The string appended at the very end, after all arguments
                and separators. Defaults to a newline character ('\\n'). Set this
                to `end=''` to print without starting a new line afterwards.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending the command fails.

        Examples:
            >>> console = sidekick.Console()
            >>> name = "World"
            >>> count = 5
            >>> console.print("Hello,", name, "!") # Output: Hello, World !
            >>> console.print("Count:", count, sep='=') # Output: Count:=5
            >>> console.print("Processing...", end='') # Prints without a newline
            >>> console.print("Done.") # Prints on the same line as "Processing..."
        """
        # Convert all arguments to strings and join them with the separator.
        text_to_print = sep.join(map(str, args)) + end
        # Prepare the payload for the 'update' command.
        # Action 'append' tells the UI to add this text to the end.
        # Key 'text' must be camelCase for the protocol.
        payload = {
            "action": "append",
            "options": { "text": text_to_print } # camelCase key
        }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(payload)

    def clear(self):
        """Removes all previously printed text from this console instance in Sidekick.

        This effectively empties the console's text area in the UI panel.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending the command fails.

        Example:
            >>> console = sidekick.Console()
            >>> console.print("Message 1")
            >>> console.print("Message 2")
            >>> import time; time.sleep(1) # Wait a second
            >>> console.clear() # The console in Sidekick becomes empty
            >>> console.print("Cleared!")
        """
        logger.info(f"Requesting clear for console '{self.target_id}'.")
        # Prepare the payload for the 'clear' action. No options are needed.
        payload = { "action": "clear" }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(payload)

    def _reset_specific_callbacks(self):
        """Internal: Resets console-specific callbacks when the module is removed.

        Called automatically by the base class's `remove()` method.
        """
        # Reset the input text callback reference.
        self._input_text_callback = None

    # --- Removal ---
    # Inherits the standard remove() method from BaseModule. Calling `console.remove()`
    # will send a command to the Sidekick UI to remove this console panel instance
    # and will perform local cleanup (unregistering handlers, resetting callbacks).