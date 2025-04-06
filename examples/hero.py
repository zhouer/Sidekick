import sidekick
import time
import random
import logging
import colorsys  # For generating distinct colors
from typing import Any

# --- Logging Setup ---
# Configure Sidekick connection logger for detailed WebSocket communication (optional)
# logging.getLogger("SidekickConn").setLevel(logging.DEBUG)
# Configure general logging for the script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ComprehensiveTest")

# --- Configuration ---
# Use clear_on_connect=True to ensure a fresh UI state each time the script runs.
sidekick.set_config(clear_on_connect=True, clear_on_disconnect=False)

# --- Global State ---
script_running = True
# Store module instances globally so callbacks can access them if needed
main_console: sidekick.Console | None = None
info_console: sidekick.Console | None = None
test_grid: sidekick.Grid | None = None
test_canvas: sidekick.Canvas | None = None
test_viz: sidekick.Viz | None = None
test_controls: sidekick.Control | None = None

# --- Helper Functions ---
def hsv_to_hex(h, s, v):
    """Converts HSV color values to a hex string."""
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return '#{:02x}{:02x}{:02x}'.format(int(r*255), int(g*255), int(b*255))

# --- Callback Handlers ---

# -- Global Handler --
def global_message_handler(message: dict):
    """Logs all messages received from Sidekick."""
    module = message.get('module', '?')
    msg_type = message.get('type', '?')
    src = message.get('src', 'N/A')
    logger.debug(f"[Global Handler] Received: mod={module}, type={msg_type}, src={src}")

# -- Console Handlers --
def handle_main_console_input(value: str):
    """Handles input from the main interactive console."""
    global script_running
    if not main_console or not info_console: return

    main_console.print(f">>> Received command: '{value}'")
    info_console.log(f"Main Console Input: '{value}'") # Log to info console

    command = value.lower().strip()
    if command == 'quit':
        main_console.print("Quit command received. Shutting down...")
        script_running = False
    elif command == 'clear grid':
        if test_grid: test_grid.clear(); main_console.print("Grid cleared.")
    elif command == 'clear canvas':
        if test_canvas: test_canvas.clear(); main_console.print("Canvas cleared.")
    elif command == 'populate grid':
        if test_grid: populate_grid_demo(test_grid); main_console.print("Grid populated.")
    elif command.startswith('viz remove '):
        var_name = value.split(' ', 2)[-1].strip()
        if test_viz and var_name:
            test_viz.remove_variable(var_name)
            main_console.print(f"Removed '{var_name}' from Viz.")
        else:
            main_console.print(f"Cannot remove '{var_name}' from Viz.")
    else:
        main_console.print(f"Unknown command: '{value}'. Try: quit, clear grid, clear canvas, populate grid, viz remove <name>")

# -- Grid Handlers --
def handle_grid_click(x: int, y: int):
    """Handles clicks on the test grid."""
    if not info_console or not test_grid: return
    info_console.log(f"Grid clicked at ({x}, {y})")
    test_grid.set_cell(x, y, color="yellow", text=f"{x}, {y}") # Update text to show coordinates
    # To revert color automatically would require timers or frontend logic.

# -- Control Handlers --
def handle_control_click(control_id: str):
    """Handles button clicks from the control panel."""
    if not info_console: return
    info_console.log(f"Control Button Clicked: '{control_id}'")

    if control_id == 'add_random_button':
        if test_controls:
            new_id = f"random_btn_{random.randint(100, 999)}"
            test_controls.add_button(control_id=new_id, text=f"Rand {new_id[-3:]}")
            info_console.log(f"Added button: {new_id}")
    elif control_id.startswith('random_btn_'):
        info_console.log(f"Random button '{control_id}' does nothing specific yet.")
    elif control_id == 'self_destruct_button':
        if test_controls:
            info_console.log("Removing self-destruct button...")
            try:
                test_controls.remove_control(control_id)
            except Exception as e:
                 info_console.log(f"Error removing control: {e}")

def handle_control_input(control_id: str, value: str):
    """Handles text input submissions from the control panel."""
    if not info_console: return
    info_console.log(f"Control Input Submitted: ID='{control_id}', Value='{value}'")
    if control_id == 'viz_input':
        if test_viz:
            try:
                # VERY UNSAFE, for demo only! Eval can execute arbitrary code.
                evaluated_value = eval(value)
                test_viz.show(f"eval_{random.randint(100,999)}", evaluated_value)
                info_console.log(f"Evaluated and showed '{value}' in Viz.")
            except Exception as e:
                info_console.log(f"Failed to eval '{value}': {e}")
        else:
            info_console.log("Viz module not available.")

# -- Generic Error Handler --
def handle_module_error(module_name: str, error_message: str):
    """Handles errors reported by any module."""
    log_message = f"ERROR from {module_name}: {error_message}"
    logger.error(log_message)
    # Try logging to info_console first, then main_console as fallback
    target_console = info_console if info_console else main_console
    if target_console:
        try:
            # Avoid potential infinite loops if console itself errors
            # Use target_id for comparison as module_name might just be descriptive
            if target_console.target_id and module_name != target_console.target_id:
                target_console.print(log_message)
            elif not target_console.target_id: # Fallback if target_id isn't set yet?
                 target_console.print(log_message)
        except Exception as e:
            logger.error(f"Failed to print error to console: {e}")

# --- Demo Functions ---

def populate_grid_demo(grid_instance: sidekick.Grid):
    """Fills the grid with a color/text pattern."""
    logger.info("Populating grid demo...")
    if not grid_instance: return
    grid_instance.clear() # Start fresh
    rows = grid_instance.num_rows
    cols = grid_instance.num_columns
    for r in range(rows):
        for c in range(cols):
            hue = (r / rows + c / cols) / 2.0
            saturation = 0.7 + (r / rows) * 0.3
            value = 0.6 + (c / cols) * 0.4
            color = hsv_to_hex(hue % 1.0, saturation, value)
            text = f"{c},{r}"
            grid_instance.set_cell(c, r, color=color, text=text)
            # Add small delay for visual effect, but can make it slow
            # time.sleep(0.005)
    logger.info("Grid population demo complete.")

def canvas_drawing_demo(canvas_instance: sidekick.Canvas):
    """Draws various shapes on the canvas."""
    logger.info("Starting canvas drawing demo...")
    if not canvas_instance: return

    w, h = canvas_instance.width, canvas_instance.height

    # Background
    canvas_instance.clear("#111827") # Dark gray background
    time.sleep(0.2)

    # Grid lines
    canvas_instance.config(stroke_style="#4B5563", line_width=1) # Gray grid lines
    for i in range(1, 10):
        x = w * i / 10
        y = h * i / 10
        canvas_instance.draw_line(int(x), 0, int(x), h)
        canvas_instance.draw_line(0, int(y), w, int(y))
    time.sleep(0.3)

    # Colorful shapes
    # Red outlined rectangle
    canvas_instance.config(stroke_style="#EF4444", line_width=3)
    canvas_instance.draw_rect(int(w*0.1), int(h*0.1), int(w*0.3), int(h*0.25), filled=False)
    time.sleep(0.2)
    # Blue filled rectangle
    canvas_instance.config(fill_style="#3B82F6")
    canvas_instance.draw_rect(int(w*0.6), int(h*0.15), int(w*0.25), int(h*0.3), filled=True)
    time.sleep(0.2)
    # Green outlined circle
    canvas_instance.config(stroke_style="#10B981", line_width=4)
    canvas_instance.draw_circle(int(w*0.25), int(h*0.7), int(min(w, h) * 0.15), filled=False)
    time.sleep(0.2)
    # Yellow filled circle with purple outline
    canvas_instance.config(fill_style="#F59E0B", stroke_style="#8B5CF6", line_width=2)
    canvas_instance.draw_circle(int(w*0.75), int(h*0.75), int(min(w, h) * 0.12), filled=True)
    time.sleep(0.3)

    # Text (Requires Canvas frontend support for text drawing)
    # canvas_instance.config(fill_style="white", font="16px sans-serif")
    # canvas_instance.draw_text("Canvas Demo", w/2, h/2, align="center")

    logger.info("Canvas drawing demo complete.")

def viz_reactivity_demo(viz_instance: sidekick.Viz):
    """Demonstrates ObservableValue reactivity."""
    logger.info("Starting Viz reactivity demo...")
    if not viz_instance or not info_console: return

    info_console.log("Creating observable list/dict...")
    obs_list = sidekick.ObservableValue([100, "hello", None])
    obs_dict = sidekick.ObservableValue({"a": 1, "b": {"nested": True}})
    viz_instance.show("Reactive List", obs_list)
    viz_instance.show("Reactive Dict", obs_dict)
    time.sleep(0.5)

    info_console.log("Modifying observables...")

    # List modifications
    time.sleep(1); info_console.log(" -> list.append(True)"); obs_list.append(True)
    time.sleep(1); info_console.log(" -> list[1] = 'world'"); obs_list[1] = "world"
    time.sleep(1); info_console.log(" -> list.insert(0, 50)"); obs_list.insert(0, 50)
    time.sleep(1); info_console.log(" -> list.pop()"); obs_list.pop()
    time.sleep(1); info_console.log(" -> del list[0]"); del obs_list[0]

    # Dict modifications
    time.sleep(1); info_console.log(" -> dict['c'] = [1, 2]"); obs_dict['c'] = [1, 2]
    time.sleep(1); info_console.log(" -> dict['a'] = 5"); obs_dict['a'] = 5
    time.sleep(1); info_console.log(" -> dict['b']['nested'] = False (Directly, No notification!)")
    # NOTE: This direct modification bypasses ObservableValue's tracking on the *inner* dict.
    # The outer dict doesn't change reference, so Viz won't update automatically here.
    # To make the inner change visible, the inner dict also needs to be an ObservableValue,
    # or the outer dict needs to be explicitly set again.
    obs_dict.get()['b']['nested'] = False
    # Explicitly trigger update by setting the outer dict (optional way to show the change)
    time.sleep(1); info_console.log(" -> dict.set({...}) # Force update"); obs_dict.set(obs_dict.get()) # Trigger resend

    time.sleep(1); info_console.log(" -> del dict['a']"); del obs_dict['a']
    time.sleep(1); info_console.log(" -> dict.clear()"); obs_dict.clear()
    time.sleep(1)

    logger.info("Viz reactivity demo complete.")


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("--- Starting Comprehensive Sidekick Test ---")
    try:
        # --- Activate Connection and Register Global Handler ---
        sidekick.activate_connection()
        sidekick.register_global_message_handler(global_message_handler)
        logger.info("Connection activated, global handler registered.")
        logger.info("Waiting for connection to become ready...")
        # Wait a bit for connection and Sidekick peer announcement
        time.sleep(1.5)

        # --- Create Modules ---
        logger.info("Creating Sidekick modules...")

        # Create Info Console (read-only) first
        info_console = sidekick.Console(instance_id="info-console", show_input=False)
        info_console.on_error(lambda err: handle_module_error("info-console", err)) # Use instance_id in handler
        info_console.print("--- Test Information ---")

        # Create Main Console (interactive)
        main_console = sidekick.Console(instance_id="main-console", show_input=True)
        main_console.on_input_text(handle_main_console_input)
        main_console.on_error(lambda err: handle_module_error("main-console", err)) # Use instance_id in handler
        main_console.print("--- Main Interactive Console ---")
        main_console.print("Type commands here (e.g., 'quit'). Output below, info in the console above.")

        # Create Grid
        test_grid = sidekick.Grid(num_columns=12, num_rows=10, instance_id="demo-grid")
        test_grid.on_click(handle_grid_click)
        test_grid.on_error(lambda err: handle_module_error("demo-grid", err)) # Use instance_id in handler

        # Create Controls
        test_controls = sidekick.Control(instance_id="demo-controls")
        test_controls.on_click(handle_control_click)
        test_controls.on_input_text(handle_control_input)
        test_controls.on_error(lambda err: handle_module_error("demo-controls", err)) # Use instance_id in handler

        # Create Canvas
        test_canvas = sidekick.Canvas(width=500, height=350, instance_id="demo-canvas")
        test_canvas.on_error(lambda err: handle_module_error("demo-canvas", err)) # Use instance_id in handler

        # Create Viz
        test_viz = sidekick.Viz(instance_id="demo-viz")
        test_viz.on_error(lambda err: handle_module_error("demo-viz", err)) # Use instance_id in handler

        logger.info("All modules created.")
        info_console.log("All Sidekick modules initialized.")
        time.sleep(0.5) # Allow module spawn messages to be processed

        # --- Run Demos ---
        info_console.log("--- Starting Grid Demo ---")
        populate_grid_demo(test_grid)
        info_console.log("Grid Demo complete. Click cells!")
        time.sleep(1)

        info_console.log("--- Starting Controls Demo ---")
        test_controls.add_button(control_id="add_random_button", text="Add Random Button")
        test_controls.add_text_input(control_id="viz_input", placeholder="Enter Python expression (unsafe!)", button_text="Show in Viz")
        test_controls.add_button(control_id="self_destruct_button", text="Remove This Button")
        info_console.log("Controls Demo setup complete. Interact!")
        time.sleep(1)

        info_console.log("--- Starting Canvas Demo ---")
        canvas_drawing_demo(test_canvas)
        info_console.log("Canvas Demo complete.")
        time.sleep(1)

        info_console.log("--- Starting Viz Demo ---")
        test_viz.show("script_info", {
            "status": "Running",
            "modules_active": [m.target_id for m in [main_console, info_console, test_grid, test_controls, test_canvas, test_viz] if m is not None],
            "start_time": time.time()
        })
        test_viz.show("random_numbers", [random.random() for _ in range(5)])
        viz_reactivity_demo(test_viz)
        info_console.log("Viz Demo complete.")
        time.sleep(1)

        # --- Main Loop ---
        main_console.print("--- All Demos Complete ---")
        main_console.print("Script is running. Interact with UI or type 'quit' in this console.")
        info_console.log("Main loop started. Waiting for user interaction or 'quit' command.")

        while script_running:
            # Update a variable periodically in Viz
            if test_viz:
                 # Ensure script_info exists before trying to update time
                 script_info_val = test_viz._shown_variables.get("script_info", {}).get('value_or_observable')
                 if isinstance(script_info_val, dict):
                      script_info_val['current_time'] = time.time() # Modify dict directly
                      test_viz.show("script_info", script_info_val) # Re-show to trigger update
                 else: # Fallback if it wasn't a dict or didn't exist
                     test_viz.show("current_time", time.time())

            time.sleep(1) # Keep main thread alive

        logger.info("Main loop finished.")

    except ConnectionRefusedError:
        logger.error("Connection refused. Is the Sidekick server running?")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt detected. Exiting gracefully...")
    except Exception as e:
        logger.exception(f"An unexpected error occurred in the main thread: {e}")
        # Try to report error to console if possible
        if main_console:
            try: main_console.print(f"FATAL ERROR: {e}")
            except Exception: pass
    finally:
        logger.info("--- Initiating Script Cleanup ---")
        # Explicitly remove modules in reverse order of creation (optional, but good practice)
        if test_viz: test_viz.remove()
        if test_canvas: test_canvas.remove()
        if test_controls: test_controls.remove()
        if test_grid: test_grid.remove()
        # Keep consoles until the very end if possible
        time.sleep(0.1) # Allow final messages
        if main_console: main_console.remove()
        if info_console: info_console.remove()

        # Unregister global handler
        sidekick.register_global_message_handler(None)

        # Close connection (also called by atexit)
        sidekick.close_connection()
        logger.info("--- Comprehensive Sidekick Test Finished ---")