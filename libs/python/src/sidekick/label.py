"""Provides the Label class for displaying static or dynamic text in Sidekick.

Use the `sidekick.Label` class to add a simple, non-interactive text label
to your Sidekick UI panel. You can set the initial text during creation and
update it later by setting the `text` property.

Labels are useful for displaying information, titles, or descriptions alongside
other components. They can be placed inside layout containers like `Row` or
`Column` by specifying the `parent` during initialization, or by adding them
as children to a container's constructor. You can also provide an `instance_id`
to uniquely identify the label.
"""

from . import logger
from .component import Component
from .events import ErrorEvent
from typing import Optional, Dict, Any, Union, Callable, Coroutine

class Label(Component):
    """Represents a non-interactive text Label component instance in the Sidekick UI.

    Creates a simple text display area. You can set the initial text when creating
    the label and update the displayed text later by setting the `label.text` property.

    Example:
        `status_label = sidekick.Label("Status: Idle", instance_id="status-display")`
        `status_label.text = "Status: Processing..."`

    Attributes:
        instance_id (str): The unique identifier for this label instance.
        text (str): The text currently displayed by the label.
    """
    def __init__(
        self,
        text: str = "",
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_error: Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]] = None,
    ):
        """Initializes the Label object and creates the UI element.

        This function is called when you create a new Label, for example:
        `title = sidekick.Label("My Application Title", instance_id="main-title")`

        It sends a message to the Sidekick UI to display a new text label.

        Args:
            text (str): The initial text to display on the label.
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this label. If `None`, an ID will be auto-generated. Must be
                unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Row` or `sidekick.Column`) where this label
                should be placed. If `None` (the default), the label is added
                to the main Sidekick panel area.
            on_error (Optional[Callable[[ErrorEvent], Union[None, Coroutine[Any, Any, None]]]]): A function to call if
                an error message related to this specific label occurs in the
                Sidekick UI. The function should accept one `ErrorEvent` object
                as an argument. The callback can be a regular function or a coroutine function (async def).
                Defaults to `None`.

        Raises:
            ValueError: If the provided `instance_id` is invalid or a duplicate.
            TypeError: If `parent` is an invalid type, or if `on_error` is
                provided but is not a callable function.
        """
        # Ensure initial text is a string.
        self._text = str(text)

        # Prepare the payload for the 'spawn' command.
        spawn_payload: Dict[str, Any] = {
            "text": self._text
        }

        super().__init__(
            component_type="label",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        logger.info(
            f"Label '{self.instance_id}' initialized with text " # Use self.instance_id
            f"'{self._text[:50]}{'...' if len(self._text) > 50 else ''}'."
        )

    @property
    def text(self) -> str:
        """str: The text currently displayed by the label.

        Setting this property updates the label's text in the Sidekick UI.
        For example:
        `my_label.text = "New information here"`
        """
        return self._text

    @text.setter
    def text(self, new_text: str):
        """Sets the text displayed by the label."""
        new_text_str = str(new_text) # Ensure it's a string
        # Update local state first
        self._text = new_text_str
        # Prepare payload for the 'setText' update action.
        payload = {
            "action": "setText",
            "options": {"text": new_text_str}
        }
        # Send the update command to the UI.
        self._send_update(payload)
        logger.debug(
            f"Label '{self.instance_id}' text set to " # Use self.instance_id
            f"'{new_text_str[:50]}{'...' if len(new_text_str) > 50 else ''}'."
        )

    # Labels are non-interactive from the Python script's perspective
    # (they don't send events like clicks back to Python).
    # The base _internal_message_handler is sufficient for handling
    # potential 'error' messages related to the Label itself.
    # No need to override _internal_message_handler for specific "event" types.

    def _reset_specific_callbacks(self):
        """Internal: Resets label-specific callbacks (none currently).

        Called by `Component.remove()`. Label currently has no specific
        user-settable callbacks beyond `on_error` (handled by base).
        """
        super()._reset_specific_callbacks()
        # No specific callbacks unique to Label to reset at this time.
        logger.debug(f"Label '{self.instance_id}': No specific callbacks to reset.") # Use self.instance_id
