"""Provides the Canvas class for creating a 2D drawing surface in Sidekick.

Use the `sidekick.Canvas` class to create a blank rectangular area within the
Sidekick panel where your Python script can draw simple graphics. This allows
you to visually represent geometric concepts, create algorithm visualizations,
build simple game graphics, or even produce basic animations controlled by your code.

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
    >>> # Create a 300 pixel wide, 200 pixel tall canvas
    >>> canvas = sidekick.Canvas(300, 200)
    >>>
    >>> # Draw a red diagonal line across the canvas
    >>> canvas.draw_line(10, 10, 290, 190, line_color='red')
    >>>
    >>> # Draw a blue filled rectangle with a thick border
    >>> canvas.draw_rect(50, 50, 100, 80, fill_color='blue', line_width=3)
    >>>
    >>> # Draw some text
    >>> canvas.draw_text(150, 120, "Hello Canvas!", text_color='white', text_size=16)

Animation Example (using double buffering):
    >>> import sidekick, time, math
    >>> canvas = sidekick.Canvas(200, 150)
    >>> angle = 0
    >>> for _ in range(60): # Animate briefly
    ...     # --- Draw onto a hidden buffer ---
    ...     with canvas.buffer() as buf: # 'buf' lets you draw on the hidden buffer
    ...         x = 100 + 80 * math.cos(angle)
    ...         y = 75 + 50 * math.sin(angle)
    ...         buf.draw_circle(int(x), int(y), 10, fill_color='orange')
    ...         buf.draw_text(10, 10, f"Angle: {angle:.1f}")
    ...     # --- Display the hidden buffer ---
    ...     # When the 'with' block ends, the hidden buffer's content is shown.
    ...     angle += 0.1
    ...     time.sleep(0.05)
    ...
    >>> print("Animation finished.")
    >>> # Use sidekick.run_forever() if you also need click handling.
"""

import threading
import math # Used in examples, good to keep imported
from typing import Optional, Dict, Any, Callable, List, Tuple, ContextManager, Union

from . import logger
from . import connection # For connection errors
from .base_module import BaseModule

# Type hint for a list of points used in polylines/polygons
# Represents a sequence of (x, y) integer coordinates.
# Example: [(10, 20), (50, 60), (30, 40)]
PointList = List[Tuple[int, int]]

# ==============================================================================
# == Internal: Canvas Buffer Proxy Class ==
# ==============================================================================

class _CanvasBufferProxy:
    """Internal helper object used with the `canvas.buffer()` context manager. (Internal).

    This proxy object is yielded by the `canvas.buffer()` context manager's
    `__enter__` method. It mimics the drawing methods of the main `Canvas` class
    (like `draw_line`, `draw_rect`). However, when you call a drawing method on
    this proxy (e.g., `buf.draw_circle(...)`), it automatically directs the drawing
    command to a specific hidden (offscreen) drawing buffer instead of the main
    visible canvas. This is the core mechanism enabling double buffering.

    Note:
        This is an internal implementation detail of the double buffering feature.
        Users should interact with it via the `canvas.buffer()` context manager,
        not by creating instances of this class directly.

    Args:
        canvas (Canvas): The parent `Canvas` instance this proxy belongs to.
        buffer_id (int): The unique ID (greater than 0) of the specific offscreen
            buffer that drawing commands on this proxy should target.
    """
    def __init__(self, canvas: 'Canvas', buffer_id: int):
        self._canvas = canvas
        self._buffer_id = buffer_id
        # Internal sanity check for buffer ID validity.
        if not isinstance(buffer_id, int) or buffer_id <= 0:
             raise ValueError("_CanvasBufferProxy requires a positive integer offscreen buffer ID.")

    # --- Mirrored Drawing Methods ---
    # Each method below forwards the call to the corresponding public method
    # on the parent `Canvas` instance, but explicitly sets the `buffer_id`
    # argument to the specific offscreen buffer ID managed by this proxy.

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

# ==============================================================================
# == Internal: Canvas Buffer Context Manager Class ==
# ==============================================================================

class _CanvasBufferContextManager:
    """Internal context manager returned by `canvas.buffer()` for double buffering. (Internal).

    This class encapsulates the logic required to manage an offscreen buffer's
    lifecycle for use within a `with` statement. It handles acquiring a buffer ID
    from the canvas's pool, preparing the buffer (clearing it), yielding the proxy
    object for drawing, and then performing the necessary actions upon exiting the
    block (drawing the completed buffer to the visible screen and releasing the
    buffer ID back to the pool).

    Note:
        This is an internal implementation detail. Users should interact with it
        via the public `canvas.buffer()` method and a `with` statement.

    Args:
        canvas (Canvas): The parent `Canvas` instance this context manager belongs to.
    """
    def __init__(self, canvas: 'Canvas'):
        self._canvas = canvas
        # Stores the ID (> 0) of the offscreen buffer acquired in __enter__. Initialized to None.
        self._buffer_id: Optional[int] = None

    def __enter__(self) -> _CanvasBufferProxy:
        """Prepares and provides an offscreen buffer when entering the `with` block.

        Steps:
        1. Acquires an available offscreen buffer ID from the parent canvas's
           internal pool (`_acquire_buffer_id`). This might involve sending a
           'createBuffer' command to the UI if no reusable buffers are available.
        2. Sends a command to the Sidekick UI to clear this newly acquired/reused
           offscreen buffer, ensuring it starts as a blank slate for the new frame.
        3. Creates and returns a `_CanvasBufferProxy` instance that is specifically
           configured to target this acquired offscreen buffer ID.

        Returns:
            _CanvasBufferProxy: An object (`buf` in `with canvas.buffer() as buf:`)
                that provides drawing methods operating on the hidden offscreen buffer.
        """
        # Get an available offscreen buffer ID (creates one in UI if needed).
        self._buffer_id = self._canvas._acquire_buffer_id() # Raises on connection error
        logger.debug(f"Canvas '{self._canvas.target_id}': Entering buffer context, acquired buffer ID {self._buffer_id}.")

        # Immediately clear the acquired offscreen buffer before the user draws on it.
        # This uses the proxy's clear method which targets the correct buffer.
        _CanvasBufferProxy(self._canvas, self._buffer_id).clear() # Raises on connection error

        # Return the proxy object that allows drawing onto this specific buffer.
        return _CanvasBufferProxy(self._canvas, self._buffer_id)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finalizes buffer operations when exiting the `with` block.

        Performs the crucial steps to display the drawn content and clean up:
        1. Checks if an exception occurred within the `with` block.
        2. **If no exception occurred:** Sends a command to draw the entire content
           of the completed hidden offscreen buffer onto the visible canvas. This is
           the "flip" or "blit" step that makes the new frame visible at once.
        3. **Always (whether an exception occurred or not):** Releases the offscreen
           buffer ID back to the parent canvas's internal pool (`_release_buffer_id`),
           making it available for reuse in subsequent `with canvas.buffer():` blocks.
        4. Returns `False` to ensure that any exception raised within the `with`
           block is *not* suppressed and propagates outward normally.

        Args:
            exc_type: The type of the exception raised within the `with` block,
                or `None` if no exception occurred.
            exc_val: The exception instance itself, or `None`.
            exc_tb: The traceback object associated with the exception, or `None`.

        Returns:
            bool: Always returns `False` to allow exceptions to propagate.
        """
        # Ensure we actually acquired a buffer ID in __enter__; otherwise, something went wrong.
        if self._buffer_id is None:
            logger.error(f"Canvas '{self._canvas.target_id}': Exiting buffer context but _buffer_id is None! Cannot draw or release buffer.")
            return False # Don't suppress potential exceptions if state is inconsistent.

        try:
            # Only perform the drawing operations if the 'with' block completed without errors.
            if exc_type is None:
                logger.debug(f"Canvas '{self._canvas.target_id}': Exiting buffer context normally. Drawing buffer {self._buffer_id} to screen.")
                # Draw the completed offscreen buffer onto the onscreen canvas.
                self._canvas._send_draw_buffer(source_buffer_id=self._buffer_id, target_buffer_id=self._canvas.ONSCREEN_BUFFER_ID)
            else:
                # If an error occurred inside the 'with' block, log it. Critically, DO NOT
                # draw the buffer to the screen, as it might contain an incomplete or
                # incorrect frame due to the error.
                logger.warning(f"Canvas '{self._canvas.target_id}': Exiting buffer context due to an exception ({exc_type}). The content of buffer {self._buffer_id} will NOT be drawn to the screen.")
        except connection.SidekickConnectionError as e:
             # Log connection errors during the exit draw/clear operations but proceed to release buffer.
             logger.error(f"Canvas '{self._canvas.target_id}': Connection error during buffer __exit__: {e}")
        except Exception as e_exit:
             # Catch any other unexpected errors during exit operations.
             logger.exception(f"Canvas '{self._canvas.target_id}': Unexpected error during buffer __exit__: {e_exit}")

        # CRITICAL: Always release the buffer ID back to the pool, regardless of
        # whether an error occurred inside the 'with' block or during the exit drawing.
        # This prevents buffer leaks.
        self._canvas._release_buffer_id(self._buffer_id)
        # Reset the stored ID for safety, ensuring it's not accidentally reused.
        self._buffer_id = None

        # Return False ensures that any exception raised *within* the 'with' block
        # is not suppressed by the context manager and will continue to propagate outwards.
        return False

# ==============================================================================
# == Main Canvas Class ==
# ==============================================================================

class Canvas(BaseModule):
    """Represents a 2D drawing canvas module instance in the Sidekick UI.

    Provides a surface within the Sidekick panel where your Python script can
    programmatically draw shapes, lines, and text. It's useful for visualizing
    algorithms, creating simple graphics or simulations, basic game displays,
    or educational demonstrations.

    Drawing commands (like `draw_line()`, `draw_rect()`) are sent immediately
    to the Sidekick UI to update the visual representation. By default, these
    draw directly onto the visible canvas area.

    For creating animations or complex scenes smoothly without flickering, use the
    `buffer()` method within a `with` statement. This enables "double buffering",
    where drawing happens on a hidden surface first, and the result is displayed
    all at once (see module docstring or `buffer()` method documentation for examples).

    You can also make the canvas interactive by responding to user clicks via the
    `on_click()` method.

    Attributes:
        target_id (str): The unique identifier for this canvas instance, used for
            communication with the Sidekick UI. Generated automatically if not
            provided during initialization.
        width (int): The width of the canvas drawing area in pixels, set during
            initialization. This value is read-only after creation.
        height (int): The height of the canvas drawing area in pixels, set during
            initialization. This value is read-only after creation.
    """
    # Class constant representing the ID of the main, visible (onscreen) buffer.
    # Drawing commands target this buffer by default if `buffer_id` is None or 0.
    ONSCREEN_BUFFER_ID = 0

    def __init__(
        self,
        width: int,
        height: int,
        instance_id: Optional[str] = None,
        spawn: bool = True,
    ):
        """Initializes a new Canvas object and optionally creates its UI element in Sidekick.

        Sets up the dimensions and prepares the canvas for drawing commands. The
        connection to Sidekick is established automatically during this initialization
        if it hasn't been already (this might block).

        Args:
            width (int): The desired width of the canvas drawing area in pixels.
                Must be a positive integer.
            height (int): The desired height of the canvas drawing area in pixels.
                Must be a positive integer.
            instance_id (Optional[str]): A specific ID to assign to this canvas instance.
                - If `spawn=True` (default): If provided, this ID will be used. Useful
                  for deterministic identification. If `None`, a unique ID (e.g.,
                  "canvas-1") will be generated automatically.
                - If `spawn=False`: This ID is **required** and must match the ID
                  of an existing canvas element already present in the Sidekick UI
                  that this Python object should connect to and control.
            spawn (bool): If `True` (the default), a command is sent to Sidekick
                (after connection) to create a new canvas UI element with the specified
                `width` and `height`. If `False`, the library assumes a canvas element
                with the given `instance_id` already exists in the UI, and this Python
                object will simply attach to it for sending drawing commands or receiving
                events. When `spawn=False`, the `width` and `height` arguments are
                still validated locally but are not sent in the (empty) spawn command.

        Raises:
            ValueError: If `width` or `height` are not positive integers, or if
                `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to the
                Sidekick UI cannot be established or fails during initialization.

        Examples:
            >>> # Create a new 300x200 canvas in Sidekick
            >>> main_canvas = sidekick.Canvas(300, 200)
            >>>
            >>> # Create another canvas with a specific ID
            >>> mini_map = sidekick.Canvas(100, 100, instance_id="ui-mini-map")
            >>>
            >>> # Assume a canvas with ID "debug-overlay" already exists in Sidekick.
            >>> # Attach a Python object to control it (local dimensions needed for validation).
            >>> overlay_control = sidekick.Canvas(100, 50, instance_id="debug-overlay", spawn=False)
        """
        # --- Validate Dimensions ---
        if not isinstance(width, int) or width <= 0:
            raise ValueError("Canvas width must be a positive integer.")
        if not isinstance(height, int) or height <= 0:
            raise ValueError("Canvas height must be a positive integer.")

        # --- Prepare Spawn Payload ---
        # The payload is only needed if we are creating (spawning) a new canvas.
        spawn_payload: Dict[str, Any] = {}
        if spawn:
            # Keys must be camelCase to match the communication protocol specification.
            spawn_payload["width"] = width
            spawn_payload["height"] = height

        # --- Initialize Base Class ---
        # This handles:
        # - Establishing the connection (blocking if needed, raises on error).
        # - Generating or assigning the target_id.
        # - Registering internal message handlers with the connection module.
        # - Sending the 'spawn' command with the payload if spawn=True.
        super().__init__(
            module_type="canvas",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None, # Send payload only if spawning
        )

        # --- Store Dimensions Locally ---
        # Store dimensions for potential use (e.g., validation, information),
        # though drawing commands rely on the UI having the correct size.
        # Make them pseudo-read-only by convention (no public setter).
        self._width = width
        self._height = height

        # --- Initialize Callback and Buffer State ---
        # Placeholder for the user's click callback function.
        self._click_callback: Optional[Callable[[int, int], None]] = None
        # Internal state for managing offscreen buffers used by canvas.buffer().
        # Key: integer buffer ID (> 0). Value: boolean indicating if currently in use.
        self._buffer_pool: Dict[int, bool] = {}
        # Counter to generate unique IDs (starting > 0) for new offscreen buffers.
        self._next_buffer_id: int = 1
        # Lock to protect access to the buffer pool from potential race conditions
        # (though typical Sidekick drawing is single-threaded).
        self._buffer_lock = threading.Lock()

        logger.info(f"Canvas '{self.target_id}' initialized (spawn={spawn}, size={self.width}x{self.height}).")

    # --- Read-only Properties for Dimensions ---
    @property
    def width(self) -> int:
        """int: The width of the canvas in pixels (read-only)."""
        return self._width

    @property
    def height(self) -> int:
        """int: The height of the canvas in pixels (read-only)."""
        return self._height


    # --- Internal Message Handling ---
    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming 'event' or 'error' messages for this canvas. (Internal).

        Overrides the base class method to specifically process 'click' events
        originating from the canvas UI element. If a click event arrives, it
        extracts the (x, y) coordinates from the message payload and, if an
        `on_click` callback function has been registered by the user, calls that
        function with the coordinates.

        It delegates to the base class's handler (`super()._internal_message_handler`)
        at the end to ensure standard 'error' message processing still occurs.

        Args:
            message (Dict[str, Any]): The raw message dictionary received from
                the connection manager. Expected keys include 'type', 'src' (matching
                this instance's target_id), and 'payload'. Payload keys are expected
                to be camelCase.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        # Handle 'event' messages specifically
        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            # Check if it's a 'click' event AND if the user has registered a handler.
            if event_type == "click" and self._click_callback:
                try:
                    # Safely extract integer coordinates from the payload.
                    x = payload.get('x')
                    y = payload.get('y')
                    if isinstance(x, int) and isinstance(y, int):
                        # Coordinates are valid, call the user's registered callback!
                        self._click_callback(x, y)
                    else:
                         # Log a warning if coordinates are missing or not integers.
                         logger.warning(f"Canvas '{self.target_id}' received 'click' event with missing/invalid coordinates: {payload}")
                except Exception as e:
                    # IMPORTANT: Catch errors *within* the user's callback function
                    # to prevent crashing the library's background listener thread.
                    logger.exception(f"Error occurred inside Canvas '{self.target_id}' on_click callback: {e}")
            else:
                 # Log other unhandled event types or if no callback was registered.
                 logger.debug(f"Canvas '{self.target_id}' received unhandled event type '{event_type}' or no click callback registered.")

        # ALWAYS call the base class handler. This is crucial for processing
        # 'error' messages sent from the UI related to this specific canvas instance.
        super()._internal_message_handler(message)

    # --- Callback Registration ---
    def on_click(self, callback: Optional[Callable[[int, int], None]]):
        """Registers a function to be called when the user clicks on the canvas.

        When the user clicks anywhere on this canvas's visible area in the
        Sidekick UI panel, the function you provide (`callback`) will be
        executed within your running Python script.

        Note:
            Click events are only triggered by interactions with the main, visible
            (onscreen) canvas (buffer ID 0). Clicks are not detected on hidden
            offscreen buffers used with `canvas.buffer()`.

        Args:
            callback (Optional[Callable[[int, int], None]]): The function to execute
                when a click occurs. This function must accept two integer arguments:
                `x` (the horizontal pixel coordinate of the click relative to the
                canvas's left edge, starting at 0) and `y` (the vertical pixel
                coordinate relative to the canvas's top edge, starting at 0).
                To remove a previously registered callback, pass `None`.

        Raises:
            TypeError: If the provided `callback` is not a callable function (or `None`).

        Example:
            >>> def draw_dot_on_click(x, y):
            ...     print(f"Canvas clicked at ({x}, {y}). Drawing a small circle there.")
            ...     # Draw a small green circle at the click location
            ...     canvas.draw_circle(x, y, 5, fill_color='green')
            ...
            >>> canvas = sidekick.Canvas(250, 250)
            >>> canvas.on_click(draw_dot_on_click)
            >>> print("Canvas created. Click on the canvas in the Sidekick panel!")
            >>> # Keep the script running to listen for click events
            >>> sidekick.run_forever()
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for canvas '{self.target_id}'.")
        self._click_callback = callback

    # --- Error Callback ---
    # The `on_error(callback)` method is inherited directly from `BaseModule`.
    # Use `canvas.on_error(my_error_handler)` to register a function that
    # receives error messages if the Sidekick UI encounters a problem specifically
    # related to processing a command for *this* canvas instance (e.g., trying
    # to draw with invalid parameters that were missed by local checks, or drawing
    # onto a non-existent buffer).

    # --- Buffer Management Methods ---
    def buffer(self) -> ContextManager[_CanvasBufferProxy]:
        """Provides a context manager (`with` statement) for efficient double buffering.

        Using this method enables double buffering, the standard technique for
        creating smooth, flicker-free animations or complex drawing sequences.
        Instead of drawing directly to the visible screen (which can cause tearing
        or flickering as elements are drawn one by one), you draw everything for
        the next frame onto a hidden (offscreen) buffer. When you're finished
        drawing the frame, the entire content of the hidden buffer is copied to
        the visible screen in one go.

        How it works in practice:

        1.  **Enter `with` block:** `with canvas.buffer() as buf:`
            *   An offscreen buffer is acquired (or created/reused).
            *   This buffer is automatically cleared.
            *   The variable `buf` becomes a proxy object that mirrors the canvas's
                drawing methods (e.g., `buf.draw_line()`).
        2.  **Inside `with` block:**
            *   All drawing commands called on `buf` (e.g., `buf.draw_circle(...)`)
                are sent to the *hidden* offscreen buffer. The visible screen remains
                unchanged during this time.
        3.  **Exit `with` block:**
            *   The visible canvas is automatically cleared.
            *   The *entire* content of the hidden buffer is drawn ("blitted") onto
                the visible canvas in a single, fast operation.
            *   The hidden buffer is released back into an internal pool so it can
                be reused efficiently next time you enter a `buffer()` context.

        Returns:
            ContextManager[_CanvasBufferProxy]: An object designed to be used in a
            `with` statement. The object yielded by the `with` statement (`buf` in
            the example) provides the drawing methods that target the hidden buffer.

        Example (Simple Animation):
            >>> import sidekick, time, math
            >>> canvas = sidekick.Canvas(150, 100)
            >>> x_pos = 10
            >>> for frame in range(50):
            ...     with canvas.buffer() as frame_buffer: # Get the hidden buffer proxy
            ...         # Draw background (optional, buffer starts clear)
            ...         # frame_buffer.draw_rect(0, 0, canvas.width, canvas.height, fill_color='lightblue')
            ...         # Draw moving element on the hidden buffer
            ...         frame_buffer.draw_circle(x_pos, 50, 10, fill_color='red')
            ...         frame_buffer.draw_text(5, 15, f"Frame: {frame}")
            ...     # --- Screen automatically updates here when 'with' block ends ---
            ...     x_pos += 2 # Move for next frame
            ...     time.sleep(0.03) # Control animation speed
            >>> print("Animation finished.")
        """
        # Returns an instance of the internal context manager class.
        return _CanvasBufferContextManager(self)

    def _acquire_buffer_id(self) -> int:
        """Internal: Gets an available offscreen buffer ID from the pool or creates one.

        Checks the internal `_buffer_pool` for an existing buffer ID that is not
        currently in use. If none is found, it generates a new unique ID (starting > 0),
        sends a 'createBuffer' command to the Sidekick UI to instantiate the
        corresponding offscreen canvas element, adds the new ID to the pool, marks
        it as in use, and returns it.

        Note: This assumes the caller handles potential connection errors raised
        when sending the 'createBuffer' command.

        Returns:
            int: The ID (> 0) of an available offscreen buffer, marked as 'in use'.

        Raises:
            SidekickConnectionError (or subclass): If sending the 'createBuffer'
                command fails when creating a new buffer.
        """
        # Use a lock to ensure thread-safe access/modification of the shared buffer pool.
        with self._buffer_lock:
            # Check if an existing, currently unused buffer is available in the pool.
            for buffer_id, is_in_use in self._buffer_pool.items():
                if not is_in_use:
                    self._buffer_pool[buffer_id] = True # Mark as now in use
                    logger.debug(f"Canvas '{self.target_id}': Reusing buffer ID {buffer_id}.")
                    return buffer_id # Return the existing ID

            # No unused buffer found, need to create a new one.
            # Get the next available ID from the internal counter.
            new_id = self._next_buffer_id
            self._next_buffer_id += 1 # Increment counter for the future.
            logger.debug(f"Canvas '{self.target_id}': No reusable buffer found. Creating new buffer with ID {new_id}.")

            # Send the 'createBuffer' command to the Sidekick UI.
            # Payload requires 'bufferId' key (camelCase) in options.
            # This call might raise SidekickConnectionError if sending fails.
            self._send_canvas_update(
                action="createBuffer",
                options={"bufferId": new_id}
            )

            # Add the new buffer ID to our pool and mark it as currently in use.
            self._buffer_pool[new_id] = True
            return new_id # Return the newly created ID

    def _release_buffer_id(self, buffer_id: int):
        """Internal: Marks an offscreen buffer ID as no longer in use in the pool.

        Called by the `_CanvasBufferContextManager`'s `__exit__` method. It updates
        the internal `_buffer_pool` to indicate that the specified buffer ID is now
        available for potential reuse by a future call to `_acquire_buffer_id`.

        Note: This does *not* send a 'destroyBuffer' command to the UI. Offscreen
        buffers are kept alive in the UI for potential reuse to improve performance,
        unless the entire canvas module instance is removed via `canvas.remove()`.

        Args:
            buffer_id (int): The ID (> 0) of the offscreen buffer to release back
                             into the pool (mark as not in use).
        """
        # Use the lock for thread-safe modification of the shared pool dictionary.
        with self._buffer_lock:
            if buffer_id in self._buffer_pool:
                # Mark the buffer as available for reuse.
                self._buffer_pool[buffer_id] = False
                logger.debug(f"Canvas '{self.target_id}': Released buffer ID {buffer_id} back to pool.")
            else:
                # This might happen if release is called improperly (e.g., wrong ID)
                # or perhaps after the canvas has already been removed.
                logger.warning(f"Canvas '{self.target_id}': Attempted to release buffer ID {buffer_id}, but it was not found in the active pool.")

    def _send_draw_buffer(self, source_buffer_id: int, target_buffer_id: int):
        """Internal: Sends the command to draw the content of one buffer onto another.

        This is primarily used by the `_CanvasBufferContextManager.__exit__` method
        to implement the double buffering "flip" – drawing the completed offscreen
        buffer (source) onto the visible onscreen buffer (target).

        Args:
            source_buffer_id (int): The ID of the buffer to copy content *from*.
            target_buffer_id (int): The ID of the buffer to draw content *onto*.

        Raises:
            SidekickConnectionError (or subclass): If sending the command fails.
        """
        # Prepare the payload with camelCase keys according to the protocol.
        # This call might raise SidekickConnectionError if sending fails.
        self._send_canvas_update(
            action="drawBuffer",
            options={
                "sourceBufferId": source_buffer_id,
                "targetBufferId": target_buffer_id
            }
        )

    # --- Internal Command Helper ---
    def _send_canvas_update(self, action: str, options: Dict[str, Any]):
        """Internal helper to construct and send a standard Canvas 'update' command payload.

        Takes the canvas-specific action name (e.g., "drawLine", "drawRect") and
        its associated options dictionary, wraps them into the standard 'update'
        payload structure required by the protocol, and sends the message using
        the base class's `_send_update` method.

        Args:
            action (str): The specific canvas action being performed (e.g., "drawLine",
                "clear", "drawRect"). This becomes the `action` field in the payload.
            options (Dict[str, Any]): A dictionary containing the parameters specific
                to the action (e.g., coordinates, colors, text). Keys within this
                dictionary **must already be `camelCase`** as required by the protocol
                (e.g., `lineColor`, `fillColor`, `bufferId`). This dictionary becomes
                the `options` field nested within the main payload.

        Raises:
            SidekickConnectionError (or subclass): If the underlying `_send_update`
                call fails (e.g., connection lost).
        """
        # Construct the final payload structure expected by the UI for canvas updates.
        update_payload = {
            "action": action,
            "options": options, # Assumes 'options' keys are already camelCase
        }
        # Delegate the actual sending and connection checks to the base class method.
        self._send_update(update_payload)

    # --- Public Drawing Methods ---

    def clear(self, buffer_id: Optional[int] = None):
        """Clears the specified canvas buffer (visible screen or an offscreen buffer).

        Erases all previously drawn shapes, lines, and text from the target buffer,
        resetting it to a blank state (typically transparent or a default background
        color determined by the UI theme).

        Args:
            buffer_id (Optional[int]): The ID of the buffer to clear.
                - If `None` (default) or `0`, clears the main visible (onscreen) canvas.
                - If a positive integer corresponding to an offscreen buffer (usually
                  obtained implicitly via `canvas.buffer()`), clears that specific
                  hidden buffer.

        Raises:
            SidekickConnectionError (or subclass): If sending the command fails.

        Examples:
            >>> canvas = sidekick.Canvas(100, 50)
            >>> canvas.draw_rect(10, 10, 30, 30, fill_color='red')
            >>> # Clear the main visible canvas
            >>> canvas.clear()
            >>>
            >>> # Example within double buffering: Clear the offscreen buffer
            >>> with canvas.buffer() as buf:
            ...     # buf implicitly refers to an offscreen buffer
            ...     # To clear *that* specific buffer (e.g., at start of frame drawing):
            ...     buf.clear() # This calls canvas.clear(buffer_id=buf._buffer_id) internally
            ...     buf.draw_circle(50, 25, 10) # Draw new content
            ... # On exit, screen is cleared, then buffer is drawn.
        """
        # Determine the target buffer ID, defaulting to the onscreen buffer (0) if None.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        logger.debug(f"Canvas '{self.target_id}': Sending 'clear' command for buffer ID {target_buffer_id}.")

        # Prepare options dictionary with camelCase key.
        options = {"bufferId": target_buffer_id}
        # Send the command using the internal helper. Raises on connection error.
        self._send_canvas_update("clear", options)

    def draw_line(self, x1: int, y1: int, x2: int, y2: int,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a straight line segment between two points on the specified buffer.

        Connects the start point `(x1, y1)` to the end point `(x2, y2)`.

        Args:
            x1 (int): The x-coordinate (pixels from left) of the line's start point.
            y1 (int): The y-coordinate (pixels from top) of the line's start point.
            x2 (int): The x-coordinate of the line's end point.
            y2 (int): The y-coordinate of the line's end point.
            line_color (Optional[str]): The color of the line. Accepts standard CSS
                color formats (e.g., 'black', '#FF0000', 'rgb(0, 255, 0)',
                'hsl(120, 100%, 50%)'). If `None`, the Sidekick UI's default line
                color (usually determined by the theme) is used.
            line_width (Optional[int]): The thickness of the line in pixels. Must be
                a positive integer (e.g., 1, 2, 3...). If `None`, the UI's default
                line width (typically 1 pixel) is used.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`, which
                targets the main visible (onscreen) canvas (ID 0). When used inside
                `with canvas.buffer() as buf:`, drawing methods on `buf` automatically
                target the correct offscreen buffer ID.

        Raises:
            ValueError: If `line_width` is provided but is not a positive integer.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> canvas = sidekick.Canvas(150, 150)
            >>> # Draw line with default color/width from (10, 20) to (100, 120)
            >>> canvas.draw_line(10, 20, 100, 120)
            >>> # Draw a thicker, blue line
            >>> canvas.draw_line(20, 30, 110, 130, line_color='blue', line_width=3)
        """
        # Determine target buffer ID.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Prepare the options dictionary for the payload.
        # Keys *must* be camelCase for the communication protocol.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2
        }
        # Add optional style parameters only if they are explicitly provided.
        if line_color is not None:
             options["lineColor"] = line_color # camelCase key for protocol
        if line_width is not None:
            # Validate line_width locally before sending.
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width # camelCase key for protocol
            else:
                 # Log a warning or raise an error for invalid input. Raising ValueError is stricter.
                 # logger.warning(f"Canvas '{self.target_id}': Invalid line_width ({line_width}) provided to draw_line. Must be positive int. Ignoring.")
                 raise ValueError("line_width must be a positive integer.")

        # Send the command. Raises on connection error.
        self._send_canvas_update("drawLine", options)

    def draw_rect(self, x: int, y: int, width: int, height: int,
                  fill_color: Optional[str] = None,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a rectangle on the specified buffer.

        The rectangle is defined by its top-left corner coordinates `(x, y)` and
        its `width` and `height`.

        Args:
            x (int): The x-coordinate of the top-left corner.
            y (int): The y-coordinate of the top-left corner.
            width (int): The width of the rectangle in pixels. Should be non-negative.
                         (A width of 0 might not be visible).
            height (int): The height of the rectangle in pixels. Should be non-negative.
                          (A height of 0 might not be visible).
            fill_color (Optional[str]): The color to fill the inside of the rectangle.
                Accepts CSS color formats. If `None` (default), the rectangle will
                not be filled (its interior will be transparent).
            line_color (Optional[str]): The color of the rectangle's outline (border).
                If `None` (default), the UI's default outline color is used. If you
                don't want an outline, you might need to set `line_width` to 0 or
                `line_color` to the same as `fill_color` or a transparent color,
                depending on the desired effect and UI behavior.
            line_width (Optional[int]): The thickness of the outline in pixels. Must
                be positive if an outline is desired. If `None` (default), the UI's
                default outline width (typically 1 pixel) is used. A `line_width` of 0
                usually means no outline is drawn.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Raises:
            ValueError: If `line_width` is provided but is not a non-negative integer,
                        or if `width` or `height` are negative.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> canvas = sidekick.Canvas(200, 150)
            >>> # Draw an empty rectangle with a 2px red border
            >>> canvas.draw_rect(10, 10, 50, 80, line_color='red', line_width=2)
            >>> # Draw a filled green rectangle with the default 1px border
            >>> canvas.draw_rect(70, 30, 40, 40, fill_color='green')
            >>> # Draw a filled yellow rectangle with effectively no border
            >>> canvas.draw_rect(120, 50, 30, 30, fill_color='yellow', line_width=0)
        """
        # Determine target buffer ID.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Basic validation for size and line width.
        if width < 0: raise ValueError("Rectangle width cannot be negative.")
        if height < 0: raise ValueError("Rectangle height cannot be negative.")

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x": x, "y": y, "width": width, "height": height
        }
        # Add optional style parameters if provided.
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            # Allow line_width of 0 to mean "no line".
            if isinstance(line_width, int) and line_width >= 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a non-negative integer.")

        # Send the command. Raises on connection error.
        self._send_canvas_update("drawRect", options)

    def draw_circle(self, cx: int, cy: int, radius: int,
                    fill_color: Optional[str] = None,
                    line_color: Optional[str] = None,
                    line_width: Optional[int] = None,
                    buffer_id: Optional[int] = None):
        """Draws a circle on the specified buffer.

        The circle is defined by its center coordinates `(cx, cy)` and its `radius`.

        Args:
            cx (int): The x-coordinate of the center of the circle.
            cy (int): The y-coordinate of the center of the circle.
            radius (int): The radius of the circle in pixels. Must be positive.
            fill_color (Optional[str]): The color to fill the inside of the circle.
                Accepts CSS color formats. If `None` (default), the circle is not filled.
            line_color (Optional[str]): The color of the circle's outline.
                If `None` (default), the UI's default outline color is used.
            line_width (Optional[int]): The thickness of the outline in pixels.
                Must be positive if an outline is desired. If `None` (default), the UI's
                default outline width (typically 1 pixel) is used. Use 0 for no outline.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Raises:
            ValueError: If `radius` is not positive, or if `line_width` is provided
                        but is not a non-negative integer.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> canvas = sidekick.Canvas(250, 150)
            >>> # Draw a filled red circle
            >>> canvas.draw_circle(50, 75, 40, fill_color='red')
            >>> # Draw an empty circle with a thick blue outline
            >>> canvas.draw_circle(150, 75, 30, line_color='blue', line_width=4)
        """
        # Determine target buffer ID.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Validate radius.
        if not isinstance(radius, (int, float)) or radius <= 0:
            raise ValueError("Circle radius must be a positive number.")
        # Ensure radius is int for payload if it was float.
        radius_int = int(radius)

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "cx": cx, "cy": cy, "radius": radius_int
        }
        # Add optional style parameters if provided.
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width >= 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a non-negative integer.")

        # Send the command. Raises on connection error.
        self._send_canvas_update("drawCircle", options)

    def draw_polyline(self, points: PointList,
                      line_color: Optional[str] = None,
                      line_width: Optional[int] = None,
                      buffer_id: Optional[int] = None):
        """Draws a series of connected line segments (an open path) on the specified buffer.

        Connects the points in the order they appear in the `points` list using
        straight lines. It's an "open" path because, unlike `draw_polygon`, it
        does not automatically draw a line connecting the last point back to the first.

        Args:
            points (List[Tuple[int, int]]): A list containing at least two vertex
                tuples, where each tuple `(x, y)` represents the integer coordinates
                of a corner point of the polyline.
            line_color (Optional[str]): The color for all line segments in the polyline.
                Uses UI default if `None`.
            line_width (Optional[int]): The thickness for all line segments in pixels.
                Must be positive. Uses UI default (typically 1) if `None`.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Raises:
            ValueError: If `points` contains fewer than two points, or if `line_width`
                        is provided but is not positive.
            TypeError: If `points` is not a list or contains non-tuple/non-numeric elements.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> canvas = sidekick.Canvas(200, 100)
            >>> # Draw a 'W' shape
            >>> w_shape_points = [(20, 80), (40, 20), (60, 80), (80, 20), (100, 80)]
            >>> canvas.draw_polyline(w_shape_points, line_color='purple', line_width=3)
        """
        # Determine target buffer ID.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Validate input points list structure and minimum length.
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError("draw_polyline requires a list of at least two (x, y) point tuples.")

        # Convert the list of tuples into the list of dictionaries format
        # required by the communication protocol ({ "x": ..., "y": ... }).
        # Also perform basic validation that points contain numbers.
        try:
            points_payload = [{"x": int(p[0]), "y": int(p[1])} for p in points]
        except (TypeError, IndexError, ValueError) as e:
             raise TypeError(f"Invalid data format in 'points' list for draw_polyline. Expect list of (x, y) tuples/lists with numbers. Error: {e}")


        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {"bufferId": target_buffer_id, "points": points_payload}
        # Add optional style parameters if provided.
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a positive integer.")

        # Send the command. Raises on connection error.
        self._send_canvas_update("drawPolyline", options)

    def draw_polygon(self, points: PointList,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None,
                     buffer_id: Optional[int] = None):
        """Draws a closed polygon shape on the specified buffer.

        Connects the vertices (points) in the order provided and automatically
        draws an additional line segment connecting the last point back to the
        first point to close the shape. The interior can optionally be filled.

        Args:
            points (List[Tuple[int, int]]): A list containing at least three vertex
                tuples, where each tuple `(x, y)` represents the integer coordinates
                of a corner of the polygon.
            fill_color (Optional[str]): The color to fill the interior of the polygon.
                Accepts CSS color formats. If `None` (default), the polygon is not filled.
            line_color (Optional[str]): The color of the polygon's outline. Uses UI
                default if `None`. Use 0 for no outline.
            line_width (Optional[int]): The thickness of the outline in pixels. Must
                be non-negative. Uses UI default (typically 1) if `None`.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Raises:
            ValueError: If `points` contains fewer than three points, or if
                        `line_width` is provided but is negative.
            TypeError: If `points` is not a list or contains invalid data.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> canvas = sidekick.Canvas(200, 200)
            >>> # Draw a filled blue triangle
            >>> triangle = [(50, 150), (100, 50), (150, 150)]
            >>> canvas.draw_polygon(triangle, fill_color='blue')
            >>> # Draw an empty hexagon outline
            >>> hexagon = [(20, 10), (60, 10), (80, 50), (60, 90), (20, 90), (0, 50)]
            >>> canvas.draw_polygon(hexagon, line_color='darkgreen', line_width=2)
        """
        # Determine target buffer ID.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Validate input points list structure and minimum length.
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError("draw_polygon requires a list of at least three (x, y) point tuples.")

        # Convert points to the protocol format and validate.
        try:
            points_payload = [{"x": int(p[0]), "y": int(p[1])} for p in points]
        except (TypeError, IndexError, ValueError) as e:
             raise TypeError(f"Invalid data format in 'points' list for draw_polygon. Expect list of (x, y) tuples/lists with numbers. Error: {e}")

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {"bufferId": target_buffer_id, "points": points_payload}
        # Add optional style parameters if provided.
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width >= 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a non-negative integer.")

        # Send the command. Raises on connection error.
        self._send_canvas_update("drawPolygon", options)

    def draw_ellipse(self, cx: int, cy: int, radius_x: int, radius_y: int,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None,
                     buffer_id: Optional[int] = None):
        """Draws an ellipse (or oval) shape on the specified buffer.

        The ellipse is defined by its center coordinates `(cx, cy)` and its
        horizontal radius (`radius_x`) and vertical radius (`radius_y`). If
        `radius_x` equals `radius_y`, this draws a circle.

        Args:
            cx (int): The x-coordinate of the center of the ellipse.
            cy (int): The y-coordinate of the center of the ellipse.
            radius_x (int): The horizontal radius (half the total width) of the ellipse.
                Must be positive.
            radius_y (int): The vertical radius (half the total height) of the ellipse.
                Must be positive.
            fill_color (Optional[str]): The color to fill the inside of the ellipse.
                Accepts CSS color formats. If `None` (default), the ellipse is not filled.
            line_color (Optional[str]): The color of the ellipse's outline. Uses UI
                default if `None`.
            line_width (Optional[int]): The thickness of the outline in pixels. Must
                be non-negative. Uses UI default (typically 1) if `None`. Use 0 for no outline.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Raises:
            ValueError: If `radius_x` or `radius_y` are not positive, or if
                        `line_width` is provided but is negative.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> canvas = sidekick.Canvas(250, 150)
            >>> # Draw a wide, short, filled red ellipse
            >>> canvas.draw_ellipse(125, 50, 80, 30, fill_color='red')
            >>> # Draw a tall, thin, empty ellipse outline
            >>> canvas.draw_ellipse(125, 100, 20, 40, line_color='black', line_width=1)
        """
        # Determine target buffer ID.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Validate radii.
        if not isinstance(radius_x, (int, float)) or radius_x <= 0:
            raise ValueError("Ellipse radius_x must be a positive number.")
        if not isinstance(radius_y, (int, float)) or radius_y <= 0:
            raise ValueError("Ellipse radius_y must be a positive number.")
        # Ensure integer radii for payload.
        radius_x_int = int(radius_x)
        radius_y_int = int(radius_y)

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "cx": cx, "cy": cy,
            "radiusX": radius_x_int, # camelCase key for the protocol
            "radiusY": radius_y_int  # camelCase key for the protocol
        }
        # Add optional style parameters if provided.
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width >= 0:
                options["lineWidth"] = line_width
            else:
                 raise ValueError("line_width must be a non-negative integer.")

        # Send the command. Raises on connection error.
        self._send_canvas_update("drawEllipse", options)

    def draw_text(self, x: int, y: int, text: str,
                  text_color: Optional[str] = None,
                  text_size: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a string of text on the specified buffer.

        The `(x, y)` coordinates typically define the position of the text. The exact
        alignment (e.g., whether `(x, y)` is the top-left corner, bottom-left baseline,
        or center) might depend slightly on the underlying UI implementation, but
        bottom-left baseline is common for canvas APIs.

        Args:
            x (int): The x-coordinate for the starting position of the text.
            y (int): The y-coordinate for the starting position of the text.
            text (str): The text string you want to display. Any Python object provided
                        will be converted to its string representation using `str()`.
            text_color (Optional[str]): The color of the text. Accepts CSS color
                formats. Uses the UI's default text color (usually black or white
                depending on theme) if `None`.
            text_size (Optional[int]): The font size in pixels. Must be positive.
                Uses the UI's default font size if `None`.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Raises:
            ValueError: If `text_size` is provided but is not positive.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> canvas = sidekick.Canvas(200, 100)
            >>> score = 150
            >>> canvas.draw_text(10, 20, f"Score: {score}") # Draw score with default style
            >>> canvas.draw_text(100, 60, "GAME OVER", text_color='red', text_size=24) # Larger, red text
        """
        # Determine target buffer ID.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x": x, "y": y,
            "text": str(text) # Ensure the text is explicitly converted to a string.
        }
        # Add optional style parameters if provided.
        if text_color is not None: options["textColor"] = text_color
        if text_size is not None:
            if isinstance(text_size, int) and text_size > 0:
                options["textSize"] = text_size
            else:
                 raise ValueError("text_size must be a positive integer.")

        # Send the command. Raises on connection error.
        self._send_canvas_update("drawText", options)

    # --- Cleanup ---
    def _reset_specific_callbacks(self):
        """Internal: Resets canvas-specific callbacks when the module is removed.

        Called automatically by the base class's `remove()` method.
        """
        # Reset the click callback reference.
        self._click_callback = None

    def remove(self):
        """Removes the canvas from the Sidekick UI and cleans up associated resources.

        This performs the necessary cleanup actions:

        1.  **Destroys Offscreen Buffers:** Sends commands to the Sidekick UI to
            destroy any hidden offscreen buffers that were created for this canvas
            instance via `canvas.buffer()`, releasing their resources in the UI.
        2.  **Calls Base `remove()`:** Invokes the `BaseModule.remove()` method, which:
            a. Unregisters the internal message handler for this canvas.
            b. Resets registered callbacks (`on_click`, `on_error`) to `None`.
            c. Sends the final 'remove' command to the Sidekick UI to delete the
               main canvas element itself.

        After calling `remove()`, you should no longer interact with this `Canvas` object.

        Raises:
            SidekickConnectionError (or subclass): Can occur if sending the
                'destroyBuffer' or the final 'remove' command fails. Cleanup of local
                Python resources (callbacks, handlers, buffer pool state) will still
                be attempted.
        """
        logger.info(f"Requesting removal of canvas '{self.target_id}' and its associated offscreen buffers.")

        # --- Destroy Offscreen Buffers ---
        # Acquire lock for safe access/modification of the buffer pool during removal.
        with self._buffer_lock:
            # Get a list of buffer IDs currently tracked in the pool *before* clearing it.
            # We only need to explicitly destroy offscreen buffers (ID > 0).
            buffer_ids_to_destroy = [bid for bid in self._buffer_pool if bid != self.ONSCREEN_BUFFER_ID]

            # Send a 'destroyBuffer' command for each known offscreen buffer.
            # Do this before removing the main canvas module.
            for buffer_id in buffer_ids_to_destroy:
                 try:
                     logger.debug(f"Canvas '{self.target_id}': Sending 'destroyBuffer' command for buffer ID {buffer_id}.")
                     # Prepare payload with camelCase key.
                     self._send_canvas_update(
                         action="destroyBuffer",
                         options={"bufferId": buffer_id}
                     )
                 except connection.SidekickConnectionError as e:
                     # Log the error but continue trying to remove other buffers and the main canvas.
                     logger.warning(f"Canvas '{self.target_id}': Failed to send destroy command for offscreen buffer {buffer_id} during removal: {e}")
                 except Exception as e_destroy:
                     # Catch other unexpected errors during buffer destruction.
                     logger.exception(f"Canvas '{self.target_id}': Unexpected error destroying buffer {buffer_id}: {e_destroy}")


            # Clear the local state of the buffer pool after attempting destruction.
            self._buffer_pool.clear()
            self._next_buffer_id = 1 # Reset the counter

        # --- Call Base Class Removal ---
        # This handles unregistering message handlers, resetting callbacks (including
        # calling our _reset_specific_callbacks), and sending the final 'remove'
        # command for the main canvas module instance itself.
        super().remove()

    def __del__(self):
        """Internal: Fallback attempt to clean up resources upon garbage collection. (Internal).

        Warning:
            Relying on `__del__` for cleanup is not reliable in Python. **You should
            always explicitly call the `canvas.remove()` method** when you are finished
            with a canvas instance to ensure proper cleanup of both Python resources
            and UI elements (including offscreen buffers) in Sidekick. This `__del__`
            method primarily attempts to call the base class's `__del__` for handler
            unregistration as a last resort. It does *not* attempt to destroy
            offscreen buffers.
        """
        try:
            # Delegate to the base class's __del__ for handler unregistration attempt.
            super().__del__()
        except Exception:
            # Suppress errors during __del__, as recommended practice.
            pass