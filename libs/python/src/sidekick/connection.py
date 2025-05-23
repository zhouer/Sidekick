"""Manages the high-level connection and communication service for Sidekick.

This module provides the `ConnectionService` class, which orchestrates the
communication between the Sidekick Python library and the Sidekick UI,
once a connection has been established by the `ServerConnector`.

The `ConnectionService` is responsible for:
- Managing the Sidekick-specific post-connection lifecycle: This includes
  handling the sequence of `system/announce` messages for peer
  discovery (hero announcing itself, waiting for Sidekick UI to announce itself),
  and managing graceful shutdown.
- Sending an initial `global/clearAll` command to the UI panel upon successful
  activation to ensure a clean state.
- Queuing messages that are sent by components before the service is fully
  active, and then dispatching them once ready.
- Serializing Python dictionary messages to JSON strings for transport and
  deserializing incoming JSON strings back to dictionaries.
- Dispatching incoming UI events (e.g., button clicks, grid interactions) and
  error messages from specific UI components to the correct Python component
  instance handlers.
- Providing user-facing functions (exposed via `sidekick/__init__.py`) to
  control the service, such as explicitly activating the connection
  (`activate_connection`), and shutting down the service (`shutdown`).
"""

import asyncio
import json
import threading
import time
import uuid
from collections import deque
from enum import Enum, auto
from typing import Dict, Any, Callable, Optional, Deque, Union, Coroutine

from . import _version # For __version__ to include in hero announce messages
from . import logger
from .core import (
    get_task_manager,
    TaskManager,
    CommunicationManager,
    CoreConnectionStatus,
    CoreConnectionError,
    CoreConnectionRefusedError,
    CoreConnectionTimeoutError,
    CoreDisconnectedError,
    CoreTaskSubmissionError,
    CoreLoopNotRunningError,
    is_pyodide
)
from .exceptions import (
    SidekickConnectionError,
    SidekickConnectionRefusedError,
    SidekickTimeoutError,
    SidekickDisconnectedError,
    SidekickError
)
from .config import DEFAULT_SERVERS, set_user_url_globally
from .server_connector import ServerConnector, ConnectionResult


# --- Constants ---
_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS = 180.0
_CONNECT_CORE_TRANSPORT_TIMEOUT_SECONDS = 3.0
_MAX_MESSAGE_QUEUE_SIZE = 1000
_ACTIVATION_WAIT_POLL_INTERVAL_CPYTHON = 0.1
_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON = 180.0 # Overall timeout for CPython's blocking activate_connection.


class _ServiceStatus(Enum):
    """Internal states for the ConnectionService lifecycle.

    These states track the detailed progress of connection activation and
    the overall operational status of the service.
    """
    IDLE = auto()
    ACTIVATING_SCHEDULED = auto()
    CORE_CONNECTED = auto()
    WAITING_SIDEKICK_ANNOUNCE = auto()
    ACTIVE = auto()
    FAILED = auto()
    SHUTTING_DOWN = auto()
    SHUTDOWN_COMPLETE = auto()


class ConnectionService:
    """
    Orchestrates Sidekick communication and manages the service lifecycle
    post-connection. This class is intended to be a singleton, accessed via
    `_get_service_instance()` at the module level.
    """

    _instance: Optional['ConnectionService'] = None
    _instance_lock = threading.Lock()

    def __init__(self):
        """
        Initializes the ConnectionService. This constructor should only be
        called internally by `_get_service_instance()` to enforce singleton behavior.
        """
        if ConnectionService._instance is not None: # pragma: no cover
            raise RuntimeError("ConnectionService is a singleton. Use _get_service_instance().")

        self._task_manager: TaskManager = get_task_manager()
        # CommunicationManager is set after successful connection via ServerConnector
        self._communication_manager: Optional[CommunicationManager] = None
        self._server_connector: ServerConnector = ServerConnector(self._task_manager)
        self._connected_server_name: Optional[str] = None # Stores name of the successfully connected server

        self._service_status: _ServiceStatus = _ServiceStatus.IDLE
        self._status_lock = threading.RLock()

        self._async_activate_task: Optional[asyncio.Task] = None
        self._activation_cv = threading.Condition(self._status_lock)

        self._hero_peer_id: str = f"hero-py-{uuid.uuid4().hex}"

        self._core_transport_connected_event: Optional[asyncio.Event] = None
        self._sidekick_ui_online_event: Optional[asyncio.Event] = None
        self._clearall_sent_and_queue_processed_event: Optional[asyncio.Event] = None

        self._message_queue: Deque[Dict[str, Any]] = deque(maxlen=_MAX_MESSAGE_QUEUE_SIZE)
        self._component_message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._user_global_message_handler: Optional[Callable[[Dict[str, Any]], None]] = None
        self._sidekick_peers_info: Dict[str, Dict[str, Any]] = {}

        logger.info(f"ConnectionService initialized (Hero Peer ID: {self._hero_peer_id})")

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Convenience method to get the event loop from the TaskManager."""
        self._task_manager.ensure_loop_running()
        return self._task_manager.get_loop()

    def _create_asyncio_events_if_needed(self) -> None:
        """Creates internal asyncio.Event instances. Must be called from TM's loop."""
        if not self._task_manager.is_loop_running(): # pragma: no cover
            logger.critical("_create_asyncio_events_if_needed called but TM loop not running.")
            self._task_manager.ensure_loop_running()

        if self._core_transport_connected_event is None:
            self._core_transport_connected_event = asyncio.Event()
        if self._sidekick_ui_online_event is None:
            self._sidekick_ui_online_event = asyncio.Event()
        if self._clearall_sent_and_queue_processed_event is None:
            self._clearall_sent_and_queue_processed_event = asyncio.Event()

    def _activation_done_callback(self, fut: asyncio.Task) -> None:
        """Callback executed when the _async_activate_and_run_message_queue task finishes or fails."""
        with self._status_lock:
            try:
                fut.result()
                logger.info(f"Async activation task completed. Service status upon completion: {self._service_status.name}")
            except asyncio.CancelledError:
                logger.info("Async activation task was cancelled (likely during shutdown).")
                if self._service_status not in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                    self._service_status = _ServiceStatus.FAILED
            except (SidekickTimeoutError, SidekickConnectionError, SidekickDisconnectedError) as e_sk_known:
                logger.error(f"Async activation failed with known Sidekick error: {type(e_sk_known).__name__}: {e_sk_known}")
                if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            except Exception as e_unexpected: # pragma: no cover
                logger.exception(f"Async activation task failed with unexpected error: {e_unexpected}")
                if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            finally:
                if not is_pyodide():
                    self._activation_cv.notify_all()

    def _re_raise_activation_failure_if_any(self) -> None:
        """Helper for CPython's blocking activate_connection.
        If the async activation task failed, this re-raises its exception.
        """
        if self._async_activate_task and self._async_activate_task.done():
            try:
                self._async_activate_task.result()
            except asyncio.CancelledError: # pragma: no cover
                raise SidekickConnectionError("Activation was cancelled (likely due to shutdown).") from None
            except (SidekickTimeoutError, SidekickConnectionRefusedError, SidekickDisconnectedError, SidekickConnectionError) as e_known:
                raise e_known
            except Exception as e_unknown: # pragma: no cover
                raise SidekickConnectionError(f"Activation failed due to an unexpected error: {e_unknown}", original_exception=e_unknown) from e_unknown


    def activate_connection_internally(self) -> None: # Renamed from activate_connection to avoid conflict with module-level
        """Ensures the Sidekick service is connected and ready.
        In CPython, this method blocks until activation is complete or fails.
        In Pyodide, it initiates asynchronous activation and returns immediately.
        This is the internal method called by the module-level activate_connection().
        """
        with self._status_lock:
            current_s_status = self._service_status
            logger.debug(f"activate_connection_internally called. Current service status: {current_s_status.name}")

            if current_s_status == _ServiceStatus.ACTIVE:
                logger.debug("Service already active. Activation not needed.")
                return

            is_activation_task_currently_running = self._async_activate_task and not self._async_activate_task.done()

            if is_activation_task_currently_running:
                logger.debug("Activation is already in progress.")
                if not is_pyodide():
                    logger.debug("CPython: activate_connection_internally blocking for ongoing async activation...")
                    start_wait_time = self._get_loop().time()
                    while self._service_status not in [_ServiceStatus.ACTIVE, _ServiceStatus.FAILED, _ServiceStatus.SHUTDOWN_COMPLETE]:
                        if not self._activation_cv.wait(timeout=_ACTIVATION_WAIT_POLL_INTERVAL_CPYTHON):
                            if (self._get_loop().time() - start_wait_time) > _ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON: # pragma: no cover
                                logger.error(f"activate_connection_internally: CPython timed out after {_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON}s waiting for ongoing activation.")
                                self._service_status = _ServiceStatus.FAILED
                                if self._async_activate_task and not self._async_activate_task.done():
                                    self._async_activate_task.cancel()
                                raise SidekickTimeoutError(f"Timeout waiting for Sidekick service activation ({_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON}s).")
                        if self._async_activate_task and self._async_activate_task.done(): break
                    if self._service_status == _ServiceStatus.FAILED:
                        self._re_raise_activation_failure_if_any()
                return

            if current_s_status in [_ServiceStatus.IDLE, _ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.FAILED]:
                logger.info(f"Initiating Sidekick connection service activation (from status: {current_s_status.name})...")
                self._service_status = _ServiceStatus.ACTIVATING_SCHEDULED
                if self._async_activate_task and not self._async_activate_task.done(): # pragma: no cover
                    self._async_activate_task.cancel()
                self._async_activate_task = None
                self._sidekick_ui_online_event = None
                self._clearall_sent_and_queue_processed_event = None
                self._core_transport_connected_event = None # Reset all events
                self._communication_manager = None # Clear old CM if any
                self._connected_server_name = None # Clear old server name

                self._task_manager.ensure_loop_running()
                self._async_activate_task = self._task_manager.submit_task(
                    self._async_activate_and_run_message_queue()
                )
                self._async_activate_task.add_done_callback(self._activation_done_callback)

                if not is_pyodide():
                    logger.debug("CPython: activate_connection_internally blocking for new async activation...")
                    start_wait_time = self._get_loop().time()
                    while self._service_status not in [_ServiceStatus.ACTIVE, _ServiceStatus.FAILED, _ServiceStatus.SHUTDOWN_COMPLETE]:
                        if not self._activation_cv.wait(timeout=_ACTIVATION_WAIT_POLL_INTERVAL_CPYTHON):
                             if (self._get_loop().time() - start_wait_time) > _ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON: # pragma: no cover
                                logger.error(f"activate_connection_internally: CPython timed out after {_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON}s waiting for new activation.")
                                self._service_status = _ServiceStatus.FAILED
                                if self._async_activate_task and not self._async_activate_task.done():
                                    self._async_activate_task.cancel()
                                raise SidekickTimeoutError(f"Timeout waiting for Sidekick service activation ({_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON}s).")
                        if self._async_activate_task and self._async_activate_task.done(): break
                    if self._service_status == _ServiceStatus.FAILED:
                        self._re_raise_activation_failure_if_any()
                return
            logger.warning(f"activate_connection_internally called in unexpected intermediate state {current_s_status.name} without a running activation task.") # pragma: no cover


    async def _async_activate_and_run_message_queue(self) -> None:
        """Core asynchronous activation logic: connect, announce, clear, process queue."""
        try:
            with self._status_lock:
                if self._service_status not in [
                    _ServiceStatus.ACTIVATING_SCHEDULED, _ServiceStatus.FAILED,
                    _ServiceStatus.IDLE, _ServiceStatus.SHUTDOWN_COMPLETE
                ]: # pragma: no cover
                    logger.warning(f"_async_activate_and_run_message_queue called in unexpected state: {self._service_status.name}. Aborting.")
                    if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
                    return

                self._create_asyncio_events_if_needed()
                self._core_transport_connected_event.clear() # type: ignore[union-attr]
                self._sidekick_ui_online_event.clear() # type: ignore[union-attr]
                self._clearall_sent_and_queue_processed_event.clear() # type: ignore[union-attr]
                self._sidekick_peers_info.clear()

            logger.debug("_async_activate: Attempting connection via ServerConnector.")
            connection_outcome: ConnectionResult
            try:
                connection_outcome = await self._server_connector.connect_async()
                # ServerConnector.connect_async() ensures its returned CM is connected or raises
                self._communication_manager = connection_outcome.communication_manager
                self._connected_server_name = connection_outcome.server_name

                # Register core handlers with the successfully obtained CM
                self._communication_manager.register_message_handler(self._handle_core_message)
                self._communication_manager.register_status_change_handler(self._handle_core_status_change)
                self._communication_manager.register_error_handler(self._handle_core_error)

                logger.info(f"Successfully connected to Sidekick server: {self._connected_server_name or 'Unknown'}")

            except SidekickConnectionError as e_conn_strat:
                logger.error(f"ServerConnector failed to establish any connection: {e_conn_strat}")
                with self._status_lock: self._service_status = _ServiceStatus.FAILED
                raise # Re-raise to be caught by the outer try-except of this function

            # Post-connection setup. CM is now self._communication_manager
            with self._status_lock:
                if self._communication_manager and self._communication_manager.is_connected():
                     self._service_status = _ServiceStatus.CORE_CONNECTED
                     if self._core_transport_connected_event: self._core_transport_connected_event.set()
                else: # Should not happen if ServerConnector worked as expected
                    logger.critical("CRITICAL: ServerConnector returned, but CM is not valid or not connected.") # pragma: no cover
                    self._service_status = _ServiceStatus.FAILED
                    raise SidekickConnectionError("ServerConnector logic error: CM invalid post-connection.")

            if connection_outcome.show_ui_url_hint and connection_outcome.ui_url_to_show:
                # This print will appear in the user's terminal.
                # print(f"Successfully connected to: {self._connected_server_name or 'Remote Server'}")
                print(f"Sidekick UI is available at: {connection_outcome.ui_url_to_show}")
                print("For the best experience, install the 'Sidekick - Your Visual Coding Buddy' VS Code extension.")

            # --- Hero Announce ---
            hero_announce = {
                "id": 0, "component": "system", "type": "announce",
                "payload": {
                    "peerId": self._hero_peer_id, "role": "hero", "status": "online",
                    "version": _version.__version__, "timestamp": int(self._get_loop().time() * 1000)
                }
            }
            logger.info(f"Sending Hero 'online' announce via {self._connected_server_name}.")
            await self._communication_manager.send_message_async(json.dumps(hero_announce))

            # --- Wait for Sidekick UI Announce ---
            with self._status_lock: self._service_status = _ServiceStatus.WAITING_SIDEKICK_ANNOUNCE
            if connection_outcome.show_ui_url_hint:
                print(f"Waiting up to {_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS}s for Sidekick UI...")
            logger.info(f"Waiting up to {_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS}s for Sidekick UI 'online' announce...")
            try:
                await asyncio.wait_for(self._sidekick_ui_online_event.wait(), timeout=_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS) # type: ignore[union-attr]
                if connection_outcome.show_ui_url_hint:
                    print("Sidekick UI is connected.")
                logger.info("Sidekick UI 'online' announce received.")
            except asyncio.TimeoutError:
                if connection_outcome.show_ui_url_hint:
                    print("Sidekick UI is not connected within the timeout period.")
                err_msg = f"Timeout waiting for Sidekick UI 'online' announce after {_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS}s."
                logger.error(err_msg)
                # If this is a remote server, the UI might take time to open, so this timeout might be more common.
                # For local server, this is more indicative of a problem.
                if self._connected_server_name == DEFAULT_SERVERS[0].name if DEFAULT_SERVERS else False:
                    logger.warning("This timeout for local server might indicate an issue with the VS Code extension panel.")
                raise SidekickTimeoutError(err_msg, timeout_seconds=_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS) from None

            # --- Send global/clearAll ---
            clearall_msg = {"id": 0, "component": "global", "type": "clearAll"}
            logger.info(f"Sending 'global/clearAll'.")
            await self._communication_manager.send_message_async(json.dumps(clearall_msg))

            # --- Process Message Queue and Set Active ---
            logger.debug("Processing message queue (if any) before setting fully active...")
            temp_queue_for_processing: Deque[Dict[str, Any]] = deque()
            with self._status_lock:
                temp_queue_for_processing.extend(self._message_queue)
                self._message_queue.clear()

            if temp_queue_for_processing:
                logger.info(f"Processing {len(temp_queue_for_processing)} queued messages.")
                for i, msg_dict in enumerate(list(temp_queue_for_processing)):
                    logger.debug(f"Sending queued message ({i+1}/{len(temp_queue_for_processing)}): type='{msg_dict.get('type', 'N/A')}'")
                    try:
                        await self._communication_manager.send_message_async(json.dumps(msg_dict))
                    except CoreDisconnectedError as e_send_q: # pragma: no cover
                        logger.error(f"Failed to send queued message due to disconnection: {e_send_q}. Re-queuing remaining and failing activation.")
                        with self._status_lock:
                            self._message_queue.appendleft(msg_dict)
                            remaining_to_requeue = list(temp_queue_for_processing)[i+1:]
                            for item_to_requeue in reversed(remaining_to_requeue):
                                self._message_queue.appendleft(item_to_requeue)
                        raise
            with self._status_lock: self._service_status = _ServiceStatus.ACTIVE
            self._clearall_sent_and_queue_processed_event.set() # type: ignore[union-attr]
            logger.info("ConnectionService is now ACTIVE. Activation sequence complete.")

        except (SidekickConnectionError, SidekickTimeoutError, SidekickDisconnectedError) as e_sk:
            logger.error(f"Sidekick activation error: {type(e_sk).__name__}: {e_sk}")
            with self._status_lock:
                if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            raise
        except Exception as e_unexpected: # pragma: no cover
            logger.exception(f"Unexpected fatal error during async activation: {e_unexpected}")
            with self._status_lock:
                 if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            # Attempt to close CM if it was set up
            if self._communication_manager and self._communication_manager.is_connected():
                try: await self._communication_manager.close_async()
                except Exception: pass
            raise SidekickConnectionError(f"Unexpected activation error: {e_unexpected}", original_exception=e_unexpected) from e_unexpected


    def _send_hero_offline_if_needed(self) -> Optional[asyncio.Task]:
        """Sends a hero 'offline' announce message if appropriate."""
        task: Optional[asyncio.Task] = None
        comm_manager_ref: Optional[CommunicationManager] = None
        can_send = False

        with self._status_lock:
            comm_manager_ref = self._communication_manager
            if comm_manager_ref and comm_manager_ref.is_connected() and \
                    self._service_status not in [_ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.FAILED, _ServiceStatus.IDLE]:
                can_send = True
        if can_send and comm_manager_ref:
            hero_offline_announce = {
                "id": 0, "component": "system", "type": "announce",
                "payload": {
                    "peerId": self._hero_peer_id, "role": "hero", "status": "offline",
                    "version": _version.__version__, "timestamp": int(time.time() * 1000)
                }
            }
            logger.info(f"Sending Hero 'offline' announce during shutdown.")
            try:
                task = self._task_manager.submit_task(
                    comm_manager_ref.send_message_async(json.dumps(hero_offline_announce))
                )
            except (CoreTaskSubmissionError, CoreLoopNotRunningError, AttributeError) as e:  # pragma: no cover
                logger.warning(f"Could not submit hero 'offline' announce task during shutdown: {e}")
        else:
            logger.debug("Skipping send_hero_offline: CM not connected or service state inappropriate.")
        return task


    def _handle_core_message(self, message_str: str) -> None:
        """Callback for CommunicationManager: handles raw messages from transport."""
        logger.debug(f"ConnectionService received core message: {message_str[:100]}{'...' if len(message_str) > 100 else ''}")
        try:
            message_dict = json.loads(message_str)
        except json.JSONDecodeError: # pragma: no cover
            logger.error(f"Failed to parse JSON from core message: {message_str[:200]}")
            return

        if self._user_global_message_handler:
            try:
                self._user_global_message_handler(message_dict)
            except Exception as e_global: # pragma: no cover
                logger.exception(f"Error in user's global message handler: {e_global}")

        msg_component = message_dict.get("component")
        msg_type = message_dict.get("type")
        payload = message_dict.get("payload")

        if msg_component == "system" and msg_type == "announce" and payload:
            peer_id = payload.get("peerId")
            role = payload.get("role")
            status = payload.get("status")
            version = payload.get("version")
            if role == "sidekick":
                if status == "online":
                    logger.info(f"Received 'sidekick online' announce from peer: {peer_id} (version: {version})")
                    with self._status_lock: self._sidekick_peers_info[peer_id] = payload
                    if self._sidekick_ui_online_event and not self._sidekick_ui_online_event.is_set():
                        self._sidekick_ui_online_event.set()
                elif status == "offline": # pragma: no cover
                    logger.info(f"Received 'sidekick offline' announce from peer: {peer_id}")
                    with self._status_lock: removed_peer = self._sidekick_peers_info.pop(peer_id, None)
                    if removed_peer and not self._sidekick_peers_info: # If last UI peer goes offline
                        logger.info("All known Sidekick UIs are now offline.")
                        if self._sidekick_ui_online_event:
                            self._sidekick_ui_online_event.clear()
                        print("Sidekick UI is disconnected, shutting down.")
                        self.shutdown_service()
        elif msg_type in ["event", "error"]:
            instance_id = message_dict.get("src")
            if instance_id:
                handler = self._component_message_handlers.get(instance_id)
                if handler:
                    try:
                        logger.debug(f"Dispatching '{msg_type}' for component '{instance_id}' to its handler.")
                        handler(message_dict)
                    except Exception as e_comp: # pragma: no cover
                        logger.exception(f"Error in component handler for '{instance_id}': {e_comp}")
                else: # pragma: no cover
                    logger.debug(f"No component handler for instance_id '{instance_id}' for '{msg_type}' message.")
            else: # pragma: no cover
                logger.warning(f"Received '{msg_type}' message without 'src' (instance_id): {message_dict}")
        else: # pragma: no cover
            logger.debug(f"Received unhandled message structure from core: comp='{msg_component}', type='{msg_type}'")


    def _handle_core_status_change(self, core_status: CoreConnectionStatus) -> None:
        """Callback for CommunicationManager: handles core transport status changes."""
        logger.info(f"ConnectionService processing core CM status change: {core_status.name}")
        status_changed_by_this_call = False
        original_service_status_for_log = self._service_status

        with self._status_lock:
            current_s_status = self._service_status
            if core_status == CoreConnectionStatus.CONNECTED:
                # This might be redundant if ServerConnector already ensured connection,
                # but it's a good confirmation. If _service_status was, e.g., ACTIVATING_SCHEDULED
                # and CM directly reports CONNECTED, update to CORE_CONNECTED.
                if current_s_status == _ServiceStatus.ACTIVATING_SCHEDULED or \
                   (self._communication_manager and self._communication_manager.is_connected() and current_s_status != _ServiceStatus.CORE_CONNECTED): # If CM is good but we weren't in CORE_CONNECTED
                    if self._service_status != _ServiceStatus.CORE_CONNECTED:
                        self._service_status = _ServiceStatus.CORE_CONNECTED
                        status_changed_by_this_call = True
                        logger.info("Service status advanced to CORE_CONNECTED (transport layer active).")
                    if self._core_transport_connected_event:
                        self._core_transport_connected_event.set()
            elif core_status in [CoreConnectionStatus.DISCONNECTED, CoreConnectionStatus.ERROR]:
                logger.warning(f"Core communication channel reported {core_status.name}.")
                if self._core_transport_connected_event:
                    self._core_transport_connected_event.clear()
                if current_s_status not in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.IDLE]:
                    if self._service_status != _ServiceStatus.FAILED:
                        self._service_status = _ServiceStatus.FAILED
                        status_changed_by_this_call = True
                        logger.error(f"Service status changed to FAILED due to core channel {core_status.name}.")
                    if self._sidekick_ui_online_event: self._sidekick_ui_online_event.clear()
                    if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()
                    if not (self._async_activate_task and not self._async_activate_task.done()):
                        if not is_pyodide() and status_changed_by_this_call : self._activation_cv.notify_all()
            if status_changed_by_this_call:
                logger.debug(f"Service status transition: {original_service_status_for_log.name} -> {self._service_status.name} (due to core status: {core_status.name})")


    def _handle_core_error(self, exc: Exception) -> None: # pragma: no cover
        """Callback for CommunicationManager: handles unexpected errors from CM's operations."""
        logger.error(f"ConnectionService received critical core CM error: {type(exc).__name__}: {exc}")
        status_changed_by_this_call = False
        with self._status_lock:
            if self._service_status not in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.IDLE]:
                if self._service_status != _ServiceStatus.FAILED:
                    self._service_status = _ServiceStatus.FAILED
                    status_changed_by_this_call = True
                    logger.error(f"Service status changed to FAILED due to core CM error: {exc}")
                if self._core_transport_connected_event: self._core_transport_connected_event.clear()
                if self._sidekick_ui_online_event: self._sidekick_ui_online_event.clear()
                if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()
                if not is_pyodide() and status_changed_by_this_call: self._activation_cv.notify_all()


    def send_message_internally(self, message_dict: Dict[str, Any]) -> None: # Renamed
        """Sends a Sidekick protocol message. Queues if service not fully active."""
        with self._status_lock:
            s_status = self._service_status
            needs_activation_kickoff = s_status in [_ServiceStatus.IDLE, _ServiceStatus.SHUTDOWN_COMPLETE] or \
                                       (s_status == _ServiceStatus.FAILED and not is_pyodide())
        if needs_activation_kickoff:
            try:
                logger.debug(f"send_message_internally: Kicking off activation from status {s_status.name}")
                self.activate_connection_internally()
            except SidekickConnectionError as e:
                logger.error(f"Implicit activation for send_message_internally failed: {e}. Message not sent.")
                raise
        with self._status_lock:
            is_ready_for_direct_send = self._clearall_sent_and_queue_processed_event and \
                                       self._clearall_sent_and_queue_processed_event.is_set() and \
                                       self._service_status == _ServiceStatus.ACTIVE
            if not is_ready_for_direct_send:
                if self._service_status in [_ServiceStatus.FAILED, _ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                    logger.error(f"Cannot send message, service status is {self._service_status.name}. Message dropped: {message_dict.get('type')}")
                    raise SidekickDisconnectedError(f"Service not active (status: {self._service_status.name}). Cannot send.")
                if len(self._message_queue) >= self._message_queue.maxlen: # type: ignore[arg-type] # pragma: no cover
                    dropped_msg = self._message_queue.popleft()
                    logger.error(f"Message queue full ({self._message_queue.maxlen}). Dropping oldest: type='{dropped_msg.get('type')}'")
                self._message_queue.append(message_dict)
                logger.debug(f"Message type='{message_dict.get('type', 'N/A')}' queued (qsize: {len(self._message_queue)}). Waiting for full activation.")
                return
        comm_manager = self._communication_manager
        if not comm_manager or not comm_manager.is_connected(): # pragma: no cover
            logger.critical("send_message_internally: CRITICAL STATE - Service ACTIVE but CM unavailable/disconnected.")
            with self._status_lock:
                self._message_queue.append(message_dict)
                if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()
                self._service_status = _ServiceStatus.FAILED
            raise SidekickDisconnectedError("Internal state inconsistency: Service active but CM not ready.")
        logger.debug(f"Sending message directly: type='{message_dict.get('type', 'N/A')}' target='{message_dict.get('target', 'N/A')}'")
        try:
            json_str = json.dumps(message_dict)
            self._task_manager.submit_task(comm_manager.send_message_async(json_str))
        except json.JSONDecodeError as e_json: # pragma: no cover
            logger.error(f"Failed to serialize message to JSON: {e_json}. Message: {message_dict}")
            raise TypeError(f"Message content not JSON serializable: {e_json}") from e_json
        except (CoreTaskSubmissionError, AttributeError) as e_submit: # pragma: no cover
            logger.error(f"Failed to submit send_message_async task: {e_submit}. Re-queuing message.")
            with self._status_lock:
                self._message_queue.append(message_dict)
                if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()
                if self._service_status == _ServiceStatus.ACTIVE: self._service_status = _ServiceStatus.CORE_CONNECTED
            raise SidekickDisconnectedError(f"Failed to submit message send task: {e_submit}", original_exception=e_submit)

    def register_component_message_handler(self, instance_id: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a message handler for a specific component instance ID."""
        if not isinstance(instance_id, str) or not instance_id:
            raise ValueError("instance_id must be a non-empty string.")
        if not callable(handler):
            raise TypeError("handler must be a callable function.")
        if instance_id in self._component_message_handlers: # pragma: no cover
            logger.warning(f"Handler already registered for instance_id: {instance_id}. Overwriting.")
        self._component_message_handlers[instance_id] = handler
        logger.debug(f"Registered component message handler for instance_id: {instance_id}")

    def unregister_component_message_handler(self, instance_id: str) -> None:
        """Unregisters a message handler for a specific component instance ID."""
        if self._component_message_handlers.pop(instance_id, None):
            logger.debug(f"Unregistered component message handler for instance_id: {instance_id}")

    def clear_all_ui_components(self) -> None:
        """Sends a command to remove all components from the Sidekick UI."""
        logger.info("Requesting ConnectionService to clear all UI components.")
        self.send_message_internally({"id": 0, "component": "global", "type": "clearAll"})


    def shutdown_service(self) -> None:
        """Initiates a graceful shutdown of the ConnectionService."""
        # offline_task_handle: Optional[asyncio.Task] = None # Not strictly needed to store
        # comm_close_task_handle: Optional[asyncio.Task] = None # Not strictly needed to store

        with self._status_lock:
            if self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                logger.debug(f"Shutdown already in progress or complete (status: {self._service_status.name}).")
                return
            logger.info(f"ConnectionService shutdown initiated. Current status: {self._service_status.name}")
            self._service_status = _ServiceStatus.SHUTTING_DOWN
            if self._async_activate_task and not self._async_activate_task.done():
                logger.debug("Cancelling active _async_activate_task during shutdown.")
                self._async_activate_task.cancel()
            if self._message_queue: # pragma: no cover
                logger.info(f"Clearing {len(self._message_queue)} messages from queue due to shutdown.")
                self._message_queue.clear()
            if self._core_transport_connected_event: self._core_transport_connected_event.clear()
            if self._sidekick_ui_online_event: self._sidekick_ui_online_event.clear()
            if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()

            _ = self._send_hero_offline_if_needed() # Fire-and-forget

            comm_manager_to_close = self._communication_manager
            if comm_manager_to_close:
                logger.debug("Scheduling CommunicationManager.close_async().")
                try:
                    _ = self._task_manager.submit_task(comm_manager_to_close.close_async()) # Fire-and-forget
                except (CoreTaskSubmissionError, CoreLoopNotRunningError) as e: # pragma: no cover
                    logger.warning(f"Could not submit CM close task during shutdown: {e}")
        logger.debug("Signaling TaskManager to shutdown (from ConnectionService.shutdown_service).")
        self._task_manager.signal_shutdown()
        with self._status_lock:
            self._component_message_handlers.clear()
            self._user_global_message_handler = None
            self._sidekick_peers_info.clear()
            self._communication_manager = None
            self._connected_server_name = None
            self._service_status = _ServiceStatus.SHUTDOWN_COMPLETE
            logger.info("ConnectionService shutdown sequence finalized.")
            if not is_pyodide():
                self._activation_cv.notify_all()


    def run_service_forever(self) -> None:
        """Blocks and keeps the service running until shutdown. (CPython specific use)."""
        if is_pyodide(): # pragma: no cover
            logger.error("run_service_forever() is synchronous and not intended for Pyodide. Use run_service_forever_async().")
            try: self.activate_connection_internally()
            except SidekickError: pass
            return
        try:
            self.activate_connection_internally()
            with self._status_lock: service_is_active = (self._service_status == _ServiceStatus.ACTIVE)
            if service_is_active:
                logger.info("ConnectionService entering run_forever wait state (CPython).")
                self._task_manager.wait_for_shutdown()
            else: # pragma: no cover
                logger.error(f"Service not active after activation attempt (status: {self._service_status.name}). Cannot run forever.")
        except KeyboardInterrupt: # pragma: no cover
            logger.info("KeyboardInterrupt in run_service_forever. Initiating shutdown.")
        except SidekickConnectionError as e: # pragma: no cover
            logger.error(f"Connection error in run_service_forever: {e}. Shutting down.")
        except Exception as e: # pragma: no cover
            logger.exception(f"Unexpected error in run_service_forever: {e}. Shutting down.")
        finally:
            with self._status_lock:
                is_already_terminal = self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]
            if not is_already_terminal:
                logger.info("run_service_forever exiting. Initiating shutdown if not already in progress.")
                self.shutdown_service()
            logger.info("ConnectionService run_forever (CPython) finished.")


    async def run_service_forever_async(self) -> None:
        """Keeps the service running asynchronously until shutdown. (Pyodide/Async use)."""
        try:
            self.activate_connection_internally()
            current_activation_task_ref: Optional[asyncio.Task] = None
            with self._status_lock:
                current_activation_task_ref = self._async_activate_task
            if current_activation_task_ref and not current_activation_task_ref.done():
                logger.debug("run_service_forever_async: Awaiting completion of current activation task.")
                try:
                    await asyncio.wait_for(current_activation_task_ref, timeout=_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON)
                except asyncio.TimeoutError: # pragma: no cover
                    logger.error(f"run_service_forever_async: Timeout waiting for activation task to complete.")
                    with self._status_lock: self._service_status = _ServiceStatus.FAILED
                except asyncio.CancelledError: # pragma: no cover
                    logger.info("run_service_forever_async: Activation task was cancelled during wait.")
            with self._status_lock: service_is_active = (self._service_status == _ServiceStatus.ACTIVE)
            if service_is_active:
                logger.info("ConnectionService entering run_forever_async wait state.")
                await self._task_manager.wait_for_shutdown_async()
            else: # pragma: no cover
                logger.warning(f"Service not active after async activation (status: {self._service_status.name}). Cannot run_forever_async effectively.")
        except KeyboardInterrupt: # pragma: no cover
            logger.info("KeyboardInterrupt (async context). Initiating shutdown.")
        except SidekickConnectionError as e: # pragma: no cover
            logger.error(f"Connection error in run_service_forever_async: {e}. Shutting down.")
        except Exception as e: # pragma: no cover
            logger.exception(f"Unexpected error in run_service_forever_async: {e}. Shutting down.")
        finally:
            with self._status_lock:
                is_already_terminal = self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]
            if not is_already_terminal:
                logger.info("run_service_forever_async exiting. Initiating shutdown if not already in progress.")
                self.shutdown_service()
            logger.info("ConnectionService run_service_forever_async finished.")

    def register_user_global_message_handler(self, handler: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        """Registers a user-defined global handler for all incoming messages."""
        if handler is not None and not callable(handler): # pragma: no cover
            raise TypeError("Global message handler must be a callable function or None.")
        self._user_global_message_handler = handler
        logger.info(f"User global message handler {'set' if handler else 'cleared'}.")

# --- Module-level public API functions using the ConnectionService Singleton ---

_connection_service_singleton_init_lock = threading.Lock()
_connection_service_singleton_instance: Optional[ConnectionService] = None

def _get_service_instance() -> ConnectionService:
    """Internal helper to get or create the singleton ConnectionService instance."""
    global _connection_service_singleton_instance
    if _connection_service_singleton_instance is None:
        with _connection_service_singleton_init_lock:
            if _connection_service_singleton_instance is None:
                _connection_service_singleton_instance = ConnectionService()
    return _connection_service_singleton_instance


def set_url(url: Optional[str]) -> None:
    """Sets the target WebSocket URL for the Sidekick connection.
    Must be called before any components are created or connection is activated.
    If None, default server list will be used.
    """
    set_user_url_globally(url) # Calls the function in config.py
    _service_instance = _get_service_instance() # Get instance to log, though not strictly needed for just setting config
    if url:
        logger.info(f"Sidekick target URL explicitly set to: {url} via module function. Default server list will be bypassed on next activation.")
    else:
        logger.info("Sidekick target URL cleared by user via module function. Default server list will be used on next activation.")


def activate_connection() -> None:
    """Ensures the Sidekick service is connected and ready.
    In CPython, this blocks until the service is active or activation fails.
    In Pyodide, this initiates asynchronous activation and returns immediately.
    """
    _get_service_instance().activate_connection_internally()

def send_message(message_dict: Dict[str, Any]) -> None:
    """Sends a message dictionary (Sidekick protocol) to the Sidekick UI.
    Will queue messages if the service is not yet fully active.
    """
    _get_service_instance().send_message_internally(message_dict)

def register_message_handler(instance_id: str, handler: Callable[[Dict[str, Any]], None]) -> None:
    """Registers a message handler for a specific component instance ID.
    Used by `Component` subclasses to receive events or errors from the UI.
    """
    _get_service_instance().register_component_message_handler(instance_id, handler)

def unregister_message_handler(instance_id: str) -> None:
    """Unregisters a message handler for a specific component instance ID."""
    _get_service_instance().unregister_component_message_handler(instance_id)

def clear_all() -> None:
    """Sends a command to remove all components from the Sidekick UI."""
    _get_service_instance().clear_all_ui_components()

def shutdown() -> None:
    """Initiates a clean shutdown of the Sidekick connection service."""
    _get_service_instance().shutdown_service()

def run_forever() -> None:
    """Keeps the script running to handle UI events. (Primarily for CPython).
    Blocks the main thread until `shutdown()` is called or an error occurs.
    """
    _get_service_instance().run_service_forever()

async def run_forever_async() -> None:
    """Keeps the script running asynchronously to handle UI events.
    (Primarily for Pyodide or asyncio-based CPython applications).
    Awaits until `shutdown()` is called or an error occurs.
    """
    await _get_service_instance().run_service_forever_async()

def submit_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    """Submits a user-defined coroutine to Sidekick's managed event loop.
    Useful for running custom asyncio code alongside Sidekick components.
    """
    return _get_service_instance()._task_manager.submit_task(coro)

def register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    """Registers a global handler for *all* incoming messages from the UI.
    Mainly for debugging or advanced use.
    """
    _get_service_instance().register_user_global_message_handler(handler)