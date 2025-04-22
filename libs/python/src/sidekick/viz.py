"""Provides the Viz class for visualizing Python variables in Sidekick.

Use the `sidekick.Viz` class to create an interactive, tree-like display of your
Python variables within the Sidekick panel in VS Code. This is incredibly helpful
for understanding the state and structure of your data, especially complex objects,
lists, dictionaries, and sets, as your script executes.

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

Basic Usage (Static Variable):
    >>> import sidekick
    >>> viz = sidekick.Viz()
    >>> my_config = {"user": "Alice", "settings": {"theme": "dark", "level": 5}}
    >>> viz.show("App Config", my_config)
    >>> # To update, you need to call show() again if my_config changes later
    >>> my_config["settings"]["level"] = 6
    >>> viz.show("App Config", my_config) # Manual update needed

Reactive Usage (with ObservableValue):
    >>> import sidekick
    >>> viz = sidekick.Viz()
    >>> reactive_list = sidekick.ObservableValue([10, 20])
    >>> viz.show("Reactive List", reactive_list)
    >>>
    >>> # Now, changes update Viz automatically!
    >>> reactive_list.append(30)
    >>> reactive_list[0] = 100
    >>> # No need to call viz.show() again!

Internal Details:

This module also contains the complex internal logic (`_get_representation`) needed
to convert arbitrary Python data structures into a specific JSON-like format that
the Sidekick frontend UI component can understand and render interactively. This
involves handling nesting, recursion, data types, and observability tracking.
"""

import functools
from typing import Any, Dict, Optional, List, Union, Callable, Set, Tuple
from . import logger
from .base_module import BaseModule
from .observable_value import ObservableValue, UnsubscribeFunction, SubscriptionCallback

# --- Internal Constants for Representation Generation ---
# These constants control the traversal limits during the conversion of
# Python data structures into the displayable representation for the Viz UI.
# They prevent excessive recursion depth and overly large message payloads.

# Maximum depth the _get_representation function will recurse into nested
# data structures (e.g., list of lists of dicts). Prevents infinite loops.
_MAX_DEPTH = 5
# Maximum number of items (list elements, dict key-value pairs, set items,
# object attributes) to include in the representation *at each level* of nesting.
# Prevents sending excessively large data for huge collections.
_MAX_ITEMS = 50

# --- Representation Helper Function (Internal Use Only) ---

def _get_representation(
    data: Any,
    depth: int = 0,
    visited_ids: Optional[Set[int]] = None
) -> Dict[str, Any]:
    """Converts Python data into a structured dictionary for the Viz UI. (Internal).

    This recursive function is the core of the Viz module's data marshalling.
    It takes arbitrary Python data and transforms it into a nested dictionary
    structure that conforms to the format expected by the Sidekick Viz frontend
    component. This structure includes type information, the value representation
    (which might be nested itself), length hints, recursion/truncation markers,
    and observability tracking.

    Key features of the conversion process:

    - Handles standard Python types (primitives, lists, tuples, sets, dicts).
    - Inspects attributes of custom objects (skipping private/callable members).
    - Detects and marks circular references using object IDs (`id()`).
    - Limits recursion depth (`_MAX_DEPTH`) and items per collection (`_MAX_ITEMS`).
    - Unwraps `ObservableValue` instances, represents their internal value, and
      marks the resulting node with `observableTracked=True`.
    - Assigns a unique-ish ID to each node in the representation tree, used by
      the frontend for efficient updates and state management (e.g., preserving
      expanded/collapsed states).

    Note:
        This function is strictly for internal use by the `Viz` class. The exact
        output format is an implementation detail tied to the Viz frontend component
        and the Sidekick communication protocol. Do not rely on this function or its
        output structure directly in user code.

    Args:
        data (Any): The Python data (variable, object, structure) to represent.
        depth (int): The current recursion depth during traversal (starts at 0).
        visited_ids (Optional[Set[int]]): A set containing the memory IDs (`id()`)
            of objects already visited along the *current* traversal path. Used to
            detect circular references. Should be `None` only on the initial call.

    Returns:
        Dict[str, Any]: A dictionary representing the data structure, suitable for
            serialization and interpretation by the Viz frontend. Key fields include
            'type', 'value', 'id', 'length' (optional), 'observableTracked' (optional).
            Nested values within the 'value' field follow the same structure.
            Payload keys intended for the UI follow `camelCase`.
    """
    # Initialize the set for tracking visited object IDs on the first call.
    if visited_ids is None: visited_ids = set()

    # Get the memory address (ID) of the current data item. Used for recursion detection.
    current_id = id(data)

    # --- Termination Conditions: Depth and Recursion ---
    # Stop recursing if maximum depth is exceeded.
    if depth > _MAX_DEPTH:
        return {
            'type': 'truncated', # Special type indicating truncation
            'value': f'<Max Depth {_MAX_DEPTH} Reached>',
            'id': f'trunc_{current_id}_{depth}' # Generate a unique ID for this truncated node
        }
    # Stop recursing if this exact object ID has already been seen *in this path*.
    if current_id in visited_ids:
        return {
            'type': 'recursive_ref', # Special type indicating recursion
            'value': f'<Recursive Reference: {type(data).__name__}>',
            'id': f'rec_{current_id}_{depth}' # Generate a unique ID for this recursion marker
        }

    # --- Prepare the Representation Dictionary ---
    # This dictionary will hold the structured representation of the current 'data'.
    rep: Dict[str, Any] = {}
    data_type_name = type(data).__name__
    # Generate a default unique ID for this node based on type, memory id, and depth.
    # This might be overridden later (e.g., for ObservableValue).
    rep['id'] = f"{data_type_name}_{current_id}_{depth}"
    rep['type'] = data_type_name # Store the Python type name.
    # Default to False, will be set to True if data is/contains ObservableValue.
    rep['observableTracked'] = False # Use camelCase for protocol consistency.

    try:
        # --- Mark as Visited and Handle Different Types ---
        # Add the current object's ID to the visited set *before* recursing into its children.
        visited_ids.add(current_id)

        if isinstance(data, ObservableValue):
            # If the data *is* an ObservableValue wrapper, we don't represent the
            # wrapper itself. Instead, we get its *internal* value and represent that.
            internal_value = data.get()
            # Recursively call _get_representation on the *inner* value.
            # Pass a *copy* of visited_ids to handle separate branches correctly.
            # Crucially, use the *same* depth, as the wrapper itself isn't a level of data nesting.
            nested_rep = _get_representation(internal_value, depth, visited_ids.copy()) # Pass same depth
            # Mark the representation of the inner value to indicate it originated from an ObservableValue.
            nested_rep['observableTracked'] = True # camelCase key for the protocol
            # Try to use the ObservableValue's persistent internal ID (_obs_value_id)
            # for the node ID. This helps Viz maintain state (like expanded nodes)
            # across updates more reliably than using the inner value's potentially
            # changing id().
            obs_id = getattr(data, '_obs_value_id', None) # Access internal ID safely
            nested_rep['id'] = obs_id if obs_id else nested_rep.get('id', f"obs_{current_id}_{depth}")
            # Return the representation of the *inner* value, now marked as observable.
            return nested_rep

        elif data is None:
            rep['value'] = 'None' # Represent None as the string 'None'
            rep['type'] = 'NoneType' # Use a distinct type name for None
        elif isinstance(data, (str, int, float, bool)):
            # Primitive types: the value is just the data itself.
            rep['value'] = data
        elif isinstance(data, (list, tuple)):
            # Represent lists and tuples similarly (as 'list' type for UI).
            rep['type'] = 'list' # Treat tuples like lists for display purposes
            list_value_rep = [] # Store representations of items in this list
            rep['length'] = len(data) # Store original length
            count = 0
            for item in data:
                # Apply item limit.
                if count >= _MAX_ITEMS:
                    list_value_rep.append({
                        'type': 'truncated',
                        'value': f'... ({len(data)} items total, showing first {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_trunc_{count}'
                    })
                    break
                # Recursively represent each item, incrementing depth. Pass copy of visited set.
                list_value_rep.append(_get_representation(item, depth + 1, visited_ids.copy()))
                count += 1
            rep['value'] = list_value_rep # Assign the list of item representations
        elif isinstance(data, dict):
            # Represent dictionaries.
            rep['type'] = 'dict'
            dict_value_rep = [] # Store representations as {key: rep, value: rep} pairs
            rep['length'] = len(data) # Store original length
            count = 0
            # Attempt to sort dict items by a string representation of their keys
            # for a more consistent display order in the UI, especially across updates.
            try:
                # Create tuples (repr(key), key, value) for sorting. repr() handles most types.
                items_to_sort = [(repr(k), k, v) for k, v in data.items()]
                sorted_items = sorted(items_to_sort)
                # Extract the original (key, value) pairs in the sorted order.
                processed_items = [(k, v) for _, k, v in sorted_items]
            except Exception as sort_err:
                # Fallback to original iteration order if sorting fails (e.g., complex keys).
                logger.debug(f"Could not sort dict keys for {data_type_name} (id: {current_id}): {sort_err}. Using original order.")
                processed_items = list(data.items())

            for k, v in processed_items:
                # Apply item limit.
                if count >= _MAX_ITEMS:
                     dict_value_rep.append({
                        # Represent truncation using a special key/value structure
                        'key': {'type': 'truncated_key', 'value': '...', 'id': f'{rep["id"]}_keytrunc_{count}'},
                        'value': {'type': 'truncated_val', 'value': f'... ({len(data)} items total, showing first {_MAX_ITEMS})', 'id': f'{rep["id"]}_valtrunc_{count}'}
                     })
                     break
                # Represent both the key and the value recursively. Pass copy of visited set.
                key_rep = _get_representation(k, depth + 1, visited_ids.copy())
                value_rep = _get_representation(v, depth + 1, visited_ids.copy())
                dict_value_rep.append({'key': key_rep, 'value': value_rep})
                count += 1
            rep['value'] = dict_value_rep # Assign the list of key-value representations
        elif isinstance(data, set):
            # Represent sets.
            rep['type'] = 'set'
            set_value_rep = [] # Store representations of items
            rep['length'] = len(data) # Store original length
            count = 0
            # Attempt to sort set items by their string representation for consistency.
            try:
                # Create tuples (repr(item), item) for sorting.
                items_to_sort = [(repr(item), item) for item in data]
                sorted_items = sorted(items_to_sort)
                # Extract original items in sorted order.
                processed_items = [item for _, item in sorted_items]
            except Exception as sort_err:
                # Fallback to original iteration order if sorting fails.
                logger.debug(f"Could not sort set items for {data_type_name} (id: {current_id}): {sort_err}. Using original order.")
                processed_items = list(data) # Convert set to list for predictable order

            for item in processed_items:
                # Apply item limit.
                if count >= _MAX_ITEMS:
                    set_value_rep.append({
                        'type': 'truncated',
                        'value': f'... ({len(data)} items total, showing first {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_trunc_{count}'
                    })
                    break
                # Represent each item recursively. Pass copy of visited set.
                set_value_rep.append(_get_representation(item, depth + 1, visited_ids.copy()))
                count += 1
            rep['value'] = set_value_rep # Assign the list of item representations
        else:
            # --- Generic Object Inspection (Fallback for other types) ---
            # Try to represent custom objects by inspecting their attributes.
            rep['type'] = f"object ({data_type_name})" # Include original type name
            # Use a dictionary to store attribute_name: attribute_representation pairs.
            object_value_rep: Dict[str, Any] = {}
            attribute_count = 0 # Count of successfully represented attributes
            skipped_attrs = 0 # Count of attributes skipped (private, callable, errors)
            attrs_to_process = {} # Temp dict to hold attributes before recursion

            # Use dir() to get potential attributes, but handle errors gracefully.
            try:
                attribute_names = dir(data)
            except Exception as e_dir:
                logger.warning(f"Could not call dir() on object {data_type_name} (id: {current_id}): {e_dir}. Falling back to repr().")
                attribute_names = [] # Proceed to repr fallback

            # Iterate through potential attributes found by dir().
            for attr_name in attribute_names:
                 # --- Filter Attributes ---
                 # Skip 'private' attributes (by convention).
                 if attr_name.startswith('_'):
                     continue
                 # Attempt to get the attribute value safely.
                 try:
                     attr_value = getattr(data, attr_name)
                     # Skip attributes that are callable (methods).
                     if callable(attr_value):
                         continue
                     # If valid, store it for representation.
                     attrs_to_process[attr_name] = attr_value
                 except Exception as e_getattr:
                     # Log if getattr fails for an attribute (e.g., permissions, dynamic properties).
                     # logger.debug(f"Could not getattr '{attr_name}' from {data_type_name} (id: {current_id}): {e_getattr}")
                     skipped_attrs += 1

            # --- Represent Filtered Attributes ---
            # Store the count of potential attributes we are representing.
            rep['length'] = len(attrs_to_process)
            # Try sorting attributes alphabetically for consistent display order.
            try: sorted_attr_items = sorted(attrs_to_process.items())
            except TypeError: sorted_attr_items = list(attrs_to_process.items()) # Fallback if names not sortable

            for attr_name, attr_value in sorted_attr_items:
                # Apply item limit to attributes.
                if attribute_count >= _MAX_ITEMS:
                    # Use '...' as a special key to indicate truncation.
                    object_value_rep['...'] = {
                        'type': 'truncated',
                        'value': f'... ({len(attrs_to_process)} attributes total, showing first {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_attrtrunc_{attribute_count}'
                    }
                    break
                # Represent the attribute's value recursively. Pass copy of visited set.
                object_value_rep[attr_name] = _get_representation(attr_value, depth + 1, visited_ids.copy())
                attribute_count += 1

            rep['value'] = object_value_rep # Assign the dict of attribute representations

            # --- Handle Empty/Unrepresentable Objects ---
            # If inspection yielded no representable attributes, fall back to using repr().
            if attribute_count == 0 and skipped_attrs == 0 and not object_value_rep:
                 logger.debug(f"Object {data_type_name} (id: {current_id}) has no representable attributes. Falling back to repr().")
                 try:
                     rep['value'] = repr(data)
                     # Change type to indicate it's just the repr string, not an inspectable object.
                     rep['type'] = f"repr ({data_type_name})"
                 except Exception as e_repr:
                    # Handle cases where even repr() fails.
                    logger.warning(f"Failed to get repr() for object {data_type_name} (id: {current_id}): {e_repr}")
                    rep['value'] = f"<Object of type {data_type_name}, repr() failed: {e_repr}>"
                    rep['type'] = 'error'


    except Exception as e_main:
        # Catch any unexpected error during the representation generation for the current 'data'.
        logger.exception(f"Error generating representation for {data_type_name} (id: {current_id}) at depth {depth}")
        # Create a minimal error representation to display in the UI.
        rep['type'] = 'error'
        rep['value'] = f"<Error representing object: {e_main}>"
        # Ensure ID exists even in error cases.
        rep['id'] = rep.get('id', f"error_{current_id}_{depth}")

    finally:
        # **CRUCIAL:** Remove the current object's ID from the visited set *after*
        # processing its branch. This allows the *same* object instance to be
        # correctly represented if it appears again elsewhere in the data structure
        # (e.g., a list containing the same dictionary object twice). It prevents
        # falsely marking subsequent appearances as recursive if they aren't part
        # of the same direct ancestral path.
        if current_id in visited_ids:
            visited_ids.remove(current_id)

    # Return the completed representation dictionary for this node.
    return rep


# --- Viz Module Class ---

class Viz(BaseModule):
    """Represents the Variable Visualizer (Viz) module instance in the Sidekick UI.

    Use this class to create an interactive panel in Sidekick where you can display
    Python variables and data structures. It presents data like lists, dictionaries,
    sets, and even custom objects in a collapsible tree view, making it easy to
    inspect their contents and structure as your script runs.

    The key feature is its integration with `sidekick.ObservableValue`. When you
    display data wrapped in an `ObservableValue` using `viz.show()`, the Viz panel
    will **automatically update** its display whenever the underlying data is
    modified *through the wrapper*. This provides a powerful *live* view of how
    your data changes over time without requiring manual refreshes.

    Attributes:
        target_id (str): The unique identifier for this Viz panel instance.
    """
    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True
    ):
        """Initializes the Viz object and optionally creates the UI panel.

        Sets up the Viz panel instance. Establishes the connection to Sidekick if
        not already done (this might block).

        Args:
            instance_id (Optional[str]): A specific ID for this Viz panel instance.
                - If `spawn=True` (default): Optional. If None, a unique ID (e.g.,
                  "viz-1") is generated automatically.
                - If `spawn=False`: **Required**. Must match the ID of an existing
                  Viz panel element in the Sidekick UI to attach to.
            spawn (bool): If True (the default), a command is sent to Sidekick
                to create a new, empty Viz panel UI element. If False, the
                library assumes a panel with the given `instance_id` already exists,
                and this Python object simply connects to it.

        Raises:
            ValueError: If `spawn` is False and `instance_id` is not provided.
            SidekickConnectionError (or subclass): If the connection to Sidekick
                cannot be established during initialization.

        Examples:
            >>> # Create a new Viz panel
            >>> data_viewer = sidekick.Viz()
            >>>
            >>> # Attach to an existing panel maybe named "debug-variables"
            >>> debug_vars = sidekick.Viz(instance_id="debug-variables", spawn=False)
        """
        # The spawn command for Viz currently doesn't require any specific payload
        # as it just creates the empty panel container.
        spawn_payload = {} if spawn else None
        # Initialize the base class (handles connection, ID, registration, spawn).
        super().__init__(
            module_type="viz",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload
        )
        # --- Internal State for Tracking Shown Variables and Subscriptions ---
        # This dictionary stores information about the variables currently displayed
        # in this Viz instance. It maps the user-provided variable name (str)
        # to another dictionary containing:
        #   - 'value_or_observable': The actual Python value or ObservableValue wrapper.
        #   - 'unsubscribe': The unsubscribe function returned by ObservableValue.subscribe()
        #                    if the value is observable, otherwise None.
        self._shown_variables: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Viz panel '{self.target_id}' initialized (spawn={spawn}).")

    # --- Internal Message Handling ---
    # Inherits _internal_message_handler from BaseModule.
    # Currently, the Viz UI component doesn't send any specific 'event' messages back
    # to the Python script based on user interaction within the tree view (like expanding
    # or collapsing nodes). Therefore, only the base class's 'error' handling is needed.
    # If future versions add interactivity (e.g., editing values), this might need overriding.

    # --- Error Callback ---
    # Inherits the on_error(callback) method directly from BaseModule.
    # Use `viz.on_error(my_handler)` to register a function that will be called
    # if the Viz UI element itself reports an error back to Python (e.g., if it
    # failed to process an 'update' or 'removeVariable' command internally).

    def _handle_observable_update(self, variable_name: str, change_details: Dict[str, Any]):
        """Internal callback triggered by changes in a subscribed ObservableValue. (Internal).

        This method is registered with an `ObservableValue` instance via its `subscribe`
        method when `viz.show()` is called with that observable. It gets executed
        automatically by the `ObservableValue` whenever its wrapped data is modified
        (e.g., via `append`, `__setitem__`, `add`, `clear`).

        Its job is to:

        1. Receive the `change_details` dictionary from the `ObservableValue`, which
           describes precisely what changed (e.g., type of change, path within the
           structure, new value, old value).
        2. Convert the relevant Python values involved in the change (new value, key)
           into the structured representation format required by the Viz UI using the
           `_get_representation` helper function.
        3. Construct an 'update' message payload containing these representations, the
           `variable_name`, the `path` to the change, the `action` type, and potentially
           the new `length` of the container.
        4. Send this granular 'update' command to the Sidekick Viz UI via `_send_update`,
           allowing the UI to efficiently update its display without needing the entire
           variable representation resent.

        Args:
            variable_name (str): The name under which the triggering `ObservableValue`
                was originally displayed using `viz.show()`. Used to target the
                correct top-level variable in the UI.
            change_details (Dict[str, Any]): A dictionary provided by the `ObservableValue`
                describing the specific change that occurred.
        """
        logger.debug(f"Viz '{self.target_id}': Received observable update for variable '{variable_name}': {change_details}")
        try:
            # Extract key information from the change notification.
            action_type = change_details.get("type", "unknown_update") # e.g., 'setitem', 'append', 'add_set'
            # Path is usually a list of indices/keys from the root variable.
            path: List[Union[str, int]] = change_details.get("path", [])

            # --- Prepare Payload Options (camelCase keys for protocol) ---
            # This dictionary will hold the data needed by the UI to apply the granular update.
            options: Dict[str, Any] = {
                "path": path # The location within the variable structure where the change occurred.
            }

            # Convert the *new* value involved in the change (if any) into its representation.
            if "value" in change_details:
                options["valueRepresentation"] = _get_representation(change_details["value"])

            # Convert the *key* involved (if any, e.g., for dict 'setitem') into its representation.
            if "key" in change_details and change_details["key"] is not None:
                options["keyRepresentation"] = _get_representation(change_details["key"])

            # Include the new length of the container (if provided by the ObservableValue).
            if "length" in change_details and change_details["length"] is not None:
                options["length"] = change_details["length"]

            # --- Special Handling for Root Set/Clear ---
            # If the notification was for a 'set' (entire value replaced) or 'clear'
            # operation on the *root* observable itself (path is empty), the granular
            # update isn't sufficient. We need to resend the complete representation
            # of the observable's *new* state to replace the entire display for that variable.
            if action_type in ["set", "clear"] and not path:
                # Retrieve the ObservableValue instance itself from our tracking dict.
                observable_instance = self._shown_variables.get(variable_name, {}).get('value_or_observable')
                if isinstance(observable_instance, ObservableValue):
                    logger.debug(f"Viz '{self.target_id}': Handling root '{action_type}' for '{variable_name}'. Regenerating full representation.")
                    # Regenerate the full representation of the observable's *current* value.
                    full_representation = _get_representation(observable_instance)
                    options["valueRepresentation"] = full_representation # Overwrite with full rep
                    # Also update the length in the options based on the new root value.
                    actual_data = observable_instance.get()
                    try:
                        options["length"] = len(actual_data) if hasattr(actual_data, '__len__') else None
                    except TypeError:
                        options["length"] = None # Handle cases where len() isn't supported
                    # Ensure the action type is 'set' for the UI when replacing the whole thing.
                    action_type = "set"
                else:
                    # This might happen if remove_variable was called concurrently with the notification.
                    logger.warning(f"Viz '{self.target_id}': ObservableValue instance for '{variable_name}' not found during root update processing. Skipping update.")
                    return # Avoid sending update if the observable is no longer tracked.

            # --- Construct and Send Update Command ---
            # Assemble the final payload for the 'update' message.
            update_payload = {
                # The specific type of mutation that occurred (used by UI to apply change).
                "action": action_type,
                # The top-level variable name being updated in the Viz panel.
                "variableName": variable_name,
                # The dictionary containing path, representations, length etc. (camelCase keys).
                "options": options
            }
            # Send the granular update command to the UI using the base class helper.
            self._send_update(update_payload) # Raises on connection error.

        except Exception as e:
            # Catch any errors during the update processing or representation generation
            # to prevent crashing the listener thread. Log the error for debugging.
            logger.exception(f"Viz '{self.target_id}': Error processing observable update "
                             f"for variable '{variable_name}'. Change details: {change_details}")


    def show(self, name: str, value: Any):
        """Displays or updates a variable in the Sidekick Viz panel.

        This is the primary method for sending data to the Viz panel. It shows the
        given Python `value` under the specified `name` in an interactive tree view.

        *   **If `name` is new:** Adds the variable to the Viz panel display.
        *   **If `name` already exists:** Updates the display for that variable to
            reflect the *current* state of the provided `value`.

        **Reactivity with `ObservableValue`:**

        The key feature is how `show()` interacts with `sidekick.ObservableValue`:

        *   If the `value` you pass is **wrapped** in `sidekick.ObservableValue`
            (e.g., `viz.show("My List", sidekick.ObservableValue([1, 2]))`),
            the Viz panel will **automatically subscribe** to changes within that
            `ObservableValue`. Any subsequent modifications made *through the wrapper*
            (e.g., `my_obs_list.append(3)`) will automatically trigger updates in the
            Viz UI, without needing further calls to `viz.show()`.
        *   If the `value` is **not** an `ObservableValue` (e.g., a regular list, dict,
            number, string, or custom object), the Viz panel simply displays a
            **snapshot** of the value at the moment `show()` is called. If the
            underlying data changes later, you **must call `viz.show(name, updated_value)`
            again** with the same `name` to refresh the display in the Sidekick panel.

        Args:
            name (str): The name to display for this variable in the Viz panel header
                (e.g., "my_list", "game_state", "loop_counter"). This acts as the
                unique identifier for the variable within this Viz instance. Must
                be a non-empty string.
            value (Any): The Python variable or value you want to visualize. This
                can be almost any Python object: primitives (int, float, str, bool,
                None), collections (list, dict, set, tuple), custom class instances,
                or, importantly, an `ObservableValue` wrapping one of these types.

        Raises:
            ValueError: If the provided `name` is empty or not a string.
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending the initial 'set' command fails.

        Example:
            >>> import sidekick
            >>> viz = sidekick.Viz()
            >>>
            >>> # --- Showing a non-observable dictionary ---
            >>> config = {"level": 1, "active": True}
            >>> viz.show("Game Config", config)
            >>> # If config changes later...
            >>> config["active"] = False
            >>> # ...Viz panel does NOT update automatically. Need to call show() again:
            >>> viz.show("Game Config", config) # Manually update the display
            >>>
            >>> # --- Showing an observable list ---
            >>> player_scores = sidekick.ObservableValue([100, 95])
            >>> viz.show("Scores", player_scores)
            >>> # Now, changes through the wrapper update Viz automatically:
            >>> player_scores.append(110)
            >>> player_scores[0] = 105
            >>> # No need to call viz.show("Scores", player_scores) again!
        """
        # --- Validate Variable Name ---
        if not isinstance(name, str) or not name:
            msg = "Variable name provided to viz.show() must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)

        # --- Handle Subscription Management for Reactivity ---
        unsubscribe_func: Optional[UnsubscribeFunction] = None # Function to call for cleanup

        # Check if we are replacing a variable previously shown under the same name.
        if name in self._shown_variables:
            previous_entry = self._shown_variables[name]
            previous_unsubscribe = previous_entry.get('unsubscribe')
            # If the *previous* value being displayed was an ObservableValue,
            # we MUST unsubscribe from it now to prevent memory leaks and stop
            # receiving notifications from the old value.
            if previous_unsubscribe:
                 logger.debug(f"Viz '{self.target_id}': Unsubscribing previous observable for variable '{name}' before showing new value.")
                 try:
                     previous_unsubscribe() # Call the stored cleanup function
                 except Exception as e_unsub:
                     # Log errors during unsubscribe but proceed with showing the new value.
                     logger.error(f"Viz '{self.target_id}': Error during unsubscribe call for variable '{name}': {e_unsub}")
                 # Ensure the old unsubscribe function reference is cleared immediately.
                 previous_entry['unsubscribe'] = None

        # Now, check if the *new* value being shown is an ObservableValue.
        if isinstance(value, ObservableValue):
            # If the new value *is* observable, subscribe to its changes.
            # We use functools.partial to create a callback that automatically
            # includes the 'variable_name' when calling our internal handler.
            update_callback = functools.partial(self._handle_observable_update, name)
            try:
                # Call the subscribe method on the ObservableValue. It returns a function
                # that we can call later to unsubscribe.
                unsubscribe_func = value.subscribe(update_callback)
                logger.info(f"Viz '{self.target_id}': Subscribed to ObservableValue changes for variable '{name}'.")
            except Exception as e_sub:
                 # Log if subscription fails, but proceed to show the value statically.
                 logger.error(f"Viz '{self.target_id}': Failed to subscribe to ObservableValue for '{name}': {e_sub}. Variable will be shown but not reactive.")
                 unsubscribe_func = None # Ensure it's None if subscription failed.

        # Store (or update) the tracking information for this variable name.
        # This includes the value/observable itself and the unsubscribe function (if any).
        self._shown_variables[name] = {'value_or_observable': value, 'unsubscribe': unsubscribe_func}
        # --- End Subscription Handling ---

        # --- Generate Initial Representation ---
        # Convert the Python value (or the value inside the ObservableValue)
        # into the nested dictionary structure required by the Viz UI.
        try:
            representation = _get_representation(value)
        except Exception as e_repr:
            # Handle errors during the complex representation generation.
            logger.exception(f"Viz '{self.target_id}': Error generating representation for variable '{name}'")
            # Create a fallback error representation to display in the UI.
            representation = {
                "type": "error",
                "value": f"<Error creating display for '{name}': {e_repr}>",
                "id": f"error_{name}_{id(value)}", # Basic unique ID for the error node
                "observableTracked": False
            }

        # Determine the length of the underlying data, if possible, for display hints.
        # If 'value' is an ObservableValue, get length of the *wrapped* data.
        actual_data = value.get() if isinstance(value, ObservableValue) else value
        data_length = None
        # Check if the actual data supports len()
        if hasattr(actual_data, '__len__') and callable(getattr(actual_data, '__len__')):
            try:
                data_length = len(actual_data) # type: ignore
            except TypeError:
                pass # Handle cases where len() raises TypeError despite having __len__

        # --- Prepare and Send Initial 'Set' Command ---
        # This command tells the UI to display this variable (or update its existing display).
        # It sends the complete initial representation.
        # Keys in options must be camelCase per protocol.
        options: Dict[str, Any] = {
            "path": [], # An empty path signifies setting/updating the root variable itself.
            "valueRepresentation": representation # The generated structure.
        }
        # Include the length hint if available.
        if data_length is not None:
            options["length"] = data_length

        # Construct the full payload for the 'set' action.
        set_payload = {
            "action": "set",             # Action 'set' adds or replaces the variable display.
            "variableName": name,        # The name to show in the Viz panel header.
            "options": options           # Contains the representation and optional length.
        }
        # Send the command using the base class helper. Raises on connection error.
        self._send_update(set_payload)
        logger.debug(f"Viz '{self.target_id}': Sent 'set' update command for variable '{name}'.")

    def remove_variable(self, name: str):
        """Removes a previously shown variable from the Viz panel display.

        Use this method when you no longer need to see a specific variable in the
        Sidekick Viz panel.

        If the variable currently displayed under this `name` was an `ObservableValue`,
        this method also automatically **unsubscribes** from its changes, preventing
        further automatic updates for this removed variable and cleaning up resources.

        Args:
            name (str): The exact name of the variable to remove. This must match the
                `name` used in the corresponding `viz.show(name, ...)` call.

        Raises:
            SidekickConnectionError (or subclass): If the connection is not ready
                or sending the removal command fails.

        Example:
            >>> viz = sidekick.Viz()
            >>> temporary_data = [1, 2, 3, 4, 5]
            >>> viz.show("Intermediate Result", temporary_data)
            >>> # ... process the data ...
            >>> # Now remove it from the display
            >>> viz.remove_variable("Intermediate Result")
        """
        # Check if the variable name exists in our tracking dictionary.
        if name in self._shown_variables:
            # Remove the entry from tracking and get its details (value, unsubscribe func).
            entry = self._shown_variables.pop(name)
            unsubscribe_func = entry.get('unsubscribe')

            # --- Unsubscribe If Necessary ---
            # If an unsubscribe function exists (meaning the removed value was observable), call it.
            if unsubscribe_func:
                 logger.info(f"Viz '{self.target_id}': Unsubscribing from observable variable '{name}' on removal.")
                 try:
                     unsubscribe_func() # Perform the cleanup callback.
                 except Exception as e_unsub:
                     # Log errors during unsubscribe but proceed with UI removal command.
                     logger.error(f"Viz '{self.target_id}': Error occurred during unsubscribe call for '{name}' on removal: {e_unsub}")

            # --- Send Remove Command to UI ---
            # Prepare the payload to remove this specific variable from the UI.
            # Keys must be camelCase.
            remove_payload = {
                # Specific action defined in protocol to remove a top-level variable by name.
                "action": "removeVariable",
                "variableName": name,
                # Protocol expects an options object, even if empty for this action.
                "options": {}
            }
            # Send the command using the base class helper. Raises on connection error.
            self._send_update(remove_payload)
            logger.info(f"Viz '{self.target_id}': Sent 'removeVariable' command for '{name}'.")
        else:
            # The variable name wasn't found in our tracking; it might have been
            # already removed or was never shown with that name. Log a warning.
            logger.warning(f"Viz '{self.target_id}': Attempted to remove variable '{name}', but it was not found in the list of shown variables.")

    def remove(self):
        """Removes the entire Viz panel instance from the Sidekick UI and cleans up resources.

        Call this method when you are completely finished with this Viz panel.
        It performs the following actions:

        1.  **Unsubscribes:** Iterates through all variables currently tracked by this
            Viz instance and, if any are `ObservableValue`s, calls their unsubscribe
            functions to stop listening for changes.
        2.  **Calls Base `remove()`:** Invokes the `BaseModule.remove()` method, which:
            a. Unregisters the internal message handler for this Viz panel.
            b. Resets registered callbacks (`on_error`) to `None`.
            c. Sends the final 'remove' command to the Sidekick UI to delete the
               entire Viz panel element itself.

        Raises:
            SidekickConnectionError (or subclass): Can occur if sending the final
                'remove' command fails. Cleanup of local Python resources (subscriptions,
                handlers) will still be attempted.
        """
        logger.info(f"Requesting removal of Viz panel '{self.target_id}' and unsubscribing from all tracked observables.")

        # --- Unsubscribe from ALL tracked observables FIRST ---
        # Iterate over a *copy* of the keys because we will be modifying the
        # _shown_variables dictionary during iteration (by popping).
        all_tracked_names = list(self._shown_variables.keys())
        for name in all_tracked_names:
            # Use pop with a default to safely handle potential concurrency issues (though unlikely).
            entry = self._shown_variables.pop(name, None)
            if entry:
                unsubscribe_func = entry.get('unsubscribe')
                if unsubscribe_func:
                     logger.debug(f"Viz '{self.target_id}': Unsubscribing from variable '{name}' during panel removal.")
                     try:
                         unsubscribe_func() # Perform cleanup callback.
                     except Exception as e:
                         # Log errors during bulk unsubscribe but continue.
                         logger.error(f"Viz '{self.target_id}': Error unsubscribing from '{name}' during panel removal: {e}")

        # Ensure the tracking dictionary is definitely clear after iteration.
        self._shown_variables.clear()

        # --- Call Base Class Removal ---
        # This handles unregistering the main message handler for the Viz panel,
        # resetting base class callbacks (`on_error`), and sending the final
        # 'remove' command for the Viz module instance itself to the UI.
        super().remove()

    def _reset_specific_callbacks(self):
        """Internal: Resets Viz-specific state when the module is removed. (Internal).

        Called automatically by the base class's `remove()` method. For Viz, the
        primary specific state to clean up is the tracking of shown variables and
        their associated unsubscribe functions.

        Note:
            The actual unsubscribing logic is currently handled directly within the
            overridden `remove()` method for Viz to ensure it happens *before* the
            base `remove()` command is sent. This method primarily serves to formally
            clear the tracking dictionary as part of the `BaseModule` removal process.
        """
        # Called by BaseModule.remove()
        # Clear the dictionary tracking shown variables and their unsubscribe functions.
        # The actual unsubscribe calls happen in the overridden Viz.remove() method.
        self._shown_variables.clear()
        logger.debug(f"Viz '{self.target_id}': Specific state (_shown_variables) cleared during removal.")

    # --- __del__ ---
    # Inherits the __del__ method from BaseModule. It provides a best-effort
    # attempt to unregister the message handler if the Viz object is garbage collected
    # without remove() being called explicitly. As noted in BaseModule, relying on
    # __del__ is discouraged; always call viz.remove() for proper cleanup.