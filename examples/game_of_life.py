import sidekick
import random
import asyncio
from copy import deepcopy
from typing import List, Optional

# --- Configuration ---
# These are constants you can easily change to alter the simulation.

GRID_WIDTH = 25  # The number of cells horizontally.
GRID_HEIGHT = 25  # The number of cells vertically.
SIM_DELAY = 0.1  # The delay in seconds between each generation when running.
LIVE_COLOR = 'RoyalBlue'  # The color for a living cell.
DEAD_COLOR = 'white'  # The color for a dead cell.

# --- Game State ---
# These are global variables that hold the current state of our game.

# This list of lists represents the game board. 1 means a cell is alive, 0 means it's dead.
game_grid: List[List[int]] = []
# A simple flag to track if the simulation is currently running or paused.
is_running = False
# This will hold the asyncio.Task object for our simulation, so we can cancel it later.
simulation_task: Optional[asyncio.Task] = None

# --- Sidekick Component Instances ---
# We declare these as global so they can be accessed from different functions.
grid: Optional[sidekick.Grid] = None
start_stop_btn: Optional[sidekick.Button] = None


# ==================================
# == Game of Life Core Logic      ==
# ==================================

def initialize_grid(width: int, height: int, randomize: bool = True):
    """
    Creates a new grid state, which is a 2D list of 0s and 1s.
    If 'randomize' is True, it will also fill the grid with a random pattern.
    """
    global game_grid
    # Create a list of lists, all initialized to 0 (dead).
    game_grid = [[0 for _ in range(width)] for _ in range(height)]
    if randomize:
        randomize_grid()


def randomize_grid():
    """Fills the current game_grid state with a random pattern of live/dead cells."""
    global game_grid
    if not game_grid: return
    for r in range(GRID_HEIGHT):
        for c in range(GRID_WIDTH):
            # random.choice gives us a 0 or a 1 with equal probability.
            game_grid[r][c] = random.choice([0, 1])


def clear_grid_state():
    """Sets all cells in the current game_grid state to dead (0)."""
    global game_grid
    if not game_grid: return
    for r in range(GRID_HEIGHT):
        for c in range(GRID_WIDTH):
            game_grid[r][c] = 0


def count_live_neighbors(r: int, c: int) -> int:
    """
    Counts the number of live neighbors for a specific cell at (row, col).
    The grid "wraps around" (toroidal), meaning the top edge is connected to the
    bottom, and the left edge is connected to the right.
    """
    count = 0
    # Loop through the 3x3 square centered on the cell (r, c).
    for i in range(-1, 2):
        for j in range(-1, 2):
            # Skip the cell itself.
            if i == 0 and j == 0:
                continue

            # The modulo operator (%) makes the grid wrap around.
            # For example, if r is 0 and i is -1, (0 - 1 + 25) % 25 = 24 (the last row).
            nr = (r + i + GRID_HEIGHT) % GRID_HEIGHT
            nc = (c + j + GRID_WIDTH) % GRID_WIDTH

            # Add the neighbor's state (1 if alive, 0 if dead) to the count.
            count += game_grid[nr][nc]

    return count


def compute_next_gen() -> Optional[List[List[int]]]:
    """
    Computes the next state of the grid based on the rules of Conway's Game of Life.
    Returns a new grid representing the next generation.
    """
    if not game_grid:
        return None

    # We create a deepcopy (a full, independent snapshot) of the grid.
    # This is crucial so that our calculations for the next state are all based
    # on the original state, not a partially-updated one.
    next_grid = deepcopy(game_grid)

    # Go through every cell in the grid.
    for r in range(GRID_HEIGHT):
        for c in range(GRID_WIDTH):
            live_neighbors = count_live_neighbors(r, c)

            # Rule 1 & 2: A live cell with fewer than 2 or more than 3 live neighbors dies.
            if game_grid[r][c] == 1:
                if live_neighbors < 2 or live_neighbors > 3:
                    next_grid[r][c] = 0
            # Rule 3: A dead cell with exactly 3 live neighbors becomes a live cell.
            else:
                if live_neighbors == 3:
                    next_grid[r][c] = 1

    return next_grid


# ==================================
# == Sidekick Interaction Logic   ==
# ==================================

def draw_grid_changes(current: List[List[int]], next_g: List[List[int]]):
    """
    A smart-drawing function. It compares the current grid with the next one
    and only updates the cells that have actually changed state. This is much
    more efficient than redrawing the entire grid every time.
    """
    if not grid: return
    for r in range(GRID_HEIGHT):
        for c in range(GRID_WIDTH):
            # If the state is different, update the color in the Sidekick grid.
            if current[r][c] != next_g[r][c]:
                color = LIVE_COLOR if next_g[r][c] == 1 else DEAD_COLOR
                grid.set_color(c, r, color)


def draw_full_grid():
    """
    Draws the entire current game_grid state onto the Sidekick Grid.
    This is used for initial setup or after a full reset like 'Randomize' or 'Clear'.
    """
    if not grid: return
    for r in range(GRID_HEIGHT):
        for c in range(GRID_WIDTH):
            color = LIVE_COLOR if game_grid[r][c] == 1 else DEAD_COLOR
            grid.set_color(c, r, color)


def simulation_step():
    """
    Performs one single step (or "turn") of the simulation.
    It computes the next generation and then calls the drawing function.
    """
    global game_grid
    current_grid_copy = deepcopy(game_grid)
    next_grid = compute_next_gen()
    if next_grid:
        draw_grid_changes(current_grid_copy, next_grid)
        # It's important to update the main game_grid only after calculating and drawing.
        game_grid = next_grid


# --- Simulation Control ---

def start_simulation():
    """Starts the automatic simulation using sidekick.submit_interval."""
    global is_running, simulation_task
    if is_running: return  # Do nothing if it's already running.

    is_running = True
    # This is the key function for animation. It tells Sidekick to call our
    # `simulation_step` function repeatedly, with a `SIM_DELAY` pause between each call.
    simulation_task = sidekick.submit_interval(simulation_step, interval=SIM_DELAY)

    if start_stop_btn:
        start_stop_btn.text = "Stop"


def stop_simulation():
    """Stops the running simulation by canceling the asyncio task."""
    global is_running, simulation_task
    if not is_running or not simulation_task: return  # Do nothing if it's not running.

    is_running = False
    # This cancels the repeating task created by `submit_interval`.
    simulation_task.cancel()
    simulation_task = None

    if start_stop_btn:
        start_stop_btn.text = "Start"


# --- Button and Grid Event Handlers ---

def handle_start_stop_click(event):
    """This function is called when the Start/Stop button is clicked."""
    if is_running:
        stop_simulation()
    else:
        start_simulation()


def handle_step_click(event):
    """This function is called when the Step button is clicked."""
    # First, make sure the automatic simulation is stopped.
    stop_simulation()
    # Then, perform just one step.
    simulation_step()


def handle_random_click(event):
    """This function is called when the Randomize button is clicked."""
    stop_simulation()
    randomize_grid()
    draw_full_grid()  # Redraw the whole grid with the new pattern.


def handle_clear_click(event):
    """This function is called when the Clear button is clicked."""
    stop_simulation()
    clear_grid_state()
    draw_full_grid()  # Redraw the whole empty grid.


def handle_grid_click(event):
    """
    This function is called when any cell in the Sidekick Grid is clicked.
    The 'event' object passed by Sidekick contains the x and y coordinates.
    """
    # Check if the click was within the valid grid area.
    if not (0 <= event.y < GRID_HEIGHT and 0 <= event.x < GRID_WIDTH):
        return

    # Toggle the state in our data model (0 becomes 1, 1 becomes 0).
    game_grid[event.y][event.x] = 1 - game_grid[event.y][event.x]

    # Update the color in the visual grid to match the new state.
    color = LIVE_COLOR if game_grid[event.y][event.x] == 1 else DEAD_COLOR
    if grid:
        grid.set_color(event.x, event.y, color)


# ==================================
# == Main Execution Block         ==
# ==================================

# The `if __name__ == "__main__":` block is the entry point of our script.
# Code inside this block will run when you execute the file directly.
if __name__ == "__main__":
    # --- Create the UI Layout ---
    # Create a Row container to hold all our buttons horizontally.
    controls_row = sidekick.Row()

    # Create the buttons and place them inside the 'controls_row' container.
    # We also link each button's 'on_click' event to its handler function.
    start_stop_btn = sidekick.Button("Start", parent=controls_row, on_click=handle_start_stop_click)
    step_btn = sidekick.Button("Step", parent=controls_row, on_click=handle_step_click)
    random_btn = sidekick.Button("Randomize", parent=controls_row, on_click=handle_random_click)
    clear_btn = sidekick.Button("Clear", parent=controls_row, on_click=handle_clear_click)

    # Create the main grid component and link its 'on_click' event.
    grid = sidekick.Grid(num_columns=GRID_WIDTH, num_rows=GRID_HEIGHT, on_click=handle_grid_click)

    # --- Initialize and Draw the Initial Game State ---
    initialize_grid(GRID_WIDTH, GRID_HEIGHT, randomize=True)
    draw_full_grid()

    # --- Keep the Script Running ---
    # This is a very important line. It tells Sidekick to keep the script alive
    # so it can listen for UI events (like button clicks) from the user.
    # Without this, the script would finish and exit immediately.
    sidekick.run_forever()