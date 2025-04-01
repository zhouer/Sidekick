import time
import random
import threading
import logging
from copy import deepcopy
from typing import List, Tuple, Set, Optional, Dict, Any

# Import Sidekick modules
from sidekick import Grid, Console, Control, connection

# --- Configuration ---
DEFAULT_WIDTH = 35
DEFAULT_HEIGHT = 35
GENERATION_DELAY = 0.01 # Faster delay for potentially large mazes
SOLVING_DELAY = 0.01    # Slightly slower to see the solving process
WALL_CHAR = '#'
PATH_CHAR = ' '
START_CHAR = 'S'
END_CHAR = 'E'
VISITED_CHAR = '.' # Character for marking visited cells during solve
SOLUTION_CHAR = 'o' # Character for the final solution path

# --- Colors for Visualization ---
WALL_COLOR = 'black'
PATH_COLOR = 'white'
START_COLOR = 'lime' #'#10B981' # Emerald Green
END_COLOR = 'red'   #'#EF4444' # Red
VISITED_COLOR = '#A5B4FC' # Light Indigo (Explored path)
SOLUTION_COLOR = 'yellow' #'#F59E0B' # Amber/Gold
CURRENT_COLOR = 'cyan' # Color for the current cell being processed in generation/solving

# --- Maze Representation ---
maze: List[List[str]] = []
grid_width = DEFAULT_WIDTH
grid_height = DEFAULT_HEIGHT
start_pos: Optional[Tuple[int, int]] = None
end_pos: Optional[Tuple[int, int]] = None

# --- State Flags ---
generating = False
solving = False
generation_complete = False
solution_found: Optional[bool] = None # None=not run, True=found, False=not found
state_lock = threading.Lock() # Lock for accessing/modifying state flags

# --- Sidekick Module Instances ---
grid: Optional[Grid] = None
console: Optional[Console] = None
controls: Optional[Control] = None

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logging.getLogger("SidekickConn").setLevel(logging.DEBUG)

# ==================================
# == Maze Utilities               ==
# ==================================
# ... (is_valid, get_neighbors, map_char_to_color functions remain the same) ...
def is_valid(r: int, c: int) -> bool:
    """Check if coordinates are within the grid boundaries."""
    return 0 <= r < grid_height and 0 <= c < grid_width

def get_neighbors(r: int, c: int, step: int = 1) -> List[Tuple[int, int]]:
    """Get valid neighbors (up, down, left, right) at a given step distance."""
    neighbors = []
    moves = [(0, step), (0, -step), (step, 0), (-step, 0)] # Right, Left, Down, Up
    for dr, dc in moves:
        nr, nc = r + dr, c + dc
        if is_valid(nr, nc):
            neighbors.append((nr, nc))
    random.shuffle(neighbors) # Shuffle for randomness
    return neighbors

def map_char_to_color(char: str) -> str:
    """Maps the internal maze character to a display color."""
    color_map = {
        WALL_CHAR: WALL_COLOR,
        PATH_CHAR: PATH_COLOR,
        START_CHAR: START_COLOR,
        END_CHAR: END_COLOR,
        VISITED_CHAR: VISITED_COLOR,
        SOLUTION_CHAR: SOLUTION_COLOR,
    }
    return color_map.get(char, PATH_COLOR) # Default to path color

# ==================================
# == Maze Generation (Randomized DFS) ==
# ==================================
# ... (initialize_maze_grid, carve_maze_recursive, generate_maze_task functions remain the same) ...
def initialize_maze_grid():
    """Fills the maze grid completely with walls and draws them."""
    global maze, grid # Ensure we are using global grid variable
    if not console or not grid: # Add safety check for grid
         logging.error("Cannot initialize maze grid - console or grid is None.")
         return

    console.print(f"Initializing {grid_width}x{grid_height} grid with walls...")
    maze = [[WALL_CHAR for _ in range(grid_width)] for _ in range(grid_height)]

    # Clear previous visuals
    grid.clear()

    console.print("Drawing initial walls...")
    start_draw_time = time.time()
    # Iterate through the newly created maze data and draw walls on the Sidekick grid
    for r in range(grid_height):
        for c in range(grid_width):
            # Check the internal state (should be WALL_CHAR) and draw
            if maze[r][c] == WALL_CHAR:
                grid.set_color(c, r, WALL_COLOR)
                # Consider removing or significantly reducing sleep for performance
                # time.sleep(0.0001) # This can drastically slow down initialization
    draw_duration = time.time() - start_draw_time
    console.print(f"Initial wall drawing took {draw_duration:.2f}s.")

    console.print("Grid initialized and walls drawn.")

def carve_maze_recursive(r: int, c: int):
    """Recursive function to carve paths using Randomized DFS."""
    global maze, grid
    if not grid: return # Need the visual grid

    maze[r][c] = PATH_CHAR
    grid.set_color(c, r, CURRENT_COLOR)
    time.sleep(GENERATION_DELAY)
    grid.set_color(c, r, PATH_COLOR)

    neighbors = get_neighbors(r, c, step=2)
    for nr, nc in neighbors:
        if maze[nr][nc] == WALL_CHAR:
            wall_r, wall_c = r + (nr - r) // 2, c + (nc - c) // 2
            if maze[wall_r][wall_c] == WALL_CHAR:
                maze[wall_r][wall_c] = PATH_CHAR
                grid.set_color(wall_c, wall_r, PATH_COLOR)
                time.sleep(GENERATION_DELAY / 2)
            carve_maze_recursive(nr, nc)

def generate_maze_task():
    """Task function to generate the maze (runs in a thread)."""
    global generating, generation_complete, start_pos, end_pos, maze
    if not console: return
    with state_lock:
        if generating or solving: console.print("WARN: Generation/Solving already in progress."); return
        generating = True
        generation_complete = False
        solution_found = None

    logging.info("Starting maze generation task...")
    console.print("Generating maze...")
    start_time = time.time()
    try:
        initialize_maze_grid()
        start_carve_r = random.randrange(0, grid_height // 2) * 2
        start_carve_c = random.randrange(0, grid_width // 2) * 2
        carve_maze_recursive(start_carve_r, start_carve_c)

        # Set Start
        start_pos = None; # Find start on first row path
        for c in range(grid_width):
             if maze[0][c] == PATH_CHAR: start_pos = (0, c); break
        if start_pos is None: # Fallback 1
             for r in range(grid_height):
                  if maze[r][0] == PATH_CHAR: start_pos = (r, 0); break
        if start_pos is None: start_pos = (0,0) # Fallback 2
        maze[start_pos[0]][start_pos[1]] = START_CHAR
        if grid: grid.set_color(start_pos[1], start_pos[0], START_COLOR)

        # Set End
        end_pos = None # Find end on last row path
        for c in range(grid_width - 1, -1, -1):
             if maze[grid_height - 1][c] == PATH_CHAR: end_pos = (grid_height - 1, c); break
        if end_pos is None: # Fallback 1
            for r in range(grid_height-1, -1, -1):
                 if maze[r][grid_width-1] == PATH_CHAR: end_pos = (r, grid_width-1); break
        if end_pos is None: end_pos = (grid_height - 1, grid_width - 1) # Fallback 2
        if end_pos == start_pos: # Ensure end is different from start if possible
             if is_valid(end_pos[0], end_pos[1]-1) and maze[end_pos[0]][end_pos[1]-1] == PATH_CHAR: end_pos = (end_pos[0], end_pos[1]-1)
             elif is_valid(end_pos[0]-1, end_pos[1]) and maze[end_pos[0]-1][end_pos[1]] == PATH_CHAR: end_pos = (end_pos[0]-1, end_pos[1])
        maze[end_pos[0]][end_pos[1]] = END_CHAR
        if grid: grid.set_color(end_pos[1], end_pos[0], END_COLOR)

        elapsed = time.time() - start_time
        console.print(f"Maze generated in {elapsed:.2f} seconds.")
        logging.info("Maze generation task finished.")
        generation_complete = True
    except Exception as e:
        logging.exception("Error during maze generation:")
        console.print(f"ERROR: Maze generation failed: {e}")
    finally:
        with state_lock: generating = False


# ==================================
# == Maze Solving (DFS)           ==
# ==================================
# ... (solve_maze_dfs, solve_maze_task functions remain the same) ...
def solve_maze_dfs(start_r: int, start_c: int, end_r: int, end_c: int) -> bool:
    """Solves the maze using DFS and visualizes the process."""
    global maze, grid
    if not grid or not console: return False

    stack: List[Tuple[int, int]] = [(start_r, start_c)]
    visited: Set[Tuple[int, int]] = set([(start_r, start_c)])
    path_taken: Dict[Tuple[int, int], Tuple[int, int]] = {}

    while stack:
        with state_lock:
             if solving is False: console.print("Solver interrupted."); return False

        r, c = stack[-1]

        if (r,c) != (start_r, start_c):
            grid.set_color(c, r, CURRENT_COLOR)
            time.sleep(SOLVING_DELAY)

        if r == end_r and c == end_c:
            logging.info("Solution found!")
            curr = (end_r, end_c)
            while curr != (start_r, start_c):
                 if maze[curr[0]][curr[1]] != END_CHAR:
                      maze[curr[0]][curr[1]] = SOLUTION_CHAR
                      grid.set_color(curr[1], curr[0], SOLUTION_COLOR)
                      time.sleep(SOLVING_DELAY / 2)
                 if curr in path_taken: curr = path_taken[curr]
                 else: logging.error(f"Path reconstruction error: Parent not found for {curr}"); break
            if start_pos: grid.set_color(start_pos[1], start_pos[0], START_COLOR)
            return True

        found_next = False
        for nr, nc in get_neighbors(r, c, step=1):
            if (nr, nc) not in visited and maze[nr][nc] != WALL_CHAR:
                visited.add((nr, nc))
                stack.append((nr, nc))
                path_taken[(nr, nc)] = (r, c)
                found_next = True
                break

        if not found_next:
            dead_end_r, dead_end_c = stack.pop()
            if maze[dead_end_r][dead_end_c] not in [START_CHAR, END_CHAR]:
                 maze[dead_end_r][dead_end_c] = VISITED_CHAR
                 grid.set_color(dead_end_c, dead_end_r, VISITED_COLOR)
                 time.sleep(SOLVING_DELAY / 2)

    logging.info("No solution found.")
    return False

def solve_maze_task():
    """Task function to solve the maze (runs in a thread)."""
    global solving, solution_found
    if not console: return
    with state_lock:
        if solving or generating: console.print("WARN: Solving/Generation already in progress."); return
        if not generation_complete: console.print("Please generate a maze first."); return
        if start_pos is None or end_pos is None: console.print("ERROR: Start or End position not set."); return
        solving = True
        solution_found = None

    logging.info("Starting maze solving task...")
    console.print("Solving maze...")
    start_time = time.time()
    try:
        # Reset visuals
        if grid:
             for r in range(grid_height):
                  for c in range(grid_width):
                       char = maze[r][c]
                       if char == VISITED_CHAR or char == SOLUTION_CHAR: maze[r][c] = PATH_CHAR; grid.set_color(c,r, PATH_COLOR)
                       elif char == START_CHAR: grid.set_color(c,r, START_COLOR)
                       elif char == END_CHAR: grid.set_color(c,r, END_COLOR)
        console.print("Visuals reset for solving.")

        found = solve_maze_dfs(start_pos[0], start_pos[1], end_pos[0], end_pos[1])
        solution_found = found

        elapsed = time.time() - start_time
        if found: console.print(f"Maze solved in {elapsed:.2f} seconds.")
        else:
            with state_lock: was_interrupted = not solving
            if was_interrupted: console.print(f"Maze solving interrupted after {elapsed:.2f} seconds.")
            else: console.print(f"No solution found after {elapsed:.2f} seconds.")
    except Exception as e:
        logging.exception("Error during maze solving:")
        console.print(f"ERROR: Maze solving failed: {e}")
        solution_found = False
    finally:
        with state_lock: solving = False


# ==================================
# == Sidekick Control Handler     ==
# ==================================

def control_handler(msg: Dict[str, Any]):
    """Handles messages received from the Control module."""
    # --- FIX: Declare intention to modify global variable ---
    global solving
    # --- End FIX ---

    # Safety check for console
    if not console:
        logging.error("Control handler called but console is None!")
        return

    logging.debug(f"Control handler received: {msg}")
    payload = msg.get('payload', {})
    event = payload.get('event')
    control_id = payload.get('controlId')

    if event == 'click':
        if control_id == 'generate_btn':
            # Stop any ongoing solve before generating
            with state_lock:
                # Now 'solving' refers to the global variable
                if solving:
                    solving = False # Signal solver thread to stop
                    console.print("Interrupting solver for new generation...")
            # Start generation in a new thread
            # Make sure generate_maze_task is defined before this point
            gen_thread = threading.Thread(target=generate_maze_task, daemon=True)
            gen_thread.start()
        elif control_id == 'solve_btn':
             # Start solving in a new thread
             # Make sure solve_maze_task is defined before this point
            solve_thread = threading.Thread(target=solve_maze_task, daemon=True)
            solve_thread.start()
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
        # time.sleep(0.5)

        # --- Create Sidekick Modules ---
        console_instance = Console(instance_id="maze_console")
        console = console_instance

        grid_instance = Grid(width=grid_width, height=grid_height, instance_id="maze_grid")
        grid = grid_instance

        # Pass the corrected control_handler
        controls_instance = Control(instance_id="maze_controls", on_message=control_handler)
        controls = controls_instance

        console.print("Maze Generator & Solver Initialized.")
        console.print(f"Grid Size: {grid_width}x{grid_height}")

        # --- Add UI Controls ---
        controls.add_button(control_id='generate_btn', text='Generate Maze')
        controls.add_button(control_id='solve_btn', text='Solve Maze (DFS)')
        console.print("Controls added. Click 'Generate Maze' to start.")

        # --- Keep Main Thread Alive ---
        logging.info("Main thread waiting. Use Sidekick controls or Ctrl+C to exit.")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logging.info("Ctrl+C detected. Shutting down...")
    except Exception as e:
        logging.exception(f"An unexpected error occurred in the main thread: {e}")
        if console:
             try: console.print(f"FATAL ERROR: {e}")
             except: pass
    finally:
        # --- Cleanup ---
        logging.info("Initiating cleanup...")
        with state_lock:
            generating = False
            solving = False
        logging.info("Generation/Solving flags set to False.")
        connection.close_connection(log_info=True)
        logging.info("Cleanup complete. Script finished.")