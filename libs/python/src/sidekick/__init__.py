"""Sidekick Python Library (`sidekick-py`).

Welcome to the Sidekick Python library! This is your starting point for
connecting your Python code to the Sidekick visual coding buddy, which typically
runs inside the Visual Studio Code editor or as a standalone web application
using Pyodide.

Sidekick helps you **see your code come alive**. Instead of just imagining what
loops are doing or how data structures change, you can use this library to create
visual representations and interactive elements directly within the Sidekick panel.

Key functionalities include creating interactive visual components, managing their
layout, handling UI events, and visualizing data structures in real-time.
The library is designed to be beginner-friendly with a synchronous-style API,
while also supporting asynchronous operations for more advanced use cases,
especially in Pyodide environments.

Getting Started:
    1.  **Install:** `pip install sidekick-py`. Ensure the Sidekick VS Code
        extension is installed OR you are running in a compatible web environment.
    2.  **Open Panel (VS Code):** Use `Ctrl+Shift+P`, search for `Sidekick: Show Panel`.
    3.  **Import:** Start your script with `import sidekick`.
    4.  **Create Components:** E.g., `label = sidekick.Label("Hello!")`.
        The connection to the Sidekick service activates implicitly on first use.
    5.  **Handle Interactivity:** Use `sidekick.run_forever()` (for CPython) or
        `await sidekick.run_forever_async()` (for Pyodide/async) at the end of
        your script if you need to process UI events like button clicks.
        Stop with Ctrl+C or by calling `sidekick.shutdown()` from a callback.

Happy visual coding!
"""

import logging

# --- Version ---
from ._version import __version__

# --- Logging Setup ---
# Configure a logger for the 'sidekick' package.
# By default, it uses a NullHandler, so applications using this library
# must configure their own logging if they wish to see Sidekick logs.
logger = logging.getLogger("sidekick")
if not logger.hasHandlers():
    logger.addHandler(logging.NullHandler())

# --- Core connection/configuration/lifecycle functions ---
# These are the primary functions for managing the Sidekick service connection.
# They are wrappers around the ConnectionService singleton.
from .connection import (
    set_url,                      # Set the WebSocket server URL before connecting.
    activate_connection,          # Explicitly activate the connection (usually implicit).
    clear_all,                    # Remove all components from the Sidekick UI.
    register_global_message_handler, # Advanced: Handle *all* incoming raw messages.
    run_forever,                  # Keep the script running (blocks main thread in CPython).
    run_forever_async,            # Keep the script running (awaits in async context).
    shutdown,                     # Gracefully close the connection to Sidekick.
    submit_task                   # Submit a user coroutine to Sidekick's event loop.
)
# Note: `send_message`, `register_message_handler`, `unregister_message_handler`
# from connection.py are primarily for internal use by Component and not re-exported here.

# --- Import custom application-level exception classes ---
# Users can catch these to handle Sidekick-specific errors.
from .exceptions import (
    SidekickError,                  # Base class for all Sidekick application errors.
    SidekickConnectionError,        # Base class for Sidekick connection issues.
    SidekickConnectionRefusedError, # Failed initial connection attempt to Sidekick service.
    SidekickTimeoutError,           # Operation timed out (e.g., waiting for UI readiness).
    SidekickDisconnectedError,      # Connection to Sidekick service lost after establishment.
)

# --- Core observable class for reactive UI updates with Viz ---
from .observable_value import ObservableValue

# --- Event classes for structured callbacks from UI components ---
from .events import (
    BaseSidekickEvent,    # Base class for all Sidekick UI events.
    ButtonClickEvent,     # Event for Button clicks.
    GridClickEvent,       # Event for Grid cell clicks.
    CanvasClickEvent,     # Event for Canvas clicks.
    TextboxSubmitEvent,   # Event for Textbox submissions.
    ConsoleSubmitEvent,   # Event for Console input submissions.
    ErrorEvent,           # Event for errors reported by a UI component.
)

# --- Standard Component Classes (UI building blocks) ---
from .grid import Grid
from .console import Console
from .viz import Viz
from .canvas import Canvas
from .label import Label
from .button import Button
from .textbox import Textbox
from .markdown import Markdown

# --- Layout Container Classes (for arranging components) ---
from .row import Row
from .column import Column


# --- __all__ Definition ---
# Explicitly defines the public API of the 'sidekick' package
# for `from sidekick import *`. It's good practice, though direct imports
# (e.g., `from sidekick import Button`) are generally preferred.
__all__ = [
    # Version
    '__version__',

    # Logger (for users who might want to configure it)
    'logger',

    # Config/Connection/Lifecycle
    'set_url',
    'activate_connection',
    'clear_all',
    'register_global_message_handler',
    'run_forever',
    'run_forever_async', # New
    'shutdown',
    'submit_task',       # New

    # Observable Value (for Viz reactivity)
    'ObservableValue',

    # Event Classes
    'BaseSidekickEvent',
    'ButtonClickEvent',
    'GridClickEvent',
    'CanvasClickEvent',
    'TextboxSubmitEvent',
    'ConsoleSubmitEvent',
    'ErrorEvent',

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

    # Error Classes
    'SidekickError',
    'SidekickConnectionError',
    'SidekickConnectionRefusedError',
    'SidekickTimeoutError',
    'SidekickDisconnectedError',
]