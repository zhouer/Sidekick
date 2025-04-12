import collections.abc
from typing import Any, List, Set, Dict, Callable, Optional, Union, Tuple
from . import logger

# Define type aliases for clarity
SubscriptionCallback = Callable[[Dict[str, Any]], None]
UnsubscribeFunction = Callable[[], None]

class ObservableValue:
    """Wraps a Python value to notify subscribers about changes.

    Use this class to wrap lists, dictionaries, or sets that you want to
    display using the `sidekick.Viz` module. When you modify the wrapped
    object using the `ObservableValue`'s methods (like `.append()`,
    `.[key] = value`, `.add()`, `.set()`), it automatically notifies the `Viz`
    module, which can then update the display in Sidekick efficiently, often
    highlighting the exact change.

    Directly modifying attributes of the *wrapped* object itself (if it's a
    custom object) will *not* trigger notifications. You need to use the
    `ObservableValue` methods or call `.set()` on the `ObservableValue` itself
    if the entire wrapped value needs to be replaced.

    Notifications include details like the type of change ("setitem", "append"),
    the path to the change (e.g., index or key), and the new value.
    """
    _obs_internal_attrs = ('_value', '_subscribers', '_obs_value_id')

    def __init__(self, initial_value: Any):
        """Initializes the ObservableValue with a value to wrap.

        Args:
            initial_value: The Python value (e.g., list, dict, set, primitive)
                to wrap and observe.
        """
        self._value: Any = initial_value
        self._subscribers: Set[SubscriptionCallback] = set()
        # Generate a relatively stable ID based on the observable object itself
        self._obs_value_id: str = f"obs_{id(self)}"

    def subscribe(self, callback: SubscriptionCallback) -> UnsubscribeFunction:
        """Registers a function to be called when the wrapped value changes.

        This is primarily used internally by the `sidekick.Viz` module. You usually
        don't need to call this directly.

        Args:
            callback (SubscriptionCallback): A function that accepts one argument,
                a dictionary containing details about the change.

        Returns:
            UnsubscribeFunction: A function that can be called with no arguments
                to remove this specific callback.

        Raises:
            TypeError: If the provided callback is not callable.
        """
        if not callable(callback):
            raise TypeError("Callback provided to ObservableValue.subscribe must be callable")
        self._subscribers.add(callback)
        # Return an unsubscribe function specific to this callback
        def unsubscribe(): self.unsubscribe(callback)
        return unsubscribe

    def unsubscribe(self, callback: SubscriptionCallback):
        """Removes a previously registered callback function. (Internal use)"""
        self._subscribers.discard(callback)

    def _notify(self, change_details: Dict[str, Any]):
        """Internal method to call all subscribers with change details."""
        if not self._subscribers: return # No subscribers, nothing to do

        # Ensure common keys exist, even if None, for consistent structure
        change_details.setdefault('path', [])
        change_details.setdefault('value', None)
        change_details.setdefault('key', None)
        change_details.setdefault('old_value', None)
        change_details.setdefault('length', None)

        # Copy subscribers in case a callback modifies the set during iteration
        subscribers_to_notify = list(self._subscribers)
        for callback in subscribers_to_notify:
            try:
                callback(change_details)
            except Exception as e:
                # Log error but continue notifying other subscribers
                logger.exception(f"Error in ObservableValue subscriber {callback}: {e}")

    def get(self) -> Any:
        """Returns the current underlying value being wrapped.

        Examples:
            >>> obs_list = ObservableValue([1, 2])
            >>> print(obs_list.get())
            [1, 2]

        Returns:
            Any: The current wrapped value.
        """
        return self._value

    def set(self, new_value: Any):
        """Replaces the entire wrapped value with a new one.

        This triggers a "set" notification to subscribers. Use this when you
        need to replace the whole object (e.g., assign a completely new list
        or dictionary). If the `new_value` provided is the *exact same object*
        in memory as the current one, no notification is sent.

        Args:
            new_value: The new value to wrap.

        Examples:
            >>> obs_data = ObservableValue({"a": 1})
            >>> viz.show("data", obs_data)
            >>> # Replace the entire dictionary
            >>> obs_data.set({"b": 2, "c": 3}) # Sidekick will update the display

        Returns:
            None
        """
        if self._value is not new_value:
            old_value = self._value
            self._value = new_value
            self._notify({
                "type": "set",
                "path": [], # Change applies to the root value
                "value": self._value, # The new value
                "old_value": old_value # The value before the change
            })

    # --- Intercepted Methods for Mutable Containers ---
    # These methods perform the operation on the wrapped value AND notify.

    def append(self, item: Any):
        """Appends an item to the wrapped list/sequence and notifies."""
        if not isinstance(self._value, collections.abc.MutableSequence): raise TypeError("append requires a mutable sequence")
        current_len = len(self._value)
        self._value.append(item)
        self._notify({
            "type": "append",
            "path": [current_len], # Index where item was added
            "value": item,         # The item added
            "length": len(self._value) # New length
        })

    def insert(self, index: int, item: Any):
        """Inserts an item at an index in the wrapped list/sequence and notifies."""
        if not isinstance(self._value, collections.abc.MutableSequence): raise TypeError("insert requires a mutable sequence")
        self._value.insert(index, item)
        self._notify({
            "type": "insert",
            "path": [index],       # Index where item was inserted
            "value": item,         # The item inserted
            "length": len(self._value) # New length
        })

    def pop(self, index: int = -1) -> Any:
        """Removes and returns item at index (default last) from list/sequence and notifies."""
        if not isinstance(self._value, collections.abc.MutableSequence): raise TypeError("pop requires a mutable sequence")
        # Determine actual index for notification before popping
        actual_index = index if index >= 0 else len(self._value) + index
        if not (0 <= actual_index < len(self._value)): raise IndexError("pop index out of range")

        popped_value = self._value.pop(index) # Perform the actual pop
        self._notify({
            "type": "pop",
            "path": [actual_index], # Index from where it was removed
            "value": None,          # No new value associated with pop
            "old_value": popped_value, # The value that was removed
            "length": len(self._value)  # New length
        })
        return popped_value

    def remove(self, value: Any):
         """Removes the first occurrence of value from list/sequence and notifies."""
         if not isinstance(self._value, collections.abc.MutableSequence): raise TypeError("remove requires a mutable sequence")
         try:
             index = self._value.index(value) # Find index first to include in notification
             self._value.remove(value) # Perform the actual removal
             self._notify({
                "type": "remove", # Specific type for removing by value
                "path": [index], # Index where the value was found and removed
                "value": None,
                "old_value": value, # The value that was removed
                "length": len(self._value) # New length
             })
         except ValueError:
            pass # Value not found, standard list behavior, no notification

    def clear(self):
        """Removes all items from the wrapped container (list, dict, set) and notifies."""
        # Check if the wrapped value has a clear method
        clear_method = getattr(self._value, 'clear', None)
        if callable(clear_method):
            old_len = len(self._value) if hasattr(self._value, '__len__') else None
            clear_method() # Call the actual clear method
            self._notify({
                "type": "clear",
                "path": [], # Clearing affects the root container
                "value": self._value, # Send the now empty container state
                "length": 0,
                # "old_length": old_len # Optional: provide old length if needed
            })
        else: raise TypeError(f"Object of type {type(self._value).__name__} has no clear() method")

    def __setitem__(self, key: Any, value: Any):
        """Sets an item/key in the wrapped container (list, dict) and notifies.

        Use standard Python syntax `obs_list[index] = value` or
        `obs_dict[key] = value`. This method intercepts the operation to
        trigger a notification.
        """
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)): raise TypeError("__setitem__ requires a mutable sequence or mapping")
        old_value = None
        is_mapping = isinstance(self._value, collections.abc.MutableMapping)
        try: # Try to get old value if key/index exists
            old_value = self._value[key] # type: ignore
        except (KeyError, IndexError):
            pass # Key/index didn't exist, old_value remains None

        self._value[key] = value # Perform the actual set operation type: ignore
        self._notify({
            "type": "setitem",
            "path": [key], # Path uses the list index or dict key
            "value": value, # The new value being set
            "key": key if is_mapping else None, # Include key only for mappings
            "old_value": old_value # The value that was replaced (or None)
        })

    def __delitem__(self, key: Any):
        """Deletes an item/key from the wrapped container (list, dict) and notifies.

        Use standard Python syntax `del obs_list[index]` or `del obs_dict[key]`.
        """
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)): raise TypeError("__delitem__ requires a mutable sequence or mapping")
        old_value = self._value[key] # Get value before deleting (will raise KeyError/IndexError if not found) type: ignore
        is_mapping = isinstance(self._value, collections.abc.MutableMapping)

        del self._value[key] # Perform the actual delete operation type: ignore
        self._notify({
            "type": "delitem",
            "path": [key], # Path uses the list index or dict key
            "value": None, # No new value associated with delete
            "key": key if is_mapping else None, # Include key only for mappings
            "old_value": old_value, # The value that was deleted
            "length": len(self._value) if hasattr(self._value, '__len__') else None # New length
        })

    def update(self, other: Union[Dict, collections.abc.Mapping] = {}, **kwargs):
        """Updates the wrapped dictionary, triggering notifications for each change.

        Works like the standard dictionary `update()` method but ensures that
        each key-value pair addition or modification triggers an individual
        "setitem" notification.
        """
        if not isinstance(self._value, collections.abc.MutableMapping): raise TypeError("update requires a mutable mapping")
        # Merge sources
        merged_updates = dict(other)
        merged_updates.update(kwargs)
        # Iterate and call __setitem__ for each key to trigger notification
        for key, value in merged_updates.items():
            self[key] = value # Calls our intercepted __setitem__

    def add(self, element: Any):
        """Adds an element to the wrapped set and notifies if changed."""
        if not isinstance(self._value, collections.abc.MutableSet): raise TypeError("add requires a mutable set")
        # Check if element is already present *before* adding
        if element not in self._value:
            self._value.add(element) # Perform the actual add
            self._notify({
                "type": "add_set",
                "path": [], # Set operations don't have a simple path
                "value": element, # The element added
                "length": len(self._value) # New length
            })

    def discard(self, element: Any):
         """Removes an element from the wrapped set if present and notifies."""
         if not isinstance(self._value, collections.abc.MutableSet): raise TypeError("discard requires a mutable set")
         # Check if element is present *before* discarding
         if element in self._value:
            self._value.discard(element) # Perform the actual discard
            self._notify({
                "type": "discard_set",
                "path": [], # Set operations don't have a simple path
                "value": None,
                "old_value": element, # The element removed
                "length": len(self._value) # New length
            })

    # --- Standard Dunder Methods (Delegation) ---
    # These methods try to behave like the wrapped value for common operations.

    def __getattr__(self, name: str) -> Any:
        """Delegates attribute access to the wrapped value."""
        # Prevent accessing internal ObservableValue attributes via delegation
        if name in ObservableValue._obs_internal_attrs:
             raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        # Delegate to the wrapped value
        return getattr(self._value, name)

    def __setattr__(self, name: str, value: Any):
        """Sets internal attributes or delegates to the wrapped value."""
        # Handle internal attributes directly
        if name in ObservableValue._obs_internal_attrs:
            object.__setattr__(self, name, value)
        else:
            # Delegate attribute setting to the wrapped value
            # Automatic notification for this is generally discouraged/complex.
            # If notification is needed for wrapped object attribute changes,
            # use .set() on the ObservableValue or ensure the wrapped object
            # itself implements some notification mechanism.
            setattr(self._value, name, value)

    def __repr__(self) -> str:
        """Returns a string representation like `ObservableValue(...)`."""
        return f"ObservableValue({repr(self._value)})"

    def __str__(self) -> str:
        """Returns the string representation of the wrapped value."""
        return str(self._value)

    def __eq__(self, other):
        """Compares the wrapped value for equality."""
        if isinstance(other, ObservableValue):
            return self._value == other._value
        return self._value == other

    def __len__(self) -> int:
        """Returns the length of the wrapped value (if it has one)."""
        # Delegate len() to the wrapped value if supported
        if hasattr(self._value, '__len__'):
            return len(self._value) # type: ignore
        raise TypeError(f"Object of type '{type(self._value).__name__}' has no len()")

    def __getitem__(self, key: Any) -> Any:
        """Allows accessing items/keys of the wrapped value using `[]`."""
        # Delegate getitem[] to the wrapped value if supported
        if isinstance(self._value, (collections.abc.Sequence, collections.abc.Mapping)):
             return self._value[key] # type: ignore
        raise TypeError(f"'{type(self._value).__name__}' object is not subscriptable")

    def __iter__(self):
        """Allows iterating over the wrapped value."""
        # Delegate iteration to the wrapped value if supported
        if hasattr(self._value, '__iter__'):
            return iter(self._value) # type: ignore
        raise TypeError(f"'{type(self._value).__name__}' object is not iterable")

    def __contains__(self, item: Any) -> bool:
        """Allows using the `in` operator on the wrapped value."""
        # Delegate 'in' operator to the wrapped value if supported
        if hasattr(self._value, '__contains__'):
            return item in self._value # type: ignore
        # Fallback: Iterate if possible but no __contains__ (less efficient)
        if hasattr(self._value, '__iter__'):
             for element in self._value: # type: ignore
                 if element == item: return True
             return False
        raise TypeError(f"Argument of type '{type(self._value).__name__}' is not iterable")