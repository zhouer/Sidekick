"""Provides the Column class for vertically arranging components in Sidekick.

Use the `sidekick.Column` class to create a container that lays out its child
components vertically, one below the other, from top to bottom.

Components are added to a `Column` either by passing the `Column` instance as the
`parent` argument when creating the child component, or by calling the
`column.add_child(component)` method after both the `Column` and the child component
have been created.

Columns themselves can be nested within other containers (like `Row` or another `Column`).
The default top-level container in Sidekick also behaves like a Column.
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Dict, Any, Union

class Column(BaseComponent):
    """Represents a Column layout container instance in the Sidekick UI.

    Child components added to this container will be arranged vertically.

    Attributes:
        target_id (str): The unique identifier for this column instance.
    """
    def __init__(
        self,
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes the Column layout container and creates the UI element.

        Args:
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, the Column is added to the root container.

        Raises:
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        # Column spawn payload is currently empty according to the protocol.
        spawn_payload: Dict[str, Any] = {}

        super().__init__(
            component_type="column",
            payload=spawn_payload,
            parent=parent # Pass parent to BaseComponent
        )
        logger.info(f"Column layout container '{self.target_id}' initialized.")

    def add_child(self, child_component: BaseComponent):
        """Moves an existing component into this Column container.

        This method sends a command to the Sidekick UI instructing it to make
        the provided `child_component` a child of this `Column`. The child component
        will be visually placed inside the column layout, typically appended to the
        end of existing children.

        Note:
            The `child_component` must already exist (i.e., its `__init__` must
            have been called). This method changes the parentage of an existing
            component.

        Args:
            child_component (BaseComponent): The Sidekick component instance
                (e.g., a `Button`, `Textbox`, `Grid`, another `Column`) to add
                as a child to this column.

        Raises:
            TypeError: If `child_component` is not a valid Sidekick component instance.
            SidekickConnectionError: If sending the update command fails.

        Example:
            >>> col_container = sidekick.Column()
            >>> title_label = sidekick.Label("Settings") # Initially in root
            >>> activate_button = sidekick.Button("Activate") # Initially in root
            >>>
            >>> # Move the label and button into the column
            >>> col_container.add_child(title_label)
            >>> col_container.add_child(activate_button)
            >>> # Now title_label and activate_button appear vertically inside col_container
        """
        if not isinstance(child_component, BaseComponent):
            raise TypeError(
                f"Invalid child type: Expected a Sidekick component instance "
                f"(e.g., Button, Label), but got {type(child_component).__name__}."
            )

        # The child component sends the 'update' command about itself,
        # specifying the 'changeParent' action and targeting this Column instance as the new parent.
        logger.debug(
            f"Column '{self.target_id}': Requesting to move child component "
            f"'{child_component.target_id}' into this column."
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
                f"Column '{self.target_id}': Failed to send changeParent update for "
                f"child '{child_component.target_id}'. Error: {e}"
            )
            # Re-raise the exception (e.g., SidekickConnectionError)
            raise e

    # Column doesn't have specific events or callbacks from the UI itself.
    # The base _internal_message_handler handles potential errors for the Column.

    def _reset_specific_callbacks(self):
        """Internal: Resets column-specific callbacks (none currently)."""
        super()._reset_specific_callbacks()
        # No specific callbacks for Column currently.
        pass