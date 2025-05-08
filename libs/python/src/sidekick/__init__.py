"""Sidekick Python Library (`sidekick-py`).

Welcome to the Sidekick Python library! This is your starting point for
connecting your Python code to the Sidekick visual coding buddy, which typically
runs inside the Visual Studio Code editor or as a standalone web application
using Pyodide.

Sidekick helps you **see your code come alive**. Instead of just imagining what
loops are doing or how data structures change, you can use this library to create
visual representations and interactive elements directly within the Sidekick panel.

What can you do with it?
    *   Create interactive grids (`sidekick.Grid`).
    *   Display text output and get user input (`sidekick.Console`).
    *   Visualize variable changes automatically (`sidekick.Viz`, `sidekick.ObservableValue`).
    *   Draw shapes, lines, and text (`sidekick.Canvas`).
    *   Display static or dynamic text labels (`sidekick.Label`).
    *   Add clickable buttons to trigger actions (`sidekick.Button`).
    *   Get single-line text input from users (`sidekick.Textbox`).
    *   Render formatted text using Markdown (`sidekick.Markdown`).
    *   Arrange components horizontally or vertically (`sidekick.Row`, `sidekick.Column`).

These visual components update in real-time as your Python code executes, making it
easier to understand, debug, demonstrate, and share programming concepts and simple applications.

Getting Started:
    1.  **Install:** `pip install sidekick-py`. Ensure the Sidekick VS Code
        extension is installed OR you are running in a compatible web environment (like Pyodide).
    2.  **Open Panel (VS Code):** Use `Ctrl+Shift+P`, search for `Sidekick: Show Panel`.
    3.  **Import:** Start your script with `import sidekick`.
    4.  **Create Components:** Instantiate components, e.g., `label = sidekick.Label("Hello!")`.
        Connection happens automatically on first component creation.
    5.  **Specify Layout:**
        *   Use the `parent` parameter: `button = sidekick.Button("OK", parent=my_row)`
        *   Use container methods: `my_row.add_child(button)`
        *   Pass children to container constructors: `my_row = sidekick.Row(button1, label1)`
    6.  **Set Callbacks:** Define component behavior using:
        *   Constructor parameters: `btn = sidekick.Button("Run", on_click=run_func)`
        *   Methods: `btn.on_click(run_func)`
        *   Decorators: `@btn.click\ndef run_func(): ...`
    7.  **Interact:** Update components via properties/methods, e.g., `label.text = "World"`.
    8.  **Keep Alive (for interactivity):** Use `sidekick.run_forever()` at the end
        of your script if you need to handle UI events (clicks, submits). Stop with
        Ctrl+C or call `sidekick.shutdown()` from a callback.

Happy visual coding!
"""

import logging

# --- Version ---
from ._version import __version__

# --- Logging Setup ---
# Set up a logger named "sidekick". By default, it has a NullHandler,
# meaning log messages won't be output unless the user configures
# logging in their own script (e.g., using logging.basicConfig).
logger = logging.getLogger("sidekick")
if not logger.hasHandlers():
    logger.addHandler(logging.NullHandler())
# Example user configuration (in their script):
# import logging
# logging.basicConfig(level=logging.DEBUG) # Or logging.INFO
# --- End Logging Setup ---


# --- Core connection/configuration/lifecycle functions ---
# These functions control the overall connection and state.
from .connection import (
    set_url,                      # Set the WebSocket server URL before connecting.
    # activate_connection,        # Internal use, ensures connection is ready.
    clear_all,                    # Remove all components from the Sidekick UI.
    register_global_message_handler, # Advanced: Handle *all* incoming messages.
    run_forever,                  # Keep the script running to handle UI events.
    shutdown,                     # Gracefully close the connection.
)

# --- Import custom exception classes ---
# These help users catch specific connection problems.
from .errors import (
    SidekickConnectionError,        # Base class for connection issues.
    SidekickConnectionRefusedError, # Failed initial connection attempt.
    SidekickTimeoutError,           # UI didn't signal readiness in time.
    SidekickDisconnectedError,      # Connection lost after being established.
)

# --- Core observable class for reactive UI updates ---
# Use this with Viz for automatic UI updates on data changes.
from .observable_value import ObservableValue

# --- Standard Component Classes ---
# These are the building blocks for your Sidekick UI.
from .grid import Grid                   # Interactive 2D grid of cells.
from .console import Console             # Text output and optional input.
from .viz import Viz                     # Visualize Python variables.
from .canvas import Canvas               # 2D drawing surface.
from .label import Label                 # Simple text display.
from .button import Button               # Clickable button.
from .textbox import Textbox             # Single-line text input.
from .markdown import Markdown           # Render Markdown formatted text.

# --- Layout Container Classes ---
# Use these to arrange other components.
from .row import Row                     # Arranges children horizontally.
from .column import Column               # Arranges children vertically.


# --- __all__ Definition ---
# This explicitly defines the public API of the 'sidekick' package
# when using `from sidekick import *`. It helps keep the namespace clean
# and provides clarity on what users are intended to interact with directly.
__all__ = [
    # Version
    '__version__',

    # Config/Connection/Lifecycle
    'set_url',
    'clear_all',
    'register_global_message_handler',
    'run_forever',
    'shutdown',

    # Observable Value (for Viz reactivity)
    'ObservableValue',

    # Components
    'Button',
    'Canvas',
    'Console',
    'Grid',
    'Label',
    'Markdown',
    'Textbox',
    'Viz',

    # Layout Containers
    'Row',
    'Column',

    # Logger (allow users to access/configure if needed)
    'logger',

    # Errors
    'SidekickConnectionError',
    'SidekickConnectionRefusedError',
    'SidekickTimeoutError',
    'SidekickDisconnectedError',

    # Note: Does not include internal implementation details like BaseComponent,
    # connection module functions (except the public ones listed above),
    # utility functions, or specific channel implementations.
]