"""Manages the high-level connection and communication service for Sidekick.

This module defines the `ConnectionService` class, which orchestrates the
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
- Providing user-facing functions (exposed via `sidekick/__init__.py` which
  in turn call methods on this service) to control the service, such as
  explicitly activating the connection and shutting down the service.

This class is intended to be a singleton within the Sidekick library,
instantiated and managed by the `sidekick.connection` module.
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
    CoreDisconnectedError,
    CoreTaskSubmissionError,
    CoreLoopNotRunningError,
    is_pyodide
)
from .exceptions import (
    SidekickConnectionError,
        SidekickTimeoutError,
    SidekickDisconnectedError,
    SidekickError
)
# DEFAULT_SERVERS is used by ServerConnector, set_user_url_globally is called by connection.py
# from .config import DEFAULT_SERVERS, set_user_url_globally
from .server_connector import ServerConnector, ConnectionResult


# --- Constants specific to ConnectionService ---
_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS = 180.0
"""Timeout in seconds for waiting for the Sidekick UI to send its 'online' announce."""

_MAX_MESSAGE_QUEUE_SIZE = 1000
"""Maximum number of messages to queue if sent before the service is fully active."""

_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON = 180.0
"""Default timeout in seconds for the synchronous `wait_for_active_connection_sync`."""


class _ServiceStatus(Enum):
    """Internal states for the ConnectionService lifecycle.

    These states track the detailed progress of connection activation and
    the overall operational status of the service.
    """
    IDLE = auto()
    ACTIVATING_SCHEDULED = auto() # Async activation task has been scheduled
    CORE_CONNECTED = auto()       # Underlying transport (CM) is connected
    WAITING_SIDEKICK_ANNOUNCE = auto() # Waiting for UI peer to announce itself
    ACTIVE = auto()               # Service is fully operational, queue processed
    FAILED = auto()               # Activation or operation failed unrecoverably
    SHUTTING_DOWN = auto()        # Shutdown process has been initiated
    SHUTDOWN_COMPLETE = auto()    # Service is fully shut down


class ConnectionService:
    """
    Orchestrates Sidekick communication and manages the service lifecycle
    post-connection. This class is intended to be a singleton, typically
    accessed via helper functions in the `sidekick.connection` module.
    """

    # _instance and _instance_lock are managed by connection.py for singleton pattern

    def __init__(self):
        """
        Initializes the ConnectionService.
        This constructor should typically only be called once by the singleton
        management logic in `sidekick.connection`.
        """
        # if ConnectionService._instance is not None: # pragma: no cover
        #     raise RuntimeError("ConnectionService is a singleton. Use _get_service_instance() from connection module.")

        self._task_manager: TaskManager = get_task_manager()
        self._communication_manager: Optional[CommunicationManager] = None
        self._server_connector: ServerConnector = ServerConnector(self._task_manager)
        self._connected_server_name: Optional[str] = None

        self._service_status: _ServiceStatus = _ServiceStatus.IDLE
        self._status_lock = threading.RLock() # Reentrant lock for status and related attributes

        self._async_activate_task: Optional[asyncio.Task] = None
        # For CPython: allows a non-event-loop thread (e.g., main thread) to block
        # until the asynchronous activation process completes or fails.
        self._sync_activation_complete_event = threading.Event()
        # Stores any exception that occurred during the _async_activate_task,
        # to be re-raised by synchronous waiters.
        self._activation_exception: Optional[BaseException] = None

        self._hero_peer_id: str = f"hero-py-{uuid.uuid4().hex}"

        # asyncio.Events used by _async_activate_and_run_message_queue
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
        """Creates internal asyncio.Event instances for the activation sequence.
        Must be called from within the TaskManager's event loop context or
        before the loop is run if these events are created by asyncio.new_event_loop().
        For Pyodide, the loop is always available. For CPython, ensure_loop_running ensures it.
        """
        if not self._task_manager.is_loop_running(): # pragma: no cover
            logger.critical("_create_asyncio_events_if_needed called but TM loop not running.")
            self._task_manager.ensure_loop_running() # Attempt to start it

        # These events are used by the _async_activate_and_run_message_queue coroutine,
        # so they should be associated with the loop that coroutine will run on.
        # If the loop is self._task_manager.get_loop(), then these events are created correctly.
        current_event_loop = self._get_loop()
        if self._core_transport_connected_event is None or self._core_transport_connected_event._loop is not current_event_loop: # type: ignore
            self._core_transport_connected_event = asyncio.Event()
        if self._sidekick_ui_online_event is None or self._sidekick_ui_online_event._loop is not current_event_loop: # type: ignore
            self._sidekick_ui_online_event = asyncio.Event()
        if self._clearall_sent_and_queue_processed_event is None or self._clearall_sent_and_queue_processed_event._loop is not current_event_loop: # type: ignore
            self._clearall_sent_and_queue_processed_event = asyncio.Event()

        # Clear them to ensure they are fresh for a new activation sequence
        self._core_transport_connected_event.clear()
        self._sidekick_ui_online_event.clear()
        self._clearall_sent_and_queue_processed_event.clear()


    def _activation_done_callback(self, fut: asyncio.Task) -> None:
        """
        Callback executed when the _async_activate_and_run_message_queue task
        finishes or fails. It updates the service status and notifies synchronous
        waiters via _sync_activation_complete_event.
        """
        original_exception: Optional[BaseException] = None
        # final_status_after_async_task = self._service_status # Capture status before potential change

        with self._status_lock: # Lock to ensure atomic update of status and exception
            try:
                fut.result() # Check for exceptions from the async activation task
                # If the future completed without exception, but the service status
                # didn't reach ACTIVE, it's still considered an activation failure.
                if self._service_status != _ServiceStatus.ACTIVE:
                    # This path might be hit if _async_activate_and_run_message_queue itself
                    # sets status to FAILED then raises, or if it's cancelled before reaching ACTIVE.
                    err_msg = f"Activation task completed but service not in ACTIVE state (current: {self._service_status.name})."
                    logger.error(err_msg)
                    # Only set _activation_exception if one isn't already set by the task itself
                    if not self._activation_exception:
                        original_exception = SidekickConnectionError(err_msg)
                    # Ensure status reflects failure if not already FAILED and not part of shutdown
                    if self._service_status not in [_ServiceStatus.FAILED, _ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                        self._service_status = _ServiceStatus.FAILED
                else:
                    logger.info(f"Async activation task completed successfully. Service is ACTIVE.")
            except asyncio.CancelledError:
                logger.info("Async activation task was cancelled.")
                original_exception = SidekickConnectionError("Activation was cancelled.")
                # Update status if cancellation was not part of a normal shutdown
                if self._service_status not in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                    self._service_status = _ServiceStatus.FAILED
            except (SidekickTimeoutError, SidekickConnectionError, SidekickDisconnectedError) as e_sk_known:
                logger.error(f"Async activation failed with known Sidekick error: {type(e_sk_known).__name__}: {e_sk_known}")
                original_exception = e_sk_known
                if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            except Exception as e_unexpected: # pragma: no cover
                logger.exception(f"Async activation task failed with unexpected error: {e_unexpected}")
                original_exception = e_unexpected
                if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            finally:
                # Store the exception for synchronous waiters if one occurred.
                # Do not overwrite if _activation_exception was already set (e.g. by shutdown).
                if original_exception and not self._activation_exception:
                    self._activation_exception = original_exception

                # Always set the synchronous event to unblock any waiters
                if not self._sync_activation_complete_event.is_set():
                    self._sync_activation_complete_event.set()

                logger.debug(
                    f"_activation_done_callback finished. "
                    f"Final service status during callback: {self._service_status.name}. "
                    f"Sync event set. Exception stored: {type(self._activation_exception).__name__ if self._activation_exception else 'None'}"
                )


    def activate_connection_internally(self) -> None:
        """
        Ensures the Sidekick service activation process is initiated if not already
        started or active. This call is non-blocking. It schedules the asynchronous
        activation task.
        To wait synchronously for completion in CPython, use `wait_for_active_connection_sync()`.
        """
        with self._status_lock:
            current_s_status = self._service_status
            logger.debug(f"activate_connection_internally called. Current service status: {current_s_status.name}")

            is_activation_task_running = self._async_activate_task and not self._async_activate_task.done()

            if current_s_status == _ServiceStatus.ACTIVE or is_activation_task_running:
                if current_s_status == _ServiceStatus.ACTIVE:
                    logger.debug("Service already active. Activation not needed.")
                else: # is_activation_task_running is true
                    logger.debug(f"Activation already in progress (status: {current_s_status.name}). No new task scheduled.")
                return

            if current_s_status in [_ServiceStatus.IDLE, _ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.FAILED]:
                logger.info(f"Initiating Sidekick connection service activation (from status: {current_s_status.name}). This is non-blocking.")
                self._service_status = _ServiceStatus.ACTIVATING_SCHEDULED

                # Reset states for a new activation attempt
                self._activation_exception = None
                self._sync_activation_complete_event.clear() # Important: clear before new task
                self._communication_manager = None
                self._connected_server_name = None
                self._sidekick_peers_info.clear()
                # Re-create or clear asyncio events for the activation sequence
                # These events must be associated with the TM's loop
                self._task_manager.ensure_loop_running() # Ensures loop is available for event creation
                self._create_asyncio_events_if_needed()

                # self._task_manager.ensure_loop_running() # Already called for _create_asyncio_events_if_needed
                self._async_activate_task = self._task_manager.submit_task(
                    self._async_activate_and_run_message_queue()
                )
                # Add the done callback that handles sync event and exception storage
                self._async_activate_task.add_done_callback(self._activation_done_callback)
                logger.debug("Async activation task (_async_activate_and_run_message_queue) has been scheduled.")
            else: # pragma: no cover
                # This case should ideally not be reached if status transitions are correct.
                logger.warning(
                    f"activate_connection_internally called in an unexpected intermediate state: {current_s_status.name}. "
                    "Activation not re-initiated."
                )
        # This method now returns immediately, without blocking.

    async def _async_activate_and_run_message_queue(self) -> None:
        """
        Core asynchronous activation logic for the ConnectionService.
        This coroutine performs the following steps:
        1. Uses `ServerConnector` to establish a low-level connection (e.g., WebSocket).
           Passes internal handlers (`_handle_core_message`, etc.) to `ServerConnector`
           so they are set up *before* any messages can arrive from the transport.
        2. If successful, prints UI URL hints if applicable.
        3. Sends the "hero online" `system/announce` message.
        4. Waits for the Sidekick UI to send its "sidekick online" `system/announce` message
           (with a timeout).
        5. Sends a `global/clearAll` message to reset the UI panel.
        6. Processes any messages that were queued while activation was in progress.
        7. Sets the service status to `ACTIVE`.

        If any step fails (e.g., connection error, timeout waiting for UI), it sets
        the service status to `FAILED` and re-raises an appropriate exception, which
        is then handled by `_activation_done_callback`.
        """
        try:
            with self._status_lock: # Check status before proceeding
                if self._service_status != _ServiceStatus.ACTIVATING_SCHEDULED: # pragma: no cover
                    logger.warning(f"_async_activate_and_run_message_queue: Expected ACTIVATING_SCHEDULED, "
                                   f"but found {self._service_status.name}. Aborting activation sequence.")
                    if not self._activation_exception: self._activation_exception = SidekickConnectionError("Activation aborted due to unexpected status change.")
                    return

                assert self._core_transport_connected_event is not None, "Core transport event not initialized"
                assert self._sidekick_ui_online_event is not None, "Sidekick UI online event not initialized"
                assert self._clearall_sent_and_queue_processed_event is not None, "ClearAll/Queue event not initialized"

            logger.debug("_async_activate_and_run_message_queue: Attempting connection via ServerConnector.")
            connection_outcome: ConnectionResult
            try:
                # Pass handlers directly to the server_connector's connect_async method
                connection_outcome = await self._server_connector.connect_async(
                    message_handler=self._handle_core_message,
                    status_change_handler=self._handle_core_status_change,
                    error_handler=self._handle_core_error
                )
                self._communication_manager = connection_outcome.communication_manager
                self._connected_server_name = connection_outcome.server_name

                with self._status_lock: # Ensure thread-safe access if needed, though this coro runs in one thread
                    self._activation_exception = None

                if not self._communication_manager: # Should be caught by ServerConnector raising error
                    raise SidekickConnectionError("ServerConnector returned without a CommunicationManager.") # pragma: no cover

                logger.info(f"Successfully connected to Sidekick server: {self._connected_server_name or 'Unknown'}")

            except SidekickConnectionError as e_conn_strat:
                logger.error(f"ServerConnector failed to establish any connection: {e_conn_strat}")
                with self._status_lock: self._service_status = _ServiceStatus.FAILED
                raise # Re-raise to be caught by _activation_done_callback

            with self._status_lock:
                if self._communication_manager and self._communication_manager.is_connected():
                     self._service_status = _ServiceStatus.CORE_CONNECTED
                     self._core_transport_connected_event.set()
                else: # pragma: no cover
                    logger.critical("CRITICAL: ServerConnector returned, but CM is not valid or not connected.")
                    self._service_status = _ServiceStatus.FAILED
                    raise SidekickConnectionError("ServerConnector logic error: CM invalid post-connection.")

            if connection_outcome.show_ui_url_hint and connection_outcome.ui_url_to_show:
                print(f"Sidekick UI is available at: {connection_outcome.ui_url_to_show}")
                print("For the best experience, install the 'Sidekick - Your Visual Coding Buddy' VS Code extension.")

            hero_announce = {
                "id": 0, "component": "system", "type": "announce",
                "payload": {
                    "peerId": self._hero_peer_id, "role": "hero", "status": "online",
                    "version": _version.__version__, "timestamp": int(self._get_loop().time() * 1000)
                }
            }
            logger.info(f"Sending Hero 'online' announce via {self._connected_server_name or 'Unknown'}.")
            if not (self._communication_manager and self._communication_manager.is_connected()):
                raise CoreDisconnectedError("Cannot send hero announce, CM not connected.") # pragma: no cover
            await self._communication_manager.send_message_async(json.dumps(hero_announce))

            with self._status_lock: self._service_status = _ServiceStatus.WAITING_SIDEKICK_ANNOUNCE
            if connection_outcome.show_ui_url_hint: print(f"Waiting up to {_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS:.0f}s for Sidekick UI...")
            logger.info(f"Waiting up to {_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS:.0f}s for Sidekick UI 'online' announce...")
            try:
                await asyncio.wait_for(self._sidekick_ui_online_event.wait(), timeout=_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS)
                if connection_outcome.show_ui_url_hint: print("Sidekick UI is connected.")
                logger.info("Sidekick UI 'online' announce received.")
            except asyncio.TimeoutError:
                if connection_outcome.show_ui_url_hint: print("Sidekick UI did not connect within the timeout period.")
                err_msg = f"Timeout waiting for Sidekick UI 'online' announce after {_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS:.0f}s."
                logger.error(err_msg)
                raise SidekickTimeoutError(err_msg, timeout_seconds=_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS) from None

            clearall_msg = {"id": 0, "component": "global", "type": "clearAll"}
            logger.info(f"Sending 'global/clearAll'.")
            if not (self._communication_manager and self._communication_manager.is_connected()):
                raise CoreDisconnectedError("Cannot send global/clearAll, CM not connected.") # pragma: no cover
            await self._communication_manager.send_message_async(json.dumps(clearall_msg))

            logger.debug("Processing message queue (if any) before setting fully active...")
            temp_queue_for_processing: Deque[Dict[str, Any]] = deque()
            with self._status_lock:
                temp_queue_for_processing.extend(self._message_queue)
                self._message_queue.clear()

            if temp_queue_for_processing:
                logger.info(f"Processing {len(temp_queue_for_processing)} queued messages.")
                for i, msg_dict in enumerate(list(temp_queue_for_processing)):
                    logger.debug(f"Sending queued message ({i+1}/{len(temp_queue_for_processing)}): type='{msg_dict.get('type', 'N/A')}' target='{msg_dict.get('target', 'N/A')}'")
                    if not (self._communication_manager and self._communication_manager.is_connected()):
                        logger.error("CM disconnected while processing message queue. Re-queuing remaining.") # pragma: no cover
                        with self._status_lock:
                            self._message_queue.appendleft(msg_dict)
                            remaining_to_requeue = list(temp_queue_for_processing)[i+1:]
                            for item_to_requeue in reversed(remaining_to_requeue):
                                self._message_queue.appendleft(item_to_requeue)
                        raise CoreDisconnectedError("CM disconnected during queue processing.")
                    try:
                        await self._communication_manager.send_message_async(json.dumps(msg_dict))
                    except CoreDisconnectedError as e_send_q: # pragma: no cover
                        logger.error(f"Failed to send queued message due to disconnection: {e_send_q}. Re-queuing current and remaining, then failing activation.")
                        with self._status_lock:
                            self._message_queue.appendleft(msg_dict)
                            remaining_to_requeue = list(temp_queue_for_processing)[i+1:]
                            for item_to_requeue in reversed(remaining_to_requeue):
                                self._message_queue.appendleft(item_to_requeue)
                        raise
            with self._status_lock: self._service_status = _ServiceStatus.ACTIVE
            self._clearall_sent_and_queue_processed_event.set()
            logger.info("ConnectionService is now ACTIVE. Activation sequence complete.")

        except (SidekickConnectionError, SidekickTimeoutError, SidekickDisconnectedError, CoreDisconnectedError) as e_sk_activation:
            logger.error(f"Sidekick activation sequence error: {type(e_sk_activation).__name__}: {e_sk_activation}")
            with self._status_lock:
                if self._service_status != _ServiceStatus.FAILED : self._service_status = _ServiceStatus.FAILED
            raise # Re-raise to be caught by _activation_done_callback
        except Exception as e_unexpected_activation: # pragma: no cover
            logger.exception(f"Unexpected fatal error during async activation sequence: {e_unexpected_activation}")
            with self._status_lock:
                 if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
            if self._communication_manager and self._communication_manager.is_connected():
                try: await self._communication_manager.close_async()
                except Exception: pass
            raise SidekickConnectionError(
                f"Unexpected activation error: {e_unexpected_activation}",
                original_exception=e_unexpected_activation
            ) from e_unexpected_activation


    def wait_for_active_connection_sync(self, timeout: Optional[float] = _ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON) -> None:
        """
        (CPython specific) Blocks the calling (non-event-loop) thread until the
        Sidekick connection is fully active and ready, or until timeout/failure.
        This method ensures the activation process is initiated if needed.

        Args:
            timeout (Optional[float]): Maximum time in seconds to wait for activation.
                If `None`, uses a default internal timeout (`_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON`).

        Raises:
            SidekickConnectionError: If activation fails for any reason.
            SidekickTimeoutError: If the timeout is reached before connection is active.
            RuntimeError: If called from the Sidekick event loop thread or in Pyodide.
        """
        if is_pyodide(): # pragma: no cover
            logger.warning("wait_for_active_connection_sync is not intended for Pyodide. Use async alternatives.")
            with self._status_lock:
                if self._service_status == _ServiceStatus.ACTIVE: return
            self.activate_connection_internally()
            return

        tm = self._task_manager
        from .core.cpython_task_manager import CPythonTaskManager # Local import to avoid circularity if TM itself uses ConnectionService logic (unlikely here)
        if isinstance(tm, CPythonTaskManager) and tm._loop_thread and \
           threading.get_ident() == tm._loop_thread.ident: # pragma: no cover
            raise RuntimeError("wait_for_active_connection_sync cannot be called from the event loop thread.")

        with self._status_lock:
            if self._service_status == _ServiceStatus.ACTIVE:
                logger.debug("wait_for_active_connection_sync: Service already active.")
                return

            is_activation_task_running = self._async_activate_task and not self._async_activate_task.done()
            if not is_activation_task_running:
                logger.debug("wait_for_active_connection_sync: Triggering activation as it's not active or in_progress.")
                self.activate_connection_internally()

        logger.debug(f"wait_for_active_connection_sync: Waiting for activation completion (timeout: {timeout}s).")

        if not self._sync_activation_complete_event.wait(timeout=timeout):
            logger.error("wait_for_active_connection_sync: Timed out waiting for _sync_activation_complete_event.")
            with self._status_lock:
                if self._async_activate_task and not self._async_activate_task.done():
                    logger.warning("wait_for_active_connection_sync: Cancelling overdue async_activate_task due to timeout.")
                    self._async_activate_task.cancel()
                    if not self._activation_exception:
                        self._activation_exception = SidekickTimeoutError(f"Timeout waiting for Sidekick service activation ({timeout}s).")
            if self._activation_exception and isinstance(self._activation_exception, SidekickTimeoutError):
                raise self._activation_exception
            raise SidekickTimeoutError(f"Timeout waiting for Sidekick service activation ({timeout}s).")

        with self._status_lock:
            if self._activation_exception:
                exc_to_raise = self._activation_exception
                logger.error(f"wait_for_active_connection_sync: Activation failed with exception: {type(exc_to_raise).__name__}: {exc_to_raise}")
                if isinstance(exc_to_raise, (SidekickError, asyncio.CancelledError)):
                    raise exc_to_raise
                else:
                    raise SidekickConnectionError(f"Activation failed: {exc_to_raise}", original_exception=exc_to_raise) from exc_to_raise

            if self._service_status != _ServiceStatus.ACTIVE:
                err_msg = f"Activation completed but service is not in ACTIVE state (status: {self._service_status.name})."
                logger.error(f"wait_for_active_connection_sync: {err_msg}")
                raise SidekickConnectionError(err_msg)

        logger.info("wait_for_active_connection_sync: Activation successful and service is active.")


    def is_active(self) -> bool:
        """Checks if the ConnectionService is fully active and ready for use.

        Returns:
            bool: True if the service status is `ACTIVE`, False otherwise.
        """
        with self._status_lock:
            return self._service_status == _ServiceStatus.ACTIVE


    def send_message_internally(self, message_dict: Dict[str, Any]) -> None:
        """
        Sends a Sidekick protocol message. Ensures activation is initiated if needed,
        and queues messages if the service is not yet fully active.
        This is the internal method called by the module-level `send_message()`
        in `sidekick.connection`.

        Args:
            message_dict (Dict[str, Any]): The Sidekick protocol message to send.

        Raises:
            SidekickDisconnectedError: If the service is in a state (e.g., FAILED,
                                       SHUTTING_DOWN) where messages cannot be
                                       queued or sent.
            TypeError: If the `message_dict` is not JSON serializable (though
                       this is usually caught by `json.dumps`).
        """
        self.activate_connection_internally() # Non-blocking, ensures activation is scheduled

        with self._status_lock:
            is_ready_for_direct_send = self._clearall_sent_and_queue_processed_event and \
                                       self._clearall_sent_and_queue_processed_event.is_set() and \
                                       self._service_status == _ServiceStatus.ACTIVE

            if not is_ready_for_direct_send:
                if self._service_status in [_ServiceStatus.FAILED, _ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                    logger.error(
                        f"Cannot send message, service status is {self._service_status.name}. Message dropped: {message_dict.get('type')}"
                    )
                    raise SidekickDisconnectedError(f"Service not active (status: {self._service_status.name}). Cannot send.")

                if len(self._message_queue) >= self._message_queue.maxlen: # type: ignore[arg-type] # pragma: no cover
                    dropped_msg = self._message_queue.popleft()
                    logger.error(f"Message queue full ({self._message_queue.maxlen}). Dropping oldest: type='{dropped_msg.get('type')}'")
                self._message_queue.append(message_dict)
                logger.debug(
                    f"Message type='{message_dict.get('type', 'N/A')}' target='{message_dict.get('target', 'N/A')}' "
                    f"queued (qsize: {len(self._message_queue)}). Waiting for full activation."
                )
                return

        comm_manager = self._communication_manager
        if not comm_manager or not comm_manager.is_connected(): # pragma: no cover
            logger.critical("send_message_internally: CRITICAL STATE - Service active but CM unavailable/disconnected.")
            with self._status_lock:
                self._message_queue.append(message_dict)
                if self._clearall_sent_and_queue_processed_event: self._clearall_sent_and_queue_processed_event.clear()
                self._service_status = _ServiceStatus.CORE_CONNECTED
            raise SidekickDisconnectedError("Internal state inconsistency: Service active but CM not ready for send.")

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


    def _send_hero_offline_if_needed(self) -> Optional[asyncio.Task]:
        """Sends a hero 'offline' announce message if appropriate conditions are met.

        This is typically called during the shutdown sequence.

        Returns:
            Optional[asyncio.Task]: The task object for the send operation if it
                                    was submitted, otherwise None.
        """
        task: Optional[asyncio.Task] = None
        comm_manager_ref: Optional[CommunicationManager] = None
        can_send = False

        with self._status_lock:
            comm_manager_ref = self._communication_manager
            if comm_manager_ref and comm_manager_ref.is_connected() and \
               self._service_status not in [_ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.FAILED, _ServiceStatus.IDLE, _ServiceStatus.ACTIVATING_SCHEDULED]:
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
                self._task_manager.ensure_loop_running()
                task = self._task_manager.submit_task(
                    comm_manager_ref.send_message_async(json.dumps(hero_offline_announce))
                )
            except (CoreTaskSubmissionError, CoreLoopNotRunningError, AttributeError) as e:  # pragma: no cover
                logger.warning(f"Could not submit hero 'offline' announce task during shutdown: {e}")
        else:
            logger.debug("Skipping send_hero_offline: CM not connected or service state inappropriate.")
        return task


    def _handle_core_message(self, message_str: str) -> None:
        """
        Callback for the underlying `CommunicationManager` to handle raw messages
        received from the transport layer (e.g., WebSocket).

        This method:
        1. Deserializes the JSON message string.
        2. Invokes the user-registered global message handler (if any).
        3. Processes `system/announce` messages to track Sidekick UI peer status,
           setting the `_sidekick_ui_online_event` when a UI announces itself.
        4. Routes `event` or `error` messages to the appropriate component-specific
           handler based on the `src` (instance_id) in the message.

        Args:
            message_str (str): The raw JSON message string received from the transport.
        """
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
                         try:
                             loop_for_event_set = self._task_manager.get_loop()
                             if loop_for_event_set and not loop_for_event_set.is_closed():
                                 loop_for_event_set.call_soon_threadsafe(self._sidekick_ui_online_event.set)
                             else: # pragma: no cover
                                 logger.error("Cannot set _sidekick_ui_online_event: TaskManager loop is not available or closed.")
                         except Exception as e_set_event: # pragma: no cover
                              logger.error(f"Error setting _sidekick_ui_online_event from _handle_core_message: {e_set_event}")

                elif status == "offline": # pragma: no cover
                    logger.info(f"Received 'sidekick offline' announce from peer: {peer_id}")
                    with self._status_lock: removed_peer = self._sidekick_peers_info.pop(peer_id, None)
                    if removed_peer and not self._sidekick_peers_info:
                        logger.info("All known Sidekick UIs are now offline.")
                        if self._sidekick_ui_online_event and self._sidekick_ui_online_event.is_set():
                            try:
                                loop_for_event_set = self._task_manager.get_loop()
                                if loop_for_event_set and not loop_for_event_set.is_closed():
                                    loop_for_event_set.call_soon_threadsafe(self._sidekick_ui_online_event.clear)
                                else:  # pragma: no cover
                                    logger.error("Cannot clear _sidekick_ui_online_event: TaskManager loop is not available or closed.")
                            except Exception as e_clear_event: # pragma: no cover
                                 logger.error(f"Error clearing _sidekick_ui_online_event: {e_clear_event}")
                        print("Sidekick UI has disconnected. Shutting down Sidekick Python client.")
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
        """
        Callback for the underlying `CommunicationManager` to report changes in its
        low-level connection status (e.g., WebSocket connected, disconnected, error).

        This method updates the `ConnectionService`'s internal status accordingly
        and sets/clears related asyncio events used for the activation sequence.
        For instance, if `core_status` becomes `CONNECTED`, it sets
        `_core_transport_connected_event`. If it becomes `DISCONNECTED` or `ERROR`,
        it updates service status to `FAILED` (if not already shutting down) and
        may signal synchronous waiters about the failure.

        Args:
            core_status (CoreConnectionStatus): The new status from the `CommunicationManager`.
        """
        logger.info(f"ConnectionService processing core CM status change: {core_status.name}")
        status_changed_by_this_call = False
        original_service_status_for_log = self._service_status

        with self._status_lock:
            current_s_status = self._service_status
            if core_status == CoreConnectionStatus.CONNECTED:
                if current_s_status == _ServiceStatus.ACTIVATING_SCHEDULED or \
                   (self._communication_manager and self._communication_manager.is_connected() and \
                    current_s_status not in [_ServiceStatus.CORE_CONNECTED, _ServiceStatus.WAITING_SIDEKICK_ANNOUNCE, _ServiceStatus.ACTIVE]):
                    if self._service_status != _ServiceStatus.CORE_CONNECTED:
                        self._service_status = _ServiceStatus.CORE_CONNECTED
                        status_changed_by_this_call = True
                        logger.info("Service status advanced to CORE_CONNECTED (transport layer active).")
                    if self._core_transport_connected_event and not self._core_transport_connected_event.is_set(): # type: ignore
                        try:
                            loop = self._core_transport_connected_event._loop # type: ignore
                            loop.call_soon_threadsafe(self._core_transport_connected_event.set)
                        except Exception: pass # Best effort

            elif core_status in [CoreConnectionStatus.DISCONNECTED, CoreConnectionStatus.ERROR]:
                logger.warning(f"Core communication channel reported {core_status.name}.")
                if self._core_transport_connected_event and self._core_transport_connected_event.is_set(): # type: ignore
                    try:
                        loop = self._core_transport_connected_event._loop # type: ignore
                        loop.call_soon_threadsafe(self._core_transport_connected_event.clear)
                    except Exception: pass

                if current_s_status not in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.IDLE, _ServiceStatus.FAILED]:
                    self._service_status = _ServiceStatus.FAILED
                    status_changed_by_this_call = True
                    logger.error(f"Service status changed to FAILED due to core channel {core_status.name}.")

                    # This error might occur during activation or after.
                    # Store it so wait_for_active_connection_sync can pick it up.
                    if not self._activation_exception:
                        self._activation_exception = SidekickDisconnectedError(f"Core channel reported {core_status.name}.")

                    # Clear other activation events if they were set
                    if self._sidekick_ui_online_event and self._sidekick_ui_online_event.is_set(): # type: ignore
                        try:
                            loop = self._sidekick_ui_online_event._loop # type: ignore
                            loop.call_soon_threadsafe(self._sidekick_ui_online_event.clear)
                        except Exception: pass
                    if self._clearall_sent_and_queue_processed_event and self._clearall_sent_and_queue_processed_event.is_set(): # type: ignore
                         try:
                            loop = self._clearall_sent_and_queue_processed_event._loop # type: ignore
                            loop.call_soon_threadsafe(self._clearall_sent_and_queue_processed_event.clear)
                         except Exception: pass

                    # If an async activation task is running, its done_callback will handle setting
                    # the _sync_activation_complete_event. If not (e.g. disconnect after activation),
                    # and a sync waiter might exist (unlikely here), then set it.
                    if not (self._async_activate_task and not self._async_activate_task.done()):
                        if not self._sync_activation_complete_event.is_set():
                            logger.debug(f"_handle_core_status_change: Setting _sync_activation_complete_event due to FAILED status without active activation task.")
                            self._sync_activation_complete_event.set()


            if status_changed_by_this_call:
                logger.debug(f"Service status transition: {original_service_status_for_log.name} -> {self._service_status.name} (due to core status: {core_status.name})")


    def _handle_core_error(self, exc: Exception) -> None: # pragma: no cover
        """
        Callback for the underlying `CommunicationManager` to report unexpected
        errors that occur within its operations (e.g., an unhandled exception
        in its listener loop or send mechanism).

        This method updates the `ConnectionService` status to `FAILED`, stores
        the exception, and ensures synchronous waiters are notified.

        Args:
            exc (Exception): The exception reported by the `CommunicationManager`.
        """
        logger.error(f"ConnectionService received critical core CM error: {type(exc).__name__}: {exc}")
        # status_changed_by_this_call = False # Not used in this version
        with self._status_lock:
            if self._service_status not in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE, _ServiceStatus.IDLE, _ServiceStatus.FAILED]:
                self._service_status = _ServiceStatus.FAILED
                # status_changed_by_this_call = True # Not used
                logger.error(f"Service status changed to FAILED due to core CM error: {exc}")
                if not self._activation_exception:
                    self._activation_exception = SidekickConnectionError(f"Core CM error: {exc}", original_exception=exc)

                # Clear asyncio events safely
                def clear_event_threadsafe(event: Optional[asyncio.Event]):
                    if event and event.is_set():
                        try:
                            loop = event._loop # type: ignore
                            loop.call_soon_threadsafe(event.clear)
                        except Exception: pass

                clear_event_threadsafe(self._core_transport_connected_event)
                clear_event_threadsafe(self._sidekick_ui_online_event)
                clear_event_threadsafe(self._clearall_sent_and_queue_processed_event)

                # Ensure sync event is set if activation was ongoing or might have waiters
                if not (self._async_activate_task and not self._async_activate_task.done()):
                    if not self._sync_activation_complete_event.is_set():
                        logger.debug(f"_handle_core_error: Setting _sync_activation_complete_event due to FAILED status without active activation task.")
                        self._sync_activation_complete_event.set()


    def register_component_message_handler(self, instance_id: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Registers a message handler for a specific component instance ID.

        Args:
            instance_id (str): The unique ID of the component instance.
            handler (Callable[[Dict[str, Any]], None]): The function to call when a
                message for this instance_id is received from the UI.

        Raises:
            ValueError: If `instance_id` is empty or not a string.
            TypeError: If `handler` is not a callable function.
        """
        if not isinstance(instance_id, str) or not instance_id:
            raise ValueError("instance_id must be a non-empty string.")
        if not callable(handler):
            raise TypeError("handler must be a callable function.")
        if instance_id in self._component_message_handlers: # pragma: no cover
            logger.warning(f"Handler already registered for instance_id: {instance_id}. Overwriting.")
        self._component_message_handlers[instance_id] = handler
        logger.debug(f"Registered component message handler for instance_id: {instance_id}")

    def unregister_component_message_handler(self, instance_id: str) -> None:
        """Unregisters a message handler for a specific component instance ID.

        Args:
            instance_id (str): The unique ID of the component instance whose
                               handler should be unregistered.
        """
        if self._component_message_handlers.pop(instance_id, None):
            logger.debug(f"Unregistered component message handler for instance_id: {instance_id}")

    def clear_all_ui_components(self) -> None:
        """Sends a command to remove all components from the Sidekick UI panel.

        This effectively resets the UI panel to its initial empty state.
        The command is queued if the service is not yet active.
        """
        logger.info("Requesting ConnectionService to clear all UI components.")
        self.send_message_internally({"id": 0, "component": "global", "type": "clearAll"})


    def shutdown_service(self) -> None:
        """Initiates a graceful shutdown of the ConnectionService.

        This process involves:
        1. Setting the service status to `SHUTTING_DOWN`.
        2. Cancelling any ongoing asynchronous activation task.
        3. Setting the synchronous activation completion event to unblock any waiters,
           marking the shutdown with an exception if appropriate.
        4. Clearing any queued messages.
        5. Sending a "hero offline" `system/announce` message to the UI (best effort).
        6. Closing the underlying `CommunicationManager` (e.g., WebSocket connection).
        7. Signaling the `TaskManager` to shut down its event loop.
        8. Clearing internal state (component handlers, peer info).
        9. Setting the service status to `SHUTDOWN_COMPLETE`.
        """
        offline_task_handle: Optional[asyncio.Task] = None
        comm_close_task_handle: Optional[asyncio.Task] = None

        with self._status_lock:
            if self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                logger.debug(f"Shutdown already in progress or complete (status: {self._service_status.name}).")
                return
            logger.info(f"ConnectionService shutdown initiated. Current status: {self._service_status.name}")
            original_status_before_shutdown = self._service_status
            self._service_status = _ServiceStatus.SHUTTING_DOWN

            if self._async_activate_task and not self._async_activate_task.done():
                logger.debug("Cancelling active _async_activate_task during shutdown.")
                self._async_activate_task.cancel()
                # The _activation_done_callback will be called due to cancellation,
                # which will set _sync_activation_complete_event and store CancelledError.

            # If activation wasn't ongoing, but a waiter might exist (e.g. if shutdown called
            # externally before wait_for_connection completes but after task is done),
            # ensure the sync event is set.
            if not self._sync_activation_complete_event.is_set():
                 logger.debug("shutdown_service: Explicitly setting _sync_activation_complete_event to unblock potential waiters.")
                 if not self._activation_exception: # Don't overwrite a more specific exception
                      self._activation_exception = SidekickError("Service is shutting down.")
                 self._sync_activation_complete_event.set()


            if self._message_queue: # pragma: no cover
                logger.info(f"Clearing {len(self._message_queue)} messages from queue due to shutdown.")
                self._message_queue.clear()

            # Safely clear asyncio events if their loop is running
            tm_loop = self._task_manager.get_loop() if self._task_manager.is_loop_running() else None
            def _safe_clear_event(event: Optional[asyncio.Event], loop: Optional[asyncio.AbstractEventLoop]):
                if event and event.is_set() and loop and not loop.is_closed():
                    try: loop.call_soon_threadsafe(event.clear)
                    except Exception: pass # Best effort
                elif event: # If loop not available, just clear ref
                    event.clear() # May not be thread-safe if loop is gone, but best effort

            _safe_clear_event(self._core_transport_connected_event, tm_loop)
            _safe_clear_event(self._sidekick_ui_online_event, tm_loop)
            _safe_clear_event(self._clearall_sent_and_queue_processed_event, tm_loop)


            offline_task_handle = self._send_hero_offline_if_needed()

            comm_manager_to_close = self._communication_manager
            if comm_manager_to_close:
                logger.debug("Scheduling CommunicationManager.close_async().")
                try:
                    self._task_manager.ensure_loop_running() # Loop needed for submitting close task
                    comm_close_task_handle = self._task_manager.submit_task(comm_manager_to_close.close_async())
                except (CoreTaskSubmissionError, CoreLoopNotRunningError) as e: # pragma: no cover
                    logger.warning(f"Could not submit CM close task during shutdown: {e}")

        # Await sub-tasks if possible (best effort for synchronous shutdown_service)
        # This part is complex if shutdown_service is called from a sync context.
        # For now, these tasks are mostly fire-and-forget from a sync shutdown_service call.
        # A more robust shutdown might involve a dedicated async shutdown method.
        # If called from the event loop, one could `await asyncio.gather`.

        logger.debug("Signaling TaskManager to shutdown (from ConnectionService.shutdown_service).")
        self._task_manager.signal_shutdown()

        with self._status_lock:
            self._component_message_handlers.clear()
            self._user_global_message_handler = None
            self._sidekick_peers_info.clear()
            self._communication_manager = None
            self._connected_server_name = None
            self._service_status = _ServiceStatus.SHUTDOWN_COMPLETE
            logger.info(f"ConnectionService shutdown sequence finalized. Status transitioned from {original_status_before_shutdown.name} to SHUTDOWN_COMPLETE.")
            # Ensure sync event is set again, just in case it was missed or cleared by other logic.
            if not self._sync_activation_complete_event.is_set():
                 if not self._activation_exception: self._activation_exception = SidekickError("Service shut down post-sync-event-check.")
                 self._sync_activation_complete_event.set()


    def run_service_forever(self) -> None:
        """Blocks and keeps the service running until shutdown.
        (Intended for CPython specific use via `sidekick.run_forever()`).

        This method first ensures the connection is active by calling
        `wait_for_active_connection_sync()`. If successful, it then waits
        for the `TaskManager` to signal its shutdown.
        Handles exceptions and ensures `shutdown_service()` is called.
        """
        if is_pyodide(): # pragma: no cover
            logger.error("run_service_forever() is synchronous and not intended for Pyodide. Use run_service_forever_async().")
            try: self.activate_connection_internally()
            except SidekickError: pass
            return

        try:
            # This call will block the main thread until connection is active or fails/times out.
            self.wait_for_active_connection_sync()

            logger.info("Sidekick connection active. Entering run_forever main loop (waiting for TaskManager shutdown).")
            self._task_manager.wait_for_shutdown()

        except SidekickTimeoutError as e_timeout:
            logger.error(f"Sidekick connection timed out for run_forever: {e_timeout}. Service will not run.")
        except SidekickConnectionError as e_conn:
            logger.error(f"Sidekick connection could not be established for run_forever: {e_conn}. Service will not run.")
        except KeyboardInterrupt: # pragma: no cover
            logger.info("KeyboardInterrupt in run_forever. Initiating shutdown.")
        except Exception as e: # pragma: no cover
            logger.exception(f"Unexpected error in run_forever: {e}. Shutting down.")
        finally:
            with self._status_lock:
                is_already_terminal = self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]

            if not is_already_terminal:
                logger.info("run_service_forever exiting. Initiating shutdown_service if not already in progress.")
                self.shutdown_service()
            else:
                if self._task_manager and self._task_manager.is_loop_running(): # pragma: no cover
                    logger.debug("run_service_forever: Ensuring TaskManager's own wait_for_shutdown can complete.")
                    try: self._task_manager.wait_for_shutdown()
                    except Exception: pass # Suppress errors if TM already shutting down

            logger.info("ConnectionService run_forever (CPython) finished.")


    async def run_service_forever_async(self) -> None:
        """Keeps the service running asynchronously until shutdown.
        (Intended for Pyodide/Async use via `await sidekick.run_forever_async()`).

        This method first ensures the connection activation is initiated and
        awaits its completion. If successful, it then awaits the `TaskManager`'s
        shutdown signal. Handles exceptions and ensures `shutdown_service()` is called.
        """
        try:
            self.activate_connection_internally() # Non-blocking, schedules activation

            current_activation_task_ref: Optional[asyncio.Task] = None
            with self._status_lock:
                current_activation_task_ref = self._async_activate_task

            if current_activation_task_ref and not current_activation_task_ref.done():
                logger.debug("run_service_forever_async: Awaiting completion of current activation task.")
                try:
                    await asyncio.wait_for(current_activation_task_ref, timeout=_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON)
                except asyncio.TimeoutError: # pragma: no cover
                    logger.error(f"run_service_forever_async: Timeout waiting for activation task to complete.")
                    with self._status_lock: # Ensure status reflects timeout if not already FAILED
                        if self._service_status != _ServiceStatus.FAILED: self._service_status = _ServiceStatus.FAILED
                    raise SidekickTimeoutError(f"Async activation timed out after {_ACTIVATION_FULL_TIMEOUT_SECONDS_CPYTHON}s.")
                except asyncio.CancelledError: # pragma: no cover
                    logger.info("run_service_forever_async: Activation task was cancelled during wait.")
                    with self._status_lock:
                         if self._service_status != _ServiceStatus.FAILED and \
                            self._service_status not in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                             self._service_status = _ServiceStatus.FAILED
                    raise

            with self._status_lock: service_is_active_final_check = (self._service_status == _ServiceStatus.ACTIVE)

            if service_is_active_final_check:
                logger.info("ConnectionService is ACTIVE. Entering run_service_forever_async wait state (waiting for TaskManager shutdown signal).")
                await self._task_manager.wait_for_shutdown_async()
            else:
                # If activation failed, an exception should have been raised from the await above.
                # If not, this is an unexpected state.
                with self._status_lock: current_status_for_error = self._service_status.name
                if not self._activation_exception: # Check if an exception was already raised by activation task
                    raise SidekickConnectionError(f"Service not active (status: {current_status_for_error}) for run_forever_async and no prior exception.")
                else: # If an exception was stored, re-raise it or a general error
                    if isinstance(self._activation_exception, SidekickError):
                        raise self._activation_exception
                    raise SidekickConnectionError(f"Service not active (status: {current_status_for_error}) due to prior activation error: {self._activation_exception}")


        except KeyboardInterrupt: # pragma: no cover
            logger.info("KeyboardInterrupt (async context). Initiating shutdown.")
        except SidekickConnectionError as e_conn_async: # pragma: no cover
            logger.error(f"Connection error in run_service_forever_async: {e_conn_async}. Shutting down.")
        except asyncio.CancelledError: # pragma: no cover
            logger.info("run_service_forever_async was cancelled. Initiating shutdown.")
        except Exception as e_async_main: # pragma: no cover
            logger.exception(f"Unexpected error in run_service_forever_async: {e_async_main}. Shutting down.")
        finally:
            with self._status_lock:
                is_already_terminal = self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]

            if not is_already_terminal:
                logger.info("run_service_forever_async exiting. Initiating shutdown_service if not already in progress.")
                self.shutdown_service() # This is sync, but called from finally. Might need async shutdown path in future.
            else:
                if self._task_manager and self._task_manager.is_loop_running(): # pragma: no cover
                    logger.debug("run_service_forever_async: Ensuring TaskManager's own wait_for_shutdown_async can complete.")
                    try: await self._task_manager.wait_for_shutdown_async()
                    except Exception: pass

            logger.info("ConnectionService run_service_forever_async finished.")


    def register_user_global_message_handler(self, handler: Optional[Callable[[Dict[str, Any]], None]]) -> None:
        """Registers a user-defined global handler for all incoming messages from the UI.

        Args:
            handler (Optional[Callable[[Dict[str, Any]], None]]): The function to call.
                Pass `None` to clear the handler.
        """
        if handler is not None and not callable(handler): # pragma: no cover
            raise TypeError("Global message handler must be a callable function or None.")
        self._user_global_message_handler = handler
        logger.info(f"User global message handler {'set' if handler else 'cleared'}.")