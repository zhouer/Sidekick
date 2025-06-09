"""Internal Utility Functions for the Sidekick Library.

This module contains helper functions used internally by other parts of the
Sidekick library.

Warning:
    Functions and variables in this module are considered internal implementation
    details. You should not need to import or use them directly in your scripts,
    as they might change without notice in future versions.
"""

import random
import os
import json
import platform
from typing import Optional

# A simple counter shared across the library instance to help generate unique IDs.
_instance_counter = 0

def generate_unique_id(prefix: str) -> str:
    """Generates a simple, sequential unique ID for a component instance.

    This function is used internally by Sidekick component classes (like `Grid`,
    `Console`, etc.) when you create an instance without providing your own specific
    `instance_id`. It ensures that each automatically generated ID is unique
    within the current script run, helping the library distinguish between
    different components of the same type (e.g., multiple Grids).

    The generated IDs follow a simple "prefix-number" format (e.g., "grid-1",
    "console-2").

    Note:
        This is intended for internal library use. You should not rely on the
        specific format of these generated IDs in your code, as it could change.
        Always use the `instance_id` attribute of a component instance if you need
        to reference its ID.

    Args:
        prefix (str): A descriptive prefix indicating the type of component,
            such as "grid", "console", or "canvas".

    Returns:
        str: A unique identifier string for the new instance (e.g., "grid-1").
    """
    # Use the global counter to ensure uniqueness across calls within the script.
    global _instance_counter
    _instance_counter += 1
    return f"{prefix}-{_instance_counter}"

PKG_NAME = "sidekick"
SESSION_ID_LENGTH = 8
SESSION_FILENAME = "session_info.json"

def _generate_random_id() -> str:
    """
    Generates a random ID with the length specified by SESSION_ID_LENGTH.

    Returns:
        str: A random numeric ID as a string.
    """
    min_val = 10**(SESSION_ID_LENGTH - 1)
    max_val = (10**SESSION_ID_LENGTH) - 1
    return str(random.randint(min_val, max_val))

def _get_app_data_dir() -> Optional[str]:
    """Gets the appropriate application data directory based on the OS.

    Returns None if a standard directory cannot be determined.
    """
    system = platform.system()
    base_dir = None
    if system == "Windows":
        base_dir = os.environ.get("APPDATA")
        if not base_dir: # Fallback if APPDATA is not set
            base_dir = os.path.expanduser("~\\AppData\\Local")
    elif system == "Darwin": # macOS
        base_dir = os.path.expanduser("~/Library/Application Support")
    else: # Linux and other Unix-like
        base_dir = os.environ.get("XDG_DATA_HOME")
        if not base_dir: # Fallback if XDG_DATA_HOME is not set
            base_dir = os.path.expanduser("~/.local/share")

    if not base_dir:
        # Fallback: if no standard directory could be determined.
        # Signal to generate_session_id to not use persistent storage.
        return None

    app_data_dir = os.path.join(base_dir, PKG_NAME)
    return app_data_dir

def generate_session_id() -> str:
    """
    Generates a session ID.

    It tries to load an existing session ID from a file in the user's
    application data directory. If a standard directory cannot be determined,
    or if the ID is not found, it generates a new ID.

    If a standard app data directory isn't found, the generated ID is transient
    and not saved to disk. Otherwise, it saves the new ID to disk and returns it.
    """
    app_data_dir = _get_app_data_dir()

    # If app_data_dir is None, it means we should use a transient session ID
    # and skip all file operations.
    if app_data_dir is None:
        return _generate_random_id()

    # Try to load existing session ID
    session_file_path = os.path.join(app_data_dir, SESSION_FILENAME)
    if os.path.exists(session_file_path):
        try:
            with open(session_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            session_id = data.get('session_id')

            # Ensure session_id is not None
            if session_id is not None:
                return str(session_id) # Return as string
        except (IOError, json.JSONDecodeError, TypeError, ValueError):
            # Errors in reading/parsing are treated as if the file is invalid/absent.
            # A new session ID will be generated.
            pass

    # Generate the new session ID
    new_session_id = _generate_random_id()
    session_data = {
        'session_id': new_session_id
    }

    # Save the new session ID
    try:
        os.makedirs(app_data_dir, exist_ok=True)
        with open(session_file_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f)
    except IOError:
        # If saving fails, the app still gets a session ID for the current run.
        # It just won't persist for the next run.
        # Optionally, log this error if a logging facility is available.
        pass

    return new_session_id
