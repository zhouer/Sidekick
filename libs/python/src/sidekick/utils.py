# Sidekick/libs/python/src/sidekick/utils.py
import uuid

_instance_counter = 0

def generate_unique_id(prefix: str) -> str:
    """
    Generates a unique ID for a module instance using a simple counter.
    Format: prefix-counter
    """
    global _instance_counter
    _instance_counter += 1
    return f"{prefix}-{_instance_counter}"

def generate_peer_id() -> str:
    """
    Generates a unique peer ID for the Hero instance using UUID.
    Format: hero-<uuid_hex>
    """
    return f"hero-{uuid.uuid4().hex}"