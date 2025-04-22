"""Internal Utility Functions for the Sidekick Library.

This module contains helper functions used internally by other parts of the
Sidekick library.

Warning:
    Functions and variables in this module are considered internal implementation
    details. You should not need to import or use them directly in your scripts,
    as they might change without notice in future versions.
"""

# A simple counter shared across the library instance to help generate unique IDs.
_instance_counter = 0

def generate_unique_id(prefix: str) -> str:
    """Generates a simple, sequential unique ID for a module instance.

    This function is used internally by Sidekick module classes (like `Grid`,
    `Console`, etc.) when you create an instance without providing your own specific
    `instance_id`. It ensures that each automatically generated ID is unique
    within the current script run, helping the library distinguish between
    different modules of the same type (e.g., multiple Grids).

    The generated IDs follow a simple "prefix-number" format (e.g., "grid-1",
    "console-2").

    Note:
        This is intended for internal library use. You should not rely on the
        specific format of these generated IDs in your code, as it could change.
        Always use the `target_id` attribute of a module instance if you need
        to reference its ID.

    Args:
        prefix (str): A descriptive prefix indicating the type of module,
            such as "grid", "console", or "canvas".

    Returns:
        str: A unique identifier string for the new instance (e.g., "grid-1").
    """
    # Use the global counter to ensure uniqueness across calls within the script.
    global _instance_counter
    _instance_counter += 1
    return f"{prefix}-{_instance_counter}"