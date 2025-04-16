"""
Internal Utility Functions for the Sidekick Library.

This module contains helper functions that are used by other parts of the
Sidekick library behind the scenes. You typically won't need to use these
functions directly in your own scripts.
"""

# A simple counter to help generate unique IDs.
_instance_counter = 0

def generate_unique_id(prefix: str) -> str:
    """Generates a simple, sequential unique ID for a module instance.

    This is used internally when you create a Sidekick module (like a Grid
    or Console) without providing your own specific `instance_id`. It helps
    the library distinguish between different modules of the same type.

    The generated IDs look like "grid-1", "console-2", etc.

    Note:
        This is intended for internal library use. Relying on the exact format
        of these generated IDs is not recommended.

    Args:
        prefix (str): A string indicating the type of module, like "grid"
            or "console".

    Returns:
        str: A unique identifier string for the new instance.
    """
    global _instance_counter
    _instance_counter += 1
    return f"{prefix}-{_instance_counter}"