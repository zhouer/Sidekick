"""
Provides the ObservableValue class for reactive Sidekick visualizations.

This module contains the `ObservableValue` class. You can think of it as a
special wrapper or container that you put around your regular Python data
(like lists, dictionaries, or sets).

The main purpose of `ObservableValue` is to work seamlessly with the
`sidekick.Viz` module. When you display an `ObservableValue` in the Viz panel:
`viz.show("my_data", sidekick.ObservableValue([1, 2]))`

...and then modify the data *using the wrapper's methods*:
`my_data.append(3)` or `my_data[0] = 10`

...the `ObservableValue` automatically tells the `Viz` panel *exactly* what changed.
This allows the Viz panel in Sidekick to update its display efficiently, often
highlighting the specific change, making it much easier to see how your data
evolves over time without needing to call `viz.show()` repeatedly.

Use this when you want the variable display in Sidekick (`Viz` module) to
automatically react to changes in your Python lists, dictionaries, or sets.
"""

import collections.abc # Used for checking mutable types like list, dict, set
from typing import Any, List, Set, Dict, Callable, Optional, Union, Tuple, Iterable, Mapping
from . import logger

# Type Aliases for clarity
# A function that receives details about a change.
SubscriptionCallback = Callable[[Dict[str, Any]], None]
# A function that, when called, stops a subscription.
UnsubscribeFunction = Callable[[], None]

class ObservableValue:
    """Wraps a Python value (list, dict, set) to notify subscribers about changes.

    Use this class to make your data "reactive" when displayed in the Sidekick
    `Viz` panel. Wrap your mutable data structures (lists, dictionaries, sets)
    in an `ObservableValue`:

    `my_list = sidekick.ObservableValue([1, 2])`
    `my_dict = sidekick.ObservableValue({'a': 1})`
    `my_set = sidekick.ObservableValue({10, 20})`

    Then, when you display them using `viz.show("data", my_list)`, the Viz panel
    will automatically update when you modify the data *through the wrapper*.
    For example:

    - `my_list.append(3)`   -> Notifies Viz about the append.
    - `my_list[0] = 100`    -> Notifies Viz about the item set.
    - `my_dict['b'] = 2`    -> Notifies Viz about the item set.
    - `my_dict.update({'c': 3})` -> Notifies Viz about the update.
    - `my_set.add(30)`      -> Notifies Viz about the addition.
    - `del my_list[1]`      -> Notifies Viz about the item deletion.

    You can also replace the entire wrapped value using `.set(new_value)`, which
    also triggers a notification.

    **Important Limitations:**
    - It primarily works by intercepting common methods (`append`, `__setitem__`, etc.)
      of standard Python lists, dicts, and sets. It might not automatically detect
      changes made through less common methods or if you modify the internal
      structure of nested objects *without* going through the `ObservableValue` wrapper.
    - If you wrap a custom object, changes made by directly setting attributes
      on the *wrapped object* (e.g., `my_obs_obj.get().some_attribute = 5`)
      will **not** be automatically detected. You would need to call
      `my_obs_obj.set(my_obs_obj.get())` or trigger a notification manually if
      the object had such a mechanism, or re-wrap mutable attributes within
      the object with their own `ObservableValue`.

    The notifications sent include details like the type of change ("setitem",
    "append", "add_set", etc.), the path to the change within the structure
    (e.g., list index, dict key), and the involved values.
    """
    # --- Internal Attributes ---
    # Define names of internal attributes used by ObservableValue itself.
    # This helps __getattr__ and __setattr__ distinguish between internal state
    # and attributes of the wrapped value.
    _obs_internal_attrs = ('_value', '_subscribers', '_obs_value_id')

    def __init__(self, initial_value: Any):
        """Initializes the ObservableValue by wrapping the given value.

        Args:
            initial_value: The Python value (e.g., list, dict, set, primitive)
                that you want to observe for changes.
        """
        # The actual Python value being wrapped.
        self._value: Any = initial_value
        # A set to store callback functions that should be notified on changes.
        self._subscribers: Set[SubscriptionCallback] = set()
        # A relatively stable internal ID used by Viz to track this specific
        # observable instance across updates. Based on the memory ID of the wrapper.
        self._obs_value_id: str = f"obs_{id(self)}"

    # --- Subscription Management (Mostly internal use by Viz) ---

    def subscribe(self, callback: SubscriptionCallback) -> UnsubscribeFunction:
        """Registers a function to be called whenever the wrapped value changes.

        This is primarily used internally by the `sidekick.Viz` module to listen
        for changes. You typically don't need to call this directly yourself.

        When a change occurs (e.g., via `append()`, `__setitem__()`), the
        `callback` function provided here will be executed with a dictionary
        containing details about that specific change.

        Args:
            callback: A function that accepts one argument: a dictionary
                describing the change event (keys like 'type', 'path', 'value').

        Returns:
            A function that, when called with no arguments, will remove this
            specific `callback` from the subscription list. This allows `Viz`
            to clean up its listeners when a variable is removed or replaced.

        Raises:
            TypeError: If the provided `callback` is not a callable function.
        """
        if not callable(callback):
            raise TypeError("Callback provided to ObservableValue.subscribe must be callable")
        # Add the callback function to the set of subscribers.
        self._subscribers.add(callback)
        logger.debug(f"Subscribed callback {callback} to ObservableValue (id: {self._obs_value_id})")

        # Create and return a specific function to unsubscribe *this* callback.
        def unsubscribe():
            self.unsubscribe(callback)
        return unsubscribe

    def unsubscribe(self, callback: SubscriptionCallback):
        """Removes a previously registered callback function. (Internal use).

        Called by the `unsubscribe` function returned from `subscribe`, or
        directly by `Viz` during cleanup in some cases.

        Args:
            callback: The specific callback function to remove.
        """
        # Safely remove the callback if it's present. `discard` doesn't
        # raise an error if the callback is already gone.
        self._subscribers.discard(callback)
        logger.debug(f"Unsubscribed callback {callback} from ObservableValue (id: {self._obs_value_id})")

    def _notify(self, change_details: Dict[str, Any]):
        """Internal method to inform all subscribers about a change.

        This method is called by the intercepted methods (like `append`, `set`, etc.)
        after a modification has been made to the wrapped value. It iterates
        through all registered `_subscribers` and calls each one with the
        `change_details`.

        Args:
            change_details (Dict[str, Any]): A dictionary containing information
                about the change that occurred (e.g., 'type', 'path', 'value', 'key').
                This dictionary is passed directly to the subscriber callbacks.
        """
        # If no one is listening, don't bother doing anything.
        if not self._subscribers:
            return

        # Ensure common keys exist in the details for consistent structure,
        # even if their value is None for a particular change type.
        change_details.setdefault('path', [])
        change_details.setdefault('value', None) # New value involved
        change_details.setdefault('key', None)   # Key involved (for dicts)
        change_details.setdefault('old_value', None) # Old value (if replaced/removed)
        change_details.setdefault('length', None)    # New length (for collections)

        logger.debug(f"Notifying {len(self._subscribers)} subscribers for ObservableValue (id: {self._obs_value_id}): {change_details}")

        # Copy the set of subscribers before iterating. This prevents issues if a
        # callback function itself tries to subscribe or unsubscribe during notification.
        subscribers_to_notify = list(self._subscribers)
        for callback in subscribers_to_notify:
            try:
                # Call the subscriber function with the change details.
                callback(change_details)
            except Exception as e:
                # Log errors in subscriber callbacks but continue notifying others.
                # Avoids one faulty subscriber breaking updates for others.
                logger.exception(f"Error in ObservableValue subscriber {callback}: {e}")

    # --- Accessing and Replacing the Wrapped Value ---

    def get(self) -> Any:
        """Returns the current underlying Python value being wrapped.

        Use this if you need direct access to the original list, dict, set, etc.,
        without the ObservableValue wrapper.

        Returns:
            The actual Python object stored inside the wrapper.

        Examples:
            >>> obs_list = sidekick.ObservableValue([10, 20])
            >>> raw_list = obs_list.get()
            >>> print(raw_list)
            [10, 20]
            >>> print(isinstance(raw_list, list))
            True
        """
        return self._value

    def set(self, new_value: Any):
        """Replaces the entire wrapped value with a completely new value.

        This is used when you want to assign a totally different object (like a
        new list or dictionary) to this observable variable, rather than just
        modifying the existing one.

        It triggers a "set" notification to subscribers, indicating that the
        entire value has been replaced.

        Note:
            If the `new_value` you provide is the *exact same object* in memory
            as the currently wrapped value (`new_value is self._value`), no
            notification will be sent, as the value hasn't actually changed.

        Args:
            new_value: The new Python object to wrap and observe.

        Returns:
            None

        Examples:
            >>> obs_data = sidekick.ObservableValue({"a": 1})
            >>> viz.show("data", obs_data)
            >>>
            >>> # Replace the whole dictionary
            >>> new_dict = {"b": 2, "c": 3}
            >>> obs_data.set(new_dict) # Viz panel updates to show the new dictionary
            >>>
            >>> # Subsequent changes to new_dict through obs_data will notify
            >>> obs_data['d'] = 4
        """
        # Only notify if the new value is actually different from the old one.
        if self._value is not new_value:
            old_value = self._value # Keep track of the old value for the notification
            self._value = new_value # Update the internal reference
            self._notify({
                "type": "set",        # Type of change: wholesale replacement
                "path": [],           # Change affects the root value (empty path)
                "value": self._value, # The new value now being wrapped
                "old_value": old_value # The value that was just replaced
            })

    # --- Intercepted Methods for Mutable Containers ---
    # These methods mimic the standard list/dict/set methods but add a call
    # to self._notify() after performing the operation.

    # --- List/Sequence Methods ---

    def append(self, item: Any):
        """Appends an item to the end of the wrapped list/sequence and notifies subscribers.

        Requires the wrapped value to be a mutable sequence (like a `list`).

        Raises:
            TypeError: If the wrapped value is not a list or similar mutable sequence.
        """
        if not isinstance(self._value, collections.abc.MutableSequence):
            raise TypeError("ObservableValue: append() requires the wrapped value to be a mutable sequence (e.g., list).")
        # Get the index where the item will be added (current length)
        current_len = len(self._value)
        # Perform the actual append operation on the wrapped list.
        self._value.append(item)
        # Notify subscribers about the change.
        self._notify({
            "type": "append",
            "path": [current_len],      # Path is the index of the new item
            "value": item,              # The item that was added
            "length": len(self._value)  # The new length of the list
        })

    def insert(self, index: int, item: Any):
        """Inserts an item at a specific index in the wrapped list/sequence and notifies."""
        if not isinstance(self._value, collections.abc.MutableSequence):
            raise TypeError("ObservableValue: insert() requires a mutable sequence.")
        # Perform the actual insert.
        self._value.insert(index, item)
        # Notify subscribers.
        self._notify({
            "type": "insert",
            "path": [index],            # Path is the index where inserted
            "value": item,              # The item inserted
            "length": len(self._value)   # The new length
        })

    def pop(self, index: int = -1) -> Any:
        """Removes and returns the item at the given index (default last) and notifies."""
        if not isinstance(self._value, collections.abc.MutableSequence):
            raise TypeError("ObservableValue: pop() requires a mutable sequence.")

        # Calculate the actual index being popped (handling negative indices)
        # to report it correctly before the list shrinks.
        try:
            list_len = len(self._value)
            if list_len == 0: raise IndexError("pop from empty list")
            actual_index = index if index >= 0 else list_len + index
            if not (0 <= actual_index < list_len): raise IndexError("pop index out of range")
        except IndexError as e:
            logger.error(f"ObservableValue: Error calculating pop index: {e}")
            raise # Re-raise the original error

        # Perform the actual pop, getting the removed value.
        popped_value = self._value.pop(index)
        # Notify subscribers.
        self._notify({
            "type": "pop",
            "path": [actual_index],   # Index from where item was removed
            "value": None,            # No *new* value associated with pop
            "old_value": popped_value, # The value that was removed
            "length": len(self._value) # The new length
        })
        return popped_value # Return the popped value like standard pop()

    def remove(self, value: Any):
         """Removes the first occurrence of a given value from the list/sequence and notifies."""
         if not isinstance(self._value, collections.abc.MutableSequence):
             raise TypeError("ObservableValue: remove() requires a mutable sequence.")
         try:
             # Find the index *before* removing, so we can report it.
             index = self._value.index(value)
             # Perform the actual removal.
             self._value.remove(value)
             # Notify subscribers.
             self._notify({
                "type": "remove", # Specific type for removing by value
                "path": [index],       # Index where the value was found
                "value": None,         # No new value
                "old_value": value,    # The value that was removed
                "length": len(self._value) # The new length
             })
         except ValueError:
            # Value wasn't found - standard list behavior is to do nothing.
            # So, we also do nothing and send no notification.
            pass

    def clear(self):
        """Removes all items from the wrapped container (list, dict, set) and notifies."""
        # Check if the wrapped value actually *has* a 'clear' method.
        clear_method = getattr(self._value, 'clear', None)
        if not callable(clear_method):
            raise TypeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} has no clear() method.")

        # Get old length (if possible) before clearing
        try:
            old_len = len(self._value) if hasattr(self._value, '__len__') else None
        except TypeError:
            old_len = None

        # Call the wrapped object's actual clear method.
        clear_method()
        # Notify subscribers that the container was cleared.
        self._notify({
            "type": "clear",
            "path": [],              # Clearing affects the root container
            "value": self._value,    # Send the now-empty container state
            "length": 0,             # New length is always 0 after clear
            # Optionally include old_length if needed by UI: "old_length": old_len
        })

    # --- Dictionary/Mapping Methods ---

    def __setitem__(self, key: Any, value: Any):
        """Sets the value for a key in the wrapped container (dict/list) and notifies.

        This method intercepts the standard Python square bracket assignment:
        `my_observable[key] = value`

        It performs the assignment on the wrapped object and then triggers a
        "setitem" notification. Works for both dictionary key assignment and
        list index assignment.

        Raises:
            TypeError: If the wrapped value doesn't support item assignment (e.g., a set).
        """
        # Check if the wrapped object supports item assignment.
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)):
            raise TypeError("ObservableValue: __setitem__ ([key] = value) requires the wrapped value to be a mutable sequence or mapping.")

        old_value = None
        is_mapping = isinstance(self._value, collections.abc.MutableMapping)
        is_sequence = isinstance(self._value, collections.abc.MutableSequence)

        # Try to get the old value *before* overwriting it, for the notification.
        try:
            if is_mapping: old_value = self._value.get(key)
            elif is_sequence and isinstance(key, int) and 0 <= key < len(self._value):
                 old_value = self._value[key] # type: ignore
        except Exception:
            # Ignore errors getting old value (e.g., key doesn't exist yet, index out of bounds)
            pass

        # Perform the actual assignment on the wrapped object.
        try:
            self._value[key] = value # type: ignore
        except IndexError as e:
            # Re-raise index errors for lists to match standard behavior
            if is_sequence: raise e
            # For mappings, this shouldn't happen unless __setitem__ is weird.
            logger.error(f"ObservableValue: Unexpected error during __setitem__ for key '{key}': {e}")
            # Avoid notifying if the set failed
            return
        except Exception as e:
            logger.error(f"ObservableValue: Unexpected error during __setitem__ for key '{key}': {e}")
             # Avoid notifying if the set failed
            return


        # Notify subscribers about the successful assignment.
        self._notify({
            "type": "setitem",
            "path": [key],              # Path is the key or index used
            "value": value,             # The new value that was set
            "key": key if is_mapping else None, # Include key *only* for dicts/mappings
            "old_value": old_value      # The value that was replaced (or None if new)
        })

    def __delitem__(self, key: Any):
        """Deletes an item/key from the wrapped container (dict/list) and notifies.

        Intercepts the standard Python `del` statement:
        `del my_observable[key]`

        Performs the deletion and then triggers a "delitem" notification.

        Raises:
            TypeError: If the wrapped value doesn't support item deletion.
            KeyError/IndexError: If the key/index doesn't exist (standard behavior).
        """
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)):
            raise TypeError("ObservableValue: __delitem__ (del obj[key]) requires a mutable sequence or mapping.")

        # Get the value *before* deleting it, to include in the notification.
        # This will raise KeyError/IndexError if the key/index doesn't exist,
        # which is the standard behavior of `del`, so we let it propagate.
        old_value = self._value[key] # type: ignore
        is_mapping = isinstance(self._value, collections.abc.MutableMapping)
        old_len = len(self._value) if hasattr(self._value, '__len__') else None

        # Perform the actual deletion on the wrapped object.
        del self._value[key] # type: ignore

        # Notify subscribers about the successful deletion.
        new_len = len(self._value) if hasattr(self._value, '__len__') else None
        self._notify({
            "type": "delitem",
            "path": [key],              # Path is the key or index deleted
            "value": None,              # No new value associated with delete
            "key": key if is_mapping else None, # Include key only for mappings
            "old_value": old_value,     # The value that was deleted
            "length": new_len           # New length after deletion
        })

    def update(self, other: Union[Dict[Any, Any], Mapping[Any, Any]] = {}, **kwargs: Any):
        """Updates the wrapped dictionary with key-value pairs and notifies for each change.

        Works like the standard dictionary `update()` method but ensures that
        each key added or modified triggers an individual "setitem" notification.

        Requires the wrapped value to be a mutable mapping (like a `dict`).

        Raises:
            TypeError: If the wrapped value is not a dictionary or similar mutable mapping.
        """
        if not isinstance(self._value, collections.abc.MutableMapping):
            raise TypeError("ObservableValue: update() requires a mutable mapping.")

        # Combine the dictionary/mapping `other` and the keyword arguments `kwargs`.
        # Using a temporary dict handles potential overlaps correctly.
        # We don't call self._value.update() directly because we want to intercept
        # each individual assignment to trigger notifications via __setitem__.
        items_to_update: Dict[Any, Any] = {}
        if hasattr(other, 'items'):
             items_to_update.update(other) # type: ignore
        elif other: # Check if 'other' is truthy to avoid errors with empty non-mappings
             try: items_to_update.update(dict(other)) # Attempt conversion if not mapping
             except TypeError: logger.warning(f"ObservableValue.update() received non-mapping 'other' argument: {type(other)}")
        items_to_update.update(kwargs)


        # Iterate through the combined items and use our intercepted __setitem__
        # for each one. This ensures notifications are sent for every change.
        for key, value in items_to_update.items():
            self[key] = value # Calls our __setitem__(key, value)

    # --- Set Methods ---

    def add(self, element: Any):
        """Adds an element to the wrapped set and notifies subscribers if it wasn't already present."""
        if not isinstance(self._value, collections.abc.MutableSet):
            raise TypeError("ObservableValue: add() requires a mutable set.")

        # Check if the element is already in the set *before* adding.
        # Only notify if the set actually changes.
        if element not in self._value:
            # Perform the actual add operation.
            self._value.add(element)
            # Notify subscribers.
            self._notify({
                "type": "add_set",       # Specific type for set addition
                "path": [],              # Set operations don't have a simple path index
                "value": element,        # The element that was added
                "length": len(self._value) # The new size of the set
            })

    def discard(self, element: Any):
         """Removes an element from the wrapped set if it is present and notifies."""
         if not isinstance(self._value, collections.abc.MutableSet):
             raise TypeError("ObservableValue: discard() requires a mutable set.")

         # Check if the element is actually in the set *before* discarding.
         # Only notify if the set actually changes.
         if element in self._value:
            # Perform the actual discard operation.
            self._value.discard(element)
            # Notify subscribers.
            self._notify({
                "type": "discard_set", # Specific type for set removal
                "path": [],            # No simple path index
                "value": None,         # No new value
                "old_value": element,  # The element that was removed
                "length": len(self._value) # The new size of the set
            })

    # --- Standard Dunder Methods (Delegation) ---
    # These methods make the ObservableValue wrapper behave more like the
    # value it contains for common operations like getting attributes, string
    # representation, comparisons, length checks, iteration, etc. They mostly
    # just "delegate" the operation to the wrapped value.

    def __getattr__(self, name: str) -> Any:
        """Delegates attribute access to the wrapped value.

        Allows you to access methods and attributes of the wrapped object
        directly through the ObservableValue instance, for convenience.
        For example, if `obs_list = ObservableValue([1, 2])`, you can call
        `obs_list.count(1)` and it will correctly call the `count` method
        of the underlying list.

        It prevents access to the ObservableValue's own internal attributes
        (like `_value`, `_subscribers`) via this delegation mechanism.
        """
        # Prevent accidental access to internal attributes via delegation.
        if name in ObservableValue._obs_internal_attrs:
             # Raise standard AttributeError if trying to access internals this way.
             raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}' (internal attributes are protected)")

        # If the attribute name is not internal, try to get it from the wrapped value.
        # This will raise an AttributeError if the wrapped value doesn't have it.
        try:
            return getattr(self._value, name)
        except AttributeError:
            # Make the error message clearer, indicating it failed on the wrapped value.
             raise AttributeError(f"'{type(self._value).__name__}' object (wrapped by ObservableValue) has no attribute '{name}'")


    def __setattr__(self, name: str, value: Any):
        """Sets internal attributes or delegates attribute setting to the wrapped value.

        - If `name` refers to one of the ObservableValue's own internal attributes
          (like `_value`), it sets that internal attribute directly.
        - Otherwise, it attempts to set the attribute on the *wrapped* object.

        **Important:** Delegating attribute setting like this does **not**
        automatically trigger notifications. If you need the Viz panel to update
        when an attribute of a wrapped *object* changes, you either need to:
          a) Call `.set(self.get())` on the ObservableValue after modifying the
             wrapped object's attribute to force a full refresh notification.
          b) Wrap the mutable attributes *within* your custom object using
             their own `ObservableValue` instances if possible.
        """
        # Check if the attribute name is one of the internal ones.
        if name in ObservableValue._obs_internal_attrs:
            # Set internal attributes directly on the ObservableValue instance.
            object.__setattr__(self, name, value)
        else:
            # Otherwise, delegate the attribute setting to the wrapped object.
            # Note: This does NOT trigger _notify() automatically.
            try:
                setattr(self._value, name, value)
            except AttributeError:
                 raise AttributeError(f"Cannot set attribute '{name}'; '{type(self._value).__name__}' object (wrapped by ObservableValue) may not support attribute assignment or the attribute is read-only.")


    def __repr__(self) -> str:
        """Returns a string representation like `ObservableValue([...])`."""
        # Show that it's an ObservableValue wrapping the inner value's repr.
        return f"ObservableValue({repr(self._value)})"

    def __str__(self) -> str:
        """Returns the string representation of the *wrapped* value."""
        # Behaves like the wrapped value when converted to string.
        return str(self._value)

    def __eq__(self, other: Any) -> bool:
        """Compares the *wrapped* value for equality."""
        # If comparing with another ObservableValue, compare their wrapped values.
        if isinstance(other, ObservableValue):
            return self._value == other._value
        # Otherwise, compare the wrapped value with the other object directly.
        return self._value == other

    def __len__(self) -> int:
        """Returns the length of the wrapped value (if it has one).

        Allows using `len(my_observable)` if the wrapped object supports it.

        Raises:
            TypeError: If the wrapped object does not support `len()`.
        """
        # Delegate len() call to the wrapped value.
        if hasattr(self._value, '__len__'):
            try:
                return len(self._value) # type: ignore
            except TypeError as e:
                # Re-raise with context if len() fails unexpectedly on an object that has __len__
                raise TypeError(f"Object of type '{type(self._value).__name__}' has __len__ but raised TypeError: {e}") from e
        else:
            raise TypeError(f"Object of type '{type(self._value).__name__}' (wrapped by ObservableValue) has no len()")

    def __getitem__(self, key: Any) -> Any:
        """Allows accessing items/keys of the wrapped value using `[]`.

        Allows `my_observable[key]` if the wrapped object supports it (like
        lists or dictionaries).

        Raises:
            TypeError: If the wrapped object does not support `[]` access.
            KeyError/IndexError: If the key/index is invalid for the wrapped object.
        """
        # Delegate item access (obj[key]) to the wrapped value.
        if isinstance(self._value, (collections.abc.Sequence, collections.abc.Mapping)):
             # This will raise KeyError or IndexError naturally if key is invalid.
             try:
                return self._value[key] # type: ignore
             except Exception as e:
                # Provide more context in case of error
                logger.debug(f"Error during ObservableValue __getitem__ for key '{key}': {e}")
                raise e # Re-raise original error
        else:
            raise TypeError(f"'{type(self._value).__name__}' object (wrapped by ObservableValue) is not subscriptable (doesn't support [])")

    def __iter__(self) -> Iterable[Any]:
        """Allows iterating over the wrapped value (e.g., in a `for` loop).

        Allows `for item in my_observable:` if the wrapped object is iterable.

        Raises:
            TypeError: If the wrapped object is not iterable.
        """
        # Delegate iteration requests to the wrapped value.
        if hasattr(self._value, '__iter__'):
            return iter(self._value) # type: ignore
        else:
            raise TypeError(f"'{type(self._value).__name__}' object (wrapped by ObservableValue) is not iterable")

    def __contains__(self, item: Any) -> bool:
        """Allows using the `in` operator (e.g., `item in my_observable`).

        Checks if the `item` is present in the wrapped value.

        Raises:
            TypeError: If the wrapped object does not support the `in` operator
                       or iteration as a fallback.
        """
        # Delegate the 'in' check to the wrapped value if possible.
        if hasattr(self._value, '__contains__'):
            try:
                 return item in self._value # type: ignore
            except Exception as e:
                 # Provide more context if 'in' fails unexpectedly
                 logger.debug(f"Error during ObservableValue __contains__ for item '{item}': {e}")
                 raise e # Re-raise original error

        # Fallback: If no __contains__, try iterating (less efficient).
        elif hasattr(self._value, '__iter__'):
             logger.debug(f"ObservableValue: Using iteration fallback for __contains__ check on type {type(self._value).__name__}.")
             try:
                 for element in self._value: # type: ignore
                     if element == item: return True
                 return False
             except Exception as e:
                 raise TypeError(f"Error during iteration fallback for 'in' operator on type '{type(self._value).__name__}': {e}") from e
        else:
            # If neither __contains__ nor __iter__ exists.
             raise TypeError(f"'{type(self._value).__name__}' object (wrapped by ObservableValue) does not support the 'in' operator.")