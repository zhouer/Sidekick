"""Provides the Row class for horizontally arranging components in Sidekick.

Use the `sidekick.Row` class to create a container that lays out its child
components horizontally, one after the other, from left to right.

Components are added to a `Row` in several ways:
1.  By passing the `Row` instance as the `parent` argument when creating the
    child component:
    `my_row = sidekick.Row()`
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
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Dict, Any, Union, Callable, Tuple # Added Callable for on_error, Tuple for *children

class Row(BaseComponent):
    """Represents a Row layout container instance in the Sidekick UI.

    Child components added to this container will be arranged horizontally,
    from left to right.

    Attributes:
        target_id (str): The unique identifier for this row instance.
    """
    def __init__(
        self,
        # Note: Positional-only arguments before '*' were introduced in Python 3.8.
        # For broader compatibility, especially if targeting older Pythons
        # where Pyodide might be used, we keep `parent` as a regular keyword arg.
        # If we wanted `parent` to be positional-only, it would look like:
        # parent: Optional[Union['BaseComponent', str]] = None, / ,
        # *children: BaseComponent,
        # on_error: Optional[Callable[[str], None]] = None,
        *children: BaseComponent, # New: Accept variable number of child components
        parent: Optional[Union['BaseComponent', str]] = None, # Kept as keyword for clarity
        on_error: Optional[Callable[[str], None]] = None, # New: For BaseComponent
    ):
        """Initializes the Row layout container and creates the UI element.

        This function is called when you create a new Row, for example:
        `my_row = sidekick.Row()`
        or with initial children:
        `button = sidekick.Button("OK")`
        `my_row = sidekick.Row(button, parent=another_container)`

        It sends a message to the Sidekick UI to display a new horizontal
        layout container.

        Args:
            *children (BaseComponent): Zero or more Sidekick component instances
                (e.g., `Button`, `Label`, another `Row`) to be immediately added
                as children to this row. These child components must already exist.
                When `Row` is created, it will attempt to move each of these
                children into itself.
            parent (Optional[Union['BaseComponent', str]]): The parent container
                (e.g., a `sidekick.Column`) where this Row itself should be placed.
                If `None` (the default), the Row is added to the main Sidekick
                panel area.
            on_error (Optional[Callable[[str], None]]): A function to call if
                an error message related to this specific Row container (not its
                children) is sent back from the Sidekick UI. The function should
                accept one string argument (the error message). Defaults to `None`.

        Raises:
            SidekickConnectionError: If the library cannot connect to the
                Sidekick UI panel.
            TypeError: If `parent` is an invalid type, or if `on_error` is
                provided but is not a callable function. Or if any of `children`
                are not valid Sidekick component instances.
        """
        # Row spawn payload is currently empty according to the protocol.
        # Layout properties (like alignment or gap) might be added here in the future.
        spawn_payload: Dict[str, Any] = {}

        super().__init__(
            component_type="row",
            payload=spawn_payload,
            parent=parent,
            on_error=on_error
        )
        logger.info(f"Row layout container '{self.target_id}' initialized.")

        # Add any children provided directly in the constructor.
        if children:
            logger.debug(f"Row '{self.target_id}': Adding {len(children)} children from constructor.")
            for child_idx, child in enumerate(children):
                if isinstance(child, BaseComponent):
                    try:
                        # The add_child method handles sending the "changeParent" update
                        # for the child component.
                        self.add_child(child)
                    except Exception as e_add:
                        # Log the error but continue processing other children.
                        # This prevents one bad child from stopping the whole row init.
                        child_id_str = getattr(child, 'target_id', f"child at index {child_idx}")
                        logger.error(
                            f"Row '{self.target_id}': Error adding child '{child_id_str}' "
                            f"from constructor. Error: {e_add}"
                        )
                        # Depending on strictness, you might choose to re-raise here.
                else:
                    # Log a TypeError if a non-component was passed.
                    logger.error(
                        f"Row '{self.target_id}': Invalid child type passed to constructor "
                        f"at index {child_idx}: {type(child).__name__}. Expected a Sidekick component."
                    )
                    # Raise a TypeError to stop if an invalid child type is provided.
                    raise TypeError(
                        f"Invalid child type in Row constructor: Expected a Sidekick component "
                        f"(e.g., Button, Label), but got {type(child).__name__}."
                    )


    def add_child(self, child_component: BaseComponent):
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
            child_component (BaseComponent): The Sidekick component instance
                (e.g., a `Button`, `Textbox`, `Canvas`, another `Row`) to add
                as a child to this row.

        Raises:
            TypeError: If `child_component` is not a valid Sidekick component instance
                       (i.e., not derived from `BaseComponent`).
            SidekickConnectionError: If sending the update command to the UI fails.

        Example:
            >>> row_container = sidekick.Row()
            >>> my_button = sidekick.Button("Click Me") # Initially in root
            >>> my_label = sidekick.Label("Info")      # Initially in root
            >>>
            >>> # Move the button and label into the row
            >>> row_container.add_child(my_button)
            >>> row_container.add_child(my_label)
            >>> # Now my_button and my_label appear horizontally inside row_container
        """
        if not isinstance(child_component, BaseComponent):
            raise TypeError(
                f"Invalid child type for Row.add_child(): Expected a Sidekick component "
                f"instance (e.g., Button, Label), but got {type(child_component).__name__}."
            )

        # The child component is responsible for sending the 'update' command about itself,
        # specifying the 'changeParent' action and targeting this Row instance
        # (using its target_id) as the new parent.
        logger.debug(
            f"Row '{self.target_id}': Requesting to move child component "
            f"'{child_component.target_id}' (type: {child_component.component_type}) "
            f"into this row."
        )
        try:
            # The payload structure for 'changeParent' is defined by the protocol.
            # It needs the 'parent' ID and optionally 'insertBefore' for ordering.
            # For simple append, 'insertBefore' can be omitted.
            child_component._send_update({
                "action": "changeParent",
                "options": {
                    "parent": self.target_id
                    # 'insertBefore': null or omitted appends to the end by default.
                }
            })
        except Exception as e:
            logger.error(
                f"Row '{self.target_id}': Failed to send 'changeParent' update for "
                f"child '{child_component.target_id}'. Error: {e}"
            )
            # Re-raise the original exception (e.g., SidekickConnectionError)
            # so the caller is aware of the failure.
            raise e

    # Row, as a layout container, doesn't typically have its own specific events
    # triggered by user interaction directly on itself from the UI (like a button click).
    # Its primary role is to contain other components.
    # The base class's _internal_message_handler is sufficient for handling
    # potential 'error' messages related to the Row component itself.

    def _reset_specific_callbacks(self):
        """Internal: Resets row-specific callbacks (none currently).

        Called by `BaseComponent.remove()`. Row currently has no specific
        user-settable callbacks beyond `on_error` (handled by base).
        """
        super()._reset_specific_callbacks()
        # No specific callbacks unique to Row to reset at this time.
        pass