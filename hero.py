# hero.py
import time
import random
# Import ObservableValue directly now
from sidekick import Grid, Console, Viz, Canvas, ObservableValue
from typing import Dict, Any, Optional, Set, Union

# --- Simple Custom Class for Demo ---
class Point:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self._internal = "secret"

    def move(self, dx: int, dy: int):
        self.x += dx
        self.y += dy

    def __repr__(self):
        return f"Point(x={self.x}, y={self.y})"

# --- Configuration ---
CLICK_COLOR = "magenta"

# --- Global variables ---
grid: Optional[Grid] = None
console: Optional[Console] = None
viz: Optional[Viz] = None
canvas: Optional[Canvas] = None

# --- Callback Functions ---
def handle_grid_click(message: Dict[str, Any]):
    global grid, console
    print(f"Received message from Grid: {message}")
    if not grid or not console: return
    if message.get("method") == "notify" and message.get('payload', {}).get('event') == 'click':
        payload = message['payload']
        x, y = payload.get('x'), payload.get('y')
        if x is not None and y is not None:
            console.log(f"Grid Clicked at ({x}, {y})! Setting color to {CLICK_COLOR}.")
            try: grid.set_color(x, y, CLICK_COLOR)
            except Exception as e: console.log(f"Error processing click at ({x},{y}): {e}")

def handle_console_input(message: Dict[str, Any]):
    global console, viz
    print(f"Received message from Console: {message}")
    if not console: return
    if message.get("method") == "notify" and message.get('payload', {}).get('event') == 'submit':
        user_input = message['payload'].get('value', '')
        console.log(f">>> User entered: {user_input}")
        if viz: viz.show("last_console_input", user_input) # Show raw value
        console.print(f"Echo: {user_input}")

# --- Main Execution ---
if __name__ == "__main__":
    print("Starting Hero script...")
    # ... (initial setup logs) ...

    # --- Initialize Sidekick Modules ---
    try:
        # grid = Grid(20, 20, instance_id="main-grid", on_message=handle_grid_click)
        console = Console(instance_id="main-console", on_message=handle_console_input)
        viz = Viz(instance_id="main-viz")
        canvas = Canvas(width=400, height=250, instance_id="main-canvas")

        console.print("--- Sidekick Hero Initialized ---")
        console.log("Modules ready. Try console input or grid clicks.")

    except Exception as e:
        print(f"Error initializing Sidekick modules: {e}")
        print("Ensure the Sidekick server (Node.js) is running.")
        exit(1)

    # --- Viz Module Examples (using ObservableValue) ---
    console.log("\n=== Variable Visualization Examples ===")
    viz.show('status', 'Starting examples...')
    time.sleep(0.5)

    # 1. Primitives - Show raw first
    viz.show('my_int_raw', 123)
    viz.show('my_str_raw', "Initial")
    time.sleep(1)

    # 2. Primitives wrapped in ObservableValue
    obs_int = ObservableValue(1000)
    obs_str = ObservableValue("Hello")
    viz.show('my_observable_int', obs_int) # Pass the observable itself
    viz.show('my_observable_str', obs_str)
    console.log("Showing observable primitives")
    viz.show('status', 'Observable primitives shown')
    time.sleep(1.5)

    console.log("Updating observable int via .set()...")
    obs_int.set(1001) # Use .set() to change value and trigger update
    time.sleep(1)
    console.log("Updating observable string via .set()...")
    obs_str.set("Hello Sidekick!")
    time.sleep(1)

    # 3. Containers wrapped in ObservableValue
    obs_list = ObservableValue([1, 2])
    obs_dict = ObservableValue({'a': True})
    obs_set = ObservableValue({'start'})

    viz.show('my_observable_list', obs_list)
    viz.show('my_observable_dict', obs_dict)
    viz.show('my_observable_set', obs_set)
    console.log("Showing observable containers")
    viz.show('status', 'Observable containers shown')
    time.sleep(1.5)

    console.log("Appending to observable list...")
    obs_list.append({'key': 'value'}) # Use list methods directly
    time.sleep(1)
    console.log("Updating observable dict...")
    obs_dict['b'] = 123 # Use dict methods directly
    time.sleep(1)
    console.log("Adding to observable set...")
    obs_set.add('new_item') # Use set methods directly
    time.sleep(1)

    # 4. Showing an ObservableValue that itself contains another ObservableValue
    obs_inner = ObservableValue("Inner Value")
    obs_outer_list = ObservableValue([10, obs_inner, 30])
    viz.show("nested_observable", obs_outer_list)
    console.log("Showing list containing an observable")
    viz.show('status', 'Nested observable shown')
    time.sleep(1.5)

    console.log("Updating inner observable...")
    obs_inner.set("Inner Updated!") # This should trigger update for nested_observable in Viz
    time.sleep(1.5)
    console.log("Appending to outer observable list...")
    obs_outer_list.append(40) # This should also trigger update
    time.sleep(1.5)


    # --- Canvas Drawing Example (remains the same) ---
    # ... (canvas drawing code from previous example) ...
    console.log("Canvas drawing demo finished.")


    # --- Keep the script running ---
    viz.show('status', 'Examples finished. Listening for interactions.')
    console.log("\n=== Ready for Interactions / Script End ===")
    console.log("Script is listening for grid clicks and console input.")
    console.log("Press Ctrl+C in this terminal to exit.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Exiting Hero script...")
    finally:
        # Cleanup
        print("Cleaning up Sidekick modules...")
        if grid: grid.remove()
        if console: console.remove()
        if viz: viz.remove() # Viz.remove() now handles unsubscribing
        if canvas: canvas.remove()
        print("Sidekick modules removed. Connection will close.")

    print("Hero script finished.")