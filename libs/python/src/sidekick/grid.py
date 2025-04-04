# Sidekick/libs/python/src/sidekick/grid.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Grid(BaseModule):
    """
    Represents an interactive Grid module instance in the Sidekick UI.

    This class allows you to create and manipulate a grid of cells, setting their
    background colors and text content. You can also receive notifications when
    a user clicks on a cell in the Sidekick interface.

    It supports two modes of initialization:
    1. Creating a new grid instance in Sidekick (`spawn=True`).
    2. Attaching to a pre-existing grid instance in Sidekick (`spawn=False`).

    **Coordinate System:**
    Methods like `set_color` and `set_text` use `(x, y)` coordinates where:
    - `x` is the **column index** (0-based, horizontal, from left).
    - `y` is the **row index** (0-based, vertical, from top, Y-axis down).
    Think `grid.set_*(column, row, ...)`.
    """
    def __init__(
        self,
        width: int,
        height: int,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Initializes the Grid object, optionally creating a new grid in Sidekick.

        Args:
            width: The number of columns for the grid. Must be a positive integer.
                   This is used for validation even if `spawn=False`.
            height: The number of rows for the grid. Must be a positive integer.
                    This is used for validation even if `spawn=False`.
            instance_id: A unique identifier for this grid instance.
                         - If `spawn=True`: Optional. If None, an ID will be generated automatically.
                           If provided, this ID will be used for the new instance.
                         - If `spawn=False`: **Required**. Specifies the ID of the existing
                           grid instance in Sidekick to attach to.
            spawn: If True (default), a command is sent to Sidekick to create a
                   new grid module instance with the specified `width` and `height`.
                   If False, no 'spawn' command is sent, and the object assumes
                   a grid with the specified `instance_id` already exists in Sidekick.
            on_message: An optional callback function that will be invoked when a
                        message (e.g., a click event) is received from the corresponding
                        grid instance in Sidekick. The callback receives the full message
                        dictionary (e.g., `{'event': 'click', 'x': 3, 'y': 5}`).
                        Payload keys are camelCase.
        """
        if not (isinstance(width, int) and width > 0 and isinstance(height, int) and height > 0):
             raise ValueError("Grid width and height must be positive integers.")

        # Payload containing size information is only needed when spawning a new instance.
        spawn_payload = {"size": [width, height]} if spawn else None

        # Initialize the base module, which handles connection activation, ID generation/validation,
        # message handler registration, and sending the spawn command if requested.
        super().__init__(
            module_type="grid",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload,
            on_message=on_message
        )

        # Store dimensions locally for client-side validation in methods like set_color/set_text.
        self.width = width
        self.height = height
        connection.logger.info(f"Grid '{self.target_id}' initialized (spawn={spawn}, size={width}x{height}).")

    def _set_cell(self, x: int, y: int, color: Optional[str] = None, text: Optional[str] = None):
        """Internal helper to construct and send a 'setCell' update command."""
        # Validate coordinates against the stored grid dimensions.
        if not (0 <= x < self.width and 0 <= y < self.height):
             connection.logger.warning(
                 f"Grid '{self.target_id}': Coordinates (x={x}, y={y}) out of bounds "
                 f"({self.width}x{self.height}). Ignoring setCell command."
             )
             return

        # Construct the options part of the payload, including only non-None values.
        options: Dict[str, Any] = {"x": x, "y": y}
        if color is not None:
            options["color"] = color
        if text is not None:
            options["text"] = str(text) # Ensure text is always a string if provided

        # Only send the update if there's actually something to change (color or text).
        if "color" in options or "text" in options:
            update_payload = {
                "action": "setCell",
                "options": options
            }
            self._send_update(update_payload)
        else:
            # Log if called without specifying any changes.
             connection.logger.debug(f"Grid '{self.target_id}': _set_cell called for (x={x}, y={y}) with no changes specified.")

    def set_color(self, x: int, y: int, color: Optional[str]):
        """
        Sets the background color of a specific cell in the Sidekick grid.

        Args:
            x: The **column index** (0-based, horizontal position from left).
            y: The **row index** (0-based, vertical position from top, Y-down).
            color: The color string (e.g., 'red', '#FF0000', 'rgba(0, 255, 0, 0.5)').
                   Set to `None` to clear the background color, reverting it to the default.
        """
        self._set_cell(x=x, y=y, color=color)

    def set_text(self, x: int, y: int, text: Optional[str]):
        """
        Sets the text content displayed within a specific cell in the Sidekick grid.

        Args:
            x: The **column index** (0-based, horizontal position from left).
            y: The **row index** (0-based, vertical position from top, Y-down).
            text: The text to display. Can be any object that converts to a string via `str()`.
                  Set to `None` or an empty string `""` to clear the text content.
        """
        self._set_cell(x=x, y=y, text=text)

    def clear(self):
        """
        Clears the entire grid in Sidekick, reverting all cells to their default
        state (typically white background, no text).
        """
        connection.logger.info(f"Requesting clear for grid '{self.target_id}'.")
        clear_payload = {"action": "clear"}
        # Options are not needed for the 'clear' action.
        self._send_update(clear_payload)

    # The remove() method is inherited from BaseModule.
    # Calling grid_instance.remove() will send a 'remove' command to Sidekick
    # for this grid instance and unregister the local message handler.