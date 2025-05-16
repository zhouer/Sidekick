"""Manages the high-level connection and communication service for Sidekick.

This module provides the `ConnectionService` class, which orchestrates the
communication between the Sidekick Python library and the Sidekick UI.
It utilizes core components (`TaskManager`, `CommunicationManager`) from
`sidekick.core` to handle low-level asynchronous operations and transport,
while exposing a mostly synchronous API to the rest of the Sidekick library
(e.g., individual Component classes).

The `ConnectionService` is responsible for:
- Managing the Sidekick-specific connection lifecycle: This includes initiating
  the connection, handling the sequence of `system/announce` messages for peer
  discovery (hero announcing itself, waiting for Sidekick UI to announce itself),
  and managing graceful shutdown.
- Sending an initial `global/clearAll` command to the UI panel upon successful
  activation to ensure a clean state.
- Queuing messages that are sent by components before the connection sequence
  is fully completed, and then dispatching them once ready.
- Serializing Python dictionary messages to JSON strings for transport and
  deserializing incoming JSON strings back to dictionaries.
- Dispatching incoming UI events (e.g., button clicks, grid interactions) and
  error messages from specific UI components to the correct Python component
  instance handlers.
- Providing user-facing functions (exposed via `sidekick/__init__.py`) to
  control the service, such as setting the target URL (`set_url`), explicitly
  activating the connection (`activate_connection`), and shutting down the
  service (`shutdown`).
- Supporting different operational modes for CPython (typically blocking on
  activation and using `run_forever`) and Pyodide (non-blocking activation
  and using `run_forever_async`).
"""

import asyncio
import json
import logging
import threading
import time
import uuid
from collections import deque # For _message_queue, a thread-safe double-ended queue
from enum import Enum, auto
from typing import Dict, Any, Callable, Optional, Deque, Union, Coroutine

from . import _version # For __version__ to include in hero announce messages
from . import logger
from .core import (
    get_task_manager,
    get_communication_manager,
    TaskManager,
    CommunicationManager,
    CoreConnectionStatus,
    CoreConnectionError,
    CoreConnectionRefusedError,
    CoreConnectionTimeoutError, # Core transport timeout
    CoreDisconnectedError,
    CoreTaskSubmissionError,
    CoreLoopNotRunningError,
    is_pyodide # Utility to check the execution environment
)
from .exceptions import (
    SidekickConnectionError,        # Base application-level connection error
    SidekickConnectionRefusedError, # Application-level connection refused
    SidekickTimeoutError,           # Application-level timeout (e.g., waiting for UI)
    SidekickDisconnectedError,      # Application-level disconnection
    SidekickError                   # General base for Sidekick application errors
)


# --- Constants ---
_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS = 5.0  # Time to wait for Sidekick UI "online" announce.
_CONNECT_CORE_TRANSPORT_TIMEOUT_SECONDS = 10.0 # Time to wait for core transport (e.g. WebSocket) to confirm connection.
_DEFAULT_WEBSOCKET_URL = "ws://localhost:5163" # Default URL for the Sidekick server.
_MAX_MESSAGE_QUEUE_SIZE = 1000 # Safety limit for the outgoing message queue.
_ACTIVATION_WAIT_POLL_INTERVAL_CPYTHON = 0.1 # Polling interval for CPython's blocking activate_connection CV.
_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON = 15.0 # Overall timeout for CPython's blocking activate_connection.


class _ServiceStatus(Enum):
    """Internal states for the ConnectionService lifecycle.

    These states track the detailed progress of connection activation and
    the overall operational status of the service.
    """
    IDLE = auto()                           # Initial state, or after clean shutdown. Not yet activated.
    ACTIVATING_SCHEDULED = auto()           # _async_activate_and_run_message_queue submitted to TaskManager.
    CORE_CONNECTING = auto()                # CommunicationManager is attempting to connect its transport.
    CORE_CONNECTED = auto()                 # Core transport (e.g., WebSocket) is connected.
    WAITING_SIDEKICK_ANNOUNCE = auto()      # Hero 'online' announce sent, waiting for Sidekick UI 'online'.
    ACTIVE = auto()                         # Fully active: Sidekick UI 'online' received, global/clearAll sent, message queue processed.
    FAILED = auto()                         # Activation failed, or an unrecoverable error occurred.
    SHUTTING_DOWN = auto()                  # Shutdown initiated by user or error.
    SHUTDOWN_COMPLETE = auto()              # Shutdown finished, resources released.


class ConnectionService:
    """
    Orchestrates Sidekick communication and manages the service lifecycle.
    This class is intended to be a singleton, accessed via `get_instance()`.
    It handles the complexities of asynchronous communication and state
    management, providing a simpler interface for other parts of the library.
    """

    _instance: Optional['ConnectionService'] = None
    _instance_lock = threading.Lock() # Lock for singleton instance creation

    def __init__(self):
        """
        Initializes the ConnectionService. This constructor should only be
        called internally by `get_instance()` to enforce singleton behavior.
        """
        if ConnectionService._instance is not None: # pragma: no cover
            raise RuntimeError("ConnectionService is a singleton. Use get_instance().")

        self._task_manager: TaskManager = get_task_manager()
        self._communication_manager: Optional[CommunicationManager] = None # Lazily initialized

        self._service_status: _ServiceStatus = _ServiceStatus.IDLE
        # Reentrant lock for _service_status and related state variables that might be
        # accessed/modified from different contexts (main thread, TM's async thread).
        self._status_lock = threading.RLock()

        self._async_activate_task: Optional[asyncio.Task] = None # Holds the main async activation task
        # Condition variable for CPython's activate_connection() to block synchronously
        # It uses _status_lock.
        self._activation_cv = threading.Condition(self._status_lock)

        self._hero_peer_id: str = f"hero-py-{uuid.uuid4().hex}" # Unique ID for this Python client
        self._websocket_url: str = _DEFAULT_WEBSOCKET_URL # Can be changed by set_target_url

        # Asyncio Events for internal coordination within the async activation flow.
        # Initialized to None; created by _create_asyncio_events_if_needed() within TM's loop context.
        self._core_transport_connected_event: Optional[asyncio.Event] = None
        self._sidekick_ui_online_event: Optional[asyncio.Event] = None
        self._clearall_sent_and_queue_processed_event: Optional[asyncio.Event] = None

        self._message_queue: Deque[Dict[str, Any]] = deque(maxlen=_MAX_MESSAGE_QUEUE_SIZE)
        self._component_message_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._user_global_message_handler: Optional[Callable[[Dict[str, Any]], None]] = None
        self._sidekick_peers_info: Dict[str, Dict[str, Any]] = {} # Tracks connected Sidekick UI peers

        logger.info(f"ConnectionService initialized (Hero Peer ID: {self._hero_peer_id})")

    @staticmethod
    def get_instance() -> 'ConnectionService':
        """Gets the singleton instance of the ConnectionService."""
        if ConnectionService._instance is None:
            with ConnectionService._instance_lock:
                if ConnectionService._instance is None:
                    ConnectionService._instance = ConnectionService()
        return ConnectionService._instance

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Convenience method to get the event loop from the TaskManager."""
        self._task_manager.ensure_loop_running() # Ensures TM and its loop are ready
        return self._task_manager.get_loop()

    def _create_asyncio_events_if_needed(self) -> None:
        """Creates internal asyncio.Event instances. Must be called from TM's loop."""
        if not self._task_manager.is_loop_running(): # pragma: no cover
            logger.critical("_create_asyncio_events_if_needed called but TM loop not running. This is a critical error.")
            # This indicates a severe logic flaw if reached.
            self._task_manager.ensure_loop_running() # Attempt to recover, though it may be too late.

        # asyncio.Event() uses the currently running loop when called from within that loop.
        if self._core_transport_connected_event is None:
            self._core_transport_connected_event = asyncio.Event()
        if self._sidekick_ui_online_event is None:
            self._sidekick_ui_online_event = asyncio.Event()
        if self._clearall_sent_and_queue_processed_event is None:
            self._clearall_sent_and_queue_processed_event = asyncio.Event()

    def set_target_url(self, url: str) -> None:
        """Sets the target WebSocket URL for the connection.
        Must be called *before* the first connection attempt.
        """
        if not isinstance(url, str) or not (url.startswith("ws://") or url.startswith("wss://")):
            raise ValueError(f"Invalid WebSocket URL: {url}. Must start with 'ws://' or 'wss://'.")
        with self._status_lock:
            if self._communication_manager is not None and self._websocket_url != url and \
               self._service_status not in [_ServiceStatus.IDLE, _ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.FAILED]:
                logger.warning( # pragma: no cover
                    f"Sidekick URL changed to '{url}' after communication manager was "
                    f"initialized with '{self._websocket_url}' and service is not idle/failed. "
                    "Change will take effect on next full (re)activation after shutdown."
                )
            self._websocket_url = url
            logger.info(f"Sidekick target URL set to: {self._websocket_url}")

    def _get_or_create_communication_manager(self) -> CommunicationManager:
        """Lazily creates and configures the CommunicationManager. Must be called with _status_lock held."""
        # Allow re-creation if CM previously existed but died and service state allows re-init.
        if self._communication_manager is None or \
           (self._communication_manager.get_current_status() in [CoreConnectionStatus.DISCONNECTED, CoreConnectionStatus.ERROR] and
            self._service_status in [_ServiceStatus.IDLE, _ServiceStatus.FAILED, _ServiceStatus.SHUTDOWN_COMPLETE]):
            logger.debug("CommunicationManager instance creating/re-creating...")
            ws_cfg = {} # Future: Populate from a global config system for ping intervals, etc.
            try:
                self._communication_manager = get_communication_manager(
                    ws_url=self._websocket_url, ws_config=ws_cfg
                )
                # Register internal handlers to bridge CM events to ConnectionService logic
                self._communication_manager.register_message_handler(self._handle_core_message)
                self._communication_manager.register_status_change_handler(self._handle_core_status_change)
                self._communication_manager.register_error_handler(self._handle_core_error)
                logger.info("CommunicationManager instance created/recreated and handlers registered.")
            except Exception as e_cm_create: # pragma: no cover
                logger.exception(f"Fatal: Failed to create CommunicationManager: {e_cm_create}")
                self._service_status = _ServiceStatus.FAILED # Critical failure
                raise SidekickConnectionError(f"Could not initialize communication manager: {e_cm_create}", original_exception=e_cm_create)

        if self._communication_manager is None: # Should be unreachable if above logic is correct # pragma: no cover
            raise RuntimeError("CommunicationManager is unexpectedly None after creation attempt.")
        return self._communication_manager

    def _activation_done_callback(self, fut: asyncio.Task) -> None:
        """Callback executed when the _async_activate_and_run_message_queue task finishes or fails."""
        with self._status_lock:
            try:
                fut.result() # Re-raises exception if the async_activate task failed
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
                if not is_pyodide(): # CPython's blocking activate_connection waits on this CV
                    self._activation_cv.notify_all()

    def _re_raise_activation_failure_if_any(self) -> None:
        """Helper for CPython's blocking activate_connection.
        If the async activation task failed, this re-raises its exception.
        Assumes _status_lock may be held or this is called after task is done.
        """
        if self._async_activate_task and self._async_activate_task.done():
            try:
                self._async_activate_task.result() # Re-raises stored exception
            except asyncio.CancelledError: # pragma: no cover
                raise SidekickConnectionError("Activation was cancelled (likely due to shutdown).") from None
            except (SidekickTimeoutError, SidekickConnectionRefusedError, SidekickDisconnectedError, SidekickConnectionError) as e_known:
                # Re-raise specific Sidekick errors directly
                raise e_known
            except Exception as e_unknown: # pragma: no cover
                # Wrap other unexpected errors from the activation task
                raise SidekickConnectionError(f"Activation failed due to an unexpected error: {e_unknown}", original_exception=e_unknown) from e_unknown

    def activate_connection(self) -> None:
        """Ensures the Sidekick service is connected and ready.
        In CPython, this method blocks until activation is complete or fails.
        In Pyodide, it initiates asynchronous activation and returns immediately.
        """
        with self._status_lock: # Main lock for coordinating activation attempts
            current_s_status = self._service_status
            logger.debug(f"activate_connection called. Current service status: {current_s_status.name}")

            if current_s_status == _ServiceStatus.ACTIVE:
                logger.debug("Service already active. Activation not needed.")
                return

            is_activation_task_currently_running = self._async_activate_task and not self._async_activate_task.done()

            if is_activation_task_currently_running:
                logger.debug("Activation is already in progress.")
                if not is_pyodide(): # CPython needs to block and wait for the *current* activation
                    logger.debug("CPython: activate_connection blocking for ongoing async activation...")
                    # Wait until the current activation task (monitored by _activation_done_callback)
                    # changes the status from intermediate states or completes.
                    start_wait_time = self._get_loop().time() # time.monotonic() better if loop is certain
                    while self._service_status not in [_ServiceStatus.ACTIVE, _ServiceStatus.FAILED, _ServiceStatus.SHUTDOWN_COMPLETE]:
                        if not self._activation_cv.wait(timeout=_ACTIVATION_WAIT_POLL_INTERVAL_CPYTHON):
                            # CV timed out, check overall timeout
                            if (self._get_loop().time() - start_wait_time) > _ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON: # pragma: no cover
                                logger.error(f"activate_connection: CPython timed out after {_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON}s waiting for ongoing activation.")
                                self._service_status = _ServiceStatus.FAILED # Force failed state
                                if self._async_activate_task and not self._async_activate_task.done():
                                    self._async_activate_task.cancel() # Attempt to cancel stuck task
                                raise SidekickTimeoutError(f"Timeout waiting for Sidekick service activation ({_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON}s).")
                        # Check if task finished while we were polling (CV might be missed in rare races)
                        if self._async_activate_task and self._async_activate_task.done(): break

                    # After waiting, if activation failed, re-raise the error
                    if self._service_status == _ServiceStatus.FAILED:
                        self._re_raise_activation_failure_if_any()
                return # Pyodide returns (already running async), CPython returns after waiting for current activation

            # If idle, shutdown_complete, or failed, we can attempt a new activation
            if current_s_status in [_ServiceStatus.IDLE, _ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.FAILED]:
                logger.info(f"Initiating Sidekick connection service activation (from status: {current_s_status.name})...")
                self._service_status = _ServiceStatus.ACTIVATING_SCHEDULED

                # Ensure any previous (e.g., failed) task is cleared before creating new one
                if self._async_activate_task and not self._async_activate_task.done():
                    self._async_activate_task.cancel() # pragma: no cover
                self._async_activate_task = None # Clear ref to old task

                # Reset internal asyncio.Events for the new activation sequence
                self._sidekick_ui_online_event = None
                self._clearall_sent_and_queue_processed_event = None
                self._core_transport_connected_event = None

                self._task_manager.ensure_loop_running() # Crucial for CPython before submitting task
                self._async_activate_task = self._task_manager.submit_task(
                    self._async_activate_and_run_message_queue()
                )
                self._async_activate_task.add_done_callback(self._activation_done_callback)

                if not is_pyodide(): # CPython blocks for this new activation
                    logger.debug("CPython: activate_connection blocking for new async activation...")
                    start_wait_time = self._get_loop().time()
                    while self._service_status not in [_ServiceStatus.ACTIVE, _ServiceStatus.FAILED, _ServiceStatus.SHUTDOWN_COMPLETE]:
                        if not self._activation_cv.wait(timeout=_ACTIVATION_WAIT_POLL_INTERVAL_CPYTHON):
                             if (self._get_loop().time() - start_wait_time) > _ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON: # pragma: no cover
                                logger.error(f"activate_connection: CPython timed out after {_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON}s waiting for new activation.")
                                self._service_status = _ServiceStatus.FAILED
                                if self._async_activate_task and not self._async_activate_task.done():
                                    self._async_activate_task.cancel()
                                raise SidekickTimeoutError(f"Timeout waiting for Sidekick service activation ({_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON}s).")
                        if self._async_activate_task and self._async_activate_task.done(): break

                    if self._service_status == _ServiceStatus.FAILED:
                        self._re_raise_activation_failure_if_any()
                return

            # If in other intermediate states (e.g., CORE_CONNECTING but no task running), log warning.
            # This implies an inconsistent state.
            logger.warning(f"activate_connection called in unexpected intermediate state {current_s_status.name} without a running activation task. Not initiating new activation.") # pragma: no cover

    async def _async_activate_and_run_message_queue(self) -> None:
        """Core asynchronous activation logic: connect, announce, clear, process queue."""
        comm_manager: Optional[CommunicationManager] = None
        try:
            with self._status_lock:
                if self._service_status not in [
                    _ServiceStatus.ACTIVATING_SCHEDULED, _ServiceStatus.FAILED,
                    _ServiceStatus.IDLE, _ServiceStatus.SHUTDOWN_COMPLETE
                ]: # pragma: no cover
                    logger.warning(f"_async_activate_and_run_message_queue called in unexpected state: {self._service_status.name}. Aborting.")
                    # Set FAILED to ensure any CPython waiter is unblocked with failure.
                    if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
                    return

                self._create_asyncio_events_if_needed() # Creates events on the current (TM's) loop
                self._core_transport_connected_event.clear() # type: ignore[union-attr]
                self._sidekick_ui_online_event.clear() # type: ignore[union-attr]
                self._clearall_sent_and_queue_processed_event.clear() # type: ignore[union-attr]
                self._sidekick_peers_info.clear()

            logger.debug("_async_activate: Getting/Creating CommunicationManager.")
            comm_manager = self._get_or_create_communication_manager()

            with self._status_lock: self._service_status = _ServiceStatus.CORE_CONNECTING
            logger.debug("_async_activate: Initiating core transport connect via CM's connect_async().")

            # Submit CM's connect_async as a task. We don't await this task directly here.
            # Instead, we await self._core_transport_connected_event which is set by the status handler.
            # This decouples waiting for connection from the direct await of connect_async,
            # allowing status updates to occur more naturally if connect_async itself is complex.
            connect_cm_task = self._task_manager.submit_task(comm_manager.connect_async())

            logger.debug(f"_async_activate: Waiting up to {_CONNECT_CORE_TRANSPORT_TIMEOUT_SECONDS}s for core transport to be confirmed connected via event...")
            try:
                await asyncio.wait_for(self._core_transport_connected_event.wait(), timeout=_CONNECT_CORE_TRANSPORT_TIMEOUT_SECONDS) # type: ignore[union-attr]
                logger.info("Core transport connection confirmed via _core_transport_connected_event.")
                # Check if the connect_cm_task itself had an error, even if event was set (unlikely but defensive)
                if connect_cm_task.done() and connect_cm_task.exception(): # pragma: no cover
                    raise connect_cm_task.exception() # Propagate error from connect_cm_task
            except asyncio.TimeoutError:
                with self._status_lock:
                    cm_stat = comm_manager.get_current_status() if comm_manager else "N/A"
                    serv_stat = self._service_status
                err_msg = (f"Timeout waiting for core transport connection confirmation event "
                           f"(Service Status: {serv_stat.name}, CM Status: {cm_stat}). "
                           f"The underlying connect_async may have also failed or timed out.")
                logger.error(err_msg)
                if not connect_cm_task.done(): connect_cm_task.cancel() # Cancel the CM connect task
                raise SidekickConnectionError(err_msg) from None # Use a more general Sidekick error for this phase

            with self._status_lock: # Re-check service status after waiting for event
                if self._service_status != _ServiceStatus.CORE_CONNECTED:
                     if self._service_status != _ServiceStatus.FAILED: # Avoid redundant logging if already FAILED
                         # This indicates event was set, but status is not CORE_CONNECTED (e.g., FAILED by callback)
                         logger.error(f"Core transport event set, but service status is '{self._service_status.name}'. Expected CORE_CONNECTED.") # pragma: no cover
                     # If FAILED, the exception would have been (or will be) propagated by connect_cm_task.
                     # The done_callback of this _async_activate_task will handle the overall failure.
                     return # Exit activation early

            # --- Hero Announce ---
            hero_announce = {
                "id": 0, "component": "system", "type": "announce",
                "payload": {
                    "peerId": self._hero_peer_id, "role": "hero", "status": "online",
                    "version": _version.__version__, "timestamp": int(self._get_loop().time() * 1000)
                }
            }
            logger.info(f"Sending Hero 'online' announce.")
            await comm_manager.send_message_async(json.dumps(hero_announce))

            # --- Wait for Sidekick UI Announce ---
            with self._status_lock: self._service_status = _ServiceStatus.WAITING_SIDEKICK_ANNOUNCE
            logger.info(f"Waiting up to {_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS}s for Sidekick UI 'online' announce...")
            try:
                await asyncio.wait_for(self._sidekick_ui_online_event.wait(), timeout=_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS) # type: ignore[union-attr]
                logger.info("Sidekick UI 'online' announce received.")
            except asyncio.TimeoutError:
                err_msg = f"Timeout waiting for Sidekick UI 'online' announce after {_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS}s."
                logger.error(err_msg)
                raise SidekickTimeoutError(err_msg, timeout_seconds=_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS) from None

            # --- Send global/clearAll ---
            clearall_msg = {"id": 0, "component": "global", "type": "clearAll"}
            logger.info(f"Sending 'global/clearAll'.")
            await comm_manager.send_message_async(json.dumps(clearall_msg))

            # --- Process Message Queue and Set Active ---
            logger.debug("Processing message queue (if any) before setting fully active...")
            temp_queue_for_processing: Deque[Dict[str, Any]] = deque()
            with self._status_lock: # Safely copy and clear queue
                temp_queue_for_processing.extend(self._message_queue)
                self._message_queue.clear()

            if temp_queue_for_processing:
                logger.info(f"Processing {len(temp_queue_for_processing)} queued messages.")
                for i, msg_dict in enumerate(list(temp_queue_for_processing)): # Iterate copy for safety
                    logger.debug(f"Sending queued message ({i+1}/{len(temp_queue_for_processing)}): type='{msg_dict.get('type', 'N/A')}'")
                    try:
                        await comm_manager.send_message_async(json.dumps(msg_dict))
                    except CoreDisconnectedError as e_send_q: # pragma: no cover
                        logger.error(f"Failed to send queued message due to disconnection: {e_send_q}. Re-queuing remaining and failing activation.")
                        with self._status_lock: # Re-queue this and subsequent messages
                            self._message_queue.appendleft(msg_dict) # Put current back
                            # Re-queue the rest of temp_queue_for_processing that haven't been attempted
                            remaining_to_requeue = list(temp_queue_for_processing)[i+1:]
                            for item_to_requeue in reversed(remaining_to_requeue):
                                self._message_queue.appendleft(item_to_requeue)
                        raise # Propagate to main try-except of this function, will set FAILED

            with self._status_lock: self._service_status = _ServiceStatus.ACTIVE
            self._clearall_sent_and_queue_processed_event.set() # type: ignore[union-attr]
            logger.info("ConnectionService is now ACTIVE. Activation sequence complete.")

        except (CoreConnectionRefusedError, CoreConnectionTimeoutError, CoreDisconnectedError, CoreConnectionError) as e_core:
            logger.error(f"Core communication error during activation: {type(e_core).__name__}: {e_core}")
            with self._status_lock:
                if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            # Wrap in appropriate SidekickError for the activation task's result
            if isinstance(e_core, CoreConnectionRefusedError):
                raise SidekickConnectionRefusedError(
                    f"Failed to connect to Sidekick service at {getattr(e_core, 'url', self._websocket_url)}.",
                    url=getattr(e_core, 'url', self._websocket_url), original_exception=e_core
                ) from e_core
            elif isinstance(e_core, CoreConnectionTimeoutError): # Core transport timeout
                 raise SidekickConnectionError(
                    f"Transport connection to Sidekick service timed out at {getattr(e_core, 'url', self._websocket_url)}.",
                    original_exception=e_core
                ) from e_core
            else: # CoreDisconnectedError or other CoreConnectionError
                raise SidekickDisconnectedError(
                    f"Disconnected from Sidekick service during activation. Reason: {getattr(e_core, 'reason', str(e_core))}",
                    reason=getattr(e_core, 'reason', None), original_exception=e_core
                ) from e_core
        except SidekickTimeoutError as e_ui_timeout: # Specifically from waiting for UI announce
            logger.error(f"Sidekick UI timeout during activation: {e_ui_timeout}")
            with self._status_lock:
                 if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            raise # Re-raise SidekickTimeoutError as is
        except Exception as e_unexpected: # pragma: no cover
            logger.exception(f"Unexpected fatal error during async activation: {e_unexpected}")
            with self._status_lock:
                 if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            if comm_manager and comm_manager.is_connected(): # Try to clean up CM if it connected
                try: await comm_manager.close_async()
                except Exception: pass
            raise SidekickConnectionError(f"Unexpected activation error: {e_unexpected}", original_exception=e_unexpected) from e_unexpected

    def _send_hero_offline_if_needed(self) -> Optional[asyncio.Task]:
        """
        Sends a hero 'offline' announce message if the service is in an appropriate
        state and the communication manager is connected.

        This is typically called during the shutdown sequence as a best-effort
        notification to the Sidekick server/UI.

        Returns:
            Optional[asyncio.Task]: The asyncio.Task for the send operation if it was
                                    submitted, otherwise None.
        """
        task: Optional[asyncio.Task] = None
        # Access _communication_manager carefully as it might be None'd or its state changing during shutdown
        comm_manager_ref: Optional[CommunicationManager] = None
        can_send = False

        with self._status_lock:  # Ensure consistent read of CM and its status
            comm_manager_ref = self._communication_manager
            if comm_manager_ref and comm_manager_ref.is_connected() and \
                    self._service_status not in [_ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.FAILED,
                                                 _ServiceStatus.IDLE]:
                # Only attempt to send if CM exists, is connected, and service isn't already fully down/never up.
                can_send = True

        if can_send and comm_manager_ref:  # comm_manager_ref should be non-None if can_send is True
            hero_offline_announce = {
                "id": 0, "component": "system", "type": "announce",
                "payload": {
                    "peerId": self._hero_peer_id, "role": "hero", "status": "offline",
                    "version": _version.__version__,
                    # Use time.time() for timestamp as loop might be shutting down for self._get_loop().time()
                    "timestamp": int(time.time() * 1000)
                }
            }
            logger.info(f"Sending Hero 'offline' announce during shutdown.")
            try:
                # Submit as a fire-and-forget task. If it fails, log but don't block shutdown.
                task = self._task_manager.submit_task(
                    comm_manager_ref.send_message_async(json.dumps(hero_offline_announce))
                )
            except (CoreTaskSubmissionError, CoreLoopNotRunningError, AttributeError) as e:  # pragma: no cover
                # AttributeError if comm_manager_ref became None between check and use (highly unlikely with current locking)
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
                    with self._status_lock: self._sidekick_peers_info[peer_id] = payload # Store/update
                    if self._sidekick_ui_online_event and not self._sidekick_ui_online_event.is_set():
                        self._sidekick_ui_online_event.set()
                elif status == "offline": # pragma: no cover
                    logger.info(f"Received 'sidekick offline' announce from peer: {peer_id}")
                    with self._status_lock: removed_peer = self._sidekick_peers_info.pop(peer_id, None)
                    if removed_peer and not self._sidekick_peers_info:
                        logger.info("All known Sidekick UIs are now offline.")
                        if self._sidekick_ui_online_event: self._sidekick_ui_online_event.clear()
        elif msg_type in ["event", "error"]:
            instance_id = message_dict.get("src")
            if instance_id:
                handler = self._component_message_handlers.get(instance_id) # Access should be thread-safe if dicts are
                if handler:
                    try:
                        logger.debug(f"Dispatching '{msg_type}' for component '{instance_id}' to its handler.")
                        handler(message_dict) # Synchronous call as per plan
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
        # This method is called by the CM, potentially from the TM's async thread.
        # It needs to safely update _service_status and notify CPython waiters.
        status_changed_by_this_call = False
        original_service_status_for_log = self._service_status # Read before lock for logging if needed

        with self._status_lock:
            current_s_status = self._service_status # Get current status under lock

            if core_status == CoreConnectionStatus.CONNECTED:
                if current_s_status == _ServiceStatus.CORE_CONNECTING:
                    self._service_status = _ServiceStatus.CORE_CONNECTED
                    status_changed_by_this_call = True
                    logger.info("Service status advanced to CORE_CONNECTED (transport layer active).")
                    if self._core_transport_connected_event: # This event is awaited by _async_activate
                        self._core_transport_connected_event.set()
                # else: If core CM reports CONNECTED but service status is beyond CORE_CONNECTING,
                # it might be a reconnect scenario (not handled yet) or redundant info.
            elif core_status in [CoreConnectionStatus.DISCONNECTED, CoreConnectionStatus.ERROR]:
                logger.warning(f"Core communication channel reported {core_status.name}.")
                if self._core_transport_connected_event:
                    self._core_transport_connected_event.clear() # Transport is down

                # If not already in a terminal state, this is an unexpected failure.
                if current_s_status not in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.IDLE]:
                    if self._service_status != _ServiceStatus.FAILED: # Avoid redundant logging/state change
                        self._service_status = _ServiceStatus.FAILED
                        status_changed_by_this_call = True
                        logger.error(f"Service status changed to FAILED due to core channel {core_status.name}.")

                    # Clear other activation-gating events
                    if self._sidekick_ui_online_event: self._sidekick_ui_online_event.clear()
                    if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()

                    # If an activation task was in progress, this core failure should cause it to fail.
                    # The task's done_callback will handle notifying CPython waiters.
                    # If not in activation, this signals an active connection dropped.
                    if not (self._async_activate_task and not self._async_activate_task.done()):
                        # If not during an active activation, and CPython is waiting in activate_connection
                        # (e.g. it was ACTIVE, then core dropped), notify it.
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


    def send_message(self, message_dict: Dict[str, Any]) -> None:
        """Sends a Sidekick protocol message. Queues if service not fully active."""
        # Determine if activation needs to be kicked off
        with self._status_lock:
            s_status = self._service_status
            # Needs activation if completely idle, or if failed (CPython might retry implicitly)
            needs_activation_kickoff = s_status in [_ServiceStatus.IDLE, _ServiceStatus.SHUTDOWN_COMPLETE] or \
                                       (s_status == _ServiceStatus.FAILED and not is_pyodide())

        if needs_activation_kickoff:
            try:
                logger.debug(f"send_message: Kicking off activation from status {s_status.name}")
                self.activate_connection() # This call handles its own logic for CPython blocking / Pyodide async
            except SidekickConnectionError as e:
                # This implies CPython's blocking activate_connection failed immediately.
                logger.error(f"Implicit activation for send_message failed: {e}. Message not sent.")
                raise # Propagate the error

        # Re-check status and access queue/event under lock
        with self._status_lock:
            is_ready_for_direct_send = self._clearall_sent_and_queue_processed_event and \
                                       self._clearall_sent_and_queue_processed_event.is_set() and \
                                       self._service_status == _ServiceStatus.ACTIVE

            if not is_ready_for_direct_send:
                if self._service_status in [_ServiceStatus.FAILED, _ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                    logger.error(f"Cannot send message, service status is {self._service_status.name}. Message dropped: {message_dict.get('type')}")
                    raise SidekickDisconnectedError(f"Service not active (status: {self._service_status.name}). Cannot send.")

                if len(self._message_queue) >= self._message_queue.maxlen: # type: ignore[arg-type]
                    dropped_msg = self._message_queue.popleft() # pragma: no cover
                    logger.error(f"Message queue full ({self._message_queue.maxlen}). Dropping oldest: type='{dropped_msg.get('type')}'")
                self._message_queue.append(message_dict)
                logger.debug(f"Message type='{message_dict.get('type', 'N/A')}' queued (qsize: {len(self._message_queue)}). Waiting for full activation.")
                # If CPython, activate_connection would have blocked or failed.
                # If Pyodide, activate_connection returned, and _async_activate_task is running.
                return # Message has been queued.

        # If execution reaches here, is_ready_for_direct_send was true.
        comm_manager = self._communication_manager # Should be valid if service is ACTIVE
        if not comm_manager or not comm_manager.is_connected(): # pragma: no cover
            logger.critical("send_message: CRITICAL STATE - Service ACTIVE but CM unavailable/disconnected.")
            with self._status_lock: # Re-queue and mark service as non-operational to force re-activation
                self._message_queue.append(message_dict)
                if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()
                self._service_status = _ServiceStatus.FAILED
            raise SidekickDisconnectedError("Internal state inconsistency: Service active but CM not ready.")

        logger.debug(f"Sending message directly: type='{message_dict.get('type', 'N/A')}' target='{message_dict.get('target', 'N/A')}'")
        try:
            json_str = json.dumps(message_dict)
            # Fire-and-forget the send task. CM's send_message_async handles its own errors
            # by updating status or calling error handler, which ConnectionService listens to.
            self._task_manager.submit_task(comm_manager.send_message_async(json_str))
        except json.JSONDecodeError as e_json: # pragma: no cover
            logger.error(f"Failed to serialize message to JSON: {e_json}. Message: {message_dict}")
            raise TypeError(f"Message content not JSON serializable: {e_json}") from e_json
        except (CoreTaskSubmissionError, AttributeError) as e_submit: # pragma: no cover
            # AttributeError if TM or CM is None unexpectedly.
            logger.error(f"Failed to submit send_message_async task: {e_submit}. Re-queuing message.")
            with self._status_lock:
                self._message_queue.append(message_dict)
                if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()
                if self._service_status == _ServiceStatus.ACTIVE: self._service_status = _ServiceStatus.CORE_CONNECTED # Rollback to a state that implies re-check
            raise SidekickDisconnectedError(f"Failed to submit message send task: {e_submit}", original_exception=e_submit)


    def register_component_message_handler(self, instance_id: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a message handler for a specific component instance ID."""
        if not isinstance(instance_id, str) or not instance_id:
            raise ValueError("instance_id must be a non-empty string.")
        if not callable(handler):
            raise TypeError("handler must be a callable function.")
        # _component_message_handlers is a standard dict, access should be GIL-protected.
        # If contention becomes an issue, a lock specific to this dict could be used.
        # For now, assuming GIL is sufficient for this relatively infrequent operation.
        if instance_id in self._component_message_handlers: # pragma: no cover
            # Overwriting a handler might be acceptable in some cases, but for now, strict.
            logger.warning(f"Handler already registered for instance_id: {instance_id}. Overwriting.")
            # raise ValueError(f"Handler already registered for instance_id: {instance_id}")
        self._component_message_handlers[instance_id] = handler
        logger.debug(f"Registered component message handler for instance_id: {instance_id}")

    def unregister_component_message_handler(self, instance_id: str) -> None:
        """Unregisters a message handler for a specific component instance ID."""
        if self._component_message_handlers.pop(instance_id, None):
            logger.debug(f"Unregistered component message handler for instance_id: {instance_id}")

    def clear_all_ui_components(self) -> None:
        """Sends a command to remove all components from the Sidekick UI."""
        logger.info("Requesting ConnectionService to clear all UI components.")
        self.send_message({"id": 0, "component": "global", "type": "clearAll"})

    def shutdown_service(self) -> None:
        """Initiates a graceful shutdown of the ConnectionService."""
        offline_task_handle: Optional[asyncio.Task] = None
        comm_close_task_handle: Optional[asyncio.Task] = None

        with self._status_lock:
            if self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                logger.debug(f"Shutdown already in progress or complete (status: {self._service_status.name}).")
                return # Already shutting down or done.

            logger.info(f"ConnectionService shutdown initiated. Current status: {self._service_status.name}")
            self._service_status = _ServiceStatus.SHUTTING_DOWN

            # 1. Cancel ongoing activation task, if any
            if self._async_activate_task and not self._async_activate_task.done():
                logger.debug("Cancelling active _async_activate_task during shutdown.")
                self._async_activate_task.cancel()
                # We don't await it here; TM's shutdown will handle its loop and tasks.

            # 2. Clear outgoing message queue
            if self._message_queue: # pragma: no cover
                logger.info(f"Clearing {len(self._message_queue)} messages from queue due to shutdown.")
                self._message_queue.clear()

            # 3. Clear internal asyncio events
            if self._core_transport_connected_event: self._core_transport_connected_event.clear()
            if self._sidekick_ui_online_event: self._sidekick_ui_online_event.clear()
            if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()

            # 4. Send hero 'offline' announce (best effort, fire-and-forget task)
            offline_task_handle = self._send_hero_offline_if_needed()

            # 5. Schedule CommunicationManager close (fire-and-forget task)
            comm_manager_to_close = self._communication_manager
            if comm_manager_to_close:
                logger.debug("Scheduling CommunicationManager.close_async().")
                try:
                    comm_close_task_handle = self._task_manager.submit_task(comm_manager_to_close.close_async())
                except (CoreTaskSubmissionError, CoreLoopNotRunningError) as e: # pragma: no cover
                    logger.warning(f"Could not submit CM close task during shutdown: {e}")
            # self._communication_manager will be set to None after TM shutdown signal

        # 6. Signal TaskManager to shut down its loop (outside status_lock)
        # This is crucial: it unblocks run_forever() or wait_for_shutdown_async()
        # and allows the TM's loop thread to start its own cleanup.
        logger.debug("Signaling TaskManager to shutdown (from ConnectionService.shutdown_service).")
        self._task_manager.signal_shutdown()

        # Optional: If we need to ensure offline/close tasks complete (makes shutdown_service async or blocking)
        # For a synchronous shutdown_service, these tasks run in background.
        # If this method were async:
        # try:
        #     if offline_task_handle: await asyncio.wait_for(offline_task_handle, timeout=1.0)
        #     if comm_close_task_handle: await asyncio.wait_for(comm_close_task_handle, timeout=2.0)
        # except asyncio.TimeoutError: logger.warning("Timeout waiting for offline/close tasks during shutdown.")
        # except Exception: pass


        with self._status_lock: # Final state updates under lock
            self._component_message_handlers.clear()
            self._user_global_message_handler = None
            self._sidekick_peers_info.clear()
            self._communication_manager = None # Dereference CM after its close is scheduled
            self._service_status = _ServiceStatus.SHUTDOWN_COMPLETE
            logger.info("ConnectionService shutdown sequence finalized.")
            # Notify CPython waiters on activate_connection CV if they were stuck
            if not is_pyodide():
                self._activation_cv.notify_all()


    def run_service_forever(self) -> None:
        """Blocks and keeps the service running until shutdown. (CPython specific use)."""
        if is_pyodide(): # pragma: no cover
            logger.error("run_service_forever() is synchronous and not intended for Pyodide. Use run_service_forever_async().")
            # Fallback: try to activate. Pyodide environment keeps worker alive.
            try: self.activate_connection()
            except SidekickError: pass
            return

        try:
            self.activate_connection() # This blocks in CPython until ACTIVE or FAILED
            with self._status_lock: service_is_active = (self._service_status == _ServiceStatus.ACTIVE)

            if service_is_active:
                logger.info("ConnectionService entering run_forever wait state (CPython).")
                self._task_manager.wait_for_shutdown() # Blocks main thread here until TM signals
            else: # pragma: no cover
                logger.error(f"Service not active after activation attempt (status: {self._service_status.name}). Cannot run forever.")
        except KeyboardInterrupt: # pragma: no cover
            logger.info("KeyboardInterrupt in run_service_forever. Initiating shutdown.")
        except SidekickConnectionError as e: # pragma: no cover
            logger.error(f"Connection error in run_service_forever: {e}. Shutting down.")
        except Exception as e: # pragma: no cover
            logger.exception(f"Unexpected error in run_service_forever: {e}. Shutting down.")
        finally:
            # This 'finally' ensures shutdown_service is called if the 'try' block exits
            # for any reason (e.g. KI, error, or if TM's wait_for_shutdown returns early).
            with self._status_lock:
                is_already_terminal = self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]

            if not is_already_terminal:
                logger.info("run_service_forever exiting. Initiating shutdown if not already in progress.")
                self.shutdown_service()
            logger.info("ConnectionService run_forever (CPython) finished.")


    async def run_service_forever_async(self) -> None:
        """Keeps the service running asynchronously until shutdown. (Pyodide/Async use)."""
        try:
            # In Pyodide/async, activate_connection() initiates async activation.
            # We need to await the completion of that activation process here.
            self.activate_connection()

            current_activation_task_ref: Optional[asyncio.Task] = None
            with self._status_lock: # Get the current activation task safely
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
                # Exceptions from activation task are handled by its done_callback, just await completion.

            with self._status_lock: service_is_active = (self._service_status == _ServiceStatus.ACTIVE)

            if service_is_active:
                logger.info("ConnectionService entering run_forever_async wait state.")
                await self._task_manager.wait_for_shutdown_async() # Async wait for TM shutdown signal
            else: # pragma: no cover
                logger.warning(f"Service not active after async activation (status: {self._service_status.name}). Cannot run_forever_async effectively.")

        except KeyboardInterrupt: # pragma: no cover
            # KI might not be reliably caught in all async/Pyodide scenarios for the worker.
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
                self.shutdown_service() # Sync call, but TM signal_shutdown is key
            logger.info("ConnectionService run_service_forever_async finished.")


    def register_user_global_message_handler(self, handler: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        """Registers a user-defined global handler for all incoming messages."""
        if handler is not None and not callable(handler): # pragma: no cover
            raise TypeError("Global message handler must be a callable function or None.")
        # This can be set/cleared without heavy locking if access in _handle_core_message is careful.
        # For simplicity, using status_lock for now if modifications are very rare.
        # A dedicated lock for _user_global_message_handler might be overkill.
        self._user_global_message_handler = handler
        logger.info(f"User global message handler {'set' if handler else 'cleared'}.")

    # Service-level error handler (not currently used, placeholder)
    _error_handler_for_service: Optional[Callable[[Exception], None]] = None


# --- Module-level public API functions using the ConnectionService Singleton ---

_connection_service_singleton_init_lock = threading.Lock()
_connection_service_singleton_instance: Optional[ConnectionService] = None

def _get_service_instance() -> ConnectionService:
    """Internal helper to get or create the singleton ConnectionService instance."""
    global _connection_service_singleton_instance
    if _connection_service_singleton_instance is None:
        with _connection_service_singleton_init_lock:
            if _connection_service_singleton_instance is None:
                # Ensure the instance creation uses the class's own singleton logic
                # if get_instance() is preferred over direct instantiation.
                # Here, ConnectionService() constructor is private-like.
                _connection_service_singleton_instance = ConnectionService()
    return _connection_service_singleton_instance


def set_url(url: str) -> None:
    """Sets the target WebSocket URL for the Sidekick connection.
    Must be called before any components are created or connection is activated.
    """
    _get_service_instance().set_target_url(url)

def activate_connection() -> None:
    """Ensures the Sidekick service is connected and ready.
    In CPython, this blocks until the service is active or activation fails.
    In Pyodide, this initiates asynchronous activation and returns immediately.
    """
    _get_service_instance().activate_connection()

def send_message(message_dict: Dict[str, Any]) -> None:
    """Sends a message dictionary (Sidekick protocol) to the Sidekick UI.
    Will queue messages if the service is not yet fully active.
    """
    _get_service_instance().send_message(message_dict)

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

def submit_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task: # Added from previous step
    """Submits a user-defined coroutine to Sidekick's managed event loop.
    Useful for running custom asyncio code alongside Sidekick components.
    """
    return _get_service_instance()._task_manager.submit_task(coro) # Delegate to TM

def register_global_message_handler(handler: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    """Registers a global handler for *all* incoming messages from the UI.
    Mainly for debugging or advanced use.
    """
    _get_service_instance().register_user_global_message_handler(handler)