"""Manages the process of connecting to a Sidekick server.

This module defines the `ServerConnector` class, which is responsible for
attempting to establish a communication channel with a Sidekick server.
It implements a prioritized connection strategy:
1. If in a Pyodide environment, it attempts to use the Pyodide-specific bridge.
2. If a URL has been explicitly set by the user (via `sidekick.set_url()`),
   it attempts to connect directly to that URL.
3. Otherwise, it iterates through a predefined list of default servers (local
   VS Code extension first, then remote cloud servers) and tries to connect
   to each one in order.

The connector handles session ID generation and URL modification for servers
that require it. Upon a successful connection, it returns details including the
active `CommunicationManager`, any UI URL that should be displayed to the user,
and hints about installing the VS Code extension for a better experience.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from .config import ServerConfig, DEFAULT_SERVERS, get_user_set_url
from .utils import generate_session_id
from .core import (
    TaskManager,
    CommunicationManager,
    CoreConnectionError,
    CoreConnectionRefusedError,
    CoreConnectionTimeoutError,
    is_pyodide,
    MessageHandlerType,
    StatusChangeHandlerType,
    ErrorHandlerType
)
from .core.factories import (
    create_websocket_communication_manager,
    create_pyodide_communication_manager,
)
from .exceptions import SidekickConnectionError, SidekickConnectionRefusedError

logger = logging.getLogger(__name__)

@dataclass
class ConnectionAttemptResult:
    """Holds the result of a single attempt to connect to a server.

    Attributes:
        success (bool): True if the connection attempt was successful, False otherwise.
        communication_manager (Optional[CommunicationManager]): The active
            CommunicationManager instance if the connection succeeded.
        final_ws_url (Optional[str]): The actual WebSocket URL used for the attempt
            (potentially with a session ID).
        ui_url_to_show (Optional[str]): The UI URL (potentially with a session ID)
            that should be shown to the user if this connection is chosen and
            `show_ui_url_hint` is True.
        show_ui_url_hint (bool): Flag indicating if the `ui_url_to_show` should
            be printed along with an installation hint for the VS Code extension.
        error (Optional[Exception]): The exception encountered if the attempt failed.
        server_name (Optional[str]): The name of the server that was attempted.
    """
    success: bool
    communication_manager: Optional[CommunicationManager] = None
    final_ws_url: Optional[str] = None
    ui_url_to_show: Optional[str] = None
    show_ui_url_hint: bool = False
    error: Optional[Exception] = None
    server_name: Optional[str] = None


@dataclass
class ConnectionResult:
    """Holds the details of a successfully established connection.

    This object is returned by `ServerConnector.connect_async()` upon success.

    Attributes:
        communication_manager (CommunicationManager): The active and connected
            CommunicationManager instance.
        ui_url_to_show (Optional[str]): The UI URL (if any) that should be
            displayed to the user (e.g., for remote cloud UIs).
        show_ui_url_hint (bool): True if a hint to install the VS Code extension
            should be shown along with the `ui_url_to_show`.
        server_name (Optional[str]): The name of the server to which the
            successful connection was made.
    """
    communication_manager: CommunicationManager
    ui_url_to_show: Optional[str] = None
    show_ui_url_hint: bool = False
    server_name: Optional[str] = None


class ServerConnector:
    """Manages the process of connecting to a Sidekick server.

    This class tries different connection strategies in a specific order:
    1. Pyodide environment (if applicable).
    2. User-defined URL (if set via `sidekick.set_url()`).
    3. A list of default servers (e.g., local VS Code, remote cloud).

    It handles session ID generation for remote servers and prepares
    the necessary information for the `ConnectionService` to proceed
    after a successful connection.
    """
    def __init__(self, task_manager: TaskManager):
        """Initializes the ServerConnector.

        Args:
            task_manager (TaskManager): The TaskManager instance to be used for
                creating CommunicationManagers.
        """
        self._task_manager = task_manager
        self._local_server_name = DEFAULT_SERVERS[0].name if DEFAULT_SERVERS else "Local Server"


    def _build_ws_url_with_session(self, base_url: str, session_id: str) -> str:
        """Appends a session_id as a query parameter to a WebSocket URL.

        Ensures that if other query parameters exist, they are preserved.
        The 'session' parameter will be added or overwritten.

        Args:
            base_url (str): The base WebSocket URL.
            session_id (str): The session ID to append.

        Returns:
            str: The WebSocket URL with the session ID included.
        """
        parsed_url = urlparse(base_url)
        query_params = parse_qs(parsed_url.query)
        query_params['session'] = [session_id] # Add or overwrite session ID
        new_query_string = urlencode(query_params, doseq=True)
        # Reconstruct the URL with the modified query string
        return urlunparse(parsed_url._replace(query=new_query_string))

    def _build_ui_url_with_session_path(self, base_ui_url: str, session_id: str) -> str:
        """Appends a session_id as a path segment to a UI URL.

        This is a common pattern for single-page applications (SPAs) like those
        hosted on Cloudflare Pages, where the session ID might be part of the path.
        Example: `https://ui.example.com` -> `https://ui.example.com/session/12345678`

        Args:
            base_ui_url (str): The base UI URL.
            session_id (str): The session ID to append as a path segment.

        Returns:
            str: The UI URL with the session ID appended as a path.
        """
        # Ensure there's no trailing slash on the base URL before appending path segment
        if base_ui_url.endswith('/'):
            return f"{base_ui_url}session/{session_id}"
        return f"{base_ui_url}/session/{session_id}"

    async def _attempt_single_ws_connection(
        self,
        server_config: ServerConfig,
        message_handler: Optional[MessageHandlerType],
        status_change_handler: Optional[StatusChangeHandlerType],
        error_handler: Optional[ErrorHandlerType]
    ) -> ConnectionAttemptResult:
        """Attempts to connect to a single WebSocket server configuration.

        This method handles session ID generation (if required by `server_config`)
        and the actual WebSocket connection attempt using a new
        `WebSocketCommunicationManager`.

        Args:
            server_config (ServerConfig): The configuration for the server to attempt.
            message_handler (Optional[MessageHandlerType]): Callback for incoming messages.
            status_change_handler (Optional[StatusChangeHandlerType]): Callback for status changes.
            error_handler (Optional[ErrorHandlerType]): Callback for communication errors.

        Returns:
            ConnectionAttemptResult: An object detailing the outcome of this attempt.
        """
        session_id_generated: Optional[str] = None
        final_ws_url = server_config.ws_url
        ui_url_to_show: Optional[str] = None

        if server_config.requires_session_id:
            session_id_generated = generate_session_id()
            final_ws_url = self._build_ws_url_with_session(server_config.ws_url, session_id_generated)
            if server_config.ui_url:
                ui_url_to_show = self._build_ui_url_with_session_path(server_config.ui_url, session_id_generated)
            logger.info(
                f"Using session ID '{session_id_generated}' for server '{server_config.name}'."
            )
        elif server_config.ui_url and server_config.show_ui_url: # Case for remote server not needing session but still showing a UI URL
            ui_url_to_show = server_config.ui_url


        logger.info(f"Attempting WebSocket connection to server '{server_config.name}' at: {final_ws_url}")
        # Create a new WebSocketCommunicationManager for each attempt.
        cm = create_websocket_communication_manager(final_ws_url, self._task_manager)

        try:
            await cm.connect_async(
                message_handler=message_handler,
                status_change_handler=status_change_handler,
                error_handler=error_handler
            )

            # After connect_async returns, cm.is_connected() should be true if successful.
            if cm.is_connected():
                logger.info(f"Successfully connected to server '{server_config.name}' at {final_ws_url}.")
                # For the local server, add a very brief pause. This can sometimes help
                # ensure the VS Code panel's WebView is fully ready to receive messages
                # immediately after connection, mitigating potential race conditions on startup.
                if server_config.name == self._local_server_name:
                    await asyncio.sleep(0.1)
                    # Re-check connection after sleep, though unlikely to change for local stable server.
                    if not cm.is_connected(): # pragma: no cover
                        logger.warning(f"Local server '{server_config.name}' disconnected during brief stabilization pause.")
                        # Treat as a failed attempt.
                        return ConnectionAttemptResult(
                            success=False,
                            error=CoreConnectionError("Local server disconnected immediately after connection."),
                            server_name=server_config.name
                        )

                return ConnectionAttemptResult(
                    success=True,
                    communication_manager=cm,
                    final_ws_url=final_ws_url,
                    ui_url_to_show=ui_url_to_show if server_config.show_ui_url else None,
                    show_ui_url_hint=server_config.show_ui_url, # Pass the flag directly
                    server_name=server_config.name
                )
            else: # pragma: no cover
                # This case should ideally be covered by connect_async raising an error.
                # If connect_async completes without error but is_connected is false,
                # it's an unexpected state.
                logger.error(
                    f"Connection attempt to server '{server_config.name}' ({final_ws_url}) "
                    "returned from connect_async, but CommunicationManager reports not connected."
                )
                return ConnectionAttemptResult(
                    success=False,
                    error=CoreConnectionError(
                        f"CommunicationManager for '{server_config.name}' did not report connected "
                        "after connect_async."
                    ),
                    server_name=server_config.name
                )

        except (CoreConnectionRefusedError, CoreConnectionTimeoutError) as e:
            # These are expected errors if the server is not available or unresponsive.
            logger.warning(
                f"Connection to server '{server_config.name}' ({final_ws_url}) failed: "
                f"{type(e).__name__} (URL: {e.url or 'N/A'})."
            )
            return ConnectionAttemptResult(success=False, error=e, server_name=server_config.name)
        except CoreConnectionError as e: # Catch other specific core connection errors
            logger.warning(
                f"Connection to server '{server_config.name}' ({final_ws_url}) "
                f"failed with CoreConnectionError: {e}"
            )
            return ConnectionAttemptResult(success=False, error=e, server_name=server_config.name)
        except Exception as e: # pragma: no cover
            # Catch any other unexpected exceptions during the connection attempt.
            logger.exception(
                f"Unexpected error during connection attempt to server '{server_config.name}' "
                f"({final_ws_url}): {e}"
            )
            return ConnectionAttemptResult(success=False, error=e, server_name=server_config.name)

    async def connect_async(
        self,
        message_handler: Optional[MessageHandlerType],
        status_change_handler: Optional[StatusChangeHandlerType],
        error_handler: Optional[ErrorHandlerType]
    ) -> ConnectionResult:
        """Attempts to establish a Sidekick connection using various strategies.

        The connection order of priority is:
        1.  Pyodide environment (if detected).
        2.  User-defined URL (if provided via `sidekick.set_url()`).
        3.  Default server list (from `sidekick.config.DEFAULT_SERVERS`).

        Args:
            message_handler (Optional[MessageHandlerType]): Callback for incoming messages.
            status_change_handler (Optional[StatusChangeHandlerType]): Callback for status changes.
            error_handler (Optional[ErrorHandlerType]): Callback for communication errors.

        Returns:
            ConnectionResult: Details of the successfully established connection.

        Raises:
            SidekickConnectionError: If all connection attempts fail.
            SidekickConnectionRefusedError: If a user-set URL is provided but connection is refused.
        """
        # --- Strategy 1: Pyodide Environment ---
        if is_pyodide():
            logger.info("Pyodide environment detected. Attempting to initialize Pyodide communication.")
            try:
                cm_pyodide = create_pyodide_communication_manager(self._task_manager)
                await cm_pyodide.connect_async(
                    message_handler=message_handler,
                    status_change_handler=status_change_handler,
                    error_handler=error_handler
                )
                if cm_pyodide.is_connected():
                    logger.info("Successfully established communication via Pyodide bridge.")
                    return ConnectionResult(
                        communication_manager=cm_pyodide,
                        server_name="Pyodide In-Browser Bridge"
                    )
                else: # pragma: no cover
                    logger.error("PyodideCommunicationManager's connect_async completed but is_connected is false.")
                    raise SidekickConnectionError("Pyodide communication setup failed: CM not connected post-init.")
            except Exception as e_pyodide: # pragma: no cover
                logger.exception(f"Critical error during Pyodide communication setup: {e_pyodide}")
                raise SidekickConnectionError(
                    f"Failed to initialize Sidekick in Pyodide environment: {e_pyodide}",
                    original_exception=e_pyodide
                )

        # --- Strategy 2: User-Defined URL ---
        user_custom_url = get_user_set_url()
        if user_custom_url:
            logger.info(f"User-defined URL '{user_custom_url}' found. Attempting direct connection.")
            user_server_config = ServerConfig(
                name="User-defined Server",
                ws_url=user_custom_url,
                ui_url=None,
                requires_session_id=False,
                show_ui_url=False
            )
            attempt_result = await self._attempt_single_ws_connection(
                user_server_config,
                message_handler,
                status_change_handler,
                error_handler
            )

            if attempt_result.success and attempt_result.communication_manager:
                logger.info(f"Successfully connected to user-defined URL: {user_custom_url}")
                return ConnectionResult(
                    communication_manager=attempt_result.communication_manager,
                    server_name=attempt_result.server_name
                )
            else:
                error_message = (
                    f"Failed to connect to user-defined Sidekick URL '{user_custom_url}'. "
                    f"Error: {attempt_result.error or 'Unknown error'}"
                )
                logger.error(error_message)
                raise SidekickConnectionRefusedError(
                    message=error_message,
                    url=user_custom_url,
                    original_exception=attempt_result.error
                )

        # --- Strategy 3: Default Server List ---
        logger.info("No user-defined URL. Attempting connections from default server list.")
        attempt_errors: List[str] = []

        if not DEFAULT_SERVERS:
            logger.error("DEFAULT_SERVERS list is empty. Cannot attempt any default connections.")
            raise SidekickConnectionError("No default Sidekick servers configured.")


        for server_config_entry in DEFAULT_SERVERS:
            attempt_result = await self._attempt_single_ws_connection(
                server_config_entry,
                message_handler,
                status_change_handler,
                error_handler
            )
            if attempt_result.success and attempt_result.communication_manager:
                return ConnectionResult(
                    communication_manager=attempt_result.communication_manager,
                    ui_url_to_show=attempt_result.ui_url_to_show,
                    show_ui_url_hint=attempt_result.show_ui_url_hint,
                    server_name=attempt_result.server_name
                )
            else:
                error_info = f"{server_config_entry.name} ({server_config_entry.ws_url}): {type(attempt_result.error).__name__}"
                if attempt_result.error and hasattr(attempt_result.error, 'url') and attempt_result.error.url: # type: ignore
                    error_info += f" (Target: {attempt_result.error.url})" # type: ignore
                attempt_errors.append(error_info)
                logger.warning(
                    f"Connection attempt to default server '{server_config_entry.name}' failed. "
                    f"Error: {attempt_result.error}"
                )

        error_summary_str = "; ".join(attempt_errors) if attempt_errors else "No servers attempted or all attempts yielded unknown errors."
        final_error_message = (
            "Failed to connect to any configured Sidekick server. Please ensure Sidekick is running "
            "(VS Code extension active, or remote server is operational). "
            f"Connection attempts summary: [{error_summary_str}]"
        )
        logger.error(final_error_message)
        raise SidekickConnectionError(final_error_message)