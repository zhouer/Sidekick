"""Provides the Viz class for visualizing Python variables in Sidekick.

Use the `sidekick.Viz` class to create an interactive, tree-like display of your
Python variables within the Sidekick panel in VS Code. This is incredibly helpful
for understanding the state and structure of your data, especially complex objects,
lists, dictionaries, and sets, as your script executes.

The Viz panel can be placed inside layout containers like `Row` or `Column` by
specifying the `parent` during initialization.

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
    >>> viz = sidekick.Viz() # Created in the root container
    >>> my_config = {"user": "Alice", "settings": {"theme": "dark", "level": 5}}
    >>> viz.show("App Config", my_config)

Reactive Usage with a Parent Container:
    >>> import sidekick
    >>> my_column = sidekick.Column()
    >>> viz_in_col = sidekick.Viz(parent=my_column)
    >>> reactive_list = sidekick.ObservableValue([10, 20])
    >>> viz_in_col.show("Reactive List", reactive_list)
    >>> reactive_list.append(30) # Viz updates automatically
"""

import functools
from typing import Any, Dict, Optional, List, Union, Callable, Set, Tuple # Added Union
from . import logger
from .base_component import BaseComponent
from .observable_value import ObservableValue, UnsubscribeFunction, SubscriptionCallback

_MAX_DEPTH = 5
_MAX_ITEMS = 50


def _get_representation(
    data: Any,
    depth: int = 0,
    visited_ids: Optional[Set[int]] = None
) -> Dict[str, Any]:
    """Converts Python data into a structured dictionary for the Viz UI. (Internal).

    Transforms arbitrary Python data into a nested dictionary structure conforming
    to the format expected by the Sidekick Viz frontend component.

    Args:
        data (Any): The Python data to represent.
        depth (int): Current recursion depth.
        visited_ids (Optional[Set[int]]): Set of `id()`s of objects already visited
            in the current traversal path to detect circular references.

    Returns:
        Dict[str, Any]: A dictionary representing the data structure, suitable for
            serialization and interpretation by the Viz frontend.
    """
    if visited_ids is None: visited_ids = set()
    current_id = id(data)

    if depth > _MAX_DEPTH:
        return {
            'type': 'truncated',
            'value': f'<Max Depth {_MAX_DEPTH} Reached>',
            'id': f'trunc_{current_id}_{depth}'
        }
    if current_id in visited_ids:
        return {
            'type': 'recursive_ref',
            'value': f'<Recursive Reference: {type(data).__name__}>',
            'id': f'rec_{current_id}_{depth}'
        }

    rep: Dict[str, Any] = {}
    data_type_name = type(data).__name__
    rep['id'] = f"{data_type_name}_{current_id}_{depth}"
    rep['type'] = data_type_name
    rep['observableTracked'] = False

    try:
        visited_ids.add(current_id)

        if isinstance(data, ObservableValue):
            internal_value = data.get()
            nested_rep = _get_representation(internal_value, depth, visited_ids.copy())
            nested_rep['observableTracked'] = True
            obs_id = getattr(data, '_obs_value_id', None)
            nested_rep['id'] = obs_id if obs_id else nested_rep.get('id', f"obs_{current_id}_{depth}")
            return nested_rep

        elif data is None:
            rep['value'] = 'None'
            rep['type'] = 'NoneType'
        elif isinstance(data, (str, int, float, bool)):
            rep['value'] = data
        elif isinstance(data, (list, tuple)):
            rep['type'] = 'list'
            list_value_rep = []
            rep['length'] = len(data)
            count = 0
            for item in data:
                if count >= _MAX_ITEMS:
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
            rep['length'] = len(data)
            count = 0
            try:
                items_to_sort = [(repr(k), k, v) for k, v in data.items()]
                sorted_items = sorted(items_to_sort)
                processed_items = [(k, v) for _, k, v in sorted_items]
            except Exception as sort_err:
                logger.debug(f"Could not sort dict keys for {data_type_name} (id: {current_id}): {sort_err}.")
                processed_items = list(data.items())

            for k, v in processed_items:
                if count >= _MAX_ITEMS:
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
            rep['length'] = len(data)
            count = 0
            try:
                items_to_sort = [(repr(item), item) for item in data]
                sorted_items = sorted(items_to_sort)
                processed_items = [item for _, item in sorted_items]
            except Exception as sort_err:
                logger.debug(f"Could not sort set items for {data_type_name} (id: {current_id}): {sort_err}.")
                processed_items = list(data)

            for item in processed_items:
                if count >= _MAX_ITEMS:
                    set_value_rep.append({
                        'type': 'truncated',
                        'value': f'... ({len(data)} items total, showing first {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_trunc_{count}'
                    })
                    break
                set_value_rep.append(_get_representation(item, depth + 1, visited_ids.copy()))
                count += 1
            rep['value'] = set_value_rep
        else: # Generic object inspection
            rep['type'] = f"object ({data_type_name})"
            object_value_rep: Dict[str, Any] = {}
            attribute_count = 0
            skipped_attrs = 0
            attrs_to_process = {}
            try:
                attribute_names = dir(data)
            except Exception:
                attribute_names = []

            for attr_name in attribute_names:
                 if attr_name.startswith('_'):
                     continue
                 try:
                     attr_value = getattr(data, attr_name)
                     if callable(attr_value):
                         continue
                     attrs_to_process[attr_name] = attr_value
                 except Exception:
                     skipped_attrs += 1

            rep['length'] = len(attrs_to_process)
            try: sorted_attr_items = sorted(attrs_to_process.items())
            except TypeError: sorted_attr_items = list(attrs_to_process.items())

            for attr_name, attr_value in sorted_attr_items:
                if attribute_count >= _MAX_ITEMS:
                    object_value_rep['...'] = {
                        'type': 'truncated',
                        'value': f'... ({len(attrs_to_process)} attributes total, showing first {_MAX_ITEMS})',
                        'id': f'{rep["id"]}_attrtrunc_{attribute_count}'
                    }
                    break
                object_value_rep[attr_name] = _get_representation(attr_value, depth + 1, visited_ids.copy())
                attribute_count += 1
            rep['value'] = object_value_rep

            if attribute_count == 0 and skipped_attrs == 0 and not object_value_rep:
                 logger.debug(f"Object {data_type_name} (id: {current_id}) has no representable attributes. Falling back to repr().")
                 try:
                     rep['value'] = repr(data)
                     rep['type'] = f"repr ({data_type_name})"
                 except Exception as e_repr:
                    logger.warning(f"Failed to get repr() for object {data_type_name} (id: {current_id}): {e_repr}")
                    rep['value'] = f"<Object of type {data_type_name}, repr() failed: {e_repr}>"
                    rep['type'] = 'error'
    except Exception as e_main:
        logger.exception(f"Error generating representation for {data_type_name} (id: {current_id}) at depth {depth}")
        rep['type'] = 'error'
        rep['value'] = f"<Error representing object: {e_main}>"
        rep['id'] = rep.get('id', f"error_{current_id}_{depth}")
    finally:
        if current_id in visited_ids:
            visited_ids.remove(current_id)
    return rep


class Viz(BaseComponent):
    """Represents the Variable Visualizer (Viz) component instance in the Sidekick UI.

    Creates an interactive panel for displaying Python variables and data structures.
    Supports automatic updates for data wrapped in `sidekick.ObservableValue`.
    Can be nested within layout containers.

    Attributes:
        target_id (str): The unique identifier for this Viz panel instance.
    """
    def __init__(self, parent: Optional[Union['BaseComponent', str]] = None):
        """Initializes the Viz object and creates the UI panel.

        Args:
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, added to the root container.

        Raises:
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        spawn_payload = {} # Viz panel doesn't need initial config options in spawn
        super().__init__(
            component_type="viz",
            payload=spawn_payload,
            parent=parent # Pass the parent argument to BaseComponent
        )
        self._shown_variables: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Viz panel '{self.target_id}' initialized.")

    def _handle_observable_update(self, variable_name: str, change_details: Dict[str, Any]):
        """Internal callback for changes in a subscribed ObservableValue. (Internal)."""
        logger.debug(
            f"Viz '{self.target_id}': Received observable update for "
            f"variable '{variable_name}': {change_details}"
        )
        try:
            action_type = change_details.get("type", "unknown_update")
            path: List[Union[str, int]] = change_details.get("path", [])
            options: Dict[str, Any] = {"path": path}

            if "value" in change_details:
                options["valueRepresentation"] = _get_representation(change_details["value"])
            if "key" in change_details and change_details["key"] is not None:
                options["keyRepresentation"] = _get_representation(change_details["key"])
            if "length" in change_details and change_details["length"] is not None:
                options["length"] = change_details["length"]

            if action_type in ["set", "clear"] and not path:
                observable_instance = self._shown_variables.get(variable_name, {}).get('value_or_observable')
                if isinstance(observable_instance, ObservableValue):
                    logger.debug(
                        f"Viz '{self.target_id}': Handling root '{action_type}' for '{variable_name}'. "
                        f"Regenerating full representation."
                    )
                    full_representation = _get_representation(observable_instance)
                    options["valueRepresentation"] = full_representation
                    actual_data = observable_instance.get()
                    try:
                        options["length"] = len(actual_data) if hasattr(actual_data, '__len__') else None
                    except TypeError:
                        options["length"] = None
                    action_type = "set" # Ensure UI handles it as a full replacement
                else:
                    logger.warning(
                        f"Viz '{self.target_id}': ObservableValue for '{variable_name}' "
                        f"not found during root update. Skipping."
                    )
                    return

            update_payload = {
                "action": action_type,
                "variableName": variable_name,
                "options": options
            }
            self._send_update(update_payload)
        except Exception as e:
            logger.exception(
                f"Viz '{self.target_id}': Error processing observable update for variable "
                f"'{variable_name}'. Change details: {change_details}"
            )

    def show(self, name: str, value: Any):
        """Displays or updates a variable in the Sidekick Viz panel.

        If `value` is an `ObservableValue`, its changes will automatically update
        the Viz display. Otherwise, `show()` must be called again to reflect changes.

        Args:
            name (str): The name to display for this variable (must be non-empty).
            value (Any): The Python variable or value to visualize.

        Raises:
            ValueError: If `name` is empty or not a string.
            SidekickConnectionError: If sending the command fails.
        """
        if not isinstance(name, str) or not name:
            msg = "Variable name provided to viz.show() must be a non-empty string."
            logger.error(msg)
            raise ValueError(msg)

        unsubscribe_func: Optional[UnsubscribeFunction] = None

        if name in self._shown_variables:
            previous_entry = self._shown_variables[name]
            previous_unsubscribe = previous_entry.get('unsubscribe')
            if previous_unsubscribe:
                 logger.debug(
                    f"Viz '{self.target_id}': Unsubscribing previous observable "
                    f"for variable '{name}'."
                 )
                 try:
                     previous_unsubscribe()
                 except Exception as e_unsub:
                     logger.error(
                        f"Viz '{self.target_id}': Error during unsubscribe for '{name}': {e_unsub}"
                     )
                 previous_entry['unsubscribe'] = None

        if isinstance(value, ObservableValue):
            update_callback = functools.partial(self._handle_observable_update, name)
            try:
                unsubscribe_func = value.subscribe(update_callback)
                logger.info(
                    f"Viz '{self.target_id}': Subscribed to ObservableValue "
                    f"for variable '{name}'."
                )
            except Exception as e_sub:
                 logger.error(
                    f"Viz '{self.target_id}': Failed to subscribe to ObservableValue "
                    f"for '{name}': {e_sub}. Variable will not be reactive."
                 )
                 unsubscribe_func = None

        self._shown_variables[name] = {
            'value_or_observable': value,
            'unsubscribe': unsubscribe_func
        }

        try:
            representation = _get_representation(value)
        except Exception as e_repr:
            logger.exception(f"Viz '{self.target_id}': Error generating representation for '{name}'")
            representation = {
                "type": "error",
                "value": f"<Error creating display for '{name}': {e_repr}>",
                "id": f"error_{name}_{id(value)}",
                "observableTracked": False
            }

        actual_data = value.get() if isinstance(value, ObservableValue) else value
        data_length = None
        if hasattr(actual_data, '__len__') and callable(getattr(actual_data, '__len__')):
            try: data_length = len(actual_data)
            except TypeError: pass

        options: Dict[str, Any] = {
            "path": [],
            "valueRepresentation": representation
        }
        if data_length is not None:
            options["length"] = data_length

        set_payload = {
            "action": "set",
            "variableName": name,
            "options": options
        }
        self._send_update(set_payload)
        logger.debug(f"Viz '{self.target_id}': Sent 'set' update for variable '{name}'.")

    def remove_variable(self, name: str):
        """Removes a previously shown variable from the Viz panel display.

        Also unsubscribes if the variable was an `ObservableValue`.

        Args:
            name (str): The exact name of the variable to remove.

        Raises:
            SidekickConnectionError: If sending the command fails.
        """
        if name in self._shown_variables:
            entry = self._shown_variables.pop(name)
            unsubscribe_func = entry.get('unsubscribe')
            if unsubscribe_func:
                 logger.info(
                    f"Viz '{self.target_id}': Unsubscribing from observable variable '{name}' on removal."
                 )
                 try:
                     unsubscribe_func()
                 except Exception as e_unsub:
                     logger.error(
                        f"Viz '{self.target_id}': Error during unsubscribe for '{name}' on removal: {e_unsub}"
                     )

            remove_payload = {
                "action": "removeVariable",
                "variableName": name,
                "options": {}
            }
            self._send_update(remove_payload)
            logger.info(f"Viz '{self.target_id}': Sent 'removeVariable' command for '{name}'.")
        else:
            logger.warning(
                f"Viz '{self.target_id}': Attempted to remove variable '{name}', "
                f"but it was not found."
            )

    def remove(self):
        """Removes the entire Viz panel instance and unsubscribes from all observables."""
        logger.info(
            f"Requesting removal of Viz panel '{self.target_id}' and unsubscribing "
            f"from all tracked observables."
        )
        all_tracked_names = list(self._shown_variables.keys())
        for name in all_tracked_names:
            entry = self._shown_variables.pop(name, None)
            if entry:
                unsubscribe_func = entry.get('unsubscribe')
                if unsubscribe_func:
                     logger.debug(
                        f"Viz '{self.target_id}': Unsubscribing from '{name}' during panel removal."
                     )
                     try: unsubscribe_func()
                     except Exception as e:
                         logger.error(
                            f"Viz '{self.target_id}': Error unsubscribing from '{name}' "
                            f"during panel removal: {e}"
                         )
        self._shown_variables.clear()
        super().remove()

    def _reset_specific_callbacks(self):
        """Internal: Resets Viz-specific state when the component is removed. (Internal)."""
        super()._reset_specific_callbacks() # Call base class method
        # The main cleanup of _shown_variables (and unsubscribing) is handled
        # in the overridden remove() method to ensure it happens before the
        # component is actually removed from the UI. This method is called
        # as part of BaseComponent.remove() sequence.
        self._shown_variables.clear()
        logger.debug(f"Viz '{self.target_id}': Specific state (_shown_variables) cleared.")

    # __del__ inherited from BaseComponent for fallback handler unregistration.