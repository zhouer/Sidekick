"""Sidekick Python Library (`sidekick-py`).

Welcome to the Sidekick Python library! This is your starting point for
connecting your Python code to the Sidekick visual coding buddy, which typically
runs inside the Visual Studio Code editor or as a standalone web application.

Sidekick helps you **see your code come alive**. Instead of just imagining what
loops are doing or how data structures change, you can use this library to create
visual representations and interactive elements directly within the Sidekick panel.

Key functionalities include creating interactive visual components, managing their
layout, handling UI events, and visualizing data structures in real-time.
The library is designed to be beginner-friendly with a synchronous-style API
for CPython users, while also supporting asynchronous operations for more
advanced use cases, especially in Pyodide environments.

Getting Started:

    1.  **Install:** `pip install sidekick-py`.
    2.  **Setup Sidekick UI:**

        *   **VS Code (Recommended):** Install the "Sidekick - Your Visual Coding Buddy"
            extension from the VS Code Marketplace (search for `sidekick-coding`).
            Then, open the Sidekick panel using `Ctrl+Shift+P` (or `Cmd+Shift+P`
            on macOS) and searching for `Sidekick: Show Panel`.
        *   **Remote/Cloud:** If not using the VS Code extension, your script might
            connect to a remote Sidekick server. If so, the library will print
            a UI URL to open in your browser.

    3.  **Import:** Start your script with `import sidekick`.
    4.  **Create Components:** E.g., `label = sidekick.Label("Hello!")`.
        Component creation is non-blocking. The connection to a Sidekick service
        (local or remote) activates implicitly when the first component is created
        or an explicit connection function like `sidekick.activate_connection()`
        is called. `activate_connection()` itself is non-blocking.
    5.  **Wait for Connection (CPython, Optional but Recommended before interaction):**
        If you need to ensure the connection is active before proceeding with
        operations that immediately require UI interaction in CPython, you can use
        `sidekick.wait_for_connection()`. This function will block until
        the connection is established or fails.
    6.  **Handle Interactivity:** Use `sidekick.run_forever()` (for CPython) or
        `await sidekick.run_forever_async()` (for Pyodide/async) at the end of
        your script if you need to process UI events like button clicks.
        `run_forever()` and `run_forever_async()` will internally wait for
        the connection to be established before proceeding.
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
# Example application setup:
# import logging
# logging.basicConfig(level=logging.DEBUG) # Or another level
# sidekick_logger = logging.getLogger("sidekick")
# # Optionally set a specific level for sidekick logs:
# # sidekick_logger.setLevel(logging.INFO)
logger = logging.getLogger("sidekick")
if not logger.hasHandlers():
    logger.addHandler(logging.NullHandler())

# --- Core connection/configuration/lifecycle functions ---
# These are the primary functions for managing the Sidekick service connection.
# They are wrappers around the ConnectionService singleton.
from .connection import (
    set_url,                      # Set a specific WebSocket server URL, bypassing defaults.
    activate_connection,          # Non-blocking: Ensures connection activation is initiated.
    wait_for_connection,          # New: (CPython) Blocks until connection is active or fails.
    clear_all,                    # Remove all components from the Sidekick UI.
    register_global_message_handler, # Advanced: Handle *all* incoming raw messages.
    run_forever,                  # Keep script running (CPython), waits for connection first.
    run_forever_async,            # Keep script running (async), waits for connection first.
    shutdown,                     # Gracefully close the connection to Sidekick.
    submit_interval,              # Submits a function to be called repeatedly at a specified interval.
    submit_task                   # Submit a user coroutine to Sidekick's event loop.
)
# Note: Internal methods like `send_message_internally` from connection.py are not re-exported.

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
    'wait_for_connection',
    'clear_all',
    'register_global_message_handler',
    'run_forever',
    'run_forever_async',
    'shutdown',
    'submit_interval',
    'submit_task',

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
