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
    4.  **Create:** Instantiate components, e.g., `label = sidekick.Label("Hello!")`.
        Connection happens automatically. Specify `parent=container` to nest elements.
    5.  **Interact:** Use component methods/properties, e.g., `label.text = "World"`.
    6.  **Listen (if needed):** Use `on_click`, `on_submit`, etc., and keep your
        script running with `sidekick.run_forever()` to handle UI events. Stop with Ctrl+C
        or `sidekick.shutdown()`.

Happy visual coding!
"""

import logging

# --- Version ---
from ._version import __version__

# --- Logging Setup ---
logger = logging.getLogger("sidekick")
if not logger.hasHandlers():
    logger.addHandler(logging.NullHandler())
# --- End Logging Setup ---


# --- Core connection/configuration/lifecycle functions ---
from .connection import (
    set_url,
    # activate_connection, # Generally internal
    clear_all,
    register_global_message_handler,
    run_forever,
    shutdown,
)

# --- Import custom exception classes ---
from .errors import (
    SidekickConnectionError,
    SidekickConnectionRefusedError,
    SidekickTimeoutError,
    SidekickDisconnectedError,
)

# --- Core observable class for reactive UI updates ---
from .observable_value import ObservableValue

# --- Original Component Classes ---
from .grid import Grid
from .console import Console
from .viz import Viz
from .canvas import Canvas

# --- New Component Classes ---
from .label import Label
from .button import Button
from .textbox import Textbox
from .markdown import Markdown

# --- New Layout Container Classes ---
from .row import Row
from .column import Column


# --- __all__ Definition ---
# Controls `from sidekick import *` behavior.
__all__ = [
    # Version
    '__version__',
    # Config/Connection/Lifecycle
    'set_url',
    'clear_all',
    'register_global_message_handler',
    'run_forever',
    'shutdown',
    # Observable
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
    # Logger
    'logger',
    # Errors
    'SidekickConnectionError',
    'SidekickConnectionRefusedError',
    'SidekickTimeoutError',
    'SidekickDisconnectedError',
    # Does not include internal implementation details like BaseComponent, connection module etc.
]