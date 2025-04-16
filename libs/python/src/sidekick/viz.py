"""
Provides the Viz class for visualizing Python variables in Sidekick.

Use the `sidekick.Viz` class to display your Python variables, including
complex data structures like lists, dictionaries, sets, and custom objects,
in an interactive tree-like view within the Sidekick panel.

Its most powerful feature is its integration with `sidekick.ObservableValue`.
When you display an `ObservableValue` using `viz.show()`, the Viz panel will
automatically update itself whenever the data inside the `ObservableValue` changes.
This makes it incredibly easy to watch how your data structures evolve as your
script runs, without needing to manually refresh the display.

This module also contains the complex internal logic (`_get_representation`)
needed to convert Python data into a format suitable for display in the
Sidekick UI, handling things like nested structures, circular references,
and large collections.
"""

import functools
from typing import Any, Dict, Optional, List, Union, Callable, Set, Tuple
from . import logger
from .base_module import BaseModule
from .observable_value import ObservableValue, UnsubscribeFunction, SubscriptionCallback

# --- Internal Constants for Representation Generation ---
# These control how deep and how many items the _get_representation function
# will explore within nested data structures to avoid infinite loops or
# sending excessively large amounts of data to the UI.
_MAX_DEPTH = 5  # How many levels deep into nested objects/lists/dicts to go.
_MAX_ITEMS = 50 # Max number of items (list elements, dict key-value pairs, set items, object attributes) to show per level.

# --- Representation Helper Function (Internal Use) ---

def _get_representation(
    data: Any,
    depth: int = 0,
    visited_ids: Optional[Set[int]] = None
) -> Dict[str, Any]:
    """Converts Python data into a structured, JSON-serializable dictionary for the Viz UI.

    This is a complex internal helper function used by `Viz.show()` and
    `_handle_observable_update()`. It recursively traverses Python data
    structures (lists, dicts, sets, objects) and creates a representation
    that the Sidekick frontend can understand and display as an interactive tree.

    It handles:
    - Basic types (int, str, bool, None).
    - Lists, tuples, sets, dictionaries.
    - Custom object attribute inspection (skipping methods and private attributes).
    - Recursion/circular references (detects and marks them).
    - Maximum depth (`_MAX_DEPTH`) to prevent infinite recursion in deep structures.
    - Maximum items per collection (`_MAX_ITEMS`) to keep payloads manageable.
    - Special handling for `ObservableValue` instances (inspects the wrapped value
      and marks the node as observable).

    Note:
        This function is for internal library use. Its output format is specific
        to the Sidekick communication protocol and UI component.

    Args:
        data (Any): The Python data to represent.
        depth (int): The current recursion depth (starts at 0).
        visited_ids (Optional[Set[int]]): A set containing the `id()` of objects
            already visited in the current traversal path, used to detect recursion.

    Returns:
        Dict[str, Any]: A dictionary representing the data, suitable for sending
            as part of the Viz module payload. Keys in the returned dictionary
            and nested dictionaries should follow the `camelCase` convention
            expected by the protocol/UI where appropriate (e.g., 'observableTracked').
    """
    # Initialize visited set for the top-level call.
    if visited_ids is None: visited_ids = set()

    # Get the memory ID of the current data item.
    current_id = id(data)

    # --- Termination Conditions for Recursion/Depth ---
    if depth > _MAX_DEPTH:
        return {
            'type': 'truncated',
            'value': f'<Max Depth {_MAX_DEPTH} Reached>',
            'id': f'trunc_{current_id}_{depth}' # Unique ID for truncated node
        }
    if current_id in visited_ids:
        return {
            'type': 'recursive_ref',
            'value': f'<Recursive Reference: {type(data).__name__}>',
            'id': f'rec_{current_id}_{depth}' # Unique ID for recursive node
        }

    # --- Prepare the Representation Dictionary ---
    rep: Dict[str, Any] = {}
    data_type_name = type(data).__name__
    # Default ID, might be overridden (e.g., for ObservableValue).
    rep['id'] = f"{data_type_name}_{current_id}_{depth}"
    rep['type'] = data_type_name
    rep['observableTracked'] = False # Assume not observable by default.

    try:
        # Mark this object ID as visited for the current path.
        visited_ids.add(current_id)

        # --- Handle Different Python Types ---

        if isinstance(data, ObservableValue):
            # If it's an ObservableValue, get its *internal* value and represent that.
            internal_value = data.get()
            # Recursively call _get_representation on the internal value.
            # Use the *same* depth, as the wrapper itself doesn't add a level.
            nested_rep = _get_representation(internal_value, depth, visited_ids.copy())
            # Mark the resulting node to indicate it came from an ObservableValue.
            nested_rep['observableTracked'] = True # camelCase for protocol
            # Try to use the ObservableValue's persistent internal ID for stability.
            obs_id = getattr(data, '_obs_value_id', None)
            nested_rep['id'] = obs_id if obs_id else nested_rep.get('id', f"obs_{current_id}_{depth}")
            return nested_rep # Return the representation of the *inner* value

        elif data is None:
            rep['value'] = 'None'
            rep['type'] = 'NoneType'
        elif isinstance(data, (str, int, float, bool)):
            # Primitive types: just store the value directly.
            rep['value'] = data
        elif isinstance(data, (list, tuple)):
            rep['type'] = 'list' # Treat tuples as lists for display
            rep['value'] = [] # Store representations of items here
            rep['length'] = len(data)
            count = 0
            for item in data:
                if count >= _MAX_ITEMS:
                    # Stop if we exceed the max items limit.
                    rep['value'].append({
                        'type': 'truncated',
                        'value': f'... ({len(data)} items total, showing {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_trunc_{count}'
                    })
                    break
                # Recursively represent each item, incrementing depth. Pass copy of visited.
                rep['value'].append(_get_representation(item, depth + 1, visited_ids.copy()))
                count += 1
        elif isinstance(data, dict):
            rep['type'] = 'dict'
            rep['value'] = [] # Store {key: rep, value: rep} pairs
            rep['length'] = len(data)
            count = 0
            # Try to sort dict items by key's repr for consistent display order.
            try:
                # Make sure keys are representable before sorting
                items_to_sort = [(repr(k), k, v) for k, v in data.items()]
                sorted_items = sorted(items_to_sort)
                processed_items = [(k,v) for _, k, v in sorted_items]
            except Exception:
                # Fallback if keys aren't comparable or repr fails
                logger.debug(f"Could not sort dict keys for {data_type_name} (id: {current_id}). Using original order.")
                processed_items = list(data.items())

            for k, v in processed_items:
                if count >= _MAX_ITEMS:
                     rep['value'].append({
                        'key': {'type': 'truncated', 'value': '...', 'id': f'{rep["id"]}_keytrunc_{count}'},
                        'value': {'type': 'truncated', 'value': f'... ({len(data)} items total, showing {_MAX_ITEMS})', 'id': f'{rep["id"]}_valtrunc_{count}'}
                    })
                     break
                # Represent both the key and the value recursively. Pass copy of visited.
                key_rep = _get_representation(k, depth + 1, visited_ids.copy())
                value_rep = _get_representation(v, depth + 1, visited_ids.copy())
                rep['value'].append({'key': key_rep, 'value': value_rep})
                count += 1
        elif isinstance(data, set):
            rep['type'] = 'set'
            rep['value'] = []
            rep['length'] = len(data)
            count = 0
            # Try to sort set items by repr for consistency.
            try:
                # Convert items to repr first for sorting
                items_to_sort = [(repr(item), item) for item in data]
                sorted_items = sorted(items_to_sort)
                processed_items = [item for _, item in sorted_items]
            except Exception:
                logger.debug(f"Could not sort set items for {data_type_name} (id: {current_id}). Using original order.")
                processed_items = list(data)

            for item in processed_items:
                if count >= _MAX_ITEMS:
                    rep['value'].append({
                        'type': 'truncated',
                        'value': f'... ({len(data)} items total, showing {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_trunc_{count}'
                    })
                    break
                # Represent each item recursively. Pass copy of visited.
                rep['value'].append(_get_representation(item, depth + 1, visited_ids.copy()))
                count += 1
        else:
            # --- Generic Object Inspection ---
            rep['type'] = f"object ({data_type_name})"
            # Use a dictionary to store attribute_name: attribute_representation pairs.
            rep['value'] = {}
            attribute_count = 0
            skipped_attrs = 0
            attrs_to_represent = {}

            # Try to get attributes using dir()
            try:
                for attr_name in dir(data):
                     # Skip private/magic attributes and callable methods.
                     if attr_name.startswith('_') or callable(getattr(data, attr_name, None)):
                        continue
                     try:
                         # Store the actual attribute value for later processing.
                         attrs_to_represent[attr_name] = getattr(data, attr_name)
                     except Exception:
                         # Count attributes we couldn't access.
                         skipped_attrs += 1

                # Length is the number of attributes we plan to represent.
                rep['length'] = len(attrs_to_represent)
                # Try sorting attributes alphabetically for consistent display.
                try: sorted_attr_items = sorted(attrs_to_represent.items())
                except TypeError: sorted_attr_items = list(attrs_to_represent.items()) # Fallback

                # Represent each accessible, non-callable attribute.
                for attr_name, attr_value in sorted_attr_items:
                    if attribute_count >= _MAX_ITEMS:
                        rep['value']['...'] = { # Use '...' as a key for the truncated message
                            'type': 'truncated',
                            'value': f'... ({len(attrs_to_represent)} attrs total, showing {_MAX_ITEMS})',
                            'id': f'{rep["id"]}_attrtrunc_{attribute_count}'
                        }
                        break
                    # Represent attribute value recursively. Pass copy of visited.
                    rep['value'][attr_name] = _get_representation(attr_value, depth + 1, visited_ids.copy())
                    attribute_count += 1

                # If we couldn't find/represent any attributes, fall back to repr().
                if attribute_count == 0 and skipped_attrs == 0 and not rep['value']:
                     logger.debug(f"Object {data_type_name} (id: {current_id}) has no representable attributes. Falling back to repr().")
                     rep['value'] = repr(data)
                     rep['type'] = f"repr ({data_type_name})" # Indicate it's just the repr string.

            except Exception as e_obj:
                # Catch errors during the dir()/getattr() process.
                logger.warning(f"Could not fully inspect object attributes for {data_type_name} (id: {current_id}): {e_obj}")
                # Fall back to repr() as a last resort.
                try:
                    rep['value'] = repr(data)
                    rep['type'] = f"repr ({data_type_name})"
                except Exception as e_repr_final:
                    # If even repr() fails.
                    rep['value'] = f"<Object of type {data_type_name}, repr() failed: {e_repr_final}>"
                    rep['type'] = 'error'

    except Exception as e:
        # Catch any unexpected error during representation generation.
        logger.exception(f"Error generating representation for type {data_type_name} (id: {current_id})")
        rep['type'] = 'error'
        rep['value'] = f"<Error representing object: {e}>"
        # Ensure ID exists even in error cases.
        rep['id'] = rep.get('id', f"error_{current_id}_{depth}")
    finally:
        # **Crucial:** Remove the current object's ID from the visited set
        # *after* exploring this path. This allows the same object to be
        # visited again via different paths in the data structure.
        if current_id in visited_ids:
            visited_ids.remove(current_id)

    return rep


# --- Viz Module Class ---

class Viz(BaseModule):
    """Represents the Variable Visualizer (Viz) module instance in Sidekick.

    Use this class to display Python variables and data structures in an
    interactive, collapsible tree view within the Sidekick UI panel. It helps
    you inspect the state of your data as your script runs.

    The most powerful feature is its integration with `sidekick.ObservableValue`.
    If you `.show()` an `ObservableValue`, the Viz panel will **automatically
    update** whenever the wrapped data changes (e.g., list append, dict setitem).
    This provides a *live*, *reactive* view of your data's state.

    Attributes:
        target_id (str): The unique identifier for this Viz panel instance.
    """
    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True
    ):
        """Initializes the Viz object and optionally creates the UI panel.

        Args:
            instance_id (Optional[str]): A specific ID for this Viz panel.
                - If `spawn=True` (default): Optional. Auto-generated if None.
                - If `spawn=False`: **Required**. Must match the ID of an existing panel.
            spawn (bool): If True (default), creates a new, empty Viz panel UI
                element in Sidekick. If False, attaches to an existing panel.

        Raises:
            ValueError: If `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established.

        Examples:
            >>> # Create a new Viz panel
            >>> viz_panel = sidekick.Viz()
            >>>
            >>> # Attach to an existing panel named "debugger-vars"
            >>> existing_viz = sidekick.Viz(instance_id="debugger-vars", spawn=False)
        """
        # Viz spawn command currently doesn't require a payload.
        spawn_payload = {} if spawn else None
        # Initialize the base class.
        super().__init__(
            module_type="viz",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload
        )
        # Internal dictionary to keep track of variables currently being displayed
        # and their associated cleanup functions (for ObservableValue).
        # Format: { variable_name: {"value_or_observable": actual_value, "unsubscribe": function_or_None} }
        self._shown_variables: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Viz panel '{self.target_id}' initialized (spawn={spawn}).")

    # --- Internal Message Handling ---
    # Inherits _internal_message_handler from BaseModule.
    # Currently, the Viz UI doesn't send any specific 'event' messages back,
    # so we only need the base class's error handling.

    # --- Error Callback ---
    # Inherits on_error(callback) method from BaseModule. Use this to handle
    # potential errors reported by the Viz UI element itself.

    def _handle_observable_update(self, variable_name: str, change_details: Dict[str, Any]):
        """Internal callback method triggered by changes in a subscribed ObservableValue.

        This function is automatically called by an `ObservableValue` instance
        when its wrapped data is modified (e.g., via `append`, `__setitem__`).
        It receives details about the change, converts the relevant data into
        the required representation format, and sends an 'update' command to the
        Sidekick Viz UI.

        Args:
            variable_name (str): The name under which the `ObservableValue` was
                originally shown using `viz.show()`.
            change_details (Dict[str, Any]): A dictionary provided by the
                `ObservableValue` describing the change (e.g., type, path,
                new value, old value).
        """
        logger.debug(f"Viz '{self.target_id}': Received observable update for '{variable_name}': {change_details}")
        try:
            # Extract details from the notification.
            action_type = change_details.get("type", "unknown") # e.g., 'setitem', 'append'
            path = change_details.get("path", []) # Path within the data structure (list indices, dict keys)

            # --- Prepare Payload Options ---
            # Convert involved values/keys into representations for the UI.
            # Keys here *must* be camelCase for the protocol.
            options: Dict[str, Any] = {
                "path": path # Path is usually just list indices or dict keys
            }
            if "value" in change_details:
                # Represent the new value involved in the change.
                options["valueRepresentation"] = _get_representation(change_details["value"])
            if "key" in change_details: # Relevant for dict operations like setitem.
                options["keyRepresentation"] = _get_representation(change_details["key"])
            if "length" in change_details: # New length after list/dict/set mutation.
                options["length"] = change_details["length"]

            # --- Special Handling for Root Set/Clear ---
            # If the *entire* ObservableValue was replaced (type 'set') or cleared
            # (type 'clear') at the root (path is empty), we need to resend the
            # complete representation of its *new* state.
            if action_type in ["set", "clear"] and not path:
                observable_instance = self._shown_variables.get(variable_name, {}).get('value_or_observable')
                if isinstance(observable_instance, ObservableValue):
                    # Regenerate the full representation of the observable's *current* value.
                    options["valueRepresentation"] = _get_representation(observable_instance)
                    # Ensure the length is also updated for the root object.
                    actual_data = observable_instance.get()
                    try:
                        options["length"] = len(actual_data) if hasattr(actual_data, '__len__') else None
                    except TypeError:
                        options["length"] = None # Handle cases where len() isn't supported
                else:
                    # This might happen if remove_variable was called concurrently. Log and skip.
                    logger.warning(f"Viz '{self.target_id}': ObservableValue for '{variable_name}' not found during root update processing. Skipping update.")
                    return # Avoid sending update if observable is gone

            # --- Construct and Send Update Command ---
            update_payload = {
                "action": action_type,          # The type of change ('setitem', 'append', etc.)
                "variableName": variable_name,  # The top-level variable name being updated
                "options": options              # Contains path, representations, length etc.
            }
            # Send the granular update command to the UI.
            self._send_update(update_payload)

        except Exception as e:
            # Catch errors during update processing to prevent crashing the listener.
            logger.exception(f"Viz '{self.target_id}': Error processing observable update for '{variable_name}'. Change: {change_details}")

    def show(self, name: str, value: Any):
        """Displays or updates a variable in the Viz panel.

        Shows the given `value` under the specified `name` in the Sidekick Viz
        panel. If a variable with the same `name` is already shown, its display
        will be updated to reflect the new `value`.

        **Reactivity:** If the `value` you provide is an instance of
        `sidekick.ObservableValue`, the Viz panel will automatically subscribe
        to changes within that `ObservableValue`. When you modify the data
        *through the `ObservableValue` wrapper* (e.g., `my_obs_list.append(5)`,
        `my_obs_dict['key'] = 'new'`), the Viz panel UI will update automatically
        to show the change, often highlighting the modified part. This provides
        a powerful live view of your data.

        For non-ObservableValues, the display shows a snapshot of the value at
        the time `show()` is called. You need to call `show()` again with the
        same name to update the display if the underlying non-observable value changes.

        Args:
            name (str): The name to display for this variable in the Viz panel
                (e.g., "my_list", "game_state", "counter"). Must be a non-empty string.
            value (Any): The Python variable or value you want to display. This can be
                almost anything: numbers, strings, lists, dicts, sets, custom objects,
                or an `ObservableValue` wrapping one of these.

        Raises:
            ValueError: If `name` is empty or not a string.
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending the command fails.

        Returns:
            None

        Examples:
            >>> # Simple static data
            >>> data = {"count": 10, "enabled": True}
            >>> viz = sidekick.Viz()
            >>> viz.show("configuration", data)
            >>>
            >>> # A reactive list using ObservableValue
            >>> items = sidekick.ObservableValue(['apple', 'banana'])
            >>> viz.show("shopping_list", items)
            >>>
            >>> # Now, changes to 'items' update the UI automatically:
            >>> items.append('orange') # Viz panel updates
            >>> items[0] = 'pear'      # Viz panel updates
            >>>
            >>> # Showing a custom object
            >>> class Player:
            ...     def __init__(self, name): self.name = name; self.hp = 100
            >>> player1 = Player("Hero")
            >>> viz.show("player_stats", player1)
            >>>
            >>> # To update the display for the non-observable 'data':
            >>> data["count"] = 20
            >>> viz.show("configuration", data) # Need to call show() again
        """
        # --- Validate Name ---
        if not isinstance(name, str) or not name:
            msg = "Variable name for viz.show() must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)

        # --- Handle Subscriptions for Reactivity ---
        unsubscribe_func: Optional[UnsubscribeFunction] = None

        # Check if we were previously showing something under this name.
        if name in self._shown_variables:
            previous_entry = self._shown_variables[name]
            # If the *previous* value was an ObservableValue, unsubscribe from it now
            # because we are replacing it with a new value (which might or might not be observable).
            if previous_entry.get('unsubscribe'):
                 logger.debug(f"Viz '{self.target_id}': Unsubscribing previous observable for variable '{name}' before showing new value.")
                 try:
                     previous_entry['unsubscribe']()
                 except Exception as e:
                     logger.error(f"Viz '{self.target_id}': Error during unsubscribe for '{name}': {e}")
                 # Clear the old unsubscribe function immediately after calling it.
                 previous_entry['unsubscribe'] = None

        # Now, check if the *new* value is an ObservableValue.
        if isinstance(value, ObservableValue):
            # If it is, subscribe to its changes. The callback will include the variable name.
            # Use functools.partial to bind the current `name` to the callback handler.
            update_callback = functools.partial(self._handle_observable_update, name)
            try:
                # Store the returned unsubscribe function so we can call it later
                # if this variable is shown again or removed.
                unsubscribe_func = value.subscribe(update_callback)
                logger.info(f"Viz '{self.target_id}': Subscribed to ObservableValue for variable '{name}'.")
            except Exception as e:
                 # Log if subscription fails, but proceed without reactivity for this variable.
                 logger.error(f"Viz '{self.target_id}': Failed to subscribe to ObservableValue for '{name}': {e}")
                 unsubscribe_func = None # Ensure it's None on failure

        # Store the new value (or ObservableValue wrapper) and its unsubscribe function (if any).
        # This overwrites any previous entry for 'name'.
        self._shown_variables[name] = {'value_or_observable': value, 'unsubscribe': unsubscribe_func}
        # --- End Subscription Handling ---

        # --- Generate Initial Representation ---
        try:
            # Convert the value (or the value inside the ObservableValue)
            # into the structured representation for the UI.
            representation = _get_representation(value)
        except Exception as e_repr:
            logger.exception(f"Viz '{self.target_id}': Error generating representation for '{name}'")
            # Create an error representation to display in the UI instead.
            representation = {
                "type": "error",
                "value": f"<Error creating display: {e_repr}>",
                "id": f"error_{name}_{id(value)}" # Basic unique ID
            }

        # Determine the length of the underlying data if possible.
        # If it's an ObservableValue, get the length of the *wrapped* data.
        actual_data = value.get() if isinstance(value, ObservableValue) else value
        data_length = None
        if hasattr(actual_data, '__len__'):
            try:
                data_length = len(actual_data)
            except TypeError:
                pass # len() not supported for this type

        # --- Prepare and Send Initial 'Set' Command ---
        # Send the full representation to initially display or update the variable.
        # Keys in options must be camelCase.
        options: Dict[str, Any] = {
            "path": [], # An empty path means we're setting the root variable.
            "valueRepresentation": representation # The generated structure.
        }
        # Include length if available.
        if data_length is not None:
            options["length"] = data_length

        set_payload = {
            "action": "set",             # Action 'set' replaces the variable display.
            "variableName": name,        # The name to show in the UI.
            "options": options
        }
        self._send_update(set_payload) # Send the command.
        logger.debug(f"Viz '{self.target_id}': Sent 'set' update for variable '{name}'.")

    def remove_variable(self, name: str):
        """Removes a previously shown variable from the Viz panel display.

        If the variable currently shown under this `name` was an `ObservableValue`,
        this method also automatically unsubscribes from its changes, stopping
        any further automatic updates for it.

        Args:
            name (str): The exact name of the variable to remove (the same name
                that was used in the corresponding `show()` call).

        Returns:
            None

        Examples:
            >>> viz = sidekick.Viz()
            >>> temp_data = [1, 2, 3]
            >>> viz.show("temporary_variable", temp_data)
            >>> # ... time passes, data is no longer needed ...
            >>> viz.remove_variable("temporary_variable") # Removes it from Sidekick panel
        """
        # Check if the variable is currently being tracked.
        if name in self._shown_variables:
            entry = self._shown_variables.pop(name) # Remove from our internal tracking.

            # --- Unsubscribe If Necessary ---
            if entry.get('unsubscribe'):
                 logger.info(f"Viz '{self.target_id}': Unsubscribing from observable '{name}' on removal.")
                 try:
                     entry['unsubscribe']() # Call the cleanup function.
                 except Exception as e:
                     # Log errors during unsubscribe but continue removal.
                     logger.error(f"Viz '{self.target_id}': Error during unsubscribe for '{name}' on removal: {e}")

            # --- Send Remove Command to UI ---
            # Keys must be camelCase.
            remove_payload = {
                "action": "removeVariable", # Specific action to remove a top-level variable
                "variableName": name,
                # "options": {} # No options needed for removal currently. Protocol expects options though.
                "options": {} # Send empty options object as per protocol expectation (optional keys)
            }
            self._send_update(remove_payload) # Send the command.
            logger.info(f"Viz '{self.target_id}': Sent remove_variable command for '{name}'.")
        else:
            # Variable wasn't found, maybe already removed or never shown.
            logger.warning(f"Viz '{self.target_id}': Variable '{name}' not found for removal. Maybe it was already removed?")

    def remove(self):
        """Removes the entire Viz panel instance from the Sidekick UI.

        This cleans up all variables currently displayed in this specific Viz
        panel and automatically unsubscribes from any `ObservableValue` instances
        that were being tracked by it.
        """
        logger.info(f"Requesting removal of Viz panel '{self.target_id}'.")

        # --- Unsubscribe from ALL tracked observables FIRST ---
        # Iterate over a copy of the keys because we're modifying the dictionary.
        for name in list(self._shown_variables.keys()):
            entry = self._shown_variables.pop(name) # Remove from tracking
            if entry.get('unsubscribe'):
                 logger.debug(f"Viz '{self.target_id}': Unsubscribing from '{name}' during panel removal.")
                 try:
                     entry['unsubscribe']()
                 except Exception as e:
                     logger.error(f"Viz '{self.target_id}': Error unsubscribing from '{name}' during panel remove: {e}")

        # Now call the base class's remove() method, which sends the 'remove' command
        # for the whole module instance and cleans up base class resources.
        super().remove()

    def _reset_specific_callbacks(self):
        """Resets Viz-specific state (subscriptions) when the module is removed.

        Note:
            The actual unsubscribing logic is currently handled directly within
            the overridden `remove()` method for Viz to ensure it happens *before*
            the base `remove()` command is sent. This method primarily just
            clears the tracking dictionary.
        """
        # Called by BaseModule.remove()
        self._shown_variables.clear()