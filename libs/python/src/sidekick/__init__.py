# Sidekick/libs/python/src/sidekick/__init__.py

"""
Sidekick Visual Coding Buddy - Python Client Library
"""

__version__ = "0.1.0"

# Core connection functions
from .connection import set_url, close_connection

# Core observable class
from .observable_value import ObservableValue

# Module classes
from .grid import Grid
from .console import Console
from .viz import Viz
from .canvas import Canvas
from .control import Control

# Explicitly define __all__ for clarity
__all__ = [
    'set_url',
    'close_connection',
    'ObservableValue',
    'Grid',
    'Console',
    'Control',
    'Viz',
    'Canvas',
]