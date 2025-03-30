# Sidekick/libs/python/src/sidekick/viz.py
import collections.abc
import time
import functools
from typing import Any, Dict, Optional, List, Union, Callable, Set, Tuple
from . import connection
from .base_module import BaseModule
from .observable_value import ObservableValue, UnsubscribeFunction, SubscriptionCallback

# --- Helper Function _get_representation (No changes needed here) ---
_MAX_DEPTH = 5
_MAX_ITEMS = 50
def _get_representation(data: Any, depth: int = 0) -> Dict[str, Any]:
    rep: Dict[str, Any] = {}
    if isinstance(data, ObservableValue):
        internal_value = data.get()
        if internal_value is data:
             obs_id = data._obs_value_id if hasattr(data, '_obs_value_id') else f"obs_{id(data)}_{depth}"
             return {'type': 'error', 'value': '<ObservableValue cannot wrap itself>', 'id': obs_id, 'observable_tracked': True}
        nested_rep = _get_representation(internal_value, depth)
        nested_rep['observable_tracked'] = True
        nested_rep['id'] = data._obs_value_id if hasattr(data, '_obs_value_id') else nested_rep.get('id', f"obs_{id(data)}_{depth}")
        return nested_rep

    base_id = f"{type(data).__name__}_{id(data)}_{depth}"
    rep['id'] = base_id; data_type = type(data).__name__; rep['type'] = data_type
    try:
        if data is None: rep['value'] = 'None'; rep['type'] = 'NoneType'
        elif isinstance(data, (str, int, float, bool)): rep['value'] = data
        elif isinstance(data, (list, tuple)):
            rep['type'] = 'list'; rep['value'] = []; rep['length'] = len(data); count = 0
            for i, item in enumerate(data):
                if count >= _MAX_ITEMS: trunc_id = f'{base_id}_trunc_{count}'; rep['value'].append({'type': 'truncated', 'value': f'... ({len(data)} items, Max {_MAX_ITEMS} Reached)', 'id': trunc_id}); break
                rep['value'].append(_get_representation(item, depth + 1)); count += 1
        elif isinstance(data, dict):
            rep['type'] = 'dict'; rep['value'] = []; rep['length'] = len(data); count = 0
            for k, v in data.items():
                if count >= _MAX_ITEMS: trunc_key_id = f'{base_id}_keytrunc_{count}'; trunc_val_id = f'{base_id}_valtrunc_{count}'; rep['value'].append({'key': {'type': 'truncated', 'value': '...', 'id': trunc_key_id}, 'value': {'type': 'truncated', 'value': f'... ({len(data)} items, Max {_MAX_ITEMS} Reached)', 'id': trunc_val_id}}); break
                key_rep = _get_representation(k, depth + 1); value_rep = _get_representation(v, depth + 1)
                rep['value'].append({'key': key_rep, 'value': value_rep}); count += 1
        elif isinstance(data, set):
            rep['type'] = 'set'; rep['value'] = []; rep['length'] = len(data); count = 0
            try: sorted_items = sorted(list(data), key=repr)
            except TypeError: sorted_items = list(data)
            for i, item in enumerate(sorted_items):
                if count >= _MAX_ITEMS: trunc_id = f'{base_id}_trunc_{count}'; rep['value'].append({'type': 'truncated', 'value': f'... ({len(data)} items, Max {_MAX_ITEMS} Reached)', 'id': trunc_id}); break
                rep['value'].append(_get_representation(item, depth + 1)); count += 1
        else:
            rep['type'] = f"object ({data_type})"; rep['value'] = {}; attribute_count = 0
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
                    if attribute_count >= _MAX_ITEMS: trunc_id = f'{base_id}_attrtrunc_{attribute_count}'; rep['value']['...'] = {'type': 'truncated', 'value': f'... (Max {_MAX_ITEMS} Attrs Reached)', 'id': trunc_id}; break
                    if attr_value is data: rec_id = f'{base_id}_rec_{attr_name}'; rep['value'][attr_name] = {'type': 'recursive_ref', 'value': f'<Recursive self reference>', 'id': rec_id}
                    else: rep['value'][attr_name] = _get_representation(attr_value, depth + 1)
                    attribute_count += 1
                if not rep['value'] and attribute_count == 0: rep['value'] = repr(data); rep['type'] = f"repr ({data_type})"
            except Exception as e_obj:
                connection.logger.warning(f"Could not fully represent object attributes for {data_type}: {e_obj}")
                try: rep['value'] = repr(data); rep['type'] = f"repr ({data_type})"
                except Exception as e_repr_final: rep['value'] = f"<Object of type {data_type}, repr failed: {e_repr_final}>"; rep['type'] = 'error'
    except Exception as e:
        connection.logger.exception(f"Error generating representation for type {data_type}")
        rep['type'] = 'error'; rep['value'] = f"<Error representing object: {e}>"
        if 'id' not in rep: rep['id'] = f"error_{id(data)}_{depth}"
    return rep


# --- Viz Module Class ---

class Viz(BaseModule):
    """ Sends detailed updates about variable changes to Sidekick. """
    def __init__(self, instance_id: Optional[str] = None):
        super().__init__("viz", instance_id, payload={}, on_message=None)
        self._shown_variables: Dict[str, Dict[str, Any]] = {}
        connection.logger.info(f"Viz module '{self.target_id}' created.")

    def _handle_observable_update(self, variable_name: str, change_details: Dict[str, Any]):
        """Callback triggered when a subscribed ObservableValue changes."""
        connection.logger.debug(f"Viz received update for '{variable_name}': {change_details}")
        try:
            payload = {
                "variable_name": variable_name,
                "change_type": change_details.get("type", "unknown"),
                "path": change_details.get("path", []),
                "value_representation": None,
                "key_representation": None,
                "length": change_details.get("length")
            }
            new_value = change_details.get("value")
            if new_value is not None or payload["change_type"] in ["set", "clear"]:
                if payload["change_type"] in ["set", "clear"]:
                    observable_instance = self._shown_variables.get(variable_name, {}).get('value_or_observable')
                    if isinstance(observable_instance, ObservableValue): payload["value_representation"] = _get_representation(observable_instance)
                    else: payload["value_representation"] = _get_representation(new_value)
                else: payload["value_representation"] = _get_representation(new_value)
            key_value = change_details.get("key")
            if key_value is not None: payload["key_representation"] = _get_representation(key_value)
            self._send_command("update", payload)
        except Exception as e:
            connection.logger.exception(f"Error processing update for observable '{variable_name}'")

    def show(self, name: str, value: Any):
        """ Displays or updates a variable, sending a full 'set' update. """
        if not isinstance(name, str) or not name:
            connection.logger.error("Variable name must be non-empty string."); return

        if name in self._shown_variables:
            previous_entry = self._shown_variables[name]
            if previous_entry.get('unsubscribe'):
                 try: previous_entry['unsubscribe']()
                 except Exception as e: connection.logger.error(f"Unsubscribe error: {e}")

        unsubscribe_func: Optional[UnsubscribeFunction] = None
        if isinstance(value, ObservableValue):
            update_callback = functools.partial(self._handle_observable_update, name)
            try:
                unsubscribe_func = value.subscribe(update_callback)
                connection.logger.info(f"Subscribed to ObservableValue for '{name}'.")
            except Exception as e:
                 connection.logger.error(f"Error subscribing: {e}"); unsubscribe_func = None

        try: representation = _get_representation(value)
        except Exception as e_repr:
            connection.logger.exception(f"Rep generation error for '{name}'")
            representation = {"type": "error", "value": f"<Rep Error: {e_repr}>", "id": f"error_{name}_{id(value)}"}

        self._shown_variables[name] = {'value_or_observable': value, 'unsubscribe': unsubscribe_func}

        # --- FIX IS HERE ---
        # Determine the actual data and its length correctly
        actual_data = value.get() if isinstance(value, ObservableValue) else value
        data_length = None
        # Check if the *actual data* (not the wrapper) supports len()
        if hasattr(actual_data, '__len__'):
            try:
                data_length = len(actual_data)
            except TypeError: # Should not happen if hasattr is true, but safeguard
                 connection.logger.warning(f"Value of type {type(actual_data)} reported __len__ but raised TypeError.")
                 pass # Keep data_length as None

        # --- END FIX ---

        payload = {
            "variable_name": name,
            "change_type": "set",
            "path": [],
            "value_representation": representation,
            "key_representation": None,
            "length": data_length # Use the correctly determined length
        }
        self._send_command("update", payload)
        connection.logger.debug(f"Viz '{self.target_id}' showing variable '{name}'.")

    def remove_variable(self, name: str):
        """ Removes a variable display using an 'update' message. """
        if name in self._shown_variables:
            entry = self._shown_variables.pop(name)
            if entry.get('unsubscribe'):
                 connection.logger.info(f"Unsubscribing on remove '{name}'.")
                 try: entry['unsubscribe']()
                 except Exception as e: connection.logger.error(f"Unsubscribe error: {e}")
            payload = {
                "variable_name": name, "change_type": "remove_variable", "path": [],
                "value_representation": None, "key_representation": None, "length": None
            }
            self._send_command("update", payload)
            connection.logger.info(f"Viz sent remove_variable update for '{name}'.")
        else:
            connection.logger.warning(f"Variable '{name}' not found for removal.")

    def remove(self):
        """ Removes the Viz module, unsubscribing and clearing variables. """
        connection.logger.info(f"Removing Viz module '{self.target_id}'...")
        variable_names = list(self._shown_variables.keys())
        for name in variable_names: self.remove_variable(name)
        self._shown_variables.clear()
        super().remove()