import time
import random
import threading
import logging
from typing import List, Tuple, Set, Optional, Dict, Any

import sidekick
from sidekick import Grid, Console, Button, Row

# --- Configuration ---
DEFAULT_WIDTH = 35
DEFAULT_HEIGHT = 35
# Adjust delays if needed, Prim's might feel slightly different
GENERATION_DELAY = 0.01 # Keep generation reasonably fast
SOLVING_DELAY = 0.01
WALL_CHAR = '#'
PATH_CHAR = ' '
START_CHAR = 'S'
END_CHAR = 'E'
VISITED_CHAR = '.'
SOLUTION_CHAR = 'o'

# --- Colors for Visualization ---
WALL_COLOR = 'black'
PATH_COLOR = 'white'
START_COLOR = 'lime'
END_COLOR = 'red'
VISITED_COLOR = '#A5B4FC' # Light Purple
SOLUTION_COLOR = 'yellow'
CURRENT_COLOR = 'cyan'
# New color for cells in the frontier set during Prim's generation
FRONTIER_COLOR = '#FCA5A5' # Light Red

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
solution_found: Optional[bool] = None
state_lock = threading.Lock()

# --- Sidekick Component Instances ---
grid: Optional[Grid] = None
console: Optional[Console] = None
row: Optional[Row] = None
generate_btn: Optional[Button] = None
solve_btn: Optional[Button] = None

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
# logging.getLogger("sidekick").setLevel(logging.DEBUG)

# ==================================
# == Maze Utilities               ==
# ==================================

def is_valid(r: int, c: int) -> bool:
    """Check if coordinates are within the grid boundaries."""
    return 0 <= r < grid_height and 0 <= c < grid_width

def get_neighbors(r: int, c: int, step: int = 1, check_wall: bool = False) -> List[Tuple[int, int]]:
    """
    Get valid neighbors (up, down, left, right) at a given step distance.
    Optionally check if the neighbor cell is currently a wall.
    """
    neighbors = []
    # Ensure consistent order for potential determinism (even though we shuffle later)
    moves = [(-step, 0), (step, 0), (0, -step), (0, step)] # Up, Down, Left, Right
    for dr, dc in moves:
        nr, nc = r + dr, c + dc
        if is_valid(nr, nc):
            # If check_wall is True, only add if the neighbor is a wall
            if not check_wall or (check_wall and maze[nr][nc] == WALL_CHAR):
                neighbors.append((nr, nc))
    random.shuffle(neighbors) # Shuffle for randomness
    return neighbors

def map_char_to_color(char: str) -> str:
    """Maps the internal maze character to a display color."""
    color_map = {
        WALL_CHAR: WALL_COLOR, PATH_CHAR: PATH_COLOR, START_CHAR: START_COLOR,
        END_CHAR: END_COLOR, VISITED_CHAR: VISITED_COLOR, SOLUTION_CHAR: SOLUTION_COLOR,
    }
    return color_map.get(char, PATH_COLOR)

# ==================================
# == Maze Generation (Prim's Algorithm) ==
# ==================================

def initialize_maze_grid():
    """Fills the maze grid completely with walls and draws them."""
    global maze, grid
    if not console or not grid:
         logging.error("Cannot initialize maze grid - console or grid is None.")
         return

    console.print(f"Initializing {grid_width}x{grid_height} grid with walls...")
    maze = [[WALL_CHAR for _ in range(grid_width)] for _ in range(grid_height)]

    grid.clear()
    console.print("Drawing initial walls...")
    start_draw_time = time.time()
    for r in range(grid_height):
        for c in range(grid_width):
            if maze[r][c] == WALL_CHAR:
                # Grid methods use (x=column, y=row) order
                grid.set_color(c, r, WALL_COLOR)
    draw_duration = time.time() - start_draw_time
    console.print(f"Initial wall drawing took {draw_duration:.2f}s.")
    console.print("Grid initialized and walls drawn.")


def generate_maze_prims():
    """Generates the maze using Prim's algorithm."""
    global maze, grid
    if not grid or not console: return

    # 1. Pick starting cell, mark as path, add its neighbors (walls) to frontier
    # Ensure start is on even coordinates for consistency with wall carving logic
    start_r = random.randrange(0, grid_height // 2) * 2
    start_c = random.randrange(0, grid_width // 2) * 2
    maze[start_r][start_c] = PATH_CHAR
    grid.set_color(start_c, start_r, PATH_COLOR) # (x, y)

    # Frontier stores tuples: (wall_r, wall_c, origin_r, origin_c)
    # We store the wall neighbor and the path cell it came from
    frontier: List[Tuple[int, int, int, int]] = []
    for nr, nc in get_neighbors(start_r, start_c, step=1, check_wall=True):
        frontier.append((nr, nc, start_r, start_c))
        # Optionally visualize frontier cells
        # grid.set_color(nc, nr, FRONTIER_COLOR)

    # 2. While frontier is not empty
    while frontier:
        # Check for interruption signal
        with state_lock:
             if not generating:
                  console.print("Generation interrupted.")
                  return # Stop generation

        # Randomly choose a frontier cell (wall) to potentially carve
        # Using pop with random index is efficient for random choice + removal
        idx = random.randrange(len(frontier))
        fr_r, fr_c, origin_r, origin_c = frontier.pop(idx)
        # Optionally reset color if it was marked as frontier
        # if maze[fr_r][fr_c] == WALL_CHAR: grid.set_color(fr_c, fr_r, WALL_COLOR)

        # Find the cell on the opposite side of the chosen frontier wall
        # relative to the origin cell it was added from
        opposite_r, opposite_c = fr_r + (fr_r - origin_r), fr_c + (fr_c - origin_c)

        # 3. Check if the opposite cell is within bounds and is also a wall
        if is_valid(opposite_r, opposite_c) and maze[opposite_r][opposite_c] == WALL_CHAR:
            # 4. Carve path through the frontier wall and the opposite cell
            # Visualize carving the wall first
            grid.set_color(fr_c, fr_r, CURRENT_COLOR) # (x, y)
            time.sleep(GENERATION_DELAY / 2)
            maze[fr_r][fr_c] = PATH_CHAR
            grid.set_color(fr_c, fr_r, PATH_COLOR) # (x, y)

            # Visualize carving the opposite cell
            grid.set_color(opposite_c, opposite_r, CURRENT_COLOR) # (x, y)
            time.sleep(GENERATION_DELAY) # Full delay here
            maze[opposite_r][opposite_c] = PATH_CHAR
            grid.set_color(opposite_c, opposite_r, PATH_COLOR) # (x, y)

            # 5. Add the *new* wall neighbors of the 'opposite' cell to the frontier
            for nnr, nnc in get_neighbors(opposite_r, opposite_c, step=1, check_wall=True):
                # Avoid adding duplicates to frontier (simple check)
                # A set could be used for the frontier for O(1) checks, but list is simpler here
                if not any(f[0] == nnr and f[1] == nnc for f in frontier):
                    frontier.append((nnr, nnc, opposite_r, opposite_c))
                    # Optionally visualize new frontier cells
                    # grid.set_color(nnc, nnr, FRONTIER_COLOR) # (x, y)

        # If the opposite cell wasn't a wall, this frontier cell leads nowhere new,
        # so we just removed it and continue the loop.


def generate_maze_task():
    """Task function to generate the maze using Prim's (runs in a thread)."""
    global generating, generation_complete, start_pos, end_pos, maze
    if not console: return
    with state_lock:
        if generating or solving: console.print("WARN: Generation/Solving already in progress."); return
        generating = True
        generation_complete = False
        solution_found = None

    logging.info("Starting maze generation task (Prim's)...")
    console.print("Generating maze (Prim's)...")
    start_time = time.time()
    try:
        initialize_maze_grid()

        # Call the Prim's generation function
        generate_maze_prims()

        # --- Set Start and End points (logic remains the same) ---
        # Try to find path cell on top edge for start
        start_pos = None
        for c in range(grid_width):
             if is_valid(0, c) and maze[0][c] == PATH_CHAR: start_pos = (0, c); break
        # If not found on top, try left edge
        if start_pos is None:
             for r in range(grid_height):
                  if is_valid(r, 0) and maze[r][0] == PATH_CHAR: start_pos = (r, 0); break
        # Fallback if no path found on top/left (shouldn't happen with Prim's from (0,0) effectively)
        if start_pos is None: start_pos = (0,0); maze[0][0] = PATH_CHAR # Ensure fallback is path
        maze[start_pos[0]][start_pos[1]] = START_CHAR
        if grid: grid.set_color(start_pos[1], start_pos[0], START_COLOR) # (x, y)

        # Try to find path cell on bottom edge for end
        end_pos = None
        for c in range(grid_width - 1, -1, -1):
             if is_valid(grid_height - 1, c) and maze[grid_height - 1][c] == PATH_CHAR: end_pos = (grid_height - 1, c); break
        # If not found on bottom, try right edge
        if end_pos is None:
            for r in range(grid_height-1, -1, -1):
                 if is_valid(r, grid_width-1) and maze[r][grid_width-1] == PATH_CHAR: end_pos = (r, grid_width-1); break
        # Fallback
        if end_pos is None: end_pos = (grid_height - 1, grid_width - 1); maze[end_pos[0]][end_pos[1]] = PATH_CHAR # Ensure fallback is path
        # Ensure start != end
        if end_pos == start_pos:
             # Try moving end left or up if overlapping and possible
             if is_valid(end_pos[0], end_pos[1]-1) and maze[end_pos[0]][end_pos[1]-1] == PATH_CHAR: end_pos = (end_pos[0], end_pos[1]-1)
             elif is_valid(end_pos[0]-1, end_pos[1]) and maze[end_pos[0]-1][end_pos[1]] == PATH_CHAR: end_pos = (end_pos[0]-1, end_pos[1])
             # If still overlapping, log warning but proceed
             if end_pos == start_pos: logging.warning("Could not separate start and end points.")
        maze[end_pos[0]][end_pos[1]] = END_CHAR
        if grid: grid.set_color(end_pos[1], end_pos[0], END_COLOR) # (x, y)

        elapsed = time.time() - start_time
        # Check if generation was interrupted before declaring completion
        with state_lock:
             if generating: # If still true, it finished normally
                  console.print(f"Maze generated in {elapsed:.2f} seconds.")
                  logging.info("Maze generation task finished.")
                  generation_complete = True
             else: # Flag was set to false externally
                  console.print(f"Maze generation interrupted after {elapsed:.2f} seconds.")
                  generation_complete = False # Ensure it's marked as not complete

    except Exception as e:
        logging.exception("Error during maze generation:")
        console.print(f"ERROR: Maze generation failed: {e}")
        generation_complete = False # Mark as not complete on error
    finally:
        with state_lock:
            generating = False # Ensure flag is reset


# ==================================
# == Maze Solving (DFS)           ==
# ==================================
def solve_maze_dfs(start_r: int, start_c: int, end_r: int, end_c: int) -> bool:
    """Solves the maze using DFS and visualizes the process."""
    global maze, grid
    if not grid or not console: return False

    stack: List[Tuple[int, int]] = [(start_r, start_c)]
    visited: Set[Tuple[int, int]] = set([(start_r, start_c)])
    path_taken: Dict[Tuple[int, int], Tuple[int, int]] = {} # Map: child -> parent

    while stack:
        with state_lock:
             if solving is False: console.print("Solver interrupted."); return False

        r, c = stack[-1] # Peek at the top

        # Visualize current exploration point (if not start)
        if (r,c) != (start_r, start_c):
            grid.set_color(c, r, CURRENT_COLOR) # (x, y)
            time.sleep(SOLVING_DELAY)

        # Check if we reached the end
        if r == end_r and c == end_c:
            logging.info("Solution found!")
            console.print("Solution found! Highlighting path...")
            curr = (end_r, end_c)
            while curr != (start_r, start_c):
                 if maze[curr[0]][curr[1]] != END_CHAR:
                      maze[curr[0]][curr[1]] = SOLUTION_CHAR
                      grid.set_color(curr[1], curr[0], SOLUTION_COLOR) # (x, y)
                      time.sleep(SOLVING_DELAY / 2)
                 # Move to the parent using the path_taken map
                 if curr in path_taken:
                      curr = path_taken[curr]
                 else:
                      logging.error(f"Path reconstruction error: Parent not found for {curr}")
                      break # Avoid infinite loop
            # Restore start color just in case it was overwritten by visualization
            if start_pos: grid.set_color(start_pos[1], start_pos[0], START_COLOR) # (x, y)
            return True

        # Explore neighbors
        found_next = False
        # Solver uses step=1 and does NOT check for walls (it checks maze char)
        for nr, nc in get_neighbors(r, c, step=1, check_wall=False):
            # Solver only moves to non-wall and unvisited cells
            if (nr, nc) not in visited and maze[nr][nc] != WALL_CHAR:
                visited.add((nr, nc))
                stack.append((nr, nc)) # Add to stack to explore next
                path_taken[(nr, nc)] = (r, c) # Record path: new cell came from current cell
                found_next = True
                break # Move to the new cell in the next loop iteration

        # If no unvisited non-wall neighbors, backtrack
        if not found_next:
            dead_end_r, dead_end_c = stack.pop()
            # Mark as visited (dead end), unless it's start/end
            if maze[dead_end_r][dead_end_c] not in [START_CHAR, END_CHAR]:
                 maze[dead_end_r][dead_end_c] = VISITED_CHAR
                 grid.set_color(dead_end_c, dead_end_r, VISITED_COLOR) # (x, y)
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
        # Reset visuals from previous solve/generation states
        if grid:
             console.print("Resetting visuals for solving...")
             for r in range(grid_height):
                  for c in range(grid_width):
                       char = maze[r][c]
                       # Reset visited/solution path cells back to normal path
                       if char == VISITED_CHAR or char == SOLUTION_CHAR:
                           maze[r][c] = PATH_CHAR
                           grid.set_color(c, r, PATH_COLOR) # (x, y)
                       # Ensure start/end/walls remain visible
                       elif char == START_CHAR: grid.set_color(c,r, START_COLOR)
                       elif char == END_CHAR: grid.set_color(c,r, END_COLOR)
                       elif char == WALL_CHAR: grid.set_color(c,r, WALL_COLOR)
             console.print("Visuals reset.")
        else:
             console.print("WARN: Grid not available for visual reset.")


        found = solve_maze_dfs(start_pos[0], start_pos[1], end_pos[0], end_pos[1])
        solution_found = found # Store result

        elapsed = time.time() - start_time
        # Check if interrupted vs. genuinely no solution
        with state_lock: was_interrupted = not solving
        if found: console.print(f"Maze solved in {elapsed:.2f} seconds.")
        elif was_interrupted: console.print(f"Maze solving interrupted after {elapsed:.2f} seconds.")
        else: console.print(f"No solution found after {elapsed:.2f} seconds.")

    except Exception as e:
        logging.exception("Error during maze solving:")
        console.print(f"ERROR: Maze solving failed: {e}")
        solution_found = False
    finally:
        with state_lock: solving = False # Ensure flag is reset


# ==================================
# == Sidekick Button Handlers     ==
# ==================================
def handle_generate_click(e):
    """Handles click on the Generate Maze button."""
    global solving, generating # Declare intention to modify global variables
    if not console: logging.error("Generate button handler called but console is None!"); return

    logging.debug("Generate button clicked")

    with state_lock:
        # Interrupt solver if running
        if solving: solving = False; console.print("Interrupting solver for new generation...")
        # Interrupt generation if running (though unlikely to click again)
        if generating: generating = False; console.print("Interrupting current generation...")
    # Start generation in a new thread
    gen_thread = threading.Thread(target=generate_maze_task, daemon=True)
    gen_thread.start()

def handle_solve_click(e):
    """Handles click on the Solve Maze button."""
    global solving, generating # Declare intention to modify global variables
    if not console: logging.error("Solve button handler called but console is None!"); return

    logging.debug("Solve button clicked")

    with state_lock:
        # Interrupt generation if running
        if generating: generating = False; console.print("Interrupting generator for solving...")
        # Interrupt solver if running (to restart it)
        if solving: solving = False; console.print("Interrupting current solver to restart...")
    # Start solving in a new thread
    solve_thread = threading.Thread(target=solve_maze_task, daemon=True)
    solve_thread.start()

# ==================================
# == Main Execution               ==
# ==================================
if __name__ == "__main__":
    try:
        row = Row()
        generate_btn = Button(text='Generate Maze (Prim\'s)', parent=row)
        generate_btn.on_click(handle_generate_click)
        solve_btn = Button(text='Solve Maze (DFS)', parent=row)
        solve_btn.on_click(handle_solve_click)

        grid = Grid(num_columns=grid_width, num_rows=grid_height)

        console = Console()
        console.print("Maze Generator & Solver Initialized.")
        console.print(f"Grid Size: {grid_width}x{grid_height}")

        logging.info("Main thread waiting. Use Sidekick controls or Ctrl+C to exit.")
        sidekick.run_forever()
    finally:
        logging.info("Initiating cleanup...")
        # Signal background threads to stop
        with state_lock: generating = False; solving = False
        logging.info("Generation/Solving flags set to False.")
        # Optional: Join threads if precise cleanup needed, but daemon threads exit anyway
        logging.info("Script finished.")
