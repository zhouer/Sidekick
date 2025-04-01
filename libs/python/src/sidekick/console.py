# Sidekick/libs/python/src/sidekick/console.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Console(BaseModule):
    """
    Represents a Console module instance in Sidekick.

    Allows printing text output and clearing the console. Optionally handles
    user input submissions via a callback.
    """
    def __init__(self, instance_id: Optional[str] = None, initial_text: str = "",
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Creates a new Console output/input visualization.

        Args:
            instance_id: Optional unique identifier. Auto-generated if None.
            initial_text: Optional text line to display immediately upon creation.
            on_message: Optional callback for messages from this console
                        (e.g., user submitting input). Receives the full message dictionary.
        """
        payload = {"text": initial_text} if initial_text else {}
        super().__init__("console", instance_id, payload, on_message)
        connection.logger.info(f"Console '{self.target_id}' created.")

    def print(self, *args, sep=' ', end=''):
        """
        Prints text to the console module, appending it to the output.

        Args:
            *args: Objects to print, converted to strings using str().
            sep: Separator string inserted between objects. Defaults to a space.
            end: String appended after the last object. Defaults to empty string.
        """
        text_to_print = sep.join(map(str, args)) + end
        # Send using the new action/options structure
        payload = {
            "action": "append",
            "options": {
                "text": text_to_print
            }
        }
        self._send_update(payload)

    def log(self, message: Any):
        """
        Prints a single message to the console (converting it to string).

        Args:
            message: The message to print.
        """
        self.print(message)

    def clear(self):
        """Clears all previously displayed text from the console output area."""
        connection.logger.info(f"Clearing console '{self.target_id}'.")
        # Send using the new action structure
        payload = {"action": "clear"}
        self._send_update(payload)