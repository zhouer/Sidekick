"""Provides the Canvas class for creating a 2D drawing surface in Sidekick.

Use the `sidekick.Canvas` class to create a blank rectangular area within the
Sidekick panel where your Python script can draw simple graphics. This allows
you to visually represent geometric concepts, create algorithm visualizations,
build simple game graphics, or even produce basic animations controlled by your code.

The canvas can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization.

Key Features:

*   **Drawing Primitives:** Draw basic shapes like lines (`draw_line`),
    rectangles (`draw_rect`), circles (`draw_circle`), polygons (`draw_polygon`),
    ellipses (`draw_ellipse`), and text (`draw_text`).
*   **Styling:** Control the appearance with options for fill color (`fill_color`),
    line color (`line_color`), line width (`line_width`), and text size/color.
*   **Coordinate System:** The origin (0, 0) is at the **top-left corner**.
    The x-axis increases to the right, and the y-axis increases downwards.
    All units (coordinates, dimensions, radii) are in pixels.
*   **Double Buffering:** Create smooth, flicker-free animations using the
    `canvas.buffer()` context manager. This draws a complete frame off-screen
    before displaying it all at once.
*   **Interactivity:** Make your canvas respond to user clicks using the
    `on_click()` method to register a callback function.

Basic Usage:
    >>> import sidekick
    >>> # Create a 300 pixel wide, 200 pixel tall canvas in the root container
    >>> canvas = sidekick.Canvas(300, 200)
    >>> canvas.draw_line(10, 10, 290, 190, line_color='red')

Usage with a Parent Container:
    >>> import sidekick
    >>> my_layout_row = sidekick.Row()
    >>> # Create a canvas inside the 'my_layout_row'
    >>> canvas_in_row = sidekick.Canvas(150, 100, parent=my_layout_row)
    >>> canvas_in_row.draw_circle(75, 50, 40, fill_color='blue')
"""

import threading
import math # Used in examples, good to keep imported
from typing import Optional, Dict, Any, Callable, List, Tuple, ContextManager, Union # Added Union

from . import logger
from . import connection
from .errors import SidekickConnectionError
from .base_component import BaseComponent

# Type hint for a list of points used in polylines/polygons
PointList = List[Tuple[int, int]]


class _CanvasBufferProxy:
    """Internal helper object used with the `canvas.buffer()` context manager. (Internal).

    Args:
        canvas (Canvas): The parent `Canvas` instance this proxy belongs to.
        buffer_id (int): The unique ID (> 0) of the specific offscreen
            buffer that drawing commands on this proxy should target.
    """
    def __init__(self, canvas: 'Canvas', buffer_id: int):
        self._canvas = canvas
        self._buffer_id = buffer_id
        if not isinstance(buffer_id, int) or buffer_id <= 0:
             raise ValueError("_CanvasBufferProxy requires a positive integer offscreen buffer ID.")

    def clear(self):
        """Clears the content of the specific offscreen buffer associated with this proxy."""
        self._canvas.clear(buffer_id=self._buffer_id)

    def draw_line(self, x1: int, y1: int, x2: int, y2: int,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None):
        """Draws a line on the specific offscreen buffer."""
        self._canvas.draw_line(x1, y1, x2, y2, line_color, line_width,
                               buffer_id=self._buffer_id)

    def draw_rect(self, x: int, y: int, width: int, height: int,
                  fill_color: Optional[str] = None,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None):
        """Draws a rectangle on the specific offscreen buffer."""
        self._canvas.draw_rect(x, y, width, height, fill_color, line_color, line_width,
                              buffer_id=self._buffer_id)

    def draw_circle(self, cx: int, cy: int, radius: int,
                    fill_color: Optional[str] = None,
                    line_color: Optional[str] = None,
                    line_width: Optional[int] = None):
        """Draws a circle on the specific offscreen buffer."""
        self._canvas.draw_circle(cx, cy, radius, fill_color, line_color, line_width,
                                buffer_id=self._buffer_id)

    def draw_polyline(self, points: PointList,
                      line_color: Optional[str] = None,
                      line_width: Optional[int] = None):
        """Draws a series of connected lines (polyline) on the specific offscreen buffer."""
        self._canvas.draw_polyline(points, line_color, line_width,
                                  buffer_id=self._buffer_id)

    def draw_polygon(self, points: PointList,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None):
        """Draws a closed polygon on the specific offscreen buffer."""
        self._canvas.draw_polygon(points, fill_color, line_color, line_width,
                                 buffer_id=self._buffer_id)

    def draw_ellipse(self, cx: int, cy: int, radius_x: int, radius_y: int,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None):
        """Draws an ellipse on the specific offscreen buffer."""
        self._canvas.draw_ellipse(cx, cy, radius_x, radius_y, fill_color, line_color, line_width,
                                buffer_id=self._buffer_id)

    def draw_text(self, x: int, y: int, text: str,
                  text_color: Optional[str] = None,
                  text_size: Optional[int] = None):
        """Draws text on the specific offscreen buffer."""
        self._canvas.draw_text(x, y, text, text_color, text_size,
                              buffer_id=self._buffer_id)


class _CanvasBufferContextManager:
    """Internal context manager returned by `canvas.buffer()` for double buffering. (Internal).

    Args:
        canvas (Canvas): The parent `Canvas` instance this context manager belongs to.
    """
    def __init__(self, canvas: 'Canvas'):
        self._canvas = canvas
        self._buffer_id: Optional[int] = None

    def __enter__(self) -> _CanvasBufferProxy:
        """Prepares and provides an offscreen buffer when entering the `with` block."""
        self._buffer_id = self._canvas._acquire_buffer_id()
        logger.debug(f"Canvas '{self._canvas.target_id}': Entering buffer context, acquired buffer ID {self._buffer_id}.")
        _CanvasBufferProxy(self._canvas, self._buffer_id).clear()
        return _CanvasBufferProxy(self._canvas, self._buffer_id)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finalizes buffer operations when exiting the `with` block."""
        if self._buffer_id is None:
            logger.error(f"Canvas '{self._canvas.target_id}': Exiting buffer context but _buffer_id is None!")
            return False

        try:
            if exc_type is None:
                logger.debug(f"Canvas '{self._canvas.target_id}': Exiting buffer context normally. Drawing buffer {self._buffer_id} to screen.")
                self._canvas._send_draw_buffer(source_buffer_id=self._buffer_id, target_buffer_id=self._canvas.ONSCREEN_BUFFER_ID)
            else:
                logger.warning(
                    f"Canvas '{self._canvas.target_id}': Exiting buffer context due to an exception "
                    f"({exc_type}). Content of buffer {self._buffer_id} NOT drawn."
                )
        except SidekickConnectionError as e:
             logger.error(f"Canvas '{self._canvas.target_id}': Connection error during buffer __exit__: {e}")
        except Exception as e_exit:
             logger.exception(f"Canvas '{self._canvas.target_id}': Unexpected error during buffer __exit__: {e_exit}")

        self._canvas._release_buffer_id(self._buffer_id)
        self._buffer_id = None
        return False # Propagate exceptions


class Canvas(BaseComponent):
    """Represents a 2D drawing canvas component instance in the Sidekick UI.

    Provides a surface within the Sidekick panel for programmatic drawing.
    Can be placed within layout containers like `Row` or `Column`.

    Attributes:
        target_id (str): The unique identifier for this canvas instance.
        width (int): The width of the canvas drawing area in pixels (read-only).
        height (int): The height of the canvas drawing area in pixels (read-only).
    """
    ONSCREEN_BUFFER_ID = 0

    def __init__(
        self,
        width: int,
        height: int,
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes a new Canvas object and creates its UI element in Sidekick.

        Args:
            width (int): The desired width of the canvas in pixels. Must be positive.
            height (int): The desired height of the canvas in pixels. Must be positive.
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, added to the root container.

        Raises:
            ValueError: If `width` or `height` are not positive integers.
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        if not isinstance(width, int) or width <= 0:
            raise ValueError("Canvas width must be a positive integer.")
        if not isinstance(height, int) or height <= 0:
            raise ValueError("Canvas height must be a positive integer.")

        spawn_payload: Dict[str, Any] = {
            "width": width,
            "height": height
        }

        super().__init__(
            component_type="canvas",
            payload=spawn_payload,
            parent=parent  # Pass the parent argument to BaseComponent
        )

        self._width = width
        self._height = height
        self._click_callback: Optional[Callable[[int, int], None]] = None
        self._buffer_pool: Dict[int, bool] = {}
        self._next_buffer_id: int = 1
        self._buffer_lock = threading.Lock()

        logger.info(f"Canvas '{self.target_id}' initialized (size={self.width}x{self.height}).")

    @property
    def width(self) -> int:
        """int: The width of the canvas in pixels (read-only)."""
        return self._width

    @property
    def height(self) -> int:
        """int: The height of the canvas in pixels (read-only)."""
        return self._height

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this canvas. (Internal)."""
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "click" and self._click_callback:
                try:
                    x = payload.get('x')
                    y = payload.get('y')
                    if isinstance(x, int) and isinstance(y, int):
                        self._click_callback(x, y)
                    else:
                         logger.warning(
                            f"Canvas '{self.target_id}' received 'click' event "
                            f"with missing/invalid coordinates: {payload}"
                         )
                except Exception as e:
                    logger.exception(
                        f"Error occurred inside Canvas '{self.target_id}' on_click callback: {e}"
                    )
            else:
                 logger.debug(
                    f"Canvas '{self.target_id}' received unhandled event type '{event_type}' "
                    f"or no click callback registered."
                 )
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[int, int], None]]):
        """Registers a function to be called when the user clicks on the canvas.

        Args:
            callback (Optional[Callable[[int, int], None]]): The function to execute.
                It must accept two integer arguments: `x` (column) and `y` (row)
                of the click. Pass `None` to remove a callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for canvas '{self.target_id}'.")
        self._click_callback = callback

    def buffer(self) -> ContextManager[_CanvasBufferProxy]:
        """Provides a context manager (`with` statement) for efficient double buffering.

        Draw operations within the `with` block target a hidden buffer. Upon exiting
        the block, the hidden buffer's content is drawn to the visible canvas.

        Returns:
            ContextManager[_CanvasBufferProxy]: A context manager yielding a proxy
            for drawing on the hidden buffer.

        Example:
            >>> with canvas.buffer() as frame_buffer:
            ...     frame_buffer.draw_circle(50, 50, 10, fill_color='red')
            ... # Screen updates when 'with' block ends.
        """
        return _CanvasBufferContextManager(self)

    def _acquire_buffer_id(self) -> int:
        """Internal: Gets an available offscreen buffer ID or creates one."""
        with self._buffer_lock:
            for buffer_id, is_in_use in self._buffer_pool.items():
                if not is_in_use:
                    self._buffer_pool[buffer_id] = True
                    logger.debug(f"Canvas '{self.target_id}': Reusing buffer ID {buffer_id}.")
                    return buffer_id

            new_id = self._next_buffer_id
            self._next_buffer_id += 1
            logger.debug(f"Canvas '{self.target_id}': Creating new buffer with ID {new_id}.")
            self._send_canvas_update(
                action="createBuffer",
                options={"bufferId": new_id}
            )
            self._buffer_pool[new_id] = True
            return new_id

    def _release_buffer_id(self, buffer_id: int):
        """Internal: Marks an offscreen buffer ID as no longer in use."""
        with self._buffer_lock:
            if buffer_id in self._buffer_pool:
                self._buffer_pool[buffer_id] = False
                logger.debug(f"Canvas '{self.target_id}': Released buffer ID {buffer_id} back to pool.")
            else:
                logger.warning(
                    f"Canvas '{self.target_id}': Attempted to release buffer ID {buffer_id}, "
                    f"but it was not found in the active pool."
                )

    def _send_draw_buffer(self, source_buffer_id: int, target_buffer_id: int):
        """Internal: Sends command to draw one buffer onto another."""
        self._send_canvas_update(
            action="drawBuffer",
            options={
                "sourceBufferId": source_buffer_id,
                "targetBufferId": target_buffer_id
            }
        )

    def _send_canvas_update(self, action: str, options: Dict[str, Any]):
        """Internal helper to construct and send a Canvas 'update' command."""
        update_payload = {
            "action": action,
            "options": options,
        }
        self._send_update(update_payload)

    def clear(self, buffer_id: Optional[int] = None):
        """Clears the specified canvas buffer (visible screen or an offscreen buffer).

        Args:
            buffer_id (Optional[int]): ID of the buffer to clear. `None` or 0 for
                the visible canvas.

        Raises:
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        logger.debug(f"Canvas '{self.target_id}': Sending 'clear' command for buffer ID {target_buffer_id}.")
        options = {"bufferId": target_buffer_id}
        self._send_canvas_update("clear", options)

    def draw_line(self, x1: int, y1: int, x2: int, y2: int,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a straight line segment between two points.

        Args:
            x1 (int): Start x-coordinate.
            y1 (int): Start y-coordinate.
            x2 (int): End x-coordinate.
            y2 (int): End y-coordinate.
            line_color (Optional[str]): Line color (CSS format). UI default if None.
            line_width (Optional[int]): Line thickness in pixels (positive). UI default if None.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `line_width` is not positive.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2
        }
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a positive integer.")
        self._send_canvas_update("drawLine", options)

    def draw_rect(self, x: int, y: int, width: int, height: int,
                  fill_color: Optional[str] = None,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a rectangle.

        Args:
            x (int): Top-left x-coordinate.
            y (int): Top-left y-coordinate.
            width (int): Rectangle width (non-negative).
            height (int): Rectangle height (non-negative).
            fill_color (Optional[str]): Fill color. Transparent if None.
            line_color (Optional[str]): Outline color. UI default if None.
            line_width (Optional[int]): Outline thickness (non-negative). 0 for no outline.
                                       UI default if None.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `width`/`height` negative, or `line_width` invalid.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        if width < 0: raise ValueError("Rectangle width cannot be negative.")
        if height < 0: raise ValueError("Rectangle height cannot be negative.")

        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x": x, "y": y, "width": width, "height": height
        }
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width >= 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a non-negative integer.")
        self._send_canvas_update("drawRect", options)

    def draw_circle(self, cx: int, cy: int, radius: int,
                    fill_color: Optional[str] = None,
                    line_color: Optional[str] = None,
                    line_width: Optional[int] = None,
                    buffer_id: Optional[int] = None):
        """Draws a circle.

        Args:
            cx (int): Center x-coordinate.
            cy (int): Center y-coordinate.
            radius (int): Circle radius (positive).
            fill_color (Optional[str]): Fill color. Not filled if None.
            line_color (Optional[str]): Outline color. UI default if None.
            line_width (Optional[int]): Outline thickness (non-negative). UI default if None.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `radius` not positive, or `line_width` invalid.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        if not isinstance(radius, (int, float)) or radius <= 0: # allow float for radius internally
            raise ValueError("Circle radius must be a positive number.")
        radius_int = int(radius)

        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "cx": cx, "cy": cy, "radius": radius_int
        }
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width >= 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a non-negative integer.")
        self._send_canvas_update("drawCircle", options)

    def draw_polyline(self, points: PointList,
                      line_color: Optional[str] = None,
                      line_width: Optional[int] = None,
                      buffer_id: Optional[int] = None):
        """Draws a series of connected line segments (an open path).

        Args:
            points (List[Tuple[int, int]]): List of at least two (x,y) vertex tuples.
            line_color (Optional[str]): Color for all segments. UI default if None.
            line_width (Optional[int]): Thickness for all segments (positive). UI default if None.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `points` has < 2 points, or `line_width` invalid.
            TypeError: If `points` format is invalid.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError("draw_polyline requires a list of at least two (x, y) point tuples.")
        try:
            points_payload = [{"x": int(p[0]), "y": int(p[1])} for p in points]
        except (TypeError, IndexError, ValueError) as e:
             raise TypeError(
                "Invalid data format in 'points' list for draw_polyline. "
                f"Expect list of (x, y) tuples/lists with numbers. Error: {e}"
            )

        options: Dict[str, Any] = {"bufferId": target_buffer_id, "points": points_payload}
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a positive integer.")
        self._send_canvas_update("drawPolyline", options)

    def draw_polygon(self, points: PointList,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None,
                     buffer_id: Optional[int] = None):
        """Draws a closed polygon shape.

        Args:
            points (List[Tuple[int, int]]): List of at least three (x,y) vertex tuples.
            fill_color (Optional[str]): Fill color. Not filled if None.
            line_color (Optional[str]): Outline color. UI default if None.
            line_width (Optional[int]): Outline thickness (non-negative). UI default if None.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `points` has < 3 points, or `line_width` invalid.
            TypeError: If `points` format is invalid.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError("draw_polygon requires a list of at least three (x, y) point tuples.")
        try:
            points_payload = [{"x": int(p[0]), "y": int(p[1])} for p in points]
        except (TypeError, IndexError, ValueError) as e:
             raise TypeError(
                "Invalid data format in 'points' list for draw_polygon. "
                f"Expect list of (x, y) tuples/lists with numbers. Error: {e}"
            )

        options: Dict[str, Any] = {"bufferId": target_buffer_id, "points": points_payload}
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width >= 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a non-negative integer.")
        self._send_canvas_update("drawPolygon", options)

    def draw_ellipse(self, cx: int, cy: int, radius_x: int, radius_y: int,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None,
                     buffer_id: Optional[int] = None):
        """Draws an ellipse (or oval) shape.

        Args:
            cx (int): Center x-coordinate.
            cy (int): Center y-coordinate.
            radius_x (int): Horizontal radius (positive).
            radius_y (int): Vertical radius (positive).
            fill_color (Optional[str]): Fill color. Not filled if None.
            line_color (Optional[str]): Outline color. UI default if None.
            line_width (Optional[int]): Outline thickness (non-negative). UI default if None.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If radii not positive, or `line_width` invalid.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        if not isinstance(radius_x, (int, float)) or radius_x <= 0:
            raise ValueError("Ellipse radius_x must be a positive number.")
        if not isinstance(radius_y, (int, float)) or radius_y <= 0:
            raise ValueError("Ellipse radius_y must be a positive number.")
        radius_x_int = int(radius_x)
        radius_y_int = int(radius_y)

        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "cx": cx, "cy": cy,
            "radiusX": radius_x_int,
            "radiusY": radius_y_int
        }
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width >= 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a non-negative integer.")
        self._send_canvas_update("drawEllipse", options)

    def draw_text(self, x: int, y: int, text: str,
                  text_color: Optional[str] = None,
                  text_size: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a string of text.

        The (x,y) coordinates typically define the text's baseline start or top-left.

        Args:
            x (int): X-coordinate for text position.
            y (int): Y-coordinate for text position.
            text (str): The text string to display.
            text_color (Optional[str]): Text color. UI default if None.
            text_size (Optional[int]): Font size in pixels (positive). UI default if None.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `text_size` is not positive.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x": x, "y": y,
            "text": str(text)
        }
        if text_color is not None: options["textColor"] = text_color
        if text_size is not None:
            if isinstance(text_size, int) and text_size > 0:
                options["textSize"] = text_size
            else:
                 raise ValueError("text_size must be a positive integer.")
        self._send_canvas_update("drawText", options)

    def _reset_specific_callbacks(self):
        """Internal: Resets canvas-specific callbacks."""
        super()._reset_specific_callbacks() # Good practice if base had its own
        self._click_callback = None

    def remove(self):
        """Removes the canvas and its offscreen buffers from the Sidekick UI."""
        logger.info(
            f"Requesting removal of canvas '{self.target_id}' and its associated offscreen buffers."
        )
        with self._buffer_lock:
            buffer_ids_to_destroy = [
                bid for bid in self._buffer_pool if bid != self.ONSCREEN_BUFFER_ID
            ]
            for buffer_id in buffer_ids_to_destroy:
                 try:
                     logger.debug(
                        f"Canvas '{self.target_id}': Sending 'destroyBuffer' for buffer ID {buffer_id}."
                     )
                     self._send_canvas_update(
                         action="destroyBuffer",
                         options={"bufferId": buffer_id}
                     )
                 except SidekickConnectionError as e:
                     logger.warning(
                        f"Canvas '{self.target_id}': Failed to destroy offscreen buffer "
                        f"{buffer_id} during removal: {e}"
                     )
                 except Exception as e_destroy:
                     logger.exception(
                        f"Canvas '{self.target_id}': Unexpected error destroying buffer {buffer_id}: {e_destroy}"
                     )
            self._buffer_pool.clear()
            self._next_buffer_id = 1
        super().remove()

    def __del__(self):
        """Internal: Fallback cleanup attempt."""
        try:
            super().__del__()
        except Exception:
            pass