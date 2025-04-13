"""
Sidekick Python Library (`sidekick-py`)

This is the main package for the Sidekick Python library. It allows your Python
scripts to connect to and control the Sidekick visualization panel, typically
running inside VS Code.

You can use this library to create interactive visuals like grids, display
text in a console, inspect variables, draw on a canvas, and add UI controls,
all updated in real-time as your Python code runs.

Start by importing the `sidekick` package:

    import sidekick

Then, create instances of visual modules like `sidekick.Grid()` or
`sidekick.Console()`.

Core concepts include:
  - Creating module instances (e.g., `grid = sidekick.Grid()`).
  - Updating module state (e.g., `grid.set_color(0, 0, 'red')`).
  - Handling events from Sidekick (e.g., `grid.on_click(my_handler)`).
  - Managing the script lifecycle (`sidekick.run_forever()`, `sidekick.shutdown()`).
"""

import logging

# --- Version ---
from ._version import __version__

# --- Logging Setup ---
# Define the main logger for the library
logger = logging.getLogger("sidekick")

# Add NullHandler to prevent "No handlers found" warnings if the
# application doesn't configure logging. This should be done only
# once per library.
if not logger.hasHandlers():
    logger.addHandler(logging.NullHandler())
# --- End Logging Setup ---


# --- Core connection/config functions ---
from .connection import (
    set_url,
    set_config,
    close_connection,
    activate_connection,
    clear_all,
    register_global_message_handler,
    ensure_ready,
    run_forever,
    flush_messages,
    shutdown,
)

# --- Core observable class ---
from .observable_value import ObservableValue

# --- Module classes ---
from .grid import Grid
from .console import Console
from .viz import Viz
from .canvas import Canvas
from .control import Control

# Explicitly define __all__ for clarity and controlling imports
__all__ = [
    # Version
    '__version__',
    # Config/Connection
    'set_url',
    'set_config',
    'close_connection',
    'activate_connection',
    'clear_all',
    'register_global_message_handler',
    'ensure_ready',
    'run_forever',
    'flush_messages',
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
]