# Sidekick/libs/python/src/sidekick/canvas.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Dict, Any

class Canvas(BaseModule):
    """
    Represents a 2D Canvas module instance in the Sidekick UI for basic drawing.

    This class allows you to programmatically draw shapes like lines, rectangles,
    and circles onto a canvas displayed in Sidekick. You can also clear the
    canvas and configure drawing styles (stroke color, fill color, line width).

    Each drawing operation (`draw_line`, `draw_rect`, etc.) sends a command with
    a unique ID (`commandId`) to ensure reliable processing and ordering by the
    Sidekick frontend.

    It supports two modes of initialization:
    1. Creating a new canvas instance in Sidekick (`spawn=True`).
    2. Attaching to a pre-existing canvas instance in Sidekick (`spawn=False`).
    """
    def __init__(
        self,
        width: int,
        height: int,
        instance_id: Optional[str] = None,
        spawn: bool = True,
        bg_color: Optional[str] = None
    ):
        """
        Initializes the Canvas object, optionally creating a new canvas in Sidekick.

        Args:
            width: The width of the canvas in pixels. Must be a positive integer.
                   Used for validation and required by Sidekick on spawn.
            height: The height of the canvas in pixels. Must be a positive integer.
                    Used for validation and required by Sidekick on spawn.
            instance_id: A unique identifier for this canvas instance.
                         - If `spawn=True`: Optional. If None, an ID will be generated.
                         - If `spawn=False`: **Required**. Specifies the ID of the existing
                           canvas instance in Sidekick to attach to.
            spawn: If True (default), sends a command to Sidekick to create a new
                   canvas module instance with the specified dimensions and background.
                   If False, assumes a canvas with `instance_id` already exists.
            bg_color: An optional background color string (e.g., 'white', '#f0f0f0')
                      for the canvas. Only used if `spawn=True`. Defaults to white
                      on the Sidekick side if not provided.
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
            payload=spawn_payload if spawn else None, # Pass payload only if spawning
            on_message=None # Canvas typically doesn't send notifications back
        )
        # Store dimensions locally for potential future use or reference.
        self.width = width
        self.height = height
        connection.logger.info(f"Canvas '{self.target_id}' initialized (spawn={spawn}, size={width}x{height}).")

    def _send_canvas_command(self, action: str, options: Optional[Dict[str, Any]] = None):
        """
        Internal helper to construct and send a canvas update command.

        Automatically retrieves the next command ID from the connection module
        and includes it in the payload.

        Args:
            action: The drawing or configuration action (e.g., "line", "config").
            options: A dictionary containing parameters specific to the action.
                     Keys should be camelCase as required by the protocol.
                     If None, an empty options object will be sent.
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
        """
        Clears the entire canvas in Sidekick, optionally filling it with a specific color.

        Args:
            color: Optional color string to fill the cleared canvas. If None,
                   the canvas usually reverts to its initial background color.
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
        """
        Configures the drawing context properties in Sidekick for subsequent drawing commands.

        Any parameter set to None will not be included in the command, leaving the
        corresponding style unchanged in Sidekick.

        Args:
            stroke_style: Color used for drawing lines and outlines (e.g., 'black', '#00FF00').
            fill_style: Color used for filling shapes (e.g., 'blue', '#FFFF00').
            line_width: Width of lines drawn, in pixels.
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
             connection.logger.debug(f"Canvas '{self.target_id}': config() called with no arguments to change.")

    def draw_line(self, x1: int, y1: int, x2: int, y2: int):
        """
        Draws a line segment on the canvas in Sidekick.

        Uses the current `strokeStyle` and `lineWidth` configured via `config()`.

        Args:
            x1: Starting x-coordinate.
            y1: Starting y-coordinate.
            x2: Ending x-coordinate.
            y2: Ending y-coordinate.
        """
        options = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        self._send_canvas_command("line", options)

    def draw_rect(self, x: int, y: int, width: int, height: int, filled: bool = False):
        """
        Draws a rectangle on the canvas in Sidekick.

        Args:
            x: X-coordinate of the top-left corner.
            y: Y-coordinate of the top-left corner.
            width: Width of the rectangle. Should be non-negative.
            height: Height of the rectangle. Should be non-negative.
            filled: If True, fills the rectangle using the current `fillStyle`.
                    If False (default), draws only the outline using the current
                    `strokeStyle` and `lineWidth`.
        """
        if width < 0 or height < 0:
             # Log a warning but allow the command to be sent; Sidekick might handle it.
             connection.logger.warning(
                 f"Canvas '{self.target_id}': draw_rect called with negative width/height "
                 f"({width}x{height}). Behavior depends on Sidekick implementation."
             )
        options = {"x": x, "y": y, "width": width, "height": height, "filled": filled}
        self._send_canvas_command("rect", options)

    def draw_circle(self, cx: int, cy: int, radius: int, filled: bool = False):
        """
        Draws a circle on the canvas in Sidekick.

        Args:
            cx: X-coordinate of the center of the circle.
            cy: Y-coordinate of the center of the circle.
            radius: Radius of the circle. Must be positive.
            filled: If True, fills the circle using the current `fillStyle`.
                    If False (default), draws only the outline using the current
                    `strokeStyle` and `lineWidth`.
        """
        if radius <= 0:
             connection.logger.error(f"Canvas '{self.target_id}': draw_circle radius must be positive. Ignoring command.")
             return # Do not send command with invalid radius
        options = {"cx": cx, "cy": cy, "radius": radius, "filled": filled}
        self._send_canvas_command("circle", options)

    # The remove() method is inherited from BaseModule.
    # Calling canvas_instance.remove() will send a 'remove' command to Sidekick
    # for this canvas instance.