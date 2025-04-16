"""
Provides the Canvas class for creating a 2D drawing surface in Sidekick.

Use the `sidekick.Canvas` class to create a blank area in the Sidekick panel
where you can draw simple shapes like lines, rectangles, and circles using
Python commands.

Think of it as a basic digital whiteboard or a simple drawing API that lets
you visually represent geometric concepts or create simple graphics controlled
by your script.
"""

from . import logger
from . import connection # Required for get_next_command_id
from .base_module import BaseModule
from typing import Optional, Dict, Any, Callable # Callable is included for consistency, though not used directly here

class Canvas(BaseModule):
    """Represents a 2D drawing canvas module instance in the Sidekick UI.

    Create an instance of this class to get a drawing area in Sidekick.
    You can then call methods like `draw_line()`, `draw_rect()`, and
    `draw_circle()` to draw shapes on it. Use `config()` to change the
    drawing color, fill color, and line thickness.

    Each drawing command sent to the UI includes a unique sequential ID
    (`commandId`) to help Sidekick process drawing operations reliably,
    especially if commands are sent very quickly.

    Attributes:
        target_id (str): The unique identifier for this canvas instance.
        width (int): The width of the canvas in pixels, as specified during creation.
        height (int): The height of the canvas in pixels, as specified during creation.
    """
    def __init__(
        self,
        width: int,
        height: int,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        bg_color: Optional[str] = None
    ):
        """Initializes the Canvas object and optionally creates the UI element.

        Sets up the dimensions and background color for the canvas.

        Args:
            width (int): The desired width of the canvas in pixels. Must be positive.
            height (int): The desired height of the canvas in pixels. Must be positive.
            instance_id (Optional[str]): A specific ID for this canvas instance.
                - If `spawn=True` (default): Optional. A unique ID will be
                  auto-generated if not provided.
                - If `spawn=False`: **Required**. Must match the ID of an
                  existing canvas element in the Sidekick UI.
            spawn (bool): If True (default), a command is sent to create a new
                canvas element in the Sidekick UI. If False, the library assumes
                the canvas element already exists, and this object attaches to it.
                If `spawn=False`, the `width`, `height`, and `bg_color` arguments
                are ignored when sending the (empty) spawn command, but `width`
                and `height` are still validated and stored locally.
            bg_color (Optional[str]): A CSS color string for the canvas background
                (e.g., 'white', '#f0f0f0', 'rgb(50, 50, 50)'). Only used if
                `spawn=True`. If None, Sidekick uses a default background color.

        Raises:
            ValueError: If `width` or `height` are not positive integers, or if
                        `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established.

        Examples:
            >>> # Create a 300x200 canvas with a light gray background
            >>> canvas = sidekick.Canvas(300, 200, bg_color="#eeeeee")
            >>>
            >>> # Attach to an existing canvas UI element named "drawing-area"
            >>> # Note: We still need dummy width/height for validation here.
            >>> existing_canvas = sidekick.Canvas(width=1, height=1,
            ...                                 instance_id="drawing-area", spawn=False)
        """
        # Validate dimensions first, even if not spawning, to store them locally.
        if not (isinstance(width, int) and width > 0):
            raise ValueError("Canvas width must be a positive integer.")
        if not (isinstance(height, int) and height > 0):
            raise ValueError("Canvas height must be a positive integer.")

        # Prepare the payload for the initial 'spawn' command.
        # Only include details if we are actually creating the canvas (spawn=True).
        spawn_payload: Dict[str, Any] = {}
        if spawn:
             # Keys must be camelCase for the protocol.
             spawn_payload["width"] = width
             spawn_payload["height"] = height
             if bg_color:
                 spawn_payload["bgColor"] = bg_color

        # Call the base class initializer. It handles connection, ID, registration,
        # and sending the spawn command if spawn=True.
        super().__init__(
            module_type="canvas",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None, # Send payload only if spawning.
        )

        # Store dimensions locally for reference (e.g., future validation, though
        # currently not used for bounds checking in drawing commands).
        self.width = width
        self.height = height
        logger.info(f"Canvas '{self.target_id}' initialized (spawn={spawn}, size={width}x{height}).")

    # --- Internal Message Handling ---
    # Inherits _internal_message_handler from BaseModule.
    # Currently, the Canvas UI doesn't send any specific 'event' messages back
    # (like clicks), so we only need the base class's error handling.

    # --- Error Callback ---
    # Inherits on_error(callback) method from BaseModule. Use this to handle
    # potential errors reported by the Canvas UI element.

    def _send_canvas_command(self, action: str, options: Optional[Dict[str, Any]] = None):
        """Internal helper to build and send a Canvas 'update' command.

        This automatically adds the required unique `commandId` to the payload
        before sending the update.

        Args:
            action (str): The specific canvas action (e.g., "line", "rect", "clear", "config").
            options (Optional[Dict[str, Any]]): A dictionary containing the parameters
                for the action (e.g., coordinates, colors). Keys should be `camelCase`.
                Defaults to an empty dictionary if None.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending fails.
        """
        # Ensure options payload is at least an empty dict.
        options_payload = options or {}

        # Construct the full payload required by the protocol for canvas updates.
        update_payload = {
            "action": action,
            "options": options_payload,
            # Get the next sequential ID for this specific drawing command.
            "commandId": connection.get_next_command_id()
        }
        # Use the base class's method to send the 'update' command.
        self._send_update(update_payload)

    # --- Public Canvas Methods ---

    def clear(self, color: Optional[str] = None):
        """Clears the entire canvas, optionally filling it with a background color.

        Removes all previously drawn shapes.

        Args:
            color (Optional[str]): A CSS color string (e.g., 'white', '#ff0000')
                to fill the canvas with after clearing. If None (default), the
                canvas will usually revert to its initial background color or
                become transparent, depending on the Sidekick UI implementation.

        Returns:
            None

        Examples:
            >>> # Clear the canvas (reverts to default background)
            >>> canvas.clear()
            >>>
            >>> # Clear the canvas and make the background blue
            >>> canvas.clear(color="blue")
        """
        options = {}
        # Only include the color option if one was provided.
        if color is not None:
            options["color"] = color
        self._send_canvas_command("clear", options)
        logger.debug(f"Canvas '{self.target_id}': Sent clear command (color={color}).")

    def config(
        self,
        stroke_style: Optional[str] = None,
        fill_style: Optional[str] = None,
        line_width: Optional[int] = None
    ):
        """Configures the drawing styles for *subsequent* shape drawing commands.

        Use this to set the color for outlines (`stroke_style`), the color used
        for filling shapes (`fill_style`), and the thickness of lines (`line_width`).
        Any style parameter you set here will remain active for all future drawing
        calls until you change it again using `config()`.

        Args:
            stroke_style (Optional[str]): The color for drawing lines and shape
                outlines (e.g., 'black', '#00FF00', 'rgba(0,0,255,0.8)'). If None,
                the current stroke style is not changed.
            fill_style (Optional[str]): The color for filling shapes (rectangles,
                circles) when the `filled` parameter is True in drawing commands
                (e.g., 'blue', '#FFFF00'). If None, the current fill style is
                not changed.
            line_width (Optional[int]): The width (thickness) of lines and shape
                outlines in pixels. Must be a positive integer. If None, the
                current line width is not changed.

        Returns:
            None

        Examples:
            >>> # Set drawing color to red, fill to yellow, line width to 3 pixels
            >>> canvas.config(stroke_style="red", fill_style="yellow", line_width=3)
            >>> # Now draw a filled red rectangle (uses the new styles)
            >>> canvas.draw_rect(10, 10, 50, 50, filled=True) # Outline red, fill yellow
            >>>
            >>> # Only change the line width back to 1 (stroke and fill remain)
            >>> canvas.config(line_width=1)
        """
        options = {}
        # Build the options dictionary, only including parameters that were provided.
        # Keys must be camelCase.
        if stroke_style is not None: options["strokeStyle"] = stroke_style
        if fill_style is not None: options["fillStyle"] = fill_style
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                logger.warning(f"Canvas '{self.target_id}': Invalid line_width ({line_width}) in config. Must be positive integer. Ignoring.")

        # Only send the command if there's actually something to configure.
        if options:
            self._send_canvas_command("config", options)
            logger.debug(f"Canvas '{self.target_id}': Sent config command: {options}")
        else:
             logger.debug(f"Canvas '{self.target_id}': config() called with no styles to change.")

    def draw_line(self, x1: int, y1: int, x2: int, y2: int):
        """Draws a straight line segment on the canvas.

        The line is drawn using the current `stroke_style` and `line_width`
        set by the last call to `config()`. The coordinate system origin (0,0)
        is typically the top-left corner of the canvas.

        Args:
            x1 (int): The x-coordinate (horizontal position) of the line's start point.
            y1 (int): The y-coordinate (vertical position) of the line's start point.
            x2 (int): The x-coordinate of the line's end point.
            y2 (int): The y-coordinate of the line's end point.

        Returns:
            None

        Examples:
            >>> # Draw a diagonal line from (10, 10) to (50, 100)
            >>> canvas.draw_line(10, 10, 50, 100)
            >>>
            >>> # Draw a horizontal line
            >>> canvas.draw_line(20, 50, 80, 50)
        """
        # Coordinates must be camelCase in the options payload.
        options = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        self._send_canvas_command("line", options)
        # Consider adding logging here if needed for debugging draws.

    def draw_rect(self, x: int, y: int, width: int, height: int, filled: bool = False):
        """Draws a rectangle on the canvas.

        Args:
            x (int): The x-coordinate of the top-left corner of the rectangle.
            y (int): The y-coordinate of the top-left corner of the rectangle.
            width (int): The width of the rectangle in pixels. Should be non-negative.
            height (int): The height of the rectangle in pixels. Should be non-negative.
            filled (bool): Determines how the rectangle is drawn:
                - If `False` (default): Draws only the outline of the rectangle using
                  the current `stroke_style` and `line_width`.
                - If `True`: Fills the rectangle with the current `fill_style`
                  *and* also draws the outline using the `stroke_style` and `line_width`.

        Returns:
            None

        Examples:
            >>> # Draw the outline of a 50x30 rectangle starting at (20, 20)
            >>> canvas.config(stroke_style='blue')
            >>> canvas.draw_rect(20, 20, 50, 30)
            >>>
            >>> # Draw a filled red rectangle (outline still uses stroke_style)
            >>> canvas.config(fill_style="red")
            >>> canvas.draw_rect(100, 50, 40, 40, filled=True)
        """
        # Log a warning if dimensions are negative, but still send the command
        # as the UI might handle it (e.g., by drawing nothing or using absolute value).
        if width < 0 or height < 0:
             logger.warning(
                 f"Canvas '{self.target_id}': draw_rect called with negative width/height "
                 f"({width}x{height}). Behavior depends on Sidekick UI implementation."
             )
        # Keys must be camelCase.
        options = {"x": x, "y": y, "width": width, "height": height, "filled": filled}
        self._send_canvas_command("rect", options)

    def draw_circle(self, cx: int, cy: int, radius: int, filled: bool = False):
        """Draws a circle on the canvas.

        Args:
            cx (int): The x-coordinate of the center of the circle.
            cy (int): The y-coordinate of the center of the circle.
            radius (int): The radius of the circle in pixels. Must be positive.
            filled (bool): Determines how the circle is drawn:
                - If `False` (default): Draws only the outline (circumference)
                  using the current `stroke_style` and `line_width`.
                - If `True`: Fills the circle with the current `fill_style`
                  *and* also draws the outline using the `stroke_style` and `line_width`.

        Raises:
            ValueError: If `radius` is zero or negative.

        Returns:
            None

        Examples:
            >>> # Draw the outline of a circle with radius 25 centered at (150, 100)
            >>> canvas.config(stroke_style='green', line_width=2)
            >>> canvas.draw_circle(150, 100, 25)
            >>>
            >>> # Draw a filled orange circle
            >>> canvas.config(fill_style="orange")
            >>> canvas.draw_circle(50, 50, 20, filled=True)
        """
        # Radius must be positive for a circle to be drawn.
        if radius <= 0:
             msg = f"Canvas '{self.target_id}': draw_circle radius must be positive, got {radius}."
             logger.error(msg + " Ignoring command.")
             # Raise ValueError to make the error explicit to the user.
             raise ValueError(msg)
        # Keys must be camelCase.
        options = {"cx": cx, "cy": cy, "radius": radius, "filled": filled}
        self._send_canvas_command("circle", options)

    # --- Removal ---
    # Inherits the remove() method from BaseModule to remove the canvas element.
    # No specific callbacks need resetting in _reset_specific_callbacks for Canvas.