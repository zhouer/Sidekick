"""Manages the high-level connection and communication service for Sidekick.

This module defines the `ConnectionService` class, which orchestrates the
communication between the Sidekick Python library and the Sidekick UI.

This implementation uses a command-based, event-loop-driven architecture.
External calls (e.g., from `sidekick.connection`) are converted into commands
and placed onto an `asyncio.Queue`. A single "master" coroutine, running in
the `TaskManager`'s event loop, processes these commands sequentially. This
ensures that all state modifications and I/O operations are centralized within
the event loop, significantly reducing threading complexity and race conditions.

The `ConnectionService` is responsible for:

- Managing the service's lifecycle via commands (ACTIVATE, SHUTDOWN).
- Handling the Sidekick-specific protocol handshake (announce, clearAll).
- Queuing and sending messages to the UI.
- Dispatching incoming UI events to the correct Python component handlers.
"""

import asyncio
import json
import threading
import time
import uuid
from collections import deque
from enum import Enum, auto
from typing import Dict, Any, Callable, Optional, Deque, Union, Coroutine

from . import _version
from . import logger
from .core import (
    get_task_manager,
    TaskManager,
    CommunicationManager,
    CoreConnectionStatus,
    CoreDisconnectedError,
    is_pyodide
)
from .exceptions import (
    SidekickConnectionError,
    SidekickTimeoutError,
    SidekickDisconnectedError,
    SidekickError
)
from .server_connector import ServerConnector, ConnectionResult

# --- Constants ---
_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS = 180.0
_MAX_INTERNAL_MESSAGE_QUEUE_SIZE = 1000
_ACTIVATION_SYNC_WAIT_TIMEOUT_SECONDS = 180.0

class _ServiceStatus(Enum):
    """Internal states for the ConnectionService lifecycle, managed by the master coroutine."""
    IDLE = auto()
    ACTIVATING = auto()
    ACTIVE = auto()
    FAILED = auto()
    SHUTTING_DOWN = auto()
    SHUTDOWN_COMPLETE = auto()

class _Command(Enum):
    """Commands that can be sent to the master coroutine's command queue."""
    ACTIVATE = auto()
    SEND_MESSAGE = auto()
    SHUTDOWN = auto()
    CLEAR_ALL = auto()
    REGISTER_HANDLER = auto()
    UNREGISTER_HANDLER = auto()
    REGISTER_GLOBAL_HANDLER = auto()
    # Internal commands submitted by CM callbacks to be processed by the master loop
    _PROCESS_RAW_MESSAGE = auto()
    _PROCESS_STATUS_CHANGE = auto()
    _PROCESS_ERROR = auto()


class ConnectionService:
    """Orchestrates Sidekick communication and manages the service lifecycle.

    This class is intended to be a singleton, accessed via `sidekick.connection`.
    It acts as a proxy, forwarding requests from the user's thread (e.g., main thread)
    as commands to a dedicated master coroutine running in the event loop. This
    design centralizes state management and I/O, preventing race conditions.
    """
    def __init__(self):
        """Initializes the ConnectionService and starts its master processing loop."""
        self._task_manager: TaskManager = get_task_manager()
        self._command_queue: asyncio.Queue = asyncio.Queue()

        # A lock to protect access to shared synchronization primitives and for
        # thread-safe reading of the service status.
        self._status_lock = threading.RLock()
        self._service_status: _ServiceStatus = _ServiceStatus.IDLE

        # For synchronizing `wait_for_active_connection_sync` with the async activation process.
        self._sync_activation_complete_event = threading.Event()
        # Holds an exception if the async activation process fails, to be re-raised in the sync waiter.
        self._activation_exception: Optional[BaseException] = None

        self._hero_peer_id: str = f"hero-py-{uuid.uuid4().hex}"

        # Start the master coroutine that will drive all state and I/O.
        self._master_task: asyncio.Task = self._task_manager.submit_task(self._master_loop_coro())
        self._master_task.add_done_callback(self._master_loop_done_callback)

        logger.info(f"ConnectionService initialized (Hero Peer ID: {self._hero_peer_id})")

    def _submit_command(self, command: tuple):
        """Submits a command to the master loop's queue using the TaskManager.

        This method is thread-safe. It wraps the `queue.put` coroutine in a task
        and submits it via the TaskManager. This ensures that the event loop is
        awakened to process the new command, even if called from a different thread.

        Args:
            command (tuple): The command and its arguments to be sent to the master loop.
        """
        try:
            # self._command_queue.put(command) is a coroutine.
            # Submitting it as a task ensures it's executed on the event loop.
            self._task_manager.submit_task(self._command_queue.put(command))
        except Exception as e: # pragma: no cover
            logger.error(f"Failed to submit command {command[0].name} to queue: {e}")

    def _master_loop_done_callback(self, task: asyncio.Task) -> None:
        """Callback for when the master coroutine finishes unexpectedly."""
        if not task.cancelled() and task.exception(): # pragma: no cover
            logger.critical(
                f"ConnectionService master coroutine terminated with an unhandled exception: {task.exception()}",
                exc_info=task.exception()
            )
        else:
            logger.info("ConnectionService master coroutine has finished.")

    async def _master_loop_coro(self) -> None:
        """The core coroutine that processes commands and manages service state."""
        # --- State variables owned exclusively by this coroutine ---
        status = _ServiceStatus.IDLE
        cm: Optional[CommunicationManager] = None
        server_connector = ServerConnector(self._task_manager)
        message_queue_internal: Deque[Dict[str, Any]] = deque(maxlen=_MAX_INTERNAL_MESSAGE_QUEUE_SIZE)
        component_handlers: Dict[str, Callable] = {}
        global_handler: Optional[Callable] = None
        sidekick_peers: Dict[str, Dict] = {}
        activation_task: Optional[asyncio.Task] = None

        def update_status(new_status: _ServiceStatus):
            """Atomically updates the internal and externally visible status."""
            nonlocal status
            if status == new_status: return
            logger.info(f"ConnectionService status changing from {status.name} to {new_status.name}")
            status = new_status
            with self._status_lock:
                self._service_status = new_status

        def activation_done_callback(task: asyncio.Task):
            """Callback for when the activation task completes."""
            nonlocal activation_task
            if not task.cancelled():
                if task_exc := task.exception():
                    with self._status_lock:
                        if not self._activation_exception: self._activation_exception = task_exc
            else: logger.debug("Activation task was cancelled, no exception stored from it.")
            # Always set the event to unblock any synchronous waiters.
            self._sync_activation_complete_event.set()
            activation_task = None

        async def perform_activation_sequence() -> None:
            """The coroutine that performs the actual connection and handshake logic."""
            nonlocal cm, sidekick_peers
            try:
                # 1. Connect using ServerConnector. It will try servers sequentially.
                conn_result: ConnectionResult = await server_connector.connect_async(
                    message_handler=lambda msg: self._submit_command((_Command._PROCESS_RAW_MESSAGE, msg)),
                    status_change_handler=lambda s: self._submit_command((_Command._PROCESS_STATUS_CHANGE, s)),
                    error_handler=lambda e: self._submit_command((_Command._PROCESS_ERROR, e))
                )
                cm = conn_result.communication_manager
                logger.info(f"Successfully connected to Sidekick server: {conn_result.server_name or 'Unknown'}")
                if conn_result.show_ui_url_hint and conn_result.ui_url_to_show:
                    print(f"Sidekick UI is available at: {conn_result.ui_url_to_show}")

                # 2. Perform Sidekick protocol handshake.
                hero_announce = { "id": 0, "component": "system", "type": "announce", "payload": { "peerId": self._hero_peer_id, "role": "hero", "status": "online", "version": _version.__version__, "timestamp": int(time.time() * 1000) }}
                await cm.send_message_async(json.dumps(hero_announce))

                sidekick_online_event = self._task_manager.create_event()
                sidekick_peers['_online_event_'] = sidekick_online_event
                if conn_result.show_ui_url_hint: print(f"Waiting up to {_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS:.0f}s for Sidekick UI...")

                await asyncio.wait_for(sidekick_online_event.wait(), timeout=_SIDEKICK_UI_WAIT_TIMEOUT_SECONDS)
                sidekick_peers.pop('_online_event_', None)
                if conn_result.show_ui_url_hint: print("Sidekick UI is connected.")

                # 3. Clear UI and process any messages that were queued during activation.
                await cm.send_message_async(json.dumps({"id": 0, "component": "global", "type": "clearAll"}))
                logger.info(f"Processing {len(message_queue_internal)} queued messages.")
                while message_queue_internal:
                    msg = message_queue_internal.popleft()
                    await cm.send_message_async(json.dumps(msg))

                # 4. Activation is complete.
                update_status(_ServiceStatus.ACTIVE)
            except asyncio.CancelledError:
                logger.info("Sidekick activation sequence was cancelled.")
                update_status(_ServiceStatus.FAILED)
                raise # Re-raise CancelledError to mark the task as cancelled.
            except Exception as e:
                # Catch any other failure during activation (e.g., connection errors, timeout).
                logger.error(f"Sidekick activation sequence failed: {e}", exc_info=(isinstance(e, SidekickError) or not isinstance(e, SidekickConnectionError)))
                update_status(_ServiceStatus.FAILED)
                raise # Re-raise exception to be stored by the done_callback.

        # --- Main command processing loop ---
        while status != _ServiceStatus.SHUTDOWN_COMPLETE:
            cmd, *args = await self._command_queue.get()
            try:
                if cmd == _Command.ACTIVATE:
                    if status in [_ServiceStatus.IDLE, _ServiceStatus.FAILED, _ServiceStatus.SHUTDOWN_COMPLETE]:
                        update_status(_ServiceStatus.ACTIVATING)
                        with self._status_lock: self._sync_activation_complete_event.clear(); self._activation_exception = None
                        if activation_task and not activation_task.done(): activation_task.cancel()
                        activation_task = self._task_manager.submit_task(perform_activation_sequence())
                        activation_task.add_done_callback(activation_done_callback)
                    else: logger.debug(f"Activate command ignored, status is {status.name}")

                elif cmd == _Command.SEND_MESSAGE:
                    message_dict, = args
                    if status == _ServiceStatus.ACTIVE and cm: await cm.send_message_async(json.dumps(message_dict))
                    elif status in [_ServiceStatus.ACTIVATING, _ServiceStatus.IDLE]: message_queue_internal.append(message_dict)
                    else: logger.warning(f"Message dropped, service status is {status.name}: {message_dict.get('type')}")

                elif cmd == _Command._PROCESS_RAW_MESSAGE:
                    msg_str, = args
                    try:
                        msg = json.loads(msg_str)
                        if global_handler: global_handler(msg)
                        if msg.get("component") == "system" and msg.get("type") == "announce":
                            payload = msg.get("payload", {})
                            peer_id, role, p_status = payload.get("peerId"), payload.get("role"), payload.get("status")
                            if role == "sidekick" and p_status == "online":
                                sidekick_peers[peer_id] = payload
                                if (online_event := sidekick_peers.get('_online_event_')): online_event.set()
                            elif role == "sidekick" and p_status == "offline":
                                if sidekick_peers.pop(peer_id, None): logger.info(f"Sidekick UI peer {peer_id} went offline.")
                        elif msg.get("type") in ["event", "error"]:
                            if (instance_id := msg.get("src")) in component_handlers: component_handlers[instance_id](msg)
                    except json.JSONDecodeError: logger.error(f"Failed to parse incoming JSON: {msg_str[:200]}")

                elif cmd == _Command._PROCESS_STATUS_CHANGE:
                    core_status, = args
                    if core_status in [CoreConnectionStatus.DISCONNECTED, CoreConnectionStatus.ERROR]:
                        logger.warning(f"Core communication channel reported {core_status.name}.")
                        if status == _ServiceStatus.ACTIVATING and activation_task and not activation_task.done():
                            logger.info(f"Cancelling activation task due to core channel status change: {core_status.name}")
                            activation_task.cancel()
                        elif status == _ServiceStatus.ACTIVE:
                            update_status(_ServiceStatus.FAILED)
                            with self._status_lock:
                                if not self._activation_exception: self._activation_exception = SidekickDisconnectedError(f"Core channel reported {core_status.name}.")
                                self._sync_activation_complete_event.set()

                elif cmd == _Command._PROCESS_ERROR:
                    exc, = args
                    if exc and status not in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]:
                        logger.error(f"Core communication error reported: {exc}")
                        if status == _ServiceStatus.ACTIVATING and activation_task and not activation_task.done():
                            activation_task.cancel()
                        elif status != _ServiceStatus.FAILED:
                            update_status(_ServiceStatus.FAILED)
                            with self._status_lock:
                                if not self._activation_exception: self._activation_exception = SidekickConnectionError(f"Core communication error: {exc}", original_exception=exc)
                                self._sync_activation_complete_event.set()

                elif cmd == _Command.REGISTER_HANDLER: component_handlers[args[0]] = args[1]
                elif cmd == _Command.UNREGISTER_HANDLER: component_handlers.pop(args[0], None)
                elif cmd == _Command.REGISTER_GLOBAL_HANDLER: global_handler = args[0]
                elif cmd == _Command.CLEAR_ALL:
                    if status == _ServiceStatus.ACTIVE and cm: await cm.send_message_async(json.dumps({"id": 0, "component": "global", "type": "clearAll"}))
                    else: logger.warning(f"clearAll command ignored, status is {status.name}")

                elif cmd == _Command.SHUTDOWN:
                    if status == _ServiceStatus.SHUTDOWN_COMPLETE: continue
                    logger.info("Master coroutine received SHUTDOWN command.")
                    break
            except Exception as e: # pragma: no cover
                logger.exception(f"Exception in master coroutine while processing command {cmd.name}: {e}")
                update_status(_ServiceStatus.FAILED)
                with self._status_lock: self._activation_exception = e; self._sync_activation_complete_event.set()

        # --- Shutdown sequence ---
        update_status(_ServiceStatus.SHUTTING_DOWN)
        if activation_task and not activation_task.done(): activation_task.cancel()
        if cm and cm.is_connected():
            try:
                offline = {"id": 0, "component": "system", "type": "announce", "payload": { "peerId": self._hero_peer_id, "role": "hero", "status": "offline", "version": _version.__version__, "timestamp": int(time.time() * 1000) }}
                await cm.send_message_async(json.dumps(offline))
            except Exception: pass
            await cm.close_async()
        component_handlers.clear(); message_queue_internal.clear(); sidekick_peers.clear(); global_handler = None
        self._task_manager.stop_loop()
        update_status(_ServiceStatus.SHUTDOWN_COMPLETE)
        with self._status_lock:
             if not self._activation_exception: self._activation_exception = SidekickError("Service shut down.")
             self._sync_activation_complete_event.set()
        logger.info("ConnectionService shutdown sequence complete.")

    def activate_connection_internally(self) -> None:
        """Schedules the activation of the Sidekick service."""
        self._submit_command((_Command.ACTIVATE,))

    def wait_for_active_connection_sync(self, timeout: Optional[float] = _ACTIVATION_SYNC_WAIT_TIMEOUT_SECONDS) -> None:
        """Blocks the calling thread until the service is active, or fails."""
        if is_pyodide(): raise RuntimeError("wait_for_active_connection_sync is not suitable for Pyodide.")
        self.activate_connection_internally()
        logger.debug(f"wait_for_active_connection_sync: Waiting for event (timeout: {timeout}s).")
        if not self._sync_activation_complete_event.wait(timeout=timeout):
            raise SidekickTimeoutError(f"Timeout waiting for Sidekick service activation ({timeout}s).")
        with self._status_lock:
            if self._activation_exception:
                exc = self._activation_exception
                if isinstance(exc, asyncio.CancelledError): raise SidekickError("Connection activation was cancelled.") from exc
                if isinstance(exc, SidekickError): raise exc
                raise SidekickConnectionError(f"Activation failed: {exc}", original_exception=exc) from exc
            if self._service_status != _ServiceStatus.ACTIVE:
                raise SidekickConnectionError(f"Activation completed but service not ACTIVE (status: {self._service_status.name}).")

    def is_active(self) -> bool:
        """Checks if the service is fully active."""
        with self._status_lock: return self._service_status == _ServiceStatus.ACTIVE

    def send_message_internally(self, message_dict: Dict[str, Any]) -> None:
        """Schedules a message to be sent to the UI, queueing if not yet active."""
        self.activate_connection_internally()
        self._submit_command((_Command.SEND_MESSAGE, message_dict))

    def register_component_message_handler(self, instance_id: str, handler: Callable) -> None:
        """Schedules the registration of a component message handler."""
        if not isinstance(instance_id, str) or not instance_id: raise ValueError("instance_id must be a non-empty string.")
        if not callable(handler): raise TypeError("handler must be a callable function.")
        self._submit_command((_Command.REGISTER_HANDLER, instance_id, handler))

    def unregister_component_message_handler(self, instance_id: str) -> None:
        """Schedules the un-registration of a component message handler."""
        self._submit_command((_Command.UNREGISTER_HANDLER, instance_id))

    def register_user_global_message_handler(self, handler: Optional[Callable]) -> None:
        """Schedules the registration of a global message handler."""
        if handler and not callable(handler): raise TypeError("Global handler must be callable.")
        self._submit_command((_Command.REGISTER_GLOBAL_HANDLER, handler))

    def clear_all_ui_components(self) -> None:
        """Schedules a command to clear all UI components."""
        self._submit_command((_Command.CLEAR_ALL,))

    def shutdown_service(self, wait: bool = False) -> None:
        """Schedules the shutdown of the service and optionally waits for it."""
        self._submit_command((_Command.SHUTDOWN,))
        if wait and not is_pyodide():
            logger.info("shutdown_service: Waiting for TaskManager to stop.")
            self._task_manager.wait_for_stop()

    def run_service_forever(self) -> None:
        """(CPython) Waits for connection and then for the service to be stopped."""
        if is_pyodide():
            logger.error("run_service_forever() is not intended for Pyodide."); return
        shutdown_initiated_by_interrupt = False
        try:
            self.wait_for_active_connection_sync()
            logger.info("Sidekick connection active. Entering run_forever (waiting for TaskManager stop).")
            self._task_manager.wait_for_stop()
        except SidekickError as e: logger.error(f"Sidekick service could not start for run_forever: {e}")
        except KeyboardInterrupt: logger.info("KeyboardInterrupt in run_forever."); shutdown_initiated_by_interrupt = True
        finally:
            with self._status_lock: is_shutting_down = self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]
            if not is_shutting_down:
                logger.info("run_service_forever exiting. Initiating shutdown.")
                self.shutdown_service(wait=not shutdown_initiated_by_interrupt)
            logger.info("ConnectionService run_forever (CPython) finished.")

    async def run_service_forever_async(self) -> None:
        """(Async) Waits for connection and then for a shutdown command."""
        try:
            self.activate_connection_internally()
            await self._master_task
        except asyncio.CancelledError: logger.info("run_service_forever_async cancelled.")
        finally:
            with self._status_lock: is_shutting_down = self._service_status in [_ServiceStatus.SHUTTING_DOWN, _ServiceStatus.SHUTDOWN_COMPLETE]
            if not is_shutting_down: self.shutdown_service(wait=False)
            logger.info("ConnectionService run_service_forever_async finished.")
