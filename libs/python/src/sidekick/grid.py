"""
Sidekick Grid Module Interface.

This module provides the `Grid` class, allowing you to create and interact
with a grid of cells displayed in the Sidekick panel.

It's useful for:
  - Visualizing 2D data structures (like mazes or game boards).
  - Creating simple pixel-based animations.
  - Building interactive simulations where users can click on cells.
"""

from . import logger
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Grid(BaseModule):
    """Represents an interactive Grid module instance in the Sidekick UI.

    Use this class to create and manipulate a grid of cells in Sidekick.
    You can control the background color and display text within each cell.
    It's useful for visualizing 2D arrays, game boards, or simple animations.
    You can also detect when the user clicks on a cell using `on_click`.

    Coordinate System:
        Methods like `set_color`, `set_text`, `clear_cell`, and the `on_click`
        callback use `(x, y)` coordinates where:
        - `x` is the **column index** (0-based, starting from the left).
        - `y` is the **row index** (0-based, starting from the top).

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
        spawn: bool = True
    ):
        """Initializes the Grid object, optionally creating a new grid in Sidekick.

        Sets up the grid dimensions and prepares it for cell manipulation.

        Args:
            num_columns (int): The number of columns for the grid. Must be a
                positive integer. Defaults to 16.
            num_rows (int): The number of rows for the grid. Must be a
                positive integer. Defaults to 16.
            instance_id (Optional[str]): A specific ID for this grid instance.
                - If `spawn=True`: Optional. Auto-generated if None.
                - If `spawn=False`: **Required**. Identifies the existing grid.
            spawn (bool): If True (default), creates a new grid UI element.
                If False, attaches to an existing grid element. `num_columns` and
                `num_rows` are used for validation even if `spawn=False`, but the
                spawn command itself requires them only when `spawn=True`.

        Raises:
            ValueError: If `num_columns` or `num_rows` are not positive integers,
                        or if `spawn` is False and `instance_id` is None.

        Examples:
            >>> # Create a default 16x16 grid
            >>> grid1 = sidekick.Grid()
            >>>
            >>> # Create a 10x5 grid
            >>> grid2 = sidekick.Grid(num_columns=10, num_rows=5)
            >>>
            >>> # Attach to an existing grid named "game-board"
            >>> existing_grid = sidekick.Grid(instance_id="game-board", spawn=False,
            ...                               num_columns=20, num_rows=20) # Still need dimensions

        """
        # Validate dimensions first
        if not (isinstance(num_columns, int) and num_columns > 0):
            raise ValueError(f"Grid num_columns must be a positive integer, got {num_columns}")
        if not (isinstance(num_rows, int) and num_rows > 0):
             raise ValueError(f"Grid num_rows must be a positive integer, got {num_rows}")

        spawn_payload: Dict[str, Any] = {}
        if spawn:
             spawn_payload["numColumns"] = num_columns
             spawn_payload["numRows"] = num_rows

        # Initialize base module (handles connection, ID, internal handler registration)
        super().__init__(
            module_type="grid",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None
        )

        self.num_columns = num_columns
        self.num_rows = num_rows
        self._click_callback: Optional[Callable[[int, int], None]] = None
        logger.info(f"Grid '{self.target_id}' initialized (spawn={spawn}, size={num_columns}x{num_rows}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages for this grid instance, dispatching to callbacks."""
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "click" and self._click_callback:
                try:
                    x = payload.get('x')
                    y = payload.get('y')
                    if x is not None and y is not None:
                        self._click_callback(x, y)
                    else:
                         logger.warning(f"Grid '{self.target_id}' received click event with missing coordinates: {payload}")
                except Exception as e:
                    logger.exception(f"Error in Grid '{self.target_id}' on_click callback: {e}")
            else:
                 logger.debug(f"Grid '{self.target_id}' received unhandled event type '{event_type}'.")

        # Call base handler for error messages
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[int, int], None]]):
        """Registers a function to handle clicks on grid cells.

        When the user clicks on any cell within this grid in the Sidekick UI,
        the function you register here will be called.

        Args:
            callback (Optional[Callable[[int, int], None]]): A function that takes
                two arguments:
                1. `x` (int): The column index (0-based) of the clicked cell.
                2. `y` (int): The row index (0-based) of the clicked cell.
                Pass `None` to remove the current callback.

        Raises:
            TypeError: If the provided callback is not callable or None.

        Examples:
            >>> def cell_clicked(x, y):
            ...     print(f"Cell ({x}, {y}) was clicked!")
            ...     # Example: Set clicked cell color to blue
            ...     grid.set_color(x, y, "blue")
            >>>
            >>> grid = sidekick.Grid(5, 5)
            >>> grid.on_click(cell_clicked)
            >>> # sidekick.run_forever() # Needed to keep script alive for clicks

        Returns:
            None
        """
        if callback is not None and not callable(callback):
            raise TypeError("Click callback must be callable or None")
        logger.info(f"Setting on_click callback for grid '{self.target_id}'.")
        self._click_callback = callback

    # on_error is inherited from BaseModule

    def set_color(self, x: int, y: int, color: Optional[str]):
        """Sets the background color of a specific cell.

        Setting the color does not affect the cell's text content.

        Args:
            x (int): Column index (0-based).
            y (int): Row index (0-based).
            color (Optional[str]): The background color to set for the cell.
                Use CSS color strings like 'red', '#00ff00', 'rgba(0,0,255,0.5)'.
                Pass `None` to clear the background color of the cell, restoring
                its default background.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                        grid's boundaries (`0 <= x < num_columns`, `0 <= y < num_rows`).

        Examples:
            >>> # Set cell (0, 0) to red background
            >>> grid.set_color(0, 0, "red")
            >>> # Clear background color of cell (0, 0)
            >>> grid.set_color(0, 0, None)

        Returns:
            None
        """
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (0 <= y < {self.num_rows}).")

        options: Dict[str, Any] = {"x": x, "y": y, "color": color} # None will be sent as null
        update_payload = { "action": "setColor", "options": options }
        self._send_update(update_payload)


    def set_text(self, x: int, y: int, text: Optional[str]):
        """Sets the text content of a specific cell.

        Setting the text does not affect the cell's background color.

        Args:
            x (int): Column index (0-based).
            y (int): Row index (0-based).
            text (Optional[str]): The text to display inside the cell.
                Pass `None` or an empty string `""` to clear the text content
                of the cell.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                        grid's boundaries (`0 <= x < num_columns`, `0 <= y < num_rows`).

        Examples:
            >>> # Set text "Start" in cell (1, 2)
            >>> grid.set_text(1, 2, "Start")
            >>> # Clear text in cell (1, 2)
            >>> grid.set_text(1, 2, None)
            >>> # Also clears text in cell (1, 2)
            >>> grid.set_text(1, 2, "")

        Returns:
            None
        """
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (0 <= y < {self.num_rows}).")

        # Send None as null, "" as empty string (both clear text per protocol)
        options: Dict[str, Any] = {"x": x, "y": y, "text": text}
        update_payload = { "action": "setText", "options": options }
        self._send_update(update_payload)

    def clear_cell(self, x: int, y: int):
        """Clears both the background color and text content of a specific cell.

        Resets the cell to its default visual state.

        Args:
            x (int): Column index (0-based).
            y (int): Row index (0-based).

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                        grid's boundaries (`0 <= x < num_columns`, `0 <= y < num_rows`).

        Examples:
            >>> grid.set_color(3, 3, "purple")
            >>> grid.set_text(3, 3, "Value")
            >>> # Clear everything in cell (3, 3)
            >>> grid.clear_cell(3, 3)

        Returns:
            None
        """
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (0 <= y < {self.num_rows}).")

        options: Dict[str, Any] = {"x": x, "y": y}
        update_payload = { "action": "clearCell", "options": options }
        self._send_update(update_payload)

    def clear(self):
        """Clears the **entire grid**, resetting all cells to their default state.

        Removes all colors and text from all cells in the grid. This corresponds
        to the `clear` action in the protocol.

        Examples:
            >>> grid.set_color(0, 0, "red")
            >>> grid.set_text(1, 1, "Hi")
            >>> # Clear the whole grid
            >>> grid.clear()

        Returns:
            None
        """
        logger.info(f"Requesting clear for entire grid '{self.target_id}'.")
        clear_payload = { "action": "clear" } # No options needed for whole grid clear
        self._send_update(clear_payload)

    def _reset_specific_callbacks(self):
        """Resets grid-specific callbacks on removal."""
        self._click_callback = None

    # remove() is inherited from BaseModule