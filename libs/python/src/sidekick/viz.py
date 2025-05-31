"""Provides the Viz class for visualizing Python variables in Sidekick.

Use the `sidekick.Viz` class to create an interactive, tree-like display of your
Python variables within the Sidekick panel in VS Code. This is incredibly helpful
for understanding the state and structure of your data, especially complex objects,
lists, dictionaries, and sets, as your script executes.

The Viz panel can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization, or by adding it as a child
to a container's constructor. You can also provide an `instance_id` to uniquely
identify the Viz panel.

Key Features:

*   **Variable Inspection:** Display almost any Python variable (`int`, `str`, `list`,
    `dict`, `set`, custom objects) using the `show()` method. The Viz panel presents
    nested structures in a collapsible tree view.
*   **Reactivity (with ObservableValue):** The most powerful feature! If you wrap
    your mutable data (lists, dicts, sets) in `sidekick.ObservableValue` before
    showing it (`viz.show("my_data", sidekick.ObservableValue(data))`), the Viz
    panel will **automatically update** its display whenever you modify the data
    through the `ObservableValue` wrapper. Changes are often highlighted, making
    it easy to see exactly what happened.
*   **Clear Display:** Handle large collections and deep nesting by truncating the
    display automatically. Detect and visualize recursive references to prevent
    infinite loops.
*   **Variable Removal:** Remove variables from the display when they are no longer
    needed using `remove_variable()`.

Basic Usage:
    >>> import sidekick
    >>> viz = sidekick.Viz(instance_id="main-data-viewer")
    >>> my_config = {"user": "Alice", "settings": {"theme": "dark", "level": 5}}
    >>> viz.show("App Config", my_config)

Reactive Usage with a Parent Container:
    >>> import sidekick
    >>> my_column = sidekick.Column()
    >>> viz_in_col = sidekick.Viz(parent=my_column, instance_id="reactive-viz")
    >>> reactive_list = sidekick.ObservableValue([10, 20])
    >>> viz_in_col.show("Reactive List", reactive_list)
    >>> reactive_list.append(30) # Viz updates automatically
    >>> # sidekick.run_forever() # Needed for ObservableValue updates in some scenarios
"""

import functools
from typing import Any, Dict, Optional, List, Union, Callable, Set, Tuple, Coroutine
from . import logger
from .component import Component
from .events import ErrorEvent
from .observable_value import ObservableValue, UnsubscribeFunction

# Constants for controlling the depth and item count in the representation.
# These help prevent excessively large messages and UI overload.
_MAX_DEPTH = 5    # Maximum recursion depth when visualizing nested structures.
_MAX_ITEMS = 50   # Maximum number of items (list elements, dict entries, set items, object attributes)
                  # to show before truncating.


def _get_representation(
    data: Any,
    depth: int = 0,
    visited_ids: Optional[Set[int]] = None # Set of id(obj) to detect recursion
) -> Dict[str, Any]:
    """Converts Python data into a structured dictionary for the Viz UI. (Internal).

    This recursive function takes arbitrary Python data and transforms it into
    a nested dictionary structure. This structure is designed to be easily
    serialized to JSON and then interpreted by the Sidekick Viz frontend component
    to render the interactive tree view.

    It handles:
    - Basic types (int, str, float, bool, None).
    - Collections (list, tuple, dict, set), including truncation (`_MAX_ITEMS`).
    - `ObservableValue` instances by unwrapping them and marking them.
    - Custom objects by inspecting their non-callable, non-private attributes.
    - Recursion detection to prevent infinite loops (`visited_ids`).
    - Depth limiting to prevent overly deep traversals (`_MAX_DEPTH`).

    Args:
        data (Any): The Python data to represent.
        depth (int): Current recursion depth, used for `_MAX_DEPTH` check.
        visited_ids (Optional[Set[int]]): A set containing the `id()` of objects
            already visited in the current branch of the traversal. This is crucial
            for detecting and correctly representing circular references.

    Returns:
        Dict[str, Any]: A dictionary representing the data's structure and value,
            adhering to the format expected by the Viz UI. Key fields include:
            'type' (e.g., "list", "dict", "object (ClassName)", "truncated"),
            'value' (the actual data or a representation of it),
            'id' (a unique string for this node in the tree, for UI state),
            'length' (for collections), and 'observableTracked' (boolean).
    """
    # Initialize visited_ids for the top-level call.
    if visited_ids is None:
        visited_ids = set()

    current_id = id(data) # Get memory address for recursion detection and unique ID generation.

    # --- Termination Conditions for Recursion ---
    if depth > _MAX_DEPTH:
        return {
            'type': 'truncated', # Special type indicating truncation
            'value': f'<Max Depth {_MAX_DEPTH} Reached>',
            'id': f'trunc_{current_id}_{depth}' # Unique ID for this truncated node
        }
    if current_id in visited_ids:
        return {
            'type': 'recursive_ref', # Special type for circular references
            'value': f'<Recursive Reference to {type(data).__name__} object>',
            'id': f'rec_{current_id}_{depth}' # Unique ID for this recursive reference node
        }

    # --- Basic Setup for Representation Dictionary ---
    rep: Dict[str, Any] = {}
    data_type_name = type(data).__name__
    # Generate a unique ID for this node in the Viz tree.
    # Combines type, memory ID, and depth to help ensure uniqueness.
    rep['id'] = f"{data_type_name}_{current_id}_{depth}"
    rep['type'] = data_type_name # Store the Python type name
    rep['observableTracked'] = False # Default, can be overridden for ObservableValues

    try:
        # Add current object's ID to visited set before recursing into its children/attributes.
        visited_ids.add(current_id)

        # --- Type-Specific Representation Logic ---

        if isinstance(data, ObservableValue):
            # If data is an ObservableValue, get its underlying value and represent that.
            # Mark it as 'observableTracked' so the UI can treat it specially.
            internal_value = data.get()
            # Recursively get representation of the internal value.
            # Pass a *copy* of visited_ids to ensure siblings don't interfere with recursion detection.
            nested_rep = _get_representation(internal_value, depth, visited_ids.copy())
            nested_rep['observableTracked'] = True
            # Use the ObservableValue's own stable ID if available, for better UI state persistence.
            obs_id = getattr(data, '_obs_value_id', None)
            nested_rep['id'] = obs_id if obs_id else nested_rep.get('id', f"obs_{current_id}_{depth}")
            return nested_rep # Return the representation of the *wrapped* value.

        elif data is None:
            rep['value'] = 'None' # Special string for None
            rep['type'] = 'NoneType' # Consistent type name for None
        elif isinstance(data, (str, int, float, bool)):
            # For basic immutable types, the value is itself.
            rep['value'] = data
        elif isinstance(data, (list, tuple)):
            rep['type'] = 'list' # Treat tuples as lists for display consistency
            list_value_rep = []
            rep['length'] = len(data) # Store original length
            count = 0
            for item in data:
                if count >= _MAX_ITEMS: # Truncate if too many items
                    list_value_rep.append({
                        'type': 'truncated',
                        'value': f'... ({len(data)} items total, showing first {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_trunc_{count}'
                    })
                    break
                list_value_rep.append(_get_representation(item, depth + 1, visited_ids.copy()))
                count += 1
            rep['value'] = list_value_rep
        elif isinstance(data, dict):
            rep['type'] = 'dict'
            dict_value_rep = []
            rep['length'] = len(data) # Store original length
            count = 0
            # Attempt to sort dictionary items by a string representation of their keys
            # for a more consistent display order in the UI.
            try:
                # Create (repr(key), key, value) tuples for sorting
                items_to_sort = [(repr(k), k, v) for k, v in data.items()]
                sorted_items = sorted(items_to_sort) # Sort by repr(key)
                processed_items = [(k, v) for _, k, v in sorted_items] # Extract (key, value)
            except Exception as sort_err:
                # If sorting fails (e.g., uncomparable key reprs), fall back to original order.
                logger.debug(
                    f"Could not sort dict keys for {data_type_name} (id: {current_id}): {sort_err}. "
                    f"Using original item order."
                )
                processed_items = list(data.items())

            for k, v in processed_items:
                if count >= _MAX_ITEMS: # Truncate if too many items
                     dict_value_rep.append({
                        'key': {'type': 'truncated_key', 'value': '...', 'id': f'{rep["id"]}_keytrunc_{count}'},
                        'value': {'type': 'truncated_val', 'value': f'... ({len(data)} items total, showing first {_MAX_ITEMS})', 'id': f'{rep["id"]}_valtrunc_{count}'}
                     })
                     break
                key_rep = _get_representation(k, depth + 1, visited_ids.copy())
                value_rep = _get_representation(v, depth + 1, visited_ids.copy())
                dict_value_rep.append({'key': key_rep, 'value': value_rep})
                count += 1
            rep['value'] = dict_value_rep
        elif isinstance(data, set):
            rep['type'] = 'set'
            set_value_rep = []
            rep['length'] = len(data) # Store original length
            count = 0
            # Attempt to sort set items by their string representation for consistent display.
            try:
                items_to_sort = [(repr(item), item) for item in data]
                sorted_items = sorted(items_to_sort)
                processed_items = [item for _, item in sorted_items]
            except Exception as sort_err:
                # If sorting fails, fall back to an arbitrary (but still iterated) order.
                logger.debug(
                    f"Could not sort set items for {data_type_name} (id: {current_id}): {sort_err}. "
                    f"Using original iteration order."
                )
                processed_items = list(data) # Convert set to list for iteration

            for item in processed_items:
                if count >= _MAX_ITEMS: # Truncate if too many items
                    set_value_rep.append({
                        'type': 'truncated',
                        'value': f'... ({len(data)} items total, showing first {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_trunc_{count}'
                    })
                    break
                set_value_rep.append(_get_representation(item, depth + 1, visited_ids.copy()))
                count += 1
            rep['value'] = set_value_rep
        else: # Generic object inspection (custom classes, etc.)
            rep['type'] = f"object ({data_type_name})" # Include class name in type
            object_value_rep: Dict[str, Any] = {} # Stores attribute_name: representation
            attribute_count = 0
            skipped_attrs_due_to_error = 0
            attrs_to_process: Dict[str, Any] = {}

            # Try to get attributes using dir()
            try:
                attribute_names = dir(data)
            except Exception:
                attribute_names = [] # Fallback if dir() fails

            # Filter and collect attributes: non-private, non-callable.
            for attr_name in attribute_names:
                 if attr_name.startswith('_'): # Skip private/protected attributes
                     continue
                 try:
                     attr_value = getattr(data, attr_name)
                     if callable(attr_value): # Skip methods/callable attributes
                         continue
                     attrs_to_process[attr_name] = attr_value
                 except Exception:
                     # If getattr fails for some reason, skip this attribute.
                     skipped_attrs_due_to_error += 1

            rep['length'] = len(attrs_to_process) # Number of representable attributes
            # Attempt to sort attributes by name for consistent display.
            try:
                sorted_attr_items = sorted(attrs_to_process.items())
            except TypeError: # Fallback if attribute names are uncomparable
                sorted_attr_items = list(attrs_to_process.items())

            for attr_name, attr_value in sorted_attr_items:
                if attribute_count >= _MAX_ITEMS: # Truncate if too many attributes
                    object_value_rep['...'] = { # Use '...' as a special key for truncation display
                        'type': 'truncated',
                        'value': f'... ({len(attrs_to_process)} attributes total, showing first {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_attrtrunc_{attribute_count}'
                    }
                    break
                object_value_rep[attr_name] = _get_representation(attr_value, depth + 1, visited_ids.copy())
                attribute_count += 1
            rep['value'] = object_value_rep

            # If object has no displayable attributes, or if dir() failed and getattr also failed,
            # fall back to using its string representation (repr).
            if attribute_count == 0 and skipped_attrs_due_to_error == 0 and not object_value_rep and not attribute_names:
                 logger.debug(
                    f"Object {data_type_name} (id: {current_id}) has no representable attributes "
                    f"or dir() failed. Falling back to repr()."
                )
                 try:
                     rep['value'] = repr(data)
                     rep['type'] = f"repr ({data_type_name})" # Indicate it's a repr fallback
                 except Exception as e_repr:
                    # If repr() itself fails, show an error message.
                    logger.warning(f"Failed to get repr() for object {data_type_name} (id: {current_id}): {e_repr}")
                    rep['value'] = f"<Object of type {data_type_name}, repr() failed: {e_repr}>"
                    rep['type'] = 'error' # Mark as an error representation

    except Exception as e_main:
        # Catch-all for any unexpected error during representation generation.
        logger.exception(
            f"Error generating representation for data of type {data_type_name} "
            f"(id: {current_id}) at depth {depth}. Original error: {e_main}"
        )
        rep['type'] = 'error' # Mark as an error representation
        rep['value'] = f"<Error representing object: {e_main}>"
        # Ensure 'id' is present even in error cases for UI stability.
        rep['id'] = rep.get('id', f"error_{current_id}_{depth}")
    finally:
        # CRITICAL: Remove current object's ID from visited set *after* processing
        # its children/attributes. This allows the same object to be correctly
        # represented if it appears multiple times at the same level or in different
        # branches of the data structure (but not in a direct cycle).
        if current_id in visited_ids:
            visited_ids.remove(current_id)
    return rep


class Viz(Component):
    """Represents the Variable Visualizer (Viz) component instance in the Sidekick UI.

    Creates an interactive panel for displaying Python variables and data structures.
    This is particularly useful for inspecting lists, dictionaries, sets, and custom
    objects as your script runs.

    When used with `sidekick.ObservableValue`, the Viz panel can automatically
    update its display when the wrapped data changes, providing a reactive view
    of your program's state.

    The Viz panel can be nested within layout containers like `Row` or `Column`.

    Attributes:
        instance_id (str): The unique identifier for this Viz panel instance.
    """
    def __init__(
        self,
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_error: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
    ):
        """Initializes the Viz object and creates the UI panel.

        This function is called when you create a new Viz panel, for example:
        `data_viewer = sidekick.Viz()`

        It sends a message to the Sidekick UI to display a new variable
        visualization panel.

        Args:
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this Viz panel. If `None`, an ID will be auto-generated. Must be
                unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Row` or `sidekick.Column`) where this Viz panel
                should be placed. If `None` (the default), the Viz panel is added
                to the main Sidekick panel area.
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call if
                an error message related to this specific Viz panel (not necessarily
                the variables it's displaying) occurs in the Sidekick UI. The
                function should accept one `ErrorEvent` object as an argument. The callback can be a regular
                function or a coroutine function (async def). Defaults to `None`.

        Raises:
            ValueError: If the provided `instance_id` is invalid or a duplicate.
            TypeError: If `parent` is an invalid type, or if `on_error` is
                provided but is not a callable function.
        """
        # Viz panel doesn't require any specific configuration options in its spawn payload.
        spawn_payload: Dict[str, Any] = {}

        super().__init__(
            component_type="viz",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        # Internal dictionary to keep track of variables shown in this Viz instance.
        # Key: variable_name (str)
        # Value: Dict{'value_or_observable': actual_value, 'unsubscribe': Optional[UnsubscribeFunction]}
        self._shown_variables: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Viz panel '{self.instance_id}' initialized.") # Use self.instance_id

    def _handle_observable_update(self, variable_name: str, change_details: Dict[str, Any]):
        """Internal callback triggered by an ObservableValue when its wrapped data changes. (Internal).

        This method is registered with an `ObservableValue` when `viz.show()` is
        called with that observable. When the `ObservableValue` detects a change
        (e.g., an item is appended to a list, a dict key is updated), it calls this
        handler.

        This handler then:
        1.  Constructs a partial representation of the changed data (or the full
            representation if it's a root-level 'set' or 'clear').
        2.  Sends an 'update' message to the Sidekick UI with the specific change
            details (action type, path to the change, new value representation, etc.),
            allowing the UI to perform a granular update of the displayed tree.

        Args:
            variable_name (str): The name under which the `ObservableValue` was
                originally shown in this Viz panel.
            change_details (Dict[str, Any]): A dictionary from the `ObservableValue`
                describing the change (e.g., 'type', 'path', 'value', 'key').
        """
        logger.debug(
            f"Viz '{self.instance_id}': Received observable update for " # Use self.instance_id
            f"variable '{variable_name}'. Change details: {change_details}"
        )
        try:
            action_type: str = change_details.get("type", "unknown_update")
            # Path from the root of the variable to the element that changed.
            # e.g., ['my_list', 0] or ['my_dict', 'key1', 'inner_list', 2]
            path: List[Union[str, int]] = change_details.get("path", [])
            options: Dict[str, Any] = {"path": path} # Start building options for the update message

            # If the change details include a 'value', get its representation.
            if "value" in change_details:
                options["valueRepresentation"] = _get_representation(change_details["value"])
            # If a 'key' was involved (e.g., for dict item changes), represent it.
            if "key" in change_details and change_details["key"] is not None:
                options["keyRepresentation"] = _get_representation(change_details["key"])
            # If a new 'length' for a container is provided, include it.
            if "length" in change_details and change_details["length"] is not None:
                options["length"] = change_details["length"]

            # Special handling for root-level 'set' or 'clear' operations on an ObservableValue.
            # In these cases, the entire underlying value of the observable has been replaced or cleared.
            # We need to send a full representation of the new state.
            if action_type in ["set", "clear"] and not path: # 'path' is empty for root changes
                observable_instance = self._shown_variables.get(variable_name, {}).get('value_or_observable')
                if isinstance(observable_instance, ObservableValue):
                    logger.debug(
                        f"Viz '{self.instance_id}': Handling root '{action_type}' for observable '{variable_name}'. "
                        f"Regenerating full representation of its new state."
                    )
                    # Get the new full representation of the observable's content.
                    full_representation = _get_representation(observable_instance)
                    options["valueRepresentation"] = full_representation
                    # Also update the length if the new content is a container.
                    actual_data = observable_instance.get()
                    try:
                        options["length"] = len(actual_data) if hasattr(actual_data, '__len__') else None
                    except TypeError: # Handle cases where len() is not applicable
                        options["length"] = None
                    # Ensure the action type for the UI is 'set' to indicate a full replacement.
                    action_type = "set"
                else:
                    # This shouldn't happen if our internal state is consistent.
                    logger.warning(
                        f"Viz '{self.instance_id}': ObservableValue instance for '{variable_name}' "
                        f"not found during root update processing. Skipping update."
                    )
                    return # Cannot proceed without the observable instance.

            # Construct the final update payload to send to the UI.
            update_payload = {
                "action": action_type,      # e.g., "setitem", "append", "set" (for root)
                "variableName": variable_name, # The top-level name of the variable in Viz
                "options": options          # Contains path, new value representation, etc.
            }
            self._send_update(update_payload) # Send the granular update to the UI
        except Exception as e:
            # Log any errors during the processing of an observable update.
            logger.exception(
                f"Viz '{self.instance_id}': Error processing observable update for variable " # Use self.instance_id
                f"'{variable_name}'. Change details were: {change_details}. Error: {e}"
            )

    def show(self, name: str, value: Any):
        """Displays or updates a Python variable in this Sidekick Viz panel.

        Call this method to make a Python variable visible in the Viz panel.
        If a variable with the same `name` was already shown, its display will
        be updated to reflect the new `value`.

        If the `value` you provide is an instance of `sidekick.ObservableValue`,
        the Viz panel will automatically subscribe to changes in that observable.
        This means that when you modify the data *through* the `ObservableValue`
        wrapper (e.g., `my_observable_list.append(item)`), the Viz display will
        update in real-time without needing to call `viz.show()` again.

        For non-observable values, you must call `viz.show()` again with the
        same `name` if the `value` changes and you want the Viz panel to reflect
        that change.

        Args:
            name (str): The name to display for this variable in the Viz panel.
                This name acts as the identifier for the variable within this
                Viz instance. It must be a non-empty string.
            value (Any): The Python variable or value you want to visualize.
                This can be any Python object (numbers, strings, lists, dicts,
                sets, custom objects, or `ObservableValue` instances).

        Raises:
            ValueError: If the provided `name` is empty or not a string.
            SidekickConnectionError: If sending the command to the UI fails.
        """
        if not isinstance(name, str) or not name:
            msg = "Variable name provided to viz.show() must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)

        unsubscribe_func: Optional[UnsubscribeFunction] = None # To store unsubscribe for new observable

        # If this variable name was previously shown, we might need to unsubscribe
        # from an old ObservableValue associated with it.
        if name in self._shown_variables:
            previous_entry = self._shown_variables[name]
            previous_unsubscribe_func = previous_entry.get('unsubscribe')
            if previous_unsubscribe_func:
                 logger.debug(
                    f"Viz '{self.instance_id}': Variable '{name}' is being reshown. " # Use self.instance_id
                    f"Unsubscribing from its previous ObservableValue if any."
                 )
                 try:
                     previous_unsubscribe_func() # Call the old unsubscribe function
                 except Exception as e_unsub:
                     # Log error but continue, as we are replacing it anyway.
                     logger.error(
                        f"Viz '{self.instance_id}': Error during unsubscribe for previously shown " # Use self.instance_id
                        f"variable '{name}': {e_unsub}"
                     )
                 # Clear the old unsubscribe function from the entry.
                 previous_entry['unsubscribe'] = None

        # If the new value is an ObservableValue, subscribe to its changes.
        if isinstance(value, ObservableValue):
            # Create a partial function that includes the variable name for the callback.
            # This way, _handle_observable_update knows which top-level variable changed.
            update_callback_with_name = functools.partial(self._handle_observable_update, name)
            try:
                unsubscribe_func = value.subscribe(update_callback_with_name)
                logger.info(
                    f"Viz '{self.instance_id}': Successfully subscribed to ObservableValue " # Use self.instance_id
                    f"for variable '{name}'."
                )
            except Exception as e_sub:
                 # If subscription fails, log it. The variable will be shown but won't be reactive.
                 logger.error(
                    f"Viz '{self.instance_id}': Failed to subscribe to ObservableValue " # Use self.instance_id
                    f"for variable '{name}': {e_sub}. The variable will be displayed "
                    f"statically but will not auto-update."
                 )
                 unsubscribe_func = None # Ensure it's None if subscription failed

        # Store (or update) the variable and its potential unsubscribe function.
        self._shown_variables[name] = {
            'value_or_observable': value, # Store the actual value or ObservableValue instance
            'unsubscribe': unsubscribe_func # Store the function to call to stop listening
        }

        # Generate the initial representation of the value to send to the UI.
        try:
            representation = _get_representation(value)
        except Exception as e_repr:
            # If representation generation fails, create an error representation.
            logger.exception(
                f"Viz '{self.instance_id}': Error generating initial representation for variable '{name}'. " # Use self.instance_id
                f"Displaying an error message in Viz. Original error: {e_repr}"
            )
            representation = {
                "type": "error",
                "value": f"<Error creating display for '{name}': {e_repr}>",
                "id": f"error_{name}_{id(value)}", # Basic ID for error node
                "observableTracked": False
            }

        # Determine the length of the actual data (if applicable) for the payload.
        actual_data_for_len = value.get() if isinstance(value, ObservableValue) else value
        data_length = None
        if hasattr(actual_data_for_len, '__len__') and callable(getattr(actual_data_for_len, '__len__')):
            try:
                data_length = len(actual_data_for_len)
            except TypeError: # Handles objects that have __len__ but it's not applicable (e.g. some custom objects)
                pass

        # Prepare the 'options' for the 'set' command (which shows or updates a variable).
        options: Dict[str, Any] = {
            "path": [], # For a top-level 'set', the path is empty.
            "valueRepresentation": representation # The generated structure for the UI.
        }
        if data_length is not None:
            options["length"] = data_length # Include length if available.

        # Construct and send the 'set' command payload.
        set_payload = {
            "action": "set", # Action to show/update a variable.
            "variableName": name,
            "options": options
        }
        self._send_update(set_payload)
        logger.debug(f"Viz '{self.instance_id}': Sent 'set' update to display/update variable '{name}'.") # Use self.instance_id

    def remove_variable(self, name: str):
        """Removes a previously shown variable from this Viz panel display.

        If the variable was an `ObservableValue`, this method will also automatically
        unsubscribe the Viz panel from its updates. Calling this for a variable
        name that is not currently shown has no effect and logs a warning.

        Args:
            name (str): The exact name of the variable to remove from the Viz display,
                as previously used in `viz.show(name, ...)`.

        Raises:
            SidekickConnectionError: If sending the command to the UI fails.
        """
        if name in self._shown_variables:
            entry_to_remove = self._shown_variables.pop(name) # Remove from internal tracking
            unsubscribe_func = entry_to_remove.get('unsubscribe')
            if unsubscribe_func:
                 logger.info(
                    f"Viz '{self.instance_id}': Unsubscribing from observable for variable " # Use self.instance_id
                    f"'{name}' as it is being removed from display."
                 )
                 try:
                     unsubscribe_func() # Cleanly stop listening to the observable
                 except Exception as e_unsub:
                     logger.error(
                        f"Viz '{self.instance_id}': Error during unsubscribe for variable '{name}' " # Use self.instance_id
                        f"on its removal: {e_unsub}"
                     )

            # Send command to UI to remove the variable from its display.
            remove_payload = {
                "action": "removeVariable", # Protocol action for removing a variable
                "variableName": name,
                "options": {} # No specific options needed for removeVariable
            }
            self._send_update(remove_payload)
            logger.info(f"Viz '{self.instance_id}': Sent 'removeVariable' command for variable '{name}'.") # Use self.instance_id
        else:
            logger.warning(
                f"Viz '{self.instance_id}': Attempted to remove variable '{name}', " # Use self.instance_id
                f"but it was not found in the list of currently shown variables. Ignoring."
            )

    def remove(self):
        """Removes the entire Viz panel instance from the Sidekick UI.

        This also ensures that the Viz panel unsubscribes from all
        `ObservableValue` instances it was tracking, preventing potential
        memory leaks or unwanted callbacks after the panel is gone.
        """
        logger.info(
            f"Requesting removal of Viz panel '{self.instance_id}'. " # Use self.instance_id
            f"Unsubscribing from all {len(self._shown_variables)} tracked observable variables."
        )
        # Iterate over a copy of the keys because we are modifying the dictionary.
        all_tracked_variable_names = list(self._shown_variables.keys())
        for name in all_tracked_variable_names:
            entry = self._shown_variables.pop(name, None) # Remove from tracking
            if entry:
                unsubscribe_func = entry.get('unsubscribe')
                if unsubscribe_func:
                     logger.debug(
                        f"Viz '{self.instance_id}': Unsubscribing from observable for variable '{name}' " # Use self.instance_id
                        f"during full panel removal."
                     )
                     try:
                         unsubscribe_func()
                     except Exception as e:
                         # Log error but continue cleanup.
                         logger.error(
                            f"Viz '{self.instance_id}': Error unsubscribing from variable '{name}' " # Use self.instance_id
                            f"during full panel removal: {e}"
                         )
        # Ensure the dictionary is clear after iterating.
        self._shown_variables.clear()
        # Call the base class's remove() method to send the 'remove' command for the Viz panel itself.
        super().remove()

    def _reset_specific_callbacks(self):
        """Internal: Resets Viz-specific state, primarily clearing tracked variables.

        Called by `Component.remove()`. For Viz, the main cleanup of
        `_shown_variables` (including unsubscribing from observables) is more
        robustly handled in the overridden `Viz.remove()` method to ensure it
        happens *before* the UI component is instructed to remove itself.
        This method serves as a final explicit clear if `Viz.remove()` logic
        was somehow bypassed, though that shouldn't normally occur.
        """
        super()._reset_specific_callbacks() # Call base class method
        # Clear the dictionary of shown variables. Unsubscribing should have
        # ideally happened in the overridden remove() method.
        if self._shown_variables: # Check if not already cleared by self.remove()
            logger.debug(
                f"Viz '{self.instance_id}': _reset_specific_callbacks called. " # Use self.instance_id
                f"Clearing _shown_variables (count: {len(self._shown_variables)}). "
                f"Unsubscriptions should have occurred in Viz.remove()."
            )
            self._shown_variables.clear()
        else:
            logger.debug(f"Viz '{self.instance_id}': _shown_variables already clear in _reset_specific_callbacks.") # Use self.instance_id


    # Viz component primarily sends data to the UI. It doesn't typically receive
    # interactive events (like clicks on variable nodes) back from the UI that would
    # trigger Python callbacks, other than generic 'error' messages handled by Component.
    # Thus, no specific _internal_message_handler override is usually needed beyond base.

    # __del__ is inherited from Component for fallback handler unregistration.
