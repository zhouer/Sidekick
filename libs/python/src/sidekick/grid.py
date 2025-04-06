# Sidekick/libs/python/src/sidekick/grid.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Callable, Dict, Any

class Grid(BaseModule):
    """
    Represents an interactive Grid module instance in the Sidekick UI.

    This class allows you to create and manipulate a grid of cells displayed
    in Sidekick. You can set the background color and text content for each
    individual cell. You can also register callbacks for click events and errors.

    It supports two modes of initialization:
    1. Creating a new grid instance in Sidekick (`spawn=True`).
    2. Attaching to a pre-existing grid instance in Sidekick (`spawn=False`).

    Coordinate System:
        Methods like `set_cell`, `set_color`, `set_text`, and the `on_click` callback
        use `(x, y)` coordinates where:
        - `x` is the **column index** (0-based, starting from the left).
        - `y` is the **row index** (0-based, starting from the top, Y-axis points down).

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
        """
        Initializes the Grid object, optionally creating a new grid in Sidekick.

        Args:
            num_columns (int): The number of columns for the grid. Defaults to 16.
            num_rows (int): The number of rows for the grid. Defaults to 16.
            instance_id (Optional[str]): A unique identifier for this grid instance.
                - If `spawn=True`: Optional. Auto-generated if None.
                - If `spawn=False`: **Required**.
            spawn (bool): If True (default), creates a new grid instance in Sidekick.
                If False, attaches to an existing grid instance.

        Raises:
            ValueError: If dimensions are invalid or if `spawn` is False and `instance_id` is None.
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
        connection.logger.info(f"Grid '{self.target_id}' initialized (spawn={spawn}, size={num_columns}x{num_rows}).")

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
                         connection.logger.warning(f"Grid '{self.target_id}' received click event with missing coordinates: {payload}")
                except Exception as e:
                    connection.logger.exception(f"Error in Grid '{self.target_id}' on_click callback: {e}")
            else:
                 connection.logger.debug(f"Grid '{self.target_id}' received unhandled event type '{event_type}'.")

        # Call base handler for error messages
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[int, int], None]]):
        """
        Registers a function to be called when a cell in this grid is clicked.

        The callback function will receive two integer arguments:
        the x (column) and y (row) coordinate of the clicked cell.

        Args:
            callback: A function accepting `x` and `y` integers, or None to unregister.
        """
        if callback is not None and not callable(callback):
            raise TypeError("Click callback must be callable or None")
        connection.logger.info(f"Setting on_click callback for grid '{self.target_id}'.")
        self._click_callback = callback

    # on_error is inherited from BaseModule

    def set_cell(self, x: int, y: int, color: Optional[str] = None, text: Optional[str] = None):
        """
        Sets the state (color and/or text) of a specific cell in the Sidekick grid.

        Args:
            x (int): The **column index** (0-based).
            y (int): The **row index** (0-based).
            color (Optional[str]): Background color (CSS string or None to clear).
            text (Optional[str]): Text content (string or None to clear).

        Raises:
            IndexError: If coordinates are out of bounds.
        """
        if not (0 <= x < self.num_columns):
             raise IndexError(f"Grid '{self.target_id}': Column index x={x} is out of bounds (0 <= x < {self.num_columns}).")
        if not (0 <= y < self.num_rows):
              raise IndexError(f"Grid '{self.target_id}': Row index y={y} is out of bounds (0 <= y < {self.num_rows}).")

        if color is None and text is None:
            # No change specified, though frontend might interpret differently than just not sending
            connection.logger.debug(f"Grid '{self.target_id}': set_cell called for (x={x}, y={y}) with no changes specified.")
            # We still send the update in case the frontend clears attributes on null
            # return

        options: Dict[str, Any] = {"x": x, "y": y}
        if color is not None: options["color"] = color
        if text is not None: options["text"] = str(text)

        update_payload = { "action": "setCell", "options": options }
        self._send_update(update_payload)

    def set_color(self, x: int, y: int, color: Optional[str]):
        """
        Sets **only** the background color of a specific cell.

        Args:
            x (int): Column index.
            y (int): Row index.
            color (Optional[str]): Color string or None to clear.

        Raises:
            IndexError: If coordinates are out of bounds.
        """
        self.set_cell(x=x, y=y, color=color, text=None) # Send text as None explicitly

    def set_text(self, x: int, y: int, text: Optional[str]):
        """
        Sets **only** the text content of a specific cell.

        Args:
            x (int): Column index.
            y (int): Row index.
            text (Optional[str]): Text string or None/"" to clear.

        Raises:
            IndexError: If coordinates are out of bounds.
        """
        self.set_cell(x=x, y=y, color=None, text=text) # Send color as None explicitly

    def clear(self):
        """Clears the entire grid in Sidekick."""
        connection.logger.info(f"Requesting clear for grid '{self.target_id}'.")
        clear_payload = { "action": "clear" }
        self._send_update(clear_payload)

    def _reset_specific_callbacks(self):
        """Resets grid-specific callbacks on removal."""
        self._click_callback = None

    # remove() is inherited from BaseModule