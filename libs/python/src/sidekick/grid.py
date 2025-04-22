"""Provides the Grid class for creating interactive 2D grids in Sidekick.

Use the `sidekick.Grid` class to create a grid of rectangular cells (like a
spreadsheet, checkerboard, or pixel display) within the Sidekick panel. You
can programmatically control the background color and display text within each
individual cell of the grid from your Python script.

This module is particularly useful for:

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
    >>> # Create a small 4x3 grid
    >>> my_grid = sidekick.Grid(num_columns=4, num_rows=3)
    >>>
    >>> # Set the background color of the top-left cell to blue
    >>> my_grid.set_color(x=0, y=0, color='blue')
    >>>
    >>> # Put the text "Hi" in the cell at column 1, row 2 (bottom middle)
    >>> my_grid.set_text(x=1, y=2, text='Hi')
    >>>
    >>> # Clear the content and color of the top-left cell
    >>> my_grid.clear_cell(x=0, y=0)

Interactive Usage:
    >>> import sidekick
    >>> grid = sidekick.Grid(5, 5)
    >>>
    >>> def user_clicked_cell(x, y):
    ...     print(f"User clicked cell at column {x}, row {y}")
    ...     grid.set_text(x, y, "Clicked!") # Show feedback in the grid
    ...
    >>> grid.on_click(user_clicked_cell)
    >>> print("Click on the grid cells in the Sidekick panel!")
    >>> sidekick.run_forever() # Keep script alive to listen for clicks
"""

from . import logger
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Grid(BaseModule):
    """Represents an interactive Grid module instance in the Sidekick UI.

    Instantiate this class to create a grid of cells with specified dimensions
    in the Sidekick panel. You can then manipulate individual cells using methods
    like `set_color()`, `set_text()`, `clear_cell()`, or clear the entire grid
    with `clear()`. Use `on_click()` to register a function that responds to user
    clicks on the grid cells.

    Attributes:
        target_id (str): The unique identifier for this grid instance.
        num_columns (int): The number of columns this grid has (read-only).
        num_rows (int): The number of rows this grid has (read-only).
    """
    def __init__(
        self,
        num_columns: int,
        num_rows: int,
        instance_id: Optional[str] = None,
        spawn: bool = True
    ):
        """Initializes the Grid object and optionally creates the UI element.

        Sets up the grid's dimensions and prepares it for interaction. Establishes
        the connection to Sidekick if not already done (this might block).

        Args:
            num_columns (int): The number of columns the grid should have. Must be
                a positive integer (greater than 0).
            num_rows (int): The number of rows the grid should have. Must be a
                positive integer (greater than 0).
            instance_id (Optional[str]): A specific ID for this grid instance.
                - If `spawn=True` (default): Optional. If None, a unique ID (e.g.,
                  "grid-1") is generated automatically.
                - If `spawn=False`: **Required**. Must match the ID of an existing
                  grid element in the Sidekick UI to attach to.
            spawn (bool): If True (the default), a command is sent to Sidekick
                to create a new grid UI element with the specified dimensions.
                If False, the library assumes a grid element with the given
                `instance_id` already exists, and this Python object simply
                connects to it. The `num_columns` and `num_rows` arguments are
                still validated locally when `spawn=False` but are not sent in
                the (empty) spawn command.

        Raises:
            ValueError: If `num_columns` or `num_rows` are not positive integers,
                        or if `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established during initialization.

        Examples:
            >>> # Create a standard 8x8 grid
            >>> board_grid = sidekick.Grid(num_columns=8, num_rows=8)
            >>>
            >>> # Create a wide grid
            >>> wide_grid = sidekick.Grid(20, 5)
            >>>
            >>> # Attach to an existing grid named "level-map" (assume it's 30x20)
            >>> map_control = sidekick.Grid(instance_id="level-map", spawn=False,
            ...                             num_columns=30, num_rows=20)
        """
        # --- Validate Dimensions ---
        if not isinstance(num_columns, int) or num_columns <= 0:
            raise ValueError("Grid num_columns must be a positive integer.")
        if not isinstance(num_rows, int) or num_rows <= 0:
             raise ValueError("Grid num_rows must be a positive integer.")

        # --- Prepare Spawn Payload ---
        # Payload is only needed if we are creating (spawning) a new grid.
        spawn_payload: Dict[str, Any] = {}
        if spawn:
             # Keys must be camelCase for the protocol specification.
             spawn_payload["numColumns"] = num_columns
             spawn_payload["numRows"] = num_rows

        # --- Initialize Base Module ---
        # Handles connection activation, ID assignment, handler registration,
        # and sending the 'spawn' command with the payload if spawn=True.
        super().__init__(
            module_type="grid",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None # Send payload only if spawning
        )

        # --- Store Local State (Dimensions) ---
        # Store dimensions primarily for bounds checking in methods like set_color/set_text.
        # Make them pseudo-read-only by convention.
        self._num_columns = num_columns
        self._num_rows = num_rows

        # --- Initialize Callback ---
        # Placeholder for the user's click callback function.
        self._click_callback: Optional[Callable[[int, int], None]] = None
        # Log initialization details.
        spawn_info = f"size={self.num_columns}x{self.num_rows}" if spawn else "attaching to existing"
        logger.info(f"Grid '{self.target_id}' initialized ({spawn_info}).")

    # --- Read-only Properties for Dimensions ---
    @property
    def num_columns(self) -> int:
        """int: The number of columns in the grid (read-only)."""
        return self._num_columns

    @property
    def num_rows(self) -> int:
        """int: The number of rows in the grid (read-only)."""
        return self._num_rows


    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this grid. (Internal).

        Overrides the base class method to specifically process 'click' events
        originating from the grid UI element. When a 'click' event arrives, it
        extracts the clicked cell's `x` (column) and `y` (row) coordinates from
        the payload and, if an `on_click` callback function is registered, calls
        that function with the coordinates.

        It delegates to the base class's handler (`super()._internal_message_handler`)
        at the end to ensure standard 'error' message processing still occurs.

        Args:
            message (Dict[str, Any]): The raw message dictionary received. Expected
                payload keys are camelCase.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload keys are expected to be camelCase.

        # Handle 'event' messages specifically
        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            # Check if it's a 'click' event AND if the user has registered a handler.
            if event_type == "click" and self._click_callback:
                try:
                    # Extract integer coordinates (x=column, y=row) from the payload.
                    x = payload.get('x')
                    y = payload.get('y')
                    # Ensure coordinates were received correctly and are integers.
                    if isinstance(x, int) and isinstance(y, int):
                        # Coordinates are valid, call the user's registered callback!
                        self._click_callback(x, y)
                    else:
                         # Log a warning if coordinates are missing or not integers.
                         logger.warning(f"Grid '{self.target_id}' received 'click' event with missing or invalid coordinates: {payload}")
                except Exception as e:
                    # IMPORTANT: Catch errors *within* the user's callback function
                    # to prevent crashing the library's background listener thread.
                    logger.exception(f"Error occurred inside Grid '{self.target_id}' on_click callback: {e}")
            else:
                 # Log other unhandled event types or if no callback was registered.
                 logger.debug(f"Grid '{self.target_id}' received unhandled event type '{event_type}' or no click callback registered.")

        # ALWAYS call the base class handler. This is crucial for processing
        # 'error' messages sent from the UI related to this specific grid instance.
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[int, int], None]]):
        """Registers a function to call when the user clicks on any cell in this grid.

        When the user clicks a cell within this grid in the Sidekick UI panel, the
        `callback` function you provide here will be executed within your running
        Python script.

        Args:
            callback (Optional[Callable[[int, int], None]]): The function to call
                when a cell is clicked. This function must accept two integer arguments:
                1. `x` (int): The **column index** (0-based, from left) of the clicked cell.
                2. `y` (int): The **row index** (0-based, from top) of the clicked cell.
                Pass `None` to remove any previously registered click callback.

        Raises:
            TypeError: If the provided `callback` is not a callable function (or `None`).

        Example:
            >>> import sidekick
            >>> grid = sidekick.Grid(10, 10)
            >>>
            >>> def paint_cell(column, row):
            ...     print(f"Painting cell at ({column}, {row})")
            ...     grid.set_color(column, row, "lightblue") # Change color on click
            ...
            >>> grid.on_click(paint_cell)
            >>> print("Click on the grid cells in Sidekick to paint them!")
            >>>
            >>> # Keep the script running to listen for clicks!
            >>> sidekick.run_forever()
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for grid '{self.target_id}'.")
        self._click_callback = callback

    # --- Error Callback ---
    # Inherits the on_error(callback) method directly from BaseModule.
    # Use `grid.on_error(my_handler)` to register a function that will be
    # called if the Grid UI element itself reports an error back to Python
    # (e.g., if it failed to process a `set_color` command due to an internal UI issue).

    def set_color(self, x: int, y: int, color: Optional[str]):
        """Sets the background color of a specific cell in the grid.

        Changes the visual appearance of a single cell (square) in the grid UI.
        This operation does not affect any text that might be displayed in the cell.

        Args:
            x (int): The **column index** (0 to `num_columns - 1`) of the target cell.
            y (int): The **row index** (0 to `num_rows - 1`) of the target cell.
            color (Optional[str]): The desired background color for the cell. This
                should be a string representing a color in a standard CSS format,
                such as:
                - Color names: 'red', 'blue', 'lightgray'
                - Hex codes: '#FF0000', '#00F', '#abcdef'
                - RGB: 'rgb(0, 255, 0)', 'rgba(0, 0, 255, 0.5)' (for transparency)
                - HSL: 'hsl(120, 100%, 50%)', 'hsla(240, 50%, 50%, 0.7)'
                Pass `None` to clear any custom background color previously set for
                this cell, resetting it to the default grid cell background.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                        valid range of columns (0 to `num_columns-1`) or rows
                        (0 to `num_rows-1`).
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending the command fails.

        Example:
            >>> grid = sidekick.Grid(4, 4)
            >>> # Set cell (0, 0) (top-left) to red
            >>> grid.set_color(0, 0, "red")
            >>> # Set cell (3, 3) (bottom-right) to semi-transparent green
            >>> grid.set_color(3, 3, "rgba(0, 255, 0, 0.5)")
            >>> # Clear the color of cell (0, 0), reverting it to default
            >>> grid.set_color(0, 0, None)
        """
        # --- Bounds Check ---
        # Validate coordinates against the stored dimensions.
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (must be 0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (must be 0 <= y < {self.num_rows}).")

        # --- Prepare and Send Command ---
        # Construct the options dictionary with camelCase keys as required by the protocol.
        # Sending None for the color value signals the UI to clear the specific color.
        options: Dict[str, Any] = {"x": x, "y": y, "color": color}
        # Construct the full update payload for the 'setColor' action.
        update_payload = { "action": "setColor", "options": options }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(update_payload)


    def set_text(self, x: int, y: int, text: Optional[str]):
        """Sets the text content displayed inside a specific cell in the grid.

        Places the given text string within the boundaries of the specified cell
        in the Sidekick UI. Setting text does not affect the cell's background color.
        If the text is too long to fit, the UI might truncate it or handle overflow.

        Args:
            x (int): The **column index** (0 to `num_columns - 1`) of the target cell.
            y (int): The **row index** (0 to `num_rows - 1`) of the target cell.
            text (Optional[str]): The text string to display within the cell. Any
                Python object provided will be converted to its string representation
                using `str()`. If you pass `None` or an empty string `""`, any
                existing text currently displayed in the specified cell will be cleared.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                        valid range of columns (0 to `num_columns-1`) or rows
                        (0 to `num_rows-1`).
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending the command fails.

        Example:
            >>> grid = sidekick.Grid(3, 3)
            >>> # Put an "X" in the center cell (1, 1)
            >>> grid.set_text(1, 1, "X")
            >>> # Put a number in the top-right cell (2, 0)
            >>> count = 5
            >>> grid.set_text(2, 0, str(count)) # Convert number to string
            >>> # Clear the text from the center cell
            >>> grid.set_text(1, 1, None)
            >>> # Setting empty string also clears text
            >>> grid.set_text(2, 0, "")
        """
        # --- Bounds Check ---
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (must be 0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (must be 0 <= y < {self.num_rows}).")

        # --- Prepare and Send Command ---
        # Ensure the text is explicitly a string or None before sending.
        text_to_send = str(text) if text is not None else None
        # Construct options with camelCase keys. Sending None or "" clears text in UI.
        options: Dict[str, Any] = {"x": x, "y": y, "text": text_to_send}
        # Construct the full update payload for the 'setText' action.
        update_payload = { "action": "setText", "options": options }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(update_payload)

    def clear_cell(self, x: int, y: int):
        """Clears both the background color and the text content of a specific cell.

        Resets the specified cell `(x, y)` back to its default visual state, removing
        any custom background color set by `set_color()` and any text set by `set_text()`.

        Args:
            x (int): The **column index** (0 to `num_columns - 1`) of the cell to clear.
            y (int): The **row index** (0 to `num_rows - 1`) of the cell to clear.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                        valid grid boundaries.
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending the command fails.

        Example:
            >>> grid = sidekick.Grid(4, 4)
            >>> grid.set_color(3, 3, "purple")
            >>> grid.set_text(3, 3, "Value")
            >>> # Reset cell (3, 3) completely to its default state
            >>> grid.clear_cell(3, 3)
        """
        # --- Bounds Check ---
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (must be 0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (must be 0 <= y < {self.num_rows}).")

        # --- Prepare and Send Command ---
        # Construct options with camelCase keys.
        options: Dict[str, Any] = {"x": x, "y": y}
        # Construct the full update payload for the 'clearCell' action.
        update_payload = { "action": "clearCell", "options": options }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(update_payload)

    def clear(self):
        """Clears the *entire grid*, resetting all cells to their default state.

        Removes all custom background colors and all text content from *every cell*
        in the grid simultaneously. The grid will appear visually empty, as if it
        was just created.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending the command fails.

        Example:
            >>> grid = sidekick.Grid(5, 5)
            >>> grid.set_color(0, 0, "red")
            >>> grid.set_text(1, 1, "Hi")
            >>> grid.set_color(4, 4, "blue")
            >>> # ... other manipulations ...
            >>> # Now clear the entire grid back to its initial state
            >>> grid.clear()
        """
        logger.info(f"Requesting clear for entire grid '{self.target_id}'.")
        # Prepare the payload for the 'clear' action targeting the whole grid.
        # According to the protocol, this action doesn't require an 'options' field.
        clear_payload = { "action": "clear" }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(clear_payload)

    def _reset_specific_callbacks(self):
        """Internal: Resets grid-specific callbacks when the module is removed.

        Called automatically by the base class's `remove()` method.
        """
        # Reset the click callback reference for this grid instance.
        self._click_callback = None

    # --- Removal ---
    # Inherits the standard remove() method from BaseModule. Calling `grid.remove()`
    # will send a command to the Sidekick UI to remove this grid instance
    # and will perform local cleanup (unregistering handlers, resetting callbacks).