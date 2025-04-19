"""Provides the Canvas class for creating a 2D drawing surface in Sidekick.

Use the `sidekick.Canvas` class to create a blank area in the Sidekick panel
where you can draw simple shapes like lines, rectangles, circles, polygons,
ellipses, and text using Python commands.

Think of it as a digital whiteboard or a simple drawing API that lets
you visually represent geometric concepts, create simple graphics, or even
build basic animations controlled by your script.

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
    >>> canvas.draw_text(150, 120, "Hello!", text_color='white', text_size=16)

Coordinate System:
    The coordinate system origin (0, 0) is the **top-left corner** of the canvas.
    The x-axis increases to the right, and the y-axis increases downwards.
    All coordinates and dimensions (like `width`, `height`, `radius`) are in pixels.

Double Buffering for Animation:
    For smoother animations without flickering, Sidekick provides a "double buffer"
    mechanism. You draw all the elements of your animation frame onto a hidden
    (offscreen) buffer, and then display the entire frame at once. This is done
    using a `with` statement and the `canvas.buffer()` method:

    >>> import sidekick
    >>> import time
    >>> import math
    >>>
    >>> canvas = sidekick.Canvas(200, 150)
    >>> angle = 0
    >>>
    >>> while True:
    ...     # --- Start drawing on the hidden buffer ---
    ...     with canvas.buffer() as buf:
    ...         # Calculate new position for a circle
    ...         x = 100 + 80 * math.cos(angle)
    ...         y = 75 + 50 * math.sin(angle)
    ...
    ...         # Draw the circle on the hidden buffer
    ...         buf.draw_circle(int(x), int(y), 10, fill_color='orange')
    ...         # Draw text on the hidden buffer
    ...         buf.draw_text(10, 10, f"Angle: {angle:.1f}", text_color='black')
    ...     # --- End drawing on the hidden buffer ---
    ...     # When the 'with' block ends, the hidden buffer's content is
    ...     # automatically copied to the visible canvas in Sidekick.
    ...
    ...     angle += 0.1
    ...     time.sleep(0.05) # Control animation speed
    ...
    ...     # Add a condition to stop the loop (e.g., after one rotation)
    ...     if angle > 2 * math.pi:
    ...         print("Animation finished.")
    ...         break
    ...
    >>> # Keep the panel open if needed (e.g., if using on_click)
    >>> # sidekick.run_forever()

Interactivity (Clicks):
    You can also make your canvas react when the user clicks on it:
    >>> import sidekick
    >>>
    >>> canvas = sidekick.Canvas(250, 250)
    >>>
    >>> def handle_click(x, y):
    ...     \"\"\"This function is called when the canvas is clicked.\"\"\"
    ...     print(f"Canvas was clicked at coordinates ({x}, {y})")
    ...     # Draw a small green circle where the user clicked
    ...     canvas.draw_circle(x, y, 5, fill_color='green')
    ...
    >>> # Register the function to handle click events
    >>> canvas.on_click(handle_click)
    >>>
    >>> print("Canvas created. Click on the canvas in Sidekick!")
    >>> # Keep the script running to listen for click events
    >>> sidekick.run_forever()
"""

import threading
import math  # Used in examples, good to keep imported
from typing import Optional, Dict, Any, Callable, List, Tuple, ContextManager, Union

from . import logger
from . import connection
from .base_module import BaseModule

# Type hint for a list of points used in polylines/polygons
# Example: [(10, 20), (50, 60), (30, 40)]
PointList = List[Tuple[int, int]]

# ==============================================================================
# == Internal: Canvas Buffer Proxy Class ==
# ==============================================================================

class _CanvasBufferProxy:
    """Internal helper object used with the `canvas.buffer()` context manager.

    When you use `with canvas.buffer() as buf:`, the `buf` variable holds an
    instance of this proxy class. It mimics the drawing methods of the main
    `Canvas` (like `draw_line`, `draw_rect`), but automatically directs those
    commands to a specific hidden (offscreen) drawing buffer instead of the
    visible canvas.

    Note:
        This is an internal implementation detail. You shouldn't need to create
        or interact with this class directly. Use the `canvas.buffer()` context
        manager.

    Args:
        canvas (Canvas): The parent `Canvas` instance this proxy is associated with.
        buffer_id (int): The unique ID (greater than 0) of the offscreen buffer
            that this proxy will draw onto.
    """
    def __init__(self, canvas: 'Canvas', buffer_id: int):
        self._canvas = canvas
        self._buffer_id = buffer_id
        # Ensure the associated buffer_id is valid
        if buffer_id <= 0:
             raise ValueError("CanvasBufferProxy requires a positive offscreen buffer ID.")

    # --- Mirrored Drawing Methods ---
    # Each method below calls the corresponding public method on the parent
    # `Canvas` instance, but forces the `buffer_id` argument to be the
    # specific ID of the offscreen buffer managed by this proxy.

    def clear(self):
        """Clears the content of the offscreen buffer associated with this context."""
        self._canvas.clear(buffer_id=self._buffer_id)

    def draw_line(self, x1: int, y1: int, x2: int, y2: int,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None):
        """Draws a line on the offscreen buffer."""
        self._canvas.draw_line(x1, y1, x2, y2, line_color, line_width,
                               buffer_id=self._buffer_id)

    def draw_rect(self, x: int, y: int, width: int, height: int,
                  fill_color: Optional[str] = None,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None):
        """Draws a rectangle on the offscreen buffer."""
        self._canvas.draw_rect(x, y, width, height, fill_color, line_color, line_width,
                              buffer_id=self._buffer_id)

    def draw_circle(self, cx: int, cy: int, radius: int,
                    fill_color: Optional[str] = None,
                    line_color: Optional[str] = None,
                    line_width: Optional[int] = None):
        """Draws a circle on the offscreen buffer."""
        self._canvas.draw_circle(cx, cy, radius, fill_color, line_color, line_width,
                                buffer_id=self._buffer_id)

    def draw_polyline(self, points: PointList,
                      line_color: Optional[str] = None,
                      line_width: Optional[int] = None):
        """Draws a series of connected lines (polyline) on the offscreen buffer."""
        self._canvas.draw_polyline(points, line_color, line_width,
                                  buffer_id=self._buffer_id)

    def draw_polygon(self, points: PointList,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None):
        """Draws a closed polygon on the offscreen buffer."""
        self._canvas.draw_polygon(points, fill_color, line_color, line_width,
                                 buffer_id=self._buffer_id)

    def draw_ellipse(self, cx: int, cy: int, radius_x: int, radius_y: int,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None):
        """Draws an ellipse on the offscreen buffer."""
        self._canvas.draw_ellipse(cx, cy, radius_x, radius_y, fill_color, line_color, line_width,
                                  buffer_id=self._buffer_id)

    def draw_text(self, x: int, y: int, text: str,
                  text_color: Optional[str] = None,
                  text_size: Optional[int] = None):
        """Draws text on the offscreen buffer."""
        self._canvas.draw_text(x, y, text, text_color, text_size,
                              buffer_id=self._buffer_id)

# ==============================================================================
# == Internal: Canvas Buffer Context Manager Class ==
# ==============================================================================

class _CanvasBufferContextManager:
    """Internal context manager returned by `canvas.buffer()`.

    This class manages the lifecycle of using an offscreen buffer for double
    buffering. It handles acquiring a buffer ID when entering the `with` block,
    preparing it (clearing), and then performing the necessary actions upon
    exiting the block (drawing the buffer to the screen and releasing the ID).

    Note:
        This is an internal implementation detail. Use the `canvas.buffer()` method.

    Args:
        canvas (Canvas): The parent `Canvas` instance this context manager belongs to.
    """
    def __init__(self, canvas: 'Canvas'):
        self._canvas = canvas
        # Stores the ID of the acquired offscreen buffer. Initialized to None.
        self._buffer_id: Optional[int] = None

    def __enter__(self) -> _CanvasBufferProxy:
        """Prepares an offscreen buffer when entering the `with` block.

        Steps:
        1. Acquires an available offscreen buffer ID from the canvas's internal pool.
        2. Sends a command to the Sidekick UI to clear this newly acquired buffer,
           ensuring it's blank before drawing starts.
        3. Returns a `_CanvasBufferProxy` instance that targets this specific buffer ID.

        Returns:
            _CanvasBufferProxy: An object with drawing methods that will operate
                on the hidden offscreen buffer.
        """
        # Get an available buffer ID (will create one if needed)
        self._buffer_id = self._canvas._acquire_buffer_id()
        logger.debug(f"Canvas '{self._canvas.target_id}': Entering buffer context, acquired buffer ID {self._buffer_id}.")

        # Immediately clear the acquired offscreen buffer before the user draws on it
        self._canvas.clear(buffer_id=self._buffer_id)

        # Return the proxy object that allows drawing onto this specific buffer
        return _CanvasBufferProxy(self._canvas, self._buffer_id)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Finalizes buffer operations when exiting the `with` block.

        Steps:
        1. Checks if an exception occurred within the `with` block.
        2. If no exception occurred:
           a. **Clears the visible (onscreen) canvas.** This is necessary because
              the offscreen buffer might have transparency, and we want to replace
              the previous onscreen content completely, not draw over it.
           b. Sends a command to the Sidekick UI to draw the entire content of the
              hidden offscreen buffer onto the now-cleared visible canvas.
        3. Releases the offscreen buffer ID back to the canvas's internal pool,
           making it available for reuse.
        4. Allows any exception raised within the `with` block to propagate outwards.

        Args:
            exc_type: The type of the exception raised within the `with` block,
                or `None` if no exception occurred.
            exc_val: The exception instance itself, or `None`.
            exc_tb: The traceback object, or `None`.

        Returns:
            bool: `False` to indicate that any exception that occurred should be
            re-raised after this method finishes.
        """
        # Ensure we actually acquired a buffer ID in __enter__
        if self._buffer_id is None:
            logger.error(f"Canvas '{self._canvas.target_id}': Exiting buffer context but buffer ID is None! This should not happen.")
            return False # Don't suppress potential exceptions

        # Only draw the buffer to the screen if the 'with' block completed without errors
        if exc_type is None:
            logger.debug(f"Canvas '{self._canvas.target_id}': Exiting buffer context normally. Clearing screen and drawing buffer {self._buffer_id}.")
            # --- Double Buffering Fix ---
            # 1. Clear the onscreen canvas first to ensure transparency works correctly
            self._canvas.clear(buffer_id=self._canvas.ONSCREEN_BUFFER_ID)
            # 2. Draw the completed offscreen buffer onto the (now clear) onscreen canvas
            self._canvas._send_draw_buffer(source_buffer_id=self._buffer_id, target_buffer_id=self._canvas.ONSCREEN_BUFFER_ID)
        else:
            # If an error occurred inside the 'with' block, log it but don't draw the (potentially incomplete) buffer.
            logger.warning(f"Canvas '{self._canvas.target_id}': Exiting buffer context due to an exception ({exc_type}). The content of buffer {self._buffer_id} will NOT be drawn to the screen.")

        # CRITICAL: Always release the buffer ID back to the pool, regardless of whether an error occurred.
        self._canvas._release_buffer_id(self._buffer_id)
        # Reset the stored ID for safety
        self._buffer_id = None

        # Return False ensures that any exception raised within the 'with' block
        # is not suppressed and will continue to propagate.
        return False

# ==============================================================================
# == Main Canvas Class ==
# ==============================================================================

class Canvas(BaseModule):
    """Represents a 2D drawing canvas module instance in the Sidekick UI.

    Provides a surface where you can programmatically draw shapes, lines, and text.
    Useful for visualizing algorithms, creating simple graphics, games, or animations.

    To draw, simply call methods like `draw_line()`, `draw_rect()`, etc.
    By default, these draw directly to the visible canvas.

    For smoother animations, use the `buffer()` method within a `with` statement
    to utilize double buffering (see module docstring for example).

    Attributes:
        target_id (str): The unique identifier for this canvas instance, used for
            communication with the Sidekick UI. Automatically generated if not
            provided during initialization.
        width (int): The width of the canvas drawing area in pixels. Set during
            initialization.
        height (int): The height of the canvas drawing area in pixels. Set during
            initialization.
    """
    # Class constant representing the ID of the visible (onscreen) buffer.
    ONSCREEN_BUFFER_ID = 0

    def __init__(
        self,
        width: int,
        height: int,
        instance_id: Optional[str] = None,
        spawn: bool = True,
    ):
        """Initializes a new Canvas object and its corresponding element in Sidekick.

        Args:
            width (int): The desired width of the canvas drawing area in pixels.
                Must be a positive integer.
            height (int): The desired height of the canvas drawing area in pixels.
                Must be a positive integer.
            instance_id (Optional[str]): A specific ID for this canvas instance.
                - If `spawn=True` (default): If provided, this ID will be used.
                  If `None`, a unique ID (e.g., "canvas-1") will be generated.
                - If `spawn=False`: This ID is **required** and must match the ID
                  of an existing canvas element already present in the Sidekick UI
                  that you want to control with this Python object.
            spawn (bool): If `True` (the default), a command is sent to Sidekick
                to create a new canvas UI element with the specified `width` and
                `height`. If `False`, the library assumes a canvas element with the
                given `instance_id` already exists in the UI, and this Python object
                will simply attach to it for sending drawing commands or receiving
                events. When `spawn=False`, the `width` and `height` arguments are
                still validated locally but are not sent in the (empty) spawn command.

        Raises:
            ValueError: If `width` or `height` are not positive integers, or if
                `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to the
                Sidekick UI cannot be established or fails during initialization.

        Examples:
            >>> # Create a new 300x200 canvas in Sidekick
            >>> my_canvas = sidekick.Canvas(300, 200)
            >>>
            >>> # Create another canvas with a specific ID
            >>> game_area = sidekick.Canvas(640, 480, instance_id="main-game-canvas")
            >>>
            >>> # Assume a canvas with ID "debug-overlay" already exists in Sidekick.
            >>> # Attach a Python object to control it (dimensions needed for validation).
            >>> overlay = sidekick.Canvas(100, 50, instance_id="debug-overlay", spawn=False)
        """
        # Validate dimensions before proceeding.
        if not (isinstance(width, int) and width > 0):
            raise ValueError("Canvas width must be a positive integer.")
        if not (isinstance(height, int) and height > 0):
            raise ValueError("Canvas height must be a positive integer.")

        # Prepare the payload (data) for the initial 'spawn' command.
        spawn_payload: Dict[str, Any] = {}
        if spawn:
            # Keys must be camelCase to match the communication protocol.
            spawn_payload["width"] = width
            spawn_payload["height"] = height

        # Initialize the base class. This handles:
        # - Establishing the connection (blocking if needed).
        # - Generating/assigning the target_id.
        # - Registering internal message handlers.
        # - Sending the 'spawn' command if spawn=True.
        super().__init__(
            module_type="canvas",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload if spawn else None, # Send payload only if spawning
        )

        # Store dimensions locally for reference (e.g., validation).
        self.width = width
        self.height = height
        # Initialize the placeholder for the user's click callback function.
        self._click_callback: Optional[Callable[[int, int], None]] = None
        # --- Double Buffering Internal State ---
        # Dictionary to track offscreen buffers: { buffer_id: is_currently_in_use }
        self._buffer_pool: Dict[int, bool] = {}
        # Counter to generate unique IDs for new offscreen buffers (starting from 1)
        self._next_buffer_id: int = 1
        # Lock to prevent race conditions when multiple threads might access the buffer pool
        # (though typical Sidekick use is single-threaded for drawing).
        self._buffer_lock = threading.Lock()

        logger.info(f"Canvas '{self.target_id}' initialized (spawn={spawn}, size={width}x{height}).")

    # --- Internal Message Handling ---
    def _internal_message_handler(self, message: Dict[str, Any]):
        """Handles incoming messages (events or errors) from the Sidekick UI
           specifically targeted at this canvas instance.

        Overrides the base class method to process 'click' events. If a click
        event message arrives, it extracts the (x, y) coordinates from the
        message payload and, if an `on_click` callback function has been
        registered by the user, calls that function with the coordinates.

        It always calls the base class's handler afterwards to ensure standard
        'error' message processing occurs.

        Args:
            message (Dict[str, Any]): The raw message dictionary received from
                the Sidekick connection manager. Expected keys include 'type',
                'src' (matching this instance's target_id), and 'payload'.
                Payload keys are expected to be camelCase.
        """
        msg_type = message.get("type")
        payload = message.get("payload")

        if msg_type == "event":
            event_type = payload.get("event") if payload else None
            # Check if it's a 'click' event AND if the user has registered a handler
            if event_type == "click" and self._click_callback:
                try:
                    # Safely extract coordinates from the payload
                    x = payload.get('x')
                    y = payload.get('y')
                    # Validate that coordinates are present and are integers
                    if x is not None and isinstance(x, int) and \
                       y is not None and isinstance(y, int):
                        # Call the user's registered callback function!
                        self._click_callback(x, y)
                    else:
                         logger.warning(f"Canvas '{self.target_id}' received click event with missing/invalid coordinates: {payload}")
                except Exception as e:
                    # Important: Catch errors *within* the user's callback function
                    # to prevent crashing the library's background listener thread.
                    logger.exception(f"Error occurred inside Canvas '{self.target_id}' on_click callback: {e}")
            else:
                 # Log other event types if needed for debugging
                 logger.debug(f"Canvas '{self.target_id}' received unhandled event type '{event_type}' or no click callback registered.")

        # Always call the base class handler. This is crucial for handling
        # 'error' messages sent from the UI related to this canvas instance.
        super()._internal_message_handler(message)

    # --- Callback Registration ---
    def on_click(self, callback: Optional[Callable[[int, int], None]]):
        """Registers a function to be called when the user clicks on the canvas.

        When the user clicks anywhere on the visible canvas area in the
        Sidekick UI panel, the function you provide (`callback`) will be
        executed within your running Python script.

        Note:
            Click events are only triggered by interactions with the visible
            (onscreen) canvas (buffer ID 0). Clicks are not detected on hidden
            offscreen buffers used with `canvas.buffer()`.

        Args:
            callback (Optional[Callable[[int, int], None]]): The function to execute
                when a click occurs. This function must accept two integer arguments:
                `x` (the horizontal pixel coordinate of the click, 0 = left edge)
                and `y` (the vertical pixel coordinate, 0 = top edge).
                To remove a previously registered callback, pass `None`.

        Raises:
            TypeError: If the provided `callback` is not a callable function (or `None`).

        Returns:
            None: This method only registers the callback and does not return a value.

        Example:
            >>> def user_drew_dot(x, y):
            ...     print(f"Drawing a dot at ({x}, {y}) because the user clicked there.")
            ...     # Draw a small black circle at the click location
            ...     canvas.draw_circle(x, y, 3, fill_color='black')
            ...
            >>> canvas = sidekick.Canvas(200, 100)
            >>> canvas.on_click(user_drew_dot)
            >>> print("Click on the canvas in Sidekick!")
            >>> sidekick.run_forever() # Essential to keep listening for events
        """
        if callback is not None and not callable(callback):
            raise TypeError("The provided on_click callback must be a callable function or None.")
        logger.info(f"Setting on_click callback for canvas '{self.target_id}'.")
        self._click_callback = callback

    # --- Error Callback ---
    # The `on_error(callback)` method is inherited from `BaseModule`.
    # Use `canvas.on_error(my_error_handler)` to register a function that
    # receives error messages if the Sidekick UI encounters a problem specifically
    # related to processing a command for *this* canvas instance (e.g., trying
    # to draw on a non-existent buffer).

    # --- Buffer Management Methods ---
    def buffer(self) -> ContextManager[_CanvasBufferProxy]:
        """Provides a context manager for efficient double buffering.

        Using this method within a `with` statement enables double buffering,
        which is the recommended technique for creating smooth, flicker-free
        animations or complex drawing sequences.

        How it works:
        1. Entering the `with` block (`with canvas.buffer() as buf:`):
           - An offscreen (hidden) buffer is acquired or created.
           - This hidden buffer is cleared automatically.
           - The `buf` variable becomes a proxy object.
        2. Inside the `with` block:
           - All drawing commands called on `buf` (e.g., `buf.draw_circle(...)`)
             are sent to the hidden buffer, not the visible canvas.
        3. Exiting the `with` block:
           - The visible canvas is cleared.
           - The entire content of the hidden buffer is drawn ("blitted") onto
             the visible canvas in a single operation.
           - The hidden buffer is released back into a pool for reuse.

        Returns:
            ContextManager[_CanvasBufferProxy]: An object designed to be used
            in a `with` statement. The object yielded (`buf` in the example)
            provides the drawing methods that target the hidden buffer.

        Example (Simple Animation):
            >>> import time, math
            >>> canvas = sidekick.Canvas(100, 100)
            >>> angle = 0
            >>> for _ in range(100): # Animate for 100 frames
            ...     with canvas.buffer() as frame_buffer:
            ...         # Calculate position
            ...         cx = 50 + 40 * math.cos(angle)
            ...         cy = 50 + 40 * math.sin(angle)
            ...         # Draw on the hidden buffer
            ...         frame_buffer.draw_circle(int(cx), int(cy), 5, fill_color='blue')
            ...     # Screen updates automatically here
            ...     angle += 0.1
            ...     time.sleep(0.02)
        """
        return _CanvasBufferContextManager(self)

    def _acquire_buffer_id(self) -> int:
        """Internal: Gets an available offscreen buffer ID from the pool.

        If no unused buffers are available in the pool, it generates a new unique
        ID, sends a command to the Sidekick UI to create a corresponding buffer
        element, adds the new ID to the pool, and returns it.

        Returns:
            int: The ID of an available offscreen buffer (always > 0).

        Raises:
            SidekickConnectionError (or subclass): If sending the 'createBuffer'
                command fails.
        """
        # Use a lock to ensure thread-safe access to the buffer pool dictionary
        with self._buffer_lock:
            # First, check if there's an existing buffer in the pool that's not currently in use
            for buffer_id, is_in_use in self._buffer_pool.items():
                if not is_in_use:
                    self._buffer_pool[buffer_id] = True # Mark as now in use
                    logger.debug(f"Canvas '{self.target_id}': Reusing buffer ID {buffer_id}.")
                    return buffer_id # Return the existing, unused ID

            # If no unused buffer was found, we need to create a new one.
            # Get the next available ID from our counter.
            new_id = self._next_buffer_id
            self._next_buffer_id += 1 # Increment the counter for the next time
            logger.debug(f"Canvas '{self.target_id}': Creating new buffer with ID {new_id}.")

            # Send the 'createBuffer' command to the Sidekick UI.
            # The payload requires the 'bufferId' key (camelCase).
            payload = {
                "action": "createBuffer",
                "options": {"bufferId": new_id},
            }
            # self._send_update handles sending the message via the connection.
            self._send_update(payload)

            # Add the new buffer ID to our pool and mark it as currently in use.
            self._buffer_pool[new_id] = True
            return new_id # Return the newly created ID

    def _release_buffer_id(self, buffer_id: int):
        """Internal: Marks an offscreen buffer ID as no longer in use in the pool.

        This is typically called when a `with canvas.buffer() as buf:` block exits.
        It allows the buffer ID to be potentially reused later by `_acquire_buffer_id`.

        Args:
            buffer_id (int): The ID of the offscreen buffer (must be > 0) to release.
        """
        # Use the lock for safe modification of the shared pool dictionary
        with self._buffer_lock:
            if buffer_id in self._buffer_pool:
                # Mark the buffer as no longer in use
                self._buffer_pool[buffer_id] = False
                logger.debug(f"Canvas '{self.target_id}': Released buffer ID {buffer_id} back to pool.")
            else:
                # This might happen if release is called improperly or after `remove()`
                logger.warning(f"Canvas '{self.target_id}': Attempted to release buffer ID {buffer_id}, but it was not found in the pool.")
        # Note: This does *not* send a 'destroyBuffer' command. Buffers are kept
        # in the UI for potential reuse unless the entire canvas is removed.

    def _send_draw_buffer(self, source_buffer_id: int, target_buffer_id: int):
        """Internal: Sends the command to draw one buffer onto another.

        This is used by the context manager (`__exit__`) to draw the completed
        offscreen buffer onto the visible onscreen buffer.

        Args:
            source_buffer_id (int): The ID of the buffer to copy *from*.
            target_buffer_id (int): The ID of the buffer to draw *onto*.

        Raises:
            SidekickConnectionError (or subclass): If sending the command fails.
        """
        # Prepare the payload with camelCase keys for the protocol.
        payload = {
            "action": "drawBuffer",
            "options": {
                "sourceBufferId": source_buffer_id,
                "targetBufferId": target_buffer_id
            },
        }
        self._send_update(payload)

    # --- Internal Command Helper ---
    def _send_canvas_update(self, action: str, options: Dict[str, Any]):
        """Internal helper to build and send a standard Canvas 'update' command.

        Constructs the payload dictionary required by the protocol for canvas updates
        and sends it using the base class's `_send_update` method.

        Args:
            action (str): The specific canvas action being performed (e.g., "drawLine",
                "clear", "drawRect"). This becomes the `action` field in the payload.
            options (Dict[str, Any]): A dictionary containing the parameters specific
                to the action (e.g., coordinates, colors, text). Keys within this
                dictionary **must already be `camelCase`** as required by the protocol.
                This dictionary becomes the `options` field in the payload.

        Raises:
            SidekickConnectionError (or subclass): If the underlying `_send_update`
                call fails (e.g., connection lost).
        """
        # Construct the final payload structure expected by the UI
        update_payload = {
            "action": action,
            "options": options, # Assumes 'options' keys are already camelCase
        }
        # Delegate the actual sending and connection checks to the base class method
        self._send_update(update_payload)

    # --- Public Drawing Methods ---

    def clear(self, buffer_id: Optional[int] = None):
        """Clears the specified canvas buffer (visible screen or an offscreen buffer).

        Removes all previously drawn shapes and content from the target buffer,
        effectively resetting it to a blank state (usually transparent or the
        default background color).

        Args:
            buffer_id (Optional[int]): The ID of the buffer to clear.
                - If `None` (default) or `0`, clears the visible (onscreen) canvas.
                - If a positive integer corresponding to a buffer acquired via
                  `canvas.buffer()`, clears that specific offscreen buffer.

        Returns:
            None: This method sends a command and does not return a value.

        Raises:
            SidekickConnectionError (or subclass): If sending the command fails.

        Examples:
            >>> # Clear the main visible canvas
            >>> canvas.clear()
            >>>
            >>> # Example within double buffering: Clear the offscreen buffer
            >>> with canvas.buffer() as buf:
            ...     # buf implicitly refers to an offscreen buffer
            ...     # To clear *that* specific buffer:
            ...     buf.clear() # This calls canvas.clear(buffer_id=buf._buffer_id) internally
            ...     # ... draw the new frame onto buf ...
        """
        # Determine the target buffer ID, defaulting to onscreen (0) if None is passed.
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID
        logger.debug(f"Canvas '{self.target_id}': Sending clear command for buffer ID {target_buffer_id}.")

        # Prepare options dictionary with camelCase key.
        options = {"bufferId": target_buffer_id}
        # Send the command using the internal helper.
        self._send_canvas_update("clear", options)

    def draw_line(self, x1: int, y1: int, x2: int, y2: int,
                  line_color: Optional[str] = None,
                  line_width: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws a straight line segment between two points on the specified buffer.

        Args:
            x1 (int): The x-coordinate (horizontal position) of the line's start point.
            y1 (int): The y-coordinate (vertical position) of the line's start point.
            x2 (int): The x-coordinate of the line's end point.
            y2 (int): The y-coordinate of the line's end point.
            line_color (Optional[str]): The color of the line. Accepts standard CSS
                color formats (e.g., 'black', '#FF0000', 'rgb(0, 255, 0)').
                If `None`, the Sidekick UI's default line color is used.
            line_width (Optional[int]): The thickness of the line in pixels. Must be
                a positive integer. If `None`, the UI's default line width
                (usually 1 pixel) is used.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`, which
                targets the visible (onscreen) canvas (ID 0). Provide the ID of
                an offscreen buffer if drawing within a `canvas.buffer()` context.

        Returns:
            None: This method sends a command and does not return a value.

        Raises:
            ValueError: If `line_width` is provided but is not a positive integer.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> canvas.draw_line(10, 20, 100, 150) # Draw line with default color/width
            >>> canvas.draw_line(20, 30, 110, 160, line_color='blue', line_width=3) # Blue, 3px thick
        """
        # Determine target buffer ID
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Prepare the options dictionary for the payload.
        # Keys *must* be camelCase for the protocol.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2
        }
        # Add optional style parameters only if they are provided.
        if line_color is not None:
             options["lineColor"] = line_color # camelCase key
        if line_width is not None:
            # Validate line_width before adding it
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width # camelCase key
            else:
                 logger.warning(f"Canvas '{self.target_id}': Invalid line_width ({line_width}) provided to draw_line. It must be a positive integer. Ignoring.")
                 # Optional: raise ValueError("line_width must be a positive integer.")

        # Send the command.
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
            x (int): The x-coordinate of the top-left corner of the rectangle.
            y (int): The y-coordinate of the top-left corner.
            width (int): The width of the rectangle in pixels. Should be non-negative.
            height (int): The height of the rectangle in pixels. Should be non-negative.
            fill_color (Optional[str]): The color to fill the inside of the rectangle.
                Accepts CSS color formats. If `None`, the rectangle will not be filled
                (it will be transparent).
            line_color (Optional[str]): The color of the rectangle's outline (border).
                If `None`, the UI's default outline color is used.
            line_width (Optional[int]): The thickness of the outline in pixels. Must
                be positive. If `None`, the UI's default outline width is used.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Returns:
            None: This method sends a command and does not return a value.

        Raises:
            ValueError: If `line_width` is provided but is not positive, or if
                        `width` or `height` are negative (though often drawing
                        libraries handle negative sizes gracefully, it's good practice).
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> # Draw an empty rectangle with a red border
            >>> canvas.draw_rect(50, 50, 100, 80, line_color='red', line_width=2)
            >>> # Draw a filled green rectangle with the default border
            >>> canvas.draw_rect(200, 100, 50, 50, fill_color='green')
            >>> # Draw a filled yellow rectangle with no visible border (using default width 1)
            >>> canvas.draw_rect(10, 150, 30, 30, fill_color='yellow', line_color='yellow')
        """
        # Determine target buffer ID
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Basic validation for size (optional, but good practice)
        if width < 0: logger.warning(f"Canvas '{self.target_id}': draw_rect called with negative width ({width}).")
        if height < 0: logger.warning(f"Canvas '{self.target_id}': draw_rect called with negative height ({height}).")

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x": x, "y": y, "width": width, "height": height
        }
        # Add optional style parameters if provided.
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                 logger.warning(f"Canvas '{self.target_id}': Invalid line_width ({line_width}) provided to draw_rect. Must be positive. Ignoring.")
                 # Optional: raise ValueError("line_width must be a positive integer.")

        # Send the command.
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
                If `None`, the circle is not filled.
            line_color (Optional[str]): The color of the circle's outline.
                If `None`, the UI's default outline color is used.
            line_width (Optional[int]): The thickness of the outline in pixels.
                Must be positive. If `None`, the UI's default outline width is used.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Returns:
            None: This method sends a command and does not return a value.

        Raises:
            ValueError: If `radius` is not positive, or if `line_width` is provided
                        but is not positive.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> # Draw a filled red circle
            >>> canvas.draw_circle(100, 100, 50, fill_color='red')
            >>> # Draw an empty circle with a thick blue outline
            >>> canvas.draw_circle(200, 80, 30, line_color='blue', line_width=4)
        """
        # Determine target buffer ID
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Validate radius
        if not (isinstance(radius, (int, float)) and radius > 0):
            raise ValueError(f"Canvas '{self.target_id}': draw_circle radius must be a positive number, got {radius}.")

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "cx": cx, "cy": cy, "radius": radius
        }
        # Add optional style parameters if provided.
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                 logger.warning(f"Canvas '{self.target_id}': Invalid line_width ({line_width}) provided to draw_circle. Must be positive. Ignoring.")
                 # Optional: raise ValueError("line_width must be a positive integer.")

        # Send the command.
        self._send_canvas_update("drawCircle", options)

    def draw_polyline(self, points: PointList,
                      line_color: Optional[str] = None,
                      line_width: Optional[int] = None,
                      buffer_id: Optional[int] = None):
        """Draws a series of connected line segments (an open path) on the specified buffer.

        Connects the points in the order they appear in the `points` list.
        Unlike `draw_polygon`, it does not automatically connect the last point
        back to the first.

        Args:
            points (List[Tuple[int, int]]): A list containing at least two tuples,
                where each tuple `(x, y)` represents the integer coordinates of a
                vertex (corner) of the polyline.
            line_color (Optional[str]): The color of the line segments. Uses UI default
                if `None`.
            line_width (Optional[int]): The thickness of the line segments in pixels.
                Must be positive. Uses UI default if `None`.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Returns:
            None: This method sends a command and does not return a value.

        Raises:
            ValueError: If `points` contains fewer than two points, or if `line_width`
                        is provided but is not positive.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> # Draw a V-shape
            >>> path = [(50, 50), (100, 100), (150, 50)]
            >>> canvas.draw_polyline(path, line_color='purple', line_width=2)
        """
        # Determine target buffer ID
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Validate input points list
        if not isinstance(points, list) or len(points) < 2:
            raise ValueError(f"Canvas '{self.target_id}': draw_polyline requires a list of at least two (x, y) points.")

        # Convert the list of tuples into the list of dictionaries format
        # required by the communication protocol ({ "x": ..., "y": ... }).
        points_payload = [{"x": p[0], "y": p[1]} for p in points]

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {"bufferId": target_buffer_id, "points": points_payload}
        # Add optional style parameters if provided.
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                 logger.warning(f"Canvas '{self.target_id}': Invalid line_width ({line_width}) provided to draw_polyline. Must be positive. Ignoring.")
                 # Optional: raise ValueError("line_width must be a positive integer.")

        # Send the command.
        self._send_canvas_update("drawPolyline", options)

    def draw_polygon(self, points: PointList,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None,
                     buffer_id: Optional[int] = None):
        """Draws a closed polygon shape on the specified buffer.

        Connects the points in the order provided and automatically connects the
        last point back to the first point to close the shape.

        Args:
            points (List[Tuple[int, int]]): A list containing at least three tuples,
                where each tuple `(x, y)` represents the integer coordinates of a
                vertex (corner) of the polygon.
            fill_color (Optional[str]): The color to fill the inside of the polygon.
                If `None`, the polygon is not filled.
            line_color (Optional[str]): The color of the polygon's outline. Uses UI
                default if `None`.
            line_width (Optional[int]): The thickness of the outline in pixels. Must
                be positive. Uses UI default if `None`.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Returns:
            None: This method sends a command and does not return a value.

        Raises:
            ValueError: If `points` contains fewer than three points, or if
                        `line_width` is provided but is not positive.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> # Draw a filled blue triangle
            >>> triangle_points = [(50, 150), (100, 50), (150, 150)]
            >>> canvas.draw_polygon(triangle_points, fill_color='blue')
            >>> # Draw an empty hexagon with a green border
            >>> hex_points = [(200, 100), (230, 80), (260, 100), (260, 130), (230, 150), (200, 130)]
            >>> canvas.draw_polygon(hex_points, line_color='green', line_width=2)
        """
        # Determine target buffer ID
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Validate input points list
        if not isinstance(points, list) or len(points) < 3:
            raise ValueError(f"Canvas '{self.target_id}': draw_polygon requires a list of at least three (x, y) points.")

        # Convert points to the protocol format.
        points_payload = [{"x": p[0], "y": p[1]} for p in points]

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {"bufferId": target_buffer_id, "points": points_payload}
        # Add optional style parameters if provided.
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                 logger.warning(f"Canvas '{self.target_id}': Invalid line_width ({line_width}) provided to draw_polygon. Must be positive. Ignoring.")
                 # Optional: raise ValueError("line_width must be a positive integer.")

        # Send the command.
        self._send_canvas_update("drawPolygon", options)

    def draw_ellipse(self, cx: int, cy: int, radius_x: int, radius_y: int,
                     fill_color: Optional[str] = None,
                     line_color: Optional[str] = None,
                     line_width: Optional[int] = None,
                     buffer_id: Optional[int] = None):
        """Draws an ellipse (or oval) shape on the specified buffer.

        The ellipse is defined by its center coordinates `(cx, cy)` and its
        horizontal (`radius_x`) and vertical (`radius_y`) radii.

        Args:
            cx (int): The x-coordinate of the center of the ellipse.
            cy (int): The y-coordinate of the center of the ellipse.
            radius_x (int): The horizontal radius (half the width) of the ellipse.
                Must be positive.
            radius_y (int): The vertical radius (half the height) of the ellipse.
                Must be positive.
            fill_color (Optional[str]): The color to fill the inside of the ellipse.
                If `None`, the ellipse is not filled.
            line_color (Optional[str]): The color of the ellipse's outline. Uses UI
                default if `None`.
            line_width (Optional[int]): The thickness of the outline in pixels. Must
                be positive. Uses UI default if `None`.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Returns:
            None: This method sends a command and does not return a value.

        Raises:
            ValueError: If `radius_x` or `radius_y` are not positive, or if
                        `line_width` is provided but is not positive.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> # Draw a wide, short, filled red ellipse
            >>> canvas.draw_ellipse(150, 100, 80, 30, fill_color='red')
            >>> # Draw a tall, thin, empty ellipse outline
            >>> canvas.draw_ellipse(50, 150, 20, 60, line_color='black', line_width=1)
        """
        # Determine target buffer ID
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Validate radii
        if not (isinstance(radius_x, (int, float)) and radius_x > 0):
            raise ValueError(f"Canvas '{self.target_id}': draw_ellipse radius_x must be a positive number.")
        if not (isinstance(radius_y, (int, float)) and radius_y > 0):
            raise ValueError(f"Canvas '{self.target_id}': draw_ellipse radius_y must be a positive number.")

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "cx": cx, "cy": cy,
            "radiusX": radius_x, # camelCase key for the protocol
            "radiusY": radius_y  # camelCase key for the protocol
        }
        # Add optional style parameters if provided.
        if fill_color is not None: options["fillColor"] = fill_color
        if line_color is not None: options["lineColor"] = line_color
        if line_width is not None:
            if isinstance(line_width, int) and line_width > 0:
                options["lineWidth"] = line_width
            else:
                 logger.warning(f"Canvas '{self.target_id}': Invalid line_width ({line_width}) provided to draw_ellipse. Must be positive. Ignoring.")
                 # Optional: raise ValueError("line_width must be a positive integer.")

        # Send the command.
        self._send_canvas_update("drawEllipse", options)

    def draw_text(self, x: int, y: int, text: str,
                  text_color: Optional[str] = None,
                  text_size: Optional[int] = None,
                  buffer_id: Optional[int] = None):
        """Draws text (a string) on the specified buffer.

        The `(x, y)` coordinates typically define the starting position of the
        text's baseline (bottom-left for most standard fonts, but the exact
        alignment can depend on the underlying UI implementation).

        Args:
            x (int): The x-coordinate for the starting position of the text.
            y (int): The y-coordinate for the starting position of the text.
            text (str): The text string you want to draw. It will be converted
                to a string if it isn't already.
            text_color (Optional[str]): The color of the text. Accepts CSS color
                formats. Uses the UI's default text color (usually black or white
                depending on theme) if `None`.
            text_size (Optional[int]): The font size in pixels. Must be positive.
                Uses the UI's default font size if `None`.
            buffer_id (Optional[int]): The target buffer ID. Defaults to `None`
                (targets the visible onscreen canvas, ID 0).

        Returns:
            None: This method sends a command and does not return a value.

        Raises:
            ValueError: If `text_size` is provided but is not positive.
            SidekickConnectionError (or subclass): If sending the command fails.

        Example:
            >>> canvas.draw_text(10, 20, "Score: 100")
            >>> canvas.draw_text(50, 80, "Game Over", text_color='red', text_size=24)
        """
        # Determine target buffer ID
        target_buffer_id = buffer_id if buffer_id is not None else self.ONSCREEN_BUFFER_ID

        # Prepare options dictionary with camelCase keys.
        options: Dict[str, Any] = {
            "bufferId": target_buffer_id,
            "x": x, "y": y,
            "text": str(text) # Ensure the text is explicitly converted to a string
        }
        # Add optional style parameters if provided.
        if text_color is not None: options["textColor"] = text_color
        if text_size is not None:
            if isinstance(text_size, int) and text_size > 0:
                options["textSize"] = text_size
            else:
                 logger.warning(f"Canvas '{self.target_id}': Invalid text_size ({text_size}) provided to draw_text. Must be positive. Ignoring.")
                 # Optional: raise ValueError("text_size must be a positive integer.")

        # Send the command.
        self._send_canvas_update("drawText", options)

    # --- Cleanup ---
    def _reset_specific_callbacks(self):
        """Internal: Resets canvas-specific callbacks when the module is removed.

        Called automatically by the base class's `remove()` method.
        """
        self._click_callback = None

    def remove(self):
        """Removes the canvas from the Sidekick UI and cleans up associated resources.

        This performs the following actions:
        1. Sends commands to the Sidekick UI to destroy any offscreen buffers
           that were created for this canvas instance.
        2. Calls the base class `remove()` method, which:
           a. Unregisters internal message handlers for this canvas.
           b. Resets any registered callbacks (`on_click`, `on_error`).
           c. Sends the final 'remove' command to the Sidekick UI to delete
              the main canvas element itself.

        After calling `remove()`, you should no longer interact with this `Canvas` object.

        Returns:
            None: This method initiates removal and does not return a value.

        Raises:
            SidekickConnectionError (or subclass): Can occur if sending the
                'destroyBuffer' or 'remove' commands fails. Cleanup of local
                Python resources (callbacks, handlers) will still be attempted.
        """
        logger.info(f"Requesting removal of canvas '{self.target_id}' and attempting to destroy its associated offscreen buffers.")

        # --- Destroy Offscreen Buffers ---
        # Use a lock for safe access to the buffer pool during removal.
        with self._buffer_lock:
            # Get a list of buffer IDs currently in the pool *before* clearing it.
            # We only need to destroy offscreen buffers (ID > 0).
            buffer_ids_to_destroy = [bid for bid in self._buffer_pool.keys() if bid != self.ONSCREEN_BUFFER_ID]

            # Send a 'destroyBuffer' command for each offscreen buffer.
            for buffer_id in buffer_ids_to_destroy:
                 try:
                     payload = {
                         "action": "destroyBuffer",
                         "options": {"bufferId": buffer_id}, # camelCase key
                     }
                     # Use _send_update directly as it's an update-like command.
                     self._send_update(payload)
                     logger.debug(f"Canvas '{self.target_id}': Sent destroy command for buffer ID {buffer_id}.")
                 except connection.SidekickConnectionError as e:
                     # Log the error but continue trying to remove other buffers and the main canvas.
                     logger.warning(f"Canvas '{self.target_id}': Failed to send destroy command for offscreen buffer {buffer_id} during removal: {e}")

            # Clear the local state of the buffer pool after attempting destruction.
            self._buffer_pool.clear()
            self._next_buffer_id = 1 # Reset the counter

        # --- Call Base Class Removal ---
        # This handles unregistering message handlers, resetting callbacks,
        # and sending the final 'remove' command for the canvas module itself.
        super().remove()

    def __del__(self):
        """Internal: Fallback attempt to clean up resources when the object is garbage collected.

        Warning:
            Relying on `__del__` for cleanup is not recommended in Python, as its
            execution is not guaranteed. **You should always explicitly call the
            `canvas.remove()` method** when you are finished with a canvas instance
            to ensure proper cleanup in the Sidekick UI and the Python library.
            This `__del__` method primarily attempts to call the base class's
            `__del__` for handler unregistration as a safety net.
        """
        try:
            # Call the base class's __del__ to attempt handler unregistration.
            super().__del__()
        except Exception:
            # Suppress errors during __del__ as is standard practice.
            pass