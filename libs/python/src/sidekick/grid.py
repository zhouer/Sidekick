# Sidekick/libs/python/src/sidekick/grid.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Grid(BaseModule):
    """
    Represents an interactive Grid module instance in Sidekick.

    Allows setting cell colors and text, clearing the grid, and receiving
    click notifications.

    **Coordinate System:**
    This module uses a standard UI coordinate system where:
    - `x` represents the **column index** (horizontal position), starting from 0 on the left.
    - `y` represents the **row index** (vertical position), starting from 0 at the top (Y-axis points downwards).

    Therefore, the common usage pattern is `grid.set_*(column, row, ...)`.
    """
    def __init__(self, width: int, height: int, instance_id: Optional[str] = None,
                 on_message: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Creates a new Grid visualization in the Sidekick UI.

        Args:
            width: The number of columns (horizontal size). Must be a positive integer.
            height: The number of rows (vertical size). Must be a positive integer.
            instance_id: Optional unique identifier. Auto-generated if None.
            on_message: Optional callback for messages from this grid (e.g., clicks).
                        Receives the full message dictionary, where the payload for a click
                        will contain `{'event': 'click', 'x': column, 'y': row}`.
        """
        if not (isinstance(width, int) and width > 0 and isinstance(height, int) and height > 0):
             raise ValueError("Grid width and height must be positive integers.")
        # Payload for spawn: size is [width, height] which corresponds to [columns, rows]
        payload = {"size": [width, height]}
        super().__init__("grid", instance_id, payload, on_message)
        self.width = width   # Number of columns
        self.height = height # Number of rows
        connection.logger.info(f"Grid '{self.target_id}' created ({width} cols x {height} rows).")

    def _set_cell(self, x: int, y: int, color: Optional[str] = None, text: Optional[str] = None):
        """Internal helper to send a setCell update."""
        # Validate coordinates against width (columns) and height (rows)
        if not (0 <= x < self.width and 0 <= y < self.height):
             connection.logger.warning(f"_set_cell: Coordinates (x={x}, y={y}) out of bounds for grid '{self.target_id}' ({self.width} cols x {self.height} rows).")
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
                "options": options # options contains 'x' (column) and 'y' (row)
            }
            self._send_update(payload)
        else:
             connection.logger.debug(f"Grid '{self.target_id}': _set_cell called for (x={x}, y={y}) with no changes specified.")


    def set_color(self, x: int, y: int, color: Optional[str]):
        """
        Sets the background color of a specific cell.

        Args:
            x: The **column index** (0-based, horizontal position from left).
            y: The **row index** (0-based, vertical position from top, Y-down).
            color: The color string (e.g., 'red', '#FF0000').
                   Set to `None` to clear the color (revert to default).
        """
        self._set_cell(x=x, y=y, color=color)

    def set_text(self, x: int, y: int, text: Optional[str]):
        """
        Sets the text content displayed within a specific cell.

        Args:
            x: The **column index** (0-based, horizontal position from left).
            y: The **row index** (0-based, vertical position from top, Y-down).
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