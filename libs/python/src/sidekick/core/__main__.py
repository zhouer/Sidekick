"""Minimal test program for sidekick.core components in a CPython environment.

This script directly uses the TaskManager and CommunicationManager to interact
with a Sidekick WebSocket server. It demonstrates:
1. Connecting to the server.
2. Sending a 'hero online' announcement.
3. Sending a 'clearAll' message.
4. Spawning a grid component.
5. Sending random color updates to the grid.
6. Sending a 'hero offline' announcement before closing.

To run this:
1. Ensure a Sidekick WebSocket server is running (e.g., from VS Code extension
   or a standalone test server) on the default URL (ws://localhost:5163).
2. Execute from the project root: `python -m sidekick.core`
"""
import asyncio
import concurrent.futures
import json
import logging
import random
import time
import uuid
from typing import Optional

from sidekick.core.task_manager import TaskManager
from sidekick.core.communication_manager import CommunicationManager
from sidekick.core.factories import get_task_manager, get_communication_manager
from sidekick.core.status import CoreConnectionStatus
from sidekick.core.exceptions import CoreConnectionError, CoreDisconnectedError, CoreConnectionRefusedError, CoreConnectionTimeoutError

# --- Configuration ---
LOG_LEVEL = logging.DEBUG
WEBSOCKET_URL = "ws://localhost:5163"
TEST_DURATION_SECONDS = 7 # Reduced for quicker testing
COLOR_UPDATE_INTERVAL_SECONDS = 0.2
GRID_COLS = 5
GRID_ROWS = 5
HERO_PEER_ID = f"test-hero-core-{uuid.uuid4().hex[:8]}" # Shorter UUID
SIDEKICK_VERSION = "0.0.0-core-test"

# --- Logging Setup ---
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s", # Added threadName
)
logger = logging.getLogger(__name__)


# --- Handler Functions ---
_sidekick_ui_online_event = asyncio.Event() # Used to wait for sidekick UI if needed

async def on_message_received(message_str: str) -> None:
    """Handles incoming messages from the server."""
    logger.info(f"<<< Received message: {message_str[:200]}{'...' if len(message_str) > 200 else ''}")
    try:
        msg = json.loads(message_str)
        if msg.get("component") == "system" and msg.get("type") == "announce":
            payload = msg.get("payload", {})
            if payload.get("role") == "sidekick" and payload.get("status") == "online":
                logger.info(f"Sidekick UI Peer '{payload.get('peerId')}' announced ONLINE (version: {payload.get('version')}).")
                _sidekick_ui_online_event.set()
    except json.JSONDecodeError: # pragma: no cover
        logger.error(f"Failed to parse incoming JSON: {message_str}")


async def on_status_changed(status: CoreConnectionStatus) -> None:
    """Handles connection status changes."""
    logger.info(f"Connection status changed to: {status.name}")
    # _connected_event logic removed, relying on connect_async completion/failure


async def on_error_received(error: Exception) -> None: # pragma: no cover
    """Handles errors from the communication manager."""
    logger.error(f"Communication manager reported error: {type(error).__name__}: {error}")


async def send_json_message_robustly(comm_manager: CommunicationManager, message_dict: dict, description: str):
    """Helper to send a dictionary as a JSON string message, with robustness for shutdown."""
    if not comm_manager.is_connected(): # pragma: no cover
        logger.warning(f"Cannot send '{description}': CommunicationManager not connected.")
        return

    try:
        json_str = json.dumps(message_dict)
        logger.info(f">>> Sending {description} (type: {message_dict.get('type', 'N/A')})")
        await comm_manager.send_message_async(json_str)
    except CoreDisconnectedError: # pragma: no cover
        logger.error(f"Failed to send '{description}': Disconnected during send attempt.")
    except RuntimeError as e: # pragma: no cover
        if "cannot schedule new futures after shutdown" in str(e).lower() or "Event loop is closed" in str(e).lower():
            logger.warning(f"Could not send '{description}', event loop shutting down: {e}")
        else:
            logger.exception(f"Runtime error sending '{description}': {e}")
    except Exception as e: # pragma: no cover
        logger.exception(f"Unexpected error sending '{description}': {e}")


async def run_core_test_sequence(task_manager: TaskManager, comm_manager: CommunicationManager):
    """The core asynchronous logic for the test script."""
    _sidekick_ui_online_event.clear() # Reset for this run

    comm_manager.register_message_handler(on_message_received)
    comm_manager.register_status_change_handler(on_status_changed)
    comm_manager.register_error_handler(on_error_received)

    logger.info("Attempting to connect CommunicationManager...")
    try:
        await comm_manager.connect_async() # Should raise on failure
        if not comm_manager.is_connected(): # Defensive check
             logger.error("connect_async returned but manager still not connected. Aborting.") # pragma: no cover
             return
        logger.info("CommunicationManager connect_async completed and reports connected.")
    except (CoreConnectionRefusedError, CoreConnectionTimeoutError, CoreConnectionError) as e:
        logger.error(f"Initial connection using CommunicationManager failed: {e}")
        return # Cannot proceed

    logger.info("Connection established by CommunicationManager. Starting message sequence.")
    grid_id = f"coretest-grid-{random.randint(1000, 9999)}"

    try:
        # 1. Send hero online
        hero_online_announce = {
            "id": 0, "component": "system", "type": "announce",
            "payload": {
                "peerId": HERO_PEER_ID, "role": "hero", "status": "online",
                "version": SIDEKICK_VERSION, "timestamp": int(time.time() * 1000)
            }
        }
        await send_json_message_robustly(comm_manager, hero_online_announce, "Hero Online Announce")

        # Optional: Wait for Sidekick UI to announce itself if testing bi-directional init
        # try:
        #     logger.info("Waiting briefly for Sidekick UI 'online' announce...")
        #     await asyncio.wait_for(_sidekick_ui_online_event.wait(), timeout=2.0)
        # except asyncio.TimeoutError:
        #     logger.warning("Did not receive Sidekick UI 'online' announce within timeout (this is okay for core test).")

        # 2. Send clearAll
        clear_all_msg = {"id": 0, "component": "global", "type": "clearAll"}
        await send_json_message_robustly(comm_manager, clear_all_msg, "ClearAll")

        # 3. Spawn grid
        spawn_grid_msg = {
            "id": 0, "component": "grid", "type": "spawn", "target": grid_id,
            "payload": {"numColumns": GRID_COLS, "numRows": GRID_ROWS}
        }
        await send_json_message_robustly(comm_manager, spawn_grid_msg, "Spawn Grid")

        # 4. Randomly color cells for a duration
        logger.info(f"Sending color updates for {TEST_DURATION_SECONDS} seconds...")
        start_time = time.monotonic()
        colors = ["red", "green", "blue", "yellow", "purple", "orange", "cyan", "magenta", "lightgray"]
        color_updates_sent = 0
        while (time.monotonic() - start_time) < TEST_DURATION_SECONDS:
            if not comm_manager.is_connected(): # pragma: no cover
                logger.warning("Disconnected during color update loop.")
                break
            update_color_msg = {
                "id": 0, "component": "grid", "type": "update", "target": grid_id,
                "payload": {
                    "action": "setColor",
                    "options": {
                        "color": random.choice(colors),
                        "x": random.randint(0, GRID_COLS - 1),
                        "y": random.randint(0, GRID_ROWS - 1)
                    }
                }
            }
            # Submit as a fire-and-forget task to not block the loop if send is slow,
            # but for this test, direct await is fine to ensure order.
            await send_json_message_robustly(comm_manager, update_color_msg, f"Grid SetColor {color_updates_sent + 1}")
            color_updates_sent += 1
            await asyncio.sleep(COLOR_UPDATE_INTERVAL_SECONDS) # Next await point for cancellation
        logger.info(f"Sent {color_updates_sent} color updates.")

    except asyncio.CancelledError: # pragma: no cover
        logger.info("run_core_test_sequence task was cancelled.")
        # Allow finally block to run for cleanup
    except CoreDisconnectedError: # pragma: no cover
        logger.error("Disconnected during test message sequence.")
    except Exception as e: # pragma: no cover
        logger.exception(f"An error occurred during the test message sequence: {e}")
    finally:
        logger.info("run_core_test_sequence: Entering finally block for cleanup.")
        # The actual sending of offline and closing of CM will be handled by
        # tm.signal_shutdown() -> _run_loop_in_thread's finally -> which cancels this task (main_test_logic)
        # and also CM's listener task.
        # The CM's listener, upon cancellation, should close its WebSocket if it's a client.
        # Or, ConnectionService would typically handle sending offline and closing CM.
        # For this core test, we rely on the TaskManager's shutdown to trigger CM listener's cleanup.
        # The "hero offline" sending is more of an application-level concern.
        if comm_manager and task_manager.is_loop_running():
            # Best effort to schedule CM close, TM will try to run it if loop is still up
            logger.info("run_core_test_sequence finally: Scheduling CommunicationManager close (fire and forget).")
            await task_manager.submit_task(comm_manager.close_async())
            # No sleeps, no awaiting these tasks here. Let this task (main_test_logic) finish.

        logger.info("Core test logic sequence (main_test_logic task) fully completed its finally block.")

if __name__ == "__main__":
    logger.info("Starting Sidekick Core CPython Test Program...")
    main_task_future: Optional[concurrent.futures.Future] = None
    tm = get_task_manager()
    comm = None # Initialize comm to None

    try:
        tm.ensure_loop_running()
        comm = get_communication_manager(ws_url=WEBSOCKET_URL) # Get CM instance

        logger.info("Submitting main_test_logic to TaskManager via submit_and_wait...")
        # submit_and_wait blocks the main thread until main_test_logic completes or errors.
        # KeyboardInterrupt during this wait is handled inside submit_and_wait.
        tm.submit_and_wait(run_core_test_sequence(tm, comm))
        logger.info("main_test_logic successfully completed via submit_and_wait.")

    except KeyboardInterrupt: # pragma: no cover
        logger.info("__main__: KeyboardInterrupt received. Main thread terminating.")
        # submit_and_wait should have called tm.signal_shutdown() already.
        # If not, or for belt-and-suspenders:
        # if tm and not tm._sync_shutdown_wait_event.is_set(): # Accessing internal for test clarity
        #    logger.info("__main__: Ensuring TM shutdown is signaled due to KI.")
        #    tm.signal_shutdown()
    except CoreConnectionError as e_conn_main: # pragma: no cover
        logger.error(f"__main__: Test failed due to CoreConnectionError: {e_conn_main}")
    except Exception as e_main: # pragma: no cover
        logger.exception(f"__main__: Test failed with an unexpected error: {e_main}")
    finally:
        logger.info("__main__: Entering final shutdown phase.")
        if tm: # Ensure tm was initialized
            # tm.signal_shutdown() ensures that the async loop and its thread know to stop.
            # It's okay to call this multiple times.
            logger.info("__main__: Signaling TaskManager to shutdown (finally block).")
            tm.signal_shutdown()

            # tm.wait_for_shutdown() blocks the main thread until the TaskManager's
            # loop thread has fully completed its cleanup and exited.
            # This is important for a clean exit of the main script.
            logger.info("__main__: Waiting for TaskManager to complete shutdown...")
            tm.wait_for_shutdown()
            logger.info("__main__: TaskManager shutdown complete.")
        else: # pragma: no cover
            logger.info("__main__: TaskManager was not initialized. Skipping TM shutdown calls.")

        logger.info("Sidekick Core CPython Test Program finished execution.")
