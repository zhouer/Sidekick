# Sidekick/libs/python/src/sidekick/modules.py
from . import connection
from .utils import generate_unique_id
from typing import Optional, Tuple, List, Dict, Any, Callable

# Base class (optional, but good for common functionality)
class BaseModule:
    def __init__(self, module_type: str, instance_id: Optional[str] = None, payload: Optional[Dict[str, Any]] = None,
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None):
        connection.activate_connection() # Ensure connection is allowed and potentially initiated
        self.module_type = module_type
        self.target_id = instance_id or generate_unique_id(module_type)
        self._on_message_callback = on_message # Store callback reference

        # Register handler *before* sending spawn, in case Sidekick replies immediately
        if self._on_message_callback:
            connection.register_message_handler(self.target_id, self._on_message_callback)

        self._send_command("spawn", payload or {})

    def _send_command(self, method: str, payload: Optional[Dict[str, Any]] = None):
        message: Dict[str, Any] = {
            "id": 0, # id field from spec, might be used later
            "module": self.module_type,
            "method": method,
            "target": self.target_id,
        }
        if payload is not None:
            message["payload"] = payload
        connection.send_message(message)

    def remove(self):
        """Removes the module instance from the Sidekick UI and unregisters message handler."""
        connection.logger.info(f"Removing module '{self.target_id}' and unregistering handler.")
        # Unregister handler first
        connection.unregister_message_handler(self.target_id)
        # Then send remove command
        self._send_command("remove")


    def __del__(self):
        # Attempt to remove the instance and handler when the Python object is garbage collected
        # Note: This is not guaranteed to run reliably. Explicit .remove() is safer.
        try:
            # Check if connection/handler might still be valid (basic check)
            if hasattr(connection, 'unregister_message_handler'):
                 connection.unregister_message_handler(self.target_id)
            # Don't send remove command here, as WS connection might be gone
            # self._send_command("remove") # Avoid sending in __del__
        except Exception:
            # Suppress errors during garbage collection
            pass


class Grid(BaseModule):
    """Represents a Grid module instance in Sidekick."""
    def __init__(self, width: int, height: int, instance_id: Optional[str] = None,
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Creates a new Grid visualization.

        Args:
            width: The number of columns in the grid.
            height: The number of rows in the grid.
            instance_id: Optional specific ID for this grid instance.
            on_message: Optional callback function to handle messages from this grid (e.g., clicks).
                        The callback will receive the full message dictionary.
        """
        if not (isinstance(width, int) and width > 0 and isinstance(height, int) and height > 0):
             raise ValueError("Grid width and height must be positive integers.")
        payload = {"size": [width, height]}
        super().__init__("grid", instance_id, payload, on_message) # Pass callback to BaseModule
        self.width = width
        self.height = height
        connection.logger.info(f"Grid '{self.target_id}' created ({width}x{height}).")


    def set_color(self, x: int, y: int, color: str):
        """
        Sets the background color of a specific cell.

        Args:
            x: The column index (0-based).
            y: The row index (0-based).
            color: The color string (e.g., 'red', '#FF0000', 'rgb(255,0,0)').
        """
        if not (0 <= x < self.width and 0 <= y < self.height):
             connection.logger.warning(f"set_color: Coordinates ({x},{y}) out of bounds for grid '{self.target_id}' ({self.width}x{self.height}).")
             return
        payload = {"x": x, "y": y, "color": color}
        self._send_command("update", payload)

    def set_text(self, x: int, y: int, text: str):
        """
        Sets the text content of a specific cell.

        Args:
            x: The column index (0-based).
            y: The row index (0-based).
            text: The text to display in the cell.
        """
        if not (0 <= x < self.width and 0 <= y < self.height):
             connection.logger.warning(f"set_text: Coordinates ({x},{y}) out of bounds for grid '{self.target_id}' ({self.width}x{self.height}).")
             return
        payload = {"x": x, "y": y, "text": str(text)} # Ensure text is string
        self._send_command("update", payload)

    def clear_cell(self, x: int, y: int):
        """
        Clears the color and text of a specific cell, reverting to default.

        Args:
            x: The column index (0-based).
            y: The row index (0-based).
        """
        if not (0 <= x < self.width and 0 <= y < self.height):
             connection.logger.warning(f"clear_cell: Coordinates ({x},{y}) out of bounds for grid '{self.target_id}' ({self.width}x{self.height}).")
             return
        # Send None or empty string based on frontend expectation for clearing
        payload = {"x": x, "y": y, "color": None, "text": ""} # Assume None clears color, "" clears text
        self._send_command("update", payload)

    def fill(self, color: str):
         """Fills the entire grid with a specific color."""
         # Optimize later: Add a batch fill command if supported by frontend
         connection.logger.info(f"Filling grid '{self.target_id}' with color '{color}'.")
         payload = {"fill_color": color} # Example payload for a potential future fill method
         # For now, fallback to individual cell updates
         # self._send_command("update", payload) # If batch fill is implemented
         for y in range(self.height):
             for x in range(self.width):
                 self.set_color(x, y, color) # Current implementation


class Console(BaseModule):
    """Represents a Console module instance in Sidekick."""
    def __init__(self, instance_id: Optional[str] = None, initial_text: str = "",
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None): # Add on_message if console can send messages back
        """
        Creates a new Console output visualization.

        Args:
            instance_id: Optional specific ID for this console instance.
            initial_text: Optional text to display immediately upon creation.
            on_message: Optional callback (currently unused by console, but kept for consistency).
        """
        payload = {"text": initial_text} if initial_text else {}
        super().__init__("console", instance_id, payload, on_message) # Pass callback
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