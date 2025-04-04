# Sidekick/libs/python/src/sidekick/console.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Console(BaseModule):
    """
    Represents a Console module instance in the Sidekick UI.

    Allows printing text output, clearing the console area, and optionally handling
    user input submissions from the frontend via a callback. This class can either
    create a new console instance in Sidekick or attach to a pre-existing one.

    Attributes:
        target_id (str): The unique identifier for this console instance.
    """
    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        initial_text: str = "",
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Initializes or attaches to a Console module in the Sidekick UI.

        Args:
            instance_id (Optional[str]): A specific ID for this console instance.
                                         - If `spawn=True`, optional (auto-generated if None).
                                         - If `spawn=False`, **must** be provided.
            spawn (bool): If True (default), creates a new console instance in Sidekick.
                          Sends a 'spawn' command, potentially with `initial_text`.
                          If False, attaches to an existing console with `instance_id`.
                          No 'spawn' command sent.
            initial_text (str): Text line to display immediately upon creation.
                                Only used if `spawn=True`. Defaults to "".
            on_message (Optional[Callable]): Callback for messages from this console
                                             (e.g., user submitting input). Receives the
                                             full message dictionary (payload format:
                                             `{'event': 'submit', 'value': submitted_text}`).
        Raises:
            ValueError: If `spawn` is False and `instance_id` is None.
        """
        # Payload only matters if spawning a new instance
        spawn_payload = {"text": initial_text} if spawn and initial_text else {}

        super().__init__(
            module_type="console",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload,
            on_message=on_message
        )
        connection.logger.info(f"Console '{self.target_id}' initialized (spawn={spawn}).")

    def print(self, *args: Any, sep: str = ' ', end: str = ''):
        """
        Prints text to this console module instance in Sidekick, appending it.

        Converts all arguments to strings using `str()`, joins them with `sep`,
        and appends `end`. Sends an 'update' command with action 'append'.

        Args:
            *args (Any): Objects to print.
            sep (str): Separator string inserted between objects. Defaults to a space.
            end (str): String appended after the last object. Defaults to empty string.
        """
        text_to_print = sep.join(map(str, args)) + end
        # Send using the standard action/options structure
        payload = {
            "action": "append",
            "options": {
                "text": text_to_print # Ensure payload key is camelCase
            }
        }
        # Send the update command (handles buffering via connection.send_message)
        self._send_update(payload)

    def log(self, message: Any):
        """
        Convenience method to print a single message to the console.

        Equivalent to `console.print(message)`.

        Args:
            message (Any): The message to print (will be converted to string).
        """
        self.print(message) # Simply calls the print method

    def clear(self):
        """
        Clears all previously displayed text from this console instance in Sidekick.
        Sends an 'update' command with action 'clear'.
        """
        connection.logger.info(f"Requesting clear for console '{self.target_id}'.")
        payload = {"action": "clear"}
        # Send the update command (handles buffering via connection.send_message)
        self._send_update(payload)

    # remove() method is inherited from BaseModule, sends 'remove' command.