# Sidekick/libs/python/src/sidekick/canvas.py
from . import connection
from .base_module import BaseModule
from typing import Optional, Dict, Any, Tuple

class Canvas(BaseModule):
    """
    Represents a 2D Canvas module instance in Sidekick for basic drawing operations.

    Allows drawing shapes (lines, rectangles, circles) and configuring drawing styles.
    Each drawing command is sent with a unique ID for reliable processing by the frontend.
    """
    def __init__(self, width: int, height: int, bg_color: Optional[str] = None,
                 instance_id: Optional[str] = None):
        """Creates a new Canvas visualization."""
        if not (isinstance(width, int) and width > 0 and isinstance(height, int) and height > 0):
            raise ValueError("Canvas width and height must be positive integers.")
        payload: Dict[str, Any] = {"width": width, "height": height}
        if bg_color:
            payload["bgColor"] = bg_color
        super().__init__("canvas", instance_id, payload, on_message=None)
        self.width = width
        self.height = height
        connection.logger.info(f"Canvas '{self.target_id}' created ({width}x{height}).")

    def _send_canvas_command(self, action: str, options: Optional[Dict[str, Any]] = None):
        """Internal helper to send a canvas update command with a unique commandId."""
        payload = {
            "action": action, # Use 'action' key
            "options": options or {},
            "commandId": connection.get_next_command_id() # Add unique ID from connection module
        }
        self._send_update(payload)

    def clear(self, color: Optional[str] = None):
        """Clears the entire canvas."""
        options = {}
        if color:
            options["color"] = color
        self._send_canvas_command("clear", options) # Use 'clear' action

    def config(self, stroke_style: Optional[str] = None, fill_style: Optional[str] = None, line_width: Optional[int] = None):
        """Configures drawing properties."""
        options = {}
        if stroke_style is not None: options["strokeStyle"] = stroke_style
        if fill_style is not None: options["fillStyle"] = fill_style
        if line_width is not None: options["lineWidth"] = line_width

        if options:
            self._send_canvas_command("config", options) # Use 'config' action
        else:
             connection.logger.debug(f"Canvas '{self.target_id}': config() called with no arguments to change.")

    def draw_line(self, x1: int, y1: int, x2: int, y2: int):
        """Draws a line segment."""
        options = {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
        self._send_canvas_command("line", options) # Use 'line' action

    def draw_rect(self, x: int, y: int, width: int, height: int, filled: bool = False):
        """Draws a rectangle."""
        if width < 0 or height < 0:
             connection.logger.warning(f"Canvas '{self.target_id}': draw_rect width and height should be non-negative.")
        options = {"x": x, "y": y, "width": width, "height": height, "filled": filled}
        self._send_canvas_command("rect", options) # Use 'rect' action

    def draw_circle(self, cx: int, cy: int, radius: int, filled: bool = False):
        """Draws a circle."""
        if radius <= 0:
             connection.logger.warning(f"Canvas '{self.target_id}': draw_circle radius must be positive.")
             return
        options = {"cx": cx, "cy": cy, "radius": radius, "filled": filled}
        self._send_canvas_command("circle", options) # Use 'circle' action