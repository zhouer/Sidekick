"""
Sidekick Canvas Module Interface.

This module provides the `Canvas` class, which allows your Python script
to interact with a 2D drawing canvas displayed in the Sidekick panel.
You can use it to draw simple shapes like lines, rectangles, and circles,
and control their appearance (color, line width).

Think of it like a simple digital whiteboard you can draw on from your code.
"""

from . import logger
from . import connection
from .base_module import BaseModule
from typing import Optional, Dict, Any, Callable

class Canvas(BaseModule):
    """Represents a 2D Canvas module instance in the Sidekick UI for basic drawing.

    Use this class to create a drawing area in Sidekick and draw simple shapes
    like lines, rectangles, and circles programmatically from your Python script.
    You can control the colors and line width for drawing.

    Each drawing command (`draw_line`, `draw_rect`, etc.) is sent with a unique
    internal ID (`commandId`) to help Sidekick process them reliably.

    Attributes:
        target_id (str): The unique identifier for this canvas instance.
        width (int): The width of the canvas in pixels.
        height (int): The height of the canvas in pixels.
    """
    def __init__(
        self,
        width: int,
        height: int,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        bg_color: Optional[str] = None
    ):
        """Initializes the Canvas object, optionally creating a new canvas in Sidekick.

        Sets up the canvas dimensions and prepares it for drawing commands.

        Args:
            width (int): The desired width of the canvas in pixels. Must be positive.
            height (int): The desired height of the canvas in pixels. Must be positive.
            instance_id (Optional[str]): A specific ID for this canvas instance.
                - If `spawn=True`: Optional. Auto-generated if None.
                - If `spawn=False`: **Required**. Identifies the existing canvas.
            spawn (bool): If True (default), creates a new canvas UI element.
                If False, attaches to an existing canvas element. `width`, `height`,
                and `bg_color` are ignored if `spawn=False`.
            bg_color (Optional[str]): A background color string (like 'white',
                '#f0f0f0', 'rgb(255, 0, 0)') for the canvas. Only used if
                `spawn=True`. Defaults to a standard background on the Sidekick side
                if not provided.

        Raises:
            ValueError: If `width` or `height` are not positive integers, or if
                        `spawn` is False and `instance_id` is None.

        Examples:
            >>> # Create a 300x200 canvas with a light gray background
            >>> canvas = sidekick.Canvas(300, 200, bg_color="#eeeeee")
            >>>
            >>> # Attach to an existing canvas named "drawing-area"
            >>> existing_canvas = sidekick.Canvas(width=1, height=1, # Dummy values needed
            ...                                 instance_id="drawing-area", spawn=False)
        """
        if not (isinstance(width, int) and width > 0 and isinstance(height, int) and height > 0):
            raise ValueError("Canvas width and height must be positive integers.")

        # Payload only matters if spawning a new instance.
        spawn_payload: Dict[str, Any] = {}
        if spawn:
             spawn_payload["width"] = width
             spawn_payload["height"] = height
             if bg_color:
                 spawn_payload["bgColor"] = bg_color # camelCase key

        super().__init__(
            module_type="canvas",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None,
        )
        # Store dimensions locally for potential future use or reference.
        self.width = width
        self.height = height
        logger.info(f"Canvas '{self.target_id}' initialized (spawn={spawn}, size={width}x{height}).")

    # _internal_message_handler is inherited from BaseModule and handles 'error'
    # Canvas currently doesn't have specific 'event' types to handle.

    # on_error is inherited from BaseModule

    def _send_canvas_command(self, action: str, options: Optional[Dict[str, Any]] = None):
        """Internal helper to construct and send a canvas update command.

        Automatically includes the next unique command ID required by the protocol.

        Args:
            action (str): The drawing or configuration action (e.g., "line", "rect").
            options (Optional[Dict[str, Any]]): Action-specific parameters.
                Keys should be camelCase. Defaults to an empty dictionary.

        Returns:
            None
        """
        # Ensure options is at least an empty dict if None is passed.
        options_payload = options or {}

        # Construct the full payload including the action, options, and commandId.
        update_payload = {
            "action": action,
            "options": options_payload,
            "commandId": connection.get_next_command_id() # Get unique ID for this command
        }
        self._send_update(update_payload)

    def clear(self, color: Optional[str] = None):
        """Clears the entire canvas, optionally filling it with a specific color.

        Args:
            color (Optional[str]): A color string (like 'white', '#ff0000') to fill
                the canvas after clearing. If None, it usually reverts to the
                initial background or becomes transparent, depending on Sidekick.

        Examples:
            >>> # Clear the canvas (revert to default background)
            >>> canvas.clear()
            >>> # Clear the canvas and make it blue
            >>> canvas.clear(color="blue")

        Returns:
            None
        """
        options = {}
        if color is not None:
            options["color"] = color
        self._send_canvas_command("clear", options)

    def config(
        self,
        stroke_style: Optional[str] = None,
        fill_style: Optional[str] = None,
        line_width: Optional[int] = None
    ):
        """Configures the drawing styles for subsequent drawing commands.

        Set the color used for outlines (`stroke_style`), the color for filling
        shapes (`fill_style`), and the thickness of lines (`line_width`). Any
        parameter left as `None` will not be changed in Sidekick.

        Args:
            stroke_style (Optional[str]): Color for lines and outlines (e.g., 'black', '#00FF00').
            fill_style (Optional[str]): Color for filling shapes (e.g., 'blue', '#FFFF00').
            line_width (Optional[int]): Width of lines in pixels.

        Examples:
            >>> # Set drawing color to red, fill color to yellow, line width to 3 pixels
            >>> canvas.config(stroke_style="red", fill_style="yellow", line_width=3)
            >>> # Only change the line width to 1
            >>> canvas.config(line_width=1)

        Returns:
            None
        """
        options = {}
        # Only include options if they are explicitly provided (not None).
        if stroke_style is not None: options["strokeStyle"] = stroke_style
        if fill_style is not None: options["fillStyle"] = fill_style
        if line_width is not None: options["lineWidth"] = line_width

        # Send the command only if there are actual configuration changes.
        if options:
            self._send_canvas_command("config", options)
        else:
             logger.debug(f"Canvas '{self.target_id}': config() called with no arguments to change.")

    def draw_line(self, x1: int, y1: int, x2: int, y2: int):
        """Draws a line segment on the canvas.

        Uses the current `stroke_style` and `line_width` set by `config()`.

        Args:
            x1 (int): Starting x-coordinate of the line.
            y1 (int): Starting y-coordinate of the line.
            x2 (int): Ending x-coordinate of the line.
            y2 (int): Ending y-coordinate of the line.

        Examples:
            >>> # Draw a diagonal line from top-left (10,10) to (50,50)
            >>> canvas.draw_line(10, 10, 50, 50)

        Returns:
            None
        """
        options = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        self._send_canvas_command("line", options)

    def draw_rect(self, x: int, y: int, width: int, height: int, filled: bool = False):
        """Draws a rectangle on the canvas.

        Args:
            x (int): X-coordinate of the top-left corner.
            y (int): Y-coordinate of the top-left corner.
            width (int): Width of the rectangle. Should be non-negative.
            height (int): Height of the rectangle. Should be non-negative.
            filled (bool): If True, fills the rectangle using the current `fill_style`.
                If False (default), draws only the outline using the current
                `stroke_style` and `line_width`.

        Examples:
            >>> # Draw the outline of a 50x30 rectangle at (20, 20)
            >>> canvas.draw_rect(20, 20, 50, 30)
            >>>
            >>> # Draw a filled red rectangle (assuming fill_style is red)
            >>> canvas.config(fill_style="red")
            >>> canvas.draw_rect(100, 50, 40, 40, filled=True)

        Returns:
            None
        """
        if width < 0 or height < 0:
             # Log a warning but allow the command to be sent; Sidekick might handle it.
             logger.warning(
                 f"Canvas '{self.target_id}': draw_rect called with negative width/height "
                 f"({width}x{height}). Behavior depends on Sidekick implementation."
             )
        options = {"x": x, "y": y, "width": width, "height": height, "filled": filled}
        self._send_canvas_command("rect", options)

    def draw_circle(self, cx: int, cy: int, radius: int, filled: bool = False):
        """Draws a circle on the canvas.

        Args:
            cx (int): X-coordinate of the center of the circle.
            cy (int): Y-coordinate of the center of the circle.
            radius (int): Radius of the circle. Must be positive.
            filled (bool): If True, fills the circle using the current `fill_style`.
                If False (default), draws only the outline using the current
                `stroke_style` and `line_width`.

        Raises:
            ValueError: If `radius` is not positive (logs an error and ignores command).

        Examples:
            >>> # Draw the outline of a circle with radius 25 centered at (150, 100)
            >>> canvas.draw_circle(150, 100, 25)
            >>>
            >>> # Draw a filled green circle
            >>> canvas.config(fill_style="green")
            >>> canvas.draw_circle(50, 50, 20, filled=True)

        Returns:
            None
        """
        if radius <= 0:
             # Log error and return without sending command for invalid radius
             logger.error(f"Canvas '{self.target_id}': draw_circle radius must be positive. Ignoring command.")
             # Raise ValueError to notify the user more directly
             raise ValueError("Canvas draw_circle radius must be positive.")
        options = {"cx": cx, "cy": cy, "radius": radius, "filled": filled}
        self._send_canvas_command("circle", options)

    # The remove() method is inherited from BaseModule.