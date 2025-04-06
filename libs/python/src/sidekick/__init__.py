# Sidekick/libs/python/src/sidekick/__init__.py

"""
Sidekick Visual Coding Buddy - Python Client Library
"""

# --- Version ---
from ._version import __version__

# --- Core connection/config functions ---
from .connection import (
    set_url,
    set_config,
    close_connection,
    activate_connection,
    clear_all,
    register_global_message_handler
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
    # Observable
    'ObservableValue',
    # Modules
    'Grid',
    'Console',
    'Control',
    'Viz',
    'Canvas',
]