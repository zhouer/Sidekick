"""Provides the Column class for vertically arranging components in Sidekick.

Use the `sidekick.Column` class to create a container that lays out its child
components vertically, one below the other, from top to bottom.

Components are added to a `Column` in several ways:

1.  By passing the `Column` instance as the `parent` argument when creating the
    child component:
    `my_col = sidekick.Column(instance_id="main-layout")`
    `label_in_col = sidekick.Label("Title", parent=my_col)`
2.  By calling the `column.add_child(component)` method after both the `Column`
    and the child component have been created:
    `my_input = sidekick.Textbox()`
    `my_col = sidekick.Column()`
    `my_col.add_child(my_input)`
3.  By passing existing components directly to the `Column` constructor:
    `label1 = sidekick.Label("First")`
    `button1 = sidekick.Button("Submit")`
    `my_col = sidekick.Column(label1, button1)`

Columns themselves can be nested within other containers (like `Row` or another `Column`).
The default top-level container in Sidekick also behaves like a Column.
You can also provide an `instance_id` to uniquely identify the Column.
"""

from . import logger
from .component import Component
from .events import ErrorEvent
from typing import Optional, Dict, Any, Union, Callable, Tuple, Coroutine

class Column(Component):
    """Represents a Column layout container instance in the Sidekick UI.

    Child components added to this container will be arranged vertically,
    one below the other.

    Attributes:
        instance_id (str): The unique identifier for this column instance.
    """
    def __init__(
        self,
        *children: Component,
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_error: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
    ):
        """Initializes the Column layout container and creates the UI element.

        This function is called when you create a new Column, for example:
        `my_column = sidekick.Column()`
        or with initial children:
        `label = sidekick.Label("Name:")`
        `my_column = sidekick.Column(label, parent=another_container, instance_id="form-column")`

        It sends a message to the Sidekick UI to display a new vertical
        layout container.

        Args:
            *children (Component): Zero or more Sidekick component instances
                (e.g., `Button`, `Label`, another `Column`) to be immediately
                added as children to this column. These child components must
                already exist. When `Column` is created, it will attempt to
                move each of these children into itself.
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this Column. If `None`, an ID will be auto-generated. Must be
                unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Row`) where this Column itself should be placed.
                If `None` (the default), the Column is added to the main Sidekick
                panel area (which acts like a root column).
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call if
                an error message related to this specific Column container (not its
                children) is sent back from the Sidekick UI. The function should
                accept one `ErrorEvent` object as an argument. The callback can be a regular
                function or a coroutine function (async def). Defaults to `None`.

        Raises:
            ValueError: If the provided `instance_id` is invalid or a duplicate,
                        or if any of `children` are not valid Sidekick components.
            TypeError: If `parent` is an invalid type, or if `on_error` is
                provided but is not a callable function.
        """
        # Column spawn payload is currently empty according to the protocol.
        # Layout properties (like alignment or gap) might be added here in the future.
        spawn_payload: Dict[str, Any] = {}

        super().__init__(
            component_type="column",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        logger.info(f"Column layout container '{self.instance_id}' initialized.") # Use self.instance_id

        # Add any children provided directly in the constructor.
        if children:
            logger.debug(f"Column '{self.instance_id}': Adding {len(children)} children from constructor.") # Use self.instance_id
            for child_idx, child in enumerate(children):
                if isinstance(child, Component):
                    try:
                        # The add_child method handles sending the "changeParent" update
                        # for the child component.
                        self.add_child(child)
                    except Exception as e_add:
                        # Log the error but continue processing other children.
                        child_id_str = getattr(child, 'instance_id', f"child at index {child_idx}") # Use child's instance_id
                        logger.error(
                            f"Column '{self.instance_id}': Error adding child '{child_id_str}' " # Use self.instance_id
                            f"from constructor. Error: {e_add}"
                        )
                        # Optionally re-raise if strictness is preferred.
                else:
                    # Log a TypeError if a non-component was passed.
                    logger.error(
                        f"Column '{self.instance_id}': Invalid child type passed to constructor " # Use self.instance_id
                        f"at index {child_idx}: {type(child).__name__}. Expected a Sidekick component."
                    )
                    # Raise a TypeError to stop if an invalid child type is provided.
                    raise TypeError(
                        f"Invalid child type in Column constructor: Expected a Sidekick component "
                        f"(e.g., Button, Label), but got {type(child).__name__}."
                    )

    def add_child(self, child_component: Component):
        """Moves an existing component into this Column container.

        This method sends a command to the Sidekick UI instructing it to make
        the provided `child_component` a child of this `Column`. The child component
        will be visually placed inside the column layout, typically appended to the
        end of existing children (below the last child).

        Note:
            The `child_component` must already exist (i.e., its `__init__` must
            have been called). This method changes the parentage of an existing
            component, effectively moving it.

        Args:
            child_component (Component): The Sidekick component instance
                (e.g., a `Button`, `Textbox`, `Grid`, another `Column`) to add
                as a child to this column.

        Raises:
            TypeError: If `child_component` is not a valid Sidekick component instance
                       (i.e., not derived from `Component`).
            SidekickConnectionError: If sending the update command to the UI fails.

        Example:
            >>> col_container = sidekick.Column(instance_id="content-area")
            >>> title_label = sidekick.Label("Settings") # Initially in root
            >>> activate_button = sidekick.Button("Activate") # Initially in root
            >>>
            >>> # Move the label and button into the column
            >>> col_container.add_child(title_label)
            >>> col_container.add_child(activate_button)
            >>> # Now title_label and activate_button appear vertically inside col_container
        """
        if not isinstance(child_component, Component):
            raise TypeError(
                f"Invalid child type for Column.add_child(): Expected a Sidekick component "
                f"instance (e.g., Button, Label), but got {type(child_component).__name__}."
            )

        # The child component is responsible for sending the 'update' command about itself,
        # specifying the 'changeParent' action and targeting this Column instance
        # (using its instance_id) as the new parent.
        logger.debug(
            f"Column '{self.instance_id}': Requesting to move child component " # Use self.instance_id
            f"'{child_component.instance_id}' (type: {child_component.component_type}) " # Use child's instance_id
            f"into this column."
        )
        try:
            # The payload structure for 'changeParent' is defined by the protocol.
            child_component._send_update({
                "action": "changeParent",
                "options": {
                    "parent": self.instance_id # This Column's instance_id
                    # 'insertBefore': null or omitted appends to the end by default.
                }
            })
        except Exception as e:
            logger.error(
                f"Column '{self.instance_id}': Failed to send 'changeParent' update for " # Use self.instance_id
                f"child '{child_component.instance_id}'. Error: {e}" # Use child's instance_id
            )
            # Re-raise the original exception (e.g., SidekickConnectionError).
            raise e

    # Column, as a layout container, doesn't typically have its own specific events
    # triggered by user interaction directly on itself from the UI.
    # The base class's _internal_message_handler is sufficient for handling
    # potential 'error' messages related to the Column component itself.

    def _reset_specific_callbacks(self):
        """Internal: Resets column-specific callbacks (none currently).

        Called by `Component.remove()`. Column currently has no specific
        user-settable callbacks beyond `on_error` (handled by base).
        """
        super()._reset_specific_callbacks()
        # No specific callbacks unique to Column to reset at this time.
        logger.debug(f"Column '{self.instance_id}': No specific callbacks to reset.") # Use self.instance_id
