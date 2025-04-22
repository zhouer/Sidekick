"""
Sidekick Python Library (`sidekick-py`).

This is the main entry point for the Sidekick Python library! You'll typically
start by importing this package to connect your Python scripts to the visual
Sidekick panel, which usually runs inside Visual Studio Code.

With this library, you can:
- Create interactive grids (`sidekick.Grid`).
- Display text output and get user input (`sidekick.Console`).
- Inspect your variables and how they change (`sidekick.Viz`).
- Draw shapes on a canvas (`sidekick.Canvas`).
- Add buttons and input fields (`sidekick.Control`).

All these visual elements appear in the Sidekick panel and update in real-time
as your Python code runs.

Getting Started:
1. Make sure the Sidekick VS Code extension is installed and the panel is open.
2. Import the library: `import sidekick`
3. Create visual elements: `grid = sidekick.Grid(5, 5)`
4. Control them: `grid.set_color(0, 0, 'red')`
5. If you need to handle clicks or input, keep your script alive: `sidekick.run_forever()`

Happy visual coding!
"""

import logging

# --- Version ---
# Import the version number defined in _version.py
from ._version import __version__

# --- Logging Setup ---
# Set up the main logger for the 'sidekick' library.
# This allows users of the library to easily control the log output
# (e.g., show detailed debug messages) by configuring this logger.
logger = logging.getLogger("sidekick")

# Add a default NullHandler. This prevents the "No handlers could be found
# for logger 'sidekick'" warning if the user's script doesn't configure
# logging explicitly. It means log messages won't go anywhere by default,
# but the user *can* add their own handlers if they want to see the logs.
if not logger.hasHandlers():
    logger.addHandler(logging.NullHandler())
# --- End Logging Setup ---


# --- Core connection/config functions ---
# These functions manage the underlying connection to the Sidekick UI
# and allow for basic configuration.
from .connection import (
    set_url,                          # Set the WebSocket URL (call before connecting).
    set_config,                       # Configure connection behavior (call before connecting).
    close_connection,                 # (Mostly internal) Closes the connection immediately.
    activate_connection,              # Ensures connection is ready (blocks if not).
    clear_all,                        # Clears all UI elements in Sidekick.
    register_global_message_handler,  # Advanced: Listen to *all* incoming messages.
    run_forever,                      # Keeps the script alive to handle UI events.
    shutdown,                         # Cleanly disconnects from Sidekick.
    SidekickConnectionError,          # Base class for all Sidekick connection errors. Catch this for any connection issue.
    SidekickConnectionRefusedError,   # Raised on initial connection failure (server not found/reachable, panel not open?).
    SidekickTimeoutError,             # Raised if connected to server, but Sidekick UI panel doesn't signal readiness in time.
    SidekickDisconnectedError,        # Raised if the connection is lost *after* being successfully established.
)

# --- Core observable class ---
# Used with sidekick.Viz for reactive updates.
from .observable_value import ObservableValue

# --- Module classes ---
# These are the main classes you'll use to create visual elements.
from .grid import Grid
from .console import Console
from .viz import Viz
from .canvas import Canvas
from .control import Control

# Define what gets imported when a user does `from sidekick import *`.
# It's generally better to import specific things (like `import sidekick`
# or `from sidekick import Grid`), but this list controls the wildcard import.
__all__ = [
    # Version
    '__version__',
    # Config/Connection
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
    # Logger
    'logger',
    # Errors
    'SidekickConnectionError',
    'SidekickConnectionRefusedError',
    'SidekickTimeoutError',
    'SidekickDisconnectedError',
]