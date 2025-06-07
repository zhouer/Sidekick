"""Configuration for Sidekick server connections.

This module defines the structure for server configurations and provides a default
list of servers that the Sidekick Python library will attempt to connect to.
It also manages any user-defined URL set via `sidekick.set_url()`.

The primary components are:

- `ServerConfig`: A data class holding details for a single server endpoint,
  including its WebSocket URL, an optional UI URL (for remote servers), and
  flags indicating if a session ID is needed and if the UI URL should be shown.
- `DEFAULT_SERVERS`: A list of `ServerConfig` instances. The library will
  iterate through this list, attempting to connect, starting with local options
  and falling back to remote ones if specified.
- Functions to manage a user-specified URL, which, if set, overrides the
  `DEFAULT_SERVERS` list.
"""
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ServerConfig:
    """Data class representing the configuration for a single Sidekick server.

    Attributes:
        name (str): A human-readable name for the server (e.g., "Local VS Code", "Sidekick Cloud").
        ws_url (str): The WebSocket URL for the Sidekick server (e.g., "ws://localhost:5163").
        ui_url (Optional[str]): The base URL for the web-based UI, if applicable
            (e.g., "https://remote-sidekick-ui.com"). Used for remote servers where
            the UI is hosted separately. For local VS Code, this is typically `None`.
        requires_session_id (bool): If `True`, a unique session ID will be generated
            and appended to both `ws_url` (as a query parameter `?session=`) and
            `ui_url` (typically as a path segment, e.g., `/session_id`).
            Defaults to `False`.
        show_ui_url (bool): If `True` and a connection to this server is successful,
            the (potentially session-specific) `ui_url` will be printed to the console,
            prompting the user to open it. Defaults to `False`.
    """
    name: str
    ws_url: str
    ui_url: Optional[str] = None
    requires_session_id: bool = False
    show_ui_url: bool = False

DEFAULT_SERVERS: List[ServerConfig] = [
    ServerConfig(
        name='VS Code Extension',
        ws_url='ws://localhost:5163',
        ui_url=None, # UI is within VS Code panel, no separate URL needed
        requires_session_id=False,
        show_ui_url=False,
    ),
    ServerConfig(
        name='Sidekick Cloud',
        ws_url='wss://ws-sidekick.zhouer.workers.dev',
        ui_url='https://ui-sidekick.pages.dev',
        requires_session_id=True,
        show_ui_url=True,
    ),
]

# --- User-defined URL Management ---

# This global variable stores the URL if the user explicitly sets one
# using sidekick.set_url(). If None, the DEFAULT_SERVERS list is used.
_user_set_url: Optional[str] = None

def get_user_set_url() -> Optional[str]:
    """Retrieves the WebSocket URL explicitly set by the user.

    If `sidekick.set_url()` has been called with a URL, this function returns that URL.
    Otherwise, it returns `None`, indicating that the default server list should be used.

    Returns:
        Optional[str]: The user-set URL, or `None` if not set.
    """
    return _user_set_url

def set_user_url_globally(url: Optional[str]) -> None:
    """Sets or clears the user-defined WebSocket URL.

    This function is called internally by `sidekick.set_url()` to store the
    user's preference.

    Args:
        url (Optional[str]): The WebSocket URL to set (e.g., "ws://custom.server/ws").
            If `None`, it clears any previously set user URL, reverting to the
            default server list behavior.

    Raises:
        ValueError: If the provided `url` is not `None` and is not a valid
                    WebSocket URL format (i.e., does not start with "ws://" or "wss://").
    """
    global _user_set_url
    if url is not None:
        if not isinstance(url, str) or not (url.startswith("ws://") or url.startswith("wss://")):
            raise ValueError(
                "Invalid WebSocket URL provided to sidekick.set_url(). "
                "URL must be a string starting with 'ws://' or 'wss://'."
            )
    _user_set_url = url
