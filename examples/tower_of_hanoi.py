import sidekick
import asyncio
from typing import List, Tuple, Optional, Callable, Dict, Any, AsyncIterator
from enum import Enum, auto

# --- Configuration ---
DEFAULT_NUM_DISKS = 3
MAX_DISKS_FOR_LAYOUT = 8
MOVE_DELAY = 0.5

# Disk Colors and Peg/Base colors
DISK_COLORS = ["#FFADAD", "#FFD6A5", "#FDFFB6", "#CAFFBF", "#9BF6FF", "#A0C4FF", "#BDB2FF", "#FFC6FF"]
PEG_COLOR = "#cccccc"
EMPTY_COLOR = None


# --- State Enum ---
class SolveState(Enum):
    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    FINISHED = auto()
    STOPPED = auto()


# ==================================
# Class 1: Visualizer (UI Only)
# ==================================
class HanoiVisualizer:
    """Handles all Sidekick UI interactions."""

    def __init__(self):
        self.grid: Optional[sidekick.Grid] = None
        self.controls_row: Optional[sidekick.Row] = None
        self.num_disks_input: Optional[sidekick.Textbox] = None
        self.start_pause_btn: Optional[sidekick.Button] = None
        self.status_console: Optional[sidekick.Console] = None
        self.grid_width = 0
        self.grid_height = 0
        self.peg_centers: List[int] = []
        self.peg_color_width = 1
        self.base_row_y = 0
        self.top_padding = 2
        self.base_disk_width = 3
        self.disk_width_factor = 2

    def setup_sidekick_ui(self, input_handler, click_handler):
        sidekick.clear_all()
        self.controls_row = sidekick.Row()
        self.num_disks_input = sidekick.Textbox(
            placeholder="Disks", value=str(DEFAULT_NUM_DISKS), parent=self.controls_row
        )
        self.num_disks_input.on_submit(input_handler)
        self.start_pause_btn = sidekick.Button(text="Start", parent=self.controls_row)
        self.start_pause_btn.on_click(click_handler)
        self.status_console = sidekick.Console(text="--- Hanoi Log ---\n")
        self.grid = None
        sidekick.logger.info("Sidekick UI components created.")

    def update_button_text(self, new_text: str):
        if self.start_pause_btn:
            self.start_pause_btn.text = new_text

    def calculate_and_init_grid(self, num_disks: int):
        sidekick.logger.info(f"Visualizer calculating layout for {num_disks} disks.")
        if num_disks <= 0: raise ValueError("Number of disks must be positive.")
        if num_disks > MAX_DISKS_FOR_LAYOUT: num_disks = MAX_DISKS_FOR_LAYOUT

        self.base_disk_width = 3
        self.disk_width_factor = 2
        spacing, side_padding, self.top_padding = 5, 4, 2
        peg_extra_height, base_row_height = 2, 1
        self.peg_color_width = 1
        min_width_per_peg = self.base_disk_width

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
            side_padding + 2 * width_per_peg + 2 * spacing + width_per_peg // 2,
        ]

        if self.grid: self.grid.remove()
        self.grid = sidekick.Grid(num_columns=self.grid_width, num_rows=self.grid_height)
        sidekick.logger.info(f"Grid created/recreated ({self.grid_width}x{self.grid_height})")

    def draw_pegs_and_base(self):
        if not self.grid: return
        self.grid.clear()
        for x in range(self.grid_width): self.grid.set_color(x, self.base_row_y, PEG_COLOR)
        for center_x in self.peg_centers:
            peg_start_x = center_x - self.peg_color_width // 2
            for x_peg in range(peg_start_x, peg_start_x + self.peg_color_width):
                for y in range(self.top_padding, self.base_row_y):
                    self.grid.set_color(x_peg, y, PEG_COLOR)

    def _get_disk_coords_and_width(self, disk_size: int, peg_index: int, disk_index_on_peg: int) -> Tuple[
        int, int, int]:
        center_x = self.peg_centers[peg_index]
        disk_visual_width = self.base_disk_width + (disk_size - 1) * self.disk_width_factor
        if disk_visual_width % 2 == 0: disk_visual_width += 1
        start_col = center_x - disk_visual_width // 2
        return self.base_row_y - 1 - disk_index_on_peg, start_col, start_col + disk_visual_width - 1

    def draw_disk(self, disk_size: int, peg_index: int, disk_index_on_peg: int):
        if not self.grid: return
        row, start_col, end_col = self._get_disk_coords_and_width(disk_size, peg_index, disk_index_on_peg)
        disk_color = DISK_COLORS[(disk_size - 1) % len(DISK_COLORS)]
        for x in range(start_col, end_col + 1):
            if 0 <= x < self.grid_width: self.grid.set_color(x, row, disk_color)

    def clear_disk(self, disk_size: int, peg_index: int, disk_index_on_peg: int):
        if not self.grid: return
        row, start_col, end_col = self._get_disk_coords_and_width(disk_size, peg_index, disk_index_on_peg)
        center_x = self.peg_centers[peg_index]
        for x in range(start_col, end_col + 1):
            if 0 <= x < self.grid_width:
                peg_start_x = center_x - self.peg_color_width // 2
                is_peg_cell = peg_start_x <= x < peg_start_x + self.peg_color_width
                self.grid.set_color(x, row, PEG_COLOR if is_peg_cell else EMPTY_COLOR)

    def draw_all_disks(self, pegs_state: List[List[int]]):
        if not self.grid: return
        for peg_index, disks_on_peg in enumerate(pegs_state):
            for disk_index, disk_size in enumerate(disks_on_peg):
                self.draw_disk(disk_size, peg_index, disk_index)

    def update_status(self, message: str):
        if self.status_console: self.status_console.print(message)


# ==================================
# Class 2: Solver (Algorithm Only)
# ==================================
MoveType = Tuple[int, int, int]  # from_peg, to_peg, disk_size

class HanoiSolver:
    """Encapsulates the async recursive Hanoi solving logic."""

    def __init__(self):
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    async def solve_generator(self, n: int, source: int, dest: int, aux: int) -> AsyncIterator[MoveType]:
        """Async generator that yields moves for the Tower of Hanoi problem."""
        if self._stop_requested: return
        if n > 0:
            async for move in self.solve_generator(n - 1, source, aux, dest):
                if self._stop_requested: return
                yield move

            if self._stop_requested: return
            yield (source, dest, n)

            async for move in self.solve_generator(n - 1, aux, dest, source):
                if self._stop_requested: return
                yield move


# ==================================
# Class 3: Controller (Orchestrator)
# ==================================
class HanoiController:
    """Manages game state and communication between Solver and Visualizer, asynchronously."""

    def __init__(self):
        self.visualizer = HanoiVisualizer()
        self.solver = HanoiSolver()
        self.num_disks = DEFAULT_NUM_DISKS
        self.pegs: List[List[int]] = []
        self.solve_state = SolveState.IDLE
        self._solve_task: Optional[asyncio.Task] = None

    def setup(self):
        """Initial setup of UI and game."""
        self.visualizer.setup_sidekick_ui(self.handle_input, self.handle_click)
        self.initialize_game(self.num_disks)

    def initialize_game(self, num_disks: int):
        self.visualizer.update_status(f"Initializing for {num_disks} disks...")
        self.stop_solve()  # Ensure any previous solve is stopped cleanly

        if num_disks > MAX_DISKS_FOR_LAYOUT:
            self.num_disks = MAX_DISKS_FOR_LAYOUT
            self.visualizer.update_status(f"Using max {self.num_disks} disks.")
        else:
            self.num_disks = num_disks

        self.visualizer.calculate_and_init_grid(self.num_disks)

        self.pegs = [[] for _ in range(3)]
        for i in range(self.num_disks, 0, -1): self.pegs[0].append(i)

        self.visualizer.draw_pegs_and_base()
        self.visualizer.draw_all_disks(self.pegs)
        self.set_state(SolveState.IDLE)  # This will now correctly set button to "Start"
        self.visualizer.update_status(f"Ready with {self.num_disks} disks.")

    def set_state(self, new_state: SolveState):
        if self.solve_state == new_state: return
        self.solve_state = new_state
        sidekick.logger.info(f"Controller state changed to: {new_state.name}")

        button_text = "Start"  # Default text
        if new_state == SolveState.IDLE:
            button_text = "Start"
        elif new_state == SolveState.RUNNING:
            button_text = "Pause"
        elif new_state == SolveState.PAUSED:
            button_text = "Resume"
        elif new_state in [SolveState.FINISHED, SolveState.STOPPED]:
            button_text = "Restart"

        self.visualizer.update_button_text(button_text)

    def handle_click(self, event: sidekick.ButtonClickEvent):
        """Handles button clicks: Start/Pause/Resume/Restart."""
        if self.solve_state in [SolveState.IDLE, SolveState.FINISHED, SolveState.STOPPED]:
            self.start_solve()
        elif self.solve_state == SolveState.RUNNING:
            self.pause_solve()
        elif self.solve_state == SolveState.PAUSED:
            self.resume_solve()

    def handle_input(self, event: sidekick.TextboxSubmitEvent):
        """Handles disk number input and resets the game."""
        try:
            num_disks_input = int(event.value)
            if num_disks_input <= 0:
                self.visualizer.update_status("Number of disks must be positive.")
                return
            self.initialize_game(num_disks_input)
        except ValueError:
            self.visualizer.update_status(f"Invalid input: '{event.value}'. Please enter a number.")

    def start_solve(self):
        if self.solve_state not in [SolveState.IDLE, SolveState.FINISHED, SolveState.STOPPED]: return
        self.initialize_game(self.num_disks)  # Reset board before starting
        self.set_state(SolveState.RUNNING)
        self.visualizer.update_status(f"--- Solving for {self.num_disks} disks START ---")

        # We run the solving logic in a dedicated coroutine
        self._solve_task = sidekick.submit_task(self._run_solve_loop())

    async def _run_solve_loop(self):
        """The main async loop that gets moves and animates them."""
        self.solver = HanoiSolver()  # Create a fresh solver instance
        try:
            # The async generator yields one move at a time
            async for from_peg, to_peg, disk_size in self.solver.solve_generator(self.num_disks, 0, 2, 1):
                if self.solve_state == SolveState.PAUSED:
                    # If paused, wait until state changes
                    await self.wait_for_resume()

                if self.solve_state == SolveState.STOPPED:
                    break

                # Animate the move
                self.animate_move(from_peg, to_peg, disk_size)

                # Wait for the next frame
                await asyncio.sleep(MOVE_DELAY)

            # Check if the loop finished naturally or was stopped
            if self.solve_state != SolveState.STOPPED:
                self.visualizer.update_status("--- Solve Complete! ---")
                self.set_state(SolveState.FINISHED)

        except asyncio.CancelledError:
            sidekick.logger.info("Solve loop task was cancelled.")
            # The state should already be STOPPED from the stop_solve method
        except Exception as e:
            self.visualizer.update_status(f"--- Solver Error: {e} ---")
            sidekick.logger.exception("Error in solve loop")
            self.set_state(SolveState.IDLE)

    def animate_move(self, from_peg: int, to_peg: int, disk_size: int):
        """Applies a single move to the state and visualizer."""
        # Update internal state
        from_peg_index = len(self.pegs[from_peg]) - 1
        popped_disk = self.pegs[from_peg].pop()
        to_peg_index = len(self.pegs[to_peg])
        self.pegs[to_peg].append(popped_disk)

        # Update visuals
        self.visualizer.update_status(f"Move disk {disk_size} from {from_peg + 1} to {to_peg + 1}")
        self.visualizer.clear_disk(disk_size, from_peg, from_peg_index)
        self.visualizer.draw_disk(disk_size, to_peg, to_peg_index)

    def pause_solve(self):
        if self.solve_state != SolveState.RUNNING: return
        self.set_state(SolveState.PAUSED)
        self.visualizer.update_status("Paused.")

    def resume_solve(self):
        if self.solve_state != SolveState.PAUSED: return
        self.set_state(SolveState.RUNNING)
        self.visualizer.update_status("Resumed.")

    def stop_solve(self):
        """Requests the async solver task to stop."""
        task_was_running = self._solve_task and not self._solve_task.done()
        if task_was_running:
            sidekick.logger.info("Requesting solver task stop...")
            self.solver.stop()  # Signal the generator to stop yielding
            self._solve_task.cancel()
            self.visualizer.update_status("--- Solve Stopped/Reset ---")
            self.set_state(SolveState.STOPPED)
        self._solve_task = None

    async def wait_for_resume(self):
        """Asynchronously waits until the state is no longer PAUSED."""
        while self.solve_state == SolveState.PAUSED:
            if self.solver._stop_requested: break
            await asyncio.sleep(0.1)  # Check every 100ms without blocking


# --- Main Execution ---
if __name__ == "__main__":
    controller = HanoiController()
    controller.setup()
    sidekick.run_forever()
