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
        success (bool): True if the connection attempt was successful.
        communication_manager (Optional[CommunicationManager]): The active manager if success.
        final_ws_url (Optional[str]): The actual WebSocket URL used for the attempt.
        ui_url_to_show (Optional[str]): The UI URL to show the user, if applicable.
        show_ui_url_hint (bool): Flag indicating if a hint to install the VS Code
            extension should be shown.
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
        communication_manager (CommunicationManager): The active and connected manager.
        ui_url_to_show (Optional[str]): The UI URL to display to the user.
        show_ui_url_hint (bool): True if a hint about the VS Code extension should be shown.
        server_name (Optional[str]): The name of the server for the successful connection.
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
        """Appends a session_id as a query parameter to a WebSocket URL."""
        parsed_url = urlparse(base_url)
        query_params = parse_qs(parsed_url.query)
        query_params['session'] = [session_id]
        new_query_string = urlencode(query_params, doseq=True)
        return urlunparse(parsed_url._replace(query=new_query_string))

    def _build_ui_url_with_session_path(self, base_ui_url: str, session_id: str) -> str:
        """Appends a session_id as a path segment to a UI URL."""
        if base_ui_url.endswith('/'):
            return f"{base_ui_url}session/{session_id}"
        return f"{base_ui_url}/session/{session_id}"

    async def _attempt_single_ws_connection(
        self,
        server_config: ServerConfig,
    ) -> ConnectionAttemptResult:
        """Attempts to connect to a single WebSocket server configuration.

        This method handles session ID generation and the actual connection attempt.
        Crucially, it does not attach the final service-level handlers. It only
        validates if a connection can be made.

        Args:
            server_config (ServerConfig): The configuration for the server to attempt.

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
            logger.info(f"Using session ID '{session_id_generated}' for server '{server_config.name}'.")
        elif server_config.ui_url and server_config.show_ui_url:
            ui_url_to_show = server_config.ui_url

        logger.info(f"Attempting WebSocket connection to server '{server_config.name}' at: {final_ws_url}")
        cm = create_websocket_communication_manager(final_ws_url, self._task_manager)

        try:
            # Connect without handlers. We only care about success/failure here.
            await cm.connect_async()

            if cm.is_connected():
                logger.info(f"Successfully connected to server '{server_config.name}' at {final_ws_url}.")
                if server_config.name == self._local_server_name:
                    await asyncio.sleep(0.1) # Brief pause for VS Code WebView stabilization
                    if not cm.is_connected(): # pragma: no cover
                        raise CoreConnectionError("Local server disconnected immediately after connection.")

                return ConnectionAttemptResult(
                    success=True, communication_manager=cm, final_ws_url=final_ws_url,
                    ui_url_to_show=ui_url_to_show if server_config.show_ui_url else None,
                    show_ui_url_hint=server_config.show_ui_url, server_name=server_config.name
                )
            else: # pragma: no cover
                raise CoreConnectionError(f"CM for '{server_config.name}' not connected post-connect.")

        except (CoreConnectionRefusedError, CoreConnectionTimeoutError, CoreConnectionError) as e:
            logger.warning(f"Connection to server '{server_config.name}' ({final_ws_url}) failed: {type(e).__name__}.")
            return ConnectionAttemptResult(success=False, error=e, server_name=server_config.name)
        except Exception as e: # pragma: no cover
            logger.exception(f"Unexpected error during connection attempt to server '{server_config.name}': {e}")
            return ConnectionAttemptResult(success=False, error=e, server_name=server_config.name)

    async def connect_async(
        self,
        message_handler: Optional[MessageHandlerType],
        status_change_handler: Optional[StatusChangeHandlerType],
        error_handler: Optional[ErrorHandlerType]
    ) -> ConnectionResult:
        """Attempts to establish a Sidekick connection using various strategies.

        It iterates through connection options, and upon finding a successful one,
        it attaches the provided handlers to the chosen `CommunicationManager` and
        starts its listener task.

        Args:
            message_handler (Optional[MessageHandlerType]): The final callback for incoming messages.
            status_change_handler (Optional[StatusChangeHandlerType]): The final callback for status changes.
            error_handler (Optional[ErrorHandlerType]): The final callback for communication errors.

        Returns:
            ConnectionResult: Details of the successfully established connection.

        Raises:
            SidekickConnectionError: If all connection attempts fail.
        """
        # --- Strategy 1: Pyodide Environment ---
        if is_pyodide():
            logger.info("Pyodide environment detected. Initializing Pyodide communication.")
            try:
                cm_pyodide = create_pyodide_communication_manager(self._task_manager)
                await cm_pyodide.connect_async(message_handler, status_change_handler, error_handler)
                if cm_pyodide.is_connected():
                    logger.info("Successfully established communication via Pyodide bridge.")
                    return ConnectionResult(communication_manager=cm_pyodide, server_name="Pyodide In-Browser Bridge")
                else: # pragma: no cover
                    raise SidekickConnectionError("Pyodide communication setup failed: CM not connected post-init.")
            except Exception as e_pyodide: # pragma: no cover
                raise SidekickConnectionError(f"Failed to initialize Sidekick in Pyodide environment: {e_pyodide}", original_exception=e_pyodide)

        # --- Strategy 2: User-Defined URL ---
        if user_custom_url := get_user_set_url():
            logger.info(f"User-defined URL '{user_custom_url}' found. Attempting direct connection.")
            user_server_config = ServerConfig(name="User-defined Server", ws_url=user_custom_url)
            attempt_result = await self._attempt_single_ws_connection(user_server_config)

            if attempt_result.success and (successful_cm := attempt_result.communication_manager):
                logger.info(f"Successfully connected to user-defined URL: {user_custom_url}")
                # Now attach the final handlers to the chosen CommunicationManager.
                await successful_cm.connect_async(message_handler, status_change_handler, error_handler)
                return ConnectionResult(communication_manager=successful_cm, server_name=attempt_result.server_name)
            else:
                error_message = f"Failed to connect to user-defined Sidekick URL '{user_custom_url}'. Error: {attempt_result.error or 'Unknown'}"
                raise SidekickConnectionRefusedError(message=error_message, url=user_custom_url, original_exception=attempt_result.error)

        # --- Strategy 3: Default Server List ---
        logger.info("No user-defined URL. Attempting connections from default server list.")
        attempt_errors: List[str] = []

        if not DEFAULT_SERVERS:
            raise SidekickConnectionError("No default Sidekick servers configured.")

        for server_config_entry in DEFAULT_SERVERS:
            attempt_result = await self._attempt_single_ws_connection(server_config_entry)
            if attempt_result.success and (successful_cm := attempt_result.communication_manager):
                # Attach final handlers to the successful CM instance. This ensures
                # that listener tasks and callbacks are only set up for the one
                # connection that we are actually going to use.
                await successful_cm.connect_async(message_handler, status_change_handler, error_handler)
                return ConnectionResult(
                    communication_manager=successful_cm,
                    ui_url_to_show=attempt_result.ui_url_to_show,
                    show_ui_url_hint=attempt_result.show_ui_url_hint,
                    server_name=attempt_result.server_name
                )
            else:
                error_info = f"{server_config_entry.name}: {type(attempt_result.error).__name__}"
                attempt_errors.append(error_info)

        final_error_message = (
            "Failed to connect to any configured Sidekick server. Please ensure Sidekick is running. "
            f"Connection attempts summary: [{'; '.join(attempt_errors)}]"
        )
        logger.error(final_error_message)
        raise SidekickConnectionError(final_error_message)
