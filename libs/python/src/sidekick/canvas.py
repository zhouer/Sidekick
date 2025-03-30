# Sidekick/libs/python/src/sidekick/canvas.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Dict, Any, Tuple

class Canvas(BaseModule):
    """Represents a 2D Canvas module instance in Sidekick for basic drawing."""
    def __init__(self, width: int, height: int, bg_color: Optional[str] = None,
                 instance_id: Optional[str] = None):
        """
        Creates a new Canvas visualization.

        Args:
            width: The width of the canvas in pixels.
            height: The height of the canvas in pixels.
            bg_color: Optional background color (CSS color string, e.g., '#FFFFFF'). Defaults to white.
            instance_id: Optional specific ID for this canvas instance.
        """
        if not (isinstance(width, int) and width > 0 and isinstance(height, int) and height > 0):
            raise ValueError("Canvas width and height must be positive integers.")

        payload: Dict[str, Any] = {"width": width, "height": height}
        if bg_color:
            payload["bgColor"] = bg_color

        # Canvas typically doesn't send notifications back, so on_message is None
        super().__init__("canvas", instance_id, payload, on_message=None)
        self.width = width
        self.height = height
        connection.logger.info(f"Canvas '{self.target_id}' created ({width}x{height}).")

    def clear(self, color: Optional[str] = None):
        """
        Clears the canvas.

        Args:
            color: Optional CSS color string. If provided, clears to this color.
                   Otherwise, clears to the initial background color.
        """
        payload: Dict[str, Any] = {"command": "clear", "options": {}}
        if color:
            payload["options"]["color"] = color
        self._send_command("update", payload)

    def config(self, stroke_style: Optional[str] = None, fill_style: Optional[str] = None, line_width: Optional[int] = None):
        """
        Configures drawing properties (colors, line width) for subsequent commands.
        Omitted properties remain unchanged.

        Args:
            stroke_style: CSS color string for outlines/strokes.
            fill_style: CSS color string for filling shapes.
            line_width: Width of lines/strokes in pixels.
        """
        options = {}
        if stroke_style is not None:
            options["strokeStyle"] = stroke_style
        if fill_style is not None:
            options["fillStyle"] = fill_style
        if line_width is not None:
            options["lineWidth"] = line_width

        if options: # Only send if there's something to configure
            payload = {"command": "config", "options": options}
            self._send_command("update", payload)
        else:
             connection.logger.debug(f"Canvas '{self.target_id}': config() called with no arguments.")

    def draw_line(self, x1: int, y1: int, x2: int, y2: int):
        """Draws a line using the current strokeStyle and lineWidth."""
        options = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        payload = {"command": "line", "options": options}
        self._send_command("update", payload)

    def draw_rect(self, x: int, y: int, width: int, height: int, filled: bool = False):
        """Draws a rectangle using current styles.

        Args:
            x: Top-left corner x-coordinate.
            y: Top-left corner y-coordinate.
            width: Width of the rectangle.
            height: Height of the rectangle.
            filled: If True, fills the rectangle using fillStyle, otherwise strokes it using strokeStyle.
        """
        options = {"x": x, "y": y, "width": width, "height": height, "filled": filled}
        payload = {"command": "rect", "options": options}
        self._send_command("update", payload)

    def draw_circle(self, cx: int, cy: int, radius: int, filled: bool = False):
        """Draws a circle using current styles.

        Args:
            cx: Center x-coordinate.
            cy: Center y-coordinate.
            radius: Radius of the circle.
            filled: If True, fills the circle using fillStyle, otherwise strokes it using strokeStyle.
        """
        if radius <= 0:
             connection.logger.warning(f"Canvas '{self.target_id}': draw_circle radius must be positive.")
             return
        options = {"cx": cx, "cy": cy, "radius": radius, "filled": filled}
        payload = {"command": "circle", "options": options}
        self._send_command("update", payload)
