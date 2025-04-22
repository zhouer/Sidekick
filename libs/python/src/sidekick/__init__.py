"""Sidekick Python Library (`sidekick-py`).

Welcome to the Sidekick Python library! This is your starting point for
connecting your Python code to the Sidekick visual coding buddy, which typically
runs inside the Visual Studio Code editor.

Sidekick helps you **see your code come alive**. Instead of just imagining what
loops are doing or how data structures change, you can use this library to create
visual representations and interactive elements directly within the Sidekick panel
in VS Code.

What can you do with it?
    *   Create interactive grids for maps, games, or data display (`sidekick.Grid`).
    *   Show text output like `print()`, but in a dedicated Sidekick area, and
        even get text input back from the user (`sidekick.Console`).
    *   Visualize your variables (lists, dictionaries, objects) and see how they
        change over time, automatically (`sidekick.Viz` with `sidekick.ObservableValue`).
    *   Draw shapes, lines, and text on a 2D canvas (`sidekick.Canvas`).
    *   Add clickable buttons and text input fields to trigger actions in your
        Python script (`sidekick.Control`).

These visual modules update in real-time as your Python code executes, making it
easier to understand, debug, and demonstrate programming concepts.

Getting Started:
    1.  **Install:** Make sure you have `sidekick-py` installed (`pip install sidekick-py`)
        and the Sidekick VS Code extension is installed and enabled.
    2.  **Open Panel:** In VS Code, open the Sidekick panel (Ctrl+Shift+P, search for
        `Sidekick: Show Panel`).
    3.  **Import:** Start your Python script with `import sidekick`.
    4.  **Create:** Instantiate a visual module, e.g., `grid = sidekick.Grid(5, 5)`.
        The connection to Sidekick happens automatically here!
    5.  **Interact:** Use the module's methods, e.g., `grid.set_color(0, 0, 'blue')`.
    6.  **Listen (if needed):** If you need to react to user clicks or input
        (using methods like `grid.on_click(...)`), you must keep your script
        running. Add `sidekick.run_forever()` at the end of your script. You can
        stop it by pressing Ctrl+C in the terminal.

Happy visual coding!
"""

import logging

# --- Version ---
# Import the version number defined in _version.py so users can access it.
from ._version import __version__

# --- Logging Setup ---
# Set up the main logger for the 'sidekick' library.
# This allows users of the library to easily control the log output level
# (e.g., show detailed debug messages) by configuring this logger in their script.
logger = logging.getLogger("sidekick")

# Add a default NullHandler if no handlers are already configured by the user.
# This prevents the common "No handlers could be found for logger 'sidekick'"
# warning if the user's script doesn't explicitly configure logging.
# Log messages will simply be discarded unless the user adds their own handlers
# (e.g., via logging.basicConfig()).
if not logger.hasHandlers():
    logger.addHandler(logging.NullHandler())
# --- End Logging Setup ---


# --- Core connection/configuration/lifecycle functions ---
# These functions manage the underlying WebSocket connection to the Sidekick UI
# and allow for basic configuration and script lifecycle control.
from .connection import (
    set_url,                          # Set the WebSocket URL (call before connecting).
    set_config,                       # Configure connection behavior (call before connecting).
    # close_connection is mostly internal, prefer shutdown()
    activate_connection,              # Ensures connection is ready (blocks if not, called implicitly).
    clear_all,                        # Clears all UI elements created by this script in Sidekick.
    register_global_message_handler,  # Advanced: Listen to *all* incoming messages (for debugging).
    run_forever,                      # Keeps the script alive to handle UI events (clicks, input).
    shutdown,                         # Cleanly disconnects from Sidekick.
    # Exception classes users might need to catch
    SidekickConnectionError,          # Base class for all Sidekick connection errors.
    SidekickConnectionRefusedError,   # Raised on initial connection failure (server not found/reachable?).
    SidekickTimeoutError,             # Raised if connected to server, but Sidekick UI doesn't respond in time.
    SidekickDisconnectedError,        # Raised if the connection is lost *after* being established.
)

# --- Core observable class for reactive UI updates ---
# Used primarily with sidekick.Viz for automatic display updates when data changes.
from .observable_value import ObservableValue

# --- Main module classes ---
# These are the primary classes users interact with to create visual elements.
from .grid import Grid
from .console import Console
from .viz import Viz
from .canvas import Canvas
from .control import Control

# --- __all__ Definition ---
# Define what symbols are imported when a user does `from sidekick import *`.
# It's generally recommended for users to import the main package (`import sidekick`)
# or specific classes (`from sidekick import Grid, Console`), but this list
# controls the behavior of wildcard imports.
__all__ = [
    # Version
    '__version__',
    # Config/Connection/Lifecycle
    'set_url',
    'set_config',
    'clear_all',
    'register_global_message_handler',
    'run_forever',
    'shutdown',
    # Observable
    'ObservableValue',
    # Modules
    'Grid',
    'Console',
    'Control',
    'Viz',
    'Canvas',
    # Logger (for users who want to configure it)
    'logger',
    # Errors (for users who want to catch them)
    'SidekickConnectionError',
    'SidekickConnectionRefusedError',
    'SidekickTimeoutError',
    'SidekickDisconnectedError',
    # Does not include internal connection functions like `activate_connection` or utility functions.
]