# Sidekick/libs/python/src/sidekick/console.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Console(BaseModule):
    """
    Represents a Console module instance in the Sidekick UI.

    Allows printing text output to a scrolling area in Sidekick. You can also
    clear the console area. Optionally, an input field can be displayed below
    the output area, allowing the user to type text and send it back to your
    Python script via a callback function.

    This class can either create a new console instance in Sidekick or attach
    to a pre-existing one.

    Attributes:
        target_id (str): The unique identifier for this console instance.
    """
    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        initial_text: str = "",
        show_input: bool = False,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Initializes or attaches to a Console module in the Sidekick UI.

        Args:
            instance_id (Optional[str]): A specific ID for this console instance.
                Useful if you want to ensure you are always interacting with the same
                console UI element across script runs (requires `spawn=False`).
                - If `spawn=True`: Optional. If None, an ID will be generated automatically.
                - If `spawn=False`: **Required**. Specifies the ID of the existing
                  console instance in Sidekick to attach to.
            spawn (bool): If True (default), creates a new console instance in Sidekick.
                Sends a 'spawn' command with the configuration (like `showInput`).
                If False, attaches to an existing console with `instance_id`.
                No 'spawn' command sent, and `initial_text`/`show_input` are ignored.
            initial_text (str): Text line to display immediately upon creation.
                Only used if `spawn=True`. Defaults to "".
            show_input (bool): If True, displays a text input field and a send button
                below the console output area in Sidekick. Defaults to False (no input shown).
                Only used if `spawn=True`.
            on_message (Optional[Callable]): A function to call when the user sends
                input from the Sidekick UI (only relevant if `show_input=True`).
                The function will receive a single dictionary argument representing the
                message from Sidekick. For input events, the payload will look like:
                `{'event': 'inputText', 'value': submitted_text}`.
                Make sure the function you provide can accept one argument.

        Raises:
            ValueError: If `spawn` is False and `instance_id` is None.
        """
        # Payload only matters if spawning a new instance
        spawn_payload: Dict[str, Any] = {}
        if spawn:
            # Ensure showInput is always included in the spawn payload
            spawn_payload["showInput"] = show_input # camelCase key
            if initial_text:
                 # Only add initial text if it's not empty
                 spawn_payload["text"] = initial_text

        # Initialize the base class, which handles connection, ID, spawn command etc.
        super().__init__(
            module_type="console",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None, # Only send payload if spawning
            on_message=on_message # Register the callback for 'notify' messages
        )
        connection.logger.info(f"Console '{self.target_id}' initialized (spawn={spawn}, show_input={show_input if spawn else 'N/A'}).")

    def print(self, *args: Any, sep: str = ' ', end: str = ''):
        """
        Prints text to this console module instance in Sidekick, appending it
        to the output area.

        This works very similar to Python's built-in `print()` function.
        It converts all arguments to strings, joins them with the `sep` string,
        and adds the `end` string. The final text is then displayed on a new
        line (or appended, depending on `end`) in the Sidekick console.

        Example:
            console.print("Hello", "world!")  # Sends "Hello world!"
            console.print(1, 2, 3, sep='-')   # Sends "1-2-3"

        Args:
            *args (Any): One or more objects to print. They will be converted to
                         strings using `str()`.
            sep (str): The separator string inserted between objects. Defaults to a space ' '.
            end (str): The string appended after the last object. Defaults to an empty
                       string '', meaning subsequent prints start right after.
                       Use `end='\\n'` to ensure a newline, although the UI usually handles this.
        """
        text_to_print = sep.join(map(str, args)) + end
        # Construct the payload for the 'update' command
        # Using the standard action/options structure for Sidekick updates
        payload = {
            "action": "append", # Instructs the UI to add text
            "options": {
                "text": text_to_print # The text content (ensure payload key is camelCase)
            }
        }
        # Send the update command (handles buffering via connection.send_message)
        self._send_update(payload)

    def log(self, message: Any):
        """
        A convenient shortcut to print a single message to the console.

        This is equivalent to calling `console.print(message)`.

        Args:
            message (Any): The message or object to print. It will be converted to a string.
        """
        self.print(message) # Simply calls the more general print method

    def clear(self):
        """
        Removes all previously displayed text from this console instance in Sidekick,
        leaving the output area empty.
        """
        connection.logger.info(f"Requesting clear for console '{self.target_id}'.")
        # Construct the payload for the 'clear' action
        payload = {
            "action": "clear"
            # 'options' are not needed for the clear action
        }
        # Send the update command (handles buffering via connection.send_message)
        self._send_update(payload)

    # remove() method is inherited from BaseModule.
    # Calling console_instance.remove() will send a 'remove' command to Sidekick
    # for this console instance and unregister the local message handler.