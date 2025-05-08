"""Provides the Markdown class for rendering Markdown content in Sidekick.

Use the `sidekick.Markdown` class to display text formatted using Markdown syntax
within your Sidekick UI panel. This allows for richer text presentation compared
to a simple `Label`, including headings, lists, bold/italic text, code blocks,
links, and potentially images (depending on the frontend implementation).

Markdown components can be placed inside layout containers like `Row` or `Column`
by specifying the `parent` during initialization.
"""

from . import logger
from .base_component import BaseComponent
from typing import Optional, Dict, Any, Union

class Markdown(BaseComponent):
    """Represents a component that renders Markdown formatted text in the Sidekick UI.

    Creates an area where Markdown source text is rendered as formatted content.
    Update the displayed content by setting the `source` property with a new
    Markdown string.

    Attributes:
        target_id (str): The unique identifier for this Markdown instance.
        source (str): The current Markdown source string being rendered.
    """
    def __init__(
        self,
        initial_source: str = "",
        parent: Optional[Union['BaseComponent', str]] = None,
    ):
        """Initializes the Markdown object and creates the UI element.

        Args:
            initial_source (str): The initial Markdown source string to render.
                Defaults to "".
            parent (Optional[Union['BaseComponent', str]]): The parent container.
                If `None`, added to the root container.

        Raises:
            SidekickConnectionError: If connection to Sidekick fails.
            TypeError: If `parent` is an invalid type.
        """
        self._source = str(initial_source)

        # Prepare the payload for the 'spawn' command.
        # Keys must be camelCase per the protocol.
        spawn_payload: Dict[str, Any] = {
            "initialSource": self._source
        }

        super().__init__(
            component_type="markdown",
            payload=spawn_payload,
            parent=parent # Pass parent to BaseComponent
        )
        logger.info(f"Markdown '{self.target_id}' initialized.")

    @property
    def source(self) -> str:
        """str: The current Markdown source string being rendered.

        Setting this property updates the rendered content in the Sidekick UI
        by providing a new Markdown string.
        """
        return self._source

    @source.setter
    def source(self, new_md_source: str):
        """Sets the Markdown source string to be rendered."""
        new_src_str = str(new_md_source)
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
        logger.debug(f"Markdown '{self.target_id}' source updated.")

    # Markdown components are typically non-interactive from the Python side
    # (clicks on rendered links etc. are handled by the browser/webview).
    # No specific event handling or callbacks needed here.

    def _reset_specific_callbacks(self):
        """Internal: Resets markdown-specific callbacks (none currently)."""
        super()._reset_specific_callbacks()
        # No specific callbacks for Markdown currently.
        pass