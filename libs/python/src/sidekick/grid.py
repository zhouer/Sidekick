"""Provides the Grid class for creating interactive 2D grids in Sidekick.

Use the `sidekick.Grid` class to create a grid of rectangular cells (like a
spreadsheet, checkerboard, or pixel display) within the Sidekick panel. You
can programmatically control the background color and display text within each
individual cell of the grid from your Python script.

The grid can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization.

This component is particularly useful for:

*   **Visualizing 2D Data:** Representing game maps, matrices, or cellular automata states.
*   **Simple Graphics:** Creating pixel art or basic pattern displays.
*   **Interactive Elements:** Building simple interactive boards or simulations
    where the user can click on cells to trigger actions or provide input to
    your Python script (using `on_click()`).

Coordinate System:
    Methods like `set_color`, `set_text`, `clear_cell`, and the `on_click` callback
    use `(x, y)` coordinates to identify specific cells within the grid:

    *   `x` represents the **column index**, starting from 0 for the leftmost column.
    *   `y` represents the **row index**, starting from 0 for the topmost row.

    So, `(0, 0)` is the top-left cell.

Basic Usage:
    >>> import sidekick
    >>> my_grid = sidekick.Grid(num_columns=4, num_rows=3) # In root container
    >>> my_grid.set_color(x=0, y=0, color='blue')

Interactive Usage with a Parent Container:
    >>> import sidekick
    >>> my_row = sidekick.Row()
    >>> grid_in_row = sidekick.Grid(5, 5, parent=my_row)
    >>>
    >>> def user_clicked_cell(x, y):
    ...     grid_in_row.set_text(x, y, "Clicked!")
    ...
    >>> grid_in_row.on_click(user_clicked_cell)
    >>> # sidekick.run_forever()
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Callable, Dict, Any, Union # Added Union

class Grid(BaseComponent):
    """Represents an interactive Grid component instance in the Sidekick UI.

    Instantiate this class to create a grid of cells. Can be nested.

    Attributes:
        target_id (str): The unique identifier for this grid instance.
        num_columns (int): The number of columns this grid has (read-only).
        num_rows (int): The number of rows this grid has (read-only).
    """
    def __init__(
        self,
        num_columns: int,
        num_rows: int,
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes the Grid object and creates the UI element.

        Args:
            num_columns (int): Number of columns (must be > 0).
            num_rows (int): Number of rows (must be > 0).
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, added to the root container.

        Raises:
            ValueError: If `num_columns` or `num_rows` are not positive integers.
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        if not isinstance(num_columns, int) or num_columns <= 0:
            raise ValueError("Grid num_columns must be a positive integer.")
        if not isinstance(num_rows, int) or num_rows <= 0:
             raise ValueError("Grid num_rows must be a positive integer.")

        spawn_payload: Dict[str, Any] = {
            "numColumns": num_columns,
            "numRows": num_rows
        }

        super().__init__(
            component_type="grid",
            payload=spawn_payload,
            parent=parent # Pass the parent argument to BaseComponent
        )

        self._num_columns = num_columns
        self._num_rows = num_rows
        self._click_callback: Optional[Callable[[int, int], None]] = None
        logger.info(f"Grid '{self.target_id}' initialized (size={self.num_columns}x{self.num_rows}).")

    @property
    def num_columns(self) -> int:
        """int: The number of columns in the grid (read-only)."""
        return self._num_columns

    @property
    def num_rows(self) -> int:
        """int: The number of rows in the grid (read-only)."""
        return self._num_rows

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this grid. (Internal)."""
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "click" and self._click_callback:
                try:
                    x = payload.get('x')
                    y = payload.get('y')
                    if isinstance(x, int) and isinstance(y, int):
                        self._click_callback(x, y)
                    else:
                         logger.warning(
                            f"Grid '{self.target_id}' received 'click' event "
                            f"with missing or invalid coordinates: {payload}"
                         )
                except Exception as e:
                    logger.exception(
                        f"Error occurred inside Grid '{self.target_id}' on_click callback: {e}"
                    )
            else:
                 logger.debug(
                    f"Grid '{self.target_id}' received unhandled event type '{event_type}' "
                    f"or no click callback registered."
                 )
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[int, int], None]]):
        """Registers a function to call when the user clicks on any cell in this grid.

        Args:
            callback (Optional[Callable[[int, int], None]]): Function to call.
                Must accept `x` (column index) and `y` (row index).
                Pass `None` to remove a callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for grid '{self.target_id}'.")
        self._click_callback = callback

    def set_color(self, x: int, y: int, color: Optional[str]):
        """Sets the background color of a specific cell.

        Args:
            x (int): Column index (0 to `num_columns - 1`).
            y (int): Row index (0 to `num_rows - 1`).
            color (Optional[str]): CSS color string (e.g., 'red', '#FF0000').
                `None` clears the color to default.

        Raises:
            IndexError: If `x` or `y` are out of bounds.
            SidekickConnectionError: If sending command fails.
        """
        if not (0 <= x < self.num_columns):
             raise IndexError(
                f"Grid '{self.target_id}': Column index x={x} is out of bounds "
                f"(must be 0 <= x < {self.num_columns})."
            )
        if not (0 <= y < self.num_rows):
              raise IndexError(
                f"Grid '{self.target_id}': Row index y={y} is out of bounds "
                f"(must be 0 <= y < {self.num_rows})."
            )

        options: Dict[str, Any] = {"x": x, "y": y, "color": color}
        update_payload = { "action": "setColor", "options": options }
        self._send_update(update_payload)

    def set_text(self, x: int, y: int, text: Optional[str]):
        """Sets the text content displayed inside a specific cell.

        Args:
            x (int): Column index.
            y (int): Row index.
            text (Optional[str]): Text to display. `None` or "" clears existing text.

        Raises:
            IndexError: If `x` or `y` are out of bounds.
            SidekickConnectionError: If sending command fails.
        """
        if not (0 <= x < self.num_columns):
             raise IndexError(
                f"Grid '{self.target_id}': Column index x={x} is out of bounds "
                f"(must be 0 <= x < {self.num_columns})."
            )
        if not (0 <= y < self.num_rows):
              raise IndexError(
                f"Grid '{self.target_id}': Row index y={y} is out of bounds "
                f"(must be 0 <= y < {self.num_rows})."
            )

        text_to_send = str(text) if text is not None else None
        options: Dict[str, Any] = {"x": x, "y": y, "text": text_to_send}
        update_payload = { "action": "setText", "options": options }
        self._send_update(update_payload)

    def clear_cell(self, x: int, y: int):
        """Clears both the background color and text content of a specific cell.

        Args:
            x (int): Column index.
            y (int): Row index.

        Raises:
            IndexError: If `x` or `y` are out of bounds.
            SidekickConnectionError: If sending command fails.
        """
        if not (0 <= x < self.num_columns):
             raise IndexError(
                f"Grid '{self.target_id}': Column index x={x} is out of bounds "
                f"(must be 0 <= x < {self.num_columns})."
            )
        if not (0 <= y < self.num_rows):
              raise IndexError(
                f"Grid '{self.target_id}': Row index y={y} is out of bounds "
                f"(must be 0 <= y < {self.num_rows})."
            )

        options: Dict[str, Any] = {"x": x, "y": y}
        update_payload = { "action": "clearCell", "options": options }
        self._send_update(update_payload)

    def clear(self):
        """Clears the *entire grid*, resetting all cells to their default state.

        Raises:
            SidekickConnectionError: If sending command fails.
        """
        logger.info(f"Requesting clear for entire grid '{self.target_id}'.")
        clear_payload = { "action": "clear" }
        self._send_update(clear_payload)

    def _reset_specific_callbacks(self):
        """Internal: Resets grid-specific callbacks."""
        super()._reset_specific_callbacks()
        self._click_callback = None