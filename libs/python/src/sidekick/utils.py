_instance_counter = 0

def generate_unique_id(prefix: str) -> str:
    """Generates a simple unique ID for a module instance. (Internal use)

    Creates IDs like "grid-1", "console-2", etc. Used when an `instance_id`
    is not provided by the user during module initialization.

    Args:
        prefix (str): The module type prefix (e.g., "grid", "console").

    Returns:
        str: A unique ID string for the instance.
    """
    global _instance_counter
    _instance_counter += 1
    return f"{prefix}-{_instance_counter}"
