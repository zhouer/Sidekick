# hero_test_cases.py
import time
import random
import threading
from typing import Dict, Any
from sidekick import (
    set_url,
    close_connection,
    Grid,
    Console,
    Viz,
    Canvas,
    ObservableValue
)
import logging

# --- Configuration ---
SIDEKICK_URL = "ws://localhost:5163" # Default URL
TEST_DURATION_SECONDS = 60 # How long the main loop runs
LOG_LEVEL = logging.DEBUG # Set to INFO for less verbose output

# --- Setup Logging ---
# Configure root logger or specific loggers
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logging.getLogger("SidekickConn").setLevel(LOG_LEVEL)
logging.getLogger("HeroTest").setLevel(LOG_LEVEL)
logger = logging.getLogger("HeroTest")

# --- Global Variables for Modules (for interaction) ---
grid_module: Grid | None = None
console_module: Console | None = None
viz_module: Viz | None = None
canvas_module: Canvas | None = None
obs_counter: ObservableValue | None = None
obs_list: ObservableValue | None = None
obs_dict: ObservableValue | None = None
obs_set: ObservableValue | None = None
obs_complex: ObservableValue | None = None

# --- Callback Functions ---

def handle_console_input(msg: Dict[str, Any]):
    """Callback for handling messages from the Console module."""
    global obs_counter, obs_list, obs_dict, obs_set, obs_complex, grid_module
    payload = msg.get('payload', {})
    event = payload.get('event')

    if event == 'submit':
        value = payload.get('value', '').strip().lower()
        logger.info(f"Console Input Received: '{value}'")
        if console_module:
            console_module.print(f"> You entered: {value}") # Echo input

        # --- Trigger various actions based on input ---
        if value == 'inc' and obs_counter is not None:
            obs_counter.set(obs_counter.get() + 1)
            logger.info("Incremented counter.")
        elif value == 'dec' and obs_counter is not None:
            obs_counter.set(obs_counter.get() - 1)
            logger.info("Decremented counter.")
        elif value == 'add_list' and obs_list is not None:
            new_item = f"item_{len(obs_list)}"
            obs_list.append(new_item)
            logger.info(f"Appended '{new_item}' to list.")
        elif value == 'pop_list' and obs_list is not None and len(obs_list) > 0:
            popped = obs_list.pop()
            logger.info(f"Popped '{popped}' from list.")
        elif value == 'change_list' and obs_list is not None and len(obs_list) > 0:
            index_to_change = random.randint(0, len(obs_list) - 1)
            obs_list[index_to_change] = f"changed_{random.randint(100, 999)}"
            logger.info(f"Changed list item at index {index_to_change}.")
        elif value == 'add_dict' and obs_dict is not None:
            new_key = f"key_{random.randint(1, 100)}"
            obs_dict[new_key] = random.random()
            logger.info(f"Added/Updated key '{new_key}' in dict.")
        elif value == 'del_dict' and obs_dict is not None and len(obs_dict) > 0:
            key_to_delete = random.choice(list(obs_dict.get().keys()))
            del obs_dict[key_to_delete]
            logger.info(f"Deleted key '{key_to_delete}' from dict.")
        elif value == 'add_set' and obs_set is not None:
             item = random.randint(1, 20)
             obs_set.add(item) # Automatically handles duplicates
             logger.info(f"Added {item} to set.")
        elif value == 'discard_set' and obs_set is not None and len(obs_set) > 0:
             item = random.choice(list(obs_set.get()))
             obs_set.discard(item)
             logger.info(f"Discarded {item} from set.")
        elif value == 'clear_list' and obs_list is not None:
            obs_list.clear()
            logger.info("Cleared list.")
        elif value == 'clear_dict' and obs_dict is not None:
            obs_dict.clear()
            logger.info("Cleared dict.")
        elif value == 'clear_set' and obs_set is not None:
            obs_set.clear()
            logger.info("Cleared set.")
        elif value == 'change_complex' and obs_complex is not None:
            # Example of modifying nested structure (requires careful handling)
            current_complex = obs_complex.get()
            current_complex['nested_list'].append(random.randint(1000,2000))
            current_complex['nested_dict']['c'] = time.time()
            # MUST call .set() to notify if the outer structure was modified
            # or if nested parts are not ObservableValues themselves.
            obs_complex.set(current_complex)
            logger.info("Modified complex observable.")
        elif value == 'fill_grid' and grid_module:
             color = random.choice(['red', 'green', 'blue', 'yellow', 'purple', 'orange', 'cyan', 'lightgrey'])
             grid_module.fill(color)
             logger.info(f"Filled grid with {color}")
        elif value == 'clear_grid' and grid_module:
             grid_module.fill('white') # Assuming white is the default clear color
             logger.info("Cleared grid")
        elif value == 'remove_counter' and viz_module:
            viz_module.remove_variable("Counter")
            logger.info("Removed 'Counter' from Viz.")
        elif value == 'readd_counter' and viz_module and obs_counter:
            viz_module.show("Counter", obs_counter) # Re-add
            logger.info("Re-added 'Counter' to Viz.")
        elif value == 'help':
            if console_module:
                 console_module.print("\n--- Available Commands ---")
                 console_module.print("inc / dec        : Modify Counter")
                 console_module.print("add_list / pop_list / change_list / clear_list")
                 console_module.print("add_dict / del_dict / clear_dict")
                 console_module.print("add_set / discard_set / clear_set")
                 console_module.print("change_complex   : Modify complex observable")
                 console_module.print("fill_grid / clear_grid")
                 console_module.print("remove_counter / readd_counter")
                 console_module.print("help             : Show this message")
                 console_module.print("--------------------------\n")
        else:
             if console_module:
                 console_module.print(f"Unknown command: '{value}'. Type 'help' for options.")

def handle_grid_click(msg: Dict[str, Any]):
    """Callback for handling messages from the Grid module."""
    global console_module, grid_module
    payload = msg.get('payload', {})
    event = payload.get('event')

    if event == 'click' and grid_module:
        x, y = payload.get('x'), payload.get('y')
        logger.info(f"Grid Click Received: ({x}, {y})")
        if console_module:
            console_module.print(f"Grid clicked at: x={x}, y={y}")
        # Example interaction: Change clicked cell color
        color = random.choice(['magenta', 'cyan', 'lime', 'pink'])
        grid_module.set_color(x, y, color)
        grid_module.set_text(x, y, f"{x},{y}")

# --- Test Setup Function ---
def setup_sidekick_modules():
    """Creates and initializes all Sidekick modules for testing."""
    global grid_module, console_module, viz_module, canvas_module
    global obs_counter, obs_list, obs_dict, obs_set, obs_complex

    logger.info("--- Setting up Sidekick Modules ---")

    try:
        # 1. Grid Module
        logger.info("Creating Grid...")
        grid_module = Grid(width=12, height=8, instance_id="test-grid", on_message=handle_grid_click)
        grid_module.fill("white")
        grid_module.set_text(0, 0, "Click!")
        logger.info("Grid created.")
        time.sleep(0.1) # Small delay between module spawns

        # 2. Console Module
        logger.info("Creating Console...")
        console_module = Console(instance_id="test-console", on_message=handle_console_input)
        console_module.print("Welcome to Sidekick Test Suite!")
        console_module.log("Console module ready. Type 'help' for commands.")
        logger.info("Console created.")
        time.sleep(0.1)

        # 3. Viz Module
        logger.info("Creating Viz...")
        viz_module = Viz(instance_id="test-viz")
        logger.info("Viz created.")
        time.sleep(0.1)

        # 4. Canvas Module
        logger.info("Creating Canvas...")
        canvas_module = Canvas(width=350, height=250, bg_color="beige", instance_id="test-canvas")
        # Initial drawing
        canvas_module.config(stroke_style="black", line_width=1)
        canvas_module.draw_rect(5, 5, 340, 240, filled=False) # Border
        logger.info("Canvas created.")
        time.sleep(0.1)

        # --- Setup Observable Values and show in Viz ---
        logger.info("Setting up Observable Values...")
        obs_counter = ObservableValue(0)
        obs_list = ObservableValue(['initial_a', 'initial_b'])
        obs_dict = ObservableValue({'a': 100, 'persistent': 'value'})
        obs_set = ObservableValue({'apple', 'banana'})
        obs_complex = ObservableValue({
            'id': 123,
            'name': 'Complex Object',
            'is_active': True,
            'nested_list': [101, 102],
            'nested_dict': {'a': 1.1, 'b': None, 'c': 'initial_c'},
            'nested_set': {'x', 'y'}
        })
        # Also show some static values
        static_string = "This is static"
        static_tuple = (10, 20, 30)

        if viz_module:
            viz_module.show("Counter", obs_counter)
            viz_module.show("Observable List", obs_list)
            viz_module.show("Observable Dict", obs_dict)
            viz_module.show("Observable Set", obs_set)
            viz_module.show("Complex Observable", obs_complex)
            viz_module.show("Static String", static_string)
            viz_module.show("Static Tuple", static_tuple)
            logger.info("Observable Values shown in Viz.")
        else:
             logger.error("Viz module not available to show variables.")

        logger.info("--- Setup Complete ---")
        if console_module:
            console_module.print("All modules initialized. Test running...")

    except Exception as e:
        logger.exception("Error during module setup!")
        raise # Re-raise exception to stop the script

# --- Main Test Loop Function ---
def run_tests(duration: int):
    """Runs periodic updates for a given duration."""
    global obs_counter, grid_module, canvas_module
    start_time = time.time()
    logger.info(f"--- Starting Test Loop (Duration: {duration}s) ---")
    counter = 0
    angle = 0

    while time.time() - start_time < duration:
        loop_start = time.time()

        # 1. Update Observable Counter periodically
        if obs_counter is not None:
            # Alternate between set and direct modification if possible (though set is standard)
            if counter % 5 == 0:
                 obs_counter.set(obs_counter.get() + 10)
            # else: # Direct math usually doesn't work unless type overloads operators
                 # obs_counter += 1 # This likely won't work directly on ObservableValue

        # 2. Update Grid randomly
        if grid_module:
            rand_x = random.randint(0, grid_module.width - 1)
            rand_y = random.randint(0, grid_module.height - 1)
            rand_color = f"hsl({random.randint(0, 360)}, 70%, 80%)" # Random light color
            grid_module.set_color(rand_x, rand_y, rand_color)
            if counter % 10 == 0: # Occasionally clear a cell
                 clear_x = random.randint(0, grid_module.width - 1)
                 clear_y = random.randint(0, grid_module.height - 1)
                 grid_module.clear_cell(clear_x, clear_y)

        # 3. Draw on Canvas periodically
        if canvas_module:
            # Simple animation - draw lines radiating from center
            center_x = canvas_module.width / 2
            center_y = canvas_module.height / 2
            radius = min(center_x, center_y) * 0.8
            end_x = center_x + radius * math.cos(math.radians(angle))
            end_y = center_y + radius * math.sin(math.radians(angle))
            hue = angle % 360
            canvas_module.config(stroke_style=f"hsl({hue}, 80%, 50%)", line_width=1)
            canvas_module.draw_line(center_x, center_y, end_x, end_y)
            angle = (angle + 15) % 360 # Increment angle

            # Occasionally clear canvas
            if counter % 50 == 49: # Every 50 loops approx
                 canvas_module.clear()
                 canvas_module.config(stroke_style="black", line_width=1)
                 canvas_module.draw_rect(5, 5, canvas_module.width-10, canvas_module.height-10) # Redraw border
                 logger.info("Canvas cleared periodically.")

        # 4. Log progress
        if counter % 20 == 0 and console_module: # Log every ~20 seconds if loop is 1s
             logger.debug(f"Test loop iteration {counter}")
             console_module.log(f"Tick {counter}...")

        counter += 1
        # Ensure loop takes roughly 1 second
        loop_duration = time.time() - loop_start
        sleep_time = max(0, 1.0 - loop_duration)
        time.sleep(sleep_time)

    logger.info(f"--- Test Loop Finished (Ran for ~{duration}s) ---")

# --- Main Execution ---
if __name__ == "__main__":
    import math # Import math for canvas example

    logger.info("Starting Sidekick Hero Test Script...")
    try:
        # 1. Set URL (optional, if not default)
        # set_url(SIDEKICK_URL)

        # 2. Activate connection (needed before first module)
        # activate_connection() # Important!

        # 3. Setup modules (which will trigger connection)
        setup_sidekick_modules()

        # 4. Run the main test loop
        run_tests(TEST_DURATION_SECONDS)

        logger.info("Test script completed normally.")

    except Exception as e:
        logger.exception("An unhandled exception occurred in the main script!")
    finally:
        # 5. Close connection explicitly (optional, atexit handles it too)
        logger.info("Requesting connection close...")
        close_connection()
        logger.info("Script finished.")