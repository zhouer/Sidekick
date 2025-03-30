# Sidekick/libs/python/src/sidekick/observable_value.py
import collections.abc
from typing import Any, List, Set, Dict, Callable, Optional, Union, Tuple

# Callback now receives details about the change
# change_details keys: 'type', 'path', 'value', 'key', 'old_value', 'length'
SubscriptionCallback = Callable[[Dict[str, Any]], None]
UnsubscribeFunction = Callable[[], None]

class ObservableValue:
    """
    Wraps a Python value, allowing external subscribers to be notified
    with details about how the internal value changes.
    """
    _obs_internal_attrs = ('_value', '_subscribers', '_obs_value_id')

    def __init__(self, initial_value: Any):
        self._value: Any = initial_value
        self._subscribers: Set[SubscriptionCallback] = set()
        self._obs_value_id: str = f"obs_{id(self)}"

    def subscribe(self, callback: SubscriptionCallback) -> UnsubscribeFunction:
        if not callable(callback):
            raise TypeError("Callback must be callable")
        self._subscribers.add(callback)
        def unsubscribe(): self.unsubscribe(callback)
        return unsubscribe

    def unsubscribe(self, callback: SubscriptionCallback):
        self._subscribers.discard(callback)

    def _notify(self, change_details: Dict[str, Any]):
        """Calls registered subscribers with details about the change."""
        if not self._subscribers: return # Optimization

        # Ensure basic fields exist, even if None
        change_details.setdefault('path', [])
        change_details.setdefault('value', None)
        change_details.setdefault('key', None)
        change_details.setdefault('old_value', None) # Optional info
        change_details.setdefault('length', None)

        subscribers_to_notify = list(self._subscribers)
        for callback in subscribers_to_notify:
            try:
                callback(change_details)
            except Exception as e:
                print(f"Error in ObservableValue subscriber {callback}: {e}")

    def get(self) -> Any:
        return self._value

    def set(self, new_value: Any):
        """Explicitly sets the internal value. Triggers 'set' notification."""
        if self._value is not new_value: # Avoid notification if identical object
            old_value = self._value
            self._value = new_value
            self._notify({
                "type": "set",
                "path": [], # Root path
                "value": self._value,
                "old_value": old_value
            })

    # --- Intercepted Methods ---

    def append(self, item: Any):
        if not isinstance(self._value, collections.abc.MutableSequence): raise TypeError("...")
        current_len = len(self._value)
        self._value.append(item)
        self._notify({
            "type": "append",
            "path": [current_len], # Path is the index where it was added
            "value": item,
            "length": len(self._value)
        })

    def insert(self, index: int, item: Any):
        if not isinstance(self._value, collections.abc.MutableSequence): raise TypeError("...")
        self._value.insert(index, item)
        self._notify({
            "type": "insert", # Consider if frontend needs specific 'insert' or treats as 'setitem'/'append' conceptually
            "path": [index],
            "value": item,
            "length": len(self._value)
            # Note: 'insert' shifts subsequent indices, complex for frontend to track without full replace?
            # Maybe simplify: treat insert like a full 'set' for now? Or send specific 'insert' type. Let's try 'insert'.
        })

    def pop(self, index: int = -1) -> Any:
        if not isinstance(self._value, collections.abc.MutableSequence): raise TypeError("...")
        # Normalize index before popping
        actual_index = index if index >= 0 else len(self._value) + index
        if not (0 <= actual_index < len(self._value)): raise IndexError("pop index out of range")

        popped_value = self._value.pop(index)
        self._notify({
            "type": "pop",
            "path": [actual_index], # Path is the index from where it was removed
            "value": None, # No new value
            "old_value": popped_value,
            "length": len(self._value)
        })
        return popped_value

    def remove(self, value: Any):
         if not isinstance(self._value, collections.abc.MutableSequence): raise TypeError("...")
         try:
             index = self._value.index(value) # Find index first
             self._value.remove(value) # standard behavior raises ValueError if not found
             self._notify({
                "type": "remove", # Specific type for removing by value
                "path": [index], # Path is the index where it was found
                "value": None,
                "old_value": value,
                "length": len(self._value)
             })
         except ValueError:
            pass # Value not found, do nothing, no notification

    def clear(self):
        if callable(getattr(self._value, 'clear', None)):
            # Need to know type for path/value info if needed
            was_mapping = isinstance(self._value, collections.abc.MutableMapping)
            was_set = isinstance(self._value, collections.abc.MutableSet)
            was_sequence = isinstance(self._value, collections.abc.MutableSequence)
            old_len = len(self._value) if hasattr(self._value, '__len__') else None

            self._value.clear()
            self._notify({
                "type": "clear",
                "path": [], # Clearing affects the root
                "value": self._value, # Send the now empty container
                "length": 0,
                "old_length": old_len # Maybe useful context
            })
        else: raise TypeError("...")

    def __setitem__(self, key: Any, value: Any):
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)): raise TypeError("...")
        old_value = None
        if isinstance(self._value, collections.abc.MutableSequence):
             if not isinstance(key, int): raise TypeError("List index must be int")
             if 0 <= key < len(self._value): old_value = self._value[key]
        elif isinstance(self._value, collections.abc.MutableMapping):
             old_value = self._value.get(key) # Get old value if key exists

        self._value[key] = value # type: ignore
        self._notify({
            "type": "setitem",
            "path": [key], # Path is the index/key
            "value": value,
            "key": key if isinstance(self._value, collections.abc.MutableMapping) else None, # Include key for dicts
            "old_value": old_value
        })

    def __delitem__(self, key: Any):
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)): raise TypeError("...")
        old_value = None
        is_mapping = isinstance(self._value, collections.abc.MutableMapping)
        if isinstance(self._value, collections.abc.MutableSequence):
             if not isinstance(key, int): raise TypeError("List index must be int")
             actual_index = key if key >= 0 else len(self._value) + key
             if not (0 <= actual_index < len(self._value)): raise IndexError("delitem index out of range")
             old_value = self._value[actual_index]
             path_key = actual_index
        elif is_mapping:
             if key not in self._value: raise KeyError(key)
             old_value = self._value[key]
             path_key = key
        else: raise TypeError("Unsupported type for delitem") # Should not happen

        del self._value[key] # type: ignore
        self._notify({
            "type": "delitem",
            "path": [path_key],
            "value": None, # No new value
            "key": path_key if is_mapping else None,
            "old_value": old_value,
            "length": len(self._value) if hasattr(self._value, '__len__') else None
        })

    def update(self, other: Union[Dict, collections.abc.Mapping], **kwargs):
        if not isinstance(self._value, collections.abc.MutableMapping): raise TypeError("...")
        # To send granular updates for 'update', we'd need to compare before/after
        # For simplicity now, treat 'update' as a full 'set' notification
        temp_dict = dict(other)
        temp_dict.update(kwargs)
        if not temp_dict: return # No changes if update source is empty

        # Option 1: Simple - Send whole value (less granular)
        # old_value = self._value.copy() # Snapshot before update
        # self._value.update(other, **kwargs)
        # self._notify({"type": "set", "path": [], "value": self._value, "old_value": old_value})

        # Option 2: Granular - Send individual setitem notifications (more complex, potentially many messages)
        merged_updates = dict(other)
        merged_updates.update(kwargs)
        for key, value in merged_updates.items():
            # Call our own __setitem__ to trigger individual notifications
             self[key] = value

    def add(self, element: Any):
        if not isinstance(self._value, collections.abc.MutableSet): raise TypeError("...")
        if element not in self._value:
            self._value.add(element)
            self._notify({
                "type": "add_set",
                "path": [], # Set changes don't have a simple path like list/dict index/key
                "value": element, # The element added
                "length": len(self._value)
            })

    def discard(self, element: Any):
         if not isinstance(self._value, collections.abc.MutableSet): raise TypeError("...")
         if element in self._value:
            self._value.discard(element)
            self._notify({
                "type": "discard_set",
                "path": [],
                "value": None,
                "old_value": element, # The element removed
                "length": len(self._value)
            })

    # --- Standard delegation ---
    def __getattr__(self, name: str) -> Any:
        if name in ObservableValue._obs_internal_attrs: raise AttributeError(...)
        # Attribute access on wrapped object *doesn't* trigger notifications by default
        return getattr(self._value, name)

    def __setattr__(self, name: str, value: Any):
        if name in ObservableValue._obs_internal_attrs:
            object.__setattr__(self, name, value)
        else:
            # To notify on wrapped object attribute changes, you'd need
            # manual notification or a more complex proxy. For now, no notification.
            setattr(self._value, name, value)
            # If you wanted notification (use carefully):
            # self._notify({"type": "setattr", "path": [name], "value": value})

    # ... (other dunder methods like __getitem__, __len__, __iter__, __repr__, __eq__ remain largely the same) ...
    # Update __repr__ if desired
    def __repr__(self) -> str:
        return f"ObservableValue({repr(self._value)})"

    def __str__(self) -> str:
        return str(self._value)

    def __eq__(self, other):
        if isinstance(other, ObservableValue): return self._value == other._value
        return self._value == other

    def __len__(self) -> int:
        if not hasattr(self._value, '__len__'): raise TypeError(...)
        return len(self._value)

    def __getitem__(self, key: Any) -> Any:
        if not isinstance(self._value, (collections.abc.Sequence, collections.abc.Mapping)): raise TypeError(...)
        return self._value[key] # type: ignore

    def __iter__(self):
         if not hasattr(self._value, '__iter__'): raise TypeError(...)
         return iter(self._value)

    def __contains__(self, item: Any) -> bool:
         if not hasattr(self._value, '__contains__'): raise TypeError(...)
         return item in self._value