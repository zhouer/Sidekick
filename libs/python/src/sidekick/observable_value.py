# Sidekick/libs/python/src/sidekick/observable_value.py
import collections.abc
from typing import Any, List, Set, Dict, Callable, Optional, Union

# Type hint for the callback function subscribers provide
# It receives the new value as an argument
SubscriptionCallback = Callable[[Any], None]
UnsubscribeFunction = Callable[[], None]

class ObservableValue:
    """
    Wraps a Python value, allowing external subscribers to be notified
    when the internal value changes.

    For immutable types, changes are made via the `.set()` method.
    For mutable containers (list, dict, set), common mutating methods
    are intercepted to trigger notifications automatically.
    """
    # Attributes starting with _obs are internal to the wrapper
    _obs_internal_attrs = ('_value', '_subscribers', '_obs_value_id')

    def __init__(self, initial_value: Any):
        self._value: Any = initial_value
        # Use a set for efficient addition/removal of subscribers
        self._subscribers: Set[SubscriptionCallback] = set()
        # Basic ID for the observable instance itself
        self._obs_value_id: str = f"obs_{id(self)}"

    # --- Subscription Management ---

    def subscribe(self, callback: SubscriptionCallback) -> UnsubscribeFunction:
        """Registers a callback function to be called when the value changes.

        Args:
            callback: The function to call with the new value.

        Returns:
            A function that can be called to unsubscribe the callback.
        """
        if not callable(callback):
            raise TypeError("Callback must be callable")
        self._subscribers.add(callback)

        # Return an unsubscribe function using a closure
        def unsubscribe():
            self.unsubscribe(callback)

        return unsubscribe

    def unsubscribe(self, callback: SubscriptionCallback):
        """Removes a previously registered callback."""
        self._subscribers.discard(callback) # Use discard to avoid error if not found

    def _notify(self):
        """Calls all registered subscribers with the current internal value."""
        # Create a copy in case a callback modifies the set during iteration
        subscribers_to_notify = list(self._subscribers)
        for callback in subscribers_to_notify:
            try:
                # Pass the *current* internal value to the callback
                callback(self._value)
            except Exception as e:
                # Log or handle callback errors appropriately?
                # For now, just print an error and continue notifying others
                print(f"Error in ObservableValue subscriber {callback}: {e}")

    # --- Value Management ---

    def get(self) -> Any:
        """Returns the current internal value."""
        return self._value

    def set(self, new_value: Any):
        """
        Explicitly sets the internal value. Required for changing immutable types
        or completely replacing the wrapped value. Triggers notification.
        """
        if self._value is not new_value: # Basic check to avoid notify if value is identical object
             self._value = new_value
             self._notify()

    # --- Attribute Access (Delegation) ---

    def __getattr__(self, name: str) -> Any:
        if name in ObservableValue._obs_internal_attrs:
             raise AttributeError(f"'{type(self).__name__}' accessing internal attribute '{name}'")
        return getattr(self._value, name)

    def __setattr__(self, name: str, value: Any):
        if name in ObservableValue._obs_internal_attrs:
            object.__setattr__(self, name, value)
        else:
            # Setting attributes on the *wrapped* object usually requires
            # calling .set() on the ObservableValue or re-showing it in Viz,
            # as we don't generally notify on delegated setattr.
            setattr(self._value, name, value)
            # If automatic notification on *any* setattr was desired (use cautiously):
            # self._notify()

    def __delattr__(self, name: str):
         if name in ObservableValue._obs_internal_attrs:
              raise AttributeError(f"Cannot delete internal attribute '{name}'")
         else:
              delattr(self._value, name)
              # If automatic notification on delattr was desired:
              # self._notify()

    # --- Container Emulation Methods (Intercepted for Notifications) ---
    # These methods modify the internal `_value` AND call `_notify()`

    # List/MutableSequence methods
    def append(self, item: Any):
        if not isinstance(self._value, collections.abc.MutableSequence):
            raise TypeError(f"Cannot 'append' to non-sequence type: {type(self._value).__name__}")
        self._value.append(item)
        self._notify() # Notify after modification

    def insert(self, index: int, item: Any):
         if not isinstance(self._value, collections.abc.MutableSequence):
            raise TypeError(f"Cannot 'insert' into non-sequence type: {type(self._value).__name__}")
         self._value.insert(index, item)
         self._notify()

    def pop(self, index: int = -1) -> Any:
        if not isinstance(self._value, collections.abc.MutableSequence):
            raise TypeError(f"Cannot 'pop' from non-sequence type: {type(self._value).__name__}")
        popped_value = self._value.pop(index)
        self._notify()
        return popped_value

    def remove(self, value: Any):
         if not isinstance(self._value, collections.abc.MutableSequence):
            raise TypeError(f"Cannot 'remove' from non-sequence type: {type(self._value).__name__}")
         self._value.remove(value) # Raises ValueError if not found (standard behavior)
         self._notify()

    def clear(self):
        if callable(getattr(self._value, 'clear', None)):
            self._value.clear()
            self._notify()
        else:
             raise TypeError(f"Wrapped type {type(self._value).__name__} does not support 'clear'")

    def __setitem__(self, key: Any, value: Any):
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)):
             raise TypeError(f"Cannot set item on non-sequence/mapping type: {type(self._value).__name__}")
        self._value[key] = value # type: ignore
        self._notify()

    def __delitem__(self, key: Any):
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)):
             raise TypeError(f"Cannot delete item from non-sequence/mapping type: {type(self._value).__name__}")
        del self._value[key] # type: ignore
        self._notify()

    # --- Dict/MutableMapping specific methods ---
    def update(self, other: Union[Dict, collections.abc.Mapping], **kwargs):
        if not isinstance(self._value, collections.abc.MutableMapping):
             raise TypeError(f"Cannot 'update' non-mapping type: {type(self._value).__name__}")
        self._value.update(other, **kwargs)
        self._notify()

    # --- Set/MutableSet specific methods ---
    def add(self, element: Any):
        if not isinstance(self._value, collections.abc.MutableSet):
            raise TypeError(f"Cannot 'add' to non-set type: {type(self._value).__name__}")
        # Only notify if the set actually changes size
        len_before = len(self._value)
        self._value.add(element)
        if len(self._value) != len_before:
            self._notify()

    def discard(self, element: Any):
         if not isinstance(self._value, collections.abc.MutableSet):
            raise TypeError(f"Cannot 'discard' from non-set type: {type(self._value).__name__}")
         # Only notify if the element was actually present
         if element in self._value:
            self._value.discard(element)
            self._notify()

    # --- Generic Accessor methods ---
    def __getitem__(self, key: Any) -> Any:
        if not isinstance(self._value, (collections.abc.Sequence, collections.abc.Mapping)):
            raise TypeError(f"Wrapped type {type(self._value).__name__} does not support getitem")
        return self._value[key] # type: ignore

    def __len__(self) -> int:
        if not hasattr(self._value, '__len__'):
             raise TypeError(f"Wrapped type {type(self._value).__name__} does not support len()")
        return len(self._value)

    def __iter__(self):
        if not hasattr(self._value, '__iter__'):
            raise TypeError(f"Wrapped type {type(self._value).__name__} does not support iteration")
        return iter(self._value)

    def __contains__(self, item: Any) -> bool:
        if not hasattr(self._value, '__contains__'):
            raise TypeError(f"Wrapped type {type(self._value).__name__} does not support 'in' operator")
        return item in self._value

    def __repr__(self) -> str:
        return f"ObservableValue({repr(self._value)})"

    def __str__(self) -> str:
        return str(self._value)

    def __eq__(self, other):
        # Compare based on the wrapped value if comparing to another ObservableValue or raw value
        if isinstance(other, ObservableValue):
            return self._value == other._value
        return self._value == other

    # Consider __hash__ if needed, but only if _value is hashable and immutable
    # def __hash__(self):
    #     if not isinstance(self._value, collections.abc.Hashable):
    #         raise TypeError(f"Unhaashable type wrapped in ObservableValue: {type(self._value).__name__}")
    #     return hash(self._value)