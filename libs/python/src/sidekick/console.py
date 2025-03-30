# Sidekick/libs/python/src/sidekick/console.py
from . import connection
from .base_module import BaseModule # Assuming BaseModule is extracted or defined
from typing import Optional, Callable, Dict, Any

class Console(BaseModule):
    """Represents a Console module instance in Sidekick, supporting output and input."""
    def __init__(self, instance_id: Optional[str] = None, initial_text: str = "",
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Creates a new Console output/input visualization.

        Args:
            instance_id: Optional specific ID for this console instance.
            initial_text: Optional text to display immediately upon creation.
            on_message: Optional callback function to handle messages from the console
                        (e.g., user input submissions). Receives the full message dictionary.
        """
        payload = {"text": initial_text} if initial_text else {}
        # Pass on_message callback to the base module constructor
        super().__init__("console", instance_id, payload, on_message)
        connection.logger.info(f"Console '{self.target_id}' created.")

    def print(self, *args, sep=' ', end=''):
        """
        Prints text to the console module, similar to Python's print function.
        Note: Currently sends each print call as a separate message.

        Args:
            *args: Objects to print. They will be converted to strings.
            sep: Separator between objects.
            end: String appended after the last object (defaults to empty, unlike standard print's newline).
        """
        text = sep.join(map(str, args)) + end
        # Frontend console expects 'text' in payload for appending
        payload = {"text": text}
        self._send_command("update", payload)

    def log(self, message: str):
        """Prints a message, automatically handling string conversion."""
        self.print(message)

    def clear(self):
        """Clears the console output."""
        # Define a payload convention for clearing the console via an update message
        connection.logger.info(f"Clearing console '{self.target_id}'.")
        payload = {"clear": True} # Frontend needs to interpret this
        self._send_command("update", payload)