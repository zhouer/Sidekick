# Sidekick/libs/python/src/sidekick/viz.py
import collections.abc
import time
import functools
from typing import Any, Dict, Optional, List, Union, Callable, Set, Tuple
from . import connection
from .base_module import BaseModule
from .observable_value import ObservableValue, UnsubscribeFunction, SubscriptionCallback

# --- Representation Helper (_get_representation) ---
# (Keep the existing _get_representation function here - it's complex and correct)
# (Ensure it uses camelCase keys like 'observableTracked')
_MAX_DEPTH = 5
_MAX_ITEMS = 50
def _get_representation(data: Any, depth: int = 0, visited_ids: Optional[Set[int]] = None) -> Dict[str, Any]:
    # --- Ensure keys like 'observableTracked' are camelCase ---
    if visited_ids is None: visited_ids = set()
    current_id = id(data)
    if depth > _MAX_DEPTH: return {'type': 'truncated', 'value': f'<Max Depth {_MAX_DEPTH} Reached>', 'id': f'trunc_{current_id}_{depth}'}
    if current_id in visited_ids: return {'type': 'recursive_ref', 'value': f'<Recursive Reference: {type(data).__name__}>', 'id': f'rec_{current_id}_{depth}'}

    rep: Dict[str, Any] = {}
    data_type_name = type(data).__name__
    rep['id'] = f"{data_type_name}_{current_id}_{depth}" # Default ID
    rep['type'] = data_type_name

    try:
        visited_ids.add(current_id)
        if isinstance(data, ObservableValue):
            internal_value = data.get()
            # Generate representation for the internal value
            nested_rep = _get_representation(internal_value, depth, visited_ids) # Pass same depth
            # Mark this node as originating from an ObservableValue
            nested_rep['observableTracked'] = True # camelCase key
            # Use the observable's own ID if available for stability
            nested_rep['id'] = getattr(data, '_obs_value_id', nested_rep.get('id', f"obs_{current_id}_{depth}"))
            return nested_rep
        elif data is None: rep['value'] = 'None'; rep['type'] = 'NoneType'
        elif isinstance(data, (str, int, float, bool)): rep['value'] = data
        elif isinstance(data, (list, tuple)):
            rep['type'] = 'list'; rep['value'] = []; rep['length'] = len(data); count = 0
            for item in data:
                if count >= _MAX_ITEMS: rep['value'].append({'type': 'truncated', 'value': f'... ({len(data)} items, Max {_MAX_ITEMS} Reached)', 'id': f'{rep["id"]}_trunc_{count}'}); break
                rep['value'].append(_get_representation(item, depth + 1, visited_ids.copy())); count += 1
        elif isinstance(data, dict):
            rep['type'] = 'dict'; rep['value'] = []; rep['length'] = len(data); count = 0
            # Attempt to sort keys for consistent display, fallback if keys are unorderable
            try: sorted_items = sorted(data.items(), key=lambda item: repr(item[0]))
            except TypeError: sorted_items = list(data.items())
            for k, v in sorted_items:
                if count >= _MAX_ITEMS: rep['value'].append({'key': {'type': 'truncated', 'value': '...', 'id': f'{rep["id"]}_keytrunc_{count}'}, 'value': {'type': 'truncated', 'value': f'... ({len(data)} items, Max {_MAX_ITEMS} Reached)', 'id': f'{rep["id"]}_valtrunc_{count}'}}); break
                key_rep = _get_representation(k, depth + 1, visited_ids.copy())
                value_rep = _get_representation(v, depth + 1, visited_ids.copy())
                rep['value'].append({'key': key_rep, 'value': value_rep}); count += 1
        elif isinstance(data, set):
            rep['type'] = 'set'; rep['value'] = []; rep['length'] = len(data); count = 0
            try: sorted_items = sorted(list(data), key=repr)
            except TypeError: sorted_items = list(data)
            for item in sorted_items:
                if count >= _MAX_ITEMS: rep['value'].append({'type': 'truncated', 'value': f'... ({len(data)} items, Max {_MAX_ITEMS} Reached)', 'id': f'{rep["id"]}_trunc_{count}'}); break
                rep['value'].append(_get_representation(item, depth + 1, visited_ids.copy())); count += 1
        else: # Generic object inspection
            rep['type'] = f"object ({data_type_name})"; rep['value'] = {}; attribute_count = 0
            try:
                attrs = {}; skipped_attrs = 0
                # Iterate through attributes, skipping private/magic/callables
                for attr_name in dir(data):
                     if attr_name.startswith('_'): continue
                     try:
                        attr_value = getattr(data, attr_name)
                        if callable(attr_value): continue # Skip methods
                        attrs[attr_name] = attr_value
                     except Exception: skipped_attrs += 1
                rep['length'] = len(attrs) # Length represents number of displayed attributes
                # Attempt to sort attributes for consistency
                try: sorted_attr_items = sorted(attrs.items())
                except TypeError: sorted_attr_items = list(attrs.items())

                for attr_name, attr_value in sorted_attr_items:
                    if attribute_count >= _MAX_ITEMS: rep['value']['...'] = {'type': 'truncated', 'value': f'... (Max {_MAX_ITEMS} Attrs Reached)', 'id': f'{rep["id"]}_attrtrunc_{attribute_count}'}; break
                    rep['value'][attr_name] = _get_representation(attr_value, depth + 1, visited_ids.copy())
                    attribute_count += 1
                # If no attributes were representable, fall back to repr()
                if not rep['value'] and attribute_count == 0 and skipped_attrs == 0 :
                     rep['value'] = repr(data); rep['type'] = f"repr ({data_type_name})"
            except Exception as e_obj:
                connection.logger.warning(f"Could not fully represent object attributes for {data_type_name}: {e_obj}")
                try: rep['value'] = repr(data); rep['type'] = f"repr ({data_type_name})"
                except Exception as e_repr_final: rep['value'] = f"<Object of type {data_type_name}, repr failed: {e_repr_final}>"; rep['type'] = 'error'
    except Exception as e:
        connection.logger.exception(f"Error generating representation for type {data_type_name}")
        rep['type'] = 'error'; rep['value'] = f"<Error representing object: {e}>"
        rep['id'] = rep.get('id', f"error_{current_id}_{depth}")
    finally:
        # Ensure the current ID is removed from visited set for this path
        if current_id in visited_ids:
            visited_ids.remove(current_id)
    return rep


# --- Viz Module Class ---

class Viz(BaseModule):
    """
    Represents the Variable Visualizer module instance in the Sidekick UI.

    This module allows you to display Python variables and data structures in
    an interactive, expandable view within Sidekick. It integrates with the
    `ObservableValue` class to automatically reflect changes made to wrapped
    mutable objects (lists, dicts, sets) in the UI.

    It supports two modes of initialization:
    1. Creating a new variable visualizer panel instance in Sidekick (`spawn=True`).
    2. Attaching to a pre-existing panel instance in Sidekick (`spawn=False`).
    """
    def __init__(
        self,
        instance_id: Optional[str] = None,
        spawn: bool = True
    ):
        """
        Initializes the Viz object, optionally creating a new viz panel in Sidekick.

        Args:
            instance_id: A unique identifier for this viz panel instance.
                         - If `spawn=True`: Optional. If None, an ID will be generated.
                         - If `spawn=False`: **Required**. Specifies the ID of the existing
                           viz panel instance in Sidekick to attach to.
            spawn: If True (default), sends a command to Sidekick to create a new
                   viz module instance.
                   If False, assumes a viz panel with `instance_id` already exists.
        """
        # Viz spawn payload is currently empty.
        spawn_payload = {} if spawn else None

        super().__init__(
            module_type="viz",
            instance_id=instance_id,
            spawn=spawn,
            payload=spawn_payload,
        )
        # Stores information about shown variables and their potential unsubscribe functions.
        self._shown_variables: Dict[str, Dict[str, Any]] = {}
        connection.logger.info(f"Viz panel '{self.target_id}' initialized (spawn={spawn}).")

    # _internal_message_handler is inherited from BaseModule and handles 'error'
    # Viz currently doesn't have specific 'event' types to handle.

    # on_error is inherited from BaseModule
    # def on_error(self, callback: Optional[Callable[[str], None]]): inherited


    def _handle_observable_update(self, variable_name: str, change_details: Dict[str, Any]):
        """
        Internal callback triggered by changes in an observed ObservableValue.

        Formats the change details into an 'update' command payload according
        to the Sidekick protocol and sends it to the frontend for granular UI updates.

        Args:
            variable_name: The name of the variable associated with the ObservableValue.
            change_details: The dictionary provided by ObservableValue describing the change.
        """
        connection.logger.debug(f"Viz '{self.target_id}': Received update for '{variable_name}': {change_details}")
        try:
            action_type = change_details.get("type", "unknown") # e.g., "setitem", "append"
            path = change_details.get("path", [])

            # Construct the 'options' part of the payload, generating representations
            # for values and keys involved in the change, ensuring camelCase.
            options: Dict[str, Any] = { "path": path }
            if "value" in change_details:
                options["valueRepresentation"] = _get_representation(change_details["value"])
            if "key" in change_details: # Relevant for dict operations
                options["keyRepresentation"] = _get_representation(change_details["key"])
            if "length" in change_details: # Relevant for container size changes
                options["length"] = change_details["length"]

            # Special handling for root 'set' or 'clear' on an ObservableValue:
            # Resend the full representation of the observable's *current* value.
            if action_type in ["set", "clear"] and not path: # Only if path is empty (root change)
                observable_instance = self._shown_variables.get(variable_name, {}).get('value_or_observable')
                # Ensure observable_instance is not None before getting representation
                if observable_instance is not None:
                    options["valueRepresentation"] = _get_representation(observable_instance)
                    # Ensure length is also updated for root set/clear
                    actual_data = observable_instance.get() if isinstance(observable_instance, ObservableValue) else observable_instance
                    try: options["length"] = len(actual_data) if hasattr(actual_data, '__len__') else None
                    except TypeError: options["length"] = None
                else:
                     # If the observable was removed concurrently, we might not have it. Log and skip.
                     connection.logger.warning(f"Viz '{self.target_id}': Observable instance for '{variable_name}' not found during root update. Skipping.")
                     return


            # Construct the full update payload.
            update_payload = {
                "action": action_type,
                "variableName": variable_name,
                "options": options
            }
            self._send_update(update_payload)

        except Exception as e:
            # Log errors during the update processing but don't crash.
            connection.logger.exception(
                f"Viz '{self.target_id}': Error processing update "
                f"for observable '{variable_name}'. Change: {change_details}"
            )

    def show(self, name: str, value: Any):
        """
        Displays or updates a variable in the Viz panel in Sidekick.

        If the `value` is an `ObservableValue`, the Viz module will subscribe to its
        changes and automatically send granular updates to Sidekick, allowing for
        efficient and highlighted UI updates.

        If the variable `name` already exists, this call will update its value and
        re-subscribe if necessary (unsubscribing from the previous value if it was
        an ObservableValue).

        Args:
            name: The name to display for the variable in the Sidekick UI. Must be a non-empty string.
            value: The Python variable or value to display. Can be any type, including
                   an `ObservableValue`.
        """
        if not isinstance(name, str) or not name:
            connection.logger.error("Variable name for viz.show() must be a non-empty string.")
            return

        # --- Subscription Handling ---
        # Unsubscribe from the previous ObservableValue if this variable name is being reused.
        if name in self._shown_variables:
            previous_entry = self._shown_variables[name]
            if previous_entry.get('unsubscribe'):
                 connection.logger.debug(f"Viz '{self.target_id}': Unsubscribing previous observable for '{name}'.")
                 try:
                     previous_entry['unsubscribe']()
                 except Exception as e:
                     # Log error during unsubscribe but continue.
                     connection.logger.error(f"Viz '{self.target_id}': Error during unsubscribe for '{name}': {e}")

        unsubscribe_func: Optional[UnsubscribeFunction] = None
        # If the new value is an ObservableValue, subscribe to it.
        if isinstance(value, ObservableValue):
            # Create a partial function for the callback to include the variable name.
            update_callback = functools.partial(self._handle_observable_update, name)
            try:
                unsubscribe_func = value.subscribe(update_callback)
                connection.logger.info(f"Viz '{self.target_id}': Subscribed to ObservableValue for variable '{name}'.")
            except Exception as e:
                 connection.logger.error(f"Viz '{self.target_id}': Error subscribing to ObservableValue for '{name}': {e}")
                 unsubscribe_func = None # Ensure it's None if subscription failed

        # Store the value/observable and its unsubscribe function (if any).
        self._shown_variables[name] = {'value_or_observable': value, 'unsubscribe': unsubscribe_func}
        # --- End Subscription Handling ---

        # --- Generate Representation and Initial Payload ---
        try:
            # Generate the visual representation of the value.
            representation = _get_representation(value)
        except Exception as e_repr:
            connection.logger.exception(f"Viz '{self.target_id}': Error generating representation for '{name}'")
            # Create an error representation to display in Sidekick.
            representation = {"type": "error", "value": f"<Representation Error: {e_repr}>", "id": f"error_{name}_{id(value)}"}

        # Determine the length of the underlying data if possible.
        actual_data = value.get() if isinstance(value, ObservableValue) else value
        data_length = None
        if hasattr(actual_data, '__len__'):
            try: data_length = len(actual_data)
            except TypeError: pass # len() might not be supported (e.g., for some custom objects)

        # Construct the 'set' payload to send the initial/updated full representation.
        options: Dict[str, Any] = {
            "path": [], # 'set' applies to the root path.
            "valueRepresentation": representation
        }
        if data_length is not None:
            options["length"] = data_length

        initial_payload = {
            "action": "set",
            "variableName": name,
            "options": options
        }
        # --- End Payload Construction ---

        # Send the initial 'set' update command.
        self._send_update(initial_payload)
        connection.logger.debug(f"Viz '{self.target_id}': Sent 'set' update for variable '{name}'.")

    def remove_variable(self, name: str):
        """
        Removes a variable from the Viz panel display in Sidekick.

        If the removed variable was associated with an `ObservableValue`, its
        subscription will be automatically cancelled.

        Args:
            name: The name of the variable to remove.
        """
        if name in self._shown_variables:
            entry = self._shown_variables.pop(name) # Remove from local tracking
            # Unsubscribe if an unsubscribe function exists for this variable.
            if entry.get('unsubscribe'):
                 connection.logger.info(f"Viz '{self.target_id}': Unsubscribing on remove_variable for '{name}'.")
                 try:
                     entry['unsubscribe']()
                 except Exception as e:
                     connection.logger.error(f"Viz '{self.target_id}': Error during unsubscribe for '{name}': {e}")

            # Send the 'removeVariable' command to Sidekick.
            remove_payload = {
                "action": "removeVariable",
                "variableName": name,
                "options": {} # No specific options needed for removal.
            }
            self._send_update(remove_payload)
            connection.logger.info(f"Viz '{self.target_id}': Sent remove_variable update for '{name}'.")
        else:
            connection.logger.warning(f"Viz '{self.target_id}': Variable '{name}' not found for removal.")

    def remove(self):
        """
        Removes the entire Viz panel instance from Sidekick.

        This also automatically unsubscribes from any tracked ObservableValues
        associated with variables previously shown in this panel.
        """
        connection.logger.info(f"Requesting removal of Viz panel '{self.target_id}'.")
        # Unsubscribe from all tracked observables before sending the remove command.
        for name, entry in list(self._shown_variables.items()): # Iterate over a copy
            if entry.get('unsubscribe'):
                 connection.logger.debug(f"Viz '{self.target_id}': Unsubscribing from '{name}' during panel removal.")
                 try:
                     entry['unsubscribe']()
                 except Exception as e:
                     connection.logger.error(f"Viz '{self.target_id}': Error unsubscribing from '{name}' during remove: {e}")
            # Remove from local tracking as we go.
            del self._shown_variables[name]

        # Call the base class remove method, which sends the 'remove' command for the panel itself.
        super().remove()

    def _reset_specific_callbacks(self):
        """Resets Viz-specific state (subscriptions) on removal."""
        # The main remove() method already handles unsubscribing.
        self._shown_variables.clear()