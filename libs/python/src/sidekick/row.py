"""Provides the Row class for horizontally arranging components in Sidekick.

Use the `sidekick.Row` class to create a container that lays out its child
components horizontally, one after the other, from left to right.

Components are added to a `Row` in several ways:

1.  By passing the `Row` instance as the `parent` argument when creating the
    child component:
    `my_row = sidekick.Row(instance_id="button-bar")`
    `button_in_row = sidekick.Button("Hi", parent=my_row)`
2.  By calling the `row.add_child(component)` method after both the `Row` and
    the child component have been created:
    `my_button = sidekick.Button("Click")`
    `my_row = sidekick.Row()`
    `my_row.add_child(my_button)`
3.  By passing existing components directly to the `Row` constructor:
    `button1 = sidekick.Button("One")`
    `label1 = sidekick.Label("Info")`
    `my_row = sidekick.Row(button1, label1)`

Rows themselves can be nested within other containers (like `Column` or another `Row`).
You can also provide an `instance_id` to uniquely identify the Row.
"""

from . import logger
from .component import Component
from .events import ErrorEvent
from typing import Optional, Dict, Any, Union, Callable, Tuple, Coroutine

class Row(Component):
    """Represents a Row layout container instance in the Sidekick UI.

    Child components added to this container will be arranged horizontally,
    from left to right.

    Attributes:
        instance_id (str): The unique identifier for this row instance.
    """
    def __init__(
        self,
        *children: Component,
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_error: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
    ):
        """Initializes the Row layout container and creates the UI element.

        This function is called when you create a new Row, for example:
        `my_row = sidekick.Row()`
        or with initial children:
        `button = sidekick.Button("OK")`
        `my_row = sidekick.Row(button, parent=another_container, instance_id="action-row")`

        It sends a message to the Sidekick UI to display a new horizontal
        layout container.

        Args:
            *children (Component): Zero or more Sidekick component instances
                (e.g., `Button`, `Label`, another `Row`) to be immediately added
                as children to this row. These child components must already exist.
                When `Row` is created, it will attempt to move each of these
                children into itself.
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this Row. If `None`, an ID will be auto-generated. Must be
                unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Column`) where this Row itself should be placed.
                If `None` (the default), the Row is added to the main Sidekick
                panel area.
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call if
                an error message related to this specific Row container (not its
                children) is sent back from the Sidekick UI. The function should
                accept one `ErrorEvent` object as an argument. The callback can be a regular
                function or a coroutine function (async def). Defaults to `None`.

        Raises:
            ValueError: If the provided `instance_id` is invalid or a duplicate,
                        or if any of `children` are not valid Sidekick components.
            TypeError: If `parent` is an invalid type, or if `on_error` is
                provided but is not a callable function.
        """
        # Row spawn payload is currently empty according to the protocol.
        # Layout properties (like alignment or gap) might be added here in the future.
        spawn_payload: Dict[str, Any] = {}

        super().__init__(
            component_type="row",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        logger.info(f"Row layout container '{self.instance_id}' initialized.") # Use self.instance_id

        # Add any children provided directly in the constructor.
        if children:
            logger.debug(f"Row '{self.instance_id}': Adding {len(children)} children from constructor.") # Use self.instance_id
            for child_idx, child in enumerate(children):
                if isinstance(child, Component):
                    try:
                        # The add_child method handles sending the "changeParent" update
                        # for the child component.
                        self.add_child(child)
                    except Exception as e_add:
                        # Log the error but continue processing other children.
                        # This prevents one bad child from stopping the whole row init.
                        child_id_str = getattr(child, 'instance_id', f"child at index {child_idx}") # Use child's instance_id
                        logger.error(
                            f"Row '{self.instance_id}': Error adding child '{child_id_str}' " # Use self.instance_id
                            f"from constructor. Error: {e_add}"
                        )
                        # Depending on strictness, you might choose to re-raise here.
                else:
                    # Log a TypeError if a non-component was passed.
                    logger.error(
                        f"Row '{self.instance_id}': Invalid child type passed to constructor " # Use self.instance_id
                        f"at index {child_idx}: {type(child).__name__}. Expected a Sidekick component."
                    )
                    # Raise a TypeError to stop if an invalid child type is provided.
                    raise TypeError(
                        f"Invalid child type in Row constructor: Expected a Sidekick component "
                        f"(e.g., Button, Label), but got {type(child).__name__}."
                    )


    def add_child(self, child_component: Component):
        """Moves an existing component into this Row container.

        This method sends a command to the Sidekick UI instructing it to make
        the provided `child_component` a child of this `Row`. The child component
        will be visually placed inside the row layout, typically appended to the
        end of existing children (to the right of the last child).

        Note:
            The `child_component` must already exist (i.e., its `__init__` must
            have been called). This method changes the parentage of an existing
            component, effectively moving it.

        Args:
            child_component (Component): The Sidekick component instance
                (e.g., a `Button`, `Textbox`, `Canvas`, another `Row`) to add
                as a child to this row.

        Raises:
            TypeError: If `child_component` is not a valid Sidekick component instance
                       (i.e., not derived from `Component`).
            SidekickConnectionError: If sending the update command to the UI fails.

        Example:
            >>> row_container = sidekick.Row(instance_id="my-toolbar")
            >>> my_button = sidekick.Button("Click Me") # Initially in root
            >>> my_label = sidekick.Label("Info")      # Initially in root
            >>>
            >>> # Move the button and label into the row
            >>> row_container.add_child(my_button)
            >>> row_container.add_child(my_label)
            >>> # Now my_button and my_label appear horizontally inside row_container
        """
        if not isinstance(child_component, Component):
            raise TypeError(
                f"Invalid child type for Row.add_child(): Expected a Sidekick component "
                f"instance (e.g., Button, Label), but got {type(child_component).__name__}."
            )

        # The child component is responsible for sending the 'update' command about itself,
        # specifying the 'changeParent' action and targeting this Row instance
        # (using its instance_id) as the new parent.
        logger.debug(
            f"Row '{self.instance_id}': Requesting to move child component " # Use self.instance_id
            f"'{child_component.instance_id}' (type: {child_component.component_type}) " # Use child's instance_id
            f"into this row."
        )
        try:
            # The payload structure for 'changeParent' is defined by the protocol.
            # It needs the 'parent' ID (which is self.instance_id for this Row)
            # and optionally 'insertBefore' for ordering.
            # For simple append, 'insertBefore' can be omitted.
            child_component._send_update({
                "action": "changeParent",
                "options": {
                    "parent": self.instance_id # This Row's instance_id
                    # 'insertBefore': null or omitted appends to the end by default.
                }
            })
        except Exception as e:
            logger.error(
                f"Row '{self.instance_id}': Failed to send 'changeParent' update for " # Use self.instance_id
                f"child '{child_component.instance_id}'. Error: {e}" # Use child's instance_id
            )
            # Re-raise the original exception (e.g., SidekickConnectionError)
            # so the caller is aware of the failure.
            raise e

    # Row, as a layout container, doesn't typically have its own specific events
    # triggered by user interaction directly on itself from the UI (like a button click).
    # Its primary role is to contain other components.
    # The base class's _internal_message_handler is sufficient for handling
    # potential 'error' messages related to the Row component itself.
    # No need to override _internal_message_handler for specific "event" types.

    def _reset_specific_callbacks(self):
        """Internal: Resets row-specific callbacks (none currently).

        Called by `Component.remove()`. Row currently has no specific
        user-settable callbacks beyond `on_error` (handled by base).
        """
        super()._reset_specific_callbacks()
        # No specific callbacks unique to Row to reset at this time.
        logger.debug(f"Row '{self.instance_id}': No specific callbacks to reset.") # Use self.instance_id
