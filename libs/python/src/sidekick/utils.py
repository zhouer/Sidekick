# Sidekick/libs/python/src/sidekick/utils.py
import uuid

_instance_counter = 0

def generate_unique_id(prefix: str) -> str:
    """Generates a unique ID for a module instance."""
    global _instance_counter
    _instance_counter += 1
    # Simple counter for now, UUID might be better for robustness
    # return f"{prefix}-{uuid.uuid4().hex[:6]}"
    return f"{prefix}-{_instance_counter}"
