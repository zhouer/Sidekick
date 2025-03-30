# Sidekick/libs/python/src/sidekick/grid.py
from . import connection
from .base_module import BaseModule # Assuming BaseModule is extracted or defined
from typing import Optional, Callable, Dict, Any

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
         # For now, fallback to individual cell updates
         for y in range(self.height):
             for x in range(self.width):
                 self.set_color(x, y, color) # Current implementation
