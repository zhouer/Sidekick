# Sidekick/libs/python/src/sidekick/grid.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Grid(BaseModule):
    """
    Represents an interactive Grid module instance in the Sidekick UI.

    This class allows you to create and manipulate a grid of cells displayed
    in Sidekick. You can set the background color and text content for each
    individual cell. You can also receive notifications (via a callback function)
    when a user clicks on a cell in the Sidekick interface.

    It supports two modes of initialization:
    1. Creating a new grid instance in Sidekick (`spawn=True`).
    2. Attaching to a pre-existing grid instance in Sidekick (`spawn=False`).

    **Coordinate System:**
    Methods like `set_cell`, `set_color`, and `set_text` use `(x, y)` coordinates
    where:
    - `x` is the **column index** (0-based, starting from the left).
    - `y` is the **row index** (0-based, starting from the top, Y-axis points down).
    Think `grid.set_*(column, row, ...)`.

    Attributes:
        target_id (str): The unique identifier for this grid instance.
        num_columns (int): The number of columns in the grid.
        num_rows (int): The number of rows in the grid.
    """
    def __init__(
        self,
        num_columns: int = 16,
        num_rows: int = 16,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        Initializes the Grid object, optionally creating a new grid in Sidekick.

        Args:
            num_columns (int): The number of columns for the grid (horizontal dimension).
                Must be a positive integer. Defaults to 16.
                Used for validation even if `spawn=False`.
            num_rows (int): The number of rows for the grid (vertical dimension).
                Must be a positive integer. Defaults to 16.
                Used for validation even if `spawn=False`.
            instance_id (Optional[str]): A unique identifier for this grid instance.
                - If `spawn=True`: Optional. If None, an ID will be generated automatically.
                  If provided, this ID will be used for the new instance.
                - If `spawn=False`: **Required**. Specifies the ID of the existing
                  grid instance in Sidekick to attach to. `num_columns` and `num_rows`
                  should still match the dimensions of the existing grid for accurate
                  client-side validation, although they are not sent in the payload.
            spawn (bool): If True (default), a command is sent to Sidekick to create a
                new grid module instance with the specified `num_columns` and `num_rows`.
                If False, no 'spawn' command is sent, and the object assumes
                a grid with the specified `instance_id` already exists in Sidekick.
            on_message (Optional[Callable]): A function to call when a message (e.g.,
                a click event) is received from the corresponding grid instance in
                Sidekick. The callback receives the full message dictionary.
                For click events, the payload looks like:
                `{'event': 'click', 'x': column_index, 'y': row_index}`.
                Ensure the provided function accepts one dictionary argument.

        Raises:
            ValueError: If `num_columns` or `num_rows` are not positive integers.
            ValueError: If `spawn` is False and `instance_id` is None.
        """
        # Validate dimensions first
        if not (isinstance(num_columns, int) and num_columns > 0):
            raise ValueError(f"Grid num_columns must be a positive integer, got {num_columns}")
        if not (isinstance(num_rows, int) and num_rows > 0):
             raise ValueError(f"Grid num_rows must be a positive integer, got {num_rows}")

        # Payload containing dimension information is only needed when spawning.
        spawn_payload: Dict[str, Any] = {}
        if spawn:
             # Use camelCase keys as required by the protocol
             spawn_payload["numColumns"] = num_columns
             spawn_payload["numRows"] = num_rows

        # Initialize the base module, which handles connection activation, ID generation/validation,
        # message handler registration, and sending the spawn command if requested.
        super().__init__(
            module_type="grid",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None, # Only send payload if spawning
            on_message=on_message
        )

        # Store dimensions locally for client-side validation and potentially other uses.
        self.num_columns = num_columns
        self.num_rows = num_rows
        connection.logger.info(f"Grid '{self.target_id}' initialized (spawn={spawn}, size={num_columns}x{num_rows}).")

    def set_cell(self, x: int, y: int, color: Optional[str] = None, text: Optional[str] = None):
        """
        Sets the state (color and/or text) of a specific cell in the Sidekick grid.

        You must provide at least `color` or `text` to change the cell.
        If both `color` and `text` are `None`, this method does nothing.

        Example:
            grid.set_cell(2, 3, color='blue') # Set cell at col 2, row 3 to blue
            grid.set_cell(0, 0, text='X', color='#FF0000') # Set cell 0,0 to red with text 'X'
            grid.set_cell(5, 5, color=None) # Clear background color of cell 5,5
            grid.set_cell(1, 1, text=None) # Clear text content of cell 1,1

        Args:
            x (int): The **column index** (0-based, horizontal position from left).
            y (int): The **row index** (0-based, vertical position from top, Y-down).
            color (Optional[str]): The background color to set for the cell.
                Can be a color name (e.g., 'red', 'lightblue'), a hex code
                (e.g., '#FF0000', '#87CEEB'), or other valid CSS color strings.
                Set to `None` to clear the background color, reverting it to the default
                (usually white).
            text (Optional[str]): The text content to display within the cell.
                Can be any object that converts to a string via `str()`.
                Set to `None` or an empty string `""` to clear the text content.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                grid boundaries (0 <= x < num_columns, 0 <= y < num_rows).
        """
        # Validate coordinates against the stored grid dimensions.
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (0 <= y < {self.num_rows}).")

        # Only send the update if there's actually something to change (color or text provided).
        if color is None and text is None:
            connection.logger.debug(f"Grid '{self.target_id}': set_cell called for (x={x}, y={y}) with no changes specified (both color and text are None). Ignoring.")
            return

        # Construct the options part of the payload, including only non-None values.
        options: Dict[str, Any] = {"x": x, "y": y} # Coordinates are always required
        # Add color if it's provided (even if it's an empty string, let UI handle it)
        if color is not None:
            options["color"] = color # Expects string or null on the frontend
        # Add text if it's provided
        if text is not None:
            options["text"] = str(text) # Ensure text is always a string if provided

        # Construct the full update payload using the standard action/options structure
        update_payload = {
            "action": "setCell",
            "options": options
        }
        # Send the update command (will be buffered if Sidekick not ready)
        self._send_update(update_payload)

    def set_color(self, x: int, y: int, color: Optional[str]):
        """
        Sets **only** the background color of a specific cell in the Sidekick grid,
        leaving any existing text unchanged.

        This is a convenience method equivalent to calling
        `set_cell(x, y, color=color, text=current_text)`.

        Args:
            x (int): The **column index** (0-based, horizontal position from left).
            y (int): The **row index** (0-based, vertical position from top, Y-down).
            color (Optional[str]): The color string (e.g., 'red', '#FF0000').
                Set to `None` to clear the background color.

        Raises:
            IndexError: If the coordinates are out of bounds.
        """
        # We only pass the color to set_cell. Text is implicitly None, meaning
        # the frontend should only update the color property.
        self.set_cell(x=x, y=y, color=color, text=None)

    def set_text(self, x: int, y: int, text: Optional[str]):
        """
        Sets **only** the text content displayed within a specific cell in the
        Sidekick grid, leaving any existing background color unchanged.

        This is a convenience method equivalent to calling
        `set_cell(x, y, color=current_color, text=text)`.

        Args:
            x (int): The **column index** (0-based, horizontal position from left).
            y (int): The **row index** (0-based, vertical position from top, Y-down).
            text (Optional[str]): The text to display. Converts via `str()`.
                Set to `None` or `""` to clear the text.

        Raises:
            IndexError: If the coordinates are out of bounds.
        """
        # We only pass the text to set_cell. Color is implicitly None, meaning
        # the frontend should only update the text property.
        self.set_cell(x=x, y=y, color=None, text=text)

    def clear(self):
        """
        Clears the entire grid in Sidekick, reverting all cells to their default
        state (typically white background, no text).
        """
        connection.logger.info(f"Requesting clear for grid '{self.target_id}'.")
        # Construct the payload for the 'clear' action
        clear_payload = {
            "action": "clear"
            # Options are not needed for the 'clear' action.
        }
        # Send the update command (will be buffered if Sidekick not ready)
        self._send_update(clear_payload)

    # The remove() method is inherited from BaseModule.
    # Calling grid_instance.remove() will send a 'remove' command to Sidekick
    # for this grid instance and unregister the local message handler.