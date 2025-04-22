"""
Provides the Grid class for creating interactive 2D grids in Sidekick.

Use the `sidekick.Grid` class to create a grid of cells (like a spreadsheet
or checkerboard) in the Sidekick panel. You can control the background color
and display text within each cell.

This is useful for:
- Visualizing 2D data structures (e.g., game maps, matrices).
- Creating simple pixel-based animations or patterns.
- Building interactive simulations where the user can click on cells to
  trigger actions in your Python script.
"""

from . import logger
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Grid(BaseModule):
    """Represents an interactive Grid module instance in the Sidekick UI.

    Create an instance of this class to make a grid of cells appear in Sidekick.
    You must specify the number of columns and rows. You can then use methods
    like `set_color()` and `set_text()` to change the appearance of individual
    cells. You can also use `on_click()` to specify a function that should run
    when the user clicks a cell in the UI.

    Coordinate System:
        Methods like `set_color`, `set_text`, `clear_cell`, and the `on_click`
        callback use `(x, y)` coordinates to identify cells:
        - `x` represents the **column index** (starting from 0 at the left).
        - `y` represents the **row index** (starting from 0 at the top).

    Attributes:
        target_id (str): The unique identifier for this grid instance.
        num_columns (int): The number of columns this grid has.
        num_rows (int): The number of rows this grid has.
    """
    def __init__(
        self,
        num_columns: int,
        num_rows: int,
        instance_id: Optional[str] = None,
        spawn: bool = True
    ):
        """Initializes the Grid object and optionally creates the UI element.

        Sets up the grid's dimensions and prepares it for cell manipulation.

        Args:
            num_columns (int): The number of columns the grid should have.
                Must be a positive integer.
            num_rows (int): The number of rows the grid should have.
                Must be a positive integer.
            instance_id (Optional[str]): A specific ID for this grid instance.
                - If `spawn=True` (default): Optional. Auto-generated if None.
                - If `spawn=False`: **Required**. Must match the ID of an existing grid.
            spawn (bool): If True (default), creates a new grid element in Sidekick.
                If False, attaches to an existing grid element. The dimensions
                (`num_columns`, `num_rows`) are primarily used by the UI when
                spawning, but they are validated and stored locally regardless.

        Raises:
            ValueError: If `num_columns` or `num_rows` are not positive integers,
                        or if `spawn` is False and `instance_id` is not provided.
            TypeError: If `num_columns` or `num_rows` are missing.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established.

        Examples:
            >>> # Create a 10x5 grid
            >>> grid1 = sidekick.Grid(num_columns=10, num_rows=5)
            >>>
            >>> # Create another 8x8 grid
            >>> grid2 = sidekick.Grid(8, 8)
            >>>
            >>> # Attach to an existing grid named "game-board" (assuming it's 20x20)
            >>> board = sidekick.Grid(instance_id="game-board", spawn=False,
            ...                       num_columns=20, num_rows=20)
        """
        # --- Validate Dimensions ---
        if not (isinstance(num_columns, int) and num_columns > 0):
            raise ValueError(f"Grid num_columns must be a positive integer, got {num_columns}")
        if not (isinstance(num_rows, int) and num_rows > 0):
             raise ValueError(f"Grid num_rows must be a positive integer, got {num_rows}")

        # --- Prepare Spawn Payload ---
        spawn_payload: Dict[str, Any] = {}
        if spawn:
             # Keys must be camelCase for the protocol.
             spawn_payload["numColumns"] = num_columns
             spawn_payload["numRows"] = num_rows

        # --- Initialize Base Module ---
        # Handles connection, ID generation, handler registration, and sending spawn command.
        super().__init__(
            module_type="grid",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None
        )

        # --- Store Local State ---
        self.num_columns = num_columns
        self.num_rows = num_rows
        # Placeholder for the user's click callback function.
        self._click_callback: Optional[Callable[[int, int], None]] = None
        logger.info(f"Grid '{self.target_id}' initialized (spawn={spawn}, size={num_columns}x{num_rows}).")

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages specifically for this grid instance.

        This overrides the base class method to add handling for 'click' events.
        If a 'click' event arrives, it extracts the x and y coordinates and
        calls the registered `on_click` callback function.

        It still calls the base class's handler at the end to ensure 'error'
        messages are processed.

        Args:
            message (Dict[str, Any]): The raw message dictionary received.
        """
        msg_type = message.get("type")
        payload = message.get("payload") # Payload keys are expected to be camelCase.

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            # Is it a click event, and did the user register a handler?
            if event_type == "click" and self._click_callback:
                try:
                    # Extract coordinates from the payload.
                    x = payload.get('x')
                    y = payload.get('y')
                    # Ensure coordinates were received correctly.
                    if x is not None and isinstance(x, int) and \
                       y is not None and isinstance(y, int):
                        # Call the user's registered function with the coordinates!
                        self._click_callback(x, y)
                    else:
                         logger.warning(f"Grid '{self.target_id}' received click event with missing or invalid coordinates: {payload}")
                except Exception as e:
                    # Catch errors within the user's callback.
                    logger.exception(f"Error in Grid '{self.target_id}' on_click callback: {e}")
            else:
                 # Log other event types if needed for debugging.
                 logger.debug(f"Grid '{self.target_id}' received unhandled event type '{event_type}'.")

        # Call the base class handler to process potential 'error' messages.
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[int, int], None]]):
        """Registers a function to call when a user clicks on any cell in this grid.

        When the user clicks a cell in the Sidekick UI panel, the `callback`
        function you provide here will be executed in your Python script.

        Args:
            callback (Optional[Callable[[int, int], None]]): The function to call
                when a cell is clicked. This function should accept two arguments:
                1. `x` (int): The column index (0-based) of the clicked cell.
                2. `y` (int): The row index (0-based) of the clicked cell.
                Pass `None` to remove any previously registered callback.

        Raises:
            TypeError: If the provided `callback` is not a function (or None).

        Returns:
            None

        Examples:
            >>> def handle_cell_click(x, y):
            ...     print(f"Cell ({x}, {y}) was clicked!")
            ...     # Example: Highlight the clicked cell
            ...     grid.set_color(x, y, "yellow")
            ...
            >>> grid = sidekick.Grid(5, 5)
            >>> grid.on_click(handle_cell_click)
            >>>
            >>> # Important: Keep the script running to listen for clicks!
            >>> sidekick.run_forever()
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for grid '{self.target_id}'.")
        self._click_callback = callback

    # --- Error Callback ---
    # Inherits on_error(callback) method from BaseModule. Use this to handle
    # potential errors reported by the Grid UI element itself.

    def set_color(self, x: int, y: int, color: Optional[str]):
        """Sets the background color of a specific cell in the grid.

        Changes the visual appearance of one square in the grid UI. This does
        not affect any text that might be displayed in the cell.

        Args:
            x (int): The column index (0 to `num_columns - 1`) of the cell.
            y (int): The row index (0 to `num_rows - 1`) of the cell.
            color (Optional[str]): The desired background color as a CSS color
                string (e.g., 'red', '#00ff00', 'rgba(0, 0, 255, 0.5)').
                Pass `None` to clear the background color, resetting it to the
                default appearance.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                        grid's boundaries.

        Returns:
            None

        Examples:
            >>> grid = sidekick.Grid(4, 4)
            >>> # Set cell (0, 0) (top-left) to red
            >>> grid.set_color(0, 0, "red")
            >>> # Set cell (3, 3) (bottom-right) to semi-transparent green
            >>> grid.set_color(3, 3, "rgba(0, 255, 0, 0.5)")
            >>> # Clear the color of cell (0, 0)
            >>> grid.set_color(0, 0, None)
        """
        # --- Bounds Check ---
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (0 <= y < {self.num_rows}).")

        # --- Prepare and Send Command ---
        # Keys in options must be camelCase. Sending None for color clears it.
        options: Dict[str, Any] = {"x": x, "y": y, "color": color}
        update_payload = { "action": "setColor", "options": options }
        self._send_update(update_payload)


    def set_text(self, x: int, y: int, text: Optional[str]):
        """Sets the text content displayed inside a specific cell.

        Places the given text string within the boundaries of the specified cell
        in the Sidekick UI. Setting text does not affect the cell's background color.

        Args:
            x (int): The column index (0 to `num_columns - 1`) of the cell.
            y (int): The row index (0 to `num_rows - 1`) of the cell.
            text (Optional[str]): The text to display. If you pass `None` or an
                empty string `""`, any existing text in the cell will be cleared.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                        grid's boundaries.

        Returns:
            None

        Examples:
            >>> grid = sidekick.Grid(3, 3)
            >>> # Put "X" in the center cell
            >>> grid.set_text(1, 1, "X")
            >>> # Put "Start" in the top-left cell
            >>> grid.set_text(0, 0, "Start")
            >>> # Clear the text from the center cell
            >>> grid.set_text(1, 1, None)
            >>> # Also clears text
            >>> grid.set_text(0, 0, "")
        """
        # --- Bounds Check ---
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (0 <= y < {self.num_rows}).")

        # --- Prepare and Send Command ---
        # Ensure text is a string or None.
        text_to_send = str(text) if text is not None else None
        # Keys must be camelCase. Sending None or "" should clear the text.
        options: Dict[str, Any] = {"x": x, "y": y, "text": text_to_send}
        update_payload = { "action": "setText", "options": options }
        self._send_update(update_payload)

    def clear_cell(self, x: int, y: int):
        """Clears both the background color and the text content of a specific cell.

        Resets the cell to its default visual state (default background, no text).

        Args:
            x (int): The column index (0 to `num_columns - 1`) of the cell to clear.
            y (int): The row index (0 to `num_rows - 1`) of the cell to clear.

        Raises:
            IndexError: If the provided `x` or `y` coordinates are outside the
                        grid's boundaries.

        Returns:
            None

        Examples:
            >>> grid = sidekick.Grid(4,4)
            >>> grid.set_color(3, 3, "purple")
            >>> grid.set_text(3, 3, "Value")
            >>> # Reset cell (3, 3) completely
            >>> grid.clear_cell(3, 3)
        """
        # --- Bounds Check ---
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (0 <= y < {self.num_rows}).")

        # --- Prepare and Send Command ---
        # Keys must be camelCase.
        options: Dict[str, Any] = {"x": x, "y": y}
        update_payload = { "action": "clearCell", "options": options }
        self._send_update(update_payload)

    def clear(self):
        """Clears the *entire grid*, resetting all cells to their default state.

        This removes all custom background colors and all text from every cell
        in the grid, making it look like it did when it was first created.

        Returns:
            None

        Examples:
            >>> grid = sidekick.Grid(5, 5)
            >>> grid.set_color(0, 0, "red")
            >>> grid.set_text(1, 1, "Hi")
            >>> grid.set_color(4, 4, "blue")
            >>> # Now clear everything
            >>> grid.clear()
        """
        logger.info(f"Requesting clear for entire grid '{self.target_id}'.")
        # Action 'clear' with no options clears the whole grid.
        clear_payload = { "action": "clear" }
        self._send_update(clear_payload)

    def _reset_specific_callbacks(self):
        """Resets grid-specific callbacks when the module is removed."""
        # Called by BaseModule.remove()
        self._click_callback = None

    # --- Removal ---
    # Inherits the remove() method from BaseModule to remove the grid element.