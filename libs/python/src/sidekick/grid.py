"""Provides the Grid class for creating interactive 2D grids in Sidekick.

Use the `sidekick.Grid` class to create a grid of rectangular cells (like a
spreadsheet, checkerboard, or pixel display) within the Sidekick panel. You
can programmatically control the background color and display text within each
individual cell of the grid from your Python script.

The grid can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization, or by adding it as a child
to a container's constructor. You can also provide an `instance_id` to uniquely
identify the grid.

This component is particularly useful for:

*   **Visualizing 2D Data:** Representing game maps, matrices, or cellular automata states.
*   **Simple Graphics:** Creating pixel art or basic pattern displays.
*   **Interactive Elements:** Building simple interactive boards or simulations
    where the user can click on cells to trigger actions or provide input to
    your Python script (using `on_click()` or the `on_click` constructor parameter,
    where the callback receives a `GridClickEvent` object).

Coordinate System:
    Methods like `set_color`, `set_text`, `clear_cell`, and the `on_click` callback
    use `(x, y)` coordinates to identify specific cells within the grid:

    *   `x` represents the **column index**, starting from 0 for the leftmost column.
    *   `y` represents the **row index**, starting from 0 for the topmost row.

    So, `(0, 0)` is the top-left cell.

Basic Usage:
    >>> import sidekick
    >>> my_grid = sidekick.Grid(num_columns=4, num_rows=3, instance_id="main-board")
    >>> my_grid.set_color(x=0, y=0, color='blue')

Interactive Usage with a Parent Container:
    >>> import sidekick
    >>> from sidekick.events import GridClickEvent # Import the event type
    >>>
    >>> my_row = sidekick.Row()
    >>>
    >>> def user_clicked_cell(event: GridClickEvent):
    ...     print(f"Grid '{event.instance_id}' clicked at ({event.x}, {event.y})")
    ...     # Assume grid_in_row is accessible or passed differently if needed
    ...     grid_in_row.set_text(event.x, event.y, "Clicked!")
    ...
    >>> grid_in_row = sidekick.Grid(
    ...     num_columns=5,
    ...     num_rows=5,
    ...     parent=my_row,
    ...     instance_id="interactive-grid",
    ...     on_click=user_clicked_cell
    ... )
    >>> # sidekick.run_forever() # Keep script running to process clicks
"""

from . import logger
from .component import Component
from .events import GridClickEvent, ErrorEvent
from typing import Optional, Callable, Dict, Any, Union, Coroutine

class Grid(Component):
    """Represents an interactive Grid component instance in the Sidekick UI.

    Instantiate this class to create a grid of cells. You can set cell colors,
    text, and respond to user clicks on individual cells. The grid can be
    nested within layout containers like `Row` or `Column`.

    Attributes:
        instance_id (str): The unique identifier for this grid instance.
        num_columns (int): The number of columns this grid has (read-only).
        num_rows (int): The number of rows this grid has (read-only).
    """
    def __init__(
        self,
        num_columns: int,
        num_rows: int,
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_click: Optional[Callable[[GridClickEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
        on_error: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
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
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this grid. If `None`, an ID will be auto-generated. Must be
                unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Row` or `sidekick.Column`) where this grid
                should be placed. If `None` (the default), the grid is added
                to the main Sidekick panel area.
            on_click (Optional[Callable[[GridClickEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call
                when the user clicks on any cell in this grid. The function should
                accept one `GridClickEvent` object as an argument, which contains
                `instance_id`, `type`, `x` (column index), and `y` (row index)
                of the clicked cell. The callback can be a regular function or a coroutine function (async def).
                Defaults to `None`.
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call if
                an error related to this specific grid occurs in the Sidekick UI.
                The function should take one `ErrorEvent` object as an argument.
                The callback can be a regular function or a coroutine function (async def).
                Defaults to `None`.

        Raises:
            ValueError: If `num_columns` or `num_rows` are not positive integers,
                        or if the provided `instance_id` is invalid or a duplicate.
            TypeError: If `parent` is an invalid type, or if `on_click` or
                `on_error` are provided but are not callable functions.
        """
        if not isinstance(num_columns, int) or num_columns <= 0:
            raise ValueError("Grid num_columns must be a positive integer.")
        if not isinstance(num_rows, int) or num_rows <= 0:
             raise ValueError("Grid num_rows must be a positive integer.")

        # Prepare payload for the 'spawn' command.
        spawn_payload: Dict[str, Any] = {
            "numColumns": num_columns,
            "numRows": num_rows
        }

        # Initialize before super()
        self._num_columns = num_columns
        self._num_rows = num_rows
        self._click_callback: Optional[Callable[[GridClickEvent], Union[None, Coroutine[Any, Any, None]]]] = None

        super().__init__(
            component_type="grid",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        logger.info(
            f"Grid '{self.instance_id}' initialized " # Use self.instance_id
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
        It constructs a `GridClickEvent` object and passes it to the registered callback.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "click":
                logger.debug(f"Grid '{self.instance_id}' received click event.")
                # The UI sends the 'x' (column) and 'y' (row) of the click.
                x_coord = payload.get('x')
                y_coord = payload.get('y')

                # Validate that x and y are indeed integers before calling callback.
                if isinstance(x_coord, int) and isinstance(y_coord, int):
                    # Construct the GridClickEvent object
                    click_event = GridClickEvent(
                        instance_id=self.instance_id, # Component's own ID
                        type="click",
                        x=x_coord,
                        y=y_coord
                    )
                    self._invoke_callback(self._click_callback, click_event)
                else:
                     # This indicates a potential protocol mismatch or UI bug.
                     logger.warning(
                        f"Grid '{self.instance_id}' received 'click' event "
                        f"with missing or invalid coordinates: {payload}"
                     )
                return

        # Call the base handler for potential 'error' messages or other base handling.
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[GridClickEvent], Union[None, Coroutine[Any, Any, None]]]]):
        """Registers a function to call when the user clicks on any cell in this grid.

        The provided callback function will be executed in your Python script.
        It will receive a `GridClickEvent` object containing the `instance_id` of
        this grid, the event `type` ("click"), and the `x` (column index) and `y`
        (row index) of the cell that was clicked. Coordinates are 0-indexed.

        You can also set this callback directly when creating the grid using
        the `on_click` parameter in its constructor.

        Args:
            callback (Optional[Callable[[GridClickEvent], Union[None, Coroutine[Any, Any, None]]]]): The function to call
                when a cell is clicked. It must accept one `GridClickEvent` argument.
                The callback can be a regular function or a coroutine function (async def).
                Pass `None` to remove a previously registered callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.

        Example:
            >>> from sidekick.events import GridClickEvent
            >>>
            >>> def handle_grid_interaction(event: GridClickEvent):
            ...     print(f"Grid '{event.instance_id}' cell ({event.x}, {event.y}) was clicked.")
            ...     my_interactive_grid.set_color(event.x, event.y, "yellow")
            ...
            >>> my_interactive_grid = sidekick.Grid(3, 3, instance_id="game-board")
            >>> my_interactive_grid.on_click(handle_grid_interaction)
            >>> # sidekick.run_forever() # Needed to process clicks
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for grid '{self.instance_id}'.")
        self._click_callback = callback

    def click(self, func: Callable[[GridClickEvent], Union[None, Coroutine[Any, Any, None]]]) -> Callable[[GridClickEvent], Union[None, Coroutine[Any, Any, None]]]:
        """Decorator to register a function to call when a cell in this grid is clicked.

        This provides an alternative, more Pythonic way to set the click handler
        if you prefer decorators. The decorated function will receive a
        `GridClickEvent` object as its argument.

        Args:
            func (Callable[[GridClickEvent], Union[None, Coroutine[Any, Any, None]]]): The function to register as the click handler.
                It should accept one `GridClickEvent` argument. The callback can be a regular
                function or a coroutine function (async def).

        Returns:
            Callable[[GridClickEvent], Union[None, Coroutine[Any, Any, None]]]: The original function, allowing the decorator to be used directly.

        Raises:
            TypeError: If `func` is not a callable function.

        Example:
            >>> from sidekick.events import GridClickEvent
            >>>
            >>> my_board = sidekick.Grid(5, 5, instance_id="decorator-grid")
            >>>
            >>> @my_board.click
            ... def highlight_cell(event: GridClickEvent):
            ...     print(f"Grid '{event.instance_id}' cell ({event.x}, {event.y}) clicked via decorator!")
            ...     my_board.set_color(event.x, event.y, "magenta")
            ...
            >>> # sidekick.run_forever() # Needed to process clicks
        """
        self.on_click(func) # Register the function using the standard method
        return func # Return the original function

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
                f"Grid '{self.instance_id}': Column index x={x} is out of bounds "
                f"(must be 0 <= x < {self.num_columns})."
            )
        if not (0 <= y < self.num_rows):
              raise IndexError(
                f"Grid '{self.instance_id}': Row index y={y} is out of bounds "
                f"(must be 0 <= y < {self.num_rows})."
            )

        # Prepare payload for the 'setColor' update action.
        options: Dict[str, Any] = {"x": x, "y": y, "color": color} # 'color' can be None
        update_payload = { "action": "setColor", "options": options }
        self._send_update(update_payload)
        # logger.debug(f"Grid '{self.instance_id}' set_color({x},{y}) to {color}") # Can be verbose

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
                f"Grid '{self.instance_id}': Column index x={x} is out of bounds "
                f"(must be 0 <= x < {self.num_columns})."
            )
        if not (0 <= y < self.num_rows):
              raise IndexError(
                f"Grid '{self.instance_id}': Row index y={y} is out of bounds "
                f"(must be 0 <= y < {self.num_rows})."
            )

        # Convert text to string if not None, otherwise pass None.
        text_to_send = str(text) if text is not None else None
        # Prepare payload for the 'setText' update action.
        options: Dict[str, Any] = {"x": x, "y": y, "text": text_to_send}
        update_payload = { "action": "setText", "options": options }
        self._send_update(update_payload)
        # logger.debug(f"Grid '{self.instance_id}' set_text({x},{y}) to '{text_to_send}'")

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
                f"Grid '{self.instance_id}': Column index x={x} is out of bounds "
                f"(must be 0 <= x < {self.num_columns})."
            )
        if not (0 <= y < self.num_rows):
              raise IndexError(
                f"Grid '{self.instance_id}': Row index y={y} is out of bounds "
                f"(must be 0 <= y < {self.num_rows})."
            )

        # Prepare payload for the 'clearCell' update action.
        options: Dict[str, Any] = {"x": x, "y": y} # No other options needed
        update_payload = { "action": "clearCell", "options": options }
        self._send_update(update_payload)
        logger.debug(f"Grid '{self.instance_id}' cleared cell ({x},{y}).")

    def clear(self):
        """Clears the *entire grid*, resetting all cells to their default state.

        This will remove all text and custom background colors from every cell
        in the grid.

        Raises:
            SidekickConnectionError: If sending the command to the UI fails.
        """
        logger.info(f"Requesting clear for entire grid '{self.instance_id}'.")
        # Prepare payload for the 'clear' update action (targets the whole grid).
        clear_payload = { "action": "clear" } # No options needed for a full grid clear
        self._send_update(clear_payload)

    def _reset_specific_callbacks(self):
        """Internal: Resets grid-specific callbacks when the component is removed."""
        super()._reset_specific_callbacks()
        self._click_callback = None
        logger.debug(f"Grid '{self.instance_id}': Click callback reset.")
