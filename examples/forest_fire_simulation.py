# forest_fire_simulation.py
import time
import random
import threading
import logging
from copy import deepcopy
from typing import List, Tuple, Optional, Dict, Any

# Import Sidekick modules
from sidekick import Grid, Console, Control, connection

# --- Configuration ---
GRID_WIDTH = 50
GRID_HEIGHT = 50
SIM_DELAY = 0.1  # Delay between simulation steps in seconds

# --- Simulation Parameters ---
P_GROWTH = 0.01   # Probability of an empty cell growing a tree
P_LIGHTNING = 0.0001 # Probability of a tree catching fire spontaneously (lightning)

# --- State Constants ---
STATE_EMPTY = 0
STATE_TREE = 1
STATE_BURNING = 2

# --- Colors for Visualization ---
EMPTY_COLOR = '#D1D5DB' # Gray-300 (Empty ground)
TREE_COLOR = '#10B981'  # Emerald-500 (Healthy tree)
FIRE_COLOR = '#EF4444'  # Red-500 (Burning tree)
# Optional: Add more colors for different burning stages if desired

# --- Simulation State ---
forest_grid: List[List[int]] = [] # Stores the state (0, 1, or 2) of each cell
running = False                   # Flag to control the simulation loop
state_lock = threading.Lock()     # Lock for safely accessing shared state (running, forest_grid)
sim_thread: Optional[threading.Thread] = None # Simulation thread instance

# --- Sidekick Module Instances ---
grid: Optional[Grid] = None
console: Optional[Console] = None
controls: Optional[Control] = None

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logging.getLogger("SidekickConn").setLevel(logging.DEBUG) # Uncomment for detailed logs

# ==================================
# == Simulation Utilities         ==
# ==================================

def is_valid(r: int, c: int) -> bool:
    """Check if coordinates are within the grid boundaries."""
    return 0 <= r < GRID_HEIGHT and 0 <= c < GRID_WIDTH

def get_neighbors(r: int, c: int) -> List[Tuple[int, int]]:
    """Get valid Moore neighbors (8 directions) for a cell."""
    neighbors = []
    for dr in range(-1, 2):
        for dc in range(-1, 2):
            if dr == 0 and dc == 0: # Skip self
                continue
            nr, nc = r + dr, c + dc
            if is_valid(nr, nc):
                neighbors.append((nr, nc))
    # No shuffling needed here, check all neighbors
    return neighbors

def map_state_to_color(state: int) -> str:
    """Maps the internal integer state to a display color."""
    if state == STATE_TREE:
        return TREE_COLOR
    elif state == STATE_BURNING:
        return FIRE_COLOR
    else: # STATE_EMPTY
        return EMPTY_COLOR

# ==================================
# == Core Simulation Logic        ==
# ==================================

def initialize_forest():
    """Creates the initial forest grid, mostly empty."""
    global forest_grid
    if not console: return
    console.print(f"Initializing {GRID_WIDTH}x{GRID_HEIGHT} forest...")
    # Start with an empty grid
    forest_grid = [[STATE_EMPTY for _ in range(GRID_WIDTH)] for _ in range(GRID_HEIGHT)]
    # Optional: Seed with a few initial trees?
    # for _ in range(GRID_WIDTH * GRID_HEIGHT // 10): # Seed 10% trees
    #    r, c = random.randrange(GRID_HEIGHT), random.randrange(GRID_WIDTH)
    #    forest_grid[r][c] = STATE_TREE
    console.print("Forest initialized (mostly empty).")

def compute_next_forest_state() -> Optional[List[List[int]]]:
    """Computes the next state of the forest based on the rules."""
    if not forest_grid: return None

    next_grid = deepcopy(forest_grid) # Work on a copy to avoid cascading changes

    for r in range(GRID_HEIGHT):
        for c in range(GRID_WIDTH):
            current_state = forest_grid[r][c]

            if current_state == STATE_EMPTY:
                # Rule 1: Empty cell grows a tree with probability P_GROWTH
                if random.random() < P_GROWTH:
                    next_grid[r][c] = STATE_TREE
            elif current_state == STATE_TREE:
                # Rule 2: Tree catches fire if a neighbor is burning
                neighbor_is_burning = False
                for nr, nc in get_neighbors(r, c):
                    if forest_grid[nr][nc] == STATE_BURNING:
                        neighbor_is_burning = True
                        break
                if neighbor_is_burning:
                    next_grid[r][c] = STATE_BURNING
                else:
                    # Rule 3: Tree catches fire spontaneously (lightning) with probability P_LIGHTNING
                    if random.random() < P_LIGHTNING:
                        next_grid[r][c] = STATE_BURNING
                    # Otherwise, the tree remains a tree (no change needed in next_grid)
            elif current_state == STATE_BURNING:
                # Rule 4: Burning tree becomes empty in the next step
                next_grid[r][c] = STATE_EMPTY
            # Else: Should not happen if states are managed correctly

    return next_grid

# ==================================
# == Sidekick Interaction Logic   ==
# ==================================

def draw_full_forest():
    """Draws the entire current forest state onto the Sidekick Grid."""
    if not grid or not forest_grid: return
    logging.debug("Drawing full forest state.")
    for r in range(GRID_HEIGHT):
        for c in range(GRID_WIDTH):
            color = map_state_to_color(forest_grid[r][c])
            grid.set_color(c, r, color) # Grid uses (x, y) order

def draw_forest_changes(current: List[List[int]], next_g: List[List[int]]):
    """Updates the Sidekick Grid, only drawing cells that changed state."""
    if not grid or not current or not next_g: return
    changes = 0
    for r in range(GRID_HEIGHT):
        for c in range(GRID_WIDTH):
            if current[r][c] != next_g[r][c]:
                changes += 1
                color = map_state_to_color(next_g[r][c])
                grid.set_color(c, r, color) # Grid uses (x, y) order
    if changes > 0:
        logging.debug(f"Drew {changes} cell changes.")

# ==================================
# == Simulation Thread Logic      ==
# ==================================

def simulation_loop():
    """The main loop for the simulation, run in a separate thread."""
    global forest_grid # We will modify the global grid state here
    logging.info("Simulation thread started.")
    while True:
        should_run = False
        # Check if the simulation should be running in this iteration
        with state_lock:
            should_run = running

        if not should_run:
            # If stopped, sleep briefly to avoid busy-waiting
            time.sleep(0.1)
            continue # Skip the rest of the loop iteration

        # --- Simulation Step ---
        start_time = time.time()
        logging.debug("Simulation loop running - Computing next state")

        # Keep a reference to the current state for comparison drawing
        current_grid_state = forest_grid
        # Compute the next state based on the current state
        next_grid_state = compute_next_forest_state()

        if next_grid_state:
            # Draw only the changes between current and next state
            draw_forest_changes(current_grid_state, next_grid_state)
            # CRITICAL: Update the global state *after* calculating and drawing
            # Protect this write with the lock if controls might also modify it (e.g., reset)
            with state_lock:
                # Check again if still running before modifying grid
                # This prevents overwriting a reset grid if Stop/Reset was clicked during computation
                if running:
                    forest_grid = next_grid_state
                else:
                    logging.info("Simulation stopped during computation, discarding result.")
                    # If stopped, don't update the global grid, just exit the loop iteration
                    continue # Go back to the top to check the 'running' flag again

        else:
             logging.error("compute_next_forest_state returned None")

        # --- Delay ---
        elapsed = time.time() - start_time
        sleep_time = max(0, SIM_DELAY - elapsed)
        logging.debug(f"Step computed in {elapsed:.3f}s, sleeping for {sleep_time:.3f}s")
        if sleep_time > 0:
            time.sleep(sleep_time)

        # Check again if still running *after* sleep, before next iteration
        with state_lock:
            if not running:
                logging.info("Simulation loop detected stop signal after sleep.")
                # No need to explicitly break, the check at the top will handle it


# ==================================
# == Sidekick Control Handler     ==
# ==================================

def control_handler(msg: Dict[str, Any]):
    """Handles messages received from the Control module."""
    global running, forest_grid # Need access to modify running and potentially reset grid

    if not console: logging.error("Control handler called but console is None!"); return

    logging.debug(f"Control handler received: {msg}")
    payload = msg.get('payload', {})
    event = payload.get('event')
    control_id = payload.get('controlId')

    if event == 'click':
        with state_lock: # Acquire lock to safely modify shared state
            if control_id == 'start_btn':
                if not running:
                    running = True
                    console.print("Simulation Started.")
                    logging.info("Start button clicked - Running set to True")
            elif control_id == 'stop_btn':
                if running:
                    running = False
                    console.print("Simulation Stopped.")
                    logging.info("Stop button clicked - Running set to False")
            elif control_id == 'reset_btn':
                # Stop the simulation first
                if running:
                    running = False
                    console.print("Simulation Stopped for Reset.")
                    logging.info("Reset button clicked - Running set to False")
                # Re-initialize the forest state
                initialize_forest()
                # Draw the newly initialized state immediately
                draw_full_forest()
                console.print("Forest Reset.")
            else:
                logging.warning(f"Unknown control click: {control_id}")
    else:
        logging.warning(f"Received non-click event from controls: {event}")

# ==================================
# == Main Execution               ==
# ==================================

if __name__ == "__main__":
    console_instance = None
    grid_instance = None
    controls_instance = None
    try:
        # --- Initialize Sidekick ---
        connection.activate_connection()
        logging.info("Attempting to connect to Sidekick...")
        time.sleep(0.5) # Allow time for connection

        # --- Create Sidekick Modules ---
        console_instance = Console(instance_id="fire_console")
        console = console_instance

        grid_instance = Grid(width=GRID_WIDTH, height=GRID_HEIGHT, instance_id="fire_grid")
        grid = grid_instance

        controls_instance = Control(instance_id="fire_controls", on_message=control_handler)
        controls = controls_instance

        console.print("Forest Fire Simulation Initialized.")
        console.print(f"Grid: {GRID_WIDTH}x{GRID_HEIGHT}, Growth: {P_GROWTH:.2f}, Lightning: {P_LIGHTNING:.4f}")

        # --- Add UI Controls ---
        controls.add_button(control_id='start_btn', text='Start Fire')
        controls.add_button(control_id='stop_btn', text='Stop Fire')
        controls.add_button(control_id='reset_btn', text='Reset Forest')
        console.print("Controls added.")

        # --- Initial Forest Setup ---
        initialize_forest() # Create initial empty forest data
        draw_full_forest()  # Draw the initial state
        console.print("Initial empty forest drawn. Click 'Start Fire'.")

        # --- Start Simulation Thread ---
        # Start the simulation loop in a background thread
        # Use daemon=True so the thread exits automatically when the main script exits
        sim_thread = threading.Thread(target=simulation_loop, daemon=True)
        sim_thread.start()

        # --- Keep Main Thread Alive ---
        logging.info("Simulation thread started. Main thread waiting. Use controls or Ctrl+C.")
        while True:
            # Main thread sleeps, background thread does the work
            # The connection listener thread handles control callbacks
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Ctrl+C detected. Shutting down...")
    except Exception as e:
        logging.exception(f"An unexpected error occurred in the main thread: {e}")
        if console:
             try: console.print(f"FATAL ERROR: {e}")
             except: pass # Ignore errors during final error reporting
    finally:
        # --- Cleanup ---
        logging.info("Initiating cleanup...")
        # Signal the simulation thread to stop cleanly
        with state_lock:
            running = False
        logging.info("Simulation flag set to False.")
        # Give the simulation thread a moment to finish its current loop if needed
        # (Optional, depends if precise cleanup is critical)
        # if sim_thread and sim_thread.is_alive():
        #    sim_thread.join(timeout=0.5) # Wait briefly

        # Close the Sidekick connection (also called by atexit, but explicit is good)
        connection.close_connection(log_info=True)
        logging.info("Cleanup complete. Script finished.")