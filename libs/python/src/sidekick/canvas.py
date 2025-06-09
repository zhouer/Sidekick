"""Provides the Canvas class for creating a 2D drawing surface in Sidekick.

Use the `sidekick.Canvas` class to create a blank rectangular area within the
Sidekick panel where your Python script can draw simple graphics. This allows
you to visually represent geometric concepts, create algorithm visualizations,
build simple game graphics, or even produce basic animations controlled by your code.

The canvas can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization, or by adding it as a child
to a container's constructor. You can also provide an `instance_id` to uniquely
identify the canvas.

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
    `on_click()` method or the `on_click` constructor parameter to register a
    callback function that receives a `CanvasClickEvent` object.

Basic Usage:
    >>> import sidekick
    >>> # Create a 300 pixel wide, 200 pixel tall canvas
    >>> canvas = sidekick.Canvas(300, 200, instance_id="main-drawing-area")
    >>> canvas.draw_line(10, 10, 290, 190, line_color='red')

Interactive Usage with a Parent Container:
    >>> import sidekick
    >>> from sidekick.events import CanvasClickEvent # Import the event type
    >>>
    >>> my_layout_row = sidekick.Row()
    >>>
    >>> def canvas_clicked(event: CanvasClickEvent):
    ...     print(f"Canvas '{event.instance_id}' clicked at ({event.x}, {event.y})")
    ...     # Assume canvas_in_row is accessible
    ...     canvas_in_row.draw_circle(event.x, event.y, 5, fill_color='green')
    ...
    >>> canvas_in_row = sidekick.Canvas(
    ...     width=150, height=100,
    ...     parent=my_layout_row,
    ...     instance_id="interactive-canvas",
    ...     on_click=canvas_clicked
    ... )
    >>> canvas_in_row.draw_circle(75, 50, 40, fill_color='blue')
    >>> # sidekick.run_forever() # Keep script running to process clicks
"""

import threading
from typing import Optional, Dict, Any, Callable, List, Tuple, ContextManager, Union, Coroutine

from . import logger
from .component import Component
from .events import CanvasClickEvent, ErrorEvent

# Type hint for a list of points used in polylines/polygons
PointList = List[Tuple[int, int]]


class _CanvasBufferProxy:
    """Internal helper object used with the `canvas.buffer()` context manager. (Internal).

    This object is what you get inside a `with canvas.buffer() as buf:` block.
    All drawing methods called on `buf` (e.g., `buf.draw_line()`) will target
    a hidden, off-screen buffer instead of drawing directly to the visible canvas.

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

    When you use `with canvas.buffer() as buf:`, this object's `__enter__` method
    is called to set up an off-screen buffer, and its `__exit__` method is called
    when the `with` block finishes to draw the off-screen buffer's contents to the
    visible canvas.

    Args:
        canvas (Canvas): The parent `Canvas` instance this context manager belongs to.
    """
    def __init__(self, canvas: 'Canvas'):
        self._canvas = canvas
        self._buffer_id: Optional[int] = None # The ID of the off-screen buffer being used.

    def __enter__(self) -> _CanvasBufferProxy:
        """Prepares and provides an offscreen buffer when entering the `with` block."""
        # Acquire an available buffer ID from the canvas's pool.
        # This might involve creating a new buffer in the UI if none are free.
        self._buffer_id = self._canvas._acquire_buffer_id()
        logger.debug(
            f"Canvas '{self._canvas.instance_id}': Entering buffer context, " # Use instance_id
            f"acquired offscreen buffer ID {self._buffer_id}."
        )
        # Create a proxy object that will direct all its drawing calls
        # to this specific off-screen buffer.
        buffer_proxy = _CanvasBufferProxy(self._canvas, self._buffer_id)
        # It's good practice to clear the off-screen buffer before drawing on it,
        # to ensure no remnants from previous uses are visible.
        buffer_proxy.clear()
        return buffer_proxy

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finalizes buffer operations when exiting the `with` block.

        If no exception occurred within the `with` block, this method sends a command
        to the Sidekick UI to draw the contents of the off-screen buffer (identified
        by `self._buffer_id`) onto the visible canvas (on-screen buffer).
        It then releases the off-screen buffer ID back to the canvas's pool.
        """
        if self._buffer_id is None:
            # This should ideally not happen if __enter__ succeeded.
            logger.error(
                f"Canvas '{self._canvas.instance_id}': Exiting buffer context, " # Use instance_id
                f"but _buffer_id is unexpectedly None! Cannot draw to screen."
            )
            return False # Indicate an issue, but don't suppress outer exceptions.

        try:
            # Only draw the buffer to the screen if the 'with' block completed without errors.
            if exc_type is None:
                logger.debug(
                    f"Canvas '{self._canvas.instance_id}': Exiting buffer context normally. " # Use instance_id
                    f"Drawing buffer {self._buffer_id} to screen (buffer ID {self._canvas.ONSCREEN_BUFFER_ID})."
                )
                self._canvas._send_draw_buffer(
                    source_buffer_id=self._buffer_id,
                    target_buffer_id=self._canvas.ONSCREEN_BUFFER_ID # ONSCREEN_BUFFER_ID is 0
                )
            else:
                # If an exception occurred inside the 'with' block, the off-screen buffer
                # might be in an inconsistent state. It's safer not to draw it.
                logger.warning(
                    f"Canvas '{self._canvas.instance_id}': Exiting buffer context due to an exception " # Use instance_id
                    f"of type '{exc_type.__name__ if exc_type else 'Unknown'}'. "
                    f"Content of offscreen buffer {self._buffer_id} will NOT be drawn to the screen."
                )
        except Exception as e_exit:
             # Catch any other unexpected errors during the drawing process.
             logger.exception(
                f"Canvas '{self._canvas.instance_id}': Unexpected error during " # Use instance_id
                f"buffer __exit__ (drawing to screen): {e_exit}"
            )
             # Let the original exception (if any) propagate.

        # Always release the buffer ID back to the pool, regardless of exceptions.
        self._canvas._release_buffer_id(self._buffer_id)
        self._buffer_id = None # Clear the stored buffer ID.

        # Return False to propagate any exceptions that occurred *within* the 'with' block.
        # If exc_type is None, returning False has no effect.
        return False


class Canvas(Component):
    """Represents a 2D drawing canvas component instance in the Sidekick UI.

    Provides a surface within the Sidekick panel for programmatic drawing of shapes,
    text, and for creating simple animations. The canvas origin (0,0) is at the
    top-left corner. It can be nested within layout containers like `Row` or `Column`.

    Attributes:
        instance_id (str): The unique identifier for this canvas instance.
        width (int): The width of the canvas drawing area in pixels (read-only).
        height (int): The height of the canvas drawing area in pixels (read-only).
    """
    # Special ID representing the main, visible on-screen canvas buffer in the UI.
    ONSCREEN_BUFFER_ID = 0

    def __init__(
        self,
        width: int,
        height: int,
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_click: Optional[Callable[[CanvasClickEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
        on_error: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
    ):
        """Initializes a new Canvas object and creates its UI element in Sidekick.

        This function is called when you create a new Canvas, for example:
        `my_drawing_area = sidekick.Canvas(400, 300, on_click=handle_drawing_click)`

        It sends a message to the Sidekick UI to display a new drawing canvas.

        Args:
            width (int): The desired width of the canvas in pixels.
                Must be a positive integer (e.g., > 0).
            height (int): The desired height of the canvas in pixels.
                Must be a positive integer (e.g., > 0).
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this canvas. If `None`, an ID will be auto-generated. Must be
                unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Row` or `sidekick.Column`) where this canvas
                should be placed. If `None` (the default), the canvas is added
                to the main Sidekick panel area.
            on_click (Optional[Callable[[CanvasClickEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call
                when the user clicks on the canvas. The function should accept one
                `CanvasClickEvent` object as an argument, which contains `instance_id`,
                `type`, `x` (click x-coordinate), and `y` (click y-coordinate).
                The callback can be a regular function or a coroutine function (async def).
                Defaults to `None`.
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call if
                an error related to this specific canvas occurs in the Sidekick UI.
                The function should take one `ErrorEvent` object as an argument.
                The callback can be a regular function or a coroutine function (async def).
                Defaults to `None`.

        Raises:
            ValueError: If `width` or `height` are not positive integers, or if the
                        provided `instance_id` is invalid or a duplicate.
            TypeError: If `parent` is an invalid type, or if `on_click` or
                `on_error` are provided but are not callable functions.
        """
        if not isinstance(width, int) or width <= 0:
            raise ValueError("Canvas width must be a positive integer.")
        if not isinstance(height, int) or height <= 0:
            raise ValueError("Canvas height must be a positive integer.")

        # Prepare payload for the 'spawn' command.
        spawn_payload: Dict[str, Any] = {
            "width": width,
            "height": height
        }

        # Initialize attributes before super() call.
        self._width = width
        self._height = height
        self._click_callback: Optional[Callable[[CanvasClickEvent], Union[None, Coroutine[Any, Any, None]]]] = None
        self._buffer_pool: Dict[int, bool] = {} # Stores {buffer_id: is_in_use}
        self._next_buffer_id: int = 1 # Start offscreen buffer IDs from 1 (0 is onscreen)
        self._buffer_lock = threading.Lock() # Protects access to _buffer_pool and _next_buffer_id

        super().__init__(
            component_type="canvas",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        logger.info(
            f"Canvas '{self.instance_id}' initialized " # Use self.instance_id
            f"(size={self.width}x{self.height})."
        )

        # Register on_click callback if provided in the constructor.
        if on_click is not None:
            self.on_click(on_click)

    @property
    def width(self) -> int:
        """int: The width of the canvas in pixels (read-only).

        Set during initialization and cannot be changed later.
        """
        return self._width

    @property
    def height(self) -> int:
        """int: The height of the canvas in pixels (read-only).

        Set during initialization and cannot be changed later.
        """
        return self._height

    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this canvas. (Internal).

        This method is called by the Sidekick connection manager when an event
        (like a "click") occurs on this canvas in the UI.
        It constructs a `CanvasClickEvent` object and passes it to the registered callback.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            if event_type == "click":
                logger.debug(f"Canvas '{self.instance_id}' received click event.")
                # The UI sends 'x' and 'y' coordinates of the click.
                x_coord = payload.get('x')
                y_coord = payload.get('y')
                # Validate that x and y are integers.
                if isinstance(x_coord, int) and isinstance(y_coord, int):
                    # Construct the CanvasClickEvent object
                    click_event = CanvasClickEvent(
                        instance_id=self.instance_id,
                        type="click",
                        x=x_coord,
                        y=y_coord
                    )
                    self._invoke_callback(self._click_callback, click_event)
                else:
                     # This indicates a protocol mismatch or UI bug.
                     logger.warning(
                        f"Canvas '{self.instance_id}' received 'click' event "
                        f"with missing/invalid coordinates: {payload}"
                     )
                return

        # Call the base handler for potential 'error' messages or other base handling.
        super()._internal_message_handler(message)

    def on_click(self, callback: Optional[Callable[[CanvasClickEvent], Union[None, Coroutine[Any, Any, None]]]]):
        """Registers a function to call when the user clicks on this canvas.

        The provided callback function will be executed in your Python script.
        It will receive a `CanvasClickEvent` object containing the `instance_id` of
        this canvas, the event `type` ("click"), and the `x` and `y` coordinates
        of the click relative to the canvas's top-left corner.

        You can also set this callback directly when creating the canvas using
        the `on_click` parameter in its constructor.

        Args:
            callback (Optional[Callable[[CanvasClickEvent], Union[None, Coroutine[Any, Any, None]]]]): The function to call
                when the canvas is clicked. It must accept one `CanvasClickEvent`
                argument. The callback can be a regular function or a coroutine function (async def).
                Pass `None` to remove a previously registered callback.

        Raises:
            TypeError: If `callback` is not a callable function or `None`.

        Example:
            >>> from sidekick.events import CanvasClickEvent
            >>>
            >>> def report_click(event: CanvasClickEvent):
            ...     print(f"Canvas '{event.instance_id}' clicked at ({event.x}, {event.y}).")
            ...     # my_drawing_area.draw_circle(event.x, event.y, 3, fill_color='red')
            ...
            >>> my_drawing_area = sidekick.Canvas(200, 150, instance_id="click-zone")
            >>> my_drawing_area.on_click(report_click)
            >>> # sidekick.run_forever() # Needed to process clicks
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for canvas '{self.instance_id}'.") # Use self.instance_id
        self._click_callback = callback

    def click(self, func: Callable[[CanvasClickEvent], Union[None, Coroutine[Any, Any, None]]]) -> Callable[[CanvasClickEvent], Union[None, Coroutine[Any, Any, None]]]:
        """Decorator to register a function to call when this canvas is clicked.

        This provides an alternative, more Pythonic way to set the click handler
        if you prefer decorators. The decorated function will receive a
        `CanvasClickEvent` object as its argument.

        Args:
            func (Callable[[CanvasClickEvent], Union[None, Coroutine[Any, Any, None]]]): The function to register as the click handler.
                It should accept one `CanvasClickEvent` argument. The callback can be a regular
                function or a coroutine function (async def).

        Returns:
            Callable[[CanvasClickEvent], Union[None, Coroutine[Any, Any, None]]]: The original function, allowing the decorator to be used directly.

        Raises:
            TypeError: If `func` is not a callable function.

        Example:
            >>> from sidekick.events import CanvasClickEvent
            >>>
            >>> interactive_canvas = sidekick.Canvas(100, 100, instance_id="decorator-canvas")
            >>>
            >>> @interactive_canvas.click
            ... def handle_canvas_interaction(event: CanvasClickEvent):
            ...     print(f"Canvas '{event.instance_id}' clicked at ({event.x}, {event.y}) via decorator!")
            ...     interactive_canvas.draw_rect(event.x - 2, event.y - 2, 4, 4, fill_color='green')
            ...
            >>> # sidekick.run_forever() # Needed to process clicks
        """
        self.on_click(func) # Register the function using the standard method
        return func # Return the original function

    def buffer(self) -> ContextManager[_CanvasBufferProxy]:
        """Provides a context manager (`with` statement) for efficient double buffering.

        When you want to draw multiple shapes or create an animation frame, drawing
        each element directly to the screen can cause flickering. Double buffering
        solves this by first drawing everything to a hidden, off-screen buffer.
        Once all drawing operations for the frame are complete (when the `with`
        block ends), the entire content of the hidden buffer is instantly drawn
        to the visible canvas. This results in smoother graphics and animations.

        Returns:
            ContextManager[_CanvasBufferProxy]: A context manager. When used in a
            `with` statement, it yields a `_CanvasBufferProxy` object. All drawing
            methods called on this proxy object will target the hidden buffer.

        Example:
            >>> # Assume 'my_canvas' is an existing sidekick.Canvas instance
            >>> with my_canvas.buffer() as frame_buffer:
            ...     # These draw calls happen on a hidden buffer
            ...     frame_buffer.clear() # Clear the hidden buffer first
            ...     frame_buffer.draw_circle(50, 50, 10, fill_color='red')
            ...     frame_buffer.draw_rect(100, 30, 20, 40, fill_color='blue')
            ...
            >>> # When the 'with' block exits, the screen updates once with the red circle
            >>> # and blue rectangle, avoiding flicker.
        """
        return _CanvasBufferContextManager(self)

    def _acquire_buffer_id(self) -> int:
        """Internal: Gets an available offscreen buffer ID from the pool or creates a new one.

        This method manages a pool of offscreen buffer IDs. If a free buffer ID
        is available, it's reused. Otherwise, a new ID is generated, and a command
        is sent to the UI to create a corresponding offscreen buffer. This is
        thread-safe.

        Returns:
            int: The ID of an available (and now marked as 'in-use') offscreen buffer.
                 Buffer IDs are always positive integers (>0).
        """
        with self._buffer_lock: # Ensure thread-safe access to the pool
            # Try to find an existing, unused buffer ID in the pool.
            for buffer_id, is_in_use in self._buffer_pool.items():
                if not is_in_use:
                    self._buffer_pool[buffer_id] = True # Mark as in-use
                    logger.debug(
                        f"Canvas '{self.instance_id}': Reusing offscreen buffer ID {buffer_id} from pool."
                    )
                    return buffer_id

            # If no free buffer ID was found, create a new one.
            new_id = self._next_buffer_id
            self._next_buffer_id += 1 # Increment for the next potential new buffer

            logger.debug(
                f"Canvas '{self.instance_id}': Creating new offscreen buffer with ID {new_id} in UI."
            )
            # Send a command to the UI to create this new offscreen buffer.
            self._send_canvas_update(
                action="createBuffer",
                options={"bufferId": new_id}
            )
            self._buffer_pool[new_id] = True # Add to pool and mark as in-use
            return new_id

    def _release_buffer_id(self, buffer_id: int):
        """Internal: Marks an offscreen buffer ID as no longer in use, returning it to the pool.

        Called by `_CanvasBufferContextManager.__exit__` after the buffer's contents
        have been drawn (or if an error occurred). This is thread-safe.

        Args:
            buffer_id (int): The ID of the offscreen buffer to release.
        """
        with self._buffer_lock: # Ensure thread-safe access to the pool
            if buffer_id in self._buffer_pool:
                self._buffer_pool[buffer_id] = False # Mark as available
                logger.debug(
                    f"Canvas '{self.instance_id}': Released offscreen buffer ID {buffer_id} back to pool."
                )
            else:
                # This might happen if remove() was called concurrently or other logic errors.
                logger.warning(
                    f"Canvas '{self.instance_id}': Attempted to release buffer ID {buffer_id}, "
                    f"but it was not found in the active pool. It might have been already destroyed."
                )

    def _send_draw_buffer(self, source_buffer_id: int, target_buffer_id: int):
        """Internal: Sends command to draw one buffer's content onto another buffer in the UI.

        Typically used to draw an offscreen buffer (`source_buffer_id`) onto the
        visible onscreen buffer (`target_buffer_id = ONSCREEN_BUFFER_ID`).

        Args:
            source_buffer_id (int): The ID of the buffer to copy from.
            target_buffer_id (int): The ID of the buffer to draw onto.
        """
        self._send_canvas_update(
            action="drawBuffer",
            options={
                "sourceBufferId": source_buffer_id,
                "targetBufferId": target_buffer_id
            }
        )

    def _send_canvas_update(self, action: str, options: Dict[str, Any]):
        """Internal helper to construct and send a Canvas 'update' command.

        All canvas drawing operations and buffer manipulations use this method
        to send their specific update commands to the UI.

        Args:
            action (str): The specific canvas action (e.g., "drawLine", "createBuffer").
            options (Dict[str, Any]): A dictionary of options for that action.
        """
        update_payload = {
            "action": action,
            "options": options,
        }
        self._send_update(update_payload)

    def clear(self, buffer_id: Optional[int] = None):
        """Clears the specified canvas buffer (visible screen or an offscreen buffer).

        If `buffer_id` is `None` or `0` (which is `Canvas.ONSCREEN_BUFFER_ID`),
        this will clear the main, visible canvas area in the Sidekick UI.
        If a positive `buffer_id` is provided (e.g., from within a
        `canvas.buffer()` context), it clears that specific offscreen buffer.

        Args:
            buffer_id (Optional[int]): The ID of the buffer to clear.
                Defaults to `None`, which means the visible onscreen canvas
                (ID `0`). For offscreen buffers obtained via `canvas.buffer()`,
                the proxy object automatically provides the correct ID.

        Raises:
            SidekickConnectionError: If sending the command to the UI fails.
        """
        # Determine the target buffer ID. If None, use the onscreen buffer ID.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        log_target = "visible canvas" if target_buffer_id == self.ONSCREEN_BUFFER_ID else f"buffer ID {target_buffer_id}"
        logger.debug(f"Canvas '{self.instance_id}': Sending 'clear' command for {log_target}.")

        options = {"bufferId": target_buffer_id}
        self._send_canvas_update("clear", options)

    def draw_line(self, x1: int, y1: int, x2: int, y2: int,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a straight line segment between two points on the canvas.

        Args:
            x1 (int): The x-coordinate of the starting point of the line.
            y1 (int): The y-coordinate of the starting point of the line.
            x2 (int): The x-coordinate of the ending point of the line.
            y2 (int): The y-coordinate of the ending point of the line.
            line_color (Optional[str]): The color of the line, as a CSS color
                string (e.g., 'blue', '#00FF00'). If `None`, the UI's default
                line color will be used.
            line_width (Optional[int]): The thickness of the line in pixels.
                Must be a positive integer if provided. If `None`, the UI's
                default line width will be used.
            buffer_id (Optional[int]): The ID of the buffer to draw on.
                Defaults to `None` (the visible onscreen canvas). When drawing
                inside a `with canvas.buffer() as buf:`, `buf.draw_line(...)`
                automatically targets the correct offscreen buffer.

        Raises:
            ValueError: If `line_width` is provided but is not a positive integer.
            SidekickConnectionError: If sending the command to the UI fails.
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
                 raise ValueError("line_width for draw_line must be a positive integer if provided.")
        self._send_canvas_update("drawLine", options)

    def draw_rect(self, x: int, y: int, width: int, height: int,
                  fill_color: Optional[str] = None,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a rectangle on the canvas.

        The `(x, y)` coordinates specify the top-left corner of the rectangle.

        Args:
            x (int): The x-coordinate of the top-left corner.
            y (int): The y-coordinate of the top-left corner.
            width (int): The width of the rectangle in pixels. Must be non-negative.
            height (int): The height of the rectangle in pixels. Must be non-negative.
            fill_color (Optional[str]): The color to fill the rectangle with (CSS
                format). If `None`, the rectangle will not be filled (transparent fill).
            line_color (Optional[str]): The color of the rectangle's outline (CSS
                format). If `None`, the UI's default outline color is used.
            line_width (Optional[int]): The thickness of the outline in pixels.
                Must be non-negative if provided. A `line_width` of `0` typically
                means no outline. If `None`, the UI's default outline width is used.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `width` or `height` are negative, or if `line_width`
                        is provided but is not a non-negative integer.
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
                 raise ValueError("line_width for draw_rect must be a non-negative integer if provided.")
        self._send_canvas_update("drawRect", options)

    def draw_circle(self, cx: int, cy: int, radius: int,
                    fill_color: Optional[str] = None,
                    line_color: Optional[str] = None,
                    line_width: Optional[int] = None,
                    buffer_id: Optional[int] = None):
        """Draws a circle on the canvas.

        Args:
            cx (int): The x-coordinate of the circle's center.
            cy (int): The y-coordinate of the circle's center.
            radius (int): The radius of the circle in pixels. Must be positive.
            fill_color (Optional[str]): Fill color (CSS format). No fill if `None`.
            line_color (Optional[str]): Outline color (CSS format). UI default if `None`.
            line_width (Optional[int]): Outline thickness (non-negative). UI default if `None`.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `radius` is not positive, or if `line_width` is provided
                        but is not a non-negative integer.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        # The protocol might expect integer radius, but allowing float internally
        # and then converting can be convenient for calculations.
        if not isinstance(radius, (int, float)) or radius <= 0:
            raise ValueError("Circle radius must be a positive number.")
        radius_int = int(radius) # Ensure integer for protocol if needed

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
                 raise ValueError("line_width for draw_circle must be a non-negative integer if provided.")
        self._send_canvas_update("drawCircle", options)

    def draw_polyline(self, points: PointList,
                      line_color: Optional[str] = None,
                      line_width: Optional[int] = None,
                      buffer_id: Optional[int] = None):
        """Draws a series of connected line segments (an open path) on the canvas.

        Args:
            points (List[Tuple[int, int]]): A list of at least two (x,y) tuples
                representing the vertices of the polyline. For example:
                `[(10, 10), (50, 50), (10, 90)]` would draw a V-shape.
            line_color (Optional[str]): Color for all segments (CSS format). UI default if `None`.
            line_width (Optional[int]): Thickness for all segments (positive). UI default if `None`.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `points` has fewer than 2 points, or if `line_width` is
                        provided but is not a positive integer.
            TypeError: If the `points` argument is not a list or if its elements
                       are not valid (x,y) tuples/lists of numbers.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError("draw_polyline requires a list of at least two (x, y) point tuples.")

        # Validate and convert points to the protocol format ({'x': ..., 'y': ...})
        try:
            points_payload = [{"x": int(p[0]), "y": int(p[1])} for p in points]
        except (TypeError, IndexError, ValueError) as e:
             raise TypeError(
                "Invalid data format in 'points' list for draw_polyline. "
                f"Expected a list of (x, y) tuples or lists containing numbers. Original error: {e}"
            ) from e

        options: Dict[str, Any] = {"bufferId": target_buffer_id, "points": points_payload}
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width for draw_polyline must be a positive integer if provided.")
        self._send_canvas_update("drawPolyline", options)

    def draw_polygon(self, points: PointList,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None,
                     buffer_id: Optional[int] = None):
        """Draws a closed polygon shape on the canvas.

        The last point in the `points` list will be automatically connected back
        to the first point to close the shape.

        Args:
            points (List[Tuple[int, int]]): A list of at least three (x,y) tuples
                representing the vertices of the polygon.
            fill_color (Optional[str]): Fill color (CSS format). No fill if `None`.
            line_color (Optional[str]): Outline color (CSS format). UI default if `None`.
            line_width (Optional[int]): Outline thickness (non-negative). UI default if `None`.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `points` has fewer than 3 points, or if `line_width` is
                        provided but is not a non-negative integer.
            TypeError: If the `points` argument is not a list or if its elements
                       are not valid (x,y) tuples/lists of numbers.
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
                f"Expected a list of (x, y) tuples or lists containing numbers. Original error: {e}"
            ) from e

        options: Dict[str, Any] = {"bufferId": target_buffer_id, "points": points_payload}
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width >= 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width for draw_polygon must be a non-negative integer if provided.")
        self._send_canvas_update("drawPolygon", options)

    def draw_ellipse(self, cx: int, cy: int, radius_x: int, radius_y: int,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None,
                     buffer_id: Optional[int] = None):
        """Draws an ellipse (or oval) shape on the canvas.

        Args:
            cx (int): The x-coordinate of the ellipse's center.
            cy (int): The y-coordinate of the ellipse's center.
            radius_x (int): The horizontal radius of the ellipse in pixels. Must be positive.
            radius_y (int): The vertical radius of the ellipse in pixels. Must be positive.
            fill_color (Optional[str]): Fill color (CSS format). No fill if `None`.
            line_color (Optional[str]): Outline color (CSS format). UI default if `None`.
            line_width (Optional[int]): Outline thickness (non-negative). UI default if `None`.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `radius_x` or `radius_y` are not positive, or if `line_width`
                        is provided but is not a non-negative integer.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        if not isinstance(radius_x, (int, float)) or radius_x <= 0: # Allow float for calc, convert for protocol
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
                 raise ValueError("line_width for draw_ellipse must be a non-negative integer if provided.")
        self._send_canvas_update("drawEllipse", options)

    def draw_text(self, x: int, y: int, text: str,
                  text_color: Optional[str] = None,
                  text_size: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a string of text on the canvas.

        The `(x,y)` coordinates typically define the starting point of the text's
        baseline (for many fonts) or the top-left corner. The exact interpretation
        can depend on the UI's rendering implementation.

        Args:
            x (int): The x-coordinate for the text's position.
            y (int): The y-coordinate for the text's position.
            text (str): The text string to display.
            text_color (Optional[str]): The color of the text (CSS format).
                UI default if `None`.
            text_size (Optional[int]): The font size in pixels. Must be positive
                if provided. UI default if `None`.
            buffer_id (Optional[int]): Target buffer ID. Defaults to visible canvas.

        Raises:
            ValueError: If `text_size` is provided but is not a positive integer.
            SidekickConnectionError: If sending command fails.
        """
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x": x, "y": y,
            "text": str(text) # Ensure text is a string
        }
        if text_color is not None: options["textColor"] = text_color
        if text_size is not None:
            if isinstance(text_size, int) and text_size > 0:
                options["textSize"] = text_size
            else:
                 raise ValueError("text_size for draw_text must be a positive integer if provided.")
        self._send_canvas_update("drawText", options)

    def _reset_specific_callbacks(self):
        """Internal: Resets canvas-specific callbacks when the component is removed."""
        super()._reset_specific_callbacks()
        self._click_callback = None
        logger.debug(f"Canvas '{self.instance_id}': Click callback reset.")

    def remove(self):
        """Removes the canvas and its associated offscreen buffers from the Sidekick UI.

        This method cleans up not only the visible canvas but also any offscreen
        buffers that were created for double buffering via `canvas.buffer()`.
        It's important to call this when you're done with a canvas to free up
        resources in the Sidekick UI.
        """
        logger.info(
            f"Requesting removal of canvas '{self.instance_id}' and its associated offscreen buffers."
        )
        # Lock the buffer pool while we iterate and send destroy commands.
        with self._buffer_lock:
            # Get a list of all offscreen buffer IDs currently in the pool.
            # We iterate over a copy of the keys because we might modify the pool.
            buffer_ids_to_destroy = [
                bid for bid in self._buffer_pool.keys() if bid != self.ONSCREEN_BUFFER_ID
            ]
            # Send a 'destroyBuffer' command for each offscreen buffer.
            for buffer_id_to_remove in buffer_ids_to_destroy:
                 try:
                     logger.debug(
                        f"Canvas '{self.instance_id}': Sending 'destroyBuffer' for offscreen "
                        f"buffer ID {buffer_id_to_remove} during canvas removal."
                     )
                     self._send_canvas_update(
                         action="destroyBuffer",
                         options={"bufferId": buffer_id_to_remove}
                     )
                 except Exception as e_destroy:
                     logger.exception(
                        f"Canvas '{self.instance_id}': Unexpected error destroying offscreen "
                        f"buffer {buffer_id_to_remove} during canvas removal: {e_destroy}"
                     )
            # Clear the local buffer pool and reset the ID counter.
            self._buffer_pool.clear()
            self._next_buffer_id = 1 # Reset for potential future canvas (though this one is being removed)

        # Call the base class's remove() method to handle the removal of the main canvas component.
        super().remove()
