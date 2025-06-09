"""Provides the ObservableValue class for making Sidekick visualizations reactive.

This module contains the `ObservableValue` class, a special wrapper you can use
around your regular Python lists, dictionaries, or sets.

Why use it?

The main purpose of `ObservableValue` is to work hand-in-hand with the
`sidekick.Viz` component. When you display an `ObservableValue` using `viz.show()`,
the Viz panel in Sidekick gains a superpower: it **automatically updates** its
display whenever you modify the data inside the `ObservableValue`.

How it works:

1.  Wrap your data: `my_list = sidekick.ObservableValue([1, 2])`
2.  Show it in Viz: `viz.show("My List", my_list)`
3.  Modify the data **using the wrapper's methods**:

    *   `my_list.append(3)`
    *   `my_list[0] = 99`
    *   `del my_list[1]`

4.  Observe: The Viz panel in Sidekick updates instantly to show these changes,
    often highlighting exactly what was modified.

This makes it much easier to track how your data structures evolve during your
script's execution without needing to manually call `viz.show()` after every single change.

Note on Limitations:

*   Automatic updates only occur when you modify the data *through* the
    `ObservableValue` wrapper's methods (like `.append()`, `[key]=value`, `.add()`).
    Changes made directly to the underlying object obtained via `.get()` might not
    be detected automatically.
*   For nested structures (e.g., a list inside a dictionary), you would need to
    wrap the inner mutable structures with `ObservableValue` as well if you want
    their internal changes to trigger automatic updates.
*   Changes made by directly setting attributes on a wrapped *custom object* are
    generally not detected automatically.
"""

import collections.abc # Used for checking mutable collection types like list, dict, set
from typing import Any, List, Set, Dict, Callable, Optional, Union, Tuple, Iterable, Mapping
from . import logger

# Type Alias for clarity: Represents a function that subscribers provide to receive notifications.
# The function should accept one argument: a dictionary containing change details.
SubscriptionCallback = Callable[[Dict[str, Any]], None]
# Type Alias for clarity: Represents the function returned by 'subscribe', which can be called to stop the subscription.
UnsubscribeFunction = Callable[[], None]

class ObservableValue:
    """Wraps a Python value (list, dict, set) to notify subscribers about changes.

    Use this class to make your data "reactive" when displayed using the `sidekick.Viz`
    component. By wrapping mutable data structures (lists, dictionaries, sets) in an
    `ObservableValue`, you enable the Viz panel in Sidekick to update its display
    automatically whenever you modify the wrapped data through this wrapper object.

    This is achieved by intercepting common modification methods (like `append`,
    `__setitem__`, `update`, `add`, `clear`, etc.) and sending notifications
    after the operation completes.

    Basic Usage:
        >>> import sidekick
        >>> viz = sidekick.Viz() # Assuming Viz panel is ready
        >>>
        >>> # Wrap a list
        >>> shopping_list = sidekick.ObservableValue(['apples', 'bananas'])
        >>> viz.show("Groceries", shopping_list)
        >>>
        >>> # Modify through the wrapper - Viz updates automatically!
        >>> shopping_list.append('carrots')
        >>> shopping_list[0] = 'blueberries'
        >>>
        >>> # Wrap a dictionary
        >>> config = sidekick.ObservableValue({'theme': 'dark', 'autosave': False})
        >>> viz.show("Settings", config)
        >>>
        >>> # Modify through the wrapper - Viz updates automatically!
        >>> config['autosave'] = True
        >>> config.update({'fontSize': 12})
        >>> del config['theme']

    Key Benefit: Simplifies tracking data changes visually in Sidekick, as you
    don't need repeated calls to `viz.show()` after each modification to an
    observed value.

    See the module docstring for important limitations regarding direct modification
    of unwrapped values or attributes of wrapped custom objects.
    """
    # --- Internal Attributes ---
    # Define names of attributes used internally by ObservableValue itself.
    # This helps __getattr__ and __setattr__ distinguish between accessing/setting
    # internal state vs. delegating to the wrapped value.
    _obs_internal_attrs = ('_value', '_subscribers', '_obs_value_id')

    def __init__(self, value: Any):
        """Initializes the ObservableValue by wrapping the provided Python value.

        Args:
            value: The Python value (e.g., a list, dict, set, number, string, etc.)
                that you want to make observable.
        """
        # The actual Python object being wrapped and observed.
        self._value: Any = value
        # A set holding the callback functions of active subscribers (like Viz).
        self._subscribers: Set[SubscriptionCallback] = set()
        # A relatively stable internal ID string based on the memory address of this
        # ObservableValue wrapper instance. Used by Viz to track this specific
        # observable across updates, helping maintain UI state (like expanded nodes).
        self._obs_value_id: str = f"obs_{id(self)}"

    # --- Subscription Management (Primarily for internal use by Viz) ---

    def subscribe(self, callback: SubscriptionCallback) -> UnsubscribeFunction:
        """Registers a function to be called whenever the wrapped value changes. (Internal).

        This method is primarily intended for internal use by the `sidekick.Viz`
        component. When `viz.show()` is called with an `ObservableValue`, Viz uses
        this method to register its own internal handler (`_handle_observable_update`).

        When a change occurs to the wrapped value (triggered by methods like
        `append()`, `__setitem__()`, `set()`, etc.), the `callback` function
        provided here is executed with a dictionary containing details about
        that specific change (e.g., type of change, path, new value).

        Args:
            callback: A function that accepts one argument: a dictionary
                describing the change event (common keys include 'type', 'path',
                'value', 'key', 'old_value', 'length').

        Returns:
            UnsubscribeFunction: A function that, when called with no arguments,
                will remove this specific `callback` from the subscription list.
                This allows `Viz` to clean up its listener when the variable is
                removed from the display or the Viz panel itself is removed.

        Raises:
            TypeError: If the provided `callback` is not a callable function.
        """
        if not callable(callback):
            raise TypeError("Callback provided to ObservableValue.subscribe must be callable")
        # Add the provided callback function to the set of active subscribers.
        self._subscribers.add(callback)
        logger.debug(f"Subscribed callback {callback} to ObservableValue (id: {self._obs_value_id})")

        # Create and return a dedicated function to unsubscribe this specific callback.
        # This avoids potential issues with removing the wrong callback if multiple
        # subscribers exist.
        def unsubscribe():
            self.unsubscribe(callback)
        return unsubscribe

    def unsubscribe(self, callback: SubscriptionCallback):
        """Removes a previously registered callback function. (Internal).

        Typically called by the `unsubscribe` function returned from `subscribe`,
        or potentially directly by `Viz` during cleanup.

        Args:
            callback: The specific callback function instance to remove from the
                      set of subscribers.
        """
        # Use set.discard() which safely removes the callback if it's present,
        # but does nothing (without error) if it was already removed.
        self._subscribers.discard(callback)
        logger.debug(f"Unsubscribed callback {callback} from ObservableValue (id: {self._obs_value_id})")

    def _notify(self, change_details: Dict[str, Any]):
        """Internal method to inform all registered subscribers about a change. (Internal).

        This method is called internally by the ObservableValue's intercepted
        methods (like `append`, `set`, `__setitem__`) *after* a modification
        has been successfully made to the wrapped `_value`.

        It iterates through all currently registered subscriber callbacks and calls
        each one, passing the `change_details` dictionary.

        Args:
            change_details (Dict[str, Any]): A dictionary containing information
                about the change that occurred. Standard keys include 'type' (e.g.,
                "setitem", "append"), 'path' (list indices/dict keys), 'value' (new
                value involved), 'key' (for dict changes), 'old_value' (value replaced
                or removed), and 'length' (new container length).
        """
        # Optimization: If no subscribers are registered, do nothing.
        if not self._subscribers:
            return

        # Ensure common keys exist in the details dictionary for a consistent structure,
        # even if their value is None for a particular change type. Helps subscribers.
        change_details.setdefault('path', []) # Path from root to change location
        change_details.setdefault('value', None) # New value involved (if any)
        change_details.setdefault('key', None)   # Key involved (for dicts, if any)
        change_details.setdefault('old_value', None) # Old value replaced/removed (if any)
        change_details.setdefault('length', None)    # New length of container (if applicable)

        logger.debug(f"Notifying {len(self._subscribers)} subscribers for ObservableValue (id: {self._obs_value_id}): {change_details}")

        # Iterate over a *copy* of the subscribers set. This prevents modification
        # issues if a subscriber callback itself tries to subscribe or unsubscribe
        # during the notification process.
        subscribers_to_notify = list(self._subscribers)
        for callback in subscribers_to_notify:
            try:
                # Call the subscriber function, passing the details of the change.
                callback(change_details)
            except Exception as e:
                # Log errors within subscriber callbacks but continue notifying others.
                # Prevents one faulty subscriber (e.g., in Viz) from breaking updates
                # for potential future subscribers.
                logger.exception(f"Error occurred inside ObservableValue subscriber callback {callback}: {e}")

    # --- Accessing and Replacing the Wrapped Value ---

    def get(self) -> Any:
        """Returns the actual underlying Python value being wrapped by this ObservableValue.

        Use this method when you need direct access to the original list, dictionary,
        set, or other object stored inside, without the ObservableValue wrapper's
        notification logic.

        Be cautious: Modifying mutable objects obtained via `get()` directly (e.g.,
        `my_obs_list.get().append(item)`) will **not** trigger automatic notifications
        to subscribers like `sidekick.Viz`. For automatic updates, always modify
        through the `ObservableValue` wrapper itself (`my_obs_list.append(item)`).

        Returns:
            The actual Python object currently stored within the wrapper.

        Example:
            >>> obs_list = sidekick.ObservableValue([10, 20, 30])
            >>> raw_list = obs_list.get()
            >>> print(raw_list)
            [10, 20, 30]
            >>> print(type(raw_list))
            <class 'list'>
            >>> # Modifying raw_list directly does NOT notify Viz
            >>> raw_list.pop()
            30
            >>> # Modifying through the wrapper DOES notify Viz
            >>> obs_list.pop() # Viz will update
        """
        return self._value

    def set(self, new_value: Any):
        """Replaces the currently wrapped value with a completely new value.

        This method is used when you want to assign a fundamentally different
        object (e.g., a new list, a different dictionary, a number instead of a
        list) to this observable variable, rather than just modifying the contents
        of the existing wrapped object.

        It triggers a "set" notification to all subscribers, indicating that the
        entire value has been replaced.

        Note:
            If the `new_value` you provide is the *exact same object* in memory
            as the currently wrapped value (i.e., `new_value is self.get()`),
            this method will do nothing and send no notification, as the value
            hasn't conceptually changed from the wrapper's perspective.

        Args:
            new_value: The new Python object to wrap and observe going forward.

        Example:
            >>> obs_data = sidekick.ObservableValue({"status": "pending"})
            >>> viz.show("Job Status", obs_data) # Show initial state
            >>>
            >>> # Replace the entire dictionary
            >>> final_status = {"status": "complete", "result": 123}
            >>> obs_data.set(final_status) # Viz panel updates to show the new dict
            >>>
            >>> # Further modifications through obs_data now affect final_status
            >>> obs_data["timestamp"] = time.time() # Viz updates again
        """
        # Optimization: Only update and notify if the new value is actually
        # a different object from the one currently stored. Checking identity `is`
        # is important here, not just equality `==`.
        if self._value is not new_value:
            old_value = self._value # Keep a reference to the old value for the notification.
            self._value = new_value # Update the internal reference to the new value.
            # Send a notification indicating a 'set' operation at the root path.
            self._notify({
                "type": "set",        # Type of change: wholesale replacement
                "path": [],           # Path is empty, indicating the root value changed
                "value": self._value, # The new value now being wrapped
                "old_value": old_value # The value that was just replaced
                # Length is typically handled by the Viz component during 'set' based on new value.
            })

    # --- Intercepted Methods for Mutable Containers ---
    # These methods override standard Python operations for lists, dicts, and sets.
    # They first perform the operation on the wrapped self._value, and then,
    # if the operation was successful and potentially changed the value,
    # they call self._notify() to inform subscribers.

    # --- List/Sequence Methods ---

    def append(self, item: Any):
        """Appends an item to the end of the wrapped list/sequence and notifies subscribers.

        This method mimics the behavior of `list.append()`. It requires the
        wrapped value (`self.get()`) to be a mutable sequence (like a standard
        Python `list`).

        Raises:
            AttributeError: If the wrapped value does not have an `append` method.
            TypeError: If the wrapped value is not a list or similar mutable sequence
                       (though usually caught by AttributeError first).

        Example:
            >>> items = sidekick.ObservableValue(['a', 'b'])
            >>> viz.show("Items", items)
            >>> items.append('c') # Viz automatically updates to show ['a', 'b', 'c']
        """
        # Check if the wrapped object supports append (duck typing).
        if not isinstance(self._value, collections.abc.MutableSequence):
            # Provide a more specific error message.
            raise TypeError("ObservableValue: append() requires the wrapped value to be a mutable sequence (e.g., list).")

        # Record current length to determine the index of the appended item.
        current_len = len(self._value)
        # Perform the actual append operation on the wrapped list.
        try:
            self._value.append(item) # type: ignore # Assume append exists if MutableSequence passed
        except AttributeError:
             raise AttributeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} has no 'append' method.")

        # Notify subscribers about the successful append operation.
        self._notify({
            "type": "append",
            "path": [current_len],      # Path identifies the index of the newly added item
            "value": item,              # The item that was actually added
            "length": len(self._value)  # The new total length of the list
        })

    def insert(self, index: int, item: Any):
        """Inserts an item at a specific index in the wrapped list/sequence and notifies subscribers.

        Mimics `list.insert()`. Requires the wrapped value to be a mutable sequence.

        Args:
            index (int): The index at which to insert the `item`.
            item (Any): The item to insert.

        Raises:
            AttributeError: If the wrapped value does not have an `insert` method.
            TypeError: If the wrapped value is not a list or similar.
            IndexError: If the index is out of range for insertion (behavior matches list.insert).
        """
        if not isinstance(self._value, collections.abc.MutableSequence):
            raise TypeError("ObservableValue: insert() requires the wrapped value to be a mutable sequence.")
        # Perform the actual insert operation on the wrapped list.
        try:
            self._value.insert(index, item) # type: ignore # Assume insert exists
        except AttributeError:
             raise AttributeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} has no 'insert' method.")

        # Notify subscribers about the successful insertion.
        self._notify({
            "type": "insert",
            "path": [index],            # Path identifies the index where insertion occurred
            "value": item,              # The item that was inserted
            "length": len(self._value)  # The new total length of the list
        })

    def pop(self, index: int = -1) -> Any:
        """Removes and returns the item at the given index (default last) and notifies subscribers.

        Mimics `list.pop()`. Requires the wrapped value to be a mutable sequence.

        Args:
            index (int): The index of the item to remove. Defaults to -1 (the last item).

        Returns:
            The item that was removed from the list.

        Raises:
            AttributeError: If the wrapped value does not have a `pop` method.
            TypeError: If the wrapped value is not a list or similar.
            IndexError: If the list is empty or the index is out of range.
        """
        if not isinstance(self._value, collections.abc.MutableSequence):
            raise TypeError("ObservableValue: pop() requires the wrapped value to be a mutable sequence.")

        # Determine the actual index being popped *before* mutation for accurate reporting.
        # Handles negative indices correctly. Raises IndexError if invalid.
        try:
            list_len = len(self._value)
            if list_len == 0: raise IndexError("pop from empty list") # Match list behavior
            actual_index = index if index >= 0 else list_len + index
            if not (0 <= actual_index < list_len): raise IndexError("pop index out of range") # Match list behavior
        except IndexError as e:
            logger.error(f"ObservableValue: Error calculating pop index (index={index}, len={list_len}): {e}")
            raise # Re-raise the standard Python error

        # Perform the actual pop operation on the wrapped list.
        try:
            popped_value = self._value.pop(index) # type: ignore # Assume pop exists
        except AttributeError:
            raise AttributeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} has no 'pop' method.")
        except IndexError as e:
            # This might happen in race conditions, though unlikely for typical Sidekick usage.
            logger.error(f"ObservableValue: IndexError during pop itself (index={index}): {e}")
            raise e


        # Notify subscribers about the successful pop operation.
        self._notify({
            "type": "pop",
            "path": [actual_index],     # Path identifies the index from which the item was removed
            "value": None,              # No *new* value is associated with a pop
            "old_value": popped_value,  # The value that was actually removed
            "length": len(self._value)  # The new total length of the list
        })
        # Return the removed value, just like standard list.pop().
        return popped_value

    def remove(self, value: Any):
         """Removes the first occurrence of a given value from the wrapped list/sequence and notifies subscribers.

         Mimics `list.remove()`. Requires the wrapped value to be a mutable sequence.
         If the value is not found, it does nothing (and sends no notification), matching
         the standard `list.remove()` behavior.

         Args:
             value (Any): The value to search for and remove the first instance of.

         Raises:
            AttributeError: If the wrapped value does not have a `remove` method.
            TypeError: If the wrapped value is not a list or similar.
            ValueError: While this method catches the `ValueError` from `list.remove`
                        (when the value isn't found) and does nothing, the underlying
                        `list.index` call used for notification *could* raise it if the
                        value disappears between the check and the call (highly unlikely).
         """
         if not isinstance(self._value, collections.abc.MutableSequence):
             raise TypeError("ObservableValue: remove() requires the wrapped value to be a mutable sequence.")

         try:
             # Find the index *before* removing, so we can report the path accurately.
             # This will raise ValueError if 'value' is not in the list.
             index_to_remove = self._value.index(value) # type: ignore # Assume index exists

             # Perform the actual removal operation on the wrapped list.
             # This might also raise ValueError, but we check first with index().
             self._value.remove(value) # type: ignore # Assume remove exists

             # If remove succeeded (i.e., index() didn't raise ValueError), notify.
             self._notify({
                "type": "remove", # Specific type for removing by value rather than index
                "path": [index_to_remove], # Path is the index where the value was found
                "value": None,             # No *new* value associated with removal
                "old_value": value,        # The value that was actually removed
                "length": len(self._value) # The new total length of the list
             })
         except ValueError:
            # Standard list.remove() behavior: if the value isn't found, do nothing.
            # So, we catch the ValueError from index() and do not notify.
            pass
         except AttributeError:
             # Handle cases where wrapped object lacks index() or remove().
             raise AttributeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} has no 'remove' or 'index' method.")

    def clear(self):
        """Removes all items from the wrapped container (list, dict, set) and notifies subscribers.

        Requires the wrapped value to have a callable `clear()` method.

        Raises:
            AttributeError: If the wrapped object does not have a `clear` method.
            TypeError: If the wrapped object's `clear` attribute is not callable.
        """
        # Check if the wrapped value actually *has* a 'clear' method using getattr.
        clear_method = getattr(self._value, 'clear', None)
        if not callable(clear_method):
            # Raise error if no clear method exists or it's not callable.
            raise AttributeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} has no callable 'clear' method.")

        # Store old length *before* clearing for potential use in notification (though not strictly required by Viz currently).
        try:
            old_len = len(self._value) if hasattr(self._value, '__len__') else None
        except TypeError:
            old_len = None # Handle cases like custom objects without len()

        # Call the wrapped object's actual clear method.
        clear_method()

        # Notify subscribers that the container was cleared.
        self._notify({
            "type": "clear",
            "path": [],              # Path is empty, indicates the root container was cleared
            "value": self._value,    # Include the (now empty) container state in the notification
            "length": 0,             # New length is always 0 after clear
            # Optionally include old_length if needed by UI: "old_length": old_len
        })

    # --- Dictionary/Mapping Methods ---

    def __setitem__(self, key: Any, value: Any):
        """Sets the value for a key/index in the wrapped container (dict/list) and notifies subscribers.

        This method intercepts the standard Python square bracket assignment syntax:
        `my_observable[key] = value`

        It performs the assignment operation on the wrapped object (`self._value`)
        and then, if successful, triggers a "setitem" notification to inform
        subscribers (like Viz) about the change. This works for both dictionary
        key assignment (`my_dict[key] = val`) and list index assignment
        (`my_list[index] = val`).

        Args:
            key (Any): The key (for dictionaries) or index (for lists) to assign to.
            value (Any): The new value to associate with the key/index.

        Raises:
            TypeError: If the wrapped value does not support item assignment (e.g.,
                       if it's a set, tuple, or immutable object).
            IndexError: If the wrapped value is a list and the index is out of range.
            KeyError: Typically not raised by assignment itself, but underlying checks might.
        """
        # Check if the wrapped object supports item assignment (MutableSequence or MutableMapping).
        # Using abstract base classes makes this check more robust for custom collections.
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)):
            raise TypeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} does not support item assignment using []=.")

        old_value = None
        is_mapping = isinstance(self._value, collections.abc.MutableMapping)
        is_sequence = isinstance(self._value, collections.abc.MutableSequence)

        # Attempt to retrieve the *old* value associated with the key/index *before*
        # overwriting it. This is useful for notifications (e.g., Viz highlighting).
        # We wrap this in a try/except because the key/index might not exist yet.
        try:
            if is_mapping:
                # For dicts, use get() which returns None if key doesn't exist.
                old_value = self._value.get(key)
            elif is_sequence and isinstance(key, int):
                # For lists, check index validity before accessing to avoid IndexError here.
                if 0 <= key < len(self._value):
                     old_value = self._value[key] # Access only if index is valid
        except Exception:
            # Ignore potential errors retrieving the old value (e.g., key not found, index error).
            # old_value will remain None, which is acceptable.
            pass

        # Perform the actual assignment operation on the wrapped object.
        # This is the core action that modifies the user's data.
        try:
            self._value[key] = value # type: ignore # Assume __setitem__ exists if type checks passed
        except IndexError as e:
            # If it's a sequence and assignment fails due to index, re-raise standard error.
            if is_sequence: raise e
            # Should not happen for mappings normally, but log if it does.
            logger.error(f"ObservableValue: Unexpected error during dict __setitem__ for key '{key}': {e}")
            return # Avoid notifying if the assignment failed
        except Exception as e:
            # Catch any other unexpected errors during assignment.
            logger.error(f"ObservableValue: Unexpected error during __setitem__ for key '{key}': {e}")
            return # Avoid notifying if the assignment failed

        # If assignment succeeded, notify subscribers about the change.
        self._notify({
            "type": "setitem",
            "path": [key],              # Path is the key or index that was assigned to
            "value": value,             # The new value that was assigned
            # Include 'key' only for dictionary/mapping types for clarity in Viz.
            "key": key if is_mapping else None,
            "old_value": old_value      # The value that was replaced (or None if it was a new key/index)
            # Length is usually not changed by setitem unless list grows (not standard)
        })

    def __delitem__(self, key: Any):
        """Deletes an item/key from the wrapped container (dict/list) and notifies subscribers.

        Intercepts the standard Python `del` statement used with square brackets:
        `del my_observable[key]`

        It performs the deletion operation on the wrapped object (`self._value`)
        and then, if successful, triggers a "delitem" notification. Works for
        deleting dictionary keys or list items by index.

        Args:
            key (Any): The key (for dictionaries) or index (for lists) to delete.

        Raises:
            TypeError: If the wrapped value does not support item deletion.
            KeyError: If the wrapped value is a dictionary and the key is not found.
            IndexError: If the wrapped value is a list and the index is out of range.
        """
        if not isinstance(self._value, (collections.abc.MutableSequence, collections.abc.MutableMapping)):
            raise TypeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} does not support item deletion using del [].")

        is_mapping = isinstance(self._value, collections.abc.MutableMapping)
        old_len = None
        old_value = None

        # Attempt to get the value *before* deleting it for the notification.
        # This will naturally raise KeyError/IndexError if the key/index doesn't exist,
        # matching the standard behavior of `del`, so we allow it to propagate upwards.
        try:
            old_value = self._value[key] # type: ignore # Assume __getitem__ exists
            if hasattr(self._value, '__len__'): old_len = len(self._value)
        except (KeyError, IndexError) as e:
             raise e # Let standard errors propagate if item doesn't exist
        except Exception as e_get:
             logger.error(f"ObservableValue: Unexpected error getting item '{key}' before deletion: {e_get}")
             raise e_get # Propagate unexpected errors


        # Perform the actual deletion operation on the wrapped object.
        try:
            del self._value[key] # type: ignore # Assume __delitem__ exists
        except (KeyError, IndexError) as e:
             # Should ideally not happen if the __getitem__ above succeeded, but handle defensively.
             logger.error(f"ObservableValue: Error during deletion itself for key/index '{key}': {e}")
             raise e
        except Exception as e_del:
             logger.error(f"ObservableValue: Unexpected error during deletion itself for key/index '{key}': {e_del}")
             raise e_del


        # If deletion succeeded, notify subscribers.
        new_len = len(self._value) if hasattr(self._value, '__len__') else None
        self._notify({
            "type": "delitem",          # Use "delitem" or potentially "pop" if consistent
            "path": [key],              # Path is the key or index that was deleted
            "value": None,              # No *new* value associated with deletion
            "key": key if is_mapping else None, # Include key only for mappings
            "old_value": old_value,     # The value that was actually deleted
            "length": new_len           # The new length after deletion
        })

    def update(self, other: Union[Dict[Any, Any], Mapping[Any, Any], Iterable[Tuple[Any, Any]]] = {}, **kwargs: Any):
        """Updates the wrapped dictionary with key-value pairs from another mapping and/or keyword arguments, notifying subscribers for each change.

        Mimics the behavior of `dict.update()`. It iterates through the items to be
        added or updated and uses the intercepted `__setitem__` method for each one.
        This ensures that subscribers (like Viz) receive individual "setitem"
        notifications for every key that is added or whose value is changed, allowing
        for more granular UI updates compared to a single bulk update notification.

        Requires the wrapped value (`self.get()`) to be a mutable mapping (like a
        standard Python `dict`).

        Args:
            other: Can be another dictionary, an object implementing the `Mapping`
                   protocol, or an iterable of key-value pairs (like `[('a', 1), ('b', 2)]`).
                   Keys and values from `other` will be added/updated in the wrapped dict.
            **kwargs: Keyword arguments are treated as additional key-value pairs
                      to add or update in the wrapped dictionary.

        Raises:
            AttributeError: If the wrapped value does not behave like a dictionary (no `__setitem__`).
            TypeError: If the wrapped value is not a dictionary or similar mutable mapping,
                       or if the `other` argument is not a valid source for updates.

        Example:
            >>> settings = sidekick.ObservableValue({'font': 'Arial', 'size': 10})
            >>> viz.show("Settings", settings)
            >>>
            >>> # Update using another dictionary
            >>> settings.update({'size': 12, 'theme': 'dark'}) # Sends 2 notifications
            >>> # Update using keyword arguments
            >>> settings.update(line_numbers=True, theme='light') # Sends 2 notifications (theme overwritten)
        """
        if not isinstance(self._value, collections.abc.MutableMapping):
            raise TypeError("ObservableValue: update() requires the wrapped value to be a mutable mapping (e.g., dict).")

        # Combine the dictionary/mapping `other` and the keyword arguments `kwargs`.
        # We process `other` first, then `kwargs` to match dict.update behavior
        # where kwargs can override keys present in `other`.
        # We perform the updates item by item using self[key] = value to trigger
        # individual notifications via our intercepted __setitem__.
        # We don't call self._value.update() directly, as that would bypass notifications.

        items_to_process: List[Tuple[Any, Any]] = []

        # Process the 'other' argument first
        if hasattr(other, 'keys') and callable(other.keys): # More robust check for mapping-like
             try: items_to_process.extend([(k, other[k]) for k in other.keys()]) # type: ignore
             except Exception as e:
                  logger.warning(f"ObservableValue.update(): Error iterating through 'other' mapping: {e}")
                  # Decide whether to raise or just ignore 'other'
                  raise TypeError(f"Could not process 'other' argument provided to update(): {e}") from e
        elif hasattr(other, '__iter__'): # Check if it's an iterable of pairs
            try: items_to_process.extend([(k, v) for k, v in other]) # type: ignore
            except (TypeError, ValueError) as e:
                 logger.warning(f"ObservableValue.update(): 'other' argument is iterable but not yielding key-value pairs: {e}")
                 raise TypeError(f"'other' argument must be a mapping or an iterable of pairs: {e}") from e
        elif other: # If 'other' is provided but not valid
             raise TypeError(f"'other' argument must be a mapping or an iterable of pairs, got {type(other).__name__}")


        # Add/override with keyword arguments
        if kwargs:
            items_to_process.extend(kwargs.items())

        # Now, iterate through the combined items and use our intercepted __setitem__
        # for each one. This ensures individual notifications are sent.
        for key, value in items_to_process:
            try:
                self[key] = value # Calls our intercepted __setitem__(key, value)
            except Exception as e_set:
                 # Log errors during the individual setitem calls but continue update if possible.
                 logger.error(f"ObservableValue.update(): Error setting key '{key}' during update: {e_set}")
                 # Optionally re-raise if strictness is needed: raise e_set


    # --- Set Methods ---

    def add(self, element: Any):
        """Adds an element to the wrapped set and notifies subscribers if the element was not already present.

        Mimics `set.add()`. Requires the wrapped value to be a mutable set.
        If the element is already in the set, this method does nothing (and sends
        no notification), matching standard set behavior.

        Args:
            element (Any): The element to add to the set.

        Raises:
            AttributeError: If the wrapped value does not have an `add` method or is not a set.
            TypeError: If the wrapped value is not a set or similar mutable set.
        """
        # Check if the wrapped value behaves like a set.
        if not isinstance(self._value, collections.abc.MutableSet):
            raise TypeError("ObservableValue: add() requires the wrapped value to be a mutable set.")

        # Check if the element is already present *before* attempting to add.
        # Only notify if the set's state actually changes.
        needs_add = False
        try:
            if element not in self._value: # type: ignore # Assume __contains__ exists for MutableSet
                 needs_add = True
        except TypeError as e_cont:
            # Handle cases where element is unhashable for 'in' check
            logger.warning(f"ObservableValue.add(): Cannot check containment for element {element} (unhashable?): {e_cont}")
            # Attempt the add anyway, relying on the set's own handling
            needs_add = True # Assume it might change the set

        if needs_add:
            # Perform the actual add operation on the wrapped set.
            try:
                self._value.add(element) # type: ignore # Assume add exists
                # If add succeeded, notify subscribers.
                self._notify({
                    "type": "add_set",       # Specific type for set addition
                    "path": [],              # Set operations don't have a simple path index
                    "value": element,        # The element that was actually added
                    "length": len(self._value) # The new size of the set
                })
            except AttributeError:
                 raise AttributeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} has no 'add' method.")
            except TypeError as e_add:
                 # Catch errors if the element is unhashable for the add operation itself.
                 logger.error(f"ObservableValue.add(): Failed to add element {element} (unhashable?): {e_add}")
                 raise e_add # Re-raise the TypeError


    def discard(self, element: Any):
         """Removes an element from the wrapped set if it is present, and notifies subscribers if removal occurred.

         Mimics `set.discard()`. Requires the wrapped value to be a mutable set.
         If the element is not found in the set, this method does nothing (and sends
         no notification), matching standard set behavior.

         Args:
             element (Any): The element to remove from the set.

         Raises:
             AttributeError: If the wrapped value does not have a `discard` method.
             TypeError: If the wrapped value is not a set or similar.
         """
         if not isinstance(self._value, collections.abc.MutableSet):
             raise TypeError("ObservableValue: discard() requires the wrapped value to be a mutable set.")

         # Check if the element is actually in the set *before* attempting to discard.
         # Only notify if the set's state actually changes.
         needs_discard = False
         try:
             if element in self._value: # type: ignore # Assume __contains__ exists
                 needs_discard = True
         except TypeError as e_cont:
             # Element might be unhashable, discard will handle it, no need to notify if check fails
             logger.warning(f"ObservableValue.discard(): Cannot check containment for element {element} (unhashable?): {e_cont}")
             # Proceed to discard, let the set handle unhashable if necessary
             pass


         if needs_discard:
             # Perform the actual discard operation on the wrapped set.
             try:
                 self._value.discard(element) # type: ignore # Assume discard exists
                 # If discard potentially removed the element (it was present), notify.
                 self._notify({
                     "type": "discard_set", # Specific type for set removal
                     "path": [],            # No simple path index for set elements
                     "value": None,         # No *new* value associated with removal
                     "old_value": element,  # The element that was targeted for removal
                     "length": len(self._value) # The new size of the set
                 })
             except AttributeError:
                  raise AttributeError(f"ObservableValue: Wrapped object of type {type(self._value).__name__} has no 'discard' method.")
             except TypeError as e_disc:
                  # Catch errors if the element is unhashable for discard.
                  logger.error(f"ObservableValue.discard(): Failed to discard element {element} (unhashable?): {e_disc}")
                  raise e_disc # Re-raise


    # --- Standard Dunder Methods (Delegation) ---
    # These methods allow the ObservableValue wrapper to behave more like the
    # value it contains for common Python operations (attribute access, string
    # conversion, comparisons, length checking, iteration, item access, etc.).
    # They mostly delegate the operation directly to the wrapped `self._value`.

    def __getattr__(self, name: str) -> Any:
        """Delegates attribute access to the wrapped value if the attribute is not internal.

        This allows you to conveniently access methods and attributes of the wrapped
        object directly through the `ObservableValue` instance. For example, if
        `obs_list = ObservableValue([1, 2])`, calling `obs_list.count(1)` will correctly
        delegate to the underlying list's `count` method.

        It prevents direct access to the `ObservableValue`'s own internal attributes
        (like `_value`, `_subscribers`) via this delegation mechanism to avoid conflicts.

        Args:
            name (str): The name of the attribute being accessed.

        Returns:
            Any: The value of the attribute from the wrapped object.

        Raises:
            AttributeError: If the attribute name refers to an internal attribute of
                            `ObservableValue` itself, or if the wrapped object does not
                            have an attribute with the given `name`.
        """
        # Prevent accidental delegation of the wrapper's internal attributes.
        if name in ObservableValue._obs_internal_attrs:
             # Raise standard AttributeError if trying to access internal attributes this way.
             raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}' (use .get() maybe? Internal attributes are protected)")

        # If the attribute name is not internal, try to get it from the wrapped value.
        # This will raise AttributeError naturally if the wrapped value doesn't have it.
        try:
            return getattr(self._value, name)
        except AttributeError:
            # Re-raise AttributeError with a more informative message.
             raise AttributeError(f"'{type(self._value).__name__}' object (wrapped by ObservableValue) has no attribute '{name}'")


    def __setattr__(self, name: str, value: Any):
        """Sets internal attributes or delegates attribute setting to the wrapped value.

        This method controls how attribute assignment works on the `ObservableValue` instance:

        *   If the `name` being assigned matches one of the `ObservableValue`'s own
            internal attributes (defined in `_obs_internal_attrs`, e.g., `_value`),
            it sets that internal attribute directly on the wrapper instance itself.
        *   Otherwise (if `name` is not an internal attribute), it attempts to set the
            attribute with the given `name` and `value` directly on the *wrapped object*
            (`self._value`).

        **Important:** Delegating attribute setting to the wrapped object via this method
        does **not** automatically trigger notifications to subscribers like Viz.
        If you need the Viz panel to update when you change an attribute of a wrapped
        *custom object*, you have several options:
          1.  Call `.set(self.get())` on the `ObservableValue` *after* modifying the
              wrapped object's attribute(s). This forces a full "set" notification,
              telling Viz to re-render the entire object display.
          2.  If the attribute itself holds mutable data (like a list), consider
              wrapping that attribute's value in its *own* `ObservableValue`.
          3.  If the custom object has its own notification mechanism, trigger it manually.

        Args:
            name (str): The name of the attribute to set.
            value (Any): The value to assign to the attribute.

        Raises:
            AttributeError: If attempting to set an attribute on a wrapped object that
                            doesn't support attribute assignment (e.g., built-in types
                            like `int` or `list`, or objects without `__slots__` or
                            `__dict__` allowing the assignment).
        """
        # Check if the attribute name is one of the predefined internal ones.
        if name in ObservableValue._obs_internal_attrs:
            # If internal, set the attribute directly on the ObservableValue instance itself
            # using object.__setattr__ to bypass our own __setattr__ override.
            object.__setattr__(self, name, value)
        else:
            # If not internal, delegate the attribute setting to the wrapped object.
            # Note: This delegation does NOT automatically trigger self._notify().
            try:
                setattr(self._value, name, value)
            except AttributeError as e:
                 # Provide a clearer error if setting the attribute on the wrapped object fails.
                 raise AttributeError(f"Cannot set attribute '{name}' on wrapped object of type "
                                      f"'{type(self._value).__name__}': {e}")


    def __repr__(self) -> str:
        """Returns a string representation showing it's an ObservableValue wrapping another value.

        Example: `ObservableValue([1, 2, 3])`
        """
        # Provide a representation that clearly indicates it's an ObservableValue wrapper.
        return f"ObservableValue({repr(self._value)})"

    def __str__(self) -> str:
        """Returns the string representation of the *wrapped* value.

        Allows `str(my_observable)` to behave the same as `str(my_observable.get())`.
        """
        # Delegate string conversion directly to the wrapped value.
        return str(self._value)

    def __eq__(self, other: Any) -> bool:
        """Compares the *wrapped* value for equality.

        Allows comparing an `ObservableValue` directly with another value or
        another `ObservableValue`. The comparison is performed on the underlying
        wrapped values.

        Example:
            >>> obs1 = ObservableValue([1, 2])
            >>> obs2 = ObservableValue([1, 2])
            >>> obs1 == [1, 2] # True
            >>> obs1 == obs2   # True
        """
        # If comparing with another ObservableValue, compare their wrapped values.
        if isinstance(other, ObservableValue):
            return self._value == other._value
        # Otherwise, compare the wrapped value directly with the other object.
        return self._value == other

    def __len__(self) -> int:
        """Returns the length of the wrapped value, if the wrapped value supports `len()`.

        Allows using `len(my_observable)` just like `len(my_observable.get())`.

        Raises:
            TypeError: If the wrapped object type does not have a defined length
                       (e.g., numbers, None, objects without `__len__`).
        """
        # Delegate the len() call to the wrapped value.
        # Check explicitly for __len__ first for clarity.
        if hasattr(self._value, '__len__') and callable(getattr(self._value, '__len__')):
            try:
                # Type ignore helps linters understand len() works here
                return len(self._value) # type: ignore
            except TypeError as e:
                # Re-raise with context if len() fails unexpectedly.
                raise TypeError(f"Object of type '{type(self._value).__name__}' (wrapped) has __len__ but raised TypeError: {e}") from e
        else:
            # Raise standard TypeError if wrapped object isn't sizable.
            raise TypeError(f"Object of type '{type(self._value).__name__}' (wrapped by ObservableValue) has no len()")

    def __getitem__(self, key: Any) -> Any:
        """Allows accessing items/keys of the wrapped value using square bracket notation (`[]`).

        Enables syntax like `my_observable[key]` or `my_observable[index]` if the
        wrapped object (`self.get()`) supports item access (like lists, dictionaries,
        or custom objects implementing `__getitem__`).

        Args:
            key (Any): The key or index to access within the wrapped object.

        Returns:
            Any: The value associated with the key/index in the wrapped object.

        Raises:
            TypeError: If the wrapped object does not support item access (`__getitem__`).
            KeyError: If the wrapped object is a dictionary and the key is not found.
            IndexError: If the wrapped object is a list and the index is out of range.
        """
        # Delegate item access (obj[key]) directly to the wrapped value.
        # This relies on the wrapped object's __getitem__ implementation.
        # We check common types first for better error messages.
        if isinstance(self._value, (collections.abc.Sequence, collections.abc.Mapping)):
             try:
                # This will naturally raise KeyError or IndexError if the key/index is invalid.
                return self._value[key] # type: ignore # Assume subscriptable
             except (KeyError, IndexError) as e:
                 raise e # Re-raise standard access errors
             except Exception as e:
                # Provide more context for unexpected errors during access.
                logger.debug(f"Error during ObservableValue __getitem__ for key '{key}': {e}")
                raise e # Re-raise original error
        # If not a standard sequence/mapping, check if it implements __getitem__ anyway.
        elif hasattr(self._value, '__getitem__'):
             try:
                 return self._value[key] # type: ignore
             except (TypeError, KeyError, IndexError) as e: # Catch standard errors
                 raise e
             except Exception as e:
                logger.debug(f"Error during custom __getitem__ for key '{key}': {e}")
                raise e
        else:
            # Raise TypeError if the wrapped object fundamentally doesn't support item access.
            raise TypeError(f"'{type(self._value).__name__}' object (wrapped by ObservableValue) is not subscriptable (does not support [])")

    def __iter__(self) -> Iterable[Any]:
        """Allows iterating over the wrapped value (e.g., in a `for` loop).

        Enables syntax like `for item in my_observable:` if the wrapped object
        (`self.get()`) is itself iterable (like lists, dictionaries, sets, strings,
        or custom objects implementing `__iter__`).

        Yields:
            The items produced by iterating over the wrapped value.

        Raises:
            TypeError: If the wrapped object is not iterable.
        """
        # Delegate iteration request directly to the wrapped value.
        if hasattr(self._value, '__iter__') and callable(getattr(self._value, '__iter__')):
            return iter(self._value) # type: ignore # Assume iterable
        else:
            # Raise standard TypeError if the wrapped object cannot be iterated.
            raise TypeError(f"'{type(self._value).__name__}' object (wrapped by ObservableValue) is not iterable")

    def __contains__(self, item: Any) -> bool:
        """Allows using the `in` operator to check for containment in the wrapped value.

        Enables syntax like `element in my_observable` if the wrapped object
        (`self.get()`) supports containment checks (like lists, dictionaries checking keys,
        sets, strings, or custom objects implementing `__contains__`).

        Args:
            item (Any): The item to check for containment within the wrapped value.

        Returns:
            bool: True if the `item` is found in the wrapped value, False otherwise.

        Raises:
            TypeError: If the wrapped object does not support the `in` operator
                       (typically requires `__contains__` or being iterable).
        """
        # Delegate the 'in' check (containment) directly to the wrapped value.
        # This relies on the wrapped object's __contains__ method if it exists,
        # or falls back to iteration if __contains__ is missing but __iter__ exists.
        try:
            # Type ignore helps linters understand 'in' works with various types
            return item in self._value # type: ignore
        except TypeError as e:
            # Re-raise TypeError if 'in' is fundamentally not supported by the wrapped type.
             raise TypeError(f"'{type(self._value).__name__}' object (wrapped by ObservableValue) does not support the 'in' operator: {e}") from e
        except Exception as e_cont:
             # Catch other unexpected errors during the 'in' check.
             logger.debug(f"Error during ObservableValue __contains__ for item '{item}': {e_cont}")
             raise e_cont # Re-raise original error
