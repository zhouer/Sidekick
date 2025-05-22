"""Minimal test program for sidekick.core components in a CPython environment.

This script directly uses the TaskManager and a WebSocketCommunicationManager
to interact with a Sidekick WebSocket server. It demonstrates:
1. Creating a TaskManager and a WebSocketCommunicationManager.
2. Connecting the CommunicationManager to the server.
3. Sending a 'hero online' announcement.
4. Sending a 'clearAll' message.
5. Spawning a grid component.
6. Sending random color updates to the grid.
7. Gracefully shutting down the managers.

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

# Import core components and factories
from sidekick.core.task_manager import TaskManager
from sidekick.core.communication_manager import CommunicationManager
from sidekick.core.factories import get_task_manager, create_websocket_communication_manager # MODIFIED
from sidekick.core.status import CoreConnectionStatus
from sidekick.core.exceptions import (
    CoreConnectionError,
    CoreDisconnectedError,
    CoreConnectionRefusedError,
    CoreConnectionTimeoutError
)

# --- Configuration ---
LOG_LEVEL = logging.DEBUG
WEBSOCKET_URL = "ws://localhost:5163" # Target WebSocket server
TEST_DURATION_SECONDS = 7
COLOR_UPDATE_INTERVAL_SECONDS = 0.2
GRID_COLS = 5
GRID_ROWS = 5
HERO_PEER_ID = f"test-hero-core-{uuid.uuid4().hex[:8]}"
SIDEKICK_VERSION = "0.0.0-core-test"

# --- Logging Setup ---
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s",
)
logger = logging.getLogger("sidekick.core.main_test") # More specific logger name


# --- Handler Functions & State ---
_sidekick_ui_online_event = asyncio.Event() # Used to wait for sidekick UI if needed

async def on_message_received(message_str: str) -> None:
    """Handles incoming messages from the server."""
    logger.info(f"<<< Received message: {message_str[:200]}{'...' if len(message_str) > 200 else ''}")
    try:
        msg = json.loads(message_str)
        if msg.get("component") == "system" and msg.get("type") == "announce":
            payload = msg.get("payload", {})
            if payload.get("role") == "sidekick" and payload.get("status") == "online":
                logger.info(
                    f"Sidekick UI Peer '{payload.get('peerId')}' announced ONLINE "
                    f"(version: {payload.get('version')})."
                )
                _sidekick_ui_online_event.set()
    except json.JSONDecodeError: # pragma: no cover
        logger.error(f"Failed to parse incoming JSON: {message_str}")
    except Exception as e: # pragma: no cover
        logger.exception(f"Error in on_message_received: {e}")


async def on_status_changed(status: CoreConnectionStatus) -> None:
    """Handles connection status changes reported by the CommunicationManager."""
    logger.info(f"CommunicationManager status changed to: {status.name}")


async def on_error_received(error: Exception) -> None: # pragma: no cover
    """Handles errors reported by the CommunicationManager."""
    logger.error(f"CommunicationManager reported an error: {type(error).__name__}: {error}")


async def send_json_message_robustly(
    comm_manager: CommunicationManager,
    message_dict: dict,
    description: str
):
    """Helper to send a dictionary as a JSON string message.

    Includes checks for connection status and handles potential errors during sending,
    especially relevant during shutdown.
    """
    if not comm_manager.is_connected(): # pragma: no cover
        logger.warning(f"Cannot send '{description}': CommunicationManager is not connected.")
        return

    try:
        json_str = json.dumps(message_dict)
        # Log a summary of the message being sent.
        msg_type_info = message_dict.get('type', 'N/A')
        msg_comp_info = message_dict.get('component', 'N/A')
        logger.info(f">>> Sending {description} (component: {msg_comp_info}, type: {msg_type_info})")
        await comm_manager.send_message_async(json_str)
    except CoreDisconnectedError: # pragma: no cover
        logger.error(f"Failed to send '{description}': Disconnected during send attempt.")
    except RuntimeError as e: # pragma: no cover
        # Catch errors like "cannot schedule new futures after shutdown"
        if "cannot schedule new futures after shutdown" in str(e).lower() or \
           "Event loop is closed" in str(e).lower():
            logger.warning(f"Could not send '{description}', as event loop is shutting down: {e}")
        else:
            # Other RuntimeErrors
            logger.exception(f"A runtime error occurred while sending '{description}': {e}")
    except Exception as e: # pragma: no cover
        # Catch any other unexpected errors during the send process.
        logger.exception(f"An unexpected error occurred while sending '{description}': {e}")


async def run_core_test_sequence(task_manager: TaskManager, comm_manager: CommunicationManager):
    """The core asynchronous logic for the test script.

    This function performs the sequence of connecting, sending various messages,
    and then allows for cleanup.

    Args:
        task_manager: The TaskManager instance.
        comm_manager: The CommunicationManager instance to use for communication.
    """
    _sidekick_ui_online_event.clear() # Reset for this run

    # Register handlers with the CommunicationManager.
    comm_manager.register_message_handler(on_message_received)
    comm_manager.register_status_change_handler(on_status_changed)
    comm_manager.register_error_handler(on_error_received)

    logger.info(f"Attempting to connect CommunicationManager to {comm_manager._url if hasattr(comm_manager, '_url') else 'unknown URL'}...")
    try:
        # connect_async() should raise an appropriate CoreConnectionError on failure.
        await comm_manager.connect_async()
        if not comm_manager.is_connected(): # Defensive check, should not be needed if connect_async is robust
             logger.error("connect_async returned but CommunicationManager still not connected. Aborting test sequence.") # pragma: no cover
             return
        logger.info("CommunicationManager connect_async completed and reports connected.")
    except (CoreConnectionRefusedError, CoreConnectionTimeoutError, CoreConnectionError) as e:
        logger.error(f"Initial connection using CommunicationManager failed: {e}. Test sequence cannot proceed.")
        return # Cannot proceed if connection fails.

    logger.info("Connection established. Starting test message sequence.")
    grid_id = f"coretest-grid-{random.randint(1000, 9999)}"

    try:
        # 1. Send hero online announcement.
        hero_online_announce = {
            "id": 0, "component": "system", "type": "announce",
            "payload": {
                "peerId": HERO_PEER_ID, "role": "hero", "status": "online",
                "version": SIDEKICK_VERSION, "timestamp": int(time.time() * 1000)
            }
        }
        await send_json_message_robustly(comm_manager, hero_online_announce, "Hero Online Announce")

        # Optional: Wait for Sidekick UI to announce itself. This is useful for testing
        # bi-directional initialization but not strictly required for this core CM test.
        # try:
        #     logger.info("Waiting briefly for Sidekick UI 'online' announce...")
        #     await asyncio.wait_for(_sidekick_ui_online_event.wait(), timeout=2.0)
        # except asyncio.TimeoutError:
        #     logger.warning("Did not receive Sidekick UI 'online' announce within timeout (this is okay for core test).")

        # 2. Send global/clearAll message.
        clear_all_msg = {"id": 0, "component": "global", "type": "clearAll"}
        await send_json_message_robustly(comm_manager, clear_all_msg, "Global ClearAll")

        # 3. Spawn a grid component.
        spawn_grid_msg = {
            "id": 0, "component": "grid", "type": "spawn", "target": grid_id,
            "payload": {"numColumns": GRID_COLS, "numRows": GRID_ROWS}
        }
        await send_json_message_robustly(comm_manager, spawn_grid_msg, "Spawn Grid")

        # 4. Send random color updates to the grid for a specified duration.
        logger.info(f"Sending color updates to grid '{grid_id}' for {TEST_DURATION_SECONDS} seconds...")
        start_time = time.monotonic()
        colors = ["red", "green", "blue", "yellow", "purple", "orange", "cyan", "magenta", "lightgray", "pink"]
        color_updates_sent = 0
        while (time.monotonic() - start_time) < TEST_DURATION_SECONDS:
            if not comm_manager.is_connected(): # pragma: no cover
                logger.warning("Disconnected during color update loop. Stopping updates.")
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
            # For this test, direct await is fine to ensure order and observe behavior.
            await send_json_message_robustly(comm_manager, update_color_msg, f"Grid SetColor {color_updates_sent + 1}")
            color_updates_sent += 1
            # Allow other tasks to run and check for cancellation.
            await asyncio.sleep(COLOR_UPDATE_INTERVAL_SECONDS)
        logger.info(f"Finished sending color updates. Total updates sent: {color_updates_sent}.")

    except asyncio.CancelledError: # pragma: no cover
        logger.info("Core test sequence task (run_core_test_sequence) was cancelled.")
        # Allow the finally block to run for cleanup.
    except CoreDisconnectedError: # pragma: no cover
        logger.error("Disconnected during test message sequence. Aborting sequence.")
    except Exception as e: # pragma: no cover
        logger.exception(f"An unexpected error occurred during the test message sequence: {e}")
    finally:
        logger.info("run_core_test_sequence: Entering 'finally' block for cleanup.")
        # The CommunicationManager's close_async will be called by the main __main__ block's
        # finally clause, after the TaskManager signals shutdown and this task (run_core_test_sequence)
        # is awaited or cancelled.
        # We don't initiate CM close from here directly to avoid race conditions with TM shutdown.
        logger.info("Core test logic sequence (run_core_test_sequence task) has completed its 'finally' block.")


if __name__ == "__main__":
    logger.info("Starting Sidekick Core CPython Test Program...")
    tm: Optional[TaskManager] = None
    comm: Optional[CommunicationManager] = None

    try:
        tm = get_task_manager() # Get the singleton TaskManager
        tm.ensure_loop_running() # Start the TaskManager's event loop if not already running

        # Create a WebSocketCommunicationManager instance using the factory.
        # The TaskManager (tm) is passed to it.
        logger.info(f"Creating WebSocketCommunicationManager for URL: {WEBSOCKET_URL}")
        comm = create_websocket_communication_manager(url=WEBSOCKET_URL, task_manager=tm) # MODIFIED

        logger.info("Submitting main test logic (run_core_test_sequence) to TaskManager via submit_and_wait...")
        # submit_and_wait will block the main thread here until run_core_test_sequence completes or errors.
        # KeyboardInterrupt (Ctrl+C) during this wait is handled within submit_and_wait.
        tm.submit_and_wait(run_core_test_sequence(tm, comm))
        logger.info("Main test logic (run_core_test_sequence) successfully completed via submit_and_wait.")

    except KeyboardInterrupt: # pragma: no cover
        logger.info("__main__: KeyboardInterrupt received. Main thread will now terminate.")
        # tm.signal_shutdown() should have been called by submit_and_wait if KI happened there.
        # If KI happens before submit_and_wait, tm might not be fully shut down yet.
    except CoreConnectionError as e_conn_main: # pragma: no cover
        logger.error(f"__main__: Test failed due to a CoreConnectionError: {e_conn_main}")
    except Exception as e_main: # pragma: no cover
        logger.exception(f"__main__: Test failed with an unexpected error: {e_main}")
    finally:
        logger.info("__main__: Entering final shutdown phase.")
        if comm and tm and tm.is_loop_running(): # Check if comm was created and loop is still usable
            # Attempt graceful close of the CommunicationManager if it exists and was connected.
            # This should be done before TaskManager's full shutdown if possible.
            if comm.is_connected() or comm.get_current_status() == CoreConnectionStatus.CLOSING:
                logger.info("__main__: Attempting to close CommunicationManager gracefully...")
                try:
                    # Use submit_and_wait to ensure close_async completes before TM shutdown proceeds too far.
                    tm.submit_and_wait(comm.close_async())
                    logger.info("__main__: CommunicationManager close_async completed.")
                except Exception as e_close: # pragma: no cover
                    logger.error(f"__main__: Error during explicit CommunicationManager close: {e_close}")

        if tm: # Ensure tm was initialized
            logger.info("__main__: Signaling TaskManager to shutdown (from main finally block).")
            tm.signal_shutdown() # Ensures the async loop and its thread know to stop.

            logger.info("__main__: Waiting for TaskManager to complete its shutdown sequence...")
            tm.wait_for_shutdown() # Blocks main thread until TM's loop thread has fully exited.
            logger.info("__main__: TaskManager shutdown process complete.")
        else: # pragma: no cover
            logger.info("__main__: TaskManager was not initialized. Skipping TM shutdown calls.")

        logger.info("Sidekick Core CPython Test Program finished execution.")