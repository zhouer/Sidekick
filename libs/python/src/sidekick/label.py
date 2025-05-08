"""Provides the Label class for displaying static or dynamic text in Sidekick.

Use the `sidekick.Label` class to add a simple, non-interactive text label
to your Sidekick UI panel. You can set the initial text during creation and
update it later by setting the `text` property.

Labels are useful for displaying information, titles, or descriptions alongside
other components. They can be placed inside layout containers like `Row` or
`Column` by specifying the `parent` during initialization.
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Dict, Any, Union

class Label(BaseComponent):
    """Represents a non-interactive text Label component instance in the Sidekick UI.

    Creates a simple text display area. Update the displayed text by setting
    the `text` property.

    Attributes:
        target_id (str): The unique identifier for this label instance.
        text (str): The text currently displayed by the label.
    """
    def __init__(
        self,
        text: str = "",
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes the Label object and creates the UI element.

        Args:
            text (str): The initial text to display. Defaults to "".
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, added to the root container.

        Raises:
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        self._text = str(text)

        # Prepare the payload for the 'spawn' command.
        # Keys must be camelCase per the protocol.
        spawn_payload: Dict[str, Any] = {
            "text": self._text
        }

        super().__init__(
            component_type="label",
            payload=spawn_payload,
            parent=parent # Pass parent to BaseComponent
        )
        logger.info(f"Label '{self.target_id}' initialized with text '{self._text}'.")

    @property
    def text(self) -> str:
        """str: The text currently displayed by the label.

        Setting this property updates the label's text in the Sidekick UI.
        """
        return self._text

    @text.setter
    def text(self, new_text: str):
        """Sets the text displayed by the label."""
        new_text_str = str(new_text)
        # Update local state first
        self._text = new_text_str
        # Prepare payload for the 'setText' update action.
        # Keys must be camelCase per the protocol.
        payload = {
            "action": "setText",
            "options": {"text": new_text_str}
        }
        # Send the update command to the UI.
        self._send_update(payload)
        logger.debug(f"Label '{self.target_id}' text set to '{new_text_str}'.")

    # Labels are non-interactive, so no specific event handling or callbacks needed here.
    # The base _internal_message_handler is sufficient for handling potential errors.

    def _reset_specific_callbacks(self):
        """Internal: Resets label-specific callbacks (none currently)."""
        super()._reset_specific_callbacks()
        # No specific callbacks for Label currently.
        pass