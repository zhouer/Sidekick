# comprehensive_hero_test.py
import time
import logging
import random
from sidekick import (
    Grid,
    Console,
    Viz,
    Canvas,
    Control,
    ObservableValue,
    set_url,
    close_connection,
    connection # Import connection to potentially access logger/other functions
)

# --- Configuration ---
SIDEKICK_URL = "ws://localhost:5163" # Default URL
INTERACTION_WAIT_TIME = 15 # Seconds to wait for user interaction tests
STEP_DELAY = 1.5 # Seconds delay between automated steps for visualization

# --- Logging Setup ---
# Configure logging to see Sidekick library messages and script output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# Optionally set Sidekick connection logger to DEBUG for more detail
connection.logger.setLevel(logging.DEBUG)
script_logger = logging.getLogger("HeroTestScript")
script_logger.setLevel(logging.INFO)

# --- Callback Handlers ---
# These functions will be called when messages arrive from specific modules

def grid_interaction_handler(message):
    """Handles messages from the 'test-grid'."""
    script_logger.info(f"[Grid Handler] Received: {message}")
    payload = message.get('payload', {})
    if message.get('method') == 'notify' and payload.get('event') == 'click':
        script_logger.info(f"--> Grid cell clicked at ({payload.get('x')}, {payload.get('y')})")
        # Example response: Set clicked cell to blue
        grid.set_color(payload.get('x'), payload.get('y'), 'blue')

def console_interaction_handler(message):
    """Handles messages from the 'main-console'."""
    script_logger.info(f"[Console Handler] Received: {message}")
    payload = message.get('payload', {})
    if message.get('method') == 'notify' and payload.get('event') == 'submit':
        user_input = payload.get('value', '')
        script_logger.info(f"--> Console input submitted: '{user_input}'")
        console.print(f"Hero received: '{user_input}'. Responding...")
        # Example response based on input
        if user_input.lower() == 'hello':
            console.print("Hello there!")
        elif user_input.lower() == 'clear grid':
             grid.clear()
             console.print("Grid cleared via console command.")
        else:
            console.print(f"Unknown command: {user_input}")

def control_interaction_handler(message):
    """Handles messages from the 'interactive-controls'."""
    script_logger.info(f"[Control Handler] Received: {message}")
    payload = message.get('payload', {})
    event = payload.get('event')
    control_id = payload.get('controlId') # Expecting camelCase from protocol

    if message.get('method') == 'notify':
        if event == 'click':
            script_logger.info(f"--> Control Button '{control_id}' clicked.")
            if control_id == 'test_button_1':
                console.log("Test Button 1 was clicked!")
                # Example: Change grid cell on button click
                grid.set_color(0, 0, f"rgb({random.randint(0,255)},{random.randint(0,255)},{random.randint(0,255)})")
            elif control_id == 'remove_me_btn':
                 console.log(f"Button '{control_id}' clicked. Removing this button.")
                 controls.remove_control('remove_me_btn') # Test removing control from callback
        elif event == 'inputText':
            value = payload.get('value', '')
            script_logger.info(f"--> Control Input '{control_id}' submitted value: '{value}'")
            if control_id == 'text_input_1':
                 console.log(f"Received text from Control Input 1: {value.upper()}")
                 # Example: Update a visualized variable based on input
                 if 'message_obs' in globals():
                     message_obs.set(f"From Control: {value}")


# --- Main Test Script ---
if __name__ == "__main__":
    script_logger.info("--- Starting Sidekick Comprehensive Test Script ---")

    try:
        # --- Optional: Set URL if not default ---
        # set_url("ws://...")
        # script_logger.info(f"Set Sidekick URL to: {SIDEKICK_URL}") # Log if set_url is used

        # --- Initialize Modules ---
        script_logger.info("Initializing modules...")
        # Grid with click handler
        grid = Grid(num_columns=10, num_rows=8, instance_id="test-grid", on_message=grid_interaction_handler)
        # Console with input handler
        console = Console(instance_id="main-console", on_message=console_interaction_handler)
        # Control panel with interaction handler
        controls = Control(instance_id="interactive-controls", on_message=control_interaction_handler)
        # Canvas for drawing
        canvas = Canvas(width=400, height=200, bg_color="lightyellow", instance_id="drawing-canvas")
        # Variable visualizer
        viz = Viz(instance_id="variable-viz")
        script_logger.info("Modules initialized.")
        time.sleep(STEP_DELAY)

        # --- Console Tests ---
        console.log("--- Console Tests ---")
        console.print("Hello from the Hero script!")
        console.print("Testing print with", "multiple", "arguments", sep='|')
        console.print("This line has no 'end'.", end='')
        console.print("This should be on the same line.")
        time.sleep(STEP_DELAY)
        console.clear()
        console.print("Console cleared. Waiting for input...")
        script_logger.info(f"Console ready. Try typing 'hello' or 'clear grid' and submitting in Sidekick UI.")
        time.sleep(STEP_DELAY) # Give some time to see the message

        # --- Grid Tests ---
        console.log("--- Grid Tests ---")
        grid.set_color(1, 1, "red")
        grid.set_text(1, 1, "Hi")
        grid.set_color(3, 4, "#00FF00")
        grid.set_text(3, 4, "OK")
        grid.set_color(5, 0, "rgba(0, 0, 255, 0.5)")
        console.print("Grid cells updated.")
        script_logger.info("Grid updated. Try clicking cells in the Sidekick UI.")
        time.sleep(STEP_DELAY * 2)
        console.print("Clearing grid...")
        grid.clear() # Test grid clear
        console.print("Grid cleared.")
        time.sleep(STEP_DELAY)

        # --- Canvas Tests ---
        console.log("--- Canvas Tests ---")
        # Config styles
        canvas.config(line_width=3, stroke_style="purple")
        # Draw shapes
        canvas.draw_line(10, 10, 390, 190)
        canvas.config(fill_style="orange")
        canvas.draw_rect(50, 50, 100, 80, filled=True)
        canvas.config(stroke_style="teal", line_width=1)
        canvas.draw_rect(200, 30, 150, 100, filled=False)
        canvas.config(fill_style="rgba(255, 0, 0, 0.7)")
        canvas.draw_circle(80, 150, 40, filled=True)
        canvas.config(line_width=5, stroke_style="black")
        canvas.draw_circle(300, 100, 50, filled=False)
        console.print("Canvas drawing commands sent.")
        # Test rapid commands (check frontend queueing)
        console.print("Sending rapid canvas commands...")
        for i in range(0, 400, 20):
            canvas.config(stroke_style=f"hsl({i % 360}, 100%, 50%)")
            canvas.draw_line(i, 195, i+10, 10)
        console.print("Rapid commands finished.")
        time.sleep(STEP_DELAY * 2)
        canvas.clear(color="lightblue") # Test clear with color
        console.print("Canvas cleared with lightblue.")
        time.sleep(STEP_DELAY)

        # --- Control Tests ---
        console.log("--- Control Tests ---")
        controls.add_button(control_id="test_button_1", text="Click Me!")
        controls.add_text_input(
            control_id="text_input_1",
            placeholder="Enter message for Viz",
            initial_value="Default Text",
            button_text="Update Viz"
        )
        controls.add_button(control_id="remove_me_btn", text="Remove This Button")
        console.print("Controls added.")
        script_logger.info("Controls added. Try clicking buttons or submitting text in Sidekick UI.")
        # Wait longer here to allow user interaction
        script_logger.info(f"Waiting {INTERACTION_WAIT_TIME} seconds for Control interactions...")
        time.sleep(INTERACTION_WAIT_TIME)
        # Test removing a control programmatically (if not removed by callback)
        # Check if button still exists before trying to remove
        # This requires frontend state or assuming it wasn't clicked. Let's skip for now.
        # try: controls.remove_control('remove_me_btn')
        # except Exception: pass # Might already be removed
        console.print("Finished control interaction test period.")
        time.sleep(STEP_DELAY)


        # --- Viz Tests ---
        console.log("--- Viz Tests ---")
        # Static values
        viz.show("my_integer", 123)
        viz.show("my_float", 3.14159)
        viz.show("my_string", "Hello Sidekick!")
        viz.show("my_boolean", True)
        viz.show("my_none", None)
        my_list = [1, "two", None, [4, 5]]
        my_dict = {"a": 10, "b": {"c": True, "d": my_list}}
        my_set = {1, 1, 2, 3, "hello"}
        my_tuple = (100, 200)
        viz.show("my_list", my_list)
        viz.show("my_dict", my_dict)
        viz.show("my_set", my_set)
        viz.show("my_tuple", my_tuple) # Tuples are immutable, treated like lists for display

        console.print("Static variables shown in Viz.")
        time.sleep(STEP_DELAY * 2)

        # Observable values
        console.print("Testing ObservableValues with Viz...")
        counter_obs = ObservableValue(0)
        list_obs = ObservableValue([10, 20, {"id": "item3"}])
        dict_obs = ObservableValue({"x": 1, "y": 2, "nested": ObservableValue("initial")}) # Nested observable
        set_obs = ObservableValue({100, 200})
        message_obs = ObservableValue("Original message") # Used by control callback

        viz.show("counter", counter_obs)
        viz.show("observable_list", list_obs)
        viz.show("observable_dict", dict_obs)
        viz.show("observable_set", set_obs)
        viz.show("message", message_obs)
        console.print("Observable variables shown. Starting updates...")
        time.sleep(STEP_DELAY)

        # Test updates
        script_logger.info("Updating counter (set)...")
        counter_obs.set(1)
        time.sleep(STEP_DELAY)

        script_logger.info("Appending to list (append)...")
        list_obs.append(30)
        time.sleep(STEP_DELAY)

        script_logger.info("Updating list item (setitem)...")
        list_obs[1] = 25
        time.sleep(STEP_DELAY)

        script_logger.info("Popping from list (pop)...")
        popped = list_obs.pop()
        console.print(f"(Popped value: {popped})")
        time.sleep(STEP_DELAY)

        script_logger.info("Updating dict item (setitem)...")
        dict_obs["y"] = 3
        time.sleep(STEP_DELAY)

        script_logger.info("Adding dict item (setitem)...")
        dict_obs["z"] = ObservableValue(99) # Add another observable
        time.sleep(STEP_DELAY)

        script_logger.info("Updating nested observable in dict (set)...")
        dict_obs["nested"].set("updated nested") # Access internal observable and set
        time.sleep(STEP_DELAY)

        script_logger.info("Deleting dict item (delitem)...")
        del dict_obs["x"]
        time.sleep(STEP_DELAY)

        script_logger.info("Updating dict via update() method (multiple setitem)...")
        dict_obs.update({"y": 4, "new_key": "added"})
        time.sleep(STEP_DELAY)

        script_logger.info("Adding to set (add_set)...")
        set_obs.add(300)
        set_obs.add(100) # Should not trigger notification
        time.sleep(STEP_DELAY)

        script_logger.info("Discarding from set (discard_set)...")
        set_obs.discard(200)
        set_obs.discard(999) # Should not trigger notification
        time.sleep(STEP_DELAY)

        script_logger.info("Clearing list (clear)...")
        list_obs.clear()
        time.sleep(STEP_DELAY)

        script_logger.info("Clearing dict (clear)...")
        dict_obs.clear()
        time.sleep(STEP_DELAY)

        # Test removing variable
        console.print("Removing 'counter' and 'observable_set' from Viz...")
        viz.remove_variable("counter")
        viz.remove_variable("observable_set")
        time.sleep(STEP_DELAY)

        console.print("Observable value tests complete.")

        # --- Keep Running for Interaction ---
        script_logger.info("--- Test Script Setup Complete ---")
        script_logger.info("Script will now wait for interactions or KeyboardInterrupt (Ctrl+C).")
        script_logger.info("Try interacting with the Grid, Console, and Controls in Sidekick.")
        while True:
            # Keep main thread alive to allow background listener thread to work
            time.sleep(10)
            # Optional: Add periodic updates here if needed
            # counter_obs.set(counter_obs.get() + 10)
            # viz.show("timestamp", time.time())


    except KeyboardInterrupt:
        script_logger.info("\n--- KeyboardInterrupt received, shutting down. ---")
    except ConnectionRefusedError:
         script_logger.error(f"Connection Refused: Could not connect to Sidekick at {SIDEKICK_URL}. Is Sidekick running?")
    except Exception as e:
        script_logger.exception(f"An unexpected error occurred: {e}")
    finally:
        # --- Cleanup ---
        # Optional: Explicitly remove modules (connection closes automatically via atexit)
        # It's often better to let atexit handle closure unless testing removal specifically.
        script_logger.info("Performing cleanup (connection will close via atexit).")
        # if 'grid' in globals(): grid.remove()
        # if 'console' in globals(): console.remove()
        # if 'controls' in globals(): controls.remove()
        # if 'canvas' in globals(): canvas.remove()
        # if 'viz' in globals(): viz.remove()

        # Ensure connection closes if script exits abnormally before atexit might run
        # close_connection() # Usually handled by atexit

        script_logger.info("--- Test Script Finished ---")