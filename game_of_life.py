import time
import random
import threading
import copy # For deep copying the grid state
from typing import List, Dict, Any, Optional
from sidekick import (
    Grid,
    Control,
    Console, # Optional: for logging status
    ObservableValue, # Optional: could track generation count
    set_url,
    close_connection,
    # activate_connection
)
from sidekick import connection as sidekick_connection
import logging

# --- Configuration ---
GRID_WIDTH = 20
GRID_HEIGHT = 20
UPDATE_INTERVAL = 0.2  # Seconds between simulation steps
ALIVE_COLOR = 'black'
DEAD_COLOR = 'white'
SIDEKICK_URL = "ws://localhost:5163"
LOG_LEVEL = logging.INFO # DEBUG for more verbose output

# --- Setup Logging ---
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger("SidekickConn").setLevel(LOG_LEVEL)
logging.getLogger("GameOfLife").setLevel(LOG_LEVEL)
logger = logging.getLogger("GameOfLife")

# --- Global State ---
grid_module: Optional[Grid] = None
control_module: Optional[Control] = None
console_module: Optional[Console] = None # Optional console

# Game state: 0 = dead, 1 = alive
game_grid: List[List[int]] = []
previous_grid_state: List[List[int]] = [] # For optimized UI updates

simulation_running = False
simulation_thread: Optional[threading.Thread] = None
# Use threading.Event for safer start/stop signaling across threads
simulation_stop_event = threading.Event()

# --- Game Logic ---

def count_live_neighbors(x: int, y: int) -> int:
    """Counts live neighbors for a cell, wrapping around edges (toroidal)."""
    count = 0
    for i in range(-1, 2):
        for j in range(-1, 2):
            if i == 0 and j == 0:
                continue # Skip self
            # Calculate neighbor coordinates with wrap-around
            nx = (x + i + GRID_WIDTH) % GRID_WIDTH
            ny = (y + j + GRID_HEIGHT) % GRID_HEIGHT
            if game_grid[ny][nx] == 1:
                count += 1
    return count

def calculate_next_generation() -> List[List[int]]:
    """Computes the next state of the grid based on Conway's rules."""
    # Create a new grid for the next state to avoid modifying the current state during calculation
    next_grid = [[0 for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            live_neighbors = count_live_neighbors(x, y)
            current_state = game_grid[y][x]

            if current_state == 1: # Cell is alive
                if live_neighbors < 2 or live_neighbors > 3:
                    next_grid[y][x] = 0 # Dies (underpopulation or overpopulation)
                else:
                    next_grid[y][x] = 1 # Survives
            else: # Cell is dead
                if live_neighbors == 3:
                    next_grid[y][x] = 1 # Becomes alive (reproduction)
                else:
                    next_grid[y][x] = 0 # Stays dead
    return next_grid

def update_grid_ui(force_redraw=False):
    """Updates the Sidekick Grid UI based on the current game_grid state."""
    global previous_grid_state
    if not grid_module:
        return

    logger.debug("Updating Grid UI...")
    changed_cells = 0
    for y in range(GRID_HEIGHT):
        for x in range(GRID_WIDTH):
            # --- Optimization: Only update cells that changed state ---
            if force_redraw or game_grid[y][x] != previous_grid_state[y][x]:
                color = ALIVE_COLOR if game_grid[y][x] == 1 else DEAD_COLOR
                grid_module.set_color(x, y, color)
                changed_cells += 1

    logger.debug(f"Grid UI updated. Changed cells: {changed_cells}")
    # Update the previous state *after* sending commands for the difference
    previous_grid_state = copy.deepcopy(game_grid)


def randomize_grid():
    """Fills the game grid with a random pattern."""
    global game_grid
    logger.info("Randomizing grid state...")
    game_grid = [[random.choice([0, 1]) for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
    if console_module:
        console_module.log("Grid randomized.")

def clear_grid_state():
    """Clears the game grid state (all cells dead)."""
    global game_grid
    logger.info("Clearing grid state...")
    game_grid = [[0 for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
    if console_module:
        console_module.log("Grid cleared.")

# --- Simulation Thread ---

def run_simulation():
    """The main loop for the simulation thread."""
    global game_grid, simulation_running
    logger.info("Simulation thread started.")

    while not simulation_stop_event.is_set(): # Check event flag for stopping
        loop_start_time = time.time()

        # Calculate next state
        next_grid = calculate_next_generation()

        # Check again before potentially long UI update if we should stop
        if simulation_stop_event.is_set():
            break

        # Update game state
        game_grid = next_grid

        # Update UI (optimized)
        update_grid_ui()

        # Check again before sleeping
        if simulation_stop_event.is_set():
            break

        # Control update speed
        loop_duration = time.time() - loop_start_time
        sleep_time = max(0, UPDATE_INTERVAL - loop_duration)
        # Use event.wait for interruptible sleep
        simulation_stop_event.wait(timeout=sleep_time)

    logger.info("Simulation thread stopped.")
    # Ensure simulation_running flag is false when thread exits
    simulation_running = False # May need lock if accessed elsewhere critically


# --- Callback Functions ---

def handle_grid_click(msg: Dict[str, Any]):
    """Handles clicks on the Grid module."""
    global game_grid
    if simulation_running:
        logger.debug("Ignoring grid click while simulation is running.")
        if console_module: console_module.print("Stop simulation to edit.")
        return

    payload = msg.get('payload', {})
    event = payload.get('event')
    if event == 'click' and 'x' in payload and 'y' in payload:
        x, y = payload['x'], payload['y']
        if 0 <= y < GRID_HEIGHT and 0 <= x < GRID_WIDTH:
            # Toggle cell state
            game_grid[y][x] = 1 - game_grid[y][x] # Flip 0 to 1, 1 to 0
            logger.info(f"Grid cell ({x},{y}) toggled to state {game_grid[y][x]}.")
            # Update UI immediately for responsiveness (force single cell redraw)
            if grid_module:
                 color = ALIVE_COLOR if game_grid[y][x] == 1 else DEAD_COLOR
                 grid_module.set_color(x, y, color)
                 # Also update previous state for this cell to prevent immediate redraw conflict
                 previous_grid_state[y][x] = game_grid[y][x]
        else:
            logger.warning(f"Ignoring click outside grid bounds: ({x},{y})")


def handle_control_interaction(msg: Dict[str, Any]):
    """Handles button clicks from the Control module."""
    global simulation_running, simulation_thread, game_grid

    payload = msg.get('payload', {})
    event = payload.get('event')
    control_id = payload.get('control_id')

    if event == 'click':
        logger.info(f"Control button clicked: '{control_id}'")
        if control_id == 'start':
            if not simulation_running:
                simulation_running = True
                simulation_stop_event.clear() # Ensure flag is cleared
                # Start thread only if it's not already running or has finished
                if simulation_thread is None or not simulation_thread.is_alive():
                    simulation_thread = threading.Thread(target=run_simulation, daemon=True)
                    simulation_thread.start()
                    logger.info("Simulation started.")
                    if console_module: console_module.log("Simulation started.")
                else:
                     logger.warning("Start clicked, but simulation thread already seems active.")
            else:
                logger.info("Start clicked, but simulation already running.")
                if console_module: console_module.print("Simulation already running.")

        elif control_id == 'stop':
            if simulation_running:
                simulation_running = False
                simulation_stop_event.set() # Signal thread to stop
                logger.info("Stop signal sent to simulation thread.")
                if console_module: console_module.log("Simulation stopped.")
                # We don't explicitly join the thread here to keep UI responsive
            else:
                logger.info("Stop clicked, but simulation not running.")
                if console_module: console_module.print("Simulation is not running.")

        elif control_id == 'step':
            if simulation_running:
                logger.warning("Cannot step while simulation is running.")
                if console_module: console_module.print("Stop simulation to step.")
            else:
                logger.info("Executing one step...")
                game_grid = calculate_next_generation()
                update_grid_ui() # Update UI after step
                logger.info("Step executed.")
                if console_module: console_module.log("Step executed.")

        elif control_id == 'randomize':
             if simulation_running:
                 logger.warning("Cannot randomize while simulation is running.")
                 if console_module: console_module.print("Stop simulation to randomize.")
             else:
                 randomize_grid()
                 update_grid_ui(force_redraw=True) # Force full redraw after randomize

        elif control_id == 'clear':
             if simulation_running:
                 logger.warning("Cannot clear while simulation is running.")
                 if console_module: console_module.print("Stop simulation to clear.")
             else:
                 clear_grid_state()
                 update_grid_ui(force_redraw=True) # Force full redraw after clear


# --- Setup Function ---

def setup_sidekick():
    """Initializes Sidekick connection, modules, and game state."""
    global grid_module, control_module, console_module, game_grid, previous_grid_state

    logger.info("--- Initializing Sidekick Setup ---")
    try:
        # sidekick_connection.activate_connection() # Allow connection attempts

        # Create Console (Optional)
        console_module = Console(instance_id="game-of-life-log")
        console_module.print("Game of Life Initializing...")
        time.sleep(0.1)

        # Create Grid
        grid_module = Grid(width=GRID_WIDTH, height=GRID_HEIGHT, instance_id="game-of-life-grid", on_message=handle_grid_click)
        time.sleep(0.1)

        # Create Controls
        control_module = Control(instance_id="game-of-life-controls", on_message=handle_control_interaction)
        control_module.add_button(control_id="start", text="Start ▶")
        control_module.add_button(control_id="stop", text="Stop ⏹")
        control_module.add_button(control_id="step", text="Step ⏭")
        control_module.add_button(control_id="randomize", text="Randomize 🎲")
        control_module.add_button(control_id="clear", text="Clear 🧹")
        time.sleep(0.1)

        # Initialize Game State
        clear_grid_state() # Start with a dead grid
        previous_grid_state = copy.deepcopy(game_grid) # Initialize previous state

        # Initial UI draw
        update_grid_ui(force_redraw=True)

        console_module.print("Setup complete. Click cells or use controls.")
        logger.info("--- Sidekick Setup Complete ---")

    except Exception as e:
        logger.exception("CRITICAL ERROR during setup!")
        if console_module:
             console_module.print(f"ERROR during setup: {e}")
        # Optionally re-raise or exit?
        raise SystemExit("Failed to initialize Sidekick modules")


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Starting Game of Life with Sidekick...")
    try:
        # Configure Sidekick URL if needed
        # sidekick_connection.set_url(SIDEKICK_URL)

        # Setup modules and initial state
        setup_sidekick()

        # Keep the main thread alive while the simulation runs in the background
        # or until the user interrupts (Ctrl+C)
        logger.info("Main thread running. Simulation controlled by background thread and UI.")
        logger.info("Press Ctrl+C to exit.")
        while True:
            # Check if simulation thread died unexpectedly (optional safeguard)
            if simulation_running and (simulation_thread is None or not simulation_thread.is_alive()):
                 logger.error("Simulation thread seems to have died unexpectedly!")
                 simulation_running = False
                 # Optionally try to restart or just log the error

            time.sleep(1) # Main thread sleeps, polling infrequently


    except KeyboardInterrupt:
        logger.info("Ctrl+C detected. Exiting.")
        # Signal simulation thread to stop if it's running
        simulation_stop_event.set()
        if simulation_thread and simulation_thread.is_alive():
             logger.info("Waiting briefly for simulation thread to stop...")
             simulation_thread.join(timeout=1.0) # Wait max 1 sec
             if simulation_thread.is_alive():
                  logger.warning("Simulation thread did not stop gracefully.")

    except SystemExit as e:
         logger.error(f"System exit requested: {e}")
    except Exception as e:
        logger.exception("An unhandled exception occurred in the main loop!")
    finally:
        # Explicitly close connection (atexit also does this, but good practice)
        logger.info("Requesting Sidekick connection close...")
        sidekick_connection.close_connection()
        logger.info("Game of Life script finished.")