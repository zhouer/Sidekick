# Sidekick/libs/python/src/sidekick/grid.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Grid(BaseModule):
    """
    Represents an interactive Grid module instance in Sidekick.

    Allows setting cell colors and text, clearing the grid, and receiving
    click notifications.
    """
    def __init__(self, width: int, height: int, instance_id: Optional[str] = None,
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Creates a new Grid visualization in the Sidekick UI.

        Args:
            width: The number of columns (must be positive).
            height: The number of rows (must be positive).
            instance_id: Optional unique identifier. Auto-generated if None.
            on_message: Optional callback for messages from this grid (e.g., clicks).
                        Receives the full message dictionary.
        """
        if not (isinstance(width, int) and width > 0 and isinstance(height, int) and height > 0):
             raise ValueError("Grid width and height must be positive integers.")
        payload = {"size": [width, height]}
        super().__init__("grid", instance_id, payload, on_message)
        self.width = width
        self.height = height
        connection.logger.info(f"Grid '{self.target_id}' created ({width}x{height}).")

    def _set_cell(self, x: int, y: int, color: Optional[str] = None, text: Optional[str] = None):
        """Internal helper to send a setCell update."""
        if not (0 <= x < self.width and 0 <= y < self.height):
             connection.logger.warning(f"_set_cell: Coordinates ({x},{y}) out of bounds for grid '{self.target_id}' ({self.width}x{self.height}).")
             return

        options: Dict[str, Any] = {"x": x, "y": y}
        # Include color/text in options only if explicitly provided
        if color is not None:
            options["color"] = color
        if text is not None:
            options["text"] = str(text) # Ensure text is string

        # Only send update if there's something to change
        if "color" in options or "text" in options:
            payload = {
                "action": "setCell",
                "options": options
            }
            self._send_update(payload)
        else:
             connection.logger.debug(f"Grid '{self.target_id}': _set_cell called for ({x},{y}) with no changes specified.")


    def set_color(self, x: int, y: int, color: Optional[str]):
        """
        Sets the background color of a specific cell.

        Args:
            x: The column index (0-based).
            y: The row index (0-based).
            color: The color string (e.g., 'red', '#FF0000').
                   Set to `None` to clear the color (revert to default).
        """
        self._set_cell(x=x, y=y, color=color)

    def set_text(self, x: int, y: int, text: Optional[str]):
        """
        Sets the text content displayed within a specific cell.

        Args:
            x: The column index (0-based).
            y: The row index (0-based).
            text: The text to display. Set to `None` or empty string "" to clear text.
        """
        self._set_cell(x=x, y=y, text=text)

    def clear(self):
        """
        Clears the entire grid, reverting all cells to their default state
        (typically white background, no text).
        """
        connection.logger.info(f"Clearing grid '{self.target_id}'.")
        payload = {"action": "clear"}
        self._send_update(payload)
