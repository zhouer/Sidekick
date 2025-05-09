"""Provides the Markdown class for rendering Markdown content in Sidekick.

Use the `sidekick.Markdown` class to display text formatted using Markdown syntax
within your Sidekick UI panel. This allows for richer text presentation compared
to a simple `Label`, including headings, lists, bold/italic text, code blocks,
links, and potentially images (depending on the frontend implementation's
capabilities).

Markdown components can be placed inside layout containers like `Row` or `Column`
by specifying the `parent` during initialization, or by adding them as children
to a container's constructor. You can also provide an `instance_id` to uniquely
identify the Markdown component.
"""

from . import logger
from .component import Component
from .events import ErrorEvent
from typing import Optional, Dict, Any, Union, Callable

class Markdown(Component):
    """Represents a component that renders Markdown formatted text in the Sidekick UI.

    Creates an area where Markdown source text is rendered as formatted content.
    You can set the initial Markdown string when creating the component and
    update the displayed content later by setting the `markdown.source` property
    with a new Markdown string.

    Example:
        `md_display = sidekick.Markdown("# Title\\nSome *italic* text.", instance_id="doc-viewer")`
        `md_display.source += "\\n- A list item"`

    Attributes:
        instance_id (str): The unique identifier for this Markdown instance.
        source (str): The current Markdown source string being rendered.
    """
    def __init__(
        self,
        source: str,
        instance_id: Optional[str] = None,
        parent: Optional[Union['Component', str]] = None,
        on_error: Optional[Callable[[ErrorEvent], None]] = None,
    ):
        """Initializes the Markdown object and creates the UI element.

        This function is called when you create a new Markdown component, for example:
        `notes = sidekick.Markdown("## Meeting Notes\\n- Discuss X\\n- Review Y", instance_id="meeting-notes")`

        It sends a message to the Sidekick UI to display a new area for
        rendering Markdown content.

        Args:
            source (str): The initial Markdown source string to render.
            instance_id (Optional[str]): An optional, user-defined unique identifier
                for this Markdown component. If `None`, an ID will be auto-generated.
                Must be unique if provided.
            parent (Optional[Union['Component', str]]): The parent container
                (e.g., a `sidekick.Row` or `sidekick.Column`) where this Markdown
                component should be placed. If `None` (the default), it's added
                to the main Sidekick panel area.
            on_error (Optional[Callable[[ErrorEvent], None]]): A function to call if
                an error message related to this specific Markdown component occurs
                in the Sidekick UI. The function should accept one `ErrorEvent` object
                as an argument. Defaults to `None`.

        Raises:
            ValueError: If the provided `instance_id` is invalid or a duplicate.
            SidekickConnectionError: If the library cannot connect to the
                Sidekick UI panel.
            TypeError: If `parent` is an invalid type, or if `on_error` is
                provided but is not a callable function.
        """
        # Ensure initial source is a string.
        self._source = str(source)

        # Prepare the payload for the 'spawn' command.
        # Keys must be camelCase per the protocol.
        spawn_payload: Dict[str, Any] = {
            "initialSource": self._source # Protocol uses 'initialSource'
        }

        super().__init__(
            component_type="markdown",
            payload=spawn_payload,
            instance_id=instance_id,
            parent=parent,
            on_error=on_error
        )
        logger.info(
            f"Markdown '{self.instance_id}' initialized with initial source " # Use self.instance_id
            f"length {len(self._source)}."
        )

    @property
    def source(self) -> str:
        """str: The current Markdown source string being rendered.

        Setting this property updates the rendered content in the Sidekick UI
        by providing a new Markdown string. For example:
        `my_markdown.source = "### New Section\\nDetails here."`
        """
        return self._source

    @source.setter
    def source(self, new_md_source: str):
        """Sets the Markdown source string to be rendered."""
        new_src_str = str(new_md_source) # Ensure it's a string
        # Update local state first
        self._source = new_src_str
        # Prepare payload for the 'setSource' update action.
        # Keys must be camelCase per the protocol.
        payload = {
            "action": "setSource",
            "options": {"source": new_src_str}
        }
        # Send the update command to the UI.
        self._send_update(payload)
        logger.debug(
            f"Markdown '{self.instance_id}' source updated " # Use self.instance_id
            f"(new length: {len(new_src_str)})."
        )

    # Markdown components are typically non-interactive from the Python script's
    # perspective (e.g., clicks on rendered links are handled by the browser/webview).
    # They don't send events like clicks back to Python.
    # The base _internal_message_handler is sufficient for handling
    # potential 'error' messages related to the Markdown component itself.
    # No need to override _internal_message_handler for specific "event" types.

    def _reset_specific_callbacks(self):
        """Internal: Resets markdown-specific callbacks (none currently).

        Called by `Component.remove()`. Markdown currently has no specific
        user-settable callbacks beyond `on_error` (handled by base).
        """
        super()._reset_specific_callbacks()
        # No specific callbacks unique to Markdown to reset at this time.
        logger.debug(f"Markdown '{self.instance_id}': No specific callbacks to reset.") # Use self.instance_id