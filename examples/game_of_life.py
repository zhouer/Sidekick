import time
import random
import threading
import logging
from copy import deepcopy
from typing import List, Dict, Any, Optional

import sidekick
from sidekick import Grid, Console, Row, Button

# --- Configuration ---
GRID_WIDTH = 30
GRID_HEIGHT = 30
SIM_DELAY = 0.1  # Delay between simulation steps in seconds
LIVE_COLOR = 'black' # '#34D399' # Teal-ish color for live cells
DEAD_COLOR = 'white' # '#E5E7EB' # Light gray for dead cells

# --- Logging Setup (Optional) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logging.getLogger("sidekick").setLevel(logging.DEBUG)

# --- Game State ---
# Represents the grid: 0 for dead, 1 for live
game_grid: List[List[int]] = []
# Flag to control the simulation loop
running = False
# Lock for safely accessing the 'running' flag from different threads
run_lock = threading.Lock()
# Simulation thread instance
sim_thread: Optional[threading.Thread] = None

# --- Sidekick Component Instances ---
# Initialize with None, create after connection activation potentially
grid: Optional[Grid] = None
console: Optional[Console] = None
controls_row: Optional[Row] = None
start_btn: Optional[Button] = None
stop_btn: Optional[Button] = None
step_btn: Optional[Button] = None
random_btn: Optional[Button] = None
clear_btn: Optional[Button] = None

# ==================================
# == Game of Life Core Logic      ==
# ==================================

def initialize_grid(width: int, height: int, randomize: bool = True):
    """Creates a new grid, optionally filling it randomly."""
    global game_grid
    logging.info(f"Initializing grid ({width}x{height}), randomize={randomize}")
    game_grid = [[0 for _ in range(width)] for _ in range(height)]
    if randomize:
        randomize_grid()

def randomize_grid():
    """Fills the current game_grid with random live/dead cells."""
    global game_grid
    if not game_grid: return
    logging.info("Randomizing grid")
    height = len(game_grid)
    width = len(game_grid[0]) if height > 0 else 0
    for r in range(height):
        for c in range(width):
            game_grid[r][c] = random.choice([0, 1])

def clear_grid():
    """Sets all cells in the current game_grid to dead (0)."""
    global game_grid
    if not game_grid: return
    logging.info("Clearing grid")
    height = len(game_grid)
    width = len(game_grid[0]) if height > 0 else 0
    for r in range(height):
        for c in range(width):
            game_grid[r][c] = 0

def count_live_neighbors(r: int, c: int) -> int:
    """Counts live neighbors for a cell at (r, c) with toroidal wrapping."""
    if not game_grid: return 0
    height = len(game_grid)
    width = len(game_grid[0]) if height > 0 else 0
    count = 0
    for i in range(-1, 2):
        for j in range(-1, 2):
            if i == 0 and j == 0: # Skip the cell itself
                continue
            # Calculate neighbor coordinates with wrap-around
            nr = (r + i + height) % height
            nc = (c + j + width) % width
            count += game_grid[nr][nc]
    return count

def compute_next_gen() -> Optional[List[List[int]]]:
    """Computes the next generation grid based on Conway's rules."""
    if not game_grid: return None
    height = len(game_grid)
    width = len(game_grid[0]) if height > 0 else 0
    # Create a new grid for the next state to avoid modifying during iteration
    next_grid = deepcopy(game_grid)

    for r in range(height):
        for c in range(width):
            live_neighbors = count_live_neighbors(r, c)
            current_state = game_grid[r][c]

            # Apply Game of Life rules
            if current_state == 1: # Live cell
                if live_neighbors < 2 or live_neighbors > 3:
                    next_grid[r][c] = 0 # Dies
                # else: stays alive (no change needed)
            else: # Dead cell
                if live_neighbors == 3:
                    next_grid[r][c] = 1 # Becomes live

    return next_grid

# ==================================
# == Sidekick Interaction Logic   ==
# ==================================

def draw_grid(current: List[List[int]], next_g: List[List[int]]):
    """Updates the Sidekick Grid, only drawing cells that changed."""
    if not grid or not current or not next_g: return
    height = len(current)
    width = len(current[0]) if height > 0 else 0
    changes = 0
    for r in range(height):
        for c in range(width):
            if current[r][c] != next_g[r][c]:
                changes += 1
                color = LIVE_COLOR if next_g[r][c] == 1 else DEAD_COLOR
                grid.set_color(c, r, color)
    if changes > 0:
        logging.debug(f"Drew {changes} cell changes.")

def draw_full_grid():
    """Draws the entire current game_grid state onto the Sidekick Grid."""
    if not grid or not game_grid: return
    logging.debug("Drawing full grid state.")
    height = len(game_grid)
    width = len(game_grid[0]) if height > 0 else 0
    for r in range(height):
        for c in range(width):
            color = LIVE_COLOR if game_grid[r][c] == 1 else DEAD_COLOR
            grid.set_color(c, r, color)

def handle_start_click():
    """Handles click on the Start button."""
    global running
    logging.debug("Start button clicked")

    if not console: return

    with run_lock: # Lock when potentially modifying 'running' or grid
        if not running:
            running = True
            console.print("Simulation Started.")
            logging.info("Start button clicked - Running set to True")

def handle_stop_click():
    """Handles click on the Stop button."""
    global running
    logging.debug("Stop button clicked")

    if not console: return

    with run_lock: # Lock when potentially modifying 'running' or grid
        if running:
            running = False
            console.print("Simulation Stopped.")
            logging.info("Stop button clicked - Running set to False")

def handle_step_click():
    """Handles click on the Step button."""
    global running, game_grid
    logging.debug("Step button clicked")

    if not console: return

    with run_lock: # Lock when potentially modifying 'running' or grid
        # Stop simulation first, then perform one step
        if running:
            running = False
            console.print("Simulation Stopped for Stepping.")
            logging.info("Step button clicked - Running set to False")
        # Compute and draw one step
        console.print("Performing one step...")
        logging.info("Step button clicked - Computing next gen")
        current_grid_copy = deepcopy(game_grid) # Keep current state for comparison
        next_grid = compute_next_gen()
        if next_grid:
            draw_grid(current_grid_copy, next_grid)
            game_grid = next_grid # Update state after drawing changes
        console.print("Step completed.")

def handle_random_click():
    """Handles click on the Randomize button."""
    global running
    logging.debug("Randomize button clicked")

    if not console: return

    with run_lock: # Lock when potentially modifying 'running' or grid
        # Stop simulation before randomizing
        if running:
            running = False
            console.print("Simulation Stopped for Randomization.")
            logging.info("Randomize button clicked - Running set to False")
        randomize_grid()
        draw_full_grid() # Draw the new randomized state
        console.print("Grid randomized.")

def handle_clear_click():
    """Handles click on the Clear button."""
    global running
    logging.debug("Clear button clicked")

    if not console: return

    with run_lock: # Lock when potentially modifying 'running' or grid
        # Stop simulation before clearing
        if running:
            running = False
            console.print("Simulation Stopped for Clearing.")
            logging.info("Clear button clicked - Running set to False")
        clear_grid()
        draw_full_grid() # Draw the new cleared state
        console.print("Grid cleared.")

def handle_grid_click(x: int, y: int):
    """Handles clicks on the Grid component."""
    global game_grid
    if not grid or not console or not game_grid: return

    with run_lock: # Prevent modification while simulation might be reading
        if 0 <= y < len(game_grid) and 0 <= x < len(game_grid[0]):
            # Toggle the state of the clicked cell
            game_grid[y][x] = 1 - game_grid[y][x]
            color = LIVE_COLOR if game_grid[y][x] == 1 else DEAD_COLOR
            grid.set_color(x, y, color)
            console.print(f"Toggled cell ({x},{y}) to {'Live' if game_grid[y][x] == 1 else 'Dead'}")
        else:
            console.print(f"WARN: Click outside grid bounds ({x},{y})")

# ==================================
# == Simulation Thread Logic      ==
# ==================================

def simulation_loop():
    """The main loop for the simulation, run in a separate thread."""
    global game_grid
    logging.info("Simulation thread started.")
    while True:
        should_run = False
        with run_lock:
            should_run = running # Check if we should run this iteration

        if should_run:
            start_time = time.time()
            logging.debug("Simulation loop running - Computing next gen")
            current_grid_copy = deepcopy(game_grid) # Keep current state for comparison
            next_grid = compute_next_gen()
            if next_grid:
                # Update the Sidekick grid visually
                draw_grid(current_grid_copy, next_grid)
                # Update the internal game state *after* drawing changes
                game_grid = next_grid
            else:
                 logging.error("Compute_next_gen returned None") # Should not happen if grid exists

            # Calculate time spent and sleep accordingly
            elapsed = time.time() - start_time
            sleep_time = max(0, SIM_DELAY - elapsed)
            logging.debug(f"Step computed in {elapsed:.3f}s, sleeping for {sleep_time:.3f}s")
            if sleep_time > 0:
                time.sleep(sleep_time)
        else:
            # If not running, sleep for a short duration to avoid busy-waiting
            time.sleep(0.1) # Check run status every 100ms

# ==================================
# == Main Execution               ==
# ==================================

if __name__ == "__main__":
    try:
        controls_row = Row()
        start_btn = Button(text='Start', parent=controls_row)
        start_btn.on_click(handle_start_click)
        stop_btn = Button(text='Stop', parent=controls_row)
        stop_btn.on_click(handle_stop_click)
        step_btn = Button(text='Step', parent=controls_row)
        step_btn.on_click(handle_step_click)
        random_btn = Button(text='Randomize', parent=controls_row)
        random_btn.on_click(handle_random_click)
        clear_btn = Button(text='Clear', parent=controls_row)
        clear_btn.on_click(handle_clear_click)

        grid = Grid(num_columns=GRID_WIDTH, num_rows=GRID_HEIGHT)
        grid.on_click(handle_grid_click) # Register grid click handler

        console = Console()
        console.print("Welcome to Conway's Game of Life!")
        console.print(f"Grid Size: {GRID_WIDTH}x{GRID_HEIGHT}. Delay: {SIM_DELAY}s")

        # Initialize and draw the initial grid state
        initialize_grid(GRID_WIDTH, GRID_HEIGHT, randomize=True)
        draw_full_grid()
        console.print("Initial grid generated.")

        # Start the simulation loop in a background thread
        # Use daemon=True so the thread exits when the main script exits
        sim_thread = threading.Thread(target=simulation_loop, daemon=True)
        sim_thread.start()

        # Keep the main thread alive to handle callbacks and keyboard interrupt
        console.print("Simulation thread started. Use controls or Ctrl+C to exit.")
        sidekick.run_forever()
    finally:
        # Attempt to stop the simulation cleanly if it was running
        with run_lock:
            running = False
        logging.info("Stopping simulation flag.")

        # Optional: Explicitly remove components (though connection close handles handlers)
        # if controls_row: controls_row.remove()
        # if start_btn: start_btn.remove()
        # if stop_btn: stop_btn.remove()
        # if step_btn: step_btn.remove()
        # if random_btn: random_btn.remove()
        # if clear_btn: clear_btn.remove()
        # if grid: grid.remove()
        # if console: console.remove()

        logging.info("Script finished.")
