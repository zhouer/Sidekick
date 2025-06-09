"""Core utility functions for the Sidekick library's underlying infrastructure.

This module provides helper functions that are used by other modules within
the `sidekick.core` sub-package. These utilities are generally low-level
and support the fundamental operations of the core components.
"""

import sys
from functools import lru_cache

@lru_cache(maxsize=1)
def is_pyodide() -> bool:
    """Checks if the Python code is currently running in a Pyodide environment.

    This function determines the execution environment by checking common indicators
    associated with Pyodide, such as the presence of the 'pyodide' module or
    the 'sys.platform' value being 'emscripten'.

    The result is cached after the first call for efficiency.

    Returns:
        bool: True if the environment is detected as Pyodide, False otherwise.

    Example:
        >>> from sidekick.core.utils import is_pyodide
        >>> if is_pyodide():
        ...     print("Running in Pyodide!")
        ... else:
        ...     print("Running in a standard CPython environment (or similar).")
    """
    # Method 1: Check sys.platform
    # Pyodide sets sys.platform to "emscripten".
    if sys.platform == "emscripten":
        return True

    # Method 2: Try importing the 'pyodide' module
    # This is a strong indicator.
    try:
        import pyodide # type: ignore[import-not-found,import-untyped]
        # If the import succeeds, we are very likely in Pyodide.
        # We can even do a quick check on a known pyodide object if needed,
        # but the import itself is usually sufficient.
        # For example: from pyodide.ffi import IN_WORKER (if always available)
        return True
    except ImportError:
        # 'pyodide' module is not available.
        pass

    # Method 3: Check for JavaScript context (less direct for pure Python utility)
    # Sometimes, `js` module is available.
    try:
        import js # type: ignore[import-not-found]
        # Check for a global object that Pyodide typically exposes, e.g., 'self.pyodide'.
        # This is more of a heuristic and might be less reliable than the other checks.
        if hasattr(js.globalThis, 'pyodide'):
            return True # pragma: no cover (less common path, harder to test reliably in all CIs)
    except ImportError:
        pass # 'js' module not available.
    except Exception: # pragma: no cover
        pass # Catch any other errors from js access

    return False
