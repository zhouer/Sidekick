# Sidekick/libs/python/src/sidekick/viz.py
import collections.abc
import time
import functools # For creating partial functions for callbacks
from typing import Any, Dict, Optional, List, Union, Callable, Set
from . import connection
from .base_module import BaseModule
from .observable_value import ObservableValue, UnsubscribeFunction # Import ObservableValue

# --- Helper Function for Data Representation (Updated) ---

_MAX_DEPTH = 5
_MAX_ITEMS = 50

def _get_representation(data: Any, depth: int = 0) -> Dict[str, Any]:
    """
    Recursively converts Python data to a JSON-serializable representation for Viz.
    Now checks for ObservableValue and adds 'observable_tracked' flag.
    """
    rep: Dict[str, Any] = {}

    if depth > _MAX_DEPTH:
        rep['type'] = 'truncated'
        rep['value'] = f'... (Max Depth {depth} Reached)'
        rep['id'] = f"truncated_{id(data)}_{depth}"
        return rep

    # --- Check for ObservableValue FIRST ---
    if isinstance(data, ObservableValue):
        # Represent the *internal* value and mark as tracked
        internal_value = data.get()
        nested_rep = _get_representation(internal_value, depth) # Represent internal value
        nested_rep['observable_tracked'] = True # Mark as observable
        # Use the observable's ID for the top-level node
        nested_rep['id'] = data._obs_value_id if hasattr(data, '_obs_value_id') else nested_rep.get('id', f"obs_{id(data)}_{depth}")
        # Special case: prevent infinite recursion if observable wraps itself
        if internal_value is data:
             return {'type': 'error', 'value': '<ObservableValue cannot wrap itself>', 'id': nested_rep['id']}
        else:
             return nested_rep # Return the representation of the internal value, marked

    # --- If not ObservableValue, proceed with type checking ---
    data_type = type(data).__name__
    rep['type'] = data_type
    rep['id'] = f"{data_type}_{id(data)}_{depth}" # Default ID

    try:
        if data is None:
            rep['value'] = 'None'
        elif isinstance(data, (str, int, float, bool)):
            rep['value'] = data
        elif isinstance(data, (list, tuple)):
            rep['type'] = 'list'
            rep['value'] = []
            rep['length'] = len(data)
            count = 0
            for item in data:
                if count >= _MAX_ITEMS:
                    rep['value'].append({'type': 'truncated', 'value': f'... ({len(data)} items, Max {_MAX_ITEMS} Reached)', 'id': f'list_trunc_{rep["id"]}'})
                    break
                rep['value'].append(_get_representation(item, depth + 1))
                count += 1
        elif isinstance(data, dict):
            rep['type'] = 'dict'
            rep['value'] = []
            rep['length'] = len(data)
            count = 0
            for key, value in data.items():
                if count >= _MAX_ITEMS:
                     rep['value'].append({'key': {'type': 'truncated', 'value': '...', 'id': f'dict_key_trunc_{rep["id"]}'}, 'value': {'type': 'truncated', 'value': f'... ({len(data)} items, Max {_MAX_ITEMS} Reached)', 'id': f'dict_val_trunc_{rep["id"]}'}})
                     break
                key_rep = _get_representation(key, depth + 1)
                value_rep = _get_representation(value, depth + 1)
                rep['value'].append({'key': key_rep, 'value': value_rep})
                count += 1
        elif isinstance(data, set):
            rep['type'] = 'set'
            rep['value'] = []
            rep['length'] = len(data)
            count = 0
            try:
                 sorted_items = sorted(list(data), key=repr)
            except TypeError:
                 sorted_items = list(data)
            for item in sorted_items:
                if count >= _MAX_ITEMS:
                    rep['value'].append({'type': 'truncated', 'value': f'... ({len(data)} items, Max {_MAX_ITEMS} Reached)', 'id': f'set_trunc_{rep["id"]}'})
                    break
                rep['value'].append(_get_representation(item, depth + 1))
                count += 1
        else: # Other objects
            rep['type'] = f"object ({data_type})"
            rep['value'] = {}
            attribute_count = 0
            try:
                attrs = {k: getattr(data, k) for k in dir(data) if not k.startswith('_') and not callable(getattr(data, k))}
                rep['length'] = len(attrs)
                for attr_name, attr_value in attrs.items():
                    if attribute_count >= _MAX_ITEMS:
                         rep['value']['...'] = {'type': 'truncated', 'value': f'... (Max {_MAX_ITEMS} Attrs Reached)', 'id': f'obj_attr_trunc_{rep["id"]}'}
                         break
                    if attr_value is data:
                        rep['value'][attr_name] = {'type': 'recursive_ref', 'value': f'<Recursive self reference>', 'id': f'obj_rec_{attr_name}_{rep["id"]}'}
                    else:
                        rep['value'][attr_name] = _get_representation(attr_value, depth + 1)
                    attribute_count += 1
                if not rep['value']:
                     rep['value'] = repr(data)
            except Exception:
                try: rep['value'] = repr(data)
                except Exception as e_repr_final:
                    rep['value'] = f"<Object of type {data_type}, repr failed: {e_repr_final}>"; rep['type'] = 'error'
    except Exception as e:
        connection.logger.exception(f"Error generating representation for type {data_type}")
        rep['type'] = 'error'; rep['value'] = f"<Error representing object: {e}>"
        if 'id' not in rep: rep['id'] = f"error_{id(data)}_{depth}"

    return rep


# --- Viz Module Class (Updated) ---

class Viz(BaseModule):
    """
    Represents a Variable Visualizer module instance in Sidekick.
    Displays Python variables and automatically updates when showing
    an ObservableValue whose internal value changes.
    """
    def __init__(self, instance_id: Optional[str] = None):
        """ Creates a new Variable Visualizer (Viz) module. """
        super().__init__("viz", instance_id, payload={}, on_message=None)
        # Store variable name -> { 'value_or_observable': Any, 'unsubscribe': Optional[UnsubscribeFunction] }
        self._shown_variables: Dict[str, Dict[str, Any]] = {}
        connection.logger.info(f"Viz module '{self.target_id}' created.")

    def _handle_observable_update(self, variable_name: str, new_value: Any):
        """Callback triggered when a subscribed ObservableValue changes."""
        connection.logger.info(f"ObservableValue '{variable_name}' updated. Sending to Sidekick.")
        try:
            # Re-generate representation for the *new* internal value
            representation = _get_representation(new_value) # Pass the raw new value
            representation['observable_tracked'] = True # Ensure flag is set

            payload = {
                "variable_name": variable_name,
                "representation": representation,
                "change_type": "observable_update", # Specific change type for frontend
                "change_details": {} # Can add more details if needed later
            }
            self._send_command("update", payload)
        except Exception as e:
            connection.logger.exception(f"Error processing update for observable '{variable_name}'")


    def show(self, name: str, value: Any):
        """
        Displays or updates a variable in the Viz module.
        If the value is an ObservableValue, Viz subscribes to its changes
        for automatic updates.

        Args:
            name: The name to display for the variable.
            value: The Python value or ObservableValue instance to display.
        """
        if not isinstance(name, str) or not name:
            connection.logger.error("Variable name for viz.show() must be a non-empty string.")
            return

        # --- Unsubscribe from previous observable if we're replacing it ---
        if name in self._shown_variables:
            previous_entry = self._shown_variables[name]
            if previous_entry.get('unsubscribe'):
                 connection.logger.debug(f"Unsubscribing from previous ObservableValue for '{name}'.")
                 try:
                     previous_entry['unsubscribe']()
                 except Exception as e_unsub:
                      connection.logger.error(f"Error during unsubscribe for '{name}': {e_unsub}")


        # --- Handle ObservableValue subscription ---
        unsubscribe_func: Optional[UnsubscribeFunction] = None
        value_to_represent = value

        if isinstance(value, ObservableValue):
            value_to_represent = value.get() # Get current internal value for initial display
            # Create the specific callback for this variable name using partial
            update_callback = functools.partial(self._handle_observable_update, name)
            try:
                unsubscribe_func = value.subscribe(update_callback)
                connection.logger.info(f"Subscribed to ObservableValue for '{name}'.")
            except Exception as e_sub:
                 connection.logger.error(f"Error subscribing to ObservableValue for '{name}': {e_sub}")
                 unsubscribe_func = None # Ensure we don't store a failed subscription

        # --- Generate representation and store info ---
        try:
             representation = _get_representation(value) # Pass original value (handles observable inside)
        except Exception as e_repr:
            connection.logger.exception(f"Error generating representation for variable '{name}'")
            representation = {"type": "error", "value": f"<Error generating representation: {e_repr}>", "id": f"error_{name}"}

        # Store the value/observable and the unsubscribe function
        self._shown_variables[name] = {
            'value_or_observable': value,
            'unsubscribe': unsubscribe_func
        }

        # --- Send update to frontend ---
        payload = {
            "variable_name": name,
            "representation": representation,
            "change_type": "replace", # viz.show always signals a 'replace'
            "change_details": {} # Details handled by specific observable updates
        }
        self._send_command("update", payload)
        connection.logger.debug(f"Viz '{self.target_id}' showing variable '{name}'.")


    def remove_variable(self, name: str):
        """Removes a variable display from the Viz module and unsubscribes if needed."""
        if name in self._shown_variables:
            entry = self._shown_variables.pop(name) # Remove from dict
            if entry.get('unsubscribe'):
                 connection.logger.info(f"Unsubscribing from ObservableValue for removed variable '{name}'.")
                 try:
                    entry['unsubscribe']()
                 except Exception as e_unsub:
                      connection.logger.error(f"Error during unsubscribe for removed variable '{name}': {e_unsub}")

            # Send command to frontend to remove the visual element
            payload = {"variable_name": name}
            self._send_command("remove_var", payload)
            connection.logger.info(f"Viz '{self.target_id}' removed variable '{name}'.")
        else:
            connection.logger.warning(f"Variable '{name}' not found in Viz '{self.target_id}' for removal.")


    def remove(self):
        """Removes the Viz module instance, unsubscribing from all observables."""
        connection.logger.info(f"Removing Viz module '{self.target_id}' and unsubscribing...")
        # Create a list of names to iterate over, as we modify the dict
        variable_names = list(self._shown_variables.keys())
        for name in variable_names:
             # Use remove_variable logic to handle unsubscribe and dict cleanup
             self.remove_variable(name)
        # Ensure dict is empty after loop
        self._shown_variables.clear()
        # Call base class remove to send remove command etc.
        super().remove()