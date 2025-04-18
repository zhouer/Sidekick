import sidekick
import time
import threading
import sys
from typing import List, Tuple, Optional, Callable, Iterator, Dict, Any
from enum import Enum, auto

# --- Configuration ---
DEFAULT_NUM_DISKS = 3
MAX_DISKS_FOR_LAYOUT = 8
MOVE_DELAY = 0.5 # Adjusted delay

# Disk Colors
DISK_COLORS = [
    "#FFADAD", "#FFD6A5", "#FDFFB6", "#CAFFBF", "#9BF6FF",
    "#A0C4FF", "#BDB2FF", "#FFC6FF", "#ff8fab", "#f8ad9d"
]
PEG_COLOR = "#cccccc" # Light gray for pegs/base
EMPTY_COLOR = None    # Use default background for empty cells

# --- State Enum ---
class SolveState(Enum):
    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    FINISHED = auto()

# ==================================
# Class 1: Visualizer (UI Only)
# ==================================
class HanoiVisualizer:
    """Handles all Sidekick UI interactions."""
    def __init__(self):
        self.grid: Optional[sidekick.Grid] = None
        self.controls: Optional[sidekick.Control] = None
        self.status_console: Optional[sidekick.Console] = None
        self.grid_width = 0
        self.grid_height = 0
        self.peg_centers: List[int] = []
        self.peg_color_width = 1
        self.base_row_y = 0
        self.top_padding = 0
        self.base_disk_width = 3
        self.disk_width_factor = 2

        # Store control state locally for update workaround
        self._control_configs: Dict[str, Dict[str, Any]] = {}

    def setup_sidekick_ui(self, input_handler, click_handler):
        """Creates initial Sidekick controls and console."""
        sidekick.clear_all()

        self.controls = sidekick.Control()
        # Store config before adding for potential updates later
        self._add_control_config("num_disks", control_type="textInput", text=str(DEFAULT_NUM_DISKS), button_text="Set & Reset", placeholder="Disks:")
        self._add_control_config("start_pause", control_type="button", text="Start")

        # Add controls to Sidekick UI
        self.controls.add_text_input("num_disks", placeholder=self._control_configs["num_disks"]["config"].get("placeholder",""), initial_value=self._control_configs["num_disks"]["config"]["text"], button_text=self._control_configs["num_disks"]["config"]["button_text"])
        self.controls.add_button("start_pause", self._control_configs["start_pause"]["config"]["text"])

        # Register handlers
        self.controls.on_input_text(input_handler)
        self.controls.on_click(click_handler)
        self.controls.on_error(lambda msg: sidekick.logger.error(f"Controls Error: {msg}"))

        self.status_console = sidekick.Console(initial_text="--- Hanoi Log ---") # Initial title
        self.status_console.on_error(lambda msg: sidekick.logger.error(f"Status Console Error: {msg}"))

        self.grid = None
        sidekick.logger.info("Sidekick UI modules (controls, status) created.")

    def _add_control_config(self, control_id: str, control_type: str, text: str, **kwargs):
        """Stores control configuration."""
        # Ensure kwargs are serializable if needed, though not strictly required here
        config = {"text": text, **kwargs}
        self._control_configs[control_id] = {
            "controlType": control_type,
            "config": config
        }

    def update_button_text(self, control_id: str, new_text: str):
        """Updates button text (workaround: removes and re-adds)."""
        if not self.controls or control_id not in self._control_configs or self._control_configs[control_id]["controlType"] != "button":
             sidekick.logger.warning(f"Cannot update text for non-existent or non-button control: {control_id}")
             return
        try:
            # Update stored config first
            self._control_configs[control_id]["config"]["text"] = new_text
            # Remove and re-add the button in Sidekick
            self.controls.remove_control(control_id)
            self.controls.add_button(control_id, new_text)
            sidekick.logger.debug(f"Updated button '{control_id}' text to '{new_text}'")
        except Exception as e:
             sidekick.logger.error(f"Error updating button text for '{control_id}': {e}")


    def calculate_and_init_grid(self, num_disks: int):
        """Calculates layout and creates/recreates the Sidekick Grid."""
        sidekick.logger.info(f"Visualizer calculating layout for {num_disks} disks.")
        if num_disks <= 0: raise ValueError("Number of disks must be positive.")
        if num_disks > MAX_DISKS_FOR_LAYOUT: num_disks = MAX_DISKS_FOR_LAYOUT

        # --- Layout Constants ---
        self.base_disk_width = 3
        self.disk_width_factor = 2
        spacing = 5
        side_padding = 4
        self.top_padding = 2
        peg_extra_height = 2
        self.peg_color_width = 1
        base_row_height = 1
        min_width_per_peg = self.base_disk_width

        # --- Calculations ---
        max_disk_width = self.base_disk_width + (num_disks - 1) * self.disk_width_factor
        if max_disk_width % 2 == 0: max_disk_width += 1
        width_per_peg = max(max_disk_width, min_width_per_peg)
        if width_per_peg % 2 == 0: width_per_peg += 1

        self.grid_width = (3 * width_per_peg) + (2 * spacing) + (2 * side_padding)
        self.grid_height = num_disks + peg_extra_height + base_row_height + self.top_padding
        self.base_row_y = self.grid_height - base_row_height

        self.peg_centers = [
            side_padding + width_per_peg // 2,
            side_padding + width_per_peg + spacing + width_per_peg // 2,
            side_padding + 2 * width_per_peg + 2 * spacing + width_per_peg // 2
        ]

        # --- Create/Recreate Grid ---
        if self.grid:
            try: self.grid.remove()
            except Exception as e: sidekick.logger.warning(f"Could not remove previous grid: {e}")
        try:
            self.grid = sidekick.Grid(num_columns=self.grid_width, num_rows=self.grid_height)
            self.grid.on_error(lambda msg: sidekick.logger.error(f"Grid Error: {msg}"))
            sidekick.logger.info(f"Grid created/recreated ({self.grid_width}x{self.grid_height})")
        except sidekick.SidekickConnectionError as e:
             self.update_status(f"Connection Error creating grid: {e}")
             raise
        except Exception as e:
             self.update_status(f"Error creating grid: {e}")
             sidekick.logger.exception("Error creating grid")
             raise RuntimeError("Failed to create grid") from e

    def draw_pegs_and_base(self):
        """Draws the static elements (base, pegs)."""
        if not self.grid: return
        sidekick.logger.debug("Drawing pegs and base")
        self.grid.clear() # Clear everything first
        # Draw Base
        for x in range(self.grid_width):
            self.grid.set_color(x, self.base_row_y, PEG_COLOR)
        # Draw Pegs
        for center_x in self.peg_centers:
            peg_start_x = center_x - self.peg_color_width // 2
            peg_end_x = center_x + self.peg_color_width // 2
            for x_peg in range(peg_start_x, peg_end_x + 1):
                if 0 <= x_peg < self.grid_width:
                    # Draw from TOP_PADDING down to the base row
                    for y in range(self.top_padding, self.base_row_y):
                        self.grid.set_color(x_peg, y, PEG_COLOR)

    def _get_disk_coords_and_width(self, disk_size: int, peg_index: int, disk_index_on_peg: int) -> Tuple[int, int, int]:
        """Calculates the row, start/end columns for a specific disk."""
        center_x = self.peg_centers[peg_index]
        disk_visual_width = self.base_disk_width + (disk_size - 1) * self.disk_width_factor
        if disk_visual_width % 2 == 0: disk_visual_width +=1

        start_col = center_x - disk_visual_width // 2
        end_col = center_x + disk_visual_width // 2
        row = self.base_row_y - 1 - disk_index_on_peg
        return row, start_col, end_col

    def draw_disk(self, disk_size: int, peg_index: int, disk_index_on_peg: int):
        """Draws a single disk at the specified position."""
        if not self.grid: return
        try:
            row, start_col, end_col = self._get_disk_coords_and_width(disk_size, peg_index, disk_index_on_peg)
            disk_color = DISK_COLORS[(disk_size - 1) % len(DISK_COLORS)]

            if row >= 0:
                for x in range(start_col, end_col + 1):
                    if 0 <= x < self.grid_width:
                        self.grid.set_color(x, row, disk_color)
        except IndexError:
             sidekick.logger.error(f"Error drawing disk: peg_index={peg_index}, centers={len(self.peg_centers)}")
        except Exception as e:
             sidekick.logger.error(f"Unexpected error drawing disk {disk_size} at peg {peg_index}: {e}")

    def clear_disk(self, disk_size: int, peg_index: int, disk_index_on_peg: int):
        """Clears the area where a disk was, revealing the peg/base."""
        if not self.grid: return
        try:
            row, start_col, end_col = self._get_disk_coords_and_width(disk_size, peg_index, disk_index_on_peg)
            center_x = self.peg_centers[peg_index]

            if row >= 0:
                for x in range(start_col, end_col + 1):
                    if 0 <= x < self.grid_width:
                         peg_start_x = center_x - self.peg_color_width // 2
                         peg_end_x = center_x + self.peg_color_width // 2
                         is_peg_cell = peg_start_x <= x <= peg_end_x
                         color_to_set = PEG_COLOR if is_peg_cell else EMPTY_COLOR
                         self.grid.set_color(x, row, color_to_set)
        except IndexError:
             sidekick.logger.error(f"Error clearing disk: peg_index={peg_index}, centers={len(self.peg_centers)}")
        except Exception as e:
            sidekick.logger.error(f"Unexpected error clearing disk {disk_size} at peg {peg_index}: {e}")

    def draw_all_disks(self, pegs_state: List[List[int]]):
        """Draws all disks based on the provided state."""
        if not self.grid: return
        sidekick.logger.debug("Drawing all disks")
        for peg_index, disks_on_peg in enumerate(pegs_state):
            for disk_index, disk_size in enumerate(disks_on_peg):
                self.draw_disk(disk_size, peg_index, disk_index)

    def update_status(self, message: str):
        """Appends a message to the status console."""
        if self.status_console:
            # Keep history, add newline
            self.status_console.print(message, end='\n')
        sidekick.logger.info(f"Status: {message}")

# ==================================
# Class 2: Solver (Algorithm Only)
# ==================================
MoveType = Tuple[int, int, int] # from_peg, to_peg, disk_size

class HanoiSolver:
    """Encapsulates the recursive Hanoi solving logic with pause/stop."""
    def __init__(self, move_callback: Callable[[MoveType], None]):
        self._stop_request = threading.Event()
        self._paused = threading.Event() # True when paused, clear to resume
        self._move_callback = move_callback

    def pause(self):
        """Signals the solver to pause."""
        self._paused.set()
        sidekick.logger.info("Solver pause requested.")

    def resume(self):
        """Signals the solver to resume."""
        self._paused.clear()
        sidekick.logger.info("Solver resume requested.")

    def stop(self):
        """Signals the solver to stop."""
        self._stop_request.set()
        self._paused.clear() # Ensure it's not stuck waiting if stopped while paused
        sidekick.logger.info("Solver stop requested.")

    @property
    def is_stop_requested(self):
        return self._stop_request.is_set()

    @property
    def is_paused(self):
        return self._paused.is_set()

    def wait_if_paused(self):
         """Blocks if paused, checking stop signal periodically."""
         if self._paused.is_set():
             sidekick.logger.debug(f"Solver paused, waiting...")
             while self._paused.is_set():
                 if self._stop_request.is_set():
                      sidekick.logger.debug("Solver stopping while paused.")
                      return True # Indicate stopped
                 time.sleep(0.1)
             sidekick.logger.debug(f"Solver resumed.")
             # Check stop again immediately after resuming
             if self._stop_request.is_set():
                  sidekick.logger.debug("Solver stopping after resuming.")
                  return True # Indicate stopped
         return False # Indicate not stopped

    def solve(self, n: int, source: int, destination: int, auxiliary: int):
        """Starts the recursive solving process."""
        sidekick.logger.info(f"Solver starting: n={n}, src={source}, dest={destination}, aux={auxiliary}")
        self._stop_request.clear()
        self._paused.clear()
        try:
            for move in self._hanoi_recursive(n, source, destination, auxiliary):
                # Check stop signal *before* calling the callback
                if self.is_stop_requested:
                    sidekick.logger.info("Solver stopping during iteration.")
                    break

                # Callback handles the move, delay, AND pause waiting
                self._move_callback(move)

                # Check stop signal *after* the callback returns
                if self.is_stop_requested:
                    sidekick.logger.info("Solver stopping after move callback returned.")
                    break

        except Exception as e:
             sidekick.logger.exception("Error during Hanoi solve recursion")
             self._stop_request.set() # Ensure stop on error
        finally:
             sidekick.logger.info("Solver finished or stopped.")
             self._stop_request.set()
             self._paused.clear() # Ensure not left paused on exit

    def _hanoi_recursive(self, n: int, source: int, destination: int, auxiliary: int) -> Iterator[MoveType]:
        """Recursive generator yielding moves (from, to, disk_n)."""
        if self.is_stop_requested: return
        stopped_while_paused = self.wait_if_paused()
        if stopped_while_paused or self.is_stop_requested: return

        if n > 0:
            # Move n-1 disks from source to auxiliary
            yield from self._hanoi_recursive(n - 1, source, auxiliary, destination)
            if self.is_stop_requested: return

            # Check pause/stop again before yielding the actual move
            stopped_while_paused = self.wait_if_paused()
            if stopped_while_paused or self.is_stop_requested: return

            # Yield the move for the nth disk
            yield (source, destination, n) # Disk number is n here
            if self.is_stop_requested: return # Check immediately after yielding

            # Move n-1 disks from auxiliary to destination
            yield from self._hanoi_recursive(n - 1, auxiliary, destination, source)
            if self.is_stop_requested: return

# ==================================
# Class 3: Controller (Orchestrator)
# ==================================
class HanoiController:
    """Manages game state, threads, and communication between Solver and Visualizer."""
    def __init__(self):
        self.visualizer = HanoiVisualizer()
        # Pass the method reference for the callback
        self.solver = HanoiSolver(move_callback=self._handle_solver_move)
        self.num_disks = DEFAULT_NUM_DISKS
        self.pegs: List[List[int]] = []
        self.solve_state = SolveState.IDLE
        self._solve_thread: Optional[threading.Thread] = None
        # Lock for safely modifying pegs state from different threads
        self._state_lock = threading.Lock()

    def setup(self):
        """Initial setup of UI and game."""
        try:
            self.visualizer.setup_sidekick_ui(
                input_handler=self.handle_control_input,
                click_handler=self.handle_control_click
            )
            self.initialize_game(self.num_disks)
        except sidekick.SidekickConnectionError as e:
             print(f"\nConnection Error during setup: {e}", file=sys.stderr)
             raise # Propagate connection error to main loop
        except Exception as e:
             sidekick.logger.exception("Error during controller setup")
             print(f"\nError during setup: {e}", file=sys.stderr)
             # Might want to exit or handle differently
             raise


    def initialize_game(self, num_disks: int):
        """Resets game state and visuals."""
        self.visualizer.update_status(f"Initializing for {num_disks} disks...")
        self.stop_solver_thread() # Ensure any previous solve is stopped cleanly

        try:
            # Determine actual number of disks respecting MAX limit
            if num_disks > MAX_DISKS_FOR_LAYOUT:
                 self.num_disks = MAX_DISKS_FOR_LAYOUT
                 self.visualizer.update_status(f"Using max {self.num_disks} disks.")
            elif num_disks <= 0:
                 self.visualizer.update_status("Number of disks must be positive.")
                 return # Don't proceed with invalid disk count
            else:
                 self.num_disks = num_disks

            # Calculate layout and recreate grid via visualizer
            self.visualizer.calculate_and_init_grid(self.num_disks)

        except RuntimeError as e: # Catch grid creation error
             self.visualizer.update_status(f"Initialization failed: {e}")
             return
        except Exception as e:
             self.visualizer.update_status(f"Layout/Init Error: {e}")
             sidekick.logger.exception("Error initializing game layout/grid")
             return

        # Initialize peg state
        with self._state_lock:
            self.pegs = [[] for _ in range(3)]
            for i in range(self.num_disks, 0, -1):
                self.pegs[0].append(i)

        # Initial Draw
        self.visualizer.draw_pegs_and_base()
        self.visualizer.draw_all_disks(self.pegs)
        self.set_state(SolveState.IDLE) # Reset state machine
        self.visualizer.update_status(f"Ready with {self.num_disks} disks.")

    def set_state(self, new_state: SolveState):
        """Updates the controller state and the button text."""
        if self.solve_state == new_state: return # Avoid redundant updates
        self.solve_state = new_state
        sidekick.logger.info(f"Controller state changed to: {new_state.name}")
        button_text = "Start"
        if new_state == SolveState.RUNNING: button_text = "Pause"
        elif new_state == SolveState.PAUSED: button_text = "Resume"
        elif new_state == SolveState.FINISHED: button_text = "Start" # Ready for new game
        try:
            self.visualizer.update_button_text("start_pause", button_text)
        except sidekick.SidekickConnectionError as e:
            sidekick.logger.error(f"Connection error updating button text: {e}")
            # Handle connection loss gracefully if needed


    def handle_control_click(self, control_id: str):
        """Handles button clicks: Start/Pause/Resume."""
        if control_id == "start_pause":
            if self.solve_state == SolveState.IDLE or self.solve_state == SolveState.FINISHED:
                self.start_solve()
            elif self.solve_state == SolveState.RUNNING:
                self.pause_solve()
            elif self.solve_state == SolveState.PAUSED:
                self.resume_solve()

    def handle_control_input(self, control_id: str, value: str):
        """Handles disk number input and reset."""
        if control_id == "num_disks":
            # Attempt to stop cleanly before re-initializing
            # stop_solver_thread() will update state to IDLE if it stops something
            current_state_before_stop = self.solve_state
            self.stop_solver_thread()
            # If stopping failed or was already idle, ensure state is IDLE before init
            if self._solve_thread and self._solve_thread.is_alive():
                 self.visualizer.update_status("Failed to stop previous solve. Cannot reset.")
                 return
            if current_state_before_stop != SolveState.IDLE:
                 self.set_state(SolveState.IDLE) # Explicitly set IDLE after stop

            try:
                num_disks_input = int(value)
                self.initialize_game(num_disks_input) # Handles validation inside
            except ValueError:
                self.visualizer.update_status(f"Invalid input: '{value}'. Please enter a number.")
            except Exception as e:
                 self.visualizer.update_status(f"Error setting disks: {e}")
                 sidekick.logger.exception("Error handling disk input")

    def start_solve(self):
        """Starts a new solve process in a thread."""
        if self.solve_state not in [SolveState.IDLE, SolveState.FINISHED]:
            sidekick.logger.warning(f"Cannot start solve, state is {self.solve_state.name}.")
            return
        if not self.visualizer.grid or self.num_disks == 0:
             self.visualizer.update_status("Please initialize with disks first.")
             return

        self.stop_solver_thread() # Ensure no old thread lingers

        self.visualizer.update_status(f"--- Solving for {self.num_disks} disks START ---")
        self.set_state(SolveState.RUNNING)

        def solve_thread_target():
            try:
                self.solver.solve(self.num_disks, 0, 2, 1)
            except Exception as e:
                sidekick.logger.exception("Exception escaped from solver thread target")
                # Ensure state reflects the issue
                self.set_state(SolveState.IDLE) # Or an ERROR state if defined
                self.visualizer.update_status(f"--- Solver Error: {e} ---")
                return # Exit thread on error

            # Check if stopped externally vs finished naturally
            final_state = SolveState.FINISHED if not self.solver.is_stop_requested else SolveState.IDLE
            self.set_state(final_state)
            if final_state == SolveState.FINISHED:
                self.visualizer.update_status("--- Solve Complete! ---")
            else:
                self.visualizer.update_status("--- Solve Stopped/Reset ---")


        self._solve_thread = threading.Thread(target=solve_thread_target, daemon=True)
        self._solve_thread.start()

    def pause_solve(self):
        """Signals the solver thread to pause."""
        if self.solve_state != SolveState.RUNNING or not self._solve_thread or not self._solve_thread.is_alive():
             sidekick.logger.warning("Cannot pause, not running.")
             return
        self.solver.pause()
        self.set_state(SolveState.PAUSED)
        self.visualizer.update_status("Paused.")

    def resume_solve(self):
        """Signals the solver thread to resume."""
        if self.solve_state != SolveState.PAUSED:
             sidekick.logger.warning("Cannot resume, not paused.")
             return
        self.solver.resume()
        self.set_state(SolveState.RUNNING)
        self.visualizer.update_status("Resumed.")

    def stop_solver_thread(self):
        """Requests the solver thread to stop and waits briefly."""
        if self._solve_thread and self._solve_thread.is_alive():
            sidekick.logger.info("Requesting solver thread stop...")
            self.solver.stop() # Signal the solver first
            self._solve_thread.join(timeout=0.2) # Slightly longer wait
            if self._solve_thread.is_alive():
                 sidekick.logger.warning("Solver thread did not stop quickly.")
                 # Consider stronger interrupt if needed, but risky
            else:
                 sidekick.logger.info("Solver thread stopped.")
        self._solve_thread = None
        # If stopping actively running/paused solve, reset state to IDLE
        if self.solve_state not in [SolveState.IDLE, SolveState.FINISHED]:
             self.set_state(SolveState.IDLE)

    def _handle_solver_move(self, move: MoveType):
        """Callback executed by Solver thread when a move should occur."""
        # Check stop signal early
        if self.solver.is_stop_requested: return

        from_peg, to_peg, disk_size = move
        popped_disk = -1
        from_peg_index = -1
        to_peg_index = -1

        try:
            # Update internal state (Protected)
            with self._state_lock:
                if not self.pegs[from_peg]:
                    raise ValueError(f"Solver requested move from empty peg {from_peg}")
                from_peg_index = len(self.pegs[from_peg]) - 1
                popped_disk = self.pegs[from_peg].pop()

                if popped_disk != disk_size:
                    self.pegs[from_peg].append(popped_disk) # Put back
                    raise ValueError(f"Solver yielded disk {disk_size} but found {popped_disk} on peg {from_peg}")

                to_peg_index = len(self.pegs[to_peg])
                self.pegs[to_peg].append(popped_disk)

            # Check stop signal after state change, before UI/delay
            if self.solver.is_stop_requested: return

            # --- Visual Updates ---
            # Use try-except around UI calls to prevent UI errors from stopping solver logic
            try:
                self.visualizer.update_status(f"Move disk {disk_size} from {from_peg+1} to {to_peg+1}")
                self.visualizer.clear_disk(disk_size, from_peg, from_peg_index)
                self.visualizer.draw_disk(disk_size, to_peg, to_peg_index)
            except sidekick.SidekickConnectionError as e_vis:
                sidekick.logger.error(f"Connection error during visualization: {e_vis}")
                self.solver.stop() # Stop solver if UI connection lost
                return # Don't proceed with delay if UI failed
            except Exception as e_vis:
                sidekick.logger.exception(f"Error during visualization update for move {move}")
                # Optionally stop solver on vis error, or just log and continue? Stopping is safer.
                self.solver.stop()
                return

            # --- Pause Check Location (before delay) ---
            stopped_while_paused = self.solver.wait_if_paused()
            if stopped_while_paused or self.solver.is_stop_requested:
                 sidekick.logger.info("Move handler stopping (during/after pause check).")
                 return # Exit handler if stopped/paused

            # --- Delay ---
            # Check stop signal *again* right before sleeping
            if self.solver.is_stop_requested:
                 sidekick.logger.info("Move handler stopping before delay.")
                 return

            time.sleep(MOVE_DELAY)

        except Exception as e:
             sidekick.logger.exception(f"Error handling solver move {move}")
             self.visualizer.update_status(f"Error processing move: {e}")
             self.solver.stop() # Signal solver to stop on error


# --- Main Execution ---
if __name__ == "__main__":
    controller = HanoiController()
    controller.setup()
    sidekick.run_forever()
    controller.stop_solver_thread()
