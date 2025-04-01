# Sidekick/libs/python/src/sidekick/viz.py
import collections.abc
import time
import functools
from typing import Any, Dict, Optional, List, Union, Callable, Set, Tuple
from . import connection
from .base_module import BaseModule
from .observable_value import ObservableValue, UnsubscribeFunction, SubscriptionCallback

# --- Representation Helper (_get_representation) ---
# (Code remains the same as the previous version - it already generates camelCase keys internally)
_MAX_DEPTH = 5
_MAX_ITEMS = 50
def _get_representation(data: Any, depth: int = 0, visited_ids: Optional[Set[int]] = None) -> Dict[str, Any]:
    if visited_ids is None: visited_ids = set()
    current_id = id(data)
    if depth > _MAX_DEPTH: return {'type': 'truncated', 'value': f'<Max Depth {_MAX_DEPTH} Reached>', 'id': f'trunc_{current_id}_{depth}'}
    if current_id in visited_ids: return {'type': 'recursive_ref', 'value': f'<Recursive Reference: {type(data).__name__}>', 'id': f'rec_{current_id}_{depth}'}

    rep: Dict[str, Any] = {}
    data_type_name = type(data).__name__
    rep['id'] = f"{data_type_name}_{current_id}_{depth}"
    rep['type'] = data_type_name

    try:
        visited_ids.add(current_id)
        if isinstance(data, ObservableValue):
            internal_value = data.get()
            nested_rep = _get_representation(internal_value, depth, visited_ids)
            nested_rep['observableTracked'] = True # camelCase
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
            for k, v in data.items():
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
        else:
            rep['type'] = f"object ({data_type_name})"; rep['value'] = {}; attribute_count = 0
            try:
                attrs = {}; skipped_attrs = 0
                for attr_name in dir(data):
                     if attr_name.startswith('_'): continue
                     try:
                        attr_value = getattr(data, attr_name)
                        if callable(attr_value): continue
                        attrs[attr_name] = attr_value
                     except Exception: skipped_attrs += 1
                rep['length'] = len(attrs)
                for attr_name, attr_value in attrs.items():
                    if attribute_count >= _MAX_ITEMS: rep['value']['...'] = {'type': 'truncated', 'value': f'... (Max {_MAX_ITEMS} Attrs Reached)', 'id': f'{rep["id"]}_attrtrunc_{attribute_count}'}; break
                    rep['value'][attr_name] = _get_representation(attr_value, depth + 1, visited_ids.copy())
                    attribute_count += 1
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
        visited_ids.remove(current_id)
    return rep

# --- Viz Module Class ---

class Viz(BaseModule):
    """
    Represents the Variable Visualizer module instance in Sidekick.

    Allows showing Python variables and automatically updating the view
    when ObservableValues change, using a structured payload format.
    """
    def __init__(self, instance_id: Optional[str] = None):
        """Creates a new Viz module instance."""
        super().__init__("viz", instance_id, payload={}, on_message=None)
        self._shown_variables: Dict[str, Dict[str, Any]] = {}
        connection.logger.info(f"Viz module '{self.target_id}' created.")

    def _handle_observable_update(self, variable_name: str, change_details: Dict[str, Any]):
        """
        Internal callback triggered by ObservableValue changes.
        Formats and sends the update payload according to the revised protocol.
        """
        connection.logger.debug(f"Viz '{self.target_id}' received update for '{variable_name}': {change_details}")
        try:
            # Build the options dictionary first
            options: Dict[str, Any] = {
                "path": change_details.get("path", [])
            }
            # Add optional fields to options if they exist in change_details
            if "value" in change_details:
                options["valueRepresentation"] = _get_representation(change_details["value"])
            if "key" in change_details:
                options["keyRepresentation"] = _get_representation(change_details["key"])
            if "length" in change_details:
                options["length"] = change_details["length"]

            # For 'set' and 'clear', regenerate the full representation
            action_type = change_details.get("type", "unknown")
            if action_type in ["set", "clear"]:
                observable_instance = self._shown_variables.get(variable_name, {}).get('value_or_observable')
                # Ensure valueRepresentation exists for 'set', even if observable is None
                options["valueRepresentation"] = _get_representation(observable_instance)
                # Path should be empty for root set/clear
                options["path"] = []


            # Construct the final payload
            payload = {
                "action": action_type,
                "variableName": variable_name,
                "options": options
            }
            self._send_update(payload)

        except Exception as e:
            connection.logger.exception(f"Viz '{self.target_id}': Error processing update for observable '{variable_name}'")

    def show(self, name: str, value: Any):
        """
        Displays or updates a variable in the Viz module using the 'set' action.

        Args:
            name: The name for the variable in the Sidekick UI.
            value: The Python variable/value to display.
        """
        if not isinstance(name, str) or not name:
            connection.logger.error("Variable name for viz.show() must be a non-empty string.")
            return

        # --- Subscription Handling (same as before) ---
        if name in self._shown_variables:
            previous_entry = self._shown_variables[name]
            if previous_entry.get('unsubscribe'):
                 connection.logger.debug(f"Viz '{self.target_id}': Unsubscribing previous observable for '{name}'.")
                 try: previous_entry['unsubscribe']()
                 except Exception as e: connection.logger.error(f"Viz '{self.target_id}': Error during unsubscribe for '{name}': {e}")
        unsubscribe_func: Optional[UnsubscribeFunction] = None
        if isinstance(value, ObservableValue):
            update_callback = functools.partial(self._handle_observable_update, name)
            try:
                unsubscribe_func = value.subscribe(update_callback)
                connection.logger.info(f"Viz '{self.target_id}': Subscribed to ObservableValue for variable '{name}'.")
            except Exception as e:
                 connection.logger.error(f"Viz '{self.target_id}': Error subscribing to ObservableValue for '{name}': {e}")
                 unsubscribe_func = None
        self._shown_variables[name] = {'value_or_observable': value, 'unsubscribe': unsubscribe_func}
        # --- End Subscription Handling ---

        # --- Generate Representation and Length (same as before) ---
        try: representation = _get_representation(value)
        except Exception as e_repr:
            connection.logger.exception(f"Viz '{self.target_id}': Error generating representation for '{name}'")
            representation = {"type": "error", "value": f"<Representation Error: {e_repr}>", "id": f"error_{name}_{id(value)}"}
        actual_data = value.get() if isinstance(value, ObservableValue) else value
        data_length = None
        if hasattr(actual_data, '__len__'):
            try: data_length = len(actual_data)
            except TypeError: pass
        # --- End Representation and Length ---

        # --- Construct Payload according to the new structure ---
        options: Dict[str, Any] = {
            "path": [], # 'set' action applies to root path
            "valueRepresentation": representation
        }
        if data_length is not None:
            options["length"] = data_length

        payload = {
            "action": "set",
            "variableName": name,
            "options": options
        }
        # --- End Payload Construction ---

        self._send_update(payload)
        connection.logger.debug(f"Viz '{self.target_id}' sent 'set' update for variable '{name}'.")

    def remove_variable(self, name: str):
        """
        Removes a variable from the Viz module display using the 'removeVariable' action.

        Args:
            name: The name of the variable to remove.
        """
        if name in self._shown_variables:
            entry = self._shown_variables.pop(name)
            if entry.get('unsubscribe'):
                 connection.logger.info(f"Viz '{self.target_id}': Unsubscribing on remove_variable for '{name}'.")
                 try: entry['unsubscribe']()
                 except Exception as e: connection.logger.error(f"Viz '{self.target_id}': Error during unsubscribe for '{name}': {e}")

            # Send 'removeVariable' action. Options can be empty/omitted.
            payload = {
                "action": "removeVariable",
                "variableName": name,
                "options": {} # Send empty options object
            }
            self._send_update(payload)
            connection.logger.info(f"Viz '{self.target_id}' sent remove_variable update for '{name}'.")
        else:
            connection.logger.warning(f"Viz '{self.target_id}': Variable '{name}' not found for removal.")

    # remove() method inherited from BaseModule remains the same functionally
    # but its internal call to remove_variable() now sends the correct payload.