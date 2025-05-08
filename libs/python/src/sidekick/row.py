"""Provides the Row class for horizontally arranging components in Sidekick.

Use the `sidekick.Row` class to create a container that lays out its child
components horizontally, one after the other, from left to right.

Components are added to a `Row` either by passing the `Row` instance as the
`parent` argument when creating the child component, or by calling the
`row.add_child(component)` method after both the `Row` and the child component
have been created.

Rows themselves can be nested within other containers (like `Column` or another `Row`).
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Dict, Any, Union

class Row(BaseComponent):
    """Represents a Row layout container instance in the Sidekick UI.

    Child components added to this container will be arranged horizontally.

    Attributes:
        target_id (str): The unique identifier for this row instance.
    """
    def __init__(
        self,
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes the Row layout container and creates the UI element.

        Args:
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, the Row is added to the root container.

        Raises:
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        # Row spawn payload is currently empty according to the protocol.
        # Layout properties might be added here in the future if needed.
        spawn_payload: Dict[str, Any] = {}

        super().__init__(
            component_type="row",
            payload=spawn_payload,
            parent=parent # Pass parent to BaseComponent
        )
        logger.info(f"Row layout container '{self.target_id}' initialized.")

    def add_child(self, child_component: BaseComponent):
        """Moves an existing component into this Row container.

        This method sends a command to the Sidekick UI instructing it to make
        the provided `child_component` a child of this `Row`. The child component
        will be visually placed inside the row layout, typically appended to the
        end of existing children.

        Note:
            The `child_component` must already exist (i.e., its `__init__` must
            have been called). This method changes the parentage of an existing
            component.

        Args:
            child_component (BaseComponent): The Sidekick component instance
                (e.g., a `Button`, `Textbox`, `Canvas`, another `Row`) to add
                as a child to this row.

        Raises:
            TypeError: If `child_component` is not a valid Sidekick component instance.
            SidekickConnectionError: If sending the update command fails.

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
                f"Invalid child type: Expected a Sidekick component instance "
                f"(e.g., Button, Label), but got {type(child_component).__name__}."
            )

        # The child component sends the 'update' command about itself,
        # specifying the 'changeParent' action and targeting this Row instance as the new parent.
        logger.debug(
            f"Row '{self.target_id}': Requesting to move child component "
            f"'{child_component.target_id}' into this row."
        )
        try:
            child_component._send_update({
                "action": "changeParent",
                "options": {
                    "parent": self.target_id
                    # 'insertBefore' could be added here later for ordered insertion
                }
            })
        except Exception as e:
            logger.error(
                f"Row '{self.target_id}': Failed to send changeParent update for "
                f"child '{child_component.target_id}'. Error: {e}"
            )
            # Re-raise the exception (e.g., SidekickConnectionError)
            raise e

    # Row doesn't have specific events or callbacks from the UI itself.
    # The base _internal_message_handler handles potential errors for the Row.

    def _reset_specific_callbacks(self):
        """Internal: Resets row-specific callbacks (none currently)."""
        super()._reset_specific_callbacks()
        # No specific callbacks for Row currently.
        pass