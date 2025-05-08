"""Provides the Grid class for creating interactive 2D grids in Sidekick.

Use the `sidekick.Grid` class to create a grid of rectangular cells (like a
spreadsheet, checkerboard, or pixel display) within the Sidekick panel. You
can programmatically control the background color and display text within each
individual cell of the grid from your Python script.

The grid can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization, or by adding it as a child
to a container's constructor.

This component is particularly useful for:

*   **Visualizing 2D Data:** Representing game maps, matrices, or cellular automata states.
*   **Simple Graphics:** Creating pixel art or basic pattern displays.
*   **Interactive Elements:** Building simple interactive boards or simulations
    where the user can click on cells to trigger actions or provide input to
    your Python script (using `on_click()` or the `on_click` constructor parameter).

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
    >>>
    >>> def user_clicked_cell(x, y):
    ...     grid_in_row.set_text(x, y, "Clicked!")
    ...
    >>> grid_in_row = sidekick.Grid(5, 5, parent=my_row, on_click=user_clicked_cell)
    >>> # sidekick.run_forever() # Keep script running to process clicks
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Callable, Dict, Any, Union

class Grid(BaseComponent):
    """Represents an interactive Grid component instance in the Sidekick UI.

    Instantiate this class to create a grid of cells. You can set cell colors,
    text, and respond to user clicks on individual cells. The grid can be
    nested within layout containers like `Row` or `Column`.

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
        on_click: Optional[Callable[[int, int], None]] = None, # New parameter
        on_error: Optional[Callable[[str], None]] = None, # For BaseComponent
    ):
        """Initializes the Grid object and creates the UI element.

        This function is called when you create a new Grid, for example:
        `game_board = sidekick.Grid(10, 10, on_click=handle_board_click)`

        It sends a message to the Sidekick UI to display a new grid.

        Args:
            num_columns (int): The number of columns the grid should have.
                Must be a positive integer (e.g., > 0).
            num_rows (int): The number of rows the grid should have.
                Must be a positive integer (e.g., > 0).
            parent (Optional[Union['BaseComponent', str]]): The parent container
                (e.g., a `sidekick.Row` or `sidekick.Column`) where this grid
                should be placed. If `None` (the default), the grid is added
                to the main Sidekick panel area.
            on_click (Optional[Callable[[int, int], None]]): A function to call
                when the user clicks on any cell in this grid. This is an
                alternative to using the `my_grid.on_click(callback)` method
                later. The function should accept two integer arguments: `x` (the
                column index of the clicked cell) and `y` (the row index).
                Defaults to `None`.
            on_error (Optional[Callable[[str], None]]): A function to call if
                an error related to this specific grid occurs in the Sidekick UI.
                The function should take one string argument (the error message).
                Defaults to `None`.

        Raises:
            ValueError: If `num_columns` or `num_rows` are not positive integers.
            SidekickConnectionError: If the library cannot connect to the
                Sidekick UI panel.
            TypeError: If `parent` is an invalid type, or if `on_click` or
                `on_error` are provided but are not callable functions.
        """
        if not isinstance(num_columns, int) or num_columns <= 0:
            raise ValueError("Grid num_columns must be a positive integer.")
        if not isinstance(num_rows, int) or num_rows <= 0:
             raise ValueError("Grid num_rows must be a positive integer.")

        # Prepare payload for the 'spawn' command.
        # Keys must be camelCase per the protocol.
        spawn_payload: Dict[str, Any] = {
            "numColumns": num_columns,
            "numRows": num_rows
        }

        # Initialize before super()
        self._num_columns = num_columns
        self._num_rows = num_rows
        self._click_callback: Optional[Callable[[int, int], None]] = None

        super().__init__(
            component_type="grid",
            payload=spawn_payload,
            parent=parent,
            on_error=on_error # Pass to BaseComponent's __init__
        )
        logger.info(
            f"Grid '{self.target_id}' initialized "
            f"(size={self.num_columns}x{self.num_rows})."
        )

        # Register on_click callback if provided in the constructor.
        if on_click is not None:
            self.on_click(on_click)

    @property
    def num_columns(self) -> int:
        """int: The number of columns in the grid (read-only).

        This value is set when the grid is created and cannot be changed afterwards.
        """
        return self._num_columns

    @property
    def num_rows(self) -> int:
        """int: The number of rows in the grid (read-only).

        This value is set when the grid is created and cannot be changed afterwards.
        """
        return self._num_rows

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this grid. (Internal).

        This method is called by the Sidekick connection manager when an event
        (like a "click") occurs on a cell of this grid in the UI.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "click" and self._click_callback:
                try:
                    # The UI sends the 'x' (column) and 'y' (row) of the click.
                    x = payload.get('x')
                    y = payload.get('y')
                    # Validate that x and y are indeed integers before calling callback.
                    if isinstance(x, int) and isinstance(y, int):
                        self._click_callback(x, y)
                    else:
                         # This indicates a potential protocol mismatch or UI bug.
                         logger.warning(
                            f"Grid '{self.target_id}' received 'click' event "
                            f"with missing or invalid coordinates: {payload}"
                         )
                except Exception as e:
                    # Prevent errors in user callback from crashing the listener.
                    logger.exception(
                        f"Error occurred inside Grid '{self.target_id}' on_click callback: {e}"
                    )
            elif event_type: # An event occurred but we don't have a handler or it's an unknown type
                 logger.debug(
                    f"Grid '{self.target_id}' received unhandled event type '{event_type}' "
                    f"or no click callback registered for 'click'."
                 )
        # Always call the base handler for potential 'error' messages or other base handling.
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[int, int], None]]):
        """Registers a function to call when the user clicks on any cell in this grid.

        The provided callback function will be executed in your Python script.
        It will receive two integer arguments: the `x` (column index) and `y`
        (row index) of the cell that was clicked. Coordinates are 0-indexed.

        You can also set this callback directly when creating the grid using
        the `on_click` parameter in its constructor.

        Args:
            callback (Optional[Callable[[int, int], None]]): The function to call
                when a cell is clicked. It must accept two integer arguments:
                `x` (column) and `y` (row). Pass `None` to remove a previously
                registered callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.

        Example:
            >>> def handle_grid_interaction(col_idx, row_idx):
            ...     print(f"Cell ({col_idx}, {row_idx}) was clicked.")
            ...     my_interactive_grid.set_color(col_idx, row_idx, "yellow")
            ...
            >>> my_interactive_grid = sidekick.Grid(3, 3)
            >>> my_interactive_grid.on_click(handle_grid_interaction)
            >>> # sidekick.run_forever() # Needed to process clicks
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for grid '{self.target_id}'.")
        self._click_callback = callback

    def set_color(self, x: int, y: int, color: Optional[str]):
        """Sets the background color of a specific cell in the grid.

        Args:
            x (int): The column index of the cell (0 to `num_columns - 1`).
            y (int): The row index of the cell (0 to `num_rows - 1`).
            color (Optional[str]): The desired background color for the cell,
                as a CSS color string (e.g., 'red', '#FF0000', 'rgb(0,255,0)').
                If you pass `None`, the cell's color will be reset to the default
                background color in the UI.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside
                        the grid's dimensions.
            SidekickConnectionError: If sending the command to the UI fails.
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

        # Prepare payload for the 'setColor' update action.
        # Keys must be camelCase per the protocol.
        options: Dict[str, Any] = {"x": x, "y": y, "color": color} # 'color' can be None
        update_payload = { "action": "setColor", "options": options }
        self._send_update(update_payload)
        # logger.debug(f"Grid '{self.target_id}' set_color({x},{y}) to {color}") # Can be verbose

    def set_text(self, x: int, y: int, text: Optional[str]):
        """Sets the text content displayed inside a specific cell.

        Any existing text in the cell will be replaced.

        Args:
            x (int): The column index of the cell (0 to `num_columns - 1`).
            y (int): The row index of the cell (0 to `num_rows - 1`).
            text (Optional[str]): The text string to display in the cell.
                If you pass `None` or an empty string `""`, any existing text
                in the cell will be cleared.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside
                        the grid's dimensions.
            SidekickConnectionError: If sending the command to the UI fails.
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

        # Convert text to string if not None, otherwise pass None.
        text_to_send = str(text) if text is not None else None
        # Prepare payload for the 'setText' update action.
        options: Dict[str, Any] = {"x": x, "y": y, "text": text_to_send}
        update_payload = { "action": "setText", "options": options }
        self._send_update(update_payload)
        # logger.debug(f"Grid '{self.target_id}' set_text({x},{y}) to '{text_to_send}'")

    def clear_cell(self, x: int, y: int):
        """Clears both the background color and text content of a specific cell.

        This resets the cell at the given `(x, y)` coordinates to its default
        appearance (default background color, no text).

        Args:
            x (int): The column index of the cell (0 to `num_columns - 1`).
            y (int): The row index of the cell (0 to `num_rows - 1`).

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside
                        the grid's dimensions.
            SidekickConnectionError: If sending the command to the UI fails.
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

        # Prepare payload for the 'clearCell' update action.
        options: Dict[str, Any] = {"x": x, "y": y} # No other options needed
        update_payload = { "action": "clearCell", "options": options }
        self._send_update(update_payload)
        logger.debug(f"Grid '{self.target_id}' cleared cell ({x},{y}).")

    def clear(self):
        """Clears the *entire grid*, resetting all cells to their default state.

        This will remove all text and custom background colors from every cell
        in the grid.

        Raises:
            SidekickConnectionError: If sending the command to the UI fails.
        """
        logger.info(f"Requesting clear for entire grid '{self.target_id}'.")
        # Prepare payload for the 'clear' update action (targets the whole grid).
        clear_payload = { "action": "clear" } # No options needed for a full grid clear
        self._send_update(clear_payload)

    def _reset_specific_callbacks(self):
        """Internal: Resets grid-specific callbacks when the component is removed."""
        super()._reset_specific_callbacks()
        self._click_callback = None
        logger.debug(f"Grid '{self.target_id}': Click callback reset.")